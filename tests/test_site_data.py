import io

import numpy as np
import pytest
from PIL import Image

from src import site_data as sd


def test_tile_range_and_transform_agree():
    # Dakar, about -17.45, 14.7: tile x = floor((lon + 180) / 360 * 2^z)
    x, y = -1942539.0, 1653890.0                         # Web Mercator metres
    x0, y0, x1, y1 = sd.tile_range((x, y, x, y), 14)
    assert (x0, y0) == (x1, y1)
    assert x0 == int((-17.45 + 180) / 360 * 2 ** 14)
    t = sd.mosaic_transform(14, x0, y0)
    col, row = ~t @ (x, y)
    assert 0 <= col < sd.TILE_PX and 0 <= row < sd.TILE_PX


def test_tile_range_whole_world_at_zoom_zero():
    o = sd.ORIGIN
    assert sd.tile_range((-o, -o, o - 1, o - 1), 0) == (0, 0, 0, 0)


def test_split_tiles_skips_empty_tiles():
    mosaic = np.zeros((256, 512), dtype=np.uint8)
    mosaic[10, 300] = 2
    tiles = list(sd.split_tiles(mosaic, 5, 7))
    assert [(x, y) for x, y, _ in tiles] == [(6, 7)]
    with pytest.raises(ValueError):
        list(sd.split_tiles(np.zeros((100, 256), dtype=np.uint8), 0, 0))


def test_overlay_keeps_both_cities():
    a = np.array([[1, 0], [0, 0]], dtype=np.uint8)
    b = np.array([[0, 0], [0, 3]], dtype=np.uint8)
    assert sd.overlay(a, b).tolist() == [[1, 0], [0, 3]]


def test_period_classes():
    years = np.array([-1, 0, 2016, 2017, 2020, 2021, 2025, 2026])
    assert sd.period_classes(years, (2016, 2020, 2025)).tolist() == [0, 0, 1, 2, 2, 3, 3, 0]


def test_encode_png_round_trip():
    tile = np.zeros((256, 256), dtype=np.uint8)
    tile[:10, :10] = 2
    image = Image.open(io.BytesIO(sd.encode_png(tile, {1: "#8f8d87", 2: "#f19a5f"})))
    assert image.mode == "P"
    assert np.array_equal(np.array(image), tile)
    assert image.convert("RGBA").getpixel((0, 0)) == (0xf1, 0x9a, 0x5f, 255)
    assert image.convert("RGBA").getpixel((100, 100))[3] == 0      # class 0 transparent


def test_ground_pixel_area():
    # Zoom 14 at the equator: about 9.55 m; at Dakar's latitude: about 9.24 m
    assert sd.ground_pixel_area_m2(14, np.array(0.0)) == pytest.approx(9.554 ** 2, rel=1e-3)
    assert sd.ground_pixel_area_m2(14, np.array(14.7)) == pytest.approx(9.240 ** 2, rel=1e-3)
    assert sd.mercator_to_lat(0.0) == pytest.approx(0.0)


def test_validation_summary():
    v = lambda e: {"estimate": e, "margin95": 0.1}
    report = {
        "n_points": 120, "unsure_labels": 30, "overall_accuracy": v(0.8),
        "date_accuracy": {"start": v(0.9), "end": v(0.85)},
        "users_accuracy": {"new_built": v(0.5)}, "producers_accuracy": {"new_built": v(0.4)},
        "area_ha": {"new_built": v(1200)},
        "mapped_area_ha": {"not_built": 5000, "built_at_start": 2000, "new_built": 1000},
        "built_area_ha": {"2016": v(1800), "2025": v(3100)},
    }
    s = sd.validation_summary(report, 2016, 2025)
    assert s["built_area"]["2025"]["mapped_ha"] == 3000
    assert s["built_area"]["2016"]["corrected_ha"]["estimate"] == 1800
    assert s["new_built"]["mapped_ha"] == 1000
    assert "users_accuracy_tolerant" not in s["new_built"]
    report["tolerant"] = {"users_accuracy": {"new_built": v(0.75)},
                          "cover_of_map_class": {"new_built": {"built": v(0.6)}}}
    s = sd.validation_summary(report, 2016, 2025)
    assert s["new_built"]["users_accuracy_tolerant"]["estimate"] == 0.75
    assert "growth" not in s
    report["built_area_growth"] = {"estimate": 0.72, "low95": 0.4, "high95": 1.1, "log_se": 0.1,
                                   "mapped": 0.5}
    g = sd.validation_summary(report, 2016, 2025)["growth"]
    assert g == {"mapped": 0.5, "corrected": {"estimate": 0.72, "low95": 0.4, "high95": 1.1}}


def test_split_tiles_and_overlay_on_rgba():
    mosaic = np.zeros((256, 512, 4), dtype=np.uint8)
    mosaic[0, 260] = [10, 20, 30, 255]
    assert [(x, y) for x, y, _ in sd.split_tiles(mosaic, 0, 0)] == [(1, 0)]
    a = np.zeros((1, 2, 4), dtype=np.uint8)
    a[0, 0] = [1, 1, 1, 255]
    b = np.zeros((1, 2, 4), dtype=np.uint8)
    b[0, 1] = [2, 2, 2, 255]
    assert sd.overlay(a, b)[..., 0].tolist() == [[1, 2]]


def test_stretch_rgba():
    refl = np.array([[[0.02, 0.32, 0.5, np.nan]]] * 3)     # 3 bands, 1 row, 4 pixels
    rgba = sd.stretch_rgba(refl, (0.02, 0.32), 1.0)
    assert rgba.shape == (1, 4, 4)
    assert rgba[0, :, 0].tolist() == [0, 255, 255, 0]       # low, high, clipped, no data
    assert rgba[0, :, 3].tolist() == [255, 255, 255, 0]
    mid = np.full((3, 1, 1), 0.17)                          # half-way
    assert sd.stretch_rgba(mid, (0.02, 0.32), 1.0)[0, 0, 0] == 128
    assert sd.stretch_rgba(mid, (0.02, 0.32), 2.0)[0, 0, 0] == round(255 * 0.5 ** 0.5)


def test_encode_webp_round_trip():
    tile = np.zeros((256, 256, 4), dtype=np.uint8)
    tile[..., :3] = 120
    tile[..., 3] = 255
    opaque = Image.open(io.BytesIO(sd.encode_webp(tile, 90)))
    assert opaque.format == "WEBP" and opaque.mode == "RGB"
    assert abs(int(np.array(opaque)[100, 100, 0]) - 120) <= 3
    tile[:128, :, 3] = 0
    holed = np.array(Image.open(io.BytesIO(sd.encode_webp(tile, 90))).convert("RGBA"))
    assert holed[0, 0, 3] == 0 and holed[200, 0, 3] == 255


def test_crop_to_classes():
    classes = np.zeros((20, 20), dtype=np.uint8)
    classes[5, 6] = classes[7, 9] = 1
    rows, cols = sd.crop_to_classes(classes, margin=1, factor=4)
    assert (rows.start, cols.start) == (4, 5)
    assert (rows.stop - rows.start) % 4 == 0 and (cols.stop - cols.start) % 4 == 0
    assert rows.stop >= 9 and cols.stop >= 11
    with pytest.raises(ValueError):
        sd.crop_to_classes(np.zeros((4, 4), dtype=np.uint8), 0, 2)


def test_encode_footprint_png_keeps_colours():
    colors = {1: "#808080", 2: "#ff0000"}
    rgba = np.zeros((1, 3, 4), dtype=np.uint8)
    rgba[0, 0] = [128, 128, 128, 255]
    rgba[0, 1] = [255, 0, 0, 64]
    back = np.array(Image.open(io.BytesIO(sd.encode_footprint_png(rgba, colors, 8))).convert("RGBA"))
    assert back[0, 0].tolist() == [128, 128, 128, 255]
    assert back[0, 1, :3].tolist() == [255, 0, 0] and back[0, 1, 3] == round(255 * 2 / 8)
    assert back[0, 2, 3] == 0


def test_footprint_rgba():
    colors = {1: "#808080", 2: "#ff0000"}
    classes = np.zeros((2, 4), dtype=np.uint8)
    classes[:, 0] = 1                      # block 1: half class 1
    classes[0, 2:] = 2                     # block 2: 2 x class 2, 1 x class 1
    classes[1, 2] = 1
    rgba = sd.footprint_rgba(classes, 2, colors)
    assert rgba.shape == (1, 2, 4)
    assert rgba[0, 0].tolist() == [128, 128, 128, 128]          # grey, half opaque
    assert rgba[0, 1, :3].tolist() == [255, 0, 0]                # majority class 2
    assert rgba[0, 1, 3] == round(255 * 3 / 4)
    empty = sd.footprint_rgba(np.zeros((2, 2), dtype=np.uint8), 2, colors)
    assert empty[0, 0].tolist() == [0, 0, 0, 0]


def test_note_stats_weight_of_a_false_detection():
    first_year = np.zeros((10, 10), dtype=np.int16)
    first_year[:5, :4] = 2016          # 20 pixels built at the start
    first_year[5:, :4] = 2020          # 20 real new pixels
    first_year[0:2, 5:10] = 2018       # block of 10 pixels...
    first_year[2, 5:10] = 2025         # ...and 5 more
    first_year[9, 9] = 2026            # after the period: not counted
    inside = np.zeros((10, 10), dtype=bool)
    inside[:4, 5:] = True
    stats = sd.note_stats(first_year, inside, 2016, 2025, pixel_area_m2=10_000.0)   # 1 ha pixels
    assert stats == {"mapped_ha": 15.0, "main_year": 2018, "share_of_new_built_pct": 42.9,
                     "growth_pct": 175.0, "growth_without_pct": 100.0}
    with pytest.raises(ValueError):
        sd.note_stats(first_year, np.zeros((10, 10), dtype=bool), 2016, 2025, 10_000.0)
