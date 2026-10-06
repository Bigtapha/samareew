"""Step 4 - Indicators by city, commune, sector, direction and distance ring (ROADMAP §4.3).

Inputs : outputs/cities/<city>/urbanisation_year.tif (step 3), zones/ (step 0),
         WorldPop Global 2 population (downloaded once to data/raw/worldpop/)
Outputs: outputs/tables/indicators.csv   long table: indicator, city, unit_type, unit, year_start, year, value
         outputs/tables/units.csv        spatial units: name and land area
         outputs/tables/indicators.json  format version, sources, one fact sheet per indicator
         outputs/cities/<city>/growth_type_<start>_<end>.tif, data/j3_growth_<city>.png (control map)

Usage
    python -m pipeline.s4_indicators     # always every city: the tables cover all of them
"""
import json
from datetime import date

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio import features
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds

import config as cfg
from config.indicators import INDICATORS, SOURCES, UNIT_TYPES
from src import indicators as ind
from src.zones import DIRECTION_NAMES, DIRECTIONS_8

WORLDPOP_DIR = cfg.DATA_DIR / "raw" / "worldpop"
GROWTH_COLORS = {ind.DENSIFICATION: "#2b8cbe", ind.EXTENSION: "#fe9929", ind.LEAPFROG: "#d7301f"}
GROWTH_LABELS_FR = {ind.DENSIFICATION: "Densification", ind.EXTENSION: "Extension",
                    ind.LEAPFROG: "Saut"}


# --- Spatial units -----------------------------------------------------------

def rasterize(gdf: gpd.GeoDataFrame, shape, transform) -> np.ndarray:
    """Label of the polygon containing each pixel centre (row number, -1 = none)."""
    return features.rasterize(((g, i) for i, g in enumerate(gdf.geometry)), out_shape=shape,
                              transform=transform, fill=-1, dtype="int32")


def city_units(city: str, shape, transform) -> list:
    """[(unit_type, labels, [(unit, public label), ...]), ...] for one city."""
    units = [("city", np.zeros(shape, dtype=np.int32), [(city, cfg.CITIES[city]["name"])])]

    communes = gpd.read_file(cfg.ZONES_DIR / "communes.geojson").to_crs(cfg.ANALYSIS_CRS)
    communes = communes[communes["city"] == city].reset_index(drop=True)
    if communes["commune"].duplicated().any():
        raise ValueError(f"{city}: two communes share a name in communes.geojson")
    units.append(("commune", rasterize(communes, shape, transform),
                  list(zip(communes["commune"], communes["commune"]))))

    if cfg.CITIES[city]["sectors"]:
        sectors = gpd.read_file(cfg.ZONES_DIR / "sectors.geojson").to_crs(cfg.ANALYSIS_CRS)
        sectors = sectors[sectors["city"] == city].reset_index(drop=True)
        units.append(("sector", rasterize(sectors, shape, transform),
                      list(zip(sectors["sector"], sectors["label"]))))

    centres = gpd.read_file(cfg.ZONES_DIR / "centres.geojson").to_crs(cfg.ANALYSIS_CRS)
    centre = centres.loc[centres["city"] == city, "geometry"].iloc[0]
    direction, ring = ind.direction_ring_labels(shape, transform, (centre.x, centre.y),
                                                cfg.RING_WIDTH_M)
    units.append(("direction", direction, [(d, DIRECTION_NAMES[d]) for d in DIRECTIONS_8]))
    km = cfg.RING_WIDTH_M / 1000
    rings = [(f"{r * km:g}-{(r + 1) * km:g} km", f"{r * km:g}–{(r + 1) * km:g} km")
             for r in range(int(ring.max()) + 1)]
    units.append(("ring", ring, rings))
    return units


# --- Population ----------------------------------------------------------------

def worldpop_file(year: int):
    """WorldPop Senegal raster of one year, downloaded once."""
    path = WORLDPOP_DIR / f"sen_pop_{year}.tif"
    if not path.exists():
        WORLDPOP_DIR.mkdir(parents=True, exist_ok=True)
        url = cfg.WORLDPOP_URL.format(year=year)
        print(f"  downloading {url}")
        response = requests.get(url, headers={"User-Agent": cfg.HTTP_USER_AGENT}, timeout=600)
        response.raise_for_status()
        path.write_bytes(response.content)
    return path


def population_grid(year: int, shape, transform, crs) -> np.ndarray:
    """Inhabitants per pixel of the city grid (WorldPop density, nearest neighbour)."""
    with rasterio.open(worldpop_file(year)) as src:
        bounds = transform_bounds(crs, src.crs, *rasterio.transform.array_bounds(*shape, transform))
        margin = 10 * src.res[0]
        window = from_bounds(bounds[0] - margin, bounds[1] - margin, bounds[2] + margin,
                             bounds[3] + margin, src.transform).round_offsets().round_lengths()
        # Dakar reaches the western edge of the raster: clip the window, or the read would be
        # cut while its transform is not (population shifted by the missing columns)
        window = window.intersection(Window(0, 0, src.width, src.height))
        people = src.read(1, window=window, masked=True).filled(0).astype(np.float64)
        win_transform = src.window_transform(window)
        src_crs = src.crs
    people[people < 0] = 0
    density = people / ind.cell_areas_m2(win_transform.f, win_transform.a, people.shape[0])[:, None]
    out = np.zeros(shape, dtype=np.float64)
    reproject(density, out, src_transform=win_transform, src_crs=src_crs,
              dst_transform=transform, dst_crs=crs, resampling=Resampling.nearest)
    return out * abs(transform.a * transform.e)


# --- Indicators ------------------------------------------------------------------

def indicator_rows(city, unit_type, labels, units, first_year, pixel_area, pop, growth):
    """Long-table rows of every indicator for one set of units (``pop``: (n_units, n_years))."""
    years = cfg.PUBLISHED_YEARS
    n = len(units)
    built_px, land_px = ind.built_counts(first_year, labels, n, years)
    built = built_px * pixel_area / 10_000          # ha, (n_units, n_years)
    land = land_px * pixel_area / 10_000

    rows = []

    def add(indicator, i, year, value, digits, year_start=None):
        if np.isfinite(value):
            rows.append({"indicator": indicator, "city": city, "unit_type": unit_type,
                         "unit": units[i][0], "year_start": year_start, "year": year,
                         "value": round(float(value), digits)})

    with np.errstate(divide="ignore", invalid="ignore"):
        index = np.where(built[:, :1] > 0, built / built[:, :1] * 100, np.nan)
        share = np.where(land[:, None] > 0, built / land[:, None] * 100, np.nan)
        per_capita = np.where(pop >= cfg.MIN_POPULATION, built * 10_000 / pop, np.nan)
    for i in range(n):
        if land[i] == 0:
            continue
        for j, year in enumerate(years):
            add("built_area_ha", i, year, built[i, j], 1)
            if j > 0:
                add("new_built_ha", i, year, built[i, j] - built[i, j - 1], 1)
            add("growth_index", i, year, index[i, j], 1)
            add("built_share_pct", i, year, share[i, j], 1)
            add("population", i, year, pop[i, j], 0)
            add("built_m2_per_capita", i, year, per_capita[i, j], 1)

    for (start, end), types in growth.items():
        area = {t: ind.unit_sums((types == t).astype(np.float64), labels, n) * pixel_area / 10_000
                for t in ind.GROWTH_TYPES}
        total = sum(area.values())
        s, e = years.index(start), years.index(end)
        for i in range(n):
            if land[i] == 0:
                continue
            for t, name in ind.GROWTH_TYPES.items():
                add(f"growth_{name}_ha", i, end, area[t][i], 1, start)
                if total[i] > 0:
                    add(f"growth_{name}_share_pct", i, end, area[t][i] / total[i] * 100, 1, start)
            if pop[i, s] >= cfg.MIN_POPULATION:
                add("sdg_11_3_1", i, end, ind.sdg_11_3_1(built[i, s], built[i, e], pop[i, s], pop[i, e]),
                    2, start)
    unit_rows = [{"city": city, "unit_type": unit_type, "unit": u, "label": label,
                  "land_ha": round(float(land[i]), 1)} for i, (u, label) in enumerate(units) if land[i] > 0]
    return rows, unit_rows


def growth_map(first_year, types, name, start, end, path):
    """Control map of the growth types of one period."""
    show = np.zeros(first_year.shape, dtype=np.uint8)            # 0 = not built
    show[(first_year > 0) & (first_year <= start)] = 1           # 1 = built at the start
    show[types > 0] = types[types > 0] + 1                       # 2..4 = growth types
    cmap = ListedColormap(["#f2efe9", "#6b6b6b"] + [GROWTH_COLORS[t] for t in ind.GROWTH_TYPES])
    cmap.set_bad("white")
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(np.ma.masked_where(first_year < 0, show), cmap=cmap, vmin=0, vmax=4,
              interpolation="nearest")
    ax.set_title(f"Type de croissance — {name}, {start} → {end}")
    ax.set_axis_off()
    handles = [Patch(color="#6b6b6b", label=f"Bâti en {start}")] + [
        Patch(color=GROWTH_COLORS[t], label=GROWTH_LABELS_FR[t]) for t in ind.GROWTH_TYPES]
    ax.legend(handles=handles, loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_city(city: str) -> tuple:
    out_dir = cfg.city_output_dir(city)
    with rasterio.open(out_dir / cfg.FIRST_YEAR_TIF) as src:
        first_year = src.read(1)
        profile, transform, crs = src.profile, src.transform, src.crs
    pixel_size = abs(transform.a)
    pixel_area = abs(transform.a * transform.e)
    name = cfg.CITIES[city]["name"]

    growth = {}
    for start, end in cfg.GROWTH_PERIODS:
        types = ind.growth_types(first_year, start, end, pixel_size,
                                 cfg.GROWTH_FRINGE_M, cfg.GROWTH_MAX_HOLE_HA,
                                 cfg.GROWTH_CIRCLE_RADIUS_M, cfg.GROWTH_MIN_BUILT_SHARE)
        growth[(start, end)] = types
        with rasterio.open(out_dir / cfg.GROWTH_TYPE_TIF.format(start=start, end=end), "w",
                           **{**profile, "dtype": "uint8", "nodata": None, "compress": "deflate"}) as dst:
            dst.write(types, 1)
            dst.update_tags(description="Growth type: 1 densification, 2 extension, 3 leapfrog")
    first, last = cfg.GROWTH_PERIODS[-1]
    growth_map(first_year, growth[(first, last)], name, first, last,
               cfg.DATA_DIR / f"j3_growth_{city}.png")

    unit_sets = city_units(city, first_year.shape, transform)
    # Population summed per unit one year at a time (a 10 m grid per year would not fit in memory)
    inside = first_year >= 0
    pop = {unit_type: np.zeros((len(units), len(cfg.PUBLISHED_YEARS))) for unit_type, _, units in unit_sets}
    for j, year in enumerate(cfg.PUBLISHED_YEARS):
        people = population_grid(year, first_year.shape, transform, crs)
        for unit_type, labels, units in unit_sets:
            pop[unit_type][:, j] = ind.unit_sums(people, labels, len(units), inside)

    rows, unit_rows = [], []
    for unit_type, labels, units in unit_sets:
        r, u = indicator_rows(city, unit_type, labels, units, first_year, pixel_area,
                              pop[unit_type], growth)
        rows += r
        unit_rows += u
    return rows, unit_rows


def summary(table: pd.DataFrame) -> None:
    city = table[table["unit_type"] == "city"]
    first, last = cfg.PUBLISHED_YEARS[0], cfg.PUBLISHED_YEARS[-1]
    p_start, p_end = cfg.GROWTH_PERIODS[-1]
    pick = {
        f"built_ha_{last}": ("built_area_ha", None, last),
        f"pop_{first}": ("population", None, first),
        f"pop_{last}": ("population", None, last),
        f"m2_hab_{first}": ("built_m2_per_capita", None, first),
        f"m2_hab_{last}": ("built_m2_per_capita", None, last),
        "densif_%": ("growth_densification_share_pct", p_start, p_end),
        "extens_%": ("growth_extension_share_pct", p_start, p_end),
        "saut_%": ("growth_leapfrog_share_pct", p_start, p_end),
        "odd_11.3.1": ("sdg_11_3_1", p_start, p_end),
    }
    out = {}
    for column, (indicator, start, year) in pick.items():
        sel = city[(city["indicator"] == indicator) & (city["year"] == year)]
        if start is not None:
            sel = sel[sel["year_start"] == start]
        out[column] = sel.set_index("city")["value"]
    print(pd.DataFrame(out).to_string())


def main():
    missing = [c for c in cfg.CITIES if not (cfg.city_output_dir(c) / cfg.FIRST_YEAR_TIF).exists()]
    if missing:
        raise SystemExit(f"No urbanisation map for {missing}: run python -m pipeline.s3_postprocess")
    rows, unit_rows = [], []
    for city in cfg.CITIES:
        print(f"Indicators for {city}...")
        r, u = run_city(city)
        rows += r
        unit_rows += u

    cfg.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(rows).astype({"year_start": "Int64"})
    unknown = set(table["indicator"]) - set(INDICATORS)
    if unknown:
        raise ValueError(f"indicators without a fact sheet in config/indicators.py: {unknown}")
    table.to_csv(cfg.INDICATORS_CSV, index=False)
    pd.DataFrame(unit_rows).to_csv(cfg.UNITS_CSV, index=False)
    meta = {
        "format_version": cfg.FORMAT_VERSION,
        "generated": date.today().isoformat(),
        "years": cfg.PUBLISHED_YEARS,
        "periods": cfg.GROWTH_PERIODS,
        "files": {"indicators": cfg.INDICATORS_CSV.name, "units": cfg.UNITS_CSV.name},
        "unit_types": UNIT_TYPES,
        "sources": SOURCES,
        "indicators": INDICATORS,
    }
    cfg.INDICATORS_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(table)} rows, {len(unit_rows)} units -> {cfg.TABLES_DIR.relative_to(cfg.ROOT)}")
    summary(table)


if __name__ == "__main__":
    main()
