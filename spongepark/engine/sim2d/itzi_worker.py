"""Runs one Itzi simulation in memory. Executed by Itzi's own Python (3.12+, see ``sim2d/itzi_model.py``), not
imported by the engine: it reads ``inputs.npz`` and ``config.json`` from a folder and writes
``outputs.npz`` and ``result.json`` there. Standard library, numpy and itzi only.

inputs.npz: dem, friction (Manning n), infiltration (mm/h, constant) or infiltration_steps (mm/h, one grid
per rain step: Horton or curve number worked out by the engine), rain_rates (mm/h per rain step),
rain_mask (1 where it rains), bctype (2 = open edge, 1 = closed).
config.json: cell_m, rain_dt_s, duration_s, record_s.
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from itzi.array_definitions import ARRAY_DEFINITIONS, ArrayCategory
from itzi.const import InfiltrationModelType, TemporalType
from itzi.data_containers import SimulationConfig, SurfaceFlowParameters
from itzi.providers.domain_data import DomainData
from itzi.providers.memory_input import MemoryRasterInputProvider, TimedRasterSlice
from itzi.providers.memory_output import MemoryRasterOutputProvider, MemoryVectorOutputProvider
from itzi.simulation_builder import SimulationBuilder


def main(folder: str) -> None:
    d = Path(folder)
    cfg = json.loads((d / "config.json").read_text())
    a = np.load(d / "inputs.npz")
    dem, friction, infil = a["dem"].astype(np.float32), a["friction"].astype(np.float32), a["infiltration"].astype(np.float32)
    rates, rain_mask, bctype = a["rain_rates"], a["rain_mask"].astype(np.float32), a["bctype"].astype(np.float32)
    rows, cols = dem.shape
    cell = float(cfg["cell_m"])
    start = datetime(2000, 1, 1)
    end = start + timedelta(seconds=float(cfg["duration_s"]))
    rain_dt = timedelta(seconds=float(cfg["rain_dt_s"]))

    # rain: one slice per run of equal intensity, then dry to the end
    slices, i = [], 0
    while i < len(rates):
        j = i
        while j + 1 < len(rates) and rates[j + 1] == rates[i]:
            j += 1
        t0, t1 = start + rain_dt * i, min(start + rain_dt * (j + 1), end)
        if t0 < end:
            slices.append(TimedRasterSlice(start_time=t0, end_time=t1, array=(rain_mask * float(rates[i])).astype(np.float32)))
        i = j + 1
    last = slices[-1].end_time if slices else start
    if last < end:
        slices.append(TimedRasterSlice(start_time=last, end_time=end, array=np.zeros((rows, cols), np.float32)))

    domain = DomainData(north=rows * cell, south=0.0, east=cols * cell, west=0.0, rows=rows, cols=cols, crs_wkt="")
    inputs = {x.key: None for x in ARRAY_DEFINITIONS if ArrayCategory.INPUT in x.category}
    inputs.update(dem="dem", friction="friction", rain="rain", infiltration="infiltration", bctype="bctype")
    outputs = {x.key: None for x in ARRAY_DEFINITIONS if ArrayCategory.OUTPUT in x.category}
    want = ["water_depth", "v", "qx", "qy", "mean_infiltration", "mean_boundary_flow"]
    for k in want:
        if k in outputs:
            outputs[k] = k
    # recorded every minute (peaks, totals); depth frames are kept every record_s for the replay
    step_s = min(60.0, float(cfg["record_s"]))
    sim_cfg = SimulationConfig(start_time=start, end_time=end, record_step=timedelta(seconds=step_s),
                               temporal_type=TemporalType.RELATIVE, input_map_names=inputs, output_map_names=outputs,
                               surface_flow_parameters=SurfaceFlowParameters(**cfg.get("surface", {})),
                               infiltration_model=InfiltrationModelType.CONSTANT)
    static = {"dem": dem, "friction": friction, "bctype": bctype}
    timed = {"rain": slices}
    if "infiltration_steps" in a.files:   # infiltration that changes through the storm
        steps = a["infiltration_steps"].astype(np.float32)
        isl = []
        for k in range(len(steps)):
            t0, t1 = start + rain_dt * k, min(start + rain_dt * (k + 1), end)
            if t0 < end:
                isl.append(TimedRasterSlice(start_time=t0, end_time=t1, array=steps[k]))
        if isl and isl[-1].end_time < end:
            isl.append(TimedRasterSlice(start_time=isl[-1].end_time, end_time=end, array=steps[-1]))
        timed["infiltration"] = isl
    else:
        static["infiltration"] = infil
    inp = MemoryRasterInputProvider({
        "domain_data": domain, "simulation_start_time": start, "simulation_end_time": end,
        "static_arrays": static, "timed_arrays": timed,
    })
    out = MemoryRasterOutputProvider({"out_map_names": {k: v for k, v in outputs.items() if v}})
    t = time.time()
    sim = (SimulationBuilder(sim_cfg, np.zeros((rows, cols), bool))
           .with_domain_data(domain).with_input_provider(inp).with_raster_output_provider(out)
           .with_vector_output_provider(MemoryVectorOutputProvider()).build())
    sim.initialize()
    while sim.sim_time < end:
        sim.update()
    cont = sim.get_continuity_data()
    sim.finalize()
    seconds = time.time() - t

    rec = out.output_maps_dict
    if cfg.get("debug"):
        for k, v in rec.items():
            if v:
                arrs = [np.asarray(x) for _, x in v]
                print(k, len(v), "nan", int(np.isnan(arrs[-1]).sum()), "max per record", [round(float(np.nanmax(x)), 4) if np.isfinite(x).any() else None for x in arrs][:12])

    def series(k):
        return rec.get(k) or []

    def secs(x):
        return x.total_seconds() if isinstance(x, timedelta) else (x - start).total_seconds()

    depth = series("water_depth")
    times_all = np.array([secs(t_) for t_, _ in depth])
    every = max(1, int(round(float(cfg["record_s"]) / step_s)))
    keep = [k for k in range(len(depth)) if k % every == 0 or k == len(depth) - 1]
    times = times_all[keep]
    frames = np.stack([np.nan_to_num(depth[k][1]) for k in keep]).astype(np.float16) if depth else np.zeros((0, rows, cols), np.float16)
    hmax = np.max([np.nan_to_num(a_) for _, a_ in depth], axis=0) if depth else np.zeros((rows, cols))
    vmax = np.max([np.nan_to_num(a_) for _, a_ in series("v")], axis=0) if series("v") else np.zeros((rows, cols))
    qx = np.mean([np.nan_to_num(a_) for _, a_ in series("qx")], axis=0) if series("qx") else np.zeros((rows, cols))
    qy = np.mean([np.nan_to_num(a_) for _, a_ in series("qy")], axis=0) if series("qy") else np.zeros((rows, cols))
    # mean rates per record (mm/h) -> total depth infiltrated per cell (m)
    infil_m = np.zeros((rows, cols))
    prev = 0.0
    for t_, a_ in series("mean_infiltration"):
        now = secs(t_)
        infil_m += np.nan_to_num(a_) * (now - prev) / 3600 / 1000
        prev = now
    np.savez_compressed(d / "outputs.npz", times_s=times, depth_m=frames, hmax=hmax, vmax=vmax, qx_mean=qx, qy_mean=qy,
                        infiltration_m=infil_m)
    (d / "result.json").write_text(json.dumps({
        "seconds": seconds, "frames": int(len(times)),
        "continuity": {k: float(v) for k, v in cont.model_dump().items()} if hasattr(cont, "model_dump")
        else {k: float(getattr(cont, k)) for k in ("new_domain_vol", "volume_change", "volume_error", "continuity_error")},
        "records": len(depth),
    }))


if __name__ == "__main__":
    main(sys.argv[1])
