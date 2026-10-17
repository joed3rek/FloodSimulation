"""TR-55 functions checked against the manual's own worked examples, and SWMM's CURVE_NUMBER option."""

import pytest

from spongepark.engine.hydrology import tr55
from spongepark.engine.hydrology.wastewater import wastewater_m3_day
from spongepark.engine.project import Source

from .conftest import constant_storm, rect
from .test_swmm import run_storm

IN, FT = 25.4, 0.3048


def test_runoff_equation_matches_table_2_1_and_examples():
    # Example 2-1: CN 70, P = 6 in -> Q = 2.81 in; example 2-2: CN 75 -> 3.28 in.
    assert tr55.runoff_depth_mm(6 * IN, 70) / IN == pytest.approx(2.81, abs=0.01)
    assert tr55.runoff_depth_mm(6 * IN, 75) / IN == pytest.approx(3.28, abs=0.01)
    # Table 2-1 spot values.
    assert tr55.runoff_depth_mm(1.0 * IN, 98) / IN == pytest.approx(0.79, abs=0.01)
    assert tr55.runoff_depth_mm(3.0 * IN, 60) / IN == pytest.approx(0.33, abs=0.01)
    assert tr55.runoff_depth_mm(1.0 * IN, 60) == 0.0


def test_initial_abstraction_matches_table_4_1():
    for cn, ia_in in [(40, 3.000), (61, 1.279), (75, 0.667), (98, 0.041)]:
        assert 0.2 * tr55.retention_mm(cn) / IN == pytest.approx(ia_in, abs=0.001)


def test_weighted_and_composite_cn_match_worksheets():
    assert tr55.weighted_cn([(61, 30), (74, 70)]) == pytest.approx(70.1, abs=0.05)  # example 2-1
    assert round(tr55.composite_cn(61, 20)) == 68  # figure 2-3 text example
    assert round(tr55.composite_cn(61, 20, unconnected_ratio=0.75)) == 66  # figure 2-4 text example
    assert round(tr55.composite_cn(61, 35)) == 74 and round(tr55.composite_cn(74, 35)) == 82  # example 2-3
    assert round(tr55.composite_cn(74, 25, unconnected_ratio=0.5)) == 78  # example 2-4
    assert tr55.composite_cn(61, 40, unconnected_ratio=1.0) == tr55.composite_cn(61, 40)  # R ignored >= 30 %


def test_travel_time_matches_example_3_1():
    sheet = tr55.sheet_flow_tt_hr(0.24, 100 * FT, 3.6 * IN, 0.01)
    v_sc = tr55.shallow_velocity_m_s(0.01, paved=False)
    shallow = tr55.travel_time_hr(1400 * FT, v_sc)
    v_ch = tr55.channel_velocity_m_s(27 * FT ** 2, 28.2 * FT, 0.005, 0.05)
    channel = tr55.travel_time_hr(7300 * FT, v_ch)
    assert sheet == pytest.approx(0.30, abs=0.005)
    assert v_sc / FT == pytest.approx(1.6, abs=0.02) and shallow == pytest.approx(0.24, abs=0.005)
    assert v_ch / FT == pytest.approx(2.05, abs=0.01) and channel == pytest.approx(0.99, abs=0.005)
    assert sheet + shallow + channel == pytest.approx(1.53, abs=0.01)
    with pytest.raises(tr55.TR55Error):
        tr55.sheet_flow_tt_hr(0.24, 120, 90, 0.01)


def test_tables_and_soil_groups():
    assert tr55.curve_number("open_space_good", "B") == 61
    assert tr55.curve_number("brush_good", "A") == 30
    assert tr55.hsg_from_rate(20) == "A" and tr55.hsg_from_rate(5) == "B"
    assert tr55.hsg_from_rate(2) == "C" and tr55.hsg_from_rate(0.5) == "D"
    assert tr55.hsg_from_texture("Sandy clay loam") == "C"
    with pytest.raises(tr55.TR55Error):
        tr55.curve_number("open_space_good", "B/D")


def test_wastewater_estimate():
    assert wastewater_m3_day(1000) == pytest.approx(120.0)  # 1000 x 150 L x 0.8


@pytest.mark.parametrize("cn,p_mm", [(70, 150), (80, 75)])
def test_swmm_curve_number_matches_tr55_without_initial_abstraction(tmp_project, tmp_path, cn, p_mm):
    # SWMM's CN method has no 0.2S initial abstraction (depression storage plays that role), so with
    # zero depression storage it follows the TR-55 equation with Ia = 0.
    soil = dict(hsg="B", ksat_mm_hr=5, dry_time_days=7)
    p = tmp_project([(rect(0, 0, 50, 20), dict(id="S", outlet="OUT", pct_imperv=0, slope_pct=2, flow_length_m=20,
                                               curve_number=cn, dstore_perv_mm=0))], soil=soil, post_storm_hr=24)
    p.parameters.set("swmm.infiltration_method", "CURVE_NUMBER", source=Source.USER)
    _, _, wb = run_storm(p, "baseline", constant_storm(p_mm / 6, 6), tmp_path)
    q_mm = wb["outflow_total_m3"] / 1000 * 1000  # 1000 m2
    assert q_mm == pytest.approx(tr55.runoff_depth_mm(p_mm, cn, ia_ratio=0.0), rel=0.04)
    assert abs(wb["closure_error_pct"]) < 1


def test_cover_lookup_feeds_swmm(tmp_project, tmp_path):
    soil = dict(texture="loam", ksat_mm_hr=5, dry_time_days=7)  # loam -> HSG B; ksat is used for seepage only
    p = tmp_project([(rect(0, 0, 50, 20), dict(id="S", outlet="OUT", pct_imperv=20, slope_pct=2,
                                               tr55_cover="open_space_good"))], soil=soil)
    p.parameters.set("swmm.infiltration_method", "CURVE_NUMBER", source=Source.USER)
    spec, _, _ = run_storm(p, "baseline", constant_storm(20, 2), tmp_path)
    assert spec.subcatchments[0].curve_number == 61  # pervious CN only; SWMM handles the 20 % impervious
    text = (tmp_path / "baseline.inp").read_text()
    assert "INFILTRATION CURVE_NUMBER" in " ".join(text.split())
