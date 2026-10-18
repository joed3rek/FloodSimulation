"""Rainfall tables that come with the engine, each with its source (``data/presets.json``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from ..project import Project, Source
from .tables import STANDARD_RPS, RainfallTable

DATA = Path(__file__).with_name("data") / "presets.json"


def presets() -> Dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def apply(project: Project, preset: Optional[str] = None, rows: Optional[List[Dict[str, float]]] = None,
          source: str = "") -> Dict[str, Any]:
    """Set the project's rainfall table (a preset or rows given), choose the return periods the table has,
    and make the design storms. Returns the storms (depth, peak) and what was left out."""
    from ..pipeline import make_hyetographs

    label = source
    if preset:
        p = presets().get(preset)
        if p is None:
            raise ValueError(f"no rainfall preset '{preset}'.")
        rows, label = p["rows"], f"{p['label']} ({p['source']})"
    if not rows:
        raise ValueError("give a preset or the rainfall rows.")
    table = RainfallTable.from_frame(pd.DataFrame(rows))
    table.to_csv(project.path("rainfall/return_periods.csv"))
    have = set(table.return_periods)
    rps = [rp for rp in STANDARD_RPS if rp in have]
    missing = [rp for rp in STANDARD_RPS if rp not in have]
    P = project.parameters
    P.set("rainfall.input_kind", table.kind(), "-", Source.SITE_MEASURED, note=label[:300])
    P.set("project.return_periods", rps, "yr", Source.DESIGNER,
          note="the return periods the rainfall table gives" + (f" (no {missing} yr in it)" if missing else ""))
    P.confirm("project.return_periods")
    storms = make_hyetographs(project)
    project.history.log("rainfall", source=label[:200], return_periods=rps)
    return {"source": label, "kind": table.kind(), "return_periods": rps, "missing": missing,
            "method": P.value("rainfall.hyetograph_method"),
            "storms": [{"return_period_yr": rp, "depth_mm": round(h.depth_mm, 1), "peak_mm_hr": round(h.peak_mm_hr, 1),
                        "duration_hr": h.duration_hr} for rp, h in sorted(storms.items())]}


def current(project: Project) -> Optional[Dict[str, Any]]:
    if not project.exists("rainfall/return_periods.csv"):
        return None
    df = pd.read_csv(project.path("rainfall/return_periods.csv"))
    P = project.parameters
    q = P.get("rainfall.input_kind")
    return {"source": q.note if q is not None else "", "rows": df.to_dict(orient="records"),
            "return_periods": P.value("project.return_periods"), "method": P.value("rainfall.hyetograph_method")}
