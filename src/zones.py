"""Study zones and communes: pure geometry (Shapely), no Earth Engine needed, so it can be unit-tested.

All geometries are expected in a projected CRS in metres (config.ANALYSIS_CRS).
"""
import math
import re
import unicodedata

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


def name_key(name: str) -> str:
    """Comparable commune name: 'Mermoz-Sacré-Cœur' and 'MERMOZ SACRE COEUR' give the same key.

    Used to match OSM communes with the census (ANSD writes names in capitals, without accents).
    """
    s = str(name).replace("œ", "oe").replace("Œ", "OE")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"['’`]", "", s)            # M'bour -> MBOUR
    s = re.sub(r"[-_./]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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


DIRECTIONS_8 = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
DIRECTION_NAMES = {"N": "Nord", "NE": "Nord-Est", "E": "Est", "SE": "Sud-Est",
                   "S": "Sud", "SO": "Sud-Ouest", "O": "Ouest", "NO": "Nord-Ouest"}


def direction_wedge(centre, index: int, n: int, radius: float):
    """Triangle-fan wedge for direction ``index`` out of ``n``, centred on its azimuth (0 = north)."""
    half = math.pi / n
    azimuth = 2 * math.pi * index / n
    steps = 16
    arc = [(centre.x + radius * math.sin(azimuth - half + 2 * half * k / steps),
            centre.y + radius * math.cos(azimuth - half + 2 * half * k / steps)) for k in range(steps + 1)]
    return shapely.Polygon([(centre.x, centre.y), *arc])


def sectors(centre, zone, ring_width: float, min_area: float = 0.0) -> list:
    """Split a zone into a central disc and rings x 8 directions around ``centre``.

    The first ring (0 - ring_width) is one central sector. Pieces smaller than
    ``min_area`` (at the edge of the zone) are merged into the sector just inside them.
    Returns dicts: direction ('C' for the centre), ring_min, ring_max (metres), geometry.
    """
    max_dist = shapely.hausdorff_distance(centre, zone.boundary) + ring_width
    result = [{"direction": "C", "ring_min": 0, "ring_max": ring_width,
               "geometry": centre.buffer(ring_width, 64).intersection(zone)}]
    inner = {}
    r = ring_width
    while r < max_dist:
        ring = centre.buffer(r + ring_width, 64).difference(centre.buffer(r, 64)).intersection(zone)
        for i, d in enumerate(DIRECTIONS_8):
            piece = ring.intersection(direction_wedge(centre, i, 8, (r + ring_width) * 2))
            if piece.is_empty:
                continue
            if piece.area < min_area and d in inner:
                inner[d]["geometry"] = unary_union([inner[d]["geometry"], piece])
                inner[d]["ring_max"] = r + ring_width
                continue
            sector = {"direction": d, "ring_min": r, "ring_max": r + ring_width, "geometry": piece}
            result.append(sector)
            inner[d] = sector
        r += ring_width
    return result
