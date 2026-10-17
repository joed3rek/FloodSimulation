"""Canopy interception (SWMM does not model tree canopies).

Each tree canopy is a storage bucket of ``capacity_mm`` (per unit canopy area)
that fills first, from the start of the storm. Rain falling on canopy beyond
that capacity reaches the ground (throughfall). Evaporation from the canopy
during the storm is ignored (conservative: it would increase interception).

For a subcatchment with canopy cover fraction ``f`` and area-weighted capacity
``S`` the rainfall reaching the ground in interval k is

    net_k = gross_k - f * intercepted_k,   intercepted_k = min(gross_k, S - stored_k)

Net rainfall is applied to that subcatchment through its own rain gauge, and the
intercepted volume is reported as its own term in the water balance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..site.model import Tree

log = logging.getLogger(__name__)


@dataclass
class CanopyCover:
    fraction: float  # canopy area / subcatchment area, 0-1
    capacity_mm: float  # area-weighted interception capacity per unit canopy area
    canopy_area_m2: float


def canopy_cover(geom: BaseGeometry, trees: List[Tree], default_capacity_mm: float) -> CanopyCover:
    """Canopy fraction and weighted capacity over ``geom``. Overlapping crowns are not double counted."""
    if not trees or geom.area <= 0:
        return CanopyCover(0.0, 0.0, 0.0)
    pieces, weights = [], []
    for t in trees:
        c = t.canopy().intersection(geom)
        if c.area > 0:
            pieces.append(c)
            weights.append((c.area, t.interception_capacity_mm or default_capacity_mm))
    if not pieces:
        return CanopyCover(0.0, 0.0, 0.0)
    union_area = unary_union(pieces).area
    raw = sum(a for a, _ in weights)
    cap = sum(a * s for a, s in weights) / raw
    return CanopyCover(min(union_area / geom.area, 1.0), cap, union_area)


def intercept(depths_mm: np.ndarray, capacity_mm: float) -> np.ndarray:
    """Depth intercepted per interval (mm, per unit canopy area) by a bucket of ``capacity_mm``."""
    out = np.zeros_like(depths_mm, dtype=float)
    stored = 0.0
    for k, p in enumerate(depths_mm):
        take = min(p, max(capacity_mm - stored, 0.0))
        out[k] = take
        stored += take
    return out


def net_rainfall(depths_mm: np.ndarray, cover: CanopyCover) -> np.ndarray:
    """Subcatchment-average rainfall reaching the ground per interval, mm."""
    if cover.fraction <= 0:
        return depths_mm.astype(float).copy()
    return depths_mm - cover.fraction * intercept(depths_mm, cover.capacity_mm)


def intercepted_volume_m3(depths_mm: np.ndarray, cover: CanopyCover, area_m2: float) -> float:
    """Total intercepted volume over the subcatchment, m3."""
    return float(np.sum(depths_mm - net_rainfall(depths_mm, cover))) / 1000.0 * area_m2
