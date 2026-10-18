"""Parameter system.

Every value the engine uses is stored in ``parameters.json`` with its unit, its
source and whether the user has confirmed it. Nothing is assumed silently: the
engine reads parameters only through :class:`ParameterSet`, and reports list
every parameter that is still an unconfirmed default.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Union

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

ParamValue = Union[bool, int, float, str, List[Any], Dict[str, Any], None]


class Source(str, Enum):
    """Where a parameter value came from."""

    DEFAULT = "default"
    SITE_MEASURED = "site measured"
    LITERATURE = "literature"
    DESIGNER = "designer"  # a design decision entered by the designer (e.g. area budget)
    USER = "designer"  # older name, kept as an alias

    @classmethod
    def _missing_(cls, value):
        if value == "user":  # files written before schema 1.1
            return cls.DESIGNER
        return None


class Parameter(BaseModel):
    """One parameter with provenance."""

    key: str
    value: ParamValue
    unit: str = "-"
    source: Source = Source.DEFAULT
    note: str = ""
    confirmed: bool = False

    @property
    def is_unconfirmed_default(self) -> bool:
        return not self.confirmed and self.source in (Source.DEFAULT, Source.LITERATURE)


class ParameterSet(BaseModel):
    """All project parameters, keyed by dotted name (e.g. ``rainfall.time_step_min``)."""

    items: Dict[str, Parameter] = Field(default_factory=dict)

    def __contains__(self, key: str) -> bool:
        return key in self.items

    def __iter__(self) -> Iterator[Parameter]:  # type: ignore[override]
        return iter(self.items.values())

    def get(self, key: str) -> Parameter:
        try:
            return self.items[key]
        except KeyError:
            raise KeyError(
                f"Parameter '{key}' is not defined in this project. "
                "Add it with `spongepark params set` or re-create the project defaults."
            ) from None

    def value(self, key: str) -> Any:
        """Return the value of a parameter (raises if missing)."""
        return self.get(key).value

    def value_or(self, key: str, fallback: Any) -> Any:
        """Return the value, or ``fallback`` when the key is absent (no silent default is stored)."""
        return self.items[key].value if key in self.items else fallback

    def set(
        self,
        key: str,
        value: ParamValue,
        unit: Optional[str] = None,
        source: Source = Source.USER,
        note: Optional[str] = None,
        confirmed: bool = True,
    ) -> Parameter:
        """Set a value. Values set by the user are confirmed by default."""
        old = self.items.get(key)
        p = Parameter(
            key=key,
            value=value,
            unit=unit if unit is not None else (old.unit if old else "-"),
            source=source,
            note=note if note is not None else (old.note if old else ""),
            confirmed=confirmed,
        )
        self.items[key] = p
        log.info("parameter %s = %r %s (%s)", key, value, p.unit, source.value)
        return p

    def confirm(self, key: str) -> None:
        self.get(key).confirmed = True

    def unconfirmed(self) -> List[Parameter]:
        return [p for p in self.items.values() if p.is_unconfirmed_default]

    def merge_defaults(self, defaults: "ParameterSet") -> List[str]:
        """Bring the set up to the engine's defaults. Returns added keys.

        Adds new defaults, refreshes the value of defaults that are still unconfirmed (they are not
        user decisions) and drops unconfirmed defaults the engine no longer has. Values set or
        confirmed by the user are never touched."""
        added = []
        for k, p in defaults.items.items():
            if k not in self.items:
                self.items[k] = p.model_copy(deep=True)
                added.append(k)
            elif self.items[k].is_unconfirmed_default and self.items[k].value != p.value:
                log.info("default %s updated: %r -> %r", k, self.items[k].value, p.value)
                self.items[k] = p.model_copy(deep=True)
        for k in [k for k, p in self.items.items() if k not in defaults.items and p.is_unconfirmed_default]:
            log.info("obsolete default %s removed", k)
            del self.items[k]
        return added

    def to_json_dict(self) -> Dict[str, Any]:
        return {k: p.model_dump(mode="json", exclude={"key"}) for k, p in sorted(self.items.items())}

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> "ParameterSet":
        return cls(items={k: Parameter(key=k, **v) for k, v in data.items()})
