"""Analyse Baseline
Delineates subcatchments from the terrain and runs the existing-site SWMM model for every return period.
Inputs:  project (str); run (bool, button)
Outputs: outfalls (list of points); table (list of str)
"""
import Rhino.Geometry as rg

if run and project:
    r = run_job("POST", "/projects/{}/baseline".format(project))
    s = r["summary"]
    table = [s["calibration"]]
    for rp, v in sorted(s["return_periods"].items(), key=lambda kv: int(kv[0])):
        wb = v["water_balance"]
        table.append("{:>4}-yr  rain {:6.1f} mm  leaving {:8.1f} m3  peak {:.3f} m3/s  continuity {:.2f} %".format(
            rp, v["storm"]["depth_mm"], wb["outflow_total_m3"] + wb["flooding_m3"], v["hydrograph"]["peak_cms"],
            wb["closure_error_pct"]))
    outfalls = []
    for sc in (r["delineation"] or {}).get("subcatchments", []):
        x, y = sc["outfall_xy"]
        outfalls.append(rg.Point3d(x, y, sc["outfall_level_m"]))
