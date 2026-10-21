"""Where water leaves the park: the designer confirms each exit (Site setup > Outfalls).

Delineation finds every place where surface flow reaches the edge of the surveyed park (``OUT_<k>`` in
``site/outfalls.geojson``). Many parks have no real outfall there: a compound wall or a kerb holds the water,
which ponds against it and spills to the road only when it rises above the edge. The engine does not guess
which: the designer answers for each exit

- ``open``: water leaves here (a gate, an opening in the wall, a drain inlet): a free outfall, as before;
- ``closed``: no way out: the water ponds behind the edge, up to the height of the wall or kerb there, and
  above that spills over it to the road.

A closed exit is an existing ``edge_pond`` element in every scenario, the existing site included: a storage
node whose stage-area curve is the ground draining to that exit up to the edge height, with an overflow weir
at the edge height into the outfall (the road). The ground under it already infiltrates in its subcatchment,
so the edge pond is not cut out of it and gets no rain of its own; the water standing in it soaks into
the soil under it at the soil's rate (seepage), as any stored water does. Exits not answered stay open and are
listed as unconfirmed.

``site/outfall_answers.json``: ``{"exits": [{"x", "y", "state", "edge_height_m"}], "all": {...}}``; answers are
matched to exits by position (exit ids change when the drainage is redone), within ``MATCH_M``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..project import Project

REL = "site/outfall_answers.json"
MATCH_M = 3.0
STATES = ("open", "closed")


def _answers(project: Project) -> Dict[str, Any]:
    return project.read_json(REL) if project.exists(REL) else {"exits": [], "all": {}}


def _exits(project: Project) -> List[Dict[str, Any]]:
    if not project.exists("site/outfalls.geojson"):
        return []
    subs = project.read_geojson("site/subcatchments.geojson")["features"] if project.exists("site/subcatchments.geojson") else []
    from shapely.geometry import shape

    area: Dict[str, float] = {}
    for f in subs:
        o = f["properties"].get("outlet")
        area[o] = area.get(o, 0.0) + float(shape(f["geometry"]).area)
    out = []
    for f in project.read_geojson("site/outfalls.geojson")["features"]:
        p = f["properties"]
        x, y = f["geometry"]["coordinates"][:2]
        out.append({"id": p["id"], "x": round(float(x), 2), "y": round(float(y), 2),
                    "ground_m": p.get("invert_elev_m"), "draining_area_m2": round(area.get(p["id"], 0.0), 1)})
    out.sort(key=lambda e: -e["draining_area_m2"])
    return out


def _answer_for(ex: Dict[str, Any], ans: Dict[str, Any]) -> Dict[str, Any]:
    """This exit's answer: its own (nearest within MATCH_M), else the answer for all exits."""
    best, dist = None, MATCH_M
    for a in ans.get("exits", []):
        d = float(np.hypot(a["x"] - ex["x"], a["y"] - ex["y"]))
        if d <= dist:
            best, dist = a, d
    a = best or ans.get("all") or {}
    return {"state": a.get("state"), "edge_height_m": a.get("edge_height_m")}


def status(project: Project) -> Dict[str, Any]:
    """Every exit with its answer, and whether all are confirmed."""
    ans = _answers(project)
    rows = []
    for ex in _exits(project):
        a = _answer_for(ex, ans)
        rows.append({**ex, **a, "confirmed": a["state"] == "open" or (a["state"] == "closed" and bool(a["edge_height_m"]))})
    return {"exits": rows, "all": ans.get("all", {}), "count": len(rows),
            "confirmed": bool(rows) and all(r["confirmed"] for r in rows),
            "closed": sum(1 for r in rows if r["state"] == "closed" and r["confirmed"]),
            "question": "Where can water leave the park? For each point where the ground drains to the edge, say "
                        "whether there is a way out (gate, opening, drain inlet) or a wall / kerb that holds the "
                        "water, and how high that edge is."}


def apply(project: Project, answers: Dict[str, Any]) -> Dict[str, Any]:
    """Save the answers: ``all`` (one answer for every exit, e.g. no outfall anywhere) and/or ``exits``
    ([{id or x/y, state, edge_height_m}]). A closed exit needs the edge height (m above the ground there)."""
    exits = {e["id"]: e for e in _exits(project)}
    if not exits:
        raise ValueError("analyse the site first: the exits come from the drainage of the ground.")

    def check(a: Dict[str, Any], who: str) -> Dict[str, Any]:
        st = a.get("state")
        if st not in STATES:
            raise ValueError(f"{who}: say 'open' (water leaves here) or 'closed' (a wall or kerb holds it).")
        h = a.get("edge_height_m")
        if st == "closed":
            if h is None or float(h) <= 0:
                raise ValueError(f"{who}: give the height of the wall or kerb (m above the ground there).")
            if float(h) > 3.0:
                raise ValueError(f"{who}: an edge {float(h):g} m high is not a kerb or park wall; check the value.")
        return {"state": st, "edge_height_m": float(h) if st == "closed" else None}

    old = _answers(project)
    out: Dict[str, Any] = {"exits": list(old.get("exits", [])), "all": old.get("all", {})}
    if answers.get("all"):
        out["all"] = check(answers["all"], "all exits")
        out["exits"] = []   # one answer for all replaces the per-exit ones
    for a in answers.get("exits", []) or []:
        ex = exits.get(a.get("id")) if a.get("id") else None
        x, y = (ex["x"], ex["y"]) if ex else (a.get("x"), a.get("y"))
        if x is None or y is None:
            raise ValueError(f"unknown exit '{a.get('id')}'.")
        row = {"x": float(x), "y": float(y), **check(a, a.get("id") or f"exit at {x:.1f}, {y:.1f}")}
        out["exits"] = [e for e in out["exits"] if np.hypot(e["x"] - row["x"], e["y"] - row["y"]) > MATCH_M] + [row]
    project.write_json(REL, out)
    st = status(project)
    project.history.log("outfalls", closed=st["closed"], confirmed=st["confirmed"])
    return st


# ------------------------------------------------------------------ the flood model
def edge_elements(project: Project, site) -> List[Any]:
    """The closed exits as ``edge_pond`` elements (source "existing", locked), wired: the subcatchments that
    drained to the exit drain into the pond, which spills over the edge into the outfall."""
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from shapely import contains_xy
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from ..nbs.components import NbSElement
    from ..terrain.raster import read_geotiff

    st = status(project)
    closed = [e for e in st["exits"] if e["state"] == "closed" and e["confirmed"]]
    if not closed or not project.exists("terrain/existing.tif"):
        return []
    dem = read_geotiff(project.path("terrain/existing.tif"))
    X, Y = dem.cell_centres()
    cell = dem.cell_size
    t = from_origin(dem.origin[0], dem.origin[1], cell, cell)
    out = []
    for ex in closed:
        subs = [s for s in site.subcatchments if s.outlet == ex["id"]]
        if not subs:
            continue
        inv = float(ex["ground_m"])
        H = float(ex["edge_height_m"])
        catch = unary_union([s.shape() for s in subs])
        m = contains_xy(catch, X, Y) & (dem.z != dem.nodata)
        z = np.where(m, dem.z, np.nan)
        stage = []
        for h in np.linspace(0.0, H, 12):
            wet = m & (z <= inv + h)
            stage.append([round(float(h), 4), max(round(float(wet.sum() * cell * cell), 2), cell * cell)])
        wet = (m & (z <= inv + H)).astype("int32")
        polys = [shape(g) for g, v in shapes(wet, mask=wet > 0, transform=t)]
        fp = unary_union(polys) if polys else catch.centroid.buffer(cell)
        if fp.geom_type != "Polygon":
            fp = max(fp.geoms, key=lambda g: g.area)
        n = ex["id"].split("_", 1)[-1]
        out.append(NbSElement(
            id=f"EDGE_{n}", type="edge_pond", geometry=fp.__geo_interface__, source="existing", locked=True,
            invert_elev_m=round(inv, 3), max_ponding_depth_m=H, freeboard_m=1.0, stage_curve=stage, weir_length_m=round(max(float(np.sqrt(stage[-1][1])), 1.0), 2),
            overflow_to=ex["id"], inflow_from=[s.id for s in subs],
            param_sources={"max_ponding_depth_m": "designer (Site setup > Outfalls): edge height",
                           "stage_curve": "ground model behind the exit"},
            notes=f"No outfall at {ex['id']} (Site setup > Outfalls): water ponds against the edge and spills over "
                  f"it at {H:g} m to the road; the standing water soaks in at the soil's rate."))
    return out


def wire(elements: List[Any], edges: List[Any]) -> None:
    """Route into the edge ponds: elements discharging to a closed exit discharge to its pond instead, and
    subcatchments already drained by an element stay with that element."""
    pond_of = {e.overflow_to: e.id for e in edges}
    taken = {sid for e in elements for sid in e.inflow_from}
    for e in elements:
        if e.outflow_to in pond_of:
            e.outflow_to = pond_of[e.outflow_to]
        if e.overflow_to in pond_of:
            e.overflow_to = pond_of[e.overflow_to]
    for p in edges:
        p.inflow_from = [s for s in p.inflow_from if s not in taken]
