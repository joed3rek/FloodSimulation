"""Run a SWMM model with PySWMM and collect results.

Volumes are taken from SWMM's own accumulators wherever they exist (runoff and
routing continuity, node/storage statistics, LID water balances, outfall
cumulative inflow). Per-link volumes (controlled release vs overflow) have no
SWMM accumulator, so they are integrated from link flows sampled every
``sample_step_s``; their sum is checked against the exact outfall volume.

Note: PySWMM 2.2 returns routing ``final_storage`` in ft3 for SI models, so final
stored volume is summed from node volumes instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from .builder import ModelSpec

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    inp_path: Path
    rpt_path: Path
    timeseries: pd.DataFrame
    runoff: Dict[str, float]  # SWMM runoff continuity (mm over total subcatchment area) + error %
    routing: Dict[str, float]  # SWMM routing continuity (m3) + error %
    total_area_m2: float
    storage: Dict[str, Dict[str, float]] = field(default_factory=dict)  # node -> stats (m3, m)
    lid: Dict[str, Dict[str, float]] = field(default_factory=dict)  # element id -> balance (m3)
    subcatch: Dict[str, Dict[str, float]] = field(default_factory=dict)
    outfall_volume_m3: Dict[str, float] = field(default_factory=dict)
    link_volume_m3: Dict[str, float] = field(default_factory=dict)
    node_flooding_m3: Dict[str, float] = field(default_factory=dict)
    node_final_volume_m3: Dict[str, float] = field(default_factory=dict)
    peak_outfall_inflow_cms: Dict[str, float] = field(default_factory=dict)

    @property
    def runoff_error_pct(self) -> float:
        return float(self.runoff["routing_error"])

    @property
    def routing_error_pct(self) -> float:
        return float(self.routing["routing_error"])


def run(spec: ModelSpec, inp_path: Path, sample_step_s: int = 60) -> RunResult:
    """Run ``inp_path`` (rendered from ``spec``) and collect results."""
    from pyswmm import LidGroups, Links, Nodes, Simulation, Subcatchments, SystemStats

    inp_path = Path(inp_path)
    rpt = inp_path.with_suffix(".rpt")
    out = inp_path.with_suffix(".out")
    rows: List[Dict[str, float]] = []
    with Simulation(str(inp_path), str(rpt), str(out)) as sim:
        nodes = Nodes(sim)
        links = Links(sim)
        subs = Subcatchments(sim)
        stats = SystemStats(sim)
        outfalls = [nodes[o] for o in spec.outfalls]
        st_nodes = {eid: nodes[em.node] for eid, em in spec.elements.items() if em.node}
        ctrl = {eid: links[em.controlled_link] for eid, em in spec.elements.items() if em.controlled_link}
        ovf = {eid: links[em.overflow_link] for eid, em in spec.elements.items() if em.overflow_link}
        lid_units = {}
        for eid, em in spec.elements.items():
            if em.is_lid:
                lid_units[eid] = list(LidGroups(sim)[em.subcatchment])[0]
        lid_subs = {eid: subs[em.subcatchment] for eid, em in spec.elements.items() if em.is_lid}
        sim.step_advance(sample_step_s)
        start = sim.start_time

        def sample() -> None:
            t = (sim.current_time - start).total_seconds() / 3600.0
            r: Dict[str, float] = {"time_hr": t}
            r["outflow_total_cms"] = float(sum(o.total_inflow for o in outfalls))
            for o, oid in zip(outfalls, spec.outfalls):
                r[f"outfall_{oid}_cms"] = float(o.total_inflow)
            for eid, n in st_nodes.items():
                r[f"depth_{eid}_m"] = float(n.depth)
                r[f"inflow_{eid}_cms"] = float(n.total_inflow)
                r[f"flooding_{eid}_cms"] = float(n.flooding)
            for eid, l in ctrl.items():
                r[f"controlled_{eid}_cms"] = float(l.flow)
            for eid, l in ovf.items():
                r[f"overflow_{eid}_cms"] = float(l.flow)
            for eid, u in lid_units.items():
                r[f"depth_{eid}_m"] = float(u.surface.depth) / 1000.0
                r[f"outflow_{eid}_cms"] = float(lid_subs[eid].runoff)
            rows.append(r)

        for _ in sim:
            sample()

        runoff = dict(stats.runoff_stats)
        routing = dict(stats.routing_stats)
        res = RunResult(
            inp_path=inp_path, rpt_path=rpt, timeseries=pd.DataFrame(rows),
            runoff=runoff, routing=routing, total_area_m2=spec.total_area_m2(),
        )
        for eid, n in st_nodes.items():
            s = dict(n.storage_statistics)
            s.update(n.statistics)
            s["cumulative_inflow_m3"] = float(n.cumulative_inflow)
            res.storage[eid] = s
            res.node_final_volume_m3[eid] = float(n.volume)
            res.node_flooding_m3[eid] = float(n.statistics["flooding_volume"])
        for eid, u in lid_units.items():
            wb = u.water_balance
            A = u.unit_area * u.number
            res.lid[eid] = {
                "inflow_m3": wb.inflow / 1000.0 * A,
                "evaporation_m3": wb.evaporation / 1000.0 * A,
                "infiltration_m3": wb.infiltration / 1000.0 * A,
                "surface_outflow_m3": wb.surface_flow / 1000.0 * A,
                "drain_outflow_m3": wb.drain_flow / 1000.0 * A,
                "initial_volume_m3": wb.initial_volume / 1000.0 * A,
                "final_volume_m3": wb.final_volume / 1000.0 * A,
            }
        for s in spec.subcatchments:
            res.subcatch[s.id] = dict(subs[s.id].statistics)
        for o, oid in zip(outfalls, spec.outfalls):
            res.outfall_volume_m3[oid] = float(o.cumulative_inflow)
            # Node.statistics segfaults for outfalls in PySWMM 2.2 when a model has no links; use outfall stats.
            res.peak_outfall_inflow_cms[oid] = float(o.outfall_statistics["peak_flowrate"])
    # SWMM state cannot be read before the first step; add the t = 0 row (no flow yet,
    # storage at its initial depth, i.e. the permanent pool for wet ponds).
    first = {c: 0.0 for c in res.timeseries.columns}
    for eid, em in spec.elements.items():
        if em.node:
            first[f"depth_{eid}_m"] = em.pool_depth_m
    res.timeseries = pd.concat([pd.DataFrame([first]), res.timeseries], ignore_index=True)
    ts = res.timeseries
    t_s = ts["time_hr"].to_numpy() * 3600.0
    for col in ts.columns:
        if col.startswith(("controlled_", "overflow_")):
            v = ts[col].to_numpy()
            res.link_volume_m3[col[:-4]] = float(np.sum(0.5 * (v[1:] + v[:-1]) * np.diff(t_s)))
    log.info(
        "%s: runoff continuity %.3f %%, routing continuity %.3f %%",
        inp_path.name, res.runoff_error_pct, res.routing_error_pct,
    )
    return res


def node_initial_volume(res: RunResult) -> float:
    return float(sum(s.get("initial_volume", 0.0) for s in res.storage.values()))


def to_jsonable(d: Any) -> Any:
    if isinstance(d, dict):
        return {str(k): to_jsonable(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [to_jsonable(v) for v in d]
    if isinstance(d, (np.floating, np.integer)):
        return d.item()
    return d
