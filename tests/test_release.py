from pathlib import Path

from src import release as rl

PERIODS = [(2016, 2020), (2020, 2025), (2016, 2025)]


def test_data_package_has_every_city_and_period():
    pairs = rl.data_package_files(Path("/repo"), ["dakar", "touba"], PERIODS)
    arcs = [a for _, a in pairs]
    assert len(arcs) == len(set(arcs))
    assert all(a.startswith(rl.DATA_PREFIX + "/") for a in arcs)
    for city in ("dakar", "touba"):
        assert f"{rl.DATA_PREFIX}/rasters/{city}/urbanisation_year.tif" in arcs
        for s, e in PERIODS:
            assert f"{rl.DATA_PREFIX}/rasters/{city}/growth_type_{s}_{e}.tif" in arcs


def test_data_package_keeps_frozen_zones_and_leaves_out_unpublished_files():
    pairs = rl.data_package_files(Path("/repo"), ["dakar"], PERIODS)
    sources = {a: s for s, a in pairs}
    assert sources[f"{rl.DATA_PREFIX}/boundaries/communes.geojson"] == Path("/repo/zones/communes.geojson")
    assert sources[f"{rl.DATA_PREFIX}/known_errors/map_notes.geojson"] == Path("/repo/outputs/site/map_notes.geojson")
    names = " ".join(sources)
    assert "_init" not in names            # intermediate validation sheets
    assert "worldpop_by_commune" not in names  # WorldPop is published by city only


def test_site_assets_are_relative_to_the_root(tmp_path):
    tiles = tmp_path / "outputs" / "site" / "tiles"
    basemap = tmp_path / "site" / "public" / "basemap"
    (basemap / "fonts" / "Noto Sans Regular").mkdir(parents=True)
    tiles.mkdir(parents=True)
    for p in (tiles / "urbanisation.pmtiles", tiles / "notes.txt", basemap / "basemap.pmtiles",
              basemap / "fonts" / "Noto Sans Regular" / "0-255.pbf"):
        p.write_bytes(b"x")
    arcs = [a for _, a in rl.site_asset_files(tmp_path, tiles, basemap)]
    assert arcs == ["outputs/site/tiles/urbanisation.pmtiles",
                    "site/public/basemap/basemap.pmtiles",
                    "site/public/basemap/fonts/Noto Sans Regular/0-255.pbf"]


def test_data_readme_names_version_commit_and_files():
    text = rl.data_readme("1.0.0", "2026-10-09", "abc1234", {"dakar": "Dakar", "touba": "Touba"},
                          list(range(2016, 2026)), PERIODS, "https://github.com/x/y")
    assert "version 1.0.0" in text and "`abc1234`" in text
    assert "Dakar, Touba" in text and "2016–2025" in text
    assert "(2016–2020, 2020–2025, 2016–2025)" in text
