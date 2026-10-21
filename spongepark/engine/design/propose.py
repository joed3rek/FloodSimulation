"""Suggested layouts for the design scenario, and SWMM verification of the design.

``suggest`` runs the layout generator ("quick": placement, sizing and grading from the flow and suitability
maps) or the NSGA-II optimiser with its surrogate ("optimise": several layouts trading area against retention,
each checked in SWMM). Each suggestion is kept in ``proposals/<id>.json`` with its elements and its SWMM results
(brief section 7: proposals retained for comparison).

``accept`` puts a proposal's elements into the design scenario (replacing what is there, or added to it), where
they stay marked as proposal elements until the designer changes them; ``verify`` runs SWMM on the design for every
return period and compares it with the existing site.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..nbs.components import elements_fc, has_elements
from ..pipeline import compare, run_option
from ..project import Project
from ..project.schema import Proposal, utcnow

log = logging.getLogger(__name__)


def _ensure_baseline(project: Project) -> None:
    if not project.exists("rainfall/hyetographs") or not any(project.path("rainfall/hyetographs").glob("rp*.csv")):
        raise ValueError("use the design rainfall first (Step 2).")
    if not project.exists("site/ground.json") and not project.exists("site/soil_zones.geojson"):
        raise ValueError("answer the ground questions first (Step 2).")
    if not project.exists("scenarios/baseline/results/summary.json"):
        run_option(project, "baseline")


def _rows(cmp_: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"return_period_yr": r["return_period_yr"], "retained_pct": r["option_retained_pct"],
             "existing_retained_pct": r["baseline_retained_pct"], "peak_reduction_pct": r["peak_reduction_pct"]}
            for r in cmp_["rows"]]


def _keep(project: Project, oid: str, method: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    """Save option ``oid`` as a proposal: its elements, the SWMM comparison, how it was made."""
    from ..nbs.components import load_elements, to_record

    cmp_ = compare(project, oid)
    els = load_elements(project, oid)
    pid = f"{method}_{utcnow().replace(':', '').replace('-', '')[:15]}_{oid}"
    area = sum(float(e.area_m2 or 0) for e in els)
    summary = project.read_json(f"scenarios/{oid}/results/summary.json")
    prop = Proposal(id=pid, mode=method, elements=[to_record(e) for e in els],
                    metrics={"rows": _rows(cmp_), "area_m2": area, "intervention_area_pct": summary.get("intervention_area_pct"),
                             "design_retention_storm_yr": cmp_.get("design_retention_storm_yr")},
                    settings={"from_option": oid, **extra})
    project.write_json(f"proposals/{pid}.json", prop.model_dump(mode="json"))
    fc = elements_fc(project, oid)
    return {"id": pid, "method": method, "elements": len(els), "area_m2": area,
            "types": sorted({e.type for e in els}), "rows": _rows(cmp_),
            "design_retention_storm_yr": cmp_.get("design_retention_storm_yr"), "features": fc}


def _sizing_note(project: Project, rep: Dict[str, Any]) -> str:
    """What the layout was sized for and, when the area budget stopped it, how much more the storm needs."""
    rp = rep["design_storm"]["return_period_yr"]
    els = [e for e in rep["elements"] if e["type"] != "bioswale"]
    need = sum(float(e["target_m3"] or 0) for e in els)
    held = sum(float(min(e["holds_m3_estimate"] or 0, e["target_m3"] or 0)) for e in els)
    pct = float(project.parameters.value("layout.max_area_pct"))
    note = f"Sized for the {rp}-year storm ({rep['design_storm']['runoff_depth_mm']:.0f} mm of runoff)."
    if any(e["limited_by"] == "area budget" for e in rep["elements"]) and need > held * 1.02:
        note += (f" The area budget ({pct:g} % of the park) stopped it: the elements hold about {held:.0f} m3 of the "
                 f"{need:.0f} m3 that storm sends them. A larger storm gives the same layout until the budget is "
                 "raised (Design > Targets).")
    return note


def suggest(project: Project, method: str = "quick", mode: str = "forward", effort: str = "normal",
            scenario_id: str = "design") -> Dict[str, Any]:
    """Suggested layouts, each checked in SWMM and kept as a proposal. The quick layout starts from the design's
    own elements (drawn by the designer, or locked): they are kept as they are and the layout fills around them."""
    from ..layout.generate import generate
    from ..nbs.components import load_elements, save_elements
    from ..optimise.run import optimise

    _ensure_baseline(project)
    out: List[Dict[str, Any]] = []
    if method == "quick":
        locked = set(project.locked_ids(scenario_id)) if has_elements(project, scenario_id) else set()
        own = [e for e in load_elements(project, scenario_id) if e.source == "designer" or e.locked or e.id in locked]             if has_elements(project, scenario_id) else []
        save_elements(project, "_suggest", own)   # the generator keeps them and places around them
        rep = generate(project, "_suggest")
        run_option(project, "_suggest")
        prop = _keep(project, "_suggest", "quick", {})
        prop["note"] = _sizing_note(project, rep)
        out.append(prop)
    elif method == "optimise":
        sizes = {"quick": dict(n_initial=6, rounds=1, per_round=2, pop_size=16, n_gen=10, n_final=3),
                 "normal": dict(n_initial=8, rounds=2, per_round=3, pop_size=24, n_gen=20, n_final=3)}[effort]
        res = optimise(project, mode, prefix="_opt", **sizes)
        for o in res["options"]:
            out.append(_keep(project, o["option_id"], "optimise", {"mode": mode, "overrides": o.get("overrides"),
                                                                    "types": o.get("types")}))
    else:
        raise ValueError("method is 'quick' or 'optimise'.")
    project.history.log("suggest", method=method, proposals=[p["id"] for p in out])
    return {"proposals": out}


def accept(project: Project, scenario_id: str, proposal_id: str, replace: bool = True) -> Dict[str, Any]:
    """Put a proposal's elements into the design scenario (carved and checked), marked as proposal elements."""
    from ..nbs.components import from_record, to_feature_collection
    from .edit import apply

    if not project.exists(f"proposals/{proposal_id}.json"):
        raise ValueError(f"no proposal {proposal_id}.")
    prop = project.read_json(f"proposals/{proposal_id}.json")
    new = to_feature_collection([from_record(r) for r in prop["elements"]])["features"]
    current = elements_fc(project, scenario_id)["features"] if has_elements(project, scenario_id) else []
    keep = [] if replace else current
    used = {f["properties"]["id"] for f in keep}
    for f in new:   # proposal elements keep their ids unless they clash with the designer's
        p = f["properties"]
        if p.get("source") == "designer":   # the designer's own elements, kept by the layout: unchanged
            used.add(p["id"])
            continue
        p["source"] = "proposal"
        p["proposal_id"] = proposal_id
        base, k = p["id"], 1
        while p["id"] in used:
            k += 1
            p["id"] = f"{base}_{k}"
        used.add(p["id"])
        for drop in ("area_m2", "storage_volume_m3", "drawdown_time_hr", "contributing_area_m2", "inflow_from",
                     "outflow_to", "overflow_to", "results", "locked"):
            p.pop(drop, None)
    fc = {"type": "FeatureCollection", "features": keep + new}
    return apply(project, scenario_id, fc, "accept", None, after={"proposal_id": proposal_id, "replace": replace})


def verify(project: Project, scenario_id: str) -> Dict[str, Any]:
    """SWMM on the design for every return period, compared with the existing site."""
    _ensure_baseline(project)
    run_option(project, scenario_id)
    cmp_ = compare(project, scenario_id)
    project.history.log("verify", scenario=scenario_id)
    return {"scenario": scenario_id, "rows": _rows(cmp_), "design_retention_storm_yr": cmp_.get("design_retention_storm_yr"),
            "design_no_overflow_storm_yr": cmp_.get("design_no_overflow_storm_yr")}
