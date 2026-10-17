# Reports and calibration (Phase 8)

## Report

```
spongepark report PROJECT OUT_DIR [--option ID ...] [--no-pdf]
```

Writes one self-contained HTML file (charts embedded) and, when Edge or Chrome is installed, a PDF
printed from it. Next to it, `swmm/<option>/rp*.inp` holds every SWMM input file for independent
review. Sections:

1. Headline results per option: rain kept on site now and with the design, peak reduction, litres kept,
   largest storm fully retained.
2. Site and data: infiltration method, design storm method, rainfall table, soil zones with sources,
   survey quality (spot level RMSE, issues).
3. Existing condition: drainage map, water balance per storm, 2D flood map (indicative).
4. Each option: layout, component schedule (area, depth, storage, infiltration, design and SWMM
   drawdown, draining area, destination), earthworks (cut, fill, net, per element), SWMM water
   balance, comparison with the existing site, hydrographs and water balance charts, 2D maps,
   guideline findings with citations.
5. Optimisation: Pareto chart, surrogate accuracy and whether it was used, options; performance curve.
6. Calibration status.
7. Assumptions and limitations.
8. Every parameter with value, unit, source and whether the designer confirmed it.
9. The SWMM input files.

Labels are always shown: "uncalibrated: suitable for scenario comparison, not absolute prediction"
(or the calibration result), and "indicative" for 2D outputs.

## Calibration

```
spongepark calibrate PROJECT OPTION rainfall_event.csv observed.csv --target outflow_total_cms
```

- `rainfall_event.csv`: `time_min` and `intensity_mm_hr` (or `depth_mm`), e.g. a KSNDMC gauge record.
- `observed.csv`: `time_hr` and `value`, for a model series: `outflow_total_cms` (flow at the
  outfall) or `depth_<element>_m` (e.g. a level logger in a pond, or depths read from timestamped
  photos).

Four multipliers on site surfaces are fitted with SWMM in the loop (bounded Powell search, ranges
in `calibration.bounds`): infiltration (Horton/Green-Ampt rates, or the curve number's retention S),
Manning's n, depression storage and imperviousness. The fit is measured by the Nash-Sutcliffe
efficiency (NSE). Only when it reaches `calibration.min_nse` (0.5) are the factors stored as
site-measured parameters and the project relabelled *calibrated* (with the NSE and the event); all
later runs use them. Otherwise nothing changes and the report says the model stays uncalibrated.

Outputs: `calibration/report.json`, `calibration/history.json` (every trial), `calibration/calibration.png`.

One event is a weak calibration; check against a second event before relying on it.
