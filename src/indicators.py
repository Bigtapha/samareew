"""Indicators from the urbanisation-year map: pure NumPy / SciPy, no Earth Engine needed.

Every function works on a city grid (rows, cols) of 10 m pixels in a projected CRS:
``first_year`` is the output of ``postprocess.urbanisation_year`` (year a pixel became
built, 0 = not built, -1 = never observed / outside the study zone) and ``labels`` gives
the spatial unit of each pixel (0 .. n_units - 1, -1 = no unit).
"""
import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve

# Growth types (Atlas of Urban Expansion, Angel et al.)
NO_GROWTH, DENSIFICATION, EXTENSION, LEAPFROG = 0, 1, 2, 3
GROWTH_TYPES = {DENSIFICATION: "densification", EXTENSION: "extension", LEAPFROG: "leapfrog"}

EIGHT_CONNECTED = np.ones((3, 3), dtype=bool)
EARTH_RADIUS_M = 6_371_007.2  # authalic radius: sphere with the area of the WGS84 ellipsoid


def built_counts(first_year: np.ndarray, labels: np.ndarray, n_units: int, years: list) -> tuple:
    """Built-up pixels per unit at the end of each year, and observed pixels per unit.

    Returns (built, land): ``built`` is (n_units, n_years), cumulative; ``land`` is
    (n_units,), the pixels of each unit inside the study zone.
    """
    inside = (labels >= 0) & (first_year >= 0)
    unit = labels[inside].astype(np.int64)
    year = first_year[inside]
    n_years = len(years)
    # Index of the urbanisation year; n_years for "not built" (and years after the last one)
    year_index = np.full(year.shape, n_years, dtype=np.int64)
    built = (year > 0) & (year <= years[-1])
    year_index[built] = np.searchsorted(years, year[built])
    counts = np.bincount(unit * (n_years + 1) + year_index, minlength=n_units * (n_years + 1))
    counts = counts.reshape(n_units, n_years + 1)
    return counts[:, :n_years].cumsum(axis=1), np.bincount(unit, minlength=n_units)


def unit_sums(values: np.ndarray, labels: np.ndarray, n_units: int, mask=None) -> np.ndarray:
    """Sum of ``values`` per unit (pixels with label -1, or outside ``mask``, are ignored)."""
    keep = labels >= 0 if mask is None else (labels >= 0) & mask
    return np.bincount(labels[keep].astype(np.int64), weights=values[keep], minlength=n_units)


def built_share_in_circle(built: np.ndarray, observed: np.ndarray, radius_px: float) -> np.ndarray:
    """Share of built pixels among the observed pixels of a circle around every pixel.

    Unobserved pixels (sea, outside the zone) are left out of the share. 0 where the circle
    has no observed pixel.
    """
    r = int(np.floor(radius_px))
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    disc = (x * x + y * y <= radius_px * radius_px).astype(np.float32)
    n_built = fftconvolve(built.astype(np.float32), disc, mode="same")
    n_observed = fftconvolve(observed.astype(np.float32), disc, mode="same")
    return np.where(n_observed > 0.5, n_built / np.maximum(n_observed, 1), 0.0)


def urban_footprint(built: np.ndarray, observed: np.ndarray, pixel_size: float,
                    fringe_m: float, max_hole_ha: float) -> np.ndarray:
    """Built-up area + its fringe + the open spaces it encloses (Atlas of Urban Expansion).

    ``built`` is the urban built-up area (see ``growth_types``):
    - fringe: open land within ``fringe_m`` of a built pixel;
    - enclosed open space: an open patch (4-connected) smaller than ``max_hole_ha`` that
      touches neither the edge of the grid nor an unobserved pixel (sea, outside the zone).
    """
    near = ndimage.distance_transform_edt(~built, sampling=pixel_size) <= fringe_m
    footprint = built | (near & observed)
    patches, n = ndimage.label(~footprint)
    if n == 0:
        return footprint
    open_to_outside = np.zeros(n + 1, dtype=bool)
    edges = np.concatenate([patches[0], patches[-1], patches[:, 0], patches[:, -1],
                            patches[~observed]])
    open_to_outside[edges] = True
    small = np.bincount(patches.ravel(), minlength=n + 1) * pixel_size ** 2 <= max_hole_ha * 10_000
    enclosed = small & ~open_to_outside
    enclosed[0] = False  # label 0 is the footprint itself
    return footprint | enclosed[patches]


def growth_types(first_year: np.ndarray, start: int, end: int, pixel_size: float,
                 fringe_m: float, max_hole_ha: float, radius_m: float, min_share: float) -> np.ndarray:
    """Type of every pixel built after ``start`` and up to ``end`` (uint8, see GROWTH_TYPES).

    The urban footprint of ``start`` is drawn around its urban and suburban built-up area
    only: built pixels with at least ``min_share`` built land in a circle of ``radius_m``
    (Atlas: 25 % in 1 km²). Scattered rural buildings are left out, otherwise their fringe
    would cover most of the periphery at 10 m.
    - densification: inside the urban footprint of ``start`` (``urban_footprint``);
    - extension: outside it, in a new patch (8-connected) that touches it;
    - leapfrog: in a new patch that does not touch it.
    """
    observed = first_year >= 0
    built = (first_year > 0) & (first_year <= start)
    new = (first_year > start) & (first_year <= end)
    urban = built & (built_share_in_circle(built, observed, radius_m / pixel_size) >= min_share)
    footprint = urban_footprint(urban, observed, pixel_size, fringe_m, max_hole_ha)

    result = np.zeros(first_year.shape, dtype=np.uint8)
    result[new & footprint] = DENSIFICATION
    outside = new & ~footprint
    patches, n = ndimage.label(outside, structure=EIGHT_CONNECTED)
    touches = np.zeros(n + 1, dtype=bool)
    touches[patches[ndimage.binary_dilation(footprint, structure=EIGHT_CONNECTED) & outside]] = True
    result[outside] = np.where(touches[patches[outside]], EXTENSION, LEAPFROG)
    return result


def direction_ring_labels(shape: tuple, transform, centre_xy: tuple, ring_width: float,
                          n_directions: int = 8) -> tuple:
    """Direction (0 = north, clockwise) and distance ring (0 = first ring) of every pixel centre.

    ``transform`` is an affine transform of a north-up grid (rasterio ``Affine``).
    Directions are wedges centred on their azimuth, as in ``zones.sectors``.
    """
    x = transform.c + (np.arange(shape[1], dtype=np.float64) + 0.5) * transform.a
    y = transform.f + (np.arange(shape[0], dtype=np.float64) + 0.5) * transform.e
    dx = (x - centre_xy[0])[np.newaxis, :]
    dy = (y - centre_xy[1])[:, np.newaxis]
    azimuth = np.degrees(np.arctan2(dx, dy)) % 360
    step = 360 / n_directions
    direction = ((azimuth + step / 2) // step).astype(np.int32) % n_directions
    ring = (np.hypot(dx, dy) // ring_width).astype(np.int32)
    return direction, ring


def cell_areas_m2(top_lat: float, res_deg: float, n_rows: int) -> np.ndarray:
    """Area (m²) of the cells of each row of a north-up lon/lat grid, on the authalic sphere."""
    edges = np.radians(top_lat - res_deg * np.arange(n_rows + 1))
    return EARTH_RADIUS_M ** 2 * np.radians(res_deg) * np.abs(np.diff(np.sin(edges)))


def sdg_11_3_1(built_start: float, built_end: float, pop_start: float, pop_end: float) -> float:
    """SDG 11.3.1: ratio of land consumption rate to population growth rate.

    Both rates are ln(end / start) / n_years, so the number of years cancels out.
    > 1: built-up area grows faster than population (the city spreads out). NaN when the
    ratio has no meaning (zero values, population not growing).
    """
    if min(built_start, built_end, pop_start, pop_end) <= 0 or pop_end <= pop_start:
        return float("nan")
    return float(np.log(built_end / built_start) / np.log(pop_end / pop_start))
