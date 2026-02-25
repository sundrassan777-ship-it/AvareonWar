# game_state/victory.py
# Victory checking mixin for GameState (Phase 7 decomposition)

"""
Victory conditions: domination, capital assault, total conquest, elimination.

Provides methods for checking win conditions and eliminating players
from the game when their capital territory is conquered.
"""

from utils.logger import get_logger

logger = get_logger(__name__)


class VictoryMixin:
    """Mixin providing victory checking and player elimination methods for GameState."""

    def check_victory(self):
        """
        Check if any player has won based on the selected victory condition.

        Returns:
            int: Winner player index, or -1 if no winner yet
        """
        # Count territories per player
        territory_counts = [0] * self.num_players
        for owner in self.territory_owners.values():
            if owner >= 0:
                territory_counts[owner] += 1

        # DEBUG: Print territory counts
        logger.debug(f"check_victory: Victory Condition: {self.victory_condition}")
        logger.debug(f"check_victory: Territory counts: {territory_counts}")

        # Route to appropriate victory check based on victory_condition
        if self.victory_condition == "Domination (45+)":
            return self._check_domination_victory(territory_counts)
        elif self.victory_condition == "Capital Assault":
            return self._check_capital_assault_victory(territory_counts)
        elif self.victory_condition == "Total Conquest":
            return self._check_total_conquest_victory(territory_counts)

        # Fallback to Domination if unknown victory condition
        logger.warning(f"Unknown victory condition '{self.victory_condition}', defaulting to Domination")
        return self._check_domination_victory(territory_counts)

    def _check_domination_victory(self, territory_counts):
        """
        Check Domination victory (45+ territories).

        Works team-wise: aggregates territory counts for all players on the same team.
        A team wins when their combined territory count reaches the threshold.

        Args:
            territory_counts (list): Territory count per player

        Returns:
            int: Winner player index (representative of winning team), or -1 if no winner
        """
        victory_threshold = self.victory_territory_threshold

        # Check if teams are active - aggregate by team if so
        if hasattr(self, 'player_teams') and self.player_teams:
            # Build team territory counts
            team_counts = {}  # team_id -> total territories
            team_members = {}  # team_id -> list of player indices

            for player_id, count in enumerate(territory_counts):
                team_id = self.player_teams[player_id]
                if team_id not in team_counts:
                    team_counts[team_id] = 0
                    team_members[team_id] = []
                team_counts[team_id] += count
                team_members[team_id].append(player_id)

            # Check if any team meets threshold
            for team_id, total_count in team_counts.items():
                logger.debug(f"Team {team_id + 1}: {total_count} territories (need {victory_threshold})")
                if total_count >= victory_threshold:
                    # Use first active team member as winner representative
                    winner = team_members[team_id][0]
                    for member in team_members[team_id]:
                        if territory_counts[member] > 0:
                            winner = member
                            break

                    logger.info(f"DOMINATION TEAM VICTORY for Team {team_id + 1}!")
                    self.winner = winner
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   TEAM {team_id + 1} WINS!")
                    self.add_message(f"   ({total_count} territories)")
                    self.add_message(f"============================")
                    return winner
        else:
            # No teams - check per-player (original behavior)
            for i, count in enumerate(territory_counts):
                logger.debug(f"Player {i}: {count} territories (need {victory_threshold})")
                if count >= victory_threshold:
                    logger.info(f"DOMINATION VICTORY for Player {i}!")
                    self.winner = i
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   PLAYER {i + 1} WINS!")
                    self.add_message(f"   ({count} territories)")
                    self.add_message(f"============================")
                    return i

        logger.debug(f"No domination victory yet")
        return -1

    def _check_capital_assault_victory(self, territory_counts):
        """
        Check Capital Assault victory (last team/player standing).

        In Capital Assault mode, players are eliminated when their capital is captured.
        Victory is achieved when only one team (or player, if no teams) remains.

        Args:
            territory_counts (list): Territory count per player

        Returns:
            int: Winner player index, or -1 if no winner
        """
        # Get active players (those with at least one territory)
        active_players = [i for i, count in enumerate(territory_counts) if count > 0]

        logger.debug(f"Active players: {active_players}")

        # Check if only one team remains (team-based victory)
        if hasattr(self, 'player_teams') and self.player_teams:
            active_teams = set(self.player_teams[i] for i in active_players)
            logger.debug(f"Active teams: {active_teams}")

            if len(active_teams) == 1:
                # All remaining players are on same team - team wins
                winner = active_players[0]  # Use first active player as winner representative
                self.winner = winner
                self.phase = 'ended'
                team_num = self.player_teams[winner]
                self.add_message(f"")
                self.add_message(f"============================")
                self.add_message(f"   TEAM {team_num + 1} WINS!")
                self.add_message(f"   (Last team standing)")
                self.add_message(f"============================")
                logger.info(f"CAPITAL ASSAULT TEAM VICTORY for Team {team_num + 1}!")
                return winner
        else:
            # No teams - check for last player standing
            if len(active_players) == 1:
                winner = active_players[0]
                self.winner = winner
                self.phase = 'ended'
                self.add_message(f"")
                self.add_message(f"============================")
                self.add_message(f"   PLAYER {winner + 1} WINS!")
                self.add_message(f"   (Last player standing)")
                self.add_message(f"============================")
                logger.info(f"CAPITAL ASSAULT VICTORY for Player {winner + 1}!")
                return winner

        logger.debug(f"No capital assault victory yet - {len(active_players)} players/teams remaining")
        return -1

    def _check_total_conquest_victory(self, territory_counts):
        """
        Check Total Conquest victory (all territories on the map).

        Works team-wise: aggregates territory counts for all players on the same team.
        A team wins when their combined territory count equals all territories.

        Args:
            territory_counts (list): Territory count per player

        Returns:
            int: Winner player index (representative of winning team), or -1 if no winner
        """
        total_territories = len(self.territory_owners)  # Total territories on map

        # Check if teams are active - aggregate by team if so
        if hasattr(self, 'player_teams') and self.player_teams:
            # Build team territory counts
            team_counts = {}  # team_id -> total territories
            team_members = {}  # team_id -> list of player indices

            for player_id, count in enumerate(territory_counts):
                team_id = self.player_teams[player_id]
                if team_id not in team_counts:
                    team_counts[team_id] = 0
                    team_members[team_id] = []
                team_counts[team_id] += count
                team_members[team_id].append(player_id)

            # Check if any team owns all territories
            for team_id, total_count in team_counts.items():
                logger.debug(f"Team {team_id + 1}: {total_count}/{total_territories} territories")
                if total_count == total_territories:
                    # Use first active team member as winner representative
                    winner = team_members[team_id][0]
                    for member in team_members[team_id]:
                        if territory_counts[member] > 0:
                            winner = member
                            break

                    logger.info(f"TOTAL CONQUEST TEAM VICTORY for Team {team_id + 1}!")
                    self.winner = winner
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   TEAM {team_id + 1} WINS!")
                    self.add_message(f"   (Total conquest - all territories)")
                    self.add_message(f"============================")
                    return winner
        else:
            # No teams - check per-player (original behavior)
            for i, count in enumerate(territory_counts):
                logger.debug(f"Player {i}: {count}/{total_territories} territories")
                if count == total_territories:
                    logger.info(f"TOTAL CONQUEST VICTORY for Player {i}!")
                    self.winner = i
                    self.phase = 'ended'
                    self.add_message(f"")
                    self.add_message(f"============================")
                    self.add_message(f"   PLAYER {i + 1} WINS!")
                    self.add_message(f"   (Total conquest - all territories)")
                    self.add_message(f"============================")
                    return i

        logger.debug(f"No total conquest victory yet")
        return -1

    def eliminate_player(self, player_index):
        """
        Eliminate player and neutralize their territories (Capital Assault mode).

        Called when a player's capital is captured. All territories owned by the eliminated
        player become neutral, and all units and buildings are destroyed.

        Args:
            player_index (int): Index of the player to eliminate
        """
        # Get all territories owned by eliminated player
        player_territories = [t for t, owner in self.territory_owners.items()
                             if owner == player_index]

        logger.info(f"[CAPITAL ASSAULT] Eliminating Player {player_index + 1}")
        logger.info(f"[CAPITAL ASSAULT] Neutralizing {len(player_territories)} territories")

        for territory in player_territories:
            # 1. Destroy all buildings (uses existing method line 2343-2450+)
            self.destroy_buildings(territory, player_index, new_owner=-1)

            # 2. Remove all units
            # Clear garrison system (multi-player garrison dict)
            self.territory_garrisons[territory] = {}

            # Clear army unit tracking list
            if territory in self.army_units:
                self.army_units[territory] = []

            # Clear simple army counters
            self.armies[territory] = 0
            self.armies_unmoved[territory] = 0
            self.armies_moved[territory] = 0

            # 3. Convert to neutral
            self.territory_owners[territory] = -1

            # 4. Cancel training queues
            if territory in self.training_queue:
                del self.training_queue[territory]
            if territory in self.hero_training_queue:
                del self.hero_training_queue[territory]

        # Add message log
        self.add_message(f"")
        self.add_message(f"============================")
        self.add_message(f"Player {player_index + 1} ELIMINATED!")
        self.add_message(f"Capital conquered - all territories neutralized")
        self.add_message(f"============================")
        self.add_message(f"")
