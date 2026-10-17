"""Local engine API (FastAPI) used by the Unity app and the Grasshopper components.

Start it with ``spongepark serve`` (binds to 127.0.0.1 only). A client opens a project by path and
then calls the pipeline stages. Long stages (baseline, generate, run, optimise, 2D) run as jobs: the
call returns ``{"job": id}`` at once, and ``GET /jobs/{id}`` reports ``running``, ``done`` (with
the result) or ``error``. Add ``?wait=true`` to block until the job ends.

The API never computes anything itself: every route calls the same engine functions as the CLI.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from pydantic import BaseModel

from spongepark import __version__
from spongepark.engine.project import Project, Source

log = logging.getLogger(__name__)

app = FastAPI(title="spongepark engine", version=__version__,
              description="Local API to the sponge park engine. SWMM is the source of truth; 2D outputs are indicative.")

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

# the web app's dev server (vite) runs on another local port
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?",
                   allow_methods=["*"], allow_headers=["*"])
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
SERVED = {".png": "image/png", ".json": "application/json", ".geojson": "application/geo+json", ".html": "text/html",
          ".pdf": "application/pdf", ".dxf": "application/dxf", ".csv": "text/csv", ".inp": "text/plain",
          ".3dm": "application/octet-stream", ".tif": "image/tiff"}

_projects: Dict[str, Project] = {}
_locks: Dict[str, threading.Lock] = {}
_jobs: Dict[str, Dict[str, Any]] = {}
_pool = ThreadPoolExecutor(max_workers=2)


def _project(pid: str) -> Project:
    if pid not in _projects:
        raise HTTPException(404, f"project {pid} is not open")
    return _projects[pid]


def _job(pid: str, name: str, fn: Callable[[Project], Any], wait: bool) -> Dict[str, Any]:
    p = _project(pid)
    jid = uuid.uuid4().hex[:12]
    _jobs[jid] = {"id": jid, "project": pid, "name": name, "status": "running"}

    def work():
        with _locks[pid]:
            try:
                _jobs[jid].update(status="done", result=_jsonable(fn(p)))
            except Exception as ex:  # reported to the client, not raised in the server
                log.exception("job %s failed", name)
                _jobs[jid].update(status="error", error=str(ex), trace=traceback.format_exc()[-2000:])

    fut = _pool.submit(work)
    if wait:
        fut.result()
        return _jobs[jid]
    return {"job": jid, "status": "running"}


def _jsonable(x: Any) -> Any:
    from spongepark.engine.swmm.runner import to_jsonable

    return to_jsonable(x)


# ------------------------------------------------------------------ projects
class OpenRequest(BaseModel):
    path: str
    create: bool = False
    name: Optional[str] = None
    crs: str = "EPSG:32643"


@app.get("/health")
def health() -> Dict[str, Any]:
    # features let a client tell an engine started before an update from a current one
    return {"ok": True, "engine": __version__, "features": ["intake", "fs", "report", "calibrate", "sim2d"],
            "open_projects": list(_projects)}


@app.post("/projects/open")
def open_project(req: OpenRequest) -> Dict[str, Any]:
    path = Path(req.path)
    p = Project.create(path, req.name or path.stem, crs=req.crs) if req.create and not path.exists() else Project.open(path)
    pid = uuid.uuid4().hex[:8]
    _projects[pid], _locks[pid] = p, threading.Lock()
    return {"project": pid, **info(pid)}


@app.get("/projects/{pid}")
def info(pid: str) -> Dict[str, Any]:
    p = _project(pid)
    return {"name": p.manifest.project_name, "crs": p.manifest.crs, "calibration": p.manifest.calibration_status,
            "options": p.option_ids(), "unconfirmed_parameters": len(p.parameters.unconfirmed()),
            "has_terrain": p.exists("terrain/existing.tif"), "has_baseline": p.exists("options/baseline/results/summary.json"),
            "path": str(p.package_path or p.root),
            "return_periods": p.parameters.value("project.return_periods"),
            "has_soils": bool(p.read_geojson("site/soil_zones.geojson")["features"]),
            "has_rainfall": p.exists("rainfall/return_periods.csv")}


@app.post("/projects/{pid}/save")
def save(pid: str) -> Dict[str, Any]:
    with _locks[pid]:
        return {"saved": str(_project(pid).save())}


@app.post("/projects/{pid}/close")
def close(pid: str, save_first: bool = True) -> Dict[str, Any]:
    p = _project(pid)
    with _locks[pid]:
        if save_first:
            p.save()
        p.close()
    del _projects[pid]
    return {"closed": pid}


@app.get("/projects/{pid}/parameters")
def parameters(pid: str, prefix: str = "", unconfirmed: bool = False) -> List[Dict[str, Any]]:
    p = _project(pid)
    return [q.model_dump(mode="json") for q in p.parameters if q.key.startswith(prefix)
            and (not unconfirmed or q.is_unconfirmed_default)]


class ParamSet(BaseModel):
    value: Any
    unit: Optional[str] = None
    source: str = "user"
    note: Optional[str] = None


@app.put("/projects/{pid}/parameters/{key}")
def set_parameter(pid: str, key: str, body: ParamSet) -> Dict[str, Any]:
    p = _project(pid)
    with _locks[pid]:
        q = p.parameters.set(key, body.value, body.unit, Source(body.source), body.note)
        p.history.log("param_set", key=key, value=body.value, source=body.source, via="api")
    return q.model_dump(mode="json")


@app.post("/projects/{pid}/parameters/{key}/confirm")
def confirm_parameter(pid: str, key: str) -> Dict[str, Any]:
    p = _project(pid)
    p.parameters.confirm(key)
    return p.parameters.get(key).model_dump(mode="json")


# ------------------------------------------------------------------ pipeline stages
class SurveyRequest(BaseModel):
    drawing: str
    layer_map: Dict[str, Any]
    park_area_m2: Optional[float] = None


@app.post("/projects/{pid}/survey/inspect")
def survey_inspect(pid: str, drawing: str = Body(..., embed=True)) -> Dict[str, Any]:
    from spongepark.engine.io import cad

    inv = cad.inventory(cad.read(Path(drawing)))
    return {"inventory": _jsonable(inv), "suggested_layer_map": cad.suggest_layer_map(inv)}


@app.post("/projects/{pid}/survey/import")
def survey_import(pid: str, req: SurveyRequest, wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.terrain.survey import import_survey

    return _job(pid, "import_survey", lambda p: import_survey(p, Path(req.drawing), req.layer_map, req.park_area_m2), wait)


@app.post("/projects/{pid}/baseline")
def baseline(pid: str, delineate_first: bool = True, wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.hydrology.delineate import delineate
    from spongepark.engine.pipeline import make_hyetographs, run_option

    def fn(p: Project):
        rep = delineate(p) if delineate_first else None
        make_hyetographs(p)
        return {"delineation": rep, "summary": run_option(p, "baseline")}

    return _job(pid, "baseline", fn, wait)


class GenerateRequest(BaseModel):
    types: Optional[List[str]] = None
    overrides: Dict[str, Any] = {}
    run: bool = True


@app.post("/projects/{pid}/options/{oid}/generate")
def generate_option(pid: str, oid: str, req: GenerateRequest, wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.layout.generate import generate
    from spongepark.engine.pipeline import compare, run_option

    def fn(p: Project):
        rep = generate(p, oid, req.types, req.overrides or None)
        out = {"layout": rep}
        if req.run:
            run_option(p, oid)
            out["comparison"] = compare(p, oid)
        return out

    return _job(pid, f"generate {oid}", fn, wait)


@app.post("/projects/{pid}/options/{oid}/run")
def run(pid: str, oid: str, wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.pipeline import compare, run_option

    def fn(p: Project):
        s = run_option(p, oid)
        return {"summary": s, "comparison": compare(p, oid) if oid != "baseline" else None}

    return _job(pid, f"run {oid}", fn, wait)


@app.get("/projects/{pid}/options/{oid}/components")
def components(pid: str, oid: str) -> Dict[str, Any]:
    return _project(pid).read_geojson(f"options/{oid}/components.geojson")


@app.put("/projects/{pid}/options/{oid}/components")
def put_components(pid: str, oid: str, fc: Dict[str, Any] = Body(...), rerun: bool = True,
                   wait: bool = False) -> Dict[str, Any]:
    """Designer edits (e.g. from Grasshopper): elements sent here become designer elements and are locked."""
    from spongepark.engine.layout.apply import regrade
    from spongepark.engine.pipeline import compare, run_option

    def fn(p: Project):
        for f in fc.get("features", []):
            f["properties"]["source"] = "designer"
            f["properties"]["locked"] = True
        p.write_geojson(f"options/{oid}/components.geojson", fc)
        p.locks.locked[oid] = sorted({f["properties"]["id"] for f in fc.get("features", [])})
        out = {"regrade": regrade(p, oid)}
        if rerun:
            run_option(p, oid)
            out["comparison"] = compare(p, oid)
        return out

    return _job(pid, f"edit {oid}", fn, wait)


@app.get("/projects/{pid}/options/{oid}/summary")
def summary(pid: str, oid: str) -> Dict[str, Any]:
    return _project(pid).read_json(f"options/{oid}/results/summary.json")


@app.get("/projects/{pid}/options/{oid}/comparison")
def comparison(pid: str, oid: str) -> Dict[str, Any]:
    return _project(pid).read_json(f"options/{oid}/results/comparison.json")


@app.get("/projects/{pid}/options/{oid}/timeseries/{rp}")
def timeseries(pid: str, oid: str, rp: int, columns: Optional[str] = None) -> Dict[str, Any]:
    import pandas as pd

    df = pd.read_parquet(_project(pid).path(f"options/{oid}/results/rp{rp}_timeseries.parquet"))
    if columns:
        df = df[["time_hr"] + [c for c in columns.split(",") if c in df.columns]]
    return {"columns": list(df.columns), "data": df.to_numpy().tolist()}


class OptimiseRequest(BaseModel):
    mode: str = "forward"
    initial: Optional[int] = None
    rounds: Optional[int] = None


@app.post("/projects/{pid}/optimise")
def optimise(pid: str, req: OptimiseRequest, wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.optimise.run import optimise as opt

    return _job(pid, f"optimise {req.mode}", lambda p: opt(p, req.mode, n_initial=req.initial, rounds=req.rounds), wait)


@app.post("/projects/{pid}/options/{oid}/sim2d/{rp}")
def sim2d(pid: str, oid: str, rp: int, cell_m: Optional[float] = None, wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.sim2d.run import run2d

    return _job(pid, f"sim2d {oid} rp{rp}", lambda p: run2d(p, oid, rp, cell_m), wait)


# ------------------------------------------------------------------ data for viewers (Unity)
@app.get("/projects/{pid}/terrain")
def terrain(pid: str, option: Optional[str] = None, max_cells: int = 250_000) -> Dict[str, Any]:
    """Height grid as base64 little-endian float32, row 0 = north. NaN = no data."""
    from spongepark.engine.io.viewer import terrain_payload

    try:
        return terrain_payload(_project(pid), option, max_cells)
    except Exception as ex:
        raise HTTPException(404, str(ex))


@app.get("/projects/{pid}/options/{oid}/sim2d/{rp}/frames")
def sim2d_frames(pid: str, oid: str, rp: int, start: int = 0, count: int = 1000) -> Dict[str, Any]:
    """Depth frames (indicative) as base64 float16, frame-major, row 0 = north."""
    from spongepark.engine.io.viewer import frames_payload

    p = _project(pid)
    if not p.exists(f"options/{oid}/sim2d/rp{rp}.npz"):
        raise HTTPException(404, "run the 2D simulation first")
    return frames_payload(p, oid, rp, start, count)


@app.get("/projects/{pid}/options/{oid}/sim2d/{rp}/inputs")
def sim2d_inputs(pid: str, oid: str, rp: int, cell_m: Optional[float] = None) -> Dict[str, Any]:
    """Inputs of the 2D model (for the GPU port and its verification against the engine)."""
    from spongepark.engine.io.viewer import sim2d_inputs_payload

    return sim2d_inputs_payload(_project(pid), oid, rp, cell_m)


@app.get("/projects/{pid}/options/{oid}/sim2d/{rp}/summary")
def sim2d_summary(pid: str, oid: str, rp: int) -> Dict[str, Any]:
    return _project(pid).read_json(f"options/{oid}/sim2d/rp{rp}_summary.json")


@app.get("/projects/{pid}/options/{oid}/retained/{rp}")
def retained(pid: str, oid: str, rp: int, every: int = 5) -> Dict[str, Any]:
    """Running litres retained on site through the storm (SWMM time series)."""
    from spongepark.engine.io.viewer import retained_payload

    return retained_payload(_project(pid), oid, rp, every)


@app.post("/projects/{pid}/viewer-bundle")
def viewer_bundle(pid: str, out_dir: str = Body(..., embed=True), options: Optional[List[str]] = Body(None, embed=True),
                  wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.io.viewer import write_bundle

    return _job(pid, "viewer bundle", lambda p: write_bundle(p, Path(out_dir), options), wait)


# ------------------------------------------------------------------ exports and round trip
@app.post("/projects/{pid}/options/{oid}/export")
def export(pid: str, oid: str, out_dir: str = Body(..., embed=True),
           formats: List[str] = Body(["3dm", "dxf", "report"], embed=True), wait: bool = False) -> Dict[str, Any]:
    def fn(p: Project):
        out, d = {}, Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        if "3dm" in formats:
            from spongepark.rhino.roundtrip import export_3dm

            out["3dm"] = export_3dm(p, oid, d / f"{oid}.3dm")["path"]
        if "dxf" in formats and p.exists(f"options/{oid}/design.dxf"):
            import shutil

            out["dxf"] = str(shutil.copy(p.path(f"options/{oid}/design.dxf"), d / f"{oid}_design.dxf"))
        if "report" in formats:
            from spongepark.engine.report.html import build_report

            out["report"] = build_report(p, [oid], d)
        return out

    return _job(pid, f"export {oid}", fn, wait)


@app.post("/projects/{pid}/report")
def report(pid: str, out_dir: str = Body(..., embed=True), options: Optional[List[str]] = Body(None, embed=True),
           pdf: bool = Body(True, embed=True), wait: bool = False) -> Dict[str, Any]:
    """Full HTML (and PDF) report for the chosen options, with the SWMM files."""
    from spongepark.engine.report.html import build_report

    return _job(pid, "report", lambda p: build_report(p, options, Path(out_dir), pdf), wait)


@app.post("/projects/{pid}/options/{oid}/import-3dm")
def import_rhino(pid: str, oid: str, path: str = Body(..., embed=True), rerun: bool = True,
                 wait: bool = False) -> Dict[str, Any]:
    from spongepark.rhino.roundtrip import import_3dm

    return _job(pid, f"import 3dm {oid}", lambda p: import_3dm(p, oid, Path(path), rerun), wait)


@app.post("/video/encode")
def video_encode(folder: str = Body(..., embed=True), fps: int = Body(30, embed=True)) -> Dict[str, Any]:
    """Encode the Unity app's PNG frames to MP4 (bundled ffmpeg), for machines without ffmpeg."""
    from spongepark.engine.report.video import encode

    try:
        return {"video": str(encode(Path(folder), fps))}
    except Exception as ex:
        raise HTTPException(400, str(ex))


@app.get("/projects/{pid}/file")
def project_file(pid: str, path: str):
    """A file inside the project (images, JSON, reports), for the web app. Paths cannot leave the project."""
    from fastapi.responses import FileResponse

    p = _project(pid)
    target = (p.root / path).resolve()
    if not str(target).startswith(str(p.root.resolve())) or target.suffix.lower() not in SERVED:
        raise HTTPException(403, "not allowed")
    if not target.exists():
        raise HTTPException(404, f"{path} not found")
    return FileResponse(target, media_type=SERVED[target.suffix.lower()])


@app.get("/fs/list")
def fs_list(dir: Optional[str] = None, ext: str = ".sponge,.dxf,.dwg,.csv,.json,.3dm") -> Dict[str, Any]:
    """Folders and matching files, for the web app's file picker (local server only)."""
    d = Path(dir).expanduser() if dir else Path.cwd()
    if not d.exists() or not d.is_dir():
        raise HTTPException(404, f"{d} is not a folder")
    exts = {e.strip().lower() for e in ext.split(",") if e.strip()}
    items = []
    try:
        for c in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if c.name.startswith("."):
                continue
            if c.is_dir() and c.suffix.lower() != ".sponge":
                items.append({"name": c.name, "path": str(c), "kind": "folder"})
            elif c.suffix.lower() in exts:
                items.append({"name": c.name, "path": str(c), "kind": "file", "size": c.stat().st_size if c.is_file() else None})
    except PermissionError:
        raise HTTPException(403, f"cannot read {d}")
    return {"dir": str(d.resolve()), "parent": str(d.resolve().parent), "items": items}


@app.get("/fs/file")
def fs_file(path: str):
    """A report, drawing or image written outside the project (exports), for the web app (local server only)."""
    from fastapi.responses import FileResponse

    f = Path(path).expanduser().resolve()
    if f.suffix.lower() not in SERVED or not f.is_file():
        raise HTTPException(404, f"{path} not found or not an allowed file type")
    return FileResponse(f, media_type=SERVED[f.suffix.lower()], filename=None if f.suffix.lower() in (".html", ".png", ".pdf") else f.name)


class CalibrateRequest(BaseModel):
    option: str = "baseline"
    rainfall: str
    observed: str
    target: str = "outflow_total_cms"
    evaluations: int = 80
    apply: bool = True


@app.post("/projects/{pid}/calibrate")
def calibrate(pid: str, req: CalibrateRequest, wait: bool = False) -> Dict[str, Any]:
    from spongepark.engine.swmm.calibrate import calibrate as cal

    return _job(pid, "calibrate", lambda p: cal(p, req.option, Path(req.rainfall), Path(req.observed), req.target,
                                                 req.evaluations, req.apply), wait)


@app.get("/projects/{pid}/jobs")
def project_jobs(pid: str) -> List[Dict[str, Any]]:
    return [{k: v for k, v in j.items() if k != "result"} for j in _jobs.values() if j["project"] == pid]


# ------------------------------------------------------------------ survey intake (opening screen)
from fastapi import Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402


@app.post("/intake/upload")
async def intake_upload(request: Request, filename: str = Query(...)) -> Dict[str, Any]:
    """A drawing sent as the raw request body; stored in the workspace, then read."""
    from spongepark.engine.io import intake
    from spongepark.engine.io.cad import CadError

    try:
        path = intake.save_upload(filename, await request.body())
        return intake.start(path)
    except CadError as ex:
        raise HTTPException(400, str(ex))


@app.post("/intake/start")
def intake_start(path: str = Body(..., embed=True)) -> Dict[str, Any]:
    from spongepark.engine.io import intake
    from spongepark.engine.io.cad import CadError

    try:
        return intake.start(Path(path))
    except CadError as ex:
        raise HTTPException(400, str(ex))


@app.get("/intake/preview")
def intake_preview(path: str, layer: Optional[str] = None) -> Response:
    """The drawing with one layer highlighted (PNG)."""
    from spongepark.engine.io import intake

    return Response(intake.preview(Path(path), layer), media_type="image/png",
                    headers={"Cache-Control": "max-age=3600"})


class IntakeFinish(BaseModel):
    survey: str
    links: Dict[str, str]
    project_path: Optional[str] = None
    park_area_m2: Optional[float] = None
    contours_in_surface: bool = True
    units_scale_to_m: float = 1.0


@app.post("/intake/finish")
def intake_finish(req: IntakeFinish, wait: bool = False) -> Dict[str, Any]:
    """Clean the drawing, create the project and build the ground model (a job)."""
    from spongepark.engine.io import intake

    jid = uuid.uuid4().hex[:12]
    _jobs[jid] = {"id": jid, "project": None, "name": "survey intake", "status": "running"}

    def work():
        try:
            _jobs[jid].update(status="done", result=_jsonable(intake.finish(
                Path(req.survey), req.links, Path(req.project_path) if req.project_path else None,
                req.park_area_m2, req.contours_in_surface, req.units_scale_to_m)))
        except Exception as ex:
            log.exception("intake failed")
            _jobs[jid].update(status="error", error=str(ex))

    fut = _pool.submit(work)
    if wait:
        fut.result()
        return _jobs[jid]
    return {"job": jid, "status": "running"}


@app.get("/jobs/{jid}")
def job(jid: str) -> Dict[str, Any]:
    if jid not in _jobs:
        raise HTTPException(404, "unknown job")
    return _jobs[jid]


def _mount_web() -> None:
    """Serve the built web app at / (after every API route, so the API keeps priority)."""
    if WEB_DIST.exists() and not any(getattr(r, "name", "") == "web" for r in app.routes):
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


_mount_web()


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    if host not in ("127.0.0.1", "localhost"):
        log.warning("serving on %s: the API has no authentication; keep it on a trusted network", host)
    if WEB_DIST.exists():
        log.info("web app: http://%s:%d/", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
