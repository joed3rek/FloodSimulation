"""TR-55 (NRCS 1986) curve numbers, runoff equation and travel time, in metric units.

Used for:
- the pervious curve number of each subcatchment when ``swmm.infiltration_method`` is
  ``CURVE_NUMBER`` (SWMM computes the impervious share itself, so only the pervious CN is passed);
- independent hand checks of SWMM runoff volumes (``site_check``);
- time-of-concentration estimates (sheet, shallow concentrated and channel flow).

Equation and table numbers refer to TR-55, Second Edition, June 1986.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Dict, Iterable, List, Optional, Tuple

FT = 0.3048
IN = 25.4


class TR55Error(ValueError):
    pass


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(resources.files(__package__).joinpath("data/tr55.json").read_text(encoding="utf-8"))


def covers(kind: Optional[str] = None) -> Dict[str, dict]:
    out = {k: v for k, v in data()["curve_numbers"].items() if not k.startswith("_")}
    return {k: v for k, v in out.items() if kind is None or v["kind"] == kind}


# ------------------------------------------------------------------ soils
def hsg_from_rate(rate_mm_hr: float) -> str:
    """Hydrologic soil group from the minimum (saturated) infiltration rate (Appendix A)."""
    for g in "ABC":
        if rate_mm_hr > data()["hsg"][g]["min_rate_mm_hr"]:
            return g
    return "D"


def hsg_from_texture(texture: str) -> str:
    """Hydrologic soil group for a disturbed, uncompacted profile from its surface texture (Appendix A)."""
    t = data()["disturbed_soil_texture_hsg"].get(texture.strip().lower())
    if t is None:
        raise TR55Error(f"texture '{texture}' is not in TR-55's disturbed-soil table.")
    return t


def _single_hsg(hsg: str) -> str:
    g = hsg.strip().upper()
    if "/" in g:
        raise TR55Error(
            f"dual group '{hsg}': TR-55 uses the first letter if the soil is effectively drained, "
            "the second if not. Enter the single group that applies."
        )
    if g not in "ABCD" or len(g) != 1:
        raise TR55Error(f"unknown hydrologic soil group '{hsg}'.")
    return g


def curve_number(cover: str, hsg: str) -> float:
    """CN from TR-55 tables 2-2a to 2-2c for a cover key (see ``covers()``) and soil group."""
    c = covers().get(cover)
    if c is None:
        raise TR55Error(f"unknown TR-55 cover '{cover}'. Known: {', '.join(sorted(covers()))}.")
    return float(max(c[_single_hsg(hsg)], 30))


# ------------------------------------------------------------------ runoff (chapter 2)
def retention_mm(cn: float) -> float:
    """Potential maximum retention S (mm), eq. 2-4 in metric: S = 25400/CN - 254."""
    if not 0 < cn <= 100:
        raise TR55Error(f"curve number {cn} out of range (0, 100].")
    return 25400.0 / cn - 254.0


def runoff_depth_mm(p_mm: float, cn: float, ia_ratio: float = 0.2) -> float:
    """Direct runoff Q (mm), eq. 2-1 with Ia = ia_ratio * S."""
    s = retention_mm(cn)
    ia = ia_ratio * s
    if p_mm <= ia:
        return 0.0
    return (p_mm - ia) ** 2 / (p_mm - ia + s)


def composite_cn(cn_pervious: float, pct_imperv: float, unconnected_ratio: float = 0.0,
                 cn_imperv: float = 98.0) -> float:
    """Composite CN (figures 2-3 and 2-4, Appendix F).

    ``unconnected_ratio`` R is the share of impervious area that drains over pervious ground.
    TR-55 applies the R reduction only when total impervious area is below 30 %.
    """
    f = pct_imperv / 100.0
    r = unconnected_ratio if pct_imperv < 30 else 0.0
    return cn_pervious + f * (cn_imperv - cn_pervious) * (1 - 0.5 * r)


def weighted_cn(parts: Iterable[Tuple[float, float]]) -> float:
    """Area-weighted CN from (cn, area) pairs (worksheet 2)."""
    parts = list(parts)
    a = sum(x for _, x in parts)
    return sum(cn * x for cn, x in parts) / a


# ------------------------------------------------------------------ travel time (chapter 3)
def sheet_flow_tt_hr(n: float, length_m: float, p2_24h_mm: float, slope: float) -> float:
    """Sheet flow travel time, Manning's kinematic solution (eq. 3-3). TR-55 limits L to 300 ft (91.44 m)."""
    if length_m > data()["limits"]["max_sheet_flow_length_m"] + 1e-6:
        raise TR55Error(f"sheet flow length {length_m:.1f} m exceeds TR-55's 91.44 m (300 ft) limit.")
    L_ft = length_m / FT
    p2_in = p2_24h_mm / IN
    return 0.007 * (n * L_ft) ** 0.8 / (p2_in ** 0.5 * slope ** 0.4)


def shallow_velocity_m_s(slope: float, paved: bool) -> float:
    """Average shallow concentrated flow velocity (figure 3-1, Appendix F)."""
    return (20.3282 if paved else 16.1345) * slope ** 0.5 * FT


def channel_velocity_m_s(area_m2: float, wetted_perimeter_m: float, slope: float, n: float) -> float:
    """Manning's equation (eq. 3-4) in SI."""
    r = area_m2 / wetted_perimeter_m
    return r ** (2.0 / 3.0) * slope ** 0.5 / n


def travel_time_hr(length_m: float, velocity_m_s: float) -> float:
    """Eq. 3-1."""
    return length_m / (3600.0 * velocity_m_s)


# ------------------------------------------------------------------ site hand check
@dataclass
class SubcatchCheck:
    id: str
    area_m2: float
    hsg: str
    cn_pervious: float
    cn_source: str
    pct_imperv: float
    cn_composite: float
    runoff_mm: Dict[float, float]
    runoff_m3: Dict[float, float]
    warnings: List[str]


def site_check(site, depths_mm: Dict[float, float], ia_ratio: float = 0.2) -> List[SubcatchCheck]:
    """TR-55 runoff for every site and external subcatchment, as an independent check on SWMM.

    Impervious areas are treated as directly connected (figure 2-3).
    """
    out: List[SubcatchCheck] = []
    lim = data()["limits"]
    for s in site.subcatchments + site.external:
        cnp, src, hsg = site.pervious_cn(s)
        cnc = composite_cn(cnp, s.pct_imperv)
        a = s.shape().area
        q = {rp: runoff_depth_mm(p, cnc, ia_ratio) for rp, p in depths_mm.items()}
        w = []
        if cnc < lim["min_weighted_cn"]:
            w.append(f"weighted CN {cnc:.0f} < 40: TR-55 advises another procedure.")
        low = [rp for rp, v in q.items() if v < lim["low_runoff_depth_mm"]]
        if low:
            w.append(f"runoff < 12.7 mm for {', '.join(f'{r:g}-yr' for r in low)}: the CN method is less accurate.")
        out.append(SubcatchCheck(s.id, a, hsg, cnp, src, s.pct_imperv, cnc, q,
                                 {rp: v * a / 1000.0 for rp, v in q.items()}, w))
    return out
