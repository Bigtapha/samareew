import numpy as np
import pytest

from src import postprocess as pp

YEARS = [2016, 2017, 2018, 2019, 2020]


def pixel(series):
    """Build a (n_years, 1, 1) stack from a list of yearly values."""
    return np.array(series, dtype=np.uint8).reshape(-1, 1, 1)


@pytest.mark.parametrize("series, expected", [
    ([0, 0, 0, 0, 0], 0),            # never built
    ([1, 1, 1, 1, 1], 2016),         # built from the start
    ([0, 0, 1, 1, 1], 2018),         # built in 2018
    ([0, 1, 0, 0, 0], 0),            # one-year noise is ignored
    ([0, 1, 0, 1, 1], 2019),         # 2017 not persistent enough (2/4 < 0.8)
    ([0, 0, 1, 255, 1], 2018),       # a missing year does not break the series
    ([0, 0, 1, 1, 0], 0),            # not built at the end -> not urbanised
    ([255, 255, 255, 255, 255], -1), # never observed
])
def test_urbanisation_year(series, expected):
    assert pp.urbanisation_year(pixel(series), YEARS, 0.8)[0, 0] == expected


@pytest.mark.parametrize("series, expected", [
    ([0, 1, 0, 1, 1, 1, 1, 1, 1, 1], 2019),        # 2017 passes 80 % (8/9) but 2018 is not built
    ([0, 1, 255, 1, 1, 1, 1, 1, 1, 1], 2017),      # next valid year after 2017 is 2019: built
    ([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], 2025),        # last year: no next year to check
])
def test_next_valid_year_must_be_built(series, expected):
    years = list(range(2016, 2026))
    assert pp.urbanisation_year(pixel(series), years, 0.8)[0, 0] == expected


def test_next_year_condition_can_be_switched_off():
    years = list(range(2016, 2026))
    series = [0, 1, 0, 1, 1, 1, 1, 1, 1, 1]                  # dry-year false detection in 2017
    assert pp.urbanisation_year(pixel(series), years, 0.8, confirm_next=False)[0, 0] == 2017


def test_wrong_number_of_bands():
    with pytest.raises(ValueError):
        pp.urbanisation_year(pixel([0, 1]), YEARS, 0.8)


def test_area_by_year():
    first_year = np.array([[2016, 2018], [0, 2018]], dtype=np.int16)
    df = pp.area_by_year(first_year, YEARS, pixel_area_m2=10_000)  # 1 ha pixels
    assert df["built_area_ha"].tolist() == [1.0, 1.0, 3.0, 3.0, 3.0]
    assert df["new_built_ha"].tolist() == [0.0, 0.0, 2.0, 0.0, 0.0]


def test_period_index():
    periods = [(2016, 2016, "a"), (2017, 2018, "b")]
    first_year = np.array([0, 2016, 2017, 2018, 2019])
    assert pp.period_index(first_year, periods).tolist() == [0, 1, 2, 2, 0]
