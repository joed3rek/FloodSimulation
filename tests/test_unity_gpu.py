"""Phase 7: the Unity GPU water simulation (WaterSim.compute) against the engine, on a real GPU.

Runs only when SPONGEPARK_TEST_UNITY=1 (it starts the Unity editor in batch mode, which takes a few
minutes). The editor is taken from SPONGEPARK_UNITY_EDITOR or the default Unity Hub folder.
"""

import base64
import glob
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from .unity_case import build

ROOT = Path(__file__).resolve().parents[1]


def _editor():
    e = os.environ.get("SPONGEPARK_UNITY_EDITOR")
    if e:
        return e
    found = sorted(glob.glob(r"C:\Program Files\Unity\Hub\Editor\*\Editor\Unity.exe"))
    return found[0] if found else None


@pytest.mark.skipif(os.environ.get("SPONGEPARK_TEST_UNITY") != "1", reason="set SPONGEPARK_TEST_UNITY=1 to run")
def test_gpu_matches_engine(tmp_path):
    editor = _editor()
    assert editor, "Unity editor not found"
    build(tmp_path)
    subprocess.run([editor, "-batchmode", "-projectPath", str(ROOT / "unity" / "SpongeParkApp"),
                    "-executeMethod", "SpongePark.EditorTools.BatchVerify.Run", "-inputs", str(tmp_path / "inputs.json"),
                    "-out", str(tmp_path / "gpu.json"), "-logFile", str(tmp_path / "unity.log")], check=False, timeout=1800)
    g = json.loads((tmp_path / "gpu.json").read_text())
    assert g["ok"], g.get("error")
    e = json.loads((tmp_path / "engine.json").read_text())
    rain = e["balance"]["rainfall_m3"]
    for k, v in g["balance"].items():
        assert abs(v - e["balance"][k]) <= 0.01 * rain, k   # within 1 % of rainfall
    de = np.frombuffer(base64.b64decode(e["depth"]), "<f4")
    dg = np.frombuffer(base64.b64decode(g["depth"]), "<f4")
    assert np.abs(de - dg).max() < 0.01
