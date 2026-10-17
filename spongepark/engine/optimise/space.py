"""Design space searched by the optimiser.

A layout is not encoded cell by cell: the decision variables are the settings of the Phase 4
generator (which component types are included, how much of the area budget is used, the storm the
elements are sized for, ponding depths and how placement trades water reaching a cell against low
ground). Each setting produces a complete, graded, valid layout, so every candidate respects the
keep-out areas, setbacks, locks and drawdown rule by construction.

Ranges come from ``optimise.ranges`` (a project parameter, so the designer sees and confirms them);
depth ranges are the safety limits for public ponding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from ..project import Project


@dataclass
class Variable:
    name: str  # parameter key, "include.<type>", "budget_use" or "design_rp_index"
    lo: float
    hi: float
    kind: str = "real"  # "real" | "flag" | "index"


@dataclass
class Space:
    variables: List[Variable]
    types: List[str]
    return_periods: List[int]
    max_area_pct: float

    @classmethod
    def from_project(cls, project: Project) -> "Space":
        P = project.parameters
        types = list(P.value("layout.types"))
        rps = [int(r) for r in P.value("project.return_periods")]
        vs = [Variable("budget_use", *P.value("optimise.ranges")["budget_use"]),
              Variable("design_rp_index", 0, len(rps) - 1, "index")]
        for t in types:
            vs.append(Variable(f"include.{t}", 0, 1, "flag"))
        for key, (lo, hi) in P.value("optimise.ranges").items():
            if key == "budget_use":
                continue
            t = key.split(".")[1] if key.startswith("nbs.") else None
            if t is None or t in types:
                vs.append(Variable(key, float(lo), float(hi)))
        return cls(vs, types, rps, float(P.value("layout.max_area_pct")))

    @property
    def n(self) -> int:
        return len(self.variables)

    def bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        return np.array([v.lo for v in self.variables], float), np.array([v.hi for v in self.variables], float)

    def decode(self, x: np.ndarray) -> Tuple[List[str], Dict[str, Any]]:
        """(element types, parameter overrides) for one point of the space."""
        types, ov = [], {}
        for v, val in zip(self.variables, x):
            if v.kind == "flag":
                if val >= 0.5:
                    types.append(v.name.split(".", 1)[1])
            elif v.name == "budget_use":
                ov["layout.max_area_pct"] = round(float(val) * self.max_area_pct, 3)
            elif v.kind == "index":
                ov["layout.design_return_period_yr"] = self.return_periods[int(round(float(val)))]
            else:
                ov[v.name] = round(float(val), 4)
        types = [t for t in self.types if t in types]  # keep the treatment-train order
        return types, ov

    def features(self, x: np.ndarray) -> np.ndarray:
        """Numeric features of a point (decoded values, flags as 0/1) for the surrogate."""
        out = []
        for v, val in zip(self.variables, x):
            if v.kind == "flag":
                out.append(1.0 if val >= 0.5 else 0.0)
            elif v.kind == "index":
                out.append(float(self.return_periods[int(round(float(val)))]))
            else:
                out.append(float(val))
        return np.array(out)

    def names(self) -> List[str]:
        return [v.name for v in self.variables]
