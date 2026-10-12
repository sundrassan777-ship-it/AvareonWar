# -*- coding: utf-8 -*-
"""
Team battles - found 2026-10-12 while changing Keep battles, fixed on the owner's request.

Both turn modes key a battle by TEAM LEADER (the lowest player index of each team present)
with the allies' armies merged in, and the battle's result treated that key as one player:
- a joint defence where the owner's ally has the lower index handed the territory to the
  ally - the owner's buildings were destroyed and the owner's units lost;
- a winning team's other members lost all their units (survivors came from the leader's
  own units only);
- defending losses could be booked on the attackers' units, and a simultaneous defending
  team's strength at a Keep was cut to the owner's own units;
- the owner got no Battle Report (its ally was taken for the attacker).

Now each ally keeps its own surviving units: a defending team loses its allies' units first
and the owner's last (the existing rule), an attacking team shares its losses in proportion
to army size (SimAllianceHandler's design), and a defending team that holds keeps the
territory with its owner. Battles are built by the game's own code for each mode.
"""

import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from game_state import GameState  # noqa: E402
from simultaneous import SimPhaseManager, SimultaneousGameState  # noqa: E402



def contested():
    """The contested territory (the map is loaded per test, by conftest)."""
    return h.adjacent_triple()[1]


def new_state(teams, humans=()):
    n = len(teams)
    gs = GameState(num_players=n, player_is_ai=[p not in humans for p in range(n)],
                   player_ai_difficulty=[1] * n, skip_setup_phase=True)
    gs.player_teams = list(teams)
    gs.phase = 'playing'
    return gs


def garrison(gs, player, units):
    gs.territory_garrisons.setdefault(contested(), {})[player] = {
        'unmoved': sum(1 for u in units if u['status'] == 'ready'),
        'moved': sum(1 for u in units if u['status'] == 'moved'), 'units': units}


def sim_battle(gs, players):
    """The battle simultaneous mode builds for these players' garrisons in T."""
    sim = SimultaneousGameState(gs)
    pm = SimPhaseManager(sim)
    sim.phase_manager = pm
    pm.pending_battles = [pm._create_battle_conflict(contested(), list(players))]
    pm._setup_battles_for_ui()
    return gs.pending_battles[0]


def sequential_battle(gs, attacker, units):
    """The battle sequential mode builds when `attacker`'s units arrive in T."""
    composition = {}
    for unit in units:
        composition[unit['type']] = composition.get(unit['type'], 0) + 1
    gs.current_player = attacker
    gs.turn_phase = 'execution'
    gs.pending_arrivals = [SimpleNamespace(to_territory=contested(), player=attacker,
                                           army_count=len(units),
                                           composition=composition, units=units)]
    gs._process_arrivals()
    return gs.pending_battles[0]


def types(gs, player):
    garrisons = gs.territory_garrisons.get(contested(), {})
    return sorted(u['type'] for u in (garrisons.get(player) or {}).get('units', []))


class TestJointDefence:
    """Owner 2 defends T with ally 0 (the lower index - the team's key) against 1."""

    def _defence(self, sequential=False, humans=()):
        gs = new_state(teams=(0, 1, 0), humans=humans)
        h.place(gs, contested(), 2, h.units('Swordsman', 'Swordsman', 'Swordsman'), buildings={0: 'Farm'})
        garrison(gs, 0, h.units('Pikeman', 'Pikeman', 'Pikeman'))
        attack = h.units('Archer', status='moved')
        if sequential:
            battle = sequential_battle(gs, 1, attack)
        else:
            garrison(gs, 1, attack)
            battle = sim_battle(gs, [2, 0, 1])
        assert 0 in battle.armies and 2 not in battle.armies   # keyed by the ally
        return gs, battle

    def test_the_territory_stays_with_its_owner(self):
        gs, _ = self._defence()
        gs.resolve_battle(0, rng=random.Random(1))
        assert gs.territory_owners[contested()] == 2
        assert gs.buildings.get(contested()) == {0: 'Farm'}

    def test_each_defender_keeps_their_own_survivors_allies_lose_first(self):
        gs, battle = self._defence()
        gs.resolve_battle(0, rng=random.Random(1))
        assert types(gs, 1) == []
        assert types(gs, 2) == ['Swordsman'] * 3             # the owner loses last
        survivors = len(types(gs, 0)) + len(types(gs, 2))
        assert survivors == battle.surviving_armies

    def test_sequential_turns_too(self):
        gs, _ = self._defence(sequential=True)
        gs.resolve_battle(0, rng=random.Random(1))
        assert gs.territory_owners[contested()] == 2
        assert gs.buildings.get(contested()) == {0: 'Farm'}
        assert types(gs, 2) == ['Swordsman'] * 3 and types(gs, 1) == []

    def test_the_owner_gets_the_battle_report(self):
        gs, _ = self._defence(humans=(2,))
        gs.resolve_battle(0, rng=random.Random(1))
        [report] = gs.last_battle_reports
        assert (report['defender'], report['attacker'], report['held']) == (2, 1, True)
        assert report['unit_breakdown']['Swordsman']['original'] == 3


class TestJointAttack:

    def test_allies_share_their_losses_and_keep_their_own_survivors(self):
        """1 and 3 (allies) take T from 2: one loss, shared by army size (4 : 2)."""
        gs = new_state(teams=(0, 1, 2, 1))
        h.place(gs, contested(), 2, h.units('Swordsman', 'Swordsman'))
        garrison(gs, 1, h.units(*['Swordsman'] * 4, status='moved'))
        garrison(gs, 3, h.units('Swordsman', 'Swordsman', status='moved'))
        battle = sim_battle(gs, [2, 1, 3])
        gs.resolve_battle(0, rng=random.Random(1))
        assert gs.territory_owners[contested()] == 1                   # the team's key (it then chooses)
        assert types(gs, 1) == ['Swordsman'] * 3
        assert types(gs, 3) == ['Swordsman'] * 2
        assert battle.surviving_armies == 5


class TestDefendersAtAKeep:

    def test_a_defending_team_fights_with_all_its_units(self):
        """Simultaneous: owner 2 (3) + ally 0 (3) hold a Keep against 1 (2). The team's
        strength was cut to the owner's 3 units, and its losses were not the allies'."""
        gs = new_state(teams=(0, 1, 0))
        h.place(gs, contested(), 2, h.units('Swordsman', 'Swordsman', 'Swordsman'), buildings={0: 'Keep'})
        garrison(gs, 0, h.units('Swordsman', 'Swordsman', 'Swordsman'))
        garrison(gs, 1, h.units('Swordsman', 'Swordsman', status='moved'))
        battle = sim_battle(gs, [2, 0, 1])
        assert battle.original_garrison == 6
        gs.resolve_battle(0, rng=random.Random(1))
        # 6 against 2: one loss, an ally's
        assert gs.territory_owners[contested()] == 2
        assert types(gs, 0) == ['Swordsman'] * 2 and types(gs, 2) == ['Swordsman'] * 3
        assert "Ally (Player 2)" not in "\n".join(gs.messages)   # the attacker is no ally

    def test_sequential_turns_hold_it_as_a_keep_too(self):
        """Sequential mode only made it a Keep battle when the owner was the team's key."""
        gs = new_state(teams=(0, 1, 0))
        h.place(gs, contested(), 2, h.units('Swordsman', 'Swordsman', 'Swordsman'),
                buildings={0: 'Keep'})
        garrison(gs, 0, h.units('Swordsman', 'Swordsman', 'Swordsman'))
        battle = sequential_battle(gs, 1, h.units('Swordsman', 'Swordsman', status='moved'))
        assert (battle.keep_bonus_player, battle.keep_bonus, battle.original_garrison) == (0, 2, 6)
        gs.resolve_battle(0, rng=random.Random(1))
        assert gs.territory_owners[contested()] == 2
        assert types(gs, 0) == ['Swordsman'] * 2 and types(gs, 2) == ['Swordsman'] * 3


class TestCreditAndAbilities:

    def _joint_attack(self, gs, attackers):
        h.place(gs, contested(), 2, h.units('Swordsman', 'Swordsman'))
        for player, count in attackers.items():
            garrison(gs, player, h.units(*['Swordsman'] * count, status='moved'))
        return sim_battle(gs, [2] + list(attackers))

    def test_kills_are_credited_to_each_ally_by_their_units(self):
        gs = new_state(teams=(0, 1, 2, 1))
        self._joint_attack(gs, {1: 4, 3: 2})
        gs.resolve_battle(0, rng=random.Random(1))
        # 2 kills shared 4 : 2 (largest remainder); the defender killed the team's 1 loss
        assert gs.player_stats[1].get('units_killed', 0) == 1
        assert gs.player_stats[3].get('units_killed', 0) == 1
        assert gs.player_stats[2].get('units_killed', 0) == 1

    def test_a_losing_ally_gets_scavenge_the_fallen(self):
        """Only the losing side's key used to be checked for its abilities."""
        gs = new_state(teams=(0, 1, 2, 1))
        h.place(gs, contested(), 2, h.units(*['Swordsman'] * 6))
        garrison(gs, 1, h.units('Swordsman', status='moved'))
        garrison(gs, 3, h.units('Swordsman', status='moved'))
        gs.heroes[3]['Darius Brennhen'] = {'keep_territory': h.spread_territories(4)[3],
                                           'keep_plot': 0, 'status': 'active'}
        gold = gs.player_gold[3]
        sim_battle(gs, [2, 1, 3])
        gs.resolve_battle(0, rng=random.Random(1))
        assert gs.territory_owners[contested()] == 2
        assert gs.player_gold[3] == gold + 30
