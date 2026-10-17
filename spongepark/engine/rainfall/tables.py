"""Return-period rainfall table and depth-duration (IDF) lookup.

The table holds, for each return period (yr) and duration (hr), a rainfall
depth (mm). It can come from 24-hour depths only, or from an IDF table with
several durations. Intensities are converted to depths (depth = i x t).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

STANDARD_RPS = [1, 2, 5, 10, 25, 50, 100]


class RainfallError(ValueError):
    pass


@dataclass
class RainfallTable:
    """Depth (mm) per return period (yr) and duration (hr)."""

    df: pd.DataFrame  # columns: return_period_yr, duration_hr, depth_mm
    short_duration_method: str = "imd_one_third"

    @classmethod
    def from_csv(cls, path: Path, short_duration_method: str = "imd_one_third") -> "RainfallTable":
        """Read a CSV with ``return_period_yr``, ``duration_hr`` and ``depth_mm`` or ``intensity_mm_hr``.

        A CSV with only ``return_period_yr`` and ``depth_mm`` is read as 24-hour depths.
        """
        raw = pd.read_csv(path, comment="#")
        return cls.from_frame(raw, short_duration_method)

    @classmethod
    def from_frame(cls, raw: pd.DataFrame, short_duration_method: str = "imd_one_third") -> "RainfallTable":
        df = raw.rename(columns=str.strip).copy()
        if "return_period_yr" not in df:
            raise RainfallError("Rainfall table needs a 'return_period_yr' column.")
        if "duration_hr" not in df:
            log.info("no duration_hr column: treating depths as 24-hour depths")
            df["duration_hr"] = 24.0
        if "depth_mm" not in df:
            if "intensity_mm_hr" not in df:
                raise RainfallError("Rainfall table needs 'depth_mm' or 'intensity_mm_hr'.")
            df["depth_mm"] = df["intensity_mm_hr"] * df["duration_hr"]
        df = df[["return_period_yr", "duration_hr", "depth_mm"]].astype(float)
        if (df["depth_mm"] <= 0).any():
            raise RainfallError("Rainfall depths must be positive.")
        df = df.sort_values(["return_period_yr", "duration_hr"]).reset_index(drop=True)
        t = cls(df=df, short_duration_method=short_duration_method)
        t._check_monotonic()
        return t

    def _check_monotonic(self) -> None:
        for d, g in self.df.groupby("duration_hr"):
            if not np.all(np.diff(g["depth_mm"].to_numpy()) >= 0):
                raise RainfallError(f"Depths must not decrease with return period (duration {d} h).")
        for rp, g in self.df.groupby("return_period_yr"):
            if not np.all(np.diff(g["depth_mm"].to_numpy()) >= 0):
                raise RainfallError(f"Depths must not decrease with duration (return period {rp} yr).")

    @property
    def return_periods(self) -> List[int]:
        return [int(r) for r in sorted(self.df["return_period_yr"].unique())]

    @property
    def is_24h_only(self) -> bool:
        return set(self.df["duration_hr"].unique()) == {24.0}

    def kind(self) -> str:
        return "24h_depth" if self.is_24h_only else "idf"

    def depth(self, rp: float, duration_hr: float) -> float:
        """Rainfall depth (mm) for return period ``rp`` (yr) and ``duration_hr`` (hr)."""
        g = self.df[self.df["return_period_yr"] == float(rp)]
        if g.empty:
            raise RainfallError(f"No rainfall data for the {rp}-year return period.")
        durs = g["duration_hr"].to_numpy()
        deps = g["depth_mm"].to_numpy()
        if len(durs) == 1:
            if self.short_duration_method != "imd_one_third":
                raise RainfallError(f"Unknown short duration method {self.short_duration_method}.")
            # IMD / CWC one-third power rule: P_t = P_T (t / T)^(1/3)
            return float(deps[0] * (duration_hr / durs[0]) ** (1.0 / 3.0))
        lt, ld = np.log(durs), np.log(deps)
        x = np.log(duration_hr)
        if x < lt[0] or x > lt[-1]:
            log.warning(
                "duration %.3f h is outside the IDF table (%.3f-%.3f h): log-log extrapolation used",
                duration_hr, durs[0], durs[-1],
            )
            i = 0 if x < lt[0] else -2
            slope = (ld[i + 1] - ld[i]) / (lt[i + 1] - lt[i])
            return float(np.exp(ld[i] + slope * (x - lt[i])))
        return float(np.exp(np.interp(x, lt, ld)))

    def to_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.df.to_csv(path, index=False)

    def summary(self) -> Dict[int, Dict[float, float]]:
        out: Dict[int, Dict[float, float]] = {}
        for _, r in self.df.iterrows():
            out.setdefault(int(r.return_period_yr), {})[float(r.duration_hr)] = float(r.depth_mm)
        return out


def check_return_periods(table: RainfallTable, required: Optional[List[int]] = None) -> List[int]:
    """Return the required return periods missing from the table."""
    required = required or STANDARD_RPS
    have = set(table.return_periods)
    return [rp for rp in required if rp not in have]
