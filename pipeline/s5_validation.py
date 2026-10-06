"""Step 5 - National validation: stratified sample, blind labels, accuracy by city (ROADMAP J4).

1. ``--draw`` draws the same stratified sample in every city (config.settings
   VALIDATION_POINTS): not built, built at the start, and the new built-up area split by
   growth type. The points go to a labelling sheet that does not show the map class.
2. The points are photo-interpreted blind in Google Earth Pro (historical imagery), filling
   labels.csv: is the 10 m pixel built at the start and at the end of the period?
3. Without ``--draw``, the labels are compared with the map: area-weighted accuracies,
   corrected areas and their 95 % margins, by city and for the four cities together
   (src/validation.py, METHODOLOGIE §14).

Inputs : outputs/cities/<city>/urbanisation_year.tif (step 3), growth_type_<start>_<end>.tif (step 4)
Outputs: outputs/validation/labels.csv      sheet to fill (id, city, lon, lat, empty label columns)
         outputs/validation/sample_key.csv  map stratum, class and year of each point
         outputs/validation/strata.csv      pixels, area, weight and points per city and stratum
         outputs/validation/points.kml      points and their 10 m pixel, one folder per city
         outputs/validation/accuracy.json   accuracy report (after labelling)
         data/j4_sample_<city>.png          control map of the sample

Usage
    python -m pipeline.s5_validation --draw          # once; refuses to erase labels already entered
    python -m pipeline.s5_validation                 # accuracy from the labels entered so far
"""
import argparse
import json
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


# --- 3. Accuracy ---------------------------------------------------------------------

def year_check(points: pd.DataFrame) -> dict:
    """Urbanisation year of the map against the year seen on the imagery, for the points
    that are new built-up in both and have a photo-interpreted year."""
    p = points[(points["map_class"] == va.NEW_BUILT) & (points["ref_class"] == va.NEW_BUILT)
               & points["year_built"].notna()]
    diff = p["map_year"] - p["year_built"]
    within = int((diff.abs() <= 1).sum())
    return {"n_points": int(len(p)),
            "within_one_year": round(within / len(p), 3) if len(p) else None,
            "within_one_year_margin95": round(va.binomial_margin(within, len(p)), 3) if len(p) > 1 else None,
            "mean_map_minus_imagery": round(float(diff.mean()), 2) if len(p) else None}


def labelled_points() -> pd.DataFrame:
    labels = pd.read_csv(cfg.VALIDATION_LABELS_CSV)
    key = pd.read_csv(cfg.VALIDATION_KEY_CSV)
    done = labels.dropna(subset=[f"built_{START}", f"built_{END}"])
    bad = done[~done[[f"built_{START}", f"built_{END}"]].isin([0, 1]).all(axis=1)]
    if len(bad):
        raise SystemExit(f"labels must be 0 or 1: {bad['id'].tolist()}")
    points = done.drop(columns=["city", "lon", "lat"]).merge(key, on="id", validate="one_to_one")
    points["ref_class"] = va.reference_class(points[f"built_{START}"], points[f"built_{END}"])
    return points


def report() -> None:
    points = labelled_points()
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
        r["unsure_labels"] = int((p["sure"] == 0).sum())
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
        result["national"] = r
        oa = r["overall_accuracy"]
        print(f"national: overall accuracy {oa['estimate']:.3f} ± {oa['margin95']:.3f}")
    cfg.VALIDATION_REPORT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--draw", action="store_true", help="draw the sample (once)")
    parser.add_argument("--force", action="store_true", help="with --draw: erase the labels entered")
    args = parser.parse_args()
    draw(args.force) if args.draw else report()
