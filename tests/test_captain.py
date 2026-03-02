# -*- coding: utf-8 -*-
"""
Tests for Captain unit type.

Covers:
- UNIT_TYPES definition (strength, counters, cost)
- Strength calculation (0.25 base strength, +12% army bonus, non-stacking)
- Counter effectiveness (always neutral 1.0)
- Extended movement (army_has_captain, find_2hop_path)
- Heroic Fortitude discount (75g → 50g)

Uses a real GameState instance with skip_setup_phase=True.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
from game_state import GameState


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _make_gs(num_players=2):
    """Create a minimal GameState for testing."""
    gs = GameState(
        num_players=num_players,
        player_is_ai=[False] * num_players,
        player_ai_difficulty=[0] * num_players,
        skip_setup_phase=True
    )
    return gs


def _setup_garrison(gs, territory, player, unit_types_list):
    """Set up a garrison with specific unit types.
    unit_types_list: list of unit type strings, e.g. ['Swordsman', 'Captain', 'Archer']
    """
    gs.territory_owners[territory] = player
    units = [gs._make_unit(ut, i, 'ready') for i, ut in enumerate(unit_types_list)]
    gs.territory_garrisons[territory] = {}
    gs.add_garrison(territory, player, unmoved=len(units), moved=0, units=units)
    gs.army_units[territory] = units[:]
    gs.armies[territory] = len(units)
    gs.armies_unmoved[territory] = len(units)


# ===========================================================================
# Test: UNIT_TYPES definition
# ===========================================================================

class TestCaptainDefinition:
    """Verify Captain exists in UNIT_TYPES with correct fields."""

    def test_captain_in_unit_types(self):
        gs = _make_gs()
        assert 'Captain' in gs.UNIT_TYPES

    def test_captain_cost(self):
        gs = _make_gs()
        assert gs.UNIT_TYPES['Captain']['cost'] == 75

    def test_captain_letter(self):
        gs = _make_gs()
        assert gs.UNIT_TYPES['Captain']['letter'] == 'T'

    def test_captain_strength(self):
        gs = _make_gs()
        assert gs.UNIT_TYPES['Captain']['strength'] == 0.25

    def test_captain_no_counters(self):
        gs = _make_gs()
        assert gs.UNIT_TYPES['Captain']['counters'] is None
        assert gs.UNIT_TYPES['Captain']['countered_by'] is None

    def test_captain_army_bonus(self):
        gs = _make_gs()
        assert gs.UNIT_TYPES['Captain']['army_bonus'] == 0.12

    def test_all_units_have_strength(self):
        """All unit types should have a 'strength' key."""
        gs = _make_gs()
        for unit_type, info in gs.UNIT_TYPES.items():
            assert 'strength' in info, f"{unit_type} missing 'strength' key"


# ===========================================================================
# Test: Strength calculation
# ===========================================================================

class TestCaptainStrength:
    """Verify Captain's 0.25 base strength and +12% army bonus."""

    def test_captain_base_strength_in_battle(self):
        """Captain contributes 0.25 effective strength per unit."""
        gs = _make_gs()
        # 1 Captain vs 1 Swordsman (neutral matchup for Captain)
        comp = {'Captain': 1}
        enemy = {'Swordsman': 1}
        strength = gs.calculate_army_effective_strength(comp, enemy)
        # Captain: 1 × 0.25 × 1.0 effectiveness = 0.25
        assert abs(strength - 0.25) < 0.01

    def test_captain_weaker_than_countered_unit(self):
        """Captain (0.25) should be weaker than a fully countered unit (0.5)."""
        gs = _make_gs()
        # Swordsman vs pure Archers (fully countered → 0.5 effectiveness)
        swordsman_strength = gs.calculate_army_effective_strength(
            {'Swordsman': 1}, {'Archer': 10}
        )
        captain_strength = gs.calculate_army_effective_strength(
            {'Captain': 1}, {'Archer': 10}
        )
        # Swordsman countered: 1 × 1.0 × 0.5 = 0.5
        # Captain: 1 × 0.25 × 1.0 = 0.25
        assert captain_strength < swordsman_strength

    def test_captain_bonus_boosts_other_units(self):
        """Army with Captain gets +12% strength for non-Captain units."""
        gs = _make_gs()
        enemy = {'Swordsman': 5}
        # Without Captain: 5 Archers
        no_captain = gs.calculate_army_effective_strength({'Archer': 5}, enemy)
        # With Captain: 5 Archers + 1 Captain
        with_captain = gs.calculate_army_effective_strength({'Archer': 5, 'Captain': 1}, enemy)
        # Expected: Archers get ×1.12 bonus, plus Captain's own 0.25 contribution
        expected = no_captain * 1.12 + 0.25  # Captain's own contribution (neutral vs Swordsmen)
        assert abs(with_captain - expected) < 0.01

    def test_captain_bonus_non_stacking(self):
        """Multiple Captains should NOT stack the +12% bonus."""
        gs = _make_gs()
        enemy = {'Swordsman': 5}
        one_captain = gs.calculate_army_effective_strength({'Archer': 5, 'Captain': 1}, enemy)
        two_captains = gs.calculate_army_effective_strength({'Archer': 5, 'Captain': 2}, enemy)
        # Difference should only be the extra Captain's own 0.25 contribution
        # (bonus is the same +12% in both cases)
        assert abs(two_captains - one_captain - 0.25) < 0.01

    def test_captain_effectiveness_always_neutral(self):
        """Captain effectiveness should always be 1.0 regardless of enemy composition."""
        gs = _make_gs()
        for enemy_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']:
            effectiveness = gs.calculate_unit_effectiveness('Captain', {enemy_type: 10})
            assert abs(effectiveness - 1.0) < 0.01, f"Captain vs {enemy_type} should be 1.0"

    def test_no_enemies_captain_counts_as_full(self):
        """With no enemies, each unit counts at face value (strength × count)."""
        gs = _make_gs()
        comp = {'Swordsman': 3, 'Captain': 1}
        # No enemies: returns sum of counts (per existing logic)
        strength = gs.calculate_army_effective_strength(comp, {})
        assert abs(strength - 4.0) < 0.01  # 3 + 1 = 4 (no strength multiplier when no enemies)


# ===========================================================================
# Test: army_has_captain
# ===========================================================================

class TestArmyHasCaptain:

    def test_has_captain_true(self):
        gs = _make_gs()
        _setup_garrison(gs, 'Aelatania', 0, ['Swordsman', 'Captain', 'Archer'])
        assert gs.army_has_captain('Aelatania', 0) is True

    def test_has_captain_false(self):
        gs = _make_gs()
        _setup_garrison(gs, 'Aelatania', 0, ['Swordsman', 'Archer'])
        assert gs.army_has_captain('Aelatania', 0) is False

    def test_has_captain_empty_garrison(self):
        gs = _make_gs()
        assert gs.army_has_captain('Aelatania', 0) is False


# ===========================================================================
# Test: find_2hop_path
# ===========================================================================

class TestFind2HopPath:

    def _setup_chain(self, gs, territories, owners):
        """Set up a chain of territories with specified owners."""
        for t, owner in zip(territories, owners):
            gs.territory_owners[t] = owner

    def test_valid_2hop_path(self):
        """Find 2-hop path through allied intermediate territory."""
        gs = _make_gs()
        # Need 3 territories in a chain: A -- B -- C where B is adjacent to both
        # Find such a chain from actual map data
        all_territories = map_data.get_all_territories()
        found = False
        for t1 in all_territories:
            n1 = set(map_data.get_neighbors(t1))
            for mid in n1:
                n_mid = set(map_data.get_neighbors(mid))
                for t2 in n_mid:
                    if t2 != t1 and t2 not in n1:  # t2 not adjacent to t1
                        # Found a valid chain
                        self._setup_chain(gs, [t1, mid, t2], [0, 0, 0])
                        result = gs.find_2hop_path(t1, t2, 0)
                        assert result is not None, f"Expected valid 2-hop path {t1} -> {mid} -> {t2}"
                        found = True
                        break
                if found:
                    break
            if found:
                break
        assert found, "Could not find a valid 3-territory chain in map data"

    def test_no_path_enemy_intermediate(self):
        """2-hop should fail if intermediate is enemy-owned."""
        gs = _make_gs()
        all_territories = map_data.get_all_territories()
        for t1 in all_territories:
            n1 = set(map_data.get_neighbors(t1))
            for mid in n1:
                n_mid = set(map_data.get_neighbors(mid))
                for t2 in n_mid:
                    if t2 != t1 and t2 not in n1:
                        # Make intermediate enemy-owned
                        self._setup_chain(gs, [t1, mid, t2], [0, 1, 0])
                        result = gs.find_2hop_path(t1, t2, 0)
                        assert result is None, "Should fail with enemy intermediate"
                        return
        pytest.skip("No valid chain found")

    def test_no_path_enemy_destination(self):
        """2-hop should fail if destination is enemy-owned (no 2-hop attacks)."""
        gs = _make_gs()
        all_territories = map_data.get_all_territories()
        for t1 in all_territories:
            n1 = set(map_data.get_neighbors(t1))
            for mid in n1:
                n_mid = set(map_data.get_neighbors(mid))
                for t2 in n_mid:
                    if t2 != t1 and t2 not in n1:
                        # Destination is enemy
                        self._setup_chain(gs, [t1, mid, t2], [0, 0, 1])
                        result = gs.find_2hop_path(t1, t2, 0)
                        assert result is None, "Should fail with enemy destination"
                        return
        pytest.skip("No valid chain found")

    def test_adjacent_returns_none(self):
        """Adjacent territories should return None (use normal movement)."""
        gs = _make_gs()
        all_territories = map_data.get_all_territories()
        t1 = all_territories[0]
        t2 = map_data.get_neighbors(t1)[0]
        gs.territory_owners[t1] = 0
        gs.territory_owners[t2] = 0
        result = gs.find_2hop_path(t1, t2, 0)
        assert result is None


# ===========================================================================
# Test: Heroic Fortitude discount
# ===========================================================================

class TestHeroicFortitudeDiscount:

    def test_captain_cost_before_heroic_fortitude(self):
        gs = _make_gs()
        cost = gs.get_effective_cost('Captain', 75, 0)
        assert cost == 75

    def test_captain_cost_after_heroic_fortitude(self):
        gs = _make_gs()
        gs.player_captain_cost_discount[0] = 33  # Heroic Fortitude researched
        cost = gs.get_effective_cost('Captain', 75, 0)
        assert cost == 50  # int(75 * 67 / 100) = 50


# ===========================================================================
# Test: Player stats tracking
# ===========================================================================

class TestCaptainStats:

    def test_captains_trained_stat_exists(self):
        gs = _make_gs()
        assert 'captains_trained' in gs.player_stats[0]
        assert gs.player_stats[0]['captains_trained'] == 0
