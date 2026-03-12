# -*- coding: utf-8 -*-
# campaign_mission_2.py
# Campaign Mission 2: Early Eastern Conquests
# A mission with dormant AI factions that awaken based on player actions.

import copy
import pygame
import map_data
from utils.logger import get_logger
# Phase 2C refactoring: import shared campaign utilities instead of defining them locally
from campaign_utils import TransmissionOverlay, CameraPanAnimation, CameraZoomAnimation
from campaign_utils import update_endgame_sequence, render_endgame_sequence

logger = get_logger(__name__)

# ============================================================================
# MISSION CONFIGURATION
# ============================================================================

# Territories enabled for this mission (all others are hidden/disabled)
MISSION_2_TERRITORIES = [
    "Révia", "Venexia", "Valeonia", "Velognia", "The Holy Land",
    "Lobardia", "Elland", "Lentria", "Elletian Isles"
]

# Display name overrides for this mission
MISSION_2_DISPLAY_NAMES = {
    "The Holy Land": "Neimer Coast",
    "Venexia": "Heilonic Kingdom of Worham",
    "Révia": "Heilonic Kingdom of Entaron"
}

# Faction territory ownership mapping
# Player 0 = Human (Green), Player 1 = Elletic Tribes (Yellow)
# Player 2 = Heilonic Tribes (Blue), Player 3 = Chiefdom of Valeonia (Red)
FACTION_TERRITORIES = {
    0: ["Lobardia"],  # Human player
    1: ["Elletian Isles", "Lentria", "Elland", "The Holy Land"],  # Elletic Tribes
    2: ["Venexia", "Révia"],  # Heilonic Tribes
    3: ["Valeonia", "Velognia"],  # Chiefdom of Valeonia
}

# Player colors: Green, Yellow, Blue, Red
PLAYER_COLORS = [
    (100, 200, 100),   # Player 0: Green (human)
    (255, 220, 100),   # Player 1: Yellow (Elletic Tribes)
    (100, 150, 255),   # Player 2: Blue (Heilonic Tribes)
    (255, 100, 100),   # Player 3: Red (Chiefdom of Valeonia)
]

# Initial setup for each territory
TERRITORY_SETUP = {
    # Player 0 - Human (Green) - Lobardia
    "Lobardia": {
        "owner": 0,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    # Player 1 - Elletic Tribes (Yellow)
    "Elletian Isles": {
        "owner": 1,
        "buildings": {0: "Keep"},
        "units": [{"type": "Archer", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0}]
    },
    "Lentria": {
        "owner": 1,
        "buildings": {0: "Mine", 1: "Farm"},
        "units": [
            {"type": "Pikeman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Elland": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Square"},
        "units": [
            {"type": "Archer", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "The Holy Land": {
        "owner": 1,
        "buildings": {0: "Square", 1: "Barracks"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    # Player 2 - Heilonic Tribes (Blue)
    "Venexia": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Révia": {
        "owner": 2,
        "buildings": {0: "Square", 1: "Barracks"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    # Player 3 - Chiefdom of Valeonia (Red)
    "Valeonia": {
        "owner": 3,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": [
            {"type": "Pikeman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 6, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Velognia": {
        "owner": 3,
        "buildings": {0: "Farm", 1: "Farm"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 6, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 7, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
}

# Faction names
FACTION_NAMES = {
    0: None,  # Use player's profile name
    1: "Elletic Tribes",
    2: "Heilonic Tribes",
    3: "Chiefdom of Valeonia",
}


# ============================================================================
# INTRO VOICE MAPPING (INTRO_SEQUENCE index → voice key)
# ============================================================================

INTRO_STEP_TO_VOICE = {
    1: "M2T1", 2: "M2T2", 3: "M2T3", 4: "M2T4",
    6: "M2T5", 8: "M2T6", 10: "M2T7", 12: "M2T8"
}

# ============================================================================
# INTRO SEQUENCE DEFINITION
# ============================================================================

# Intro sequence steps: (action, duration_or_target, transmission_text)
# Actions: 'wait', 'show_timer', 'pan_to', 'start_game'
INTRO_SEQUENCE = [
    # Initial camera zoom to Lobardia, game paused
    ("zoom_to", "Lobardia", ""),
    # First transmission starts AFTER zoom completes (wait duration = how long it stays visible)
    ("wait", 6.0, "Warlord, our success in unifying Lobardic tribes sounds throughout the lands!"),
    ("wait", 7.0, "Our victories must not stop here! There are riches and glory ready to be taken!"),
    ("wait", 4.0, "But our time is short! The enemies sense our growing ambition!"),
    ("show_timer", 7.0, "Winds carry the word of our moves to our enemies. We must not relent and pursue victory!"),
    ("pan_to", "Lentria", ""),
    ("wait", 5.0, "The Elletic Tribes on our southern frontier. Weak and ripe for conquest."),
    ("pan_to", "Venexia", ""),
    ("wait", 7.0, "The Heilonic Tribes. Divided, they were weak, but together.. might pose a challenge."),
    ("pan_to", "Valeonia", ""),
    ("wait", 6.0, "And the Valeonians.. proud and strong. But their pride will be their downfall."),
    ("pan_to", "Lobardia", ""),
    ("wait", 9.0, "Gather our men! Fight for glory! The tribes will not attack until provoked, so plan ahead well."),
    ("start_game", 0, ""),
]


# Phase 2C: TransmissionOverlay, CameraPanAnimation, CameraZoomAnimation
# are now imported from campaign_utils.py (see imports at top of file).


# ============================================================================
# MISSION 2 MAIN CLASS
# ============================================================================

class Mission2:
    """
    Campaign Mission 2: Early Eastern Conquests

    Features:
    - Cinematic intro sequence with camera pans and transmissions
    - Dormant AI factions that awaken based on player actions
    - Quest tracking for defeating all 3 enemy factions
    - Event-triggered transmissions
    - Victory sequence when all factions defeated
    """

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_2'  # For achievement tracking
        self.active = True

        # Faction awakened state
        self.faction_awakened = {1: False, 2: False, 3: False}
        self.faction_defeated = {1: False, 2: False, 3: False}

        # Bonus achievement tracking: "The Taller They Are..."
        # True if player attacks Valeonia (faction 3) BEFORE attacking factions 1 or 2
        self.bonus_valeonia_first = None  # None=undecided, True=met, False=failed

        # Dormant AI turn timing
        self.dormant_turn_timer = 0.0
        self.dormant_turn_duration = 3.0  # 3 seconds for dormant AI turn

        # Intro sequence state
        self.intro_active = True
        self.intro_step_index = 0
        self.intro_timer = 0.0
        self.intro_waiting_for_pan = False
        self.game_paused = True  # Game paused during intro
        self.timer_visible = False  # Turn timer visibility

        # Camera animation
        self.camera_animation = None

        # Transmission overlay
        self.transmission_overlay = None
        self.transmission_timer = 0.0
        self.transmission_duration = 0.0

        # Quest log: list of {'text': str, 'completed': bool}
        self.quest_log = [
            {'text': 'Defeat the Elletic Tribes', 'completed': False},
            {'text': 'Defeat the Heilonic Tribes', 'completed': False},
            {'text': 'Defeat the Chiefdom of Valeonia', 'completed': False},
        ]

        # Victory sequence state
        self.game_frozen = False
        self.victory_sequence_active = False
        self.victory_phase = None
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0
        self.victory_image = None
        self.victory_image_scale = 0.0

        # Defeat sequence state (player loses all territories)
        self.defeat_sequence_active = False
        self.defeat_phase = None
        self.defeat_timer = 0.0
        self.defeat_fade_alpha = 0
        self.defeat_image = None
        self.defeat_image_scale = 0.0
        self._pending_victory = False  # True when victory transmission shown, waiting to start sequence
        self._pending_defeat = False
        self._victory_waiting = False  # True when victory triggered but waiting for battles to finish
        self._defeat_waiting = False   # True when defeat triggered but waiting for battles to finish

        # Pending transmission queue (for events during gameplay)
        self.pending_transmission = None
        self.pending_transmission_duration = 0.0
        self.pending_transmission_voice = None  # Voice key for pending transmission

        # Inter-transmission pause timer (1s gap between consecutive voiced transmissions)
        self._intro_pause_timer = 0.0

        # Timer highlight pulsation (20 seconds when first shown)
        self.timer_highlight_start_time = None
        self.timer_highlight_duration = 20.0  # Pulsate for 20 seconds

        # AI blocking is handled via block_ai property (checks intro + dormant state)

        # Allow turn timer to auto-end player turns (unlike tutorial which disables it)
        self.allow_timer_expiry = True

        # Bake cloud cover into map image (covers non-mission territory areas)
        self._bake_cloud_cover()

        # Store original flag icons for restoration on cleanup
        self.original_flag_icons = None

        # Set up territory filtering and display names
        map_data.set_enabled_territories(MISSION_2_TERRITORIES)
        map_data.set_territory_display_names(MISSION_2_DISPLAY_NAMES)

        # Set up initial game state
        self._setup_initial_state()

        # Start intro sequence
        self._start_intro_sequence()

    def _setup_initial_state(self):
        """Configure the game state for Mission 2 scenario."""
        gs = self.game_state

        # Set player colors
        for i, color in enumerate(PLAYER_COLORS):
            if i < len(gs.player_colors):
                gs.player_colors[i] = color

        # Remap flag icons to match player colors
        # Default: 0=Red, 1=Blue, 2=Green, 3=Yellow
        # Mission 2: Player 0=Green, 1=Yellow, 2=Blue, 3=Red
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and len(game.army_flag_icons) >= 4:
            # Save original flag mappings for restoration on cleanup
            self.original_flag_icons = {i: game.army_flag_icons[i] for i in range(4)}
            # Remap: Player 0 gets Green (2), Player 1 gets Yellow (3),
            #        Player 2 gets Blue (1), Player 3 gets Red (0)
            game.army_flag_icons[0] = self.original_flag_icons[2]  # Green for human
            game.army_flag_icons[1] = self.original_flag_icons[3]  # Yellow for Elletic Tribes
            game.army_flag_icons[2] = self.original_flag_icons[1]  # Blue for Heilonic
            game.army_flag_icons[3] = self.original_flag_icons[0]  # Red for Valeonia

        # Set faction names
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name

        # Set starting gold for human player
        gs.player_gold[0] = 500

        # Configure each territory
        for territory, config in TERRITORY_SETUP.items():
            owner = config["owner"]
            gs.territory_owners[territory] = owner

            # Clear any pre-existing garrisons from default game init
            gs.territory_garrisons[territory] = {}

            # Set buildings
            if territory not in gs.buildings:
                gs.buildings[territory] = {}
            for plot_idx, building_type in config.get("buildings", {}).items():
                gs.buildings[territory][plot_idx] = building_type

            # Set garrison units — deep copy to prevent TERRITORY_SETUP mutation on restart
            units = copy.deepcopy(config.get("units", []))
            unmoved = len(units)
            gs.set_garrison_armies(territory, owner, unmoved=unmoved, moved=0, units=units)

        # Clear non-mission territories to prevent stale state from previous games
        mission_set = set(MISSION_2_TERRITORIES)
        for territory in list(gs.territory_owners.keys()):
            if territory not in mission_set:
                gs.territory_owners[territory] = -1
                gs.territory_garrisons[territory] = {}
                gs.buildings[territory] = {}

        # Invalidate bonus cache after bulk territory setup
        gs.invalidate_territorial_bonus_cache()

        # Set starting territories for reference
        gs.player_starting_territories[0] = "Lobardia"
        gs.player_starting_territories[1] = "Elletian Isles"
        gs.player_starting_territories[2] = "Venexia"
        gs.player_starting_territories[3] = "Valeonia"

        logger.info("Initial state configured")

    def _start_intro_sequence(self):
        """Start the intro sequence."""
        self.intro_active = True
        self.intro_step_index = 0
        self.intro_timer = 0.0
        self.game_paused = True
        self._execute_intro_step()

    def _execute_intro_step(self):
        """Execute the current intro sequence step."""
        from global_sound import play_transmission_sound, stop_transmission_sound

        if self.intro_step_index >= len(INTRO_SEQUENCE):
            self._end_intro_sequence()
            return

        action, param, text = INTRO_SEQUENCE[self.intro_step_index]
        logger.debug(f"Intro step {self.intro_step_index}: {action}, param={param}")

        if action == "zoom_to":
            # Initial zoom to territory
            self._start_zoom_animation(param)
            self.intro_waiting_for_pan = True
            if text:
                self._show_transmission(text)
                # Play voice line for this intro step
                voice_key = INTRO_STEP_TO_VOICE.get(self.intro_step_index)
                if voice_key:
                    play_transmission_sound(voice_key)

        elif action == "wait":
            # Wait for duration, show text
            self.intro_timer = 0.0
            if text:
                self._show_transmission(text)
                # Play voice line for this intro step
                voice_key = INTRO_STEP_TO_VOICE.get(self.intro_step_index)
                if voice_key:
                    play_transmission_sound(voice_key)
            else:
                self.transmission_overlay = None
                stop_transmission_sound()

        elif action == "show_timer":
            # Show and highlight the timer bar
            self.timer_visible = True
            self.intro_timer = 0.0
            # Start timer highlight pulsation
            import time
            self.timer_highlight_start_time = time.time()
            if text:
                self._show_transmission(text)
                # Play voice line for this intro step
                voice_key = INTRO_STEP_TO_VOICE.get(self.intro_step_index)
                if voice_key:
                    play_transmission_sound(voice_key)

        elif action == "pan_to":
            # Pan camera to territory — hide text and stop voice during pan
            self._start_pan_animation(param)
            self.intro_waiting_for_pan = True
            self.transmission_overlay = None
            stop_transmission_sound()

        elif action == "start_game":
            # End intro, start gameplay
            self._end_intro_sequence()

    def _start_zoom_animation(self, territory):
        """Start camera zoom animation to a territory."""
        import main as _main
        MAP_HEIGHT = _main.MAP_HEIGHT

        camera = self.main_game.camera
        target_center = self.main_game.scaled_centers.get(
            territory, map_data.get_territory_center(territory)
        )
        screen_width = self.main_game.screen.get_width()

        self.camera_animation = CameraZoomAnimation(
            camera_handler=camera,
            start_zoom=camera.min_zoom,
            target_zoom=camera.max_zoom,
            duration=1.5,
            target_center_world=target_center,
            screen_width=screen_width,
            map_area_height=MAP_HEIGHT,
        )

    def _start_pan_animation(self, territory):
        """Start camera pan animation to a territory."""
        import main as _main
        MAP_HEIGHT = _main.MAP_HEIGHT

        camera = self.main_game.camera
        target_center = self.main_game.scaled_centers.get(
            territory, map_data.get_territory_center(territory)
        )
        screen_width = self.main_game.screen.get_width()

        self.camera_animation = CameraPanAnimation(
            camera_handler=camera,
            target_center_world=target_center,
            duration=1.5,  # Pan duration
            screen_width=screen_width,
            map_area_height=MAP_HEIGHT,
        )

    def _end_intro_sequence(self):
        """End the intro sequence and start gameplay."""
        import time
        from global_sound import stop_transmission_sound
        logger.info("Intro sequence complete, starting gameplay")
        self.intro_active = False
        self.game_paused = False
        self.timer_visible = True
        self.transmission_overlay = None
        stop_transmission_sound()  # Stop any playing intro voice
        # Note: block_ai is now a property that checks dormant state

        # Enable the turn timer in game state and reset the start time
        self.game_state.turn_timer_enabled = True
        self.game_state.planning_phase_start_time = time.time()  # Reset timer to start now

    def _show_transmission(self, text, speaker="Advisor"):
        """Show or update the transmission overlay with speaker name."""
        import main as _main
        TOP_PANEL_HEIGHT = _main.TOP_PANEL_HEIGHT
        screen = self.main_game.screen
        sw = screen.get_width()
        sh = screen.get_height()
        if not self.transmission_overlay:
            self.transmission_overlay = TransmissionOverlay(sw, sh, text, TOP_PANEL_HEIGHT, speaker=speaker)
        else:
            self.transmission_overlay.set_text(text, speaker=speaker)

    def _queue_transmission(self, text, duration, voice_key=None, speaker="Advisor"):
        """Queue a transmission to show during gameplay, with optional voice line."""
        self.pending_transmission = text
        self.pending_transmission_duration = duration
        self.pending_transmission_voice = voice_key
        self.pending_transmission_speaker = speaker

    def _start_pending_transmission(self):
        """Start showing a pending transmission with optional voice line."""
        if self.pending_transmission:
            speaker = getattr(self, 'pending_transmission_speaker', "Advisor")
            self._show_transmission(self.pending_transmission, speaker=speaker)
            self.transmission_duration = self.pending_transmission_duration
            self.transmission_timer = 0.0
            # Play voice line if one was queued with this transmission
            if self.pending_transmission_voice:
                from global_sound import play_transmission_sound
                play_transmission_sound(self.pending_transmission_voice)
            self.pending_transmission = None
            self.pending_transmission_duration = 0.0
            self.pending_transmission_voice = None
            self.pending_transmission_speaker = "Advisor"

    def _is_gameplay_idle(self):
        """Check if gameplay is idle (no battles, popups, turn announcements, or animations).
        Also considers game idle when phase is 'ended' (turn advancement blocked, no new battles)."""
        gs = self.game_state
        battle_popup_open = getattr(self.main_game, 'battle_popup_visible', False)
        # Accept planning phase OR ended phase (turn can't advance once game ends,
        # but we still need to wait for any active battle popups to close)
        phase_ok = gs.turn_phase == 'planning' or gs.phase == 'ended'
        return (phase_ok
                and not gs.pending_battles
                and not battle_popup_open
                and not gs.turn_announcement_active)

    # ========================================================================
    # FRAME UPDATE
    # ========================================================================

    def update(self, delta_time):
        """Called every frame from main.py game loop. Returns 'exit_campaign' to exit."""
        if not self.active:
            return None

        # Cap delta_time to prevent animation skipping
        delta_time = min(delta_time, 0.05)

        # Update camera animation
        if self.camera_animation and self.camera_animation.active:
            still_active = self.camera_animation.update(delta_time)
            if not still_active and self.intro_waiting_for_pan:
                # Pan complete, advance to next intro step
                self.intro_waiting_for_pan = False
                self.intro_step_index += 1
                self._execute_intro_step()

        # Process inter-transmission pause (1s gap between consecutive voiced intro steps)
        if self._intro_pause_timer > 0:
            self._intro_pause_timer -= delta_time
            if self._intro_pause_timer <= 0:
                self._intro_pause_timer = 0
                self.intro_step_index += 1
                self._execute_intro_step()
            return None  # Don't process intro timer during pause

        # Update intro sequence timing
        if self.intro_active and not self.intro_waiting_for_pan:
            action, param, _ = INTRO_SEQUENCE[self.intro_step_index]
            if action in ("wait", "show_timer"):
                self.intro_timer += delta_time
                if self.intro_timer >= param:
                    # Check if next step has text — if so, insert 1s pause
                    next_idx = self.intro_step_index + 1
                    if next_idx < len(INTRO_SEQUENCE) and INTRO_SEQUENCE[next_idx][2]:
                        # Next step has text: pause before advancing
                        from global_sound import stop_transmission_sound
                        self.transmission_overlay = None
                        stop_transmission_sound()
                        self._intro_pause_timer = 1.0
                    else:
                        # Next step has no text (pan/start_game): advance immediately
                        self.intro_step_index += 1
                        self._execute_intro_step()

        # Skip turn announcement animation for AI players (fast AI turns)
        if not self.intro_active:
            gs = self.game_state
            if gs.current_player != 0 and gs.turn_announcement_active:
                game = self.main_game
                if hasattr(game, 'turn_announcement_effect') and game.turn_announcement_effect:
                    game.turn_announcement_effect.cleanup()
                    game.turn_announcement_effect = None
                gs._complete_turn_announcement()

        # Update gameplay transmission timer — must run before victory/defeat checks
        # so that pending victory/defeat transmissions can expire and transition to animation
        if not self.intro_active and self.transmission_overlay and self.transmission_duration > 0:
            self.transmission_timer += delta_time
            if self.transmission_timer >= self.transmission_duration:
                from global_sound import stop_transmission_sound
                self.transmission_overlay = None
                self.transmission_duration = 0.0
                stop_transmission_sound()  # Stop voice when transmission text expires

        # Check if gameplay is idle (no battles, popups, or animations blocking)
        gameplay_idle = self._is_gameplay_idle()

        # Start pending transmission only when gameplay is idle
        if not self.intro_active and not self.transmission_overlay and self.pending_transmission:
            if gameplay_idle:
                self._start_pending_transmission()

        # Deferred victory: wait until all battles/popups closed AND transmissions shown
        if self._victory_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.pending_transmission:
                self._victory_waiting = False
                self.game_frozen = True
                self.game_paused = True
                self._clear_hover_tooltips()

                text = "Victory is ours! The lesser tribes were no match for our speed and strength!"
                self._show_transmission(text)
                self.transmission_duration = 6.0
                self.transmission_timer = 0.0
                # Play victory voice line (M2T20)
                from global_sound import play_transmission_sound
                play_transmission_sound("M2T20")
                self._pending_victory = True

        # Deferred defeat: same pattern
        if self._defeat_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.pending_transmission:
                self._defeat_waiting = False
                self.game_frozen = True
                self.game_paused = True
                self._clear_hover_tooltips()

                text = "Our forces have been annihilated! The tribes have proven too strong..."
                self._show_transmission(text)
                self.transmission_duration = 5.0
                self.transmission_timer = 0.0
                # Play defeat voice line (M2T21)
                from global_sound import play_transmission_sound
                play_transmission_sound("M2T21")
                self._pending_defeat = True

        # Victory/defeat sequence checks — run after transmission timer so pending
        # victory/defeat transmissions can expire before transitioning to animation
        result = self._update_victory_sequence(delta_time)
        if result == 'exit':
            self._cleanup()
            return 'exit_campaign'

        result = self._update_defeat_sequence(delta_time)
        if result == 'exit':
            self._cleanup()
            return 'exit_campaign'

        return None

    def skip_transmission(self):
        """Skip the currently visible transmission (ESC key).

        Returns True if a transmission was skipped, False otherwise.
        Handles both intro sequence and gameplay transmissions.
        Victory/defeat: hiding overlay triggers endgame animation naturally
        via _pending_victory/_pending_defeat flags in update().
        """
        if not self.active or not self.transmission_overlay:
            return False
        # Don't skip during victory/defeat cinematic animation
        if self.victory_sequence_active or self.defeat_sequence_active:
            return False

        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        self.transmission_overlay = None

        if self.intro_active:
            # During intro: cancel pause/timer, cancel camera animation, advance
            self._intro_pause_timer = 0
            self.intro_timer = 0.0
            self.intro_waiting_for_pan = False
            if self.camera_animation:
                self.camera_animation = None
            self.intro_step_index += 1
            self._execute_intro_step()
        else:
            # During gameplay: reset timer, next queued transmission starts on
            # next idle frame via update() logic
            self.transmission_timer = 0.0
            self.transmission_duration = 0.0
        return True

    # ========================================================================
    # AI TURN HANDLING
    # ========================================================================

    def update_ai_turn(self, delta_time):
        """Handle AI turn timing. Returns True if AI turn is being managed."""
        if not self.active or self.intro_active:
            return False

        current_player = self.game_state.current_player
        if current_player == 0:
            return False  # Not AI turn

        gs = self.game_state

        # Skip turns for defeated factions entirely
        if self.faction_defeated.get(current_player, False):
            logger.debug(f"Skipping turn for defeated faction {current_player}")
            gs.next_player()
            return True

        # Wait for animations to complete before resolving battles or ending turn
        if gs.turn_phase == 'execution':
            return True  # Wait for animations

        # Auto-resolve any pending battles
        if gs.turn_phase == 'battles' and gs.pending_battles:
            self._auto_resolve_battles()
            return True

        # All AI factions are managed by Mission2
        self.dormant_turn_timer += delta_time

        # Fast 0.5s AI turns for campaign (announcement already skipped)
        if self.dormant_turn_timer >= 0.5:
            logger.debug(f"AI player {current_player} ending turn")
            self.dormant_turn_timer = 0.0
            gs.next_player()

        return True

    def _auto_resolve_battles(self):
        """Auto-resolve all pending battles during AI turn."""
        gs = self.game_state
        if not gs.pending_battles:
            return

        num_battles = len(gs.pending_battles)
        logger.debug(f"Auto-resolving {num_battles} battle(s)")

        # Resolve battles in reverse order to maintain indices
        for battle_idx in range(num_battles - 1, -1, -1):
            if battle_idx < len(gs.pending_battles):
                battle = gs.pending_battles[battle_idx]
                # Battle is an object with .territory attribute, not a dict
                territory_name = getattr(battle, 'territory', 'Unknown')
                logger.debug(f"Resolving battle in {territory_name}")
                gs.resolve_battle(battle_idx)

    def execute_ai_turn_override(self):
        """Called instead of normal AI execution. Handles both dormant and awakened AI."""
        current_player = self.game_state.current_player
        if current_player == 0:
            return

        # Dormant AI does nothing
        if not self.faction_awakened.get(current_player, False):
            pass  # Just wait, turn ends via update_ai_turn timer
        else:
            # Awakened AI: execute simple AI behavior (train units, attack player 0)
            self._execute_awakened_ai(current_player)

    def _execute_awakened_ai(self, player_id):
        """Execute simple AI behavior for awakened factions.

        Behavior:
        - Train units at barracks if affordable
        - Attack player 0 territories that are adjacent
        """
        gs = self.game_state

        # Find territories owned by this player
        my_territories = [t for t in MISSION_2_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return  # Faction eliminated

        # Find player 0 territories that are adjacent to our territories
        player_targets = []
        for t in MISSION_2_TERRITORIES:
            if gs.territory_owners.get(t) == 0:
                player_targets.append(t)

        # Simple AI: train units and attack
        for territory in my_territories:
            # Train units at barracks
            buildings = gs.buildings.get(territory, {})
            for plot_idx, building in buildings.items():
                if building == 'Barracks':
                    # Train a unit if we have gold
                    if gs.player_gold[player_id] >= 15:  # Swordsman cost
                        gs.start_training(territory, plot_idx, 'Swordsman')

            # Check if we can attack a player territory
            garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
            units = garrison.get('units', [])
            unmoved_count = sum(1 for u in units if u.get('status') == 'ready')

            if unmoved_count >= 3:  # Attack with 3+ units
                # Find adjacent player territories
                neighbors = map_data.get_neighbors(territory)
                for neighbor in neighbors:
                    if gs.territory_owners.get(neighbor) == 0:
                        # Create attack order
                        unit_ids = [u['id'] for u in units if u.get('status') == 'ready'][:unmoved_count]
                        gs.add_movement_order_for_units(territory, neighbor, unit_ids, player=player_id)
                        logger.debug(f"Awakened AI {player_id}: attacking {neighbor} from {territory}")
                        break  # One attack per territory

    # ========================================================================
    # AI BLOCKING PROPERTY
    # ========================================================================

    @property
    def block_ai(self):
        """Return True if AI should be blocked for the current player.

        In Mission 2, ALL AI factions are controlled by Mission2 to ensure:
        - Dormant factions do nothing
        - Awakened factions only attack player 0
        """
        if self.intro_active:
            return True

        current_player = self.game_state.current_player
        if current_player == 0:
            return False  # Human player, no AI to block

        # Block normal AI for ALL AI factions - Mission2 controls their behavior
        return True

    # ========================================================================
    # ACTION GATING
    # ========================================================================

    def is_action_allowed(self, action_type, **kwargs):
        """Check if a player action is permitted."""
        if not self.active:
            return True

        # Block all actions during intro or victory
        if self.intro_active or self.victory_sequence_active:
            return False

        # Block all actions when game is paused
        if self.game_paused:
            return False

        # Block Keep building
        if action_type == 'build' and kwargs.get('building_type') == 'Keep':
            return False

        # Block Heroes tab
        if action_type == 'sidebar_tab' and kwargs.get('tab_name') == 'heroes':
            return False

        return True

    def should_button_be_locked(self, button_id):
        """Check if a specific button should be locked/greyed out."""
        if not self.active:
            return False

        # Lock Keep building button
        if button_id == 'building_Keep':
            return True

        return False

    def is_button_locked(self, button_id):
        """Alias for should_button_be_locked - used by main.py UI code."""
        return self.should_button_be_locked(button_id)

    def should_highlight_button(self, button_id):
        """Check if a button should be highlighted. Mission 2 doesn't use button highlights."""
        return False

    def get_ai_thinking_text(self):
        """Override AI thinking indicator to show unified 'Enemies thinking...' text."""
        return ("Enemies thinking...", "")

    def should_hide_heroes_tab(self):
        """Check if Heroes tab should be hidden."""
        return self.active

    def is_timer_visible(self):
        """Check if turn timer should be visible."""
        if self.intro_active:
            return self.timer_visible
        return True

    def should_highlight_timer(self):
        """Check if turn timer should be highlighted (pulsating for 20 seconds)."""
        import time
        # Highlight/pulsate for 20 seconds after timer is first shown
        if self.timer_highlight_start_time is not None:
            elapsed = time.time() - self.timer_highlight_start_time
            if elapsed < self.timer_highlight_duration:
                # Pulsate effect: return True/False alternating every 0.5 seconds
                return int(elapsed * 2) % 2 == 0
        return False

    # ========================================================================
    # EVENT NOTIFICATIONS
    # ========================================================================

    def notify_event(self, event_type, **kwargs):
        """Receive gameplay events from hooked game systems."""
        if not self.active or self.intro_active:
            return

        # Check for attack orders (awakening triggers)
        if event_type == 'order_created':
            from_territory = kwargs.get('from_territory')
            to_territory = kwargs.get('to_territory')
            player = kwargs.get('player', 0)

            # Only check human player attacks
            if player == 0:
                self._check_attack_awakening(to_territory)

        # Check for territory conquest
        elif event_type == 'territory_conquered':
            territory = kwargs.get('territory')
            new_owner = kwargs.get('new_owner')
            self._on_territory_conquered(territory, new_owner)

        # Check army count for Elletic Tribes awakening
        elif event_type == 'turn_start' and kwargs.get('player_index') == 0:
            self._check_army_count_awakening()

    def _check_attack_awakening(self, target_territory):
        """Check if attacking a territory awakens a faction."""
        # Track which faction is being attacked for bonus achievement
        for faction_id, territories in FACTION_TERRITORIES.items():
            if faction_id == 0:
                continue
            if target_territory in territories:
                # First attack determines bonus eligibility ("The Taller They Are...")
                if self.bonus_valeonia_first is None:
                    if faction_id == 3:  # Valeonia
                        self.bonus_valeonia_first = True
                        logger.info("Bonus condition: Player attacked Valeonia first!")
                    else:
                        self.bonus_valeonia_first = False
                        logger.info(f"Bonus condition failed: Player attacked faction {faction_id} before Valeonia")
                break

        # Check which faction owns the target and awaken if needed
        for faction_id, territories in FACTION_TERRITORIES.items():
            if faction_id == 0:
                continue  # Skip human player

            if target_territory in territories and not self.faction_awakened[faction_id]:
                # Awaken this faction due to attack
                self._awaken_faction(faction_id, 'attack')
                break

    def _check_army_count_awakening(self):
        """Check if player has >10 armies in one territory (awakens Elletic Tribes)."""
        if self.faction_awakened[1]:
            return  # Already awakened

        gs = self.game_state
        for territory in MISSION_2_TERRITORIES:
            if gs.territory_owners.get(territory) == 0:
                garrison = gs.territory_garrisons.get(territory, {}).get(0, {})
                unit_count = len(garrison.get('units', []))
                if unit_count > 10:
                    self._awaken_faction(1, 'army_count')
                    break

    def _awaken_faction(self, faction_id, reason):
        """Awaken a faction and show appropriate transmission."""
        if self.faction_awakened.get(faction_id, False):
            return

        self.faction_awakened[faction_id] = True
        logger.info(f"Faction {faction_id} awakened due to: {reason}")

        # Determine transmission text and voice key
        if faction_id == 1:  # Elletic Tribes
            if reason == 'army_count':
                text = "The Elletic Tribes have taken notice of our conscription. They pose to attack!"
                duration = 5.0
                self._queue_transmission(text, duration, voice_key="M2T9")
            else:  # attack
                text = "Our aggression caused the Elletic Tribes to declare open war!"
                duration = 4.0
                self._queue_transmission(text, duration, voice_key="M2T10")

        elif faction_id == 2:  # Heilonic Tribes
            if reason == 'attack':
                text = "Our attack has stirred the Heilonics into fight!"
                duration = 3.0
                self._queue_transmission(text, duration, voice_key="M2T11")
            # If awakened by Elletic defeat, no transmission

        elif faction_id == 3:  # Chiefdom of Valeonia
            if reason == 'attack':
                # Attacking Valeonia awakens ALL other factions
                other_factions_alive = []
                for other_id in [1, 2]:  # Elletic Tribes, Heilonic Tribes
                    if not self.faction_defeated.get(other_id, False):
                        if not self.faction_awakened.get(other_id, False):
                            self.faction_awakened[other_id] = True
                            logger.info(f"Faction {other_id} awakened due to Valeonia attack")
                        other_factions_alive.append(other_id)

                # Special transmission if other factions are still alive
                if other_factions_alive:
                    text = "Bold move, warlord. Attacking the most powerful chiefdom like that.. all other tribes have sensed their opportunity to decimate us!"
                    duration = 8.0
                    self._queue_transmission(text, duration, voice_key="M2T12")
                else:
                    # Original message if Valeonia is the last faction
                    text = "The Valeonians are taking up arms!"
                    duration = 3.0
                    self._queue_transmission(text, duration, voice_key="M2T13")

    def _on_territory_conquered(self, territory, new_owner):
        """Handle territory conquest - check for faction defeat or player defeat."""
        # Check if player was defeated (lost all territories)
        if new_owner != 0:
            self._check_player_defeat()
            return  # Rest of function handles human player conquests only

        # Check each faction — must check ALL mission territories, not just starting ones,
        # because awakened AI can conquer new territories beyond their starting set
        for faction_id in FACTION_TERRITORIES:
            if faction_id == 0:
                continue

            if self.faction_defeated[faction_id]:
                continue

            # Check if faction still owns ANY territory in the mission
            faction_alive = False
            for t in MISSION_2_TERRITORIES:
                if self.game_state.territory_owners.get(t) == faction_id:
                    faction_alive = True
                    break

            if not faction_alive:
                self._on_faction_defeated(faction_id)

    def _on_faction_defeated(self, faction_id):
        """Handle faction defeat."""
        if self.faction_defeated.get(faction_id, False):
            return

        self.faction_defeated[faction_id] = True
        logger.info(f"Faction {faction_id} defeated!")

        # Mark quest as complete
        quest_map = {
            1: 'Defeat the Elletic Tribes',
            2: 'Defeat the Heilonic Tribes',
            3: 'Defeat the Chiefdom of Valeonia',
        }
        quest_text = quest_map.get(faction_id)
        if quest_text:
            for quest in self.quest_log:
                if quest['text'] == quest_text:
                    quest['completed'] = True
                    break

        # Check if all factions defeated (victory)
        all_defeated = all(self.faction_defeated.values())

        if all_defeated:
            # Final victory - skip faction defeat transmission
            self._start_victory()
        else:
            # Show faction defeat transmission with voice
            if faction_id == 1:  # Elletic Tribes
                if not self.faction_awakened[2]:
                    # Heilonic still dormant - awaken them
                    self.faction_awakened[2] = True
                    text = "The Elletic Tribes have been subjugated! The Heilonics anticipate our aggression!"
                    duration = 5.0
                    self._queue_transmission(text, duration, voice_key="M2T14")
                elif self.faction_defeated.get(2, False) and not self.faction_awakened[3]:
                    # Heilonic already defeated AND Valeonia still dormant - awaken Valeonia
                    self.faction_awakened[3] = True
                    text = "The Elletic Tribes have been subjugated! The Valeonians sense our might!"
                    duration = 5.0
                    self._queue_transmission(text, duration, voice_key="M2T15")
                else:
                    text = "The Elletic Tribes have been subjugated!"
                    duration = 3.0
                    self._queue_transmission(text, duration, voice_key="M2T16")

            elif faction_id == 2:  # Heilonic Tribes
                # Only awaken Valeonia if BOTH Elletic and Heilonic are now defeated
                if self.faction_defeated.get(1, False) and not self.faction_awakened[3]:
                    # Elletic already defeated AND Valeonia still dormant - awaken Valeonia
                    self.faction_awakened[3] = True
                    text = "The Heilonics are scattered! The Valeonians sense our might!"
                    duration = 4.0
                    self._queue_transmission(text, duration, voice_key="M2T17")
                else:
                    text = "The Heilonics are scattered!"
                    duration = 2.0
                    self._queue_transmission(text, duration, voice_key="M2T18")

            elif faction_id == 3:  # Chiefdom of Valeonia
                text = "The Valeonians have been humbled!"
                duration = 3.0
                self._queue_transmission(text, duration, voice_key="M2T19")

    def _check_player_defeat(self):
        """Check if player has lost all territories (defeat condition)."""
        # Count player territories within mission area
        player_territories = sum(
            1 for t in MISSION_2_TERRITORIES
            if self.game_state.territory_owners.get(t) == 0
        )

        if player_territories == 0:
            self._start_defeat()

    def _clear_hover_tooltips(self):
        """Clear all hover tooltip state so they don't persist over victory/defeat screens."""
        game = self.main_game
        game.hovered_territory = None
        game.hovered_army = None
        game.show_tooltip_army = None

    def _start_defeat(self):
        """Start the defeat sequence (deferred until battles/animations finish)."""
        if self.defeat_sequence_active or self._pending_defeat or self._defeat_waiting:
            return

        logger.info("Player defeated - waiting for battles/animations to finish")

        # Set game state so the game counts as finished (for games_finished tracking)
        self.game_state.phase = 'ended'

        # Defer until battles and popups are closed (checked each frame in update)
        self._defeat_waiting = True

    def _update_defeat_sequence(self, delta_time):
        """Update the defeat sequence animation. Returns 'exit' when done.
        Phase 2C: delegates to shared update_endgame_sequence() from campaign_utils.
        """
        return update_endgame_sequence(self, delta_time, 'defeat')

    def _render_defeat_sequence(self, screen):
        """Render the defeat sequence overlay.
        Phase 2C: delegates to shared render_endgame_sequence() from campaign_utils.
        """
        render_endgame_sequence(self, screen, 'defeat')

    def get_bonus_conditions(self):
        """Return bonus condition flags for achievement system."""
        return {
            'campaign_mission_2_bonus': self.bonus_valeonia_first is True,
        }

    def _start_victory(self):
        """Start the final victory sequence (deferred until battles/animations finish)."""
        if self.victory_sequence_active or self._pending_victory or self._victory_waiting:
            return

        logger.info("Victory condition met - waiting for battles/animations to finish")

        # Set game state for achievement tracking
        self.game_state.winner = 0
        self.game_state.phase = 'ended'

        # Defer until battles and popups are closed (checked each frame in update)
        self._victory_waiting = True

    # ========================================================================
    # VICTORY SEQUENCE
    # ========================================================================

    def _update_victory_sequence(self, delta_time):
        """Update the victory sequence animation. Returns 'exit' when done.
        Phase 2C: delegates to shared update_endgame_sequence() from campaign_utils.
        """
        return update_endgame_sequence(self, delta_time, 'victory')

    def _render_victory_sequence(self, screen):
        """Render the victory sequence overlay.
        Phase 2C: delegates to shared render_endgame_sequence() from campaign_utils.
        """
        render_endgame_sequence(self, screen, 'victory')

    # ========================================================================
    # RENDER
    # ========================================================================

    def _bake_cloud_cover(self):
        """Bake cloud cover directly into the map image.

        Loads CampaignMission2Cover.png, converts black background to transparency
        (pixel brightness → alpha), then blits it onto map_image_original.
        This eliminates separate overlay rendering and any UI clipping issues.
        Uses pure pygame (no numpy) for PyInstaller compatibility.
        """
        try:
            raw = pygame.image.load('assets/CampaignMaps/CampaignMission2Cover.png').convert()
        except pygame.error as e:
            logger.warning(f"Could not load CampaignMission2Cover.png: {e}")
            return

        w, h = raw.get_size()

        # Extract raw RGBA pixel data as a bytearray for bulk manipulation.
        # For each pixel, set alpha = max(R, G, B) so black → transparent, white → opaque.
        raw_str = pygame.image.tostring(raw, 'RGBA')
        pixels = bytearray(raw_str)
        for i in range(0, len(pixels), 4):
            pixels[i + 3] = max(pixels[i], pixels[i + 1], pixels[i + 2])

        # Reconstruct surface from modified pixel data
        cover = pygame.image.fromstring(bytes(pixels), (w, h), 'RGBA')

        # Scale cover to match map_image_original if sizes differ
        game = self.main_game
        map_w, map_h = game.map_image_original.get_size()
        if (w, h) != (map_w, map_h):
            cover = pygame.transform.smoothscale(cover, (map_w, map_h))

        # Blit cloud cover onto the original map image
        game.map_image_original.blit(cover, (0, 0))

        # Invalidate cached scaled map so it re-renders with the composited image
        game.cached_scaled_map = None
        game.cached_zoom_level = None

    def render(self, screen):
        """Called after normal game rendering to draw mission overlay."""
        if not self.active:
            return

        # Victory sequence takes over all rendering
        if self.victory_sequence_active or hasattr(self, '_pending_victory') and self._pending_victory:
            if self.victory_sequence_active:
                self._render_victory_sequence(screen)
            # Draw transmission during pending victory
            if self.transmission_overlay:
                self.transmission_overlay.render(screen)
            return

        # Defeat sequence takes over all rendering
        if self.defeat_sequence_active or self._pending_defeat:
            if self.defeat_sequence_active:
                self._render_defeat_sequence(screen)
            # Draw transmission during pending defeat
            if self.transmission_overlay:
                self.transmission_overlay.render(screen)
            return

        # Draw transmission board if visible
        if self.transmission_overlay:
            self.transmission_overlay.render(screen)

    # ========================================================================
    # QUEST LOG ACCESS
    # ========================================================================

    def get_quest_log(self):
        """Return the quest log list for rendering in the Quests tab."""
        return self.quest_log

    # ========================================================================
    # TERRITORY INTERACTION
    # ========================================================================

    def is_territory_interactive(self, territory_name):
        """Check if a territory can be hovered/clicked."""
        if not self.active:
            return True
        # Only mission territories are interactive
        return territory_name in MISSION_2_TERRITORIES

    def get_adjacency_override(self, territory):
        """Get adjacency override for movement restrictions. Returns None for normal behavior."""
        # No special adjacency restrictions in Mission 2
        return None

    def get_highlight_territory(self):
        """Return the territory name to highlight, or None. Used by map_renderer."""
        # Mission 2 doesn't use step-based territory highlighting
        return None

    def should_highlight_plot(self, territory, plot_index):
        """Check if a specific plot should be highlighted. Mission 2 doesn't use plot highlights."""
        return False

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def _cleanup(self):
        """Clean up mission state when exiting."""
        from global_sound import stop_transmission_sound
        logger.info("Cleaning up")
        stop_transmission_sound()  # Stop any playing voice on mission exit
        map_data.clear_enabled_territories()
        map_data.clear_territory_display_names()

        # Restore original flag icons
        if self.original_flag_icons and hasattr(self.main_game, 'army_flag_icons'):
            for i, flags in self.original_flag_icons.items():
                self.main_game.army_flag_icons[i] = flags

        self.active = False

    def deactivate(self):
        """Deactivate the mission (called on exit)."""
        self._cleanup()
