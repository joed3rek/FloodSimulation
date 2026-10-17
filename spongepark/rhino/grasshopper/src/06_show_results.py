"""Show Results
Element outlines coloured by how full they get in a storm (green empty -> red full or overflowing).
Inputs:  project (str); option (str); rp (int)
Outputs: curves (list of curves); colours (list of colours); labels (list of str); ids (list of str)
"""
import Rhino.Geometry as rg
import System.Drawing as sd


def ramp(t):
    t = max(0.0, min(1.0, t))
    return sd.Color.FromArgb(int(255 * t), int(180 * (1 - t) + 40), int(60 * (1 - t)))


def outline(geom, width):
    if geom["type"] == "Polygon":
        return rg.Polyline([rg.Point3d(x, y, 0) for x, y in geom["coordinates"][0]]).ToNurbsCurve()
    if geom["type"] == "LineString":
        return rg.Polyline([rg.Point3d(x, y, 0) for x, y in geom["coordinates"]]).ToNurbsCurve()
    x, y = geom["coordinates"][:2]
    return rg.Circle(rg.Point3d(x, y, 0), (width or 1.2) / 2).ToNurbsCurve()


if project and option and rp:
    fc = call("GET", "/projects/{}/options/{}/components".format(project, option))
    s = call("GET", "/projects/{}/options/{}/summary".format(project, option))
    res = {e["id"]: e for e in s["return_periods"][str(rp)]["elements"]}
    curves, colours, labels, ids = [], [], [], []
    for f in fc["features"]:
        p = f["properties"]
        e = res.get(p["id"], {})
        if e.get("pct_full") is not None:
            full = e["pct_full"] / 100.0
        else:  # LID: full when it sends water on
            full = 1.0 if (e.get("outflow_m3") or 0) > 0.01 else 0.3
        curves.append(outline(f["geometry"], p.get("well_diameter_m") or p.get("top_width_m")))
        colours.append(ramp(full))
        ids.append(p["id"])
        labels.append("{} {}: {:.0f} % full, overflow {:.1f} m3".format(p["id"], p["type"], 100 * full,
                                                                      e.get("overflow_m3") or 0))
