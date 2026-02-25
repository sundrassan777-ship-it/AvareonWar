"""
Unit tests for the garrison system.

Tests cover:
- Adding garrisons (additive behavior, default units, explicit units)
- Removing garrisons (deletion, safety on nonexistent, isolation between players)
- Getting territory total armies (empty, single player, multi-player)
- Getting garrison armies for a specific player
- Cleaning up empty garrisons and fixing count mismatches
- Applying casualties (moved-first priority, capping at garrison size)
- Moving garrison units between territories
- Unit dict factory (_make_unit)
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
    """Reloads map_data to ensure clean state (campaign tests may contaminate it)."""
    map_data.load_polygons()
    map_data.clear_enabled_territories()  # Reset campaign territory filtering
    gs = GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1], skip_setup_phase=True)
    return gs


# ============================================================================
# TestAddGarrison
# ============================================================================

class TestAddGarrison:
    """Tests for adding garrisons to territories."""

    def test_add_garrison_creates_entry(self, game):
        """Adding a garrison creates the territory_garrisons entry."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)

        assert 'Lobardia' in game.territory_garrisons
        assert 0 in game.territory_garrisons['Lobardia']

    def test_add_garrison_with_units(self, game):
        """Adding a garrison with explicit units stores them."""
        game.territory_owners['Lobardia'] = 0
        units = [
            game._make_unit('Archer', 0, 'ready'),
            game._make_unit('Cavalry', 1, 'ready'),
        ]
        game.add_garrison('Lobardia', 0, unmoved=2, units=units)

        garrison = game.territory_garrisons['Lobardia'][0]
        assert len(garrison['units']) == 2
        assert garrison['units'][0]['type'] == 'Archer'
        assert garrison['units'][1]['type'] == 'Cavalry'

    def test_add_garrison_creates_default_swordsmen(self, game):
        """Adding a garrison without units arg creates Swordsman units."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)

        garrison = game.territory_garrisons['Lobardia'][0]
        assert len(garrison['units']) == 3
        for unit in garrison['units']:
            assert unit['type'] == 'Swordsman'

    def test_add_garrison_is_additive(self, game):
        """Calling add_garrison twice adds to existing counts."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)
        game.add_garrison('Lobardia', 0, unmoved=3)

        garrison = game.territory_garrisons['Lobardia'][0]
        assert garrison['unmoved'] == 6

    def test_add_garrison_multiple_players(self, game):
        """Two players can have garrisons in the same territory."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)
        game.add_garrison('Lobardia', 1, unmoved=2)

        assert 0 in game.territory_garrisons['Lobardia']
        assert 1 in game.territory_garrisons['Lobardia']
        assert game.territory_garrisons['Lobardia'][0]['unmoved'] == 3
        assert game.territory_garrisons['Lobardia'][1]['unmoved'] == 2


# ============================================================================
# TestRemoveGarrison
# ============================================================================

class TestRemoveGarrison:
    """Tests for removing garrisons from territories."""

    def test_remove_garrison_deletes_entry(self, game):
        """Removing a garrison deletes the player's entry from the territory."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)
        game.remove_garrison('Lobardia', 0)

        assert 0 not in game.territory_garrisons.get('Lobardia', {})

    def test_remove_garrison_nonexistent(self, game):
        """Removing a nonexistent garrison does not crash."""
        # Should not raise any exception
        game.remove_garrison('Lobardia', 0)
        game.remove_garrison('NonexistentTerritory', 0)

    def test_remove_garrison_leaves_other_players(self, game):
        """Removing one player's garrison does not affect another player's."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)
        game.add_garrison('Lobardia', 1, unmoved=2)
        game.remove_garrison('Lobardia', 0)

        assert 0 not in game.territory_garrisons['Lobardia']
        assert 1 in game.territory_garrisons['Lobardia']
        assert game.territory_garrisons['Lobardia'][1]['unmoved'] == 2


# ============================================================================
# TestGetTerritoryTotalArmies
# ============================================================================

class TestGetTerritoryTotalArmies:
    """Tests for getting total army count in a territory."""

    def test_total_armies_empty(self, game):
        """Territory with no garrison returns 0."""
        assert game.get_territory_total_armies('Lobardia') == 0

    def test_total_armies_single_player(self, game):
        """Counts unmoved + moved for a single player."""
        game.territory_owners['Lobardia'] = 0
        units = [
            game._make_unit('Swordsman', 0, 'ready'),
            game._make_unit('Swordsman', 1, 'ready'),
            game._make_unit('Swordsman', 2, 'moved'),
        ]
        game.add_garrison('Lobardia', 0, unmoved=2, moved=1, units=units)

        assert game.get_territory_total_armies('Lobardia') == 3

    def test_total_armies_multiple_players(self, game):
        """Sums across all player garrisons in the territory."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)
        game.add_garrison('Lobardia', 1, unmoved=2, moved=1)

        assert game.get_territory_total_armies('Lobardia') == 6


# ============================================================================
# TestGetGarrisonArmies
# ============================================================================

class TestGetGarrisonArmies:
    """Tests for getting a specific player's garrison army info."""

    def test_get_garrison_armies_exists(self, game):
        """Returns dict with unmoved, moved, total for existing garrison."""
        game.territory_owners['Lobardia'] = 0
        units = [
            game._make_unit('Swordsman', 0, 'ready'),
            game._make_unit('Swordsman', 1, 'ready'),
            game._make_unit('Swordsman', 2, 'moved'),
        ]
        game.add_garrison('Lobardia', 0, unmoved=2, moved=1, units=units)

        result = game.get_garrison_armies('Lobardia', 0)
        assert result is not None
        assert result['unmoved'] == 2
        assert result['moved'] == 1
        assert result['total'] == 3

    def test_get_garrison_armies_nonexistent(self, game):
        """Returns None for a missing garrison."""
        assert game.get_garrison_armies('Lobardia', 0) is None
        assert game.get_garrison_armies('NonexistentTerritory', 0) is None


# ============================================================================
# TestCleanupEmptyGarrisons
# ============================================================================

class TestCleanupEmptyGarrisons:
    """Tests for cleaning up empty or desynced garrisons."""

    def test_cleanup_removes_empty(self, game):
        """Garrison with 0 armies is removed by cleanup."""
        game.territory_owners['Lobardia'] = 0
        # Manually create an empty garrison entry
        game.territory_garrisons['Lobardia'] = {
            0: {'unmoved': 0, 'moved': 0, 'units': []}
        }

        game.cleanup_empty_garrisons('Lobardia')

        assert 0 not in game.territory_garrisons.get('Lobardia', {})

    def test_cleanup_keeps_nonempty(self, game):
        """Garrison with armies is kept by cleanup."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)

        game.cleanup_empty_garrisons('Lobardia')

        assert 0 in game.territory_garrisons['Lobardia']
        assert game.territory_garrisons['Lobardia'][0]['unmoved'] == 3

    def test_cleanup_fixes_count_mismatch(self, game):
        """Garrison where unmoved+moved != len(units) gets synced."""
        game.territory_owners['Lobardia'] = 0
        # Manually create a garrison with mismatched counts
        game.territory_garrisons['Lobardia'] = {
            0: {
                'unmoved': 5,
                'moved': 0,
                'units': [
                    game._make_unit('Swordsman', 0, 'ready'),
                    game._make_unit('Swordsman', 1, 'ready'),
                    game._make_unit('Swordsman', 2, 'ready'),
                ]
            }
        }

        game.cleanup_empty_garrisons('Lobardia')

        # After cleanup, counts should match the actual 3 units
        garrison = game.territory_garrisons['Lobardia'][0]
        total = garrison['unmoved'] + garrison['moved']
        assert total == len(garrison['units'])
        assert total == 3


# ============================================================================
# TestApplyGarrisonCasualties
# ============================================================================

class TestApplyGarrisonCasualties:
    """Tests for applying casualties to garrisons."""

    def test_casualties_reduces_armies(self, game):
        """Applying casualties reduces the army count."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=5)

        actual = game.apply_garrison_casualties('Lobardia', 0, 2)

        assert actual == 2
        garrison = game.territory_garrisons['Lobardia'][0]
        total = garrison['unmoved'] + garrison['moved']
        assert total == 3

    def test_casualties_removes_moved_first(self, game):
        """Moved units die before unmoved units."""
        game.territory_owners['Lobardia'] = 0
        units = [
            game._make_unit('Swordsman', 0, 'ready'),
            game._make_unit('Swordsman', 1, 'ready'),
            game._make_unit('Swordsman', 2, 'moved'),
            game._make_unit('Swordsman', 3, 'moved'),
        ]
        game.add_garrison('Lobardia', 0, unmoved=2, moved=2, units=units)

        game.apply_garrison_casualties('Lobardia', 0, 2)

        garrison = game.territory_garrisons['Lobardia'][0]
        # Both moved units should be removed, unmoved should remain
        assert garrison['unmoved'] == 2
        assert garrison['moved'] == 0

    def test_casualties_cannot_exceed_garrison(self, game):
        """Cannot remove more units than exist; returns actual casualties applied."""
        game.territory_owners['Lobardia'] = 0
        game.add_garrison('Lobardia', 0, unmoved=3)

        actual = game.apply_garrison_casualties('Lobardia', 0, 10)

        assert actual == 3
        garrison = game.territory_garrisons['Lobardia'][0]
        total = garrison['unmoved'] + garrison['moved']
        assert total == 0


# ============================================================================
# TestMoveGarrisonUnits
# ============================================================================

class TestMoveGarrisonUnits:
    """Tests for moving garrison units between territories."""

    def test_move_units_transfers(self, game):
        """Units move from one territory to another."""
        game.territory_owners['Lobardia'] = 0
        game.territory_owners['Lunedale'] = 0
        game.add_garrison('Lobardia', 0, unmoved=5)

        result = game.move_garrison_units('Lobardia', 'Lunedale', 0, 3)

        assert result is True
        assert game.territory_garrisons['Lobardia'][0]['unmoved'] == 2
        assert game.get_territory_total_armies('Lunedale') == 3

    def test_move_units_marks_as_moved(self, game):
        """Moved units get 'moved' status at the destination."""
        game.territory_owners['Lobardia'] = 0
        game.territory_owners['Lunedale'] = 0
        game.add_garrison('Lobardia', 0, unmoved=5)

        game.move_garrison_units('Lobardia', 'Lunedale', 0, 3)

        dest_garrison = game.territory_garrisons['Lunedale'][0]
        assert dest_garrison['moved'] == 3
        for unit in dest_garrison['units']:
            assert unit['status'] == 'moved'

    def test_move_exceeding_available_fails(self, game):
        """Cannot move more ready units than available; returns False."""
        game.territory_owners['Lobardia'] = 0
        game.territory_owners['Lunedale'] = 0
        game.add_garrison('Lobardia', 0, unmoved=2)

        result = game.move_garrison_units('Lobardia', 'Lunedale', 0, 5)

        assert result is False
        # Source garrison should be unchanged
        assert game.territory_garrisons['Lobardia'][0]['unmoved'] == 2


# ============================================================================
# TestMakeUnit
# ============================================================================

class TestMakeUnit:
    """Tests for the _make_unit factory method."""

    def test_make_unit_structure(self, game):
        """Unit dict has all required fields: id, status, order, type, xp, level."""
        unit = game._make_unit('Swordsman', 0, 'ready')

        assert unit['id'] == 0
        assert unit['status'] == 'ready'
        assert unit['order'] is None
        assert unit['type'] == 'Swordsman'
        assert unit['xp'] == 0
        assert unit['level'] == 0

    def test_make_unit_types(self, game):
        """Can create all 4 unit types: Swordsman, Archer, Pikeman, Cavalry."""
        for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']:
            unit = game._make_unit(unit_type, 0, 'ready')
            assert unit['type'] == unit_type
