# -*- coding: utf-8 -*-
"""
Small fixes from the FFA test game of 2026-10-14 (simultaneous, 3 PCs):

- Cancelling a planned move (the sidebar's Cancel Order / CANCEL ALL) sent ORDER_REMOVE
  to the other PCs. Simultaneous planned moves stay on the planning PC until Ready, so
  nobody else holds one: all 16 deliveries failed ("cancel order failed"). No longer sent
  in simultaneous mode; sequential mode is unchanged.
- Clicking the crossed swords of a battle another player resolves did nothing visible and
  logged an ERROR (Blue clicked 13 times in 6 s). Now a notice says who resolves it.
- Two checks that run every frame logged the same line every frame: the territory
  tooltip's unit-count check (125 lines on one PC) and "Timer expired for remote player"
  (648 lines over the 3 PCs). Each is now logged once.
"""

import logging
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame  # noqa: E402
import pytest  # noqa: E402

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from config.action_error_messages import format_action_error  # noqa: E402
from game_state import GameState  # noqa: E402
from network_config import MessageType  # noqa: E402
from simultaneous import SimultaneousGameState  # noqa: E402
import simultaneous.sim_state as sim_state_module  # noqa: E402


# ============================================================================
# NO ORDER_REMOVE FOR SIMULTANEOUS PLANNED MOVES
# ============================================================================

def _planned_move(session, player):
    """`player` plans a move of one unit on their own PC; returns (game, order)."""
    a, b, _c = h.adjacent_triple()
    session.on_all(lambda gs: (h.place(gs, a, player, h.units('Swordsman', 'Swordsman')),
                               h.place(gs, b, player)))
    game = session.game(player)
    gs = game.game_state
    gs.current_player = player
    assert gs.add_movement_order_for_units(a, b, [0], player=player)
    gs.sidebar_expanded = True
    gs.active_sidebar_tab = 'action_queue'
    game.sidebar_tab_buttons = {}
    return game, gs.movement_orders[-1]


def _click_cancel(game, order):
    rect = pygame.Rect(10, 10, 20, 20)
    game.order_cancel_buttons = [(rect, order, 0)]
    game.cancel_all_button = None
    assert game.handle_order_sidebar_click(rect.center) is True


def _click_cancel_all(game, player):
    game.order_cancel_buttons = []
    game.order_sidebar_player = player
    game.cancel_all_button = pygame.Rect(10, 100, 50, 20)
    assert game.handle_order_sidebar_click(game.cancel_all_button.center) is True


def _order_removes_sent(session, player):
    return [entry for entry in session.net.log
            if entry[0] == 'c2s' and entry[1] == player and entry[2] == MessageType.ORDER_REMOVE]


class TestNoCancelMessagesInSimultaneous:

    def test_cancelling_a_planned_move_sends_nothing(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        client, order = _planned_move(session, 1)
        _click_cancel(client, order)
        session.run_until_quiet()
        assert client.game_state.movement_orders == []          # cancelled here
        assert _order_removes_sent(session, 1) == []

    def test_cancel_all_sends_nothing(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        client, _order = _planned_move(session, 1)
        _click_cancel_all(client, 1)
        session.run_until_quiet()
        assert client.game_state.movement_orders == []
        assert _order_removes_sent(session, 1) == []

    def test_a_cancelled_move_is_not_submitted_at_ready(self, make_session):
        """The cancel still works where it matters: the move never reaches the host."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        client, order = _planned_move(session, 1)
        _click_cancel(client, order)
        h.click_end_turn(client)
        session.step_all()
        session.run_until_quiet()
        host_orders = session.game(0).sim_state.player_orders.get(1, [])
        assert [o for o in host_orders if o.get('type') == 'movement'] == []

    def test_sequential_cancels_are_still_sent(self, make_session):
        """Sequential mode is left as it was."""
        session = make_session(num_players=2, turn_mode='sequential')
        h.set_turn(session, 1)
        client, order = _planned_move(session, 1)
        _click_cancel(client, order)
        session.run_until_quiet()
        assert len(_order_removes_sent(session, 1)) == 1


# ============================================================================
# A BATTLE ANOTHER PLAYER RESOLVES
# ============================================================================

@pytest.fixture(scope="module")
def pygame_display():
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


def _sim_game_with_battle(resolver):
    """Single-player simultaneous game, resolving phase, one battle resolved by `resolver`."""
    from main import Game
    game = Game()
    game.initialize_game({'num_players': 2, 'player_is_ai': [False, True],
                          'player_ai_difficulty': [1, 1], 'game_mode': 'simultaneous'})
    game.tutorial_mission = None
    gs = game.game_state
    gs.phase = 'playing'
    territory = h.spread_territories(2)[0]
    gs.pending_battles = [h.battle_at(territory, 0, 1, resolver=resolver)]
    game.sim_state.sim_phase = 'resolving'
    game.battle_markers = [pygame.Rect(10, 200, 20, 20)]
    return game


class TestBattleOfAnotherResolver:

    def test_the_click_names_who_resolves_it(self, pygame_display, caplog):
        game = _sim_game_with_battle(resolver=1)
        name = game.game_state.get_player_name(1, include_title=False)
        with mock.patch.object(game, 'show_action_error') as show:
            handled = game.handle_battle_marker_click(game.battle_markers[0].center)
        assert handled is False                             # falls through, as before
        show.assert_called_once_with('battle_other_resolver', player=name)
        assert game.battle_popup_visible is False
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    def test_the_notice_shows_once_however_often_it_is_clicked(self, pygame_display):
        """Blue clicked 13 times in 6 s: one notice, its timer restarted."""
        game = _sim_game_with_battle(resolver=1)
        text = format_action_error('battle_other_resolver',
                                   player=game.game_state.get_player_name(1, include_title=False))
        for _ in range(5):
            game.handle_battle_marker_click(game.battle_markers[0].center)
        shown = [n.get('system_text') for n in game.chat_notification_effect._notifications]
        assert shown.count(text) == 1

    def test_the_resolver_still_opens_it(self, pygame_display):
        game = _sim_game_with_battle(resolver=0)
        with mock.patch.object(game, 'show_action_error') as show:
            assert game.handle_battle_marker_click(game.battle_markers[0].center) is True
        show.assert_not_called()
        assert game.battle_popup_visible is True


# ============================================================================
# LINES LOGGED EVERY FRAME, NOW ONCE
# ============================================================================

class TestLoggedOnce:

    def test_tooltip_count_mismatch_is_warned_once(self, caplog):
        """Green's PC, Duchy of Daurels: 6 units listed, counters at 11 (the counters
        themselves were fixed in Phase 2 - this is about the log)."""
        gs = GameState(num_players=2, skip_setup_phase=True)
        territory = h.spread_territories(2)[0]
        h.place(gs, territory, 1, h.units(*['Swordsman'] * 6))
        gs.territory_garrisons[territory][1]['unmoved'] = 11
        caplog.set_level(logging.WARNING, logger='game_state.military')
        for _ in range(5):
            assert gs.get_unit_composition(territory) == {'Swordsman': 6}
        warnings = [r for r in caplog.records if 'TOOLTIP MISMATCH' in r.getMessage()]
        assert len(warnings) == 1

        # A different mismatch is reported again
        gs.territory_garrisons[territory][1]['unmoved'] = 12
        gs.get_unit_composition(territory)
        warnings = [r for r in caplog.records if 'TOOLTIP MISMATCH' in r.getMessage()]
        assert len(warnings) == 2

    def test_a_longer_unit_list_is_still_cut_to_the_counters(self):
        gs = GameState(num_players=2, skip_setup_phase=True)
        territory = h.spread_territories(2)[0]
        h.place(gs, territory, 1, h.units(*['Swordsman'] * 6))
        gs.territory_garrisons[territory][1]['unmoved'] = 4
        for _ in range(3):
            assert gs.get_unit_composition(territory) == {'Swordsman': 4}

    def test_remote_timer_expiry_is_logged_once_per_round(self, monkeypatch):
        gs = GameState(num_players=2, skip_setup_phase=True)
        sim = SimultaneousGameState(gs)
        sim.is_multiplayer_client = True
        sim.local_player_index = 1
        sim.players_ready[1] = True                  # our own player is done
        lines = []
        monkeypatch.setattr(sim_state_module.sim_log, 'state',
                            lambda message, data=None: lines.append(message))
        sim.player_timers[0] = 0.5
        for _ in range(5):
            sim.update_timers(1.0)
        expired = [line for line in lines if 'Timer expired for remote player 0' in line]
        assert len(expired) == 1
        assert sim.players_ready.get(0, False) is False      # still waits for the network

        sim.round_number += 1                        # next round: logged again, once
        for _ in range(3):
            sim.update_timers(1.0)
        expired = [line for line in lines if 'Timer expired for remote player 0' in line]
        assert len(expired) == 2
