"""Staged rules (docs/KNOWLEDGE_BRIEF.md, A3): values extracted from a source, waiting for review.

``knowledge/staging/<source>.jsonl``, one rule per line, committed: only the fact, its units (SI, with the
original kept), when it applies, and where it is (file, page or section, a verbatim snippet under 15 words) so
a person can check it. Every rule starts "unreviewed"; only approved rules (knowledge/rules/) drive checks.
``check()`` verifies each rule against the text store: the snippet must be on the cited page.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from . import registry, textstore

ELEMENTS = ("rain_garden", "bioswale", "vegetated_swale", "filter_strip", "tree_trench", "infiltration_trench",
            "recharge_well", "permeable_pavement", "green_roof", "rainwater_harvesting", "detention_basin",
            "retention_pond", "constructed_wetland", "check_dam", "depave")
CATEGORIES = ("siting", "geometry", "media", "storage", "inlet", "pretreatment", "outlet", "planting", "safety",
              "construction", "maintenance", "performance", "cost")

# unit -> (SI unit, factor); temperature-like offsets are not needed here
UNITS: Dict[str, tuple] = {
    "m": ("m", 1.0), "mm": ("m", 1e-3), "cm": ("m", 1e-2), "ft": ("m", 0.3048), "in": ("m", 0.0254), "km": ("m", 1e3),
    "m2": ("m2", 1.0), "ft2": ("m2", 0.09290304), "ac": ("m2", 4046.8564224), "ha": ("m2", 1e4), "km2": ("m2", 1e6),
    "m3": ("m3", 1.0), "l": ("m3", 1e-3), "ft3": ("m3", 0.028316846592), "gal": ("m3", 0.003785411784),
    "mm/hr": ("mm/hr", 1.0), "in/hr": ("mm/hr", 25.4), "m/s": ("m/s", 1.0), "ft/s": ("m/s", 0.3048),
    "m/day": ("mm/hr", 1000 / 24), "cm/hr": ("mm/hr", 10.0),
    "hr": ("hr", 1.0), "min": ("hr", 1 / 60), "day": ("hr", 24.0), "days": ("hr", 24.0), "yr": ("yr", 1.0),
    "%": ("%", 1.0), "fraction": ("%", 100.0), "H:V": ("H:V", 1.0), "V:H": ("V:H", 1.0), "ratio": ("ratio", 1.0),
    "m3/s": ("m3/s", 1.0), "l/s": ("m3/s", 1e-3), "cfs": ("m3/s", 0.028316846592),
    "kg/m3": ("kg/m3", 1.0), "count": ("count", 1.0), "-": ("-", 1.0), "text": ("text", 1.0),
    "times/yr": ("times/yr", 1.0), "USD/m2": ("USD/m2", 1.0), "USD/m3": ("USD/m3", 1.0),
    "ppm": ("ppm", 1.0), "m3/ha": ("m3/ha", 1.0), "mm/day": ("mm/hr", 1 / 24), "m2/s": ("m2/s", 1.0),
}


def to_si(v: Optional[float], unit: str) -> Optional[float]:
    if v is None:
        return None
    return round(float(v) * UNITS[unit][1], 6)


class StagedRule(BaseModel):
    id: str                                   # <source>.<element>.<parameter>[.<n>]
    source: str                               # registry id
    edition: str = ""
    file: str                                 # the file in knowledge/raw/<source>/
    page: int                                 # page (PDF), section number (web page) or sheet (spreadsheet)
    section: str = ""                         # the heading or table the value is in
    snippet: str                              # verbatim, under 15 words, for a person to find it
    element: str
    category: str
    parameter: str                            # an engine field where one exists (e.g. max_ponding_depth_m)
    value: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    unit: str                                 # as written
    value_si: Optional[float] = None
    min_si: Optional[float] = None
    max_si: Optional[float] = None
    unit_si: str = ""
    text: str = ""                            # a rule without a number (e.g. "fence when deeper than ...")
    condition: str = ""                       # when it applies
    severity: Literal["requirement", "recommendation", "typical", "information"] = "recommendation"
    climate: List[str] = Field(default_factory=list)
    confidence: float = 0.8
    method: str = "read by Claude (Anthropic) from the text store; snippet verified on the page"
    extracted: str = Field(default_factory=lambda: date.today().isoformat())
    status: Literal["unreviewed", "approved", "edited", "rejected"] = "unreviewed"
    note: str = ""

    @field_validator("element")
    @classmethod
    def _element(cls, v):
        if v not in ELEMENTS and v != "general":
            raise ValueError(f"unknown element '{v}'")
        return v

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"unknown category '{v}'")
        return v

    @field_validator("snippet")
    @classmethod
    def _snippet(cls, v):
        if not 2 <= len(v.split()) <= 14:
            raise ValueError(f"the snippet must be 2 to 14 words (has {len(v.split())}): '{v}'")
        return v

    @model_validator(mode="after")
    def _si(self):
        if self.unit not in UNITS:
            raise ValueError(f"{self.id}: unknown unit '{self.unit}' (add it to UNITS)")
        if self.value is None and self.min is None and self.max is None and not self.text:
            raise ValueError(f"{self.id}: a value, a range or a text rule is needed")
        self.unit_si = UNITS[self.unit][0]
        self.value_si, self.min_si, self.max_si = (to_si(x, self.unit) for x in (self.value, self.min, self.max))
        return self


def path(source_id: str, base: Optional[Path] = None) -> Path:
    return (base or registry.root()) / "staging" / f"{source_id}.jsonl"


def load(source_id: str, base: Optional[Path] = None) -> List[StagedRule]:
    p = path(source_id, base)
    if not p.exists():
        return []
    return [StagedRule.model_validate_json(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def save(source_id: str, rules: List[StagedRule], base: Optional[Path] = None) -> Path:
    p = path(source_id, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    ids = [r.id for r in rules]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate rule ids: {sorted(dup)}")
    p.write_text("".join(r.model_dump_json(exclude_none=True) + "\n" for r in rules), encoding="utf-8")
    return p


def check(source_id: str, base: Optional[Path] = None) -> List[str]:
    """Problems with a source's staged rules: snippets not on their page, wrong source id."""
    problems = []
    for r in load(source_id, base):
        if r.source != source_id:
            problems.append(f"{r.id}: source is '{r.source}', file is {source_id}.jsonl")
        if not textstore.contains(source_id, r.file, r.page, r.snippet, base):
            problems.append(f"{r.id}: snippet not found on {r.file} p.{r.page}: '{r.snippet}'")
    return problems
