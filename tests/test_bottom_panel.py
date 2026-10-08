# -*- coding: utf-8 -*-
"""
Tests: the bottom panel overhaul (rendering/bottom_panel_kit.py + main.py views).

Every section of the bottom panel is laid out as: centred headline, gold rule,
content. These tests pin the shared geometry and the End Turn section:

  - section_rect() stays inside the panel and between the pillars, at 1280x720,
    1600x900, 1920x1080 and 2560x1440 (panel 180 / 211 / 253 / 300 px tall)
  - End Turn: button + timer fit their section at every resolution, even with a
    player name that wraps; greyed/highlight rules; hover and click flash change
    pixels; the turn number follows sequential vs simultaneous mode
  - CampaignBTN inner tint colours the wood only, never the gold frame

Resolutions are forced by swapping main.set_display_mode for an offscreen surface:
the window size a test machine allows (and the dummy driver's 1600x900 cap) must
not decide what gets tested.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


def _make_game(width, height, monkeypatch):
    import pygame
    import main
    # Offscreen surface of exactly the requested size (see module docstring)
    monkeypatch.setattr(main, 'set_display_mode',
                        lambda size, fs=False, vs=False, force_reinit=False: (pygame.Surface(size), False))
    monkeypatch.setattr(main, '_set_app_icon', lambda: None)
    g = main.Game()
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
    g.apply_display_settings(width, height, False)
    gs = g.game_state
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 0
    g.tutorial_mission = None
    g.mouse_pos = (0, 0)
    g.clicked_element = None
    return g


@pytest.fixture
def game(pygame_display, monkeypatch):
    return _make_game(1600, 900, monkeypatch)


@pytest.fixture(params=RESOLUTIONS, ids=lambda r: '%dx%d' % r)
def any_res_game(request, pygame_display, monkeypatch):
    return _make_game(request.param[0], request.param[1], monkeypatch)


def _panel(game):
    import pygame
    top, height = game.bottom_panel_geometry()
    return pygame.Rect(0, top, game.screen.get_width(), height)


# ===========================================================================
# Kit geometry
# ===========================================================================

class TestSectionRect:

    def test_inside_panel_and_clear_of_pillars(self, any_res_game):
        g = any_res_game
        kit = g.bottom_panel_kit
        panel = _panel(g)
        left_x, right_x = 400, 800
        rect = kit.section_rect(left_x, right_x)
        assert panel.contains(rect)
        half = g.separator_width // 2
        assert rect.left > left_x + half and rect.right < right_x - half
        # Below the wooden beam along the top edge
        assert rect.top >= panel.top + int(panel.height * 0.1)

    def test_leftmost_section_starts_at_screen_edge(self, game):
        rect = game.bottom_panel_kit.section_rect(None, 300)
        assert 0 < rect.left < 30

    def test_fonts_follow_panel_height_not_ui_scale(self, pygame_display, monkeypatch):
        """At 2560x1440 ui_scale is 1.6 but the panel only grows to 300 px (x1.42)."""
        big = _make_game(2560, 1440, monkeypatch)
        assert big.ui_scale > 1.5
        assert abs(big.bottom_panel_kit.scale - 300 / 211.0) < 0.01


# ===========================================================================
# End Turn section
# ===========================================================================

class TestEndTurnLayout:

    def test_button_and_timer_inside_section(self, any_res_game):
        g = any_res_game
        g.draw_bottom_ui()
        section = g._end_turn_section_rect()
        assert section.contains(g.end_turn_button)
        assert _panel(g).contains(g.end_turn_button)

    def test_long_name_still_fits_at_720p(self, pygame_display, monkeypatch):
        g = _make_game(1280, 720, monkeypatch)
        g.game_state.get_player_name = lambda i, include_title=True: 'Archduke Maximilian of Upper Rossenburg'
        g.draw_bottom_ui()
        section = g._end_turn_section_rect()
        assert section.contains(g.end_turn_button)

    def test_button_is_centred(self, game):
        game.draw_bottom_ui()
        section = game._end_turn_section_rect()
        assert abs(game.end_turn_button.centerx - section.centerx) <= 1


class TestEndTurnState:

    def test_normal(self, game):
        assert game._end_turn_button_state() == ('normal', 'End Turn')

    def test_locked_while_armies_move(self, game):
        game.game_state.turn_phase = 'execution'
        assert game._end_turn_button_state()[0] == 'locked'

    def test_tutorial_highlight(self, game, monkeypatch):
        game.tutorial_mission = SimpleNamespace(
            active=True, should_highlight_button=lambda b: b == 'end_turn',
            is_button_locked=lambda b: False, is_action_allowed=lambda a, **k: True,
            is_timer_visible=lambda: True)
        monkeypatch.setattr(game, '_is_tutorial_active', lambda: True)
        assert game._end_turn_button_state()[0] == 'highlight'
        game.draw_bottom_ui()  # Draws the pulse ring without errors

    def test_sim_ready_shows_waiting(self, game, monkeypatch):
        game.sim_state = SimpleNamespace(sim_phase='planning', players_ready={0: True},
                                         get_waiting_player_names=lambda: ['AI Player 2'],
                                         round_number=4)
        monkeypatch.setattr(game, 'get_local_player', lambda: 0)
        assert game._end_turn_button_state() == ('locked', 'Waiting...')
        assert game._planning_timer_info() == ('waiting', ['AI Player 2'])

    def test_sim_resolving_label(self, game):
        game.sim_state = SimpleNamespace(sim_phase='resolving', players_ready={})
        assert game._end_turn_button_state() == ('locked', 'Resolving...')


class TestTurnNumber:

    def test_sequential_is_one_based(self, game):
        game.game_state.turn_number = 0
        assert game._display_turn_number() == 1
        game.game_state.turn_number = 6
        assert game._display_turn_number() == 7

    def test_simultaneous_uses_round_number(self, game):
        game.sim_state = SimpleNamespace(round_number=5)
        assert game._display_turn_number() == 5


class TestEndTurnFeedback:
    """Hover brightens and a click flash brightens more (pixel check, like the sidebar audit)."""

    def _button_pixels(self, game):
        import pygame
        game.screen.fill((0, 0, 0))
        game.draw_bottom_ui()
        rect = game.end_turn_button
        # Sample a strip through the wood, away from the label in the middle
        y = rect.centery
        xs = [rect.left + int(rect.w * f) for f in (0.22, 0.25, 0.28, 0.72, 0.75, 0.78)]
        return [tuple(game.screen.get_at((x, y)))[:3] for x in xs]

    def test_hover_and_flash_change_pixels(self, game):
        normal = self._button_pixels(game)
        game.mouse_pos = game.end_turn_button.center
        hover = self._button_pixels(game)
        game.clicked_element = ('bottom_button', 'end_turn')
        flash = self._button_pixels(game)
        assert sum(map(sum, hover)) > sum(map(sum, normal))
        assert sum(map(sum, flash)) > sum(map(sum, hover))


# ===========================================================================
# Ornate button art
# ===========================================================================

class TestInnerTint:

    def test_wood_tinted_frame_untouched(self, pygame_display):
        from utils.surface_utils import get_campaign_button_image, tint_campaign_button_wood
        art = get_campaign_button_image()
        tinted = tint_campaign_button_wood(art, (120, 220, 110))
        w, h = art.get_size()
        # Middle of the wood: now green-dominant (it was brown: red-dominant)
        wood = tinted.get_at((w // 2, h // 2))
        assert wood.g > wood.r and art.get_at((w // 2, h // 2)).r > art.get_at((w // 2, h // 2)).g
        # Gold frame pixels INSIDE the tint window (the notch beside the left end
        # cap) are untouched - only the colour test keeps them gold
        for x, y in ((229, 192), (230, 108), (233, 102)):
            px = (round(x * w / 1502.0), round(y * h / 297.0))
            assert art.get_at(px).g >= 150 and art.get_at(px).a == 255  # really gold
            assert tinted.get_at(px) == art.get_at(px)
