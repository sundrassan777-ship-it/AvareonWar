# -*- coding: utf-8 -*-
"""
Unique unit ids - found in the FFA test game of 2026-10-14.

Simultaneous-mode arrivals numbered a newcomer len(units). A garrison that had lost a
unit that round gave the newcomer an id still in use: Leimarch, round 9, held
[Archer #0, Cavalry #1]; #0 marched to Liadnon while an Archer from Carnae arrived and
became the second #1. Nothing ever renumbers a garrison, so from then on every order that
named both twins - the army panel selects every ready unit when it opens, "Select All"
does too - was refused by the host: 35 orders over the game, every player and the AI.
GarrisonMixin.next_free_unit_id() gives the lowest id that is free in the garrison.

Sequential mode's ally reinforcement numbered arrivals 0..n-1 and appended them to the
ally's existing garrison there - the same clash.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_player  # noqa: E402
import map_data  # noqa: E402
import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from game_state import GameState  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402
from simultaneous.sim_ai import SimultaneousAI  # noqa: E402


def _manager(player_is_ai=(False, False)):
    """A simultaneous round's machinery without a network (the single-player path)."""
    gs = GameState(num_players=len(player_is_ai), player_is_ai=list(player_is_ai),
                   player_ai_difficulty=[1] * len(player_is_ai), skip_setup_phase=True)
    sim = SimultaneousGameState(gs)
    sim.phase_manager = SimPhaseManager(sim)
    return gs, sim, sim.phase_manager


def _unit(unit_type, unit_id, status='ready'):
    return {'id': unit_id, 'status': status, 'order': None, 'type': unit_type, 'xp': 0, 'level': 0}


def _move(player, source, target, unit_ids):
    return {'type': 'movement', 'player_id': player, 'from_territory': source,
            'to_territory': target, 'army_count': len(unit_ids), 'unit_ids': list(unit_ids)}


def _units(gs, territory, player):
    return (gs.territory_garrisons.get(territory, {}).get(player) or {}).get('units', [])


def _ids(gs, territory, player):
    return [unit['id'] for unit in _units(gs, territory, player)]


def _run_moves(pm, orders):
    """The armies set off and arrive (what the round does once the animations end)."""
    pm._execute_movement_orders(orders)
    pm._process_arrivals()


def _leimarch_round_9(gs, pm, player=0):
    """Round 9 of the test game: A held [Archer #0 ready, Cavalry #1 just trained];
    #0 marched to C while B's Archer #0 came in."""
    a, b, c = h.adjacent_triple()
    h.place(gs, a, player, [_unit('Archer', 0), _unit('Cavalry', 1, status='moved')])
    h.place(gs, b, player, [_unit('Archer', 0)])
    h.place(gs, c, player)
    _run_moves(pm, [_move(player, a, c, [0]), _move(player, b, a, [0])])
    return a, b, c


class TestNextFreeUnitId:

    def test_the_lowest_id_no_unit_uses(self):
        assert GameState.next_free_unit_id([{'id': 1}, {'id': 0}, {'id': 3}]) == 2

    def test_an_empty_garrison_starts_at_0(self):
        assert GameState.next_free_unit_id([]) == 0

    def test_a_gap_left_by_a_unit_that_marched_out_is_reused(self):
        assert GameState.next_free_unit_id([{'id': 1}]) == 0


class TestSimultaneousArrivals:

    def test_the_round_9_leimarch_arrival_gets_a_free_id(self):
        gs, _sim, pm = _manager()
        a, _b, c = _leimarch_round_9(gs, pm)
        ids = _ids(gs, a, 0)
        assert sorted(ids) == [0, 1]                        # was [1, 1]
        assert {unit['type']: unit['id'] for unit in _units(gs, a, 0)} == {'Cavalry': 1, 'Archer': 0}
        assert _ids(gs, c, 0) == [0]

    def test_next_round_the_whole_army_moves(self):
        """What the army panel does: select every ready unit, move them all."""
        gs, sim, pm = _manager()
        a, _b, c = _leimarch_round_9(gs, pm)
        sim._reset_unit_movement_status()                  # the next round's planning
        ready = [unit['id'] for unit in _units(gs, a, 0) if unit['status'] == 'ready']
        assert len(ready) == 2
        valid = pm.prepare_orders({0: [_move(0, a, c, ready)]})
        assert len(valid) == 1 and sorted(valid[0]['unit_ids']) == sorted(ready)
        _run_moves(pm, valid)
        assert _units(gs, a, 0) == []
        assert sorted(unit['type'] for unit in _units(gs, c, 0)) == ['Archer', 'Archer', 'Cavalry']
        assert len(set(_ids(gs, c, 0))) == 3

    def test_several_arrivals_into_a_garrison_with_a_gap(self):
        gs, _sim, pm = _manager()
        a, b, c = h.adjacent_triple()
        h.place(gs, a, 0, [_unit('Swordsman', 0), _unit('Archer', 2)])
        h.place(gs, b, 0, [_unit('Swordsman', 0), _unit('Pikeman', 1)])
        h.place(gs, c, 0, [_unit('Cavalry', 0)])
        _run_moves(pm, [_move(0, a, b, [0]), _move(0, b, a, [0, 1]), _move(0, c, a, [0])])
        ids = _ids(gs, a, 0)
        assert len(ids) == 4 and len(set(ids)) == 4
        assert ids[0] == 2                                  # the unit that stayed keeps its id
        assert _ids(gs, b, 0) == [0]

    def test_an_arrival_into_an_empty_garrison_is_numbered_from_0(self):
        """Unchanged behaviour: a fresh garrison still gets 0..n-1."""
        gs, _sim, pm = _manager()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 0, [_unit('Swordsman', 4), _unit('Archer', 7)])
        h.place(gs, b, 0)
        _run_moves(pm, [_move(0, a, b, [4, 7])])
        assert _ids(gs, b, 0) == [0, 1]

    def test_the_ais_orders_name_each_unit_once(self):
        gs, sim, pm = _manager(player_is_ai=(False, True))
        ai = SimultaneousAI(sim, ai_player)
        a, _b, c = _leimarch_round_9(gs, pm, player=1)
        sim._reset_unit_movement_status()
        ai._queue_action_as_order(1, 'move', {'from': a, 'to': c, 'army_count': 2})
        order = sim.player_orders[1][-1]
        assert len(order['unit_ids']) == 2 and len(set(order['unit_ids'])) == 2
        assert len(pm.prepare_orders({1: [order]})) == 1


def _plain_territory():
    """A territory that is neither a fortress (its innate Keep would make the owner a
    defender) nor a starting territory."""
    avoid = set(h.spread_territories(4))
    for territory in sorted(map_data.get_all_territories()):
        if territory not in avoid and not map_data.is_fortress_territory(territory):
            return territory
    raise AssertionError("no plain territory on the map")


class TestSequentialAllyReinforcement:

    def test_reinforcing_an_ally_where_this_player_already_stands(self):
        """Player 0's units already guard ally 1's territory, whose own garrison is gone;
        two more of player 0's units arrive."""
        gs = GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1],
                       skip_setup_phase=True)
        gs.player_teams = [0, 0]
        gs.phase = 'playing'
        territory = _plain_territory()
        gs.territory_owners[territory] = 1
        gs.buildings.pop(territory, None)
        gs.territory_garrisons[territory] = {
            0: {'unmoved': 2, 'moved': 0, 'units': [_unit('Swordsman', 0), _unit('Pikeman', 1)]}}
        gs.current_player = 0
        gs.turn_phase = 'execution'
        gs.pending_arrivals = [SimpleNamespace(
            to_territory=territory, player=0, army_count=2, composition={'Archer': 2},
            units=[_unit('Archer', 0, status='moved'), _unit('Archer', 1, status='moved')])]
        gs._process_arrivals()
        ids = _ids(gs, territory, 0)
        assert len(ids) == 4 and len(set(ids)) == 4         # was [0, 1, 0, 1]
        assert gs.territory_owners[territory] == 1


class TestMultiplayerRound:

    def test_the_army_moves_whole_on_every_pc(self, make_session):
        """Round 1 repeats Leimarch's round 9 on a client; in round 2 the client sends the
        whole army on, and the host carries it out."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        a, b, c = h.adjacent_triple()
        session.on_all(lambda gs: (
            h.place(gs, a, 1, [_unit('Archer', 0), _unit('Cavalry', 1, status='moved')]),
            h.place(gs, b, 1, [_unit('Archer', 0)]),
            h.place(gs, c, 1)))
        client, host = session.game(1), session.game(0)
        assert client.game_state.add_movement_order_for_units(a, c, [0])
        assert client.game_state.add_movement_order_for_units(b, a, [0])
        for index in (1, 0):
            h.click_end_turn(session.game(index))
            session.step_all()
        session.step_until(lambda: host.sim_state.round_number == 2, max_steps=400)
        session.run_until_quiet()

        ids = _ids(client.game_state, a, 1)
        assert sorted(ids) == [0, 1]
        ready = [unit['id'] for unit in _units(client.game_state, a, 1) if unit['status'] == 'ready']
        assert client.game_state.add_movement_order_for_units(a, c, ready)
        for index in (1, 0):
            h.click_end_turn(session.game(index))
            session.step_all()
        session.step_until(lambda: host.sim_state.round_number == 3, max_steps=400)
        session.run_until_quiet()

        for gs in (client.game_state, host.game_state):
            assert _units(gs, a, 1) == []
            assert sorted(unit['type'] for unit in _units(gs, c, 1)) == ['Archer', 'Archer', 'Cavalry']
