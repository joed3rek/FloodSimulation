"""Phase 8: calibration recovers known factors from a synthetic 'observed' event."""

import pandas as pd
import pytest

from spongepark.engine.project import Source
from spongepark.engine.swmm.calibrate import _simulate, calibrate
from spongepark.engine.rainfall.hyetograph import from_user_csv

from .test_layout import _valley_project


def test_calibration_recovers_known_infiltration_factor(tmp_path):
    p, _ = _valley_project(tmp_path)
    with p:
        # a 2-hour recorded storm
        rain = pd.DataFrame({"time_min": [0, 15, 30, 45, 60, 75, 90, 105], "intensity_mm_hr": [5, 20, 45, 30, 15, 8, 4, 0]})
        rain.to_csv(tmp_path / "event.csv", index=False)
        storm = from_user_csv(tmp_path / "event.csv", 0, 5)
        truth = {"infiltration": 0.5, "roughness": 1.0, "depression_storage": 1.0, "imperviousness": 1.0}
        obs = _simulate(p, "baseline", storm, truth, "outflow_total_cms", tmp_path)
        obs = obs.iloc[::10].rename(columns={"outflow_total_cms": "value"})
        obs.to_csv(tmp_path / "observed.csv", index=False)
        assert p.manifest.calibration_status == "uncalibrated"
        rep = calibrate(p, "baseline", tmp_path / "event.csv", tmp_path / "observed.csv", "outflow_total_cms",
                        max_evaluations=60)
        assert rep["nse_uncalibrated"] < rep["nse_calibrated"] and rep["nse_calibrated"] > 0.95
        assert rep["factors"]["infiltration"] == pytest.approx(0.5, rel=0.25)
        assert rep["accepted"] and p.manifest.calibration_status.startswith("calibrated")
        q = p.parameters.get("calibration.infiltration_factor")
        assert q.source == Source.SITE_MEASURED and q.confirmed
        assert p.exists("calibration/calibration.png")


def test_poor_fit_leaves_model_uncalibrated(tmp_path):
    p, _ = _valley_project(tmp_path)
    with p:
        pd.DataFrame({"time_min": [0, 30, 60], "intensity_mm_hr": [10, 10, 0]}).to_csv(tmp_path / "e.csv", index=False)
        # observations unrelated to rainfall: a flow that rises when it stops raining
        pd.DataFrame({"time_hr": [0, 0.5, 1, 1.5, 2, 3], "value": [0.05, 0.0, 0.0, 0.08, 0.1, 0.0]}).to_csv(
            tmp_path / "o.csv", index=False)
        rep = calibrate(p, "baseline", tmp_path / "e.csv", tmp_path / "o.csv", "outflow_total_cms", max_evaluations=20)
        assert not rep["accepted"] and p.manifest.calibration_status == "uncalibrated"
        assert p.parameters.value("calibration.infiltration_factor") == 1.0
