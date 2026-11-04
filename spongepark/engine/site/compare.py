"""Before and after: the same storm on the existing site (from the survey) and on the proposed design.

A proposed design's project carries the survey's project (``survey/existing.sponge``). Asked for a storm, this runs the 2D
flood model on both under the same conditions, on a temporary copy of the survey's project so the original stays as it is:
the same rainfall and ground answers, the same grid and time step, the edge held at the same height, and only the inlets
and outlets the designer marked as existing site conditions (the design's own ones are in the design alone).

For each it works out where the rain went, and how much flooding there is:

- ``runoff``: rain (and inlet water) that did not soak in, which is what has to be stored or leave;
- ``flood_m2``: the ground that gets at least the flood depth (``sim2d.flood_depth_threshold_m``) during the storm;
- ``not_collected``: the same, outside the rain gardens and swales: runoff the design is not catching where it should.
  The existing site has none of them, so all its flooding counts.

Written to ``comparison/rp<rp>.json`` and ``comparison/rp<rp>.png``; the flooded areas go in the viewers' layers, one for
before and one for after. Indicative, as the 2D model is: for comparing the two, not absolute prediction.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..project import Project

log = logging.getLogger(__name__)

EXISTING = "survey/existing.sponge"
BEFORE_LAYER = "Before: flooded"
AFTER_LAYER = "After: flood not collected"
MIN_PATCH_CELLS = 2   # one wet cell on its own is not an area to act on
MAX_LISTED = 12


def available(project: Project) -> bool:
    return project.exists(EXISTING)


def _same_conditions(design: Project, existing: Project) -> None:
    """The existing site under the design's rain, ground, grid and time step, with its edge held the same way."""
    from ..rainfall.presets import apply as set_rain, current
    from . import ground, openings, outfalls

    rain = current(design)
    if rain is None:
        raise ValueError("set the rainfall first (Site setup > Rainfall).")
    set_rain(existing, None, rain["rows"], rain.get("source") or "the design's rainfall")
    answers = (ground.load(design) or {}).get("answers")
    if not answers:
        raise ValueError("answer the ground questions first (Site setup > Ground).")
    ground.apply(existing, answers)
    if design.exists(outfalls.REL):
        existing.write_json(outfalls.REL, design.read_json(outfalls.REL))
    existing.write_json(openings.REL, {"openings": [o for o in openings.load(design)["openings"] if o["origin"] == "site"],
                                       "confirmed": True})
    from ..project.parameters import Source

    for key, unit in (("sim2d.cell_m", "m"), ("sim2d.courant", "-")):
        existing.parameters.set(key, design.parameters.value(key), unit, Source.DEFAULT, "As the proposed design, to compare them.")


def _read(project: Project, rp: int) -> Dict[str, Any]:
    from ..terrain.raster import read_geotiff

    dem = read_geotiff(project.path(f"scenarios/baseline/sim2d/max_depth_rp{rp}.tif"))
    frames = np.load(project.path(f"scenarios/baseline/sim2d/rp{rp}.npz"))
    return {"max": np.where(dem.z != dem.nodata, dem.z, 0.0), "grid": dem, "mask": frames["mask"].astype(bool),
            "frames": frames["depth_m"].astype(float)}


def _measure(run: Dict[str, Any], grid: Dict[str, Any], thr: float, zone: Optional[np.ndarray], flow: Dict[str, Any]) -> Dict[str, Any]:
    """Where the rain went and how much flooding, from the run's balance and its depths."""
    from scipy import ndimage

    b = run["balance"]
    dem, mask, hmax = grid["grid"], grid["mask"], grid["max"]
    cell = dem.cell_size
    X, Y = dem.cell_centres()
    in_zone = np.zeros(mask.shape, bool) if zone is None else zone
    flood = (hmax >= thr) & mask
    outside = flood & ~in_zone
    lab, n = ndimage.label(outside, structure=np.ones((3, 3)))
    patches: List[Dict[str, Any]] = []
    for k in range(1, n + 1):
        m = lab == k
        if m.sum() < MIN_PATCH_CELLS:
            outside[m] = False
            continue
        i = np.unravel_index(int(np.argmax(np.where(m, hmax, -1))), m.shape)
        patches.append({"x": round(float(X[i]), 1), "y": round(float(Y[i]), 1), "area_m2": round(float(m.sum() * cell * cell), 1),
                        "max_depth_m": round(float(hmax[i]), 2)})
    patches.sort(key=lambda p: -p["area_m2"])
    frames = grid["frames"]
    peak_out = float((frames * (outside & mask)).sum(axis=(1, 2)).max()) * cell * cell if len(frames) else 0.0
    peak_in = float((frames * (in_zone & mask)).sum(axis=(1, 2)).max()) * cell * cell if len(frames) else 0.0
    rain, inlet, soaked = float(b["rainfall_m3"]), float(b.get("inlet_m3", 0.0)), float(b["infiltration_ground_m3"]) + float(b["infiltration_elements_m3"])
    area = float(mask.sum() * cell * cell)
    return {"site_m2": round(area, 1), "rain_m3": round(rain, 1), "inlet_m3": round(inlet, 1), "soaked_in_m3": round(soaked, 1),
            "runoff_m3": round(rain + inlet - soaked, 1), "runoff_mm": round(1000 * (rain + inlet - soaked) / area, 1),
            "runoff_share": round((rain + inlet - soaked) / (rain + inlet), 3) if rain + inlet else 0.0,
            "left_site_m3": round(float(b["outflow_m3"]), 1), "standing_at_end_m3": round(float(b["surface_remaining_m3"]), 1),
            "flood_m2": round(float(flood.sum() * cell * cell), 1), "flood_share": round(float(flood.sum() / mask.sum()), 3),
            "not_collected_m2": round(float(outside.sum() * cell * cell), 1), "not_collected_peak_m3": round(peak_out, 1),
            "collected_peak_m3": round(peak_in, 1), "deepest_m": round(float(hmax[mask].max()), 2),
            "deepest_not_collected_m": round(float(hmax[outside].max()), 2) if outside.any() else 0.0,
            "pooling_points": int(flow.get("hotspots", 0)), "hollows_hold_m3": round(float(flow.get("ponding_volume_m3", 0.0)), 1),
            "patches": patches, "outside": outside}


def _zone_on(project: Project, dem) -> np.ndarray:
    from scipy import ndimage
    from shapely import contains_xy
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from ..io.model3d import NBS_ZONES

    X, Y = dem.cell_centres()
    if not project.exists(NBS_ZONES):
        return np.zeros(X.shape, bool)
    zone = contains_xy(unary_union([shape(f["geometry"]) for f in project.read_geojson(NBS_ZONES)["features"]]), X, Y)
    return ndimage.binary_dilation(zone, structure=np.ones((3, 3)))   # the banks they spill to are theirs


def _mesh(mask: np.ndarray, dem, level, color: str, name: str, title: str, visible: bool) -> Optional[Dict[str, Any]]:
    """A cell mask as a smooth surface for the viewers: rounded off the grid's steps, lying on ``level(x, y)``."""
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from shapely import delaunay_triangles
    from shapely.geometry import shape

    if not mask.any():
        return None
    t = from_origin(dem.origin[0], dem.origin[1], dem.cell_size, dem.cell_size)
    r = dem.cell_size * 0.5
    feats = []
    for geom, _ in shapes(mask.astype("uint8"), mask=mask, transform=t):
        poly = shape(geom).buffer(r, quad_segs=2).buffer(-r, quad_segs=2)
        for part in getattr(poly, "geoms", [poly]):
            if part.is_empty or part.geom_type != "Polygon":
                continue
            part = part.segmentize(dem.cell_size * 2)
            tris = [g for g in delaunay_triangles(part).geoms if part.contains(g.representative_point())]
            if not tris:
                continue
            xy = np.array([c for g in tris for c in list(g.exterior.coords)[:3]])
            v, idx = np.unique(np.round(xy, 2), axis=0, return_inverse=True)
            xyz = np.c_[v, level(v[:, 0], v[:, 1])]
            feats.append({"g": "mesh", "xyz": np.round(xyz, 3).ravel().tolist(), "tri": np.asarray(idx).ravel().tolist(),
                          "color": color, "smooth": True})
    if not feats:
        return None
    return {"name": name, "title": title, "kind": "model", "color": color, "visible": visible, "count": len(feats), "role": "flood",
            "features": feats}


def _layers(project: Project, before, after, rp: int, ground_dem) -> None:
    """Put the two flooded areas in the viewers' layers, drawn on the design's ground."""
    from . import survey_layers

    z = np.where(ground_dem.z != ground_dem.nodata, ground_dem.z, np.nan)
    fill = float(np.nanmedian(z))

    def level(depth_grid):
        def at(x, y):
            c = np.clip(((x - ground_dem.origin[0]) / ground_dem.cell_size).astype(int), 0, z.shape[1] - 1)
            r = np.clip(((ground_dem.origin[1] - y) / ground_dem.cell_size).astype(int), 0, z.shape[0] - 1)
            return np.nan_to_num(z[r, c], nan=fill) + 0.05
        return at

    doc = project.read_json(survey_layers.REL)
    doc["layers"] = [L for L in doc["layers"] if L.get("role") != "flood"]
    new = [_mesh(after["outside"], after["grid"], level(after), "#E53935", AFTER_LAYER, f"After: flood not collected ({rp}-year)", True),
           _mesh(before["outside"], before["grid"], level(before), "#FB8C00", BEFORE_LAYER, f"Before: flooded ({rp}-year)", False)]
    doc["layers"] += [L for L in new if L]
    project.write_json(survey_layers.REL, doc)


def _picture(project: Project, rp: int, before, after, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    top = max(float(before["grid_max"]), float(after["grid_max"]), 0.1)
    fig, ax = plt.subplots(1, 2, figsize=(16, 7), dpi=110)
    for a, side, title in zip(ax, (before, after), (f"Before: existing site, {rp}-year storm", f"After: proposed design, {rp}-year storm")):
        dem, hmax, outside = side["grid"], side["max"], side["outside"]
        x0, y0, x1, y1 = dem.bounds()
        a.set_facecolor("#E8E8E2")
        im = a.imshow(np.ma.masked_less(np.where(side["mask"], hmax, 0.0), 0.01), extent=(x0, x1, y0, y1), cmap="Blues", vmin=0, vmax=top)
        X, Y = dem.cell_centres()
        if outside.any():
            a.contour(X, Y, outside.astype(float), levels=[0.5], colors="#E53935", linewidths=1.0)
        a.set_title(f"{title}\nflood not collected {side['not_collected_m2']:,.0f} m2 (red outline), runoff {side['runoff_m3']:,.0f} m3", fontsize=11)
        a.set_aspect("equal")
    fig.colorbar(im, ax=ax, shrink=0.8, label="Deepest water in the storm (m)")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def run(project: Project, rp: int) -> Dict[str, Any]:
    """The same storm on the existing site and the proposed design. Returns and saves what changed."""
    from ..sim2d.run import run2d
    from ..terrain.raster import read_geotiff
    from . import analysis

    if not available(project):
        raise ValueError("this project has no survey with it: before and after needs a proposed design made with its survey.")
    thr = float(project.parameters.value("sim2d.flood_depth_threshold_m"))
    if not project.exists(analysis.REL):
        analysis.run(project)
    after_run = run2d(project, "baseline", rp, engine="builtin")
    after_grid = _read(project, rp)
    flow_after = project.read_json("site/flow_analysis.json").get("summary", {}) if project.exists("site/flow_analysis.json") else {}
    after = {**_measure(after_run, after_grid, thr, _zone_on(project, after_grid["grid"]), flow_after), **after_grid}

    tmp = Path(tempfile.mkdtemp(prefix="spongepark_before_"))
    try:
        copy = tmp / "existing.sponge"
        shutil.copy2(project.path(EXISTING), copy)
        with Project.open(copy) as ex:
            _same_conditions(project, ex)
            flow_before = analysis.run(ex)["flow"]
            before_run = run2d(ex, "baseline", rp, engine="builtin")
            before_grid = _read(ex, rp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    before = {**_measure(before_run, before_grid, thr, None, flow_before), **before_grid}

    for side in (before, after):
        side["grid_max"] = side["deepest_m"]
    project.path("comparison").mkdir(exist_ok=True)
    image = project.path(f"comparison/rp{rp}.png")
    _picture(project, rp, before, after, image)
    _layers(project, before, after, rp, read_geotiff(project.path("terrain/existing.tif")))

    keep = lambda side: {k: v for k, v in side.items() if k not in ("outside", "max", "grid", "mask", "frames", "grid_max")}

    def change(key):
        a, b = before[key], after[key]
        return round(100 * (b - a) / a, 1) if a else None

    out = {"rp": rp, "before": keep(before), "after": keep(after), "flood_depth_m": thr, "image": str(image),
           "change_pct": {k: change(k) for k in ("runoff_m3", "runoff_mm", "flood_m2", "not_collected_m2", "not_collected_peak_m3", "deepest_m")},
           "label": after_run.get("label"), "infiltration": {"before": before_run["infiltration"], "after": after_run["infiltration"]},
           "before_layer": BEFORE_LAYER, "after_layer": AFTER_LAYER}
    project.write_json(f"comparison/rp{rp}.json", {k: v for k, v in out.items() if k != "image"})
    project.history.log("before_and_after", rp=rp)
    return out
