"""Write the Phase 1 charts for an option from stored results."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from ..project.package import Project
from .charts import hydrographs, performance_curve, water_balance_bars


def _series(project: Project, option_id: str) -> dict:
    d = project.root / "options" / option_id / "results"
    out = {}
    for f in d.glob("rp*_timeseries.parquet"):
        out[int(f.stem[2:].split("_")[0])] = pd.read_parquet(f)
    return out


def write_charts(project: Project, option_id: str, out_dir: Path, baseline_id: str = "baseline") -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    opt = project.read_json(f"scenarios/{option_id}/results/summary.json")
    base = project.read_json(f"scenarios/{baseline_id}/results/summary.json")
    files.append(water_balance_bars({"Existing": base, f"Proposed ({option_id})": opt},
                                    out_dir / f"water_balance_{option_id}.png"))
    duration = max(v["storm"]["duration_hr"] for v in opt["return_periods"].values())
    files.append(hydrographs(_series(project, baseline_id), _series(project, option_id),
                             out_dir / f"hydrographs_{option_id}.png",
                             window_hr=(max(0.0, duration / 2 - 4), duration / 2 + 12)))
    rel = f"scenarios/{option_id}/results/performance_curve.json"
    if project.exists(rel):
        files.append(performance_curve(project.read_json(rel), out_dir / f"performance_curve_{option_id}.png",
                                       "Scaled manual layout (Phase 1)"))
    for f in files:
        dest = project.path(f"scenarios/{option_id}/results/{f.name}")
        dest.write_bytes(f.read_bytes())
    return files
