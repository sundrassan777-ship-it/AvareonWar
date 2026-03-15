# -*- coding: utf-8 -*-
# campaign_mission_6.py
# Campaign Mission 6: The Second War
# 3 factions: Human (Red) vs Northern Powers (Blue, Hard AI) + Independent States (Yellow, Med AI).
# Blue and Yellow are allied against Human. 4 sequential quests with territory transfers.
# Dynamic AI: Blue activates when Red attacks Yellow, angers when Red attacks Blue.
# Victory: Complete all 4 quests. Defeat: Red loses all 4 core territories simultaneously.

import copy
import random
import pygame
import time
import map_data
from utils.logger import get_logger
# Shared campaign utilities (TransmissionOverlay, camera animations, endgame sequences)
from campaign_utils import TransmissionOverlay, CameraZoomAnimation
from campaign_utils import update_endgame_sequence, render_endgame_sequence

logger = get_logger(__name__)

# ============================================================================
# MISSION CONFIGURATION
# ============================================================================

# All 33 territories enabled for this mission
MISSION_6_TERRITORIES = [
    # Player 0 (Human / Red): 5 starting territories
    "Nordica", "Leuse Valley", "Velognia", "Valeonia", "Sordia",
    # Player 1 (Northern Powers / Blue): 5 starting territories
    "Duchy of Daurels", "Northern Heilonia", "Aelatania", "Londia", "Courtieux",
    # Player 2 (Independent States / Yellow): 23 starting territories
    "Daomea", "Ahtep", "Amennia", "Liadnon", "Sstep",
    "Anodia", "Southern Quil'en", "Northern Quil'en", "Amorian Shores",
    "Venexia", "Révia",
    "Role", "Vice", "Mose", "Riar", "Ajuna", "Espoia",
    "Nefrid", "Conda", "Odatria", "Cinto", "Oucine", "Ahara",
]

# Faction territory ownership mapping
FACTION_TERRITORIES = {
    0: ["Nordica", "Leuse Valley", "Velognia", "Valeonia", "Sordia"],
    1: ["Duchy of Daurels", "Northern Heilonia", "Aelatania", "Londia", "Courtieux"],
    2: ["Daomea", "Ahtep", "Amennia", "Liadnon", "Sstep",
        "Anodia", "Southern Quil'en", "Northern Quil'en", "Amorian Shores",
        "Venexia", "Révia",
        "Role", "Vice", "Mose", "Riar", "Ajuna", "Espoia",
        "Nefrid", "Conda", "Odatria", "Cinto", "Oucine", "Ahara"],
}

# Player colors: Red (human), Blue (Northern Powers), Yellow (Independent States)
PLAYER_COLORS = [
    (255, 100, 100),   # Player 0: Red (human)
    (100, 150, 255),   # Player 1: Blue (Northern Powers)
    (255, 220, 100),   # Player 2: Yellow (Independent States)
]

# Faction display names
FACTION_NAMES = {
    0: None,                    # Human player (use profile name)
    1: "Northern Powers",
    2: "Independent States",
}

# Starting gold per faction
STARTING_GOLD = {
    0: 500,
    1: 1650,
    2: 350,
}

# Territories Red cannot attack at game start (unlocked progressively via quests)
INITIALLY_BLOCKED_TERRITORIES = {
    "Venexia", "Révia", "Liadnon", "Northern Heilonia", "Duchy of Daurels",
    "Aelatania", "Courtieux", "Londia", "Amennia", "Sstep", "Ahtep", "Daomea",
    "Role", "Vice", "Mose", "Riar", "Ajuna", "Espoia",
    "Nefrid", "Conda", "Odatria", "Cinto", "Oucine", "Ahara",
}

# Quest target territories (sequential — each must be completed before the next)
QUEST_1_TARGETS = ["Anodia", "Southern Quil'en", "Amorian Shores", "Northern Quil'en"]
QUEST_2_TARGETS = ["Liadnon", "Sstep", "Amennia"]
QUEST_3_TARGETS = ["Révia", "Venexia"]
QUEST_4_TARGETS = ["Northern Heilonia", "Duchy of Daurels", "Londia"]

# Territories transferred to Red on Quest 1 completion
QUEST_1_TRANSFER_TO_RED = ["Ahtep", "Daomea"]

# Territories transferred to Blue on Quest 1 completion
QUEST_1_TRANSFER_TO_BLUE = [
    "Role", "Vice", "Mose", "Riar", "Ajuna", "Espoia",
    "Nefrid", "Conda", "Odatria", "Cinto", "Oucine", "Ahara",
    "Amennia", "Sstep", "Liadnon",
]

# Territories unblocked for Red attack after each quest
QUEST_1_UNBLOCK = [
    "Role", "Vice", "Mose", "Riar", "Ajuna", "Espoia",
    "Nefrid", "Conda", "Odatria", "Cinto", "Oucine", "Ahara",
    "Amennia", "Sstep", "Liadnon",
]
QUEST_2_UNBLOCK = ["Révia", "Venexia"]
QUEST_3_UNBLOCK = ["Northern Heilonia", "Duchy of Daurels", "Aelatania", "Courtieux", "Londia"]

# Territories transferred to Blue on Quest 2 completion
QUEST_2_TRANSFER_TO_BLUE = ["Venexia", "Révia"]

# Defeat condition: Red loses ALL of these simultaneously
DEFEAT_TERRITORIES = ["Leuse Valley", "Nordica", "Valeonia", "Velognia"]

# Mission speaker name for transmissions
MISSION_6_SPEAKER = "King Leonid Royen"

# Intro sequence: zoom to Leuse Valley + opening transmissions
INTRO_SEQUENCE = [
    # Step 0: Zoom to Leuse Valley
    ("zoom_to", "Leuse Valley", ""),
    # Step 1-4: Opening narrative transmissions (durations = voice file length + 1s)
    ("wait", 8.9, "Even though Azincourne fell, we cannot relent. We are not safe for as long as Azincourne is allowed to prosper."),
    ("wait", 11.1, "Conquest at this point, however, would be ill-advised. The borderlands are massively secured. We need allies and resources for a full-scale invasion."),
    ("wait", 12.3, "Our ally, Sordia, will join our fight. Our common ancestry will be the cornerstone of our alliance. However, they are far to the southwest."),
    ("wait", 9.8, "We need to build a corridor between us and them. Take over the states of Quil'en and Anodia - we will use their resources for our war."),
    # Step 5: Start gameplay
    ("start_game", 0, ""),
]

# Map intro step indices to voice keys (step 0 is zoom, steps 1-4 are transmissions)
INTRO_STEP_TO_VOICE = {1: "M6T1", 2: "M6T2", 3: "M6T3", 4: "M6T4"}

# ============================================================================
# UNIT CREATION HELPERS (same pattern as campaign_mission_5.py)
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
    # ========== HUMAN (Player 0, Red) ==========
    "Sordia": {
        "owner": 0,
        "buildings": {0: "Keep"},
        "units": _make_units([("Swordsman", 1), ("Archer", 1), ("Pikeman", 1), ("Cavalry", 1)]),
    },
    "Nordica": {
        "owner": 0,
        "buildings": {0: "Barracks"},
        "units": _make_units([("Swordsman", 1), ("Archer", 1), ("Pikeman", 1), ("Cavalry", 1)]),
    },
    "Leuse Valley": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Training Grounds"},
        "units": _make_units([("Swordsman", 2), ("Archer", 2), ("Pikeman", 2), ("Cavalry", 2), ("Captain", 1)]),
    },
    "Velognia": {
        "owner": 0,
        "buildings": {0: "Farm"},
        "units": _make_units([("Swordsman", 1), ("Archer", 1), ("Pikeman", 1), ("Cavalry", 1)]),
    },
    "Valeonia": {
        "owner": 0,
        "buildings": {0: "Keep"},
        "units": _make_units([("Swordsman", 1), ("Archer", 1), ("Pikeman", 1), ("Cavalry", 1), ("Captain", 1)]),
    },

    # ========== NORTHERN POWERS (Player 1, Blue) ==========
    "Aelatania": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_random_units(15),
    },
    "Duchy of Daurels": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_random_units(15),
    },
    "Northern Heilonia": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Barracks", 2: "Farm"},
        "units": _make_random_units(9),
    },
    "Londia": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Barracks"},
        "units": _make_random_units(9),
    },
    "Courtieux": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Farm"},
        "units": _make_random_units(15),
    },

    # ========== INDEPENDENT STATES (Player 2, Yellow) — specific buildings ==========
    "Révia": {
        "owner": 2,
        "buildings": {0: "Square", 1: "Keep"},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Venexia": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Amorian Shores": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_random_units(random.randint(1, 4)),
    },

    # ========== INDEPENDENT STATES (Player 2, Yellow) — no specific buildings ==========
    "Anodia": {
        "owner": 2,
        "buildings": {},  # Filled randomly in _setup_initial_state
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Southern Quil'en": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Northern Quil'en": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Daomea": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Ahtep": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Amennia": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Liadnon": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Sstep": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Role": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Vice": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Mose": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Riar": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Ajuna": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Espoia": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Nefrid": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Conda": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Odatria": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Cinto": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Oucine": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
    "Ahara": {
        "owner": 2,
        "buildings": {},
        "units": _make_random_units(random.randint(1, 4)),
    },
}


# ============================================================================
# MISSION 6 CLASS
# ============================================================================

class Mission6:
    """
    Campaign Mission 6: The Second War

    3 factions: Human (Red) vs Northern Powers (Blue) + Independent States (Yellow).
    Blue and Yellow are allied (team 1). Human is solo (team 0).
    4 sequential quests with territory transfers and progressive unlocking.
    Dynamic AI: Blue activates when Red attacks Yellow, angers when Red attacks Blue.
    Victory: Complete all 4 quests. Defeat: Red loses all 4 core territories.
    """

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_6'
        self.active = True

        # AI turn timing (0.5s fast turns, same as missions 4/5)
        self.ai_turn_timer = 0.0
        self._ai_executed_this_turn = False  # Guard: prevent duplicate AI execution per turn

        # AI turn counter per faction
        self.faction_turn_count = {1: 0, 2: 0}

        # --- Dynamic AI behavior flags ---
        # Blue (Northern Powers) starts passive — activated by player actions
        self.blue_active = False     # Blue can attack Red when True
        self.blue_angered = False    # Blue uses 3 armies instead of 1 when True

        # Blocked territories: Red cannot send armies to these territories
        self._blocked_territories = set(INITIALLY_BLOCKED_TERRITORIES)

        # Quest state: tracks which quest is currently active (1-4)
        self.current_quest = 1

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

        # Quest log — 4 objectives (sequential)
        self.quest_log = [
            {'text': 'Conquer Anodia, Southern Quil\'en, Amorian Shores and Northern Quil\'en', 'completed': False},
            {'text': 'Conquer Liadnon, Sstep and Amennia', 'completed': False},
            {'text': 'Conquer Révia and Venexia', 'completed': False},
            {'text': 'Conquer Northern Heilonia, Duchy of Daurels and Londia', 'completed': False},
        ]

        # Victory/defeat sequence state (same attrs as missions 4/5, needed by campaign_utils)
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
        self._defeat_text = "We have lost our homeland. All is lost."
        self._defeat_voice_key = "M6T12"

        # Allow turn timer to auto-end player turns
        self.allow_timer_expiry = True

        # Store original flag icons for restoration on cleanup
        self.original_flag_icons = None

        # Set up territory filtering
        map_data.set_enabled_territories(MISSION_6_TERRITORIES)

        # Set up initial game state
        self._setup_initial_state()

        # Pre-assign starting heroes to the human player
        self._assign_starting_heroes()

        # Start intro sequence
        self._start_intro_sequence()

        logger.info("Mission 6 'The Second War' initialized: 33 territories, 3 factions, teams [0, 1, 1]")

    def _setup_initial_state(self):
        """Configure the game state for Mission 6 scenario."""
        gs = self.game_state

        # Set player colors (3 players)
        for i, color in enumerate(PLAYER_COLORS):
            if i < len(gs.player_colors):
                gs.player_colors[i] = color

        # Remap flag icons to match player colors
        # Default flag order: 0=Red, 1=Blue, 2=Green, 3=Yellow
        # Mission 6: Player 0=Red (keep), Player 1=Blue (keep), Player 2=Yellow (from slot 3)
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and len(game.army_flag_icons) >= 4:
            self.original_flag_icons = {i: game.army_flag_icons[i] for i in range(4)}
            # Player 0 (Red) = original index 0 — no change needed
            # Player 1 (Blue) = original index 1 — no change needed
            game.army_flag_icons[2] = self.original_flag_icons[3]  # Yellow for Independent States

        # Set faction names
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name

        # Set starting gold per faction
        for player_id, gold in STARTING_GOLD.items():
            if player_id < gs.num_players:
                gs.player_gold[player_id] = gold

        # Set up alliances: Blue (1) and Yellow (2) allied against Red (0)
        gs.player_teams[0] = 0  # Red: team 0 (solo)
        gs.player_teams[1] = 1  # Blue: team 1
        gs.player_teams[2] = 1  # Yellow: team 1

        # Configure each territory from TERRITORY_SETUP
        for territory, config in TERRITORY_SETUP.items():
            owner = config["owner"]
            gs.territory_owners[territory] = owner

            # Clear any pre-existing garrisons from default game init
            # (prevents stale armies from other players appearing in mission territories)
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
        # (prevents default game init from leaving stale armies/buildings on the map)
        mission_set = set(MISSION_6_TERRITORIES)
        for territory in list(gs.territory_owners.keys()):
            if territory not in mission_set:
                gs.territory_owners[territory] = -1
                gs.territory_garrisons[territory] = {}
                gs.buildings[territory] = {}

        # Fill empty plots in AI territories with random Farm/Mine/Barracks
        self._fill_ai_empty_plots()

        # Invalidate bonus cache after bulk territory setup
        gs.invalidate_territorial_bonus_cache()

        # Set starting territories for reference
        gs.player_starting_territories[0] = "Leuse Valley"
        gs.player_starting_territories[1] = "Aelatania"
        gs.player_starting_territories[2] = "Révia"

        # --- Pre-researched technologies ---
        self._pre_research_techs(0, max_row=2)  # Red: rows 0-2
        self._pre_research_techs(2, max_row=2)  # Yellow: rows 0-2
        self._pre_research_techs(1, max_row=5)  # Blue: rows 0-5 (needs castle)

        logger.info("Mission 6 initial state configured: 33 territories, alliances [0] vs [1,2]")

    def _fill_ai_empty_plots(self):
        """Fill unspecified plots in AI territories with random Farm/Mine/Barracks.
        Human (player 0) unspecified plots remain empty."""
        gs = self.game_state
        random_buildings = ['Farm', 'Mine', 'Barracks']

        for territory, config in TERRITORY_SETUP.items():
            owner = config["owner"]
            if owner == 0:
                continue  # Human plots stay empty if not specified

            plots = map_data.get_plots(territory)
            buildings = gs.buildings.get(territory, {})

            for plot_idx in range(len(plots)):
                if plot_idx in buildings:
                    continue  # Already has a building
                # Fill with random building
                gs.buildings[territory][plot_idx] = random.choice(random_buildings)

    def _pre_research_techs(self, player_id, max_row):
        """Pre-research all techs in rows 0 through max_row for all 3 columns.
        Mirrors finish_research() logic for applying effects."""
        gs = self.game_state

        # For rows 3+, player needs a Castle. Set it up on a Keep territory.
        if max_row >= 3 and player_id == 1:
            # Blue: Castle at Aelatania (plot 0 = Keep)
            gs.castle_upgrades['Aelatania'] = {0: True}

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

        # Row 5: tech_0_5 (Efficient Mining II), tech_1_5 (Cavalry Mastery), tech_2_5 (Improved Command II)
        if max_row >= 5:
            # tech_0_5: Efficient Mining II — +20% Mine income again (checked inline)
            # tech_1_5: Cavalry Mastery — Cavalry strength bonus (checked inline)
            gs.player_command_limit[player_id] += 35               # tech_2_5: +35 command limit (total +70)

        # Unlock next tier techs (row after max_row) if available
        next_row = max_row + 1
        if next_row < 7:
            for col in range(3):
                gs.player_tech_available[player_id].add(f"tech_{col}_{next_row}")

    def _assign_starting_heroes(self):
        """Pre-assign Vearen Asford (Leuse Valley) and Halon Nextroy (Valeonia) to Red."""
        gs = self.game_state

        if 0 not in gs.heroes:
            gs.heroes[0] = {}
        if 0 not in gs.hero_ownership:
            gs.hero_ownership[0] = set()

        # Vearen Asford at Leuse Valley Keep (plot 0)
        gs.heroes[0]["Vearen Asford"] = {
            'keep_territory': 'Leuse Valley',
            'keep_plot': 0  # Keep is at plot index 0 for Leuse Valley
        }
        gs.hero_ownership[0].add("Vearen Asford")

        # Halon Nextroy at Valeonia Keep (plot 0)
        gs.heroes[0]["Halon Nextroy"] = {
            'keep_territory': 'Valeonia',
            'keep_plot': 0  # Keep is at plot index 0 for Valeonia
        }
        gs.hero_ownership[0].add("Halon Nextroy")

        logger.info("Assigned Vearen Asford to Leuse Valley Keep, Halon Nextroy to Valeonia Keep")

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

        elif action == 'wait':
            # Show transmission text and wait for duration
            self.intro_timer = 0.0
            if text:
                self._show_transmission(text, speaker=MISSION_6_SPEAKER)
                self.transmission_duration = param
                # Play voice line for this intro step
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
    # TRANSMISSION HELPERS
    # ========================================================================

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
    # UPDATE (called every frame)
    # ========================================================================

    def update(self, delta_time):
        """Called every frame to update mission state."""
        if not self.active:
            return None
        # Cap delta_time to prevent animation jumps on large frame times
        delta_time = min(delta_time, 0.05)

        # Update camera animation (zoom)
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

                text = "The Azincourne heartland lies wide open! They will surely not be able to withstand our might and sue for peace!"
                self._show_transmission(text, speaker=MISSION_6_SPEAKER)
                self.transmission_duration = 8.3
                self.transmission_timer = 0.0
                # Play victory voice line
                from global_sound import play_transmission_sound
                play_transmission_sound("M6T11")

        # Deferred defeat: same pattern
        if self._defeat_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.transmission_queue:
                self._defeat_waiting = False
                self._pending_defeat = True
                self.game_paused = True

                self._show_transmission(self._defeat_text, speaker=MISSION_6_SPEAKER)
                self.transmission_duration = 4.6
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
    # AI CONTROL — custom AI with dynamic behavior
    # ========================================================================

    @property
    def block_ai(self):
        """Block normal AI for all AI players — Mission6 controls their behavior."""
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
        """Called instead of normal AI execution. Dispatches to custom faction AI."""
        current_player = self.game_state.current_player
        if current_player == 0:
            return

        # Guard: only execute AI once per turn (this method is called every frame)
        if self._ai_executed_this_turn:
            return
        self._ai_executed_this_turn = True

        # Execute the custom faction AI
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
    # CUSTOM FACTION AI — build, train, reinforce, attack with dynamic rules
    # ========================================================================

    def _execute_faction_ai(self, player_id):
        """Execute AI for a faction: build, train, reinforce, then attack.

        Blue (player 1): Initially passive. Activated when Red attacks Yellow.
          - Activation: can attack Red with max 1 army per source, can train.
          - After Quest 2: can attack with max 2 armies per source.
          - After Quest 3+: can attack with max 3 armies per source.
          - Core territories (Daurels, Aelatania, Londia, Courtieux) keep min 11 armies.
          - Always fortifies own territories only (never Yellow's).

        Yellow (player 2): Never attacks Red.
          - Can train, but max 6 armies per territory.
          - Fortifies own territories only (path must not cross other players').
        """
        gs = self.game_state

        # Increment turn counter for this faction
        self.faction_turn_count[player_id] = self.faction_turn_count.get(player_id, 0) + 1

        # Find territories owned by this faction
        my_territories = [t for t in MISSION_6_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return  # Faction eliminated

        # Phase 1: Build structures on empty plots (always)
        self._ai_build(player_id, my_territories)

        # Phase 2: Train units (with faction-specific rules)
        if player_id == 1:
            # Blue: can only train when activated
            if self.blue_active:
                self._ai_train(player_id, my_territories, max_per_territory=None)
        elif player_id == 2:
            # Yellow: can always train, max 6 armies per territory
            self._ai_train(player_id, my_territories, max_per_territory=6)

        # Phase 3: Reinforce own territories (Blue only — Yellow cannot reinforce)
        if player_id == 1:
            self._ai_reinforce(player_id, my_territories)

        # Phase 4: Attack enemy territories (with faction-specific rules)
        if player_id == 1:
            # Blue: only attacks Red when activated
            if self.blue_active:
                # Scale attack strength by quest progress:
                # Quest 1 active: 1 unit per attack
                # After Quest 2: 2 units per attack
                # After Quest 3+: 3 units per attack
                if self.current_quest >= 4:
                    max_units_per_attack = 3
                elif self.current_quest >= 3:
                    max_units_per_attack = 2
                else:
                    max_units_per_attack = 1
                self._ai_attack(player_id, my_territories, max_units_per_attack)
        # Yellow: never attacks Red (no attack phase)

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
                    original_player = gs.current_player
                    try:
                        gs.current_player = player_id
                        gs.start_construction(territory, plot_idx, building_type)
                    finally:
                        gs.current_player = original_player
                    break  # One building per territory per turn

    def _ai_train(self, player_id, my_territories, max_per_territory=None):
        """Train units at all barracks. Optionally cap total armies per territory."""
        gs = self.game_state

        # Cycle through unit types for variety
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

                # Check army limit (global max or per-territory cap)
                total_units = sum(len(g.get('units', []))
                                  for g in gs.territory_garrisons.get(territory, {}).values())
                if total_units >= gs.MAX_ARMIES_PER_TERRITORY:
                    continue
                if max_per_territory is not None and total_units >= max_per_territory:
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

        Both Blue and Yellow: only fortify own territories.
        Yellow: path must not cross other players' territory (only move through own).
        """
        gs = self.game_state
        units_moved = 0
        max_units = 999  # No ramp limit on reinforcements

        # Identify enemy territories (not owned by self or allies)
        enemy_territories = set()
        for t in MISSION_6_TERRITORIES:
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

        # Identify rear territories (not on frontline)
        rear_territories = [t for t in my_territories if t not in frontline]

        for rear_t in rear_territories:
            if units_moved >= max_units:
                break

            garrison = gs.territory_garrisons.get(rear_t, {}).get(player_id, {})
            ready_units = [u for u in garrison.get('units', []) if u.get('status') == 'ready']
            if not ready_units:
                continue

            # Core Blue territories must keep at least BLUE_MIN_GARRISON armies
            if rear_t in self.BLUE_MIN_GARRISON_TERRITORIES:
                total_units = len(garrison.get('units', []))
                spare = total_units - self.BLUE_MIN_GARRISON
                if spare <= 0:
                    continue
                ready_units = ready_units[:spare]

            # Find adjacent OWN territory closer to frontline
            neighbors = map_data.get_neighbors(rear_t)
            best_target = None
            for n in neighbors:
                # Only move to own territories (never to ally territories)
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
                count = min(len(ready_units), available_slots, remaining_budget)
                units_to_move = ready_units[:count]

                if units_to_move:
                    unit_ids = [u['id'] for u in units_to_move]
                    gs.add_movement_order_for_units(rear_t, best_target, unit_ids, player=player_id)
                    units_moved += len(units_to_move)

    # Core Blue territories that must maintain minimum garrison of 11 armies
    BLUE_MIN_GARRISON_TERRITORIES = {"Duchy of Daurels", "Aelatania", "Londia", "Courtieux"}
    BLUE_MIN_GARRISON = 11

    def _ai_attack(self, player_id, my_territories, max_units_per_attack):
        """Attack enemy territories from every available source territory.

        Only targets Red (player 0) territories — never attacks allied Yellow.
        max_units_per_attack: cap on units sent from each source (1=active, 3=angered).
        Each target territory can be attacked from at most 2 different sources.
        Every source with ready units will attack if a valid target exists.
        Core Blue territories (Daurels, Aelatania, Londia, Courtieux) keep at least 11 armies.
        """
        gs = self.game_state

        # Find Red territories adjacent to our territories (only attack Red)
        red_territories = set()
        for t in MISSION_6_TERRITORIES:
            if gs.territory_owners.get(t, -1) == 0:
                red_territories.add(t)

        if not red_territories:
            return

        # Build attack candidates: (source, target, ready_count, score)
        attack_candidates = []
        for my_t in my_territories:
            garrison = gs.territory_garrisons.get(my_t, {}).get(player_id, {})
            ready_units = [u for u in garrison.get('units', []) if u.get('status') == 'ready']
            if not ready_units:
                continue

            neighbors = map_data.get_neighbors(my_t)
            for neighbor in neighbors:
                if neighbor in red_territories:
                    # Score: prefer targets where we have numerical advantage
                    target_garrison = gs.territory_garrisons.get(neighbor, {}).get(0, {})
                    target_count = len(target_garrison.get('units', []))
                    score = len(ready_units) - target_count
                    attack_candidates.append((my_t, neighbor, len(ready_units), score))

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

            # Re-fetch ready units (may have changed)
            garrison = gs.territory_garrisons.get(my_t, {}).get(player_id, {})
            ready_units = [u for u in garrison.get('units', []) if u.get('status') == 'ready']
            if not ready_units:
                continue

            # Core Blue territories must keep at least BLUE_MIN_GARRISON armies
            if my_t in self.BLUE_MIN_GARRISON_TERRITORIES:
                total_units = len(garrison.get('units', []))
                spare = total_units - self.BLUE_MIN_GARRISON
                if spare <= 0:
                    continue  # Not enough to attack while keeping minimum garrison
                ready_units = ready_units[:spare]  # Cap to spare units only

            # Send up to max_units_per_attack units from this source
            send_count = min(len(ready_units), max_units_per_attack)
            units_to_send = ready_units[:send_count]
            unit_ids = [u['id'] for u in units_to_send]
            gs.add_movement_order_for_units(my_t, target, unit_ids, player=player_id)
            used_sources.add(my_t)
            target_source_count[target] = target_source_count.get(target, 0) + 1
            logger.debug(f"AI {player_id} attacking {target} from {my_t} with "
                       f"{send_count} units (max {max_units_per_attack}/attack)")

    # ========================================================================
    # TERRITORY TRANSFERS (programmatic ownership change)
    # ========================================================================

    def _transfer_territories(self, territories, new_owner):
        """Transfer territories to new_owner, keeping existing buildings and armies.

        Buildings are territory-keyed (not player-keyed) so they stay automatically.
        Garrison units are moved from old owner's garrison to new owner's garrison.
        """
        gs = self.game_state
        for territory in territories:
            old_owner = gs.territory_owners.get(territory, -1)
            if old_owner == new_owner:
                continue  # Already owned by target

            gs.territory_owners[territory] = new_owner

            # Transfer garrison from old owner to new owner
            old_garrison = gs.territory_garrisons.get(territory, {}).get(old_owner, {})
            if old_garrison and old_garrison.get('units'):
                units = old_garrison.get('units', [])
                unmoved = old_garrison.get('unmoved', 0)
                moved = old_garrison.get('moved', 0)
                # Clear old garrison — delete key entirely to avoid empty dict
                # that would crash reset_garrison_moved_status (expects 'units' key)
                if territory in gs.territory_garrisons and old_owner in gs.territory_garrisons[territory]:
                    del gs.territory_garrisons[territory][old_owner]
                # Set new garrison under new owner
                gs.set_garrison_armies(territory, new_owner, unmoved=unmoved, moved=moved, units=units)
            else:
                # No garrison to transfer — ensure new owner has empty entry
                if territory not in gs.territory_garrisons:
                    gs.territory_garrisons[territory] = {}

        gs.invalidate_territorial_bonus_cache()
        logger.info(f"Transferred {len(territories)} territories to player {new_owner}")

    # ========================================================================
    # QUEST SYSTEM (sequential quests with territory transfers)
    # ========================================================================

    def _check_quest_completion(self):
        """Check if the current quest's targets are all owned by Red (player 0)."""
        gs = self.game_state

        if self.current_quest == 1:
            if all(gs.territory_owners.get(t) == 0 for t in QUEST_1_TARGETS):
                self._complete_quest_1()
        elif self.current_quest == 2:
            if all(gs.territory_owners.get(t) == 0 for t in QUEST_2_TARGETS):
                self._complete_quest_2()
        elif self.current_quest == 3:
            if all(gs.territory_owners.get(t) == 0 for t in QUEST_3_TARGETS):
                self._complete_quest_3()
        elif self.current_quest == 4:
            if all(gs.territory_owners.get(t) == 0 for t in QUEST_4_TARGETS):
                self._complete_quest_4()

    def _complete_quest_1(self):
        """Quest 1 complete: Conquer Anodia, S. Quil'en, Amorian Shores, N. Quil'en.

        Aftermath:
        - Red gains Ahtep + Daomea (with existing buildings/armies)
        - 15 southern territories transfer to Blue
        - Those territories become attackable by Red
        """
        self.quest_log[0]['completed'] = True
        self.current_quest = 2
        logger.info("Quest 1 complete — transferring territories")

        # Transfer Ahtep and Daomea to Red (player 0)
        self._transfer_territories(QUEST_1_TRANSFER_TO_RED, 0)

        # Transfer 15 southern territories to Blue (player 1)
        self._transfer_territories(QUEST_1_TRANSFER_TO_BLUE, 1)

        # Unblock those territories for Red attack
        for t in QUEST_1_UNBLOCK:
            self._blocked_territories.discard(t)

        # Also unblock Ahtep and Daomea (now owned by Red, but remove from blocked set)
        self._blocked_territories.discard("Ahtep")
        self._blocked_territories.discard("Daomea")

        # Two-part quest 1 completion transmission (durations = voice file length + 1s)
        self._queue_transmission(
            "Our alliance is secure. And look, the mighty empiurate of Ahtep agreed to join our cause.",
            7.6, "M6T5"
        )
        self._queue_transmission(
            "We will use their military to advance our ends, but beware - "
            "Azincourne has also found more allies. Push through Sstep, Liadnon "
            "and Amennia to secure our heartland.",
            13.0, "M6T6"
        )

    def _complete_quest_2(self):
        """Quest 2 complete: Conquer Liadnon, Sstep, Amennia.

        Aftermath:
        - Venexia and Révia transfer to Blue (with buildings/armies)
        - Révia and Venexia become attackable by Red
        """
        self.quest_log[1]['completed'] = True
        self.current_quest = 3
        logger.info("Quest 2 complete — transferring Venexia and Révia to Blue")

        # Transfer Venexia and Révia to Blue (player 1)
        self._transfer_territories(QUEST_2_TRANSFER_TO_BLUE, 1)

        # Unblock for Red attack
        for t in QUEST_2_UNBLOCK:
            self._blocked_territories.discard(t)

        self._queue_transmission(
            "We have rid Azincourne of its allies. Now it is time to strike. "
            "We must bypass the fortified borderlands by conquering the weak "
            "states of Venexia and Révia.",
            12.2, "M6T7"
        )

    def _complete_quest_3(self):
        """Quest 3 complete: Conquer Révia and Venexia.

        Aftermath:
        - Unlock Northern Blue territories for attack (N. Heilonia, Daurels, Aelatania, Courtieux, Londia)
        """
        self.quest_log[2]['completed'] = True
        self.current_quest = 4
        logger.info("Quest 3 complete — unlocking northern territories")

        # Unblock the Northern Powers' core territories for Red attack
        for t in QUEST_3_UNBLOCK:
            self._blocked_territories.discard(t)

        self._queue_transmission(
            "We are on the borders of Azincourne! Strike their heartland! "
            "Decimate their territories of Duchy of Daurels, Northern Heilonia and Londia!",
            11.1, "M6T8"
        )

    def _complete_quest_4(self):
        """Quest 4 complete: Conquer N. Heilonia, Duchy of Daurels, Londia.

        Aftermath: Victory!
        """
        self.quest_log[3]['completed'] = True
        logger.info("Quest 4 complete — VICTORY!")

        self._start_victory()

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
        """All 33 mission territories are viewable/hoverable."""
        if not self.active:
            return True
        return territory_name in MISSION_6_TERRITORIES

    def is_attack_target_blocked(self, territory_name):
        """Check if Red player is blocked from sending armies to this territory.

        Returns True if territory is in the blocked set and current player is Red (0).
        Used by main.py right-click handler to prevent army orders to restricted territories.
        """
        if self.game_state.current_player != 0:
            return False
        return territory_name in self._blocked_territories

    def get_adjacency_override(self, territory):
        """No special adjacency restrictions in Mission 6."""
        return None

    def get_highlight_territory(self):
        """No step-based territory highlighting in Mission 6."""
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
            self._on_territory_conquered(territory, new_owner)

    def _on_territory_conquered(self, territory, new_owner):
        """Handle territory conquest — check quests, dynamic AI triggers, and defeat condition.

        Quest completion: checked when Red conquers any territory.
        Blue activation: when Red conquers a Yellow territory.
        Blue anger: when Red conquers a Blue territory (overrides activation).
        Defeat: Red loses ALL 4 core territories simultaneously.
        """
        gs = self.game_state

        # --- DYNAMIC AI TRIGGERS (only when Red conquers) ---
        if new_owner == 0:
            # Check which faction previously owned this territory
            # (We check the original faction lists, not current owners, since transfers happen)

            # Trigger: Red attacks Yellow territory → Blue activates
            # We check if the territory was owned by Yellow (player 2) before conquest
            # Since new_owner is 0 and the territory was just conquered, the old owner
            # was whoever owned it. We can detect this by checking if Blue should activate.
            # Simpler: if territory was in Yellow's starting set or is currently Yellow-owned
            # after transfers, Blue activates.
            # Actually, we already know the conquest happened — the old owner was NOT Red.
            # We need to know if it was Yellow (2) or Blue (1).
            # The territory_owners was already updated to new_owner=0 before this callback,
            # so we can't read the old owner. Instead, we track based on territory lists.

            # For activation trigger: if territory was NOT one of Blue's starting territories
            # and Blue is not yet active, this was likely a Yellow territory → activate Blue
            if not self.blue_angered:
                if territory in FACTION_TERRITORIES[1] or territory in QUEST_3_UNBLOCK:
                    # Red conquered a Blue territory → anger Blue
                    if not self.blue_angered:
                        self.blue_angered = True
                        self.blue_active = True
                        logger.info(f"Blue angered! Red conquered Blue territory {territory}")
                        self._queue_transmission(
                            "The Northern Powers amass their forces against us. They send even more forces to attack!",
                            7.0, "M6T9"
                        )
                elif not self.blue_active:
                    # Red conquered a non-Blue territory (Yellow) → activate Blue
                    self.blue_active = True
                    logger.info(f"Blue activated! Red conquered Yellow territory {territory}")
                    self._queue_transmission(
                        "The Northern Powers have taken notice of our expansion. "
                        "They are sending skirmishing forces against us!",
                        7.5, "M6T10"
                    )

            # Check quest completion whenever Red conquers a territory
            self._check_quest_completion()

        # --- DEFEAT CHECK: Red lost ALL 4 core territories ---
        all_core_lost = all(
            gs.territory_owners.get(t) != 0
            for t in DEFEAT_TERRITORIES
        )
        if all_core_lost:
            logger.info("Red lost all 4 core territories — defeat!")
            self._defeat_text = "We have lost our homeland. All is lost."
            self._start_defeat()

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
        """Return visible quests only: completed quests + current active quest.
        Future quests are hidden until the previous quest is completed."""
        visible = []
        for i, quest in enumerate(self.quest_log):
            if quest['completed']:
                visible.append(quest)
            elif i + 1 == self.current_quest:
                # Show the currently active quest (quest indices are 1-based in current_quest)
                visible.append(quest)
            # Future quests are not shown
        return visible

    # ========================================================================
    # ACHIEVEMENT INTEGRATION
    # ========================================================================

    def get_bonus_conditions(self):
        """Return bonus achievement conditions for Mission 6."""
        return {
            'campaign_mission_6_bonus': False,  # TBD
        }

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def _cleanup(self):
        """Clean up mission state when exiting."""
        from global_sound import stop_transmission_sound
        logger.info("Cleaning up Mission 6")
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
