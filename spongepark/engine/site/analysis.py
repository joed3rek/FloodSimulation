"""Analyse the existing site: where water runs and collects, and how the existing park handles each storm.

Run by the designer (Analyse > Analyse site) once the site model is confirmed and Site setup is answered:

- the drainage is redone on the ground as it now stands (ponds cut in, existing wells as sinks), then the
  flow lines, arrows, ponding hotspots and exits (:mod:`..hydrology.flowmap`);
- SWMM runs the existing site (the baseline) for every design storm, with the rainfall and the ground answers.

The 2D flood model is not part of it: Simulate runs every storm afterwards, side by side (:func:`flood_storms`).

``site/analysis.json`` records that it was run and what with. Changing Site setup (rainfall, ground, ponds,
wells) clears it, so the app shows the analysis as out of date until it is run again.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List

from ..project import Project
from ..project.schema import utcnow

log = logging.getLogger(__name__)
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
    shutil.rmtree(project.path("scenarios/baseline/sim2d"), ignore_errors=True)   # the old Site setup's water
    rec = {"when": utcnow(), "flow": flow["summary"], "storms": storms is not None,
           "missing": [k for k, v in need.items() if not v]}
    project.write_json(REL, rec)
    project.history.log("site_analysed", storms=storms is not None)
    return {**rec, "baseline": storms}


def design_storms(project: Project) -> List[int]:
    """The storms SWMM has run for the existing site, which Simulate floods."""
    rel = "scenarios/baseline/results/summary.json"
    return sorted(int(rp) for rp in project.read_json(rel)["return_periods"]) if project.exists(rel) else []


def flood_state(storms: List[int]) -> Dict[str, Any]:
    """How the storms behind the app are getting on, for the app to show."""
    return {"running": bool(storms), "total": len(storms), "done": [], "failed": []}


def flood_storms(project: Project, storms: List[int], stop: threading.Event, state: Dict[str, Any], gpu: bool = False) -> None:
    """The 2D flood model for each storm, side by side, one low-priority process each, until done or ``stop`` is set
    (which ends them at once). With ``gpu`` the graphics card takes the biggest storms, one at a time, and the CPU the
    rest; a storm that fails on the card runs on the CPU. ``state`` follows along; the project's state files must be
    saved first."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(Path(__file__).resolve().parents[3]), os.environ.get("PYTHONPATH", "")])}
    flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == "win32" else 0   # the app stays smooth
    workers = max(1, min(len(storms), (os.cpu_count() or 2) // 2))
    waiting, running, card = sorted(storms), {}, None
    if gpu:
        workers = max(1, workers - 1)
    retried = set()
    try:
        while (waiting or running) and not stop.is_set():
            while waiting and (len(running) - (card is not None) < workers or (gpu and card is None)):
                on_card = gpu and card is None
                rp = waiting.pop() if on_card else waiting.pop(0)
                if on_card:
                    card = rp
                err = tempfile.TemporaryFile()
                running[rp] = (subprocess.Popen(
                    [sys.executable, "-m", "spongepark.engine.sim2d.flood_worker", str(os.getpid()), str(project.root), "baseline", str(rp),
                     "gpu" if on_card else "builtin"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err, env=env, creationflags=flags), err)
            for rp, (proc, err) in list(running.items()):
                if proc.poll() is None:
                    continue
                del running[rp]
                was_card, card = card == rp, None if card == rp else card
                if proc.returncode == 0:
                    state["done"].append(rp)
                elif was_card and rp not in retried:
                    log.warning("the %s-year storm failed on the graphics card; the CPU takes it", rp)
                    retried.add(rp)
                    gpu = False   # the card is not usable: every storm left goes to the CPU
                    waiting.insert(0, rp)
                else:   # the flow and SWMM results still stand; the map says which storm has no water
                    err.seek(0)
                    log.error("2D flood run failed for the %s-year storm: %s", rp, err.read().decode(errors="replace")[-2000:])
                    state["failed"].append(rp)
                err.close()
            stop.wait(0.5)
    finally:
        for proc, err in running.values():
            _kill(proc)
            err.close()


def _kill(proc: subprocess.Popen) -> None:
    """End a storm's process and what it started (a virtual environment's python.exe starts the real one)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.kill()
    proc.wait()


def flood_finished(project: Project, state: Dict[str, Any]) -> None:
    """Every storm has run: note it in the project's history (each storm's own summary holds its results)."""
    project.history.log("site_flood_run", storms=state["done"], failed=state["failed"])


def stale(project: Project) -> None:
    """Site setup changed: the analysis no longer matches it."""
    if project.exists(REL):
        project.path(REL).unlink()
