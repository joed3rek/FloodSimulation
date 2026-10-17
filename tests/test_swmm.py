"""Phase 1: SWMM builder verified analytically and against a hand-built model."""

import shutil
from pathlib import Path

import pytest

from spongepark.engine.metrics import water_balance
from spongepark.engine.pipeline import prepare_option
from spongepark.engine.site import Site
from spongepark.engine.swmm import build_spec, render_inp, run

from .conftest import constant_storm, rect

FIXTURES = Path(__file__).parent / "fixtures"


def run_storm(project, option_id, storm, tmp_path):
    site = Site.load(project)
    els, findings = prepare_option(project, option_id, site) if option_id != "baseline" else ([], [])
    spec = build_spec(site, els, project.parameters, option_id)
    inp = tmp_path / f"{option_id}.inp"
    inp.write_text(render_inp(spec, site, project.parameters, {storm.return_period_yr: storm}, storm.return_period_yr))
    res = run(spec, inp, 60)
    return spec, res, water_balance(spec, res, storm.depth_mm)


def test_impervious_plane_runoff_equals_rainfall(tmp_project, tmp_path):
    p = tmp_project([(rect(0, 0, 50, 20), dict(id="S", outlet="OUT", pct_imperv=100, slope_pct=2, flow_length_m=20,
                                               dstore_imperv_mm=0, pct_zero_imperv=100))])
    _, res, wb = run_storm(p, "baseline", constant_storm(30, 1), tmp_path)
    assert wb["rainfall_total_m3"] == pytest.approx(30.0)
    assert wb["outflow_total_m3"] == pytest.approx(30.0, rel=0.005)
    assert abs(wb["swmm_runoff_continuity_pct"]) < 1 and abs(wb["swmm_routing_continuity_pct"]) < 1
    assert abs(wb["closure_error_pct"]) < 1


def test_pervious_surface_with_high_infiltration_gives_no_runoff(tmp_project, tmp_path):
    soil = dict(max_rate_mm_hr=100, min_rate_mm_hr=100, decay_1_hr=4, dry_time_days=7, max_volume_mm=0)
    p = tmp_project([(rect(0, 0, 50, 20), dict(id="S", outlet="OUT", pct_imperv=0, slope_pct=2, flow_length_m=20))],
                    soil=soil)
    _, res, wb = run_storm(p, "baseline", constant_storm(20, 1), tmp_path)
    assert wb["outflow_total_m3"] == pytest.approx(0.0, abs=1e-3)
    assert wb["infiltration_surfaces_m3"] == pytest.approx(20.0, rel=0.01)


def test_pond_seepage_matches_ksat_times_area(tmp_project, tmp_path):
    # Rain falls only on a 100 m2 vertical-sided dry pond: 50 mm -> 5 m3, seeping at 10 mm/h over 100 m2.
    sub = [(rect(0, 0, 1, 1), dict(id="TINY", outlet="OUT", pct_imperv=0, slope_pct=1))]
    pond = [(rect(10, 0, 20, 10), dict(id="P", type="detention_pond", invert_elev_m=100, side_slope_h_v=0,
                                       max_ponding_depth_m=0.5, overflow_to="OUT"))]
    p = tmp_project(sub, pond, post_storm_hr=12)
    _, res, wb = run_storm(p, "opt", constant_storm(50, 1), tmp_path)
    assert wb["infiltration_storage_beds_m3"] == pytest.approx(5.0, rel=0.02)
    assert wb["outflow_total_m3"] < 0.05  # only the 1 m2 placeholder subcatchment can produce runoff
    assert abs(wb["closure_error_pct"]) < 1


def _hand_equivalent(tmp_project):
    sub = [(rect(0, 0, 50, 20), dict(id="SC1", outlet="OUT", pct_imperv=100, slope_pct=1, flow_length_m=20,
                                     dstore_imperv_mm=1.5, dstore_perv_mm=5, pct_zero_imperv=25))]
    els = [
        (rect(50, 0, 55, 10), dict(id="RG1", type="rain_garden", inflow_from=["SC1"], outflow_to="DP")),
        (rect(60, 0, 70, 10), dict(id="DP", type="detention_pond", invert_elev_m=100, side_slope_h_v=0,
                                   max_ponding_depth_m=0.5, outlet_diameter_m=0.05, weir_length_m=2.0,
                                   outflow_to="OUT", overflow_to="OUT")),
    ]
    p = tmp_project(sub, els, boundary=rect(0, 0, 50, 20), outfall_elev=99.0, post_storm_hr=6)
    p.parameters.set("guidelines.enforce_errors", False)  # 50 mm orifice is below the 75 mm guideline on purpose
    return p


def test_builder_matches_hand_built_model(tmp_project, tmp_path):
    from pyswmm import Nodes, Simulation, SystemStats

    hand = tmp_path / "hand.inp"
    shutil.copy(FIXTURES / "hand_built_simple.inp", hand)
    with Simulation(str(hand)) as sim:
        nodes = Nodes(sim)
        for _ in sim:
            pass
        h_out_ctrl = nodes["OUTA"].cumulative_inflow
        h_out_ovf = nodes["OUTB"].cumulative_inflow
        h_runoff = dict(SystemStats(sim).runoff_stats)
        h_routing = dict(SystemStats(sim).routing_stats)
        h_pond_max = nodes["POND"].statistics["max_depth"]
    h_area = 1150.0
    p = _hand_equivalent(tmp_project)
    spec, res, wb = run_storm(p, "opt", constant_storm(60, 1), tmp_path)
    assert wb["rainfall_total_m3"] == pytest.approx(h_runoff["rainfall"] * h_area / 1000, rel=1e-6)
    assert wb["outflow_controlled_m3"] == pytest.approx(h_out_ctrl, rel=0.01)
    assert wb["outflow_overflow_m3"] == pytest.approx(h_out_ovf, rel=0.01, abs=0.05)
    assert wb["infiltration_lid_m3"] + wb["infiltration_surfaces_m3"] == pytest.approx(
        h_runoff["infiltration"] * h_area / 1000, rel=0.01)
    assert wb["infiltration_storage_beds_m3"] == pytest.approx(h_routing["seepage_loss"], rel=0.01)
    assert res.storage["DP"]["max_depth"] == pytest.approx(h_pond_max, rel=0.01)
    assert abs(wb["closure_error_pct"]) < 1
