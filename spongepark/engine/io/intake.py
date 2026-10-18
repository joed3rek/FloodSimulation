"""Survey intake: from a dropped DXF to a project with a clean layer system and a ground model.

1. ``start(path)`` reads the drawing, proposes the standard (SP-*) name and title for every layer,
   links the ones it understands, and turns the rest into questions: layers whose meaning is unclear
   (SP-CHECK-*), layers it does not recognise, and recognised-by-fragment guesses to confirm.
2. ``preview(path, layer)`` draws the whole drawing faintly with one layer highlighted, so each
   question shows exactly what is on that layer.
3. ``finish(...)`` writes a cleaned copy of the drawing (layers renamed and merged to the standard,
   exact duplicates removed, original untouched), creates the ``.sponge`` project with both drawings
   inside it (``survey/``), and builds the ground model.
"""

from __future__ import annotations

import io
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import cad

log = logging.getLogger(__name__)

WORKSPACE = Path.home() / "SpongePark"


def _standard() -> Dict[str, Any]:
    return cad.layer_standard()


def _choices() -> List[Dict[str, str]]:
    """Every standard layer a drawing layer can be linked to, grouped for the interface."""
    groups = {"LVL": "Levels", "CONT": "Contours", "SITE": "Site", "BLDG": "Site", "WALL": "Site", "FENCE": "Site",
              "GATE": "Site", "STEP": "Site", "FURNITURE": "Site", "PATH": "Movement", "ROAD": "Movement",
              "DRAIN": "Water", "WELL": "Water", "WATER": "Water", "TREE": "Planting", "UTIL": "Utilities", "ANNO": "Annotation"}
    out = []
    for l in _standard()["layers"]:
        key = l["name"].split("-")[1]
        if key in ("CHECK", "DSN"):
            continue
        out.append({"name": l["name"], "title": l["title"], "group": groups.get(key, "Other"), "description": l["description"]})
    out.append({"name": "", "title": "Not needed (leave out)", "group": "Other", "description": "Kept in the drawing, not used"})
    return out


def start(path: Path) -> Dict[str, Any]:
    path = Path(path)
    doc = cad.read(path)
    inv = cad.inventory(doc)
    std = {l["name"]: l for l in _standard()["layers"]}
    questions_def = _standard().get("questions", {})
    info = {li["name"]: li for li in inv["layers"]}
    layers = []
    for r in cad.suggest_renames(inv):
        li = info[r.old]
        s = std.get(r.new)
        q = None
        if r.new in questions_def:
            q = {"kind": "unclear", "ask": questions_def[r.new]["ask"],
                 "answers": [{"name": a, "title": t} for a, t in questions_def[r.new]["answers"]]}
        elif r.confidence == "none" and r.old != "0":
            q = {"kind": "unknown", "ask": "The engine does not recognise this layer. What is on it?"}
        elif r.confidence == "partial":
            q = {"kind": "confirm", "ask": f"Looks like {s['title'].lower()}. Is it?"}
        elif r.old == "0" and sum(li["entities"].values()) > 0:
            q = {"kind": "unknown", "ask": "Layer 0 holds objects drawn without a layer. What are they?"}
        layers.append({
            "layer": r.old, "proposed": r.new if s else "", "title": s["title"] if s else "Not recognised",
            "role": s.get("role") if s else None, "confidence": r.confidence, "entities": li["entities"],
            "count": int(sum(li["entities"].values())), "numbers": li["numeric_texts"], "level_range": li["level_range"],
            "z_values": li["z_nonzero_share"], "question": q,
        })
    order = {"unclear": 0, "unknown": 1, "confirm": 2, None: 3}
    layers.sort(key=lambda x: (order[(x["question"] or {}).get("kind")], -x["count"]))
    return {"survey": str(path), "name": path.stem, "dxf_version": inv["dxf_version"], "units": inv["insunits"],
            "extents": inv["extents_xy"], "layers": layers, "choices": _choices(),
            "questions": sum(1 for l in layers if l["question"])}


@lru_cache(maxsize=4)
def _segments(path: str, mtime: float) -> Tuple[Dict[str, Any], Tuple[float, float, float, float]]:
    """Drawable geometry per layer (lines and points), read once per file version."""
    doc = cad.read(Path(path))
    lines: Dict[str, List[Any]] = {}
    pts: Dict[str, List[Tuple[float, float]]] = {}
    xs, ys = [], []
    for e in doc.modelspace():
        L, t = e.dxf.layer, e.dxftype()
        try:
            if t in ("TEXT", "MTEXT"):
                x, y = cad._text_xy(e)
                pts.setdefault(L, []).append((x, y))
            elif t == "INSERT":
                p = e.dxf.insert
                pts.setdefault(L, []).append((p.x, p.y))
                # draw what the block contains (a boundary or building drawn as a block shows as itself)
                drawn = 0
                for ve in e.virtual_entities():
                    if drawn > 200:
                        break
                    vs = cad._vertices(ve) if ve.dxftype() in ("LWPOLYLINE", "POLYLINE", "LINE", "ARC", "SPLINE") else []
                    if len(vs) >= 2:
                        xy = [(v[0], v[1]) for v in vs]
                        if cad._closed(ve):
                            xy.append(xy[0])
                        lines.setdefault(L, []).append(xy)
                        drawn += 1
            elif t in ("POINT", "CIRCLE"):
                p = e.dxf.location if t == "POINT" else e.dxf.center
                pts.setdefault(L, []).append((p.x, p.y))
            else:
                vs = cad._vertices(e)
                if len(vs) >= 2:
                    xy = [(v[0], v[1]) for v in vs]
                    if cad._closed(e):
                        xy.append(xy[0])
                    lines.setdefault(L, []).append(xy)
                    xs += [v[0] for v in xy]
                    ys += [v[1] for v in xy]
        except Exception:  # odd entities do not stop a preview
            continue
    for v in pts.values():
        xs += [p[0] for p in v]
        ys += [p[1] for p in v]
    import numpy as np

    ext = (float(np.percentile(xs, 1)), float(np.percentile(ys, 1)), float(np.percentile(xs, 99)), float(np.percentile(ys, 99))) \
        if xs else (0.0, 0.0, 1.0, 1.0)
    return {"lines": lines, "points": pts}, ext


def geometry(path: Path, detail: float = 4000.0) -> Dict[str, Any]:
    """The drawing's linework per layer for an interactive plan view (pan and zoom in the client).

    Coordinates are drawing units relative to ``origin`` (the lower-left of the extent), rounded to
    0.01; lines are simplified to 1/``detail`` of the drawing's size, which is finer than a screen
    pixel at fit zoom. Returns {"origin": [x, y], "extent": [w, h], "layers": {name: {"lines":
    [[x0, y0, x1, y1, ...], ...], "points": [x0, y0, ...]}}}."""
    from shapely.geometry import LineString

    path = Path(path)
    geo, (x0, y0, x1, y1) = _segments(str(path), path.stat().st_mtime)
    tol = max(x1 - x0, y1 - y0, 1e-9) / detail
    layers: Dict[str, Any] = {}
    for name in sorted(set(geo["lines"]) | set(geo["points"])):
        out_lines = []
        for seg in geo["lines"].get(name, []):
            xy = seg
            if len(seg) > 2:
                xy = list(LineString(seg).simplify(tol, preserve_topology=False).coords)
            if len(xy) >= 2:
                out_lines.append([round(v, 2) for q in xy for v in (q[0] - x0, q[1] - y0)])
        pts = [round(v, 2) for q in geo["points"].get(name, []) for v in (q[0] - x0, q[1] - y0)]
        layers[name] = {"lines": out_lines, "points": pts}
    return {"origin": [x0, y0], "extent": [x1 - x0, y1 - y0], "layers": layers}


def preview(path: Path, layer: Optional[str] = None, size_px: int = 560) -> bytes:
    """PNG of the drawing (faint) with ``layer`` highlighted in terracotta."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    path = Path(path)
    geo, (x0, y0, x1, y1) = _segments(str(path), path.stat().st_mtime)
    if layer:  # zoom to the layer, keeping enough of the drawing around it to place it
        import numpy as np

        lx = [q[0] for seg in geo["lines"].get(layer, []) for q in seg] + [q[0] for q in geo["points"].get(layer, [])]
        ly = [q[1] for seg in geo["lines"].get(layer, []) for q in seg] + [q[1] for q in geo["points"].get(layer, [])]
        if lx:
            span = max(x1 - x0, y1 - y0)
            bx0, bx1, by0, by1 = np.percentile(lx, 1), np.percentile(lx, 99), np.percentile(ly, 1), np.percentile(ly, 99)
            half = max(bx1 - bx0, by1 - by0, 0.25 * span) * 0.65
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            x0, x1, y0, y1 = max(x0, cx - half), min(x1, cx + half), max(y0, cy - half), min(y1, cy + half)
            if x1 - x0 < half or y1 - y0 < half:  # near the drawing's edge: keep the window square
                x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
    pad = 0.05 * max(x1 - x0, y1 - y0, 1)
    fig = plt.figure(figsize=(size_px / 100, size_px / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#FDFCF8")
    fig.patch.set_facecolor("#FDFCF8")
    others = [s for L, segs in geo["lines"].items() if L != layer for s in segs]
    if others:
        ax.add_collection(LineCollection(others, colors="#C9C2B6", linewidths=0.4))
    for L, p in geo["points"].items():
        if L != layer and p:
            ax.scatter([q[0] for q in p], [q[1] for q in p], s=0.6, c="#D6CFC4", linewidths=0)
    if layer:
        mine = geo["lines"].get(layer, [])
        if mine:
            ax.add_collection(LineCollection(mine, colors="#B5733E", linewidths=1.6))
        p = geo["points"].get(layer, [])
        if p:
            ax.scatter([q[0] for q in p], [q[1] for q in p], s=14, c="#B5733E", linewidths=0)
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def finish(survey: Path, links: Dict[str, str], project_path: Optional[Path] = None,
           park_area_m2: Optional[float] = None, contours_in_surface: Any = "auto", units_scale_to_m: float = 1.0) -> Dict[str, Any]:
    """Clean the drawing with the confirmed links, create the project and build the ground model.

    ``links``: drawing layer -> standard layer name ("" = not needed)."""
    from ..project import Project
    from ..terrain.survey import import_survey

    survey = Path(survey)
    renames = {old: (new or f"SP-X-{old}") for old, new in links.items() if old != "0"}
    cleaned = survey.with_name(survey.stem + "_SP.dxf")
    report = cad.standardise(survey, renames, cleaned)
    m = cad.suggest_layer_map(cad.inventory(cad.read(cleaned)))
    if not m["roles"].get("spot_levels") and not m["roles"].get("contours"):
        raise cad.CadError("no layer holds levels: link at least the spot levels or contours.")
    m.update(confirmed=True, units_scale_to_m=units_scale_to_m, contours_in_surface=contours_in_surface,
             needs_decision=[], note="Confirmed in the survey intake: every layer linked by the designer.")
    project_path = Path(project_path) if project_path else survey.with_name(survey.stem.replace(" ", "_") + ".sponge")
    with Project.create(project_path, survey.stem, crs="LOCAL", overwrite=project_path.exists()) as p:
        # the .sponge file carries its drawings: the surveyor's original and the cleaned copy
        import shutil

        p.path("survey").mkdir(exist_ok=True)
        shutil.copy2(survey, p.path(f"survey/{survey.name}"))
        shutil.copy2(cleaned, p.path(f"survey/{cleaned.name}"))
        q = import_survey(p, cleaned, m, park_area_m2)
        p.history.log("survey_intake", survey=str(survey), cleaned=str(cleaned), links=links,
                      duplicates_removed=report["duplicates_removed_total"])
        from ..site import survey_layers

        layers = survey_layers.build(p)   # walls, gates, trees, paths ... on the ground, layer by layer
        p.save()
    return {"project": str(project_path), "cleaned_drawing": str(cleaned), "cleaning": report, "layer_map": m,
            "qc": {k: q.get(k) for k in ("spot_cross_validation", "issues", "elevation_range_m")},
            "survey_layers": [{"name": L["name"], "title": L["title"], "count": L["count"]} for L in layers["layers"]]}


def save_upload(filename: str, data: bytes) -> Path:
    """Store an uploaded drawing in the workspace (one folder per drawing)."""
    name = Path(filename).name
    if Path(name).suffix.lower() not in (".dxf", ".dwg"):
        raise cad.CadError("upload a .dxf (or .dwg with the ODA File Converter installed).")
    folder = WORKSPACE / Path(name).stem.replace(" ", "_")
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / name
    out.write_bytes(data)
    return out
