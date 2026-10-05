# SamaReew — urban expansion in Senegal

> **SamaReew** (_sama réew_, "my country" in Wolof) is becoming a public, open-data atlas
> comparing Senegalese cities (Dakar, Touba, Thiès, Mbour), inspired by Our World in Data.
> See [ROADMAP.md](ROADMAP.md). The content below documents the first case study:
> **urban expansion in the Dakar region, 2016–2026**.
>
> **Work in progress (J2):** the code is moving to a national pipeline (one model for the
> four cities). The case-study results are kept in `outputs/legacy_dakar/`. New commands:
> `python -m pipeline.s0_zones`, `s1_train`, `s2_classify`, `s3_postprocess`
> (settings in `config/`, cities in `config/cities.py`).

Ten years of urban expansion mapped from **Sentinel-2** imagery with **Google Earth Engine**,
a **Random Forest** classifier, a temporal consistency filter and an **independent accuracy
assessment**, published as an **interactive web map**.

**[→ Open the interactive map](https://Bigtapha.github.io/samareew/)**

![Urban expansion map](outputs/legacy_dakar/urban_expansion_map.png)

## Why this area

The Dakar region concentrates a large share of Senegal's population on a narrow peninsula.
With the city centre almost fully built, growth now spreads eastwards into the Rufisque
department, towards Lac Rose, Bambilor and Diamniadio, on former farmland, dunes and
wetlands. This project measures where and when land was built up, year by year.

The study area is the official boundary of the Dakar region (FAO GAUL, level 1). It can be
switched to another administrative unit, to your own boundary file or to a simple
rectangle in `config.py` (`AOI_MODE`).

## Key results

| | |
|---|---|
| Built-up area in 2016 | 15,487 ha |
| Built-up area in 2026 | 26,266 ha |
| Growth 2016–2026 | +69.6 % |
| Agreement with reference products (30 % test sample) | 91.8 % (kappa 0.84) |
| Overall accuracy (independent validation, area-weighted) | _pending_ |

_Areas from `outputs/legacy_dakar/built_area_by_year.csv`, agreement from `outputs/legacy_dakar/accuracy_gee_test.json`;
independent accuracy from `outputs/accuracy_validation.json` once step 4 is done._

## Method

```
Sentinel-2 L1C (harmonised)            ESA WorldCover 2021 + Dynamic World 2021
        │ Cloud Score+ masking                    │ keep pixels where both agree
        ▼                                          ▼
Dry-season median composite / year  ──►  Training samples (built / not built)
        │ + NDVI, NDBI, MNDWI, BSI                 │ 70 % train / 30 % test
        ▼                                          ▼
Random Forest (200 trees) ◄────────────────────────┘
        │ classify 2016 … 2026
        ▼
Yearly built-up maps ──► temporal consistency filter ──► year of urbanisation
        │                                                        │
        ▼                                                        ▼
Independent validation on                           Statistics, static map,
photo-interpreted points (QA/QC)                    interactive web map
```

1. **Composites** — January–May (dry season) median of cloud-masked Sentinel-2 scenes,
   one per year. Cloud Score+ removes clouds and shadows.
2. **Training data** — built / not-built labels taken only where two independent products
   (ESA WorldCover and Google Dynamic World) agree, to reduce label noise.
3. **Classification** — Random Forest on 6 bands and 4 spectral indices. The spectral
   indices help separate buildings from bright sand, a major source of confusion here.
4. **Temporal consistency** — a pixel is urbanised in year Y only if it stays built in at
   least 80 % of the following years and at the end of the period. This removes
   one-year classification noise (see `tests/test_postprocess.py`).
5. **Accuracy assessment** — stratified random points, labelled blind by visual
   interpretation of very-high-resolution historical imagery (Google Earth Pro), then
   confusion matrix, kappa, precision/recall and area-weighted overall accuracy.

## Repository structure

```
config.py              all settings (study area, years, thresholds, colours)
01_classify_gee.py     Earth Engine: composites, Random Forest, accuracy on test sample, export
02_postprocess.py      urbanisation year, statistics, static map and chart
03_make_webmap.py      data for the web map (docs/)
04_validation.py       independent accuracy assessment (make points / evaluate)
src/                   reusable functions (Earth Engine helpers, NumPy post-processing)
tests/                 unit tests for the post-processing rules
docs/                  interactive web map (Leaflet), published with GitHub Pages
```

## How to run

```bash
pip install -r requirements.txt
# set GEE_PROJECT in config.py (a Google Cloud project registered for Earth Engine)
# optional: change the study area in config.py (AOI_MODE, ADMIN_FILTERS)

python 01_classify_gee.py          # add --drive to export through Google Drive instead
python 02_postprocess.py
python 04_validation.py make       # then label outputs/validation_points.csv
python 04_validation.py evaluate
python 03_make_webmap.py
python -m http.server --directory docs   # preview on http://localhost:8000
pytest
```

## Limitations

- Administrative boundaries from FAO GAUL 2015 are approximate along the coastline.
- Sentinel-2 at 10 m detects groups of buildings rather than individual houses; small or
  scattered constructions can be missed.
- Bright sand, beaches and salt flats (Lac Rose) can be confused with built-up areas; the
  spectral indices and the temporal filter reduce but do not remove this.
- The 2016 composite relies on Sentinel-2A only (fewer scenes), so it is slightly noisier;
  2017 also has few clear scenes, which likely inflates the 2016→2017 jump.
- The temporal filter has fewer following years to check near the end of the period
  (a pixel first built in 2026 is not confirmed at all), so growth in 2025–2026 is
  probably overestimated.
- Accuracy on the 30 % test sample measures agreement with reference products, not true
  accuracy; the independent validation (step 4) is the figure to report.

## Tools

Python · Google Earth Engine · geemap · rasterio · NumPy · pandas · scikit-learn ·
Matplotlib · Leaflet

## License

Code: [MIT](LICENSE). Produced data: [CC BY 4.0](LICENSE-DATA.md).

## Author

**Moustapha Cisse** — Geomatics engineer, remote sensing and geospatial data engineering.
Contains modified Copernicus Sentinel data (2016–2026).
