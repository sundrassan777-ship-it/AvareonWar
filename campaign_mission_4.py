# -*- coding: utf-8 -*-
# campaign_mission_4.py
# Campaign Mission 4: Domination
# Features custom hybrid AI (normal build/train, attack-player-only, ramp limit,
# defensive minimums), pre-assigned hero, and territory display name overrides.

import pygame
import map_data
from utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# MISSION CONFIGURATION
# ============================================================================

# All 21 territories enabled for this mission
MISSION_4_TERRITORIES = [
    # Human (Player 0)
    "Aelatania", "Duchy of Daurels", "Courtieux",
    # Eastern Kingdoms (Player 1)
    "Londia", "Northern Heilonia", "Révia", "Venexia", "The Holy Land",
    "Elletian Isles", "Lobardia", "Lentria", "Elland",
    # Confederation of the Leuse (Player 2)
    "Valeonia", "Velognia", "Leuse Valley", "Nordica",
    # Ahtep Empire (Player 3)
    "Amennia", "Sstep", "Daomea", "Ahtep", "Liadnon",
]

# Display name overrides for this mission
MISSION_4_DISPLAY_NAMES = {
    "Northern Heilonia": "Southern Londia",
    "Londia": "Northern Londia",
    "Révia": "Heilonic Kingdom of Entaron",
    "Venexia": "Car-Venex Union",
    "The Holy Land": "Neimer Coast",
    "Duchy of Daurels": "Kingdom of Daurels",
    "Elland": "Elletia",
}

# Faction territory ownership mapping
# Player 0 = Human (Blue), Player 1 = Eastern Kingdoms (Green)
# Player 2 = Confederation of the Leuse (Red), Player 3 = Ahtep Empire (Yellow)
FACTION_TERRITORIES = {
    0: ["Aelatania", "Duchy of Daurels", "Courtieux"],
    1: ["Londia", "Northern Heilonia", "Révia", "Venexia", "The Holy Land",
        "Elletian Isles", "Lobardia", "Lentria", "Elland"],
    2: ["Valeonia", "Velognia", "Leuse Valley", "Nordica"],
    3: ["Amennia", "Sstep", "Daomea", "Ahtep", "Liadnon"],
}

# Player colors: Blue, Green, Red, Yellow
PLAYER_COLORS = [
    (100, 150, 255),   # Player 0: Blue (human)
    (100, 200, 100),   # Player 1: Green (Eastern Kingdoms)
    (255, 100, 100),   # Player 2: Red (Confederation of the Leuse)
    (255, 220, 100),   # Player 3: Yellow (Ahtep Empire)
]

# Faction names
FACTION_NAMES = {
    0: None,  # Use player's profile name
    1: "Eastern Kingdoms",
    2: "Confederation of the Leuse",
    3: "Ahtep Empire",
}

# Starting gold per faction
STARTING_GOLD = {
    0: 800,
    1: 100,
    2: 250,
    3: 5000,
}

# Defensive minimums: min units AI keeps in territories adjacent to player 0
FACTION_DEFENSE_MIN = {
    1: 1,   # Eastern Kingdoms: at least 1 unit
    2: 3,   # Confederation: at least 3 units
    3: 5,   # Ahtep Empire: at least 5 units
}

# ============================================================================
# TERRITORY SETUP - Initial buildings and units
# ============================================================================

_global_unit_id = 0  # Global counter ensures unique IDs across all territories

def _make_unit(unit_type, unit_id, level=0):
    """Helper to create a unit dict."""
    return {"type": unit_type, "id": unit_id, "status": "ready", "order": None, "xp": 0, "level": level}

def _make_units(composition, level=0):
    """Create a list of unit dicts from a composition list of (type, count) tuples.

    Uses a global counter so unit IDs are unique across all territories,
    preventing selection/status collisions for same-player units.
    """
    global _global_unit_id
    units = []
    for unit_type, count in composition:
        for _ in range(count):
            units.append(_make_unit(unit_type, _global_unit_id, level))
            _global_unit_id += 1
    return units

TERRITORY_SETUP = {
    # ========== HUMAN (Player 0) — ALL UNITS LEVEL 2 ==========
    "Aelatania": {
        "owner": 0,
        "buildings": {0: "Barracks", 1: "Keep"},
        "units": _make_units([("Pikeman", 2), ("Swordsman", 2), ("Archer", 1)], level=2),
    },
    "Duchy of Daurels": {
        "owner": 0,
        "buildings": {0: "Keep", 1: "Mine"},
        "units": _make_units([("Archer", 3), ("Cavalry", 2), ("Swordsman", 1)], level=2),
    },
    "Courtieux": {
        "owner": 0,
        "buildings": {0: "Farm", 1: "Barracks", 2: "Barracks"},
        "units": _make_units([("Cavalry", 3), ("Archer", 2)], level=2),
    },

    # ========== EASTERN KINGDOMS (Player 1) ==========
    "Londia": {
        "owner": 1,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_units([("Swordsman", 1), ("Archer", 1)]),
    },
    "Northern Heilonia": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Farm", 2: "Barracks"},
        "units": _make_units([("Pikeman", 1), ("Cavalry", 1)]),
    },
    "Révia": {
        "owner": 1,
        "buildings": {0: "Square", 1: "Farm"},
        "units": _make_units([("Swordsman", 1)]),
    },
    "Venexia": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Barracks"},
        "units": _make_units([("Archer", 1), ("Cavalry", 1)]),
    },
    "The Holy Land": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Barracks"},
        "units": _make_units([("Swordsman", 2)]),
    },
    "Elletian Isles": {
        "owner": 1,
        "buildings": {0: "Barracks"},
        "units": _make_units([("Archer", 1), ("Pikeman", 2), ("Cavalry", 1)]),
    },
    "Lobardia": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_units([("Cavalry", 1), ("Pikeman", 1)]),
    },
    "Lentria": {
        "owner": 1,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_units([("Archer", 1), ("Pikeman", 1)]),
    },
    "Elland": {
        "owner": 1,
        "buildings": {0: "Farm", 1: "Farm"},
        "units": _make_units([("Swordsman", 1), ("Archer", 1)]),
    },

    # ========== CONFEDERATION OF THE LEUSE (Player 2) ==========
    "Valeonia": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks"},
        "units": _make_units([("Swordsman", 3), ("Cavalry", 3)]),
    },
    "Velognia": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Farm"},
        "units": _make_units([("Pikeman", 4)]),
    },
    "Leuse Valley": {
        "owner": 2,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Barracks"},
        "units": _make_units([("Cavalry", 2), ("Pikeman", 4), ("Archer", 2)]),
    },
    "Nordica": {
        "owner": 2,
        "buildings": {0: "Barracks", 1: "Barracks"},
        "units": _make_units([("Swordsman", 1), ("Archer", 3)]),
    },

    # ========== AHTEP EMPIRE (Player 3) ==========
    "Ahtep": {
        "owner": 3,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Barracks"},
        "units": _make_units([("Cavalry", 5), ("Pikeman", 2), ("Archer", 2)]),
    },
    "Amennia": {
        "owner": 3,
        "buildings": {0: "Keep", 1: "Barracks", 2: "Farm"},
        "units": _make_units([("Swordsman", 4), ("Archer", 4)]),
    },
    "Liadnon": {
        "owner": 3,
        "buildings": {0: "Mine", 1: "Barracks"},
        "units": _make_units([("Cavalry", 2)]),
    },
    "Sstep": {
        "owner": 3,
        "buildings": {0: "Mine", 1: "Barracks"},
        "units": _make_units([("Archer", 3), ("Swordsman", 1)]),
    },
    "Daomea": {
        "owner": 3,
        "buildings": {0: "Mine", 1: "Barracks", 2: "Barracks"},
        "units": _make_units([("Pikeman", 3)]),
    },
}

# Basic intro: zoom to Aelatania + text
INTRO_SEQUENCE = [
    ("zoom_to", "Aelatania", ""),
    ("wait", 11.0, "The fall of the Mother empire resonates deep within me. We are surrounded by savages, uncultured swines."),
    ("wait", 12.0, "It is our solemn duty to spread the higher culture, to enrich this continent with the knowledge and plenty of the Mother empire's legacy."),
    ("wait", 11.0, "But the savages are already resisting. They will not accept our paths and our faith peacefully.. only through force."),
    ("wait", 14.0, "We must not relent, lest our ways will be erased forever. For the glory of the Gods, we must prevail! Smite the heretics!"),
    ("start_game", 0, ""),
]

# Voice key mapping: intro step index → sound key for voiced transmissions
INTRO_STEP_TO_VOICE = {1: "M4T1", 2: "M4T2", 3: "M4T3", 4: "M4T4"}


# ============================================================================
# CAMERA ANIMATION CLASSES (copied from campaign_mission_2 pattern)
# ============================================================================

class CameraZoomAnimation:
    """Smooth camera zoom animation centered on a target territory.

    Uses the camera_handler object (same pattern as campaign_mission_2).
    The camera_handler has .offset (list [x,y]) and .zoom attributes.
    """
    def __init__(self, camera_handler, target_center_world, duration, screen_width, map_area_height):
        self.camera = camera_handler
        self.target_center = target_center_world
        self.duration = duration
        self.screen_width = screen_width
        self.map_area_height = map_area_height
        self.elapsed = 0.0
        self.done = False

        # Store starting zoom; target is max_zoom for a close-up
        self.start_zoom = camera_handler.zoom
        self.target_zoom = getattr(camera_handler, 'max_zoom', 1.5)

        # Center camera on target at starting zoom
        self._update_camera_position()

    def _update_camera_position(self):
        """Adjust camera offset to keep target_center in screen center."""
        screen_cx = self.screen_width / 2.0
        screen_cy = self.map_area_height / 2.0
        self.camera.offset[0] = self.target_center[0] - screen_cx / self.camera.zoom
        self.camera.offset[1] = self.target_center[1] - screen_cy / self.camera.zoom
        if hasattr(self.camera, 'clamp_to_bounds'):
            self.camera.clamp_to_bounds()

    def update(self, delta_time):
        """Update animation. Returns True when complete."""
        if self.done:
            return True

        self.elapsed += delta_time
        t = min(self.elapsed / self.duration, 1.0)
        # Ease-out cubic
        t = 1.0 - (1.0 - t) ** 3

        # Interpolate zoom
        self.camera.zoom = self.start_zoom + (self.target_zoom - self.start_zoom) * t

        # Keep target centered at current zoom level
        self._update_camera_position()

        if self.elapsed >= self.duration:
            self.done = True
            return True
        return False


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
        """Render text with word wrapping."""
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
# MISSION 4 CLASS
# ============================================================================

class Mission4:
    """
    Campaign Mission 4: Domination

    Features:
    - 21 territories across 4 factions (1 human + 3 AI)
    - Custom AI: builds/trains normally, attacks only player 0, ramp limit,
      defensive minimums per faction
    - Pre-assigned hero: Regnus Aevencourne (Brennhen clone)
    - Territory display name overrides (7 renames)
    - Basic intro sequence (zoom + text)
    - Victory when Eastern Kingdoms + Confederation defeated, defeat when Regnus dies
    """

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_4'
        self.active = True

        # Faction state tracking
        self.faction_defeated = {1: False, 2: False, 3: False}

        # AI turn ramp: tracks how many turns each AI faction has taken
        self.faction_turn_count = {1: 0, 2: 0, 3: 0}

        # AI turn timing (0.5s fast turns)
        self.ai_turn_timer = 0.0
        self._ai_executed_this_turn = False  # Guard: prevent duplicate AI execution per turn

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

        # Quest log — victory requires defeating EK + Leuse only (Ahtep optional)
        # Defeat condition: Regnus Aevencourne dies (Keep conquered)
        self.quest_log = [
            {'text': 'Conquer the Eastern Kingdoms', 'completed': False},
            {'text': 'Conquer the Confederacy of the Leuse', 'completed': False},
            {'text': 'Regnus Aevencourne in Aelatania must survive', 'completed': False},
        ]

        # Victory/defeat sequence state
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

        # Transmission queue for gameplay events: list of (text, duration, voice_key) tuples
        self.transmission_queue = []
        # Inter-transmission pause timer (1s silent gap between voiced intro steps)
        self._intro_pause_timer = 0.0

        # Allow turn timer to auto-end player turns
        self.allow_timer_expiry = True

        # Store original flag icons for restoration on cleanup
        self.original_flag_icons = None

        # Set up territory filtering and display names
        map_data.set_enabled_territories(MISSION_4_TERRITORIES)
        map_data.set_territory_display_names(MISSION_4_DISPLAY_NAMES)

        # Set up initial game state
        self._setup_initial_state()

        # Pre-assign Regnus Aevencourne hero to player
        self._assign_starting_hero()

        # Start intro sequence
        self._start_intro_sequence()

    def _setup_initial_state(self):
        """Configure the game state for Mission 4 scenario."""
        gs = self.game_state

        # Set player colors
        for i, color in enumerate(PLAYER_COLORS):
            if i < len(gs.player_colors):
                gs.player_colors[i] = color

        # Remap flag icons to match player colors
        # Default flag order: 0=Red, 1=Blue, 2=Green, 3=Yellow
        # Mission 4: Player 0=Blue, 1=Green, 2=Red, 3=Yellow
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and len(game.army_flag_icons) >= 4:
            self.original_flag_icons = {i: game.army_flag_icons[i] for i in range(4)}
            game.army_flag_icons[0] = self.original_flag_icons[1]  # Blue for human
            game.army_flag_icons[1] = self.original_flag_icons[2]  # Green for Eastern Kingdoms
            game.army_flag_icons[2] = self.original_flag_icons[0]  # Red for Confederation
            # Player 3 stays Yellow (index 3) — no change needed

        # Set faction names
        for player_id, name in FACTION_NAMES.items():
            if name and player_id < len(gs.player_names):
                gs.player_names[player_id] = name

        # Set starting gold per faction
        for player_id, gold in STARTING_GOLD.items():
            gs.player_gold[player_id] = gold

        # Configure each territory from TERRITORY_SETUP
        for territory, config in TERRITORY_SETUP.items():
            owner = config["owner"]
            gs.territory_owners[territory] = owner

            # Set buildings
            if territory not in gs.buildings:
                gs.buildings[territory] = {}
            for plot_idx, building_type in config.get("buildings", {}).items():
                gs.buildings[territory][plot_idx] = building_type

            # Set garrison units
            units = config.get("units", [])
            unmoved = len(units)
            gs.set_garrison_armies(territory, owner, unmoved=unmoved, moved=0, units=units)

        # Set starting territories for reference
        gs.player_starting_territories[0] = "Aelatania"
        gs.player_starting_territories[1] = "Londia"
        gs.player_starting_territories[2] = "Valeonia"
        gs.player_starting_territories[3] = "Amennia"

        # --- Pre-researched technologies for human player (first 3 from each column) ---
        # This gives the player an economic and military edge to offset the 3v1 disadvantage
        pre_researched = [
            'tech_0_0', 'tech_0_1', 'tech_0_2',  # Efficient Farming I, Efficient Mining I, Leave Nothing Behind
            'tech_1_0', 'tech_1_1', 'tech_1_2',  # Improved Training, Makeshift Barracks, Animal Handling
            'tech_1_3',                            # Battlement Archery (+50% Archer strength near Keep/Castle)
            'tech_2_0', 'tech_2_1', 'tech_2_2',  # Master Planner I, Improved Command I, Royal Decree
        ]
        for tech_id in pre_researched:
            gs.player_tech_researched[0].add(tech_id)
            gs.player_tech_available[0].discard(tech_id)

        # Apply tech effects directly (mirror finish_research logic)
        gs.player_training_cost_discount[0] = 20       # tech_1_0: Swordsman/Pikeman -20%
        gs.player_barracks_cost_discount[0] = 25        # tech_1_1: Barracks -25%, full refund
        gs.player_barracks_full_refund[0] = True         # tech_1_1: 100% demolish refund
        gs.player_cavalry_cost_discount[0] = 25          # tech_1_2: Cavalry -25%
        gs.player_archer_keep_strength_bonus[0] = 50      # tech_1_3: Archers +50% near Keep/Castle
        gs.player_planning_time_limit[0] += 30           # tech_2_0: +30s planning time
        gs.player_command_limit[0] += 35                 # tech_2_1: +35 command limit
        gs.player_royal_decree_discount[0] = 15          # tech_2_2: Hero/Keep -15%
        # tech_0_0, tech_0_1, tech_0_2 effects are checked inline in income calculations

        # Unlock next tier techs — Castle required, which we give below
        gs.player_tech_available[0].add('tech_0_3')  # row 3 col 0
        gs.player_tech_available[0].add('tech_1_4')  # row 4 col 1 (tech_1_3 already researched)
        gs.player_tech_available[0].add('tech_2_3')  # row 3 col 2

        # --- Castle upgrade at Aelatania (plot 1 = Keep) ---
        # Unlocks tier 4+ tech research from turn 1
        gs.castle_upgrades['Aelatania'] = {1: True}

        logger.info("Mission 4 initial state configured with 21 territories, 10 pre-researched techs, Castle at Aelatania")

    def _assign_starting_hero(self):
        """Pre-assign Regnus Aevencourne to the player at Aelatania Keep."""
        gs = self.game_state
        hero_name = "Regnus Aevencourne"

        # Add hero to player's heroes dict
        if 0 not in gs.heroes:
            gs.heroes[0] = {}
        gs.heroes[0][hero_name] = {
            'keep_territory': 'Aelatania',
            'keep_plot': 1  # Keep is at plot index 1 for Aelatania
        }

        # Track ownership
        if 0 not in gs.hero_ownership:
            gs.hero_ownership[0] = set()
        gs.hero_ownership[0].add(hero_name)

        logger.info(f"Assigned {hero_name} to player at Aelatania Keep")

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
            # Start zoom animation to target territory (uses camera handler, same as mission 2)
            try:
                import main as _main
                map_area_height = _main.MAP_HEIGHT
            except (ImportError, AttributeError):
                map_area_height = self.main_game.screen.get_height()
            camera = self.main_game.camera
            sw = self.main_game.screen.get_width()
            # Use scaled_centers (viewport-adjusted) with fallback to raw centroid
            target_center = self.main_game.scaled_centers.get(
                param, map_data.get_territory_center(param)
            )
            self.camera_animation = CameraZoomAnimation(
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
                self._show_transmission(text)
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
        import time
        self.game_state.planning_phase_start_time = time.time()
        logger.info("Intro sequence complete — gameplay begins")

    def _show_transmission(self, text, speaker="Regnus Aevencourne"):
        """Show or update the transmission overlay with optional speaker name."""
        import main as _main
        TOP_PANEL_HEIGHT = _main.TOP_PANEL_HEIGHT
        screen = self.main_game.screen
        sw = screen.get_width()
        sh = screen.get_height()
        if not self.transmission_overlay:
            self.transmission_overlay = TransmissionOverlay(sw, sh, text, TOP_PANEL_HEIGHT, speaker=speaker)
        else:
            self.transmission_overlay.set_text(text)

    def _queue_transmission(self, text, duration, voice_key=None):
        """Queue a transmission to show during gameplay. Supports multiple queued messages.
        voice_key: optional sound key (e.g. "M4T5") to play when transmission starts.
        """
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
            return

        # Update camera animation
        if self.camera_animation:
            done = self.camera_animation.update(delta_time)
            if done:
                if self.intro_waiting_for_zoom:
                    self.intro_waiting_for_zoom = False
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
        if self.intro_active and not self.intro_waiting_for_zoom:
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
                self.game_frozen = True

                text = "The Gods have delivered us victory! Long may their reign shine upon the glory of our new Empire!"
                self._show_transmission(text)
                self.transmission_duration = 9.0
                self.transmission_timer = 0.0
                # Play victory voice line
                from global_sound import play_transmission_sound
                play_transmission_sound("M4T7")

        # Deferred defeat: same pattern — wait for battles/popups, then show defeat
        if self._defeat_waiting and gameplay_idle:
            if not self.transmission_overlay and not self.transmission_queue:
                self._defeat_waiting = False
                self._pending_defeat = True
                self.game_frozen = True

                text = "Regnus has been slain! Without his leadership, the favour of the Gods is lost!"
                self._show_transmission(text, speaker="Nobleman")
                self.transmission_duration = 5.0
                self.transmission_timer = 0.0
                # Play defeat voice line
                from global_sound import play_transmission_sound
                play_transmission_sound("M4T8")

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

    # ========================================================================
    # AI CONTROL
    # ========================================================================

    @property
    def block_ai(self):
        """Block normal AI for all AI players — Mission4 controls their behavior."""
        if self.intro_active:
            return True
        current_player = self.game_state.current_player
        if current_player == 0:
            return False  # Human player
        return True  # Block normal AI for all AI factions

    @property
    def block_ai_thinking(self):
        """Control the AI thinking indicator text."""
        return False  # Show unified "Enemies thinking..." via get_ai_thinking_text()

    def get_ai_thinking_text(self):
        """Override AI thinking indicator to show unified 'Enemies thinking...' text."""
        return ("Enemies thinking...", "")

    def execute_ai_turn_override(self):
        """Called instead of normal AI execution. Dispatches to faction AI.

        Note: This is called EVERY FRAME by ai_player.execute_turn() because
        block_ai bypasses the turn_in_progress guard. We use _ai_executed_this_turn
        to ensure the AI logic only runs once per turn.
        """
        current_player = self.game_state.current_player
        if current_player == 0:
            return

        # Skip turns for defeated factions
        if self.faction_defeated.get(current_player, False):
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

        # Force-complete turn announcement for AI players immediately.
        # main.py gates handle_ai_turn() behind `not turn_announcement_active`,
        # so if we don't clear this, the AI never gets to execute its turn.
        # _complete_turn_announcement() runs turn-start effects (building/training
        # completion, XP ticks, etc.) that are essential for AI economy.
        if gs.turn_announcement_active:
            if hasattr(gs, '_complete_turn_announcement'):
                gs._complete_turn_announcement()
            else:
                gs.turn_announcement_active = False

        # Skip turns for defeated factions
        if self.faction_defeated.get(current_player, False):
            self._ai_executed_this_turn = False
            gs.next_player()
            return True

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
    # CUSTOM FACTION AI
    # ========================================================================

    def _execute_faction_ai(self, player_id):
        """Execute AI for a faction: build, train, reinforce, then attack.

        Ramp rule: on faction's Nth turn, max N total units sent in attacks AND
        N total units moved as reinforcements. This ensures gradual escalation.
        Defensive minimums: keep FACTION_DEFENSE_MIN[player_id] units in territories
        adjacent to player 0 before attacking.
        """
        gs = self.game_state

        # Increment turn counter for this faction
        self.faction_turn_count[player_id] += 1
        turn_n = self.faction_turn_count[player_id]
        defense_min = FACTION_DEFENSE_MIN.get(player_id, 1)

        # Ramp formula: 1-1-1-2-2-2-3-4-5... (delayed aggression, slow early game)
        if turn_n <= 3:
            max_units = 1
        elif turn_n <= 6:
            max_units = 2
        else:
            max_units = turn_n - 4  # turn 7→3, 8→4, 9→5, ...

        # Find territories owned by this faction
        my_territories = [t for t in MISSION_4_TERRITORIES
                         if gs.territory_owners.get(t) == player_id]

        if not my_territories:
            return  # Faction eliminated

        # Phase 1: Build structures on empty plots
        self._ai_build(player_id, my_territories)

        # Phase 2: Train units at all barracks (continuous training)
        self._ai_train(player_id, my_territories)

        # Phase 3: Plan reinforcements (move rear units toward player 0 border)
        self._ai_reinforce(player_id, my_territories, max_units)

        # Phase 4: Plan attacks against player 0 only
        self._ai_attack(player_id, my_territories, max_units, defense_min)

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
                    # Temporarily set current_player for the building call
                    original_player = gs.current_player
                    gs.current_player = player_id
                    gs.start_construction(territory, plot_idx, building_type)
                    gs.current_player = original_player
                    break  # One building per territory per turn

    def _ai_train(self, player_id, my_territories):
        """Train units at all barracks whenever affordable. Prioritize mixed composition."""
        gs = self.game_state

        # Cycle through unit types for variety
        unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
        type_idx = self.faction_turn_count[player_id] % len(unit_types)

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
                    gs.current_player = player_id
                    gs.start_training(territory, plot_idx, unit_type)
                    gs.current_player = original_player
                    type_idx += 1

    def _ai_reinforce(self, player_id, my_territories, max_units):
        """Move units from rear territories toward the player 0 border.

        Capped at max_units total units moved per turn (ramp limit).
        """
        gs = self.game_state
        units_moved = 0

        # Identify border territories (adjacent to player 0)
        player_0_territories = set(t for t in MISSION_4_TERRITORIES
                                   if gs.territory_owners.get(t) == 0)

        border_territories = set()
        for t in my_territories:
            neighbors = map_data.get_neighbors(t)
            for n in neighbors:
                if n in player_0_territories:
                    border_territories.add(t)
                    break

        # Identify rear territories (not on border, have units)
        rear_territories = [t for t in my_territories if t not in border_territories]

        for rear_t in rear_territories:
            if units_moved >= max_units:
                break

            garrison = gs.territory_garrisons.get(rear_t, {}).get(player_id, {})
            units = garrison.get('units', [])
            ready_units = [u for u in units if u.get('status') == 'ready']

            if not ready_units:
                continue

            # Find adjacent territory that's closer to the border (prefer own border territories)
            neighbors = map_data.get_neighbors(rear_t)
            best_target = None
            for n in neighbors:
                if n in border_territories:
                    best_target = n
                    break
                if gs.territory_owners.get(n) == player_id and n not in rear_territories:
                    best_target = n

            if best_target:
                # Move units up to ramp limit (respecting army limit at target)
                remaining_budget = max_units - units_moved
                target_units = sum(len(g.get('units', []))
                                   for g in gs.territory_garrisons.get(best_target, {}).values())
                available_slots = gs.MAX_ARMIES_PER_TERRITORY - target_units
                count = min(len(ready_units), available_slots, remaining_budget)
                units_to_move = ready_units[:count]

                if units_to_move:
                    unit_ids = [u['id'] for u in units_to_move]
                    gs.add_movement_order_for_units(rear_t, best_target, unit_ids, player=player_id)
                    units_moved += len(units_to_move)

    def _ai_attack(self, player_id, my_territories, max_units, defense_min):
        """Attack player 0 territories. Respects defensive minimums and ramp limit.

        max_units caps the TOTAL number of units sent across all attack orders this turn.
        """
        gs = self.game_state
        units_sent = 0

        # Find player 0 territories
        player_0_territories = set(t for t in MISSION_4_TERRITORIES
                                   if gs.territory_owners.get(t) == 0)

        if not player_0_territories:
            return  # Player already eliminated

        # Build attack candidates: (our territory, target territory, available units after defense reserve)
        attack_candidates = []

        for my_t in my_territories:
            garrison = gs.territory_garrisons.get(my_t, {}).get(player_id, {})
            units = garrison.get('units', [])
            ready_units = [u for u in units if u.get('status') == 'ready']

            # Check if this territory is adjacent to player 0
            neighbors = map_data.get_neighbors(my_t)
            adjacent_to_player = any(n in player_0_territories for n in neighbors)

            if not adjacent_to_player:
                continue

            # Reserve defensive minimum
            available = len(ready_units) - defense_min
            if available <= 0:
                continue

            # Find which player 0 territories we can attack
            for neighbor in neighbors:
                if neighbor in player_0_territories:
                    # Score: prefer weakly defended territories
                    target_garrison = gs.territory_garrisons.get(neighbor, {}).get(0, {})
                    target_units = len(target_garrison.get('units', []))
                    score = available - target_units  # Higher = better odds
                    attack_candidates.append((my_t, neighbor, available, score))

        # Sort by score (best odds first)
        attack_candidates.sort(key=lambda x: x[3], reverse=True)

        # Execute attacks up to ramp limit (caps total UNITS, not orders)
        used_sources = set()  # Each source territory attacks once
        for my_t, target, available, score in attack_candidates:
            if units_sent >= max_units:
                break
            if my_t in used_sources:
                continue

            garrison = gs.territory_garrisons.get(my_t, {}).get(player_id, {})
            units = garrison.get('units', [])
            ready_units = [u for u in units if u.get('status') == 'ready']

            # Cap units to send by remaining ramp budget and defense minimum
            remaining_budget = max_units - units_sent
            send_count = min(available, remaining_budget)
            units_to_send = ready_units[:send_count]
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

        # Block hero training (player has pre-assigned hero only)
        if action_type == 'train_hero':
            return False

        # Keeps are allowed — hero training is separately blocked above
        # and should_hide_hero_training() hides the training UI

        return True

    def should_hide_hero_training(self):
        """Return True to hide all hero training icons in the Keep UI.

        Mission 4 uses a pre-assigned hero; no training options should appear.
        """
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
        """Handle territory conquest — check for faction elimination and victory/defeat.

        Victory: Eastern Kingdoms (1) AND Confederation of the Leuse (2) defeated.
        Defeat: Regnus Aevencourne is killed (Keep destroyed).
        """
        gs = self.game_state

        # Check if Regnus Aevencourne was killed (defeat condition)
        # Hero is removed from gs.heroes by kill_heroes_in_keep() before this event fires
        regnus_alive = (
            0 in gs.heroes and
            'Regnus Aevencourne' in gs.heroes[0]
        )
        if not regnus_alive:
            logger.info("Regnus Aevencourne has fallen — defeat!")
            self.quest_log[2]['completed'] = False  # Mark survival quest as failed
            self._start_defeat()
            return

        # Check if any AI faction has been eliminated
        for faction_id in [1, 2, 3]:
            if self.faction_defeated[faction_id]:
                continue

            # Check if faction still owns any territory
            has_territory = any(
                gs.territory_owners.get(t) == faction_id
                for t in MISSION_4_TERRITORIES
            )

            if not has_territory:
                self.faction_defeated[faction_id] = True
                faction_name = FACTION_NAMES.get(faction_id, f"Faction {faction_id}")
                logger.info(f"{faction_name} has been defeated!")

                # Update quest log: quest 0=EK (faction 1), quest 1=Leuse (faction 2)
                if faction_id == 1:
                    self.quest_log[0]['completed'] = True
                elif faction_id == 2:
                    self.quest_log[1]['completed'] = True

                # Victory: Eastern Kingdoms AND Confederation defeated
                # Skip individual defeat transmission — victory transmission plays instead
                if self.faction_defeated[1] and self.faction_defeated[2]:
                    self._start_victory()
                else:
                    # Queue mid-game faction defeat transmission with voice
                    if faction_id == 1:
                        self._queue_transmission(
                            'The heretics of the so-called "Divine Mother" are defeated! One less stain upon this world!',
                            9.0, voice_key="M4T5")
                    elif faction_id == 2:
                        self._queue_transmission(
                            "The upstarts of the Leuse Valley have been conquered! No more of their meddling!",
                            7.0, voice_key="M4T6")

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
                self.victory_phase = 'exit'
                return 'exit'

        return None

    def _render_victory_sequence(self, screen):
        """Render the victory sequence overlay."""
        if not self.victory_sequence_active:
            return

        sw, sh = screen.get_size()

        if self.victory_fade_alpha > 0:
            overlay = pygame.Surface((sw, sh))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(self.victory_fade_alpha)
            screen.blit(overlay, (0, 0))

        if self.victory_phase in ('image_grow', 'image_hold') and self.victory_image:
            iw, ih = self.victory_image.get_size()
            scale = max(0.01, self.victory_image_scale)
            sw2, sh2 = int(iw * scale), int(ih * scale)
            if sw2 > 0 and sh2 > 0:
                scaled = pygame.transform.smoothscale(self.victory_image, (sw2, sh2))
                screen.blit(scaled, ((sw - sw2) // 2, (sh - sh2) // 2))

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
                self.defeat_phase = 'exit'
                return 'exit'

        return None

    def _render_defeat_sequence(self, screen):
        """Render the defeat sequence overlay."""
        if not self.defeat_sequence_active:
            return

        sw, sh = screen.get_size()

        if self.defeat_fade_alpha > 0:
            overlay = pygame.Surface((sw, sh))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(self.defeat_fade_alpha)
            screen.blit(overlay, (0, 0))

        if self.defeat_phase in ('image_grow', 'image_hold') and self.defeat_image:
            iw, ih = self.defeat_image.get_size()
            scale = max(0.01, self.defeat_image_scale)
            sw2, sh2 = int(iw * scale), int(ih * scale)
            if sw2 > 0 and sh2 > 0:
                scaled = pygame.transform.smoothscale(self.defeat_image, (sw2, sh2))
                screen.blit(scaled, ((sw - sw2) // 2, (sh - sh2) // 2))

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
        return territory_name in MISSION_4_TERRITORIES

    def get_adjacency_override(self, territory):
        """No special adjacency restrictions in Mission 4."""
        return None

    def get_highlight_territory(self):
        """No step-based territory highlighting in Mission 4."""
        return None

    def should_highlight_plot(self, territory, plot_index):
        """No plot highlights in Mission 4."""
        return False

    def get_bonus_conditions(self):
        """Return bonus achievement conditions for Mission 4.

        'Empire Who?' bonus: defeat the Ahtep Empire (faction 3) and win.
        """
        return {
            'campaign_mission_4_bonus': self.faction_defeated.get(3, False),
        }

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def _cleanup(self):
        """Clean up mission state when exiting."""
        from global_sound import stop_transmission_sound
        logger.info("Cleaning up Mission 4")
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
