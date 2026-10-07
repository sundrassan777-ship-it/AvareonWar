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

    def test_default_stretch_continues_the_edge_not_a_reflection(self, pygame_display):
        """Geography must carry on outward, not bend back (mirror reversed the NE coast
        of Azincournean). Source: red inland, a blue last few columns at the edge ->
        the extension continues blue; a mirror would bring the red back."""
        import pygame
        from rendering.map_extension import MapEastExtension
        from config.constants import MAP_EAST_MODE
        assert MAP_EAST_MODE == 'stretch'
        src = pygame.Surface((4096, 3072))
        src.fill((220, 20, 20))
        src.fill((20, 20, 220), pygame.Rect(4096 - 8, 0, 8, 3072))
        ext = MapEastExtension()
        ext.ensure_built(src, 1600, 865, 1.65)
        w, h = ext.surface.get_size()
        r, g, b = tuple(ext.surface.get_at((int(w * 0.3), h // 2)))[:3]
        assert b > r, f"extension reflected the inland colour: {(r, g, b)}"

        mirror = MapEastExtension(mode='mirror')
        mirror.ensure_built(src, 1600, 865, 1.65)
        r, g, b = tuple(mirror.surface.get_at((int(w * 0.3), h // 2)))[:3]
        assert r > b, "sanity: the mirror mode does bring the inland colour back"

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


# ============================================================================
# PART 2 — SIDEBAR LAYOUT (ui/sidebar_layout.py) AND HIT-TESTING
# ============================================================================

class TestSidebarLayoutMath:

    def test_progress_endpoints_and_no_animation(self):
        from ui.sidebar_layout import sidebar_progress
        assert sidebar_progress(True, None, 1000, 150) == 1.0
        assert sidebar_progress(False, None, 1000, 150) == 0.0
        # Finished slide == target
        assert sidebar_progress(False, 0, 1000, 150) == 0.0
        assert sidebar_progress(True, 0, 1000, 150) == 1.0

    def test_progress_mid_slide(self):
        from ui.sidebar_layout import sidebar_progress
        # Half-way, smoothstep(0.5) == 0.5 in both directions
        assert sidebar_progress(True, 1000, 1075, 150) == pytest.approx(0.5)
        assert sidebar_progress(False, 1000, 1075, 150) == pytest.approx(0.5)
        # Collapsing starts at 1 and ends at 0
        assert sidebar_progress(False, 1000, 1000, 150) == pytest.approx(1.0)

    def test_reversal_is_continuous(self):
        """Toggling mid-slide resumes from the current position (no jump)."""
        from ui.sidebar_layout import sidebar_progress, reverse_anim_start
        start, now, dur = 1000, 1030, 150           # 20% into an expand
        before = sidebar_progress(True, start, now, dur)
        new_start = reverse_anim_start(start, now, dur)
        after = sidebar_progress(False, new_start, now, dur)
        assert after == pytest.approx(before)
        # A finished slide restarts fresh
        assert reverse_anim_start(0, 5000, dur) == 5000
        assert reverse_anim_start(None, 5000, dur) == 5000

    def test_layout_geometry(self):
        from ui.sidebar_layout import compute_sidebar_layout
        expanded = compute_sidebar_layout(1600, 46, 649, 1.0, 250, 40)
        assert expanded.panel_x == 1350 and expanded.tab_x == 1310 and expanded.panel_visible
        collapsed = compute_sidebar_layout(1600, 46, 649, 0.0, 250, 40)
        # Panel fully off-screen; bookmark tabs flush with the right screen edge
        assert collapsed.panel_x == 1600 and collapsed.tab_x == 1560
        assert not collapsed.panel_visible


class TestSidebarHitTesting:

    def test_expanded_geometry_unchanged(self, game):
        """Expanded sidebar sits exactly where it always did."""
        import main
        layout = game.get_sidebar_layout()
        assert layout.panel_x == main.WINDOW_WIDTH - main.UIConstants.SIDEBAR_WIDTH
        assert layout.progress == 1.0

    def test_panel_body_is_bounded_to_the_map_height(self, game):
        import main
        x = main.WINDOW_WIDTH - 100
        assert game.is_point_over_sidebar_panel((x, main.TOP_PANEL_HEIGHT + 50))
        # Bottom UI below the sidebar is NOT the sidebar (Demolish Keep regression)
        assert not game.is_point_over_sidebar_panel((x, main.BOTTOM_UI_Y + 10))
        assert game.mouse.get_click_area((x, main.BOTTOM_UI_Y + 10)) == 'bottom_ui'
        assert game.mouse.get_click_area((x, main.TOP_PANEL_HEIGHT + 50)) == 'sidebar'

    def test_tabs_count_as_sidebar(self, game):
        game.draw_order_sidebar()  # rebuilds the tab rects
        tab = game.sidebar_tab_buttons['technology']
        assert game.is_point_on_sidebar_chrome(tab.center)
        assert game.is_point_over_sidebar(tab.center)
        # Just left of the tab column is map
        assert not game.is_point_over_sidebar((tab.x - 5, tab.centery))

    def test_collapsed_panel_area_is_map(self, game):
        """With the panel collapsed its former area is map for every check."""
        import main
        game.game_state.sidebar_expanded = False
        game._sidebar_anim_start_ms = None
        game.sidebar_tab_buttons = {}
        game.sidebar_toggle_button = None
        pos = (main.WINDOW_WIDTH - 150, main.TOP_PANEL_HEIGHT + main.MAP_HEIGHT // 2)
        assert not game.is_point_over_sidebar(pos)
        assert game.mouse.get_click_area(pos) == 'map_area'

    def test_ai_turn_whitelist_follows_tabs_only(self, game):
        """AI turns allow clicks on the tabs, not the 50 px of map left of them."""
        import main
        game.draw_order_sidebar()
        tab = game.sidebar_tab_buttons['action_log']
        assert game._is_ai_turn_click_allowed(tab.center)
        assert not game._is_ai_turn_click_allowed((tab.x - 30, tab.centery))  # old leak
        assert game._is_ai_turn_click_allowed((10, main.TOP_PANEL_HEIGHT - 2))  # top panel
        # Tab x band but inside the bottom UI: the old x-only band let this through
        assert not game._is_ai_turn_click_allowed((tab.centerx, main.BOTTOM_UI_Y + 20))


class TestToggleSidebar:

    def test_toggle_flips_and_animates(self, game):
        gs = game.game_state
        assert gs.sidebar_expanded
        assert game.toggle_sidebar() is True
        assert gs.sidebar_expanded is False
        assert game.is_sidebar_animating()
        assert game.toggle_sidebar(expand=False) is False  # already collapsed
        assert game.toggle_sidebar(expand=True, animate=False) is True
        assert gs.sidebar_expanded and not game.is_sidebar_animating()

    def test_mission_forbids_collapse_but_never_expand(self, game):
        from types import SimpleNamespace
        game.tutorial_mission = SimpleNamespace(
            active=True, is_action_allowed=lambda a, **k: a != 'toggle_sidebar')
        assert not game.can_collapse_sidebar()
        assert game.toggle_sidebar() is False
        assert game.game_state.sidebar_expanded
        # Expanding is always allowed so the panel can never get stuck closed
        game.game_state.sidebar_expanded = False
        assert game.toggle_sidebar() is True
        # An inactive mission does not restrict anything
        game.tutorial_mission.active = False
        assert game.can_collapse_sidebar()

    def test_real_tutorial_refuses_toggle(self):
        """TutorialMission refuses 'toggle_sidebar' (decision: no collapse in the tutorial)."""
        from types import SimpleNamespace
        from tutorial_mission import TutorialMission
        mission = TutorialMission.__new__(TutorialMission)
        mission.active = True
        mission.current_step_index = 0
        mission.steps = [SimpleNamespace(
            allowed_actions={'camera': True, 'sidebar_tabs': ['technology']},
            movement_whitelist=None)]
        assert mission.is_action_allowed('toggle_sidebar') is False

    def test_toggle_clears_tech_particles(self, game):
        """Particles store absolute positions; after the panel moves they'd float over the map."""
        game.ui_renderer.tech_particles.append({'x': 1400, 'y': 300})
        game.toggle_sidebar()
        assert game.ui_renderer.tech_particles == []

    def test_new_game_starts_expanded(self, game):
        game.toggle_sidebar(animate=True)
        game.initialize_game({
            'num_players': 2,
            'player_is_ai': [False, True],
            'player_ai_difficulty': [None, 'Normal'],
        })
        assert game.game_state.sidebar_expanded
        assert game._sidebar_anim_start_ms is None


class TestBottomStripHover:
    """
    Pre-existing bug fixed alongside the migration: hover and tooltips compared the
    cursor y with MAP_HEIGHT (a height) instead of BOTTOM_UI_Y (a y), so the lowest
    TOP_PANEL_HEIGHT px of the map never highlighted nor showed tooltips.
    """

    def _point_over_territory_near_bottom(self, game):
        import main
        y = main.BOTTOM_UI_Y - 5
        for x in range(40, main.WINDOW_WIDTH - 400, 7):
            world = game.screen_to_world((x, y))
            territory = game.get_territory_at_pos(world)
            if territory and not game.get_plot_at_pos(world):
                return (x, y), territory
        pytest.skip("no territory under the bottom strip at this camera position")

    def test_hover_reaches_the_bottom_of_the_map(self, game):
        _set_camera(game, game.camera.min_zoom)
        pos, _territory = self._point_over_territory_near_bottom(game)
        game.handle_mouse_motion(pos)
        assert game.hovered_territory is not None or game.hovered_army is not None

    def test_tooltip_reaches_the_bottom_of_the_map(self, game, monkeypatch):
        import pygame
        _set_camera(game, game.camera.min_zoom)
        pos, territory = self._point_over_territory_near_bottom(game)
        calls = []
        monkeypatch.setattr(game, 'draw_territory_hover_tooltip', lambda p: calls.append(p))
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: pos)
        game.mouse_pos = pos
        game.hover_start_time = None
        game.show_tooltip_army = None
        game.show_tooltip_button = None
        game.show_tooltip_territory = territory
        game.update_frame_tooltips()
        assert calls, "territory tooltip suppressed in the lowest strip of the map"
