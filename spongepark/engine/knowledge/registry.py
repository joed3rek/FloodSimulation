"""The source registry, ``knowledge/sources.yaml``: what may be fetched, from where, under which terms."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ACCESS = ("open", "user-supplied", "metadata-only")


def root() -> Path:
    """The knowledge folder: ``SPONGEPARK_KNOWLEDGE`` or ``knowledge/`` at the repository root."""
    env = os.environ.get("SPONGEPARK_KNOWLEDGE")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "knowledge"


@dataclass
class Source:
    id: str
    title: str
    publisher: str
    access: str
    status: str
    kind: str = ""
    edition: str = ""
    landing: str = ""
    files: List[str] = field(default_factory=list)
    licence_note: str = ""
    robots: str = ""
    climate: List[str] = field(default_factory=list)
    elements: List[str] = field(default_factory=list)
    priority: int = 3
    notes: str = ""

    @property
    def fetchable(self) -> bool:
        """Open, checked reachable, and with files to fetch."""
        return self.access == "open" and self.status == "reachable" and bool(self.files)

    def raw_dir(self, base: Optional[Path] = None) -> Path:
        return (base or root()) / "raw" / self.id


def load(path: Optional[Path] = None) -> Dict[str, Any]:
    import yaml

    p = path or root() / "sources.yaml"
    with open(p, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc


def sources(path: Optional[Path] = None) -> List[Source]:
    """The registry's sources, checked: unique ids, a known access type."""
    doc = load(path)
    out, seen = [], set()
    known = set(Source.__dataclass_fields__)
    for raw in doc.get("sources", []):
        s = Source(**{k: v for k, v in raw.items() if k in known})
        if s.id in seen:
            raise ValueError(f"sources.yaml: duplicate source id '{s.id}'.")
        if s.access not in ACCESS:
            raise ValueError(f"sources.yaml: {s.id} has access '{s.access}' (expected one of {', '.join(ACCESS)}).")
        s.files = [str(u) for u in (s.files or [])]
        seen.add(s.id)
        out.append(s)
    return out


def user_agent(path: Optional[Path] = None) -> str:
    return str(load(path).get("user_agent") or "spongepark-knowledge/0.1")
