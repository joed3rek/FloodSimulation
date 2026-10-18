"""The ground questionnaire: what the park's ground is like, turned into TR-55 curve numbers.

The designer answers a few questions (soil type; what covers the open park and in what condition; whether
the footpaths are paved). Each cover and condition maps to a TR-55 cover (NRCS 1986, tables 2-2a to 2-2c),
the soil type to a hydrologic soil group (Appendix A), and the curve numbers come from TR-55 itself
(``hydrology/data/tr55.json``, each with its table and page). The open park's curve number is the
area-weighted mean of the covers given.

Applying the answers:

- writes ``site/ground.json`` (answers, derivation, citations, and a TR-55 runoff check per storm);
- writes the park as one soil zone with the chosen soil group (``site/soil_zones.geojson``);
- sets each subcatchment's pervious curve number (and adds paved footpaths to its impervious share);
- switches infiltration to ``CURVE_NUMBER`` (SWMM and the 2D model).

Delineation rebuilds the subcatchments, so :func:`apply_to_subcatchments` runs again after it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..hydrology import tr55
from ..project import Project, Source

REL = "site/ground.json"

SOILS = [
    {"id": "A", "label": "Sandy or gravelly: water soaks in fast", "hsg": "A"},
    {"id": "B", "label": "Loam or red loamy soil: soaks in moderately", "hsg": "B"},
    {"id": "C", "label": "Silty or clayey loam, or compacted: soaks in slowly", "hsg": "C"},
    {"id": "D", "label": "Clay, black cotton soil, or shallow rock: hardly soaks in", "hsg": "D"},
    {"id": "unknown", "label": "Not sure (use group C until a percolation test; marked as assumed)", "hsg": "C"},
]
COVERS = [
    {"id": "grass", "label": "Grass lawn"},
    {"id": "shrubs", "label": "Shrubs and brush"},
    {"id": "woods", "label": "Woods (trees with leaf litter)"},
    {"id": "woods_grass", "label": "Trees over grass"},
    {"id": "bare", "label": "Bare soil"},
]
CONDITIONS = [
    {"id": "good", "label": "Well maintained (more than 75 % covered)"},
    {"id": "fair", "label": "Fairly kept (50-75 % covered)"},
    {"id": "poor", "label": "Not maintained (less than 50 % covered)"},
    {"id": "barren", "label": "Barren (no vegetation)"},
]
PATHS = [
    {"id": "paved", "label": "Paved (concrete, tiles, asphalt)"},
    {"id": "gravel", "label": "Gravel or murram"},
    {"id": "earth", "label": "Earth (unpaved)"},
]
# (cover, condition) -> TR-55 cover key
TR55_KEY = {
    ("grass", "good"): "open_space_good", ("grass", "fair"): "open_space_fair", ("grass", "poor"): "open_space_poor",
    ("shrubs", "good"): "brush_good", ("shrubs", "fair"): "brush_fair", ("shrubs", "poor"): "brush_poor",
    ("woods", "good"): "woods_good", ("woods", "fair"): "woods_fair", ("woods", "poor"): "woods_poor",
    ("woods_grass", "good"): "woods_grass_good", ("woods_grass", "fair"): "woods_grass_fair",
    ("woods_grass", "poor"): "woods_grass_poor",
}
BARREN = "fallow_bare_soil"


def questions() -> Dict[str, Any]:
    return {"soils": SOILS, "covers": COVERS, "conditions": CONDITIONS, "paths": PATHS,
            "source": "NRCS (1986) TR-55 Urban Hydrology for Small Watersheds, tables 2-2a to 2-2c and Appendix A."}


def _key(cover: str, condition: str) -> str:
    if cover == "bare" or condition == "barren":
        return BARREN
    k = TR55_KEY.get((cover, condition))
    if k is None:
        raise ValueError(f"no TR-55 cover for '{cover}' in '{condition}' condition.")
    return k


def derive(answers: Dict[str, Any], rainfall_rows: Optional[List[Dict[str, float]]] = None) -> Dict[str, Any]:
    """Curve numbers from the answers. ``answers``: {"soil": id, "covers": [{"cover", "condition", "share_pct"}],
    "paths": id}. Returns the derivation (with citations) and, given rainfall rows, a TR-55 runoff check."""
    soil = next((s for s in SOILS if s["id"] == answers.get("soil")), None)
    if soil is None:
        raise ValueError("choose the soil type.")
    hsg = soil["hsg"]
    covers = answers.get("covers") or []
    if not covers:
        raise ValueError("give at least one ground cover.")
    total = sum(float(c.get("share_pct") or 0) for c in covers)
    if total <= 0:
        raise ValueError("the cover shares must add up to more than 0 %.")
    data = tr55.covers()
    rows, cn_sum = [], 0.0
    for c in covers:
        key = _key(c["cover"], c["condition"])
        cn = tr55.curve_number(key, hsg)
        share = float(c.get("share_pct") or 0) / total
        cn_sum += share * cn
        d = data[key]
        rows.append({"cover": c["cover"], "condition": c["condition"], "share_pct": round(100 * share, 1),
                     "tr55_cover": key, "tr55_label": d["label"], "cn": cn,
                     "citation": f"TR-55 table {d['table']}, p. {d['page']}, HSG {hsg}"})
    cn = round(cn_sum, 1)
    out = {"answers": answers, "hsg": hsg, "soil_assumed": answers.get("soil") == "unknown",
           "covers": rows, "curve_number": cn,
           "s_mm": round(25400.0 / cn - 254.0, 2), "ia_mm": round(0.2 * (25400.0 / cn - 254.0), 2),
           "paths": answers.get("paths") or "paved",
           "note": "Curve number of the open park (pervious part), area-weighted over the covers given. Buildings "
                   "and paved paths are impervious (CN 98) and are counted separately."}
    if rainfall_rows:
        out["runoff_check"] = [{"return_period_yr": r["return_period_yr"], "rain_mm": r["depth_mm"],
                                "runoff_mm": round(tr55.runoff_depth_mm(r["depth_mm"], cn), 2)}
                               for r in rainfall_rows]
    return out


def _rain_rows(project: Project) -> Optional[List[Dict[str, float]]]:
    if not project.exists("rainfall/return_periods.csv"):
        return None
    import pandas as pd

    df = pd.read_csv(project.path("rainfall/return_periods.csv"))
    if "duration_hr" in df:
        df = df[df["duration_hr"] == df["duration_hr"].max()]
    col = "depth_mm" if "depth_mm" in df else None
    if col is None:
        return None
    return [{"return_period_yr": int(r.return_period_yr), "depth_mm": float(r.depth_mm)} for r in df.itertuples()]


def _paved_path_share(project: Project) -> float:
    """Share of the park covered by footpath surfaces (from the survey layers)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from .survey_layers import park_boundary

    park = park_boundary(project)
    if park is None or not project.exists("site/survey_layers.json") or park.area <= 0:
        return 0.0
    tris = []
    for L in project.read_json("site/survey_layers.json")["layers"]:
        if L["kind"] != "path":
            continue
        for f in L["features"]:
            if f["g"] != "mesh":
                continue
            xyz, t = f["xyz"], f["tri"]
            for i in range(0, len(t), 3):
                pts = [(xyz[3 * t[i + j]], xyz[3 * t[i + j] + 1]) for j in range(3)]
                tris.append(Polygon(pts))
    if not tris:
        return 0.0
    return float(unary_union(tris).intersection(park).area / park.area)


def apply_to_subcatchments(project: Project) -> int:
    """Set the questionnaire's curve number on every subcatchment (after delineation rebuilds them)."""
    if not project.exists(REL) or not project.exists("site/subcatchments.geojson"):
        return 0
    g = project.read_json(REL)
    fc = project.read_geojson("site/subcatchments.geojson")
    extra = 100 * g.get("paved_path_share", 0.0) if g.get("paths") == "paved" else 0.0
    for f in fc["features"]:
        p = f["properties"]
        p["curve_number"] = g["curve_number"]
        p["tr55_cover"] = None
        p["cn_source"] = "ground questionnaire (TR-55)"
        base = float(p.get("pct_imperv_buildings", p.get("pct_imperv", 0.0)) or 0.0)
        p["pct_imperv_buildings"] = base
        p["pct_imperv"] = round(min(100.0, base + extra), 2)
    project.write_geojson("site/subcatchments.geojson", fc)
    return len(fc["features"])


def apply(project: Project, answers: Dict[str, Any]) -> Dict[str, Any]:
    """Save the answers, derive the curve numbers and set up infiltration from them."""
    from .survey_layers import park_boundary

    out = derive(answers, _rain_rows(project))
    out["paved_path_share"] = round(_paved_path_share(project), 4)
    project.write_json(REL, out)
    park = park_boundary(project)
    if park is not None:
        project.write_geojson("site/soil_zones.geojson", {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": park.__geo_interface__,
            "properties": {"id": "PARK", "hsg": out["hsg"], "source": "ground questionnaire",
                           "dry_time_days": float(project.parameters.value_or("swmm.cn_dry_time_days", 7.0)),
                           "note": ("soil group assumed (C) until a percolation test" if out["soil_assumed"]
                                    else "soil group from the designer's answer")}}]})
    n = apply_to_subcatchments(project)
    P = project.parameters
    P.set("swmm.infiltration_method", "CURVE_NUMBER", "-", Source.DESIGNER,
          "From the ground questionnaire: TR-55 curve numbers.")
    P.confirm("swmm.infiltration_method")
    project.history.log("ground_questionnaire", cn=out["curve_number"], hsg=out["hsg"], subcatchments=n)
    return out


def load(project: Project) -> Optional[Dict[str, Any]]:
    return project.read_json(REL) if project.exists(REL) else None
