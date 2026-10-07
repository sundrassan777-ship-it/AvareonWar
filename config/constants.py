# -*- coding: utf-8 -*-
# config/constants.py
# All game constants - colors, sizes, timing, etc.

"""
Game Constants
==============

This module contains all constants used throughout the game:
- Window and resolution settings
- Colors (basic, panel-specific, UI states)
- UI sizing (buttons, tooltips, badges, etc.)
- Timing (delays, animations)
- Camera settings
- Map dimensions
- AI difficulty modifiers and thresholds
- Combat effectiveness multipliers

Extracted from main.py during Phase 1 of refactoring.
"""

from typing import Tuple
import math

# Type aliases for color tuples
Color3 = Tuple[int, int, int]        # RGB color (no alpha)
Color4 = Tuple[int, int, int, int]   # RGBA color (with alpha)

# ===========================================
# WINDOW & RESOLUTION
# ===========================================

# Game version displayed on main menu
GAME_VERSION = "1.0.0"

# Window Size - ADJUST THESE TO FIT YOUR SCREEN
WINDOW_WIDTH = 1600  # Adjust this to your screen width
WINDOW_HEIGHT = 850  # Adjust this to your screen height

# Frame rate - PERFORMANCE OPTIMIZATION: Raised from 60 to 80 FPS target
FPS = 80
# Selectable FPS caps in the options menus. 0 = no manual cap (VSync or FPS above
# paces frames). Note there is deliberately no "truly uncapped" option: frame
# timing is derived per frame and an unbounded loop makes it meaningless.
FPS_LIMIT_OPTIONS = [0, 60, 80, 120, 144, 165, 240]
# Reduced frame rate when window is unfocused/minimized (Steam requirement: don't burn CPU in background)
UNFOCUSED_FPS = 10

# ===========================================
# FONT PATHS
# ===========================================

# Cinzel font files (custom fonts for in-game UI)
# Located in assets/fonts/ directory
CINZEL_REGULAR = "assets/fonts/Cinzel-Regular.ttf"
CINZEL_SEMIBOLD = "assets/fonts/Cinzel-SemiBold.ttf"
CINZEL_BOLD = "assets/fonts/Cinzel-Bold.ttf"

# ===========================================
# MAP DIMENSIONS
# ===========================================

# Original map dimensions (for scaling polygons)
# Updated 2026-01-24: New high-resolution map (4096×3072)
ORIGINAL_MAP_WIDTH = 4096
ORIGINAL_MAP_HEIGHT = 3072

# Map area (calculated based on window size and panels)
MAP_WIDTH = WINDOW_WIDTH  # Full width (no right panel)

# East map extension (rendering/map_extension.py)
# The map is left-aligned, so when zoomed far out on a 16:9 window it ends before
# the window's right edge (~175 px at zoom 1.65). That strip used to be hidden by
# the right sidebar; the extension fills it so the sidebar can collapse.
# A painted '<background>_east.png' beside the map image overrides the generated one.
MAP_EAST_FOG_COLOR = (60, 48, 32)     # Warm dark parchment the generated edge fades into
MAP_EAST_MIN_SRC_PX = 256             # Narrowest generated extension (source pixels)
MAP_EAST_MAX_SRC_PX = 2048            # Widest generated extension; beyond it is solid fog
MAP_EAST_MAX_PIXELS = 2_000_000       # Memory cap for the stored extension (~8 MB)
MAP_EAST_BLUR_FACTOR = 16             # Blur of the mirrored strip (hides reversed labels)
MAP_EAST_CRISP_BAND = 0.08            # Share of the width kept crisp at the seam
# 'stretch': edge colours run straight east (coastlines carry on outward).
# 'mirror' : the map's last strip reflected (more texture, but reverses coastlines —
#            on Azincournean the NE coast bent back south-west).
MAP_EAST_MODE = 'stretch'

# ===========================================
# COLORS
# ===========================================
# Organized by category. RGB tuples are Color3, RGBA tuples are Color4.

# --- Basic / General-Purpose Colors ---
WHITE: Color3 = (255, 255, 255)
BLACK: Color3 = (0, 0, 0)
RED: Color3 = (255, 0, 0)
GREEN: Color3 = (0, 255, 0)
BLUE: Color3 = (0, 0, 255)
YELLOW: Color3 = (255, 255, 0)
GRAY: Color3 = (150, 150, 150)
DARK_GRAY: Color3 = (80, 80, 80)
HIGHLIGHT: Color4 = (255, 255, 0, 100)  # Yellow highlight with transparency

# L3: Canonical player colors - single source of truth for game_state.py,
# integrated_setup.py, and any other module that needs player colors.
PLAYER_COLORS = [
    (255, 100, 100),   # Bright Red - Player 1
    (100, 150, 255),   # Bright Blue - Player 2
    (100, 255, 100),   # Bright Green - Player 3
    (255, 255, 100)    # Bright Yellow - Player 4
]
NEUTRAL_COLOR: Color3 = (150, 150, 150)  # Gray for neutral territories

# --- UI Panel Colors: Brown Background (Top & Bottom Panels) ---
BROWN_TEXT_PRIMARY: Color3 = (255, 250, 240)    # Cream/Ivory - main text
BROWN_TEXT_SECONDARY: Color3 = (255, 215, 150)  # Light Gold - secondary text
BROWN_TEXT_HEADING: Color3 = (255, 255, 255)    # White - headings/titles
BROWN_SEPARATOR: Color3 = (210, 180, 140)       # Tan - separator lines
BROWN_GOLD: Color3 = (255, 223, 0)              # Bright Gold - money/income

# --- UI Panel Colors: Dark Red Background (Right Panel) ---
RED_TEXT_PRIMARY: Color3 = (200, 255, 255)       # Light Cyan - main text
RED_TEXT_SECONDARY: Color3 = (255, 255, 200)     # Light Yellow - secondary text
RED_TEXT_HEADING: Color3 = (255, 255, 200)       # Pale Yellow - headings
RED_SEPARATOR: Color3 = (200, 180, 160)          # Light Tan - separator lines
RED_ACCENT_BRIGHT: Color3 = (0, 255, 255)        # Bright Cyan - accents/arrows
RED_TEXT_DIM: Color3 = (220, 220, 220)           # Light Gray - dim text

# --- Map Colors: Building Plot States ---
COLOR_PLOT_GRAY: Color4 = (150, 150, 150, 200)
COLOR_PLOT_BORDER: Color4 = (50, 50, 50, 255)
COLOR_GOLD_HIGHLIGHT: Color4 = (255, 215, 0, 255)
COLOR_CONSTRUCTION: Color4 = (200, 200, 100, 150)
COLOR_CONSTRUCTION_BORDER: Color4 = (150, 150, 50, 255)
COLOR_CONSTRUCTION_TEXT: Color3 = (200, 200, 200)
COLOR_EMPTY_PLOT_CAN_BUILD: Color4 = (100, 220, 100, 180)
COLOR_EMPTY_PLOT_CANNOT_BUILD: Color4 = (200, 200, 200, 80)
COLOR_EMPTY_PLOT_BORDER: Color4 = (100, 100, 100, 150)

# --- Map Colors: Building/Training Icons ---
COLOR_ICON_AVAILABLE: Color4 = (100, 200, 100, 200)
COLOR_ICON_UNAVAILABLE: Color4 = (200, 100, 100, 200)
# Locked by the tutorial/campaign mission (greyed) - distinct from red "a rule refuses it"
COLOR_ICON_LOCKED: Color4 = (120, 120, 120, 200)
COLOR_ICON_BORDER: Color4 = (50, 50, 50, 255)

# --- Map Colors: Movement Arrows ---
COLOR_ARROW_MOVEMENT: Color3 = (0, 200, 0)

# --- UI Colors: Tooltips ---
COLOR_TOOLTIP_BG: Color3 = (50, 50, 50)
COLOR_TOOLTIP_BORDER: Color3 = (200, 200, 200)

# --- Map Colors: Territory Glow ---
COLOR_TERRITORY_GLOW_FRIENDLY: Color3 = (0, 255, 0)
COLOR_TERRITORY_GLOW_ENEMY: Color3 = (255, 0, 0)
COLOR_TERRITORY_GLOW_NEUTRAL: Color3 = (200, 200, 200)

# ===========================================
# UI ELEMENT SIZES
# ===========================================

# Plot and Building Icon Sizes (2x larger for better visibility!)
PLOT_CIRCLE_RADIUS = 24  # Was 12 (2x larger)
PLOT_CIRCLE_CENTER_OFFSET = 30  # Was 15 (2x larger)
PLOT_SURFACE_SIZE = 60  # Was 30 (2x larger)
EMPTY_PLOT_RADIUS = 16  # Was 8 (2x larger)
BUILDING_ICON_RADIUS = 42  # Orbit radius for quick-access icons (increased for 6 buildings)
ICON_CLICK_RADIUS = 18  # Click/display radius per icon (reduced for 6 buildings)

# Army and Badge Sizes
ARMY_CIRCLE_RADIUS = 15
BADGE_RADIUS = 16

# Army banner (flag) geometry.
# The banner hangs UPWARD from the army circle: its pole base sits exactly on the
# circle anchor, so it spans (anchor_y - height) .. anchor_y.
# CRITICAL: rendering AND hit-testing both derive their geometry from this ratio via
# Game.get_army_banner_rect(). If the two ever use different values, the clickable
# area drifts away from the drawn banner. Never inline this number again.
ARMY_FLAG_HEIGHT_RATIO = 3.3  # banner height = ARMY_CIRCLE_RADIUS * ui_scale * this

# The army circle is DRAWN smaller than ARMY_CIRCLE_RADIUS and lifted above its
# anchor, so the flag pole sits naturally inside the ring. Hit-testing must use
# the same two numbers or the clickable circle drifts off the visible one - it
# used to hit-test a full-radius circle centred ON the anchor, which reached
# 0.60 * radius BELOW the drawn ring (~9-14px) and picked up clicks on empty map.
ARMY_CIRCLE_DRAW_SCALE = 0.75  # drawn ring radius = ARMY_CIRCLE_RADIUS * ui_scale * this
ARMY_CIRCLE_DRAW_LIFT = 0.35   # ring centre sits this * base radius ABOVE the anchor
DEFAULT_ARMY_FLAG_ASPECT = 0.66  # width/height fallback if flag art has no usable size

# Button Sizes
BUTTON_SIZE_SQUARE = 60  # Size for training and building buttons
BUTTON_SPACING = 10

# ===========================================
# TOOLTIP SETTINGS
# ===========================================

# Timing
HOVER_DELAY_MS = 500  # 0.5 seconds before tooltip appears
TOOLTIP_DELAY_MS = 500  # Delay before showing tooltips (milliseconds)
TOOLTIP_DELAY_BUTTON_MS = 500  # Delay for button tooltips (milliseconds)

# Positioning
TOOLTIP_OFFSET_X = 15
TOOLTIP_OFFSET_Y = 15
TOOLTIP_BORDER_WIDTH = 2
TOOLTIP_SCREEN_MARGIN = 5  # Margin from screen edges

# Sizing
TOOLTIP_LINE_HEIGHT = 15
TOOLTIP_WIDTH_TRAINING = 150
TOOLTIP_WIDTH_BUILDING = 200
TOOLTIP_WIDTH_PLOT = 135
TOOLTIP_PADDING = 7

# ===========================================
# ARROW DRAWING
# ===========================================

ARROW_LINE_WIDTH = 4
ARROW_HEAD_SIZE = 15
ARROW_HEAD_ANGLE_RAD = 0.5236  # math.pi / 6 (30 degrees)

# Cascade cancel animation: red shaking arrows when auto-cancelled due to overflow
COLOR_ARROW_CANCELLED: Color3 = (220, 50, 50)
ARROW_CANCEL_DURATION = 0.6       # seconds
ARROW_CANCEL_SHAKE_FREQ = 30      # Hz (oscillation speed)
ARROW_CANCEL_SHAKE_AMP = 4        # pixels (shake amplitude)

# ===========================================
# UI SPACING
# ===========================================

UI_LINE_SPACING = 30  # Vertical space between text lines
UI_LINE_SPACING_SMALL = 22  # Smaller vertical spacing
UI_LINE_SPACING_LARGE = 40  # Larger vertical spacing
UI_SECTION_SPACING = 40  # Space between UI sections
UI_BUTTON_SPACING = 5  # Horizontal space between buttons
UI_PADDING = 8  # General padding around UI elements
UI_PANEL_PADDING = 10  # Padding inside panels

# ===========================================
# ANIMATION & TIMING
# ===========================================

CLICK_FLASH_DURATION_MS = 150  # How long click flash lasts (milliseconds)

# ===========================================
# CAMERA SETTINGS
# ===========================================

CAMERA_SCROLL_SPEED = 15  # Edge scrolling speed (pixels per frame)
CAMERA_PAN_SPEED = 10  # Keyboard pan speed (pixels per frame)
CAMERA_ZOOM_SPEED = 0.15  # Zoom increment per scroll

# ===========================================
# AI DIFFICULTY MODIFIERS
# ===========================================
# Extracted from ai_player.py DIFFICULTY_CONFIGS.
# These are the per-difficulty-level multipliers and timing values
# used to tune AI decision quality, aggression, and pacing.

# --- Easy Difficulty (level 0) ---
AI_EASY_INCOME_MULTIPLIER = 0.75
AI_EASY_DECISION_DELAY_MIN = 5.0       # Seconds before AI acts (minimum)
AI_EASY_DECISION_DELAY_MAX = 8.0       # Seconds before AI acts (maximum)
AI_EASY_STRATEGY_QUALITY = 0.85        # Decision quality factor (0.0-1.0)
AI_EASY_HERO_ABILITY_USAGE = 0.65      # Probability of using hero abilities
AI_EASY_TECH_RESEARCH_RATE = 0.8       # Probability of researching available tech
AI_EASY_ATTACK_AGGRESSION = 0.5        # How aggressively AI initiates attacks
AI_EASY_BUILDING_EFFICIENCY = 0.85     # Probability of building when beneficial

# --- Medium Difficulty (level 1) ---
AI_MEDIUM_INCOME_MULTIPLIER = 1.0
AI_MEDIUM_DECISION_DELAY_MIN = 3.0
AI_MEDIUM_DECISION_DELAY_MAX = 5.0
AI_MEDIUM_STRATEGY_QUALITY = 0.95
AI_MEDIUM_HERO_ABILITY_USAGE = 0.9
AI_MEDIUM_TECH_RESEARCH_RATE = 0.95
AI_MEDIUM_ATTACK_AGGRESSION = 0.8
AI_MEDIUM_BUILDING_EFFICIENCY = 0.95

# --- Hard Difficulty (level 2) ---
AI_HARD_INCOME_MULTIPLIER = 1.25
AI_HARD_DECISION_DELAY_MIN = 2.0
AI_HARD_DECISION_DELAY_MAX = 3.0
AI_HARD_STRATEGY_QUALITY = 1.0
AI_HARD_HERO_ABILITY_USAGE = 1.0
AI_HARD_TECH_RESEARCH_RATE = 1.0
AI_HARD_ATTACK_AGGRESSION = 1.0
AI_HARD_BUILDING_EFFICIENCY = 1.0

# ===========================================
# AI ECONOMY THRESHOLDS
# ===========================================
# Extracted from ai_economy.py.
# These control when the AI decides to upgrade, demolish, or prioritize buildings.

# Castle upgrade cost threshold (gold required to upgrade Keep -> Castle)
AI_CASTLE_UPGRADE_COST = 150  # L2 fix: actual Castle upgrade cost is 150

# Strong economy thresholds for proactive Castle upgrade (scaled to 10/15/20 income tiers)
AI_STRONG_ECONOMY_INCOME_THRESHOLD = 230   # Min income to consider economy "strong"
AI_STRONG_ECONOMY_GOLD_THRESHOLD = 150     # Min gold alongside strong income

# Tech investment threshold: min techs in any column to count as "invested"
AI_TECH_INVESTED_MIN_COUNT = 2

# Tech row threshold: researched row >= this means approaching Castle-required techs
AI_TECH_APPROACHING_CASTLE_ROW = 2

# Castle upgrade priority score (returned when AI decides to upgrade Keep -> Castle)
AI_CASTLE_UPGRADE_PRIORITY_SCORE = 150.0

# Keep placement: hero enabling thresholds
AI_KEEP_HERO_ENABLE_MIN_TERRITORIES = 8    # Min territories to justify Keep for heroes
AI_KEEP_HERO_ENABLE_MIN_GOLD = 300         # Min gold to justify Keep for heroes
AI_KEEP_HERO_ENABLE_BONUS = 120.0          # Score bonus when hero enabling is critical
AI_KEEP_MIDGAME_MIN_TERRITORIES = 12       # Territory count for mid-game Keep priority
AI_KEEP_MIDGAME_BONUS = 80.0              # Score bonus for mid-game Keep

# Keep placement: territory value/threat thresholds
AI_KEEP_HIGH_VALUE_THRESHOLD = 60          # Territory value considered "high"
AI_KEEP_HIGH_THREAT_THRESHOLD = 40         # Threat level considered "high"
AI_KEEP_HIGH_VALUE_THREAT_BONUS = 20.0     # Bonus when both value and threat are high
AI_KEEP_CAPITAL_ASSAULT_BONUS = 50.0       # Bonus for Keep in capital during Capital Assault

# Demolition threshold: AI considers demolishing Farms/Mines above this gold (scaled to 10/15/20 income tiers)
AI_DEMOLITION_GOLD_THRESHOLD = 2400

# Budget allocation: emergency reserve
AI_BUDGET_RESERVE_PERCENT = 0.02           # Reserve 2% of gold for emergencies
AI_BUDGET_RESERVE_MAX = 10                 # Maximum gold reserved

# Budget allocation ratios by mode: (buildings, tech, training)
AI_BUDGET_ECONOMY_BUILDINGS = 0.5
AI_BUDGET_ECONOMY_TECH = 0.3
AI_BUDGET_ECONOMY_TRAINING = 0.2

AI_BUDGET_DEFENSE_TRAINING = 0.6
AI_BUDGET_DEFENSE_BUILDINGS = 0.3
AI_BUDGET_DEFENSE_TECH = 0.1

AI_BUDGET_EXPANSION_TRAINING = 0.5
AI_BUDGET_EXPANSION_BUILDINGS = 0.3
AI_BUDGET_EXPANSION_TECH = 0.2

AI_BUDGET_CONQUEST_TRAINING = 0.75
AI_BUDGET_CONQUEST_BUILDINGS = 0.15
AI_BUDGET_CONQUEST_TECH = 0.10

AI_BUDGET_VICTORY_PUSH_TRAINING = 0.7
AI_BUDGET_VICTORY_PUSH_BUILDINGS = 0.2
AI_BUDGET_VICTORY_PUSH_TECH = 0.1

# ===========================================
# COMBAT EFFECTIVENESS MULTIPLIERS
# ===========================================
# Extracted from game_state.py calculate_unit_effectiveness().
# These define how much a unit's strength is scaled based on counter matchups.

COMBAT_COUNTER_MULTIPLIER = 2.0       # Unit fights an enemy it counters
COMBAT_NEUTRAL_MULTIPLIER = 1.0       # No counter relationship
COMBAT_COUNTERED_MULTIPLIER = 0.5     # Unit fights an enemy that counters it