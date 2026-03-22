# -*- coding: utf-8 -*-
# campaign_mission_7.py
# Campaign Mission 7: The Fall
# 2 factions: Human (Blue, player 0) vs Central Alliance (Red AI, player 1).
# Human has 23 territories, Central Alliance has 18 territories.
# Custom AI with garrison enforcement on 6 core territories (min 13 armies).
# Victory: Conquer all Central Alliance territories.
# Defeat: Lose all territories, OR Courtieux falls, OR Lunedale falls.

import copy
import random
import pygame
import time
import map_data
from utils.logger import get_logger
# Shared campaign utilities (TransmissionOverlay, camera animations, endgame sequences)
from campaign_utils import TransmissionOverlay, CameraZoomAnimation, CameraPanAnimation
from campaign_utils import update_endgame_sequence, render_endgame_sequence

logger = get_logger(__name__)

# ============================================================================
# MISSION CONFIGURATION
# ============================================================================

# All 41 territories enabled for this mission (Mission 6's 33 + 8 new)
MISSION_7_TERRITORIES = [
    # Player 0 (Human / Blue): 23 starting territories
    "Aelatania", "Courtieux", "Londia", "Zjoal Islands",
    "March of Auverne", "Affrancian Uplands", "Carnae", "Vense",
    "Damlére", "Role", "Mose", "Vice", "Oucine", "Riar",
    "Odatria", "Conda", "Ahara", "Espoia", "Nefrid", "Ajuna",
    "Lunedale", "Free Cities", "Cinto",
    # Player 1 (Central Alliance / Red): 18 starting territories
    "Nordica", "Leuse Valley", "Velognia", "Valeonia", "Sordia",
    "Duchy of Daurels", "Northern Heilonia", "Révia", "Venexia",
    "Daomea", "Ahtep", "Amennia", "Liadnon", "Sstep",
    "Anodia", "Southern Quil'en", "Northern Quil'en", "Amorian Shores",
]

# Faction territory ownership mapping
FACTION_TERRITORIES = {
    0: ["Aelatania", "Courtieux", "Londia", "Zjoal Islands",
        "March of Auverne", "Affrancian Uplands", "Carnae", "Vense",
        "Damlére", "Role", "Mose", "Vice", "Oucine", "Riar",
        "Odatria", "Conda", "Ahara", "Espoia", "Nefrid", "Ajuna",
        "Lunedale", "Free Cities", "Cinto"],
    1: ["Nordica", "Leuse Valley", "Velognia", "Valeonia", "Sordia",
        "Duchy of Daurels", "Northern Heilonia", "Révia", "Venexia",
        "Daomea", "Ahtep", "Amennia", "Liadnon", "Sstep",
        "Anodia", "Southern Quil'en", "Northern Quil'en", "Amorian Shores"],
}

# Player colors: Blue (human), Red (Central Alliance)
PLAYER_COLORS = [
    (100, 150, 255),   # Player 0: Blue (human)
    (255, 100, 100),   # Player 1: Red (Central Alliance)
]

# Faction display names
FACTION_NAMES = {
    0: None,                    # Human player (use profile name)
    1: "Central Alliance",
}

# Starting gold per faction
STARTING_GOLD = {
    0: 1500,
    1: 25000,
}

# Core AI territories that must maintain minimum garrison (enforced by custom AI)
CORE_TERRITORIES = {"Ahtep", "Sordia", "Leuse Valley", "Nordica", "Valeonia", "Velognia"}
CORE_MIN_GARRISON = 13

# Frontline + frontline-adjacent AI territories (get 7 starting units)
FRONTLINE_TERRITORIES = {"Duchy of Daurels", "Northern Heilonia", "Daomea",
                         "Amennia", "Révia", "Venexia"}

# Mission speaker name for transmissions
MISSION_7_SPEAKER = "King Aidam Narn"

# Intro sequence: zoom to Courtieux, pan to Lunedale and back, 3 transmissions
# Format: (action, target/duration, text)
# Estimated durations: ~2.5 words/sec + 1s buffer
INTRO_SEQUENCE = [
    # Step 0: Zoom to Courtieux
    ("zoom_to", "Courtieux", ""),
    # Step 1: Opening transmission (M7T1: 7.16s + 0.5s buffer)
    ("wait", 7.7, "The Naragonese attack against Avantgardia has failed. "
                   "We must strike hard and fast while they are in disarray."),
    # Step 2: Pan camera to Lunedale over 1s
    ("pan_to", "Lunedale", ""),
    # Step 3: Transmission about eastern allies (M7T2: 6.37s + 0.5s buffer)
    ("wait", 6.9, "Allies of Northern Powers are also prepared to strike from the east. "
                   "Let us join them in an attack!"),
    # Step 4: Pan camera back to Courtieux over 1s
    ("pan_to", "Courtieux", ""),
    # Step 5: Final rallying cry (M7T3: 2.85s + 0.5s buffer)
    ("wait", 3.4, "The fall of Naragonthid and their allies is upon us!"),
    # Step 6: Start gameplay
    ("start_game", 0, ""),
]

# Map intro step indices to voice keys for transmission sound playback
INTRO_STEP_TO_VOICE = {1: "M7T1", 3: "M7T2", 5: "M7T3"}

# ============================================================================
# UNIT CREATION HELPERS
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


def _make_random_units(count, level=0):
    """Create a random combination of units from basic combat types."""
    global _global_unit_id
    unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
    units = []
    for _ in range(count):
        unit_type = random.choice(unit_types)
        units.append(_make_unit(unit_type, _global_unit_id, level))
        _global_unit_id += 1
    return units


# ============================================================================
# TERRITORY SETUP — buildings and starting units per territory
# ============================================================================

TERRITORY_SETUP = {
    # ========== HUMAN (Player 0, Blue) — 23 territories ==========
    "Courtieux": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Training Grounds"},
        "units": _make_random_units(13, level=5),
    },
    "Lunedale": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Farm"},
        "units": _make_random_units(random.randint(6, 7)),
    },
    "Affrancian Uplands": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Farm"},
        "units": _make_random_units(random.randint(6, 7)),
    },
    "Londia": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_random_units(9, level=5),
    },
    "Aelatania": {
        "owner": 0,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_random_units(9, level=5),
    },
    "Carnae": {
        "owner": 0,
        "buildings": {0: "Mine", 1: "Barracks"},
        "units": _make_random_units(random.randint(4, 6)),
    },
    "March of Auverne": {
        "owner": 0,
        "buildings": {0: "Training Grounds"},
        "units": _make_random_units(random.randint(6, 7)),
    },
    "Vense": {
        "owner": 0,
        "buildings": {0: "Mine"},
        "units": _make_random_units(random.randint(4, 6)),
    },
    "Damlére": {
        "owner": 0,
        "buildings": {0: "Mine"},
        "units": _make_random_units(8),
    },
    "Role": {
        "owner": 0,
        "buildings": {0: "Farm"},
        "units": _make_random_units(1),
    },
    "Vice": {
        "owner": 0,
        "buildings": {0: "Farm"},
        "units": _make_random_units(1),
    },
    "Mose": {
        "owner": 0,
        "buildings": {0: "Farm"},
        "units": _make_random_units(1),
    },
    "Ajuna": {
        "owner": 0,
        "buildings": {0: "Farm"},
        "units": _make_random_units(1),
    },
    "Odatria": {
        "owner": 0,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_random_units(1),
    },
    "Oucine": {
        "owner": 0,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_random_units(1),
    },
    "Conda": {
        "owner": 0,
        "buildings": {0: "Training Grounds", 1: "Farm"},
        "units": _make_random_units(1),
    },
    "Cinto": {
        "owner": 0,
        "buildings": {0: "Mine"},
        "units": _make_random_units(1),
    },
    "Espoia": {
        "owner": 0,
        "buildings": {0: "Farm"},
        "units": _make_random_units(1),
    },
    "Free Cities": {
        "owner": 0,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_random_units(random.randint(6, 7)),
    },
    "Zjoal Islands": {
        "owner": 0,
        "buildings": {},
        "units": _make_random_units(1),
    },
    "Riar": {
        "owner": 0,
        "buildings": {},
        "units": _make_random_units(1),
    },
    "Ahara": {
        "owner": 0,
        "buildings": {},
        "units": _make_random_units(1),
    },
    "Nefrid": {
        "owner": 0,
        "buildings": {},
        "units": _make_random_units(1),
    },

    # ========== CENTRAL POWERS (Player 1, Red) — 18 territories ==========
    # Frontline territories (7 units each)
    "Duchy of Daurels": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_random_units(7),
    },
    "Northern Heilonia": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Barracks", 2: "Training Grounds"},
        "units": _make_random_units(7),
    },
    "Daomea": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Training Grounds"},
        "units": _make_random_units(7),
    },
    # Frontline-adjacent territories (7 units each)
    "Amennia": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_random_units(7),
    },
    "Révia": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Mine"},
        "units": _make_random_units(7),
    },
    "Venexia": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Mine"},
        "units": _make_random_units(7),
    },
    # Core castle territories (15 units each, min 13 garrison enforced)
    "Leuse Valley": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Farm", 2: "Barracks"},
        "units": _make_random_units(15),
    },
    "Valeonia": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_random_units(15),
    },
    "Sordia": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Mine"},
        "units": _make_random_units(15),
    },
    "Ahtep": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Farm", 2: "Barracks"},
        "units": _make_random_units(15),
    },
    # Core non-castle territories (15 units each, min 13 garrison enforced)
    "Nordica": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_random_units(15),
    },
    "Velognia": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Mine"},
        "units": _make_random_units(15),
    },
    # Interior territories (5-7 random units each)
    "Liadnon": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Mine"},
        "units": _make_random_units(random.randint(5, 7)),
    },
    "Sstep": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Barracks"},
        "units": _make_random_units(random.randint(5, 7)),
    },
    "Anodia": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_random_units(random.randint(5, 7)),
    },
    "Southern Quil'en": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Mine"},
        "units": _make_random_units(random.randint(5, 7)),
    },
    "Northern Quil'en": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Mine"},
        "units": _make_random_units(random.randint(5, 7)),
    },
    "Amorian Shores": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Mine"},
        "units": _make_random_units(random.randint(5, 7)),
    },
}


# ============================================================================
# MISSION 7 CLASS
# ============================================================================

class Mission7:
    """
    Campaign Mission 7: The Fall

    2 factions: Human (Blue) vs Central Alliance (Red AI, Hard).
    Human has 23 territories, Central Alliance has 18 territories.
    Custom AI with garrison enforcement on 6 core territories.
    Victory: Conquer all Central Alliance territories.
    Defeat: Lose all territories, OR Courtieux falls (King Aidam Narn dies),
            OR Lunedale falls (General Neil Hévilneu dies).
    """

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_7'
        self.active = True

        # Bonus achievement: "Spending Spree" — disqualified if player gold ever exceeds 3500
        self._spending_spree_disqualified = False

        # AI turn timing (0.5s fast turns, same as missions 5/6)
        self.ai_turn_timer = 0.0
        self._ai_executed_this_turn = False  # Guard: prevent duplicate AI execution per turn

        # AI turn counter
        self.faction_turn_count = {1: 0}

        # Intro sequence state
        self.intro_active = True
        self.intro_step_index = 0
        self.intro_timer = 0.0
        self.intro_waiting_for_zoom = False
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

        # Quest log — 3 objectives (all visible from start)
        self.quest_log = [
            {'text': 'Conquer all territories of the Central Alliance', 'completed': False},
            {'text': 'King Aidam Narn must survive in Courtieux', 'completed': False},
            {'text': 'General Neil Hévilneu must survive in Lunedale', 'completed': False},
        ]

        # Victory/defeat sequence state (same attrs as missions 4/5/6, needed by campaign_utils)
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

        # Track which enemy hero capture transmissions have been shown (prevent duplicates)
        self._announced_captures = set()

        # Defeat text, speaker, duration, and voice key (set dynamically based on defeat cause)
        self._defeat_text = "We have lost everything. All is lost."
        self._defeat_speaker = MISSION_7_SPEAKER
        self._defeat_duration = 3.0
        self._defeat_voice_key = "M7T9"

        # Allow turn timer to auto-end player turns
        self.allow_timer_expiry = True

        # Store original flag icons for restoration on cleanup
        self.original_flag_icons = None

        # Set up territory filtering
        map_data.set_enabled_territories(MISSION_7_TERRITORIES)

        # Set up initial game state
        self._setup_initial_state()

        # Pre-assign starting heroes
        self._assign_starting_heroes()

        # Start intro sequence
        self._start_intro_sequence()

        logger.info("Mission 7 'The Fall' initialized: 41 territories, 2 factions (23 human, 18 AI)")

    def _setup_initial_state(self):
        """Configure the game state for Mission 7 scenario."""
        gs = self.game_state

        # Set player colors (2 players)
        for i, color in enumerate(PLAYER_COLORS):
            if i < len(gs.player_colors):
                gs.player_colors[i] = color

        # Remap flag icons: Human (player 0) = Blue flags (slot 1), AI (player 1) = Red flags (slot 0)
        # army_flag_icons is a dict keyed by player_index (0, 1, ... , -1 for neutral)
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and 0 in game.army_flag_icons and 1 in game.army_flag_icons:
            self.original_flag_icons = {k: v for k, v in game.army_flag_icons.items()}
            # Swap flag icons: player 0 gets Blue (originally slot 1), player 1 gets Red (originally slot 0)
            original_0 = self.original_flag_icons[0]
            original_1 = self.original_flag_icons[1]
            game.army_flag_icons[0] = original_1  # Human (player 0) = Blue flags
            game.army_flag_icons[1] = original_0  # Central Alliance (player 1) = Red flags

        # Set faction names
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name

        # Set starting gold per faction
        for player_id, gold in STARTING_GOLD.items():
            if player_id < gs.num_players:
                gs.player_gold[player_id] = gold

        # Set up teams: opposing teams
        gs.player_teams[0] = 0  # Human: team 0
        gs.player_teams[1] = 1  # Central Alliance: team 1

        # Set AI difficulty to Hard
        gs.player_ai_difficulty[1] = 2

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

        # Clear ownership, garrisons, and buildings for all non-mission territories
        mission_set = set(MISSION_7_TERRITORIES)
        for territory in list(gs.territory_owners.keys()):
            if territory not in mission_set:
                gs.territory_owners[territory] = -1
                gs.territory_garrisons[territory] = {}
                gs.buildings[territory] = {}

        # Set castle upgrades for 7 territories (3 human + 4 AI)
        # Human castles: Courtieux, Lunedale, Affrancian Uplands (plot 0 = Keep)
        gs.castle_upgrades['Courtieux'] = {0: True}
        gs.castle_upgrades['Lunedale'] = {0: True}
        gs.castle_upgrades['Affrancian Uplands'] = {0: True}
        # AI castles: Leuse Valley, Valeonia, Sordia, Ahtep (plot 0 = Keep)
        gs.castle_upgrades['Leuse Valley'] = {0: True}
        gs.castle_upgrades['Valeonia'] = {0: True}
        gs.castle_upgrades['Sordia'] = {0: True}
        gs.castle_upgrades['Ahtep'] = {0: True}

        # Invalidate bonus cache after bulk territory setup
        gs.invalidate_territorial_bonus_cache()

        # Set starting territories for reference
        gs.player_starting_territories[0] = "Courtieux"
        gs.player_starting_territories[1] = "Nordica"

        # --- Pre-researched technologies ---
        # Human: first row (row 0) in all 3 columns
        self._pre_research_techs(0, max_row=0)
        # Central Alliance: first 5 rows (rows 0-4) in all 3 columns
        self._pre_research_techs(1, max_row=4)

        logger.info("Mission 7 initial state configured: 41 territories, teams [0] vs [1]")

    def _pre_research_techs(self, player_id, max_row):
        """Pre-research all techs in rows 0 through max_row for all 3 columns.
        Mirrors finish_research() logic for applying effects."""
        gs = self.game_state

        # For rows 3+: player needs a Castle. AI has castles at Leuse Valley, etc.
        # Human has castles at Courtieux, Lunedale, Affrancian Uplands.
        # castle_upgrades already set in _setup_initial_state.

        # Build list of tech IDs to research
        tech_ids = []
        for col in range(3):
            for row in range(max_row + 1):
                tech_ids.append(f"tech_{col}_{row}")

        # Add all techs to researched set, remove from available
        for tech_id in tech_ids:
            gs.player_tech_researched[player_id].add(tech_id)
            gs.player_tech_available[player_id].discard(tech_id)

        # Apply tech effects directly (mirror finish_research logic in game_state/buildings.py)
        # Row 0: tech_0_0 (Efficient Farming I), tech_1_0 (Improved Training), tech_2_0 (Master Planner I)
        if max_row >= 0:
            # tech_0_0: Efficient Farming I — +20% Farm income (checked inline in economy, no attr)
            gs.player_training_cost_discount[player_id] = 20       # tech_1_0: Swordsman/Pikeman -20%
            gs.player_planning_time_limit[player_id] += 30         # tech_2_0: +30s planning time

        # Row 1: tech_0_1 (Efficient Mining I), tech_1_1 (Makeshift Barracks), tech_2_1 (Improved Command I)
        if max_row >= 1:
            # tech_0_1: Efficient Mining I — +20% Mine income (checked inline in economy, no attr)
            gs.player_barracks_cost_discount[player_id] = 25       # tech_1_1: Barracks -25%
            gs.player_barracks_full_refund[player_id] = True       # tech_1_1: 100% demolish refund
            gs.player_command_limit[player_id] += 35               # tech_2_1: +35 command limit

        # Row 2: tech_0_2 (Leave Nothing Behind), tech_1_2 (Animal Handling), tech_2_2 (Royal Decree)
        if max_row >= 2:
            # tech_0_2: Leave Nothing Behind — 50% recovery on Farm/Mine destruction (checked inline)
            gs.player_cavalry_cost_discount[player_id] = 25        # tech_1_2: Cavalry -25%
            gs.player_royal_decree_discount[player_id] = 15        # tech_2_2: Hero/Keep -15%

        # Row 3: tech_0_3 (Supply and Demand), tech_1_3 (Battlement Archery), tech_2_3 (Master Planner II)
        if max_row >= 3:
            # tech_0_3: Supply and Demand — Squares multiply by 2.5x (checked inline, requires castle)
            gs.player_archer_keep_strength_bonus[player_id] = 50   # tech_1_3: Archers +50% near Keep/Castle
            gs.player_planning_time_limit[player_id] += 30         # tech_2_3: +30s (Master Planner II)

        # Row 4: tech_0_4 (Efficient Farming II), tech_1_4 (Raze the Countryside), tech_2_4 (Heroic Fortitude)
        if max_row >= 4:
            # tech_0_4: Efficient Farming II — +20% Farm income again (checked inline)
            # tech_1_4: Raze the Countryside — destroy enemy Farm/Mine on conquest (checked inline)
            gs.player_hero_limit[player_id] = 4                    # tech_2_4: hero limit to 4

        # Unlock next tier techs (row after max_row) if available
        next_row = max_row + 1
        if next_row < 7:
            for col in range(3):
                gs.player_tech_available[player_id].add(f"tech_{col}_{next_row}")

    def _assign_starting_heroes(self):
        """Pre-assign heroes to both factions."""
        gs = self.game_state

        # --- Human heroes (player 0) ---
        if 0 not in gs.heroes:
            gs.heroes[0] = {}
        if 0 not in gs.hero_ownership:
            gs.hero_ownership[0] = set()

        # Aidam Narn at Courtieux Keep (plot 0) — defeat condition if killed
        gs.heroes[0]["Aidam Narn"] = {
            'keep_territory': 'Courtieux',
            'keep_plot': 0
        }
        gs.hero_ownership[0].add("Aidam Narn")

        # Neil Hévilneu at Lunedale Keep (plot 0) — defeat condition if killed
        gs.heroes[0]["Neil Hévilneu"] = {
            'keep_territory': 'Lunedale',
            'keep_plot': 0
        }
        gs.hero_ownership[0].add("Neil Hévilneu")

        # Erec Silvyr at Londia Keep (plot 0) — NOT a defeat condition
        gs.heroes[0]["Erec Silvyr"] = {
            'keep_territory': 'Londia',
            'keep_plot': 0
        }
        gs.hero_ownership[0].add("Erec Silvyr")

        # --- Central Alliance heroes (player 1) ---
        if 1 not in gs.heroes:
            gs.heroes[1] = {}
        if 1 not in gs.hero_ownership:
            gs.hero_ownership[1] = set()

        # Vearen Asford at Duchy of Daurels Keep (plot 0)
        gs.heroes[1]["Vearen Asford"] = {
            'keep_territory': 'Duchy of Daurels',
            'keep_plot': 0
        }
        gs.hero_ownership[1].add("Vearen Asford")

        # Darius Brennhen at Nordica Keep (plot 0)
        gs.heroes[1]["Darius Brennhen"] = {
            'keep_territory': 'Nordica',
            'keep_plot': 0
        }
        gs.hero_ownership[1].add("Darius Brennhen")

        logger.info("Assigned heroes: Human (Aidam Narn, Neil Hévilneu, Erec Silvyr), "
                     "Central Alliance (Vearen Asford, Darius Brennhen)")

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
            # Smooth pan to target territory over 1 second (no zoom change)
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
            self.camera_animation = CameraPanAnimation(
                camera_handler=camera,
                target_center_world=target_center,
                duration=1.0,
                screen_width=sw,
                map_area_height=map_area_height,
            )
            self.intro_waiting_for_zoom = True
            self.intro_timer = 0.0

        elif action == 'wait':
            # Show transmission text and wait for duration
            self.intro_timer = 0.0
            if text:
                self._show_transmission(text, speaker=MISSION_7_SPEAKER)
                self.transmission_duration = param
                # Play voice line for this intro step (if available)
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
        stop_transmission_sound()
        # Reset planning timer so it starts fresh after intro
        self.game_state.planning_phase_start_time = time.time()
        logger.info("Intro sequence complete — gameplay begins")

    # ========================================================================
    # TRANSMISSION SYSTEM
    # ========================================================================

    def _show_transmission(self, text, speaker=MISSION_7_SPEAKER):
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
        """Queue a transmission to show during gameplay."""
        self.transmission_queue.append((text, duration, voice_key))

    def _start_pending_transmission(self):
        """Start showing the next queued transmission."""
        if self.transmission_queue:
            text, duration, voice_key = self.transmission_queue.pop(0)
            self._show_transmission(text)
            self.transmission_duration = duration
            self.transmission_timer = 0.0
            if voice_key:
                from global_sound import play_transmission_sound
                play_transmission_sound(voice_key)

    def _is_gameplay_idle(self):
        """Check if gameplay is idle (no battles, popups, turn announcements, or animations)."""
        gs = self.game_state
        battle_popup_open = getattr(self.main_game, 'battle_popup_visible', False)
        phase_ok = gs.turn_phase == 'planning' or gs.phase == 'ended'
        return (phase_ok
                and not gs.pending_battles
                and not battle_popup_open
                and not gs.turn_announcement_active)

    def skip_transmission(self):
        """Skip the currently visible transmission (ESC key).
        Returns True if a transmission was skipped, False otherwise."""
        if not self.active or not self.transmission_overlay:
            return False
        # Don't skip during victory/defeat cinematic animation
        if self.victory_sequence_active or self.defeat_sequence_active:
            return False

        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        self.transmission_overlay = None

        if self.intro_active:
            # During intro: cancel timers, cancel camera animation, advance
            self._intro_pause_timer = 0
            self.intro_timer = 0.0
            self.intro_waiting_for_zoom = False
            if self.camera_animation:
                self.camera_animation = None
            self.intro_step_index += 1
            self._execute_intro_step()
        else:
            # During gameplay: reset timer, next queued transmission starts on next idle frame
            self.transmission_timer = 0.0
            self.transmission_duration = 0.0
        return True

    # ========================================================================
    # SAVE / RESTORE STATE (for campaign save system)
    # ========================================================================

    def get_save_state(self):
        """Serialize mission-specific state for save game."""
        return {
            'active': self.active,
            'quest_log': self.quest_log,
            'faction_turn_count': {str(k): v for k, v in self.faction_turn_count.items()},
            '_spending_spree_disqualified': self._spending_spree_disqualified,
            '_announced_captures': sorted(list(self._announced_captures)),
            'intro_active': self.intro_active,
            'intro_step_index': self.intro_step_index,
            'game_paused': self.game_paused,
            'timer_visible': self.timer_visible,
            'allow_timer_expiry': self.allow_timer_expiry,
            'game_frozen': self.game_frozen,
            '_defeat_text': self._defeat_text,
            '_defeat_speaker': self._defeat_speaker,
            '_defeat_duration': self._defeat_duration,
            '_defeat_voice_key': self._defeat_voice_key,
        }

    def restore_save_state(self, data):
        """Restore mission-specific state from save game data."""
        self.active = data.get('active', True)
        self.quest_log = data.get('quest_log', self.quest_log)
        self.faction_turn_count = {int(k): v for k, v in data.get('faction_turn_count', {}).items()} or self.faction_turn_count
        self._spending_spree_disqualified = data.get('_spending_spree_disqualified', False)
        self._announced_captures = set(data.get('_announced_captures', []))
        # Skip intro on load — player is resuming mid-game
        # Clear all intro/transmission state so constructor's _start_intro_sequence() doesn't replay
        self.intro_active = False
        self.intro_step_index = 0
        self.intro_waiting_for_zoom = False
        self.camera_animation = None
        self._intro_pause_timer = 0.0
        self.transmission_overlay = None
        self.transmission_queue = []
        self.transmission_duration = 0.0
        self.game_paused = False
        self.timer_visible = data.get('timer_visible', True)
        self.allow_timer_expiry = data.get('allow_timer_expiry', True)
        self.game_frozen = data.get('game_frozen', False)
        self._defeat_text = data.get('_defeat_text', self._defeat_text)
        self._defeat_speaker = data.get('_defeat_speaker', self._defeat_speaker)
        self._defeat_duration = data.get('_defeat_duration', self._defeat_duration)
        self._defeat_voice_key = data.get('_defeat_voice_key', self._defeat_voice_key)

    # ========================================================================
    # UPDATE (called every frame)
    # ========================================================================

    def update(self, delta_time):
        """Called every frame to update mission state."""
        if not self.active:
            return None
        # Cap delta_time to prevent animation jumps on large frame times
        delta_time = min(delta_time, 0.05)

        # Update camera animation (zoom/pan)
        if self.camera_animation:
            self.camera_animation.update(delta_time)
            if not self.camera_animation.active:
                if self.intro_waiting_for_zoom:
                    self.intro_waiting_for_zoom = False
                    self.intro_step_index += 1
                    self._execute_intro_step()
                self.camera_animation = None

        # Process inter-transmission pause
        if self._intro_pause_timer > 0:
            self._intro_pause_timer -= delta_time
            if self._intro_pause_timer <= 0:
                self._intro_pause_timer = 0
                self.intro_step_index += 1
                self._execute_intro_step()
            return None

        # Update intro timing
        if self.intro_active and not self.intro_waiting_for_zoom:
            action = INTRO_SEQUENCE[self.intro_step_index][0] if self.intro_step_index < len(INTRO_SEQUENCE) else None
            if action == 'wait':
                self.intro_timer += delta_time
                if self.intro_timer >= self.transmission_duration:
                    # Check if next step has text — if so, insert 1s pause
                    next_idx = self.intro_step_index + 1
                    if next_idx < len(INTRO_SEQUENCE) and INTRO_SEQUENCE[next_idx][2]:
                        from global_sound import stop_transmission_sound
                        self.transmission_overlay = None
                        stop_transmission_sound()
                        self._intro_pause_timer = 1.0
                    else:
                        self.intro_step_index += 1
                        self._execute_intro_step()

        # Bonus "Spending Spree": disqualify if player gold ever exceeds 3500
        if not self.intro_active and not self._spending_spree_disqualified:
            if self.game_state.player_gold[0] > 3500:
                self._spending_spree_disqualified = True
                logger.info(f"Spending Spree disqualified: player gold {self.game_state.player_gold[0]} exceeded 3500")

        # Instant AI turns: skip turn announcement animation for AI players
        if not self.intro_active:
            gs = self.game_state
            if gs.current_player != 0 and gs.turn_announcement_active:
                game = self.main_game
                if hasattr(game, 'turn_announcement_effect') and game.turn_announcement_effect:
                    game.turn_announcement_effect.cleanup()
                    game.turn_announcement_effect = None
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

                # Show victory transmission with voice (M7T6: 4.62s + 0.5s buffer)
                text = "The war machine of the Central Alliance has been crushed! Victory is ours!"
                self._show_transmission(text, speaker=MISSION_7_SPEAKER)
                self.transmission_duration = 5.1
                self.transmission_timer = 0.0
                # Play victory voice line
                from global_sound import play_transmission_sound
                play_transmission_sound("M7T6")

        # Deferred defeat: same pattern
        if self._defeat_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.transmission_queue:
                self._defeat_waiting = False
                self._pending_defeat = True
                self.game_paused = True

                # Show defeat transmission with appropriate speaker and voice
                self._show_transmission(self._defeat_text, speaker=self._defeat_speaker)
                self.transmission_duration = self._defeat_duration
                self.transmission_timer = 0.0
                # Play defeat voice line
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

    # ========================================================================
    # AI CONTROL — custom AI with garrison enforcement on core territories
    # ========================================================================

    @property
    def block_ai(self):
        """Block normal AI for Central Alliance — Mission7 controls their behavior."""
        if self.intro_active:
            return True
        current_player = self.game_state.current_player
        if current_player == 0:
            return False  # Human player
        return True  # Block normal AI, use custom AI with garrison enforcement

    @property
    def block_ai_thinking(self):
        return False

    def get_ai_thinking_text(self):
        """Override AI thinking indicator."""
        return ("Central Alliance thinking...", "")

    def execute_ai_turn_override(self):
        """Called instead of normal AI execution. Dispatches to custom faction AI
        that respects core territory garrison requirements.

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

        # Force-complete turn announcement for AI players immediately
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
            self._ai_executed_this_turn = False  # Reset guard for next turn
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
        """Execute AI for Central Alliance: build, train, reinforce, then attack.

        All movement respects CORE_MIN_GARRISON — core territories never go
        below 13 units. Full aggression otherwise (Hard AI behavior).
        """
        gs = self.game_state

        # Increment turn counter
        self.faction_turn_count[player_id] = self.faction_turn_count.get(player_id, 0) + 1

        # Find territories owned by this faction
        my_territories = [t for t in MISSION_7_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return  # Faction eliminated

        # Phase 1: Build structures on empty plots
        self._ai_build(player_id, my_territories)

        # Phase 2: Train units at all barracks
        self._ai_train(player_id, my_territories)

        # Phase 3: Reinforce frontline from rear (respecting core garrison requirements)
        self._ai_reinforce(player_id, my_territories)

        # Phase 4: Attack enemy territories with full aggression
        self._ai_attack(player_id, my_territories)

    def _get_available_units(self, territory, player_id):
        """Get units available to move (above garrison minimum for core territories).

        Returns list of ready units that can be moved without violating
        the territory's core garrison requirement.
        """
        gs = self.game_state
        garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
        units = garrison.get('units', [])
        ready_units = [u for u in units if u.get('status') == 'ready']

        # Core territories must keep at least CORE_MIN_GARRISON armies
        if territory in CORE_TERRITORIES:
            total_units = len(units)
            spare = total_units - CORE_MIN_GARRISON
            if spare <= 0:
                return []
            return ready_units[:spare]

        return ready_units

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

    def _ai_reinforce(self, player_id, my_territories):
        """Move units from rear territories toward frontline.

        Respects CORE_MIN_GARRISON on core territories. Unlimited budget otherwise.
        """
        gs = self.game_state
        units_moved = 0
        max_units = 999  # No ramp limit on reinforcements

        # Identify enemy territories (not owned by self)
        enemy_territories = set()
        for t in MISSION_7_TERRITORIES:
            t_owner = gs.territory_owners.get(t, -1)
            if t_owner >= 0 and t_owner != player_id:
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

        # Identify rear territories (not on frontline)
        rear_territories = [t for t in my_territories if t not in frontline]

        for rear_t in rear_territories:
            if units_moved >= max_units:
                break

            available = self._get_available_units(rear_t, player_id)
            if not available:
                continue

            # Find adjacent OWN territory closer to frontline
            neighbors = map_data.get_neighbors(rear_t)
            best_target = None
            for n in neighbors:
                # Only move to own territories
                if gs.territory_owners.get(n) != player_id:
                    continue
                if n in frontline:
                    best_target = n
                    break
                if n not in rear_territories:
                    best_target = n

            if best_target:
                # Check army limit at target
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

    def _ai_attack(self, player_id, my_territories):
        """Attack enemy territories with full aggression (Hard AI).

        Respects CORE_MIN_GARRISON for core source territories.
        Each target can be attacked from up to 2 sources.
        Every source with available units will attack if a valid target exists.
        """
        gs = self.game_state

        # Find enemy territories adjacent to our territories
        enemy_territories = set()
        for t in MISSION_7_TERRITORIES:
            t_owner = gs.territory_owners.get(t, -1)
            if t_owner >= 0 and t_owner != player_id:
                enemy_territories.add(t)

        if not enemy_territories:
            return

        # Build attack candidates: (source, target, available_count, score)
        attack_candidates = []
        for my_t in my_territories:
            available = self._get_available_units(my_t, player_id)
            if not available:
                continue

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

        # Execute attacks: every source attacks once, max 2 sources per target
        used_sources = set()
        target_source_count = {}  # How many sources already attacking each target

        for my_t, target, _, score in attack_candidates:
            if my_t in used_sources:
                continue  # Each source attacks only once
            if target_source_count.get(target, 0) >= 2:
                continue  # Max 2 sources per target territory

            # Re-fetch available units (may have changed from reinforcement orders)
            available = self._get_available_units(my_t, player_id)
            if not available:
                continue

            # Send all available units (full aggression, Hard AI)
            unit_ids = [u['id'] for u in available]
            gs.add_movement_order_for_units(my_t, target, unit_ids, player=player_id)
            used_sources.add(my_t)
            target_source_count[target] = target_source_count.get(target, 0) + 1
            logger.debug(f"AI {player_id} turn {self.faction_turn_count[player_id]}: "
                       f"attacking {target} from {my_t} with {len(available)} units")

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

        # Block hero training for all players — heroes are pre-assigned
        if action_type == 'train_hero':
            return False

        return True

    def should_hide_hero_training(self):
        """Hide hero training UI — heroes are pre-assigned, no new training."""
        return True

    def should_button_be_locked(self, button_id):
        return False

    def is_button_locked(self, button_id):
        return self.should_button_be_locked(button_id)

    def should_highlight_button(self, button_id):
        return False

    def is_timer_visible(self):
        return self.timer_visible

    # ========================================================================
    # TERRITORY INTERACTION
    # ========================================================================

    def is_territory_interactive(self, territory_name):
        """All 41 mission territories are viewable/hoverable."""
        if not self.active:
            return True
        return territory_name in MISSION_7_TERRITORIES

    def is_attack_target_blocked(self, territory_name):
        """No attack restrictions in Mission 7 — all territories are valid targets."""
        return False

    def get_adjacency_override(self, territory):
        """No special adjacency restrictions in Mission 7."""
        return None

    def get_highlight_territory(self):
        """No step-based territory highlighting in Mission 7."""
        return None

    def should_highlight_plot(self, territory, plot_index):
        return False

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
            self._check_enemy_hero_captured(territory, new_owner)
            self._on_territory_conquered(territory, new_owner)

        elif event_type == 'hero_killed':
            # Handle hero death from Regicide (or other non-conquest causes)
            hero_name = kwargs.get('hero_name')
            killer = kwargs.get('killer')
            if killer == 0 and hero_name and hero_name not in self._announced_captures:
                self._announced_captures.add(hero_name)
                # Show capture transmission for known enemy heroes
                if hero_name == 'Vearen Asford':
                    self._queue_transmission(
                        "Naragonese general Vearen Asford has been captured!",
                        3.6, "M7T4"
                    )
                elif hero_name == 'Darius Brennhen':
                    self._queue_transmission(
                        "Lord of Noxefort, Darius Brennhen, has been captured!",
                        3.7, "M7T5"
                    )

    def _check_enemy_hero_captured(self, territory, new_owner):
        """Show transmission when an enemy hero is captured (their keep territory conquered).

        Called before _on_territory_conquered so the transmission is queued
        before any victory/defeat sequence starts.
        Hero death happens in kill_heroes_in_keep() before this callback,
        so the hero is already removed from gs.heroes[1] when we check.
        """
        if new_owner != 0:
            return  # Only show for human conquests

        # Check if Vearen Asford's keep was here (hero already killed by game engine)
        if territory == 'Duchy of Daurels' and 'Vearen Asford' not in self._announced_captures:
            gs = self.game_state
            if "Vearen Asford" not in gs.heroes.get(1, {}):
                self._announced_captures.add('Vearen Asford')
                self._queue_transmission(
                    "Naragonese general Vearen Asford has been captured!",
                    3.6, "M7T4"
                )

        # Check if Darius Brennhen's keep was here
        if territory == 'Nordica' and 'Darius Brennhen' not in self._announced_captures:
            gs = self.game_state
            if "Darius Brennhen" not in gs.heroes.get(1, {}):
                self._announced_captures.add('Darius Brennhen')
                self._queue_transmission(
                    "Lord of Noxefort, Darius Brennhen, has been captured!",
                    3.7, "M7T5"
                )

    def _on_territory_conquered(self, territory, new_owner):
        """Handle territory conquest — check victory/defeat conditions.

        Victory: Central Alliance (player 1) owns 0 territories on the map.
        Defeat: Human loses Courtieux (King Aidam Narn dies),
                OR Human loses Lunedale (General Neil Hévilneu dies),
                OR Human owns 0 territories.
        """
        gs = self.game_state

        # --- DEFEAT CHECK: Courtieux captured — King Aidam Narn dies ---
        if territory == 'Courtieux' and new_owner != 0:
            logger.info("Courtieux captured — King Aidam Narn has fallen! Defeat!")
            self._defeat_text = "King of Azincourne is dead! The alliance is lost!"
            self._defeat_speaker = "General Neil Hévilneu"
            self._defeat_duration = 4.4
            self._defeat_voice_key = "M7T7"
            self._start_defeat()
            return

        # --- DEFEAT CHECK: Lunedale captured — General Neil Hévilneu dies ---
        if territory == 'Lunedale' and new_owner != 0:
            logger.info("Lunedale captured — General Neil Hévilneu has fallen! Defeat!")
            self._defeat_text = "General Hévilneu is dead! Without his tactical command, our effort is lost!"
            self._defeat_speaker = MISSION_7_SPEAKER
            self._defeat_duration = 5.8
            self._defeat_voice_key = "M7T8"
            self._start_defeat()
            return

        # --- DEFEAT CHECK: Human owns 0 territories ---
        human_territories = [t for t in MISSION_7_TERRITORIES
                            if gs.territory_owners.get(t) == 0]
        if not human_territories:
            logger.info("Human lost all territories — defeat!")
            self._defeat_text = "We have lost everything. All is lost."
            self._defeat_speaker = MISSION_7_SPEAKER
            self._defeat_duration = 3.0
            self._defeat_voice_key = "M7T9"
            self._start_defeat()
            return

        # --- VICTORY CHECK: Central Alliance owns 0 territories ---
        ai_territories = [t for t in MISSION_7_TERRITORIES
                         if gs.territory_owners.get(t) == 1]
        if not ai_territories:
            logger.info("Central Alliance eliminated — VICTORY!")
            self.quest_log[0]['completed'] = True
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
        """Update victory animation. Returns 'exit' when done."""
        return update_endgame_sequence(self, delta_time, 'victory')

    def _render_victory_sequence(self, screen):
        """Render the victory sequence overlay."""
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
        """Update defeat animation. Returns 'exit' when done."""
        return update_endgame_sequence(self, delta_time, 'defeat')

    def _render_defeat_sequence(self, screen):
        """Render the defeat sequence overlay."""
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
        """Return all 3 quests (all visible from start)."""
        return self.quest_log

    def get_bonus_conditions(self):
        """Return bonus condition flags for achievement system."""
        return {
            'campaign_mission_7_bonus': not self._spending_spree_disqualified,
        }

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def _cleanup(self):
        """Clean up mission state when exiting."""
        from global_sound import stop_transmission_sound
        logger.info("Cleaning up Mission 7")
        stop_transmission_sound()
        map_data.clear_enabled_territories()

        # Restore original flag icons
        if self.original_flag_icons and hasattr(self.main_game, 'army_flag_icons'):
            for i, flags in self.original_flag_icons.items():
                self.main_game.army_flag_icons[i] = flags

        self.active = False

    def deactivate(self):
        """Deactivate the mission (called on exit)."""
        self._cleanup()
