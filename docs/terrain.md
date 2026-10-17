# Survey import and terrain analysis (Phases 2 and 3)

## Phase 2: survey drawing to DEM

```
spongepark terrain inspect park.dxf --out layer_map.json     # layers, suggested roles
spongepark terrain preview park.dxf --map layer_map.json     # picture of what each role picks up
spongepark terrain import park.sponge park.dxf --map layer_map.json --park-area-m2 2245
```

- **DXF** is read with ezdxf. **DWG** needs the free ODA File Converter, or Save As DXF in AutoCAD.
- **Layer map** (`layer_map.json`) assigns layers to roles: `spot_levels`, `contours`,
  `contour_labels`, `boundary`, `buildings`, `trees`, `drains`, `roads`, `paths`, `water`, `walls`.
  Layers whose meaning is unclear (for example `BE-LEVEL`) are listed in `needs_decision`. The import
  refuses an unconfirmed map unless explicitly overridden.
- **Contours** with true Z are read directly. Contours drawn at Z = 0 get their level from the
  nearest contour label within `terrain.label_search_m`. Unlabelled or conflicting contours are
  excluded and reported.
- **Spot levels** come from numeric text ("99.855", "RL 902.35"), 3D points, or block attributes.
  Duplicates are removed.
- **Contours as a check.** Many survey drawings contain contours generated from the spot grid.
  Set `contours_in_surface: false` and the surface is built from spot levels alone. Contours are then
  compared with it (`contour_vs_spots`), and any that disagree are flagged.
- **Surface**: Delaunay TIN with linear interpolation, gridded at `terrain.dem_cell_m`. No
  extrapolation beyond the survey points.

### Quality report (`terrain/qc.json`, `terrain/qc.png`)

| Check | Meaning |
|---|---|
| Spot cross-validation | each spot level against the surface built without it (10-fold); RMSE and outliers above `terrain.spot_tolerance_m` |
| Contour interval, crossings | contours at different levels must not cross |
| Contours vs spot levels | mean difference per contour |
| Flat triangle area | terracing from contour-only data |
| Gaps | share of DEM cells farther than `terrain.max_gap_m` from any point |
| Boundary | surveyed area vs stated park area; share of the boundary with data |

## Phase 3: flow and subcatchments

```
spongepark terrain delineate park.sponge
```

1. Priority-flood sink filling (Barnes et al. 2014). The fill depth gives the natural depressions
   (`terrain/flow/depressions.geojson`).
2. D8 steepest-descent flow directions and flow accumulation.
3. Water leaves where flow reaches the edge of the surveyed area. Neighbouring exit cells form one
   outfall. Drainage areas below `terrain.min_subcatchment_area_m2` merge into a neighbour.
4. Each outfall's drainage area becomes a SWMM subcatchment, with:
   - area
   - median slope
   - flow length (95th percentile of the D8 path length; width = area / flow length)
   - impervious share from building polygons
   - depression storage including the natural depressions as an equivalent depth

Outputs: `site/subcatchments.geojson`, `site/outfalls.geojson`, `site/boundary.geojson` (the
modelled area), `terrain/flow/*.tif`, `terrain/flow/report.json`, `terrain/flow/flow.png`.

### Limitations

- Compound walls are not modelled. Real exits are gates, wall openings and drain inlets, so
  outfall locations must be confirmed.
- The TIN has no breaklines, so kerbs and drain edges are smoothed.
- Survey drawings often draw paths and roads as outlines around lawns, so only buildings count as
  impervious unless the designer adds other kinds (`terrain.impervious_context_kinds`). Outlines that
  enclose the park are ignored and listed in the report.

## Layer standard (SP-*)

Every survey drawing can be converted to one set of layer names
(`spongepark/engine/io/data/layer_standard.json`), so the engine reads all parks the same way and
the designer sees the same layers in every DWG.

```
spongepark terrain standardise DRAWING.dxf                         # writes DRAWING.layer_renames.csv
spongepark terrain standardise DRAWING.dxf --renames DRAWING.layer_renames.csv
```

The second run writes `DRAWING_SP.dxf` (original untouched): layers renamed and merged, standard
colours, each layer's description records its original names, exact duplicate entities removed, empty
old layers deleted. It also writes `DRAWING_SP.layer_map.json`; SP-* layers get their role from the
standard, and `SP-CHECK-*` layers (meaning unclear) are listed under `needs_decision`.

| Group | Layers |
|---|---|
| Levels | SP-LVL-SPOT, SP-LVL-ROAD |
| Contours | SP-CONT-MAJOR, SP-CONT-MINOR, SP-CONT-LABEL |
| Site | SP-SITE-BOUNDARY, SP-SITE-BOUNDARY-LABEL, SP-BLDG, SP-WALL, SP-FENCE, SP-GATE, SP-STEP, SP-FURNITURE |
| Movement | SP-PATH, SP-ROAD, SP-ROAD-ANNO |
| Water | SP-DRAIN-EDGE, SP-DRAIN-LINE, SP-DRAIN-MANHOLE, SP-WATER, SP-WATER-TANK |
| Planting | SP-TREE, SP-TREE-COCONUT |
| Utilities | SP-UTIL-POWER |
| Annotation | SP-ANNO-TEXT, SP-ANNO-DIM, SP-ANNO-GRID, SP-ANNO-GRID-LABEL, SP-ANNO-TITLE, SP-ANNO-HATCH |
| To decide | SP-CHECK-BE-LEVEL, SP-CHECK-BOUNDARY-ALT, SP-CHECK-BUILDING-LINE |

Layers not in the standard become `SP-X-<old name>` (nothing is lost). To use a new surveyor's
name, add it to the layer's `aliases`.
