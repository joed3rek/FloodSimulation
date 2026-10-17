# Known limitations

- SWMM is one-dimensional. Where water spreads on the ground comes only from the 2D model, which is
  labelled indicative. The 2D model does not route pond outlets or pipes, and applies no canopy
  interception.
- Uncalibrated results are for comparing scenarios, not for absolute prediction. Calibration needs
  observed events (rainfall plus flows, levels or timestamped flood photos).
- Results are sensitive to the design storm pattern and to infiltration values. A 24-hour depth
  with the alternating block method produces very intense short peaks.
- Recharge well performance depends on subsurface data. Wells are placed only when the strata
  infiltration rate and rock depth are given; in SWMM they seep through the bottom only (conservative).
- Canopy interception uses a simple bucket that fills first, with no evaporation during the storm.
- Water-quality benefits (wetlands, separators, NSBBs, floating wetlands) are not modelled.
- Grading only cuts: no berms or fill are designed, so each element overflows at the existing ground
  level on its rim and the excavated soil is counted as export.
- Generated layouts place detention and retention ponds, bioswales, rain gardens and recharge wells.
  Constructed wetlands, edge engineering and in-line check dams are modelled when drawn by the designer
  but are not placed automatically.
- Element sizes from the generator are hand estimates; the SWMM run of the option is the result.
- The optimiser varies the generator's settings (budget use, sizing storm, types, depths, placement
  weights), not every cell: it searches layouts the generator can produce.
- TR-55 curve numbers and soil groups come from US data. Treat them as literature values until checked
  against Bengaluru percolation tests or observed runoff.
- Wastewater base flow from sewage-carrying drains is estimated (`hydrology/wastewater.py`) but not
  routed into SWMM.
- Walls and gates are not modelled: water leaves wherever flow reaches the edge of the surveyed area.
- The Grasshopper components that build Rhino geometry, and the macOS and WebGL builds of the Unity app,
  have not been run here.
