"""NbS element schema, parameter resolution and geometry.

Elements are stored in ``scenarios/<id>/elements.json`` as element records (the brief's
section 8.3 model, ``project.schema.ElementRecord``); :func:`to_record` and :func:`from_record`
convert losslessly between that record and :class:`NbSElement`, the engine's working form. Missing
design values are filled from project parameters (``nbs.<type>.<field>``) and every filled value is
recorded in ``param_sources`` so reports can show which values were defaults.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from ..project.parameters import ParameterSet
from .catalogue import LID_BIORETENTION, LID_SWALE, ComponentSpec, spec

log = logging.getLogger(__name__)


class ElementError(ValueError):
    pass


class NbSElement(BaseModel):
    """One NbS element. Lengths in m, areas in m2, volumes in m3, rates in mm/hr, times in hr."""

    id: str
    type: str
    geometry: Dict[str, Any]
    area_m2: Optional[float] = None
    max_ponding_depth_m: Optional[float] = None
    storage_volume_m3: Optional[float] = None
    infiltration_rate_mm_hr: Optional[float] = None
    soil_media_depth_m: Optional[float] = None
    drawdown_time_hr: Optional[float] = None
    contributing_area_m2: Optional[float] = None
    inflow_from: List[str] = Field(default_factory=list)  # subcatchment ids draining here
    outflow_to: Optional[str] = None  # element / outfall id (LID surface outflow, or controlled outlet)
    overflow_to: Optional[str] = None  # element / outfall id (storage overflow weir)
    locked: bool = False
    source: str = "proposal"  # "proposal" (generated) | "designer"
    results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)  # verified metrics per return period

    # design detail (filled from parameters when absent)
    invert_elev_m: Optional[float] = None
    side_slope_h_v: Optional[float] = None
    permanent_pool_depth_m: Optional[float] = None
    outlet_diameter_m: Optional[float] = None
    outlet_coefficient: Optional[float] = None
    outlet_weir_length_m: Optional[float] = None
    weir_length_m: Optional[float] = None
    seepage_rate_mm_hr: Optional[float] = None
    longitudinal_slope_pct: Optional[float] = None
    top_width_m: Optional[float] = None
    manning_n: Optional[float] = None
    vegetation_volume_fraction: Optional[float] = None
    storage_layer_depth_m: Optional[float] = None
    underdrain_coefficient: Optional[float] = None  # SWMM drain coefficient (mm/h per mm^0.5); None = no underdrain
    well_diameter_m: Optional[float] = None
    well_depth_m: Optional[float] = None
    dam_height_m: Optional[float] = None
    pool_area_m2: Optional[float] = None  # green bridge: water surface behind it at the crest (from the carved ground)
    freeboard_m: Optional[float] = None
    safety_bench_width_m: Optional[float] = None  # retention pond bench at the permanent pool edge
    # guideline-only attributes (optional, checked when given)
    check_dam_spacing_m: Optional[float] = None
    forebay_volume_fraction: Optional[float] = None
    cell_count: Optional[int] = None
    length_to_width: Optional[float] = None
    shallow_zone_depth_m: Optional[float] = None
    peak_velocity_m_s: Optional[float] = None
    contained_return_period_yr: Optional[float] = None
    hydraulic_retention_time_hr: Optional[float] = None
    native_ksat_m_s: Optional[float] = None

    soil_zone: Optional[str] = None
    # drawn as a curve (like a CAD spline): the points the designer placed; the geometry is the smooth
    # curve through them (open for a swale, closed for an outline). None = drawn with straight segments.
    fit_points: Optional[List[List[float]]] = None
    param_sources: Dict[str, str] = Field(default_factory=dict)
    # record fields this engine does not model, kept so a round trip loses nothing:
    # {"record": {...}, "parameters": {...}, "outlet": {...}}
    extra: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    notes: str = ""

    @property
    def spec(self) -> ComponentSpec:
        return spec(self.type)

    def footprint(self) -> BaseGeometry:
        """Plan footprint polygon (m)."""
        g = shape(self.geometry)
        if g.geom_type in ("Polygon", "MultiPolygon"):
            return g
        if g.geom_type == "LineString":
            if not self.top_width_m:
                raise ElementError(f"{self.id}: a centreline needs top_width_m.")
            return g.buffer(self.top_width_m / 2.0, cap_style=2)
        if g.geom_type == "Point":
            if not self.well_diameter_m:
                raise ElementError(f"{self.id}: a point element needs well_diameter_m.")
            return Point(g.x, g.y).buffer(self.well_diameter_m / 2.0, quad_segs=32)
        raise ElementError(f"{self.id}: unsupported geometry {g.geom_type}.")

    # ------------------------------------------------------------------ storage geometry
    @property
    def pool_depth_m(self) -> float:
        """Permanent pool depth (m); zero for elements without a permanent pool."""
        if self.type in ("retention_pond", "constructed_wetland"):
            return float(self.permanent_pool_depth_m or 0.0)
        return 0.0

    @property
    def crest_depth_m(self) -> float:
        """Depth from storage invert to the overflow crest, m."""
        if self.type == "recharge_well":
            return float(self.well_depth_m)
        if self.type in ("inline_check_dam", "green_bridge"):
            return float(self.dam_height_m)
        return self.pool_depth_m + float(self.max_ponding_depth_m or 0.0)

    def stage_area(self, n: int = 12) -> List[Tuple[float, float]]:
        """Stage-area curve [(depth m, area m2)] from invert to crest + freeboard.

        Banks are sloped at ``side_slope_h_v``; the footprint is the plan area at the
        crest. Above the crest the bank continues at the same slope.
        """
        fp = self.footprint()
        top = self.crest_depth_m
        ymax = top + (self.freeboard_m or 0.0)
        if self.type == "recharge_well":
            a = fp.area
            return [(0.0, a), (ymax, a)]
        if self.type == "green_bridge":   # backwater on a graded channel: the pool lengthens with depth
            a = max(float(self.pool_area_m2 if self.pool_area_m2 is not None else fp.area), 0.01)
            return [(float(h), max(a * min(h / top, 1.0), 0.01 * a)) for h in np.linspace(0.0, ymax, n)]
        z = float(self.side_slope_h_v or 0.0)
        out = []
        min_area = 0.01 * fp.area
        for h in np.linspace(0.0, ymax, n):
            d = z * (top - h)
            a = fp.buffer(-d).area if d != 0 else fp.area
            out.append((float(h), max(float(a), min_area)))
        if out[0][1] <= min_area * 1.0001:
            log.warning("%s: banks at %.1f:1 close before the invert; bottom area clipped to 1 %% of footprint", self.id, z)
        return out

    def volume_between(self, h0: float, h1: float) -> float:
        """Storage volume (m3) between depths h0 and h1 above invert (trapezoidal on the curve)."""
        curve = self.stage_area(n=60)
        hs = np.array([c[0] for c in curve])
        As = np.array([c[1] for c in curve])
        grid = np.linspace(h0, h1, 200)
        a = np.interp(grid, hs, As)
        return float(np.sum(0.5 * (a[1:] + a[:-1]) * np.diff(grid)))


# --------------------------------------------------------------------------- resolution
_PARAM_FIELDS = {
    # element field -> parameter suffix under nbs.<type>.
    "max_ponding_depth_m": "max_ponding_depth_m",
    "soil_media_depth_m": "soil_media_depth_m",
    "side_slope_h_v": "side_slope_h_v",
    "permanent_pool_depth_m": "permanent_pool_depth_m",
    "outlet_diameter_m": "outlet_diameter_m",
    "outlet_coefficient": "outlet_coefficient",
    "outlet_weir_length_m": "outlet_weir_length_m",
    "longitudinal_slope_pct": "longitudinal_slope_pct",
    "top_width_m": "top_width_m",
    "manning_n": "manning_n",
    "vegetation_volume_fraction": "vegetation_volume_fraction",
    "storage_layer_depth_m": "storage_layer_depth_m",
    "well_diameter_m": "diameter_m",
    "well_depth_m": "depth_m",
    "dam_height_m": "dam_height_m",
}


def _fill(el: NbSElement, field: str, params: ParameterSet, key: str) -> None:
    if getattr(el, field) is None and key in params:
        p = params.get(key)
        setattr(el, field, p.value)
        el.param_sources[field] = f"{p.source.value}{'' if p.confirmed else ' (unconfirmed)'}: {key}"


SoilLookup = Callable[[BaseGeometry], Tuple[Optional[str], Optional[float]]]


def resolve_element(el: NbSElement, params: ParameterSet, soil_lookup: Optional[SoilLookup] = None) -> NbSElement:
    """Fill missing design values from parameters and compute derived quantities.

    ``soil_lookup(footprint) -> (zone_id, native_rate_mm_hr)`` supplies the soil under the element.
    """
    el = el.model_copy(deep=True)
    sp = spec(el.type)
    gtype = el.geometry.get("type")
    if gtype not in sp.geometry:
        raise ElementError(f"{el.id}: {sp.label} geometry must be one of {sp.geometry}, got {gtype}.")
    for field, suffix in _PARAM_FIELDS.items():
        _fill(el, field, params, f"nbs.{el.type}.{suffix}")
    if el.weir_length_m is None:
        _fill(el, "weir_length_m", params, "nbs.overflow_weir_length_m")
        if el.type == "inline_check_dam":
            _fill(el, "weir_length_m", params, "nbs.inline_check_dam.notch_width_m")
    if sp.is_storage and el.freeboard_m is None:
        _fill(el, "freeboard_m", params, "nbs.storage_freeboard_m")

    native_rate_mm_hr: Optional[float] = None
    if soil_lookup is not None:
        zone, native_rate_mm_hr = soil_lookup(el.footprint())
        if el.soil_zone is None:
            el.soil_zone = zone
    # infiltration: native soil unless the element states its own (recharge well: strata rate)
    if el.infiltration_rate_mm_hr is None:
        if el.type == "recharge_well":
            raise ElementError(
                f"{el.id}: recharge wells need infiltration_rate_mm_hr of the permeable strata "
                "(from borehole or percolation test data). It is not defaulted."
            )
        if native_rate_mm_hr is None:
            raise ElementError(f"{el.id}: no soil zone covers this element and no infiltration rate is given.")
        el.infiltration_rate_mm_hr = native_rate_mm_hr
        el.param_sources["infiltration_rate_mm_hr"] = f"soil zone {el.soil_zone}"

    if sp.is_storage and el.seepage_rate_mm_hr is None:
        if el.type == "recharge_well":
            el.seepage_rate_mm_hr = el.infiltration_rate_mm_hr
        else:
            key = f"nbs.{el.type}.seepage_fraction"
            frac = params.value_or(key, 1.0)
            el.seepage_rate_mm_hr = float(el.infiltration_rate_mm_hr) * float(frac)
            el.param_sources["seepage_rate_mm_hr"] = f"native rate x {key} = {frac}"

    if sp.is_storage and el.invert_elev_m is None:
        raise ElementError(f"{el.id}: storage elements need invert_elev_m (Phase 1 has no terrain to derive it).")

    fp = el.footprint()
    el.area_m2 = float(fp.area)
    el.storage_volume_m3 = storage_volume(el, params)
    el.drawdown_time_hr = analytic_drawdown_hr(el, params)
    return el


def storage_volume(el: NbSElement, params: ParameterSet) -> float:
    """Design storage volume, m3.

    LIDs: surface ponding (net of vegetation) plus media void storage.
    Storage elements: live volume between the permanent pool and the overflow crest.
    """
    sp = el.spec
    A = float(el.area_m2 or el.footprint().area)
    if sp.swmm == LID_BIORETENTION:
        veg = el.vegetation_volume_fraction or 0.0
        por = params.value_or(f"nbs.{el.type}.media_porosity", 0.45)
        fc = params.value_or(f"nbs.{el.type}.media_field_capacity", 0.2)
        void = params.value_or(f"nbs.{el.type}.storage_layer_void_ratio", 0.4)
        return A * (
            el.max_ponding_depth_m * (1 - veg)
            + (el.soil_media_depth_m or 0.0) * (por - fc)
            + (el.storage_layer_depth_m or 0.0) * void
        )
    if sp.swmm == LID_SWALE:
        W = el.top_width_m or 1.0
        d = el.max_ponding_depth_m
        z = el.side_slope_h_v or 0.0
        cross = d * max(W - z * d, 0.0)
        return (A / W) * cross * (1 - (el.vegetation_volume_fraction or 0.0))
    return el.volume_between(el.pool_depth_m, el.crest_depth_m)


def analytic_drawdown_hr(el: NbSElement, params: ParameterSet) -> Optional[float]:
    """Simple design drawdown estimate (hr); the SWMM-simulated drawdown is reported separately."""
    sp = el.spec
    if sp.swmm == LID_BIORETENTION:
        media = params.value_or(f"nbs.{el.type}.media_ksat_mm_hr", None)
        rate = min(el.infiltration_rate_mm_hr, media) if media else el.infiltration_rate_mm_hr
        if el.underdrain_coefficient and media:
            rate = media   # with an underdrain the surface drains through the media, whatever the soil below
        return el.max_ponding_depth_m * 1000.0 / rate if rate > 0 else None
    if sp.swmm == LID_SWALE:
        r = el.infiltration_rate_mm_hr
        return el.max_ponding_depth_m * 1000.0 / r if r > 0 else None
    live = el.crest_depth_m - el.pool_depth_m
    r = el.seepage_rate_mm_hr or 0.0
    if el.type in ("detention_pond", "constructed_wetland") or (el.type == "retention_pond" and el.outlet_diameter_m):
        return None  # outlet-controlled: use the simulated drawdown
    return live * 1000.0 / r if r > 0 else None


# --------------------------------------------------------------------------- element records (brief 8.3)
# NbSElement field -> ElementRecord.parameters field (same name unless listed)
_RENAMED = {"top_width_m": "width_m", "max_ponding_depth_m": "depth_m", "well_diameter_m": "diameter_m",
            "weir_length_m": "overflow_weir_length_m"}
_PARAMS = ["top_width_m", "max_ponding_depth_m", "side_slope_h_v", "soil_media_depth_m", "storage_layer_depth_m",
           "underdrain_coefficient",
           "permanent_pool_depth_m", "freeboard_m", "safety_bench_width_m", "invert_elev_m", "longitudinal_slope_pct", "manning_n",
           "vegetation_volume_fraction", "check_dam_spacing_m", "dam_height_m", "pool_area_m2", "well_diameter_m", "well_depth_m",
           "seepage_rate_mm_hr", "weir_length_m",
           # guideline-only attributes travel as extra parameters
           "forebay_volume_fraction", "cell_count", "length_to_width", "shallow_zone_depth_m", "peak_velocity_m_s",
           "contained_return_period_yr", "hydraulic_retention_time_hr", "native_ksat_m_s"]
_TOP = ["infiltration_rate_mm_hr", "area_m2", "storage_volume_m3", "contributing_area_m2", "drawdown_time_hr",
        "soil_zone", "fit_points", "param_sources", "notes", "results"]


_RECORD_KEYS = {"id", "type", "geometry", "parameters", "connections", "locked", "source", *_TOP}


def to_record(el: NbSElement) -> Dict[str, Any]:
    """Element record (an entry of ``scenarios/<id>/elements.json``) from an engine element."""
    params: Dict[str, Any] = {}
    for f in _PARAMS:
        v = getattr(el, f)
        if v is not None:
            params[_RENAMED.get(f, f)] = v
    kept_outlet = el.extra.get("outlet", {})
    if el.outlet_diameter_m is not None or el.outlet_weir_length_m is not None or el.outlet_coefficient is not None \
            or kept_outlet:
        params["outlet"] = {**kept_outlet, **{k: v for k, v in {
            "type": kept_outlet.get("type") or ("orifice" if el.outlet_diameter_m is not None else "weir"),
            "diameter_m": el.outlet_diameter_m, "weir_length_m": el.outlet_weir_length_m,
            "coefficient": el.outlet_coefficient}.items() if v is not None}}
    params.update(el.extra.get("parameters", {}))
    rec: Dict[str, Any] = {"id": el.id, "type": el.type, "geometry": el.geometry, "parameters": params,
                           "connections": {"inflow_from": list(el.inflow_from), "outflow_to": el.outflow_to,
                                           "overflow_to": el.overflow_to},
                           "locked": bool(el.locked),
                           "source": "designer" if el.source == "designer" else "proposal"}
    for f in _TOP:
        v = getattr(el, f)
        if v is not None and v != {} and v != "":
            rec[f] = v
    for k, v in el.extra.get("record", {}).items():
        rec.setdefault(k, v)
    return rec


def from_record(rec: Dict[str, Any]) -> NbSElement:
    """Engine element from an element record."""
    inv = {v: k for k, v in _RENAMED.items()}
    params = dict(rec.get("parameters") or {})
    outlet = params.pop("outlet", None) or {}
    d: Dict[str, Any] = {"id": rec["id"], "type": rec["type"], "geometry": rec["geometry"],
                         "locked": bool(rec.get("locked", False)),
                         "source": "designer" if rec.get("source") == "designer" else "proposal"}
    extra: Dict[str, Dict[str, Any]] = {}
    known = set(NbSElement.model_fields)
    for k, v in params.items():
        f = inv.get(k, k)
        if f in _PARAMS and f in known:
            d[f] = v
        else:
            extra.setdefault("parameters", {})[k] = v
    if outlet:
        d["outlet_diameter_m"] = outlet.get("diameter_m")
        d["outlet_weir_length_m"] = outlet.get("weir_length_m")
        d["outlet_coefficient"] = outlet.get("coefficient")
        rest = {k: v for k, v in outlet.items() if k not in ("diameter_m", "weir_length_m", "coefficient")}
        if rest:
            extra["outlet"] = rest
    conn = rec.get("connections") or {}
    d["inflow_from"] = list(conn.get("inflow_from") or [])
    d["outflow_to"] = conn.get("outflow_to")
    d["overflow_to"] = conn.get("overflow_to")
    for f in _TOP:
        if f in rec:
            d[f] = rec[f]
    rest = {k: v for k, v in rec.items() if k not in _RECORD_KEYS}
    if rest:
        extra["record"] = rest
    d["extra"] = extra
    return NbSElement.model_validate({k: v for k, v in d.items() if v is not None})


def elements_rel(scenario_id: str) -> str:
    return f"scenarios/{scenario_id}/elements.json"


def has_elements(project, scenario_id: str) -> bool:
    return project.exists(elements_rel(scenario_id))


def load_elements(project, scenario_id: str) -> List[NbSElement]:
    """Elements of a scenario (empty when it has none)."""
    if not has_elements(project, scenario_id):
        return []
    return read_elements(project.read_json(elements_rel(scenario_id)))


def save_elements(project, scenario_id: str, elements: List[NbSElement]) -> None:
    """Write ``scenarios/<id>/elements.json`` (and a scenario.json the first time)."""
    project.write_json(elements_rel(scenario_id), write_elements(elements))
    sc = f"scenarios/{scenario_id}/scenario.json"
    if not project.exists(sc):
        from ..project.schema import Scenario

        status = "proposal" if elements and all(e.source != "designer" for e in elements) else "draft"
        project.write_json(sc, Scenario(id=scenario_id, name=scenario_id, status=status).model_dump(mode="json"))


def elements_fc(project, scenario_id: str) -> Dict[str, Any]:
    """The scenario's elements as a GeoJSON FeatureCollection (API, viewers, Grasshopper)."""
    return to_feature_collection(load_elements(project, scenario_id))


def save_elements_fc(project, scenario_id: str, fc: Dict[str, Any]) -> None:
    save_elements(project, scenario_id, read_elements(fc))


def to_feature_collection(elements: List[NbSElement]) -> Dict[str, Any]:
    feats = []
    for el in elements:
        props = el.model_dump(mode="json", exclude={"geometry"} | ({"extra"} if not el.extra else set()), exclude_none=True)
        feats.append({"type": "Feature", "geometry": el.geometry, "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def read_elements(data: Any) -> List[NbSElement]:
    """Elements from an elements.json document, a list of records, or a GeoJSON FeatureCollection."""
    if isinstance(data, dict) and "elements" in data:
        data = data["elements"]
    if isinstance(data, list):
        out, ids = [], set()
        for i, rec in enumerate(data):
            if "id" not in rec:
                raise ElementError(f"element {i} has no 'id'.")
            if rec["id"] in ids:
                raise ElementError(f"duplicate element id '{rec['id']}'.")
            ids.add(rec["id"])
            out.append(from_record(rec))
        return out
    fc = data
    out = []
    ids = set()
    for i, f in enumerate(fc.get("features", [])):
        props = dict(f.get("properties") or {})
        if "id" not in props:
            raise ElementError(f"feature {i} has no 'id'.")
        if props["id"] in ids:
            raise ElementError(f"duplicate element id '{props['id']}'.")
        ids.add(props["id"])
        props["geometry"] = f["geometry"]
        if props.get("source") == "generated":  # name used before schema 1.1
            props["source"] = "proposal"
        out.append(NbSElement.model_validate(props))
    return out


def write_elements(elements: List[NbSElement]) -> Dict[str, Any]:
    """The elements.json document for ``elements``."""
    from ..project.schema import SCHEMA_VERSION

    return {"schema_version": SCHEMA_VERSION, "elements": [to_record(e) for e in elements]}


def to_geojson_geometry(g: BaseGeometry) -> Dict[str, Any]:
    return dict(mapping(g))
