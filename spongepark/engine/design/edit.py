"""Designer edits: NbS elements placed by hand (in the Unity design tools, Grasshopper or a script).

:func:`apply` takes the scenario's elements as drawn (a GeoJSON FeatureCollection in project metres),
saves them as designer elements, carves them into the ground (the same regrading the generated layouts
use, in its quick form) and checks them, without running SWMM: placing and shaping is quick. The flow
map, the rebuilt subcatchments and the drawings wait until the designer asks for them (Design done):
the flow map is redone when next read, the full regrade runs before SWMM (`ensure_regraded`).

Every call records what the designer did in ``edit_log.json`` (brief section 7: training data for
learning from designers).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from shapely.geometry import shape

from ..nbs.components import NbSElement, read_elements, save_elements_fc
from ..project import Project
from ..project.schema import EditLog, EditLogEntry, Scenario

log = logging.getLogger(__name__)

# element types the design tools place, and how each is drawn
TOOLS = {
    "rain_garden": "polygon",
    "detention_pond": "polygon",
    "retention_pond": "polygon",
    "bioswale": "line",
    "recharge_well": "point",
    "green_bridge": "line",   # drawn across a bioswale
}


def _depth_ranges(project: Project) -> Dict[str, List[float]]:
    """Public-safety ponding depth ranges per type (m), from the project's parameters."""
    ranges = project.parameters.value_or("optimise.ranges", {}) or {}
    out = {}
    for k, v in ranges.items():
        if k.startswith("nbs.") and k.endswith(".max_ponding_depth_m"):
            out[k.split(".")[1]] = [float(v[0]), float(v[1])]
    return out


def _value(project: Project, el: NbSElement, field: str, key: str) -> Optional[float]:
    v = getattr(el, field, None)
    if v is None:
        v = project.parameters.value_or(key, None)
    return float(v) if isinstance(v, (int, float)) else None


def measure(project: Project, el: NbSElement) -> Dict[str, Any]:
    """Size and indicative storage of one element from its geometry and parameters (no soil data needed)."""
    t = el.type
    g = shape(el.geometry)
    row: Dict[str, Any] = {"id": el.id, "type": t}
    if t == "recharge_well":
        d = _value(project, el, "well_diameter_m", "nbs.recharge_well.diameter_m") or 1.2
        depth = _value(project, el, "well_depth_m", "nbs.recharge_well.depth_m") or 6.0
        row.update(diameter_m=d, depth_m=depth, area_m2=math.pi * d * d / 4,
                   storage_m3=math.pi * d * d / 4 * depth * 0.4)   # filter media voids
        return row
    if t == "green_bridge":
        deck = _value(project, el, "top_width_m", "nbs.green_bridge.top_width_m") or 1.5
        h = _value(project, el, "dam_height_m", "nbs.green_bridge.dam_height_m") or 0.15
        pool = float(el.pool_area_m2 or 0.0)   # known once the ground is carved
        row.update(length_m=g.length, width_m=deck, crest_m=h, area_m2=g.length * deck, pool_area_m2=pool,
                   storage_m3=pool * h / 2)   # a wedge of water behind the crest
        return row
    if t == "bioswale":
        w = _value(project, el, "top_width_m", "nbs.bioswale.top_width_m") or 3.0
        depth = _value(project, el, "max_ponding_depth_m", "nbs.bioswale.max_ponding_depth_m") or 0.3
        z = _value(project, el, "side_slope_h_v", "nbs.bioswale.side_slope_h_v") or 3.0
        length = g.length if g.geom_type == "LineString" else g.length / 2
        cross = depth * max(w - z * depth, 0.0)
        row.update(length_m=length, width_m=w, depth_m=depth, area_m2=length * w, storage_m3=length * cross)
        return row
    area = g.area
    depth = _value(project, el, "max_ponding_depth_m", f"nbs.{t}.max_ponding_depth_m") or 0.3
    row.update(area_m2=area, depth_m=depth)
    if t == "rain_garden":
        media = _value(project, el, "soil_media_depth_m", "nbs.rain_garden.soil_media_depth_m") or 0.0
        row.update(media_depth_m=media, storage_m3=area * (depth + media * 0.25))   # ponding + media voids
    else:
        z = _value(project, el, "side_slope_h_v", f"nbs.{t}.side_slope_h_v") or 0.0
        # live storage of a basin with sloped sides: the top area shrinks by the banks
        r = math.sqrt(area / math.pi)
        bottom = math.pi * max(r - z * depth, 0.0) ** 2
        row.update(side_slope_h_v=z, storage_m3=depth * (area + bottom + math.sqrt(area * bottom)) / 3)
        if t == "retention_pond":
            row["permanent_pool_depth_m"] = _value(project, el, "permanent_pool_depth_m",
                                                   "nbs.retention_pond.permanent_pool_depth_m")
    return row


def check(project: Project, elements: List[NbSElement], rows: List[Dict[str, Any]],
          regrade_warnings: List[str]) -> Dict[str, Any]:
    """Warnings a designer should see while placing: outside the park, keep-out areas, depth limits, budget."""
    from ..site.survey_layers import park_boundary

    warnings: List[Dict[str, str]] = []
    park = park_boundary(project)
    site_area = park.area if park is not None else None
    ranges = _depth_ranges(project)
    for el, row in zip(elements, rows):
        g = shape(el.geometry)
        if park is not None and not park.buffer(0.5).contains(g):
            warnings.append({"element": el.id, "kind": "outside", "text": f"{el.id} is partly outside the park boundary."})
        lim = ranges.get(el.type)
        d = row.get("depth_m")
        if lim and d is not None and not (lim[0] - 1e-6 <= d <= lim[1] + 1e-6):
            warnings.append({"element": el.id, "kind": "depth",
                             "text": f"{el.id}: ponding depth {d:.2f} m is outside the safe range "
                                     f"{lim[0]:.2f}-{lim[1]:.2f} m for a {el.type.replace('_', ' ')} (default limits)."})
    for w in regrade_warnings:
        eid = w.split(" ", 1)[0]
        warnings.append({"element": eid, "kind": "keep_out", "text": w})
    warnings += _swale_grade_checks(project, elements)
    warnings += _bridge_checks(project, elements)
    # a bridge's deck lies on its swale: it adds no area of its own
    used = sum(r.get("area_m2") or 0.0 for r in rows if r.get("type") != "green_bridge")
    limit_pct = float(project.parameters.value_or("layout.max_area_pct", 10.0))
    budget = {"used_m2": used, "site_m2": site_area,
              "used_pct": 100.0 * used / site_area if site_area else None, "limit_pct": limit_pct}
    if budget["used_pct"] is not None and budget["used_pct"] > limit_pct:
        warnings.append({"element": "", "kind": "budget",
                         "text": f"The elements cover {budget['used_pct']:.1f} % of the park; the area budget is {limit_pct:g} %."})
    return {"warnings": warnings, "budget": budget}


def _swale_grade_checks(project: Project, elements: List[NbSElement]) -> List[Dict[str, str]]:
    """Bioswales should run across the slope at a gentle grade (HC 4.7 p.6, 12: 0.5-2 % preferred, up to 6 % with
    check dams; below 0.5 % water stands). Warn when the ground along one falls too steeply, and say when it runs
    straight down the slope."""
    import numpy as np

    from ..terrain.raster import read_geotiff

    swales = [e for e in elements if e.type == "bioswale" and e.geometry.get("type") == "LineString"]
    if not swales or not project.exists("terrain/existing.tif"):
        return []
    dem = read_geotiff(project.path("terrain/existing.tif"))
    z = np.where(dem.z == dem.nodata, np.nan, dem.z)
    gy, gx = np.gradient(z, dem.cell_size)
    fall = 100 * np.hypot(gx, gy)

    def at(arr, x, y):
        c = int((x - dem.origin[0]) / dem.cell_size)
        r = int((dem.origin[1] - y) / dem.cell_size)
        return float(arr[r, c]) if 0 <= r < arr.shape[0] and 0 <= c < arr.shape[1] else float("nan")

    P = project.parameters
    lo = float(P.value_or("nbs.bioswale.min_longitudinal_slope_pct", 0.5))
    hi = float(P.value_or("layout.swale_grade_preferred_max_pct", 2.0))
    top = float(P.value_or("nbs.bioswale.max_longitudinal_slope_pct", 4.0))
    out: List[Dict[str, str]] = []
    for e in swales:
        line = shape(e.geometry)
        if line.length < 1.0:
            continue
        pts = [line.interpolate(d) for d in np.linspace(0, line.length, max(2, int(line.length) + 1))]
        zs = np.array([at(z, p.x, p.y) for p in pts])
        if np.isnan(zs).any():
            continue
        grade = 100 * abs(zs[0] - zs[-1]) / line.length
        steepest = float(np.nanmean([at(fall, p.x, p.y) for p in pts]))
        downhill = steepest > 1.0 and grade >= 0.8 * steepest
        how = " It runs straight down the slope: turn it across the slope, along the contours." if downhill else ""
        if grade > top:
            out.append({"element": e.id, "kind": "grade",
                        "text": f"{e.id}: the ground along it falls {grade:.1f} %, more than {top:g} % (HC 4.11: drop "
                                f"structures needed; HC 4.7: 0.5-2 % preferred, up to 6 % with check dams)." + how})
        elif grade > hi:
            out.append({"element": e.id, "kind": "grade",
                        "text": f"{e.id}: the ground along it falls {grade:.1f} %; HC 4.7 prefers 0.5-{hi:g} % "
                                f"(faster water erodes and soaks in less; add check dams every 10-15 m)." + how})
        elif grade < lo:
            out.append({"element": e.id, "kind": "grade",
                        "text": f"{e.id}: the ground along it is almost level ({grade:.2f} %); it is carved to fall "
                                f"at least {lo:g} % (HC 4.7: below 0.5 % water stands), so it gets deeper towards its end."})
    return out


def _bridge_checks(project: Project, elements: List[NbSElement]) -> List[Dict[str, str]]:
    """Green bridges: each crosses a swale, stays below its banks, and bridges on one swale are not too close."""
    out: List[Dict[str, str]] = []
    swales = [e for e in elements if e.type == "bioswale" and e.geometry.get("type") == "LineString"]
    gap = float(project.parameters.value_or("nbs.green_bridge.min_spacing_m", 10.0))
    on: Dict[str, List[tuple]] = {}
    for b in (e for e in elements if e.type == "green_bridge"):
        line = shape(b.geometry)
        host = max(swales, key=lambda s: line.intersection(s.footprint()).length, default=None)
        if host is None or line.intersection(host.footprint()).length <= 0:
            out.append({"element": b.id, "kind": "bridge",
                        "text": f"{b.id} does not cross a bioswale: draw it across one so it holds water back."})
            continue
        cl = shape(host.geometry)
        if not line.intersects(cl):
            out.append({"element": b.id, "kind": "bridge",
                        "text": f"{b.id} does not reach across {host.id}: draw it from bank to bank."})
        h = _value(project, b, "dam_height_m", "nbs.green_bridge.dam_height_m") or 0.15
        d = _value(project, host, "max_ponding_depth_m", "nbs.bioswale.max_ponding_depth_m") or 0.3
        if h > d + 1e-6:
            out.append({"element": b.id, "kind": "bridge",
                        "text": f"{b.id}: crest {h:.2f} m is above the depth of {host.id} ({d:.2f} m); it is held to the swale depth."})
        x = line.intersection(cl)
        on.setdefault(host.id, []).append((cl.project(x.centroid if not x.is_empty else line.centroid), b.id))
    for host, bs in on.items():
        bs.sort()
        for (s0, a), (s1, b) in zip(bs, bs[1:]):
            if s1 - s0 < gap:
                out.append({"element": b, "kind": "bridge",
                            "text": f"{a} and {b} are {s1 - s0:.0f} m apart on {host}; guidelines space check dams "
                                    f"at least {gap:g} m apart."})
    return out


def defaults(project: Project) -> Dict[str, Any]:
    """What the design tools need: how each type is drawn, its default sizes and the depth limits."""
    P = project.parameters
    keys = {
        "rain_garden": ["max_ponding_depth_m", "soil_media_depth_m"],
        "bioswale": ["top_width_m", "max_ponding_depth_m", "side_slope_h_v", "check_dam_spacing_m"],
        "detention_pond": ["max_ponding_depth_m", "side_slope_h_v", "outlet_diameter_m"],
        "retention_pond": ["permanent_pool_depth_m", "max_ponding_depth_m", "side_slope_h_v", "safety_bench_width_m"],
        "recharge_well": ["well_diameter_m", "well_depth_m"],
        "green_bridge": ["dam_height_m", "top_width_m"],
    }
    alias = {"well_diameter_m": "diameter_m", "well_depth_m": "depth_m"}
    out = {}
    ranges = _depth_ranges(project)
    for t, fields in keys.items():
        vals = {}
        for f in fields:
            v = P.value_or(f"nbs.{t}.{alias.get(f, f)}", None)
            if isinstance(v, (int, float)):
                vals[f] = float(v)
        out[t] = {"draw": TOOLS[t], "defaults": vals, "depth_range_m": ranges.get(t)}
    out["budget_pct"] = float(P.value_or("layout.max_area_pct", 10.0))
    return out


def current(project: Project, scenario_id: str) -> Dict[str, Any]:
    """The scenario's elements as a FeatureCollection, measured and checked (no regrading)."""
    from ..nbs.components import elements_fc, has_elements

    fc = elements_fc(project, scenario_id) if has_elements(project, scenario_id) else {"type": "FeatureCollection", "features": []}
    els = read_elements(fc)
    rows = [measure(project, e) for e in els]
    return {"scenario": scenario_id, "features": fc, "elements": rows, **check(project, els, rows, [])}


def apply(project: Project, scenario_id: str, fc: Dict[str, Any], action: Optional[str] = None,
          element_id: Optional[str] = None, before: Optional[Dict[str, Any]] = None,
          after: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Save the scenario's elements as drawn, carve them into the ground and check them (no SWMM)."""
    from ..hydrology.delineate import delineate
    from ..layout.apply import regrade

    if scenario_id == "baseline":
        raise ValueError("the existing site (baseline) has no elements.")
    tools = defaults(project)
    for f in fc.get("features", []):
        p = f.setdefault("properties", {})
        if not p.get("type") or not p.get("id"):
            raise ValueError(f"every element needs an id and a type ({p}).")
        try:   # a clear message for a malformed shape, before anything is saved
            g = shape(f.get("geometry") or {})
        except Exception as ex:
            raise ValueError(f"{p['id']}: its geometry is not valid GeoJSON ({ex}).")
        expect = {"polygon": ("Polygon", "MultiPolygon"), "line": ("LineString",), "point": ("Point",)}.get(TOOLS.get(p["type"], ""), None)
        if expect and g.geom_type not in expect:
            raise ValueError(f"{p['id']}: a {p['type'].replace('_', ' ')} is drawn as a {expect[0].lower()}, not a {g.geom_type}.")
        if g.geom_type in ("Polygon", "MultiPolygon") and (not g.is_valid or g.area < 1.0):
            raise ValueError(f"{p['id']}: the outline crosses itself or is smaller than 1 m2.")
        # sizes not given take the project's defaults, written onto the element so it says what was used
        for k, v in tools.get(p["type"], {}).get("defaults", {}).items():
            if p.get(k) is None:
                p[k] = v
        # suggested elements stay "proposal" until the designer changes them; the designer's own are locked
        p["source"] = "proposal" if p.get("source") == "proposal" else "designer"
        p["locked"] = p["source"] == "designer"
    if not project.exists("site/subcatchments.geojson"):   # the ground's drainage, needed to carve
        delineate(project)
    sc = f"scenarios/{scenario_id}/scenario.json"
    if not project.exists(sc):
        project.write_json(sc, Scenario(id=scenario_id, name="Design", status="draft",
                                        note="Elements placed by the designer.").model_dump(mode="json"))
    save_elements_fc(project, scenario_id, fc)
    project.locks.locked[scenario_id] = sorted({f["properties"]["id"] for f in fc.get("features", [])
                                                if f["properties"].get("source") != "proposal"})
    elements = read_elements(fc)
    if elements:
        rep = regrade(project, scenario_id, quick=True)
        warnings = rep["warnings"]
        cut = rep["cut_total_m3"]
        from ..nbs.components import load_elements

        elements = load_elements(project, scenario_id)   # as carved: a bridge's pool, invert, routing
    else:   # everything deleted: the scenario's ground is the existing ground again
        for rel in (f"scenarios/{scenario_id}/terrain/graded.tif", f"terrain/graded_{scenario_id}.tif",
                    f"scenarios/{scenario_id}/regrade_pending.json"):
            if project.exists(rel):
                project.path(rel).unlink()
        warnings, cut = [], 0.0
    rows = [measure(project, e) for e in elements]
    out = {"scenario": scenario_id, "elements": rows, "cut_m3": cut, **check(project, elements, rows, warnings)}
    from ..hydrology.flowmap import rel_for

    if project.exists(rel_for(scenario_id)):   # the flow map is redone on the carved ground when next asked for
        project.path(rel_for(scenario_id)).unlink()
    if action:
        log_ = EditLog.model_validate(project.read_json("edit_log.json")) if project.exists("edit_log.json") else EditLog()
        log_.entries.append(EditLogEntry(scenario=scenario_id, action=action, element_id=element_id,
                                         before=before, after=after))
        project.write_json("edit_log.json", log_.model_dump(mode="json"))
    project.history.log("design_edit", scenario=scenario_id, edit=action, element=element_id,
                        elements=len(elements))
    return out
