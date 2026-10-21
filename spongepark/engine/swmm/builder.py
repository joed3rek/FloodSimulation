"""Build an EPA SWMM model from the site, an NbS layout and design storms.

Representation (documented in the .inp header and docs/swmm.md):

* Site subcatchments: element footprints are cut out of them, so areas reconcile.
* LID elements (rain garden, bioswale, edge engineering): a dedicated subcatchment
  whose whole area is one LID unit. Upstream subcatchments route to it (run-on),
  and its outflow goes to ``outflow_to``.
* Storage elements (ponds, wetland, recharge well, check dam): a storage node with
  a tabular stage-area curve and constant bed seepage (Ksat only), plus a
  "direct rain" subcatchment over its footprint so rain on the water surface is
  counted. Controlled outlets are orifices (or a weir at pool level for wetlands);
  overflow is a weir at the crest.
* Canopy interception is applied outside SWMM: subcatchments with canopy get their
  own rain gauge carrying net (below-canopy) rainfall.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..interception.canopy import CanopyCover, canopy_cover, net_rainfall
from ..nbs.catalogue import LID_BIORETENTION, LID_SWALE
from ..nbs.components import NbSElement
from ..project.parameters import ParameterSet
from ..rainfall.hyetograph import Hyetograph
from ..site.model import Site, SiteError, Subcatchment
from .inp import InpFile, hhmm, hhmmss

log = logging.getLogger(__name__)

START_DATE = "01/01/2000"


class BuildError(ValueError):
    pass


def swmm_id(s: str) -> str:
    """SWMM object names may not contain spaces or ';'."""
    out = re.sub(r"[^A-Za-z0-9_.\-]", "_", s)
    if not out:
        raise BuildError(f"invalid id '{s}'")
    return out


@dataclass
class SubcatchSpec:
    id: str
    geom: BaseGeometry
    area_m2: float
    outlet: str  # SWMM node or subcatchment id
    pct_imperv: float
    width_m: float
    slope_pct: float
    soil_zone: str
    n_imperv: float
    n_perv: float
    dstore_imperv_mm: float
    dstore_perv_mm: float
    pct_zero: float
    canopy: CanopyCover
    kind: str  # "site" | "external" | "lid" | "direct"
    element_id: Optional[str] = None
    gauge: str = "SITE"
    curve_number: Optional[float] = None  # pervious CN (CURVE_NUMBER infiltration only)
    cn_source: str = ""


@dataclass
class ElementSwmm:
    element_id: str
    type: str
    is_lid: bool
    subcatchment: str  # LID subcatchment or direct-rain subcatchment
    node: Optional[str] = None  # storage node
    controlled_link: Optional[str] = None
    overflow_link: Optional[str] = None
    pool_depth_m: float = 0.0
    crest_depth_m: float = 0.0
    area_m2: float = 0.0


@dataclass
class ModelSpec:
    """Structure of one option's SWMM model, independent of the storm."""

    option_id: str
    subcatchments: List[SubcatchSpec]
    elements: Dict[str, ElementSwmm]
    element_objs: Dict[str, NbSElement]
    outfalls: List[str]  # every SWMM outfall node (physical outfalls plus per-link outfall nodes)
    links_to_outfall: Dict[str, str]  # link id -> role ("controlled" | "overflow")
    infiltration_method: str
    notes: List[str] = field(default_factory=list)
    outfall_of: Dict[str, str] = field(default_factory=dict)  # SWMM outfall node -> physical outfall id
    outfall_role: Dict[str, str] = field(default_factory=dict)  # SWMM outfall node -> "runoff"|"controlled"|"overflow"

    @property
    def gauges(self) -> List[str]:
        return sorted({s.gauge for s in self.subcatchments})

    def area_m2(self, kinds: Tuple[str, ...] = ("site", "lid", "direct")) -> float:
        return float(sum(s.area_m2 for s in self.subcatchments if s.kind in kinds))

    def total_area_m2(self) -> float:
        return float(sum(s.area_m2 for s in self.subcatchments))


CALIBRATION_KEYS = {"infiltration": "calibration.infiltration_factor", "roughness": "calibration.roughness_factor",
                    "depression_storage": "calibration.depression_storage_factor",
                    "imperviousness": "calibration.imperviousness_factor"}


def calibration_factors(params: ParameterSet) -> Dict[str, float]:
    """Multipliers on site-surface parameters (1 = uncalibrated). Infiltration scales Horton/Green-Ampt
    rates, or the curve number's potential retention S."""
    return {k: float(params.value_or(v, 1.0)) for k, v in CALIBRATION_KEYS.items()}


# --------------------------------------------------------------------------- structure
def build_spec(
    site: Site,
    elements: List[NbSElement],
    params: ParameterSet,
    option_id: str,
) -> ModelSpec:
    """Assemble the model structure (subcatchments, elements, routing)."""
    method = str(params.value("swmm.infiltration_method")).upper()
    cap_default = float(params.value("interception.capacity_mm"))
    notes: List[str] = []
    site.validate()
    out_ids = {swmm_id(o.id) for o in site.outfalls}

    cal = calibration_factors(params)
    if any(v != 1.0 for v in cal.values()):
        notes.append("calibration factors applied to site surfaces: "
                     + ", ".join(f"{k} x{v:g}" for k, v in cal.items()))

    def cn_fields(s) -> Dict[str, object]:
        if "CURVE" not in method:
            return {}
        cn, src, _ = site.pervious_cn(s)
        if cal["infiltration"] != 1.0:  # scale the potential retention S
            S = (25400.0 / cn - 254.0) * cal["infiltration"]
            cn, src = float(np.clip(25400.0 / (S + 254.0), 30.0, 99.0)), f"{src}; calibrated S x{cal['infiltration']:g}"
        notes.append(f"subcatchment {s.id}: pervious CN {cn:g} ({src}).")
        return {"curve_number": cn, "cn_source": src}

    el_by_id = {e.id: e for e in elements}
    if len(el_by_id) != len(elements):
        raise BuildError("duplicate element ids")

    def entry(target: str, who: str) -> str:
        """SWMM object that receives water sent to ``target`` (element id or outfall id)."""
        if target in el_by_id:
            e = el_by_id[target]
            return f"LID_{swmm_id(e.id)}" if e.spec.is_lid else f"ST_{swmm_id(e.id)}"
        if swmm_id(target) in out_ids:
            return swmm_id(target)
        raise BuildError(f"{who} drains to unknown element/outfall '{target}'.")

    # subcatchment -> element assignment from inflow_from
    assigned: Dict[str, str] = {}
    sub_ids = {s.id for s in site.subcatchments + site.external}
    for e in elements:
        for sid in e.inflow_from:
            if sid not in sub_ids:
                raise BuildError(f"{e.id}: inflow_from lists unknown subcatchment '{sid}'.")
            if sid in assigned:
                raise BuildError(f"subcatchment {sid} drains to both {assigned[sid]} and {e.id}.")
            assigned[sid] = e.id

    footprints = unary_union([e.footprint() for e in elements]) if elements else None
    subs: List[SubcatchSpec] = []

    def surface(s: Subcatchment, geom: BaseGeometry, kind: str) -> Optional[SubcatchSpec]:
        area = float(geom.area)
        if area < 0.01:
            notes.append(f"subcatchment {s.id} is fully covered by NbS footprints and was removed.")
            return None
        zone = s.soil_zone
        if zone is None:
            z, _ = site.dominant_soil(geom)
            if z is None:
                raise SiteError(f"subcatchment {s.id} is not covered by any soil zone.")
            zone = z.id
        else:
            site.soil(zone)
        L = s.flow_length_m
        if L is None:
            L = float(np.sqrt(s.shape().area))
            notes.append(f"subcatchment {s.id}: flow length not given, sqrt(area) = {L:.1f} m used for width.")
        target = assigned.get(s.id)
        outlet = entry(target, f"subcatchment {s.id}") if target else (
            swmm_id(s.outlet) if swmm_id(s.outlet) in out_ids else swmm_id(s.outlet)
        )
        return SubcatchSpec(
            id=swmm_id(s.id), geom=geom, area_m2=area, outlet=outlet,
            pct_imperv=float(np.clip(s.pct_imperv * cal["imperviousness"], 0.0, 100.0)), width_m=area / L,
            slope_pct=s.slope_pct, soil_zone=zone,
            n_imperv=(s.n_imperv if s.n_imperv is not None else params.value("surface.n_imperv")) * cal["roughness"],
            n_perv=(s.n_perv if s.n_perv is not None else params.value("surface.n_perv")) * cal["roughness"],
            dstore_imperv_mm=(s.dstore_imperv_mm if s.dstore_imperv_mm is not None
                              else params.value("surface.dstore_imperv_mm")) * cal["depression_storage"],
            dstore_perv_mm=(s.dstore_perv_mm if s.dstore_perv_mm is not None
                            else params.value("surface.dstore_perv_mm")) * cal["depression_storage"],
            pct_zero=s.pct_zero_imperv if s.pct_zero_imperv is not None else params.value("surface.pct_zero_imperv"),
            canopy=canopy_cover(geom, site.trees, cap_default), kind=kind,
            **cn_fields(s),
        )

    for s in site.subcatchments:
        g = s.shape()
        if footprints is not None:
            g = g.difference(footprints)
        sp = surface(s, g, "site")
        if sp:
            subs.append(sp)
    for s in site.external:
        sp = surface(s, s.shape(), "external")
        if sp:
            subs.append(sp)

    # elements
    emap: Dict[str, ElementSwmm] = {}
    links_to_outfall: Dict[str, str] = {}
    # SWMM allows one inlet link per outfall: each link leaving the site gets its own outfall node
    # at the same place and invert; this also makes per-link volumes exact (cumulative inflow).
    link_outfall: Dict[str, Tuple[str, str, str]] = {}
    decks = unary_union([e.footprint() for e in elements if e.type == "green_bridge"])         if any(e.type == "green_bridge" for e in elements) else None
    for e in elements:
        eid = swmm_id(e.id)
        fp = e.footprint()
        if decks is not None and e.spec.is_lid and fp.intersects(decks):   # a bridge's deck is its own (rain on it)
            fp = fp.difference(decks)
        zone_id = e.soil_zone
        if zone_id is None:
            z, _ = site.dominant_soil(fp)
            zone_id = z.id if z else site.soils[0].id
        cov = canopy_cover(fp, site.trees, cap_default)
        if e.spec.is_lid:
            if not e.outflow_to:
                raise BuildError(f"{e.id}: LID elements need outflow_to (where surface outflow goes).")
            if e.overflow_to and e.overflow_to != e.outflow_to:
                notes.append(f"{e.id}: SWMM sends all LID surface outflow to outflow_to; overflow_to ignored.")
            slope = e.longitudinal_slope_pct if e.spec.swmm == LID_SWALE else 0.5
            subs.append(SubcatchSpec(
                id=f"LID_{eid}", geom=fp, area_m2=float(fp.area), outlet=entry(e.outflow_to, e.id),
                pct_imperv=0.0, width_m=float(np.sqrt(fp.area)), slope_pct=float(slope or 0.5), soil_zone=zone_id,
                n_imperv=params.value("surface.n_imperv"), n_perv=params.value("surface.n_perv"),
                dstore_imperv_mm=0.0, dstore_perv_mm=0.0, pct_zero=100.0, canopy=cov, kind="lid", element_id=e.id,
            ))
            emap[e.id] = ElementSwmm(e.id, e.type, True, f"LID_{eid}", area_m2=float(fp.area))
        else:
            node = f"ST_{eid}"
            subs.append(SubcatchSpec(
                id=f"DR_{eid}", geom=fp, area_m2=float(fp.area), outlet=node,
                pct_imperv=100.0, width_m=float(np.sqrt(fp.area)), slope_pct=0.5, soil_zone=zone_id,
                n_imperv=0.011, n_perv=0.011, dstore_imperv_mm=0.0, dstore_perv_mm=0.0, pct_zero=100.0,
                canopy=cov, kind="direct", element_id=e.id,
            ))
            em = ElementSwmm(e.id, e.type, False, f"DR_{eid}", node=node, pool_depth_m=e.pool_depth_m,
                             crest_depth_m=e.crest_depth_m, area_m2=float(fp.area))
            for target, role in ((e.outflow_to, "controlled"), (e.overflow_to, "overflow")):
                if not target:
                    continue
                dst = entry(target, e.id)
                if dst.startswith("LID_"):
                    raise BuildError(
                        f"{e.id}: storage elements can discharge only to storage elements or outfalls "
                        f"(got LID element '{target}')."
                    )
                link = ("OR_" if role == "controlled" and e.type != "constructed_wetland" else
                        "OW_" if role == "controlled" else "WR_") + eid
                if role == "controlled":
                    em.controlled_link = link
                else:
                    em.overflow_link = link
                if dst in out_ids:
                    links_to_outfall[link] = role
                    link_outfall[link] = (dst, f"{dst}__{link}", role)
            if e.outflow_to and e.type in ("recharge_well", "inline_check_dam"):
                raise BuildError(f"{e.id}: {e.type} has no controlled outlet; use overflow_to.")
            if e.outflow_to and e.type == "retention_pond" and not e.outlet_diameter_m:
                raise BuildError(f"{e.id}: a controlled outlet from a retention pond needs outlet_diameter_m.")
            if not e.overflow_to:
                notes.append(f"{e.id}: no overflow_to; water above Ymax is lost as node flooding.")
            emap[e.id] = em

    # gauges: subcatchments with canopy get their own net-rainfall gauge
    for s in subs:
        if s.canopy.fraction > 1e-3:
            s.gauge = s.id
    _check_routing(subs, emap, el_by_id, out_ids)
    outfall_of = {o: o for o in out_ids}
    outfall_role = {o: "runoff" for o in out_ids}
    for link, (phys, node, role) in link_outfall.items():
        outfall_of[node] = phys
        outfall_role[node] = role
    spec = ModelSpec(option_id, subs, emap, el_by_id, sorted(outfall_of), links_to_outfall, method, notes,
                     outfall_of=outfall_of, outfall_role=outfall_role)
    for n in notes:
        log.info("%s: %s", option_id, n)
    return spec


def _check_routing(subs: List[SubcatchSpec], emap, el_by_id, out_ids) -> None:
    """Reject routing loops among subcatchments and storage elements."""
    graph: Dict[str, List[str]] = {}
    for s in subs:
        graph.setdefault(s.id, []).append(s.outlet)
    for eid, em in emap.items():
        e = el_by_id[eid]
        if em.node:
            graph.setdefault(em.subcatchment, []).append(em.node)
            for t in (e.outflow_to, e.overflow_to):
                if t and t in emap:
                    graph.setdefault(em.node, []).append(emap[t].node or emap[t].subcatchment)
    state: Dict[str, int] = {}

    def visit(n: str, path: List[str]) -> None:
        if state.get(n) == 1:
            raise BuildError("routing loop: " + " -> ".join(path + [n]))
        if state.get(n) == 2:
            return
        state[n] = 1
        for m in graph.get(n, []):
            visit(m, path + [n])
        state[n] = 2

    for n in list(graph):
        visit(n, [])


# --------------------------------------------------------------------------- rendering
def gauge_series(spec: ModelSpec, storm: Hyetograph) -> Dict[str, np.ndarray]:
    """Rain gauge intensity series (mm/hr) per gauge for one storm."""
    depths = storm.depths_mm()
    out = {"SITE": storm.intensity_mm_hr.astype(float)}
    for s in spec.subcatchments:
        if s.gauge != "SITE":
            out[s.gauge] = net_rainfall(depths, s.canopy) * 60.0 / storm.dt_min
    return out


def render_inp(
    spec: ModelSpec,
    site: Site,
    params: ParameterSet,
    storms: Dict[int, Hyetograph],
    active_rp: int,
    title: str = "",
) -> str:
    """Render a runnable .inp. All storms in ``storms`` are written; gauges use ``active_rp``."""
    inp = InpFile()
    storm = storms[active_rp]
    sim_hr = storm.duration_hr + float(params.value("sim.post_storm_hr"))
    method = spec.infiltration_method

    inp.comment("TITLE", f"spongepark model: option '{spec.option_id}' - {title}")
    inp.comment("TITLE", f"Active design storm: {active_rp}-yr ({storm.method}, {storm.depth_mm:.1f} mm, "
                         f"{storm.duration_hr:g} h). To run another storm point gauges at series RP<n>_<gauge>.")
    inp.comment("TITLE", "Generated by spongepark; SWMM engine unmodified. Units: SI (m, mm, ha, m3/s).")
    inp.comment("TITLE", "LID_* = subcatchment fully occupied by one LID unit; DR_* = direct rain on a storage element.")
    inp.comment("TITLE", "<outfall>__<link> = the same physical outfall, one node per incoming link (SWMM allows one).")
    for n in spec.notes:
        inp.comment("TITLE", n)

    o = inp.option
    o("FLOW_UNITS", "CMS")
    o("INFILTRATION", method)
    o("FLOW_ROUTING", params.value("swmm.flow_routing"))
    o("LINK_OFFSETS", "DEPTH")
    o("MIN_SLOPE", 0)
    o("ALLOW_PONDING", "NO")
    o("SKIP_STEADY_STATE", "NO")
    o("START_DATE", START_DATE)
    o("START_TIME", "00:00:00")
    o("REPORT_START_DATE", START_DATE)
    o("REPORT_START_TIME", "00:00:00")
    days, rem = divmod(sim_hr, 24.0)
    o("END_DATE", _date_plus_days(int(days)))
    o("END_TIME", hhmmss(rem * 3600))
    o("SWEEP_START", "01/01")
    o("SWEEP_END", "12/31")
    o("DRY_DAYS", 0)
    o("REPORT_STEP", hhmmss(params.value("swmm.report_step_s")))
    o("WET_STEP", hhmmss(params.value("swmm.wet_step_s")))
    o("DRY_STEP", hhmmss(params.value("swmm.dry_step_s")))
    o("ROUTING_STEP", params.value("swmm.routing_step_s"))
    o("INERTIAL_DAMPING", "PARTIAL")
    o("NORMAL_FLOW_LIMITED", "BOTH")
    o("VARIABLE_STEP", 0.75)
    o("LENGTHENING_STEP", 0)
    o("MIN_SURFAREA", 0)
    o("MAX_TRIALS", 8)
    o("HEAD_TOLERANCE", 0.0015)
    o("SYS_FLOW_TOL", 5)
    o("LAT_FLOW_TOL", 5)
    o("MINIMUM_STEP", 0.5)
    o("THREADS", 1)

    inp.add("EVAPORATION", "CONSTANT", float(params.value("evaporation.rate_mm_day")))
    inp.add("EVAPORATION", "DRY_ONLY", "NO")

    interval = hhmm(storm.dt_min / 60.0)
    for g in spec.gauges:
        inp.add("RAINGAGES", f"RG_{g}", "INTENSITY", interval, 1.0, "TIMESERIES", f"RP{active_rp}_{g}")
    for rp in sorted(storms):
        for g, series in gauge_series(spec, storms[rp]).items():
            if g not in spec.gauges:
                continue
            dt_hr = storms[rp].dt_min / 60.0
            for k, v in enumerate(series):
                inp.add("TIMESERIES", f"RP{rp}_{g}", hhmm(k * dt_hr), float(v))
            inp.add("TIMESERIES", f"RP{rp}_{g}", hhmm(len(series) * dt_hr), 0.0)

    for s in spec.subcatchments:
        soil = site.soil(s.soil_zone)
        inp.add("SUBCATCHMENTS", s.id, f"RG_{s.gauge}", s.outlet, s.area_m2 / 1e4, s.pct_imperv, s.width_m,
                s.slope_pct, 0, comment=f"{s.kind}{' ' + s.element_id if s.element_id else ''}; "
                                        f"canopy {s.canopy.fraction * 100:.1f} %")
        inp.add("SUBAREAS", s.id, s.n_imperv, s.n_perv, s.dstore_imperv_mm, s.dstore_perv_mm, s.pct_zero, "OUTLET")
        if "CURVE" in method:
            if soil.dry_time_days is None:
                raise BuildError(f"soil zone {soil.id}: CURVE_NUMBER needs dry_time_days (soil recovery time).")
            if s.curve_number is None:  # LID or direct-rain area: no pervious surface left
                inp.add("INFILTRATION", s.id, 98.0, 0, soil.dry_time_days, comment="unused: no pervious area")
            else:
                inp.add("INFILTRATION", s.id, s.curve_number, 0, soil.dry_time_days, comment=s.cn_source)
        else:
            vals = soil.swmm_params(method)
            f = calibration_factors(params)["infiltration"] if s.kind in ("site", "external") else 1.0
            if "HORTON" in method:
                vals[0], vals[1] = vals[0] * f, vals[1] * f
            else:
                vals[1] = vals[1] * f
            inp.add("INFILTRATION", s.id, *vals)
        x, y = s.geom.centroid.x, s.geom.centroid.y
        poly = s.geom if s.geom.geom_type == "Polygon" else max(getattr(s.geom, "geoms", [s.geom]), key=lambda g: g.area)
        for px, py in list(poly.exterior.coords)[:-1]:
            inp.add("Polygons", s.id, float(px), float(py))

    init_sat = float(params.value("swmm.lid_initial_saturation_pct"))
    for eid, em in spec.elements.items():
        e = spec.element_objs[eid]
        if em.is_lid:
            _write_lid(inp, e, em, params, init_sat)
        else:
            _write_storage(inp, e, em, params, site)

    from shapely.geometry import shape as _shape

    phys = {swmm_id(o_.id): o_ for o_ in site.outfalls}
    for node in spec.outfalls:
        o_ = phys[spec.outfall_of[node]]
        note = "" if node == spec.outfall_of[node] else f"{spec.outfall_role[node]} link into outfall {o_.id}"
        inp.add("OUTFALLS", node, o_.invert_elev_m, o_.kind, "NO", comment=note)
        g = _shape(o_.geometry)
        inp.add("COORDINATES", node, float(g.centroid.x), float(g.centroid.y))

    inp.add("REPORT", "INPUT", "NO")
    inp.add("REPORT", "CONTROLS", "NO")
    inp.add("REPORT", "SUBCATCHMENTS", "ALL")
    inp.add("REPORT", "NODES", "ALL")
    inp.add("REPORT", "LINKS", "ALL")
    return inp.render()


def _write_lid(inp: InpFile, e: NbSElement, em: ElementSwmm, params: ParameterSet, init_sat: float) -> None:
    name = f"LC_{swmm_id(e.id)}"
    pond_mm = e.max_ponding_depth_m * 1000.0
    veg = e.vegetation_volume_fraction or 0.0
    if e.spec.swmm == LID_SWALE:
        z = e.side_slope_h_v or 0.0
        W = e.top_width_m or float(np.sqrt(em.area_m2))
        if W - 2 * z * e.max_ponding_depth_m < 0:
            raise BuildError(f"{e.id}: swale bottom width is negative (top {W} m, side {z}:1, depth "
                             f"{e.max_ponding_depth_m} m).")
        inp.add("LID_CONTROLS", name, "VS", comment=f"{e.type} {e.id}")
        inp.add("LID_CONTROLS", name, "SURFACE", pond_mm, veg, e.manning_n, e.longitudinal_slope_pct, z)
        width = W
    else:
        t = e.type
        storage_mm = (e.storage_layer_depth_m or 0.0) * 1000.0
        lid_type = "BC" if storage_mm > 0 or e.underdrain_coefficient else "RG"
        inp.add("LID_CONTROLS", name, lid_type, comment=f"{e.type} {e.id}")
        inp.add("LID_CONTROLS", name, "SURFACE", pond_mm, veg, 0.1, 0.0, 0.0)
        inp.add("LID_CONTROLS", name, "SOIL", (e.soil_media_depth_m or 0.0) * 1000.0,
                params.value(f"nbs.{t}.media_porosity"), params.value(f"nbs.{t}.media_field_capacity"),
                params.value(f"nbs.{t}.media_wilting_point"), params.value(f"nbs.{t}.media_ksat_mm_hr"),
                params.value(f"nbs.{t}.media_conductivity_slope"), params.value(f"nbs.{t}.media_suction_head_mm"))
        inp.add("LID_CONTROLS", name, "STORAGE", storage_mm,
                params.value(f"nbs.{t}.storage_layer_void_ratio"), e.infiltration_rate_mm_hr, 0,
                comment="seepage to native soil = element infiltration rate")
        if lid_type == "BC" and e.underdrain_coefficient:
            inp.add("LID_CONTROLS", name, "DRAIN", e.underdrain_coefficient, 0.5, 0, 6, 0, 0,
                    comment="underdrain from the bottom of the gravel layer")
        elif lid_type == "BC":
            inp.add("LID_CONTROLS", name, "DRAIN", 0, 0.5, 0, 6, 0, 0, comment="no underdrain")
        width = 0
    inp.add("LID_USAGE", em.subcatchment, name, 1, em.area_m2, width, init_sat, 0, 0)


def _write_storage(inp: InpFile, e: NbSElement, em: ElementSwmm, params: ParameterSet, site: Site) -> None:
    node = em.node
    curve = f"SC_{swmm_id(e.id)}"
    stage = e.stage_area()
    ymax = stage[-1][0]
    inp.add("STORAGE", node, e.invert_elev_m, ymax, e.pool_depth_m, "TABULAR", curve, 0, 1.0, 0,
            e.seepage_rate_mm_hr, 0, comment=f"{e.type} {e.id}; seepage {e.seepage_rate_mm_hr:g} mm/hr")
    for k, (h, a) in enumerate(stage):
        inp.add("CURVES", curve, "Storage" if k == 0 else "", h, a)
    x, y = e.footprint().centroid.x, e.footprint().centroid.y
    inp.add("COORDINATES", node, float(x), float(y))

    def target_node(t: str, link: str) -> str:
        for o in site.outfalls:
            if o.id == t:
                return f"{swmm_id(t)}__{link}"
        return f"ST_{swmm_id(t)}"

    cw = float(params.value("nbs.overflow_weir_coefficient"))
    if em.controlled_link:
        dst = target_node(e.outflow_to, em.controlled_link)
        if em.controlled_link.startswith("OW_"):
            inp.add("WEIRS", em.controlled_link, node, dst, "TRANSVERSE", e.pool_depth_m, cw, "NO", 0, 0, "YES",
                    comment="adjustable outlet weir at permanent pool level")
            inp.add("XSECTIONS", em.controlled_link, "RECT_OPEN", ymax - e.pool_depth_m + 1.0,
                    e.outlet_weir_length_m, 0, 0)
        else:
            offset = e.pool_depth_m
            inp.add("ORIFICES", em.controlled_link, node, dst, "SIDE", offset, e.outlet_coefficient or 0.65, "NO", 0,
                    comment="controlled release")
            inp.add("XSECTIONS", em.controlled_link, "CIRCULAR", e.outlet_diameter_m, 0, 0, 0)
    if em.overflow_link:
        dst = target_node(e.overflow_to, em.overflow_link)
        inp.add("WEIRS", em.overflow_link, node, dst, "TRANSVERSE", e.crest_depth_m, cw, "NO", 0, 0, "YES",
                comment="overflow spillway at crest")
        inp.add("XSECTIONS", em.overflow_link, "RECT_OPEN", ymax - e.crest_depth_m + 1.0, e.weir_length_m, 0, 0)


def _date_plus_days(days: int) -> str:
    from datetime import date, timedelta

    d = date(2000, 1, 1) + timedelta(days=days)
    return d.strftime("%m/%d/%Y")
