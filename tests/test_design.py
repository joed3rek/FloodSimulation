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
