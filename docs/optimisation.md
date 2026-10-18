# Optimisation and the surrogate model (Phase 5)

```
spongepark optimise run PROJECT --mode forward     # best retention / peak / earthworks within the budget
spongepark optimise run PROJECT --mode inverse     # least area that fully retains optimise.target_return_period_yr
spongepark optimise curve PROJECT                  # largest storm fully retained vs area budget
```

The baseline must be run first.

## What is varied

The optimiser does not move cells around. It varies the settings of the layout generator
([layout.md](layout.md)), and every setting gives a complete, graded, valid layout:

| Variable | Range (parameter `optimise.ranges`) |
|---|---|
| Share of the area budget used | 30-100 % of `layout.max_area_pct` |
| Storm the elements are sized for | any of `project.return_periods` |
| Which component types are included | on / off for each type in `layout.types` |
| Ponding depths per type | public-safety limits, e.g. rain garden and swale 150-300 mm (HC-4.11) |
| Placement weights | water reaching a cell vs low ground |

Keep-out areas, setbacks, locks and the drawdown rule hold for every candidate because the generator
enforces them.

## Objectives and constraints

- **Forward mode:** maximise rainfall retained on site, minimise peak outflow (as a share of the
  baseline peak) and minimise cut volume. Retention and peak are averaged over the return periods
  with `optimise.return_period_weights` (equal by default).
- **Inverse mode:** minimise intervention area and cut volume, subject to retaining the target storm
  fully (outflow within `nbs.retention_overflow_tolerance_fraction` of rainfall).
- **Constraint in both:** the longest simulated drawdown must not exceed `nbs.max_drawdown_hr`.

## How the search runs

1. `optimise.initial_samples` layouts from a Latin hypercube are generated, graded and run in SWMM.
2. A **surrogate** (gradient boosting) is trained to predict retained %, peak ratio, area, cut and
   drawdown. A quarter of the layouts are held out; each target must reach R² >= `ml.min_r2` (0.8)
   on them, or the surrogate is **not used** and NSGA-II evaluates candidates with SWMM directly.
3. NSGA-II searches on the surrogate (`optimise.population` x `optimise.generations` cheap
   predictions). The best distinct candidates are run in SWMM and added to the data (active
   learning), for `optimise.active_rounds` rounds.
4. The Pareto set is taken **from SWMM-evaluated layouts only**. Three to five representatives (the
   best on each objective plus the most balanced) are written as options `pareto_1..n` (or
   `inverse_1..n`) and run in SWMM again.

Every number in `optimise/<mode>_report.json` and in the options comes from SWMM. The surrogate only
chose which layouts to run; its hold-out scores are reported for transparency.

## Outputs (in the project)

| File | Content |
|---|---|
| `optimise/dataset.json` | Every SWMM-evaluated layout (settings, metrics); reused by later runs |
| `optimise/<mode>_report.json` | Rounds, surrogate scores, Pareto set, options |
| `optimise/<mode>_pareto.png` | All layouts, the Pareto set, the options written |
| `optimise/performance_curve.json/.png` | Largest storm fully retained and retained % against budget |
| `scenarios/pareto_n/` | Full options: components, graded DEM, SWMM models and results |

Runs are deterministic (`optimise.seed`).
