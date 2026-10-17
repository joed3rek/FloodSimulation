"""Phase 0: synthetic terrains and GeoTIFF I/O."""

import numpy as np
import pytest

from spongepark.engine.terrain import bowl, planar, read_geotiff, v_valley, write_geotiff
from spongepark.engine.terrain.synthetic import bowl_volume_below_rim


def test_planar_slope():
    d = planar(size_m=(50, 40), cell_size=0.5, slope_pct=2.0, aspect="south")
    assert d.z.shape == (80, 100)
    # rows run north -> south; elevation falls southwards at 2 %
    dz = np.diff(d.z[:, 0])
    assert np.allclose(dz, -0.02 * 0.5)


def test_v_valley_lowest_on_centreline():
    d = v_valley(size_m=(40, 40), cell_size=1.0)
    lowest_cols = np.argmin(d.z, axis=1)
    assert np.all(np.abs(lowest_cols - 19.5) <= 0.5)


def test_bowl_volume_matches_analytic():
    depth, size, cell = 2.0, 100.0, 0.25
    d = bowl(size_m=(size, size), cell_size=cell, depth_m=depth)
    rim = d.z.min() + depth
    X, Y = d.cell_centres()
    inside = (X - X.mean()) ** 2 + (Y - Y.mean()) ** 2 <= (size / 2) ** 2
    vol = np.sum((rim - d.z)[inside]) * cell * cell
    assert vol == pytest.approx(bowl_volume_below_rim(depth, size / 2), rel=0.01)


def test_geotiff_roundtrip(tmp_path):
    d = planar(size_m=(20, 10), cell_size=0.5)
    write_geotiff(d, tmp_path / "t.tif")
    r = read_geotiff(tmp_path / "t.tif")
    assert r.cell_size == 0.5
    assert r.origin == pytest.approx(d.origin)
    assert np.allclose(r.z, d.z, atol=1e-4)
    assert "32643" in r.crs
