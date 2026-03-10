# -*- coding: utf-8 -*-
# campaign_mission_5.py
# Campaign Mission 5: The First War
# 3 factions: Human (Red) + Elletic Rebels (Yellow, allied) vs Azincourne Empire (Blue).
# Custom AI with per-territory garrison requirements enforced on all AI players.
# Victory: 9 specific territories controlled by team 0 (player 0 or player 1).
# Defeat: Elletic Isles captured by enemy OR human loses all territories.

import copy
import pygame
import time
import map_data
from utils.logger import get_logger
# Shared campaign utilities (TransmissionOverlay, camera animations, endgame sequences)
from campaign_utils import TransmissionOverlay, CameraPanAnimation, CameraZoomAnimation
from campaign_utils import update_endgame_sequence, render_endgame_sequence

logger = get_logger(__name__)

# ============================================================================
# MISSION CONFIGURATION
# ============================================================================

# All 17 territories enabled for this mission
MISSION_5_TERRITORIES = [
    # Player 0 (Human / Red): 2 territories
    "Nordica", "Leuse Valley",
    # Player 1 (Elletic Rebels / Yellow, allied): 2 territories
    "Elland", "Elletian Isles",
    # Player 2 (Azincourne Empire / Blue, enemy): 13 territories
    "Aelatania", "Courtieux", "Duchy of Daurels", "Northern Heilonia",
    "Londia", "Révia", "Venexia", "The Holy Land",
    "Lentria", "Lobardia", "Valeonia", "Velognia", "Amennia",
]

# Display name overrides for this mission
MISSION_5_DISPLAY_NAMES = {
    "The Holy Land": "Neimer Coast",
    "Elletian Isles": "Elletic Isles",
}

# Faction territory ownership mapping
FACTION_TERRITORIES = {
    0: ["Nordica", "Leuse Valley"],
    1: ["Elland", "Elletian Isles"],
    2: ["Aelatania", "Courtieux", "Duchy of Daurels", "Northern Heilonia",
        "Londia", "Révia", "Venexia", "The Holy Land",
        "Lentria", "Lobardia", "Valeonia", "Velognia", "Amennia"],
}

# Player colors: Red (human), Yellow (ally), Blue (enemy)
PLAYER_COLORS = [
    (255, 100, 100),   # Player 0: Red (human)
    (255, 220, 100),   # Player 1: Yellow (Elletic Rebels, ally)
    (100, 150, 255),   # Player 2: Blue (Azincourne Empire, enemy)
]

# Faction display names
FACTION_NAMES = {
    0: None,               # Human player (use profile name)
    1: "Elletic Rebels",
    2: "Azincourne Empire",
}

# Starting gold per faction
STARTING_GOLD = {
    0: 2000,   # Human: boosted starting gold (2 territories, allied)
    1: 25000,  # Ally: massive gold reserve matching empire (2 territories, AI)
    2: 25000,  # Enemy: massive gold reserve for continuous unit production
}

# Victory condition: all 9 of these must be owned by team 0 (player 0 or player 1)
VICTORY_TERRITORIES = [
    "Elletian Isles", "Valeonia", "Velognia", "Elland",
    "Lentria", "Lobardia", "Venexia", "Révia", "The Holy Land",
]

# Defeat condition: if this territory is captured by player 2, the mission is lost
FAIL_TERRITORY = "Elletian Isles"

# Starting allied territories (for bonus achievement check)
STARTING_ALLIED_TERRITORIES = ["Nordica", "Leuse Valley", "Elland", "Elletian Isles"]

# Garrison requirements: minimum units that must remain in each AI territory.
# AI will not move units below this threshold when reinforcing or attacking.
GARRISON_REQUIREMENTS = {
    # Elletic Rebels (Player 1, ally)
    "Elletian Isles": 9,   # 5 Archers, 2 Pikeman, 2 Swordsman
    "Elland": 3,           # 3 Swordsman
    # Azincourne Empire (Player 2, enemy)
    "Valeonia": 6,         # 5 Pikeman, 1 Archer
    "Velognia": 6,         # 5 Swordsman, 1 Cavalry
    "Lobardia": 3,         # 3 Swordsman
    "Lentria": 4,          # 2 Pikeman, 2 Archers
    "The Holy Land": 4,    # 1 Archer, 1 Swordsman, 2 Cavalry
    "Révia": 0,            # no garrison required
    "Venexia": 2,          # 2 Swordsman
    "Amennia": 10,         # 10 Archers
    "Duchy of Daurels": 9, # 5 Archers, 4 Pikeman
    "Northern Heilonia": 8,# 4 Cavalry, 4 Swordsman
    "Aelatania": 9,        # 9 Cavalry
    "Londia": 15,          # 5 Archers, 5 Swordsman, 5 Pikeman (fortress — no units leave)
    "Courtieux": 12,       # 9 Cavalry, 3 Swordsman
}

# ============================================================================
# UNIT CREATION HELPERS (same pattern as campaign_mission_4.py)
# ============================================================================

_global_unit_id = 0


def _make_unit(unit_type, unit_id, level=0):
    """Create a single unit dict with the given type and level."""
    return {"type": unit_type, "id": unit_id, "status": "ready", "order": None, "xp": 0, "level": level}


def _make_units(composition, level=0):
    """Create a batch of units from a list of (type, count) tuples."""
    global _global_unit_id
    units = []
    for unit_type, count in composition:
        for _ in range(count):
            units.append(_make_unit(unit_type, _global_unit_id, level))
            _global_unit_id += 1
    return units


# ============================================================================
# TERRITORY SETUP — buildings and starting units per territory
# ============================================================================

TERRITORY_SETUP = {
    # ========== HUMAN (Player 0, Red) — level 1 units ==========
    "Nordica": {
        "owner": 0,
        "buildings": {0: "Barracks"},  # plot 1 empty
        "units": _make_units([("Pikeman", 3), ("Swordsman", 3), ("Archer", 2)], level=1),
    },
    "Leuse Valley": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Barracks"},  # plot 2 empty
        "units": _make_units([("Cavalry", 2), ("Swordsman", 3), ("Archer", 3), ("Pikeman", 1)], level=1),
    },

    # ========== ELLETIC REBELS (Player 1, Yellow, ally) — level 0 ==========
    "Elletian Isles": {
        "owner": 1,
        "buildings": {0: "Keep"},
        "units": _make_units([("Archer", 7), ("Pikeman", 3), ("Swordsman", 4)]),
    },
    "Elland": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_units([("Cavalry", 4), ("Swordsman", 3), ("Archer", 3)]),
    },

    # ========== AZINCOURNE EMPIRE (Player 2, Blue, enemy) — level 0 ==========
    # 13 territories with garrison requirements (see GARRISON_REQUIREMENTS)
    "Valeonia": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_units([("Pikeman", 7), ("Archer", 3)]),
    },
    "Velognia": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_units([("Swordsman", 7), ("Cavalry", 4)]),
    },
    "Lobardia": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_units([("Swordsman", 5)]),
    },
    "Lentria": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_units([("Pikeman", 4), ("Archer", 4)]),
    },
    "The Holy Land": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_units([("Archer", 2), ("Swordsman", 2), ("Cavalry", 2)]),
    },
    "Venexia": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_units([("Swordsman", 3)]),
    },
    "Révia": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": [],  # no starting units
    },
    "Amennia": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Barracks"},
        "units": _make_units([("Archer", 10)]),
    },
    "Duchy of Daurels": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_units([("Archer", 5), ("Pikeman", 5)]),
    },
    "Northern Heilonia": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Barracks"},
        "units": _make_units([("Cavalry", 6), ("Swordsman", 4)]),
    },
    "Aelatania": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_units([("Cavalry", 10)]),
    },
    "Londia": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_units([("Archer", 5), ("Swordsman", 5), ("Pikeman", 5)]),
    },
    "Courtieux": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Barracks", 2: "Barracks"},
        "units": _make_units([("Cavalry", 11), ("Swordsman", 4)]),
    },
}

# Intro sequence: zoom, transmissions with camera pans, then start game
# Speaker for all intro transmissions: "Rebellious Noble"
INTRO_SEQUENCE = [
    # Step 0: Zoom to Leuse Valley
    ("zoom_to", "Leuse Valley", ""),
    # Step 1: First transmission (5s voice line M5T1)
    ("wait", 5.0, "The time has come! The Azincourne Empire shall rule the east no longer!"),
    # Step 2: Second transmission (9s voice line M5T2)
    ("wait", 9.0, "We must reclaim what is rightfully ours! We have successfully driven them out of Nordica and the Leuse Valley, but we must not stop there!"),
    # Step 3: Pan camera to Elland (1s)
    ("pan_to", "Elland", ""),
    # Step 4: Third transmission (6s voice line M5T3)
    ("wait", 6.0, "The Elletic Rebels have also begun their assault on the mainland. Their help will be invaluable for our liberation!"),
    # Step 5: Pan camera back to Leuse Valley (1s)
    ("pan_to", "Leuse Valley", ""),
    # Step 6: Fourth transmission (4s voice line M5T4)
    ("wait", 4.0, "Seize our chance! Strike as one! Death to the oppressors!"),
    # Step 7: Start gameplay
    ("start_game", 0, ""),
]

# Voice line mapping (intro step index → voice key for M5T1–M5T4)
INTRO_STEP_TO_VOICE = {1: "M5T1", 2: "M5T2", 4: "M5T3", 6: "M5T4"}

# Speaker name used for all mission 5 transmissions
MISSION_5_SPEAKER = "Rebellious Noble"


# ============================================================================
# MISSION 5 CLASS
# ============================================================================

class Mission5:
    """
    Campaign Mission 5: The First War

    3 factions: Human (Red) + Elletic Rebels (Yellow, ally) vs Azincourne Empire (Blue).
    Players 0 and 1 are allied (team 0) against player 2 (team 1).
    Custom AI with per-territory garrison requirements for both AI players.
    Victory: 9 specific territories controlled by team 0.
    Defeat: Elletic Isles captured by enemy OR human loses all territories.
    """

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_5'
        self.active = True

        # AI turn timing (0.5s fast turns, same as mission 4)
        self.ai_turn_timer = 0.0
        self._ai_executed_this_turn = False  # Guard: prevent duplicate AI execution per turn

        # AI attack ramp: tracks how many turns each AI faction has taken
        # Ramp limits how many units can be sent in attacks/reinforcements per turn
        self.faction_turn_count = {1: 0, 2: 0}

        # Intro sequence state
        self.intro_active = True
        self.intro_step_index = 0
        self.intro_timer = 0.0
        self.intro_waiting_for_zoom = False
        self.intro_waiting_for_pan = False
        self.game_paused = True
        self.timer_visible = False

        # Camera animation
        self.camera_animation = None

        # Transmission overlay
        self.transmission_overlay = None
        self.transmission_timer = 0.0
        self.transmission_duration = 0.0

        # Transmission queue for gameplay events: list of (text, duration, voice_key) tuples
        self.transmission_queue = []
        # Inter-transmission pause timer (1s silent gap between consecutive voiced intro steps)
        self._intro_pause_timer = 0.0

        # Quest log — 2 objectives
        self.quest_log = [
            {'text': 'The Elletic Isles must not fall to the Azincourneans', 'completed': False},
            {'text': 'Liberate Valeonia, Velognia, Elland, Lentria, Lobardia, Venexia, Révia and the Neimer Coast', 'completed': False},
        ]

        # Victory/defeat sequence state (same attrs as mission 4, needed by campaign_utils)
        self.game_frozen = False
        self.victory_sequence_active = False
        self.victory_phase = None
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0
        self.victory_image = None
        self.victory_image_scale = 0.0

        self.defeat_sequence_active = False
        self.defeat_phase = None
        self.defeat_timer = 0.0
        self.defeat_fade_alpha = 0
        self.defeat_image = None
        self.defeat_image_scale = 0.0
        self._pending_defeat = False
        self._pending_victory = False
        self._victory_waiting = False
        self._defeat_waiting = False

        # Defeat text and voice key (set dynamically based on defeat cause)
        self._defeat_text = "We have failed. And the suffering of our people shall not end.."
        self._defeat_voice_key = "M5T7"

        # Allow turn timer to auto-end player turns
        self.allow_timer_expiry = True

        # Store original flag icons for restoration on cleanup
        self.original_flag_icons = None

        # Set up territory filtering and display names
        map_data.set_enabled_territories(MISSION_5_TERRITORIES)
        map_data.set_territory_display_names(MISSION_5_DISPLAY_NAMES)

        # Set up initial game state
        self._setup_initial_state()

        # Start intro sequence
        self._start_intro_sequence()

        logger.info("Mission 5 'The First War' initialized: 17 territories, 3 factions, teams [0, 0, 1]")

    def _setup_initial_state(self):
        """Configure the game state for Mission 5 scenario."""
        gs = self.game_state

        # Set player colors (3 players)
        for i, color in enumerate(PLAYER_COLORS):
            if i < len(gs.player_colors):
                gs.player_colors[i] = color

        # Remap flag icons to match player colors
        # Default flag order: 0=Red, 1=Blue, 2=Green, 3=Yellow
        # Mission 5: Player 0=Red (keep), Player 1=Yellow (from slot 3), Player 2=Blue (from slot 1)
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and len(game.army_flag_icons) >= 4:
            self.original_flag_icons = {i: game.army_flag_icons[i] for i in range(4)}
            # Player 0 (Red) = original index 0 — no change needed
            game.army_flag_icons[1] = self.original_flag_icons[3]  # Yellow for Elletic Rebels
            game.army_flag_icons[2] = self.original_flag_icons[1]  # Blue for Azincourne Empire

        # Set faction names
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name

        # Set starting gold per faction
        for player_id, gold in STARTING_GOLD.items():
            if player_id < gs.num_players:
                gs.player_gold[player_id] = gold

        # Configure each territory from TERRITORY_SETUP
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
        mission_set = set(MISSION_5_TERRITORIES)
        for territory in list(gs.territory_owners.keys()):
            if territory not in mission_set:
                gs.territory_owners[territory] = -1
                gs.territory_garrisons[territory] = {}
                gs.buildings[territory] = {}

        # Invalidate bonus cache after bulk territory setup
        gs.invalidate_territorial_bonus_cache()

        # Set starting territories for reference
        gs.player_starting_territories[0] = "Nordica"
        gs.player_starting_territories[1] = "Elletian Isles"
        gs.player_starting_territories[2] = "Aelatania"

        # --- Pre-researched technologies for human player ---
        # Efficient Farming I (tech_0_0) and Master Planner I (tech_2_0)
        # give early economic and planning advantages
        pre_researched = [
            'tech_0_0',  # Efficient Farming I: +20% Farm income (checked inline in economy)
            'tech_2_0',  # Master Planner I: +30s planning time
        ]
        for tech_id in pre_researched:
            gs.player_tech_researched[0].add(tech_id)
            gs.player_tech_available[0].discard(tech_id)

        # Apply tech effects directly (mirror finish_research logic)
        # tech_0_0: Efficient Farming I — effect checked inline in income calculations, no attribute needed
        # tech_2_0: Master Planner I — +30s planning time
        gs.player_planning_time_limit[0] += 30

        # Unlock next tier techs (row 1 in each column where we researched row 0)
        gs.player_tech_available[0].add('tech_0_1')  # Efficient Mining I (next in col 0)
        gs.player_tech_available[0].add('tech_2_1')  # Improved Command I (next in col 2)

        # --- Pre-researched technologies for Azincourne Empire (player 2) ---
        # All column 2 techs (Master Planner row). Gives +70 command limit (75 → 145),
        # which lets the empire train beyond its ~85 starting units with 25k gold.
        # Also requires a Castle for row 4+ techs.
        gs.castle_upgrades['Aelatania'] = {0: True}  # Castle at Aelatania (plot 0 = Keep)
        p2_pre_researched = [
            'tech_2_0',  # Master Planner I: +30s planning time
            'tech_2_1',  # Improved Command I: +35 command limit (75 → 110)
            'tech_2_2',  # Royal Decree: Hero/Keep -15%
            'tech_2_3',  # Master Planner II: +30s planning time (requires castle)
            'tech_2_4',  # Heroic Fortitude: hero limit to 4 (requires castle)
            'tech_2_5',  # Improved Command II: +35 command limit (110 → 145)
            'tech_2_6',  # Last Resort: hero keep defense +2 (requires castle)
        ]
        for tech_id in p2_pre_researched:
            gs.player_tech_researched[2].add(tech_id)
            gs.player_tech_available[2].discard(tech_id)

        # Apply tech effects directly for player 2 (mirror finish_research logic)
        gs.player_planning_time_limit[2] += 30           # tech_2_0: +30s
        gs.player_command_limit[2] += 35                 # tech_2_1: +35 command limit
        gs.player_royal_decree_discount[2] = 15          # tech_2_2: Hero/Keep -15%
        gs.player_planning_time_limit[2] += 30           # tech_2_3: +30s (Master Planner II)
        gs.player_hero_limit[2] = 4                      # tech_2_4: hero limit to 4
        gs.player_command_limit[2] += 35                 # tech_2_5: +35 command limit (total +70)
        gs.player_hero_keep_defense_bonus[2] = 2         # tech_2_6: hero keep defense +2
        # No next-tier to unlock — entire column 2 is researched

        # --- Castle upgrade at Elletian Isles for Elletic Rebels (player 1, plot 0 = Keep) ---
        # Gives the ally faction a Castle, unlocking castle-tier tech research
        gs.castle_upgrades['Elletian Isles'] = {0: True}

        # --- Pre-researched technologies for Elletic Rebels (player 1) ---
        # Rows 0-3 of all 3 columns (12 techs total). Rows 4-6 are NOT researched.
        p1_pre_researched = [
            'tech_0_0', 'tech_0_1', 'tech_0_2', 'tech_0_3',  # Efficient Farming I, Efficient Mining I, Leave Nothing Behind, Supply and Demand
            'tech_1_0', 'tech_1_1', 'tech_1_2', 'tech_1_3',  # Improved Training, Makeshift Barracks, Animal Handling, Battlement Archery
            'tech_2_0', 'tech_2_1', 'tech_2_2', 'tech_2_3',  # Master Planner I, Improved Command I, Royal Decree, Master Planner II
        ]
        for tech_id in p1_pre_researched:
            gs.player_tech_researched[1].add(tech_id)
            gs.player_tech_available[1].discard(tech_id)

        # Apply tech effects directly for player 1 (mirror finish_research logic)
        # tech_0_0: Efficient Farming I — +20% Farm income (checked inline in economy)
        # tech_0_1: Efficient Mining I — +20% Mine income (checked inline in economy)
        # tech_0_2: Leave Nothing Behind — 50% recovery on Farm/Mine destruction (checked inline)
        # tech_0_3: Supply and Demand — Squares multiply by 2.5x (checked inline, requires castle)
        gs.player_training_cost_discount[1] = 20       # tech_1_0: Swordsman/Pikeman -20%
        gs.player_barracks_cost_discount[1] = 25        # tech_1_1: Barracks -25%
        gs.player_barracks_full_refund[1] = True         # tech_1_1: 100% demolish refund
        gs.player_cavalry_cost_discount[1] = 25          # tech_1_2: Cavalry -25%
        gs.player_archer_keep_strength_bonus[1] = 50     # tech_1_3: Archers +50% near Keep/Castle
        gs.player_planning_time_limit[1] += 30           # tech_2_0: +30s planning time
        gs.player_command_limit[1] += 35                 # tech_2_1: +35 command limit
        gs.player_royal_decree_discount[1] = 15          # tech_2_2: Hero/Keep -15%
        gs.player_planning_time_limit[1] += 30           # tech_2_3: +30s planning time (Master Planner II)

        # Unlock next tier techs for player 1 — row 4 in each column (requires castle, which we gave)
        gs.player_tech_available[1].add('tech_0_4')  # Efficient Farming II
        gs.player_tech_available[1].add('tech_1_4')  # Raze the Countryside
        gs.player_tech_available[1].add('tech_2_4')  # Heroic Fortitude

        logger.info("Mission 5 initial state configured: 17 territories, 2 human pre-researched techs, 12 ally pre-researched techs, Castle at Elletian Isles")

    # ========================================================================
    # INTRO SEQUENCE
    # ========================================================================

    def _start_intro_sequence(self):
        """Start the intro sequence."""
        self.intro_active = True
        self.intro_step_index = 0
        self.intro_timer = 0.0
        self.game_paused = True
        self._execute_intro_step()

    def _execute_intro_step(self):
        """Execute the current intro sequence step."""
        if self.intro_step_index >= len(INTRO_SEQUENCE):
            self._end_intro_sequence()
            return

        action, param, text = INTRO_SEQUENCE[self.intro_step_index]

        if action == 'zoom_to':
            # Start zoom animation to target territory
            try:
                import main as _main
                map_area_height = _main.MAP_HEIGHT
            except (ImportError, AttributeError):
                map_area_height = self.main_game.screen.get_height()
            camera = self.main_game.camera
            sw = self.main_game.screen.get_width()
            target_center = self.main_game.scaled_centers.get(
                param, map_data.get_territory_center(param)
            )
            self.camera_animation = CameraZoomAnimation(
                camera_handler=camera,
                start_zoom=camera.zoom,
                target_zoom=getattr(camera, 'max_zoom', 1.5),
                duration=1.0,
                target_center_world=target_center,
                screen_width=sw,
                map_area_height=map_area_height,
            )
            self.intro_waiting_for_zoom = True
            self.intro_timer = 0.0

        elif action == 'pan_to':
            # Pan camera to target territory — hide text and stop voice during pan
            self._start_pan_animation(param, duration=2.0)
            self.intro_waiting_for_pan = True
            self.transmission_overlay = None
            from global_sound import stop_transmission_sound
            stop_transmission_sound()

        elif action == 'wait':
            # Show transmission text and wait for duration
            self.intro_timer = 0.0
            if text:
                self._show_transmission(text, speaker=MISSION_5_SPEAKER)
                self.transmission_duration = param
                # Play voice line for this intro step if mapped
                voice_key = INTRO_STEP_TO_VOICE.get(self.intro_step_index)
                if voice_key:
                    from global_sound import play_transmission_sound
                    play_transmission_sound(voice_key)
            else:
                self.transmission_overlay = None
                self.transmission_duration = param

        elif action == 'start_game':
            self._end_intro_sequence()

    def _end_intro_sequence(self):
        """End the intro and start gameplay."""
        from global_sound import stop_transmission_sound
        self.intro_active = False
        self.game_paused = False
        self.timer_visible = True
        self.transmission_overlay = None
        self.camera_animation = None
        stop_transmission_sound()  # Stop any lingering intro voice
        # Reset planning timer so it starts fresh after intro (not from game init)
        self.game_state.planning_phase_start_time = time.time()
        logger.info("Intro sequence complete — gameplay begins")

    def _start_pan_animation(self, territory, duration=1.0):
        """Start camera pan animation to a territory (no zoom change)."""
        try:
            import main as _main
            map_area_height = _main.MAP_HEIGHT
        except (ImportError, AttributeError):
            map_area_height = self.main_game.screen.get_height()
        camera = self.main_game.camera
        sw = self.main_game.screen.get_width()
        target_center = self.main_game.scaled_centers.get(
            territory, map_data.get_territory_center(territory)
        )
        self.camera_animation = CameraPanAnimation(
            camera_handler=camera,
            target_center_world=target_center,
            duration=duration,
            screen_width=sw,
            map_area_height=map_area_height,
        )

    def _show_transmission(self, text, speaker="Commander"):
        """Show or update the transmission overlay with optional speaker name."""
        import main as _main
        TOP_PANEL_HEIGHT = _main.TOP_PANEL_HEIGHT
        screen = self.main_game.screen
        sw = screen.get_width()
        sh = screen.get_height()
        if not self.transmission_overlay:
            self.transmission_overlay = TransmissionOverlay(sw, sh, text, TOP_PANEL_HEIGHT, speaker=speaker)
        else:
            self.transmission_overlay.set_text(text, speaker=speaker)

    def _queue_transmission(self, text, duration, voice_key=None):
        """Queue a transmission to show during gameplay. Supports multiple queued messages."""
        self.transmission_queue.append((text, duration, voice_key))

    def _start_pending_transmission(self):
        """Start showing the next queued transmission. Plays voice if key provided."""
        if self.transmission_queue:
            text, duration, voice_key = self.transmission_queue.pop(0)
            self._show_transmission(text)
            self.transmission_duration = duration
            self.transmission_timer = 0.0
            if voice_key:
                from global_sound import play_transmission_sound
                play_transmission_sound(voice_key)

    def _is_gameplay_idle(self):
        """Check if gameplay is idle (no battles, popups, turn announcements, or animations).

        Used to gate transmissions and victory/defeat sequences so they don't
        overlap with battle reports or turn start animations.
        Also considers game idle when phase is 'ended' (turn advancement blocked, no new battles).
        """
        gs = self.game_state
        battle_popup_open = getattr(self.main_game, 'battle_popup_visible', False)
        phase_ok = gs.turn_phase == 'planning' or gs.phase == 'ended'
        return (phase_ok
                and not gs.pending_battles
                and not battle_popup_open
                and not gs.turn_announcement_active)

    # ========================================================================
    # UPDATE (called every frame)
    # ========================================================================

    def update(self, delta_time):
        """Called every frame to update mission state."""
        if not self.active:
            return None
        # Cap delta_time to prevent animation jumps on large frame times
        delta_time = min(delta_time, 0.05)

        # Update camera animation (zoom or pan)
        if self.camera_animation:
            self.camera_animation.update(delta_time)
            if not self.camera_animation.active:
                if self.intro_waiting_for_zoom:
                    self.intro_waiting_for_zoom = False
                    self.intro_step_index += 1
                    self._execute_intro_step()
                elif self.intro_waiting_for_pan:
                    self.intro_waiting_for_pan = False
                    self.intro_step_index += 1
                    self._execute_intro_step()
                self.camera_animation = None

        # Process inter-transmission pause (1s gap between consecutive voiced intro steps)
        if self._intro_pause_timer > 0:
            self._intro_pause_timer -= delta_time
            if self._intro_pause_timer <= 0:
                self._intro_pause_timer = 0
                self.intro_step_index += 1
                self._execute_intro_step()
            return None  # Don't process intro timer during pause

        # Update intro timing
        if self.intro_active and not self.intro_waiting_for_zoom and not self.intro_waiting_for_pan:
            action = INTRO_SEQUENCE[self.intro_step_index][0] if self.intro_step_index < len(INTRO_SEQUENCE) else None
            if action == 'wait':
                self.intro_timer += delta_time
                if self.intro_timer >= self.transmission_duration:
                    # Check if next step has text — if so, insert 1s pause
                    next_idx = self.intro_step_index + 1
                    if next_idx < len(INTRO_SEQUENCE) and INTRO_SEQUENCE[next_idx][2]:
                        # Next step has text: pause before advancing
                        from global_sound import stop_transmission_sound
                        self.transmission_overlay = None
                        stop_transmission_sound()
                        self._intro_pause_timer = 1.0
                    else:
                        # Next step has no text (zoom/start_game): advance immediately
                        self.intro_step_index += 1
                        self._execute_intro_step()

        # Instant AI turns: skip turn announcement animation for AI players
        # This immediately completes the announcement and lets AI execute without delay
        if not self.intro_active:
            gs = self.game_state
            if gs.current_player != 0 and gs.turn_announcement_active:
                # Kill any pending turn announcement effect in main game
                game = self.main_game
                if hasattr(game, 'turn_announcement_effect') and game.turn_announcement_effect:
                    game.turn_announcement_effect.cleanup()
                    game.turn_announcement_effect = None
                # Immediately complete the turn start effects
                gs._complete_turn_announcement()

        # Gameplay transmission timer — stop voice when text expires
        if not self.intro_active and self.transmission_overlay and self.transmission_duration > 0:
            self.transmission_timer += delta_time
            if self.transmission_timer >= self.transmission_duration:
                self.transmission_overlay = None
                self.transmission_duration = 0.0
                from global_sound import stop_transmission_sound
                stop_transmission_sound()

        # Check if gameplay is idle (no battles, popups, or animations blocking)
        gameplay_idle = self._is_gameplay_idle()

        # Start next queued transmission only when gameplay is idle
        if not self.intro_active and not self.transmission_overlay and self.transmission_queue:
            if gameplay_idle:
                self._start_pending_transmission()

        # Deferred victory: wait until all battles/popups closed AND queued transmissions shown
        if self._victory_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.transmission_queue:
                self._victory_waiting = False
                self._pending_victory = True
                self.game_paused = True

                text = "We have prevailed! The Azincournean Empire cannot hold! Liberation is at hand!"
                self._show_transmission(text, speaker=MISSION_5_SPEAKER)
                self.transmission_duration = 6.0
                self.transmission_timer = 0.0
                # Play victory voice line M5T5
                from global_sound import play_transmission_sound
                play_transmission_sound("M5T5")

        # Deferred defeat: same pattern — wait for battles/popups, then show defeat
        if self._defeat_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.transmission_queue:
                self._defeat_waiting = False
                self._pending_defeat = True
                self.game_paused = True

                self._show_transmission(self._defeat_text, speaker=MISSION_5_SPEAKER)
                self.transmission_duration = 4.0
                self.transmission_timer = 0.0
                # Play defeat voice line (M5T6 for ally defeat, M5T7 for player defeat)
                from global_sound import play_transmission_sound
                play_transmission_sound(self._defeat_voice_key)

        # Update victory sequence — return 'exit_campaign' to tell main.py to exit game loop
        result = self._update_victory_sequence(delta_time)
        if result == 'exit':
            self._cleanup()
            return 'exit_campaign'

        # Update defeat sequence
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
            self.intro_waiting_for_zoom = False
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
    # AI CONTROL — custom AI with per-territory garrison requirements
    # ========================================================================

    @property
    def block_ai(self):
        """Block normal AI for all AI players — Mission5 controls their behavior
        via execute_ai_turn_override() with garrison requirement enforcement."""
        if self.intro_active:
            return True
        current_player = self.game_state.current_player
        if current_player == 0:
            return False  # Human player
        return True  # Block normal AI for all AI factions

    @property
    def block_ai_thinking(self):
        return False

    def get_ai_thinking_text(self):
        """Override AI thinking indicator."""
        return ("Enemies thinking...", "")

    def execute_ai_turn_override(self):
        """Called instead of normal AI execution. Dispatches to custom faction AI
        that respects per-territory garrison requirements.

        Note: Called EVERY FRAME by ai_player.execute_turn() because block_ai
        bypasses the turn_in_progress guard. We use _ai_executed_this_turn to
        ensure the AI logic only runs once per turn.
        """
        current_player = self.game_state.current_player
        if current_player == 0:
            return

        # Guard: only execute AI once per turn (this method is called every frame)
        if self._ai_executed_this_turn:
            return
        self._ai_executed_this_turn = True

        # Execute the custom faction AI with garrison enforcement
        self._execute_faction_ai(current_player)

    def update_ai_turn(self, delta_time):
        """Handle AI turn timing. Returns True if AI turn is being managed."""
        if not self.active or self.intro_active:
            return False

        current_player = self.game_state.current_player
        if current_player == 0:
            return False  # Not AI turn

        gs = self.game_state

        # Force-complete turn announcement for AI players immediately.
        # main.py gates handle_ai_turn() behind `not turn_announcement_active`,
        # so if we don't clear this, the AI never gets to execute its turn.
        if gs.turn_announcement_active:
            if hasattr(gs, '_complete_turn_announcement'):
                gs._complete_turn_announcement()
            else:
                gs.turn_announcement_active = False

        # Wait for execution animations to complete
        if gs.turn_phase == 'execution':
            return True

        # Auto-resolve any pending battles
        if gs.turn_phase == 'battles' and gs.pending_battles:
            self._auto_resolve_battles()
            return True

        # 0.5s fast AI turns
        self.ai_turn_timer += delta_time
        if self.ai_turn_timer >= 0.5:
            self.ai_turn_timer = 0.0
            self._ai_executed_this_turn = False  # Reset guard for next AI player
            gs.next_player()

        return True

    def _auto_resolve_battles(self):
        """Auto-resolve all pending battles during AI turn."""
        gs = self.game_state
        if not gs.pending_battles:
            return
        for battle_idx in range(len(gs.pending_battles) - 1, -1, -1):
            if battle_idx < len(gs.pending_battles):
                gs.resolve_battle(battle_idx)

    # ========================================================================
    # CUSTOM FACTION AI — build, train, reinforce, attack with garrison limits
    # ========================================================================

    def _execute_faction_ai(self, player_id):
        """Execute AI for a faction: build, train, reinforce, then attack.

        All movement respects GARRISON_REQUIREMENTS — units below the minimum
        for a territory are never moved away.
        Alliance-aware: AI uses game_state.are_allies() to determine enemies.

        Per-faction behavior:
        - Elletic Rebels (player 1): Aggressive — no unit cap on reinforce/attack.
        - Azincourne Empire (player 2): Defensive — reinforces freely, but only
          sends token attacks (1 unit) each turn.
        """
        gs = self.game_state

        # Increment turn counter for this faction
        self.faction_turn_count[player_id] = self.faction_turn_count.get(player_id, 0) + 1

        # Per-faction caps: (max_reinforce, max_attack)
        # Player 1 (Elletic Rebels): aggressive — unlimited reinforce and attack
        # Player 2 (Azincourne Empire): defensive — unlimited reinforce, token 1-unit attacks
        if player_id == 1:
            max_reinforce = 999  # No practical limit — send everything forward
            max_attack = 999     # Full aggression — attack with all available units
        else:
            max_reinforce = 999  # Freely reinforce and fortify territories
            max_attack = 1       # Token attacks only — defensive posture

        # Find territories owned by this faction
        my_territories = [t for t in MISSION_5_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return  # Faction eliminated

        # Phase 1: Build structures on empty plots
        self._ai_build(player_id, my_territories)

        # Phase 2: Train units at all barracks
        self._ai_train(player_id, my_territories)

        # Phase 3: Reinforce frontline from rear (respecting garrison requirements)
        self._ai_reinforce(player_id, my_territories, max_reinforce)

        # Phase 4: Attack enemy territories (respecting garrison requirements)
        self._ai_attack(player_id, my_territories, max_attack)

    def _get_available_units(self, territory, player_id):
        """Get units available to move (above garrison minimum).

        Returns list of ready units that can be moved without violating
        the territory's garrison requirement.
        """
        gs = self.game_state
        garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
        units = garrison.get('units', [])
        ready_units = [u for u in units if u.get('status') == 'ready']

        min_garrison = GARRISON_REQUIREMENTS.get(territory, 0)
        available_count = len(ready_units) - min_garrison
        if available_count <= 0:
            return []
        return ready_units[:available_count]

    def _ai_build(self, player_id, my_territories):
        """Build structures on empty plots. Prioritize Barracks, then economy."""
        gs = self.game_state

        for territory in my_territories:
            # Check one building per territory per turn
            if territory in gs.buildings_started_this_turn:
                continue

            plots = map_data.get_plots(territory)
            buildings = gs.buildings.get(territory, {})

            for plot_idx in range(len(plots)):
                # Skip occupied plots
                if plot_idx in buildings:
                    continue
                # Skip plots under construction
                if territory in gs.under_construction and plot_idx in gs.under_construction[territory]:
                    continue

                # Decide what to build: Barracks if none, else Farm
                has_barracks = any(b == 'Barracks' for b in buildings.values())
                if not has_barracks:
                    building_type = 'Barracks'
                else:
                    building_type = 'Farm'

                cost = gs.get_building_cost(building_type, player=player_id)
                if gs.player_gold[player_id] >= cost:
                    # Use try/finally to restore current_player on exception
                    original_player = gs.current_player
                    try:
                        gs.current_player = player_id
                        gs.start_construction(territory, plot_idx, building_type)
                    finally:
                        gs.current_player = original_player
                    break  # One building per territory per turn

    def _ai_train(self, player_id, my_territories):
        """Train units at all barracks whenever affordable. Cycle unit types for variety."""
        gs = self.game_state

        # Cycle through unit types for variety (based on game turn number)
        unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
        type_idx = gs.turn_number % len(unit_types)

        for territory in my_territories:
            buildings = gs.buildings.get(territory, {})
            for plot_idx, building in buildings.items():
                if building != 'Barracks':
                    continue

                # Check if already training at this barracks
                training_queue = gs.training_queue.get(territory, {})
                if plot_idx in training_queue:
                    continue

                # Check army limit
                total_units = sum(len(g.get('units', []))
                                  for g in gs.territory_garrisons.get(territory, {}).values())
                if total_units >= gs.MAX_ARMIES_PER_TERRITORY:
                    continue

                # Pick unit type and check affordability
                unit_type = unit_types[type_idx % len(unit_types)]
                cost = gs.UNIT_TYPES[unit_type]['cost']
                if gs.player_gold[player_id] >= cost:
                    original_player = gs.current_player
                    try:
                        gs.current_player = player_id
                        gs.start_training(territory, plot_idx, unit_type)
                    finally:
                        gs.current_player = original_player
                    type_idx += 1

    def _ai_reinforce(self, player_id, my_territories, max_units):
        """Move excess units (above garrison minimum) from rear toward frontline.

        Frontline = territories adjacent to an enemy. Rear = everything else.
        Only moves units above GARRISON_REQUIREMENTS threshold.
        Capped at max_units total units moved per turn (ramp limit).
        """
        gs = self.game_state
        units_moved = 0

        # Identify enemy territories (not owned by self or allies)
        enemy_territories = set()
        for t in MISSION_5_TERRITORIES:
            t_owner = gs.territory_owners.get(t, -1)
            if t_owner >= 0 and t_owner != player_id and not gs.are_allies(player_id, t_owner):
                enemy_territories.add(t)

        if not enemy_territories:
            return

        # Identify frontline territories (adjacent to an enemy)
        frontline = set()
        for t in my_territories:
            neighbors = map_data.get_neighbors(t)
            for n in neighbors:
                if n in enemy_territories:
                    frontline.add(t)
                    break

        # Identify rear territories (not on frontline, have available units)
        rear_territories = [t for t in my_territories if t not in frontline]

        for rear_t in rear_territories:
            if units_moved >= max_units:
                break

            available = self._get_available_units(rear_t, player_id)
            if not available:
                continue

            # Find adjacent territory closer to frontline (prefer own frontline territories)
            neighbors = map_data.get_neighbors(rear_t)
            best_target = None
            for n in neighbors:
                if n in frontline:
                    best_target = n
                    break
                if gs.territory_owners.get(n) == player_id and n not in rear_territories:
                    best_target = n

            if best_target:
                # Check army limit at target, cap by ramp budget
                target_units = sum(len(g.get('units', []))
                                   for g in gs.territory_garrisons.get(best_target, {}).values())
                available_slots = gs.MAX_ARMIES_PER_TERRITORY - target_units
                remaining_budget = max_units - units_moved
                count = min(len(available), available_slots, remaining_budget)
                units_to_move = available[:count]

                if units_to_move:
                    unit_ids = [u['id'] for u in units_to_move]
                    gs.add_movement_order_for_units(rear_t, best_target, unit_ids, player=player_id)
                    units_moved += len(units_to_move)

    def _ai_attack(self, player_id, my_territories, max_units):
        """Attack enemy territories with units above garrison minimum.

        Alliance-aware: only attacks territories owned by non-allied players.
        Respects GARRISON_REQUIREMENTS for source territories.
        max_units caps the TOTAL number of units sent across all attack orders this turn.
        """
        gs = self.game_state
        units_sent = 0

        # Find enemy territories adjacent to our territories
        enemy_territories = set()
        for t in MISSION_5_TERRITORIES:
            t_owner = gs.territory_owners.get(t, -1)
            if t_owner >= 0 and t_owner != player_id and not gs.are_allies(player_id, t_owner):
                enemy_territories.add(t)

        if not enemy_territories:
            return

        # Build attack candidates: (source, target, available_count, score)
        attack_candidates = []

        for my_t in my_territories:
            available = self._get_available_units(my_t, player_id)
            if not available:
                continue

            # Check which enemy territories are adjacent
            neighbors = map_data.get_neighbors(my_t)
            for neighbor in neighbors:
                if neighbor in enemy_territories:
                    # Score: prefer weakly defended targets
                    target_owner = gs.territory_owners.get(neighbor, -1)
                    target_garrison = gs.territory_garrisons.get(neighbor, {}).get(target_owner, {})
                    target_units = len(target_garrison.get('units', []))
                    score = len(available) - target_units  # Higher = better odds
                    attack_candidates.append((my_t, neighbor, len(available), score))

        # Sort by score (best odds first)
        attack_candidates.sort(key=lambda x: x[3], reverse=True)

        # Execute attacks up to ramp limit — each source territory attacks once
        used_sources = set()
        for my_t, target, _, score in attack_candidates:
            if units_sent >= max_units:
                break
            if my_t in used_sources:
                continue

            # Re-fetch available units (may have changed from reinforcement orders)
            available = self._get_available_units(my_t, player_id)
            if not available:
                continue

            # Cap units to send by remaining ramp budget
            remaining_budget = max_units - units_sent
            send_count = min(len(available), remaining_budget)
            units_to_send = available[:send_count]

            if units_to_send:
                unit_ids = [u['id'] for u in units_to_send]
                gs.add_movement_order_for_units(my_t, target, unit_ids, player=player_id)
                used_sources.add(my_t)
                units_sent += len(units_to_send)
                logger.debug(f"AI {player_id} turn {self.faction_turn_count[player_id]}: "
                           f"attacking {target} from {my_t} with {len(units_to_send)} units "
                           f"(budget {units_sent}/{max_units})")

    # ========================================================================
    # ACTION GATING
    # ========================================================================

    def is_action_allowed(self, action_type, **kwargs):
        """Check if a player action is permitted."""
        if not self.active:
            return True

        # Block all actions during intro, victory, or defeat
        if self.intro_active or self.victory_sequence_active or self.defeat_sequence_active:
            return False

        if self.game_paused or self.game_frozen:
            return False

        # Block hero training for all players
        if action_type == 'train_hero':
            return False

        return True

    def should_hide_hero_training(self):
        """Hide hero training UI — no heroes in this mission."""
        return True

    def should_button_be_locked(self, button_id):
        """Check if a button should be grayed out. Returns False for normal behavior."""
        return False

    def is_button_locked(self, button_id):
        """Alias for should_button_be_locked — used by main.py UI code."""
        return self.should_button_be_locked(button_id)

    def should_highlight_button(self, button_id):
        """Check if a button should be highlighted. Returns False for normal behavior."""
        return False

    def is_timer_visible(self):
        """Control turn timer visibility."""
        return self.timer_visible

    # ========================================================================
    # EVENT HANDLING
    # ========================================================================

    def notify_event(self, event_type, **kwargs):
        """Receive gameplay events from hooked game systems."""
        if not self.active or self.intro_active:
            return

        if event_type == 'territory_conquered':
            territory = kwargs.get('territory')
            new_owner = kwargs.get('new_owner')
            self._on_territory_conquered(territory, new_owner)

    def _on_territory_conquered(self, territory, new_owner):
        """Handle territory conquest — check victory and defeat conditions.

        Victory: all 9 VICTORY_TERRITORIES owned by team 0 (player 0 or player 1).
        Defeat: Elletic Isles captured by Azincourne (player 2), or human loses all territories.
        """
        gs = self.game_state

        # --- DEFEAT CHECK 1: Elletic Isles captured by enemy (player 2) ---
        if territory == FAIL_TERRITORY and new_owner == 2:
            logger.info("Elletic Isles fell to Azincourne — defeat!")
            self._defeat_text = "Our allies have been defeated! Without them, all hope is lost!"
            self._defeat_voice_key = "M5T6"
            self._start_defeat()
            return

        # --- DEFEAT CHECK 2: Human player lost all territories ---
        human_has_territory = any(
            gs.territory_owners.get(t) == 0 for t in MISSION_5_TERRITORIES
        )
        if not human_has_territory:
            logger.info("Human player eliminated — defeat!")
            self._defeat_text = "We have failed. And the suffering of our people shall not end.."
            self._defeat_voice_key = "M5T7"
            self._start_defeat()
            return

        # --- VICTORY CHECK: All 9 victory territories owned by team 0 ---
        all_liberated = True
        for vt in VICTORY_TERRITORIES:
            owner = gs.territory_owners.get(vt, -1)
            # Team 0 = player 0 or player 1
            if owner != 0 and owner != 1:
                all_liberated = False
                break

        if all_liberated:
            # Update quest log
            self.quest_log[0]['completed'] = True  # Elletic Isles survived
            self.quest_log[1]['completed'] = True  # Liberation complete
            logger.info("All victory territories liberated — victory!")
            self._start_victory()

    # ========================================================================
    # VICTORY SEQUENCE
    # ========================================================================

    def _start_victory(self):
        """Start the victory sequence (deferred until battles finish)."""
        if self.victory_sequence_active or self._pending_victory or self._victory_waiting:
            return

        logger.info("Victory condition met — waiting for battles/animations to finish")
        self.game_state.winner = 0
        self.game_state.phase = 'ended'
        self._victory_waiting = True

    def _update_victory_sequence(self, delta_time):
        """Update victory animation. Returns 'exit' when done.
        Delegates to shared update_endgame_sequence() from campaign_utils.
        """
        return update_endgame_sequence(self, delta_time, 'victory')

    def _render_victory_sequence(self, screen):
        """Render the victory sequence overlay.
        Delegates to shared render_endgame_sequence() from campaign_utils.
        """
        render_endgame_sequence(self, screen, 'victory')

    # ========================================================================
    # DEFEAT SEQUENCE
    # ========================================================================

    def _start_defeat(self):
        """Start the defeat sequence (deferred until battles finish)."""
        if self.defeat_sequence_active or self._pending_defeat or self._defeat_waiting:
            return

        logger.info("Player defeated — waiting for battles/animations to finish")
        self.game_state.phase = 'ended'
        self._defeat_waiting = True

    def _update_defeat_sequence(self, delta_time):
        """Update defeat animation. Returns 'exit' when done.
        Delegates to shared update_endgame_sequence() from campaign_utils.
        """
        return update_endgame_sequence(self, delta_time, 'defeat')

    def _render_defeat_sequence(self, screen):
        """Render the defeat sequence overlay.
        Delegates to shared render_endgame_sequence() from campaign_utils.
        """
        render_endgame_sequence(self, screen, 'defeat')

    # ========================================================================
    # RENDERING
    # ========================================================================

    def render(self, screen):
        """Called after normal game rendering to draw mission overlays."""
        if not self.active:
            return

        # Victory sequence takes over rendering
        if self.victory_sequence_active or self._pending_victory:
            if self.victory_sequence_active:
                self._render_victory_sequence(screen)
            if self.transmission_overlay:
                self.transmission_overlay.render(screen)
            return

        # Defeat sequence takes over rendering
        if self.defeat_sequence_active or self._pending_defeat:
            if self.defeat_sequence_active:
                self._render_defeat_sequence(screen)
            if self.transmission_overlay:
                self.transmission_overlay.render(screen)
            return

        # Draw transmission board if visible
        if self.transmission_overlay:
            self.transmission_overlay.render(screen)

    # ========================================================================
    # QUEST LOG
    # ========================================================================

    def get_quest_log(self):
        """Return the quest log list for the Quests tab UI."""
        return self.quest_log

    # ========================================================================
    # TERRITORY INTERACTION
    # ========================================================================

    def is_territory_interactive(self, territory_name):
        """Check if a territory can be hovered/clicked."""
        if not self.active:
            return True
        return territory_name in MISSION_5_TERRITORIES

    def get_adjacency_override(self, territory):
        """No special adjacency restrictions in Mission 5."""
        return None

    def get_highlight_territory(self):
        """No step-based territory highlighting in Mission 5."""
        return None

    def should_highlight_plot(self, territory, plot_index):
        """No plot highlights in Mission 5."""
        return False

    def get_bonus_conditions(self):
        """Return bonus achievement conditions for Mission 5.

        Bonus "Change of Command": Azincourne Empire (player 2) owns no territories.
        Covers both their starting 13 and any they may have conquered during the game.
        """
        gs = self.game_state
        azincourne_has_no_territories = not any(
            gs.territory_owners.get(t) == 2 for t in MISSION_5_TERRITORIES
        )
        return {
            'campaign_mission_5_bonus': azincourne_has_no_territories,
        }

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def _cleanup(self):
        """Clean up mission state when exiting."""
        from global_sound import stop_transmission_sound
        logger.info("Cleaning up Mission 5")
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
