"""Grade NbS elements into the existing-ground DEM.

An element is cut into the ground below its *rim*: the lowest ground level just outside its
footprint, where water would spill out. The design surface inside the footprint falls from the rim
at the side slope to the bottom (rim - depth). Grading only cuts; berms are not built, so the
overflow level is the existing rim and the storage is conservative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class Cut:
    rim_m: float  # spill level (lowest ground just outside the footprint)
    bottom_m: float  # rim - depth
    cut_m3: float  # excavated volume
    storage_m3: float  # volume below the rim on the graded surface
    area_m2: float


def rim_level(z: np.ndarray, region: np.ndarray, mask: np.ndarray) -> float:
    """Lowest ground on the ring of cells just outside ``region`` (inside the domain)."""
    from scipy import ndimage

    ring = ndimage.binary_dilation(region, structure=np.ones((3, 3))) & ~region & mask
    if ring.any():
        return float(z[ring].min())
    edge = region & ~ndimage.binary_erosion(region, structure=np.ones((3, 3)))
    return float(z[edge].min())


def design_surface(region: np.ndarray, cell: float, rim: float, depth: float,
                   side_slope_h_v: Optional[float]) -> np.ndarray:
    """Design level for cells of ``region`` (NaN elsewhere)."""
    from scipy import ndimage

    bottom = rim - depth
    if side_slope_h_v:
        d = (ndimage.distance_transform_edt(region) - 0.5) * cell  # distance in from the footprint edge
        zd = np.maximum(bottom, rim - d / side_slope_h_v)
    else:
        zd = np.full(region.shape, bottom)
    return np.where(region, zd, np.nan)


def flat_volume(region: np.ndarray, cell: float, depth: float, side_slope_h_v: Optional[float]) -> float:
    """Storage of the footprint on flat ground (used while sizing)."""
    zd = design_surface(region, cell, 0.0, depth, side_slope_h_v)
    return float(np.nansum(-zd) * cell ** 2)


def grade(z: np.ndarray, region: np.ndarray, mask: np.ndarray, cell: float, depth: float,
          side_slope_h_v: Optional[float]) -> tuple:
    """Cut ``region`` into ``z``. Returns (graded z, Cut)."""
    rim = rim_level(z, region, mask)
    zd = design_surface(region, cell, rim, depth, side_slope_h_v)
    out = z.copy()
    m = region & (zd < z)
    out[m] = zd[m]
    cut = float((z - out)[region].sum() * cell ** 2)
    storage = float(np.clip(rim - out[region], 0, None).sum() * cell ** 2)
    return out, Cut(rim, rim - depth, cut, storage, float(region.sum() * cell ** 2))
