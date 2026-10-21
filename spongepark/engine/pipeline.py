"""Pipeline stages, each callable on its own (CLI, API, Rhino).

hyetographs -> prepare option (resolve + guideline checks) -> build/run SWMM for
every return period (baseline and option) -> metrics -> results in the project.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .metrics.water_balance import element_summary, peak_and_time, water_balance
from .nbs.components import NbSElement, has_elements, load_elements, resolve_element, save_elements
from .nbs.guidelines import Finding, check_elements
from .project.package import Project
from .rainfall.hyetograph import Hyetograph, design_storms
from .rainfall.tables import RainfallTable, check_return_periods
from .site.model import Site
from .swmm.builder import ModelSpec, build_spec, render_inp
from .swmm.runner import run, to_jsonable

log = logging.getLogger(__name__)

BASELINE = "baseline"
UNCALIBRATED = "uncalibrated: suitable for scenario comparison, not absolute prediction"


class PipelineError(RuntimeError):
    pass


# --------------------------------------------------------------------------- rainfall
def rainfall_table(project: Project) -> RainfallTable:
    if not project.exists("rainfall/return_periods.csv"):
        raise PipelineError("No rainfall table. Import one with `spongepark rainfall import`.")
    return RainfallTable.from_csv(
        project.path("rainfall/return_periods.csv"),
        short_duration_method=project.parameters.value("rainfall.short_duration_method"),
    )


def make_hyetographs(project: Project, user_csv: Optional[Path] = None) -> Dict[int, Hyetograph]:
    """Generate and store one design storm per return period."""
    p = project.parameters
    table = rainfall_table(project)
    rps = [int(r) for r in p.value("project.return_periods")]
    missing = check_return_periods(table, rps)
    if missing:
        raise PipelineError(f"Rainfall table lacks return periods: {missing}.")
    storms = design_storms(
        table, rps,
        method=p.value("rainfall.hyetograph_method"),
        duration_hr=float(p.value("rainfall.storm_duration_hr")),
        dt_min=float(p.value("rainfall.time_step_min")),
        peak_position=float(p.value("rainfall.alternating_block_peak_position")),
        huff_quartile=int(p.value("rainfall.huff_quartile")),
        user_csv=user_csv,
    )
    for rp, h in storms.items():
        h.to_csv(project.path(f"rainfall/hyetographs/rp{rp}.csv"))
    project.history.log("hyetographs", method=p.value("rainfall.hyetograph_method"), rps=rps, table_kind=table.kind())
    return storms


def load_hyetographs(project: Project) -> Dict[int, Hyetograph]:
    rps = [int(r) for r in project.parameters.value("project.return_periods")]
    if not all(project.exists(f"rainfall/hyetographs/rp{rp}.csv") for rp in rps):
        return make_hyetographs(project)
    method = str(project.parameters.value("rainfall.hyetograph_method"))
    return {rp: Hyetograph.from_csv(project.path(f"rainfall/hyetographs/rp{rp}.csv"), rp, method) for rp in rps}


# --------------------------------------------------------------------------- option
def prepare_option(project: Project, option_id: str, site: Optional[Site] = None) -> tuple:
    """Resolve elements against parameters and soils, run guideline checks, write them back."""
    from .site import outfalls, wells

    site = site or Site.load(project, option_id)
    # the existing recharge wells (survey, answered in Site setup) are in every scenario, the existing site too
    existing = wells.resolved(project, site)
    # exits with no way out (Site setup > Outfalls): water ponds against the edge, then spills to the road
    soil = site.soil_lookup(str(project.parameters.value("swmm.infiltration_method")).upper())
    edges = [resolve_element(e, project.parameters, soil) for e in outfalls.edge_elements(project, site)]
    if option_id == BASELINE:
        outfalls.wire(existing, edges)
        existing += edges
        _contributing_areas(existing, site)
        return existing, []
    if not has_elements(project, option_id):
        raise PipelineError(f"Scenario '{option_id}' has no elements.json.")
    method = str(project.parameters.value("swmm.infiltration_method")).upper()
    raw = load_elements(project, option_id)
    locked = set(project.locked_ids(option_id))
    elements = []
    for e in raw:
        if e.id in locked:
            e.locked = True
        elements.append(resolve_element(e, project.parameters, site.soil_lookup(method)))
    _contributing_areas(elements, site)
    findings = check_elements(elements)
    save_elements(project, option_id, elements)
    existing = [e for e in existing if e.id not in {x.id for x in elements}]
    outfalls.wire(elements + existing, edges)
    existing += edges
    _contributing_areas(existing, site)   # nothing is routed to or from them
    elements += existing
    project.write_json(f"scenarios/{option_id}/guideline_findings.json", [f.model_dump() for f in findings])
    errors = [f for f in findings if f.severity == "error"]
    for f in findings:
        log.log(logging.WARNING if f.severity != "info" else logging.INFO, "[%s] %s (%s)", f.severity, f.message, f.citation)
    if errors and project.parameters.value("guidelines.enforce_errors"):
        raise PipelineError(
            f"{len(errors)} guideline error(s) in option '{option_id}': "
            + "; ".join(f"{f.message} [{f.citation}]" for f in errors)
        )
    return elements, findings


def _contributing_areas(elements: List[NbSElement], site: Site) -> None:
    """Contributing area = own footprint + subcatchments routed to it + everything upstream (m2)."""
    sub_area = {s.id: s.shape().area for s in site.subcatchments + site.external}
    by_id = {e.id: e for e in elements}
    memo: Dict[str, float] = {}

    def area(eid: str, stack: tuple = ()) -> float:
        if eid in memo:
            return memo[eid]
        if eid in stack:
            raise PipelineError("routing loop through " + " -> ".join(stack + (eid,)))
        e = by_id[eid]
        a = float(e.area_m2 or 0.0) + sum(sub_area.get(s, 0.0) for s in e.inflow_from)
        for u in elements:
            if eid in (u.outflow_to, u.overflow_to):
                a += area(u.id, stack + (eid,))
        memo[eid] = a
        return a

    for e in elements:
        e.contributing_area_m2 = area(e.id)


def run_option(
    project: Project,
    option_id: str,
    return_periods: Optional[List[int]] = None,
    site: Optional[Site] = None,
) -> Dict[str, Any]:
    """Build and run SWMM for every return period; store time series and summaries."""
    p = project.parameters
    site = site or Site.load(project, option_id)
    storms = load_hyetographs(project)
    rps = return_periods or sorted(storms)
    elements, findings = prepare_option(project, option_id, site)
    spec = build_spec(site, elements, p, option_id)
    odir = project.option_dir(option_id)
    (odir / "swmm").mkdir(exist_ok=True)
    (odir / "results").mkdir(exist_ok=True)
    title = f"{project.manifest.project_name} / {option_id}"
    (odir / "model.inp").write_text(render_inp(spec, site, p, storms, max(storms), title), encoding="utf-8")
    limit = float(p.value("swmm.continuity_error_limit_pct"))
    threshold = float(p.value("nbs.drawdown_threshold_m"))
    per_rp: Dict[str, Any] = {}
    for rp in rps:
        inp = odir / "swmm" / f"rp{rp}.inp"
        inp.write_text(render_inp(spec, site, p, {rp: storms[rp]}, rp, title), encoding="utf-8")
        res = run(spec, inp, int(p.value("sim.sample_step_s")))
        ts = res.timeseries.copy()
        rain = storms[rp].intensity_mm_hr
        k = (ts["time_hr"] * 60.0 / storms[rp].dt_min).astype(int)
        ts.insert(1, "rain_mm_hr", [float(rain[i]) if 0 <= i < len(rain) else 0.0 for i in k])
        ts.to_parquet(odir / "results" / f"rp{rp}_timeseries.parquet", index=False)
        wb = water_balance(spec, res, storms[rp].depth_mm)
        flags = []
        for key in ("swmm_runoff_continuity_pct", "swmm_routing_continuity_pct", "closure_error_pct"):
            if abs(wb[key]) > limit:
                flags.append(f"{key} = {wb[key]:.2f} % exceeds {limit} %")
        if flags:
            log.warning("%s RP%s: %s", option_id, rp, "; ".join(flags))
        per_rp[str(rp)] = {
            "storm": {"depth_mm": storms[rp].depth_mm, "peak_mm_hr": storms[rp].peak_mm_hr,
                      "duration_hr": storms[rp].duration_hr, "method": storms[rp].method},
            "water_balance": wb,
            "hydrograph": peak_and_time(res.timeseries),
            "peak_outfall_inflow_cms": res.peak_outfall_inflow_cms,
            "elements": element_summary(spec, res, threshold),
            "timing": overflow_timing(spec, res),
            "flooded_locations": flooded_locations(spec, res, elements),
            "flags": flags,
            "rpt": str((Path("swmm") / f"rp{rp}.rpt").as_posix()),
        }
    # verified results per return period on each element (brief 8.3), written back to elements.json
    by_id = {e.id: e for e in elements}
    for rp_key, r in per_rp.items():
        for row in r["elements"]:
            el = by_id.get(row["id"])
            if el is not None:
                el.results[rp_key] = {k: v for k, v in row.items() if k not in ("id", "type") and v is not None}
    if option_id != BASELINE:   # the existing wells live in site/wells.geojson, not in the scenario
        save_elements(project, option_id, [e for e in elements if e.source != "existing"])
    site_area = site.site_area_m2
    nbs_area = sum(e.area_m2 or 0.0 for e in elements if e.source != "existing")   # the design's own
    summary = {
        "option_id": option_id,
        "calibration": project.manifest.calibration_status if project.manifest.calibration_status != "uncalibrated"
        else UNCALIBRATED,
        "site_area_m2": site_area,
        "intervention_area_m2": nbs_area,
        "intervention_area_pct": 100.0 * nbs_area / site_area if site_area else None,
        "elements": [e.model_dump(mode="json", exclude={"geometry"}, exclude_none=True) for e in elements],
        "guideline_findings": [f.model_dump() for f in findings],
        "model_notes": spec.notes,
        "return_periods": per_rp,
        "unconfirmed_parameters": [q.key for q in p.unconfirmed()],
        "source_of_truth": "All hydrological numbers from EPA SWMM 5.2 (PySWMM, unmodified engine) "
                           "except canopy interception (computed outside SWMM).",
    }
    project.write_json(f"scenarios/{option_id}/results/summary.json", to_jsonable(summary))
    project.history.log("run_option", option=option_id, rps=rps, flags=sum(len(v["flags"]) for v in per_rp.values()))
    return summary


def overflow_timing(spec, res) -> Dict[str, Any]:
    """When water first leaves the site, and when uncontrolled overflow (weirs, flooding) starts (hr)."""
    from .metrics.water_balance import first_time_above

    ts = res.timeseries
    starts = [t for eid in spec.elements for t in (first_time_above(ts, f"overflow_{eid}_cms"),
                                                   first_time_above(ts, f"flooding_{eid}_cms")) if t is not None]
    return {"first_outflow_hr": first_time_above(ts, "outflow_total_cms"),
            "uncontrolled_overflow_start_hr": min(starts) if starts else None}


def flooded_locations(spec, res, elements: List[NbSElement]) -> List[Dict[str, Any]]:
    """Storage elements that flooded (water above the node's capacity), with where they are."""
    out = []
    by_id = {e.id: e for e in elements}
    for eid, vol in sorted(res.node_flooding_m3.items()):
        if vol > 1e-3:
            c = by_id[eid].footprint().centroid if eid in by_id else None
            out.append({"element": eid, "volume_m3": float(vol),
                        "x": float(c.x) if c is not None else None, "y": float(c.y) if c is not None else None})
    return out


def compare(project: Project, option_id: str, baseline_id: str = BASELINE) -> Dict[str, Any]:
    """Peak reduction, lag and design retention storm against the baseline."""
    opt = project.read_json(f"scenarios/{option_id}/results/summary.json")
    base = project.read_json(f"scenarios/{baseline_id}/results/summary.json")
    tol = float(project.parameters.value("nbs.retention_overflow_tolerance_fraction"))
    rows = []
    for rp in sorted(opt["return_periods"], key=int):
        o, b = opt["return_periods"][rp], base["return_periods"].get(rp)
        if b is None:
            continue
        ow, bw = o["water_balance"], b["water_balance"]
        oh, bh = o["hydrograph"], b["hydrograph"]
        peak_red = 100.0 * (1 - oh["peak_cms"] / bh["peak_cms"]) if bh["peak_cms"] > 0 else None
        lag = (oh["time_to_peak_hr"] - bh["time_to_peak_hr"]) if oh["time_to_peak_hr"] is not None and bh["time_to_peak_hr"] is not None else None
        rows.append({
            "return_period_yr": int(rp),
            "rainfall_mm": o["storm"]["depth_mm"],
            "rainfall_total_m3": ow["rainfall_total_m3"],
            "baseline_outflow_m3": bw["outflow_total_m3"] + bw["flooding_m3"],
            "option_outflow_m3": ow["outflow_total_m3"] + ow["flooding_m3"],
            "option_uncontrolled_m3": ow["uncontrolled_leaving_m3"],
            "baseline_retained_pct": bw["retained_pct"],
            "option_retained_pct": ow["retained_pct"],
            "baseline_peak_cms": bh["peak_cms"],
            "option_peak_cms": oh["peak_cms"],
            "peak_reduction_pct": peak_red,
            "lag_hr": lag,
            "fully_retained": (ow["outflow_total_m3"] + ow["flooding_m3"]) <= tol * ow["rainfall_total_m3"],
            "no_uncontrolled_overflow": ow["uncontrolled_leaving_m3"] <= tol * ow["rainfall_total_m3"],
            "flags": o["flags"] + b["flags"],
        })
    out = {
        "option_id": option_id,
        "baseline_id": baseline_id,
        "tolerance_fraction": tol,
        "rows": rows,
        "design_retention_storm_yr": _largest_consecutive(rows, "fully_retained"),
        "design_no_overflow_storm_yr": _largest_consecutive(rows, "no_uncontrolled_overflow"),
        "intervention_area_pct": opt["intervention_area_pct"],
    }
    project.write_json(f"scenarios/{option_id}/results/comparison.json", to_jsonable(out))
    return out


def _largest_consecutive(rows: List[Dict[str, Any]], key: str) -> Optional[int]:
    best = None
    for r in rows:
        if r[key]:
            best = r["return_period_yr"]
        else:
            break
    return best
