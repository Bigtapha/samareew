"""Step 6 - Cross-check of our built-up maps with GHSL and Google Open Buildings (ROADMAP J3).

References (brought to our 10 m grid by Earth Engine, downloaded once):
- Open Buildings Temporal v1 (Google): yearly building maps 2016-2023, 4 m effective;
- GHSL built-up surface: 10 m in 2018, and 100 m every 5 years 1975-2030 (2025 and 2030
  are projections).
Both measure roofs; our map measures built-up pixels: the areas differ by definition, so
the checks measure where the maps agree (src/crosscheck.py, METHODOLOGIE §13).
The WorldPop population of step 4 is also checked against the 2013 and 2023 censuses (ANSD
directory of localities) on the communes entirely inside a zone.

Inputs : outputs/cities/<city>/urbanisation_year.tif (step 3), outputs/tables/indicators.csv (step 4)
Outputs: outputs/crosscheck/built_area_sources.csv   area per city, source and year
         outputs/crosscheck/agreement.csv            agreement measures per city
         outputs/crosscheck/population_census.csv    WorldPop and census per commune
         data/cities/<city>/reference_roofs.tif, ghsl_built_surface.json (downloads)
         data/j3_crosscheck.png                      growth of the three sources (control)

Usage
    python -m pipeline.s6_crosscheck              # uses cached downloads when present
    python -m pipeline.s6_crosscheck --refresh    # download the references again
"""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
import requests

import config as cfg
from src import crosscheck as cc
from src import indicators as ind

CENSUS_DIR = cfg.DATA_DIR / "raw" / "rgph5"
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


def census_table(region: str, year: int) -> pd.DataFrame:
    """Census population of every neighbourhood / village of a region (ANSD, cached)."""
    path = CENSUS_DIR / f"localites_{region.lower()}_{year}.csv"
    if not path.exists():
        CENSUS_DIR.mkdir(parents=True, exist_ok=True)
        url = cfg.CENSUS_URL.format(year=year, region=region)
        print(f"  downloading {url}")
        # The ANSD server does not send its intermediate certificate: verification fails
        response = requests.get(url, headers={"User-Agent": cfg.HTTP_USER_AGENT}, timeout=600,
                                verify=False)
        response.raise_for_status()
        path.write_bytes(response.content)
    return pd.read_csv(path)


def census_check(indicators: pd.DataFrame) -> pd.DataFrame:
    """WorldPop (step 4) against the census, on the communes entirely inside a zone."""
    communes = gpd.read_file(cfg.ZONES_DIR / "communes.geojson")
    communes = communes[communes["share_of_commune"] >= cfg.CENSUS_MIN_SHARE]
    pop = indicators[(indicators["indicator"] == "population") & (indicators["unit_type"] == "commune")]
    pop = pop.set_index(["city", "unit", "year"])["value"]
    first = cfg.PUBLISHED_YEARS[0]
    rows = []
    for city, group in communes.groupby("city", sort=False):
        census = {}
        for year in cfg.CENSUS_YEARS:
            table = pd.concat([census_table(r, year) for r in cfg.CITIES[city]["census_regions"]])
            census[year] = table.groupby(table["COMMUNE"].map(cc.name_key))["POPULATION"].sum()
        for commune in group["commune"]:
            key = cc.name_key(cfg.CENSUS_COMMUNE_ALIASES.get(commune, commune))
            c13, c23 = census[2013].get(key, np.nan), census[2023].get(key, np.nan)
            w16, w23 = pop.get((city, commune, first), np.nan), pop.get((city, commune, 2023), np.nan)
            rows.append({"city": city, "commune": commune, "census_2013": c13, "census_2023": c23,
                         f"worldpop_{first}": w16, "worldpop_2023": w23,
                         "worldpop_to_census": round(w23 / c23, 3) if c23 > 0 else np.nan,
                         "census_annual_growth_pct": round(cc.annual_growth_pct(c13, c23, 10), 2),
                         "worldpop_annual_growth_pct": round(cc.annual_growth_pct(w16, w23, 2023 - first), 2)})
    table = pd.DataFrame(rows)
    missing = table.loc[table["census_2023"].isna(), "commune"].tolist()
    if missing:
        raise ValueError(f"communes not found in the 2023 census: {missing}; "
                         "add them to CENSUS_COMMUNE_ALIASES in config/settings.py")
    return table


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

    if not cfg.INDICATORS_CSV.exists():
        raise SystemExit(f"{cfg.INDICATORS_CSV} not found: run python -m pipeline.s4_indicators")
    census = census_check(pd.read_csv(cfg.INDICATORS_CSV))
    census.to_csv(cfg.CROSSCHECK_DIR / "population_census.csv", index=False)
    by_city = census.groupby("city", sort=False).agg(
        communes=("commune", "size"), census_2023=("census_2023", "sum"),
        worldpop_2023=("worldpop_2023", "sum"), median_ratio=("worldpop_to_census", "median"))
    by_city["ratio_of_sums"] = (by_city["worldpop_2023"] / by_city["census_2023"]).round(3)
    print(by_city.to_string())
    print(agreement.pivot_table(index=["metric", "reference", "group", "year"], columns="city",
                                values="value").round(2).to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="download the references again")
    main(parser.parse_args().refresh)
