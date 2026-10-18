"""Survey intake: layers linked or asked, previews, cleaned drawing, project with a ground model."""

import ezdxf
import pytest
from fastapi.testclient import TestClient

from spongepark.api.server import app
from spongepark.engine.io import cad, intake
from spongepark.engine.project import Project

from .test_survey_import import make_dxf


@pytest.fixture
def drawing(tmp_path):
    p = make_dxf(tmp_path / "park survey.dxf")
    doc = ezdxf.readfile(p)
    doc.modelspace().add_line((5, 5), (8, 8), dxfattribs={"layer": "MYSTERY 7"})
    doc.modelspace().add_lwpolyline([(0, 0), (100, 0), (100, 60)], dxfattribs={"layer": "COMPOUND WALL"})
    doc.modelspace().add_line((40, 0), (44, 0), dxfattribs={"layer": "GATE"})
    doc.saveas(p)
    return p


def test_start_links_known_layers_and_asks_about_the_rest(drawing):
    r = intake.start(drawing)
    by = {l["layer"]: l for l in r["layers"]}
    assert by["BLOCK LEVELS"]["proposed"] == "SP-LVL-SPOT" and by["BLOCK LEVELS"]["question"] is None
    assert by["ESMajor"]["title"] == "Major contours"
    assert by["BE-LEVEL"]["question"]["kind"] == "unclear" and len(by["BE-LEVEL"]["question"]["answers"]) >= 2
    assert by["MYSTERY 7"]["question"]["kind"] == "unknown"
    assert r["questions"] == 2
    assert r["layers"][0]["question"] is not None  # questions come first
    assert any(c["name"] == "" for c in r["choices"]) and all(not c["name"].startswith("SP-CHECK") for c in r["choices"])


def test_preview_is_a_png(drawing):
    png = intake.preview(drawing, "BE-LEVEL")
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 2000


def test_geometry_gives_linework_per_layer_for_the_plan(drawing):
    g = intake.geometry(drawing)
    w, h = g["extent"]
    assert w > 0 and h > 0
    assert "BE-LEVEL" in g["layers"]
    for layer in g["layers"].values():
        for line in layer["lines"]:
            assert len(line) >= 4 and len(line) % 2 == 0
        assert len(layer["points"]) % 2 == 0
    # coordinates are relative to the extent's lower-left, so most of the drawing sits inside it
    xs = [v for L in g["layers"].values() for line in L["lines"] for v in line[0::2]]
    inside = sum(-0.05 * w <= x <= 1.05 * w for x in xs) / len(xs)
    assert inside > 0.9


def test_finish_cleans_the_drawing_and_builds_the_ground(drawing, tmp_path):
    r = intake.start(drawing)
    links = {l["layer"]: l["proposed"] for l in r["layers"]}
    links["BE-LEVEL"] = ""       # answered: not needed
    links["MYSTERY 7"] = ""
    out = intake.finish(drawing, links, tmp_path / "park.sponge")
    cleaned = cad.read(out["cleaned_drawing"])
    layers = {e.dxf.layer for e in cleaned.modelspace()}
    assert "SP-LVL-SPOT" in layers and "BLOCK LEVELS" not in layers and "SP-X-BE-LEVEL" in layers
    assert out["cleaning"]["duplicates_removed_total"] > 0
    assert "SP-X-BE-LEVEL" not in sum(out["layer_map"]["roles"].values(), [])  # left out stays out
    with Project.open(out["project"]) as p:
        assert p.exists("terrain/existing.tif") and p.exists("site/boundary.geojson")
        assert p.exists(f"survey/{drawing.name}") and p.exists(f"survey/{drawing.stem}_SP.dxf")  # one file carries all
    assert out["qc"]["spot_cross_validation"]["rmse_m"] < 0.05


def test_finish_refuses_without_levels(drawing, tmp_path):
    r = intake.start(drawing)
    links = {l["layer"]: ("" if l["proposed"] in ("SP-LVL-SPOT", "SP-CONT-MAJOR", "SP-CONT-MINOR") else l["proposed"]) for l in r["layers"]}
    with pytest.raises(cad.CadError, match="levels"):
        intake.finish(drawing, links, tmp_path / "x.sponge")


def test_upload_through_the_api(drawing, tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "WORKSPACE", tmp_path / "ws")
    c = TestClient(app)
    r = c.post("/intake/upload", params={"filename": drawing.name}, content=drawing.read_bytes())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["survey"].startswith(str(tmp_path / "ws")) and data["questions"] == 2
    assert c.get("/intake/preview", params={"path": data["survey"], "layer": "ESMajor"}).headers["content-type"] == "image/png"
    bad = c.post("/intake/upload", params={"filename": "notes.txt"}, content=b"hello")
    assert bad.status_code == 400


def test_finish_puts_the_survey_layers_on_the_ground(drawing, tmp_path):
    """Walls, gates, trees, boundary ... become 3D-ready layers on the ground model, one per SP layer."""
    import numpy as np

    from spongepark.engine.project.jsonschema import validate_package
    from spongepark.engine.terrain.raster import read_geotiff

    r = intake.start(drawing)
    links = {l["layer"]: l["proposed"] for l in r["layers"]}
    links["BE-LEVEL"] = ""
    links["MYSTERY 7"] = ""
    out = intake.finish(drawing, links, tmp_path / "park.sponge")
    assert {L["name"] for L in out["survey_layers"]} >= {"SP-WALL", "SP-GATE", "SP-TREE", "SP-SITE-BOUNDARY"}
    with Project.open(out["project"]) as p:
        layers = {L["name"]: L for L in p.read_json("site/survey_layers.json")["layers"]}
        assert {k: v for k, v in validate_package(p.root).items() if v} == {}
        wall = layers["SP-WALL"]
        # boundary walls are shown as 2 m fencing
        assert wall["kind"] == "fence" and wall["source_layers"] == ["COMPOUND WALL"] and wall["height_m"] == 2.0
        # the 4 m gate line becomes one gate on the wall, facing along it, with an opening cut in the wall
        gates = layers["SP-GATE"]["features"]
        assert len(gates) == 1 and gates[0]["g"] == "point"
        assert abs(gates[0]["width_m"] - 4.0) < 0.1 and abs(gates[0]["angle_deg"] % 180) < 1
        assert abs(gates[0]["xyz"][0] - 42) < 0.2 and abs(gates[0]["xyz"][1]) < 0.2
        bottom = [np.array(f["xyz"]).reshape(-1, 3) for f in wall["features"]]
        assert not any(((40.5 < a[:, 0]) & (a[:, 0] < 43.5) & (np.abs(a[:, 1]) < 0.1)).any() for a in bottom)
        xyz = np.array(wall["features"][0]["xyz"]).reshape(-1, 3)
        assert len(xyz) > 3                      # densified so it follows the ground
        dem = read_geotiff(p.path("terrain/existing.tif"))
        z = dem.z[dem.z != dem.nodata]
        assert z.min() - 0.01 <= xyz[:, 2].min() and xyz[:, 2].max() <= z.max() + 0.01   # on the ground
        tree = layers["SP-TREE"]["features"][0]
        assert tree["g"] == "point" and abs(tree["radius_m"] - 3) < 1e-6
        assert not any(n.startswith(("SP-LVL", "SP-ANNO", "SP-CONT-LABEL")) for n in layers)   # no annotation
