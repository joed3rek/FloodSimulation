# Roadmap and open questions

The project follows the phases of [BRIEF.md](BRIEF.md) (Sponge Park Designer, section 15). Work
before that brief (survey import, terrain, layout generation, optimisation, Rhino, the 2D model,
reports) is already in the engine and is reused by the later phases.

| Phase | Scope | Status (2026-10-21) |
|---|---|---|
| 0 | Foundations: shared JSON Schema, `.sponge` read and write in C# and Python, engine CLI, synthetic terrains | done |
| 1 | Engine core: rainfall and hyetographs, manual NbS from JSON, SWMM builder and runner, water balance, metrics | done |
| 2 | Unity shell and terrain | done (built-in render pipeline, not URP: decided with the designer); workspace UI Pass 1 in review |
| 3 | GPU flood simulation | done (WaterSim.compute, checked against the engine's 2D model) |
| 4 | Survey import and baseline in the app | done for DXF (layer questions, Site setup, Analyse site with SWMM baseline); DEM (GeoTIFF) import and DWG (needs ODA) not in the app |
| 5 | Editing tools | mostly: five NbS tools plus green bridge, curves, carving, checks, budget meter, undo/redo. Missing: terrain brushes, rotate, duplicate, lock toggle, snapping. The live flood now runs on "Design done", not after every edit (designer's request) |
| 6 | Verification loop | partly: Check in SWMM and the verified results card. Missing: live-against-verified comparison panel and GPU calibration against SWMM |
| 7 | Proposal and ML | done: quick layout, NSGA-II optimiser with surrogate, options verified in SWMM, accept and edit |
| 8 | Exports and reports | done: report, DXF, Rhino, web viewer, video |
| 9 | Calibration and packaging | calibration routine done; packaging dropped by the designer |

Beyond the brief: existing recharge wells, green bridges, the NbS knowledge base ([KNOWLEDGE_BRIEF.md](KNOWLEDGE_BRIEF.md)),
the start screen and opening animation.

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
