"""Layout optimisation (Phase 5): NSGA-II over the generator settings, a surrogate to search faster,
active learning, and SWMM verification of everything reported.

Loop:
1. Latin hypercube sample of the design space; each sample is generated, graded and run in SWMM.
2. Train the surrogate on all SWMM-evaluated layouts. If it meets ``ml.min_r2`` on hold-out data,
   NSGA-II searches on the surrogate (thousands of cheap predictions); otherwise NSGA-II evaluates
   with SWMM directly (small population).
3. Active learning: the most promising, mutually distinct surrogate picks are run in SWMM and added
   to the data; repeat for ``optimise.active_rounds``.
4. The Pareto set is taken from SWMM-evaluated layouts only. Three to five representatives are
   written as options ``<prefix>_1..n`` and run in SWMM again, so every reported number is SWMM.

Modes:
- **forward**: maximise weighted retention, minimise weighted peak ratio and cut, within the area budget;
- **inverse**: minimise area and cut while fully retaining ``optimise.target_return_period_yr``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from ..ml.surrogate import Surrogate
from ..pipeline import compare, run_option
from ..layout.generate import generate
from ..project import Project
from .evaluate import evaluate, objectives
from .space import Space

log = logging.getLogger(__name__)


def _settings(project: Project, mode: str) -> Dict[str, Any]:
    P = project.parameters
    rps = [int(r) for r in P.value("project.return_periods")]
    w = P.value("optimise.return_period_weights") or {}
    return {
        "weights": {str(rp): float(w.get(str(rp), 1.0)) for rp in rps},
        "target_rp": int(P.value("optimise.target_return_period_yr")) if mode == "inverse" else None,
        "max_dd": float(P.value("nbs.max_drawdown_hr")),
        "tol": float(P.value("nbs.retention_overflow_tolerance_fraction")),
        "seed": int(P.value("optimise.seed")),
        "rps": rps,
    }


def _obj(rows, mode, s):
    F, G = [], []
    for r in rows:
        f, g = objectives(r, mode, s["weights"], s["target_rp"], s["max_dd"], s["tol"])
        F.append(f)
        G.append(g)
    return np.array(F, float), np.array(G, float)


def _surrogate_problem(space: Space, sur: Surrogate, mode: str, s: Dict[str, Any], rain_mm: Dict[int, float]):
    from pymoo.core.problem import Problem

    rps = s["rps"]
    w = np.array([s["weights"][str(rp)] for rp in rps])
    n_obj = 3 if mode == "forward" else 2
    xl, xu = space.bounds()
    flag_idx = [i for i, v in enumerate(space.variables) if v.kind == "flag"]

    class P(Problem):
        def __init__(self):
            super().__init__(n_var=space.n, n_obj=n_obj, n_ieq_constr=2, xl=xl, xu=xu)

        def _evaluate(self, X, out, *args, **kwargs):
            Fx = np.array([space.features(x) for x in X])
            pr = sur.predict(Fx, rps, rain_mm)
            retained = (pr["retained_pct"] * w).sum(1) / w.sum()
            peak = (pr["peak_ratio"] * w).sum(1) / w.sum()
            none = (X[:, flag_idx] < 0.5).all(1) if flag_idx else np.zeros(len(X), bool)
            g_dd = pr["max_drawdown_hr"] - s["max_dd"]
            if mode == "forward":
                F = np.column_stack([-retained, peak, pr["cut_m3"]])
                g2 = np.where(none, 1.0, -1.0)
            else:
                j = rps.index(s["target_rp"])
                F = np.column_stack([pr["area_pct"], pr["cut_m3"]])
                g2 = 100.0 - pr["retained_pct"][:, j] - 100 * s["tol"]
                g2 = np.where(none, 1e3, g2)
            out["F"] = F
            out["G"] = np.column_stack([g_dd, g2])

    return P()


def _direct_problem(project: Project, space: Space, mode: str, s: Dict[str, Any], rows: List[Dict[str, Any]]):
    from pymoo.core.problem import ElementwiseProblem

    n_obj = 3 if mode == "forward" else 2
    xl, xu = space.bounds()

    class P(ElementwiseProblem):
        def __init__(self):
            super().__init__(n_var=space.n, n_obj=n_obj, n_ieq_constr=2, xl=xl, xu=xu)

        def _evaluate(self, x, out, *args, **kwargs):
            r = evaluate(project, space, x)
            r["source"] = "nsga2-direct"
            rows.append(r)
            f, g = objectives(r, mode, s["weights"], s["target_rp"], s["max_dd"], s["tol"])
            out["F"], out["G"] = f, g

    return P()


def _pick_distinct(X: np.ndarray, F: np.ndarray, k: int, known: np.ndarray, xl, xu) -> np.ndarray:
    """Up to ``k`` points spread over the front (extremes first), not too close to evaluated points."""
    if len(X) == 0:
        return X
    span = np.where(xu > xl, xu - xl, 1.0)
    order = list(dict.fromkeys([int(np.argmin(F[:, j])) for j in range(F.shape[1])] + list(range(len(X)))))
    out: List[int] = []
    for i in order:
        xi = (X[i] - xl) / span
        near = [np.linalg.norm(xi - (X[j] - xl) / span) for j in out]
        near += [np.linalg.norm(xi - (kx - xl) / span) for kx in known]
        if not near or min(near) > 0.05:
            out.append(i)
        if len(out) == k:
            break
    return X[out]


def representatives(F: np.ndarray, k: int) -> List[int]:
    """Indices of up to ``k`` options from a front: the best per objective, then the most balanced."""
    picks = [int(np.argmin(F[:, j])) for j in range(F.shape[1])]
    lo, hi = F.min(0), F.max(0)
    norm = (F - lo) / np.where(hi > lo, hi - lo, 1.0)
    for i in np.argsort(np.linalg.norm(norm, axis=1)):
        picks.append(int(i))
    return list(dict.fromkeys(picks))[:k]


def optimise(project: Project, mode: str = "forward", n_initial: Optional[int] = None,
             rounds: Optional[int] = None, per_round: Optional[int] = None, pop_size: Optional[int] = None,
             n_gen: Optional[int] = None, n_final: Optional[int] = None, prefix: Optional[str] = None) -> Dict[str, Any]:
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.operators.sampling.lhs import LHS
    from pymoo.optimize import minimize
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting

    if mode not in ("forward", "inverse"):
        raise ValueError("mode must be 'forward' or 'inverse'.")
    P = project.parameters
    s = _settings(project, mode)
    space = Space.from_project(project)
    xl, xu = space.bounds()
    n_initial = n_initial or int(P.value("optimise.initial_samples"))
    rounds = rounds if rounds is not None else int(P.value("optimise.active_rounds"))
    per_round = per_round or int(P.value("optimise.samples_per_round"))
    pop_size = pop_size or int(P.value("optimise.population"))
    n_gen = n_gen or int(P.value("optimise.generations"))
    n_final = n_final or int(P.value("optimise.representatives"))
    prefix = prefix or ("pareto" if mode == "forward" else "inverse")
    base = project.read_json("scenarios/baseline/results/summary.json")
    rain_mm = {int(rp): float(v["storm"]["depth_mm"]) for rp, v in base["return_periods"].items()}
    missing = [rp for rp in s["rps"] if rp not in rain_mm]
    if missing:
        raise ValueError(f"run the baseline for return periods {missing} first.")

    ds_rel = "optimise/dataset.json"
    rows: List[Dict[str, Any]] = project.read_json(ds_rel) if project.exists(ds_rel) else []
    rows = [r for r in rows if len(r["x"]) == space.n and r.get("space") == space.names()]
    for r in rows:
        r.setdefault("source", "earlier run")

    # 1. initial design: Latin hypercube, every sample through grading + SWMM
    from pymoo.core.problem import Problem

    class _Box(Problem):
        def __init__(self):
            super().__init__(n_var=space.n, xl=xl, xu=xu)

    X0 = LHS().do(_Box(), n_initial, random_state=np.random.default_rng(s["seed"])).get("X")
    for i, x in enumerate(X0):
        r = evaluate(project, space, x)
        r.update(source="latin hypercube", space=space.names())
        rows.append(r)
        log.info("sample %d/%d: %s", i + 1, n_initial, "ok" if r["feasible"] else r.get("reason"))

    history: List[Dict[str, Any]] = []
    sur: Optional[Surrogate] = None
    for k in range(rounds):
        sur = Surrogate.train(rows, space.features, s["seed"] + k, float(P.value("ml.test_fraction")),
                              float(P.value("ml.min_r2")))
        entry: Dict[str, Any] = {"round": k + 1, "rows": len(rows),
                                 "surrogate_scores": sur.scores if sur else None,
                                 "surrogate_used": bool(sur and sur.usable)}
        if sur is not None and sur.usable:
            res = minimize(_surrogate_problem(space, sur, mode, s, rain_mm), NSGA2(pop_size=pop_size),
                           ("n_gen", n_gen), seed=s["seed"] + k, verbose=False)
            Xp = np.atleast_2d(res.X) if res.X is not None else np.empty((0, space.n))
            Fp = np.atleast_2d(res.F) if res.F is not None else np.empty((0, 3))
            known = np.array([r["x"] for r in rows])
            picks = _pick_distinct(Xp, Fp, per_round, known, xl, xu)
            for x in picks:
                r = evaluate(project, space, x)
                r.update(source=f"surrogate pick, round {k + 1}", space=space.names())
                rows.append(r)
            entry["evaluated"] = len(picks)
        else:
            entry["note"] = ("surrogate below ml.min_r2 on hold-out data: searched with SWMM directly"
                             if sur is not None else "too few feasible layouts to train a surrogate")
            before = len(rows)
            minimize(_direct_problem(project, space, mode, s, rows), NSGA2(pop_size=max(4, per_round)),
                     ("n_gen", 2), seed=s["seed"] + k, verbose=False)
            for r in rows[before:]:
                r["space"] = space.names()
            entry["evaluated"] = len(rows) - before
        history.append(entry)
        log.info("round %d: %s", k + 1, entry)

    project.write_json(ds_rel, rows)

    # 2. Pareto set from SWMM-evaluated layouts only
    feas = [r for r in rows if r.get("feasible")]
    if not feas:
        raise ValueError("no feasible layout was found: " + "; ".join({r.get("reason", "") for r in rows})[:500])
    F, G = _obj(feas, mode, s)
    ok = (G <= 0).all(1)
    cand = [r for r, o in zip(feas, ok) if o] or feas
    Fc, _ = _obj(cand, mode, s)
    front = NonDominatedSorting().do(Fc, only_non_dominated_front=True)
    front_rows = [cand[i] for i in front]
    reps = representatives(Fc[front], n_final)

    # 3. representatives written as options and re-run in SWMM
    options = []
    for n, i in enumerate(reps, start=1):
        r = front_rows[i]
        oid = f"{prefix}_{n}"
        rep = generate(project, oid, r["types"], r["overrides"])
        run_option(project, oid)
        c = compare(project, oid)
        options.append({"option_id": oid, "types": r["types"], "overrides": r["overrides"],
                        "area_pct": rep["intervention_area_pct"], "cut_m3": rep["cut_total_m3"],
                        "design_retention_storm_yr": c["design_retention_storm_yr"],
                        "retained_pct": {str(x["return_period_yr"]): x["option_retained_pct"] for x in c["rows"]},
                        "peak_reduction_pct": {str(x["return_period_yr"]): x["peak_reduction_pct"] for x in c["rows"]},
                        "swmm_verified": True})
    report = {
        "mode": mode,
        "target_return_period_yr": s["target_rp"],
        "space": [vars(v) for v in space.variables],
        "settings": {k: v for k, v in s.items() if k != "rps"},
        "evaluations_swmm": len(rows),
        "feasible": len(feas),
        "rounds": history,
        "surrogate_final": {"scores": sur.scores, "usable": sur.usable, "min_r2": sur.min_r2} if sur else None,
        "pareto_size": len(front_rows),
        "pareto": [{"types": r["types"], "overrides": r["overrides"], "area_pct": r["area_pct"],
                    "cut_m3": r["cut_m3"], "retained_pct": {rp: v["retained_pct"] for rp, v in r["per_rp"].items()},
                    "peak_ratio": {rp: v["peak_ratio"] for rp, v in r["per_rp"].items()},
                    "design_retention_storm_yr": r["design_retention_storm_yr"]} for r in front_rows],
        "options": options,
        "note": "Every number here comes from SWMM runs; the surrogate only chose which layouts to run.",
    }
    project.write_json(f"optimise/{mode}_report.json", report)
    _plot_front(project, mode, Fc, front, reps)
    project.history.log("optimise", mode=mode, evaluations=len(rows), options=[o["option_id"] for o in options])
    return report


def _plot_front(project: Project, mode: str, F: np.ndarray, front, reps) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 5), dpi=130)
    if mode == "forward":
        x, y, xl, yl = -F[:, 0], F[:, 1], "Weighted rainfall retained on site (%)", "Weighted peak outflow / baseline"
    else:
        x, y, xl, yl = F[:, 0], F[:, 1], "Intervention area (% of site)", "Cut volume (m3)"
    ax.scatter(x, y, s=14, color="#b9c2c0", label="SWMM-evaluated layouts")
    ax.scatter(x[front], y[front], s=22, color="#2a78d6", label="Pareto set")
    for n, i in enumerate(reps, start=1):
        j = front[i]
        ax.scatter(x[j], y[j], s=60, facecolor="none", edgecolor="#14201f")
        ax.annotate(str(n), (x[j], y[j]), xytext=(5, 5), textcoords="offset points", fontsize=8)
    ax.set_xlabel(xl)
    ax.set_ylabel(yl)
    ax.legend(fontsize=8, frameon=False)
    ax.set_title(f"Optimisation ({mode}); circled = options written to the project", fontsize=9)
    fig.tight_layout()
    fig.savefig(project.path(f"optimise/{mode}_pareto.png"))
    plt.close(fig)


def performance_curve(project: Project, budgets_pct: Optional[List[float]] = None) -> Dict[str, Any]:
    """Largest storm fully retained against intervention area budget (SWMM for every point)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    budgets_pct = budgets_pct or list(project.parameters.value("optimise.performance_curve_budgets_pct"))
    rows = []
    for b in budgets_pct:
        oid = f"_curve_{b:g}"
        try:
            rep = generate(project, oid, None, {"layout.max_area_pct": float(b)})
            run_option(project, oid)
            c = compare(project, oid)
            rows.append({"budget_pct": b, "area_pct": rep["intervention_area_pct"],
                         "design_retention_storm_yr": c["design_retention_storm_yr"],
                         "retained_pct": {str(x["return_period_yr"]): x["option_retained_pct"] for x in c["rows"]}})
        except Exception as ex:  # a budget too small for any element
            rows.append({"budget_pct": b, "area_pct": 0.0, "design_retention_storm_yr": None, "error": str(ex)[:200]})
        finally:
            import shutil

            shutil.rmtree(project.option_dir(oid), ignore_errors=True)
            t = project.path(f"terrain/graded_{oid}.tif")
            if t.exists():
                t.unlink()
    out = {"rows": rows, "note": "Each point: generated layout at that budget, SWMM run for every return period."}
    project.write_json("optimise/performance_curve.json", out)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4), dpi=130)
    xs = [r["budget_pct"] for r in rows]
    a1.plot(xs, [r["design_retention_storm_yr"] or 0 for r in rows], "o-", color="#2a78d6", lw=2)
    a1.set_xlabel("Area budget (% of site)")
    a1.set_ylabel("Largest storm fully retained (yr; 0 = none)")
    rps = sorted({int(k) for r in rows for k in r.get("retained_pct", {})})
    for rp in rps:
        a2.plot(xs, [r.get("retained_pct", {}).get(str(rp), np.nan) for r in rows], "o-", lw=1.5, label=f"{rp}-yr")
    a2.set_xlabel("Area budget (% of site)")
    a2.set_ylabel("Rainfall retained on site (%)")
    a2.legend(fontsize=7, frameon=False, ncol=2)
    fig.suptitle("Performance curve (SWMM, uncalibrated)", fontsize=10)
    fig.tight_layout()
    fig.savefig(project.path("optimise/performance_curve.png"))
    plt.close(fig)
    return out
