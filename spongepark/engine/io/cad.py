"""Read survey drawings (DXF; DWG through the ODA File Converter if installed).

Workflow:
1. ``inventory`` lists every layer with entity counts, Z values and numeric texts.
2. ``suggest_layer_map`` proposes which layers hold contours, spot levels, boundary and site
   features. The suggestion is saved unconfirmed; the designer confirms or edits it.
3. ``extract`` reads the mapped layers into survey data:
   - contours with true Z (3D vertices or polyline elevation), or contours drawn at Z = 0 whose
     level comes from the nearest contour label (common in Indian survey drawings);
   - spot levels from 3D points, or from numeric text whose value is the level.
   Nothing is guessed: unlabeled contours, conflicting labels and unreadable texts are reported.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

log = logging.getLogger(__name__)

INSUNITS = {0: "unitless", 1: "inches", 2: "feet", 4: "millimetres", 5: "centimetres", 6: "metres"}
_NUM = re.compile(r"^\s*(?:RL|EL|LVL|\+)?\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)\s*m?\s*$", re.I)

# Layer roles and the name fragments that suggest them (lower case). Order matters: first match wins.
ROLES: List[Tuple[str, Tuple[str, ...]]] = [
    ("contour_labels", ("contann", "contour lab", "contour text", "cont_txt")),
    ("contours", ("esmajor", "esminor", "contour", "cont_maj", "cont_min")),
    ("spot_levels", ("block levels", "spot level", "spot height", "road levels", "levels", "spot")),
    ("boundary", ("boundary", "boundery", "site bound")),
    ("buildings", ("bldg", "building", "bulding", "shed")),
    ("trees", ("tree",)),
    ("drains", ("drain", "canal", "swd", "nala")),
    ("roads", ("road",)),
    ("paths", ("foot path", "footpath", "pathway")),
    ("water", ("water", "lake", "pond")),
    ("walls", ("wall", "fence", "fencing")),
]
# Layers that look like levels but whose meaning must be confirmed (e.g. drain bed or plinth levels).
ASK = ("be-level", "be level", "invert", "plinth")


class CadError(ValueError):
    pass


def read(path: Path):
    """Open a DXF, or a DWG through the ODA File Converter."""
    import ezdxf
    from ezdxf import recover

    path = Path(path)
    if path.suffix.lower() == ".dwg":
        from ezdxf.addons import odafc

        if not odafc.is_installed():
            raise CadError(
                f"{path.name}: DWG needs the ODA File Converter (free, opendesign.com), "
                "or save the drawing as DXF from AutoCAD."
            )
        return odafc.readfile(str(path))
    try:
        return ezdxf.readfile(str(path))
    except Exception:  # damaged file: try ezdxf's recovery mode
        doc, auditor = recover.readfile(str(path))
        log.warning("%s: recovered with %d errors", path.name, len(auditor.errors))
        return doc


def parse_level(text: str) -> Optional[float]:
    m = _NUM.match(text.replace("\\P", " ").strip())
    return float(m.group(1)) if m else None


def _text(e) -> str:
    return e.dxf.text if e.dxftype() == "TEXT" else e.plain_text()


def _text_xy(e) -> Tuple[float, float]:
    p = e.dxf.insert
    if e.dxftype() == "TEXT" and (e.dxf.get("halign", 0) or e.dxf.get("valign", 0)) and e.dxf.hasattr("align_point"):
        p = e.dxf.align_point
    return float(p.x), float(p.y)


def _vertices(e) -> List[Tuple[float, float, float]]:
    t = e.dxftype()
    if t == "LWPOLYLINE":
        z = float(e.dxf.elevation)
        return [(float(x), float(y), z) for x, y, *_ in e.get_points()]
    if t == "POLYLINE":
        ez = float(e.dxf.elevation.z) if e.is_2d_polyline else 0.0
        return [(float(v.dxf.location.x), float(v.dxf.location.y), float(v.dxf.location.z) or ez) for v in e.vertices]
    if t == "LINE":
        s, n = e.dxf.start, e.dxf.end
        return [(s.x, s.y, s.z), (n.x, n.y, n.z)]
    if t == "SPLINE":
        return [(p.x, p.y, p.z) for p in e.flattening(0.05)]
    if t == "ARC":
        return [(p.x, p.y, p.z) for p in e.flattening(0.05)]
    return []


def _closed(e) -> bool:
    t = e.dxftype()
    if t == "LWPOLYLINE":
        return bool(e.closed)
    if t == "POLYLINE":
        return bool(e.is_closed)
    return False


# ------------------------------------------------------------------ inventory
@dataclass
class LayerInfo:
    name: str
    entities: Dict[str, int]
    numeric_texts: int = 0
    level_range: Optional[Tuple[float, float]] = None
    z_nonzero_share: Optional[float] = None
    suggested_role: Optional[str] = None


def _role(name: str) -> Optional[str]:
    if name.upper().startswith("SP-"):  # standard layer: its role is fixed by the standard
        s = {x["name"].upper(): x for x in layer_standard()["layers"]}.get(name.upper())
        if s is not None:
            return "ask" if s["role"] == "check" else s["role"]
        return None  # SP-X-*: kept but left out on purpose
    n = name.lower()
    if any(a in n for a in ASK):
        return "ask"
    for role, keys in ROLES:
        if any(k in n for k in keys):
            return role
    return None


def inventory(doc) -> Dict[str, Any]:
    counts: Dict[str, Counter] = defaultdict(Counter)
    nums: Dict[str, List[float]] = defaultdict(list)
    zs: Dict[str, List[float]] = defaultdict(list)
    for e in doc.modelspace():
        L = e.dxf.layer
        t = e.dxftype()
        counts[L][t] += 1
        if t in ("TEXT", "MTEXT"):
            v = parse_level(_text(e))
            if v is not None:
                nums[L].append(v)
        elif t in ("LWPOLYLINE", "POLYLINE", "LINE"):
            vs = _vertices(e)
            if vs:
                zs[L].append(vs[0][2])
    layers = []
    for L, c in sorted(counts.items(), key=lambda kv: -sum(kv[1].values())):
        n = nums.get(L, [])
        z = zs.get(L, [])
        layers.append(LayerInfo(
            name=L, entities=dict(c), numeric_texts=len(n),
            level_range=(min(n), max(n)) if n else None,
            z_nonzero_share=(float(np.mean([abs(v) > 1e-9 for v in z])) if z else None),
            suggested_role=_role(L),
        ))
    ext_min, ext_max = doc.header.get("$EXTMIN"), doc.header.get("$EXTMAX")
    return {
        "dxf_version": doc.dxfversion,
        "insunits": INSUNITS.get(doc.header.get("$INSUNITS", 0), str(doc.header.get("$INSUNITS"))),
        "extents_xy": [list(ext_min)[:2], list(ext_max)[:2]] if ext_min is not None else None,
        "layers": [vars(li) for li in layers],
    }


def suggest_layer_map(inv: Dict[str, Any]) -> Dict[str, Any]:
    roles: Dict[str, List[str]] = defaultdict(list)
    ask = []
    for li in inv["layers"]:
        r = li["suggested_role"]
        if r == "ask":
            ask.append(li["name"])
        elif r:
            roles[r].append(li["name"])
    return {
        "confirmed": False,
        "units_scale_to_m": 1.0,
        "contours_in_surface": "auto",
        "roles": dict(roles),
        "needs_decision": ask,
        "note": "Suggested from layer names. Check every role, set units_scale_to_m if the drawing is not in "
                "metres, decide the layers in needs_decision, then set confirmed to true. Set "
                "contours_in_surface to false when the contours were generated from the spot levels "
                "(the QC report says so): they are then used only as a check.",
    }


# ------------------------------------------------------------------ extraction
@dataclass
class Contour:
    line: LineString
    z: Optional[float]
    how: str  # "3d" | "elevation" | "label" | "unlabeled" | "conflict"
    layer: str


@dataclass
class Spot:
    x: float
    y: float
    z: float
    layer: str


@dataclass
class Survey:
    contours: List[Contour]
    spots: List[Spot]
    features: Dict[str, List[Dict[str, Any]]]  # role -> GeoJSON-like features
    issues: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def points(self, spacing_m: float = 1.0, include_contours: bool = True) -> np.ndarray:
        """Elevation points (x, y, z): spots, plus contours densified at ``spacing_m`` if included."""
        pts = [(s.x, s.y, s.z) for s in self.spots]
        for c in (self.contours if include_contours else []):
            if c.z is None:
                continue
            n = max(2, int(np.ceil(c.line.length / spacing_m)) + 1)
            for d in np.linspace(0, c.line.length, n):
                p = c.line.interpolate(d)
                pts.append((p.x, p.y, c.z))
        return np.array(pts, dtype=float).reshape(-1, 3)


def _key(coords: Iterable[Tuple[float, float]]) -> Tuple:
    return tuple((round(x, 3), round(y, 3)) for x, y in coords)


def extract(doc, layer_map: Dict[str, Any], label_search_m: float = 3.0,
            level_range: Optional[Tuple[float, float]] = None) -> Survey:
    roles = layer_map.get("roles", {})
    k = float(layer_map.get("units_scale_to_m", 1.0))
    by_layer: Dict[str, List[Any]] = defaultdict(list)
    for e in doc.modelspace():
        by_layer[e.dxf.layer].append(e)
    on = lambda role: [e for L in roles.get(role, []) for e in by_layer.get(L, [])]  # noqa: E731
    issues: List[str] = []
    stats: Dict[str, Any] = {}

    def ok(v: float) -> bool:
        return level_range is None or level_range[0] <= v <= level_range[1]

    # contours
    contours: List[Contour] = []
    seen = set()
    dup = 0
    for e in on("contours"):
        vs = _vertices(e)
        if len(vs) < 2:
            continue
        xy = [(x * k, y * k) for x, y, _ in vs]
        key = _key(xy)
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        z = np.array([v[2] for v in vs]) * k
        line = LineString(xy)
        if np.all(np.abs(z) > 1e-9) and np.ptp(z) < 1e-6:
            contours.append(Contour(line, float(z[0]), "3d", e.dxf.layer))
        else:
            contours.append(Contour(line, None, "unlabeled", e.dxf.layer))
    stats["contours_duplicates_removed"] = dup

    labels = []
    for e in on("contour_labels"):
        if e.dxftype() in ("TEXT", "MTEXT"):
            v = parse_level(_text(e))
            if v is not None and ok(v):
                x, y = _text_xy(e)
                labels.append((Point(x * k, y * k), v))
    if labels and any(c.z is None for c in contours):
        need = [c for c in contours if c.z is None]
        tree = STRtree([c.line for c in need])
        votes: Dict[int, List[float]] = defaultdict(list)
        unused = 0
        for pt, v in labels:
            i = tree.nearest(pt)
            if i is not None and need[int(i)].line.distance(pt) <= label_search_m:
                votes[int(i)].append(v)
            else:
                unused += 1
        for i, c in enumerate(need):
            vals = sorted(set(votes.get(i, [])))
            if len(vals) == 1:
                c.z, c.how = vals[0], "label"
            elif len(vals) > 1:
                c.how = "conflict"
                issues.append(f"contour on {c.layer} near ({c.line.coords[0][0]:.1f}, {c.line.coords[0][1]:.1f}) "
                              f"has conflicting labels {vals}; excluded.")
        stats["contour_labels"] = len(labels)
        stats["contour_labels_unused"] = unused
        if unused:
            issues.append(f"{unused} contour label(s) are more than {label_search_m} m from any contour.")
    n_un = sum(c.how == "unlabeled" for c in contours)
    if n_un:
        issues.append(f"{n_un} contour(s) have no Z and no label within {label_search_m} m; excluded.")
    stats["contours"] = Counter(c.how for c in contours)

    # spot levels
    spots: List[Spot] = []
    bad = 0
    out_of_range = 0
    for e in on("spot_levels"):
        t = e.dxftype()
        if t in ("TEXT", "MTEXT"):
            v = parse_level(_text(e))
            if v is None:
                bad += 1
                continue
            if not ok(v):
                out_of_range += 1
                continue
            x, y = _text_xy(e)
            spots.append(Spot(x * k, y * k, v, e.dxf.layer))
        elif t == "POINT" and abs(e.dxf.location.z) > 1e-9:
            p = e.dxf.location
            spots.append(Spot(p.x * k, p.y * k, p.z * k, e.dxf.layer))
        elif t == "INSERT":
            v = next((parse_level(a.dxf.text) for a in getattr(e, "attribs", []) if parse_level(a.dxf.text) is not None), None)
            z = v if v is not None else (e.dxf.insert.z * k if abs(e.dxf.insert.z) > 1e-9 else None)
            if z is not None and ok(z):
                spots.append(Spot(e.dxf.insert.x * k, e.dxf.insert.y * k, z, e.dxf.layer))
    # identical location, different value
    by_xy: Dict[Tuple[float, float], List[float]] = defaultdict(list)
    for s in spots:
        by_xy[(round(s.x, 2), round(s.y, 2))].append(s.z)
    clash = {xy: v for xy, v in by_xy.items() if len(set(v)) > 1}
    for xy, v in clash.items():
        issues.append(f"spot levels at ({xy[0]}, {xy[1]}) disagree: {sorted(set(v))}; all kept.")
    n0 = len(spots)
    uniq = {(round(s.x, 2), round(s.y, 2), s.z): s for s in spots}
    spots = list(uniq.values())
    stats["spots"] = len(spots)
    stats["spots_duplicates_removed"] = n0 - len(spots)
    if bad:
        issues.append(f"{bad} text(s) on spot-level layers are not numbers; ignored.")
    if out_of_range:
        issues.append(f"{out_of_range} spot level(s) outside {level_range}; ignored.")

    # site features
    feats: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for role in ("boundary", "buildings", "drains", "roads", "paths", "water", "walls"):
        seen_f = set()
        for e in on(role):
            vs = _vertices(e)
            if len(vs) < 2:
                continue
            xy = [(x * k, y * k) for x, y, _ in vs]
            key = _key(xy)
            if key in seen_f:
                continue
            seen_f.add(key)
            if _closed(e) and len(xy) >= 3:
                g = Polygon(xy)
                geom = {"type": "Polygon", "coordinates": [list(g.exterior.coords)]}
            else:
                geom = {"type": "LineString", "coordinates": xy}
            feats[role].append({"geometry": geom, "properties": {"kind": role, "layer": e.dxf.layer}})
    for e in on("trees"):
        if e.dxftype() in ("INSERT", "CIRCLE", "POINT"):
            p = e.dxf.insert if e.dxftype() == "INSERT" else (e.dxf.center if e.dxftype() == "CIRCLE" else e.dxf.location)
            r = float(e.dxf.radius) * k if e.dxftype() == "CIRCLE" else None
            feats["trees"].append({"geometry": {"type": "Point", "coordinates": (p.x * k, p.y * k)},
                                   "properties": {"kind": "tree" if r else "tree_unsized", "layer": e.dxf.layer,
                                                  "block": e.dxf.name if e.dxftype() == "INSERT" else "",
                                                  "canopy_radius_m": r}})
    # existing recharge wells: one point each (a circle gives the diameter)
    seen_w = set()
    for e in on("recharge_wells"):
        t = e.dxftype()
        if t not in ("INSERT", "CIRCLE", "POINT"):
            continue
        p = e.dxf.insert if t == "INSERT" else (e.dxf.center if t == "CIRCLE" else e.dxf.location)
        key = (round(p.x * k, 1), round(p.y * k, 1))
        if key in seen_w:
            continue
        seen_w.add(key)
        d = 2 * float(e.dxf.radius) * k if t == "CIRCLE" else None
        feats["recharge_wells"].append({"geometry": {"type": "Point", "coordinates": (p.x * k, p.y * k)},
                                        "properties": {"kind": "recharge_well", "layer": e.dxf.layer, "existing": True,
                                                       "diameter_m": d, "block": e.dxf.name if t == "INSERT" else ""}})
    return Survey(contours, spots, dict(feats), issues, stats)


ROLE_COLOURS = {
    "spot_levels": "#14201f", "contours": "#eb6834", "contour_labels": "#eda100", "boundary": "#1baf7a",
    "buildings": "#6250d6", "trees": "#008300", "drains": "#2a78d6", "roads": "#8a8a8a", "paths": "#c9a26b",
    "water": "#5fb3cf", "walls": "#e87ba4", "recharge_wells": "#6a5acd",
}


def preview(doc, layer_map: Dict[str, Any], out: Path, title: str = "") -> Path:
    """Draw what each role picks up, coloured by role, to check a layer map against the drawing."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    roles = layer_map.get("roles", {})
    layer_role = {L: r for r, Ls in roles.items() for L in Ls}
    fig, ax = plt.subplots(figsize=(11, 9), dpi=130)
    counts: Counter = Counter()
    for e in doc.modelspace():
        r = layer_role.get(e.dxf.layer)
        if r is None:
            continue
        c = ROLE_COLOURS.get(r, "#999999")
        t = e.dxftype()
        if t in ("TEXT", "MTEXT"):
            x, y = _text_xy(e)
            if r == "spot_levels":
                ax.plot(x, y, ".", color=c, ms=3)
            ax.annotate(_text(e)[:12], (x, y), fontsize=4.5, color=c)
        elif t in ("INSERT", "POINT", "CIRCLE"):
            p = e.dxf.insert if t == "INSERT" else (e.dxf.location if t == "POINT" else e.dxf.center)
            ax.plot(p.x, p.y, "o", color=c, ms=3, mfc="none")
        else:
            vs = _vertices(e)
            if len(vs) >= 2:
                xs, ys = [v[0] for v in vs], [v[1] for v in vs]
                if _closed(e):
                    xs.append(xs[0]); ys.append(ys[0])
                ax.plot(xs, ys, color=c, lw=1.6 if r in ("boundary", "contours") else 0.8)
            else:
                continue
        counts[r] += 1
    handles = [Line2D([0], [0], color=ROLE_COLOURS.get(r, "#999"), lw=2,
                      label=f"{r}: {', '.join(roles[r])} ({counts[r]})") for r in roles if counts[r]]
    ax.legend(handles=handles, fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1))
    unmapped = sorted({e.dxf.layer for e in doc.modelspace()} - set(layer_role))
    ax.set_title(f"{title}\nnot mapped (ignored): {', '.join(unmapped)[:220]}", fontsize=8)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


# ------------------------------------------------------------------ layer standard
@lru_cache(maxsize=1)
def layer_standard() -> Dict[str, Any]:
    """The SP-* layer standard (``io/data/layer_standard.json``)."""
    import json
    from importlib import resources

    return json.loads(resources.files(__package__).joinpath("data/layer_standard.json").read_text(encoding="utf-8"))


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


@dataclass
class Rename:
    old: str
    new: str
    confidence: str  # "standard" | "exact" | "partial" | "none"
    entities: int = 0
    note: str = ""


def suggest_renames(inv: Dict[str, Any], standard: Optional[Dict[str, Any]] = None) -> List[Rename]:
    """Propose an SP-* name for every layer of a drawing.

    ``exact``: the whole layer name is a known alias. ``partial``: the name contains an alias (the
    longest one wins) - check it. ``none``: unknown, kept under SP-X-<old name> so nothing is lost.
    Layer 0 cannot be renamed and is left as it is."""
    std = standard or layer_standard()
    names = {s["name"].upper(): s for s in std["layers"]}
    alias = {_norm(a): s for s in std["layers"] for a in s["aliases"]}
    out = []
    for li in inv["layers"]:
        old, n = li["name"], _norm(li["name"])
        count = sum(li["entities"].values())
        if old.upper() in names:
            out.append(Rename(old, names[old.upper()]["name"], "standard", count))
        elif old == "0":
            out.append(Rename(old, "0", "none", count, "layer 0 cannot be renamed; move its entities by hand if they matter"))
        elif n in alias:
            s = alias[n]
            out.append(Rename(old, s["name"], "exact", count, s["description"]))
        else:
            hits = sorted(((a, s) for a, s in alias.items() if a in n), key=lambda t: -len(t[0]))
            if hits:
                a, s = hits[0]
                out.append(Rename(old, s["name"], "partial", count, f"name contains '{a}': {s['description']}"))
            else:
                new = "SP-X-" + re.sub(r"[^A-Z0-9]+", "-", old.upper()).strip("-")
                out.append(Rename(old, new, "none", count, "not in the standard: kept, check what it is"))
    return out


def write_renames(renames: List[Rename], path: Path) -> Path:
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["old_layer", "new_layer", "confidence", "entities", "note"])
        for r in renames:
            w.writerow([r.old, r.new, r.confidence, r.entities, r.note])
    return path


def read_renames(path: Path) -> Dict[str, str]:
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        return {row["old_layer"]: row["new_layer"].strip() for row in csv.DictReader(f) if row["new_layer"].strip()}


def _signature(e) -> Optional[Tuple]:
    """Geometry + content key for exact-duplicate detection (None = never treated as duplicate)."""
    t = e.dxftype()
    r = lambda v: (round(v.x, 3), round(v.y, 3), round(v.z, 3))  # noqa: E731
    if t in ("LWPOLYLINE", "POLYLINE", "LINE", "SPLINE", "ARC"):
        vs = _vertices(e)
        return (t, e.dxf.layer, _closed(e), tuple((round(x, 3), round(y, 3), round(z, 3)) for x, y, z in vs)) if vs else None
    if t in ("TEXT", "MTEXT"):
        return (t, e.dxf.layer, _text(e), r(e.dxf.insert))
    if t == "CIRCLE":
        return (t, e.dxf.layer, r(e.dxf.center), round(e.dxf.radius, 3))
    if t == "POINT":
        return (t, e.dxf.layer, r(e.dxf.location))
    if t == "INSERT":
        return (t, e.dxf.layer, e.dxf.name, r(e.dxf.insert), round(e.dxf.get("rotation", 0), 3),
                tuple(a.dxf.text for a in getattr(e, "attribs", [])))
    return None


def standardise(src: Path, renames: Dict[str, str], out: Path, dedupe: bool = True,
                standard: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write a copy of ``src`` with layers renamed/merged to the standard and exact duplicates removed.

    Every entity (model space, paper space and inside block definitions) is moved to its new layer.
    New layers get the standard colour and a description that records the original layer names.
    Old layers left empty are removed. ``src`` is never modified."""
    std = standard or layer_standard()
    spec = {s["name"]: s for s in std["layers"]}
    doc = read(src)
    moved: Counter = Counter()
    for e in doc.entitydb.values():
        if e.is_alive and e.dxf.hasattr("layer") and e.dxf.layer in renames and renames[e.dxf.layer] != e.dxf.layer:
            moved[(e.dxf.layer, renames[e.dxf.layer])] += 1
            e.dxf.layer = renames[e.dxf.layer]

    sources: Dict[str, List[str]] = defaultdict(list)
    for old, new in renames.items():
        if old != new:
            sources[new].append(old)
    for new, olds in sources.items():
        s = spec.get(new, {})
        lay = doc.layers.get(new) if doc.layers.has_entry(new) else doc.layers.add(new)
        if "color" in s:
            lay.color = int(s["color"])
        try:
            lay.description = f"{s.get('description', '')} | was: {', '.join(sorted(olds))}".strip(" |")
        except Exception:  # description needs R2000+
            pass

    removed = Counter()
    if dedupe:
        msp = doc.modelspace()
        seen = set()
        for e in list(msp):
            k = _signature(e)
            if k is None:
                continue
            if k in seen:
                removed[e.dxf.layer] += 1
                msp.delete_entity(e)
            else:
                seen.add(k)

    used = {e.dxf.layer for e in doc.entitydb.values() if e.is_alive and e.dxf.hasattr("layer")}
    dropped = []
    for old in renames:
        if old not in used and old not in ("0", "Defpoints") and doc.layers.has_entry(old) and old not in sources:
            try:
                doc.layers.remove(old)
                dropped.append(old)
            except Exception:  # the layer is still referenced somewhere (e.g. a layer state)
                log.warning("could not remove layer %s", old)
    out = Path(out)
    doc.saveas(out)
    return {
        "source": str(src), "output": str(out),
        "moved": [{"from": a, "to": b, "entities": n} for (a, b), n in sorted(moved.items())],
        "duplicates_removed": dict(removed), "duplicates_removed_total": int(sum(removed.values())),
        "layers_removed": dropped,
    }
