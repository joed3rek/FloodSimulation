"""NbS element schema, parameter resolution and geometry.

An element is read from ``options/<id>/components.geojson``. Missing design
values are filled from project parameters (``nbs.<type>.<field>``) and every
filled value is recorded in ``param_sources`` so reports can show which values
were defaults.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from ..project.parameters import ParameterSet
from .catalogue import LID_BIORETENTION, LID_SWALE, ComponentSpec, spec

log = logging.getLogger(__name__)


class ElementError(ValueError):
    pass


class NbSElement(BaseModel):
    """One NbS element. Lengths in m, areas in m2, volumes in m3, rates in mm/hr, times in hr."""

    id: str
    type: str
    geometry: Dict[str, Any]
    area_m2: Optional[float] = None
    max_ponding_depth_m: Optional[float] = None
    storage_volume_m3: Optional[float] = None
    infiltration_rate_mm_hr: Optional[float] = None
    soil_media_depth_m: Optional[float] = None
    drawdown_time_hr: Optional[float] = None
    contributing_area_m2: Optional[float] = None
    inflow_from: List[str] = Field(default_factory=list)  # subcatchment ids draining here
    outflow_to: Optional[str] = None  # element / outfall id (LID surface outflow, or controlled outlet)
    overflow_to: Optional[str] = None  # element / outfall id (storage overflow weir)
    locked: bool = False
    source: str = "generated"  # "generated" | "designer"

    # design detail (filled from parameters when absent)
    invert_elev_m: Optional[float] = None
    side_slope_h_v: Optional[float] = None
    permanent_pool_depth_m: Optional[float] = None
    outlet_diameter_m: Optional[float] = None
    outlet_coefficient: Optional[float] = None
    outlet_weir_length_m: Optional[float] = None
    weir_length_m: Optional[float] = None
    seepage_rate_mm_hr: Optional[float] = None
    longitudinal_slope_pct: Optional[float] = None
    top_width_m: Optional[float] = None
    manning_n: Optional[float] = None
    vegetation_volume_fraction: Optional[float] = None
    storage_layer_depth_m: Optional[float] = None
    well_diameter_m: Optional[float] = None
    well_depth_m: Optional[float] = None
    dam_height_m: Optional[float] = None
    freeboard_m: Optional[float] = None
    # guideline-only attributes (optional, checked when given)
    check_dam_spacing_m: Optional[float] = None
    forebay_volume_fraction: Optional[float] = None
    cell_count: Optional[int] = None
    length_to_width: Optional[float] = None
    shallow_zone_depth_m: Optional[float] = None
    peak_velocity_m_s: Optional[float] = None
    contained_return_period_yr: Optional[float] = None
    hydraulic_retention_time_hr: Optional[float] = None
    native_ksat_m_s: Optional[float] = None

    soil_zone: Optional[str] = None
    param_sources: Dict[str, str] = Field(default_factory=dict)
    notes: str = ""

    @property
    def spec(self) -> ComponentSpec:
        return spec(self.type)

    def footprint(self) -> BaseGeometry:
        """Plan footprint polygon (m)."""
        g = shape(self.geometry)
        if g.geom_type in ("Polygon", "MultiPolygon"):
            return g
        if g.geom_type == "LineString":
            if not self.top_width_m:
                raise ElementError(f"{self.id}: a centreline needs top_width_m.")
            return g.buffer(self.top_width_m / 2.0, cap_style=2)
        if g.geom_type == "Point":
            if not self.well_diameter_m:
                raise ElementError(f"{self.id}: a point element needs well_diameter_m.")
            return Point(g.x, g.y).buffer(self.well_diameter_m / 2.0, quad_segs=32)
        raise ElementError(f"{self.id}: unsupported geometry {g.geom_type}.")

    # ------------------------------------------------------------------ storage geometry
    @property
    def pool_depth_m(self) -> float:
        """Permanent pool depth (m); zero for elements without a permanent pool."""
        if self.type in ("retention_pond", "constructed_wetland"):
            return float(self.permanent_pool_depth_m or 0.0)
        return 0.0

    @property
    def crest_depth_m(self) -> float:
        """Depth from storage invert to the overflow crest, m."""
        if self.type == "recharge_well":
            return float(self.well_depth_m)
        if self.type == "inline_check_dam":
            return float(self.dam_height_m)
        return self.pool_depth_m + float(self.max_ponding_depth_m or 0.0)

    def stage_area(self, n: int = 12) -> List[Tuple[float, float]]:
        """Stage-area curve [(depth m, area m2)] from invert to crest + freeboard.

        Banks are sloped at ``side_slope_h_v``; the footprint is the plan area at the
        crest. Above the crest the bank continues at the same slope.
        """
        fp = self.footprint()
        top = self.crest_depth_m
        ymax = top + (self.freeboard_m or 0.0)
        if self.type == "recharge_well":
            a = fp.area
            return [(0.0, a), (ymax, a)]
        z = float(self.side_slope_h_v or 0.0)
        out = []
        min_area = 0.01 * fp.area
        for h in np.linspace(0.0, ymax, n):
            d = z * (top - h)
            a = fp.buffer(-d).area if d != 0 else fp.area
            out.append((float(h), max(float(a), min_area)))
        if out[0][1] <= min_area * 1.0001:
            log.warning("%s: banks at %.1f:1 close before the invert; bottom area clipped to 1 %% of footprint", self.id, z)
        return out

    def volume_between(self, h0: float, h1: float) -> float:
        """Storage volume (m3) between depths h0 and h1 above invert (trapezoidal on the curve)."""
        curve = self.stage_area(n=60)
        hs = np.array([c[0] for c in curve])
        As = np.array([c[1] for c in curve])
        grid = np.linspace(h0, h1, 200)
        a = np.interp(grid, hs, As)
        return float(np.sum(0.5 * (a[1:] + a[:-1]) * np.diff(grid)))


# --------------------------------------------------------------------------- resolution
_PARAM_FIELDS = {
    # element field -> parameter suffix under nbs.<type>.
    "max_ponding_depth_m": "max_ponding_depth_m",
    "soil_media_depth_m": "soil_media_depth_m",
    "side_slope_h_v": "side_slope_h_v",
    "permanent_pool_depth_m": "permanent_pool_depth_m",
    "outlet_diameter_m": "outlet_diameter_m",
    "outlet_coefficient": "outlet_coefficient",
    "outlet_weir_length_m": "outlet_weir_length_m",
    "longitudinal_slope_pct": "longitudinal_slope_pct",
    "top_width_m": "top_width_m",
    "manning_n": "manning_n",
    "vegetation_volume_fraction": "vegetation_volume_fraction",
    "storage_layer_depth_m": "storage_layer_depth_m",
    "well_diameter_m": "diameter_m",
    "well_depth_m": "depth_m",
    "dam_height_m": "dam_height_m",
}


def _fill(el: NbSElement, field: str, params: ParameterSet, key: str) -> None:
    if getattr(el, field) is None and key in params:
        p = params.get(key)
        setattr(el, field, p.value)
        el.param_sources[field] = f"{p.source.value}{'' if p.confirmed else ' (unconfirmed)'}: {key}"


SoilLookup = Callable[[BaseGeometry], Tuple[Optional[str], Optional[float]]]


def resolve_element(el: NbSElement, params: ParameterSet, soil_lookup: Optional[SoilLookup] = None) -> NbSElement:
    """Fill missing design values from parameters and compute derived quantities.

    ``soil_lookup(footprint) -> (zone_id, native_rate_mm_hr)`` supplies the soil under the element.
    """
    el = el.model_copy(deep=True)
    sp = spec(el.type)
    gtype = el.geometry.get("type")
    if gtype not in sp.geometry:
        raise ElementError(f"{el.id}: {sp.label} geometry must be one of {sp.geometry}, got {gtype}.")
    for field, suffix in _PARAM_FIELDS.items():
        _fill(el, field, params, f"nbs.{el.type}.{suffix}")
    if el.weir_length_m is None:
        _fill(el, "weir_length_m", params, "nbs.overflow_weir_length_m")
        if el.type == "inline_check_dam":
            _fill(el, "weir_length_m", params, "nbs.inline_check_dam.notch_width_m")
    if sp.is_storage and el.freeboard_m is None:
        _fill(el, "freeboard_m", params, "nbs.storage_freeboard_m")

    native_rate_mm_hr: Optional[float] = None
    if soil_lookup is not None:
        zone, native_rate_mm_hr = soil_lookup(el.footprint())
        if el.soil_zone is None:
            el.soil_zone = zone
    # infiltration: native soil unless the element states its own (recharge well: strata rate)
    if el.infiltration_rate_mm_hr is None:
        if el.type == "recharge_well":
            raise ElementError(
                f"{el.id}: recharge wells need infiltration_rate_mm_hr of the permeable strata "
                "(from borehole or percolation test data). It is not defaulted."
            )
        if native_rate_mm_hr is None:
            raise ElementError(f"{el.id}: no soil zone covers this element and no infiltration rate is given.")
        el.infiltration_rate_mm_hr = native_rate_mm_hr
        el.param_sources["infiltration_rate_mm_hr"] = f"soil zone {el.soil_zone}"

    if sp.is_storage and el.seepage_rate_mm_hr is None:
        if el.type == "recharge_well":
            el.seepage_rate_mm_hr = el.infiltration_rate_mm_hr
        else:
            key = f"nbs.{el.type}.seepage_fraction"
            frac = params.value_or(key, 1.0)
            el.seepage_rate_mm_hr = float(el.infiltration_rate_mm_hr) * float(frac)
            el.param_sources["seepage_rate_mm_hr"] = f"native rate x {key} = {frac}"

    if sp.is_storage and el.invert_elev_m is None:
        raise ElementError(f"{el.id}: storage elements need invert_elev_m (Phase 1 has no terrain to derive it).")

    fp = el.footprint()
    el.area_m2 = float(fp.area)
    el.storage_volume_m3 = storage_volume(el, params)
    el.drawdown_time_hr = analytic_drawdown_hr(el, params)
    return el


def storage_volume(el: NbSElement, params: ParameterSet) -> float:
    """Design storage volume, m3.

    LIDs: surface ponding (net of vegetation) plus media void storage.
    Storage elements: live volume between the permanent pool and the overflow crest.
    """
    sp = el.spec
    A = float(el.area_m2 or el.footprint().area)
    if sp.swmm == LID_BIORETENTION:
        veg = el.vegetation_volume_fraction or 0.0
        por = params.value_or(f"nbs.{el.type}.media_porosity", 0.45)
        fc = params.value_or(f"nbs.{el.type}.media_field_capacity", 0.2)
        void = params.value_or(f"nbs.{el.type}.storage_layer_void_ratio", 0.4)
        return A * (
            el.max_ponding_depth_m * (1 - veg)
            + (el.soil_media_depth_m or 0.0) * (por - fc)
            + (el.storage_layer_depth_m or 0.0) * void
        )
    if sp.swmm == LID_SWALE:
        W = el.top_width_m or 1.0
        d = el.max_ponding_depth_m
        z = el.side_slope_h_v or 0.0
        cross = d * max(W - z * d, 0.0)
        return (A / W) * cross * (1 - (el.vegetation_volume_fraction or 0.0))
    return el.volume_between(el.pool_depth_m, el.crest_depth_m)


def analytic_drawdown_hr(el: NbSElement, params: ParameterSet) -> Optional[float]:
    """Simple design drawdown estimate (hr); the SWMM-simulated drawdown is reported separately."""
    sp = el.spec
    if sp.swmm == LID_BIORETENTION:
        media = params.value_or(f"nbs.{el.type}.media_ksat_mm_hr", None)
        rate = min(el.infiltration_rate_mm_hr, media) if media else el.infiltration_rate_mm_hr
        return el.max_ponding_depth_m * 1000.0 / rate if rate > 0 else None
    if sp.swmm == LID_SWALE:
        r = el.infiltration_rate_mm_hr
        return el.max_ponding_depth_m * 1000.0 / r if r > 0 else None
    live = el.crest_depth_m - el.pool_depth_m
    r = el.seepage_rate_mm_hr or 0.0
    if el.type in ("detention_pond", "constructed_wetland") or (el.type == "retention_pond" and el.outlet_diameter_m):
        return None  # outlet-controlled: use the simulated drawdown
    return live * 1000.0 / r if r > 0 else None


def read_elements(fc: Dict[str, Any]) -> List[NbSElement]:
    """Parse a components FeatureCollection."""
    out = []
    ids = set()
    for i, f in enumerate(fc.get("features", [])):
        props = dict(f.get("properties") or {})
        if "id" not in props:
            raise ElementError(f"feature {i} has no 'id'.")
        if props["id"] in ids:
            raise ElementError(f"duplicate element id '{props['id']}'.")
        ids.add(props["id"])
        props["geometry"] = f["geometry"]
        out.append(NbSElement.model_validate(props))
    return out


def write_elements(elements: List[NbSElement]) -> Dict[str, Any]:
    feats = []
    for el in elements:
        props = el.model_dump(mode="json", exclude={"geometry"}, exclude_none=True)
        feats.append({"type": "Feature", "geometry": el.geometry, "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def to_geojson_geometry(g: BaseGeometry) -> Dict[str, Any]:
    return dict(mapping(g))
