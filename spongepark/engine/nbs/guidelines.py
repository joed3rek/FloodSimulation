"""Design guideline rules and checks.

Rules live in ``data/guidelines.json`` (one entry per numeric range in the
Habitat Collective guideline chapters, each with its citation). Every element is
checked before a SWMM run; findings are stored with the option results and
printed in reports. ``error`` findings stop a run when
``guidelines.enforce_errors`` is true; ``warning`` and ``info`` are reported only.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel

from .components import NbSElement


class GuidelineRule(BaseModel):
    id: str
    applies_to: List[str]
    field: str
    min: Optional[float] = None
    max: Optional[float] = None
    unit: str = "-"
    severity: str = "warning"  # info | warning | error
    source: str
    section: str
    page: Optional[int] = None
    note: str = ""

    def citation(self, sources: Dict[str, str]) -> str:
        page = f", p.{self.page}" if self.page else ""
        return f"{self.source} {self.section}{page}"


class Finding(BaseModel):
    element_id: str
    rule_id: str
    severity: str
    field: str
    value: Any
    allowed: str
    message: str
    citation: str


@lru_cache(maxsize=1)
def _load() -> Dict[str, Any]:
    with resources.files("spongepark.engine.nbs").joinpath("data/guidelines.json").open(encoding="utf-8") as f:
        return json.load(f)


def rules() -> List[GuidelineRule]:
    return [GuidelineRule.model_validate(r) for r in _load()["rules"]]


def sources() -> Dict[str, str]:
    return dict(_load()["sources"])


def context_notes() -> List[Dict[str, Any]]:
    return list(_load().get("context_notes", []))


def _allowed(r: GuidelineRule) -> str:
    if r.min is not None and r.max is not None:
        return f"{r.min:g}-{r.max:g} {r.unit}"
    if r.min is not None:
        return f">= {r.min:g} {r.unit}"
    return f"<= {r.max:g} {r.unit}"


def check_element(el: NbSElement, rule_set: Optional[Iterable[GuidelineRule]] = None) -> List[Finding]:
    """Check one element against every applicable rule whose field has a value."""
    out: List[Finding] = []
    srcs = sources()
    for r in rule_set if rule_set is not None else rules():
        if el.type not in r.applies_to:
            continue
        v = getattr(el, r.field, None)
        if v is None:
            continue
        low = r.min is not None and v < r.min - 1e-12
        high = r.max is not None and v > r.max + 1e-12
        if low or high:
            out.append(
                Finding(
                    element_id=el.id,
                    rule_id=r.id,
                    severity=r.severity,
                    field=r.field,
                    value=v,
                    allowed=_allowed(r),
                    message=f"{el.id} ({el.type}): {r.field} = {v:g} {r.unit} is outside {_allowed(r)}. {r.note}",
                    citation=r.citation(srcs),
                )
            )
    return out


def check_elements(elements: Iterable[NbSElement]) -> List[Finding]:
    rs = rules()
    return [f for el in elements for f in check_element(el, rs)]
