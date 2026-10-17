"""Play Storm
Water depth in each element through the storm. Drive t (0-1) with a slider or a timer.
Inputs:  project (str); option (str); rp (int); t (float 0-1)
Outputs: time_hr (float); rain_mm_hr (float); depths (list of str); fill (list of float 0-1); ids (list of str)
"""
if project and option and rp is not None:
    key = (project, option, rp)
    cache = globals().setdefault("_sp_cache", {})
    if key not in cache:
        fc = call("GET", "/projects/{}/options/{}/components".format(project, option))
        ts = call("GET", "/projects/{}/options/{}/timeseries/{}".format(project, option, rp))
        s = call("GET", "/projects/{}/options/{}/summary".format(project, option))
        crest = {}
        for e in s["return_periods"][str(rp)]["elements"]:
            md, pf = e.get("max_depth_m"), e.get("pct_full")
            crest[e["id"]] = (md / (pf / 100.0)) if md and pf else (md or 1.0)
        cache[key] = (fc, ts, crest)
    fc, ts, crest = cache[key]
    cols = ts["columns"]
    row = ts["data"][int(round((t or 0) * (len(ts["data"]) - 1)))]
    time_hr = row[0]
    rain_mm_hr = row[cols.index("rain_mm_hr")] if "rain_mm_hr" in cols else 0.0
    ids, fill, depths = [], [], []
    for f in fc["features"]:
        i = f["properties"]["id"]
        c = "depth_{}_m".format(i)
        d = row[cols.index(c)] if c in cols else 0.0
        ids.append(i)
        fill.append(max(0.0, min(1.0, d / crest.get(i, 1.0))))
        depths.append("{}: {:.2f} m".format(i, d))
