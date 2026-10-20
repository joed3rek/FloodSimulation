"""Staged rules from the Habitat Collective NbS design guidelines (fact sheets 4.1-4.12, draft D2, Aug 2026).
The user's own team's guidelines (supplied 2026-10-20). Element sheets are added section by section."""
from spongepark.engine.knowledge import staging

SRC, ED, CL = "hc_guidelines", "Draft D2, August 2026", ["Aw"]
rules = []


def r(rid, file, page, section, snippet, element, category, parameter, unit, **kw):
    climate = kw.pop("climate", CL)   # a sheet quoting another city's standard keeps that city's climate
    rules.append(staging.StagedRule(id=f"{SRC}.{rid}", source=SRC, edition=ED, file=file, page=page, section=section,
                                    snippet=snippet, element=element, category=category, parameter=parameter,
                                    unit=unit, climate=climate, **kw))


# ---------------------------------------------------------------- 4.5 percolation well (recharge_well)
W, RW = "4.5_Percolation Well_D2.pdf", "recharge_well"
r("rw.cost", W, 3, "4.5.1 Facts and Figures", "₹1 - 3 Lakhs (full system)", RW, "cost", "capex", "text",
  text="Capex INR 1-3 lakh per full system; annual opex INR 6,000-8,000 per unit.", severity="information")
r("rw.size", W, 3, "4.5.1 Facts and Figures", "0.9 - 3m x 6 - 9m", RW, "geometry", "well_diameter_m", "m", min=0.9, max=3.0,
  condition="per unit, diameter x depth 6-9 m", severity="typical")
r("rw.perc_rate", W, 8, "4.5.4 Calculations", "≥15 to 25 mm/hr", RW, "siting", "native_infiltration_rate_mm_hr", "mm/hr",
  min=15, max=25, condition="minimum field percolation rate", severity="requirement")
r("rw.safety_factor", W, 8, "4.5.4 Calculations", "Design Safety Factor 2.0 to 2.5", RW, "storage",
  "infiltration_safety_factor", "ratio", min=2.0, max=2.5)
r("rw.drawdown", W, 8, "4.5.4 Calculations", "Max Drawdown Time 48 to 72 hours", RW, "storage", "drawdown_time_hr", "hr",
  min=48, max=72)
r("rw.porosity", W, 8, "4.5.4 Calculations", "Porosity of gravel packing (0.32 - 0.40)", RW, "storage", "fill_porosity",
  "fraction", min=0.32, max=0.40)
r("rw.casing", W, 8, "4.5.4 Calculations", "150 mm to 300 mm (typical casing)", RW, "geometry", "casing_diameter_m", "mm",
  min=150, max=300, condition="outer rings 600-1200 mm", severity="typical")
r("rw.depth_shallow", W, 8, "4.5.4 Calculations", "3.0m to 6.0 m (Shallow/ Medium)", RW, "geometry", "well_depth_m", "m",
  min=3.0, max=6.0, condition="shallow/medium wells; deep injection 30-60 m", severity="typical")
r("rw.silt_trap", W, 8, "4.5.4 Calculations", "Minimum 10% of total storm capture volume", RW, "pretreatment",
  "silt_trap_volume_fraction", "%", min=10, severity="requirement")
r("rw.gw", W, 9, "4.5.4 Constraints & Clearances", "Min. 1.0 m to 1.5 m above SHWT", RW, "siting",
  "groundwater_separation_m", "m", min=1.0, max=1.5, condition="above the seasonal high water table", severity="requirement")
r("rw.building", W, 9, "4.5.4 Constraints & Clearances", "Min. 3.0 m (10 ft) from building foundations", RW, "siting",
  "building_setback_m", "m", min=3.0, severity="requirement")
r("rw.bedrock", W, 9, "4.5.4 Constraints & Clearances", "Stop excavation ≥ 1.2 m above solid bedrock", RW, "siting",
  "bedrock_separation_m", "m", min=1.2, severity="requirement")
r("rw.wt_depth", W, 10, "4.5.5-01 Site Criteria", "table depth ≥ 3 m bgl", RW, "siting", "min_depth_to_water_table_m", "m",
  min=3.0, condition="not suitable where the water table is shallower (waterlogging) or in homogeneous clay",
  severity="requirement")
r("rw.wt_max", W, 10, "4.5.5-01 Site Criteria", "ideally suited for water table depths up to 15 m bgl", RW, "siting",
  "depth_to_water_table_m", "m", max=15, condition="recharge shafts in India", severity="typical")
r("rw.roof", W, 10, "4.5.5-01 Site Criteria", "Single well: 100–1,000 m² of roof area typical", RW, "siting",
  "contributing_area_m2", "m2", min=100, max=1000, condition="per well, rooftop catchment", severity="typical")
r("rw.first_flush", W, 10, "4.5.5-01 Site Criteria", "A first-flush bypass is mandatory", RW, "pretreatment",
  "first_flush_bypass", "text", text="First-flush bypass before connecting a roof to the well.", severity="requirement")
r("rw.spacing", W, 10, "4.5.5-01 Site Criteria", "series or parallel at 3–5 m spacing", RW, "geometry", "well_spacing_m", "m",
  min=3, max=5, condition="multiple wells for large impervious areas (CGWB)")
r("rw.wall", W, 10, "4.5.5-01 Site Criteria", "≥1 m from compound wall", RW, "siting", "wall_setback_m", "m", min=1.0,
  severity="requirement")
r("rw.borewell", W, 10, "4.5.5-01 Site Criteria", "≥ 30 m from existing bore wells or tubewells", RW, "siting",
  "borewell_setback_m", "m", min=30, severity="requirement")
r("rw.quality", W, 10, "4.5.5-01 Site Criteria", "already exceeds permissible limits under BIS IS 10500", RW, "siting",
  "groundwater_quality", "text", severity="requirement",
  text="No recharge well where groundwater already exceeds IS 10500 limits; test over fluoride-affected aquifers.")
r("rw.diameter", W, 12, "4.5.5-02 Well Geometry", "Recharge well: 0.9 - 1.5 m", RW, "geometry", "well_diameter_m", "m",
  min=0.9, max=1.5, condition="recharge shafts over 2 m; dry wells 0.9-1.8 m")
r("rw.rate", W, 12, "4.5.5-02 Well Geometry", "recharge rate with inverted filter ranges 7–14 litres per second",
  RW, "performance", "recharge_rate", "l/s", min=7, max=14, condition="2-3 m diameter shaft (CGWB field data)",
  severity="information")
r("rw.depth", W, 12, "4.5.5-02 Well Geometry", "Percolation Well: 6 - 9m", RW, "geometry", "well_depth_m", "m", min=6, max=9,
  condition="recharge shafts up to 8 m")
r("rw.no_wt", W, 12, "4.5.5-02 Well Geometry", "it should NOT touch the water table", RW, "geometry", "well_depth_rule", "text",
  text="End in the permeable stratum; do not touch the water table (mounding, backflow).", severity="requirement")
r("rw.deep_noc", W, 12, "4.5.5-02 Well Geometry", "depths beyond 15 m require a hydrogeological assessment", RW,
  "siting", "deep_well_assessment_depth_m", "m", value=15,
  condition="deeper wells need a hydrogeological assessment and a CGWA NOC in notified areas", severity="requirement")
r("rw.filter", W, 14, "4.5.5-03 Inverted Filter", "each layer 300–600 mm thick", RW, "media", "filter_layer_depth_m", "mm",
  min=300, max=600, condition="boulders 50-200 mm, gravel 5-50 mm, coarse sand 1.5-2 mm (coarsest at the bottom)")
r("rw.no_fine_sand", W, 14, "4.5.5-03 Inverted Filter", "Do NOT use uniform fine sand throughout", RW, "media", "media_mix",
  "text", text="No uniform fine sand fill: it clogs irreversibly.", severity="requirement")
r("rw.void", W, 14, "4.5.5-03 Inverted Filter", "Leave a minimum 300 mm void space at the top", RW, "geometry",
  "top_void_m", "mm", min=300, condition="below the RCC cover slab, for inspection")
r("rw.clean_sand", W, 14, "4.5.5-03 Inverted Filter", "cleaned before every monsoon season", RW, "maintenance",
  "top_sand_cleaning_interval", "yr", value=1, condition="top sandy (morang) layer, pre-monsoon", severity="requirement")
r("rw.slab", W, 16, "4.5.5-05 Cover & Safety", "M20 RCC cover slab with 150 mm minimum thickness", RW, "safety",
  "cover_slab_thickness_m", "mm", min=150, condition="flush or at most 50 mm above ground", severity="requirement")
r("rw.opening", W, 16, "4.5.5-05 Cover & Safety", "minimum 1 inspection opening 450 mm dia", RW, "maintenance",
  "inspection_opening_diameter_m", "mm", min=450, condition="lockable lid; 1 mm anti-mosquito mesh")
r("rw.load", W, 16, "4.5.5-05 Cover & Safety", "Minimum imposed load of 10 kN/m²", RW, "safety", "cover_design_load", "text",
  text="Design the cover for at least 10 kN/m2, vehicular where cars can reach it.", severity="requirement")
r("rw.inlet", W, 16, "4.5.5-05 Inlet Pipe", "min. 100 mm dia from desilting chamber to shaft", RW, "inlet",
  "inlet_pipe_diameter_m", "mm", min=100, condition="75 mm from downpipe to desilting chamber")
r("rw.screen", W, 16, "4.5.5-05 Inlet Pipe", "Wire mesh screen (2–3 mm aperture)", RW, "pretreatment", "screen_aperture_m",
  "mm", min=2, max=3, condition="every downpipe junction and the desilting chamber inlet")
r("rw.desilt", W, 17, "4.5.6 Maintenance Schedule", "Highest - 3 years;", RW, "maintenance", "desilting_interval", "yr",
  min=3, max=7, condition="depending on pre-filtration; 10 years with pre-filters and no ground runoff")
r("rw.ponding", W, 18, "4.5.7 Hydrological Assessment", "ponding cleared within 3-3.5 hours post-rainfall", RW, "performance",
  "surface_ponding_clearance_hr", "hr", min=3, max=3.5, severity="information")
r("rw.tss", W, 18, "4.5.7 Hydrological Assessment", "90-95% TSS removal", RW, "performance", "tss_load_reduction_pct", "%",
  min=90, max=95, severity="information")

# ---------------------------------------------------------------- 4.2 rain garden (sidewalk rain gardens after NYC DEP)
G, RG, NYC = "4.2_Rain Garden_D2.pdf", "rain_garden", ["Cfa"]
r("rg.cost", G, 3, "4.2.1 Facts and Figures", "₹3,860 (full system)", RG, "cost", "capex", "text",
  text="Capex about INR 3,860 per 1.2 x 1.2 m unit; annual opex about INR 200.", severity="information")
r("rg.plan", G, 12, "4.2.4 Calculations", "Length 10–20 ft (3–6 m)", RG, "geometry", "length_m", "m", min=3, max=6,
  condition="sidewalk cells, width 1.2-1.8 m", climate=NYC, severity="typical")
r("rg.catchment", G, 12, "4.2.4 Calculations", "200–600 ft² (18–56 m²) per cell", RG, "siting", "contributing_area_m2", "m2",
  min=18, max=56, condition="sidewalk cell", climate=NYC, severity="typical")
r("rg.ponding", G, 12, "4.2.4 Calculations", "Ponding depth 75–150 mm (3–6 in)", RG, "geometry", "max_ponding_depth_m", "mm",
  min=75, max=150, condition="sidewalk cells (park rain gardens 150-300 mm)", climate=NYC)
r("rg.long_slope", G, 12, "4.2.4 Calculations", "Ideally 0–2%; use check dams if >2%", RG, "geometry",
  "longitudinal_slope_pct", "%", min=0, max=2, climate=NYC)
r("rg.inlet", G, 12, "4.2.4 Calculations", "Min. 18 in (450 mm) wide drop curb inlet", RG, "inlet", "inlet_width_m", "mm",
  min=450, condition="outlet 250 mm", climate=NYC)
r("rg.drawdown", G, 12, "4.2.4 Calculations", "Full drawdown within 48 hrs", RG, "storage", "drawdown_time_hr", "hr", max=48,
  value=36, condition="24-48 h preferred; mosquito control", severity="requirement")
r("rg.media_rate", G, 12, "4.2.4 Calculations", ">13 mm/hr minimum; ideal 25–50 mm/hr", RG, "media",
  "media_infiltration_rate_mm_hr", "mm/hr", min=13, max=50, condition="25-50 mm/hr after amendment is ideal",
  severity="requirement")
r("rg.gw", G, 12, "4.2.4 Calculations", "Min. 600 mm (2 ft) from seasonal high groundwater", RG, "siting",
  "groundwater_separation_m", "mm", min=600, condition="to the base of the stone layer", climate=NYC, severity="requirement")
r("rg.soil_depth", G, 12, "4.2.4 Calculations", "18 in (450 mm) without tree", RG, "media", "soil_media_depth_m", "mm",
  min=450, condition="600 mm with a tree", climate=NYC)
r("rg.soil_mix", G, 12, "4.2.4 Calculations", "85–88% sand, <5% clay, <5% silt", RG, "media", "media_mix", "text",
  text="Engineered soil: 85-88 % sand, <5 % clay, <5 % silt, 20-30 % compost by volume; no plain topsoil.")
r("rg.stone", G, 12, "4.2.4 Calculations", "tree); clean open-graded stone 20–50 mm; ~0.4 porosity", RG, "storage",
  "storage_layer_depth_m", "in", value=24, condition="24 in without a tree, 30 in with; stone 20-50 mm, porosity about 0.4",
  climate=NYC)
r("rg.outlet", G, 12, "4.2.4 Calculations", "Outlet drop curb set 3 in (75 mm) below low point", RG, "outlet",
  "outlet_drop_m", "mm", value=75, climate=NYC)
r("rg.cleanout", G, 12, "4.2.4 Calculations", "cleanout every 20–30 m", RG, "outlet", "underdrain_cleanout_spacing_m", "m",
  min=20, max=30)
r("rg.area_share", G, 14, "4.2.5-01 Sizing & Footprint", "3–7% of contributing impervious catchment area", RG, "siting",
  "footprint_fraction_of_drainage_area", "%", min=3, max=7, condition="loading ratio 5:1 to 10:1 to be checked")
r("rg.loading", G, 14, "4.2.5-01 Sizing & Footprint", "should be checked: typical 5:1–10:1", RG, "siting",
  "impervious_to_footprint_ratio", "ratio", min=5, max=10, severity="typical")
r("rg.min_width", G, 14, "4.2.5-01 Sizing & Footprint", "Minimum width for planting 0.6 m (2 ft)", RG, "geometry",
  "min_width_m", "m", min=0.6)
r("rg.total_depth", G, 18, "4.2.5-02 Soil & Media", "not to exceed 60 in (1,524 mm)", RG, "geometry", "total_depth_m", "mm",
  max=1524, condition="soil plus stone base", climate=NYC)
r("rg.compost", G, 18, "4.2.5-02 Soil & Media", "(20–30% organic material by volume)", RG, "media",
  "media_organic_content_pct", "%", min=20, max=30, condition="compost by volume")
r("rg.clear_path", G, 20, "4.2.5-05 Structural & Safety", "Min. 5 ft (1.5 m) unobstructed pedestrian path", RG, "safety",
  "pedestrian_clear_width_m", "m", min=1.5, condition="sidewalk installations", climate=NYC, severity="requirement")
r("rg.plant_height", G, 20, "4.2.5-05 Structural & Safety", "Planting height limit 4 ft", RG, "safety", "max_plant_height_m", "ft",
  max=4, condition="sight lines at intersections", climate=NYC)
r("rg.inspect_storm", G, 24, "4.2.6 Maintenance Schedule", "After every storm event ≥ 25 mm", RG, "maintenance",
  "inspection_storm_depth", "mm", value=25, condition="clear litter and sediment from curb cuts")
r("rg.sediment", G, 24, "4.2.6 Maintenance Schedule", "volume is reduced by 15–20% of design capacity", RG, "maintenance",
  "sediment_removal_trigger_pct", "%", min=15, max=20, condition="stone base / forebay; every 5-10 years or as needed")
r("rg.mulch", G, 25, "4.2.6 Material Specification", "Max 75 mm (3 in) shredded mulch", RG, "media", "mulch_depth_m", "mm",
  max=75, condition="no wood chips (they float and block curb cuts)", climate=NYC)

# ---------------------------------------------------------------- 4.6 retention basin (retention_pond; after NC DEQ, MN, PA DEP)
B, RP, US = "4.6_Retention Basin_D2.pdf", "retention_pond", ["Cfa", "Dfa"]
r("rp.cost", B, 3, "4.6.1 Facts and Figures", "₹15-20 Lakhs (full system)", RP, "cost", "capex", "text",
  text="Capex INR 15-20 lakh for a basin of about 25 x 18 m; annual opex INR 60,000-2,00,000.", severity="information")
r("rp.pool_depth", B, 8, "4.6.4 Calculations", "Min: 0.9 m (3 ft) · Typical: 1.2–2.3 m", RP, "geometry",
  "permanent_pool_depth_m", "m", min=0.9, max=3.0, value=1.2, condition="typical 1.2-2.3 m; deeper stratifies",
  climate=US, severity="requirement")
r("rp.footprint", B, 8, "4.6.4 Calculations", "1–3% of contributing drainage area", RP, "siting",
  "footprint_fraction_of_drainage_area", "%", min=1, max=3, climate=US)
r("rp.lw", B, 8, "4.6.4 Calculations", "≥ 3:1 overall; shortest flow path ≥ 0.7 × overall", RP, "geometry",
  "length_to_width", "ratio", min=3, climate=US)
r("rp.outer_slope", B, 8, "4.6.4 Calculations", "Outer embankment: max 3H:1V", RP, "safety", "side_slope_h_v", "H:V", min=3,
  condition="outer embankment; interior/aquatic bench 4H:1V to 5H:1V; safety bench at least 4H:1V", climate=US,
  severity="requirement")
r("rp.forebay_vol", B, 8, "4.6.4 Calculations", "10–20% of total permanent pool volume", RP, "pretreatment",
  "forebay_volume_fraction", "%", min=10, max=20, climate=US)
r("rp.forebay_depth", B, 8, "4.6.4 Calculations", "0.9–1.8 m (3–6 ft); set 300 mm below main basin floor", RP,
  "pretreatment", "forebay_depth_m", "m", min=0.9, max=1.8, climate=US)
r("rp.forebay_where", B, 8, "4.6.4 Calculations", "At each major inlet draining ≥ 10% of total catchment", RP,
  "pretreatment", "forebay_inlet_share_pct", "%", min=10, condition="a forebay at each inlet draining this much", climate=US)
r("rp.gravel", B, 8, "4.6.4 Calculations", "Thickness ≥ 450 mm · Gravel 20–50 mm", RP, "media", "storage_layer_depth_m",
  "mm", min=450, condition="uniform crushed angular stone, porosity 0.4")
r("rp.soil", B, 8, "4.6.4 Calculations", "Total depth: 650 mm · 40–50% native soil", RP, "media", "soil_media_depth_m",
  "mm", value=650, condition="40-50 % native soil, 25-30 % sand, 20-25 % compost")
r("rp.hrt", B, 8, "4.6.4 Calculations", "Water quality HRT ≥ 14 days", RP, "storage", "hydraulic_retention_time_hr", "day",
  min=14, max=21, condition="about 90 % TSS removal; surcharge drawdown 2-5 days", climate=US)
r("rp.drawdown", B, 14, "4.6.5-03 Maintenance & Overflow", "draw-down requirement for the temporary surcharge volume remains 2–5 days",
  RP, "storage", "drawdown_time_hr", "day", min=2, max=5, condition="surcharge volume above the permanent pool", climate=US)
r("rp.pool_wqv", B, 8, "4.6.4 Calculations", "≥ 1 × Water Quality Volume (WQv)", RP, "storage",
  "permanent_pool_to_wqv_ratio", "ratio", min=1, climate=US)
r("rp.liner", B, 12, "4.6.5-02 Soil Suitability / Liner", "impermeable liner required to maintain permanent pool", RP,
  "siting", "liner_on_permeable_soils", "text", text="HSG A/B soils or karst: an impermeable liner is needed to hold the pool.",
  climate=US, severity="requirement")
r("rp.removal", B, 14, "4.6.5-03 Maintenance & Overflow", "TSS: 70–90%", RP, "performance", "tss_load_reduction_pct", "%",
  min=70, max=90, condition="TP 50-70 %, TN 25-40 %, metals and hydrocarbons 50-80 %", climate=US, severity="information")
r("rp.freeboard", B, 14, "4.6.5-03 Maintenance & Overflow", "Min: 300 mm (1 ft) above maximum surcharge level", RP,
  "outlet", "freeboard_m", "mm", min=300, max=600, condition="typical 300-600 mm", climate=US, severity="requirement")
r("rp.spillway", B, 14, "4.6.5-03 Maintenance & Overflow", "capable of passing the 100- year storm", RP, "outlet",
  "spillway_design_storm", "yr", min=100, condition="online facilities, with 1 ft freeboard", climate=US, severity="requirement")
r("rp.no_turf", B, 16, "4.6.5-04 Vegetation", "turf grass should not be used", RP, "planting", "buffer_planting", "text",
  text="Buffer of native trees, shrubs and ground covers, no turf; emergent natives in the wet zone (e.g. vetiver, colocasia).")
r("rp.forebay_clean", B, 17, "4.6.6 Maintenance Schedule", "reaches 50% of design forebay volume", RP, "maintenance",
  "forebay_cleanout_trigger_pct", "%", value=50, condition="typically every 1-3 years")
r("rp.basin_clean", B, 17, "4.6.6 Maintenance Schedule", "reduced by 15–20% of design capacity", RP, "maintenance",
  "sediment_removal_trigger_pct", "%", min=15, max=20, condition="main basin, every 5-10 years")

# ---------------------------------------------------------------- 4.7 bio-swale (bioswale; after NACTO, FHWA HEC-15, USEPA, CPHEEO)
S, BS = "4.7_Bio-Swale_D2.pdf", "bioswale"
r("bs.cost", S, 3, "4.7.1 Facts and Figures", "₹40,000 - 1,00,000(full system)", BS, "cost", "capex", "text",
  text="Capex INR 40,000-1,00,000 for a swale of at least 3 x 1 m; annual opex INR 1,200-3,000.", severity="information")
r("bs.min_size", S, 3, "4.7.1 Facts and Figures", "min. 3 m x min. 1 m", BS, "geometry", "length_m", "m", min=3,
  condition="minimum unit 3 m long, 1 m wide", severity="typical")
r("bs.area", S, 8, "4.7.4 Calculations", "≤ 5 acres (2 hectares)", BS, "siting", "contributing_area_m2", "ha", max=2.0,
  climate=US, severity="requirement")
r("bs.velocity", S, 8, "4.7.4 Calculations", "≤ 1.0 fps (0.3m/s)", BS, "geometry", "peak_velocity_m_s", "m/s", max=0.3,
  condition="water quality flow", climate=US, severity="requirement")
r("bs.manning", S, 8, "4.7.4 Calculations", "0.20 to 0.35 (for dense grass/ turf)", BS, "geometry", "manning_n", "-",
  min=0.20, max=0.35, climate=US)
r("bs.hrt", S, 8, "4.7.4 Calculations", "Min Hydraulic Retention Time ≥ 9 minutes", BS, "storage", "residence_time", "min",
  min=9, climate=US)
r("bs.surface_drawdown", S, 8, "4.7.4 Calculations", "Drawdown Time (Surface) ≤ 12 Hours", BS, "storage",
  "drawdown_time_hr", "hr", max=12, condition="surface ponding (media subsurface 48 h)", severity="requirement")
r("bs.media_drawdown", S, 8, "4.7.4 Calculations", "Drawdown Time (Media Subsurface) ≤48 Hours", BS, "storage",
  "media_drawdown_time_hr", "hr", max=48, severity="requirement")
r("bs.media_depth", S, 8, "4.7.4 Calculations", "Min. 2.0 feet (600 mm)", BS, "media", "soil_media_depth_m", "mm", min=600,
  severity="requirement")
r("bs.media_rate", S, 8, "4.7.4 Calculations", "1.0 in/hr to 6.0 in/hr", BS, "media", "media_infiltration_rate_mm_hr",
  "in/hr", min=1.0, max=6.0, condition="NACTO allows peaks up to 10 in/hr", climate=US)
r("bs.native_rate", S, 8, "4.7.4 Calculations", "≥ 0.5 in/hr (12.7 mm/hr)", BS, "siting", "native_infiltration_rate_mm_hr",
  "in/hr", min=0.5, climate=US)
r("bs.ponding", S, 8, "4.7.4 Calculations", "6 in. to 18 in. maximum", BS, "geometry", "max_ponding_depth_m", "in",
  min=6, max=18, climate=US)
r("bs.bottom_width_calc", S, 8, "4.7.4 Calculations", "2.0 feet to 8.0 feet", BS, "geometry", "bottom_width_m", "ft",
  min=2, max=8, climate=US)
r("bs.long_slope", S, 8, "4.7.4 Calculations", "0.5% to 2.0% (Ideal)", BS, "geometry", "longitudinal_slope_pct", "%",
  min=0.5, max=2.0, condition="up to 6 % with check dams")
r("bs.side_slope", S, 8, "4.7.4 Calculations", "4H:1V (Recommended for Maintenance)", BS, "geometry", "side_slope_h_v",
  "H:V", value=4, min=2, condition="2:1 to 3:1 absolute maximum")
r("bs.ratio", S, 10, "4.7.5-01 Swale Dimension", "Roughly 5:1 to 10:1", BS, "siting", "impervious_to_footprint_ratio",
  "ratio", min=5, max=10)
r("bs.length", S, 10, "4.7.5-01 Swale Dimension", "Generally 30–60 m minimum for effective treatment", BS, "geometry",
  "length_m", "m", min=30, value=60)
r("bs.wqv", S, 10, "4.7.5-01 Swale Dimension", "often the first 25 mm (1 inch) of runoff", BS, "storage",
  "water_quality_runoff_depth", "mm", value=25)
r("bs.bottom_width", S, 10, "4.7.5-01 Swale Dimension", "0.45 – 2.4 m", BS, "geometry", "bottom_width_m", "m", min=0.45,
  max=2.4, condition="the notes give 1.0 m as the practical urban limit in one column and 2.4 m in the other")
r("bs.gw_5ft", S, 10, "4.7.5-01 Swale Dimension", "Maintain a 5-foot minimum clearance", BS, "siting",
  "groundwater_separation_m", "ft", min=5, condition="conflicts with the 2 ft (USEPA 2004) in the notes of the same row",
  climate=US)
r("bs.gw_2ft", S, 10, "4.7.5-01 Swale Dimension", "at least 2 feet above the seasonally high groundwater table", BS,
  "siting", "groundwater_separation_m", "ft", min=2, condition="USEPA 2004; conflicts with the 5 ft in the same row",
  climate=US)
r("bs.freeboard", S, 12, "4.7.5-02 Hydrology", "0.15–0.3 m (6–12 in) of freeboard", BS, "outlet", "freeboard_m", "m",
  min=0.15, max=0.3, condition="above the design water surface; total depth rarely over 0.6 m (FHWA HEC-15, CPHEEO)")
r("bs.drainage", S, 12, "4.7.5-02 Hydrology", "450 mm recommended; may vary from 150–600+ mm", BS, "media",
  "storage_layer_depth_m", "mm", value=450, min=150, max=600,
  condition="150-300 mm good native soils; 300-450 with underdrain; 450-600 with internal water storage")
r("bs.velocity_cons", S, 16, "4.7.5-02 Hydrology", "0.5–1.0 m/s is more conservative", BS, "geometry", "peak_velocity_m_s",
  "m/s", min=0.5, max=1.0, condition="design (not water quality) flows")
r("bs.storm", S, 16, "4.7.5-02 Hydrology", "Typically sized for the 2-year or 10-year storm", BS, "storage",
  "design_storm", "yr", min=2, max=10, condition="depending on jurisdiction", severity="typical")
r("bs.media_range", S, 16, "4.7.5-03 Soil & Vegetation", "600 – 1000 mm (topsoil + sand/ gravel)", BS, "media",
  "soil_media_depth_m", "mm", min=600, max=1000)
r("bs.plants", S, 16, "4.7.5-03 Soil & Vegetation", "Grass, sedge, Vetiver, Cyperus, Chrysopogon", BS, "planting",
  "species", "text", text="Native grass, sedge, vetiver, Cyperus, Chrysopogon.")
r("bs.check_dams", S, 18, "4.7.5-04 Underdrain, Overflow", "Every 10–15 m to reduce erosion", "check_dam", "geometry",
  "check_dam_spacing_m", "m", min=10, max=15)
r("bs.cleanouts", S, 18, "4.7.5-04 Underdrain, Overflow", "Cleanouts to be provided at 30m spacing max", BS, "outlet",
  "underdrain_cleanout_spacing_m", "m", max=30)
r("bs.underdrain", S, 18, "4.7.5-04 Underdrain, Overflow", "Pipe diameter: 100–150 mm (4–6 in) perforated pipe", BS,
  "outlet", "underdrain_diameter_m", "mm", min=100, max=150, condition="in 0.3 m of washed gravel; orifice or riser outlet")
r("bs.native_min", S, 18, "4.7.5-04 Underdrain, Overflow", ">13 mm/hr (adjusted with soil amendment)", BS, "siting",
  "native_infiltration_rate_mm_hr", "mm/hr", min=13)
r("bs.setback", S, 18, "4.7.5-04 Underdrain, Overflow", "Typically 3 m from buildings", BS, "siting", "building_setback_m",
  "m", min=3)
r("bs.inspect", S, 21, "4.7.6 Maintenance Schedule", "6 months and before monsoons", BS, "maintenance",
  "inspection_frequency", "times/yr", value=2, condition="side slopes, channel bottom, clogging")
r("bs.sediment", S, 21, "4.7.6 Maintenance Schedule", "after 25% of the original design volume has filled", BS,
  "maintenance", "sediment_removal_trigger_pct", "%", value=25, condition="usually when about 4 in has built up")

# ---------------------------------------------------------------- 4.8 detention basin (detention_basin; after Maine DEP, Riverside Co., ITD)
D, DB = "4.8_Detention Basin.pdf", "detention_basin"
r("db.cost", D, 3, "4.8.1 Facts and Figures", "₹15 - 37 Lakhs (full system)", DB, "cost", "capex", "text",
  text="Capex INR 15-37 lakh for a basin of at least 25 x 17 m; annual opex INR 50,000-1.3 lakh.", severity="information")
r("db.min_size", D, 3, "4.8.1 Facts and Figures", "Min. 25m x Min. 17m", DB, "geometry", "area_m2", "m2", min=425,
  condition="minimum unit 25 m x 17 m", severity="typical")
r("db.drain", D, 8, "4.8.4 Calculations", "Full drawdown in 48–72 hrs", DB, "storage", "drawdown_time_hr", "hr", min=48, max=72,
  condition="dry basin", climate=US, severity="requirement")
r("db.storage_rule", D, 8, "4.8.4 Calculations", "1 ac-ft per 4 ac drainage area", DB, "storage",
  "storage_depth_over_catchment", "ft", value=0.25, condition="rule of thumb: 1 acre-ft per 4 acres, i.e. 0.25 ft (76 mm) of runoff",
  climate=US, severity="typical")
r("db.storms", D, 8, "4.8.4 Calculations", "2-yr, 10-yr, 25-yr, 100-yr, 24-hr", DB, "storage", "design_storm", "yr", min=2,
  max=100, condition="route each 24-hour storm (TR-55 / HEC-HMS)", climate=US)
r("db.lw", D, 8, "4.8.4 Calculations", "Min 2:1; optimum ≥3:1", DB, "geometry", "length_to_width", "ratio", min=2, value=3,
  climate=US)
r("db.flow_path", D, 8, "4.8.4 Calculations", "≥0.7 (shortest path / basin length)", DB, "geometry", "flow_path_ratio",
  "ratio", min=0.7, condition="extended detention", climate=US)
r("db.side_slope", D, 8, "4.8.4 Calculations", "≤3H:1V preferred; 2H:1V absolute min", DB, "geometry", "side_slope_h_v",
  "H:V", min=2, value=3, condition="at least one slope at 3:1", climate=US, severity="requirement")
r("db.freeboard_no_spill", D, 8, "4.8.4 Calculations", "WSEdesign ≥ 3 ft", DB, "outlet", "freeboard_m", "ft", min=3,
  condition="no emergency spillway: embankment crest above the design water level", climate=US, severity="requirement")
r("db.freeboard_spill", D, 8, "4.8.4 Calculations", "WSEspillway - WSEdesign ≥ 1 ft", DB, "outlet", "freeboard_m", "ft", min=1,
  condition="with an emergency spillway", climate=US, severity="requirement")
r("db.forebay", D, 10, "4.8.5-01 Basin Sizing & Design", "Forebay 300mm below main basin", DB, "pretreatment",
  "forebay_depth_below_floor_m", "mm", value=300)
r("db.liner", D, 10, "4.8.5-01 Basin Sizing & Design", "Dry basins should not be located in HSG-A", DB, "siting",
  "liner_on_permeable_soils", "text", text="Dry basins on HSG A/B soils or within 1 ft of bedrock need an impermeable liner.",
  climate=US, severity="requirement")
r("db.sediment_life", D, 10, "4.8.5-01 Basin Sizing & Design", "over the basin’s design life (50–100 years)", DB, "storage",
  "sediment_storage_design_life", "yr", min=50, max=100, climate=US)
r("db.orifice", D, 14, "4.8.5-02 Overflow Design", "Minimum orifice diame­ter: 1.0 in (circular)", DB, "outlet",
  "outlet_diameter_m", "in", min=1.0, condition="orifices under 3 in need extra inspection", climate=US, severity="requirement")
r("db.release", D, 14, "4.8.5-02 Overflow Design", "Design to release 50% of VBMP within 24 hrs", DB, "storage",
  "half_volume_drawdown_hr", "hr", max=24, condition="100 % of the BMP volume within 72 h", climate=US)
r("db.overflow_pipe", D, 14, "4.8.5-02 Overflow Design", "Overflow pipe min. dia 100-200 mm", DB, "outlet",
  "overflow_pipe_diameter_m", "mm", min=100, max=200)
r("db.wq_detention", D, 14, "4.8.5-02 Overflow Design", "average detention time of 12 hours", DB, "storage",
  "detention_time_hr", "hr", min=12, condition="water quality volume", climate=US)
r("db.micropool", D, 14, "4.8.5-02 Overflow Design", "Micropool at outlet (≥4 ft deep)", DB, "outlet", "micropool_depth_m",
  "ft", min=4, climate=US)
r("db.trash", D, 14, "4.8.5-02 Overflow Design", "Trash rack spacing ≤6 in", DB, "outlet", "trash_rack_spacing_m", "in",
  max=6, condition="inclined racks at least four times the outlet opening", climate=US)
r("db.max_detention", D, 17, "4.8.5-03 Hydrology", "Maximum 96 hrs to prevent mosquito breeding", DB, "safety",
  "max_detention_time_hr", "hr", max=96, condition="longer only with anti-mosquito measures", climate=US,
  severity="requirement")
r("db.tss", D, 17, "4.8.5-03 Hydrology", "Extended detention of 24–40 hrs", DB, "performance", "detention_time_hr", "hr",
  min=24, max=40, condition="needed for about 80 % TSS removal", climate=US, severity="information")
r("db.gw", D, 17, "4.8.5-03 Hydrology", "Min. 1 ft above seasonal high groundwater table", DB, "siting",
  "groundwater_separation_m", "ft", min=1, condition="and 1 ft above bedrock", climate=US, severity="requirement")
r("db.media", D, 17, "4.8.5-03 Hydrology", "Min 450mm drainage layer; 650mm engi­neered soil", DB, "media",
  "storage_layer_depth_m", "mm", min=450, condition="650 mm engineered soil (40-50 % native, 25-30 % sand, 20-25 % compost)")
r("db.access", D, 18, "4.8.5-04 Maintenance", "Min. access road width: 10–15 ft", DB, "maintenance", "access_road_width_m",
  "ft", min=10, max=15, condition="max road slope 15 %, cross-slope 3 %", climate=US)
r("db.sediment", D, 18, "4.8.5-04 Maintenance", "storage capacity by 15 to 20 percent", DB, "maintenance",
  "sediment_removal_trigger_pct", "%", min=15, max=20, condition="main basin; forebay at least annually")
r("db.mow", D, 19, "4.8.6 Vegetation", "Mow ≤2x/year, max height 12 in", DB, "maintenance", "mowing_frequency", "times/yr",
  max=2, condition="no trees in the pool zone", climate=US)
r("db.forebay_clean", D, 19, "4.8.6 Maintenance Schedule", "Remove sediment from forebay when depth reaches 50%", DB,
  "maintenance", "forebay_cleanout_trigger_pct", "%", value=50)
r("db.recharge", D, 20, "4.8.7 Hydrological Assessment", "Generally low to none, as detention basins", DB, "performance",
  "groundwater_recharge", "text", text="Low to no groundwater recharge: built for temporary storage and slow release.",
  severity="information")

staging.save(SRC, rules)
print(len(rules), "rules")
