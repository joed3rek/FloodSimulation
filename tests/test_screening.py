"""Volume screening reproduces the client's TR-55 sheet values and catches arithmetic slips."""

import pytest

from spongepark.engine.hydrology.screening import screen_park

PARK = {
    "id": "p", "name": "P", "park_area_m2": 2245, "catchment_area_m2": 11550,
    "catchment_parts": [{"area_m2": 11550, "cn": 94}],
    "client_runoff_m3": {"2": 974, "25": 1780},
    "interventions": [
        {"name": "planters", "qty": 19, "depth_m": 0.3, "area_m2": 11, "volume_m3": 62.7},
        {"name": "basin", "qty": 1, "depth_m": 1.2, "area_m2": 209, "volume_m3": 600},
    ],
    "client_totals": {"area_m2": 220},
}


def test_screen_matches_sheet_and_flags_errors():
    s = screen_park(PARK, {2: 101.510, 25: 172.155}, park_cn=74)
    assert s.runoff_m3["2"] == pytest.approx(974, abs=1)  # client sheet, CN 94
    assert s.runoff_m3["25"] == pytest.approx(1780, abs=1)
    assert s.park_runoff_m3["2"] == pytest.approx(91, abs=1)  # CN 74 on the park itself
    assert s.storage_m3 == pytest.approx(62.7 + 250.8)
    joined = " ".join(s.checks)
    assert "basin" in joined and "250.8" in joined  # 209 x 1.2 is not 600
    assert "footprint" in joined  # 19 planters counted once in the sheet's area total
    assert s.capture_pct["2"] == pytest.approx(100 * 313.5 / s.runoff_m3["2"])
    # the storm whose runoff just fills the storage
    from spongepark.engine.hydrology.tr55 import runoff_depth_mm
    assert runoff_depth_mm(s.fill_depth_mm, 94) * 11.55 == pytest.approx(s.storage_m3, rel=1e-6)
