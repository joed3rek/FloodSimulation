"""Synthetic 1 ha sponge park used for tests and the end-to-end example.

All values here are ILLUSTRATIVE PLACEHOLDERS (not Bengaluru design data). The
site is a 100 m x 100 m park on a 2 % slope falling north to south, with a
street draining into it from the north.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from ..engine.project.package import Project
from ..engine.project.parameters import Source
from ..engine.terrain.raster import write_geotiff
from ..engine.terrain.synthetic import planar

X0, Y0 = 781000.0, 1434000.0  # SW corner, UTM 43N
ILLUSTRATIVE = "ILLUSTRATIVE PLACEHOLDER - replace with site data"


def _rect(x1: float, y1: float, x2: float, y2: float) -> Dict[str, Any]:
    pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    return {"type": "Polygon", "coordinates": [[(X0 + x, Y0 + y) for x, y in pts]]}


def _pt(x: float, y: float) -> Dict[str, Any]:
    return {"type": "Point", "coordinates": (X0 + x, Y0 + y)}


def _line(*pts: Tuple[float, float]) -> Dict[str, Any]:
    return {"type": "LineString", "coordinates": [(X0 + x, Y0 + y) for x, y in pts]}


def ground(y: float) -> float:
    """Ground elevation (m) at local northing y: 900 m at the south edge, rising 2 %."""
    return 900.0 + 0.02 * y


def _fc(features: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> Dict[str, Any]:
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": g, "properties": p} for g, p in features]}


RAINFALL_24H = pd.DataFrame(
    {"return_period_yr": [1, 2, 5, 10, 25, 50, 100], "depth_mm": [60, 85, 110, 130, 155, 175, 195]}
)


def site_layers() -> Dict[str, Dict[str, Any]]:
    subs = [
        (_rect(0, 60, 100, 100), dict(id="SC_N_LAWN", outlet="OUT1", pct_imperv=5, slope_pct=2, flow_length_m=40, land_cover="lawn", tr55_cover="open_space_fair")),
        (_rect(0, 35, 30, 60), dict(id="SC_COURT", outlet="OUT1", pct_imperv=95, slope_pct=1, flow_length_m=25, land_cover="court", tr55_cover="open_space_fair")),
        (_rect(30, 55, 100, 60), dict(id="SC_PATH", outlet="OUT1", pct_imperv=90, slope_pct=1.5, flow_length_m=5, land_cover="path", tr55_cover="open_space_fair")),
        (_rect(30, 35, 100, 55), dict(id="SC_MID_LAWN", outlet="OUT1", pct_imperv=5, slope_pct=2, flow_length_m=20, land_cover="lawn", tr55_cover="open_space_fair")),
        (_rect(0, 0, 100, 35), dict(id="SC_S_LAWN", outlet="OUT1", pct_imperv=10, slope_pct=2, flow_length_m=35, land_cover="lawn", tr55_cover="open_space_fair")),
    ]
    ext = [(_rect(0, 100, 100, 108), dict(id="EXT_STREET", outlet="OUT1", pct_imperv=100, slope_pct=1.5, flow_length_m=8, land_cover="road", tr55_cover="open_space_poor"))]
    soils = [
        (_rect(0, 50, 100, 108), dict(id="Z_SANDY_LOAM", max_rate_mm_hr=75, min_rate_mm_hr=20, decay_1_hr=4, dry_time_days=7,
                                       suction_mm=110, ksat_mm_hr=20, imd=0.3, source="default", note=ILLUSTRATIVE)),
        (_rect(0, 0, 100, 50), dict(id="Z_RED_LATERITE", max_rate_mm_hr=40, min_rate_mm_hr=8, decay_1_hr=4, dry_time_days=7,
                                     suction_mm=170, ksat_mm_hr=8, imd=0.25, source="default", note=ILLUSTRATIVE)),
    ]
    outfalls = [(_pt(50, 0), dict(id="OUT1", invert_elev_m=899.5, kind="FREE", note="Site outlet to storm water drain"))]
    context = [
        (_pt(20, 80), dict(id="T1", kind="tree", canopy_radius_m=5, species="Samanea saman")),
        (_pt(70, 85), dict(id="T2", kind="tree", canopy_radius_m=6, species="Pongamia pinnata")),
        (_pt(15, 20), dict(id="T3", kind="tree", canopy_radius_m=4, species="")),
        (_pt(85, 25), dict(id="T4", kind="tree", canopy_radius_m=5, species="", interception_capacity_mm=1.5)),
    ]
    boundary = [(_rect(0, 0, 100, 100), dict(id="SITE"))]
    return {
        "site/boundary.geojson": _fc(boundary),
        "site/subcatchments.geojson": _fc(subs),
        "site/external_catchment.geojson": _fc(ext),
        "site/soil_zones.geojson": _fc(soils),
        "site/outfalls.geojson": _fc(outfalls),
        "site/context.geojson": _fc(context),
    }


def manual_layout(with_wetland: bool = False) -> Dict[str, Any]:
    """Treatment train: rain gardens + bioswale -> detention pond -> recharge well -> retention pond/wetland -> outlet."""
    els = [
        (_rect(31, 40, 37, 50), dict(id="RG1", type="rain_garden", inflow_from=["SC_COURT"], outflow_to="DP1", source="designer")),
        (_rect(70, 50, 80, 54), dict(id="RG2", type="rain_garden", inflow_from=["SC_PATH"], outflow_to="DP1", source="designer")),
        (_line((50, 98), (50, 40)), dict(id="SW1", type="bioswale", top_width_m=3.0, inflow_from=["SC_N_LAWN", "EXT_STREET"],
                                         outflow_to="DP1", check_dam_spacing_m=12, source="designer")),
        (_rect(35, 15, 65, 30), dict(id="DP1", type="detention_pond", invert_elev_m=899.9, inflow_from=["SC_MID_LAWN", "SC_S_LAWN"],
                                     outflow_to="OUT1", overflow_to="RW1", source="designer")),
        (_pt(70, 20), dict(id="RW1", type="recharge_well", invert_elev_m=round(ground(20) - 6.0, 2), infiltration_rate_mm_hr=30.0,
                           overflow_to="SINK", source="designer",
                           notes="Strata infiltration rate is ILLUSTRATIVE; needs percolation test / borehole data.")),
    ]
    if with_wetland:
        els.append((_rect(72, 2, 98, 14), dict(id="CW1", type="constructed_wetland", invert_elev_m=899.6,
                                               outflow_to="OUT1", overflow_to="OUT1", cell_count=2, length_to_width=26 / 12,
                                               source="designer")))
        els[-2][1]["overflow_to"] = "CW1"
    else:
        els.append((_rect(72, 2, 98, 16), dict(id="RP1", type="retention_pond", invert_elev_m=898.6, overflow_to="OUT1", side_slope_h_v=3.0,
                                               source="designer")))
        els[-2][1]["overflow_to"] = "RP1"
    return _fc(els)


def populate(project: Project, with_dem: bool = True) -> None:
    """Write the synthetic site, rainfall and two manual options into ``project``."""
    for rel, fc in site_layers().items():
        project.write_geojson(rel, fc)
    RAINFALL_24H.to_csv(project.path("rainfall/return_periods.csv"), index=False)
    project.parameters.set("rainfall.input_kind", "24h_depth", "-", Source.DEFAULT,
                           note=f"Synthetic example rainfall: {ILLUSTRATIVE}", confirmed=False)
    if with_dem:
        dem = planar(size_m=(100, 100), cell_size=1.0, slope_pct=2.0, base_elev=900.0, origin=(X0, Y0 + 100))
        write_geotiff(dem, project.path("terrain/existing.tif"))
    project.write_geojson("options/manual/components.geojson", manual_layout(False))
    project.write_geojson("options/manual_wetland/components.geojson", manual_layout(True))
    project.history.log("example_populated", site="synthetic 1 ha park")
