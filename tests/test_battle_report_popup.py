# -*- coding: utf-8 -*-
"""
Tests for the Battle Report UI layer.

Covers the popup's text/geometry rules (ui/battle_report_popup.py) and the
report-only mode of EnhancedBattleInterface that the Detail button opens.

Needs a display surface because both load assets with convert_alpha(), so it
opens a dummy-driver window like test_battle_interface_integration.py does.
"""

import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import map_data  # noqa: E402  (conftest autouse fixture handles load/cleanup)
from game_state import GameState  # noqa: E402
from config.font_manager import FontManager  # noqa: E402
from ui.battle_report_popup import (  # noqa: E402
    BattleReportPopupRenderer,
    build_report_lines,
)
from ui.effects.battle_interface import (  # noqa: E402
    BattleInterfaceState,
    EnhancedBattleInterface,
)
from rendering.helpers import DrawingHelpers  # noqa: E402


SCREEN_W, SCREEN_H = 1600, 900
TOP = 60
BOTTOM = 760


def _report(**overrides):
    """A LOST report; override any field."""
    report = {
        'territory': 'Lobardia',
        'turn_number': 3,
        'defender': 1,
        'attacker': 0,
        'held': False,
        'units_lost': 3,
        'units_remaining': 0,
        'structures_destroyed': 2,
        'structures_captured': 0,
        'structures_remaining': 0,
        'unit_breakdown': {
            'Swordsman': {'original': 3, 'survived': 0, 'lost': 3},
        },
        'attacker_lost': 1,
        'attacker_survivors': 17,
        'defender_lost': 3,
        'defender_survivors': 0,
    }
    report.update(overrides)
    return report


@pytest.fixture(scope='module')
def screen():
    pygame.init()
    pygame.display.set_mode((SCREEN_W, SCREEN_H))
    surface = pygame.display.get_surface()
    yield surface
    pygame.display.quit()
    pygame.quit()


class _FakeGame:
    """
    Minimal stand-in exposing only what the renderer reads off Game.

    Avoids constructing the real Game (which opens menus, sound and networking)
    while still exercising the real fonts, helpers and scale maths.
    """

    def __init__(self, surface):
        self.screen = surface
        self.ui_scale = 1.0
        pygame.font.init()
        font_manager = FontManager()
        self.small_font = font_manager.get_font(12)
        self.small_font_bold = font_manager.get_bold_font(12)
        self.mouse_pos = (-1, -1)
        self.clicked_element = None
        self.menu_button_img = None
        self.helpers = DrawingHelpers(surface, self.small_font, self.small_font_bold,
                                       self.small_font)
        self._text_cache = {}

    def scale(self, value):
        return int(value * self.ui_scale)

    def _get_cached_text(self, text, font, color):
        key = (text, id(font), color)
        if key not in self._text_cache:
            self._text_cache[key] = font.render(text, True, color)
        return self._text_cache[key]


@pytest.fixture
def game(screen):
    return _FakeGame(screen)


@pytest.fixture
def renderer(game):
    return BattleReportPopupRenderer(game)


# ===========================================================================
# Body text
# ===========================================================================

class TestReportLines:

    def test_loss_lines(self):
        lines = build_report_lines(_report())
        assert lines == [" - 3 Units Lost", " - 2 Structures Destroyed"]

    def test_defended_lines(self):
        lines = build_report_lines(_report(
            held=True, units_remaining=1, structures_remaining=2))
        assert lines == [" - 1 Unit Remaining", " - 2 Structures Remaining"]

    def test_singular_and_plural(self):
        lines = build_report_lines(_report(units_lost=1, structures_destroyed=1))
        assert lines[0] == " - 1 Unit Lost"
        assert lines[1] == " - 1 Structure Destroyed"

    def test_captured_line_only_when_seledra_saved_something(self):
        """The third line exists only when Champion of the People fired."""
        assert len(build_report_lines(_report(structures_captured=0))) == 2

        lines = build_report_lines(_report(
            structures_destroyed=1, structures_captured=2))
        assert lines == [
            " - 3 Units Lost",
            " - 1 Structure Destroyed",
            " - 2 Structures Captured",
        ]

    def test_zero_units_lost_still_reported(self):
        """An uncontested capture or a Keep-only defence has no unit losses."""
        lines = build_report_lines(_report(units_lost=0))
        assert lines[0] == " - 0 Units Lost"


# ===========================================================================
# Geometry
# ===========================================================================

class TestPopupGeometry:

    def _bounds(self):
        return (0, TOP, SCREEN_W, BOTTOM)

    def test_stays_anchored_to_the_territory(self, renderer):
        """
        The popup belongs to a place on the map, so it must track the territory
        exactly and NOT be clamped into view. Parking it against the screen edge
        when you pan away would read as a HUD element and misreport where the
        battle happened.
        """
        bounds = self._bounds()
        first = renderer.get_layout(_report(), (800, 400), bounds)['panel_rect']
        moved = renderer.get_layout(_report(), (500, 250), bounds)['panel_rect']

        assert moved.x == first.x - 300
        assert moved.y == first.y - 150

    def test_is_centred_on_the_territory(self, renderer):
        """
        Centred on both axes, so the popup is visible whenever its territory is.
        Placing it above the territory meant one near the top of the map band was
        culled entirely while the territory itself was still in plain view.
        """
        bounds = self._bounds()
        anchor = (800, 400)
        panel = renderer.get_layout(_report(), anchor, bounds)['panel_rect']
        assert abs(panel.centerx - anchor[0]) <= 1
        assert abs(panel.centery - anchor[1]) <= 1

    def test_visible_territory_always_has_a_visible_report(self, renderer):
        """
        Wherever the territory centre lands inside the band, some of its report is on
        screen. This is the property centring buys: placing the popup above the
        territory culled it entirely for anything near the top edge.
        """
        bounds = self._bounds()
        band = pygame.Rect(0, TOP, SCREEN_W, BOTTOM - TOP)
        for anchor in [(1, TOP + 1), (SCREEN_W - 1, TOP + 1), (1, BOTTOM - 1),
                       (SCREEN_W - 1, BOTTOM - 1), (SCREEN_W // 2, TOP + 1),
                       (SCREEN_W // 2, BOTTOM - 1), (800, 400)]:
            panel = renderer.get_layout(_report(), anchor, bounds)['panel_rect']
            assert panel.colliderect(band), (anchor, panel)

    def test_buttons_are_clickable_away_from_the_band_edges(self, renderer, game):
        """
        The buttons sit at the bottom of the board, so a territory centred within
        half a popup of an edge can have them clipped away entirely. They must be
        reachable everywhere else; "Close All Battle Reports" covers the rest.
        """
        bounds = self._bounds()
        layout = renderer.get_layout(_report(), (800, 400), bounds)
        margin_x = layout['panel_rect'].width
        margin_y = layout['panel_rect'].height

        for anchor in [(margin_x, TOP + margin_y), (SCREEN_W - margin_x, TOP + margin_y),
                       (margin_x, BOTTOM - margin_y),
                       (SCREEN_W - margin_x, BOTTOM - margin_y), (800, 400)]:
            rects = renderer.draw(
                game.screen, [_report()], bounds, lambda r, a=anchor: a)
            assert [entry[1] for entry in rects] == ['detail', 'close'], anchor

    def test_follows_the_territory_off_screen(self, renderer):
        """Panning far away must carry the popup out of the view entirely."""
        bounds = self._bounds()
        for anchor in [(-4000, -4000), (9000, 9000), (-2000, 400)]:
            panel = renderer.get_layout(_report(), anchor, bounds)['panel_rect']
            band = pygame.Rect(0, TOP, SCREEN_W, BOTTOM - TOP)
            assert not panel.colliderect(band), (anchor, panel)

    def test_offscreen_popups_are_culled_and_produce_no_hit_rects(self, renderer, game):
        rects = renderer.draw(
            game.screen, [_report()], self._bounds(), lambda r: (-5000, -5000))
        assert rects == []

    def test_hit_rects_are_clipped_to_the_visible_band(self, renderer, game):
        """
        A button hanging below the map must not take clicks where it is hidden,
        or Priority 0 would swallow them before the bottom panel sees them.
        """
        bounds = self._bounds()
        # Anchor low enough that the popup straddles the bottom edge of the band.
        anchor = (800, BOTTOM + 40)
        layout = renderer.get_layout(_report(), anchor, bounds)
        assert layout['panel_rect'].bottom > BOTTOM, "test anchor must straddle the edge"

        rects = renderer.draw(game.screen, [_report()], bounds, lambda r: anchor)
        for rect, _action, _report_obj in rects:
            assert rect.bottom <= BOTTOM, rect
            assert rect.top >= TOP, rect

    def test_drawing_restores_the_previous_clip(self, renderer, game):
        """The clip is shared state; leaking it would break later drawing."""
        game.screen.set_clip(None)
        renderer.draw(game.screen, [_report()], self._bounds(), lambda r: (800, 400))
        assert game.screen.get_clip() == game.screen.get_rect()

    def test_buttons_sit_inside_the_board(self, renderer):
        layout = renderer.get_layout(_report(), (800, 400), self._bounds())
        board = layout['board_rect']
        for key in ('detail_rect', 'close_rect'):
            assert board.contains(layout[key]), key

    def test_detail_is_left_of_close_and_they_do_not_overlap(self, renderer):
        layout = renderer.get_layout(_report(), (800, 400), self._bounds())
        detail, close = layout['detail_rect'], layout['close_rect']
        assert detail.right <= close.left
        assert detail.width == close.width

    def test_board_sits_inside_the_panel(self, renderer):
        """Content insets against the visible board, not the feathered surface."""
        layout = renderer.get_layout(_report(), (800, 400), self._bounds())
        assert layout['panel_rect'].contains(layout['board_rect'])
        assert layout['board_rect'].top > layout['panel_rect'].top
        assert layout['board_rect'].left > layout['panel_rect'].left

    def test_three_line_report_is_taller(self, renderer):
        """A Seledra report has an extra line, so the panel must grow."""
        bounds = self._bounds()
        two = renderer.get_layout(_report(), (800, 400), bounds)
        three = renderer.get_layout(
            _report(structures_captured=2), (800, 400), bounds)
        assert three['panel_rect'].height > two['panel_rect'].height

    def test_title_reflects_outcome(self, renderer):
        bounds = self._bounds()
        assert renderer.get_layout(_report(), (800, 400), bounds)['title'] == "LOST"
        held = renderer.get_layout(_report(held=True), (800, 400), bounds)
        assert held['title'] == "DEFENDED"
        assert held['title_color'] != renderer.get_layout(
            _report(), (800, 400), bounds)['title_color']

    def test_size_is_independent_of_camera(self, renderer):
        """
        The popup tracks the territory but must not scale with zoom, or the text
        would become unreadable when zoomed out.
        """
        bounds = self._bounds()
        near = renderer.get_layout(_report(), (400, 300), bounds)['panel_rect']
        far = renderer.get_layout(_report(), (1200, 600), bounds)['panel_rect']
        assert near.size == far.size

    def test_draw_returns_rects_for_both_buttons(self, renderer, game):
        rects = renderer.draw(
            game.screen, [_report()], self._bounds(), lambda r: (800, 400))
        actions = [entry[1] for entry in rects]
        assert actions == ['detail', 'close']

    def test_draw_skips_reports_without_an_anchor(self, renderer, game):
        """A territory missing from scaled_centers must not crash the frame."""
        rects = renderer.draw(
            game.screen, [_report()], self._bounds(), lambda r: None)
        assert rects == []

    def test_geometry_matches_what_was_drawn(self, renderer, game):
        """Draw and hit-test share get_layout(), so they cannot desync."""
        bounds = self._bounds()
        rects = renderer.draw(
            game.screen, [_report()], bounds, lambda r: (800, 400))
        layout = renderer.get_layout(_report(), (800, 400), bounds)
        assert rects[0][0] == layout['detail_rect']
        assert rects[1][0] == layout['close_rect']


# ===========================================================================
# Detail screen (report-only EnhancedBattleInterface)
# ===========================================================================

class TestReportOnlyBattleInterface:

    @pytest.fixture
    def interface(self, screen):
        game_state = GameState(
            num_players=2, player_is_ai=[False, False],
            player_ai_difficulty=[1, 1], skip_setup_phase=True)
        # Empty pending_battles proves the report path never reads it.
        game_state.pending_battles = []
        return EnhancedBattleInterface(
            screen=screen,
            game_state=game_state,
            battle_index=None,
            font_manager=FontManager(),
            current_player_index=1,
            report_snapshot=_report(),
        )

    def test_opens_directly_in_report_state(self, interface):
        assert interface.state == BattleInterfaceState.REPORT
        assert interface.particle_effect is None
        assert interface.splash_effect is None

    def test_defender_sees_a_defeat(self, interface):
        """
        The attacker saw this battle as a victory; the defender must see the same
        fight as a defeat.
        """
        assert interface.current_player_won is False

    def test_defended_report_shows_victory(self, screen):
        game_state = GameState(
            num_players=2, player_is_ai=[False, False],
            player_ai_difficulty=[1, 1], skip_setup_phase=True)
        game_state.pending_battles = []
        ui = EnhancedBattleInterface(
            screen=screen, game_state=game_state, battle_index=None,
            font_manager=FontManager(), current_player_index=1,
            report_snapshot=_report(held=True, units_remaining=4,
                                    defender_survivors=4, defender_lost=0))
        assert ui.current_player_won is True

    def test_renders_without_touching_pending_battles(self, interface):
        """A KeyError or AttributeError here would crash the frame."""
        interface.render()

    def test_update_is_inert(self, interface):
        interface.update(0.016)
        assert interface.state == BattleInterfaceState.REPORT
        assert interface.is_finished() is False

    def test_close_button_finishes_it(self, interface):
        assert interface.handle_click(interface.close_button_rect.center) == 'close'
        assert interface.is_finished() is True

    def test_click_elsewhere_does_not_close(self, interface):
        assert interface.handle_click((1, 1)) is None
        assert interface.is_finished() is False

    def test_totals_come_from_the_defender_side(self, interface):
        """
        _render_report() picks its totals on current_player == attacker_player, so a
        defender-POV report must read defender_lost / defender_survivors.
        """
        assert interface.current_player != interface.attacker_player
        assert interface.battle_result['defender_lost'] == 3
        assert interface.battle_result['defender_survivors'] == 0

    def test_empty_breakdown_renders(self, screen):
        """Uncontested captures and Keep-only defences carry no unit breakdown."""
        game_state = GameState(
            num_players=2, player_is_ai=[False, False],
            player_ai_difficulty=[1, 1], skip_setup_phase=True)
        game_state.pending_battles = []
        ui = EnhancedBattleInterface(
            screen=screen, game_state=game_state, battle_index=None,
            font_manager=FontManager(), current_player_index=1,
            report_snapshot=_report(unit_breakdown={}, units_lost=0))
        ui.render()
