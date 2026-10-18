"""Water balance and performance metrics for one SWMM run.

Domain: the site plus any external catchment draining into it. Terms (m3):

    Rainfall (gross, site + external)
      = canopy interception
      + infiltration (surfaces) + infiltration (LID NbS) + infiltration (storage beds)
      + recharge (recharge wells)
      + evaporation
      + change in storage (surface/depression, LID media, storage nodes)
      + outflow leaving site (runoff + controlled release + overflow)
      + node flooding
      + closure error

Every term except interception comes from SWMM accumulators.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..swmm.builder import ModelSpec
from ..swmm.runner import RunResult

log = logging.getLogger(__name__)


def gross_rainfall_m3(spec: ModelSpec, depth_mm: float) -> Dict[str, float]:
    site = sum(s.area_m2 for s in spec.subcatchments if s.kind != "external")
    ext = sum(s.area_m2 for s in spec.subcatchments if s.kind == "external")
    return {"site": site * depth_mm / 1000.0, "external": ext * depth_mm / 1000.0}


def water_balance(spec: ModelSpec, res: RunResult, storm_depth_mm: float) -> Dict[str, float]:
    A = res.total_area_m2
    mm = lambda key: float(res.runoff[key]) * A / 1000.0  # noqa: E731  (SWMM runoff stats are mm over total area)
    gross = gross_rainfall_m3(spec, storm_depth_mm)
    gross_total = gross["site"] + gross["external"]
    net = mm("rainfall")
    lid_inf = sum(v["infiltration_m3"] for v in res.lid.values())
    lid_evap = sum(v["evaporation_m3"] for v in res.lid.values())
    lid_dS = sum(v["final_volume_m3"] - v["initial_volume_m3"] for v in res.lid.values())
    recharge = sum(s["exfil_loss"] for eid, s in res.storage.items() if spec.elements[eid].type == "recharge_well")
    bed_inf = sum(s["exfil_loss"] for eid, s in res.storage.items() if spec.elements[eid].type != "recharge_well")
    node_init = sum(s["initial_volume"] for s in res.storage.values())
    node_final = sum(res.node_final_volume_m3.values())
    out_role = {"runoff": 0.0, "controlled": 0.0, "overflow": 0.0}
    for node, v in res.outfall_volume_m3.items():
        out_role[spec.outfall_role.get(node, "runoff")] += v
    terms = {
        "rainfall_site_m3": gross["site"],
        "rainfall_external_m3": gross["external"],
        "rainfall_total_m3": gross_total,
        "interception_m3": gross_total - net,
        "infiltration_surfaces_m3": mm("infiltration") - lid_inf,
        "infiltration_nbs_m3": lid_inf + bed_inf,
        "infiltration_lid_m3": lid_inf,
        "infiltration_storage_beds_m3": bed_inf,
        "recharge_m3": recharge,
        "evaporation_m3": mm("evaporation") + float(res.routing["evaporation_loss"]),
        "storage_change_surface_m3": mm("final_storage") - mm("init_storage") - lid_dS,
        "storage_change_lid_m3": lid_dS,
        "storage_change_nodes_m3": node_final - node_init,
        "outflow_runoff_m3": out_role["runoff"],
        "outflow_controlled_m3": out_role["controlled"],
        "outflow_overflow_m3": out_role["overflow"],
        "flooding_m3": float(res.routing["flooding"]),
    }
    terms["outflow_total_m3"] = out_role["runoff"] + out_role["controlled"] + out_role["overflow"]
    losses = (
        terms["interception_m3"] + terms["infiltration_surfaces_m3"] + terms["infiltration_nbs_m3"]
        + terms["recharge_m3"] + terms["evaporation_m3"] + terms["storage_change_surface_m3"]
        + terms["storage_change_lid_m3"] + terms["storage_change_nodes_m3"] + terms["outflow_total_m3"]
        + terms["flooding_m3"]
    )
    terms["closure_error_m3"] = gross_total - losses
    terms["closure_error_pct"] = 100.0 * terms["closure_error_m3"] / gross_total if gross_total else 0.0
    terms["swmm_runoff_continuity_pct"] = res.runoff_error_pct
    terms["swmm_routing_continuity_pct"] = res.routing_error_pct
    leaving = terms["outflow_total_m3"] + terms["flooding_m3"]
    terms["retained_m3"] = gross_total - leaving
    terms["retained_pct"] = 100.0 * terms["retained_m3"] / gross_total if gross_total else 0.0
    terms["uncontrolled_leaving_m3"] = terms["outflow_runoff_m3"] + terms["outflow_overflow_m3"] + terms["flooding_m3"]
    return terms


def peak_and_time(ts: pd.DataFrame, col: str = "outflow_total_cms") -> Dict[str, Optional[float]]:
    v = ts[col].to_numpy()
    if v.max() <= 1e-9:
        return {"peak_cms": 0.0, "time_to_peak_hr": None, "centroid_hr": None}
    i = int(np.argmax(v))
    t = ts["time_hr"].to_numpy()
    return {"peak_cms": float(v[i]), "time_to_peak_hr": float(t[i]), "centroid_hr": float(np.sum(v * t) / np.sum(v))}


def simulated_drawdown_hr(ts: pd.DataFrame, depth_col: str, base_depth_m: float, threshold_m: float) -> Optional[float]:
    """Hours from peak depth until depth returns to within ``threshold_m`` of ``base_depth_m``.

    Returns 0 if the element never ponds, ``None`` if it has not drained by the end of the run.
    """
    d = ts[depth_col].to_numpy() - base_depth_m
    t = ts["time_hr"].to_numpy()
    if d.max() <= threshold_m:
        return 0.0
    i = int(np.argmax(d))
    after = np.nonzero(d[i:] <= threshold_m)[0]
    if after.size == 0:
        return None
    return float(t[i + after[0]] - t[i])


def first_time_above(ts: pd.DataFrame, col: str, threshold: float = 1e-5) -> Optional[float]:
    """First time (hr from storm start) a series exceeds ``threshold``; None if it never does."""
    if col not in ts:
        return None
    above = np.nonzero(ts[col].to_numpy() > threshold)[0]
    return float(ts["time_hr"].to_numpy()[above[0]]) if above.size else None


def element_summary(spec: ModelSpec, res: RunResult, threshold_m: float) -> List[Dict[str, Any]]:
    ts = res.timeseries
    out = []
    for eid, em in spec.elements.items():
        e = spec.element_objs[eid]
        row: Dict[str, Any] = {"id": eid, "type": e.type, "area_m2": em.area_m2, "storage_volume_m3": e.storage_volume_m3}
        dcol = f"depth_{eid}_m"
        if em.is_lid:
            lb = res.lid[eid]
            row.update(
                inflow_m3=lb["inflow_m3"], infiltration_m3=lb["infiltration_m3"], evaporation_m3=lb["evaporation_m3"],
                outflow_m3=lb["surface_outflow_m3"] + lb["drain_outflow_m3"], overflow_m3=None,
                max_ponding_m=float(ts[dcol].max()),
                drawdown_hr=simulated_drawdown_hr(ts, dcol, 0.0, threshold_m),
            )
        else:
            st = res.storage[eid]
            row.update(
                inflow_m3=st["cumulative_inflow_m3"], infiltration_m3=st["exfil_loss"], evaporation_m3=st["evap_loss"],
                outflow_m3=res.link_volume_m3.get(f"controlled_{eid}", 0.0),
                overflow_m3=res.link_volume_m3.get(f"overflow_{eid}", 0.0),
                max_depth_m=float(st["max_depth"]),
                max_depth_above_pool_m=float(st["max_depth"]) - em.pool_depth_m,
                pct_full=100.0 * float(st["max_depth"]) / em.crest_depth_m if em.crest_depth_m else None,
                flooding_m3=res.node_flooding_m3[eid],
                drawdown_hr=simulated_drawdown_hr(ts, dcol, em.pool_depth_m, threshold_m),
                overflow_start_hr=first_time_above(ts, f"overflow_{eid}_cms"),
                overflow_peak_cms=float(ts[f"overflow_{eid}_cms"].max()) if f"overflow_{eid}_cms" in ts else None,
                flooding_start_hr=first_time_above(ts, f"flooding_{eid}_cms"),
            )
        row["analytic_drawdown_hr"] = e.drawdown_time_hr
        out.append(row)
    return out
