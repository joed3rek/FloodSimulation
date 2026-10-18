"""A project that uses every file of the .sponge schema, for round-trip tests (Python and Unity)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict

from spongepark.engine.project import Project, Source
from spongepark.engine.project.schema import (EditLog, EditLogEntry, ElementRecord, ElementsFile, Proposal, Scenario,
                                              TerrainEdit, TerrainEdits)

X0, Y0 = 500000.0, 1400000.0

ELEMENTS = [
    {"id": "RG1", "type": "rain_garden", "source": "proposal", "locked": True,
     "geometry": {"type": "Polygon", "coordinates": [[[X0, Y0], [X0 + 12.5, Y0], [X0 + 12.5, Y0 + 8], [X0, Y0 + 8], [X0, Y0]]]},
     "parameters": {"depth_m": 0.25, "soil_media_depth_m": 0.6, "storage_layer_depth_m": 0.3, "side_slope_h_v": 3,
                    "outlet": {"type": "orifice", "diameter_m": 0.05, "coefficient": 0.61}},
     "infiltration_rate_mm_hr": 12.7, "area_m2": 100.0, "storage_volume_m3": 41.3, "contributing_area_m2": 1850.0,
     "drawdown_time_hr": 19.7, "connections": {"inflow_from": ["S1", "S2"], "outflow_to": "DP1", "overflow_to": "OUT"},
     "soil_zone": "Z-red-loam", "param_sources": {"infiltration_rate_mm_hr": "soil zone Z-red-loam"},
     "notes": "Kept clear of the neem tree (Azadirachta indica) root zone — 3 m.",
     "results": {"10": {"peak_inflow_m3_s": 0.084, "max_depth_m": 0.21, "overflowed": False, "time_to_drain_hr": 18.5},
                 "100": {"peak_inflow_m3_s": 0.19, "max_depth_m": 0.25, "overflowed": True}}},
    {"id": "SW1", "type": "bioswale", "source": "designer",
     "geometry": {"type": "LineString", "coordinates": [[X0 - 5, Y0 + 20], [X0 + 15, Y0 + 22.25], [X0 + 40, Y0 + 21]]},
     "parameters": {"width_m": 2.5, "depth_m": 0.3, "side_slope_h_v": 4, "longitudinal_slope_pct": 1.2,
                    "manning_n": 0.24, "check_dam_spacing_m": 10, "dam_height_m": 0.15},
     "connections": {"inflow_from": ["S3"], "outflow_to": "RG1"}},
    {"id": "DP1", "type": "detention_pond", "source": "proposal",
     "geometry": {"type": "Polygon", "coordinates": [[[X0 + 50, Y0], [X0 + 80, Y0], [X0 + 80, Y0 + 25], [X0 + 50, Y0 + 25], [X0 + 50, Y0]]]},
     "parameters": {"depth_m": 1.2, "side_slope_h_v": 3, "freeboard_m": 0.3, "invert_elev_m": 897.35,
                    "safety_bench_width_m": 1.5, "overflow_weir_length_m": 2.0,
                    "outlet": {"type": "orifice", "diameter_m": 0.15}}},
    {"id": "RW1", "type": "recharge_well", "source": "designer",
     "geometry": {"type": "Point", "coordinates": [X0 + 30, Y0 + 10]},
     "parameters": {"diameter_m": 1.2, "well_depth_m": 6.0, "seepage_rate_mm_hr": 40.0},
     "infiltration_rate_mm_hr": 40.0, "future_field": {"kept": [1, 2, 3]}},   # a field a later version adds
]


def build(path: Path) -> Path:
    """Write a .sponge that fills every modelled file, plus binary and GeoJSON files to carry through."""
    p = Project.create(path, "Round trip park — HSR", overwrite=True)
    p.parameters.set("rain.design_return_period_yr", 25, source=Source.DESIGNER, note="target storm")
    p.parameters.set("soil.Z-red-loam.infiltration_mm_hr", 12.7, unit="mm/hr", source=Source.SITE_MEASURED,
                     note="double-ring test, 2026-03-04")
    p.history.log("survey_import", file="8A MAIN PARK.dxf", layers=32, when="2026-10-01T09:30:00+05:30")
    p.locks.locked["opt"] = ["RG1"]
    for rec in ELEMENTS:
        ElementRecord.model_validate(rec)
    p.write_json("scenarios/opt/elements.json", {"schema_version": "1.1", "elements": ELEMENTS})
    p.write_json("scenarios/opt/scenario.json", Scenario(id="opt", name="Designer option", based_on="p1",
                                                          status="accepted", note="from proposal p1").model_dump(mode="json"))
    p.write_json("scenarios/baseline/scenario.json", Scenario(id="baseline", name="Existing", status="baseline").model_dump(mode="json"))
    p.write_json("scenarios/baseline/elements.json", ElementsFile().model_dump(mode="json"))
    edits = TerrainEdits(edits=[
        TerrainEdit(id="E1", kind="berm", geometry={"type": "LineString", "coordinates": [[X0, Y0 + 30], [X0 + 20, Y0 + 30]]},
                    height_m=0.4, width_m=1.5, scenario="opt"),
        TerrainEdit(id="E2", kind="lower", geometry={"type": "Point", "coordinates": [X0 + 5, Y0 + 5]}, radius_m=4,
                    strength_m=0.2)])
    p.write_json("terrain/edits.json", edits.model_dump(mode="json"))
    log = EditLog(entries=[
        EditLogEntry(scenario="opt", action="accept_and_edit", proposal_id="p1"),
        EditLogEntry(scenario="opt", action="resize", element_id="RG1", before={"area_m2": 80.0, "when": "2026-10-02T10:00:00Z"},
                     after={"area_m2": 100.0})])
    p.write_json("edit_log.json", log.model_dump(mode="json"))
    p.write_json("proposals/p1.json", Proposal(id="p1", mode="inverse", elements=[ElementRecord.model_validate(ELEMENTS[0])],
                                               metrics={"peak_reduction_pct": {"10": 46.2, "100": 18.9}, "cost_inr": 1250000},
                                               settings={"seed": 7, "generations": 40}).model_dump(mode="json"))
    # files outside the schema travel unchanged
    p.path("terrain/existing.tif").write_bytes(bytes(range(256)) * 64)
    p.write_json("site/boundary.geojson", {"type": "FeatureCollection", "features": []})
    p.path("scenarios/opt/swmm/model.inp").write_text("[TITLE]\nround trip\n", encoding="utf-8")
    out = p.save()
    p.close()
    return out


# ------------------------------------------------------------------ comparison
def _clean(v: Any) -> Any:
    """null and absent are the same; 3 and 3.0 are the same (Python compares them equal)."""
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def read_package(path: Path) -> Dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def differences(a: Path, b: Path, ignore_manifest=("modified", "app_version")) -> list:
    """What changed between two .sponge files: JSON compared by meaning, every other file byte for byte."""
    fa, fb = read_package(a), read_package(b)
    out = [f"only in {a.name}: {n}" for n in sorted(set(fa) - set(fb))]
    out += [f"only in {b.name}: {n}" for n in sorted(set(fb) - set(fa))]
    for n in sorted(set(fa) & set(fb)):
        if n.endswith(".json"):
            ja, jb = _clean(json.loads(fa[n])), _clean(json.loads(fb[n]))
            if n == "manifest.json":
                for k in ignore_manifest:
                    ja.pop(k, None)
                    jb.pop(k, None)
            if ja != jb:
                out.append(f"{n} differs")
        elif fa[n] != fb[n]:
            out.append(f"{n} bytes differ")
    return out
