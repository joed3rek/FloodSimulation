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
