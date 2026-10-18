"""Phase 4: generated layout on a synthetic valley, from suitability to the SWMM run of the option."""

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box, shape

from spongepark.engine.grading.grade import grade
from spongepark.engine.hydrology.delineate import delineate
from spongepark.engine.layout.generate import generate
from spongepark.engine.pipeline import compare, make_hyetographs, run_option
from spongepark.engine.project import Project, Source
from spongepark.engine.site import Site
from spongepark.engine.terrain import read_geotiff, v_valley, write_geotiff
from spongepark.engine.nbs.components import elements_fc

BUILDING = box(2, 50, 12, 60)  # south-west hillside (valley runs north-south through x = 30)


def _fc(items):
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": g.__geo_interface__, "properties": p} for g, p in items]}


def _valley_project(root):
    p = Project.create(root / "v.sponge", "valley", crs="LOCAL")
    dem = v_valley(size_m=(60, 80), cell_size=1.0)
    dem.origin = (0.0, 80.0)  # put the site at (0, 0)-(60, 80)
    write_geotiff(dem, p.path("terrain/existing.tif"))
    P = p.parameters
    P.set("project.return_periods", [2, 5], source=Source.USER)
    P.set("layout.design_return_period_yr", 5, source=Source.USER)
    p.write_geojson("site/context.geojson", _fc([(BUILDING, {"kind": "buildings", "layer": "B"})]))
    delineate(p)
    dom = p.read_geojson("site/boundary.geojson")["features"][0]["geometry"]
    p.write_geojson("site/soil_zones.geojson", {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": dom, "properties": dict(
            id="Z", max_rate_mm_hr=40, min_rate_mm_hr=8, decay_1_hr=4, dry_time_days=7, suction_mm=170,
            ksat_mm_hr=8, imd=0.25, source="user")}]})
    pd.DataFrame({"return_period_yr": [2, 5], "depth_mm": [85, 110]}).to_csv(
        p.path("rainfall/return_periods.csv"), index=False)
    make_hyetographs(p)
    base = run_option(p, "baseline")
    return p, base


@pytest.fixture(scope="module")
def valley(tmp_path_factory):
    p, base = _valley_project(tmp_path_factory.mktemp("lay"))
    rep = generate(p, "auto")
    opt = run_option(p, "auto")
    cmp_ = compare(p, "auto")
    yield p, base, rep, opt, cmp_
    p.close()


def test_grading_cuts_to_depth_below_rim():
    z = np.full((20, 20), 10.0)
    z[:, 0] = 9.9  # the lowest ground next to the footprint sets the rim
    region = np.zeros_like(z, bool)
    region[5:15, 5:15] = True
    mask = np.ones_like(region)
    zg, cut = grade(z, region, mask, 1.0, 0.3, None)
    assert cut.rim_m == pytest.approx(10.0) and cut.bottom_m == pytest.approx(9.7)
    assert np.allclose(zg[region], 9.7) and np.allclose(zg[~region], z[~region])
    assert cut.cut_m3 == pytest.approx(100 * 0.3) and cut.storage_m3 == pytest.approx(30)
    _, sloped = grade(z, region, mask, 1.0, 0.6, 4.0)
    assert sloped.storage_m3 < 100 * 0.6  # banks at 4:1 take volume


def test_elements_placed_in_the_valley_and_away_from_the_building(valley):
    p, _, rep, _, _ = valley
    types = {e["type"] for e in rep["elements"]}
    assert "detention_pond" in types
    pond = next(e for e in rep["elements"] if e["type"] == "detention_pond")
    by_id = {e["id"]: e for e in rep["elements"]}

    def ends_in(e, target):
        seen = set()
        while e["id"] not in seen:
            seen.add(e["id"])
            if e["id"] == target:
                return True
            if e["outflow_to"] not in by_id:
                return False
            e = by_id[e["outflow_to"]]
        return False

    into_pond = sum(e["drains_here_after_grading_m2"] for e in rep["elements"] if ends_in(e, pond["id"]))
    assert into_pond > 0.9 * rep["site_area_m2"]  # the valley floor and its swales feed the pond
    assert pond["holds_m3_estimate"] >= 0.98 * pond["target_m3"] and pond["limited_by"] == "design storm"
    comps = elements_fc(p, "auto")["features"]
    setback = p.parameters.value("layout.building_setback_m")
    for f in comps:
        g = shape(f["geometry"])
        assert g.distance(BUILDING) >= setback - 1.0  # one cell of rasterisation tolerance
        if f["properties"]["type"] == "detention_pond":
            cx = g.centroid.x
            assert abs(cx - 30) < 10  # on the valley line
    assert rep["generated_area_m2"] <= rep["area_budget_m2"] + 1e-6


def test_graded_surface_only_cuts(valley):
    p, *_ = valley
    z0 = read_geotiff(p.path("terrain/existing.tif")).z
    zg = read_geotiff(p.path("scenarios/auto/terrain/graded.tif")).z
    m = zg != -9999
    assert (zg[m] <= z0[m] + 1e-4).all() and (zg[m] < z0[m] - 0.05).any()


def test_rebuilt_subcatchments_tile_the_site_and_feed_elements(valley):
    p, _, rep, _, _ = valley
    site = Site.load(p, "auto")
    assert sum(s.shape().area for s in site.subcatchments) == pytest.approx(site.boundary.area, rel=1e-3)
    comps = elements_fc(p, "auto")["features"]
    for f in comps:
        assert f["properties"]["inflow_from"] == [f"SC_{f['properties']['id']}"]
    # the baseline still uses the delineated subcatchments
    assert {s.id for s in Site.load(p).subcatchments} != {s.id for s in site.subcatchments}


def test_option_runs_closes_mass_balance_and_beats_baseline(valley):
    _, _, _, opt, cmp_ = valley
    for rp, v in opt["return_periods"].items():
        wb = v["water_balance"]
        assert abs(wb["closure_error_pct"]) < 1 and abs(wb["swmm_routing_continuity_pct"]) < 1, rp
    for r in cmp_["rows"]:
        assert r["option_outflow_m3"] < r["baseline_outflow_m3"]
        assert r["peak_reduction_pct"] > 0


def test_design_drawing_and_contours(valley):
    p, *_ = valley
    import ezdxf

    doc = ezdxf.readfile(p.path("scenarios/auto/design.dxf"))
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert {"SP-DSN-CONTOUR", "SP-DSN-POND", "SP-DSN-LABEL", "SP-SITE-BOUNDARY"} <= layers
    assert p.read_geojson("scenarios/auto/design_contours.geojson")["features"]


def test_swale_follows_the_valley_line_and_feeds_the_pond(tmp_path):
    p, _ = _valley_project(tmp_path)
    with p:
        rep = generate(p, "train", ["detention_pond", "bioswale"],
                       overrides={"nbs.bioswale.min_longitudinal_slope_pct": 0.5})
        sw = [e for e in rep["elements"] if e["type"] == "bioswale"]
        assert sw, rep["skipped"]
        comps = {f["properties"]["id"]: f for f in elements_fc(p, "train")["features"]}
        line = shape(comps[sw[0]["id"]]["geometry"])
        assert line.geom_type == "LineString" and abs(line.centroid.x - 30) < 3  # on the valley line
        last = sw[-1]
        assert last["outflow_to"].startswith(("DP_", "OUT")), last  # the train ends in the pond or an outfall
        assert all(e["outflow_to"].startswith(("BS_", "DP_", "OUT")) for e in sw)
        assert 0.5 <= comps[sw[0]["id"]]["properties"]["longitudinal_slope_pct"] <= 4
        # the override was not stored in the project
        assert p.parameters.value("nbs.bioswale.min_longitudinal_slope_pct") == 1.0
        run_option(p, "train")  # SWMM accepts the treatment train


def test_recharge_wells_need_site_data_then_take_pond_overflow(tmp_path):
    p, _ = _valley_project(tmp_path)
    with p:
        rep = generate(p, "wells", ["detention_pond", "recharge_well"])
        assert not any(e["type"] == "recharge_well" for e in rep["elements"])
        assert any("site.recharge_strata_rate_mm_hr" in s for s in rep["skipped"])
        p.parameters.set("site.recharge_strata_rate_mm_hr", 30.0, "mm/hr", Source.SITE_MEASURED, note="test borehole")
        p.parameters.set("site.rock_depth_m", 12.0, "m", Source.SITE_MEASURED, note="test borehole")
        rep = generate(p, "wells", ["detention_pond", "recharge_well"])
        well = next(e for e in rep["elements"] if e["type"] == "recharge_well")
        pond = next(e for e in rep["elements"] if e["type"] == "detention_pond")
        comps = {f["properties"]["id"]: f["properties"] for f in elements_fc(p, "wells")["features"]}
        assert comps[pond["id"]]["overflow_to"] == well["id"]
        assert comps[well["id"]]["overflow_to"].startswith("OUT")
        res = run_option(p, "wells")
        assert abs(res["return_periods"]["5"]["water_balance"]["closure_error_pct"]) < 1


def test_rain_gardens_rejected_when_they_drain_too_slowly(tmp_path):
    from spongepark.engine.layout.generate import LayoutError

    p, _ = _valley_project(tmp_path)
    with p:
        # 0.2 m ponding at 8 mm/h takes 25 h, more than the 10 h allowed here
        with pytest.raises(LayoutError, match="drawdown 25 h"):
            generate(p, "slow", ["rain_garden"], overrides={"nbs.max_drawdown_hr": 10.0})
