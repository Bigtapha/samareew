"""Step 3 - Local post-processing of every city: urbanisation year, statistics, static maps.

Input : data/cities/<city>/built_by_year.tif (step 2)
Output, in outputs/cities/<city>/: urbanisation_year.tif, built_area_by_year.csv,
        urban_expansion_map.png, built_area_chart.png

Usage
    python -m pipeline.s3_postprocess                 # every city with a stack from step 2
    python -m pipeline.s3_postprocess --city touba    # one city
"""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np
import rasterio

import config as cfg
from src import postprocess as pp


def save_geotiff(array, profile, path):
    profile = profile.copy()
    profile.update(count=1, dtype="int16", nodata=pp.NODATA_OUT, compress="deflate")
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)
        dst.update_tags(description="Year of urbanisation (0 = not built, -1 = no data)")


def static_map(first_year, name, path):
    classes = np.ma.masked_where(first_year == pp.NODATA_OUT,   # outside the study area
                                 pp.period_index(first_year, cfg.PERIODS))
    cmap = ListedColormap(["#f2efe9"] + cfg.PERIOD_COLORS)
    cmap.set_bad("white")
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(classes, cmap=cmap, vmin=0, vmax=len(cfg.PERIODS), interpolation="nearest")
    ax.set_title(f"Urban expansion - {name}, {cfg.PUBLISHED_YEARS[0]}-{cfg.PUBLISHED_YEARS[-1]}")
    ax.set_axis_off()
    handles = [Patch(color=c, label=p[2]) for c, p in zip(cfg.PERIOD_COLORS, cfg.PERIODS)]
    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=True)
    ax.text(0.99, 0.01, "Source: Copernicus Sentinel-2, processed in Google Earth Engine",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="#555")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart(stats, name, path):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(stats["year"], stats["built_area_ha"], color="#d95f0e")
    ax.set_ylabel("Built-up area (ha)")
    ax.set_title(f"Built-up area per year - {name}")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_city(city: str) -> None:
    stack_path = cfg.city_data_dir(city) / cfg.BUILT_STACK_TIF
    out_dir = cfg.city_output_dir(city)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = cfg.CITIES[city]["name"]
    with rasterio.open(stack_path) as src:
        stack = src.read()
        profile = src.profile
        pixel_area = abs(src.transform.a * src.transform.e)

    if stack.shape[0] != len(cfg.YEARS):
        raise SystemExit(f"{stack_path}: expected {len(cfg.YEARS)} bands, found {stack.shape[0]}")

    missing = [(y, round(float((b == pp.NODATA_IN).mean()) * 100, 1))
               for y, b in zip(cfg.YEARS, stack)]
    print("  share of pixels without clear observation (%):", dict(missing))

    first_year = pp.urbanisation_year(stack, cfg.YEARS, cfg.PERSISTENCE_RATIO)
    # Built only in the last year: not confirmed yet, so not published (counted as not built)
    first_year[first_year > cfg.PUBLISHED_YEARS[-1]] = 0
    save_geotiff(first_year, profile, out_dir / cfg.FIRST_YEAR_TIF)

    stats = pp.area_by_year(first_year, cfg.PUBLISHED_YEARS, pixel_area)
    stats.to_csv(out_dir / cfg.STATS_CSV, index=False)
    print(stats.to_string(index=False))

    static_map(first_year, name, out_dir / "urban_expansion_map.png")
    chart(stats, name, out_dir / "built_area_chart.png")
    print(f"  saved results in {out_dir.relative_to(cfg.ROOT)}")


def main(cities: list):
    done = []
    for city in cities:
        if not (cfg.city_data_dir(city) / cfg.BUILT_STACK_TIF).exists():
            print(f"{city}: no stack from step 2, skipped")
            continue
        print(f"Post-processing {city}...")
        run_city(city)
        done.append(city)
    if not done:
        raise SystemExit("Nothing to do: run python -m pipeline.s2_classify first")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", choices=list(cfg.CITIES), help="only this city (default: all)")
    args = parser.parse_args()
    main([args.city] if args.city else list(cfg.CITIES))
