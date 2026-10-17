"""Pydantic models for the project manifest, history and locks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from spongepark import __version__

SCHEMA_VERSION = "1.0"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Units(BaseModel):
    length: str = "m"
    rainfall: str = "mm"
    time: str = "hr"
    flow: str = "m3/s"
    volume: str = "m3"


class Manifest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    project_name: str
    city: str = "Bengaluru"
    crs: str = "EPSG:32643"  # UTM 43N; "LOCAL" allowed for local survey metres
    units: Units = Field(default_factory=Units)
    created: str = Field(default_factory=utcnow)
    modified: str = Field(default_factory=utcnow)
    engine_version: str = __version__
    calibration_status: str = "uncalibrated"


class HistoryEntry(BaseModel):
    time: str = Field(default_factory=utcnow)
    action: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    engine_version: str = __version__


class History(BaseModel):
    entries: List[HistoryEntry] = Field(default_factory=list)

    def log(self, action: str, **detail: Any) -> None:
        self.entries.append(HistoryEntry(action=action, detail=detail))


class Locks(BaseModel):
    """Elements locked by the designer, per option."""

    locked: Dict[str, List[str]] = Field(default_factory=dict)  # option_id -> element ids
    note: Optional[str] = None
