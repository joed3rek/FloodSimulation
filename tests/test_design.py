"""Design tools: elements placed by the designer are saved, carved into the ground and checked (no SWMM)."""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spongepark.api.server import app
from spongepark.engine.io import intake
from spongepark.engine.project import Project
from spongepark.engine.terrain.raster import read_geotiff

from .test_intake import drawing  # noqa: F401  (fixture)


@pytest.fixture
def site(drawing, tmp_path):  # noqa: F811
    r = intake.start(drawing)
    links = {l["layer"]: l["proposed"] for l in r["layers"]}
    links["BE-LEVEL"] = ""
    links["MYSTERY 7"] = ""
    return intake.finish(drawing, links, tmp_path / "park.sponge")["project"]


def _fc(*features):
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": g, "properties": p} for g, p in features]}


def test_place_carve_check_undo_through_the_api(site):
    c = TestClient(app)
    pid = c.post("/projects/open", json={"path": site}).json()["project"]
    tools = c.get(f"/projects/{pid}/design/tools").json()
    assert tools["rain_garden"]["draw"] == "polygon" and tools["recharge_well"]["draw"] == "point"
    assert tools["rain_garden"]["defaults"]["max_ponding_depth_m"] > 0 and tools["budget_pct"] > 0

    rg = ({"type": "Polygon", "coordinates": [[[30, 20], [40, 20], [40, 28], [30, 28], [30, 20]]]},
          {"id": "RG1", "type": "rain_garden", "max_ponding_depth_m": 0.25})
    deep = ({"type": "Polygon", "coordinates": [[[60, 30], [66, 30], [66, 36], [60, 36], [60, 30]]]},
            {"id": "RG2", "type": "rain_garden", "max_ponding_depth_m": 0.6})
    well = ({"type": "Point", "coordinates": [50, 40]}, {"id": "RW1", "type": "recharge_well"})
    r = c.put(f"/projects/{pid}/design/design?wait=true",
              json={"features": _fc(rg, deep, well), "action": "create", "element_id": "RW1"}).json()
    assert r["status"] == "done", r.get("error")
    out = r["result"]
    rows = {e["id"]: e for e in out["elements"]}
    assert abs(rows["RG1"]["area_m2"] - 80) < 1e-6 and rows["RG1"]["storage_m3"] > 80 * 0.25
    assert rows["RW1"]["depth_m"] == 6.0
    kinds = {(w["element"], w["kind"]) for w in out["warnings"]}
    assert ("RG2", "depth") in kinds                      # 0.6 m is beyond the rain garden's safe range
    assert out["budget"]["used_m2"] > 115 and out["budget"]["limit_pct"] > 0

    with Project.open(site) as p:
        g = read_geotiff(p.path("scenarios/design/terrain/graded.tif"))
        e = read_geotiff(p.path("terrain/existing.tif"))
        cut = np.where((g.z != g.nodata) & (e.z != e.nodata), e.z - g.z, 0)
        assert cut.max() > 0.2                                    # the rain garden is carved into the ground
        log = p.read_json("edit_log.json")["entries"]
        assert log[-1]["action"] == "create" and log[-1]["element_id"] == "RW1"
        assert {x["source"] for x in p.read_json("scenarios/design/elements.json")["elements"]} == {"designer"}

    # undo = send the earlier state; deleting everything gives back the existing ground
    r = c.put(f"/projects/{pid}/design/design?wait=true", json={"features": _fc(), "action": "delete"}).json()
    assert r["status"] == "done" and r["result"]["elements"] == []
    t = c.get(f"/projects/{pid}/terrain?option=design")
    assert t.status_code == 200
    assert c.get(f"/projects/{pid}/design/design").json()["elements"] == []
    c.post(f"/projects/{pid}/close")


def test_flow_analysis_needs_only_the_ground(site):
    """Flow lines, arrows and ponding hotspots from the ground model, before any rainfall or soil data."""
    from spongepark.engine.project.jsonschema import validate_package

    c = TestClient(app)
    pid = c.post("/projects/open", json={"path": site}).json()["project"]
    a = c.get(f"/projects/{pid}/flow").json()
    assert a["flow_lines"] and a["arrows"] and a["exits"]
    for x, y, z, dx, dy, s in a["arrows"][:50]:
        assert abs(np.hypot(dx, dy) - 1) < 0.01 and s > 0
    for f in a["flow_lines"]:
        assert len(f["xyz"]) == 3 * len(f["area_m2"]) and max(f["area_m2"]) >= a["min_line_area_m2"]
    assert sum(e["draining_area_m2"] for e in a["exits"]) > 0
    for h in a["hotspots"]:
        assert h["max_depth_m"] > 0 and h["volume_m3"] > 0 and len(h["outline"]) >= 6
    c.post(f"/projects/{pid}/close")
    with Project.open(site) as p:
        assert p.exists("site/flow_analysis.json")
        assert {k: v for k, v in validate_package(p.root).items() if v} == {}


def test_a_malformed_shape_is_refused_with_its_element_named(site):
    c = TestClient(app)
    pid = c.post("/projects/open", json={"path": site}).json()["project"]
    flat = ({"type": "Polygon", "coordinates": [[30, 20], [40, 20], [40, 28], [30, 20]]}, {"id": "DP1", "type": "detention_pond"})
    r = c.put(f"/projects/{pid}/design/design?wait=true", json={"features": _fc(flat), "action": "create"}).json()
    assert r["status"] == "error" and "DP1" in r["error"]
    bow = ({"type": "Polygon", "coordinates": [[[30, 20], [40, 28], [40, 20], [30, 28], [30, 20]]]}, {"id": "RG9", "type": "rain_garden"})
    r = c.put(f"/projects/{pid}/design/design?wait=true", json={"features": _fc(bow), "action": "create"}).json()
    assert r["status"] == "error" and "crosses itself" in r["error"]
    c.post(f"/projects/{pid}/close")


def test_an_element_wholly_on_keep_out_ground_is_kept_but_not_carved(site):
    """A rain garden drawn under a tree's canopy (keep-out) is not dug, and the designer is told why."""
    c = TestClient(app)
    pid = c.post("/projects/open", json={"path": site}).json()["project"]
    under_tree = ({"type": "Polygon", "coordinates": [[[19, 19], [21, 19], [21, 21], [19, 21], [19, 19]]]},
                  {"id": "RG5", "type": "rain_garden"})
    r = c.put(f"/projects/{pid}/design/design?wait=true", json={"features": _fc(under_tree), "action": "create"}).json()
    assert r["status"] == "done", r.get("error")
    texts = [w["text"] for w in r["result"]["warnings"]]
    assert any("RG5" in t and ("not carved" in t or "keep-out" in t) for t in texts), texts
    c.post(f"/projects/{pid}/close")
