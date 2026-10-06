import pytest

from src.gee_utils import season_dates


@pytest.mark.parametrize("start, end, expected", [
    ("11-01", "05-31", ("2015-11-01", "2016-05-31")),   # season starts the previous year
    ("01-01", "05-31", ("2016-01-01", "2016-05-31")),   # season within the year
])
def test_season_dates(start, end, expected):
    assert season_dates(2016, start, end) == expected
