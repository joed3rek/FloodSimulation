"""Re-grade an option from its current elements (after designer edits) and rebuild its subcatchments.

Used by the Rhino round trip and by `layout regrade`: nothing is placed or resized; every element
is carved into the existing ground as drawn, storage inverts are recomputed from the new rims, and
flow is traced again so each element receives its real contributing area. Keep-out areas are never
regraded (an element drawn over one is reported).
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from shapely import contains_xy

from ..grading.grade import Cut, grade
from ..hydrology import flow as fl
from ..nbs.components import NbSElement, read_elements
from ..project import Project
from .generate import (STORAGE_TYPES, LayoutError, Placed, _grade_swale, _rebuild, _subcatchment_raster,
                       _write_outputs, keep_out, load_grid, surface_depth)


def regrade(project: Project, option_id: str) -> Dict[str, Any]:
    P = project.parameters
    rel = f"options/{option_id}/components.geojson"
    if not project.exists(rel):
        raise LayoutError(f"option {option_id} has no components.")
    elements: List[NbSElement] = read_elements(project.read_geojson(rel))
    g = load_grid(project)
    cell2 = g.cell ** 2
    blocked, _ = keep_out(project, g)
    sub_lab, sub_props = _subcatchment_raster(project, g)
    zg = np.where(g.mask, g.dem.z, np.nan)
    placed: List[Placed] = []
    warnings: List[str] = []
    for e in elements:
        fp = e.footprint()
        region = contains_xy(fp, g.X, g.Y) & g.mask
        if not region.any():
            c = fp.centroid
            d = np.where(g.mask, np.hypot(g.X - c.x, g.Y - c.y), np.inf)
            region = np.zeros(g.mask.shape, bool)
            region[np.unravel_index(int(np.argmin(d)), d.shape)] = True
        over = float((region & blocked).sum() * cell2)
        if over > 0.5:
            warnings.append(f"{e.id} covers {over:.0f} m2 of keep-out area; that part is not regraded.")
        seed = np.unravel_index(int(np.nanargmin(np.where(region, g.z, np.nan))), region.shape)
        p = Placed(e.id, e.type, region, (int(seed[0]), int(seed[1])), 0.0, 0.0, 0.0, "designer")
        if e.type == "bioswale" and e.geometry["type"] == "LineString":
            p.notes.append({"line": e.geometry})
            p.estimate_m3 = float(e.storage_volume_m3 or 0.0)
            zg, p.cut = _grade_swale(zg, g, p, P, blocked)
        elif e.type == "recharge_well":
            z0 = float(g.z[p.seed])
            depth = float(e.well_depth_m or P.value("nbs.recharge_well.depth_m"))
            p.cut = Cut(z0, z0 - depth, 0.0, 0.0, float(region.sum() * cell2))
            e.invert_elev_m = round(z0 - depth, 3)
        else:
            depth = float(e.max_ponding_depth_m or P.value(f"nbs.{e.type}.max_ponding_depth_m")) \
                + (float(e.permanent_pool_depth_m or P.value_or(f"nbs.{e.type}.permanent_pool_depth_m", 0.0) or 0.0)
                   if e.type in ("retention_pond", "constructed_wetland") else 0.0)
            side = None if e.type == "rain_garden" else (e.side_slope_h_v or P.value_or(f"nbs.{e.type}.side_slope_h_v", None))
            zg, p.cut = grade(zg, region & ~blocked, g.mask, g.cell, depth or surface_depth(P, e.type), side)
            if e.spec.is_storage:
                e.invert_elev_m = round(p.cut.bottom_m, 3)
        placed.append(p)

    # routing: keep valid destinations, find one for elements without
    ids = {e.id for e in elements}
    outfalls = {str(p["outlet"]) for p in sub_props.values()}
    el_lab = np.zeros(g.mask.shape, int)
    for i, p in enumerate(placed, start=1):
        el_lab[p.region] = i
    rec = fl.downstream(g.dirs).ravel()
    for i, (e, p) in enumerate(zip(elements, placed), start=1):
        for f in ("outflow_to", "overflow_to"):
            v = getattr(e, f)
            if v and v not in ids and v not in outfalls:
                setattr(e, f, None)
        if e.outflow_to or e.overflow_to:
            continue
        j = np.ravel_multi_index(p.seed, g.mask.shape)
        target = None
        for _ in range(g.mask.size):
            j = rec[j]
            if j < 0:
                break
            k = el_lab.ravel()[j]
            if k and k != i:
                q = elements[k - 1]
                if (e.type not in STORAGE_TYPES or q.type in STORAGE_TYPES) and (q.type != "rain_garden" or e.type == "rain_garden"):
                    target = q.id
                    break
        dest = target or str(sub_props[int(sub_lab[p.seed])]["outlet"])
        if e.spec.is_storage:
            e.overflow_to = dest
            if e.type == "detention_pond":
                e.outflow_to = dest
        else:
            e.outflow_to = dest

    sinks = np.zeros(g.mask.shape, bool)
    owner = np.zeros(g.mask.shape, object)
    for e, p in zip(elements, placed):
        sinks |= p.region
        owner[p.region] = e.id
    subs, sub_rows = _rebuild(project, g, zg, sinks, owner, sub_lab, sub_props)
    names = {s["properties"]["id"] for s in subs}
    for e in elements:
        e.inflow_from = [f"SC_{e.id}"] if f"SC_{e.id}" in names else []
        # resolved values are recomputed by the next SWMM run
        e.area_m2 = e.storage_volume_m3 = e.drawdown_time_hr = e.contributing_area_m2 = None
    _write_outputs(project, option_id, g, zg, elements, placed, subs, blocked)
    cut = np.where(g.mask, g.dem.z - zg, 0.0)
    rep = {"option_id": option_id, "elements": [e.id for e in elements], "warnings": warnings,
           "cut_total_m3": float(cut[cut > 0].sum() * cell2), "subcatchments": sub_rows}
    project.write_json(f"options/{option_id}/regrade_report.json", rep)
    project.history.log("regrade", option=option_id, elements=len(elements))
    return rep
