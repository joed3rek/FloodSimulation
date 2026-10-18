"""Itzi (Courty et al., GPL-2.0) as the 2D surface flood model, run as a separate process.

Itzi solves the local inertial shallow water equations on the grid with rain on every cell and
infiltration. It needs Python 3.12+, so it runs in its own environment (for example the Python that comes
with QGIS, with itzi installed beside it): ``spongepark itzi setup`` writes a launcher for it, and the
engine finds it through ``SPONGEPARK_ITZI_PYTHON`` or the default launcher path. Running it as a separate
program also keeps its GPL licence apart from the engine.

The park is given on a rectangular grid: outside the park the ground is the display base (lower than the
park's edge, see ``terrain.extend``), it gets no rain and no infiltration, and the outer edge of the grid is
an open boundary, so water that leaves the park runs off and out. Volumes are counted for the park.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

from .model import Result2D

log = logging.getLogger(__name__)

DEFAULT_LAUNCHER = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "spongepark" / "itzi-python.bat"
WORKER = Path(__file__).with_name("itzi_worker.py")


class ItziError(RuntimeError):
    pass


def launcher() -> Optional[Path]:
    """The command that runs Itzi's Python, or None when Itzi is not set up."""
    p = os.environ.get("SPONGEPARK_ITZI_PYTHON")
    cand = Path(p) if p else DEFAULT_LAUNCHER
    return cand if cand.exists() else None


def available() -> bool:
    return launcher() is not None


def setup(qgis_root: Path, target: Optional[Path] = None) -> Path:
    """Install Itzi beside a QGIS (or OSGeo4W) Python 3.12+ and write the launcher. QGIS is not changed:
    Itzi and its packages go to their own folder, which the launcher puts first on the Python path."""
    qgis_root = Path(qgis_root)
    env = qgis_root / "bin" / "o4w_env.bat"
    if not env.exists() or not (qgis_root / "bin" / "python3.exe").exists():
        raise ItziError(f"{qgis_root} does not look like a QGIS / OSGeo4W folder (no bin/o4w_env.bat).")
    target = Path(target) if target else DEFAULT_LAUNCHER.parent / "itzi-py312"
    target.mkdir(parents=True, exist_ok=True)
    lines = ["@echo off",
             "rem Python with Itzi, written by `spongepark itzi setup`. QGIS itself is not changed.",
             f'call "{env}"',
             f"set PYTHONPATH={target}",
             '"%OSGEO4W_ROOT%\\bin\\python3.exe" %*']
    DEFAULT_LAUNCHER.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")
    r = subprocess.run([str(DEFAULT_LAUNCHER), "-m", "pip", "install", "--upgrade", "--target", str(target), "itzi"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ItziError("pip could not install itzi: " + r.stderr[-1500:])
    check = subprocess.run([str(DEFAULT_LAUNCHER), "-c", "import itzi, numpy"], capture_output=True, text=True)
    if check.returncode != 0:
        raise ItziError("itzi installed but does not import: " + check.stderr[-1500:])
    return DEFAULT_LAUNCHER


def simulate_itzi(z: np.ndarray, park: np.ndarray, cell: float, rain_mm_hr: np.ndarray, rain_dt_s: float,
                  duration_s: float, n_manning: np.ndarray, infil_mm_hr: np.ndarray,
                  frame_every_s: float = 300.0, timeout_s: float = 3600.0, infil_fn=None,
                  surface: Optional[dict] = None) -> Result2D:
    """Run Itzi on grid ``z`` (no NaN; row 0 = north). ``park`` marks where rain falls and volumes are
    counted; the outer edge of the grid is open. Returns the same result as the built-in model, with
    the mean flow (qx, qy) and maximum speed in ``res.extra``. ``infil_fn(t_s, rain_mm_hr, cum_rain_mm)``
    (Horton, curve number) is evaluated for every rain step, as the built-in model does."""
    exe = launcher()
    if exe is None:
        raise ItziError("Itzi is not set up: run `spongepark itzi setup` (needs QGIS or another Python 3.12).")
    rows, cols = z.shape
    bct = np.ones((rows, cols), np.float32)
    bct[0, :] = bct[-1, :] = bct[:, 0] = bct[:, -1] = 2.0      # open outer edge
    with tempfile.TemporaryDirectory(prefix="itzi_") as tmp:
        d = Path(tmp)
        extra = {}
        if infil_fn is not None:
            rr = np.asarray(rain_mm_hr, float)
            n_steps = int(np.ceil(duration_s / rain_dt_s))
            cum, grids = 0.0, []
            for k in range(n_steps):
                i_k = float(rr[k]) if k < len(rr) else 0.0
                grids.append(np.where(park, infil_fn(k * rain_dt_s, i_k, cum), 0.0).astype(np.float32))
                cum += i_k * rain_dt_s / 3600
            extra["infiltration_steps"] = np.stack(grids)
        np.savez(d / "inputs.npz", dem=z.astype(np.float32), friction=n_manning.astype(np.float32),
                 infiltration=np.where(park, infil_mm_hr, 0.0).astype(np.float32),
                 rain_rates=np.asarray(rain_mm_hr, float), rain_mask=park.astype(np.float32), bctype=bct, **extra)
        (d / "config.json").write_text(json.dumps({"cell_m": cell, "rain_dt_s": rain_dt_s, "duration_s": duration_s,
                                                   "record_s": frame_every_s, "surface": surface or {},
                                                   "debug": bool(os.environ.get("SPONGEPARK_ITZI_DEBUG"))}))
        # Itzi stops when its own mass-balance check fails (short intense peaks on steep ground): try again
        # with a shorter time step
        tries = [surface or {}, {**(surface or {}), "cfl": 0.5}, {**(surface or {}), "cfl": 0.3, "dtmax": 1.0}]
        for used in tries:
            cfg = json.loads((d / "config.json").read_text())
            cfg["surface"] = used
            (d / "config.json").write_text(json.dumps(cfg))
            r = subprocess.run([str(exe), str(WORKER), str(d)], capture_output=True, text=True, timeout=timeout_s,
                               shell=False)
            if r.returncode == 0 or "MassBalanceError" not in (r.stderr or ""):
                break
            log.info("Itzi mass-balance stop with %s; retrying with a shorter time step", used)
        if os.environ.get("SPONGEPARK_ITZI_DEBUG"):
            print(r.stdout[-4000:])
        if r.returncode != 0 or not (d / "result.json").exists():
            raise ItziError("Itzi failed: " + (r.stderr or r.stdout)[-1500:])
        meta = json.loads((d / "result.json").read_text())
        with np.load(d / "outputs.npz") as o:   # read everything, then close (Windows keeps open files)
            times, frames = o["times_s"], o["depth_m"].astype(np.float32)
            hmax, vmax, qx, qy = o["hmax"], o["vmax"], o["qx_mean"], o["qy_mean"]
            infil_acc = o["infiltration_m"] if "infiltration_m" in o.files else None

    a = cell * cell
    steps = int(np.ceil(duration_s / rain_dt_s))
    rain_depth_m = float(np.sum(np.asarray(rain_mm_hr, float)[:steps]) * rain_dt_s / 3600 / 1000)
    rain = rain_depth_m * float(park.sum()) * a
    infil = float(infil_acc[park].sum() * a) if infil_acc is not None else None
    surface = float(frames[-1][park].sum() * a) if len(frames) else 0.0
    out = rain - (infil or 0.0) - surface        # what left the park (over its edge)
    balance = {"rainfall_m3": rain, "infiltration_ground_m3": infil if infil is not None else float("nan"),
               "infiltration_elements_m3": 0.0, "outflow_m3": out, "surface_remaining_m3": surface,
               "element_storage_remaining_m3": 0.0,
               "continuity_error_m3": float(meta["continuity"].get("volume_error", 0.0)),
               "continuity_error_pct": 100 * float(meta["continuity"].get("continuity_error", 0.0)),
               "model": "itzi", "run_seconds": meta["seconds"], "itzi_settings": used}
    res = Result2D(times, frames, np.where(park, hmax, 0.0), balance)
    res.extra = {"vmax_m_s": vmax, "qx_mean": qx, "qy_mean": qy}   # flow pattern for the map
    return res
