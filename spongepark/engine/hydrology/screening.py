"""Volume screening of proposed park NbS against catchment runoff (TR-55 curve numbers).

A first-pass check before SWMM: how much of each design storm's runoff volume the proposed
storage can hold. Storage is taken as the surface volume (qty x area x depth) only; infiltration
during the storm, media pore space and outflows are ignored, so capture is understated. SWMM runs
replace this once surveys, soils and connections are known.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .tr55 import runoff_depth_mm

FIRST_INCH_MM = 25.4


@dataclass
class ParkScreen:
    id: str
    name: str
    park_area_m2: float
    catchment_area_m2: float
    cn_weighted: float
    storage_m3: float
    footprint_m2: float
    runoff_m3: Dict[str, float]  # keyed by return period ("2") or "first_inch"
    park_runoff_m3: Dict[str, float]
    capture_pct: Dict[str, float]
    fill_depth_mm: Optional[float]  # 24 h rainfall whose catchment runoff just fills the storage
    checks: List[str] = field(default_factory=list)


def _runoff(parts: List[dict], p_mm: float, ia_ratio: float) -> float:
    return sum(runoff_depth_mm(p_mm, pt["cn"], ia_ratio) * pt["area_m2"] / 1000.0 for pt in parts)


def _fill_depth(parts: List[dict], storage_m3: float, ia_ratio: float) -> Optional[float]:
    if storage_m3 <= 0:
        return None
    lo, hi = 0.0, 2000.0
    if _runoff(parts, hi, ia_ratio) < storage_m3:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _runoff(parts, mid, ia_ratio) < storage_m3 else (lo, mid)
    return hi


def screen_park(park: dict, depths_mm: Dict[str, float], park_cn: float, ia_ratio: float = 0.2,
                rel_tol: float = 0.01) -> ParkScreen:
    parts = park["catchment_parts"]
    checks: List[str] = []
    parts_area = sum(p["area_m2"] for p in parts)
    stated = park.get("catchment_area_m2")
    if stated and abs(parts_area - stated) > rel_tol * stated:
        checks.append(f"catchment parts sum to {parts_area:,.0f} m2, stated catchment is {stated:,.0f} m2 "
                      f"({100 * (parts_area - stated) / stated:+.1f} %).")
    storage = footprint = 0.0
    for it in park["interventions"]:
        v = it["qty"] * it["area_m2"] * it["depth_m"]
        storage += v
        footprint += it["qty"] * it["area_m2"]
        if "volume_m3" in it and abs(v - it["volume_m3"]) > max(0.01, rel_tol * v):
            checks.append(f"{it['name']}: {it['qty']} x {it['area_m2']} m2 x {it['depth_m']} m = {v:.1f} m3, "
                          f"sheet says {it['volume_m3']} m3.")
    ct = park.get("client_totals", {})
    if "volume_m3" in ct and abs(storage - ct["volume_m3"]) > max(0.1, rel_tol * storage):
        checks.append(f"total storage recomputes to {storage:.1f} m3, sheet total is {ct['volume_m3']} m3.")
    if "area_m2" in ct and abs(footprint - ct["area_m2"]) > max(0.1, rel_tol * footprint):
        checks.append(f"total footprint recomputes to {footprint:.0f} m2, sheet total is {ct['area_m2']} m2.")

    allp = {**{str(k): v for k, v in depths_mm.items()}, "first_inch": FIRST_INCH_MM}
    runoff = {k: _runoff(parts, p, ia_ratio) for k, p in allp.items()}
    park_q = {k: runoff_depth_mm(p, park_cn, ia_ratio) * park["park_area_m2"] / 1000.0 for k, p in allp.items()}
    capture = {k: (100.0 * min(1.0, storage / q) if q > 0 else 100.0) for k, q in runoff.items()}
    for rp, v in park.get("client_runoff_m3", {}).items():
        mine = runoff.get(str(rp))
        if mine is not None and abs(mine - v) > max(1.0, rel_tol * v):
            checks.append(f"{rp}-yr runoff recomputes to {mine:,.0f} m3, sheet says {v:,.0f} m3.")
    cnw = sum(p["cn"] * p["area_m2"] for p in parts) / parts_area
    return ParkScreen(park["id"], park["name"], park["park_area_m2"], parts_area, cnw, storage, footprint,
                      runoff, park_q, capture, _fill_depth(parts, storage, ia_ratio), checks)
