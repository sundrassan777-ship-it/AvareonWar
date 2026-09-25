# -*- coding: utf-8 -*-
"""
Tests: Phase 1 bug fixes of the Action Failure Feedback effort.

These bugs sat underneath the (upcoming) error toasts and would have made them
lie or misfire:

  1. last_action_error was only cleared when main.py read it, so a code left
     behind by an AI / remote / keyboard call was shown for a later, unrelated
     failure. Every action method now resets it on entry.
  2. add_movement_order_for_units() auto-cancelled the selected units' previous
     orders BEFORE validating the new one - a refused re-order destroyed them.
     The auto-cancel is now rolled back when validation fails.
  3. The Action Queue X buttons stored the index among the local player's orders
     but cancel_movement_order() used it on the full list (all players), so the
     wrong order could be cancelled. CANCEL ALL also wiped every player's orders.
  4. The mission 'train_hero' gate ran before the hero-button hit-test and
     swallowed every other bottom-panel click (e.g. Demolish Keep).
"""

import os
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
# conftest.py autouse fixture handles load_polygons() + cleanup

from game_state import GameState, MovementOrder


FROM = "Lobardia"
NEIGHBOUR = "Lentria"      # adjacent to Lobardia
FAR_AWAY = "Nordia"        # not adjacent to Lobardia


def _make_state():
    return GameState(
        num_players=2,
        player_is_ai=[False, False],
        player_ai_difficulty=[1, 1],
        skip_setup_phase=True,
    )


def _give_garrison(gs, territory, player, count, unit_type="Swordsman"):
    """Own the territory and place `count` ready units there (ids 0..count-1)."""
    gs.territory_owners[territory] = player
    units = [gs._make_unit(unit_type, i, 'ready') for i in range(count)]
    gs.territory_garrisons[territory] = {}
    gs.add_garrison(territory, player, unmoved=count, moved=0, units=units)
    gs.army_units[territory] = units[:]
    gs.armies[territory] = count
    gs.armies_unmoved[territory] = count
    return units


@pytest.fixture
def gs():
    state = _make_state()
    state.current_player = 0
    state.turn_phase = 'planning'
    return state


# ===========================================================================
# Bug 1 - stale last_action_error
# ===========================================================================

class TestStaleErrorCodeReset:

    def test_construction_clears_stale_code_on_codeless_failure(self, gs):
        """A code-less refusal (invalid building type) must not report an old 'gold' code."""
        gs.last_action_error = "gold"  # left behind by an earlier (e.g. AI) call
        gs.territory_owners[FROM] = 0
        assert gs.start_construction(FROM, 0, "NotABuilding") is False
        assert gs.last_action_error is None

    def test_training_clears_stale_code(self, gs):
        gs.last_action_error = "command_limit"
        gs.territory_owners[FROM] = 0
        assert gs.start_training(FROM, 0, "NotAUnit") is False
        assert gs.last_action_error is None

    def test_research_clears_stale_code(self, gs):
        gs.last_action_error = "gold"
        assert gs.start_research("no_such_tech") is False
        assert gs.last_action_error is None

    def test_hero_training_clears_stale_code(self, gs):
        gs.last_action_error = "hero_limit"
        assert gs.start_hero_training(FROM, 0, "NotAHero") is False
        assert gs.last_action_error is None

    def test_castle_upgrade_clears_stale_code(self, gs):
        gs.last_action_error = "gold"
        gs.territory_owners[FROM] = 1  # not ours -> code-less refusal
        assert gs.start_castle_upgrade(FROM, 0) is False
        assert gs.last_action_error is None

    def test_movement_order_clears_stale_code(self, gs):
        gs.last_action_error = "army_limit"
        _give_garrison(gs, FROM, 0, 2)
        assert gs.add_movement_order_for_units(FROM, FAR_AWAY, [0], player=0) is False
        assert gs.last_action_error is None

    def test_hero_ability_clears_stale_code(self, gs):
        gs.last_action_error = "gold"
        assert gs.activate_hero_ability("Nobody", 0) is False
        assert gs.last_action_error is None

    def test_real_failure_still_sets_code(self, gs):
        """The reset must not swallow a genuine code set by the same call."""
        gs.territory_owners[FROM] = 0
        gs.player_gold[0] = 0
        assert gs.start_construction(FROM, 0, "Farm") is False
        assert gs.last_action_error == "gold"


# ===========================================================================
# Bug 2 - refused re-order must keep the previous orders
# ===========================================================================

class TestReorderRollback:

    def test_not_adjacent_reorder_keeps_previous_order(self, gs):
        units = _give_garrison(gs, FROM, 0, 3)
        assert gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0, 1], player=0)
        original = gs.movement_orders[0]

        # Re-order the same units to a territory that is not adjacent -> refused
        assert gs.add_movement_order_for_units(FROM, FAR_AWAY, [0, 1], player=0) is False

        assert gs.movement_orders == [original]
        assert original.unit_ids == [0, 1]
        assert original.army_count == 2
        assert units[0]['status'] == 'ordered' and units[0]['order'] is original
        assert units[1]['status'] == 'ordered' and units[1]['order'] is original

    def test_partial_overlap_is_restored(self, gs):
        """Re-ordering a subset partially edits the old order; a refusal must undo the edit."""
        units = _give_garrison(gs, FROM, 0, 3)
        assert gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0, 1, 2], player=0)
        original = gs.movement_orders[0]

        assert gs.add_movement_order_for_units(FROM, FAR_AWAY, [1], player=0) is False

        assert gs.movement_orders == [original]
        assert original.unit_ids == [0, 1, 2]
        assert original.army_count == 3
        assert all(u['status'] == 'ordered' and u['order'] is original for u in units)

    def test_reinforce_limit_reorder_keeps_previous_order(self, gs):
        _give_garrison(gs, FROM, 0, 3)
        _give_garrison(gs, NEIGHBOUR, 0, gs.MAX_ARMIES_PER_TERRITORY)  # full friendly target
        other = "Venexia"  # also adjacent to Lobardia, free for the first order
        gs.territory_owners[other] = 1
        assert gs.add_movement_order_for_units(FROM, other, [0], player=0)
        original = gs.movement_orders[0]

        assert gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0], player=0) is False
        assert gs.movement_orders == [original]

    def test_refused_reorder_does_not_log_cancellation(self, gs):
        _give_garrison(gs, FROM, 0, 2)
        gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0], player=0)
        gs.messages.clear()
        gs.add_movement_order_for_units(FROM, FAR_AWAY, [0], player=0)
        assert not any("Previous orders" in str(m) for m in gs.messages)

    def test_successful_reorder_still_replaces_previous_order(self, gs):
        """Unchanged behaviour: a valid re-order replaces the old one."""
        _give_garrison(gs, FROM, 0, 2)
        gs.add_movement_order_for_units(FROM, NEIGHBOUR, [0], player=0)
        assert gs.add_movement_order_for_units(FROM, "Venexia", [0], player=0)
        assert len(gs.movement_orders) == 1
        assert gs.movement_orders[0].to_territory == "Venexia"


# ===========================================================================
# Bug 3 - cancelling the right order
# ===========================================================================

def _order(player, frm, to):
    return MovementOrder(from_territory=frm, to_territory=to, army_count=1, player=player, unit_ids=[])


class TestOrderCancelIndex:

    def test_get_full_order_index_skips_other_players(self, gs):
        gs.movement_orders = [_order(1, "A", "B"), _order(0, "C", "D"), _order(1, "E", "F"), _order(0, "G", "H")]
        assert gs.get_full_order_index(0, 0) == 1
        assert gs.get_full_order_index(0, 1) == 3
        assert gs.get_full_order_index(1, 1) == 2
        assert gs.get_full_order_index(0, 2) is None
        assert gs.get_full_order_index(0, -1) is None

    def test_cancel_all_for_player_keeps_other_players_orders(self, gs):
        mine, theirs = _order(0, "A", "B"), _order(1, "C", "D")
        gs.movement_orders = [theirs, mine]
        assert gs.cancel_all_orders(player=0) == 1
        assert gs.movement_orders == [theirs]

    def test_cancel_all_without_player_is_unchanged(self, gs):
        gs.movement_orders = [_order(0, "A", "B"), _order(1, "C", "D")]
        assert gs.cancel_all_orders() == 2
        assert gs.movement_orders == []


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
    g.game_state.turn_phase = 'planning'
    g.game_state.current_player = 0
    g.tutorial_mission = None
    return g


class TestOrderCancelClick:

    def test_x_button_cancels_its_own_order(self, game):
        """The X of the local player's 1st order must cancel that order, not movement_orders[0]."""
        import pygame
        gs = game.game_state
        ai_order, my_order = _order(1, "A", "B"), _order(0, "C", "D")
        gs.movement_orders = [ai_order, my_order]
        gs.sidebar_expanded = True
        game.sidebar_tab_buttons = {}
        rect = pygame.Rect(10, 10, 20, 20)
        game.order_cancel_buttons = [(rect, my_order, 0)]

        assert game.handle_order_sidebar_click(rect.center) is True
        assert gs.movement_orders == [ai_order]

    def test_x_button_of_vanished_order_does_nothing(self, game):
        import pygame
        gs = game.game_state
        ai_order = _order(1, "A", "B")
        gs.movement_orders = [ai_order]
        gs.sidebar_expanded = True
        game.sidebar_tab_buttons = {}
        rect = pygame.Rect(10, 10, 20, 20)
        game.order_cancel_buttons = [(rect, _order(0, "X", "Y"), 0)]  # no longer in the list

        game.handle_order_sidebar_click(rect.center)
        assert gs.movement_orders == [ai_order]

    def test_cancel_all_button_cancels_only_sidebar_players_orders(self, game):
        import pygame
        gs = game.game_state
        ai_order, my_order = _order(1, "A", "B"), _order(0, "C", "D")
        gs.movement_orders = [ai_order, my_order]
        gs.sidebar_expanded = True
        game.sidebar_tab_buttons = {}
        game.order_cancel_buttons = []
        game.order_sidebar_player = 0
        game.cancel_all_button = pygame.Rect(10, 100, 50, 20)

        game.handle_order_sidebar_click(game.cancel_all_button.center)
        assert gs.movement_orders == [ai_order]

    def test_cancel_all_hidden_during_ai_turn(self, game):
        """
        Sequential: the AI places its orders one by one (with pauses) during its turn.
        The button used to be drawn whenever ANY order existed, so CANCEL ALL showed up
        on the human's sidebar during the AI's turn. It now follows the sidebar player.
        """
        from game_state import MovementOrder
        gs = game.game_state
        gs.sidebar_expanded = True
        gs.active_sidebar_tab = 'action_queue'
        gs.current_player = 1  # AI's turn
        gs.movement_orders = [MovementOrder('Lobardia', 'Lentria', 3, 1, [0, 1, 2])]

        game.draw_order_sidebar()
        assert game.cancel_all_button is None
        assert game.order_cancel_buttons == []

        # Sanity: the human's own order still gets both buttons on their turn
        gs.current_player = 0
        gs.movement_orders = [MovementOrder('Lobardia', 'Lentria', 1, 0, [0])]
        game.draw_order_sidebar()
        assert game.cancel_all_button is not None
        assert len(game.order_cancel_buttons) == 1

    def test_remote_cancel_uses_per_player_index(self, game):
        gs = game.game_state
        ai_order, remote_order = _order(0, "A", "B"), _order(1, "C", "D")
        gs.movement_orders = [ai_order, remote_order]
        game._handle_remote_order_remove({'player_order_index': 0, 'player_index': 1})
        assert gs.movement_orders == [ai_order]

    def test_remote_cancel_all_keeps_receivers_orders(self, game):
        gs = game.game_state
        mine, remote = _order(0, "A", "B"), _order(1, "C", "D")
        gs.movement_orders = [mine, remote]
        game._handle_remote_order_remove({'cancel_all': True, 'player_index': 1})
        assert gs.movement_orders == [mine]


# ===========================================================================
# Bug 4 - the train_hero mission gate must not swallow other clicks
# ===========================================================================

class TestTrainHeroGateScope:

    def _setup(self, game):
        import pygame
        import main
        MAP_HEIGHT = main.MAP_HEIGHT
        game.tutorial_mission = SimpleNamespace(
            active=True,
            is_action_allowed=lambda action, **kw: action != 'train_hero',
        )
        game.selected_keep = (FROM, 0)
        y = MAP_HEIGHT + 40
        game.hero_train_buttons = {'Seledra': pygame.Rect(10, y, 30, 30)}
        game.demolish_keep_button = pygame.Rect(300, y, 60, 30)
        game.demolish_keep_territory = FROM
        game.demolish_keep_plot_index = 0
        game.end_turn_button = None
        return game

    def test_demolish_keep_still_works_when_hero_training_blocked(self, game):
        self._setup(game)
        with mock.patch.object(game, 'is_local_player_active', return_value=True), \
                mock.patch.object(game.game_state, 'destroy_building', return_value=True) as destroy:
            assert game.handle_bottom_ui_click(game.demolish_keep_button.center) is True
        destroy.assert_called_once_with(FROM, 0)

    def test_hero_button_is_still_blocked(self, game):
        self._setup(game)
        with mock.patch.object(game, 'is_local_player_active', return_value=True), \
                mock.patch.object(game.game_state, 'start_hero_training') as train:
            assert game.handle_bottom_ui_click(game.hero_train_buttons['Seledra'].center) is True
        train.assert_not_called()
