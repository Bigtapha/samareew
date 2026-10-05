import numpy as np
import pandas as pd
import pytest

from src import validation as va

NAMES = {0: "not built", 1: "built at start", 2: "new built-up"}


def test_map_classes():
    first_year = np.array([[0, 2016, 2019, -1]])
    assert va.map_classes(first_year, 2016).tolist() == [[0, 1, 2, -1]]


def test_stratified_pixels_caps_at_available():
    classes = np.array([[0, 0, 0, 1]])
    picks = va.stratified_pixels(classes, {0: 2, 1: 5, 2: 3}, np.random.default_rng(0))
    assert len(picks[0][0]) == 2 and len(picks[1][0]) == 1 and 2 not in picks


def test_area_weighted_accuracy():
    # Stratum 0 covers 90 % of the map and is always right; stratum 2 (10 %) is right half the time
    points = pd.DataFrame({"map_class": [0, 0, 2, 2], "ref_class": [0, 0, 2, 0]})
    weights = {0: 0.9, 1: 0.0, 2: 0.1}
    report = va.accuracy_report(points, weights, NAMES)
    assert report["overall_accuracy"] == pytest.approx(0.75)
    assert report["area_weighted_overall_accuracy"] == pytest.approx(0.9 * 1 + 0.1 * 0.5)
