"""Step 6 - Cross-check of our built-up maps with GHSL and Google Open Buildings (ROADMAP J3).

References (brought to our 10 m grid by Earth Engine, downloaded once):
- Open Buildings Temporal v1 (Google): yearly building maps 2016-2023, 4 m effective;
- GHSL built-up surface: 10 m in 2018, and 100 m every 5 years 1975-2030 (2025 and 2030
  are projections).
Both measure roofs; our map measures built-up pixels: the areas differ by definition, so
the checks measure where the maps agree (src/crosscheck.py, METHODOLOGIE §13).
The WorldPop population of step 4 is also checked against the 2013 and 2023 censuses (ANSD
directory of localities) on the communes entirely inside a zone.

Inputs : outputs/cities/<city>/urbanisation_year.tif (step 3), data/worldpop_by_commune.csv (step 4)
Outputs: outputs/crosscheck/built_area_sources.csv   area per city, source and year
         outputs/crosscheck/agreement.csv            agreement measures per city
         outputs/crosscheck/population_census.csv    WorldPop and census per commune
         outputs/crosscheck/sdg_census.csv           SDG 11.3.1 with the census or WorldPop, by city
         data/cities/<city>/reference_roofs.tif, ghsl_built_surface.json (downloads)
         data/j3_crosscheck.png                      growth of the three sources (control)

Usage
    python -m pipeline.s6_crosscheck              # uses cached downloads when present
    python -m pipeline.s6_crosscheck --refresh    # download the references again
    python -m pipeline.s6_crosscheck --census     # only WorldPop and SDG 11.3.1 against the census
"""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

import config as cfg
from src import crosscheck as cc
from src import indicators as ind
from pipeline.s4_indicators import census_by_commune, census_key, whole_communes

_ee_ready = False


def earth_engine():
    global _ee_ready
    from src import gee_utils as gu
    if not _ee_ready:
        gu.init(cfg.GEE_PROJECT)
        _ee_ready = True
    return gu


def download_references(city: str, refresh: bool) -> None:
    """Roof fractions on our grid, and the GHSL series of the zone (cached in data/)."""
    data_dir = cfg.city_data_dir(city)
    roofs = data_dir / cfg.REFERENCE_ROOFS_TIF
    series = data_dir / cfg.GHSL_SERIES_JSON
    if roofs.exists() and series.exists() and not refresh:
        return
    import ee
    import geemap
    gu = earth_engine()
    zone = gu.city_zone(cfg, city)
    if refresh or not series.exists():
        series.write_text(json.dumps(gu.ghsl_built_surface_series(zone, cfg.GHSL_BUILT_COLLECTION), indent=2))
    if roofs.exists() and not refresh:
        return
    with rasterio.open(cfg.city_output_dir(city) / cfg.FIRST_YEAR_TIF) as src:
        b = src.bounds
    region = ee.Geometry.Rectangle([b.left, b.bottom, b.right, b.top], cfg.ANALYSIS_CRS, False)
    image = gu.roof_fraction_layers(zone, cfg.OB_YEARS, cfg.OB_PRESENCE_THRESHOLD,
                                    cfg.ANALYSIS_CRS, cfg.SCALE)
    geemap.download_ee_image(image, str(roofs), region=region, crs=cfg.ANALYSIS_CRS,
                             scale=cfg.SCALE, dtype="uint8", max_tile_size=cfg.DOWNLOAD_MAX_TILE_MB)


def run_city(city: str) -> tuple:
    with rasterio.open(cfg.city_output_dir(city) / cfg.FIRST_YEAR_TIF) as src:
        first_year = src.read(1)
        transform = src.transform
    with rasterio.open(cfg.city_data_dir(city) / cfg.REFERENCE_ROOFS_TIF) as ref:
        if ref.shape != first_year.shape or ref.transform != transform:
            raise ValueError(f"{city}: {cfg.REFERENCE_ROOFS_TIF} is not on the grid of our map; use --refresh")
        roofs = dict(zip(ref.descriptions, ref.read()))
    ghsl_series = {int(k): v for k, v in
                   json.loads((cfg.city_data_dir(city) / cfg.GHSL_SERIES_JSON).read_text()).items()}
    pixel_area_ha = abs(transform.a * transform.e) / 10_000
    inside = first_year >= 0

    def ours(year):
        return (first_year > 0) & (first_year <= year)

    def roof_ha(roof):
        return float(roof[inside].sum(dtype=np.float64)) / 100 * pixel_area_ha

    areas, agreement = [], []

    def agree(metric, reference, group, year, value):
        agreement.append({"city": city, "metric": metric, "reference": reference, "group": group,
                          "year": year, "value": round(value, 3)})

    for year in cfg.PUBLISHED_YEARS:
        areas.append({"city": city, "source": "samareew", "year": year,
                      "area_ha": round(ours(year)[inside].sum() * pixel_area_ha, 1), "projected": False})
    for year in cfg.OB_YEARS:
        roof = roofs[f"ob_{year}"]
        areas.append({"city": city, "source": "open_buildings", "year": year,
                      "area_ha": round(roof_ha(roof), 1), "projected": False})
        agree("roof_share_in_our_built", "open_buildings", "", year,
              cc.roof_share_inside(roof, ours(year), inside) * 100)
        agree("cell_correlation", "open_buildings", "", year,
              cc.cell_correlation(ours(year), roof, inside, cfg.CHECK_CELL_PX))
    areas.append({"city": city, "source": "ghsl_10m", "year": 2018,
                  "area_ha": round(roof_ha(roofs["ghsl_2018"]), 1), "projected": False})
    agree("roof_share_in_our_built", "ghsl_10m", "", 2018,
          cc.roof_share_inside(roofs["ghsl_2018"], ours(2018), inside) * 100)
    agree("cell_correlation", "ghsl_10m", "", 2018,
          cc.cell_correlation(ours(2018), roofs["ghsl_2018"], inside, cfg.CHECK_CELL_PX))
    for epoch, ha in sorted(ghsl_series.items()):
        areas.append({"city": city, "source": "ghsl_100m", "year": epoch, "area_ha": round(ha, 1),
                      "projected": epoch > cfg.GHSL_LAST_OBSERVED_EPOCH})

    # Confirmation: share of our pixels with reference roofs within 30 m, by group
    start, end = cfg.OB_YEARS[0], cfg.OB_YEARS[-1]
    types = ind.growth_types(first_year, start, end, abs(transform.a), cfg.GROWTH_FRINGE_M,
                             cfg.GROWTH_MAX_HOLE_HA, cfg.GROWTH_CIRCLE_RADIUS_M, cfg.GROWTH_MIN_BUILT_SHARE)
    for reference, band, year in [("open_buildings", f"ob_{end}", end), ("ghsl_10m", "ghsl_2018", 2018)]:
        groups = {"not_built": inside & ((first_year == 0) | (first_year > year)),
                  f"built_{start}": first_year == start,
                  f"new_{start + 1}_{year}": (first_year > start) & (first_year <= year)}
        if year == end:
            groups.update({f"new_{name}": types == t for t, name in ind.GROWTH_TYPES.items()})
        conf = cc.confirmed(roofs[band], cfg.CHECK_WINDOW_PX, cfg.CHECK_MIN_ROOF_PCT)
        for group, rate in cc.confirmation_rates(conf, groups).items():
            agree("confirmed_pct", reference, group, year, rate)

    # Growth over common periods
    a = {(r["source"], r["year"]): r["area_ha"] for r in areas}
    agree("growth_pct", "samareew", f"{start}-{end}", end, cc.growth_pct(a["samareew", start], a["samareew", end]))
    agree("growth_pct", "open_buildings", f"{start}-{end}", end,
          cc.growth_pct(a["open_buildings", start], a["open_buildings", end]))
    agree("annual_growth_pct", "samareew", "2016-2020", 2020,
          cc.annual_growth_pct(a["samareew", 2016], a["samareew", 2020], 4))
    agree("annual_growth_pct", "ghsl_100m", "2015-2020", 2020,
          cc.annual_growth_pct(a["ghsl_100m", 2015], a["ghsl_100m", 2020], 5))
    return areas, agreement


def census_check() -> pd.DataFrame:
    """WorldPop (step 4, by commune) against the census, on the communes entirely inside a zone."""
    if not cfg.WORLDPOP_COMMUNES_CSV.exists():
        raise SystemExit(f"{cfg.WORLDPOP_COMMUNES_CSV} not found: run python -m pipeline.s4_indicators")
    pop = pd.read_csv(cfg.WORLDPOP_COMMUNES_CSV).set_index(["city", "commune", "year"])["population"]
    first = cfg.PUBLISHED_YEARS[0]
    rows = []
    for city in cfg.CITIES:
        census = {year: census_by_commune(city, year) for year in cfg.CENSUS_YEARS}
        for commune in whole_communes(city):
            key = census_key(commune)
            c13, c23 = census[2013].get(key, np.nan), census[2023].get(key, np.nan)
            w16, w23 = pop.get((city, commune, first), np.nan), pop.get((city, commune, 2023), np.nan)
            rows.append({"city": city, "commune": commune, "census_2013": c13, "census_2023": c23,
                         f"worldpop_{first}": w16, "worldpop_2023": w23,
                         "worldpop_to_census": round(w23 / c23, 3) if c23 > 0 else np.nan,
                         "census_annual_growth_pct": round(cc.annual_growth_pct(c13, c23, 10), 2),
                         "worldpop_annual_growth_pct": round(cc.annual_growth_pct(w16, w23, 2023 - first), 2)})
    return pd.DataFrame(rows)


def census_sdg(census: pd.DataFrame) -> pd.DataFrame:
    """SDG 11.3.1 on the communes counted in both censuses: population growth from the census
    (2013-2023) or from WorldPop (2016-2023), built-up growth from the map (2016-2023).
    WorldPop spreads the population over a satellite map of the built-up area, so its growth
    may follow the built-up area: the census tells whether the ratio is partly circular."""
    first, last = cfg.PUBLISHED_YEARS[0], cfg.CENSUS_YEARS[-1]
    table = pd.read_csv(cfg.INDICATORS_CSV)
    built = table[(table["indicator"] == "built_area_ha") & (table["unit_type"] == "commune")]
    built = built.set_index(["city", "unit", "year"])["value"]
    c = census.dropna(subset=["census_2013", "census_2023", f"worldpop_{first}", "worldpop_2023"]).copy()
    c["built_start"] = [built.get((ci, co, first), np.nan) for ci, co in zip(c["city"], c["commune"])]
    c["built_end"] = [built.get((ci, co, last), np.nan) for ci, co in zip(c["city"], c["commune"])]
    rows = []
    for city, g in c.groupby("city", sort=False):
        s = g[["census_2013", "census_2023", f"worldpop_{first}", "worldpop_2023",
               "built_start", "built_end"]].sum()
        n_census, n_map = cfg.CENSUS_YEARS[-1] - cfg.CENSUS_YEARS[0], last - first
        rows.append({
            "city": city, "communes": len(g),
            "census_2013": int(s["census_2013"]), "census_2023": int(s["census_2023"]),
            f"worldpop_{first}": round(s[f"worldpop_{first}"]), "worldpop_2023": round(s["worldpop_2023"]),
            f"built_{first}_ha": round(s["built_start"]), f"built_{last}_ha": round(s["built_end"]),
            "census_annual_growth_pct": round(cc.annual_growth_pct(s["census_2013"], s["census_2023"], n_census), 2),
            "worldpop_annual_growth_pct": round(cc.annual_growth_pct(s[f"worldpop_{first}"], s["worldpop_2023"], n_map), 2),
            "built_annual_growth_pct": round(cc.annual_growth_pct(s["built_start"], s["built_end"], n_map), 2),
            "sdg_11_3_1_census": round(ind.sdg_11_3_1_annual(s["built_start"], s["built_end"], n_map,
                                                             s["census_2013"], s["census_2023"], n_census), 2),
            "sdg_11_3_1_worldpop": round(ind.sdg_11_3_1(s["built_start"], s["built_end"],
                                                        s[f"worldpop_{first}"], s["worldpop_2023"]), 2),
        })
    return pd.DataFrame(rows)


def growth_chart(areas: pd.DataFrame, path) -> None:
    styles = {"samareew": ("SamaReew (pixels bâtis)", "#d95f0e", "-"),
              "open_buildings": ("Open Buildings (toits)", "#2b8cbe", "-"),
              "ghsl_100m": ("GHSL (toits, 100 m)", "#555555", "--")}
    cities = list(cfg.CITIES)
    fig, axes = plt.subplots(1, len(cities), figsize=(4 * len(cities), 3.6), sharey=True)
    for ax, city in zip(axes, cities):
        for source, (label, color, ls) in styles.items():
            d = areas[(areas["city"] == city) & (areas["source"] == source)
                      & (areas["year"] >= 2015)].sort_values("year")
            base = d["area_ha"].iloc[0]
            ax.plot(d["year"], d["area_ha"] / base * 100, ls, color=color, marker="o", ms=3, label=label)
        ax.set_title(cfg.CITIES[city]["name"])
        ax.grid(alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Indice (première année = 100)")
    axes[0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Croissance du bâti selon trois sources (GHSL 2025 : projection)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def census_outputs() -> None:
    census = census_check()
    census.to_csv(cfg.CROSSCHECK_DIR / "population_census.csv", index=False)
    by_city = census.groupby("city", sort=False).agg(
        communes=("commune", "size"), census_2023=("census_2023", "sum"),
        worldpop_2023=("worldpop_2023", "sum"), median_ratio=("worldpop_to_census", "median"))
    by_city["ratio_of_sums"] = (by_city["worldpop_2023"] / by_city["census_2023"]).round(3)
    print(by_city.to_string())
    sdg = census_sdg(census)
    sdg.to_csv(cfg.CROSSCHECK_DIR / "sdg_census.csv", index=False)
    print(sdg.to_string(index=False))


def main(refresh: bool):
    missing = [c for c in cfg.CITIES if not (cfg.city_output_dir(c) / cfg.FIRST_YEAR_TIF).exists()]
    if missing:
        raise SystemExit(f"No urbanisation map for {missing}: run python -m pipeline.s3_postprocess")
    areas, agreement = [], []
    for city in cfg.CITIES:
        print(f"Cross-check of {city}...")
        download_references(city, refresh)
        a, g = run_city(city)
        areas += a
        agreement += g
    cfg.CROSSCHECK_DIR.mkdir(parents=True, exist_ok=True)
    areas, agreement = pd.DataFrame(areas), pd.DataFrame(agreement)
    areas.to_csv(cfg.CROSSCHECK_DIR / "built_area_sources.csv", index=False)
    agreement.to_csv(cfg.CROSSCHECK_DIR / "agreement.csv", index=False)
    growth_chart(areas, cfg.DATA_DIR / "j3_crosscheck.png")

    census_outputs()
    print(agreement.pivot_table(index=["metric", "reference", "group", "year"], columns="city",
                                values="value").round(2).to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="download the references again")
    parser.add_argument("--census", action="store_true",
                        help="only the population checks against the census (no rasters)")
    args = parser.parse_args()
    if args.census:
        census_outputs()
    else:
        main(args.refresh)
