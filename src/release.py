"""Release packages (step 8): what goes into the downloadable data and the site assets.

Pure functions (paths and text only), so they can be unit-tested. A package is a list of
(source file, path in the archive) pairs; step 8 checks that the sources exist and writes
the archives.
"""
from pathlib import Path

DATA_PREFIX = "samareew-data"

GROWTH_CODES = "1 densification, 2 extension, 3 leapfrog, 0 = no new built-up area"


def data_package_files(root: Path, cities: list, growth_periods: list) -> list:
    """Files of the downloadable data, as (source, archive path) pairs under DATA_PREFIX/.

    Tables, rasters by city, full-resolution boundaries (zones/), validation sample and
    labels, cross-check and model agreement, plus the licence, citation and method notes.
    """
    out = root / "outputs"
    pairs = [
        (root / "LICENSE-DATA.md", "LICENSE-DATA.md"),
        (root / "CITATION.cff", "CITATION.cff"),
        (root / "METHODOLOGIE.md", "METHODOLOGIE.md"),
        (out / "tables" / "indicators.csv", "tables/indicators.csv"),
        (out / "tables" / "indicators.json", "tables/indicators.json"),
        (out / "tables" / "units.csv", "tables/units.csv"),
    ]
    for city in cities:
        pairs.append((out / "cities" / city / "urbanisation_year.tif",
                      f"rasters/{city}/urbanisation_year.tif"))
        for start, end in growth_periods:
            name = f"growth_type_{start}_{end}.tif"
            pairs.append((out / "cities" / city / name, f"rasters/{city}/{name}"))
    for name in ("zones", "urban_clusters", "communes", "sectors", "centres"):
        pairs.append((root / "zones" / f"{name}.geojson", f"boundaries/{name}.geojson"))
    pairs.append((out / "site" / "map_notes.geojson", "known_errors/map_notes.geojson"))
    for name in ("labels.csv", "cover_2025.csv", "sample_key.csv", "strata.csv",
                 "accuracy.json", "points.kml"):
        pairs.append((out / "validation" / name, f"validation/{name}"))
    for name in ("agreement.csv", "built_area_sources.csv", "population_census.csv"):
        pairs.append((out / "crosscheck" / name, f"crosscheck/{name}"))
    pairs.append((out / "model" / "accuracy_by_city.json", "model/accuracy_by_city.json"))
    return [(src, f"{DATA_PREFIX}/{arc}") for src, arc in pairs]


def site_asset_files(root: Path, tiles_dir: Path, basemap_dir: Path) -> list:
    """Map archives ignored by git (step 7 tiles, basemap), as (source, archive path) pairs.

    Archive paths are relative to the repository root: the deployment extracts the archive
    there, and `npm run build` then finds the files where it expects them.
    """
    files = sorted(tiles_dir.glob("*.pmtiles"))
    files += sorted(p for p in basemap_dir.rglob("*") if p.is_file())
    return [(p, p.relative_to(root).as_posix()) for p in files]


def data_readme(version: str, released: str, commit: str, cities: dict, years: list,
                growth_periods: list, repo_url: str) -> str:
    """README.md placed at the top of the data archive (English, like the code)."""
    names = ", ".join(cities.values())
    periods = ", ".join(f"{s}–{e}" for s, e in growth_periods)
    return f"""# SamaReew data, version {version}

Urban expansion {years[0]}–{years[-1]} in {len(cities)} Senegalese cities ({names}), mapped
every year from Sentinel-2 imagery with one national Random Forest model.

- Released: {released}, from commit `{commit}` of {repo_url}
- Website: https://bigtapha.github.io/samareew/
- Method, settings and limits: `METHODOLOGIE.md` (French)
- Licence: CC BY 4.0, except `boundaries/communes.geojson` (ODbL 1.0, © OpenStreetMap
  contributors); see `LICENSE-DATA.md`. How to cite: `CITATION.cff`.

## Contents

| Path | Content |
|---|---|
| `tables/indicators.csv` | All indicators, long table: indicator, city, unit, year, value |
| `tables/indicators.json` | One fact sheet per indicator: title, unit, definition, sources, reliability |
| `tables/units.csv` | Spatial units (cities, communes, Touba sectors, directions, rings) and their land area |
| `rasters/<city>/urbanisation_year.tif` | Year a 10 m pixel became built-up: {years[0]} = built in {years[0]} or before, 0 = not built, -1 = no data (int16, EPSG:32628) |
| `rasters/<city>/growth_type_<start>_<end>.tif` | Type of the new built-up area of each period ({periods}): {GROWTH_CODES} (uint8, EPSG:32628) |
| `boundaries/*.geojson` | Study zones, GHSL urban clusters, communes, Touba sectors and centres (EPSG:4326) |
| `known_errors/map_notes.geojson` | Large false detections checked on the imagery and left in the map: outline, mapped area, weight in the city's figures (not exhaustive) |
| `validation/` | National accuracy sample: points and strata, photo-interpreted labels, second reading of {years[-1]}, map class of each point (`sample_key.csv`), accuracy and corrected areas (`accuracy.json`) |
| `crosscheck/` | Comparison with Google Open Buildings, GHSL and the 2023 census (RGPH-5) |
| `model/accuracy_by_city.json` | Agreement of the national model with the reference labels, by city |

## Reading the figures

Tables and rasters give the values of the map. The validation measured how far they can be
trusted: the built-up area of {years[-1]} is right on average, but only about half of the
mapped new built-up area is truly new (the rest is mostly subdivisions or building sites);
growth types are indicative and {years[-1]} is provisional. The map is not corrected by hand:
known large false detections stay in the rasters and tables and are listed in `known_errors/`.
Details in `METHODOLOGIE.md`.
"""
