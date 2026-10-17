"""Write Back
Sends edited element geometry to the engine: each becomes a designer element and is locked; the
engine regrades, rebuilds subcatchments and reruns SWMM.
Inputs:  project (str); option (str); curves (list of curves); ids (list of str, empty = new);
         types (list of str: rain_garden, bioswale, detention_pond, retention_pond, recharge_well); send (bool, button)
Outputs: result (list of str)
"""
if send and project and option and curves:
    fc = call("GET", "/projects/{}/options/{}/components".format(project, option))
    old = {f["properties"]["id"]: f["properties"] for f in fc["features"]}
    feats, n = [], 0
    for k, crv in enumerate(curves):
        eid = ids[k] if ids and k < len(ids) and ids[k] else None
        etype = types[k] if types and k < len(types) and types[k] else (old.get(eid, {}).get("type") or "rain_garden")
        if eid is None:
            n += 1
            eid = "{}_GH{}".format(etype[:2].upper(), n)
        props = dict(old.get(eid, {}), id=eid, type=etype)
        for drop in ("area_m2", "storage_volume_m3", "drawdown_time_hr", "contributing_area_m2", "inflow_from"):
            props.pop(drop, None)
        ok, pl = crv.TryGetPolyline()
        if ok:
            pts = [(p.X, p.Y) for p in pl]
        else:
            pts = [(crv.PointAt(crv.Domain.ParameterAt(i / 100.0)).X, crv.PointAt(crv.Domain.ParameterAt(i / 100.0)).Y)
                   for i in range(101)]
        if etype == "recharge_well":
            bb = crv.GetBoundingBox(True)
            geom = {"type": "Point", "coordinates": [bb.Center.X, bb.Center.Y]}
            props["well_diameter_m"] = bb.Max.X - bb.Min.X
        elif crv.IsClosed:
            geom = {"type": "Polygon", "coordinates": [pts]}
        else:
            geom = {"type": "LineString", "coordinates": pts}
        if etype in ("detention_pond", "retention_pond", "recharge_well"):
            props["invert_elev_m"] = 0.0  # recomputed from the new rim by the regrade
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    r = run_job("PUT", "/projects/{}/options/{}/components".format(project, option),
                {"type": "FeatureCollection", "features": feats})
    result = list(r["regrade"]["warnings"])
    for x in (r.get("comparison") or {}).get("rows", []):
        result.append("{:>4}-yr retained {:.1f} %".format(x["return_period_yr"], x["option_retained_pct"]))
