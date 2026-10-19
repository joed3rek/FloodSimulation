"""A park drawn the way Tree Park is: trees as a symbol on layer 0, paths as the ground between beds outlined by
path edges, and a pond on the water layer. The symbols are asked about and become trees; the paths become path
surface; the pond is shown as water and stores rain once its depth is given (and not before)."""

import ezdxf
import numpy as np
import pytest
from fastapi.testclient import TestClient

from spongepark.api.server import app
from spongepark.engine.io import intake
from spongepark.engine.project import Project

from .test_survey_import import make_dxf


@pytest.fixture
def park(tmp_path):
    p = make_dxf(tmp_path / "tree park.dxf")
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    tree = doc.blocks.new("A$TREE1")
    tree.add_circle((0, 0), 2.0)
    for i in range(12):
        msp.add_blockref("A$TREE1", (12 + 6 * i, 55), dxfattribs={"layer": "0"})
    # two beds outlined by path edges, a 5 m path between them and round them up to the boundary
    for x0, x1 in ((5, 45), (50, 95)):
        msp.add_lwpolyline([(x0, 5), (x1, 5), (x1, 45), (x0, 45)], close=True, dxfattribs={"layer": "FOOT PATH"})
    msp.add_lwpolyline([(60, 15), (75, 15), (75, 30), (60, 30)], close=True, dxfattribs={"layer": "POND"})
    doc.saveas(p)
    return p


def _finish(path, tmp_path, trees=True):
    r = intake.start(path)
    rows = {l["layer"]: l for l in r["layers"]}
    sym = rows["0/A$TREE1"]
    assert sym["proposed"] == "SP-TREE" and sym["question"]["kind"] == "confirm" and sym["count"] == 12
    links = {l["layer"]: l["proposed"] for l in r["layers"]}
    links.update({"BE-LEVEL": "", "FOOT PATH": "SP-PATH", "POND": "SP-WATER"})
    if not trees:
        links["0/A$TREE1"] = ""
    return intake.finish(path, links, tmp_path / "park.sponge")["project"]


def test_symbols_on_layer_zero_become_trees_when_linked(park, tmp_path):
    with Project.open(_finish(park, tmp_path)) as p:
        layers = {L["name"]: L for L in p.read_json("site/survey_layers.json")["layers"]}
    trees = [f for f in layers["SP-TREE"]["features"] if f["g"] == "point"]
    assert len(trees) == 1 + 12   # the drawing's own tree plus the symbols
    assert sum(1 for f in trees if abs(f.get("radius_m", 0) - 2.0) < 0.05) == 12
    assert not list((tmp_path).glob("*_symbols.dxf"))   # the working copy is removed


def test_paths_between_beds_become_path_surface(park, tmp_path):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    with Project.open(_finish(park, tmp_path)) as p:
        L = next(L for L in p.read_json("site/survey_layers.json")["layers"] if L["kind"] == "path")
    tris = []
    for f in L["features"]:
        if f["g"] == "mesh":
            xyz, t = np.array(f["xyz"]).reshape(-1, 3), np.array(f["tri"]).reshape(-1, 3)
            tris += [Polygon(xyz[k][:, :2]) for k in t]
    surface = unary_union(tris)
    assert surface.contains(Polygon([(46, 10), (49, 10), (49, 40), (46, 40)]))   # the path between the beds
    assert surface.intersection(Polygon([(10, 10), (40, 10), (40, 40), (10, 40)])).area < 1   # not the beds


def test_a_pond_stores_rain_once_its_depth_is_given(park, tmp_path):
    c = TestClient(app)
    pid = c.post("/projects/open", json={"path": _finish(park, tmp_path)}).json()["project"]
    ponds = c.get(f"/projects/{pid}/site/ponds").json()["ponds"]
    assert len(ponds) == 1 and ponds[0]["in_park"] and not ponds[0]["in_model"]   # nothing assumed
    assert abs(ponds[0]["area_m2"] - 225) < 1
    bad = c.put(f"/projects/{pid}/site/ponds", json={"answers": [{"id": "POND1", "depth_m": 0.5, "water_m": 0.8}]})
    assert bad.status_code == 400
    r = c.put(f"/projects/{pid}/site/ponds", json={"answers": [{"id": "POND1", "depth_m": 1.0, "water_m": 0.4}]}).json()
    pond = r["ponds"][0]
    assert pond["in_model"] and pond["storage_m3"] > 0.8 * 225 * 0.6   # about the area times the room (0.6 m)
    flow = c.get(f"/projects/{pid}/flow").json()
    assert any(h["volume_m3"] > 0.8 * pond["storage_m3"] for h in flow["hotspots"])   # water collects in it
    # answered again: the cut is redone from the surveyed ground, not added to the last one
    r2 = c.put(f"/projects/{pid}/site/ponds", json={"answers": [{"id": "POND1", "depth_m": 1.0, "water_m": 0.4}]}).json()
    assert abs(r2["ponds"][0]["storage_m3"] - pond["storage_m3"]) < 1e-6
    c.post(f"/projects/{pid}/close")
