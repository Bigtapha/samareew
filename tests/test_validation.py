import math

import numpy as np
import pandas as pd
import pytest

from src import validation as va


def test_map_classes():
    first_year = np.array([[0, 2016, 2019, 2025, 2026, -1]])
    assert va.map_classes(first_year, 2016, 2025).tolist() == [[0, 1, 2, 2, 0, -1]]


def test_strata_codes_split_new_built_by_growth_type():
    classes = np.array([[0, 1, 2, 2, 2, -1]])
    growth = np.array([[0, 0, 1, 2, 3, 0]])
    names = list(va.STRATA)
    codes = va.strata_codes(classes, growth)
    assert [names[c] for c in codes[0, :5]] == list(va.STRATA)
    assert codes[0, 5] == -1
    with pytest.raises(ValueError):
        va.strata_codes(classes, np.zeros_like(growth))


def test_stratified_pixels_caps_at_available():
    codes = np.array([[0, 0, 0, 1]])
    picks = va.stratified_pixels(codes, {"not_built": 2, "built_at_start": 5, "leapfrog": 3},
                                 np.random.default_rng(0))
    assert len(picks["not_built"][0]) == 2 and len(picks["built_at_start"][0]) == 1
    assert "leapfrog" not in picks


def test_reference_class():
    assert va.reference_class([0, 1, 0, 1], [0, 1, 1, 0]).tolist() == [
        va.NOT_BUILT, va.BUILT_AT_START, va.NEW_BUILT, va.NOT_BUILT]


def test_stratified_mean_weights_strata_by_area():
    # Stratum a covers 90 % of the map and is always right; stratum b (10 %) half the time
    points = pd.DataFrame({"stratum": ["a", "a", "b", "b"], "y": [1, 1, 1, 0]})
    est, se = va.stratified_mean(points, {"a": 0.9, "b": 0.1}, "y")
    assert est == pytest.approx(0.9 + 0.1 * 0.5)
    assert se == pytest.approx(math.sqrt(0.1 ** 2 * 0.5 / 2))   # sample variance of [1, 0] = 0.5
    with pytest.raises(ValueError):
        va.stratified_mean(points[points["stratum"] == "a"], {"a": 0.9, "b": 0.1}, "y")


def test_stratified_ratio_equals_proportion_ratio():
    points = pd.DataFrame({"stratum": ["a"] * 4 + ["b"] * 4,
                           "y": [1, 0, 0, 0, 1, 1, 0, 0], "x": [1, 1, 0, 0, 1, 1, 1, 1]})
    weights = {"a": 0.75, "b": 0.25}
    r, se = va.stratified_ratio(points, weights, "y", "x")
    assert r == pytest.approx((0.75 * 0.25 + 0.25 * 0.5) / (0.75 * 0.5 + 0.25 * 1.0))
    assert se > 0
    # Constant ratio in every stratum: no uncertainty
    same = points.assign(y=points["x"])
    assert va.stratified_ratio(same, weights, "y", "x") == pytest.approx((1.0, 0.0))


def test_accuracy_report():
    points = pd.DataFrame({
        "stratum":   ["not_built"] * 4 + ["built_at_start"] * 2 + ["leapfrog"] * 2,
        "map_class": [0, 0, 0, 0, 1, 1, 2, 2],
        "ref_class": [0, 0, 0, 2, 1, 1, 2, 0],
    })
    weights = {"not_built": 0.8, "built_at_start": 0.15, "leapfrog": 0.05}
    report = va.accuracy_report(points, weights, total_area_ha=1000)
    assert report["overall_accuracy"]["estimate"] == pytest.approx(0.8 * 0.75 + 0.15 + 0.05 * 0.5, abs=1e-3)
    assert report["users_accuracy"]["new_built"]["estimate"] == pytest.approx(0.5)
    # New built-up in reality: 1/4 of the not-built stratum + 1/2 of the leapfrog stratum
    assert report["area_ha"]["new_built"]["estimate"] == pytest.approx(1000 * (0.8 / 4 + 0.05 / 2))
    assert report["mapped_area_ha"] == {"not_built": 800, "built_at_start": 150, "new_built": 50}
    # Producer's accuracy of new built-up: found 0.025 of 0.225
    assert report["producers_accuracy"]["new_built"]["estimate"] == pytest.approx(0.025 / 0.225, abs=1e-3)


def test_date_accuracy_ignores_timing_errors():
    points = pd.DataFrame({
        "stratum":   ["not_built"] * 2 + ["leapfrog"] * 2,
        "map_class": [0, 0, 2, 2],
        # Second leapfrog point: built in 2016 already, so wrong class but right at the end
        "ref_start": [0, 0, 0, 1],
        "ref_end":   [0, 1, 1, 1],
    })
    weights = {"not_built": 0.9, "leapfrog": 0.1}
    acc = va.date_accuracy(points, weights)
    assert acc["end"]["estimate"] == pytest.approx(0.9 * 0.5 + 0.1)
    assert acc["start"]["estimate"] == pytest.approx(0.9 + 0.1 * 0.5)


def test_tolerant_built():
    built = [1, 0, 0, 0]
    cover = [None, "subdivision", "bare_soil", None]
    assert va.tolerant_built(built, cover, ("subdivision", "construction")).tolist() == [1, 1, 0, 0]


def test_class_shares():
    points = pd.DataFrame({
        "stratum":   ["not_built"] * 2 + ["leapfrog"] * 2 + ["extension"] * 2,
        "map_class": [0, 0, 2, 2, 2, 2],
        "kind":      ["a", "a", "b", "c", "b", "b"],
    })
    weights = {"not_built": 0.8, "leapfrog": 0.1, "extension": 0.1}
    shares = va.class_shares(points, weights, 2, "kind")
    # New built-up: half of leapfrog and all of extension are "b"
    assert shares["b"]["estimate"] == pytest.approx(0.75)
    assert shares["c"]["estimate"] == pytest.approx(0.25)
    assert "a" not in shares


def test_log_interval_is_skewed_upwards():
    low, high = va.log_interval(2.0, 0.4)
    assert low > 2.0 - 1.96 * 0.4 and high > 2.0 + 1.96 * 0.4
    assert math.isclose(low * high, 4.0)                    # symmetric on the log scale
    assert all(math.isnan(v) for v in va.log_interval(0.0, 0.1))


def test_growth_estimate():
    # One stratum: half the points built at the start, all built at the end -> growth +100 %
    points = pd.DataFrame({"stratum": ["a"] * 4, "b0": [1, 1, 0, 0], "b1": [1, 1, 1, 1]})
    g = va.growth_estimate(points, {"a": 1.0}, "b0", "b1")
    assert g["estimate"] == 1.0 and g["low95"] < 1.0 < g["high95"]


def test_growth_difference():
    a = {"estimate": 1.0, "log_se": 0.1}                     # factor 2
    b = {"estimate": 0.0, "log_se": 0.1}                     # factor 1
    d = va.growth_difference(a, b)
    assert math.isclose(d["factor_ratio"], 2.0) and d["established"]
    assert d["low95"] > 1.0
    assert not va.growth_difference(a, {"estimate": 0.8, "log_se": 0.3})["established"]
