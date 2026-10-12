# -*- coding: utf-8 -*-
"""
Simultaneous-mode multiplayer flow (multiplayer audit, Phase 4).

The host is the single source of truth: it applies every non-movement order, sends
its state snapshot with the validated movement (SIM_ALL_READY) and the new round's
snapshot at round end (SIM_ROUND_COMPLETE). AI battles / choices, round ends and AI
planning run on the host only; clients learn who is ready from SIM_READY_STATE; AFK
players never stall a round; a disconnected player's empire is taken over by the AI.

Real Game objects joined by tests/mp_harness.py (Peer.step runs the same
Game._update_simultaneous the real loop runs).
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from game_state import GameState  # noqa: E402
from network.state_snapshot import build_snapshot  # noqa: E402
from network_config import MessageType  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402
from simultaneous.sim_ai import SimultaneousAI  # noqa: E402


@pytest.fixture
def instant_ai(monkeypatch):
    """AI planning threads skip their 'thinking' pause."""
    monkeypatch.setattr(SimultaneousAI, 'THINKING_DELAY', {0: (0, 0), 1: (0, 0), 2: (0, 0)})


def wait_for_ai(game, timeout=20.0):
    """Let the host's AI planning threads finish (they think in real time)."""
    if game.sim_ai is not None:
        for thread in list(game.sim_ai.ai_planning.values()):
            thread.join(timeout)


def end_turn_all(session):
    """Every human presses End Turn (clients first, then the host)."""
    for index in sorted(session.peers, reverse=True):
        h.click_end_turn(session.game(index))
        session.step_all()


def comparable(gs):
    """A peer's state for cross-peer comparison (JSON round trip like the wire).
    current_player is per PC in simultaneous mode (each PC's own local player)."""
    data = json.loads(json.dumps(build_snapshot(gs)))
    data.pop('current_player')
    return data


def sim_battles(gs, *specs):
    """Pending simultaneous battles (+ matching garrisons), one per
    (territory, owner, attacker, resolver)."""
    gs.pending_battles = []
    for territory, owner, attacker, resolver in specs:
        h.place(gs, territory, owner, h.units('Archer'))
        gs.territory_garrisons[territory][attacker] = {
            'unmoved': 0, 'moved': 3, 'units': h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')}
        gs.pending_battles.append(h.battle_at(territory, owner=owner, attacker=attacker, resolver=resolver))


def sim_battle(gs, territory, owner, attacker, resolver):
    """A pending simultaneous battle at `territory` (+ matching garrisons)."""
    sim_battles(gs, (territory, owner, attacker, resolver))


def enter_resolving(session):
    for peer in session.peers.values():
        peer.game.sim_state.sim_phase = 'resolving'


class TestHostIsTheTruth:

    def test_a_build_the_host_refused_is_undone_on_the_client(self, make_session):
        """The client could afford a Farm on its own screen, the host's state says no."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        capital = h.spread_territories(2)[1]
        client, host = session.game(1), session.game(0)
        host.game_state.player_gold[1] = 0                 # the host's (authoritative) view
        assert client._try_start_construction(capital, 0, 'Farm')
        assert client.game_state.under_construction.get(capital)
        end_turn_all(session)
        session.run_until_quiet()
        assert not client.game_state.under_construction.get(capital)
        assert comparable(client.game_state) == comparable(host.game_state)
        assert client.game_state.current_player == 1

    def test_three_player_round_with_an_ai_ends_identical_everywhere(self, make_session, instant_ai):
        session = make_session(num_players=3, ai_slots=(2,), turn_mode='simultaneous')
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman', 'Archer', 'Pikeman')),
                                   h.place(gs, b, 1)))
        client = session.game(1)
        assert client.game_state.add_movement_order_for_units(a, b, [0, 1])
        end_turn_all(session)
        wait_for_ai(session.game(0))
        session.step_until(lambda: session.gs(0).turn_number == 2, max_steps=400)
        session.run_until_quiet()
        assert client.sim_state.round_number == session.game(0).sim_state.round_number == 2
        assert comparable(client.game_state) == comparable(session.gs(0))
        # Each PC still acts for its own player
        assert client.game_state.current_player == 1 and session.gs(0).current_player == 0

    def test_four_player_rounds_end_identical_everywhere(self, make_session, instant_ai):
        """Host + two clients + an AI play two rounds; every PC holds the same game."""
        session = make_session(num_players=4, ai_slots=(3,), turn_mode='simultaneous')
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 2, h.units('Cavalry', 'Cavalry')),
                                   h.place(gs, b, 2)))
        assert session.game(2).game_state.add_movement_order_for_units(a, b, [0])
        for round_number in (2, 3):
            end_turn_all(session)
            wait_for_ai(session.game(0))
            session.step_until(lambda: session.gs(0).turn_number == round_number, max_steps=400)
            session.run_until_quiet()
            host_state = comparable(session.gs(0))
            for index in (1, 2):
                assert session.game(index).sim_state.round_number == round_number
                assert comparable(session.gs(index)) == host_state
                assert session.gs(index).current_player == index

    def test_round_end_clears_what_the_client_still_showed(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        client = session.game(1)
        sim_battle(client.game_state, b, owner=0, attacker=1, resolver=1)   # client only
        client.sim_state.sim_phase = 'resolving'
        h.open_battle(client, b)
        session.game(0)._sim_broadcast_round_complete(2)
        session.run_until_quiet()
        assert client.game_state.pending_battles == []
        assert client.enhanced_battle_ui is None and not client.battle_popup_visible
        assert client.sim_state.sim_phase == 'planning' and client.sim_state.round_number == 2


class TestHostOnlyWork:

    def test_ai_battles_are_resolved_by_the_host_only(self, make_session, monkeypatch):
        session = make_session(num_players=3, ai_slots=(2,), turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: sim_battle(gs, b, owner=1, attacker=2, resolver=2))
        enter_resolving(session)
        client = session.game(1)
        client_resolved = []
        monkeypatch.setattr(client, '_resolve_battle_locally',
                            lambda index: client_resolved.append(index))
        session.step_until(lambda: not client.game_state.pending_battles, max_steps=60)
        assert client_resolved == []                         # replayed the host's result
        assert client.game_state.territory_owners[b] == session.gs(0).territory_owners[b] == 2

    def test_ai_alliance_choices_are_made_by_the_host_only(self, make_session):
        session = make_session(num_players=3, ai_slots=(2,), teams=[0, 1, 1],
                               turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()

        def arrange(gs):
            h.place(gs, b, 1, h.units('Archer'))
            gs.territory_garrisons[b][2] = {'unmoved': 0, 'moved': 1, 'units': h.units('Pikeman', status='moved')}
            gs.pending_battles = []
        session.on_all(arrange)
        enter_resolving(session)
        marker = {'type': 'alliance', 'territory': b, 'players': [1, 2], 'chooser': 2}
        for peer in session.peers.values():
            peer.game.sim_state.phase_manager.pending_alliance_markers = [dict(marker)]
        client = session.game(1)
        client_choices = []
        client._auto_choose_alliance_owner = lambda *a, **k: client_choices.append(a)
        session.step_until(lambda: session.gs(0).turn_number == 2, max_steps=60)
        session.run_until_quiet()
        assert client_choices == []
        assert client.game_state.territory_owners[b] == session.gs(0).territory_owners[b]

    def test_only_the_host_ends_a_round(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        client = session.game(1)
        client.sim_state.complete_round()
        assert client.sim_state.round_number == 1


class TestReadyState:

    def test_clients_see_who_is_ready(self, make_session):
        session = make_session(num_players=3, turn_mode='simultaneous')
        first, second = session.game(1), session.game(2)
        h.click_end_turn(first)
        session.run_until_quiet()
        assert second.sim_state.players_ready[1] is True
        assert second.sim_state.players_ready[0] is False and second.sim_state.players_ready[2] is False
        assert second.sim_state.get_waiting_players() == [0, 2]

    def test_ready_state_of_another_round_is_ignored(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        client = session.game(1)
        client._handle_network_message({'type': MessageType.SIM_READY_STATE,
                                        'data': {'round': 7, 'ready': [0]}})
        assert client.sim_state.players_ready[0] is False

    def test_a_client_timer_only_readies_its_own_player(self, make_session):
        session = make_session(num_players=3, turn_mode='simultaneous')
        client = session.game(1)
        for pid in client.sim_state.player_timers:
            client.sim_state.player_timers[pid] = 0.05
        client._update_sim_planning_timers(0.1)
        ready = client.sim_state.players_ready
        assert ready[1] is True and ready[0] is False and ready[2] is False


class TestAfk:

    def _client_battle(self, session):
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: sim_battle(gs, b, owner=0, attacker=1, resolver=1))
        enter_resolving(session)
        return b

    def test_idle_resolver_gets_their_battles_resolved_on_their_pc(self, make_session, monkeypatch):
        from main import Game
        monkeypatch.setattr(Game, 'SIM_AFK_RESOLVE_SECONDS', 0.0)
        session = make_session(num_players=2, turn_mode='simultaneous')
        b = self._client_battle(session)
        session.run_until_quiet()
        for index in (0, 1):
            assert session.gs(index).pending_battles == []
            assert session.gs(index).territory_owners[b] == 1

    def test_host_settles_an_absent_players_battles(self, make_session, monkeypatch):
        from main import Game
        monkeypatch.setattr(Game, 'SIM_HOST_FALLBACK_SECONDS', 0.0)
        session = make_session(num_players=2, turn_mode='simultaneous')
        b = self._client_battle(session)
        client = session.game(1)
        client_resolved = []
        monkeypatch.setattr(client, '_resolve_battle_locally',
                            lambda index: client_resolved.append(index))
        session.run_until_quiet()
        assert client_resolved == []                         # the host did it
        assert session.gs(0).territory_owners[b] == session.gs(1).territory_owners[b] == 1


class TestRoundEnd:
    """The round ends only when nothing of it is left - and only once."""

    def _two_battles(self, session):
        """b: the host's battle; c: the client's."""
        _, b, c = h.adjacent_triple()
        session.on_all(lambda gs: sim_battles(gs, (b, 1, 0, 0), (c, 0, 1, 1)))
        enter_resolving(session)
        return b, c

    def _client_fights(self, session, territory):
        client = session.game(1)
        h.open_battle(client, territory)
        h.fight(client)
        h.close_battle(client)
        session.run_until_quiet()

    def test_round_waits_for_the_hosts_open_battle_report(self, make_session):
        """The host's own result goes out when its report closes: the round used to end
        under the open report once the other players' battles were done."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        b, c = self._two_battles(session)
        host = session.game(0)
        h.open_battle(host, b)
        h.fight(host)                                        # report open
        self._client_fights(session, c)
        assert host.game_state.pending_battles == []
        assert host.sim_state.round_number == 1 and host.sim_state.sim_phase == 'resolving'
        h.close_battle(host)
        session.run_until_quiet()
        assert session.game(1).sim_state.round_number == host.sim_state.round_number == 2
        assert comparable(session.gs(1)) == comparable(host.game_state)

    def test_alliance_marker_from_the_hosts_report_stays_in_its_round(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        b, c = self._two_battles(session)
        host = session.game(0)
        host._alliance_marker_for = lambda battle, territory: (
            {'type': 'alliance', 'territory': territory, 'players': [0, 1], 'chooser': 0}
            if territory == b else None)
        h.open_battle(host, b)
        h.fight(host)
        self._client_fights(session, c)
        h.close_battle(host)                                 # queues the marker
        session.run_until_quiet()
        pm = host.sim_state.phase_manager
        assert host.sim_state.round_number == 1             # waits for the choice
        assert [m['territory'] for m in pm.pending_alliance_markers] == [b]
        host._auto_choose_alliance_owner(0, "test")
        session.run_until_quiet()
        assert session.game(1).sim_state.round_number == host.sim_state.round_number == 2
        assert pm.pending_alliance_markers == []
        assert comparable(session.gs(1)) == comparable(host.game_state)

    def test_a_late_alliance_choice_does_not_end_the_next_round(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        host = session.game(0)
        assert host.sim_state.sim_phase == 'planning'
        host._handle_network_message({'type': MessageType.SIM_ALLIANCE_CHOICE,
                                      'data': {'territory': b, 'new_owner': 1}})
        assert host.sim_state.round_number == 1 and host.sim_state.sim_phase == 'planning'

    def test_the_alliance_popup_ignores_a_choice_already_made(self, make_session):
        import pygame
        session = make_session(num_players=2, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        host = session.game(0)
        session.on_all(lambda gs: (h.place(gs, b, 0), setattr(gs, 'pending_battles', [])))
        enter_resolving(session)
        marker = {'type': 'alliance', 'territory': b, 'players': [0, 1], 'chooser': 0}
        host.sim_state.phase_manager.pending_alliance_markers = [dict(marker)]
        assert host.handle_alliance_marker_click((0, 0), marker)
        host._auto_choose_alliance_owner(0, "host fallback")     # settled meanwhile
        assert host.sim_state.round_number == 2
        assert not host.alliance_choice_popup_visible
        # A click that still reaches the popup (e.g. the same frame) changes nothing
        host.alliance_choice_popup_visible = True
        host.alliance_choice_popup_rect = pygame.Rect(0, 0, 50, 50)
        host.alliance_choice_buttons = [(pygame.Rect(0, 0, 10, 10), 1)]
        assert host.handle_alliance_choice_click((5, 5))
        assert host.sim_state.round_number == 2 and not host.alliance_choice_popup_visible


class TestAfkWindows:
    """Battle windows left open never hold a round forever."""

    def test_a_battle_report_left_open_is_closed(self, make_session, monkeypatch):
        from main import Game
        monkeypatch.setattr(Game, 'SIM_AFK_RESOLVE_SECONDS', 0.0)
        session = make_session(num_players=2, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: sim_battle(gs, b, owner=0, attacker=1, resolver=1))
        enter_resolving(session)
        client = session.game(1)
        h.open_battle(client, b)
        h.fight(client)                                      # ...and walks away
        session.run_until_quiet()
        assert client.enhanced_battle_ui is None
        assert client.sim_state.round_number == session.game(0).sim_state.round_number == 2
        assert session.gs(0).territory_owners[b] == client.game_state.territory_owners[b]

    def test_host_fallback_settles_the_hosts_own_battle_too(self, make_session, monkeypatch):
        """The host walked away from an open battle window (which counts as busy)."""
        from main import Game
        monkeypatch.setattr(Game, 'SIM_HOST_FALLBACK_SECONDS', 0.0)
        session = make_session(num_players=2, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: sim_battle(gs, b, owner=1, attacker=0, resolver=0))
        enter_resolving(session)
        host = session.game(0)
        h.open_battle(host, b)
        session.run_until_quiet()
        assert host.enhanced_battle_ui is None               # nothing left to fight in it
        assert session.game(1).sim_state.round_number == host.sim_state.round_number == 2
        assert session.gs(1).territory_owners[b] == host.game_state.territory_owners[b]


class TestTakeover:

    def test_ai_plays_the_round_of_a_player_who_left_while_planning(self, make_session, instant_ai):
        session = make_session(num_players=2, turn_mode='simultaneous')
        host = session.game(0)
        session.net.server.set_game_started(True)
        h.click_end_turn(host)
        session.step_all()
        session.net.server._disconnect_client(1, "crashed")
        session.peers[0].step()                              # takeover starts the AI
        wait_for_ai(host)
        session.step_until(lambda: host.sim_state.round_number == 2, max_steps=200)
        assert host.game_state.player_is_ai[1] is True
        assert host.game_state.player_ai_difficulty[1] == 1          # Medium

    def test_ai_resolves_the_battles_of_a_player_who_left(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: sim_battle(gs, b, owner=0, attacker=1, resolver=1))
        enter_resolving(session)
        host = session.game(0)
        session.net.server.set_game_started(True)
        session.net.server._disconnect_client(1, "crashed")
        for _ in range(40):                                  # > AI delay (2 s at 0.1 s steps)
            session.peers[0].step()
        assert host.game_state.pending_battles == []
        assert host.game_state.territory_owners[b] == 1


# ---------------------------------------------------------------------------
# Order validation (phase manager, no network)
# ---------------------------------------------------------------------------

def _manager():
    gs = GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1],
                   skip_setup_phase=True)
    sim = SimultaneousGameState(gs)
    sim.phase_manager = SimPhaseManager(sim)
    return gs, sim, sim.phase_manager


class TestOrderValidation:

    def test_units_cannot_be_used_by_two_orders(self):
        gs, _, pm = _manager()
        a, b, c = h.adjacent_triple()
        h.place(gs, a, 0, h.units('Swordsman', 'Archer'))
        orders = {0: [
            {'type': 'movement', 'from_territory': a, 'to_territory': b, 'army_count': 2, 'unit_ids': [0, 1]},
            {'type': 'movement', 'from_territory': a, 'to_territory': c, 'army_count': 1, 'unit_ids': [1]},
        ]}
        valid = pm.prepare_orders(orders)
        assert [o['to_territory'] for o in valid] == [b]

    def test_count_follows_the_unit_list(self):
        gs, _, pm = _manager()
        a, b, _ = h.adjacent_triple()
        h.place(gs, a, 0, h.units('Swordsman', 'Archer', 'Pikeman'))
        orders = {0: [{'type': 'movement', 'from_territory': a, 'to_territory': b,
                       'army_count': 3, 'unit_ids': [0]}]}
        assert pm.prepare_orders(orders)[0]['army_count'] == 1

    def test_choosing_an_alliance_owner_removes_that_territorys_marker(self):
        gs, sim, pm = _manager()
        first, second = h.spread_territories(2)
        for territory in (first, second):
            gs.territory_owners[territory] = 0
        pm.pending_alliance_markers = [
            {'type': 'alliance', 'territory': first, 'players': [0, 1], 'chooser': 0},
            {'type': 'alliance', 'territory': second, 'players': [0, 1], 'chooser': 0}]
        sim.sim_phase = 'resolving'
        pm.resolve_alliance_marker(second, 1)
        assert [m['territory'] for m in pm.pending_alliance_markers] == [first]


class TestKnockedOutPlayers:
    """A player who loses their last territory is out (check_victory). Simultaneous mode
    keeps its own eliminated list (auto-readied every round, sent at round end), and only
    Capital Assault eliminations reached it: in Domination / Total Conquest a human who
    was knocked out but stayed connected held up every later round until their own
    planning timer ran out (seen in the first test game: an AI knocked out in round 22
    never reached the list)."""

    def _knock_out_client_2(self, session):
        """Domination game: the host takes client 2's last territory in a battle."""
        homes = h.spread_territories(3)
        _, b, _ = h.adjacent_triple()

        def arrange(gs):
            h.place(gs, homes[2], 0)                         # their capital is already gone
            sim_battle(gs, b, owner=2, attacker=0, resolver=0)
        session.on_all(arrange)
        enter_resolving(session)
        host = session.game(0)
        h.open_battle(host, b)
        h.fight(host)
        h.close_battle(host)
        session.run_until_quiet()
        assert host.sim_state.round_number == 2
        assert 2 in host.game_state.eliminated_players
        return host

    def test_the_next_round_does_not_wait_for_them(self, make_session):
        session = make_session(num_players=3, turn_mode='simultaneous')
        host = self._knock_out_client_2(session)
        h.click_end_turn(session.game(1))
        session.step_all()
        h.click_end_turn(host)
        session.run_until_quiet()
        assert host.sim_state.round_number == 3              # nobody waited for P3
        assert session.game(1).sim_state.round_number == 3

    def test_every_pc_knows_they_are_out(self, make_session):
        session = make_session(num_players=3, turn_mode='simultaneous')
        self._knock_out_client_2(session)
        for index in (0, 1, 2):
            assert 2 in session.game(index).sim_state.eliminated_players

    def test_a_player_knocked_out_while_the_others_plan_does_not_hold_up_the_round(
            self, make_session):
        """E.g. Aggressive Diplomacy takes their last territory during planning: the host
        readies them at once instead of waiting for their timer."""
        session = make_session(num_players=3, turn_mode='simultaneous')
        host = session.game(0)
        h.click_end_turn(session.game(1))
        session.step_all()
        h.click_end_turn(host)
        session.run_until_quiet()
        assert host.sim_state.round_number == 1              # waiting for P3
        home = h.spread_territories(3)[2]

        def knock_out(gs):
            h.place(gs, home, 0)
            gs.check_victory()
        session.on_all(knock_out)
        session.run_until_quiet()
        assert host.sim_state.round_number == session.game(1).sim_state.round_number == 2


class TestClientRoundRecords:

    def test_a_client_records_every_round(self, make_session):
        """complete_round() writes a round's game log / sync log / replay records, and only
        the host runs it (Phase 4): a client's per-game log and saved replay of a
        simultaneous game had no rounds at all."""
        from game_logger import GameLogger
        from replay_recorder import ReplayRecorder
        session = make_session(num_players=2, turn_mode='simultaneous')
        for index in (0, 1):
            gs = session.gs(index)
            gs.game_logger = GameLogger(gs)
            gs.replay_recorder = ReplayRecorder(gs)
        end_turn_all(session)
        session.run_until_quiet()
        for index in (0, 1):
            gs = session.gs(index)
            assert gs.turn_number == 2
            assert list(gs.game_logger.turn_data) == [1]
            assert len(gs.replay_recorder.snapshots) == 2          # start + round 1


class TestKeepBattles:

    def test_attackers_fighting_over_a_keep_replay_identically(self, make_session):
        """Two attackers at one Keep fight each other first (_fight_for_the_keep); every
        PC replays that from the resolver's seed - no PC needs the resolver's result
        forced on it (_apply_battle_outcome)."""
        from game_state import Battle
        session = make_session(num_players=3, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()

        def arrange(gs):
            h.place(gs, b, 2, h.units('Swordsman'), buildings={0: 'Keep'})
            gs.territory_garrisons[b][0] = {
                'unmoved': 0, 'moved': 4, 'units': h.units(*['Cavalry'] * 4, status='moved')}
            gs.territory_garrisons[b][1] = {
                'unmoved': 0, 'moved': 4, 'units': h.units(*['Cavalry'] * 4, status='moved')}
            battle = Battle(b)
            battle.original_owner = 2
            battle.add_army(2, 1, {'Swordsman': 1})
            battle.add_army(0, 4, {'Cavalry': 4})
            battle.add_army(1, 4, {'Cavalry': 4})            # a tie: the seed's dice decide
            battle.keep_bonus, battle.keep_bonus_player, battle.original_garrison = 2, 2, 1
            battle.team_members_map = {0: [0], 1: [1], 2: [2]}
            battle.attackers, battle.resolver, battle.is_multi_way = [0, 1], 0, True
            gs.pending_battles = [battle]
        session.on_all(arrange)
        enter_resolving(session)
        corrections = []
        for index in (1, 2):
            game = session.game(index)
            real = game._apply_battle_outcome
            game._apply_battle_outcome = (lambda territory, data, real=real:
                                          corrections.append(territory) or real(territory, data))
        host = session.game(0)
        h.open_battle(host, b)
        h.fight(host)
        h.close_battle(host)
        session.run_until_quiet()
        assert "fight each other first" in "\n".join(host.game_state.messages)
        assert corrections == []
        assert session.gs(1).territory_owners[b] == session.gs(2).territory_owners[b] \
            == host.game_state.territory_owners[b]
        assert comparable(session.gs(1)) == comparable(host.game_state) == comparable(session.gs(2))


class TestTeamBattles:

    def test_a_team_battle_replays_identically_and_shows_its_survivors(self, make_session):
        """2 v 2: allies 1 and 3 take 2's territory; 1 (a client) fights it. Every PC
        replays it the same way, each ally keeps their own survivors, and the battle
        window counts the team's survivors."""
        session = make_session(num_players=4, turn_mode='simultaneous', teams=[0, 1, 0, 1])
        _, b, _ = h.adjacent_triple()
        for peer in session.peers.values():
            gs = peer.game.game_state
            h.place(gs, b, 2, h.units('Swordsman', 'Swordsman'))
            gs.territory_garrisons[b][1] = {
                'unmoved': 0, 'moved': 4, 'units': h.units(*['Swordsman'] * 4, status='moved')}
            gs.territory_garrisons[b][3] = {
                'unmoved': 0, 'moved': 2, 'units': h.units('Swordsman', 'Swordsman', status='moved')}
            pm = peer.game.sim_state.phase_manager
            pm.pending_battles = [pm._create_battle_conflict(b, [2, 1, 3])]
            pm._setup_battles_for_ui()
        enter_resolving(session)
        corrections = []
        for index in (0, 2, 3):
            game = session.game(index)
            real = game._apply_battle_outcome
            game._apply_battle_outcome = (lambda territory, data, real=real:
                                          corrections.append(territory) or real(territory, data))
        client = session.game(1)
        h.open_battle(client, b)
        h.fight(client)
        assert client.enhanced_battle_ui.attacker_survivors == 5
        h.close_battle(client)
        session.run_until_quiet()
        assert corrections == []
        for index in range(4):
            gs = session.gs(index)
            assert gs.territory_owners[b] == 1
            assert len(gs.territory_garrisons[b][1]['units']) == 3
            assert len(gs.territory_garrisons[b][3]['units']) == 2
