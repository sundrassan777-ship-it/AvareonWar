# -*- coding: utf-8 -*-
"""
Tests for Battle Resolution System (game_state/military.py resolve_battle)

Covers:
- Basic battle resolution (valid/invalid, attacker/defender wins, state updates)
- Unit counter system (Swordsman > Pikeman > Cavalry > Archer > Swordsman)
- Keep defense bonus (two-phase Keep battles)
- Tied battles (dice roll fallback)

Uses a real GameState instance with skip_setup_phase=True to test actual
battle resolution logic without mocking.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
# H12 fix: conftest.py autouse fixture handles load_polygons() + cleanup

from game_state import GameState, Battle


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _make_units(game, unit_type, count, status='ready'):
    """Create a list of unit dicts using the GameState factory method."""
    return [game._make_unit(unit_type, i, status) for i in range(count)]


def _setup_territory(game, territory, player, unit_type, count):
    """
    Set up a territory with a garrison for a player.

    Assigns ownership, creates garrison with specified unit type and count,
    and synchronises the legacy army tracking dicts (armies, armies_unmoved,
    army_units) so that battle resolution works correctly.
    """
    game.territory_owners[territory] = player
    units = _make_units(game, unit_type, count)
    game.territory_garrisons[territory] = {}
    game.add_garrison(territory, player, unmoved=count, moved=0, units=units)
    game.army_units[territory] = units[:]
    game.armies[territory] = count
    game.armies_unmoved[territory] = count


def _create_battle(territory, attacker, attacker_count, attacker_comp,
                   defender, defender_count, defender_comp,
                   keep_bonus=0):
    """
    Create a Battle object ready for resolution.

    Args:
        territory: Territory name where battle occurs.
        attacker: Attacker player index.
        attacker_count: Total attacker army size.
        attacker_comp: Dict of {unit_type: count} for attacker.
        defender: Defender player index.
        defender_count: Total defender army size.
        defender_comp: Dict of {unit_type: count} for defender.
        keep_bonus: Keep defense bonus (0 if no Keep).

    Returns:
        Battle object with armies and compositions set.
    """
    battle = Battle(territory)
    battle.original_owner = defender
    # Add defender first, then attacker (order follows garrison-then-arrival)
    battle.add_army(defender, defender_count, defender_comp)
    battle.add_army(attacker, attacker_count, attacker_comp)
    if keep_bonus > 0:
        battle.keep_bonus = keep_bonus
        battle.keep_bonus_player = defender
        battle.original_garrison = defender_count
    return battle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def game():
    """Create a fresh GameState for each test (skip setup phase).
    L10 fix: conftest.py autouse fixture handles map_data cleanup.
    """
    gs = GameState(
        num_players=2,
        player_is_ai=[False, False],
        player_ai_difficulty=[1, 1],
        skip_setup_phase=True
    )
    return gs


# ===========================================================================
# TestBattleResolutionBasic
# ===========================================================================

class TestBattleResolutionBasic:
    """Basic battle resolution tests: validation, outcomes, state updates."""

    def test_resolve_battle_invalid_index(self, game):
        """Battle index out of range should return False without crashing."""
        # No pending battles at all
        result = game.resolve_battle(0)
        assert result is False, "resolve_battle should return False for out-of-range index"

        # One battle exists, but index 5 is invalid
        _setup_territory(game, "Lobardia", 1, "Swordsman", 3)
        battle = _create_battle(
            "Lobardia", attacker=0, attacker_count=5,
            attacker_comp={"Swordsman": 5},
            defender=1, defender_count=3,
            defender_comp={"Swordsman": 3}
        )
        game.pending_battles.append(battle)
        result = game.resolve_battle(5)
        assert result is False, "resolve_battle should return False for index beyond list length"

    def test_resolve_battle_already_resolved(self, game):
        """Already-resolved battle should return False."""
        _setup_territory(game, "Lobardia", 1, "Swordsman", 3)
        battle = _create_battle(
            "Lobardia", attacker=0, attacker_count=5,
            attacker_comp={"Swordsman": 5},
            defender=1, defender_count=3,
            defender_comp={"Swordsman": 3}
        )
        battle.resolved = True  # Mark as already resolved
        game.pending_battles.append(battle)
        result = game.resolve_battle(0)
        assert result is False, "resolve_battle should return False for already-resolved battle"

    def test_attacker_wins_normal_battle(self, game):
        """10 Swordsmen attacking 3 Swordsmen should result in attacker victory."""
        territory = "Lobardia"
        _setup_territory(game, territory, 1, "Swordsman", 3)

        battle = _create_battle(
            territory, attacker=0, attacker_count=10,
            attacker_comp={"Swordsman": 10},
            defender=1, defender_count=3,
            defender_comp={"Swordsman": 3}
        )
        game.pending_battles.append(battle)

        result = game.resolve_battle(0)
        assert result is True, "resolve_battle should return True on success"
        assert battle.resolved is True, "Battle should be marked resolved"
        assert battle.winner == 0, "Attacker (player 0) should win with overwhelming numbers"

    def test_defender_wins_normal_battle(self, game):
        """3 Swordsmen attacking 10 Swordsmen should result in defender victory."""
        territory = "Lobardia"
        _setup_territory(game, territory, 1, "Swordsman", 10)

        battle = _create_battle(
            territory, attacker=0, attacker_count=3,
            attacker_comp={"Swordsman": 3},
            defender=1, defender_count=10,
            defender_comp={"Swordsman": 10}
        )
        game.pending_battles.append(battle)

        result = game.resolve_battle(0)
        assert result is True
        assert battle.resolved is True
        assert battle.winner == 1, "Defender (player 1) should win with superior numbers"

    def test_battle_updates_territory_ownership(self, game):
        """Winner of battle should take ownership of the contested territory."""
        territory = "Lobardia"
        _setup_territory(game, territory, 1, "Swordsman", 3)

        battle = _create_battle(
            territory, attacker=0, attacker_count=10,
            attacker_comp={"Swordsman": 10},
            defender=1, defender_count=3,
            defender_comp={"Swordsman": 3}
        )
        game.pending_battles.append(battle)
        game.resolve_battle(0)

        assert game.territory_owners[territory] == battle.winner, (
            "Territory ownership should be updated to the battle winner"
        )

    def test_battle_removes_from_pending(self, game):
        """After resolution the battle should be removed from pending_battles."""
        territory = "Lobardia"
        _setup_territory(game, territory, 1, "Swordsman", 3)

        battle = _create_battle(
            territory, attacker=0, attacker_count=10,
            attacker_comp={"Swordsman": 10},
            defender=1, defender_count=3,
            defender_comp={"Swordsman": 3}
        )
        game.pending_battles.append(battle)
        game.resolve_battle(0)

        assert len(game.pending_battles) == 0, (
            "pending_battles should be empty after resolving the only battle"
        )

    def test_battle_sets_ready_to_advance(self, game):
        """ready_to_advance_turn should be True when no battles remain."""
        territory = "Lobardia"
        _setup_territory(game, territory, 1, "Swordsman", 3)

        battle = _create_battle(
            territory, attacker=0, attacker_count=10,
            attacker_comp={"Swordsman": 10},
            defender=1, defender_count=3,
            defender_comp={"Swordsman": 3}
        )
        game.pending_battles.append(battle)

        # Ensure flag is False before resolution
        game.ready_to_advance_turn = False
        game.resolve_battle(0)

        assert game.ready_to_advance_turn is True, (
            "ready_to_advance_turn should be set True when all battles are resolved"
        )


# ===========================================================================
# TestBattleCounterSystem
# ===========================================================================

class TestBattleCounterSystem:
    """
    Tests for the unit counter system.

    Counter chain: Swordsman > Pikeman > Cavalry > Archer > Swordsman (circular).
    Units with a counter advantage get 2x effectiveness against countered enemies,
    while countered units get 0.5x effectiveness. With equal army sizes the side
    with the counter advantage should consistently win.
    """

    def test_swordsmen_beat_pikemen(self, game):
        """Swordsman counters Pikeman - equal numbers, Swordsmen should win."""
        territory = "Lobardia"
        count = 8
        _setup_territory(game, territory, 1, "Pikeman", count)

        battle = _create_battle(
            territory, attacker=0, attacker_count=count,
            attacker_comp={"Swordsman": count},
            defender=1, defender_count=count,
            defender_comp={"Pikeman": count}
        )
        game.pending_battles.append(battle)
        game.resolve_battle(0)

        assert battle.winner == 0, (
            f"Swordsmen (player 0) should beat Pikemen (player 1) with equal numbers. "
            f"Winner was player {battle.winner}"
        )

    def test_pikemen_beat_cavalry(self, game):
        """Pikeman counters Cavalry - equal numbers, Pikemen should win."""
        territory = "Lobardia"
        count = 8
        _setup_territory(game, territory, 1, "Cavalry", count)

        battle = _create_battle(
            territory, attacker=0, attacker_count=count,
            attacker_comp={"Pikeman": count},
            defender=1, defender_count=count,
            defender_comp={"Cavalry": count}
        )
        game.pending_battles.append(battle)
        game.resolve_battle(0)

        assert battle.winner == 0, (
            f"Pikemen (player 0) should beat Cavalry (player 1) with equal numbers. "
            f"Winner was player {battle.winner}"
        )

    def test_cavalry_beat_archers(self, game):
        """Cavalry counters Archer - equal numbers, Cavalry should win."""
        territory = "Lobardia"
        count = 8
        _setup_territory(game, territory, 1, "Archer", count)

        battle = _create_battle(
            territory, attacker=0, attacker_count=count,
            attacker_comp={"Cavalry": count},
            defender=1, defender_count=count,
            defender_comp={"Archer": count}
        )
        game.pending_battles.append(battle)
        game.resolve_battle(0)

        assert battle.winner == 0, (
            f"Cavalry (player 0) should beat Archers (player 1) with equal numbers. "
            f"Winner was player {battle.winner}"
        )

    def test_archers_beat_swordsmen(self, game):
        """Archer counters Swordsman - equal numbers, Archers should win."""
        territory = "Lobardia"
        count = 8
        _setup_territory(game, territory, 1, "Swordsman", count)

        battle = _create_battle(
            territory, attacker=0, attacker_count=count,
            attacker_comp={"Archer": count},
            defender=1, defender_count=count,
            defender_comp={"Swordsman": count}
        )
        game.pending_battles.append(battle)
        game.resolve_battle(0)

        assert battle.winner == 0, (
            f"Archers (player 0) should beat Swordsmen (player 1) with equal numbers. "
            f"Winner was player {battle.winner}"
        )

    def test_counter_advantage_reduces_casualties(self, game):
        """Winner with counter advantage should lose fewer troops than in a mirror match."""
        territory_counter = "Lobardia"
        territory_mirror = "Lentria"
        count = 10

        # Battle 1: Counter advantage (Swordsman vs Pikeman)
        _setup_territory(game, territory_counter, 1, "Pikeman", count)
        battle_counter = _create_battle(
            territory_counter, attacker=0, attacker_count=count,
            attacker_comp={"Swordsman": count},
            defender=1, defender_count=count,
            defender_comp={"Pikeman": count}
        )
        game.pending_battles.append(battle_counter)
        game.resolve_battle(0)

        # Battle 2: Mirror match (Swordsman vs Swordsman, attacker has 12 to guarantee win)
        _setup_territory(game, territory_mirror, 1, "Swordsman", count)
        battle_mirror = _create_battle(
            territory_mirror, attacker=0, attacker_count=12,
            attacker_comp={"Swordsman": 12},
            defender=1, defender_count=count,
            defender_comp={"Swordsman": count}
        )
        game.pending_battles.append(battle_mirror)
        game.resolve_battle(0)

        # Both battles should be won by attacker
        assert battle_counter.winner == 0, "Counter battle should be won by attacker"
        assert battle_mirror.winner == 0, "Mirror battle should be won by attacker"

        # Counter advantage battle: attacker started with 10 vs 10
        # Mirror battle: attacker started with 12 vs 10 (needed more troops)
        # The counter-advantaged attacker should have MORE survivors relative to starting count
        counter_survivors = battle_counter.surviving_armies
        mirror_survivors = battle_mirror.surviving_armies

        # H10 fix: Assert comparative advantage, not trivially-true >= 1.
        # Counter-advantaged attacker (10 vs 10) should do at least as well as
        # the mirror attacker (12 vs 10) relative to starting troops.
        counter_ratio = counter_survivors / 10.0  # started with 10
        mirror_ratio = mirror_survivors / 12.0    # started with 12
        assert counter_ratio >= mirror_ratio, (
            f"Counter advantage should yield better survival ratio: "
            f"counter={counter_ratio:.2f} vs mirror={mirror_ratio:.2f}"
        )


# ===========================================================================
# TestKeepBattle
# ===========================================================================

class TestKeepBattle:
    """
    Tests for Keep defense bonus in battle resolution.

    Keep adds +2 effective armies for the defender via a two-phase combat system:
    - Phase 1: Attackers vs Garrison (unit counters apply)
    - Phase 2: Remaining attackers vs Keep (type-neutral, pure numbers)
    """

    def test_keep_battle_attacker_wins(self, game):
        """Large force should break through a small garrison defended by a Keep."""
        territory = "Lobardia"
        defender = 1
        attacker = 0
        defender_count = 3
        attacker_count = 10

        _setup_territory(game, territory, defender, "Swordsman", defender_count)
        # Place a Keep in the territory (plot index 0)
        game.buildings[territory] = {0: 'Keep'}

        battle = _create_battle(
            territory, attacker=attacker, attacker_count=attacker_count,
            attacker_comp={"Swordsman": attacker_count},
            defender=defender, defender_count=defender_count,
            defender_comp={"Swordsman": defender_count},
            keep_bonus=2
        )
        game.pending_battles.append(battle)

        result = game.resolve_battle(0)
        assert result is True, "resolve_battle should succeed"
        assert battle.resolved is True
        assert battle.winner == attacker, (
            f"Attacker with 10 armies should break through 3 garrison + Keep (bonus 2). "
            f"Winner was player {battle.winner}"
        )

    def test_keep_battle_defender_wins(self, game):
        """Small attack force should fail against garrison + Keep defense."""
        territory = "Lobardia"
        defender = 1
        attacker = 0
        defender_count = 5
        attacker_count = 4

        _setup_territory(game, territory, defender, "Swordsman", defender_count)
        game.buildings[territory] = {0: 'Keep'}

        battle = _create_battle(
            territory, attacker=attacker, attacker_count=attacker_count,
            attacker_comp={"Swordsman": attacker_count},
            defender=defender, defender_count=defender_count,
            defender_comp={"Swordsman": defender_count},
            keep_bonus=2
        )
        game.pending_battles.append(battle)

        result = game.resolve_battle(0)
        assert result is True
        assert battle.resolved is True
        assert battle.winner == defender, (
            f"Defender with 5 garrison + Keep (bonus 2) should repel 4 attackers. "
            f"Winner was player {battle.winner}"
        )

    def test_keep_bonus_applied(self, game):
        """Battle with Keep should have keep_bonus > 0 on the battle object."""
        territory = "Lobardia"
        defender = 1
        attacker = 0

        _setup_territory(game, territory, defender, "Swordsman", 5)
        game.buildings[territory] = {0: 'Keep'}

        battle = _create_battle(
            territory, attacker=attacker, attacker_count=10,
            attacker_comp={"Swordsman": 10},
            defender=defender, defender_count=5,
            defender_comp={"Swordsman": 5},
            keep_bonus=2
        )

        # Verify keep_bonus was set correctly by _create_battle
        assert battle.keep_bonus == 2, "Keep bonus should be 2"
        assert battle.keep_bonus_player == defender, "Keep bonus should belong to defender"
        assert battle.original_garrison == 5, "Original garrison count should be recorded"

        # Resolve and confirm battle still completes with Keep logic
        game.pending_battles.append(battle)
        result = game.resolve_battle(0)
        assert result is True
        assert battle.resolved is True


# ===========================================================================
# TestBattleTie
# ===========================================================================

class TestBattleTie:
    """
    Tests for tied battles.

    When two armies have exactly equal effective strength, the battle falls back
    to a dice roll system. The test verifies that resolution completes without
    errors and produces a valid winner.
    """

    def test_tied_battle_uses_dice(self, game):
        """Armies with equal strength should resolve via dice without crashing."""
        territory = "Lobardia"
        count = 5  # Same unit type, same count -> equal effective strength

        _setup_territory(game, territory, 1, "Swordsman", count)

        battle = _create_battle(
            territory, attacker=0, attacker_count=count,
            attacker_comp={"Swordsman": count},
            defender=1, defender_count=count,
            defender_comp={"Swordsman": count}
        )
        game.pending_battles.append(battle)

        result = game.resolve_battle(0)
        assert result is True, "resolve_battle should succeed even on ties"
        assert battle.resolved is True, "Battle should be marked resolved after tie-breaking"
        # Winner should be one of the two players or -1 (perfect dice tie -> neutral)
        assert battle.winner in (0, 1, -1), (
            f"Winner should be player 0, 1, or -1 (neutral). Got: {battle.winner}"
        )
