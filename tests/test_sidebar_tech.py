# -*- coding: utf-8 -*-
"""
Sidebar overhaul P5 — Technology tab: connector arrow states (cached sprites), the
grid fitted to the panel height (it ran under the bottom panel at 1280x720) and the
centred header.
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


def _make_game(width, height):
    from main import Game
    g = Game()
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
    g.apply_display_settings(width, height, False)
    gs = g.game_state
    gs.phase = 'playing'
    gs.current_player = 0
    gs.active_sidebar_tab = 'technology'
    g.tutorial_mission = None
    g.mouse_pos = (0, 0)
    return g


@pytest.fixture
def game(pygame_display):
    return _make_game(1600, 900)


class TestArrowSprites:

    def test_states_differ_and_are_cached(self, game):
        w = game.sidebar_widgets
        sprites = {s: w.tech_arrow(32, s) for s in ('locked', 'open', 'done')}
        assert all(w.tech_arrow(32, s) is sprites[s] for s in sprites)   # cached
        assert all(sp.get_height() == 32 for sp in sprites.values())
        centre = {s: sp.get_at((sp.get_width() // 2, 12))[:3] for s, sp in sprites.items()}
        # Locked shaft is bronze/gold (red > green), open/done are green
        assert centre['locked'][0] > centre['locked'][2] and centre['locked'][0] >= centre['locked'][1]
        for s in ('open', 'done'):
            assert centre[s][1] > centre[s][0] and centre[s][1] > centre[s][2]
        assert centre['open'] != centre['done']

    def test_arrow_state_follows_research(self, game, monkeypatch):
        """tech_c_r researched -> arrow r is open; both ends researched -> done."""
        calls = []
        w = game.sidebar_widgets
        real = w.tech_arrow
        monkeypatch.setattr(w, 'tech_arrow', lambda length, state: calls.append(state) or real(length, state))
        game.game_state.player_tech_researched[0] = {'tech_0_0', 'tech_0_1', 'tech_1_0'}
        game.draw_order_sidebar()
        # Arrows are drawn column by column, rows 0-5
        assert len(calls) == 18
        assert calls[0:3] == ['done', 'open', 'locked']      # column 0
        assert calls[6:8] == ['open', 'locked']              # column 1
        assert calls[12] == 'locked'                         # column 2


class TestGridFit:

    @pytest.mark.parametrize('size', [(1280, 720), (1600, 900), (1920, 1080)])
    def test_all_tiles_inside_panel(self, pygame_display, size):
        g = _make_game(*size)
        g.draw_order_sidebar()
        lay = g.get_sidebar_layout()
        tiles = list(g.technology_buttons.values())
        assert len(tiles) == 21
        panel_bottom = lay.top + lay.height
        assert max(r.bottom for r in tiles) <= panel_bottom
        assert min(r.left for r in tiles) >= lay.panel_x
        assert max(r.right for r in tiles) <= lay.panel_x + 250 * 2   # sanity (scaled panels)

    def test_full_size_tiles_at_1600(self, game):
        game.draw_order_sidebar()
        assert {r.width for r in game.technology_buttons.values()} == {54}

    def test_grid_centred_on_tapestry(self, game):
        from ui.sidebar_layout import content_geometry
        from ui.scaler import UIConstants
        game.draw_order_sidebar()
        lay = game.get_sidebar_layout()
        full = content_geometry(lay.panel_x, lay.top, lay.height, panel_width=UIConstants.SIDEBAR_WIDTH)
        tiles = list(game.technology_buttons.values())
        middle = (min(r.left for r in tiles) + max(r.right for r in tiles)) / 2
        assert abs(middle - full.center_x) <= 1
