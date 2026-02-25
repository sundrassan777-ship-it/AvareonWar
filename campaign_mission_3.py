# -*- coding: utf-8 -*-
# campaign_mission_3.py
# Campaign Mission 3: Western Expansion
# Features dynamic alliance (Uhmayya joins then betrays), semi-dormant AI,
# heroes enabled, and AI restrictions (half-unit movement, no heroes).

import pygame
import map_data
import random
from utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# MISSION CONFIGURATION
# ============================================================================

# All 35 territories enabled for this mission
MISSION_3_TERRITORIES = [
    # Player start
    "Zjoal Islands",
    # Kingdom of Affrancia (9 territories)
    "Lunedale", "Free Cities", "Affrancian Uplands", "March of Auverne",
    "Vense", "Carnae", "Cualus", "Orlais", "Orhas",
    # Warlords of Nordia (14 territories)
    "Damlére", "Role", "Vice", "Oucine", "Daomea", "Espoia", "Nefrid",
    "Conda", "Ahara", "Cinto", "Odatria", "Mose", "Riar", "Ajuna",
    # Uhmayyan Empiurate (11 territories)
    "Linan", "Vianaa", "Osana", "Lamacia", "Aunon", "Fahlaan Dunes",
    "Leimarch", "Liadnon", "Ahtep", "Sordia", "Anodia",
]

# Faction territory ownership mapping
# Player 0 = Human, Player 1 = Kingdom of Affrancia (Active)
# Player 2 = Warlords of Nordia (Semi-dormant), Player 3 = Uhmayyan Empiurate (Semi-dormant -> Ally -> Betrays)
FACTION_TERRITORIES = {
    0: ["Zjoal Islands"],
    1: ["Lunedale", "Free Cities", "Affrancian Uplands", "March of Auverne",
        "Vense", "Carnae", "Cualus", "Orlais", "Orhas"],
    2: ["Damlére", "Role", "Vice", "Oucine", "Daomea", "Espoia", "Nefrid",
        "Conda", "Ahara", "Cinto", "Odatria", "Mose", "Riar", "Ajuna"],
    3: ["Linan", "Vianaa", "Osana", "Lamacia", "Aunon", "Fahlaan Dunes",
        "Leimarch", "Liadnon", "Ahtep", "Sordia", "Anodia"],
}

# Player colors
PLAYER_COLORS = [
    (100, 200, 100),   # Player 0: Green (human)
    (100, 150, 255),   # Player 1: Blue (Kingdom of Affrancia)
    (255, 100, 100),   # Player 2: Red (Warlords of Nordia)
    (255, 220, 100),   # Player 3: Yellow (Uhmayyan Empiurate)
]

# Faction names
FACTION_NAMES = {
    0: None,  # Use player's profile name
    1: "Kingdom of Affrancia",
    2: "Warlords of Nordia",
    3: "Uhmayyan Empiurate",
}

# Key territory that triggers Uhmayyan alliance
ALLIANCE_TRIGGER_TERRITORY = "Orhas"

# Player capital (defeat if lost)
PLAYER_CAPITAL = "Zjoal Islands"

# ============================================================================
# TERRITORY SETUP - Initial buildings and units
# ============================================================================

TERRITORY_SETUP = {
    # ========== PLAYER (idx 0) ==========
    "Zjoal Islands": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 6, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 7, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 8, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 9, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 10, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 11, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 12, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 13, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },

    # ========== KINGDOM OF AFFRANCIA (idx 1) - ACTIVE AI ==========
    "Free Cities": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Keep"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Lunedale": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 6, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Affrancian Uplands": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Farm"},
        "units": [
            {"type": "Pikeman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "March of Auverne": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Mine", 2: "Farm"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Vense": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Carnae": {
        "owner": 1,
        "buildings": {0: "Mine", 1: "Mine"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Cualus": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Barracks"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Orlais": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Farm"},
        "units": [
            {"type": "Archer", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Orhas": {
        "owner": 1,
        "buildings": {0: "Keep"},
        "units": [
            {"type": "Archer", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },

    # ========== UHMAYYAN EMPIURATE (idx 3) - SEMI-DORMANT -> ALLY -> BETRAYS ==========
    "Linan": {
        "owner": 3,
        "buildings": {0: "Keep"},
        "units": [
            {"type": "Archer", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Ahtep": {
        "owner": 3,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Barracks"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Liadnon": {
        "owner": 3,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Anodia": {
        "owner": 3,
        "buildings": {0: "Barracks", 1: "Mine"},
        "units": [
            {"type": "Pikeman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Sordia": {
        "owner": 3,
        "buildings": {0: "Keep", 1: "Mine"},
        "units": [
            {"type": "Pikeman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Fahlaan Dunes": {
        "owner": 3,
        "buildings": {0: "Barracks"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Vianaa": {
        "owner": 3,
        "buildings": {0: "Farm", 1: "Farm"},
        "units": [
            {"type": "Pikeman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Osana": {
        "owner": 3,
        "buildings": {0: "Keep"},
        "units": [
            {"type": "Archer", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Lamacia": {
        "owner": 3,
        "buildings": {0: "Barracks"},
        "units": [
            {"type": "Swordsman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Swordsman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Aunon": {
        "owner": 3,
        "buildings": {0: "Mine"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Leimarch": {
        "owner": 3,
        "buildings": {0: "Keep"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },

    # ========== WARLORDS OF NORDIA (idx 2) - SEMI-DORMANT ==========
    # Damlére and Daomea have specified buildings/units
    "Damlére": {
        "owner": 2,
        "buildings": {0: "Keep"},
        "units": [
            {"type": "Pikeman", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 4, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Pikeman", "id": 5, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 6, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 7, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 8, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    "Daomea": {
        "owner": 2,
        "buildings": {0: "Keep"},
        "units": [
            {"type": "Cavalry", "id": 0, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Cavalry", "id": 1, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 2, "status": "ready", "order": None, "xp": 0, "level": 0},
            {"type": "Archer", "id": 3, "status": "ready", "order": None, "xp": 0, "level": 0},
        ]
    },
    # Remaining 12 Nordia territories: free plots, random 0-3 units
    # These will be generated dynamically in _setup_initial_state
}

# Nordia territories that need random unit generation
NORDIA_RANDOM_TERRITORIES = [
    "Role", "Vice", "Oucine", "Espoia", "Nefrid", "Conda",
    "Ahara", "Cinto", "Odatria", "Mose", "Riar", "Ajuna"
]

# Available unit types for random generation
RANDOM_UNIT_TYPES = ["Swordsman", "Pikeman", "Archer", "Cavalry"]


# ============================================================================
# INTRO SEQUENCE DEFINITION
# ============================================================================

INTRO_SEQUENCE = [
    # Initial camera zoom to player start
    ("zoom_to", "Zjoal Islands", ""),
    ("wait", 10.0, "I feel the call of the thunder gods beckoning. The corrupt Affrancia must not rule the west any longer."),
    ("wait", 7.0, "My name is Serthus Diarcess. And I have a vision.. a vision of greatness."),
    ("show_timer", 5.0, "The path will not be easy.. many foes stand in our way."),
    ("pan_to", "Free Cities", ""),
    ("wait", 8.0, "The Kingdom of Affrancia - my former home. Even now they marshal armies to squash us."),
    ("pan_to", "Damlére", ""),
    ("wait", 8.0, "The Warlords of Nordia. Fractured, but numerous. They build strength while watching the horizon."),
    ("pan_to", "Ahtep", ""),
    ("wait", 7.0, "And the Uhmayyan Empiurate. Cunning traders and warriors of the southern sands."),
    ("pan_to", "Zjoal Islands", ""),
    ("wait", 7.0, "We must break these forces and unite the west under the Zjoal rule. By blood and honor!"),
    ("start_game", 0, ""),
]

# ============================================================================
# INTRO VOICE MAPPING (INTRO_SEQUENCE index → voice key)
# ============================================================================

INTRO_STEP_TO_VOICE = {
    1: "M3T1", 2: "M3T2", 3: "M3T3",
    5: "M3T4", 7: "M3T5", 9: "M3T6", 11: "M3T7"
}


# ============================================================================
# TRANSMISSION OVERLAY (reused from Mission 2)
# ============================================================================

class TransmissionOverlay:
    """Renders the Transmission Board with speaker header, flush at top-left of map area."""

    def __init__(self, screen_width, screen_height, text, top_panel_height, speaker=""):
        self.text = text
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.top_panel_height = top_panel_height
        self.speaker = speaker

        # Board dimensions: ~29% screen width (full image including transparent padding)
        self.width = int(screen_width * 0.29)

        # TransmissionBG.png has transparent padding around the visible wooden board.
        # These fractions (measured from the source image) let us align the header
        # with the visible board area and eliminate visual gaps.
        BG_LEFT_FRAC = 0.069   # 6.9% left/right transparent margin
        BG_TOP_FRAC = 0.200    # 20% top transparent margin

        # Load and scale body background (TransmissionBG.png)
        try:
            raw_bg = pygame.image.load('assets/TransmissionBG.png').convert_alpha()
        except pygame.error:
            raw_bg = None

        if raw_bg:
            aspect = raw_bg.get_height() / raw_bg.get_width()
            self.body_height = int(self.width * aspect)
            self.bg_surface = pygame.transform.smoothscale(raw_bg, (self.width, self.body_height))
        else:
            self.body_height = int(screen_height * 0.12)
            self.bg_surface = None

        # Calculate visible body area insets (in scaled pixels)
        bg_left_inset = int(self.width * BG_LEFT_FRAC)
        bg_top_inset = int(self.body_height * BG_TOP_FRAC)
        visible_body_width = self.width - 2 * bg_left_inset

        # Load and scale speaker header (GMenuButton.png) to match visible body width
        try:
            raw_header = pygame.image.load('assets/SpeakerBG.png').convert_alpha()
        except pygame.error:
            raw_header = None

        if raw_header:
            header_aspect = raw_header.get_height() / raw_header.get_width()
            natural_header_h = int(visible_body_width * header_aspect)
            self.header_height = int(natural_header_h * 0.2)  # 20% of natural height
            self.header_surface = pygame.transform.smoothscale(
                raw_header, (visible_body_width, self.header_height))
        else:
            self.header_height = int(screen_height * 0.03)
            self.header_surface = None

        self.header_width = visible_body_width

        # Header: flush at screen left edge, just below top panel
        self.header_x = 0
        self.header_y = top_panel_height

        # Body: shifted left so visible board edge aligns with screen edge,
        # shifted up so visible board top touches header bottom
        self.body_x = -bg_left_inset
        self.body_y = self.header_y + self.header_height - bg_top_inset

        # Keep self.height for text padding calculations
        self.height = self.body_height

        # Body text font
        try:
            self.font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(14, int(screen_height / 47)))
        except (FileNotFoundError, OSError):
            self.font = pygame.font.SysFont('serif', max(14, int(screen_height / 47)))

        # Speaker name font (bold, slightly smaller)
        try:
            self.speaker_font = pygame.font.Font('assets/fonts/Cinzel-Bold.ttf', max(13, int(screen_height / 52)))
        except (FileNotFoundError, OSError):
            self.speaker_font = pygame.font.SysFont('serif', max(13, int(screen_height / 52)), bold=True)

    def set_text(self, text, speaker=None):
        """Update the displayed text and optionally the speaker."""
        self.text = text
        if speaker is not None:
            self.speaker = speaker

    def render(self, screen):
        """Draw the speaker header + transmission board overlay."""
        # Draw body first (TransmissionBG.png) — its transparent padding won't cover the header
        if self.bg_surface:
            screen.blit(self.bg_surface, (self.body_x, self.body_y))
        else:
            panel_rect = pygame.Rect(self.body_x, self.body_y, self.width, self.body_height)
            bg = pygame.Surface((self.width, self.body_height), pygame.SRCALPHA)
            bg.fill((20, 20, 30, 220))
            screen.blit(bg, (self.body_x, self.body_y))
            pygame.draw.rect(screen, (180, 160, 100), panel_rect, 2)

        # Draw speaker header (GMenuButton.png) on top
        if self.header_surface:
            screen.blit(self.header_surface, (self.header_x, self.header_y))
        else:
            hdr_bg = pygame.Surface((self.header_width, self.header_height), pygame.SRCALPHA)
            hdr_bg.fill((40, 30, 20, 230))
            screen.blit(hdr_bg, (self.header_x, self.header_y))
            pygame.draw.rect(screen, (180, 160, 100),
                             pygame.Rect(self.header_x, self.header_y,
                                         self.header_width, self.header_height), 2)

        # Draw speaker name centered on header
        if self.speaker:
            speaker_surface = self.speaker_font.render(self.speaker, True, (255, 255, 240))
            sx = self.header_x + (self.header_width - speaker_surface.get_width()) // 2
            sy = self.header_y + (self.header_height - speaker_surface.get_height()) // 2
            screen.blit(speaker_surface, (sx, sy))

        # Render wrapped text inside the visible body area
        padding_x = int(self.width * 0.12)
        padding_y = int(self.body_height * 0.25)
        text_area_width = self.width - 2 * padding_x
        self._render_wrapped_text(screen, self.text, self.body_x + padding_x,
                                  self.body_y + padding_y, text_area_width)

    def _render_wrapped_text(self, screen, text, x, y, max_width):
        words = text.split(' ')
        lines = []
        current_line = ''
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            test_surface = self.font.render(test_line, True, (255, 255, 255))
            if test_surface.get_width() > max_width and current_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)

        line_height = self.font.get_linesize()
        for i, line in enumerate(lines):
            line_surface = self.font.render(line, True, (255, 255, 240))
            screen.blit(line_surface, (x, y + i * line_height))


# ============================================================================
# CAMERA ANIMATIONS (reused from Mission 2)
# ============================================================================

class CameraPanAnimation:
    """Smooth camera pan from current position to a target territory center."""

    def __init__(self, camera_handler, target_center_world, duration, screen_width, map_area_height):
        self.camera = camera_handler
        self.target_center = target_center_world
        self.duration = duration
        self.screen_width = screen_width
        self.map_area_height = map_area_height
        self.elapsed = 0.0
        self.active = True

        screen_cx = screen_width / 2.0
        screen_cy = map_area_height / 2.0
        self.start_center = (
            self.camera.offset[0] + screen_cx / self.camera.zoom,
            self.camera.offset[1] + screen_cy / self.camera.zoom
        )

    def update(self, delta_time):
        if not self.active:
            return False

        self.elapsed += delta_time
        progress = min(1.0, self.elapsed / self.duration)

        if progress < 0.5:
            eased = 2 * progress * progress
        else:
            eased = 1 - pow(-2 * progress + 2, 2) / 2

        current_x = self.start_center[0] + (self.target_center[0] - self.start_center[0]) * eased
        current_y = self.start_center[1] + (self.target_center[1] - self.start_center[1]) * eased

        screen_cx = self.screen_width / 2.0
        screen_cy = self.map_area_height / 2.0
        self.camera.offset[0] = current_x - screen_cx / self.camera.zoom
        self.camera.offset[1] = current_y - screen_cy / self.camera.zoom
        self.camera.clamp_to_bounds()

        if progress >= 1.0:
            self.active = False
        return self.active


class CameraZoomAnimation:
    """Smooth camera zoom animation centered on a target point."""

    def __init__(self, camera_handler, start_zoom, target_zoom, duration, target_center_world,
                 screen_width, map_area_height):
        self.camera = camera_handler
        self.start_zoom = start_zoom
        self.target_zoom = target_zoom
        self.duration = duration
        self.target_center = target_center_world
        self.screen_width = screen_width
        self.map_area_height = map_area_height
        self.elapsed = 0.0
        self.active = True

        self.camera.zoom = start_zoom
        self._update_camera_position(0.0)

    def update(self, delta_time):
        if not self.active:
            return False
        self.elapsed += delta_time
        progress = min(1.0, self.elapsed / self.duration)

        eased = 1.0 - pow(1.0 - progress, 3)
        self.camera.zoom = self.start_zoom + (self.target_zoom - self.start_zoom) * eased
        self._update_camera_position(eased)

        if progress >= 1.0:
            self.active = False
        return self.active

    def _update_camera_position(self, progress):
        screen_cx = self.screen_width / 2.0
        screen_cy = self.map_area_height / 2.0
        self.camera.offset[0] = self.target_center[0] - screen_cx / self.camera.zoom
        self.camera.offset[1] = self.target_center[1] - screen_cy / self.camera.zoom
        self.camera.clamp_to_bounds()


# ============================================================================
# MISSION 3 MAIN CLASS
# ============================================================================

class Mission3:
    """
    Campaign Mission 3: Western Expansion

    Features:
    - 35 territories across 4 factions
    - Heroes ENABLED (player can train heroes, AI cannot)
    - Dynamic alliance: Uhmayya joins player after Orhas captured, then betrays
    - Semi-dormant AI: Nordia and Uhmayya have restricted behavior until triggered
    - AI restrictions: Half-unit movement, no heroes, no demolishing
    - Pre-assigned hero: Serthus Diarcess
    """

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_3'  # For achievement tracking
        self.active = True

        # Faction state tracking
        # Affrancia (1): Active from start
        # Nordia (2): Semi-dormant (can build/train, cannot move) until player has 4+ territories or attacked
        # Uhmayya (3): Semi-dormant until Affrancia eliminated OR Orhas captured OR Nordia attacked
        self.faction_awakened = {1: True, 2: False, 3: False}  # Affrancia starts active
        self.faction_defeated = {1: False, 2: False, 3: False}

        # Bonus achievement tracking: "Storming Nordia"
        # True if Nordia (faction 2) fully conquered while Affrancia (faction 1) held 5+ territories
        # throughout the entire time Nordia was alive. Disqualified if Affrancia ever dips below 5.
        self.bonus_storming_nordia = False
        self._storming_nordia_disqualified = False

        # Alliance and betrayal state
        self.alliance_formed = False  # Uhmayya joins player
        self.betrayal_triggered = False  # Uhmayya betrays after Affrancia+Nordia eliminated

        # Semi-dormant AI tracking for Nordia (can build/train but not move)
        self.nordia_awakened = False  # Fully awakened (can move)

        # Affrancia balance: alternate-turn attacks and defector spawns
        self.affrancia_turn_count = 0  # Affrancia attacks on odd turns only (1, 3, 5...)
        self.affrancia_captured = set()  # Track first-time Affrancia captures for defector spawns
        self.pending_defector_spawns = []  # Deferred spawns (resolved after battle cleanup)

        # AI turn timing
        self.ai_turn_timer = 0.0
        self.ai_turn_duration = 2.0

        # Intro sequence state
        self.intro_active = True
        self.intro_step_index = 0
        self.intro_timer = 0.0
        self.intro_waiting_for_pan = False
        self.game_paused = True
        self.timer_visible = False

        # Camera animation
        self.camera_animation = None

        # Transmission overlay
        self.transmission_overlay = None
        self.transmission_timer = 0.0
        self.transmission_duration = 0.0

        # Quest log - initial quests (Uhmayya alliance is a surprise)
        self.quest_log = [
            {'text': 'Defeat the Kingdom of Affrancia', 'completed': False},
            {'text': 'Defeat the Warlords of Nordia', 'completed': False},
            {'text': 'Serthus in Zjoal Islands must survive', 'completed': False},
        ]

        # Victory/defeat sequence state
        self.game_frozen = False
        self.victory_sequence_active = False
        self.victory_phase = None
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0
        self.victory_image = None
        self.victory_image_scale = 0.0
        self._pending_victory = False
        self._victory_waiting = False  # True when victory triggered but waiting for battles to finish

        self.defeat_sequence_active = False
        self.defeat_phase = None
        self.defeat_timer = 0.0
        self.defeat_fade_alpha = 0
        self.defeat_image = None
        self.defeat_image_scale = 0.0
        self._pending_defeat = False
        self._defeat_waiting = False  # True when defeat triggered but waiting for battles to finish

        # Pending transmission queue (list of (text, duration, voice_key) tuples)
        self.transmission_queue = []

        # Inter-transmission pause timer (1s gap between consecutive voiced intro steps)
        self._intro_pause_timer = 0.0

        # Timer highlight
        self.timer_highlight_start_time = None
        self.timer_highlight_duration = 20.0

        # Allow turn timer
        self.allow_timer_expiry = True

        # Store original flag icons
        self.original_flag_icons = None

        # Set up territory filtering
        map_data.set_enabled_territories(MISSION_3_TERRITORIES)

        # Set up initial game state
        self._setup_initial_state()

        # Pre-assign Serthus Diarcess to player
        self._assign_starting_hero()

        # Start intro sequence
        self._start_intro_sequence()

    def _setup_initial_state(self):
        """Configure the game state for Mission 3 scenario."""
        gs = self.game_state

        # Set player colors
        for i, color in enumerate(PLAYER_COLORS):
            if i < len(gs.player_colors):
                gs.player_colors[i] = color

        # Remap flag icons
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and len(game.army_flag_icons) >= 4:
            self.original_flag_icons = {i: game.army_flag_icons[i] for i in range(4)}
            # Player 0=Green (2), Player 1=Blue (1), Player 2=Red (0), Player 3=Yellow (3)
            game.army_flag_icons[0] = self.original_flag_icons[2]  # Green for human
            game.army_flag_icons[1] = self.original_flag_icons[1]  # Blue for Affrancia
            game.army_flag_icons[2] = self.original_flag_icons[0]  # Red for Nordia
            game.army_flag_icons[3] = self.original_flag_icons[3]  # Yellow for Uhmayya

        # Set faction names
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name

        # Set team alliances: Affrancia (1) and Nordia (2) are allied against the player
        # Each player_teams entry indicates which "team" they belong to
        gs.player_teams[0] = 0  # Player on own team
        gs.player_teams[1] = 1  # Affrancia and Nordia share team 1
        gs.player_teams[2] = 1
        gs.player_teams[3] = 3  # Uhmayya starts independent

        # Set starting gold
        gs.player_gold[0] = 500
        gs.player_gold[1] = 300
        gs.player_gold[2] = 200
        gs.player_gold[3] = 300

        # Configure specified territories
        for territory, config in TERRITORY_SETUP.items():
            owner = config["owner"]
            gs.territory_owners[territory] = owner

            if territory not in gs.buildings:
                gs.buildings[territory] = {}
            for plot_idx, building_type in config.get("buildings", {}).items():
                gs.buildings[territory][plot_idx] = building_type

            units = config.get("units", [])
            unmoved = len(units)
            gs.set_garrison_armies(territory, owner, unmoved=unmoved, moved=0, units=units)

        # Generate random units for remaining Nordia territories
        for territory in NORDIA_RANDOM_TERRITORIES:
            gs.territory_owners[territory] = 2  # Nordia
            if territory not in gs.buildings:
                gs.buildings[territory] = {}
            # Random 0-3 units
            num_units = random.randint(0, 3)
            units = []
            for i in range(num_units):
                unit_type = random.choice(RANDOM_UNIT_TYPES)
                units.append({"type": unit_type, "id": i, "status": "ready", "order": None, "xp": 0, "level": 0})
            gs.set_garrison_armies(territory, 2, unmoved=num_units, moved=0, units=units)

        # Set starting territories
        gs.player_starting_territories[0] = "Zjoal Islands"
        gs.player_starting_territories[1] = "Free Cities"
        gs.player_starting_territories[2] = "Damlére"
        gs.player_starting_territories[3] = "Ahtep"

        logger.info("Initial state configured with 35 territories")

    def _assign_starting_hero(self):
        """Pre-assign Serthus Diarcess to the player."""
        gs = self.game_state
        hero_name = "Serthus Diarcess"

        # Add Serthus to player's heroes
        if 0 not in gs.heroes:
            gs.heroes[0] = {}
        gs.heroes[0][hero_name] = {
            'keep_territory': 'Zjoal Islands',
            'keep_plot': 0  # Keep is at plot 0
        }

        # Track ownership
        if 0 not in gs.hero_ownership:
            gs.hero_ownership[0] = set()
        gs.hero_ownership[0].add(hero_name)

        logger.info(f"Assigned {hero_name} to player in Zjoal Islands")

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
            self._start_zoom_animation(param)
            self.intro_waiting_for_pan = True
            if text:
                self._show_transmission(text)
                # Play voice line for this intro step
                voice_key = INTRO_STEP_TO_VOICE.get(self.intro_step_index)
                if voice_key:
                    play_transmission_sound(voice_key)

        elif action == "wait":
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
            self.timer_visible = True
            self.intro_timer = 0.0
            import time
            # Use monotonic clock: immune to NTP/DST adjustments
            self.timer_highlight_start_time = time.monotonic()
            if text:
                self._show_transmission(text)
                # Play voice line for this intro step
                voice_key = INTRO_STEP_TO_VOICE.get(self.intro_step_index)
                if voice_key:
                    play_transmission_sound(voice_key)

        elif action == "pan_to":
            # Pan camera — hide text and stop voice during pan
            self._start_pan_animation(param)
            self.intro_waiting_for_pan = True
            self.transmission_overlay = None
            stop_transmission_sound()

        elif action == "start_game":
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
            duration=1.5,
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
        stop_transmission_sound()  # Stop any lingering intro voice

        self.game_state.turn_timer_enabled = True
        # Use monotonic clock: immune to NTP/DST adjustments
        self.game_state.planning_phase_start_time = time.monotonic()

    def _show_transmission(self, text, speaker="Serthus Diarcess"):
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

    def _queue_transmission(self, text, duration, voice_key=None, speaker="Serthus Diarcess"):
        """Queue a transmission to show during gameplay. Supports multiple queued messages.
        voice_key: optional sound key (e.g. "M3T8") to play when transmission starts.
        """
        self.transmission_queue.append((text, duration, voice_key, speaker))

    def _start_pending_transmission(self):
        """Start showing the next queued transmission. Plays voice if key provided."""
        if self.transmission_queue:
            text, duration, voice_key, speaker = self.transmission_queue.pop(0)
            self._show_transmission(text, speaker=speaker)
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

        delta_time = min(delta_time, 0.05)

        # Camera animation
        if self.camera_animation and self.camera_animation.active:
            still_active = self.camera_animation.update(delta_time)
            if not still_active and self.intro_waiting_for_pan:
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

        # Intro timing
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

        # Process deferred defector spawns (must happen after battle resolution completes)
        # Transmission queued once here even if multiple territories spawn defectors this turn
        if self.pending_defector_spawns:
            captured_before = len(self.affrancia_captured)
            for territory in self.pending_defector_spawns:
                self._spawn_defectors(territory)
            self.pending_defector_spawns.clear()
            # Only show transmission if at least one defector group actually spawned
            if len(self.affrancia_captured) > captured_before:
                self._queue_transmission("More dissatisfied Affrancians have joined us!", 3.0, voice_key="M3T12")

        # Gameplay transmission timer — must run before victory/defeat checks
        # so that pending victory/defeat transmissions can expire and transition to animation
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
                # All clear — now fire the victory transmission and sequence
                self._victory_waiting = False
                self.game_frozen = True
                self.game_paused = True
                self._clear_hover_tooltips()

                text = "Total victory! The western lands bow to our might! The Empire grows ever stronger!"
                self._show_transmission(text)
                self.transmission_duration = 6.0
                self.transmission_timer = 0.0
                self._pending_victory = True
                # Play victory voice line
                from global_sound import play_transmission_sound
                play_transmission_sound("M3T16")

        # Deferred defeat: same pattern — wait for battles/popups, then show defeat
        if self._defeat_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.transmission_queue:
                self._defeat_waiting = False
                self.game_frozen = True
                self.game_paused = True
                self._clear_hover_tooltips()

                text = "Zjoal Islands has fallen! Serthus is lost! Our campaign ends in ruin..."
                self._show_transmission(text, speaker="Thunder Priest")
                self.transmission_duration = 5.0
                self.transmission_timer = 0.0
                self._pending_defeat = True
                # Play defeat voice line
                from global_sound import play_transmission_sound
                play_transmission_sound("M3T17")

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

    # ========================================================================
    # AI TURN HANDLING
    # ========================================================================

    def update_ai_turn(self, delta_time):
        """Handle AI turn timing. Returns True if AI turn is being managed.

        Campaign AI turns are fast (0.5s) with no turn announcement animation.
        """
        if not self.active or self.intro_active:
            return False

        current_player = self.game_state.current_player
        if current_player == 0:
            return False

        gs = self.game_state

        # Skip defeated factions instantly
        if self.faction_defeated.get(current_player, False):
            logger.debug(f"Skipping turn for defeated faction {current_player}")
            gs.next_player()
            return True

        # Wait for movement animations to complete
        if gs.turn_phase == 'execution':
            return True

        # Auto-resolve battles instantly
        if gs.turn_phase == 'battles' and gs.pending_battles:
            self._auto_resolve_battles()
            return True

        # Brief 0.5s delay so the player can see AI actions before turn advances
        self.ai_turn_timer += delta_time
        if self.ai_turn_timer >= 0.5:
            self.ai_turn_timer = 0.0
            gs.next_player()

        return True

    def _auto_resolve_battles(self):
        """Auto-resolve all pending battles during AI turn."""
        gs = self.game_state
        if not gs.pending_battles:
            return

        num_battles = len(gs.pending_battles)
        logger.debug(f"Auto-resolving {num_battles} battle(s)")

        for battle_idx in range(num_battles - 1, -1, -1):
            if battle_idx < len(gs.pending_battles):
                battle = gs.pending_battles[battle_idx]
                territory_name = getattr(battle, 'territory', 'Unknown')
                logger.debug(f"Resolving battle in {territory_name}")
                gs.resolve_battle(battle_idx)

    def execute_ai_turn_override(self):
        """Called instead of normal AI execution. Handles all AI factions with restrictions."""
        current_player = self.game_state.current_player
        if current_player == 0:
            return

        # Check if faction is allied with player (Uhmayya after alliance)
        if self.alliance_formed and not self.betrayal_triggered and current_player == 3:
            # Uhmayya is allied - use standard AI but with restrictions
            self._execute_allied_ai(current_player)
            return

        # Execute faction-specific AI
        if current_player == 1:  # Kingdom of Affrancia
            self.affrancia_turn_count += 1
            if self.affrancia_turn_count <= 4:
                # Early game: alternating attacks + single-source restriction
                self._execute_affrancia_ai(current_player)
            else:
                # After 4 turns: full active AI, no restrictions
                self._execute_active_ai(current_player)
        elif current_player == 2:  # Warlords of Nordia (semi-dormant)
            self._execute_nordia_ai(current_player)
        elif current_player == 3:  # Uhmayyan Empiurate (semi-dormant or hostile)
            self._execute_uhmayya_ai(current_player)

    def _get_enemy_players(self, player_id):
        """Determine which factions this player should attack."""
        enemy_players = [0]  # Player is always enemy to all AI

        # Affrancia (1) and Nordia (2) are always allied with each other
        # They only fight the human player, and Uhmayya once Uhmayya allies with player
        if player_id == 1:
            # Affrancia: also fights Uhmayya after Uhmayya joins the player
            if not self.faction_defeated.get(3, False):
                if self.alliance_formed and not self.betrayal_triggered:
                    enemy_players.append(3)
        elif player_id == 2:
            # Nordia: also fights Uhmayya after Uhmayya joins the player
            if not self.faction_defeated.get(3, False):
                if self.alliance_formed and not self.betrayal_triggered:
                    enemy_players.append(3)
        elif player_id == 3:
            if self.alliance_formed and not self.betrayal_triggered:
                # Allied Uhmayya: don't attack the player (remove 0 from enemies)
                enemy_players = []
                # Focus on Nordia; ignore Affrancia while Affrancia is still active
                # (avoids splitting forces across two fronts)
                if not self.faction_defeated.get(1, False):
                    # Affrancia alive — only fight Nordia
                    if not self.faction_defeated.get(2, False):
                        enemy_players.append(2)
                else:
                    # Affrancia eliminated — fight Nordia too
                    if not self.faction_defeated.get(2, False):
                        enemy_players.append(2)
            else:
                # Hostile Uhmayya (after betrayal): enemies are player 0, Affrancia, Nordia
                if not self.faction_defeated.get(1, False):
                    enemy_players.append(1)
                if not self.faction_defeated.get(2, False):
                    enemy_players.append(2)

        return enemy_players

    def _execute_affrancia_ai(self, player_id):
        """Execute Affrancia AI with alternating attack/consolidate turns.

        Builds and trains every turn, but only attacks on odd turns (1, 3, 5...).
        Even turns are "consolidation" turns - forces regroup.
        Only used for Affrancia's first 4 turns; after that, normal _execute_active_ai.
        """
        gs = self.game_state

        my_territories = [t for t in MISSION_3_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        # Always: build structures and train units
        for territory in my_territories:
            self._ai_build_structures(player_id, territory)
            buildings = gs.buildings.get(territory, {})
            for plot_idx, building in buildings.items():
                if building == 'Barracks':
                    if gs.player_gold[player_id] >= 15:
                        unit_type = random.choice(["Swordsman", "Pikeman", "Archer"])
                        gs.start_training(territory, plot_idx, unit_type)

        # Only attack/reinforce on odd turns (1, 3, 5...)
        # Affrancia restriction: only one source territory can attack each target
        if self.affrancia_turn_count % 2 == 1:
            enemy_players = self._get_enemy_players(player_id)
            targets_attacked = set()

            for territory in my_territories:
                garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
                units = garrison.get('units', [])
                ready_units = [u for u in units if u.get('status') == 'ready']
                unmoved_count = len(ready_units)

                max_moveable = max(unmoved_count // 2, min(unmoved_count, 1))
                if max_moveable < 1:
                    continue

                neighbors = map_data.get_neighbors(territory)
                neighbors = [n for n in neighbors if n in MISSION_3_TERRITORIES]

                # Attack first enemy neighbor not already being attacked
                attacked = False
                for neighbor in neighbors:
                    neighbor_owner = gs.territory_owners.get(neighbor)
                    if neighbor_owner in enemy_players and neighbor not in targets_attacked:
                        unit_ids = [u['id'] for u in ready_units][:max_moveable]
                        gs.add_movement_order_for_units(territory, neighbor, unit_ids, player=player_id)
                        targets_attacked.add(neighbor)
                        attacked = True
                        break

                # Reinforce if no attack opportunity
                if not attacked:
                    for neighbor in neighbors:
                        neighbor_owner = gs.territory_owners.get(neighbor)
                        if neighbor_owner == player_id:
                            neighbor_neighbors = map_data.get_neighbors(neighbor)
                            has_enemy_border = any(
                                gs.territory_owners.get(nn) in enemy_players
                                for nn in neighbor_neighbors if nn in MISSION_3_TERRITORIES
                            )
                            if has_enemy_border:
                                unit_ids = [u['id'] for u in ready_units][:max_moveable]
                                gs.add_movement_order_for_units(territory, neighbor, unit_ids, player=player_id)
                                break

    def _execute_active_ai(self, player_id):
        """Execute AI for active factions (Affrancia, awakened Nordia/Uhmayya).

        Reckless campaign AI: attacks every reachable enemy neighbor, reinforces
        frontlines, still respects half-unit movement restriction.
        """
        gs = self.game_state

        my_territories = [t for t in MISSION_3_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return

        # Determine enemies based on faction alliances
        enemy_players = self._get_enemy_players(player_id)

        for territory in my_territories:
            # Build structures on empty plots
            self._ai_build_structures(player_id, territory)

            # Train units at barracks (AI restriction: no heroes)
            buildings = gs.buildings.get(territory, {})
            for plot_idx, building in buildings.items():
                if building == 'Barracks':
                    if gs.player_gold[player_id] >= 15:
                        unit_type = random.choice(["Swordsman", "Pikeman", "Archer"])
                        gs.start_training(territory, plot_idx, unit_type)

            # Reckless AI: attack or reinforce with half-unit restriction
            garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
            units = garrison.get('units', [])
            ready_units = [u for u in units if u.get('status') == 'ready']
            unmoved_count = len(ready_units)

            # AI restriction: can only move HALF of units (minimum 1)
            max_moveable = max(unmoved_count // 2, min(unmoved_count, 1))
            if max_moveable < 1:
                continue

            neighbors = map_data.get_neighbors(territory)
            # Filter to only mission territories
            neighbors = [n for n in neighbors if n in MISSION_3_TERRITORIES]

            # Reckless: attack the first enemy neighbor found
            attacked = False
            for neighbor in neighbors:
                neighbor_owner = gs.territory_owners.get(neighbor)
                if neighbor_owner in enemy_players:
                    unit_ids = [u['id'] for u in ready_units][:max_moveable]
                    gs.add_movement_order_for_units(territory, neighbor, unit_ids, player=player_id)
                    logger.debug(f"AI {player_id}: attacking {neighbor} from {territory} with {max_moveable} units")
                    attacked = True
                    break

            # If no enemy neighbor, reinforce a friendly territory that borders an enemy
            if not attacked and max_moveable >= 1:
                for neighbor in neighbors:
                    neighbor_owner = gs.territory_owners.get(neighbor)
                    if neighbor_owner == player_id:
                        # Check if this neighbor borders an enemy
                        neighbor_neighbors = map_data.get_neighbors(neighbor)
                        has_enemy_border = any(
                            gs.territory_owners.get(nn) in enemy_players
                            for nn in neighbor_neighbors if nn in MISSION_3_TERRITORIES
                        )
                        if has_enemy_border:
                            unit_ids = [u['id'] for u in ready_units][:max_moveable]
                            gs.add_movement_order_for_units(territory, neighbor, unit_ids, player=player_id)
                            logger.debug(f"AI {player_id}: reinforcing {neighbor} from {territory}")
                            break

    def _get_empty_plot(self, territory, gs):
        """Find the first empty plot in a territory (not built, not under construction)."""
        buildings = gs.buildings.get(territory, {})
        under_construction = gs.under_construction.get(territory, {})
        plots = map_data.get_plots(territory)
        for plot_idx in range(len(plots)):
            if plot_idx not in buildings and plot_idx not in under_construction:
                return plot_idx
        return None

    def _ai_build_structures(self, player_id, territory):
        """Smart building logic for campaign AI. Fills empty plots with useful structures.

        Priority: Barracks (troops), Farm/Mine (economy), Keep (border defense), Square (boost).
        """
        gs = self.game_state
        buildings = gs.buildings.get(territory, {})
        under_construction = gs.under_construction.get(territory, {})
        gold = gs.player_gold[player_id]

        # One build per territory per turn
        if territory in gs.buildings_started_this_turn:
            return

        empty_plot = self._get_empty_plot(territory, gs)
        if empty_plot is None:
            return

        # Collect all built + under-construction types
        all_types = list(buildings.values())
        all_types.extend(btype for btype, _ in under_construction.values())

        has_barracks = 'Barracks' in all_types
        has_farm = 'Farm' in all_types
        has_mine = 'Mine' in all_types
        has_keep = 'Keep' in all_types
        has_square = 'Square' in all_types

        # Priority 1: Barracks if none (need troops)
        if not has_barracks and gold >= 50:
            gs.start_construction(territory, empty_plot, 'Barracks')
            return

        # Priority 2: Farm for income
        if not has_farm and gold >= 30:
            gs.start_construction(territory, empty_plot, 'Farm')
            return

        # Priority 3: Mine for income
        if not has_mine and gold >= 40:
            gs.start_construction(territory, empty_plot, 'Mine')
            return

        # Priority 4: Keep on border territories for defense
        if not has_keep and gold >= 100:
            neighbors = map_data.get_neighbors(territory)
            enemy_players = self._get_enemy_players(player_id)
            is_border = any(
                gs.territory_owners.get(n) in enemy_players
                for n in neighbors if n in MISSION_3_TERRITORIES
            )
            if is_border:
                gs.start_construction(territory, empty_plot, 'Keep')
                return

        # Priority 5: Square for income multiplier
        if not has_square and gold >= 60:
            gs.start_construction(territory, empty_plot, 'Square')
            return

        # Priority 6: Second barracks if everything else built
        if gold >= 50:
            gs.start_construction(territory, empty_plot, 'Barracks')

    def _execute_nordia_ai(self, player_id):
        """Execute AI for Warlords of Nordia (semi-dormant or awakened)."""
        gs = self.game_state

        my_territories = [t for t in MISSION_3_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return

        # Semi-dormant: can build and train (max 6 units per territory), cannot move
        for territory in my_territories:
            # Build structures on empty plots (Barracks, Farms, Mines, etc.)
            self._ai_build_structures(player_id, territory)

            # Train units at barracks (max 6 per territory while semi-dormant)
            buildings = gs.buildings.get(territory, {})
            garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
            units = garrison.get('units', [])
            current_unit_count = len(units)

            if current_unit_count < 6:
                for plot_idx, building in buildings.items():
                    if building == 'Barracks':
                        if gs.player_gold[player_id] >= 15:
                            unit_type = random.choice(["Swordsman", "Pikeman"])
                            gs.start_training(territory, plot_idx, unit_type)

        # If awakened, can also move units
        if self.nordia_awakened:
            self._execute_active_ai(player_id)

    def _execute_uhmayya_ai(self, player_id):
        """Execute AI for Uhmayyan Empiurate (semi-dormant, allied, or hostile)."""
        if not self.faction_awakened.get(3, False):
            # Semi-dormant: just build and train
            self._execute_semi_dormant_build(player_id)
            return

        # Awakened (hostile): full AI with restrictions
        self._execute_active_ai(player_id)

    def _execute_allied_ai(self, player_id):
        """Execute AI for allied Uhmayya (fights other AI factions). Reckless style."""
        gs = self.game_state

        my_territories = [t for t in MISSION_3_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return

        # Allied Uhmayya: focus on Nordia, ignore Affrancia while it's still active
        enemy_players = self._get_enemy_players(player_id)

        for territory in my_territories:
            # Build structures on empty plots
            self._ai_build_structures(player_id, territory)

            # Train units
            buildings = gs.buildings.get(territory, {})
            for plot_idx, building in buildings.items():
                if building == 'Barracks':
                    if gs.player_gold[player_id] >= 15:
                        gs.start_training(territory, plot_idx, 'Cavalry')

            # Reckless: attack enemies with half-unit restriction (min 1)
            garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
            units = garrison.get('units', [])
            ready_units = [u for u in units if u.get('status') == 'ready']
            unmoved_count = len(ready_units)

            max_moveable = max(unmoved_count // 2, min(unmoved_count, 1))
            if max_moveable < 1:
                continue

            neighbors = map_data.get_neighbors(territory)
            neighbors = [n for n in neighbors if n in MISSION_3_TERRITORIES]

            attacked = False
            for neighbor in neighbors:
                neighbor_owner = gs.territory_owners.get(neighbor)
                if neighbor_owner in enemy_players:
                    unit_ids = [u['id'] for u in ready_units][:max_moveable]
                    gs.add_movement_order_for_units(territory, neighbor, unit_ids, player=player_id)
                    logger.debug(f"Allied Uhmayya: attacking {neighbor} from {territory}")
                    attacked = True
                    break

            # Reinforce frontline if no enemy neighbor
            if not attacked and max_moveable >= 1:
                for neighbor in neighbors:
                    neighbor_owner = gs.territory_owners.get(neighbor)
                    if neighbor_owner == player_id:
                        neighbor_neighbors = map_data.get_neighbors(neighbor)
                        has_enemy_border = any(
                            gs.territory_owners.get(nn) in enemy_players
                            for nn in neighbor_neighbors if nn in MISSION_3_TERRITORIES
                        )
                        if has_enemy_border:
                            unit_ids = [u['id'] for u in ready_units][:max_moveable]
                            gs.add_movement_order_for_units(territory, neighbor, unit_ids, player=player_id)
                            logger.debug(f"Allied Uhmayya: reinforcing {neighbor} from {territory}")
                            break

    def _execute_semi_dormant_build(self, player_id):
        """Execute building/training for semi-dormant AI (no movement)."""
        gs = self.game_state

        my_territories = [t for t in MISSION_3_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        for territory in my_territories:
            # Build structures on empty plots
            self._ai_build_structures(player_id, territory)

            # Train units at barracks (max 6 per territory while semi-dormant)
            garrison = gs.territory_garrisons.get(territory, {}).get(player_id, {})
            units = garrison.get('units', [])
            current_unit_count = len(units)

            if current_unit_count < 6:
                buildings = gs.buildings.get(territory, {})
                for plot_idx, building in buildings.items():
                    if building == 'Barracks':
                        if gs.player_gold[player_id] >= 15:
                            gs.start_training(territory, plot_idx, random.choice(["Cavalry", "Archer"]))

    # ========================================================================
    # AI BLOCKING PROPERTY
    # ========================================================================

    @property
    def block_ai(self):
        """Return True if AI should be blocked for the current player."""
        if self.intro_active:
            return True

        current_player = self.game_state.current_player
        if current_player == 0:
            return False

        # Block normal AI for ALL AI factions - Mission3 controls their behavior
        return True

    # ========================================================================
    # ACTION GATING (Only Serthus available - no other hero training)
    # ========================================================================

    def is_action_allowed(self, action_type, **kwargs):
        """Check if a player action is permitted. Only Serthus is available as hero."""
        if not self.active:
            return True

        if self.intro_active or self.victory_sequence_active or self.defeat_sequence_active:
            return False

        if self.game_paused:
            return False

        # Block training ANY hero (Serthus is pre-assigned, others don't fit timeline)
        if action_type == 'train_hero':
            return False

        return True

    def should_button_be_locked(self, button_id):
        """Check if a specific button should be locked."""
        if not self.active:
            return False

        return False

    def is_button_locked(self, button_id):
        return self.should_button_be_locked(button_id)

    def should_highlight_button(self, button_id):
        return False

    def get_ai_thinking_text(self):
        """Override AI thinking indicator to show unified 'Enemies thinking...' text."""
        return ("Enemies thinking...", "")

    def should_hide_heroes_tab(self):
        """Heroes tab is NOT hidden in Mission 3."""
        return False

    def is_timer_visible(self):
        if self.intro_active:
            return self.timer_visible
        return True

    def should_highlight_timer(self):
        import time
        if self.timer_highlight_start_time is not None:
            # Use monotonic clock: immune to NTP/DST adjustments
            elapsed = time.monotonic() - self.timer_highlight_start_time
            if elapsed < self.timer_highlight_duration:
                return int(elapsed * 2) % 2 == 0
        return False

    # ========================================================================
    # EVENT NOTIFICATIONS
    # ========================================================================

    def notify_event(self, event_type, **kwargs):
        """Receive gameplay events from hooked game systems."""
        if not self.active or self.intro_active:
            return

        if event_type == 'order_created':
            from_territory = kwargs.get('from_territory')
            to_territory = kwargs.get('to_territory')
            player = kwargs.get('player', 0)

            if player == 0:
                self._check_attack_triggers(to_territory)

        elif event_type == 'territory_conquered':
            territory = kwargs.get('territory')
            new_owner = kwargs.get('new_owner')
            self._on_territory_conquered(territory, new_owner)

        elif event_type == 'turn_announcement_done' and kwargs.get('player_index') == 0:
            # Fired at start of player 0's turn - check if we've expanded enough
            self._check_territory_count_awakening()

    def _check_attack_triggers(self, target_territory):
        """Check if attacking a territory triggers awakening or alliance."""
        # Check if attacking Nordia territory (awakens Nordia and Uhmayya)
        if target_territory in FACTION_TERRITORIES[2]:  # Nordia territory
            if not self.nordia_awakened:
                self._awaken_nordia('attack')
            if not self.faction_awakened.get(3, False):
                self._awaken_uhmayya('nordia_attacked')

        # Safety: moving toward Uhmayya territory auto-forms alliance
        if target_territory in FACTION_TERRITORIES[3]:
            if not self.alliance_formed:
                self._form_alliance()

    def _check_territory_count_awakening(self):
        """Check if player has 4+ territories (awakens Nordia)."""
        if self.nordia_awakened:
            return

        gs = self.game_state
        player_territories = sum(
            1 for t in MISSION_3_TERRITORIES
            if gs.territory_owners.get(t) == 0
        )

        if player_territories >= 4:
            self._awaken_nordia('territory_count')

    def _awaken_nordia(self, reason):
        """Fully awaken Warlords of Nordia (can now move units)."""
        if self.nordia_awakened:
            return

        self.nordia_awakened = True
        logger.info(f"Nordia awakened due to: {reason}")

        if reason == 'territory_count':
            text = "The Warlords of Nordia have taken notice of our expansion! They march to war!"
            self._queue_transmission(text, 7.0, voice_key="M3T8")
        else:
            text = "Our attack on Nordia has united the warlords! They strike back!"
            self._queue_transmission(text, 5.0, voice_key="M3T9")

    def _awaken_uhmayya(self, reason):
        """Awaken Uhmayyan Empiurate and form alliance with player.

        Uhmayya always joins as an ally when awakened — regardless of trigger.
        They only turn hostile later via betrayal.
        """
        if self.faction_awakened.get(3, False):
            return

        self.faction_awakened[3] = True
        logger.info(f"Uhmayya awakened due to: {reason}")

        # Auto-form alliance when Uhmayya awakens (they join the player's side)
        if not self.alliance_formed:
            self._form_alliance()

        if reason == 'nordia_attacked':
            text = "The Uhmayyan Empiurate senses opportunity in our conflict with Nordia — they offer an alliance!"
            self._queue_transmission(text, 8.0, voice_key="M3T10")
        elif reason == 'affrancia_eliminated':
            text = "With Affrancia fallen, the Uhmayyan Empiurate offers an alliance!"
            self._queue_transmission(text, 5.0, voice_key="M3T11")
        else:
            return  # Alliance formed via _form_alliance which has its own transmission

    def _spawn_defectors(self, territory):
        """Spawn defector units when player captures an Affrancia territory for the first time.

        Spawns 1 Swordsman, 1 Pikeman, 1 Archer, 1 Cavalry in the captured territory.
        If that would exceed 15 units, tries Zjoal Islands, then any player territory.
        """
        if territory in self.affrancia_captured:
            return  # Already captured before, no defectors on re-conquest
        self.affrancia_captured.add(territory)

        gs = self.game_state
        defector_types = ["Swordsman", "Pikeman", "Archer", "Cavalry"]
        num_defectors = len(defector_types)

        # Find a territory to place the defectors (garrison must stay under 15)
        def get_unit_count(t):
            garrison = gs.territory_garrisons.get(t, {}).get(0, {})
            return len(garrison.get('units', []))

        spawn_territory = None

        # Priority 1: the captured territory itself
        if get_unit_count(territory) + num_defectors <= 15:
            spawn_territory = territory
        # Priority 2: Zjoal Islands (home base)
        elif get_unit_count(PLAYER_CAPITAL) + num_defectors <= 15:
            spawn_territory = PLAYER_CAPITAL
        # Priority 3: any other player territory
        else:
            for t in MISSION_3_TERRITORIES:
                if gs.territory_owners.get(t) == 0 and get_unit_count(t) + num_defectors <= 15:
                    spawn_territory = t
                    break

        if spawn_territory is None:
            return  # All territories full, no spawn, no transmission

        # Create the defector units
        garrison = gs.territory_garrisons.get(spawn_territory, {}).get(0, {})
        existing_units = garrison.get('units', [])
        next_id = max((u['id'] for u in existing_units), default=-1) + 1

        units = []
        for i, unit_type in enumerate(defector_types):
            units.append({
                'id': next_id + i,
                'type': unit_type,
                'status': 'ready',
                'order': None,
                'xp': 0,
                'level': 0,
            })

        gs.add_garrison(spawn_territory, 0, unmoved=num_defectors, moved=0, units=units)
        logger.info(f"Defectors spawned in {spawn_territory}: {defector_types}")

    def _on_territory_conquered(self, territory, new_owner):
        """Handle territory conquest - check alliance, betrayal, victory, defeat."""
        gs = self.game_state

        # Check defeat condition: player lost Zjoal Islands
        if territory == PLAYER_CAPITAL and new_owner != 0:
            self._start_defeat()
            return

        # Affrancian defectors: defer spawn until after battle resolution completes
        # (resolve_battle overwrites garrisons AFTER this event fires)
        if new_owner == 0 and territory in FACTION_TERRITORIES[1]:
            if territory not in self.affrancia_captured:
                self.pending_defector_spawns.append(territory)

        # Check alliance trigger: player captured Orhas
        if territory == ALLIANCE_TRIGGER_TERRITORY and new_owner == 0:
            if not self.alliance_formed:
                self._form_alliance()

        # Bonus "Storming Nordia" disqualification: if Affrancia drops below 5 territories
        # while Nordia is still alive, permanently disqualify the bonus achievement
        if not self._storming_nordia_disqualified and not self.faction_defeated.get(2, False):
            affrancia_count = sum(
                1 for t in MISSION_3_TERRITORIES
                if gs.territory_owners.get(t) == 1
            )
            if affrancia_count < 5:
                self._storming_nordia_disqualified = True
                logger.info(f"Storming Nordia disqualified: Affrancia dropped to {affrancia_count} territories while Nordia alive")

        # Check faction elimination
        for faction_id in [1, 2, 3]:
            if faction_id == 0:
                continue
            if self.faction_defeated[faction_id]:
                continue

            faction_alive = any(
                gs.territory_owners.get(t) == faction_id
                for t in FACTION_TERRITORIES[faction_id]
            )

            # Also check if faction owns ANY territory (they might have conquered outside starting area)
            if not faction_alive:
                faction_alive = any(
                    gs.territory_owners.get(t) == faction_id
                    for t in MISSION_3_TERRITORIES
                )

            if not faction_alive:
                self._on_faction_defeated(faction_id)

    def _form_alliance(self):
        """Form alliance with Uhmayyan Empiurate."""
        if self.alliance_formed:
            return

        self.alliance_formed = True
        self.faction_awakened[3] = True  # Ensure awakened

        # Switch Uhmayya to player's team
        self.game_state.player_teams[3] = 0
        logger.info("Alliance formed! Uhmayya joins player's team")

        text = "We have received a message from the Uhmayyans - they want to join us in an alliance!"
        self._queue_transmission(text, 7.0, voice_key="M3T13")

    def _trigger_betrayal(self):
        """Uhmayyan Empiurate betrays the player."""
        if self.betrayal_triggered:
            return

        self.betrayal_triggered = True

        # Switch Uhmayya back to enemy
        self.game_state.player_teams[3] = 3
        logger.info("Betrayal! Uhmayya turns hostile!")

        # Kill all player units stationed in Uhmayya-owned territories
        self._purge_player_units_in_uhmayya()

        # Add new quest
        self.quest_log.append({'text': 'Defeat the Uhmayyan Empiurate', 'completed': False})

        text = "And now.. for the Uhmayyans. They have served their purpose. This ends now. Condolences to our units in their lands.. they served well."
        self._queue_transmission(text, 14.0, voice_key="M3T14")

    def _purge_player_units_in_uhmayya(self):
        """Remove all player garrisons from Uhmayya-owned territories on betrayal."""
        gs = self.game_state
        purged_total = 0

        for territory in MISSION_3_TERRITORIES:
            if gs.territory_owners.get(territory) != 3:
                continue  # Only Uhmayya-owned territories

            # Check if player has a garrison here (allied garrison from alliance period)
            if territory in gs.territory_garrisons and 0 in gs.territory_garrisons[territory]:
                garrison = gs.territory_garrisons[territory][0]
                unit_count = len(garrison.get('units', []))
                if unit_count > 0:
                    purged_total += unit_count
                    logger.debug(f"{unit_count} player unit(s) killed in {territory}")

                # Remove player garrison entirely
                del gs.territory_garrisons[territory][0]
                gs.sync_legacy_garrison_data(territory)

        if purged_total > 0:
            gs.add_message(f"The Uhmayyans slaughtered {purged_total} of our troops stationed in their lands!")
            logger.debug(f"Total player units purged: {purged_total}")
        else:
            logger.warning("No player units were in Uhmayya territory")

    def _on_faction_defeated(self, faction_id):
        """Handle faction defeat."""
        if self.faction_defeated.get(faction_id, False):
            return

        self.faction_defeated[faction_id] = True
        logger.info(f"Faction {faction_id} defeated!")

        # Bonus achievement check: "Storming Nordia"
        # When Nordia (faction 2) is defeated, grant bonus only if Affrancia never dropped below 5
        # territories at any point while Nordia was alive (tracked by _storming_nordia_disqualified)
        if faction_id == 2:
            affrancia_territory_count = sum(
                1 for t in MISSION_3_TERRITORIES
                if self.game_state.territory_owners.get(t) == 1
            )
            if self._storming_nordia_disqualified:
                logger.info(f"Bonus condition not met: Affrancia dropped below 5 territories at some point during the mission")
            elif affrancia_territory_count >= 5:
                self.bonus_storming_nordia = True
                logger.info(f"Bonus condition met: Storming Nordia (Affrancia has {affrancia_territory_count} territories, never dropped below 5)")
            else:
                logger.info(f"Bonus condition not met: Affrancia only has {affrancia_territory_count} territories")

        # Mark quest complete
        quest_map = {
            1: 'Defeat the Kingdom of Affrancia',
            2: 'Defeat the Warlords of Nordia',
            3: 'Defeat the Uhmayyan Empiurate',
        }
        quest_text = quest_map.get(faction_id)
        if quest_text:
            for quest in self.quest_log:
                if quest['text'] == quest_text:
                    quest['completed'] = True
                    break

        # Check for betrayal trigger (Affrancia AND Nordia eliminated)
        if self.alliance_formed and not self.betrayal_triggered:
            if self.faction_defeated.get(1, False) and self.faction_defeated.get(2, False):
                self._trigger_betrayal()
                return  # Don't check victory yet

        # Check if Affrancia eliminated awakens Uhmayya
        if faction_id == 1 and not self.faction_awakened.get(3, False):
            self._awaken_uhmayya('affrancia_eliminated')

        # Show defeat transmission with faction-specific voice line
        faction_names = {1: "Kingdom of Affrancia", 2: "Warlords of Nordia", 3: "Uhmayyan Empiurate"}
        faction_voice = {1: "M3T15a", 2: "M3T15b", 3: "M3T15c"}
        text = f"The {faction_names[faction_id]} has been crushed!"
        self._queue_transmission(text, 3.0, voice_key=faction_voice.get(faction_id))

        # Check victory (all 3 factions eliminated)
        if all(self.faction_defeated.values()):
            self._start_victory()

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

    def get_bonus_conditions(self):
        """Return bonus condition flags for achievement system."""
        return {
            'campaign_mission_3_bonus': self.bonus_storming_nordia,
        }

    def _start_victory(self):
        """Start the victory sequence (deferred until battles/animations finish)."""
        if self.victory_sequence_active or self._pending_victory or self._victory_waiting:
            return

        logger.info("Victory condition met - waiting for battles/animations to finish")

        # Set game state for achievement tracking
        self.game_state.winner = 0
        self.game_state.phase = 'ended'

        # Mark survival quest as complete
        for quest in self.quest_log:
            if 'Serthus' in quest['text']:
                quest['completed'] = True
                break

        # Defer until battles and popups are closed (checked each frame in update)
        self._victory_waiting = True

    # ========================================================================
    # VICTORY/DEFEAT SEQUENCES
    # ========================================================================

    def _update_victory_sequence(self, delta_time):
        """Update victory sequence. Returns 'exit' when done."""
        # Wait for transmission to finish (timer is incremented by gameplay timer block in update())
        if self._pending_victory:
            if not self.transmission_overlay:
                # Transmission expired (cleared by gameplay timer) — start victory animation
                self._pending_victory = False
                self.victory_sequence_active = True
                self.victory_phase = 'fade'
                self.victory_timer = 0.0
                try:
                    self.victory_image = pygame.image.load('assets/victoryscrn.png').convert_alpha()
                except pygame.error:
                    self.victory_image = None
            return None

        if not self.victory_sequence_active:
            return None

        self.victory_timer += delta_time

        if self.victory_phase == 'fade':
            progress = min(self.victory_timer / 0.5, 1.0)
            self.victory_fade_alpha = int(255 * progress)
            if progress >= 1.0:
                self.victory_phase = 'image_grow'
                self.victory_timer = 0.0

        elif self.victory_phase == 'image_grow':
            progress = min(self.victory_timer / 0.3, 1.0)
            self.victory_image_scale = 0.75 * (1.0 - (1.0 - progress) ** 2)
            if progress >= 1.0:
                self.victory_phase = 'image_hold'
                self.victory_timer = 0.0

        elif self.victory_phase == 'image_hold':
            if self.victory_timer >= 5.0:
                return 'exit'

        return None

    def _update_defeat_sequence(self, delta_time):
        """Update defeat sequence. Returns 'exit' when done."""
        # Wait for transmission to finish (timer is incremented by gameplay timer block in update())
        if self._pending_defeat:
            if not self.transmission_overlay:
                # Transmission expired (cleared by gameplay timer) — start defeat animation
                self._pending_defeat = False
                self.defeat_sequence_active = True
                self.defeat_phase = 'fade'
                self.defeat_timer = 0.0
                try:
                    self.defeat_image = pygame.image.load('assets/defeatscrn.png').convert_alpha()
                except pygame.error:
                    self.defeat_image = None
            return None

        if not self.defeat_sequence_active:
            return None

        self.defeat_timer += delta_time

        if self.defeat_phase == 'fade':
            progress = min(self.defeat_timer / 0.5, 1.0)
            self.defeat_fade_alpha = int(255 * progress)
            if progress >= 1.0:
                self.defeat_phase = 'image_grow'
                self.defeat_timer = 0.0

        elif self.defeat_phase == 'image_grow':
            progress = min(self.defeat_timer / 0.3, 1.0)
            self.defeat_image_scale = 0.75 * (1.0 - (1.0 - progress) ** 2)
            if progress >= 1.0:
                self.defeat_phase = 'image_hold'
                self.defeat_timer = 0.0

        elif self.defeat_phase == 'image_hold':
            if self.defeat_timer >= 5.0:
                return 'exit'

        return None

    def _render_victory_sequence(self, screen):
        """Render victory sequence overlay."""
        if not self.victory_sequence_active:
            return

        screen_width, screen_height = screen.get_size()

        if self.victory_fade_alpha > 0:
            overlay = pygame.Surface((screen_width, screen_height))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(self.victory_fade_alpha)
            screen.blit(overlay, (0, 0))

        if self.victory_phase in ('image_grow', 'image_hold') and self.victory_image:
            img_width, img_height = self.victory_image.get_size()
            scale = max(0.01, self.victory_image_scale)
            scaled_width = int(img_width * scale)
            scaled_height = int(img_height * scale)

            if scaled_width > 0 and scaled_height > 0:
                scaled_img = pygame.transform.smoothscale(self.victory_image, (scaled_width, scaled_height))
                x = (screen_width - scaled_width) // 2
                y = (screen_height - scaled_height) // 2
                screen.blit(scaled_img, (x, y))

    def _render_defeat_sequence(self, screen):
        """Render defeat sequence overlay."""
        if not self.defeat_sequence_active:
            return

        screen_width, screen_height = screen.get_size()

        if self.defeat_fade_alpha > 0:
            overlay = pygame.Surface((screen_width, screen_height))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(self.defeat_fade_alpha)
            screen.blit(overlay, (0, 0))

        if self.defeat_phase in ('image_grow', 'image_hold') and self.defeat_image:
            img_width, img_height = self.defeat_image.get_size()
            scale = max(0.01, self.defeat_image_scale)
            scaled_width = int(img_width * scale)
            scaled_height = int(img_height * scale)

            if scaled_width > 0 and scaled_height > 0:
                scaled_img = pygame.transform.smoothscale(self.defeat_image, (scaled_width, scaled_height))
                x = (screen_width - scaled_width) // 2
                y = (screen_height - scaled_height) // 2
                screen.blit(scaled_img, (x, y))

    # ========================================================================
    # RENDER
    # ========================================================================

    def render(self, screen):
        """Called after normal game rendering to draw mission overlay."""
        if not self.active:
            return

        if self.victory_sequence_active or self._pending_victory:
            if self.victory_sequence_active:
                self._render_victory_sequence(screen)
            if self.transmission_overlay:
                self.transmission_overlay.render(screen)
            return

        if self.defeat_sequence_active or self._pending_defeat:
            if self.defeat_sequence_active:
                self._render_defeat_sequence(screen)
            if self.transmission_overlay:
                self.transmission_overlay.render(screen)
            return

        if self.transmission_overlay:
            self.transmission_overlay.render(screen)

    # ========================================================================
    # QUEST LOG
    # ========================================================================

    def get_quest_log(self):
        """Return the quest log list for rendering in the Quests tab."""
        return self.quest_log

    # ========================================================================
    # TERRITORY INTERACTION
    # ========================================================================

    def is_territory_interactive(self, territory_name):
        if not self.active:
            return True
        return territory_name in MISSION_3_TERRITORIES

    def get_adjacency_override(self, territory):
        return None

    def get_highlight_territory(self):
        return None

    def should_highlight_plot(self, territory, plot_index):
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

        if self.original_flag_icons and hasattr(self.main_game, 'army_flag_icons'):
            for i, flags in self.original_flag_icons.items():
                self.main_game.army_flag_icons[i] = flags

        self.active = False

    def deactivate(self):
        """Deactivate the mission (called on exit)."""
        self._cleanup()
