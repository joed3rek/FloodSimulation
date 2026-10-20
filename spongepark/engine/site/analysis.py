"""Analyse the existing site: where water runs and collects, and how the existing park handles each storm.

Run by the designer (Analyse > Analyse site) once the site model is confirmed and Site setup is answered:

- the drainage is redone on the ground as it now stands (ponds cut in, existing wells as sinks), then the
  flow lines, arrows, ponding hotspots and exits (:mod:`..hydrology.flowmap`);
- SWMM runs the existing site (the baseline) for every design storm, with the rainfall and the ground answers.

``site/analysis.json`` records that it was run and what with. Changing Site setup (rainfall, ground, ponds,
wells) clears it, so the app shows the analysis as out of date until it is run again.
"""

from __future__ import annotations

from typing import Any, Dict

from ..project import Project
from ..project.schema import utcnow

REL = "site/analysis.json"


def ready(project: Project) -> Dict[str, bool]:
    """What the storm part needs: the design storms and the ground (TR-55 answers or soil zones)."""
    soils = project.exists("site/soil_zones.geojson") and bool(project.read_geojson("site/soil_zones.geojson")["features"])
    return {"rainfall": project.exists("rainfall/return_periods.csv"),
            "ground": project.exists("site/ground.json") or soils}


def run(project: Project) -> Dict[str, Any]:
    from ..hydrology import flowmap
    from ..hydrology.delineate import delineate
    from ..pipeline import make_hyetographs, run_option

    delineate(project)
    flow = flowmap.analyse(project)
    need = ready(project)
    storms = None
    if all(need.values()):
        make_hyetographs(project)
        storms = run_option(project, "baseline")
    rec = {"when": utcnow(), "flow": flow["summary"], "storms": storms is not None,
           "missing": [k for k, v in need.items() if not v]}
    project.write_json(REL, rec)
    project.history.log("site_analysed", storms=storms is not None)
    return {**rec, "baseline": storms}


def stale(project: Project) -> None:
    """Site setup changed: the analysis no longer matches it."""
    if project.exists(REL):
        project.path(REL).unlink()
