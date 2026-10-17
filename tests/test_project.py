"""Phase 0: project file, parameters, CRS."""

import json
import zipfile

import pytest

from spongepark.engine.project import CRSError, Project, ProjectError, Source, default_parameters, validate_project_crs


def test_create_save_load_roundtrip(tmp_path):
    path = tmp_path / "park.sponge"
    with Project.create(path, "Pilot", city="Bengaluru") as p:
        p.parameters.set("design.area_budget_pct", 15.0, "%", Source.USER, "client brief")
        p.write_json("site/test.json", {"a": 1})
        p.history.log("test_edit", note="x")
        p.save()
    assert zipfile.is_zipfile(path)
    names = zipfile.ZipFile(path).namelist()
    for required in ("manifest.json", "parameters.json", "locks.json", "history.json"):
        assert required in names
    with Project.open(path) as q:
        assert q.manifest.project_name == "Pilot"
        assert q.manifest.crs == "EPSG:32643"
        assert q.parameters.value("design.area_budget_pct") == 15.0
        assert q.parameters.get("design.area_budget_pct").confirmed
        assert q.read_json("site/test.json") == {"a": 1}
        assert [e.action for e in q.history.entries] == ["create", "test_edit"]


def test_folder_project_and_overwrite_guard(tmp_path):
    d = tmp_path / "proj"
    Project.create(d, "Folder").close()
    assert (d / "manifest.json").exists()
    with pytest.raises(ProjectError):
        Project.create(d, "again")


def test_defaults_are_flagged_and_unconfirmed():
    ps = default_parameters()
    assert ps.items, "defaults registry empty"
    for p in ps:
        assert p.source in (Source.DEFAULT, Source.LITERATURE)
        assert not p.confirmed
        assert p.unit
    # site properties must never be defaulted
    assert not any(k.startswith("soil.") for k in ps.items)


def test_confirm_parameter(tmp_path):
    with Project.create(tmp_path / "a.sponge", "x") as p:
        n = len(p.parameters.unconfirmed())
        p.parameters.confirm("nbs.max_drawdown_hr")
        assert len(p.parameters.unconfirmed()) == n - 1


def test_crs_validation():
    assert validate_project_crs("EPSG:32643") == "EPSG:32643"
    assert validate_project_crs("local") == "LOCAL"
    with pytest.raises(CRSError):
        validate_project_crs("EPSG:4326")


def test_geographic_geojson_rejected_or_reprojected(tmp_path):
    lonlat = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": "B"},
         "geometry": {"type": "Point", "coordinates": [77.59, 12.97]}}]}
    with Project.create(tmp_path / "c.sponge", "x") as p:
        with pytest.raises(CRSError):
            p.write_geojson("site/boundary.geojson", lonlat)
        p.write_geojson("site/boundary.geojson", lonlat, source_crs="EPSG:4326")
        x, y = p.read_geojson("site/boundary.geojson")["features"][0]["geometry"]["coordinates"]
        assert 770000 < x < 790000 and 1430000 < y < 1440000


def test_unknown_schema_version_rejected(tmp_path):
    d = tmp_path / "old"
    Project.create(d, "x").close()
    m = json.loads((d / "manifest.json").read_text())
    m["schema_version"] = "9.9"
    (d / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ProjectError):
        Project.open(d)
