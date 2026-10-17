"""Export a project's terrain for a quick look in Unity (before the Unity app of Phase 7).

Writes a textured OBJ mesh of the existing-ground DEM: ``<name>.obj`` + ``.mtl`` + ``.png`` (hillshade
tinted by subcatchment, with the main flow paths and outfalls). Drag the folder into a Unity project's
Assets. Unity is Y-up and left-handed and mirrors X when importing OBJ, so vertices are written as
(-east, height, north): in Unity +X is east and +Z is north. Heights are relative to the lowest
ground level and multiplied by ``exaggeration`` (park relief is often under a metre).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from shapely import contains_xy

from ..project import Project
from ..terrain.raster import read_geotiff

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def _rgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255


def _texture(project: Project, dem, valid: np.ndarray, option_id: Optional[str] = None) -> np.ndarray:
    """RGB image (rows north to south) of the terrain and its drainage (and an option's elements)."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from shapely.geometry import shape

    z = np.where(valid, dem.z, np.nanmean(dem.z[valid]))
    gy, gx = np.gradient(z, dem.cell_size)
    # hillshade, light from the north-west, with the relief exaggerated so gentle slopes show
    nx, ny, nz = -gx * 10, gy * 10, np.ones_like(z)
    n = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    light = np.array([-1, 1, 1.5]) / np.linalg.norm([-1, 1, 1.5])
    shade = np.clip((nx * light[0] + ny * light[1] + nz * light[2]) / n, 0, 1)
    img = np.repeat((0.55 + 0.45 * shade)[..., None], 3, axis=2) * np.array([0.93, 0.95, 0.90])
    t = from_origin(dem.origin[0], dem.origin[1], dem.cell_size, dem.cell_size)
    subs = f"options/{option_id}/site/subcatchments.geojson" if option_id else "site/subcatchments.geojson"
    if project.exists(subs):
        feats = project.read_geojson(subs)["features"]
        if feats:
            lab = rasterize([(shape(f["geometry"]), i + 1) for i, f in enumerate(feats)], out_shape=z.shape,
                            transform=t, fill=0, dtype="int32")
            for i in range(1, len(feats) + 1):
                m = lab == i
                img[m] = 0.7 * img[m] + 0.3 * _rgb(PALETTE[(i - 1) % len(PALETTE)])
    if option_id is None and project.exists("terrain/flow/accumulation_m2.tif"):
        acc = read_geotiff(project.path("terrain/flow/accumulation_m2.tif")).z
        a = np.where(valid & (acc > 0), acc, np.nan)
        if np.isfinite(a).any():
            streams = a >= np.nanpercentile(a, 97)
            img[streams] = _rgb("#1f5fbf")
    if project.exists("site/outfalls.geojson"):
        X, Y = dem.cell_centres()
        for f in project.read_geojson("site/outfalls.geojson")["features"]:
            x, y = f["geometry"]["coordinates"][:2]
            img[np.hypot(X - x, Y - y) <= max(1.0, 2 * dem.cell_size)] = _rgb("#14201f")
    if option_id and project.exists(f"options/{option_id}/components.geojson"):
        X, Y = dem.cell_centres()
        for f in project.read_geojson(f"options/{option_id}/components.geojson")["features"]:
            m = contains_xy(shape(f["geometry"]), X, Y)
            col = "#008300" if f["properties"].get("type") == "rain_garden" else "#2a78d6"
            img[m] = 0.35 * img[m] + 0.65 * _rgb(col)
    img[~valid] = 1.0
    return img


def export_obj(project: Project, out_dir: Path, name: str = "terrain", exaggeration: float = 5.0,
               texture_px_per_cell: int = 4, option_id: Optional[str] = None) -> Dict[str, Any]:
    """With ``option_id``: the option's graded ground with its elements. Existing and option exports
    share origin and height datum, so they overlay exactly when both sit at (0, 0, 0) in Unity."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ex = read_geotiff(project.path("terrain/existing.tif"), crs_fallback=project.manifest.crs)
    ex_valid = (ex.z != ex.nodata) & np.isfinite(ex.z)
    if ex_valid.sum() < 4:
        raise ValueError("the DEM has no data.")
    X, Y = ex.cell_centres()
    x0, y0 = float(X[ex_valid].min()), float(Y[ex_valid].min())
    zmin = float(ex.z[ex_valid].min())
    dem = ex
    if option_id:
        rel = f"options/{option_id}/terrain/graded.tif"
        if not project.exists(rel):
            raise ValueError(f"option {option_id} has no graded ground; run `layout generate` first.")
        dem = read_geotiff(project.path(rel), crs_fallback=project.manifest.crs)
    valid = (dem.z != dem.nodata) & np.isfinite(dem.z)
    nr, nc = dem.z.shape
    X, Y = dem.cell_centres()
    x_min, y_min, x_max, y_max = dem.bounds()

    idx = -np.ones(dem.z.shape, int)
    idx[valid] = np.arange(1, valid.sum() + 1)
    lines = [f"# spongepark terrain export: {project.manifest.project_name}",
             f"# Unity axes: +X east, +Y up, +Z north; origin = ({x0:.3f}, {y0:.3f}) survey m, "
             f"height 0 = {zmin:.3f} m, vertical exaggeration x{exaggeration:g}",
             f"mtllib {name}.mtl", f"o {name}"]
    for r, c in zip(*np.nonzero(valid)):
        lines.append(f"v {-(X[r, c] - x0):.3f} {(dem.z[r, c] - zmin) * exaggeration:.4f} {Y[r, c] - y0:.3f}")
    for r, c in zip(*np.nonzero(valid)):
        lines.append(f"vt {(X[r, c] - x_min) / (x_max - x_min):.6f} {(Y[r, c] - y_min) / (y_max - y_min):.6f}")
    lines += [f"usemtl {name}", "s 1"]
    faces = 0
    for r in range(nr - 1):
        for c in range(nc - 1):
            a, b, d, e = idx[r, c], idx[r, c + 1], idx[r + 1, c], idx[r + 1, c + 1]
            # counter-clockwise seen from above in OBJ's right-handed frame (normal +Y); Unity keeps it facing up
            if a > 0 and b > 0 and d > 0:
                lines.append(f"f {a}/{a} {d}/{d} {b}/{b}")
                faces += 1
            if b > 0 and e > 0 and d > 0:
                lines.append(f"f {b}/{b} {d}/{d} {e}/{e}")
                faces += 1
    (out_dir / f"{name}.obj").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / f"{name}.mtl").write_text(
        f"newmtl {name}\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nillum 1\nmap_Kd {name}.png\n", encoding="utf-8")
    img = _texture(project, dem, valid, option_id)
    img = np.repeat(np.repeat(img, texture_px_per_cell, 0), texture_px_per_cell, 1)
    plt.imsave(out_dir / f"{name}.png", np.clip(img, 0, 1))
    info = {
        "project": project.manifest.project_name,
        "crs": dem.crs,
        "origin_survey_m": [x0, y0],
        "ground_level_at_height_0_m": zmin,
        "option": option_id or "existing ground",
        "relief_m": float(dem.z[valid].max() - dem.z[valid].min()),
        "vertical_exaggeration": exaggeration,
        "size_m": [float(X[valid].max() - x0), float(Y[valid].max() - y0)],
        "cell_m": dem.cell_size,
        "vertices": int(valid.sum()),
        "triangles": faces,
        "texture": "hillshade; subcatchments tinted; blue = main flow paths (top 3 % accumulation); dark dots = outfalls",
        "axes": "Unity +X east, +Y up, +Z north (1 unit = 1 m)",
    }
    (out_dir / f"{name}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info
