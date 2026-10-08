# -*- coding: utf-8 -*-
"""
Sidebar overhaul P2 — Action Queue cards, CANCEL ALL footer and the generic sidebar
mouse wheel (Game.handle_sidebar_wheel).
"""

import os
import sys
from types import SimpleNamespace

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
    """4 players, teams [0, 0, 1, 1]: player 1 is the local player's ally."""
    from main import Game
    g = Game()
    g.initialize_game({
        'num_players': 4,
        'player_is_ai': [False, True, True, True],
        'player_ai_difficulty': [None, 1, 1, 1],
        'player_teams': [0, 0, 1, 1],
    })
    g.apply_display_settings(1600, 900, False)
    gs = g.game_state
    gs.phase = 'playing'
    gs.current_player = 0
    gs.active_sidebar_tab = 'action_queue'
    g.tutorial_mission = None
    for i, territory in enumerate(g.scaled_polygons):
        gs.territory_owners[territory] = i % 4
    return g


def _territory_of(game, owner, skip=0):
    owned = [t for t, o in game.game_state.territory_owners.items() if o == owner]
    return owned[skip]


def _order(game, to_owner, n_units=3, typed=True, src_skip=0):
    from game_state import MovementOrder
    gs = game.game_state
    src = _territory_of(game, 0, src_skip)
    dst = _territory_of(game, to_owner, 1 if to_owner == 0 else 0)
    ids = []
    if typed:
        garrison = gs.territory_garrisons.setdefault(src, {}).setdefault(0, {'unmoved': 10, 'moved': 0})
        units = garrison.setdefault('units', [])
        for k in range(n_units):
            uid = f"t_{len(gs.movement_orders)}_{k}"
            units.append({'id': uid, 'status': 'ready', 'order': None,
                          'type': ['Swordsman', 'Archer'][k % 2], 'xp': 0, 'level': 0})
            ids.append(uid)
    order = MovementOrder(src, dst, n_units, 0, unit_ids=ids)
    gs.movement_orders.append(order)
    return order


def _over_panel(game):
    lay = game.get_sidebar_layout()
    return (lay.panel_x + 120, lay.top + lay.height // 2)


# ============================================================================
# ORDER KIND / COMPOSITION
# ============================================================================

class TestOrderKind:

    def test_own_ally_attack(self, game):
        ui = game.ui_renderer
        assert ui._order_kind(0, _territory_of(game, 0)) == 'own'
        # The old card showed allied reinforcements in attack red
        assert ui._order_kind(0, _territory_of(game, 1)) == 'ally'
        assert ui._order_kind(0, _territory_of(game, 2)) == 'attack'

    def test_neutral_is_an_attack(self, game):
        territory = _territory_of(game, 3)
        game.game_state.territory_owners[territory] = -1
        assert game.ui_renderer._order_kind(0, territory) == 'attack'


class TestComposition:

    def test_typed_units_are_counted_in_fixed_order(self, game):
        order = _order(game, 2, n_units=3)
        comp = game.ui_renderer._order_composition(order.from_territory, 0, order.unit_ids, 3)
        assert comp == [('Swordsman', 2), ('Archer', 1)]

    def test_count_only_order_falls_back_to_the_count(self, game):
        order = _order(game, 2, n_units=4, typed=False)
        assert game.ui_renderer._order_composition(order.from_territory, 0, [], 4) == [(None, 4)]


# ============================================================================
# DRAWING, SCROLLING, BUTTONS
# ============================================================================

class TestQueueDrawing:

    def test_many_orders_scroll_and_rects_stay_in_the_viewport(self, game):
        for i in range(40):
            _order(game, (0, 1, 2)[i % 3], n_units=2, src_skip=i % 5)
        game.draw_order_sidebar()
        scroll = game.sidebar_scroll['action_queue']
        assert scroll.max_offset > 0
        buttons = game.order_cancel_buttons
        assert 0 < len(buttons) < 40   # only the visible ones are clickable
        for rect, order, index in buttons:
            assert order in game.game_state.movement_orders
            assert rect.bottom <= game.cancel_all_button.top

    def test_cards_never_reach_cancel_all(self, game):
        for i in range(12):
            _order(game, 2, src_skip=i % 5)
        game.draw_order_sidebar()
        assert game.cancel_all_button is not None
        for rect, entry in game.order_card_rects:
            assert rect.bottom <= game.cancel_all_button.top

    def test_cancel_all_is_centred_on_the_tapestry(self, game):
        from ui.sidebar_layout import content_geometry
        _order(game, 2)
        game.draw_order_sidebar()
        lay = game.get_sidebar_layout()
        centre = content_geometry(lay.panel_x, lay.top, lay.height).center_x
        assert abs(game.cancel_all_button.centerx - centre) <= 1

    def test_index_matches_the_players_order_position(self, game):
        orders = [_order(game, 2, src_skip=i) for i in range(3)]
        game.draw_order_sidebar()
        for rect, order, index in game.order_cancel_buttons:
            assert orders[index] is order

    def test_cancel_order_click_cancels_and_flashes(self, game):
        first, second = _order(game, 2), _order(game, 0, src_skip=1)
        game.draw_order_sidebar()
        rect = next(r for r, o, i in game.order_cancel_buttons if o is second)
        game.mouse.handle_left_click(rect.center)
        assert second not in game.game_state.movement_orders
        assert first in game.game_state.movement_orders
        assert game.clicked_element == ('sidebar_cancel_order', second.order_id)

    def test_cancel_all_click_cancels_and_flashes(self, game):
        _order(game, 2)
        _order(game, 1, src_skip=1)
        game.draw_order_sidebar()
        game.mouse.handle_left_click(game.cancel_all_button.center)
        assert [o for o in game.game_state.movement_orders if o.player == 0] == []
        assert game.clicked_element == ('sidebar_cancel_all', None)

    def test_locked_cancel_all_looks_locked(self, game):
        import pygame
        _order(game, 2)
        game.mouse_pos = (0, 0)
        game.draw_order_sidebar()
        rect = game.cancel_all_button
        normal = sum(pygame.transform.average_color(game.screen, rect)[:3])
        game.tutorial_mission = SimpleNamespace(
            active=True, should_highlight_button=lambda b: False, is_button_locked=lambda b: False,
            is_action_allowed=lambda a, **k: a not in ('cancel_order', 'cancel_all_orders'))
        game.draw_order_sidebar()
        locked = sum(pygame.transform.average_color(game.screen, game.cancel_all_button)[:3])
        assert locked < normal * 0.85

    def test_empty_queue(self, game):
        game.game_state.movement_orders = []
        game.draw_order_sidebar()
        assert game.cancel_all_button is None
        assert game.order_cancel_buttons == []


class TestSubmittedOrders:

    def test_submitted_sim_orders_are_listed_read_only(self, game):
        sim = SimpleNamespace(
            players_ready={0: True},
            player_orders={0: [
                {'type': 'movement', 'player_id': 0, 'from_territory': _territory_of(game, 0),
                 'to_territory': _territory_of(game, 2), 'army_count': 3, 'unit_ids': []},
                {'type': 'build', 'player_id': 0},
            ]},
            sim_phase='planning',
        )
        game.sim_state = sim
        try:
            game.game_state.movement_orders = []
            game.draw_order_sidebar()
            entries = [entry for rect, entry in game.order_card_rects]
            assert len(entries) == 1 and entries[0].submitted
            assert game.order_cancel_buttons == []      # no cancelling after Ready
            assert game.cancel_all_button is None
        finally:
            game.sim_state = None


# ============================================================================
# GENERIC SIDEBAR WHEEL
# ============================================================================

class TestSidebarWheel:

    def test_wheel_scrolls_the_queue_not_the_map(self, game, monkeypatch):
        import pygame
        for i in range(30):
            _order(game, 2, src_skip=i % 5)
        game.draw_order_sidebar()
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: _over_panel(game))
        zoom_before = game.camera.target_zoom
        game.handle_camera_zoom(-1)    # wheel down
        assert game.sidebar_scroll['action_queue'].offset > 0
        assert game.camera.target_zoom == zoom_before

    def test_wheel_over_a_tab_without_scroll_never_zooms(self, game, monkeypatch):
        import pygame
        game.game_state.active_sidebar_tab = 'technology'
        game.draw_order_sidebar()
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: _over_panel(game))
        zoom_before = game.camera.target_zoom
        game.handle_camera_zoom(1)
        assert game.camera.target_zoom == zoom_before

    def test_wheel_off_the_panel_still_zooms(self, game, monkeypatch):
        import pygame
        game.draw_order_sidebar()
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (300, 300))
        assert game.handle_sidebar_wheel(1) is False

    def test_collapsed_sidebar_does_not_take_the_wheel(self, game, monkeypatch):
        import pygame
        game.toggle_sidebar(expand=False, animate=False)
        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: _over_panel(game))
        assert game.handle_sidebar_wheel(1) is False

    def test_new_game_resets_scroll(self, game):
        game.sidebar_scroll['action_queue'].offset = 120
        game.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                              'player_ai_difficulty': [None, 1]})
        assert game.sidebar_scroll['action_queue'].offset == 0
