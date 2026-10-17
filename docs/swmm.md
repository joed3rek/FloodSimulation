# How the SWMM model is built

`spongepark/engine/swmm/builder.py` turns the site, an NbS layout and the design storms into an
EPA SWMM 5.2 input file (SI units: m, mm, ha, m3/s; dynamic wave routing, 5 s step).

1. **Site subcatchments** have the NbS footprints cut out of them, so subcatchment areas plus
   element areas equal the site area (checked in the tests).
2. **LID elements** each get a subcatchment that is 100 % one LID unit. Upstream subcatchments
   route onto it. Its outflow goes to `outflow_to`.
3. **Storage elements** become a storage node with a tabular stage-area curve and constant bed
   seepage (`Ksat` only, the SWMM 5.2 seepage option). A "direct rain" subcatchment (`DR_*`) over the
   footprint makes sure rain on the water surface is counted. Controlled outlets are side orifices,
   or a weir at pool level for wetlands. Overflow is a transverse weir at the crest.
4. **Outfalls**: SWMM allows one incoming link per outfall. Each link leaving the site gets its own
   outfall node (`OUT1__WR_RP1`) at the same place and invert. That also gives exact controlled
   and overflow volumes.
5. **Canopy interception** is applied outside SWMM. Subcatchments under canopy get their own rain
   gauge carrying below-canopy rainfall.

Output per option: `model.inp` (every storm included, gauges on the largest) and `swmm/rp<N>.inp`
(the exact file run, plus its `.rpt`) for independent review.

## Verification (tests)

- An impervious plane with no losses gives runoff equal to rainfall (within 0.5 %).
- A pervious surface whose infiltration capacity exceeds rainfall gives no runoff.
- Pond seepage equals Ksat x area x time (within 2 %).
- A **hand-built SWMM model** (`tests/fixtures/hand_built_simple.inp`, written independently)
  matches the generated model within 1 % for controlled release, overflow, infiltration, seepage and
  peak pond depth.
- The synthetic park runs all seven return periods with SWMM continuity errors and water-balance
  closure below 1 %.

## Notes for reviewers

- Recharge wells seep through the **bottom only** (SWMM storage seepage uses the bottom and sloped
  banks; vertical walls add no area). This is conservative.
- LID infiltration to native soil uses the soil-zone rate under the element. Rain garden media
  conductivity is a separate parameter.
- PySWMM 2.2 issues worked around: routing `final_storage` is returned in ft3 for SI models, so
  final storage is summed from node volumes. `Node.statistics` crashes for outfalls in models
  without links, so outfall statistics are used instead.

## Curve-number infiltration

Set `swmm.infiltration_method` to `CURVE_NUMBER` to use TR-55 curve numbers. Each soil zone needs a
hydrologic soil group (`hsg`, or a `texture` or measured rate it can be derived from) and
`dry_time_days`. Each site or external subcatchment needs `tr55_cover`, the TR-55 cover of its
pervious part, or an explicit `curve_number`. Only the pervious CN is passed to SWMM, because SWMM
handles `pct_imperv` itself. See `docs/references.md` for how SWMM's CN form differs from TR-55.
