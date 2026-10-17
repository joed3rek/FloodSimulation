"""Static charts (PNG) for reports: water balance, hydrographs, performance curve.

Colours follow the validated 8-slot categorical palette (fixed order, never
cycled). Rainfall is drawn in its own panel above hydrographs (never a second
y-axis).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

log = logging.getLogger(__name__)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"

BALANCE_TERMS: List[Tuple[str, List[str]]] = [
    ("Canopy interception", ["interception_m3"]),
    ("Infiltration (ground)", ["infiltration_surfaces_m3"]),
    ("Infiltration (NbS)", ["infiltration_nbs_m3"]),
    ("Recharge (wells)", ["recharge_m3"]),
    ("Evaporation", ["evaporation_m3"]),
    ("Stored at end", ["storage_change_surface_m3", "storage_change_lid_m3", "storage_change_nodes_m3"]),
    ("Controlled release", ["outflow_controlled_m3"]),
    ("Runoff, overflow & flooding", ["outflow_runoff_m3", "outflow_overflow_m3", "flooding_m3"]),
]


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.yaxis.label.set_color(TEXT_2)
    ax.xaxis.label.set_color(TEXT_2)


def _fig(w: float, h: float, **kw):
    fig, ax = plt.subplots(figsize=(w, h), facecolor=SURFACE, **kw)
    return fig, ax


def water_balance_bars(summaries: Dict[str, Dict[str, Any]], path: Path, title: str = "") -> Path:
    """Stacked bars of the water balance (% of rainfall) per return period, one panel per option."""
    n = len(summaries)
    fig, axes = _fig(5.0 * n, 4.2, ncols=n, sharey=True, squeeze=False)
    for ax, (name, summ) in zip(axes[0], summaries.items()):
        rps = sorted(summ["return_periods"], key=int)
        bottom = [0.0] * len(rps)
        x = list(range(len(rps)))
        for (label, keys), color in zip(BALANCE_TERMS, SERIES):
            vals = []
            for rp in rps:
                wb = summ["return_periods"][rp]["water_balance"]
                vals.append(100.0 * max(sum(wb[k] for k in keys), 0.0) / wb["rainfall_total_m3"])
            ax.bar(x, vals, bottom=bottom, color=color, width=0.62, edgecolor=SURFACE, linewidth=1.0, label=label)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_xticks(x, [f"{rp} yr" for rp in rps])
        ax.set_title(name, color=TEXT, fontsize=10, loc="left")
        ax.set_ylim(0, 105)
        _style(ax)
    axes[0][0].set_ylabel("Share of rainfall (%)")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles[::-1], labels[::-1], loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8,
               labelcolor=TEXT_2)
    if title:
        fig.suptitle(title, color=TEXT, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def hydrographs(
    baseline: Dict[int, pd.DataFrame], option: Dict[int, pd.DataFrame], path: Path,
    option_label: str = "Proposed", window_hr: Optional[Tuple[float, float]] = None,
) -> Path:
    """Small multiples: one column per return period, rainfall panel above the outflow panel."""
    rps = sorted(option)
    fig, axes = plt.subplots(2, len(rps), figsize=(2.6 * len(rps), 4.6), facecolor=SURFACE, sharex=True,
                             gridspec_kw={"height_ratios": [1, 2.4]}, squeeze=False)
    for j, rp in enumerate(rps):
        o, b = option[rp], baseline.get(rp)
        ax_r, ax_q = axes[0][j], axes[1][j]
        ax_r.fill_between(o["time_hr"], o["rain_mm_hr"], step="post", color="#9ec5f4", linewidth=0)
        ax_r.invert_yaxis()
        if b is not None:
            ax_q.plot(b["time_hr"], b["outflow_total_cms"] * 1000.0, color=SERIES[0], linewidth=1.4, label="Existing")
        ax_q.plot(o["time_hr"], o["outflow_total_cms"] * 1000.0, color=SERIES[1], linewidth=1.4, label=option_label)
        ax_r.set_title(f"{rp}-year", color=TEXT, fontsize=9, loc="left")
        if window_hr:
            ax_q.set_xlim(*window_hr)
        _style(ax_r)
        _style(ax_q)
        ax_q.set_xlabel("Time (h)")
    axes[0][0].set_ylabel("Rain (mm/h)")
    axes[1][0].set_ylabel("Site outflow (L/s)")
    axes[1][0].legend(frameon=False, fontsize=8, labelcolor=TEXT_2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def performance_curve(points: Sequence[Dict[str, Any]], path: Path, label: str = "") -> Path:
    """Intervention area (% of site) against the largest storm retained, under two definitions."""
    order = [1, 2, 5, 10, 25, 50, 100]
    fig, ax = _fig(6.0, 3.8)
    xs = [p["intervention_area_pct"] for p in points]
    series = [
        ("No uncontrolled overflow", "design_no_overflow_storm_yr", SERIES[0]),
        ("Fully retained (no release at all)", "design_retention_storm_yr", SERIES[1]),
    ]
    for name, key, color in series:
        ys = [order.index(p[key]) + 1 if p[key] else 0 for p in points]
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=7, markeredgecolor=SURFACE,
                markeredgewidth=2, label=name)
        ax.annotate(name, (xs[-1], ys[-1]), textcoords="offset points", xytext=(6, 0), va="center", fontsize=8,
                    color=TEXT_2)
    ax.set_yticks(range(0, len(order) + 1), ["none"] + [f"{r} yr" for r in order])
    ax.set_xlabel("Intervention area (% of site)")
    ax.set_ylabel("Largest storm retained")
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT_2, loc="upper left")
    if label:
        ax.set_title(label, color=TEXT, fontsize=10, loc="left")
    _style(ax)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path
