# -*- coding: utf-8 -*-
# achievement_manager.py
# Achievement system: definitions, stat tracking, persistence, and checking

"""
Achievement Manager
===================

Singleton module that owns all achievement definitions, tracks cumulative stats,
persists earned achievements to config.json (via settings_manager), and checks
for newly unlocked achievements after each game.

Categories: General, Campaign, Training, Conquest
Reward types: None, 'title' (shown under profile name), 'icon' (selectable in profile)
"""

from datetime import datetime
from settings_manager import settings
from player_level import player_level_manager
from steam_integration import steam_manager
from utils.logger import get_logger

logger = get_logger(__name__)


# --- Achievement Definitions ---
# Each achievement has: id, name, description, category, icon path, reward info, unlock condition

ACHIEVEMENTS = [
    # === General Category ===
    {
        'id': 'tactician',
        'name': 'Tactician',
        'description': 'Finish 1000 games (Custom, Multiplayer, or Campaign).',
        'category': 'general',
        'icon': 'assets/achievements/RewardsIcons/TacticianIcon.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/TacticianIcon.png',
        'reward_name': 'Tactician Icon',
        'stat_key': 'games_finished',
        'stat_threshold': 1000,
    },
    {
        'id': 'halberdier',
        'name': 'Halberdier',
        'description': 'Train a total of 2000 Pikemen across all games.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Halberdier.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/Halberdier.png',
        'reward_name': 'Halberdier Icon',
        'stat_key': 'pikemen_trained_total',
        'stat_threshold': 2000,
    },
    {
        'id': 'ranger',
        'name': 'Ranger',
        'description': 'Train a total of 2000 Archers across all games.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Ranger.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/Ranger.png',
        'reward_name': 'Ranger Icon',
        'stat_key': 'archers_trained_total',
        'stat_threshold': 2000,
    },
    {
        'id': 'fighter',
        'name': 'Fighter',
        'description': 'Train a total of 2000 Swordsmen across all games.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Fighter.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/Fighter.png',
        'reward_name': 'Fighter Icon',
        'stat_key': 'swordsmen_trained_total',
        'stat_threshold': 2000,
    },
    {
        'id': 'knight',
        'name': 'Knight',
        'description': 'Train a total of 2000 Cavalry across all games.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Knight.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/Knight.png',
        'reward_name': 'Knight Icon',
        'stat_key': 'cavalry_trained_total',
        'stat_threshold': 2000,
    },
    # --- Player Level Achievements ---
    # These use the special stat_key 'player_level' which is resolved from
    # PlayerLevelManager rather than the cumulative stats dict.
    {
        'id': 'level_5',
        'name': 'Level 5',
        'description': 'Reach Player Level 5.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level5.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'player_level',
        'stat_threshold': 5,
    },
    {
        'id': 'level_10',
        'name': 'Level 10',
        'description': 'Reach Player Level 10.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level10.png',
        'reward_type': 'title',
        'reward_id': 'Scout',
        'stat_key': 'player_level',
        'stat_threshold': 10,
    },
    {
        'id': 'level_20',
        'name': 'Level 20',
        'description': 'Reach Player Level 20.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level20.png',
        'reward_type': 'title',
        'reward_id': 'Soldier',
        'stat_key': 'player_level',
        'stat_threshold': 20,
    },
    {
        'id': 'level_30',
        'name': 'Level 30',
        'description': 'Reach Player Level 30.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level30.png',
        'reward_type': 'title',
        'reward_id': 'Sergeant',
        'stat_key': 'player_level',
        'stat_threshold': 30,
    },
    {
        'id': 'level_40',
        'name': 'Level 40',
        'description': 'Reach Player Level 40.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level40.png',
        'reward_type': 'title',
        'reward_id': 'Corporal',
        'stat_key': 'player_level',
        'stat_threshold': 40,
    },
    {
        'id': 'level_50',
        'name': 'Level 50',
        'description': 'Reach Player Level 50.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level50.png',
        'reward_type': 'title',
        'reward_id': 'Lieutenant',
        'stat_key': 'player_level',
        'stat_threshold': 50,
    },
    {
        'id': 'level_75',
        'name': 'Level 75',
        'description': 'Reach Player Level 75.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level75.png',
        'reward_type': 'title',
        'reward_id': 'High Lieutenant',
        'stat_key': 'player_level',
        'stat_threshold': 75,
    },
    {
        'id': 'level_100',
        'name': 'Level 100',
        'description': 'Reach Player Level 100.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level100.png',
        'reward_type': 'title',
        'reward_id': 'Commander',
        'stat_key': 'player_level',
        'stat_threshold': 100,
    },
    {
        'id': 'level_150',
        'name': 'Level 150',
        'description': 'Reach Player Level 150.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level150.png',
        'reward_type': 'title',
        'reward_id': 'High Commander',
        'stat_key': 'player_level',
        'stat_threshold': 150,
    },
    {
        'id': 'level_200',
        'name': 'Level 200',
        'description': 'Reach Player Level 200.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level200.png',
        'reward_type': 'title',
        'reward_id': 'Captain',
        'stat_key': 'player_level',
        'stat_threshold': 200,
    },
    {
        'id': 'level_250',
        'name': 'Level 250',
        'description': 'Reach Player Level 250.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level250.png',
        'reward_type': 'title',
        'reward_id': 'Marshal',
        'stat_key': 'player_level',
        'stat_threshold': 250,
    },
    {
        'id': 'level_500',
        'name': 'Level 500',
        'description': 'Reach Player Level 500.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Level500.png',
        'reward_type': 'title',
        'reward_id': 'High Marshal',
        'stat_key': 'player_level',
        'stat_threshold': 500,
    },
    {
        'id': 'hero_slayer',
        'name': 'Hero Slayer',
        'description': 'Kill 25 Heroes in Custom or Multiplayer games.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/HeroSlayer.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'heroes_killed_total',
        'stat_threshold': 25,
    },
    {
        'id': 'kingslayer',
        'name': 'Kingslayer',
        'description': 'Kill 75 Heroes in Custom or Multiplayer games.',
        'category': 'general',
        'icon': 'assets/achievements/AchievementIcons/Kingslayer.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/HannasIcon.png',
        'reward_name': 'Hannas Icon',
        'stat_key': 'heroes_killed_total',
        'stat_threshold': 75,
    },
    # === Training Category ===
    {
        'id': 'apprentice',
        'name': 'Apprentice',
        'description': 'Defeat an AI opponent in a Custom Game.',
        'category': 'training',
        'icon': 'assets/achievements/AchievementIcons/OneAIWin.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'custom_game_ai_wins',
        'stat_threshold': 1,
    },
    {
        'id': 'initiate',
        'name': 'Initiate',
        'description': 'Win 10 custom games against AI opponents.',
        'category': 'training',
        'icon': 'assets/achievements/AchievementIcons/TenAIWin.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'custom_game_ai_wins',
        'stat_threshold': 10,
    },
    {
        'id': 'aspirant_soldier',
        'name': 'Aspirant Soldier',
        'description': 'Win 100 custom games against AI opponents.',
        'category': 'training',
        'icon': 'assets/achievements/AchievementIcons/HundredAIWin.png',
        'reward_type': 'title',
        'reward_id': 'Aspirant Soldier',
        'stat_key': 'custom_game_ai_wins',
        'stat_threshold': 100,
    },
    {
        'id': 'proven_soldier',
        'name': 'Proven Soldier',
        'description': 'Win 200 custom games against AI opponents.',
        'category': 'training',
        'icon': 'assets/achievements/AchievementIcons/SwordsmanIcon.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/AchievementIcons/SwordsmanIcon.png',
        'reward_name': 'Swordsman Icon',
        'stat_key': 'custom_game_ai_wins',
        'stat_threshold': 200,
    },
    # === Conquest Category (Multiplayer Wins) ===
    {
        'id': 'mp_first_win',
        'name': 'A Step Into the World',
        'description': 'Win a multiplayer game.',
        'category': 'conquest',
        'icon': 'assets/achievements/AchievementIcons/OneMultiplayerWin.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'multiplayer_wins',
        'stat_threshold': 1,
    },
    {
        'id': 'mp_contender',
        'name': 'Contender',
        'description': 'Win 10 multiplayer games.',
        'category': 'conquest',
        'icon': 'assets/achievements/AchievementIcons/TenMultiplayerWins.png',
        'reward_type': 'title',
        'reward_id': 'Contender',
        'stat_key': 'multiplayer_wins',
        'stat_threshold': 10,
    },
    {
        'id': 'mp_high_contender',
        'name': 'High Contender',
        'description': 'Win 50 multiplayer games.',
        'category': 'conquest',
        'icon': 'assets/achievements/AchievementIcons/FiftyMultiplayerWins.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/Conquest1Icon.png',
        'reward_name': 'Desolation Icon',
        'stat_key': 'multiplayer_wins',
        'stat_threshold': 50,
    },
    {
        'id': 'mp_rival',
        'name': 'Rival',
        'description': 'Win 100 multiplayer games.',
        'category': 'conquest',
        'icon': 'assets/achievements/AchievementIcons/HundredMultiplayerWins.png',
        'reward_type': 'title',
        'reward_id': 'Rival',
        'stat_key': 'multiplayer_wins',
        'stat_threshold': 100,
    },
    {
        'id': 'mp_conqueror',
        'name': 'Conqueror',
        'description': 'Win 500 multiplayer games.',
        'category': 'conquest',
        'icon': 'assets/achievements/AchievementIcons/FiveHundredMultiplayerWins.png',
        'reward_type': 'title',
        'reward_id': 'Conqueror',
        'reward_type_2': 'icon',
        'reward_id_2': 'assets/achievements/RewardsIcons/Conquest2Icon.png',
        'reward_name_2': 'Fiery Desolation Icon',
        'stat_key': 'multiplayer_wins',
        'stat_threshold': 500,
    },
    {
        'id': 'mp_devastator',
        'name': 'Devastator',
        'description': 'Win 1000 multiplayer games.',
        'category': 'conquest',
        'icon': 'assets/achievements/RewardsIcons/Conquest3Icon.png',
        'reward_type': 'title',
        'reward_id': 'Devastator',
        'reward_type_2': 'icon',
        'reward_id_2': 'assets/achievements/RewardsIcons/Conquest3Icon.png',
        'reward_name_2': 'The Destructor Icon',
        'stat_key': 'multiplayer_wins',
        'stat_threshold': 1000,
    },
    # === Campaign Category ===
    {
        'id': 'campaign_mission_1',
        'name': 'Rise of Affrancia',
        'description': 'Complete Chapter 1: Rise of Affrancia.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign1Achiev.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'campaign_mission_1_completed',
        'stat_threshold': 1,
    },
    {
        'id': 'campaign_mission_2',
        'name': 'Early Eastern Conquests',
        'description': 'Complete Chapter 2: Early Eastern Conquests.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign2Achiev.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'campaign_mission_2_completed',
        'stat_threshold': 1,
    },
    {
        'id': 'campaign_mission_2_bonus',
        'name': 'The Taller They Are...',
        'description': 'Attack the Chiefdom of Valeonia before any other faction and win Chapter 2.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign2BonusAchiev.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/LordVenderfornet.png',
        'reward_name': 'Prime Lord Venderfornet Icon',
        'stat_key': 'campaign_mission_2_bonus',
        'stat_threshold': 1,
    },
    {
        'id': 'campaign_mission_3',
        'name': 'Storms above the West',
        'description': 'Complete Chapter 3: Storms above the West.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign3Achiev.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'campaign_mission_3_completed',
        'stat_threshold': 1,
    },
    {
        'id': 'campaign_mission_3_bonus',
        'name': 'Storming Nordia',
        'description': 'Defeat the Warlords of Nordia in Chapter 3 without the Kingdom of Affrancia ever dropping below 5 territories, then complete the mission.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign3BonusAchiev.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/LeiIcon.png',
        'reward_name': 'Marshal Michen Lei Icon',
        'stat_key': 'campaign_mission_3_bonus',
        'stat_threshold': 1,
    },
    # Mission 4: Domination — completion
    {
        'id': 'campaign_mission_4',
        'name': 'Domination',
        'description': 'Complete Chapter 4: Domination.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign4Achiev.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'campaign_mission_4_completed',
        'stat_threshold': 1,
    },
    # Mission 4 Bonus — defeat Ahtep Empire and win
    {
        'id': 'campaign_mission_4_bonus',
        'name': 'Empire Who?',
        'description': 'Defeat the Ahtep Empire and win Chapter 4: Domination.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign4Bonus.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/regnus.png',
        'reward_name': 'Regnus Aevencourne Icon',
        'stat_key': 'campaign_mission_4_bonus',
        'stat_threshold': 1,
    },
    # Mission 5: The First War — completion
    {
        'id': 'campaign_mission_5',
        'name': 'The First War',
        'description': 'Complete Chapter 5: The First War.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign5Achiev.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'campaign_mission_5_completed',
        'stat_threshold': 1,
    },
    # Mission 5 Bonus — conquer all Azincourne Empire territories and win
    {
        'id': 'campaign_mission_5_bonus',
        'name': 'Change of Command',
        'description': 'Conquer all territories controlled by the Empire of Azincourne and win Chapter 5: The First War.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign5BonusAchiev.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/AlexiusBrennhen.png',
        'reward_name': 'Alexius Brennhen',
        'stat_key': 'campaign_mission_5_bonus',
        'stat_threshold': 1,
    },
    # Mission 6: The Second War — completion
    {
        'id': 'campaign_mission_6',
        'name': 'The Second War',
        'description': 'Complete Chapter 6: The Second War.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign6Achiev.png',
        'reward_type': None,
        'reward_id': None,
        'stat_key': 'campaign_mission_6_completed',
        'stat_threshold': 1,
    },
    # Mission 6 Bonus: Red World — conquer all Northern Powers territories and win
    {
        'id': 'campaign_mission_6_bonus',
        'name': 'Red World',
        'description': 'Conquer all territories owned by Northern Powers and win Chapter 6.',
        'category': 'campaign',
        'icon': 'assets/achievements/AchievementIcons/Campaign6BonusAchiev.png',
        'reward_type': 'icon',
        'reward_id': 'assets/achievements/RewardsIcons/KalanIcon.png',
        'reward_name': 'Lord Kalan',
        'stat_key': 'campaign_mission_6_bonus',
        'stat_threshold': 1,
    },
]

# Valid categories for filtering
CATEGORIES = ['general', 'campaign', 'training', 'conquest']
CATEGORY_LABELS = {
    'general': 'General',
    'campaign': 'Campaign',
    'training': 'Training',
    'conquest': 'Conquest',
}

# All reward icons that can appear in the profile (includes future/undefined ones)
# These show as locked with "Coming soon" if no achievement references them yet
ALL_REWARD_ICON_PATHS = [
    'assets/achievements/AchievementIcons/SwordsmanIcon.png',
    'assets/achievements/RewardsIcons/TacticianIcon.png',
    'assets/achievements/RewardsIcons/Conquest1Icon.png',
    'assets/achievements/RewardsIcons/Conquest2Icon.png',
    'assets/achievements/RewardsIcons/Conquest3Icon.png',
    'assets/achievements/RewardsIcons/HannasIcon.png',
    'assets/achievements/RewardsIcons/KalanIcon.png',
    'assets/achievements/RewardsIcons/LeiIcon.png',
    'assets/achievements/RewardsIcons/LordVenderfornet.png',
    'assets/achievements/RewardsIcons/Halberdier.png',
    'assets/achievements/RewardsIcons/Ranger.png',
    'assets/achievements/RewardsIcons/Fighter.png',
    'assets/achievements/RewardsIcons/Knight.png',
    'assets/achievements/RewardsIcons/regnus.png',
    'assets/achievements/RewardsIcons/AlexiusBrennhen.png',
]

# Build lookup: reward_icon_path -> achievement that awards it (or None)
# Checks both primary reward_type and secondary reward_type_2 for dual-reward achievements
_REWARD_ICON_TO_ACHIEVEMENT = {}
for _ach in ACHIEVEMENTS:
    if _ach['reward_type'] == 'icon' and _ach['reward_id']:
        _REWARD_ICON_TO_ACHIEVEMENT[_ach['reward_id']] = _ach
    if _ach.get('reward_type_2') == 'icon' and _ach.get('reward_id_2'):
        _REWARD_ICON_TO_ACHIEVEMENT[_ach['reward_id_2']] = _ach

# Build lookup: title string -> achievement that awards it
# Checks both primary reward_type and secondary reward_type_2 for dual-reward achievements
_TITLE_TO_ACHIEVEMENT = {}
for _ach in ACHIEVEMENTS:
    if _ach['reward_type'] == 'title' and _ach['reward_id']:
        _TITLE_TO_ACHIEVEMENT[_ach['reward_id']] = _ach
    if _ach.get('reward_type_2') == 'title' and _ach.get('reward_id_2'):
        _TITLE_TO_ACHIEVEMENT[_ach['reward_id_2']] = _ach

# All possible titles (from achievements that award titles, including dual-reward secondary titles)
ALL_TITLES = []
for _ach in ACHIEVEMENTS:
    if _ach['reward_type'] == 'title' and _ach['reward_id']:
        ALL_TITLES.append(_ach['reward_id'])
    if _ach.get('reward_type_2') == 'title' and _ach.get('reward_id_2'):
        ALL_TITLES.append(_ach['reward_id_2'])


class AchievementManager:
    """
    Singleton achievement manager. Tracks stats, checks for newly earned
    achievements, and provides queries for UI display.
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
        """Load achievement stats and earned data from settings_manager"""
        self.stats = settings.get_achievement_stats().copy()
        self.earned = settings.get_earned_achievements().copy()
        logger.info(f"Achievements loaded: {len(self.earned)} earned, stats={self.stats}")

    def sync_to_steam(self):
        """Push all locally-earned achievements to Steam.
        Call once after Steam SDK initializes to catch any achievements
        earned offline or before the portal had them defined."""
        if not steam_manager.is_available:
            logger.info("Steam sync skipped — Steam not available")
            return
        logger.info(f"Steam sync: checking {len(self.earned)} locally-earned achievements: {list(self.earned.keys())}")
        synced = 0
        for ach_id in self.earned:
            already = steam_manager.is_achievement_unlocked(ach_id)
            logger.info(f"  Steam achievement '{ach_id}': already_unlocked={already}")
            if not already:
                result = steam_manager.unlock_achievement(ach_id)
                logger.info(f"  Unlock attempt for '{ach_id}': result={result}")
                if result:
                    synced += 1
        logger.info(f"Steam sync complete: {synced} achievements pushed")

    def save(self):
        """Persist achievement data via settings_manager"""
        settings.set_achievement_stats(self.stats)
        settings.set_earned_achievements(self.earned)
        settings.save()

    def record_game_result(self, game):
        """
        Analyze a completed game and update stats. Returns list of newly earned achievements.

        Tracks all finished games (win or loss) for the games_finished counter.
        Detects game mode (campaign/custom/multiplayer), checks if the human player won,
        and increments mode-specific win counters only on victory.
        """
        gs = game.game_state

        # Accumulate per-unit-type training stats even on premature quit
        # (these achievements aren't tied to game completion)
        human_player_index = None
        for i in range(gs.num_players):
            if not gs.player_is_ai[i]:
                human_player_index = i
                break

        if human_player_index is not None and human_player_index in gs.player_stats:
            p_stats = gs.player_stats[human_player_index]
            # Unit training counts (all game modes)
            for gs_key, ach_key in [('pikemen_trained', 'pikemen_trained_total'),
                                     ('archers_trained', 'archers_trained_total'),
                                     ('swordsmen_trained', 'swordsmen_trained_total'),
                                     ('cavalry_trained', 'cavalry_trained_total')]:
                count = p_stats.get(gs_key, 0)
                if count > 0:
                    self.stats[ach_key] = self.stats.get(ach_key, 0) + count

            # Hero kills (Custom and Multiplayer only, not Campaign)
            mission = getattr(game, 'tutorial_mission', None)
            is_campaign = mission is not None and hasattr(mission, 'mission_id')
            if not is_campaign:
                hero_kills = p_stats.get('heroes_killed', 0)
                if hero_kills > 0:
                    self.stats['heroes_killed_total'] = self.stats.get('heroes_killed_total', 0) + hero_kills

        if gs.phase != 'ended':
            # Game quit prematurely - save training progress, check training achievements only
            newly_earned = self._check_new_achievements()
            self.save()
            return newly_earned

        # Track all finished games regardless of outcome (for Tactician achievement)
        self.stats['games_finished'] = self.stats.get('games_finished', 0) + 1
        logger.info(f"Game finished. Total games: {self.stats['games_finished']}")

        human_won = human_player_index is not None and gs.winner == human_player_index

        # Determine game mode
        # Campaign detection via mission_id attribute (campaign_map is unreliable -
        # Mission 3 uses the default in-game map so campaign_map=None)
        mission = getattr(game, 'tutorial_mission', None)
        is_campaign = mission is not None and hasattr(mission, 'mission_id')
        is_multiplayer = getattr(game, 'multiplayer_mode', False) or \
                         getattr(game, 'network_connection', None) is not None
        is_custom = not is_campaign and not is_multiplayer

        # Increment mode-specific total game counters (win or loss) for win rate stats
        has_ai_opponent = False
        if is_custom:
            has_ai_opponent = any(
                gs.player_is_ai[i] for i in range(gs.num_players) if i != human_player_index
            )
            if has_ai_opponent:
                self.stats['custom_games_ai_finished'] = self.stats.get('custom_games_ai_finished', 0) + 1
                logger.info(f"Custom game (vs AI) finished. Total: {self.stats['custom_games_ai_finished']}")
        elif is_multiplayer:
            self.stats['multiplayer_games_finished'] = self.stats.get('multiplayer_games_finished', 0) + 1
            logger.info(f"Multiplayer game finished. Total: {self.stats['multiplayer_games_finished']}")

        # Increment win-specific stat counters only if human won
        if human_won:
            if is_custom and has_ai_opponent:
                self.stats['custom_game_ai_wins'] = self.stats.get('custom_game_ai_wins', 0) + 1
                logger.info(f"Custom game AI win recorded. Total: {self.stats['custom_game_ai_wins']}")
            elif is_multiplayer:
                self.stats['multiplayer_wins'] = self.stats.get('multiplayer_wins', 0) + 1
                logger.info(f"Multiplayer win recorded. Total: {self.stats['multiplayer_wins']}")
            elif is_campaign:
                # Set mission-specific completion stat
                mission_id = mission.mission_id
                completion_key = f'campaign_{mission_id}_completed'
                self.stats[completion_key] = 1
                logger.info(f"Campaign mission completed: {mission_id} (stat: {completion_key})")

                # Bridge bonus conditions from mission to stats
                if hasattr(mission, 'get_bonus_conditions'):
                    bonus_conditions = mission.get_bonus_conditions()
                    for stat_key, condition_met in bonus_conditions.items():
                        if condition_met:
                            self.stats[stat_key] = 1
                            logger.info(f"Campaign bonus condition met: {stat_key}")

        # Check for newly earned achievements (runs for wins AND losses)
        newly_earned = self._check_new_achievements()
        self.save()
        return newly_earned

    def _check_new_achievements(self):
        """Compare current stats against all achievement thresholds. Return newly earned list."""
        newly_earned = []
        for ach in ACHIEVEMENTS:
            ach_id = ach['id']
            if ach_id in self.earned:
                continue  # Already earned
            # Level achievements pull from PlayerLevelManager, not cumulative stats
            if ach['stat_key'] == 'player_level':
                stat_value = player_level_manager.get_level()
            else:
                stat_value = self.stats.get(ach['stat_key'], 0)
            if stat_value >= ach['stat_threshold']:
                timestamp = datetime.now().isoformat()
                self.earned[ach_id] = timestamp
                newly_earned.append(ach)
                logger.info(f"Achievement earned: {ach['name']} (id={ach_id})")
                # Sync to Steam (no-op if Steam unavailable)
                steam_manager.unlock_achievement(ach_id)
        return newly_earned

    # --- Query methods for UI ---

    def get_all_achievements(self):
        """Return all achievement definitions with earned status, timestamp, and progress"""
        result = []
        for ach in ACHIEVEMENTS:
            entry = ach.copy()
            entry['earned'] = ach['id'] in self.earned
            entry['earned_timestamp'] = self.earned.get(ach['id'], None)
            # Include current progress toward the stat threshold
            # Level achievements pull from PlayerLevelManager, not cumulative stats
            if ach['stat_key'] == 'player_level':
                entry['stat_progress'] = player_level_manager.get_level()
            else:
                entry['stat_progress'] = self.stats.get(ach['stat_key'], 0)
            result.append(entry)
        return result

    def get_achievements_by_category(self, category):
        """Return achievements filtered by category"""
        return [a for a in self.get_all_achievements() if a['category'] == category]

    def is_earned(self, achievement_id):
        """Check if a specific achievement has been earned"""
        return achievement_id in self.earned

    def get_earned_timestamp(self, achievement_id):
        """Get ISO timestamp when achievement was earned (or None)"""
        return self.earned.get(achievement_id, None)

    def get_unlocked_titles(self):
        """Return list of title strings from earned achievements (checks both primary and secondary rewards)"""
        titles = []
        for ach in ACHIEVEMENTS:
            if ach['id'] not in self.earned:
                continue
            if ach['reward_type'] == 'title':
                titles.append(ach['reward_id'])
            if ach.get('reward_type_2') == 'title':
                titles.append(ach['reward_id_2'])
        return titles

    def get_unlocked_reward_icons(self):
        """Return list of icon paths from earned achievements (checks both primary and secondary rewards)"""
        icons = []
        for ach in ACHIEVEMENTS:
            if ach['id'] not in self.earned:
                continue
            if ach['reward_type'] == 'icon':
                icons.append(ach['reward_id'])
            if ach.get('reward_type_2') == 'icon':
                icons.append(ach['reward_id_2'])
        return icons

    def get_selected_title(self):
        """Get currently selected display title from settings"""
        return settings.get_selected_title()

    def set_selected_title(self, title):
        """Set the active display title and persist"""
        settings.set_selected_title(title)
        settings.save()

    def get_reward_icon_info(self, icon_path):
        """
        Get info about a reward icon for the profile tooltip.
        Returns (is_unlocked, tooltip_text).
        """
        ach = _REWARD_ICON_TO_ACHIEVEMENT.get(icon_path)
        if ach is None:
            # No achievement defined for this icon yet
            return False, "Coming soon"
        is_unlocked = ach['id'] in self.earned
        if is_unlocked:
            return True, ach['name']
        else:
            return False, f"Unlock: {ach['name']}"

    def get_title_info(self, title):
        """
        Get info about a title for the profile tooltip.
        Returns (is_unlocked, tooltip_text).
        """
        ach = _TITLE_TO_ACHIEVEMENT.get(title)
        if ach is None:
            return False, "Coming soon"
        is_unlocked = ach['id'] in self.earned
        if is_unlocked:
            return True, ach['name']
        else:
            return False, f"Unlock: {ach['name']}"

    def get_stat_value(self, stat_key):
        """Get a cumulative stat value"""
        return self.stats.get(stat_key, 0)


# Global singleton instance
achievement_manager = AchievementManager()
