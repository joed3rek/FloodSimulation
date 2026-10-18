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


def test_verified_results_are_stored_on_each_element(example):
    """Brief 8.3: every element carries its verified (SWMM) results per return period."""
    from spongepark.engine.project.jsonschema import validate_package

    p, *_ = example
    els = p.read_json("scenarios/manual/elements.json")["elements"]
    assert els
    for e in els:
        assert sorted(map(int, e["results"])) == [1, 2, 5, 10, 25, 50, 100], e["id"]
        assert "inflow_m3" in e["results"]["10"]
    assert {k: v for k, v in validate_package(p.root).items() if v} == {}


def test_overflow_timing_and_flooded_locations(example):
    _, _, opt, _ = example
    for rp, r in opt["return_periods"].items():
        t = r["timing"]
        assert t["first_outflow_hr"] is None or t["first_outflow_hr"] >= 0
        if t["uncontrolled_overflow_start_hr"] is not None and t["first_outflow_hr"] is not None:
            assert t["uncontrolled_overflow_start_hr"] >= t["first_outflow_hr"] - 1e-9, rp
        for e in r["elements"]:
            if (e.get("overflow_m3") or 0) > 1e-3:
                assert e["overflow_start_hr"] is not None and e["overflow_peak_cms"] > 0, (rp, e["id"])
        for f in r["flooded_locations"]:
            assert f["volume_m3"] > 0 and f["x"] is not None


def test_manual_elements_from_json_records(tmp_path):
    """Manual NbS from JSON: element records (brief 8.3) load through the CLI like GeoJSON does."""
    import json

    from typer.testing import CliRunner

    from spongepark.cli.main import app
    from spongepark.engine.nbs.components import load_elements

    from .sponge_case import ELEMENTS

    path = tmp_path / "m.sponge"
    Project.create(path, "manual").close()
    src = tmp_path / "elements.json"
    src.write_text(json.dumps({"schema_version": "1.1", "elements": ELEMENTS}), encoding="utf-8")
    r = CliRunner().invoke(app, ["option", "import", str(path), "designer", str(src)])
    assert r.exit_code == 0, r.output
    with Project.open(path) as p:
        els = {e.id: e for e in load_elements(p, "designer")}
        assert set(els) == {"RG1", "SW1", "DP1", "RW1"}
        assert els["DP1"].safety_bench_width_m == 1.5 and els["RG1"].outlet_diameter_m == 0.05
        assert els["RW1"].extra["record"]["future_field"] == {"kept": [1, 2, 3]}
