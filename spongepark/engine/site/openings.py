"""Inlets and outlets the designer places on the site (Site setup > Inlets and outlets).

The drainage finds where the ground runs to the edge (:mod:`.outfalls`); this is the other half: where water can really
get in and out, which only the designer knows. Nothing here is assumed, so each one says:

- ``kind``: ``outlet`` (water leaves; on the site's edge, it is moved to the nearest point of it) or ``inlet`` (water
  from outside comes in);
- ``origin``: ``site`` (an existing site condition: in every run) or ``design`` (part of the design: in design runs only;
  in a project built from a design model every run is the design);
- an outlet's ``width_m`` and ``invert_m``: the level water leaves at, on the survey's own datum (the invert or bottom
  level many surveys mark at an outlet), so it may be below the ground beside it (a drain) or above it (a sill) with
  no sign to work out. Saved with ``ground_m`` (the ground there) and ``sill_m`` (invert minus ground; negative when
  below it). An old row with only ``sill_m`` (height above the ground) still reads as ground + sill;
- an inlet's ``area_m2`` draining to it and ``runoff_pct`` of the rain on that area that arrives.

``site/openings.json``: ``{"openings": [...], "confirmed": bool}``; ``confirmed`` is the designer saying the list is
complete (it may be empty: no way in or out).

The storm model cuts each outlet through the edge at its sill and adds each inlet's water at its cell. The SWMM run
counts an outlet through the exit whose catchment it lies in (:func:`outlet_levels`); inlets are not in the SWMM run yet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..project import Project

REL = "site/openings.json"
KINDS = ("outlet", "inlet")
ORIGINS = ("site", "design")
SNAP_M = 5.0     # a click this close to the site counts as on it
MODEL_SOURCE = "site/model_source.json"
LEVEL_MARGIN_M = 5.0   # an outlet level this far outside the site's ground levels is not on the survey's datum
DEM_REL = "terrain/existing.tif"


def _dem(project: Project):
    from ..terrain.raster import read_geotiff

    return read_geotiff(project.path(DEM_REL)) if project.exists(DEM_REL) else None


def ground_range(dem) -> Optional[List[float]]:
    """The lowest and highest ground on the site (m, survey datum)."""
    if dem is None:
        return None
    z = dem.z[dem.z != dem.nodata]
    return [round(float(z.min()), 3), round(float(z.max()), 3)] if z.size else None


def outlet_ground(dem, x: float, y: float, width_m: float = 0.0) -> Optional[float]:
    """The ground an outlet opens from: the lowest within its width (at least two cells) of the point, so an outlet in
    a boundary wall reads the ground beside the wall, not the wall's top."""
    if dem is None:
        return None
    X, Y = dem.cell_centres()
    near = (dem.z != dem.nodata) & (np.hypot(X - x, Y - y) <= max(float(width_m) / 2, 2 * dem.cell_size))
    return float(dem.z[near].min()) if near.any() else _ground_at(dem, x, y)


def snap(project: Project, x: float, y: float, kind: str = "outlet", width_m: float = 0.0) -> Dict[str, Any]:
    """Where a click puts an opening (an outlet onto the site's edge) and the ground there, for the app's form."""
    from shapely.geometry import Point
    from shapely.ops import nearest_points

    boundary = _boundary(project)
    p = Point(x, y)
    if boundary is not None:
        p = nearest_points(boundary.exterior if kind == "outlet" else boundary, p)[0] if (kind == "outlet" or boundary.distance(p) > 0) else p
    dem = _dem(project)
    g = outlet_ground(dem, p.x, p.y, width_m) if kind == "outlet" else (_ground_at(dem, p.x, p.y) if dem is not None else None)
    return {"x": round(p.x, 2), "y": round(p.y, 2), "ground_m": None if g is None else round(g, 3),
            "ground_range_m": ground_range(dem)}


def invert_of(o: Dict[str, Any], ground: Optional[float]) -> Optional[float]:
    """The level an outlet lets water out at: its own invert, or (an old row) the ground plus its sill."""
    if o.get("invert_m") is not None:
        return float(o["invert_m"])
    return None if ground is None else ground + float(o.get("sill_m") or 0.0)


def _boundary(project: Project):
    from shapely.geometry import shape
    from shapely.ops import unary_union

    if not project.exists("site/boundary.geojson"):
        return None
    features = project.read_geojson("site/boundary.geojson")["features"]
    return unary_union([shape(f["geometry"]) for f in features]) if features else None


def load(project: Project) -> Dict[str, Any]:
    return project.read_json(REL) if project.exists(REL) else {"openings": [], "confirmed": False}


def status(project: Project) -> Dict[str, Any]:
    """The list, and gaps seen in a modelled boundary wall that nobody has said anything about yet."""
    st = load(project)
    gaps: List[Dict[str, Any]] = []
    if project.exists("terrain/qc.json"):
        wall = project.read_json("terrain/qc.json").get("wall") or {}
        for g in wall.get("openings", []):
            if not any(np.hypot(o["x"] - g["x"], o["y"] - g["y"]) <= max(SNAP_M, g["width_m"]) for o in st["openings"]):
                gaps.append(g)
    return {**st, "gaps": gaps, "from_model": project.exists(MODEL_SOURCE), "ground_range_m": ground_range(_dem(project)),
            "question": "Where does water enter or leave this site? Place each inlet and outlet, and say whether it is an "
                        "existing site condition or part of the design. Everywhere else the edge holds the water."}


def _check(a: Dict[str, Any], i: int, boundary, dem=None) -> Dict[str, Any]:
    from shapely.geometry import Point
    from shapely.ops import nearest_points

    who = f"{a.get('kind') or 'opening'} {i + 1}"
    kind, origin = a.get("kind"), a.get("origin")
    if kind not in KINDS:
        raise ValueError(f"{who}: say whether it is an outlet or an inlet.")
    if origin not in ORIGINS:
        raise ValueError(f"{who}: say whether it is an existing site condition or part of the design.")
    try:
        p = Point(float(a["x"]), float(a["y"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"{who}: place it on the site.")
    if boundary is not None:
        d = boundary.distance(p)
        if d > SNAP_M:
            raise ValueError(f"{who}: it is {d:.0f} m outside the site; place it on the site.")
        if kind == "outlet":
            if boundary.exterior.distance(p) > SNAP_M:
                raise ValueError(f"{who}: an outlet goes on the edge of the site; this is "
                                 f"{boundary.exterior.distance(p):.0f} m from it.")
            p = nearest_points(boundary.exterior, p)[0]
        elif d > 0:
            p = nearest_points(boundary, p)[0]
    out = {"id": a.get("id") or f"{kind.upper()}_{i + 1}", "kind": kind, "origin": origin,
           "x": round(p.x, 2), "y": round(p.y, 2), "name": str(a.get("name") or "")}

    def number(key, label, lo, hi=None, open_lo=False):
        v = a.get(key)
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{who}: give the {label}.")
        if v < lo or (open_lo and v == lo) or (hi is not None and v > hi):
            raise ValueError(f"{who}: the {label} cannot be {v:g}.")
        return v

    if kind == "outlet":
        out["width_m"] = number("width_m", "width of the outlet (m)", 0.0, open_lo=True)
        ground = outlet_ground(dem, p.x, p.y, out["width_m"])
        if a.get("invert_m") is not None and a.get("invert_m") != "":
            invert = number("invert_m", "level of the outlet (m, on the survey's levels)", -1e6)
            span = ground_range(dem)
            if span and not (span[0] - LEVEL_MARGIN_M <= invert <= span[1] + LEVEL_MARGIN_M):
                raise ValueError(f"{who}: {invert:g} m is not a level on this site's survey, whose ground runs from "
                                 f"{span[0]:.2f} to {span[1]:.2f} m. Give the outlet's level on the same levels "
                                 f"(its invert or bottom level), not its height above the ground.")
        else:   # an old row: height above the ground
            sill = number("sill_m", "level of the outlet (m, on the survey's levels)", 0.0)
            invert = (ground or 0.0) + sill
        out["invert_m"] = round(invert, 3)
        if ground is not None:
            out["ground_m"] = round(ground, 3)
            out["sill_m"] = round(invert - ground, 3)
        else:
            out["sill_m"] = round(float(a.get("sill_m") or 0.0), 3)
    else:
        out["area_m2"] = number("area_m2", "area draining to the inlet (m2)", 0.0, open_lo=True)
        out["runoff_pct"] = number("runoff_pct", "share of the rain on that area that arrives (%)", 0.0, 100.0, open_lo=True)
    return out


def save(project: Project, body: Dict[str, Any]) -> Dict[str, Any]:
    boundary = _boundary(project)
    dem = _dem(project)
    rows = [_check(a, i, boundary, dem) for i, a in enumerate(body.get("openings") or [])]
    ids = [r["id"] for r in rows]
    for i, r in enumerate(rows):   # a copy made in the app comes without an id, or with its original's
        if ids.count(r["id"]) > 1 and ids.index(r["id"]) != i:
            n = 1
            while f"{r['kind'].upper()}_{n}" in ids:
                n += 1
            r["id"] = ids[i] = f"{r['kind'].upper()}_{n}"
    project.write_json(REL, {"openings": rows, "confirmed": bool(body.get("confirmed"))})
    project.history.log("openings", outlets=sum(o["kind"] == "outlet" for o in rows),
                        inlets=sum(o["kind"] == "inlet" for o in rows), confirmed=bool(body.get("confirmed")))
    return status(project)


def active(project: Project, option: Optional[str] = None) -> List[Dict[str, Any]]:
    """The openings in this run. Design ones are only in design runs; a design model's project is all design."""
    rows = load(project)["openings"]
    if project.exists(MODEL_SOURCE) or (option and option != "baseline"):
        return rows
    return [o for o in rows if o["origin"] == "site"]


def _ground_at(dem, x: float, y: float) -> Optional[float]:
    X, Y = dem.cell_centres()
    d = np.where(dem.z != dem.nodata, np.hypot(X - x, Y - y), np.inf)
    i = np.unravel_index(int(np.argmin(d)), d.shape)
    return float(dem.z[i]) if np.isfinite(d[i]) else None


def outlet_levels(project: Project, option: Optional[str] = None) -> Dict[str, float]:
    """Exit id -> the lowest level water leaves at through an outlet in that exit's catchment."""
    from shapely.geometry import Point, shape

    from ..terrain.raster import read_geotiff

    outs = [o for o in active(project, option) if o["kind"] == "outlet"]
    if not outs or not project.exists("site/subcatchments.geojson") or not project.exists("terrain/existing.tif"):
        return {}
    subs = [(f["properties"].get("outlet"), shape(f["geometry"])) for f in project.read_geojson("site/subcatchments.geojson")["features"]]
    if not subs:
        return {}
    dem = read_geotiff(project.path("terrain/existing.tif"))
    levels: Dict[str, float] = {}
    for o in outs:
        p = Point(o["x"], o["y"])
        exit_id = min(subs, key=lambda s: s[1].distance(p))[0]
        level = invert_of(o, outlet_ground(dem, o["x"], o["y"], float(o.get("width_m") or 0.0)))
        if exit_id and level is not None:
            levels[exit_id] = min(levels.get(exit_id, level), level)
    return levels


def inlet_cells(project: Project, option: Optional[str], X: np.ndarray, Y: np.ndarray, mask: np.ndarray) -> List[tuple]:
    """(row, col, area m2 whose rain arrives) of each inlet in this run, for the storm model."""
    out = []
    for o in active(project, option):
        if o["kind"] == "inlet" and mask.any():
            d = np.where(mask, np.hypot(X - o["x"], Y - o["y"]), np.inf)
            r, c = np.unravel_index(int(np.argmin(d)), d.shape)
            out.append((int(r), int(c), float(o["area_m2"]) * float(o["runoff_pct"]) / 100.0))
    return out
