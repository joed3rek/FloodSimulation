"""Phase 0: the shared .sponge schema, its generated C# classes, element records and the 1.0 migration."""

import json
import os
import shutil
import subprocess
import zipfile

import pytest

from spongepark.engine.nbs.components import NbSElement, from_record, load_elements, to_record
from spongepark.engine.project import Project
from spongepark.engine.project.csharp import CS_PATH, generate
from spongepark.engine.project.jsonschema import SCHEMA_PATH, build_schema, validate_package
from spongepark.engine.project.schema import ElementRecord

from .sponge_case import ELEMENTS, build, differences, read_package
from .test_unity_gpu import ROOT, _editor


def test_committed_schema_matches_the_models():
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == json.loads(json.dumps(build_schema())), \
        "schema/sponge.schema.json is out of date: run `spongepark schema export`"


def test_committed_csharp_matches_the_schema():
    assert CS_PATH.read_text(encoding="utf-8") == generate(), \
        "SpongeSchema.g.cs is out of date: run `spongepark schema csharp`"


@pytest.mark.parametrize("rec", ELEMENTS, ids=[r["id"] for r in ELEMENTS])
def test_element_records_convert_without_loss(rec):
    el = from_record(rec)
    assert isinstance(el, NbSElement)
    again = to_record(el)
    # equal as records (a default written out, such as locked: false, is not a change)
    assert ElementRecord.model_validate(again).model_dump(exclude_none=True) ==         ElementRecord.model_validate(rec).model_dump(exclude_none=True)
    assert set(rec) <= set(again)


def test_a_rich_project_validates_and_reopens(tmp_path):
    path = build(tmp_path / "rich.sponge")
    with Project.open(path) as p:
        errors = {k: v for k, v in validate_package(p.root).items() if v}
        assert errors == {}
        assert {e.id for e in load_elements(p, "opt")} == {"RG1", "SW1", "DP1", "RW1"}
        assert p.parameters.get("rain.design_return_period_yr").source.value == "designer"
        again = p.save(tmp_path / "again.sponge")
    assert differences(path, again) == []


def test_migrates_a_1_0_project(tmp_path):
    """1.0 kept options/<id>/components.geojson and parameter source "user"."""
    src = tmp_path / "old"
    with Project.create(tmp_path / "new.sponge", "old park") as p:
        shutil.copytree(p.root, src)
    shutil.rmtree(src / "scenarios")
    (src / "edit_log.json").unlink()
    (src / "terrain" / "edits.json").unlink()
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["schema_version"] = "1.0"
    (src / "manifest.json").write_text(json.dumps(manifest))
    params = json.loads((src / "parameters.json").read_text())
    params["rain.design_return_period_yr"] = {"value": 10, "unit": "yr", "source": "user", "note": "", "confirmed": True}
    (src / "parameters.json").write_text(json.dumps(params))
    (src / "options" / "auto").mkdir(parents=True)
    poly = ELEMENTS[0]["geometry"]
    (src / "options" / "auto" / "components.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": poly,
         "properties": {"id": "RG1", "type": "rain_garden", "max_ponding_depth_m": 0.25, "source": "generated"}}]}))
    old = tmp_path / "old.sponge"
    with zipfile.ZipFile(old, "w") as z:
        for f in src.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(src).as_posix())

    with Project.open(old) as p:
        assert p.manifest.schema_version == "1.1"
        assert not p.exists("options")
        assert p.parameters.get("rain.design_return_period_yr").source.value == "designer"
        els = load_elements(p, "auto")
        assert [(e.id, e.source, e.max_ponding_depth_m) for e in els] == [("RG1", "proposal", 0.25)]
        assert p.read_json("scenarios/auto/scenario.json")["status"] == "proposal"
        assert p.exists("edit_log.json") and p.exists("terrain/edits.json")
        assert {k: v for k, v in validate_package(p.root).items() if v} == {}


@pytest.mark.skipif(os.environ.get("SPONGEPARK_TEST_UNITY") != "1", reason="set SPONGEPARK_TEST_UNITY=1 to run")
def test_unity_round_trip_loses_nothing(tmp_path):
    """Phase 0 acceptance: a project created in Python opens in Unity and round trips without loss."""
    editor = _editor()
    assert editor, "Unity editor not found"
    src = build(tmp_path / "python.sponge")
    out, report = tmp_path / "unity.sponge", tmp_path / "report.json"
    project = os.environ.get("SPONGEPARK_UNITY_PROJECT", str(ROOT / "unity" / "SpongeParkApp"))
    subprocess.run([editor, "-batchmode", "-projectPath", project, "-executeMethod", "SpongePark.EditorTools.RoundTrip.Run",
                    "-in", str(src), "-out", str(out), "-report", str(report), "-logFile", str(tmp_path / "unity.log")],
                   check=False, timeout=1800)
    r = json.loads(report.read_text())
    assert r["ok"], r.get("error")
    assert r["scenarios"] == {"baseline": 0, "opt": 4} and r["proposals"] == 1 and r["terrain_edits"] == 2
    assert differences(src, out) == []
    assert all("\\" not in n for n in read_package(out))
    with Project.open(out) as p:   # and Python reads Unity's file
        assert {k: v for k, v in validate_package(p.root).items() if v} == {}
        assert p.manifest.app_version
