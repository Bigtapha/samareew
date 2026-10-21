"""Step 7 - Site data: everything the site reads besides the indicator tables (ROADMAP §4.2).

The site (J5) reads only outputs/. This step puts there, in light formats for slow mobile
connections:

1. the map layers (config.settings SITE_LAYERS) as raster tiles in one PMTiles archive per
   layer, for the four cities: paletted PNG in Web Mercator, zooms SITE_MIN_ZOOM to
   SITE_MAX_ZOOM (14 is about the 10 m pixel); lower zooms keep the most common class;
2. the boundaries (zones, communes, Touba sectors, centres) as simplified GeoJSON, with the
   same unit names as outputs/tables/units.csv;
3. the validation results the site shows (accuracy and corrected areas, by city), and the
   known errors outlined on the maps (config/map_notes.py) with their weight in the figures;
4. a manifest listing files, layers, legends, cities and licences;
5. the city footprints at the same scale (home page): one small paletted PNG per city;
6. the satellite image shown under the layers on request: the true-colour Sentinel-2
   composite of SITE_IMAGE_YEAR (same season and cloud mask as the classification) over the
   bounding box of each zone, downloaded once from Earth Engine, as WebP tiles.

Inputs : outputs/cities/<city>/urbanisation_year.tif, growth_type_<start>_<end>.tif (steps 3-4)
         zones/*.geojson (step 0), outputs/validation/accuracy.json (step 5)
         Earth Engine (once per city): data/cities/<city>/true_colour_<year>.tif
Outputs: outputs/site/tiles/<layer>.pmtiles      (ignored by git: rebuilt by this step)
         outputs/site/footprints/<city>.png
         outputs/site/boundaries/*.geojson
         outputs/site/map_notes.geojson
         outputs/site/validation.json, outputs/site/manifest.json
         data/j5_tiles_<layer>.png               control map of the tiles read back

Usage
    python -m pipeline.s7_site_data              # uses the cached image downloads when present
    python -m pipeline.s7_site_data --refresh    # download the satellite image again
    python -m pipeline.s7_site_data --drive dakar   # export one city's image to Google Drive
                                                    # (when Earth Engine refuses direct downloads)
"""
import argparse
import io
import json
from datetime import date

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import shapely
from PIL import Image
from scipy import ndimage
from pmtiles.reader import MmapSource, Reader
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import write
from rasterio.warp import Resampling, reproject, transform_bounds

import config as cfg
from src import site_data as sd

MERCATOR = "EPSG:3857"
UTM = "EPSG:32628"
START, END = cfg.VALIDATION_PERIOD
OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
SAMAREEW_ATTRIBUTION = "SamaReew (CC BY 4.0), Sentinel-2 (Copernicus)"
IMAGE_ATTRIBUTION = f"Contient des données Copernicus Sentinel modifiées ({cfg.SITE_IMAGE_YEAR}), SamaReew"


# --- 1. Map tiles ----------------------------------------------------------------------

def layer_classes(city: str, layer: dict) -> tuple:
    """Class raster of one city for one layer, with its transform and CRS."""
    out_dir = cfg.city_output_dir(city)
    if layer["source"] == "urbanisation_year":
        with rasterio.open(out_dir / cfg.FIRST_YEAR_TIF) as src:
            classes = sd.period_classes(src.read(1), layer["breaks"])
            return classes, src.transform, src.crs
    start, end = layer["period"]
    with rasterio.open(out_dir / cfg.GROWTH_TYPE_TIF.format(start=start, end=end)) as src:
        return src.read(1).astype(np.uint8), src.transform, src.crs


def city_mosaic(classes, transform, crs, z: int) -> tuple:
    """The city's classes on the tile grid of zoom ``z``: (mosaic, x0, y0)."""
    rows, cols = classes.shape
    bounds = transform_bounds(crs, MERCATOR, *rasterio.transform.array_bounds(rows, cols, transform))
    x0, y0, x1, y1 = sd.tile_range(bounds, z)
    mosaic = np.zeros(((y1 - y0 + 1) * sd.TILE_PX, (x1 - x0 + 1) * sd.TILE_PX), dtype=np.uint8)
    reproject(classes, mosaic, src_transform=transform, src_crs=crs,
              dst_transform=sd.mosaic_transform(z, x0, y0), dst_crs=MERCATOR,
              resampling=Resampling.nearest if z == cfg.SITE_MAX_ZOOM else Resampling.mode)
    return mosaic, x0, y0


def build_layer(name: str, layer: dict) -> dict:
    """Write outputs/site/tiles/<name>.pmtiles; return its statistics."""
    colors = {code: color for code, _, color in layer["classes"]}
    rasters = {city: layer_classes(city, layer) for city in cfg.CITIES}
    encoded, stats = {}, {"tiles": {}, "bytes": 0}
    for z in range(cfg.SITE_MIN_ZOOM, cfg.SITE_MAX_ZOOM + 1):
        tiles = {}
        for city, (classes, transform, crs) in rasters.items():
            mosaic, x0, y0 = city_mosaic(classes, transform, crs, z)
            for x, y, tile in sd.split_tiles(mosaic, x0, y0):
                tiles[(x, y)] = sd.overlay(tiles[(x, y)], tile) if (x, y) in tiles else tile.copy()
        for (x, y), tile in tiles.items():
            encoded[zxy_to_tileid(z, x, y)] = sd.encode_png(tile, colors)
        stats["tiles"][z] = len(tiles)

    bounds = [transform_bounds(crs, "EPSG:4326", *rasterio.transform.array_bounds(*c.shape, t))
              for c, t, crs in rasters.values()]
    west, south = min(b[0] for b in bounds), min(b[1] for b in bounds)
    east, north = max(b[2] for b in bounds), max(b[3] for b in bounds)
    cfg.SITE_TILES_DIR.mkdir(parents=True, exist_ok=True)
    path = cfg.SITE_TILES_DIR / f"{name}.pmtiles"
    with write(path) as writer:
        for tile_id in sorted(encoded):
            writer.write_tile(tile_id, encoded[tile_id])
        e7 = lambda v: int(round(v * 1e7))
        writer.finalize(
            {"tile_type": TileType.PNG, "tile_compression": Compression.NONE,
             "min_lon_e7": e7(west), "min_lat_e7": e7(south), "max_lon_e7": e7(east), "max_lat_e7": e7(north),
             "center_zoom": cfg.SITE_MIN_ZOOM, "center_lon_e7": e7((west + east) / 2),
             "center_lat_e7": e7((south + north) / 2)},
            {"name": name, "description": layer["title"], "attribution": SAMAREEW_ATTRIBUTION,
             "legend": [{"code": c, "label": l, "color": col} for c, l, col in layer["classes"]]})
    stats["bytes"] = path.stat().st_size
    stats["bounds"] = [round(v, 5) for v in (west, south, east, north)]
    return stats


def read_back(name: str, z: int, bounds: tuple) -> tuple:
    """Mosaic of the classes stored in the archive at zoom ``z`` over ``bounds`` (Web Mercator)."""
    x0, y0, x1, y1 = sd.tile_range(bounds, z)
    mosaic = np.zeros(((y1 - y0 + 1) * sd.TILE_PX, (x1 - x0 + 1) * sd.TILE_PX), dtype=np.uint8)
    with open(cfg.SITE_TILES_DIR / f"{name}.pmtiles", "rb") as f:
        reader = Reader(MmapSource(f))
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                data = reader.get(z, x, y)
                if data:
                    tile = np.array(Image.open(io.BytesIO(data)))
                    mosaic[(y - y0) * sd.TILE_PX:(y - y0 + 1) * sd.TILE_PX,
                           (x - x0) * sd.TILE_PX:(x - x0 + 1) * sd.TILE_PX] = tile
    return mosaic, x0, y0


def check_layer(name: str, layer: dict, zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Read the archive back at the highest zoom: area of each class by city (ha), against the
    same count on the 10 m source rasters, and a control map."""
    rows = []
    fig, axes = plt.subplots(1, len(cfg.CITIES), figsize=(5 * len(cfg.CITIES), 5.5))
    zones_m = zones.to_crs(MERCATOR)
    for ax, city in zip(axes, cfg.CITIES):
        classes, transform, crs = layer_classes(city, layer)
        bounds = transform_bounds(crs, MERCATOR, *rasterio.transform.array_bounds(*classes.shape, transform))
        mosaic, x0, y0 = read_back(name, cfg.SITE_MAX_ZOOM, bounds)
        t = sd.mosaic_transform(cfg.SITE_MAX_ZOOM, x0, y0)
        # Keep the pixels of this city only (neighbouring zones can share a tile)
        inside = rasterio.features.geometry_mask(zones_m[zones_m["city"] == city].geometry,
                                                 mosaic.shape, t, invert=True)
        ys = t.f + t.e * (np.arange(mosaic.shape[0]) + 0.5)
        area = sd.ground_pixel_area_m2(cfg.SITE_MAX_ZOOM, sd.mercator_to_lat(ys))[:, None]
        pixel_ha = abs(transform.a * transform.e) / 10_000
        for code, label, _ in layer["classes"]:
            rows.append({"city": city, "class": label,
                         "tiles_ha": round(float((area * ((mosaic == code) & inside)).sum()) / 10_000, 1),
                         "source_ha": round(float((classes == code).sum() * pixel_ha), 1)})
        rgba = np.zeros(mosaic.shape + (4,))
        for code, _, color in layer["classes"]:
            rgba[mosaic == code] = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)] + [1]
        extent = [t.c, t.c + t.a * mosaic.shape[1], t.f + t.e * mosaic.shape[0], t.f]
        ax.imshow(rgba, extent=extent, interpolation="nearest")
        zones_m[zones_m["city"] == city].boundary.plot(ax=ax, color="black", linewidth=0.6)
        ax.set_title(cfg.CITIES[city]["name"])
        ax.set_axis_off()
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in layer["classes"]]
    fig.legend(handles, [l for _, l, _ in layer["classes"]], loc="lower center", ncol=len(handles))
    fig.suptitle(f"{layer['title']} — tuiles relues au zoom {cfg.SITE_MAX_ZOOM}")
    fig.savefig(cfg.DATA_DIR / f"j5_tiles_{name}.png", dpi=110)
    plt.close(fig)
    out = pd.DataFrame(rows)
    out["gap_pct"] = (100 * (out["tiles_ha"] / out["source_ha"] - 1)).round(2)
    return out


# --- 1b. Satellite image -----------------------------------------------------------------

IMAGE_NAME = cfg.SITE_IMAGE_NAME.format(year=cfg.SITE_IMAGE_YEAR)


def zone_box_utm(city: str) -> tuple:
    zones = gpd.read_file(cfg.ZONES_GEOJSON).to_crs(UTM)
    return tuple(zones[zones["city"] == city].total_bounds)


def image_path(city: str):
    return cfg.city_data_dir(city) / cfg.SITE_IMAGE_TIF.format(year=cfg.SITE_IMAGE_YEAR)


def true_colour_image(city: str) -> tuple:
    """Earth Engine image of the true-colour composite (reflectance x 10000, 0 = no data)
    over the zone's bounding box, and that box."""
    import ee
    from src import gee_utils as gu
    gu.init(cfg.GEE_PROJECT)
    box = ee.Geometry.Rectangle(list(zone_box_utm(city)), UTM, False)
    image = (gu.seasonal_composite(box, cfg.SITE_IMAGE_YEAR, cfg.SEASON_START, cfg.SEASON_END,
                                   cfg.CLOUD_SCORE_THRESHOLD)
             .select(cfg.SITE_IMAGE_BANDS).multiply(10000).round().unmask(0).toUint16())
    return image, box


def download_image(city: str, refresh: bool) -> None:
    """Direct download of the composite into data/cities/<city>/ (cached)."""
    path = image_path(city)
    if path.exists() and not refresh:
        return
    import geemap
    image, box = true_colour_image(city)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written under another name first: a failed download must not pass for a cached one.
    # Few parallel requests: the noncommercial tier limits concurrency (HTTP 429).
    partial = path.with_suffix(".partial.tif")
    try:
        geemap.download_ee_image(image, str(partial), region=box, crs=cfg.ANALYSIS_CRS, scale=cfg.SCALE,
                                 dtype="uint16", max_tile_size=cfg.DOWNLOAD_MAX_TILE_MB,
                                 num_threads=cfg.DOWNLOAD_THREADS)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(path)


def export_image_to_drive(city: str) -> None:
    """Earth Engine export task to Google Drive, when direct downloads are refused (quota)."""
    import ee
    image, box = true_colour_image(city)
    name = f"{image_path(city).stem}_{city}"
    ee.batch.Export.image.toDrive(image=image, description=name, fileNamePrefix=name, region=box,
                                  scale=cfg.SCALE, crs=cfg.ANALYSIS_CRS, maxPixels=1e10).start()
    print(f"export started: when the task is done (https://code.earthengine.google.com/tasks), "
          f"download {name}.tif from Google Drive to {image_path(city)}")


def image_rgba(city: str) -> tuple:
    """8-bit RGBA image of one city (bands first), with its transform and CRS."""
    path = cfg.city_data_dir(city) / cfg.SITE_IMAGE_TIF.format(year=cfg.SITE_IMAGE_YEAR)
    with rasterio.open(path) as src:
        raw = src.read().astype(np.float32)
        transform, crs = src.transform, src.crs
    raw[:, (raw == 0).all(axis=0)] = np.nan
    rgba = sd.stretch_rgba(raw / 10000, cfg.SITE_IMAGE_STRETCH, cfg.SITE_IMAGE_GAMMA)
    return np.moveaxis(rgba, -1, 0), transform, crs


def image_mosaic(rgba, transform, crs, z: int) -> tuple:
    """The city's image on the tile grid of zoom ``z``: (mosaic rows x cols x 4, x0, y0)."""
    bounds = transform_bounds(crs, MERCATOR, *rasterio.transform.array_bounds(*rgba.shape[1:], transform))
    x0, y0, x1, y1 = sd.tile_range(bounds, z)
    mosaic = np.zeros((4, (y1 - y0 + 1) * sd.TILE_PX, (x1 - x0 + 1) * sd.TILE_PX), dtype=np.uint8)
    reproject(rgba, mosaic, src_transform=transform, src_crs=crs,
              dst_transform=sd.mosaic_transform(z, x0, y0), dst_crs=MERCATOR,
              resampling=Resampling.bilinear if z == cfg.SITE_MAX_ZOOM else Resampling.average)
    mosaic[3] = np.where(mosaic[3] >= 128, 255, 0)    # no half-transparent edges
    mosaic[:3, mosaic[3] == 0] = 0
    return np.moveaxis(mosaic, 0, -1), x0, y0


def build_image(refresh: bool) -> dict:
    """Write outputs/site/tiles/sentinel2_<year>.pmtiles; return its statistics. A city whose
    image cannot be downloaded is left out with a warning (the site shows the others)."""
    rasters, missing = {}, []
    for city in cfg.CITIES:
        try:
            download_image(city, refresh)
        except Exception as error:                      # quota, network: keep the other cities
            print(f"WARNING {city}: satellite image not downloaded ({type(error).__name__}); "
                  f"try again later or: python -m pipeline.s7_site_data --drive {city}")
            missing.append(city)
            continue
        rasters[city] = image_rgba(city)
    encoded, stats = {}, {"tiles": {}, "bytes": 0}
    for z in range(cfg.SITE_MIN_ZOOM, cfg.SITE_MAX_ZOOM + 1):
        tiles = {}
        for city, (rgba, transform, crs) in rasters.items():
            mosaic, x0, y0 = image_mosaic(rgba, transform, crs, z)
            for x, y, tile in sd.split_tiles(mosaic, x0, y0):
                tiles[(x, y)] = sd.overlay(tiles[(x, y)], tile) if (x, y) in tiles else tile.copy()
        for (x, y), tile in tiles.items():
            encoded[zxy_to_tileid(z, x, y)] = sd.encode_webp(tile, cfg.SITE_IMAGE_QUALITY)
        stats["tiles"][z] = len(tiles)
        if z == cfg.SITE_MAX_ZOOM - 2:
            image_control_map(tiles, z)

    bounds = [transform_bounds(crs, "EPSG:4326", *rasterio.transform.array_bounds(*r.shape[1:], t))
              for r, t, crs in rasters.values()]
    west, south = min(b[0] for b in bounds), min(b[1] for b in bounds)
    east, north = max(b[2] for b in bounds), max(b[3] for b in bounds)
    path = cfg.SITE_TILES_DIR / f"{IMAGE_NAME}.pmtiles"
    cfg.SITE_TILES_DIR.mkdir(parents=True, exist_ok=True)
    with write(path) as writer:
        for tile_id in sorted(encoded):
            writer.write_tile(tile_id, encoded[tile_id])
        e7 = lambda v: int(round(v * 1e7))
        writer.finalize(
            {"tile_type": TileType.WEBP, "tile_compression": Compression.NONE,
             "min_lon_e7": e7(west), "min_lat_e7": e7(south), "max_lon_e7": e7(east), "max_lat_e7": e7(north),
             "center_zoom": cfg.SITE_MIN_ZOOM, "center_lon_e7": e7((west + east) / 2),
             "center_lat_e7": e7((south + north) / 2)},
            {"name": IMAGE_NAME, "attribution": IMAGE_ATTRIBUTION})
    stats["bytes"] = path.stat().st_size
    stats["bounds"] = [round(v, 5) for v in (west, south, east, north)]
    sizes = [len(b) for b in encoded.values()]
    stats["mean_tile_kb"] = round(sum(sizes) / len(sizes) / 1024, 1)
    stats["cities"], stats["missing"] = list(rasters), missing
    return stats


def image_control_map(tiles: dict, z: int) -> None:
    """All tiles of one zoom side by side: data/j5_tiles_sentinel2_<year>.png."""
    xs, ys = [x for x, _ in tiles], [y for _, y in tiles]
    x0, y0 = min(xs), min(ys)
    canvas = np.full(((max(ys) - y0 + 1) * sd.TILE_PX, (max(xs) - x0 + 1) * sd.TILE_PX, 4), 255, dtype=np.uint8)
    for (x, y), tile in tiles.items():
        block = canvas[(y - y0) * sd.TILE_PX:(y - y0 + 1) * sd.TILE_PX, (x - x0) * sd.TILE_PX:(x - x0 + 1) * sd.TILE_PX]
        block[tile[..., 3] > 0] = tile[tile[..., 3] > 0]
    Image.fromarray(canvas[..., :3]).save(cfg.DATA_DIR / f"j5_tiles_{IMAGE_NAME}.png")


# --- 1c. Footprints at the same scale ---------------------------------------------------

def build_footprints() -> dict:
    """One picture per city of the "urbanisation" classes, SITE_FOOTPRINT_M metres per pixel,
    cropped to the built-up area: outputs/site/footprints/<city>.png."""
    layer = cfg.SITE_LAYERS["urbanisation"]
    colors = {code: color for code, _, color in layer["classes"]}
    out_dir = cfg.SITE_DATA_DIR / "footprints"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for city in cfg.CITIES:
        classes, transform, _ = layer_classes(city, layer)
        pixel_m = abs(transform.a)
        factor = int(round(cfg.SITE_FOOTPRINT_M / pixel_m))
        rows, cols = sd.crop_to_classes(classes, int(cfg.SITE_FOOTPRINT_MARGIN_M / pixel_m), factor)
        pad = max(0, -rows.start, -cols.start, rows.stop - classes.shape[0], cols.stop - classes.shape[1])
        padded = np.pad(classes, pad)
        crop = padded[rows.start + pad:rows.stop + pad, cols.start + pad:cols.stop + pad]
        rgba = sd.footprint_rgba(crop, factor, colors)
        path = out_dir / f"{city}.png"
        path.write_bytes(sd.encode_footprint_png(rgba, colors, cfg.SITE_FOOTPRINT_LEVELS))
        # Check: the picture keeps the built-up area (opacity = share of built-up pixels)
        area_ha = float(rgba[..., 3].astype(float).sum() / 255 * cfg.SITE_FOOTPRINT_M ** 2 / 10_000)
        source_ha = float((classes > 0).sum() * pixel_m ** 2 / 10_000)
        files[city] = {"file": f"footprints/{city}.png", "width_px": rgba.shape[1], "height_px": rgba.shape[0],
                       "width_km": round(rgba.shape[1] * cfg.SITE_FOOTPRINT_M / 1000, 2),
                       "height_km": round(rgba.shape[0] * cfg.SITE_FOOTPRINT_M / 1000, 2),
                       "kb": round(path.stat().st_size / 1024, 1),
                       "area_gap_pct": round(100 * (area_ha / source_ha - 1), 2)}
    return files


# --- 2. Boundaries ---------------------------------------------------------------------

def simplify(gdf: gpd.GeoDataFrame, coverage: bool) -> gpd.GeoDataFrame:
    """Simplify in metres, city by city; a coverage (communes, sectors) keeps shared edges."""
    g = gdf.to_crs(UTM)
    parts = []
    for _, group in g.groupby("city", sort=False):
        geoms = group.geometry.values
        geoms = shapely.coverage_simplify(geoms, cfg.SITE_SIMPLIFY_M) if coverage \
            else shapely.simplify(geoms, cfg.SITE_SIMPLIFY_M, preserve_topology=True)
        parts.append(group.set_geometry(geoms))
    g = gpd.GeoDataFrame(pd.concat(parts), crs=UTM).to_crs("EPSG:4326")
    g["geometry"] = shapely.set_precision(g.geometry.values, 10 ** -cfg.SITE_COORD_DECIMALS)
    return g


def write_geojson(gdf: gpd.GeoDataFrame, columns: list, path) -> None:
    features = [{"type": "Feature", "properties": {c: row[c] for c in columns},
                 "geometry": shapely.geometry.mapping(row.geometry)}
                for _, row in gdf.iterrows()]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build_boundaries() -> dict:
    out = cfg.SITE_BOUNDARIES_DIR
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    zones = gpd.read_file(cfg.ZONES_GEOJSON)
    zones["unit_type"], zones["unit"], zones["label"] = "city", zones["city"], zones["name"]
    communes = gpd.read_file(cfg.ZONES_DIR / "communes.geojson")
    communes["unit_type"], communes["unit"], communes["label"] = "commune", communes["commune"], communes["commune"]
    sectors = gpd.read_file(cfg.ZONES_DIR / "sectors.geojson")
    sectors["unit_type"], sectors["unit"] = "sector", sectors["sector"]
    columns = ["city", "unit_type", "unit", "label"]
    for name, gdf, coverage, licence in [("zones", zones, False, "CC BY 4.0"),
                                         ("communes", communes, True, "ODbL 1.0"),
                                         ("sectors", sectors, True, "CC BY 4.0")]:
        simple = simplify(gdf, coverage)
        if not simple.geometry.is_valid.all() or simple.geometry.is_empty.any():
            raise ValueError(f"{name}: invalid or empty geometry after simplification")
        write_geojson(simple, columns, out / f"{name}.geojson")
        files[name] = {"file": f"boundaries/{name}.geojson", "licence": licence,
                       "attribution": OSM_ATTRIBUTION if licence.startswith("ODbL") else SAMAREEW_ATTRIBUTION,
                       "features": len(simple)}
    centres = gpd.read_file(cfg.ZONES_DIR / "centres.geojson")
    centres["geometry"] = shapely.set_precision(centres.geometry.values, 10 ** -cfg.SITE_COORD_DECIMALS)
    write_geojson(centres, ["city", "landmark"], out / "centres.geojson")
    files["centres"] = {"file": "boundaries/centres.geojson", "licence": "CC BY 4.0",
                        "attribution": SAMAREEW_ATTRIBUTION, "features": len(centres)}
    return files


def check_boundaries() -> pd.DataFrame:
    """Area of each unit before and after simplification (km²), and unit names against the tables."""
    units = pd.read_csv(cfg.UNITS_CSV)
    rows = []
    for name, source in [("zones", cfg.ZONES_GEOJSON), ("communes", cfg.ZONES_DIR / "communes.geojson"),
                         ("sectors", cfg.ZONES_DIR / "sectors.geojson")]:
        before = gpd.read_file(source).to_crs(UTM)
        after = gpd.read_file(cfg.SITE_BOUNDARIES_DIR / f"{name}.geojson").to_crs(UTM)
        known = set(zip(units["city"], units["unit_type"], units["unit"].astype(str)))
        missing = [u for u in zip(after["city"], after["unit_type"], after["unit"].astype(str)) if u not in known]
        if missing:
            raise ValueError(f"{name}: units unknown to {cfg.UNITS_CSV.name}: {missing[:5]}")
        gap = (after.area.values / before.area.values - 1) * 100
        # Shared edges: the union of a coverage must not gain holes or overlaps
        overlap = after.groupby("city").apply(lambda g: g.area.sum() - g.union_all().area).sum() / 1e6
        rows.append({"layer": name, "features": len(after), "max_area_gap_pct": round(float(np.abs(gap).max()), 3),
                     "overlap_km2": round(float(overlap), 4),
                     "kb": round((cfg.SITE_BOUNDARIES_DIR / f"{name}.geojson").stat().st_size / 1024, 1),
                     "source_kb": round(source.stat().st_size / 1024, 1)})
    return pd.DataFrame(rows)


# --- 2b. Map notes ---------------------------------------------------------------------

def build_notes() -> dict:
    """Known errors of the map (config/map_notes.py): outline of the mapped built-up area
    inside the box of each note, and its weight in the figures of the city."""
    features = []
    for note in cfg.MAP_NOTES:
        with rasterio.open(cfg.city_output_dir(note["city"]) / cfg.FIRST_YEAR_TIF) as src:
            first_year, transform, crs = src.read(1), src.transform, src.crs
        box = shapely.box(*transform_bounds("EPSG:4326", crs, *note["bounds"]))
        inside = rasterio.features.geometry_mask([box], first_year.shape, transform, invert=True)
        stats = sd.note_stats(first_year, inside, START, END, abs(transform.a * transform.e))
        block = ndimage.binary_closing((first_year > 0) & inside, iterations=cfg.SITE_NOTE_CLOSE_PX)
        block = ndimage.binary_fill_holes(block) & inside
        parts = [shapely.geometry.shape(g) for g, v in
                 rasterio.features.shapes(block.astype(np.uint8), mask=block, transform=transform) if v]
        parts = [p for p in parts if p.area >= cfg.SITE_NOTE_MIN_PART_HA * 10_000]
        outline = shapely.union_all(parts).buffer(cfg.SITE_NOTE_MARGIN_M).simplify(cfg.SITE_SIMPLIFY_M)
        outline = gpd.GeoSeries([outline], crs=crs).to_crs("EPSG:4326").iloc[0]
        outline = shapely.set_precision(outline, 10 ** -cfg.SITE_COORD_DECIMALS)
        if outline.is_empty or not outline.is_valid:
            raise ValueError(f"{note['id']}: empty or invalid outline")
        point = outline.representative_point()
        properties = {k: note[k] for k in ("id", "city", "kind", "title", "evidence", "reported")}
        properties |= stats | {"period": [START, END], "lon": round(point.x, 5), "lat": round(point.y, 5)}
        features.append({"type": "Feature", "properties": properties,
                         "geometry": shapely.geometry.mapping(outline)})
    cfg.SITE_NOTES_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                                 ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"file": cfg.SITE_NOTES_GEOJSON.name, "licence": "CC BY 4.0", "attribution": SAMAREEW_ATTRIBUTION,
            "kinds": {"false_detection": "Fausse détection connue"},
            "notes": [f["properties"] for f in features]}


# --- 3. Validation summary -------------------------------------------------------------

def build_validation() -> dict:
    report = json.loads(cfg.VALIDATION_REPORT_JSON.read_text())
    out = {"date": report["date"], "period": report["period"],
           "method": "METHODOLOGIE.md#14",
           "note": ("Précisions pondérées par la surface, marges à 95 %. Les tableaux et les cartes "
                    "gardent les valeurs de la carte ; les surfaces corrigées sont publiées à côté."),
           "cities": {c: sd.validation_summary(r, START, END) for c, r in report["cities"].items()},
           "national": sd.validation_summary(report["national"], START, END),
           # Pairs of cities: is one growing faster, once corrected? (95 %, METHODOLOGIE §14.4)
           "growth_comparison": report.get("growth_comparison", [])}
    cfg.SITE_VALIDATION_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


# --- 4. Manifest -----------------------------------------------------------------------

def build_manifest(layers: dict, image: dict, footprints: dict, boundaries: dict, notes: dict) -> None:
    zones = gpd.read_file(cfg.ZONES_GEOJSON)
    centres = gpd.read_file(cfg.ZONES_DIR / "centres.geojson")
    cities = {}
    for city in cfg.CITIES:
        z = zones[zones["city"] == city]
        c = centres[centres["city"] == city].geometry.iloc[0]
        cities[city] = {"name": cfg.CITIES[city]["name"],
                        "bounds": [round(v, 5) for v in z.total_bounds],
                        "centre": [round(c.x, 5), round(c.y, 5)]}
    manifest = {
        "format_version": cfg.FORMAT_VERSION,
        "generated": date.today().isoformat(),
        "cities": cities,
        "tables": {"indicators": "../tables/indicators.json", "values": "../tables/indicators.csv",
                   "units": "../tables/units.csv"},
        "layers": {name: {"title": layer["title"], "file": f"tiles/{name}.pmtiles", "type": "raster",
                          "tile_format": "png", "tile_size": sd.TILE_PX,
                          "min_zoom": cfg.SITE_MIN_ZOOM, "max_zoom": cfg.SITE_MAX_ZOOM,
                          "bounds": layers[name]["bounds"],
                          "legend": [{"code": c, "label": l, "color": col} for c, l, col in layer["classes"]],
                          "licence": "CC BY 4.0", "attribution": SAMAREEW_ATTRIBUTION}
                   for name, layer in cfg.SITE_LAYERS.items()},
        "images": {IMAGE_NAME: {
            "title": f"Image satellite {cfg.SITE_IMAGE_YEAR} (Sentinel-2)",
            "description": (f"Composite en couleurs naturelles de la saison sèche {cfg.SITE_IMAGE_YEAR} "
                            "(1er novembre - 31 mai), pixels de 10 m, celui qu'a classé le modèle"),
            "year": cfg.SITE_IMAGE_YEAR, "file": f"tiles/{IMAGE_NAME}.pmtiles", "type": "raster",
            "tile_format": "webp", "tile_size": sd.TILE_PX,
            "min_zoom": cfg.SITE_MIN_ZOOM, "max_zoom": cfg.SITE_MAX_ZOOM, "bounds": image["bounds"],
            "cities": image["cities"],
            "licence": "Copernicus (libre, attribution)", "attribution": IMAGE_ATTRIBUTION}},
        "footprints": {"layer": "urbanisation", "metres_per_pixel": cfg.SITE_FOOTPRINT_M,
                       "cities": {c: {k: f[k] for k in ("file", "width_px", "height_px", "width_km", "height_km")}
                                  for c, f in footprints.items()},
                       "licence": "CC BY 4.0", "attribution": SAMAREEW_ATTRIBUTION},
        "boundaries": boundaries,
        "notes": notes,
        "validation": "validation.json",
    }
    cfg.SITE_MANIFEST_JSON.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))


def main(refresh: bool) -> None:
    zones = gpd.read_file(cfg.ZONES_GEOJSON)
    layers = {}
    for name, layer in cfg.SITE_LAYERS.items():
        stats = build_layer(name, layer)
        layers[name] = stats
        print(f"{name}: {sum(stats['tiles'].values())} tiles, {stats['bytes'] / 1e6:.1f} MB "
              f"(per zoom: {stats['tiles']})")
        print(check_layer(name, layer, zones).to_string(index=False))
    footprints = build_footprints()
    print("footprints:", {c: f"{f['width_px']}x{f['height_px']} px, {f['kb']} kB, area {f['area_gap_pct']:+} %"
                          for c, f in footprints.items()})
    image = build_image(refresh)
    print(f"{IMAGE_NAME}: {sum(image['tiles'].values())} tiles, {image['bytes'] / 1e6:.1f} MB, "
          f"{image['mean_tile_kb']} kB per tile (per zoom: {image['tiles']})")
    boundaries = build_boundaries()
    print(check_boundaries().to_string(index=False))
    notes = build_notes()
    print("map notes:", {n["id"]: f"{n['mapped_ha']} ha, {n['share_of_new_built_pct']} % of the new built-up area, "
                                  f"growth {n['growth_pct']:+} % ({n['growth_without_pct']:+} % without)"
                         for n in notes["notes"]})
    validation = build_validation()
    print(f"validation: {len(validation['cities'])} cities + national")
    build_manifest(layers, image, footprints, boundaries, notes)
    print(f"-> {cfg.SITE_DATA_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="download the satellite image again")
    parser.add_argument("--drive", metavar="CITY", help="only start the export of this city's image to Google Drive")
    args = parser.parse_args()
    if args.drive:
        export_image_to_drive(args.drive)
    else:
        main(args.refresh)
