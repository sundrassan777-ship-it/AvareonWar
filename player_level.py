# -*- coding: utf-8 -*-
# player_level.py
# Player Level system: XP tracking, level calculation, persistence

"""
Player Level Manager
====================

Singleton module that manages the player's persistent level and XP.
XP is earned from gameplay actions (tracked via game_state player_stats)
and end-of-game bonuses. Level progression uses a tiered XP-per-level formula.

XP Sources (per action, tracked during gameplay via _track_stat):
- Unit trained: +2 XP
- Building built: +2 XP
- Neutral territory conquered: +2 XP
- Enemy territory conquered (no battle): +4 XP
- Enemy territory conquered (with battle): +8 XP
- Hero trained: +4 XP
- Hero killed: +10 XP per hero
- Active hero ability used: +2 XP
- Technology researched: +4 XP

End-of-game bonuses:
- Custom/MP defeat: +25 XP
- Custom/MP victory: +50 XP (doubled to 100 if enemy team has >= as many human players)
- Campaign first-time mission win: +100 XP

Eligibility:
- Campaign: always eligible
- Custom/MP: only if at least 1 enemy player exists
- No XP on premature quit (game not ended)

Halving:
- If player's team has MORE players than enemy team, all XP is halved
"""

from settings_manager import settings
from utils.logger import get_logger

logger = get_logger(__name__)


# --- Level Progression Formula ---
# Each tier: (max_level_in_tier, xp_per_level)
# Level 1 requires 0 XP. Reaching level 2 requires 100 XP, etc.
XP_TIERS = [
    (10, 100),       # Levels 1-10: 100 XP per level
    (20, 250),       # Levels 11-20: 250 XP per level
    (40, 500),       # Levels 21-40: 500 XP per level
    (100, 1000),     # Levels 41-100: 1000 XP per level
    (200, 2500),     # Levels 101-200: 2500 XP per level
    (500, 5000),     # Levels 201-500: 5000 XP per level
    (10000, 10000),  # Levels 501-10000: 10000 XP per level
]
MAX_LEVEL = 10000

# XP amounts per gameplay action (used by game_state hooks via _track_stat)
XP_UNIT_TRAINED = 2
XP_BUILDING_BUILT = 2
XP_NEUTRAL_CONQUEST = 2
XP_ENEMY_UNCONTESTED_CONQUEST = 4
XP_BATTLE_CONQUEST = 8
XP_HERO_TRAINED = 4
XP_HERO_KILLED = 10       # Per hero killed
XP_HERO_ABILITY_USED = 2
XP_TECH_RESEARCHED = 4

# End-of-game bonus XP
XP_DEFEAT_BONUS = 25
XP_VICTORY_BONUS = 50
XP_MULTIPLAYER_VICTORY_BONUS = 100   # Replaces 50 when enemy has >= as many humans
XP_CAMPAIGN_FIRST_WIN = 100

# Anti-win-farming: if all enemies were eliminated via disconnect and had less than
# this XP from gameplay actions, the game "doesn't count" (no XP awarded at all)
DISCONNECT_FARMING_XP_THRESHOLD = 50


# --- Cumulative XP cache ---
# Maps level -> total cumulative XP needed to reach that level (computed lazily)
_xp_cache = {}


def xp_for_level(level):
    """
    Calculate the total cumulative XP required to reach a given level.
    Level 1 requires 0 XP. Level 2 requires 100 XP. Etc.
    Results are cached for performance.
    """
    if level <= 1:
        return 0
    if level in _xp_cache:
        return _xp_cache[level]

    # Walk through tiers accumulating XP
    total_xp = 0
    current_level = 1
    prev_tier_max = 0

    for tier_max, xp_per_level in XP_TIERS:
        # How many levels this tier covers from current_level
        tier_start = max(current_level, prev_tier_max + 1) if prev_tier_max > 0 else current_level
        tier_end = min(level, tier_max + 1)  # +1 because reaching level N means completing level N-1

        if tier_start >= tier_end:
            prev_tier_max = tier_max
            continue

        levels_in_tier = tier_end - tier_start
        total_xp += levels_in_tier * xp_per_level
        current_level = tier_end
        prev_tier_max = tier_max

        if current_level >= level:
            break

    _xp_cache[level] = total_xp
    return total_xp


def level_from_xp(total_xp):
    """
    Determine the player's level given their total accumulated XP.
    Returns an integer level (1 to MAX_LEVEL).
    """
    if total_xp <= 0:
        return 1

    # Walk through tiers to find which level the XP corresponds to
    remaining_xp = total_xp
    current_level = 1
    prev_tier_max = 0

    for tier_max, xp_per_level in XP_TIERS:
        tier_start = prev_tier_max + 1 if prev_tier_max > 0 else 1
        levels_in_tier = tier_max - tier_start + 1
        tier_total_xp = levels_in_tier * xp_per_level

        if remaining_xp < tier_total_xp:
            # Level falls within this tier
            levels_gained = remaining_xp // xp_per_level
            current_level = tier_start + levels_gained
            return min(current_level, MAX_LEVEL)

        remaining_xp -= tier_total_xp
        current_level = tier_max + 1
        prev_tier_max = tier_max

    # XP exceeds all defined tiers — cap at MAX_LEVEL
    return MAX_LEVEL


def get_progress_for_xp(total_xp):
    """
    Calculate level progress info for a given total XP amount.
    Returns dict: {level, xp_into_level, xp_for_next, progress_fraction}
    Used for UI bar fill calculations.
    """
    level = level_from_xp(total_xp)
    xp_at_current = xp_for_level(level)
    xp_at_next = xp_for_level(level + 1) if level < MAX_LEVEL else xp_at_current
    xp_into_level = total_xp - xp_at_current
    xp_for_next = xp_at_next - xp_at_current

    if level >= MAX_LEVEL or xp_for_next <= 0:
        progress_fraction = 1.0
    else:
        progress_fraction = min(1.0, xp_into_level / xp_for_next)

    return {
        'level': level,
        'xp_into_level': xp_into_level,
        'xp_for_next': xp_for_next,
        'progress_fraction': progress_fraction,
    }


class PlayerLevelManager:
    """
    Singleton player level manager. Tracks persistent XP and level,
    calculates end-of-game XP awards, and provides progress queries for UI.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.load()

    def load(self):
        """Load player XP and campaign completion data from settings_manager"""
        self.total_xp = settings.get('player_xp', 0)
        self.campaign_missions_xp_claimed = list(
            settings.get('campaign_missions_xp_claimed', [])
        )
        logger.info(
            f"Player level loaded: XP={self.total_xp}, "
            f"level={self.get_level()}, "
            f"campaign_claimed={self.campaign_missions_xp_claimed}"
        )

    def save(self):
        """Persist player XP and campaign data via settings_manager"""
        settings.set('player_xp', self.total_xp)
        settings.set('campaign_missions_xp_claimed', self.campaign_missions_xp_claimed)
        settings.save()

    def get_level(self):
        """Return current player level"""
        return level_from_xp(self.total_xp)

    def get_xp(self):
        """Return total accumulated XP"""
        return self.total_xp

    def get_progress(self):
        """
        Get current level progress for UI display.
        Returns dict: {level, xp_into_level, xp_for_next, progress_fraction}
        """
        return get_progress_for_xp(self.total_xp)

    def record_game_xp(self, game):
        """
        Calculate and persist XP earned from a completed game.
        Called from show_recap_if_ended() after achievement recording.

        Returns dict with:
          xp_earned: total XP earned this game (after halving)
          old_level: player level before this game
          new_level: player level after this game
          old_xp: total XP before this game
          new_xp: total XP after this game

        Returns xp_earned=0 if not eligible or no XP earned.
        Action XP is awarded even on premature quit; end-of-game bonuses require game to finish.
        """
        gs = game.game_state
        old_xp = self.total_xp
        old_level = self.get_level()
        no_xp_result = {
            'xp_earned': 0, 'old_level': old_level, 'new_level': old_level,
            'old_xp': old_xp, 'new_xp': old_xp,
        }
        game_finished = (gs.phase == 'ended')

        # Find the human player index
        human_index = self._find_human_index(game)
        if human_index is None:
            return no_xp_result

        # Detect game mode
        mission = getattr(game, 'tutorial_mission', None)
        is_campaign = mission is not None and hasattr(mission, 'mission_id')
        is_multiplayer = (getattr(game, 'multiplayer_mode', False) or
                          getattr(game, 'network_connection', None) is not None)

        # Eligibility check: Custom/MP require at least 1 enemy player
        if not is_campaign:
            if not self._has_enemy_player(gs, human_index):
                logger.info("No enemy players found — no XP earned")
                return no_xp_result

        # Anti-win-farming: if all enemies eliminated via disconnect with <50 XP, no XP at all
        if not is_campaign and is_multiplayer:
            if self._is_disconnect_farming(gs, human_index):
                logger.info("Victory triggered by low-XP disconnect elimination — no XP awarded")
                return no_xp_result

        # Read action XP accumulated during gameplay (via _track_stat hooks)
        action_xp = gs.player_stats.get(human_index, {}).get('xp_earned', 0)

        # End-of-game bonus only if the game finished (not on premature quit)
        bonus_xp = 0
        if game_finished:
            bonus_xp = self._calculate_end_bonus(
                game, gs, human_index, is_campaign, is_multiplayer, mission
            )

        total_earned = action_xp + bonus_xp

        # Apply halving if player's team outnumbers enemy team
        if self._should_halve(gs, human_index):
            total_earned = total_earned // 2
            logger.info(f"XP halved due to team size advantage: {action_xp + bonus_xp} -> {total_earned}")

        # Cap at max level — don't award XP beyond what's needed
        if self.get_level() >= MAX_LEVEL:
            total_earned = 0

        # Persist
        self.total_xp += total_earned
        new_level = self.get_level()
        self.save()

        logger.info(
            f"Game XP recorded: action={action_xp}, bonus={bonus_xp}, "
            f"total_earned={total_earned}, level {old_level}->{new_level}"
        )

        return {
            'xp_earned': total_earned,
            'old_level': old_level,
            'new_level': new_level,
            'old_xp': old_xp,
            'new_xp': self.total_xp,
        }

    def _find_human_index(self, game):
        """
        Find the local human player index.
        In multiplayer, uses local_player_index. Otherwise, finds first non-AI player.
        """
        gs = game.game_state
        # Multiplayer: use local_player_index if available
        local_idx = getattr(gs, 'local_player_index', None)
        if local_idx is not None and not gs.player_is_ai[local_idx]:
            return local_idx

        # Single-player: find first human
        for i in range(gs.num_players):
            if not gs.player_is_ai[i]:
                return i
        return None

    def _is_disconnect_farming(self, gs, human_index):
        """
        Check if victory was caused by disconnect elimination of low-XP enemies.

        Returns True (game "doesn't count") only if ALL enemies were eliminated
        via disconnect AND all had < DISCONNECT_FARMING_XP_THRESHOLD XP from actions.
        If any enemy was defeated normally or had meaningful gameplay, returns False.
        """
        disconnect_elims = getattr(gs, 'disconnect_eliminations', set())
        if not disconnect_elims:
            return False  # No disconnect eliminations occurred

        my_team = gs.player_teams[human_index]
        # Check if all enemy players were disconnect-eliminated
        for p in range(gs.num_players):
            if p == human_index:
                continue
            if gs.player_teams[p] == my_team:
                continue  # Ally, skip
            # This is an enemy — was it eliminated by disconnect?
            if p not in disconnect_elims:
                return False  # At least one enemy was NOT disconnect-eliminated

        # All enemies were disconnect-eliminated. Check if any had meaningful gameplay
        for p in disconnect_elims:
            if gs.player_teams[p] == my_team:
                continue  # Skip allied disconnects
            xp = gs.player_stats.get(p, {}).get('xp_earned', 0)
            if xp >= DISCONNECT_FARMING_XP_THRESHOLD:
                return False  # Enemy had meaningful gameplay

        # All disconnected enemies had < threshold XP — this is farming
        logger.info(f"Disconnect farming detected: all enemies disconnect-eliminated with <{DISCONNECT_FARMING_XP_THRESHOLD} XP")
        return True

    def _has_enemy_player(self, gs, human_index):
        """Check if at least 1 enemy player (different team) exists"""
        my_team = gs.player_teams[human_index]
        for i in range(gs.num_players):
            if gs.player_teams[i] != my_team:
                return True
        return False

    def _should_halve(self, gs, human_index):
        """
        Check if XP should be halved due to team size advantage.
        Halved when player's team has MORE players than any enemy team.
        Based on initial team sizes (player_teams list), not current alive count.
        """
        my_team = gs.player_teams[human_index]

        # Count players per team
        team_sizes = {}
        for i in range(gs.num_players):
            team = gs.player_teams[i]
            team_sizes[team] = team_sizes.get(team, 0) + 1

        my_team_size = team_sizes.get(my_team, 1)

        # Check if any enemy team has fewer players
        # (halve if ALL enemy teams are smaller, meaning we outnumber everyone)
        enemy_teams = {t: s for t, s in team_sizes.items() if t != my_team}
        if not enemy_teams:
            return False

        # Halve if my team size > total enemy player count
        # e.g. 3v1: my_team=3, enemies=1 -> halve
        # e.g. 2v2: my_team=2, enemies=2 -> no halve
        # e.g. 2v1v1: my_team=2, enemies=2 (1+1) -> no halve
        total_enemy_players = sum(enemy_teams.values())
        return my_team_size > total_enemy_players

    def _calculate_end_bonus(self, game, gs, human_index, is_campaign,
                             is_multiplayer, mission):
        """Calculate end-of-game bonus XP"""
        human_won = gs.winner == human_index

        if is_campaign:
            # Campaign: 100 XP for first-time win, 0 otherwise
            if not human_won:
                return 0
            mission_id = getattr(mission, 'mission_id', None)
            if mission_id is None:
                return 0
            if mission_id in self.campaign_missions_xp_claimed:
                # Already claimed first-time bonus for this mission
                logger.info(f"Campaign mission {mission_id} already claimed — no bonus XP")
                return 0
            # First-time win — award bonus and record
            self.campaign_missions_xp_claimed.append(mission_id)
            logger.info(f"Campaign first-time win bonus: +{XP_CAMPAIGN_FIRST_WIN} XP (mission {mission_id})")
            return XP_CAMPAIGN_FIRST_WIN

        # Custom Game or Multiplayer
        if not human_won:
            return XP_DEFEAT_BONUS

        # Victory bonus — check for multiplayer doubling
        if is_multiplayer:
            # Count human players on each side
            my_team = gs.player_teams[human_index]
            my_team_humans = sum(
                1 for i in range(gs.num_players)
                if gs.player_teams[i] == my_team and not gs.player_is_ai[i]
            )
            enemy_humans = sum(
                1 for i in range(gs.num_players)
                if gs.player_teams[i] != my_team and not gs.player_is_ai[i]
            )
            # Doubled when enemy team has >= as many human players as your team
            if enemy_humans >= my_team_humans:
                logger.info(
                    f"Multiplayer victory doubled: enemy humans ({enemy_humans}) "
                    f">= my team humans ({my_team_humans})"
                )
                return XP_MULTIPLAYER_VICTORY_BONUS

        return XP_VICTORY_BONUS


# Global singleton instance
player_level_manager = PlayerLevelManager()
