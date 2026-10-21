"""Ponding hotspots fill with each storm's runoff: bigger storms fill hollows more, up to the brim, then spill."""

from spongepark.engine.hydrology.flowmap import fill

# a hollow 0.3 m deep holding 30 m3 when full: [height above the deepest point, volume, wet area]
STAGE = [[0.0, 0.0, 0.0], [0.1, 2.0, 40.0], [0.2, 10.0, 100.0], [0.3, 30.0, 150.0]]


def test_fill_grows_with_the_storm_then_spills():
    small, mid, big = fill(STAGE, 1.0), fill(STAGE, 10.0), fill(STAGE, 50.0)
    assert 0 < small["max_depth_m"] < mid["max_depth_m"] < big["max_depth_m"] == 0.3
    assert mid["volume_m3"] == 10.0 and mid["area_m2"] == 100.0 and not mid["full"]
    assert big["full"] and big["volume_m3"] == 30.0 and big["spill_m3"] == 20.0


def test_no_runoff_no_pool():
    assert fill(STAGE, 0.0) == {"volume_m3": 0.0, "max_depth_m": 0.0, "area_m2": 0.0, "full": False, "spill_m3": 0.0}
