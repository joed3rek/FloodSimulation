# spongepark

Stormwater design and flood simulation engine for **sponge parks**: sites that intercept,
infiltrate, store, recharge and slowly release rainfall with nature-based solutions (NbS).
Pilot: a park in Bengaluru (Habitat Collective).

**EPA SWMM 5.2 is the source of truth.** Every runoff, infiltration, storage and overflow number
comes from an unmodified SWMM engine run through PySWMM. The one exception is canopy
interception, which SWMM does not model; it is computed separately and reported as its own term.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Project file, parameters, CLI skeleton, synthetic terrains | done |
| 1 | Rainfall, hyetographs, manual NbS layout, SWMM build/run, water balance, metrics, charts | done |
| 2-8 | Survey import and terrain, baseline flow analysis, layout generation and grading, optimisation with a surrogate, Rhino round trip, Grasshopper, 2D model, engine API, Unity app, reports and calibration | done ([docs/roadmap.md](docs/roadmap.md)) |

## Install

```
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e .[dev]
```

Requires Python 3.10+ (see the Rhino note in [docs/roadmap.md](docs/roadmap.md)).

## Quick start

```
spongepark example examples/output          # synthetic 1 ha park, end to end
pytest                                      # all tests
```

Working on your own site, from the survey drawing:

```
spongepark project new park.sponge --name "Pilot park" --crs LOCAL
spongepark terrain standardise survey.dxf                      # optional: SP-* layer names
spongepark terrain inspect survey.dxf                          # suggested layer map: check, set "confirmed": true
spongepark terrain import park.sponge survey.dxf --map survey.layer_map.json
spongepark terrain delineate park.sponge                       # subcatchments and outfalls from the ground
spongepark site import park.sponge soils soil_zones.geojson    # infiltration per zone (never assumed)
spongepark rainfall import park.sponge return_periods.csv
spongepark params list park.sponge --unconfirmed
spongepark run park.sponge baseline                            # existing site, every return period
spongepark layout generate park.sponge auto                    # place, size and grade NbS
spongepark run park.sponge auto && spongepark compare park.sponge auto
spongepark optimise run park.sponge --mode forward             # Pareto options, SWMM-verified
spongepark optimise curve park.sponge                          # largest storm retained vs budget
spongepark sim2d run park.sponge auto 25                       # 2D surface flooding (indicative)
spongepark rhino export park.sponge auto auto.3dm              # edit in Rhino, then:
spongepark rhino import park.sponge auto auto_edited.3dm       # detects edits, regrades, reruns
spongepark report park.sponge report/                          # HTML + PDF report, SWMM files
spongepark serve                                               # web app at http://127.0.0.1:8765, API for Unity and Grasshopper
```

Most of this is easier in the web app: `spongepark serve`, then open http://127.0.0.1:8765 ([docs/web.md](docs/web.md)).

A hand-drawn layout can still be imported with `spongepark option import park.sponge manual layout.geojson`.
The Unity app is in `unity/SpongeParkApp` ([docs/unity.md](docs/unity.md)).

## NbS components

Eight component types, each with its SWMM representation and the design guideline rules it is
checked against (`spongepark nbs catalogue`, `spongepark nbs rules`):

rain garden, bioswale, detention pond, retention pond, recharge well, constructed wetland (4.10),
edge engineering (4.11) and in-line SWD check dam (4.12).

## Documentation

- [docs/project_file.md](docs/project_file.md): the `.sponge` package and the parameter system
- [docs/rainfall.md](docs/rainfall.md): return-period tables and design storms
- [docs/nbs_components.md](docs/nbs_components.md): components, SWMM representation and guideline checks
- [docs/swmm.md](docs/swmm.md): how the SWMM model is built and verified
- [docs/terrain.md](docs/terrain.md): survey import, layer standard, DEM quality checks, flow and subcatchments
- [docs/layout.md](docs/layout.md): layout generation, sizing, grading and subcatchment rebuild
- [docs/optimisation.md](docs/optimisation.md): NSGA-II optimisation, surrogate, performance curve
- [docs/rhino.md](docs/rhino.md): .3dm export, round trip and Grasshopper components
- [docs/sim2d.md](docs/sim2d.md): 2D rain-on-grid model (indicative)
- [docs/web.md](docs/web.md): the web app and its design system
- [docs/unity.md](docs/unity.md): the Unity app, GPU water and video
- [docs/report.md](docs/report.md): the report and calibration
- [docs/water_balance.md](docs/water_balance.md): water balance terms and metrics
- [docs/references.md](docs/references.md): reference register (guideline chapters, TR-55, lake-cascade appendix)
- [docs/limitations.md](docs/limitations.md): known limitations
- [docs/roadmap.md](docs/roadmap.md): phases and open questions
