"""Design storm hyetographs.

Methods
-------
* ``alternating_block``: blocks of the depth-duration curve, largest block at the
  peak position, the rest alternating either side (Chow, Maidment & Mays 1988).
* ``huff``: Huff (1967) median cumulative distribution for a chosen quartile,
  scaled to the storm depth.
* ``user_csv``: a recorded storm (e.g. KSNDMC or IMD gauge), either used as-is or
  scaled to each return period's storm depth.

Peak flows are sensitive to the method; reports state which method was used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .tables import RainfallError, RainfallTable

log = logging.getLogger(__name__)


@dataclass
class Hyetograph:
    """Rainfall intensity per interval. ``intensity_mm_hr[k]`` applies over [k dt, (k+1) dt)."""

    return_period_yr: int
    dt_min: float
    intensity_mm_hr: np.ndarray
    method: str

    @property
    def depth_mm(self) -> float:
        return float(np.sum(self.intensity_mm_hr) * self.dt_min / 60.0)

    @property
    def duration_hr(self) -> float:
        return len(self.intensity_mm_hr) * self.dt_min / 60.0

    @property
    def peak_mm_hr(self) -> float:
        return float(np.max(self.intensity_mm_hr)) if len(self.intensity_mm_hr) else 0.0

    def depths_mm(self) -> np.ndarray:
        return self.intensity_mm_hr * self.dt_min / 60.0

    def to_frame(self) -> pd.DataFrame:
        t = np.arange(len(self.intensity_mm_hr)) * self.dt_min
        return pd.DataFrame(
            {
                "time_min": t,
                "intensity_mm_hr": self.intensity_mm_hr,
                "cumulative_mm": np.cumsum(self.depths_mm()),
            }
        )

    def to_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_csv(path, index=False)

    @classmethod
    def from_csv(cls, path: Path, rp: int, method: str = "stored") -> "Hyetograph":
        df = pd.read_csv(path)
        dt = float(df["time_min"].iloc[1] - df["time_min"].iloc[0])
        return cls(rp, dt, df["intensity_mm_hr"].to_numpy(dtype=float), method)


def _n_steps(duration_hr: float, dt_min: float) -> int:
    n = duration_hr * 60.0 / dt_min
    if abs(n - round(n)) > 1e-6:
        raise RainfallError("Storm duration must be a whole number of time steps.")
    return int(round(n))


def alternating_block(
    table: RainfallTable, rp: int, duration_hr: float, dt_min: float, peak_position: float = 0.5
) -> Hyetograph:
    """Alternating block hyetograph from the depth-duration relationship."""
    n = _n_steps(duration_hr, dt_min)
    cum = np.array([table.depth(rp, (k + 1) * dt_min / 60.0) for k in range(n)])
    blocks = np.diff(np.concatenate([[0.0], cum]))
    if np.any(blocks < -1e-9):
        raise RainfallError("Depth-duration curve decreases; cannot build alternating blocks.")
    order = np.sort(blocks)[::-1]
    out = np.zeros(n)
    centre = int(round(peak_position * (n - 1)))
    positions = [centre]
    left, right = centre - 1, centre + 1
    # alternate right then left, falling back to whichever side still has room
    turn_right = True
    while len(positions) < n:
        if (turn_right and right < n) or left < 0:
            positions.append(right)
            right += 1
        else:
            positions.append(left)
            left -= 1
        turn_right = not turn_right
    for depth, pos in zip(order, positions):
        out[pos] = depth
    return Hyetograph(rp, dt_min, out * 60.0 / dt_min, "alternating_block")


def load_huff_curves() -> pd.DataFrame:
    with resources.files("spongepark.engine.rainfall").joinpath("data/huff_median_curves.csv").open() as f:
        return pd.read_csv(f, comment="#")


def huff(table: RainfallTable, rp: int, duration_hr: float, dt_min: float, quartile: int = 2) -> Hyetograph:
    """Huff median-curve hyetograph for ``quartile`` (1-4), total depth = P(rp, duration)."""
    if quartile not in (1, 2, 3, 4):
        raise RainfallError("Huff quartile must be 1, 2, 3 or 4.")
    curves = load_huff_curves()
    n = _n_steps(duration_hr, dt_min)
    total = table.depth(rp, duration_hr)
    tf = np.linspace(0.0, 1.0, n + 1)
    cum = np.interp(tf, curves["time_fraction"], curves[f"q{quartile}"]) * total
    depths = np.diff(cum)
    return Hyetograph(rp, dt_min, depths * 60.0 / dt_min, f"huff_q{quartile}")


def from_user_csv(
    path: Path, rp: int, dt_min: float, scale_to_depth_mm: Optional[float] = None
) -> Hyetograph:
    """Read a recorded storm (``time_min`` plus ``intensity_mm_hr`` or ``depth_mm``).

    The record is resampled to ``dt_min`` by cumulative-depth interpolation, and
    optionally scaled so its total equals ``scale_to_depth_mm``.
    """
    df = pd.read_csv(path, comment="#")
    t = df["time_min"].to_numpy(dtype=float)
    if len(t) < 2:
        raise RainfallError(f"{path} needs at least two rows.")
    step = np.diff(t)
    if "depth_mm" in df:
        d = df["depth_mm"].to_numpy(dtype=float)
    elif "intensity_mm_hr" in df:
        d = df["intensity_mm_hr"].to_numpy(dtype=float) * np.append(step, step[-1]) / 60.0
    else:
        raise RainfallError(f"{path} needs 'depth_mm' or 'intensity_mm_hr'.")
    edges = np.append(t, t[-1] + step[-1])
    cum = np.concatenate([[0.0], np.cumsum(d)])
    n = int(np.ceil((edges[-1] - edges[0]) / dt_min - 1e-9))
    new_edges = edges[0] + np.arange(n + 1) * dt_min
    new_cum = np.interp(new_edges, edges, cum)
    depths = np.diff(new_cum)
    if scale_to_depth_mm is not None:
        if depths.sum() <= 0:
            raise RainfallError(f"{path} contains no rainfall.")
        depths = depths * scale_to_depth_mm / depths.sum()
    return Hyetograph(rp, dt_min, depths * 60.0 / dt_min, "user_csv")


def design_storms(
    table: RainfallTable,
    return_periods: list,
    method: str,
    duration_hr: float,
    dt_min: float,
    peak_position: float = 0.5,
    huff_quartile: int = 2,
    user_csv: Optional[Path] = None,
    user_scale: bool = True,
) -> Dict[int, Hyetograph]:
    """Build one design storm per return period."""
    out: Dict[int, Hyetograph] = {}
    for rp in return_periods:
        if method == "alternating_block":
            out[rp] = alternating_block(table, rp, duration_hr, dt_min, peak_position)
        elif method == "huff":
            out[rp] = huff(table, rp, duration_hr, dt_min, huff_quartile)
        elif method == "user_csv":
            if user_csv is None:
                raise RainfallError("hyetograph_method = user_csv needs a CSV file.")
            scale = table.depth(rp, duration_hr) if user_scale else None
            out[rp] = from_user_csv(user_csv, rp, dt_min, scale)
        else:
            raise RainfallError(f"Unknown hyetograph method '{method}'.")
        log.info(
            "RP %3d yr: %s, %.1f mm over %.1f h, peak %.1f mm/hr",
            rp, out[rp].method, out[rp].depth_mm, out[rp].duration_hr, out[rp].peak_mm_hr,
        )
    return out
