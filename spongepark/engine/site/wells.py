"""Existing recharge wells: found on the survey's recharge-well layer and part of the existing site.

They are in the park today, so they count in the existing site (baseline) as well as in every design: SWMM
(a storage node that seeps into the ground) and the 2D flood model (a sink) include them everywhere, and a
design only gets credit for the wells the designer adds. The drawing gives a well's position and, when it
is drawn as a circle, its diameter; never its depth or how fast the strata take water. The designer gives
those once for all the wells (Site setup > Wells), and can change any one well. A well without answers is
shown but left out of the flood model, and the designer is told so. Nothing is assumed.

``site/wells.geojson``: one point per well (id, ground level, drawn diameter, inside the park or not, the
answers for that well), and under ``answers`` the values given for all of them.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..project import Project

log = logging.getLogger(__name__)

REL = "site/wells.geojson"
SAME_WELL_M = 0.5            # symbols this close are one well (a circle and a block drawn together)
FIELDS = ("depth_m", "diameter_m", "infiltration_rate_mm_hr")
LABELS = {"depth_m": "depth", "diameter_m": "diameter", "infiltration_rate_mm_hr": "strata infiltration rate"}


def record(project: Project, points: List[Tuple[float, float, Optional[float]]], ground, park) -> List[Dict[str, Any]]:
    """Write site/wells.geojson for the wells found: (x, y, drawn radius or None) per symbol. Answers given
    earlier are kept for a well at the same place."""
    from shapely.geometry import Point

    old = _read(project)
    old_feats = old.get("features", [])
    merged: List[List[float]] = []
    for x, y, r in sorted(points, key=lambda q: (q[0], q[1])):
        for m in merged:
            if np.hypot(m[0] - x, m[1] - y) <= SAME_WELL_M:
                m[2] = m[2] or r
                break
        else:
            merged.append([x, y, r])
    feats = []
    for i, (x, y, r) in enumerate(merged):
        z = float(ground(np.array([x]), np.array([y]))[0])
        props: Dict[str, Any] = {"id": f"EW{i + 1}", "ground_m": round(z, 3),
                                 "drawn_diameter_m": round(2 * r, 2) if r else None,
                                 "in_park": bool(park is not None and park.buffer(0.5).contains(Point(x, y)))}
        prev = next((f["properties"] for f in old_feats
                     if np.hypot(f["geometry"]["coordinates"][0] - x, f["geometry"]["coordinates"][1] - y) <= SAME_WELL_M), None)
        if prev:
            for k in FIELDS:
                if prev.get(k) is not None:
                    props[k] = prev[k]
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(x, 3), round(y, 3)]},
                      "properties": props})
    fc = {"type": "FeatureCollection", "answers": old.get("answers", {}), "features": feats}
    project.write_geojson(REL, fc)
    return feats


def _ensure(project: Project) -> None:
    """Record the wells if this project has not yet: from the survey layers (built, or rebuilt when out of date)."""
    from . import survey_layers

    if project.exists(REL):
        return
    if project.exists("terrain/existing.tif") and project.exists("survey") and any(project.path("survey").glob("*_SP.dxf")):
        survey_layers.load(project)   # (re)builds the layers, and with them the wells, when out of date
    if not project.exists(REL) and project.exists(survey_layers.REL):
        _from_layers(project)   # layers built before wells were recorded: take the wells from them


def _from_layers(project: Project) -> None:
    """Record the wells from site/survey_layers.json (the recharge-well layer's points)."""
    from . import survey_layers

    doc = project.read_json(survey_layers.REL)
    pts = [(f["xyz"][0], f["xyz"][1], f.get("radius_m")) for L in doc.get("layers", [])
           if L.get("kind") == "recharge_well" for f in L.get("features", []) if f.get("g") == "point"]
    if project.exists("terrain/existing.tif"):
        record(project, pts, survey_layers._Ground(project, doc.get("extent")), survey_layers.park_boundary(project))


def _read(project: Project) -> Dict[str, Any]:
    return project.read_geojson(REL) if project.exists(REL) else {"features": []}


def _values(p: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """A well's values: its own answer, else (diameter) the drawing, else the answer for all wells."""
    out = {}
    for k in FIELDS:
        v = p.get(k)
        if v is None and k == "diameter_m":
            v = p.get("drawn_diameter_m")
        if v is None:
            v = answers.get(k)
        out[k] = None if v is None else float(v)
    return out


def _missing(v: Dict[str, Optional[float]]) -> List[str]:
    return [LABELS[k] for k in FIELDS if not v.get(k) or v[k] <= 0]


def status(project: Project) -> Dict[str, Any]:
    """The wells in the park, the answers, and which wells are in the flood model (the questions to ask)."""
    _ensure(project)
    fc = _read(project)
    answers = fc.get("answers", {})
    wells = []
    for f in fc.get("features", []):
        p = dict(f["properties"])
        if not p.get("in_park"):
            continue
        v = _values(p, answers)
        miss = _missing(v)
        p.update(x=f["geometry"]["coordinates"][0], y=f["geometry"]["coordinates"][1], values=v,
                 in_model=not miss, missing=miss)
        wells.append(p)
    drawn = sorted({w["drawn_diameter_m"] for w in wells if w.get("drawn_diameter_m")})
    return {"wells": wells, "answers": answers, "count": len(wells),
            "in_model": sum(1 for w in wells if w["in_model"]), "drawn_diameters_m": drawn}


def apply(project: Project, answers: Dict[str, Any]) -> Dict[str, Any]:
    """Save the answers: ``{"depth_m", "diameter_m", "infiltration_rate_mm_hr"}`` for all wells and
    optionally ``"wells": [{"id", <the same fields>}]`` for single wells (null clears a well's own value)."""
    _ensure(project)
    fc = _read(project)
    if not fc.get("features"):
        raise ValueError("this project's survey has no recharge wells.")

    def check(k: str, v: Any, who: str) -> Optional[float]:
        if v in (None, ""):
            return None
        v = float(v)
        if v <= 0:
            raise ValueError(f"{who}: the {LABELS[k]} must be more than 0.")
        if k == "depth_m" and v > 60:
            raise ValueError(f"{who}: a recharge well {v:g} m deep is outside what the model covers (up to 60 m).")
        return v

    common = dict(fc.get("answers", {}))
    for k in FIELDS:
        if k in answers:
            common[k] = check(k, answers[k], "all wells")
    fc["answers"] = {k: v for k, v in common.items() if v is not None}
    by_id = {f["properties"]["id"]: f for f in fc["features"]}
    for a in answers.get("wells") or []:
        f = by_id.get(a.get("id"))
        if f is None:
            raise ValueError(f"no well {a.get('id')} in this project.")
        for k in FIELDS:
            if k in a:
                f["properties"][k] = check(k, a[k], a["id"])
    project.write_geojson(REL, fc)
    from .ponds import _refresh

    _refresh(project)   # the wells are sinks now: drainage, flow lines and the design's ground are redone
    st = status(project)
    project.history.log("wells", in_model=st["in_model"], count=st["count"])
    return st


def existing_elements(project: Project) -> List[Any]:
    """The answered wells in the park as recharge-well elements (source "existing", locked), for every
    scenario's flood model including the existing site's."""
    from ..nbs.components import NbSElement

    fc = _read(project)
    answers = fc.get("answers", {})
    out = []
    for f in fc.get("features", []):
        p = f["properties"]
        if not p.get("in_park"):
            continue
        v = _values(p, answers)
        if _missing(v):
            continue
        out.append(NbSElement(
            id=p["id"], type="recharge_well", geometry=f["geometry"], source="existing", locked=True,
            well_depth_m=v["depth_m"], well_diameter_m=v["diameter_m"],
            infiltration_rate_mm_hr=v["infiltration_rate_mm_hr"],
            invert_elev_m=round(float(p["ground_m"]) - v["depth_m"], 3),
            param_sources={"well_depth_m": "designer (Site setup > Wells)",
                           "well_diameter_m": "survey drawing" if p.get("drawn_diameter_m") and p.get("diameter_m") is None
                           else "designer (Site setup > Wells)",
                           "infiltration_rate_mm_hr": "designer (Site setup > Wells)"},
            notes="Existing recharge well (survey)."))
    return out


def sink_cells(project: Project, X: np.ndarray, Y: np.ndarray, mask: np.ndarray) -> List[Tuple[str, Tuple[int, int]]]:
    """(well id, grid cell) of each well in the flood model: the cell it sits in, or the nearest one in the
    domain. The ground's flow routing treats these cells as sinks, so each well gets the catchment that
    drains into it (SC_<id>), as the designer's elements do."""
    out = []
    for e in existing_elements(project):
        x, y = e.geometry["coordinates"][:2]
        d = np.where(mask, np.hypot(X - x, Y - y), np.inf)
        k = int(np.argmin(d))
        if np.isfinite(d.ravel()[k]):
            out.append((e.id, tuple(int(v) for v in np.unravel_index(k, d.shape))))
    return out


def resolved(project: Project, site=None) -> List[Any]:
    """existing_elements with their storage and seepage worked out (no soil lookup needed: a well states
    its own strata rate) and, given the scenario's site, wired: the subcatchment SC_<id> drains into each
    well, and a full well overflows to where that ground drained before."""
    from shapely.geometry import Point

    from ..nbs.components import resolve_element

    out = [resolve_element(e, project.parameters) for e in existing_elements(project)]
    if site is not None:
        subs = {s.id: s for s in site.subcatchments}
        for e in out:
            sc = subs.get(f"SC_{e.id}")
            if sc is None:   # no catchment of its own: it overflows like the ground around it
                pt = Point(*e.geometry["coordinates"][:2])
                sc_around = next((s for s in site.subcatchments if s.shape().buffer(0.5).contains(pt)), None)
                e.overflow_to = sc_around.outlet if sc_around is not None else None
                continue
            e.inflow_from = [sc.id]
            e.overflow_to = sc.outlet
    return out
