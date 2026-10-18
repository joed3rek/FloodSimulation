"""Rhino .3dm export and round trip (rhino3dm; no Rhino installation needed).

Export writes the terrain, contours, NbS elements, analysis and context on the brief's layers. Every
NbS object carries user text: all element fields and the SWMM results per return period, plus the
geometry it was exported with (``sp_centroid``, ``sp_area_m2``, ``sp_length_m``) so edits can be
detected.

Import reads an edited file, identifies elements by layer and id, detects moved, resized, deleted
and new elements, marks every edited or new element as a designer element and locks it, updates the
option, then (by default) regrades, rebuilds the subcatchments and reruns SWMM.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import LineString, Point, Polygon, shape

from ..engine.nbs.components import NbSElement, load_elements, save_elements
from ..engine.project import Project
from ..engine.terrain.raster import DEM, read_geotiff

log = logging.getLogger(__name__)

NBS_LAYERS = {"bioswale": "Bioswale", "rain_garden": "RainGarden", "detention_pond": "DetentionPond",
              "retention_pond": "RetentionPond", "recharge_well": "RechargeWell"}
LAYER_TYPE = {v: k for k, v in NBS_LAYERS.items()}
COLOURS = {
    "TERRAIN::Existing": (150, 150, 140), "TERRAIN::Graded": (120, 140, 110),
    "CONTOURS::Existing": (200, 120, 60), "CONTOURS::Proposed": (180, 60, 30),
    "NBS::Bioswale": (27, 175, 122), "NBS::RainGarden": (0, 131, 0), "NBS::DetentionPond": (42, 120, 214),
    "NBS::RetentionPond": (20, 70, 160), "NBS::RechargeWell": (98, 80, 214),
    "ANALYSIS::FlowPaths": (31, 95, 191), "ANALYSIS::Subcatchments": (235, 104, 52),
    "ANALYSIS::CutFill": (227, 73, 72), "ANALYSIS::FloodDepth": (95, 179, 207),
    "CONTEXT::Boundary": (27, 175, 122), "CONTEXT::Buildings": (98, 80, 214), "CONTEXT::Trees": (0, 131, 0),
}
MOVE_TOL_M = 0.10
SIZE_TOL = 0.01


class _Layers:
    def __init__(self, f):
        import rhino3dm as r

        self.f, self.r, self.idx = f, r, {}

    def __call__(self, path: str) -> int:
        if path in self.idx:
            return self.idx[path]
        parent, _, child = path.partition("::")
        if parent not in self.idx:
            L = self.r.Layer()
            L.Name = parent
            self.idx[parent] = self.f.Layers.Add(L)
        L = self.r.Layer()
        L.Name = child
        L.Color = (*COLOURS.get(path, (128, 128, 128)), 255)
        L.ParentLayerId = self.f.Layers.FindIndex(self.idx[parent]).Id
        self.idx[path] = self.f.Layers.Add(L)
        return self.idx[path]


def _sampler(dem: DEM):
    valid = (dem.z != dem.nodata) & np.isfinite(dem.z)
    fallback = float(np.median(dem.z[valid]))

    def z_at(x: float, y: float) -> float:
        c = int((x - dem.origin[0]) / dem.cell_size)
        r = int((dem.origin[1] - y) / dem.cell_size)
        if 0 <= r < dem.z.shape[0] and 0 <= c < dem.z.shape[1] and valid[r, c]:
            return float(dem.z[r, c])
        return fallback
    return z_at


def _mesh(dem: DEM, max_vertices: int = 60000, colours: Optional[np.ndarray] = None):
    import rhino3dm as r

    valid = (dem.z != dem.nodata) & np.isfinite(dem.z)
    step = max(1, int(np.ceil(np.sqrt(valid.sum() / max_vertices))))
    z = dem.z[::step, ::step]
    v = valid[::step, ::step]
    X, Y = dem.cell_centres()
    X, Y = X[::step, ::step], Y[::step, ::step]
    col = colours[::step, ::step] if colours is not None else None
    m = r.Mesh()
    idx = -np.ones(z.shape, int)
    k = 0
    for i, j in zip(*np.nonzero(v)):
        m.Vertices.Add(float(X[i, j]), float(Y[i, j]), float(z[i, j]))
        if col is not None:
            m.VertexColors.Add(*[int(c) for c in col[i, j]])
        idx[i, j] = k
        k += 1
    for i in range(z.shape[0] - 1):
        for j in range(z.shape[1] - 1):
            a, b, c, d = idx[i, j], idx[i, j + 1], idx[i + 1, j + 1], idx[i + 1, j]
            if min(a, b, c, d) >= 0:
                m.Faces.AddFace(int(a), int(d), int(c), int(b))
    m.Normals.ComputeNormals()
    return m


def _attrs(layer: int, name: str = "", user: Optional[Dict[str, Any]] = None):
    import rhino3dm as r

    a = r.ObjectAttributes()
    a.LayerIndex = layer
    if name:
        a.Name = name
    for k, v in (user or {}).items():
        if v is None:
            continue
        a.SetUserString(str(k), v if isinstance(v, str) else json.dumps(v))
    return a


def _polyline(coords, z_at, z: Optional[float] = None):
    import rhino3dm as r

    pl = r.Point3dList()
    for x, y, *rest in coords:
        pl.Add(float(x), float(y), float(z if z is not None else z_at(x, y)))
    return pl


def export_3dm(project: Project, option_id: str, out: Path) -> Dict[str, Any]:
    import rhino3dm as r

    from ..engine.terrain.tin import contour_lines

    f = r.File3dm()
    f.Settings.ModelUnitSystem = r.UnitSystem.Meters
    layer = _Layers(f)
    ex = read_geotiff(project.path("terrain/existing.tif"), crs_fallback=project.manifest.crs)
    z_ex = _sampler(ex)
    f.Objects.AddMesh(_mesh(ex), _attrs(layer("TERRAIN::Existing"), "existing ground"))
    graded_rel = f"scenarios/{option_id}/terrain/graded.tif"
    gr = read_geotiff(project.path(graded_rel)) if project.exists(graded_rel) else None
    z_gr = _sampler(gr) if gr is not None else z_ex
    if gr is not None:
        f.Objects.AddMesh(_mesh(gr), _attrs(layer("TERRAIN::Graded"), f"graded ground ({option_id})"))
    interval = float(min(project.parameters.value("layout.contour_intervals_m")))
    for c in contour_lines(ex, interval):
        f.Objects.AddPolyline(_polyline(c["geometry"]["coordinates"], None, c["properties"]["z"]),
                              _attrs(layer("CONTOURS::Existing"), user={"z": c["properties"]["z"]}))
    if project.exists(f"scenarios/{option_id}/design_contours.geojson"):
        for c in project.read_geojson(f"scenarios/{option_id}/design_contours.geojson")["features"]:
            if c["properties"].get("interval_m", interval) == interval:
                f.Objects.AddPolyline(_polyline(c["geometry"]["coordinates"], None, c["properties"]["z"]),
                                      _attrs(layer("CONTOURS::Proposed"), user={"z": c["properties"]["z"]}))

    # NbS elements with their fields and SWMM results
    results: Dict[str, Dict[str, Any]] = {}
    srel = f"scenarios/{option_id}/results/summary.json"
    if project.exists(srel):
        for rp, v in project.read_json(srel)["return_periods"].items():
            for e in v["elements"]:
                for k, val in e.items():
                    if k not in ("id", "type") and isinstance(val, (int, float)) and val is not None:
                        results.setdefault(e["id"], {})[f"rp{rp}.{k}"] = round(float(val), 4)
    n_el = 0
    for e in load_elements(project, option_id):
        L = layer(f"NBS::{NBS_LAYERS.get(e.type, e.type)}")
        fields = e.model_dump(mode="json", exclude={"geometry", "param_sources"}, exclude_none=True)
        g = shape(e.geometry)
        geo = {"sp_centroid": [round(g.centroid.x, 3), round(g.centroid.y, 3)] if g.geom_type != "Point" else [g.x, g.y],
               "sp_area_m2": round(float(e.footprint().area), 3), "sp_length_m": round(float(g.length), 3),
               "sp_geometry_type": g.geom_type}
        a = _attrs(L, e.id, {**fields, **geo, **results.get(e.id, {})})
        if g.geom_type == "Point":
            dia = float(e.well_diameter_m or project.parameters.value("nbs.recharge_well.diameter_m"))
            f.Objects.AddCircle(r.Circle(r.Point3d(g.x, g.y, z_gr(g.x, g.y)), dia / 2), a)
        elif g.geom_type == "LineString":
            f.Objects.AddPolyline(_polyline(g.coords, z_gr), a)
        else:
            f.Objects.AddPolyline(_polyline(g.exterior.coords, z_ex), a)
        n_el += 1

    # analysis
    if project.exists(f"scenarios/{option_id}/site/subcatchments.geojson") or project.exists("site/subcatchments.geojson"):
        srel = f"scenarios/{option_id}/site/subcatchments.geojson"
        subs = project.read_geojson(srel if project.exists(srel) else "site/subcatchments.geojson")["features"]
        for s in subs:
            g = shape(s["geometry"])
            for poly in getattr(g, "geoms", [g]):
                f.Objects.AddPolyline(_polyline(poly.exterior.coords, z_gr),
                                      _attrs(layer("ANALYSIS::Subcatchments"), s["properties"]["id"],
                                             {"id": s["properties"]["id"], "outlet": s["properties"].get("outlet")}))
    for line in _flow_paths(project):
        f.Objects.AddPolyline(_polyline(line.coords, z_ex), _attrs(layer("ANALYSIS::FlowPaths")))
    cut_rel = f"scenarios/{option_id}/terrain/cut.tif"
    if project.exists(cut_rel) and gr is not None:
        cut = read_geotiff(project.path(cut_rel)).z
        col = _ramp(np.where(cut > 0.005, cut, 0.0), (255, 255, 255), (227, 73, 72))
        f.Objects.AddMesh(_mesh(gr, colours=col), _attrs(layer("ANALYSIS::CutFill"), "cut depth (white 0, red max)"))
    for tif in sorted(project.path(f"scenarios/{option_id}/sim2d").glob("max_depth_rp*.tif")) \
            if project.path(f"scenarios/{option_id}/sim2d").exists() else []:
        d = read_geotiff(tif)
        col = _ramp(np.where(d.z > 0, d.z, 0.0), (240, 240, 240), (31, 95, 191))
        base = DEM(np.where(d.z != d.nodata, d.z + np.nan_to_num(_resample(gr or ex, d)), d.nodata),
                   d.cell_size, d.origin, d.crs, d.nodata)
        f.Objects.AddMesh(_mesh(base, colours=col), _attrs(layer("ANALYSIS::FloodDepth"),
                                                           f"maximum 2D depth {tif.stem} (indicative)"))
    # context
    for b in project.read_geojson("site/boundary.geojson")["features"]:
        g = shape(b["geometry"])
        for poly in getattr(g, "geoms", [g]):
            f.Objects.AddPolyline(_polyline(poly.exterior.coords, z_ex), _attrs(layer("CONTEXT::Boundary")))
    for c in project.read_geojson("site/context.geojson")["features"] if project.exists("site/context.geojson") else []:
        kind = c["properties"].get("kind")
        g = shape(c["geometry"])
        if kind == "buildings" and g.geom_type == "Polygon":
            f.Objects.AddPolyline(_polyline(g.exterior.coords, z_ex), _attrs(layer("CONTEXT::Buildings")))
        elif kind in ("tree", "tree_unsized"):
            rad = float(c["properties"].get("canopy_radius_m") or 1.0)
            f.Objects.AddCircle(r.Circle(r.Point3d(g.x, g.y, z_ex(g.x, g.y)), rad),
                                _attrs(layer("CONTEXT::Trees"), user={"canopy_radius_m": c["properties"].get("canopy_radius_m"),
                                                                      "sized": kind == "tree"}))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not f.Write(str(out), 8):
        raise IOError(f"could not write {out}")
    project.history.log("export_3dm", option=option_id, path=str(out))
    return {"path": str(out), "elements": n_el, "layers": sorted(layer.idx)}


def _ramp(v: np.ndarray, lo, hi) -> np.ndarray:
    m = float(np.nanmax(v)) if np.isfinite(v).any() and np.nanmax(v) > 0 else 1.0
    t = np.clip(np.nan_to_num(v) / m, 0, 1)[..., None]
    return (np.array(lo) * (1 - t) + np.array(hi) * t).astype(int)


def _resample(src: DEM, like: DEM) -> np.ndarray:
    X, Y = like.cell_centres()
    c = ((X - src.origin[0]) / src.cell_size).astype(int).clip(0, src.z.shape[1] - 1)
    r = ((src.origin[1] - Y) / src.cell_size).astype(int).clip(0, src.z.shape[0] - 1)
    z = src.z[r, c]
    return np.where(z == src.nodata, np.nan, z)


def _flow_paths(project: Project) -> List[LineString]:
    """Main flow lines (top 3 % accumulation) as polylines."""
    from shapely.ops import linemerge

    if not project.exists("terrain/flow/accumulation_m2.tif") or not project.exists("terrain/flow/filled.tif"):
        return []
    from ..engine.hydrology import flow as fl

    acc = read_geotiff(project.path("terrain/flow/accumulation_m2.tif"))
    filled = read_geotiff(project.path("terrain/flow/filled.tif"))
    mask = acc.z != acc.nodata
    dirs = fl.d8_directions(np.where(mask, filled.z, np.nan), mask)
    a = np.where(mask, acc.z, np.nan)
    if not np.isfinite(a).any():
        return []
    stream = mask & (a >= np.nanpercentile(a, 97))
    X, Y = acc.cell_centres()
    segs = []
    for rr, cc in zip(*np.nonzero(stream)):
        k = dirs[rr, cc]
        if k < 0:
            continue
        dr, dc = fl.D8[k]
        r2, c2 = rr + dr, cc + dc
        if stream[r2, c2]:
            segs.append(LineString([(X[rr, cc], Y[rr, cc]), (X[r2, c2], Y[r2, c2])]))
    merged = linemerge(segs) if segs else None
    return [] if merged is None else list(getattr(merged, "geoms", [merged]))


# ------------------------------------------------------------------ import
def _curve_geometry(geo) -> Tuple[str, Any]:
    """('Polygon'|'LineString'|'Point', shapely geometry) from a Rhino curve."""
    import rhino3dm as r

    if isinstance(geo, r.ArcCurve) and geo.IsCompleteCircle:
        c = geo.Arc.Center
        return "Point", (Point(c.X, c.Y), geo.Arc.Radius * 2)
    dom = geo.Domain
    n = 200
    pts = []
    ok, pl = (False, None)
    try:
        ok, pl = geo.TryGetPolyline()
    except Exception:
        pass
    if ok and pl is not None:
        pts = [(pl[i].X, pl[i].Y) for i in range(pl.Count)]
    else:
        for t in np.linspace(dom.T0, dom.T1, n):
            p = geo.PointAt(float(t))
            pts.append((p.X, p.Y))
    if geo.IsClosed and len(pts) >= 4:
        return "Polygon", Polygon(pts)
    return "LineString", LineString(pts)


def import_3dm(project: Project, option_id: str, path: Path, rerun: bool = True) -> Dict[str, Any]:
    """Apply a designer's edits from a .3dm to the option. Returns what changed."""
    import rhino3dm as r

    f = r.File3dm.Read(str(path))
    if f is None:
        raise IOError(f"cannot read {path}")
    layer_path = {}
    for i in range(len(f.Layers)):
        L = f.Layers[i]
        layer_path[L.Index] = L.FullPath
    current = {e.id: e for e in load_elements(project, option_id)}
    seen, changes = set(), {"moved": [], "resized": [], "reshaped": [], "new": [], "deleted": [], "unchanged": []}
    out: List[NbSElement] = []
    counters: Dict[str, int] = {}
    for obj in f.Objects:
        lp = layer_path.get(obj.Attributes.LayerIndex, "")
        if not lp.startswith("NBS::"):
            continue
        etype = LAYER_TYPE.get(lp.split("::", 1)[1])
        if etype is None:
            continue
        kind, geom = _curve_geometry(obj.Geometry)
        eid = obj.Attributes.GetUserString("id") or obj.Attributes.Name or ""
        well_dia = None
        if kind == "Point":
            geom, well_dia = geom
        if eid in current and eid not in seen:
            e = current[eid].model_copy(deep=True)
            seen.add(eid)
            old = shape(e.geometry)
            moved = (geom.centroid.distance(old.centroid) > MOVE_TOL_M) if kind != "Point" else geom.distance(old) > MOVE_TOL_M
            area_new = geom.area if kind == "Polygon" else (geom.length if kind == "LineString" else (well_dia or 0))
            area_old = old.area if old.geom_type == "Polygon" else (old.length if old.geom_type == "LineString" else (e.well_diameter_m or 0))
            resized = abs(area_new - area_old) > max(SIZE_TOL * max(area_old, 1e-9), 0.05)
            reshaped = not moved and not resized and kind == "Polygon" and \
                geom.symmetric_difference(old).area > max(SIZE_TOL * old.area, 0.5)
            if not (moved or resized or reshaped):
                changes["unchanged"].append(eid)
                out.append(e)
                continue
            for k, flag in (("moved", moved), ("resized", resized), ("reshaped", reshaped)):
                if flag:
                    changes[k].append(eid)
        else:
            n = counters.get(etype, 0) + 1
            while f"{etype[:2].upper()}_D{n}" in current or f"{etype[:2].upper()}_D{n}" in seen:
                n += 1
            counters[etype] = n
            eid = f"{etype[:2].upper()}_D{n}"
            seen.add(eid)
            e = NbSElement(id=eid, type=etype, geometry={"type": "Point", "coordinates": (0, 0)})
            changes["new"].append(eid)
        e.geometry = geom.__geo_interface__
        if kind == "Point" and well_dia:
            e.well_diameter_m = round(float(well_dia), 3)
        if etype == "bioswale" and kind == "LineString" and e.top_width_m is None:
            e.top_width_m = float(project.parameters.value("nbs.bioswale.top_width_m"))
        e.source = "designer"
        e.locked = True
        e.invert_elev_m = None if e.spec.is_storage else e.invert_elev_m
        out.append(e)
    changes["deleted"] = [i for i in current if i not in seen]
    # storage inverts are recomputed by the regrade; the old value is a placeholder until then
    for e in out:
        if e.spec.is_storage and e.invert_elev_m is None:
            e.invert_elev_m = 0.0
    save_elements(project, option_id, out)
    edited = changes["moved"] + changes["resized"] + changes["reshaped"] + changes["new"]
    locked = set(project.locks.locked.get(option_id, [])) - set(changes["deleted"])
    project.locks.locked[option_id] = sorted(locked | set(edited))
    project.history.log("import_3dm", option=option_id, **{k: v for k, v in changes.items() if k != "unchanged"})
    result: Dict[str, Any] = {"changes": changes, "rerun": False}
    if rerun and any(changes[k] for k in ("moved", "resized", "reshaped", "new", "deleted")):
        from ..engine.layout.apply import regrade
        from ..engine.pipeline import compare, run_option

        result["regrade"] = regrade(project, option_id)
        run_option(project, option_id)
        result["comparison"] = compare(project, option_id) if project.exists("scenarios/baseline/results/summary.json") else None
        result["rerun"] = True
    return result
