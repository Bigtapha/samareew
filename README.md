# SamaReew — urban expansion in Senegal

**SamaReew** (_sama réew_, "my country" in Wolof) is a public, open-data atlas that compares
Senegalese cities, inspired by [Our World in Data](https://ourworldindata.org). The first
theme is **urban expansion, 2016–2026**, in four cities: **Dakar, Touba, Thiès and Mbour**.

Built-up areas are mapped every year from **Sentinel-2** imagery with **Google Earth Engine**
and **one national Random Forest** model, then cleaned with a temporal consistency filter
and checked by an independent accuracy assessment.

The plan, the decisions taken and the decisions still open are in **[ROADMAP.md](ROADMAP.md)**:
read it first.

## Project status

| Milestone | Status |
|---|---|
| J0 — Setup (git, GitHub, licences) | Done |
| J1 — Study zones (zones, communes, centres, Touba sectors) | Done, frozen in [`zones/`](zones/README.md) |
| **J2 — National model and classification** | **In progress** on branch `j2-modele-national` |
| J3 — Indicators and cross-check with GHSL / Open Buildings | To do |
| J4 — National validation (~480 photo-interpreted points) | To do |
| J5 — Website v1 | To do |
| J6 — Publication | To do |

**J2 so far**: the code has been reorganised into a national pipeline (`config/`,
`pipeline/`). Steps 1 and 3 were smoke-tested (sampling and training on Touba with a few
points; post-processing reproduces the Dakar case-study figures exactly).

**Next step**: run step 1 for real on the four cities, check the agreement by city in
`outputs/model/accuracy_by_city.json`, then run step 2 (yearly stacks, the longest step)
and check the number of Sentinel-2 scenes per city and year.

## Study zones

The same rule for every city, so that cities can be compared (details in
[`zones/README.md`](zones/README.md)):

- **Zone** = GHSL urban cluster 2025 (GHS-SMOD, class ≥ 21) + **2 km** buffer, land only.
- **Public unit** = the **commune**, from OpenStreetMap (no open official dataset exists),
  corrected automatically. Touba is also split into **47 sectors** (central disc 0–2 km,
  then 2 km rings × 8 directions), because the commune of Touba Mosquée covers most of it.
  "Touba" means the Touba–Mbacké agglomeration; Mbacké's figures come from its commune.
- **Centre** of each city (for directions and distance rings): Place de l'Indépendance
  (Dakar), Grande Mosquée (Touba), Place de France (Thiès), fishing quay (Mbour).

| City | Urban cluster | Study zone | Communes |
|---|---|---|---|
| Dakar | 537 km² | 878 km² | 58 |
| Touba | 226 km² | 413 km² | 7 (+ 47 sectors) |
| Thiès | 140 km² | 375 km² | 8 |
| Mbour | 155 km² | 295 km² | 8 |

## Method

```
Sentinel-2 L1C (harmonised)            ESA WorldCover 2021 + Dynamic World 2021
        │ Cloud Score+ masking                    │ keep pixels where both agree
        ▼                                          ▼
Dry-season median composite        Training samples, balanced city × class
per city and year                  (1,500 points per class and per city), 70 % / 30 %
        │ + NDVI, NDBI, MNDWI, BSI                 │
        ▼                                          ▼
One national Random Forest (200 trees) ◄───────────┘   evaluated city by city
        │ classify 2016 … 2026, every city
        ▼
Yearly built-up maps ──► temporal consistency filter ──► year of urbanisation
                                                                 │
                                         indicators by city, commune and sector (J3)
```

1. **Composites** — January–May (dry season) median of cloud-masked Sentinel-2 scenes,
   one per city and year. Cloud Score+ removes clouds and shadows.
2. **Training data** — built / not-built labels taken only where two independent products
   (ESA WorldCover and Google Dynamic World) agree, to reduce label noise.
3. **Classification** — one Random Forest for the whole country, on 6 bands and 4 spectral
   indices (they help separate buildings from bright sand), so that cities are comparable.
4. **Temporal consistency** — a pixel is urbanised in year Y only if it stays built in at
   least 80 % of the following years and at the end of the period
   (see `tests/test_postprocess.py`).
5. **Accuracy** — the 30 % test points only measure agreement with the reference products.
   True accuracy will come from a national sample photo-interpreted blind in Google Earth
   Pro (J4), with area-weighted accuracy per city.

## Repository structure

```
config/
  settings.py        settings shared by all cities (years, season, model, thresholds, paths)
  cities.py          one entry per city: name, seed point, centre, sectors
pipeline/            one step = one module, run from the project root
  s0_zones.py        study zones, communes, centres, sectors -> zones/ (frozen)
  s1_train.py        training samples + national Random Forest, agreement by city
  s2_classify.py     yearly built-up stacks per city
  s3_postprocess.py  urbanisation year, statistics, static map per city
src/                 reusable functions: gee_utils (Earth Engine), postprocess, zones, validation
tests/               unit tests (pure functions, no Earth Engine needed)
zones/               frozen study zones (GeoJSON, versioned)
data/                ignored by git: downloads (data/raw/), training samples, stacks (data/cities/<city>/)
outputs/             model/ (evaluation), cities/<city>/ (results), legacy_dakar/ (first case study)
docs/                old Dakar web map (GitHub Pages), to be replaced by the site in J5
```

## How to run

```bash
python -m venv myvenv && source myvenv/bin/activate
pip install -r requirements.txt
# set GEE_PROJECT in config/settings.py (a Google Cloud project registered for Earth Engine)

python -m pipeline.s0_zones           # only to change the zones (they are frozen in zones/)
python -m pipeline.s1_train           # samples + national model -> outputs/model/
python -m pipeline.s2_classify        # all cities; --city touba for one; --drive to export via Drive
python -m pipeline.s3_postprocess     # all cities with a stack; --city touba for one
pytest
```

Practical notes:

- Step 0 caches its downloads in `data/raw/` (`--refresh` to download again). The public
  Overpass (OSM) servers are often busy: the step tries three mirrors in turn.
- Step 2 retrains the model from `data/training_samples.csv`, so it uses exactly the model
  evaluated in step 1. Run step 1 first.
- The virtual environment uses Python 3.10, no longer supported by Google's libraries since
  October 2026 (it still works, with a warning): move to Python 3.11+ when convenient.

## First case study: Dakar region (legacy)

Before the national project, the method was tested on the Dakar region (FAO GAUL boundary,
own model). Results are kept in `outputs/legacy_dakar/` for comparison with the national
model: built-up area 15,487 ha in 2016 → 26,266 ha in 2026 (+69.6 %), agreement with
reference products 91.8 % (kappa 0.84). Its validation sample (260 points) was abandoned
in favour of the national one.

![Urban expansion map, Dakar region](outputs/legacy_dakar/urban_expansion_map.png)

## Limitations

- Sentinel-2 at 10 m detects groups of buildings rather than individual houses; small or
  scattered constructions can be missed.
- Bright sand, beaches and salt flats can be confused with built-up areas; the spectral
  indices and the temporal filter reduce but do not remove this.
- 2016 relies on Sentinel-2A only (fewer scenes) and 2017 has few clear scenes, which likely
  inflates the 2016→2017 jump.
- The temporal filter has fewer following years to check near the end of the period, so
  growth in 2025–2026 is probably overestimated.
- Commune boundaries come from OpenStreetMap and are not official (least reliable around Thiès).

## Tools

Python · Google Earth Engine · geemap · rasterio · GeoPandas · Shapely · NumPy · pandas ·
scikit-learn · Matplotlib

## License

Code: [MIT](LICENSE). Produced data: [CC BY 4.0](LICENSE-DATA.md), except
`zones/communes.geojson` (derived from OpenStreetMap): ODbL 1.0.

## Author

**Moustapha Cisse** — Geomatics engineer, remote sensing and geospatial data engineering.
Contains modified Copernicus Sentinel data (2016–2026).
