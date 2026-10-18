"""Surface from survey points (Delaunay TIN), DEM gridding and quality checks.

The TIN is unconstrained: contours enter as densified points, not breaklines. Drain edges, walls
and kerbs are therefore smoothed across; Phase 3 adds breaklines where they matter for flow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import Delaunay, cKDTree
from shapely import contains_xy
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from .raster import DEM


def build_dem(points: np.ndarray, cell_m: float, crs: str, mask: Optional[BaseGeometry] = None,
              pad_m: float = 2.0, nodata: float = -9999.0) -> DEM:
    """Linear interpolation on the Delaunay TIN of ``points`` (x, y, z), gridded at ``cell_m``.

    Cells outside the points' convex hull, or outside ``mask`` (if given), are nodata.
    """
    if len(points) < 3:
        raise ValueError("at least 3 survey points are needed for a surface.")
    xmin, ymin = points[:, :2].min(axis=0) - pad_m
    xmax, ymax = points[:, :2].max(axis=0) + pad_m
    if mask is not None:
        bx = mask.bounds
        xmin, ymin = min(xmin, bx[0] - pad_m), min(ymin, bx[1] - pad_m)
        xmax, ymax = max(xmax, bx[2] + pad_m), max(ymax, bx[3] + pad_m)
    xmin, ymin = np.floor(xmin / cell_m) * cell_m, np.floor(ymin / cell_m) * cell_m
    xmax, ymax = np.ceil(xmax / cell_m) * cell_m, np.ceil(ymax / cell_m) * cell_m
    nc, nr = int(round((xmax - xmin) / cell_m)), int(round((ymax - ymin) / cell_m))
    dem = DEM(np.zeros((nr, nc)), cell_m, (float(xmin), float(ymax)), crs, nodata)
    X, Y = dem.cell_centres()
    z = LinearNDInterpolator(points[:, :2], points[:, 2])(X, Y)
    if mask is not None:
        z[~contains_xy(mask.buffer(pad_m), X, Y)] = np.nan
    dem.z = np.where(np.isnan(z), nodata, z)
    return dem


def _valid(dem: DEM) -> np.ndarray:
    return dem.z != dem.nodata


def cross_validate_spots(spots: np.ndarray, others: np.ndarray, folds: int = 10, seed: int = 0) -> np.ndarray:
    """Residual (surveyed - interpolated) at each spot, leaving it out (k-fold) of the surface."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(spots))
    res = np.full(len(spots), np.nan)
    for f in range(folds):
        test = idx[f::folds]
        train = np.setdiff1d(idx, test)
        base = np.vstack([spots[train], others]) if len(others) else spots[train]
        if len(base) < 3:
            continue
        pred = LinearNDInterpolator(base[:, :2], base[:, 2])(spots[test, 0], spots[test, 1])
        res[test] = spots[test, 2] - pred
    return res


def contours_decision(survey, min_spots: int = 30) -> Dict[str, Any]:
    """Should the drawn contours shape the ground, or only check it?

    With enough spot levels, contours are left out of the surface when one of them disagrees with the
    spot levels around it by more than a quarter of the contour interval (it would put a false step,
    spike or pit in the ground), or when they all follow the spot levels closely (they were generated
    from them and add nothing but interpolation artefacts). Returns {"use": bool, "reason": str}.
    """
    spots = np.array([(s.x, s.y, s.z) for s in survey.spots]).reshape(-1, 3)
    lab = [c for c in survey.contours if c.z is not None]
    if not lab:
        return {"use": False, "reason": "no contours with levels in the drawing."}
    if len(spots) < min_spots:
        return {"use": True, "reason": f"only {len(spots)} spot levels: the contours are needed to shape the ground."}
    f = LinearNDInterpolator(spots[:, :2], spots[:, 2])
    zc = sorted({c.z for c in lab})
    d = np.diff(zc)
    interval = float(np.min(d[d > 1e-6])) if len(zc) >= 2 and (d > 1e-6).any() else 0.5
    off, checked = [], 0
    for c in lab:
        n = max(2, int(c.line.length))
        pp = np.array([c.line.interpolate(t).coords[0] for t in np.linspace(0, c.line.length, n)])
        zz = f(pp[:, 0], pp[:, 1])
        ok = ~np.isnan(zz)
        if ok.sum() < 2:
            continue
        checked += 1
        diff = float(np.mean(c.z - zz[ok]))
        if abs(diff) > interval / 4:
            x0, y0 = c.line.coords[0]
            off.append(f"{c.z:g} m near ({x0:.0f}, {y0:.0f}) is {diff:+.2f} m from the spot levels")
    if off:
        return {"use": False, "reason": f"{len(off)} of {checked} contours disagree with the spot levels "
                                        f"({'; '.join(off[:3])}): the ground is built from the {len(spots)} spot "
                                        "levels and the contours only check it."}
    if checked:
        return {"use": False, "reason": f"the contours follow the {len(spots)} spot levels closely (they look "
                                        "generated from them): the ground is built from the spot levels."}
    return {"use": True, "reason": "the contours lie outside the spot levels: they extend the ground."}


def quality(survey, dem: DEM, points: np.ndarray, spot_tol_m: float = 0.15, max_gap_m: float = 15.0,
            stated_park_area_m2: Optional[float] = None, contours_in_surface: bool = True) -> Dict[str, Any]:
    """Checks a designer should see before trusting the surface."""
    q: Dict[str, Any] = {"issues": list(survey.issues), "stats": dict(survey.stats),
                         "contours_in_surface": contours_in_surface}
    spots = np.array([(s.x, s.y, s.z) for s in survey.spots]).reshape(-1, 3)
    contour_pts = points[len(spots):] if len(points) > len(spots) else np.empty((0, 3))
    zs = points[:, 2]
    q["elevation_range_m"] = [float(zs.min()), float(zs.max())] if len(zs) else None

    # 1. spot levels against the surface built without them
    if len(spots) >= 10:
        res = cross_validate_spots(spots, contour_pts)
        ok = ~np.isnan(res)
        r = res[ok]
        q["spot_cross_validation"] = {
            "n": int(ok.sum()), "rmse_m": float(np.sqrt(np.mean(r ** 2))), "mae_m": float(np.mean(np.abs(r))),
            "max_abs_m": float(np.max(np.abs(r))), "tolerance_m": spot_tol_m,
        }
        bad = np.nonzero(ok & (np.abs(np.nan_to_num(res)) > spot_tol_m))[0]
        q["spot_outliers"] = [
            {"x": float(spots[i, 0]), "y": float(spots[i, 1]), "z": float(spots[i, 2]), "residual_m": float(res[i])}
            for i in bad[np.argsort(-np.abs(res[bad]))]
        ]
        if len(bad):
            q["issues"].append(f"{len(bad)} spot level(s) differ from their neighbours by more than {spot_tol_m} m "
                               "(typo, a point on a wall or drain, or a real step); see spot_outliers.")

    # 2. contours: interval and crossings
    zc = sorted({c.z for c in survey.contours if c.z is not None})
    if len(zc) >= 2:
        d = np.diff(zc)
        q["contour_levels"] = zc
        q["contour_interval_m"] = float(np.round(np.min(d[d > 1e-6]), 3))
    lab = [c for c in survey.contours if c.z is not None]
    crossings = 0
    for i in range(len(lab)):
        for j in range(i + 1, len(lab)):
            if abs(lab[i].z - lab[j].z) > 1e-6 and lab[i].line.intersects(lab[j].line):
                crossings += 1
    q["contour_crossings"] = crossings
    if crossings:
        q["issues"].append(f"{crossings} pair(s) of contours at different levels cross: a labelling or survey error.")
    if len(spots) >= 3 and lab:
        # contours against the surface built from spot levels alone
        f = LinearNDInterpolator(spots[:, :2], spots[:, 2])
        rows, allb = [], []
        for c in lab:
            n = max(2, int(c.line.length))
            pp = np.array([c.line.interpolate(t).coords[0] for t in np.linspace(0, c.line.length, n)])
            zz = f(pp[:, 0], pp[:, 1])
            ok = ~np.isnan(zz)
            if ok.sum() < 2:
                continue
            b = float(np.mean(c.z - zz[ok]))
            allb += list(c.z - zz[ok])
            x0, y0 = c.line.coords[0]
            rows.append({"z": c.z, "mean_diff_m": b, "length_m": float(c.line.length), "start": [x0, y0]})
        interval = q.get("contour_interval_m", 0.5)
        q["contour_vs_spots"] = {"per_contour": rows,
                                 "rmse_m": float(np.sqrt(np.mean(np.square(allb)))) if allb else None,
                                 "mean_m": float(np.mean(allb)) if allb else None}
        for r_ in rows:
            if abs(r_["mean_diff_m"]) > interval / 4:
                q["issues"].append(f"contour {r_['z']} m near ({r_['start'][0]:.1f}, {r_['start'][1]:.1f}) is "
                                   f"{r_['mean_diff_m']:+.2f} m from the spot levels around it.")
        good = [r_ for r_ in rows if abs(r_["mean_diff_m"]) <= interval / 4]
        if rows and len(good) >= 0.8 * len(rows) and contours_in_surface and len(spots) >= 50:
            q["issues"].append("contours match the spot levels closely (they look generated from them); "
                               "consider contours_in_surface = false so they only check the surface.")
        # spots that contradict the contour levels they sit next to (within 1 m)
        from shapely.geometry import Point
        bad_c = 0
        interval = q.get("contour_interval_m", 0.5)
        for s in spots:
            for c in lab:
                if c.line.distance(Point(s[0], s[1])) < 1.0 and abs(s[2] - c.z) > interval:
                    bad_c += 1
                    break
        q["spots_contradicting_contours"] = bad_c
        if bad_c:
            q["issues"].append(f"{bad_c} spot level(s) within 1 m of a contour differ from it by more than one interval.")

    # 3. TIN: flat triangles (all corners equal, the classic contour artefact)
    if len(points) >= 3:
        tri = Delaunay(points[:, :2])
        zt = points[tri.simplices, 2]
        p = points[tri.simplices, :2]
        area = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                            - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))
        flat_mask = np.ptp(zt, axis=1) < 1e-6
        flat = float(area[flat_mask].sum() / area.sum()) if area.sum() > 0 else 0.0
        q["flat_triangle_area_share"] = flat
        if flat > 0.05:
            q["issues"].append(f"{flat:.0%} of the surveyed area is covered by flat triangles (all corners on one "
                               "contour level): the surface is terraced there; spot levels in valleys and on ridges "
                               "would fix it.")

    # 4. coverage and gaps
    v = _valid(dem)
    X, Y = dem.cell_centres()
    dist, _ = cKDTree(points[:, :2]).query(np.column_stack([X[v], Y[v]]))
    q["max_gap_m"] = float(dist.max()) if dist.size else None
    q["share_cells_beyond_gap"] = float(np.mean(dist > max_gap_m)) if dist.size else None
    if dist.size and q["share_cells_beyond_gap"] > 0:
        q["issues"].append(f"{q['share_cells_beyond_gap']:.0%} of DEM cells are more than {max_gap_m} m from any "
                           "survey point (interpolated across a gap).")
    bnd = survey.features.get("boundary", [])
    polys = [Polygon(f["geometry"]["coordinates"][0]) for f in bnd if f["geometry"]["type"] == "Polygon"]
    if polys:
        main = max(polys, key=lambda p: p.area)
        q["boundary_area_m2"] = float(main.area)
        q["boundary_polygons"] = [float(p.area) for p in polys]
        inside = contains_xy(main, X, Y)
        q["boundary_covered_share"] = float(np.mean(v[inside])) if inside.any() else 0.0
        if q["boundary_covered_share"] < 0.98:
            q["issues"].append(f"only {q['boundary_covered_share']:.0%} of the site boundary has surface data.")
        if stated_park_area_m2:
            dif = (main.area - stated_park_area_m2) / stated_park_area_m2
            q["boundary_vs_stated_area"] = float(dif)
            if abs(dif) > 0.05:
                q["issues"].append(f"surveyed boundary is {main.area:,.0f} m2, the stated park area is "
                                   f"{stated_park_area_m2:,.0f} m2 ({dif:+.0%}).")
        if len(polys) > 1:
            q["issues"].append(f"{len(polys)} boundary polygons ({', '.join(f'{p.area:,.0f}' for p in polys)} m2); "
                               "the largest is used.")

    # 5. slopes
    if v.sum() > 4:
        z = np.where(v, dem.z, np.nan)
        gy, gx = np.gradient(z, dem.cell_size)
        s = 100 * np.hypot(gx, gy)
        s = s[~np.isnan(s)]
        q["slope_pct"] = {"p50": float(np.percentile(s, 50)), "p95": float(np.percentile(s, 95)), "max": float(s.max())}
    return q


def contour_lines(dem: DEM, interval: float) -> List[Dict[str, Any]]:
    """Contours of the DEM as GeoJSON-like features (for comparison with the survey)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    z = np.where(_valid(dem), dem.z, np.nan)
    lo, hi = np.nanmin(z), np.nanmax(z)
    levels = np.arange(np.ceil(lo / interval) * interval, hi + 1e-9, interval)
    X, Y = dem.cell_centres()
    fig = plt.figure()
    cs = plt.contour(X, Y, z, levels=levels)
    out = []
    for lev, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) > 1:
                out.append({"geometry": {"type": "LineString", "coordinates": seg.tolist()},
                            "properties": {"z": float(lev)}})
    plt.close(fig)
    return out
