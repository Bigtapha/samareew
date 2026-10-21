"""Accuracy assessment on photo-interpreted points: pure NumPy / pandas, so it can be unit-tested.

National validation (ROADMAP J4): a stratified random sample of each city's map, labelled
blind, then design-based estimates with standard errors (Olofsson et al., 2014; Stehman,
2014). The strata split the map classes further: the new built-up area is divided by growth
type, so a stratum always lies inside one map class.
"""
import numpy as np
import pandas as pd

# Map / reference classes, at the end of the validation period
NOT_BUILT, BUILT_AT_START, NEW_BUILT = 0, 1, 2
CLASS_NAMES = {NOT_BUILT: "not_built", BUILT_AT_START: "built_at_start", NEW_BUILT: "new_built"}
NODATA = -1

# Strata: (name, map class). Growth types use the codes of src.indicators (1, 2, 3).
STRATA = {
    "not_built": NOT_BUILT,
    "built_at_start": BUILT_AT_START,
    "densification": NEW_BUILT,
    "extension": NEW_BUILT,
    "leapfrog": NEW_BUILT,
}
GROWTH_STRATA = {1: "densification", 2: "extension", 3: "leapfrog"}
Z95 = 1.96


def map_classes(first_year: np.ndarray, start_year: int, end_year: int) -> np.ndarray:
    """Map class at the end of the period from the urbanisation year: 0 = not built,
    1 = already built in the first year, 2 = became built during the period, -1 = no data.
    Pixels urbanised after ``end_year`` are not built at the end."""
    classes = np.full(first_year.shape, NODATA, dtype=np.int8)
    classes[(first_year == 0) | (first_year > end_year)] = NOT_BUILT
    classes[(first_year > 0) & (first_year <= start_year)] = BUILT_AT_START
    classes[(first_year > start_year) & (first_year <= end_year)] = NEW_BUILT
    return classes


def strata_codes(classes: np.ndarray, growth_type: np.ndarray) -> np.ndarray:
    """Stratum index (position in STRATA) of each pixel, -1 outside the map.

    The new built-up pixels are split by their growth type over the same period; every one
    of them must have a type.
    """
    if ((classes == NEW_BUILT) & (growth_type == 0)).any():
        raise ValueError("some new built-up pixels have no growth type: maps of different periods?")
    names = list(STRATA)
    codes = np.full(classes.shape, -1, dtype=np.int8)
    codes[classes == NOT_BUILT] = names.index("not_built")
    codes[classes == BUILT_AT_START] = names.index("built_at_start")
    for t, name in GROWTH_STRATA.items():
        codes[(classes == NEW_BUILT) & (growth_type == t)] = names.index(name)
    return codes


def stratified_pixels(codes: np.ndarray, points_per_stratum: dict, rng: np.random.Generator) -> dict:
    """Random pixels in each stratum: {stratum name: (rows, cols)}, at most the requested number."""
    names = list(STRATA)
    picks = {}
    for name, n in points_per_stratum.items():
        rows, cols = np.nonzero(codes == names.index(name))
        if len(rows):
            idx = rng.choice(len(rows), size=min(n, len(rows)), replace=False)
            picks[name] = (rows[idx], cols[idx])
    return picks


def reference_class(built_start, built_end) -> np.ndarray:
    """Reference class from the two photo-interpreted dates (1 = built, 0 = not built).

    The end state decides first, like the map: a building gone at the end is not built.
    """
    built_start, built_end = np.asarray(built_start), np.asarray(built_end)
    return np.where(built_end == 0, NOT_BUILT, np.where(built_start == 1, BUILT_AT_START, NEW_BUILT))


# --- Design-based estimates ------------------------------------------------------
# ``points``: one row per labelled point, with a ``stratum`` column (any hashable key, e.g.
# (city, stratum) for the national estimate). ``weights``: {stratum: share of the mapped
# area}, summing to 1 over the population being estimated.

def _stratum_stats(points: pd.DataFrame, weights: dict, cols: list) -> list:
    """(W_h, n_h, means, covariance matrix) for each sampled stratum."""
    stats = []
    for h, group in points.groupby("stratum", sort=False):
        x = group[cols].to_numpy(dtype=float)
        cov = np.cov(x, rowvar=False, ddof=1).reshape(len(cols), len(cols)) if len(x) > 1 \
            else np.full((len(cols), len(cols)), np.nan)
        stats.append((weights[h], len(x), x.mean(axis=0), cov))
    return stats


def stratified_mean(points: pd.DataFrame, weights: dict, col: str) -> tuple:
    """Estimated mean of ``col`` over the whole area, and its standard error.

    With ``col`` a 0/1 indicator, this is a proportion of the area (e.g. the overall accuracy,
    or the share of the area that is new built-up in reality).
    """
    est, var = 0.0, 0.0
    for w, n, mean, cov in _stratum_stats(points, weights, [col]):
        est += w * mean[0]
        var += w ** 2 * cov[0, 0] / n
    total_w = sum(weights[h] for h in points["stratum"].unique())
    if not np.isclose(total_w, sum(weights.values())):
        raise ValueError("every stratum of the area must hold at least one point")
    return float(est), float(np.sqrt(var))


def stratified_ratio(points: pd.DataFrame, weights: dict, num: str, den: str) -> tuple:
    """Ratio of two estimated totals (sum W_h ybar_h / sum W_h xbar_h) and its standard
    error (Stehman, 2014, eq. 27). User's and producer's accuracies are such ratios."""
    stats = _stratum_stats(points, weights, [num, den])
    y = sum(w * m[0] for w, _, m, _ in stats)
    x = sum(w * m[1] for w, _, m, _ in stats)
    if x == 0:
        return float("nan"), float("nan")
    r = y / x
    var = sum(w ** 2 * (c[0, 0] + r ** 2 * c[1, 1] - 2 * r * c[0, 1]) / n
              for w, n, _, c in stats) / x ** 2
    return float(r), float(np.sqrt(var))


def log_interval(est: float, se: float) -> tuple:
    """95 % interval of a positive ratio, computed on its logarithm (delta method:
    se(ln r) = se(r) / r). A ratio of areas is skewed: the symmetric interval est ± 1.96 se
    is too wide below and too narrow above (checked against a stratified bootstrap)."""
    if not est > 0:
        return float("nan"), float("nan")
    half = Z95 * se / est
    return float(est * np.exp(-half)), float(est * np.exp(half))


def growth_estimate(points: pd.DataFrame, weights: dict, start_col: str, end_col: str) -> dict:
    """Growth of the built-up area between two dates from the photo-interpreted 0/1 labels:
    ratio of the estimated areas built at the end and at the start, minus one. Both areas come
    from the same points, so the ratio estimator accounts for their correlation."""
    r, se = stratified_ratio(points, weights, end_col, start_col)
    low, high = log_interval(r, se)
    return {"estimate": round(r - 1, 3), "low95": round(low - 1, 3), "high95": round(high - 1, 3),
            "log_se": round(se / r, 4)}


def growth_difference(a: dict, b: dict) -> dict:
    """Compare the corrected growth of two cities (outputs of ``growth_estimate``). The
    samples of two cities are independent, so the variances of the log growth factors add.
    ``established`` is True when the 95 % interval of the ratio of the factors excludes 1."""
    d = np.log1p(a["estimate"]) - np.log1p(b["estimate"])
    se = float(np.hypot(a["log_se"], b["log_se"]))
    return {"factor_ratio": round(float(np.exp(d)), 3),
            "low95": round(float(np.exp(d - Z95 * se)), 3),
            "high95": round(float(np.exp(d + Z95 * se)), 3),
            "established": bool(abs(d) > Z95 * se)}


def accuracy_report(points: pd.DataFrame, weights: dict, total_area_ha: float) -> dict:
    """Area-weighted accuracies and corrected areas from labelled points.

    ``points`` columns: stratum, map_class, ref_class. Values are given with their 95 %
    margin (1.96 standard errors).
    """
    p = points.copy()
    p["correct"] = (p["map_class"] == p["ref_class"]).astype(float)

    def value(est_se, scale=1.0, digits=3):
        est, se = est_se
        return {"estimate": round(est * scale, digits), "margin95": round(Z95 * se * scale, digits)}

    report = {"n_points": int(len(p)),
              "overall_accuracy": value(stratified_mean(p, weights, "correct")),
              "users_accuracy": {}, "producers_accuracy": {}, "area_ha": {}, "mapped_area_ha": {},
              "by_stratum": {}}
    mapped = {}
    for h, w in weights.items():
        cls = p.loc[p["stratum"] == h, "map_class"]
        if len(cls):
            mapped[int(cls.iloc[0])] = mapped.get(int(cls.iloc[0]), 0.0) + w
    for k, name in CLASS_NAMES.items():
        p["is_map"] = (p["map_class"] == k).astype(float)
        p["is_ref"] = (p["ref_class"] == k).astype(float)
        p["both"] = p["is_map"] * p["is_ref"]
        report["users_accuracy"][name] = value(stratified_ratio(p, weights, "both", "is_map"))
        report["producers_accuracy"][name] = value(stratified_ratio(p, weights, "both", "is_ref"))
        report["area_ha"][name] = value(stratified_mean(p, weights, "is_ref"), total_area_ha, 0)
        report["mapped_area_ha"][name] = round(mapped.get(k, 0.0) * total_area_ha)
    for h, group in p.groupby("stratum", sort=False):
        report["by_stratum"][str(h)] = {"n": int(len(group)),
                                        "weight": round(float(weights[h]), 4),
                                        "accuracy": round(float(group["correct"].mean()), 3)}
    return report


def date_accuracy(points: pd.DataFrame, weights: dict) -> dict:
    """Area-weighted built / not-built accuracy at each date, ignoring when the change happened.

    ``points`` columns: stratum, map_class, ref_start, ref_end (photo-interpreted 0/1). The map
    is built at the start for class 1, at the end for classes 1 and 2.
    """
    p = points.copy()
    p["ok_start"] = ((p["map_class"] == BUILT_AT_START).astype(int) == p["ref_start"]).astype(float)
    p["ok_end"] = ((p["map_class"] != NOT_BUILT).astype(int) == p["ref_end"]).astype(float)
    out = {}
    for name, col in [("start", "ok_start"), ("end", "ok_end")]:
        est, se = stratified_mean(p, weights, col)
        out[name] = {"estimate": round(est, 3), "margin95": round(Z95 * se, 3)}
    return out


def tolerant_built(built_end, cover, urbanising) -> np.ndarray:
    """Built at the end in the tolerant sense: built (1), or land being urbanised according
    to the cover noted at the second reading (e.g. an unbuilt subdivision)."""
    built_end = np.asarray(built_end)
    return np.where((built_end == 1) | pd.Series(cover).isin(urbanising).to_numpy(), 1, 0)


def class_shares(points: pd.DataFrame, weights: dict, map_class: int, col: str) -> dict:
    """Area-weighted share of each value of ``col`` inside one map class, with its 95 % margin
    (e.g. what covers the area the map calls new built-up)."""
    p = points.copy()
    p["is_map"] = (p["map_class"] == map_class).astype(float)
    out = {}
    for value in p.loc[p["is_map"] == 1, col].dropna().unique():
        p["both"] = p["is_map"] * (p[col] == value)
        est, se = stratified_ratio(p, weights, "both", "is_map")
        out[str(value)] = {"estimate": round(est, 3), "margin95": round(Z95 * se, 3)}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["estimate"]))


def binomial_margin(k: int, n: int) -> float:
    """95 % margin of a simple proportion k / n (normal approximation), NaN if n < 2."""
    if n < 2:
        return float("nan")
    p = k / n
    return float(Z95 * np.sqrt(p * (1 - p) / (n - 1)))


def map_measures(points: pd.DataFrame, weights: dict) -> dict:
    """Main accuracies of one map against the labelled points (95 % margins), to compare maps.

    The sample may have been drawn from another map: the strata stay a fixed partition of the
    area, so the stratified estimators remain unbiased (Stehman, 2014). ``points`` columns:
    stratum, map_class, map_year, ref_class, ref_start, ref_end, year_built (NaN if unread).
    """
    r = accuracy_report(points, weights, 1.0)
    end = date_accuracy(points, weights)["end"]
    both_new = points[(points["map_class"] == NEW_BUILT) & (points["ref_class"] == NEW_BUILT)
                      & points["year_built"].notna()]
    within = int(((both_new["map_year"] - both_new["year_built"]).abs() <= 1).sum())
    return {"overall_accuracy": r["overall_accuracy"],
            "built_accuracy_end": end,
            "new_built_users": r["users_accuracy"]["new_built"],
            "new_built_producers": r["producers_accuracy"]["new_built"],
            "year_within_one": {"estimate": round(within / len(both_new), 3) if len(both_new) else None,
                                "n": int(len(both_new))}}
