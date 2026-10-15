# -*- coding: utf-8 -*-
"""
Hero abilities taking units that are queued in a planned move - found in the FFA test game
of 2026-10-14.

Decisive Strike, Royal Charisma and Valorous Charge lowered the garrison's 'moved' counter
for every unit that was not 'ready'. A unit queued in a planned move is 'ordered', which
counts as unmoved, so 'unmoved' stayed too high. The army banner is drawn from those
counters: Red struck Green's 12 units in Duchy of Daurels (round 28) while Green had
queued them - Green's PC showed 11 armies (3 flags) where 6 units were left.

The units also stayed in the planned moves, and the simultaneous host refused a move
naming a dead unit, its surviving units included (Green's move of unit #6). Now
GarrisonMixin._take_unit() keeps the counters right and takes the unit out of its move;
a move left empty, or a two-hop (Captain) move left without its Captain, is cancelled.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
from game_state import GameState, MovementOrder  # noqa: E402

TYPES = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']


def new_state():
    return GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1],
                     skip_setup_phase=True)


def army(count):
    return h.units(*[TYPES[i % len(TYPES)] for i in range(count)])


def garrison(gs, territory, player):
    return gs.territory_garrisons[territory][player]


def ids(gs, territory, player):
    return [unit['id'] for unit in garrison(gs, territory, player)['units']]


def counted(gs, territory, player):
    """What the banner reads: the garrison's counters."""
    data = garrison(gs, territory, player)
    return data['unmoved'] + data['moved']


def picks(gs, territory, player, unit_ids):
    """The caster's picks as they travel over the network: [owner, id, type]."""
    by_id = {unit['id']: unit for unit in garrison(gs, territory, player)['units']}
    return [[player, unit_id, by_id[unit_id]['type']] for unit_id in unit_ids]


def orders_from(gs, territory):
    return [order for order in gs.movement_orders if order.from_territory == territory]


def green_round_28(gs):
    """Player 1 holds 12 units in A and has queued two moves out of it."""
    a, b, c = h.adjacent_triple()
    h.place(gs, a, 1, army(12))
    h.place(gs, b, 1)
    h.place(gs, c, 1)
    assert gs.add_movement_order_for_units(a, b, [0, 1, 2, 3, 4], player=1)
    assert gs.add_movement_order_for_units(a, c, [5], player=1)
    return a, b, c


class TestDecisiveStrike:

    def test_counters_follow_the_units_when_queued_units_are_struck(self):
        gs = new_state()
        a, _b, _c = green_round_28(gs)
        assert gs.execute_decisive_strike(
            a, 0, pre_selected_units=picks(gs, a, 1, [0, 1, 5, 6, 7, 8]))[0]
        assert len(ids(gs, a, 1)) == 6
        assert counted(gs, a, 1) == 6                       # was 9: the banner's strength
        assert gs.get_territory_total_armies(a) == 6

    def test_struck_units_leave_their_planned_moves(self):
        gs = new_state()
        a, b, c = green_round_28(gs)
        assert gs.execute_decisive_strike(
            a, 0, pre_selected_units=picks(gs, a, 1, [0, 1, 5, 6, 7, 8]))[0]
        moves = orders_from(gs, a)
        assert [(order.to_territory, order.unit_ids, order.army_count) for order in moves] == [
            (b, [2, 3, 4], 3)]                               # the move to C lost its only unit
        statuses = {unit['id']: unit['status'] for unit in garrison(gs, a, 1)['units']}
        assert statuses == {2: 'ordered', 3: 'ordered', 4: 'ordered',
                            9: 'ready', 10: 'ready', 11: 'ready'}
        assert all(unit['order'] is moves[0] for unit in garrison(gs, a, 1)['units']
                   if unit['status'] == 'ordered')

    def test_ready_and_moved_units_are_counted_as_before(self):
        gs = new_state()
        a, _b, _c = h.adjacent_triple()
        h.place(gs, a, 1, h.units('Swordsman', 'Archer', 'Pikeman', 'Cavalry')
                + [dict(unit, id=unit['id'] + 4) for unit in
                   h.units('Swordsman', 'Archer', 'Pikeman', 'Cavalry', status='moved')])
        assert gs.execute_decisive_strike(a, 0, pre_selected_units=picks(gs, a, 1, [0, 1, 4, 5]))[0]
        data = garrison(gs, a, 1)
        assert (data['unmoved'], data['moved']) == (2, 2)

    def test_the_selection_list_a_move_was_made_from_is_left_alone(self):
        """A move made from the army panel keeps the panel's own list as its unit_ids."""
        gs = new_state()
        a, b, _c = h.adjacent_triple()
        h.place(gs, a, 1, army(4))
        h.place(gs, b, 1)
        selection = [0, 1, 2]
        assert gs.add_movement_order_for_units(a, b, selection, player=1)
        assert gs.execute_decisive_strike(a, 0, pre_selected_units=picks(gs, a, 1, [0, 3]))[0]
        assert orders_from(gs, a)[0].unit_ids == [1, 2]
        assert selection == [0, 1, 2]


class TestTwoHopMoves:

    def _two_hop(self, struck):
        """Player 1's Captain #0 leads Swordsman #1 on a two-hop move out of A."""
        gs = new_state()
        a, b, c = h.adjacent_triple()
        h.place(gs, a, 1, h.units('Captain', 'Swordsman', 'Archer', 'Pikeman'))
        order = MovementOrder(a, c, 2, 1, unit_ids=[0, 1], intermediate_territory=b)
        gs.movement_orders.append(order)
        for unit in garrison(gs, a, 1)['units'][:2]:
            unit['status'] = 'ordered'
            unit['order'] = order
        assert gs.execute_decisive_strike(a, 0, pre_selected_units=picks(gs, a, 1, struck))[0]
        return gs, a, order

    def test_a_two_hop_move_that_lost_its_captain_is_cancelled(self):
        gs, a, order = self._two_hop(struck=[0, 2])
        assert order not in gs.movement_orders
        swordsman = next(u for u in garrison(gs, a, 1)['units'] if u['id'] == 1)
        assert swordsman['status'] == 'ready' and swordsman['order'] is None
        assert counted(gs, a, 1) == 2

    def test_a_two_hop_move_that_kept_its_captain_goes_on(self):
        gs, a, order = self._two_hop(struck=[1, 2])
        assert order in gs.movement_orders
        assert (order.unit_ids, order.army_count) == ([0], 1)


class TestRoyalCharismaAndValorousCharge:

    def test_royal_charisma_steals_queued_units_cleanly(self):
        gs = new_state()
        a, b, _c = h.adjacent_triple()
        keep = h.spread_territories(2)[0]
        h.place(gs, keep, 0, h.units('Swordsman'), buildings={0: 'Keep'})
        gs.heroes[0]['Aidam Narn'] = {'keep_territory': keep, 'keep_plot': 0, 'status': 'active'}
        gs.hero_ownership[0].add('Aidam Narn')
        h.place(gs, a, 1, army(6))
        h.place(gs, b, 1)
        assert gs.add_movement_order_for_units(a, b, [0, 1, 2], player=1)
        stolen = [tuple(pick) for pick in picks(gs, a, 1, [0, 1, 3, 4, 5])]
        assert gs.execute_royal_charisma(a, 0, pre_selected_unit_ids=stolen)[0]
        assert ids(gs, a, 1) == [2]
        assert counted(gs, a, 1) == 1                       # was 3
        assert [(o.unit_ids, o.army_count) for o in orders_from(gs, a)] == [([2], 1)]

    def test_valorous_charge_takes_units_out_of_the_casters_moves(self):
        """The caster had queued Keep units while planning, then cast the charge."""
        gs = new_state()
        keep, b, target = h.adjacent_triple()
        hero = 'Serthus Diarcess'
        h.place(gs, keep, 0, army(5), buildings={0: 'Keep'})
        gs.heroes[0][hero] = {'keep_territory': keep, 'keep_plot': 0, 'status': 'active'}
        gs.hero_ownership[0].add(hero)
        h.place(gs, b, 0)
        h.place(gs, target, 0, h.units(*(['Swordsman'] * (gs.MAX_ARMIES_PER_TERRITORY - 2))))
        assert gs.add_movement_order_for_units(keep, b, [0, 1, 2], player=0)
        assert gs.execute_valorous_charge(
            target, 0, pre_selected_units=picks(gs, keep, 0, [0, 3]))[0]
        assert sorted(ids(gs, keep, 0)) == [1, 2, 4]
        assert counted(gs, keep, 0) == 3                    # was 4
        assert [(o.unit_ids, o.army_count) for o in orders_from(gs, keep)] == [([1, 2], 2)]


class TestMultiplayer:

    def test_a_strike_on_a_queued_army_keeps_the_rest_of_the_move(self, make_session, monkeypatch):
        """Green's round 28: the host strikes a client's army the client has queued. The
        client's banner shows what is left, and the units that survive still march."""
        session = make_session(num_players=2, turn_mode='simultaneous')
        host_capital = h.spread_territories(2)[0]
        a, b, c = h.adjacent_triple()
        hero, ability_index = h.hero_with_ability('Decisive Strike')

        def arrange(gs):
            gs.buildings[host_capital] = {0: 'Keep'}
            gs.heroes[0][hero] = {'keep_territory': host_capital, 'keep_plot': 0, 'status': 'active'}
            gs.hero_ownership[0].add(hero)
            h.place(gs, a, 1, army(12))
            h.place(gs, b, 1)
            h.place(gs, c, 1)
        session.on_all(arrange)
        client, host = session.game(1), session.game(0)
        assert client.game_state.add_movement_order_for_units(a, b, [0, 1, 2, 3, 4])
        assert client.game_state.add_movement_order_for_units(a, c, [5])

        real_sample = random.sample

        def strike_picks(population, k):
            """The host 'rolls' units 0, 1, 5, 6, 7, 8 of the client's army."""
            items = list(population)
            if k == 6 and len(items) == 12:
                return [items[i] for i in (0, 1, 5, 6, 7, 8)]
            return real_sample(items, k)
        monkeypatch.setattr(random, 'sample', strike_picks)
        h.cast_targeted_ability(host, hero, ability_index, a)
        session.run_until_quiet()

        gs = client.game_state
        assert len(ids(gs, a, 1)) == 6 and counted(gs, a, 1) == 6
        assert [(o.to_territory, o.unit_ids) for o in gs.movement_orders] == [(b, [2, 3, 4])]

        for index in (1, 0):
            h.click_end_turn(session.game(index))
            session.step_all()
        session.step_until(lambda: host.sim_state.round_number == 2, max_steps=400)
        session.run_until_quiet()
        for state in (client.game_state, host.game_state):
            assert sorted(ids(state, b, 1)) == [0, 1, 2]     # the three survivors arrived
            assert len(ids(state, a, 1)) == 3
