# -*- coding: utf-8 -*-
"""
Tests: Phase 5 of the Action Failure Feedback effort — army orders (right-click a
territory with units selected in the army strip).

Refusals now give the denial sound + toast instead of an Action Log line only:
  reinforce_limit, not_adjacent ("Cannot reach target territory!"), unit_not_ready,
  target_blocked (Mission 6), wrong_phase (simultaneous 'resolving').
Silent by decision: right-click without units selected, destination == source,
tutorial blocks.

Also: main.py's own reinforcement pre-check was removed. It counted the selected
units' existing order to the same destination twice and refused valid re-orders;
the rule inside add_movement_order_for_units() (after the auto-cancel) decides.
"""

import os
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import map_data
# conftest.py autouse fixture handles load_polygons() + cleanup

from game_state import GameState

FROM = "Lobardia"
NEIGHBOUR = "Lentria"   # adjacent to Lobardia
FAR_AWAY = "Nordia"     # not adjacent to Lobardia


def _give_garrison(gs, territory, player, count, status='ready'):
    gs.territory_owners[territory] = player
    units = [gs._make_unit("Swordsman", i, status) for i in range(count)]
    gs.territory_garrisons[territory] = {}
    gs.add_garrison(territory, player, unmoved=count, moved=0, units=units)
    gs.army_units[territory] = units[:]
    gs.armies[territory] = count
    gs.armies_unmoved[territory] = count
    return units


@pytest.fixture
def gs():
    state = GameState(num_players=2, player_is_ai=[False, False],
                      player_ai_difficulty=[1, 1], skip_setup_phase=True)
    state.current_player = 0
    state.turn_phase = 'planning'
    return state


# ===========================================================================
# Error codes from add_movement_order_for_units()
# ===========================================================================

class TestMovementOrderCodes:

    def test_not_adjacent(self, gs):
        _give_garrison(gs, FROM, 0, 2)
        assert gs.add_movement_order_for_units(FROM, FAR_AWAY, [0], player=0) is False
        assert gs.last_action_error == 'not_adjacent'

    def test_unit_not_ready(self, gs):
        units = _give_garrison(gs, FROM, 0, 2)
        units[1]['status'] = 'moved'
        assert gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0, 1], player=0) is False
        assert gs.last_action_error == 'unit_not_ready'

    def test_reinforce_limit_with_placeholders(self, gs):
        _give_garrison(gs, FROM, 0, 2)
        _give_garrison(gs, NEIGHBOUR, 0, gs.MAX_ARMIES_PER_TERRITORY)
        assert gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0], player=0) is False
        assert gs.last_action_error == 'reinforce_limit'
        assert gs.last_action_error_args == {'territory': NEIGHBOUR, 'limit': gs.MAX_ARMIES_PER_TERRITORY}

    def test_success_sets_no_code(self, gs):
        _give_garrison(gs, FROM, 0, 2)
        assert gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0], player=0) is True
        assert gs.last_action_error is None


# ===========================================================================
# Right-click wiring (real Game)
# ===========================================================================

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
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                       'player_ai_difficulty': [1, 1]})
    g.game_state.phase = 'playing'
    g.game_state.turn_phase = 'planning'
    g.game_state.current_player = 0
    g.tutorial_mission = None
    return g


@pytest.fixture
def target(game):
    """(territory, screen_pos) of a territory visible on screen."""
    from test_action_feedback_phase2 import _visible_territory_point
    return _visible_territory_point(game)


def _far_from(territory):
    """A territory that is not the target and not adjacent to it."""
    for t in map_data.get_all_territories():
        if t != territory and not map_data.are_adjacent(t, territory):
            return t
    pytest.fail("no non-adjacent territory")


def _open_strip(game, from_territory, count=2):
    units = _give_garrison(game.game_state, from_territory, 0, count)
    game.show_army_composition = True
    game.army_composition_territory = from_territory
    game.army_composition_player = 0
    game.selected_army_units = [u['id'] for u in units]
    return units


class TestRightClickFeedback:

    def test_unreachable_target_toasts(self, game, target):
        territory, pos = target
        _open_strip(game, _far_from(territory))
        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_right_click(pos)
        show.assert_called_once_with('not_adjacent')

    def test_reinforce_limit_toasts_with_territory(self, game, target):
        territory, pos = target
        neighbour = next(iter(map_data.get_neighbors(territory)))
        _open_strip(game, neighbour)
        _give_garrison(game.game_state, territory, 0, game.game_state.MAX_ARMIES_PER_TERRITORY)
        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_right_click(pos)
        show.assert_called_once_with('reinforce_limit', territory=territory,
                                     limit=game.game_state.MAX_ARMIES_PER_TERRITORY)

    def test_no_selection_is_silent(self, game, target):
        territory, pos = target
        game.show_army_composition = False
        game.selected_army_units = []
        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_right_click(pos)
        show.assert_not_called()

    def test_same_territory_is_silent(self, game, target):
        territory, pos = target
        _open_strip(game, territory)
        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_right_click(pos)
        show.assert_not_called()

    def test_mission_blocked_target_toasts(self, game, target):
        territory, pos = target
        _open_strip(game, next(iter(map_data.get_neighbors(territory))))
        game.tutorial_mission = SimpleNamespace(
            active=True,
            is_territory_interactive=lambda t: True,
            is_attack_target_blocked=lambda t: t == territory,
            is_action_allowed=lambda *a, **k: True,
        )
        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_right_click(pos)
        show.assert_called_once_with('target_blocked', territory=territory)

    def test_tutorial_move_block_is_silent(self, game, target):
        """A tutorial 'move' block sets no code -> no toast (by decision)."""
        territory, pos = target
        _open_strip(game, next(iter(map_data.get_neighbors(territory))))
        game.game_state.tutorial_mission = SimpleNamespace(is_action_allowed=lambda *a, **k: False)
        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_right_click(pos)
        show.assert_not_called()


class TestResolvingPhase:

    @pytest.fixture
    def sim_game(self, pygame_display):
        from main import Game
        g = Game()
        g.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                           'player_ai_difficulty': [1, 1], 'game_mode': 'simultaneous'})
        g.game_state.phase = 'playing'
        g.game_state.turn_phase = 'planning'
        g.game_state.current_player = 0
        g.tutorial_mission = None
        g.sim_state.sim_phase = 'resolving'
        return g

    def test_order_attempt_while_resolving_toasts(self, sim_game):
        from test_action_feedback_phase2 import _visible_territory_point
        territory, pos = _visible_territory_point(sim_game)
        _open_strip(sim_game, next(iter(map_data.get_neighbors(territory))))
        with mock.patch.object(sim_game, 'show_action_error') as show, \
                mock.patch.object(sim_game.game_state, 'add_movement_order_for_units') as add:
            sim_game.handle_right_click(pos)
        show.assert_called_once_with('wrong_phase')
        add.assert_not_called()

    def test_plain_right_click_while_resolving_is_silent(self, sim_game):
        from test_action_feedback_phase2 import _visible_territory_point
        territory, pos = _visible_territory_point(sim_game)
        sim_game.show_army_composition = False
        sim_game.selected_army_units = []
        with mock.patch.object(sim_game, 'show_action_error') as show:
            sim_game.handle_right_click(pos)
        show.assert_not_called()


class TestNoDoubleCountedReinforcement:

    def test_reordering_units_to_same_destination_is_allowed(self, game, target):
        """
        Destination holds 13; 2 units already have an order there (projected 15).
        Re-ordering ONE of them to the same destination must work: it leaves the old
        order, so the total stays 15. The old pre-check added it on top of its own
        existing order (15 + 1 = 16 > 15) and refused.
        """
        territory, pos = target
        gs = game.game_state
        neighbour = next(iter(map_data.get_neighbors(territory)))
        _give_garrison(gs, territory, 0, gs.MAX_ARMIES_PER_TERRITORY - 2)
        units = _open_strip(game, neighbour)
        ids = [u['id'] for u in units]
        assert gs.add_movement_order_for_units(neighbour, territory, ids, player=0)
        game.selected_army_units = [ids[0]]

        with mock.patch.object(game, 'show_action_error') as show:
            game.handle_right_click(pos)
        show.assert_not_called()
        # The unit moved into its own new order: two orders of one unit each
        assert sorted(o.army_count for o in gs.movement_orders) == [1, 1]
        assert all(o.to_territory == territory for o in gs.movement_orders)
