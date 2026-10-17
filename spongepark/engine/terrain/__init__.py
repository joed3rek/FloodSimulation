"""Terrain: DEM container, GeoTIFF I/O and synthetic test terrains (TIN/DEM generation in Phase 2)."""

from .raster import DEM, read_geotiff, write_geotiff
from .synthetic import GENERATORS, bowl, planar, v_valley

__all__ = ["DEM", "GENERATORS", "bowl", "planar", "read_geotiff", "v_valley", "write_geotiff"]
