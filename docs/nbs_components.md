# NbS components and design guidelines

## Catalogue

Each component type is one entry in `spongepark/engine/nbs/data/components.json`. To add a new
guideline chapter, add an entry there and its rules to `guidelines.json`.

| Type | Guideline | Functions | SWMM representation |
|---|---|---|---|
| rain_garden | - | infiltration, detention | LID Rain Garden (Bio-Retention Cell if a gravel layer is set) in its own subcatchment |
| bioswale | - | conveyance, infiltration | LID Vegetative Swale in its own subcatchment |
| detention_pond | - | detention, infiltration | storage node, bottom orifice (controlled release), crest spillway |
| retention_pond | - | retention | storage node with permanent pool, crest spillway, optional orifice at pool level |
| recharge_well | - | infiltration | cylindrical storage node seeping at the strata rate, overflow at the rim |
| constructed_wetland | 4.10 | retention, detention, treatment | storage node, shallow permanent pool, outlet weir at pool level, spillway |
| edge_engineering | 4.11 | conveyance, infiltration, habitat | LID Vegetative Swale along the edge |
| inline_check_dam | 4.12 | detention, treatment | small storage pool behind the dam with a notch weir |

Water-quality treatment (separators, NSBBs, floating wetlands, wetland polishing) is **not**
modelled by SWMM in this version. Those benefits are reported qualitatively, never as volume.

## Element attributes

Every element carries the fields required by the brief: id, type, geometry, area_m2,
max_ponding_depth_m, storage_volume_m3, infiltration_rate_mm_hr, soil_media_depth_m,
drawdown_time_hr, contributing_area_m2, inflow_from, outflow_to, overflow_to, locked, source.
It also carries design details (invert, side slope, outlet size, etc.). Missing values are filled
from `nbs.<type>.*` parameters, and `param_sources` records each one.

Routing:

- `inflow_from` lists the subcatchments that drain to the element.
- `outflow_to` is the downstream element or outfall. For LIDs this is all surface outflow; for storage it is the controlled outlet.
- `overflow_to` is the storage spillway destination.

## Design guideline checks

`guidelines.json` holds every numeric range from the Habitat Collective chapters 4.10-4.12, each
with its source, section and page. Before each run, every element is checked against each rule
that applies to it. Findings are written to `options/<id>/guideline_findings.json`:

- **error** (e.g. orifice < 75 mm, freeboard < 300 mm): the run stops unless `guidelines.enforce_errors` is false
- **warning** (e.g. side slopes outside 3:1-4:1, ponding outside 150-300 mm, infiltration < 13 mm/h)
- **info** (e.g. lining required where native k > 1e-6 m/s)

Run `spongepark option check park.sponge <option>` to see the findings without running SWMM.

## Storage quantities

- Rain gardens: ponding x (1 - vegetation fraction) + media depth x (porosity - field capacity) + gravel layer x void ratio.
- Swales: trapezoidal cross-section x length.
- Ponds and wetlands: the stage-area curve is built by offsetting the footprint inwards at the side slope, then integrated between the permanent pool and the crest.
