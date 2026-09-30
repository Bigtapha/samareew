"""Pure NumPy post-processing: no Earth Engine needed, so it can be unit-tested."""
import numpy as np
import pandas as pd

NODATA_IN = 255   # no clear Sentinel-2 observation for that year
NODATA_OUT = -1   # never observed


def urbanisation_year(stack: np.ndarray, years: list, persistence_ratio: float) -> np.ndarray:
    """Year in which each pixel became built-up, with a temporal consistency rule.

    Parameters
    ----------
    stack : array (n_years, rows, cols) with 1 = built, 0 = not built, 255 = no data
    years : list of years matching the first axis of ``stack``
    persistence_ratio : a pixel is urbanised in year Y if it is built in Y and in at
        least this share of the valid years from Y to the end, and if its most recent
        valid observation is built (urbanisation is considered irreversible).

    Returns
    -------
    int16 array (rows, cols): the urbanisation year, 0 if not built at the end of
    the period, -1 if the pixel was never observed.
    """
    if stack.shape[0] != len(years):
        raise ValueError("stack must have one band per year")

    valid = stack != NODATA_IN
    built = stack == 1

    # Suffix sums: number of built / valid years from index i to the end
    built_after = np.flip(np.cumsum(np.flip(built, 0), 0), 0)
    valid_after = np.flip(np.cumsum(np.flip(valid, 0), 0), 0)

    # Status at the most recent valid observation
    last_status = np.zeros(stack.shape[1:], dtype=bool)
    for i in range(len(years)):
        last_status = np.where(valid[i], built[i], last_status)

    persistent = built & (built_after >= persistence_ratio * valid_after)
    candidate = persistent & last_status[np.newaxis]

    has_year = candidate.any(axis=0)
    first_index = candidate.argmax(axis=0)
    result = np.where(has_year, np.asarray(years)[first_index], 0).astype(np.int16)
    result[~valid.any(axis=0)] = NODATA_OUT
    return result


def area_by_year(first_year: np.ndarray, years: list, pixel_area_m2: float) -> pd.DataFrame:
    """Cumulative built-up area and new built-up area per year, in hectares."""
    rows = []
    previous = 0.0
    for year in years:
        n_pixels = np.count_nonzero((first_year > 0) & (first_year <= year))
        area_ha = n_pixels * pixel_area_m2 / 10_000
        rows.append({"year": year,
                     "built_area_ha": round(area_ha, 1),
                     "new_built_ha": round(area_ha - previous, 1) if year != years[0] else 0.0})
        previous = area_ha
    df = pd.DataFrame(rows)
    first = df["built_area_ha"].iloc[0]
    df["growth_since_start_pct"] = ((df["built_area_ha"] / first - 1) * 100).round(1) if first else np.nan
    return df


def period_index(first_year: np.ndarray, periods: list) -> np.ndarray:
    """Map urbanisation years to legend classes: 0 = none, 1..n = period number."""
    out = np.zeros(first_year.shape, dtype=np.uint8)
    for i, (start, end, _label) in enumerate(periods, start=1):
        out[(first_year >= start) & (first_year <= end)] = i
    return out
