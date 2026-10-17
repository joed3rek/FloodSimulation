# The project file (`.sponge`) and parameters

A `.sponge` file is a zip of one project folder. Every module reads and writes it, so there are
no manual conversions. You can also work on an unzipped folder directly (useful for Rhino).

| Path | Content |
|---|---|
| `manifest.json` | schema version, name, city, CRS (default EPSG:32643, UTM 43N), units, dates, engine version, calibration status |
| `parameters.json` | every parameter: value, unit, source, note, confirmed |
| `terrain/existing.tif` | existing DEM (Phase 2; synthetic in the example) |
| `site/boundary.geojson` | site boundary |
| `site/subcatchments.geojson` | hand-drawn subcatchments (Phase 1; delineated from the DEM in Phase 3) |
| `site/external_catchment.geojson` | areas outside the site draining into it |
| `site/soil_zones.geojson` | infiltration parameters per zone |
| `site/outfalls.geojson` | where water leaves the site |
| `site/context.geojson` | trees (`kind: tree`, `canopy_radius_m`), buildings, paths, no-go zones |
| `rainfall/return_periods.csv` | depth per return period and duration |
| `rainfall/hyetographs/rp<N>.csv` | design storms |
| `options/<id>/components.geojson` | NbS elements (resolved values written back) |
| `options/<id>/model.inp` | complete SWMM model with every storm included |
| `options/<id>/swmm/rp<N>.inp/.rpt` | the exact files run for each return period |
| `options/<id>/results/` | `summary.json`, `comparison.json`, `rp<N>_timeseries.parquet`, charts |
| `options/<id>/guideline_findings.json` | design guideline breaches with citations |
| `locks.json` | elements locked by the designer |
| `history.json` | log of runs and edits |

`baseline` is the reserved option id for the existing site (no NbS).

## Parameters: no hidden defaults

Every value the engine uses lives in `parameters.json`, with:

- **source**: `default`, `literature`, `site measured` or `user` (a design decision such as the area budget)
- **confirmed**: `false` for every default until you confirm it

`spongepark params list park.sponge --unconfirmed` lists what is still assumed. Results record
the unconfirmed keys, and reports will flag them.

Soil infiltration, rainfall depths and recharge-well strata rates are **never** defaulted. They
must come from you.

## Coordinates

All geometry is in metres in a projected CRS (default UTM 43N) or local survey metres (`LOCAL`).
GeoJSON in longitude/latitude is rejected unless you pass `--source-crs EPSG:4326`, in which case
it is reprojected.

## Drawings inside the project

Projects created through the survey intake keep the surveyor's drawing and its cleaned copy (layers
on the SP-* standard) in `survey/`, so a single `.sponge` file carries everything: drawings,
parameters, ground model, options and results.
