# Rainfall and design storms

## Return-period table

`rainfall/return_periods.csv` holds `return_period_yr`, `duration_hr` and `depth_mm` (or
`intensity_mm_hr`, converted to depth). A file with only `return_period_yr` and `depth_mm` is read
as **24-hour depths**.

When only 24-hour depths exist, shorter-duration depths come from the IMD/CWC one-third power rule,
`P_t = P_24 (t/24)^(1/3)` (parameter `rainfall.short_duration_method`, source `literature`). With an
IDF table, depths are interpolated log-log between durations.

## Design storms (parameter `rainfall.hyetograph_method`)

- **alternating_block** (default): blocks from the depth-duration curve, largest in the middle
  (`rainfall.alternating_block_peak_position`), others alternating either side. It embeds every
  duration's intensity in one storm.
- **huff**: Huff (1967) median curves, quartile 1-4. The built-in curve values are approximate
  digitisations. Replace them with curves derived from KSNDMC gauge data where possible.
- **user_csv**: a recorded storm (`time_min` plus `intensity_mm_hr` or `depth_mm`), resampled to the
  time step and scaled to each return period's depth.

Defaults: 24-hour storm, 5-minute step, 72-hour dry period afterwards (`sim.post_storm_hr`), so
slow release and drawdown are captured.

**Peak flows are sensitive to the storm pattern.** A 24-hour alternating-block storm built from 24-hour
depths with the one-third rule gives a very intense 5-minute peak (about 350 mm/h for the 100-year
example). Short-duration IDF data or real gauge storms are strongly preferred.
