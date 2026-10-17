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
layout_app = typer.Typer(help="Generated NbS layouts (Phase 4).", no_args_is_help=True)
rhino_app = typer.Typer(help="Rhino .3dm export and round trip (Phase 6).", no_args_is_help=True)
sim2d_app = typer.Typer(help="2D rain-on-grid surface model, indicative (Phase 6).", no_args_is_help=True)
optimise_app = typer.Typer(help="Optimisation with NSGA-II and a surrogate, SWMM-verified (Phase 5).",
                           no_args_is_help=True)
nbs_app = typer.Typer(help="Component catalogue and design guidelines.", no_args_is_help=True)
for sub, name in [(project_app, "project"), (params_app, "params"), (rain_app, "rainfall"), (site_app, "site"),
                  (option_app, "option"), (terrain_app, "terrain"), (layout_app, "layout"), (optimise_app, "optimise"),
                  (rhino_app, "rhino"), (sim2d_app, "sim2d"),
                  (nbs_app, "nbs")]:
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


# ------------------------------------------------------------------ layout
@layout_app.command("generate")
def layout_generate(path: Path, option: str = typer.Argument("auto"),
                    types: Optional[List[str]] = typer.Option(None, "--type", help="Element type (repeatable).")) -> None:
    """Place, size and grade NbS elements from the terrain, and rebuild the option's subcatchments."""
    from spongepark.engine.layout.generate import generate

    with _open(path) as p:
        r = generate(p, option, types or None)
        d = r["design_storm"]
        typer.echo(f"sized for the {d['return_period_yr']}-yr storm: {d['runoff_depth_mm']:.1f} mm runoff ({d['source']})")
        for e in r["elements"]:
            typer.echo(f"  {e['id']:6s} {e['type']:15s} {e['area_m2']:6.0f} m2  drains {e['drains_here_after_grading_m2']:6.0f} m2  "
                       f"holds ~{e['holds_m3_estimate']:5.1f} of {e['target_m3']:5.1f} m3 ({e['limited_by']})  -> {e['outflow_to']}")
        typer.echo(f"area {r['generated_area_m2']:.0f} of {r['area_budget_m2']:.0f} m2 budget; cut {r['cut_total_m3']:.0f} m3")
        p.save()
    typer.echo(f"next: spongepark option run {path} {option}")


@layout_app.command("regrade")
def layout_regrade(path: Path, option: str, run: bool = True) -> None:
    """Regrade an option from its current elements (after edits), rebuild subcatchments, rerun SWMM."""
    from spongepark.engine.layout.apply import regrade
    from spongepark.engine.pipeline import compare, run_option

    with _open(path) as p:
        r = regrade(p, option)
        for w in r["warnings"]:
            typer.echo(f"  ! {w}")
        typer.echo(f"regraded {len(r['elements'])} elements, cut {r['cut_total_m3']:.0f} m3")
        if run:
            run_option(p, option)
            compare(p, option)
        p.save()


# ------------------------------------------------------------------ rhino and 2D
@rhino_app.command("export")
def rhino_export(path: Path, option: str, out: Path) -> None:
    """Write terrain, contours, NbS (with all fields and SWMM results), analysis and context to .3dm."""
    from spongepark.rhino.roundtrip import export_3dm

    with _open(path) as p:
        r = export_3dm(p, option, out)
    typer.echo(f"written {r['path']}: {r['elements']} NbS elements, layers {', '.join(r['layers'])}")


@rhino_app.command("import")
def rhino_import(path: Path, option: str, drawing: Path, rerun: bool = True) -> None:
    """Apply a designer's .3dm edits: detect moved/resized/deleted/new elements, lock them, rerun."""
    from spongepark.rhino.roundtrip import import_3dm

    with _open(path) as p:
        r = import_3dm(p, option, drawing, rerun)
        for k, v in r["changes"].items():
            if v and k != "unchanged":
                typer.echo(f"  {k}: {', '.join(v)}")
        typer.echo("rerun: grading, subcatchments and SWMM" if r["rerun"] else "no changes")
        p.save()


@sim2d_app.command("run")
def sim2d_run(path: Path, option: str, rp: int, cell: Optional[float] = None) -> None:
    """2D surface simulation of an option for one return period (indicative), compared with SWMM."""
    from spongepark.engine.sim2d.run import run2d

    with _open(path) as p:
        s = run2d(p, option, rp, cell)
        b = s["balance"]
        typer.echo(f"{s['label']}")
        typer.echo(f"rain {b['rainfall_m3']:.1f} m3: leaves {b['outflow_m3']:.1f}, infiltrates "
                   f"{b['infiltration_ground_m3'] + b['infiltration_elements_m3']:.1f}, continuity "
                   f"{b['continuity_error_pct']:.3f} %; flooded >= {s['flood_depth_threshold_m']} m: "
                   f"{s['flooded_area_m2']:.0f} m2, max depth {s['max_depth_m']:.2f} m")
        if s["swmm_comparison"]:
            typer.echo(f"leaving the site vs SWMM: {s['swmm_comparison']['difference_pct_of_rainfall']:+.1f} % of rainfall")
        p.save()


@app.command("report")
def report(path: Path, out: Path, options: Optional[List[str]] = typer.Option(None, "--option"), pdf: bool = True) -> None:
    """Full HTML (and PDF) report: results, schedules, earthworks, water balance, parameters, SWMM files."""
    from spongepark.engine.report.html import build_report

    with _open(path) as p:
        r = build_report(p, options or None, out, pdf)
        p.save()
    typer.echo(f"report: {r['html']}")
    if r.get("pdf"):
        typer.echo(f"pdf: {r['pdf']}")
    typer.echo(f"{len(r['swmm_files'])} SWMM input files copied; {r['unconfirmed_parameters']} parameters still unconfirmed")


@app.command("calibrate")
def calibrate_cmd(path: Path, option: str, rainfall: Path, observed: Path,
                  target: str = typer.Option("outflow_total_cms", help="Model series: outflow_total_cms or depth_<id>_m."),
                  evaluations: int = 80, apply: bool = True) -> None:
    """Fit infiltration, roughness, depression storage and imperviousness factors to an observed event."""
    from spongepark.engine.swmm.calibrate import calibrate

    with _open(path) as p:
        r = calibrate(p, option, rainfall, observed, target, evaluations, apply)
        typer.echo(f"NSE {r['nse_uncalibrated']:.2f} -> {r['nse_calibrated']:.2f}; factors "
                   + ", ".join(f"{k} x{v:.2f}" for k, v in r["factors"].items()))
        typer.echo(r["note"])
        p.save()


@app.command("viewer-bundle")
def viewer_bundle(path: Path, out: Path, options: Optional[List[str]] = typer.Option(None, "--option")) -> None:
    """Write the JSON bundle the Unity WebGL viewer reads (terrain, options, retained curves, 2D frames)."""
    from spongepark.engine.io.viewer import write_bundle

    with _open(path) as p:
        m = write_bundle(p, out, options or None)
    typer.echo(f"written {len(m['files'])} files to {out} (options: {', '.join(m['options'])})")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the local engine API for the Unity app and Grasshopper components."""
    from spongepark.api.server import serve as _serve

    _serve(host, port)


# ------------------------------------------------------------------ optimise
@optimise_app.command("run")
def optimise_run(path: Path, mode: str = typer.Option("forward", help="forward | inverse"),
                 initial: Optional[int] = None, rounds: Optional[int] = None) -> None:
    """Search layouts (surrogate + NSGA-II), verify the Pareto options in SWMM and write them as options."""
    from spongepark.engine.optimise.run import optimise

    with _open(path) as p:
        r = optimise(p, mode, n_initial=initial, rounds=rounds)
        for h in r["rounds"]:
            typer.echo(f"round {h['round']}: {h['rows']} layouts in SWMM; surrogate "
                       f"{'used' if h['surrogate_used'] else 'not used'} {h.get('note', '')}")
        typer.echo(f"{r['evaluations_swmm']} SWMM-evaluated layouts, {r['pareto_size']} on the Pareto set")
        for o in r["options"]:
            ret = ", ".join(f"{k}-yr {v:.0f}%" for k, v in o["retained_pct"].items())
            typer.echo(f"  {o['option_id']}: {o['area_pct']:.1f} % of site, cut {o['cut_m3']:.0f} m3, "
                       f"design retention storm {o['design_retention_storm_yr'] or '-'} yr; retained {ret}")
        p.save()


@optimise_app.command("curve")
def optimise_curve(path: Path, budgets: Optional[List[float]] = typer.Option(None, "--budget")) -> None:
    """Performance curve: largest storm fully retained against area budget."""
    from spongepark.engine.optimise.run import performance_curve

    with _open(path) as p:
        out = performance_curve(p, budgets or None)
        for r in out["rows"]:
            typer.echo(f"  budget {r['budget_pct']:>4g} %: area {r['area_pct']:.1f} %, largest storm fully retained "
                       f"{r['design_retention_storm_yr'] or 'none'}")
        p.save()


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


@terrain_app.command("inspect")
def terrain_inspect(drawing: Path, out: Optional[Path] = None) -> None:
    """List a survey drawing's layers and write a suggested layer map to confirm."""
    import json

    from spongepark.engine.io import cad

    inv = cad.inventory(cad.read(drawing))
    typer.echo(f"{drawing.name}: {inv['dxf_version']}, header units {inv['insunits']}, extents {inv['extents_xy']}")
    for li in inv["layers"]:
        lv = f" levels {li['level_range'][0]:g}..{li['level_range'][1]:g} ({li['numeric_texts']})" if li["level_range"] else ""
        typer.echo(f"  {li['name'][:34]:34s} {str(li['suggested_role'] or '-'):15s} {li['entities']}{lv}")
    m = cad.suggest_layer_map(inv)
    out = out or drawing.with_suffix(".layer_map.json")
    out.write_text(json.dumps(m, indent=2), encoding="utf-8")
    typer.echo(f"suggested layer map: {out}  (check it, then set \"confirmed\": true)")
    if m["needs_decision"]:
        typer.echo(f"  decide what these layers mean: {', '.join(m['needs_decision'])}")


@terrain_app.command("preview")
def terrain_preview(drawing: Path, layer_map: Path = typer.Option(..., "--map"), out: Optional[Path] = None) -> None:
    """Draw what each layer-map role picks up, to compare with the drawing."""
    import json

    from spongepark.engine.io import cad

    out = out or layer_map.with_suffix(".png")
    cad.preview(cad.read(drawing), json.loads(layer_map.read_text(encoding="utf-8")), out, drawing.name)
    typer.echo(f"preview: {out}")


@terrain_app.command("standardise")
def terrain_standardise(drawing: Path, renames: Optional[Path] = typer.Option(None, help="Checked renames CSV."),
                        out: Optional[Path] = None, keep_duplicates: bool = False) -> None:
    """Rename a drawing's layers to the SP-* standard.

    Without --renames: write a suggested renames CSV to check. With it: write <name>_SP.dxf
    (original untouched) and a layer map for it."""
    import json

    from spongepark.engine.io import cad

    if renames is None:
        rs = cad.suggest_renames(cad.inventory(cad.read(drawing)))
        csv_path = drawing.with_suffix(".layer_renames.csv")
        cad.write_renames(rs, csv_path)
        for r in rs:
            typer.echo(f"  {r.old[:30]:30s} -> {r.new:24s} {r.confidence:8s} {r.entities:6d}")
        typer.echo(f"suggested renames: {csv_path}  (check 'partial' and 'none' rows, then run again with --renames)")
        return
    out = out or drawing.with_name(drawing.stem + "_SP.dxf")
    rep = cad.standardise(drawing, cad.read_renames(renames), out, dedupe=not keep_duplicates)
    m = cad.suggest_layer_map(cad.inventory(cad.read(out)))
    map_path = out.with_suffix(".layer_map.json")
    map_path.write_text(json.dumps(m, indent=2), encoding="utf-8")
    typer.echo(f"written {out}: {sum(x['entities'] for x in rep['moved'])} entities moved, "
               f"{rep['duplicates_removed_total']} exact duplicates removed, {len(rep['layers_removed'])} old layers removed")
    typer.echo(f"layer map: {map_path}  (still to confirm)")
    if m["needs_decision"]:
        typer.echo(f"  decide: {', '.join(m['needs_decision'])}")


@terrain_app.command("export-unity")
def terrain_export_unity(path: Path, out: Path, exaggeration: float = typer.Option(5.0, help="Vertical exaggeration."),
                         name: Optional[str] = None,
                         option: Optional[str] = typer.Option(None, help="Export this option's graded ground.")) -> None:
    """Textured OBJ of the terrain and its drainage, to drag into a Unity project's Assets."""
    from spongepark.engine.io.unity import export_obj

    with _open(path) as p:
        info = export_obj(p, out, name or (option or "terrain"), exaggeration, option_id=option)
    typer.echo(f"written {out}: {info['vertices']} vertices, {info['size_m'][0]:.0f} x {info['size_m'][1]:.0f} m, "
               f"relief {info['relief_m']:.2f} m shown x{exaggeration:g}")


@terrain_app.command("import")
def terrain_import(path: Path, drawing: Path, layer_map: Path = typer.Option(..., "--map"),
                   park_area_m2: Optional[float] = None) -> None:
    """Build the existing-ground DEM, boundary and context from a survey drawing."""
    import json

    from spongepark.engine.terrain.survey import import_survey

    with _open(path) as p:
        q = import_survey(p, drawing, json.loads(layer_map.read_text(encoding="utf-8")), park_area_m2)
        cv = q.get("spot_cross_validation") or {}
        typer.echo(f"DEM {q['source']['dem_shape']} cells at {q['source']['dem_cell_m']} m; levels "
                   f"{q['elevation_range_m'][0]:.2f}-{q['elevation_range_m'][1]:.2f} m")
        if cv:
            typer.echo(f"spot levels vs surface: RMSE {cv['rmse_m']:.3f} m, max {cv['max_abs_m']:.2f} m (n {cv['n']})")
        for i in q["issues"]:
            typer.echo(f"  ! {i}")
        p.save()
        typer.echo("written: " + ", ".join(q["outputs"]))


@terrain_app.command("delineate")
def terrain_delineate(path: Path) -> None:
    """Subcatchments, outfalls and natural depressions from the existing-ground DEM."""
    from spongepark.engine.hydrology.delineate import delineate

    with _open(path) as p:
        r = delineate(p)
        typer.echo(f"modelled area {r['domain_area_m2']:,.0f} m2 ({len(r['subcatchments'])} subcatchments), "
                   f"natural depressions {r['depression_total_m3']:.1f} m3")
        for s in r["subcatchments"]:
            typer.echo(f"  {s['subcatchment']:6s} -> {s['outfall']:7s} {s['area_m2']:8.0f} m2  slope {s['slope_pct_median']:.1f} %  "
                       f"flow length {s['flow_length_m']:.0f} m  impervious {s['pct_imperv']:.0f} %  "
                       f"depressions {s['depression_m3']:.1f} m3")
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


@app.command("screen")
def screen(parks_json: Path, rainfall_csv: Path, out: Optional[Path] = None) -> None:
    """Volume screen: proposed NbS storage against TR-55 catchment runoff, per park and storm."""
    import json
    from dataclasses import asdict

    import pandas as pd

    from spongepark.engine.hydrology.screening import screen_park

    d = json.loads(parks_json.read_text(encoding="utf-8"))
    r = pd.read_csv(rainfall_csv)
    r = r[r["duration_hr"] == 24]
    depths = {int(a): float(b) for a, b in zip(r["return_period_yr"], r["depth_mm"])}
    results = [screen_park(p, depths, d.get("park_cn", 74)) for p in d["parks"]]
    for s in results:
        fill = f"{s.fill_depth_mm:.1f} mm" if s.fill_depth_mm else "-"
        typer.echo()
        typer.echo(f"{s.name}: catchment {s.catchment_area_m2:,.0f} m2 ({s.catchment_area_m2 / s.park_area_m2:.0f}x park), "
                   f"CN {s.cn_weighted:.1f}, storage {s.storage_m3:.1f} m3 on {s.footprint_m2:.0f} m2; fills at {fill}")
        for k, q in s.runoff_m3.items():
            typer.echo(f"  {k:>10}: runoff {q:>10,.0f} m3   storage holds {s.capture_pct[k]:6.2f} %")
        for c in s.checks:
            typer.echo(f"  ! {c}")
    if out:
        out.write_text(json.dumps([asdict(s) for s in results], indent=2), encoding="utf-8")
        typer.echo(f"written: {out}")


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
