"""Shared helpers: tiny synthetic projects with known analytical behaviour."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from spongepark.engine.project import Project, Source
from spongepark.engine.rainfall import Hyetograph
from spongepark.engine.nbs.components import save_elements_fc

X0, Y0 = 500000.0, 1400000.0


def rect(x1, y1, x2, y2) -> Dict[str, Any]:
    pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    return {"type": "Polygon", "coordinates": [[(X0 + x, Y0 + y) for x, y in pts]]}


def fc(items: List[tuple]) -> Dict[str, Any]:
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": g, "properties": p} for g, p in items]}


def constant_storm(intensity_mm_hr: float, hours: float, dt_min: float = 5.0, rp: int = 1) -> Hyetograph:
    n = int(round(hours * 60 / dt_min))
    return Hyetograph(rp, dt_min, np.full(n, float(intensity_mm_hr)), "constant")


HORTON = dict(max_rate_mm_hr=50, min_rate_mm_hr=10, decay_1_hr=4, dry_time_days=7, max_volume_mm=0)


def make_project(
    tmp_path: Path,
    subcatchments: List[tuple],
    elements: Optional[List[tuple]] = None,
    soil: Optional[Dict[str, Any]] = None,
    boundary: Optional[Dict[str, Any]] = None,
    outfall_elev: float = 99.0,
    post_storm_hr: float = 6.0,
) -> Project:
    p = Project.create(tmp_path / "t.sponge", "test", overwrite=True)
    p.write_geojson("site/subcatchments.geojson", fc(subcatchments))
    if boundary:
        p.write_geojson("site/boundary.geojson", fc([(boundary, {"id": "B"})]))
    p.write_geojson("site/soil_zones.geojson", fc([(rect(-1000, -1000, 1000, 1000), {"id": "Z", **(soil or HORTON)})]))
    p.write_geojson("site/outfalls.geojson",
                    fc([({"type": "Point", "coordinates": (X0, Y0 - 5)}, {"id": "OUT", "invert_elev_m": outfall_elev})]))
    if elements is not None:
        save_elements_fc(p, "opt", fc(elements))
    p.parameters.set("evaporation.rate_mm_day", 0.0, source=Source.USER)
    p.parameters.set("sim.post_storm_hr", post_storm_hr, source=Source.USER)
    p.parameters.set("sim2d.engine", "builtin", source=Source.USER)   # tests do not depend on Itzi being installed
    return p


@pytest.fixture
def tmp_project(tmp_path):
    projects = []

    def _make(*a, **k):
        pr = make_project(tmp_path, *a, **k)
        projects.append(pr)
        return pr

    yield _make
    for pr in projects:
        pr.close()
