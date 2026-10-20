"""Staged rules from the CGWB Manual on Artificial Recharge of Ground Water (user-supplied copy, 2026-10-20)."""
from spongepark.engine.knowledge import staging

SRC, ED, CL = "cgwb_recharge", "Central Ground Water Board, Ministry of Water Resources (2007)", ["Aw", "BSh", "Cwa", "Am"]
F = "Manual-Artificial-Recharge.pdf"
RW = "recharge_well"
rules = []


def r(rid, page, section, snippet, element, category, parameter, unit, **kw):
    rules.append(staging.StagedRule(id=f"{SRC}.{rid}", source=SRC, edition=ED, file=F, page=page, section=section,
                                    snippet=snippet, element=element, category=category, parameter=parameter,
                                    unit=unit, climate=CL, **kw))


# ---------------------------------------------------------------- where recharge is wanted (siting)
r("rw.cutoff", 54, "5.1.2 Sub-surface Storage Capacity", "below a certain cut-off level (say 3.00 m.bgl in phreatic aquifers)",
  RW, "siting", "min_depth_to_water_table_m", "m", min=3.0,
  condition="phreatic aquifers: only the unsaturated zone below this depth counts as recharge storage")
r("rw.priority_shallow", 56, "5.1.3 Prioritisation of Areas", "water levels in the range of 3 to 6 m.bgl", RW, "siting",
  "depth_to_water_table_m", "m", min=3, max=6, condition="priority area if also declining 0.10-0.20 m/yr",
  severity="information")
r("rw.priority_deep", 56, "5.1.3 Prioritisation of Areas", "water levels deeper than 9.00 m bgl", RW, "siting",
  "depth_to_water_table_m", "m", min=9, condition="priority area if declining more than 0.40 m/yr", severity="information")
r("rw.tank_wt", 84, "6.2.2.5 Percolation Tanks", "should remain more than 3 m below ground level", RW, "siting",
  "min_depth_to_water_table_m", "m", min=3.0, condition="post-monsoon water level (percolation tanks)", severity="requirement")

# ---------------------------------------------------------------- injection / recharge wells
r("rw.efficiency", 98, "6.2.3.1.1 Site Selection and Design Criteria", "should be taken as 40 to 60 percent", RW, "storage",
  "injection_efficiency_pct", "%", min=40, max=60,
  condition="of a pumping well of similar design, because of clogging", severity="requirement")
r("rw.injection_head", 98, "6.2.3.1.1 Site Selection and Design Criteria", "worked out as 1.2 times the depth to the top",
  RW, "safety", "max_injection_head_factor", "ratio", max=1.2,
  condition="water column, times the depth to the top of the confined aquifer (hydrofracturing)", severity="requirement")
r("rw.pipe_100", 99, "6.2.3.1.1 Site Selection and Design Criteria", "pipes with nominal diameters of 100mm, 150mm, 200mm", RW,
  "geometry", "well_diameter_m", "mm", value=100,
  condition="carries up to 50 m3/hr (150 mm: 150, 200 mm: 250, 250 mm: 400 m3/hr)", severity="typical")
r("rw.penetrate", 99, "6.2.3.1.1 Site Selection and Design Criteria", "designed to fully penetrate the aquifer", RW,
  "geometry", "aquifer_penetration", "text", text="Recharge wells should fully penetrate the aquifer.")
r("rw.entrance_velocity", 99, "6.2.3.1.1 Site Selection and Design Criteria", "velocity recommended (0.03m/sec) for pumping wells",
  RW, "geometry", "screen_entrance_velocity", "m/s", max=0.03, condition="exit velocity through the screen")
r("rw.source_water", 98, "6.2.3.1.1 Site Selection and Design Criteria", "ensure that the water being used for recharge is not contaminated",
  RW, "pretreatment", "source_water_quality", "text", text="Recharge water must not be contaminated and must suit the formation water.",
  severity="requirement")
r("rw.pipe_to_bottom", 102, "6.2.3.2.1 Site Characteristics and Design Guidelines", "guided through a pipe to the bottom of well",
  RW, "inlet", "inlet_pipe_to_bottom", "text", text="Feed recharge water by pipe to below the water level (no scour, no air).")

# ---------------------------------------------------------------- recharge pits and shafts
r("pit.side_slope", 103, "6.2.3.3.1.1 Recharge Pits", "The side slopes of recharge pits should be 2:1", RW, "geometry",
  "side_slope_h_v", "H:V", value=2, condition="recharge pits")
r("pit.infiltration_test", 103, "6.2.3.3.1.1 Recharge Pits", "should be ascertained through infiltration tests",
  RW, "siting", "infiltration_test", "text", text="Test the permeability of the underlying strata before building.",
  severity="requirement")
r("shaft.diameter_dug", 104, "6.2.3.3.2.1 Recharge Shafts", "about 2m in diameter at the bottom if manually dug", RW, "geometry",
  "well_diameter_m", "m", value=2.0, condition="manually dug shafts", severity="typical")
r("shaft.diameter_drilled", 104, "6.2.3.3.2.1 Recharge Shafts", "the diameter may not exceed 1m", RW, "geometry",
  "well_diameter_m", "m", max=1.0, condition="drilled shafts")
r("shaft.reach", 104, "6.2.3.3.2.1 Recharge Shafts", "need not necessarily touch the water table", RW, "geometry",
  "well_depth_rule", "text", text="Reach the permeable strata through the low-permeability layer; need not reach the water table.")
r("shaft.filter", 104, "6.2.3.3.2.1 Recharge Shafts", "back-filled with an inverse filter, comprising boulders/cobbles", RW,
  "media", "filter_fill", "text", text="Inverse filter: boulders/cobbles at the bottom, then gravel, then sand (replaced periodically).")
r("shaft.silt", 106, "6.2.3.3.2.1 Recharge Shafts", "should be made as silt-free as possible", RW, "pretreatment",
  "silt_free_inflow", "text", text="Filter the source water before it enters the shaft.", severity="requirement")

# ---------------------------------------------------------------- roof-top harvesting into recharge (rainwater_harvesting)
r("rwh.filter_sand", 124, "7.2.6.3 Classification of Filters", "ranging in thickness from 60 to 90 cm", "rainwater_harvesting",
  "media", "filter_sand_depth_m", "cm", min=60, max=90, condition="coarse sand over graded gravel")
r("rwh.first_flush", 190, "10.5.1 Tips for Maintenance", "Avoid first 15 or 20 minutes of rainfall", "rainwater_harvesting",
  "pretreatment", "first_flush_minutes", "min", min=15, max=20, condition="depending on rain intensity")
r("rwh.filter_change", 190, "10.5.1 Tips for Maintenance", "Change the filter media every rainy season", "rainwater_harvesting",
  "maintenance", "filter_replacement_interval", "yr", value=1)
r("rwh.down_pipe", 117, "7.2.4 Down Pipe", "PVC material of diameter 7.5 cm", "rainwater_harvesting", "inlet",
  "down_pipe_diameter_m", "cm", value=7.5, severity="typical")

staging.save(SRC, rules)
print(len(rules), "rules")
