"""Survey drawing -> project terrain (DEM, boundary, context) with a quality report."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from shapely.geometry import Polygon

from ..io import cad
from ..project import Project
from .raster import write_geotiff
from .tin import build_dem, contour_lines, quality


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def import_survey(project: Project, drawing: Path, layer_map: Dict[str, Any],
                  stated_park_area_m2: Optional[float] = None, require_confirmed: bool = True) -> Dict[str, Any]:
    if require_confirmed and not layer_map.get("confirmed"):
        raise cad.CadError("layer map is not confirmed: check it and set \"confirmed\": true.")
    P = project.parameters
    doc = cad.read(drawing)
    lr = layer_map.get("level_range_m")
    survey = cad.extract(doc, layer_map, label_search_m=float(P.value("terrain.label_search_m")),
                         level_range=tuple(lr) if lr else None)
    use_contours = bool(layer_map.get("contours_in_surface", True))
    if not survey.spots:
        use_contours = True
    pts = survey.points(spacing_m=float(P.value("terrain.contour_point_spacing_m")), include_contours=use_contours)
    dem = build_dem(pts, float(P.value("terrain.dem_cell_m")), project.manifest.crs)
    q = quality(survey, dem, pts, spot_tol_m=float(P.value("terrain.spot_tolerance_m")),
                max_gap_m=float(P.value("terrain.max_gap_m")), stated_park_area_m2=stated_park_area_m2,
                contours_in_surface=use_contours)

    project.write_json("terrain/layer_map.json", layer_map)
    write_geotiff(dem, project.path("terrain/existing.tif"))
    with open(project.path("terrain/survey_points.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x", "y", "z", "source"])
        for s in survey.spots:
            w.writerow([f"{s.x:.3f}", f"{s.y:.3f}", f"{s.z:.3f}", f"spot:{s.layer}"])
        for c in survey.contours:
            if c.z is not None:
                for x, y in c.line.coords:
                    w.writerow([f"{x:.3f}", f"{y:.3f}", f"{c.z:.3f}", f"contour:{c.how}"])
    crs_note = {"crs_note": project.manifest.crs}
    bnd = survey.features.get("boundary", [])
    polys = [f for f in bnd if f["geometry"]["type"] == "Polygon"]
    if polys:
        main = max(polys, key=lambda f: Polygon(f["geometry"]["coordinates"][0]).area)
        project.write_geojson("site/boundary.geojson", {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": main["geometry"], "properties": {"id": "SITE", "source": str(drawing.name)}}]})
    ctx = [{"type": "Feature", "geometry": f["geometry"], "properties": {**f["properties"], "id": f"{role}_{i}"}}
           for role, fs in survey.features.items() if role != "boundary" for i, f in enumerate(fs)]
    project.write_geojson("site/context.geojson", {"type": "FeatureCollection", "features": ctx})
    q["outputs"] = ["terrain/existing.tif", "terrain/survey_points.csv", "terrain/qc.json", "terrain/qc.png",
                    "site/boundary.geojson", "site/context.geojson"]
    q["source"] = {"file": drawing.name, "sha256": _sha256(drawing), **crs_note,
                   "dem_cell_m": dem.cell_size, "dem_shape": list(dem.shape)}
    q["trees_unsized"] = sum(1 for f in survey.features.get("trees", []) if f["properties"]["kind"] == "tree_unsized")
    project.write_json("terrain/qc.json", q)
    _plot(dem, survey, q, project.path("terrain/qc.png"), drawing.stem)
    project.history.log("terrain_import", file=drawing.name, issues=len(q["issues"]))
    return q


def _plot(dem, survey, q, out: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    z = np.where(dem.z != dem.nodata, dem.z, np.nan)
    x0, y0, x1, y1 = dem.bounds()
    fig, ax = plt.subplots(figsize=(9, 9 * (y1 - y0) / max(x1 - x0, 1e-9) + 0.6), dpi=130)
    im = ax.imshow(z, extent=(x0, x1, y0, y1), cmap="Greys_r", interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.7, label="DEM level (m, survey datum)")
    interval = q.get("contour_interval_m") or 0.25
    for f in contour_lines(dem, interval / 2):
        c = np.array(f["geometry"]["coordinates"])
        ax.plot(c[:, 0], c[:, 1], color="#2a78d6", lw=0.6, alpha=0.8)
    for c in survey.contours:
        if c.z is not None:
            x, y = c.line.xy
            ax.plot(x, y, color="#eb6834", lw=1.4)
    for f in survey.features.get("boundary", []):
        if f["geometry"]["type"] == "Polygon":
            c = np.array(f["geometry"]["coordinates"][0])
            ax.plot(c[:, 0], c[:, 1], color="#1baf7a", lw=1.6)
    sp = np.array([(s.x, s.y) for s in survey.spots]).reshape(-1, 2)
    if len(sp):
        ax.scatter(sp[:, 0], sp[:, 1], s=4, color="#14201f")
    for o in q.get("spot_outliers", []):
        ax.scatter([o["x"]], [o["y"]], s=80, facecolors="none", edgecolors="#e34948", lw=1.5)
        ax.annotate(f"{o['residual_m']:+.2f}", (o["x"], o["y"]), fontsize=7, color="#e34948",
                    xytext=(4, 4), textcoords="offset points")
    ax.set_title(f"{title}: DEM (grey), survey contours (orange), DEM contours (blue),\n"
                 "boundary (green), spot levels (dots), outliers (red, residual m)", fontsize=9)
    ax.set_aspect("equal")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
