"""Minimal DEM container and GeoTIFF I/O."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from ..project.crs import LOCAL


@dataclass
class DEM:
    """A north-up elevation grid.

    ``z[row, col]`` in metres; row 0 is the northern edge. ``origin`` is the
    (x, y) of the top-left corner of the top-left cell, in metres.
    """

    z: np.ndarray
    cell_size: float  # m
    origin: Tuple[float, float]  # (x_min, y_max), m
    crs: str = "EPSG:32643"
    nodata: float = -9999.0

    @property
    def shape(self) -> Tuple[int, int]:
        return self.z.shape  # type: ignore[return-value]

    def cell_centres(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return (X, Y) arrays of cell-centre coordinates, m."""
        nr, nc = self.z.shape
        x0, y0 = self.origin
        xs = x0 + (np.arange(nc) + 0.5) * self.cell_size
        ys = y0 - (np.arange(nr) + 0.5) * self.cell_size
        return np.meshgrid(xs, ys)

    def bounds(self) -> Tuple[float, float, float, float]:
        nr, nc = self.z.shape
        x0, y0 = self.origin
        return x0, y0 - nr * self.cell_size, x0 + nc * self.cell_size, y0


def write_geotiff(dem: DEM, path: Path) -> None:
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(
        driver="GTiff",
        height=dem.z.shape[0],
        width=dem.z.shape[1],
        count=1,
        dtype="float32",
        transform=from_origin(dem.origin[0], dem.origin[1], dem.cell_size, dem.cell_size),
        nodata=dem.nodata,
        compress="deflate",
    )
    if dem.crs != LOCAL:
        profile["crs"] = dem.crs
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(dem.z.astype("float32"), 1)


def read_geotiff(path: Path, crs_fallback: Optional[str] = LOCAL) -> DEM:
    import rasterio

    with rasterio.open(path) as src:
        z = src.read(1).astype("float64")
        t = src.transform
        if abs(t.a + t.e) > 1e-9 or t.b or t.d:
            raise ValueError("Only north-up rasters with square cells are supported.")
        crs = src.crs.to_string() if src.crs else crs_fallback
        return DEM(z=z, cell_size=t.a, origin=(t.c, t.f), crs=crs, nodata=src.nodata or -9999.0)
