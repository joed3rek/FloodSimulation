# Roadmap and open questions

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundations | done |
| 1 | SWMM engine with manual layout | done |
| 2 | DWG/DEM import, layer mapping, TIN, DEM, quality checks | next |
| 3 | Sink fill, flow direction/accumulation, subcatchments, baseline SWMM from terrain | |
| 4 | Suitability scoring, placement, sizing, grading, contours, subcatchment rebuild | |
| 5 | pymoo NSGA-II, surrogate ML, active learning, inverse mode | |
| 6 | rhino3dm export/round trip, Grasshopper components, 2D rain-on-grid | |
| 7 | Unity app | |
| 8 | Reports, calibration, documentation | |

## Technical notes

- **Python version.** The engine targets Python 3.10+ (developed on 3.10.6). Rhino 8's embedded
  CPython is 3.9, so the Grasshopper components will call the engine through the local FastAPI
  server or a subprocess rather than importing it inside Rhino. This is decided in Phase 6.
- **Component catalogue.** New guideline chapters are added as data (`components.json`,
  `guidelines.json`) without code changes, unless they need a new SWMM representation.

## Decisions needed from the designer

See the end-of-phase summary for the current list: retention definition, rainfall data type,
infiltration data per zone, external catchment, rock depth, ponding limits, area budget, and
whether guideline chapters for rain gardens, bioswales, ponds and recharge wells exist.
