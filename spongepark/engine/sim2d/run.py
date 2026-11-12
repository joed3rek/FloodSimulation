"""Run the 2D surface model for a project option and compare its volumes with SWMM.

``run2d(project, option_id, rp)`` uses the option's graded ground (existing ground for the
baseline), the design storm of ``rp``, the soil zone infiltration rates, and the option's NbS elements
as sinks (capacity = SWMM element storage volume, emptying at the element's infiltration or seepage
rate). Writes ``scenarios/<id>/sim2d/rp<rp>.npz`` (depth frames), ``max_depth_rp<rp>.tif``, a summary
JSON and a PNG. Everything is labelled indicative.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union

from ..nbs.components import has_elements, load_elements
from ..pipeline import load_hyetographs
from ..project import Project
from ..site.model import Site
from ..terrain.raster import DEM, read_geotiff, write_geotiff
from .model import INDICATIVE, Elements2D, njit, simulate

log = logging.getLogger(__name__)


def _coarsen(z: np.ndarray, valid: np.ndarray, k: int):
    """Block-average a grid by an integer factor (cells with no data stay out)."""
    if k <= 1:
        return z, valid
    nr, nc = (z.shape[0] // k) * k, (z.shape[1] // k) * k
    zz = np.where(valid, z, 0.0)[:nr, :nc].reshape(nr // k, k, nc // k, k)
    vv = valid[:nr, :nc].reshape(nr // k, k, nc // k, k)
    cnt = vv.sum((1, 3))
    out = np.where(cnt > 0, zz.sum((1, 3)) / np.maximum(cnt, 1), 0.0)
    return out, cnt >= (k * k) / 2


def _keep_barriers(z: np.ndarray, project: Project, k: int) -> None:
    """A coarse cell holding part of a thin wall or check dam takes its top (a block average would wash it away): a design
    model's walls hold water on the storm's coarser grid too. Changes ``z`` in place."""
    if k <= 1 or not project.exists("terrain/barriers.tif"):
        return
    b = read_geotiff(project.path("terrain/barriers.tif"))
    nr, nc = z.shape
    top = np.where(b.z != b.nodata, b.z, -np.inf)[:nr * k, :nc * k].reshape(nr, k, nc, k).max((1, 3))
    z[np.isfinite(top)] = np.maximum(z, top)[np.isfinite(top)]


@njit(cache=True, nogil=True)
def _curve_number(out, imperv, base, S, i, P):
    nr, nc = out.shape
    for r in range(nr):
        for c in range(nc):
            if imperv[r, c]:
                out[r, c] = 0.0
            else:
                ratio = S[r, c] / (P + S[r, c])
                out[r, c] = max(base[r, c], i * ratio * ratio)


def _infiltration(site: Site, method: str, X, Y, mask, imperv):
    """Ground infiltration matching the SWMM method: (constant rates mm/hr, rate function or None, note).

    CURVE_NUMBER: f = i (S / (P + S))^2 from the SCS runoff equation with Ia = 0 (as SWMM), never
    below the zone's saturated rate when one is given; S from each subcatchment's pervious CN.
    HORTON: f = fmin + (f0 - fmin) exp(-k t) from the storm start. GREEN_AMPT: constant Ksat."""
    f = np.zeros(mask.shape)
    for zone in site.soils:
        m = contains_xy(shape(zone.geometry), X, Y)
        if "CURVE" in method:
            r = zone.ksat_mm_hr if zone.ksat_mm_hr is not None else zone.min_rate_mm_hr
            f[m] = float(r or 0.0)
        else:
            f[m] = zone.native_rate(method)
    f[imperv] = 0.0
    if "CURVE" in method:
        S = np.full(mask.shape, np.nan)
        for sc in site.subcatchments:
            cn, _, _ = site.pervious_cn(sc)
            S[contains_xy(sc.shape(), X, Y)] = 25400.0 / cn - 254.0
        S = np.where(np.isnan(S), np.nanmean(S), S)
        base = f.copy()
        now = np.zeros(mask.shape)

        def fn(t, i, P):
            _curve_number(now, imperv, base, S, i, P)
            return now

        return f, fn, "curve number (SCS, Ia = 0, as SWMM), floor at the zone's saturated rate",             {"kind": "curve_number", "base_mm_hr": f, "S_mm": np.where(imperv, 0.0, S)}
    if "HORTON" in method:
        f0, fmin, k = np.zeros(mask.shape), np.zeros(mask.shape), np.zeros(mask.shape)
        for zone in site.soils:
            m = contains_xy(shape(zone.geometry), X, Y)
            f0[m], fmin[m], k[m] = zone.max_rate_mm_hr, zone.min_rate_mm_hr, zone.decay_1_hr

        def fn(t, i, P):
            return np.where(imperv, 0.0, fmin + (f0 - fmin) * np.exp(-k * t / 3600))

        return f, fn, "Horton decay from the storm start",             {"kind": "horton", "f0_mm_hr": np.where(imperv, 0.0, f0), "fmin_mm_hr": np.where(imperv, 0.0, fmin), "k_1_hr": k}
    return f, None, "constant saturated rate (Green-Ampt Ksat)", {"kind": "constant", "base_mm_hr": f}


@dataclass
class Inputs2D:
    """Everything the 2D model needs; also served to the Unity GPU port so both run the same case."""

    dem: DEM
    mask: np.ndarray
    n: np.ndarray
    f: np.ndarray
    infil_fn: Any
    infil_note: str
    infil_params: Dict[str, Any]
    elements: Optional[Elements2D]
    rain_mm_hr: np.ndarray
    rain_dt_s: float
    duration_s: float
    alpha: float
    dt_max: float
    inlets: Any = None   # (row, col, area m2) where water from outside the site arrives
    theta: float = 0.9   # sim2d.flow_theta
    ground: Optional[np.ndarray] = None   # the park's ground before its edge was raised to hold water (closed exits)


def prepare2d(project: Project, option_id: str, rp: int, cell_m: Optional[float] = None) -> Inputs2D:
    P = project.parameters
    site = Site.load(project, option_id)
    dem_rel = f"scenarios/{option_id}/terrain/graded.tif"
    dem = read_geotiff(project.path(dem_rel if option_id != "baseline" and project.exists(dem_rel)
                                    else "terrain/existing.tif"), crs_fallback=project.manifest.crs)
    cell_m = float(cell_m or P.value("sim2d.cell_m"))
    k = max(1, int(round(cell_m / dem.cell_size)))
    valid = (dem.z != dem.nodata) & np.isfinite(dem.z)
    z, valid = _coarsen(dem.z, valid, k)
    _keep_barriers(z, project, k)
    cell = dem.cell_size * k
    g = DEM(z, cell, dem.origin, dem.crs, dem.nodata)
    X, Y = g.cell_centres()
    mask = valid & contains_xy(site.boundary, X, Y)
    ground = g.z.copy()
    _close_exits(project, g, mask, X, Y, option_id)

    # roughness and infiltration per cell
    imperv_kinds = set(P.value("terrain.impervious_context_kinds"))
    ctx = project.read_geojson("site/context.geojson")["features"] if project.exists("site/context.geojson") else []
    imperv_polys = [shape(f["geometry"]) for f in ctx if f["geometry"]["type"] == "Polygon"
                    and f["properties"].get("kind") in imperv_kinds and shape(f["geometry"]).area < 0.9 * site.boundary.area]
    imperv = contains_xy(unary_union(imperv_polys), X, Y) if imperv_polys else np.zeros(mask.shape, bool)
    n = np.where(imperv, float(P.value("surface.n_imperv")), float(P.value("surface.n_perv")))
    method = str(P.value("swmm.infiltration_method")).upper()
    f, infil_fn, infil_note, infil_params = _infiltration(site, method, X, Y, mask, imperv)
    f, infil_fn, infil_note = _nbs_zones(project, f, infil_fn, infil_note, infil_params, X, Y, mask)

    # NbS elements as sinks (resolved values written by the SWMM run of the option)
    from ..site import wells

    els = None
    elements = load_elements(project, option_id) if option_id != "baseline" and has_elements(project, option_id) else []
    elements = elements + [e for e in wells.resolved(project) if e.id not in {x.id for x in elements}]   # existing wells
    if elements:
        lab = -np.ones(mask.shape, np.int64)
        caps, rates, areas, ids = [], [], [], []
        for e in elements:
            m = contains_xy(e.footprint(), X, Y) & mask
            if not m.any():  # smaller than a cell: take the nearest one
                c = e.footprint().centroid
                d = np.where(mask, np.hypot(X - c.x, Y - c.y), np.inf)
                m = np.zeros(mask.shape, bool)
                m[np.unravel_index(int(np.argmin(d)), d.shape)] = True
            lab[m & (lab < 0)] = len(ids)
            ids.append(e.id)
            caps.append(float(e.storage_volume_m3 or 0.0))
            r = e.seepage_rate_mm_hr if e.seepage_rate_mm_hr is not None else (e.infiltration_rate_mm_hr or 0.0)
            rates.append(float(r) / 1000 / 3600)
            areas.append(float(e.area_m2 or e.footprint().area))
        els = Elements2D(lab, ids, np.array(caps), np.array(rates), np.array(areas))

    storm = load_hyetographs(project)[rp]
    from ..site import openings

    return Inputs2D(g, mask, n, f, infil_fn, infil_note, infil_params, els, storm.intensity_mm_hr.astype(float),
                    storm.dt_min * 60, storm.duration_hr * 3600 + float(P.value("sim2d.extra_time_hr")) * 3600,
                    min(float(P.value("sim2d.courant")), 0.5),   # projects saved with the old default of 0.7 too
                    float(P.value("sim2d.max_time_step_s")),
                    openings.inlet_cells(project, option_id, X, Y, mask), float(P.value_or("sim2d.flow_theta", 0.9)),
                    ground)


def _nbs_zones(project: Project, f, infil_fn, note, params, X, Y, mask):
    """Rain gardens and swales in a design model soak water in at the fact sheets' media rate, not the park's."""
    from ..io.model3d import NBS_RATE_KEY, NBS_ZONES
    from shapely.ops import unary_union

    if not project.exists(NBS_ZONES):
        return f, infil_fn, note
    rate = float(project.parameters.value(NBS_RATE_KEY))
    zone = contains_xy(unary_union([shape(z["geometry"]) for z in project.read_geojson(NBS_ZONES)["features"]]), X, Y) & mask
    f = np.where(zone, np.maximum(f, rate), f)
    if "base_mm_hr" in params:
        params["base_mm_hr"] = np.where(zone, np.maximum(params["base_mm_hr"], rate), params["base_mm_hr"])
    note = f"{note}; rain gardens and swales at {rate:g} mm/hr (HC 4.2 p.12, HC 4.7 p.8)"
    if infil_fn is None:
        return f, None, note
    park = infil_fn

    def fn(t, i, P):
        v = park(t, i, P)
        return np.where(zone, np.maximum(v, rate), v)

    return f, fn, note


def _close_exits(project: Project, g: DEM, mask: np.ndarray, X: np.ndarray, Y: np.ndarray, option: Optional[str] = None) -> None:
    """Exits with no way out (Site setup > Outfalls): the park's edge cells whose ground drains to such an exit
    are raised by its edge height (the wall or kerb), so water ponds against the edge and spills over it only
    above that height, as in SWMM. Then each outlet the designer placed cuts through that edge at its sill.
    Changes ``g.z`` in place."""
    from scipy import ndimage

    from ..site import openings, outfalls

    closed = {e["id"]: float(e["edge_height_m"]) for e in outfalls.status(project, option, with_outlets=False)["exits"]
              if e["state"] == "closed" and e["edge_height_m"]}   # answered, or held: nobody marked a way out
    outlets = [o for o in openings.active(project, option) if o["kind"] == "outlet"]
    if (not closed and not outlets) or not project.exists("site/subcatchments.geojson"):
        return
    ground = g.z.copy()
    ring = mask & ~ndimage.binary_erosion(mask, structure=np.ones((3, 3)), border_value=0)
    tops = outfalls.wall_tops(project, g)   # a modelled wall stands at its own height; a gap in it at the answer's
    for f in project.read_geojson("site/subcatchments.geojson")["features"]:
        h = closed.get(f["properties"].get("outlet"))
        if h:
            edge = ring & contains_xy(shape(f["geometry"]).buffer(g.cell_size), X, Y)
            g.z[edge] += h
            if tops is not None:
                walled = edge & np.isfinite(tops)
                g.z[walled] = np.maximum(ground[walled], tops[walled])
    for o in outlets:
        cut = ring & (np.hypot(X - o["x"], Y - o["y"]) <= max(float(o["width_m"]) / 2, g.cell_size))
        if o.get("invert_m") is not None:   # its level on the survey's datum, below the ground (a drain) or above it
            g.z[cut] = float(o["invert_m"])
        else:
            g.z[cut] = ground[cut] + float(o["sill_m"])


def _engine(P) -> str:
    """'itzi' when chosen (or 'auto' and Itzi is set up), otherwise the built-in model."""
    from .itzi_model import available

    choice = str(P.value_or("sim2d.engine", "auto")).lower()
    if choice == "itzi" and not available():
        raise RuntimeError("sim2d.engine is 'itzi' but Itzi is not set up: run `spongepark itzi setup`.")
    return "itzi" if choice == "itzi" or (choice == "auto" and available()) else "builtin"


def _run_itzi(inp: Inputs2D, frame_s: float):
    """Run Itzi on the 2D inputs. The grid is widened by a margin of lower ground with an open edge, so
    water leaving the park runs off; NbS elements are already carved into the graded ground and infiltrate
    at their own rate. Results are cropped back to the inputs' grid."""
    from ..terrain.extend import extend_dem
    from .itzi_model import simulate_itzi

    from scipy import ndimage

    g, mask, cell = inp.dem, inp.mask, inp.dem.cell_size
    R, C = mask.shape
    x0, y1 = g.origin
    bounds = (x0, y1 - R * cell, x0 + C * cell, y1)
    # an edge raised to hold water (a closed exit) stands just outside the park here, not on its edge cells: rain
    # falling on a wall of single cells would pour off it fast enough to stall Itzi's time step
    raised = (g.z - inp.ground > 1e-6) & mask if inp.ground is not None else np.zeros_like(mask)
    z_park = np.where(raised, inp.ground, g.z) if raised.any() else g.z
    big, _ = extend_dem(DEM(np.where(mask, z_park, g.nodata), cell, g.origin, g.crs, g.nodata), bounds, margin_m=4 * cell)
    left = int(round((x0 - big.origin[0]) / cell))
    top = int(round((big.origin[1] - y1) / cell))
    pad = ((top, big.z.shape[0] - R - top), (left, big.z.shape[1] - C - left))
    if raised.any():
        tops = np.pad(np.where(raised, g.z, -np.inf), pad, constant_values=-np.inf)
        wall = ndimage.grey_dilation(tops, footprint=np.ones((3, 3), bool))   # each outside cell beside a raised edge
        outside = ~np.pad(mask, pad) & np.isfinite(wall)
        big.z[outside] = np.maximum(big.z[outside], wall[outside])
    f = inp.f.copy()
    el = inp.elements
    if el is not None:   # element cells infiltrate (or seep) at the element's own rate
        for k, rate in enumerate(el.rate_m_s):
            f[el.label == k] = rate * 1000 * 3600
    n_big = np.pad(inp.n, pad, mode="edge")
    f_big = np.pad(np.where(mask, f, 0.0), pad)
    fn = None
    if inp.infil_fn is not None:
        base_fn = inp.infil_fn

        def fn(t, i, cum):
            grid = base_fn(t, i, cum)
            if el is not None:
                for k, rate in enumerate(el.rate_m_s):
                    grid = np.where(el.label == k, rate * 1000 * 3600, grid)
            return np.pad(np.where(mask, grid, 0.0), pad)

    res = simulate_itzi(big.z, np.pad(mask, pad), cell, inp.rain_mm_hr, inp.rain_dt_s, inp.duration_s,
                        n_big, f_big, frame_every_s=frame_s, infil_fn=fn)
    rs, cs = slice(top, top + R), slice(left, left + C)
    res.frames = res.frames[:, rs, cs]
    res.max_depth = res.max_depth[rs, cs]
    if res.velocity is not None:
        res.velocity = res.velocity[:, :, rs, cs]
    flow = {k: v[rs, cs] for k, v in res.extra.items()}
    return res, flow


def run2d(project: Project, option_id: str, rp: int, cell_m: Optional[float] = None,
          frame_every_s: Optional[float] = None, engine: Optional[str] = None) -> Dict[str, Any]:
    """``engine``: 'builtin' or 'itzi' for this run only (design changes use the quick built-in model;
    verification uses Itzi when it is set up)."""
    P = project.parameters
    inp = prepare2d(project, option_id, rp, cell_m)
    g, mask, els, cell = inp.dem, inp.mask, inp.elements, inp.dem.cell_size
    dem = g
    infil_note = inp.infil_note
    duration_s = inp.duration_s
    frame_s = float(frame_every_s or P.value("sim2d.frame_interval_s"))
    engine = _engine(P) if engine in (None, "", "auto") else engine
    engine_note = None
    if engine == "itzi" and inp.elements is not None and not project.exists(f"scenarios/{option_id}/terrain/graded.tif"):
        # Itzi holds water only where the ground does: elements must be carved into the scenario's ground
        if str(P.value_or("sim2d.engine", "auto")).lower() == "itzi":
            raise RuntimeError(f"{option_id}: the elements are not carved into the ground yet (regrade it first), "
                               "so Itzi would not see their storage.")
        engine, engine_note = "builtin", "Itzi needs the elements carved into the ground; the built-in model was used."
    if engine == "itzi" and inp.inlets:
        engine, engine_note = "builtin", "Itzi cannot take the inlets here; the built-in model was used."
    flow = None
    if engine == "gpu":
        from .gpu import can_run, simulate_gpu

        if can_run(inp):
            res = simulate_gpu(inp, frame_s)
        else:
            engine, engine_note = "builtin", "The graphics card port does not cover this case; the built-in model was used."
    if engine == "itzi":
        res, flow = _run_itzi(inp, frame_s)
    elif engine != "gpu":
        res = simulate(g.z, mask, cell, inp.rain_mm_hr, inp.rain_dt_s, duration_s, inp.n, inp.f, els,
                       frame_every_s=frame_s, alpha=inp.alpha, dt_max=inp.dt_max, infil_fn=inp.infil_fn, inlets=inp.inlets,
                       theta=inp.theta)

    # SWMM comparison
    swmm = None
    srel = f"scenarios/{option_id}/results/summary.json"
    if project.exists(srel):
        r = project.read_json(srel)["return_periods"].get(str(rp))
        if r:
            wb = r["water_balance"]
            leaving = wb["outflow_total_m3"] + wb["flooding_m3"]
            rain = wb["rainfall_total_m3"]
            swmm = {"rainfall_m3": rain, "leaving_site_m3": leaving,
                    "difference_pct_of_rainfall": 100 * (res.balance["outflow_m3"] / res.balance["rainfall_m3"]
                                                         - leaving / rain) if rain else None}
    thr = float(P.value("sim2d.flood_depth_threshold_m"))
    out_dir = f"scenarios/{option_id}/sim2d"
    project.path(out_dir).mkdir(parents=True, exist_ok=True)
    # written aside and moved into place: the app can ask for a storm while it is still being written
    with open(project.path(f"{out_dir}/rp{rp}.tmp.npz"), "wb") as tmp:
        np.savez_compressed(tmp, times_s=res.times_s, depth_m=res.frames.astype(np.float16),
                            mask=mask, origin=np.array(g.origin), cell_m=cell,
                            **({"velocity_ms": res.velocity.astype(np.float16)} if res.velocity is not None else {}),
                            **({k: v.astype(np.float32) for k, v in flow.items()} if flow else {}))
    os.replace(project.path(f"{out_dir}/rp{rp}.tmp.npz"), project.path(f"{out_dir}/rp{rp}.npz"))
    write_geotiff(DEM(np.where(mask, res.max_depth, dem.nodata), cell, g.origin, g.crs, dem.nodata),
                  project.path(f"{out_dir}/max_depth_rp{rp}.tmp.tif"))
    os.replace(project.path(f"{out_dir}/max_depth_rp{rp}.tmp.tif"), project.path(f"{out_dir}/max_depth_rp{rp}.tif"))
    summary = {
        "label": INDICATIVE,
        "model": "Itzi (Courty et al., local inertial shallow water)" if engine == "itzi" else "built-in local inertial model",
        "ran_on": "graphics card" if engine == "gpu" else "CPU",
        "model_note": engine_note,
        "option_id": option_id, "return_period_yr": rp, "cell_m": cell, "duration_hr": duration_s / 3600,
        "balance": res.balance,
        "infiltration": infil_note,
        "flooded_area_m2": float(((res.max_depth >= thr) & mask & ~(els.label >= 0 if els else False)).sum() * cell ** 2),
        "flood_depth_threshold_m": thr,
        "max_depth_m": float(res.max_depth[mask].max()),
        "element_storage_end_m3": res.element_store_m3,
        "swmm_comparison": swmm,
        "frames": int(len(res.times_s)),
    }
    project.write_json(f"{out_dir}/rp{rp}_summary.json", summary)
    _plot(project.path(f"{out_dir}/max_depth_rp{rp}.png"), g, mask, res.max_depth, thr, summary)
    project.history.log("sim2d", option=option_id, rp=rp, continuity_pct=res.balance["continuity_error_pct"])
    return summary


def _plot(out, g: DEM, mask, hmax, thr, summary) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x0, y0, x1, y1 = g.bounds()
    fig, ax = plt.subplots(figsize=(9, 7), dpi=130)
    ax.imshow(np.where(mask, g.z, np.nan), extent=(x0, x1, y0, y1), cmap="Greys_r", alpha=0.6)
    d = np.where(mask & (hmax >= thr), hmax, np.nan)
    im = ax.imshow(d, extent=(x0, x1, y0, y1), cmap="Blues", vmin=0, vmax=max(0.3, float(np.nanmax(hmax[mask]))))
    fig.colorbar(im, ax=ax, label="Maximum water depth (m)", shrink=0.8)
    sw = summary["swmm_comparison"]
    cmp_txt = f"; leaving site vs SWMM: {sw['difference_pct_of_rainfall']:+.1f} % of rainfall" if sw else ""
    ax.set_title(f"{summary['option_id']}, {summary['return_period_yr']}-yr storm: maximum depth >= {thr:g} m "
                 f"(INDICATIVE){cmp_txt}", fontsize=8)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
