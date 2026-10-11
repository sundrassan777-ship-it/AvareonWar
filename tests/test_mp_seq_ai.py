# -*- coding: utf-8 -*-
"""
Computer players and AI takeover in sequential multiplayer (multiplayer audit, Phase 6).

The host owns every computer player's turn: only the host runs the AI (every PC used to
run its own copy with its own dice, C1), and the AI's moves, battles and turn end reach
the other PCs exactly like a human turn owner's - EXECUTE_ORDERS / BATTLE_RESOLVE /
TURN_END with state snapshots. The AI plays on a worker thread, so those messages are
queued and sent by the main loop, in order. A player who leaves during their own turn has
it finished by the AI on the host, and a win against such an empire does not count for XP
when its player left at once.

Real Game objects joined by tests/mp_harness.py.
"""

import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from network.state_snapshot import build_snapshot  # noqa: E402
from network_config import MessageType  # noqa: E402


@pytest.fixture
def instant_ai(monkeypatch):
    """The AI's human-readability pauses take no time."""
    from ai_player import AIPlayer
    monkeypatch.setattr(AIPlayer, '_pace', lambda self, game_state, seconds: None)


def state(gs):
    return json.loads(json.dumps(build_snapshot(gs)))


def assert_all_identical(session):
    reference = state(session.gs(0))
    for index in session.peers:
        assert state(session.gs(index)) == reference, f"peer {index} differs from the host"


def on_worker_thread(fn):
    """Run fn on another thread - where the AI plays its turn - and wait for it."""
    result = []
    worker = threading.Thread(target=lambda: result.append(fn()))
    worker.start()
    worker.join(10)
    return result[0] if result else None


def step_until_turn_of(session, player, timeout=60.0):
    """Step every peer (letting the host's AI thread run) until it is `player`'s turn
    everywhere and nothing is left in flight."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.step_all()
        time.sleep(0.002)                                    # the AI's worker thread
        host = session.game(0)
        if (all(session.gs(i).current_player == player for i in session.peers)
                and not host._ai_turn_running()):
            session.run_until_quiet()
            return
    raise AssertionError(f"never became player {player}'s turn")


def sent_types(session):
    return [entry[2] for entry in session.net.log if entry[0] == 's2c']


class TestHostRunsTheAi:

    def test_only_the_host_runs_the_ai(self, make_session, instant_ai, monkeypatch):
        """3 players: host, client, AI. The client never starts an AI turn; the AI's turn
        reaches it and every PC ends identical."""
        session = make_session(num_players=3, ai_slots=(2,))
        client = session.game(1)
        client_ai_turns = []
        monkeypatch.setattr(client, 'handle_ai_turn', lambda: client_ai_turns.append(1))
        h.set_turn(session, 2)
        step_until_turn_of(session, 0)
        assert client_ai_turns == []
        assert 2 in session.game(0).ai_players
        assert session.game(1).ai_players == {}
        assert_all_identical(session)

    def test_ai_moves_reach_every_pc(self, make_session):
        """The AI ends its turn on its worker thread with a planned move: EXECUTE_ORDERS is
        queued there and sent by the main loop; the client replays the move."""
        session = make_session(num_players=3, ai_slots=(2,))
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 2, h.units('Swordsman', 'Archer')), h.place(gs, b, 2)))
        h.set_turn(session, 2)
        host = session.game(0)
        assert host.game_state.add_movement_order_for_units(a, b, [0, 1])
        on_worker_thread(host.game_state.next_player)        # what the AI does
        assert host._outgoing_from_threads                   # queued, not sent from there
        assert MessageType.EXECUTE_ORDERS not in sent_types(session)
        session.run_until_quiet()
        assert MessageType.EXECUTE_ORDERS in sent_types(session)
        assert h.garrison_summary(session.gs(1), b) == {2: ['Archer', 'Swordsman']}
        assert session.gs(1).current_player == 0             # the host ended the AI's turn
        assert_all_identical(session)

    def test_ai_battles_reach_every_pc(self, make_session):
        """The AI resolves its battle on its worker thread: seeded, queued, replayed."""
        session = make_session(num_players=3, ai_slots=(2,))
        _, b, _ = h.adjacent_triple()

        def arrange(gs):
            h.place(gs, b, 1, h.units('Archer'))
            gs.territory_garrisons[b][2] = {'unmoved': 0, 'moved': 3,
                                            'units': h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')}
            gs.pending_battles = [h.battle_at(b, owner=1, attacker=2)]
            gs.turn_phase = 'battles'
        h.set_turn(session, 2)
        session.on_all(arrange)
        host = session.game(0)
        assert on_worker_thread(lambda: host.game_state.resolve_battle_shared(0)) is True
        on_worker_thread(host.game_state._advance_to_next_player)   # the AI ends the turn
        session.run_until_quiet()
        types = sent_types(session)
        assert types.index(MessageType.BATTLE_RESOLVE) < types.index(MessageType.TURN_END)
        assert session.gs(1).pending_battles == []
        assert session.gs(1).territory_owners[b] == session.gs(0).territory_owners[b]
        assert_all_identical(session)


class TestThreadSends:

    def test_messages_from_another_thread_keep_their_order(self, make_session):
        session = make_session(num_players=2)
        host = session.game(0)

        def chat(text):
            host._send_action_to_remote(MessageType.CHAT_MESSAGE,
                                        {'player_index': 0, 'message': text, 'channel': 'all'})
        on_worker_thread(lambda: chat("first"))              # queued for the main loop
        assert list(host._outgoing_from_threads)
        chat("second")                                       # main thread: "first" goes first
        assert not host._outgoing_from_threads
        session.run_until_quiet()
        received = [entry[2] for entry in session.gs(1).get_visible_chat_messages(1)]
        assert received.index("first") < received.index("second")

    def test_snapshots_are_summarised_in_the_log(self):
        from main import Game
        from sync_logger import _sanitize_data
        data = {'player_index': 1, 'snapshot': {'territory_owners': {'A': 1}}}
        assert Game._payload_for_log(data) == {'player_index': 1, 'snapshot': '<state snapshot>'}
        assert _sanitize_data(data)['snapshot'] == '<state snapshot>'


class TestTakeover:
    """A player leaves during their own turn: the host's AI finishes it."""

    def _leave(self, session, index=1):
        session.net.server.set_game_started(True)
        session.net.server._disconnect_client(index, "crashed")

    def test_while_planning(self, make_session, instant_ai):
        session = make_session(num_players=2)
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman')), h.place(gs, b, 1)))
        h.set_turn(session, 1)
        client, host = session.game(1), session.game(0)
        assert client.game_state.add_movement_order_for_units(a, b, [0])
        client._send_action_to_remote(MessageType.MOVEMENT_ORDER, {
            'from_territory': a, 'to_territory': b, 'unit_ids': [0], 'player_index': 1})
        session.run_until_quiet()                            # the host has their move
        self._leave(session)
        deadline = time.monotonic() + 60
        while host.game_state.current_player != 0 and time.monotonic() < deadline:
            session.peers[0].step()
            time.sleep(0.002)
        gs = host.game_state
        assert gs.current_player == 0                        # their turn ended
        assert gs.player_is_ai[1] and gs.player_ai_difficulty[1] == 1
        assert 1 in host.ai_players
        assert 1 in gs.ai_takeover_xp

    def test_after_their_moves_ran(self, make_session):
        """Their moves ran on the host; they left before their TURN_END."""
        session = make_session(num_players=2)
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman')), h.place(gs, b, 1)))
        h.set_turn(session, 1)
        client, host = session.game(1), session.game(0)
        assert client.game_state.add_movement_order_for_units(a, b, [0])
        h.click_end_turn(client)
        session.flush()
        for _ in range(10):                                  # the host replays their moves
            session.peers[0].step()
        assert host.game_state.turn_phase == 'execution' and host.game_state.current_player == 1
        self._leave(session)
        session.peers[0].step()
        assert host.game_state.current_player == 0
        assert h.garrison_summary(host.game_state, b) == {1: ['Swordsman']}

    def test_during_their_battles(self, make_session):
        """3 players: client 1 attacks the host and leaves before fighting; the host fights
        the battle and client 2 ends up with the same game."""
        session = make_session(num_players=3)
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Cavalry', 'Cavalry', 'Cavalry')),
                                   h.place(gs, b, 0, h.units('Archer'))))
        h.set_turn(session, 1)
        attacker = session.game(1)
        assert attacker.game_state.add_movement_order_for_units(a, b, [0, 1, 2])
        h.click_end_turn(attacker)
        session.step_until(lambda: session.gs(0).pending_battles and session.gs(2).pending_battles)
        session.peers.pop(1)                                 # their PC is gone
        self._leave(session)
        session.run_until_quiet()
        for index in (0, 2):
            assert session.gs(index).pending_battles == []
            assert session.gs(index).current_player == 2
        assert state(session.gs(2)) == state(session.gs(0))


class TestWinFarming:

    def _game(self, takeover_xp, disconnect_eliminations=(), num_players=2):
        return SimpleNamespace(
            num_players=num_players, player_teams=list(range(num_players)),
            disconnect_eliminations=set(disconnect_eliminations),
            ai_takeover_xp=dict(takeover_xp),
            player_stats={p: {'xp_earned': 500} for p in range(num_players)})

    def test_beating_an_empire_whose_player_left_at_once_does_not_count(self):
        from player_level import player_level_manager
        assert player_level_manager._is_disconnect_farming(self._game({1: 10}), 0) is True

    def test_it_counts_if_they_had_played_properly(self):
        from player_level import player_level_manager
        assert player_level_manager._is_disconnect_farming(self._game({1: 60}), 0) is False

    def test_it_counts_if_another_enemy_was_beaten_normally(self):
        from player_level import player_level_manager
        game = self._game({1: 10}, num_players=3)
        assert player_level_manager._is_disconnect_farming(game, 0) is False
