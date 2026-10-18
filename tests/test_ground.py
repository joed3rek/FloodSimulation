"""Ground questionnaire (TR-55 curve numbers) and the HSR rainfall preset."""

import pytest
from fastapi.testclient import TestClient

from spongepark.api.server import app
from spongepark.engine.site.ground import derive

from .test_design import site  # noqa: F401  (fixture)
from .test_intake import drawing  # noqa: F401  (fixture)

HSR_PDF_CN74 = {2: 40.48, 5: 62.28, 10: 77.62, 25: 97.76, 50: 113.12, 100: 128.62, 500: 165.27}


def test_well_kept_lawn_on_unknown_soil_is_cn_74_and_matches_the_hsr_runoff_table():
    rows = [{"return_period_yr": rp, "depth_mm": d} for rp, d in
            {2: 101.510, 5: 129.781, 10: 148.490, 25: 172.155, 50: 189.713, 100: 207.110, 500: 247.374}.items()]
    g = derive({"soil": "unknown", "covers": [{"cover": "grass", "condition": "good", "share_pct": 100}]}, rows)
    assert g["curve_number"] == 74 and g["hsg"] == "C" and g["soil_assumed"]
    assert "2-2a" in g["covers"][0]["citation"]
    for r in g["runoff_check"]:
        assert abs(r["runoff_mm"] - HSR_PDF_CN74[r["return_period_yr"]]) < 0.02, r


def test_mixed_covers_are_area_weighted():
    g = derive({"soil": "B", "covers": [{"cover": "grass", "condition": "fair", "share_pct": 60},
                                        {"cover": "woods", "condition": "good", "share_pct": 30},
                                        {"cover": "shrubs", "condition": "barren", "share_pct": 10}]})
    # TR-55 HSG B: open space fair 69, woods good 55, fallow bare soil 86
    assert g["curve_number"] == pytest.approx(0.6 * 69 + 0.3 * 55 + 0.1 * 86, abs=0.05)
    with pytest.raises(ValueError):
        derive({"soil": "B", "covers": []})


def test_questionnaire_and_rainfall_through_the_api_make_the_project_ready_to_run(site):  # noqa: F811
    c = TestClient(app)
    pid = c.post("/projects/open", json={"path": site}).json()["project"]
    assert c.get("/ground/questions").json()["soils"]
    assert "hsr_imd_24h" in c.get("/rainfall/presets").json()
    r = c.put(f"/projects/{pid}/rainfall", json={"preset": "hsr_imd_24h"}).json()
    assert r["return_periods"] == [2, 5, 10, 25, 50, 100] and r["missing"] == [1]
    assert all(s["depth_mm"] > 100 for s in r["storms"])
    g = c.put(f"/projects/{pid}/site/ground", json={"soil": "C", "paths": "paved",
              "covers": [{"cover": "grass", "condition": "good", "share_pct": 100}]}).json()
    assert g["curve_number"] == 74 and g["runoff_check"][3]["runoff_mm"] == pytest.approx(97.76, abs=0.02)
    info = c.get(f"/projects/{pid}").json()
    assert info["has_rainfall"] and info["has_soils"] and info["has_ground"]
    q = c.get(f"/projects/{pid}/parameters?prefix=swmm.infiltration_method").json()
    assert q[0]["value"] == "CURVE_NUMBER"
    c.post(f"/projects/{pid}/close")


def test_soil_group_gives_the_nbs_drain_out_rate_unless_a_test_is_given():
    from spongepark.engine.site.ground import infiltration_rate

    assert infiltration_rate("C", None)["ksat_mm_hr"] == 1.27 and infiltration_rate("C", None)["assumed"]
    assert infiltration_rate("C", 12.0) == {"ksat_mm_hr": 12.0, "source": "percolation test (designer)", "assumed": False}
    assert infiltration_rate("D", None)["ksat_mm_hr"] is None      # 0-1.27 mm/h: needs a percolation test
