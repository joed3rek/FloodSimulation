"""Project report (Phase 8): one self-contained HTML file (charts embedded) and a PDF of it.

Sections: headline results, site and data (survey quality, soils, rainfall), existing condition,
each option (layout, component schedule, earthworks, water balance, comparison, hydrographs, 2D
maximum depth, guideline findings), optimisation and performance curve, calibration, every parameter
with its source, assumptions and limitations, and the SWMM input files for independent review.

Every number is read from stored engine results (SWMM runs; the 2D model is labelled indicative).
"""

from __future__ import annotations

import base64
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..project import Project
from .export import write_charts

log = logging.getLogger(__name__)
TEMPLATES = Path(__file__).parent / "templates"
LIMITATIONS = [
    "SWMM is one-dimensional. Where water spreads on the ground comes only from the 2D model, which is indicative.",
    "Uncalibrated results are for comparing scenarios, not for absolute prediction.",
    "Results are sensitive to the design storm pattern and to infiltration values; peak flows in particular "
    "depend on how the 24-hour depth is distributed in time.",
    "Recharge well performance depends on subsurface data (strata infiltration rate, rock depth).",
    "Canopy interception is a bucket that fills first, with no evaporation during the storm.",
    "Water-quality benefits (wetlands, separators, floating wetlands) are not modelled.",
    "Grading only cuts: no berms or fill are designed; excavated soil is counted as export.",
    "Curve numbers and soil groups come from TR-55 (US data) until checked against local percolation tests.",
]


def _img(path: Path) -> Optional[str]:
    if path is None or not Path(path).exists():
        return None
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _fmt(v: Any, nd: int = 1) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e4 and nd <= 1):
        return f"{int(v):,}"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def _option(project: Project, oid: str, charts_dir: Path) -> Dict[str, Any]:
    base = f"options/{oid}"
    summ = project.read_json(f"{base}/results/summary.json")
    cmp_ = project.read_json(f"{base}/results/comparison.json") if project.exists(f"{base}/results/comparison.json") else None
    layout = project.read_json(f"{base}/layout_report.json") if project.exists(f"{base}/layout_report.json") else None
    charts = {}
    if oid != "baseline":
        try:
            files = write_charts(project, oid, charts_dir)
            charts = {f.stem.split("_" + oid)[0]: _img(f) for f in files}
        except Exception as ex:  # charts are optional in the report
            log.warning("charts for %s: %s", oid, ex)
    # component schedule: design values and the SWMM results for the largest storm
    rps = sorted(summ["return_periods"], key=int)
    res = {e["id"]: e for e in summ["return_periods"][rps[-1]]["elements"]} if rps else {}
    schedule = []
    for e in summ.get("elements", []):
        r = res.get(e["id"], {})
        schedule.append({
            "id": e["id"], "type": e["type"].replace("_", " "), "source": e.get("source", ""),
            "area": _fmt(e.get("area_m2"), 0), "depth": _fmt(e.get("max_ponding_depth_m") or e.get("well_depth_m") or e.get("dam_height_m"), 2),
            "storage": _fmt(e.get("storage_volume_m3")), "infiltration": _fmt(e.get("infiltration_rate_mm_hr"), 2),
            "drawdown_design": _fmt(e.get("drawdown_time_hr"), 0), "drawdown_swmm": _fmt(r.get("drawdown_hr"), 0),
            "contributing": _fmt(e.get("contributing_area_m2"), 0), "to": e.get("outflow_to") or e.get("overflow_to") or "",
        })
    balance = []
    for rp in rps:
        wb = summ["return_periods"][rp]["water_balance"]
        balance.append({"rp": rp, **{k: _fmt(v) for k, v in wb.items()}, "flags": summ["return_periods"][rp]["flags"]})
    earth = None
    if layout:
        e = layout.get("earthworks") or {"cut_m3": layout.get("cut_total_m3"), "fill_m3": 0, "net_export_m3": layout.get("cut_total_m3"),
                                         "by_element_m3": {}}
        earth = {"cut": _fmt(e["cut_m3"], 0), "fill": _fmt(e["fill_m3"], 0), "net": _fmt(e["net_export_m3"], 0),
                 "by_element": {k: _fmt(v, 1) for k, v in e.get("by_element_m3", {}).items()}}
    sim2d = []
    sdir = project.path(f"{base}/sim2d")
    if sdir.exists():
        for js in sorted(sdir.glob("rp*_summary.json"), key=lambda p: int(p.stem[2:].split("_")[0])):
            s = project.read_json(f"{base}/sim2d/{js.name}")
            rp = s["return_period_yr"]
            sim2d.append({"rp": rp, "img": _img(sdir / f"max_depth_rp{rp}.png"),
                          "flooded": _fmt(s["flooded_area_m2"], 0), "max_depth": _fmt(s["max_depth_m"], 2),
                          "continuity": _fmt(s["balance"]["continuity_error_pct"], 3),
                          "vs_swmm": _fmt((s.get("swmm_comparison") or {}).get("difference_pct_of_rainfall"), 1)})
    findings = project.read_json(f"{base}/guideline_findings.json") if project.exists(f"{base}/guideline_findings.json") else []
    return {
        "id": oid, "summary": summ, "comparison": cmp_, "layout": layout, "schedule": schedule, "balance": balance,
        "earthworks": earth, "charts": charts, "sim2d": sim2d, "findings": findings,
        "layout_img": _img(project.path(f"{base}/layout.png")),
        "area_pct": _fmt(summ.get("intervention_area_pct"), 1), "notes": summ.get("model_notes", []),
    }


def build_report(project: Project, option_ids: Optional[List[str]], out_dir: Path, pdf: bool = True) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = out_dir / "charts"
    if not project.exists("options/baseline/results/summary.json"):
        raise ValueError("run the baseline first: the report compares every option with the existing site.")
    option_ids = option_ids or [o for o in project.option_ids()
                                if o != "baseline" and not o.startswith("_") and project.exists(f"options/{o}/results/summary.json")]
    P = project.parameters
    params = [{"key": q.key, "value": _fmt(q.value, 3) if isinstance(q.value, float) else str(q.value)[:80], "unit": q.unit,
               "source": q.source.value, "confirmed": q.confirmed, "note": q.note} for q in P]
    unconfirmed = [p for p in params if not p["confirmed"] and p["source"] in ("default", "literature")]
    baseline = _option(project, "baseline", charts_dir)
    options = [_option(project, o, charts_dir) for o in option_ids]
    headline = []
    for o in options:
        c = o["comparison"]
        if not c:
            continue
        rows = {str(r["return_period_yr"]): r for r in c["rows"]}
        headline.append({"id": o["id"], "area_pct": o["area_pct"],
                         "design_storm": c["design_retention_storm_yr"],
                         "rows": [{"rp": rp, "kept_now": _fmt(r["baseline_retained_pct"], 0), "kept": _fmt(r["option_retained_pct"], 0),
                                   "peak": _fmt(r["peak_reduction_pct"], 0), "litres": _fmt((r["rainfall_total_m3"] - r["option_outflow_m3"]) * 1000, 0)}
                                  for rp, r in rows.items()]})
    qc = project.read_json("terrain/qc.json") if project.exists("terrain/qc.json") else None
    soils = project.read_geojson("site/soil_zones.geojson")["features"]
    rain = None
    if project.exists("rainfall/return_periods.csv"):
        import pandas as pd

        rain = pd.read_csv(project.path("rainfall/return_periods.csv")).to_dict("records")
    opt_rep = {m: project.read_json(f"optimise/{m}_report.json") for m in ("forward", "inverse")
               if project.exists(f"optimise/{m}_report.json")}
    curve = project.read_json("optimise/performance_curve.json") if project.exists("optimise/performance_curve.json") else None
    calib = project.read_json("calibration/report.json") if project.exists("calibration/report.json") else None
    # SWMM files for independent review
    swmm_dir = out_dir / "swmm"
    inps = []
    for oid in ["baseline"] + option_ids:
        src = project.path(f"options/{oid}/swmm")
        if src.exists():
            for f in sorted(src.glob("*.inp")):
                dest = swmm_dir / oid / f.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dest)
                inps.append(str(dest.relative_to(out_dir)).replace("\\", "/"))
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    env.filters["f"] = _fmt
    html = env.get_template("report.html.j2").render(
        project=project.manifest, generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        calibration=baseline["summary"]["calibration"], headline=headline, baseline=baseline, options=options,
        qc=qc, soils=[s["properties"] for s in soils], rain=rain, params=params, unconfirmed=unconfirmed,
        optimise=opt_rep, curve=curve, curve_img=_img(project.path("optimise/performance_curve.png")),
        pareto_imgs={m: _img(project.path(f"optimise/{m}_pareto.png")) for m in opt_rep},
        calib=calib, calib_img=_img(project.path("calibration/calibration.png")), inps=inps,
        limitations=LIMITATIONS, qc_img=_img(project.path("terrain/qc.png")),
        flow_img=_img(project.path("terrain/flow/flow.png")),
        hyetograph=P.value("rainfall.hyetograph_method"), storm_hr=P.value("rainfall.storm_duration_hr"),
        infiltration_method=P.value("swmm.infiltration_method"),
    )
    name = f"{project.manifest.project_name}_report".replace(" ", "_")
    html_path = out_dir / f"{name}.html"
    html_path.write_text(html, encoding="utf-8")
    out = {"html": str(html_path), "swmm_files": inps, "options": option_ids, "unconfirmed_parameters": len(unconfirmed)}
    if pdf:
        out["pdf"] = _pdf(html_path)
    project.history.log("report", path=str(html_path), options=option_ids)
    return out


def _pdf(html: Path) -> Optional[str]:
    """Print the HTML to PDF with a headless Edge or Chrome, when one is installed."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("chromium") or "", shutil.which("google-chrome") or "",
    ]
    exe = next((c for c in candidates if c and Path(c).exists()), None)
    if exe is None:
        log.warning("no Edge/Chrome found: open the HTML report and print it to PDF")
        return None
    pdf = html.resolve().with_suffix(".pdf")  # the browser resolves relative paths against its own folder
    cmd = [exe, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", html.resolve().as_uri()]
    try:
        subprocess.run(cmd, check=True, timeout=180, capture_output=True)
    except Exception as ex:
        log.warning("PDF printing failed: %s", ex)
        return None
    return str(pdf) if pdf.exists() else None
