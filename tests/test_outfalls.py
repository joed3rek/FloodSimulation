"""Where water leaves the park is the designer's answer (Site setup > Outfalls): an exit with no way out holds the
water against the edge up to the wall or kerb height, lets it soak in, and spills over the edge above that."""

import pytest

from spongepark.engine.pipeline import run_option
from spongepark.engine.site import outfalls

from .test_layout import _valley_project


@pytest.fixture(scope="module")
def valley(tmp_path_factory):
    p, base = _valley_project(tmp_path_factory.mktemp("outfalls"))
    yield p, base
    p.close()


def test_exits_wait_for_the_designer(valley):
    p, _ = valley
    st = outfalls.status(p)
    assert st["count"] >= 1 and not st["confirmed"] and st["closed"] == 0
    with pytest.raises(ValueError, match="height of the wall"):
        outfalls.apply(p, {"all": {"state": "closed"}})


def test_closed_exits_hold_water_at_the_edge(valley):
    p, _ = valley
    open_ = run_option(p, "baseline")["return_periods"]["5"]["water_balance"]
    st = outfalls.apply(p, {"all": {"state": "closed", "edge_height_m": 0.15}})
    assert st["confirmed"] and st["closed"] == st["count"]
    r = run_option(p, "baseline")["return_periods"]["5"]
    wb = r["water_balance"]
    edges = [e for e in r["elements"] if e["type"] == "edge_pond"]
    assert edges and max(e["max_depth_m"] for e in edges) <= 0.15 + 0.05
    assert wb["outflow_total_m3"] < open_["outflow_total_m3"]   # the edge holds part of what left before
    assert abs(wb["closure_error_pct"]) < 1


def test_one_exit_opened_again(valley):
    p, _ = valley
    first = outfalls.status(p)["exits"][0]
    st = outfalls.apply(p, {"exits": [{"id": first["id"], "state": "open"}]})
    row = next(e for e in st["exits"] if e["id"] == first["id"])
    assert row["state"] == "open" and st["closed"] == st["count"] - 1
