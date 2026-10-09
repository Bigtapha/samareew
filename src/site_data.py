"""Site data (step 7): map tiles, boundaries and validation summary in the exchange format.

Pure functions (NumPy, Pillow, shapely), so they can be unit-tested. Tiles follow the usual
Web Mercator scheme (EPSG:3857, 256 px, x from the west, y from the north), as read by
MapLibre GL from a PMTiles archive.
"""
import io
import math

import numpy as np
from affine import Affine
from PIL import Image

TILE_PX = 256
EARTH_RADIUS = 6378137.0
ORIGIN = math.pi * EARTH_RADIUS            # half the width of the Web Mercator square
TRANSPARENT = 0


def tile_size_m(z: int) -> float:
    """Width of one tile at zoom ``z``, in Web Mercator metres."""
    return 2 * ORIGIN / 2 ** z


def tile_range(bounds: tuple, z: int) -> tuple:
    """Tiles (x0, y0, x1, y1), inclusive, covering ``bounds`` = (minx, miny, maxx, maxy) in
    Web Mercator metres."""
    size = tile_size_m(z)
    minx, miny, maxx, maxy = bounds
    n = 2 ** z - 1
    x0 = min(max(int((minx + ORIGIN) // size), 0), n)
    x1 = min(max(int((maxx + ORIGIN) // size), 0), n)
    y0 = min(max(int((ORIGIN - maxy) // size), 0), n)
    y1 = min(max(int((ORIGIN - miny) // size), 0), n)
    return x0, y0, x1, y1


def mosaic_transform(z: int, x0: int, y0: int) -> Affine:
    """Affine transform of a mosaic of tiles whose top-left tile is (x0, y0) at zoom ``z``."""
    res = tile_size_m(z) / TILE_PX
    return Affine(res, 0, -ORIGIN + x0 * tile_size_m(z), 0, -res, ORIGIN - y0 * tile_size_m(z))


def split_tiles(mosaic: np.ndarray, x0: int, y0: int):
    """Yield (x, y, tile) for every 256 px tile of the mosaic that is not fully transparent.
    The mosaic holds classes (rows, cols) or colours (rows, cols, bands), 0 where empty."""
    rows, cols = mosaic.shape[:2]
    if rows % TILE_PX or cols % TILE_PX:
        raise ValueError("the mosaic must be a whole number of tiles")
    for i in range(rows // TILE_PX):
        for j in range(cols // TILE_PX):
            tile = mosaic[i * TILE_PX:(i + 1) * TILE_PX, j * TILE_PX:(j + 1) * TILE_PX]
            if tile.any():
                yield x0 + j, y0 + i, tile


def overlay(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    """Tile of two cities: the pixels of ``top`` that are not transparent win (class tiles,
    or RGBA tiles where the last band is the alpha)."""
    if top.ndim == 3:
        return np.where(top[..., -1:] > 0, top, base)
    return np.where(top != TRANSPARENT, top, base)


def period_classes(first_year: np.ndarray, breaks: tuple) -> np.ndarray:
    """Class of each pixel from its urbanisation year: 1 = built in ``breaks[0]`` or before,
    then k for a year in (breaks[k-2], breaks[k-1]]; 0 = not built, no data or built after
    the last break."""
    classes = np.zeros(first_year.shape, dtype=np.uint8)
    built = first_year > 0
    classes[built & (first_year <= breaks[0])] = 1
    for k in range(1, len(breaks)):
        classes[built & (first_year > breaks[k - 1]) & (first_year <= breaks[k])] = k + 1
    return classes


def encode_png(tile: np.ndarray, colors: dict) -> bytes:
    """Paletted PNG of a class tile; class 0 is transparent. ``colors``: {class: "#rrggbb"}."""
    if tile.max() >= 256:
        raise ValueError("classes must fit in one byte")
    palette = [0, 0, 0] * 256
    for code, hex_color in colors.items():
        palette[3 * code:3 * code + 3] = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    image = Image.fromarray(tile.astype(np.uint8), mode="P")
    image.putpalette(palette)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True, transparency=TRANSPARENT)
    return out.getvalue()


def stretch_rgba(reflectance: np.ndarray, stretch: tuple, gamma: float) -> np.ndarray:
    """8-bit RGBA image (rows, cols, 4) from reflectance bands (3, rows, cols), 0-1.

    ``stretch`` = (low, high) reflectance mapped to 0 and 255, the same for the three bands
    so that colours stay natural; ``gamma`` > 1 lightens dark tones. NaN pixels (no data)
    are transparent, every other pixel is opaque.
    """
    low, high = stretch
    valid = np.all(np.isfinite(reflectance), axis=0)
    scaled = np.clip((np.nan_to_num(reflectance) - low) / (high - low), 0, 1) ** (1 / gamma)
    rgba = np.zeros(reflectance.shape[1:] + (4,), dtype=np.uint8)
    rgba[..., :3] = np.round(np.moveaxis(scaled, 0, -1) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0)
    rgba[~valid, :3] = 0
    return rgba


def encode_webp(tile: np.ndarray, quality: int) -> bytes:
    """WebP of an RGBA tile; fully opaque tiles are stored without the alpha band."""
    opaque = bool((tile[..., 3] == 255).all())
    image = Image.fromarray(tile[..., :3] if opaque else tile, mode="RGB" if opaque else "RGBA")
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=quality, method=6)
    return out.getvalue()


def crop_to_classes(classes: np.ndarray, margin: int, factor: int) -> tuple:
    """Row and column slices around the non-zero pixels, plus ``margin`` pixels, with sizes
    rounded up to a multiple of ``factor`` (the crop may run past the raster: pad it)."""
    rows, cols = np.nonzero(classes)
    if not len(rows):
        raise ValueError("no class pixel to crop to")
    r0, c0 = rows.min() - margin, cols.min() - margin
    r1, c1 = rows.max() + 1 + margin, cols.max() + 1 + margin
    r1 = r0 + -(-(r1 - r0) // factor) * factor
    c1 = c0 + -(-(c1 - c0) // factor) * factor
    return slice(r0, r1), slice(c0, c1)


def footprint_rgba(classes: np.ndarray, factor: int, colors: dict) -> np.ndarray:
    """Small RGBA picture of a class raster, ``factor`` times coarser: each output pixel takes
    the colour of its most common class and an opacity equal to its share of class pixels,
    so that sparse built-up areas look lighter rather than disappearing or filling up.

    ``classes`` (rows and cols multiples of ``factor``) holds codes 0 (empty) to n;
    ``colors`` = {code: "#rrggbb"}.
    """
    rows, cols = classes.shape
    if rows % factor or cols % factor:
        raise ValueError("the raster must be a whole number of blocks")
    blocks = classes.reshape(rows // factor, factor, cols // factor, factor).swapaxes(1, 2)
    codes = sorted(colors)
    counts = np.stack([(blocks == c).sum(axis=(2, 3)) for c in codes])      # (n, rows', cols')
    total = counts.sum(axis=0)
    rgba = np.zeros(total.shape + (4,), dtype=np.uint8)
    palette = np.array([[int(colors[c][i:i + 2], 16) for i in (1, 3, 5)] for c in codes], dtype=np.uint8)
    rgba[..., :3] = palette[counts.argmax(axis=0)]
    rgba[..., 3] = np.round(255 * total / factor ** 2).astype(np.uint8)
    rgba[total == 0, :3] = 0
    return rgba


def encode_footprint_png(rgba: np.ndarray, colors: dict, levels: int) -> bytes:
    """Paletted PNG of a footprint: the exact class colours, each at ``levels`` opacities
    (index 0 transparent). Much smaller than RGBA for a picture with few colours."""
    codes = sorted(colors)
    rgb = np.array([[int(colors[c][i:i + 2], 16) for i in (1, 3, 5)] for c in codes], dtype=np.uint8)
    match = (rgba[..., None, :3] == rgb).all(axis=-1)                 # (rows, cols, n)
    level = np.round(rgba[..., 3].astype(float) / 255 * levels).astype(int)   # 0 .. levels
    index = np.where((level > 0) & match.any(axis=-1), 1 + match.argmax(axis=-1) * levels + level - 1, 0)
    palette, alpha = [0, 0, 0], [0]
    for color in rgb:
        for k in range(1, levels + 1):
            palette += color.tolist()
            alpha.append(round(255 * k / levels))
    image = Image.fromarray(index.astype(np.uint8), mode="P")
    image.putpalette(palette + [0, 0, 0] * (256 - len(palette) // 3))
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True, transparency=bytes(alpha))
    return out.getvalue()


def ground_pixel_area_m2(z: int, lat: np.ndarray) -> np.ndarray:
    """Ground area of one tile pixel at zoom ``z`` and latitude ``lat`` (degrees): Web Mercator
    stretches distances by 1 / cos(lat)."""
    res = tile_size_m(z) / TILE_PX
    return (res * np.cos(np.radians(lat))) ** 2


def mercator_to_lat(y: np.ndarray) -> np.ndarray:
    """Latitude (degrees) of Web Mercator northings."""
    return np.degrees(2 * np.arctan(np.exp(np.asarray(y) / EARTH_RADIUS)) - math.pi / 2)


# --- Validation summary ------------------------------------------------------------

def validation_summary(report: dict, start: int, end: int) -> dict:
    """What the site shows of one accuracy report of step 5 (a city or the four cities):
    accuracies and corrected areas with their 95 % margins, next to the mapped areas."""
    mapped = report["mapped_area_ha"]
    out = {
        "n_points": report["n_points"],
        "unsure_labels": report.get("unsure_labels"),
        "overall_accuracy": report["overall_accuracy"],
        "built_accuracy": {str(start): report["date_accuracy"]["start"],
                           str(end): report["date_accuracy"]["end"]},
        "new_built": {
            "users_accuracy": report["users_accuracy"]["new_built"],
            "producers_accuracy": report["producers_accuracy"]["new_built"],
            "mapped_ha": mapped["new_built"],
            "corrected_ha": report["area_ha"]["new_built"],
        },
        "built_area": {
            str(start): {"mapped_ha": mapped["built_at_start"],
                         "corrected_ha": report["built_area_ha"][str(start)]},
            str(end): {"mapped_ha": mapped["built_at_start"] + mapped["new_built"],
                       "corrected_ha": report["built_area_ha"][str(end)]},
        },
    }
    tolerant = report.get("tolerant")
    if tolerant:
        out["new_built"]["users_accuracy_tolerant"] = tolerant["users_accuracy"]["new_built"]
        out["new_built"]["cover_in_reality"] = tolerant["cover_of_map_class"]["new_built"]
    return out
