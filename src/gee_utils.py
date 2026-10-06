"""Google Earth Engine helpers: cloud masking, composites, indices, labels."""
import ee

S2_COLLECTION = "COPERNICUS/S2_HARMONIZED"                 # Level-1C, full archive since 2015
CLOUD_SCORE_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
S2_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
INDEX_BANDS = ["NDVI", "NDBI", "MNDWI", "BSI"]
FEATURE_BANDS = S2_BANDS + INDEX_BANDS


def init(project: str) -> None:
    """Authenticate (first run only) and initialise Earth Engine."""
    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)


def city_zone(cfg, city: str) -> ee.Geometry:
    """Frozen study zone of a city (zones/zones.geojson), simplified for Earth Engine."""
    import geopandas as gpd  # imported here: only needed on the client side
    zones = gpd.read_file(cfg.ZONES_GEOJSON).to_crs(cfg.ANALYSIS_CRS)
    zone = zones.loc[zones["city"] == city, "geometry"]
    if len(zone) != 1:
        raise ValueError(f"{city} is not in {cfg.ZONES_GEOJSON}; run python -m pipeline.s0_zones")
    simple = zone.simplify(cfg.ZONE_SIMPLIFY_M).to_crs(4326).iloc[0]
    return ee.Geometry(simple.__geo_interface__, None, False)  # planar edges, as in GeoJSON


def season_dates(year: int, season_start: str, season_end: str) -> tuple:
    """First and last day (ISO strings) of the season of ``year``.

    Dates are "MM-DD". If the start comes after the end, the season starts in the
    previous year: ("11-01", "05-31") for 2016 gives ("2015-11-01", "2016-05-31").
    """
    start_year = year - 1 if season_start > season_end else year
    return f"{start_year}-{season_start}", f"{year}-{season_end}"


def add_indices(img: ee.Image) -> ee.Image:
    """Spectral indices that help separate built-up areas from sand, vegetation and water."""
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndbi = img.normalizedDifference(["B11", "B8"]).rename("NDBI")
    mndwi = img.normalizedDifference(["B3", "B11"]).rename("MNDWI")
    bsi = img.expression(
        "((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))",
        {"SWIR": img.select("B11"), "RED": img.select("B4"),
         "NIR": img.select("B8"), "BLUE": img.select("B2")},
    ).rename("BSI")
    return img.addBands([ndvi, ndbi, mndwi, bsi])


def seasonal_composite(aoi: ee.Geometry, year: int, season_start: str,
                       season_end: str, cloud_threshold: float) -> ee.Image:
    """Cloud-masked median composite of Sentinel-2 for one dry season.

    Reflectance is scaled to 0-1 and spectral indices are added.
    """
    start, last_day = season_dates(year, season_start, season_end)
    end = ee.Date(last_day).advance(1, "day")

    s2 = (ee.ImageCollection(S2_COLLECTION)
          .filterBounds(aoi)
          .filterDate(start, end))
    cloud_score = ee.ImageCollection(CLOUD_SCORE_COLLECTION)

    def mask_clouds(img):
        return img.updateMask(img.select("cs_cdf").gte(cloud_threshold))

    composite = (s2.linkCollection(cloud_score, ["cs_cdf"])
                 .map(mask_clouds)
                 .select(S2_BANDS)
                 .median()
                 .divide(10000))
    return add_indices(composite).clip(aoi).set("year", year)


def count_images(aoi: ee.Geometry, year: int, season_start: str, season_end: str) -> int:
    """Number of Sentinel-2 scenes available for the season (useful for QA)."""
    start, last_day = season_dates(year, season_start, season_end)
    end = ee.Date(last_day).advance(1, "day")
    return (ee.ImageCollection(S2_COLLECTION)
            .filterBounds(aoi)
            .filterDate(start, end)
            .size().getInfo())


def reference_labels(aoi: ee.Geometry, year: int) -> ee.Image:
    """Binary built-up label (1 = built, 0 = not built) from two independent products.

    A pixel is kept only where ESA WorldCover (2021) and the annual mode of
    Google Dynamic World agree. Disagreement areas are masked out, which gives
    cleaner training samples.
    """
    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    dynamic_world = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
                     .filterBounds(aoi)
                     .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                     .select("label")
                     .mode())

    wc_built = worldcover.eq(50)      # 50 = built-up in WorldCover
    dw_built = dynamic_world.eq(6)    # 6 = built in Dynamic World

    built = wc_built.And(dw_built)
    not_built = wc_built.Not().And(dw_built.Not())

    return (ee.Image(0).where(built, 1)
            .updateMask(built.Or(not_built))
            .rename("label").toByte().clip(aoi))


GHSL_BUILT_10M = "JRC/GHSL/P2023A/GHS_BUILT_S_10m"         # 2018 only
OPEN_BUILDINGS_TEMPORAL = "GOOGLE/Research/open-buildings-temporal/v1"


def roof_fraction_layers(aoi: ee.Geometry, ob_years: list, presence_threshold: float,
                         crs: str, scale: float) -> ee.Image:
    """Share of each pixel covered by buildings (0-100 %) in two reference products.

    - ``ob_<year>``: Open Buildings Temporal (Google, yearly, 4 m effective): share of the
      0.5 m sub-pixels whose building confidence is at least ``presence_threshold``;
    - ``ghsl_2018``: GHSL built-up surface at 10 m (m² of buildings per 100 m² cell).
    """
    layers = []
    for year in ob_years:
        presence = (ee.ImageCollection(OPEN_BUILDINGS_TEMPORAL)
                    .filterBounds(aoi)
                    .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                    .select("building_presence")
                    .mosaic())
        roof = (presence.gte(presence_threshold)
                .setDefaultProjection(crs="EPSG:32628", scale=0.5)
                .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                .reproject(crs=crs, scale=scale)
                .multiply(100))
        layers.append(roof.rename(f"ob_{year}"))
    ghsl = ee.ImageCollection(GHSL_BUILT_10M).first().select("built_surface")
    layers.append(ghsl.rename("ghsl_2018"))
    return ee.Image.cat(layers).unmask(0).round().toByte().clip(aoi)


def ghsl_built_surface_series(aoi: ee.Geometry, collection: str) -> dict:
    """GHSL built-up surface (ha) inside ``aoi`` for every epoch of the collection (100 m)."""
    images = ee.ImageCollection(collection).select("built_surface")
    def area(img):
        total = img.reduceRegion(ee.Reducer.sum(), aoi, scale=100, maxPixels=1e10)
        return ee.Feature(None, {"epoch": img.get("system:index"),
                                 "ha": ee.Number(total.get("built_surface")).divide(10_000)})
    rows = ee.FeatureCollection(images.map(area)).getInfo()["features"]
    return {int(f["properties"]["epoch"]): f["properties"]["ha"] for f in rows}
