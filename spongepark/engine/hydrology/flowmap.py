"""Where water goes on the existing ground: flow lines, flow arrows and ponding hotspots.

Worked out from the ground model alone (no rainfall or soil data): the D8 flow directions and
accumulation from :mod:`.delineate`, and the natural depressions sink filling finds. This is the
"flow pattern" map a designer reads before choosing where interventions go; the storm simulation
(:mod:`..sim2d`) adds how deep and for how long, and needs rainfall and infiltration.

Written to ``site/flow_analysis.json``:

- ``flow_lines``: the main flow paths (cells draining at least ``min_line_area_m2``), with the area
  draining to each point, so a viewer can draw bigger flows wider;
- ``arrows``: flow direction on a regular spacing (downhill on the smoothed ground);
- ``hotspots``: depressions where water collects (outline, deepest point, depth, volume, the level
  water fills to), largest first, and the exits where flow leaves the surveyed park.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from ..project import Project
from ..terrain.raster import read_geotiff
from . import flow as fl

log = logging.getLogger(__name__)

REL = "site/flow_analysis.json"
VERSION = 2


def _ensure_flow(project: Project) -> None:
    if not project.exists("terrain/flow/accumulation_m2.tif") or not project.exists("site/subcatchments.geojson"):
        from .delineate import delineate

        delineate(project)


def rel_for(scenario: Optional[str]) -> str:
    return REL if not scenario or scenario == "baseline" else f"scenarios/{scenario}/flow_analysis.json"


def analyse(project: Project, min_line_area_m2: float = 40.0, arrow_spacing_m: float = 3.0,
            scenario: Optional[str] = None) -> Dict[str, Any]:
    """Flow on the existing ground, or (``scenario``) on a scenario's carved ground: its NbS elements hold
    water where they are carved, so flow lines end in them and their basins are marked as storage."""
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from scipy import ndimage
    from shapely.geometry import LineString, shape
    from shapely.ops import linemerge, unary_union

    _ensure_flow(project)
    dem = read_geotiff(project.path("terrain/existing.tif"))
    acc_r = read_geotiff(project.path("terrain/flow/accumulation_m2.tif"))
    filled_r = read_geotiff(project.path("terrain/flow/filled.tif"))
    dep_r = read_geotiff(project.path("terrain/flow/depression_depth.tif"))
    mask = acc_r.z != acc_r.nodata
    cell = acc_r.cell_size
    z = np.where(mask, dem.z, np.nan)
    acc = np.where(mask, acc_r.z, 0.0)
    filled = np.where(mask, filled_r.z, np.nan)
    X, Y = acc_r.cell_centres()
    graded_rel = f"scenarios/{scenario}/terrain/graded.tif" if scenario and scenario != "baseline" else None
    if graded_rel and project.exists(graded_rel):
        g = read_geotiff(project.path(graded_rel))
        if g.z.shape == mask.shape:   # same grid as the existing ground: work out the flow on the carved ground
            z = np.where(mask & (g.z != g.nodata), g.z, np.nan)
            m2 = mask & np.isfinite(z)
            filled = fl.fill_sinks(z, m2)
            acc = np.where(m2, fl.accumulation(filled, m2, fl.d8_directions(filled, m2)) * cell * cell, 0.0)
            min_d = float(project.parameters.value_or("terrain.min_depression_depth_m", 0.02))
            d = np.where(m2, filled - z, 0.0)
            dep_r = type(dep_r)(z=np.where(d >= min_d, d, 0.0), cell_size=cell, origin=acc_r.origin, crs=acc_r.crs,
                                nodata=-9999.0)
            mask = m2

    # ---- main flow lines
    dirs = fl.d8_directions(filled, mask)
    thr = max(min_line_area_m2, float(np.percentile(acc[mask], 90)) if mask.any() else min_line_area_m2)
    stream = mask & (acc >= thr)
    segs = []
    for r, c in zip(*np.nonzero(stream)):
        k = dirs[r, c]
        if k < 0:
            continue
        dr, dc = fl.D8[k]
        r2, c2 = r + dr, c + dc
        if 0 <= r2 < mask.shape[0] and 0 <= c2 < mask.shape[1] and stream[r2, c2]:
            segs.append(LineString([(X[r, c], Y[r, c]), (X[r2, c2], Y[r2, c2])]))
    merged = linemerge(segs) if segs else None
    lines = [] if merged is None else list(getattr(merged, "geoms", [merged]))
    flow_lines = []
    for ln in lines:
        if ln.length < 2 * cell:
            continue
        ln = ln.simplify(cell * 0.3)
        xy = np.asarray(ln.coords)
        rr = np.clip(((acc_r.origin[1] - xy[:, 1]) / cell).astype(int), 0, mask.shape[0] - 1)
        cc = np.clip(((xy[:, 0] - acc_r.origin[0]) / cell).astype(int), 0, mask.shape[1] - 1)
        zz = np.nan_to_num(z[rr, cc], nan=float(np.nanmin(z)))
        flow_lines.append({"xyz": np.round(np.c_[xy, zz], 3).ravel().tolist(),
                           "area_m2": np.round(acc[rr, cc], 1).tolist()})
    flow_lines.sort(key=lambda f: -max(f["area_m2"]))

    # ---- arrows: downhill on the ground smoothed over about a metre
    zs = ndimage.gaussian_filter(np.where(mask, z, np.nanmean(z)), sigma=max(1.0, 1.0 / cell))
    gy, gx = np.gradient(zs, cell)   # rows run north to south: +gy means the ground rises southward
    step = max(1, int(round(arrow_spacing_m / cell)))
    arrows = []
    for r in range(step // 2, mask.shape[0], step):
        for c in range(step // 2, mask.shape[1], step):
            if not mask[r, c]:
                continue
            dx, dy = -gx[r, c], gy[r, c]            # downhill, in plan (x east, y north)
            s = float(np.hypot(dx, dy))
            if s < 1e-4:                            # flat: no direction worth showing
                continue
            arrows.append([round(float(X[r, c]), 2), round(float(Y[r, c]), 2), round(float(z[r, c]), 3),
                           round(float(dx / s), 3), round(float(dy / s), 3), round(100 * s, 2)])

    # ---- hotspots: depressions where water collects, and where it leaves the park
    depth = np.where(mask, dep_r.z, 0.0)
    depth = np.where(depth == dep_r.nodata, 0.0, depth)
    lab, n = ndimage.label(depth > 0, structure=np.ones((3, 3)))
    t = from_origin(acc_r.origin[0], acc_r.origin[1], cell, cell)
    polys: Dict[int, Any] = {}
    for geom, v in shapes(lab.astype("int32"), mask=lab > 0, transform=t):
        polys.setdefault(int(v), []).append(shape(geom))
    hot = []
    for k in range(1, n + 1):
        m = lab == k
        if not m.any():
            continue
        i = np.argmax(np.where(m, depth, -1))
        r, c = np.unravel_index(i, m.shape)
        poly = unary_union(polys.get(k, [])).simplify(cell * 0.3)
        level = float(np.nanmax(np.where(m, filled, np.nan)))
        outline = poly if poly.geom_type == "Polygon" else max(getattr(poly, "geoms", [poly]), key=lambda g: g.area)
        catch = float(acc[r, c])
        hot.append({"kind": "ponding", "area_m2": round(float(m.sum() * cell * cell), 1),
                    "max_depth_m": round(float(depth[m].max()), 3),
                    "volume_m3": round(float(depth[m].sum() * cell * cell), 2),
                    "water_level_m": round(level, 3), "draining_area_m2": round(catch, 1),
                    "x": round(float(X[r, c]), 2), "y": round(float(Y[r, c]), 2), "z": round(float(z[r, c]), 3),
                    "outline": np.round(np.asarray(outline.exterior.coords), 2).ravel().tolist()})
    # in a carved scenario, water held in an NbS element is storage, not a flooding hotspot
    if scenario and scenario != "baseline":
        from shapely.geometry import Point
        from shapely.ops import unary_union as _union

        from ..nbs.components import has_elements, load_elements

        if has_elements(project, scenario):
            fps = _union([e.footprint().buffer(0.75) for e in load_elements(project, scenario)])
            for h in hot:
                if fps.contains(Point(h["x"], h["y"])):
                    h["kind"] = "nbs_storage"
    hot.sort(key=lambda h: (h["kind"] != "ponding", -h["volume_m3"]))
    for i, h in enumerate(hot, start=1):
        h["id"] = f"H{i}" if h["kind"] == "ponding" else f"S{i}"
    exits = []
    if project.exists("site/outfalls.geojson"):
        rep = project.read_json("terrain/flow/report.json") if project.exists("terrain/flow/report.json") else {}
        area_by_out = {r_["outfall"]: r_["area_m2"] for r_ in rep.get("subcatchments", [])}
        for f in project.read_geojson("site/outfalls.geojson")["features"]:
            x, y = f["geometry"]["coordinates"][:2]
            exits.append({"id": f["properties"]["id"], "kind": "exit", "x": round(x, 2), "y": round(y, 2),
                          "z": f["properties"].get("invert_elev_m"),
                          "draining_area_m2": round(float(area_by_out.get(f["properties"]["id"], 0.0)), 1)})
    if graded_rel:   # how much of the carved ground still drains to each exit
        for e in exits:
            c = int(np.clip((e["x"] - acc_r.origin[0]) / cell, 0, mask.shape[1] - 1))
            r = int(np.clip((acc_r.origin[1] - e["y"]) / cell, 0, mask.shape[0] - 1))
            win = acc[max(0, r - 2):r + 3, max(0, c - 2):c + 3]
            e["draining_area_m2"] = round(float(win.max()) if win.size else 0.0, 1)
    exits.sort(key=lambda e: -e["draining_area_m2"])

    out = {"version": VERSION, "cell_m": cell, "min_line_area_m2": thr,
           "flow_lines": flow_lines, "arrows": arrows, "hotspots": hot, "exits": exits,
           "scenario": scenario or "baseline",
           "summary": {"hotspots": sum(1 for h in hot if h["kind"] == "ponding"),
                       "ponding_volume_m3": round(sum(h["volume_m3"] for h in hot if h["kind"] == "ponding"), 2),
                       "nbs_storage_m3": round(sum(h["volume_m3"] for h in hot if h["kind"] != "ponding"), 2),
                       "deepest_m": max((h["max_depth_m"] for h in hot if h["kind"] == "ponding"), default=0.0),
                       "exits": len(exits)},
           "notes": ["From the ground model alone: where water runs and where it collects. How deep and for "
                     "how long comes from the storm simulation, which needs rainfall and infiltration.",
                     "Water leaves wherever flow reaches the edge of the surveyed park; walls and gates are "
                     "not modelled yet."]}
    project.write_json(rel_for(scenario), out)
    project.history.log("flow_analysis", hotspots=len(hot), exits=len(exits))
    return out


def load(project: Project, rebuild: bool = False, scenario: Optional[str] = None) -> Dict[str, Any]:
    rel = rel_for(scenario)
    if rebuild or not project.exists(rel) or project.read_json(rel).get("version") != VERSION:
        return analyse(project, scenario=scenario)
    return project.read_json(rel)
