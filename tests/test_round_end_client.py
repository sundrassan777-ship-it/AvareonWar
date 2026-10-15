# -*- coding: utf-8 -*-
"""
A simultaneous client's round end - found in the FFA test game of 2026-10-14.

1. In a round without battles the host ends the round ~0.5 s after SIM_ALL_READY. When
   both messages reached a client together, the client applied SIM_ROUND_COMPLETE while
   its own armies were still marching and skipped the round's arrivals: Blue lost Daomea
   and Ahtep undefended and got no Battle Report (those reports are made on each PC when
   the armies arrive), and its Action Log said Blue's Keep in Ahtep was finished - a Keep
   the host had cancelled. SIM_ROUND_COMPLETE now waits like TURN_END does.
2. Only the host runs the round end, and the Action Log is not part of its state: clients
   never saw "X trained in Y", "... is ready!" or "... no longer silenced" for their own
   empire. The host now sends its round-end lines, which replace the client's copy.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from network.state_snapshot import build_snapshot  # noqa: E402


def _end_round_with_the_client_asleep(session):
    """Both players press End Turn; the host plays the whole round while the client
    does not run a frame - the host's SIM_ALL_READY and SIM_ROUND_COMPLETE then reach
    the client in one batch, as they did in the test game."""
    client, host = session.game(1), session.game(0)
    h.click_end_turn(client)
    session.step_all()
    h.click_end_turn(host)
    for _ in range(400):
        session.net.flush()
        session.peers[0].step()
        if host.sim_state.round_number == 2:
            break
    assert host.sim_state.round_number == 2
    session.net.flush()
    session.peers[1].step()          # both messages in one frame
    session.run_until_quiet()


class TestRoundEndRace:

    def _lose_an_undefended_territory(self, make_session):
        """Blue's round 10: the host's army walks into the client's empty territory, where
        the client's Keep had one turn of building left."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        a, b, _c = h.adjacent_triple()

        def arrange(gs):
            h.place(gs, a, 1, buildings={})
            gs.under_construction[a] = {0: ('Keep', 1, 85)}
            h.place(gs, b, 0, h.units('Archer'))
        session.on_all(arrange)
        assert session.game(0).game_state.add_movement_order_for_units(b, a, [0])
        _end_round_with_the_client_asleep(session)
        return session, a

    def test_the_client_gets_its_battle_report(self, make_session):
        session, lost = self._lose_an_undefended_territory(make_session)
        client = session.game(1)
        reports = [r for r in client.game_state.battle_report_inbox if r['territory'] == lost]
        assert len(reports) == 1 and reports[0]['defender'] == 1 and not reports[0]['held']
        assert client.game_state.territory_owners[lost] == 0

    def test_no_line_about_the_cancelled_keep(self, make_session):
        session, lost = self._lose_an_undefended_territory(make_session)
        for game in (session.game(0), session.game(1)):
            assert not any(f"Keep completed in {lost}" in line for line in game.game_state.messages)
            assert lost not in game.game_state.buildings or game.game_state.buildings[lost].get(0) != 'Keep'


class TestRoundNews:

    def _train_one(self, make_session):
        """The client trains a Swordsman, which is ready at the end of round 1."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        capital = h.spread_territories(2)[1]
        session.on_all(lambda gs: gs.buildings.setdefault(capital, {}).update({0: 'Barracks'}))
        client = session.game(1)
        assert client._try_start_training(capital, 0, 'Swordsman')
        for index in (1, 0):
            h.click_end_turn(session.game(index))
            session.step_all()
        session.step_until(lambda: session.game(0).sim_state.round_number == 2, max_steps=400)
        session.run_until_quiet()
        return session, capital

    def test_the_client_sees_its_own_trained_unit(self, make_session):
        session, capital = self._train_one(make_session)
        lines = session.game(1).game_state.messages
        marker = lines.index("--- Round 2 ---")
        assert f"Player 2: Swordsman trained in {capital}" in lines[marker + 1:]
        assert lines.count("--- Round 2 ---") == 1

    def test_each_round_end_line_once_as_on_the_host(self, make_session):
        session, _capital = self._train_one(make_session)
        client_lines = session.game(1).game_state.messages
        host_lines = session.game(0).game_state.messages
        income = [line for line in client_lines if line.startswith("Player 2 earned")]
        assert income == [line for line in host_lines if line.startswith("Player 2 earned")]
        assert len(income) == 1

    def test_an_older_host_without_the_lines_changes_nothing(self, make_session):
        """No round_end_messages field: the client keeps its own bookkeeping lines."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        client, host = session.game(1), session.game(0)
        before = len(client.game_state.messages)
        client._sim_apply_round_complete({
            'round_number': 2, 'snapshot': build_snapshot(host.game_state),
            'eliminated_players': [], 'overflow_territories': {}})
        new_lines = client.game_state.messages[before:]
        assert any(line.startswith("Player 2 earned") for line in new_lines)
        assert "--- Round 2 ---" in new_lines
