"""Re-grade an option from its current elements (after designer edits) and rebuild its subcatchments.

Used by the Rhino round trip and by `layout regrade`: nothing is placed or resized; every element
is carved into the existing ground as drawn, storage inverts are recomputed from the new rims, and
flow is traced again so each element receives its real contributing area. Keep-out areas are never
regraded (an element drawn over one is reported). Green bridges raise their swale to the crest and
pass the swale's outflow from pool to pool (see :func:`_green_bridges`).

``quick=True`` (each design edit while drawing) only carves and routes: the subcatchments, contours,
DXF and layout picture are redone by the full regrade that :func:`ensure_regraded` runs before SWMM.
The existing ground and its subcatchment raster are cached between edits (keyed on the files' times).
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from shapely import contains_xy

from ..grading.grade import Cut, grade
from ..hydrology import flow as fl
from ..nbs.components import NbSElement, has_elements, load_elements
from ..project import Project
from .generate import (STORAGE_TYPES, LayoutError, Placed, _grade_swale, _rebuild, _subcatchment_raster,
                       _write_outputs, keep_out, load_grid, surface_depth)


PENDING = "regrade_pending.json"   # in scenarios/<id>/: a quick regrade was done, the full one is owed
_cache: Dict[tuple, tuple] = {}


def _cached_grid(project: Project):
    """The existing ground grid and its subcatchment raster, reused while their files are unchanged."""
    def stamp(rel: str) -> float:
        return project.path(rel).stat().st_mtime if project.exists(rel) else 0.0

    key = (str(project.root), stamp("terrain/existing.tif"), stamp("site/boundary.geojson"),
           stamp("site/subcatchments.geojson"))
    if key not in _cache:
        for k in [k for k in _cache if k[0] == key[0]]:
            del _cache[k]
        g = load_grid(project)
        _cache[key] = (g, *_subcatchment_raster(project, g))
    return _cache[key]


def ensure_regraded(project: Project, option_id: str) -> None:
    """The full regrade (subcatchments, contours, drawings) if quick edits left it owed."""
    if project.exists(f"scenarios/{option_id}/{PENDING}") and has_elements(project, option_id):
        regrade(project, option_id)


def regrade(project: Project, option_id: str, quick: bool = False) -> Dict[str, Any]:
    P = project.parameters
    if not has_elements(project, option_id):
        raise LayoutError(f"scenario {option_id} has no elements.")
    elements: List[NbSElement] = load_elements(project, option_id)
    g, sub_lab, sub_props = _cached_grid(project)
    cell2 = g.cell ** 2
    blocked, _ = keep_out(project, g)
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
        elif e.type == "green_bridge":   # raised after every swale is carved (below)
            z0 = float(g.z[p.seed])
            p.cut = Cut(z0, z0, 0.0, 0.0, float(region.sum() * cell2))
            e.invert_elev_m, e.pool_area_m2 = round(z0, 3), 0.0   # until it is found on a swale
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
            free = region & ~blocked
            if not free.any():   # all of it lies on trees, paths or buildings: nothing is dug
                z0 = float(g.z[p.seed])
                p.cut = Cut(z0, z0, 0.0, 0.0, 0.0)
                warnings.append(f"{e.id} lies entirely on keep-out ground (trees, paths or buildings): it is not carved; "
                                "move it to open ground.")
            else:
                zg, p.cut = grade(zg, free, g.mask, g.cell, depth or surface_depth(P, e.type), side)
            if e.spec.is_storage:
                e.invert_elev_m = round(p.cut.bottom_m, 3)
        placed.append(p)

    bridges = _green_bridges(P, g, zg, elements, placed, warnings)   # bridge id -> (swale id, distance along it)
    for e in elements:   # a swale with bridges, and its bridges, are routed afresh below
        if e.id in bridges or e.id in {h for h, _ in bridges.values()}:
            e.outflow_to = e.overflow_to = None

    # routing: keep valid destinations, find one for elements without
    ids = {e.id for e in elements}
    outfalls = {str(p["outlet"]) for p in sub_props.values()}
    el_lab = np.zeros(g.mask.shape, int)
    for i, (e, p) in enumerate(zip(elements, placed), start=1):
        if e.type != "green_bridge":   # a bridge lies on its swale: the swale takes the water
            el_lab[p.region] = i
    rec = fl.downstream(g.dirs).ravel()
    for i, (e, p) in enumerate(zip(elements, placed), start=1):
        for f in ("outflow_to", "overflow_to"):
            v = getattr(e, f)
            if v and v not in ids and v not in outfalls:
                setattr(e, f, None)
        if e.outflow_to or e.overflow_to or e.id in bridges:
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

    # the swale's outflow passes through its bridges' pools, upstream first, then where the swale went
    chain: Dict[str, List] = {}
    for b, (host, s) in bridges.items():
        chain.setdefault(host, []).append((s, b))
    by_id = {e.id: e for e in elements}
    for host, bs in chain.items():
        order = [b for _, b in sorted(bs)]
        dest = by_id[host].outflow_to
        by_id[host].outflow_to = order[0]
        for a, b in zip(order, order[1:]):
            by_id[a].overflow_to = b
        # SWMM storage cannot spill into an LID: follow LIDs on to where they send their water
        seen = set()
        while dest in by_id and by_id[dest].spec.is_lid and dest not in seen:
            seen.add(dest)
            dest = by_id[dest].outflow_to
        by_id[order[-1]].overflow_to = dest

    if quick:
        _write_quick(project, option_id, g, zg, elements)
        cut = np.where(g.mask, g.dem.z - zg, 0.0)
        rep = {"option_id": option_id, "elements": [e.id for e in elements], "warnings": warnings,
               "cut_total_m3": float(cut[cut > 0].sum() * cell2), "quick": True}
        project.write_json(f"scenarios/{option_id}/{PENDING}", {"since": "design edit"})
        return rep

    sinks = np.zeros(g.mask.shape, bool)
    owner = np.zeros(g.mask.shape, object)
    for e, p in zip(elements, placed):
        if e.type == "green_bridge":
            continue
        sinks |= p.region
        owner[p.region] = e.id
    _existing_well_sinks(project, g, sinks, owner)
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
    project.write_json(f"scenarios/{option_id}/regrade_report.json", rep)
    if project.exists(f"scenarios/{option_id}/{PENDING}"):
        project.path(f"scenarios/{option_id}/{PENDING}").unlink()
    project.history.log("regrade", option=option_id, elements=len(elements))
    return rep


def _write_quick(project: Project, option_id: str, g, zg: np.ndarray, elements: List[NbSElement]) -> None:
    """What a design edit needs: the elements and the carved ground (the views and the flow map read it)."""
    from ..nbs.components import save_elements
    from ..terrain.raster import DEM, write_geotiff

    save_elements(project, option_id, elements)
    nod = g.dem.nodata
    graded = DEM(np.where(g.mask, zg, nod), g.cell, g.dem.origin, g.dem.crs, nod)
    write_geotiff(graded, project.path(f"scenarios/{option_id}/terrain/graded.tif"))
    write_geotiff(graded, project.path(f"terrain/graded_{option_id}.tif"))


def _green_bridges(P, g, zg: np.ndarray, elements: List[NbSElement], placed: List[Placed],
                   warnings: List[str]) -> Dict[str, tuple]:
    """Raise each green bridge's swale to its crest (in zg) and measure the pool behind it.

    The swale's bottom under the deck is lifted to bottom + crest height (never above the ground as it
    was); the pool is the swale's ground upstream of the bridge (the swale invert falls along its line)
    below the crest and connected to it. Sets the bridge's invert, pool area and weir length; returns
    bridge id -> (swale id, distance of the bridge along the swale's line)."""
    import shapely
    from scipy import ndimage
    from shapely.geometry import shape

    cell2 = g.cell ** 2
    swales = [(e, p) for e, p in zip(elements, placed) if e.type == "bioswale" and e.geometry["type"] == "LineString"]
    out: Dict[str, tuple] = {}
    for e, p in zip(elements, placed):
        if e.type != "green_bridge":
            continue
        line = shape(e.geometry)
        best = max(swales, key=lambda sp: line.intersection(sp[0].footprint()).length, default=None)
        if best is None or line.intersection(best[0].footprint()).length <= 0:
            continue   # reported by the design checks; holds nothing
        se, sp = best
        deck = p.region & sp.region
        if not deck.any():
            warnings.append(f"{e.id} is narrower than the ground model's cells on {se.id}; it is not raised.")
            continue
        cl = shape(se.geometry)
        x = line.intersection(cl)
        s_b = float(cl.project(x.centroid if not x.is_empty else line.centroid))
        h = float(e.dam_height_m or P.value("nbs.green_bridge.dam_height_m"))
        depth = float(se.max_ponding_depth_m or P.value("nbs.bioswale.max_ponding_depth_m"))
        h = min(h, depth)
        e.dam_height_m = round(h, 3)
        bottom = float(np.nanmin(zg[deck]))
        crest = bottom + h
        zg[deck] = np.maximum(zg[deck], np.minimum(crest, g.dem.z[deck]))
        rr, cc = np.nonzero(sp.region)
        st = shapely.line_locate_point(cl, shapely.points(g.X[rr, cc], g.Y[rr, cc]))
        up = np.zeros(g.mask.shape, bool)
        up[rr[st < s_b], cc[st < s_b]] = True
        wet = up & ~deck & (zg < crest)
        lab, _ = ndimage.label(wet, structure=np.ones((3, 3)))
        touch = ndimage.binary_dilation(deck, structure=np.ones((3, 3), bool)) & wet
        pool = np.isin(lab, np.unique(lab[touch])[np.unique(lab[touch]) > 0])
        if not pool.any():
            warnings.append(f"{e.id} holds no water: the swale bottom upstream of it is above its crest.")
        e.pool_area_m2 = round(float(pool.sum() * cell2), 2)
        e.invert_elev_m = round(bottom, 3)
        W = float(se.top_width_m or P.value("nbs.bioswale.top_width_m"))
        z = float(se.side_slope_h_v or P.value("nbs.bioswale.side_slope_h_v"))
        e.weir_length_m = round(max(W - 2 * z * depth, 0.3), 2)   # water spills over the swale's bottom width
        p.cut = Cut(crest, bottom, 0.0, 0.0, float(deck.sum() * cell2))
        out[e.id] = (se.id, s_b)
    return out


def _existing_well_sinks(project: Project, g, sinks: np.ndarray, owner: np.ndarray) -> None:
    """The existing recharge wells stay sinks on the graded ground, so each keeps its catchment SC_<id>
    (where a design element covers a well's cell, the element takes the water)."""
    from ..site import wells

    for wid, rc in wells.sink_cells(project, g.X, g.Y, g.mask):
        if not sinks[rc]:
            sinks[rc] = True
            owner[rc] = wid
