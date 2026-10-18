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
STYLE = 4   # how the layers are modelled; a file made with an older style is rebuilt on load

# SP layer (or prefix) -> how the viewer draws it. height_m: display height above the ground (m).
KINDS: List[Tuple[str, Dict[str, Any]]] = [
    # every wall that encloses the park is shown as 2 m metal fencing
    ("SP-WALL", {"kind": "fence", "height_m": 2.0, "color": "#2F3A33", "visible": True}),
    ("SP-FENCE", {"kind": "fence", "height_m": 2.0, "color": "#2F3A33", "visible": True}),
    ("SP-GATE", {"kind": "gate", "height_m": 2.1, "color": "#26302A", "visible": True}),
    ("SP-BLDG", {"kind": "building", "height_m": 3.0, "color": "#D9CFC0", "visible": True}),   # flat-roofed blocks
    ("SP-WATER-TANK", {"kind": "building", "height_m": 1.5, "color": "#9FB7C4", "visible": True}),
    ("SP-TREE-COCONUT", {"kind": "palm", "height_m": 8.0, "color": "#7A9A55", "visible": True}),
    ("SP-TREE", {"kind": "tree", "height_m": 6.0, "color": "#5D7052", "visible": True}),
    ("SP-PATH", {"kind": "path", "width_m": 0.15, "color": "#D2BF96", "visible": True}),
    ("SP-ROAD-ANNO", None),
    ("SP-ROAD", {"kind": "road", "width_m": 0.2, "color": "#3F4042", "visible": True}),
    ("SP-DRAIN-MANHOLE", {"kind": "manhole", "color": "#5A5A55", "visible": True}),
    ("SP-WELL-RECHARGE", {"kind": "recharge_well", "color": "#6A5ACD", "visible": True}),
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
POINT_KINDS = {"tree", "palm", "manhole", "pole", "furniture", "recharge_well"}
SKIP_TYPES = {"TEXT", "MTEXT", "DIMENSION", "HATCH", "LEADER", "MULTILEADER", "ATTDEF", "ATTRIB", "VIEWPORT", "IMAGE"}
TREE_SYMBOL_MAX_M = 15.0   # a closed shape this small on a tree layer is one tree's symbol
GATE_MAX_M = 15.0          # a "gate" longer than this is something else drawn on the gate layer: drawn on the ground
GATE_WIDTH_M = (1.0, 8.0)  # a gate symbol's long side, clamped to a sensible gate width
MAX_OTHER_FEATURES = 3000  # unsorted layers (title blocks, hatching) are capped so the viewer stays quick
MIN_SURFACE_M2 = 1.0      # smaller road or path surfaces are slivers between drawn lines
PATH_MAX_WIDTH_M = 5.0     # a band between path lines this narrow (on average) is path surface
ROAD_MAX_WIDTH_M = 25.0    # a band between road lines narrower than this is road surface
ROAD_END_GAP_M = 30.0      # loose road ends this close are joined (the break symbols at a road's ends)
EDGE_COLOR = {"road": "#8A8A85", "path": "#B9A27A"}   # kerb and path edge lines


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


def park_boundary(project: Project):
    """The park's boundary polygon as surveyed, or None. (Delineation replaces site/boundary.geojson with the
    part of the park the ground model covers and keeps the survey's boundary in terrain/survey_boundary.geojson.)"""
    from shapely.geometry import shape

    rel = "terrain/survey_boundary.geojson" if project.exists("terrain/survey_boundary.geojson") else "site/boundary.geojson"
    if not project.exists(rel):
        return None
    polys = [shape(f["geometry"]) for f in project.read_geojson(rel).get("features", [])
             if f.get("geometry") and f["geometry"]["type"] in ("Polygon", "MultiPolygon")]
    return max(polys, key=lambda g: g.area) if polys else None


class _Ground:
    """Bilinear heights from the ground model, extended over ``bounds`` as the viewer shows it."""

    def __init__(self, project: Project, bounds=None):
        from ..terrain.extend import extend_dem

        d, _ = extend_dem(read_geotiff(project.path("terrain/existing.tif")), bounds, boundary=park_boundary(project))
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

    # gates first: each gate symbol becomes one gate (position, width, direction along the fence),
    # and the fences get an opening there
    fence_lines = [geo for _, st, ps in read if st["kind"] in ("fence", "boundary") for g, geo, _ in ps if g == "line"]
    gates_by_layer = {name: _gates(ps, fence_lines) for name, st, ps in read if st["kind"] == "gate"}
    openings = [gt["opening"] for gl in gates_by_layer.values() for gt in gl[0]]

    layers = []
    for name, style, pieces in read:
        kind = style["kind"]
        feats = []
        notes = []
        if kind == "gate":
            gates, rest = gates_by_layer[name]
            for gt in gates:
                z = float(ground(np.array([gt["x"]]), np.array([gt["y"]]))[0])
                feats.append({"g": "point", "xyz": [round(gt["x"], 3), round(gt["y"], 3), round(z, 3)],
                              "width_m": round(gt["width_m"], 2), "angle_deg": round(gt["angle_deg"], 1)})
            pieces = [("line", geo, {**info, "on_ground": True}) for geo, info in rest]
            if rest:
                notes.append(f"{len(rest)} line(s) on this layer are longer than {GATE_MAX_M:g} m, so they are not "
                             "gates; they are drawn on the ground. Check what the surveyor meant.")
        elif kind == "fence" and openings:
            pieces = _cut(pieces, openings)
        elif kind == "boundary" and _needs_fence(pieces, read):
            # the park is enclosed by fencing: where the drawing shows none along the boundary, it is fenced
            pieces = _cut(pieces, openings) if openings else pieces
            style.update(fenced=True, height_m=2.0)
            notes.append("No wall or fence is drawn along this boundary, so it is shown fenced (2 m).")
        elif kind == "building":
            pieces, loose = _footprints(pieces)
            if loose:
                notes.append(f"{loose} line(s) on this layer do not close into a building outline; left out.")
        elif kind in ("road", "path"):
            surfaces = _road_surfaces(pieces, park_boundary(project)) if kind == "road" else _path_surfaces(pieces)
            for poly in surfaces:
                m = _drape_polygon(poly, ground, step)
                if m:
                    feats.append(m)
            pieces = [(g, geo, {**info, "color": EDGE_COLOR[kind]}) for g, geo, info in pieces]
            if not surfaces:
                notes.append("its lines do not enclose a surface, so only the edges are drawn.")
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
                continue
            else:
                raw = np.asarray(geo, dtype=float)
                xy = _densify(raw, step)
                z = ground(xy[:, 0], xy[:, 1])
                flat = np.round(np.c_[xy, z], 3).ravel().tolist()
                f = {"g": "line", "closed": bool(info.get("closed")), "xyz": flat}
                if info.get("on_ground"):
                    f["on_ground"] = True
                if info.get("color"):
                    f["color"] = info["color"]
                feats.append(f)
        if not feats:
            continue
        if kind == "other" and len(feats) > MAX_OTHER_FEATURES:
            notes.append(f"{len(feats)} objects: only the first {MAX_OTHER_FEATURES} are drawn (unsorted layer).")
            feats = feats[:MAX_OTHER_FEATURES]
        sized = sum(1 for f in feats if f.get("radius_m"))
        if notes:
            style["note"] = " ".join(notes)
        layers.append({
            "name": name, "title": _title(name), "source_layers": sorted(names.get(name, [])),
            **style, "count": len(feats), **({"sized": sized} if kind in ("tree", "palm") else {}),
            "features": feats,
        })
    out = {"schema_version": "1.1", "style": STYLE, "drawing": f"survey/{drawing.name}", "extent": extent,
           "note": "Plan positions from the survey, heights from the ground model. Wall, building and tree "
                   "heights are display heights only.",
           "layers": layers}
    project.write_json(REL, out)
    log.info("survey layers: %s", ", ".join(f"{L['name']} ({L['count']})" for L in layers))
    return out


def _gates(pieces, fence_lines):
    """Gate symbols -> gates. Pieces closer than 1 m form one symbol; its long side is the gate's width,
    its direction follows the nearest fence (within 6 m). Returns (gates, other lines)."""
    from shapely.geometry import LineString, MultiPoint, Point
    from shapely.ops import nearest_points, unary_union

    lines = [np.asarray(geo, dtype=float) for g, geo, _ in pieces if g == "line"]
    infos = [info for g, _, info in pieces if g == "line"]
    pts = [np.asarray(geo, dtype=float) for g, geo, _ in pieces if g == "point"]
    shapes = [LineString(a) for a in lines] + [Point(*p) for p in pts]
    if not shapes:
        return [], []
    blobs = unary_union([g.buffer(0.5) for g in shapes])
    blobs = list(getattr(blobs, "geoms", [blobs]))
    fences = unary_union([LineString(a) for a in fence_lines if len(a) >= 2]) if fence_lines else None
    gates, rest = [], []
    for b in blobs:
        members = [i for i, g in enumerate(shapes) if g.intersects(b)]
        coords = [c for i in members for c in shapes[i].coords]
        rect = MultiPoint(coords).minimum_rotated_rectangle
        rc = np.asarray(rect.exterior.coords) if rect.geom_type == "Polygon" else np.asarray(coords)
        sides = np.diff(rc, axis=0)[:2] if len(rc) >= 2 else np.array([[1.0, 0.0]])
        lengths = np.hypot(sides[:, 0], sides[:, 1])
        long_side = float(lengths.max()) if len(lengths) else 0.0
        if long_side > GATE_MAX_M:
            rest += [(lines[i], infos[i]) for i in members if i < len(lines)]
            continue
        c = rect.centroid
        direction = sides[int(np.argmax(lengths))] if len(lengths) else np.array([1.0, 0.0])
        if fences is not None and fences.distance(c) <= 6.0:   # sit on the fence, along it
            on = nearest_points(fences, c)[0]
            seg = _segment_near(fences, on)
            if seg is not None:
                direction = seg
            c = on
        width = float(np.clip(long_side, *GATE_WIDTH_M))
        ang = float(np.degrees(np.arctan2(direction[1], direction[0])))
        u = np.array([np.cos(np.radians(ang)), np.sin(np.radians(ang))])
        a, b2 = np.array([c.x, c.y]) - u * width / 2, np.array([c.x, c.y]) + u * width / 2
        gates.append({"x": float(c.x), "y": float(c.y), "width_m": width, "angle_deg": ang,
                      "opening": LineString([a, b2]).buffer(0.6, cap_style="flat")})
    return gates, rest


def _needs_fence(boundary_pieces, read) -> bool:
    """True when less than half of the park boundary has a drawn wall or fence within 1.5 m of it."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    bnd = [LineString(geo) for g, geo, _ in boundary_pieces if g == "line" and len(geo) >= 2]
    fences = [LineString(geo) for _, st, ps in read if st["kind"] == "fence" for g, geo, _ in ps if g == "line" and len(geo) >= 2]
    if not bnd:
        return False
    total = sum(b.length for b in bnd)
    if not fences or total <= 0:
        return True
    near = unary_union(fences).buffer(1.5)
    return sum(b.intersection(near).length for b in bnd) / total < 0.5


def _segment_near(lines, p) -> Optional[np.ndarray]:
    """Direction of the line segment nearest to point p."""
    best, out = 1e9, None
    for ln in getattr(lines, "geoms", [lines]):
        c = np.asarray(ln.coords)
        for a, b in zip(c[:-1], c[1:]):
            from shapely.geometry import LineString

            d = LineString([a, b]).distance(p)
            if d < best:
                best, out = d, b - a
    return out


def _cut(pieces, openings):
    """Fence lines with the gate openings taken out."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    hole = unary_union(openings)
    out = []
    for g, geo, info in pieces:
        if g != "line":
            out.append((g, geo, info))
            continue
        left = LineString(geo).difference(hole)
        for part in getattr(left, "geoms", [left]):
            if part.geom_type == "LineString" and part.length > 0.05:
                out.append(("line", np.asarray(part.coords), {"closed": False}))
    return out


def _footprints(pieces):
    """Building outlines: closed shapes as they are, loose lines joined into closed shapes where they meet.
    Returns (closed outlines, number of lines that close nothing)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union

    lines = [LineString(geo) for g, geo, _ in pieces if g == "line" and len(geo) >= 2]
    if not lines:
        return pieces, 0
    faces = [f for f in polygonize(unary_union(lines)) if f.area > 1.0]
    # a face inside another face is a courtyard or detail: keep the outer outline
    faces = [f for f in faces if not any(o is not f and o.contains(f.representative_point()) and o.area > f.area
                                         for o in faces)]
    used = unary_union([f.exterior for f in faces]).buffer(0.05) if faces else None
    loose = sum(1 for ln in lines if used is None or not used.contains(ln))
    out = [("line", np.asarray(f.exterior.coords), {"closed": True}) for f in faces]
    return out + [(g, geo, info) for g, geo, info in pieces if g == "point"], loose


def _road_surfaces(pieces, boundary):
    """Road surface between the kerb lines. The loose ends of the kerbs (at the break symbols where the
    survey stops) are joined across each road, then every band narrower than ROAD_MAX_WIDTH_M that is
    not the park itself is road."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    lines = [LineString(geo) for g, geo, _ in pieces if g == "line" and len(geo) >= 2]
    if not lines:
        return []
    ends = []
    for ln in lines:
        if not ln.is_ring:
            ends += [np.asarray(ln.coords[0]), np.asarray(ln.coords[-1])]
    joins, used = [], set()
    for i, a in enumerate(ends):
        if i in used:
            continue
        best = None
        for j, b in enumerate(ends):
            if j == i or j in used or (i // 2 == j // 2):
                continue
            d = float(np.hypot(*(a - b)))
            if d <= ROAD_END_GAP_M and (best is None or d < best[0]):
                best = (d, j)
        if best is not None:
            used |= {i, best[1]}
            joins.append(LineString([a, ends[best[1]]]))
    faces = list(polygonize(unary_union(lines + joins)))
    park = boundary.representative_point() if boundary is not None else None
    out = []
    for f in faces:
        if park is not None and f.contains(park):   # the park block itself (a ring of road has the park as its hole)
            continue
        if 2 * f.area / f.length <= ROAD_MAX_WIDTH_M:
            out.append(f)
    return out


def _path_surfaces(pieces):
    """Path surface: the narrow bands between path lines (a band of the same width all round)."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    lines = [LineString(geo) for g, geo, _ in pieces if g == "line" and len(geo) >= 2]
    if not lines:
        return []
    faces = list(polygonize(unary_union(lines)))
    out = []
    for f in faces:
        # a face with a hole is a band between two rings (the hole is a separate face)
        if 2 * f.area / f.length <= PATH_MAX_WIDTH_M:
            out.append(f)
    return out


def _drape_polygon(poly, ground, step: float) -> Optional[Dict[str, Any]]:
    """A polygon as a triangle mesh lying on the ground: its outline (densified) and a grid of points
    inside it, triangulated; triangles outside the polygon (holes, concave bays) are dropped."""
    from scipy.spatial import Delaunay, QhullError
    from shapely import contains_xy

    if poly.is_empty or poly.area < MIN_SURFACE_M2:   # slivers between nearly touching lines are not surfaces
        return None
    rings = [np.asarray(poly.exterior.coords)] + [np.asarray(r.coords) for r in poly.interiors]
    pts = np.vstack([_densify(r, step) for r in rings])
    x0, y0, x1, y1 = poly.bounds
    gx, gy = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
    inner = np.c_[gx.ravel(), gy.ravel()]
    if len(inner):
        inner = inner[contains_xy(poly.buffer(-step * 0.3), inner[:, 0], inner[:, 1])]
        pts = np.vstack([pts, inner])
    pts = np.unique(np.round(pts, 3), axis=0)
    if len(pts) < 3:
        return None
    try:
        tri = Delaunay(pts)
    except QhullError:
        try:   # nearly flat or collinear points: nudge them slightly so a triangulation exists
            tri = Delaunay(pts, qhull_options="QJ")
        except QhullError:
            log.warning("surface of %.1f m2 could not be triangulated; left out", poly.area)
            return None
    cen = pts[tri.simplices].mean(axis=1)
    keep = contains_xy(poly.buffer(1e-3), cen[:, 0], cen[:, 1])
    simp = tri.simplices[keep]
    if not len(simp):
        return None
    used = np.unique(simp)
    remap = -np.ones(len(pts), dtype=int)
    remap[used] = np.arange(len(used))
    p = pts[used]
    z = ground(p[:, 0], p[:, 1])
    return {"g": "mesh", "xyz": np.round(np.c_[p, z], 3).ravel().tolist(), "tri": remap[simp].ravel().tolist()}


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
    out = project.read_json(REL)
    return out if out.get("style") == STYLE else build(project)
