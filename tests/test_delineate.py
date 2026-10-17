"""Phase 3: flow analysis and subcatchment delineation on synthetic terrains with known answers."""

import numpy as np
import pytest

from spongepark.engine.hydrology import flow as fl
from spongepark.engine.hydrology.delineate import delineate
from spongepark.engine.project import Project
from spongepark.engine.site import Site
from spongepark.engine.terrain import bowl, planar, v_valley, write_geotiff


def _project(tmp_path, dem):
    p = Project.create(tmp_path / "p", "t", crs="EPSG:32643")
    write_geotiff(dem, p.path("terrain/existing.tif"))
    return p


def test_bowl_depression_volume_matches_analytic(tmp_path):
    dem = bowl(size_m=(100, 100), cell_size=1.0, depth_m=2.0)
    mask = np.ones(dem.z.shape, bool)
    filled = fl.fill_sinks(dem.z, mask)
    X, Y = dem.cell_centres()
    deps, _ = fl.depressions(dem.z, filled, mask, 1.0, X, Y)
    assert len(deps) == 1
    # paraboloid z = a r^2 with a = 2 / 50^2, filled to the lowest edge cell (centre 0.5 m inside the rim)
    a, r_fill = 2.0 / 50.0 ** 2, 49.5
    assert deps[0].volume_m3 == pytest.approx(np.pi * a * r_fill ** 4 / 2, rel=0.005)


def test_plane_drains_to_one_outfall_on_its_low_edge(tmp_path):
    dem = planar(size_m=(60, 40), cell_size=1.0, slope_pct=2.0, aspect="south")
    with _project(tmp_path, dem) as p:
        rep = delineate(p)
        assert len(rep["subcatchments"]) == 1
        sc = rep["subcatchments"][0]
        assert sc["area_m2"] == pytest.approx(2400)
        assert sc["depression_m3"] == pytest.approx(0, abs=0.01)
        _, y_min, _, y_max = dem.bounds()
        assert sc["outfall_xy"][1] == pytest.approx(y_min + 0.5)  # bottom row
        assert sc["flow_length_m"] == pytest.approx(38, abs=1.5)  # 95th percentile of a 40 m fall line
        assert sc["slope_pct_median"] == pytest.approx(2.0, abs=0.01)
        site = Site.load(p)
        assert sum(sc.shape().area for sc in site.subcatchments) == pytest.approx(site.boundary.area)


def test_valley_accumulates_all_flow_at_its_mouth(tmp_path):
    dem = v_valley(size_m=(60, 80), cell_size=1.0)
    mask = np.ones(dem.z.shape, bool)
    filled = fl.fill_sinks(dem.z, mask)
    dirs = fl.d8_directions(filled, mask)
    acc = fl.accumulation(filled, mask, dirs)
    # the channel runs between two cell columns: its two mouth cells collect the whole valley
    out = dirs == fl.OUT
    assert out.sum() == 2 and np.nonzero(out)[0].tolist() == [79, 79]
    assert acc[out].sum() == mask.sum()


def test_two_slopes_give_two_subcatchments(tmp_path):
    # a ridge along x = 30: west half falls west, east half falls east
    dem = planar(size_m=(60, 40), cell_size=1.0)
    X, _ = dem.cell_centres()
    x0 = dem.bounds()[0]
    dem.z = 100 - 0.03 * np.abs(X - (x0 + 30))
    with _project(tmp_path, dem) as p:
        rep = delineate(p)
        areas = sorted(r["area_m2"] for r in rep["subcatchments"])
        assert len(areas) == 2 and areas[0] == pytest.approx(1200, rel=0.05)


def test_unity_export_faces_up_and_keeps_orientation(tmp_path):
    from spongepark.engine.io.unity import export_obj

    dem = planar(size_m=(20, 10), cell_size=1.0, slope_pct=2.0, aspect="south")
    with _project(tmp_path, dem) as p:
        delineate(p)
        info = export_obj(p, tmp_path / "u", exaggeration=1.0)
    lines = (tmp_path / "u" / "terrain.obj").read_text().splitlines()
    v = np.array([[float(t) for t in ln.split()[1:]] for ln in lines if ln.startswith("v ")])
    f = [[int(t.split("/")[0]) - 1 for t in ln.split()[1:]] for ln in lines if ln.startswith("f ")]
    assert info["triangles"] == len(f) == 2 * 19 * 9
    for tri in f:
        a, b, c = v[tri]
        assert np.cross(b - a, c - a)[1] > 0  # right-handed CCW from above
    # ground falls to the south: north side (+z) is higher; east is -x before Unity mirrors it
    assert v[v[:, 2].argmax(), 1] > v[v[:, 2].argmin(), 1]
    assert v[:, 0].max() <= 0 and (tmp_path / "u" / "terrain.png").exists()
