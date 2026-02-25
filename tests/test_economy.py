"""
Tests for the economy system (game_state/economy.py).

Covers:
- Territory income calculation (base, Farm, Mine, Square, combined)
- Player income aggregation across territories
- Income collection (gold tracking, stat tracking)
- Effective cost calculation with territorial bonuses
- Taxation system (levels, deductions, floor at zero)
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data
map_data.load_polygons()  # Must be called FIRST

from game_state import GameState


@pytest.fixture
def game():
    """Create a fresh GameState with 2 human players, skipping setup phase.
    Reloads map_data to ensure clean state (campaign tests may contaminate it).

    All territories start neutral (owner=-1), each player starts with 100 gold,
    no buildings, no heroes, no tech researched.
    """
    map_data.load_polygons()
    map_data.clear_enabled_territories()  # Reset campaign territory filtering
    gs = GameState(
        num_players=2,
        player_is_ai=[False, False],
        player_ai_difficulty=[1, 1],
        skip_setup_phase=True
    )
    return gs


# ============================================================================
# TestTerritoryIncome - income calculation for a single territory
# ============================================================================

class TestTerritoryIncome:
    """Tests for calculate_territory_income() on individual territories."""

    def test_base_income_matches_map_data(self, game):
        """Base income for a territory should match map_data.get_territory_income()."""
        expected = map_data.get_territory_income("Lobardia")
        actual = game.calculate_territory_income("Lobardia")
        assert actual == expected, (
            f"Lobardia base income should be {expected}, got {actual}"
        )

    def test_farm_adds_income(self, game):
        """A territory with a Farm should have higher income than without."""
        base_income = game.calculate_territory_income("Lobardia")

        # Place a Farm on plot 0
        game.buildings["Lobardia"] = {0: 'Farm'}
        farm_income = game.calculate_territory_income("Lobardia")

        assert farm_income > base_income, (
            f"Farm income ({farm_income}) should exceed base income ({base_income})"
        )
        # Farm adds 10 gold (at level 0, no tech bonuses)
        assert farm_income == base_income + 10

    def test_mine_adds_income(self, game):
        """A territory with a Mine should have higher income than without."""
        base_income = game.calculate_territory_income("Lunedale")

        # Place a Mine on plot 0
        game.buildings["Lunedale"] = {0: 'Mine'}
        mine_income = game.calculate_territory_income("Lunedale")

        assert mine_income > base_income, (
            f"Mine income ({mine_income}) should exceed base income ({base_income})"
        )
        # Mine adds 15 gold (at level 0, no tech bonuses)
        assert mine_income == base_income + 15

    def test_square_multiplies_income(self, game):
        """A territory with a Square should have multiplied income (1.5x)."""
        base_income = game.calculate_territory_income("Lobardia")

        # Place a Square on plot 0
        game.buildings["Lobardia"] = {0: 'Square'}
        square_income = game.calculate_territory_income("Lobardia")

        expected = int(base_income * 1.5)
        assert square_income == expected, (
            f"Square income should be {expected} (1.5x of {base_income}), got {square_income}"
        )

    def test_farm_and_square_combined(self, game):
        """Farm + Square together should give multiplicative benefit: (base + farm) * 1.5."""
        base_income = map_data.get_territory_income("Lobardia")

        # Place Farm on plot 0 and Square on plot 1
        game.buildings["Lobardia"] = {0: 'Farm', 1: 'Square'}
        combined_income = game.calculate_territory_income("Lobardia")

        # Formula: (base_income + farm_bonus) * multiplier
        # Farm adds 10, Square multiplies by 1.5
        expected = int((base_income + 10) * 1.5)
        assert combined_income == expected, (
            f"Farm+Square income should be {expected}, got {combined_income}. "
            f"Formula: ({base_income} + 10) * 1.5"
        )


# ============================================================================
# TestPlayerIncome - income aggregation across all player territories
# ============================================================================

class TestPlayerIncome:
    """Tests for calculate_player_income() aggregation."""

    def test_player_income_sums_territories(self, game):
        """Player owning 2 territories should get the sum of both incomes."""
        # Give player 0 two territories
        game.territory_owners["Lobardia"] = 0
        game.territory_owners["Lunedale"] = 0

        income_lobardia = game.calculate_territory_income("Lobardia", player_index=0)
        income_lunedale = game.calculate_territory_income("Lunedale", player_index=0)

        total_income = game.calculate_player_income(0)

        # Total should be sum of individual territory incomes
        # (may include territorial bonus modifier at the end, but with no
        #  bonus territories assigned, it should be a straight sum)
        assert total_income == income_lobardia + income_lunedale, (
            f"Total income ({total_income}) should equal "
            f"Lobardia ({income_lobardia}) + Lunedale ({income_lunedale})"
        )

    def test_player_income_zero_territories(self, game):
        """Player owning 0 territories should get 0 income."""
        # All territories are neutral (-1) by default with skip_setup_phase
        income = game.calculate_player_income(0)
        assert income == 0, f"Player with no territories should have 0 income, got {income}"

    def test_player_income_ignores_other_players(self, game):
        """Player income should only count territories owned by that player."""
        # Give different territories to different players
        game.territory_owners["Lobardia"] = 0
        game.territory_owners["Free Cities"] = 1

        income_p0 = game.calculate_player_income(0)
        income_p1 = game.calculate_player_income(1)

        # Player 0 should only get Lobardia income
        lobardia_income = game.calculate_territory_income("Lobardia", player_index=0)
        assert income_p0 == lobardia_income, (
            f"Player 0 income ({income_p0}) should equal Lobardia income ({lobardia_income})"
        )

        # Player 1 should only get Free Cities income
        free_cities_income = game.calculate_territory_income("Free Cities", player_index=1)
        assert income_p1 == free_cities_income, (
            f"Player 1 income ({income_p1}) should equal Free Cities income ({free_cities_income})"
        )


# ============================================================================
# TestCollectIncome - gold collection and stat tracking
# ============================================================================

class TestCollectIncome:
    """Tests for collect_income() gold addition and stat tracking."""

    def test_collect_income_adds_gold(self, game):
        """Gold should increase after collecting income."""
        # Give player 0 a territory so they have some income
        game.territory_owners["Lobardia"] = 0
        gold_before = game.player_gold[0]

        game.collect_income(0)

        gold_after = game.player_gold[0]
        assert gold_after > gold_before, (
            f"Gold should increase after collecting income: "
            f"before={gold_before}, after={gold_after}"
        )

    def test_collect_income_tracks_stats(self, game):
        """Player stats should be updated after collecting income."""
        # Give player 0 a territory
        game.territory_owners["Lobardia"] = 0
        gold_acquired_before = game.player_stats[0]['gold_acquired']

        game.collect_income(0)

        gold_acquired_after = game.player_stats[0]['gold_acquired']
        assert gold_acquired_after > gold_acquired_before, (
            f"gold_acquired stat should increase: "
            f"before={gold_acquired_before}, after={gold_acquired_after}"
        )


# ============================================================================
# TestEffectiveCost - cost calculation with discounts and bonuses
# ============================================================================

class TestEffectiveCost:
    """Tests for get_effective_cost() discount system."""

    def test_base_cost_no_discounts(self, game):
        """With no discounts active, effective cost should equal base cost."""
        # Player 0 has no upgrades, no territorial bonuses, no heroes
        cost = game.get_effective_cost('Swordsman', 20, player=0)
        assert cost == 20, (
            f"Swordsman effective cost with no discounts should be 20, got {cost}"
        )

    def test_territorial_bonus_reduces_cost(self, game):
        """Player owning a unit_cost bonus territory should pay less for units."""
        # Venexia has unit_cost bonus (-5% per territory)
        game.territory_owners["Venexia"] = 0

        # Base cost 20, with -5% territorial unit_cost bonus
        cost = game.get_effective_cost('Swordsman', 20, player=0)
        expected = int(20 * (100 - 5) / 100)  # = int(20 * 0.95) = 19
        assert cost == expected, (
            f"Swordsman cost with unit_cost bonus should be {expected}, got {cost}"
        )


# ============================================================================
# TestTaxation - taxation system (levels, deductions, floor)
# ============================================================================

class TestTaxation:
    """Tests for apply_taxation() deduction system."""

    def test_taxation_level_zero_no_deduction(self, game):
        """Tax level 0 should not deduct any gold."""
        game.taxation_level = 0
        game.player_gold[0] = 200

        game.apply_taxation(0)

        assert game.player_gold[0] == 200, (
            f"Gold should be unchanged at tax level 0: got {game.player_gold[0]}"
        )

    def test_taxation_reduces_gold(self, game):
        """Higher tax level should reduce gold by the expected percentage."""
        game.taxation_level = 2  # 50% tax rate
        game.player_gold[0] = 200

        game.apply_taxation(0)

        # 50% of 200 = 100 deducted, leaving 100
        assert game.player_gold[0] == 100, (
            f"Gold after 50% tax on 200 should be 100, got {game.player_gold[0]}"
        )

    def test_taxation_cannot_go_negative(self, game):
        """Gold should not go below 0 even with 100% taxation."""
        game.taxation_level = 4  # 100% tax rate
        game.player_gold[0] = 50

        game.apply_taxation(0)

        assert game.player_gold[0] >= 0, (
            f"Gold should not be negative after taxation: got {game.player_gold[0]}"
        )
