"""Itzi as the 2D flood model (runs only where Itzi is set up: `spongepark itzi setup`)."""

import numpy as np
import pytest

from spongepark.engine.sim2d.itzi_model import available, simulate_itzi
from spongepark.engine.sim2d.model import simulate

pytestmark = pytest.mark.skipif(not available(), reason="Itzi is not set up on this machine")


def test_itzi_agrees_with_the_built_in_model_on_a_hollow():
    """A tilted plane with a hollow, steady rain, constant infiltration: same physics, same answer."""
    rows, cols, cell = 40, 60, 1.0
    y, x = np.mgrid[0:rows, 0:cols] * cell
    z = 100 + 0.01 * x - 0.4 * np.exp(-((x - 20) ** 2 + (y - 20) ** 2) / 30)
    park = np.zeros(z.shape, bool)
    park[2:-2, 2:-2] = True
    rain = np.r_[np.full(6, 40.0), np.zeros(6)]          # 40 mm/h for 30 min, then dry
    n, f = np.full(z.shape, 0.05), np.full(z.shape, 5.0)
    b = simulate(z, park, cell, rain, 300, 3600, n, np.where(park, f, 0), None, frame_every_s=300)
    i = simulate_itzi(z, park, cell, rain, 300, 3600, n, f, frame_every_s=300)
    assert abs(i.balance["rainfall_m3"] - b.balance["rainfall_m3"]) < 1e-6
    assert abs(i.balance["infiltration_ground_m3"] - b.balance["infiltration_ground_m3"]) < 0.05 * b.balance["rainfall_m3"]
    hb, hi = b.max_depth[park].max(), i.max_depth[park].max()
    assert hi > 0.05 and abs(hi - hb) < 0.25 * hb                 # the hollow fills to about the same depth
    assert np.unravel_index(np.argmax(i.max_depth), z.shape) == np.unravel_index(np.argmax(b.max_depth), z.shape)
    assert i.frames.shape[0] >= 12 and "qx_mean" in i.extra
