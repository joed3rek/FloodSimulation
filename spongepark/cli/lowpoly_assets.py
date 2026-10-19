"""The low-poly art the Unity app is dressed with, taken from three Asset Store packs the designer has downloaded:

- POLYGON - Starter Pack (Synty Studios): bushes, grass, flowers, rocks, manhole, sky dome, lily pads;
- Low-Poly Simple Nature Pack (JustCreate): bushes, grass, flowers, rocks;
- Low Poly Tree Pack (Broken Vector): trees;
- Realistic Tree 9 [Rainbow Tree] (Pixel Games): the park's trees (a broad, spreading broadleaf tree).

They are under the Asset Store EULA: the app may ship them, but this repository is public, so they are not
committed. `spongepark unity lowpoly-assets` reads each downloaded .unitypackage (from Unity's download folder) and
writes its files, with Unity's own .meta files so prefabs, models, materials and textures stay linked, into the app
project under the pack's own folder (git-ignored). Demo scenes and characters are left out. Unity then lists the
pieces the app uses (Sponge Park > List low-poly art, and every build); without them the app draws its own models.
"""

from __future__ import annotations

import gzip
import os
import tarfile
from pathlib import Path
from typing import Dict, List, Optional

STORE = Path(os.environ.get("APPDATA", "")) / "Unity" / "Asset Store-5.x"
PACKS = {
    "synty": STORE / "Synty Studios" / "3D ModelsEnvironments" / "POLYGON - Starter Pack - Art by Synty.unitypackage",
    "nature": STORE / "JustCreate" / "3D ModelsEnvironmentsLandscapes" / "Low-Poly Simple Nature Pack.unitypackage",
    "trees": STORE / "Broken Vector" / "3D ModelsVegetationTrees" / "Low Poly Tree Pack.unitypackage",
    "tree9": STORE / "Pixel Games" / "3D ModelsVegetationTrees" / "Realistic Tree 9 Rainbow Tree.unitypackage",
}
APP_PROJECT = Path(__file__).resolve().parents[2] / "unity" / "SpongeParkApp"
SKIP = ("/Characters/", "/Weapons/", "/FX/", "/Scenes/", "/Demo")   # not needed by the app
SKIP_EXT = (".unity", ".lighting", ".asset")                      # scenes, lighting and demo data


def _wanted(path: str) -> bool:
    return path.startswith("Assets/") and not any(s in path for s in SKIP) and not path.endswith(SKIP_EXT)


def extract_pack(package: Path, project: Path = APP_PROJECT) -> Dict[str, object]:
    """Write one pack's files (with their .meta files) into the project, under the pack's own folders."""
    paths: Dict[str, str] = {}
    files: Dict[str, Dict[str, bytes]] = {}
    with gzip.open(package, "rb") as gz, tarfile.open(fileobj=gz, mode="r|") as t:
        for m in t:
            parts = m.name.strip("./").split("/")
            if len(parts) != 2 or parts[1] not in ("pathname", "asset", "asset.meta"):
                continue
            guid, kind = parts
            data = t.extractfile(m).read()
            if kind == "pathname":
                paths[guid] = data.decode("utf-8").splitlines()[0]
            else:
                files.setdefault(guid, {})[kind] = data
    root = project.resolve()
    written, roots = 0, set()
    for guid, p in paths.items():
        if not _wanted(p):
            continue
        dst = (project / p).resolve()
        if root not in dst.parents:   # a path in the package never writes outside the project
            continue
        roots.add(p.split("/")[1])
        got = files.get(guid, {})
        if "asset" in got:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(got["asset"])
            written += 1
        else:
            dst.mkdir(parents=True, exist_ok=True)
        if "asset.meta" in got:
            Path(str(dst) + ".meta").write_bytes(got["asset.meta"])
    return {"package": package.name, "files": written, "folders": sorted(roots)}


def extract(packs: Optional[Dict[str, Path]] = None, project: Path = APP_PROJECT) -> List[Dict[str, object]]:
    out = []
    for name, path in (packs or PACKS).items():
        if not Path(path).exists():
            out.append({"package": Path(path).name, "missing": True})
            continue
        out.append(extract_pack(Path(path), project))
    return out
