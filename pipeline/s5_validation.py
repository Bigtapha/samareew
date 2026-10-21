"""Step 5 - National validation: stratified sample, blind labels, accuracy by city (ROADMAP J4).

1. ``--draw`` draws the same stratified sample in every city (config.settings
   VALIDATION_POINTS): not built, built at the start, and the new built-up area split by
   growth type. The points go to a labelling sheet that does not show the map class.
2. The points are photo-interpreted blind in Google Earth Pro (historical imagery), filling
   labels.csv: is the 10 m pixel built at the start and at the end of the period?
3. Without ``--draw``, the labels are compared with the map: area-weighted accuracies,
   corrected areas and their 95 % margins, by city and for the four cities together
   (src/validation.py, METHODOLOGIE §14).
4. ``--cover`` prepares a second blind reading of the points labelled not built at the end:
   what covers them (config.settings VALIDATION_COVER_CLASSES). Once it is complete, the
   report adds a tolerant accuracy where land being urbanised counts as built.

Inputs : outputs/cities/<city>/urbanisation_year.tif (step 3), growth_type_<start>_<end>.tif (step 4)
Outputs: outputs/validation/labels.csv      sheet to fill (id, city, lon, lat, empty label columns)
         outputs/validation/sample_key.csv  map stratum, class and year of each point
         outputs/validation/strata.csv      pixels, area, weight and points per city and stratum
         outputs/validation/points.kml      points and their 10 m pixel, one folder per city
         outputs/validation/accuracy.json   accuracy report (after labelling)
         outputs/validation/cover_2025.csv  second reading sheet (--cover)
         outputs/validation/cover_2025.kml  its points, for Google Earth Pro
         data/j4_sample_<city>.png          control map of the sample

Usage
    python -m pipeline.s5_validation --draw          # once; refuses to erase labels already entered
    python -m pipeline.s5_validation --cover         # once, after labelling: second reading sheet
    python -m pipeline.s5_validation                 # accuracy from the labels entered so far
"""
import argparse
import json
import re
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import transform as warp_transform

import config as cfg
from src import validation as va

START, END = cfg.VALIDATION_PERIOD
LABEL_COLUMNS = [f"built_{START}", f"built_{END}", "year_built", "sure",
                 f"image_date_{START}", f"image_date_{END}", "note"]
STRATUM_COLORS = {"not_built": "#f2efe9", "built_at_start": "#6b6b6b", "densification": "#2b8cbe",
                  "extension": "#fe9929", "leapfrog": "#d7301f"}
STRATUM_LABELS_FR = {"not_built": "Non bâti", "built_at_start": f"Bâti en {START}",
                     "densification": "Densification", "extension": "Extension", "leapfrog": "Saut"}


def read_city(city: str) -> tuple:
    out_dir = cfg.city_output_dir(city)
    with rasterio.open(out_dir / cfg.FIRST_YEAR_TIF) as src:
        first_year, transform, crs = src.read(1), src.transform, src.crs
    with rasterio.open(out_dir / cfg.GROWTH_TYPE_TIF.format(start=START, end=END)) as src:
        if src.transform != transform or src.shape != first_year.shape:
            raise ValueError(f"{city}: growth types and urbanisation year are not on the same grid")
        growth = src.read(1)
    return first_year, growth, transform, crs


# --- 1. Sample ---------------------------------------------------------------------

def draw_city(city: str, rng: np.random.Generator) -> tuple:
    first_year, growth, transform, crs = read_city(city)
    codes = va.strata_codes(va.map_classes(first_year, START, END), growth)
    picks = va.stratified_pixels(codes, cfg.VALIDATION_POINTS, rng)
    pixel_ha = abs(transform.a * transform.e) / 10_000
    names = list(va.STRATA)
    pixels = np.bincount(codes[codes >= 0], minlength=len(names))
    strata = [{"city": city, "stratum": s, "map_class": va.CLASS_NAMES[va.STRATA[s]],
               "pixels": int(pixels[i]), "area_ha": round(pixels[i] * pixel_ha, 1),
               "weight": round(pixels[i] / pixels.sum(), 6), "points": len(picks.get(s, ([],))[0])}
              for i, s in enumerate(names)]

    rows = []
    for stratum, (r, c) in picks.items():
        x, y = rasterio.transform.xy(transform, r, c)          # pixel centres
        for ri, ci, xi, yi in zip(r, c, x, y):
            rows.append({"city": city, "stratum": stratum, "map_class": va.STRATA[stratum],
                         "map_year": int(first_year[ri, ci]), "row": int(ri), "col": int(ci),
                         "x": xi, "y": yi})
    points = pd.DataFrame(rows).sample(frac=1, random_state=rng.integers(2 ** 31)).reset_index(drop=True)
    # Shuffled within the city: neither the id nor the order gives away the stratum
    points.insert(0, "id", [f"{city[:3].upper()}-{i + 1:03d}" for i in range(len(points))])
    lon, lat = warp_transform(crs, "EPSG:4326", points["x"].tolist(), points["y"].tolist())
    points["lon"], points["lat"] = np.round(lon, 6), np.round(lat, 6)
    # Corners of each pixel, for the square drawn in Google Earth
    half = abs(transform.a) / 2
    corners = []
    for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)]:
        cx, cy = warp_transform(crs, "EPSG:4326", (points["x"] + dx * half).tolist(),
                                (points["y"] + dy * half).tolist())
        corners.append(list(zip(cx, cy)))
    points["square"] = [[c[i] for c in corners] for i in range(len(points))]
    sample_map(city, codes, points, cfg.DATA_DIR / f"j4_sample_{city}.png")
    return points, strata


def sample_map(city: str, codes: np.ndarray, points: pd.DataFrame, path) -> None:
    """Control map: strata and sampled points."""
    names = list(va.STRATA)
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(np.ma.masked_less(codes, 0), cmap=ListedColormap([STRATUM_COLORS[s] for s in names]),
              vmin=0, vmax=len(names) - 1, interpolation="nearest")
    for s in names:
        p = points[points["stratum"] == s]
        ax.scatter(p["col"], p["row"], s=14, color=STRATUM_COLORS[s], edgecolor="black", linewidth=0.6)
    ax.set_title(f"Échantillon de validation — {cfg.CITIES[city]['name']} ({len(points)} points)")
    ax.set_axis_off()
    ax.legend(handles=[Patch(facecolor=STRATUM_COLORS[s], edgecolor="black", label=STRATUM_LABELS_FR[s])
                       for s in names], loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_kml(points: pd.DataFrame, path) -> None:
    """One folder per city; each placemark shows the point and the outline of its pixel."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           "<name>SamaReew - validation</name>",
           '<Style id="pt"><IconStyle><scale>0.6</scale></IconStyle>'
           "<LineStyle><color>ff00ffff</color><width>2</width></LineStyle>"
           "<PolyStyle><fill>0</fill></PolyStyle></Style>"]
    for city, group in points.groupby("city", sort=False):
        out.append(f"<Folder><name>{cfg.CITIES[city]['name']}</name>")
        for p in group.sort_values("id").itertuples():
            ring = " ".join(f"{lon:.7f},{lat:.7f},0" for lon, lat in p.square)
            out.append(f"<Placemark><name>{p.id}</name><styleUrl>#pt</styleUrl><MultiGeometry>"
                       f"<Point><coordinates>{p.lon},{p.lat},0</coordinates></Point>"
                       f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{ring}</coordinates>"
                       "</LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>")
        out.append("</Folder>")
    out.append("</Document></kml>")
    path.write_text("\n".join(out), encoding="utf-8")


def draw(force: bool) -> None:
    if cfg.VALIDATION_LABELS_CSV.exists() and not force:
        labels = pd.read_csv(cfg.VALIDATION_LABELS_CSV, dtype=str)
        if labels[LABEL_COLUMNS].notna().any().any():
            raise SystemExit(f"{cfg.VALIDATION_LABELS_CSV} already holds labels: drawing again would "
                             "erase them (use --force only if you really mean it)")
    rng = np.random.default_rng(cfg.VALIDATION_SEED)
    points, strata = [], []
    for city in cfg.CITIES:
        p, s = draw_city(city, rng)
        points.append(p)
        strata += s
        print(f"{city}: {len(p)} points")
    points = pd.concat(points, ignore_index=True)
    cfg.VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    sheet = points.sort_values(["city", "id"], key=lambda s: s.map(list(cfg.CITIES).index)
                               if s.name == "city" else s)[["id", "city", "lon", "lat"]]
    for col in LABEL_COLUMNS:
        sheet[col] = ""
    sheet.to_csv(cfg.VALIDATION_LABELS_CSV, index=False)
    points[["id", "city", "stratum", "map_class", "map_year", "row", "col", "lon", "lat"]].to_csv(
        cfg.VALIDATION_KEY_CSV, index=False)
    pd.DataFrame(strata).to_csv(cfg.VALIDATION_STRATA_CSV, index=False)
    write_kml(points, cfg.VALIDATION_KML)
    print(pd.DataFrame(strata).pivot(index="stratum", columns="city", values="weight").round(3).to_string())


# --- 4. Second reading: cover of the points not built at the end ----------------------

def cover(force: bool) -> None:
    """Sheet and KML of the points labelled not built at the end, without the map class.
    The points are chosen from the labels only, never from the map, so the reading stays blind."""
    if cfg.VALIDATION_COVER_CSV.exists() and not force:
        done = pd.read_csv(cfg.VALIDATION_COVER_CSV, dtype=str)
        if done[f"cover_{END}"].notna().any():
            raise SystemExit(f"{cfg.VALIDATION_COVER_CSV} already holds covers (use --force only "
                             "if you really mean to erase them)")
    labels = pd.read_csv(cfg.VALIDATION_LABELS_CSV, dtype=str)
    sheet = labels[labels[f"built_{END}"] == "0"][["id", "city", "lon", "lat", f"image_date_{END}"]].copy()
    sheet.insert(4, f"cover_{END}", "")
    sheet["note"] = ""
    sheet.to_csv(cfg.VALIDATION_COVER_CSV, index=False)
    # Same placemarks as points.kml (pixel outline included), only the selected ids
    kml = cfg.VALIDATION_KML.read_text(encoding="utf-8")
    keep = set(sheet["id"])
    kml = re.sub(r"<Placemark><name>([^<]+)</name>.*?</Placemark>\n?",
                 lambda m: m.group(0) if m.group(1) in keep else "", kml)
    kml = kml.replace("<name>SamaReew - validation</name>", f"<name>SamaReew - occupation {END}</name>")
    cfg.VALIDATION_COVER_KML.write_text(kml, encoding="utf-8")
    print(f"{len(sheet)} points to read again -> {cfg.VALIDATION_COVER_CSV.name}, {cfg.VALIDATION_COVER_KML.name}")
    print("covers: " + ", ".join(cfg.VALIDATION_COVER_CLASSES))


def with_covers(points: pd.DataFrame):
    """Add the cover of the second reading, or return None while it is missing or incomplete."""
    if not cfg.VALIDATION_COVER_CSV.exists():
        return None
    covers = pd.read_csv(cfg.VALIDATION_COVER_CSV, dtype=str)
    col = f"cover_{END}"
    bad = covers[covers[col].notna() & ~covers[col].isin(list(cfg.VALIDATION_COVER_CLASSES))]
    if len(bad):
        raise SystemExit(f"unknown covers {sorted(bad[col].unique())} for {bad['id'].tolist()}")
    todo = int(covers[col].isna().sum())
    if todo:
        print(f"second reading: {len(covers) - todo} of {len(covers)} covers entered")
        return None
    p = points.merge(covers[["id", col]], on="id", how="left", validate="one_to_one")
    missing = p[(p[f"built_{END}"] == 0) & p[col].isna()]
    if len(missing):
        raise SystemExit(f"{cfg.VALIDATION_COVER_CSV.name} misses points labelled not built: "
                         f"{missing['id'].tolist()} (run --cover again?)")
    p[col] = p[col].fillna("built")
    p["built_end_tolerant"] = va.tolerant_built(p[f"built_{END}"], p[col], cfg.VALIDATION_URBANISING)
    p["ref_class"] = va.reference_class(p[f"built_{START}"], p["built_end_tolerant"])
    return p


def tolerant_measures(points: pd.DataFrame, weights: dict, total_area_ha: float) -> dict:
    """Accuracy when land being urbanised counts as built, and what covers each map class."""
    r = va.accuracy_report(points, weights, total_area_ha)
    col = f"cover_{END}"
    return {"urbanising_covers": list(cfg.VALIDATION_URBANISING),
            "overall_accuracy": r["overall_accuracy"],
            "users_accuracy": r["users_accuracy"],
            "producers_accuracy": r["producers_accuracy"],
            "area_ha": r["area_ha"],
            "date_accuracy_end": va.date_accuracy(points.rename(columns={
                f"built_{START}": "ref_start", "built_end_tolerant": "ref_end"}), weights)["end"],
            "cover_of_map_class": {name: va.class_shares(points, weights, k, col)
                                   for k, name in va.CLASS_NAMES.items()}}


# --- 3. Accuracy ---------------------------------------------------------------------

def year_check(points: pd.DataFrame) -> dict:
    """Urbanisation year of the map against the year seen on the imagery, for the points
    that are new built-up in both and have a photo-interpreted year."""
    p = points[(points["map_class"] == va.NEW_BUILT) & (points["ref_class"] == va.NEW_BUILT)
               & points["year_built"].notna()]
    diff = p["map_year"] - p["year_built"]
    within = int((diff.abs() <= 1).sum())
    # Per urbanisation year of the map (points, not area-weighted): is the new built-up real?
    new = points[points["map_class"] == va.NEW_BUILT]
    by_year = {str(y): {"n": int(len(g)),
                        "new_built": round(float((g["ref_class"] == va.NEW_BUILT).mean()), 3),
                        "not_built": round(float((g["ref_class"] == va.NOT_BUILT).mean()), 3)}
               for y, g in new.groupby("map_year")}
    return {"n_points": int(len(p)),
            "within_one_year": round(within / len(p), 3) if len(p) else None,
            "within_one_year_margin95": round(va.binomial_margin(within, len(p)), 3) if len(p) > 1 else None,
            "mean_map_minus_imagery": round(float(diff.mean()), 2) if len(p) else None,
            "new_built_by_map_year": by_year}


def extra_measures(points: pd.DataFrame, weights: dict, total_area_ha: float) -> dict:
    """Built / not-built accuracy and corrected built-up area at each date, the corrected
    growth between them, and the overall accuracy on sure labels only (an upper bound: the
    unsure points are the hard ones)."""
    out = {"date_accuracy": va.date_accuracy(
        points.rename(columns={f"built_{START}": "ref_start", f"built_{END}": "ref_end"}), weights),
        "built_area_ha": {}}
    for year in (START, END):
        est, se = va.stratified_mean(points, weights, f"built_{year}")
        out["built_area_ha"][str(year)] = {"estimate": round(est * total_area_ha),
                                           "margin95": round(va.Z95 * se * total_area_ha)}
    out["built_area_growth"] = va.growth_estimate(points, weights, f"built_{START}", f"built_{END}")
    sure = points[points["sure"] == 1]
    try:
        oa = va.accuracy_report(sure, weights, 1.0)["overall_accuracy"]
        out["overall_accuracy_sure_only"] = {**oa, "n_points": int(len(sure))}
    except ValueError:                       # a stratum without any sure label
        out["overall_accuracy_sure_only"] = None
    return out


def mapped_growth(report: dict) -> float:
    """Growth of the mapped built-up area over the validation period (pixel counts)."""
    m = report["mapped_area_ha"]
    return round((m["built_at_start"] + m["new_built"]) / m["built_at_start"] - 1, 3)


def growth_comparison(cities: dict) -> list:
    """Every pair of cities: is the corrected growth of one established as faster?"""
    names = list(cities)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            d = va.growth_difference(cities[a]["built_area_growth"], cities[b]["built_area_growth"])
            out.append({"cities": [a, b], **d})
            verdict = "established" if d["established"] else "not established"
            print(f"growth {a} / {b}: factor ratio {d['factor_ratio']:.2f} "
                  f"[{d['low95']:.2f}, {d['high95']:.2f}], {verdict}")
    return out


def labelled_points() -> pd.DataFrame:
    labels = pd.read_csv(cfg.VALIDATION_LABELS_CSV)
    key = pd.read_csv(cfg.VALIDATION_KEY_CSV)
    done = labels.dropna(subset=[f"built_{START}", f"built_{END}"])
    bad = done[~done[[f"built_{START}", f"built_{END}"]].isin([0, 1]).all(axis=1)]
    if len(bad):
        raise SystemExit(f"labels must be 0 or 1: {bad['id'].tolist()}")
    points = done.drop(columns=["city", "lon", "lat"]).merge(key, on="id", validate="one_to_one")
    points["ref_class"] = va.reference_class(points[f"built_{START}"], points[f"built_{END}"])
    # year_built is entered as YYYY or YYYY-MM (date of the first image showing the building)
    points["year_built"] = pd.to_numeric(points["year_built"].astype("string").str[:4], errors="coerce")
    return points


def report() -> None:
    points = labelled_points()
    tolerant = with_covers(points)
    strata = pd.read_csv(cfg.VALIDATION_STRATA_CSV)
    print(f"{len(points)} labelled points out of {int(strata['points'].sum())}")
    result = {"date": date.today().isoformat(), "period": [START, END],
              "points_per_stratum": cfg.VALIDATION_POINTS, "cities": {}, "national": None}
    complete = []
    for city in cfg.CITIES:
        s = strata[strata["city"] == city]
        p = points[points["city"] == city]
        counts = p["stratum"].value_counts()
        if any(counts.get(h, 0) < 2 for h in s.loc[s["points"] > 0, "stratum"]):
            print(f"{city}: {len(p)} points, at least two per stratum are needed for an estimate")
            continue
        weights = dict(zip(s["stratum"], s["weight"]))
        r = va.accuracy_report(p.assign(stratum=p["stratum"]), weights, s["area_ha"].sum())
        r["year_check"] = year_check(p)
        r.update(extra_measures(p, weights, s["area_ha"].sum()))
        r["built_area_growth"]["mapped"] = mapped_growth(r)
        r["unsure_labels"] = int((p["sure"] == 0).sum())
        if tolerant is not None:
            r["tolerant"] = tolerant_measures(tolerant[tolerant["city"] == city], weights, s["area_ha"].sum())
        result["cities"][city] = r
        complete.append(city)
        oa = r["overall_accuracy"]
        print(f"{city}: overall accuracy {oa['estimate']:.3f} ± {oa['margin95']:.3f} ({len(p)} points)")
    if len(complete) == len(cfg.CITIES):
        total = strata["pixels"].sum()
        weights = {(c, h): px / total for c, h, px in zip(strata["city"], strata["stratum"], strata["pixels"])}
        national = points.assign(stratum=list(zip(points["city"], points["stratum"])))
        r = va.accuracy_report(national, weights, strata["area_ha"].sum())
        r.pop("by_stratum")
        r["year_check"] = year_check(points)
        r.update(extra_measures(national, weights, strata["area_ha"].sum()))
        r["built_area_growth"]["mapped"] = mapped_growth(r)
        r["unsure_labels"] = int((points["sure"] == 0).sum())
        if tolerant is not None:
            r["tolerant"] = tolerant_measures(
                tolerant.assign(stratum=list(zip(tolerant["city"], tolerant["stratum"]))),
                weights, strata["area_ha"].sum())
        result["national"] = r
        oa = r["overall_accuracy"]
        print(f"national: overall accuracy {oa['estimate']:.3f} ± {oa['margin95']:.3f}")
        if tolerant is not None:
            t = r["tolerant"]
            print(f"national, tolerant: overall accuracy {t['overall_accuracy']['estimate']:.3f}, "
                  f"user's accuracy of new built-up {t['users_accuracy']['new_built']['estimate']:.3f}")
    if len(complete) == len(cfg.CITIES):
        result["growth_comparison"] = growth_comparison(result["cities"])
    cfg.VALIDATION_REPORT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--draw", action="store_true", help="draw the sample (once)")
    parser.add_argument("--cover", action="store_true",
                        help="prepare the second reading of the points labelled not built (once)")
    parser.add_argument("--force", action="store_true",
                        help="with --draw or --cover: erase what was entered")
    args = parser.parse_args()
    if args.draw:
        draw(args.force)
    elif args.cover:
        cover(args.force)
    else:
        report()
