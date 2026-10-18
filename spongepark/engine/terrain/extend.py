"""Ground for display beyond the surveyed area.

The ground model (``terrain/existing.tif``) only covers where the survey has levels, usually the park
itself. The drawing also shows what is around it (compound wall, roads, drains). To show those on
the ground, :func:`extend_dem` widens the grid to cover them and fills the new cells from the nearest
surveyed ground, smoothed. Filled cells are marked so a viewer can draw them differently. This is
for display only: the hydrological models use the surveyed ground model as it is.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np

from .raster import DEM


def extend_dem(dem: DEM, bounds: Optional[Sequence[float]] = None, margin_m: float = 5.0,
               smooth_m: float = 3.0) -> Tuple[DEM, np.ndarray]:
    """Grid covering the DEM and ``bounds`` (x_min, y_min, x_max, y_max) plus ``margin_m``.

    Returns the extended DEM (no nodata) and a boolean mask, True where the ground was surveyed."""
    from scipy import ndimage

    z0 = np.where(dem.z == dem.nodata, np.nan, dem.z.astype("float64"))
    c = dem.cell_size
    x0, y1 = dem.origin
    x1, y0 = x0 + z0.shape[1] * c, y1 - z0.shape[0] * c
    if bounds is not None:
        bx0, by0, bx1, by1 = bounds
        # whole cells, so the surveyed cells keep their exact positions
        left = max(0, int(np.ceil((x0 - (bx0 - margin_m)) / c)))
        right = max(0, int(np.ceil(((bx1 + margin_m) - x1) / c)))
        top = max(0, int(np.ceil(((by1 + margin_m) - y1) / c)))
        bottom = max(0, int(np.ceil((y0 - (by0 - margin_m)) / c)))
    else:
        left = right = top = bottom = 0
    z = np.full((z0.shape[0] + top + bottom, z0.shape[1] + left + right), np.nan)
    z[top:top + z0.shape[0], left:left + z0.shape[1]] = z0
    surveyed = np.isfinite(z)
    if not surveyed.any():
        raise ValueError("the ground model has no data.")
    if (~surveyed).any():
        idx = ndimage.distance_transform_edt(~surveyed, return_distances=False, return_indices=True)
        filled = z[tuple(idx)]
        smooth = ndimage.gaussian_filter(filled, sigma=max(1.0, smooth_m / c), mode="nearest")
        z = np.where(surveyed, z, smooth)
    out = DEM(z=z, cell_size=c, origin=(x0 - left * c, y1 + top * c), crs=dem.crs, nodata=dem.nodata)
    return out, surveyed
