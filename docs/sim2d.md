# 2D surface simulation (Phase 6) - indicative

```
spongepark sim2d run PROJECT OPTION RP [--cell 1.0]     # OPTION may be 'baseline'
```

SWMM is one-dimensional: it gives volumes and flows but not where water spreads. The 2D model shows
surface ponding and overflow routes on the ground, before and after the intervention. Its results
are labelled **indicative** everywhere; SWMM remains the source of reported numbers.

## Method

Rain falls on every cell of the DEM (the option's graded ground, or the existing ground for the
baseline), block-averaged to `sim2d.cell_m`. Water moves between cells with the **local inertial**
form of the shallow water equations (Bates, Horritt & Fewtrell 2010; de Almeida et al. 2012), an
explicit scheme with an adaptive time step `dt = alpha dx / sqrt(g h)`. Manning's n comes from the
surface parameters (impervious on buildings). Water leaves over the edges of the site.

- **Infiltration** uses the same method as the SWMM model: curve number (SCS with Ia = 0, as SWMM),
  Horton decay, or constant Ksat for Green-Ampt.
- **NbS elements are sinks**: water on their cells goes into the element's store until its SWMM
  storage volume is full; the store empties at the element's infiltration or seepage rate. Once full,
  water stays on the surface and flows on.
- **Mass balance**: rainfall = ground infiltration + element infiltration + outflow + water left on
  the surface + water left in the elements. Outgoing flows are limited so no cell goes negative, which
  keeps the error at rounding level (reported every run).
- **Comparison with SWMM**: the volume leaving the site is compared with the SWMM run of the same
  option and storm, as a share of rainfall. `sim2d.volume_tolerance_pct` (5 %) is the acceptance
  limit used in the tests. On Nethravathi (25-yr) the difference was +1.3 % (existing ground) and
  -4.7 % (generated option).

## Outputs (`scenarios/<id>/sim2d/`)

| File | Content |
|---|---|
| `rp<N>.npz` | Depth frames every `sim2d.frame_interval_s` (float16), times, mask, origin, cell size |
| `max_depth_rp<N>.tif/.png` | Maximum depth map |
| `rp<N>_summary.json` | Mass balance, flooded area (>= `sim2d.flood_depth_threshold_m`), SWMM comparison |

The Unity app reads the frames through the engine API (`/sim2d/{rp}/frames`).

## Limits

- Controlled outlets of ponds are not routed in 2D (their water stays in the store); overflow happens
  on the surface when the store is full.
- Canopy interception is not applied in 2D.
- Pipes and drains are not modelled; water leaves at the site edge.
