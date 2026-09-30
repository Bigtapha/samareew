"""Step 2 - Local post-processing: urbanisation year, statistics and static maps.

Input : data/built_by_year.tif (from step 1)
Output: outputs/urbanisation_year.tif, outputs/built_area_by_year.csv,
        outputs/urban_expansion_map.png, outputs/built_area_chart.png
"""
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


def static_map(first_year, path):
    classes = np.ma.masked_where(first_year == pp.NODATA_OUT,   # outside the study area
                                 pp.period_index(first_year, cfg.PERIODS))
    cmap = ListedColormap(["#f2efe9"] + cfg.PERIOD_COLORS)
    cmap.set_bad("white")
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(classes, cmap=cmap, vmin=0, vmax=len(cfg.PERIODS), interpolation="nearest")
    ax.set_title(f"Urban expansion - {cfg.AOI_NAME}, {cfg.YEARS[0]}-{cfg.YEARS[-1]}")
    ax.set_axis_off()
    handles = [Patch(color=c, label=p[2]) for c, p in zip(cfg.PERIOD_COLORS, cfg.PERIODS)]
    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=True)
    ax.text(0.99, 0.01, "Source: Copernicus Sentinel-2, processed in Google Earth Engine",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="#555")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart(stats, path):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(stats["year"], stats["built_area_ha"], color="#d95f0e")
    ax.set_ylabel("Built-up area (ha)")
    ax.set_title("Built-up area per year")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    cfg.OUTPUT_DIR.mkdir(exist_ok=True)
    with rasterio.open(cfg.BUILT_STACK_TIF) as src:
        stack = src.read()
        profile = src.profile
        pixel_area = abs(src.transform.a * src.transform.e)

    if stack.shape[0] != len(cfg.YEARS):
        raise SystemExit(f"Expected {len(cfg.YEARS)} bands, found {stack.shape[0]}")

    missing = [(y, round(float((b == pp.NODATA_IN).mean()) * 100, 1))
               for y, b in zip(cfg.YEARS, stack)]
    print("Share of pixels without clear observation (%):", dict(missing))

    first_year = pp.urbanisation_year(stack, cfg.YEARS, cfg.PERSISTENCE_RATIO)
    save_geotiff(first_year, profile, cfg.FIRST_YEAR_TIF)

    stats = pp.area_by_year(first_year, cfg.YEARS, pixel_area)
    stats.to_csv(cfg.STATS_CSV, index=False)
    print(stats.to_string(index=False))

    static_map(first_year, cfg.OUTPUT_DIR / "urban_expansion_map.png")
    chart(stats, cfg.OUTPUT_DIR / "built_area_chart.png")
    print(f"Saved results in {cfg.OUTPUT_DIR}. Next: python 03_make_webmap.py")


if __name__ == "__main__":
    main()
