# Known limitations

- SWMM is one-dimensional. Where water spreads on the ground will come only from the 2D module
  (Phase 6), which will be labelled indicative.
- Uncalibrated results are for comparing scenarios, not for absolute prediction.
- Results are sensitive to the design storm pattern and to infiltration values. A 24-hour depth
  with the one-third rule produces very intense short peaks.
- Recharge well performance depends on subsurface data. In SWMM, wells seep through the bottom only
  (conservative).
- Canopy interception uses a simple bucket that fills first, with no evaporation during the storm.
- Water-quality benefits (wetlands, separators, NSBBs, floating wetlands) are not modelled.
- Phase 1 subcatchments are drawn by hand, and Phase 1 storage inverts are entered by hand. Both
  come from the DEM from Phase 3/4.
- The Phase 1 performance curve scales one manual layout uniformly. It is not an optimisation.
- TR-55 curve numbers and soil groups come from US data. Treat them as literature values until checked
  against Bengaluru percolation tests or observed runoff.
- Wastewater base flow from sewage-carrying drains is estimated (`hydrology/wastewater.py`) but not yet
  routed into SWMM.
