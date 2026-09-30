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
