"""Step 0 - National study zones: one zone per city and its communes (ROADMAP J1).

Rule, identical for every city:
    GHSL urban cluster (GHS-SMOD, degree of urbanisation >= 21) containing the city
    + fixed buffer (config.ZONE_BUFFER_M), split halfway where two cities' buffers meet,
    clipped to land (OCHA COD-AB national boundary).
Communes come from OpenStreetMap (admin_level 8), corrected: names without the old
"Communauté rurale de" prefix, overlaps removed (the smallest commune keeps the area).

Outputs (frozen and versioned; re-run only to change the rule)
- zones/urban_clusters.geojson   GHSL urban cluster of each city
- zones/zones.geojson            study zone of each city
- zones/communes.geojson         communes clipped to the zones

Usage
    python 00_zones.py               # uses cached downloads in data/raw/ when present
    python 00_zones.py --refresh     # download OSM and OCHA data again
"""
import argparse
import io
import json
import time
import zipfile
from datetime import date

import ee
import geopandas as gpd
import requests
from shapely.geometry import shape
from shapely.ops import unary_union

import config as cfg
from src import gee_utils as gu
from src import zones as zn

RAW_DIR = cfg.DATA_DIR / "raw"
COD_ADMIN0 = "sen_admin0.geojson"
OSM_CACHE = RAW_DIR / "osm_communes_overpass.json"


def urban_clusters() -> gpd.GeoSeries:
    """GHSL urban cluster containing each city's seed point."""
    smod = (ee.ImageCollection(cfg.GHSL_SMOD_COLLECTION)
            .filter(ee.Filter.eq("system:index", cfg.GHSL_EPOCH)).first().select("smod_code"))
    seeds = [p for _, p in cfg.CITIES.values()]
    region = ee.Geometry.MultiPoint(seeds).bounds().buffer(50_000)
    vectors = smod.gte(cfg.GHSL_MIN_CLASS).selfMask().reduceToVectors(
        geometry=region, crs=smod.projection(), scale=1000, geometryType="polygon",
        eightConnected=True, maxPixels=1e9)
    geoms = {}
    for slug, (name, seed) in cfg.CITIES.items():
        hits = vectors.filterBounds(ee.Geometry.Point(seed))
        if hits.size().getInfo() != 1:
            raise ValueError(f"{name}: the seed point {seed} is not inside exactly one GHSL urban cluster")
        geoms[slug] = shape(hits.geometry().transform("EPSG:4326", 1).getInfo())
    return gpd.GeoSeries(geoms, crs=4326).to_crs(cfg.ANALYSIS_CRS)


def land_mask(refresh: bool):
    path = RAW_DIR / COD_ADMIN0
    if refresh or not path.exists():
        print("Downloading OCHA COD-AB boundaries ...")
        r = requests.get(cfg.COD_AB_URL, timeout=300)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extract(COD_ADMIN0, RAW_DIR)
    return gpd.read_file(path).to_crs(cfg.ANALYSIS_CRS).union_all()


def overpass(query: str, attempts: int = 3) -> str:
    """Run an Overpass query, trying each mirror in turn (public servers are often busy)."""
    for attempt in range(attempts):
        for url in cfg.OVERPASS_URLS:
            try:
                r = requests.post(url, data={"data": query}, timeout=300,
                                  headers={"User-Agent": cfg.HTTP_USER_AGENT})
                if r.ok and r.text.lstrip().startswith("{"):
                    return r.text
                print(f"  {url}: HTTP {r.status_code}")
            except requests.RequestException as err:
                print(f"  {url}: {err}")
        time.sleep(30 * (attempt + 1))
    raise RuntimeError("All Overpass servers failed; try again later.")


def osm_communes(bbox_wgs84, refresh: bool) -> tuple:
    """OSM administrative relations at commune level inside the bounding box."""
    if refresh or not OSM_CACHE.exists():
        print("Downloading OSM communes (Overpass) ...")
        w, s, e, n = bbox_wgs84
        query = (f'[out:json][timeout:240];relation["boundary"="administrative"]'
                 f'["admin_level"="{cfg.OSM_COMMUNE_ADMIN_LEVEL}"]({s},{w},{n},{e});out geom;')
        OSM_CACHE.write_text(overpass(query), encoding="utf-8")
    data = json.loads(OSM_CACHE.read_text(encoding="utf-8"))
    rows = []
    for el in data["elements"]:
        poly = zn.relation_polygon(el)
        if poly is None:
            print(f"  skipped OSM relation {el['id']} ({el['tags'].get('name')}): open boundary")
            continue
        rows.append({"commune": zn.clean_name(el["tags"].get("name", "?")),
                     "osm_name": el["tags"].get("name"), "osm_id": el["id"], "geometry": poly})
    gdf = gpd.GeoDataFrame(rows, crs=4326).to_crs(cfg.ANALYSIS_CRS)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf, data["osm3s"]["timestamp_osm_base"]


def communes_by_zone(communes: gpd.GeoDataFrame, zones: dict) -> gpd.GeoDataFrame:
    communes = communes.copy()
    communes["full_area"] = communes.area
    communes["geometry"] = zn.remove_overlaps(list(communes.geometry))
    rows = []
    for slug, zone in zones.items():
        for _, c in communes[communes.intersects(zone)].iterrows():
            part = c.geometry.intersection(zone)
            if part.area / 1e6 < cfg.MIN_COMMUNE_PART_KM2:
                continue
            rows.append({"city": slug, "commune": c.commune, "osm_name": c.osm_name, "osm_id": c.osm_id,
                         "area_km2": round(part.area / 1e6, 2),
                         "share_of_commune": round(part.area / c.full_area, 3), "geometry": part})
    return gpd.GeoDataFrame(rows, crs=cfg.ANALYSIS_CRS)


def write(gdf: gpd.GeoDataFrame, name: str) -> None:
    path = cfg.ZONES_DIR / name
    gdf.to_crs(4326).to_file(path, driver="GeoJSON", COORDINATE_PRECISION=6)
    print(f"  wrote {path.relative_to(cfg.ROOT)} ({len(gdf)} features)")


def main(refresh: bool) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cfg.ZONES_DIR.mkdir(exist_ok=True)
    gu.init(cfg.GEE_PROJECT)

    clusters = urban_clusters()
    land = land_mask(refresh)
    zones = zn.study_zones(dict(clusters.items()), cfg.ZONE_BUFFER_M, land)

    bbox = gpd.GeoSeries([unary_union(list(zones.values()))], crs=cfg.ANALYSIS_CRS).to_crs(4326).total_bounds
    communes, osm_date = osm_communes(bbox, refresh)
    communes["geometry"] = communes.intersection(land)  # OSM boundaries often run out to sea
    communes = communes_by_zone(communes[~communes.is_empty], zones)

    today = date.today().isoformat()
    names = {slug: name for slug, (name, _) in cfg.CITIES.items()}
    write(gpd.GeoDataFrame(
        {"city": list(clusters.index), "name": [names[s] for s in clusters.index],
         "area_km2": (clusters.area / 1e6).round(1).values,
         "source": f"GHSL GHS-SMOD R2023A epoch {cfg.GHSL_EPOCH}, class >= {cfg.GHSL_MIN_CLASS}"},
        geometry=clusters.values, crs=cfg.ANALYSIS_CRS), "urban_clusters.geojson")
    write(gpd.GeoDataFrame(
        {"city": list(zones), "name": [names[s] for s in zones],
         "area_km2": [round(z.area / 1e6, 1) for z in zones.values()],
         "rule": f"GHSL urban cluster + {cfg.ZONE_BUFFER_M} m buffer, split halfway between cities, land only",
         "created": today},
        geometry=list(zones.values()), crs=cfg.ANALYSIS_CRS), "zones.geojson")
    communes["osm_date"] = osm_date[:10]
    write(communes, "communes.geojson")

    print("\nCity    cluster km2   zone km2   communes   zone covered by communes")
    for slug, zone in zones.items():
        sub = communes[communes.city == slug]
        covered = sub.area_km2.sum() / (zone.area / 1e6)
        print(f"{slug:7} {clusters[slug].area / 1e6:11.0f} {zone.area / 1e6:10.0f} {len(sub):10} {covered:12.0%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="download OSM and OCHA data again")
    main(parser.parse_args().refresh)
