"""Full evaluation of one layout: generate + grade + rebuild (Phase 4), then SWMM for every return period.

This is the only source of the numbers the optimiser reports: surrogate predictions are used to
choose which layouts to evaluate, never as results.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any, Dict, List, Optional

import numpy as np

from ..layout.generate import LayoutError, generate
from ..pipeline import PipelineError, compare, run_option
from ..project import Project
from .space import Space

log = logging.getLogger(__name__)


def evaluate(project: Project, space: Space, x: np.ndarray, option_id: str = "_eval",
             keep: bool = False) -> Dict[str, Any]:
    """Metrics of the layout at ``x`` from SWMM. ``feasible`` is False when no valid layout exists."""
    types, ov = space.decode(x)
    row: Dict[str, Any] = {"x": [float(v) for v in x], "types": types, "overrides": ov, "feasible": False}
    if not types:
        row["reason"] = "no component type included"
        return row
    try:
        rep = generate(project, option_id, types, ov)
        run_option(project, option_id)
        cmp_ = compare(project, option_id)
    except (LayoutError, PipelineError) as ex:
        row["reason"] = str(ex)[:300]
        _cleanup(project, option_id, keep)
        return row
    summ = project.read_json(f"options/{option_id}/results/summary.json")
    per_rp = {}
    max_dd = 0.0
    for r in cmp_["rows"]:
        rp = str(r["return_period_yr"])
        per_rp[rp] = {
            "rainfall_mm": r["rainfall_mm"],
            "retained_pct": r["option_retained_pct"],
            "baseline_retained_pct": r["baseline_retained_pct"],
            "peak_cms": r["option_peak_cms"],
            "peak_ratio": r["option_peak_cms"] / r["baseline_peak_cms"] if r["baseline_peak_cms"] else 1.0,
            "outflow_m3": r["option_outflow_m3"],
            "fully_retained": r["fully_retained"],
            "continuity_ok": not r["flags"],
        }
        for e in summ["return_periods"][rp]["elements"]:
            dd = e.get("drawdown_hr")
            if dd is not None and np.isfinite(dd):
                max_dd = max(max_dd, float(dd))
    row.update(
        feasible=True,
        area_pct=float(rep["intervention_area_pct"]),
        cut_m3=float(rep["cut_total_m3"]),
        n_elements=len(rep["elements"]),
        element_types={t: sum(e["type"] == t for e in rep["elements"]) for t in space.types},
        max_drawdown_hr=max_dd,
        design_retention_storm_yr=cmp_["design_retention_storm_yr"],
        per_rp=per_rp,
        skipped=rep["skipped"],
        swmm_verified=True,
    )
    _cleanup(project, option_id, keep)
    return row


def _cleanup(project: Project, option_id: str, keep: bool) -> None:
    if keep:
        return
    shutil.rmtree(project.option_dir(option_id), ignore_errors=True)
    tif = project.path(f"terrain/graded_{option_id}.tif")
    if tif.exists():
        tif.unlink()


def objectives(row: Dict[str, Any], mode: str, weights: Dict[str, float], target_rp: Optional[int],
               max_drawdown_hr: float, tol_fraction: float) -> tuple:
    """(objectives to minimise, constraints <= 0) from a SWMM-evaluated row.

    forward: maximise weighted retention, minimise weighted peak ratio and cut volume.
    inverse: minimise intervention area and cut volume, subject to retaining ``target_rp`` fully."""
    if not row.get("feasible"):
        n_obj = 3 if mode == "forward" else 2
        return [1e6] * n_obj, [1e6, 1e6]
    w = {rp: weights.get(rp, 1.0) for rp in row["per_rp"]}
    tw = sum(w.values()) or 1.0
    retained = sum(w[rp] * v["retained_pct"] for rp, v in row["per_rp"].items()) / tw
    peak = sum(w[rp] * v["peak_ratio"] for rp, v in row["per_rp"].items()) / tw
    g_dd = row["max_drawdown_hr"] - max_drawdown_hr
    if mode == "forward":
        return [-retained, peak, row["cut_m3"]], [g_dd, -1.0]
    t = row["per_rp"].get(str(target_rp))
    if t is None:
        raise ValueError(f"the {target_rp}-yr storm was not run; add it to project.return_periods.")
    g_target = 100.0 - t["retained_pct"] - 100 * tol_fraction  # same tolerance as `compare` uses
    return [row["area_pct"], row["cut_m3"]], [g_dd, g_target]
