"""Generate Options
Generates a layout (or, with optimise, Pareto options), grades it and runs SWMM.
Inputs:  project (str); option (str, e.g. "auto"); optimise (bool); mode (str forward|inverse); run (bool, button)
Outputs: options (list of str); report (list of str)
"""
if run and project:
    if optimise:
        r = run_job("POST", "/projects/{}/optimise".format(project), {"mode": mode or "forward"})
        options = [o["option_id"] for o in r["options"]]
        report = ["{}: {:.1f} % of site, cut {:.0f} m3, design retention storm {} yr".format(
            o["option_id"], o["area_pct"], o["cut_m3"], o["design_retention_storm_yr"]) for o in r["options"]]
        report.append(r["note"])
    else:
        r = run_job("POST", "/projects/{}/options/{}/generate".format(project, option or "auto"), {"run": True})
        options = [option or "auto"]
        report = ["{} {} {:.0f} m2 -> {}".format(e["id"], e["type"], e["area_m2"], e["outflow_to"])
                  for e in r["layout"]["elements"]] + ["skipped: " + s for s in r["layout"]["skipped"]]
        report += ["kept (designer): " + i for i in r["layout"]["kept_designer_elements"]]
