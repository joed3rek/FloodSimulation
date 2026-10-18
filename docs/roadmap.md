# Roadmap and open questions

The project follows the phases of [BRIEF.md](BRIEF.md) (Sponge Park Designer, section 15). Work
before that brief (survey import, terrain, layout generation, optimisation, Rhino, the 2D model,
reports) is already in the engine and is reused by the later phases.

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundations: shared JSON Schema, `.sponge` read and write in C# and Python, engine CLI, synthetic terrains | done: Python to Unity to Python round trip without loss |
| 1 | Engine core: rainfall and hyetographs, manual NbS from JSON, SWMM builder and runner, water balance, metrics | in progress |
| 2 | Unity shell and terrain | |
| 3 | GPU flood simulation | first version exists (WaterSim.compute, checked against the engine) |
| 4 | Survey import and baseline in the app | survey intake screen exists (DXF) |
| 5 | Editing tools | |
| 6 | Verification loop | |
| 7 | Proposal and ML | engine side exists (NSGA-II, surrogate) |
| 8 | Exports and reports | engine side exists |
| 9 | Calibration and packaging | calibration exists; packaging to do |

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
