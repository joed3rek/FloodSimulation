# Layout generation, grading and subcatchment rebuild (Phase 4)

`spongepark layout generate PROJECT [OPTION] [--type T ...]` proposes an NbS layout for an option,
grades it into the terrain, rebuilds the subcatchments on the graded ground and writes everything
the SWMM run of that option needs. Then `spongepark option run PROJECT OPTION` and
`spongepark option compare PROJECT OPTION` give its performance against the baseline.

The baseline must have been run first: elements are sized from its SWMM runoff.

## What it does, in plain terms

1. **Where can elements go?** Cells are ruled out when they are outside the site, within the
   boundary setback, under or near buildings (`layout.building_setback_m`), on mapped paths, roads,
   walls, drains or water (closed loops drawn around lawns block only the line itself), inside a
   tree's root protection radius, or steeper than the element allows.
2. **Where should they go?** Remaining cells get a score from four things, weighted by
   `layout.weight.*`: how much water reaches the cell, how low it is in the park, whether it is
   already a natural hollow (less digging) and how gentle the ground is.
3. **Placement, in treatment-train order** (`layout.types`):
   - *Detention / retention ponds* at the best low points receiving at least
     `nbs.<type>.min_contributing_area_m2`.
   - *Bioswales* along concentrated flow lines, from a channel head downhill, between
     `min_length_m` and `max_length_m`, at a longitudinal slope within the limits (brief: 1-4 %).
     They convey water towards the ponds.
   - *Rain gardens* on the remaining small drainage areas.
   - *Recharge wells* at each pond's spill point, taking its overflow. They are placed only when
     `site.recharge_strata_rate_mm_hr` and `site.rock_depth_m` are given (borehole data); the well
     must stop 0.5 m above rock.
4. **Sizing.** Each element is grown over nearby low ground until it holds the design-storm runoff
   of the area draining to it: runoff depth (baseline SWMM, `layout.design_return_period_yr`) x
   drainage area. Growth stops at the element's size limit or the area budget
   (`layout.max_area_pct`). The drainage area is re-measured once the footprint exists, because a
   footprint catches more than its first cell.
5. **Drawdown.** Elements emptied only by infiltration (rain gardens, swales, ponds without an
   outlet) are rejected when ponding depth / infiltration rate exceeds `nbs.max_drawdown_hr`. The
   report states the rate that would be needed.
6. **Grading** (on the DEM grid). Each pond or garden is cut below its *rim* (the lowest ground just
   outside it, where water would spill), with side slopes for ponds. Swales are trapezoidal channels
   whose invert never rises downstream. Grading only cuts; keep-out areas and designer elements are
   never altered. Cut volumes per element and in total are reported; the excavated soil is counted
   as export (fill is not designed).
7. **Subcatchment rebuild.** Flow is traced again on the graded ground with every element as a sink.
   Each element gets the subcatchment that really drains into it (`SC_<element>`); the rest keep
   their outfalls. Areas reconcile with the site exactly (checked).
8. **Routing.** Each element sends its outflow to the next element downstream, or to its outfall.
   Storage elements discharge only to storage elements (a SWMM rule).

Designer elements (source `designer`, or locked) already in the option are kept as they are and
everything else is placed around them.

## Outputs (`scenarios/<id>/`)

| File | Content |
|---|---|
| `elements.json` | Elements with all attributes, notes on how each was sized |
| `site/subcatchments.geojson` | Rebuilt subcatchments, used by this option's SWMM runs |
| `terrain/graded.tif` (also `terrain/graded_<id>.tif`) | Graded DEM |
| `terrain/cut.tif` | Cut depth per cell |
| `design_contours.geojson` | Contours of the graded ground (`layout.contour_intervals_m`) |
| `design.dxf` | Contours and footprints on SP-DSN-* layers, in survey coordinates: overlay it on the survey |
| `layout.png` | Keep-out areas, elements, subcatchments |
| `layout_report.json` | Sizes, targets, what limited each element, earthworks, skipped types and why |

`spongepark terrain export-unity PROJECT OUT --option ID` exports the graded ground with the
elements for a quick look in Unity; it shares origin and height datum with the existing-ground
export, so the two overlay exactly.

## Limits of this version

- No berms or fill: storage is what is cut below the existing rim.
- Sizing is a hand estimate; the SWMM run of the option is the result.
- Parameters are calls for the designer: every `layout.*` and `nbs.<type>.*` value is a default
  until confirmed.
