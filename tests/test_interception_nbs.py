"""Phase 1: canopy interception, NbS geometry and guideline checks."""

import numpy as np
import pytest

from spongepark.engine.interception import CanopyCover, intercept, net_rainfall
from spongepark.engine.nbs import NbSElement, catalogue, check_element, resolve_element, rules
from spongepark.engine.project import default_parameters

from .conftest import rect


def test_bucket_fills_first():
    got = intercept(np.array([0.4, 0.4, 0.4, 0.4]), 1.0)
    assert np.allclose(got, [0.4, 0.4, 0.2, 0.0])


def test_net_rainfall_partial_cover():
    depths = np.array([2.0, 2.0])
    net = net_rainfall(depths, CanopyCover(fraction=0.5, capacity_mm=1.0, canopy_area_m2=0))
    assert net.sum() == pytest.approx(4.0 - 0.5 * 1.0)


def test_catalogue_includes_guideline_components():
    cat = catalogue()
    for t in ("rain_garden", "bioswale", "detention_pond", "retention_pond", "recharge_well",
              "constructed_wetland", "edge_engineering", "inline_check_dam"):
        assert t in cat
    assert cat["constructed_wetland"].chapter == "4.10"
    assert cat["edge_engineering"].swmm == "lid_swale"


def test_every_rule_cites_a_source():
    for r in rules():
        assert r.source.startswith("HC-") and r.section and (r.min is not None or r.max is not None)
        for t in r.applies_to:
            assert t in catalogue() or t == "check_dam"


def _resolve(el):
    return resolve_element(el, default_parameters(), lambda g: ("Z", 20.0))


def test_vertical_sided_pond_volume_is_area_times_depth():
    el = _resolve(NbSElement(id="P", type="detention_pond", geometry=rect(0, 0, 20, 10), invert_elev_m=100,
                             side_slope_h_v=0.0, max_ponding_depth_m=0.5))
    assert el.area_m2 == pytest.approx(200)
    assert el.storage_volume_m3 == pytest.approx(100, rel=1e-3)
    assert el.seepage_rate_mm_hr == pytest.approx(20.0)


def test_sloped_pond_volume_matches_prismoid():
    # 20 x 10 top, 0.5 m deep, 4:1 sides -> bottom 16 x 6
    el = _resolve(NbSElement(id="P", type="detention_pond", geometry=rect(0, 0, 20, 10), invert_elev_m=100,
                             side_slope_h_v=4.0, max_ponding_depth_m=0.5))
    a1, a2, am = 200.0, 96.0, 18 * 8
    prismoid = 0.5 / 6 * (a1 + a2 + 4 * am)
    assert el.storage_volume_m3 == pytest.approx(prismoid, rel=0.01)


def test_recharge_well_needs_strata_rate():
    with pytest.raises(ValueError):
        _resolve(NbSElement(id="W", type="recharge_well", geometry={"type": "Point", "coordinates": (0, 0)},
                            invert_elev_m=95))


def test_swale_centreline_footprint():
    el = _resolve(NbSElement(id="S", type="bioswale",
                             geometry={"type": "LineString", "coordinates": [(0, 0), (0, 40)]}, top_width_m=3))
    assert el.area_m2 == pytest.approx(120)


def test_guideline_findings():
    el = _resolve(NbSElement(id="P", type="detention_pond", geometry=rect(0, 0, 20, 10), invert_elev_m=100,
                             outlet_diameter_m=0.05, side_slope_h_v=2.0))
    ids = {f.rule_id: f for f in check_element(el)}
    assert ids["inline.orifice_min"].severity == "error"
    assert "4.12" in ids["inline.orifice_min"].citation
    assert "edge.side_slope" in ids
    ok = _resolve(NbSElement(id="P2", type="detention_pond", geometry=rect(0, 0, 20, 10), invert_elev_m=100))
    assert not [f for f in check_element(ok) if f.severity == "error"]
