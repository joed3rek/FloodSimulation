"""Generate an NbS layout from the terrain (Phase 4).

1. **Suitability.** Hard constraints (outside the site, boundary setback, buildings, mapped paths,
   roads, walls, drains and water, tree root zones, ground too steep) and a weighted score of water
   reaching the cell, low ground, existing depressions and gentle slope.
2. **Placement and sizing.** Element types are placed in order (``layout.types``). Each new element
   seeds at the best-scoring free cell that still receives enough *uncaptured* water, and grows over
   low, nearby ground until it holds the design-storm runoff of its drainage area
   (runoff depth from the baseline SWMM run x drainage area), or reaches its size limit or the area
   budget. Water reaching an element is then counted as captured.
3. **Grading.** Each element is cut below its rim (``grading.grade``).
4. **Subcatchment rebuild.** Flow is traced again on the graded ground with the elements as sinks:
   each element gets the subcatchment that really drains into it, and the rest keep their outfalls.
5. **Outputs** under ``scenarios/<id>/``: ``elements.json`` (generated + kept designer elements),
   ``site/subcatchments.geojson`` (used by this option's SWMM runs), ``terrain/graded.tif``,
   ``terrain/cut.tif``, ``terrain/suitability_<type>.tif``, ``design_contours.geojson``,
   ``design.dxf`` (SP-DSN-* layers in survey coordinates), ``layout.png`` and ``layout_report.json``.

Every threshold and weight is a project parameter (``layout.*``, ``nbs.<type>.*``) flagged unconfirmed
until the designer confirms it.
"""

from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from shapely import contains_xy
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from ..grading.grade import Cut, flat_volume, grade
from ..hydrology import flow as fl
from ..hydrology.delineate import _polygons, context_surfaces
from ..nbs.components import NbSElement, has_elements, load_elements, save_elements
from ..project import Project, Source
from ..site.model import Site, SiteError
from ..terrain.raster import DEM, read_geotiff, write_geotiff

log = logging.getLogger(__name__)

PREFIX = {"rain_garden": "RG", "bioswale": "BS", "detention_pond": "DP", "retention_pond": "RP", "recharge_well": "RW"}
SUPPORTED = tuple(PREFIX)


class LayoutError(ValueError):
    pass


@dataclass
class Placed:
    id: str
    type: str
    region: np.ndarray
    seed: Tuple[int, int]
    drainage_m2: float  # uncaptured drainage area at placement
    target_m3: float
    estimate_m3: float
    limited_by: str
    cut: Optional[Cut] = None
    outflow_to: str = ""
    overflow_to: str = ""
    end: Optional[Tuple[int, int]] = None  # downstream end (swales)
    notes: List[Any] = field(default_factory=list)


# ------------------------------------------------------------------ terrain and constraints
@dataclass
class Grid:
    dem: DEM
    X: np.ndarray
    Y: np.ndarray
    mask: np.ndarray
    z: np.ndarray
    filled: np.ndarray
    dirs: np.ndarray
    depth: np.ndarray
    slope: np.ndarray
    domain: Any

    @property
    def cell(self) -> float:
        return self.dem.cell_size


def load_grid(project: Project) -> Grid:
    dem = read_geotiff(project.path("terrain/existing.tif"), crs_fallback=project.manifest.crs)
    if not project.exists("site/boundary.geojson"):
        raise LayoutError("no site boundary; run `terrain delineate` first.")
    domain = unary_union([shape(f["geometry"]) for f in project.read_geojson("site/boundary.geojson")["features"]])
    X, Y = dem.cell_centres()
    mask = (dem.z != dem.nodata) & contains_xy(domain, X, Y)
    z = np.where(mask, dem.z, np.nan)
    filled = fl.fill_sinks(z, mask)
    dirs = fl.d8_directions(filled, mask)
    gy, gx = np.gradient(np.where(mask, dem.z, np.nan), dem.cell_size)
    slope = 100 * np.hypot(gx, gy)
    return Grid(dem, X, Y, mask, z, filled, dirs, np.where(mask, filled - z, 0.0), slope, domain)


def keep_out(project: Project, g: Grid) -> Tuple[np.ndarray, Dict[str, int]]:
    """Cells where no element may go, and how many cells each constraint removes."""
    out, counts, _ = _keep_out(project, g)
    return out, counts


def crossable(project: Project, g: Grid) -> np.ndarray:
    """Keep-out cells that are only footpath: a bioswale may cross them through a trench drain."""
    _, _, path_only = _keep_out(project, g)
    return path_only


def _keep_out(project: Project, g: Grid) -> Tuple[np.ndarray, Dict[str, int], np.ndarray]:
    P = project.parameters
    setback = float(P.value("layout.boundary_setback_m"))
    line_buf = float(P.value("layout.line_feature_buffer_m"))
    bldg = float(P.value("layout.building_setback_m"))
    tree_r = float(P.value("layout.tree_protection_radius_m"))
    buf = {"paths": float(P.value_or("layout.path_buffer_m", line_buf)),
           "walls": float(P.value_or("layout.wall_buffer_m", line_buf))}
    avoid = set(P.value("layout.avoid_context_kinds"))
    area = float(g.mask.sum() * g.cell ** 2)
    _, enclosing, _ = context_surfaces(project, g.domain, area, set())
    enclosing_layers = {e["layer"] for e in enclosing}

    shapes: Dict[str, List[Any]] = {"boundary setback": [g.domain.boundary.buffer(setback)]}
    ctx = project.read_geojson("site/context.geojson")["features"] if project.exists("site/context.geojson") else []
    for f in ctx:
        kind = f["properties"].get("kind", "")
        geom = shape(f["geometry"])
        if kind in ("tree", "tree_unsized"):
            r = max(tree_r, float(f["properties"].get("canopy_radius_m") or 0.0))
            shapes.setdefault("tree root zones", []).append(Point(geom.x, geom.y).buffer(r))
            continue
        if kind not in avoid:
            continue
        if geom.geom_type == "Polygon":
            if kind == "buildings":
                geom = geom.buffer(bldg)
            elif kind != "water" or (f["properties"].get("layer") in enclosing_layers and geom.area >= 0.9 * area):
                # surveyors draw paths, walls and roads as closed loops around lawns: keep off the line only
                geom = geom.exterior.buffer(buf.get(kind, line_buf))
        else:
            geom = geom.buffer(bldg if kind == "buildings" else buf.get(kind, line_buf))
        shapes.setdefault(kind, []).append(geom)
    out = np.zeros(g.mask.shape, bool)
    counts: Dict[str, int] = {}
    masks: Dict[str, np.ndarray] = {}
    for name, gs in shapes.items():
        m = contains_xy(unary_union(gs), g.X, g.Y) & g.mask
        masks[name] = m
        counts[name] = int((m & ~out).sum())
        out |= m
    path_only = masks.get("paths", np.zeros(g.mask.shape, bool)).copy()
    for name, m in masks.items():
        if name != "paths":
            path_only &= ~m
    return out, counts, path_only


def _norm(a: np.ndarray, m: np.ndarray) -> np.ndarray:
    v = a[m]
    if v.size == 0 or np.ptp(v) == 0:
        return np.where(m, 0.5, np.nan)
    return np.where(m, (a - v.min()) / np.ptp(v), np.nan)


def suitability(project: Project, g: Grid, allowed: np.ndarray, wacc: np.ndarray) -> np.ndarray:
    """Score 0-1 on allowed cells (NaN elsewhere)."""
    P = project.parameters
    w = {k: float(P.value(f"layout.weight.{k}")) for k in ("accumulation", "low_ground", "depression", "gentle_slope")}
    total = sum(w.values()) or 1.0
    s_acc = _norm(np.log1p(wacc), allowed)
    s_low = 1 - _norm(g.z, allowed)
    s_dep = _norm(np.minimum(g.depth, 0.3), allowed)
    s_slope = 1 - _norm(np.nan_to_num(g.slope), allowed)
    s = (w["accumulation"] * s_acc + w["low_ground"] * s_low + w["depression"] * s_dep
         + w["gentle_slope"] * s_slope) / total
    return np.where(allowed, s, np.nan)


# ------------------------------------------------------------------ sizing helpers
def storage_per_m2(P, t: str) -> Optional[float]:
    """Storage per m2 of footprint for LID types (m3/m2); None for storage types (depends on shape)."""
    if t != "rain_garden":
        return None
    v = lambda k, d=0.0: float(P.value_or(f"nbs.{t}.{k}", d) or 0.0)  # noqa: E731
    return (v("max_ponding_depth_m") * (1 - v("vegetation_volume_fraction"))
            + v("soil_media_depth_m") * (v("media_porosity", 0.45) - v("media_field_capacity", 0.2))
            + v("storage_layer_depth_m") * v("storage_layer_void_ratio", 0.4))


def surface_depth(P, t: str) -> float:
    return float(P.value(f"nbs.{t}.max_ponding_depth_m")) + float(P.value_or(f"nbs.{t}.permanent_pool_depth_m", 0.0) or 0.0)


def runoff_depth_mm(project: Project) -> Tuple[float, int, str]:
    """Design-storm runoff depth over the site from the baseline SWMM run."""
    rp = int(project.parameters.value("layout.design_return_period_yr"))
    rel = "scenarios/baseline/results/summary.json"
    if not project.exists(rel):
        raise LayoutError("run the baseline first (`option run PATH baseline`): sizing uses its SWMM runoff.")
    r = project.read_json(rel)["return_periods"].get(str(rp))
    if r is None:
        raise LayoutError(f"the baseline has no {rp}-yr run; add it to project.return_periods and rerun.")
    wb = r["water_balance"]
    c = (wb["outflow_total_m3"] + wb["flooding_m3"]) / wb["rainfall_total_m3"]
    return c * float(r["storm"]["depth_mm"]), rp, f"baseline SWMM {rp}-yr: runoff coefficient {c:.2f} x {r['storm']['depth_mm']:.0f} mm"


def _grow(g: Grid, seed: Tuple[int, int], free: np.ndarray, climb: float, done) -> np.ndarray:
    """Grow a 4-connected footprint from ``seed`` over ``free`` cells, nearest and lowest first,
    until ``done(region, n_cells)`` is true or nothing is left."""
    region = np.zeros(free.shape, bool)
    r0, c0 = seed
    z0 = g.z[r0, c0]
    heap = [(0.0, r0, c0)]
    seen = {seed}
    n = 0
    while heap:
        _, r, c = heapq.heappop(heap)
        region[r, c] = True
        n += 1
        if done(region, n):
            break
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < free.shape[0] and 0 <= cc < free.shape[1] and free[rr, cc] and (rr, cc) not in seen:
                seen.add((rr, cc))
                d = np.hypot(rr - r0, cc - c0) * g.cell
                heapq.heappush(heap, (d + climb * (g.z[rr, cc] - z0), rr, cc))
    return region


# ------------------------------------------------------------------ main
def generate(project: Project, option_id: str, types: Optional[List[str]] = None,
             overrides: Optional[Dict[str, Any]] = None, write_outputs: bool = True) -> Dict[str, Any]:
    """Generate, grade and rebuild a layout for ``option_id``.

    ``overrides``: parameter values used for this call only (the optimiser varies budgets and depths
    this way); they are recorded in the report, not stored in the project."""
    saved = project.parameters
    if overrides:
        project.parameters = saved.model_copy(deep=True)
        for k, v in overrides.items():
            project.parameters.set(k, v, source=Source.USER, note="optimiser / call override")
    try:
        rep = _generate(project, option_id, types, write_outputs)
        rep["overrides"] = dict(overrides or {})
        if write_outputs and overrides:
            _record_sizes(project, option_id)   # the elements say the sizes they were built with
        if write_outputs:
            project.write_json(f"scenarios/{option_id}/layout_report.json", rep)
        return rep
    finally:
        project.parameters = saved


# element field -> parameter key suffix (nbs.<type>.<suffix>) for sizes a layout is built with
_SIZE_FIELDS = {"max_ponding_depth_m": "max_ponding_depth_m", "permanent_pool_depth_m": "permanent_pool_depth_m",
                "side_slope_h_v": "side_slope_h_v", "soil_media_depth_m": "soil_media_depth_m",
                "top_width_m": "top_width_m"}


def _record_sizes(project: Project, option_id: str) -> None:
    """Write the sizes in force while the layout was built (optimiser overrides included) onto its elements,
    so the elements stay true to the graded ground when they are re-resolved or edited later."""
    from ..nbs.components import has_elements, load_elements, save_elements

    if not has_elements(project, option_id):
        return
    P = project.parameters
    els = load_elements(project, option_id)
    for e in els:
        for field, suffix in _SIZE_FIELDS.items():
            v = P.value_or(f"nbs.{e.type}.{suffix}", None)
            if isinstance(v, (int, float)) and hasattr(e, field):
                setattr(e, field, float(v))
    save_elements(project, option_id, els)


def _generate(project: Project, option_id: str, types: Optional[List[str]], write_outputs: bool) -> Dict[str, Any]:
    from scipy import ndimage

    P = project.parameters
    types = list(types or P.value("layout.types"))
    bad = [t for t in types if t not in SUPPORTED]
    if bad:
        raise LayoutError(f"cannot place {bad} automatically; supported: {', '.join(SUPPORTED)}.")
    g = load_grid(project)
    cell, cell2 = g.cell, g.cell ** 2
    runoff_mm, rp, runoff_src = runoff_depth_mm(project)
    site_area = float(g.mask.sum() * cell2)
    site = Site.load(project)
    method = str(P.value("swmm.infiltration_method")).upper()
    max_dd = float(P.value("nbs.max_drawdown_hr"))

    # designer elements in the option are kept as they are
    kept: List[NbSElement] = []
    if has_elements(project, option_id):
        locked = set(project.locked_ids(option_id))
        kept = [e for e in load_elements(project, option_id) if e.source == "designer" or e.locked or e.id in locked]
    taken = np.zeros(g.mask.shape, bool)
    element_cells = np.zeros(g.mask.shape, bool)
    kept_cells: Dict[str, np.ndarray] = {}
    for e in kept:
        m = contains_xy(e.footprint(), g.X, g.Y) & g.mask
        kept_cells[e.id] = m
        element_cells |= m
        taken |= m
    kept_area = sum(float(e.footprint().area) for e in kept)

    blocked, blocked_counts = keep_out(project, g)
    spacing = float(P.value("layout.element_spacing_m"))
    climb = float(P.value("layout.growth_climb_weight"))
    state = {"budget": float(P.value("layout.max_area_pct")) / 100 * site_area - kept_area}
    budget_start = state["budget"]
    sub_lab, sub_props = _subcatchment_raster(project, g)
    skipped: List[str] = []

    placed: List[Placed] = []
    rejected = np.zeros(g.mask.shape, bool)

    storage_cells = np.zeros(g.mask.shape, bool)

    def wacc_now(conveying: bool = False):
        """(captured cells, uncaptured accumulation m2). Swales convey towards storage, so for them
        water already bound for a pond still counts."""
        cells = element_cells & ~storage_cells if conveying else element_cells
        captured = fl.reaches(g.filled, g.mask, g.dirs, cells) if cells.any() else np.zeros_like(g.mask)
        return captured, fl.accumulation(g.filled, g.mask, g.dirs, weight=(~captured).astype(float)) * cell2

    def accept(p: Placed) -> None:
        placed.append(p)
        element_cells[p.region] = True
        if p.type in STORAGE_TYPES:
            storage_cells[p.region] = True
        taken[ndimage.distance_transform_edt(~p.region) * cell <= spacing] = True
        state["budget"] -= float(p.region.sum() * cell2)

    def native_rate(r: int, c: int) -> float:
        z, _ = site.dominant_soil(Point(g.X[r, c], g.Y[r, c]).buffer(cell))
        if z is None:
            raise LayoutError("no soil zone covers the site.")
        try:
            return float(z.native_rate(method))
        except SiteError as ex:
            raise LayoutError(f"{ex} Layout sizing needs it to check drawdown.") from ex

    # rain gardens on slow native soil get a stone layer and an underdrain (HC 4.2), if allowed
    ud_ok = bool(P.value_or("nbs.rain_garden.underdrain_on_slow_soil", True))
    ud_below = float(P.value_or("nbs.underdrain_below_native_mm_hr", 13.0))
    ud_depth = float(P.value_or("nbs.rain_garden.underdrain_storage_depth_m", 0.6))
    ud_void = float(P.value_or("nbs.rain_garden.storage_layer_void_ratio", 0.4))

    for t in types:
        if t == "bioswale":
            _place_swales(project, g, blocked, taken, rejected, wacc_now, accept, lambda: state["budget"], runoff_mm,
                          native_rate, max_dd, skipped)
            continue
        if t == "recharge_well":
            _place_wells(project, g, blocked, placed, accept, skipped)
            continue
        max_slope = float(P.value(f"nbs.{t}.max_ground_slope_pct"))
        min_contrib = float(P.value(f"nbs.{t}.min_contributing_area_m2"))
        a_min, a_max = float(P.value(f"nbs.{t}.min_area_m2")), float(P.value(f"nbs.{t}.max_area_m2"))
        depth = surface_depth(P, t)
        live = float(P.value(f"nbs.{t}.max_ponding_depth_m"))
        side = P.value_or(f"nbs.{t}.side_slope_h_v", None)
        k_lid = storage_per_m2(P, t)
        allowed_t = g.mask & ~blocked & (np.nan_to_num(g.slope, nan=1e9) <= max_slope)
        k = 0
        n_dd = 0
        n_ud = 0
        for _ in range(500):
            if state["budget"] < a_min:
                break
            captured, wacc = wacc_now()
            free = allowed_t & ~taken & ~rejected
            cand = free & (wacc >= min_contrib)
            if not cand.any():
                break
            score = suitability(project, g, free, wacc)
            r, c = np.unravel_index(int(np.nanargmax(np.where(cand, score, np.nan))), score.shape)
            # drawdown: elements emptied only by infiltration must empty within the limit
            # (ponds with an outlet are checked on the SWMM drawdown)
            seep = 1.0 if t == "rain_garden" else float(P.value_or(f"nbs.{t}.seepage_fraction", 1.0) or 0.0)
            infiltration_only = t == "rain_garden" or (t == "detention_pond" and not P.value_or(f"nbs.{t}.outlet_diameter_m", None))
            underdrain = False
            if infiltration_only and seep > 0:
                native = native_rate(r, c)
                rate = native * seep
                if t == "rain_garden":
                    media = P.value_or("nbs.rain_garden.media_ksat_mm_hr", None)
                    rate = min(rate, media) if media else rate
                dd = live * 1000 / rate if rate > 0 else float("inf")
                if t == "rain_garden" and ud_ok and (native < ud_below or dd > max_dd):
                    underdrain = True   # drains through the media into the gravel and the underdrain
                    n_ud += 1
                elif dd > max_dd:
                    rejected |= cand & (np.hypot(g.X - g.X[r, c], g.Y - g.Y[r, c]) <= 5 * cell)
                    n_dd += 1
                    if n_dd >= 3:  # the same soil everywhere: stop trying
                        skipped.append(f"{t}: drawdown {dd:.0f} h at {rate:g} mm/h exceeds nbs.max_drawdown_hr "
                                       f"= {max_dd:g} h; needs >= {live * 1000 / max_dd:.1f} mm/h, a shallower "
                                       "ponding depth or an underdrain.")
                        break
                    continue
            contrib = float(wacc[r, c])
            cap = min(a_max, state["budget"])
            k_el = (k_lid + ud_depth * ud_void) if underdrain and k_lid is not None else k_lid
            for _ in range(4):  # the footprint catches more than its seed: resize to what reaches it
                target = runoff_mm / 1000 * contrib
                if k_el is not None:
                    need_cells = int(np.ceil(min(max(target / k_el, a_min), cap) / cell2))
                    done = lambda reg, n, _n=need_cells: n >= _n  # noqa: E731
                else:
                    def done(reg, n, _cap=cap, _t=target):
                        return n * cell2 >= _cap or (n % 8 == 0 and flat_volume(reg, cell, depth, side) >= _t)
                region = _grow(g, (r, c), free, climb, done)
                a = float(region.sum() * cell2)
                est = a * k_el if k_el is not None else flat_volume(region, cell, depth, side)
                reach = float((fl.reaches(g.filled, g.mask, g.dirs, region) & ~captured).sum() * cell2)
                if reach <= contrib * 1.02 or a >= cap - cell2:
                    contrib = max(contrib, reach)
                    target = runoff_mm / 1000 * contrib
                    break
                contrib = reach
            if a < a_min or est <= 0:
                rejected |= region
                continue
            limited = ("design storm" if est >= target * 0.98 else
                       "area budget" if a >= state["budget"] - cell2 else
                       "size limit" if a >= a_max - cell2 else "space")
            k += 1
            p_new = Placed(f"{PREFIX[t]}_{k}", t, region, (int(r), int(c)), contrib, target, est, limited)
            if underdrain:
                p_new.notes.append({"underdrain": True, "native_rate_mm_hr": native})
            accept(p_new)
        if n_ud:
            skipped.append(f"{t}: the native soil drains slower than {ud_below:g} mm/h, so rain gardens have a "
                           f"{ud_depth:g} m stone layer and a perforated underdrain (HC 4.2); a percolation test "
                           "may show they need none.")

    if not placed and not kept:
        raise LayoutError(_nothing_fits(blocked_counts, skipped, cell2))

    # grading, in placement order; designer elements and keep-out areas are never altered
    zg = np.where(g.mask, g.dem.z, np.nan)
    protect = blocked.copy()
    for m in kept_cells.values():
        protect |= m
    for p in placed:
        if p.type == "bioswale":
            zg, p.cut = _grade_swale(zg, g, p, P, protect)
        elif p.type == "recharge_well":
            z0 = float(zg[p.seed])
            p.cut = Cut(z0, z0 - float(P.value("nbs.recharge_well.depth_m")), 0.0, p.estimate_m3,
                        float(p.region.sum() * cell2))
        else:
            side = P.value_or(f"nbs.{p.type}.side_slope_h_v", None) if p.type != "rain_garden" else None
            zg, p.cut = grade(zg, p.region & ~protect, g.mask, cell, surface_depth(P, p.type), side)

    _route(placed, g, sub_lab, sub_props)
    elements = list(kept)
    for p in placed:
        elements.append(NbSElement.model_validate(_element_props(p, P, g, rp, runoff_mm)))

    # subcatchment rebuild on the graded ground
    sinks = np.zeros(g.mask.shape, bool)
    sink_owner = np.zeros(g.mask.shape, object)
    regions = {p.id: p.region for p in placed}
    regions.update(kept_cells)
    for e in elements:
        m = regions[e.id]
        sinks |= m
        sink_owner[m] = e.id
    from .apply import _existing_well_sinks

    _existing_well_sinks(project, g, sinks, sink_owner)
    subs, sub_rows = _rebuild(project, g, zg, sinks, sink_owner, sub_lab, sub_props)
    for e in elements:
        sc = f"SC_{e.id}"
        e.inflow_from = [sc] if any(s["properties"]["id"] == sc for s in subs) else []

    cut_cells = np.where(g.mask, g.dem.z - zg, 0.0)
    cut_total = float(cut_cells[cut_cells > 0].sum() * cell2)
    gen_area = float(sum(p.region.sum() * cell2 for p in placed))
    report = {
        "option_id": option_id,
        "design_storm": {"return_period_yr": rp, "runoff_depth_mm": runoff_mm, "source": runoff_src},
        "site_area_m2": site_area,
        "area_budget_m2": budget_start + kept_area,
        "generated_area_m2": gen_area,
        "intervention_area_pct": 100 * (gen_area + kept_area) / site_area,
        "kept_designer_elements": [e.id for e in kept],
        "keep_out_cells_removed": {k: v * cell2 for k, v in blocked_counts.items()},
        "skipped": skipped,
        "elements": [{"id": p.id, "type": p.type, "area_m2": float(p.region.sum() * cell2),
                      "drainage_at_placement_m2": p.drainage_m2,
                      "drains_here_after_grading_m2": next((r["area_m2"] for r in sub_rows if r["id"] == f"SC_{p.id}"), 0.0),
                      "target_m3": p.target_m3, "holds_m3_estimate": p.estimate_m3,
                      "surface_storage_below_rim_m3": p.cut.storage_m3, "limited_by": p.limited_by,
                      "rim_m": p.cut.rim_m, "bottom_m": p.cut.bottom_m, "cut_m3": p.cut.cut_m3,
                      "outflow_to": p.outflow_to, "overflow_to": p.overflow_to or p.outflow_to} for p in placed],
        "earthworks": {"cut_m3": cut_total, "fill_m3": 0.0, "net_export_m3": cut_total,
                       "by_element_m3": {p.id: p.cut.cut_m3 for p in placed}},
        "cut_total_m3": cut_total,
        "subcatchments": sub_rows,
        "assumptions": [
            "Grading only cuts: no berms, so each element overflows at the existing ground level on its rim.",
            "Excavated soil leaves the site (fill is not designed): cut = net export.",
            "Rain garden storage = ponding x (1 - plants) + media voids (porosity - field capacity) + gravel voids.",
            "Elements emptied only by infiltration are rejected when ponding depth / rate exceeds nbs.max_drawdown_hr.",
            "Element sizes are first estimates; SWMM runs of the option give the actual performance.",
        ],
    }
    if write_outputs:
        _write_outputs(project, option_id, g, zg, elements, placed, subs, blocked)
    project.history.log("layout_generate", option=option_id, elements=[p.id for p in placed], kept=[e.id for e in kept])
    return report


def _element_props(p: Placed, P, g: Grid, rp: int, runoff_mm: float) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(id=p.id, type=p.type, source="proposal", outflow_to=p.outflow_to)
    if p.type == "bioswale":
        info = p.notes[-1]
        base.update(geometry=info["line"], top_width_m=float(P.value("nbs.bioswale.top_width_m")),
                    longitudinal_slope_pct=round(info["slope_pct"], 3),
                    notes=f"along a concentrated flow line draining {p.drainage_m2:.0f} m2; length "
                          f"{info['length_m']:.1f} m, slope {info['slope_pct']:.2f} %; cut {p.cut.cut_m3:.1f} m3")
        if info.get("path_crossings"):
            pts = ", ".join(f"({x:.1f}, {y:.1f})" for x, y in info["path_crossings"])
            base["notes"] += (f"; crosses {len(info['path_crossings'])} footpath(s) at {pts} through a trench drain "
                              "(the path stays level)")
        if info.get("underdrain"):
            base["notes"] += (f"; native soil {info['native_rate_mm_hr']:g} mm/h < "
                              f"{float(P.value_or('nbs.underdrain_below_native_mm_hr', 13.0)):g} mm/h: build with a "
                              f"perforated underdrain in a {float(P.value_or('nbs.bioswale.underdrain_gravel_depth_m', 0.45)):g} m "
                              "gravel layer (HC 4.7)")
        return base
    if p.type == "recharge_well":
        base.pop("outflow_to")
        base.update(geometry={"type": "Point", "coordinates": (float(g.X[p.seed]), float(g.Y[p.seed]))},
                    infiltration_rate_mm_hr=float(P.value("site.recharge_strata_rate_mm_hr")),
                    invert_elev_m=round(p.cut.bottom_m, 3), overflow_to=p.outflow_to,
                    well_diameter_m=float(P.value("nbs.recharge_well.diameter_m")),
                    well_depth_m=float(P.value("nbs.recharge_well.depth_m")),
                    notes=f"receives the overflow of {p.notes[0]}; strata rate and rock depth from site parameters")
        return base
    geom = _polygons(np.where(p.region, 1, 0), g.dem)[1]
    if geom.geom_type != "Polygon":
        geom = max(geom.geoms, key=lambda q: q.area)
    base.update(geometry=geom.__geo_interface__,
                notes=f"sized for the {rp}-yr storm: {p.drainage_m2:.0f} m2 draining here x {runoff_mm:.0f} mm = "
                      f"{p.target_m3:.1f} m3; holds ~{p.estimate_m3:.1f} m3 (limited by {p.limited_by}); "
                      f"rim {p.cut.rim_m:.2f} m, cut {p.cut.cut_m3:.1f} m3")
    ud = next((n for n in p.notes if isinstance(n, dict) and n.get("underdrain")), None)
    if p.type == "rain_garden" and ud:
        # SWMM drain q = C h^0.5 (mm/h, h in mm): C = 2 sqrt(D) / T empties a water depth D in T hours.
        # D: the stone layer full plus the media's drainable water; T: the drawdown limit (HC 4.2: 48 h)
        stone = float(P.value_or("nbs.rain_garden.underdrain_storage_depth_m", 0.6))
        media = float(P.value("nbs.rain_garden.soil_media_depth_m"))
        drainable = float(P.value("nbs.rain_garden.media_porosity")) - float(P.value("nbs.rain_garden.media_field_capacity"))
        depth_mm = 1000 * (stone * float(P.value("nbs.rain_garden.storage_layer_void_ratio")) + media * drainable)
        C = 2 * depth_mm ** 0.5 / float(P.value("nbs.max_drawdown_hr"))
        base.update(storage_layer_depth_m=stone, underdrain_coefficient=round(C, 3))
        base["notes"] += (f"; underdrained (HC 4.2): native soil {ud['native_rate_mm_hr']:g} mm/h < "
                          f"{float(P.value_or('nbs.underdrain_below_native_mm_hr', 13.0)):g} mm/h, {stone:g} m stone "
                          f"layer, drain sized to empty it within {float(P.value('nbs.max_drawdown_hr')):g} h")
    if p.type != "rain_garden":
        base.update(invert_elev_m=round(p.cut.bottom_m, 3), overflow_to=p.overflow_to or p.outflow_to)
        if p.type == "retention_pond":
            base.pop("outflow_to")  # permanent pool: overflow weir only
    return base


STORAGE_TYPES = {"detention_pond", "retention_pond", "recharge_well"}


def _route(placed: List[Placed], g: Grid, sub_lab, sub_props) -> None:
    """Treatment train: each element sends water to the next element downstream, else to its outfall.
    Storage elements discharge only to storage elements (SWMM); rain gardens receive only from rain gardens."""
    el_lab = np.zeros(g.mask.shape, int)
    for i, p in enumerate(placed, start=1):
        if p.type != "recharge_well":
            el_lab[p.region] = i
    rec = fl.downstream(g.dirs).ravel()
    for i, p in enumerate(placed, start=1):
        if p.type == "recharge_well":
            continue
        start = np.ravel_multi_index(p.end if p.end else p.seed, g.mask.shape)
        target_id = None
        j = start
        for _ in range(g.mask.size):
            j = rec[j]
            if j < 0:
                break
            lab = el_lab.ravel()[j]
            if lab and lab != i:
                q = placed[lab - 1]
                if (p.type not in STORAGE_TYPES or q.type in STORAGE_TYPES) and (q.type != "rain_garden" or p.type == "rain_garden"):
                    target_id = q.id
                    break
        sid = int(sub_lab.ravel()[start])
        p.outflow_to = target_id or (sub_props[sid]["outlet"] if sid in sub_props else "")
        if not p.outflow_to:
            raise LayoutError(f"{p.id}: cannot find where it drains.")
    by_id = {p.id: p for p in placed}
    for w in placed:
        if w.type == "recharge_well":
            pond = by_id[w.notes[0]]
            w.outflow_to = pond.overflow_to or pond.outflow_to
            pond.overflow_to = w.id


def _place_swales(project, g: Grid, blocked, taken, rejected, wacc_now, accept, budget_left, runoff_mm,
                  native_rate, max_dd, skipped) -> None:
    """Bioswales along concentrated flow lines: from a channel head down the D8 path while the ground
    is free, between ``min_length_m`` and ``max_length_m``, at a longitudinal slope within the limits."""
    from scipy import ndimage
    from shapely.geometry import LineString

    P = project.parameters
    cell, cell2 = g.cell, g.cell ** 2
    W = float(P.value("nbs.bioswale.top_width_m"))
    min_c = float(P.value("nbs.bioswale.min_contributing_area_m2"))
    Lmin, Lmax = float(P.value("nbs.bioswale.min_length_m")), float(P.value("nbs.bioswale.max_length_m"))
    smin = float(P.value("nbs.bioswale.min_longitudinal_slope_pct"))
    smax = float(P.value("nbs.bioswale.max_longitudinal_slope_pct"))
    live = float(P.value("nbs.bioswale.max_ponding_depth_m"))
    max_cross = float(P.value_or("layout.swale_path_crossing_max_m", 0.0))
    cross = crossable(project, g).ravel() if max_cross > 0 else np.zeros(g.mask.size, bool)
    rec = fl.downstream(g.dirs).ravel()
    d = g.dirs.ravel()
    k = 0
    reasons: Dict[str, int] = {}
    for _ in range(200):
        captured, wacc = wacc_now(conveying=True)
        free = g.mask & ~blocked & ~taken & ~rejected
        cand = free & (wacc >= min_c)
        if not cand.any() or budget_left() < W * Lmin:
            break
        # channel heads: candidate cells that no other candidate drains into
        ci = np.flatnonzero(cand)
        donors = np.zeros(g.mask.size, bool)
        rr = rec[ci]
        donors[rr[rr >= 0]] = True
        heads = [i for i in ci if not donors[i]]
        head = max(heads, key=lambda i: wacc.ravel()[i])
        path = [head]
        length = 0.0
        j = head
        crossings: List[List[int]] = []
        # a line rejected as too short may still be part of a longer one from upstream: rejected cells only
        # stop being swale heads, not swale ground
        fr, tk = (g.mask & ~blocked & ~taken).ravel(), taken.ravel()
        while length < Lmax:
            nxt = rec[j]
            if nxt < 0:
                break
            if not fr[nxt]:
                # a footpath: the swale passes under it through a trench drain when the path is narrow and open
                # ground follows; the path cells stay level (not carved)
                run, at, run_len, jj = [], nxt, 0.0, j
                while at >= 0 and cross[at] and not tk[at] and run_len <= max_cross:
                    run_len += float(fl.DIST[d[jj]]) * cell
                    run.append(at)
                    jj, at = at, rec[at]
                if run and at >= 0 and fr[at] and run_len <= max_cross and length + run_len < Lmax:
                    crossings.append(run)
                    path += run
                    length += run_len
                    j = run[-1]
                    continue
                break
            length += float(fl.DIST[d[j]]) * cell
            path.append(nxt)
            j = nxt
        rs, cs = np.unravel_index(path, g.mask.shape)
        drop = float(g.z[rs[0], cs[0]] - g.z[rs[-1], cs[-1]])
        slope = 100 * drop / length if length > 0 else 0.0
        why = None
        if length < Lmin:
            why = "flow line too short on free ground"
        elif not smin <= slope <= smax:
            why = f"longitudinal slope outside {smin:g}-{smax:g} %"
        # no drawdown rejection: a swale empties along its grade (SWMM's vegetative swale); on slow native soil
        # HC 4.7 calls for an underdrain, recorded on the element (SWMM credits only the surface infiltration)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
            rejected.ravel()[path] = True
            continue
        line = LineString(list(zip(g.X[rs, cs], g.Y[rs, cs]))).simplify(cell / 2)
        fp = line.buffer(W / 2, cap_style=2)
        region = contains_xy(fp, g.X, g.Y) & g.mask
        crossed = np.zeros(g.mask.shape, bool)
        if crossings:
            crossed.ravel()[[i for run in crossings for i in run]] = True
            crossed = ndimage.binary_dilation(crossed, iterations=int(np.ceil(W / cell))) & cross.reshape(g.mask.shape)
        if (region & ((blocked & ~crossed) | taken)).sum() > 0.1 * region.sum() or region.sum() * cell2 > budget_left():
            reasons["footprint hits keep-out or budget"] = reasons.get("footprint hits keep-out or budget", 0) + 1
            rejected.ravel()[path] = True
            continue
        region &= ~(blocked | taken)
        contrib = float(wacc.ravel()[path[-1]])
        k += 1
        p = Placed(f"BS_{k}", "bioswale", region, (int(rs[0]), int(cs[0])), contrib, runoff_mm / 1000 * contrib,
                   storage_swale(P, float(fp.area)), "conveyance")
        p.end = (int(rs[-1]), int(cs[-1]))
        native = native_rate(int(rs[0]), int(cs[0]))
        xings = []
        for run in crossings:
            rr, cc = np.unravel_index(run, g.mask.shape)
            xings.append([round(float(g.X[rr, cc].mean()), 2), round(float(g.Y[rr, cc].mean()), 2)])
        p.notes.append({"line": line.__geo_interface__, "length_m": length, "slope_pct": slope, "path_crossings": xings,
                        "underdrain": native < float(P.value_or("nbs.underdrain_below_native_mm_hr", 13.0)),
                        "native_rate_mm_hr": native})
        accept(p)
    if reasons and k == 0:
        skipped.append("bioswale: none placed (" + ", ".join(f"{v} x {r}" for r, v in reasons.items()) + ").")


def _nothing_fits(blocked_counts: Dict[str, int], skipped: List[str], cell2: float) -> str:
    """Why no element was placed, in plain words, and what would let the engine place more."""
    lost = sorted(((k, v * cell2) for k, v in blocked_counts.items() if v), key=lambda kv: -kv[1])
    kept_out = ", ".join(f"{k} {a:.0f} m²" for k, a in lost[:4])
    lines = ["No element could be placed on this park."]
    if kept_out:
        lines.append(f"Ground kept free: {kept_out}.")
    lines += [s[0].upper() + s[1:] for s in skipped]
    lines.append("To place more: draw elements yourself in Design, lower the keep-out distances, or add a "
                 "percolation test (Site setup > Ground) and borehole data for recharge wells (Site setup > Wells).")
    return " ".join(lines)


def storage_swale(P, area_m2: float) -> float:
    """Swale surface storage (m3) for a footprint of ``area_m2`` (same formula as the SWMM element)."""
    W = float(P.value("nbs.bioswale.top_width_m"))
    d = float(P.value("nbs.bioswale.max_ponding_depth_m"))
    z = float(P.value("nbs.bioswale.side_slope_h_v"))
    veg = float(P.value_or("nbs.bioswale.vegetation_volume_fraction", 0.0))
    return area_m2 / W * d * max(W - z * d, 0.0) * (1 - veg)


def _grade_swale(z: np.ndarray, g: Grid, p: Placed, P, protect: np.ndarray) -> Tuple[np.ndarray, Cut]:
    """Trapezoidal channel: invert = ground along the line minus depth, never rising downstream."""
    import shapely

    line = shape(p.notes[-1]["line"])
    W = float(P.value("nbs.bioswale.top_width_m"))
    D = float(P.value("nbs.bioswale.max_ponding_depth_m"))
    side = float(P.value("nbs.bioswale.side_slope_h_v"))
    n = max(2, int(line.length / (g.cell / 2)) + 1)
    s = np.linspace(0, line.length, n)
    pts = shapely.line_interpolate_point(line, s)
    r = np.clip(((g.dem.origin[1] - shapely.get_y(pts)) / g.cell).astype(int), 0, z.shape[0] - 1)
    c = np.clip(((shapely.get_x(pts) - g.dem.origin[0]) / g.cell).astype(int), 0, z.shape[1] - 1)
    ground = np.where(np.isfinite(z[r, c]), z[r, c], np.nanmin(z))
    invert = np.minimum.accumulate(ground - D)
    region = p.region & ~protect
    rr, cc = np.nonzero(region)
    cells = shapely.points(g.X[rr, cc], g.Y[rr, cc])
    st = shapely.line_locate_point(line, cells)
    dist = shapely.distance(line, cells)
    b2 = max(W / 2 - side * D, 0.0)
    zd = np.interp(st, s, invert) + np.clip((dist - b2) / side, 0, D)
    out = z.copy()
    out[rr, cc] = np.minimum(z[rr, cc], zd)
    cut = float((z - out)[rr, cc].sum() * g.cell ** 2)
    return out, Cut(float(ground[0]), float(invert[-1]), cut, p.estimate_m3, float(p.region.sum() * g.cell ** 2))


def _place_wells(project, g: Grid, blocked, placed: List[Placed], accept, skipped) -> None:
    """Recharge wells at the spill point of each pond, taking its overflow (treatment train)."""
    from scipy import ndimage

    P = project.parameters
    missing = [k for k in ("site.recharge_strata_rate_mm_hr", "site.rock_depth_m") if k not in P]
    if missing:
        skipped.append(f"recharge_well: needs {', '.join(missing)} (borehole / percolation data); not assumed.")
        return
    depth = float(P.value("nbs.recharge_well.depth_m"))
    rock = float(P.value("site.rock_depth_m"))
    if depth > rock - 0.5:
        skipped.append(f"recharge_well: well depth {depth:g} m reaches within 0.5 m of rock at {rock:g} m; "
                       "reduce nbs.recharge_well.depth_m.")
        return
    dia = float(P.value("nbs.recharge_well.diameter_m"))
    spacing = float(P.value("nbs.recharge_well.min_spacing_m"))
    wells: List[Tuple[float, float]] = []
    k = 0
    for pond in [p for p in placed if p.type in ("detention_pond", "retention_pond")]:
        ring = ndimage.binary_dilation(pond.region, structure=np.ones((3, 3))) & ~pond.region & g.mask & ~blocked
        if not ring.any():
            continue
        zr = np.where(ring, g.z, np.inf)
        r, c = np.unravel_index(int(np.argmin(zr)), zr.shape)
        x, y = float(g.X[r, c]), float(g.Y[r, c])
        if any(np.hypot(x - a, y - b) < spacing for a, b in wells):
            continue
        region = (np.hypot(g.X - x, g.Y - y) <= max(dia / 2, g.cell / 2)) & g.mask
        k += 1
        w = Placed(f"RW_{k}", "recharge_well", region, (int(r), int(c)), 0.0, 0.0,
                   float(np.pi * dia ** 2 / 4 * depth), "receives pond overflow")
        w.notes.append(pond.id)
        wells.append((x, y))
        accept(w)
    if k == 0:
        skipped.append("recharge_well: no pond to receive overflow from.")


def _write_outputs(project, option_id, g: Grid, zg, elements, placed, subs, blocked) -> None:
    P = project.parameters
    cell = g.cell
    odir = f"scenarios/{option_id}"
    save_elements(project, option_id, elements)
    project.write_geojson(f"{odir}/site/subcatchments.geojson", {"type": "FeatureCollection", "features": subs})
    nod = g.dem.nodata
    graded = DEM(np.where(g.mask, zg, nod), cell, g.dem.origin, g.dem.crs, nod)
    write_geotiff(graded, project.path(f"{odir}/terrain/graded.tif"))
    write_geotiff(graded, project.path(f"terrain/graded_{option_id}.tif"))
    write_geotiff(DEM(np.where(g.mask, g.dem.z - zg, nod), cell, g.dem.origin, g.dem.crs, nod),
                  project.path(f"{odir}/terrain/cut.tif"))
    intervals = [float(v) for v in P.value("layout.contour_intervals_m")]
    contours = []
    for iv in intervals:
        for c in _contours(graded, iv):
            c["properties"]["interval_m"] = iv
            contours.append(c)
    project.write_geojson(f"{odir}/design_contours.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", **c} for c in contours]})
    fine = min(intervals)
    _dxf(project.path(f"{odir}/design.dxf"), g, elements, placed,
         [c for c in contours if c["properties"]["interval_m"] == fine])
    _plot(project.path(f"{odir}/layout.png"), g, blocked, placed, subs, elements)


def _subcatchment_raster(project: Project, g: Grid) -> Tuple[np.ndarray, Dict[int, Dict[str, Any]]]:
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    feats = project.read_geojson("site/subcatchments.geojson")["features"]
    if not feats:
        raise LayoutError("no site subcatchments; run `terrain delineate` first.")
    t = from_origin(g.dem.origin[0], g.dem.origin[1], g.cell, g.cell)
    lab = rasterize([(shape(f["geometry"]), i + 1) for i, f in enumerate(feats)], out_shape=g.mask.shape,
                    transform=t, fill=0, dtype="int32")
    # cells on polygon edges left unlabelled: take the nearest label
    from scipy import ndimage

    if (g.mask & (lab == 0)).any():
        idx = ndimage.distance_transform_edt(lab == 0, return_distances=False, return_indices=True)
        lab = lab[idx[0], idx[1]]
    return lab, {i + 1: f["properties"] for i, f in enumerate(feats)}


def _rebuild(project: Project, g: Grid, zg: np.ndarray, sinks: np.ndarray, owner: np.ndarray,
             sub_lab: np.ndarray, sub_props: Dict[int, Dict[str, Any]]):
    """Subcatchments on the graded ground: one per element (draining into it) and the rest per outfall."""
    P = project.parameters
    cell, cell2 = g.cell, g.cell ** 2
    z = np.where(g.mask, zg, np.nan)
    filled = fl.fill_sinks(z, g.mask, sinks=sinks)
    dirs = fl.d8_directions(filled, g.mask, sinks=sinks)
    term = fl.outlet_of(filled, g.mask, dirs)
    L = fl.flow_length(filled, g.mask, dirs, cell)
    depth = np.where(g.mask & ~sinks, filled - z, 0.0)
    depth = np.where(depth >= float(P.value("terrain.min_depression_depth_m")), depth, 0.0)
    gy, gx = np.gradient(z, cell)
    slope = 100 * np.hypot(gx, gy)

    names: Dict[str, int] = {}
    lab = np.zeros(g.mask.shape, int)
    tflat = term.ravel()
    own, base = owner.ravel(), sub_lab.ravel()
    for i in np.flatnonzero(g.mask):
        t = tflat[i]
        key = f"SC_{own[t]}" if sinks.ravel()[t] else str(sub_props[base[t]]["id"])
        lab.ravel()[i] = names.setdefault(key, len(names) + 1)
    polys = _polygons(lab, g.dem)
    imperv, _, _ = context_surfaces(project, g.domain, float(g.mask.sum() * cell2),
                                    set(P.value("terrain.impervious_context_kinds")))
    dbase = float(P.value("surface.dstore_perv_mm"))
    copy_keys = ("soil_zone", "curve_number", "tr55_cover", "land_cover", "n_imperv", "n_perv", "dstore_imperv_mm",
                 "pct_zero_imperv")
    feats, rows = [], []
    for key, k in names.items():
        m = lab == k
        poly = polys[k]
        area = float(m.sum() * cell2)
        ids, cnt = np.unique(sub_lab[m], return_counts=True)
        src = sub_props[int(ids[np.argmax(cnt)])]
        outlet = src["outlet"] if key.startswith("SC_") else sub_props[[i for i, p in sub_props.items()
                                                                         if str(p["id"]) == key][0]]["outlet"]
        s = slope[m]
        s = s[np.isfinite(s)]
        dep_mm = 1000 * float(depth[m].sum() * cell2) / area
        props = {kk: src[kk] for kk in copy_keys if kk in src}
        props.update({
            "id": key, "outlet": outlet,
            "pct_imperv": round(float(poly.intersection(imperv).area / poly.area * 100) if not imperv.is_empty else 0.0, 2),
            "slope_pct": round(float(np.median(s)) if s.size else 0.5, 3),
            "flow_length_m": round(max(float(np.percentile(L[m], 95)), cell), 2),
            "dstore_perv_mm": round(dbase + dep_mm, 2),
            "note": ("drains into " + key[3:] if key.startswith("SC_") else "drains to " + outlet)
                    + " on the graded ground (Phase 4 rebuild)",
        })
        feats.append({"type": "Feature", "geometry": poly.__geo_interface__, "properties": props})
        rows.append({"id": key, "outlet": outlet, "area_m2": area})
    return feats, rows


def _contours(dem: DEM, interval: float) -> List[Dict[str, Any]]:
    from ..terrain.tin import contour_lines

    return contour_lines(dem, interval)


def _dxf(path, g: Grid, elements: List[NbSElement], placed: List[Placed], contours) -> None:
    """Design drawing in survey coordinates, on SP-DSN-* layers, to overlay on the survey."""
    import ezdxf

    from ..io.cad import layer_standard

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    spec = {s["name"]: s for s in layer_standard()["layers"]}
    layer_of = {"rain_garden": "SP-DSN-RAINGARDEN", "bioswale": "SP-DSN-SWALE", "recharge_well": "SP-DSN-WELL"}
    for name in ("SP-DSN-CONTOUR", "SP-DSN-RAINGARDEN", "SP-DSN-SWALE", "SP-DSN-POND", "SP-DSN-WELL", "SP-DSN-LABEL",
                 "SP-SITE-BOUNDARY"):
        doc.layers.add(name, color=int(spec.get(name, {}).get("color", 7)))
    msp = doc.modelspace()
    for c in contours:
        msp.add_lwpolyline(c["geometry"]["coordinates"], dxfattribs={"layer": "SP-DSN-CONTOUR",
                                                                    "elevation": float(c["properties"]["z"])})
    for b in getattr(g.domain, "geoms", [g.domain]):
        msp.add_lwpolyline(list(b.exterior.coords), close=True, dxfattribs={"layer": "SP-SITE-BOUNDARY"})
    info = {p.id: p for p in placed}
    for e in elements:
        fp = e.footprint()
        layer = layer_of.get(e.type, "SP-DSN-POND")
        for poly in getattr(fp, "geoms", [fp]):
            msp.add_lwpolyline(list(poly.exterior.coords), close=True, dxfattribs={"layer": layer})
        p = info.get(e.id)
        txt = f"{e.id} {fp.area:.0f} m2" + (f" RIM {p.cut.rim_m:.2f} BOT {p.cut.bottom_m:.2f}" if p else "")
        c = fp.representative_point()
        msp.add_text(txt, dxfattribs={"layer": "SP-DSN-LABEL", "height": 0.4, "insert": (c.x, c.y)})
    doc.saveas(path)


def _plot(out, g: Grid, blocked, placed: List[Placed], subs, elements) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x0, y0, x1, y1 = g.dem.bounds()
    fig, ax = plt.subplots(figsize=(10, 8), dpi=130)
    ax.imshow(np.where(g.mask, g.z, np.nan), extent=(x0, x1, y0, y1), cmap="Greys_r", alpha=0.5)
    ax.imshow(np.where(blocked & g.mask, 1.0, np.nan), extent=(x0, x1, y0, y1), cmap="Reds", vmin=0, vmax=2, alpha=0.35)
    pal = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
    for i, f in enumerate(subs):
        geom = shape(f["geometry"])
        for poly in getattr(geom, "geoms", [geom]):
            ax.plot(*poly.exterior.xy, color=pal[i % len(pal)], lw=0.8)
    for e in elements:
        fp = e.footprint()
        col = {"rain_garden": "#008300", "bioswale": "#1baf7a", "recharge_well": "#6250d6"}.get(e.type, "#2a78d6")
        for poly in getattr(fp, "geoms", [fp]):
            ax.fill(*poly.exterior.xy, color=col, alpha=0.6)
        c = fp.representative_point()
        ax.annotate(e.id, (c.x, c.y), fontsize=7, ha="center")
    ax.set_title("Generated layout: rain gardens (dark green), swales (green), ponds (blue), wells (purple),\n"
                 "keep-out (red), rebuilt subcatchments (outlines)", fontsize=9)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
