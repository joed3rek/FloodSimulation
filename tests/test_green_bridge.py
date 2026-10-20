"""Green bridges: a low crossing across a bioswale holds water behind it to its crest, then spills over."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spongepark.api.server import app
from spongepark.engine.project import Project
from spongepark.engine.terrain.raster import read_geotiff

from .conftest import X0, Y0, constant_storm, rect
from .test_design import _fc, site  # noqa: F401  (fixture)
from .test_intake import drawing  # noqa: F401  (fixture)
from .test_swmm import run_storm


def _line(*pts):
    return {"type": "LineString", "coordinates": [list(p) for p in pts]}


def test_bridge_raises_its_swale_holds_a_pool_and_passes_the_swale_on(site):  # noqa: F811
    c = TestClient(app)
    pid = c.post("/projects/open", json={"path": site}).json()["project"]
    assert c.get(f"/projects/{pid}/design/tools").json()["green_bridge"]["draw"] == "line"
    swale = (_line((20, 30), (50, 30), (80, 30)), {"id": "SW1", "type": "bioswale"})
    gb1 = (_line((50, 27), (50, 33)), {"id": "GB1", "type": "green_bridge"})
    gb2 = (_line((70, 27), (70, 33)), {"id": "GB2", "type": "green_bridge"})
    gb3 = (_line((76, 27), (76, 33)), {"id": "GB3", "type": "green_bridge"})    # 6 m after GB2: too close
    stray = (_line((30, 50), (30, 55)), {"id": "GB4", "type": "green_bridge"})  # crosses no swale
    r = c.put(f"/projects/{pid}/design/design?wait=true",
              json={"features": _fc(swale, gb1, gb2, gb3, stray), "action": "create", "element_id": "GB1"}).json()
    assert r["status"] == "done", r.get("error")
    out = r["result"]
    kinds = {(w["element"], w["kind"]) for w in out["warnings"]}
    assert ("GB4", "bridge") in kinds and ("GB3", "bridge") in kinds and ("GB1", "bridge") not in kinds
    rows = {e["id"]: e for e in out["elements"]}
    swale_area = rows["SW1"]["area_m2"]
    assert out["budget"]["used_m2"] == pytest.approx(swale_area)   # decks lie on the swale: no extra area

    with Project.open(site) as p:
        els = {e["id"]: e for e in p.read_json("scenarios/design/elements.json")["elements"]}
        b = els["GB1"]
        assert b["parameters"]["pool_area_m2"] > 0 and b["parameters"]["dam_height_m"] == pytest.approx(0.15)
        # the swale's outflow goes through its bridges upstream first, then where the swale went
        assert els["SW1"]["connections"]["outflow_to"] == "GB1"
        assert els["GB1"]["connections"]["overflow_to"] == "GB2"
        assert els["GB2"]["connections"]["overflow_to"] == "GB3"
        assert els["GB3"]["connections"]["overflow_to"] not in (None, "GB1", "GB2", "GB3", "SW1")
        # the ground under the deck stands at the crest: the swale bottom there plus 0.15 m
        g = read_geotiff(p.path("scenarios/design/terrain/graded.tif"))
        X, Y = g.cell_centres()
        ox, oy = p.read_json("terrain/frame.json")["origin"] if p.exists("terrain/frame.json") else (0.0, 0.0)
        r_, c_ = np.unravel_index(np.argmin(np.hypot(X - 50 - ox, Y - 30 - oy)), X.shape)
        assert g.z[r_, c_] == pytest.approx(b["parameters"]["invert_elev_m"] + 0.15, abs=0.02)
        # edits carve quickly; the subcatchments and drawings are rebuilt when SWMM needs them
        assert p.exists("scenarios/design/regrade_pending.json") and not p.exists("scenarios/design/design.dxf")
        from spongepark.engine.site import Site

        Site.load(p, "design")
        assert not p.exists("scenarios/design/regrade_pending.json") and p.exists("scenarios/design/design.dxf")
        assert p.exists("scenarios/design/site/subcatchments.geojson")
    c.post(f"/projects/{pid}/close")


def test_swmm_bridge_pool_holds_water_then_spills(tmp_project, tmp_path):
    """Run-on from a paved area through a swale: a bridge keeps its pool (seeping slowly); the rest spills on."""
    soil = dict(max_rate_mm_hr=2, min_rate_mm_hr=2, decay_1_hr=4, dry_time_days=7, max_volume_mm=0)
    sub = [(rect(0, 0, 40, 20), dict(id="S", outlet="OUT", pct_imperv=100, slope_pct=2, flow_length_m=20))]
    swale = (_line((X0 + 0, Y0 + 25), (X0 + 40, Y0 + 25)),
             dict(id="SW", type="bioswale", top_width_m=3, inflow_from=["S"], outflow_to="OUT"))
    p0 = tmp_project(sub, [swale], soil=soil)
    _, _, without = run_storm(p0, "opt", constant_storm(40, 1), tmp_path)
    p0.close()

    gb = (_line((X0 + 30, Y0 + 23), (X0 + 30, Y0 + 27)),
          dict(id="GB", type="green_bridge", invert_elev_m=99.5, pool_area_m2=40.0, dam_height_m=0.15,
               overflow_to="OUT"))
    swale[1]["outflow_to"] = "GB"
    p = tmp_project(sub, [swale, gb], soil=soil)
    spec, res, wb = run_storm(p, "opt", constant_storm(40, 1), tmp_path)
    assert "GB" in spec.elements and not spec.elements["GB"].is_lid
    assert abs(wb["closure_error_pct"]) < 1
    held = without["outflow_total_m3"] - wb["outflow_total_m3"]
    assert 0.5 < held <= 40 * 0.15 / 2 + 0.5   # about the wedge behind the crest (3 m3), less what seeps
