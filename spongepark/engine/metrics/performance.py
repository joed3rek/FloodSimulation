"""Performance curve: intervention area (% of site) against largest storm fully retained.

Phase 1 builds the curve by uniformly scaling a manual layout's footprints
(about each element's centroid) to target area percentages; depths, inverts and
routing are unchanged and recharge wells keep their diameter. Phase 5 replaces
this with optimised layouts. Each point is a full SWMM run.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from shapely.affinity import scale
from shapely.geometry import mapping, shape

from ..project.package import Project
from ..site.model import Site

log = logging.getLogger(__name__)


def scaled_layout(fc: Dict[str, Any], factor: float, boundary=None) -> Dict[str, Any]:
    """Scale every non-well footprint by ``factor`` in area (linear factor sqrt(factor))."""
    k = factor ** 0.5
    feats = []
    for f in fc["features"]:
        props = dict(f["properties"])
        g = shape(f["geometry"])
        if props["type"] != "recharge_well":
            if g.geom_type == "LineString":
                g = scale(g, k, k, origin="centroid")
                if props.get("top_width_m"):
                    props["top_width_m"] = props["top_width_m"] * k
            else:
                g = scale(g, k, k, origin="centroid")
                if boundary is not None and g.geom_type in ("Polygon", "MultiPolygon"):
                    g = g.intersection(boundary)
            for key in ("area_m2", "storage_volume_m3", "drawdown_time_hr", "contributing_area_m2"):
                props.pop(key, None)
        props["source"] = "generated"
        props["notes"] = (props.get("notes", "") + f" Scaled x{factor:.2f} in area for performance curve.").strip()
        feats.append({"type": "Feature", "geometry": mapping(g), "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def build_curve(project: Project, base_option: str, levels_pct: Sequence[float]) -> List[Dict[str, Any]]:
    """Create scaled options, run them for all return periods and compare with the baseline."""
    from ..pipeline import BASELINE, compare, prepare_option, run_option

    site = Site.load(project)
    elements, _ = prepare_option(project, base_option, site)
    current_pct = 100.0 * sum(e.area_m2 for e in elements) / site.site_area_m2
    if not project.exists(f"options/{BASELINE}/results/summary.json"):
        run_option(project, BASELINE, site=site)
    base_fc = project.read_geojson(f"options/{base_option}/components.geojson")
    points = []
    for lvl in levels_pct:
        oid = f"{base_option}_area{int(round(lvl))}"
        fc = scaled_layout(base_fc, lvl / current_pct, site.boundary)
        project.write_geojson(f"options/{oid}/components.geojson", fc)
        summ = run_option(project, oid, site=site)
        cmp_ = compare(project, oid)
        points.append({
            "option_id": oid,
            "target_pct": lvl,
            "intervention_area_pct": summ["intervention_area_pct"],
            "design_retention_storm_yr": cmp_["design_retention_storm_yr"],
            "design_no_overflow_storm_yr": cmp_["design_no_overflow_storm_yr"],
        })
        log.info("%s: %.1f %% area -> fully retains up to %s yr", oid, summ["intervention_area_pct"],
                 cmp_["design_retention_storm_yr"])
    project.write_json(f"options/{base_option}/results/performance_curve.json", points)
    return points
