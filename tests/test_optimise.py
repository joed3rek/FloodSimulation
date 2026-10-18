"""Phase 5: optimisation over generated layouts, surrogate accuracy gate, SWMM verification."""

import numpy as np
import pytest

from spongepark.engine.ml.surrogate import Surrogate
from spongepark.engine.optimise.evaluate import evaluate, objectives
from spongepark.engine.optimise.run import optimise, performance_curve, representatives
from spongepark.engine.optimise.space import Space

from .test_layout import _valley_project
from spongepark.engine.nbs.components import has_elements


@pytest.fixture(scope="module")
def valley(tmp_path_factory):
    p, _ = _valley_project(tmp_path_factory.mktemp("opt"))
    p.parameters.set("layout.types", ["detention_pond", "bioswale"])
    p.parameters.set("nbs.bioswale.min_longitudinal_slope_pct", 0.5)
    yield p
    p.close()


def test_space_decodes_to_generator_settings(valley):
    sp = Space.from_project(valley)
    lo, hi = sp.bounds()
    types, ov = sp.decode(hi)
    assert types == ["detention_pond", "bioswale"]
    assert ov["layout.max_area_pct"] == pytest.approx(valley.parameters.value("layout.max_area_pct"))
    assert ov["layout.design_return_period_yr"] == 5 and ov["nbs.detention_pond.max_ponding_depth_m"] == 1.0
    assert "nbs.rain_garden.max_ponding_depth_m" not in ov  # type not in layout.types
    assert sp.decode(lo)[0] == []


def test_evaluation_is_swmm_and_cleans_up(valley):
    sp = Space.from_project(valley)
    lo, hi = sp.bounds()
    r = evaluate(valley, sp, (lo + hi) / 2 + 0.3 * (hi - lo))
    assert r["feasible"] and r["swmm_verified"] and set(r["per_rp"]) == {"2", "5"}
    assert 0 < r["area_pct"] <= valley.parameters.value("layout.max_area_pct") + 1e-6
    assert not has_elements(valley, "_eval")
    f, g = objectives(r, "forward", {}, None, 48, 0.01)
    assert f[0] < 0 and 0 < f[1] <= 1.2


def test_surrogate_refused_below_accuracy_threshold():
    rng = np.random.default_rng(0)
    rows = []
    for _ in range(24):  # pure noise: nothing to learn
        rows.append({"x": list(rng.random(3)), "feasible": True, "area_pct": rng.random(), "cut_m3": rng.random(),
                     "max_drawdown_hr": rng.random(), "per_rp": {"2": {"rainfall_mm": 85, "retained_pct": rng.random() * 100,
                                                                       "peak_ratio": rng.random()}}})
    s = Surrogate.train(rows, lambda x: x, 0, 0.25, 0.8)
    assert s is not None and not s.usable


def test_surrogate_learns_a_smooth_response():
    rng = np.random.default_rng(1)
    rows = []
    for _ in range(80):
        x = rng.random(3)
        rows.append({"x": list(x), "feasible": True, "area_pct": 10 * x[0], "cut_m3": 50 * x[0] + 20 * x[1],
                     "max_drawdown_hr": 5 + 10 * x[2],
                     "per_rp": {rp: {"rainfall_mm": d, "retained_pct": 40 + 50 * x[0] - 0.1 * d,
                                     "peak_ratio": 1 - 0.6 * x[0]} for rp, d in (("2", 85), ("5", 110))}})
    s = Surrogate.train(rows, lambda x: x, 0, 0.25, 0.8)
    assert s.usable, s.scores


def test_representatives_include_the_extremes():
    F = np.array([[0, 5], [1, 3], [2, 2], [5, 0]], float)
    r = representatives(F, 3)
    assert r[:2] == [0, 3] and len(r) == 3


def test_forward_optimisation_produces_swmm_verified_options(valley):
    rep = optimise(valley, "forward", n_initial=8, rounds=1, per_round=2, pop_size=12, n_gen=6, n_final=3)
    assert rep["pareto_size"] >= 1 and 1 <= len(rep["options"]) <= 3
    for o in rep["options"]:
        assert o["swmm_verified"]
        assert valley.exists(f"scenarios/{o['option_id']}/results/summary.json")
        assert o["area_pct"] <= valley.parameters.value("layout.max_area_pct") + 1e-6
    assert valley.exists("optimise/forward_pareto.png") and valley.exists("optimise/dataset.json")
    assert rep["evaluations_swmm"] >= 8


def test_performance_curve_grows_with_budget(valley):
    out = performance_curve(valley, [2, 10])
    small, big = out["rows"]
    assert big["retained_pct"]["5"] >= small["retained_pct"]["5"] - 0.5
    assert valley.exists("optimise/performance_curve.png")
