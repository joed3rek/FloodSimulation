# The project file (`.sponge`) and parameters

A `.sponge` file is a zip of one project folder. Every module reads and writes it, so there are
no manual conversions. You can also work on an unzipped folder directly (useful for Rhino).

| Path | Content |
|---|---|
| `manifest.json` | schema version, name, city, CRS (default EPSG:32643, UTM 43N), units, dates, engine and app versions, calibration status |
| `parameters.json` | every parameter: value, unit, source, note, confirmed |
| `survey/` | the surveyor's drawing, its cleaned copy (SP-* layers) and the layer mapping |
| `terrain/existing.tif` | existing DEM |
| `terrain/edits.json` | terrain shaping operations (raise, lower, smooth, flatten, berm, check dam) |
| `site/boundary.geojson` | site boundary |
| `site/subcatchments.geojson` | subcatchments (hand drawn, or delineated from the DEM) |
| `site/external_catchment.geojson` | areas outside the site draining into it |
| `site/soil_zones.geojson` | infiltration parameters per zone |
| `site/outfalls.geojson` | where water leaves the site |
| `site/context.geojson` | trees (`kind: tree`, `canopy_radius_m`), buildings, paths, no-go zones |
| `rainfall/return_periods.csv` | depth per return period and duration |
| `rainfall/hyetographs/rp<N>.csv` | design storms |
| `scenarios/<id>/scenario.json` | name, status (draft, proposal, accepted, baseline), the proposal it started from |
| `scenarios/<id>/elements.json` | NbS elements (brief section 8.3), resolved values written back |
| `scenarios/<id>/terrain.tif` | the scenario's rebuilt terrain |
| `scenarios/<id>/model.inp` | complete SWMM model with every storm included |
| `scenarios/<id>/swmm/rp<N>.inp/.rpt` | the exact files run for each return period |
| `scenarios/<id>/results/` | `summary.json`, `comparison.json`, `rp<N>_timeseries.parquet`, charts |
| `scenarios/<id>/guideline_findings.json` | design guideline breaches with citations |
| `proposals/<id>.json` | optimiser proposals kept for comparison |
| `edit_log.json` | designer decisions about proposals (accept, edit, move, resize, delete) |
| `locks.json` | elements locked by the designer |
| `history.json` | log of runs and edits |

`baseline` is the reserved scenario id for the existing site (no NbS). The HTTP API still calls
scenarios "options" in its routes (`/projects/{id}/options/{scenario}`).

## One schema for Python and Unity

The JSON files are described once, as pydantic models in `spongepark/engine/project/schema.py`.

- `spongepark schema export` writes the shared JSON Schema, `schema/sponge.schema.json`.
- `spongepark schema csharp` generates the Unity classes from it
  (`Assets/SpongePark/Core/Data/SpongeSchema.g.cs`). `SpongePackage.cs` reads and writes `.sponge`
  files with them.
- `spongepark schema validate park.sponge` checks a project against the schema.

Tests fail if the committed schema or the C# classes fall behind the models. Every class keeps
fields it does not know (`Extra` in C#, extra fields in Python), so a file written by a newer
version is not damaged by an older one. Other files (rasters, GeoJSON, SWMM models) are carried
through byte for byte. The round trip Python, then Unity, then Python is tested
(`SPONGEPARK_TEST_UNITY=1 pytest tests/test_schema.py`).

Projects saved with schema 1.0 (`options/<id>/components.geojson`, source `user`) are upgraded
when they are opened.

## Parameters: no hidden defaults

Every value the engine uses lives in `parameters.json`, with:

- **source**: `default`, `literature`, `site measured` or `designer` (a design decision such as the area budget)
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
parameters, ground model, scenarios and results.
