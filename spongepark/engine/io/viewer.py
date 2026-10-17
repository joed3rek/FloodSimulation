"""Data for viewers (Unity app, WebGL results viewer).

The same payloads are served by the engine API and written to a *viewer bundle* (a folder of JSON
files) that the WebGL build reads from ``StreamingAssets/bundle`` when no engine is running.
Arrays are base64 little-endian (float32 heights, float16 depths); row 0 is north.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..project import Project
from ..terrain.raster import read_geotiff


def b64(a: np.ndarray, dtype: str = "<f4") -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode()


def terrain_payload(project: Project, option: Optional[str] = None, max_cells: int = 250_000) -> Dict[str, Any]:
    rel = f"options/{option}/terrain/graded.tif" if option and option != "baseline" else "terrain/existing.tif"
    d = read_geotiff(project.path(rel))
    z = np.where(d.z == d.nodata, np.nan, d.z)
    step = max(1, int(np.ceil(np.sqrt(z.size / max_cells))))
    z = z[::step, ::step]
    return {"option": option or "existing", "rows": z.shape[0], "cols": z.shape[1], "cell_m": d.cell_size * step,
            "origin": list(d.origin), "z_min": float(np.nanmin(z)), "z_max": float(np.nanmax(z)), "z": b64(z)}


def frames_payload(project: Project, option: str, rp: int, start: int = 0, count: int = 100000) -> Dict[str, Any]:
    d = np.load(project.path(f"options/{option}/sim2d/rp{rp}.npz"))
    frames = d["depth_m"][start:start + count]
    return {"label": "indicative", "option": option, "return_period_yr": rp,
            "times_s": d["times_s"][start:start + count].tolist(), "rows": int(frames.shape[1]),
            "cols": int(frames.shape[2]), "cell_m": float(d["cell_m"]), "origin": d["origin"].tolist(),
            "frames": b64(frames, "<f2")}


def retained_payload(project: Project, option: str, rp: int, every: int = 5) -> Dict[str, Any]:
    """Running litres retained on site from the SWMM time series: rainfall so far - water that left."""
    import pandas as pd

    df = pd.read_parquet(project.path(f"options/{option}/results/rp{rp}_timeseries.parquet"))
    s = project.read_json(f"options/{option}/results/summary.json")
    area = float(s["site_area_m2"])
    t = df["time_hr"].to_numpy()
    dt_s = np.diff(t, prepend=t[0]) * 3600
    rain_m3 = np.cumsum(df["rain_mm_hr"].to_numpy() / 1000 / 3600 * area * dt_s)
    out_cols = [c for c in df.columns if c == "outflow_total_cms"] or [c for c in df.columns if c.startswith("outfall_")]
    left = np.cumsum(df[out_cols].sum(axis=1).to_numpy() * dt_s)
    flood_cols = [c for c in df.columns if c.startswith("flooding_")]
    if flood_cols:
        left += np.cumsum(df[flood_cols].sum(axis=1).to_numpy() * dt_s)
    retained_l = np.maximum(rain_m3 - left, 0) * 1000
    idx = np.arange(0, len(t), max(1, every))
    return {"option": option, "return_period_yr": rp, "source": "SWMM time series (uncalibrated)",
            "time_hr": t[idx].tolist(), "rain_l": (rain_m3[idx] * 1000).tolist(), "retained_l": retained_l[idx].tolist(),
            "site_area_m2": area}


def sim2d_inputs_payload(project: Project, option: str, rp: int, cell_m: Optional[float] = None) -> Dict[str, Any]:
    """Inputs of the 2D model, so a GPU port can run exactly the same case and be verified."""
    from ..sim2d.run import prepare2d

    inp = prepare2d(project, option, rp, cell_m)
    els = inp.elements
    infil = {k: (b64(v) if isinstance(v, np.ndarray) else v) for k, v in inp.infil_params.items()}
    return {
        "rows": int(inp.mask.shape[0]), "cols": int(inp.mask.shape[1]), "cell_m": inp.dem.cell_size,
        "origin": list(inp.dem.origin), "z": b64(np.where(inp.mask, inp.dem.z, 0.0)), "mask": b64(inp.mask, "u1"),
        "n": b64(inp.n), "infiltration": infil, "rain_mm_hr": inp.rain_mm_hr.tolist(), "rain_dt_s": inp.rain_dt_s,
        "duration_s": inp.duration_s, "alpha": inp.alpha, "dt_max": inp.dt_max, "edge_drop_fraction": 0.01,
        "elements": None if els is None else {
            "ids": els.ids, "label": b64(els.label, "<i4"), "capacity_m3": els.capacity_m3.tolist(),
            "rate_m_s": els.rate_m_s.tolist(), "area_m2": els.area_m2.tolist()},
    }


def write_bundle(project: Project, out_dir: Path, options: Optional[List[str]] = None) -> Dict[str, Any]:
    """Write a viewer bundle: terrain, options, comparisons, retained curves and 2D frames."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    options = options or [o for o in project.option_ids() if not o.startswith("_")]
    manifest: Dict[str, Any] = {"project": project.manifest.project_name,
                                "calibration": project.manifest.calibration_status,
                                "label_2d": "indicative", "options": {}, "files": []}

    def put(name: str, data: Any) -> None:
        (out / name).write_text(json.dumps(data), encoding="utf-8")
        manifest["files"].append(name)

    put("terrain_existing.json", terrain_payload(project, None))
    for o in options:
        entry: Dict[str, Any] = {"return_periods": [], "sim2d": []}
        if o != "baseline" and project.exists(f"options/{o}/terrain/graded.tif"):
            put(f"terrain_{o}.json", terrain_payload(project, o))
            entry["terrain"] = f"terrain_{o}.json"
        if project.exists(f"options/{o}/components.geojson"):
            put(f"components_{o}.json", project.read_geojson(f"options/{o}/components.geojson"))
        if project.exists(f"options/{o}/results/summary.json"):
            s = project.read_json(f"options/{o}/results/summary.json")
            entry["return_periods"] = sorted(int(r) for r in s["return_periods"])
            entry["calibration"] = s["calibration"]
            for rp in entry["return_periods"]:
                put(f"retained_{o}_rp{rp}.json", retained_payload(project, o, rp))
        if project.exists(f"options/{o}/results/comparison.json"):
            put(f"comparison_{o}.json", project.read_json(f"options/{o}/results/comparison.json"))
        sdir = project.path(f"options/{o}/sim2d")
        if sdir.exists():
            for npz in sorted(sdir.glob("rp*.npz")):
                rp = int(npz.stem[2:])
                put(f"frames_{o}_rp{rp}.json", frames_payload(project, o, rp))
                entry["sim2d"].append(rp)
        manifest["options"][o] = entry
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
