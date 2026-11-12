"""A site modelled in Rhino or exported to COLLADA becomes a project: the same ground grid a survey gives, so flow and
ponding read it as usual. The site: a 60 x 40 m slope with a bowl at a known place, a building, and trees to ignore."""

import re
import numpy as np
import pytest
import rhino3dm as r
from fastapi.testclient import TestClient

from spongepark.api.server import app
from spongepark.engine.hydrology import flowmap
from spongepark.engine.io import model3d
from spongepark.engine.project import Project
from spongepark.engine.terrain.raster import read_geotiff

BOWL = (20.0, 20.0)
BOWL_R, BOWL_D = 6.0, 1.0
ROLES = {"Terrain": "ground", "Buildings": "building", "Trees": "ignore"}


def ground_z(x, y):
    d = np.hypot(x - BOWL[0], y - BOWL[1])
    return 100.0 + 0.02 * x - BOWL_D * np.clip(1 - (d / BOWL_R) ** 2, 0, None)


def grid(w=60, d=40, step=1.0, hole=None):
    xs, ys = np.arange(0, w + step, step), np.arange(0, d + step, step)
    v = [(x, y, ground_z(x, y)) for y in ys for x in xs]
    n = len(xs)
    q = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(len(ys) - 1) for i in range(n - 1)
         if hole is None or not (hole[0] <= xs[i] < hole[1] and hole[2] <= ys[j] < hole[3])]
    return v, q


def box(x0, y0, x1, y1, z0, z1):
    v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    return v, [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]


def rhino_mesh(v, q, k=1.0):
    m = r.Mesh()
    for x, y, z in v:
        m.Vertices.Add(float(x * k), float(y * k), float(z * k))
    for f in q:
        m.Faces.AddFace(*f)
    return m


def write_3dm(path, units=r.UnitSystem.Meters, k=1.0, hole=None, boundary=None):
    f = r.File3dm()
    f.Settings.ModelUnitSystem = units

    def layer(name):
        a = r.ObjectAttributes()
        a.LayerIndex = f.Layers.AddLayer(name, (0, 0, 0, 255))
        return a

    f.Objects.AddMesh(rhino_mesh(*grid(hole=hole), k), layer("Terrain"))
    f.Objects.AddMesh(rhino_mesh(*box(45, 25, 55, 35, 100, 106), k), layer("Buildings"))
    f.Objects.AddMesh(rhino_mesh(*box(5, 5, 8, 8, 100, 120), k), layer("Trees"))
    if boundary:
        pts = [r.Point3d(x * k, y * k, 0) for x, y in boundary + boundary[:1]]
        f.Objects.AddCurve(r.PolylineCurve(pts), layer("Site boundary"))
    assert f.Write(str(path), 0)
    return path


def dae_geometry(gid, v, q):
    pos = " ".join(f"{a:.4f}" for p in v for a in p)
    tris = " ".join(f"{a} {b} {c} {a} {c} {d}" for a, b, c, d in q)
    return (f'<geometry id="{gid}"><mesh><source id="{gid}-p"><float_array id="{gid}-a" count="{len(v) * 3}">{pos}</float_array>'
            f'<technique_common><accessor source="#{gid}-a" count="{len(v)}" stride="3"/></technique_common></source>'
            f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-p"/></vertices>'
            f'<triangles count="{len(q) * 2}"><input semantic="VERTEX" source="#{gid}-v" offset="0"/><p>{tris}</p></triangles>'
            f"</mesh></geometry>")


def write_dae(path, up="Z_UP", wrap=False):
    """Coordinates in the file are y-up when asked for; ``wrap`` puts the scene in one node, as SketchUp does."""
    parts = {"Terrain": grid(), "Buildings": box(45, 25, 55, 35, 100, 106), "Trees": box(5, 5, 8, 8, 100, 120)}

    def to_file(v):
        return [(x, z, -y) if up == "Y_UP" else (x, y, z) for x, y, z in v]

    geos = "".join(dae_geometry(n, to_file(v), q) for n, (v, q) in parts.items())
    nodes = "".join(f'<node name="{n}"><instance_geometry url="#{n}"/></node>' for n in parts)
    if wrap:
        nodes = f'<node name="SketchUp">{nodes}</node>'
    path.write_text(f'<?xml version="1.0"?><COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
                    f'<asset><unit name="meter" meter="1"/><up_axis>{up}</up_axis></asset>'
                    f"<library_geometries>{geos}</library_geometries>"
                    f'<library_visual_scenes><visual_scene id="S">{nodes}</visual_scene></library_visual_scenes>'
                    f'<scene><instance_visual_scene url="#S"/></scene></COLLADA>')
    return path


def roles_of(info):
    return {L["layer"]: L["role"] for L in info["layers"]}


def _check_site(project_path):
    with Project.open(project_path) as p:
        dem = read_geotiff(p.path("terrain/existing.tif"))
        X, Y = dem.cell_centres()
        at = lambda x, y: dem.z[np.unravel_index(np.argmin(np.hypot(X - x, Y - y)), X.shape)]
        assert at(*BOWL) == pytest.approx(ground_z(*BOWL), abs=0.05)
        assert at(35, 5) == pytest.approx(ground_z(35, 5), abs=0.05)
        assert at(50, 30) == pytest.approx(106, abs=0.01)         # the building stands as a block
        assert at(6.5, 6.5) == pytest.approx(ground_z(6.5, 6.5), abs=0.05)   # the tree layer is not in the ground
        buildings = [f for f in p.read_geojson("site/context.geojson")["features"] if f["properties"]["kind"] == "buildings"]
        assert len(buildings) == 1
        assert p.read_json("terrain/qc.json")["site_area_m2"] == pytest.approx(60 * 40, rel=0.02)


@pytest.mark.parametrize("make", [
    lambda t: write_3dm(t / "site.3dm"),
    lambda t: write_dae(t / "site.dae"),
    lambda t: write_dae(t / "site.dae", up="Y_UP"),
    lambda t: write_dae(t / "site.dae", wrap=True),
], ids=["rhino", "dae-z-up", "dae-y-up", "dae-one-wrapping-node"])
def test_a_model_becomes_the_ground_with_its_hollow_in_the_right_place(make, tmp_path):
    path = make(tmp_path)
    info = model3d.inspect(path)
    assert roles_of(info) == ROLES
    assert info["max"][2] == pytest.approx(106)   # the size of what the study uses: the trees are left out
    out = model3d.finish(path, roles_of(info))
    _check_site(out["project"])
    with Project.open(out["project"]) as p:
        hollow = [h for h in flowmap.load(p, True)["hotspots"] if h["kind"] == "ponding"][0]
    assert hollow["max_depth_m"] == pytest.approx(BOWL_D, abs=0.25)
    assert np.hypot(hollow["x"] - BOWL[0], hollow["y"] - BOWL[1]) < 2.0


def test_units_come_from_the_file_and_can_be_overridden(tmp_path):
    mm = write_3dm(tmp_path / "mm.3dm", r.UnitSystem.Millimeters, k=1000.0)
    info = model3d.inspect(mm)
    assert info["scale_to_m"] == 0.001 and info["units_known"] and info["cell_m"] == 0.5
    _check_site(model3d.finish(mm, ROLES)["project"])

    none = write_3dm(tmp_path / "none.3dm", r.UnitSystem.Unset, k=1000.0)
    info = model3d.inspect(none)
    assert not info["units_known"] and any("units" in n for n in info["notes"])
    _check_site(model3d.finish(none, ROLES, scale_to_m=0.001)["project"])


def test_a_gap_in_the_mesh_does_not_let_water_out(tmp_path):
    path = write_3dm(tmp_path / "gap.3dm", hole=(30, 34, 10, 14))
    out = model3d.finish(path, ROLES)
    with Project.open(out["project"]) as p:
        dem = read_geotiff(p.path("terrain/existing.tif"))
        X, Y = dem.cell_centres()
        inside = (X > 30) & (X < 34) & (Y > 10) & (Y < 14)
        assert (dem.z[inside] != dem.nodata).all()
        assert dem.z[inside] == pytest.approx(ground_z(X[inside], Y[inside]), abs=0.05)
    assert out["qc"]["holes_filled_m2"] == pytest.approx(16, abs=4)
    assert any("gaps" in i for i in out["qc"]["issues"])


def test_a_boundary_curve_sets_the_site(tmp_path):
    path = write_3dm(tmp_path / "b.3dm", boundary=[(5, 5), (40, 5), (40, 35), (5, 35)])
    roles = roles_of(model3d.inspect(path))
    assert roles["Site boundary"] == "boundary"
    assert model3d.finish(path, roles)["qc"]["site_area_m2"] == pytest.approx(35 * 30, rel=0.03)


def test_a_surface_without_a_mesh_is_reported_not_guessed(tmp_path):
    f = r.File3dm()
    f.Objects.AddBrep(r.Brep.CreateFromBox(r.Box(r.BoundingBox(0, 0, 0, 10, 10, 1))))
    path = tmp_path / "nurbs.3dm"
    assert f.Write(str(path), 0)
    info = model3d.inspect(path)
    assert any("no saved mesh" in n for n in info["notes"])
    with pytest.raises(model3d.ModelError, match="ground"):
        model3d.finish(path, {L["layer"]: "ground" for L in info["layers"]})
    assert not (tmp_path / "nurbs.sponge").exists()   # a failed model leaves no project behind


def test_an_existing_project_is_never_replaced(tmp_path):
    path = write_3dm(tmp_path / "site.3dm")
    one = model3d.finish(path, ROLES)["project"]
    two = model3d.finish(path, ROLES)["project"]
    assert one.endswith("site.sponge") and two.endswith("site_2.sponge")


def test_a_wrong_file_says_so(tmp_path):
    bad = tmp_path / "bad.dae"
    bad.write_text("not xml")
    with pytest.raises(model3d.ModelError, match="COLLADA"):
        model3d.inspect(bad)
    with pytest.raises(model3d.ModelError, match="3dm"):
        model3d.inspect(tmp_path / "x.obj")


def test_a_proposed_design_runs_through_the_engine_and_needs_all_three(tmp_path):
    """From the three files to flow and ponding, through the routes the app calls."""
    c = TestClient(app)
    path = write_dae(tmp_path / "site.dae")
    info = c.post("/intake/model/inspect", json={"path": str(path)}).json()
    assert roles_of(info) == ROLES
    only_model = c.post("/intake/model/finish?wait=true", json={"model": str(path), "roles": roles_of(info)})
    assert only_model.status_code == 400 and "all three" in only_model.json()["detail"]
    survey = _survey_project(tmp_path)
    plan = _design_plan(tmp_path / "plan.dxf", (0, 0))
    job = c.post("/intake/model/finish?wait=true", json={"model": str(path), "roles": roles_of(info), "survey_project": survey,
                                                         "design_plan": str(plan)}).json()
    assert job["status"] == "done", job
    opened = c.post("/projects/open", json={"path": job["result"]["project"]}).json()
    assert opened["has_terrain"] and opened["from_model"] and opened["has_survey"]
    pid = opened["project"]
    assert {"Terrain", "Buildings", "Proposed contours", "Existing contours", "Plan wall"} <= {L["name"] for L in c.get(f"/projects/{pid}/site/layers").json()["layers"]}
    assert c.get(f"/projects/{pid}/site/ponds").status_code == 200
    assert c.get(f"/projects/{pid}/flow").json()["hotspots"]
    assert c.post("/intake/model/inspect", json={"path": str(tmp_path / "missing.dae")}).status_code == 400


def test_blocks_are_read_where_they_are_placed(tmp_path):
    """A building placed as a block: its geometry stands at the placement, on the block's layer."""
    f = r.File3dm()
    f.Settings.ModelUnitSystem = r.UnitSystem.Meters
    a = r.ObjectAttributes()
    a.LayerIndex = f.Layers.AddLayer("Terrain", (0, 0, 0, 255))
    f.Objects.AddMesh(rhino_mesh(*grid()), a)
    b = r.ObjectAttributes()
    b.LayerIndex = f.Layers.AddLayer("Buildings", (0, 0, 0, 255))
    idef = f.InstanceDefinitions.Add("Hall", "", "", "", r.Point3d(0, 0, 0), (rhino_mesh(*box(0, 0, 10, 10, 100, 106)),), (b,))
    f.Objects.AddInstanceObject(r.InstanceReference(f.InstanceDefinitions[idef].Id, r.Transform.Translation(45, 25, 0)), b)
    path = tmp_path / "blocks.3dm"
    assert f.Write(str(path), 0)
    with Project.open(model3d.finish(path, {"Terrain": "ground", "Buildings": "building"})["project"]) as p:
        dem = read_geotiff(p.path("terrain/existing.tif"))
        X, Y = dem.cell_centres()
        at = lambda x, y: dem.z[np.unravel_index(np.argmin(np.hypot(X - x, Y - y)), X.shape)]
        assert at(50, 30) == pytest.approx(106, abs=0.01)
        assert at(5, 5) < 101


def park_by_material(path):
    """As Rhino exports a park to COLLADA: every object called Brep, the materials tell the parts apart. A walled site
    with a 4 m gap, a bowl with a water surface over it, a check dam across a sloping swale, and the surroundings."""
    w, d = 60.0, 40.0
    ground, gq = grid()
    water = ([(14, 14, 100.1), (26, 14, 100.1), (26, 26, 100.1), (14, 26, 100.1)], [(0, 1, 2, 3)])
    plate = ([(-300, -300, 95), (300, -300, 95), (300, 300, 95), (-300, 300, 95)], [(0, 1, 2, 3)])

    def wall(x0, y0, x1, y1):   # upright faces only; the north wall has a gap at x 28-32
        return ([(x0, y0, 99), (x1, y1, 99), (x1, y1, 103), (x0, y0, 103)], [(0, 1, 2, 3)])

    walls = [wall(-0.5, -0.5, w + 0.5, -0.5), wall(w + 0.5, -0.5, w + 0.5, d + 0.5), wall(-0.5, d + 0.5, -0.5, -0.5),
             wall(-0.5, d + 0.5, 28, d + 0.5), wall(32, d + 0.5, w + 0.5, d + 0.5)]
    dam = wall(40, 5, 40, 15)
    parts = {"terrain": ("0.75 0.25 0.25 1", [(ground, gq)]), "wall": ("0 1 0 1", walls), "dam": ("0.7 0.7 0.7 1", [dam]),
             "water": ("0 0 0.75 1", [water]), "plate": ("0.98 0.98 0.98 1", [plate])}
    geos, nodes, mats, effs = "", "", "", ""
    i = 0
    for name, (col, meshes) in parts.items():
        effs += (f'<effect id="e{name}"><profile_COMMON><technique sid="c"><lambert><diffuse><color>{col}</color></diffuse>'
                 f'</lambert></technique></profile_COMMON></effect>')
        mats += f'<material id="m{name}" name="{name}"><instance_effect url="#e{name}"/></material>'
        for v, q in meshes:
            gid = f"g{i}"
            i += 1
            geos += dae_geometry(gid, v, q).replace("<triangles ", '<triangles material="s" ')
            nodes += (f'<node name="Brep"><instance_geometry url="#{gid}"><bind_material><technique_common>'
                      f'<instance_material symbol="s" target="#m{name}"/></technique_common></bind_material>'
                      f"</instance_geometry></node>")
    path.write_text(f'<?xml version="1.0"?><COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
                    f'<asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>'
                    f"<library_effects>{effs}</library_effects><library_materials>{mats}</library_materials>"
                    f"<library_geometries>{geos}</library_geometries>"
                    f'<library_visual_scenes><visual_scene id="S">{nodes}</visual_scene></library_visual_scenes>'
                    f'<scene><instance_visual_scene url="#S"/></scene></COLLADA>')
    return path


def test_a_sketchup_export_is_sorted_by_material_and_its_edge_lines_are_no_loss(tmp_path):
    """SketchUp names its parts group_0, instance_0 ... and draws every edge as lines."""
    text = park_by_material(tmp_path / "park.dae").read_text()
    nodes = iter(range(99))
    text = re.sub(r'(<node [^>]*?name=")[^"]*"', lambda m: f'{m.group(1)}instance_{next(nodes)}"', text)
    text = text.replace("</mesh>", '<lines count="1" material="M"><input semantic="VERTEX" source="#x" offset="0"/><p>0 1</p></lines></mesh>')
    path = tmp_path / "sketchup.dae"
    path.write_text(text)
    info = model3d.inspect(path)
    assert info["by_material"]
    assert not any("not read" in n for n in info["notes"])


def test_a_model_with_no_layers_is_sorted_by_material_and_suggested_from_its_shapes(tmp_path):
    info = model3d.inspect(park_by_material(tmp_path / "park.dae"))
    assert info["by_material"]
    roles = {L["layer"].split()[-1]: L["role"] for L in info["layers"]}
    assert roles == {"terrain": "ground", "wall": "boundary_wall", "dam": "barrier", "water": "water", "plate": "ignore"}
    assert next(L for L in info["layers"] if L["layer"].endswith("water"))["color"] == "#0000bf"
    assert info["max"][0] == pytest.approx(60.5)       # the size of the site, not of the plate around it


def test_a_boundary_wall_holds_the_water_and_its_gap_is_listed(tmp_path):
    path = park_by_material(tmp_path / "park.dae")
    info = model3d.inspect(path)
    out = model3d.finish(path, {L["layer"]: L["role"] for L in info["layers"]})
    q = out["qc"]
    assert q["site_area_m2"] == pytest.approx(60 * 40, rel=0.05)
    assert q["wall"]["height_m"] == pytest.approx(103 - ground_z(30, 39), abs=0.4)
    gaps = q["wall"]["openings"]
    assert len(gaps) == 1 and gaps[0]["x"] == pytest.approx(30, abs=2) and gaps[0]["y"] == pytest.approx(40, abs=2)
    with Project.open(out["project"]) as p:
        ans = p.read_json("site/outfall_answers.json")["all"]
        assert ans["state"] == "closed" and ans["edge_height_m"] > 0
        assert p.exists("terrain/barriers.tif")              # kept for the storm's coarser grid
        dem = read_geotiff(p.path("terrain/existing.tif"))
        X, Y = dem.cell_centres()
        at = lambda x, y: dem.z[np.unravel_index(np.argmin(np.hypot(X - x, Y - y)), X.shape)]
        assert at(*BOWL) == pytest.approx(ground_z(*BOWL), abs=0.05)   # the bed, not the water surface over it
        assert max(at(39.75, 10.25), at(40.25, 10.25)) == pytest.approx(103, abs=0.01)   # the check dam stands, though only upright faces
        hollow = [h for h in flowmap.load(p, True)["hotspots"] if h["kind"] == "ponding"]
        assert any(np.hypot(h["x"] - BOWL[0], h["y"] - BOWL[1]) < 2 and h["max_depth_m"] > 0.7 for h in hollow)
        view = p.read_json("site/survey_layers.json")
        assert view["from_model"] and not view["planting"]
        assert {L["role"] for L in view["layers"]} == {"ground", "boundary_wall", "barrier", "water", "contours"}


def test_thin_walls_stand_on_the_storms_coarser_grid(tmp_path):
    from spongepark.engine.sim2d.run import _coarsen, _keep_barriers

    path = park_by_material(tmp_path / "park.dae")
    out = model3d.finish(path, {L["layer"]: L["role"] for L in model3d.inspect(path)["layers"]})
    with Project.open(out["project"]) as p:
        dem = read_geotiff(p.path("terrain/existing.tif"))
        z, _ = _coarsen(dem.z, dem.z != dem.nodata, 2)
        r, c = int((dem.origin[1] - 10.0) / 1.0), int((40.0 - dem.origin[0]) / 1.0)   # the check dam, on the 1 m grid
        near = lambda g: g[r - 1:r + 2, c - 1:c + 2].max()
        assert near(z) < 103 - 0.1                # averaged, the dam is washed away
        _keep_barriers(z, p, 2)
        assert near(z) == pytest.approx(103, abs=0.01)


def _walled_site_with_storm(tmp_path):
    from spongepark.engine.hydrology.delineate import delineate
    from spongepark.engine.rainfall.presets import apply as rain

    path = park_by_material(tmp_path / "park.dae")
    project = model3d.finish(path, {L["layer"]: L["role"] for L in model3d.inspect(path)["layers"]})["project"]
    p = Project.open(project)
    rain(p, "hsr_imd_24h", None, "")
    delineate(p)
    return p


def test_an_opening_must_say_what_it_is_and_where(tmp_path):
    from spongepark.engine.site import openings

    with _walled_site_with_storm(tmp_path) as p:
        st = openings.status(p)
        assert not st["confirmed"] and len(st["gaps"]) == 1 and "existing site condition" in st["question"]
        ok = {"kind": "outlet", "origin": "design", "x": 30.0, "y": 39.0, "width_m": 4, "sill_m": 0}
        for bad, words in (({**ok, "origin": None}, "existing site condition"), ({**ok, "kind": None}, "outlet or an inlet"),
                           ({**ok, "x": 30.0, "y": 20.0}, "edge of the site"), ({**ok, "width_m": None}, "width")):
            with pytest.raises(ValueError, match=words):
                openings.save(p, {"openings": [bad]})
        st = openings.save(p, {"openings": [ok], "confirmed": True})
        assert st["confirmed"] and st["gaps"] == []
        assert st["openings"][0]["y"] == pytest.approx(40, abs=1.5)   # moved onto the edge


def test_an_outlet_lets_water_out_and_an_inlet_brings_it_in(tmp_path):
    from spongepark.engine.sim2d.run import prepare2d
    from spongepark.engine.sim2d.model import simulate
    from spongepark.engine.site import openings

    def run(p):
        i = prepare2d(p, "baseline", 25, 2.0)
        return simulate(i.dem.z, i.mask, i.dem.cell_size, i.rain_mm_hr * 8, i.rain_dt_s, 6 * 3600, i.n, i.f * 0,
                        i.elements, alpha=i.alpha, dt_max=i.dt_max, inlets=i.inlets).balance

    with _walled_site_with_storm(tmp_path) as p:
        closed = run(p)
        low = {"kind": "outlet", "origin": "site", "x": 0.5, "y": 20.0, "width_m": 6, "sill_m": 0}   # the low side of the slope
        openings.save(p, {"openings": [low], "confirmed": True})
        opened = run(p)
        assert closed["outflow_m3"] < 0.015 * closed["rainfall_m3"]   # rain on the wall tops runs off both ways
        assert opened["outflow_m3"] > 20 * max(closed["outflow_m3"], 1.0)
        inlet = {"kind": "inlet", "origin": "site", "x": 50.0, "y": 20.0, "area_m2": 1000, "runoff_pct": 50}
        openings.save(p, {"openings": [inlet], "confirmed": True})
        fed = run(p)
        assert fed["inlet_m3"] == pytest.approx(0.5 * 1000 * closed["rainfall_m3"] / (p.read_json("terrain/qc.json")["site_area_m2"]), rel=0.1)
        assert abs(fed["continuity_error_pct"]) < 1e-6


def test_an_outlet_level_is_given_on_the_survey_datum(tmp_path):
    from spongepark.engine.site import openings

    with _walled_site_with_storm(tmp_path) as p:
        lo, hi = openings.status(p)["ground_range_m"]
        base = {"kind": "outlet", "origin": "site", "x": 0.5, "y": 20.0, "width_m": 2}
        old = openings.save(p, {"openings": [{**base, "sill_m": 0.2}]})["openings"][0]      # an old row: above the ground
        ground = old["ground_m"]
        assert old["invert_m"] == pytest.approx(ground + 0.2, abs=1e-3) and old["sill_m"] == pytest.approx(0.2, abs=1e-3)
        below = openings.save(p, {"openings": [{**base, "invert_m": ground - 0.3}]})["openings"][0]   # a drain below it
        assert below["sill_m"] == pytest.approx(-0.3, abs=1e-3)
        if lo > openings.LEVEL_MARGIN_M:
            with pytest.raises(ValueError, match="not a level on this site's survey"):
                openings.save(p, {"openings": [{**base, "invert_m": 0}]})
        copy = {**below}
        rows = openings.save(p, {"openings": [below, copy]})["openings"]                    # a copy gets its own id
        assert len({r["id"] for r in rows}) == 2
        assert openings.outlet_levels(p) and min(openings.outlet_levels(p).values()) == pytest.approx(ground - 0.3, abs=1e-3)


def test_design_openings_stay_out_of_an_existing_site_run(tmp_path):
    from spongepark.engine.site import openings

    with _walled_site_with_storm(tmp_path) as p:
        rows = [{"kind": "inlet", "origin": "design", "x": 30, "y": 20, "area_m2": 10, "runoff_pct": 50}]
        openings.save(p, {"openings": rows})
        assert len(openings.active(p, "baseline")) == 1                 # a design model's project is all design
        p.path("site/model_source.json").unlink()
        assert openings.active(p, "baseline") == [] and len(openings.active(p, "design")) == 1


def test_rain_gardens_and_swales_soak_in_at_the_fact_sheet_rate(tmp_path):
    from spongepark.engine.hydrology.delineate import delineate
    from spongepark.engine.rainfall.presets import apply as rain
    from spongepark.engine.sim2d.run import prepare2d
    from spongepark.engine.site import ground

    path = write_3dm(tmp_path / "s.3dm")
    f = r.File3dm.Read(str(path))
    a = r.ObjectAttributes()
    a.LayerIndex = f.Layers.AddLayer("RG and BS", (0, 0, 0, 255))
    f.Objects.AddMesh(rhino_mesh(*box(30, 30, 40, 38, 100.2, 104)), a)
    f.Write(str(path), 0)
    info = model3d.inspect(path)
    roles = roles_of(info)
    assert roles["RG and BS"] == "nbs"
    out = model3d.finish(path, roles)
    assert out["qc"]["nbs_m2"] == pytest.approx(80, abs=10)
    with Project.open(out["project"]) as p:
        rain(p, "hsr_imd_24h", None, "")
        delineate(p)
        ground.apply(p, {"soil": "C", "paths": "paved", "covers": [{"cover": "grass", "condition": "good", "share_pct": 100}]})
        i = prepare2d(p, "baseline", 25, 1.0)
        X, Y = i.dem.cell_centres()
        rates = i.infil_fn(0, 0.0, 0.0)
        assert rates[np.unravel_index(np.argmin(np.hypot(X - 35, Y - 34)), X.shape)] == 25.0
        assert rates[np.unravel_index(np.argmin(np.hypot(X - 10, Y - 34)), X.shape)] < 25.0
        assert "HC 4.2" in i.infil_note
        view = {L["name"]: L for L in p.read_json("site/survey_layers.json")["layers"]}
        assert view["RG and BS"]["color"] == "#55803f".upper() and view["Terrain"]["color"] == "#8FB46C"   # what it is, not its paint


def test_the_compound_wall_stands_at_its_modelled_height(tmp_path):
    from scipy import ndimage

    from spongepark.engine.sim2d.run import prepare2d
    from spongepark.engine.site import outfalls

    with _walled_site_with_storm(tmp_path) as p:
        i = prepare2d(p, "baseline", 25, 1.0)
        ring = i.mask & ~ndimage.binary_erosion(i.mask, structure=np.ones((3, 3)), border_value=0)
        X, Y = i.dem.cell_centres()
        walled = ring & ~(np.hypot(X - 30, Y - 40) < 4)     # all but the 4 m gap
        assert np.median(i.dem.z[walled]) == pytest.approx(103, abs=0.01)   # the wall's top, not ground + one height
        for e in outfalls.status(p)["exits"]:
            assert e["edge_height_m"] == pytest.approx(103 - e["ground_m"], abs=0.05)


def _design_plan(path, off, wells=((20.0, 20.0), (50.0, 30.0))):
    """The design in plan, as drawn: inside a block, on the survey's coordinates, with contours that must not be used."""
    import ezdxf

    doc = ezdxf.new()
    b = doc.blocks.new("PLAN")
    for name in ("0.2.0_ Boundary Wall", "Recharge Wekk", "1.0.0. X_Levels_1M"):
        doc.layers.add(name)
    b.add_lwpolyline([(-0.5, -0.5), (60.5, -0.5), (60.5, 40.5), (-0.5, 40.5)], close=True, dxfattribs={"layer": "0.2.0_ Boundary Wall"})
    for x, y in wells:
        b.add_circle((x, y), 0.6, dxfattribs={"layer": "Recharge Wekk"})
    b.add_lwpolyline([(0, 0), (60, 40)], dxfattribs={"layer": "1.0.0. X_Levels_1M"})
    doc.modelspace().add_blockref("PLAN", (off[0], off[1]))
    doc.saveas(path)
    return path


def _survey_project(tmp_path):
    from spongepark.engine.io import intake
    from .test_survey_import import make_dxf

    drawing = make_dxf(tmp_path / "survey.dxf")
    links = {L["layer"]: L["proposed"] for L in intake.start(drawing)["layers"]}
    links.update({"BE-LEVEL": "", "MYSTERY 7": ""})
    return intake.finish(drawing, links, tmp_path / "survey.sponge")["project"]


def test_survey_design_and_model_make_the_design_model_with_proposed_contours(tmp_path):
    survey = _survey_project(tmp_path)
    with Project.open(survey) as sp:
        existing = read_geotiff(sp.path("terrain/existing.tif"))
    off = (existing.origin[0] + 15.0, existing.origin[1] - 55.0)
    plan = _design_plan(tmp_path / "plan.dxf", off)
    model = park_by_material(tmp_path / "park.dae")
    roles = {L["layer"]: L["role"] for L in model3d.inspect(model)["layers"]}
    out = model3d.finish(model, roles, tmp_path / "design.sponge", survey_project=survey, design_plan=plan)
    q = out["qc"]
    assert q["offset_m"][:2] == pytest.approx(list(off), abs=0.01)   # the wall on the plan's wall
    assert q["wells_from_plan"] == 2
    with Project.open(out["project"]) as p:
        dem = read_geotiff(p.path("terrain/existing.tif"))
        X, Y = dem.cell_centres()
        at = lambda x, y: dem.z[np.unravel_index(np.argmin(np.hypot(X - x, Y - y)), X.shape)]
        # the levels are the model's, moved as a whole: the bowl is still there, whatever the survey or the plan says
        assert at(BOWL[0] + off[0], BOWL[1] + off[1]) == pytest.approx(ground_z(*BOWL) + q["offset_m"][2], abs=0.05)
        assert p.exists("terrain/survey_existing.tif")
        layers = {L["name"]: L for L in p.read_json("site/survey_layers.json")["layers"]}
        assert layers["Proposed contours"]["visible"] and layers["Proposed contours"]["count"] > 0
        assert not layers["Existing contours"]["visible"]
        lows = [min(f["xyz"][2::3]) for f in layers["Proposed contours"]["features"]]
        assert min(lows) == pytest.approx(99.5 + q["offset_m"][2], abs=0.6)
        wells = p.read_geojson("site/wells.geojson")["features"]
        assert len(wells) == 2 and wells[0]["properties"]["drawn_diameter_m"] == 1.2 and wells[0]["properties"]["in_park"]
        src = p.read_json("site/model_source.json")
        assert src["design_plan"] == "plan.dxf" and src["survey_project"] == "survey.sponge"


def test_the_plans_contours_are_not_read(tmp_path):
    plan = model3d.read_plan(_design_plan(tmp_path / "plan.dxf", (0, 0)))
    assert plan["wall"][1][0] == pytest.approx(60.5)       # only the wall gives the extent, not the contour layer
    assert len(plan["wells"]) == 2
    with pytest.raises(model3d.ModelError, match="dxf"):
        model3d.read_plan(tmp_path / "plan.dwg")


def test_the_plan_says_which_nameless_material_is_the_swales(tmp_path):
    from shapely.geometry import box as rect

    model = model3d.read(park_by_material(tmp_path / "park.dae"))
    names = {n.split()[-1]: n for n in model.layers}
    roles = {names["terrain"]: "ground", names["water"]: "ground"}
    outlines = rect(13, 13, 27, 27)
    got = model3d._nbs_from_plan(model, roles, 1.0, np.zeros(3), outlines)
    assert got[names["water"]] == "nbs" and got[names["terrain"]] == "ground"   # mostly inside, though the terrain has as much there
    named = {**roles, names["terrain"]: "nbs"}     # the designer's own answer stands
    assert model3d._nbs_from_plan(model, named, 1.0, np.zeros(3), outlines) == named


def test_the_three_are_measured_against_each_other(tmp_path):
    survey = _survey_project(tmp_path)
    with Project.open(survey) as sp:
        origin = read_geotiff(sp.path("terrain/existing.tif")).origin
    off = (origin[0] + 15.0, origin[1] - 55.0)
    model = park_by_material(tmp_path / "park.dae")
    roles = {L["layer"]: L["role"] for L in model3d.inspect(model)["layers"]}
    out = model3d.finish(model, roles, tmp_path / "d.sponge", survey_project=survey, design_plan=_design_plan(tmp_path / "plan.dxf", off))
    a = out["qc"]["alignment"]
    assert a["plan_wall_to_model_wall_m"]["p95"] < 0.05     # drawn on the same wall
    assert 0 <= a["site_overlap"] <= 1 and a["ground_vs_survey_m"]["p05"] <= a["ground_vs_survey_m"]["p95"]
    assert out["qc"]["offset_m"][2] == pytest.approx(a["ground_vs_survey_m"]["median"] + out["qc"]["offset_m"][2], abs=0.05)
    assert model3d._align_notes({"plan_wall_to_model_wall_m": {"median": 3, "p95": 5}, "site_overlap": 0.5}) != []


def test_before_and_after_the_same_storm_on_both_and_where_runoff_is_not_collected(tmp_path):
    from spongepark.engine.project.parameters import Source
    from spongepark.engine.rainfall.presets import apply as rain
    from spongepark.engine.site import compare, ground, openings

    survey = _survey_project(tmp_path)
    answers = {"soil": "C", "paths": "paved", "covers": [{"cover": "grass", "condition": "good", "share_pct": 100}]}
    with Project.open(survey) as sp:
        rain(sp, "hsr_imd_24h", None, "")
        ground.apply(sp, answers)
        origin = read_geotiff(sp.path("terrain/existing.tif")).origin
        sp.save()
    off = (origin[0] + 15.0, origin[1] - 55.0)
    model = write_3dm(tmp_path / "d.3dm")
    f = r.File3dm.Read(str(model))
    a = r.ObjectAttributes()
    a.LayerIndex = f.Layers.AddLayer("RG and BS", (0, 0, 0, 255))
    f.Objects.AddMesh(rhino_mesh(*box(14, 14, 26, 26, 99.0, 100.3)), a)   # a basin at the bowl
    f.Write(str(model), 0)
    roles = roles_of(model3d.inspect(model))
    out = model3d.finish(model, roles, tmp_path / "design.sponge", survey_project=survey, design_plan=_design_plan(tmp_path / "plan.dxf", off))
    with Project.open(out["project"]) as p:
        assert p.exists("rainfall/return_periods.csv") and ground.load(p)["answers"] == answers   # answered once, for the survey
        assert compare.available(p)
        p.parameters.set("sim2d.cell_m", 2.0, "m", Source.DEFAULT, "a quick test")
        got = compare.run(p, 25)
        b, c = got["before"], got["after"]
        assert b["rain_m3"] > 0 and c["rain_m3"] > 0
        assert b["runoff_m3"] == pytest.approx(b["rain_m3"] - b["soaked_in_m3"], abs=0.2)
        assert b["not_collected_m2"] == pytest.approx(b["flood_m2"], rel=0.05)   # nothing collects it on the existing site
        assert c["not_collected_m2"] <= c["flood_m2"]
        assert isinstance(c["patches"], list) and "outside" not in c
        assert p.exists("comparison/rp25.json") and p.exists("comparison/rp25.png")
        names = {L["name"]: L for L in p.read_json("site/survey_layers.json")["layers"]}
        assert not names.get(compare.BEFORE_LAYER, {"visible": False})["visible"]


def test_before_and_after_needs_the_survey(tmp_path):
    from spongepark.engine.site import compare

    out = model3d.finish(write_3dm(tmp_path / "d.3dm"), ROLES, tmp_path / "x.sponge")
    with Project.open(out["project"]) as p:
        with pytest.raises(ValueError, match="survey"):
            compare.run(p, 25)
