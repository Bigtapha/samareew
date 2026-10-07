"""Settings shared by all cities. Edit this file, not the pipeline steps."""
from pathlib import Path

# --- Paths ---------------------------------------------------------------
ROOT = Path(__file__).parents[1]
DATA_DIR = ROOT / "data"              # ignored by git: raw and intermediate files
OUTPUT_DIR = ROOT / "outputs"
ZONES_DIR = ROOT / "zones"            # frozen study zones (step 0)
MODEL_DIR = OUTPUT_DIR / "model"      # national model: evaluation by city

# --- Google Earth Engine -------------------------------------------------
# Your Google Cloud project registered for Earth Engine
# (see https://developers.google.com/earth-engine/guides/access)
GEE_PROJECT = "tieufmaps"

# Projected CRS used for analysis and area calculations (UTM zone 28N)
ANALYSIS_CRS = "EPSG:32628"
SCALE = 10  # metres (Sentinel-2 native resolution for B2, B3, B4, B8)
ZONE_SIMPLIFY_M = 20  # zones are simplified before being sent to Earth Engine

# --- Time period ---------------------------------------------------------
YEARS = list(range(2016, 2027))  # 2016 ... 2026 (Sentinel-2A launched June 2015)
# The last year is classified but not published: it only confirms the previous years in
# the temporal filter (a single year can never be filtered). Published: 2016 ... 2025.
PUBLISHED_YEARS = YEARS[:-1]
# Dry season in Senegal: few clouds, stable vegetation -> comparable composites.
# A start after the end means the season starts in the previous year: the "2016" season
# runs from 1 November 2015 to 31 May 2016.
SEASON_START = "11-01"  # MM-DD
SEASON_END = "05-31"

# Cloud Score+ threshold (0-1). Higher = stricter cloud masking.
CLOUD_SCORE_THRESHOLD = 0.60

# Direct download of the yearly stacks (step 2): tile size in MB (Earth Engine maximum: 32).
# Smaller tiles avoid "User memory limit exceeded" with long seasons (many scenes per median).
DOWNLOAD_MAX_TILE_MB = 8

# --- Classification (one national model) ---------------------------------
TRAINING_YEAR = 2021          # year of the reference land-cover products (WorldCover 2021)
POINTS_PER_CLASS = 1500       # stratified sample size per class AND per city (balanced city x class)
TRAIN_FRACTION = 0.7          # 70 % training, 30 % test, in every city
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
    (2025, 2025, "2025"),
]
PERIOD_COLORS = ["#6b6b6b", "#fee391", "#fec44f", "#fe9929", "#d95f0e", "#993404"]

# --- Study zones (step 0, see ROADMAP J1) --------------------------------
# One zone per city, same rule everywhere: GHSL urban cluster + fixed buffer,
# clipped to land. Zones are written once to zones/ and then frozen.
GHSL_SMOD_COLLECTION = "JRC/GHSL/P2023A/GHS_SMOD_V2-0"
GHSL_EPOCH = "2025"
GHSL_MIN_CLASS = 21        # 21-23 = urban cluster, 30 = urban centre (GHSL degree of urbanisation)
ZONE_BUFFER_M = 2000       # margin for growth beyond the 2025 urban cluster
# Where buffers of two cities overlap, each point goes to the nearest urban cluster.

# Land mask and communes
COD_AB_URL = ("https://data.humdata.org/dataset/bd9bc484-155d-41a3-87cf-064310a94492/resource/"
              "02745b5a-88b7-4132-ae11-8bdaf64afff8/download/sen_admin_boundaries.geojson.zip")
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
HTTP_USER_AGENT = "SamaReew (https://github.com/Bigtapha/samareew)"
OSM_COMMUNE_ADMIN_LEVEL = "8"
MIN_COMMUNE_PART_KM2 = 0.5  # commune pieces smaller than this inside a zone are dropped

# Sectors (cities with "sectors": True in config/cities.py): central disc of one ring
# width, then rings x 8 directions around the city centre.
SECTOR_RING_M = 2000

# --- Indicators (step 4, ROADMAP §4.3) -----------------------------------
FORMAT_VERSION = "0.1"           # version of the exchange format read by the site (ROADMAP §4.2)
RING_WIDTH_M = SECTOR_RING_M     # distance rings around the centre, in every city
# Growth types (Atlas of Urban Expansion): the urban footprint at the start of a period is
# the urban and suburban built-up area + a fringe of open land + the open spaces it encloses.
# Urban or suburban = at least GROWTH_MIN_BUILT_SHARE built land in a 1 km² circle around
# the pixel; sparser built-up (villages, scattered houses) is rural and left out.
GROWTH_PERIODS = [(2016, 2020), (2020, 2025), (2016, 2025)]
GROWTH_CIRCLE_RADIUS_M = 564     # circle of 1 km² (Atlas "walking distance" circle)
GROWTH_MIN_BUILT_SHARE = 0.25
GROWTH_FRINGE_M = 100
GROWTH_MAX_HOLE_HA = 200
# Population: WorldPop Global 2, constrained, 100 m, one file per year (CC BY 4.0)
WORLDPOP_URL = ("https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{year}/SEN/"
                "v1/100m/constrained/sen_pop_{year}_CN_100m_R2025A_v1.tif")
WORLDPOP_RELEASE = "WorldPop Global 2, R2025A v1"
# WorldPop is published for whole cities only: its split between communes is off by a factor
# 0.35 to 2.9 against the census (METHODOLOGIE §13.4). By commune, the census is published.
# Built-up m² per inhabitant and SDG 11.3.1 are not published for units with fewer people
# (a few hundred inhabitants give meaningless ratios)
MIN_POPULATION = 1000

# Census (RGPH-5 2023, ANSD, CC BY 4.0): published by commune for the communes entirely
# inside a zone, and used to check WorldPop (step 6). Source: the ANSD directory of
# localities (population of every neighbourhood and village with its commune), one CSV per
# region and census year.
CENSUS_URL = ("https://www.ansd.sn/data-recensement.csv?field_liste_annee_value={year}"
              "&field_regions_value={region}&_format=csv")
CENSUS_YEARS = [2013, 2023]          # RGPH-4 and RGPH-5
CENSUS_PUBLISHED_YEAR = 2023         # published by commune (RGPH-5)
CENSUS_MIN_SHARE = 0.99              # share of the commune's land inside the zone
# OSM commune name -> ANSD commune name, where spellings differ (other names match once
# accents, case, hyphens and apostrophes are removed)
CENSUS_COMMUNE_ALIASES = {
    "Bambylor": "BAMBILOR",
    "Djidah Thiaroye Kaw": "DJIDAH THIAROYE KAO",
    "La Somone": "SOMONE",
    "Popenguine-Ndayane": "POPENGUINE",
    "Sébikhotane": "SEBIKOTANE",
    "Tivaouane Peulh-Niaga": "TIVAOUANE PEULH NIAGHA",
    "Yenne": "YENE",
}

# --- Cross-check (step 6) -----------------------------------------------
# Reference building maps, brought to our 10 m grid as roof fractions (0-100 %)
OB_YEARS = list(range(2016, 2024))   # Open Buildings Temporal v1 (Google): 2016 ... 2023
OB_PRESENCE_THRESHOLD = 0.5          # building confidence of a 0.5 m sub-pixel (uncalibrated)
GHSL_BUILT_COLLECTION = "JRC/GHSL/P2023A/GHS_BUILT_S"   # 100 m, epochs 1975 ... 2030
# GHSL observes 1975, 1990, 2000, 2014 (Landsat) and 2018 (Sentinel-2); the 5-year epochs in
# between are interpolated, and the epochs after 2020 are extrapolated ("projected" in outputs)
GHSL_LAST_OBSERVED_EPOCH = 2020
# A pixel of our map is "confirmed" if the reference has at least CHECK_MIN_ROOF_PCT of
# roofs on average in a window of CHECK_WINDOW_PX x CHECK_WINDOW_PX pixels around it (30 m:
# absorbs small misregistrations; 5 % of 900 m² = 45 m², a small house).
CHECK_WINDOW_PX = 3
CHECK_MIN_ROOF_PCT = 5
CHECK_CELL_PX = 10                   # 1 ha cells for the correlation of the two maps

# --- Validation (step 5, ROADMAP J4) -------------------------------------
# Stratified random sample of each city's map over the whole published period, the same
# design in every city. The new built-up area is split by growth type (Atlas rule of
# step 4, same period), to measure the accuracy of leapfrog growth city by city.
VALIDATION_PERIOD = (2016, 2025)
VALIDATION_POINTS = {             # points per stratum and per city (120 per city)
    "not_built": 40,
    "built_at_start": 32,
    "densification": 16,
    "extension": 16,
    "leapfrog": 16,
}
VALIDATION_SEED = SEED
# Second reading (decided 07/10/2026): what covers each point labelled not built at the end,
# from the end image only. Closed list, fixed before the reading.
VALIDATION_COVER_CLASSES = {
    "partly_built": "bâti, mais sur moins de la moitié du carré",
    "construction": "chantier : fondations, dalle ou murs bas (pas encore « murs montés »)",
    "subdivision": "lotissement non construit : parcelles nivelées, bornées ou clôturées, rues tracées",
    "dirt_track": "piste ou route en terre hors du tissu bâti et hors lotissement",
    "bare_soil": "sol nu, sable, dune, plage, carrière",
    "vegetation": "champ, jachère, arbres, herbe",
    "water": "eau, zone humide, tanne",
    "other": "autre (préciser dans note)",
}
# Covers counted as land being urbanised in the tolerant accuracy (the strict one is official)
VALIDATION_URBANISING = ("partly_built", "construction", "subdivision")

# --- Files ---------------------------------------------------------------
ZONES_GEOJSON = ZONES_DIR / "zones.geojson"
TRAINING_SAMPLES_CSV = DATA_DIR / "training_samples.csv"   # written by step 1, read by step 2
ACCURACY_BY_CITY_JSON = MODEL_DIR / "accuracy_by_city.json"

# Per-city files, in data/cities/<city>/ and outputs/cities/<city>/
BUILT_STACK_TIF = "built_by_year.tif"        # one band per year (0/1/255)
IMAGE_COUNTS_JSON = "image_counts.json"      # Sentinel-2 scenes per season (quality check)
FIRST_YEAR_TIF = "urbanisation_year.tif"     # year a pixel became built
STATS_CSV = "built_area_by_year.csv"
GROWTH_TYPE_TIF = "growth_type_{start}_{end}.tif"   # 1 densification, 2 extension, 3 leapfrog

# Exchange format (step 4), in outputs/tables/
TABLES_DIR = OUTPUT_DIR / "tables"
INDICATORS_CSV = TABLES_DIR / "indicators.csv"       # long table: one value per row
UNITS_CSV = TABLES_DIR / "units.csv"                 # spatial units: names and land area
INDICATORS_JSON = TABLES_DIR / "indicators.json"     # one fact sheet per indicator
# WorldPop by commune: not published, kept for the census check of step 6
WORLDPOP_COMMUNES_CSV = DATA_DIR / "worldpop_by_commune.csv"

# Cross-check (step 6)
REFERENCE_ROOFS_TIF = "reference_roofs.tif"          # data/cities/<city>/: ob_<year>, ghsl_2018 bands
GHSL_SERIES_JSON = "ghsl_built_surface.json"         # data/cities/<city>/: GHSL roofs (ha) per epoch
CROSSCHECK_DIR = OUTPUT_DIR / "crosscheck"

# Validation (step 5), in outputs/validation/
VALIDATION_DIR = OUTPUT_DIR / "validation"
VALIDATION_LABELS_CSV = VALIDATION_DIR / "labels.csv"     # sheet to fill, without the map classes
VALIDATION_KEY_CSV = VALIDATION_DIR / "sample_key.csv"    # map class of each point: do not open while labelling
VALIDATION_STRATA_CSV = VALIDATION_DIR / "strata.csv"     # pixels and points per city and stratum
VALIDATION_KML = VALIDATION_DIR / "points.kml"            # points and their 10 m pixel, for Google Earth Pro
VALIDATION_REPORT_JSON = VALIDATION_DIR / "accuracy.json"
VALIDATION_COVER_CSV = VALIDATION_DIR / "cover_2025.csv"  # second reading: cover of the points not built at the end
VALIDATION_COVER_KML = VALIDATION_DIR / "cover_2025.kml"  # the same points, for Google Earth Pro


def city_data_dir(city: str) -> Path:
    return DATA_DIR / "cities" / city


def city_output_dir(city: str) -> Path:
    return OUTPUT_DIR / "cities" / city
