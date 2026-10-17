"""Surrogate models that predict SWMM metrics from layout settings, to search faster.

They only decide *which* layouts are worth a full SWMM evaluation; they never supply a reported
number. A surrogate is used only when its hold-out accuracy meets ``ml.min_r2`` for every target;
otherwise the optimiser evaluates candidates with SWMM directly.

Two models (gradient boosting, scikit-learn):

* per return period, from the layout features plus return period and rainfall depth: retained %
  and peak outflow ratio (option / baseline);
* per layout: intervention area %, cut volume and the longest simulated drawdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

RP_TARGETS = ("retained_pct", "peak_ratio")
LAYOUT_TARGETS = ("area_pct", "cut_m3", "max_drawdown_hr")


def rp_rows(rows: List[Dict[str, Any]], features) -> Tuple[np.ndarray, np.ndarray]:
    X, Y = [], []
    for r in rows:
        if not r.get("feasible"):
            continue
        f = features(np.array(r["x"]))
        for rp, v in r["per_rp"].items():
            X.append(np.r_[f, float(rp), float(v["rainfall_mm"])])
            Y.append([v[t] for t in RP_TARGETS])
    return np.array(X), np.array(Y)


def layout_rows(rows: List[Dict[str, Any]], features) -> Tuple[np.ndarray, np.ndarray]:
    X = [features(np.array(r["x"])) for r in rows if r.get("feasible")]
    Y = [[r[t] for t in LAYOUT_TARGETS] for r in rows if r.get("feasible")]
    return np.array(X), np.array(Y)


@dataclass
class Model:
    names: List[str]
    estimators: List[Any] = field(default_factory=list)
    scores: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def fit(self, X: np.ndarray, Y: np.ndarray, seed: int, test_fraction: float) -> "Model":
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
        from sklearn.model_selection import train_test_split

        Xtr, Xte, Ytr, Yte = train_test_split(X, Y, test_size=test_fraction, random_state=seed)
        self.estimators, self.scores = [], {}
        for j, name in enumerate(self.names):
            m = GradientBoostingRegressor(random_state=seed, n_estimators=200, max_depth=3, learning_rate=0.05,
                                          subsample=0.9)
            m.fit(Xtr, Ytr[:, j])
            pred = m.predict(Xte)
            const = np.ptp(Yte[:, j]) < 1e-9
            self.scores[name] = {
                "r2": 1.0 if const and np.allclose(pred, Yte[:, j], atol=1e-6) else float(r2_score(Yte[:, j], pred)),
                "mae": float(mean_absolute_error(Yte[:, j], pred)),
                "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
            }
            m.fit(X, Y[:, j])  # final model on all data
            self.estimators.append(m)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.column_stack([m.predict(X) for m in self.estimators])


@dataclass
class Surrogate:
    rp_model: Model
    layout_model: Model
    min_r2: float

    @property
    def scores(self) -> Dict[str, Dict[str, float]]:
        return {**self.rp_model.scores, **self.layout_model.scores}

    @property
    def usable(self) -> bool:
        return all(s["r2"] >= self.min_r2 for s in self.scores.values())

    @classmethod
    def train(cls, rows: List[Dict[str, Any]], features, seed: int, test_fraction: float, min_r2: float,
              min_rows: int = 8) -> Optional["Surrogate"]:
        Xl, Yl = layout_rows(rows, features)
        if len(Xl) < min_rows:
            return None
        Xr, Yr = rp_rows(rows, features)
        return cls(Model(list(RP_TARGETS)).fit(Xr, Yr, seed, test_fraction),
                   Model(list(LAYOUT_TARGETS)).fit(Xl, Yl, seed, test_fraction), min_r2)

    def predict(self, F: np.ndarray, rps: List[int], rain_mm: Dict[int, float]) -> Dict[str, np.ndarray]:
        """Predictions for feature rows ``F``: per-RP arrays (n, n_rp) and per-layout arrays (n,)."""
        out: Dict[str, np.ndarray] = {}
        lay = self.layout_model.predict(F)
        for j, t in enumerate(LAYOUT_TARGETS):
            out[t] = lay[:, j]
        per = [self.rp_model.predict(np.column_stack([F, np.full(len(F), rp), np.full(len(F), rain_mm[rp])]))
               for rp in rps]
        for j, t in enumerate(RP_TARGETS):
            out[t] = np.column_stack([p[:, j] for p in per])
        return out
