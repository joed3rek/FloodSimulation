# Water balance and metrics

Domain: the site plus any external catchment draining into it. For each option and return period:

```
Rainfall = canopy interception
         + infiltration (ground surfaces) + infiltration (NbS: LID media and pond beds)
         + recharge (wells)
         + evaporation
         + water still stored at the end (surface, LID media, ponds)
         + outflow leaving the site (direct runoff + controlled release + overflow)
         + node flooding
         + closure error
```

Every term except interception is a SWMM accumulator. The closure error and both SWMM continuity
errors are reported, and any run above 1 % is flagged (`swmm.continuity_error_limit_pct`).

## Metrics

| Metric | Definition |
|---|---|
| Retained % | (rainfall - outflow - flooding) / rainfall |
| Peak reduction % | 1 - option peak outflow / baseline peak outflow |
| Lag | option time-to-peak minus baseline time-to-peak (h) |
| Drawdown (simulated) | hours from peak depth until the element is within `nbs.drawdown_threshold_m` of empty (or of its permanent pool); `null` = not drained by the end of the run |
| Drawdown (design) | ponding depth / limiting infiltration rate (simple estimate) |
| Largest storm fully retained | largest return period (with all smaller ones) whose outflow plus flooding is at most `nbs.retention_overflow_tolerance_fraction` of rainfall |
| Largest storm with no uncontrolled overflow | same, counting only direct runoff, spillway overflow and flooding (controlled release allowed) |

The two retention definitions differ when a layout has a detention orifice, which releases water
in every storm. Which one is reported as the headline is a design decision (see roadmap).

## Performance curve

`spongepark perf-curve` scales the layout's footprints to 5-25 % of the site and runs every return
period at each size. In Phase 1 this is a uniformly scaled manual layout; Phase 5 replaces it with
optimised layouts.

All results are labelled **uncalibrated: suitable for scenario comparison, not absolute prediction**
until a calibration is run (Phase 8).
