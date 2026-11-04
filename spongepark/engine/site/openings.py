"""Inlets and outlets the designer places on the site (Site setup > Inlets and outlets).

The drainage finds where the ground runs to the edge (:mod:`.outfalls`); this is the other half: where water can really
get in and out, which only the designer knows. Nothing here is assumed, so each one says:

- ``kind``: ``outlet`` (water leaves; on the site's edge, it is moved to the nearest point of it) or ``inlet`` (water
  from outside comes in);
- ``origin``: ``site`` (an existing site condition: in every run) or ``design`` (part of the design: in design runs only;
  in a project built from a design model every run is the design);
- an outlet's ``width_m`` and ``sill_m`` (how far above the ground water must rise to leave);
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
    return {**st, "gaps": gaps, "from_model": project.exists(MODEL_SOURCE),
            "question": "Where does water enter or leave this site? Place each inlet and outlet, and say whether it is an "
                        "existing site condition or part of the design. Everywhere else the edge holds the water."}


def _check(a: Dict[str, Any], i: int, boundary) -> Dict[str, Any]:
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
        out["sill_m"] = number("sill_m", "height of its sill above the ground (m; 0 if level)", 0.0)
    else:
        out["area_m2"] = number("area_m2", "area draining to the inlet (m2)", 0.0, open_lo=True)
        out["runoff_pct"] = number("runoff_pct", "share of the rain on that area that arrives (%)", 0.0, 100.0, open_lo=True)
    return out


def save(project: Project, body: Dict[str, Any]) -> Dict[str, Any]:
    boundary = _boundary(project)
    rows = [_check(a, i, boundary) for i, a in enumerate(body.get("openings") or [])]
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
        z = _ground_at(dem, o["x"], o["y"])
        if exit_id and z is not None:
            level = z + float(o["sill_m"])
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
