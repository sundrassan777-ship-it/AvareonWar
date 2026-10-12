# -*- coding: utf-8 -*-
"""
Sequential-mode multiplayer flow (multiplayer audit, Phase 5).

The turn owner's PC is the truth for its turn: EXECUTE_ORDERS carries its state snapshot
(planned moves included) and every other PC replays the same moves; TURN_END carries its
state after the turn advanced, and the others apply it instead of advancing on their own.
Only the owner's planning timer ends a turn, the owner's battles can never stall the game
(AFK rules), and a game that ends in the owner's turn sends its final state.

Real Game objects joined by tests/mp_harness.py (Peer.step runs the same
Game._update_sequential_turn the real loop runs).
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from network.state_snapshot import build_snapshot  # noqa: E402
from network_config import MessageType  # noqa: E402


def state(gs):
    """A peer's whole game state for cross-peer comparison (JSON round trip like the
    wire). Sequential mode: current_player is the same on every PC."""
    return json.loads(json.dumps(build_snapshot(gs)))


def assert_all_identical(session):
    reference = state(session.gs(0))
    for index in session.peers:
        assert state(session.gs(index)) == reference, f"peer {index} differs from the host"


def sent(session, direction, msg_type):
    """Frames of one type in the harness log ('c2s' client -> server, 's2c' server -> client)."""
    return [entry for entry in session.net.log if entry[0] == direction and entry[2] == msg_type]


def client_attack(session, attacker=1, defender=0):
    """`attacker` (a client) is about to attack `defender`'s territory B from A."""
    a, b, _ = h.adjacent_triple()
    session.on_all(lambda gs: (h.place(gs, a, attacker, h.units('Cavalry', 'Cavalry', 'Cavalry')),
                               h.place(gs, b, defender, h.units('Archer'))))
    h.set_turn(session, attacker)
    game = session.game(attacker)
    assert game.game_state.add_movement_order_for_units(a, b, [0, 1, 2])
    return game, a, b


def client_move(session):
    """Client 1 moves a Swordsman between two of its own territories (no battle)."""
    a, b, _ = h.adjacent_triple()
    session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman')), h.place(gs, b, 1)))
    h.set_turn(session, 1)
    client = session.game(1)
    assert client.game_state.add_movement_order_for_units(a, b, [0])
    return client, a, b


class TestTurnOwnerIsTheTruth:

    def test_a_client_turn_reaches_every_pc(self, make_session):
        """3 players: client 1 builds and moves; host and client 2 end up identical."""
        session = make_session(num_players=3)
        capital = h.spread_territories(3)[1]
        client, a, b = client_move(session)
        assert client._try_start_construction(capital, 0, 'Farm')
        h.click_end_turn(client)
        session.run_until_quiet()
        assert_all_identical(session)
        assert session.gs(0).current_player == 2
        assert h.garrison_summary(session.gs(2), b) == {1: ['Swordsman']}

    def test_four_players_play_a_full_round(self, make_session):
        """Host + 3 clients end their turns in order; identical after every turn."""
        session = make_session(num_players=4)
        start_turn = session.gs(0).turn_number
        for player in range(4):
            assert session.gs(player).current_player == player
            h.click_end_turn(session.game(player))
            session.run_until_quiet()
            assert_all_identical(session)
        assert [session.gs(i).current_player for i in range(4)] == [0, 0, 0, 0]
        assert session.gs(3).turn_number == start_turn + 1

    def test_only_the_turn_owner_sends_turn_end(self, make_session):
        session = make_session(num_players=3)
        h.click_end_turn(session.game(0))
        session.run_until_quiet()
        assert len(sent(session, 's2c', MessageType.TURN_END)) == 2    # host -> each client
        assert sent(session, 'c2s', MessageType.TURN_END) == []
        assert [session.gs(i).current_player for i in (0, 1, 2)] == [1, 1, 1]

    def test_receivers_never_advance_on_their_own(self, make_session):
        """The host replays the client's move to the end and still waits for TURN_END
        (it used to advance from its own replay)."""
        session = make_session(num_players=2)
        client, _, b = client_move(session)
        host = session.game(0)
        h.click_end_turn(client)
        session.flush()
        for _ in range(10):                                  # the host alone, 1 s
            session.peers[0].step()
        assert not host.game_state.active_animations
        assert host.game_state.current_player == 1
        assert host.game_state.turn_phase == 'execution'
        session.run_until_quiet()
        assert host.game_state.current_player == client.game_state.current_player == 0
        assert_all_identical(session)

    def test_turn_end_waits_for_our_replay_of_the_moves(self, make_session):
        session = make_session(num_players=2)
        client, _, b = client_move(session)
        host = session.game(0)
        h.click_end_turn(client)
        session.flush()
        session.peers[0].step()                              # host replay under way
        for _ in range(6):                                   # the client finishes first
            session.peers[1].step()
        assert client.game_state.current_player == 0         # ...and sent TURN_END
        session.flush()
        session.peers[0].step()
        assert host.game_state.active_animations             # replay not cut short
        assert host._held_network_messages
        session.run_until_quiet()
        assert h.garrison_summary(host.game_state, b) == {1: ['Swordsman']}
        assert_all_identical(session)

    def test_a_desync_is_reported_and_corrected_when_the_moves_begin(self, make_session):
        session = make_session(num_players=2)
        client, _, _ = client_move(session)
        host = session.game(0)
        host.game_state.player_gold[1] += 77                 # the host's copy drifted
        recorded = []

        class FakeSyncLogger:
            def record_action(self, *args, **kwargs):
                pass

            def record_turn_snapshot(self, turn_number):
                pass

            def record_desync(self, turn_number, diff):
                recorded.append(diff)
        host.game_state.sync_logger = FakeSyncLogger()
        h.click_end_turn(client)
        session.run_until_quiet()
        assert recorded and any(key.startswith('player_gold') for key in recorded[0])
        assert session.gs(0).player_gold == session.gs(1).player_gold


class TestTurnStart:

    def test_messages_wait_for_our_turn_start_effects(self, make_session):
        """The owner built right after its own announcement; ours was still running. The
        building arrives after our turn-start effects (it used to lose a turn here)."""
        session = make_session(num_players=2)
        capital = h.spread_territories(2)[1]
        h.set_turn(session, 1)
        client, host = session.game(1), session.game(0)
        host.game_state.turn_announcement_active = True     # ours is still running
        assert client._try_start_construction(capital, 0, 'Farm')
        session.flush()
        session.peers[0].step()
        assert capital not in host.game_state.under_construction
        assert host._held_network_messages
        session.run_until_quiet()
        assert (host.game_state.under_construction[capital][0]
                == client.game_state.under_construction[capital][0])

    def test_a_new_turn_is_not_cut_short_by_the_previous_clock(self, make_session):
        session = make_session(num_players=2)
        client = session.game(1)
        client.game_state.planning_phase_start_time = time.time() - 10_000   # stale clock
        h.click_end_turn(session.game(0))                    # the client's turn starts
        session.run_until_quiet()
        assert client.game_state.current_player == session.gs(0).current_player == 1
        assert client.game_state.turn_phase == 'planning'


class TestPlanningTimer:

    def test_only_the_owners_timer_ends_the_turn(self, make_session):
        """Every PC's clock runs out. Only the client's ends the turn - with its planned
        move, on every PC (each PC used to end the turn on its own clock, C2)."""
        session = make_session(num_players=2)
        client, _, b = client_move(session)
        host_gs = session.gs(0)
        own_advances = []
        advance = host_gs._advance_to_next_player
        host_gs._advance_to_next_player = lambda: (own_advances.append(host_gs.current_player), advance())
        session.on_all(lambda gs: setattr(gs, 'planning_phase_start_time', time.time() - 10_000))
        session.run_until_quiet()
        assert own_advances == []                            # the host never ended it
        assert sent(session, 'c2s', MessageType.EXECUTE_ORDERS)   # the move went out
        for index in (0, 1):
            assert session.gs(index).current_player == 0
            assert h.garrison_summary(session.gs(index), b) == {1: ['Swordsman']}
        assert_all_identical(session)


class TestBattles:

    def test_three_players_stay_identical_through_a_battle(self, make_session):
        """Client 1 attacks client 2; the host and the defender replay it."""
        session = make_session(num_players=3)
        attacker, _, b = client_attack(session, attacker=1, defender=2)
        h.click_end_turn(attacker)
        session.step_until(lambda: any(bt.territory == b for bt in attacker.game_state.pending_battles))
        h.open_battle(attacker, b)
        h.fight(attacker)
        h.close_battle(attacker)
        session.run_until_quiet()
        assert_all_identical(session)
        assert session.gs(2).current_player == 2
        h.click_end_turn(session.game(2))
        session.run_until_quiet()
        assert_all_identical(session)
        assert session.gs(1).current_player == 0


class TestAfk:

    def test_untouched_battles_are_resolved(self, make_session, monkeypatch):
        from main import Game
        monkeypatch.setattr(Game, 'SEQ_AFK_RESOLVE_SECONDS', 0.0)
        session = make_session(num_players=2)
        client, _, _ = client_attack(session)
        h.click_end_turn(client)
        session.run_until_quiet()
        for index in (0, 1):
            assert session.gs(index).pending_battles == []
            assert session.gs(index).current_player == 0
        assert_all_identical(session)

    def test_a_battle_report_left_open_is_closed(self, make_session, monkeypatch):
        from main import Game
        session = make_session(num_players=2)
        client, _, b = client_attack(session)
        h.click_end_turn(client)
        session.step_until(lambda: any(bt.territory == b for bt in client.game_state.pending_battles))
        h.open_battle(client, b)
        h.fight(client)                                      # ...and walks away
        # (patched only now: at 0 s the untouched battle itself would resolve at once)
        monkeypatch.setattr(Game, 'SEQ_AFK_RESOLVE_SECONDS', 0.0)
        session.run_until_quiet()
        assert client.enhanced_battle_ui is None
        assert session.gs(0).current_player == client.game_state.current_player == 0
        assert_all_identical(session)

    def test_battles_are_settled_under_an_abandoned_window(self, make_session, monkeypatch):
        from main import Game
        session = make_session(num_players=2)
        client, _, b = client_attack(session)
        h.click_end_turn(client)
        session.step_until(lambda: any(bt.territory == b for bt in client.game_state.pending_battles))
        h.open_battle(client, b)                             # ...and walks away before FIGHT
        monkeypatch.setattr(Game, 'SEQ_BATTLE_FALLBACK_SECONDS', 0.0)
        session.run_until_quiet()
        assert client.enhanced_battle_ui is None             # nothing left to fight in it
        assert session.gs(0).current_player == client.game_state.current_player == 0
        assert_all_identical(session)


class TestGameEnd:

    def test_final_state_is_sent_when_the_game_ends_in_our_turn(self, make_session):
        session = make_session(num_players=2)
        a, b, _ = h.adjacent_triple()
        _, client_capital = h.spread_territories(2)

        def arrange(gs):
            h.place(gs, client_capital, 0)                   # the client keeps only B
            h.place(gs, a, 0, h.units('Cavalry', 'Cavalry'))
            h.place(gs, b, 1)                                # undefended
        session.on_all(arrange)
        host = session.game(0)
        assert host.game_state.add_movement_order_for_units(a, b, [0, 1])
        h.click_end_turn(host)
        session.run_until_quiet()
        for index in (0, 1):
            assert session.gs(index).phase == 'ended'
            assert session.gs(index).winner == 0
        assert sent(session, 's2c', MessageType.TURN_END)   # the final state went out
        assert_all_identical(session)
