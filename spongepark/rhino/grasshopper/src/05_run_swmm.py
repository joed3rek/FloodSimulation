"""Run SWMM
Runs SWMM for every return period of an option and compares it with the baseline.
Inputs:  project (str); option (str); run (bool, button)
Outputs: table (list of str); design_retention_storm (int)
"""
if run and project and option:
    r = run_job("POST", "/projects/{}/options/{}/run".format(project, option))
    c = r["comparison"]
    table = [r["summary"]["calibration"]]
    if c:
        design_retention_storm = c["design_retention_storm_yr"]
        for row in c["rows"]:
            table.append("{:>4}-yr retained {:5.1f} % (baseline {:5.1f} %), peak -{:4.0f} %, lag {:+.2f} h".format(
                row["return_period_yr"], row["option_retained_pct"], row["baseline_retained_pct"],
                row["peak_reduction_pct"] or 0, row["lag_hr"] or 0))
