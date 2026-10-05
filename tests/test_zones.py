import pytest
from shapely.geometry import Point, box

from src import zones as zn


def test_overlapping_buffers_are_split_halfway():
    clusters = {"a": box(0, 0, 10, 10), "b": box(20, 0, 30, 10)}   # 10 m apart
    z = zn.study_zones(clusters, buffer_m=8)
    assert z["a"].intersection(z["b"]).area == pytest.approx(0, abs=1e-6)
    assert z["a"].bounds[2] == pytest.approx(15, abs=1)              # halfway line
    assert z["b"].bounds[0] == pytest.approx(15, abs=1)
    assert z["a"].contains(clusters["a"])


def test_zone_is_clipped_to_land():
    land = box(-100, -100, 5, 100)
    z = zn.study_zones({"a": box(0, 0, 10, 10)}, buffer_m=5, land=land)
    assert z["a"].bounds[2] == pytest.approx(5)


def test_remove_overlaps_smallest_wins():
    big, small = box(0, 0, 10, 10), box(2, 2, 4, 4)
    new_big, new_small = zn.remove_overlaps([big, small])
    assert new_small.equals(small)
    assert new_big.area == pytest.approx(100 - 4)
    assert new_big.intersection(new_small).area == pytest.approx(0)


@pytest.mark.parametrize("raw, expected", [
    ("Commune de Grand-Dakar", "Grand-Dakar"),
    ("Communauté rurale de Fandène", "Fandène"),
    ("Commune du Golf Sud", "Golf Sud"),
    ("Commune d'Ndiass", "Ndiass"),
    ("M'bour", "M'bour"),
])
def test_clean_name(raw, expected):
    assert zn.clean_name(raw) == expected


def test_relation_polygon_with_hole():
    def way(coords, role):
        return {"type": "way", "role": role, "geometry": [{"lon": x, "lat": y} for x, y in coords]}
    element = {"members": [
        way([(0, 0), (10, 0), (10, 10)], "outer"),
        way([(10, 10), (0, 10), (0, 0)], "outer"),           # outer ring split in two ways
        way([(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)], "inner"),
    ]}
    poly = zn.relation_polygon(element)
    assert poly.area == pytest.approx(100 - 4)
    assert not poly.contains(Point(5, 5))


def test_sectors_cover_the_zone_without_overlap():
    centre, zone = Point(0, 0), box(-9000, -5000, 7000, 6000)
    secs = zn.sectors(centre, zone, ring_width=2000, min_area=500_000)
    total = sum(s["geometry"].area for s in secs)
    assert total == pytest.approx(zone.area, rel=1e-6)                  # no gap, no overlap
    assert secs[0]["direction"] == "C" and secs[0]["ring_max"] == 2000  # one central sector
    assert {s["direction"] for s in secs[1:]} == set(zn.DIRECTIONS_8)
    assert min(s["geometry"].area for s in secs) >= 500_000             # slivers merged inward


def test_north_sector_points_north():
    secs = zn.sectors(Point(0, 0), box(-10000, -10000, 10000, 10000), ring_width=2000)
    north = [s for s in secs if s["direction"] == "N" and s["ring_min"] == 2000][0]
    c = north["geometry"].centroid
    assert c.y > 2000 and abs(c.x) < 100
