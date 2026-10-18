"""Run the 2D surface model for a project option and compare its volumes with SWMM.

``run2d(project, option_id, rp)`` uses the option's graded ground (existing ground for the
baseline), the design storm of ``rp``, the soil zone infiltration rates, and the option's NbS elements
as sinks (capacity = SWMM element storage volume, emptying at the element's infiltration or seepage
rate). Writes ``scenarios/<id>/sim2d/rp<rp>.npz`` (depth frames), ``max_depth_rp<rp>.tif``, a summary
JSON and a PNG. Everything is labelled indicative.
"""

from __future__ import annotations

import logging
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
from .model import INDICATIVE, Elements2D, simulate

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

        def fn(t, i, P):
            return np.where(imperv, 0.0, np.maximum(base, i * (S / (P + S)) ** 2))

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
    cell = dem.cell_size * k
    g = DEM(z, cell, dem.origin, dem.crs, dem.nodata)
    X, Y = g.cell_centres()
    mask = valid & contains_xy(site.boundary, X, Y)

    # roughness and infiltration per cell
    imperv_kinds = set(P.value("terrain.impervious_context_kinds"))
    ctx = project.read_geojson("site/context.geojson")["features"] if project.exists("site/context.geojson") else []
    imperv_polys = [shape(f["geometry"]) for f in ctx if f["geometry"]["type"] == "Polygon"
                    and f["properties"].get("kind") in imperv_kinds and shape(f["geometry"]).area < 0.9 * site.boundary.area]
    imperv = contains_xy(unary_union(imperv_polys), X, Y) if imperv_polys else np.zeros(mask.shape, bool)
    n = np.where(imperv, float(P.value("surface.n_imperv")), float(P.value("surface.n_perv")))
    method = str(P.value("swmm.infiltration_method")).upper()
    f, infil_fn, infil_note, infil_params = _infiltration(site, method, X, Y, mask, imperv)

    # NbS elements as sinks (resolved values written by the SWMM run of the option)
    els = None
    if option_id != "baseline" and has_elements(project, option_id):
        elements = load_elements(project, option_id)
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
    return Inputs2D(g, mask, n, f, infil_fn, infil_note, infil_params, els, storm.intensity_mm_hr.astype(float),
                    storm.dt_min * 60, storm.duration_hr * 3600 + float(P.value("sim2d.extra_time_hr")) * 3600,
                    float(P.value("sim2d.courant")), float(P.value("sim2d.max_time_step_s")))


def run2d(project: Project, option_id: str, rp: int, cell_m: Optional[float] = None,
          frame_every_s: Optional[float] = None) -> Dict[str, Any]:
    P = project.parameters
    inp = prepare2d(project, option_id, rp, cell_m)
    g, mask, els, cell = inp.dem, inp.mask, inp.elements, inp.dem.cell_size
    dem = g
    infil_note = inp.infil_note
    duration_s = inp.duration_s
    res = simulate(g.z, mask, cell, inp.rain_mm_hr, inp.rain_dt_s, duration_s, inp.n, inp.f, els,
                   frame_every_s=float(frame_every_s or P.value("sim2d.frame_interval_s")),
                   alpha=inp.alpha, dt_max=inp.dt_max, infil_fn=inp.infil_fn)

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
    np.savez_compressed(project.path(f"{out_dir}/rp{rp}.npz"), times_s=res.times_s, depth_m=res.frames.astype(np.float16),
                        mask=mask, origin=np.array(g.origin), cell_m=cell)
    write_geotiff(DEM(np.where(mask, res.max_depth, dem.nodata), cell, g.origin, g.crs, dem.nodata),
                  project.path(f"{out_dir}/max_depth_rp{rp}.tif"))
    summary = {
        "label": INDICATIVE,
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
