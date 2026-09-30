"""Project settings. Edit this file, not the scripts."""
from pathlib import Path

# --- Paths ---------------------------------------------------------------
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
WEB_DIR = ROOT / "docs"            # served by GitHub Pages
WEB_DATA_DIR = WEB_DIR / "data"

# --- Google Earth Engine -------------------------------------------------
# Your Google Cloud project registered for Earth Engine
# (see https://developers.google.com/earth-engine/guides/access)
GEE_PROJECT = "tieufmaps"

# --- Study area ----------------------------------------------------------
# How the study area is defined:
#   "admin" : administrative boundary taken from an Earth Engine collection (default)
#   "file"  : your own boundary file in GeoJSON (for example from geoBoundaries or HDX)
#   "bbox"  : a simple rectangle
AOI_MODE = "admin"

# "admin" mode: FAO GAUL level 1 = regions. The filters must select exactly one feature.
ADMIN_COLLECTION = "FAO/GAUL/2015/level1"
ADMIN_FILTERS = {"ADM0_NAME": "Senegal", "ADM1_NAME": "Dakar"}

# "file" mode
AOI_FILE = DATA_DIR / "dakar_region.geojson"

# "bbox" mode, WGS84 [min_lon, min_lat, max_lon, max_lat] (here: Lac Rose area)
AOI_BBOX = [-17.30, 14.79, -17.16, 14.89]

AOI_NAME = "Dakar region, Senegal"

# Projected CRS used for analysis and area calculations (UTM zone 28N)
ANALYSIS_CRS = "EPSG:32628"
SCALE = 10  # metres (Sentinel-2 native resolution for B2, B3, B4, B8)

# --- Time period ---------------------------------------------------------
YEARS = list(range(2016, 2027))  # 2016 ... 2026
# Dry season in Senegal: few clouds, stable vegetation -> comparable composites
SEASON_START = "01-01"  # MM-DD
SEASON_END = "05-31"

# Cloud Score+ threshold (0-1). Higher = stricter cloud masking.
CLOUD_SCORE_THRESHOLD = 0.60

# --- Classification ------------------------------------------------------
TRAINING_YEAR = 2021          # year of the reference land-cover products (WorldCover 2021)
POINTS_PER_CLASS = 1500       # stratified training/test sample size per class
TRAIN_FRACTION = 0.7          # 70 % training, 30 % test
N_TREES = 200
SEED = 42

# --- Post-processing -----------------------------------------------------
# A pixel is considered urbanised in year Y if it is classified as built-up
# in at least this share of the years from Y to the last year, including
# the last year. This removes one-year classification noise.
PERSISTENCE_RATIO = 0.8

# Periods used for the map legend (start_year, end_year, label)
PERIODS = [
    (2016, 2016, "Built before 2017"),
    (2017, 2018, "2017-2018"),
    (2019, 2020, "2019-2020"),
    (2021, 2022, "2021-2022"),
    (2023, 2024, "2023-2024"),
    (2025, 2026, "2025-2026"),
]
PERIOD_COLORS = ["#6b6b6b", "#fee391", "#fec44f", "#fe9929", "#d95f0e", "#993404"]

# --- Files ---------------------------------------------------------------
AOI_BOUNDARY_GEOJSON = DATA_DIR / "aoi_boundary.geojson"  # written by step 1
AOI_BOUNDS_JSON = DATA_DIR / "aoi_bounds.json"            # written by step 1
BUILT_STACK_TIF = DATA_DIR / "built_by_year.tif"          # one band per year (0/1/255)
FIRST_YEAR_TIF = OUTPUT_DIR / "urbanisation_year.tif"     # year a pixel became built
ACCURACY_JSON = OUTPUT_DIR / "accuracy_gee_test.json"
STATS_CSV = OUTPUT_DIR / "built_area_by_year.csv"
