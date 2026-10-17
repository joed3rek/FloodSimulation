"""Command line interface: every pipeline stage can be run on its own.

    spongepark project new park.sponge --name "Pilot park"
    spongepark rainfall import park.sponge rainfall.csv
    spongepark site import park.sponge subcatchments subs.geojson
    spongepark option import park.sponge manual layout.geojson
    spongepark run park.sponge baseline
    spongepark run park.sponge manual
    spongepark compare park.sponge manual
    spongepark example out/          # end-to-end synthetic example
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

import typer

from spongepark import __version__

app = typer.Typer(help="Sponge park stormwater design engine (EPA SWMM via PySWMM).", no_args_is_help=True)
project_app = typer.Typer(help="Create and inspect projects.", no_args_is_help=True)
params_app = typer.Typer(help="List, set and confirm parameters.", no_args_is_help=True)
rain_app = typer.Typer(help="Rainfall tables and design storms.", no_args_is_help=True)
site_app = typer.Typer(help="Site layers.", no_args_is_help=True)
option_app = typer.Typer(help="NbS layout options.", no_args_is_help=True)
terrain_app = typer.Typer(help="Terrain (synthetic test terrains in Phase 0).", no_args_is_help=True)
nbs_app = typer.Typer(help="Component catalogue and design guidelines.", no_args_is_help=True)
for sub, name in [(project_app, "project"), (params_app, "params"), (rain_app, "rainfall"), (site_app, "site"),
                  (option_app, "option"), (terrain_app, "terrain"), (nbs_app, "nbs")]:
    app.add_typer(sub, name=name)

SITE_LAYERS = {
    "boundary": "site/boundary.geojson",
    "subcatchments": "site/subcatchments.geojson",
    "external": "site/external_catchment.geojson",
    "soils": "site/soil_zones.geojson",
    "outfalls": "site/outfalls.geojson",
    "context": "site/context.geojson",
}


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging.")) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _open(path: Path):
    from spongepark.engine.project import Project

    return Project.open(path)


@app.command()
def version() -> None:
    """Show engine and SWMM versions."""
    import pyswmm
    import swmm.toolkit

    typer.echo(f"spongepark {__version__}; pyswmm {pyswmm.__version__}; swmm-toolkit {swmm.toolkit.__version__}")


# ------------------------------------------------------------------ project
@project_app.command("new")
def project_new(path: Path, name: str = typer.Option(...), city: str = "Bengaluru", crs: str = "EPSG:32643",
                overwrite: bool = False) -> None:
    """Create a .sponge project (or a project folder if PATH has no .sponge suffix)."""
    from spongepark.engine.project import Project

    with Project.create(path, name, city, crs, overwrite=overwrite):
        pass
    typer.echo(f"created {path}")


@project_app.command("info")
def project_info(path: Path) -> None:
    with _open(path) as p:
        m = p.manifest
        typer.echo(json.dumps(m.model_dump(mode="json"), indent=2))
        typer.echo(f"options: {', '.join(p.option_ids()) or '-'}")
        typer.echo(f"unconfirmed parameters: {len(p.parameters.unconfirmed())}")


# ------------------------------------------------------------------ params
@params_app.command("list")
def params_list(path: Path, unconfirmed: bool = False, prefix: str = "") -> None:
    with _open(path) as p:
        for q in p.parameters:
            if unconfirmed and not q.is_unconfirmed_default:
                continue
            if not q.key.startswith(prefix):
                continue
            flag = "" if q.confirmed else "  [UNCONFIRMED]"
            typer.echo(f"{q.key:55s} {q.value!s:>14} {q.unit:10s} {q.source.value}{flag}")


@params_app.command("set")
def params_set(path: Path, key: str, value: str, unit: Optional[str] = None,
               source: str = typer.Option("user", help="default | site measured | literature | user"),
               note: Optional[str] = None) -> None:
    """Set a parameter (value parsed as JSON when possible, e.g. 0.3, true, [1,2])."""
    from spongepark.engine.project import Source

    try:
        v = json.loads(value)
    except json.JSONDecodeError:
        v = value
    with _open(path) as p:
        p.parameters.set(key, v, unit, Source(source), note)
        p.history.log("param_set", key=key, value=v, source=source)
        p.save()


@params_app.command("confirm")
def params_confirm(path: Path, keys: List[str] = typer.Argument(None), all_: bool = typer.Option(False, "--all")) -> None:
    """Mark defaults as confirmed by the user (required before they appear unflagged in reports)."""
    with _open(path) as p:
        targets = [q.key for q in p.parameters.unconfirmed()] if all_ else (keys or [])
        for k in targets:
            p.parameters.confirm(k)
        p.history.log("param_confirm", keys=targets)
        p.save()
    typer.echo(f"confirmed {len(targets)} parameter(s)")


# ------------------------------------------------------------------ terrain
@terrain_app.command("synthetic")
def terrain_synthetic(path: Path, kind: str = typer.Option("planar", help="planar | v_valley | bowl"),
                      size: float = 100.0, cell: float = 0.5) -> None:
    from spongepark.engine.terrain import GENERATORS, write_geotiff

    with _open(path) as p:
        dem = GENERATORS[kind](size_m=(size, size), cell_size=cell)
        dem.crs = p.manifest.crs
        write_geotiff(dem, p.path("terrain/existing.tif"))
        p.history.log("terrain_synthetic", kind=kind, size=size, cell=cell)
        p.save()


# ------------------------------------------------------------------ rainfall
@rain_app.command("import")
def rain_import(path: Path, csv: Path, source: str = "site measured") -> None:
    """Import a return-period table (24 h depths or IDF depths/intensities per duration)."""
    from spongepark.engine.project import Source
    from spongepark.engine.rainfall import RainfallTable

    with _open(path) as p:
        t = RainfallTable.from_csv(csv)
        t.to_csv(p.path("rainfall/return_periods.csv"))
        p.parameters.set("rainfall.input_kind", t.kind(), "-", Source(source), note=f"imported from {csv.name}")
        p.history.log("rainfall_import", file=csv.name, kind=t.kind())
        p.save()
    typer.echo(f"imported {t.kind()} table: return periods {t.return_periods}")


@rain_app.command("storms")
def rain_storms(path: Path, user_csv: Optional[Path] = None) -> None:
    """Generate design storm hyetographs for every return period."""
    from spongepark.engine.pipeline import make_hyetographs

    with _open(path) as p:
        storms = make_hyetographs(p, user_csv)
        p.save()
    for rp, h in storms.items():
        typer.echo(f"{rp:>4} yr: {h.depth_mm:7.1f} mm, peak {h.peak_mm_hr:6.1f} mm/h ({h.method})")


# ------------------------------------------------------------------ site
@site_app.command("import")
def site_import(path: Path, layer: str, geojson: Path, source_crs: Optional[str] = None) -> None:
    """Import a site layer: boundary, subcatchments, external, soils, outfalls, context."""
    if layer not in SITE_LAYERS:
        raise typer.BadParameter(f"layer must be one of {', '.join(SITE_LAYERS)}")
    with _open(path) as p:
        p.write_geojson(SITE_LAYERS[layer], json.loads(geojson.read_text(encoding="utf-8")), source_crs)
        p.history.log("site_import", layer=layer, file=geojson.name)
        p.save()


@site_app.command("check")
def site_check(path: Path) -> None:
    from spongepark.engine.site import Site

    with _open(path) as p:
        for msg in Site.load(p).validate() or ["site layers valid"]:
            typer.echo(msg)


@site_app.command("tr55")
def site_tr55(path: Path, duration_hr: float = 24.0) -> None:
    """TR-55 curve-number runoff per subcatchment: an independent check on SWMM volumes."""
    from spongepark.engine.hydrology import tr55
    from spongepark.engine.pipeline import rainfall_table
    from spongepark.engine.site import Site

    with _open(path) as p:
        site = Site.load(p)
        table = rainfall_table(p)
        rps = [float(r) for r in p.parameters.value("project.return_periods")]
        depths = {rp: table.depth(rp, duration_hr) for rp in rps}
        rows = tr55.site_check(site, depths, float(p.parameters.value("tr55.ia_ratio")))
        typer.echo(f"{'subcatchment':14s} {'HSG':3s} {'CNp':>5s} {'imp%':>5s} {'CNc':>5s}  "
                   + "  ".join(f"Q{rp:g}yr mm" for rp in rps))
        for r in rows:
            typer.echo(f"{r.id:14s} {r.hsg:3s} {r.cn_pervious:5.0f} {r.pct_imperv:5.0f} {r.cn_composite:5.1f}  "
                       + "  ".join(f"{r.runoff_mm[rp]:9.1f}" for rp in rps))
            for w in r.warnings:
                typer.echo(f"    ! {w}")
        tot = {rp: sum(r.runoff_m3[rp] for r in rows) for rp in rps}
        rain = {rp: sum(r.area_m2 for r in rows) * depths[rp] / 1000 for rp in rps}
        typer.echo("TR-55 runoff (m3):   " + "  ".join(f"{rp:g}yr {tot[rp]:.0f} ({100 * tot[rp] / rain[rp]:.0f} %)" for rp in rps))
        if p.exists("options/baseline/results/summary.json"):
            sm = p.read_json("options/baseline/results/summary.json")["return_periods"]
            swmm = {rp: sm[str(int(rp))]["water_balance"] for rp in rps if str(int(rp)) in sm}
            typer.echo("SWMM baseline (m3):  " + "  ".join(
                f"{rp:g}yr {w['outflow_total_m3'] + w['flooding_m3']:.0f} "
                f"({100 * (w['outflow_total_m3'] + w['flooding_m3']) / w['rainfall_total_m3']:.0f} %)"
                for rp, w in swmm.items()))
        typer.echo("TR-55 uses Ia = 0.2S and treats impervious areas as connected; see docs/references.md.")


# ------------------------------------------------------------------ options
@option_app.command("import")
def option_import(path: Path, option_id: str, geojson: Path, source_crs: Optional[str] = None) -> None:
    with _open(path) as p:
        p.write_geojson(f"options/{option_id}/components.geojson", json.loads(geojson.read_text(encoding="utf-8")),
                        source_crs)
        p.history.log("option_import", option=option_id, file=geojson.name)
        p.save()


@option_app.command("lock")
def option_lock(path: Path, option_id: str, element_ids: List[str]) -> None:
    with _open(path) as p:
        cur = set(p.locks.locked.get(option_id, []))
        p.locks.locked[option_id] = sorted(cur | set(element_ids))
        p.history.log("lock", option=option_id, elements=element_ids)
        p.save()


@option_app.command("check")
def option_check(path: Path, option_id: str) -> None:
    """Resolve elements and report design guideline findings (no SWMM run)."""
    from spongepark.engine.pipeline import prepare_option

    with _open(path) as p:
        p.parameters.set("guidelines.enforce_errors", False, confirmed=False)  # report everything
        els, findings = prepare_option(p, option_id)
    for e in els:
        typer.echo(f"{e.id:8s} {e.type:20s} {e.area_m2:8.1f} m2 {e.storage_volume_m3:8.1f} m3")
    for f in findings:
        typer.echo(f"[{f.severity}] {f.message} ({f.citation})")


# ------------------------------------------------------------------ run / compare
@app.command("run")
def run_cmd(path: Path, option_id: str, rp: List[int] = typer.Option(None, help="Return periods (default all).")) -> None:
    """Build and run SWMM for an option ('baseline' = existing site)."""
    from spongepark.engine.pipeline import run_option

    with _open(path) as p:
        s = run_option(p, option_id, rp or None)
        p.save()
    for k, v in s["return_periods"].items():
        wb = v["water_balance"]
        typer.echo(f"{k:>4} yr: retained {wb['retained_pct']:5.1f} %, peak {v['hydrograph']['peak_cms'] * 1000:7.1f} L/s, "
                   f"continuity {wb['swmm_runoff_continuity_pct']:+.2f}/{wb['swmm_routing_continuity_pct']:+.2f} %"
                   f"{'  FLAGGED' if v['flags'] else ''}")


@app.command("compare")
def compare_cmd(path: Path, option_id: str) -> None:
    from spongepark.engine.pipeline import compare

    with _open(path) as p:
        c = compare(p, option_id)
        p.save()
    for r in c["rows"]:
        typer.echo(f"{r['return_period_yr']:>4} yr: retained {r['baseline_retained_pct']:5.1f} -> {r['option_retained_pct']:5.1f} %, "
                   f"peak -{(r['peak_reduction_pct'] or 0):5.1f} %, lag {r['lag_hr'] if r['lag_hr'] is not None else '-'} h")
    typer.echo(f"largest storm fully retained: {c['design_retention_storm_yr'] or 'none'}")


@app.command("charts")
def charts_cmd(path: Path, option_id: str, out: Path = Path("charts")) -> None:
    from spongepark.engine.report.export import write_charts

    with _open(path) as p:
        for f in write_charts(p, option_id, out):
            typer.echo(f)


@app.command("perf-curve")
def perf_curve(path: Path, option_id: str, levels: str = "5,10,15,20,25") -> None:
    from spongepark.engine.metrics.performance import build_curve

    with _open(path) as p:
        pts = build_curve(p, option_id, [float(x) for x in levels.split(",")])
        p.save()
    for q in pts:
        typer.echo(f"{q['intervention_area_pct']:5.1f} % -> {q['design_retention_storm_yr'] or 'none'}")


# ------------------------------------------------------------------ catalogue
@nbs_app.command("catalogue")
def nbs_catalogue() -> None:
    from spongepark.engine.nbs import catalogue

    for k, c in catalogue().items():
        typer.echo(f"{k:22s} {c.label:36s} ch.{c.chapter or '-':5s} SWMM: {c.swmm}")


@nbs_app.command("rules")
def nbs_rules(component: Optional[str] = None) -> None:
    from spongepark.engine.nbs import rules

    for r in rules():
        if component and component not in r.applies_to:
            continue
        rng = f"{r.min if r.min is not None else ''}..{r.max if r.max is not None else ''} {r.unit}"
        typer.echo(f"[{r.severity:7s}] {r.id:38s} {r.field:28s} {rng:22s} {r.source} p.{r.page}")


# ------------------------------------------------------------------ example
@app.command()
def example(out: Path = typer.Argument(Path("examples/output")), curve: bool = True) -> None:
    """Create the synthetic example project and run it end to end."""
    from spongepark.engine.pipeline import compare, make_hyetographs, run_option
    from spongepark.engine.project import Project
    from spongepark.engine.report.export import write_charts
    from spongepark.examples.synthetic_park import populate

    out.mkdir(parents=True, exist_ok=True)
    pkg = out / "synthetic_park.sponge"
    with Project.create(pkg, "Synthetic sponge park", overwrite=True) as p:
        populate(p)
        make_hyetographs(p)
        run_option(p, "baseline")
        for oid in ("manual", "manual_wetland"):
            run_option(p, oid)
            c = compare(p, oid)
            typer.echo(f"{oid}: {c['intervention_area_pct']:.1f} % of site, fully retains up to "
                       f"{c['design_retention_storm_yr'] or 'none'} yr")
        if curve:
            from spongepark.engine.metrics.performance import build_curve

            build_curve(p, "manual", [5, 10, 15, 20, 25])
        p.save()
        for f in write_charts(p, "manual", out / "charts"):
            typer.echo(f"chart: {f}")
    typer.echo(f"project saved: {pkg}")


if __name__ == "__main__":
    app()
