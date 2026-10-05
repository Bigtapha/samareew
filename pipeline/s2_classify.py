"""Step 2 - Google Earth Engine: yearly built-up maps of every city with the national model.

The national Random Forest is trained again from data/training_samples.csv (step 1),
so it is exactly the model evaluated in step 1.

Outputs, in data/cities/<city>/
- built_by_year.tif     one band per year, 1 = built-up, 0 = not built, 255 = no data
- image_counts.json     number of Sentinel-2 scenes per season (quality check)

Usage
    python -m pipeline.s2_classify                  # every city, direct download (geemap)
    python -m pipeline.s2_classify --city touba     # one city
    python -m pipeline.s2_classify --drive          # or export the stacks to Google Drive
"""
import argparse
import json

import ee
import pandas as pd

import config as cfg
from pipeline.s1_train import train_classifier
from src import gee_utils as gu


def classify_all_years(zone, classifier):
    """Classify every year and stack the results into one multi-band image."""
    layers = []
    for year in cfg.YEARS:
        composite = gu.seasonal_composite(zone, year, cfg.SEASON_START,
                                          cfg.SEASON_END, cfg.CLOUD_SCORE_THRESHOLD)
        built = (composite.select(gu.FEATURE_BANDS).classify(classifier)
                 .unmask(255).toByte().rename(f"built_{year}"))
        layers.append(built)
    # Outside the study zone (but inside its bounding box) -> 255 = no data
    return ee.Image.cat(layers).clip(zone).unmask(255, False)


def run_city(city: str, classifier, to_drive: bool) -> None:
    out_dir = cfg.city_data_dir(city)
    out_dir.mkdir(parents=True, exist_ok=True)
    zone = gu.city_zone(cfg, city)

    counts = {y: gu.count_images(zone, y, cfg.SEASON_START, cfg.SEASON_END) for y in cfg.YEARS}
    (out_dir / cfg.IMAGE_COUNTS_JSON).write_text(json.dumps(counts, indent=2))
    print(f"  Sentinel-2 scenes per season: {counts}")

    stack = classify_all_years(zone, classifier)
    if to_drive:
        name = f"built_by_year_{city}"
        ee.batch.Export.image.toDrive(
            image=stack, description=name, fileNamePrefix=name, region=zone.bounds(maxError=1),
            scale=cfg.SCALE, crs=cfg.ANALYSIS_CRS, maxPixels=1e10).start()
        print(f"  export started: download {name}.tif from Google Drive to {out_dir / cfg.BUILT_STACK_TIF}")
    else:
        import geemap  # imported here: only needed for direct download
        path = out_dir / cfg.BUILT_STACK_TIF
        geemap.download_ee_image(stack, str(path), region=zone.bounds(maxError=1),
                                 crs=cfg.ANALYSIS_CRS, scale=cfg.SCALE, dtype="uint8")
        print(f"  saved {path}")


def main(cities: list, to_drive: bool):
    if not cfg.TRAINING_SAMPLES_CSV.exists():
        raise SystemExit(f"{cfg.TRAINING_SAMPLES_CSV} not found: run python -m pipeline.s1_train first")
    gu.init(cfg.GEE_PROJECT)
    classifier = train_classifier(pd.read_csv(cfg.TRAINING_SAMPLES_CSV))
    for city in cities:
        print(f"Classifying {city} {cfg.YEARS[0]}-{cfg.YEARS[-1]}...")
        run_city(city, classifier, to_drive)
    print("Done. Next: python -m pipeline.s3_postprocess")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", choices=list(cfg.CITIES), help="only this city (default: all)")
    parser.add_argument("--drive", action="store_true", help="export the stacks to Google Drive")
    args = parser.parse_args()
    main([args.city] if args.city else list(cfg.CITIES), args.drive)
