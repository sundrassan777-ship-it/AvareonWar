# -*- coding: utf-8 -*-
"""
Simultaneous-mode multiplayer sync tests (pre-launch multiplayer audit).

Simultaneous mode is the primary multiplayer mode. Network tests run real Game
objects joined by tests/mp_harness.py; the sim_state / phase-manager tests use the
real classes directly.

xfail(strict=True) tests reproduce confirmed audit findings (ID in the reason); the
fixing phase removes the marker.
"""

import os
import sys
import threading

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from game_state import GameState  # noqa: E402
from network_config import MessageType  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402


def ready_both(session):
    """Client presses End Turn, the host learns it, then the host presses End Turn."""
    h.click_end_turn(session.game(1))
    session.step_all()
    h.click_end_turn(session.game(0))


class TestHarnessSanity:

    def test_a_simple_round_completes_on_both_peers(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        ready_both(session)
        session.run_until_quiet()
        assert session.game(0).sim_state.round_number == session.game(1).sim_state.round_number == 2


class TestOrderExecution:

    def test_split_army_moves_both_groups(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        a, b, _ = h.adjacent_triple()
        session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman', 'Swordsman', 'Archer', 'Archer')),
                                   h.place(gs, b, 1)))
        client = session.game(1)
        assert client.game_state.add_movement_order_for_units(a, b, [0, 1])
        assert client.game_state.add_movement_order_for_units(a, b, [2, 3])
        ready_both(session)
        session.run_until_quiet()
        for index in (0, 1):
            assert len(h.garrison_summary(session.gs(index), b).get(1, [])) == 4

    def test_client_executes_only_what_the_host_executes(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        a, b, c = h.adjacent_triple()
        far = h.far_from(a)
        # The host also makes a valid move elsewhere, so its round lasts until those armies
        # arrive (with no valid move at all, the round ends at once and its override would
        # hide the client's divergence inside the same message batch)
        x, y, _ = h.adjacent_triple(avoid=set(h.spread_territories(4)) | {a, b, c, far})
        session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman', 'Archer')), h.place(gs, far, 1),
                                   h.place(gs, x, 0, h.units('Pikeman')), h.place(gs, y, 0)))
        host, client = session.game(0), session.game(1)
        assert host.game_state.add_movement_order_for_units(x, y, [0])
        # An order the host refuses (not adjacent) - e.g. sent by a modified client
        client.sim_state.add_order(1, {'type': 'movement', 'player_id': 1, 'from_territory': a,
                                       'to_territory': far, 'army_count': 2, 'unit_ids': [0, 1]})
        ready_both(session)
        session.flush()                               # SIM_ALL_READY reaches the client
        for _ in range(30):                           # both execute and process arrivals; the
            session.peers[0].step()                   # host's round-complete is not delivered
            session.peers[1].step()
        assert not session.gs(1).active_animations
        assert h.garrison_summary(session.gs(1), far) == h.garrison_summary(session.gs(0), far)


class TestBattleResolution:

    def test_fight_resolves_the_battle_that_was_opened(self, make_session):
        client, b = self._client_window_on_battle_two(make_session)
        h.fight(client)
        assert client.game_state.territory_owners[b] == 1

    def test_the_windows_own_fight_button_survives_the_shift(self, make_session):
        """Through the battle window's REAL FIGHT button (h.fight stubs it): the window
        read its battle at the index saved when it opened - past the end of the list
        once battle #1 was gone, so the click crashed with an IndexError."""
        client, b = self._client_window_on_battle_two(make_session)
        ui = client.enhanced_battle_ui
        assert client.handle_battle_popup_click(ui.resolve_button_rect.center) is True
        assert client.game_state.territory_owners[b] == 1

    def _client_window_on_battle_two(self, make_session):
        """The client's window shows battle #2 while the host resolves battle #1."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        a, b, _ = h.adjacent_triple()
        cavalry = h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')

        def arrange(gs):
            h.place(gs, a, 1, h.units('Archer'))                       # host attacks the client at A
            gs.territory_garrisons[a][0] = {'unmoved': 0, 'moved': 3, 'units': [dict(u) for u in cavalry]}
            h.place(gs, b, 0, h.units('Archer'))                       # client attacks the host at B
            gs.territory_garrisons[b][1] = {'unmoved': 0, 'moved': 3, 'units': [dict(u) for u in cavalry]}
            gs.pending_battles = [h.battle_at(a, owner=1, attacker=0),
                                  h.battle_at(b, owner=0, attacker=1)]
        session.on_all(arrange)
        for peer in session.peers.values():
            peer.game.sim_state.sim_phase = 'resolving'

        client, host = session.game(1), session.game(0)
        h.open_battle(client, b)                      # the client's window shows battle #2
        h.open_battle(host, a)                        # meanwhile the host fights battle #1
        h.fight(host)
        h.close_battle(host)
        session.flush()
        client._process_network_messages()            # the client learns battle #1 is gone
        return client, b


class TestRoundSync:

    def test_waiting_list_is_accurate_in_the_next_round(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        ready_both(session)
        session.run_until_quiet()
        client_sim = session.game(1).sim_state
        assert client_sim.round_number == 2
        assert not client_sim.players_ready.get(0, False)

    def test_client_survives_an_elimination_after_round_sync(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        session.game(0)._sim_broadcast_round_complete(2)
        session.run_until_quiet()
        client_sim = session.game(1).sim_state
        client_sim.eliminate_player(1)
        assert 1 in client_sim.eliminated_players

    def test_host_alliance_choice_is_sent_before_the_round_ends(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        host = session.game(0)
        territory = h.far_from(h.spread_territories(2)[0])
        host.sim_state.sim_phase = 'resolving'
        host.game_state.pending_battles = []
        host.sim_state.phase_manager.pending_alliance_markers = [
            {'type': 'alliance', 'territory': territory, 'players': [0, 1], 'chooser': 0}]
        button = pygame.Rect(100, 100, 50, 20)
        host.alliance_choice_popup_visible = True
        host.alliance_choice_territory = territory
        host.alliance_choice_players = [0, 1]
        host.alliance_choice_popup_rect = pygame.Rect(0, 0, 1600, 900)
        host.alliance_choice_buttons = [(button, 1)]
        host.handle_alliance_choice_click(button.center)
        session.flush()
        received = [t for d, i, t in session.net.log if d == 's2c' and i == 1]
        assert (received.index(MessageType.SIM_ALLIANCE_CHOICE)
                < received.index(MessageType.SIM_ROUND_COMPLETE))


class TestAiPlanning:

    def test_clients_do_not_plan_for_ai_slots(self, make_session):
        session = make_session(num_players=3, ai_slots=(2,), turn_mode='simultaneous')
        assert session.game(1).sim_ai is None


# ---------------------------------------------------------------------------
# sim_state / phase manager (no network needed)
# ---------------------------------------------------------------------------

def _sim(num_players=2, player_is_ai=None):
    gs = GameState(num_players=num_players, player_is_ai=player_is_ai or [False] * num_players,
                   player_ai_difficulty=[1] * num_players, skip_setup_phase=True)
    sim = SimultaneousGameState(gs)
    sim.phase_manager = SimPhaseManager(sim)
    return gs, sim


class TestReadiness:

    def test_host_execution_never_starts_on_a_background_thread(self):
        gs, sim = _sim(player_is_ai=[False, True])
        sim.is_multiplayer_host = True
        started_on = []
        sim.on_all_ready_callback = lambda: started_on.append(threading.current_thread())
        sim.start_planning_phase()
        sim.players_ready[0] = True
        worker = threading.Thread(target=sim.mark_ready, args=(1,))
        worker.start()
        worker.join()
        assert started_on == []                       # deferred, not run on the AI thread
        sim.check_deferred_execution()                # the main loop picks it up
        assert started_on == [threading.main_thread()]

    def test_humans_are_not_auto_readied_in_multiplayer(self):
        gs, sim = _sim()
        territory = h.spread_territories(2)[1]
        gs.territory_owners[territory] = 1            # owns land, no army, no gold
        gs.player_gold = [100, 0]
        sim.local_player_index = 1
        sim.is_multiplayer_client = True
        sim.start_planning_phase()
        assert not sim.players_ready[1]


class TestAiHeroAbilities:

    def _hero_setup(self, ability_name):
        gs, sim = _sim(player_is_ai=[False, True])
        hero, _ = h.hero_with_ability(ability_name)
        home, target = h.spread_territories(2)[1], h.spread_territories(2)[0]
        gs.territory_owners[home] = 1
        gs.buildings[home] = {0: 'Keep'}
        gs.heroes[1][hero] = {'keep_territory': home, 'keep_plot': 0, 'status': 'active'}
        gs.hero_ownership[1].add(hero)
        return gs, sim, hero, home, target

    def test_ai_decisive_strike_is_executed(self):
        gs, sim, hero, _, target = self._hero_setup('Decisive Strike')
        h.place(gs, target, 0, h.units('Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Swordsman', 'Archer'))
        sim.phase_manager._apply_hero_ability_order({'type': 'hero_ability', 'player_id': 1,
                                                     'hero_type': hero, 'ability_name': 'Decisive Strike',
                                                     'target': target})
        assert len(gs.territory_garrisons[target][0]['units']) == 3

    def test_ai_targeted_ability_goes_on_cooldown(self):
        gs, sim, hero, home, _ = self._hero_setup('Relentless Charge')
        h.place(gs, home, 1, h.units('Swordsman'))
        sim.phase_manager._apply_hero_ability_order({'type': 'hero_ability', 'player_id': 1,
                                                     'hero_type': hero, 'ability_name': 'Relentless Charge',
                                                     'target': home})
        assert len(gs.territory_garrisons[home][1]['units']) == 5          # cast went through
        assert gs.hero_ability_cooldowns[1].get(hero, {}).get('Relentless Charge', 0) > 0
