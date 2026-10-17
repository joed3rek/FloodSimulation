"""Coordinate reference system checks.

All geometry must be in metres in a projected CRS (default UTM 43N, EPSG:32643)
or in local survey metres (``LOCAL``). Geographic coordinates are rejected
unless the caller asks for reprojection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

LOCAL = "LOCAL"


class CRSError(ValueError):
    pass


def validate_project_crs(crs: str) -> str:
    """Return a normalised CRS string, raising if it is not a projected metric CRS."""
    if crs.upper() == LOCAL:
        return LOCAL
    from pyproj import CRS

    c = CRS.from_user_input(crs)
    if not c.is_projected:
        raise CRSError(f"{crs} is geographic (degrees). Use a projected CRS in metres, e.g. EPSG:32643.")
    unit = c.axis_info[0].unit_name.lower()
    if unit not in ("metre", "meter"):
        raise CRSError(f"{crs} uses '{unit}' units; the engine requires metres.")
    epsg = c.to_epsg()
    return f"EPSG:{epsg}" if epsg else c.to_wkt()


def _iter_coords(geom: Dict[str, Any]):
    t = geom.get("type")
    coords = geom.get("coordinates")
    if t == "Point":
        yield coords
    elif t in ("LineString", "MultiPoint"):
        yield from coords
    elif t in ("Polygon", "MultiLineString"):
        for ring in coords:
            yield from ring
    elif t == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                yield from ring
    elif t == "GeometryCollection":
        for g in geom.get("geometries", []):
            yield from _iter_coords(g)


def looks_geographic(fc: Dict[str, Any]) -> bool:
    """True if every coordinate lies within lon/lat ranges (a strong hint of degrees)."""
    n = 0
    for f in fc.get("features", []):
        if not f.get("geometry"):
            continue
        for x, y, *_ in _iter_coords(f["geometry"]):
            n += 1
            if abs(x) > 180 or abs(y) > 90:
                return False
    return n > 0


def geojson_crs(fc: Dict[str, Any]) -> Optional[str]:
    crs = fc.get("crs")
    if isinstance(crs, dict):
        name = crs.get("properties", {}).get("name")
        if name:
            # "urn:ogc:def:crs:EPSG::32643" -> "EPSG:32643"
            if "EPSG" in name.upper():
                return "EPSG:" + name.split(":")[-1]
            return name
    return None


def ensure_project_crs(fc: Dict[str, Any], project_crs: str, source_crs: Optional[str] = None) -> Dict[str, Any]:
    """Return ``fc`` in the project CRS, reprojecting if a different source CRS is declared.

    Raises :class:`CRSError` if coordinates look geographic and no source CRS is given.
    """
    src = source_crs or geojson_crs(fc)
    if src is None:
        if looks_geographic(fc) and project_crs != LOCAL:
            raise CRSError(
                "Coordinates look like longitude/latitude degrees. Supply the source CRS "
                "(e.g. --source-crs EPSG:4326) so they can be reprojected to the project CRS."
            )
        return fc
    if project_crs == LOCAL:
        raise CRSError(f"Project uses local survey metres but the data declare CRS {src}.")
    from pyproj import CRS, Transformer

    if CRS.from_user_input(src) == CRS.from_user_input(project_crs):
        out = dict(fc)
        out.pop("crs", None)
        return out
    tr = Transformer.from_crs(src, project_crs, always_xy=True)
    from shapely.geometry import mapping, shape
    from shapely.ops import transform

    feats = []
    for f in fc.get("features", []):
        g = f.get("geometry")
        if g:
            g = mapping(transform(tr.transform, shape(g)))
        feats.append({**f, "geometry": g})
    log.info("reprojected %d features from %s to %s", len(feats), src, project_crs)
    return {"type": "FeatureCollection", "features": feats}
