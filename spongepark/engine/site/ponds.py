"""Existing ponds: found on the survey's water layer, shown as water, and part of the flood model as storage.

The survey gives a pond's outline but rarely its bottom: levels are taken on the bank or on the water surface.
So the ground model runs flat across a pond and stores nothing there. The designer gives, for each pond in the
park, how deep it is from its edge (where it overflows) to the bottom, and how deep the water in it usually
stands. The difference is the room it has for a storm. It is cut into the ground model below the edge level,
so the flow analysis (flow lines end in it, a ponding hotspot), the 2D flood model and SWMM (a depression,
hence storage) all see it. A pond without answers is shown but left out of the flood model, and the designer
is told so. Nothing is assumed.

- ``site/ponds.geojson``: one feature per pond (id, area, edge level, inside the park or not, the answers);
- ``terrain/existing_surveyed.tif``: the ground model as surveyed (kept once; the cut is redone from it).
"""

from __future__ import annotations

import logging
import shutil
from typing import Any, Dict, List, Optional

import numpy as np

from ..project import Project
from ..terrain.raster import read_geotiff, write_geotiff

log = logging.getLogger(__name__)

REL = "site/ponds.geojson"
SURVEYED = "terrain/existing_surveyed.tif"
GROUND = "terrain/existing.tif"
MIN_POND_M2 = 4.0          # smaller closed shapes on the water layer are symbols, not ponds
CLOSE_GAP_M = 1.5          # an outline whose ends are this close is closed


def outlines(pieces) -> List[Any]:
    """Pond polygons from the water layer's lines: closed outlines, or outlines whose ends nearly meet."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union

    polys, open_lines = [], []
    for g, geo, info in pieces:
        if g != "line" or len(geo) < 3:
            continue
        xy = np.asarray(geo, dtype=float)
        if info.get("closed") or np.hypot(*(xy[0] - xy[-1])) <= CLOSE_GAP_M:
            p = Polygon(xy).buffer(0)
            if p.area >= MIN_POND_M2:
                polys.append(p)
        else:
            open_lines.append(LineString(xy))
    if open_lines:   # outlines drawn in pieces
        polys += [p for p in polygonize(unary_union(open_lines)) if p.area >= MIN_POND_M2]
    merged = unary_union(polys) if polys else None
    if merged is None:
        return []
    return list(merged.geoms) if hasattr(merged, "geoms") else [merged]


def record(project: Project, polys, ground, park) -> List[Dict[str, Any]]:
    """Write site/ponds.geojson for the ponds found (keeping earlier answers for the same pond)."""
    old = {f["properties"]["id"]: f["properties"] for f in load(project)}
    feats = []
    for i, poly in enumerate(sorted(polys, key=lambda p: -p.area)):
        ring = np.asarray(poly.exterior.coords)
        edge = ground(ring[:, 0], ring[:, 1])
        pid = f"POND{i + 1}"
        # the edge's low point: where the pond overflows (a low percentile, so one odd level does not decide it)
        props = {"id": pid, "area_m2": round(float(poly.area), 1), "edge_level_m": round(float(np.percentile(edge, 5)), 3),
                 "in_park": bool(park is not None and park.intersects(poly))}
        prev = old.get(pid)
        if prev and abs(prev.get("area_m2", 0) - props["area_m2"]) < 0.5:
            for k in ("depth_m", "water_m"):
                if prev.get(k) is not None:
                    props[k] = prev[k]
        feats.append({"type": "Feature", "geometry": poly.__geo_interface__, "properties": props})
    project.write_geojson(REL, {"type": "FeatureCollection", "features": feats})
    return feats


def load(project: Project) -> List[Dict[str, Any]]:
    return project.read_geojson(REL).get("features", []) if project.exists(REL) else []


def status(project: Project) -> List[Dict[str, Any]]:
    """Each pond in the park and whether it is in the flood model (the questions to ask)."""
    from . import survey_layers

    if project.exists("terrain/existing.tif") and any(project.path("survey").glob("*_SP.dxf"))             if project.exists("survey") else False:
        survey_layers.load(project)   # (re)builds the layers, and with them the ponds, when out of date
    out = []
    for f in load(project):
        p = dict(f["properties"])
        if not p.get("in_park"):
            continue
        p["in_model"] = _ready(p)
        p["storage_m3"] = p.get("room_m3") if p["in_model"] else None
        out.append(p)
    return out


def _ready(p: Dict[str, Any]) -> bool:
    d, w = p.get("depth_m"), p.get("water_m")
    return d is not None and w is not None and d > 0 and 0 <= w <= d


def apply(project: Project, answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Save the ponds' depths and cut each pond's room for a storm into the ground model (redone from the
    surveyed ground each time). ``answers``: [{"id", "depth_m", "water_m"}]."""
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    from shapely.geometry import shape

    fc = project.read_geojson(REL) if project.exists(REL) else {"features": []}
    by_id = {f["properties"]["id"]: f for f in fc["features"]}
    for a in answers or []:
        f = by_id.get(a.get("id"))
        if f is None:
            raise ValueError(f"no pond {a.get('id')} in this project.")
        d = a.get("depth_m")
        w = a.get("water_m", 0 if d is not None else None)
        d = None if d in (None, "") else float(d)
        w = None if w in (None, "") else float(w)
        if d is not None and d <= 0:
            raise ValueError(f"{a['id']}: the depth must be more than 0 m.")
        if d is not None and w is not None and not 0 <= w <= d:
            raise ValueError(f"{a['id']}: the usual water depth must be between 0 and the pond's depth ({d:g} m).")
        f["properties"]["depth_m"] = d
        f["properties"]["water_m"] = w

    if not project.exists(SURVEYED):
        shutil.copy2(project.path(GROUND), project.path(SURVEYED))
    dem = read_geotiff(project.path(SURVEYED))
    z = dem.z.copy()
    valid = z != dem.nodata
    transform = from_origin(dem.origin[0], dem.origin[1], dem.cell_size, dem.cell_size)
    cut_m3 = 0.0
    used = []
    for f in fc["features"]:
        p = f["properties"]
        if not p.get("in_park") or not _ready(p):
            continue
        room = p["depth_m"] - p["water_m"]
        p["room_m3"] = 0.0
        if room <= 0:
            used.append(p["id"])   # full to the brim: no room, flow passes over it
            continue
        inside = ~geometry_mask([shape(f["geometry"])], out_shape=z.shape, transform=transform) & valid
        bottom = p["edge_level_m"] - room
        new = np.minimum(z[inside], bottom)
        cut_m3 += float((z[inside] - new).sum()) * dem.cell_size ** 2
        # its room for a storm: the volume below the overflow level
        p["room_m3"] = round(float(np.clip(p["edge_level_m"] - new, 0, None).sum()) * dem.cell_size ** 2, 1)
        z[inside] = new
        used.append(p["id"])
    project.write_geojson(REL, fc)
    dem.z = z
    write_geotiff(dem, project.path(GROUND))
    project.history.log("ponds", ponds=used, room_m3=round(cut_m3, 1))
    _refresh(project)
    return {"ponds": status(project), "room_m3": round(cut_m3, 1)}


def _refresh(project: Project) -> None:
    """The ground changed: drainage, flow lines and the design's carved ground are redone on it."""
    from ..hydrology import flowmap
    from ..hydrology.delineate import delineate

    if project.exists("site/subcatchments.geojson") or project.exists("terrain/flow/accumulation_m2.tif"):
        delineate(project)
        flowmap.analyse(project)
    try:
        from ..design import edit

        cur = edit.current(project, "design")
        if cur and cur.get("features", {}).get("features"):
            edit.apply(project, "design", cur["features"])
    except Exception as ex:   # the design is redone on its next edit
        log.warning("design ground not redone after the pond change: %s", ex)
