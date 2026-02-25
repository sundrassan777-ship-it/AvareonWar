"""
Tests for the victory condition system.

Covers all three victory modes (Domination, Capital Assault, Total Conquest),
team-based victory aggregation, and player elimination mechanics.

Victory modes:
    - "Domination (45+)": First player/team to reach 45+ territories wins
    - "Capital Assault": Last player/team standing (all others have 0 territories)
    - "Total Conquest": Own ALL territories on the map

Key method: game.check_victory() returns winner player_index or -1.
On victory: sets game.winner and game.phase = 'ended'.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data

from game_state import GameState


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def game():
    """Standard 2-player game with setup phase skipped (phase='playing').
    L10 fix: conftest.py autouse fixture handles map_data cleanup.
    """
    gs = GameState(
        num_players=2,
        player_is_ai=[False, False],
        player_ai_difficulty=[1, 1],
        skip_setup_phase=True
    )
    return gs


@pytest.fixture
def game_3p():
    """3-player game for Capital Assault multi-player elimination tests."""
    gs = GameState(
        num_players=3,
        player_is_ai=[False, False, False],
        player_ai_difficulty=[1, 1, 1],
        skip_setup_phase=True
    )
    return gs


@pytest.fixture
def game_4p():
    """4-player game for team-based victory tests."""
    gs = GameState(
        num_players=4,
        player_is_ai=[False, False, False, False],
        player_ai_difficulty=[1, 1, 1, 1],
        skip_setup_phase=True
    )
    return gs


# ============================================================================
# TestDominationVictory
# ============================================================================

class TestDominationVictory:
    """Tests for 'Domination (45+)' victory condition."""

    def test_no_winner_below_threshold(self, game):
        """Player with 44 territories should NOT trigger a domination win."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Domination (45+)"

        # Give player 0 exactly 44 territories (one below threshold)
        for t in territories[:44]:
            game.territory_owners[t] = 0
        for t in territories[44:]:
            game.territory_owners[t] = 1

        result = game.check_victory()
        assert result == -1, "No winner expected when player has only 44 territories"

    def test_winner_at_threshold(self, game):
        """Player with exactly 45 territories should win domination."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Domination (45+)"

        # Give player 0 exactly 45 territories (threshold)
        for t in territories[:45]:
            game.territory_owners[t] = 0
        for t in territories[45:]:
            game.territory_owners[t] = 1

        result = game.check_victory()
        assert result == 0, "Player 0 should win with exactly 45 territories"

    def test_winner_above_threshold(self, game):
        """Player with 50 territories (above threshold) should win domination."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Domination (45+)"

        # Give player 0 fifty territories (well above threshold)
        for t in territories[:50]:
            game.territory_owners[t] = 0
        for t in territories[50:]:
            game.territory_owners[t] = 1

        result = game.check_victory()
        assert result == 0, "Player 0 should win with 50 territories"

    def test_sets_phase_ended(self, game):
        """Winning by domination should set game.phase to 'ended'."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Domination (45+)"

        # Confirm phase starts as 'playing'
        assert game.phase == 'playing', "Phase should start as 'playing'"

        for t in territories[:45]:
            game.territory_owners[t] = 0
        for t in territories[45:]:
            game.territory_owners[t] = 1

        game.check_victory()
        assert game.phase == 'ended', "Phase should be 'ended' after domination win"

    def test_sets_winner(self, game):
        """Winning by domination should set game.winner to the winning player index."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Domination (45+)"

        # Give player 1 the winning territories instead of player 0
        for t in territories[:45]:
            game.territory_owners[t] = 1
        for t in territories[45:]:
            game.territory_owners[t] = 0

        game.check_victory()
        assert game.winner == 1, "game.winner should be set to player 1"


# ============================================================================
# TestCapitalAssaultVictory
# ============================================================================

class TestCapitalAssaultVictory:
    """Tests for 'Capital Assault' victory condition (last player standing)."""

    def test_no_winner_both_have_territories(self, game):
        """No winner when both players still own territories."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Capital Assault"

        # Split territories between both players
        for t in territories[:30]:
            game.territory_owners[t] = 0
        for t in territories[30:]:
            game.territory_owners[t] = 1

        result = game.check_victory()
        assert result == -1, "No winner when both players have territories"

    def test_winner_when_opponent_eliminated(self, game):
        """Player wins when opponent has 0 territories (fully eliminated)."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Capital Assault"

        # Player 0 owns all territories; player 1 owns nothing
        for t in territories:
            game.territory_owners[t] = 0

        result = game.check_victory()
        assert result == 0, "Player 0 should win as last player standing"
        assert game.phase == 'ended', "Phase should be 'ended' after capital assault win"
        # M15 fix: Also verify game.winner is set correctly
        assert game.winner == 0, "game.winner should be set to player 0"

    def test_capital_capture_triggers_elimination_and_victory(self, game):
        """C3 fix: Full Capital Assault flow — eliminate_player → check_victory → winner.
        Tests the actual capital-capture mechanic end-to-end."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Capital Assault"

        # Player 0 owns 40 territories, player 1 owns 17
        for t in territories[:40]:
            game.territory_owners[t] = 0
        for t in territories[40:]:
            game.territory_owners[t] = 1

        # No winner yet — both players alive
        assert game.check_victory() == -1

        # Simulate capital capture: eliminate player 1
        game.eliminate_player(1)

        # Player 1's territories should now be neutral
        for t in territories[40:]:
            assert game.territory_owners[t] == -1, f"{t} should be neutral after elimination"

        # Now check victory — player 0 is last standing
        result = game.check_victory()
        assert result == 0, "Player 0 should win after eliminating player 1"
        assert game.winner == 0
        assert game.phase == 'ended'

    def test_capital_assault_three_players(self, game_3p):
        """With 3 players, need all others eliminated for victory."""
        territories = list(game_3p.territory_owners.keys())
        game_3p.victory_condition = "Capital Assault"

        # Player 0 has territories, player 1 has some, player 2 has none
        for t in territories[:30]:
            game_3p.territory_owners[t] = 0
        for t in territories[30:]:
            game_3p.territory_owners[t] = 1
        # Player 2 owns nothing -- but two players remain

        result = game_3p.check_victory()
        assert result == -1, "No winner when 2 of 3 players still have territories"

        # Now eliminate player 1 as well -- only player 0 remains
        for t in territories[30:]:
            game_3p.territory_owners[t] = 0

        result = game_3p.check_victory()
        assert result == 0, "Player 0 wins when all opponents eliminated"


# ============================================================================
# TestTotalConquestVictory
# ============================================================================

class TestTotalConquestVictory:
    """Tests for 'Total Conquest' victory condition (own ALL territories)."""

    def test_no_winner_partial_ownership(self, game):
        """Player with all-but-one territories should NOT win total conquest."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Total Conquest"

        # Give player 0 all but one territory
        for t in territories[:-1]:
            game.territory_owners[t] = 0
        # Last territory belongs to player 1
        game.territory_owners[territories[-1]] = 1

        result = game.check_victory()
        assert result == -1, "No winner when one territory is still held by opponent"

    def test_winner_total_ownership(self, game):
        """Player owning all territories should win total conquest."""
        territories = list(game.territory_owners.keys())
        game.victory_condition = "Total Conquest"

        # Give player 0 every territory on the map
        for t in territories:
            game.territory_owners[t] = 0

        result = game.check_victory()
        assert result == 0, f"Player 0 should win with all {len(territories)} territories"
        assert game.phase == 'ended', "Phase should be 'ended' after total conquest win"
        assert game.winner == 0, "game.winner should be player 0"


# ============================================================================
# TestTeamVictory
# ============================================================================

class TestTeamVictory:
    """Tests for team-based victory (combined territory counts across teammates)."""

    def test_domination_team_combined_count(self, game_4p):
        """Two teammates with 25 territories each (50 total) should win domination."""
        territories = list(game_4p.territory_owners.keys())
        game_4p.victory_condition = "Domination (45+)"

        # Set up teams: players 0,1 on team 0; players 2,3 on team 1
        game_4p.player_teams = [0, 0, 1, 1]

        # Player 0 gets 25, player 1 gets 25 (team total = 50 >= 45 threshold)
        for t in territories[:25]:
            game_4p.territory_owners[t] = 0
        for t in territories[25:50]:
            game_4p.territory_owners[t] = 1
        # Remaining territories go to team 1
        for t in territories[50:]:
            game_4p.territory_owners[t] = 2

        result = game_4p.check_victory()
        # Winner should be a member of team 0 (player 0 or 1)
        assert result in (0, 1), "A member of team 0 should win with combined 50 territories"
        assert game_4p.phase == 'ended', "Phase should be 'ended' after team domination win"

    def test_no_team_victory_below_threshold(self, game_4p):
        """Two teammates with 22 territories each (44 total) should NOT win."""
        territories = list(game_4p.territory_owners.keys())
        game_4p.victory_condition = "Domination (45+)"

        # Set up teams: players 0,1 on team 0; players 2,3 on team 1
        game_4p.player_teams = [0, 0, 1, 1]

        # Player 0 gets 22, player 1 gets 22 (team total = 44, below 45)
        for t in territories[:22]:
            game_4p.territory_owners[t] = 0
        for t in territories[22:44]:
            game_4p.territory_owners[t] = 1
        # Remaining territories split to team 1
        for t in territories[44:]:
            game_4p.territory_owners[t] = 2

        result = game_4p.check_victory()
        assert result == -1, "No winner when team total is only 44 (below 45 threshold)"


# ============================================================================
# TestEliminatePlayer
# ============================================================================

class TestEliminatePlayer:
    """Tests for the eliminate_player() method used in Capital Assault mode."""

    def test_eliminate_clears_territories(self, game):
        """Eliminated player's territories should become neutral (-1)."""
        territories = list(game.territory_owners.keys())

        # Give player 0 some territories
        owned = territories[:10]
        for t in owned:
            game.territory_owners[t] = 0
        for t in territories[10:]:
            game.territory_owners[t] = 1

        game.eliminate_player(0)

        # All of player 0's former territories should now be neutral
        for t in owned:
            assert game.territory_owners[t] == -1, (
                f"Territory {t} should be neutral (-1) after elimination"
            )

    def test_eliminate_clears_garrisons(self, game):
        """Eliminated player's territory garrisons should be cleared."""
        territories = list(game.territory_owners.keys())

        # Set up ownership and garrisons for player 0
        owned = territories[:5]
        for t in owned:
            game.territory_owners[t] = 0
            # Add a garrison entry for player 0
            game.territory_garrisons[t] = {0: {'unmoved': 3, 'moved': 0, 'units': []}}

        game.eliminate_player(0)

        # Garrisons should be cleared (empty dict) after elimination
        for t in owned:
            assert game.territory_garrisons[t] == {}, (
                f"Garrison for {t} should be empty after elimination"
            )

    def test_eliminate_clears_armies(self, game):
        """Eliminated player's army counts should be zeroed out."""
        territories = list(game.territory_owners.keys())

        # Set up ownership and army counts for player 0
        owned = territories[:5]
        for t in owned:
            game.territory_owners[t] = 0
            game.armies[t] = 5
            game.armies_unmoved[t] = 3
            game.armies_moved[t] = 2

        game.eliminate_player(0)

        # All army counters should be zeroed for eliminated territories
        for t in owned:
            assert game.armies[t] == 0, (
                f"armies[{t}] should be 0 after elimination"
            )
            assert game.armies_unmoved[t] == 0, (
                f"armies_unmoved[{t}] should be 0 after elimination"
            )
            assert game.armies_moved[t] == 0, (
                f"armies_moved[{t}] should be 0 after elimination"
            )
