"""A 3D model (Rhino .3dm or COLLADA .dae) as the ground of a flow and pooling study.

1. ``inspect(path)`` reads the model and lists its layers with what each holds, the units and the size, and
   suggests a role for each layer: ground, building, boundary or ignore.
2. ``finish(...)`` creates the ``.sponge`` project with the model inside it (``survey/``) and turns the model into
   the same ground grid a survey gives (``terrain/existing.tif``), so flow, ponding and the storm runs read it as usual.

The grid holds the highest ground or building surface over each cell. Each building becomes one flat block (rain
runs off it; a parapet or a dished roof must not read as a pond). Thin walls and check dams keep their own heights and
are written to every cell they touch, so water cannot slip between grid points. A boundary wall sets the site: the
ground inside it, with every exit closed (:mod:`..site.outfalls`) and the gaps in the wall listed as possible inlets and
outlets. Water surfaces are left out of the ground, so the beds under them are what the water fills. Gaps enclosed by
the model are filled across and reported: left empty they would count as the edge of the site, and water would leave
through them.

A model with no usable layers (every object named alike, as Rhino exports to COLLADA) is sorted by material instead.

Given with the site's survey project and the design's plan (DXF), the model is moved onto the survey's coordinates and
levels, so the design and the existing site can be laid over each other. Levels always come from the model: the plan gives
positions only (where the model's boundary wall goes, and the recharge wells). The proposed contours are drawn from the
model, the existing ones from the survey.

``rhino3dm`` cannot mesh a surface: NURBS and polysurface objects are read through the meshes Rhino saved with them.
Objects without one are counted and reported, never guessed at.
"""

from __future__ import annotations

import logging
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from numba import njit

log = logging.getLogger(__name__)

SUFFIXES = (".3dm", ".dae")
ROLES = ("ground", "nbs", "building", "barrier", "boundary_wall", "water", "boundary", "ignore")
ROLE_COLOR = {"ground": "#8FB46C", "nbs": "#55803F", "building": "#D8CDB8", "barrier": "#A89F8E", "boundary_wall": "#C8C2B4",
              "water": "#3F8FD2"}
# what a thing is, from its layer's name: the model's own paint colours are only working colours
NAME_COLOR = [(r"\b(rg|bs)\b|rain ?garden|bio ?swale|swale", "#55803F"), (r"foot ?path|path|sidewalk|walkway", "#CDBEA4"),
              (r"kerb|curb", "#B8B4A8"), (r"rail|fence", "#6B6F72"), (r"baffle|check ?dam", "#A89F8E"), (r"metal|plate", "#7A7F85"),
              (r"drain|trench", "#8E979C"), (r"play", "#D9A066"), (r"gazebo", "#E4DCCB"), (r"compost", "#7A5C3E"),
              (r"toilet|block|building|built", "#D8CDB8"), (r"wall", "#C8C2B4"), (r"terrain|lawn|grass|ground|model", "#8FB46C")]
NBS_RATE_MM_HR = 25.0      # bottom of the ideal media rate of a rain garden (HC 4.2 p.12: >13, ideally 25-50 mm/hr) and of a
#                            bioswale's filter media (HC 4.7 p.8: 1.0-6.0 in/hr)
SOURCE = "site/model_source.json"
EXISTING_PROJECT = "survey/existing.sponge"   # the survey's project, for before and after
SURVEY_GROUND = "terrain/survey_existing.tif"   # the existing ground, from the survey project (on the same coordinates)
_PLAN_WALL = re.compile(r"boundary.?wall|compound")
_PLAN_WELL = re.compile(r"recharge|percolation|\bwell")
_PLAN_NBS = re.compile(r"swale|rain.?garden|bioretention")
PLAN_NBS_SHARE = 0.3       # at least this much of a material's plan lies inside the plan's swales and rain gardens
LINE_UP_WARN_M = 1.0       # plan and model walls differing in size by more than this are worth checking
ALIGN_WALL_WARN_M = 1.0    # plan and model walls further apart than this are not lined up
ALIGN_SITE_WARN = 0.9      # survey and model sites overlapping less than this (intersection over union) are not the same site
CONTOUR_STEPS = (0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0)
NBS_ZONES = "site/nbs_zones.geojson"
NBS_RATE_KEY = "nbs.design_model.media_rate_mm_hr"
RHINO_UNITS = {"Microns": 1e-6, "Millimeters": 1e-3, "Centimeters": 0.01, "Decimeters": 0.1, "Meters": 1.0,
               "Dekameters": 10.0, "Hectometers": 100.0, "Kilometers": 1000.0, "Inches": 0.0254, "Feet": 0.3048,
               "Yards": 0.9144, "Miles": 1609.344}
UNIT_CHOICES = [("Metres", 1.0), ("Centimetres", 0.01), ("Millimetres", 0.001), ("Feet", 0.3048), ("Inches", 0.0254)]
MAX_DEPTH = 16             # nested blocks or nodes deeper than this are a cycle or a broken file
CURVE_SAMPLES = 200        # points taken along a smooth boundary curve
DEFAULT_MAX_CELLS = 4_000_000   # the suggested cell size keeps a large model to about this many cells
HARD_MAX_CELLS = 25_000_000     # beyond this the grid will not fit in memory comfortably: ask for a coarser one
HOLE_WARN_SHARE = 0.02     # filled gaps above this share of the site are worth checking
SURROUNDINGS_MIN_M2 = 1000.0     # a plan this large on this few triangles per m2 is a plain block of the surroundings,
SURROUNDINGS_MAX_TRI_M2 = 0.02   # not a modelled site surface
WALL_HULL_M = 1.0          # a boundary wall runs within this distance of the outline of the whole site ...
WALL_HULL_SHARE = 0.8      # ... for this share of its points
THIN_FLAT_SHARE = 0.6      # less of its surface than this facing up: a thin upright thing, not a surface
MAX_WALL_GAP_CELLS = 128   # gaps in a boundary wall up to about this many cells are bridged to find what it encloses
WALL_REACH_CELLS = 4       # how far from the site's edge the wall's top is looked for
EDGE_HEIGHT_MAX_M = 3.0    # the most Site setup > Outfalls takes as an edge height
MODEL_COURANT = 0.35       # deep ponds on a fine grid oscillate at the default 0.7 (the time step factor of the 2D model)

_IGNORE = re.compile(r"tree|shrub|plant|veg|canop|foliage|people|person|human|figure|car\b|vehicle|furnitur|bench|"
                     r"light|lamp|sign|context|background|annotation|sun\b|camera")
_BOUNDARY = re.compile(r"boundar|site.?edge|site.?limit|extent")
_NBS = re.compile(r"\b(rg|bs)\b|rain ?garden|bio ?swale|swale")
_BUILDING = re.compile(r"build|bldg|house|structur|roof|gazebo|pavilion|toilet|kiosk")
_GROUND = re.compile(r"terrain|ground|topo|grade|grading|landform|contour|\bdem\b|\bland\b|surface|\bsite\b")


# what an exporter calls an object when it has no name of its own: the kind of object, not a part of the site
_GENERIC_LABEL = re.compile(r"(brep|mesh|extrusion|subd|surface|curve|polysurface|group|default|node|object|"
                            r"instance|instance-def.*|component.*|sketchup)[\s_\-#\d]*$", re.I)


class ModelError(ValueError):
    """A problem with the model, in words the designer can act on."""


@dataclass
class Layer:
    tris: List[np.ndarray] = field(default_factory=list)   # (n, 3, 3) arrays, model units
    curves: List[np.ndarray] = field(default_factory=list)  # closed curves, (n, 3) arrays, model units
    objects: int = 0
    unmeshed: int = 0      # objects with a surface but no mesh to read
    color: Optional[str] = None    # "#rrggbb" of its material, for a model sorted by material

    def triangles(self) -> np.ndarray:
        return np.concatenate(self.tris) if self.tris else np.empty((0, 3, 3))


@dataclass
class Model:
    format: str
    units: str
    scale_to_m: Optional[float]   # None: the file does not say
    up_axis: str = "Z"
    layers: Dict[str, Layer] = field(default_factory=dict)
    unread: int = 0        # geometry kinds this reader does not take (triangle strips and the like)
    by_material: bool = False      # the "layers" are the model's materials

    def layer(self, name: str) -> Layer:
        return self.layers.setdefault(name or "Default", Layer())


# ------------------------------------------------------------------ Rhino
def _rhino_matrix(x) -> np.ndarray:
    return np.array([[getattr(x, f"M{r}{c}") for c in range(4)] for r in range(4)], float)


def _apply(m: Optional[np.ndarray], pts: np.ndarray) -> np.ndarray:
    return pts if m is None else pts @ m[:3, :3].T + m[:3, 3]


def _rhino_mesh(mesh, m: Optional[np.ndarray]) -> np.ndarray:
    if not len(mesh.Faces):
        return np.empty((0, 3, 3))
    v = _apply(m, np.array([(p.X, p.Y, p.Z) for p in (mesh.Vertices[i] for i in range(len(mesh.Vertices)))], float))
    f = np.array([tuple(mesh.Faces[i])[:4] for i in range(len(mesh.Faces))], int)
    quads = f[f[:, 2] != f[:, 3]]
    return np.concatenate([v[f[:, [0, 1, 2]]], v[quads[:, [0, 2, 3]]]])


def _rhino_curve(curve, m: Optional[np.ndarray]) -> Optional[np.ndarray]:
    if not curve.IsClosed:
        return None
    if hasattr(curve, "PointCount") and hasattr(curve, "Point"):   # a polyline: its own corners
        pts = [curve.Point(i) for i in range(curve.PointCount)]
    else:
        pts = [curve.PointAt(t) for t in np.linspace(curve.Domain.T0, curve.Domain.T1, CURVE_SAMPLES)]
    return _apply(m, np.array([(p.X, p.Y, p.Z) for p in pts], float))


def _rhino_add(r, f3, geom, layer: Layer, m: Optional[np.ndarray], depth: int = 0) -> None:
    if isinstance(geom, r.Mesh):
        layer.tris.append(_rhino_mesh(geom, m))
    elif isinstance(geom, r.Brep):
        meshes = [face.GetMesh(r.MeshType.Any) for face in geom.Faces]
        if not all(meshes):
            layer.unmeshed += 1
        layer.tris += [_rhino_mesh(x, m) for x in meshes if x]
    elif isinstance(geom, r.Extrusion):
        mesh = geom.GetMesh(r.MeshType.Any)
        if mesh:
            layer.tris.append(_rhino_mesh(mesh, m))
        else:
            layer.unmeshed += 1
    elif isinstance(geom, (r.Surface, r.SubD)):
        layer.unmeshed += 1
    elif isinstance(geom, r.Curve):
        c = _rhino_curve(geom, m)
        if c is not None:
            layer.curves.append(c)
    elif isinstance(geom, r.InstanceReference) and depth < MAX_DEPTH:
        d = f3.InstanceDefinitions.FindId(geom.ParentIdefId)
        x = _rhino_matrix(geom.Xform)
        x = x if m is None else m @ x
        for oid in (d.GetObjectIds() if d else []):
            o = f3.Objects.FindId(oid)
            if o is not None:
                _rhino_add(r, f3, o.Geometry, layer, x, depth + 1)


def _read_3dm(path: Path) -> Model:
    import rhino3dm as r

    f3 = r.File3dm.Read(str(path))
    if f3 is None:
        raise ModelError(f"could not read {path.name} as a Rhino file (it may be damaged, or from a newer Rhino).")
    unit = f3.Settings.ModelUnitSystem.name
    model = Model("Rhino", unit, RHINO_UNITS.get(unit))
    names = [L.FullPath or L.Name for L in f3.Layers]
    colors = {n: "#%02x%02x%02x" % tuple(L.Color[:3]) for n, L in zip(names, f3.Layers)}
    # a block's own geometry is listed among the objects too: it only stands where the block is placed
    in_blocks = {str(oid) for d in f3.InstanceDefinitions for oid in d.GetObjectIds()}
    for o in f3.Objects:
        if str(o.Attributes.Id) in in_blocks:
            continue
        i = o.Attributes.LayerIndex
        layer = model.layer(names[i] if 0 <= i < len(names) else "Default")
        layer.color = colors.get(names[i]) if 0 <= i < len(names) else None
        layer.objects += 1
        _rhino_add(r, f3, o.Geometry, layer, None)
    return model


# ------------------------------------------------------------------ COLLADA
def _floats(text: Optional[str]) -> np.ndarray:
    return np.array((text or "").split(), float)


def _ints(text: Optional[str]) -> np.ndarray:
    return np.array((text or "").split(), int)


def _dae_geometry(geo: ET.Element) -> Tuple[List[Tuple[str, np.ndarray]], int]:
    """(material symbol, triangles) of one <geometry> (untransformed), and how many primitives this reader does not take."""
    mesh = geo.find("mesh")
    if mesh is None:
        return [], 0
    sources = {s.get("id"): s for s in mesh.findall("source")}
    verts = mesh.find("vertices")
    pos = next((i.get("source", "")[1:] for i in (verts.findall("input") if verts is not None else [])
                if i.get("semantic") == "POSITION"), None)
    src = sources.get(pos)
    arr = src.find("float_array") if src is not None else None
    if arr is None:
        return [], 0
    acc = src.find("technique_common/accessor")
    stride = int(acc.get("stride", 3)) if acc is not None else 3
    v = _floats(arr.text).reshape(-1, stride)[:, :3]
    out, unread = [], 0
    for prim in mesh:
        if prim.tag in ("source", "vertices", "extra", "lines", "linestrips"):   # edges hold no surface
            continue
        if prim.tag not in ("triangles", "polylist", "polygons"):
            unread += 1
            continue
        inputs = prim.findall("input")
        step = max((int(i.get("offset", 0)) for i in inputs), default=0) + 1
        off = next((int(i.get("offset", 0)) for i in inputs if i.get("semantic") == "VERTEX"), 0)
        if prim.tag == "triangles":
            idx = _ints(prim.findtext("p"))[off::step]
            out.append((prim.get("material", ""), v[idx[:len(idx) // 3 * 3].reshape(-1, 3)]))
            continue
        if prim.tag == "polylist":
            idx, at, loops = _ints(prim.findtext("p"))[off::step], 0, []
            for c in _ints(prim.findtext("vcount")):
                loops.append(idx[at:at + c])
                at += c
        else:
            loops = [_ints(p.text)[off::step] for p in prim.findall("p")]
        fan = [(L[0], L[i], L[i + 1]) for L in loops for i in range(1, len(L) - 1)]
        if fan:
            out.append((prim.get("material", ""), v[np.array(fan, int)]))
    return out, unread


def _dae_materials(root: ET.Element) -> Dict[str, Tuple[str, Optional[str]]]:
    """Material id -> (name, "#rrggbb" of its diffuse colour, if it has one)."""
    effects = {e.get("id"): e for e in root.findall("library_effects/effect")}
    out: Dict[str, Tuple[str, Optional[str]]] = {}
    for m in root.findall("library_materials/material"):
        ie = m.find("instance_effect")
        e = effects.get(ie.get("url", "").lstrip("#")) if ie is not None else None
        c = e.find(".//diffuse/color") if e is not None else None
        rgb = _floats(c.text)[:3] if c is not None else None
        out[m.get("id")] = (m.get("name") or m.get("id") or "material",
                            "#%02x%02x%02x" % tuple(int(round(float(x) * 255)) for x in rgb)
                            if rgb is not None and len(rgb) == 3 else None)
    return out


def _dae_transform(node: ET.Element) -> np.ndarray:
    m = np.eye(4)
    for e in node:
        t = np.eye(4)
        if e.tag == "matrix":
            t = _floats(e.text).reshape(4, 4)
        elif e.tag == "translate":
            t[:3, 3] = _floats(e.text)[:3]
        elif e.tag == "scale":
            t[:3, :3] = np.diag(_floats(e.text)[:3])
        elif e.tag == "rotate":
            a = _floats(e.text)
            n = a[:3] / (np.linalg.norm(a[:3]) or 1.0)
            k = np.array([[0, -n[2], n[1]], [n[2], 0, -n[0]], [-n[1], n[0], 0]])
            th = np.radians(a[3])
            t[:3, :3] = np.eye(3) + np.sin(th) * k + (1 - np.cos(th)) * k @ k
        else:
            continue
        m = m @ t
    return m


def _read_dae(path: Path) -> Model:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as ex:
        raise ModelError(f"could not read {path.name} as a COLLADA file: {ex}")
    for e in root.iter():
        e.tag = e.tag.split("}")[-1]   # no namespaces
    if root.tag != "COLLADA":
        raise ModelError(f"{path.name} is not a COLLADA file.")
    unit = root.find("asset/unit")
    up = (root.findtext("asset/up_axis") or "Y_UP").strip().upper()[0]
    model = Model("COLLADA", unit.get("name", "file units") if unit is not None else "not stated",
                  float(unit.get("meter", 1.0)) if unit is not None else None, up)
    geos = {g.get("id"): g for g in root.findall("library_geometries/geometry")}
    lib_nodes = {n.get("id"): n for n in root.findall("library_nodes/node")}
    materials = _dae_materials(root)
    cache: Dict[str, List[Tuple[str, np.ndarray]]] = {}
    groups: Dict[Tuple[str, str], Layer] = {}   # (node label, material id)

    def add_geometry(inst: ET.Element, m: np.ndarray, name: str) -> None:
        gid = inst.get("url", "").lstrip("#")
        if gid not in geos:
            return
        if gid not in cache:
            cache[gid], unread = _dae_geometry(geos[gid])
            model.unread += unread
        bind = {b.get("symbol"): b.get("target", "").lstrip("#") for b in inst.iter("instance_material")}
        for symbol, t in cache[gid]:
            g = groups.setdefault((name, bind.get(symbol, symbol)), Layer())
            g.objects += 1
            if len(t):
                g.tris.append(_apply(m, t.reshape(-1, 3)).reshape(-1, 3, 3))

    def walk(node: ET.Element, m: np.ndarray, label: str, name_it: bool, only_child: bool, depth: int) -> None:
        # the layer: the node's own layer attribute, else the first level with more than one node
        # (SketchUp and others wrap the whole scene in one node)
        if depth > MAX_DEPTH:
            return
        own = (node.get("layer") or "").split(" ")[0]
        label = own or ((node.get("name") or node.get("id") or label) if name_it else label)
        m = m @ _dae_transform(node)
        for g in node.findall("instance_geometry"):
            add_geometry(g, m, label)
        kids = node.findall("node") + [lib_nodes[i.get("url", "").lstrip("#")] for i in node.findall("instance_node")
                                       if i.get("url", "").lstrip("#") in lib_nodes]
        for k in kids:
            walk(k, m, label, name_it and only_child, len(kids) == 1, depth + 1)

    scene = root.find("scene/instance_visual_scene")
    scenes = {s.get("id"): s for s in root.findall("library_visual_scenes/visual_scene")}
    vs = scenes.get(scene.get("url", "").lstrip("#")) if scene is not None else next(iter(scenes.values()), None)
    tops = vs.findall("node") if vs is not None else []
    for n in tops:
        walk(n, np.eye(4), "Default", True, len(tops) == 1, 0)
    # no usable layers (every object named alike): the materials are what tells the parts apart
    model.by_material = all(_GENERIC_LABEL.match(k[0]) for k in groups) and len({k[1] for k in groups}) >= 2
    for (label, mat), g in groups.items():
        name, color = materials.get(mat, (mat, None))
        layer = model.layer(f"{color or 'no colour'}  {name}" if model.by_material else label)
        layer.tris += g.tris
        layer.objects += g.objects
        layer.color = color if model.by_material else None
    swap = {"Y": lambda p: np.stack([p[..., 0], -p[..., 2], p[..., 1]], -1),
            "X": lambda p: np.stack([-p[..., 1], p[..., 0], p[..., 2]], -1)}.get(up)
    if swap:
        for L in model.layers.values():
            L.tris = [swap(t) for t in L.tris]
    return model


def read(path: Path) -> Model:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUFFIXES:
        raise ModelError("choose a Rhino (.3dm) or COLLADA (.dae) model.")
    if not path.is_file():
        raise ModelError(f"the file {path} does not exist.")
    return _read_3dm(path) if suffix == ".3dm" else _read_dae(path)


# ------------------------------------------------------------------ what the model holds
def _suggest(name: str, has_tris: bool, has_curves: bool) -> Optional[str]:
    n = re.sub(r"[:_\-]+", " ", name.lower())
    if _BOUNDARY.search(n) and has_curves:
        return "boundary"
    if not has_tris or _IGNORE.search(n):
        return "ignore"
    if _NBS.search(n):
        return "nbs"
    if _BUILDING.search(n):
        return "building"
    return "ground" if _GROUND.search(n) else None


def _suggest_by_shape(rows: List[Dict[str, Any]], layers: Dict[str, Layer]) -> None:
    """Roles from what each row's triangles look like, where its name says nothing. Only a suggestion: the designer sees
    every row. Plain blocks of the surroundings and water first, then what is left is the site, whose outline tells a
    boundary wall; thin upright things are walls and check dams, the rest ground. A name that says what a thing is
    (``_suggest``) stands, except that the surroundings are told by shape: "Buildings" may be the neighbours."""
    from shapely import distance, points
    from shapely.geometry import MultiPoint

    def shape_of(t):
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        plan, area = float(np.abs(n[:, 2]).sum() / 2), float(np.linalg.norm(n, axis=1).sum() / 2)
        return plan, (plan / area if area > 0 else 0.0)

    site, rng = [], np.random.default_rng(0)
    for r in rows:
        t = layers[r["layer"]].triangles()
        if not len(t):
            r["role"] = r["role"] if r["role"] == "boundary" else "ignore"
            continue
        plan, _ = shape_of(t)
        c = r.get("color")
        rgb = [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)] if c else None   # dark blue is the water, whatever its layer
        if plan >= SURROUNDINGS_MIN_M2 and len(t) / plan < SURROUNDINGS_MAX_TRI_M2:
            r["role"] = "ignore"
        elif rgb and rgb[2] > 0.4 and rgb[0] < 0.25 and rgb[1] < 0.25:
            r["role"] = "water"
        elif r["role"] != "ignore":
            site.append((r, t))
    if not site:
        return
    every = np.concatenate([t.reshape(-1, 3)[:, :2] for _, t in site])
    hull = MultiPoint(every[rng.choice(len(every), min(len(every), 20000), replace=False)]).convex_hull.exterior
    for r, t in site:
        _, flat = shape_of(t)
        pts = t.reshape(-1, 3)[:, :2]
        pts = pts[rng.choice(len(pts), min(len(pts), 2000), replace=False)]
        near = float((distance(points(pts), hull) <= WALL_HULL_M).mean())
        if flat < THIN_FLAT_SHARE and near >= WALL_HULL_SHARE:
            r["role"] = "boundary_wall"
        elif r["role"] is None:
            r["role"] = "barrier" if flat < THIN_FLAT_SHARE else "ground"


def _extent(tris: np.ndarray) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    if not len(tris):
        return None
    p = tris.reshape(-1, 3)
    return p.min(axis=0), p.max(axis=0)


def _cell_for(width_m: float, depth_m: float, base_m: float) -> float:
    """The project's usual cell size, coarser only when a large model would not fit in ``DEFAULT_MAX_CELLS``."""
    need = (width_m * depth_m / DEFAULT_MAX_CELLS) ** 0.5
    return base_m if need <= base_m else float(np.ceil(need * 10) / 10)


def inspect(path: Path) -> Dict[str, Any]:
    from ..project.defaults import default_parameters

    path = Path(path)
    model = read(path)
    scale = model.scale_to_m if model.scale_to_m else 1.0
    rows, plan = [], {}
    for name, L in model.layers.items():
        t = L.triangles()
        e = _extent(t)
        if e is not None:
            plan[name] = float((e[1][0] - e[0][0]) * (e[1][1] - e[0][1]))
        rows.append({"layer": name, "objects": L.objects, "triangles": len(t), "closed_curves": len(L.curves),
                     "unmeshed": L.unmeshed, "role": _suggest(name, len(t) > 0, bool(L.curves)), "color": L.color,
                     "min": e[0].tolist() if e is not None else None, "max": e[1].tolist() if e is not None else None})
    _suggest_by_shape(rows, model.layers)
    if not any(r["role"] == "ground" for r in rows):   # the widest undecided layer is the likely ground
        free = {r["layer"]: plan[r["layer"]] for r in rows if r["role"] is None}
        if free:
            pick = max(free, key=free.get)
            next(r for r in rows if r["layer"] == pick)["role"] = "ground"
    for r in rows:
        r["role"] = r["role"] or "ignore"

    # the size of what the study will use, as suggested: not a ground plane or the neighbourhood around the site
    used = {r["layer"] for r in rows if r["role"] in ("ground", "nbs", "building", "barrier", "boundary_wall")}
    all_t = [L.triangles() for n, L in model.layers.items() if L.tris and n in used] or \
            [L.triangles() for L in model.layers.values() if L.tris]
    e = _extent(np.concatenate(all_t)) if all_t else None
    w, d = ((e[1][0] - e[0][0]) * scale, (e[1][1] - e[0][1]) * scale) if e is not None else (0.0, 0.0)
    notes = []
    unmeshed = sum(L.unmeshed for L in model.layers.values())
    if unmeshed:
        notes.append(f"{unmeshed} object(s) are surfaces with no saved mesh and cannot be read. In Rhino run Mesh on "
                     "them, or view them shaded and use Save (not Save Small), then choose the file again.")
    if model.scale_to_m is None:
        notes.append("The file does not say what units it is in: choose them below and check the size.")
    if model.unread:
        notes.append(f"{model.unread} group(s) of triangle strips or fans in the file were not read.")
    if e is None:
        notes.append("Nothing in this file can be used as ground: it holds no meshes.")
    choices = [{"name": n, "to_m": v} for n, v in UNIT_CHOICES]
    if model.scale_to_m and not any(abs(v - model.scale_to_m) < 1e-9 for _, v in UNIT_CHOICES):
        choices.insert(0, {"name": f"As in the file ({model.units})", "to_m": model.scale_to_m})
    return {"model": str(path), "format": model.format, "units": model.units, "units_known": model.scale_to_m is not None,
            "scale_to_m": scale, "unit_choices": choices, "up_axis": model.up_axis, "layers": rows,
            "min": e[0].tolist() if e is not None else None, "max": e[1].tolist() if e is not None else None,
            "cell_m": _cell_for(w, d, float(default_parameters().value("terrain.dem_cell_m"))), "notes": notes,
            "roles": list(ROLES), "by_material": model.by_material}


# ------------------------------------------------------------------ model to ground grid
@njit(cache=True)
def _rasterise(tris, x0, y1, cell, out):
    """The highest surface over each cell centre (NaN where there is none). Walls are edge-on and add nothing."""
    nr, nc = out.shape
    for i in range(tris.shape[0]):
        ax, ay, az = tris[i, 0, 0], tris[i, 0, 1], tris[i, 0, 2]
        bx, by, bz = tris[i, 1, 0], tris[i, 1, 1], tris[i, 1, 2]
        cx, cy, cz = tris[i, 2, 0], tris[i, 2, 1], tris[i, 2, 2]
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-12:
            continue
        c0 = max(0, int(np.floor((min(ax, bx, cx) - x0) / cell)))
        c1 = min(nc - 1, int(np.floor((max(ax, bx, cx) - x0) / cell)))
        r0 = max(0, int(np.floor((y1 - max(ay, by, cy)) / cell)))
        r1 = min(nr - 1, int(np.floor((y1 - min(ay, by, cy)) / cell)))
        for r in range(r0, r1 + 1):
            py = y1 - (r + 0.5) * cell
            for c in range(c0, c1 + 1):
                px = x0 + (c + 0.5) * cell
                u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / det
                v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / det
                w = 1.0 - u - v
                if u >= -1e-9 and v >= -1e-9 and w >= -1e-9:
                    z = u * az + v * bz + w * cz
                    if out[r, c] != out[r, c] or z > out[r, c]:
                        out[r, c] = z


@njit(cache=True)
def _rasterise_edges(tris, x0, y1, cell, out):
    """Every cell a triangle's edges pass through gets the edge's height there: a wall thinner than a cell, or drawn
    only as upright faces, still stands on the grid."""
    nr, nc = out.shape
    for i in range(tris.shape[0]):
        for k in range(3):
            ax, ay, az = tris[i, k, 0], tris[i, k, 1], tris[i, k, 2]
            j = (k + 1) % 3
            bx, by, bz = tris[i, j, 0], tris[i, j, 1], tris[i, j, 2]
            n = int(max(abs(bx - ax), abs(by - ay)) / (cell / 3.0)) + 1
            for s in range(n + 1):
                f = s / n
                c = int(np.floor((ax + f * (bx - ax) - x0) / cell))
                r = int(np.floor((y1 - (ay + f * (by - ay))) / cell))
                if 0 <= r < nr and 0 <= c < nc:
                    z = az + f * (bz - az)
                    if out[r, c] != out[r, c] or z > out[r, c]:
                        out[r, c] = z


def _no_diagonal_gaps(z: np.ndarray) -> None:
    """Cells meeting only at a corner get a neighbour, so a line of them holds water in every direction."""
    m = np.isfinite(z)
    d1 = m[:-1, :-1] & m[1:, 1:] & ~m[:-1, 1:] & ~m[1:, :-1]
    d2 = m[:-1, 1:] & m[1:, :-1] & ~m[:-1, :-1] & ~m[1:, 1:]
    z[:-1, 1:][d1] = z[:-1, :-1][d1]
    z[:-1, :-1][d2] = z[:-1, 1:][d2]


def _thin(tris: np.ndarray, shape: Tuple[int, int], x0: float, y1: float, cell: float) -> np.ndarray:
    out = np.full(shape, np.nan)
    if len(tris):
        _rasterise(tris, x0, y1, cell, out)
        _rasterise_edges(tris, x0, y1, cell, out)
        _no_diagonal_gaps(out)
    return out


def _inside_wall(wall: np.ndarray, cell: float) -> Tuple[Optional[np.ndarray], List[Dict[str, float]]]:
    """What a boundary wall encloses, bridging its gaps, and where those gaps are. The smallest bridge that encloses
    most of the wall's extent is the one that closes the gaps."""
    from scipy import ndimage

    if not wall.any():
        return None, []
    rows, cols = np.nonzero(wall)
    box = (np.ptp(rows) + 1) * (np.ptp(cols) + 1)
    square = np.ones((3, 3), bool)
    g = 1
    while g <= MAX_WALL_GAP_CELLS:
        closed = ndimage.binary_dilation(wall, structure=square, iterations=g)
        filled = ndimage.binary_fill_holes(closed)
        if (filled & ~closed).sum() >= 0.25 * box:
            # grown back out by as much, up to the wall: whatever it cannot reach in a corner is inside too
            inner = ndimage.binary_dilation(filled & ~closed, structure=square, iterations=g + 1) & filled & ~wall
            inner = ndimage.binary_fill_holes(inner | wall) & ~wall
            return inner, _openings(inner, wall, cell)
        g *= 2
    return None, []


def _openings(inner: np.ndarray, wall: np.ndarray, cell: float) -> List[Dict[str, float]]:
    """The stretches of the site's edge with no wall beside them: (row, col, width in m), widest first."""
    from scipy import ndimage

    edge = inner & ~ndimage.binary_erosion(inner, structure=np.ones((3, 3)), border_value=0)
    near_wall = ndimage.binary_dilation(wall, structure=np.ones((3, 3)), iterations=2)
    lab, n = ndimage.label(edge & ~near_wall, structure=np.ones((3, 3)))
    out = []
    for k in range(1, n + 1):
        r, c = np.nonzero(lab == k)
        width = float(max(np.ptp(r), np.ptp(c)) + 1) * cell
        if width >= 2 * cell:
            out.append({"row": int(r.mean()), "col": int(c.mean()), "width_m": round(width, 1)})
    return sorted(out, key=lambda o: -o["width_m"])


def _fill_holes(z: np.ndarray, holes: np.ndarray, X: np.ndarray, Y: np.ndarray, ground: np.ndarray) -> None:
    """Across each gap from the ``ground`` around it, not from a wall beside it: that would ramp the ground up to the
    wall. A gap with no ground around it takes what is there."""
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    from scipy.ndimage import binary_dilation
    from scipy.spatial import QhullError

    rim = binary_dilation(holes, iterations=2) & np.isfinite(ground)
    source = ground
    if not rim.any():
        rim, source = binary_dilation(holes) & np.isfinite(z), z
    pts, vals = np.column_stack([X[rim], Y[rim]]), source[rim]
    near = NearestNDInterpolator(pts, vals)(X[holes], Y[holes])
    try:
        lin = LinearNDInterpolator(pts, vals)(X[holes], Y[holes])
    except QhullError:
        lin = near
    z[holes] = np.where(np.isfinite(lin), lin, near)


def _outline(mask: np.ndarray, dem) -> Any:
    """The outer edge of the largest connected part of ``mask``."""
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from shapely.geometry import Polygon, shape

    t = from_origin(dem.origin[0], dem.origin[1], dem.cell_size, dem.cell_size)
    polys = [shape(g) for g, _ in shapes(mask.astype("uint8"), mask=mask, transform=t)]
    return Polygon(max(polys, key=lambda p: p.area).exterior.coords)


def _boundary_curve(layers: List[Layer], scale: float) -> Optional[Any]:
    from shapely.geometry import Polygon

    polys = [Polygon(c[:, :2] * scale).buffer(0) for L in layers for c in L.curves if len(c) >= 4]
    polys = [p for p in polys if not p.is_empty]
    return max(polys, key=lambda p: p.area) if polys else None


def build_ground(model: Model, roles: Dict[str, str], scale: float, cell: float, crs: str = "LOCAL", offset=None):
    """(DEM, site polygon, building polygons, report) from the layers given each role."""
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from scipy import ndimage
    from shapely import contains_xy
    from shapely.geometry import shape

    from ..terrain.raster import DEM

    move = np.zeros(3) if offset is None else np.asarray(offset, float)

    def picked(role):
        return [L for n, L in model.layers.items() if roles.get(n) == role]

    def tris(role):
        ts = [L.triangles() for L in picked(role) if L.tris]
        return np.concatenate(ts) * scale + move if ts else np.empty((0, 3, 3))

    ground, buildings, barriers, walls = tris("ground"), tris("building"), tris("barrier"), tris("boundary_wall")
    nbs = tris("nbs")
    ground = np.concatenate([ground, nbs])
    if not len(ground):
        raise ModelError("mark at least one layer holding a mesh as ground.")
    boundary = _boundary_curve(picked("boundary"), scale)
    if boundary is not None and move.any():
        from shapely import affinity

        boundary = affinity.translate(boundary, float(move[0]), float(move[1]))
    if boundary is None and picked("boundary"):
        raise ModelError("a layer is marked as boundary but holds no closed curve: draw one, or set that layer to ignore.")
    every = np.concatenate([ground, buildings, barriers, walls]).reshape(-1, 3)   # (ground includes the rain gardens and swales)
    lo, hi = every.min(axis=0), every.max(axis=0)
    x0, y0 = np.floor(lo[:2] / cell) * cell - cell   # a spare cell all round: a wall may lie on the very edge
    x1, y1 = np.ceil(hi[:2] / cell) * cell + cell
    nc, nr = max(1, int(round((x1 - x0) / cell))), max(1, int(round((y1 - y0) / cell)))
    if nr * nc > HARD_MAX_CELLS:
        raise ModelError(f"at {cell:g} m cells the model is {nc} x {nr} cells, too many to work with: its size is "
                         f"{x1 - x0:,.0f} x {y1 - y0:,.0f} m. Check the units, or use a larger cell size.")

    g = np.full((nr, nc), np.nan)
    _rasterise(ground, float(x0), float(y1), float(cell), g)
    b = np.full((nr, nc), np.nan)
    if len(buildings):
        _rasterise(buildings, float(x0), float(y1), float(cell), b)
    if not np.isfinite(g).any():
        raise ModelError("the ground layer has no surface facing up: it may be standing on edge. Check the model's "
                         "up direction, and that its units are right for the size shown.")
    bar = _thin(barriers, (nr, nc), float(x0), float(y1), float(cell))
    wall = _thin(walls, (nr, nc), float(x0), float(y1), float(cell))
    z = np.fmax(np.fmax(np.fmax(g, b), bar), wall)   # they all stand on the ground, whichever is higher
    n_top = np.full((nr, nc), np.nan)
    if len(nbs):
        _rasterise(nbs, float(x0), float(y1), float(cell), n_top)
    dem = DEM(np.zeros((nr, nc)), float(cell), (float(x0), float(y1)), crs, -9999.0)
    X, Y = dem.cell_centres()

    # one flat block per building
    is_b = np.isfinite(b)
    lab, n_b = ndimage.label(is_b, structure=np.ones((3, 3)))
    if n_b:
        tops = np.asarray(ndimage.maximum(z, lab, index=np.arange(1, n_b + 1)))
        z[is_b] = tops[lab[is_b] - 1]

    issues: List[str] = []
    # a boundary wall sets the site, unless a boundary curve was given: the ground inside it
    inner, openings = _inside_wall(np.isfinite(wall), float(cell)) if len(walls) else (None, [])
    if len(walls) and inner is None:
        issues.append("the boundary wall does not enclose the site (its gaps are too wide), so it only stands as a wall.")
    holes = ndimage.binary_fill_holes(np.isfinite(z)) & ~np.isfinite(z)
    if inner is not None and boundary is None:
        holes |= inner & ~np.isfinite(z)
    n_holes = int(holes.sum())
    if n_holes:
        _fill_holes(z, holes, X, Y, g)
    wall_report = None
    if inner is not None and boundary is None:
        boundary = _outline(inner, dem).simplify(cell * 0.5)
        # how high the wall stands above the ground just inside it
        # (the highest part of the wall within a few cells: a plinth may stand in front of it)
        top = ndimage.maximum_filter(np.nan_to_num(wall, nan=-1e9), size=2 * WALL_REACH_CELLS + 1)
        edge = inner & ~ndimage.binary_erosion(inner, structure=np.ones((3, 3)), border_value=0) & np.isfinite(z)
        rise = (top - z)[edge & (top > -1e8)]
        h = float(np.median(rise)) if rise.size else 0.0
        at = [{"x": round(float(x0 + (o["col"] + 0.5) * cell), 1), "y": round(float(y1 - (o["row"] + 0.5) * cell), 1),
               "width_m": o["width_m"]} for o in openings]
        wall_report = {"height_m": round(h, 2), "openings": at}
        issues.append(f"The boundary wall stands about {h:.1f} m above the ground inside it and holds the water: every "
                      "exit starts closed. Open the real outlets in Site setup > Outfalls.")
        if at:
            issues.append(f"{len(at)} gap(s) in the wall, closed for now; open any that are outlets: "
                          + "; ".join(f"{o['width_m']:g} m at ({o['x']:.0f}, {o['y']:.0f})" for o in at) + ".")
    if boundary is None:
        parts, n = ndimage.label(np.isfinite(z), structure=np.ones((3, 3)))
        sizes = ndimage.sum(np.ones_like(parts), parts, index=np.arange(1, n + 1))
        keep = int(np.argmax(sizes)) + 1
        dropped = float((sizes.sum() - sizes[keep - 1]) * cell * cell)
        if dropped > 0:
            issues.append(f"{dropped:,.0f} m2 of the model is not joined to the main site and was left out.")
            z[(parts != keep) & (parts > 0)] = np.nan
        boundary = _outline(np.isfinite(z), dem).simplify(cell * 0.5)

    inside = contains_xy(boundary, X, Y)
    covered = float(np.isfinite(z)[inside].mean()) if inside.any() else 0.0
    if covered == 0.0:
        raise ModelError("the boundary curve does not overlap the ground: check that it is drawn over the site.")
    if covered < 0.98:
        issues.append(f"only {covered:.0%} of the boundary curve has ground under it; the rest is treated as outside the site.")
    used = inside & np.isfinite(z)
    area = float(used.sum() * cell * cell)
    hole_m2 = n_holes * cell * cell
    if n_holes:
        issues.append(f"{hole_m2:,.1f} m2 of gaps in the model were filled across"
                      + (f" ({hole_m2 / area:.0%} of the site): check them, the fill may hide or invent a hollow."
                         if hole_m2 / area >= HOLE_WARN_SHARE else "."))
    rng = [float(z[used].min()), float(z[used].max())]
    if rng[1] - rng[0] < 0.01:
        issues.append("the ground is flat: water will have no direction to run in. Check that the ground layer has "
                      "its levels and that the model's up direction is right.")
    if wall_report is None:
        issues.append("Flow leaves wherever it reaches the edge of the model. If water cannot leave there, close that "
                      "exit in Site setup > Outfalls.")
    dem.z = np.where(np.isfinite(z), z, dem.nodata)

    t = from_origin(float(x0), float(y1), cell, cell)
    polys = []
    if n_b:
        polys = [shape(geom) for geom, _ in shapes(lab.astype("int32"), mask=lab > 0, transform=t)]
    # where the rain gardens and swales are the surface; what stands in them (a dam, a wall) is not
    zone = np.isfinite(n_top) & (n_top >= np.nan_to_num(z, nan=-np.inf) - 1e-3)
    nbs_polys = [shape(geom) for geom, _ in shapes(zone.astype("uint8"), mask=zone, transform=t)] if zone.any() else []
    bars = DEM(np.where(np.isfinite(bar), bar, -9999.0), float(cell), (float(x0), float(y1)), crs, -9999.0)
    walls_grid = DEM(np.where(np.isfinite(wall), wall, -9999.0), float(cell), (float(x0), float(y1)), crs, -9999.0) if len(walls) else None
    return dem, g, boundary, polys, bars, walls_grid, nbs_polys, {"issues": issues, "elevation_range_m": rng, "site_area_m2": area,
                                  "holes_filled_m2": hole_m2, "buildings": n_b, "boundary_covered_share": covered,
                                  "ground_triangles": len(ground), "building_triangles": len(buildings),
                                  "wall": wall_report, "nbs_m2": float(zone.sum() * cell * cell)}


def _view_layers(model: Model, roles: Dict[str, str], scale: float, offset=None, extra: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The model itself for the 3D view, one layer per row of the dialog, in the model's own colours."""
    from ..site.survey_layers import STYLE

    layers = []
    for name, L in model.layers.items():
        role = roles.get(name, "ignore")
        t = L.triangles()
        if role in ("ignore", "boundary") or not len(t):
            continue
        v, tri = np.unique(np.round(t.reshape(-1, 3) * scale + (0 if offset is None else offset), 3), axis=0, return_inverse=True)
        low = re.sub(r"[:_\-]+", " ", name.lower())
        color = ROLE_COLOR[role] if model.by_material or role == "water" else \
            next((c for pat, c in NAME_COLOR if re.search(pat, low)), ROLE_COLOR[role])
        feature = {"g": "mesh", "xyz": v.ravel().tolist(), "tri": np.asarray(tri).ravel().tolist(), "color": color,
                   "smooth": role in ("ground", "nbs", "water"),   # shaded smoothly across its triangles: walls keep their edges
                   **({"water": True} if role == "water" else {})}
        layers.append({"name": name, "title": f"{role.replace('_', ' ').capitalize()}: {name}", "kind": "model", "color": color,
                       "visible": True, "count": 1, "role": role, "features": [feature]})
    return {"style": STYLE, "from_model": True, "planting": False, "layers": layers + (extra or [])}


def outfalls_walls() -> str:
    from ..site.outfalls import WALLS

    return WALLS


def read_plan(path: Path) -> Dict[str, Any]:
    """What the design's plan adds: the extent of its boundary wall and its recharge wells (x, y, radius). Its contours
    are not read: the levels come from the model."""
    import ezdxf
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union

    path = Path(path)
    if path.suffix.lower() != ".dxf" or not path.is_file():
        raise ModelError(f"choose the design plan as a .dxf file (in AutoCAD, Save As DXF): {path.name}.")
    level = logging.getLogger("ezdxf").level
    logging.getLogger("ezdxf").setLevel(logging.ERROR)   # copying blocks complains of what it leaves behind
    try:
        doc = ezdxf.readfile(path)
    except (OSError, ezdxf.DXFError) as ex:
        raise ModelError(f"could not read the design plan {path.name}: {ex}")
    wall: List[Tuple[float, float]] = []
    wall_lines: List[List[Tuple[float, float]]] = []
    wells: List[Tuple[float, float, float]] = []
    swales: List[Any] = []

    def visit(e, depth=0):
        if e.dxftype() == "INSERT":
            if depth < MAX_DEPTH:
                try:
                    for v in e.virtual_entities():
                        visit(v, depth + 1)
                except (ezdxf.DXFError, ValueError, KeyError, AttributeError):
                    pass    # an external reference: not in this file
            return
        name = e.dxf.layer.lower()
        if _PLAN_WALL.search(name) and e.dxftype() == "LWPOLYLINE":
            wall.extend((p[0], p[1]) for p in e.get_points())
            wall_lines.append([(p[0], p[1]) for p in e.get_points()] + ([tuple(e.get_points()[0][:2])] if e.closed else []))
        elif _PLAN_WELL.search(name) and e.dxftype() == "CIRCLE":
            wells.append((e.dxf.center.x, e.dxf.center.y, e.dxf.radius))
        elif _PLAN_NBS.search(name) and e.dxftype() == "LWPOLYLINE" and e.closed:
            pts = [(p[0], p[1]) for p in e.get_points()]
            if len(pts) >= 3:
                swales.append(Polygon(pts).buffer(0))
        elif _PLAN_NBS.search(name) and e.dxftype() == "CIRCLE":
            swales.append(Point(e.dxf.center.x, e.dxf.center.y).buffer(e.dxf.radius))

    try:
        for e in doc.modelspace():
            visit(e)
    finally:
        logging.getLogger("ezdxf").setLevel(level)
    a = np.array(wall) if wall else None
    return {"wall": (a.min(axis=0), a.max(axis=0)) if a is not None else None, "wells": wells, "wall_lines": wall_lines,
            "swales": unary_union(swales) if swales else None}


def _line_up(model: Model, roles: Dict[str, str], scale: float, plan: Optional[Dict[str, Any]], survey_dem) -> Tuple[np.ndarray, List[str]]:
    """How far to move the model (m) to lie on the survey: in plan by its boundary wall on the plan's (else its ground on
    the survey's), in level so that its ground lies on the survey's as a whole."""
    def tris(*which):
        ts = [L.triangles() for n, L in model.layers.items() if roles.get(n) in which and L.tris]
        return np.concatenate(ts).reshape(-1, 3) * scale if ts else np.empty((0, 3))

    walls, ground = tris("boundary_wall"), tris("ground", "nbs")
    off, notes = np.zeros(3), []
    if plan and plan.get("wall") and len(walls):
        lo, hi = plan["wall"]
        off[:2] = (lo + hi) / 2 - (walls[:, :2].min(axis=0) + walls[:, :2].max(axis=0)) / 2
        d = np.abs((hi - lo) - (walls[:, :2].max(axis=0) - walls[:, :2].min(axis=0))).max()
        if d > LINE_UP_WARN_M:
            notes.append(f"the boundary wall on the plan and in the model differ in size by {d:.1f} m: check they are the same design.")
    elif survey_dem is not None and len(ground):
        v = survey_dem.z != survey_dem.nodata
        X, Y = survey_dem.cell_centres()
        off[:2] = [(X[v].min() + X[v].max()) / 2 - (ground[:, 0].min() + ground[:, 0].max()) / 2,
                   (Y[v].min() + Y[v].max()) / 2 - (ground[:, 1].min() + ground[:, 1].max()) / 2]
        notes.append("no boundary wall to line the model up by: it was centred on the survey. Check that it lies where it should.")
    if survey_dem is not None and len(ground):
        c = ((ground[:, 0] + off[0] - survey_dem.origin[0]) / survey_dem.cell_size).astype(int)
        r = ((survey_dem.origin[1] - ground[:, 1] - off[1]) / survey_dem.cell_size).astype(int)
        ok = (r >= 0) & (r < survey_dem.z.shape[0]) & (c >= 0) & (c < survey_dem.z.shape[1])
        ok[ok] = survey_dem.z[r[ok], c[ok]] != survey_dem.nodata
        if ok.sum() < 0.5 * len(ground):
            notes.append("the model lies mostly outside the survey: check that they are the same site.")
        if ok.any():
            off[2] = float(np.median(survey_dem.z[r[ok], c[ok]] - ground[ok, 2]))
    return off, notes


def _nbs_from_plan(model: Model, roles: Dict[str, str], scale: float, offset, swales) -> Dict[str, str]:
    """A model with no names (a COLLADA export) cannot say which material is the rain gardens and swales, but the plan
    can: the ground material with the most area inside the plan's outlines, if a good part of it lies there (a small
    part such as a metal plate may lie wholly inside and still not be them). A role the designer gave is kept otherwise."""
    from shapely import contains_xy

    if swales is None or "nbs" in roles.values():
        return roles
    best, most = None, 0.0
    for name, L in model.layers.items():
        t = L.triangles()
        if roles.get(name) != "ground" or not len(t):
            continue
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        plan_area = np.abs(n[:, 2]) * scale * scale / 2
        c = t.mean(axis=1)[:, :2] * scale + offset[:2]
        inside = float(plan_area[contains_xy(swales, c[:, 0], c[:, 1])].sum())
        if inside > most and inside >= PLAN_NBS_SHARE * float(plan_area.sum()):
            best, most = name, inside
    return {**roles, best: "nbs"} if best else roles


def _alignment(model: Model, roles: Dict[str, str], scale: float, offset, plan, site, survey_dem, survey_site) -> Dict[str, Any]:
    """How well the three lie on each other, measured: the plan's wall against the model's, the survey's site against
    the model's, and the model's ground against the survey's (the design changes it, so this is not an error by itself)."""
    from shapely import distance, points
    from shapely.geometry import LineString

    def tris(*which):
        ts = [L.triangles() for n, L in model.layers.items() if roles.get(n) in which and L.tris]
        return np.concatenate(ts).reshape(-1, 3) * scale + offset if ts else np.empty((0, 3))

    rng = np.random.default_rng(0)
    out: Dict[str, Any] = {}
    walls, ground = tris("boundary_wall"), tris("ground", "nbs")
    if plan and plan.get("wall_lines") and len(walls):
        line = LineString(max(plan["wall_lines"], key=len))
        pick = walls[rng.choice(len(walls), min(len(walls), 5000), replace=False), :2]
        d = distance(points(pick), line)
        out["plan_wall_to_model_wall_m"] = {"median": round(float(np.median(d)), 3), "p95": round(float(np.percentile(d, 95)), 3)}
    if survey_site is not None and site is not None:
        both = survey_site.intersection(site).area
        out["survey_site_m2"] = round(float(survey_site.area), 1)
        out["model_site_m2"] = round(float(site.area), 1)
        out["site_overlap"] = round(float(both / survey_site.union(site).area), 3)
        out["site_edge_gap_m"] = round(float(survey_site.exterior.hausdorff_distance(site.exterior)), 2)
    if survey_dem is not None and len(ground):
        c = ((ground[:, 0] - survey_dem.origin[0]) / survey_dem.cell_size).astype(int)
        r = ((survey_dem.origin[1] - ground[:, 1]) / survey_dem.cell_size).astype(int)
        ok = (r >= 0) & (r < survey_dem.z.shape[0]) & (c >= 0) & (c < survey_dem.z.shape[1])
        ok[ok] = survey_dem.z[r[ok], c[ok]] != survey_dem.nodata
        if ok.any():
            d = survey_dem.z[r[ok], c[ok]] - ground[ok, 2]
            out["ground_vs_survey_m"] = {"median": round(float(np.median(d)), 3), "p05": round(float(np.percentile(d, 5)), 2),
                                         "p95": round(float(np.percentile(d, 95)), 2)}
    return out


def _align_notes(a: Dict[str, Any]) -> List[str]:
    notes, w = [], a.get("plan_wall_to_model_wall_m")
    if w and w["p95"] > ALIGN_WALL_WARN_M:
        notes.append(f"the model's wall is up to {w['p95']:.1f} m from the plan's: check that they are the same design.")
    if a.get("site_overlap") is not None and a["site_overlap"] < ALIGN_SITE_WARN:
        notes.append(f"the survey's site and the model's overlap only {a['site_overlap']:.0%}: check that they are the same site.")
    return notes


def _plan_layers(plan, survey_site, dem) -> List[Dict[str, Any]]:
    """The plan's and the survey's outlines laid on the model (switched off to begin with), to compare them by eye."""
    def draped(coords):
        xy = np.asarray(coords, float)[:, :2]
        X0, Y1 = dem.origin
        c = np.clip(((xy[:, 0] - X0) / dem.cell_size).astype(int), 0, dem.z.shape[1] - 1)
        r = np.clip(((Y1 - xy[:, 1]) / dem.cell_size).astype(int), 0, dem.z.shape[0] - 1)
        z = np.where(dem.z[r, c] != dem.nodata, dem.z[r, c], float(np.median(dem.z[dem.z != dem.nodata])))
        return np.round(np.c_[xy, z], 3).ravel().tolist()

    def layer(name, title, color, lines):
        feats = [{"g": "line", "xyz": draped(c), "on_ground": True} for c in lines if len(c) >= 2]
        return {"name": name, "title": title, "kind": "contours", "color": color, "visible": False, "count": len(feats),
                "role": "overlay", "features": feats} if feats else None

    def rings(g):
        return [list(q.exterior.coords) for q in getattr(g, "geoms", [g])] if g is not None and not g.is_empty else []

    wells = [[(x + r * np.cos(t), y + r * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 13)] for x, y, r in (plan or {}).get("wells", [])]
    out = [layer("Survey boundary", "Survey: park boundary", "#FFFFFF", rings(survey_site))]
    if plan:
        out += [layer("Plan wall", "Plan: boundary wall", "#FF3B30", plan["wall_lines"]),
                layer("Plan swales", "Plan: swales and rain gardens", "#FFD60A", rings(plan["swales"])),
                layer("Plan wells", "Plan: recharge wells", "#0A84FF", wells)]
    return [L for L in out if L]


def _contours(z: np.ndarray, dem, boundary, title: str, name: str, color: str, visible: bool) -> Optional[Dict[str, Any]]:
    """Contours of ``z`` inside the site, as a layer for the viewers."""
    from shapely import contains_xy
    from shapely.geometry import LineString

    from ..terrain.raster import DEM
    from ..terrain.tin import contour_lines

    X, Y = dem.cell_centres()
    grid = np.where(np.isfinite(z) & (z != dem.nodata) & contains_xy(boundary, X, Y), z, dem.nodata)
    if not (grid != dem.nodata).any():
        return None
    valid = grid[grid != dem.nodata]
    relief = float(valid.max() - valid.min())
    interval = next((s for s in CONTOUR_STEPS if relief / s <= 12), CONTOUR_STEPS[-1])
    features = []
    for f in contour_lines(DEM(grid, dem.cell_size, dem.origin, dem.crs, dem.nodata), interval):
        line = LineString(f["geometry"]["coordinates"]).simplify(dem.cell_size * 0.1)
        xyz = [[round(x, 2), round(y, 2), round(f["properties"]["z"], 3)] for x, y in line.coords]
        features.append({"g": "line", "xyz": [v for p in xyz for v in p], "on_ground": True})
    return {"name": name, "title": f"{title}, every {interval:g} m", "kind": "contours", "color": color, "visible": visible,
            "count": len(features), "role": "contours", "features": features}


def _free_path(path: Path) -> Path:
    """Never replace an existing project: the next free name beside it."""
    out, n = path, 2
    while out.exists():
        out = path.with_name(f"{path.stem}_{n}{path.suffix}")
        n += 1
    return out


def finish(model_path: Path, roles: Dict[str, str], project_path: Optional[Path] = None,
           scale_to_m: Optional[float] = None, cell_m: Optional[float] = None, survey_project: Optional[Path] = None,
           design_plan: Optional[Path] = None) -> Dict[str, Any]:
    """Create the project from the model. ``roles``: layer name -> one of ``ROLES``. ``survey_project``: the site's project
    made from its survey, for the coordinates and the existing contours. ``design_plan``: the design's DXF, for the wells."""
    from ..project import Project
    from ..project.defaults import default_parameters
    from ..terrain.raster import write_geotiff

    model_path = Path(model_path)
    bad = sorted(set(roles.values()) - set(ROLES))
    if bad:
        raise ModelError(f"unknown layer role: {', '.join(bad)}.")
    if cell_m is not None and cell_m <= 0:
        raise ModelError("the cell size must be above zero.")
    if scale_to_m is not None and scale_to_m <= 0:
        raise ModelError("the model's units must scale to a length above zero.")
    model = read(model_path)
    scale = scale_to_m or model.scale_to_m or 1.0
    project_path = Path(project_path) if project_path else model_path.with_name(model_path.stem.replace(" ", "_") + ".sponge")
    if not project_path.parent.is_dir():
        raise ModelError(f"the folder to save the project in does not exist: {project_path.parent}.")
    # the ground first: a model that fails leaves no half-made project behind
    cell = float(cell_m or default_parameters().value("terrain.dem_cell_m"))
    survey_dem = survey_site = survey_rain = survey_ground = None
    if survey_project:
        from ..project import Project as _P
        from ..terrain.raster import read_geotiff

        with _P.open(Path(survey_project)) as sp:
            if not sp.exists("terrain/existing.tif"):
                raise ModelError(f"{Path(survey_project).name} has no ground from a survey.")
            survey_dem = read_geotiff(sp.path("terrain/existing.tif"))
            from ..rainfall.presets import current as current_rain
            from ..site.ground import load as load_ground

            survey_rain, survey_ground = current_rain(sp), (load_ground(sp) or {}).get("answers")
            if sp.exists("site/boundary.geojson"):
                from shapely.geometry import shape
                from shapely.ops import unary_union

                survey_site = unary_union([shape(f["geometry"]) for f in sp.read_geojson("site/boundary.geojson")["features"]])
    plan = read_plan(Path(design_plan)) if design_plan else None
    offset, line_notes = _line_up(model, roles, scale, plan, survey_dem)
    if plan:
        roles = _nbs_from_plan(model, roles, scale, offset, plan["swales"])
    dem, ground_z, boundary, buildings, barriers, wall_tops, nbs_polys, q = build_ground(model, roles, scale, cell, offset=offset)
    q["issues"] = line_notes + q["issues"]
    if offset.any():
        q["issues"].insert(0, f"Lined up with the survey: moved {offset[0]:.1f} m east, {offset[1]:.1f} m north, {offset[2]:.2f} m up.")
    q["offset_m"] = [round(float(v), 3) for v in offset]
    q["alignment"] = _alignment(model, roles, scale, offset, plan, boundary, survey_dem, survey_site)
    q["issues"] = _align_notes(q["alignment"]) + q["issues"]
    project_path = _free_path(project_path)
    with Project.create(project_path, model_path.stem, crs="LOCAL") as p:
        p.path("survey").mkdir(exist_ok=True)
        shutil.copy2(model_path, p.path(f"survey/{model_path.name}"))
        if design_plan:
            shutil.copy2(design_plan, p.path(f"survey/{Path(design_plan).name}"))
        if survey_dem is not None:
            write_geotiff(survey_dem, p.path(SURVEY_GROUND))
            shutil.copy2(survey_project, p.path(EXISTING_PROJECT))   # the existing site travels with the design
        write_geotiff(dem, p.path("terrain/existing.tif"))
        write_geotiff(barriers, p.path("terrain/barriers.tif"))
        if wall_tops is not None:
            write_geotiff(wall_tops, p.path(outfalls_walls()))
        p.write_geojson("site/boundary.geojson", {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": boundary.__geo_interface__,
             "properties": {"id": "SITE", "source": model_path.name}}]})
        p.write_geojson("site/context.geojson", {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": b.__geo_interface__,
             "properties": {"id": f"buildings_{i}", "kind": "buildings", "layer": "model"}}
            for i, b in enumerate(buildings)]})
        source = {"file": model_path.name, "format": model.format, "units": model.units, "scale_to_m": scale,
                  "up_axis": model.up_axis, "cell_m": cell, "roles": roles, "offset_m": q["offset_m"],
                  "design_plan": Path(design_plan).name if design_plan else None,
                  "survey_project": Path(survey_project).name if survey_project else None}
        p.write_json(SOURCE, source)
        from ..project.parameters import Source
        from ..site import outfalls, survey_layers

        extra = [_contours(ground_z, dem, boundary, "Proposed contours (from the 3D model)", "Proposed contours", "#E8E2C8", True)]
        if survey_dem is not None:
            X, Y = dem.cell_centres()
            c = np.clip(((X - survey_dem.origin[0]) / survey_dem.cell_size).astype(int), 0, survey_dem.z.shape[1] - 1)
            r = np.clip(((survey_dem.origin[1] - Y) / survey_dem.cell_size).astype(int), 0, survey_dem.z.shape[0] - 1)
            extra.append(_contours(survey_dem.z[r, c].astype(float), dem, boundary, "Existing contours (from the survey)",
                                   "Existing contours", "#8A6A3C", False))
        extra += _plan_layers(plan, survey_site, dem)
        p.write_json(survey_layers.REL, _view_layers(model, roles, scale, offset, [e for e in extra if e]))
        if plan and plan["wells"]:
            from ..site import wells

            def level(x, y):
                c = np.clip(((x - dem.origin[0]) / cell).astype(int), 0, dem.z.shape[1] - 1)
                r = np.clip(((dem.origin[1] - y) / cell).astype(int), 0, dem.z.shape[0] - 1)
                return dem.z[r, c]

            found = wells.record(p, plan["wells"], level, boundary)
            q["wells_from_plan"] = len(found)
            q["issues"].append(f"{len(found)} recharge wells from the design plan: give their depth and rate in Site setup > Wells, "
                               "or they stay out of the flood model.")
        P = p.parameters
        if q.get("wall"):   # the wall holds the water: every exit closed until the designer opens the real outlets
            h = float(np.clip(q["wall"]["height_m"], 0.1, EDGE_HEIGHT_MAX_M))
            p.write_json(outfalls.REL, {"exits": [], "all": {"state": "closed", "edge_height_m": h}})
        if nbs_polys:
            p.write_geojson(NBS_ZONES, {"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": z.__geo_interface__, "properties": {"id": f"NBS_{i}"}} for i, z in enumerate(nbs_polys)]})
            P.set(NBS_RATE_KEY, NBS_RATE_MM_HR, "mm/hr", Source.LITERATURE,
                  "Rain gardens and swales in a design model: bottom of the ideal media rates, HC 4.2 p.12 (>13, ideally 25-50 "
                  "mm/hr) and HC 4.7 p.8 (filter media 1.0-6.0 in/hr). Assumes the media drains freely below (amended, or underdrained).")
        P.set("sim2d.courant", MODEL_COURANT, "-", Source.DEFAULT,
              "Deep ponds on a fine grid oscillate at the Bates et al. (2010) factor of 0.7 (false depths); halved for this project.")
        # the same storm and soil as the existing site: answered once, for the survey
        if survey_rain:
            from ..rainfall.presets import apply as set_rain

            set_rain(p, None, survey_rain["rows"], survey_rain.get("source") or "as the existing site")
        if survey_ground:
            from ..site.ground import apply as set_ground

            set_ground(p, survey_ground)
        p.write_json("terrain/qc.json", {**q, "source": source})
        p.history.log("model_intake", file=model_path.name, cell_m=cell, scale_to_m=scale, roles=roles)
        p.save()
    return {"project": str(project_path), "qc": q}
