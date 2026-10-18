"""Phase 2: survey DXF import on synthetic drawings with a known surface z = 100 + 0.02 x - 0.01 y."""

import json

import ezdxf
import numpy as np
import pytest

from spongepark.engine.io import cad
from spongepark.engine.project import Project
from spongepark.engine.terrain import read_geotiff
from spongepark.engine.terrain.survey import import_survey


def surface(x, y):
    return 100 + 0.02 * x - 0.01 * y


def make_dxf(path, contours_3d=False, units=6, typo=False, duplicate=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = units
    msp = doc.modelspace()
    # spot levels as text on a 5 m grid (value = level, insertion z = 0)
    for x in range(0, 101, 5):
        for y in range(0, 61, 5):
            z = surface(x, y)
            if typo and (x, y) == (50, 30):
                z += 1.0  # a mistyped level
            msp.add_text(f"{z:.3f}", dxfattribs={"layer": "BLOCK LEVELS", "insert": (x, y)})
            if duplicate:
                msp.add_text(f"{z:.3f}", dxfattribs={"layer": "BLOCK LEVELS", "insert": (x, y)})
    # contours: z = level  ->  x = (level - 100 + 0.01 y) / 0.02
    for lev in (100.5, 101.0, 101.5):
        ys = np.linspace(0, 60, 31)
        pts = [((lev - 100 + 0.01 * y) / 0.02, y) for y in ys]
        if contours_3d:
            pl = msp.add_polyline3d([(x, y, lev) for x, y in pts], dxfattribs={"layer": "ESMajor"})
        else:
            pl = msp.add_polyline2d(pts, dxfattribs={"layer": "ESMajor"})
            mid = pts[15]
            msp.add_text(f"{lev:g}", dxfattribs={"layer": "ESContAnn", "insert": (mid[0] + 0.5, mid[1])})
        if duplicate:
            msp.add_polyline2d(pts, dxfattribs={"layer": "ESMajor"})
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 60), (0, 60)], close=True, dxfattribs={"layer": "BOUNDARY"})
    msp.add_text("99.000", dxfattribs={"layer": "BE-LEVEL", "insert": (10, 10)})
    msp.add_circle((20, 20), 3, dxfattribs={"layer": "TREE"})
    doc.saveas(path)
    return path


def confirmed_map(path, **kw):
    m = cad.suggest_layer_map(cad.inventory(cad.read(path)))
    m.update(confirmed=True, **kw)
    return m


def test_inventory_suggests_roles_and_asks_about_be_level(tmp_path):
    p = make_dxf(tmp_path / "s.dxf")
    m = cad.suggest_layer_map(cad.inventory(cad.read(p)))
    assert m["roles"]["spot_levels"] == ["BLOCK LEVELS"]
    assert m["roles"]["contours"] == ["ESMajor"] and m["roles"]["contour_labels"] == ["ESContAnn"]
    assert m["roles"]["boundary"] == ["BOUNDARY"]
    assert m["needs_decision"] == ["BE-LEVEL"] and m["confirmed"] is False


def test_labelled_flat_contours_get_their_levels(tmp_path):
    p = make_dxf(tmp_path / "s.dxf")
    s = cad.extract(cad.read(p), confirmed_map(p))
    zs = sorted(c.z for c in s.contours)
    assert zs == [100.5, 101.0, 101.5] and all(c.how == "label" for c in s.contours)
    assert s.stats["contours_duplicates_removed"] == 3
    assert s.stats["spots"] == 21 * 13 and s.stats["spots_duplicates_removed"] == 21 * 13
    assert s.features["trees"][0]["properties"]["canopy_radius_m"] == 3


def test_3d_contours_read_directly(tmp_path):
    p = make_dxf(tmp_path / "s.dxf", contours_3d=True, duplicate=False)
    s = cad.extract(cad.read(p), confirmed_map(p))
    assert sorted(c.z for c in s.contours) == [100.5, 101.0, 101.5] and all(c.how == "3d" for c in s.contours)


@pytest.mark.parametrize("use_contours", [True, False])
def test_dem_reproduces_known_surface(tmp_path, use_contours):
    p = make_dxf(tmp_path / "s.dxf")
    with Project.create(tmp_path / "pr", "t", crs="LOCAL") as pr:
        q = import_survey(pr, p, confirmed_map(p, contours_in_surface=use_contours), stated_park_area_m2=6000)
        dem = read_geotiff(pr.path("terrain/existing.tif"))
        X, Y = dem.cell_centres()
        v = dem.z != dem.nodata
        err = dem.z[v] - surface(X[v], Y[v])
        assert np.sqrt(np.mean(err ** 2)) < 0.01  # planar surface: linear TIN is exact up to contour sampling
        assert q["spot_cross_validation"]["rmse_m"] < 0.01
        assert q["boundary_area_m2"] == pytest.approx(6000) and q["boundary_covered_share"] > 0.98
        assert q["contour_interval_m"] == 0.5 and q["contour_crossings"] == 0
        assert abs(q["contour_vs_spots"]["mean_m"]) < 0.01
        assert pr.exists("terrain/qc.png") and pr.exists("site/boundary.geojson")
        assert json.loads(pr.path("terrain/qc.json").read_text())["source"]["sha256"]


def test_typo_in_spot_level_is_flagged(tmp_path):
    p = make_dxf(tmp_path / "s.dxf", typo=True)
    with Project.create(tmp_path / "pr", "t", crs="LOCAL") as pr:
        q = import_survey(pr, p, confirmed_map(p, contours_in_surface=False))
    worst = q["spot_outliers"][0]
    assert (worst["x"], worst["y"]) == (50, 30) and worst["residual_m"] == pytest.approx(1.0, abs=0.05)


def test_unconfirmed_map_is_refused(tmp_path):
    p = make_dxf(tmp_path / "s.dxf")
    m = cad.suggest_layer_map(cad.inventory(cad.read(p)))
    with Project.create(tmp_path / "pr", "t", crs="LOCAL") as pr, pytest.raises(cad.CadError):
        import_survey(pr, p, m)


def test_level_text_parsing():
    assert cad.parse_level("RL 902.35") == 902.35
    assert cad.parse_level("+99.855") == 99.855
    assert cad.parse_level("100") == 100.0
    assert cad.parse_level("GATE") is None and cad.parse_level("B1") is None


def test_standardise_renames_merges_and_dedupes(tmp_path):
    p = make_dxf(tmp_path / "s.dxf")
    doc = cad.read(p)
    doc.modelspace().add_lwpolyline([(1, 1), (5, 1), (5, 5)], close=True, dxfattribs={"layer": "Existing Building"})
    doc.modelspace().add_lwpolyline([(6, 6), (9, 6), (9, 9)], close=True, dxfattribs={"layer": "BLDG"})
    doc.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "MYSTERY 2"})
    doc.saveas(p)

    rs = {r.old: r for r in cad.suggest_renames(cad.inventory(cad.read(p)))}
    assert rs["BLOCK LEVELS"].new == "SP-LVL-SPOT" and rs["BLOCK LEVELS"].confidence == "exact"
    assert rs["BLDG"].new == rs["Existing Building"].new == "SP-BLDG"
    assert rs["BE-LEVEL"].new == "SP-CHECK-BE-LEVEL"
    assert rs["MYSTERY 2"].new == "SP-X-MYSTERY-2" and rs["MYSTERY 2"].confidence == "none"

    csv_path = cad.write_renames(list(rs.values()), tmp_path / "r.csv")
    out = tmp_path / "s_SP.dxf"
    rep = cad.standardise(p, cad.read_renames(csv_path), out)
    assert rep["duplicates_removed_total"] == 21 * 13 + 3  # duplicate spot texts and contours
    sp = cad.read(out)
    layers = {e.dxf.layer for e in sp.modelspace()}
    assert {"SP-LVL-SPOT", "SP-CONT-MAJOR", "SP-CONT-LABEL", "SP-SITE-BOUNDARY", "SP-BLDG"} <= layers
    assert not sp.layers.has_entry("BLOCK LEVELS") and sp.layers.get("SP-BLDG").color == 5
    assert "BLOCK LEVELS" in {e.dxf.layer for e in cad.read(p).modelspace()}  # original untouched

    m = cad.suggest_layer_map(cad.inventory(sp))
    assert m["roles"]["spot_levels"] == ["SP-LVL-SPOT"] and m["needs_decision"] == ["SP-CHECK-BE-LEVEL"]
    s = cad.extract(sp, {**m, "confirmed": True})
    assert sorted(c.z for c in s.contours) == [100.5, 101.0, 101.5] and s.stats["spots"] == 21 * 13
    assert s.stats["spots_duplicates_removed"] == 0


def test_contours_that_disagree_with_the_spot_levels_only_check_the_ground():
    """A contour put at the wrong level would make a false mound or pit: with enough spot levels the
    ground is built from them, and the reason is given."""
    from shapely.geometry import LineString

    from spongepark.engine.io.cad import Contour, Spot, Survey
    from spongepark.engine.terrain.tin import contours_decision

    rng = np.random.default_rng(0)
    spots = [Spot(x, y, 100 + 0.01 * x, "S") for x in range(0, 60, 6) for y in range(0, 60, 6)]
    good = Contour(LineString([(20, 0), (20, 54)]), 100.2, "label", "C")
    wrong = Contour(LineString([(30, 5), (30, 50)]), 101.0, "label", "C")   # the ground there is ~100.3
    d = contours_decision(Survey([good, wrong], spots, {}, [], {}))
    assert d["use"] is False and "disagree" in d["reason"]
    d = contours_decision(Survey([good], spots, {}, [], {}))
    assert d["use"] is False and "generated" in d["reason"]          # adds nothing to 100 spot levels
    d = contours_decision(Survey([good, wrong], spots[:10], {}, [], {}))
    assert d["use"] is True                                          # too few spot levels: contours needed
