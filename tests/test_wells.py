"""Existing recharge wells on the survey count in the existing site and in every design, once the designer has
given their depth, diameter and the strata's infiltration rate (nothing is assumed). Each well gets the
catchment that drains into it, takes water in SWMM, and a design gets no credit for it."""

import numpy as np
import pytest
from shapely.geometry import shape

from spongepark.engine.pipeline import prepare_option, run_option
from spongepark.engine.site import wells
from spongepark.engine.terrain.raster import read_geotiff

from .test_layout import _valley_project


def _ground(p):
    dem = read_geotiff(p.path("terrain/existing.tif"))

    def at(x, y):
        c = np.clip(((np.asarray(x) - dem.origin[0]) / dem.cell_size).astype(int), 0, dem.z.shape[1] - 1)
        r = np.clip(((dem.origin[1] - np.asarray(y)) / dem.cell_size).astype(int), 0, dem.z.shape[0] - 1)
        return dem.z[r, c]
    return at


@pytest.fixture(scope="module")
def valley_wells(tmp_path_factory):
    p, base = _valley_project(tmp_path_factory.mktemp("wells"))
    park = shape(p.read_geojson("site/boundary.geojson")["features"][0]["geometry"])
    # two wells near the valley floor (one drawn as a circle, 1.2 m), the same well drawn twice, one outside
    wells.record(p, [(30.0, 40.0, 0.6), (30.2, 40.1, None), (29.0, 20.0, None), (500.0, 500.0, None)],
                 _ground(p), park)
    yield p, base
    p.close()


def test_wells_wait_for_their_answers(valley_wells):
    p, _ = valley_wells
    st = wells.status(p)
    assert st["count"] == 2 and st["in_model"] == 0   # the duplicate is one well; the far one is outside the park
    assert st["drawn_diameters_m"] == [1.2]
    assert all("depth" in w["missing"] and "strata infiltration rate" in w["missing"] for w in st["wells"])
    assert wells.existing_elements(p) == []
    with pytest.raises(ValueError):
        wells.apply(p, {"depth_m": -2})


def test_answered_wells_count_in_the_existing_site(valley_wells):
    p, base = valley_wells
    st = wells.apply(p, {"depth_m": 6, "infiltration_rate_mm_hr": 30})
    w = {x["id"]: x for x in st["wells"]}
    assert st["in_model"] == 1 and "diameter" in w["EW1"]["missing"]   # EW1 (29, 20) has no drawn diameter
    st = wells.apply(p, {"diameter_m": 1.0})
    assert st["in_model"] == 2
    assert {x["id"]: x["values"]["diameter_m"] for x in st["wells"]} == {"EW1": 1.0, "EW2": 1.2}   # the drawing first
    subs = {f["properties"]["id"]: f["properties"] for f in p.read_geojson("site/subcatchments.geojson")["features"]}
    assert "SC_EW2" in subs and subs["SC_EW2"]["outlet"].startswith("OUT_")
    els, _ = prepare_option(p, "baseline")
    assert {e.id for e in els} == {"EW1", "EW2"} and all(e.source == "existing" for e in els)
    ew2 = next(e for e in els if e.id == "EW2")
    assert ew2.inflow_from == ["SC_EW2"] and ew2.storage_volume_m3 > 0
    after = run_option(p, "baseline")
    rp = str(max(int(k) for k in after["return_periods"]))
    before_out = base["return_periods"][rp]["water_balance"]["outflow_total_m3"]
    after_out = after["return_periods"][rp]["water_balance"]["outflow_total_m3"]
    assert after_out < before_out   # the wells take water the park used to send away
    assert after["intervention_area_m2"] == 0   # existing wells are not a design's intervention
    assert not p.exists("scenarios/baseline/elements.json")


def test_one_well_answered_on_its_own(valley_wells):
    p, _ = valley_wells
    st = wells.apply(p, {"wells": [{"id": "EW2", "depth_m": 3}]})
    w = {x["id"]: x for x in st["wells"]}
    assert w["EW2"]["values"]["depth_m"] == 3 and w["EW1"]["values"]["depth_m"] == 6
    st = wells.apply(p, {"wells": [{"id": "EW2", "depth_m": None}]})   # back to the value for all wells
    assert {x["id"]: x["values"]["depth_m"] for x in st["wells"]}["EW2"] == 6


def test_a_design_keeps_the_existing_wells_without_credit(valley_wells):
    from spongepark.engine.layout.generate import generate
    from spongepark.engine.nbs.components import load_elements

    p, _ = valley_wells
    generate(p, "auto")
    assert not any(e.id.startswith("EW") for e in load_elements(p, "auto"))   # not saved into the design
    subs = {f["properties"]["id"] for f in p.read_geojson("scenarios/auto/site/subcatchments.geojson")["features"]} \
        if p.exists("scenarios/auto/site/subcatchments.geojson") else set()
    res = run_option(p, "auto")
    ids = {e["id"] for e in res["elements"]}
    assert {"EW1", "EW2"} <= ids   # in the design's flood model
    designed = sum(e.area_m2 or 0 for e in load_elements(p, "auto"))
    assert res["intervention_area_m2"] == pytest.approx(designed)   # only the design's own elements count
    assert not any(e.id.startswith("EW") for e in load_elements(p, "auto"))
    assert "SC_EW2" in subs   # the well keeps its catchment on the graded ground
