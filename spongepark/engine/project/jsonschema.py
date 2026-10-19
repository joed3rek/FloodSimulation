"""The shared JSON Schema of the ``.sponge`` file, generated from the pydantic models in ``schema.py``.

``spongepark schema export`` writes ``schema/sponge.schema.json`` (committed). The Unity data classes
are generated from that file (``spongepark schema csharp``), and a test fails if either is out of date,
so the Python models, the schema and the C# classes never drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from pydantic.json_schema import models_json_schema

from .schema import FILES, SCHEMA_VERSION

REPO = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO / "schema" / "sponge.schema.json"


def build_schema() -> Dict[str, Any]:
    models = sorted({m for m in FILES.values()}, key=lambda m: m.__name__)
    _, defs = models_json_schema([(m, "validation") for m in models], ref_template="#/$defs/{model}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://habitatcollective.in/spongepark/sponge.schema.json",
        "title": "Sponge Park project file (.sponge)",
        "description": "The JSON files inside a .sponge package. Each entry of 'files' names a path in the package "
                       "and the definition that describes it. Generated from spongepark/engine/project/schema.py.",
        "version": SCHEMA_VERSION,
        "files": {path: {"$ref": f"#/$defs/{m.__name__}", "map_of": path == "parameters.json"}
                  for path, m in FILES.items()},
        "$defs": defs["$defs"],
    }


def export(path: Path = SCHEMA_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validator_for(path_in_package: str):
    """A jsonschema validator for one file of the package (e.g. "manifest.json", "scenarios/<id>/elements.json")."""
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    key = path_in_package
    if key not in schema["files"]:
        parts = key.split("/")
        if parts[0] == "scenarios":
            key = f"scenarios/<id>/{parts[-1]}"
        elif parts[0] == "proposals":
            key = "proposals/<id>.json"
    entry = schema["files"][key]
    target = {"$ref": entry["$ref"]}
    if entry.get("map_of"):
        target = {"type": "object", "additionalProperties": {"$ref": entry["$ref"]}}
    return jsonschema.Draft202012Validator({**target, "$defs": schema["$defs"]})


def validate_package(root: Path) -> Dict[str, list]:
    """Validate every JSON file of an unpacked project folder. Returns {file: [errors]} (empty when valid)."""
    out: Dict[str, list] = {}
    files = ["manifest.json", "parameters.json", "history.json", "locks.json", "edit_log.json", "terrain/edits.json",
             "site/survey_layers.json", "site/flow_analysis.json", "onboarding.json"]
    files += [str(p.relative_to(root)).replace("\\", "/") for p in sorted((root / "scenarios").glob("*/*.json"))
              if p.name in ("elements.json", "scenario.json")]
    files += [str(p.relative_to(root)).replace("\\", "/") for p in sorted((root / "proposals").glob("*.json"))]
    for rel in files:
        f = root / rel
        if not f.exists():
            continue
        v = validator_for(rel)
        errs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in v.iter_errors(json.loads(f.read_text(encoding="utf-8")))]
        out[rel] = errs
    return out
