"""Phase 7: the GPU kernel structure (float32, parallel kernels) gives the engine's 2D results."""

import numpy as np
import pytest

from spongepark.engine.sim2d.gpu_reference import simulate_gpu_reference
from spongepark.engine.sim2d.model import Elements2D, simulate
from spongepark.engine.terrain import bowl, v_valley


@pytest.mark.parametrize("case", ["valley", "bowl_with_element"])
def test_gpu_kernels_match_engine_model(case):
    if case == "valley":
        dem = v_valley(size_m=(30, 40), cell_size=1.0)
        els = None
    else:
        dem = bowl(size_m=(30, 30), cell_size=1.0, depth_m=0.8)
        lab = -np.ones(dem.z.shape, np.int64)
        lab[13:17, 13:17] = 0
        els = Elements2D(lab, ["E"], np.array([6.0]), np.array([5 / 1000 / 3600]), np.array([16.0]))
    mask = np.ones(dem.z.shape, bool)
    rain = np.r_[np.full(6, 20.0), np.full(6, 60.0), np.full(12, 5.0)]
    n = np.full(dem.z.shape, 0.04)
    f = np.full(dem.z.shape, 2.0)
    a = simulate(dem.z, mask, 1.0, rain, 300.0, 3 * 3600, n, f, els)
    b = simulate_gpu_reference(dem.z, mask, 1.0, rain, 300.0, 3 * 3600, n, f, els)
    rain_v = a.balance["rainfall_m3"]
    for k in ("outflow_m3", "infiltration_ground_m3", "infiltration_elements_m3", "surface_remaining_m3",
              "element_storage_remaining_m3"):
        assert b[k] == pytest.approx(a.balance[k], abs=0.002 * rain_v), k
    assert np.abs(b["hmax"] - a.max_depth).max() < 0.005
