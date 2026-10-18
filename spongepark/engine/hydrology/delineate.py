"""Subcatchments and outfalls from the existing-ground DEM (Phase 3).

Writes ``site/subcatchments.geojson``, ``site/outfalls.geojson`` and ``site/boundary.geojson`` (the
modelled domain), plus ``terrain/flow/*`` and a report. Natural depressions found by sink filling are
added to each subcatchment's pervious depression storage as an equivalent depth, so SWMM holds the
water the ground would hold.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union

from ..project import Project
from ..terrain.raster import DEM, read_geotiff, write_geotiff
from . import flow as fl


def _polygons(lab: np.ndarray, dem: DEM) -> Dict[int, Any]:
    from rasterio.features import shapes
    from rasterio.transform import from_origin

    t = from_origin(dem.origin[0], dem.origin[1], dem.cell_size, dem.cell_size)
    polys: Dict[int, List[Any]] = {}
    for geom, v in shapes(lab.astype("int32"), mask=lab > 0, transform=t):
        polys.setdefault(int(v), []).append(shape(geom))
    return {k: unary_union(v) for k, v in polys.items()}


def context_surfaces(project: Project, boundary, domain_area_m2: float, kinds) -> Tuple[Any, List, List]:
    """Union of closed context polygons of ``kinds`` inside the site (impervious surfaces), plus the
    polygons ignored as outlines drawn around the whole site and the closed outlines of other kinds."""
    ctx = project.read_geojson("site/context.geojson")["features"] if project.exists("site/context.geojson") else []
    polys, enclosing, outlines = [], [], []
    for f in ctx:
        if f["geometry"]["type"] != "Polygon":
            continue
        g = shape(f["geometry"])
        kind = f["properties"].get("kind")
        inside = float(g.intersection(boundary).area) if boundary is not None else float(g.area)
        if inside < 1.0:
            continue
        if inside >= 0.9 * domain_area_m2:
            enclosing.append({"kind": kind, "layer": f["properties"].get("layer"), "area_m2": float(g.area)})
            continue  # an outline drawn around the park, not a surface
        if kind in kinds:
            polys.append(g)
        else:
            outlines.append({"kind": kind, "layer": f["properties"].get("layer"), "inside_m2": inside})
    return (unary_union(polys) if polys else unary_union([])), enclosing, outlines


def delineate(project: Project) -> Dict[str, Any]:
    P = project.parameters
    dem = read_geotiff(project.path("terrain/existing.tif"), crs_fallback=project.manifest.crs)
    X, Y = dem.cell_centres()
    valid = dem.z != dem.nodata
    bnd = project.read_geojson("site/boundary.geojson")["features"] if project.exists("site/boundary.geojson") else []
    survey_boundary = unary_union([shape(f["geometry"]) for f in bnd]) if bnd else None
    mask = valid & (contains_xy(survey_boundary, X, Y) if survey_boundary is not None else True)
    if mask.sum() < 4:
        raise ValueError("no DEM cells inside the site boundary.")
    cell = dem.cell_size
    z = np.where(mask, dem.z, np.nan)

    filled = fl.fill_sinks(z, mask)
    dirs = fl.d8_directions(filled, mask)
    acc = fl.accumulation(filled, mask, dirs)
    out_cell = fl.outlet_of(filled, mask, dirs)
    L = fl.flow_length(filled, mask, dirs, cell)
    deps, depth = fl.depressions(z, filled, mask, cell, X, Y, float(P.value("terrain.min_depression_depth_m")))
    lab = fl.group_outlets(out_cell, mask, cell, float(P.value("terrain.min_subcatchment_area_m2")))

    gy, gx = np.gradient(np.where(mask, dem.z, np.nan), cell)
    slope = 100 * np.hypot(gx, gy)
    polys = _polygons(lab, dem)
    imperv_kinds = set(P.value("terrain.impervious_context_kinds"))
    imperv, enclosing, outlines = context_surfaces(project, survey_boundary, float(mask.sum() * cell ** 2), imperv_kinds)
    dstore_base = float(P.value("surface.dstore_perv_mm"))

    subs, outs, rows = [], [], []
    for k, poly in sorted(polys.items()):
        m = lab == k
        area = float(m.sum() * cell ** 2)
        a_exit = np.where(m & (out_cell == np.arange(out_cell.size).reshape(out_cell.shape)), acc, -1)
        r, c = np.unravel_index(int(np.argmax(a_exit)), a_exit.shape)
        inv = float(dem.z[r, c])
        oid, sid = f"OUT_{k}", f"SC_{k}"
        flen = float(np.percentile(L[m], 95))
        s = slope[m]
        s = s[~np.isnan(s)]
        dep_vol = float((depth[m]).sum() * cell ** 2)
        dep_mm = 1000 * dep_vol / area
        imp = float(poly.intersection(imperv).area / poly.area * 100) if not imperv.is_empty else 0.0
        subs.append({"type": "Feature", "geometry": poly.__geo_interface__, "properties": {
            "id": sid, "outlet": oid, "pct_imperv": round(imp, 2),
            "slope_pct": round(float(np.median(s)) if s.size else 0.5, 3),
            "flow_length_m": round(max(flen, cell), 2),
            "dstore_perv_mm": round(dstore_base + dep_mm, 2), "land_cover": "park (terrain-derived)",
            "note": f"terrain-derived; natural depressions {dep_vol:.1f} m3 added as {dep_mm:.1f} mm depression storage",
        }})
        outs.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": (float(X[r, c]), float(Y[r, c]))},
                     "properties": {"id": oid, "invert_elev_m": round(inv, 3), "kind": "FREE",
                                    "note": "where surface flow leaves the surveyed park (to confirm: gate, wall "
                                            "opening or drain inlet)"}})
        rows.append({"subcatchment": sid, "outfall": oid, "area_m2": area, "pct_imperv": imp, "slope_pct_median": float(np.median(s)) if s.size else None,
                     "flow_length_m": flen, "depression_m3": dep_vol, "depression_mm": dep_mm,
                     "outfall_xy": [float(X[r, c]), float(Y[r, c])], "outfall_level_m": inv})

    domain = unary_union(list(polys.values()))
    project.write_geojson("site/subcatchments.geojson", {"type": "FeatureCollection", "features": subs})
    project.write_geojson("site/outfalls.geojson", {"type": "FeatureCollection", "features": outs})
    project.write_geojson("site/boundary.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": domain.__geo_interface__,
         "properties": {"id": "DOMAIN", "note": "surveyed part of the site boundary (modelled area)"}}]})
    if survey_boundary is not None:
        project.write_geojson("terrain/survey_boundary.geojson", {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": survey_boundary.__geo_interface__, "properties": {"id": "SURVEY"}}]})
    for name, arr in (("filled", filled), ("accumulation_m2", acc * cell ** 2), ("depression_depth", depth),
                      ("flow_length", L)):
        write_geotiff(DEM(np.where(mask, arr, dem.nodata), cell, dem.origin, dem.crs, dem.nodata),
                      project.path(f"terrain/flow/{name}.tif"))
    project.write_geojson("terrain/flow/depressions.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": d.centroid},
         "properties": {"id": f"DEP_{d.id}", "area_m2": round(d.area_m2, 1), "max_depth_m": round(d.max_depth_m, 3),
                        "volume_m3": round(d.volume_m3, 2)}} for d in deps]})
    report = {
        "domain_area_m2": float(domain.area),
        "survey_boundary_area_m2": float(survey_boundary.area) if survey_boundary is not None else None,
        "unmodelled_area_m2": float(survey_boundary.area - domain.area) if survey_boundary is not None else None,
        "subcatchments": rows,
        "depressions": [vars(d) for d in deps],
        "depression_total_m3": float(sum(d.volume_m3 for d in deps)),
        "ignored_enclosing_outlines": enclosing,
        "closed_outlines_not_counted": outlines,
        "assumptions": [
            "Water leaves wherever flow reaches the edge of the surveyed area; walls are not modelled.",
            "Flow length is the 95th percentile of D8 path length to the exit; width = area / flow length.",
            f"Impervious share counts only closed polygons of kinds {sorted(imperv_kinds)} from the survey.",
        ],
    }
    project.write_json("terrain/flow/report.json", report)
    _plot(project, dem, mask, acc, lab, outs, deps, cell)
    project.history.log("delineate", subcatchments=len(subs), depressions=len(deps))
    from ..site.ground import apply_to_subcatchments

    apply_to_subcatchments(project)   # the ground questionnaire's curve numbers, if answered
    return report


def _plot(project, dem, mask, acc, lab, outs, deps, cell) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    x0, y0, x1, y1 = dem.bounds()
    ext = (x0, x1, y0, y1)
    fig, ax = plt.subplots(figsize=(10, 8), dpi=130)
    pal = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
    n = int(lab.max())
    cmap = ListedColormap([pal[i % len(pal)] for i in range(max(n, 1))])
    ax.imshow(np.where(lab > 0, lab, np.nan), extent=ext, cmap=cmap, alpha=0.35, interpolation="nearest",
              vmin=0.5, vmax=n + 0.5)
    a = np.where(mask, acc * cell ** 2, np.nan)
    streams = np.where(a >= np.nanpercentile(a, 97), a, np.nan)
    ax.imshow(np.log10(streams), extent=ext, cmap="Blues", interpolation="nearest")
    for f in outs:
        x, y = f["geometry"]["coordinates"]
        ax.plot(x, y, "v", color="#14201f", ms=8)
        ax.annotate(f["properties"]["id"], (x, y), fontsize=7, xytext=(4, -10), textcoords="offset points")
    for d in deps:
        ax.plot(*d.centroid, "o", ms=max(3, min(14, d.volume_m3 ** 0.5 * 3)), mfc="none", color="#e34948")
    ax.set_title("Subcatchments (shaded), main flow paths (blue), outfalls (triangles),\n"
                 "natural depressions (red circles, size ~ volume)", fontsize=9)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(project.path("terrain/flow/flow.png"))
    plt.close(fig)
