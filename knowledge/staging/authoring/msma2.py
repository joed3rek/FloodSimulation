"""Staged rules from MSMA 2nd Edition (DID Malaysia, 2012): chapters 7 (detention pond), 8 (infiltration),
11 (water quality ponds and wetlands)."""
from spongepark.engine.knowledge import staging

SRC, ED, CL = "msma2", "2nd edition, August 2012", ["Af"]
F = "MSMA2ndEdition_august_2012.pdf"
rules = []


def r(rid, page, section, snippet, element, category, parameter, unit, **kw):
    rules.append(staging.StagedRule(id=f"{SRC}.{rid}", source=SRC, edition=ED, file=F, page=page, section=section,
                                    snippet=snippet, element=element, category=category, parameter=parameter,
                                    unit=unit, climate=CL, **kw))


DP, WP, RW, IT, WL = "detention_basin", "retention_pond", "recharge_well", "infiltration_trench", "constructed_wetland"
# ---------------------------------------------------------------- chapter 7: detention pond
r("dp.lw", 194, "7.1.1 System Components", "The length to width ratio of the storage zone should be at least 3:2",
  DP, "geometry", "length_to_width", "ratio", min=1.5)
r("wp.catchment", 194, "7.1 Introduction", "For wet pond, the catchment area served is greater than 10ha",
  WP, "siting", "contributing_area_m2", "ha", min=10, condition="baseflow to keep the permanent pool", severity="requirement")
r("dp.wq_depth", 195, "7.1.2 Water Quality Control", "designed and constructed based on 40mm runoff depth", DP,
  "pretreatment", "water_quality_runoff_depth", "mm", value=40, condition="pretreatment BMPs upstream of detention ponds",
  severity="requirement")
r("dp.release", 196, "7.2.1 (b) Release Timing", "is recommended to be within 24 hours", DP, "storage", "drawdown_time_hr",
  "hr", max=24, condition="outflow hydrograph release (empty) time")
r("dp.safety_depth", 196, "7.2.1 (e) Public Safety", "Recommended depths of dry pond are limited to 1.2 m or 1.5 m",
  DP, "safety", "max_ponding_depth_m", "m", max=1.5, value=1.2, condition="otherwise fence the pond", severity="requirement")
r("dp.safety_slope", 196, "7.2.1 (e) Public Safety", "The side slope of ponds should not be steeper than 1(V):4(H)",
  DP, "safety", "side_slope_h_v", "H:V", min=4, condition="steeper slopes may need a fence or rail", severity="requirement")
r("dp.forebay", 197, "7.2.2.2 GPTs and Sediment Forebay", "one-third (1/3) of water quality pond or wetlands volume",
  DP, "pretreatment", "forebay_volume_fraction", "%", value=33.3, condition="of the water quality pond or wetland volume")
r("dp.forebay_lw", 197, "7.2.2.2 GPTs and Sediment Forebay", "with a minimum length to width ratio of 2:1", DP,
  "pretreatment", "forebay_length_to_width", "ratio", min=2)
r("dp.wq_share", 197, "7.2.2.3 Water Quality Pond or Wetlands", "a volume of about 30% of the detention pond volume",
  DP, "pretreatment", "water_quality_volume_fraction", "%", value=30, severity="typical")
r("dp.trash_area", 198, "7.2.3.2 Trash Racks", "at least ten (10) times larger than the control outlet opening", DP,
  "outlet", "trash_rack_area_ratio", "ratio", min=10)
r("dp.trash_angle", 198, "7.2.3.2 Trash Racks", "A maximum angle of 60o to the horizontal", DP, "safety",
  "trash_rack_angle_deg", "-", max=60, condition="inclined bar racks")
r("dp.spillway", 199, "7.2.4 Secondary Outlet", "a minimum design storm of 100 year ARI", DP, "outlet",
  "spillway_design_storm", "yr", min=100, condition="non-hazard small detention ponds", severity="requirement")
r("dp.dry_time", 199, "7.2.5.1 Dry Time", "Dry pond is proposed to be emptied within 12 hours after rain stops", DP,
  "storage", "drawdown_time_hr", "hr", max=12)
r("wp.dry_time", 199, "7.2.5.1 Dry Time", "back to normal 24 hours after the rain ceases", WP, "storage",
  "drawdown_time_hr", "hr", max=24, condition="water level of a wet pond")
r("dp.low_flow", 200, "7.2.5.2 Low Flow Channel", "computed based on 10mm runoff depth from the contributing catchment",
  DP, "inlet", "low_flow_bypass_runoff_depth", "mm", value=10)
r("dp.max_depth", 200, "7.2.6.2 (a) Pond Water Depth", "should not exceed 3.0 m under normal operating conditions", DP,
  "safety", "max_ponding_depth_m", "m", max=3.0, condition="embankments not classified as dams", severity="requirement")
r("dp.side_slope", 200, "7.2.6.2 (c) Side Slopes", "side slopes of 1(V):6(H) or flatter are recommended", DP, "geometry",
  "side_slope_h_v", "H:V", min=6, condition="for public safety and mowing (1:4 maximum)")
r("dp.floor", 200, "7.2.6.2 (d) Bottom Grades", "a minimum grade of 1% to provide positive drainage", DP, "geometry",
  "floor_slope_pct", "%", min=1)
r("dp.freeboard", 201, "7.2.6.2 (e) Freeboard", "a minimum of 0.3 m above the water surface", DP, "outlet", "freeboard_m",
  "m", min=0.3, condition="embankment top above the water level with the spillway at maximum design flow",
  severity="requirement")
r("dp.dissipator", 201, "7.3.1 Primary Outlet and Downstream", "Where the head exceeds 1 m, a structure for dissipating energy",
  DP, "outlet", "energy_dissipator_head_m", "m", value=1.0, condition="above this head an energy dissipator is needed")

# ---------------------------------------------------------------- chapter 8: infiltration (sumps = recharge_well, trenches)
for el, k in ((RW, "rw"), (IT, "it")):
    r(f"{k}.min_rate", 237, "8.2.3 Site Suitability Limitations", "Saturated soil infiltration rate should be a minimum rate of 13mm/hr",
      el, "siting", "native_infiltration_rate_mm_hr", "mm/hr", min=13, severity="requirement")
    r(f"{k}.clay", 237, "8.2.3 Site Suitability Limitations", "Soils with 30% or greater clay content", el, "siting",
      "native_clay_content_pct", "%", max=30, condition="or 40 % or more silt plus clay: not to be used", severity="requirement")
    r(f"{k}.drain", 237, "8.2.3 Site Suitability Limitations", "drain the water quality design storm in 48", el, "storage",
      "drawdown_time_hr", "hr", max=48, condition="aerobic conditions")
    r(f"{k}.gw", 237, "8.2.3 Site Suitability Limitations", "at least 1.5m above the seasonal high ground water level",
      el, "siting", "groundwater_separation_m", "m", min=1.5, condition="also above bedrock or a clay lens", severity="requirement")
    r(f"{k}.fill", 237, "8.2.3 Site Suitability Limitations", "Infiltration systems should not utilise fill material", el,
      "siting", "fill_soils", "text", text="Not on or in fill soils.", severity="requirement")
    r(f"{k}.drinking", 237, "8.2.3 Site Suitability Limitations", "should not be allowed in well-field areas", el, "siting",
      "drinking_water_wells", "text", text="Not in well-fields or near drinking water wells or springs.", severity="requirement")
    r(f"{k}.structure", 237, "8.2.3 Site Suitability Limitations", "located at a minimum of 3m from any structure", el,
      "siting", "building_setback_m", "m", min=3, condition="on-site sumps and trenches", severity="requirement")
    r(f"{k}.septic", 237, "8.2.3 Site Suitability Limitations", "10m from a non-potable water supply well", el, "siting",
      "well_septic_setback_m", "m", min=10, condition="non-potable well, septic tank or drain field", severity="requirement")
    r(f"{k}.slope", 237, "8.2.3 Site Suitability Limitations", "located on slopes up to 15%", el, "siting",
      "natural_slope_pct", "%", max=15, condition="base of the facility below 3 %")
    r(f"{k}.fd", 238, "8.2.4 Design Criteria", "should be one-half the infiltration rate", el, "storage",
      "design_infiltration_factor", "fraction", value=0.5, condition="design rate = half the rate from soil texture",
      severity="requirement")
    r(f"{k}.porosity", 239, "8.2.4 Design Criteria", "with void space (i.e., porosity) in the range of 30 to 40%", el,
      "storage", "fill_porosity", "%", min=30, max=40)
r("ib.building", 237, "8.2.3 Site Suitability Limitations", "at least 7m down-slope and 50m up-slope from building foundations",
  IT, "siting", "building_setback_m", "m", min=7, condition="infiltration basins: 7 m down-slope, 50 m up-slope")
r("it.soil_log", 238, "8.2.4 Design Criteria", "a minimum of 3.0m below the bottom of the facility", IT, "siting",
  "soil_log_depth_below_base_m", "m", min=3.0, severity="requirement")
r("it.wqv", 238, "8.2.4 Design Criteria", "(WQV) of 40mm over the equivalent impervious contributing", IT, "storage",
  "water_quality_runoff_depth", "mm", value=40)

# ---------------------------------------------------------------- chapter 11: water quality ponds (retention_pond) and wetlands
r("wq.dry_drain", 310, "11.2.1 Dry type", "the design volume) of 24 hours to 48 hours",
  DP, "storage", "drawdown_time_hr", "hr", min=24, max=48, condition="dry type water quality pond")
r("wp.drawdown_min", 311, "11.2.1 Wet type", "in no less than 12 hours", WP, "storage", "drawdown_time_hr", "hr", min=12,
  condition="surcharge water quality volume above the permanent pool")
r("wp.catchment_min", 311, "11.2.2.1 Drainage Area", "The minimum recommended catchment area is 2.5ha", WP, "siting",
  "contributing_area_m2", "ha", min=2.5, condition="commercial or industrial; 3.5 ha residential")
r("wp.slopes", 311, "11.2.2.2 Location and Site Suitability", "shall not be located on unstable slopes or slopes greater than 15%",
  WP, "siting", "natural_slope_pct", "%", max=15, severity="requirement")
r("wp.lw", 313, "11.2.3.1 Shape", "length-to-width ratio of a basin should be at least 2:1", WP, "geometry",
  "length_to_width", "ratio", min=2)
r("wp.wqv", 313, "11.2.3.2 Water Quality Volume", "runoff from a 40mm rainfall depth over the contributing catchment", WP,
  "storage", "water_quality_runoff_depth", "mm", value=40)
r("wp.sediment", 313, "11.2.3.2 Water Quality Volume", "about 80 to 90% sediment removal", WP, "performance",
  "tss_load_reduction_pct", "%", min=80, max=90, condition="12 h (wet) / 48 h (dry) drawdown", severity="information")
r("wp.safety", 313, "11.2.3.4 Safety", "depths over 1.0m whenever possible", WP, "safety", "max_ponding_depth_m", "m", max=1.0,
  condition="residential areas; otherwise fence unless a littoral zone buffers it", severity="requirement")
r("wl.area", 317, "11.3.2.2 Space Requirement", "no less than 1% of the contributing drainage area", WL, "siting",
  "area_fraction_of_drainage_area", "%", min=1)
r("wl.depth", 318, "11.3.3.1 Design Criteria", "A depth range of 0.3m to 1.2m", WL, "geometry", "max_ponding_depth_m", "m",
  min=0.3, max=1.2, severity="typical")
r("wl.hrt", 318, "11.3.3.1 Design Criteria", "a hydraulic residence time of at least 12 hours", WL, "storage",
  "hydraulic_retention_time_hr", "hr", min=12)

staging.save(SRC, rules)
print(len(rules), "rules")
