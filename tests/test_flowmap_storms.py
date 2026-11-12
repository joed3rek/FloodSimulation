"""Ponding hotspots fill with each storm's runoff: bigger storms fill hollows more, up to the brim, then spill."""

import numpy as np

from spongepark.engine.hydrology.flowmap import fill, route_hollows
from spongepark.engine.site.outfalls import held_cells

# a hollow 0.3 m deep holding 30 m3 when full: [height above the deepest point, volume, wet area]
STAGE = [[0.0, 0.0, 0.0], [0.1, 2.0, 40.0], [0.2, 10.0, 100.0], [0.3, 30.0, 150.0]]


def test_fill_grows_with_the_storm_then_spills():
    small, mid, big = fill(STAGE, 1.0), fill(STAGE, 10.0), fill(STAGE, 50.0)
    assert 0 < small["max_depth_m"] < mid["max_depth_m"] < big["max_depth_m"] == 0.3
    assert mid["volume_m3"] == 10.0 and mid["area_m2"] == 100.0 and not mid["full"]
    assert big["full"] and big["volume_m3"] == 30.0 and big["spill_m3"] == 20.0


def test_no_runoff_no_pool():
    assert fill(STAGE, 0.0) == {"volume_m3": 0.0, "max_depth_m": 0.0, "area_m2": 0.0, "full": False, "spill_m3": 0.0}


def _hollow(id_, area, spills_to=None, stage=STAGE):
    return {"id": id_, "draining_area_m2": area, "spills_to": spills_to, "stage": stage}


def test_spill_runs_on_to_the_next_hollow_and_no_water_is_counted_twice():
    # 1000 m2 drains to A, whose spill runs to B; B's own ground is a further 500 m2. 100 mm of runoff: 150 m3 in all
    big = [[0.0, 0.0, 0.0], [1.0, 500.0, 500.0]]
    got = route_hollows([_hollow("B", 1500.0, stage=big), _hollow("A", 1000.0, "B")], 100.0)
    assert got["A"]["volume_m3"] == 30.0 and got["A"]["spill_m3"] == 70.0
    assert got["B"]["volume_m3"] == 120.0           # 50 m3 of its own and 70 m3 from A
    assert got["A"]["volume_m3"] + got["B"]["volume_m3"] == 150.0


def test_a_hollow_upstream_that_holds_it_all_leaves_only_the_own_ground_for_the_next():
    big = [[0.0, 0.0, 0.0], [1.0, 500.0, 500.0]]
    got = route_hollows([_hollow("A", 100.0, "B"), _hollow("B", 200.0, stage=big)], 100.0)
    assert got["A"]["volume_m3"] == 10.0 and got["A"]["spill_m3"] == 0.0
    assert got["B"]["volume_m3"] == 10.0


def test_water_held_at_an_exit_reaches_only_the_ground_connected_to_the_exit():
    # low ground by the exit at the left, a ridge, then a separate hollow as low as the exit's water
    z = np.array([[1.0, 1.0, 3.0, 1.0, 3.0]])
    wet = held_cells(np.ones_like(z, dtype=bool), z, 1.5, 0, 0)
    assert wet.tolist() == [[True, True, False, False, False]]
    wet = held_cells(np.ones_like(z, dtype=bool), z, 3.0, 0, 0)
    assert wet.tolist() == [[True, True, True, True, True]]


def test_a_hollow_knows_the_ground_that_drains_to_it():
    import numpy as np

    from spongepark.engine.hydrology import flowmap
    from spongepark.engine.hydrology import flow as fl

    # a plane falling to the east into a pit near the east edge
    n = 30
    x, y = np.meshgrid(np.arange(n) + 0.5, n - np.arange(n) - 0.5)
    z = 10.0 - 0.1 * x
    hollow = np.zeros((n, n), bool)
    hollow[14:17, 25:28] = True
    z[hollow] -= 1.0
    mask = np.ones((n, n), bool)
    dirs = fl.d8_directions(fl.fill_sinks(z, mask), mask)
    out = flowmap.feeding_ground(dirs, mask, hollow, z, x, y, 1.0, (0.0, float(n)))
    assert out["feeders"], "the ways down to the hollow"
    first = out["feeders"][0]
    assert first[0] < first[-3]   # runs east, downhill, towards the hollow
    assert 25 <= first[-3] <= 28 and 14 <= n - first[-2] <= 17   # and ends in it
    xs = out["catchment"][0::2]
    assert min(xs) < 20 and max(xs) <= 30


def test_water_held_at_a_closed_exit_carries_the_ground_that_drains_to_it():
    from spongepark.engine.hydrology.flowmap import _held_at_exit
    from spongepark.engine.terrain.raster import DEM

    # a 20 x 20 m slope falling to the west edge, where the closed exit is; all of it drains there
    z = np.tile(np.linspace(100.0, 101.9, 20), (20, 1))
    dem = DEM(z=z, cell_size=1.0, origin=(0.0, 20.0))
    ex = {"id": "OUT_1", "x": 0.5, "y": 10.5, "z": 100.0, "edge_height_m": 0.3}
    sub = {"geometry": {"type": "Polygon", "coordinates": [[(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]]},
           "properties": {"id": "S1", "outlet": "OUT_1"}}
    results = {"elements": [{"id": "EDGE_1", "max_ponding_depth_m": 0.3}],
               "return_periods": {"10": {"elements": [{"id": "EDGE_1", "max_depth_m": 0.2, "overflow_m3": 0.0}]}}}
    held = _held_at_exit(ex, results, dem, [sub])
    assert not held["needs_analysis"] and "outline" in held["storms"]["10"]
    assert abs(held["draining_area_m2"] - 400.0) < 5           # the whole subcatchment
    assert len(held["catchment"]) >= 8                           # x, y pairs of its outline
