"""Wastewater (dry-weather) inflow estimate used in the Bengaluru lake-cascade model.

V_ww = population x supply (lpcd) x return fraction
(Runoff volume appendix; CPHEEO 1999; JICA 2017 BWSSB Phase 3 report.)

Bengaluru storm water drains often carry sewage, so a park NbS fed by a drain may receive a
constant base flow that occupies storage before any rain falls. Not yet routed into SWMM: it needs
a confirmed drain entry point and population, so the pipeline asks for them instead of assuming.
"""

from __future__ import annotations


def wastewater_m3_day(population: float, lpcd: float = 150.0, return_fraction: float = 0.8) -> float:
    if population < 0 or lpcd < 0 or not 0 <= return_fraction <= 1:
        raise ValueError("population and lpcd must be >= 0 and return_fraction in [0, 1].")
    return population * lpcd * return_fraction / 1000.0


def wastewater_cms(population: float, lpcd: float = 150.0, return_fraction: float = 0.8) -> float:
    return wastewater_m3_day(population, lpcd, return_fraction) / 86400.0
