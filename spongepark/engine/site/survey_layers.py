"""Everything the survey drawing shows, layer by layer, placed on the ground model.

After the survey intake has cleaned the drawing (layers renamed to the SP-* standard) and built the
DEM, :func:`build` reads every physical layer of the cleaned drawing (walls, fences, gates,
buildings, trees, paths, roads, drains, water, manholes, poles, steps, furniture, contours) and drapes
its geometry on the DEM, so a viewer can draw the site in 3D and switch each layer on and off.
Annotation (text, dimensions, grid, title block, level labels) is left out.

Written to ``site/survey_layers.json``. Heights of walls, buildings and trees are display heights for
the 3D view only (the survey gives plan positions, not heights); nothing hydrological uses them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..io import cad
from ..project import Project
from ..terrain.raster import read_geotiff

log = logging.getLogger(__name__)

REL = "site/survey_layers.json"

# SP layer (or prefix) -> how the viewer draws it. height_m: display height above the ground (m).
KINDS: List[Tuple[str, Dict[str, Any]]] = [
    ("SP-WALL", {"kind": "wall", "height_m": 1.8, "color": "#B9AE9C", "visible": True}),
    ("SP-FENCE", {"kind": "fence", "height_m": 1.2, "color": "#8E8778", "visible": True}),
    ("SP-GATE", {"kind": "gate", "height_m": 2.1, "color": "#C18C5D", "visible": True}),
    ("SP-BLDG", {"kind": "building", "height_m": 3.5, "color": "#D9CFC0", "visible": True}),
    ("SP-WATER-TANK", {"kind": "building", "height_m": 1.5, "color": "#9FB7C4", "visible": True}),
    ("SP-TREE-COCONUT", {"kind": "palm", "height_m": 8.0, "color": "#7A9A55", "visible": True}),
    ("SP-TREE", {"kind": "tree", "height_m": 6.0, "color": "#5D7052", "visible": True}),
    ("SP-PATH", {"kind": "path", "width_m": 0.5, "color": "#CDB991", "visible": True}),
    ("SP-ROAD-ANNO", None),
    ("SP-ROAD", {"kind": "road", "width_m": 0.4, "color": "#8A8A85", "visible": True}),
    ("SP-DRAIN-MANHOLE", {"kind": "manhole", "color": "#5A5A55", "visible": True}),
    ("SP-DRAIN", {"kind": "drain", "width_m": 0.4, "color": "#4A7C96", "visible": True}),
    ("SP-WATER", {"kind": "water", "width_m": 0.3, "color": "#4A7C96", "visible": True}),
    ("SP-UTIL-POWER", {"kind": "pole", "height_m": 7.0, "color": "#4A4A44", "visible": False}),
    ("SP-STEP", {"kind": "step", "width_m": 0.25, "color": "#A89F90", "visible": True}),
    ("SP-FURNITURE", {"kind": "furniture", "height_m": 0.6, "color": "#8C582C", "visible": True}),
    ("SP-SITE-BOUNDARY-LABEL", None),
    ("SP-SITE-BOUNDARY", {"kind": "boundary", "width_m": 0.3, "color": "#E8B04A", "visible": True}),
    ("SP-CONT-LABEL", None),
    ("SP-CONT", {"kind": "contour", "width_m": 0.12, "color": "#8C582C", "visible": False}),
    ("SP-DSN-LABEL", None),
    ("SP-DSN", {"kind": "design", "width_m": 0.25, "color": "#B5733E", "visible": True}),
    ("SP-CHECK", {"kind": "other", "width_m": 0.15, "color": "#A85448", "visible": False}),
    ("SP-LVL", None),      # level texts and points: they are the ground model itself
    ("SP-ANNO", None),     # text, dimensions, grid, title, hatching
    ("SP-X-", None),       # layers the designer marked "not needed"
]
OTHER = {"kind": "other", "width_m": 0.15, "color": "#9A9A90", "visible": False}
POINT_KINDS = {"tree", "palm", "manhole", "pole", "furniture"}
SKIP_TYPES = {"TEXT", "MTEXT", "DIMENSION", "HATCH", "LEADER", "MULTILEADER", "ATTDEF", "ATTRIB", "VIEWPORT", "IMAGE"}
TREE_SYMBOL_MAX_M = 15.0   # a closed shape this small on a tree layer is one tree's symbol
GATE_MAX_M = 15.0          # a "gate" longer than this is something else drawn on the gate layer: drawn on the ground


def style_for(layer: str) -> Optional[Dict[str, Any]]:
    """Display style of an SP layer; None = not drawn (annotation, levels, not needed)."""
    for prefix, style in KINDS:
        if layer.upper().startswith(prefix):
            return None if style is None else dict(style)
    return dict(OTHER)


def _cleaned_drawing(project: Project) -> Optional[Path]:
    found = sorted(project.path("survey").glob("*_SP.dxf"), key=lambda f: f.stat().st_mtime)
    return found[-1] if found else None


def _original_names(project: Project) -> Dict[str, List[str]]:
    """SP layer -> the surveyor's layer names that were linked to it in the intake."""
    out: Dict[str, List[str]] = {}
    for e in project.history.entries:
        if e.action == "survey_intake":
            out.clear()
            for old, new in (e.detail.get("links") or {}).items():
                if new:
                    out.setdefault(new, []).append(old)
    return out


class _Ground:
    """Bilinear heights from the ground model, extended over ``bounds`` as the viewer shows it."""

    def __init__(self, project: Project, bounds=None):
        from ..terrain.extend import extend_dem

        d, _ = extend_dem(read_geotiff(project.path("terrain/existing.tif")), bounds)
        self.z, self.cell, (self.x0, self.y0) = d.z, d.cell_size, d.origin

    def __call__(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        r = (self.y0 - y) / self.cell - 0.5
        c = (x - self.x0) / self.cell - 0.5
        R, C = self.z.shape
        r = np.clip(r, 0, R - 1.000001)
        c = np.clip(c, 0, C - 1.000001)
        r0, c0 = np.floor(r).astype(int), np.floor(c).astype(int)
        fr, fc = r - r0, c - c0
        z = self.z
        return ((1 - fr) * ((1 - fc) * z[r0, c0] + fc * z[r0, c0 + 1])
                + fr * ((1 - fc) * z[r0 + 1, c0] + fc * z[r0 + 1, c0 + 1]))


def _densify(xy: np.ndarray, step: float) -> np.ndarray:
    """Add points so no segment is longer than ``step`` (the line then follows the ground)."""
    out = [xy[0]]
    for a, b in zip(xy[:-1], xy[1:]):
        n = int(np.ceil(np.hypot(*(b - a)) / step))
        for i in range(1, n + 1):
            out.append(a + (b - a) * i / n)
    return np.array(out)


def _shapes(e, k: float, explode: bool) -> List[Tuple[str, Any, Dict[str, Any]]]:
    """('line', xy, info) and ('point', (x, y), info) pieces of one drawing entity, in metres."""
    t = e.dxftype()
    if t in SKIP_TYPES:
        return []
    if t == "INSERT":
        p = e.dxf.insert
        if not explode:   # a symbol (tree, pole, manhole): its size on the drawing gives the canopy radius
            info: Dict[str, Any] = {"block": e.dxf.name}
            try:
                from ezdxf import bbox

                ext = bbox.extents([e])
                if ext.has_data:
                    r = max(ext.size.x, ext.size.y) * k / 2
                    if 0.2 <= r <= TREE_SYMBOL_MAX_M / 2:
                        info["radius_m"] = float(r)
            except Exception:
                pass
            return [("point", (p.x * k, p.y * k), info)]
        out = []
        try:
            for i, ve in enumerate(e.virtual_entities()):
                if i > 400:
                    break
                out += _shapes(ve, k, True)
        except Exception:  # a broken block does not stop the import
            pass
        return out or [("point", (p.x * k, p.y * k), {"block": e.dxf.name})]
    if t == "POINT":
        p = e.dxf.location
        return [("point", (p.x * k, p.y * k), {})]
    if t == "CIRCLE":
        c, r = e.dxf.center, float(e.dxf.radius) * k
        if not explode:
            return [("point", (c.x * k, c.y * k), {"radius_m": r})]
        a = np.linspace(0, 2 * np.pi, 25)
        return [("line", np.c_[c.x * k + r * np.cos(a), c.y * k + r * np.sin(a)], {"closed": True})]
    vs = cad._vertices(e)
    if len(vs) < 2:
        return []
    xy = np.array([(x * k, y * k) for x, y, _ in vs])
    closed = cad._closed(e)
    if closed:
        xy = np.vstack([xy, xy[:1]])
    return [("line", xy, {"closed": closed})]


def build(project: Project) -> Dict[str, Any]:
    """Read the cleaned survey drawing and write ``site/survey_layers.json``. Returns its content."""
    drawing = _cleaned_drawing(project)
    if drawing is None:
        raise FileNotFoundError("no cleaned survey drawing in this project (survey/*_SP.dxf): run the survey intake first.")
    if not project.exists("terrain/existing.tif"):
        raise FileNotFoundError("no ground model yet (terrain/existing.tif).")
    lm = project.read_json("terrain/layer_map.json") if project.exists("terrain/layer_map.json") else {}
    k = float(lm.get("units_scale_to_m", 1.0))
    names = _original_names(project)

    by_layer: Dict[str, List[Any]] = {}
    for e in cad.read(drawing).modelspace():
        by_layer.setdefault(e.dxf.layer, []).append(e)

    # read every layer first: the ground is extended to cover what the drawing shows
    read: List[Tuple[str, Dict[str, Any], List[Any]]] = []
    for name in sorted(by_layer):
        style = style_for(name)
        if style is None:
            continue
        kind = style["kind"]
        pieces = []
        for e in by_layer[name]:
            pieces += _shapes(e, k, explode=kind not in POINT_KINDS)
        if kind in ("tree", "palm"):   # tree symbols drawn as small closed shapes: one tree each
            kept = []
            for g, geo, info in pieces:
                if g == "line":
                    ext = np.ptp(geo, axis=0)
                    if max(ext) <= TREE_SYMBOL_MAX_M:
                        kept.append(("point", tuple(geo.mean(axis=0)), {"radius_m": float(max(ext)) / 2}))
                        continue
                kept.append((g, geo, info))
            pieces = _dedupe_points(kept)
        read.append((name, style, _dedupe_lines(pieces)))
    xs = [v for _, st, ps in read if st["kind"] != "other" for g, geo, _ in ps
          for v in (np.asarray(geo)[:, 0] if g == "line" else [geo[0]])]
    ys = [v for _, st, ps in read if st["kind"] != "other" for g, geo, _ in ps
          for v in (np.asarray(geo)[:, 1] if g == "line" else [geo[1]])]
    extent = [float(np.percentile(xs, 0.5)), float(np.percentile(ys, 0.5)),
              float(np.percentile(xs, 99.5)), float(np.percentile(ys, 99.5))] if xs else None
    ground = _Ground(project, extent)
    step = max(1.0, 2 * ground.cell)

    layers = []
    for name, style, pieces in read:
        kind = style["kind"]
        feats = []
        for g, geo, info in pieces:
            if g == "point":
                x, y = geo
                z = float(ground(np.array([x]), np.array([y]))[0])
                f = {"g": "point", "xyz": [round(x, 3), round(y, 3), round(z, 3)]}
                if info.get("radius_m"):
                    f["radius_m"] = round(float(info["radius_m"]), 2)
                if info.get("block"):
                    f["block"] = info["block"]
                feats.append(f)
            else:
                raw = np.asarray(geo, dtype=float)
                xy = _densify(raw, step)
                z = ground(xy[:, 0], xy[:, 1])
                flat = np.round(np.c_[xy, z], 3).ravel().tolist()
                f = {"g": "line", "closed": bool(info.get("closed")), "xyz": flat}
                if kind == "gate" and np.hypot(*np.diff(raw, axis=0).T).sum() > GATE_MAX_M:
                    f["on_ground"] = True   # too long to be a gate: drawn as a line on the ground
                feats.append(f)
        if not feats:
            continue
        sized = sum(1 for f in feats if f.get("radius_m"))
        long_gates = sum(1 for f in feats if f.get("on_ground"))
        if long_gates:
            style["note"] = (f"{long_gates} line(s) on this layer are longer than {GATE_MAX_M:g} m, so they are not "
                             "gates; they are drawn on the ground. Check what the surveyor meant.")
        layers.append({
            "name": name, "title": _title(name), "source_layers": sorted(names.get(name, [])),
            **style, "count": len(feats), **({"sized": sized} if kind in ("tree", "palm") else {}),
            "features": feats,
        })
    out = {"schema_version": "1.1", "drawing": f"survey/{drawing.name}", "extent": extent,
           "note": "Plan positions from the survey, heights from the ground model. Wall, building and tree "
                   "heights are display heights only.",
           "layers": layers}
    project.write_json(REL, out)
    log.info("survey layers: %s", ", ".join(f"{L['name']} ({L['count']})" for L in layers))
    return out


def _dedupe_points(pieces):
    seen, out = set(), []
    for g, geo, info in pieces:
        if g == "point":
            key = (round(geo[0], 1), round(geo[1], 1))
            if key in seen:
                continue
            seen.add(key)
        out.append((g, geo, info))
    return out


def _dedupe_lines(pieces):
    """The same line drawn twice (often once per original layer merged into one SP layer) is kept once."""
    seen, out = set(), []
    for g, geo, info in pieces:
        if g == "line":
            a = np.round(np.asarray(geo) / 0.05).astype(int)
            key = min(tuple(map(tuple, a)), tuple(map(tuple, a[::-1])))
            if key in seen:
                continue
            seen.add(key)
        out.append((g, geo, info))
    return out


def _title(name: str) -> str:
    from ..io.intake import _choices

    for c in _choices():
        if c["name"] == name:
            return c["title"]
    return "Unsorted objects (layer 0)" if name == "0" else f"Other: {name}"


def load(project: Project, rebuild: bool = False) -> Dict[str, Any]:
    """The survey layers, built on first use (projects made before this file existed)."""
    if rebuild or not project.exists(REL):
        return build(project)
    return project.read_json(REL)
