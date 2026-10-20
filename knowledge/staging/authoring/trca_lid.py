"""Staged rules from the STEP LID wiki (trca_lid), read page by page; every snippet is checked on its page."""
from spongepark.engine.knowledge import staging

SRC, ED, CL = "trca_lid", "web wiki, snapshot 2026-10-20", ["Dfa", "Dfb"]
B, BS, ES, DP, WL, RG = ("Bioretention.html", "Bioswales.html", "Enhanced_swales.html", "Dry_ponds.html",
                         "Wetlands.html", "Rain_gardens.html")
SZ = "Bioretention__Sizing_and_modeling.html"
rules = []


def r(rid, file, page, section, snippet, element, category, parameter, unit, **kw):
    rules.append(staging.StagedRule(id=f"{SRC}.{rid}", source=SRC, edition=ED, file=file, page=page, section=section,
                                    snippet=snippet, element=element, category=category, parameter=parameter,
                                    unit=unit, climate=CL, **kw))


# ---------------------------------------------------------------- bioretention (rain_garden)
r("rg.underdrain_below_rate", B, 5, "Native Soil", "For infiltration rates <15 mm/h an underdrain is recommended",
  "rain_garden", "siting", "native_infiltration_rate_needing_underdrain", "mm/hr", max=15,
  condition="below this native soil rate an underdrain is recommended")
r("rg.footprint_share", B, 7, "Available Space", "reserve approximately 10 to 20% of the contributing drainage area",
  "rain_garden", "siting", "footprint_fraction_of_drainage_area", "%", min=10, max=20, condition="conceptual design stage",
  severity="typical")
r("rg.ip_ratio_cd", B, 7, "Available Space", "range from 5:1 to 15:1 on low permeability soils",
  "rain_garden", "siting", "impervious_to_footprint_ratio", "ratio", min=5, max=15, condition="HSG C and D soils")
r("rg.ip_ratio_ab", B, 7, "Available Space", "10:1 to 20:1 on high permeability soils",
  "rain_garden", "siting", "impervious_to_footprint_ratio", "ratio", min=10, max=20, condition="HSG A and B soils")
r("rg.max_drainage_area", B, 7, "Available Space", "receives runoff from more than 0.8 Ha",
  "rain_garden", "siting", "contributing_area_m2", "ha", max=0.8, condition="distributed cells; trade-off with maintenance")
r("rg.min_width", B, 7, "Available Space", "cells should be no narrower than 0.6 m at any point",
  "rain_garden", "geometry", "min_width_m", "m", min=0.6)
r("rg.contributing_slope", B, 8, "Site Topography", "Contributing slopes should be 1 to 5%",
  "rain_garden", "siting", "contributing_slope_pct", "%", min=1, max=5)
r("rg.head_underdrain", B, 9, "Available Head", "elevation difference of 1 to 1.5 m is needed",
  "rain_garden", "siting", "available_head_m", "m", min=1.0, max=1.5,
  condition="with an underdrain: between the inlet and the downstream storm sewer inverts")
r("rg.groundwater_separation", B, 10, "Water Table", "Maintaining a separation of 1 m between the elevations",
  "rain_garden", "siting", "groundwater_separation_m", "m", min=1.0,
  condition="base of practice to seasonally high water table or top of bedrock; may vary with mounding analysis")
r("rg.hotspots", B, 11, "Pollution Hot Spot Runoff", "runoff from pollution hot spots should not be treated by bioretention",
  "rain_garden", "siting", "hotspot_runoff", "text", text="No full or partial infiltration designs for pollution hot-spot runoff; lined (filtration only) designs may be used.",
  severity="requirement")
r("rg.karst", B, 13, "Karst", "Infiltration designs are unsuitable in areas of known or implied karst",
  "rain_garden", "siting", "karst", "text", text="Infiltration designs are unsuitable on karst.", severity="requirement")
r("rg.building_setback", B, 15, "Setbacks From Buildings", "a setback of 4 m from the building foundations should be applied",
  "rain_garden", "siting", "building_setback_m", "m", min=4.0, condition="unlined; no setback needed with an impermeable liner")
r("rg.wellhead", B, 6, "Wellhead Protection", "should not be located within the 2 year time-of-travel",
  "rain_garden", "siting", "wellhead_protection", "text",
  text="Not within the 2-year time-of-travel wellhead protection area when receiving road or parking runoff.",
  severity="requirement")
r("rg.large_cell_area", B, 18, "Parkland and Natural Areas", "a larger bioretention (50 - 800 m 2 ) cell may be used",
  "rain_garden", "geometry", "area_m2", "m2", min=50, max=800, condition="end-of-pipe cell in parkland next to a water course",
  severity="typical")
r("rg.ip_ratio_sizing", B, 21, "Sizing and Modelling", "runoff from approximately 5 to 20 times the footprint area",
  "rain_garden", "siting", "impervious_to_footprint_ratio", "ratio", min=5, max=20)
r("rg.inlet_drop", B, 22, "Inlets", "Provide a 50 to 100 mm drop in elevation",
  "rain_garden", "inlet", "inlet_drop_m", "mm", min=50, max=100, condition="between inlet invert and mulch or apron surface")
r("rg.forebay_volume", B, 23, "Pretreatment", "ponding volume of 25% of the surface ponding storage requirement",
  "rain_garden", "pretreatment", "forebay_volume_fraction", "%", value=25, condition="forebay with concentrated overland inflow")
r("rg.forebay_lw", B, 23, "Pretreatment", "Constructed with 2:1 length to width ratio",
  "rain_garden", "pretreatment", "forebay_length_to_width", "ratio", value=2)
r("rg.filter_strip_length", B, 23, "Pretreatment", "Min. flow path length of 3 m, with 5 m preferred",
  "filter_strip", "geometry", "flow_path_length_m", "m", min=3, value=5, condition="as pretreatment to bioretention; 5 m preferred")
r("rg.filter_strip_slope", B, 23, "Pretreatment", "slope between 1 and 3%",
  "filter_strip", "geometry", "slope_pct", "%", min=1, max=3, condition="as pretreatment to bioretention")
r("rg.ponding_depth", B, 26, "Overflow Elevation", "A good starting point is 150 to 350 mm above",
  "rain_garden", "geometry", "max_ponding_depth_m", "mm", min=150, max=350, condition="overflow invert above the mulch surface")
r("rg.drawdown", B, 26, "Overflow Elevation", "must drain within 48 hours",
  "rain_garden", "storage", "drawdown_time_hr", "hr", max=48, condition="no underdrain: ponded water into the native soil",
  severity="requirement")
r("rg.freeboard", B, 27, "Freeboard", "150 mm will usually suffice",
  "rain_garden", "outlet", "freeboard_m", "mm", value=150, condition="inlet invert to overflow invert")
r("bs.freeboard", BS, 12, "Freeboard", "a freeboard of 300 mm is generally accepted",
  "bioswale", "outlet", "freeboard_m", "mm", value=300, condition="swales conveying flowing water")
r("rg.media_depth", B, 30, "Filter Media Bed", "Recommended filter media bed depth is 0.5 to 1.0 m",
  "rain_garden", "media", "soil_media_depth_m", "m", min=0.5, max=1.0)
r("rg.media_depth_constrained", B, 30, "Filter Media Bed", "beds as shallow as 0.3 m",
  "rain_garden", "media", "soil_media_depth_m", "m", min=0.3, condition="constrained applications", severity="information")
r("rg.media_depth_shrubs", B, 30, "Filter Media Bed", "0.6 m to support shrubs and 1.0 metre to support trees",
  "rain_garden", "media", "soil_media_depth_m", "m", min=0.6, condition="0.3 m grasses and perennials, 0.6 m shrubs, 1.0 m trees")
r("rg.bed_side_slope", B, 30, "Filter Media Bed", "maximum side slopes of 1:3 or 33%",
  "rain_garden", "geometry", "side_slope_h_v", "H:V", min=3, condition="filter bed installed level; 1:3 (V:H) steepest")
r("rg.mulch", B, 30, "Filter Media Bed", "Maintaining a 75 to 100 mm layer of double shredded wood mulch",
  "rain_garden", "media", "mulch_depth_m", "mm", min=75, max=100)
r("rg.media_blend_a", B, 30, "Filter Media Bed", "Consists of 3 parts sand to 1 part organic material/additives",
  "rain_garden", "media", "media_mix", "text", text="Blend A: 3 sand : 1 organic (drainage priority, I:P >= 15).")
r("rg.media_p", B, 43, "Water Quality", "kept between 12 to 40 ppm",
  "rain_garden", "media", "media_plant_available_p_ppm", "ppm", min=12, max=40, condition="to avoid phosphorus export")
r("rg.underdrain_diameter", B, 32, "Underdrain", "pipe with diameter ≥ 200 mm",
  "rain_garden", "outlet", "underdrain_diameter_m", "mm", min=200)
r("rg.choker", B, 33, "Choker Layer", "A minimum 100 mm deep layer of clean 5 to 20 mm",
  "rain_garden", "media", "choker_layer_depth_m", "mm", min=100)
r("rg.reservoir_depth", B, 34, "Storage Reservoir", "Should be a minimum of 300 mm deep",
  "rain_garden", "storage", "storage_layer_depth_m", "mm", min=300)
r("rg.plant_spacing", B, 36, "Plants", "planted 0.5 m on center, and no more than 0.6 m",
  "rain_garden", "planting", "plant_spacing_m", "m", value=0.5, max=0.6, condition="perennial forbs and grasses")
r("rg.species", B, 37, "Plant Selection", "A variety (min. five) species should be used",
  "rain_garden", "planting", "species_count", "count", min=5)
r("rg.construction_offset", B, 38, "Construction", "only be excavated to 75 cm above the final post-construction base",
  "rain_garden", "construction", "excavation_offset_m", "cm", value=75,
  condition="when the cell is used as a temporary sediment basin during construction")
r("rg.inspection", B, 39, "Inspection and Maintenance", "Inspections should occur twice annually (spring and late fall)",
  "rain_garden", "maintenance", "inspection_frequency", "times/yr", value=2, condition="and after major storms")
r("rg.vegetation_cover", B, 39, "Inspection and Maintenance", "vegetation density (≥ 80% coverage)",
  "rain_garden", "maintenance", "vegetation_cover_pct", "%", min=80)
r("rg.camera", B, 39, "Inspection and Maintenance", "Camera inspection of these pipes should be conducted every 5 years",
  "rain_garden", "maintenance", "pipe_camera_inspection_interval", "yr", value=5)
r("rg.media_replace", B, 39, "Inspection and Maintenance", "every 5 to 10 years",
  "rain_garden", "maintenance", "inlet_media_replacement_interval", "yr", min=5, max=10,
  condition="top 5 cm of filter media around inlets")
r("rg.watering", B, 39, "Inspection and Maintenance", "Watering may be needed until plant establishment (first 2 years)",
  "rain_garden", "maintenance", "establishment_watering_period", "yr", value=2)
r("rg.rr_underdrain", B, 42, "Water Balance", "45% with underdrain | 30% with underdrain and liner",
  "rain_garden", "performance", "runoff_reduction_pct", "%", value=45,
  condition="estimate with underdrain (30 % with underdrain and liner)", severity="information")
r("rg.tss", B, 43, "Water Quality", "load reductions between 88 to 99%",
  "rain_garden", "performance", "tss_load_reduction_pct", "%", min=88, max=99, condition="9 unlined facilities, Ontario",
  severity="information")
r("rg.tp", B, 43, "Water Quality", "total phosphorus load reductions between 68 and 92%",
  "rain_garden", "performance", "tp_load_reduction_pct", "%", min=68, max=92, condition="unlined facilities, Ontario",
  severity="information")
r("rg.total_depth_max", SZ, 1, "(top)", "not usually > 2 m", "rain_garden", "geometry", "total_depth_m", "m", max=2.0,
  condition="limited by construction practice")
r("rg.total_depth_min", SZ, 1, "(top)", "not less than 0.6 m to support deep rooting perennials",
  "rain_garden", "geometry", "total_depth_m", "m", min=0.6)
r("rg.ip_max", SZ, 1, "(top)", "(or I/P ratio ) of 20", "rain_garden", "siting", "impervious_to_footprint_ratio",
  "ratio", max=20, severity="requirement")
r("rg.depression", RG, 4, "Planning Considerations", "a surface depression of approximately 150 mm",
  "rain_garden", "geometry", "max_ponding_depth_m", "mm", value=150, condition="residential rain garden", severity="typical")

# ---------------------------------------------------------------- swales (bioswale / vegetated_swale)
r("es.space", ES, 9, "Available Space", "Reserve open space of about 5 to 20% of the size",
  "vegetated_swale", "siting", "footprint_fraction_of_drainage_area", "%", min=5, max=20)
r("es.width", ES, 9, "Available Space", "A width of at least 2 metres is needed",
  "vegetated_swale", "geometry", "min_width_m", "m", min=2.0)
r("es.long_slope", ES, 10, "Site Topography", "Swale longitudinal slopes may range from 0.5 to 6%",
  "vegetated_swale", "geometry", "longitudinal_slope_pct", "%", min=0.5, max=6)
r("es.check_dams_above", ES, 10, "Site Topography", "On slopes steeper than 3%, check dams should be used",
  "vegetated_swale", "geometry", "longitudinal_slope_needing_check_dams_pct", "%", min=3)
r("es.gw", ES, 11, "Water Table", "Maintaining a separation of 1 m between the elevations of the base",
  "vegetated_swale", "siting", "groundwater_separation_m", "m", min=1.0)
r("es.setback", ES, 15, "Setback from Buildings", "Should be set back a minimum of 4m from building foundations",
  "vegetated_swale", "siting", "building_setback_m", "m", min=4.0)
r("es.drainage_area", ES, 16, "Design", "Treat drainage areas of < 2 hectares",
  "vegetated_swale", "siting", "contributing_area_m2", "ha", max=2.0, severity="requirement")
r("es.residence", ES, 16, "Design", "Minimum residence time of 5 minutes",
  "vegetated_swale", "geometry", "residence_time", "min", min=5, severity="requirement")
r("es.velocity", ES, 16, "Design", "Maximum flow velocity 0.3 m/s",
  "vegetated_swale", "geometry", "peak_velocity_m_s", "m/s", max=0.3, severity="requirement")
r("es.bottom_width", ES, 16, "Design", "Bottom width between 0.75 - 3.0 m",
  "vegetated_swale", "geometry", "bottom_width_m", "m", min=0.75, max=3.0, severity="requirement")
r("es.length", ES, 16, "Design", "Minimum length 30 m", "vegetated_swale", "geometry", "length_m", "m", min=30,
  severity="requirement")
r("es.flow_depth", ES, 16, "Design", "to a maximum of 100 mm", "vegetated_swale", "geometry", "max_flow_depth_m", "mm",
  max=100, condition="regularly mown swales: 50 % of grass height, at most 100 mm")
r("es.ip", ES, 17, "Geometry and Site Layout", "5:1 on low permeability soils", "vegetated_swale", "siting",
  "impervious_to_footprint_ratio", "ratio", value=5, condition="HSG C and D (20:1 on HSG A and B)")
r("es.check_dam_height", ES, 32, "Check dams", "may be up to 0.6 m in height", "check_dam", "geometry", "dam_height_m", "m",
  max=0.6, condition="enhanced swales; ponded depth <= 0.6 m")
r("es.check_dam_spacing", ES, 32, "Check dams", "are usually installed between 10 - 20 m along the swale",
  "check_dam", "geometry", "check_dam_spacing_m", "m", min=10, max=20, severity="typical")
r("es.check_dam_stone", ES, 32, "Check dams", "minimum median diameter 25 - 75 mm", "check_dam", "construction",
  "stone_median_diameter_m", "mm", min=25, max=75)
r("es.compensation", ES, 33, "Sizing and spacing of check dams", "The compensation gradient of enhanced swales must be < 1 %",
  "check_dam", "geometry", "effective_slope_pct", "%", max=1.0, value=0.5, condition="0.5 % preferred", severity="requirement")
r("es.ponding_time", ES, 33, "Sizing and spacing of check dams", "infiltrate in a specified period (often 48 - 72 hours)",
  "check_dam", "storage", "drawdown_time_hr", "hr", min=48, max=72, severity="typical")
r("es.grass_height", ES, 25, "Planting Considerations", "allowed to grow between 75 to 150 mm",
  "vegetated_swale", "planting", "grass_height_m", "mm", min=75, max=150)
r("es.side_slope", ES, 28, "Modeling", "Suggested value of 3 or 4 if design permits",
  "vegetated_swale", "geometry", "side_slope_h_v", "H:V", min=3, max=4, severity="typical")
r("es.manning", ES, 28, "Modeling", "0.03 – 0.06", "vegetated_swale", "geometry", "manning_n", "-", min=0.03, max=0.06,
  condition="mown grass, depending on density", severity="typical")
r("es.rr", ES, 36, "Water Balance", "runoff reduction rate of 45 to 10%", "vegetated_swale", "performance",
  "runoff_reduction_pct", "%", min=10, max=45, condition="45 % on HSG A/B, 10 % on HSG C/D", severity="information")
r("es.tss", ES, 37, "Water Quality", "76% for total suspended solids", "vegetated_swale", "performance",
  "tss_load_reduction_pct", "%", value=76, condition="median of performance studies", severity="information")
r("bs.rr", BS, 18, "Performance", "Runoff Reduction Estimate* 45% with underdrain", "bioswale", "performance",
  "runoff_reduction_pct", "%", value=45, condition="estimate with underdrain", severity="information")
r("bs.inspection", BS, 14, "Inspection and Maintenance", "Inspections should occur twice annually (spring and late fall)",
  "bioswale", "maintenance", "inspection_frequency", "times/yr", value=2)

# ---------------------------------------------------------------- dry ponds (detention_basin), MOE (2003) table
r("dp.drainage", DP, 10, "Design", "≥10 Ha preferred", "detention_basin", "siting", "contributing_area_m2", "ha", min=5, value=10,
  condition="5 ha minimum (orifice size), 10 ha or more preferred")
r("dp.detention", DP, 12, "Detention time", "A minimum detention time of 24 hours should be targeted",
  "detention_basin", "storage", "detention_time_hr", "hr", min=24, value=48, condition="48 h preferred for water quality",
  severity="requirement")
r("dp.forebay_depth", DP, 10, "Design", "Minimum depth: 1 m (1.5 m preferred)", "detention_basin", "pretreatment",
  "forebay_depth_m", "m", min=1.0, value=1.5)
r("dp.forebay_area", DP, 10, "Design", "Maximum Area: 20% (preferred) to 33% of total permanent pool",
  "detention_basin", "pretreatment", "forebay_area_fraction", "%", max=33, value=20)
r("dp.lw", DP, 10, "Design", "Overall: minimum 3:1", "detention_basin", "geometry", "length_to_width", "ratio", min=3, value=4,
  condition="4:1 preferred")
r("dp.depth", DP, 10, "Design", "Maximum 3 m", "detention_basin", "safety", "max_ponding_depth_m", "m", max=3.0,
  severity="requirement")
r("dp.side_slope", DP, 10, "Design", "4:1 average", "detention_basin", "safety", "side_slope_h_v", "H:V", value=4, min=3,
  condition="average 4:1; no steeper than 3:1 except where under 0.5 m deep", severity="requirement")
r("dp.inlet_pipe", DP, 10, "Design", "Minimum 450 mm diameter inlet pipe", "detention_basin", "inlet", "inlet_pipe_diameter_m",
  "mm", min=450)
r("dp.outlet_pipe", DP, 10, "Design", "Minimum: 450 mm diameter outlet pipe", "detention_basin", "outlet",
  "outlet_pipe_diameter_m", "mm", min=450)
r("dp.orifice", DP, 10, "Design", "If orifice control used, 75 mm diameter minimum", "detention_basin", "outlet",
  "outlet_diameter_m", "mm", min=75, value=100, condition="100 mm preferable", severity="requirement")
r("dp.pipe_slope", DP, 10, "Design", "Preferred pipe slope: > 1 %", "detention_basin", "inlet", "pipe_slope_pct", "%", min=1)
r("dp.buffer", DP, 19, "Buffer", "A minimum of a 3 m buffer strip", "detention_basin", "safety", "buffer_width_m", "m", min=3,
  condition="from the maximum design water level")
r("dp.buffer_species", DP, 19, "Buffer", "at least least 5 species should be planted", "detention_basin", "planting",
  "species_count", "count", min=5)
r("dp.planted_depth", DP, 20, "Planting Strategy", "maximum storage depths may be reduced to 1 to 1.5 metres",
  "detention_basin", "planting", "max_ponding_depth_m", "m", min=1.0, max=1.5, condition="depending on the planting strategy",
  severity="information")
r("dp.storage_35", DP, 21, "Performance", "35% 90 50", "detention_basin", "storage", "storage_volume_per_area", "m3/ha", value=90,
  condition="35 % impervious catchment, basic protection (150 / 200 / 240 m3/ha at 55 / 70 / 85 %)", severity="typical")
r("dp.tss", DP, 21, "Performance", "basic treatment level of 60% long-term TSS removal", "detention_basin", "performance",
  "tss_load_reduction_pct", "%", value=60, condition="dry ponds alone", severity="information")
r("dp.cleanout", DP, 24, "Forecasting Sediment Accumulation and Cleanouts", "declines below 5% of its original design criterion",
  "detention_basin", "maintenance", "sediment_removal_trigger_pct", "%", value=5,
  condition="clean when TSS removal falls 5 percentage points below design")

# ---------------------------------------------------------------- wetlands and wet ponds (retention_pond / constructed_wetland)
r("wl.pond_vs_wetland", WL, 3, "Planning considerations", "shallow zones (<0.5 m deep) comprise less than 20% of its surface area",
  "retention_pond", "geometry", "shallow_zone_fraction", "%", max=20,
  condition="a wet pond; a wetland has shallow zones (<0.5 m) over 70 % of its volume", severity="information")
r("wl.pp_depth", WL, 4, "Sizing free-water", "should range from 150 mm to 300 mm", "constructed_wetland", "geometry",
  "permanent_pool_depth_m", "mm", min=150, max=300)
r("wl.active_depth", WL, 4, "Sizing free-water", "Maximum 1.0 m for storms < 10 year event", "constructed_wetland", "storage",
  "max_ponding_depth_m", "m", max=1.0, condition="storms under the 10-year event", severity="requirement")
r("wl.side_slope", WL, 4, "Sizing free-water", "5:1 For 3 m above and below permanent pool", "constructed_wetland", "safety",
  "side_slope_h_v", "H:V", value=5, condition="5:1 within 3 m of the permanent pool, at most 3:1 elsewhere", severity="requirement")
r("wl.buffer", WL, 4, "Sizing free-water", "Minimum 7.5 m above maximum water quality/ erosion control water level",
  "constructed_wetland", "safety", "buffer_width_m", "m", min=7.5)
r("wl.storage", WL, 4, "Sizing free-water", "the recommended storage volume for wet ponds is 60 - 250 m 3 /ha",
  "retention_pond", "storage", "storage_volume_per_area", "m3/ha", min=60, max=250, severity="typical")
r("wl.forebay", WL, 4, "Sizing free-water", "Maximum area: 20 % of total permanent pool", "constructed_wetland", "pretreatment",
  "forebay_area_fraction", "%", max=20)

# ---------------------------------------------------------------- soakaways, trenches and chambers (recharge_well, infiltration_trench)
IC, IT = "Infiltration_chambers.html", "Infiltration_trenches.html"
for el, f in (("recharge_well", IC), ("infiltration_trench", IT)):
    k = "rw" if el == "recharge_well" else "it"
    pg = {"slope": 9, "gw": 10, "hot": 11, "karst": 13, "setback": 14}
    r(f"{k}.natural_slope", f, pg["slope"], "Site Topography", "cannot be located on natural slopes greater than 15%",
      el, "siting", "natural_slope_pct", "%", max=15, severity="requirement")
    r(f"{k}.gw", f, pg["gw"], "Water Table", "Maintaining a separation of one (1) metre between the elevations",
      el, "siting", "groundwater_separation_m", "m", min=1.0, condition="base to seasonally high water table or bedrock")
    r(f"{k}.hotspots", f, pg["hot"], "Pollution Hot Spot Runoff",
      "runoff from pollution hot spots should not be treated by infiltration trenches", el, "siting", "hotspot_runoff", "text",
      text="Not for pollution hot-spot runoff.", severity="requirement")
    r(f"{k}.karst", f, pg["karst"], "Karst", "chambers and soakaways are not suitable in areas of known", el, "siting", "karst",
      "text", text="Not on karst.", severity="requirement")
    r(f"{k}.setback", f, pg["setback"], "Setback from Buildings", "setback a minimum of four (4) metres from building foundations",
      el, "siting", "building_setback_m", "m", min=4.0)
r("rw.ip", IC, 5, "Geometry and Site Layout", "between 5:1 on low permeability soils (HSG C & D)", "recharge_well", "siting",
  "impervious_to_footprint_ratio", "ratio", min=5, max=20, condition="5:1 on HSG C & D to 20:1 on HSG A & B")
r("rw.depth", IC, 5, "Geometry and Site Layout", "Not typically deeper than 4 m", "recharge_well", "geometry", "well_depth_m",
  "m", max=4.0, condition="chambers and soakaways", severity="typical")
r("rw.cover", IC, 3, "Planning Considerations", "a minimum of 20 cm cover is recommended for most applications",
  "recharge_well", "construction", "min_cover_m", "cm", min=20)
r("rw.porosity", IC, 17, "Storage Reservoir", "crushed angular stone (max. wash loss of 0.5%) with a porosity of 0.4",
  "recharge_well", "storage", "fill_porosity", "fraction", value=0.4)
r("rw.drainage", IC, 31, "Inspection and Maintenance", "drains within the required drainage time (typically 72 hours)",
  "recharge_well", "storage", "drawdown_time_hr", "hr", max=72, severity="typical")
r("rw.inspection", IC, 31, "Inspection and Maintenance", "twice a year in the spring and/or late fall",
  "recharge_well", "maintenance", "inspection_frequency", "times/yr", value=2, condition="pretreatment, inlets and outlets")
r("rw.shoring", IC, 29, "Excavation", "If >2.0 m in depth, trench shorings will be required", "recharge_well", "construction",
  "shoring_depth_m", "m", value=2.0, condition="excavations deeper than this need shoring", severity="requirement")
r("rw.pretreat_drop", IT, 18, "Pre-Treatment", "Provide a 75 to 150 mm elevation drop between the inlet invert",
  "infiltration_trench", "pretreatment", "inlet_drop_m", "mm", min=75, max=150, condition="grass swale pretreatment")
r("it.depth", IT, 15, "Sizing", "not normally deeper than 3 to 4 m", "infiltration_trench", "geometry", "total_depth_m", "m",
  max=4.0, min=3.0, condition="to keep the unsaturated flow path to the water table", severity="typical")
r("it.ip", IT, 16, "Geometry and Site Layout", "5:1 to 20:1", "infiltration_trench", "siting", "impervious_to_footprint_ratio",
  "ratio", min=5, max=20)
r("it.drainage", IT, 33, "Inspection and Maintenance", "maximum acceptable length of time (typically 72 hours)",
  "infiltration_trench", "storage", "drawdown_time_hr", "hr", max=72)
r("it.monitor_storm", IT, 33, "Inspection and Maintenance", "following every major storm event (>25 mm)",
  "infiltration_trench", "maintenance", "inspection_storm_depth", "mm", value=25)
r("it.recheck", IT, 33, "Inspection and Maintenance", "every 15 years at a minimum", "infiltration_trench", "maintenance",
  "drainage_test_interval", "yr", max=15)

staging.save(SRC, rules)
print(len(rules), "rules")
