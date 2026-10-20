"""Staged rules from PUB's Engineering Procedures for ABC Waters Design Features (condensed booklet, 2024 ed.)."""
from spongepark.engine.knowledge import staging

SRC, ED, CL = "pub_abc_waters", "Engineering Procedures, condensed booklet, 2024 edition", ["Af"]
F = "Condensed_Booklet_of_Engin_Procedures.pdf"
rules = []


def r(rid, page, section, snippet, element, category, parameter, unit, **kw):
    rules.append(staging.StagedRule(id=f"{SRC}.{rid}", source=SRC, edition=ED, file=F, page=page, section=section,
                                    snippet=snippet, element=element, category=category, parameter=parameter,
                                    unit=unit, climate=CL, **kw))


# ---------------------------------------------------------------- chapter 5: vegetated swales and buffer strips
r("vs.long_slope", 8, "5.2.2 Hydraulic Design", "longitudinal slopes of between 1 % and 4 %", "vegetated_swale", "geometry",
  "longitudinal_slope_pct", "%", min=1, max=4, condition="milder slopes waterlog; steeper need check banks")
r("vs.check_dam", 8, "5.2.2 Hydraulic Design", "low level rock weirs (e.g. 100 mm)", "check_dam", "geometry", "dam_height_m",
  "mm", value=100, condition="swales steeper than 4 %", severity="typical")
r("vs.v_minor", 9, "5.2.2 Hydraulic Design", "preferably less than 0.5 m/s for minor flood flows", "vegetated_swale",
  "geometry", "peak_velocity_m_s", "m/s", max=0.5, condition="minor flood flows (up to the 10-year ARI)")
r("vs.v_major", 9, "5.2.2 Hydraulic Design", "not more than 2.0 m/s for major flood flows", "vegetated_swale", "geometry",
  "peak_velocity_m_s", "m/s", max=2.0, condition="major flood flows (up to the 100-year ARI)", severity="requirement")
r("vs.dv_low", 9, "5.2.2 Hydraulic Design", "depth x velocity < 0.6 m2/s for low risk locations", "vegetated_swale",
  "safety", "depth_velocity_product", "m2/s", max=0.6, condition="low-risk locations (0.4 m2/s where pedestrian use is high)",
  severity="requirement")
r("vs.crossing_depth", 9, "5.2.2 Hydraulic Design", "maximum flow depth on driveway crossings = 0.3 m", "vegetated_swale",
  "safety", "max_flow_depth_crossing_m", "m", max=0.3, severity="requirement")
r("vs.side_slope", 17, "5.3.3.1 Swale Width and Side Slopes", "swale side slopes are typically between 1 in 10 and 1 in 4",
  "vegetated_swale", "geometry", "side_slope_h_v", "H:V", min=4, max=10, condition="parks, easements, medians",
  severity="typical")
r("vs.manning_shallow", 18, "5.3.3.3 Swale Capacity", "recommended values are between 0.15 and 0.3", "vegetated_swale",
  "geometry", "manning_n", "-", min=0.15, max=0.3, condition="flow shallower than the vegetation (treatment flows)")
r("vs.manning_deep", 18, "5.3.3.3 Swale Capacity", "0.03 – 0.05 at more than twice the vegetation depth", "vegetated_swale",
  "geometry", "manning_n", "-", min=0.03, max=0.05, condition="flow deeper than twice the vegetation (50-100 yr ARI)")
r("fs.slope", 20, "5.3.4.2 Buffer Requirements", "It is best if slopes can be kept below 5 %", "filter_strip", "geometry",
  "slope_pct", "%", max=5, condition="up to 20 % with well distributed flows")
r("fs.slope_max", 20, "5.3.4.2 Buffer Requirements", "buffers can still perform well with slopes up to 20 %",
  "filter_strip", "geometry", "slope_pct", "%", max=20, condition="flows well distributed; flow spreaders likely",
  severity="information")
r("fs.setdown", 20, "5.3.4.2 Buffer Requirements", "the top of the vegetation is set 60 mm below the edge of pavement",
  "filter_strip", "inlet", "inlet_drop_m", "mm", value=60, condition="slotted kerb with level drop")
r("vs.dv_all", 22, "5.3.5.2 Velocity and Depth Check", "depth x velocity of < 0.4 m2/s is not exceeded", "vegetated_swale",
  "safety", "depth_velocity_product", "m2/s", max=0.4, condition="all flows up to the major design event",
  severity="requirement")
r("vs.pit_blockage", 22, "5.3.6 Step 6: Size Overflow Pits", "assumes the field inlet is 50 % blocked", "vegetated_swale",
  "outlet", "overflow_pit_blockage_pct", "%", value=50, severity="requirement")

# ---------------------------------------------------------------- chapter 6: bioretention swales (bioswale)
r("bs.ksat_max", 50, "6.2.5 Filter media", "should not exceed 500 mm/hr", "bioswale", "media",
  "media_ksat_mm_hr", "mm/hr", max=500, severity="requirement", condition="to sustain vegetation growth")
r("bs.ksat_pref", 50, "6.2.5 Filter media", "preferably be between 100 - 300 mm/hr", "bioswale", "media",
  "media_ksat_mm_hr", "mm/hr", min=100, max=300, condition="50-100 mm/hr accepted with caution")
r("bs.curve_ed", 53, "6.3.1 Confirm treatment performance", "Extended Detention Depth = from 0 mm to 300 mm", "bioswale",
  "geometry", "max_ponding_depth_m", "mm", min=0, max=300, condition="range covered by the sizing curves", severity="typical")
r("bs.media_depth", 62, "6.3.4 Filter media", "Typical depths are between 600-1000 mm with a minimum depth of 400mm",
  "bioswale", "media", "soil_media_depth_m", "mm", min=400, max=1000, value=600,
  condition="400 mm only where depth is constrained")
r("bs.media_trees", 62, "6.3.4 Filter media", "must have a minimum depth of 1000 mm", "bioswale", "media",
  "soil_media_depth_m", "mm", min=1000, condition="deep rooted plants such as trees", severity="requirement")
r("bs.organic_max", 63, "6.3.4 Filter media", "should not result in more than 10% organic content", "bioswale", "media",
  "media_organic_content_pct", "%", max=10)
r("bs.ph", 63, "6.3.4 Filter media", "amended (if required) to between 5.5 and 7.5", "bioswale", "media", "media_ph", "-",
  min=5.5, max=7.5)
r("bs.ksat_tolerance", 63, "6.3.4 Filter media", "within ± 20% of the design saturated hydraulic conductivity",
  "bioswale", "construction", "media_ksat_tolerance_pct", "%", max=20,
  condition="laboratory tests of at least five samples")
r("bs.transition", 64, "6.3.4 Transition Layer", "The transition layer is recommended to be 100 mm thick", "bioswale",
  "media", "transition_layer_depth_m", "mm", value=100)
r("bs.drainage", 64, "6.3.4 Drainage Layer", "The drainage layer is to be a minimum of 200 mm thick", "bioswale", "media",
  "storage_layer_depth_m", "mm", min=200, severity="requirement")
r("bs.pipe_max", 65, "6.3.5.2 Under-drain design", "The recommended maximum diameter of the perforated pipes is 100 mm",
  "bioswale", "outlet", "underdrain_diameter_m", "mm", max=100)
r("bs.perf_blockage", 65, "6.3.5.2 Under-drain design", "A 50 % blockage of the perforation is recommended", "bioswale",
  "outlet", "underdrain_blockage_pct", "%", value=50)
r("bs.liner", 66, "6.3.5.4 Impermeable lining", "more than one order of magnitude (10 times) greater", "bioswale",
  "siting", "media_to_native_ksat_ratio_without_liner", "ratio", min=10,
  condition="filter media vs surrounding soil: above this no impermeable lining is needed")
r("bs.long_slope", 70, "Typical Design Parameters", "Swale longitudinal slope 1% to 4 %", "bioswale", "geometry",
  "longitudinal_slope_pct", "%", min=1, max=4, severity="typical")
r("bs.side_slope", 70, "Typical Design Parameters", "Swale side slope Maximum 1 in 3", "bioswale", "geometry",
  "side_slope_h_v", "H:V", min=3, condition="1 in 9 where vehicles cross at grade", severity="requirement")
r("bs.pipe_spacing", 72, "Design assessment checklist", "Maximum spacing of collection pipes <1.5m?", "bioswale", "outlet",
  "underdrain_spacing_m", "m", max=1.5)
r("bs.media_mix", 84, "6.6.6.2 Filter Media Specifications", "clay 2 – 4 %, silt 4 – 8 %, sand < 85 %", "bioswale", "media",
  "media_mix", "text", text="Sandy loam: clay 2-4 %, silt 4-8 %, sand < 85 % (FAWB 2009).", severity="typical")
r("bs.organic_range", 84, "6.6.6.2 Filter Media Specifications", "Organic content between 3% and 10%", "bioswale", "media",
  "media_organic_content_pct", "%", min=3, max=10)
r("bs.drainage_media", 84, "6.6.6.4 Drainage Layer Specifications", "The drainage layer is to be 2 - 5 mm screenings",
  "bioswale", "media", "drainage_layer_particle_m", "mm", min=2, max=5)

# ---------------------------------------------------------------- chapter 7: bioretention basins (rain_garden)
r("rg.ksat_max", 103, "7.3.5 Filter media", "should not exceed 500 mm/hr", "rain_garden", "media", "media_ksat_mm_hr",
  "mm/hr", max=500, severity="requirement", condition="to sustain vegetation growth")
r("rg.ksat_pref", 103, "7.3.5 Filter media", "preferably be between 100 - 300 mm/hr", "rain_garden", "media",
  "media_ksat_mm_hr", "mm/hr", min=100, max=300, condition="50-100 mm/hr accepted with caution")
r("rg.media_depth", 112, "7.4 Filter media", "Typical depths are between 600-1000 mm with a minimum depth of 400mm",
  "rain_garden", "media", "soil_media_depth_m", "mm", min=400, max=1000, value=600,
  condition="400 mm only where depth is constrained")
r("rg.transition", 114, "7.4 Transition Layer", "The transition layer is recommended to be 100 mm thick", "rain_garden",
  "media", "transition_layer_depth_m", "mm", value=100)
r("rg.drainage", 114, "7.4 Drainage Layer", "The drainage layer is to be a minimum of 200 mm thick", "rain_garden", "media",
  "storage_layer_depth_m", "mm", min=200, severity="requirement")
r("rg.submerged_zone", 114, "7.4 Submerged zone", "increased in depth by 120mm for every additional week", "rain_garden",
  "storage", "submerged_zone_extra_depth_per_dry_week", "mm", value=120,
  condition="submerged zone, per week of expected zero inflow")
r("rg.submerged_transition", 114, "7.4 Submerged zone", "a 50mm transition layer should separate the filter media",
  "rain_garden", "media", "submerged_zone_transition_m", "mm", value=50)
r("rg.targets", 129, "7.6 Worked example", "80%, 45% and 45% for TSS, TN and TP respectively", "rain_garden",
  "performance", "tss_load_reduction_pct", "%", value=80, condition="Singapore treatment targets (TN and TP 45 %)",
  severity="information")
r("rg.ed_example", 129, "7.6 Worked example", "The extended detention depth is 200 mm", "rain_garden", "geometry",
  "max_ponding_depth_m", "mm", value=200, condition="worked example", severity="typical")

staging.save(SRC, rules)
print(len(rules), "rules")
