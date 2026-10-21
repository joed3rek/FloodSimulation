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
    ("terrain.dem_cell_m", 0.5, "m", D, "DEM cell size built from survey points."),
    ("terrain.label_search_m", 3.0, "m", D,
     "Largest distance from a contour label to the contour it names (contours drawn at Z = 0)."),
    ("terrain.contour_point_spacing_m", 1.0, "m", D, "Spacing of points taken along contours for the TIN."),
    ("terrain.spot_tolerance_m", 0.15, "m", D,
     "Spot levels that differ from the surface built from their neighbours by more than this are flagged."),
    ("terrain.max_gap_m", 15.0, "m", D, "DEM cells farther than this from any survey point are flagged."),
    ("terrain.min_depression_depth_m", 0.02, "m", D,
     "Sink-filled areas shallower than this are survey noise, not depressions."),
    ("terrain.min_subcatchment_area_m2", 50.0, "m2", D,
     "Drainage areas smaller than this are merged into the neighbour they share most border with."),
    ("terrain.impervious_context_kinds", ["buildings"], "-", D,
     "Context kinds whose closed polygons count as impervious in terrain-derived subcatchments. Survey "
     "drawings often draw paths and roads as outlines around lawns, so they are not counted unless the "
     "designer adds them."),
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
    ("nbs.rain_garden.max_ponding_depth_m", 0.15, "m", D,
     "Surface ponding depth (HC 4.2 Calculations p.10: 75-150 mm; HC 4.11: 150-300 mm edge ponding)."),
    ("nbs.rain_garden.soil_media_depth_m", 0.6, "m", D, "Engineered soil media depth."),
    ("nbs.rain_garden.media_porosity", 0.45, "fraction", L, "Media porosity."),
    ("nbs.rain_garden.media_field_capacity", 0.2, "fraction", L, "Media field capacity."),
    ("nbs.rain_garden.media_wilting_point", 0.1, "fraction", L, "Media wilting point."),
    ("nbs.rain_garden.media_ksat_mm_hr", 50.0, "mm/hr", L,
     "Engineered media saturated conductivity (HC 4.2 p.10, 16: > 13 mm/hr, ideal 25-50 mm/hr after amendment)."),
    ("nbs.rain_garden.media_conductivity_slope", 10.0, "-", L, "Conductivity slope."),
    ("nbs.rain_garden.media_suction_head_mm", 50.0, "mm", L, "Media suction head."),
    ("nbs.rain_garden.vegetation_volume_fraction", 0.1, "fraction", L, "Surface volume taken by plants."),
    ("nbs.rain_garden.storage_layer_depth_m", 0.0, "m", D,
     "Gravel storage layer under the media. 0 -> SWMM Rain Garden; >0 -> Bio-Retention Cell."),
    ("nbs.rain_garden.storage_layer_void_ratio", 0.4, "fraction", L, "Gravel void ratio."),
    ("nbs.rain_garden.underdrain_on_slow_soil", True, "-", D,
     "On slow native soil, place rain gardens with a stone layer and a perforated underdrain (HC 4.2 Material "
     "Specification: HSG C/D partial infiltration with underdrain; HSG A/B full infiltration, no underdrain)."),
    ("nbs.underdrain_below_native_mm_hr", 13.0, "mm/hr", D,
     "Native soil slower than this needs an underdrain (HC 4.2: if native soil < 13 mm/hr, underdrain may be "
     "needed; HC 4.7: infiltration capacity > 13 mm/hr, target native rate >= 12.7 mm/hr)."),
    ("nbs.rain_garden.underdrain_storage_depth_m", 0.6, "m", D,
     "Stone base (drainage layer) of an underdrained rain garden (HC 4.2: 600 mm without tree, 750 mm with tree; "
     "min. 450 mm)."),
    ("nbs.bioswale.underdrain_gravel_depth_m", 0.45, "m", D,
     "Drainage layer of a bioswale on poor soil with an underdrain (HC 4.7: 300-450 mm)."),
    # --- bioswale ------------------------------------------------------------------
    ("nbs.bioswale.max_ponding_depth_m", 0.3, "m", D, "Swale berm height (max flow depth)."),
    ("nbs.bioswale.longitudinal_slope_pct", 2.0, "%", D, "Longitudinal slope (1-4 % preferred)."),
    ("nbs.bioswale.side_slope_h_v", 4.0, "H:V", D,
     "Side slope, run per unit rise (HC 4.7 p.6, 12: 4H:1V recommended, 3H:1V maximum)."),
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
    # --- green bridge (check dam across a bioswale) ---------------------------------------------
    ("nbs.green_bridge.dam_height_m", 0.15, "m", D,
     "Crest above the swale bottom (PUB ABC Waters check dams 100 mm; TRCA at most 0.6 m); kept below the swale depth."),
    ("nbs.green_bridge.top_width_m", 1.5, "m", D, "Deck width along the swale (a walkable crossing)."),
    ("nbs.green_bridge.seepage_fraction", 1.0, "fraction", D,
     "Pool bed seepage as a fraction of the native soil rate (1 = the swale's unlined bed)."),
    ("nbs.green_bridge.min_spacing_m", 10.0, "m", D, "Closest spacing of bridges on one swale (HC 10-15 m, TRCA 10-20 m)."),
    # --- layout generation (Phase 4) ---------------------------------------------------------------
    ("layout.types", ["detention_pond", "bioswale", "rain_garden", "recharge_well"], "-", D,
     "Element types the generator places, in order: ponds take the largest flows at low points, swales convey "
     "along flow lines towards them, rain gardens catch small areas, recharge wells take pond overflow."),
    ("layout.design_return_period_yr", 5, "yr", D,
     "Storm the generated elements are sized to capture (runoff depth from the baseline SWMM run)."),
    ("layout.max_area_pct", 10.0, "%", D, "Area budget: generated elements may cover at most this share of the site."),
    ("layout.boundary_setback_m", 2.0, "m", D, "No element closer than this to the site boundary."),
    ("layout.building_setback_m", 3.0, "m", L,
     "No infiltrating element closer than this to a building (foundation protection; 3 m / 10 ft is common)."),
    ("layout.tree_protection_radius_m", 3.0, "m", D,
     "Keep-out radius around existing trees without a mapped canopy (root protection; a mapped canopy is used "
     "when larger)."),
    ("layout.avoid_context_kinds", ["buildings", "paths", "roads", "water", "walls", "drains"], "-", D,
     "Mapped features no element may overlap (closed polygons; lines are buffered by the setback below)."),
    ("layout.line_feature_buffer_m", 1.0, "m", D, "Keep-out half-width around mapped line features (paths, walls)."),
    ("layout.element_spacing_m", 3.0, "m", D, "Minimum gap between generated elements."),
    ("layout.growth_climb_weight", 10.0, "m/m", D,
     "Footprint growth: metres of extra distance equivalent to 1 m of climb (higher = follows low ground more)."),
    ("layout.weight.accumulation", 0.4, "-", D, "Suitability weight: water reaching the cell."),
    ("layout.weight.low_ground", 0.3, "-", D, "Suitability weight: low ground within the site."),
    ("layout.weight.depression", 0.2, "-", D, "Suitability weight: existing natural depression (less excavation)."),
    ("layout.weight.gentle_slope", 0.1, "-", D, "Suitability weight: gentle ground slope."),
    ("layout.contour_intervals_m", [0.25, 0.5], "m", D, "Intervals of the design contours (finest goes to the DXF)."),
    ("nbs.rain_garden.max_ground_slope_pct", 8.0, "%", D, "Rain gardens only where the existing ground is flatter."),
    ("nbs.rain_garden.min_contributing_area_m2", 20.0, "m2", D, "Smallest drainage area worth a rain garden."),
    ("nbs.rain_garden.max_area_m2", 80.0, "m2", D, "Largest single rain garden."),
    ("nbs.rain_garden.min_area_m2", 6.0, "m2", D, "Smallest rain garden built."),
    ("nbs.bioswale.min_contributing_area_m2", 100.0, "m2", D, "Flow lines draining at least this area get a swale."),
    ("nbs.bioswale.min_length_m", 8.0, "m", D, "Shortest swale built."),
    ("nbs.bioswale.max_length_m", 40.0, "m", D, "Longest single swale."),
    ("nbs.bioswale.min_longitudinal_slope_pct", 0.5, "%", D,
     "Flattest swale (HC 4.7 p.6, 12: 0.5-2 % preferred, below 0.5 % water stagnates; HC 4.11 also 0.5 %)."),
    ("nbs.bioswale.max_longitudinal_slope_pct", 4.0, "%", D, "Steepest swale without drop structures (HC-4.11)."),
    ("nbs.retention_pond.max_ground_slope_pct", 10.0, "%", D, "Retention ponds only where the ground is flatter."),
    ("nbs.retention_pond.min_contributing_area_m2", 400.0, "m2", D, "Smallest drainage area worth a retention pond."),
    ("nbs.retention_pond.max_area_m2", 600.0, "m2", D, "Largest single retention pond."),
    ("nbs.retention_pond.min_area_m2", 60.0, "m2", D, "Smallest retention pond built."),
    ("nbs.detention_pond.max_ground_slope_pct", 10.0, "%", D, "Ponds only where the existing ground is flatter."),
    ("nbs.detention_pond.min_contributing_area_m2", 400.0, "m2", D, "Smallest drainage area worth a pond."),
    ("nbs.detention_pond.max_area_m2", 600.0, "m2", D, "Largest single pond."),
    ("nbs.detention_pond.min_area_m2", 40.0, "m2", D, "Smallest pond built."),
    # --- optimisation and surrogate (Phase 5) ----------------------------------------------------
    ("optimise.ranges", {
        "budget_use": [0.3, 1.0],
        "nbs.detention_pond.max_ponding_depth_m": [0.3, 1.0],
        "nbs.rain_garden.max_ponding_depth_m": [0.15, 0.30],
        "nbs.bioswale.max_ponding_depth_m": [0.15, 0.30],
        "layout.weight.accumulation": [0.1, 0.8],
        "layout.weight.low_ground": [0.1, 0.8],
    }, "-", D,
     "Search ranges. budget_use = share of layout.max_area_pct used; depth ranges are the public-safety "
     "ponding limits (rain garden and swale: HC-4.11 150-300 mm)."),
    ("optimise.return_period_weights", {}, "-", D,
     "Weight of each return period in the retention and peak objectives ({} = equal)."),
    ("optimise.target_return_period_yr", 10, "yr", D, "Inverse mode: storm to retain fully with the least area."),
    ("optimise.initial_samples", 16, "-", D, "Latin hypercube layouts evaluated in SWMM before the search."),
    ("optimise.active_rounds", 3, "-", D, "Active learning rounds (surrogate search, then SWMM checks)."),
    ("optimise.samples_per_round", 4, "-", D, "Surrogate picks verified in SWMM per round."),
    ("optimise.population", 40, "-", D, "NSGA-II population on the surrogate."),
    ("optimise.generations", 40, "-", D, "NSGA-II generations on the surrogate."),
    ("optimise.representatives", 4, "-", D, "Pareto options written to the project (3-5)."),
    ("optimise.seed", 7, "-", D, "Random seed (runs are deterministic)."),
    ("optimise.performance_curve_budgets_pct", [5, 10, 15, 20, 25], "%", D, "Budgets of the performance curve."),
    ("ml.min_r2", 0.8, "-", D, "Hold-out R2 every surrogate target must reach before the surrogate is used."),
    ("ml.test_fraction", 0.25, "fraction", D, "Share of SWMM-evaluated layouts held out to test the surrogate."),
    # --- 2D surface model (Phase 6) ---------------------------------------------------------------
    ("swmm.cn_dry_time_days", 7.0, "days", L,
     "SWMM curve-number drying time (days for saturated soil to recover); it barely affects a single design "
     "storm. 7 days is the SWMM 5 manual's typical value."),
    ("sim2d.engine", "auto", "-", D,
     "2D flood model: 'itzi' (Itzi, GPL, run as a separate program; set up with `spongepark itzi setup`), "
     "'builtin' (the engine's own local inertial model), or 'auto' (Itzi when it is set up)."),
    ("sim2d.cell_m", 1.0, "m", D, "2D model cell size (the DEM is block-averaged up to it)."),
    ("sim2d.courant", 0.7, "-", L, "Time step factor alpha in dt = alpha dx / sqrt(g h) (Bates et al. 2010)."),
    ("sim2d.max_time_step_s", 10.0, "s", D, "Longest 2D time step (dry periods)."),
    ("sim2d.frame_interval_s", 300.0, "s", D, "Interval of stored depth frames."),
    ("sim2d.extra_time_hr", 2.0, "hr", D, "Simulated time after the storm ends."),
    ("sim2d.flood_depth_threshold_m", 0.05, "m", D, "Depth counted as flooded in the 2D summary."),
    ("sim2d.volume_tolerance_pct", 5.0, "%", D,
     "Accepted difference between 2D and SWMM volume leaving the site, as a share of rainfall."),
    # --- calibration (Phase 8) -------------------------------------------------------------------
    ("calibration.infiltration_factor", 1.0, "-", D,
     "Multiplier on soil infiltration (Horton/Green-Ampt rates, or the curve number's retention S). Set by calibration."),
    ("calibration.roughness_factor", 1.0, "-", D, "Multiplier on Manning's n of site surfaces. Set by calibration."),
    ("calibration.depression_storage_factor", 1.0, "-", D, "Multiplier on depression storage. Set by calibration."),
    ("calibration.imperviousness_factor", 1.0, "-", D, "Multiplier on % impervious. Set by calibration."),
    ("calibration.bounds", {"infiltration": [0.3, 3.0], "roughness": [0.5, 2.0], "depression_storage": [0.3, 3.0],
                            "imperviousness": [0.7, 1.3]}, "-", D, "Search range of each calibration factor."),
    ("calibration.min_nse", 0.5, "-", D,
     "Nash-Sutcliffe efficiency the calibrated model must reach to be labelled calibrated."),
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
