# -*- coding: utf-8 -*-
# campaign_mission_5.py
# Campaign Mission 5: Placeholder
# Infrastructure stub — implements the full mission duck-typed interface
# with no-op implementations. To be fleshed out with actual mission logic.

import pygame
import map_data
from utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# MISSION CONFIGURATION (placeholder — update when designing actual mission)
# ============================================================================

MISSION_5_TERRITORIES = [
    "Aelatania", "Lobardia", "Venexia", "Valeonia",
]

FACTION_TERRITORIES = {
    0: ["Aelatania"],
    1: ["Lobardia"],
    2: ["Venexia"],
    3: ["Valeonia"],
}

PLAYER_COLORS = [
    (100, 150, 255),   # Player 0: Blue (human)
    (100, 200, 100),   # Player 1: Green
    (255, 100, 100),   # Player 2: Red
    (255, 220, 100),   # Player 3: Yellow
]

FACTION_NAMES = {
    0: None,
    1: "Faction B",
    2: "Faction C",
    3: "Faction D",
}

STARTING_GOLD = {
    0: 500,
    1: 500,
    2: 500,
    3: 500,
}


class Mission5:
    """
    Campaign Mission 5 — placeholder stub.
    Implements the full mission interface expected by main.py (~60 hook points).
    All methods return safe no-op defaults until actual mission logic is written.
    """

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_5'
        self.active = True
        self.game_frozen = False
        self.game_paused = False
        self.intro_active = False

        # Set up enabled territories for the mission map
        map_data.set_enabled_territories(MISSION_5_TERRITORIES)

        # Assign territory ownership to factions
        self._setup_initial_state()

        logger.info("Mission 5 initialized (placeholder)")

    def _setup_initial_state(self):
        """Configure initial territory ownership, armies, gold, and colors.

        NOTE: This is a placeholder stub. Territory ownership uses the correct
        GameState API (gs.territory_owners) and gold uses gs.player_gold,
        matching the pattern established in campaign_mission_2.py and
        campaign_mission_4.py.
        """
        gs = self.game_state

        # Set faction colors
        for player_idx, color in enumerate(PLAYER_COLORS):
            if player_idx < gs.num_players:
                gs.player_colors[player_idx] = color

        # Set faction names
        for player_idx, name in FACTION_NAMES.items():
            if name and player_idx < gs.num_players:
                gs.player_names[player_idx] = name

        # Assign territories to factions using the correct GameState API:
        # gs.territory_owners[territory_name] = player_idx
        # (NOT gs.territories[territory_name]['owner'], which is the wrong API)
        for player_idx, territories in FACTION_TERRITORIES.items():
            if player_idx < gs.num_players:
                for territory_name in territories:
                    if territory_name in gs.territory_owners:
                        gs.territory_owners[territory_name] = player_idx

        # Set starting gold using the correct GameState API: gs.player_gold[idx]
        # (NOT gs.gold[idx], which does not exist)
        for player_idx, gold in STARTING_GOLD.items():
            if player_idx < gs.num_players:
                gs.player_gold[player_idx] = gold

    # ========================================================================
    # Frame update / render (called from main.py game loop)
    # ========================================================================

    def update(self, delta_time):
        """Frame update — returns 'exit_campaign' on victory, None otherwise"""
        if not self.active:
            return None
        return None

    def render(self, screen):
        """Draw mission overlays after normal rendering"""
        pass

    # ========================================================================
    # AI control hooks
    # ========================================================================

    @property
    def block_ai(self):
        """True to skip normal AI execution during intro/scripted sequences"""
        return False

    @property
    def block_ai_thinking(self):
        return False

    def get_ai_thinking_text(self):
        """Override AI thinking text. Returns (text, subtitle) tuple."""
        return None

    def execute_ai_turn_override(self):
        """Called instead of normal AI logic when block_ai is True"""
        pass

    def update_ai_turn(self, delta_time):
        """Tick mission AI. Returns True if managing AI turn."""
        return False

    # ========================================================================
    # Action gating (checked throughout main.py UI code)
    # ========================================================================

    def is_action_allowed(self, action_type, **kwargs):
        """Gate specific player actions. True = action allowed."""
        return True

    def is_button_locked(self, button_id):
        """Grey out locked buttons. False = not locked."""
        return False

    def should_button_be_locked(self, button_id):
        return False

    def should_highlight_button(self, button_id):
        """Green glow on tutorial buttons. False = no highlight."""
        return False

    def is_timer_visible(self):
        """Control planning timer visibility"""
        return True

    def should_hide_hero_training(self):
        """Hide hero training panel. False = show normally."""
        return False

    # ========================================================================
    # Territory interaction
    # ========================================================================

    def is_territory_interactive(self, territory_name):
        """Filter clickable territories. True = interactive."""
        return True

    def get_adjacency_override(self, territory):
        """Override territory adjacency. None = use default."""
        return None

    def get_highlight_territory(self):
        """Territory to highlight. None = no highlight."""
        return None

    def should_highlight_plot(self, territory, plot_index):
        """Highlight a specific building plot. False = no highlight."""
        return False

    # ========================================================================
    # Event notifications (called from game hooks)
    # ========================================================================

    def notify_event(self, event_type, **kwargs):
        """Inform mission of player actions"""
        pass

    # ========================================================================
    # Quest / UI access
    # ========================================================================

    def get_quest_log(self):
        """Return list of quest entries: [{'text': str, 'completed': bool}]"""
        return [{'text': 'Mission 5 — placeholder', 'completed': False}]

    # ========================================================================
    # Achievement integration
    # ========================================================================

    def get_bonus_conditions(self):
        """Return dict of bonus condition flags for achievement_manager"""
        return {
            'campaign_mission_5_bonus': False,
        }

    # ========================================================================
    # Lifecycle
    # ========================================================================

    def deactivate(self):
        """Clean up mission state"""
        self.active = False
        logger.info("Mission 5 deactivated")
