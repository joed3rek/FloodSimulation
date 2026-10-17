"""Phase 1: rainfall tables and hyetographs."""

import numpy as np
import pandas as pd
import pytest

from spongepark.engine.rainfall import RainfallError, RainfallTable, alternating_block, from_user_csv, huff

T24 = RainfallTable.from_frame(pd.DataFrame({"return_period_yr": [1, 2, 5, 10, 25, 50, 100],
                                             "depth_mm": [60, 85, 110, 130, 155, 175, 195]}))


def test_24h_table_and_one_third_rule():
    assert T24.kind() == "24h_depth"
    assert T24.depth(10, 24) == pytest.approx(130)
    assert T24.depth(10, 3) == pytest.approx(130 * (3 / 24) ** (1 / 3))


def test_idf_table_interpolation_and_intensity_input():
    df = pd.DataFrame({"return_period_yr": [10, 10, 10], "duration_hr": [0.5, 1, 24],
                       "intensity_mm_hr": [100, 70, 5.5]})
    t = RainfallTable.from_frame(df)
    assert t.kind() == "idf"
    assert t.depth(10, 1) == pytest.approx(70)
    assert 50 < t.depth(10, 0.75) < 70


def test_rejects_decreasing_depths():
    with pytest.raises(RainfallError):
        RainfallTable.from_frame(pd.DataFrame({"return_period_yr": [1, 2], "depth_mm": [80, 60]}))


def test_alternating_block_conserves_depth_and_centres_peak():
    h = alternating_block(T24, 100, 24, 5, 0.5)
    assert h.depth_mm == pytest.approx(195, rel=1e-9)
    n = len(h.intensity_mm_hr)
    assert n == 288
    assert abs(int(np.argmax(h.intensity_mm_hr)) - round(0.5 * (n - 1))) <= 1
    # peak block equals the 5-minute depth
    assert h.intensity_mm_hr.max() * 5 / 60 == pytest.approx(T24.depth(100, 5 / 60))


def test_huff_conserves_depth():
    for q in (1, 2, 3, 4):
        h = huff(T24, 10, 6, 5, q)
        assert h.depth_mm == pytest.approx(T24.depth(10, 6))
        assert np.all(h.intensity_mm_hr >= 0)


def test_user_csv_resampled_and_scaled(tmp_path):
    f = tmp_path / "storm.csv"
    pd.DataFrame({"time_min": [0, 15, 30, 45], "depth_mm": [5, 20, 10, 5]}).to_csv(f, index=False)
    h = from_user_csv(f, rp=1, dt_min=5)
    assert h.depth_mm == pytest.approx(40)
    assert len(h.intensity_mm_hr) == 12
    h2 = from_user_csv(f, rp=1, dt_min=5, scale_to_depth_mm=80)
    assert h2.depth_mm == pytest.approx(80)
