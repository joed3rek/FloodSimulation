# Reference register

What the engine takes from each source document, and where it is used. Source PDFs belong in
`references/` (see `references/README.md`).

## Design guideline chapters 4.10, 4.11, 4.12

Component types `constructed_wetland`, `edge_engineering` and `inline_check_dam`, and the rules in
`spongepark/engine/nbs/data/guidelines.json` (each rule cites section and page). Checked before every
run; `error` rules stop the run. List them with `spongepark nbs rules`.

## TR-55: Urban Hydrology for Small Watersheds (NRCS, 1986)

Data in `spongepark/engine/hydrology/data/tr55.json`, functions in `spongepark/engine/hydrology/tr55.py`.

| Taken from TR-55 | Where | Used for |
|---|---|---|
| Runoff equation (eq. 2-1 to 2-4, metric form) | `runoff_depth_mm` | Hand check `spongepark site tr55` |
| Curve numbers, tables 2-2a, 2-2b, 2-2c | `curve_number`, `tr55_cover` on subcatchments | `CURVE_NUMBER` infiltration and hand check |
| Composite CN, figures 2-3 and 2-4 | `composite_cn` | Hand check |
| Hydrologic soil groups and disturbed-soil textures, Appendix A | `hsg`, `texture` on soil zones | CN lookup |
| Sheet, shallow concentrated and channel travel time (eq. 3-1 to 3-4, table 3-1) | `sheet_flow_tt_hr` and others | Time of concentration (Phase 3 subcatchments) |
| Limits: CN < 40, Q < 12.7 mm, sheet flow <= 91.44 m, Tc >= 0.1 h | `site_check` warnings | Hand check |

Verified against TR-55's worked examples 2-1 to 2-4 and 3-1, and tables 2-1 and 4-1 (`tests/test_tr55.py`).

Not taken: the SCS type I/IA/II/III 24-hour distributions. They are US storm patterns and TR-55 shows
them only as a figure (B-1); Bengaluru storms come from the project rainfall table instead. Also not
taken: the graphical peak discharge and tabular hydrograph methods (chapters 4-5) and the detention
routing curve (chapter 6). SWMM routes hydrographs directly, so these shortcuts are not needed.

### SWMM's CURVE_NUMBER option differs from TR-55

SWMM's curve-number infiltration has no 0.2S initial abstraction; depression storage takes that role.
With zero depression storage, SWMM follows the TR-55 equation with Ia = 0 (within 4 %, tested).
Setting depression storage to 0.2S does **not** reproduce the TR-55 Ia = 0.2S volume, because SWMM
keeps infiltrating while depression storage fills. So `site tr55` (Ia = 0.2S) and a SWMM
CURVE_NUMBER run will not match exactly. Treat the hand check as an order-of-magnitude check.

A curve number gives no infiltration rate. Under CURVE_NUMBER, NbS seepage still needs a measured
`ksat_mm_hr` for each soil zone under an element.

## Bengaluru lake-cascade model appendix (runoff volume, metric)

| Taken | Where |
|---|---|
| SCS-CN in mm with a general initial abstraction ratio λ | `runoff_depth_mm(..., ia_ratio)`, parameter `tr55.ia_ratio` |
| Wastewater = population x 150 lpcd x 0.8 (CPHEEO 1999; JICA 2017) | `hydrology/wastewater.py`, parameters `wastewater.lpcd`, `wastewater.return_fraction` |
| Lake water balance: opening + runoff + wastewater + upstream spill - evaporation - recharge - spill | Already covered by the SWMM storage-node balance (`docs/water_balance.md`) |

The wastewater estimate is not yet routed into SWMM. It needs the point where a sewage-carrying drain
enters the park, and the population it serves. These are site facts the engine will not assume.
The appendix uses a daily time step for lake cascades. The park model is event based (minutes), so
the cascade is represented by SWMM storage nodes and links, not by the daily equation.

## HSR_SPDN Runoff Volumes for Parks (Habitat Collective)

| Taken | Where |
|---|---|
| IMD 24-hour design depths, 2 to 1000 years (the same for Dhara Bendre, Chennaveera Kanavi, Nethravathi, Tree Park) | rainfall preset `hsr_imd_24h` (`spongepark/engine/rainfall/data/presets.json`), offered in Step 2 of the app |
| Open park (well maintained) CN 74; impervious 98, commercial 94, residential 90, herbaceous 70 | the same TR-55 values the ground questionnaire looks up (`site/ground.py`); CN 74 = TR-55 open space, good condition, soil group C |
| Park runoff per storm at CN 74 | `tests/test_ground.py` checks the questionnaire's runoff against this column |
| Catchment areas draining to each park (Dhara 11 550 m², Chennaveera 105 200 m², Nethravathi 211 640 m², Tree Park 2 231 452 m²) | not yet used: the external catchment needs its extent and where it enters the park |

The document has no 1-year depth, so with this rainfall the analysis covers 2 to 100 years.

## Ground questionnaire (TR-55)

Soil type gives the hydrologic soil group (Appendix A); each cover (grass lawn, shrubs, woods, trees over
grass, bare soil) and condition (well maintained > 75 % cover, fair 50-75 %, not maintained < 50 %,
barren) gives a TR-55 cover (tables 2-2a to 2-2c); the open park's curve number is the area-weighted mean.
"Not sure" about the soil uses group C, marked as assumed until a percolation test. Paved footpaths (from
the survey layers) are added to the impervious share. Infiltration becomes CURVE_NUMBER in SWMM and the 2D
model; SWMM's drying time is `soil.cn_dry_time_days` (7 days, SWMM manual).
