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
| 2-5 | Survey import and terrain, baseline flow analysis, layout generation and grading, optimisation with a surrogate | done |
| 6-8 | Rhino + 2D, Unity, reports | planned ([docs/roadmap.md](docs/roadmap.md)) |

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

Working on your own site:

```
spongepark project new park.sponge --name "Pilot park"
spongepark rainfall import park.sponge return_periods.csv
spongepark site import park.sponge boundary boundary.geojson
spongepark site import park.sponge subcatchments subcatchments.geojson
spongepark site import park.sponge soils soil_zones.geojson
spongepark site import park.sponge outfalls outfalls.geojson
spongepark option import park.sponge manual layout.geojson
spongepark params list park.sponge --unconfirmed
spongepark run park.sponge baseline
spongepark run park.sponge manual
spongepark compare park.sponge manual
spongepark charts park.sponge manual
spongepark perf-curve park.sponge manual --levels 5,10,15,20,25
```

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
- [docs/water_balance.md](docs/water_balance.md): water balance terms and metrics
- [docs/references.md](docs/references.md): reference register (guideline chapters, TR-55, lake-cascade appendix)
- [docs/limitations.md](docs/limitations.md): known limitations
- [docs/roadmap.md](docs/roadmap.md): phases and open questions
