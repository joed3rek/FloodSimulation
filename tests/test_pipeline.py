"""Phase 1 acceptance: all seven return periods on the synthetic site, continuity < 1 %."""

import pytest

from spongepark.engine.pipeline import compare, make_hyetographs, run_option
from spongepark.engine.project import Project
from spongepark.examples.synthetic_park import populate
from spongepark.engine.nbs.components import elements_fc


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    p = Project.create(tmp_path_factory.mktemp("ex") / "ex.sponge", "example")
    populate(p)
    make_hyetographs(p)
    base = run_option(p, "baseline")
    opt = run_option(p, "manual")
    cmp_ = compare(p, "manual")
    yield p, base, opt, cmp_
    p.close()


def test_all_seven_return_periods_run(example):
    _, base, opt, _ = example
    assert sorted(map(int, opt["return_periods"])) == [1, 2, 5, 10, 25, 50, 100]
    assert sorted(map(int, base["return_periods"])) == [1, 2, 5, 10, 25, 50, 100]


def test_continuity_below_one_percent(example):
    _, base, opt, _ = example
    for summ in (base, opt):
        for rp, v in summ["return_periods"].items():
            wb = v["water_balance"]
            assert abs(wb["swmm_runoff_continuity_pct"]) < 1, rp
            assert abs(wb["swmm_routing_continuity_pct"]) < 1, rp
            assert abs(wb["closure_error_pct"]) < 1, rp
            assert not v["flags"]


def test_nbs_reduce_outflow_and_peak(example):
    _, _, _, c = example
    for r in c["rows"]:
        assert r["option_outflow_m3"] < r["baseline_outflow_m3"]
        assert r["peak_reduction_pct"] > 0


def test_outputs_written(example):
    p, *_ = example
    for rel in ("scenarios/manual/model.inp", "scenarios/manual/swmm/rp100.inp", "scenarios/manual/results/summary.json",
                "scenarios/manual/results/rp10_timeseries.parquet", "scenarios/manual/guideline_findings.json",
                "rainfall/hyetographs/rp100.csv"):
        assert p.exists(rel), rel


def test_site_area_reconciles(example):
    p, _, opt, _ = example
    from spongepark.engine.nbs import read_elements
    from spongepark.engine.site import Site
    from spongepark.engine.swmm import build_spec

    site = Site.load(p)
    els = read_elements(elements_fc(p, "manual"))
    spec = build_spec(site, els, p.parameters, "manual")
    assert spec.area_m2(("site", "lid", "direct")) == pytest.approx(site.site_area_m2, rel=1e-3)
