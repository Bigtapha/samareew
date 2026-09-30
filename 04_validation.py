"""Step 4 - Independent accuracy assessment on photo-interpreted points (QA/QC).

1) python 04_validation.py make
   Draws a stratified random sample of points from the urbanisation map and writes
   - outputs/validation_points.csv  (open in QGIS or a spreadsheet)
   - outputs/validation_points.kml  (open in Google Earth Pro and use the
     historical imagery slider to check each point)

2) Fill the column ``ref_class`` for each point by visual interpretation:
     0 = not built in the last year
     1 = already built in the first year
     2 = became built during the period
   Do NOT look at the ``map_class`` column while labelling (blind interpretation).

3) python 04_validation.py evaluate
   Computes the confusion matrix, overall accuracy, kappa, per-class precision and
   recall, and the area-weighted overall accuracy -> outputs/accuracy_validation.json
"""
import argparse
import json

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import xy
from rasterio.warp import transform
from sklearn.metrics import (cohen_kappa_score, confusion_matrix,
                             precision_recall_fscore_support)

import config as cfg

CLASS_NAMES = {0: "not built", 1: f"built before {cfg.YEARS[0] + 1}", 2: "new built-up"}
POINTS_PER_CLASS = {0: 100, 1: 60, 2: 100}   # more points where errors matter most
CSV_PATH = cfg.OUTPUT_DIR / "validation_points.csv"


def map_classes(first_year):
    classes = np.full(first_year.shape, -1, dtype=np.int8)
    classes[first_year == 0] = 0
    classes[first_year == cfg.YEARS[0]] = 1
    classes[first_year > cfg.YEARS[0]] = 2
    return classes


def make_points():
    rng = np.random.default_rng(cfg.SEED)
    with rasterio.open(cfg.FIRST_YEAR_TIF) as src:
        first_year = src.read(1)
        tr, crs = src.transform, src.crs
    classes = map_classes(first_year)

    rows = []
    for cls, n in POINTS_PER_CLASS.items():
        r, c = np.nonzero(classes == cls)
        if len(r) == 0:
            continue
        pick = rng.choice(len(r), size=min(n, len(r)), replace=False)
        xs, ys = xy(tr, r[pick], c[pick])
        lons, lats = transform(crs, "EPSG:4326", list(np.atleast_1d(xs)), list(np.atleast_1d(ys)))
        for lon, lat, fy in zip(lons, lats, first_year[r[pick], c[pick]]):
            rows.append({"lon": round(lon, 6), "lat": round(lat, 6), "map_class": cls,
                         "map_year": int(fy), "ref_class": ""})

    df = pd.DataFrame(rows).sample(frac=1, random_state=cfg.SEED).reset_index(drop=True)
    df.insert(0, "id", range(1, len(df) + 1))
    cfg.OUTPUT_DIR.mkdir(exist_ok=True)
    df.to_csv(CSV_PATH, index=False)

    placemarks = "\n".join(
        f"<Placemark><name>{r.id}</name><Point><coordinates>{r.lon},{r.lat},0</coordinates></Point></Placemark>"
        for r in df.itertuples())
    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
           f"<Document><name>Validation points</name>\n{placemarks}\n</Document></kml>")
    (cfg.OUTPUT_DIR / "validation_points.kml").write_text(kml)

    # Share of the map covered by each class, used to weight the accuracy
    weights = {cls: float((classes == cls).sum() / (classes >= 0).sum()) for cls in CLASS_NAMES}
    (cfg.OUTPUT_DIR / "validation_strata_weights.json").write_text(json.dumps(weights, indent=2))
    print(f"{len(df)} points written to {CSV_PATH} and validation_points.kml")


def evaluate():
    df = pd.read_csv(CSV_PATH)
    df = df[pd.to_numeric(df["ref_class"], errors="coerce").notna()].copy()
    if df.empty:
        raise SystemExit("No labelled points: fill the ref_class column first.")
    df["ref_class"] = df["ref_class"].astype(int)

    labels = list(CLASS_NAMES)
    y_map, y_ref = df["map_class"], df["ref_class"]
    cm = confusion_matrix(y_ref, y_map, labels=labels)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_ref, y_map, labels=labels, zero_division=0)

    # Area-weighted overall accuracy: each stratum weighted by its share of the map
    weights = json.loads((cfg.OUTPUT_DIR / "validation_strata_weights.json").read_text())
    per_stratum = (df["map_class"] == df["ref_class"]).groupby(df["map_class"]).mean()
    weighted_oa = sum(weights[str(k)] * v for k, v in per_stratum.items())

    result = {
        "n_points": int(len(df)),
        "classes": [CLASS_NAMES[k] for k in labels],
        "confusion_matrix_rows_reference_cols_map": cm.tolist(),
        "overall_accuracy": round(float((y_map == y_ref).mean()), 3),
        "area_weighted_overall_accuracy": round(float(weighted_oa), 3),
        "kappa": round(float(cohen_kappa_score(y_ref, y_map, labels=labels)), 3),
        "precision_users_accuracy": dict(zip(CLASS_NAMES.values(), np.round(precision, 3).tolist())),
        "recall_producers_accuracy": dict(zip(CLASS_NAMES.values(), np.round(recall, 3).tolist())),
        "f1": dict(zip(CLASS_NAMES.values(), np.round(f1, 3).tolist())),
    }
    (cfg.OUTPUT_DIR / "accuracy_validation.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print("Re-run 03_make_webmap.py to show these figures on the web map.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["make", "evaluate"])
    args = parser.parse_args()
    make_points() if args.action == "make" else evaluate()
