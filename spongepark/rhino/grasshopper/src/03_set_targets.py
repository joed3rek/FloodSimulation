"""Set Targets
Sets design targets as user decisions (stored in the project with source 'user').
Inputs:  project (str); area_budget_pct (float); design_rp (int); max_drawdown_hr (float);
         target_rp_inverse (int); apply (bool, button)
Outputs: done (list of str)
"""
if apply and project:
    done = []
    for key, val, unit in (("layout.max_area_pct", area_budget_pct, "%"),
                           ("layout.design_return_period_yr", design_rp, "yr"),
                           ("nbs.max_drawdown_hr", max_drawdown_hr, "hr"),
                           ("optimise.target_return_period_yr", target_rp_inverse, "yr")):
        if val is not None:
            q = call("PUT", "/projects/{}/parameters/{}".format(project, key), {"value": val, "unit": unit})
            done.append("{} = {} {} ({})".format(q["key"], q["value"], q["unit"], q["source"]))
