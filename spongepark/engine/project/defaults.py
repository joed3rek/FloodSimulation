"""Default parameter registry (Bengaluru context).

Every entry is stored in the project's ``parameters.json`` at creation, flagged
``default`` or ``literature`` and ``confirmed = False``. Reports list every
unconfirmed value. Site properties that must not be assumed (soil infiltration
per zone, rainfall depths, rock depth) are deliberately *absent* here: they are
required inputs.
"""

from __future__ import annotations

from typing import List, Tuple

from .parameters import Parameter, ParameterSet, Source

D = Source.DEFAULT
L = Source.LITERATURE

# (key, value, unit, source, note)
_DEFAULTS: List[Tuple[str, object, str, Source, str]] = [
    # --- project / units ------------------------------------------------------
    ("project.return_periods", [1, 2, 5, 10, 25, 50, 100], "yr", D, "Return periods analysed."),
    # --- rainfall --------------------------------------------------------------
    ("rainfall.time_step_min", 5, "min", D, "Hyetograph and rain gauge interval."),
    ("rainfall.storm_duration_hr", 24.0, "hr", D,
     "Design storm duration. Peak results are sensitive to this choice."),
    ("rainfall.hyetograph_method", "alternating_block", "-", D,
     "One of alternating_block, huff, user_csv. Peak results are sensitive to this choice."),
    ("rainfall.alternating_block_peak_position", 0.5, "fraction", D,
     "Position of the peak block within the storm (0 = start, 1 = end)."),
    ("rainfall.huff_quartile", 2, "-", D, "Huff curve quartile (1-4) when hyetograph_method = huff."),
    ("rainfall.short_duration_method", "imd_one_third", "-", L,
     "Used only when rainfall data are 24 h depths: P_t = P_24 (t/24)^(1/3) "
     "(IMD/CWC one-third power rule) to derive short-duration depths."),
    # --- simulation -------------------------------------------------------------
    ("sim.post_storm_hr", 72.0, "hr", D,
     "Simulated dry period after the storm so drawdown and slow release are captured."),
    ("sim.sample_step_s", 60, "s", D,
     "Interval at which SWMM state is sampled for time series and link volumes."),
    ("swmm.flow_routing", "DYNWAVE", "-", D, "SWMM routing method."),
    ("swmm.routing_step_s", 5.0, "s", D, "SWMM routing time step."),
    ("swmm.wet_step_s", 60, "s", D, "SWMM runoff wet-weather step."),
    ("swmm.dry_step_s", 300, "s", D, "SWMM runoff dry-weather step."),
    ("swmm.report_step_s", 300, "s", D, "SWMM report step (.rpt/.out)."),
    ("swmm.infiltration_method", "HORTON", "-", D,
     "HORTON, MODIFIED_HORTON, GREEN_AMPT, MODIFIED_GREEN_AMPT or CURVE_NUMBER. Soil zones must supply matching "
     "values; CURVE_NUMBER takes the pervious CN per subcatchment from TR-55 (tr55_cover + soil group)."),
    ("tr55.ia_ratio", 0.2, "-", L,
     "Initial abstraction ratio Ia/S for TR-55 hand checks (TR-55 eq. 2-2). Derived from US agricultural "
     "watersheds; TR-55 cautions its use in urban areas."),
    ("wastewater.lpcd", 150.0, "L/person/day", L,
     "Water supply per person for wastewater base flow (CPHEEO 1999; Bengaluru lake-cascade appendix)."),
    ("wastewater.return_fraction", 0.8, "-", L,
     "Share of supply returned as wastewater (CPHEEO 1999; Bengaluru lake-cascade appendix)."),
    ("swmm.continuity_error_limit_pct", 1.0, "%", D, "Runs above this continuity error are flagged."),
    ("swmm.lid_initial_saturation_pct", 0.0, "%", D,
     "Initial saturation of LID soil/storage. 0 = dry antecedent conditions; monsoon storms may "
     "arrive on wet soils."),
    ("evaporation.rate_mm_day", 4.0, "mm/day", L,
     "Constant potential evaporation (Bengaluru annual mean order of magnitude)."),
    # --- subcatchment surface defaults -----------------------------------------
    ("surface.n_imperv", 0.013, "s/m^(1/3)", L, "Manning's n, impervious surfaces."),
    ("surface.n_perv", 0.15, "s/m^(1/3)", L, "Manning's n, pervious surfaces (short grass)."),
    ("surface.dstore_imperv_mm", 1.5, "mm", L, "Depression storage, impervious."),
    ("surface.dstore_perv_mm", 5.0, "mm", L, "Depression storage, pervious (lawn)."),
    ("surface.pct_zero_imperv", 25.0, "%", L, "Impervious area with no depression storage."),
    # --- canopy interception -----------------------------------------------------
    ("interception.capacity_mm", 1.0, "mm", L,
     "Canopy interception storage capacity per unit canopy area when the species value is unknown "
     "(broadleaf trees typically 0.5-2 mm)."),
    # --- NbS: common -------------------------------------------------------------
    ("nbs.max_drawdown_hr", 48.0, "hr", D, "Maximum acceptable drawdown time (48-72 h typical)."),
    ("nbs.drawdown_threshold_m", 0.01, "m", D,
     "Ponded depth below which an element is considered drained (simulated drawdown)."),
    ("nbs.storage_freeboard_m", 0.3, "m", D, "Freeboard above the overflow crest of storage elements."),
    ("nbs.overflow_weir_length_m", 2.0, "m", D, "Default overflow spillway length."),
    ("nbs.overflow_weir_coefficient", 1.7, "m^0.5/s", L, "Weir discharge coefficient (SI, broad crest)."),
    ("nbs.retention_overflow_tolerance_fraction", 0.01, "fraction", D,
     "A storm counts as fully retained when site outflow plus flooding is at most this fraction "
     "of total inflow."),
    # --- rain garden -------------------------------------------------------------
    ("nbs.rain_garden.max_ponding_depth_m", 0.2, "m", D, "Surface ponding (berm) depth."),
    ("nbs.rain_garden.soil_media_depth_m", 0.6, "m", D, "Engineered soil media depth."),
    ("nbs.rain_garden.media_porosity", 0.45, "fraction", L, "Media porosity."),
    ("nbs.rain_garden.media_field_capacity", 0.2, "fraction", L, "Media field capacity."),
    ("nbs.rain_garden.media_wilting_point", 0.1, "fraction", L, "Media wilting point."),
    ("nbs.rain_garden.media_ksat_mm_hr", 100.0, "mm/hr", L, "Engineered media saturated conductivity."),
    ("nbs.rain_garden.media_conductivity_slope", 10.0, "-", L, "Conductivity slope."),
    ("nbs.rain_garden.media_suction_head_mm", 50.0, "mm", L, "Media suction head."),
    ("nbs.rain_garden.vegetation_volume_fraction", 0.1, "fraction", L, "Surface volume taken by plants."),
    ("nbs.rain_garden.storage_layer_depth_m", 0.0, "m", D,
     "Gravel storage layer under the media. 0 -> SWMM Rain Garden; >0 -> Bio-Retention Cell."),
    ("nbs.rain_garden.storage_layer_void_ratio", 0.4, "fraction", L, "Gravel void ratio."),
    # --- bioswale ------------------------------------------------------------------
    ("nbs.bioswale.max_ponding_depth_m", 0.3, "m", D, "Swale berm height (max flow depth)."),
    ("nbs.bioswale.longitudinal_slope_pct", 2.0, "%", D, "Longitudinal slope (1-4 % preferred)."),
    ("nbs.bioswale.side_slope_h_v", 3.0, "H:V", D, "Side slope, run per unit rise."),
    ("nbs.bioswale.manning_n", 0.2, "s/m^(1/3)", L, "Manning's n for vegetated swale surface."),
    ("nbs.bioswale.vegetation_volume_fraction", 0.1, "fraction", L, "Surface volume taken by plants."),
    ("nbs.bioswale.top_width_m", 3.0, "m", D, "Top width used when a swale is given as a centreline."),
    # --- detention pond --------------------------------------------------------------
    ("nbs.detention_pond.max_ponding_depth_m", 0.6, "m", D, "Live storage depth to overflow crest."),
    ("nbs.detention_pond.side_slope_h_v", 4.0, "H:V", D, "Side slope (gentle for public safety)."),
    ("nbs.detention_pond.outlet_diameter_m", 0.075, "m", D, "Bottom orifice diameter (controlled release)."),
    ("nbs.detention_pond.outlet_coefficient", 0.65, "-", L, "Orifice discharge coefficient."),
    ("nbs.detention_pond.seepage_fraction", 1.0, "fraction", D,
     "Bed seepage as a fraction of the native soil rate (1 = unlined dry basin)."),
    ("nbs.constructed_wetland.outlet_weir_length_m", 0.3, "m", D,
     "Adjustable outlet weir at permanent pool level that releases live storage (4.10 outlet zone)."),
    ("nbs.inline_check_dam.seepage_fraction", 0.0, "fraction", D,
     "Drain bed seepage as a fraction of native rate. 0 = lined drain; 4.12 allows infiltration only "
     "if no sewage line is present."),
    # --- retention pond ----------------------------------------------------------------
    ("nbs.retention_pond.permanent_pool_depth_m", 1.0, "m", D, "Permanent pool depth."),
    ("nbs.retention_pond.max_ponding_depth_m", 0.5, "m", D, "Live storage depth above the permanent pool."),
    ("nbs.retention_pond.side_slope_h_v", 4.0, "H:V", D, "Side slope (safety benching added in grading)."),
    ("nbs.retention_pond.seepage_fraction", 0.0, "fraction", D,
     "Bed seepage as a fraction of the native soil rate. 0 = lined pool (conservative)."),
    # --- recharge well -------------------------------------------------------------------
    ("nbs.recharge_well.diameter_m", 1.2, "m", D, "Well diameter."),
    ("nbs.recharge_well.depth_m", 6.0, "m", D, "Well depth (must stay above rock / water table)."),
    ("nbs.recharge_well.min_spacing_m", 10.0, "m", D, "Minimum spacing between recharge wells."),
    # --- constructed wetland (guideline 4.10) ----------------------------------------------
    ("nbs.constructed_wetland.permanent_pool_depth_m", 0.3, "m", L,
     "Shallow vegetated zone depth (4.10: 0.1-0.6 m; emergent plants <= 0.3 m)."),
    ("nbs.constructed_wetland.max_ponding_depth_m", 0.3, "m", D, "Live storage above the permanent pool."),
    ("nbs.constructed_wetland.side_slope_h_v", 4.0, "H:V", L, "Berm side slope (4.10: 3:1 to 4:1)."),
    ("nbs.constructed_wetland.seepage_fraction", 0.0, "fraction", D,
     "Bed seepage as a fraction of native rate. 0 = lined (4.10 requires lining where k > 1e-6 m/s)."),
    # --- edge engineering (guideline 4.11) ------------------------------------------------------
    ("nbs.edge_engineering.max_ponding_depth_m", 0.15, "m", L, "Edge ponding cap (4.11: 150-300 mm)."),
    ("nbs.edge_engineering.longitudinal_slope_pct", 1.0, "%", L, "Longitudinal slope (4.11: 0.5-2 %)."),
    ("nbs.edge_engineering.side_slope_h_v", 3.0, "H:V", L, "Bank slope (4.11: 3:1 to 4:1)."),
    ("nbs.edge_engineering.manning_n", 0.2, "s/m^(1/3)", L, "Manning's n, vegetated edge."),
    ("nbs.edge_engineering.vegetation_volume_fraction", 0.1, "fraction", L, "Surface volume taken by plants."),
    ("nbs.edge_engineering.top_width_m", 2.0, "m", D, "Edge strip width when given as a centreline."),
    # --- in-line check dam (guideline 4.12) -----------------------------------------------------
    ("nbs.inline_check_dam.dam_height_m", 0.45, "m", L, "Gabion check dam height (4.12: 0.3-0.6 m)."),
    ("nbs.inline_check_dam.notch_width_m", 0.5, "m", D, "Overflow notch width."),
    ("nbs.inline_check_dam.side_slope_h_v", 1.0, "H:V", D, "Drain pool side slope (near-vertical drain walls)."),
    # --- design guidelines -----------------------------------------------------------------------
    ("guidelines.enforce_errors", True, "-", D,
     "Refuse to run an option when an element breaches an 'error' guideline rule (warnings are reported only)."),
]


def default_parameters() -> ParameterSet:
    """Return a fresh set of all default parameters, all unconfirmed."""
    ps = ParameterSet()
    for key, value, unit, source, note in _DEFAULTS:
        ps.items[key] = Parameter(key=key, value=value, unit=unit, source=source, note=note, confirmed=False)
    return ps
