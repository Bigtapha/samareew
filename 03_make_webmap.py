"""Step 3 - Prepare the interactive web map (docs/, published with GitHub Pages).

Reprojects the urbanisation map to Web Mercator, writes one transparent PNG per
period (so each period can be switched on/off in the map) and a meta.json file
with the legend, statistics and accuracy figures read by docs/index.html.
"""
import json
import shutil

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds

import config as cfg
from src import postprocess as pp


def to_web_mercator(src_path):
    """Reproject the urbanisation raster onto the AOI bounding box in EPSG:3857."""
    west, south, east, north = aoi_bounds()
    left, bottom, right, top = transform_bounds("EPSG:4326", "EPSG:3857", west, south, east, north)
    width = int(round((right - left) / cfg.SCALE))
    height = int(round((top - bottom) / cfg.SCALE))
    dst = np.full((height, width), pp.NODATA_OUT, dtype=np.int16)
    with rasterio.open(src_path) as src:
        reproject(source=rasterio.band(src, 1), destination=dst,
                  dst_transform=from_bounds(left, bottom, right, top, width, height),
                  dst_crs="EPSG:3857", dst_nodata=pp.NODATA_OUT,
                  resampling=Resampling.nearest)
    return dst


def aoi_bounds():
    """Bounding box of the study area saved by step 1 (west, south, east, north)."""
    b = json.loads(cfg.AOI_BOUNDS_JSON.read_text())
    return b["west"], b["south"], b["east"], b["north"]


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def write_period_pngs(first_year_3857):
    classes = pp.period_index(first_year_3857, cfg.PERIODS)
    files = []
    for i, color in enumerate(cfg.PERIOD_COLORS, start=1):
        rgba = np.zeros(classes.shape + (4,), dtype=np.uint8)
        rgba[classes == i] = (*hex_to_rgb(color), 255)
        name = f"period_{i}.png"
        Image.fromarray(rgba, "RGBA").save(cfg.WEB_DATA_DIR / name, optimize=True)
        files.append(f"data/{name}")
    return files


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def main():
    cfg.WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    first_year = to_web_mercator(cfg.FIRST_YEAR_TIF)
    period_files = write_period_pngs(first_year)

    rgb = {}
    for key, year in (("first", cfg.YEARS[0]), ("last", cfg.YEARS[-1])):
        src = cfg.DATA_DIR / f"rgb_{year}.png"
        if src.exists():
            shutil.copy(src, cfg.WEB_DATA_DIR / src.name)
            rgb[key] = {"year": year, "file": f"data/{src.name}"}

    stats = pd.read_csv(cfg.STATS_CSV)
    gee_acc = read_json(cfg.ACCURACY_JSON)
    validation = read_json(cfg.OUTPUT_DIR / "accuracy_validation.json")

    boundary = None
    if cfg.AOI_BOUNDARY_GEOJSON.exists():
        shutil.copy(cfg.AOI_BOUNDARY_GEOJSON, cfg.WEB_DATA_DIR / "aoi_boundary.geojson")
        boundary = "data/aoi_boundary.geojson"

    west, south, east, north = aoi_bounds()
    meta = {
        "aoi_name": cfg.AOI_NAME,
        "bounds": [[south, west], [north, east]],
        "boundary": boundary,
        "years": [cfg.YEARS[0], cfg.YEARS[-1]],
        "periods": [{"label": p[2], "color": c, "file": f}
                    for p, c, f in zip(cfg.PERIODS, cfg.PERIOD_COLORS, period_files)],
        "rgb": rgb,
        "stats": stats.to_dict(orient="records"),
        "accuracy_reference": (None if gee_acc is None else
                               {"overall_accuracy": gee_acc["overall_accuracy"],
                                "kappa": gee_acc["kappa"], "n_test": gee_acc["n_test"]}),
        "accuracy_validation": validation,
    }
    (cfg.WEB_DATA_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Web map data written to {cfg.WEB_DATA_DIR}")
    print("Preview: python -m http.server --directory docs  ->  http://localhost:8000")


if __name__ == "__main__":
    main()
