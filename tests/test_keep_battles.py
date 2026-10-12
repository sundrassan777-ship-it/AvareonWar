# -*- coding: utf-8 -*-
"""
Keep battles with several attacking sides (simultaneous mode: two enemies reach the same
Keep in one round). Seen in the first multiplayer test game (2026-10-12): only the
strongest attacker fought the Keep and the other attacker's units vanished unfought.

Owner's decision: the attackers fight each other first (open-field rules), and the winner
then assaults the Keep (the two-phase Keep battle) with its survivors.

Battles are built the way simultaneous mode builds them (one army per side, keyed by team
leader, Keep bonus on the defending side's key).
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from game_state import Battle, GameState  # noqa: E402


def new_state(player_is_ai=(True, True, False, True), teams=None):
    gs = GameState(num_players=len(player_is_ai), player_is_ai=list(player_is_ai),
                   player_ai_difficulty=[1] * len(player_is_ai), skip_setup_phase=True)
    if teams is not None:
        gs.player_teams = list(teams)
    return gs


def composition(units):
    result = {}
    for unit in units:
        result[unit['type']] = result.get(unit['type'], 0) + 1
    return result


def keep_battle(gs, owner_units, sides, owner=2, keep_key=None, teams=None):
    """
    A Keep battle at a fresh territory owned by `owner` (garrison `owner_units` + Keep).
    sides: {battle key: [(player, units), ...]} - the attacking sides, and for a defending
    team its members besides the owner (simultaneous mode merges a team under its lowest
    player index). keep_key: the defending side's key (default: the owner).
    """
    _, territory, _ = h.adjacent_triple()
    h.place(gs, territory, owner, owner_units, buildings={0: 'Keep'})
    battle = Battle(territory)
    battle.original_owner = owner
    keep_key = owner if keep_key is None else keep_key
    members = {keep_key: [owner]}
    if owner_units:
        battle.add_army(keep_key, len(owner_units), composition(owner_units))
    for key, players in sides.items():
        for player, units in players:
            gs.territory_garrisons[territory][player] = {
                'unmoved': 0, 'moved': len(units), 'units': units}
            battle.add_army(key, len(units), composition(units))
            members.setdefault(key, []).append(player)
    battle.keep_bonus = 2
    battle.keep_bonus_player = keep_key
    battle.original_garrison = len(owner_units)
    battle.team_members_map = members
    battle.allied_defenders = [p for key, ps in members.items() for p in ps if p != key]
    battle.attackers = [key for key in sides if key != keep_key]
    gs.pending_battles = [battle]
    return territory, battle


def units_of(gs, territory, player):
    return [u['type'] for u in (gs.territory_garrisons.get(territory, {}).get(player) or {}).get('units', [])]


def log_text(gs):
    return "\n".join(gs.messages)


class TestAttackersFightFirst:

    def test_the_weaker_attacker_fights_before_the_keep_is_assaulted(self):
        """4 Swordsmen and 3 Swordsmen attack 1 Swordsman + Keep. The weaker attacker used
        to vanish and the stronger took the Keep; their fight now costs the winner two
        units, and the Keep holds."""
        gs = new_state()
        territory, _ = keep_battle(gs, h.units('Swordsman'), {
            0: [(0, h.units('Swordsman', 'Swordsman', 'Swordsman', 'Swordsman', status='moved'))],
            3: [(3, h.units('Swordsman', 'Swordsman', 'Swordsman', status='moved'))]})
        assert gs.resolve_battle(0, rng=random.Random(1))
        assert "fight each other first" in log_text(gs)
        assert gs.territory_owners[territory] == 2               # the Keep held
        assert units_of(gs, territory, 0) == [] and units_of(gs, territory, 3) == []
        assert gs.buildings[territory] == {0: 'Keep'}

    def test_the_winner_of_their_fight_takes_the_keep(self):
        gs = new_state()
        strong = h.units(*['Swordsman'] * 8, status='moved')
        territory, battle = keep_battle(gs, h.units('Swordsman'), {
            0: [(0, h.units('Swordsman', 'Swordsman', status='moved'))],
            3: [(3, strong)]})
        assert gs.resolve_battle(0, rng=random.Random(1))
        # 8 vs 2: one loss; then 1 Swordsman (one more loss) and the Keep (2 armies)
        assert gs.territory_owners[territory] == 3
        assert units_of(gs, territory, 3) == ['Swordsman'] * 4
        assert units_of(gs, territory, 0) == []
        assert battle.keep_prefight_winner == 3 and battle.keep_prefight_losers == [0]

    def test_the_battle_report_names_the_attacker_that_assaulted_the_keep(self):
        gs = new_state()
        keep_battle(gs, h.units('Swordsman'), {
            0: [(0, h.units('Swordsman', 'Swordsman', status='moved'))],
            3: [(3, h.units(*['Swordsman'] * 8, status='moved'))]})
        gs.resolve_battle(0, rng=random.Random(1))
        [report] = gs.last_battle_reports
        assert report['attacker'] == 3 and report['defender'] == 2

    def test_the_keep_gives_no_credit_for_attackers_it_never_fought(self):
        gs = new_state()
        keep_battle(gs, h.units('Swordsman'), {
            0: [(0, h.units('Swordsman', 'Swordsman', 'Swordsman', 'Swordsman', status='moved'))],
            3: [(3, h.units('Swordsman', 'Swordsman', 'Swordsman', status='moved'))]})
        gs.resolve_battle(0, rng=random.Random(1))
        # Their fight: Player 1 killed Player 4's 3 units and lost 2 to them. At the Keep
        # Player 1's 2 survivors killed the garrison's Swordsman, then the Keep held.
        # The defender used to be credited with all 4 of Player 1's units.
        assert gs.player_stats[0].get('units_killed', 0) == 3 + 1
        assert gs.player_stats[3].get('units_killed', 0) == 2
        assert gs.player_stats[2].get('units_killed', 0) == 2

    def test_a_tie_between_attackers_is_rolled_with_the_battle_seed(self):
        """Equal attackers roll dice - from the battle's random source, so every PC
        replaying the battle from its seed gets the same result."""
        outcomes = []
        for _ in range(2):
            gs = new_state()
            territory, _ = keep_battle(gs, h.units('Swordsman'), {
                0: [(0, h.units('Swordsman', 'Swordsman', 'Swordsman', status='moved'))],
                3: [(3, h.units('Swordsman', 'Swordsman', 'Swordsman', status='moved'))]})
            gs.resolve_battle(0, rng=random.Random(7))
            assert "rolls:" in log_text(gs)
            outcomes.append((gs.territory_owners[territory],
                             {p: units_of(gs, territory, p) for p in range(4)}))
        assert outcomes[0] == outcomes[1]


class TestTeamGames:

    def test_the_defending_teams_leader_is_not_an_attacker(self):
        """Simultaneous mode keys a battle by team leader: the owner (2) defends with an
        ally (0, lower index), so the defending side is 0. It was counted as an attacker
        and "assaulted" its own team's Keep, which then went to the ally."""
        gs = new_state(player_is_ai=(True, True, False, True), teams=(0, 1, 0, 3))
        territory, _ = keep_battle(
            gs, h.units('Swordsman', 'Swordsman'),
            {0: [(0, h.units('Swordsman', 'Swordsman'))],
             1: [(1, h.units('Swordsman', 'Swordsman', status='moved'))]},
            keep_key=0)
        gs.resolve_battle(0, rng=random.Random(1))
        assert "fight each other first" not in log_text(gs)
        assert gs.territory_owners[territory] == 2
        assert gs.buildings[territory] == {0: 'Keep'}

    def test_allied_attackers_are_one_side(self):
        """Two allies attacking together are one army (merged under their team leader):
        they never fight each other."""
        gs = new_state(teams=(0, 3, 2, 3))
        territory, _ = keep_battle(gs, h.units('Swordsman'), {
            1: [(1, h.units(*['Swordsman'] * 4, status='moved')),
                (3, h.units(*['Swordsman'] * 4, status='moved'))]})
        gs.resolve_battle(0, rng=random.Random(1))
        assert "fight each other first" not in log_text(gs)
        assert gs.territory_owners[territory] == 1
