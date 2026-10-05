"""Step 1 - Google Earth Engine: training samples and one national Random Forest.

In every city, built / not-built labels are taken where WorldCover and Dynamic World
agree, and the same number of points is drawn per class (balanced city x class), then
split 70 / 30 into training and test points. One Random Forest is trained on the training
points of all cities together, and evaluated on the test points of each city.

Outputs
- data/training_samples.csv          every point: city, label, split, lon/lat, features
                                     (step 2 trains the same model again from this file)
- outputs/model/accuracy_by_city.json  agreement with the reference products, by city
                                     and national, with feature importance

Usage
    python -m pipeline.s1_train
"""
import json

import ee
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix, precision_recall_fscore_support

import config as cfg
from src import gee_utils as gu


def city_samples(city: str) -> pd.DataFrame:
    """Stratified sample of labelled points in one city, with a train / test split."""
    zone = gu.city_zone(cfg, city)
    composite = gu.seasonal_composite(zone, cfg.TRAINING_YEAR, cfg.SEASON_START,
                                      cfg.SEASON_END, cfg.CLOUD_SCORE_THRESHOLD)
    labels = gu.reference_labels(zone, cfg.TRAINING_YEAR)
    samples = (labels.addBands(composite.select(gu.FEATURE_BANDS))
               .stratifiedSample(numPoints=cfg.POINTS_PER_CLASS, classBand="label",
                                 region=zone, scale=cfg.SCALE, projection=ee.Projection(cfg.ANALYSIS_CRS),
                                 seed=cfg.SEED, geometries=True, tileScale=4)
               .randomColumn("random", cfg.SEED))
    rows = []
    for f in samples.getInfo()["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        rows.append({"city": city, "label": int(p["label"]),
                     "split": "train" if p["random"] < cfg.TRAIN_FRACTION else "test",
                     "lon": round(lon, 6), "lat": round(lat, 6),
                     **{b: p[b] for b in gu.FEATURE_BANDS}})
    return pd.DataFrame(rows)


def to_feature_collection(df: pd.DataFrame) -> ee.FeatureCollection:
    return ee.FeatureCollection([ee.Feature(None, {"row": int(r.Index), "label": int(r.label),
                                                   **{b: float(getattr(r, b)) for b in gu.FEATURE_BANDS}})
                                 for r in df.itertuples()])


def train_classifier(samples: pd.DataFrame) -> ee.Classifier:
    """National Random Forest trained on the training points of every city.

    Also used by step 2, so that both steps use exactly the same model.
    """
    train = samples[samples["split"] == "train"]
    return (ee.Classifier.smileRandomForest(numberOfTrees=cfg.N_TREES, seed=cfg.SEED)
            .train(features=to_feature_collection(train), classProperty="label",
                   inputProperties=gu.FEATURE_BANDS))


def agreement(y_ref, y_map) -> dict:
    labels = [0, 1]
    precision, recall, f1, _ = precision_recall_fscore_support(y_ref, y_map, labels=labels, zero_division=0)
    return {
        "n_test": int(len(y_ref)),
        "confusion_matrix_rows_reference_cols_map": confusion_matrix(y_ref, y_map, labels=labels).tolist(),
        "overall_accuracy": round(float(np.mean(np.asarray(y_ref) == np.asarray(y_map))), 3),
        "kappa": round(float(cohen_kappa_score(y_ref, y_map, labels=labels)), 3),
        "producers_accuracy": dict(zip(["not built", "built"], np.round(recall, 3).tolist())),
        "users_accuracy": dict(zip(["not built", "built"], np.round(precision, 3).tolist())),
        "f1": dict(zip(["not built", "built"], np.round(f1, 3).tolist())),
    }


def main():
    cfg.DATA_DIR.mkdir(exist_ok=True)
    cfg.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    gu.init(cfg.GEE_PROJECT)

    frames = []
    for city in cfg.CITIES:
        print(f"Sampling {city} ({cfg.TRAINING_YEAR})...")
        df = city_samples(city)
        print(f"  {len(df)} points: {df.groupby(['label', 'split']).size().to_dict()}")
        frames.append(df)
    samples = pd.concat(frames, ignore_index=True)
    samples.to_csv(cfg.TRAINING_SAMPLES_CSV, index=False)
    print(f"  saved {cfg.TRAINING_SAMPLES_CSV}")

    print(f"Training the national Random Forest on {(samples.split == 'train').sum()} points...")
    classifier = train_classifier(samples)

    test = samples[samples["split"] == "test"].reset_index(drop=True)
    classified = to_feature_collection(test).classify(classifier)
    rows, predicted = ee.List([classified.aggregate_array("row"),
                               classified.aggregate_array("classification")]).getInfo()
    test.loc[rows, "predicted"] = predicted

    report = {"national": agreement(test.label, test.predicted)}
    for city, df in test.groupby("city"):
        report[city] = agreement(df.label, df.predicted)
    report["feature_importance"] = classifier.explain().get("importance").getInfo()
    report["note"] = ("Test labels come from WorldCover / Dynamic World agreement areas: this measures "
                      "agreement with reference products, not true accuracy (see the national "
                      "validation, ROADMAP J4).")
    cfg.ACCURACY_BY_CITY_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\nAgreement with reference products on the test points")
    for key in ["national", *cfg.CITIES]:
        r = report[key]
        print(f"  {key:9} accuracy {r['overall_accuracy']:.3f}  kappa {r['kappa']:.3f}  (n = {r['n_test']})")
    print(f"Saved {cfg.ACCURACY_BY_CITY_JSON}. Next: python -m pipeline.s2_classify")


if __name__ == "__main__":
    main()
