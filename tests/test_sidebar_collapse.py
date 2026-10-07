# -*- coding: utf-8 -*-
"""
Collapsible right sidebar + east map extension.

Part 1 — East map extension (rendering/map_extension.py)
    The map background is left-aligned, so at the minimum zoom (1.65) on a 16:9
    window it ends ~175 px before the window's right edge (1600x900: at x=1427).
    The frame is filled WHITE first, and that strip used to be hidden only by the
    right sidebar (x >= 1350). The extension fills it so the sidebar can collapse
    without exposing a white band — and without changing the zoom.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WHITE = (255, 255, 255)


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
    # Normalize to a known windowed mode (Game.__init__ honours config.json, which
    # may be fullscreen) — same as tests/test_resolution_caches.py.
    g.apply_display_settings(1600, 900, False)
    return g


def _set_camera(game, zoom, offset=(0.0, 0.0)):
    """Apply camera state the way the real loop does (camera + Game mirrors)."""
    game.camera.zoom = zoom
    game.camera.target_zoom = zoom
    game.camera.offset = list(offset)
    game.camera.clamp_to_bounds()
    game.camera_zoom = game.camera.zoom
    game.camera_offset = list(game.camera.offset)


def _render_background(game, zoom=None):
    """White frame + map background only (what sits under the sidebar)."""
    _set_camera(game, game.camera.min_zoom if zoom is None else zoom)
    game.screen.fill(WHITE)
    game._blit_map_background()


def _map_right(game):
    return int(game.map_width * game.camera_zoom) + int(-game.camera_offset[0] * game.camera_zoom)


def _require_gap(game):
    """Skip when this window shape has no gap at minimum zoom (16:10, 4:3)."""
    _set_camera(game, game.camera.min_zoom)
    if _map_right(game) >= game.screen.get_width():
        pytest.skip(f"no east gap at {game.screen.get_size()} (map reaches the edge)")


def _rgb(surface, pos):
    return tuple(surface.get_at(pos))[:3]


# ============================================================================
# PURE HELPERS
# ============================================================================

class TestExtensionMath:

    def test_required_width_matches_measured_gap(self):
        """1600x900: map 865 px wide at scale 1 -> 1427 px at zoom 1.65, gap 173 px."""
        from rendering.map_extension import required_source_width
        needed = required_source_width(4096, 1600, 865, 1.65)
        # 173 screen px at 0.348 screen px per source px
        assert needed == pytest.approx(496, abs=2)

    def test_no_gap_when_map_reaches_edge(self):
        """16:10 (1920x1200: map 1166 px -> 1924 px at 1.65) needs no extension."""
        from rendering.map_extension import required_source_width
        assert required_source_width(4096, 1920, 1166, 1.65) == 0

    def test_override_path_rule(self):
        from rendering.map_extension import east_extension_override_path
        assert east_extension_override_path(None) is None
        assert east_extension_override_path('assets/map.png') == 'assets/map_east.png'
        assert (east_extension_override_path(os.path.join('maps', 'azincournean_highlands', 'map.png'))
                == os.path.join('maps', 'azincournean_highlands', 'map_east.png'))
        assert (east_extension_override_path('assets/CampaignMaps/Campaign3Map.png')
                == 'assets/CampaignMaps/Campaign3Map_east.png')

    def test_memory_cap_on_ultrawide(self, pygame_display):
        """3440x1440 needs ~1750 source px of extension; storage stays <= the cap."""
        import pygame
        from rendering.map_extension import MapEastExtension
        from config.constants import MAP_EAST_MAX_PIXELS
        src = pygame.Surface((4096, 3072))
        src.fill((120, 140, 90))
        ext = MapEastExtension()
        ext.ensure_built(src, 3440, 1460, 1.65)
        w, h = ext.surface.get_size()
        assert ext.logical_width >= 1700
        assert w * h <= MAP_EAST_MAX_PIXELS * 1.01

    def test_failed_build_is_not_retried_every_frame(self, pygame_display, tmp_path):
        """A corrupt override falls back to the generated extension, built once."""
        import pygame
        from rendering.map_extension import MapEastExtension
        bad = tmp_path / 'map_east.png'
        bad.write_bytes(b'not a png')
        src = pygame.Surface((4096, 3072))
        ext = MapEastExtension()
        ext.ensure_built(src, 1600, 865, 1.65, str(bad))
        first = ext.surface
        assert first is not None and not ext.is_override
        ext.ensure_built(src, 1600, 865, 1.65, str(bad))
        assert ext.surface is first  # same inputs -> no rebuild


# ============================================================================
# IN-GAME RENDERING
# ============================================================================

class TestEastExtensionRendering:

    def test_gap_is_not_white_at_min_zoom(self, game):
        """The strip right of the map is drawn, not left as the frame's white fill."""
        _require_gap(game)
        _render_background(game)
        w = game.screen.get_width()
        top = game.TOP_PANEL_HEIGHT
        map_right = _map_right(game)
        for y in (top + 50, top + game.MAP_HEIGHT // 2, top + game.MAP_HEIGHT - 20):
            for x in (map_right + 2, (map_right + w) // 2, w - 2):
                assert _rgb(game.screen, (x, y)) != WHITE, f"white pixel at {(x, y)}"

    def test_far_edge_fades_to_fog(self, game):
        """The generated extension ends in the warm dark parchment fog."""
        from config.constants import MAP_EAST_FOG_COLOR
        _require_gap(game)
        _render_background(game)
        px = _rgb(game.screen, (game.screen.get_width() - 1, game.TOP_PANEL_HEIGHT + 100))
        assert all(abs(a - b) <= 40 for a, b in zip(px, MAP_EAST_FOG_COLOR)), px

    def test_seam_is_continuous(self, game):
        """First extension column ~= the map's last column (mirror is seamless)."""
        _require_gap(game)
        _render_background(game)
        map_right = _map_right(game)
        top = game.TOP_PANEL_HEIGHT
        diffs = []
        for y in range(top + 20, top + game.MAP_HEIGHT - 20, 25):
            a = _rgb(game.screen, (map_right - 1, y))
            b = _rgb(game.screen, (map_right, y))
            diffs.append(sum(abs(p - q) for p, q in zip(a, b)) / 3)
        assert sum(diffs) / len(diffs) < 25, f"visible seam (mean channel diff {sum(diffs) / len(diffs):.1f})"

    def test_no_extension_when_map_fills_window(self, game):
        """Zoomed in, the map reaches the edge; the extension isn't even built."""
        game._invalidate_map_background_caches()
        _render_background(game, zoom=3.0)
        assert game.map_east_extension.surface is None

    def test_static_camera_reuses_scaled_slice(self, game):
        """While static, the extension costs a blit — its scaled slice is reused."""
        _require_gap(game)
        _render_background(game)
        first = game.map_east_extension._view_surface
        _render_background(game)
        assert game.map_east_extension._view_surface is first

    def test_painted_override_is_used(self, game, tmp_path):
        """'<background>_east.png' replaces the generated extension."""
        import pygame
        _require_gap(game)
        magenta = (200, 30, 200)
        painted = pygame.Surface((400, 3072))
        painted.fill(magenta)
        pygame.image.save(painted, str(tmp_path / 'map_east.png'))
        game.map_background_path = str(tmp_path / 'map.png')  # only the path rule matters
        game._invalidate_map_background_caches()

        _render_background(game)
        assert game.map_east_extension.is_override
        px = _rgb(game.screen, (_map_right(game) + 3, game.TOP_PANEL_HEIGHT + 100))
        assert all(abs(a - b) <= 6 for a, b in zip(px, magenta)), px

    def test_invalidate_clears_extension(self, game):
        """Map switches and in-place cloud bakes call this; the extension must rebuild."""
        _require_gap(game)
        _render_background(game)
        assert game.map_east_extension.surface is not None
        game._invalidate_map_background_caches()
        assert game.map_east_extension.surface is None
        assert game._map_view_key is None

    def test_rebuilds_after_resolution_change(self, game):
        """apply_display_settings() must drop the extension built for the old width."""
        _require_gap(game)
        _render_background(game)
        old_key = game.map_east_extension._build_key
        old_scale = game.scale_factor
        assert game.apply_display_settings(1280, 720, False) is True
        if game.scale_factor == pytest.approx(old_scale):
            pytest.skip("display did not honour the resolution change")
        assert game.map_east_extension.surface is None
        _render_background(game)
        assert game.map_east_extension._build_key != old_key
        w = game.screen.get_width()
        assert _rgb(game.screen, (w - 2, game.TOP_PANEL_HEIGHT + 50)) != WHITE
