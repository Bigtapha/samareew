"""Step 7 - Site data: everything the site reads besides the indicator tables (ROADMAP §4.2).

The site (J5) reads only outputs/. This step puts there, in light formats for slow mobile
connections:

1. the map layers (config.settings SITE_LAYERS) as raster tiles in one PMTiles archive per
   layer, for the four cities: paletted PNG in Web Mercator, zooms SITE_MIN_ZOOM to
   SITE_MAX_ZOOM (14 is about the 10 m pixel); lower zooms keep the most common class;
2. the boundaries (zones, communes, Touba sectors, centres) as simplified GeoJSON, with the
   same unit names as outputs/tables/units.csv;
3. the validation results the site shows (accuracy and corrected areas, by city);
4. a manifest listing files, layers, legends, cities and licences.

Inputs : outputs/cities/<city>/urbanisation_year.tif, growth_type_<start>_<end>.tif (steps 3-4)
         zones/*.geojson (step 0), outputs/validation/accuracy.json (step 5)
Outputs: outputs/site/tiles/<layer>.pmtiles      (ignored by git: rebuilt by this step)
         outputs/site/boundaries/*.geojson
         outputs/site/validation.json, outputs/site/manifest.json
         data/j5_tiles_<layer>.png               control map of the tiles read back

Usage
    python -m pipeline.s7_site_data
"""
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


# --- 3. Validation summary -------------------------------------------------------------

def build_validation() -> dict:
    report = json.loads(cfg.VALIDATION_REPORT_JSON.read_text())
    out = {"date": report["date"], "period": report["period"],
           "method": "METHODOLOGIE.md#14",
           "note": ("Précisions pondérées par la surface, marges à 95 %. Les tableaux et les cartes "
                    "gardent les valeurs de la carte ; les surfaces corrigées sont publiées à côté."),
           "cities": {c: sd.validation_summary(r, START, END) for c, r in report["cities"].items()},
           "national": sd.validation_summary(report["national"], START, END)}
    cfg.SITE_VALIDATION_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


# --- 4. Manifest -----------------------------------------------------------------------

def build_manifest(layers: dict, boundaries: dict) -> None:
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
        "boundaries": boundaries,
        "validation": "validation.json",
    }
    cfg.SITE_MANIFEST_JSON.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))


def main() -> None:
    zones = gpd.read_file(cfg.ZONES_GEOJSON)
    layers = {}
    for name, layer in cfg.SITE_LAYERS.items():
        stats = build_layer(name, layer)
        layers[name] = stats
        print(f"{name}: {sum(stats['tiles'].values())} tiles, {stats['bytes'] / 1e6:.1f} MB "
              f"(per zoom: {stats['tiles']})")
        print(check_layer(name, layer, zones).to_string(index=False))
    boundaries = build_boundaries()
    print(check_boundaries().to_string(index=False))
    validation = build_validation()
    print(f"validation: {len(validation['cities'])} cities + national")
    build_manifest(layers, boundaries)
    print(f"-> {cfg.SITE_DATA_DIR}")


if __name__ == "__main__":
    main()
