"""Component catalogue (one entry per NbS type / guideline chapter)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Dict, List, Optional

from pydantic import BaseModel

LID_BIORETENTION = "lid_bioretention"
LID_SWALE = "lid_swale"
STORAGE = "storage"


class ComponentSpec(BaseModel):
    type: str
    label: str
    chapter: Optional[str] = None
    functions: List[str]
    scales: List[str]
    swmm: str
    geometry: List[str]
    description: str = ""
    modelling_note: str = ""

    @property
    def is_lid(self) -> bool:
        return self.swmm in (LID_BIORETENTION, LID_SWALE)

    @property
    def is_storage(self) -> bool:
        return self.swmm == STORAGE


@lru_cache(maxsize=1)
def catalogue() -> Dict[str, ComponentSpec]:
    with resources.files("spongepark.engine.nbs").joinpath("data/components.json").open(encoding="utf-8") as f:
        data = json.load(f)
    return {k: ComponentSpec(type=k, **v) for k, v in data["components"].items()}


def spec(component_type: str) -> ComponentSpec:
    cat = catalogue()
    if component_type not in cat:
        raise ValueError(f"Unknown NbS component type '{component_type}'. Known: {', '.join(sorted(cat))}.")
    return cat[component_type]
