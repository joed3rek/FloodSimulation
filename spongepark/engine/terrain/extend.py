"""Ground for display beyond the surveyed area.

The ground model (``terrain/existing.tif``) only covers where the survey has levels, usually the park
itself. The drawing also shows what is around it (compound wall, roads, drains). To show those on
the ground, :func:`extend_dem` widens the grid to cover them:

- inside the park boundary the ground is the park's own: surveyed cells as they are, gaps filled from
  the nearest surveyed ground;
- outside it is a smooth base (the roads and verges): a plane through the ground along the park's
  edge, kept a little below the nearest park ground so it never shows through the park where the park
  slopes down.

Cells outside the park boundary are marked "not surveyed" so a viewer draws them differently. This is
for display only: the hydrological models use the surveyed ground model as it is.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np

from .raster import DEM

BASE_BELOW_PARK_M = 0.15   # the base (road) sits this far below the park ground next to it


def extend_dem(dem: DEM, bounds: Optional[Sequence[float]] = None, margin_m: float = 5.0,
               boundary=None) -> Tuple[DEM, np.ndarray]:
    """Grid covering the DEM and ``bounds`` (x_min, y_min, x_max, y_max) plus ``margin_m``.

    ``boundary``: the park's polygon (shapely), if known. Returns the extended DEM (no nodata) and a
    boolean mask, True for park ground (inside the boundary, or surveyed when there is no boundary)."""
    from scipy import ndimage
    from shapely import contains_xy

    z0 = np.where(dem.z == dem.nodata, np.nan, dem.z.astype("float64"))
    c = dem.cell_size
    x0, y1 = dem.origin
    x1, y0 = x0 + z0.shape[1] * c, y1 - z0.shape[0] * c
    left = right = top = bottom = 0
    if bounds is not None:
        bx0, by0, bx1, by1 = bounds
        # whole cells, so the surveyed cells keep their exact positions
        left = max(0, int(np.ceil((x0 - (bx0 - margin_m)) / c)))
        right = max(0, int(np.ceil(((bx1 + margin_m) - x1) / c)))
        top = max(0, int(np.ceil(((by1 + margin_m) - y1) / c)))
        bottom = max(0, int(np.ceil((y0 - (by0 - margin_m)) / c)))
    z = np.full((z0.shape[0] + top + bottom, z0.shape[1] + left + right), np.nan)
    z[top:top + z0.shape[0], left:left + z0.shape[1]] = z0
    origin = (x0 - left * c, y1 + top * c)
    surveyed = np.isfinite(z)
    if not surveyed.any():
        raise ValueError("the ground model has no data.")

    if boundary is not None:
        R, C = z.shape
        X = origin[0] + (np.arange(C) + 0.5) * c
        Y = origin[1] - (np.arange(R) + 0.5) * c
        XX, YY = np.meshgrid(X, Y)
        park = contains_xy(boundary, XX, YY)
        if not (park & surveyed).any():
            park = surveyed
    else:
        park = surveyed

    # park ground: surveyed cells, gaps filled from the nearest surveyed cell (lightly smoothed)
    idx = ndimage.distance_transform_edt(~surveyed, return_distances=False, return_indices=True)
    nearest = z[tuple(idx)]
    filled = np.where(surveyed, z, ndimage.gaussian_filter(nearest, sigma=max(1.0, 1.0 / c), mode="nearest"))
    out = np.where(park, filled, np.nan)

    # base outside the park: a plane through the park ground along its edge, below the nearest park cell
    edge = park & ~ndimage.binary_erosion(park, iterations=2)
    rr, cc = np.nonzero(edge & np.isfinite(out))
    if len(rr) >= 3:
        A = np.c_[cc * c, -rr * c, np.ones(len(rr))]
        coef, *_ = np.linalg.lstsq(A, out[rr, cc], rcond=None)
        R, C = out.shape
        gr, gc = np.mgrid[0:R, 0:C]
        plane = coef[0] * gc * c - coef[1] * gr * c + coef[2]
    else:
        plane = np.full(out.shape, np.nanmin(out))
    pidx = ndimage.distance_transform_edt(~park, return_distances=False, return_indices=True)
    near_park = out[tuple(pidx)]
    base = np.minimum(plane, near_park) - BASE_BELOW_PARK_M
    base = ndimage.gaussian_filter(base, sigma=max(1.0, 2.0 / c), mode="nearest")
    base = np.minimum(base, near_park - BASE_BELOW_PARK_M)   # smoothing must not lift it above the park
    out = np.where(park, out, base)
    return DEM(z=out, cell_size=c, origin=origin, crs=dem.crs, nodata=dem.nodata), park
