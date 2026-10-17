"""Calibration against an observed event (Phase 8).

Inputs: a recorded rainfall event (``time_min`` + ``intensity_mm_hr`` or ``depth_mm``, e.g. a KSNDMC
gauge) and an observed series at the site (``time_hr`` + ``value``): outflow at the outfall
(``outflow_total_cms``) or the water depth in an element (``depth_<id>_m``), e.g. from a level logger
or timestamped photos of ponding.

Four multipliers on site surfaces are fitted with SWMM in the loop (bounded Powell search):
infiltration (rates, or the curve number's retention S), Manning's n, depression storage and
imperviousness. The objective is the Nash-Sutcliffe efficiency (NSE) of the simulated series at the
observation times. The project is labelled *calibrated* only when the NSE reaches
``calibration.min_nse``; the factors are then stored as site-measured parameters and every later run
uses them. Otherwise nothing changes and the report says why.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from ..pipeline import prepare_option
from ..project import Project, Source
from ..rainfall.hyetograph import from_user_csv
from ..site.model import Site
from .builder import CALIBRATION_KEYS, build_spec, render_inp
from .runner import run

log = logging.getLogger(__name__)
NAMES = list(CALIBRATION_KEYS)


def nse(obs: np.ndarray, sim: np.ndarray) -> float:
    d = float(np.sum((obs - obs.mean()) ** 2))
    return 1.0 - float(np.sum((obs - sim) ** 2)) / d if d > 0 else float("nan")


def _simulate(project: Project, option_id: str, storm, factors: Dict[str, float], target: str,
              workdir: Path) -> pd.DataFrame:
    params = project.parameters.model_copy(deep=True)
    for k, v in factors.items():
        params.set(CALIBRATION_KEYS[k], float(v), source=Source.DEFAULT, note="calibration trial", confirmed=False)
    site = Site.load(project, option_id)
    elements = [] if option_id == "baseline" else prepare_option(project, option_id, site)[0]
    spec = build_spec(site, elements, params, option_id)
    inp = workdir / "event.inp"
    inp.write_text(render_inp(spec, site, params, {0: storm}, 0, f"calibration {option_id}"), encoding="utf-8")
    res = run(spec, inp, int(params.value("sim.sample_step_s")))
    ts = res.timeseries
    if target not in ts.columns:
        raise ValueError(f"'{target}' is not a model output; choose one of: {', '.join(ts.columns[1:])}.")
    return ts[["time_hr", target]]


def calibrate(project: Project, option_id: str, rainfall_csv: Path, observed_csv: Path, target: str,
              max_evaluations: int = 80, apply: bool = True) -> Dict[str, Any]:
    from scipy.optimize import minimize

    P = project.parameters
    storm = from_user_csv(Path(rainfall_csv), 0, float(P.value("rainfall.time_step_min")))
    obs = pd.read_csv(observed_csv, comment="#")
    if not {"time_hr", "value"} <= set(obs.columns):
        raise ValueError("observed CSV needs columns time_hr, value.")
    t_obs, v_obs = obs["time_hr"].to_numpy(float), obs["value"].to_numpy(float)
    bounds = P.value("calibration.bounds")
    lo = np.log([bounds[n][0] for n in NAMES])
    hi = np.log([bounds[n][1] for n in NAMES])
    work = Path(tempfile.mkdtemp(prefix="spcal_"))
    history = []

    def series(f: Dict[str, float]) -> np.ndarray:
        ts = _simulate(project, option_id, storm, f, target, work)
        return np.interp(t_obs, ts["time_hr"].to_numpy(), ts[target].to_numpy())

    def objective(x: np.ndarray) -> float:
        f = dict(zip(NAMES, np.exp(np.clip(x, lo, hi))))
        e = nse(v_obs, series(f))
        history.append({**f, "nse": e})
        return -e if np.isfinite(e) else 1e6

    start = {n: float(P.value_or(CALIBRATION_KEYS[n], 1.0)) for n in NAMES}
    sim0 = series({n: 1.0 for n in NAMES})
    x0 = np.clip(np.log([start[n] for n in NAMES]), lo, hi)
    res = minimize(objective, x0, method="Powell", bounds=list(zip(lo, hi)),
                   options={"maxfev": max_evaluations, "xtol": 1e-3, "ftol": 1e-4})
    best = dict(zip(NAMES, [float(v) for v in np.exp(np.clip(res.x, lo, hi))]))
    sim1 = series(best)
    nse0, nse1 = nse(v_obs, sim0), nse(v_obs, sim1)
    vol = lambda s: float(np.trapz(s, t_obs * 3600))  # noqa: E731
    min_nse = float(P.value("calibration.min_nse"))
    accepted = bool(np.isfinite(nse1) and nse1 >= min_nse)
    report = {
        "option_id": option_id, "target": target, "rainfall_event": str(rainfall_csv), "observed": str(observed_csv),
        "event_depth_mm": storm.depth_mm, "factors": best, "nse_uncalibrated": nse0, "nse_calibrated": nse1,
        "volume_error_pct": 100 * (vol(sim1) - vol(v_obs)) / vol(v_obs) if vol(v_obs) else None,
        "evaluations": len(history), "min_nse": min_nse, "accepted": accepted,
        "note": ("factors stored; every run now uses them" if accepted and apply else
                 "not applied" if not apply else
                 f"NSE {nse1:.2f} below {min_nse}: the model stays uncalibrated (check the data, or the model structure)"),
    }
    if accepted and apply:
        for n, v in best.items():
            P.set(CALIBRATION_KEYS[n], round(v, 4), source=Source.SITE_MEASURED,
                  note=f"calibrated on {Path(rainfall_csv).name} / {Path(observed_csv).name} ({target}), NSE {nse1:.2f}")
        project.manifest.calibration_status = (f"calibrated against one event ({Path(observed_csv).name}, {target}): "
                                               f"NSE {nse1:.2f}")
    project.write_json("calibration/report.json", report)
    project.write_json("calibration/history.json", history)
    _plot(project, t_obs, v_obs, sim0, sim1, target, nse0, nse1)
    project.history.log("calibrate", option=option_id, target=target, nse=nse1, accepted=accepted)
    return report


def _plot(project: Project, t, obs, s0, s1, target, n0, n1) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4), dpi=130)
    ax.plot(t, obs, "o", ms=3, color="#14201f", label="observed")
    ax.plot(t, s0, color="#b9c2c0", lw=1.5, label=f"uncalibrated (NSE {n0:.2f})")
    ax.plot(t, s1, color="#2a78d6", lw=2, label=f"calibrated (NSE {n1:.2f})")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel(target)
    ax.legend(frameon=False, fontsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    project.path("calibration").mkdir(exist_ok=True)
    fig.savefig(project.path("calibration/calibration.png"))
    plt.close(fig)
