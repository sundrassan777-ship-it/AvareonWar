# -*- coding: utf-8 -*-
"""
Regression tests: MapRenderer's pre-computed caches must follow the map scale.

`territory_bounding_boxes` and `multi_zoom_cache` are built once in
MapRenderer.__init__ from game.scaled_polygons. apply_display_settings()
re-derives scale_factor and re-rounds every polygon on a resolution change, but
used to leave those caches holding the OLD scale. Measured before the fix: after
switching 1600x900 -> 1280x720 the cached projection was **418 px** away from a
direct world_to_screen() projection, so territory polygons misaligned with the
map background and AABB hit-testing selected the wrong territory.

Map switching was never affected — MapRenderer is constructed inside
initialize_game(), which calls _reload_map_assets() first.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


@pytest.fixture
def game(pygame_display):
    from main import Game
    g = Game()
    g.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 'Normal'],
    })
    g.game_state.phase = 'playing'
    # Normalize to a known windowed mode. Game.__init__ honours config.json, which
    # may be fullscreen; a fullscreen window cannot always be resized afterwards
    # (notably under SDL_VIDEODRIVER=dummy, which another test module sets at import
    # time for the whole session).
    g.apply_display_settings(1600, 900, False)
    return g


def _require_scale_change(game, previous_scale):
    """
    Skip when the environment refused the resolution change.

    apply_display_settings() deliberately adapts to the size the display ACTUALLY
    gave it (Windows DPI scaling, or a driver that pins the window size), so the
    requested resolution is not guaranteed. The cache invariants below hold either
    way, but the regression this file guards only bites when the scale really moves.
    """
    if game.scale_factor == pytest.approx(previous_scale):
        pytest.skip(
            f"display did not honour the resolution change "
            f"(scale_factor stayed {game.scale_factor:.4f}); "
            f"cache-vs-scale regression cannot be exercised here")


def _sample_territories(game, count=12):
    return list(game.scaled_polygons.keys())[:count]


def _max_bbox_error(game):
    """Largest disagreement between cached bounding boxes and current polygons."""
    worst = 0.0
    for t in _sample_territories(game):
        poly = game.scaled_polygons[t]
        bbox = game.map_renderer.territory_bounding_boxes.get(t)
        assert bbox is not None, f"missing bounding box for {t}"
        expected = (min(p[0] for p in poly), min(p[1] for p in poly),
                    max(p[0] for p in poly), max(p[1] for p in poly))
        worst = max(worst, max(abs(a - b) for a, b in zip(bbox, expected)))
    return worst


def _max_projection_error(game, zoom=2.35):
    """Largest disagreement between the cached projection and world_to_screen()."""
    mr = game.map_renderer
    game.camera.zoom = zoom
    game.camera.offset = [50.0, 40.0]
    game.camera.clamp_to_bounds()
    game.camera_zoom = game.camera.zoom
    game.camera_offset = list(game.camera.offset)
    mr.cached_screen_polygons = {}
    mr.last_camera_state = None

    worst = 0.0
    for t in _sample_territories(game):
        cached = mr.get_cached_screen_polygon(t)
        direct = [game.world_to_screen(p) for p in game.scaled_polygons[t]]
        for (cx, cy), (dx, dy) in zip(cached, direct):
            worst = max(worst, abs(cx - dx), abs(cy - dy))
    return worst


@pytest.mark.parametrize('width,height', [(1280, 720), (1920, 1080)])
def test_caches_follow_resolution_change(game, width, height):
    """After a resolution change the renderer caches must match the new scale."""
    original_scale = game.scale_factor
    assert game.apply_display_settings(width, height, False) is True

    # The invariants below hold regardless, but the regression only bites when
    # scale_factor actually moves (before the fix: 418px projection error).
    _require_scale_change(game, original_scale)

    assert _max_bbox_error(game) == pytest.approx(0.0, abs=1e-6), (
        "territory_bounding_boxes still hold the old map scale")
    assert _max_projection_error(game) < 1.0, (
        "polygons misaligned with the map after a resolution change")


def test_multi_zoom_cache_follows_resolution_change(game):
    """multi_zoom_cache entries must equal polygon coords * zoom level."""
    original_scale = game.scale_factor
    game.apply_display_settings(1280, 720, False)
    _require_scale_change(game, original_scale)
    mr = game.map_renderer
    zoom = mr.ZOOM_LEVELS[2]

    worst = 0.0
    for t in _sample_territories(game):
        pre = mr.multi_zoom_cache.get((zoom, t))
        assert pre is not None, f"missing multi_zoom entry for {t}"
        for (px, py), (wx, wy) in zip(pre, game.scaled_polygons[t]):
            worst = max(worst, abs(px - wx * zoom), abs(py - wy * zoom))

    assert worst == pytest.approx(0.0, abs=1e-6), (
        "multi_zoom_cache still holds polygons at the old map scale")


def test_round_trip_resolution_change(game):
    """Changing resolution and back must leave caches consistent."""
    game.apply_display_settings(1920, 1080, False)
    assert _max_projection_error(game) < 1.0
    game.apply_display_settings(1600, 900, False)
    assert _max_bbox_error(game) == pytest.approx(0.0, abs=1e-6)
    assert _max_projection_error(game) < 1.0
