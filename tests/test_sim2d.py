"""Phase 6: 2D rain-on-grid model: mass balance, ponding, and volume agreement with SWMM."""

import numpy as np
import pandas as pd
import pytest

from spongepark.engine.hydrology.delineate import delineate
from spongepark.engine.pipeline import make_hyetographs, run_option
from spongepark.engine.project import Project, Source
from spongepark.engine.sim2d.model import Elements2D, simulate
from spongepark.engine.sim2d.run import run2d
from spongepark.engine.terrain import bowl, planar, write_geotiff


def _rain(mm_hr=30.0, hours=1.0, dt_s=300.0):
    return np.full(int(hours * 3600 / dt_s), mm_hr), dt_s


def test_mass_balance_closes_on_a_plane():
    dem = planar(size_m=(30, 20), cell_size=1.0, slope_pct=2.0, aspect="south")
    mask = np.ones(dem.z.shape, bool)
    rain, dt = _rain()
    r = simulate(dem.z, mask, 1.0, rain, dt, 2 * 3600, np.full(dem.z.shape, 0.03), np.zeros(dem.z.shape))
    b = r.balance
    assert b["rainfall_m3"] == pytest.approx(600 * 0.03, rel=1e-6)
    assert abs(b["continuity_error_pct"]) < 0.01
    assert b["outflow_m3"] > 0.95 * b["rainfall_m3"]  # an impervious plane drains


def test_bowl_holds_water_and_element_takes_its_capacity():
    dem = bowl(size_m=(40, 40), cell_size=1.0, depth_m=1.0)
    mask = np.ones(dem.z.shape, bool)
    rain, dt = _rain(50, 1)
    r = simulate(dem.z, mask, 1.0, rain, dt, 3 * 3600, np.full(dem.z.shape, 0.05), np.zeros(dem.z.shape))
    assert r.balance["outflow_m3"] < 0.05 * r.balance["rainfall_m3"]
    assert r.max_depth.max() > 0.05
    # an element at the bottom with room for 10 m3 takes exactly that, the rest ponds around it
    lab = -np.ones(dem.z.shape, np.int64)
    lab[19:21, 19:21] = 0
    els = Elements2D(lab, ["E"], np.array([10.0]), np.array([0.0]), np.array([4.0]))
    r2 = simulate(dem.z, mask, 1.0, rain, dt, 3 * 3600, np.full(dem.z.shape, 0.05), np.zeros(dem.z.shape), els)
    assert r2.element_store_m3["E"] == pytest.approx(10.0, rel=1e-6)
    assert abs(r2.balance["continuity_error_pct"]) < 0.01


@pytest.fixture(scope="module")
def plane_project(tmp_path_factory):
    p = Project.create(tmp_path_factory.mktemp("s2d") / "p.sponge", "plane", crs="LOCAL")
    dem = planar(size_m=(40, 30), cell_size=1.0, slope_pct=2.0, aspect="south")
    dem.origin = (0.0, 30.0)
    write_geotiff(dem, p.path("terrain/existing.tif"))
    p.parameters.set("project.return_periods", [2], source=Source.USER)
    p.parameters.set("rainfall.storm_duration_hr", 3.0, source=Source.USER)
    delineate(p)
    dom = p.read_geojson("site/boundary.geojson")["features"][0]["geometry"]
    p.write_geojson("site/soil_zones.geojson", {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": dom, "properties": dict(
            id="Z", max_rate_mm_hr=10, min_rate_mm_hr=10, decay_1_hr=4, dry_time_days=7, suction_mm=100,
            ksat_mm_hr=10, imd=0.3, source="user")}]})
    subs = p.read_geojson("site/subcatchments.geojson")
    for f in subs["features"]:
        f["properties"].update(dstore_perv_mm=0.0, n_perv=0.03)
    p.write_geojson("site/subcatchments.geojson", subs)
    p.parameters.set("surface.n_perv", 0.03, source=Source.USER)
    pd.DataFrame({"return_period_yr": [2], "depth_mm": [60]}).to_csv(p.path("rainfall/return_periods.csv"), index=False)
    make_hyetographs(p)
    run_option(p, "baseline")
    yield p
    p.close()


def test_2d_volume_leaving_matches_swmm(plane_project):
    s = run2d(plane_project, "baseline", 2)
    tol = plane_project.parameters.value("sim2d.volume_tolerance_pct")
    assert abs(s["balance"]["continuity_error_pct"]) < 1
    assert abs(s["swmm_comparison"]["difference_pct_of_rainfall"]) < tol, s
    assert plane_project.exists("scenarios/baseline/sim2d/rp2.npz")
    assert s["label"].startswith("indicative")
