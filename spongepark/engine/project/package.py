"""The ``.sponge`` project package.

A ``.sponge`` file is a zip of a project folder (layout in ``docs/project_file.md``).
:class:`Project` unpacks it into a private working folder, lets every module read
and write files there, and zips it back on :meth:`Project.save`. A plain folder
can also be opened directly (useful for Rhino and debugging); it is then edited
in place.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .crs import ensure_project_crs, validate_project_crs
from .defaults import default_parameters
from .parameters import ParameterSet
from .schema import SCHEMA_VERSION, History, Locks, Manifest, utcnow

log = logging.getLogger(__name__)

PathLike = Union[str, os.PathLike]

SUBDIRS = ["terrain", "site", "rainfall", "rainfall/hyetographs", "options"]

# schema migrations: from_version -> function(root) that upgrades in place to the next version
MIGRATIONS: Dict[str, Callable[[Path], str]] = {}


class ProjectError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


class Project:
    """An open project. Use as a context manager so the working folder is cleaned up."""

    def __init__(self, root: Path, package_path: Optional[Path], owns_root: bool):
        self.root = root
        self.package_path = package_path
        self._owns_root = owns_root
        self.manifest = Manifest.model_validate(_read_json(root / "manifest.json"))
        self.parameters = ParameterSet.from_json_dict(_read_json(root / "parameters.json"))
        self.locks = Locks.model_validate(_read_json(root / "locks.json"))
        self.history = History.model_validate(_read_json(root / "history.json"))

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def create(
        cls,
        path: PathLike,
        name: str,
        city: str = "Bengaluru",
        crs: str = "EPSG:32643",
        overwrite: bool = False,
    ) -> "Project":
        """Create a new project at ``path`` (a ``.sponge`` file or a folder) and return it open."""
        path = Path(path)
        if path.exists() and not overwrite:
            raise ProjectError(f"{path} already exists (use overwrite=True).")
        crs = validate_project_crs(crs)
        if path.suffix == ".sponge":
            root = Path(tempfile.mkdtemp(prefix="sponge_"))
            owns = True
        else:
            if path.exists():
                shutil.rmtree(path)
            root = path
            root.mkdir(parents=True)
            owns = False
        for d in SUBDIRS:
            (root / d).mkdir(parents=True, exist_ok=True)
        _write_json(root / "manifest.json", Manifest(project_name=name, city=city, crs=crs).model_dump(mode="json"))
        _write_json(root / "parameters.json", default_parameters().to_json_dict())
        _write_json(root / "locks.json", Locks().model_dump(mode="json"))
        hist = History()
        hist.log("create", name=name, city=city, crs=crs)
        _write_json(root / "history.json", hist.model_dump(mode="json"))
        proj = cls(root, path if owns else None, owns)
        proj.save()
        log.info("created project '%s' at %s", name, path)
        return proj

    @classmethod
    def open(cls, path: PathLike) -> "Project":
        """Open a ``.sponge`` file (unpacked to a temporary folder) or a project folder."""
        path = Path(path)
        if not path.exists():
            raise ProjectError(f"{path} does not exist.")
        if path.is_dir():
            root, pkg, owns = path, None, False
        else:
            if not zipfile.is_zipfile(path):
                raise ProjectError(f"{path} is not a .sponge package.")
            root = Path(tempfile.mkdtemp(prefix="sponge_"))
            with zipfile.ZipFile(path) as z:
                for m in z.namelist():
                    target = (root / m).resolve()
                    if not str(target).startswith(str(root.resolve())):
                        raise ProjectError(f"Unsafe path in package: {m}")
                z.extractall(root)
            pkg, owns = path, True
        _migrate(root)
        proj = cls(root, pkg, owns)
        added = proj.parameters.merge_defaults(default_parameters())
        if added:
            log.info("added %d new default parameters: %s", len(added), ", ".join(added))
        return proj

    def save(self, path: Optional[PathLike] = None) -> Path:
        """Write state files and, for packages, re-zip to ``path`` (default: the opened file)."""
        self.manifest.modified = utcnow()
        _write_json(self.root / "manifest.json", self.manifest.model_dump(mode="json"))
        _write_json(self.root / "parameters.json", self.parameters.to_json_dict())
        _write_json(self.root / "locks.json", self.locks.model_dump(mode="json"))
        _write_json(self.root / "history.json", self.history.model_dump(mode="json"))
        target = Path(path) if path else self.package_path
        if target is None:
            return self.root
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".sponge.tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(self.root.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(self.root).as_posix())
        os.replace(tmp, target)
        self.package_path = target
        return target

    def close(self) -> None:
        if self._owns_root and self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ file helpers
    def path(self, rel: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def exists(self, rel: str) -> bool:
        return (self.root / rel).exists()

    def read_json(self, rel: str) -> Any:
        return _read_json(self.root / rel)

    def write_json(self, rel: str, data: Any) -> None:
        _write_json(self.root / rel, data)

    def read_geojson(self, rel: str) -> Dict[str, Any]:
        if not self.exists(rel):
            return {"type": "FeatureCollection", "features": []}
        return self.read_json(rel)

    def write_geojson(self, rel: str, fc: Dict[str, Any], source_crs: Optional[str] = None) -> None:
        """Validate the CRS (reprojecting if needed) and write a FeatureCollection."""
        fc = ensure_project_crs(fc, self.manifest.crs, source_crs)
        self.write_json(rel, fc)

    def option_ids(self) -> List[str]:
        d = self.root / "options"
        return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []

    def option_dir(self, option_id: str) -> Path:
        d = self.root / "options" / option_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def locked_ids(self, option_id: str) -> List[str]:
        return list(self.locks.locked.get(option_id, []))


def _migrate(root: Path) -> None:
    manifest = _read_json(root / "manifest.json")
    version = manifest.get("schema_version", "0")
    while version != SCHEMA_VERSION:
        if version not in MIGRATIONS:
            raise ProjectError(
                f"Project schema version {version} is not supported by this engine "
                f"(expects {SCHEMA_VERSION})."
            )
        version = MIGRATIONS[version](root)
        log.info("migrated project schema to %s", version)
