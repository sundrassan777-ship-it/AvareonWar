# -*- coding: utf-8 -*-
"""
Multiplayer groundwork that needs no network (multiplayer audit, Phase 3):
- network/state_snapshot.py: one whole-game snapshot format (round trip, what it
  keeps per PC, what it clears),
- Decisive Strike / Valorous Charge accept the caster's random picks, so every PC
  removes / moves the same units,
- default units get integer ids (string ids crashed the next arrival).
"""

import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from game_state import GameState  # noqa: E402
from network.state_snapshot import SNAPSHOT_VERSION, apply_snapshot, build_snapshot  # noqa: E402


def new_state():
    return GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[1, 1],
                     skip_setup_phase=True, network_mode=True, local_player_index=0)


def wire(data):
    """What a network round trip does to a snapshot (JSON)."""
    return json.loads(json.dumps(data))


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def busy_state():
    """A mid-game state touching most kinds of data a snapshot must carry."""
    gs = new_state()
    home, away = h.spread_territories(2)
    a, b, c = h.adjacent_triple()
    h.place(gs, home, 0, h.units('Swordsman', 'Archer', level=2, xp=70),
            buildings={0: 'Barracks', 1: 'Keep'})
    h.place(gs, away, 1, h.units('Pikeman'))
    h.place(gs, a, 0, h.units('Cavalry', 'Cavalry'))
    h.place(gs, b, 0)
    gs.under_construction[home] = {2: ('Farm', 2, 30)}
    gs.training_queue[home] = {0: [('Archer', 1, 20)]}
    gs.heroes[0]['Evain Nithieln'] = {'keep_territory': home, 'keep_plot': 1, 'status': 'active'}
    gs.hero_ownership[0].add('Evain Nithieln')
    gs.player_gold = [321, 45]
    gs.turn_number = 7
    gs.player_command_limit[0] = 95
    gs.player_stats[0]['xp_earned'] = 40
    assert gs.add_movement_order_for_units(a, b, [0])
    gs.chat_messages.append(('12:00:00', 0, 'mine', 'all'))
    gs.messages.append('mine too')
    return gs, (home, away, a, b)


class TestSnapshot:

    def test_round_trip_reproduces_the_state(self):
        source, _ = busy_state()
        snapshot = wire(build_snapshot(source))
        target = new_state()
        apply_snapshot(target, snapshot)
        assert wire(build_snapshot(target)) == snapshot

    def test_chat_and_action_log_stay_per_pc(self):
        source, _ = busy_state()
        snapshot = wire(build_snapshot(source))
        assert 'chat_messages' not in snapshot and 'messages' not in snapshot
        target = new_state()
        target.chat_messages.append(('11:11:11', 1, 'local only', 'all'))
        apply_snapshot(target, snapshot)
        assert target.chat_messages == [('11:11:11', 1, 'local only', 'all')]

    def test_carries_ai_takeover_and_clears_work_in_progress(self):
        source, (home, *_rest) = busy_state()
        source.player_is_ai = [False, False]               # e.g. after a takeover elsewhere
        snapshot = wire(build_snapshot(source))
        target = new_state()
        target.pending_battles = [h.battle_at(home, owner=0, attacker=1)]
        target.ready_to_advance_turn = True
        apply_snapshot(target, snapshot)
        assert target.player_is_ai == [False, False]
        assert target.pending_battles == [] and not target.ready_to_advance_turn
        assert target.active_animations == [] and target.pending_arrivals == []

    def test_income_follows_the_snapshot(self):
        source, (home, away, *_rest) = busy_state()
        target = new_state()
        apply_snapshot(target, wire(build_snapshot(source)))
        before = target.calculate_player_income(1)          # now cached
        source.territory_owners[home] = 1
        apply_snapshot(target, wire(build_snapshot(source)))
        assert target.calculate_player_income(1) != before

    def test_rejects_unknown_formats(self):
        with pytest.raises(ValueError):
            apply_snapshot(new_state(), {'snapshot_version': SNAPSHOT_VERSION + 1})
        with pytest.raises(ValueError):
            apply_snapshot(new_state(), {'territory_owners': {}})

    def test_size_stays_small(self):
        source, _ = busy_state()
        assert len(json.dumps(build_snapshot(source))) < 200_000


# ---------------------------------------------------------------------------
# Random picks of hero abilities
# ---------------------------------------------------------------------------

def strike_setup():
    """Two identical states: player 1 holds 8 mixed units at `target`."""
    states = []
    target = h.spread_territories(2)[1]
    for _ in range(2):
        gs = new_state()
        h.place(gs, target, 1, h.units('Swordsman', 'Swordsman', 'Archer', 'Archer',
                                       'Pikeman', 'Pikeman', 'Cavalry', 'Cavalry'))
        states.append(gs)
    return states, target


class TestAbilityPicks:

    def test_decisive_strike_removes_the_casters_picks(self):
        (caster, receiver), target = strike_setup()
        random.seed(1)
        assert caster.execute_decisive_strike(target, 0)[0]
        picks = wire(caster._last_decisive_strike_removed)
        random.seed(99)                                    # the receiver rolls differently
        assert receiver.execute_decisive_strike(target, 0, pre_selected_units=picks)[0]
        assert (h.garrison_summary(caster, target) == h.garrison_summary(receiver, target))
        assert len(caster.territory_garrisons[target][1]['units']) == 4

    def test_missing_pick_gets_a_stand_in_of_the_same_type(self):
        (caster, receiver), target = strike_setup()
        assert caster.execute_decisive_strike(target, 0)[0]
        picks = wire(caster._last_decisive_strike_removed)
        picks[0] = [picks[0][0], 999, picks[0][2]]         # this unit id does not exist here
        assert receiver.execute_decisive_strike(target, 0, pre_selected_units=picks)[0]
        assert h.garrison_summary(caster, target) == h.garrison_summary(receiver, target)

    def test_valorous_charge_moves_the_casters_picks(self):
        hero = 'Serthus Diarcess'
        keep, target = h.spread_territories(2)
        states = []
        for _ in range(2):
            gs = new_state()
            h.place(gs, keep, 0, h.units('Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Archer'),
                    buildings={0: 'Keep'})
            gs.heroes[0][hero] = {'keep_territory': keep, 'keep_plot': 0, 'status': 'active'}
            gs.hero_ownership[0].add(hero)
            # Only 2 places left at the target: the ability has to choose
            h.place(gs, target, 0, h.units(*(['Swordsman'] * (gs.MAX_ARMIES_PER_TERRITORY - 2))))
            states.append(gs)
        caster, receiver = states
        random.seed(5)
        assert caster.execute_valorous_charge(target, 0)[0]
        picks = wire(caster._last_valorous_charge_moved)
        assert len(picks) == 2
        random.seed(77)
        assert receiver.execute_valorous_charge(target, 0, pre_selected_units=picks)[0]
        for territory in (keep, target):
            assert h.garrison_summary(caster, territory) == h.garrison_summary(receiver, territory)


# ---------------------------------------------------------------------------
# Default units
# ---------------------------------------------------------------------------

def test_default_units_get_integer_ids():
    gs = new_state()
    territory = h.spread_territories(2)[0]
    gs.set_garrison_armies(territory, 0, unmoved=2, moved=1)       # no unit list -> defaults
    ids = [u['id'] for u in gs.territory_garrisons[territory][0]['units']]
    assert ids == [0, 1, 2]
    assert max(ids) + 1 == 3                                      # what arrivals compute
