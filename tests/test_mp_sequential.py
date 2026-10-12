# -*- coding: utf-8 -*-
"""
Sequential-mode multiplayer sync tests (pre-launch multiplayer audit).

Two or three real Game objects are joined by tests/mp_harness.py. Every arrangement
is applied to all peers (Session.on_all), so the peers start in agreement; the turn
is then driven through the real input handlers (End Turn button, battle window,
chat box, ability targeting) and the peers must still agree afterwards.

xfail(strict=True) tests reproduce confirmed audit findings (ID in the reason); the
fixing phase removes the marker.
"""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from network_config import MessageType  # noqa: E402


class TestHarnessSanity:

    def test_host_build_reaches_the_client(self, make_session):
        session = make_session(num_players=2)
        capital = h.spread_territories(2)[0]
        assert session.game(0)._try_start_construction(capital, 0, 'Farm')
        session.run_until_quiet()
        assert session.gs(1).under_construction[capital][0][0] == 'Farm'
        assert session.gs(1).player_gold[0] == session.gs(0).player_gold[0]

    def test_end_turn_without_orders_passes_the_turn_everywhere(self, make_session):
        session = make_session(num_players=2)
        h.click_end_turn(session.game(0))
        session.run_until_quiet()
        assert session.gs(0).current_player == session.gs(1).current_player == 1


class TestTurnStartCompletions:

    def test_trained_unit_appears_once_on_every_peer(self, make_session):
        session = make_session(num_players=2)
        capital = h.spread_territories(2)[1]          # the client's starting territory

        def arrange(gs):
            gs.buildings[capital] = {0: 'Barracks'}
            gs.training_queue[capital] = {0: [('Archer', 1, 20)]}
        session.on_all(arrange)

        h.click_end_turn(session.game(0))             # host ends turn -> client's turn starts
        session.run_until_quiet()
        client_view = h.garrison_summary(session.gs(1), capital)
        assert client_view[1].count('Archer') == 2    # starting Archer + the trained one
        assert h.garrison_summary(session.gs(0), capital) == client_view


class TestStateSyncTiming:

    def test_host_move_is_not_reverted_on_the_client(self, make_session):
        session = make_session(num_players=2)
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 0, h.units('Swordsman', 'Swordsman', 'Archer')),
                                   h.place(gs, b, 0)))
        host = session.game(0)
        assert host.game_state.add_movement_order_for_units(a, b, [0, 1, 2])
        h.click_end_turn(host)
        session.run_until_quiet()

        assert h.garrison_summary(session.gs(0), b) == {0: ['Archer', 'Swordsman', 'Swordsman']}
        assert h.garrison_summary(session.gs(1), b) == h.garrison_summary(session.gs(0), b)
        assert h.garrison_summary(session.gs(1), a) == {}


class TestClientAttackOnTheHost:
    """The client takes the host's Farm territory with veteran Cavalry (one shared run)."""

    @pytest.fixture(scope='class')
    def outcome(self):
        session = h.Session(num_players=2)
        try:
            a, b, _ = h.adjacent_triple()
            veterans = h.units('Cavalry', 'Cavalry', 'Cavalry', level=2, xp=80)

            def arrange(gs):
                h.place(gs, a, 1, veterans)
                h.place(gs, b, 0, h.units('Archer'), buildings={0: 'Farm'})
            session.on_all(arrange)
            h.set_turn(session, 1)

            client = session.game(1)
            assert client.game_state.add_movement_order_for_units(a, b, [0, 1, 2])
            h.click_end_turn(client)
            session.step_until(lambda: any(bt.territory == b for bt in client.game_state.pending_battles))
            h.open_battle(client, b)
            h.fight(client)
            for _ in range(5):                        # messages already in flight land now
                session.step_all()
            h.close_battle(client)
            session.run_until_quiet()
            yield session, a, b
        finally:
            session.close()

    def test_the_territory_changes_hands_on_both_peers(self, outcome):
        session, _, b = outcome
        assert session.gs(0).territory_owners[b] == session.gs(1).territory_owners[b] == 1

    def test_the_captured_farm_is_destroyed_on_both_peers(self, outcome):
        session, _, b = outcome
        assert not session.gs(0).buildings.get(b)
        assert not session.gs(1).buildings.get(b)

    def test_survivors_keep_their_type_and_veterancy(self, outcome):
        session, _, b = outcome
        for index in (0, 1):
            survivors = session.gs(index).territory_garrisons[b][1]['units']
            assert survivors
            assert all(u['type'] == 'Cavalry' for u in survivors)
            assert all(isinstance(u['id'], int) for u in survivors)
            assert all(u.get('level', 0) >= 2 for u in survivors)

    def test_reinforcing_the_captured_territory_does_not_crash(self, outcome):
        session, a, b = outcome
        h.click_end_turn(session.game(0))             # host's turn ends -> back to the client
        session.run_until_quiet()
        session.on_all(lambda gs: h.place(gs, a, 1, h.units('Pikeman')))
        client = session.game(1)
        assert client.game_state.add_movement_order_for_units(a, b, [0])
        h.click_end_turn(client)
        session.run_until_quiet()
        assert 'Pikeman' in h.garrison_summary(session.gs(0), b)[1]


class TestCancellations:

    def test_cancelled_construction_is_cancelled_everywhere(self, make_session):
        session = make_session(num_players=2)
        capital = h.spread_territories(2)[1]
        h.set_turn(session, 1)
        client = session.game(1)
        gold_before = client.game_state.player_gold[1]
        assert client._try_start_construction(capital, 0, 'Farm')
        session.run_until_quiet()
        h.click_cancel_construction(client, capital, 0)
        session.run_until_quiet()
        for index in (0, 1):
            gs = session.gs(index)
            assert capital not in gs.under_construction
            assert gs.player_gold[1] == gold_before


class TestEndTurnButton:

    def test_greyed_end_turn_sends_nothing(self, make_session):
        session = make_session(num_players=2)
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman')), h.place(gs, b, 1)))
        h.set_turn(session, 1)
        client = session.game(1)
        assert client.game_state.add_movement_order_for_units(a, b, [0])
        h.click_end_turn(client)
        assert client.game_state.turn_phase == 'execution'
        session.flush()
        sent_before = [entry for entry in session.net.log if entry[0] == 'c2s']
        h.click_end_turn(client)                      # the button is greyed now
        session.flush()
        assert [entry for entry in session.net.log if entry[0] == 'c2s'] == sent_before


class TestChat:

    def test_team_chat_stays_within_the_team(self, make_session):
        session = make_session(num_players=3, teams=[0, 0, 1])
        h.send_chat(session.game(1), "attack at dawn", channel='team')
        session.run_until_quiet()

        def visible(index):
            return [entry[2] for entry in session.gs(index).get_visible_chat_messages(index)]
        assert "attack at dawn" in visible(0)        # the ally (host) reads it
        assert "attack at dawn" not in visible(2)    # the enemy does not

    def test_gold_cheat_is_disabled_in_multiplayer(self, make_session):
        session = make_session(num_players=2)
        before = [session.gs(i).player_gold[0] for i in (0, 1)]
        h.send_chat(session.game(0), "jurvikisrichboi")
        session.run_until_quiet()
        assert [session.gs(i).player_gold[0] for i in (0, 1)] == before

    def test_unit_cheat_is_disabled_in_multiplayer(self, make_session):
        session = make_session(num_players=2)
        host = session.game(0)
        capital = h.spread_territories(2)[0]
        host.selected_plot = (capital, 0)
        before = len(session.gs(0).territory_garrisons[capital][0]['units'])
        h.send_chat(host, "youhavemysword1")
        assert len(session.gs(0).territory_garrisons[capital][0]['units']) == before


class TestHeroAbilities:

    def test_decisive_strike_removes_the_same_units_everywhere(self, make_session, monkeypatch):
        session = make_session(num_players=2)
        host_capital, client_capital = h.spread_territories(2)
        hero, ability_index = h.hero_with_ability('Decisive Strike')
        victims = h.units('Swordsman', 'Swordsman', 'Swordsman', 'Swordsman',
                          'Archer', 'Archer', 'Archer', 'Archer')

        def arrange(gs):
            gs.buildings[host_capital] = {0: 'Keep'}
            gs.heroes[0][hero] = {'keep_territory': host_capital, 'keep_plot': 0, 'status': 'active'}
            gs.hero_ownership[0].add(hero)
            h.place(gs, client_capital, 1, victims)
        session.on_all(arrange)

        calls = []

        def sample(population, k):
            """Each PC 'rolls' differently: first k on one call, last k on the next."""
            calls.append(k)
            items = list(population)
            return items[:k] if len(calls) % 2 else items[-k:]
        monkeypatch.setattr(random, 'sample', sample)

        h.cast_targeted_ability(session.game(0), hero, ability_index, client_capital)
        session.run_until_quiet()
        assert len(calls) >= 1
        assert (h.garrison_summary(session.gs(0), client_capital)
                == h.garrison_summary(session.gs(1), client_capital))


class TestIncomeCache:

    def test_income_follows_a_networked_capture(self, make_session):
        session = make_session(num_players=2)
        host = session.game(0)
        gs = host.game_state
        _, b, _ = h.adjacent_triple()
        session.on_all(lambda g: h.place(g, b, 0, h.units('Archer')))
        before = gs.calculate_player_income(1)        # now cached
        gs.pending_battles = [h.battle_at(b, owner=0, attacker=1)]
        host._handle_network_message({'type': MessageType.BATTLE_RESOLVE, 'data': {
            'territory': b, 'winner': 1, 'surviving_armies': 3, 'new_owner': 1,
            'surviving_units': h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')}})
        assert gs.calculate_player_income(1) == before + gs.calculate_territory_income(b, 1)
