"""Site description: boundary, subcatchments, soil zones, outfalls and trees.

Phase 1 reads subcatchments drawn by hand (``site/subcatchments.geojson``);
Phase 3 replaces them with delineation from the DEM. Soil infiltration is never
defaulted: every soil zone must carry its own values with a source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..project.package import Project

log = logging.getLogger(__name__)

SUBCATCHMENTS = "site/subcatchments.geojson"
EXTERNAL = "site/external_catchment.geojson"
SOILS = "site/soil_zones.geojson"
OUTFALLS = "site/outfalls.geojson"
CONTEXT = "site/context.geojson"
BOUNDARY = "site/boundary.geojson"


class SiteError(ValueError):
    pass


class SoilZone(BaseModel):
    """Infiltration parameters for one zone (mm, mm/hr, 1/hr, days)."""

    id: str
    geometry: Dict[str, Any]
    # Horton
    max_rate_mm_hr: Optional[float] = None
    min_rate_mm_hr: Optional[float] = None
    decay_1_hr: Optional[float] = None
    dry_time_days: Optional[float] = None
    max_volume_mm: float = 0.0
    # Green-Ampt
    suction_mm: Optional[float] = None
    ksat_mm_hr: Optional[float] = None
    imd: Optional[float] = None
    # TR-55 (used by CURVE_NUMBER infiltration and the TR-55 hand check)
    hsg: Optional[str] = None
    texture: Optional[str] = None
    source: str = "default"
    note: str = ""

    def resolved_hsg(self) -> Tuple[str, str]:
        """(hydrologic soil group, how it was obtained). Never assumed."""
        from spongepark.engine.hydrology import tr55

        if self.hsg:
            return tr55._single_hsg(self.hsg), "given"
        rate = self.min_rate_mm_hr if self.min_rate_mm_hr is not None else self.ksat_mm_hr
        if rate is not None:
            return tr55.hsg_from_rate(rate), f"from {rate:g} mm/hr (TR-55 App. A)"
        if self.texture:
            return tr55.hsg_from_texture(self.texture), f"from texture '{self.texture}' (TR-55 App. A)"
        raise SiteError(f"soil zone {self.id}: give hsg, texture, or a measured infiltration rate.")

    def native_rate(self, method: str) -> float:
        """Long-term (saturated) infiltration rate, mm/hr."""
        if "CURVE" in method:
            rate = self.ksat_mm_hr if self.ksat_mm_hr is not None else self.min_rate_mm_hr
            if rate is None:
                raise SiteError(
                    f"soil zone {self.id}: a curve number gives no infiltration rate, but NbS seepage "
                    "needs one. Give ksat_mm_hr (percolation test) for this zone."
                )
            return rate
        if "HORTON" in method:
            if self.min_rate_mm_hr is None:
                raise SiteError(f"soil zone {self.id}: Horton needs min_rate_mm_hr.")
            return self.min_rate_mm_hr
        if self.ksat_mm_hr is None:
            raise SiteError(f"soil zone {self.id}: Green-Ampt needs ksat_mm_hr.")
        return self.ksat_mm_hr

    def swmm_params(self, method: str) -> List[float]:
        if "CURVE" in method:
            raise SiteError("CURVE_NUMBER parameters are per subcatchment; use Site.swmm_infiltration().")
        if "HORTON" in method:
            vals = [self.max_rate_mm_hr, self.min_rate_mm_hr, self.decay_1_hr, self.dry_time_days, self.max_volume_mm]
            names = "max_rate_mm_hr min_rate_mm_hr decay_1_hr dry_time_days".split()
        else:
            vals = [self.suction_mm, self.ksat_mm_hr, self.imd]
            names = "suction_mm ksat_mm_hr imd".split()
        missing = [n for n, v in zip(names, vals) if v is None]
        if missing:
            raise SiteError(f"soil zone {self.id}: {method} infiltration needs {', '.join(missing)}.")
        return [float(v) for v in vals]  # type: ignore[arg-type]


class Subcatchment(BaseModel):
    """Land surface draining to one outlet. Slopes in %, depths in mm, n in s/m^(1/3)."""

    id: str
    geometry: Dict[str, Any]
    outlet: str
    pct_imperv: float
    slope_pct: float
    flow_length_m: Optional[float] = None
    soil_zone: Optional[str] = None
    land_cover: str = ""
    n_imperv: Optional[float] = None
    n_perv: Optional[float] = None
    dstore_imperv_mm: Optional[float] = None
    dstore_perv_mm: Optional[float] = None
    pct_zero_imperv: Optional[float] = None
    curve_number: Optional[float] = None  # pervious CN, overrides the TR-55 lookup
    tr55_cover: Optional[str] = None  # TR-55 cover key for the pervious part, e.g. open_space_fair
    external: bool = False

    def shape(self) -> BaseGeometry:
        return shape(self.geometry)


class Outfall(BaseModel):
    id: str
    geometry: Dict[str, Any]
    invert_elev_m: float
    kind: str = "FREE"
    note: str = ""


class Tree(BaseModel):
    id: str
    geometry: Dict[str, Any]
    canopy_radius_m: float
    species: str = ""
    interception_capacity_mm: Optional[float] = None

    def canopy(self) -> BaseGeometry:
        return shape(self.geometry).buffer(self.canopy_radius_m, quad_segs=16)


def _features(fc: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for f in fc.get("features", []):
        props = dict(f.get("properties") or {})
        props["geometry"] = f["geometry"]
        out.append(props)
    return out


@dataclass
class Site:
    boundary: Optional[BaseGeometry]
    subcatchments: List[Subcatchment]
    external: List[Subcatchment]
    soils: List[SoilZone]
    outfalls: List[Outfall]
    trees: List[Tree] = field(default_factory=list)

    @classmethod
    def load(cls, project: Project, option_id: Optional[str] = None) -> "Site":
        """The site; an option with its own ``scenarios/<id>/site/subcatchments.geojson`` (rebuilt on
        its graded ground) uses those subcatchments (rebuilt first if quick design edits left them owed)."""
        if option_id and option_id != "baseline":
            from ..layout.apply import ensure_regraded

            ensure_regraded(project, option_id)
        b = project.read_geojson(BOUNDARY)["features"]
        boundary = unary_union([shape(f["geometry"]) for f in b]) if b else None
        rel = f"scenarios/{option_id}/{SUBCATCHMENTS}" if option_id else SUBCATCHMENTS
        subs = [Subcatchment.model_validate(p) for p in _features(project.read_geojson(
            rel if project.exists(rel) else SUBCATCHMENTS))]
        ext = [Subcatchment.model_validate({**p, "external": True}) for p in _features(project.read_geojson(EXTERNAL))]
        soils = [SoilZone.model_validate(p) for p in _features(project.read_geojson(SOILS))]
        outs = [Outfall.model_validate(p) for p in _features(project.read_geojson(OUTFALLS))]
        trees = [
            Tree.model_validate(p)
            for p in _features(project.read_geojson(CONTEXT))
            if p.get("kind") == "tree"
        ]
        return cls(boundary, subs, ext, soils, outs, trees)

    @property
    def site_area_m2(self) -> float:
        if self.boundary is not None:
            return float(self.boundary.area)
        return float(sum(s.shape().area for s in self.subcatchments))

    def soil(self, zone_id: str) -> SoilZone:
        for z in self.soils:
            if z.id == zone_id:
                return z
        raise SiteError(f"unknown soil zone '{zone_id}'.")

    def dominant_soil(self, geom: BaseGeometry) -> Tuple[Optional[SoilZone], float]:
        """Soil zone with the largest overlap and its share of ``geom`` area."""
        best, best_a = None, 0.0
        for z in self.soils:
            a = shape(z.geometry).intersection(geom).area
            if a > best_a:
                best, best_a = z, a
        share = best_a / geom.area if geom.area > 0 else 0.0
        if best is not None and share < 0.9:
            log.warning("geometry spans several soil zones; using %s (%.0f %% of area)", best.id, share * 100)
        return best, share

    def pervious_cn(self, s: "Subcatchment") -> Tuple[float, str, str]:
        """(pervious CN, source, hydrologic soil group) for a site or external subcatchment."""
        from spongepark.engine.hydrology import tr55

        zone = self.soil(s.soil_zone) if s.soil_zone else self.dominant_soil(s.shape())[0]
        if zone is None:
            raise SiteError(f"subcatchment {s.id}: no soil zone.")
        hsg, how = zone.resolved_hsg()
        if s.curve_number is not None:
            return float(s.curve_number), "given", hsg
        if not s.tr55_cover:
            raise SiteError(
                f"subcatchment {s.id}: CURVE_NUMBER needs curve_number or tr55_cover "
                f"(one of: {', '.join(sorted(tr55.covers('pervious')))})."
            )
        cover = tr55.covers().get(s.tr55_cover)
        if cover is not None and cover["kind"] != "pervious":
            raise SiteError(
                f"subcatchment {s.id}: '{s.tr55_cover}' is not a pervious cover. SWMM handles the "
                "impervious share through pct_imperv; give the cover of the pervious part."
            )
        cn = tr55.curve_number(s.tr55_cover, hsg)
        return cn, f"TR-55 {s.tr55_cover}, HSG {hsg} ({how})", hsg

    def soil_lookup(self, method: str):
        """Return a function geom -> (zone id, native infiltration rate mm/hr) for element resolution."""

        def f(geom: BaseGeometry):
            z, _ = self.dominant_soil(geom)
            return (z.id, z.native_rate(method)) if z else (None, None)

        return f

    def validate(self, tol: float = 0.005) -> List[str]:
        """Check that site subcatchments tile the boundary. Returns warnings; raises on hard errors."""
        msgs: List[str] = []
        if not self.subcatchments:
            raise SiteError("no subcatchments defined (site/subcatchments.geojson).")
        if not self.soils:
            raise SiteError("no soil zones defined (site/soil_zones.geojson); infiltration is never defaulted.")
        if not self.outfalls:
            raise SiteError("no outfalls defined (site/outfalls.geojson).")
        ids = [s.id for s in self.subcatchments + self.external]
        if len(ids) != len(set(ids)):
            raise SiteError("duplicate subcatchment ids.")
        shapes = [s.shape() for s in self.subcatchments]
        total = sum(g.area for g in shapes)
        union = unary_union(shapes)
        overlap = total - union.area
        if overlap > tol * total:
            raise SiteError(f"subcatchments overlap by {overlap:.1f} m2.")
        if self.boundary is not None:
            diff = abs(union.area - self.boundary.area)
            if diff > tol * self.boundary.area:
                raise SiteError(
                    f"subcatchments cover {union.area:.1f} m2 but the site boundary is {self.boundary.area:.1f} m2."
                )
            outside = union.difference(self.boundary).area
            if outside > tol * self.boundary.area:
                msgs.append(f"{outside:.1f} m2 of subcatchments lie outside the boundary.")
        out_ids = {o.id for o in self.outfalls}
        for s in self.subcatchments + self.external:
            if s.outlet not in out_ids and s.outlet not in ids:
                raise SiteError(f"subcatchment {s.id} drains to unknown '{s.outlet}'.")
        return msgs
