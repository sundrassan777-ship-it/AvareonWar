# -*- coding: utf-8 -*-
"""
Battle sync in multiplayer (multiplayer audit, Phase 3).

A battle resolved on one PC is REPLAYED on the others from the resolver's seed
(Game._handle_remote_battle_resolve), so every side effect happens everywhere -
buildings, heroes, reports - instead of only the owner + survivors being copied. A
result that arrives before the receiver's own copy of the move has finished is held
until the battle exists there.

Real Game objects joined by tests/mp_harness.py.
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

HERO = 'Evain Nithieln'   # no battle-related passives


def client_attacks_host(session, attackers=10, keep_with_hero=False):
    """Client (player 1) orders veteran Cavalry from A into the host's B (1 Archer)."""
    a, b, _ = h.adjacent_triple()
    veterans = h.units(*(['Cavalry'] * attackers), level=3, xp=150)

    def arrange(gs):
        h.place(gs, a, 1, veterans)
        h.place(gs, b, 0, h.units('Archer'), buildings={0: 'Keep'} if keep_with_hero else None)
        if keep_with_hero:
            gs.heroes[0][HERO] = {'keep_territory': b, 'keep_plot': 0, 'status': 'active'}
            gs.hero_ownership[0].add(HERO)
    session.on_all(arrange)
    h.set_turn(session, 1)
    client = session.game(1)
    assert client.game_state.add_movement_order_for_units(a, b, list(range(attackers)))
    return a, b


def fight_it_out(session, b):
    client = session.game(1)
    h.open_battle(client, b)
    h.fight(client)
    h.close_battle(client)


def record_battle_messages(game, monkeypatch):
    """Data of every BATTLE_RESOLVE this game handles."""
    seen = []
    original = game._handle_remote_battle_resolve

    def spy(message, allow_hold=True):
        seen.append(message['data'])
        return original(message, allow_hold=allow_hold)
    monkeypatch.setattr(game, '_handle_remote_battle_resolve', spy)
    return seen


class TestReplay:

    def test_result_carries_seed_and_full_survivors(self, make_session, monkeypatch):
        session = make_session(num_players=2)
        _, b = client_attacks_host(session)
        seen = record_battle_messages(session.game(0), monkeypatch)
        h.click_end_turn(session.game(1))
        session.step_until(lambda: any(bt.territory == b for bt in session.gs(1).pending_battles))
        fight_it_out(session, b)
        session.run_until_quiet()
        assert len(seen) == 1
        data = seen[0]
        assert isinstance(data['battle_seed'], int)
        survivors = data['garrisons']['1']['units']
        assert survivors and all(u['level'] == 3 and u['xp'] >= 150 for u in survivors)

    def test_hero_dies_and_reports_arrive_once_on_the_defender(self, make_session):
        session = make_session(num_players=2)
        _, b = client_attacks_host(session, keep_with_hero=True)
        h.click_end_turn(session.game(1))
        session.step_until(lambda: any(bt.territory == b for bt in session.gs(1).pending_battles))
        fight_it_out(session, b)
        session.run_until_quiet()

        for index in (0, 1):
            gs = session.gs(index)
            assert gs.territory_owners[b] == 1
            assert HERO not in gs.heroes[0]                 # slain on both PCs
            assert not gs.buildings.get(b)                  # Keep destroyed on both
        host = session.game(0)
        # The host replayed the battle: its own report + hero-death toast, no copies
        reports = [r for r in host.game_state.battle_report_inbox if r['territory'] == b]
        assert len(reports) == 1 and reports[0]['defender'] == 0
        assert reports[0]['heroes_slain'] == [HERO]
        assert host.battle_report_queues.get(0, []) == []
        assert (0, HERO, b) in host.game_state.hero_death_events

    def test_result_that_arrives_early_is_held_until_the_battle_exists(self, make_session):
        """The resolver fights before the receiver's own armies have arrived."""
        session = make_session(num_players=2)
        _, b = client_attacks_host(session)
        client, host = session.game(1), session.game(0)
        h.click_end_turn(client)
        for _ in range(100):                                 # only the client runs
            session.peers[1].step()
            if any(bt.territory == b for bt in client.game_state.pending_battles):
                break
        fight_it_out(session, b)
        session.flush()                                      # EXECUTE_ORDERS + result
        host._process_network_messages()
        assert host.game_state.active_animations             # host's armies still marching
        assert host._held_network_messages                   # result held, not rejected
        session.run_until_quiet()
        assert not host._held_network_messages
        assert host.game_state.territory_owners[b] == 1
        assert h.garrison_summary(host.game_state, b) == h.garrison_summary(client.game_state, b)

    def test_replay_that_disagrees_is_corrected_to_the_resolvers_result(self, make_session):
        """States had drifted: the replay gives another result -> the sender's wins."""
        session = make_session(num_players=2)
        a, b, _ = h.adjacent_triple()
        host = session.game(0)
        gs = host.game_state
        h.place(gs, b, 0, h.units('Archer'))
        gs.territory_garrisons[b][1] = {'unmoved': 0, 'moved': 3,
                                        'units': h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')}
        gs.pending_battles = [h.battle_at(b, owner=0, attacker=1)]
        gs.turn_phase = 'battles'
        claimed = h.units('Pikeman', 'Pikeman', status='moved')   # not what our replay yields
        host._handle_network_message({'type': MessageType.BATTLE_RESOLVE, 'data': {
            'territory': b, 'winner': 1, 'surviving_armies': 2, 'new_owner': 1,
            'battle_seed': 7, 'garrisons': {'1': {'unmoved': 0, 'moved': 2, 'units': claimed}}}})
        assert gs.territory_owners[b] == 1
        assert h.garrison_summary(gs, b) == {1: ['Pikeman', 'Pikeman']}
        assert gs.pending_battles == []

    def test_seedless_result_still_applies_with_allies(self, make_session):
        """Older senders: no seed - applied as sent, every garrison included."""
        session = make_session(num_players=3, teams=[0, 1, 1])
        _, b, _ = h.adjacent_triple()
        host = session.game(0)
        gs = host.game_state
        h.place(gs, b, 0, h.units('Archer'))
        gs.pending_battles = [h.battle_at(b, owner=0, attacker=1)]
        gs.turn_phase = 'battles'
        host._handle_network_message({'type': MessageType.BATTLE_RESOLVE, 'data': {
            'territory': b, 'winner': 1, 'surviving_armies': 2, 'new_owner': 1,
            'garrisons': {'1': {'unmoved': 0, 'moved': 1, 'units': h.units('Cavalry', status='moved')},
                          '2': {'unmoved': 0, 'moved': 1, 'units': h.units('Pikeman', status='moved')}}}})
        assert gs.territory_owners[b] == 1
        assert h.garrison_summary(gs, b) == {1: ['Cavalry'], 2: ['Pikeman']}


class TestBattleWindow:

    def test_fight_on_a_battle_resolved_elsewhere_closes_the_window(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        _, b, _ = h.adjacent_triple()
        client = session.game(1)
        gs = client.game_state
        h.place(gs, b, 0, h.units('Archer'))
        gs.territory_garrisons[b][1] = {'unmoved': 0, 'moved': 3,
                                        'units': h.units('Cavalry', 'Cavalry', 'Cavalry', status='moved')}
        gs.pending_battles = [h.battle_at(b, owner=0, attacker=1)]
        client.sim_state.sim_phase = 'resolving'
        h.open_battle(client, b)
        # e.g. the host settled it for an absent resolver
        client._handle_network_message({'type': MessageType.BATTLE_RESOLVE, 'data': {
            'territory': b, 'winner': 1, 'surviving_armies': 3, 'new_owner': 1, 'battle_seed': 3}})
        assert gs.pending_battles == []
        assert h.fight(client) is True
        assert client.enhanced_battle_ui is None and not client.battle_popup_visible
        assert client.selected_battle_territory is None


class TestSeededResolution:

    def test_resolvers_seed_reproduces_dice_ties(self, make_session):
        """A perfect tie goes to the dice: the replay must roll the same."""
        session = make_session(num_players=2)
        _, b, _ = h.adjacent_triple()
        outcomes = set()
        for seed in range(12):
            results = []
            for index in (0, 1):
                gs = session.gs(index)
                h.place(gs, b, 0, h.units('Swordsman', 'Swordsman'))
                gs.territory_garrisons[b][1] = {'unmoved': 0, 'moved': 2,
                                                'units': h.units('Swordsman', 'Swordsman', status='moved')}
                battle = h.battle_at(b, owner=0, attacker=1, defenders=2, attackers=2)
                battle.army_compositions = {0: {'Swordsman': 2}, 1: {'Swordsman': 2}}
                gs.pending_battles = [battle]
                gs.resolve_battle(0, rng=random.Random(seed))
                results.append((gs.territory_owners[b], h.garrison_summary(gs, b),
                                getattr(battle, 'dice_results', None)))
            assert results[0] == results[1]
            assert results[0][2] is not None                # the dice were rolled
            outcomes.add(results[0][0])
        assert len(outcomes) > 1                             # and the seed matters
