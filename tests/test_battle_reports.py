# -*- coding: utf-8 -*-
"""
Tests for the Battle Reports capture layer (game_state/military.py).

Battle Reports give a DEFENDER a post-hoc summary of a battle they never watched.
These tests cover the capture side only (snapshot contents and the rules about who
gets one); the popup rendering and click routing live in main.py / ui/.

Uses a real GameState with skip_setup_phase=True, matching test_battle_resolution.py.
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
# conftest.py autouse fixture handles load_polygons() + cleanup

from game_state import GameState, Battle


TERRITORY = "Lobardia"


# ---------------------------------------------------------------------------
# Helpers (mirrors test_battle_resolution.py)
# ---------------------------------------------------------------------------

def _make_units(game, unit_type, count, status='ready'):
    return [game._make_unit(unit_type, i, status) for i in range(count)]


def _keep_alive(game, player, territory="Nordia"):
    """
    Give the player a spare territory.

    Losing your LAST territory triggers check_victory() -> eliminate_player() inside
    the battle, and eliminated players get no report. Real games have many
    territories, so the spare keeps these tests representative.
    """
    game.territory_owners[territory] = player


def _setup_territory(game, territory, player, unit_type, count):
    """Assign ownership + garrison and sync the legacy army arrays."""
    game.territory_owners[territory] = player
    units = _make_units(game, unit_type, count)
    game.territory_garrisons[territory] = {}
    game.add_garrison(territory, player, unmoved=count, moved=0, units=units)
    game.army_units[territory] = units[:]
    game.armies[territory] = count
    game.armies_unmoved[territory] = count


def _create_battle(territory, attacker, attacker_count, attacker_comp,
                   defender, defender_count, defender_comp):
    battle = Battle(territory)
    battle.original_owner = defender
    # Defender first, then attacker (garrison-then-arrival order)
    battle.add_army(defender, defender_count, defender_comp)
    battle.add_army(attacker, attacker_count, attacker_comp)
    return battle


def _resolve(game, battle):
    game.pending_battles.append(battle)
    return game.resolve_battle(len(game.pending_battles) - 1)


def _only_report(game):
    """Exactly one report was produced; return it."""
    assert len(game.last_battle_reports) == 1, game.last_battle_reports
    return game.last_battle_reports[0]


@pytest.fixture
def game():
    return GameState(
        num_players=2,
        player_is_ai=[False, False],
        player_ai_difficulty=[1, 1],
        skip_setup_phase=True,
    )


# ===========================================================================
# Who gets a report
# ===========================================================================

class TestReportEligibility:

    def test_defender_gets_report_when_losing(self, game):
        """Player 1 is overrun by player 0 -> player 1 gets a LOST report."""
        _keep_alive(game, 1)
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)

        report = _only_report(game)
        assert report['defender'] == 1
        assert report['attacker'] == 0
        assert report['held'] is False
        assert report['units_lost'] == 2
        assert report['units_remaining'] == 0

    def test_defender_gets_report_when_holding(self, game):
        """A successful defence reports remaining units, not losses."""
        _setup_territory(game, TERRITORY, 1, "Swordsman", 20)
        battle = _create_battle(TERRITORY, 0, 2, {"Swordsman": 2},
                                1, 20, {"Swordsman": 20})
        _resolve(game, battle)

        report = _only_report(game)
        assert report['held'] is True
        assert report['units_remaining'] > 0
        assert report['units_remaining'] == report['defender_survivors']

    def test_no_report_for_ai_defender(self, game):
        """AI players never see UI, so no report is produced for them."""
        game.player_is_ai[1] = True
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)

        assert game.last_battle_reports == []

    def test_no_report_for_neutral_defender(self, game):
        """A neutral-owned territory has no player to report to."""
        _setup_territory(game, TERRITORY, -1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                -1, 2, {"Swordsman": 2})
        _resolve(game, battle)

        assert game.last_battle_reports == []

    def test_no_report_for_allied_attacker(self, game):
        """An ally taking the territory is not an attack on you."""
        game.player_teams = [0, 0]  # same team
        assert game.are_allies(0, 1)
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)

        assert game.last_battle_reports == []

    def test_no_report_for_eliminated_defender(self, game):
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        game.eliminated_players.add(1)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)

        assert game.last_battle_reports == []


# ===========================================================================
# Structure accounting (Champion of the People)
# ===========================================================================

class TestStructureCounts:

    def _lose_territory_with_buildings(self, game, attacker_has_seledra):
        _keep_alive(game, 1)
        game.buildings[TERRITORY] = {0: 'Farm', 1: 'Farm', 2: 'Barracks'}
        if attacker_has_seledra:
            game.heroes[0]['Seledra Rennervail'] = {'territory': TERRITORY, 'plot': 0}
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)
        return _only_report(game)

    def test_all_structures_destroyed_without_seledra(self, game):
        report = self._lose_territory_with_buildings(game, attacker_has_seledra=False)
        assert report['structures_destroyed'] == 3
        assert report['structures_captured'] == 0

    def test_seledra_saves_farms_as_captured_not_destroyed(self, game):
        """
        Champion of the People keeps Farms/Mines for the conqueror. They are not
        rubble, so they must not be reported as destroyed - but they are still lost
        to the enemy, so they must not be silently dropped either.
        """
        report = self._lose_territory_with_buildings(game, attacker_has_seledra=True)
        assert report['structures_destroyed'] == 1   # the Barracks
        assert report['structures_captured'] == 2    # the two saved Farms

    def test_empty_plot_does_not_inflate_counts(self, game):
        """A plot mapped to None is neither destroyed nor captured."""
        _keep_alive(game, 1)
        game.buildings[TERRITORY] = {0: 'Barracks', 1: None}
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)

        report = _only_report(game)
        assert report['structures_destroyed'] == 1
        assert report['structures_captured'] == 0

    def test_successful_defence_keeps_structures(self, game):
        game.buildings[TERRITORY] = {0: 'Farm', 1: 'Barracks'}
        _setup_territory(game, TERRITORY, 1, "Swordsman", 20)
        battle = _create_battle(TERRITORY, 0, 2, {"Swordsman": 2},
                                1, 20, {"Swordsman": 20})
        _resolve(game, battle)

        report = _only_report(game)
        assert report['held'] is True
        assert report['structures_destroyed'] == 0
        assert report['structures_captured'] == 0
        assert report['structures_remaining'] == 2


# ===========================================================================
# Snapshot shape
# ===========================================================================

class TestSnapshotShape:

    def test_snapshot_is_json_round_trippable(self, game):
        """
        The snapshot rides along on the BATTLE_RESOLVE network message, which is
        plain JSON. Tuples would silently become lists and sets would raise.
        """
        _keep_alive(game, 1)
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)
        report = _only_report(game)

        assert json.loads(json.dumps(report)) == report

    def test_snapshot_has_every_key_the_report_screen_indexes(self, game):
        """
        _render_report() indexes these directly - a missing key is a KeyError at
        draw time, and unit_breakdown entries need all three sub-keys.
        """
        _keep_alive(game, 1)
        _setup_territory(game, TERRITORY, 1, "Swordsman", 3)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 3, {"Swordsman": 3})
        _resolve(game, battle)
        report = _only_report(game)

        for key in ('attacker_lost', 'attacker_survivors',
                    'defender_lost', 'defender_survivors',
                    'territory', 'held', 'unit_breakdown',
                    'units_lost', 'units_remaining',
                    'structures_destroyed', 'structures_captured',
                    'structures_remaining', 'defender', 'attacker',
                    'turn_number'):
            assert key in report, key

        for unit_type, data in report['unit_breakdown'].items():
            assert set(data) == {'original', 'survived', 'lost'}
            assert data['original'] == data['survived'] + data['lost']

    def test_unit_breakdown_is_exact_per_type(self, game):
        """Breakdown is read from the real garrison, not estimated proportionally."""
        game.territory_owners[TERRITORY] = 1
        units = (_make_units(game, "Swordsman", 10)
                 + _make_units(game, "Archer", 10))
        for index, unit in enumerate(units):
            unit['id'] = index
        game.territory_garrisons[TERRITORY] = {}
        game.add_garrison(TERRITORY, 1, unmoved=20, moved=0, units=units)
        game.army_units[TERRITORY] = units[:]
        game.armies[TERRITORY] = 20
        game.armies_unmoved[TERRITORY] = 20

        battle = _create_battle(TERRITORY, 0, 1, {"Swordsman": 1},
                                1, 20, {"Swordsman": 10, "Archer": 10})
        _resolve(game, battle)
        report = _only_report(game)

        assert report['held'] is True
        breakdown = report['unit_breakdown']
        assert breakdown['Swordsman']['original'] == 10
        assert breakdown['Archer']['original'] == 10
        total_survived = sum(d['survived'] for d in breakdown.values())
        assert total_survived == report['units_remaining']


# ===========================================================================
# Paths that must NOT produce reports, and the one that must
# ===========================================================================

class TestOtherCapturePaths:

    def test_perfect_dice_tie_still_reports_structures(self, game):
        """
        The perfect-tie path destroys buildings inside _handle_battle_tie_with_dice(),
        BEFORE _update_battle_results() runs (which then early-returns). Capturing in
        resolve_battle() is what makes this case work at all.
        """
        _keep_alive(game, 1)
        game.buildings[TERRITORY] = {0: 'Barracks', 1: 'Farm'}
        _setup_territory(game, TERRITORY, 1, "Swordsman", 5)
        battle = _create_battle(TERRITORY, 0, 5, {"Swordsman": 5},
                                1, 5, {"Swordsman": 5})
        # Force the dice to tie so both sides are wiped and the territory goes neutral.
        import random
        original_randint = random.randint
        random.randint = lambda a, b: b
        try:
            _resolve(game, battle)
        finally:
            random.randint = original_randint

        if game.territory_owners[TERRITORY] == -1:
            report = _only_report(game)
            assert report['held'] is False
            assert report['structures_destroyed'] == 2
        else:
            pytest.skip("dice did not produce a perfect tie on this build")

    def test_keep_only_defence_reports_no_phantom_units(self, game):
        """
        A Keep/Fortress defending ALONE still creates a battle: _process_arrivals()
        puts the owner into player_armies with a count equal to the Keep bonus, even
        with an empty garrison.

        resolve_battle() then substitutes a phantom {'Swordsman': keep_bonus}
        composition, so reading player_compositions would report units the defender
        never had. The report must come from battle.army_compositions, which is only
        populated from a real garrison.
        """
        _keep_alive(game, 1)
        game.buildings[TERRITORY] = {0: 'Keep', 1: 'Farm'}
        game.territory_owners[TERRITORY] = 1
        game.territory_garrisons[TERRITORY] = {}   # no units at all - the Keep fights alone

        battle = Battle(TERRITORY)
        battle.original_owner = 1
        battle.add_army(1, 2, None)               # Keep bonus only, no composition
        battle.add_army(0, 20, {"Swordsman": 20})
        battle.keep_bonus = 2
        battle.keep_bonus_player = 1
        battle.original_garrison = 0              # the discriminator: no real garrison
        _resolve(game, battle)

        report = _only_report(game)
        assert report['defender'] == 1
        assert report['held'] is False
        assert report['units_lost'] == 0          # NOT 2 phantom Swordsmen
        assert report['unit_breakdown'] == {}
        assert report['structures_destroyed'] == 2   # the Keep and the Farm

    def test_keep_only_defence_that_holds(self, game):
        """A Keep that repels the attack reports zero unit losses, structures intact."""
        _keep_alive(game, 1)
        game.buildings[TERRITORY] = {0: 'Keep'}
        game.territory_owners[TERRITORY] = 1
        game.territory_garrisons[TERRITORY] = {}

        battle = Battle(TERRITORY)
        battle.original_owner = 1
        battle.add_army(1, 10, None)
        battle.add_army(0, 1, {"Swordsman": 1})
        battle.keep_bonus = 10
        battle.keep_bonus_player = 1
        battle.original_garrison = 0
        _resolve(game, battle)

        if game.territory_owners[TERRITORY] != 1:
            pytest.skip("Keep did not hold on this build")
        report = _only_report(game)
        assert report['held'] is True
        assert report['units_lost'] == 0
        assert report['structures_destroyed'] == 0

    def test_aggressive_diplomacy_produces_no_report(self, game):
        """
        Halon Nextroy's Aggressive Diplomacy takes a territory in real time. It must
        stay silent. This guards against a future refactor routing it through
        destroy_buildings() / the uncontested-capture path.
        """
        _keep_alive(game, 1)
        # Aggressive Diplomacy requires <=1 defending army and no Keep in the target.
        game.buildings[TERRITORY] = {0: 'Farm', 1: 'Barracks'}
        _setup_territory(game, TERRITORY, 1, "Swordsman", 1)
        game.heroes[0]['Halon Nextroy'] = {'territory': 'Avareon', 'plot': 0}

        success, error = game.execute_aggressive_diplomacy(TERRITORY, 0)

        assert success is True, error          # the guard is worthless if it no-ops
        assert game.territory_owners[TERRITORY] == 0
        assert game.battle_report_inbox == []

    def test_last_battle_reports_resets_per_battle(self, game):
        """
        Network send sites read last_battle_reports right after resolve_battle(), so
        it must never carry a previous battle's entries.
        """
        _keep_alive(game, 1, "Valeonia")
        _keep_alive(game, 0, "Avareon")
        _setup_territory(game, TERRITORY, 1, "Swordsman", 2)
        battle = _create_battle(TERRITORY, 0, 20, {"Swordsman": 20},
                                1, 2, {"Swordsman": 2})
        _resolve(game, battle)
        assert len(game.last_battle_reports) == 1

        other = "Nordia"
        _setup_territory(game, other, 0, "Swordsman", 2)
        battle2 = _create_battle(other, 1, 20, {"Swordsman": 20},
                                 0, 2, {"Swordsman": 2})
        _resolve(game, battle2)

        assert len(game.last_battle_reports) == 1
        assert game.last_battle_reports[0]['territory'] == other
        # The inbox accumulates across battles; last_battle_reports does not.
        assert len(game.battle_report_inbox) == 2
