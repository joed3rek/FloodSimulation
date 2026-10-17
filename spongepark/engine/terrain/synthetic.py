"""Synthetic test terrains with known analytical behaviour.

* planar: uniform slope; every cell drains in the slope direction.
* v_valley: two planes meeting at a channel that itself slopes; all flow
  collects in the centre line.
* bowl: paraboloid; a single pit at the centre whose volume below the rim is
  known analytically (pi * a * R^4 / 2 for z = a r^2 up to radius R).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from .raster import DEM

DEFAULT_ORIGIN = (781000.0, 1434100.0)  # UTM 43N, near central Bengaluru


def planar(
    size_m: Tuple[float, float] = (100.0, 100.0),
    cell_size: float = 0.5,
    slope_pct: float = 2.0,
    base_elev: float = 900.0,
    aspect: str = "south",
    origin: Tuple[float, float] = DEFAULT_ORIGIN,
) -> DEM:
    """A plane falling towards ``aspect`` (north/south/east/west) at ``slope_pct``."""
    nx, ny = int(round(size_m[0] / cell_size)), int(round(size_m[1] / cell_size))
    dem = DEM(z=np.zeros((ny, nx)), cell_size=cell_size, origin=origin)
    X, Y = dem.cell_centres()
    xmin, ymin, xmax, ymax = dem.bounds()
    s = slope_pct / 100.0
    dist = {"south": Y - ymin, "north": ymax - Y, "west": X - xmin, "east": xmax - X}[aspect]
    dem.z = base_elev + s * dist
    return dem


def v_valley(
    size_m: Tuple[float, float] = (100.0, 100.0),
    cell_size: float = 0.5,
    side_slope_pct: float = 5.0,
    channel_slope_pct: float = 1.0,
    base_elev: float = 900.0,
    origin: Tuple[float, float] = DEFAULT_ORIGIN,
) -> DEM:
    """A valley running north to south along the centre line x = x_mid."""
    nx, ny = int(round(size_m[0] / cell_size)), int(round(size_m[1] / cell_size))
    dem = DEM(z=np.zeros((ny, nx)), cell_size=cell_size, origin=origin)
    X, Y = dem.cell_centres()
    xmin, ymin, xmax, _ = dem.bounds()
    xmid = 0.5 * (xmin + xmax)
    dem.z = base_elev + side_slope_pct / 100.0 * np.abs(X - xmid) + channel_slope_pct / 100.0 * (Y - ymin)
    return dem


def bowl(
    size_m: Tuple[float, float] = (100.0, 100.0),
    cell_size: float = 0.5,
    depth_m: float = 2.0,
    base_elev: float = 900.0,
    origin: Tuple[float, float] = DEFAULT_ORIGIN,
) -> DEM:
    """Paraboloid z = base + a r^2, with ``depth_m`` rise at the inscribed radius R."""
    nx, ny = int(round(size_m[0] / cell_size)), int(round(size_m[1] / cell_size))
    dem = DEM(z=np.zeros((ny, nx)), cell_size=cell_size, origin=origin)
    X, Y = dem.cell_centres()
    xmin, ymin, xmax, ymax = dem.bounds()
    cx, cy = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax)
    R = 0.5 * min(xmax - xmin, ymax - ymin)
    a = depth_m / R**2
    dem.z = base_elev + a * ((X - cx) ** 2 + (Y - cy) ** 2)
    return dem


def bowl_volume_below_rim(depth_m: float, radius_m: float) -> float:
    """Analytical volume (m3) of a paraboloid bowl filled to its rim at ``radius_m``."""
    a = depth_m / radius_m**2
    return np.pi * a * radius_m**4 / 2.0


GENERATORS = {"planar": planar, "v_valley": v_valley, "bowl": bowl}
