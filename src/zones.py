"""Study zones and communes: pure geometry (Shapely), no Earth Engine needed, so it can be unit-tested.

All geometries are expected in a projected CRS in metres (config.ANALYSIS_CRS).
"""
import re

import shapely
from shapely.geometry import LineString, MultiPoint
from shapely.ops import polygonize, unary_union

BOUNDARY_SPACING_M = 100  # spacing of the points used to split overlapping zones


def nearest_territories(clusters: dict, spacing: float = BOUNDARY_SPACING_M) -> dict:
    """Split the plane between clusters: each point goes to the nearest cluster.

    Built from a Voronoi diagram of points sampled along every cluster boundary, so the
    dividing line runs halfway between neighbouring clusters (to within ``spacing``).
    Returns {key: polygon} covering the extent of the clusters plus a wide margin.
    """
    keys, points = [], []
    for key, geom in clusters.items():
        boundary = geom.boundary
        n = max(int(boundary.length // spacing), 4)
        for i in range(n):
            points.append(boundary.interpolate(i * boundary.length / n))
            keys.append(key)
    extent = unary_union(list(clusters.values())).envelope.buffer(100_000)
    cells = shapely.voronoi_polygons(MultiPoint(points), extend_to=extent, ordered=True).geoms
    return {key: unary_union([c for c, k in zip(cells, keys) if k == key]).intersection(extent)
            for key in clusters}


def study_zones(clusters: dict, buffer_m: float, land=None) -> dict:
    """Cluster + buffer, split where buffers of two cities overlap, clipped to land."""
    territories = nearest_territories(clusters) if len(clusters) > 1 else None
    zones = {}
    for key, geom in clusters.items():
        zone = geom.buffer(buffer_m)
        if territories is not None:
            zone = zone.intersection(territories[key])
        if land is not None:
            zone = zone.intersection(land)
        zones[key] = zone
    return zones


def relation_polygon(element: dict):
    """Polygon of an OSM relation returned by Overpass with ``out geom`` (None if it cannot be built)."""
    def rings(role):
        lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                 for m in element.get("members", [])
                 if m["type"] == "way" and m.get("role", "") == role and len(m.get("geometry", [])) > 1]
        return unary_union(list(polygonize(unary_union(lines)))) if lines else None

    outer = rings("outer") or rings("")
    if outer is None or outer.is_empty:
        return None
    inner = rings("inner")
    return outer.difference(inner) if inner is not None else outer


_PREFIXES = re.compile(r"^(commune|communauté rurale|communaute rurale|ville)\s+(de la|de l'|de|du|des|d')\s*",
                       re.IGNORECASE)


def clean_name(name: str) -> str:
    """'Communauté rurale de Fandène' -> 'Fandène' (all were turned into communes in 2013)."""
    return _PREFIXES.sub("", name.strip()).strip()


def remove_overlaps(geoms: list) -> list:
    """Make polygons disjoint: where they overlap, the smallest polygon keeps the area.

    OSM rural communes are often drawn coarsely over the small, more precise urban
    communes, so the smaller polygon is the more reliable one.
    """
    order = sorted(range(len(geoms)), key=lambda i: geoms[i].area)
    result, taken = [None] * len(geoms), None
    for i in order:
        g = geoms[i] if taken is None else geoms[i].difference(taken)
        result[i] = g
        taken = g if taken is None else unary_union([taken, g])
    return result
