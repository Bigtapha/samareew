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


def aoi_geometry(bbox: list) -> ee.Geometry:
    return ee.Geometry.Rectangle(bbox, proj="EPSG:4326", geodesic=False)


def admin_boundary(collection: str, filters: dict) -> ee.Geometry:
    """Boundary of one administrative unit, e.g. {"ADM0_NAME": "Senegal", "ADM1_NAME": "Dakar"}."""
    fc = ee.FeatureCollection(collection)
    for prop, value in filters.items():
        fc = fc.filter(ee.Filter.eq(prop, value))
    n = fc.size().getInfo()
    if n != 1:
        raise ValueError(f"{n} features match {filters} in {collection}; exactly one is expected. "
                         "Check the spelling of the names in config.ADMIN_FILTERS.")
    return fc.geometry()


def file_boundary(path) -> ee.Geometry:
    """Boundary read from a local GeoJSON file (all features are merged)."""
    import json
    geojson = json.loads(open(path, encoding="utf-8").read())
    if geojson["type"] == "FeatureCollection":
        return ee.FeatureCollection([ee.Feature(f) for f in geojson["features"]]).geometry()
    if geojson["type"] == "Feature":
        return ee.Feature(geojson).geometry()
    return ee.Geometry(geojson)


def load_aoi(cfg) -> ee.Geometry:
    """Study area according to config.AOI_MODE ("admin", "file" or "bbox")."""
    if cfg.AOI_MODE == "admin":
        return admin_boundary(cfg.ADMIN_COLLECTION, cfg.ADMIN_FILTERS)
    if cfg.AOI_MODE == "file":
        return file_boundary(cfg.AOI_FILE)
    if cfg.AOI_MODE == "bbox":
        return aoi_geometry(cfg.AOI_BBOX)
    raise ValueError(f"Unknown AOI_MODE: {cfg.AOI_MODE}")


def bounds_of(aoi: ee.Geometry) -> dict:
    """West/south/east/north of the study area in WGS84."""
    ring = aoi.bounds(maxError=1).coordinates().get(0).getInfo()
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    return {"west": min(lons), "south": min(lats), "east": max(lons), "north": max(lats)}


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
    start = f"{year}-{season_start}"
    end = ee.Date(f"{year}-{season_end}").advance(1, "day")

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
    end = ee.Date(f"{year}-{season_end}").advance(1, "day")
    return (ee.ImageCollection(S2_COLLECTION)
            .filterBounds(aoi)
            .filterDate(f"{year}-{season_start}", end)
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
