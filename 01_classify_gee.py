"""Step 1 - Google Earth Engine: composites, Random Forest classification, accuracy.

Outputs
- data/built_by_year.tif      one band per year, 1 = built-up, 0 = not built, 255 = no data
- data/rgb_<year>.png         true-colour composites for the web map (first and last year)
- outputs/accuracy_gee_test.json   confusion matrix and metrics on the 30 % test sample
- outputs/image_counts.json   number of Sentinel-2 scenes per season (quality check)

Usage
    python 01_classify_gee.py            # download results directly (geemap)
    python 01_classify_gee.py --drive    # or export the stack to Google Drive
"""
import argparse
import json

import ee
import requests

import config as cfg
from src import gee_utils as gu


def train_classifier(aoi):
    """Train a Random Forest on the training-year composite and evaluate it."""
    composite = gu.seasonal_composite(aoi, cfg.TRAINING_YEAR, cfg.SEASON_START,
                                      cfg.SEASON_END, cfg.CLOUD_SCORE_THRESHOLD)
    labels = gu.reference_labels(aoi, cfg.TRAINING_YEAR)

    samples = (labels.addBands(composite.select(gu.FEATURE_BANDS))
               .stratifiedSample(numPoints=cfg.POINTS_PER_CLASS, classBand="label",
                                 region=aoi, scale=cfg.SCALE, projection=ee.Projection(cfg.ANALYSIS_CRS),
                                 seed=cfg.SEED, geometries=True, tileScale=4)
               .randomColumn("random", cfg.SEED))

    train = samples.filter(ee.Filter.lt("random", cfg.TRAIN_FRACTION))
    test = samples.filter(ee.Filter.gte("random", cfg.TRAIN_FRACTION))

    classifier = (ee.Classifier.smileRandomForest(numberOfTrees=cfg.N_TREES, seed=cfg.SEED)
                  .train(features=train, classProperty="label",
                         inputProperties=gu.FEATURE_BANDS))

    matrix = test.classify(classifier).errorMatrix("label", "classification")
    report = ee.Dictionary({
        "n_train": train.size(),
        "n_test": test.size(),
        "confusion_matrix": matrix.array(),
        "overall_accuracy": matrix.accuracy(),
        "kappa": matrix.kappa(),
        "producers_accuracy": matrix.producersAccuracy(),
        "users_accuracy": matrix.consumersAccuracy(),
        "f1": matrix.fscore(),
        "feature_importance": classifier.explain().get("importance"),
    }).getInfo()
    report["note"] = ("Test labels come from WorldCover/Dynamic World agreement areas: "
                      "this measures agreement with reference products. See 04_validation.py "
                      "for an independent accuracy assessment on photo-interpreted points.")
    return classifier, report


def classify_all_years(aoi, classifier):
    """Classify every year and stack the results into one multi-band image."""
    layers = []
    for year in cfg.YEARS:
        composite = gu.seasonal_composite(aoi, year, cfg.SEASON_START,
                                          cfg.SEASON_END, cfg.CLOUD_SCORE_THRESHOLD)
        built = (composite.select(gu.FEATURE_BANDS).classify(classifier)
                 .unmask(255).toByte().rename(f"built_{year}"))
        layers.append(built)
    # Outside the study area (but inside its bounding box) -> 255 = no data
    return ee.Image.cat(layers).clip(aoi).unmask(255, False)


def download_rgb(aoi, year, path):
    composite = gu.seasonal_composite(aoi, year, cfg.SEASON_START,
                                      cfg.SEASON_END, cfg.CLOUD_SCORE_THRESHOLD)
    # Pixels outside the boundary are transparent in the PNG
    url = (composite.visualize(bands=["B4", "B3", "B2"], min=0.02, max=0.32, gamma=1.2)
           .getThumbURL({"region": aoi.bounds(maxError=1), "dimensions": 1600,
                         "format": "png", "crs": "EPSG:3857"}))
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    path.write_bytes(response.content)
    print(f"  saved {path}")


def save_aoi(aoi):
    """Save the boundary (simplified) and its bounding box for steps 2-4 and the web map."""
    bounds = gu.bounds_of(aoi)
    cfg.AOI_BOUNDS_JSON.write_text(json.dumps(bounds, indent=2))
    feature = {"type": "Feature", "properties": {"name": cfg.AOI_NAME},
               "geometry": aoi.simplify(maxError=20).getInfo()}
    cfg.AOI_BOUNDARY_GEOJSON.write_text(json.dumps(
        {"type": "FeatureCollection", "features": [feature]}))
    area_km2 = aoi.area(maxError=1).divide(1e6).getInfo()
    print(f"Study area: {cfg.AOI_NAME}, {area_km2:,.0f} km2, bounds {bounds}")


def main(to_drive: bool):
    cfg.DATA_DIR.mkdir(exist_ok=True)
    cfg.OUTPUT_DIR.mkdir(exist_ok=True)

    gu.init(cfg.GEE_PROJECT)
    aoi = gu.load_aoi(cfg)
    save_aoi(aoi)

    print("Counting Sentinel-2 scenes per season...")
    counts = {y: gu.count_images(aoi, y, cfg.SEASON_START, cfg.SEASON_END) for y in cfg.YEARS}
    (cfg.OUTPUT_DIR / "image_counts.json").write_text(json.dumps(counts, indent=2))
    print("  ", counts)

    print(f"Training Random Forest on {cfg.TRAINING_YEAR}...")
    classifier, report = train_classifier(aoi)
    cfg.ACCURACY_JSON.write_text(json.dumps(report, indent=2))
    print(f"  overall accuracy = {report['overall_accuracy']:.3f}, kappa = {report['kappa']:.3f}")

    print("Classifying all years...")
    stack = classify_all_years(aoi, classifier)

    if to_drive:
        task = ee.batch.Export.image.toDrive(
            image=stack, description="built_by_year", fileNamePrefix="built_by_year",
            region=aoi.bounds(maxError=1), scale=cfg.SCALE, crs=cfg.ANALYSIS_CRS,
            maxPixels=1e10)
        task.start()
        print("Export started. When it is finished, download built_by_year.tif "
              f"from Google Drive into {cfg.DATA_DIR}")
    else:
        import geemap  # imported here: only needed for direct download
        geemap.download_ee_image(stack, str(cfg.BUILT_STACK_TIF), region=aoi.bounds(maxError=1),
                                 crs=cfg.ANALYSIS_CRS, scale=cfg.SCALE, dtype="uint8")
        print(f"  saved {cfg.BUILT_STACK_TIF}")

    print("Downloading true-colour composites for the web map...")
    for year in (cfg.YEARS[0], cfg.YEARS[-1]):
        download_rgb(aoi, year, cfg.DATA_DIR / f"rgb_{year}.png")

    print("Done. Next: python 02_postprocess.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--drive", action="store_true", help="export the stack to Google Drive")
    main(parser.parse_args().drive)
