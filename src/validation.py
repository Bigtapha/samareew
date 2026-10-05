"""Accuracy assessment on photo-interpreted points: pure NumPy / pandas, so it can be unit-tested.

Kept from the Dakar case study for the national validation (ROADMAP J4): stratified
sampling of the urbanisation map, then confusion matrix, kappa and area-weighted accuracy.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix, precision_recall_fscore_support

NOT_BUILT, BUILT_AT_START, NEW_BUILT = 0, 1, 2
NODATA = -1


def map_classes(first_year: np.ndarray, start_year: int) -> np.ndarray:
    """Validation strata from the urbanisation year: 0 = not built at the end,
    1 = already built in the first year, 2 = became built during the period, -1 = no data."""
    classes = np.full(first_year.shape, NODATA, dtype=np.int8)
    classes[first_year == 0] = NOT_BUILT
    classes[first_year == start_year] = BUILT_AT_START
    classes[first_year > start_year] = NEW_BUILT
    return classes


def stratified_pixels(classes: np.ndarray, points_per_class: dict, rng: np.random.Generator) -> dict:
    """Random pixels in each stratum: {class: (rows, cols)}, at most the requested number."""
    picks = {}
    for cls, n in points_per_class.items():
        rows, cols = np.nonzero(classes == cls)
        if len(rows):
            idx = rng.choice(len(rows), size=min(n, len(rows)), replace=False)
            picks[cls] = (rows[idx], cols[idx])
    return picks


def strata_weights(classes: np.ndarray, class_ids) -> dict:
    """Share of the mapped area covered by each stratum."""
    valid = (classes >= 0).sum()
    return {cls: float((classes == cls).sum() / valid) for cls in class_ids}


def accuracy_report(points: pd.DataFrame, weights: dict, class_names: dict) -> dict:
    """Metrics from labelled points (columns map_class and ref_class).

    The area-weighted overall accuracy weights the accuracy of each stratum by its share
    of the map, which corrects for the unequal number of points per stratum.
    """
    labels = list(class_names)
    y_map, y_ref = points["map_class"], points["ref_class"]
    precision, recall, f1, _ = precision_recall_fscore_support(y_ref, y_map, labels=labels, zero_division=0)
    per_stratum = (y_map == y_ref).groupby(y_map).mean()
    weighted = sum(weights[k] * v for k, v in per_stratum.items())
    names = [class_names[k] for k in labels]
    return {
        "n_points": int(len(points)),
        "classes": names,
        "confusion_matrix_rows_reference_cols_map": confusion_matrix(y_ref, y_map, labels=labels).tolist(),
        "overall_accuracy": round(float((y_map == y_ref).mean()), 3),
        "area_weighted_overall_accuracy": round(float(weighted), 3),
        "kappa": round(float(cohen_kappa_score(y_ref, y_map, labels=labels)), 3),
        "precision_users_accuracy": dict(zip(names, np.round(precision, 3).tolist())),
        "recall_producers_accuracy": dict(zip(names, np.round(recall, 3).tolist())),
        "f1": dict(zip(names, np.round(f1, 3).tolist())),
    }
