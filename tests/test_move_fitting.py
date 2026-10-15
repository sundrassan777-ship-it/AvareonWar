# -*- coding: utf-8 -*-
"""
The simultaneous host fits each move to what can really go, instead of refusing it whole
or letting the army cap delete units - found in the FFA test game of 2026-10-14.

- A move whose unit list named a missing unit was refused whole (its surviving units
  stayed home): Blue sent 6 units at an undefended territory, a Decisive Strike killed 3
  after Blue pressed Ready, and none marched. Now the move goes with the units still there.
- Planning lets a reinforcement into a territory when a move out of it makes the room.
  When that outgoing move did not go, the reinforcements still arrived and the army cap
  deleted the excess on arrival: 36 units in that game. Now the latest reinforcements are
  shortened before anything moves and those units stay home.
- A hero ability among the round's orders (the AI's) runs after the moves were checked;
  a move whose units it took had the missing ones made up as default Swordsmen.
- The player is told which of their moves set off shortened or not at all.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import map_data  # noqa: E402
import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from game_state import GameState  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402

LIMIT = GameState.MAX_ARMIES_PER_TERRITORY


def _manager(player_is_ai=(False, False)):
    gs = GameState(num_players=len(player_is_ai), player_is_ai=list(player_is_ai),
                   player_ai_difficulty=[1] * len(player_is_ai), skip_setup_phase=True)
    sim = SimultaneousGameState(gs)
    sim.phase_manager = SimPhaseManager(sim)
    return gs, sim, sim.phase_manager


def _move(player, source, target, unit_ids):
    return {'type': 'movement', 'player_id': player, 'from_territory': source,
            'to_territory': target, 'army_count': len(unit_ids), 'unit_ids': list(unit_ids)}


def _army(count, unit_type='Swordsman', first_id=0):
    return [{'id': first_id + i, 'status': 'ready', 'order': None, 'type': unit_type,
             'xp': 0, 'level': 0} for i in range(count)]


def _units(gs, territory, player):
    return (gs.territory_garrisons.get(territory, {}).get(player) or {}).get('units', [])


def _not_adjacent(territory):
    neighbors = set(map_data.get_neighbors(territory))
    return next(t for t in sorted(map_data.get_all_territories())
                if t != territory and t not in neighbors)


def _run(pm, orders):
    """The round: validate, apply, fit and start the moves; the armies arrive."""
    pm.begin_execution(orders)
    pm._process_arrivals()


class TestShortenedNotRefused:

    def test_a_move_goes_with_the_units_still_there(self):
        """Blue's round 35: 6 units ordered, 3 struck after Ready."""
        gs, _sim, pm = _manager()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 1, _army(3, first_id=0) + _army(3, 'Cavalry', first_id=10))
        gs.territory_owners[b] = -1
        order = _move(1, a, b, [0, 1, 2, 3, 4, 5])          # 3, 4, 5 died after Ready
        valid = pm.prepare_orders({1: [order]})
        assert len(valid) == 1
        assert (valid[0]['unit_ids'], valid[0]['army_count']) == ([0, 1, 2], 3)
        assert order['unit_ids'] == [0, 1, 2, 3, 4, 5]     # the player's own order untouched

    def test_a_unit_named_twice_goes_once(self):
        gs, _sim, pm = _manager()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 1, _army(3))
        h.place(gs, b, 1)
        valid = pm.prepare_orders({1: [_move(1, a, b, [1, 1, 2])]})
        assert (valid[0]['unit_ids'], valid[0]['army_count']) == ([1, 2], 2)

    def test_a_move_with_none_of_its_units_left_is_refused(self):
        gs, _sim, pm = _manager()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 1, _army(2))
        h.place(gs, b, 1)
        assert pm.prepare_orders({1: [_move(1, a, b, [7, 8])]}) == []

    def test_the_struck_attack_takes_the_territory(self):
        gs, _sim, pm = _manager()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 1, _army(3))
        gs.territory_owners[b] = 0                          # undefended enemy land
        gs.territory_garrisons[b] = {}
        _run(pm, {1: [_move(1, a, b, [0, 1, 2, 3, 4, 5])]})
        assert gs.territory_owners[b] == 1
        assert len(_units(gs, b, 1)) == 3


class TestNoRoom:

    def test_reinforcements_behind_a_refused_move_stay_home(self):
        """Red's round 16: 15 in A, the move out of A refused, 11 sent in from B."""
        gs, _sim, pm = _manager()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 0, _army(LIMIT))
        h.place(gs, b, 0, _army(11, 'Archer'))
        refused = _move(0, a, _not_adjacent(a), list(range(LIMIT)))
        _run(pm, {0: [refused, _move(0, b, a, list(range(11)))]})
        assert len(_units(gs, a, 0)) == LIMIT
        assert len(_units(gs, b, 0)) == 11                   # nobody deleted

    def test_only_the_room_left_is_used(self):
        gs, _sim, pm = _manager()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 0, _army(LIMIT - 3))
        h.place(gs, b, 0, _army(5, 'Archer'))
        _run(pm, {0: [_move(0, b, a, [0, 1, 2, 3, 4])]})
        assert len(_units(gs, a, 0)) == LIMIT
        assert sorted(u['id'] for u in _units(gs, b, 0)) == [3, 4]   # the last two stayed

    def test_the_latest_reinforcement_gives_way_first(self):
        gs, _sim, pm = _manager()
        a, b, c = h.adjacent_triple()
        h.place(gs, a, 0, _army(LIMIT - 4))
        h.place(gs, b, 0, _army(3, 'Archer'))
        h.place(gs, c, 0, _army(3, 'Cavalry'))
        _run(pm, {0: [_move(0, b, a, [0, 1, 2]), _move(0, c, a, [0, 1, 2])]})
        assert len(_units(gs, b, 0)) == 0                    # the first move went whole
        assert len(_units(gs, c, 0)) == 2                    # the second gave way
        assert len(_units(gs, a, 0)) == LIMIT

    def test_units_kept_home_can_crowd_their_own_territory(self):
        """X -> Y is cut (Y is full), so X keeps its units - and Z -> X must fit too."""
        gs, _sim, pm = _manager()
        x, y, z = h.adjacent_triple()
        h.place(gs, y, 0, _army(LIMIT))
        h.place(gs, x, 0, _army(10))
        h.place(gs, z, 0, _army(6, 'Archer'))
        _run(pm, {0: [_move(0, x, y, [0, 1, 2, 3, 4]), _move(0, z, x, list(range(6)))]})
        assert len(_units(gs, y, 0)) == LIMIT
        assert len(_units(gs, x, 0)) == LIMIT
        assert len(_units(gs, z, 0)) == 1

    def test_attacks_are_not_shortened(self):
        gs, _sim, pm = _manager()
        a, b, c = h.adjacent_triple()
        h.place(gs, b, 0, _army(10))
        h.place(gs, c, 0, _army(10, 'Archer'))
        gs.territory_owners[a] = -1                          # neutral, empty
        gs.territory_garrisons[a] = {}
        valid = pm.prepare_orders({0: [_move(0, b, a, list(range(10))),
                                       _move(0, c, a, list(range(10)))]})
        assert [o['army_count'] for o in pm._finalize_movement_orders(valid)] == [10, 10]


class TestAbilityDuringTheRound:

    def test_units_an_ai_ability_took_are_not_made_up(self):
        """The AI's Decisive Strike runs among the round's orders, after the moves were
        checked; the move goes with the 2 units left, not 2 + 2 default Swordsmen."""
        gs, _sim, pm = _manager(player_is_ai=(False, True))
        hero, _ = h.hero_with_ability('Decisive Strike')
        home = h.spread_territories(2)[0]
        gs.territory_owners[home] = 1
        gs.buildings[home] = {0: 'Keep'}
        gs.heroes[1][hero] = {'keep_territory': home, 'keep_plot': 0, 'status': 'active'}
        gs.hero_ownership[1].add(hero)
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 0, _army(4, 'Archer'))
        h.place(gs, b, 0)
        strike = {'type': 'hero_ability', 'player_id': 1, 'hero_type': hero,
                  'ability_name': 'Decisive Strike', 'target': a}
        _run(pm, {0: [_move(0, a, b, [0, 1, 2, 3])], 1: [strike]})
        assert sorted(u['type'] for u in _units(gs, b, 0)) == ['Archer', 'Archer']


class TestNotices:

    def test_the_player_is_told_about_shortened_and_refused_moves(self, make_session):
        session = make_session(num_players=2, turn_mode='simultaneous')
        host = session.game(0)
        sim = host.sim_state
        a, b, c = h.adjacent_triple()
        far = _not_adjacent(a)
        sim.player_orders[0] = [_move(0, a, b, [0, 1, 2]), _move(0, a, c, [3]),
                                _move(0, b, a, [0]), _move(0, c, far, [0])]
        accepted = [dict(_move(0, a, b, [0, 1]), player_id=0),   # shortened
                    _move(0, b, a, [0])]                         # whole
        forced = [{'player_id': 0, 'territory': c, 'intended_target': far}]
        before = len(host.game_state.messages)
        host._report_shortened_moves(accepted, forced)
        lines = host.game_state.messages[before:]
        assert lines == [f"Player 1: Your move from {a} to {b} set off with 2 of 3 armies.",
                         f"Player 1: Your move from {a} to {c} could not set off."]


class TestMultiplayer:

    def test_blues_attack_still_marches_after_a_strike(self, make_session, monkeypatch):
        """Round 35 on two PCs: the client sends 6 units at an empty enemy territory and
        presses Ready; the host's Decisive Strike kills 3; those 3 still take it, and
        the client is told."""
        import random
        session = make_session(num_players=2, turn_mode='simultaneous')
        host_capital = h.spread_territories(2)[0]
        a, b, _c = h.adjacent_triple()
        hero, ability_index = h.hero_with_ability('Decisive Strike')

        def arrange(gs):
            gs.buildings[host_capital] = {0: 'Keep'}
            gs.heroes[0][hero] = {'keep_territory': host_capital, 'keep_plot': 0, 'status': 'active'}
            gs.hero_ownership[0].add(hero)
            h.place(gs, a, 1, _army(6))
            h.place(gs, b, 0)                                # the host's, empty
        session.on_all(arrange)
        client, host = session.game(1), session.game(0)
        assert client.game_state.add_movement_order_for_units(a, b, list(range(6)))
        h.click_end_turn(client)
        session.step_all()

        real_sample = random.sample
        monkeypatch.setattr(random, 'sample', lambda population, k: (
            list(population)[:k] if k == 3 and len(list(population)) == 6
            else real_sample(list(population), k)))
        h.cast_targeted_ability(host, hero, ability_index, a)
        session.run_until_quiet()
        h.click_end_turn(host)
        session.step_until(lambda: host.sim_state.round_number == 2, max_steps=400)
        session.run_until_quiet()

        for gs in (client.game_state, host.game_state):
            assert gs.territory_owners[b] == 1
            assert sorted(u['id'] for u in _units(gs, b, 1)) == [0, 1, 2]
        assert (f"Player 2: Your move from {a} to {b} set off with 3 of 6 armies."
                in client.game_state.messages)

    def test_a_reinforcement_with_no_room_stays_home_on_every_pc(self, make_session):
        """The client's move out of A is stopped by a crossing enemy army, so the
        reinforcements it sent into A have no room - they stay in B on every PC."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        a, b, c = h.adjacent_triple()

        def arrange(gs):
            h.place(gs, a, 1, _army(LIMIT))
            h.place(gs, b, 1, _army(5, 'Archer'))
            h.place(gs, c, 0, _army(LIMIT, 'Cavalry'))       # the host's, stronger
        session.on_all(arrange)
        client, host = session.game(1), session.game(0)
        assert client.game_state.add_movement_order_for_units(a, c, list(range(10)))
        assert client.game_state.add_movement_order_for_units(b, a, list(range(5)))
        assert host.game_state.add_movement_order_for_units(c, a, list(range(LIMIT)))
        for index in (1, 0):
            h.click_end_turn(session.game(index))
            session.step_all()
        session.step_until(lambda: host.sim_state.sim_phase != 'planning'
                           or host.sim_state.round_number == 2, max_steps=400)
        session.run_until_quiet()
        for gs in (client.game_state, host.game_state):
            assert len(_units(gs, b, 1)) == 5                # stayed home, none deleted
        assert (f"Player 2: Your move from {b} to {a} could not set off."
                in client.game_state.messages)
