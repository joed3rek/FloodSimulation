"""Phase 6: Rhino .3dm export and round trip (edit programmatically, re-import, detect, rerun)."""

import pytest
import rhino3dm as r
from shapely.geometry import shape

from spongepark.engine.layout.generate import generate
from spongepark.engine.pipeline import run_option
from spongepark.rhino.roundtrip import export_3dm, import_3dm

from .test_layout import _valley_project
from spongepark.engine.nbs.components import elements_fc


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    root = tmp_path_factory.mktemp("rh")
    p, _ = _valley_project(root)
    p.parameters.set("layout.types", ["detention_pond", "bioswale"])
    p.parameters.set("nbs.bioswale.min_longitudinal_slope_pct", 0.5)
    generate(p, "auto")
    run_option(p, "auto")
    out = export_3dm(p, "auto", root / "auto.3dm")
    yield p, root, out
    p.close()


def _layers(f):
    return {f.Layers[i].Index: f.Layers[i].FullPath for i in range(len(f.Layers))}


def test_export_has_brief_layers_and_element_attributes(exported):
    p, root, out = exported
    f = r.File3dm.Read(out["path"])
    paths = set(_layers(f).values())
    for need in ("TERRAIN::Existing", "TERRAIN::Graded", "CONTOURS::Existing", "CONTOURS::Proposed",
                 "NBS::DetentionPond", "ANALYSIS::Subcatchments", "ANALYSIS::CutFill", "CONTEXT::Boundary"):
        assert need in paths, need
    nbs = [o for o in f.Objects if _layers(f)[o.Attributes.LayerIndex].startswith("NBS::")]
    assert len(nbs) == out["elements"] >= 1
    a = nbs[0].Attributes
    assert a.GetUserString("id") and a.GetUserString("type") and a.GetUserString("rp5.max_depth_m") is not None


def test_round_trip_detects_edits_locks_and_reruns(exported):
    p, root, out = exported
    f = r.File3dm.Read(out["path"])
    lay = _layers(f)
    pond = next(o for o in f.Objects if lay[o.Attributes.LayerIndex] == "NBS::DetentionPond")
    pond_id = pond.Attributes.GetUserString("id")
    pond.Geometry.Translate(r.Vector3d(0, 3.0, 0))  # move the pond 3 m north
    swales = [o for o in f.Objects if lay[o.Attributes.LayerIndex] == "NBS::Bioswale"]
    for o in swales:
        f.Objects.Delete(o.Attributes.Id)
    # a new rain garden drawn by the designer on the west slope
    rg_layer = next(i for i, pth in lay.items() if pth == "NBS::RainGarden") if "NBS::RainGarden" in lay.values() else None
    if rg_layer is None:
        L = r.Layer()
        L.Name = "RainGarden"
        L.ParentLayerId = next(f.Layers[i].Id for i in range(len(f.Layers)) if f.Layers[i].FullPath == "NBS")
        rg_layer = f.Layers.Add(L)
    pl = r.Point3dList()
    for x, y in ((15, 40), (21, 40), (21, 46), (15, 46), (15, 40)):
        pl.Add(x, y, 900.0)
    att = r.ObjectAttributes()
    att.LayerIndex = rg_layer
    f.Objects.AddPolyline(pl, att)
    edited = root / "edited.3dm"
    assert f.Write(str(edited), 8)

    res = import_3dm(p, "auto", edited)
    ch = res["changes"]
    assert pond_id in ch["moved"]
    assert sorted(ch["deleted"]) == sorted(o.Attributes.GetUserString("id") for o in swales)
    assert len(ch["new"]) == 1
    comps = {f["properties"]["id"]: f["properties"] for f in elements_fc(p, "auto")["features"]}
    new_id = ch["new"][0]
    assert comps[new_id]["type"] == "rain_garden" and comps[new_id]["source"] == "designer"
    assert set(p.locks.locked["auto"]) >= {pond_id, new_id}
    assert res["rerun"] and res["comparison"]["rows"]
    # the pond was regraded at its new place: invert recomputed from the new rim
    g = shape(elements_fc(p, "auto")["features"][0]["geometry"])
    assert comps[pond_id]["invert_elev_m"] > 0 and g.is_valid


def test_unchanged_file_changes_nothing(exported):
    p, root, _ = exported
    out = export_3dm(p, "auto", root / "again.3dm")
    res = import_3dm(p, "auto", out["path"])
    assert not any(res["changes"][k] for k in ("moved", "resized", "reshaped", "new", "deleted"))
    assert res["rerun"] is False
