"""Plain-text EPA SWMM 5.2 .inp writer.

A small, explicit writer is used instead of a template so every line the engine
emits is traceable. Sections are written in the order SWMM documents them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

SECTION_ORDER = [
    "TITLE", "OPTIONS", "EVAPORATION", "RAINGAGES", "SUBCATCHMENTS", "SUBAREAS", "INFILTRATION",
    "LID_CONTROLS", "LID_USAGE", "JUNCTIONS", "OUTFALLS", "STORAGE", "CONDUITS", "ORIFICES", "WEIRS",
    "XSECTIONS", "CURVES", "TIMESERIES", "REPORT", "COORDINATES", "Polygons",
]


def fmt(v: object) -> str:
    if isinstance(v, float):
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"
    return str(v)


@dataclass
class InpFile:
    sections: Dict[str, List[str]] = field(default_factory=dict)

    def add(self, section: str, *values: object, comment: str = "") -> None:
        line = "  ".join(fmt(v) for v in values)
        if comment:
            line = f"{line}  ;{comment}" if values else f";{comment}"
        self.sections.setdefault(section, []).append(line)

    def comment(self, section: str, text: str) -> None:
        self.sections.setdefault(section, []).append(f";{text}")

    def option(self, key: str, value: object) -> None:
        self.add("OPTIONS", key, value)

    def render(self) -> str:
        out: List[str] = []
        for name in SECTION_ORDER:
            lines = self.sections.get(name)
            if not lines:
                continue
            out.append(f"[{name}]")
            out.extend(lines)
            out.append("")
        unknown = set(self.sections) - set(SECTION_ORDER)
        if unknown:
            raise ValueError(f"unknown SWMM sections: {unknown}")
        return "\n".join(out)


def hhmm(hours: float) -> str:
    """Hours -> 'H:MM' (SWMM time format)."""
    total_min = int(round(hours * 60))
    return f"{total_min // 60}:{total_min % 60:02d}"


def hhmmss(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def ring_coords(coords: Sequence) -> List[tuple]:
    return [(float(x), float(y)) for x, y, *_ in coords]
