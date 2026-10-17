"""Load Project
Inputs:  path (str) .sponge file or folder; create (bool); load (bool, button)
Outputs: project (str id); info (str); options (list of str)
"""
if load and path:
    r = call("POST", "/projects/open", {"path": path, "create": bool(create)})
    project = r["project"]
    options = r["options"]
    info = "{} | CRS {} | {} | baseline run: {} | unconfirmed parameters: {}".format(
        r["name"], r["crs"], r["calibration"], r["has_baseline"], r["unconfirmed_parameters"])
