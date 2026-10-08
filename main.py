# -*- coding: utf-8 -*-
# main.py
# Main game loop and UI

"""
War of Avareon - Main Game Loop and UI Rendering

This module contains the main Game class which handles:
- Pygame initialization and window management
- Event handling (mouse, keyboard)
- Rendering (map, UI, tooltips, popups)
- Game loop timing (60 FPS)
- User interface state management

The Game class is the visual layer that sits on top of GameState (game logic).
It handles all pygame-specific code and UI interactions, while GameState manages
the core game rules and mechanics.

Key Components:
    - Game class: Main game controller
    - Event handling: Click detection with priority system
    - Rendering pipeline: Map â†’ UI â†’ Tooltips â†’ Popups
    - Tooltip system: Hover-based with 0.5s delay
    - Bottom UI: Training, building, orders, territory info
    - Popup systems: Battles, victory screen, army composition

Architecture:
    Game (main.py) â† uses â†’ GameState (game_state.py)
    Game (main.py) â† uses â†’ map_data (map_data.py)

Phase Tracking:
    Phase 1A: Constants extracted (lines 47-107)
    Phase 1B: Error handling added (try/except blocks throughout)
    Phase 1C: Documentation added (comprehensive docstrings)

WINDOW SIZE CONFIGURATION:
To adjust the window to fit your screen, modify these constants below:
- WINDOW_WIDTH: Total window width (e.g., 1600, 1800, 1920)
- WINDOW_HEIGHT: Total window height (e.g., 800, 900, 1080)
The map will automatically scale to fit while maintaining aspect ratio.

Usage:
    python main.py

Dependencies:
    - pygame: Graphics and event handling
    - game_state: Core game logic
    - map_data: Territory and adjacency data
"""

import pygame
import sys
import math
import json
import os
import time
import random
import map_data
from game_state import GameState
from network_config import MessageType

# Import refactored modules
from config.constants import *
from ui.scaler import UIScaler, UIConstants
from ui.sidebar_layout import sidebar_progress, reverse_anim_start, compute_sidebar_layout, ScrollState
from utils.colors import lighten_color, brighten_color
from rendering.helpers import DrawingHelpers
from rendering.map_renderer import MapRenderer
from rendering.ui_renderer import UIRenderer
from rendering.panel_renderer import PanelRenderer
from rendering.map_extension import MapEastExtension, east_extension_override_path
from rendering.sidebar_widgets import SidebarWidgets
from input.camera_handler import CameraHandler
from input.keyboard_handler import KeyboardHandler
from input.mouse_handler import MouseHandler
from config.font_manager import FontManager
from steam_integration import steam_manager
from display_utils import set_display_mode, resolve_frame_cap, current_surface
# Import sparkle version of turn announcement (can switch back to turn_announcement_effect if needed)
from ui.effects.turn_announcement_sparkle import TurnAnnouncementEffect
from ui.effects.chat_notification_effect import ChatNotificationEffect
from global_sound import sound_manager, play_structure_sound  # Global sound manager instance
from music_manager import music_manager, MUSIC_END_EVENT  # Background music system
from tutorial_mission import CameraAnimation  # Reuse for Custom Game / Multiplayer start zoom
from utils.logger import get_logger, setup_logging
from utils.cursor import draw_custom_cursor, draw_attack_cursor, invalidate_cursor_cache

# Initialize structured logging before anything else logs output
setup_logging()
logger = get_logger(__name__)

# PyInstaller bundled executable support:
# When running as a bundled .exe, resources are extracted to a temp directory.
# We change to that directory so relative paths (e.g., "assets/map.png") work correctly.
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    application_path = sys._MEIPASS
    os.chdir(application_path)
else:
    # Running as script
    application_path = os.path.dirname(os.path.abspath(__file__))

# Initialize Pygame
pygame.init()

# ========================================
# UI LAYOUT CALCULATION
# ========================================
# Note: Most constants have been moved to config/constants.py
# Only the dynamic UI layout calculation remains here

# Toggle territory preview image + border + hover hint in bottom UI.
# Currently disabled — lore text renders in the image region instead.
# Re-enable by flipping to True; preview/border/hint code is preserved for future use.
SHOW_TERRITORY_PREVIEW_IMAGE = False

# Initial UI layout (will be updated when resolution changes)
_ui_layout = UIScaler.calculate_ui_layout(WINDOW_WIDTH, WINDOW_HEIGHT)

# Derived layout values (updated dynamically)
TOP_PANEL_HEIGHT = _ui_layout['top_height']
BOTTOM_UI_HEIGHT = _ui_layout['bottom_height']
MAP_HEIGHT = _ui_layout['map_height']
BOTTOM_UI_Y = _ui_layout['bottom_y']

# Update UIConstants with dynamic sidebar height
UIConstants.update_sidebar_height(_ui_layout['sidebar_height'])

# ========================================


# ========================================
# WINDOW / TASKBAR ICON
# ========================================
# These live at MODULE level (not inside `if __name__ == "__main__"`) because
# Game.__init__ and every pygame.display.set_mode() site call _set_app_icon().
# When main.py is imported rather than run as a script (tests, benchmarks, tools),
# the __main__ block never executes — previously leaving _set_app_icon undefined
# and raising NameError on Game() construction.

_app_icon = None
_ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'icon.ico')


def _load_app_icon():
    """
    Load the window/taskbar icon once and cache it in the module-level _app_icon.

    Safe to call before pygame.display is initialized — pygame.image.load()
    does not require a display surface. Returns None if the icon is missing.
    """
    global _app_icon
    if _app_icon is None:
        try:
            _app_icon = pygame.image.load(_ico_path)
        except Exception:
            _app_icon = None
    return _app_icon


def _load_map_background(map_path):
    """
    Load a map background image in DISPLAY format.

    PERFORMANCE — this .convert() is worth ~9ms on EVERY frame:
    The map was the one asset in this file never converted (every other image uses
    .convert_alpha()). An unconverted 4096x3072 RGBA surface stays in *file* format,
    and transform.scale()/smoothscale() output inherits that format — so the
    per-frame `screen.blit(scaled_map, ...)` became a per-pixel format conversion
    plus alpha blend of ~1.4M pixels. Measured on assets/map.png at viewport size:

        unconverted RGBA blit : 9.26 ms   <- ~74% of a 12.5ms (80 FPS) frame budget
        .convert() blit       : 0.15 ms
        .convert_alpha() blit : 0.74 ms

    A map background is the bottom layer — it is blitted over a filled screen and
    nothing shows through it — so it is treated as opaque and uses .convert().
    Both shipped backgrounds (assets/map.png, maps/azincournean_highlands/map.png)
    were verified fully opaque (0 non-opaque pixels). New map backgrounds must
    likewise be opaque; transparency in one would be flattened, not blended.

    Args:
        map_path: Path to the background image, or None for the dark fallback.

    Returns:
        pygame.Surface in display format (never None).
    """
    if map_path and os.path.exists(map_path):
        try:
            return pygame.image.load(map_path).convert()
        except pygame.error as exc:
            logger.error(f"Error loading map background '{map_path}': {exc}")
    # Fallback: dark surface for maps without background images
    fallback = pygame.Surface((ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT)).convert()
    fallback.fill((0, 0, 0))
    return fallback


def _set_app_icon():
    """Re-apply window and taskbar icon after any pygame.display.set_mode() call.
    Uses both pygame.display.set_icon (title bar) and Win32 SendMessage
    WM_SETICON (taskbar) to ensure the icon persists through display recreation."""
    icon = _load_app_icon()
    if icon is not None:
        try:
            pygame.display.set_icon(icon)
        except Exception:
            pass
    # Force taskbar icon via Win32 API (pygame.display.set_icon only sets title bar)
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            _ICON_SMALL, _ICON_BIG = 0, 1
            _WM_SETICON = 0x0080
            _IMAGE_ICON = 1
            _LR_LOADFROMFILE = 0x0010
            hwnd = pygame.display.get_wm_info()['window']
            # Use system metrics for DPI-correct icon sizes (e.g. 48x48 on 150% scaling)
            _SM_CXICON, _SM_CYICON = 11, 12      # Large icon (taskbar, Alt+Tab)
            _SM_CXSMICON, _SM_CYSMICON = 49, 50   # Small icon (title bar)
            big_w = user32.GetSystemMetrics(_SM_CXICON) or 32
            big_h = user32.GetSystemMetrics(_SM_CYICON) or 32
            small_w = user32.GetSystemMetrics(_SM_CXSMICON) or 16
            small_h = user32.GetSystemMetrics(_SM_CYSMICON) or 16
            # Large icon (taskbar)
            hicon_big = user32.LoadImageW(
                None, _ico_path, _IMAGE_ICON, big_w, big_h, _LR_LOADFROMFILE)
            if hicon_big:
                user32.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, hicon_big)
            # Small icon (title bar)
            hicon_small = user32.LoadImageW(
                None, _ico_path, _IMAGE_ICON, small_w, small_h, _LR_LOADFROMFILE)
            if hicon_small:
                user32.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, hicon_small)
        except Exception:
            pass


class Game:
    def __init__(self, existing_screen=None, network_connection=None, campaign_map=None):
        # campaign_map: optional path to a campaign-specific map image (e.g., 'assets/CampaignMaps/Campaign1Map.png')
        self.campaign_map = campaign_map
        # Initialize pygame display module if not already done
        if not pygame.display.get_init():
            pygame.display.init()

        # Detect native monitor resolution for fullscreen mode
        # IMPORTANT: This must happen AFTER pygame.display.init()
        display_info = pygame.display.Info()
        detected_resolution = (display_info.current_w, display_info.current_h)

        # MANUAL OVERRIDE: Uncomment and set your actual monitor resolution if auto-detection is wrong
        # self.native_resolution = (1920, 1080)  # <-- Set your monitor's native resolution here
        # If the line above is commented out, we use auto-detection:
        if not hasattr(self, 'native_resolution'):
            self.native_resolution = detected_resolution

        logger.info("=" * 60)
        logger.info("DISPLAY DETECTION")
        logger.info("=" * 60)
        logger.info(f"Auto-detected: {detected_resolution[0]}x{detected_resolution[1]}")
        logger.info(f"Using:         {self.native_resolution[0]}x{self.native_resolution[1]}")
        if self.native_resolution != detected_resolution:
            logger.warning("Manual override active!")
        logger.info(f"Display driver: {pygame.display.get_driver()}")
        logger.info(f"Video info - Hardware acceleration: {display_info.hw}")
        logger.info(f"Video info - Window manager: {display_info.wm}")
        logger.info("=" * 60)

        # Load settings to determine initial display mode
        from settings_manager import settings
        initial_resolution = settings.get_resolution()
        initial_fullscreen = settings.is_fullscreen()

        # Store default resolution from settings (for "Reset to Defaults" button)
        # This is chosen intelligently from supported resolutions (1280x720, 1600x900, 1920x1080)
        self.default_resolution = settings.get_default_resolution()
        logger.info(f"Default resolution: {self.default_resolution[0]}x{self.default_resolution[1]} (used for Reset to Defaults)")

        initial_width = initial_resolution[0]
        initial_height = initial_resolution[1]

        # Frame pacing settings. vsync_active records what the display ACTUALLY
        # achieved — it cannot be read back from the surface, because get_flags()
        # does not report the SCALED bit (see display_utils).
        self.vsync = settings.get('vsync', False)
        self.fps_limit = settings.get('fps_limit', 0)
        self.vsync_active = False
        # Float frame clock for delta_time (Clock.get_time() is integer ms)
        self._last_frame_time = time.perf_counter()

        # Use existing screen if provided (for seamless transitions)
        if existing_screen is not None:
            logger.info("Reusing existing screen for seamless transition")
            self.screen = existing_screen

            # Check if we need to resize the existing screen
            current_size = self.screen.get_size()
            current_flags = self.screen.get_flags()
            current_is_fullscreen = bool(current_flags & pygame.FULLSCREEN)

            # Only recreate if settings changed. NOTE: vsync state is deliberately
            # not compared here — it is unreadable from the surface, and the menu
            # that handed us this screen already created it with the right mode.
            if current_size != (initial_width, initial_height) or current_is_fullscreen != initial_fullscreen:
                logger.info(f"Adjusting screen from {current_size} to {initial_width}x{initial_height}")
                self.screen, self.vsync_active = set_display_mode(
                    (initial_width, initial_height), initial_fullscreen, self.vsync)
            else:
                # Inherited an already-correct surface; trust the saved setting.
                self.vsync_active = self.vsync
        else:
            # Create new screen
            logger.info(f"Starting game in {'FULLSCREEN' if initial_fullscreen else 'WINDOWED'} "
                        f"at {initial_width}x{initial_height}")
            self.screen, self.vsync_active = set_display_mode(
                (initial_width, initial_height), initial_fullscreen, self.vsync)
        pygame.display.set_caption("War of Avareon")
        _set_app_icon()  # Re-apply icon after display recreation
        pygame.mouse.set_visible(False)  # Hide system cursor — custom cursor drawn via utils/cursor.py
        self.clock = pygame.time.Clock()

        # CRITICAL FIX: Get the ACTUAL window size after creation
        # On Windows with display scaling, pygame may create a different size than requested
        actual_size = self.screen.get_size()
        actual_width = actual_size[0]
        actual_height = actual_size[1]

        logger.info(f"Window created: {actual_width}x{actual_height}")
        
        # Update global constants to match ACTUAL window size
        global WINDOW_WIDTH, WINDOW_HEIGHT, MAP_WIDTH, MAP_HEIGHT, BOTTOM_UI_Y, TOP_PANEL_HEIGHT, BOTTOM_UI_HEIGHT
        WINDOW_WIDTH = actual_width
        WINDOW_HEIGHT = actual_height
        
        # Calculate UI layout for ACTUAL window size (not requested size)
        _ui_layout = UIScaler.calculate_ui_layout(actual_width, actual_height)
        TOP_PANEL_HEIGHT = _ui_layout['top_height']
        BOTTOM_UI_HEIGHT = _ui_layout['bottom_height']
        MAP_WIDTH = WINDOW_WIDTH
        MAP_HEIGHT = _ui_layout['map_height']
        BOTTOM_UI_Y = _ui_layout['bottom_y']
        
        # Update native resolution to match actual size (fixes display scaling)
        if (actual_width, actual_height) != (initial_width, initial_height):
            logger.warning(f"Display scaling detected! Requested: {initial_width}x{initial_height}, Actual: {actual_width}x{actual_height}")
            logger.info("Recalculating UI for actual size...")
            self.native_resolution = (actual_width, actual_height)
        
        logger.info(f"UI Layout Calculated: Top={TOP_PANEL_HEIGHT}px, Map={MAP_HEIGHT}px, Bottom={BOTTOM_UI_HEIGHT}px, BottomY={BOTTOM_UI_Y}px, Total={TOP_PANEL_HEIGHT + MAP_HEIGHT + BOTTOM_UI_HEIGHT}px (should equal {WINDOW_HEIGHT}px)")
        
        # Verify layout adds up correctly
        total_height = TOP_PANEL_HEIGHT + MAP_HEIGHT + BOTTOM_UI_HEIGHT
        if total_height != WINDOW_HEIGHT:
            logger.warning(f"Layout mismatch! Total={total_height}px but Window={WINDOW_HEIGHT}px, Difference: {WINDOW_HEIGHT - total_height}px")
        else:
            logger.info("Layout verification: Perfect fit!")
        logger.info("=" * 60)

        # Store layout values as instance attributes for access by sub-modules (e.g., MapRenderer)
        # This avoids circular imports when sub-modules need these values
        self.TOP_PANEL_HEIGHT = TOP_PANEL_HEIGHT
        self.BOTTOM_UI_HEIGHT = BOTTOM_UI_HEIGHT
        self.MAP_HEIGHT = MAP_HEIGHT

        # Load territory polygons
        map_data.load_polygons()
        if not map_data.TERRITORY_POLYGONS:
            logger.error("No territory polygons loaded! Please run polygon_tool.py first to define territories.")
            sys.exit(1)
        
        # Calculate scaling factors to fit map in window
        # Try to fit map while maintaining aspect ratio
        width_scale = MAP_WIDTH / ORIGINAL_MAP_WIDTH
        height_scale = MAP_HEIGHT / ORIGINAL_MAP_HEIGHT
        
        # Use the smaller scale to ensure map fits completely
        self.scale_factor = min(width_scale, height_scale)
        
        # Calculate actual map dimensions after scaling
        self.map_width = int(ORIGINAL_MAP_WIDTH * self.scale_factor)
        self.map_height = int(ORIGINAL_MAP_HEIGHT * self.scale_factor)
        
        logger.info(f"Window: {WINDOW_WIDTH}x{WINDOW_HEIGHT}, Map scaled to: {self.map_width}x{self.map_height}, Scale factor: {self.scale_factor:.2f}")
        
        # Load and scale the map image
        try:
            # Use campaign-specific map if provided, otherwise load from map directory
            if self.campaign_map:
                map_path = self.campaign_map
            else:
                # Multi-map support: load from maps/{map_id}/ directory or default
                map_id = map_data.get_current_map_id() or 'avareon'
                map_dir = map_data.get_map_directory(map_id)
                candidate = os.path.join(map_dir, 'map.png')
                if os.path.exists(candidate):
                    map_path = candidate
                elif map_id == 'avareon':
                    map_path = "assets/map.png"
                else:
                    map_path = None  # No background — use dark fallback

            logger.info(f"Loading map: {map_path}")
            # Remembered so the east map extension can find an optional painted
            # '<background>_east.png' beside it (rendering/map_extension.py)
            self.map_background_path = map_path

            # Load original high-resolution image (4096×3072) in display format.
            # The .convert() inside _load_map_background saves ~9ms per frame.
            self.map_image_original = _load_map_background(map_path)

            # Create scaled version for initial display
            # But keep original for high-quality zooming!
            self.map_image = pygame.transform.scale(self.map_image_original, (self.map_width, self.map_height))
        except pygame.error as e:
            logger.error(f"Error loading map: {e}")
            # Last-resort fallback
            self.map_background_path = None
            self.map_image_original = _load_map_background(None)
            self.map_image = pygame.transform.scale(self.map_image_original, (self.map_width, self.map_height))
        
        # Load bottom panel background image
        try:
            bottom_panel_original = pygame.image.load("assets/BottomPanel.jpg")
            # Scale to fit window width and bottom UI height
            # Image top edge will align with BOTTOM_UI_Y
            self.bottom_panel_image = pygame.transform.scale(
                bottom_panel_original, 
                (WINDOW_WIDTH, BOTTOM_UI_HEIGHT)
            )
            logger.info("Bottom panel image loaded successfully")
        except pygame.error as e:
            logger.warning(f"Could not load BottomPanel.jpg: {e}. Using solid color fallback")
            self.bottom_panel_image = None  # Fallback to solid color
        
        # Load top panel background image
        try:
            top_panel_original = pygame.image.load("assets/TopPanel.jpg")
            # Scale to fit window width and top panel height
            # Image bottom edge will align with bottom of top panel
            self.top_panel_image = pygame.transform.scale(
                top_panel_original,
                (WINDOW_WIDTH, TOP_PANEL_HEIGHT)
            )
            logger.info("Top panel image loaded successfully")
        except pygame.error as e:
            logger.warning(f"Could not load TopPanel.jpg: {e}. Using solid color fallback")
            self.top_panel_image = None  # Fallback to solid color

        # Load resource slot assets (for enhanced top panel stats display)
        # Purpose: Replace text-based stats with visual resource slots showing Taxation, Command, Gold, Income
        # H1 fix: added convert_alpha() + try/except guard for missing assets
        try:
            self.resource_slot_img = pygame.image.load("assets/ResourceSlot.png").convert_alpha()
            self.taxation_icon = pygame.image.load("assets/TXTPTS.png").convert_alpha()
            self.command_icon = pygame.image.load("assets/CMDPTS.png").convert_alpha()
            self.gold_icon = pygame.image.load("assets/GLDPTS.png").convert_alpha()
            self.income_icon = pygame.image.load("assets/INCPTS.png").convert_alpha()
        except pygame.error as e:
            logger.warning(f"Could not load resource slot assets: {e}")
            self.resource_slot_img = None
            self.taxation_icon = None
            self.command_icon = None
            self.gold_icon = None
            self.income_icon = None
        # H2 fix: added try/except guard for menu/UI images
        try:
            self.menu_button_img = pygame.image.load("assets/GMenuButton.png").convert_alpha()
            self.ingame_menu_bg = pygame.image.load("assets/InGameMenuBG.png").convert_alpha()
            self.ingame_options_menu_bg = pygame.image.load("assets/IGOptMenuBG.png").convert_alpha()
            self.main_menu_button_img = pygame.image.load("assets/MainMenuButtonNew.png").convert_alpha()
        except pygame.error as e:
            logger.warning(f"Could not load menu UI assets: {e}")
            self.menu_button_img = None
            self.ingame_menu_bg = None
            self.ingame_options_menu_bg = None
            self.main_menu_button_img = None
        
        # Load PNG particle images for visual effects (white soft-glow, tinted per ability)
        # Particle_Cropped.png: used for passive auras + embargo (smooth round glow)
        # Particle2_Cropped.png: used for active ability effects (burst, arc, polygon burst)
        try:
            self._haste_particle_base = pygame.image.load("assets/Particle_Cropped.png").convert_alpha()
        except pygame.error as e:
            logger.warning(f"Could not load Particle_Cropped.png: {e}")
            self._haste_particle_base = None
        try:
            self._active_particle_base = pygame.image.load("assets/Particle2_Cropped.png").convert_alpha()
        except pygame.error as e:
            logger.warning(f"Could not load Particle2_Cropped.png: {e}")
            self._active_particle_base = None

        # Load right sidebar background image
        # Calculate sidebar height (map height between top and bottom panels)
        sidebar_height = WINDOW_HEIGHT - TOP_PANEL_HEIGHT - BOTTOM_UI_HEIGHT
        try:
            right_panel_original = pygame.image.load("assets/RightPanel.jpg").convert()  # opaque JPG: display format for fast per-frame blits
            # Scale to fit sidebar width and height
            # Image left edge will align with left edge of sidebar
            self.right_panel_image = pygame.transform.scale(
                right_panel_original,
                (UIConstants.SIDEBAR_WIDTH, sidebar_height)
            )
            logger.info("Right panel image loaded successfully")
        except pygame.error as e:
            logger.warning(f"Could not load RightPanel.jpg: {e}. Using solid color fallback")
            self.right_panel_image = None  # Fallback to solid color

        # Load separator image for bottom UI
        # Use full panel height (no margins) so decorative pillar extends full height
        separator_height = BOTTOM_UI_HEIGHT
        try:
            separator_original = pygame.image.load("assets/Separator1.png").convert_alpha()
            original_width = separator_original.get_width()
            original_height = separator_original.get_height()

            # Squish horizontally to make it thinner while keeping full height
            # Original is 174px wide, we'll compress it to 30px for a thin divider
            target_width = 30

            # Scale to target dimensions (squish width, match panel height)
            self.separator_image = pygame.transform.smoothscale(
                separator_original,
                (target_width, separator_height)
            )
            self.separator_width = target_width
            logger.info(f"Separator image loaded successfully ({target_width}x{separator_height}), compressed from {original_width}px to {target_width}px")
        except pygame.error as e:
            logger.warning(f"Could not load Separator1.png: {e}. Using line separator fallback")
            self.separator_image = None
            self.separator_width = 3  # Fallback to line width

        # Load TableBorder.png for territory preview frame in bottom UI
        try:
            self._preview_border_original = pygame.image.load("assets/TableBorder.png").convert_alpha()
        except pygame.error as e:
            logger.warning(f"Could not load TableBorder.png: {e}. Territory preview border disabled.")
            self._preview_border_original = None

        # Territory preview caches (invalidated on resolution change)
        self._territory_preview_cache = {}  # Keyed by (territory, w, h) → surface or None
        self._scaled_preview_border = None  # Cached scaled TableBorder
        self._scaled_preview_border_size = None  # (w, h) of cached border
        self.territory_preview_rect = None  # Hover detection rect for preview image

        # Scale polygons and centers to match map scaling
        # Using round() instead of int() for better precision and smoother polygon edges
        self.scaled_polygons = {}
        self.scaled_centers = {}
        for territory, polygon in map_data.TERRITORY_POLYGONS.items():
            self.scaled_polygons[territory] = [
                (round(x * self.scale_factor), round(y * self.scale_factor))
                for x, y in polygon
            ]
        for territory, center in map_data.TERRITORY_CENTERS.items():
            self.scaled_centers[territory] = (
                round(center[0] * self.scale_factor),
                round(center[1] * self.scale_factor)
            )

        # Scale plot positions to match map scaling
        self.scaled_plots = {}
        for territory, plots in map_data.TERRITORY_PLOTS.items():
            self.scaled_plots[territory] = [
                (round(x * self.scale_factor), round(y * self.scale_factor))
                for x, y in plots
            ]
        
        # Setup config will be passed to initialize_game method
        # This is now handled externally (from main loop)
        self.setup_config = None
        self.game_state = None

        # Use global sound manager for all sound effects
        # Purpose: Play random army composition sounds when selecting units and UI click sounds
        self.sound_manager = sound_manager

        # Multiplayer networking
        self.network_connection = network_connection
        self.multiplayer_mode = (network_connection is not None)
        self.local_player_index = None  # Will be set from network connection
        # Sync fix: queue FULL_STATE_SYNC if received during battles/animations
        self._pending_full_state_sync = None

        # Window focus tracking — throttle FPS when unfocused (Steam requirement)
        self._window_focused = True

        # Multiplayer disconnect dialog
        self.show_disconnect_dialog = False
        self.disconnect_dialog_reason = ""
        self.disconnect_dialog_shown = False

        # Start-game camera animation (zoom to player's starting territory)
        # Created in initialize_game() for Custom Game and Multiplayer modes
        self.start_camera_animation = None
        # Flag indicating a zoom animation (start/campaign animation, or mouse-wheel
        # settle) is active. NOTE: the old comment here claimed the rendering pipeline
        # used this to "skip expensive operations (smoothscale, overlay rebuild)" —
        # that was never true of the overlay (map_renderer.py has never read this
        # flag), and the smoothscale downgrade is gone now that the map rescale is
        # viewport-sized. Kept as camera state for animation-aware logic.
        self.is_zoom_animating = False

        # Phase 4A: Initialize all attributes to defaults so hasattr() guards are unnecessary.
        # These are set properly in initialize_game() or by rendering methods, but need
        # safe defaults here to prevent AttributeError if accessed before those methods run.

        # Feature-related (set in initialize_game or campaign launcher)
        self.tutorial_mission = None
        self.sim_state = None
        self.sim_ai = None
        self.last_sim_round = 0
        self.game_start_time = None

        # UI button rects (set by draw methods and ui_renderer.py)
        self.end_turn_button = None
        self.main_menu_button = None
        self.disconnect_exit_button = None
        self.train_buttons = {}
        self.queue_cancel_buttons = []
        self.demolish_barracks_button = None
        self.hero_train_buttons = {}
        self.hero_cancel_button = None
        self.demolish_keep_button = None
        self.building_buttons = {}
        self.cancel_button = None
        self.demolish_button = None
        self.territory_info_plot_buttons = []
        self.select_all_button = None
        self.deselect_all_button = None
        self.castle_upgrade_button = None
        self.castle_upgrade_cancel_button = None
        self.bonuses_button_rect = None
        self.resolve_all_battles_button = None  # "Resolve Remaining Battles" button rect (below top panel during battle phase)
        self.sidebar_tab_buttons = {}
        self.hero_selection_buttons = {}
        self.technology_buttons = {}

        # Options panel UI elements (set by ui_renderer.py)
        self.gameplay_edge_scrolling_checkbox = None
        self.gameplay_edge_scroll_mode_dropdown = None
        self.gameplay_tooltips_checkbox = None
        self.gameplay_tooltip_delay_dropdown = None
        self.gameplay_pan_speed_slider = None
        self.gameplay_zoom_speed_slider = None
        self.gameplay_fps_checkbox = None
        # Audio volume sliders (populated by ui_renderer when options panel is drawn)
        self.audio_master_slider = None
        self.audio_music_slider = None
        self.audio_sfx_slider = None

        # State flags and timers (set lazily in run loop)
        self.castle_button_is_hovering = False
        self._sim_last_timer_sync = 0
        self._ai_battle_delay_timer = 0.0
        self._ai_battle_territory = None
        self._battle_sound_played = False  # Once-per-turn guard for battle sound
        self._ai_alliance_delay_timer = 0.0
        self._ai_alliance_territory = None

        # Performance caches (created lazily on first use)
        self._ai_indicator_overlay = None
        self._ai_indicator_title_font = None
        self._ai_indicator_subtitle_font = None

    def _reload_map_assets(self, map_id):
        """Reload map image and rescale polygons/centers/plots for a different map.
        Called from initialize_game() when the selected map differs from the default."""
        # Skip map image reload for campaign missions — campaign_map was already loaded
        # in __init__ and must not be overwritten with the default avareon map image
        if not self.campaign_map:
            map_dir = map_data.get_map_directory(map_id)
            candidate = os.path.join(map_dir, 'map.png')
            if os.path.exists(candidate):
                map_path = candidate
            elif map_id == 'avareon':
                map_path = "assets/map.png"
            else:
                map_path = None

            try:
                # Display-format load (see _load_map_background) — applies to every
                # map, including Azincournean Highlands and future backgrounds.
                self.map_background_path = map_path
                self.map_image_original = _load_map_background(map_path)
                self.map_image = pygame.transform.scale(self.map_image_original, (self.map_width, self.map_height))
            except pygame.error as e:
                logger.error(f"Error reloading map image for '{map_id}': {e}")
                self.map_background_path = None
                self.map_image_original = _load_map_background(None)
                self.map_image = pygame.transform.scale(self.map_image_original, (self.map_width, self.map_height))

            # Drop the viewport map cache (and the east extension built from the old
            # background) so the new one is picked up even if the camera happens to
            # be in exactly the same position.
            self._invalidate_map_background_caches()

        # Rescale polygons from the newly loaded map_data globals
        self.scaled_polygons = {}
        self.scaled_centers = {}
        for territory, polygon in map_data.TERRITORY_POLYGONS.items():
            self.scaled_polygons[territory] = [
                (round(x * self.scale_factor), round(y * self.scale_factor))
                for x, y in polygon
            ]
        for territory, center in map_data.TERRITORY_CENTERS.items():
            self.scaled_centers[territory] = (
                round(center[0] * self.scale_factor),
                round(center[1] * self.scale_factor)
            )

        # Rescale plot positions
        self.scaled_plots = {}
        for territory, plots in map_data.TERRITORY_PLOTS.items():
            self.scaled_plots[territory] = [
                (round(x * self.scale_factor), round(y * self.scale_factor))
                for x, y in plots
            ]

        logger.info(f"Reloaded map assets for '{map_id}': {len(self.scaled_polygons)} territories, {len(self.scaled_plots)} plot sets")

    def scale(self, value):
        """
        Scale a UI dimension based on current resolution.
        Reference: 1600x900 (scale = 1.0)

        Args:
            value: Base value at 1600x900 resolution

        Returns:
            Scaled value for current resolution

        Example:
            button_width = self.scale(210)  # 210px at 1600x900, scales for other resolutions
        """
        return int(value * self.ui_scale)

    def initialize_game(self, setup_config):
        """Initialize game state with setup configuration"""
        # Import settings for gameplay config (edge scrolling, tooltips, etc.) used later in this method
        from settings_manager import settings
        self.setup_config = setup_config

        # Load selected map data (multi-map support)
        map_id = setup_config.get('map_id', 'avareon')
        map_data.load_map(map_id)
        logger.info(f"Game using map: {map_id}")

        # Reload map image and rescale polygons/centers/plots for the selected map
        # (Game.__init__ loaded Avareon by default — override with correct map here)
        self._reload_map_assets(map_id)

        # Every game starts with the sidebar expanded (the new GameState below sets
        # sidebar_expanded=True); drop any slide left over from a previous game.
        self._sidebar_anim_start_ms = None
        self._reset_sidebar_scroll()

        # Game state - use configuration from setup UI with skip_setup_phase=True
        game_mode = setup_config.get('game_mode', 'sequential')
        self.game_state = GameState(
            num_players=setup_config['num_players'],
            player_is_ai=setup_config['player_is_ai'],
            player_ai_difficulty=setup_config['player_ai_difficulty'],
            player_teams=setup_config.get('player_teams'),  # Team assignments (if provided)
            skip_setup_phase=True,
            network_mode=self.multiplayer_mode,
            local_player_index=self.local_player_index,
            taxation_level=setup_config.get('taxation_level', 0),  # Taxation level (0-4, default 0)
            victory_condition=setup_config.get('win_condition', 'Domination (45+)'),  # Victory condition string
            game_mode=game_mode  # Turn mode: 'sequential' or 'simultaneous'
        )

        # Store additional options from setup for future game logic use
        self.neutral_armies = setup_config.get('neutral_armies', False)
        self.randomize_bonuses = setup_config.get('randomize_bonuses', False)

        # Gold transfer setting — 0=Disabled, 1=25%, 2=50%, 3=75%, 4=100%.
        # Campaign missions never set this key, so campaigns default to Disabled.
        gold_transfer_idx = setup_config.get('gold_transfer', 0)
        self.game_state.gold_transfer_pct = [0, 25, 50, 75, 100][max(0, min(gold_transfer_idx, 4))]

        # Randomize territory bonuses if enabled (not used in campaign — campaign never sets this flag)
        if self.randomize_bonuses:
            bonus_mapping = setup_config.get('bonus_mapping')
            if bonus_mapping:
                # Multiplayer client: apply host-provided mapping
                map_data.apply_territory_bonuses(bonus_mapping)
            else:
                # Single-player or multiplayer host: generate random mapping
                map_data.randomize_territory_bonuses()

        # Debug: Log player configuration
        logger.info(f"Game init: num_players={setup_config['num_players']}, player_is_ai={setup_config['player_is_ai']}, game_mode={game_mode}")

        # Wrap with SimultaneousGameState if in simultaneous mode
        self.sim_state = None  # Simultaneous mode state wrapper
        self.sim_ai = None  # Simultaneous mode AI adapter
        if game_mode == 'simultaneous':
            from simultaneous import SimultaneousGameState, SimPhaseManager, SimultaneousAI
            import ai_player  # For AI decision logic
            self.sim_state = SimultaneousGameState(self.game_state)
            self.sim_state.phase_manager = SimPhaseManager(self.sim_state)
            self.sim_ai = SimultaneousAI(self.sim_state, ai_player)
            # The local human's clicks execute immediately and are also queued as sim
            # orders; the executor must skip those copies in single-player as well
            self.sim_state.click_executed_player = self.get_local_player()
            # Set multiplayer flags for proper execution coordination
            # - Clients wait for SIM_ALL_READY from host
            # - Host sends SIM_ALL_READY when all ready via callback
            if self.multiplayer_mode and self.local_player_index is not None:
                # Set local player index for order validation
                # Remote player orders skip garrison validation (already validated on sender)
                self.sim_state.local_player_index = self.local_player_index
                if self.local_player_index != 0:
                    # Client: wait for SIM_ALL_READY, don't execute locally
                    self.sim_state.is_multiplayer_client = True
                    logger.info(f"[SIM] Configured as multiplayer CLIENT (local_player_index={self.local_player_index})")
                else:
                    # Host: use callbacks for network broadcasting
                    self.sim_state.is_multiplayer_host = True
                    self.sim_state.on_all_ready_callback = self._sim_start_execution_phase
                    self.sim_state.on_round_complete_callback = self._sim_broadcast_round_complete
                    logger.info("[SIM] Configured as multiplayer HOST with callbacks")
        # Set reference to game instance for accessing scaled_centers, etc.
        self.game_state.game = self

        # Pre-claim territories from setup (dynamic for all players)
        num_players = setup_config.get('num_players', 2)

        # Use player_territories dict if available (new 2-4 player format)
        # Fall back to legacy player1_territory, player2_territory for backwards compatibility
        player_territories = setup_config.get('player_territories', {})

        # Debug: Log territory config
        logger.debug(f"INIT num_players: {num_players}, player_territories: {player_territories}")
        logger.debug(f"INIT Legacy player1_territory: {setup_config.get('player1_territory')}, player2_territory: {setup_config.get('player2_territory')}")

        for player_index in range(num_players):
            # Try new format first (player_territories dict), then legacy format
            territory = player_territories.get(player_index)
            if not territory:
                territory_key = f'player{player_index + 1}_territory'
                territory = setup_config.get(territory_key)
            if territory:
                self.game_state.territory_owners[territory] = player_index
                self.game_state._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                self.game_state.invalidate_territorial_bonus_cache()  # Ownership changed

                # Store starting territory for Capital Assault victory condition
                if player_index not in self.game_state.player_starting_territories:
                    self.game_state.player_starting_territories[player_index] = territory
                    logger.debug(f"Stored Player {player_index} starting territory: {territory}")

                # Set player name from config (multiplayer) or generate for AI
                config_player_names = setup_config.get('player_names', {})
                if player_index in config_player_names:
                    self.game_state.player_names[player_index] = config_player_names[player_index]
                elif self.game_state.player_is_ai[player_index]:
                    self.game_state.player_names[player_index] = f"Empire of {territory}"

                # Create starting army composition (1 Swordsman, 1 Archer, 1 Pikeman)
                army_units = [
                    {'type': 'Swordsman', 'status': 'ready', 'order': None, 'id': 0, 'xp': 0, 'level': 0},
                    {'type': 'Archer', 'status': 'ready', 'order': None, 'id': 1, 'xp': 0, 'level': 0},
                    {'type': 'Pikeman', 'status': 'ready', 'order': None, 'id': 2, 'xp': 0, 'level': 0}
                ]

                # Set garrison as source of truth
                self.game_state.set_garrison_armies(territory, player_index, unmoved=3, moved=0, units=army_units)

                self.game_state.territories_chosen[player_index] = 1

        # Neutral Armies: place small hostile garrisons on all unclaimed territories
        if self.neutral_armies:
            # Use seeded RNG for multiplayer determinism (all clients get same seed via setup_config)
            neutral_seed = setup_config.get('game_seed', int(time.time() * 1000) % (2**31))
            neutral_rng = random.Random(neutral_seed)
            combat_unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']

            # Collect player-owned territories to check adjacency
            player_territories = {t for t, owner in self.game_state.territory_owners.items() if owner != -1}

            for territory, owner in self.game_state.territory_owners.items():
                if owner != -1:
                    continue  # Skip player-owned territories

                # Territories adjacent to a player start get 1 unit, others get 2
                neighbors = map_data.get_neighbors(territory)
                adjacent_to_player = any(n in player_territories for n in neighbors)
                num_units = 1 if adjacent_to_player else 2

                # Build random army composition from the 4 combat unit types
                army_units = []
                for i in range(num_units):
                    unit_type = neutral_rng.choice(combat_unit_types)
                    army_units.append({
                        'type': unit_type, 'status': 'ready', 'order': None,
                        'id': i, 'xp': 0, 'level': 0
                    })

                # Place neutral garrison (player_index = -1)
                self.game_state.add_garrison(territory, -1, unmoved=num_units, moved=0, units=army_units)

            logger.info(f"[NEUTRAL ARMIES] Placed neutral garrisons on {sum(1 for o in self.game_state.territory_owners.values() if o == -1)} unclaimed territories (seed={neutral_seed})")

        # Start in playing phase
        self.game_state.current_player = 0
        self.game_state.planning_phase_start_time = time.time()
        self.game_start_time = time.time()  # Track overall game elapsed time

        # SIMULTANEOUS MODE: Start initial planning phase and trigger AI planning
        if self.sim_state is not None:
            # In simultaneous mode, set current_player to the local (human) player
            # This ensures all UI interactions use the correct player
            local_player = self.get_local_player()
            self.game_state.current_player = local_player
            logger.info(f"[SIMULTANEOUS] Set current_player to local player {local_player}")

            self.sim_state.start_planning_phase()
            # Start AI planning for all AI players
            if self.sim_ai is not None:
                self.sim_ai.start_planning_phase()
            # Track round number to detect when new rounds start
            self.last_sim_round = self.sim_state.round_number
            # Trigger Turn 1 announcement at game start
            self.turn_announcement_effect = TurnAnnouncementEffect(
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
                custom_text="Turn 1",
                on_complete=None
            )
            logger.info("[SIMULTANEOUS] Started initial planning phase with Turn 1 announcement")

        # Update previous_player to match
        self.previous_player = self.game_state.current_player

        # Load hero portrait images
        self.hero_images = {}
        for hero_name, hero_info in self.game_state.HERO_TYPES.items():
            if 'icon' in hero_info:
                try:
                    hero_image = pygame.image.load(hero_info['icon']).convert_alpha()
                    self.hero_images[hero_name] = hero_image
                    logger.debug(f"Loaded hero portrait: {hero_name}")
                except pygame.error as e:
                    logger.warning(f"Could not load {hero_info['icon']}: {e}. Using letter fallback for {hero_name}")
                    self.hero_images[hero_name] = None
            else:
                self.hero_images[hero_name] = None  # No icon specified, use letter

        # Load hero ability icons
        self.ability_images = {}  # {(hero_name, ability_index): pygame.Surface or None}
        for hero_name, hero_info in self.game_state.HERO_TYPES.items():
            if 'abilities' in hero_info and hero_info['abilities']:
                for ability_index, ability in enumerate(hero_info['abilities']):
                    if 'icon' in ability:
                        try:
                            ability_image = pygame.image.load(ability['icon']).convert_alpha()
                            self.ability_images[(hero_name, ability_index)] = ability_image
                            logger.debug(f"Loaded ability icon: {hero_name} - {ability['name']}")
                        except pygame.error as e:
                            logger.warning(f"Could not load {ability['icon']}: {e}. Using placeholder for {ability['name']}")
                            self.ability_images[(hero_name, ability_index)] = None
                    else:
                        self.ability_images[(hero_name, ability_index)] = None

        # AI player instances (initialized later when needed)
        self.ai_players = {}

        # Turn announcement effect (Bug 1 fix: only init to None if not already set by sim mode above)
        if not hasattr(self, 'turn_announcement_effect') or self.turn_announcement_effect is None:
            self.turn_announcement_effect = None  # Active turn announcement animation

        # Hero images and ability images already loaded above (lines 397-427)
        # DO NOT reset them here or they will be wiped out!

        # Load army flag icons for map display
        # Format: {player_index: {tier: pygame.Surface}}
        # tier 1: 1-4 armies, tier 2: 5-9 armies, tier 3: 10+ armies
        self.army_flag_icons = {}
        # Load all 4 player flag colors (Red, Blue, Green, Yellow)
        player_flag_colors = ['Red', 'Blue', 'Green', 'Yellow']
        for player_index in range(len(player_flag_colors)):
            color_name = player_flag_colors[player_index]
            self.army_flag_icons[player_index] = {}
            for tier in range(1, 4):  # Tiers 1, 2, 3
                flag_path = f"assets/mapicons/{color_name}Flag{tier}.png"
                try:
                    flag_image = pygame.image.load(flag_path).convert_alpha()
                    self.army_flag_icons[player_index][tier] = flag_image
                    logger.debug(f"Loaded flag icon: {color_name}Flag{tier}.png")
                except pygame.error as e:
                    logger.warning(f"Could not load {flag_path}: {e}. Flag icon will not be displayed for Player {player_index + 1} tier {tier}")
                    self.army_flag_icons[player_index][tier] = None

        # Neutral armies use NeutralFlag.png, scaled to match each tier's flag size
        self.army_flag_icons[-1] = {}
        try:
            neutral_flag_base = pygame.image.load("assets/NeutralFlag.png").convert_alpha()
            for tier in range(1, 4):
                source_flag = self.army_flag_icons.get(0, {}).get(tier)
                if source_flag:
                    scaled = pygame.transform.smoothscale(neutral_flag_base, source_flag.get_size())
                    self.army_flag_icons[-1][tier] = scaled
                else:
                    self.army_flag_icons[-1][tier] = neutral_flag_base.copy()
        except pygame.error as e:
            logger.warning(f"Could not load NeutralFlag.png: {e}. Falling back to gray-tinted flags.")
            for tier in range(1, 4):
                source_flag = self.army_flag_icons.get(0, {}).get(tier)
                if source_flag:
                    gray_flag = source_flag.copy()
                    gray_flag.fill((150, 150, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    self.army_flag_icons[-1][tier] = gray_flag
                else:
                    self.army_flag_icons[-1][tier] = None

        # Load building icons for map display
        # Format: {building_name: pygame.Surface}
        self.building_icons = {}
        building_names = ['Square', 'Keep', 'Castle', 'Barracks', 'Farm', 'Mine', 'Plot', 'Training Grounds']
        for building_name in building_names:
            # Strip spaces for filename (e.g. 'Training Grounds' -> 'TrainingGroundsIcon.png')
            icon_filename = building_name.replace(' ', '')
            icon_path = f"assets/mapicons/{icon_filename}Icon.png"
            try:
                building_image = pygame.image.load(icon_path).convert_alpha()
                self.building_icons[building_name] = building_image
                logger.debug(f"Loaded building icon: {building_name}Icon.png")
            except pygame.error as e:
                logger.warning(f"Could not load {icon_path}: {e}. Building icon will not be displayed for {building_name}")
                self.building_icons[building_name] = None

        # Load unit type icons for UI display
        # Format: {unit_type: pygame.Surface}
        self.unit_icons = {}
        unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain']
        for unit_type in unit_types:
            icon_path = f"assets/mapicons/{unit_type}Icon.png"
            try:
                unit_image = pygame.image.load(icon_path).convert_alpha()
                self.unit_icons[unit_type] = unit_image
                logger.debug(f"Loaded unit icon: {unit_type}Icon.png")
            except pygame.error as e:
                logger.warning(f"Could not load {icon_path}: {e}. Unit icon will use letter fallback for {unit_type}")
                self.unit_icons[unit_type] = None

        # Load level shield icon for veterancy display
        self.level_shield_icon = None
        level_shield_path = "assets/upgrades/LevelDisplay.png"
        try:
            self.level_shield_icon = pygame.image.load(level_shield_path).convert_alpha()
            logger.debug("Loaded level shield icon: LevelDisplay.png")
        except pygame.error as e:
            logger.warning(f"Could not load {level_shield_path}: {e}. Level shields will not display")

        # Load icon border frame for UI display
        self.icon_border = None
        icon_border_path = "assets/mapicons/IconBorder.png"
        try:
            self.icon_border = pygame.image.load(icon_border_path).convert_alpha()

            # Brighten the border by 20% to make it stand out more
            if self.icon_border:
                # Create a copy to modify
                brightened = self.icon_border.copy()
                # Add brightness overlay (increases RGB values by 20%)
                bright_overlay = pygame.Surface(self.icon_border.get_size(), pygame.SRCALPHA)
                bright_overlay.fill((51, 51, 51, 0))  # 20% of 255 = 51
                brightened.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                self.icon_border = brightened

            logger.debug("Loaded icon border: IconBorder.png (brightened +20%)")
        except pygame.error as e:
            logger.warning(f"Could not load {icon_border_path}: {e}. Icons will display without border frame")

        # Load circle border frame for circular icons
        self.circle_border = None
        circle_border_path = "assets/mapicons/CircleBorder.png"
        try:
            self.circle_border = pygame.image.load(circle_border_path).convert_alpha()

            # Brighten the border by 20% to make it stand out more
            if self.circle_border:
                # Create a copy to modify
                brightened = self.circle_border.copy()
                # Add brightness overlay (increases RGB values by 20%)
                bright_overlay = pygame.Surface(self.circle_border.get_size(), pygame.SRCALPHA)
                bright_overlay.fill((25, 25, 25, 0))  # 10% of 255 = 25
                brightened.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                self.circle_border = brightened

            logger.debug("Loaded circle border: CircleBorder.png (brightened +20%)")
        except pygame.error as e:
            logger.warning(f"Could not load {circle_border_path}: {e}. Circular icons will display without border frame")

        # Load upgrade button icons
        self.castle_upgrade_icon = None
        try:
            self.castle_upgrade_icon = pygame.image.load("assets/upgrades/CastleUpgradeButton.png").convert_alpha()
            logger.debug("Loaded upgrade icon: CastleUpgradeButton.png")
        except pygame.error as e:
            logger.warning(f"Could not load CastleUpgradeButton.png: {e}")

        # Load spell border frames for hero abilities
        self.active_spell_border = None
        self.passive_spell_border = None
        try:
            self.active_spell_border = pygame.image.load("assets/heroes/abilities/ActiveSpellBorder1.png").convert_alpha()
            logger.debug("Loaded active spell border: ActiveSpellBorder1.png")
        except pygame.error as e:
            logger.warning(f"Could not load ActiveSpellBorder1.png: {e}. Active abilities will display without border frame")

        try:
            self.passive_spell_border = pygame.image.load("assets/heroes/abilities/PassiveSpellBorder1.png").convert_alpha()
            logger.debug("Loaded passive spell border: PassiveSpellBorder1.png")
        except pygame.error as e:
            logger.warning(f"Could not load PassiveSpellBorder1.png: {e}. Passive abilities will display without border frame")

        # FPS OPTIMIZATION 6.2: Pre-load bonus button icon
        # This icon is normally loaded on-demand when the bonus panel opens
        # Pre-loading eliminates the first-open delay
        self.bonus_button_icon_original = None
        self.bonus_button_icon = None
        self.bonus_button_icon_size = None
        try:
            self.bonus_button_icon_original = pygame.image.load('assets/BonusButton.png').convert_alpha()
            logger.debug("Pre-loaded bonus button icon: BonusButton.png")
        except pygame.error as e:
            logger.warning(f"Could not pre-load BonusButton.png: {e}")

        # UI state
        self.hovered_territory = None
        self.hovered_army = None  # Territory with army being hovered
        self.mouse_pos = (0, 0)  # Track mouse position for tooltip
        self.selected_plot = None  # (territory, plot_index) tuple
        self.selected_barracks = None  # (territory, barracks_plot_index) tuple
        self.selected_keep = None  # (territory, keep_plot_index) tuple
        self.selected_hero = None  # hero_name string
        self.hero_ability_buttons = {}  # {(hero_name, ability_index): pygame.Rect}
        self.hero_ability_images = {}  # {(hero_name, ability_index): pygame.Surface or None}

        # Unified hero bubble animation system (Phase 2B dedup)
        # Config-driven: each entry defines hero name(s), territory getter, color, rise speed
        self._bubble_configs = {
            'defiance': {
                'heroes': ('Seledra Rennervail',),
                'territory_getter': 'get_defiance_protected_territories',
                'color': (150, 50, 200),   # Purple
                'rise_speed': 7.5,
                'check_polygon': True,     # Full polygon check in update
                'spawn_interval': 0.07,    # Spawn cycle interval in seconds
                'spawn_chance': 0.85,      # Probability of spawning per cycle per territory
            },
            'haste': {
                'heroes': ('Vearen Asford',),
                'territory_getter': 'get_haste_affected_territories',
                'color': (255, 165, 0),    # Orange
                'rise_speed': 7.5,
                'check_polygon': True,
                'spawn_interval': 0.07,
                'spawn_chance': 0.85,
            },
            'safe_haven': {
                'heroes': ('Darius Brennhen', 'Regnus Aevencourne'),
                'territory_getter': 'get_safe_haven_territories',
                'color': (135, 206, 250),  # Light blue
                'rise_speed': 15,
                'check_polygon': False,    # Only bbox check in update
                'spawn_interval': 0.07,
                'spawn_chance': 0.85,
            },
        }
        # Per-effect state: bubbles list and spawn timer
        self._bubble_state = {key: {'bubbles': [], 'spawn_timer': 0} for key in self._bubble_configs}

        # PERFORMANCE: Surface cache for bubble effects (avoids per-frame allocations)
        # Key: (radius, color_tuple) -> Surface
        self._bubble_surface_cache = {}
        self._bubble_surface_cache_max_size = 50  # Limit cache size to prevent memory bloat

        # PERFORMANCE: Pre-built PNG particle caches for all aura effects
        # Per-effect dict: (diameter, quantized_alpha) -> pre-scaled, pre-tinted, pre-alpha'd Surface
        self._particle_caches = {}
        self._build_particle_caches()

        # PERFORMANCE: Surface cache for hero UI overlays (avoids per-frame allocations)
        # Key: size (int) -> dict of overlay surfaces
        self._hero_overlay_cache = {}

        # PERFORMANCE OPTIMIZATION: UI icon scaling cache for bottom/right panels
        # Prevents 50% FPS drop when panels open (80→40 FPS issue)
        # Key: (icon_id, size) -> scaled surface
        self._ui_icon_cache = {}  # For building icons, unit icons, ability icons
        self._tech_border_cache = {}  # For technology tree border frames by size

        # PERFORMANCE: Text rendering cache for frequently used static text
        # Key: (text, font_name, color) -> Surface
        # Cleared when game state changes significantly (new turn, etc.)
        self._text_cache = {}
        self._text_cache_max_size = 200  # Limit cache size

        # PERFORMANCE: Rotated text cache for sidebar collapsed tab labels
        # Key: tab_name -> rotated Surface (pygame.transform.rotate is expensive)
        self._rotated_tab_text_cache = {}
        self._sidebar_toggle_sprites = {}  # Round sidebar toggle button variants (_get_sidebar_toggle_sprite)

        # PERFORMANCE: Cached overlay surfaces to avoid per-frame SRCALPHA allocations
        # Each full-screen SRCALPHA surface is ~5.44MB — reuse instead of recreating
        self._cached_silence_fog = None          # Silence fog overlay (WINDOW_WIDTH x MAP_HEIGHT)
        self._cached_negotiator_surface = None   # Master Negotiator particles (full-screen)
        self._cached_targeting_cursor = None     # Targeting cursor image (TargetCircle.png, 60x60)
        self._cached_targeting_text_bg = None    # Targeting cursor text background
        self._cached_targeting_text = None       # Cached targeting instruction text
        self._cached_spectator_banner = None     # Spectator banner surface (500x50)
        self._cached_spectator_text = None       # Last spectator banner text rendered
        self._cached_action_log_surface = None   # Action log overlay (300x400)
        self._cached_victory_overlay = None      # Victory screen overlay (full-screen)
        self._cached_victory_scale = None        # Last victory image scale factor
        self._cached_victory_scaled_img = None   # Cached smoothscaled victory image
        self._cached_alliance_overlay = None     # Alliance popup dimming overlay (full-screen)
        self._cached_alliance_bg = None          # Cached scaled alliance popup background
        self._cached_alliance_bg_size = None     # Size the alliance bg was scaled to
        self._cached_building_overlays = {}      # Building icon overlays keyed by size
        self._cached_disconnect_overlay = None   # Disconnect dialog overlay (full-screen SRCALPHA)
        self._cached_defend_overlay = None       # Forced defend popup overlay (full-screen SRCALPHA)
        self._cached_training_overlays = {}      # Training icon overlays keyed by size

        # Ability targeting system
        self.ability_targeting_active = False  # Is player currently targeting with an ability?
        self.ability_targeting_hero = None  # Which hero's ability is being targeted
        self.ability_targeting_ability_index = None  # Which ability index
        self.ability_targeting_ability_name = None  # Name of the ability being targeted

        # Master Negotiator particle system
        self.master_negotiator_particles = []  # List of particle dicts
        self.master_negotiator_particle_spawn_accumulator = 0.0

        self.hovered_plot = None  # (territory, plot_index) tuple
        self.action_log_visible = False  # Toggle for action log overlay
        self.order_cancel_buttons = []  # List of (rect, order, player_order_index) for click detection
        self.order_sidebar_player = 0  # Player whose orders the Action Queue shows (set by ui_renderer)
        self.cancel_all_button = None  # Rect for cancel all button
        self.sidebar_toggle_button = None  # Rect for sidebar expand/collapse button
        self.resolve_battle_button = None  # Rect for battle resolution button
        self.selected_battle_index = None  # Which battle is selected (None = none selected)
        self.battle_popup_visible = False  # Is battle popup showing?
        self.battle_popup_state = 'initial'  # 'initial', 'resolving', 'result'
        self.close_popup_button = None  # Rect for close popup button
        self.selected_territory_info = None  # Territory clicked for info display
        self.battle_markers = []  # List of rects for clickable battle markers
        self.alliance_markers = []  # List of alliance markers for sim mode territory choice
        self.battle_result = None  # Store result of resolved battle for display

        # Alliance choice popup (simultaneous mode - territory ownership decision)
        self.alliance_choice_popup_visible = False
        self.alliance_choice_territory = None
        self.alliance_choice_players = []
        self.alliance_choice_chooser = None
        self.alliance_choice_popup_rect = None
        self.alliance_choice_buttons = []

        # Forced defend popup (simultaneous mode - overwhelming force notification)
        self.forced_defend_popup_visible = False
        self.forced_defend_popup_queue = []  # Queue of forced defend messages
        self.forced_defend_popup_current = None  # Current message being displayed
        self.forced_defend_popup_timer = 0  # Auto-close timer (seconds remaining)
        self.forced_defend_popup_rect = None
        self.forced_defend_close_button = None

        # Enhanced battle interface (cinematic battle UI)
        self.enhanced_battle_ui = None  # EnhancedBattleInterface instance when active
        self._resolved_battle_info = None  # Stores battle info after FIGHT click, before CLOSE

        # Battle Reports (on-map summaries of battles the local player did not watch).
        # Lives on Game, not GameState, following forced_defend_popup_queue above: this is
        # per-viewer UI state, so keeping it here keeps it out of save files, the state
        # checksum and full-state sync, where it would cause false desyncs.
        # Keyed by player index rather than just the local player so hotseat works --
        # get_local_player() returns the first non-AI player, which is 0 for both humans.
        self.battle_report_queues = {}        # {player_index: [snapshot, ...]}
        self.battle_report_popups = []        # The viewer's snapshots, currently on screen
        self.battle_report_rects = []         # [(rect, action, snapshot)], rebuilt every draw
        self.battle_report_detail_ui = None   # EnhancedBattleInterface in report-only mode
        self.battle_report_renderer = None    # Lazily built BattleReportPopupRenderer
        self._battle_report_detail_source = None  # Report the detail screen is showing
        self._battle_report_planning_owner = None  # Whose planning phase is running
        self.close_all_battle_reports_button = None

        # Victory/defeat cinematic sequence (custom & multiplayer games)
        # Waits for all animations to complete, then plays fade→image→hold→auto-recap
        self.victory_sequence_pending = False   # phase='ended' detected, waiting for animations
        self.victory_sequence_active = False    # cinematic animation is playing
        self.victory_phase = None               # 'fade' | 'image_grow' | 'image_hold'
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0             # 0-255 for black overlay
        self.victory_image = None               # loaded PNG surface (victoryscrn or defeatscrn)
        self.victory_image_scale = 0.0          # 0.0-0.75 for image grow animation
        self.victory_is_win = True              # True=victory, False=defeat for local player

        # Chat system state
        self.chat_input_active = False  # Is chat input box open?
        self.chat_input_text = ""  # Current text being typed
        self.chat_channel = 'all'  # Current chat channel: 'all' or 'team' (TAB to toggle)
        # (Chat / Action Log scrolling: pixel ScrollStates in self.sidebar_scroll)
        
        # Gameplay Settings (configurable via Options menu)
        # MUST be defined BEFORE hover_delay system since hover_delay references tooltip_delay_ms
        # Load from settings manager
        self.edge_scrolling_enabled = settings.get('edge_scrolling_enabled', True)
        self.edge_scrolling_mode = settings.get('edge_scrolling_mode', 'window_edge')
        self.tooltips_enabled = settings.get('tooltips_enabled', True)
        self.tooltip_delay_ms = settings.get('tooltip_delay_ms', 500)
        self.camera_pan_speed = settings.get('camera_pan_speed', 10.0)
        self.camera_zoom_speed = settings.get('camera_zoom_speed', 1.1)
        self.show_fps = settings.get('show_fps', False)

        # Audio volume settings
        self.master_volume = settings.get('master_volume', 0.8)
        self.music_volume = settings.get('music_volume', 0.5)
        self.sfx_volume = settings.get('sfx_volume', 0.5)

        # Temporary gameplay settings (for Options menu - applied on Apply button)
        self.temp_edge_scrolling_enabled = self.edge_scrolling_enabled
        self.temp_edge_scrolling_mode = self.edge_scrolling_mode
        self.temp_tooltips_enabled = self.tooltips_enabled
        self.temp_tooltip_delay_ms = self.tooltip_delay_ms
        self.temp_camera_pan_speed = self.camera_pan_speed
        self.temp_camera_zoom_speed = self.camera_zoom_speed
        self.temp_show_fps = self.show_fps
        self.temp_master_volume = self.master_volume
        self.temp_music_volume = self.music_volume
        self.temp_sfx_volume = self.sfx_volume

        # Hover delay system (0.5 seconds before showing tooltips)
        self.hover_start_time = None  # When hover began (for map: army/territory)
        self.hover_target_territory = None  # What territory we're hovering over
        self.hover_target_army = None  # What army we're hovering over
        self.hover_delay = self.tooltip_delay_ms  # Delay in milliseconds (now configurable)
        self.show_tooltip_territory = None  # Territory to show tooltip for (after delay)
        self.show_tooltip_army = None  # Army to show tooltip for (after delay)
        
        # UI Tooltip tracking (for buttons) - SEPARATE timer for independence
        self.hover_start_time_button = None  # When button hover began (separate from map hover)
        self.hover_target_button = None  # What button we're hovering over (type, key)
        self.show_tooltip_button = None  # Button to show tooltip for (after delay)
        
        # Click flash feedback system
        self.clicked_element = None  # (type, identifier) tuple - element currently showing click flash
        self.click_flash_timer = 0  # Milliseconds remaining for click flash
        self.click_flash_duration = CLICK_FLASH_DURATION_MS  # Flash duration in milliseconds
        
        # Game menu system
        self.game_menu_visible = False  # Is game menu open?
        self.menu_button = None  # Rect for menu button in top panel
        self.menu_resume_button = None  # Rect for Resume Game button
        self.menu_save_button = None  # Rect for Save Game button (campaign only)
        self.menu_options_button = None  # Rect for Options button
        self.menu_quit_button = None  # Rect for Quit to Main Menu button

        # Players window — non-pausing modal listing all players (gold transfer UI)
        self.players_button = None  # Rect for players button in top panel
        self.players_window_visible = False
        self.players_window = None  # Lazily constructed PlayersWindow

        # Save dialog system (campaign save game)
        self.save_dialog_active = False  # Is save name dialog open?
        self.save_name_input = ""  # Current text in save name field
        self.save_name_cursor_visible = True  # Blinking cursor state
        self.save_name_cursor_timer = 0  # Cursor blink timer
        self.save_feedback_message = None  # "Saved!" or error message
        self.save_feedback_is_error = False  # True -> drawn red (a failure used to be green)
        self.save_feedback_timer = 0  # Timer for feedback display
        self.save_dialog_save_button = None  # Rect for Save button in dialog
        self.save_dialog_cancel_button = None  # Rect for Cancel button in dialog

        # Pause state (single-player only: game pauses when menu/options are open)
        self.game_paused = False
        self._pause_start_time = None  # time.time() when pause began

        # Options menu system
        self.options_menu_visible = False  # Is options menu open?
        self.options_menu_scroll_offset = 0  # Scroll position (0 = top)
        self.options_menu_max_scroll = 0  # Max scroll value (calculated in draw)
        self.options_apply_button = None  # Rect for Apply button
        self.options_back_button = None  # Rect for Back button
        self.options_reset_button = None  # Rect for Reset to Defaults button
        self.resolution_dropdown_button = None  # Rect for resolution dropdown
        self.fullscreen_checkbox = None  # Rect for fullscreen checkbox
        self.resolution_dropdown_open = False  # Is dropdown expanded?
        self.resolution_option_buttons = []  # List of (rect, resolution) for dropdown options
        
        # Slider dragging system (for options menu sliders)
        self.dragging_slider = None  # Which slider is being dragged ('pan_speed' or 'zoom_speed')
        self.drag_offset = 0  # Offset from thumb center when drag started

        # Display settings (current) - set to match what we just created
        self.is_fullscreen = settings.is_fullscreen()
        self.current_resolution = self.screen.get_size()  # Use actual created window size
        
        # Available resolutions - add native if not in list
        # Available resolutions (consistent with main menu)
        self.available_resolutions = [
            (1280, 720),
            (1600, 900),
            (1920, 1080)
        ]
        
        # Temporary settings (for Options menu - applied on Apply button)
        self.temp_resolution = self.current_resolution
        self.temp_fullscreen = self.is_fullscreen
        self.temp_vsync = self.vsync
        self.temp_fps_limit = self.fps_limit
        
        # Army Composition UI (Phase 3)
        self.show_army_composition = False  # Is composition UI visible?
        self.army_composition_territory = None  # Which territory's composition is shown
        self.army_composition_player = None  # Which player's garrison is shown (for multi-garrison)
        self.selected_army_units = []  # List of selected unit IDs within composition
        self.army_composition_buttons = []  # List of (rect, unit_id) for click detection
        self.hovered_composition_button = None  # Which button is being hovered (for tooltip)

        # Unit right-click context menu (mouse-only alternative to CTRL+click multi-select)
        # Purpose: right-clicking a unit icon in the composition strip opens a small drop-down
        # with Select / Add to Group / Remove from Group / Cancel, so partial selections can be
        # built without the keyboard.
        # Format: {'unit_id': int, 'territory': str, 'player': int, 'anchor': pygame.Rect,
        #          'items': [(action_id, label), ...]} or None when closed.
        # 'items' is frozen at open time so labels can't flip while the menu is on screen.
        self.unit_context_menu = None
        self.unit_context_menu_rects = []  # List of (rect, action_id), rebuilt every draw

        # Track current player to detect turn changes
        self.previous_player = 0  # Will be set properly when game_state is initialized

        # Font Manager (Phase 1: Custom font implementation)
        # Initialize centralized font system for Cinzel fonts
        # UI Scaling System: Scale all UI elements based on resolution
        # Reference resolution: 1600x900 (scale_factor = 1.0)
        # This keeps 1600x900 exactly as designed, scales others proportionally
        REFERENCE_WIDTH = 1600
        REFERENCE_HEIGHT = 900
        self.ui_scale = min(WINDOW_WIDTH / REFERENCE_WIDTH, WINDOW_HEIGHT / REFERENCE_HEIGHT)

        # This replaces the default pygame fonts with custom TTF fonts
        self.font_manager = FontManager()
        base_path = os.getcwd()  # Project root directory
        self.font_manager.load_fonts(base_path)

        # Fonts - Scaled based on resolution (1600x900 = reference)
        # At 1600x900: scale = 1.0, sizes are 15/24/12 (current perfect values)
        # At 1280x720: scale = 0.8, sizes become 12/19/10
        # At 1920x1080: scale = 1.2, sizes become 18/29/14
        self.font = self.font_manager.get_font(int(15 * self.ui_scale))  # Normal text
        self.large_font = self.font_manager.get_font(int(24 * self.ui_scale))  # Large text for titles
        self.small_font = self.font_manager.get_font(int(12 * self.ui_scale))  # Small text

        # Bold/SemiBold fonts
        self.small_font_bold = self.font_manager.get_bold_font(int(12 * self.ui_scale))
        self.font_bold = self.font_manager.get_bold_font(int(15 * self.ui_scale))
        self.large_font_bold = self.font_manager.get_bold_font(int(24 * self.ui_scale))

        # Italic font — Cinzel has no italic TTF, so the slant is synthetic. Its own Font
        # object (get_italic_font): set_italic() on the shared get_font() object used to
        # make ALL regular text of that size italic (P8 audit, CHANGELOG 2026-10-08)
        self.small_font_italic = self.font_manager.get_italic_font(int(12 * self.ui_scale))

        # Larger italic font for territory lore text in the bottom UI preview region
        self.lore_font_italic = self.font_manager.get_italic_font(int(16 * self.ui_scale))

        # Extra small font for 720p overflow prevention (Hero Info, tooltips)
        # At 720p, use even smaller font (8px) to prevent text overflow
        extra_small_size = 8 if WINDOW_HEIGHT == 720 else int(10 * self.ui_scale)
        self.extra_small_font = self.font_manager.get_font(extra_small_size)

        # FPS OPTIMIZATION 6.4: Pre-load additional font sizes
        # Pre-populate font cache with commonly used sizes to eliminate runtime font creation
        # This adds ~0.1s to startup but ensures smooth text rendering from frame 1
        for size in range(8, 36, 2):  # 8, 10, 12, ... 34
            try:
                self.font_manager.get_font(size)
                self.font_manager.get_bold_font(size)
            except Exception:
                pass  # Ignore errors for sizes that fail to load

        # Floating chat notification effect — shows new messages briefly on map area
        self.chat_notification_effect = ChatNotificationEffect(
            TOP_PANEL_HEIGHT, self.game_state, self.local_player_index,
            self.small_font, self.small_font_bold
        )

        # Initialize drawing helpers (Phase 3: added small_font_bold for tooltip names)
        self.helpers = DrawingHelpers(
            self.screen,
            self.font,
            self.small_font,
            self.large_font,
            self.separator_image,
            self.separator_width,
            small_font_bold=self.small_font_bold
        )
        # Right-sidebar widget kit: cached frames, buttons, bookmarks and capped-scale
        # text (rendering/sidebar_widgets.py). Cleared on resolution change.
        self.sidebar_widgets = SidebarWidgets(self)
        
        # Camera system (Phase 2D: Camera/Zoom implementation)
        self.camera_offset = [0.0, 0.0]  # [x, y] in world coordinates
        self.camera_zoom = 1.65           # Start at max zoom out (165% - user's preferred view)
        self.camera_drag_start = None     # For middle-mouse drag tracking
        
        # Camera configuration (updated per user request)
        self.camera_min_zoom = 1.65       # 165% - can't zoom out as far as before (user request)
        self.camera_max_zoom = 4.0        # 400% - can zoom in close for inspection (restored)
        self.edge_scroll_speed = 5        # Pixels per frame for edge scrolling (will be dynamic)
        self.edge_scroll_margin = 20      # Pixels from edge to trigger scrolling
        self.keyboard_scroll_speed = CAMERA_PAN_SPEED   # Pixels per frame for keyboard scrolling
        
        # Initialize camera handler
        self.camera = CameraHandler(
            self.map_width,
            self.map_height,
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
            MAP_HEIGHT,
            initial_zoom=self.camera_zoom,
            min_zoom=self.camera_min_zoom,
            max_zoom=self.camera_max_zoom
        )
        # Sync camera state
        self.camera.offset = self.camera_offset
        self.camera.zoom = self.camera_zoom
        
        # Initialize keyboard handler
        self.keyboard = KeyboardHandler()
        
        # Initialize mouse handler (needs self reference and layout values)
        self.mouse = MouseHandler(self, TOP_PANEL_HEIGHT, BOTTOM_UI_Y, WINDOW_WIDTH)

        # Tick when the sidebar's collapse/expand slide started (None = not sliding).
        # All sidebar geometry is derived from it by get_sidebar_layout()
        # (ui/sidebar_layout.py) — nothing caches sidebar coordinates any more.
        self._sidebar_anim_start_ms = None
        # Pixel scroll position per scrollable sidebar tab (see handle_sidebar_wheel)
        self._reset_sidebar_scroll()
        self.order_card_rects = []  # (clipped rect, entry) of visible Action Queue cards
        # (from, to) of the Action Queue card under the mouse; the map renderer draws that
        # route's arrow with a gold highlight (UIConstants.SIDEBAR_ROUTE_HIGHLIGHT)
        self.sidebar_hovered_route = None
        # Camera pan started from the sidebar (order card / hero portrait click):
        # a CameraPanAnimation plus the camera offset it last set - anything else that
        # moves the camera (drag, keys, edge scroll, wheel zoom) cancels the pan
        self._sidebar_pan = None
        self._sidebar_pan_offset = None
        self.sidebar_hero_ability_buttons = {}  # {(hero, i): rect} ability icons on sidebar hero cards
        self.hero_portrait_rects = {}           # {hero: rect} portraits on sidebar hero cards
        self.sidebar_tooltip = None  # (text, mouse_pos) hover label, drawn at frame end

        # Track previous player and phase for AI turn optimization
        self.previous_ai_check = -1
        self.previous_phase = None
        self.previous_turn_announcement = False

        # Initialize rendering coordinators (Phase 4: Rendering organization)
        self.map_renderer = MapRenderer(self)

        # Connect map_renderer to game_state for visual effects
        self.game_state.map_renderer = self.map_renderer

        # Set up multiplayer turn start callback
        if self.multiplayer_mode:
            self.game_state.on_turn_start_callback = self._on_turn_start_multiplayer

        # UIRenderer needs layout values (dynamic, not static constants)
        layout_values = {
            'window_width': WINDOW_WIDTH,
            'window_height': WINDOW_HEIGHT,
            'top_panel_height': TOP_PANEL_HEIGHT,
            'bottom_ui_y': BOTTOM_UI_Y,
            'bottom_ui_height': BOTTOM_UI_HEIGHT,
            'map_height': MAP_HEIGHT
        }
        self.ui_renderer = UIRenderer(self, layout_values)
        self.panel_renderer = PanelRenderer(self)
        
        # Map scaling cache (optimization: avoid rescaling every frame)
        self.cached_scaled_map = None     # Legacy full-map cache (kept for compatibility)
        self.cached_zoom_level = None     # Zoom level of cached map
        # Viewport map cache — see _blit_map_background(). Holds a viewport-sized
        # slice plus a margin, in scaled-map space, as
        # (source id, zoom, region_x0, region_y0, region_x1, region_y1).
        # Panning within the margin re-blits at a new screen offset (no rescale);
        # a rebuild happens only when the view leaves the margin or zoom changes.
        self._map_view_key = None
        self._map_view_surface = None
        self._map_view_offset = (0, 0)
        # East map extension: fills the strip past the map's right edge when zoomed far
        # out (it used to be hidden by the right sidebar). Built lazily on first draw.
        self.map_east_extension = MapEastExtension()

        # Camera debug state
        self.debug_edge_scroll = None
        self.debug_keyboard_scroll = None

        # NOTE: Settings are now loaded directly from SettingsManager during __init__
        # The old self.load_settings() method is no longer needed and has been removed
        # to prevent conflicts with the global settings system

        # Start-game camera animation (zoom to player's starting territory)
        # Skip for Campaign mode (tutorial_mission handles its own animation)
        if not self.campaign_map:
            target_territory = None
            if self.multiplayer_mode:
                # Multiplayer: zoom to local player's territory
                target_territory = self.game_state.player_starting_territories.get(self.local_player_index)
            else:
                # Custom Game: zoom to first human player's territory
                for i, is_ai in enumerate(self.game_state.player_is_ai):
                    if not is_ai:
                        target_territory = self.game_state.player_starting_territories.get(i)
                        break

            if target_territory and target_territory in self.scaled_centers:
                target_center = self.scaled_centers[target_territory]
                self.start_camera_animation = CameraAnimation(
                    camera_handler=self.camera,
                    start_zoom=self.camera.min_zoom,
                    target_zoom=self.camera.max_zoom,
                    duration=1.5,
                    target_center_world=target_center,
                    screen_width=self.screen.get_width(),
                    map_area_height=MAP_HEIGHT,
                )
                # Sync camera state immediately so first frame renders at start position
                self.camera_offset = self.camera.offset.copy()
                self.camera_zoom = self.camera.zoom
                logger.info(f"[START] Camera zoom animation: {target_territory}")

    def _on_turn_start_multiplayer(self):
        """Called when turn starts (after turn announcement) - send unit/building completions"""
        if not self.multiplayer_mode:
            return

        # Only send notifications if it's the LOCAL player's turn
        # (so remote player sees our units/buildings spawn)
        if self.game_state.current_player != self.local_player_index:
            return  # It's remote player's turn, they'll see their own units locally



        # Send unit completion notifications (units just spawned at turn start)
        if hasattr(self.game_state, 'last_completed_units') and self.game_state.last_completed_units:
            for unit_info in self.game_state.last_completed_units:
                self._send_action_to_remote(MessageType.UNIT_COMPLETE, unit_info)

        # Send building completion notifications (buildings just completed at turn start)
        if hasattr(self.game_state, 'last_completed_buildings') and self.game_state.last_completed_buildings:
            for building_info in self.game_state.last_completed_buildings:
                territory, building_type, plot_index = building_info
                self._send_action_to_remote(MessageType.BUILDING_COMPLETE, {
                    'territory': territory,
                    'building_type': building_type,
                    'plot_index': plot_index
                })

        # Sync fix: Send castle upgrade completion notifications
        if hasattr(self.game_state, 'last_completed_castle_upgrades') and self.game_state.last_completed_castle_upgrades:
            for territory, plot_index in self.game_state.last_completed_castle_upgrades:
                self._send_action_to_remote(MessageType.BUILDING_COMPLETE, {
                    'territory': territory,
                    'building_type': 'CastleUpgrade',
                    'plot_index': plot_index
                })

        # Sync fix: Send hero training completion notifications
        if hasattr(self.game_state, 'last_completed_heroes') and self.game_state.last_completed_heroes:
            for hero_info in self.game_state.last_completed_heroes:
                self._send_action_to_remote(MessageType.BUILDING_COMPLETE, {
                    'territory': hero_info['territory'],
                    'building_type': 'HeroComplete',
                    'plot_index': hero_info['keep_plot'],
                    'hero_type': hero_info['hero_type'],
                    'player_index': hero_info['player_index']
                })

    def _process_network_messages(self):
        """Process incoming network messages from remote player"""
        if not self.network_connection:
            return

        # Check for disconnection
        if hasattr(self.network_connection, 'disconnected') and self.network_connection.disconnected:
            if not self.disconnect_dialog_shown:
                self.disconnect_dialog_shown = True
                reason = getattr(self.network_connection, 'disconnect_reason', 'Unknown reason')
                logger.info(f"[NETWORK] Connection lost: {reason}")
                # Set flag to show disconnect dialog
                self.show_disconnect_dialog = True
                self.disconnect_dialog_reason = reason

        # Process all queued messages
        while True:
            msg = self.network_connection.message_queue.get_incoming_message()
            if not msg:
                break

            self._handle_network_message(msg)

        # Sync fix: apply queued FULL_STATE_SYNC if battles/animations have cleared
        # (previously these were silently dropped, causing missed sync corrections)
        if self._pending_full_state_sync is not None:
            battles_clear = (self.game_state.turn_phase != 'battles' or
                             len(self.game_state.pending_battles) == 0)
            animations_clear = not self.game_state.active_animations
            if battles_clear and animations_clear:
                logger.info("[NETWORK] Applying deferred FULL_STATE_SYNC")
                pending_data = self._pending_full_state_sync
                self._pending_full_state_sync = None
                # Re-dispatch as FULL_STATE_SYNC message
                self._handle_network_message({
                    'type': MessageType.FULL_STATE_SYNC,
                    'data': pending_data
                })

    def _handle_network_message(self, message: dict):
        """
        Handle a single network message from remote player.

        Args:
            message: Decoded message dict with 'type' and 'data' keys
        """
        msg_type = message.get('type')
        data = message.get('data', {})

        logger.debug(f"[NETWORK] Received {msg_type}: {data}")

        # VALIDATION: Ensure local_player_index is initialized
        if self.local_player_index is None:
            logger.error("[NETWORK] ERROR: local_player_index not initialized, cannot process message")
            return

        # Sync logger: record incoming action from remote player
        sync_logger = getattr(self.game_state, 'sync_logger', None)
        if sync_logger:
            remote_player = data.get('player_index', message.get('from_player_index', -1))
            sync_logger.record_action(
                msg_type, remote_player,
                self.game_state.turn_number, data, source='remote'
            )

        if msg_type == MessageType.MOVEMENT_ORDER:
            # Remote player issued a movement order
            self._handle_remote_movement_order(data)

        elif msg_type == MessageType.BUILDING_ORDER:
            # Remote player placed a building
            self._handle_remote_building_order(data)

        elif msg_type == MessageType.TRAINING_ORDER:
            # Remote player started training units
            self._handle_remote_training_order(data)

        elif msg_type == MessageType.ORDER_REMOVE:
            # Remote player cancelled an order (movement, training, castle upgrade, or hero training)
            self._handle_remote_order_remove(data)

        elif msg_type == MessageType.GOLD_TRANSFER:
            # Remote player sent gold to an ally — mirror the balance change locally.
            self._handle_remote_gold_transfer(data)

        elif msg_type == MessageType.RESEARCH_ORDER:
            # Sync fix: Remote player started research (sequential mode)
            tech_id = data.get('tech_id')
            remote_player_index = data.get('player_index')
            if remote_player_index is None:
                remote_player_index = 1 if self.local_player_index == 0 else 0
            if 0 <= remote_player_index < self.game_state.num_players and tech_id:
                original_player = self.game_state.current_player
                try:
                    self.game_state.current_player = remote_player_index
                    self.game_state.start_research(tech_id)
                    logger.info(f"[NETWORK] Player {remote_player_index} started research: {tech_id}")
                finally:
                    self.game_state.current_player = original_player

        elif msg_type == MessageType.HERO_TRAINING_ORDER:
            # Sync fix: Remote player started hero training (sequential mode)
            territory = data.get('territory')
            keep_plot = data.get('keep_plot')
            hero_type = data.get('hero_type')
            remote_player_index = data.get('player_index')
            if remote_player_index is None:
                remote_player_index = 1 if self.local_player_index == 0 else 0
            if 0 <= remote_player_index < self.game_state.num_players and territory and hero_type is not None:
                territory_owner = self.game_state.territory_owners.get(territory)
                if territory_owner == remote_player_index:
                    original_player = self.game_state.current_player
                    try:
                        self.game_state.current_player = remote_player_index
                        self.game_state.start_hero_training(territory, keep_plot, hero_type)
                        logger.info(f"[NETWORK] Player {remote_player_index} started hero training: {hero_type} in {territory}")
                    finally:
                        self.game_state.current_player = original_player
                else:
                    logger.warning(f"[NETWORK] REJECTED: Hero training in {territory} - not owned by Player {remote_player_index}")

        elif msg_type == MessageType.EXECUTE_ORDERS:
            # Remote player clicked Execute Orders
            logger.info("[NETWORK] Remote player executing orders")
            # Apply all movement orders from remote player
            orders_data = data.get('orders', [])
            for order_data in orders_data:
                from_territory = order_data.get('from_territory')
                to_territory = order_data.get('to_territory')
                unit_ids = order_data.get('unit_ids', [])

                if unit_ids:
                    self.game_state.add_movement_order_for_units(from_territory, to_territory, unit_ids)
                else:
                    self.game_state.add_movement_order(from_territory, to_territory)

            # Now execute all the orders to create animations
            self.game_state.execute_all_orders()

        elif msg_type == MessageType.BATTLE_RESOLVE:
            # Remote player resolved a battle
            logger.info("[NETWORK] Remote player resolved battle")
            territory = data.get('territory')
            winner = data.get('winner')
            surviving_armies = data.get('surviving_armies', 0)  # Bug 3 fix: default 0 prevents None < 0 TypeError
            new_owner = data.get('new_owner')
            alliance_marker = data.get('alliance_marker')  # For simultaneous mode
            surviving_units = data.get('surviving_units')  # Unit composition from host
            battle_reports = data.get('battle_reports') or []  # Defender summaries

            # VALIDATION: Verify battle exists in pending_battles
            battle_exists = False
            for battle in self.game_state.pending_battles:
                if battle.territory == territory:
                    battle_exists = True
                    break

            if not battle_exists:
                logger.warning(f"[NETWORK] REJECTED: Battle result for {territory} - no pending battle found")
                return

            # VALIDATION: Basic sanity checks on battle result
            if new_owner is None or surviving_armies < 0:
                logger.warning(f"[NETWORK] REJECTED: Invalid battle result - new_owner={new_owner}, surviving_armies={surviving_armies}")
                return

            # Apply the battle result to our game state
            if territory:
                self.game_state.territory_owners[territory] = new_owner
                self.game_state._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                self.game_state.invalidate_territorial_bonus_cache()  # Ownership changed

                # IMPORTANT: Clear ALL garrisons in this territory first (losers' armies are destroyed)
                # Then set only the winner's garrison
                if territory in self.game_state.territory_garrisons:
                    self.game_state.territory_garrisons[territory].clear()

                # Set winner's garrison (just fought, can't move)
                # If host sent surviving_units, use them to preserve unit composition
                # Otherwise fallback to auto-created Swordsmen (legacy/single-player)
                # set_garrison_armies() auto-syncs to legacy arrays via sync_legacy_garrison_data()
                self.game_state.set_garrison_armies(territory, new_owner, unmoved=0, moved=surviving_armies, units=surviving_units)

                # Remove this battle from pending_battles list
                for i, battle in enumerate(self.game_state.pending_battles):
                    if battle.territory == territory:
                        self.game_state.pending_battles.pop(i)
                        logger.info(f"[NETWORK] Removed battle for {territory}, {len(self.game_state.pending_battles)} battles remaining")
                        break

                # SIMULTANEOUS MODE: Handle alliance marker if sent
                if alliance_marker and self.sim_state is not None:
                    if hasattr(self.sim_state, 'phase_manager') and self.sim_state.phase_manager:
                        self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)
                        logger.info(f"[NETWORK] Added alliance marker for {territory}, chooser: {alliance_marker.get('chooser')}")

                # Capital Assault: run full elimination on client for battle-captured capitals
                if (self.sim_state is not None and
                    self.game_state.victory_condition == "Capital Assault" and
                    hasattr(self.game_state, 'player_starting_territories')):
                    for player_index, capital in self.game_state.player_starting_territories.items():
                        if (capital == territory and player_index != new_owner and
                            player_index not in self.sim_state.eliminated_players and
                            not self.game_state.are_allies(new_owner, player_index)):
                            self.game_state.eliminate_player(player_index)
                            self.sim_state.eliminate_player(player_index)
                            logger.info(f"[NETWORK] Capital Assault: eliminated Player {player_index + 1} on client")

                # Battle Reports: the resolver captured these, so queue any addressed to
                # us. This client applied the result above rather than running
                # resolve_battle(), so this message is its ONLY source for them.
                for report in battle_reports:
                    if isinstance(report, dict):
                        self.queue_battle_report(report)
                        # Heroes that died in this battle: this client never ran the
                        # battle, so the report is its only source for them. Queue them
                        # for the "Our Hero, X, has been slain in Y!" toast (the drain
                        # shows only the local player's own heroes).
                        for hero in report.get('heroes_slain') or []:
                            self.game_state.hero_death_events.append(
                                (report.get('defender'), hero, report.get('territory')))

                # Universal last-team-standing: check victory on client after territory change
                # (host already checks via _update_battle_results; client needs this for sync)
                self.game_state.check_victory()

                # Check if all battles resolved
                if len(self.game_state.pending_battles) == 0:
                    if self.sim_state is not None:
                        # SIMULTANEOUS MODE: Check alliance markers
                        pm = self.sim_state.phase_manager
                        markers_pending = len(pm.pending_alliance_markers) if pm else 0
                        logger.info(f"[NETWORK] All battles resolved (sim mode). Alliance markers: {markers_pending}")

                        # HOST: Complete round if no more battles/markers
                        if self.local_player_index == 0 and markers_pending == 0:
                            logger.info(f"[HOST] All conflicts resolved after remote battle, completing round")
                            self.sim_state.complete_round()
                    else:
                        # SEQUENTIAL MODE: Set ready to advance turn
                        logger.info("[NETWORK] All battles resolved, ready to advance turn")
                        self.game_state.ready_to_advance_turn = True

        elif msg_type == MessageType.TURN_END:
            # Remote player ended their turn (after battles resolved)
            logger.info("[NETWORK] Remote player ended turn")

            # If we're in battle phase and all battles resolved, advance to next player
            if self.game_state.turn_phase == 'battles' and len(self.game_state.pending_battles) == 0:
                logger.info("[NETWORK] Advancing to next player after battle phase")
                self.game_state._advance_to_next_player()
            else:
                # Regular turn end during planning phase
                self.game_state.next_player()

            # 3+ player fix: host sends authoritative state sync to all clients
            # after a client's turn ends, so other clients stay in sync
            if self.local_player_index == 0:
                self._send_full_state_sync()

            # Check if any units completed training (will be in last_completed_units)
            if hasattr(self.game_state, 'last_completed_units') and self.game_state.last_completed_units:
                # Remote player's units are now visible - no need to send back
                pass

        elif msg_type == MessageType.UNIT_COMPLETE:
            # Remote player completed training a unit
            logger.info("[NETWORK] Remote player completed unit training")
            territory = data.get('territory')
            unit_type = data.get('unit_type')
            has_haste = data.get('has_haste', False)
            unit_id = data.get('unit_id', 0)

            # VALIDATION: Verify territory ownership before adding unit
            # M5 fix: use player_index from message data instead of hardcoded 2-player logic
            if territory:
                remote_player_index = data.get('player_index', 1 if self.local_player_index == 0 else 0)
                territory_owner = self.game_state.territory_owners.get(territory)

                if territory_owner != remote_player_index:
                    logger.warning(f"[NETWORK] REJECTED: Unit completion in {territory} - territory not owned by remote player (owner={territory_owner}, remote={remote_player_index})")
                    return

            # Add the unit to the map (same logic as finish_training)
            if territory:
                # Determine territory owner
                owner = self.game_state.territory_owners.get(territory, -1)
                if owner == -1:
                    # Neutral territory - shouldn't happen for training
                    logger.warning(f"[NETWORK WARNING] Unit completed in neutral territory {territory}")
                    return

                # Create unit object
                new_unit = {
                    'id': unit_id,
                    'status': 'ready' if has_haste else 'moved',
                    'order': None,
                    'type': unit_type
                }

                # Add to garrison system (source of truth)
                if has_haste:
                    self.game_state.add_garrison(territory, owner, unmoved=1, moved=0, units=[new_unit])
                else:
                    self.game_state.add_garrison(territory, owner, unmoved=0, moved=1, units=[new_unit])

                # Sync legacy data for backward compatibility
                self.game_state.sync_legacy_garrison_data(territory)

        elif msg_type == MessageType.BUILDING_COMPLETE:
            # Remote player completed a building
            logger.info("[NETWORK] Remote player completed building")
            territory = data.get('territory')
            building_type = data.get('building_type')
            plot_index = data.get('plot_index')

            # VALIDATION: Verify territory ownership before adding building
            # M6 fix: use player_index from message data instead of hardcoded 2-player logic
            if territory:
                remote_player_index = data.get('player_index', 1 if self.local_player_index == 0 else 0)
                territory_owner = self.game_state.territory_owners.get(territory)

                if territory_owner != remote_player_index:
                    logger.warning(f"[NETWORK] REJECTED: Building completion in {territory} - territory not owned by remote player (owner={territory_owner}, remote={remote_player_index})")
                    return

            # Add the building to the map (same logic as finish_constructions)
            if territory and building_type is not None and plot_index is not None:
                if building_type == 'CastleUpgrade':
                    # Sync fix: castle upgrade completion from remote player
                    if territory not in self.game_state.castle_upgrades:
                        self.game_state.castle_upgrades[territory] = {}
                    self.game_state.castle_upgrades[territory][plot_index] = True
                    # Remove from in-progress if present
                    if territory in self.game_state.castle_upgrades_in_progress:
                        if plot_index in self.game_state.castle_upgrades_in_progress[territory]:
                            del self.game_state.castle_upgrades_in_progress[territory][plot_index]
                            if not self.game_state.castle_upgrades_in_progress[territory]:
                                del self.game_state.castle_upgrades_in_progress[territory]
                    # Trigger visual effect
                    if self.map_renderer:
                        self.map_renderer.trigger_castle_upgrade_effect(territory, plot_index)
                    logger.info(f"[NETWORK] Castle upgrade complete in {territory} plot {plot_index}")
                elif building_type == 'HeroComplete':
                    # Sync fix: hero training completion from remote player
                    hero_type = data.get('hero_type')
                    player_index = data.get('player_index', remote_player_index)
                    if hero_type:
                        if player_index not in self.game_state.heroes:
                            self.game_state.heroes[player_index] = {}
                        self.game_state.heroes[player_index][hero_type] = {
                            'keep_territory': territory,
                            'keep_plot': plot_index,
                            'status': 'active'
                        }
                        # Remove from training queue if present
                        if territory in self.game_state.hero_training_queue:
                            if plot_index in self.game_state.hero_training_queue[territory]:
                                del self.game_state.hero_training_queue[territory][plot_index]
                                if not self.game_state.hero_training_queue[territory]:
                                    del self.game_state.hero_training_queue[territory]
                        logger.info(f"[NETWORK] Hero {hero_type} training complete for Player {player_index} in {territory}")
                else:
                    # Normal building completion
                    if territory not in self.game_state.buildings:
                        self.game_state.buildings[territory] = {}
                    self.game_state.buildings[territory][plot_index] = building_type

        elif msg_type == MessageType.CHAT_MESSAGE:
            # Remote player sent a chat message
            player_index = data.get('player_index', 0)
            message = data.get('message', '')

            # VALIDATION: Check if player_index is valid
            if player_index is None or player_index < 0 or player_index >= self.game_state.num_players:
                logger.warning(f"[NETWORK] REJECTED: Invalid chat player_index: {player_index}")
                return

            if message:
                logger.debug(f"[NETWORK] Received chat from Player {player_index + 1}: {message}")
                self.game_state.add_chat_message(player_index, message)

        elif msg_type == MessageType.STATE_CHECKSUM:
            # Client sent state checksum for validation (host only)
            if self.local_player_index == 0:  # Host validates
                client_checksum = data.get('checksum')
                turn_number = data.get('turn_number')

                # Calculate our own checksum
                host_checksum = self.game_state.calculate_state_checksum()

                # Sync logger: record checksum comparison on host
                if sync_logger:
                    sync_logger.record_checksum(
                        turn_number, host_checksum,
                        remote_checksum=client_checksum,
                        match=(client_checksum == host_checksum)
                    )

                if client_checksum != host_checksum:
                    # DESYNC DETECTED!
                    logger.warning(f"[NETWORK] DESYNC DETECTED at turn {turn_number}!")
                    logger.info(f"[NETWORK] Host checksum: {host_checksum}")
                    logger.info(f"[NETWORK] Client checksum: {client_checksum}")

                    # Show warning message
                    self.game_state.add_message("WARNING: Game state desync detected! Resyncing...")

                    # Sync logger: request state detail from client(s) for diff diagnosis
                    if sync_logger:
                        # Store host's state detail for comparison when response arrives
                        self._desync_host_detail = sync_logger.build_state_detail()
                        self._desync_turn_number = turn_number
                        self._send_action_to_remote(MessageType.STATE_DETAIL_REQUEST,
                                                    {'turn_number': turn_number})
                        logger.info(f"[HOST] Sent STATE_DETAIL_REQUEST for desync at turn {turn_number}")

                    # Sync fix: send corrective FULL_STATE_SYNC on checksum mismatch
                    self._send_full_state_sync()
                    logger.info(f"[HOST] Sent corrective FULL_STATE_SYNC after desync at turn {turn_number}")
                else:
                    logger.info(f"[NETWORK] State checksum validated for turn {turn_number}")

        elif msg_type == MessageType.STATE_DETAIL_REQUEST:
            # Host is requesting full state detail for desync diagnosis (client only)
            if self.local_player_index != 0 and sync_logger:
                turn_number = data.get('turn_number', 0)
                client_detail = sync_logger.build_state_detail()
                self._send_action_to_remote(MessageType.STATE_DETAIL_RESPONSE, {
                    'turn_number': turn_number,
                    'state_detail': client_detail,
                })
                logger.info(f"[CLIENT] Sent STATE_DETAIL_RESPONSE for turn {turn_number}")

        elif msg_type == MessageType.STATE_DETAIL_RESPONSE:
            # Client sent full state detail for desync diff (host only)
            if self.local_player_index == 0 and sync_logger:
                turn_number = data.get('turn_number', 0)
                client_detail = data.get('state_detail', {})
                host_detail = getattr(self, '_desync_host_detail', {})

                # Compute field-level diff
                from sync_logger import SyncLogger
                diff = SyncLogger.compute_state_diff(host_detail, client_detail)

                if diff:
                    # Record desync on host
                    sync_logger.record_desync(turn_number, diff)
                    logger.warning(f"[HOST] Desync diff at turn {turn_number}: "
                                   f"{len(diff)} divergent fields")

                    # Send diff to client so both participants have it
                    self._send_action_to_remote(MessageType.DESYNC_DIFF, {
                        'turn_number': turn_number,
                        'diff': diff,
                    })
                else:
                    logger.info(f"[HOST] No diff found at turn {turn_number} "
                                "(states matched at detail level)")

        elif msg_type == MessageType.DESYNC_DIFF:
            # Host sent desync diff (client only) — log it locally
            if self.local_player_index != 0 and sync_logger:
                turn_number = data.get('turn_number', 0)
                diff = data.get('diff', {})
                sync_logger.record_desync(turn_number, diff)
                logger.warning(f"[CLIENT] Received desync diff at turn {turn_number}: "
                               f"{len(diff)} divergent fields")

        elif msg_type == MessageType.DISCONNECT:
            # Remote player disconnected (legacy 1v1 message)
            logger.info("[NETWORK] Remote player disconnected")

        elif msg_type == MessageType.PLAYER_DISCONNECT:
            # A specific player disconnected - AI takes over their slot
            player_index = data.get('player_index')
            ai_takeover = data.get('ai_takeover', True)
            logger.info(f"[NETWORK] Player {player_index + 1} disconnected - AI takeover: {ai_takeover}")

            if ai_takeover and player_index is not None:
                # Mark player as AI-controlled using existing player_is_ai list
                if 0 <= player_index < len(self.game_state.player_is_ai):
                    self.game_state.player_is_ai[player_index] = True
                    logger.info(f"[NETWORK] Player {player_index + 1} is now AI-controlled")

                    # Track which players disconnected (for potential reconnection)
                    if not hasattr(self.game_state, 'disconnected_players'):
                        self.game_state.disconnected_players = set()
                    self.game_state.disconnected_players.add(player_index)

                    # Chat notification: inform all players about the disconnect
                    player_name = self.game_state.player_names[player_index] if self.game_state.player_names[player_index] else f"Player {player_index + 1}"
                    self.game_state.add_chat_message(0, f"{player_name} has disconnected. AI taking over.")

        elif msg_type == MessageType.DISCONNECT_ELIMINATION:
            # Player eliminated after reconnect timeout (60s) — both host and clients process this
            player_index = data.get('player_index')
            if player_index is not None and 0 <= player_index < self.game_state.num_players:
                logger.info(f"[NETWORK] Player {player_index + 1} eliminated (disconnect timeout)")

                # Chat notification
                player_name = self.game_state.player_names[player_index] if self.game_state.player_names[player_index] else f"Player {player_index + 1}"
                self.game_state.add_chat_message(0, f"{player_name} has been disconnected and eliminated.")

                # Execute disconnect elimination (ally territory distribution + cleanup)
                self.game_state.eliminate_player_disconnect(player_index)

                # Sync simultaneous mode if active
                if self.sim_state is not None:
                    self.sim_state.eliminate_player(player_index)

                # Sequential mode: if eliminated player's turn is active, advance to next
                if (self.sim_state is None and
                    self.game_state.current_player == player_index and
                    self.game_state.phase == 'playing'):
                    logger.info(f"[NETWORK] Eliminated player's turn was active — advancing to next player")
                    self.game_state.next_player()

                # Check victory after elimination (universal last-team-standing)
                self.game_state.check_victory()

        # ========== SIMULTANEOUS MODE MESSAGES ==========

        elif msg_type == MessageType.SIM_PLAYER_READY:
            # Remote player marked themselves as ready during planning phase
            player_id = data.get('player_id')
            orders = data.get('orders', [])

            # VALIDATION: Player ID must be valid
            if player_id is None or player_id < 0 or player_id >= self.game_state.num_players:
                logger.warning(f"[NETWORK] REJECTED: Invalid player_id {player_id} in SIM_PLAYER_READY (num_players={self.game_state.num_players})")
                return

            logger.info(f"[NETWORK] Player {player_id} marked ready with {len(orders)} orders (simultaneous mode)")

            if self.sim_state is not None:
                # HOST: Store remote player's orders in sim_state
                # This is critical - orders are sent WITH the ready signal
                if self.local_player_index == 0:  # Host only
                    if self.sim_state.sim_phase == 'planning':
                        # Clear any existing orders for this player (shouldn't be any, but be safe)
                        self.sim_state.player_orders[player_id] = []
                        # Add received orders to sim_state
                        for order in orders:
                            order['player_id'] = player_id  # Ensure player_id is set
                            self.sim_state.add_order(player_id, order)
                            logger.info(f"[SIM] Received order from Player {player_id}: {order.get('from_territory')} -> {order.get('to_territory')}")
                    else:
                        logger.warning(f"[SIM] Late SIM_PLAYER_READY from player {player_id} - phase is '{self.sim_state.sim_phase}', orders discarded")

                self.sim_state.players_ready[player_id] = True

                # Host checks if all players are ready to start execution
                # Only trigger if still in planning phase (avoid double execution)
                if self.local_player_index == 0:  # Host only
                    if self.sim_state.sim_phase == 'planning' and self.sim_state.all_players_ready():
                        logger.info("[NETWORK] All players ready - starting execution phase")
                        self._sim_start_execution_phase()

        elif msg_type == MessageType.SIM_ALL_READY:
            # Host signals all players ready with merged orders (client receives this)
            # Orders are already filtered - forced defender movement orders removed
            orders = data.get('orders', [])
            forced_defenders = data.get('forced_defenders', [])
            logger.debug(f"[NETWORK] All players ready - received {len(orders)} merged orders")

            if self.sim_state is not None:
                # Process forced defenders - queue popup if local player was forced to defend
                for fd in forced_defenders:
                    fd_player = fd.get('player_id')
                    fd_territory = fd.get('territory')
                    fd_target = fd.get('intended_target')
                    if fd_player == self.local_player_index:
                        logger.info(f"[NETWORK] Forced to defend in {fd_territory} (was attacking {fd_target})")
                        # Queue popup notification (will show one at a time with auto-close)
                        self._queue_forced_defend_popup(fd_territory, fd_target)

                # Store merged orders and start execution
                self.sim_state.merged_orders = orders
                self.sim_state.sim_phase = 'executing'

                # Reset phase_manager state for this execution
                # This ensures animation completion callback works correctly
                if self.sim_state.phase_manager:
                    self.sim_state.phase_manager.execution_complete = False
                    self.sim_state.phase_manager.animations_complete = False
                    self.sim_state.phase_manager._sim_pending_arrivals = []

                # Execute all orders (movements will animate simultaneously)
                # Orders are already filtered - forced defender orders were removed by host
                self._sim_execute_merged_orders(orders)

        elif msg_type == MessageType.SIM_TIMER_UPDATE:
            # Timer sync from host (client receives this)
            timers = data.get('timers', {})
            logger.debug(f"[NETWORK] Timer update received: {timers}")

            if self.sim_state is not None:
                # Update client's timer display
                for player_id_str, remaining in timers.items():
                    player_id = int(player_id_str)
                    self.sim_state.player_timers[player_id] = remaining

        elif msg_type == MessageType.SIM_BATTLE_RESULT:
            # Battle result from the player who resolved it
            territory = data.get('territory')
            result = data.get('result', {})
            logger.info(f"[NETWORK] Battle result for {territory}: {result}")

            if self.sim_state is not None:
                # Apply battle result to game state
                winner = result.get('winner')
                surviving_armies = result.get('surviving_armies', 0)
                new_owner = result.get('new_owner')

                if territory and new_owner is not None:
                    self.game_state.territory_owners[territory] = new_owner
                    self.game_state._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                    self.game_state.invalidate_territorial_bonus_cache()  # Ownership changed
                    self.game_state.set_garrison_armies(territory, new_owner,
                                                       unmoved=0, moved=surviving_armies, units=None)

                # Remove from pending battles if tracked
                if hasattr(self.sim_state, 'pending_battles'):
                    # Battles can be objects (with .territory attr) or dicts
                    self.sim_state.pending_battles = [
                        b for b in self.sim_state.pending_battles
                        if getattr(b, 'territory', b.get('territory') if isinstance(b, dict) else None) != territory
                    ]

        elif msg_type == MessageType.SIM_HERO_ABILITY:
            # Hero ability used by another player - apply the effect locally
            player_id = data.get('player_id')
            hero_name = data.get('hero_name')
            ability_index = data.get('ability_index')
            ability_name = data.get('ability_name')
            target = data.get('target')  # For targeted abilities
            logger.debug(f"[NETWORK] Received SIM_HERO_ABILITY: Player {player_id} used {hero_name}'s {ability_name}")

            if self.game_state is not None and hero_name:
                # Temporarily set current_player to execute the ability
                original_player = self.game_state.current_player
                self.game_state.current_player = player_id

                try:
                    if target:
                        # Targeted ability - execute with target
                        if ability_name == 'Relentless Charge':
                            self.game_state.execute_relentless_charge(target, player_id)
                        elif ability_name == 'Aggressive Diplomacy':
                            self.game_state.execute_aggressive_diplomacy(target, player_id)
                        elif ability_name == 'Levy':
                            self.game_state.execute_levy(target, player_id)
                        elif ability_name == 'Royal Charisma':
                            # Sync fix: pass pre-selected stolen units from sender
                            # to ensure same random units are stolen on both sides
                            stolen_units = data.get('stolen_units')
                            self.game_state.execute_royal_charisma(target, player_id, pre_selected_unit_ids=stolen_units)
                        elif ability_name == 'Regicide':
                            self.game_state.execute_regicide(target, player_id)
                        elif ability_name == 'Decisive Strike':
                            self.game_state.execute_decisive_strike(target, player_id)
                        elif ability_name == 'Valorous Charge':
                            self.game_state.execute_valorous_charge(target, player_id)

                        # Trigger visual particle effect for the ability (network replay)
                        source_territory = None
                        if ability_name in ('Royal Charisma', 'Valorous Charge'):
                            hero_data = self.game_state.heroes.get(player_id, {}).get(hero_name)
                            if hero_data:
                                keep_terr = hero_data.get('keep_territory')
                                if ability_name == 'Royal Charisma':
                                    self.map_renderer.trigger_ability_effect(
                                        ability_name, keep_terr, player_id,
                                        source_territory=target)
                                else:
                                    self.map_renderer.trigger_ability_effect(
                                        ability_name, target, player_id,
                                        source_territory=keep_terr)
                        else:
                            self.map_renderer.trigger_ability_effect(
                                ability_name, target, player_id)

                        # Set cooldown for targeted abilities (immediate abilities set their own via activate_hero_ability)
                        hero_info = self.game_state.HERO_TYPES.get(hero_name)
                        if hero_info and ability_index is not None:
                            abilities = hero_info.get('abilities', [])
                            if ability_index < len(abilities):
                                ability = abilities[ability_index]
                                cooldown = ability.get('cooldown', 0)
                                if player_id not in self.game_state.hero_ability_cooldowns:
                                    self.game_state.hero_ability_cooldowns[player_id] = {}
                                if hero_name not in self.game_state.hero_ability_cooldowns[player_id]:
                                    self.game_state.hero_ability_cooldowns[player_id][hero_name] = {}
                                self.game_state.hero_ability_cooldowns[player_id][hero_name][ability_name] = cooldown
                    else:
                        # Immediate ability (Reinforce, Vow of Silence, etc.)
                        # Call execute function directly instead of activate_hero_ability
                        # because activate_hero_ability has validation that may fail on receiver
                        # (e.g., checking hero ownership when we already trust the sender)
                        if ability_name == 'Reinforce':
                            success, error_msg = self.game_state.execute_reinforce(player_id)
                            if success:
                                logger.info(f"[NETWORK] Executed Reinforce for player {player_id}")
                            else:
                                logger.error(f"[NETWORK] Reinforce failed for player {player_id}: {error_msg}")
                        elif ability_name == 'Vow of Silence':
                            # Silence all enemy players (counter=2: lasts until end of caster's next turn).
                            # Same target set as the local path: allies are not silenced.
                            for enemy_id in self.game_state.ability_enemies(player_id):
                                self.game_state.hero_silence_status[enemy_id] = 2
                            self.game_state.add_message(f"Player {player_id + 1}: {hero_name} casts Vow of Silence!")
                            # Same sub-line as the local path (heroes._activate_vow_of_silence):
                            # names the silenced players so they see the cast
                            self.game_state.add_message(self.game_state.ability_victims_line(
                                "Heroes silenced until next turn",
                                self.game_state.ability_enemies(player_id)))
                            logger.info(f"[NETWORK] Executed Vow of Silence for player {player_id}")
                        elif ability_name == 'Extort Populace':
                            success, error_msg = self.game_state.execute_extort_populace(player_id)
                            if success:
                                logger.info(f"[NETWORK] Executed Extort Populace for player {player_id}")
                        elif ability_name == 'Embargo':
                            self.game_state._activate_embargo(player_id)
                            logger.info(f"[NETWORK] Executed Embargo for player {player_id}")
                        elif ability_name == 'Master Negotiator':
                            self.game_state._activate_master_negotiator(player_id)
                            logger.info(f"[NETWORK] Executed Master Negotiator for player {player_id}")
                        else:
                            # Fallback for unknown immediate abilities
                            result = self.game_state.activate_hero_ability(hero_name, ability_index)
                            logger.info(f"[NETWORK] activate_hero_ability result for {ability_name}: {result}")

                        # Trigger visual effect for immediate abilities (network replay)
                        self.map_renderer.trigger_ability_effect(
                            ability_name, None, player_id)

                        # Set cooldown for immediate abilities
                        hero_info = self.game_state.HERO_TYPES.get(hero_name)
                        if hero_info and ability_index is not None:
                            abilities = hero_info.get('abilities', [])
                            if ability_index < len(abilities):
                                ability = abilities[ability_index]
                                cooldown = ability.get('cooldown', 0)
                                if player_id not in self.game_state.hero_ability_cooldowns:
                                    self.game_state.hero_ability_cooldowns[player_id] = {}
                                if hero_name not in self.game_state.hero_ability_cooldowns[player_id]:
                                    self.game_state.hero_ability_cooldowns[player_id][hero_name] = {}
                                self.game_state.hero_ability_cooldowns[player_id][hero_name][ability_name] = cooldown
                finally:
                    self.game_state.current_player = original_player

        elif msg_type == MessageType.SIM_ALLIANCE_CHOICE:
            # Territory ownership assignment from alliance arrival (from host)
            territory = data.get('territory')
            new_owner = data.get('new_owner')
            logger.info(f"[NETWORK] Alliance choice: {territory} assigned to player {new_owner}")

            if self.sim_state is not None and territory:
                # Assign territory ownership
                self.game_state.territory_owners[territory] = new_owner
                self.game_state._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                self.game_state.invalidate_territorial_bonus_cache()  # Ownership changed

                # Remove from alliance arrivals
                if territory in self.sim_state.alliance_arrivals:
                    del self.sim_state.alliance_arrivals[territory]

                # Remove from pending_alliance_markers in phase manager (sync with host)
                if hasattr(self.sim_state, 'phase_manager') and self.sim_state.phase_manager:
                    pm = self.sim_state.phase_manager
                    if hasattr(pm, 'pending_alliance_markers') and pm.pending_alliance_markers:
                        # Remove marker for this territory
                        pm.pending_alliance_markers = [
                            m for m in pm.pending_alliance_markers
                            if m.get('territory') != territory
                        ]
                        logger.info(f"[NETWORK] Removed alliance marker for {territory}, {len(pm.pending_alliance_markers)} remaining")

                    # HOST: Complete round if no more battles/markers after client resolved alliance
                    if self.local_player_index == 0:
                        battles_pending = len(self.game_state.pending_battles)
                        markers_pending = len(pm.pending_alliance_markers) if pm.pending_alliance_markers else 0
                        if battles_pending == 0 and markers_pending == 0:
                            logger.info(f"[HOST] All conflicts resolved after remote alliance choice, completing round")
                            self.sim_state.complete_round()

                # Check for overflow
                if hasattr(self.sim_state, 'alliance_handler'):
                    self.sim_state.alliance_handler._check_overflow(territory)

        elif msg_type == MessageType.SIM_ROUND_COMPLETE:
            # Round finished, start new planning phase
            round_number = data.get('round_number', 1)
            logger.info(f"[NETWORK] Round {round_number} complete - starting new planning phase")

            if self.sim_state is not None:
                # Clear movement orders (for arrow display)
                self.game_state.movement_orders.clear()
                logger.info(f"[NETWORK] Cleared movement_orders")

                # Clear player orders in sim_state
                for player_id in self.sim_state.player_orders:
                    self.sim_state.player_orders[player_id].clear()
                logger.info(f"[NETWORK] Cleared player_orders")

                # Apply income and finish constructions/research/castle upgrades for all players
                # Sync fix: must mirror host's complete_round() logic in sim_state.py
                # NOTE: These local computations serve as a fallback if host doesn't send a field.
                # The authoritative override below will overwrite all of these with host's values.
                original_player = self.game_state.current_player
                for player_id in range(self.game_state.num_players):
                    if player_id not in self.sim_state.eliminated_players:
                        self.game_state.collect_income(player_id)
                        self.game_state.current_player = player_id
                        self.game_state.finish_constructions()
                        self.game_state.finish_research()
                        self.game_state.finish_castle_upgrades()
                        self.game_state._tick_building_xp()
                        self.game_state._tick_training_grounds_xp()
                self.game_state.current_player = original_player

                # Start new planning phase BEFORE applying authoritative state.
                # start_planning_phase() resets all 'moved' units to 'ready', so it must run
                # BEFORE the host's garrison override (which has correct moved/ready statuses
                # including newly trained units with 'moved' status).
                self.sim_state.round_number = round_number
                self.sim_state.start_planning_phase()

                # Apply authoritative state from host to prevent desync
                # This overrides local calculations with host's values.
                # Applied AFTER start_planning_phase so garrison moved/ready statuses from host
                # are the final word (not reset by _reset_unit_movement_status).
                if 'player_gold' in data:
                    # player_gold is a list indexed by player_id
                    for player_id, gold in enumerate(data['player_gold']):
                        if player_id < len(self.game_state.player_gold):
                            if self.game_state.player_gold[player_id] != gold:
                                logger.debug(f"[NETWORK] Sync: Player {player_id} gold {self.game_state.player_gold[player_id]} -> {gold}")
                            self.game_state.player_gold[player_id] = gold

                if 'territory_owners' in data:
                    for territory, owner in data['territory_owners'].items():
                        if self.game_state.territory_owners.get(territory) != owner:
                            logger.debug(f"[NETWORK] Sync: {territory} owner {self.game_state.territory_owners.get(territory)} -> {owner}")
                        self.game_state.territory_owners[territory] = owner
                    # Invalidate caches once after bulk sync (not per territory)
                    self.game_state._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
                    self.game_state.invalidate_territorial_bonus_cache()

                if 'eliminated_players' in data:
                    self.sim_state.eliminated_players = set(data['eliminated_players'])
                    # Also sync to game_state's eliminated_players tracker
                    self.game_state.eliminated_players = set(data['eliminated_players'])
                    logger.debug(f"[NETWORK] Sync: eliminated_players = {self.sim_state.eliminated_players}")

                if 'disconnect_eliminations' in data:
                    self.game_state.disconnect_eliminations = set(data['disconnect_eliminations'])
                    logger.debug(f"[NETWORK] Sync: disconnect_eliminations = {self.game_state.disconnect_eliminations}")

                # Sync hero data - ensures passive abilities (Haste, Defiance, etc.) are consistent
                if 'heroes' in data:
                    for player_id_str, player_heroes in data['heroes'].items():
                        player_id = int(player_id_str)
                        self.game_state.heroes[player_id] = player_heroes
                    logger.debug(f"[NETWORK] Sync: heroes for {len(data['heroes'])} players")

                if 'hero_training_queue' in data:
                    self.game_state.hero_training_queue.clear()
                    for territory, plots in data['hero_training_queue'].items():
                        self.game_state.hero_training_queue[territory] = {
                            int(plot): tuple(entry)
                            for plot, entry in plots.items()
                        }
                    logger.debug(f"[NETWORK] Sync: hero_training_queue for {len(data['hero_training_queue'])} territories")

                if 'hero_ability_cooldowns' in data:
                    # Cooldowns are already decremented by host before broadcast
                    # Just sync the authoritative values without decrementing again
                    self.game_state.hero_ability_cooldowns.clear()
                    for player_id_str, player_cooldowns in data['hero_ability_cooldowns'].items():
                        self.game_state.hero_ability_cooldowns[int(player_id_str)] = player_cooldowns
                    logger.debug(f"[NETWORK] Sync: hero_ability_cooldowns for {len(data['hero_ability_cooldowns'])} players")
                else:
                    # Fallback: No authoritative cooldowns sent (older host version?)
                    # Decrement locally to maintain compatibility
                    if hasattr(self.game_state, '_decrement_hero_cooldowns_and_silence'):
                        self.game_state._decrement_hero_cooldowns_and_silence()

                if 'hero_silence_status' in data:
                    # Vow of Silence effect - already decremented by host
                    self.game_state.hero_silence_status.clear()
                    for player_id_str, status in data['hero_silence_status'].items():
                        self.game_state.hero_silence_status[int(player_id_str)] = status
                    logger.debug(f"[NETWORK] Sync: hero_silence_status for {len(data['hero_silence_status'])} players")

                # Sync research state - ensures tech bonuses (Efficient Farming, etc.) are consistent
                if 'player_tech_researched' in data:
                    for player_id_str, techs in data['player_tech_researched'].items():
                        player_id = int(player_id_str)
                        self.game_state.player_tech_researched[player_id] = set(techs)
                    logger.debug(f"[NETWORK] Sync: player_tech_researched for {len(data['player_tech_researched'])} players")

                if 'research_in_progress' in data:
                    self.game_state.research_in_progress.clear()
                    for player_id_str, research in data['research_in_progress'].items():
                        self.game_state.research_in_progress[int(player_id_str)] = research
                    logger.debug(f"[NETWORK] Sync: research_in_progress for {len(data['research_in_progress'])} players")

                if 'player_tech_available' in data:
                    for player_id_str, techs in data['player_tech_available'].items():
                        player_id = int(player_id_str)
                        self.game_state.player_tech_available[player_id] = set(techs)
                    logger.debug(f"[NETWORK] Sync: player_tech_available for {len(data['player_tech_available'])} players")

                # Sync tech effect arrays - derived values for cost discounts, strength bonuses, etc.
                if 'tech_effects' in data:
                    effects = data['tech_effects']
                    if 'royal_decree_discount' in effects:
                        self.game_state.player_royal_decree_discount = effects['royal_decree_discount']
                    if 'training_cost_discount' in effects:
                        self.game_state.player_training_cost_discount = effects['training_cost_discount']
                    if 'cavalry_cost_discount' in effects:
                        self.game_state.player_cavalry_cost_discount = effects['cavalry_cost_discount']
                    if 'archer_keep_strength_bonus' in effects:
                        self.game_state.player_archer_keep_strength_bonus = effects['archer_keep_strength_bonus']
                    if 'farm_destruction_gold_bonus' in effects:
                        self.game_state.player_farm_destruction_gold_bonus = effects['farm_destruction_gold_bonus']
                    if 'cavalry_strength_bonus' in effects:
                        self.game_state.player_cavalry_strength_bonus = effects['cavalry_strength_bonus']
                    if 'divide_conquer_bonus' in effects:
                        self.game_state.player_divide_conquer_bonus = effects['divide_conquer_bonus']
                    if 'barracks_cost_discount' in effects:
                        self.game_state.player_barracks_cost_discount = effects['barracks_cost_discount']
                    if 'barracks_full_refund' in effects:
                        self.game_state.player_barracks_full_refund = effects['barracks_full_refund']
                    if 'hero_keep_defense_bonus' in effects:
                        self.game_state.player_hero_keep_defense_bonus = effects['hero_keep_defense_bonus']
                    logger.debug(f"[NETWORK] Sync: tech_effects (10 effect arrays)")

                # Sync territory garrisons - army positions and unit compositions
                # Critical for fixing forced defender desync where client army moved incorrectly
                if 'territory_garrisons' in data:
                    self.game_state.territory_garrisons.clear()
                    for territory, player_garrisons in data['territory_garrisons'].items():
                        self.game_state.territory_garrisons[territory] = {
                            int(player_id): garrison_data
                            for player_id, garrison_data in player_garrisons.items()
                        }
                    # QA fix: sync legacy army counters to match garrison data
                    # (checksum includes legacy counters, so they must stay in sync)
                    from map_data import get_all_territories
                    for territory in get_all_territories():
                        self.game_state.sync_legacy_garrison_data(territory)
                    logger.debug(f"[NETWORK] Sync: territory_garrisons for {len(data['territory_garrisons'])} territories")

                # Sync fix: apply authoritative building state to prevent permanent divergence
                # from missed demolish messages, construction drift, or castle upgrade desync
                if 'buildings' in data:
                    self.game_state.buildings.clear()
                    for territory, plots in data['buildings'].items():
                        self.game_state.buildings[territory] = {
                            int(plot): btype for plot, btype in plots.items()
                        }
                    logger.debug(f"[NETWORK] Sync: buildings for {len(data['buildings'])} territories")

                if 'under_construction' in data:
                    self.game_state.under_construction.clear()
                    for territory, plots in data['under_construction'].items():
                        self.game_state.under_construction[territory] = {
                            int(plot): tuple(entry) for plot, entry in plots.items()
                        }
                    logger.debug(f"[NETWORK] Sync: under_construction")

                if 'training_queue' in data:
                    self.game_state.training_queue.clear()
                    for territory, plots in data['training_queue'].items():
                        self.game_state.training_queue[territory] = {
                            int(plot): [tuple(entry) for entry in queue]
                            for plot, queue in plots.items()
                        }
                    logger.debug(f"[NETWORK] Sync: training_queue")

                if 'castle_upgrades_in_progress' in data:
                    self.game_state.castle_upgrades_in_progress.clear()
                    for territory, plots in data['castle_upgrades_in_progress'].items():
                        self.game_state.castle_upgrades_in_progress[territory] = {
                            int(plot): turns for plot, turns in plots.items()
                        }
                    logger.debug(f"[NETWORK] Sync: castle_upgrades_in_progress")

                if 'castle_upgrades' in data:
                    self.game_state.castle_upgrades.clear()
                    for territory, plots in data['castle_upgrades'].items():
                        self.game_state.castle_upgrades[territory] = {
                            int(plot): val for plot, val in plots.items()
                        }
                    logger.debug(f"[NETWORK] Sync: castle_upgrades")

                if 'building_xp' in data:
                    self.game_state.building_xp.clear()
                    for territory, plots in data['building_xp'].items():
                        self.game_state.building_xp[territory] = {
                            int(plot): xp for plot, xp in plots.items()
                        }
                    logger.debug(f"[NETWORK] Sync: building_xp")

                if 'hero_ownership' in data:
                    for pid_str, owned_heroes in data['hero_ownership'].items():
                        self.game_state.hero_ownership[int(pid_str)] = set(owned_heroes)
                    logger.debug(f"[NETWORK] Sync: hero_ownership")

                # Sync fix: transient hero ability state
                if 'embargo_blocked_players' in data:
                    self.game_state.embargo_blocked_players = list(data['embargo_blocked_players'])
                    logger.debug(f"[NETWORK] Sync: embargo_blocked_players = {data['embargo_blocked_players']}")

                if 'player_master_negotiator_active' in data:
                    self.game_state.player_master_negotiator_active = list(data['player_master_negotiator_active'])
                    logger.debug(f"[NETWORK] Sync: player_master_negotiator_active")

                # Sync overflow territories — client never runs _process_overflow_territories()
                if 'overflow_territories' in data and self.sim_state is not None:
                    self.sim_state.overflow_territories = data['overflow_territories']
                    logger.debug(f"[NETWORK] Sync: overflow_territories ({len(data['overflow_territories'])} entries)")

                # NOTE: start_planning_phase() already called above (before authoritative override)
                # so garrison moved/ready statuses from host are preserved.
                # Do NOT call round_number or start_planning_phase again here.

                # NOTE: Do NOT call finish_training() or finish_hero_training() here.
                # The host already ran these in complete_round() and sent the results in the
                # authoritative garrisons and training_queue. Calling them again would:
                # 1. Double-decrement training timers (off by 1 turn)
                # 2. Spawn duplicate units into garrisons (desync + tooltip mismatch)
                # The same logic applies to hero training (already documented).

                # Cleanup empty garrisons to prevent ghost armies
                for territory in list(self.game_state.territory_garrisons.keys()):
                    self.game_state.cleanup_empty_garrisons(territory)

                # Clear any stale animation data
                self.game_state.active_animations.clear()

                logger.info(f"[NETWORK] Client round complete processing done")

        elif msg_type == MessageType.FULL_STATE_SYNC:
            # Sync fix: Authoritative state sync from host (sequential mode safety net)
            # QA fix: Queue if battles in progress or animations playing to avoid corruption
            # (previously dropped the message, now queued for later application)
            if (self.game_state.turn_phase == 'battles' and len(self.game_state.pending_battles) > 0):
                logger.info("[NETWORK] Queuing FULL_STATE_SYNC - battles in progress")
                self._pending_full_state_sync = data
                return
            if self.game_state.active_animations:
                logger.info("[NETWORK] Queuing FULL_STATE_SYNC - animations playing")
                self._pending_full_state_sync = data
                return
            logger.info("[NETWORK] Received FULL_STATE_SYNC from host")

            # Apply authoritative gold values
            if 'player_gold' in data:
                for pid, gold in enumerate(data['player_gold']):
                    if pid < len(self.game_state.player_gold):
                        if self.game_state.player_gold[pid] != gold:
                            logger.debug(f"[SYNC] Player {pid} gold {self.game_state.player_gold[pid]} -> {gold}")
                        self.game_state.player_gold[pid] = gold

            # Apply authoritative territory ownership
            if 'territory_owners' in data:
                for territory, owner in data['territory_owners'].items():
                    self.game_state.territory_owners[territory] = owner
                self.game_state._territory_owners_version += 1
                self.game_state.invalidate_territorial_bonus_cache()

            # Apply authoritative garrisons
            if 'territory_garrisons' in data:
                self.game_state.territory_garrisons.clear()
                for territory, player_garrisons in data['territory_garrisons'].items():
                    self.game_state.territory_garrisons[territory] = {
                        int(pid): garrison_data
                        for pid, garrison_data in player_garrisons.items()
                    }
                # QA fix: sync legacy army counters to match garrison data
                # (checksum includes legacy counters, so they must stay in sync)
                from map_data import get_all_territories
                for territory in get_all_territories():
                    self.game_state.sync_legacy_garrison_data(territory)

            # Apply authoritative buildings
            if 'buildings' in data:
                self.game_state.buildings.clear()
                for territory, plots in data['buildings'].items():
                    self.game_state.buildings[territory] = {
                        int(plot): btype for plot, btype in plots.items()
                    }

            # Apply authoritative under_construction
            if 'under_construction' in data:
                self.game_state.under_construction.clear()
                for territory, plots in data['under_construction'].items():
                    self.game_state.under_construction[territory] = {
                        int(plot): tuple(entry) for plot, entry in plots.items()
                    }

            # Apply authoritative training queue
            if 'training_queue' in data:
                self.game_state.training_queue.clear()
                for territory, plots in data['training_queue'].items():
                    self.game_state.training_queue[territory] = {
                        int(plot): [tuple(entry) for entry in queue]
                        for plot, queue in plots.items()
                    }

            # Apply authoritative castle upgrades
            if 'castle_upgrades_in_progress' in data:
                self.game_state.castle_upgrades_in_progress.clear()
                for territory, plots in data['castle_upgrades_in_progress'].items():
                    self.game_state.castle_upgrades_in_progress[territory] = {
                        int(plot): turns for plot, turns in plots.items()
                    }
            if 'castle_upgrades' in data:
                self.game_state.castle_upgrades.clear()
                for territory, plots in data['castle_upgrades'].items():
                    self.game_state.castle_upgrades[territory] = {
                        int(plot): val for plot, val in plots.items()
                    }

            # Apply authoritative research state
            if 'player_tech_researched' in data:
                for pid_str, techs in data['player_tech_researched'].items():
                    self.game_state.player_tech_researched[int(pid_str)] = set(techs)
            if 'research_in_progress' in data:
                self.game_state.research_in_progress.clear()
                for pid_str, research in data['research_in_progress'].items():
                    self.game_state.research_in_progress[int(pid_str)] = research
            if 'player_tech_available' in data:
                for pid_str, techs in data['player_tech_available'].items():
                    self.game_state.player_tech_available[int(pid_str)] = set(techs)

            # Apply authoritative tech effects
            if 'tech_effects' in data:
                effects = data['tech_effects']
                if 'royal_decree_discount' in effects:
                    self.game_state.player_royal_decree_discount = effects['royal_decree_discount']
                if 'training_cost_discount' in effects:
                    self.game_state.player_training_cost_discount = effects['training_cost_discount']
                if 'cavalry_cost_discount' in effects:
                    self.game_state.player_cavalry_cost_discount = effects['cavalry_cost_discount']
                if 'archer_keep_strength_bonus' in effects:
                    self.game_state.player_archer_keep_strength_bonus = effects['archer_keep_strength_bonus']
                if 'farm_destruction_gold_bonus' in effects:
                    self.game_state.player_farm_destruction_gold_bonus = effects['farm_destruction_gold_bonus']
                if 'cavalry_strength_bonus' in effects:
                    self.game_state.player_cavalry_strength_bonus = effects['cavalry_strength_bonus']
                if 'divide_conquer_bonus' in effects:
                    self.game_state.player_divide_conquer_bonus = effects['divide_conquer_bonus']
                if 'barracks_cost_discount' in effects:
                    self.game_state.player_barracks_cost_discount = effects['barracks_cost_discount']
                if 'barracks_full_refund' in effects:
                    self.game_state.player_barracks_full_refund = effects['barracks_full_refund']
                if 'hero_keep_defense_bonus' in effects:
                    self.game_state.player_hero_keep_defense_bonus = effects['hero_keep_defense_bonus']

            # Apply authoritative hero state
            if 'heroes' in data:
                for pid_str, player_heroes in data['heroes'].items():
                    self.game_state.heroes[int(pid_str)] = player_heroes
            if 'hero_training_queue' in data:
                self.game_state.hero_training_queue.clear()
                for territory, plots in data['hero_training_queue'].items():
                    self.game_state.hero_training_queue[territory] = {
                        int(plot): tuple(entry) for plot, entry in plots.items()
                    }
            if 'hero_ability_cooldowns' in data:
                self.game_state.hero_ability_cooldowns.clear()
                for pid_str, cooldowns in data['hero_ability_cooldowns'].items():
                    self.game_state.hero_ability_cooldowns[int(pid_str)] = cooldowns
            if 'hero_silence_status' in data:
                self.game_state.hero_silence_status.clear()
                for pid_str, status in data['hero_silence_status'].items():
                    self.game_state.hero_silence_status[int(pid_str)] = status

            # QA fix: Apply authoritative hero_ownership (prevents desync after hero training/demolish)
            if 'hero_ownership' in data:
                for pid_str, owned_heroes in data['hero_ownership'].items():
                    self.game_state.hero_ownership[int(pid_str)] = set(owned_heroes)
            else:
                # QA fix BUG 8: rebuild hero_ownership from heroes data if not sent explicitly
                # (ensures consistency even with older host versions)
                for pid in range(self.game_state.num_players):
                    owned = set()
                    # Active heroes
                    for hero_type in self.game_state.heroes.get(pid, {}):
                        owned.add(hero_type)
                    # Heroes in training queue
                    for territory, plots in self.game_state.hero_training_queue.items():
                        for plot, entry in plots.items():
                            hero_type = entry[0] if isinstance(entry, (list, tuple)) else entry
                            owner = self.game_state.territory_owners.get(territory)
                            if owner == pid:
                                owned.add(hero_type)
                    self.game_state.hero_ownership[pid] = owned

            # QA fix: Apply authoritative building_xp (Veterancy system)
            if 'building_xp' in data:
                self.game_state.building_xp.clear()
                for territory, plots in data['building_xp'].items():
                    self.game_state.building_xp[territory] = {
                        int(plot): xp for plot, xp in plots.items()
                    }

            # Sync fix: apply transient hero ability state
            if 'embargo_blocked_players' in data:
                self.game_state.embargo_blocked_players = list(data['embargo_blocked_players'])
            if 'player_master_negotiator_active' in data:
                self.game_state.player_master_negotiator_active = list(data['player_master_negotiator_active'])

            # Disconnect elimination tracking — safety net for elimination state sync
            if 'eliminated_players' in data:
                self.game_state.eliminated_players = set(data['eliminated_players'])
                logger.debug(f"[SYNC] eliminated_players = {self.game_state.eliminated_players}")
            if 'disconnect_eliminations' in data:
                self.game_state.disconnect_eliminations = set(data['disconnect_eliminations'])
                logger.debug(f"[SYNC] disconnect_eliminations = {self.game_state.disconnect_eliminations}")

            # Check victory after applying authoritative state (catches any missed eliminations)
            self.game_state.check_victory()

            logger.info("[NETWORK] FULL_STATE_SYNC applied successfully")

        else:
            logger.info(f"[NETWORK] Unknown message type: {msg_type}")

    def _handle_remote_movement_order(self, data: dict):
        """Apply movement order from remote player"""
        from_territory = data.get('from_territory')
        to_territory = data.get('to_territory')
        unit_ids = data.get('unit_ids', [])
        # Get player_index from message (4-player support) or fall back to 2-player logic
        remote_player_index = data.get('player_index')
        if remote_player_index is None:
            # Legacy fallback for 2-player - log warning for 3+ player games
            remote_player_index = 1 if self.local_player_index == 0 else 0
            if self.game_state.num_players > 2:
                logger.warning(f"[NETWORK] WARNING: Movement order missing player_index, falling back to {remote_player_index}")

        # VALIDATION: Player index must be in valid range
        if remote_player_index < 0 or remote_player_index >= self.game_state.num_players:
            logger.warning(f"[NETWORK] REJECTED: Invalid player_index {remote_player_index} (num_players={self.game_state.num_players})")
            return

        # VALIDATION: Verify territory ownership before applying order
        territory_owner = self.game_state.territory_owners.get(from_territory)

        if territory_owner != remote_player_index:
            logger.warning(f"[NETWORK] REJECTED: Movement order from {from_territory} - territory not owned by Player {remote_player_index} (owner={territory_owner})")
            return

        logger.info(f"[NETWORK] Applying movement order from Player {remote_player_index}: {from_territory} -> {to_territory}, units: {unit_ids}")

        # Apply the movement order - unit_ids is already a list of integers
        if unit_ids:
            self.game_state.add_movement_order_for_units(from_territory, to_territory, unit_ids)
        else:
            # Legacy order without specific units
            self.game_state.add_movement_order(from_territory, to_territory)

    def _handle_remote_building_order(self, data: dict):
        """Apply building order from remote player"""
        territory = data.get('territory')
        plot_index = data.get('plot_index')
        building_type = data.get('building_type')
        # Get player_index from message (4-player support) or fall back to 2-player logic
        remote_player_index = data.get('player_index')
        if remote_player_index is None:
            # Legacy fallback for 2-player - log warning for 3+ player games
            remote_player_index = 1 if self.local_player_index == 0 else 0
            if self.game_state.num_players > 2:
                logger.warning(f"[NETWORK] WARNING: Building order missing player_index, falling back to {remote_player_index}")

        # VALIDATION: Player index must be in valid range
        if remote_player_index < 0 or remote_player_index >= self.game_state.num_players:
            logger.warning(f"[NETWORK] REJECTED: Invalid player_index {remote_player_index} (num_players={self.game_state.num_players})")
            return

        # VALIDATION: Verify territory ownership before applying order
        territory_owner = self.game_state.territory_owners.get(territory)

        if territory_owner != remote_player_index:
            logger.warning(f"[NETWORK] REJECTED: Building order in {territory} - territory not owned by Player {remote_player_index} (owner={territory_owner})")
            return

        logger.info(f"[NETWORK] Applying building order from Player {remote_player_index}: {building_type} in {territory} plot {plot_index}")

        # Temporarily set current_player to remote player (start_construction checks current_player)
        # QA fix: use try/finally to prevent current_player corruption on exception
        original_player = self.game_state.current_player
        try:
            self.game_state.current_player = remote_player_index

            # Sync fix: handle castle upgrade as a special building type
            if building_type == 'CastleUpgrade':
                self.game_state.start_castle_upgrade(territory, plot_index)
            else:
                # Apply the building construction
                self.game_state.start_construction(territory, plot_index, building_type)
        finally:
            # Restore current_player even if an exception occurs
            self.game_state.current_player = original_player

    def _handle_remote_training_order(self, data: dict):
        """Apply training order from remote player"""
        territory = data.get('territory')
        barracks_plot = data.get('barracks_plot')
        unit_type = data.get('unit_type')
        # Get player_index from message (4-player support) or fall back to 2-player logic
        remote_player_index = data.get('player_index')
        if remote_player_index is None:
            # Legacy fallback for 2-player - log warning for 3+ player games
            remote_player_index = 1 if self.local_player_index == 0 else 0
            if self.game_state.num_players > 2:
                logger.warning(f"[NETWORK] WARNING: Training order missing player_index, falling back to {remote_player_index}")

        # VALIDATION: Player index must be in valid range
        if remote_player_index < 0 or remote_player_index >= self.game_state.num_players:
            logger.warning(f"[NETWORK] REJECTED: Invalid player_index {remote_player_index} (num_players={self.game_state.num_players})")
            return

        # VALIDATION: Verify territory ownership before applying order
        territory_owner = self.game_state.territory_owners.get(territory)

        if territory_owner != remote_player_index:
            logger.warning(f"[NETWORK] REJECTED: Training order in {territory} - territory not owned by Player {remote_player_index} (owner={territory_owner})")
            return

        logger.info(f"[NETWORK] Applying training order from Player {remote_player_index}: {unit_type} in {territory} barracks {barracks_plot}")

        # Temporarily set current_player to remote player (start_training checks current_player)
        # QA fix: use try/finally to prevent current_player corruption on exception
        original_player = self.game_state.current_player
        try:
            self.game_state.current_player = remote_player_index

            # Apply the training order
            self.game_state.start_training(territory, barracks_plot, unit_type)
        finally:
            # Restore current_player even if an exception occurs
            self.game_state.current_player = original_player

    def _handle_remote_order_remove(self, data: dict):
        """Remove movement order(s) from remote player.

        Handles both single order cancellation (by index) and cancel-all.
        Uses the same current_player swap pattern as other remote handlers
        so that game_state methods see the correct player context.

        Data fields:
            player_index (int): Which player cancelled the order(s).
            cancel_all (bool): If True, cancel all orders for that player.
            player_order_index (int): Index among that player's own orders (current format).
            order_index (int): Legacy — raw index into movement_orders.
        """
        cancel_all = data.get('cancel_all', False)
        order_index = data.get('order_index')
        cancel_type = data.get('cancel_type')  # Sync fix: extended for training/castle/hero cancels
        # Get player_index from message (4-player support) or fall back to 2-player logic
        remote_player_index = data.get('player_index')
        if remote_player_index is None:
            remote_player_index = 1 if self.local_player_index == 0 else 0
            if self.game_state.num_players > 2:
                logger.warning(f"[NETWORK] WARNING: ORDER_REMOVE missing player_index, falling back to {remote_player_index}")

        # VALIDATION: Player index must be in valid range
        if remote_player_index < 0 or remote_player_index >= self.game_state.num_players:
            logger.warning(f"[NETWORK] REJECTED: Invalid player_index {remote_player_index} (num_players={self.game_state.num_players})")
            return

        # Temporarily set current_player to remote player (cancel methods check current_player)
        original_player = self.game_state.current_player
        try:
            self.game_state.current_player = remote_player_index

            # Sync fix: Handle extended cancel types (training, castle upgrade, hero training)
            if cancel_type == 'training':
                territory = data.get('territory')
                barracks_plot = data.get('barracks_plot')
                queue_index = data.get('queue_index')
                if territory is not None and barracks_plot is not None and queue_index is not None:
                    self.game_state.cancel_training(territory, barracks_plot, queue_index)
                    logger.info(f"[NETWORK] Player {remote_player_index} cancelled training in {territory} plot {barracks_plot} index {queue_index}")
                else:
                    logger.warning(f"[NETWORK] ORDER_REMOVE training cancel missing fields")
            elif cancel_type == 'castle_upgrade':
                territory = data.get('territory')
                keep_plot = data.get('keep_plot')
                if territory is not None and keep_plot is not None:
                    self.game_state.cancel_castle_upgrade(territory, keep_plot)
                    logger.info(f"[NETWORK] Player {remote_player_index} cancelled castle upgrade in {territory}")
                else:
                    logger.warning(f"[NETWORK] ORDER_REMOVE castle_upgrade cancel missing fields")
            elif cancel_type == 'hero_training':
                territory = data.get('territory')
                keep_plot = data.get('keep_plot')
                if territory is not None and keep_plot is not None:
                    self.game_state.cancel_hero_training(territory, keep_plot)
                    logger.info(f"[NETWORK] Player {remote_player_index} cancelled hero training in {territory}")
                else:
                    logger.warning(f"[NETWORK] ORDER_REMOVE hero_training cancel missing fields")
            elif cancel_type == 'research':
                # Sync fix: cancel research for remote player
                self.game_state.cancel_research()
                logger.info(f"[NETWORK] Player {remote_player_index} cancelled research")
            elif cancel_type == 'demolish':
                # Sync fix: demolish building for remote player in sequential mode
                territory = data.get('territory')
                plot_index = data.get('plot_index')
                if territory is not None and plot_index is not None:
                    self.game_state.destroy_building(territory, plot_index)
                    logger.info(f"[NETWORK] Player {remote_player_index} demolished building in {territory} plot {plot_index}")
                else:
                    logger.warning(f"[NETWORK] ORDER_REMOVE demolish missing fields")
            elif cancel_all:
                # Only the sender's orders — cancelling every order here wiped the
                # receiver's own orders too
                count = self.game_state.cancel_all_orders(player=remote_player_index)
                logger.info(f"[NETWORK] Player {remote_player_index} cancelled all orders ({count} removed)")
            elif data.get('player_order_index') is not None:
                # Per-player index (the sender's Action Queue position) → full-list index
                full_index = self.game_state.get_full_order_index(
                    remote_player_index, data.get('player_order_index'))
                if full_index is not None and self.game_state.cancel_movement_order(full_index):
                    logger.info(f"[NETWORK] Player {remote_player_index} cancelled their order #{data.get('player_order_index')}")
                else:
                    logger.warning(f"[NETWORK] Player {remote_player_index} cancel order failed: invalid player_order_index {data.get('player_order_index')}")
            elif order_index is not None:
                # Legacy format: raw index into movement_orders
                if self.game_state.cancel_movement_order(order_index):
                    logger.info(f"[NETWORK] Player {remote_player_index} cancelled order at index {order_index}")
                else:
                    logger.warning(f"[NETWORK] Player {remote_player_index} cancel order failed: invalid index {order_index}")
            else:
                logger.warning(f"[NETWORK] ORDER_REMOVE missing both cancel_all and order_index")
        finally:
            # Restore current_player even if cancel methods throw
            self.game_state.current_player = original_player

    def _handle_remote_gold_transfer(self, data: dict):
        """Apply a gold transfer that happened on a remote peer.

        The sender has already deducted locally and broadcast the actual
        post-clamp amount, so we mirror the balance change without
        re-running validation — doing so could reject the transfer for
        the wrong reason (e.g. our view of "current turn" lags slightly).
        """
        sender_idx = data.get('player_index')
        recipient_idx = data.get('recipient_index')
        amount = data.get('amount')

        if sender_idx is None or recipient_idx is None or amount is None:
            logger.warning(f"[NETWORK] REJECTED: GOLD_TRANSFER missing fields: {data}")
            return
        if not (0 <= sender_idx < self.game_state.num_players):
            logger.warning(f"[NETWORK] REJECTED: GOLD_TRANSFER invalid sender {sender_idx}")
            return
        if not (0 <= recipient_idx < self.game_state.num_players):
            logger.warning(f"[NETWORK] REJECTED: GOLD_TRANSFER invalid recipient {recipient_idx}")
            return
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            logger.warning(f"[NETWORK] REJECTED: GOLD_TRANSFER non-int amount {amount!r}")
            return
        if amount <= 0:
            return

        self.game_state.player_gold[sender_idx] -= amount
        self.game_state.player_gold[recipient_idx] += amount

        # Track stats on remote peers too so the recap screen agrees
        stats = getattr(self.game_state, 'player_stats', None)
        if isinstance(stats, dict):
            if sender_idx in stats:
                stats[sender_idx]['gold_sent'] = stats[sender_idx].get('gold_sent', 0) + amount
            if recipient_idx in stats:
                stats[recipient_idx]['gold_received'] = stats[recipient_idx].get('gold_received', 0) + amount

        # Mark the sender→recipient pair as used so peers enforce the once-per-turn rule
        # against any further transfer attempts from the remote sender this turn/round.
        tracker = (self.sim_state.gold_transfers_this_round
                   if self.sim_state is not None
                   else self.game_state.gold_transfers_this_turn)
        tracker.add((sender_idx, recipient_idx))

        # Action log parity — remote peers log the transfer too so everyone sees it.
        sender_name = self.game_state.get_player_name(sender_idx)
        recipient_name = self.game_state.get_player_name(recipient_idx)
        self.game_state.add_message(f"{sender_name} sent {amount}g to {recipient_name}.")

        logger.info(f"[NETWORK] Applied remote GOLD_TRANSFER: {sender_idx} -> {recipient_idx} for {amount}g")

    def _send_full_state_sync(self):
        """
        Sync fix: Send authoritative game state to all clients (host only, sequential mode).
        Called at turn boundaries as a safety net to prevent/correct desync.
        Patterned after SIM_ROUND_COMPLETE authoritative data.
        """
        if not self.multiplayer_mode or self.local_player_index != 0:
            return  # Only host sends state sync
        if self.sim_state is not None:
            return  # Simultaneous mode uses SIM_ROUND_COMPLETE instead

        logger.info("[HOST] Sending FULL_STATE_SYNC (sequential mode safety net)")

        # Build authoritative state snapshot
        state_data = {
            # Gold values - prevents calculation divergence
            'player_gold': list(self.game_state.player_gold),
            # Territory ownership - ensures consistency after battles
            'territory_owners': dict(self.game_state.territory_owners),
            # Territory garrisons - army positions and unit compositions
            # Note: unit dicts may contain 'order' field referencing MovementOrder objects
            # which are not JSON-serializable — strip them during serialization
            'territory_garrisons': {
                territory: {
                    str(player_id): {
                        **garrison_data,
                        'units': [
                            {k: (None if k == 'order' else v) for k, v in unit.items()}
                            for unit in garrison_data.get('units', [])
                        ]
                    } if 'units' in garrison_data else garrison_data
                    for player_id, garrison_data in player_garrisons.items()
                }
                for territory, player_garrisons in self.game_state.territory_garrisons.items()
            },
            # Buildings - complete building state
            'buildings': {
                territory: {str(plot): btype for plot, btype in plots.items()}
                for territory, plots in self.game_state.buildings.items()
            },
            # Under construction - in-progress buildings
            'under_construction': {
                territory: {str(plot): list(entry) for plot, entry in plots.items()}
                for territory, plots in self.game_state.under_construction.items()
            },
            # Training queue - in-progress unit training
            'training_queue': {
                territory: {
                    str(plot): [list(entry) for entry in queue]
                    for plot, queue in plots.items()
                }
                for territory, plots in self.game_state.training_queue.items()
            },
            # Castle upgrades in progress
            'castle_upgrades_in_progress': {
                territory: {str(plot): turns for plot, turns in plots.items()}
                for territory, plots in self.game_state.castle_upgrades_in_progress.items()
            },
            # Completed castle upgrades
            'castle_upgrades': {
                territory: {str(plot): val for plot, val in plots.items()}
                for territory, plots in self.game_state.castle_upgrades.items()
            },
            # Research state
            'player_tech_researched': {
                str(pid): list(techs)
                for pid, techs in self.game_state.player_tech_researched.items()
            },
            'research_in_progress': {
                str(pid): research
                for pid, research in self.game_state.research_in_progress.items()
            },
            'player_tech_available': {
                str(pid): list(techs)
                for pid, techs in self.game_state.player_tech_available.items()
            },
            # Tech effect arrays
            'tech_effects': {
                'royal_decree_discount': list(self.game_state.player_royal_decree_discount),
                'training_cost_discount': list(self.game_state.player_training_cost_discount),
                'cavalry_cost_discount': list(self.game_state.player_cavalry_cost_discount),
                'archer_keep_strength_bonus': list(self.game_state.player_archer_keep_strength_bonus),
                'farm_destruction_gold_bonus': list(self.game_state.player_farm_destruction_gold_bonus),
                'cavalry_strength_bonus': list(self.game_state.player_cavalry_strength_bonus),
                'divide_conquer_bonus': list(self.game_state.player_divide_conquer_bonus),
                'barracks_cost_discount': list(self.game_state.player_barracks_cost_discount),
                'barracks_full_refund': list(self.game_state.player_barracks_full_refund),
                'hero_keep_defense_bonus': list(self.game_state.player_hero_keep_defense_bonus),
            },
            # Heroes
            'heroes': {str(k): v for k, v in self.game_state.heroes.items()},
            'hero_training_queue': {
                territory: {str(plot): list(entry) for plot, entry in plots.items()}
                for territory, plots in self.game_state.hero_training_queue.items()
            },
            'hero_ability_cooldowns': {
                str(pid): cooldowns
                for pid, cooldowns in self.game_state.hero_ability_cooldowns.items()
            },
            'hero_silence_status': {
                str(pid): status
                for pid, status in self.game_state.hero_silence_status.items()
            },
            # QA fix: include hero_ownership to prevent desync after hero training/demolish
            'hero_ownership': {
                str(pid): list(owned_heroes)
                for pid, owned_heroes in self.game_state.hero_ownership.items()
            },
            # QA fix: include building_xp (Veterancy) to prevent silent XP divergence
            'building_xp': {
                territory: {str(plot): xp for plot, xp in plots.items()}
                for territory, plots in self.game_state.building_xp.items()
            },
            # Sync fix: transient hero ability state — prevents desync if ability message lost
            'embargo_blocked_players': list(self.game_state.embargo_blocked_players),
            'player_master_negotiator_active': list(self.game_state.player_master_negotiator_active),
            # Disconnect elimination tracking — safety net for elimination state sync
            'eliminated_players': list(self.game_state.eliminated_players),
            'disconnect_eliminations': list(self.game_state.disconnect_eliminations),
        }

        self._send_action_to_remote(MessageType.FULL_STATE_SYNC, state_data)

        # Sync logger: record turn snapshot at this authoritative sync point (host)
        host_sync_logger = getattr(self.game_state, 'sync_logger', None)
        if host_sync_logger:
            host_sync_logger.record_turn_snapshot(self.game_state.turn_number)

    def _send_action_to_remote(self, action_type: str, data: dict):
        """
        Send an action to the remote player.

        Args:
            action_type: Type of action (e.g., MessageType.MOVEMENT_ORDER)
            data: Action data dict
        """
        if not self.network_connection:
            return

        # Sync logger: record outgoing action before sending
        sync_logger = getattr(self.game_state, 'sync_logger', None)
        if sync_logger:
            sync_logger.record_action(
                action_type, self.local_player_index,
                self.game_state.turn_number, data, source='local'
            )

        # Use the network connection's protocol so the sequence number is continuous
        # across lobby and game phases. Creating a new instance resets seq to 0,
        # causing the server's replay detection to reject game-phase messages
        # (since the lobby already sent seq 0, 1, 2, ... through the same socket).
        current_seq = self.network_connection.protocol._sequence_number
        message = self.network_connection.protocol.encode_message(action_type, data)
        self.network_connection.send_message(message)
        logger.info(f"[NETWORK] Sent {action_type} (seq={current_seq}): {data}")

    # ========== SIMULTANEOUS MODE NETWORK HELPERS ==========

    def _sim_start_execution_phase(self):
        """
        Host starts the execution phase when all players are ready.

        Detects crossing conflicts FIRST, then broadcasts filtered orders to clients.
        This ensures clients don't execute forced defender movement orders.
        """
        if self.sim_state is None:
            return

        # Step 1: Detect crossing conflicts BEFORE sending orders to clients
        # This is critical - clients must receive only valid orders after conflict resolution
        forced_defenders = []
        resolved_orders = dict(self.sim_state.player_orders)  # Copy for modification

        if self.sim_state.phase_manager and self.sim_state.phase_manager.conflict_resolver:
            resolver = self.sim_state.phase_manager.conflict_resolver
            crossing_conflicts = resolver.detect_crossing_conflicts(self.sim_state.player_orders)
            resolved_orders = resolver.resolve_crossing_conflicts(
                self.sim_state.player_orders, crossing_conflicts
            )
            forced_defenders = resolver.get_forced_defenders()
            # NOTE: Don't send separate SIM_FORCED_DEFEND - it's now included in SIM_ALL_READY

        # Step 2: Merge resolved orders (not original orders) for sending to clients
        merged_orders = []
        for player_id, orders in resolved_orders.items():
            for order in orders:
                order_copy = order.copy()
                order_copy['player_id'] = player_id  # Tag with player ID
                merged_orders.append(order_copy)

        logger.info(f"[SIM] Starting execution phase with {len(merged_orders)} merged orders (after conflict resolution)")

        # Step 3: Send SIM_ALL_READY to clients with filtered orders
        if self.multiplayer_mode:
    
            self._send_action_to_remote(MessageType.SIM_ALL_READY, {
                'orders': merged_orders,
                'forced_defenders': [
                    {'player_id': fd.get('player_id'), 'territory': fd.get('territory'),
                     'intended_target': fd.get('intended_target'), 'forced_by': fd.get('forced_by')}
                    for fd in forced_defenders
                ]
            })

        # Step 4: Process forced defenders for host (host doesn't receive SIM_ALL_READY)
        local_player = self.get_local_player()
        for fd in forced_defenders:
            if fd.get('player_id') == local_player:
                fd_territory = fd.get('territory')
                fd_target = fd.get('intended_target')
                logger.info(f"[SIM] Host forced to defend in {fd_territory} (was attacking {fd_target})")
                self._queue_forced_defend_popup(fd_territory, fd_target)

        # Store merged orders reference
        self.sim_state.merged_orders = merged_orders

        # Use phase_manager for execution - pass resolved_orders so it doesn't re-detect conflicts
        if self.sim_state.phase_manager:
            # Skip conflict detection since we already did it above
            self.sim_state.phase_manager.begin_execution_with_resolved(resolved_orders)
        else:
            # Fallback: direct execution (shouldn't happen in normal use)
            self.sim_state.sim_phase = 'executing'
            self._sim_execute_merged_orders(merged_orders)

    def _sim_broadcast_round_complete(self, round_number: int):
        """
        Host broadcasts round completion to all clients.

        Called via callback from sim_state.complete_round() when the round finishes
        (after all battles and alliance markers are resolved).

        Includes authoritative state data to prevent desync:
        - Player gold values (prevents float/calculation divergence)
        - Territory ownership (ensures consistency after battles)

        Args:
            round_number: The new round number after completion
        """
        if not self.multiplayer_mode or self.local_player_index != 0:
            return

        logger.info(f"[HOST] Broadcasting SIM_ROUND_COMPLETE (round {round_number})")

        # Collect authoritative state data to sync
        authoritative_data = {
            'round_number': round_number,
            # Gold values - prevents calculation divergence
            'player_gold': list(self.game_state.player_gold),  # list, not dict
            # Territory ownership - ensures battle results are synchronized
            'territory_owners': dict(self.game_state.territory_owners),
            # Eliminated players - for skip logic in income/construction
            'eliminated_players': list(self.sim_state.eliminated_players) if self.sim_state else [],
            # Hero data - ensures passive abilities (Haste, Defiance, etc.) are consistent
            'heroes': {str(k): v for k, v in self.game_state.heroes.items()},
            # Hero training queue - in-progress training with timers
            'hero_training_queue': {
                territory: {str(plot): list(entry) for plot, entry in plots.items()}
                for territory, plots in self.game_state.hero_training_queue.items()
            },
            # Hero ability cooldowns - for ability availability sync
            'hero_ability_cooldowns': {
                str(player_id): player_cooldowns
                for player_id, player_cooldowns in self.game_state.hero_ability_cooldowns.items()
            },
            # Hero silence status - Vow of Silence effect (blocks enemy abilities)
            'hero_silence_status': {
                str(player_id): status
                for player_id, status in self.game_state.hero_silence_status.items()
            },
            # Research state - ensures tech bonuses (Efficient Farming, etc.) are synchronized
            'player_tech_researched': {
                str(player_id): list(techs)
                for player_id, techs in self.game_state.player_tech_researched.items()
            },
            'research_in_progress': {
                str(player_id): research
                for player_id, research in self.game_state.research_in_progress.items()
            },
            'player_tech_available': {
                str(player_id): list(techs)
                for player_id, techs in self.game_state.player_tech_available.items()
            },
            # Tech effect arrays - derived values applied when research completes
            'tech_effects': {
                'royal_decree_discount': list(self.game_state.player_royal_decree_discount),
                'training_cost_discount': list(self.game_state.player_training_cost_discount),
                'cavalry_cost_discount': list(self.game_state.player_cavalry_cost_discount),
                'archer_keep_strength_bonus': list(self.game_state.player_archer_keep_strength_bonus),
                'farm_destruction_gold_bonus': list(self.game_state.player_farm_destruction_gold_bonus),
                'cavalry_strength_bonus': list(self.game_state.player_cavalry_strength_bonus),
                'divide_conquer_bonus': list(self.game_state.player_divide_conquer_bonus),
                'barracks_cost_discount': list(self.game_state.player_barracks_cost_discount),
                'barracks_full_refund': list(self.game_state.player_barracks_full_refund),
                'hero_keep_defense_bonus': list(self.game_state.player_hero_keep_defense_bonus),
            },
            # Territory garrisons - army positions and unit compositions
            # Prevents desync when forced defenders incorrectly moved on client view
            # Note: unit dicts may contain 'order' field referencing MovementOrder objects
            # which are not JSON-serializable — strip them during serialization
            'territory_garrisons': {
                territory: {
                    str(player_id): {
                        **garrison_data,
                        'units': [
                            {k: (None if k == 'order' else v) for k, v in unit.items()}
                            for unit in garrison_data.get('units', [])
                        ]
                    } if 'units' in garrison_data else garrison_data
                    for player_id, garrison_data in player_garrisons.items()
                }
                for territory, player_garrisons in self.game_state.territory_garrisons.items()
            },
            # Sync fix: building state safety net — prevents permanent divergence if
            # demolish/construction messages are lost or client logic drifts
            'buildings': {
                territory: {str(plot): btype for plot, btype in plots.items()}
                for territory, plots in self.game_state.buildings.items()
            },
            'under_construction': {
                territory: {str(plot): list(entry) for plot, entry in plots.items()}
                for territory, plots in self.game_state.under_construction.items()
            },
            'training_queue': {
                territory: {
                    str(plot): [list(entry) for entry in queue]
                    for plot, queue in plots.items()
                }
                for territory, plots in self.game_state.training_queue.items()
            },
            'castle_upgrades_in_progress': {
                territory: {str(plot): turns for plot, turns in plots.items()}
                for territory, plots in self.game_state.castle_upgrades_in_progress.items()
            },
            'castle_upgrades': {
                territory: {str(plot): val for plot, val in plots.items()}
                for territory, plots in self.game_state.castle_upgrades.items()
            },
            'building_xp': {
                territory: {str(plot): xp for plot, xp in plots.items()}
                for territory, plots in self.game_state.building_xp.items()
            },
            'hero_ownership': {
                str(pid): list(owned_heroes)
                for pid, owned_heroes in self.game_state.hero_ownership.items()
            },
            # Sync fix: transient hero ability state — prevents desync if ability message lost
            'embargo_blocked_players': list(self.game_state.embargo_blocked_players),
            'player_master_negotiator_active': list(self.game_state.player_master_negotiator_active),
            # Overflow territories — client never runs _process_overflow_territories(),
            # so sync the dict to prevent stale overflow icons and state divergence
            'overflow_territories': dict(self.sim_state.overflow_territories) if self.sim_state else {},
            # Disconnect elimination tracking — safety net for elimination state sync
            'disconnect_eliminations': list(self.game_state.disconnect_eliminations),
        }

        self._send_action_to_remote(MessageType.SIM_ROUND_COMPLETE, authoritative_data)

    def _sim_execute_merged_orders(self, orders: list):
        """
        Execute merged orders from all players simultaneously.

        This is used by clients receiving SIM_ALL_READY. It uses the phase_manager's
        movement execution to properly populate _sim_pending_arrivals for arrival processing.

        Args:
            orders: List of order dicts from all players
        """
        if self.sim_state is None:
            return

        logger.info(f"[SIM] Executing {len(orders)} orders simultaneously")

        # Save current_player to restore after execution
        original_current_player = self.game_state.current_player

        # Separate orders by type
        movement_orders = []
        build_orders = []
        train_orders = []
        research_orders = []
        demolish_orders = []
        upgrade_castle_orders = []
        train_hero_orders = []
        hero_ability_orders = []

        for order in orders:
            order_type = order.get('type')
            if order_type == 'movement':
                movement_orders.append(order)
            elif order_type == 'build':
                build_orders.append(order)
            elif order_type == 'train':
                train_orders.append(order)
            elif order_type == 'research':
                research_orders.append(order)
            elif order_type == 'demolish':
                demolish_orders.append(order)
            elif order_type == 'upgrade_castle':
                upgrade_castle_orders.append(order)
            elif order_type == 'train_hero':
                train_hero_orders.append(order)
            elif order_type == 'hero_ability':
                hero_ability_orders.append(order)

        # Get local player index for skip check
        # Local player orders were already executed when clicked (for visual feedback)
        local_player = self.local_player_index

        # Apply non-movement orders with try/finally to guarantee current_player restore
        try:
            # Apply demolish orders first (frees up plots for builds, skip local player's)
            for order in demolish_orders:
                player_id = order.get('player_id')
                if local_player is not None and player_id == local_player:
                    continue
                self.game_state.current_player = player_id
                territory = order.get('territory')
                plot_index = order.get('plot_index')
                if territory and plot_index is not None:
                    self.game_state.demolish_building(territory, plot_index)

            # Apply build orders (skip local player's - already executed)
            for order in build_orders:
                player_id = order.get('player_id')
                if local_player is not None and player_id == local_player:
                    continue  # Already executed locally
                self.game_state.current_player = player_id
                territory = order.get('territory')
                plot_index = order.get('plot_index')
                building_type = order.get('building_type')
                self.game_state.start_construction(territory, plot_index, building_type)

            # Apply upgrade castle orders (skip local player's - already executed)
            for order in upgrade_castle_orders:
                player_id = order.get('player_id')
                if local_player is not None and player_id == local_player:
                    continue
                self.game_state.current_player = player_id
                territory = order.get('territory')
                plot_index = order.get('plot_index')
                if territory and plot_index is not None:
                    self.game_state.start_castle_upgrade(territory, plot_index)

            # Apply train orders (skip local player's - already executed)
            for order in train_orders:
                player_id = order.get('player_id')
                if local_player is not None and player_id == local_player:
                    continue  # Already executed locally
                self.game_state.current_player = player_id
                territory = order.get('territory')
                barracks_plot = order.get('barracks_plot')
                unit_type = order.get('unit_type')
                self.game_state.start_training(territory, barracks_plot, unit_type)

            # Apply research orders (skip local player's - already executed)
            for order in research_orders:
                player_id = order.get('player_id')
                if local_player is not None and player_id == local_player:
                    continue  # Already executed locally
                self.game_state.current_player = player_id
                tech_id = order.get('tech_id')
                if hasattr(self.game_state, 'start_research'):
                    self.game_state.start_research(tech_id)

            # Apply hero ability orders (AI-only path; human players use SIM_HERO_ABILITY messages)
            for order in hero_ability_orders:
                player_id = order.get('player_id')
                if local_player is not None and player_id == local_player:
                    continue
                if self.sim_state and self.sim_state.phase_manager:
                    self.sim_state.phase_manager._apply_hero_ability_order(order)

            # Apply train hero orders (skip local player's - already executed)
            for order in train_hero_orders:
                player_id = order.get('player_id')
                if local_player is not None and player_id == local_player:
                    continue
                self.game_state.current_player = player_id
                territory = order.get('territory')
                keep_plot = order.get('keep_plot')
                hero_type = order.get('hero_type')
                if territory and hero_type is not None:
                    self.game_state.start_hero_training(territory, keep_plot, hero_type)
        finally:
            # Restore original current_player
            self.game_state.current_player = original_current_player

        # Use phase_manager's _execute_movement_orders for proper arrival tracking
        # This populates _sim_pending_arrivals so on_animations_complete works correctly
        if self.sim_state.phase_manager and movement_orders:
            self.sim_state.phase_manager._execute_movement_orders(movement_orders)
        elif movement_orders:
            # Fallback: use execute_all_orders (won't track arrivals properly)
            logger.warning("[WARNING] No phase_manager, using fallback execution")
            for order in movement_orders:
                player_id = order.get('player_id')
                from_territory = order.get('from_territory')
                to_territory = order.get('to_territory')
                unit_ids = order.get('unit_ids', [])
                if unit_ids:
                    self.game_state.add_movement_order_for_units(from_territory, to_territory, unit_ids, player=player_id)
                else:
                    self.game_state.current_player = player_id
                    self.game_state.add_movement_order(from_territory, to_territory)
            self.game_state.current_player = original_current_player
            self.game_state.execute_all_orders()
        else:
            # No movement orders - trigger animation complete immediately
            if self.sim_state.phase_manager:
                self.sim_state.phase_manager.animations_complete = True
                self.sim_state.phase_manager._on_animations_complete()

    def _sim_send_timer_update(self):
        """
        Host sends timer updates to client periodically.

        Called from game loop to keep client timers in sync.
        """
        if not self.multiplayer_mode or self.local_player_index != 0:
            return  # Only host sends timer updates

        if self.sim_state is None or self.sim_state.sim_phase != 'planning':
            return



        # Convert timer dict to string keys for JSON serialization
        timers = {str(k): v for k, v in self.sim_state.player_timers.items()}

        self._send_action_to_remote(MessageType.SIM_TIMER_UPDATE, {
            'timers': timers
        })

    def is_local_player_active(self) -> bool:
        """
        Check if the local player is the active player (can make moves).

        Returns:
            True if local player can act, False if spectating or waiting
        """
        # SIMULTANEOUS MODE: Block actions when player has marked ready (waiting phase)
        if self.sim_state is not None:
            # In simultaneous mode during planning phase
            if self.sim_state.sim_phase == 'planning':
                # Determine local player (the human viewing the game)
                local_player = self.get_local_player()
                # Block if already marked ready
                if self.sim_state.players_ready.get(local_player, False):
                    return False
                return True  # Can act during planning if not ready
            elif self.sim_state.sim_phase == 'resolving':
                # Resolution phase - allow interaction for battle resolution
                return True
            else:
                # Execution phase - view only (animations playing)
                return False

        # SEQUENTIAL MODE
        if not self.multiplayer_mode:
            return True  # Single player always active

        # VALIDATION: Check if local_player_index is initialized
        if self.local_player_index is None:
            logger.warning("[WARNING] local_player_index not initialized, assuming inactive")
            return False

        return self.game_state.current_player == self.local_player_index

    def get_local_player(self) -> int:
        """
        Get the local human player index.

        In multiplayer: Uses local_player_index from network connection
        In single-player: Finds the first non-AI player (the human)

        Returns:
            Player index (0-based) of the local human player
        """
        if self.multiplayer_mode and self.local_player_index is not None:
            return self.local_player_index

        # Single-player: Find the first human (non-AI) player
        for i, is_ai in enumerate(self.game_state.player_is_ai):
            if not is_ai:
                return i

        # Fallback: return 0 if somehow all players are AI
        return 0

    def _is_victory_for_local_player(self):
        """Check if the local human player (or their team) won the game."""
        local = self.get_local_player()
        winner = self.game_state.winner
        if winner is None or winner < 0:  # M3 fix: guard against None winner
            return False
        # Direct match
        if local == winner:
            return True
        # Team match: check if local player and winner are on the same team
        teams = getattr(self.game_state, 'player_teams', None)
        if teams and local < len(teams) and winner < len(teams):
            return teams[local] == teams[winner]
        return False

    def _all_animations_complete(self):
        """Check if all game animations have finished (safe to start victory cinematic).

        Includes battle report popup — cinematic waits until player closes all reports.
        """
        if self.game_state.active_animations:
            return False
        if self.game_state.pending_battles:
            return False
        if self.enhanced_battle_ui is not None:
            return False
        if self.battle_popup_visible:
            return False
        if self.turn_announcement_effect is not None:
            return False
        return True

    def _start_victory_sequence(self):
        """Initialize the victory/defeat cinematic animation sequence."""
        self.victory_sequence_active = True
        self.victory_phase = 'fade'
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0
        self.victory_image_scale = 0.0
        # Determine if local player won or lost
        self.victory_is_win = self._is_victory_for_local_player()

        # Load appropriate image
        img_path = 'assets/victoryscrn.png' if self.victory_is_win else 'assets/defeatscrn.png'
        try:
            self.victory_image = pygame.image.load(img_path).convert_alpha()
        except pygame.error:
            logger.error(f"Failed to load {img_path}")
            self.victory_image = None

    def _update_victory_sequence(self, delta_time):
        """Update the victory/defeat cinematic animation phases.

        Phase timeline: fade (0.5s) → image_grow (0.3s) → image_hold (5.0s) → auto-exit
        Returns True when the sequence is complete and the game loop should exit.
        """
        self.victory_timer += delta_time

        if self.victory_phase == 'fade':
            fade_duration = 0.5
            progress = min(self.victory_timer / fade_duration, 1.0)
            self.victory_fade_alpha = int(255 * progress)
            if self.victory_timer >= fade_duration:
                self.victory_phase = 'image_grow'
                self.victory_timer = 0.0

        elif self.victory_phase == 'image_grow':
            grow_duration = 0.3
            progress = min(self.victory_timer / grow_duration, 1.0)
            # Ease-out quadratic curve for smooth deceleration
            self.victory_image_scale = 0.75 * (1.0 - (1.0 - progress) ** 2)
            if self.victory_timer >= grow_duration:
                self.victory_phase = 'image_hold'
                self.victory_timer = 0.0
                self.victory_image_scale = 0.75

        elif self.victory_phase == 'image_hold':
            hold_duration = 5.0
            if self.victory_timer >= hold_duration:
                return True  # Signal game loop to exit and show recap

        return False

    def _render_victory_sequence(self):
        """Render the victory/defeat cinematic overlay and image."""
        screen_width, screen_height = self.screen.get_size()

        # M5 fix: Use separate cache from draw_victory_screen (which needs SRCALPHA)
        # This one uses per-surface alpha (set_alpha) on a non-SRCALPHA surface
        if not hasattr(self, '_cached_victory_seq_overlay') or self._cached_victory_seq_overlay is None or self._cached_victory_seq_overlay.get_size() != (screen_width, screen_height):
            self._cached_victory_seq_overlay = pygame.Surface((screen_width, screen_height))
        self._cached_victory_seq_overlay.fill((0, 0, 0))
        self._cached_victory_seq_overlay.set_alpha(self.victory_fade_alpha)
        self.screen.blit(self._cached_victory_seq_overlay, (0, 0))

        # Victory/defeat image (during image_grow and image_hold phases)
        if self.victory_image and self.victory_phase in ('image_grow', 'image_hold'):
            img_width = self.victory_image.get_width()
            img_height = self.victory_image.get_height()
            scale = self.victory_image_scale
            if scale > 0:
                scaled_width = int(img_width * scale)
                scaled_height = int(img_height * scale)
                # PERFORMANCE: Cache smoothscale result when scale factor unchanged
                if self._cached_victory_scale != scale:
                    self._cached_victory_scaled_img = pygame.transform.smoothscale(
                        self.victory_image, (scaled_width, scaled_height)
                    )
                    self._cached_victory_scale = scale
                x = (screen_width - scaled_width) // 2
                y = (screen_height - scaled_height) // 2
                self.screen.blit(self._cached_victory_scaled_img, (x, y))

    def get_territory_at_pos(self, pos):
        """
        Find which territory the mouse is over using polygon detection.

        FPS OPT: AABB pre-check skips ~90% of territories before expensive ray-casting.
        Uses pre-computed bounding boxes from map_renderer.territory_bounding_boxes.

        Args:
            pos: (x, y) tuple in WORLD coordinates (not screen coordinates!)
        """
        x, y = pos
        bboxes = self.map_renderer.territory_bounding_boxes
        # Check from end to start to handle overlaps better
        for territory in reversed(list(self.scaled_polygons.keys())):
            # Territories hidden by a campaign mission (enabled-territories filter) are not
            # drawn, so they must not be hoverable/clickable/targetable either — and can
            # therefore never produce an action error. Mirrors map_renderer's draw filter.
            if not map_data.is_territory_enabled(territory):
                continue
            # FPS OPT: AABB pre-check (4 comparisons) before O(n) ray-casting
            bbox = bboxes.get(territory)
            if bbox:
                min_x, min_y, max_x, max_y = bbox
                if x < min_x or x > max_x or y < min_y or y > max_y:
                    continue
            polygon = self.scaled_polygons[territory]
            if map_data.point_in_polygon(pos, polygon):
                return territory
        return None
    
    def get_army_at_pos(self, pos, mode='both'):
        """
        Check if a point lands on an army circle or its banner.

        Supports multi-garrison territories (allied reinforcement): each garrison
        has its own flag position, circle and banner.

        Args:
            pos: (x, y) tuple in WORLD coordinates (not screen coordinates!)
                 Caller should convert screen to world before calling this.
            mode: Which shapes to test -
                  'circle' -> army circles only
                  'banner' -> banner rects only
                  'both'   -> circles across ALL territories first, then banners

        Returns:
            (territory, player_index) tuple if the point hits one of the current
            player's garrisons, None otherwise.

        Selection semantics are unchanged: only the CURRENT player's garrison is
        ever returned. Other players' banners are hoverable but not clickable.

        Why circles are tested before banners ('both'):
            At minimum zoom a banner is ~30 world units tall while sibling flags
            sit on a radius-25 ring, so a banner routinely overlaps a NEIGHBOURING
            territory's circle. Testing every circle before any banner keeps
            "click the ring you can actually see" working.
        """
        x, y = pos

        current_player = self.game_state.current_player

        # PERFORMANCE: index inbound animations once instead of rescanning the
        # full animation list inside the per-territory loop (was O(T*A)).
        incoming_by_territory = {}
        for anim in self.game_state.active_animations:
            if anim.to_territory not in incoming_by_territory:
                incoming_by_territory[anim.to_territory] = set()
            incoming_by_territory[anim.to_territory].add(anim.player)

        banner_hit = None

        # Single traversal, but circles resolve immediately while banners are
        # deferred until the loop ends - that makes it a true global two-pass.
        for territory, (cx, cy) in self.scaled_centers.items():
            garrisons = self.game_state.territory_garrisons.get(territory, {})
            if current_player not in garrisons:
                continue

            num_garrisons = self.get_effective_garrison_count(
                territory, garrisons, incoming_by_territory.get(territory, set())
            )

            anchor = self.get_garrison_anchor(territory, cx, cy, current_player,
                                              num_garrisons)
            if anchor is None:
                continue
            anchor_x, anchor_y, army_count = anchor

            if mode in ('circle', 'both'):
                if self.point_in_army_circle(x, y, anchor_x, anchor_y):
                    return (territory, current_player)

            if mode in ('banner', 'both'):
                if self.point_in_army_banner(x, y, anchor_x, anchor_y,
                                             current_player, army_count):
                    # Keep the LAST match, not the first: the renderer iterates
                    # scaled_centers in this same order, so a later territory is
                    # drawn on top - last match is the topmost banner.
                    banner_hit = (territory, current_player)

        return banner_hit
    
    def get_plot_at_pos(self, pos):
        """
        Find which plot (if any) was clicked.
        
        Now accounts for both camera zoom and UI scaling to ensure click area
        matches the visual plot circle size exactly at all zoom levels.
        
        Args:
            pos: (x, y) tuple in WORLD coordinates (not screen coordinates!)
                 Caller should convert screen to world before calling this.
        
        Returns:
            (territory, plot_index) tuple if click is on a plot, None otherwise
        
        Note:
            Phase 2D: Now expects world coordinates. Callers must use
            screen_to_world() before calling this method.
            
            Click radius calculation:
            - Visual radius in screen space: EMPTY_PLOT_RADIUS * ui_scale
            - Convert to world space: (screen_radius / camera_zoom)
            - This ensures click area matches visual size at all zoom levels
        """
        x, y = pos
        
        # Calculate click radius in world space that matches visual plot size
        ui_scale = self.get_ui_scale_factor()
        # Plots now use EMPTY_PLOT_RADIUS for visual size, so click should match
        plot_click_radius_world = (EMPTY_PLOT_RADIUS * ui_scale) / self.camera_zoom
        
        # Check all territories (scaled_plots are in world coordinates)
        for territory, plots in self.scaled_plots.items():
            # Only check plots in territories owned by current player in playing phase
            if self.game_state.phase == 'playing':
                if self.game_state.territory_owners.get(territory, -1) != self.game_state.current_player:
                    continue
            
            for plot_index, plot_pos in enumerate(plots):
                px, py = plot_pos
                # Check if click is within plot radius (accounting for zoom and UI scale)
                distance = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
                if distance < plot_click_radius_world:
                    return (territory, plot_index)
        
        return None
    
    # ========================================
    # PHASE 2D: CAMERA TRANSFORMATION METHODS
    # ========================================
    
    def screen_to_world(self, screen_pos):
        """
        Convert screen coordinates to world coordinates.
        
        Wrapper that delegates to camera handler.
        
        Args:
            screen_pos: (x, y) tuple in screen coordinates
        
        Returns:
            (x, y) tuple in world coordinates
        """
        return self.camera.screen_to_world(screen_pos, TOP_PANEL_HEIGHT)
    
    def world_to_screen(self, world_pos):
        """
        Convert world coordinates to screen coordinates.
        
        Wrapper that delegates to camera handler.
        
        Args:
            world_pos: (x, y) tuple in world coordinates
        
        Returns:
            (x, y) tuple in screen coordinates
        """
        return self.camera.world_to_screen(world_pos, TOP_PANEL_HEIGHT)
    
    def get_ui_scale_factor(self):
        """
        Get UI element scale factor based on current zoom level.

        Wrapper that delegates to camera handler.

        Returns:
            float: Scale multiplier for UI element sizes (1.0 to 1.5)
        """
        return self.camera.get_ui_scale_factor()

    def get_army_flag_tier(self, army_count):
        """
        Determine which flag tier to display based on army count.

        Args:
            army_count: Total number of armies in territory

        Returns:
            int: Flag tier (1, 2, or 3)
                 - Tier 1: 1-4 armies
                 - Tier 2: 5-9 armies
                 - Tier 3: 10+ armies
        """
        if army_count <= 4:
            return 1
        elif army_count <= 9:
            return 2
        else:
            return 3

    # ============================================================
    # ARMY BANNER GEOMETRY - SINGLE SOURCE OF TRUTH
    # ============================================================
    # The banner (flag) drawn above an army circle is a first-class click/hover
    # target, not just decoration. Three separate passes need its geometry:
    #   - click  : get_army_at_pos()            (world space)
    #   - hover  : handle_mouse_motion()        (world space)
    #   - render : MapRenderer.draw_territories() (screen space)
    # These used to each recompute it independently and DISAGREED - the click box
    # was only half the banner's height, so the flag cloth was unclickable, and
    # hover ignored the banner entirely. Everything now routes through the helpers
    # below so the three passes cannot drift apart again.

    def get_army_flag_aspect(self, player_index, army_count):
        """
        Get width/height ratio of the SOURCE flag art for a garrison.

        Args:
            player_index: Garrison owner (-1 for neutral)
            army_count: Garrison size (selects flag tier 1/2/3 - tiers have
                        different aspect ratios, so this matters)

        Returns:
            float aspect ratio, or None if this garrison has no flag art.

        None is meaningful: the renderer falls back to drawing a plain army-count
        number instead of a banner (different footprint), so callers must NOT
        hit-test a banner in that case.

        NOT memoised on purpose - campaign missions hot-swap army_flag_icons
        entries at runtime (see campaign_mission_2.py), and two Surface attribute
        reads are cheaper than a correct cache-invalidation scheme.
        """
        tier = self.get_army_flag_tier(army_count)
        icon = self.army_flag_icons.get(player_index, {}).get(tier)
        if icon is None:
            return None
        height = icon.get_height()
        if height <= 0:
            return DEFAULT_ARMY_FLAG_ASPECT
        return icon.get_width() / height

    def get_army_circle_hit(self, center_x, center_y, space='world'):
        """
        Get the VISIBLE army ring's circle - the one the player actually sees.

        MapRenderer._draw_army_circle() draws the ring 25% smaller than
        ARMY_CIRCLE_RADIUS and lifted above the anchor, so the flag pole sits
        inside it. Hit-testing must use the same geometry.

        Args:
            center_x, center_y: Garrison anchor (flag-pole base) in `space` coords
            space: 'world' for hit-testing, 'screen' for rendering

        Returns:
            (x, y, radius) of the drawn ring. y is LIFTED above the anchor.

        The glow halo around the ring is deliberately excluded: it is a soft
        alpha-35 decoration, not part of the object you are aiming at.
        """
        base_radius = ARMY_CIRCLE_RADIUS * self.get_ui_scale_factor()
        radius = base_radius * ARMY_CIRCLE_DRAW_SCALE
        lift = base_radius * ARMY_CIRCLE_DRAW_LIFT

        if space == 'world':
            inv_zoom = 1.0 / self.camera_zoom
            radius *= inv_zoom
            lift *= inv_zoom

        return (center_x, center_y - lift, radius)

    def point_in_army_circle(self, px, py, center_x, center_y, space='world'):
        """
        Check whether a point falls inside the drawn army ring.

        The point and the anchor must be expressed in the SAME space.
        """
        circle_x, circle_y, radius = self.get_army_circle_hit(center_x, center_y, space)
        return (px - circle_x) ** 2 + (py - circle_y) ** 2 <= radius * radius

    def get_army_banner_rect(self, center_x, center_y, player_index, army_count,
                             space='world'):
        """
        Get the geometry of the army banner drawn above an army circle.

        The banner is blitted with its pole base at (center_x, center_y) and
        extends UPWARD by its full height. Width comes from the source art's
        aspect ratio, NOT from the circle radius.

        Args:
            center_x, center_y: Garrison anchor in `space` coordinates. This is the
                territory center for a single garrison, or flag_positions[idx] for
                one of several garrisons in an allied-reinforced territory.
            player_index: Garrison owner (-1 for neutral) - selects the art
            army_count: Garrison size - selects the flag tier
            space: 'world' for hit-testing (scaled_centers / flag_positions are in
                   world coords), 'screen' for rendering (world_to_screen output).
                   world_to_screen is a uniform scale+offset, so an axis-aligned
                   world rect maps exactly to an axis-aligned screen rect - one
                   primitive serves both spaces via a single division.

        Returns:
            (left, top, width, height) as floats, or None if no flag art exists.
            top == center_y - height, bottom == center_y.

        Returns a plain tuple rather than a pygame.Rect because Rect coerces its
        values to int, and world coordinates are fractional.
        """
        aspect = self.get_army_flag_aspect(player_index, army_count)
        if aspect is None:
            return None

        height = ARMY_CIRCLE_RADIUS * self.get_ui_scale_factor() * ARMY_FLAG_HEIGHT_RATIO
        width = height * aspect

        if space == 'world':
            # Convert screen-pixel size back into world units so the hit box
            # tracks the drawn banner at every zoom level.
            inv_zoom = 1.0 / self.camera_zoom
            height *= inv_zoom
            width *= inv_zoom

        return (center_x - width / 2.0, center_y - height, width, height)

    def point_in_army_banner(self, px, py, center_x, center_y, player_index,
                             army_count, space='world'):
        """
        Check whether a point falls inside a garrison's banner.

        The point and the anchor must be expressed in the SAME space.
        Returns False when the garrison has no banner art (nothing was drawn).
        """
        rect = self.get_army_banner_rect(center_x, center_y, player_index,
                                         army_count, space)
        if rect is None:
            return False
        left, top, width, height = rect
        return left <= px <= left + width and top <= py <= top + height

    def get_effective_garrison_count(self, territory, garrisons=None,
                                     incoming_players=None):
        """
        Get the number of flag SLOTS a territory uses for its garrison layout.

        MUST match the renderer exactly, or hit boxes land where no flag is drawn.
        This logic used to be copy-pasted into the click path, the hover path and
        the renderer - and the click copy was missing the allied-reinforcement
        rule, which made a garrison briefly unclickable mid-animation.

        Rules, in order:
          1. Count garrisons that actually have armies.
          2. Widen the count to include in-flight arrivals, so flags don't "jump"
             when a movement animation lands.
          3. Allied-reinforcement rule: an OWNED territory whose only future
             garrison is not the owner uses the 2-slot layout, to match where the
             animation is flying to.

        Args:
            territory: Territory name
            garrisons: Optional pre-fetched garrison dict (avoids a re-lookup)
            incoming_players: Optional pre-built set of inbound players, for
                callers that already indexed active_animations by destination
                (the renderer does this once per frame).
        """
        if garrisons is None:
            garrisons = self.game_state.territory_garrisons.get(territory, {})

        present = {p for p, g in garrisons.items()
                   if g.get('unmoved', 0) + g.get('moved', 0) > 0}
        num_garrisons = len(present)

        if incoming_players is None:
            incoming_players = {anim.player for anim in self.game_state.active_animations
                                if anim.to_territory == territory}

        if incoming_players:
            future_garrisons = present | incoming_players
            num_garrisons = len(future_garrisons)

            # Allied reinforcement: use the 2-position layout so the static flag
            # sits where the incoming animation is headed.
            owner = self.game_state.territory_owners.get(territory, -1)
            if owner >= 0 and num_garrisons == 1:
                if next(iter(future_garrisons)) != owner:
                    num_garrisons = 2

        return num_garrisons

    def get_garrison_anchor(self, territory, center_x, center_y, player_index,
                            num_garrisons=None):
        """
        Get the world-space anchor (flag-pole base / circle center) for ONE
        player's garrison in a territory.

        Collapses the single-garrison and multi-garrison branches that the click,
        hover and render paths each used to open-code.

        Args:
            territory: Territory name
            center_x, center_y: Territory center in world coords (scaled_centers)
            player_index: Which garrison to locate
            num_garrisons: Optional pre-computed slot count from
                get_effective_garrison_count() (avoids recomputing per garrison)

        Returns:
            (x, y, army_count) in world coords, or None if this player has no
            armies in this territory.

        NOTE: calls assign_garrison_position(), which mutates
        game_state.garrison_positions. That is pre-existing behaviour of both
        hit-test paths and is preserved deliberately - slot assignment must be
        identical across click, hover and render or the flags shuffle.
        """
        garrisons = self.game_state.territory_garrisons.get(territory, {})
        garrison = garrisons.get(player_index)
        if not garrison:
            return None

        army_count = garrison.get('unmoved', 0) + garrison.get('moved', 0)
        if army_count <= 0:
            return None

        if num_garrisons is None:
            num_garrisons = self.get_effective_garrison_count(territory, garrisons)

        if num_garrisons <= 1:
            return (center_x, center_y, army_count)

        flag_positions = self.game_state.get_flag_positions_for_territory(
            territory, center_x, center_y, num_garrisons
        )

        # Assign slots for EVERY live garrison before reading one index, so the
        # indices are stable and match the renderer's assignment order.
        for other_player in sorted(garrisons.keys()):
            other = garrisons[other_player]
            if other.get('unmoved', 0) + other.get('moved', 0) > 0:
                self.game_state.assign_garrison_position(territory, other_player,
                                                         num_garrisons)

        garrison_index = self.game_state.assign_garrison_position(
            territory, player_index, num_garrisons
        )
        if garrison_index >= len(flag_positions):
            return (center_x, center_y, army_count)

        flag_x, flag_y = flag_positions[garrison_index]
        return (flag_x, flag_y, army_count)

    def trigger_click_flash(self, element_type, identifier):
        """
        Trigger a brief visual flash when an element is clicked.
        
        Sets clicked_element and resets click_flash_timer to show a brief
        brightened color feedback when user clicks on interactive elements.
        
        Args:
            element_type: str, type of element ('bottom_button', 'map_plot', etc.)
            identifier: varies, unique identifier for the element
        
        Example:
            self.trigger_click_flash('bottom_button', 'end_turn')
            # End Turn button will flash bright for 150ms
        
        Performance:
            O(1) - just sets two variables
            No allocations, negligible cost
        """
        self.clicked_element = (element_type, identifier)
        self.click_flash_timer = self.click_flash_duration
    
    @staticmethod
    def _cycle_fps_limit(current):
        """Advance to the next FPS-limit option, wrapping around."""
        try:
            idx = FPS_LIMIT_OPTIONS.index(current)
        except ValueError:
            idx = 0  # Unknown/legacy value — restart from "Unlimited"
        return FPS_LIMIT_OPTIONS[(idx + 1) % len(FPS_LIMIT_OPTIONS)]

    def apply_display_settings(self, width, height, fullscreen=False, vsync=None):
        """
        Apply new display settings (resolution, fullscreen mode and VSync).

        `vsync=None` keeps the current setting; pass True/False to change it.

        IMPORTANT: In fullscreen mode, always uses native monitor resolution to prevent
        scaling/letterboxing issues. Custom resolutions only work in windowed mode.
        
        This method safely updates all window-size-dependent calculations:
        - Recreates display surface
        - Recalculates map scaling
        - Rescales all polygons and plots
        - Clears caches
        - Resets camera to default position
        
        Args:
            width: New window width (ignored in fullscreen - uses native)
            height: New window height (ignored in fullscreen - uses native)
            fullscreen: Whether to use fullscreen mode
        
        Returns:
            bool: True if successful, False if failed
        
        Side Effects:
            - Modifies global constants
            - Recreates display surface
            - Rescales all map-related data
            - Resets camera position and zoom
            - Clears selections
        """
        global WINDOW_WIDTH, WINDOW_HEIGHT, MAP_WIDTH, MAP_HEIGHT, BOTTOM_UI_Y, TOP_PANEL_HEIGHT, BOTTOM_UI_HEIGHT
        
        try:
            # CRITICAL: In fullscreen mode, ALWAYS use native resolution
            # This prevents scaling/letterboxing issues and is standard practice
            if fullscreen:
                actual_width = self.native_resolution[0]
                actual_height = self.native_resolution[1]
                logger.info(f"[INFO] Fullscreen mode: Using native resolution {actual_width}x{actual_height}")
            else:
                actual_width = width
                actual_height = height
            
            # Calculate new UI layout using UIScaler
            new_layout = UIScaler.calculate_ui_layout(actual_width, actual_height)
            
            # Update global constants with dynamically calculated values
            WINDOW_WIDTH = actual_width
            WINDOW_HEIGHT = actual_height
            TOP_PANEL_HEIGHT = new_layout['top_height']
            BOTTOM_UI_HEIGHT = new_layout['bottom_height']
            MAP_WIDTH = WINDOW_WIDTH
            MAP_HEIGHT = new_layout['map_height']
            BOTTOM_UI_Y = new_layout['bottom_y']
            
            # Update UIConstants with new sidebar height
            UIConstants.update_sidebar_height(new_layout['sidebar_height'])
            
            # Recreate display surface.
            # CRITICAL: route through set_display_mode so VSync survives. VSync is
            # silently lost by ANY later set_mode() call, even one passing vsync=1
            # again — only a display quit()/init() restores it. Since this method IS
            # the resolution path, a plain set_mode() here would mean VSync died the
            # first time a player changed resolution and never came back.
            want_vsync = self.vsync if vsync is None else vsync
            self.screen, self.vsync_active = set_display_mode(
                (actual_width, actual_height), fullscreen, want_vsync,
                force_reinit=(self.vsync_active and not want_vsync))
            self.vsync = want_vsync
            _set_app_icon()  # Re-apply icon after display recreation

            # CRITICAL FIX: Check if pygame created a different size (happens with Windows display scaling)
            created_size = self.screen.get_size()
            if created_size != (actual_width, actual_height):
                logger.warning(f"WARNING:  Display scaling detected during resolution change!")
                logger.info(f"   Requested: {actual_width}x{actual_height}")
                logger.info(f"   Created:   {created_size[0]}x{created_size[1]}")
                logger.info(f"   Recalculating UI for actual size...")
                
                # Update to use actual created size
                actual_width = created_size[0]
                actual_height = created_size[1]
                
                # Recalculate UI layout for actual size
                new_layout = UIScaler.calculate_ui_layout(actual_width, actual_height)
                
                # Update global constants again
                WINDOW_WIDTH = actual_width
                WINDOW_HEIGHT = actual_height
                TOP_PANEL_HEIGHT = new_layout['top_height']
                BOTTOM_UI_HEIGHT = new_layout['bottom_height']
                MAP_WIDTH = WINDOW_WIDTH
                MAP_HEIGHT = new_layout['map_height']
                BOTTOM_UI_Y = new_layout['bottom_y']
                UIConstants.SIDEBAR_HEIGHT = new_layout['sidebar_height']
                
                # Update native resolution if in fullscreen
                if fullscreen:
                    self.native_resolution = (actual_width, actual_height)

                    # CRITICAL: Reapply fullscreen mode to prevent dropping to windowed
                    # This ensures fullscreen persists even after display scaling adjustments
                    logger.info(f"[FIX] Reapplying fullscreen mode after scaling adjustment...")
                    self.screen, self.vsync_active = set_display_mode(
                        (actual_width, actual_height), True, want_vsync)
                    _set_app_icon()  # Re-apply icon after fullscreen reapply

                    # Verify it's actually fullscreen
                    final_size = self.screen.get_size()
                    if final_size == (actual_width, actual_height):
                        logger.info(f"[OK] Fullscreen mode preserved: {actual_width}x{actual_height}")
                    else:
                        logger.warning(f"WARNING: Unexpected size after reapply: {final_size[0]}x{final_size[1]}")

            # Recalculate scaling
            width_scale = MAP_WIDTH / ORIGINAL_MAP_WIDTH
            height_scale = MAP_HEIGHT / ORIGINAL_MAP_HEIGHT
            self.scale_factor = min(width_scale, height_scale)
            
            # Recalculate map dimensions
            self.map_width = int(ORIGINAL_MAP_WIDTH * self.scale_factor)
            self.map_height = int(ORIGINAL_MAP_HEIGHT * self.scale_factor)
            
            # Update camera handler with new dimensions
            self.camera.update_map_dimensions(
                self.map_width,
                self.map_height,
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
                MAP_HEIGHT
            )
            
            # Update mouse handler with new layout values
            self.mouse.update_layout(TOP_PANEL_HEIGHT, BOTTOM_UI_Y, WINDOW_WIDTH)
            # (Sidebar geometry needs no update: get_sidebar_layout() reads the
            # current WINDOW_WIDTH / TOP_PANEL_HEIGHT / MAP_HEIGHT on every call.)

            # Update UI renderer with new layout values
            layout_values = {
                'window_width': WINDOW_WIDTH,
                'window_height': WINDOW_HEIGHT,
                'top_panel_height': TOP_PANEL_HEIGHT,
                'bottom_ui_y': BOTTOM_UI_Y,
                'bottom_ui_height': BOTTOM_UI_HEIGHT,
                'map_height': MAP_HEIGHT
            }
            self.ui_renderer.update_layout(layout_values)
            
            # Re-convert the map to the NEW display format before rescaling.
            # .convert() bakes in the pixel format of the display that was current
            # at load time; set_mode() above may have changed it (resolution,
            # fullscreen, or the SCALED/vsync flags). Skipping this would silently
            # reintroduce the ~9ms-per-frame unconverted blit after a settings change.
            try:
                self.map_image_original = self.map_image_original.convert()
            except pygame.error as e:
                logger.warning(f"Could not re-convert map image after display change: {e}")

            # Rescale map image from original (ensures high quality)
            self.map_image = pygame.transform.scale(
                self.map_image_original,
                (self.map_width, self.map_height)
            )

            # Rescale polygons (using round() to match __init__ for smoother edges)
            for territory, polygon in map_data.TERRITORY_POLYGONS.items():
                self.scaled_polygons[territory] = [
                    (round(x * self.scale_factor), round(y * self.scale_factor))
                    for x, y in polygon
                ]

            # Rescale centers
            for territory, center in map_data.TERRITORY_CENTERS.items():
                self.scaled_centers[territory] = (
                    round(center[0] * self.scale_factor),
                    round(center[1] * self.scale_factor)
                )

            # Rescale plots
            for territory, plots in map_data.TERRITORY_PLOTS.items():
                self.scaled_plots[territory] = [
                    (round(x * self.scale_factor), round(y * self.scale_factor))
                    for x, y in plots
                ]
            
            # Clear caches (H11 fix: also clear icon/text caches to prevent stale entries)
            # Viewport map cache + east extension: their surfaces were created in the
            # OLD display format and the layout globals (window width, map width) have
            # changed, so drop them all.
            self._invalidate_map_background_caches()
            # The map scale_factor just changed, so the renderer's pre-computed
            # bounding boxes and multi-zoom polygons are stale (they were built from
            # the polygons at the OLD scale). Without this, territory polygons
            # misalign with the map and hit-testing goes wrong after a resolution change.
            if hasattr(self, 'map_renderer') and self.map_renderer is not None:
                self.map_renderer.rebuild_scale_caches()
            self._ui_icon_cache = {}
            self._tech_border_cache = {}
            self._text_cache = {}
            self._rotated_tab_text_cache = {}
            self._sidebar_toggle_sprites = {}  # Rebuilt from CircleBorder in the new display format
            # Sidebar widget sprites/fonts follow ui_scale and the display format
            if getattr(self, 'sidebar_widgets', None) is not None:
                self.sidebar_widgets.invalidate()
            self._hero_overlay_cache = {}
            # Close the unit context menu: its anchor rect belongs to the old layout
            self.unit_context_menu = None
            self.unit_context_menu_rects = []
            # Battle Reports: drop the cached board (it was convert_alpha()'d against the
            # old display surface) and the rects, which belong to the old layout. The
            # popups themselves survive - their anchors re-derive from scaled_centers.
            self.battle_report_rects = []
            if self.battle_report_renderer is not None:
                self.battle_report_renderer.invalidate()
            # Territory preview caches (border scaled size + preview images)
            self._territory_preview_cache = {}
            self._scaled_preview_border = None
            self._scaled_preview_border_size = None
            self.territory_preview_rect = None
            self._build_particle_caches()  # Rebuild PNG particle caches for new display
            invalidate_cursor_cache()  # Reload custom cursor after display mode change
            pygame.mouse.set_visible(False)  # Re-hide system cursor after display recreation

            # H3 fix: Update ui_scale and fonts after resolution change
            REFERENCE_WIDTH = 1600
            REFERENCE_HEIGHT = 900
            self.ui_scale = min(actual_width / REFERENCE_WIDTH, actual_height / REFERENCE_HEIGHT)
            self.font = self.font_manager.get_font(int(15 * self.ui_scale))
            self.large_font = self.font_manager.get_font(int(24 * self.ui_scale))
            self.small_font = self.font_manager.get_font(int(12 * self.ui_scale))
            self.small_font_bold = self.font_manager.get_bold_font(int(12 * self.ui_scale))
            self.font_bold = self.font_manager.get_bold_font(int(15 * self.ui_scale))
            self.large_font_bold = self.font_manager.get_bold_font(int(24 * self.ui_scale))
            # Separate italic objects - never set_italic() on a shared get_font() result
            self.small_font_italic = self.font_manager.get_italic_font(int(12 * self.ui_scale))
            self.lore_font_italic = self.font_manager.get_italic_font(int(16 * self.ui_scale))
            extra_small_size = 8 if actual_height == 720 else int(10 * self.ui_scale)
            self.extra_small_font = self.font_manager.get_font(extra_small_size)

            # M1 fix: Update instance layout attributes to match new globals
            self.TOP_PANEL_HEIGHT = TOP_PANEL_HEIGHT
            self.BOTTOM_UI_HEIGHT = BOTTOM_UI_HEIGHT
            self.MAP_HEIGHT = MAP_HEIGHT

            # Update chat notification effect with new layout/fonts
            if self.chat_notification_effect:
                self.chat_notification_effect.on_resolution_change(
                    TOP_PANEL_HEIGHT, self.small_font, self.small_font_bold
                )

            # Update helpers with new fonts/screen
            self.helpers = DrawingHelpers(self.screen, self.font, self.small_font, self.large_font,
                                          self.separator_image, self.separator_width,
                                          small_font_bold=self.small_font_bold)

            # Reset cached font sizes for AI indicator, spectator text, etc.
            self._ai_indicator_title_font = None
            self._ai_indicator_subtitle_font = None
            if hasattr(self, '_cached_spectator_text'):
                self._cached_spectator_text = None

            # Rescale panel images to new resolution
            # Bottom panel
            if self.bottom_panel_image:
                try:
                    bottom_panel_original = pygame.image.load("assets/BottomPanel.jpg")
                    self.bottom_panel_image = pygame.transform.scale(
                        bottom_panel_original,
                        (WINDOW_WIDTH, BOTTOM_UI_HEIGHT)
                    )
                except pygame.error:
                    pass  # Keep old scaled version if reload fails
            
            # Top panel
            if self.top_panel_image:
                try:
                    top_panel_original = pygame.image.load("assets/TopPanel.jpg")
                    self.top_panel_image = pygame.transform.scale(
                        top_panel_original,
                        (WINDOW_WIDTH, TOP_PANEL_HEIGHT)
                    )
                except pygame.error:
                    pass  # Keep old scaled version if reload fails
            
            # Right panel
            sidebar_height = WINDOW_HEIGHT - TOP_PANEL_HEIGHT - BOTTOM_UI_HEIGHT
            if self.right_panel_image:
                try:
                    right_panel_original = pygame.image.load("assets/RightPanel.jpg").convert()  # opaque JPG: display format for fast per-frame blits
                    self.right_panel_image = pygame.transform.scale(
                        right_panel_original,
                        (UIConstants.SIDEBAR_WIDTH, sidebar_height)
                    )
                except pygame.error:
                    pass  # Keep old scaled version if reload fails
            
            # Separator image
            separator_height = BOTTOM_UI_HEIGHT  # Full panel height (no margins)
            if self.separator_image:
                try:
                    separator_original = pygame.image.load("assets/Separator1.png").convert_alpha()
                    original_width = separator_original.get_width()
                    original_height = separator_original.get_height()

                    # Squish horizontally to make it thinner while keeping full height
                    target_width = 30

                    # Scale to target dimensions (squish width, match panel height)
                    self.separator_image = pygame.transform.smoothscale(
                        separator_original,
                        (target_width, separator_height)
                    )
                    self.separator_width = target_width
                    # Update helpers with new separator
                    self.helpers.update_separator(self.separator_image, self.separator_width)
                except pygame.error:
                    pass  # Keep old scaled version if reload fails
            
            # Reset camera to default position
            self.camera.reset_camera()
            self.camera_offset = self.camera.offset
            self.camera_zoom = self.camera.zoom
            
            # Clear selections (prevents off-screen selections)
            self.selected_plot = None
            self.selected_barracks = None
            self.selected_keep = None
            if hasattr(self.game_state, 'selected_army'):
                self.game_state.selected_army = None
            
            # Update UIConstants.SIDEBAR_HEIGHT (matches map height)
            UIConstants.SIDEBAR_HEIGHT = new_layout['sidebar_height']
            
            # Update current settings
            self.current_resolution = (actual_width, actual_height)
            self.is_fullscreen = fullscreen
            
            logger.info("=" * 60)
            logger.info("[OK] DISPLAY SETTINGS APPLIED")
            logger.info("=" * 60)
            logger.info(f"Mode: {'FULLSCREEN' if fullscreen else 'WINDOWED'}")
            logger.info(f"Requested: {width}x{height}")
            logger.info(f"Actual:    {actual_width}x{actual_height}")
            if fullscreen and (actual_width != width or actual_height != height):
                logger.info(f"Note: Using native resolution instead of requested")
            logger.info(f"")
            logger.info(f"UI Layout:")
            logger.info(f"   Top Panel:    {TOP_PANEL_HEIGHT}px")
            logger.info(f"   Map Area:     {MAP_HEIGHT}px")
            logger.info(f"   Bottom UI:    {BOTTOM_UI_HEIGHT}px")
            logger.info(f"   Bottom Y Pos: {BOTTOM_UI_Y}px")
            logger.info(f"   Total:        {TOP_PANEL_HEIGHT + MAP_HEIGHT + BOTTOM_UI_HEIGHT}px (Window: {WINDOW_HEIGHT}px)")
            
            # Verify layout
            total_height = TOP_PANEL_HEIGHT + MAP_HEIGHT + BOTTOM_UI_HEIGHT
            if total_height != WINDOW_HEIGHT:
                logger.warning(f"WARNING:  WARNING: Layout mismatch! Difference: {WINDOW_HEIGHT - total_height}px")
            else:
                logger.info(f"[OK]Layout verification: Perfect fit!")
            
            logger.info(f"")
            logger.info(f"Map Scaling:")
            logger.info(f"   Scale factor: {self.scale_factor:.2f}")
            logger.info(f"   Map size:     {self.map_width}x{self.map_height}")
            
            # Verify actual window size
            actual_size = self.screen.get_size()
            logger.info(f"")
            logger.info(f"Window Size:")
            logger.info(f"   Requested: {actual_width}x{actual_height}")
            logger.info(f"   Actual:    {actual_size[0]}x{actual_size[1]}")
            if actual_size != (actual_width, actual_height):
                logger.warning(f"WARNING:  WARNING: Size mismatch!")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to apply display settings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def draw_feedback_button(self, rect, base_color, button_type, button_id,
                            text=None, text_color=WHITE, font=None,
                            border_color=BLACK, border_width=2):
        """
        Draw a button with automatic hover/click feedback.
        
        Phase 1: Created to eliminate repetitive button rendering code.
        This is a reusable button renderer that handles:
        - Hover detection and brightening (+20%)
        - Click flash detection and brightening (+40%)
        - Background fill
        - Border drawing
        - Optional centered text
        
        Args:
            rect: pygame.Rect for button bounds
            base_color: RGB tuple for normal button color
            button_type: String identifier for click tracking (e.g., 'bottom_button')
            button_id: Unique ID within type (e.g., 'end_turn')
            text: Optional text to center in button
            text_color: Color for text (default WHITE)
            font: pygame.Font to use (default self.font)
            border_color: Color for border (default BLACK)
            border_width: Width of border in pixels (default 2)
        
        Returns:
            tuple: (final_color, is_hovering, is_clicking) for additional rendering
        
        Example:
            # Simple button
            self.draw_feedback_button(rect, (100, 150, 100), 
                                      'bottom_button', 'end_turn',
                                      text="End Turn")
            
            # Button with custom styling
            color, hovering, clicking = self.draw_feedback_button(
                rect, (200, 100, 100), 'demolish', 'barracks',
                text="Demolish", text_color=WHITE, border_width=3
            )
        
        Performance:
            O(1) - collision check, color modulation, rect draw, optional text
            ~0.00002ms per call, negligible impact
        """
        # Check hover
        is_hovering = rect.collidepoint(self.mouse_pos)
        
        # Check click flash
        is_clicking = (self.clicked_element and 
                      self.clicked_element[0] == button_type and 
                      self.clicked_element[1] == button_id)
        
        # Apply visual feedback
        final_color = base_color
        if is_clicking:
            final_color = brighten_color(base_color, 0.4)
        elif is_hovering:
            final_color = lighten_color(base_color, 0.2)
        
        # Draw background
        pygame.draw.rect(self.screen, final_color, rect)
        
        # Draw border
        if border_width > 0:
            pygame.draw.rect(self.screen, border_color, rect, border_width)
        
        # PERFORMANCE: Use text cache to avoid font.render() every frame for static button labels
        if text:
            if font is None:
                font = self.font
            text_surf = self._get_cached_text(text, font, text_color)
            text_rect = text_surf.get_rect(center=rect.center)
            self.screen.blit(text_surf, text_rect)

        return (final_color, is_hovering, is_clicking)

    def draw_tooltip_box(self, pos, lines, max_width=None, bg_color=(255, 255, 220),
                        border_color=BLACK, padding=8, line_spacing=2, use_transparency=False):
        """
        Draw a tooltip box with multiple lines of text.
        
        Phase 2: Created to eliminate repetitive tooltip rendering code.
        Enhanced to support custom fonts, colors, and transparency.
        
        This is a reusable tooltip renderer that handles:
        - Multi-line text rendering
        - Custom fonts per line (normal, small, large)
        - Automatic size calculation
        - Background and border drawing
        - Per-line text colors
        - Smart positioning (stays on screen)
        - Optional transparency (for advanced tooltips)
        
        Args:
            pos: (x, y) tuple for tooltip position (top-left corner)
            lines: List of strings, (text, color) tuples, or ("font", text, color) tuples
                   - String: Uses self.small_font and BLACK
                   - (text, color): Uses self.small_font with custom color
                   - ("normal", text, color): Uses self.font
                   - ("small", text, color): Uses self.small_font
                   - ("large", text, color): Uses self.large_font
            max_width: Optional max width in pixels
            bg_color: RGB or RGBA tuple for background
            border_color: RGB or RGBA tuple for border
            padding: Pixels of padding around text (default 8)
            line_spacing: Pixels between lines (default 2)
            use_transparency: If True, creates semi-transparent surface
        
        Returns:
            pygame.Rect: The rect of the drawn tooltip
        
        Example:
            # Simple tooltip
            self.draw_tooltip_box((x, y), [
                "Territory Name",
                ("Owner: Player 1", owner_color),
                "Armies: 5"
            ])
            
            # Advanced tooltip with custom fonts
            self.draw_tooltip_box((x, y), [
                ("normal", "Territory Name", BLACK),
                ("normal", f"Owner: Player {owner}", owner_color),
                ("small", "Buildings: 3 Farms", GREEN)
            ], use_transparency=True)
        
        Performance:
            O(n) where n = number of lines
            ~0.0001ms per tooltip
        """
        # Normalize lines to (font, text, color) tuples or lists of fragments
        normalized_lines = []
        for line in lines:
            if isinstance(line, list):
                # List of fragments for mixed-style line: [(font, text, color), ...]
                normalized_lines.append(line)
            elif isinstance(line, tuple):
                if len(line) == 3 and isinstance(line[0], str) and line[0] in ['normal', 'small', 'large', 'small_bold', 'small_italic', 'normal_bold']:
                    # Already (font_size, text, color) format - wrap in list for consistency
                    normalized_lines.append([line])
                elif len(line) == 2:
                    # (text, color) format - use small font
                    normalized_lines.append([("small", line[0], line[1])])
                else:
                    # Unknown tuple format - treat as text
                    normalized_lines.append([("small", str(line), BLACK)])
            else:
                # Just text string - use small font and BLACK
                normalized_lines.append([("small", str(line), BLACK)])

        # Render all lines and calculate required size
        # Each line can have multiple fragments with different styles
        rendered_lines = []
        max_line_width = 0
        total_height = 0

        for line_fragments in normalized_lines:
            # Render each fragment in the line
            line_surfaces = []
            line_width = 0
            line_height = 0

            for font_size, text, color in line_fragments:
                # Select appropriate font
                if font_size == "large":
                    font = self.large_font
                elif font_size == "normal":
                    font = self.font
                elif font_size == "normal_bold":
                    font = self.font_bold
                elif font_size == "small_bold":
                    font = self.small_font_bold
                elif font_size == "small_italic":
                    font = self.small_font_italic
                else:  # "small" or default
                    font = self.small_font

                surf = font.render(text, True, color)
                line_surfaces.append(surf)
                line_width += surf.get_width()
                line_height = max(line_height, surf.get_height())

            rendered_lines.append((line_surfaces, line_width, line_height))
            max_line_width = max(max_line_width, line_width)
            total_height += line_height + line_spacing
        
        # Remove last line spacing
        if rendered_lines:
            total_height -= line_spacing
        
        # Apply max width if specified
        if max_width:
            max_line_width = min(max_line_width, max_width)
        
        # Calculate tooltip dimensions
        tooltip_width = max_line_width + padding * 2
        tooltip_height = total_height + padding * 2
        
        # Smart positioning to keep tooltip on screen
        tooltip_x, tooltip_y = pos

        # Adjust if tooltip goes off right edge
        if tooltip_x + tooltip_width > WINDOW_WIDTH:
            tooltip_x = WINDOW_WIDTH - tooltip_width - 5

        # Adjust if tooltip goes off bottom edge
        # If mouse is above bottom UI panel, keep tooltip above it to prevent overlap
        # If mouse is in bottom UI area, allow tooltip to extend to window bottom
        if pos[1] < BOTTOM_UI_Y:
            # Mouse above bottom UI - keep tooltip above bottom panel
            if tooltip_y + tooltip_height > BOTTOM_UI_Y - 5:
                tooltip_y = BOTTOM_UI_Y - tooltip_height - 10
        else:
            # Mouse in bottom UI - allow tooltip to go to window bottom
            if tooltip_y + tooltip_height > WINDOW_HEIGHT:
                tooltip_y = WINDOW_HEIGHT - tooltip_height - 10

        # Ensure tooltip doesn't go off left/top edges
        tooltip_x = max(5, tooltip_x)
        tooltip_y = max(5, tooltip_y)
        
        # Create tooltip rect
        tooltip_rect = pygame.Rect(tooltip_x, tooltip_y, tooltip_width, tooltip_height)
        
        # Draw with transparency if requested
        if use_transparency:
            # MP2 fix: Reuse cached tooltip surface when size matches to avoid per-frame allocation
            tooltip_size = (tooltip_width, tooltip_height)
            if not hasattr(self, '_cached_tooltip_surface') or self._cached_tooltip_surface is None or self._cached_tooltip_surface.get_size() != tooltip_size:
                self._cached_tooltip_surface = pygame.Surface(tooltip_size, pygame.SRCALPHA)
            else:
                self._cached_tooltip_surface.fill((0, 0, 0, 0))
            tooltip_surface = self._cached_tooltip_surface
            # Background with alpha
            bg_alpha = bg_color + (240,) if len(bg_color) == 3 else bg_color
            pygame.draw.rect(tooltip_surface, bg_alpha, (0, 0, tooltip_width, tooltip_height))
            # Border with alpha
            border_alpha = border_color + (255,) if len(border_color) == 3 else border_color
            pygame.draw.rect(tooltip_surface, border_alpha, (0, 0, tooltip_width, tooltip_height), 2)
            self.screen.blit(tooltip_surface, (tooltip_x, tooltip_y))
        else:
            # Draw opaque background
            pygame.draw.rect(self.screen, bg_color, tooltip_rect)
            pygame.draw.rect(self.screen, border_color, tooltip_rect, 2)
        
        # Draw text lines (each line can have multiple fragments)
        y = tooltip_y + padding
        for line_surfaces, line_width, line_height in rendered_lines:
            x = tooltip_x + padding
            for surf in line_surfaces:
                self.screen.blit(surf, (x, y))
                x += surf.get_width()
            y += line_height + line_spacing
        
        return tooltip_rect
    
    def clamp_camera_to_bounds(self):
        """
        Clamp camera offset to keep view within map bounds.
        
        Wrapper that delegates to camera handler and syncs state.
        """
        self.camera.clamp_to_bounds()
        # Sync state back
        self.camera_offset = self.camera.offset
        self.camera_zoom = self.camera.zoom
    
    # ========================================
    # PHASE 1D: HELPER METHODS
    # ========================================
    
    def draw_letter_button(self, rect, letter, bg_color, letter_color=WHITE, border_color=BLACK, border_width=2, 
                           button_type=None, button_id=None):
        """
        Draw a square button with a centered letter (Phase 1D helper).
        
        Now supports hover and click visual feedback! (Phase 2)
        
        This helper eliminates code duplication for training and building buttons.
        The pattern appears 10+ times in the codebase.
        
        Args:
            rect: pygame.Rect for button position and size
            letter: Single character to display (e.g., 'S', 'F', 'B')
            bg_color: Background color (RGB or RGBA tuple)
            letter_color: Letter color (default: WHITE)
            border_color: Border color (default: BLACK)
            border_width: Border width in pixels (default: 2)
            button_type: Optional - type for hover/click feedback (e.g., 'training')
            button_id: Optional - identifier for hover/click feedback (e.g., 'Swordsman')
        
        Example:
            button_rect = pygame.Rect(x, y, 60, 60)
            self.draw_letter_button(button_rect, 'S', (100, 100, 150), 
                                   button_type='training', button_id='Swordsman')
        
        Phase 2 Enhancement:
            If button_type and button_id are provided, applies hover/click feedback
            automatically. Button lightens 20% on hover, brightens 40% on click.
        """
        # Apply hover/click feedback if identifiers provided
        final_bg_color = bg_color
        if button_type and button_id:
            # Check for hover
            is_hovering = rect.collidepoint(self.mouse_pos)
            
            # Check for click flash
            is_clicking = (self.clicked_element and 
                          self.clicked_element[0] == button_type and 
                          self.clicked_element[1] == button_id)
            
            # Apply visual feedback
            if is_clicking:
                final_bg_color = brighten_color(bg_color, 0.4)  # Bright flash on click
            elif is_hovering:
                final_bg_color = lighten_color(bg_color, 0.2)  # Subtle lightening on hover
        
        # Draw filled background
        pygame.draw.rect(self.screen, final_bg_color, rect)
        
        # Draw border
        pygame.draw.rect(self.screen, border_color, rect, border_width)
        
        # Draw centered letter
        letter_surf = self._get_cached_text(letter, self.large_font, letter_color)
        letter_rect = letter_surf.get_rect(center=rect.center)
        self.screen.blit(letter_surf, letter_rect)
    
    def draw_circle_badge(self, pos, text, bg_color=WHITE, border_color=None, text_color=BLACK, radius=None):
        """
        Draw a circular badge with centered text (Phase 1D helper).
        
        This helper eliminates code duplication for army count badges,
        order count badges, and other circular UI elements.
        
        Args:
            pos: (x, y) tuple for badge center position
            text: Text to display (will be converted to string)
            bg_color: Background color (default: WHITE)
            border_color: Border color (default: same as bg_color if None)
            text_color: Text color (default: BLACK)
            radius: Badge radius (default: BADGE_RADIUS constant)
        
        Example:
            self.draw_circle_badge((100, 100), 5, border_color=RED)
        """
        if border_color is None:
            border_color = bg_color
        if radius is None:
            radius = BADGE_RADIUS
        
        # Draw filled circle
        pygame.draw.circle(self.screen, bg_color, pos, radius)
        
        # Draw border circle
        pygame.draw.circle(self.screen, border_color, pos, radius, 2)
        
        # Draw centered text (cached to avoid per-frame font.render)
        text_surf = self._get_cached_text(str(text), self.small_font, text_color)
        text_rect = text_surf.get_rect(center=pos)
        self.screen.blit(text_surf, text_rect)
    
    def draw_separator(self, x_position, bottom_ui_y, bottom_ui_height):
        """
        Draw a vertical separator in the bottom UI panel.
        
        This is a wrapper method that delegates to the helpers class.
        
        Args:
            x_position: X coordinate for separator (centered on this position)
            bottom_ui_y: Y coordinate where bottom panel starts
            bottom_ui_height: Height of the bottom panel
        """
        self.helpers.draw_separator(x_position, bottom_ui_y, bottom_ui_height)
    
    def update_button_hover(self, current_hover, hover_type):
        """
        Update hover tracking for a specific button type (Phase 1D helper).
        
        Uses type-based ownership pattern to prevent interference between
        different hover systems (building, training, plot, map_building, map_training).
        
        This pattern was repeated 5+ times in the codebase and is now centralized.
        
        Type-Based Ownership:
            Each hover system only updates hover state when dealing with its own type.
            This prevents one system from accidentally clearing another system's hover.
        
        Args:
            current_hover: (type, key) tuple of current hover, or None
            hover_type: String identifying this hover system
                       (e.g., 'building', 'training', 'map_building')
        
        Side Effects:
            Updates self.hover_target_button
            Updates self.show_tooltip_button
            Updates self.hover_start_time_button
        
        Example:
            # In building icon drawing code:
            current_hover = ('building', building_name) if hovering else None
            self.update_button_hover(current_hover, 'building')
        """
        if current_hover != self.hover_target_button:
            if current_hover and current_hover[0] == hover_type:
                # Moving TO this button type - take control
                self.hover_target_button = current_hover
                self.show_tooltip_button = None  # Reset shown tooltip
                self.hover_start_time_button = pygame.time.get_ticks()  # Start timer
            elif self.hover_target_button and self.hover_target_button[0] == hover_type:
                # Moving AWAY from this button type - release control
                self.hover_target_button = None
                self.show_tooltip_button = None
                self.hover_start_time_button = None
            # Otherwise: Don't touch hover_target_button - it's for another system
    
    # ========================================
    
    def draw_silence_fog_overlay(self):
        """
        Draw a dark red fog overlay on the entire map when silence is active.

        This visual effect indicates when Vow of Silence is active.
        ALL players see the fog when ANY player has active silence effects.
        Features:
        - Gradual fade-in from transparent to full strength over 1.5 seconds
        - Continuous shimmering effect while active (pulsing alpha)
        """
        # Check if ANY player is silenced (Vow of Silence is active)
        silence_active = False
        for player_index in range(self.game_state.num_players):
            if self.game_state.hero_silence_status.get(player_index, 0) > 0:
                silence_active = True
                break

        if not silence_active:
            return

        # Get current time for animations
        current_time = pygame.time.get_ticks()

        # Calculate fade-in progress
        # Animation lasts 1.5 seconds (1500ms) - gradual fade from 0 to full strength
        fade_duration = 1500
        if self.game_state.silence_activation_time:
            elapsed = current_time - self.game_state.silence_activation_time
            fade_progress = min(1.0, elapsed / fade_duration)
        else:
            fade_progress = 1.0  # Already fully visible

        # Shimmer effect - oscillate alpha slightly over time
        # Cycle every 2 seconds (2000ms)
        shimmer_cycle = 2000
        shimmer_offset = math.sin((current_time % shimmer_cycle) / shimmer_cycle * 2 * math.pi) * 15

        # Base alpha target is 70, but we fade in from 0
        target_alpha = 70
        current_alpha = (target_alpha + shimmer_offset) * fade_progress

        # PERFORMANCE: Reuse cached fog surface instead of allocating 5.44MB SRCALPHA every frame
        if self._cached_silence_fog is None or self._cached_silence_fog.get_size() != (WINDOW_WIDTH, MAP_HEIGHT):
            self._cached_silence_fog = pygame.Surface((WINDOW_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
        self._cached_silence_fog.fill((120, 0, 0, int(current_alpha)))

        # Blit the fog over the map area (below top panel)
        self.screen.blit(self._cached_silence_fog, (0, TOP_PANEL_HEIGHT))

    def _point_in_polygon(self, x, y, polygon):
        """
        Check if a point is inside a polygon using ray casting algorithm.

        Args:
            x, y: Point coordinates
            polygon: List of (x, y) tuples representing polygon vertices

        Returns:
            bool: True if point is inside polygon
        """
        inside = False
        n = len(polygon)
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    # Additional particle colors for active ability effects (beyond passive auras)
    _EXTRA_PARTICLE_COLORS = {
        'embargo': (160, 20, 20),  # Dark red — matches MapRenderer.EMBARGO_COLOR
    }

    def _build_particle_caches(self):
        """
        Pre-build PNG particle surface caches for all aura and ability effects.

        For each effect, pre-scales the white particle PNG to the effect's color
        at every needed (diameter, alpha) combination. Eliminates runtime allocations.

        Cache structure: self._particle_caches[effect_key][(diameter, alpha)] -> Surface
        Per effect: 15 sizes x 16 alpha levels = 240 surfaces (~1MB total per effect).
        """
        self._particle_caches = {}
        if self._haste_particle_base is None:
            return

        # Collect all colors to cache: passive auras + active ability effects
        all_colors = {key: config['color'] for key, config in self._bubble_configs.items()}
        all_colors.update(self._EXTRA_PARTICLE_COLORS)

        for effect_key, color in all_colors.items():
            cache = {}

            # Screen diameters: world radii 1.5-3.9 * zoom 1.65-4.0 * 2x PNG scale = ~6 to ~32
            for diameter in range(6, 34, 2):  # Even diameters: 6, 8, ..., 32
                # Scale base PNG to target diameter, then tint to ability color
                scaled = pygame.transform.smoothscale(self._haste_particle_base, (diameter, diameter))
                scaled.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)

                # Pre-generate a surface for each quantized alpha level
                for alpha in range(0, 160, 10):  # 0, 10, 20, ..., 150
                    alpha_surface = scaled.copy()
                    alpha_surface.set_alpha(alpha)
                    cache[(diameter, alpha)] = alpha_surface

            self._particle_caches[effect_key] = cache

    def _get_bubble_surface(self, radius, base_color, alpha):
        """
        Get or create a cached bubble surface for the given parameters.

        PERFORMANCE: This avoids creating new surfaces every frame by caching
        bubble surfaces by their visual parameters. Surfaces are reused when
        the same radius/color/alpha combination is needed.

        Args:
            radius (int): Bubble radius in pixels
            base_color (tuple): RGB color tuple (r, g, b)
            alpha (int): Alpha value 0-255

        Returns:
            pygame.Surface: Cached or newly created bubble surface
        """
        # Quantize alpha to reduce cache entries (bucket to nearest 10)
        quantized_alpha = (alpha // 10) * 10
        cache_key = (radius, base_color, quantized_alpha)

        if cache_key not in self._bubble_surface_cache:
            # Limit cache size by removing oldest entries if needed
            if len(self._bubble_surface_cache) >= self._bubble_surface_cache_max_size:
                # Remove first (oldest) entry
                oldest_key = next(iter(self._bubble_surface_cache))
                del self._bubble_surface_cache[oldest_key]

            # Create new surface
            surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)

            # Draw filled circle with alpha
            color_with_alpha = base_color + (quantized_alpha,)
            pygame.draw.circle(surface, color_with_alpha, (radius, radius), radius)

            # Draw border for better visibility
            border_alpha = min(255, quantized_alpha + 50)
            border_color = base_color + (border_alpha,)
            pygame.draw.circle(surface, border_color, (radius, radius), radius, 1)

            self._bubble_surface_cache[cache_key] = surface

        return self._bubble_surface_cache[cache_key]

    def _get_hero_overlay(self, size, overlay_type):
        """
        Get or create a cached overlay surface for hero UI effects.

        PERFORMANCE: Hero ability icons use overlay surfaces for disabled/hover/click
        effects. Creating these surfaces every frame causes significant FPS loss.
        This caches overlays by size and type for reuse.

        Args:
            size (int): Square size of the overlay in pixels
            overlay_type (str): Type of overlay - 'dark', 'bright', or 'light'

        Returns:
            pygame.Surface: Cached overlay surface (do NOT modify - use .copy() if needed)
        """
        if size not in self._hero_overlay_cache:
            self._hero_overlay_cache[size] = {}

        cache = self._hero_overlay_cache[size]

        if overlay_type not in cache:
            surface = pygame.Surface((size, size), pygame.SRCALPHA)

            if overlay_type == 'dark':
                surface.fill((0, 0, 0, 150))  # Dark semi-transparent for disabled
            elif overlay_type == 'bright':
                surface.fill((100, 100, 100, 100))  # Bright for clicking
            elif overlay_type == 'light':
                surface.fill((50, 50, 50, 50))  # Light for hovering

            cache[overlay_type] = surface

        return cache[overlay_type]

    def _get_cached_ui_icon(self, icon_surface, icon_id, size):
        """
        Get or create a cached scaled icon for UI panels.

        PERFORMANCE OPTIMIZATION: Fixes 50% FPS drop when bottom/right panels open.
        Bottom panel (building/unit icons) and hero abilities were causing 80→40 FPS
        by smoothscaling icons every frame. This caches scaled icons for reuse.

        Args:
            icon_surface: Original pygame.Surface of the icon
            icon_id: Unique identifier (e.g., 'Keep', 'Infantry', 'ability_slash')
            size: Target square size in pixels

        Returns:
            pygame.Surface: Cached scaled icon
        """
        cache_key = (icon_id, size)

        if cache_key not in self._ui_icon_cache:
            # Smoothscale is expensive (~5-10ms per call)
            # Only do it once per unique (icon, size) combination
            self._ui_icon_cache[cache_key] = pygame.transform.smoothscale(
                icon_surface, (size, size))

        return self._ui_icon_cache[cache_key]

    def _get_cached_tech_border(self, border_surface, width, height):
        """
        Get or create a cached scaled technology border frame.

        PERFORMANCE OPTIMIZATION: Technology tree renders 21 buttons with borders.
        Each border was smoothscaled every frame (21× smoothscale/frame = 30% FPS drop).

        Args:
            border_surface: Original border icon surface
            width: Target width
            height: Target height

        Returns:
            pygame.Surface: Cached scaled border
        """
        cache_key = (width, height)

        if cache_key not in self._tech_border_cache:
            self._tech_border_cache[cache_key] = pygame.transform.smoothscale(
                border_surface, (width, height))

        return self._tech_border_cache[cache_key]

    def _get_cached_scaled_surface(self, surface, surface_id, width, height):
        """
        Get or create a cached scaled surface for any icon/border.

        C2/M17 fix: General-purpose scaling cache that supports non-square sizes.
        Eliminates per-frame smoothscale calls for castle icons, building icons,
        unit icons, and border frames.

        Args:
            surface: Original pygame.Surface
            surface_id: Unique identifier (e.g., 'castle_upgrade', 'icon_border')
            width: Target width
            height: Target height

        Returns:
            pygame.Surface: Cached scaled surface (do NOT modify - use .copy() if overlays needed)
        """
        cache_key = (surface_id, width, height)
        if cache_key not in self._ui_icon_cache:
            self._ui_icon_cache[cache_key] = pygame.transform.smoothscale(
                surface, (width, height))
        return self._ui_icon_cache[cache_key]

    def _apply_icon_overlay(self, icon_surface, is_clicking, is_hovering,
                            enabled=True, disabled_tint=(255, 100, 100, 128)):
        """
        Apply hover/click/disabled overlays to a scaled icon.

        C2/M17 fix: Shared helper for icon tinting. Only copies the surface when
        overlays are actually needed (hover/click/disabled state).

        Args:
            icon_surface: Base scaled icon (from cache)
            is_clicking: Whether button is being clicked
            is_hovering: Whether button is being hovered
            enabled: Whether button is enabled (False = apply disabled_tint)
            disabled_tint: RGBA color for disabled state (default: red)

        Returns:
            pygame.Surface: Icon with overlays applied (or original if no overlay needed)
        """
        needs_overlay = not enabled or is_clicking or is_hovering
        if not needs_overlay:
            return icon_surface

        # Copy only when we need to modify
        result = icon_surface.copy()
        w, h = result.get_size()

        if not enabled:
            tint_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            tint_overlay.fill(disabled_tint)
            result.blit(tint_overlay, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        if is_clicking:
            bright_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            bright_overlay.fill((100, 100, 100, 100))
            result.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif is_hovering:
            light_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            light_overlay.fill((50, 50, 50, 50))
            result.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        return result

    def _get_building_effect_text(self, effect, value):
        """Return human-readable description string for a building effect (Phase 2G dedup).

        Used in both existing-building and under-construction building UI panels.
        """
        if effect == 'income':
            return f"- Generates {value} Gold per turn."
        elif effect == 'defense':
            return f"- Provides +{value} defense bonus. (Limit 1 per territory)"
        elif effect == 'multiplier':
            return f"- Multiplies territory income x{value}."
        elif effect == 'recruitment':
            return "- Allows training of military units."
        elif effect == 'training':
            return f"- Grants {value} XP per turn to units in territory. (Limit 1 per territory)"
        else:
            return f"- {str(effect)}"

    def _is_tutorial_active(self):
        """Check if a tutorial mission is currently running.

        Replaces the repeated 3-condition guard: hasattr + truthy + .active.
        """
        return (self.tutorial_mission
                and self.tutorial_mission.active)

    def _is_tutorial_blocking(self, action):
        """Check if the tutorial mission is active and blocking a given action.

        Returns True if the action is blocked, False if allowed or no tutorial is active.
        """
        return (self._is_tutorial_active()
                and not self.tutorial_mission.is_action_allowed(action))

    def show_action_error(self, code=None, message=None, **fmt):
        """
        The single "action refused" feedback: denial sound + red notification (toast)
        in the top-left corner of the map.

        Args:
            code: key in config/action_error_messages.ACTION_ERROR_MESSAGES — all
                player-facing texts live there so they can be edited in one place
            message: literal text instead of a code (only for texts that don't come
                from the table yet)
            **fmt: values for the message's {placeholders}
        """
        from config.action_error_messages import format_action_error
        msg = message if message is not None else format_action_error(code, **fmt)

        # Audio feedback (non-stacking)
        from global_sound import play_action_denied
        play_action_denied()

        # Visual feedback — floating notification in the chat notification area
        if self.chat_notification_effect:
            self.chat_notification_effect.add_system_notification(msg)

    def _show_hero_death_notifications(self):
        """
        Drain game_state.hero_death_events and tell the local player about their own
        heroes dying: "Our Hero, X, has been slain in Y!" (text: 'hero_slain' in
        config/action_error_messages.py).

        Same red toast as action errors but WITHOUT the denial sound — it's news, not
        a refused action. Other players' hero deaths are dropped (the Action Log still
        records every death).
        """
        events = getattr(self.game_state, 'hero_death_events', None)
        if not events:
            return
        # Swap the list out first so a death recorded while we iterate isn't lost
        self.game_state.hero_death_events = []

        local_player = self.get_local_player()
        from config.action_error_messages import format_action_error
        for event in events:
            # Format: (owner, hero_type, territory) — index access survives format changes
            if event[0] != local_player or not self.chat_notification_effect:
                continue
            self.chat_notification_effect.add_system_notification(
                format_action_error('hero_slain', hero=event[1], territory=event[2]))

    def _show_action_failure_feedback(self):
        """Show the action error recorded by the last game_state action method.

        Reads game_state.last_action_error (+ last_action_error_args for the
        message's {placeholders}), set by start_training, start_construction, etc.
        Does nothing when no code was recorded (a refusal without a player-facing
        message, e.g. a tutorial block whose button is already greyed).
        """
        error = self.game_state.last_action_error
        if error is None:
            return
        fmt = getattr(self.game_state, 'last_action_error_args', None) or {}
        # Clear after reading
        self.game_state.last_action_error = None
        self.game_state.last_action_error_args = None

        self.show_action_error(error, **fmt)

    def _is_sim_resolving(self):
        """True while simultaneous mode resolves battles/alliance markers (no new actions)."""
        return self.sim_state is not None and self.sim_state.sim_phase == 'resolving'

    def _try_start_construction(self, territory, plot_index, building_name):
        """
        Shared build path for the map quick-icons, the bottom-panel buttons and the
        keyboard shortcuts. Each used to carry its own copy with different sync rules
        (the bottom panel never queued a simultaneous-mode order, the keyboard never
        synced at all), so the same action behaved differently per input.

        Runs the build locally, then syncs it: simultaneous mode queues a sim order,
        sequential multiplayer sends BUILDING_ORDER. On refusal it shows the failure
        feedback. UI deselection stays with the caller.

        Returns:
            bool: True if construction started
        """
        # No new actions while simultaneous mode resolves battles (the map icons already
        # enforced this; the bottom panel and keyboard did not)
        if self._is_sim_resolving():
            return False

        if not self.game_state.start_construction(territory, plot_index, building_name):
            self._show_action_failure_feedback()
            return False

        if self.sim_state is not None:
            # Executed locally for immediate feedback; the executor skips it for the
            # clicking player (sim_state.click_executed_player) but syncs it to others
            self.sim_state.add_order(self.get_local_player(), {
                'type': 'build',
                'player_id': self.game_state.current_player,
                'territory': territory,
                'plot_index': plot_index,
                'building_type': building_name
            })
            logger.debug(f"[SIM] Queued build order: {building_name} in {territory}")
        elif self.multiplayer_mode:
            self._send_action_to_remote(MessageType.BUILDING_ORDER, {
                'territory': territory,
                'plot_index': plot_index,
                'building_type': building_name,
                'player_index': self.local_player_index  # 4-player support
            })
        return True

    def _try_start_training(self, territory, barracks_plot_index, unit_type):
        """
        Shared unit-training path for the map quick-icons, the bottom-panel buttons and
        the keyboard shortcuts (same reasons as _try_start_construction: the map icon
        never sent TRAINING_ORDER in sequential multiplayer, the bottom panel never queued
        a simultaneous-mode order, and the keyboard did neither).

        Returns:
            bool: True if training started
        """
        if self._is_sim_resolving():
            return False

        if not self.game_state.start_training(territory, barracks_plot_index, unit_type):
            self._show_action_failure_feedback()
            return False

        if self.sim_state is not None:
            self.sim_state.add_order(self.get_local_player(), {
                'type': 'train',
                'player_id': self.game_state.current_player,
                'territory': territory,
                'barracks_plot': barracks_plot_index,
                'unit_type': unit_type
            })
            logger.debug(f"[SIM] Queued train order: {unit_type} in {territory}")
        elif self.multiplayer_mode:
            # Sync fix: remote players must see the training queue in sequential mode
            self._send_action_to_remote(MessageType.TRAINING_ORDER, {
                'territory': territory,
                'barracks_plot': barracks_plot_index,
                'unit_type': unit_type,
                'player_index': self.game_state.current_player
            })
        self.clear_button_tooltip()
        return True

    def _get_territory_preview(self, territory, width, height):
        """Get cached territory preview image, loading from disk on first access.
        Returns pygame.Surface scaled to (width, height), or None if no image exists."""
        cache_key = (territory, width, height)
        if cache_key in self._territory_preview_cache:
            return self._territory_preview_cache[cache_key]

        # Try to load preview image from the current map's territory_previews directory
        map_id = map_data.get_current_map_id()
        map_dir = map_data.get_map_directory(map_id) if map_id else 'maps/avareon'
        preview_path = os.path.join(map_dir, 'territory_previews', f'{territory}.png')
        try:
            img = pygame.image.load(preview_path).convert_alpha()
            scaled = pygame.transform.smoothscale(img, (width, height))
            self._territory_preview_cache[cache_key] = scaled
            return scaled
        except (pygame.error, FileNotFoundError):
            # No preview image available — caller will draw black rect
            self._territory_preview_cache[cache_key] = None
            return None

    def _get_cached_text(self, text, font, color):
        """
        Get or create a cached rendered text surface.

        PERFORMANCE: Font rendering (.render()) is expensive and often called
        with the same parameters every frame. This caches rendered text surfaces
        to avoid re-rendering static or frequently-used text.

        Args:
            text (str): Text to render
            font: Pygame font object (self.font, self.small_font, self.large_font)
            color (tuple): RGB or RGBA color tuple

        Returns:
            pygame.Surface: Cached rendered text surface
        """
        # Create cache key from font's identity and parameters
        cache_key = (text, id(font), color)

        if cache_key not in self._text_cache:
            # Limit cache size
            if len(self._text_cache) >= self._text_cache_max_size:
                # Remove oldest entry (first in dict)
                oldest_key = next(iter(self._text_cache))
                del self._text_cache[oldest_key]

            # Render and cache
            self._text_cache[cache_key] = font.render(text, True, color)

        return self._text_cache[cache_key]

    def _update_hero_bubbles(self, effect_key, delta_time):
        """
        Update hero ability bubble animations (Phase 2B: unified from 3 identical methods).

        Parameterized by effect_key ('defiance', 'haste', 'safe_haven') which maps to
        the config in self._bubble_configs for hero names, territory getter, rise speed, etc.
        """
        config = self._bubble_configs[effect_key]
        state = self._bubble_state[effect_key]

        # Only update if the matching hero is selected
        if self.selected_hero not in config['heroes']:
            state['bubbles'].clear()
            state['spawn_timer'] = 0
            return

        # Get affected territories via the configured getter method
        current_player = self.game_state.current_player
        territory_getter = getattr(self.game_state, config['territory_getter'])
        affected_territories = territory_getter(current_player)

        if not affected_territories:
            state['bubbles'].clear()
            return

        rise_speed = config['rise_speed']
        check_polygon = config['check_polygon']
        spawn_interval = config.get('spawn_interval', 0.1)
        spawn_chance = config.get('spawn_chance', 0.7)
        bubbles = state['bubbles']

        # Update existing bubbles
        bubbles_to_remove = []
        for bubble in bubbles:
            bubble['lifetime'] += delta_time
            bubble_duration = 1.0

            if bubble['lifetime'] >= bubble_duration:
                bubbles_to_remove.append(bubble)
            else:
                progress = bubble['lifetime'] / bubble_duration
                bubble['y'] -= rise_speed * delta_time

                # PERFORMANCE: Bounding box rejection before expensive polygon check
                territory = bubble['territory']
                bbox = self.map_renderer.territory_bounding_boxes.get(territory)
                if bbox:
                    min_x, min_y, max_x, max_y = bbox
                    if not (min_x <= bubble['x'] <= max_x and min_y <= bubble['y'] <= max_y):
                        bubbles_to_remove.append(bubble)
                        continue

                # Full polygon check only for effects that need it (defiance, haste)
                if check_polygon:
                    territory_polygon = self.scaled_polygons.get(territory)
                    if territory_polygon:
                        if not self._point_in_polygon(bubble['x'], bubble['y'], territory_polygon):
                            bubbles_to_remove.append(bubble)
                            continue

                bubble['alpha'] = int(150 * (1.0 - progress))
                bubble['radius'] = bubble['initial_radius'] * (1.0 + progress * 0.3)

        for bubble in bubbles_to_remove:
            bubbles.remove(bubble)

        # Spawn new bubbles at configurable interval
        state['spawn_timer'] += delta_time
        if state['spawn_timer'] >= spawn_interval:
            state['spawn_timer'] = 0

            for territory in affected_territories:
                territory_polygon = self.scaled_polygons.get(territory)
                if not territory_polygon:
                    continue

                bbox = self.map_renderer.territory_bounding_boxes.get(territory)
                if not bbox:
                    continue
                min_x, min_y, max_x, max_y = bbox

                for attempt in range(10):
                    x = random.uniform(min_x, max_x)
                    y = random.uniform(min_y, max_y)

                    if self._point_in_polygon(x, y, territory_polygon):
                        if random.random() < spawn_chance:
                            initial_radius = random.uniform(1.5, 3)
                            bubbles.append({
                                'territory': territory,
                                'x': x, 'y': y,
                                'radius': initial_radius,
                                'initial_radius': initial_radius,
                                'alpha': 150,
                                'lifetime': 0
                            })
                            break

    def _draw_hero_bubbles(self, effect_key):
        """
        Draw hero ability bubbles (Phase 2B: unified from 3 identical methods).

        Uses the color from self._bubble_configs[effect_key].
        """
        state = self._bubble_state[effect_key]
        if not state['bubbles']:
            return

        # PNG particle path for all auras (soft-glow particle instead of hard circles)
        particle_cache = self._particle_caches.get(effect_key)
        if particle_cache:
            self._draw_png_particles(state['bubbles'], particle_cache)
            return

        # Fallback: procedural circle path if PNG failed to load
        color = self._bubble_configs[effect_key]['color']

        for bubble in state['bubbles']:
            screen_x, screen_y = self.world_to_screen((bubble['x'], bubble['y']))

            if 0 <= screen_x <= WINDOW_WIDTH and TOP_PANEL_HEIGHT <= screen_y <= BOTTOM_UI_Y:  # H5 fix: use BOTTOM_UI_Y not MAP_HEIGHT
                scaled_radius = int(bubble['radius'] * self.camera_zoom)
                if scaled_radius < 1:
                    continue

                bubble_surface = self._get_bubble_surface(scaled_radius, color, bubble['alpha'])
                self.screen.blit(bubble_surface,
                               (screen_x - scaled_radius, screen_y - scaled_radius))

    def _draw_png_particles(self, bubbles, cache):
        """
        Draw aura bubbles using pre-cached PNG particle surfaces.

        Uses soft-glow Particle_Cropped.png pre-scaled and pre-tinted per ability
        at each (diameter, alpha) combination. Zero runtime allocations.
        """
        for bubble in bubbles:
            screen_x, screen_y = self.world_to_screen((bubble['x'], bubble['y']))
            if not (0 <= screen_x <= WINDOW_WIDTH and TOP_PANEL_HEIGHT <= screen_y <= BOTTOM_UI_Y):
                continue

            scaled_radius = int(bubble['radius'] * self.camera_zoom)
            if scaled_radius < 1:
                continue

            # Snap to nearest even diameter within cached range [6, 32] (2x scale for soft-glow)
            diameter = max(6, min(32, round(scaled_radius) * 4))
            diameter = diameter + (diameter % 2)  # Ensure even
            quantized_alpha = (int(bubble['alpha']) // 10) * 10

            surface = cache.get((diameter, quantized_alpha))
            if surface is None:
                continue

            # Blit centered on bubble position
            half = diameter // 2
            self.screen.blit(surface, (screen_x - half, screen_y - half))

    def draw_targeting_cursor(self):
        """
        Draw a targeting circle cursor when an ability is being targeted.
        Uses TargetCircle.png image, visible anywhere on screen.
        """
        mouse_pos = pygame.mouse.get_pos()

        # PERFORMANCE: Cache the targeting cursor image (load once)
        if self._cached_targeting_cursor is None:
            try:
                img = pygame.image.load('assets/TargetCircle.png').convert_alpha()
                # Scale to 120x120 targeting cursor size
                self._cached_targeting_cursor = pygame.transform.smoothscale(img, (120, 120))
            except pygame.error:
                # Fallback: draw a simple yellow circle if image missing
                self._cached_targeting_cursor = pygame.Surface((120, 120), pygame.SRCALPHA)
                pygame.draw.circle(self._cached_targeting_cursor, (255, 255, 0, 150), (60, 60), 60)
                pygame.draw.circle(self._cached_targeting_cursor, (255, 200, 0, 255), (60, 60), 60, 2)

        # Blit cached cursor centered on mouse position
        half_w = self._cached_targeting_cursor.get_width() // 2
        half_h = self._cached_targeting_cursor.get_height() // 2
        self.screen.blit(self._cached_targeting_cursor,
                       (mouse_pos[0] - half_w, mouse_pos[1] - half_h))

        # PERFORMANCE: Cache instruction text and background (static content)
        if self._cached_targeting_text is None:
            instruction_text = "Click territory to target | ESC or Right-Click to cancel"
            self._cached_targeting_text = self._get_cached_text(instruction_text, self.small_font, (255, 255, 255))
            bg_rect = self._cached_targeting_text.get_rect().inflate(10, 5)
            self._cached_targeting_text_bg = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(self._cached_targeting_text_bg, (0, 0, 0, 180),
                           self._cached_targeting_text_bg.get_rect(), border_radius=5)

        text_rect = self._cached_targeting_text.get_rect(center=(mouse_pos[0], mouse_pos[1] + half_h + 20))
        bg_rect = text_rect.inflate(10, 5)
        self.screen.blit(self._cached_targeting_text_bg, bg_rect)
        self.screen.blit(self._cached_targeting_text, text_rect)

    def _should_show_attack_cursor(self):
        """Check if attack cursor should be shown (hovering enemy/neutral with army selected)."""
        # Must have army composition UI open with units selected, and hovering a territory
        if not self.show_army_composition or not self.selected_army_units:
            return False
        if not self.hovered_territory:
            return False
        gs = self.game_state
        current = gs.current_player
        # Hovered territory must not be ours
        hover_owner = gs.territory_owners.get(self.hovered_territory, -1)
        if hover_owner == current:
            return False
        # Hovered territory must not be allied (skip check for neutral -1)
        if hover_owner >= 0 and gs.are_allies(current, hover_owner):
            return False
        return True

    # ========================================
    # PHASE 4: EXTRACTED PLOT RENDERING METHODS
    # ========================================
    
    def _select_army_garrison(self, army_result):
        """
        Open the army composition UI for a garrison that was just clicked.

        Extracted so the circle hit-test (PRIORITY 3) and the banner hit-test
        (PRIORITY 4.5) share one body instead of duplicating it.

        Args:
            army_result: (territory, player_index) from get_army_at_pos(), or a
                         bare territory name for backward compatibility.
        """
        # Unpack territory and player from result
        if isinstance(army_result, tuple):
            army_territory, army_player = army_result
        else:
            # Backward compatibility - shouldn't happen with new code
            army_territory = army_result
            army_player = self.game_state.current_player

        # Clear any stale plot/barracks selections that might interfere
        # (This fixes the bug where after battles, clicking armies doesn't work until you click a plot)
        self.selected_plot = None
        self.selected_barracks = None
        self.selected_keep = None
        self.selected_territory_info = None

        # Trigger click flash for visual feedback
        self.trigger_click_flash('army', army_territory)

        # Open army composition UI
        self.show_army_composition = True
        self.army_composition_territory = army_territory
        self.army_composition_player = army_player  # Track which player's garrison
        # Auto-select all ready units when opening composition UI
        player = army_player if army_player is not None else self.game_state.current_player
        garrison = self.game_state.territory_garrisons.get(army_territory, {}).get(player)
        if garrison:
            units = garrison.get('units', [])
            self.selected_army_units = [u['id'] for u in units if u['status'] == 'ready']
        else:
            self.selected_army_units = []

        # Play random army composition sound when opening the UI
        self.sound_manager.play_random('armycomp')

        # Deselect other UI elements
        self.game_state.deselect_army()
        self.selected_hero = None  # Deselect hero

    def handle_map_area_click(self, pos):
        """
        Handle mouse click on map area (Phase 2A extraction, Phase 2D camera update).
        
        Processes clicks on the map area only (not bottom UI). Uses a priority
        system where first match wins to prevent ambiguous clicks.
        
        NOW CAMERA-AWARE: Converts screen position to world position for accurate
        click detection with camera offset and zoom.
        
        Click Priority Order:
        1. Building icons (F/M/B/K/Q) - Quick-build from map (HIGHEST PRIORITY)
        2. Training icons (S/A/P/C) - Quick-train from Barracks
        3. Army composition circle - Opens army management UI
        4. Plot selection - Selects building plot
        5. Territory selection - Selects territory for info
        
        Building and training icons have TOP priority (checked before armies)
        to ensure icons are clickable even when overlapping with army circles.
        Clicks in the bottom UI area (pos[1] >= BOTTOM_UI_Y) are ignored here.
        
        Args:
            pos: (x, y) tuple of click position in SCREEN coordinates
        
        Returns:
            None (implicitly)
        
        Side Effects:
            - May change self.selected_plot
            - May change self.selected_barracks
            - May open army composition UI
            - May trigger building construction
            - May trigger unit training
            - May change selected territory
            - May clear tooltips
        
        Phase-Specific Behavior:
            - Setup phase: Territory selection for starting positions
            - Planning phase: Full functionality (all priorities active)
            - Execution phase: Limited interaction
        
        Phase Context:
            Extracted in Phase 2A to reduce run() method complexity.
            Updated in Phase 2D to work with camera offset and zoom.
            Updated to prioritize icons over armies for better UX.
        """
        # MULTIPLAYER: Block input if spectating
        if not self.is_local_player_active():
            return

        # Check if clicking on map area (not bottom UI)
        if pos[1] >= BOTTOM_UI_Y:
            # Click is in bottom UI - will handle separately
            return

        # PRIORITY 0: Check if in ability targeting mode
        if self.ability_targeting_active:
            # Convert screen position to world position
            world_pos = self.screen_to_world(pos)

            # Find which territory was clicked. Uses the shared lookup (skips territories a
            # mission hides) plus the same non-interactive filter as left/right-click —
            # the old private polygon loop let abilities hit hidden territories, even
            # succeeding (Aggressive Diplomacy on a hidden neutral territory).
            clicked_territory = self.get_territory_at_pos(world_pos)
            if (clicked_territory and self.tutorial_mission
                    and self.tutorial_mission.active
                    and not self.tutorial_mission.is_territory_interactive(clicked_territory)):
                clicked_territory = None

            if clicked_territory:
                # Dispatch table: maps ability names to their execute functions on GameState
                # All targeted abilities follow the same pattern: execute → cooldown → network sync
                ability_dispatch = {
                    'Relentless Charge': self.game_state.execute_relentless_charge,
                    'Aggressive Diplomacy': self.game_state.execute_aggressive_diplomacy,
                    'Levy': self.game_state.execute_levy,
                    'Decisive Strike': self.game_state.execute_decisive_strike,
                    'Valorous Charge': self.game_state.execute_valorous_charge,
                    'Royal Charisma': self.game_state.execute_royal_charisma,
                    'Regicide': self.game_state.execute_regicide,
                }

                execute_fn = ability_dispatch.get(self.ability_targeting_ability_name)
                if execute_fn:
                    current_player = self.game_state.current_player

                    # Mission hook: block Aggressive Diplomacy on restricted territories
                    if (self.ability_targeting_ability_name == 'Aggressive Diplomacy'
                            and self.tutorial_mission
                            and self.tutorial_mission.active
                            and hasattr(self.tutorial_mission, 'is_attack_target_blocked')
                            and self.tutorial_mission.is_attack_target_blocked(clicked_territory)):
                        self.show_action_error('diplomacy_blocked')
                        return

                    # execute_* record their refusal code (config/action_error_messages.py);
                    # clear any stale code first (the AI/network call the same methods)
                    self.game_state.last_action_error = None
                    self.game_state.last_action_error_args = None
                    success, error_msg = execute_fn(clicked_territory, current_player)

                    if success:
                        # Play targeted spell sound effect
                        from global_sound import play_targeted_spell_sound
                        play_targeted_spell_sound(self.ability_targeting_ability_name)

                        # Ability succeeded — put on cooldown and exit targeting mode
                        hero_name = self.ability_targeting_hero
                        ability_index = self.ability_targeting_ability_index
                        ability_name = self.ability_targeting_ability_name
                        hero_info = self.game_state.HERO_TYPES[hero_name]
                        ability = hero_info['abilities'][ability_index]
                        cooldown = ability.get('cooldown', 0)

                        # Trigger visual particle effect for the ability
                        source_territory = None
                        if ability_name in ('Royal Charisma', 'Valorous Charge'):
                            # Arc abilities need the hero's Keep territory as source/dest
                            hero_data = self.game_state.heroes.get(current_player, {}).get(hero_name)
                            if hero_data:
                                keep_terr = hero_data.get('keep_territory')
                                if ability_name == 'Royal Charisma':
                                    # Particles arc from target to Narn's Keep (units stolen)
                                    source_territory = clicked_territory
                                    self.map_renderer.trigger_ability_effect(
                                        ability_name, keep_terr, current_player,
                                        source_territory=source_territory)
                                else:
                                    # Valorous Charge: particles arc from Keep to target
                                    source_territory = keep_terr
                                    self.map_renderer.trigger_ability_effect(
                                        ability_name, clicked_territory, current_player,
                                        source_territory=source_territory)
                        else:
                            # Burst abilities: effect at target territory
                            self.map_renderer.trigger_ability_effect(
                                ability_name, clicked_territory, current_player)

                        # Put on cooldown
                        if current_player not in self.game_state.hero_ability_cooldowns:
                            self.game_state.hero_ability_cooldowns[current_player] = {}
                        if hero_name not in self.game_state.hero_ability_cooldowns[current_player]:
                            self.game_state.hero_ability_cooldowns[current_player][hero_name] = {}
                        self.game_state.hero_ability_cooldowns[current_player][hero_name][ability_name] = cooldown

                        # MULTIPLAYER: Broadcast targeted ability to other players
                        # Sync fix: send in both sequential and simultaneous modes (not just sim)
                        if self.multiplayer_mode:
                            ability_data = {
                                'player_id': current_player,
                                'hero_name': hero_name,
                                'ability_index': ability_index,
                                'ability_name': ability_name,
                                'target': clicked_territory
                            }
                            # Sync fix: include stolen unit IDs for Royal Charisma
                            # so receiver uses same random selection as sender
                            if ability_name == 'Royal Charisma' and hasattr(self.game_state, '_last_royal_charisma_stolen'):
                                ability_data['stolen_units'] = self.game_state._last_royal_charisma_stolen
                            self._send_action_to_remote(MessageType.SIM_HERO_ABILITY, ability_data)
                            logger.debug(f"[NETWORK] Sent SIM_HERO_ABILITY: {hero_name} - {ability_name} on {clicked_territory}")

                        # Exit targeting mode
                        self.ability_targeting_active = False
                        self.ability_targeting_hero = None
                        self.ability_targeting_ability_index = None
                        self.ability_targeting_ability_name = None

                        # A cast that went through but missed (Regicide with no hero in
                        # the Keep: cooldown spent by design) records a notice — show it
                        self._show_action_failure_feedback()
                    else:
                        # Invalid target - denial sound + toast (the centre-screen popup
                        # was removed: every action error now uses the same toast).
                        # Targeting stays on so the player can pick another territory.
                        if self.game_state.last_action_error:
                            self._show_action_failure_feedback()
                        else:
                            self.show_action_error(message=error_msg)

            return  # Don't process normal map clicks while targeting

        # Convert screen position to world position for click detection
        # This makes clicks work correctly with camera offset and zoom!
        world_pos = self.screen_to_world(pos)
        
        # PRIORITY 1: Check if clicking on a quick-access building icon
        # NOTE: Icons checked FIRST (before armies) so they're clickable when overlapping!
        # Tutorial gate: block quick-access building icons when build not allowed
        _tutorial_build_allowed = not self._is_tutorial_blocking('click_plots')
        # Block building during simultaneous mode resolution phase (battles/alliance markers pending)
        sim_resolving = (self.sim_state is not None and self.sim_state.sim_phase == 'resolving')
        if _tutorial_build_allowed and self.selected_plot and self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning' and not sim_resolving:
            territory, plot_index = self.selected_plot
            if territory in self.scaled_plots and plot_index < len(self.scaled_plots[territory]):
                # Get plot position in world coordinates
                world_plot_pos = self.scaled_plots[territory][plot_index]
                # Transform to screen coordinates (same as rendering!)
                plot_x, plot_y = self.world_to_screen(world_plot_pos)
                plot_x, plot_y = int(plot_x), int(plot_y)
                
                # Check if plot is empty
                is_empty = True
                if territory in self.game_state.buildings:
                    if plot_index in self.game_state.buildings[territory]:
                        if self.game_state.buildings[territory][plot_index] is not None:
                            is_empty = False
                if territory in self.game_state.under_construction:
                    if plot_index in self.game_state.under_construction[territory]:
                        is_empty = False
                
                if is_empty:
                    # Check if clicking on a building icon
                    building_list = list(self.game_state.building_types.keys())
                    num_buildings = len(building_list)
                    
                    # Get scaled icon sizes for click detection (must match rendering!)
                    ui_scale = self.get_ui_scale_factor()
                    scaled_building_icon_radius = int(BUILDING_ICON_RADIUS * ui_scale)
                    scaled_icon_click_radius = int(ICON_CLICK_RADIUS * ui_scale)

                    for i, building_name in enumerate(building_list):
                        angle = (i / num_buildings) * 2 * math.pi - math.pi / 2
                        # Icon position in screen coordinates (same as rendering, with scaling!)
                        icon_x = plot_x + int(scaled_building_icon_radius * math.cos(angle))
                        icon_y = plot_y + int(scaled_building_icon_radius * math.sin(angle))
                        
                        # Check if click is on this icon (using SCREEN coordinates and scaled radius!)
                        click_x, click_y = pos  # Use original screen position, not world_pos!
                        distance = ((click_x - icon_x) ** 2 + (click_y - icon_y) ** 2) ** 0.5
                        if distance < scaled_icon_click_radius:
                            # Clicked on building icon - trigger flash and start construction
                            self.trigger_click_flash('map_building', building_name)

                            # Shared build path (local execute + sim/network sync + feedback)
                            if self._try_start_construction(territory, plot_index, building_name):
                                self.selected_plot = None
                                self.selected_territory_info = None
                                self.clear_button_tooltip()
                            return
        
        # PRIORITY 2: Check if clicking on a quick-access training icon (around Barracks)
        # Tutorial gate: block quick-access training icons when train not allowed
        _tutorial_train_allowed = not self._is_tutorial_blocking('click_barracks')
        # Block training during simultaneous mode resolution phase (battles/alliance markers pending)
        if _tutorial_train_allowed and self.selected_barracks and self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning' and not sim_resolving:
            territory, barracks_plot_index = self.selected_barracks
            if territory in self.scaled_plots and barracks_plot_index < len(self.scaled_plots[territory]):
                # Get plot position in world coordinates
                world_barracks_pos = self.scaled_plots[territory][barracks_plot_index]
                # Transform to screen coordinates (same as rendering!)
                plot_x, plot_y = self.world_to_screen(world_barracks_pos)
                plot_x, plot_y = int(plot_x), int(plot_y)
                
                # Check if clicking on a training icon
                unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain']
                num_units = len(unit_types)
                
                # Get scaled icon sizes for click detection (must match rendering!)
                ui_scale = self.get_ui_scale_factor()
                scaled_building_icon_radius = int(BUILDING_ICON_RADIUS * ui_scale)
                scaled_icon_click_radius = int(ICON_CLICK_RADIUS * ui_scale)

                for i, unit_type in enumerate(unit_types):
                    angle = (i / num_units) * 2 * math.pi - math.pi / 2
                    # Icon position in screen coordinates (same as rendering, with scaling!)
                    icon_x = plot_x + int(scaled_building_icon_radius * math.cos(angle))
                    icon_y = plot_y + int(scaled_building_icon_radius * math.sin(angle))
                    
                    # Check if click is on this icon (using SCREEN coordinates and scaled radius!)
                    click_x, click_y = pos  # Use original screen position, not world_pos!
                    distance = ((click_x - icon_x) ** 2 + (click_y - icon_y) ** 2) ** 0.5
                    if distance < scaled_icon_click_radius:
                        # Clicked on training icon - trigger flash and try to train
                        self.trigger_click_flash('map_training', unit_type)

                        # Shared training path (local execute + sim/network sync + feedback)
                        self._try_start_training(territory, barracks_plot_index, unit_type)
                        # Stay on Barracks (don't deselect)
                        return

        # PRIORITY 2B: Hero training icons removed - use Keep UI only

        # PRIORITY 3: Check if clicking on an army CIRCLE (opens composition UI)
        # NOTE: Army check comes AFTER icon checks so icons take precedence when overlapping
        # Circles only here - banners are checked at PRIORITY 4.5, AFTER plots, because
        # the banner's full-height hit box overlaps building plots (including through the
        # flag art's transparent margins) and would otherwise steal plot clicks.
        if self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
            army_result = self.get_army_at_pos(world_pos, mode='circle')
            if army_result:
                self._select_army_garrison(army_result)
                return  # Don't process other click handling
        
        # PRIORITY 4: Check if clicking on a plot
        plot_click = self.get_plot_at_pos(world_pos)
        if plot_click:
            territory, plot_index = plot_click
            # Trigger click flash for visual feedback
            self.trigger_click_flash('plot', (territory, plot_index))
            
            # Only allow selection for current player's territories
            if self.game_state.territory_owners.get(territory, -1) == self.game_state.current_player:
                # Check if this plot has a Barracks building
                has_barracks = (territory in self.game_state.buildings and 
                               plot_index in self.game_state.buildings[territory] and
                               self.game_state.buildings[territory][plot_index] == 'Barracks')
                
                # Check if this plot has a Keep building
                has_keep = (territory in self.game_state.buildings and
                           plot_index in self.game_state.buildings[territory] and
                           self.game_state.buildings[territory][plot_index] == 'Keep')

                if has_barracks:
                    # Tutorial hook: check if barracks click is allowed
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('click_barracks')):
                        return True  # Silently block
                    # Select Barracks for training UI
                    self.selected_barracks = (territory, plot_index)
                    self.selected_keep = None
                    self.selected_plot = None
                    self.selected_territory_info = None
                    self.selected_hero = None
                    self.clear_ability_targeting()
                    self.game_state.deselect_army()
                    self.show_army_composition = False  # Close composition UI
                    self.selected_army_units = []
                    play_structure_sound('Barracks')
                    # Tutorial hook: notify barracks clicked
                    if self._is_tutorial_active():
                        self.tutorial_mission.notify_event('barracks_clicked', territory=territory)
                elif has_keep:
                    # Select Keep for hero training UI
                    self.selected_keep = (territory, plot_index)
                    self.selected_barracks = None
                    self.selected_plot = None
                    self.selected_territory_info = None
                    self.selected_hero = None
                    self.clear_ability_targeting()
                    self.game_state.deselect_army()
                    self.show_army_composition = False  # Close composition UI
                    self.selected_army_units = []
                    play_structure_sound('Keep')
                else:
                    # Tutorial hook: check if plot clicking is allowed
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('click_plots')):
                        return  # Silently block
                    # Select plot for building UI
                    self.selected_plot = plot_click
                    self.selected_barracks = None
                    self.selected_keep = None
                    self.selected_territory_info = None
                    self.selected_hero = None
                    self.clear_ability_targeting()
                    self.game_state.deselect_army()
                    self.show_army_composition = False  # Close composition UI
                    self.selected_army_units = []
                    # Play structure sound: completed building sound or construction sound
                    completed_building = self.game_state.buildings.get(territory, {}).get(plot_index)
                    if completed_building:
                        play_structure_sound(completed_building)
                    else:
                        play_structure_sound('Construction')
                return
        
        # PRIORITY 4.5: Check if clicking on an army BANNER (opens composition UI)
        # Runs after plots so plot clicking keeps its existing behaviour exactly,
        # while the banner remains clickable everywhere a plot is not.
        if self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
            army_result = self.get_army_at_pos(world_pos, mode='banner')
            if army_result:
                self._select_army_garrison(army_result)
                return  # Don't process other click handling

        # Not clicking on a plot - handle territory click
        territory = self.get_territory_at_pos(world_pos)
        # Tutorial hook: filter out non-interactive territories
        if (territory and self.tutorial_mission
                and self.tutorial_mission.active
                and not self.tutorial_mission.is_territory_interactive(territory)):
            territory = None
        if not territory:
            # Clicking on empty space - deselect everything
            self.selected_plot = None
            self.selected_territory_info = None
            self.selected_barracks = None  # Deselect barracks too
            self.selected_keep = None  # Deselect keep too
            self.selected_hero = None  # Deselect hero too
            self.clear_ability_targeting()
            self.game_state.deselect_army()  # Deselect army too
            self.show_army_composition = False  # Close composition UI
            self.selected_army_units = []  # Clear unit selection
            return
        
        # Setup phase: claim territories
        if self.game_state.phase == 'setup':
            current_player = self.game_state.current_player
            if self.game_state.claim_territory(territory, current_player):
                # Move to next player for their choice
                self.game_state.next_player()
        
        # Playing phase: show territory info
        elif self.game_state.phase == 'playing':
            # Deselect plot and barracks when clicking territory (not on plot)
            self.selected_plot = None
            self.selected_barracks = None
            self.selected_keep = None
            self.selected_hero = None
            self.clear_ability_targeting()

            # Close composition UI when clicking territory
            self.show_army_composition = False
            self.selected_army_units = []

            # Show territory info in bottom panel
            self.selected_territory_info = territory
            
            # Deselect army when clicking elsewhere (not on army circle)
            if self.game_state.turn_phase == 'planning':
                self.game_state.deselect_army()
            
            # Keep old selected_territory for backwards compatibility
            self.game_state.selected_territory = None
    
    def handle_right_click(self, pos):
        """Handle right-click for creating movement orders and canceling research (Phase 2D: camera-aware)"""
        # (The simultaneous-mode 'resolving' block is further down, once we know the
        # player actually tried to send units — only then does it earn an error toast.
        # The sidebar's research right-click has its own resolving check.)

        # Block right-clicks on top panel
        if pos[1] < TOP_PANEL_HEIGHT:
            return

        # Check if clicking on the sidebar (panel body, bookmark tabs, collapse button).
        # Uses the live sidebar layout, so it follows collapse/expand.
        if self.is_point_over_sidebar(pos):
            # Technology tab right-click cancels research (not mid-slide: the
            # buttons are moving under the cursor)
            if (self.is_point_over_sidebar_panel(pos)
                    and self.game_state.sidebar_expanded
                    and not self.is_sidebar_animating()
                    and self.game_state.active_sidebar_tab == 'technology'):
                handled = self.handle_technology_tab_click(pos, right_click=True)
                if handled:
                    return handled
            # Block all right-clicks over the sidebar from reaching the map
            return

        # Check if clicking on map area (not bottom UI)
        if pos[1] >= BOTTOM_UI_Y:
            return

        # Convert screen position to world position (Phase 2D: camera support!)
        world_pos = self.screen_to_world(pos)

        # Get the territory clicked
        territory = self.get_territory_at_pos(world_pos)
        # Tutorial hook: filter out non-interactive territories
        if (territory and self.tutorial_mission
                and self.tutorial_mission.active
                and not self.tutorial_mission.is_territory_interactive(territory)):
            territory = None
        if not territory:
            return

        # Is the player trying to send armies? Only then do the refusals below earn an
        # error toast — a plain right-click on the map stays silent.
        sending_units = bool((self.show_army_composition and self.selected_army_units)
                             or self.game_state.selected_army)

        # Block movement orders during simultaneous mode resolution phase
        if self._is_sim_resolving():
            if sending_units:
                self.show_action_error('wrong_phase')
            return

        # Mission hook: block army orders to territories restricted by campaign mission
        # (e.g., Mission 6 blocks Red from attacking certain territories until quests unlock them)
        if (territory and self.tutorial_mission
                and self.tutorial_mission.active
                and hasattr(self.tutorial_mission, 'is_attack_target_blocked')
                and self.tutorial_mission.is_attack_target_blocked(territory)):
            # Only block if player is trying to send armies (has units selected)
            if sending_units:
                self.game_state.add_message(f"Cannot target {territory} yet!")
                self.show_action_error('target_blocked', territory=territory)
                return

        # CASE 1: Composition UI is open with selected units
        if self.show_army_composition and self.army_composition_territory and self.selected_army_units:
            from_territory = self.army_composition_territory

            # Can't move to same territory (silent: not a meaningful order attempt)
            if from_territory == territory:
                return

            # The army-limit check for reinforcements happens inside
            # add_movement_order_for_units(). A separate pre-check here counted the
            # selected units' existing order to the same destination twice (they are
            # auto-cancelled only inside that method) and could refuse a valid order.

            # Create movement order for selected units
            # Pass the garrison player (for multi-garrison support)
            garrison_player = self.army_composition_player if self.army_composition_player is not None else self.game_state.current_player
            if self.game_state.add_movement_order_for_units(from_territory, territory, self.selected_army_units, player=garrison_player):
                # Don't send to remote - they'll see the movement when orders execute
                # Clear selection after issuing order
                self.selected_army_units = []
            else:
                # Refused (army limit, not reachable, units already moved): sound + toast.
                # Refusals without a player-facing code (tutorial block) stay silent.
                self._show_action_failure_feedback()
            return
        
        # CASE 2: Legacy - army selected (old system compatibility)
        if self.game_state.selected_army:
            from_territory, _ = self.game_state.selected_army
            
            # Can't move to same territory
            if from_territory == territory:
                return
            
            # Check if this would exceed army limit (for reinforcements or allied reinforcements)
            owner_from = self.game_state.territory_owners.get(from_territory, -1)
            owner_to = self.game_state.territory_owners.get(territory, -1)

            # Check for reinforcement (same owner) OR allied reinforcement
            is_friendly_move = (owner_from == owner_to or
                              (owner_to >= 0 and self.game_state.are_allies(self.game_state.current_player, owner_to)))

            if is_friendly_move:
                # This is a reinforcement - check projected capacity (accounts for outgoing orders)
                projected, _ = self.game_state._get_effective_capacity(territory)
                garrison_from = self.game_state.territory_garrisons.get(from_territory, {}).get(self.game_state.current_player)
                reinforcing_count = garrison_from.get('unmoved', 0) if garrison_from else 0
                if projected + reinforcing_count > self.game_state.MAX_ARMIES_PER_TERRITORY:
                    self.game_state.add_message(f"Cannot reinforce {territory}: would exceed army limit of {self.game_state.MAX_ARMIES_PER_TERRITORY}!")
                    return
            
            # Try to create movement order
            if self.game_state.add_movement_order(from_territory, territory):
                # Send to remote player (multiplayer)
                if self.multiplayer_mode:
            
                    # Get unit IDs from the order that was just created
                    if self.game_state.movement_orders:
                        last_order = self.game_state.movement_orders[-1]
                        self._send_action_to_remote(MessageType.MOVEMENT_ORDER, {
                            'from_territory': from_territory,
                            'to_territory': territory,
                            'unit_ids': last_order.unit_ids,
                            'player_index': self.local_player_index  # Include player for 4-player support
                        })
            return  # C1 fix: explicit return after CASE 2 movement order

    def _draw_battle_popup_initial(self, battle, modal_x, modal_y, modal_height, y_pos):
        """
        Draw initial battle popup state.
        
        Shows participants with unit compositions and resolve button.
        Called before battle resolution.
        """
        if not battle:
            return  # Can't show initial state without battle
        
        # Show participants with unit compositions
        for player, count in battle.armies.items():
            player_color = self.game_state.get_player_color(player)
            
            # Get composition if available
            player_name = self.game_state.get_player_name(player)
            if player in battle.army_compositions:
                comp = battle.army_compositions[player]
                comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])
                player_text = self._get_cached_text(f"{player_name}: {comp_str}", self.font, player_color)
            else:
                player_text = self._get_cached_text(f"{player_name}: {count} armies", self.font, player_color)

            player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(player_text, player_rect)
            y_pos += 40

        y_pos += 20

        # Show tactical prediction based on unit types
        pred_text = self._get_cached_text("(Unit types and counters will determine victor)", self.small_font, (150, 150, 150))
        pred_rect = pred_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
        self.screen.blit(pred_text, pred_rect)
        
        # Resolve button
        button_y = modal_y + modal_height - 80
        resolve_rect = pygame.Rect(WINDOW_WIDTH // 2 - 100, button_y, 200, 50)
        pygame.draw.rect(self.screen, (200, 50, 50), resolve_rect)
        pygame.draw.rect(self.screen, WHITE, resolve_rect, 3)
        button_text = self._get_cached_text("RESOLVE BATTLE", self.font, WHITE)
        button_text_rect = button_text.get_rect(center=resolve_rect.center)
        self.screen.blit(button_text, button_text_rect)
        self.resolve_battle_button = resolve_rect
    
    def _draw_battle_popup_resolving(self, modal_x, modal_y, y_pos):
        """
        Draw resolving battle popup state.
        
        Shows battle calculations - either two-phase Keep combat or
        normal deterministic combat with effective strengths.
        """
        if not self.battle_result:
            return
        
        armies = self.battle_result.get('armies', {})
        compositions = self.battle_result.get('compositions', {})
        has_keep = self.battle_result.get('has_keep', False)
        
        if not armies:
            return
        
        # Check if this is a Keep battle
        if has_keep:
            # TWO-PHASE KEEP BATTLE DISPLAY (using cached static text)
            title = self._get_cached_text("Two-Phase Keep Battle:", self.font, (255, 200, 100))
            title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(title, title_rect)
            y_pos += 40

            # Phase 1 info (cached)
            phase1_text = self._get_cached_text("Phase 1: Attackers vs Garrison (counters apply)", self.small_font, (150, 200, 255))
            phase1_rect = phase1_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(phase1_text, phase1_rect)
            y_pos += 30

            # Show compositions with effective strengths
            for player, count in armies.items():
                player_color = self.game_state.get_player_color(player)

                player_name = self.game_state.get_player_name(player)
                if player in compositions:
                    comp = compositions[player]
                    comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])
                    player_text = self._get_cached_text(f"{player_name}: {comp_str}", self.small_font, player_color)
                else:
                    player_text = self._get_cached_text(f"{player_name}: {count} armies", self.small_font, player_color)

                player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(player_text, player_rect)
                y_pos += 25

            y_pos += 10

            # Phase 2 info (cached)
            phase2_text = self._get_cached_text("Phase 2: Remaining attackers vs Keep (+2 armies)", self.small_font, (255, 200, 100))
            phase2_rect = phase2_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(phase2_text, phase2_rect)
            y_pos += 30

            # Keep is type-neutral (cached)
            keep_note = self._get_cached_text("(Keep defense is type-neutral)", self.small_font, (150, 150, 150))
            keep_note_rect = keep_note.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(keep_note, keep_note_rect)

        else:
            # NORMAL BATTLE DISPLAY (cached)
            title = self._get_cached_text("Deterministic Combat:", self.font, (255, 200, 100))
            title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(title, title_rect)
            y_pos += 40
            
            # Show compositions with effective strengths
            effective_strengths = {}
            
            for player, count in armies.items():
                player_color = self.game_state.get_player_color(player)
                
                # Get composition
                if player in compositions:
                    comp = compositions[player]
                    comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])
                    
                    # Calculate effective strength against enemies
                    enemy_comp = {}
                    for enemy_player in armies.keys():
                        if enemy_player != player and enemy_player in compositions:
                            enemy_c = compositions[enemy_player]
                            for ut, uc in enemy_c.items():
                                enemy_comp[ut] = enemy_comp.get(ut, 0) + uc
                    
                    player_name = self.game_state.get_player_name(player)
                    if enemy_comp:
                        eff_str = self.game_state.calculate_army_effective_strength(comp, enemy_comp)
                        effective_strengths[player] = eff_str

                        player_text = self._get_cached_text(
                            f"{player_name}: {comp_str}",
                            self.small_font, player_color
                        )
                        strength_text = self._get_cached_text(
                            f"Effective Strength: {eff_str:.1f}",
                            self.small_font, (200, 200, 200)
                        )
                    else:
                        player_text = self._get_cached_text(f"{player_name}: {comp_str}", self.small_font, player_color)
                        strength_text = None
                else:
                    player_name = self.game_state.get_player_name(player)
                    player_text = self._get_cached_text(f"{player_name}: {count} armies", self.small_font, player_color)
                    strength_text = None
                
                player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(player_text, player_rect)
                y_pos += 25
                
                if strength_text:
                    strength_rect = strength_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                    self.screen.blit(strength_text, strength_rect)
                    y_pos += 25
            
            # Show who has advantage based on effective strength
            if effective_strengths:
                max_strength = max(effective_strengths.values())
                leaders = [p for p, s in effective_strengths.items() if abs(s - max_strength) < 0.01]
                
                y_pos += 10
                
                if len(leaders) == 1:
                    leader = leaders[0]
                    leader_color = self.game_state.get_player_color(leader)
                    leader_name = self.game_state.get_player_name(leader)
                    advantage_text = self._get_cached_text(
                        f"{leader_name} has superior strength!",
                        self.font, leader_color
                    )
                    advantage_rect = advantage_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                    self.screen.blit(advantage_text, advantage_rect)
                else:
                    tie_text = self._get_cached_text("Perfect tie - dice will decide!", self.font, (255, 200, 0))
                    tie_rect = tie_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                    self.screen.blit(tie_text, tie_rect)
    
    def _draw_battle_popup_result(self, modal_x, modal_y, modal_height, y_pos):
        """
        Draw result battle popup state.
        
        Shows winner announcement and battle summary with compositions
        and effective strengths or roles.
        """
        if not self.battle_result:
            return
        
        winner = self.battle_result.get('winner', -1)
        surviving = self.battle_result.get('surviving_armies', 0)
        has_keep = self.battle_result.get('has_keep', False)
        compositions = self.battle_result.get('compositions', {})
        armies = self.battle_result.get('armies', {})
        
        # Victory announcement
        if winner != -1:
            winner_color = self.game_state.get_player_color(winner)
            winner_name = self.game_state.get_player_name(winner)
            winner_text = self._get_cached_text(f"{winner_name} WINS!", self.large_font, winner_color)
            winner_rect = winner_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(winner_text, winner_rect)
            y_pos += 50

            if surviving > 0:
                surv_text = self._get_cached_text(f"{surviving} armies remain", self.font, WHITE)
                surv_rect = surv_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(surv_text, surv_rect)
                y_pos += 40
        else:
            tie_text = self._get_cached_text("PERFECT TIE!", self.large_font, (255, 200, 0))
            tie_rect = tie_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(tie_text, tie_rect)
            y_pos += 50

            neutral_text = self._get_cached_text("Territory becomes neutral", self.font, WHITE)
            neutral_rect = neutral_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(neutral_text, neutral_rect)
            y_pos += 40

        # Battle Summary Section
        y_pos += 10
        summary_title = self._get_cached_text("Battle Summary:", self.font, (200, 200, 200))
        summary_rect = summary_title.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
        self.screen.blit(summary_title, summary_rect)
        y_pos += 30

        if has_keep:
            # Keep battle summary
            summary_line1 = self._get_cached_text("Two-phase Keep battle", self.small_font, (255, 200, 100))
            line1_rect = summary_line1.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(summary_line1, line1_rect)
            y_pos += 25

            # Show participants
            for player, count in armies.items():
                player_color = self.game_state.get_player_color(player)
                player_name = self.game_state.get_player_name(player)
                if player in compositions:
                    comp = compositions[player]
                    comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])
                    role = "Defender (+Keep)" if player == self.battle_result.get('defender', -1) else "Attacker"
                    player_text = self._get_cached_text(f"{player_name} ({role}): {comp_str}", self.small_font, player_color)
                else:
                    player_text = self._get_cached_text(f"{player_name}: {count} armies", self.small_font, player_color)

                player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(player_text, player_rect)
                y_pos += 22

        else:
            # Normal battle summary
            summary_line1 = self._get_cached_text("Unit counters determined outcome", self.small_font, (150, 200, 255))
            line1_rect = summary_line1.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(summary_line1, line1_rect)
            y_pos += 25

            # Show participants with effective strengths
            for player, count in armies.items():
                player_color = self.game_state.get_player_color(player)

                if player in compositions:
                    comp = compositions[player]
                    comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])

                    # Calculate effective strength
                    enemy_comp = {}
                    for enemy_player in armies.keys():
                        if enemy_player != player and enemy_player in compositions:
                            enemy_c = compositions[enemy_player]
                            for ut, uc in enemy_c.items():
                                enemy_comp[ut] = enemy_comp.get(ut, 0) + uc

                    if enemy_comp:
                        eff_str = self.game_state.calculate_army_effective_strength(comp, enemy_comp)
                        victory_mark = " [W]" if player == winner else ""  # H4 fix: ASCII winner mark (replaces garbled Unicode)
                        player_name = self.game_state.get_player_name(player)
                        player_text = self._get_cached_text(
                            f"{player_name}: {comp_str} (Str: {eff_str:.1f}){victory_mark}",
                            self.small_font, player_color
                        )
                    else:
                        player_name = self.game_state.get_player_name(player)
                        player_text = self._get_cached_text(f"{player_name}: {comp_str}", self.small_font, player_color)
                else:
                    player_name = self.game_state.get_player_name(player)
                    player_text = self._get_cached_text(f"{player_name}: {count} armies", self.small_font, player_color)
                
                player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(player_text, player_rect)
                y_pos += 22
        
        # Close button
        button_y = modal_y + modal_height - 80
        close_rect = pygame.Rect(WINDOW_WIDTH // 2 - 80, button_y, 160, 50)
        pygame.draw.rect(self.screen, (50, 150, 50), close_rect)
        pygame.draw.rect(self.screen, WHITE, close_rect, 3)
        button_text = self._get_cached_text("CLOSE", self.font, WHITE)
        button_text_rect = button_text.get_rect(center=close_rect.center)
        self.screen.blit(button_text, button_text_rect)
        self.close_popup_button = close_rect
    
    def draw_battle_popup(self):
        """
        Draw battle interface.

        Uses EnhancedBattleInterface when active, falls back to UIRenderer
        for legacy popup system.
        """
        # Use enhanced battle interface if active
        if self.enhanced_battle_ui is not None:
            self.enhanced_battle_ui.render()
            return

        # Fallback to legacy popup (should not be reached with new system)
        self.ui_renderer.draw_battle_popup()

    def draw_disconnect_dialog(self):
        """Draw disconnect dialog overlay"""
        # Semi-transparent overlay (cached to avoid 5.44MB SRCALPHA alloc per frame)
        size = (WINDOW_WIDTH, WINDOW_HEIGHT)
        if self._cached_disconnect_overlay is None or self._cached_disconnect_overlay.get_size() != size:
            self._cached_disconnect_overlay = pygame.Surface(size, pygame.SRCALPHA)
            self._cached_disconnect_overlay.fill((0, 0, 0, 180))
        overlay = self._cached_disconnect_overlay
        self.screen.blit(overlay, (0, 0))

        # Dialog box
        dialog_width = 500
        dialog_height = 250
        dialog_x = (WINDOW_WIDTH - dialog_width) // 2
        dialog_y = (WINDOW_HEIGHT - dialog_height) // 2

        dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_width, dialog_height)
        pygame.draw.rect(self.screen, (60, 60, 70), dialog_rect, border_radius=10)
        pygame.draw.rect(self.screen, (200, 200, 200), dialog_rect, 3, border_radius=10)

        # Title (cached - static text)
        title_text = self._get_cached_text("Connection Lost", self.large_font, (255, 100, 100))
        title_rect = title_text.get_rect(center=(dialog_x + dialog_width // 2, dialog_y + 50))
        self.screen.blit(title_text, title_rect)

        # Reason (cached - changes only when disconnect reason changes)
        reason_text = self._get_cached_text(self.disconnect_dialog_reason, self.small_font, (220, 220, 220))
        reason_rect = reason_text.get_rect(center=(dialog_x + dialog_width // 2, dialog_y + 100))
        self.screen.blit(reason_text, reason_rect)

        # Message (cached - static text)
        message = "The multiplayer connection has been lost."
        message_text = self._get_cached_text(message, self.small_font, (200, 200, 200))
        message_rect = message_text.get_rect(center=(dialog_x + dialog_width // 2, dialog_y + 140))
        self.screen.blit(message_text, message_rect)

        # Exit button
        button_width = 200
        button_height = 50
        button_x = dialog_x + (dialog_width - button_width) // 2
        button_y = dialog_y + dialog_height - 80

        exit_button = pygame.Rect(button_x, button_y, button_width, button_height)
        pygame.draw.rect(self.screen, (150, 50, 50), exit_button, border_radius=5)
        pygame.draw.rect(self.screen, (200, 200, 200), exit_button, 2, border_radius=5)

        exit_text = self._get_cached_text("Exit to Main Menu", self.small_font, (255, 255, 255))
        exit_text_rect = exit_text.get_rect(center=exit_button.center)
        self.screen.blit(exit_text, exit_text_rect)

        # Store button for click detection
        self.disconnect_exit_button = exit_button

    # ========================================
    # SIDEBAR LAYOUT & COLLAPSE
    # ========================================
    # Single source of truth for "where is the right sidebar": every click, hover,
    # tooltip, wheel and AI-turn check goes through these helpers instead of
    # recomputing WINDOW_WIDTH - 250 (which ignored the collapsed state).

    def get_sidebar_layout(self):
        """Current sidebar geometry, animated while sliding (see ui/sidebar_layout.py)."""
        game_state = getattr(self, 'game_state', None)
        expanded = game_state.sidebar_expanded if game_state is not None else True
        progress = sidebar_progress(expanded, self._sidebar_anim_start_ms,
                                    pygame.time.get_ticks(), UIConstants.SIDEBAR_SLIDE_MS)
        return compute_sidebar_layout(WINDOW_WIDTH, TOP_PANEL_HEIGHT, MAP_HEIGHT, progress,
                                      UIConstants.SIDEBAR_WIDTH, UIConstants.TAB_WIDTH)

    def is_sidebar_animating(self):
        """True while the collapse/expand slide is running."""
        start = self._sidebar_anim_start_ms
        return (start is not None
                and pygame.time.get_ticks() - start < UIConstants.SIDEBAR_SLIDE_MS)

    def can_collapse_sidebar(self):
        """False while the active mission forbids collapsing the sidebar.

        The tutorial forbids it at every step (TutorialMission.is_action_allowed
        refuses 'toggle_sidebar'); campaign missions and Tales allow it except while
        they block all actions (intro, pause, victory/defeat sequence).
        """
        mission = getattr(self, 'tutorial_mission', None)
        if mission is not None and getattr(mission, 'active', False):
            return bool(mission.is_action_allowed('toggle_sidebar'))
        return True

    def toggle_sidebar(self, expand=None, animate=True):
        """Collapse or expand the sidebar.

        Args:
            expand: True / False to force a state, None to flip it.
            animate: Slide (default) or snap.

        Returns:
            bool: True if the state changed. Collapsing is refused while
            can_collapse_sidebar() is False; expanding is always allowed so the
            panel can never get stuck closed.
        """
        game_state = getattr(self, 'game_state', None)
        if game_state is None:
            return False
        target = (not game_state.sidebar_expanded) if expand is None else bool(expand)
        if target == game_state.sidebar_expanded:
            return False
        if not target and not self.can_collapse_sidebar():
            return False

        game_state.sidebar_expanded = target
        if animate:
            # Reversing mid-slide resumes from the current position (no jump)
            self._sidebar_anim_start_ms = reverse_anim_start(
                self._sidebar_anim_start_ms, pygame.time.get_ticks(),
                UIConstants.SIDEBAR_SLIDE_MS)
        else:
            self._sidebar_anim_start_ms = None
        # Tech-tree particles store absolute screen positions; after the panel moves
        # they would float over the map for their 1.5-3 s lifetime.
        particles = getattr(getattr(self, 'ui_renderer', None), 'tech_particles', None)
        if particles:
            particles.clear()
        return True

    def _reset_sidebar_scroll(self):
        """Fresh scroll positions for every scrollable sidebar tab (new game).

        Action Log and Chat are anchored at the bottom: offset 0 shows the newest
        entries and the wheel moves back into history.
        """
        self.sidebar_scroll = {
            'action_queue': ScrollState('top'),
            'heroes': ScrollState('top'),
            'action_log': ScrollState('bottom'),
            'chat': ScrollState('bottom'),
        }
        # Action Log filter chip (rendering/action_log_model.FILTERS): its id and the
        # category set the log model shows (None = all)
        self.sidebar_log_filter_id = 'all'
        self.sidebar_log_filter = None
        self.sidebar_log_chips = {}   # filter id -> screen rect, filled by the renderer
        # Unread badges on the Chat / Action Log bookmarks: how many countable items the
        # viewer has already seen per tab (None = take the current total as read, so a
        # loaded save's history doesn't start out as "unread")
        self.sidebar_seen = {'chat': None, 'action_log': None}
        self._unread_cache = {}

    def set_sidebar_log_filter(self, filter_id):
        """Switch the Action Log filter chip; the log jumps back to the newest entry."""
        from rendering.action_log_model import FILTERS
        categories = next((cats for fid, _label, cats in FILTERS if fid == filter_id), None)
        self.sidebar_log_filter_id = filter_id
        self.sidebar_log_filter = set(categories) if categories else None
        self.sidebar_scroll['action_log'].offset = 0

    def handle_sidebar_wheel(self, delta):
        """Mouse wheel over the sidebar panel. Returns True when the panel took it.

        Over the panel body the wheel scrolls the active tab's list (3 text lines per
        notch) and is ALWAYS consumed there — before, on tabs without scrolling it
        zoomed the map hidden under the panel. Off the panel (or while it slides) it
        returns False and the caller zooms the map as usual.
        """
        if not self.game_state or not self.game_state.sidebar_expanded or self.is_sidebar_animating():
            return False
        if not self.is_point_over_sidebar_panel(pygame.mouse.get_pos()):
            return False
        tab = self.game_state.active_sidebar_tab
        scroll = getattr(self, 'sidebar_scroll', {}).get(tab)
        if scroll is not None and delta:
            step = 3 * self.sidebar_widgets.font('body').get_linesize()
            # Wheel up (delta > 0) = towards the start of the list
            scroll.scroll(-step if delta > 0 else step)
        return True

    def is_point_on_sidebar_chrome(self, pos):
        """True on the collapse button or a bookmark tab (visible in every state)."""
        toggle = self.sidebar_toggle_button
        if toggle is not None and toggle.collidepoint(pos):
            return True
        return any(rect.collidepoint(pos) for rect in (self.sidebar_tab_buttons or {}).values())

    def is_point_over_sidebar_panel(self, pos):
        """True over the panel body (only while any of it is on screen).

        Bounded to the map's height: the sidebar ends at the bottom UI panel, so
        bottom-UI buttons in the rightmost 250 px are never swallowed.
        """
        if not (TOP_PANEL_HEIGHT <= pos[1] < BOTTOM_UI_Y):
            return False
        layout = self.get_sidebar_layout()
        return layout.panel_visible and pos[0] >= layout.panel_x

    def is_point_over_sidebar(self, pos):
        """True anywhere the sidebar covers the map: panel body, tabs or button."""
        return self.is_point_on_sidebar_chrome(pos) or self.is_point_over_sidebar_panel(pos)

    def _is_ai_turn_click_allowed(self, pos):
        """Clicks allowed while an AI player takes its turn.

        Menus, the top panel, and the sidebar's bookmark tabs / collapse button
        (switching tabs and collapsing are local UI, not game actions). The old
        cached x-band also let through 50 px of MAP left of the tabs.
        """
        if self.game_menu_visible or self.options_menu_visible:
            return True
        if pos[1] < TOP_PANEL_HEIGHT:
            return True
        return self.is_point_on_sidebar_chrome(pos)

    def draw_order_sidebar(self):
        """
        Draw the right sidebar: panel, bookmark tabs and collapse button.

        Tabs (one active at a time): Technology, Heroes, Action Queue, Action Log,
        Quests, Chat. Visible during both planning and battle phases.

        Collapsible (F2 or the button above the tabs). Geometry comes from
        get_sidebar_layout() (ui/sidebar_layout.py):
        - expanded:  panel at the right edge, bookmark tabs sticking out to its left
        - collapsed: panel off-screen, bookmark tabs flush with the screen edge; a
                     click on a tab expands the panel on that tab
        - sliding:   panel, tabs and content drawn at the animated x
        The map is drawn full-width underneath (the panel is only an overlay), and
        the east map extension fills the strip past the map's edge when zoomed out.
        """
        # Forget a finished slide so is_sidebar_animating() stays cheap and exact
        if self._sidebar_anim_start_ms is not None and not self.is_sidebar_animating():
            self._sidebar_anim_start_ms = None
        # Hover label for this frame (set by tab content, drawn in update_frame_tooltips)
        self.sidebar_tooltip = None
        # Re-set by the Action Queue card under the mouse (read by the map renderer,
        # which draws before the sidebar - so it shows the previous frame's hover)
        self.sidebar_hovered_route = None

        layout = self.get_sidebar_layout()
        sidebar_width = UIConstants.SIDEBAR_WIDTH
        sidebar_x = layout.panel_x        # == WINDOW_WIDTH when fully collapsed
        sidebar_y = layout.top            # Start below top panel
        sidebar_height = layout.height    # Full height to bottom panel

        # Panel background (skipped when fully off-screen)
        if layout.panel_visible:
            sidebar_rect = pygame.Rect(sidebar_x, sidebar_y, sidebar_width, sidebar_height)
            # Use custom image if available, otherwise fallback to solid color
            if self.right_panel_image:
                # Blit image with left edge aligned to sidebar left edge
                self.screen.blit(self.right_panel_image, (sidebar_x, sidebar_y))
            else:
                pygame.draw.rect(self.screen, (40, 40, 40), sidebar_rect)

        # Bookmark tabs: always drawn, they travel with the panel's left edge
        content_start_y = self.ui_renderer._draw_sidebar_tab_buttons(sidebar_x, sidebar_y, sidebar_width, sidebar_height)

        # Bronze border, drawn after the tabs: its left edge leaves a gap beside the
        # active bookmark so that tab visibly merges into the panel
        if layout.panel_visible:
            self._draw_sidebar_border(pygame.Rect(sidebar_x, sidebar_y, sidebar_width, sidebar_height))

        # Collapse / expand button above the tabs (also travels with them)
        self._draw_sidebar_toggle_button(layout)

        # Order-count badge on the Action Queue bookmark while the panel is closed
        if not self.game_state.sidebar_expanded:
            self._draw_sidebar_order_badge()
        # Unread counts on the Chat / Action Log bookmarks
        if UIConstants.SIDEBAR_UNREAD_BADGES:
            self._draw_sidebar_unread_badges(layout)

        if not layout.panel_visible:
            # Fully collapsed: no content is drawn, so clear its click rects — stale
            # ones would otherwise still match clicks on the map underneath.
            self.technology_buttons = {}
            self.hero_selection_buttons = {}
            self.order_cancel_buttons = []
            self.order_card_rects = []
            self.sidebar_hero_ability_buttons = {}
            self.hero_portrait_rects = {}
            self.cancel_all_button = None
            self.update_button_hover(None, 'sidebar_hero_ability')
            return

        # Draw content based on active tab (Phase 4D: inlined delegates)
        active_tab = self.game_state.active_sidebar_tab
        if active_tab != 'heroes':
            # Hero-card rects/hover belong to the Heroes tab only
            self.sidebar_hero_ability_buttons = {}
            self.hero_portrait_rects = {}
            self.update_button_hover(None, 'sidebar_hero_ability')

        if active_tab == 'action_queue':
            self.ui_renderer._draw_action_queue_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        elif active_tab == 'technology':
            self.ui_renderer._draw_technology_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        elif active_tab == 'heroes':
            self.ui_renderer._draw_heroes_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        elif active_tab == 'action_log':
            self.ui_renderer._draw_action_log_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        elif active_tab == 'quests':
            self.ui_renderer._draw_quests_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        elif active_tab == 'chat':
            self.ui_renderer._draw_chat_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)

        # CANCEL ALL is drawn by the Action Queue renderer (pinned footer, centred on the
        # tapestry); other tabs have no such button.
        if active_tab != 'action_queue':
            self.cancel_all_button = None
            # Card / Cancel Order rects belong to the Action Queue only: stale ones would
            # still match clicks on the Action Log (whose chips share the click handler)
            self.order_cancel_buttons = []
            self.order_card_rects = []
        if active_tab != 'action_log':
            self.sidebar_log_chips = {}

    def _draw_sidebar_border(self, rect):
        """Bronze 3 px panel border (was flat grey), open beside the active tab.

        The gap lines up with the active bookmark's rect (sidebar_tab_buttons, filled by
        the tab renderer this frame), so the lit tab reads as part of the panel.
        """
        color = (138, 98, 50)
        width = 3
        pygame.draw.line(self.screen, color, rect.topleft, (rect.right - 1, rect.top), width)
        pygame.draw.line(self.screen, color, (rect.left, rect.bottom - 2), (rect.right - 1, rect.bottom - 2), width)
        pygame.draw.line(self.screen, color, (rect.right - 2, rect.top), (rect.right - 2, rect.bottom - 1), width)
        active = (self.sidebar_tab_buttons or {}).get(self.game_state.active_sidebar_tab)
        x = rect.left + 1
        if active is not None and self.game_state.sidebar_expanded:
            # Left edge in two pieces around the active tab
            if active.top > rect.top:
                pygame.draw.line(self.screen, color, (x, rect.top), (x, active.top), width)
            if active.bottom < rect.bottom:
                pygame.draw.line(self.screen, color, (x, active.bottom - 1), (x, rect.bottom - 1), width)
        else:
            pygame.draw.line(self.screen, color, (x, rect.top), (x, rect.bottom - 1), width)

    def _draw_sidebar_toggle_button(self, layout):
        """Round collapse / expand button, in the tab column just above the bookmarks.

        A gold disc (the same CircleBorder art as the map's plot icons) with dark
        chevrons pointing the way the panel will move: '>>' (collapse) while
        expanded, '<<' (expand) while collapsed. Brightens on hover and flashes on
        click; dimmed — and refused by toggle_sidebar() — while the active mission
        forbids collapsing (the whole tutorial).

        The clickable area stays the full tab-column cell (sidebar_toggle_button),
        a slightly larger target than the disc itself.
        """
        rect = pygame.Rect(layout.tab_x, layout.top + 4, UIConstants.TAB_WIDTH,
                           UIConstants.SIDEBAR_TOGGLE_HEIGHT)
        expanded = self.game_state.sidebar_expanded
        if expanded and not self.can_collapse_sidebar():
            state = 'locked'
        elif self.clicked_element == ('sidebar_toggle', 'toggle'):
            state = 'click'
        elif rect.collidepoint(self.mouse_pos):
            state = 'hover'
        else:
            state = 'normal'

        diameter = min(rect.width, rect.height) - 1
        sprite = self._get_sidebar_toggle_sprite(diameter, expanded, state)
        self.screen.blit(sprite, sprite.get_rect(center=rect.center))
        self.sidebar_toggle_button = rect

    def _get_sidebar_toggle_sprite(self, diameter, expanded, state):
        """Pre-rendered round toggle button, cached per (size, direction, state).

        PERFORMANCE: scaling the 1024 px CircleBorder art and drawing the chevrons
        happens once per variant (8 at most), never per frame. The cache is cleared
        by apply_display_settings() with the other UI caches.
        """
        key = (diameter, expanded, state)
        sprite = self._sidebar_toggle_sprites.get(key)
        if sprite is not None:
            return sprite

        sprite = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        radius = diameter // 2
        # Solid underlay: CircleBorder's centre is partly see-through (it frames plot
        # icons), so without this the map or the dark fog would show through the button.
        pygame.draw.circle(sprite, (52, 38, 20), (radius, radius), radius)        # dark bronze rim
        pygame.draw.circle(sprite, (168, 132, 58), (radius, radius), radius - 3)  # gold face
        if self.circle_border is not None:
            sprite.blit(pygame.transform.smoothscale(self.circle_border, (diameter, diameter)), (0, 0))

        if state in ('hover', 'click'):
            # Brighten the disc only (BLEND_RGB_ADD leaves alpha — the round shape — intact)
            boost = 70 if state == 'click' else 35
            sprite.fill((boost, boost, boost), special_flags=pygame.BLEND_RGB_ADD)
        elif state == 'locked':
            # Disabled look: darken (BLEND_RGBA_MULT keeps the transparent corners transparent)
            sprite.fill((150, 150, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)

        # Two dark chevrons pointing the way the panel will move
        chevron_color = (52, 42, 30) if state == 'locked' else (48, 30, 12)
        direction = 1 if expanded else -1       # +1 points right, -1 points left
        half_h = max(3, diameter // 6)
        arm = half_h
        center = diameter / 2.0
        for offset in (-arm * 0.55, arm * 0.55):
            tip_x = center + offset + direction * arm / 2.0
            back_x = tip_x - direction * arm
            pygame.draw.lines(sprite, chevron_color, False,
                              [(back_x, center - half_h), (tip_x, center), (back_x, center + half_h)], 3)

        self._sidebar_toggle_sprites[key] = sprite
        return sprite

    def _draw_sidebar_order_badge(self):
        """Red order-count badge on the Action Queue bookmark (panel collapsed).

        Counts only the local player's orders: the badge says "you have orders
        queued", so other players' (AI or remote) orders must not inflate it.
        Sits on the tab's outer edge near its top, clear of the rotated label.
        """
        tab_rect = (self.sidebar_tab_buttons or {}).get('action_queue')
        if tab_rect is None:
            return
        local_player = self.get_local_player()
        order_count = sum(1 for order in self.game_state.movement_orders
                          if order.player == local_player)
        if order_count <= 0:
            return
        self._draw_tab_badge(tab_rect, order_count, (200, 50, 50), WHITE, WHITE)

    def _draw_tab_badge(self, tab_rect, count, fill, rim, text_color):
        """Count badge on a bookmark's outer edge near its top, clear of the label.

        A circle for one digit, a pill for more ("99+" caps it). Shared by the Action
        Queue order badge (red) and the unread badges (gold).
        """
        label = str(count) if count < 100 else "99+"
        text = self.sidebar_widgets.text(label, 'small_bold', text_color)
        radius = 10
        width = max(2 * radius, text.get_width() + 10)
        rect = pygame.Rect(0, 0, width, 2 * radius)
        rect.center = (tab_rect.x, tab_rect.y + 12)
        pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        pygame.draw.rect(self.screen, rim, rect, 2, border_radius=radius)
        self.screen.blit(text, text.get_rect(center=rect.center))

    def _sidebar_unread_totals(self):
        """Countable items per badge tab: {'chat': n, 'action_log': n}.

        Chat: visible messages from OTHER players (team chat filtered as in the tab).
        Action Log: visible top-level entries in BADGE_CATEGORIES, from a log model of
        its own (same privacy rules as the tab). Both are recomputed only when their
        message list grows - a frame with no new message costs two length checks.
        """
        from rendering.action_log_model import ActionLogModel, BADGE_CATEGORIES
        gs = self.game_state
        cache = self._unread_cache
        viewer = self.get_local_player()
        chat_key = (id(gs.chat_messages), len(gs.chat_messages), viewer)
        if cache.get('chat_key') != chat_key:
            cache['chat_key'] = chat_key
            # Format: (timestamp, player_id, message[, channel]) - index access
            cache['chat'] = sum(1 for m in gs.get_visible_chat_messages(viewer) if m[1] != viewer)
        log_key = (id(gs.messages), len(gs.messages), viewer)
        if cache.get('log_key') != log_key:
            cache['log_key'] = log_key
            model = cache.setdefault('log_model', ActionLogModel())
            names = [gs.get_player_name(i) for i in range(gs.num_players)]
            if model.update(gs.messages, viewer, names, BADGE_CATEGORIES) is not None:
                cache['action_log'] = sum(1 for r in model.rows
                                          if r.kind in ('entry', 'banner', 'victory') and r.indent == 0)
            cache.setdefault('action_log', 0)
        return {'chat': cache['chat'], 'action_log': cache['action_log']}

    def _draw_sidebar_unread_badges(self, layout):
        """Gold unread counts on the Chat / Action Log bookmarks.

        The open tab counts as read (its count is marked seen every frame it shows);
        a badge appears on a closed tab - or any tab while the panel is collapsed -
        when new items arrived since.
        """
        totals = self._sidebar_unread_totals()
        seen = self.sidebar_seen
        open_tab = self.game_state.active_sidebar_tab if layout.panel_visible and self.game_state.sidebar_expanded else None
        for tab_id, total in totals.items():
            if seen.get(tab_id) is None or tab_id == open_tab or total < seen[tab_id]:
                seen[tab_id] = total
                continue
            unread = total - seen[tab_id]
            tab_rect = (self.sidebar_tab_buttons or {}).get(tab_id)
            if unread > 0 and tab_rect is not None:
                self._draw_tab_badge(tab_rect, unread, (214, 168, 64), (255, 236, 180), (40, 24, 8))

    def _handle_sidebar_hotkey(self):
        """F2: collapse / expand the sidebar, unless something modal is open.

        Returns:
            bool: True if the sidebar toggled.
        """
        if (self.chat_input_active or self.game_menu_visible or self.options_menu_visible
                or self.save_dialog_active or self.players_window_visible
                or self.enhanced_battle_ui is not None or self.battle_popup_visible
                or self.battle_report_detail_ui is not None
                or getattr(self, 'alliance_choice_popup_visible', False)
                or self.victory_sequence_active
                or self.game_state is None or self.game_state.phase == 'ended'):
            return False
        return self.toggle_sidebar()

    def draw_territory_hover_tooltip(self, mouse_pos):
        """Draw comprehensive tooltip when hovering over a territory (Phase 2: Using helper)"""
        # Check if tooltips are enabled
        if not self.tooltips_enabled:
            return
        
        if not self.show_tooltip_territory:
            return
        
        territory = self.show_tooltip_territory
        
        # Gather data
        owner = self.game_state.territory_owners.get(territory, -1)
        # IMPORTANT: Use get_territory_total_armies to include ALL garrisons (owner + allies)
        armies = self.game_state.get_territory_total_armies(territory)
        
        # Calculate combat power (armies + Keep/Fortress bonus)
        keep_bonus = 0
        # Fortress territories get innate +2 defense
        if map_data.is_fortress_territory(territory):
            keep_bonus = 2
        if territory in self.game_state.buildings:
            if any(building == 'Keep' for building in self.game_state.buildings[territory].values()):
                keep_bonus = 2
        
        # Count buildings by type (filter out None values)
        building_counts = {}
        if territory in self.game_state.buildings:
            for building_type in self.game_state.buildings[territory].values():
                if building_type is not None:
                    building_counts[building_type] = building_counts.get(building_type, 0) + 1
        
        # Count empty plots
        total_plots = len(self.scaled_plots.get(territory, []))
        used_plots = len(self.game_state.buildings.get(territory, {}))
        if territory in self.game_state.under_construction:
            used_plots += len(self.game_state.under_construction[territory])
        empty_plots = total_plots - used_plots
        
        # Build tooltip lines
        lines = []

        # Territory name - use display name for campaign mission territory renaming
        display_territory = map_data.get_display_name(territory)
        lines.append(("normal", display_territory, BLACK))
        
        # Owner
        if owner == -1:
            lines.append(("normal", "Owner: Neutral", GRAY))
        else:
            owner_color = self.game_state.get_player_color(owner)
            owner_name = self.game_state.get_player_name(owner)
            lines.append(("normal", f"Owner: {owner_name}", owner_color))
        
        # Combat Power — label source of defense bonus (Fortress vs Keep)
        if keep_bonus > 0:
            defense_source = "Fortress" if map_data.is_fortress_territory(territory) else "Keep"
            lines.append(("normal", f"Combat Power: {armies} + {keep_bonus} ({defense_source})", (150, 50, 50)))
        else:
            lines.append(("normal", f"Combat Power: {armies}", BLACK))
        
        # Unit composition breakdown
        if armies > 0:
            composition = self.game_state.get_unit_composition(territory)
            if composition:
                for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain']:
                    if unit_type in composition and composition[unit_type] > 0:
                        count = composition[unit_type]
                        battalion_name = f"{unit_type} Battalion" if count == 1 else f"{unit_type} Battalions"
                        lines.append(("small", f"  {battalion_name}: {count}", (80, 80, 80)))
        
        # Buildings
        if building_counts:
            building_parts = []
            for building_type, count in sorted(building_counts.items()):
                if count > 1:
                    building_parts.append(f"{count} {building_type}s")
                else:
                    building_parts.append(f"1 {building_type}")
            building_text = "Buildings: " + ", ".join(building_parts)
            lines.append(("small", building_text, (50, 100, 50)))
        else:
            lines.append(("small", "Buildings: None", GRAY))
        
        # Available plots
        if total_plots > 0:
            if empty_plots == 0:
                lines.append(("small", "Available: 0 (fully developed)", (100, 100, 100)))
            else:
                plot_word = "plot" if empty_plots == 1 else "plots"
                lines.append(("small", f"Available: {empty_plots} empty {plot_word}", (0, 150, 200)))
        
        # Draw using helper
        tooltip_pos = (mouse_pos[0] + 15, mouse_pos[1] + 15)
        self.draw_tooltip_box(tooltip_pos, lines, 
                             bg_color=(250, 250, 240),
                             border_color=(100, 100, 100),
                             padding=7, line_spacing=0,
                             use_transparency=True)
    
    
    def draw_button_tooltip(self, mouse_pos, button_data):
        """Draw tooltip for UI buttons (training, building, plot) - 33% smaller and follows mouse"""
        # Check if tooltips are enabled
        if not self.tooltips_enabled:
            return

        if not button_data:
            return

        button_type, button_key = button_data

        # Define tooltip colors
        silvery_color = (192, 192, 192)  # Silvery for labels
        bronze_color = (205, 127, 50)     # Bronzish for descriptions
        gold_color = (218, 165, 32)       # Gold for titles
        white_color = (255, 255, 255)     # White for values

        lines = []
        
        if button_type == 'training' or button_type == 'map_training':
            # Training button tooltip (UI or map icon)
            unit_type = button_key
            unit_info = self.game_state.UNIT_TYPES[unit_type]

            # Get counter name in plural form (Captain has no counters)
            counters_name = unit_info['counters']
            if counters_name is None:
                counters_plural = None  # Captain: no counter relationship
            elif counters_name == 'Cavalry':
                counters_plural = 'Cavalry'
            elif counters_name == 'Pikeman':
                counters_plural = 'Pikemen'
            elif counters_name == 'Swordsman':
                counters_plural = 'Swordsmen'
            else:
                counters_plural = counters_name + 's'

            # Keyboard shortcut mapping
            keyboard_shortcuts = {
                'Swordsman': 'S',
                'Archer': 'A',
                'Pikeman': 'P',
                'Cavalry': 'C',
                'Captain': 'T'
            }
            shortcut = keyboard_shortcuts.get(unit_type, '')

            # Get effective cost with discounts applied
            base_cost = unit_info['cost']
            effective_cost = self.game_state.get_effective_cost(unit_type, base_cost, self.game_state.current_player)

            # Build formatted lines with proper styling
            # Order: Title, Cost, Training Time, Effect, Shortcut (Phase 3: title uses bold font)
            lines = [
                [("normal_bold", f"Train {unit_type}", gold_color)],  # Title in gold, SemiBold weight
                [("small_bold", "Cost:", silvery_color), ("small", f" {effective_cost} Gold", white_color)],  # Cost label bold, value normal (with discount)
                [("small_bold", "Training Time:", silvery_color), ("small", " 1 turn", white_color)],  # Training time label bold, value normal
            ]
            # Captain shows army bonus + extended movement instead of counter info
            if counters_plural:
                lines.append([("small_italic", f"Counters {counters_plural}.", bronze_color)])
            else:
                lines.append([("small_italic", "Support unit. Weak in combat, but increases power of", bronze_color)])
                lines.append([("small_italic", "other units in the army by 12% and allows armies to", bronze_color)])
                lines.append([("small_italic", "move across one more territory when reinforcing.", bronze_color)])
                lines.append([("small_italic", "Bonuses do not stack.", bronze_color)])

            if shortcut:
                lines.append([("small_bold", "Shortcut:", silvery_color), ("small", f" {shortcut}", white_color)])
            
        elif button_type == 'building' or button_type == 'map_building':
            # Building button tooltip (UI or map icon)
            building_name = button_key
            building_info = self.game_state.building_types[building_name]

            # Get effective cost with all discounts applied
            building_cost = self.game_state.get_building_cost(building_name, self.game_state.current_player)

            # Build description based on effect
            effect = building_info['effect']
            value = building_info['value']
            if effect == 'income':
                description = f"Generates +{value} Gold/turn."
            elif effect == 'defense':
                if building_name == 'Keep':
                    description = "Defense bonus & trains Heroes. (Limit 1 per territory)"
                else:
                    description = "Provides defense bonus."
            elif effect == 'multiplier':
                description = f"Multiplies territory income x{value}. (Limit 1 per territory)"
            elif effect == 'recruitment':
                description = "Train military units."
            elif effect == 'training':
                description = f"Grants +{value} XP/turn to units. (Limit 1 per territory)"
            else:
                description = str(effect)

            # Get build time from data
            build_time = building_info.get('time', 1)

            # Keyboard shortcut mapping
            keyboard_shortcuts = {
                'Farm': 'F',
                'Mine': 'M',
                'Barracks': 'B',
                'Keep': 'K',
                'Square': 'Q',
                'Training Grounds': 'T'
            }
            shortcut = keyboard_shortcuts.get(building_name, '')

            # Build formatted lines with proper styling
            # Order: Title, Cost, Construction Time, Effect, Shortcut (Phase 3: title uses bold font)
            lines = [
                [("normal_bold", f"Construct {building_name}", gold_color)],  # Title in gold, SemiBold weight
                [("small_bold", "Cost:", silvery_color), ("small", f" {building_cost} Gold", white_color)],  # Cost label bold, value normal (with discount applied)
                [("small_bold", "Construction Time:", silvery_color), ("small", f" {build_time} turn{'s' if build_time > 1 else ''}", white_color)],  # Construction time label bold, value normal
                [("small_italic", description, bronze_color)],  # Effect italic bronze
            ]

            if shortcut:
                lines.append([("small_bold", "Shortcut:", silvery_color), ("small", f" {shortcut}", white_color)])
            
        elif button_type == 'hero_training' or button_type == 'map_hero_training':
            # Hero training button tooltip (UI or map icon)
            hero_type = button_key
            hero_info = self.game_state.HERO_TYPES[hero_type]

            # Get hero cost with Royal Decree discount applied
            hero_cost = hero_info['cost']
            discount_percent = self.game_state.player_royal_decree_discount[self.game_state.current_player]
            if discount_percent > 0:
                hero_cost = int(hero_cost * (100 - discount_percent) / 100)

            # Get hero description from HERO_TYPES
            description_lines = hero_info.get('description', [''])

            # Get abilities text - extract names from ability dicts
            abilities_list = hero_info.get('abilities', [])
            if abilities_list:
                ability_names = [ability.get('name', 'Unknown') for ability in abilities_list]
                abilities_text = ", ".join(ability_names)
            else:
                abilities_text = "None"

            # Keyboard shortcut mapping
            keyboard_shortcuts = {
                'Halon Nextroy': 'H',
                'Aidam Narn': 'A',
                'Erec Silvyr': 'E',
                'Darius Brennhen': 'D',
                'Neil Hévilneu': 'N',
                'Seledra Rennervail': 'S',
                'Evain Nithieln': 'V',
                'Vearen Asford': 'F',
                'Regnus Aevencourne': 'R'
            }
            shortcut = keyboard_shortcuts.get(hero_type, '')

            # Build formatted lines with proper styling (Phase 3: title uses bold font)
            lines = [
                [("normal_bold", f"Train {hero_type}", gold_color)],  # Title in gold, SemiBold weight
            ]

            # Add description lines in italic bronze
            for desc_line in description_lines:
                lines.append([("small_italic", desc_line, bronze_color)])

            # Add the rest of the info
            lines.extend([
                [("small_bold", "Cost:", silvery_color), ("small", f" {hero_cost} Gold", white_color)],  # Cost label bold, value normal (with discount applied)
                [("small_bold", "Abilities:", silvery_color), ("small", f" {abilities_text}", white_color)],  # Abilities label bold, value normal
                [("small_bold", "Training Time:", silvery_color), ("small", f" {hero_info['training_time']} turn{'s' if hero_info['training_time'] > 1 else ''}", white_color)],  # Training time label bold, value normal
            ])

            if shortcut:
                lines.append([("small_bold", "Shortcut:", silvery_color), ("small", f" {shortcut}", white_color)])

        elif button_type == 'plot':
            # Plot tooltip - check if it has building info
            if button_key:
                # Finished building on plot - show building name + veterancy info
                if isinstance(button_key, tuple) and len(button_key) == 3:
                    # Farm/Mine with veterancy data: (building_name, level, xp)
                    bldg_name, bldg_level, bldg_xp = button_key
                    lines = [[("small", bldg_name, white_color)]]
                    if bldg_level > 0 or bldg_xp > 0:
                        if bldg_level < self.game_state.MAX_LEVEL:
                            next_t = self.game_state.LEVEL_XP_CUMULATIVE[bldg_level]
                            lines.append([("small", f"Level {bldg_level} | XP: {bldg_xp}/{next_t}", gold_color)])
                        else:
                            lines.append([("small", f"Level {bldg_level} (MAX)", gold_color)])
                        bonus_pct = int(bldg_level * self.game_state.BUILDING_LEVEL_INCOME_BONUS * 100)
                        if bonus_pct > 0:
                            lines.append([("small", f"+{bonus_pct}% income bonus", (150, 200, 150))])
                else:
                    lines = [[("small", button_key, white_color)]]
            else:
                # Empty plot - show available building plot message
                lines = [[("small", "Available building plot", white_color)]]

        elif button_type == 'castle':
            # Castle upgrade/upgraded tooltip (Phase 3: titles use bold font)
            if button_key == 'castle_upgrade':
                # Upgrade to Castle button
                lines = [
                    [("normal_bold", "Upgrade to Castle", gold_color)],  # Title in gold, SemiBold weight
                    [("small_bold", "Cost:", silvery_color), ("small", " 150 Gold", white_color)],
                    [("small_bold", "Upgrade Time:", silvery_color), ("small", " 2 turns", white_color)],
                    [("small_italic", "Allows researching of higher tier technologies.", bronze_color)],
                ]
            elif button_key == 'castle_upgraded':
                # Already upgraded Castle
                lines = [
                    [("normal_bold", "Castle (Upgraded)", gold_color)],  # Title in gold, SemiBold weight
                    [("small_italic", "This Keep has been upgraded to a Castle.", bronze_color)],
                    [("small_italic", "Unlocks higher tier technology research.", bronze_color)],
                ]

        elif button_type == 'army_unit_tooltip':
            # Army unit tooltip (unit type, status, and veterancy)
            if len(button_key) >= 4:
                unit_type, unit_status, u_level, u_xp = button_key
            else:
                unit_type, unit_status = button_key[:2]
                u_level, u_xp = 0, 0
            lines = [
                [("small", unit_type, white_color)],
                [("small", f"Status: {unit_status}", bronze_color)],
            ]
            if u_level > 0 or u_xp > 0:
                # Show level and XP progress
                if u_level < self.game_state.MAX_LEVEL:
                    next_threshold = self.game_state.LEVEL_XP_CUMULATIVE[u_level]
                    lines.append([("small", f"Level {u_level} | XP: {u_xp}/{next_threshold}", gold_color)])
                else:
                    lines.append([("small", f"Level {u_level} (MAX)", gold_color)])
                # Show strength bonus
                bonus_pct = int(u_level * self.game_state.UNIT_LEVEL_STRENGTH_BONUS * 100)
                if bonus_pct > 0:
                    lines.append([("small", f"+{bonus_pct}% strength", (150, 200, 150))])

        elif button_type == 'resource_slot':
            # Resource slot tooltips (top panel stats)
            # Purpose: Explain what each stat means without highlighting the slot
            slot_name = button_key
            if slot_name == 'taxation':
                lines = [
                    [("normal_bold", "Taxation", gold_color)],
                    [("small", "Current taxation percentage.", white_color)],
                    [("small", "Taxation removes a percentage of", white_color)],
                    [("small", "unused Gold at the end of each turn.", white_color)]
                ]
            elif slot_name == 'command_limit':
                lines = [
                    [("normal_bold", "Command Limit", gold_color)],
                    [("small", "Current Command limit.", white_color)],
                    [("small", "Each unit trained occupies one", white_color)],
                    [("small", "Command point. You cannot train", white_color)],
                    [("small", "units if it would exceed your", white_color)],
                    [("small", "Command limit.", white_color)]
                ]
            elif slot_name == 'gold':
                lines = [
                    [("normal_bold", "Gold", gold_color)],
                    [("small", "Current amount of Gold available.", white_color)]
                ]
            elif slot_name == 'income':
                lines = [
                    [("normal_bold", "Income", gold_color)],
                    [("small", "Current Gold income per turn.", white_color)]
                ]
            else:
                lines = [[("small", "Unknown resource slot", white_color)]]

        elif button_type == 'territorial_bonuses':
            # Territorial Bonuses tooltip - show summed bonuses from owned territories
            # Always show local player's bonuses (not current turn player's bonuses)
            if self.multiplayer_mode:
                # Multiplayer: Use local_player_index
                player_to_show = self.local_player_index if self.local_player_index is not None else 0
            else:
                # Single-player: Find the human player (non-AI player)
                player_to_show = 0  # Default to player 0
                for i in range(self.game_state.num_players):
                    if not self.game_state.player_is_ai[i]:
                        player_to_show = i
                        break
            bonuses = self.game_state.calculate_player_territorial_bonuses(player_to_show)

            # Title
            lines = [[("normal_bold", "Territorial Bonuses", gold_color)]]

            if not bonuses:
                # No bonuses active
                lines.append([("small_italic", "No bonuses active", bronze_color)])
            else:
                # Show each active bonus (sorted alphabetically by display name)
                sorted_bonuses = sorted(bonuses.items(), key=lambda x: self.game_state.BONUS_TYPES[x[0]]['display'])
                for bonus_type, total_value in sorted_bonuses:
                    bonus_info = self.game_state.BONUS_TYPES[bonus_type]
                    display = bonus_info['display']
                    formatted = bonus_info['format'].format(total_value)
                    lines.append([("small_bold", f"{formatted} {display}", white_color)])

        elif button_type == 'resolve_all_battles':
            # "Resolve Remaining Battles" button tooltip
            lines = [
                [("normal_bold", "Resolve Remaining Battles", gold_color)],
                [("small", "Resolve all remaining battles that are", white_color)],
                [("small", "pending your action. These battles will", white_color)],
                [("small", "provide no battle reports.", white_color)],
            ]

        elif button_type == 'territory_lore':
            # Territory preview image tooltip — shows lore/description
            territory_name = button_key
            display_name = map_data.get_display_name(territory_name)
            lore_text = map_data.get_territory_lore(territory_name)

            lines = [[("normal_bold", display_name, gold_color)]]

            if lore_text:
                # Wrap lore text to fit tooltip width
                lore_lines = self.helpers.wrap_text_smart(lore_text, self.small_font, 300)
                for line in lore_lines:
                    lines.append([("small", line, bronze_color)])
            else:
                lines.append([("small_italic", "No lore available for this territory.", bronze_color)])

        if not lines:
            return

        # Draw tooltip using formatted lines (lines are already formatted with font styles and colors)
        tooltip_pos = (mouse_pos[0] + 15, mouse_pos[1] + 15)
        self.draw_tooltip_box(tooltip_pos, lines,
                             bg_color=(50, 50, 50),
                             border_color=(200, 200, 200),
                             padding=7, line_spacing=4)

    def draw_ability_tooltip(self, mouse_pos, hero_name, ability_index, player=None):
        """Draw tooltip for hero ability buttons.

        `player` whose cooldown / silence to show: defaults to the acting player (bottom
        bar); the sidebar Heroes tab passes the local player.
        """
        # Check if tooltips are enabled
        if not self.tooltips_enabled:
            return

        # Get hero info
        current_player = self.game_state.current_player if player is None else player
        if hero_name not in self.game_state.HERO_TYPES:
            return

        hero_info = self.game_state.HERO_TYPES[hero_name]
        abilities = hero_info.get('abilities', [])

        if ability_index >= len(abilities):
            return

        ability = abilities[ability_index]

        # Define tooltip colors
        silvery_color = (192, 192, 192)  # Silvery for labels
        bronze_color = (205, 127, 50)     # Bronzish for descriptions
        gold_color = (218, 165, 32)       # Gold for titles
        white_color = (255, 255, 255)     # White for values
        red_color = (255, 100, 100)       # Red for warnings

        # Build tooltip lines
        lines = []

        # Ability name (title)
        ability_name = ability.get('name', 'Unknown Ability')
        lines.append([("normal", ability_name, gold_color)])

        # Ability type (Active/Passive)
        ability_type = ability.get('type', 'active')
        if ability_type == 'passive':
            lines.append([("small_bold", "Type:", silvery_color), ("small", " Passive", white_color)])
        else:
            # Active ability - show cooldown
            base_cooldown = ability.get('cooldown', 0)
            lines.append([("small_bold", "Type:", silvery_color), ("small", " Active", white_color)])
            lines.append([("small_bold", "Cooldown:", silvery_color), ("small", f" {base_cooldown} turn{'s' if base_cooldown != 1 else ''}", white_color)])

            # Check current cooldown status
            cooldown_remaining = 0
            if hero_name in self.game_state.hero_ability_cooldowns.get(current_player, {}):
                cooldown_remaining = self.game_state.hero_ability_cooldowns[current_player][hero_name].get(ability_name, 0)

            if cooldown_remaining > 0:
                lines.append([("small_bold", "Ready in:", red_color), ("small", f" {cooldown_remaining} turn{'s' if cooldown_remaining != 1 else ''}", red_color)])

            # Check if silenced
            is_silenced = self.game_state.hero_silence_status.get(current_player, 0) > 0
            if is_silenced:
                silence_turns = self.game_state.hero_silence_status[current_player]
                lines.append([("small_italic", f"SILENCED ({silence_turns} turn{'s' if silence_turns != 1 else ''})", red_color)])

        # Description (italic bronze)
        description = ability.get('description', 'No description available.')

        # Dynamic description for Extensive Connections
        if ability_name == 'Extensive Connections':
            # Count territories owned by current player
            territory_count = sum(1 for owner in self.game_state.territory_owners.values() if owner == current_player)
            bonus_gold = territory_count * 4
            description = f"Gain 4 Gold per territory owned at the end of your turn. (Currently: {bonus_gold} Gold)"

        # Split description into multiple lines if too long (wrap at ~40 characters)
        words = description.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= 40:
                current_line += word + " "
            else:
                if current_line:
                    lines.append([("small_italic", current_line.strip(), bronze_color)])
                current_line = word + " "
        if current_line:
            lines.append([("small_italic", current_line.strip(), bronze_color)])

        if not lines:
            return

        # Draw tooltip
        tooltip_pos = (mouse_pos[0] + 15, mouse_pos[1] + 15)
        self.draw_tooltip_box(tooltip_pos, lines,
                             bg_color=(50, 50, 50),
                             border_color=(200, 200, 200),
                             padding=7, line_spacing=4)

    def clear_button_tooltip(self):
        """Clear button tooltip state (call after actions)"""
        self.hover_target_button = None
        self.show_tooltip_button = None
        self.hover_start_time_button = None

    def clear_ability_targeting(self):
        """Clear ability targeting mode (call when deselecting hero or ending turn)"""
        self.ability_targeting_active = False
        self.ability_targeting_hero = None
        self.ability_targeting_ability_index = None
        self.ability_targeting_ability_name = None

    def clear_ui_selections(self):
        """Clear all UI selections (called when turn changes)"""
        self.selected_hero = None
        self.selected_plot = None
        self.selected_barracks = None
        self.selected_keep = None
        self.selected_territory_info = None
        self.show_army_composition = False
        self.army_composition_territory = None
        self.army_composition_player = None  # Clear garrison player context
        self.selected_army_units = []
        self.clear_ability_targeting()

    def draw_army_hover_tooltip(self, mouse_pos, territory):
        """Draw army-specific tooltip when hovering over an army circle"""
        # Check if tooltips are enabled
        if not self.tooltips_enabled:
            return
        
        if not territory:
            return
        
        # Gather army data
        owner = self.game_state.territory_owners.get(territory, -1)
        total_armies = self.game_state.get_territory_total_armies(territory)

        # Build tooltip lines
        lines = []

        # Line 1: Territory name - use display name for campaign mission territory renaming
        display_territory = map_data.get_display_name(territory)
        lines.append(("normal", f"Army in {display_territory}", BLACK))

        # Line 2: Owner
        if owner >= 0:
            owner_color = self.game_state.get_player_color(owner)
            owner_name = self.game_state.get_player_name(owner)
            lines.append(("normal", f"Owner: {owner_name}", owner_color))

        # Line 3: Total forces
        lines.append(("normal", f"Total Forces: {total_armies}", BLACK))

        # Check if there are multiple garrisons (allied reinforcements)
        garrisons = self.game_state.territory_garrisons.get(territory, {})
        if len(garrisons) > 1:
            # Show breakdown by garrison
            lines.append(("small", "", BLACK))  # Blank line
            lines.append(("normal", "Garrison Breakdown:", (100, 100, 100)))

            for player_index in sorted(garrisons.keys()):
                garrison = garrisons[player_index]
                garrison_total = garrison.get('unmoved', 0) + garrison.get('moved', 0)
                garrison_unmoved = garrison.get('unmoved', 0)

                if garrison_total > 0:
                    player_color = self.game_state.get_player_color(player_index)

                    # Get player name
                    player_name = self.game_state.player_names[player_index]
                    if not player_name:
                        player_name = f"Player {player_index + 1}"

                    # Determine relationship to owner
                    if player_index == owner:
                        relationship = "Owner"
                    else:
                        # Check if player is allied with owner based on team
                        owner_team = self.game_state.player_teams[owner] if owner >= 0 else -1
                        player_team = self.game_state.player_teams[player_index]
                        if owner_team >= 0 and owner_team == player_team:
                            relationship = "Ally"
                        else:
                            relationship = "Enemy"

                    label = f"  {player_name} ({relationship}): {garrison_total}"

                    lines.append(("small", label, player_color))

                    # Show unmoved count if player has this garrison
                    if player_index == self.game_state.current_player and garrison_unmoved > 0:
                        lines.append(("small", f"    Available: {garrison_unmoved}", (0, 150, 0)))
        else:
            # Single garrison - show composition
            # Line 3.5: Unit composition breakdown (if armies exist)
            if total_armies > 0:
                composition = self.game_state.get_unit_composition(territory)
                if composition:
                    # Sort by unit type for consistent display
                    for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain']:
                        if unit_type in composition and composition[unit_type] > 0:
                            count = composition[unit_type]
                            # Use Battalion terminology
                            battalion_name = f"{unit_type} Battalion" if count == 1 else f"{unit_type} Battalions"
                            lines.append(("small", f"  {battalion_name}: {count}", (80, 80, 80)))

            # Line 4: Available for commands (only for current player's garrison)
            # IMPORTANT: Get current player's garrison specifically, not owner's legacy array
            garrison = self.game_state.territory_garrisons.get(territory, {}).get(self.game_state.current_player)
            unmoved_armies = garrison.get('unmoved', 0) if garrison else 0
            if unmoved_armies > 0:
                lines.append(("normal", f"Available for Commands: {unmoved_armies}", (0, 150, 0)))
        
        # Line 5: Check for merge orders
        for order in self.game_state.movement_orders:
            if order.from_territory == territory:
                # This army has a move order
                dest_owner = self.game_state.territory_owners.get(order.to_territory, -1)

                # Check if destination is friendly (owned by player OR ally)
                is_friendly = (dest_owner == order.player or
                             (dest_owner >= 0 and self.game_state.are_allies(order.player, dest_owner)))

                if is_friendly:
                    # Merging with own territory or reinforcing ally
                    if dest_owner == order.player:
                        lines.append(("normal", f"-> Merging with {order.to_territory}", (0, 180, 180)))
                    else:
                        lines.append(("normal", f"-> Reinforcing {order.to_territory}", (0, 180, 100)))
                else:
                    # Attacking
                    lines.append(("normal", f"-> Attacking {order.to_territory}", (180, 0, 0)))
        
        # Draw using helper (Phase 2)
        tooltip_pos = (mouse_pos[0] + 15, mouse_pos[1] + 15)
        self.draw_tooltip_box(tooltip_pos, lines,
                             bg_color=(250, 250, 240),
                             border_color=(100, 100, 100),
                             padding=7, line_spacing=0,
                             use_transparency=True)
    
    def draw_territory_info_panel(self):
        """Draw territory information and building plots in bottom UI"""
        territory = self.selected_territory_info

        # Get territory info
        owner = self.game_state.territory_owners.get(territory, -1)
        # IMPORTANT: Use get_territory_total_armies to include ALL garrisons (owner + allies)
        armies = self.game_state.get_territory_total_armies(territory)
        
        # Calculate income for this territory (with multiplier support)
        base_income = map_data.get_territory_income(territory)
        building_bonus = 0
        multiplier = 1.0

        if territory in self.game_state.buildings:
            for plot_index, building_type in self.game_state.buildings[territory].items():
                if building_type is None:
                    continue

                building_info = self.game_state.building_types.get(building_type)
                if building_info:
                    effect = building_info['effect']
                    value = building_info['value']

                    if effect == 'income':
                        building_bonus += value
                    elif effect == 'multiplier':
                        multiplier = value

        # Apply formula: (base + bonuses) * multiplier
        total_income = int((base_income + building_bonus) * multiplier)
        
        # Get actual plot count for this territory
        plot_count = len(self.scaled_plots.get(territory, []))

        # Panel starting position (left side) - dynamic (21.875% of width)
        panel_x = int(WINDOW_WIDTH * 0.21875)  # Was 350 at 1600px width
        panel_y = BOTTOM_UI_Y + 30

        # Draw title (Phase 2: Use SemiBold for territory name header)
        # Smart wrapping for long territory names (e.g., "South Affrancia")
        # Use display name for campaign mission territory renaming
        display_territory = map_data.get_display_name(territory)
        max_title_width = 200  # Maximum width for territory name before wrapping
        title_lines = self.helpers.wrap_text_smart(display_territory, self.large_font_bold, max_title_width)

        for line in title_lines:
            title_text = self._get_cached_text(line, self.large_font_bold, BROWN_TEXT_HEADING)
            self.screen.blit(title_text, (panel_x, panel_y))
            panel_y += 28  # Line height for wrapped titles

        panel_y += 7  # Extra spacing after title

        # Draw owner (with smart wrapping for long AI names like "Empire of X")
        if owner == -1:
            owner_text = self._get_cached_text("Owner: Neutral", self.font, BROWN_TEXT_PRIMARY)
            self.screen.blit(owner_text, (panel_x, panel_y))
            panel_y += 28
        else:
            owner_color = self.game_state.get_player_color(owner)
            owner_name = self.game_state.get_player_name(owner)
            full_owner_text = f"Owner: {owner_name}"

            # Smart wrapping for long owner names
            max_owner_width = 200  # Maximum width before wrapping
            owner_lines = self.helpers.wrap_text_smart(full_owner_text, self.font, max_owner_width)

            for line in owner_lines:
                owner_text = self._get_cached_text(line, self.font, owner_color)
                self.screen.blit(owner_text, (panel_x, panel_y))
                panel_y += 22  # Line height for wrapped owner

            panel_y += 6  # Extra spacing after owner

        # Draw income
        income_text = self._get_cached_text(f"Income: +{total_income}G/turn", self.small_font, BROWN_GOLD)
        self.screen.blit(income_text, (panel_x, panel_y))
        panel_y += 22  # Move down for next line

        # Draw territorial bonus (if territory has one)
        bonus_type = map_data.get_territory_bonus(territory)
        if bonus_type and bonus_type in self.game_state.BONUS_TYPES:
            bonus_info = self.game_state.BONUS_TYPES[bonus_type]
            # Format: "+3% Income" or "-5% Unit Cost"
            formatted_bonus = f"{bonus_info['format'].format(bonus_info['value'])} {bonus_info['display']}"

            # Wrap text if too long (max 200px width before wrapping)
            max_bonus_width = 200
            bonus_lines = self.helpers.wrap_text_smart(f"Bonus: {formatted_bonus}", self.small_font, max_bonus_width)

            for line in bonus_lines:
                bonus_text = self._get_cached_text(line, self.small_font, WHITE)
                self.screen.blit(bonus_text, (panel_x, panel_y))
                panel_y += 20  # Line height for wrapped bonus

        # Draw fortress defense indicator (if territory is a fortress)
        if map_data.is_fortress_territory(territory):
            fortress_text = self._get_cached_text("Fortress (+2 Defense)", self.small_font, (150, 50, 50))
            self.screen.blit(fortress_text, (panel_x, panel_y))
            panel_y += 20

        # Draw first vertical dividing line (between basic info and building plots)
        divider_x = panel_x + 220
        self.draw_separator(divider_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)
        
        # Draw building plots on the right side of divider
        if owner != -1 and plot_count > 0:  # Only show plots for owned territories with plots
            plots_x = divider_x + 20
            plots_y = BOTTOM_UI_Y + 30
            
            # PERFORMANCE: Use cached static text
            plots_title = self._get_cached_text("Building Plots:", self.font_bold, BROWN_TEXT_HEADING)
            self.screen.blit(plots_title, (plots_x, plots_y))
            plots_y += 30
            
            # Draw plots in a grid (as circles)
            plot_size = 67  # 33% smaller than 100 (was 100, now ~67)
            plot_spacing = 15  # Adjusted spacing
            plots_per_row = 5  # Adjusted for new size

            # Clear plot button storage
            self.territory_info_plot_buttons = []

            for plot_index in range(plot_count):  # Use actual plot count
                row = plot_index // plots_per_row
                col = plot_index % plots_per_row

                plot_x = plots_x + col * (plot_size + plot_spacing)
                plot_y = plots_y + row * (plot_size + plot_spacing)

                # Calculate circle center and radius
                plot_radius = plot_size // 2
                plot_center_x = plot_x + plot_radius
                plot_center_y = plot_y + plot_radius
                plot_rect = pygame.Rect(plot_x, plot_y, plot_size, plot_size)

                # Check hover (circular collision detection)
                is_hovering = False
                if self.mouse_pos:
                    mouse_x, mouse_y = self.mouse_pos
                    distance = ((mouse_x - plot_center_x) ** 2 + (mouse_y - plot_center_y) ** 2) ** 0.5
                    if distance <= plot_radius:
                        is_hovering = True

                # Check click flash
                is_clicking = (self.clicked_element and
                              self.clicked_element[0] == 'plot' and
                              self.clicked_element[1] == (territory, plot_index))
                
                # Check plot state
                building = None
                under_construction_data = None
                
                if territory in self.game_state.buildings:
                    building = self.game_state.buildings[territory].get(plot_index)
                
                if territory in self.game_state.under_construction:
                    under_construction_data = self.game_state.under_construction[territory].get(plot_index)
                
                # Draw plot based on state
                if building:
                    # Completed building - draw icon with CircleBorder
                    if building in self.building_icons and self.building_icons[building]:
                        building_icon = self.building_icons[building]

                        # C2 fix: Use cached scaling for building icons on map
                        icon_size = int(plot_radius * 1.6)
                        base_icon = self._get_cached_scaled_surface(
                            building_icon, f'bldg_{building}', icon_size, icon_size)
                        scaled_icon = self._apply_icon_overlay(
                            base_icon, is_clicking, is_hovering)

                        icon_rect = scaled_icon.get_rect(center=(plot_center_x, plot_center_y))
                        self.screen.blit(scaled_icon, icon_rect)

                        # C2 fix: Use cached border scaling
                        if self.circle_border:
                            scaled_border = self._get_cached_scaled_surface(
                                self.circle_border, 'circle_border', plot_size, plot_size)
                            border_rect = scaled_border.get_rect(center=(plot_center_x, plot_center_y))
                            self.screen.blit(scaled_border, border_rect)

                        # Draw selection highlight on top if selected
                        is_selected_plot = self.selected_plot and self.selected_plot == (territory, plot_index)
                        is_selected_barracks = (self.selected_barracks and
                                               self.selected_barracks == (territory, plot_index) and
                                               building == 'Barracks')
                        if is_selected_plot or is_selected_barracks:
                            pygame.draw.circle(self.screen, (255, 215, 0), (plot_center_x, plot_center_y), plot_radius, 4)
                    else:
                        # Fallback to circle with letter if icon not available
                        circle_color = (150, 150, 150)
                        if is_clicking:
                            circle_color = brighten_color(circle_color, 0.4)
                        elif is_hovering:
                            circle_color = lighten_color(circle_color, 0.2)
                        pygame.draw.circle(self.screen, circle_color, (plot_center_x, plot_center_y), plot_radius)

                        is_selected_plot = self.selected_plot and self.selected_plot == (territory, plot_index)
                        is_selected_barracks = (self.selected_barracks and
                                               self.selected_barracks == (territory, plot_index) and
                                               building == 'Barracks')
                        if is_selected_plot or is_selected_barracks:
                            pygame.draw.circle(self.screen, (255, 215, 0), (plot_center_x, plot_center_y), plot_radius, 4)
                        else:
                            pygame.draw.circle(self.screen, BLACK, (plot_center_x, plot_center_y), plot_radius, 2)

                        if building == 'Farm':
                            icon = self._get_cached_text("F", self.font, (50, 150, 50))
                        elif building == 'Mine':
                            icon = self._get_cached_text("M", self.font, (100, 100, 150))
                        elif building == 'Keep':
                            display_letter, _ = self.game_state.get_keep_display_info(territory, plot_index)
                            icon = self._get_cached_text(display_letter, self.font, (150, 50, 50))
                        else:
                            icon = self._get_cached_text(building[0], self.font, BLACK)
                        icon_rect = icon.get_rect(center=(plot_center_x, plot_center_y))
                        self.screen.blit(icon, icon_rect)

                    # --- Veterancy: Draw XP bar and level shields OVERLAID on Farm/Mine icon ---
                    if building in ('Farm', 'Mine'):
                        bldg_data = self.game_state.get_building_xp_data(territory, plot_index)
                        bldg_level = bldg_data['level']
                        bldg_xp = bldg_data['xp']

                        # XP bar overlaid inside bottom edge of plot circle
                        bar_inset_x = self.scale(6)  # Horizontal inset from circle edge
                        bar_inset_y = self.scale(6)  # Vertical inset from bottom edge
                        bar_h = self.scale(4)
                        bar_w = plot_size - bar_inset_x * 2
                        bar_x = plot_x + bar_inset_x
                        bar_y = plot_y + plot_size - bar_h - bar_inset_y

                        # Calculate fill ratio
                        if bldg_level < self.game_state.MAX_LEVEL:
                            prev_t = self.game_state.LEVEL_XP_CUMULATIVE[bldg_level - 1] if bldg_level > 0 else 0
                            next_t = self.game_state.LEVEL_XP_CUMULATIVE[bldg_level]
                            xp_in_level = bldg_xp - prev_t
                            xp_needed = next_t - prev_t
                            fill = max(0.0, min(1.0, xp_in_level / xp_needed)) if xp_needed > 0 else 0.0
                        else:
                            fill = 1.0

                        # Draw bar bg + fill (brass-colored like unit XP bars)
                        pygame.draw.rect(self.screen, (60, 50, 40), (bar_x, bar_y, bar_w, bar_h))
                        fill_px = int(bar_w * fill)
                        if fill_px > 0:
                            pygame.draw.rect(self.screen, (185, 155, 80), (bar_x, bar_y, fill_px, bar_h))

                        # Level shields overlaid at top edge of plot circle
                        if bldg_level > 0 and self.level_shield_icon:
                            s_size = self.scale(8)  # Slightly smaller to fit inside circle
                            cached_s = self._get_cached_scaled_surface(
                                self.level_shield_icon, 'level_shield_bldg', s_size, s_size)
                            total_w = bldg_level * s_size
                            start_x = plot_center_x - total_w // 2
                            sy = plot_y + self.scale(3)  # Inset from top edge
                            for lv in range(bldg_level):
                                sx = start_x + lv * s_size
                                self.screen.blit(cached_s, (sx, sy))

                elif under_construction_data:
                    # Under construction - draw icon with CircleBorder
                    # under_construction_data is a tuple: (building_type, turns_remaining, cost)
                    building_type = under_construction_data[0]
                    turns_remaining = under_construction_data[1]

                    if building_type in self.building_icons and self.building_icons[building_type]:
                        building_icon = self.building_icons[building_type]

                        # C2 fix: Use cached scaling for under-construction building icons
                        icon_size = int(plot_radius * 1.6)
                        base_icon = self._get_cached_scaled_surface(
                            building_icon, f'bldg_{building_type}', icon_size, icon_size)
                        scaled_icon = self._apply_icon_overlay(
                            base_icon, is_clicking, is_hovering)

                        # Apply slight transparency to indicate construction
                        # Bug 2 fix: copy before set_alpha to avoid corrupting the cached surface
                        scaled_icon = scaled_icon.copy()
                        scaled_icon.set_alpha(180)

                        icon_rect = scaled_icon.get_rect(center=(plot_center_x, plot_center_y))
                        self.screen.blit(scaled_icon, icon_rect)

                        # C2 fix: Use cached border scaling
                        if self.circle_border:
                            scaled_border = self._get_cached_scaled_surface(
                                self.circle_border, 'circle_border', plot_size, plot_size)
                            border_rect = scaled_border.get_rect(center=(plot_center_x, plot_center_y))
                            self.screen.blit(scaled_border, border_rect)

                        # Draw selection highlight on top if selected
                        if self.selected_plot and self.selected_plot == (territory, plot_index):
                            pygame.draw.circle(self.screen, (255, 215, 0), (plot_center_x, plot_center_y), plot_radius, 4)
                    else:
                        # Fallback to circle with text if icon not available
                        circle_color = (200, 200, 100)
                        if is_clicking:
                            circle_color = brighten_color(circle_color, 0.4)
                        elif is_hovering:
                            circle_color = lighten_color(circle_color, 0.2)
                        pygame.draw.circle(self.screen, circle_color, (plot_center_x, plot_center_y), plot_radius)

                        if self.selected_plot and self.selected_plot == (territory, plot_index):
                            pygame.draw.circle(self.screen, (255, 215, 0), (plot_center_x, plot_center_y), plot_radius, 4)
                        else:
                            pygame.draw.circle(self.screen, BLACK, (plot_center_x, plot_center_y), plot_radius, 2)

                        progress_text = self._get_cached_text(f"{turns_remaining}", self.font, BLACK)
                        progress_rect = progress_text.get_rect(center=(plot_center_x, plot_center_y))
                        self.screen.blit(progress_text, progress_rect)
                    
                else:
                    # Empty plot - draw PlotIcon with CircleBorder
                    # Check if we can build on this territory this turn
                    can_build = (owner == self.game_state.current_player and
                                territory not in self.game_state.buildings_started_this_turn)

                    if 'Plot' in self.building_icons and self.building_icons['Plot']:
                        plot_icon = self.building_icons['Plot']

                        # C2 fix: Use cached scaling for empty plot icons
                        icon_size = int(plot_radius * 1.6)
                        base_icon = self._get_cached_scaled_surface(
                            plot_icon, 'bldg_Plot', icon_size, icon_size)
                        scaled_icon = self._apply_icon_overlay(
                            base_icon, is_clicking, is_hovering, enabled=can_build,
                            disabled_tint=(128, 128, 128, 180))

                        icon_rect = scaled_icon.get_rect(center=(plot_center_x, plot_center_y))
                        self.screen.blit(scaled_icon, icon_rect)

                        # C2 fix: Use cached border scaling
                        if self.circle_border:
                            scaled_border = self._get_cached_scaled_surface(
                                self.circle_border, 'circle_border', plot_size, plot_size)
                            border_rect = scaled_border.get_rect(center=(plot_center_x, plot_center_y))
                            self.screen.blit(scaled_border, border_rect)

                        # Draw selection highlight on top if selected
                        if self.selected_plot and self.selected_plot == (territory, plot_index):
                            pygame.draw.circle(self.screen, (255, 215, 0), (plot_center_x, plot_center_y), plot_radius, 4)
                    else:
                        # Fallback to circle with plus sign if icon not available
                        circle_color = (180, 240, 180) if can_build else (220, 220, 220)
                        if is_clicking:
                            circle_color = brighten_color(circle_color, 0.4)
                        elif is_hovering:
                            circle_color = lighten_color(circle_color, 0.2)
                        pygame.draw.circle(self.screen, circle_color, (plot_center_x, plot_center_y), plot_radius)

                        if self.selected_plot and self.selected_plot == (territory, plot_index):
                            pygame.draw.circle(self.screen, (255, 215, 0), (plot_center_x, plot_center_y), plot_radius, 4)
                        else:
                            pygame.draw.circle(self.screen, (100, 100, 100), (plot_center_x, plot_center_y), plot_radius, 2)

                        if owner == self.game_state.current_player:
                            plus_text = self._get_cached_text("+", self.font, (100, 100, 100))
                            plus_rect = plus_text.get_rect(center=(plot_center_x, plot_center_y))
                            self.screen.blit(plus_text, plus_rect)
                
                # Store plot button for click detection
                self.territory_info_plot_buttons.append((plot_rect, territory, plot_index))
        
        # Draw second vertical dividing line (between building plots and army info)
        divider_x2 = divider_x + 400  # Position after building plots
        self.draw_separator(divider_x2, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)
        
        # Draw army info section on the right
        army_info_x = divider_x2 + 20
        army_info_y = BOTTOM_UI_Y + 30
        
        # Section title (Phase 2: Use SemiBold for section header)
        # PERFORMANCE: Use cached static text
        army_title = self._get_cached_text("Forces", self.font_bold, BROWN_TEXT_HEADING)
        self.screen.blit(army_title, (army_info_x, army_info_y))
        army_info_y += 32  # Increased spacing by 2px (was 30)

        # Total armies - 25% larger text, bold font
        armies_text = self._get_cached_text(f"Total: {armies}", self.font, BROWN_TEXT_PRIMARY)
        self.screen.blit(armies_text, (army_info_x, army_info_y))
        army_info_y += 24  # Increased spacing by 2px (was 22)

        # Unit composition breakdown (if armies exist)
        if armies > 0:
            composition = self.game_state.get_unit_composition(territory)
            if composition:
                for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain']:
                    if unit_type in composition and composition[unit_type] > 0:
                        count = composition[unit_type]
                        # Use Battalion terminology
                        battalion_name = f"{unit_type} Battalion" if count == 1 else f"{unit_type} Battalions"
                        comp_text = self._get_cached_text(f"  {battalion_name}: {count}", self.small_font, BROWN_TEXT_SECONDARY)
                        self.screen.blit(comp_text, (army_info_x, army_info_y))
                        army_info_y += 20  # Increased spacing by 2px (was 18)

        army_info_y += 7  # Increased spacing by 2px (was 5)

        # Draw army limit indicator - same size and color as Total
        if armies >= self.game_state.MAX_ARMIES_PER_TERRITORY:
            limit_text = self._get_cached_text(f"Army Limit: {armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", self.font, (180, 0, 0))
        else:
            limit_text = self._get_cached_text(f"Army Limit: {armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", self.font, BROWN_TEXT_PRIMARY)
        self.screen.blit(limit_text, (army_info_x, army_info_y))

        # --- Territory Preview Image Section ---
        # Drawn to the right of the Forces section with a separator
        divider_x3 = divider_x2 + 315  # Positioned to use available space right of Forces
        available_preview_width = WINDOW_WIDTH - divider_x3 - 20  # 20px right margin

        # Only draw if enough space (graceful degradation at low resolutions)
        if available_preview_width >= 150:
            self.draw_separator(divider_x3, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

            preview_x = divider_x3 + 20

            # Image height from panel, width fills available space (capped by 16:9 ratio)
            border_padding = 8
            preview_img_height = int(BOTTOM_UI_HEIGHT * 0.70)
            # Use available width, but don't exceed 16:9 ratio
            max_width_from_ratio = int(preview_img_height * 16 / 9)
            max_width_from_space = available_preview_width - 20 - border_padding * 2
            preview_img_width = min(max_width_from_ratio, max_width_from_space)
            border_width = preview_img_width + border_padding * 2
            border_height = preview_img_height + border_padding * 2

            # Position: left-aligned in available space
            center_x = preview_x
            # Vertically center the border + hint text in the panel, shifted down 10px to avoid overlap
            total_content_height = border_height + 18  # border + gap + hint text
            preview_y = BOTTOM_UI_Y + (BOTTOM_UI_HEIGHT - total_content_height) // 2 + 10

            img_x = center_x + border_padding
            img_y = preview_y + border_padding

            if SHOW_TERRITORY_PREVIEW_IMAGE:
                # Draw border frame (cached by size to avoid per-frame scaling)
                if self._preview_border_original:
                    if self._scaled_preview_border_size != (border_width, border_height):
                        self._scaled_preview_border = pygame.transform.smoothscale(
                            self._preview_border_original, (border_width, border_height))
                        self._scaled_preview_border_size = (border_width, border_height)
                    self.screen.blit(self._scaled_preview_border, (center_x, preview_y))

                # Draw territory preview image or black fallback inside the border
                preview_surface = self._get_territory_preview(territory, preview_img_width, preview_img_height)
                if preview_surface:
                    self.screen.blit(preview_surface, (img_x, img_y))
                else:
                    # No preview image available — show black background
                    pygame.draw.rect(self.screen, (0, 0, 0),
                                     (img_x, img_y, preview_img_width, preview_img_height))

                # Store rect for hover detection
                self.territory_preview_rect = pygame.Rect(img_x, img_y, preview_img_width, preview_img_height)

                # Draw low-opacity hint text below the framed image
                hint_y = preview_y + border_height + 4
                hint_text = self._get_cached_text(
                    "Hover over the picture to learn more.",
                    self.small_font, (150, 140, 120))
                # Center hint text under the border
                hint_x = center_x + (border_width - hint_text.get_width()) // 2
                self.screen.blit(hint_text, (hint_x, hint_y))
            else:
                # Preview image hidden — render italic lore text in the same region instead.
                self.territory_preview_rect = None
                bronze = (205, 170, 110)  # matches tooltip lore color
                lore_text = map_data.get_territory_lore(territory)
                if not lore_text:
                    lore_text = "No lore available for this territory."
                lore_font = self.lore_font_italic
                lore_lines = self.helpers.wrap_text_smart(lore_text, lore_font, preview_img_width)
                # Extra line spacing (1.35x) so the text breathes within the preview region
                line_h = int(lore_font.get_linesize() * 1.35)
                total_h = line_h * len(lore_lines)
                # Vertically center within the would-be image region
                ly = img_y + max(0, (preview_img_height - total_h) // 2)
                max_y = img_y + preview_img_height
                for ln in lore_lines:
                    if ly >= max_y:
                        break  # bounds-check — never render past container
                    surf = self._get_cached_text(ln, lore_font, bronze)
                    self.screen.blit(surf, (img_x, ly))
                    ly += line_h
        else:
            # Not enough space for preview section
            self.territory_preview_rect = None

        # Track button hover for plot tooltips (will be drawn with delay in main loop)
        if owner == self.game_state.current_player and self.territory_info_plot_buttons:
            mouse_pos = pygame.mouse.get_pos()
            current_hover = None
            for plot_rect, terr, plot_idx in self.territory_info_plot_buttons:
                # Circular collision detection
                plot_center_x = plot_rect.centerx
                plot_center_y = plot_rect.centery
                plot_radius = plot_rect.width // 2
                distance = ((mouse_pos[0] - plot_center_x) ** 2 + (mouse_pos[1] - plot_center_y) ** 2) ** 0.5
                if distance <= plot_radius:
                    # Check what's on this plot
                    existing_building = None
                    if terr in self.game_state.buildings:
                        existing_building = self.game_state.buildings[terr].get(plot_idx)

                    if existing_building:
                        # Show tooltip for finished building (include veterancy info for Farms/Mines)
                        if existing_building in ('Farm', 'Mine'):
                            bldg_data = self.game_state.get_building_xp_data(terr, plot_idx)
                            current_hover = ('plot', (existing_building, bldg_data['level'], bldg_data['xp']))
                        else:
                            current_hover = ('plot', existing_building)
                        break
                    else:
                        # Check if under construction
                        under_construction = None
                        if terr in self.game_state.under_construction:
                            under_construction = self.game_state.under_construction[terr].get(plot_idx)

                        if not under_construction:
                            # Can show tooltip for empty plot (if can build this turn)
                            can_build = terr not in self.game_state.buildings_started_this_turn

                            if can_build:
                                current_hover = ('plot', None)  # Simple plot tooltip
                                break

            # Update hover tracking using helper (Phase 1D)
            self.update_button_hover(current_hover, 'plot')

        # Territory preview image hover detection for lore tooltip
        if self.territory_preview_rect:
            mouse_pos = pygame.mouse.get_pos()
            if self.territory_preview_rect.collidepoint(mouse_pos):
                self.update_button_hover(('territory_lore', territory), 'territory_lore')
            elif self.hover_target_button and self.hover_target_button[0] == 'territory_lore':
                self.update_button_hover(None, 'territory_lore')


    # ========================================
    # PHASE 5: EXTRACTED BOTTOM UI METHODS
    # ========================================
    
    def _draw_player_info_section(self):
        """
        Draw left side player info section in bottom UI.
        
        Phase 5: Extracted from draw_bottom_ui() for maintainability.
        Displays player color, gold, income, and control buttons.
        
        Renders:
        - Current player name and color
        - Gold amount and income per turn
        - End Turn button
        - Action Log toggle button
        - Testing mode indicator
        
        Location: Left side of bottom UI panel
        Width: Expanded 75% wider for better visibility
        """
        # Dynamic positioning: moved left to expand available space (2.5% instead of 9.4%)
        # Elements are now 75% wider (210px instead of 120px)
        ui_x = int(WINDOW_WIDTH * 0.025)  # Shifted left for expansion
        ui_y = BOTTOM_UI_Y + self.scale(30)  # Scaled vertical offset

        if self.game_state.phase == 'playing':
            # Current player - smart wrapping if name+title overflows available width
            player_color = self.game_state.get_player_color(self.game_state.current_player)
            player_name = self.game_state.get_player_name(self.game_state.current_player)
            # Max width: End Turn button width (matches the element directly below)
            max_name_width = self.scale(180 if WINDOW_HEIGHT == 720 else 210)
            player_text = self._get_cached_text(player_name, self.large_font_bold, player_color)
            if player_text.get_width() <= max_name_width:
                # Fits in one line at full size
                self.screen.blit(player_text, (ui_x, ui_y))
                ui_y += self.scale(50)
            else:
                # Multi-line: use smaller font (15pt bold) for better spacing
                name_font = self.font_bold
                words = player_name.split(' ')
                line1_words = []
                for i, word in enumerate(words):
                    test_line = ' '.join(line1_words + [word])
                    if name_font.size(test_line)[0] > max_name_width and line1_words:
                        break
                    line1_words.append(word)
                line2_words = words[len(line1_words):]
                line1_surface = self._get_cached_text(' '.join(line1_words), name_font, player_color)
                self.screen.blit(line1_surface, (ui_x, ui_y))
                if line2_words:
                    line2_surface = self._get_cached_text(' '.join(line2_words), name_font, player_color)
                    self.screen.blit(line2_surface, (ui_x, ui_y + self.scale(20)))
                ui_y += self.scale(50)

            # Gold and income removed - now shown in top panel

            # End Turn button - scaled dimensions (narrower at 720p to prevent overflow)
            button_width = 180 if WINDOW_HEIGHT == 720 else 210  # Reduce width for 720p
            end_turn_rect = pygame.Rect(ui_x, ui_y, self.scale(button_width), self.scale(40))

            # Tutorial hook: override End Turn button color when highlighted
            end_turn_color = (100, 150, 100)  # Default green
            end_turn_text = "End Turn"  # Default text

            if self._is_tutorial_active():
                if self.tutorial_mission.should_highlight_button('end_turn'):
                    end_turn_color = (50, 255, 50)  # Bright green highlight
                elif (self.tutorial_mission.is_button_locked('end_turn')
                        or not self.tutorial_mission.is_action_allowed('end_turn')):
                    # Grey locked. is_action_allowed() is the check the click uses; campaign
                    # missions and the Tale only block through it (intro, pause, endgame),
                    # so is_button_locked() alone left the button looking clickable.
                    end_turn_color = (120, 120, 120)

            # SEQUENTIAL MODE: next_player() refuses while armies are still moving or
            # battles are unresolved — grey the button instead of letting it look clickable
            if self.sim_state is None and (
                    self.game_state.turn_phase == 'execution'
                    or (self.game_state.turn_phase == 'battles' and self.game_state.pending_battles)):
                end_turn_color = (120, 120, 120)

            # SIMULTANEOUS MODE: Grey out End Turn button when player is ready or during resolution
            sim_player_ready = False
            if self.sim_state is not None:
                if self.sim_state.sim_phase == 'planning':
                    local_player = self.get_local_player()
                    sim_player_ready = self.sim_state.players_ready.get(local_player, False)
                    if sim_player_ready:
                        end_turn_color = (120, 120, 120)  # Grey - waiting for other players
                        end_turn_text = "Waiting..."
                elif self.sim_state.sim_phase in ('executing', 'resolving'):
                    # Grey out during execution and resolution phases
                    end_turn_color = (120, 120, 120)
                    end_turn_text = "Resolving..." if self.sim_state.sim_phase == 'resolving' else "Executing..."

            self.draw_feedback_button(end_turn_rect, end_turn_color,
                                      'bottom_button', 'end_turn',
                                      text=end_turn_text)

            # Tutorial hook: draw pulsing green glow border on End Turn when highlighted
            if self._is_tutorial_active():
                if self.tutorial_mission.should_highlight_button('end_turn'):
                    pulse = int(180 + 75 * math.sin(pygame.time.get_ticks() / 200.0))
                    glow_rect = end_turn_rect.inflate(6, 6)
                    pygame.draw.rect(self.screen, (50, 255, 50), glow_rect, 3, border_radius=4)

            self.end_turn_button = end_turn_rect

            # Planning timer display (under End Turn button) - scaled
            # Check mission's is_timer_visible() if active, otherwise show during planning
            _show_timer = self.game_state.turn_phase == 'planning'
            if self._is_tutorial_active():
                # Mission controls timer visibility (intro sequence hides/shows it)
                if hasattr(self.tutorial_mission, 'is_timer_visible'):
                    _show_timer = _show_timer and self.tutorial_mission.is_timer_visible()
                else:
                    _show_timer = False  # Tutorial mission hides timer by default

            # SIMULTANEOUS MODE: Show waiting indicator if player is ready
            if self.sim_state is not None and self.sim_state.sim_phase == 'planning':
                local_player = self.get_local_player()
                is_ready = self.sim_state.players_ready.get(local_player, False)

                if is_ready:
                    # Show "Waiting for: X, Y" indicator with intelligent wrapping
                    waiting_names = self.sim_state.get_waiting_player_names()
                    if waiting_names:
                        # Wrap names if too long for available width
                        max_width = self.scale(button_width + 20)  # Allow slight overflow
                        waiting_lines = self._wrap_waiting_text(waiting_names, max_width)
                    else:
                        waiting_lines = ["All players ready..."]

                    # Draw waiting indicator below End Turn button (multi-line support)
                    waiting_y = ui_y + self.scale(50)
                    line_height = self.scale(16)
                    for i, line in enumerate(waiting_lines):
                        waiting_surface = self._get_cached_text(line, self.small_font, (180, 180, 180))
                        waiting_rect = waiting_surface.get_rect(center=(
                            ui_x + self.scale(button_width) // 2,
                            waiting_y + i * line_height
                        ))
                        self.screen.blit(waiting_surface, waiting_rect)
                else:
                    # Show simultaneous mode timer
                    remaining_time = self.sim_state.get_remaining_time(local_player)
                    self._draw_planning_timer(ui_x, ui_y, button_width, remaining_time,
                                             self.sim_state._get_timer_limit(local_player))

            elif _show_timer and self.sim_state is None:
                # SEQUENTIAL MODE ONLY: Standard timer display
                # (Simultaneous mode handles its own timer above)
                remaining_time = self.game_state.get_remaining_planning_time()
                time_limit = self.game_state.player_planning_time_limit[self.game_state.current_player]

                # During mission intro, show full timer bar (static, not counting down)
                if self.tutorial_mission:
                    if hasattr(self.tutorial_mission, 'intro_active') and self.tutorial_mission.intro_active:
                        remaining_time = time_limit  # Show full bar during intro

                if remaining_time is not None:
                    self._draw_planning_timer(ui_x, ui_y, button_width, remaining_time, time_limit)

            # Elapsed game time display (below End Turn button or timer)
            if self.game_start_time is not None:
                elapsed_seconds = int(time.time() - self.game_start_time)
                hours = elapsed_seconds // 3600
                minutes = (elapsed_seconds % 3600) // 60
                seconds = elapsed_seconds % 60

                # Position below the timer (if showing) or below End Turn button
                elapsed_y = ui_y + self.scale(75) if self.game_state.turn_phase == 'planning' else ui_y + self.scale(45)

                elapsed_text = f"Elapsed Game Time: {hours:02d}:{minutes:02d}:{seconds:02d}"
                elapsed_surface = self._get_cached_text(elapsed_text, self.small_font, (180, 180, 180))
                self.screen.blit(elapsed_surface, (ui_x, elapsed_y))

            # Command Limit moved to top panel (now part of Taxation - Command - Gold - Income group)

        # Vertical separator line - dynamic positioning (19.4% of width for 1600px base)
        separator_x = int(WINDOW_WIDTH * 0.194)  # Was 310 at 1600px width
        self.draw_separator(separator_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

    def _wrap_waiting_text(self, player_names: list, max_width: int) -> list:
        """
        Wrap 'Waiting for: X, Y, Z' text into multiple lines if too long.

        Args:
            player_names: List of player names waiting
            max_width: Maximum width in pixels

        Returns:
            List of text lines to render
        """
        if not player_names:
            return ["All players ready..."]

        lines = []
        current_line = "Waiting for:"

        for i, name in enumerate(player_names):
            # Check if adding this name would exceed width
            test_text = current_line + " " + name
            if i < len(player_names) - 1:
                test_text += ","

            test_width = self.small_font.size(test_text)[0]

            if test_width > max_width and current_line != "Waiting for:":
                # Start new line
                lines.append(current_line)
                current_line = name
                if i < len(player_names) - 1:
                    current_line += ","
            else:
                # Add to current line
                current_line += " " + name
                if i < len(player_names) - 1:
                    current_line += ","

        # Add final line
        if current_line:
            lines.append(current_line)

        return lines if lines else ["Waiting..."]

    def _draw_planning_timer(self, ui_x, ui_y, button_width, remaining_time, time_limit):
        """
        Draw the planning phase timer below the End Turn button.

        Used by both sequential and simultaneous modes.

        Args:
            ui_x: X position of the UI area
            ui_y: Y position below End Turn button
            button_width: Width of the End Turn button
            remaining_time: Remaining time in seconds
            time_limit: Total time limit in seconds
        """
        if remaining_time is None or time_limit <= 0:
            return

        minutes = int(remaining_time // 60)
        seconds = int(remaining_time % 60)
        timer_text = f"{minutes}:{seconds:02d}"

        # Timer rectangle dimensions - scaled (match button width)
        timer_rect_x = ui_x
        timer_rect_y = ui_y + self.scale(45)
        timer_rect_width = self.scale(button_width)
        timer_rect_height = self.scale(25)

        # Draw white background rectangle
        timer_background = pygame.Rect(timer_rect_x, timer_rect_y, timer_rect_width, timer_rect_height)
        pygame.draw.rect(self.screen, (255, 255, 255), timer_background)
        pygame.draw.rect(self.screen, (100, 100, 100), timer_background, 2)  # Border

        # Calculate time ratio and progress bar color
        time_ratio = remaining_time / time_limit

        # Progress bar color: green -> yellow -> red as time runs out
        if time_ratio > 0.5:
            bar_color = (100, 200, 100)  # Green
        elif time_ratio > 0.25:
            bar_color = (200, 200, 100)  # Yellow
        else:
            bar_color = (200, 100, 100)  # Red

        # Draw progress bar (fills from left to right, empties from right to left)
        bar_padding = 3
        inner_width = timer_rect_width - (bar_padding * 2)
        inner_height = timer_rect_height - (bar_padding * 2)
        bar_width = int(inner_width * time_ratio)
        if bar_width > 0:
            progress_bar = pygame.Rect(timer_rect_x + bar_padding, timer_rect_y + bar_padding, bar_width, inner_height)
            pygame.draw.rect(self.screen, bar_color, progress_bar)

        # Draw timer text centered on the rectangle (black for visibility)
        timer_surface = self._get_cached_text(timer_text, self.font, (0, 0, 0))
        timer_text_rect = timer_surface.get_rect(center=(timer_rect_x + timer_rect_width // 2, timer_rect_y + timer_rect_height // 2))
        self.screen.blit(timer_surface, timer_text_rect)

    def _draw_army_info_section(self):
        """
        Draw army info when army is selected.
        
        Phase 5: Extracted from draw_bottom_ui() for maintainability.
        Shows army composition, movement status, and hints.
        
        Renders:
        - Territory name
        - Total army count
        - Army limit indicator
        - Movement status (ready/moved)
        - Movement instructions
        - Deselect hint
        
        Only shown when: Army selected, no plot/barracks selected
        Location: Center-right of bottom UI
        """
        selected_territory, army_count = self.game_state.selected_army

        # Panel starting position - dynamic (21.875% of width)
        panel_x = int(WINDOW_WIDTH * 0.21875)  # Was 350 at 1600px width
        panel_y = BOTTOM_UI_Y + 30
        
        # Header
        owner = self.game_state.territory_owners.get(selected_territory, -1)
        owner_color = self.game_state.get_player_color(owner) if owner != -1 else BROWN_TEXT_PRIMARY
        title_text = self._get_cached_text("Selected Army", self.large_font, owner_color)
        self.screen.blit(title_text, (panel_x, panel_y))
        panel_y += UI_SECTION_SPACING

        # Territory name (with smart wrapping for long names)
        # Use display name for campaign mission territory renaming
        display_territory = map_data.get_display_name(selected_territory)
        full_territory_text = f"Territory: {display_territory}"
        max_territory_width = 200  # Maximum width before wrapping
        territory_lines = self.helpers.wrap_text_smart(full_territory_text, self.font, max_territory_width)

        for line in territory_lines:
            territory_text = self._get_cached_text(line, self.font, BROWN_TEXT_HEADING)
            self.screen.blit(territory_text, (panel_x, panel_y))
            panel_y += 22  # Line height for wrapped text

        panel_y += 8  # Extra spacing after territory name

        # Army count breakdown
        unmoved = self.game_state.armies_unmoved.get(selected_territory, 0)
        moved = self.game_state.armies_moved.get(selected_territory, 0)
        total = unmoved + moved

        # Total armies
        total_text = self._get_cached_text(f"Total Armies: {total}", self.font, BROWN_TEXT_PRIMARY)
        self.screen.blit(total_text, (panel_x, panel_y))
        panel_y += 28

        # Army limit indicator
        limit_color = (180, 0, 0) if total >= self.game_state.MAX_ARMIES_PER_TERRITORY else (100, 100, 100)
        limit_text = self._get_cached_text(f"Army Limit: {total}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", self.small_font, limit_color)
        self.screen.blit(limit_text, (panel_x + 10, panel_y))
        panel_y += 24

        if unmoved > 0:
            # Ready to move (green)
            ready_text = self._get_cached_text(f"\u2022 {unmoved} ready to move", self.small_font, (0, 150, 0))
            self.screen.blit(ready_text, (panel_x + 10, panel_y))
            panel_y += UI_LINE_SPACING_SMALL

            if moved > 0:
                # Already moved (gray)
                moved_text = self._get_cached_text(f"\u2022 {moved} already moved this turn", self.small_font, (120, 120, 120))
                self.screen.blit(moved_text, (panel_x + 10, panel_y))
                panel_y += UI_LINE_SPACING_SMALL
        else:
            # All moved (red warning)
            all_moved_text = self._get_cached_text(f"\u2022 All {moved} armies already moved", self.small_font, (180, 0, 0))
            self.screen.blit(all_moved_text, (panel_x + 10, panel_y))
            panel_y += UI_LINE_SPACING_SMALL

        panel_y += 10

        # Instructions
        hint_text = self._get_cached_text("Right-click adjacent territory to move", self.small_font, (100, 100, 100))
        self.screen.blit(hint_text, (panel_x, panel_y))
        panel_y += 20

        # Deselect hint
        deselect_text = self._get_cached_text("Click elsewhere to deselect", self.small_font, (100, 100, 100))
        self.screen.blit(deselect_text, (panel_x, panel_y))
    
    def _draw_instruction_message(self):
        """
        Draw centered instruction text in bottom UI.
        
        Phase 5: Extracted from draw_bottom_ui() for maintainability.
        Shows appropriate message based on game phase and state.
        
        Messages:
        - Battle phase: "Click on a battlefield to resolve battle"
        - Setup phase: "SETUP: Claim X/Y territories"
        - Playing phase: "Click a building plot or Barracks to interact"
        
        Location: Center of bottom UI
        Only shown when: No selection active
        """
        # Battle instruction during battles
        if self.game_state.turn_phase == 'battles' and len(self.game_state.pending_battles) > 0:
            if not self.battle_popup_visible:
                instruction = self._get_cached_text("Click on a battlefield to resolve battle", self.font, BLACK)
                instruction_rect = instruction.get_rect(center=(WINDOW_WIDTH // 2, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT // 2))
                self.screen.blit(instruction, instruction_rect)
            self.train_buttons = {}  # Bug 5 fix: clear plural train_buttons dict, not dead singular
            return True  # Handled

        # Default instructions when nothing selected
        elif self.game_state.phase != 'playing' or (not self.selected_plot and not self.selected_barracks and not self.selected_keep and not self.selected_hero and not self.game_state.selected_army):
            if self.game_state.phase == 'playing':
                instruction = self._get_cached_text("Click a building plot, Barracks, or Keep to interact", self.font, GRAY)
            elif self.game_state.phase == 'setup':
                chosen = self.game_state.territories_chosen[self.game_state.current_player]
                max_territories = self.game_state.max_starting_territories
                if self.game_state.is_ai_player():
                    instruction = self._get_cached_text(f"SETUP: Click a territory for AI Player {self.game_state.current_player + 1} ({chosen}/{max_territories})", self.large_font, BLACK)
                else:
                    instruction = self._get_cached_text(f"SETUP: Claim {chosen}/{max_territories} territories", self.large_font, BLACK)
            else:
                instruction = self._get_cached_text("", self.font, BLACK)

            instruction_rect = instruction.get_rect(center=(WINDOW_WIDTH // 2, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT // 2))
            self.screen.blit(instruction, instruction_rect)
            self.train_buttons = {}  # Bug 5 fix: clear plural train_buttons dict, not dead singular
            return True  # Handled
        
        return False  # Not handled
    
    def _draw_building_ui_section(self):
        """
        Draw building UI when plot is selected.
        
        Phase 5: Extracted from draw_bottom_ui() for maintainability.
        Shows different content based on plot state:
        - Completed building: Show info and demolish option
        - Under construction: Show progress and cancel option
        - Empty plot: Show building options
        
        Renders:
        - Plot title (territory + plot number)
        - Building info (if built)
        - Construction info (if building)
        - Building options (if empty)
        - Demolish/Cancel buttons
        
        Location: Center-right of bottom UI
        """
        territory, plot_index = self.selected_plot
        
        # Check plot state
        building = None
        under_construction = None
        
        if territory in self.game_state.buildings:
            building = self.game_state.buildings[territory].get(plot_index)
        
        if territory in self.game_state.under_construction:
            under_construction = self.game_state.under_construction[territory].get(plot_index)

        # Start building UI - dynamic (25% of width)
        build_ui_x = int(WINDOW_WIDTH * 0.25)  # Was 400 at 1600px width
        build_ui_y = BOTTOM_UI_Y + 30

        if building:
            # Show existing building info - polished format matching Keep/Barracks
            building_info = self.game_state.building_types[building]

            # Large building name (same format as Keep)
            building_title = self._get_cached_text(building, self.large_font, BROWN_TEXT_HEADING)
            self.screen.blit(building_title, (build_ui_x, build_ui_y))
            build_ui_y += 40

            # Show effect as bullet point with lighter color
            effect_color = (200, 200, 200)  # Light gray for consistency
            effect = building_info['effect']
            value = building_info['value']

            effect_text = self._get_cached_text(
                self._get_building_effect_text(effect, value), self.small_font, effect_color)
            self.screen.blit(effect_text, (build_ui_x, build_ui_y))
            build_ui_y += 25

            # --- Veterancy: Show XP bar and level info for Farms/Mines ---
            if building in ('Farm', 'Mine'):
                bldg_data = self.game_state.get_building_xp_data(territory, plot_index)
                bldg_level = bldg_data['level']
                bldg_xp = bldg_data['xp']

                # Level text with shield icons
                gold_color = (218, 165, 32)
                if bldg_level > 0 and self.level_shield_icon:
                    # Draw shield icons inline before level text
                    s_size = self.scale(12)
                    cached_s = self._get_cached_scaled_surface(
                        self.level_shield_icon, 'level_shield_bldg_panel', s_size, s_size)
                    sx = build_ui_x
                    for lv in range(bldg_level):
                        self.screen.blit(cached_s, (sx, build_ui_y))
                        sx += s_size + 1
                    # Level text after shields
                    level_label = self._get_cached_text(f" Level {bldg_level}", self.small_font, gold_color)
                    self.screen.blit(level_label, (sx, build_ui_y))
                    # Income bonus text
                    bonus_pct = int(bldg_level * self.game_state.BUILDING_LEVEL_INCOME_BONUS * 100)
                    if bonus_pct > 0:
                        bonus_text = self._get_cached_text(f"  (+{bonus_pct}% income)", self.small_font, (150, 200, 150))
                        self.screen.blit(bonus_text, (sx + level_label.get_width(), build_ui_y))
                else:
                    level_label = self._get_cached_text(f"Level {bldg_level}", self.small_font, (200, 200, 200))
                    self.screen.blit(level_label, (build_ui_x, build_ui_y))
                build_ui_y += 22

                # XP progress bar
                bar_w = 180
                bar_h = self.scale(6)
                bar_x = build_ui_x
                bar_y = build_ui_y

                # Calculate fill ratio
                if bldg_level < self.game_state.MAX_LEVEL:
                    prev_t = self.game_state.LEVEL_XP_CUMULATIVE[bldg_level - 1] if bldg_level > 0 else 0
                    next_t = self.game_state.LEVEL_XP_CUMULATIVE[bldg_level]
                    xp_in_level = bldg_xp - prev_t
                    xp_needed = next_t - prev_t
                    fill = max(0.0, min(1.0, xp_in_level / xp_needed)) if xp_needed > 0 else 0.0
                    xp_label = f"{xp_in_level}/{xp_needed} XP"
                else:
                    fill = 1.0
                    xp_label = "MAX"

                # Draw bar bg + fill (brass-colored)
                pygame.draw.rect(self.screen, (60, 50, 40), (bar_x, bar_y, bar_w, bar_h))
                fill_px = int(bar_w * fill)
                if fill_px > 0:
                    pygame.draw.rect(self.screen, (185, 155, 80), (bar_x, bar_y, fill_px, bar_h))
                # Thin border
                pygame.draw.rect(self.screen, (100, 90, 70), (bar_x, bar_y, bar_w, bar_h), 1)

                # XP text to the right of bar
                xp_text = self._get_cached_text(xp_label, self.small_font, (200, 200, 200))
                self.screen.blit(xp_text, (bar_x + bar_w + 8, bar_y - 2))
                build_ui_y += bar_h + 10

            # Demolish button (same format as Barracks)
            demolish_rect = pygame.Rect(build_ui_x, build_ui_y, 180, 30)

            # Tutorial hook: grey out demolish button during tutorial unless allowed
            _tutorial_demolish_locked = (self.tutorial_mission
                                         and self.tutorial_mission.active
                                         and not self.tutorial_mission.is_action_allowed('demolish'))

            if _tutorial_demolish_locked:
                # Greyed out demolish button during tutorial
                self.draw_feedback_button(demolish_rect, (80, 80, 80),
                                          'demolish', 'building',
                                          text="Demolish (50%)", font=self.small_font,
                                          text_color=(120, 120, 120))
            else:
                # Check if Confiscate is active (Erec Silvyr + Farm/Mine)
                has_confiscate = (self.game_state.player_has_silvyr(self.game_state.current_player) and
                                building in ['Farm', 'Mine'])

                if has_confiscate:
                    # Dark blue glowing button for Confiscate
                    demolish_color = (30, 60, 150)  # Dark blue
                    self.draw_feedback_button(demolish_rect, demolish_color,
                                              'demolish', 'building',
                                              text="Demolish (50%)", font=self.small_font)

                    # Add glowing effect - draw a bright blue outline
                    glow_color = (70, 120, 255)  # Bright blue glow
                    pygame.draw.rect(self.screen, glow_color, demolish_rect, 3)
                else:
                    # Normal red demolish button
                    self.draw_feedback_button(demolish_rect, (150, 100, 100),
                                              'demolish', 'building',
                                              text="Demolish (50%)", font=self.small_font)

            self.demolish_button = demolish_rect
            
        elif under_construction:
            # Show construction info - polished format matching completed buildings
            building_type = under_construction[0]  # entry is (building_type, turns_remaining, cost)
            turns_remaining = under_construction[1]
            building_info = self.game_state.building_types[building_type]

            # Large building name with "Under Construction" suffix
            building_title = self._get_cached_text(f"{building_type} (Under Construction)", self.large_font, BROWN_TEXT_HEADING)
            self.screen.blit(building_title, (build_ui_x, build_ui_y))
            build_ui_y += 40

            # Show effect as bullet point with lighter color
            effect_color = (200, 200, 200)  # Light gray for consistency
            effect = building_info['effect']
            value = building_info['value']

            effect_text = self._get_cached_text(
                self._get_building_effect_text(effect, value), self.small_font, effect_color)
            self.screen.blit(effect_text, (build_ui_x, build_ui_y))
            build_ui_y += 22

            # Turns remaining info
            turns_text = self._get_cached_text(f"- Completes in {turns_remaining} turn{'s' if turns_remaining != 1 else ''}.", self.small_font, effect_color)
            self.screen.blit(turns_text, (build_ui_x, build_ui_y))
            build_ui_y += 30

            # Cancel button (same format as Demolish)
            cancel_rect = pygame.Rect(build_ui_x, build_ui_y, 180, 30)

            # Tutorial hook: grey out cancel button during tutorial unless allowed
            _tutorial_cancel_locked = (self.tutorial_mission
                                       and self.tutorial_mission.active
                                       and not self.tutorial_mission.is_action_allowed('cancel_construction'))

            if _tutorial_cancel_locked:
                # Greyed out cancel button during tutorial
                self.draw_feedback_button(cancel_rect, (80, 80, 80),
                                          'cancel', 'construction',
                                          # Just "Cancel": the building name made long types overflow the
                                          # button, and the plot panel above already names it.
                                          text="Cancel", font=self.small_font,
                                          text_color=(120, 120, 120))
            else:
                self.draw_feedback_button(cancel_rect, (150, 100, 100),
                                          'cancel', 'construction',
                                          text="Cancel", font=self.small_font)
            self.cancel_button = cancel_rect

        else:
            # Empty plot - show building options
            # Show plot title for empty plots only
            plot_title = self._get_cached_text(f"{territory} - Plot {plot_index + 1}", self.font, BROWN_TEXT_HEADING)
            self.screen.blit(plot_title, (build_ui_x, build_ui_y))
            build_ui_y += 30

            # Check if can build this turn
            can_build = territory not in self.game_state.buildings_started_this_turn

            if not can_build:
                limit_text = self._get_cached_text("Building limit reached this turn", self.small_font, (180, 0, 0))
                self.screen.blit(limit_text, (build_ui_x, build_ui_y))
                build_ui_y += UI_LINE_SPACING_SMALL
            
            current_gold = self.game_state.player_gold[self.game_state.current_player]
            
            # Building options - arranged horizontally
            button_x = build_ui_x  # Start position for horizontal layout
            for i, (building_name, info) in enumerate(self.game_state.building_types.items()):
                # Use centralized cost with all discounts (fixes red tint persisting after discount)
                cost = self.game_state.get_building_cost(building_name)

                letter = info['letter']
                can_afford = current_gold >= cost
                
                # Check one-per-territory restrictions (Keep, Training Grounds)
                # Per-type rules — the same check start_construction() refuses with
                # (also covers "no Keep in a Fortress territory", which this copy missed)
                can_build_this_building = self.game_state.get_building_type_block_reason(
                    territory, building_name) is None

                # Button color - consider affordability, building limit, AND one-per-territory restriction
                if can_build and can_afford and can_build_this_building:
                    button_color = (100, 200, 100)  # Green
                else:
                    button_color = (200, 100, 100)  # Red

                # Tutorial hook: override button color for locking/highlighting
                building_locked = False
                if self._is_tutorial_active():
                    btn_id = f'building_{building_name}'
                    # is_action_allowed('build') is what start_construction() checks (and what
                    # the map icons use). Campaign missions/Tale only block through it (intro,
                    # pause, endgame), so is_button_locked() alone left these looking normal.
                    if (self.tutorial_mission.is_button_locked(btn_id)
                            or not self.tutorial_mission.is_action_allowed(
                                'build', building_type=building_name, territory=territory)):
                        building_locked = True
                        button_color = (120, 120, 120)  # Grey (locked)
                        can_build_this_building = False  # Prevent click
                    elif self.tutorial_mission.should_highlight_button(btn_id):
                        button_color = (50, 255, 50)  # Bright green (highlighted)

                # Calculate circular button center and radius (1.5x larger)
                button_size = int(BUTTON_SIZE_SQUARE * 1.5)
                button_radius = button_size // 2
                button_center_x = button_x + button_radius
                button_center_y = build_ui_y + button_radius
                button_rect = pygame.Rect(button_x, build_ui_y, button_size, button_size)

                # Check hover (circular collision detection)
                is_hovering = False
                if self.mouse_pos:
                    mouse_x, mouse_y = self.mouse_pos
                    distance = ((mouse_x - button_center_x) ** 2 + (mouse_y - button_center_y) ** 2) ** 0.5
                    if distance <= button_radius:
                        is_hovering = True

                # Check click flash
                is_clicking = (self.clicked_element and
                              self.clicked_element[0] == 'building' and
                              self.clicked_element[1] == building_name)

                # Apply visual feedback to color
                final_color = button_color
                if is_clicking:
                    final_color = brighten_color(button_color, 0.4)
                elif is_hovering:
                    final_color = lighten_color(button_color, 0.2)

                # Draw building icon PNG or fallback to letter
                if building_name in self.building_icons and self.building_icons[building_name]:
                    building_icon = self.building_icons[building_name]

                    # PERFORMANCE OPTIMIZATION: Use cached scaled icon (fixes 80→40 FPS drop)
                    icon_size = int(button_radius * 1.6)
                    cached_icon = self._get_cached_ui_icon(building_icon, building_name, icon_size)

                    # Create working copy for overlays (only when effects are needed)
                    display_icon = cached_icon
                    if not (can_build and can_afford and can_build_this_building) or is_clicking or is_hovering:
                        display_icon = cached_icon.copy()  # Only copy when we need to apply effects

                        # PERFORMANCE: Cache building overlay surfaces by size to avoid per-frame allocation
                        if icon_size not in self._cached_building_overlays:
                            red = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            red.fill((255, 100, 100, 128))
                            bright = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            bright.fill((100, 100, 100, 100))
                            light = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            light.fill((50, 50, 50, 50))
                            self._cached_building_overlays[icon_size] = {'red': red, 'bright': bright, 'light': light}
                        overlays = self._cached_building_overlays[icon_size]

                        # Apply tint overlay if building is unavailable: grey when locked by
                        # the tutorial/mission, red when a game rule refuses it (the icon used
                        # to turn red for both, so a mission lock looked like "can't afford")
                        if not (can_build and can_afford and can_build_this_building):
                            if building_locked:
                                if 'grey' not in overlays:
                                    grey = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                                    grey.fill((110, 110, 110, 255))
                                    overlays['grey'] = grey
                                display_icon.blit(overlays['grey'], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                            else:
                                display_icon.blit(overlays['red'], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)  # Match training UI

                        # Apply hover/click brightness effects
                        if is_clicking:
                            display_icon.blit(overlays['bright'], (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                        elif is_hovering:
                            display_icon.blit(overlays['light'], (0, 0), special_flags=pygame.BLEND_RGB_ADD)

                    # Blit final icon
                    icon_rect = display_icon.get_rect(center=(button_center_x, button_center_y))
                    self.screen.blit(display_icon, icon_rect)

                    # PERFORMANCE OPTIMIZATION: Cache border scaling too
                    if self.circle_border:
                        border_size = button_size  # Use full button size for border
                        cached_border = self._get_cached_ui_icon(self.circle_border, 'circle_border', border_size)
                        border_rect = cached_border.get_rect(center=(button_center_x, button_center_y))
                        self.screen.blit(cached_border, border_rect)
                else:
                    # Fallback to circular button with letter if icon not available
                    pygame.draw.circle(self.screen, final_color, (button_center_x, button_center_y), button_radius)
                    pygame.draw.circle(self.screen, BLACK, (button_center_x, button_center_y), button_radius, 2)
                    text_surf = self._get_cached_text(letter, self.font, WHITE)
                    text_rect = text_surf.get_rect(center=(button_center_x, button_center_y))
                    self.screen.blit(text_surf, text_rect)

                self.building_buttons[building_name] = button_rect
                button_x += button_size + 50  # Move right for next button with increased spacing
    
    def draw_bottom_ui(self):
        """
        Draw the bottom UI panel - RTS style, full width.
        
        Phase 5: Refactored into sub-methods for maintainability.
        Main method now orchestrates different UI sections:
        1. Player info (left) - Always shown
        2. Army composition - If army composition view active
        3. Army info - If army selected
        4. Territory info - If territory selected
        5. Training UI - If Barracks selected
        6. Building UI - If plot selected
        7. Instructions - Default/fallback
        
        Each section is handled by a dedicated method for clarity:
        - _draw_player_info_section()
        - _draw_army_info_section()
        - _draw_instruction_message()
        - _draw_building_ui_section()
        - draw_army_composition_ui() (already extracted)
        - draw_territory_info_panel() (already extracted)
        - draw_training_ui() (already extracted)
        
        Priority Order:
        1. Player info (always drawn first)
        2. Army composition UI (highest priority content)
        3. Army info section
        4. Territory info panel
        5. Instruction messages (battle/setup/playing)
        6. Training UI (Barracks selected)
        7. Building UI (plot selected)
        
        Phase 5 Refactoring Benefits:
        - Each section < 150 lines
        - Clear single responsibilities
        - Much easier to modify individual UI sections
        - Better code organization
        """
        # Draw background for bottom UI (starts below map area, accounting for top panel)
        bottom_rect = pygame.Rect(0, BOTTOM_UI_Y, WINDOW_WIDTH, BOTTOM_UI_HEIGHT)
        
        # Use custom image if available, otherwise fallback to solid color
        if self.bottom_panel_image:
            # Blit image with top edge aligned to BOTTOM_UI_Y
            self.screen.blit(self.bottom_panel_image, (0, BOTTOM_UI_Y))
        else:
            # Fallback: solid color background
            pygame.draw.rect(self.screen, (220, 220, 220), bottom_rect)
        
        # Draw top border line (over the image)
        pygame.draw.line(self.screen, BLACK, (0, BOTTOM_UI_Y), (WINDOW_WIDTH, BOTTOM_UI_Y), 2)

        # Clear all button dictionaries to prevent stale buttons from interfering
        # These will be repopulated by the appropriate draw method based on current context
        self.train_buttons = {}
        self.queue_cancel_buttons = []
        self.demolish_barracks_button = None
        self.hero_train_buttons = {}
        self.hero_cancel_button = None
        self.demolish_keep_button = None
        self.castle_upgrade_button = None  # L10/L11 fix: clear stale castle buttons per-frame
        self.castle_upgrade_cancel_button = None
        self.building_buttons = {}
        self.cancel_button = None
        self.demolish_button = None
        self.territory_info_plot_buttons = []
        # Hero ability slots were only reset inside draw_hero_ui, so after the Hero UI
        # closed their rects stayed clickable over whatever the bottom panel showed next
        self.hero_ability_buttons = {}

        # Always draw player info section (left side)
        self._draw_player_info_section()
        
        # Show army composition UI if enabled (Phase 3)
        if self.show_army_composition and self.army_composition_territory:
            self.draw_army_composition_ui()
            return
        
        # Show army info if army is selected
        if self.game_state.selected_army and not self.selected_plot and not self.selected_barracks and not self.selected_keep and not self.selected_hero:
            self._draw_army_info_section()
            return

        # Show territory info if territory clicked (but no plot/barracks/keep selected)
        if self.selected_territory_info and not self.selected_plot and not self.selected_barracks and not self.selected_keep and not self.selected_hero:
            self.draw_territory_info_panel()
            return
        
        # Show instruction messages (battle/setup/default)
        if self._draw_instruction_message():
            return  # Instruction was shown, we're done

        # Keep UI when Keep selected (Hero training)
        if self.selected_keep:
            self.draw_keep_ui()
            return

        # Training UI when Barracks selected
        if self.selected_barracks:
            self.draw_training_ui()
            return

        # Hero UI when hero selected
        if self.selected_hero:
            self.draw_hero_ui()
            return

        # Building UI when plot selected
        if self.selected_plot:
            self._draw_building_ui_section()
            return

    def draw_hero_ability_icon(self, rect, hero_name, ability_index, status, hovering, clicking,
                               digit_font, disabled=None, surface=None):
        """Draw one hero ability button (icon, spell border, overlays, cooldown digits).

        Shared by the bottom-bar Hero UI (60 px) and the sidebar Heroes tab (~30 px).
        `status` comes from game_state.get_hero_ability_status(). `disabled` defaults to
        "active ability that can't be cast now"; the sidebar passes True when it is not
        the viewer's turn. `surface` defaults to the screen (the sidebar draws into a
        cached sprite instead and blits that).
        """
        size = rect.w
        target = self.screen if surface is None else surface
        if disabled is None:
            disabled = status['type'] == 'active' and not status['castable']
        image = self.ability_images.get((hero_name, ability_index)) if hasattr(self, 'ability_images') else None
        if image:
            # PERFORMANCE: cached scaled icon / border / overlays (keyed by size)
            icon = self._get_cached_ui_icon(image, f'ability_{hero_name}_{ability_index}', size)
            target.blit(icon, rect.topleft)
            if disabled:
                target.blit(self._get_hero_overlay(size, 'dark'), rect.topleft)
            if clicking:
                target.blit(self._get_hero_overlay(size, 'bright'), rect.topleft, special_flags=pygame.BLEND_RGB_ADD)
            elif hovering:
                target.blit(self._get_hero_overlay(size, 'light'), rect.topleft, special_flags=pygame.BLEND_RGB_ADD)
            border, border_id = ((self.passive_spell_border, 'passive_spell_border') if status['type'] == 'passive'
                                 else (self.active_spell_border, 'active_spell_border'))
            if border:
                target.blit(self._get_cached_ui_icon(border, border_id, size), rect.topleft)
                # Hover/click also brighten the border
                if clicking:
                    target.blit(self._get_hero_overlay(size, 'bright'), rect.topleft, special_flags=pygame.BLEND_RGB_ADD)
                elif hovering:
                    target.blit(self._get_hero_overlay(size, 'light'), rect.topleft, special_flags=pygame.BLEND_RGB_ADD)
        else:
            # Fallback: ability number
            number = self._get_cached_text(str(ability_index + 1), self.font, GRAY if disabled else WHITE)
            target.blit(number, number.get_rect(center=rect.center))

        # Cooldown turns, with a shadow for readability
        if status['cooldown'] > 0:
            text = str(status['cooldown'])
            digits = self._get_cached_text(text, digit_font, (255, 200, 200))
            digits_rect = digits.get_rect(center=(rect.centerx, rect.bottom - max(8, size // 4)))
            shadow = self._get_cached_text(text, digit_font, BLACK)
            offset = 2 if size >= 40 else 1
            target.blit(shadow, (digits_rect.x + offset, digits_rect.y + offset))
            target.blit(digits, digits_rect)

    def try_cast_hero_ability(self, hero_name, ability_index, flash_type='hero_ability'):
        """Cast a hero ability exactly as the bottom-bar button does. Returns True if cast.

        Shared by the bottom-bar Hero UI and the sidebar Heroes tab so both behave
        identically: targeted abilities enter targeting mode; immediate ones run, are
        broadcast in multiplayer (SIM_HERO_ABILITY) and play their map effect; a refusal
        shows its toast. Uses game_state.current_player (the acting player) - callers
        gate on whose turn it is.
        """
        current_player = self.game_state.current_player
        status = self.game_state.get_hero_ability_status(current_player, hero_name, ability_index)
        if status is None or not status['castable']:
            return False
        ability_name = status['name']
        self.trigger_click_flash(flash_type, (hero_name, ability_index))

        result = self.game_state.activate_hero_ability(hero_name, ability_index)
        if result == 'requires_targeting':
            # Enter targeting mode
            self.ability_targeting_active = True
            self.ability_targeting_hero = hero_name
            self.ability_targeting_ability_index = ability_index
            self.ability_targeting_ability_name = ability_name
        elif result is True:
            # Immediate ability executed - broadcast to other players in multiplayer
            # Sync fix: send in both sequential and simultaneous modes (not just sim)
            if self.multiplayer_mode:
                self._send_action_to_remote(MessageType.SIM_HERO_ABILITY, {
                    'player_id': current_player,
                    'hero_name': hero_name,
                    'ability_index': ability_index,
                    'ability_name': ability_name,
                    'target': None  # No target for immediate abilities
                })
                logger.debug(f"[NETWORK] Sent SIM_HERO_ABILITY: {hero_name} - {ability_name}")
            # Trigger visual effect for immediate abilities
            self.map_renderer.trigger_ability_effect(ability_name, None, current_player)
        elif isinstance(result, str):
            # An immediate ability refused with a reason (Reinforce: its Keep territory is
            # full). The refusal recorded its message code.
            if self.game_state.last_action_error:
                self._show_action_failure_feedback()
            else:
                self.show_action_error(message=result)
        self.clear_button_tooltip()
        return True

    def draw_hero_ui(self):
        """Draw Hero UI when a hero is selected from Heroes tab"""
        hero_name = self.selected_hero

        # Get hero data
        current_player = self.game_state.current_player
        if current_player not in self.game_state.heroes:
            return
        if hero_name not in self.game_state.heroes[current_player]:
            return

        hero_data = self.game_state.heroes[current_player][hero_name]
        hero_letter = self.game_state.HERO_TYPES[hero_name]['letter']

        # Note: Player info section already draws separator dynamically
        # We don't need another separator here

        # === SECTION 1: LARGE HERO ICON ===
        icon_x = int(WINDOW_WIDTH * 0.21875)  # Start after separator (was 350 at 1600px)
        icon_y = BOTTOM_UI_Y + 35
        icon_size = 100

        # Try to use PNG image, fall back to letter if not available
        icon_rect = pygame.Rect(icon_x, icon_y, icon_size, icon_size)

        if hero_name in self.hero_images and self.hero_images[hero_name]:
            # PERFORMANCE: Cache scaled hero portrait in existing icon cache
            cache_key = (f"hero_{hero_name}", icon_size)
            if cache_key not in self._ui_icon_cache:
                self._ui_icon_cache[cache_key] = pygame.transform.scale(
                    self.hero_images[hero_name], (icon_size, icon_size)
                )
            hero_image_scaled = self._ui_icon_cache[cache_key]
            self.screen.blit(hero_image_scaled, (icon_x, icon_y))
            # Draw border around image
            pygame.draw.rect(self.screen, (200, 200, 100), icon_rect, 3, border_radius=8)
        else:
            # Fallback: Draw letter icon
            hero_color = (150, 100, 200)
            pygame.draw.rect(self.screen, hero_color, icon_rect, border_radius=8)
            pygame.draw.rect(self.screen, (200, 200, 100), icon_rect, 3, border_radius=8)
            # Draw hero letter
            hero_letter_surface = self._get_cached_text(hero_letter, self.large_font, WHITE)
            hero_letter_rect = hero_letter_surface.get_rect(center=icon_rect.center)
            self.screen.blit(hero_letter_surface, hero_letter_rect)

        # === SECTION 3: HERO NAME AND INFO ===
        name_x = icon_x + icon_size + 25
        name_y = icon_y

        # Colors
        cream_color = (245, 235, 210)
        bronze_color = (205, 127, 50)
        silvery_color = (192, 192, 192)

        # Hero name (larger font)
        name_text = self._get_cached_text(hero_name, self.large_font, BROWN_TEXT_HEADING)
        self.screen.blit(name_text, (name_x, name_y))
        name_y += 35  # Increased spacing

        # Hero description (italic bronze) - dynamically pulled from HERO_TYPES
        hero_info = self.game_state.HERO_TYPES[hero_name]
        description_lines = hero_info.get('description', ['Unknown hero'])
        for line in description_lines:
            desc_text = self._get_cached_text(line, self.small_font_italic, bronze_color)
            self.screen.blit(desc_text, (name_x, name_y))
            name_y += 22  # Increased spacing

        # Hero location with bold silvery "Location:" label
        name_y += 8  # Extra spacing before location
        location_label = self._get_cached_text("Location:", self.small_font_bold, silvery_color)
        location_value = self._get_cached_text(f" {hero_data['keep_territory']}", self.small_font, cream_color)
        self.screen.blit(location_label, (name_x, name_y))
        self.screen.blit(location_value, (name_x + location_label.get_width(), name_y))

        # === SECTION 2: SECOND SEPARATOR ===
        second_separator_x = int(WINDOW_WIDTH * 0.5)  # Positioned after hero name (was 800 at 1600px)
        self.draw_separator(second_separator_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # === SECTION 5: ABILITY BUTTONS (3 abilities - horizontal) ===
        ability_start_x = second_separator_x + 20
        ability_y = BOTTOM_UI_Y + 30
        ability_size = 60
        ability_spacing = 15

        # PERFORMANCE: Use cached static text
        ability_title = self._get_cached_text("Abilities:", self.font, BROWN_TEXT_HEADING)
        self.screen.blit(ability_title, (ability_start_x, ability_y))
        ability_y += 35

        # Clear ability buttons dict
        self.hero_ability_buttons = {}

        # Get hero abilities from HERO_TYPES
        abilities = hero_info.get('abilities', [])

        # Track ability button hover
        current_ability_hover = None

        # Draw up to 3 ability buttons horizontally
        ability_x = ability_start_x
        for i in range(3):
            ability_rect = pygame.Rect(ability_x, ability_y, ability_size, ability_size)

            # Store button rect for click detection
            self.hero_ability_buttons[(hero_name, i)] = ability_rect

            # Availability + drawing are shared with the sidebar Heroes tab
            # (game_state.get_hero_ability_status / draw_hero_ability_icon)
            status = self.game_state.get_hero_ability_status(current_player, hero_name, i)
            if status is not None:
                is_hovering = ability_rect.collidepoint(self.mouse_pos)
                if is_hovering:
                    # Track hover for tooltip (both active and passive abilities)
                    current_ability_hover = ('hero_ability', (hero_name, i))
                is_clicking = status['castable'] and self.clicked_element == ('hero_ability', (hero_name, i))
                self.draw_hero_ability_icon(ability_rect, hero_name, i, status, is_hovering, is_clicking,
                                            self.large_font)
            else:
                # No ability at this slot - draw empty placeholder
                pygame.draw.rect(self.screen, (60, 60, 60), ability_rect, border_radius=5)
                pygame.draw.rect(self.screen, (40, 40, 40), ability_rect, 2, border_radius=5)

            ability_x += ability_size + ability_spacing

        # Update button hover tracking for ability buttons
        self.update_button_hover(current_ability_hover, 'hero_ability')

        # === SECTION 6: THIRD SEPARATOR ===
        # Calculate based on 3 abilities side by side
        third_separator_x = ability_start_x + (ability_size * 3) + (ability_spacing * 2) + 20
        self.draw_separator(third_separator_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # === SECTION 7: HERO INFO ===
        info_x = third_separator_x + 20
        info_y = BOTTOM_UI_Y + 30

        # PERFORMANCE: Use cached static text
        info_title = self._get_cached_text("Hero Info:", self.font, BROWN_TEXT_HEADING)
        self.screen.blit(info_title, (info_x, info_y))
        info_y += 40  # Increased spacing

        # Death and respawn information (multi-line)
        info_lines = [
            "A Hero is slain when a Keep",
            "they are residing at is",
            "conquered. Hero can be",
            "re-summoned in a Keep",
            "after their death."
        ]

        for line in info_lines:
            info_text = self._get_cached_text(line, self.small_font, cream_color)
            self.screen.blit(info_text, (info_x, info_y))
            info_y += 20  # Line spacing

    def draw_training_ui(self):
        """Draw training interface when Barracks is selected"""
        territory, barracks_plot_index = self.selected_barracks

        # Panel starting position (right after player info separator - dynamic)
        panel_x = int(WINDOW_WIDTH * 0.194)  # Matches player info separator position
        panel_y = BOTTOM_UI_Y + 30

        # Left info section - 30 pixels from the separator for breathing room
        info_x = panel_x + 30
        info_y = panel_y

        # Draw title
        title_text = self._get_cached_text("Barracks", self.large_font, BROWN_TEXT_HEADING)
        self.screen.blit(title_text, (info_x, info_y))
        info_y += 35

        # Draw current gold and income
        current_gold = self.game_state.player_gold[self.game_state.current_player]
        current_income = self.game_state.calculate_player_income(self.game_state.current_player)
        gold_text = self._get_cached_text(f"Gold: {current_gold}G (+{current_income}/turn)", self.small_font, (218, 165, 32))
        self.screen.blit(gold_text, (info_x, info_y))
        info_y += 22

        # Get current queue info
        queue_count = 0
        if (territory in self.game_state.training_queue and
            barracks_plot_index in self.game_state.training_queue[territory]):
            queue_count = len(self.game_state.training_queue[territory][barracks_plot_index])

        # Display units in queue
        queue_text = self._get_cached_text(f"Queue: {queue_count}/4", self.small_font, BROWN_TEXT_SECONDARY)
        self.screen.blit(queue_text, (info_x, info_y))
        info_y += 22

        # Display armies in territory (include ALL garrisons)
        current_armies = self.game_state.get_territory_total_armies(territory)
        armies_text = self._get_cached_text(f"Armies: {current_armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", self.small_font, BROWN_TEXT_SECONDARY)
        self.screen.blit(armies_text, (info_x, info_y))

        # Training buttons - sized to fit 5 unit types (Swordsman, Archer, Pikeman, Cavalry, Captain)
        button_y = panel_y
        button_width = int(BUTTON_SIZE_SQUARE * 1.2)
        button_height = int(BUTTON_SIZE_SQUARE * 1.2)
        button_spacing = BUTTON_SPACING
        button_x = info_x + 150  # Position to the right of the info section
        
        # Unit type colors (for button backgrounds)
        unit_colors = {
            'Swordsman': (100, 100, 150),  # Blue-gray
            'Archer': (100, 150, 100),     # Green
            'Pikeman': (120, 90, 70),      # Brown
            'Cavalry': (180, 140, 60),     # Gold
            'Captain': (160, 120, 180)     # Purple
        }
        
        # Check army limit (reuse current_armies from above)
        at_army_limit = current_armies >= self.game_state.MAX_ARMIES_PER_TERRITORY
        # Command limit: show red hue when player's total army count >= limit
        at_command_limit = self.game_state.get_player_army_count(self.game_state.current_player) >= self.game_state.player_command_limit[self.game_state.current_player]

        # Reuse queue_count from above
        can_queue = queue_count < self.game_state.MAX_TRAINING_QUEUE  # same limit as start_training()
        
        # Store training buttons for click detection
        self.train_buttons = {}
        any_affordable = False  # Bug 4 fix: track if ANY unit is affordable

        # Draw 5 training buttons (one for each unit type including Captain)
        for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain']:
            unit_info = self.game_state.UNIT_TYPES[unit_type]
            # Use discounted cost for affordability check (fixes red tint persisting after discount)
            unit_cost = self.game_state.get_effective_cost(unit_type, unit_info['cost'])
            unit_letter = unit_info['letter']

            can_afford = current_gold >= unit_cost
            if can_afford:
                any_affordable = True  # Bug 4 fix: track across all unit types
            is_available = can_afford and can_queue and not at_army_limit and not at_command_limit

            # Tutorial hook: override training button availability
            training_locked = False
            if self._is_tutorial_active():
                btn_id = f'training_{unit_type}'
                # Same check start_training() and the map icons use (see building buttons)
                if (self.tutorial_mission.is_button_locked(btn_id)
                        or not self.tutorial_mission.is_action_allowed(
                            'train', unit_type=unit_type, territory=territory)):
                    training_locked = True
                    is_available = False

            # Create button rect
            train_button_rect = pygame.Rect(button_x, button_y, button_width, button_height)

            # Check hover and click state
            is_hovering = train_button_rect.collidepoint(self.mouse_pos)
            is_clicking = (self.clicked_element and
                          self.clicked_element[0] == 'training' and
                          self.clicked_element[1] == unit_type)

            # Get unit icon
            unit_icon = self.unit_icons.get(unit_type)

            if unit_icon:
                # PERFORMANCE OPTIMIZATION: Use cached scaled icon (fixes 80→40 FPS drop)
                icon_size = min(button_width, button_height) - 4  # Slightly smaller than button
                cached_icon = self._get_cached_ui_icon(unit_icon, f'unit_{unit_type}', icon_size)

                # Create working copy for overlays (only when effects are needed)
                display_icon = cached_icon
                if not is_available or is_clicking or is_hovering:
                    display_icon = cached_icon.copy()  # Only copy when we need to apply effects

                    # Apply tint overlay if unavailable (cached by icon_size): grey when
                    # locked by the tutorial/mission, red when a game rule refuses it
                    if not is_available:
                        if icon_size not in self._cached_training_overlays:
                            self._cached_training_overlays[icon_size] = {}
                        overlays = self._cached_training_overlays[icon_size]
                        tint_key = 'grey' if training_locked else 'red'
                        if tint_key not in overlays:
                            s = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            s.fill((110, 110, 110, 255) if training_locked else (255, 100, 100, 128))
                            overlays[tint_key] = s
                        display_icon.blit(overlays[tint_key], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                    # Apply hover/click brightness effects (cached by icon_size)
                    if is_clicking:
                        if icon_size not in self._cached_training_overlays:
                            self._cached_training_overlays[icon_size] = {}
                        overlays = self._cached_training_overlays[icon_size]
                        if 'bright' not in overlays:
                            s = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            s.fill((100, 100, 100, 100))
                            overlays['bright'] = s
                        display_icon.blit(overlays['bright'], (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                    elif is_hovering:
                        if icon_size not in self._cached_training_overlays:
                            self._cached_training_overlays[icon_size] = {}
                        overlays = self._cached_training_overlays[icon_size]
                        if 'light' not in overlays:
                            s = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            s.fill((50, 50, 50, 50))
                            overlays['light'] = s
                        display_icon.blit(overlays['light'], (0, 0), special_flags=pygame.BLEND_RGB_ADD)

                # Blit final icon
                icon_rect = display_icon.get_rect(center=train_button_rect.center)
                self.screen.blit(display_icon, icon_rect)

                # PERFORMANCE OPTIMIZATION: Cache border scaling too
                # Border is 2px larger than icon (1px per side) to fully contain icon edges
                if self.icon_border:
                    cached_border = self._get_cached_ui_icon(self.icon_border, 'icon_border', icon_size + 2)
                    border_rect = cached_border.get_rect(center=train_button_rect.center)
                    self.screen.blit(cached_border, border_rect)
            else:
                # Fallback to letter button if icon not available
                # Grey when locked by the tutorial/mission, red when a game rule refuses it
                if is_available:
                    button_color = unit_colors[unit_type]
                else:
                    button_color = (120, 120, 120) if training_locked else (200, 100, 100)
                self.draw_letter_button(train_button_rect, unit_letter, button_color, letter_color=WHITE,
                                       button_type='training', button_id=unit_type)

            # Tutorial hook: draw green highlight border if button is highlighted
            if self._is_tutorial_active():
                btn_id = f'training_{unit_type}'
                if self.tutorial_mission.should_highlight_button(btn_id):
                    # Pulsing green glow border
                    pulse = int(180 + 75 * math.sin(pygame.time.get_ticks() / 200.0))
                    pygame.draw.rect(self.screen, (50, 255, 50, pulse), train_button_rect, 3)

            # Store button for click detection
            self.train_buttons[unit_type] = train_button_rect

            # Move to next button position
            button_x += button_width + button_spacing
        
        # Move panel_y down past the buttons
        panel_y += button_height + 15
        # Status messages below the buttons (if needed)
        status_x = button_x
        if at_army_limit:
            status_text = self._get_cached_text("ARMY LIMIT REACHED", self.small_font, (180, 0, 0))
            self.screen.blit(status_text, (status_x, panel_y))
        elif not any_affordable:  # Bug 4 fix: check if ANY unit is affordable, not just last one
            status_text = self._get_cached_text("Not enough gold", self.small_font, (150, 0, 0))
            self.screen.blit(status_text, (status_x, panel_y))
        elif not can_queue:
            status_text = self._get_cached_text("Queue full", self.small_font, (150, 0, 0))
            self.screen.blit(status_text, (status_x, panel_y))
        panel_y += UI_LINE_SPACING_SMALL

        # Draw first vertical divider line (between training controls and queue)
        # Calculate position: info section (150px) + buttons (5 unit types + spacing) + margin
        divider_x = info_x + 150 + (button_width * 5) + (button_spacing * 4) + 20
        self.draw_separator(divider_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)
        
        # Draw training queue on the right
        queue_x = divider_x + 20
        queue_y = BOTTOM_UI_Y + 30
        
        # PERFORMANCE: Use cached static text
        queue_title = self._get_cached_text("Training Queue:", self.font, BROWN_TEXT_HEADING)
        self.screen.blit(queue_title, (queue_x, queue_y))
        queue_y += 30
        
        # Initialize queue cancel buttons
        self.queue_cancel_buttons = []
        
        # Display queue items
        if (territory in self.game_state.training_queue and 
            barracks_plot_index in self.game_state.training_queue[territory]):
            queue = self.game_state.training_queue[territory][barracks_plot_index]
            
            for i, entry in enumerate(queue):
                unit_type, turns_remaining = entry[0], entry[1]
                # Queue item background
                item_rect = pygame.Rect(queue_x, queue_y, 280, 30)
                pygame.draw.rect(self.screen, (220, 220, 220), item_rect)
                pygame.draw.rect(self.screen, BLACK, item_rect, 1)
                
                # Unit info
                if i == 0:
                    # First in queue - currently training
                    if turns_remaining == 0:
                        # Training paused due to army limit
                        unit_text = self._get_cached_text(f"{unit_type} (Army Limit Reached)", self.small_font, (180, 0, 0))
                    else:
                        unit_text = self._get_cached_text(f"{unit_type} (training... {turns_remaining} turn)", self.small_font, (0, 100, 0))
                else:
                    # Waiting in queue
                    unit_text = self._get_cached_text(f"{unit_type} (waiting)", self.small_font, GRAY)
                self.screen.blit(unit_text, (queue_x + 5, queue_y + 7))

                # Cancel button
                cancel_rect = pygame.Rect(queue_x + 250, queue_y + 5, 20, 20)

                # Base color
                # Tutorial hook: grey out cancel button during tutorial unless allowed
                _tutorial_cancel_locked = (self.tutorial_mission
                                           and self.tutorial_mission.active
                                           and not self.tutorial_mission.is_action_allowed('cancel_training'))
                if _tutorial_cancel_locked:
                    button_color = (80, 80, 80)
                else:
                    button_color = (200, 100, 100)
                    # Check hover
                    is_hovering = cancel_rect.collidepoint(self.mouse_pos)
                    # Check click
                    is_clicking = (self.clicked_element and
                                  self.clicked_element[0] == 'queue_cancel' and
                                  self.clicked_element[1] == i)
                    # Apply feedback
                    if is_clicking:
                        button_color = brighten_color(button_color, 0.4)
                    elif is_hovering:
                        button_color = lighten_color(button_color, 0.2)

                pygame.draw.rect(self.screen, button_color, cancel_rect)
                pygame.draw.rect(self.screen, BLACK, cancel_rect, 1)
                cancel_text_color = (120, 120, 120) if _tutorial_cancel_locked else WHITE
                cancel_text = self._get_cached_text("X", self.small_font, cancel_text_color)
                cancel_text_rect = cancel_text.get_rect(center=cancel_rect.center)
                self.screen.blit(cancel_text, cancel_text_rect)

                # Store for click detection
                self.queue_cancel_buttons.append((cancel_rect, i))

                queue_y += 35
        else:
            empty_text = self._get_cached_text("No units in queue", self.small_font, BROWN_TEXT_SECONDARY)
            self.screen.blit(empty_text, (queue_x, queue_y))
        
        # Draw second vertical divider line (between queue and tips)
        divider_x2 = queue_x + 320
        self.draw_separator(divider_x2, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)
        
        # Draw tips and controls section on the right
        tips_x = divider_x2 + 20
        tips_y = BOTTOM_UI_Y + 30

        # Section title - PERFORMANCE: Use cached static text
        tips_title = self._get_cached_text("Controls", self.font, BROWN_TEXT_HEADING)
        self.screen.blit(tips_title, (tips_x, tips_y))
        tips_y += 35

        # Keyboard shortcut hints - all static labels cached
        shortcut_text = self._get_cached_text("Keyboard Shortcuts:", self.small_font, BROWN_TEXT_PRIMARY)
        self.screen.blit(shortcut_text, (tips_x, tips_y))
        tips_y += 20

        shortcut_hint = self._get_cached_text("S = Swordsman", self.small_font, BROWN_TEXT_SECONDARY)
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 18

        shortcut_hint = self._get_cached_text("A = Archer", self.small_font, BROWN_TEXT_SECONDARY)
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 18

        shortcut_hint = self._get_cached_text("P = Pikeman", self.small_font, BROWN_TEXT_SECONDARY)
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 18

        shortcut_hint = self._get_cached_text("C = Cavalry", self.small_font, BROWN_TEXT_SECONDARY)
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 30
        
        # Demolish button (refund percentage depends on Makeshift Barracks upgrade)
        refund_percent = "100%" if self.game_state.player_barracks_full_refund[self.game_state.current_player] else "50%"
        demolish_rect = pygame.Rect(tips_x, tips_y, 180, 30)
        # Tutorial hook: grey out demolish during tutorial unless allowed
        _tutorial_demolish_locked = (self.tutorial_mission
                                     and self.tutorial_mission.active
                                     and not self.tutorial_mission.is_action_allowed('demolish'))
        if _tutorial_demolish_locked:
            self.draw_feedback_button(demolish_rect, (80, 80, 80),
                                      'demolish', 'barracks',
                                      text=f"Demolish Barracks ({refund_percent})",
                                      font=self.small_font, text_color=(120, 120, 120))
        else:
            self.draw_feedback_button(demolish_rect, (150, 100, 100),
                                      'demolish', 'barracks',
                                      text=f"Demolish Barracks ({refund_percent})",
                                      font=self.small_font)
        
        # Store for click detection
        self.demolish_barracks_button = demolish_rect
        self.demolish_barracks_territory = territory
        self.demolish_barracks_plot_index = barracks_plot_index
        
        # Track button hover for tooltips (will be drawn with delay in main loop)
        mouse_pos = pygame.mouse.get_pos()
        current_hover = None
        for unit_type, button_rect in self.train_buttons.items():
            if button_rect.collidepoint(mouse_pos):
                current_hover = ('training', unit_type)
                break
        
        # Update hover tracking using helper (Phase 1D)
        self.update_button_hover(current_hover, 'training')

    def draw_keep_ui(self):
        """Draw Hero training interface when Keep is selected"""
        territory, keep_plot_index = self.selected_keep

        # Panel position (right after player info separator - dynamic)
        panel_x = int(WINDOW_WIDTH * 0.194)  # Matches player info separator position
        panel_y = BOTTOM_UI_Y + 30

        # === SECTION 1: KEEP/CASTLE TITLE ===
        info_x = panel_x + 10
        info_y = panel_y

        # Get display name (Keep or Castle)
        _, display_name = self.game_state.get_keep_display_info(territory, keep_plot_index)
        title_text = self._get_cached_text(display_name, self.large_font, BROWN_TEXT_HEADING)
        self.screen.blit(title_text, (info_x + 15, info_y))  # Title 15px to the right

        # Get current gold for hero affordability checks
        current_gold = self.game_state.player_gold[self.game_state.current_player]

        # === SECTION 2: HERO TRAINING BUTTONS (4x2 grid) ===
        button_y = panel_y
        first_row_y = button_y  # Save the first row Y position for Castle button positioning
        button_width = int(BUTTON_SIZE_SQUARE * 1.2)
        button_height = int(BUTTON_SIZE_SQUARE * 1.2)
        button_spacing = BUTTON_SPACING
        button_x = info_x + 110  # Position 40px less to the left (was 150, now 110)

        # All hero buttons use purple color
        hero_color_purple = (150, 100, 200)

        # Check if Keep is training
        is_training = (territory in self.game_state.hero_training_queue and
                       keep_plot_index in self.game_state.hero_training_queue[territory])

        # Check if Keep already has a trained hero
        keep_has_hero = False
        if self.game_state.current_player in self.game_state.heroes:
            for hero_data in self.game_state.heroes[self.game_state.current_player].values():
                if (hero_data['keep_territory'] == territory and
                    hero_data['keep_plot'] == keep_plot_index):
                    keep_has_hero = True
                    break

        # Check if hero limit is reached
        current_hero_count = len(self.game_state.hero_ownership[self.game_state.current_player])
        hero_limit = self.game_state.player_hero_limit[self.game_state.current_player]
        hero_limit_reached = current_hero_count >= hero_limit

        # Campaign mission 4: skip drawing hero training buttons entirely
        # when the active mission hides hero training (pre-assigned hero only)
        _hide_hero_training = (
            self.game_state.tutorial_mission and
            hasattr(self.game_state.tutorial_mission, 'should_hide_hero_training') and
            self.game_state.tutorial_mission.should_hide_hero_training()
        )

        # Keep is being upgraded to a Castle: start_hero_training() refuses, so the
        # buttons must show it (they used to look available)
        keep_upgrading = self.game_state.is_upgrading_to_castle(territory, keep_plot_index)

        # A mission that forbids hero training but still shows the buttons (the base
        # tutorial): grey them out, like other tutorial-locked controls
        hero_training_locked = bool(
            self.tutorial_mission and self.tutorial_mission.active
            and not self.tutorial_mission.is_action_allowed('train_hero'))

        # Draw hero buttons (6 on first line, 2 on second line)
        # Filter out campaign-only heroes (trainable: False) from the training menu
        hero_types_list = [h for h in self.game_state.HERO_TYPES.keys()
                          if self.game_state.HERO_TYPES[h].get('trainable', True)]
        for idx, hero_type in enumerate(hero_types_list):
            if _hide_hero_training:
                break  # Skip all hero training button drawing
            hero_info = self.game_state.HERO_TYPES[hero_type]
            hero_cost = hero_info['cost']

            # Apply Royal Decree discount for display
            discount_percent = self.game_state.player_royal_decree_discount[self.game_state.current_player]
            if discount_percent > 0:
                hero_cost = int(hero_cost * (100 - discount_percent) / 100)

            hero_letter = hero_info['letter']

            can_afford = current_gold >= hero_cost
            already_owned = hero_type in self.game_state.hero_ownership[self.game_state.current_player]

            # Determine button state
            if hero_training_locked:
                button_color = (120, 120, 120)  # Locked by tutorial/mission (grey)
            elif is_training or already_owned or keep_has_hero or hero_limit_reached or keep_upgrading:
                button_color = (200, 100, 100)  # Disabled (red)
            elif can_afford:
                button_color = hero_color_purple  # Enabled (purple)
            else:
                button_color = (200, 100, 100)  # Disabled (can't afford)

            # Move to second line after 4 heroes (4x2 grid)
            if idx == 4:
                button_y += button_height + button_spacing
                button_x = info_x + 110  # Reset to starting position

            # Draw button - use PNG if available, otherwise use letter
            train_button_rect = pygame.Rect(button_x, button_y, button_width, button_height)

            # Check if PNG image is available for this hero
            if hero_type in self.hero_images and self.hero_images[hero_type]:
                # Draw PNG image button with hover/click effects

                # Check for hover
                is_hovering = train_button_rect.collidepoint(self.mouse_pos)

                # Check for click flash
                is_clicking = (self.clicked_element and
                              self.clicked_element[0] == 'hero_training' and
                              self.clicked_element[1] == hero_type)

                # M17: Use cached scaling + icon overlay helpers instead of manual per-frame scale+tint
                is_disabled = (is_training or already_owned or keep_has_hero or hero_limit_reached
                               or not can_afford or keep_upgrading or hero_training_locked)
                base_icon = self._get_cached_scaled_surface(
                    self.hero_images[hero_type], f'hero_{hero_type}', button_width, button_height)
                # Grey when locked by the tutorial/mission, red when a game rule refuses it
                hero_image_scaled = self._apply_icon_overlay(
                    base_icon, is_clicking, is_hovering,
                    enabled=not is_disabled,
                    disabled_tint=(110, 110, 110, 150) if hero_training_locked else (200, 0, 0, 120))

                # Draw the image
                self.screen.blit(hero_image_scaled, (button_x, button_y))

                # C2 fix: Use cached border scaling
                # Border is 2px larger than icon (1px per side) to fully contain icon edges
                if self.icon_border:
                    scaled_border = self._get_cached_scaled_surface(
                        self.icon_border, 'icon_border', button_width + 2, button_height + 2)
                    self.screen.blit(scaled_border, (button_x - 1, button_y - 1))
            else:
                # Fallback to letter button
                self.draw_letter_button(train_button_rect, hero_letter, button_color,
                                       letter_color=WHITE, button_type='hero_training',
                                       button_id=hero_type)

            # Store for click detection
            self.hero_train_buttons[hero_type] = train_button_rect

            button_x += button_width + button_spacing

        # === SEPARATOR AFTER HERO GRID ===
        heroes_end_x = info_x + 110 + (button_width + button_spacing) * 4
        separator1_x = heroes_end_x + 15
        self.draw_separator(separator1_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # === SECTION 3: CASTLE UPGRADE ===
        # Castle upgrade button - original size (button_width * 2)
        castle_button_width = button_width * 2
        castle_button_height = button_height * 2
        castle_button_x = separator1_x + 20  # 20px after separator
        castle_button_y = first_row_y  # Align with top of hero grid

        # Check Castle status
        try:
            is_castle = self.game_state.is_castle(territory, keep_plot_index)
            is_upgrading = self.game_state.is_upgrading_to_castle(territory, keep_plot_index)
        except Exception as e:
            logger.error(f"ERROR in Castle upgrade check: {e}")
            is_castle = False
            is_upgrading = False

        UPGRADE_COST = 150

        # Initialize Castle hover tracking variables
        self.castle_button_is_hovering = False
        self.castle_button_rect_for_hover = None

        if is_castle:
            # Already Castle - don't show the Castle button or separator
            # Just continue with the UI as normal
            pass

        elif is_upgrading:
            # Upgrading in progress - show icon + progress bar underneath
            turns_remaining = self.game_state.castle_upgrades_in_progress[territory][keep_plot_index]

            # Create rect for collision detection
            upgrade_rect = pygame.Rect(castle_button_x, castle_button_y, castle_button_width, castle_button_height)

            # Hover/click effects for the button
            is_button_hovering = upgrade_rect.collidepoint(self.mouse_pos)
            is_button_clicking = (self.clicked_element and self.clicked_element[0] == 'upgrade_castle')

            # C2 fix: Use cached scaling for castle upgrade icon (in-progress state)
            if self.castle_upgrade_icon:
                icon_width = castle_button_width
                icon_height = castle_button_height
                base_icon = self._get_cached_scaled_surface(
                    self.castle_upgrade_icon, 'castle_upgrade', icon_width, icon_height)
                scaled_icon = base_icon.copy()

                # Apply yellow tint to show it's in progress (construction state)
                yellow_overlay = pygame.Surface((icon_width, icon_height), pygame.SRCALPHA)
                yellow_overlay.fill((255, 220, 100, 120))
                scaled_icon.blit(yellow_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                # Apply hover/click brightness
                if is_button_hovering or is_button_clicking:
                    bright_overlay = pygame.Surface((icon_width, icon_height), pygame.SRCALPHA)
                    if is_button_clicking:
                        bright_overlay.fill((100, 100, 100, 100))
                    else:
                        bright_overlay.fill((50, 50, 50, 50))
                    scaled_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

                self.screen.blit(scaled_icon, (castle_button_x, castle_button_y))

                # C2 fix: Use cached border scaling
                # Border is 2px larger than icon (1px per side) to fully contain icon edges
                if self.icon_border:
                    scaled_border = self._get_cached_scaled_surface(
                        self.icon_border, 'icon_border', icon_width + 2, icon_height + 2)
                    self.screen.blit(scaled_border, (castle_button_x - 1, castle_button_y - 1))
            else:
                # Fallback to text if icon not loaded
                button_color = (200, 200, 100)  # Yellow for upgrading
                if is_button_hovering and not is_button_clicking:
                    button_color = lighten_color(button_color, 0.2)

                pygame.draw.rect(self.screen, button_color, upgrade_rect)
                pygame.draw.rect(self.screen, (218, 165, 32), upgrade_rect, 3, border_radius=5)

                icon_text = self._get_cached_text("UPGRADE", self.font, BLACK)
                icon_text_rect = icon_text.get_rect(center=(upgrade_rect.centerx, upgrade_rect.centery - 10))
                self.screen.blit(icon_text, icon_text_rect)

                subtext = self._get_cached_text("TO CASTLE", self.small_font, BLACK)
                subtext_rect = subtext.get_rect(center=(upgrade_rect.centerx, upgrade_rect.centery + 10))
                self.screen.blit(subtext, subtext_rect)

            # Progress bar underneath the button (narrower and shorter to fit in area)
            bar_width = int(castle_button_width * 1.05)  # 30% less wide (was 1.5x)
            bar_height = 22  # Half as tall (was 45)
            bar_x = castle_button_x - (bar_width - castle_button_width) // 2  # Center it
            bar_y = castle_button_y + castle_button_height + 5  # Below button with 5px gap

            queue_rect = pygame.Rect(bar_x, bar_y, bar_width, bar_height)
            pygame.draw.rect(self.screen, (220, 220, 220), queue_rect)
            pygame.draw.rect(self.screen, (218, 165, 32), queue_rect, 2)

            # Text: "X turn/s" - very small text
            # C1 fix: Use cached extra_small_font instead of per-frame Font() creation
            turn_text = "turn" if turns_remaining == 1 else "turns"
            upgrade_text = self._get_cached_text(
                f"{turns_remaining} {turn_text}",
                self.extra_small_font, (100, 100, 0)
            )
            # Center the text vertically in the taller bar
            text_y = bar_y + (bar_height - upgrade_text.get_height()) // 2
            self.screen.blit(upgrade_text, (bar_x + 5, text_y))

            # Cancel button (X) to the right of the progress bar (vertically centered)
            cancel_size = 18  # 30% smaller (was 25)
            cancel_x = bar_x + bar_width - cancel_size - 5
            cancel_y = bar_y + (bar_height - cancel_size) // 2  # Center vertically in taller bar
            cancel_rect = pygame.Rect(cancel_x, cancel_y, cancel_size, cancel_size)

            is_cancel_hovering = cancel_rect.collidepoint(self.mouse_pos)
            is_cancel_clicking = (self.clicked_element and self.clicked_element[0] == 'cancel_castle_upgrade')

            cancel_color = (150, 100, 100)
            if is_cancel_clicking:
                cancel_color = brighten_color(cancel_color, 0.4)
            elif is_cancel_hovering:
                cancel_color = lighten_color(cancel_color, 0.2)

            pygame.draw.rect(self.screen, cancel_color, cancel_rect)
            pygame.draw.rect(self.screen, BLACK, cancel_rect, 1)
            cancel_text = self._get_cached_text("X", self.small_font, WHITE)
            cancel_text_rect = cancel_text.get_rect(center=cancel_rect.center)
            self.screen.blit(cancel_text, cancel_text_rect)

            self.castle_upgrade_cancel_button = cancel_rect

            # Store hover state but don't call update_button_hover here
            # (will be called at the end of draw_keep_ui to avoid interference with hero_training hover)
            castle_hover = is_button_hovering and not cancel_rect.collidepoint(self.mouse_pos)
            self.castle_button_is_hovering = castle_hover
            self.castle_button_rect_for_hover = upgrade_rect if castle_hover else None
        else:
            # Show upgrade button (2x size, spans both rows)
            can_afford = current_gold >= UPGRADE_COST

            # Determine button state
            if is_training:
                button_color = (150, 100, 100)  # Disabled (hero training)
                button_enabled = False
            elif can_afford:
                button_color = (100, 150, 200)  # Enabled (blue)
                button_enabled = True
            else:
                button_color = (150, 100, 100)  # Disabled (can't afford)
                button_enabled = False

            upgrade_rect = pygame.Rect(castle_button_x, castle_button_y, castle_button_width, castle_button_height)

            # Hover/click effects
            is_hovering = upgrade_rect.collidepoint(self.mouse_pos)
            is_clicking = (self.clicked_element and self.clicked_element[0] == 'upgrade_castle')

            # Draw Castle upgrade icon PNG or fallback to text button
            if self.castle_upgrade_icon:
                # C2 fix: Use cached scaling instead of per-frame smoothscale
                icon_width = castle_button_width
                icon_height = castle_button_height
                base_icon = self._get_cached_scaled_surface(
                    self.castle_upgrade_icon, 'castle_upgrade', icon_width, icon_height)
                scaled_icon = self._apply_icon_overlay(
                    base_icon, is_clicking, is_hovering, enabled=button_enabled)

                # Draw icon at button position
                self.screen.blit(scaled_icon, (castle_button_x, castle_button_y))

                # Draw icon border frame overlay if available
                # Border is 2px larger than icon (1px per side) to fully contain icon edges
                if self.icon_border:
                    scaled_border = self._get_cached_scaled_surface(
                        self.icon_border, 'icon_border', icon_width + 2, icon_height + 2)
                    self.screen.blit(scaled_border, (castle_button_x - 1, castle_button_y - 1))
            else:
                # Fallback to old text button
                if button_enabled:
                    if is_clicking:
                        button_color = brighten_color(button_color, 0.4)
                    elif is_hovering:
                        button_color = lighten_color(button_color, 0.2)

                # Draw button
                pygame.draw.rect(self.screen, button_color, upgrade_rect)
                pygame.draw.rect(self.screen, BLACK, upgrade_rect, 3, border_radius=5)

                # Draw icon/text - use "UPGRADE" text
                icon_text = self._get_cached_text("UPGRADE", self.font, WHITE)
                icon_text_rect = icon_text.get_rect(center=(upgrade_rect.centerx, upgrade_rect.centery - 10))
                self.screen.blit(icon_text, icon_text_rect)

                # Draw "TO CASTLE" below
                subtext = self._get_cached_text("TO CASTLE", self.small_font, WHITE)
                subtext_rect = subtext.get_rect(center=(upgrade_rect.centerx, upgrade_rect.centery + 10))
                self.screen.blit(subtext, subtext_rect)

            # Store button for click handling (only if enabled)
            if button_enabled:
                self.castle_upgrade_button = upgrade_rect
            else:
                self.castle_upgrade_button = None

            # Store hover state but don't call update_button_hover here
            # (will be called at the end of draw_keep_ui to avoid interference with hero_training hover)
            # Track hover even if button is disabled (to show tooltip explaining why it's disabled)
            self.castle_button_is_hovering = is_hovering
            self.castle_button_rect_for_hover = upgrade_rect if is_hovering else None

        # Update panel_y to account for two rows (keep the layout consistent)
        panel_y += (button_height * 2) + button_spacing + 15

        # === SEPARATOR AFTER CASTLE ===
        separator2_x = castle_button_x + castle_button_width + 20
        self.draw_separator(separator2_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # === SECTION 4: TRAINING STATUS ===
        queue_x = separator2_x + 20
        queue_y = BOTTOM_UI_Y + 30

        # PERFORMANCE: Use cached static text
        queue_title = self._get_cached_text("Training Status:", self.font, BROWN_TEXT_HEADING)
        self.screen.blit(queue_title, (queue_x, queue_y))
        queue_y += 30

        # Display training hero
        if is_training:
            # H3 fix: handle 3-tuple (hero_type, turns, paid_cost) from Audit #3 H1
            entry = self.game_state.hero_training_queue[territory][keep_plot_index]
            hero_type, turns_remaining = entry[0], entry[1]

            # Hero box
            item_rect = pygame.Rect(queue_x, queue_y, 280, 30)
            pygame.draw.rect(self.screen, (220, 220, 220), item_rect)
            pygame.draw.rect(self.screen, BLACK, item_rect, 1)

            # Hero name and progress
            turn_text = "turn" if turns_remaining == 1 else "turns"
            hero_text = self._get_cached_text(
                f"{hero_type} (training... {turns_remaining} {turn_text})",
                self.small_font, (0, 100, 0)
            )
            self.screen.blit(hero_text, (queue_x + 5, queue_y + 7))

            # Cancel button
            cancel_rect = pygame.Rect(queue_x + 250, queue_y + 5, 20, 20)
            button_color = (200, 100, 100)

            # Hover/click feedback
            is_hovering = cancel_rect.collidepoint(self.mouse_pos)
            is_clicking = (self.clicked_element and
                          self.clicked_element[0] == 'hero_cancel')

            if is_clicking:
                button_color = brighten_color(button_color, 0.4)
            elif is_hovering:
                button_color = lighten_color(button_color, 0.2)

            pygame.draw.rect(self.screen, button_color, cancel_rect)
            pygame.draw.rect(self.screen, BLACK, cancel_rect, 1)
            cancel_text = self._get_cached_text("X", self.small_font, WHITE)
            cancel_text_rect = cancel_text.get_rect(center=cancel_rect.center)
            self.screen.blit(cancel_text, cancel_text_rect)

            self.hero_cancel_button = cancel_rect
        else:
            empty_text = self._get_cached_text("No hero in training", self.small_font, BROWN_TEXT_SECONDARY)
            self.screen.blit(empty_text, (queue_x, queue_y))

        # === SEPARATOR BEFORE HERO INFO ===
        separator3_x = queue_x + 320
        self.draw_separator(separator3_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # === SECTION 5: HERO INFO & DEMOLISH ===
        tips_x = separator3_x + 20
        tips_y = BOTTOM_UI_Y + 30

        tips_title = self._get_cached_text("Hero Info", self.font, WHITE)
        self.screen.blit(tips_title, (tips_x, tips_y))
        tips_y += 35

        # Rules as bullet points with lighter color
        # Use extra small font at 720p to prevent overflow
        info_color = (200, 200, 200)  # Light gray, distinct from white header
        info_font = self.extra_small_font if WINDOW_HEIGHT == 720 else self.small_font

        rule1 = self._get_cached_text("- Each Hero can only be trained once.", info_font, info_color)
        self.screen.blit(rule1, (tips_x, tips_y))
        tips_y += 22

        rule2 = self._get_cached_text("- Each Keep or Castle can only have", info_font, info_color)
        self.screen.blit(rule2, (tips_x, tips_y))
        tips_y += 20
        rule2b = self._get_cached_text("  one Hero.", info_font, info_color)
        self.screen.blit(rule2b, (tips_x, tips_y))
        tips_y += 22

        rule3 = self._get_cached_text("- Heroes are slain upon Keep or", info_font, info_color)
        self.screen.blit(rule3, (tips_x, tips_y))
        tips_y += 20
        rule3b = self._get_cached_text("  Castle's destruction.", info_font, info_color)
        self.screen.blit(rule3b, (tips_x, tips_y))
        tips_y += 30

        # Demolish button
        demolish_rect = pygame.Rect(tips_x, tips_y, 180, 30)
        _, display_name = self.game_state.get_keep_display_info(territory, keep_plot_index)
        # Mission hook: grey out demolish only when the mission disallows it — the
        # same test the click handler uses. (It used to grey out for ANY active
        # mission, so Keeps looked undemolishable in missions that allow it.)
        _tutorial_demolish_locked = (self.tutorial_mission
                                     and self.tutorial_mission.active
                                     and not self.tutorial_mission.is_action_allowed('demolish'))
        if _tutorial_demolish_locked:
            self.draw_feedback_button(demolish_rect, (80, 80, 80),
                                      'demolish', 'keep',
                                      text=f"Demolish {display_name} (50%)",
                                      font=self.small_font, text_color=(120, 120, 120))
        else:
            self.draw_feedback_button(demolish_rect, (150, 100, 100),
                                      'demolish', 'keep',
                                      text=f"Demolish {display_name} (50%)",
                                      font=self.small_font)

        self.demolish_keep_button = demolish_rect
        self.demolish_keep_territory = territory
        self.demolish_keep_plot_index = keep_plot_index

        # Track button hover for tooltips (will be drawn with delay in main loop)
        mouse_pos = pygame.mouse.get_pos()
        current_hover = None
        for hero_type, button_rect in self.hero_train_buttons.items():
            if button_rect.collidepoint(mouse_pos):
                current_hover = ('hero_training', hero_type)
                break

        # Update hover tracking using helper
        self.update_button_hover(current_hover, 'hero_training')

        # Castle upgrade button hover tracking (must come AFTER hero_training to take precedence)
        castle_hovering = self.castle_button_is_hovering
        if castle_hovering:
            self.update_button_hover(('castle', 'castle_upgrade'), 'castle')
        else:
            # Clear castle hover when not hovering
            if self.hover_target_button and self.hover_target_button[0] == 'castle':
                self.update_button_hover(None, 'castle')

    def draw_army_composition_ui(self):
        """Draw army composition UI for individual army control (Phase 3)"""
        territory = self.army_composition_territory
        if not territory:
            return

        # Get units from the specific player's garrison (multi-garrison support)
        player = self.army_composition_player if self.army_composition_player is not None else self.game_state.current_player
        garrison = self.game_state.territory_garrisons.get(territory, {}).get(player)
        if not garrison:
            # No garrison for this player - close composition UI
            self.show_army_composition = False
            return

        units = garrison.get('units', [])

        # The unit context menu sits on top of this panel - nothing beneath it may
        # light up on hover, so hover tests below use hover_pos instead of mouse_pos.
        ctx_menu_rect = self._get_unit_context_menu_rect()
        hover_pos = (-1, -1) if (ctx_menu_rect and ctx_menu_rect.collidepoint(self.mouse_pos)) else self.mouse_pos

        # Count status
        ready_count = sum(1 for u in units if u['status'] == 'ready')
        moved_count = sum(1 for u in units if u['status'] == 'moved')
        ordered_count = sum(1 for u in units if u['status'] == 'ordered')
        total = len(units)

        # MIDDLE SECTION: Army composition info and controls - dynamic (21.875% of width)
        middle_x = int(WINDOW_WIDTH * 0.21875)  # Was 350 at 1600px width
        panel_y = BOTTOM_UI_Y + 30
        
        # Draw title (shortened to "Army:")
        # Use the garrison player's color, not the territory owner's
        # Use display name for campaign mission territory renaming
        display_territory = map_data.get_display_name(territory)
        player_color = self.game_state.get_player_color(player) if player != -1 else BROWN_TEXT_PRIMARY
        title_text = self._get_cached_text(f"Army: {display_territory}", self.large_font, player_color)
        self.screen.blit(title_text, (middle_x, panel_y))
        panel_y += UI_SECTION_SPACING

        # Total and status summary
        summary_text = self._get_cached_text(f"Total: {total} armies", self.font, BROWN_TEXT_PRIMARY)
        self.screen.blit(summary_text, (middle_x, panel_y))
        panel_y += UI_LINE_SPACING_SMALL

        status_text = self._get_cached_text(
            f"({ready_count} ready, {moved_count} moved, {ordered_count} ordered)",
            self.small_font, BROWN_TEXT_SECONDARY
        )
        self.screen.blit(status_text, (middle_x, panel_y))
        panel_y += UI_LINE_SPACING

        # Selection count
        if self.selected_army_units:
            selected_text = self._get_cached_text(
                f"Selected: {len(self.selected_army_units)} armies",
                self.small_font, (0, 120, 180)
            )
            self.screen.blit(selected_text, (middle_x, panel_y))
            panel_y += UI_LINE_SPACING_SMALL
        
        # Add extra spacing before buttons to avoid any potential interference
        panel_y += 10
        
        # Clear old button state before creating new buttons
        self.army_composition_buttons = []
        self.select_all_button = None
        self.deselect_all_button = None
        
        # Select All and Deselect All buttons
        button_y = panel_y
        
        # Select All button - scaled dimensions (110x25 at 1600x900)
        select_all_rect = pygame.Rect(middle_x, button_y, self.scale(110), self.scale(25))

        # Base color
        button_color = (100, 150, 200)
        # Check hover
        is_hovering = select_all_rect.collidepoint(hover_pos)
        # Check click
        is_clicking = (self.clicked_element and
                      self.clicked_element[0] == 'army_comp' and
                      self.clicked_element[1] == 'select_all')
        # Apply feedback
        if is_clicking:
            button_color = brighten_color(button_color, 0.4)
        elif is_hovering:
            button_color = lighten_color(button_color, 0.2)

        pygame.draw.rect(self.screen, button_color, select_all_rect)
        pygame.draw.rect(self.screen, BLACK, select_all_rect, 2)
        select_all_text = self._get_cached_text("Select All", self.small_font, WHITE)
        text_rect = select_all_text.get_rect(center=select_all_rect.center)
        self.screen.blit(select_all_text, text_rect)
        self.select_all_button = select_all_rect

        # Deselect All button (next to Select All) - scaled
        deselect_all_rect = pygame.Rect(middle_x + self.scale(120), button_y, self.scale(110), self.scale(25))

        # Base color
        button_color = (150, 100, 100)
        # Check hover
        is_hovering = deselect_all_rect.collidepoint(hover_pos)
        # Check click
        is_clicking = (self.clicked_element and
                      self.clicked_element[0] == 'army_comp' and
                      self.clicked_element[1] == 'deselect_all')
        # Apply feedback
        if is_clicking:
            button_color = brighten_color(button_color, 0.4)
        elif is_hovering:
            button_color = lighten_color(button_color, 0.2)

        pygame.draw.rect(self.screen, button_color, deselect_all_rect)
        pygame.draw.rect(self.screen, BLACK, deselect_all_rect, 2)
        deselect_all_text = self._get_cached_text("Deselect All", self.small_font, WHITE)
        text_rect = deselect_all_text.get_rect(center=deselect_all_rect.center)
        self.screen.blit(deselect_all_text, text_rect)
        self.deselect_all_button = deselect_all_rect
        
        # Draw vertical separator line between middle and right sections
        separator_x = middle_x + 450  # Increased from 375 to 450 for very long names
        self.draw_separator(separator_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)
        
        # RIGHT SECTION: Army button grid
        grid_x = separator_x + self.scale(20)
        grid_y = BOTTOM_UI_Y + self.scale(30)

        # Draw army buttons (grid: 5 per row, max 3 rows) - scaled
        button_size = self.scale(45)
        button_spacing = self.scale(5)
        buttons_per_row = 5
        # Veterancy: XP bar and shields drawn OVER the button icon (no extra vertical space)
        xp_bar_height = self.scale(3)   # Height of XP progress bar (overlaid at bottom edge)
        row_height = button_size + button_spacing  # No extra space needed

        # Track if any unit button is being hovered (for tooltip clearing)
        any_unit_hovered = False

        for i, unit in enumerate(units):
            # Calculate button position (offset by shield height for shields above)
            col = i % buttons_per_row
            row = i // buttons_per_row

            btn_x = grid_x + col * (button_size + button_spacing)
            btn_y = grid_y + row * row_height

            button_rect = pygame.Rect(btn_x, btn_y, button_size, button_size)

            # Get unit type and its letter
            unit_type = unit.get('type', 'Swordsman')
            unit_letter = self.game_state.UNIT_TYPES[unit_type]['letter']

            # Check hover and click state
            is_hovering = button_rect.collidepoint(hover_pos)
            is_clicking = (self.clicked_element and
                          self.clicked_element[0] == 'army_unit' and
                          self.clicked_element[1] == unit['id'])

            # Track hover for tooltip (includes veterancy info)
            if is_hovering:
                any_unit_hovered = True
                unit_status = unit['status'].capitalize()
                u_level = unit.get('level', 0)
                u_xp = unit.get('xp', 0)
                current_hover = ('army_unit_tooltip', (unit_type, unit_status, u_level, u_xp))
                self.update_button_hover(current_hover, 'army_unit_tooltip')

            # Get unit icon
            unit_icon = self.unit_icons.get(unit_type)

            if unit_icon:
                # C2 fix: Use cached scaling for unit icons
                icon_size = button_size - 2
                base_icon = self._get_cached_scaled_surface(
                    unit_icon, f'unit_{unit_type}', icon_size, icon_size)

                # Determine status-based tint
                unit_status = unit['status']
                if unit_status == 'moved':
                    scaled_icon = self._apply_icon_overlay(
                        base_icon, is_clicking, is_hovering,
                        enabled=False, disabled_tint=(128, 128, 128, 180))
                elif unit_status == 'ordered':
                    scaled_icon = self._apply_icon_overlay(
                        base_icon, is_clicking, is_hovering,
                        enabled=False, disabled_tint=(255, 255, 100, 100))
                else:
                    # 'ready' status - full color, just hover/click effects
                    scaled_icon = self._apply_icon_overlay(
                        base_icon, is_clicking, is_hovering)

                icon_rect = scaled_icon.get_rect(center=button_rect.center)
                self.screen.blit(scaled_icon, icon_rect)

                # C2 fix: Use cached border scaling
                # Border is 2px larger than icon (1px per side) to fully contain icon edges
                if self.icon_border:
                    scaled_border = self._get_cached_scaled_surface(
                        self.icon_border, 'icon_border', icon_size + 2, icon_size + 2)
                    border_rect = scaled_border.get_rect(center=button_rect.center)
                    self.screen.blit(scaled_border, border_rect)

                # Draw selection border around the icon if selected (keeps icon fully visible)
                if unit['id'] in self.selected_army_units:
                    pygame.draw.rect(self.screen, (255, 215, 0), button_rect, 3)  # Gold border
            else:
                # Fallback to letter with colored background/border if icon not available
                if unit['id'] in self.selected_army_units:
                    fill_color = (255, 215, 0)
                else:
                    fill_color = (235, 230, 210)

                # Apply hover/click feedback to fill color
                if is_clicking:
                    fill_color = brighten_color(fill_color, 0.4)
                elif is_hovering:
                    fill_color = lighten_color(fill_color, 0.2)

                # Border color based on status ONLY (no unit type colors)
                if unit['status'] == 'ready':
                    border_color = (0, 200, 0)  # Green - can command
                    border_width = 3
                elif unit['status'] == 'moved':
                    border_color = (100, 100, 100)  # Gray - exhausted
                    border_width = 2
                elif unit['status'] == 'ordered':
                    border_color = (200, 200, 0)  # Yellow - has order
                    border_width = 3
                else:
                    border_color = (150, 150, 150)  # Default gray
                    border_width = 2

                # Draw button
                pygame.draw.rect(self.screen, fill_color, button_rect)
                pygame.draw.rect(self.screen, border_color, button_rect, border_width)

                # Draw unit type letter (centered)
                unit_text = self._get_cached_text(unit_letter, self.font, BLACK)
                text_rect = unit_text.get_rect(center=button_rect.center)
                self.screen.blit(unit_text, text_rect)

            # --- Veterancy: Draw XP bar overlaid at bottom edge of button ---
            unit_xp = unit.get('xp', 0)
            unit_level = unit.get('level', 0)
            bar_h = xp_bar_height
            # Inset the bar inside the icon, above the border
            bar_inset_x = self.scale(4)   # ~10% narrower from each side
            bar_inset_y = self.scale(5)   # 3px higher, sits inside icon above border
            bar_width = button_size - bar_inset_x * 2
            bar_y = btn_y + button_size - bar_h - bar_inset_y

            # Calculate fill ratio within current level
            if unit_level < self.game_state.MAX_LEVEL:
                prev_threshold = self.game_state.LEVEL_XP_CUMULATIVE[unit_level - 1] if unit_level > 0 else 0
                next_threshold = self.game_state.LEVEL_XP_CUMULATIVE[unit_level]
                xp_in_level = unit_xp - prev_threshold
                xp_needed = next_threshold - prev_threshold
                fill_ratio = max(0.0, min(1.0, xp_in_level / xp_needed)) if xp_needed > 0 else 0.0
            else:
                fill_ratio = 1.0  # Max level = full bar

            # Draw bar background (dark brown, semi-transparent look)
            pygame.draw.rect(self.screen, (60, 50, 40), (btn_x + bar_inset_x, bar_y, bar_width, bar_h))
            # Draw bar fill (brass/gold color)
            fill_w = int(bar_width * fill_ratio)
            if fill_w > 0:
                pygame.draw.rect(self.screen, (185, 155, 80), (btn_x + bar_inset_x, bar_y, fill_w, bar_h))

            # --- Veterancy: Draw level shield icons overlaid at top edge of button ---
            if unit_level > 0 and self.level_shield_icon:
                shield_icon_size = self.scale(8)  # Smaller to fit inside button
                cached_shield = self._get_cached_scaled_surface(
                    self.level_shield_icon, 'level_shield_sm', shield_icon_size, shield_icon_size)
                # Pack shields tightly together, centered horizontally on button
                total_shields_w = unit_level * shield_icon_size
                shield_start_x = btn_x + (button_size - total_shields_w) // 2
                sy = btn_y + self.scale(2)  # Slight inset from top edge
                for lv in range(unit_level):
                    sx = shield_start_x + lv * shield_icon_size
                    self.screen.blit(cached_shield, (sx, sy))

            # Store button for click detection
            self.army_composition_buttons.append((button_rect, unit['id']))

        # Clear tooltip if no unit is being hovered (prevents tooltip from persisting)
        # Purpose: Fix bug where unit tooltips would stick even after moving mouse away
        if not any_unit_hovered:
            self.update_button_hover(None, 'army_unit_tooltip')

        # Third separator line between grid and instructions
        grid_width = buttons_per_row * (button_size + button_spacing)
        instructions_separator_x = grid_x + grid_width + 15
        self.draw_separator(instructions_separator_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)
        
        # INSTRUCTIONS SECTION: To the right of third separator
        instructions_x = instructions_separator_x + 15
        instructions_y = grid_y

        # PERFORMANCE: Cache static instruction text renders
        header_text = self._get_cached_text("Unit Selection Info:", self.font_bold, WHITE)
        self.screen.blit(header_text, (instructions_x, instructions_y))
        instructions_y += self.scale(30)  # Space after header

        # Instruction lines - each point on one line
        instruction_lines = [
            "- Click to select",
            "- CTRL+Click for multi-select",
            "- Right-click unit for options",
            "- Right-click destination",
            "  to command",
            "- Click elsewhere to close"
        ]

        # Bounds-check: the list grew with the right-click hint, so stop before
        # spilling past the bottom panel on short layouts (min panel height is 180px).
        line_spacing = self.scale(22)
        max_instructions_y = BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - line_spacing

        for line in instruction_lines:
            if instructions_y > max_instructions_y:
                break
            inst_text = self._get_cached_text(line, self.small_font, BROWN_TEXT_SECONDARY)
            self.screen.blit(inst_text, (instructions_x, instructions_y))
            instructions_y += line_spacing
    
    # ------------------------------------------------------------------
    # Unit right-click context menu (army composition strip)
    # Purpose: give mouse-only players a way to build partial garrison
    # selections without holding CTRL. Right-clicking a unit icon opens a
    # small drop-down anchored to that icon.
    # ------------------------------------------------------------------

    def handle_unit_context_menu_right_click(self, pos):
        """
        Open (or close) the unit context menu on right-click in the bottom UI.

        Hooked into the main event loop BEFORE the planning-phase gate, so the
        menu behaves like the existing left-click selection, which is only
        gated on phase == 'playing'.

        Args:
            pos: Right-click position (x, y)

        Returns:
            bool: True if the click was consumed (menu opened or closed)
        """
        # Any right-click while the menu is open just dismisses it, with no action,
        # and is consumed - the same contract as a left-click outside the menu. A
        # dismissing right-click on the map must not also issue a movement order.
        if self.unit_context_menu:
            self.unit_context_menu = None
            return True

        # Same guards as handle_bottom_ui_click: playing phase, bottom UI area,
        # not spectating, composition strip actually on screen.
        if self.game_state.phase != 'playing' or pos[1] < BOTTOM_UI_Y:
            return False
        if not self.is_local_player_active():
            return False
        if not self.show_army_composition or not self.army_composition_buttons:
            return False

        # Hit-test the unit icon grid built by draw_army_composition_ui()
        for button_rect, unit_id in self.army_composition_buttons:
            if not button_rect.collidepoint(pos):
                continue

            # Build the option list. "Other" = any selected unit that isn't this one.
            # Opening the menu on a 'moved'/'ordered' unit is allowed, matching
            # plain left-click which also selects any unit regardless of status.
            others = [uid for uid in self.selected_army_units if uid != unit_id]
            items = [('select', 'Select')]
            if others:
                if unit_id in self.selected_army_units:
                    # Already part of the group - CTRL+click would remove it,
                    # so label it honestly.
                    items.append(('toggle', 'Remove from Group'))
                else:
                    items.append(('toggle', 'Add to Group'))
            items.append(('cancel', 'Cancel'))

            # Remember which garrison this menu belongs to so a stale menu
            # (units moved, turn ended, strip closed) can be detected at draw time.
            self.unit_context_menu = {
                'unit_id': unit_id,
                'territory': self.army_composition_territory,
                'player': (self.army_composition_player
                           if self.army_composition_player is not None
                           else self.game_state.current_player),
                'anchor': button_rect.copy(),
                'items': items,
            }
            return True

        return False

    def _get_unit_context_menu_rect(self):
        """
        Derive the context menu panel rect (returns None when closed).

        Single source of geometry for both drawing and hit-testing so the two
        can never desync (same idiom as integrated_setup._get_dropdown_items_rects).

        Returns:
            pygame.Rect or None: the full menu panel bounds
        """
        menu = self.unit_context_menu
        if not menu:
            return None

        item_h = self.scale(24)
        pad = self.scale(4)

        # Width follows the widest label, with a sensible minimum
        text_w = max(self.small_font.size(label)[0] for _, label in menu['items'])
        width = max(self.scale(120), text_w + self.scale(24))
        height = len(menu['items']) * item_h + pad * 2

        anchor = menu['anchor']
        overlap = self.scale(6)  # Slight overlap onto the icon corner

        # Preferred placement: down and to the right of the icon
        rect = pygame.Rect(anchor.right - overlap, anchor.bottom - overlap, width, height)

        # Flip up when it would run off the bottom of the screen (opens over the map)
        if rect.bottom > WINDOW_HEIGHT:
            rect.bottom = anchor.top + overlap

        # Clamp horizontally so the panel always stays fully on screen
        if rect.right > WINDOW_WIDTH - self.scale(4):
            rect.right = WINDOW_WIDTH - self.scale(4)
        if rect.left < 0:
            rect.left = 0
        # Vertical clamp as a safety net (tiny windows / very tall menus)
        if rect.top < 0:
            rect.top = 0

        return rect

    def _close_stale_unit_context_menu(self):
        """
        Drop the context menu if the garrison it points at is gone.

        Called at the start of draw_unit_context_menu(), which runs every frame
        before the next frame's input, so a stale menu can never consume a click.
        """
        menu = self.unit_context_menu
        if not menu:
            return

        if not self.show_army_composition:
            self.unit_context_menu = None
            return

        current_player = (self.army_composition_player
                          if self.army_composition_player is not None
                          else self.game_state.current_player)
        if menu['territory'] != self.army_composition_territory or menu['player'] != current_player:
            self.unit_context_menu = None
            return

        garrison = self.game_state.territory_garrisons.get(menu['territory'], {}).get(menu['player'])
        if not garrison:
            self.unit_context_menu = None
            return
        if not any(u['id'] == menu['unit_id'] for u in garrison.get('units', [])):
            self.unit_context_menu = None

    def draw_unit_context_menu(self):
        """
        Draw the unit context menu on top of everything in the bottom UI.

        Called late in the render pass (alongside the other popups) so the
        drop-down is never covered - the same "draw dropdown options last" rule
        the options menu resolution dropdown follows.
        """
        self._close_stale_unit_context_menu()

        menu_rect = self._get_unit_context_menu_rect()
        if menu_rect is None:
            self.unit_context_menu_rects = []
            return

        menu = self.unit_context_menu
        item_h = self.scale(24)
        pad = self.scale(4)

        # Panel: dark background with a thin golden border
        pygame.draw.rect(self.screen, (40, 35, 30), menu_rect)
        pygame.draw.rect(self.screen, (218, 165, 32), menu_rect, max(1, self.scale(1)))

        # Rebuild hit-test rects every frame from the same geometry we draw with
        self.unit_context_menu_rects = []

        # Explicit highlight colours rather than lighten_color()/brighten_color():
        # those scale multiplicatively, so on a near-black panel (40, 35, 30) they
        # move each channel by only a few points and the feedback is invisible.
        hover_color = (82, 72, 55)    # Warm brown - clearly lighter than the panel
        click_color = (150, 126, 76)  # Brass - stronger still, for the click flash

        for i, (action_id, label) in enumerate(menu['items']):
            item_rect = pygame.Rect(
                menu_rect.x + pad,
                menu_rect.y + pad + i * item_h,
                menu_rect.width - pad * 2,
                item_h
            )

            # Hover/click feedback using the standard bottom-UI treatment
            is_clicking = (self.clicked_element
                           and self.clicked_element[0] == 'unit_ctx'
                           and self.clicked_element[1] == action_id)
            is_hovering = item_rect.collidepoint(self.mouse_pos)

            if is_clicking:
                pygame.draw.rect(self.screen, click_color, item_rect)
            elif is_hovering:
                pygame.draw.rect(self.screen, hover_color, item_rect)

            label_surface = self._get_cached_text(label, self.small_font, WHITE)
            label_rect = label_surface.get_rect(
                midleft=(item_rect.x + self.scale(8), item_rect.centery))
            self.screen.blit(label_surface, label_rect)

            self.unit_context_menu_rects.append((item_rect, action_id))

    def handle_unit_context_menu_click(self, pos):
        """
        Handle a left-click while the unit context menu is open.

        The menu is modal: every click is consumed and always closes the menu.
        Clicking outside it closes with no action.

        Args:
            pos: Click position (x, y)

        Returns:
            bool: always True (click consumed)
        """
        self._close_stale_unit_context_menu()

        menu = self.unit_context_menu
        if not menu:
            return True

        unit_id = menu['unit_id']

        for item_rect, action_id in self.unit_context_menu_rects:
            if not item_rect.collidepoint(pos):
                continue

            self.trigger_click_flash('unit_ctx', action_id)

            if action_id == 'select':
                # Same as a plain left-click: replace the whole selection
                self.selected_army_units = [unit_id]
            elif action_id == 'toggle':
                # Same as CTRL+click: toggle this unit in/out of the selection
                if unit_id in self.selected_army_units:
                    self.selected_army_units.remove(unit_id)
                else:
                    self.selected_army_units.append(unit_id)
            # 'cancel' falls through - close with no action
            break

        self.unit_context_menu = None
        return True

    def draw_action_log_overlay(self):
        """Draw action log as an overlay on the right side of the screen"""
        if not self.action_log_visible:
            return
        
        # Overlay dimensions
        overlay_width = 300
        overlay_height = 400
        overlay_x = WINDOW_WIDTH - overlay_width - 20
        overlay_y = 50
        
        # PERFORMANCE: Reuse cached action log background surface
        if self._cached_action_log_surface is None or self._cached_action_log_surface.get_size() != (overlay_width, overlay_height):
            self._cached_action_log_surface = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
            pygame.draw.rect(self._cached_action_log_surface, (40, 40, 40, 230), (0, 0, overlay_width, overlay_height))
            pygame.draw.rect(self._cached_action_log_surface, WHITE, (0, 0, overlay_width, overlay_height), 2)
        self.screen.blit(self._cached_action_log_surface, (overlay_x, overlay_y))
        
        # PERFORMANCE: Cache static title and close button text
        title_text = self._get_cached_text("Action Log", self.font, WHITE)
        self.screen.blit(title_text, (overlay_x + 10, overlay_y + 10))

        # Close button
        close_rect = pygame.Rect(overlay_x + overlay_width - 30, overlay_y + 5, 25, 25)
        pygame.draw.rect(self.screen, (200, 100, 100), close_rect)
        pygame.draw.rect(self.screen, WHITE, close_rect, 1)
        close_text = self._get_cached_text("X", self.font, WHITE)
        close_text_rect = close_text.get_rect(center=close_rect.center)
        self.screen.blit(close_text, close_text_rect)
        self.action_log_close_button = close_rect
        
        # Messages — M4 fix: stop rendering past overlay bottom
        msg_y = overlay_y + 45
        max_msg_y = overlay_y + overlay_height - 10
        for message in self.game_state.messages:
            if msg_y >= max_msg_y:
                break
            # Wrap long messages
            if len(message) > 35:
                words = message.split()
                line = ""
                for word in words:
                    test_line = line + " " + word if line else word
                    if len(test_line) > 35:
                        if msg_y >= max_msg_y:
                            break
                        msg_text = self._get_cached_text(line, self.small_font, WHITE)
                        self.screen.blit(msg_text, (overlay_x + 10, msg_y))
                        msg_y += 20
                        line = word
                    else:
                        line = test_line
                if line and msg_y < max_msg_y:
                    msg_text = self._get_cached_text(line, self.small_font, WHITE)
                    self.screen.blit(msg_text, (overlay_x + 10, msg_y))
                    msg_y += 20
            else:
                msg_text = self._get_cached_text(message, self.small_font, WHITE)
                self.screen.blit(msg_text, (overlay_x + 10, msg_y))
                msg_y += 20
    
    def draw_victory_screen(self):
        """Draw the victory screen overlay"""
        # PERFORMANCE: Reuse cached overlay instead of allocating full-screen SRCALPHA every frame
        if self._cached_victory_overlay is None or self._cached_victory_overlay.get_size() != (WINDOW_WIDTH, WINDOW_HEIGHT):
            self._cached_victory_overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(self._cached_victory_overlay, (0, 0, 0, 180), (0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))
        self.screen.blit(self._cached_victory_overlay, (0, 0))
        
        # Victory text
        # Phase 7: Victory message uses Cinzel SemiBold 72px for entire message
        winner_color = self.game_state.get_player_color(self.game_state.winner)
        victory_font = self.font_manager.get_bold_font(72)
        winner_name = self.game_state.get_player_name(self.game_state.winner)
        victory_text = self._get_cached_text(f"{winner_name} WINS!", victory_font, winner_color)
        victory_rect = victory_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 50))
        self.screen.blit(victory_text, victory_rect)

        # Return to Main Menu button
        button_width = 280
        button_height = 50
        menu_button_rect = pygame.Rect(
            WINDOW_WIDTH // 2 - button_width // 2,
            WINDOW_HEIGHT // 2 + 50,
            button_width,
            button_height
        )
        pygame.draw.rect(self.screen, (100, 150, 200), menu_button_rect)
        pygame.draw.rect(self.screen, WHITE, menu_button_rect, 3)

        menu_button_text = self._get_cached_text("Return to Main Menu", self.large_font, WHITE)
        text_rect = menu_button_text.get_rect(center=menu_button_rect.center)
        self.screen.blit(menu_button_text, text_rect)

        self.main_menu_button = menu_button_rect
    
    # Pixels of map over-rendered beyond the viewport on each side, so that panning
    # re-blits a cached surface at a new offset instead of rescaling every frame.
    # Larger = fewer rebuilds while panning, but more pixels scaled per rebuild.
    _MAP_VIEW_MARGIN = 192

    def _invalidate_map_background_caches(self):
        """Drop every cache derived from map_image_original.

        Call after the background is replaced (map switch), re-converted (display
        change) or drawn into in place (mission cloud-cover bakes). The in-place case
        keeps id(map_image_original) unchanged, so the id-keyed caches cannot notice
        it on their own.
        """
        self.cached_scaled_map = None
        self.cached_zoom_level = None
        self._map_view_key = None
        self._map_view_surface = None
        extension = getattr(self, 'map_east_extension', None)
        if extension is not None:
            extension.invalidate()

    def _blit_map_east_extension(self, map_right, map_y, scaled_map_width,
                                 scaled_map_height, vis_top, vis_bottom):
        """Draw the east map extension in the strip right of the map background.

        Built lazily (first time a gap is visible) rather than at map load, so a
        mission that bakes cloud cover into the map in its __init__ is included.
        See rendering/map_extension.py.
        """
        src = self.map_image_original
        extension = self.map_east_extension
        try:
            extension.ensure_built(
                src, self.screen.get_width(), self.map_width,
                getattr(self.camera, 'min_zoom', self.camera_min_zoom),
                east_extension_override_path(getattr(self, 'map_background_path', None)))
        except (pygame.error, ValueError) as exc:
            # Never let a bad extension break the map: the draw below falls back to fog
            logger.warning(f"Could not build map east extension: {exc}")
        extension.draw(self.screen, map_right, map_y, scaled_map_width, scaled_map_height,
                       src.get_width(), vis_top, vis_bottom, margin=self._MAP_VIEW_MARGIN)

    def _blit_map_background(self):
        """
        Scale and blit ONLY the visible slice of the map background.

        PERFORMANCE — this replaces scaling the ENTIRE map on every zoom change.
        The old path built a surface of (map_width * zoom, map_height * zoom) from
        the 4096x3072 source, so its cost grew as zoom squared even though at most
        a viewport-sized slice is ever visible. At 1600x900 that is 1.53M pixels at
        zoom 1.65 but 8.98M pixels (36MB) at zoom 4.0. Measured:

            full-map   scale -> 3732x2800 : 16.1 ms      (nearest-neighbour)
            full-map   smoothscale        : 53.1 ms      <- a 53ms hitch, ~19 FPS
            viewport   scale  -> 1920x700 :  0.31 ms
            viewport   smoothscale        :  2.50 ms

        Because the viewport smoothscale is affordable every frame, quality no
        longer has to be traded away while moving: the old code fell back to
        nearest-neighbour during zoom animations and then paid one full-map
        smoothscale when the zoom settled (a guaranteed hitch). We now smoothscale
        always, and cache the result so a stationary camera costs nothing.

        Map-agnostic by design: the source rect is derived from the ACTUAL source
        surface size, not the ORIGINAL_MAP_* constants, so maps whose background
        differs in size (and the black fallback surface) work unchanged.
        """
        zoom = self.camera_zoom
        src = self.map_image_original
        src_w, src_h = src.get_size()

        scaled_map_width = int(self.map_width * zoom)
        scaled_map_height = int(self.map_height * zoom)
        if scaled_map_width <= 0 or scaled_map_height <= 0 or src_w <= 0 or src_h <= 0:
            return

        # Where the whole map would sit on screen (negative: camera moves opposite)
        map_x = int(-self.camera_offset[0] * zoom)
        map_y = int(-self.camera_offset[1] * zoom) + TOP_PANEL_HEIGHT

        # Intersect the map rect with the visible map area. Clipping at BOTTOM_UI_Y
        # also avoids scaling the strip that the bottom panel draws over anyway.
        view_bottom = BOTTOM_UI_Y if BOTTOM_UI_Y else (TOP_PANEL_HEIGHT + MAP_HEIGHT)
        vis_left = max(map_x, 0)
        vis_top = max(map_y, TOP_PANEL_HEIGHT)
        vis_right = min(map_x + scaled_map_width, self.screen.get_width())
        vis_bottom = min(map_y + scaled_map_height, view_bottom)

        # Zoomed far out, the (left-aligned) map ends before the window's right edge.
        # Fill that strip with the east extension instead of the frame's white fill —
        # it used to be hidden by the right sidebar, which can now collapse. Done
        # before the early return below so it also covers a map panned off-screen.
        map_right = map_x + scaled_map_width
        if map_right < self.screen.get_width():
            self._blit_map_east_extension(map_right, map_y, scaled_map_width,
                                          scaled_map_height, vis_top, vis_bottom)

        dest_w = int(vis_right - vis_left)
        dest_h = int(vis_bottom - vis_top)
        if dest_w <= 0 or dest_h <= 0:
            return  # Map entirely off-screen; screen.fill() already painted the gap

        # Work in "scaled-map space": offsets relative to the map's top-left corner.
        # These are stable while the camera pans (only map_x/map_y shift), which is
        # what lets a cached region survive panning.
        want_x0 = vis_left - map_x
        want_y0 = vis_top - map_y
        want_x1 = vis_right - map_x
        want_y1 = vis_bottom - map_y

        # Over-render by a margin so small pans re-blit the cached surface at a new
        # offset instead of rescaling. Without this, panning rescaled EVERY frame —
        # measured as a regression from 69.8 to 49.9 FPS, because the previous
        # full-map cache happened to make panning free (only the blit position moved).
        # A rebuild is now needed only when the view leaves the margin or zoom changes.
        cached = self._map_view_key
        reusable = (
            cached is not None
            and self._map_view_surface is not None
            and cached[0] == id(src)
            and cached[1] == zoom
            and cached[2] <= want_x0 and cached[3] <= want_y0
            and cached[4] >= want_x1 and cached[5] >= want_y1
        )

        if not reusable:
            # Only pay for the margin when it can actually be reused. While the zoom
            # is changing every frame the cache is invalidated regardless, so the
            # extra pixels are pure waste (measured: ~25% off continuous-zoom FPS).
            # Panning at a fixed zoom is where the margin earns its keep.
            zoom_unchanged = cached is not None and cached[1] == zoom
            margin = self._MAP_VIEW_MARGIN if zoom_unchanged else 0
            reg_x0 = int(max(0, want_x0 - margin))
            reg_y0 = int(max(0, want_y0 - margin))
            reg_x1 = int(min(scaled_map_width, want_x1 + margin))
            reg_y1 = int(min(scaled_map_height, want_y1 + margin))
            region_w = max(1, reg_x1 - reg_x0)
            region_h = max(1, reg_y1 - reg_y0)

            x_ratio = src_w / scaled_map_width
            y_ratio = src_h / scaled_map_height

            src_x = max(0, min(src_w - 1, int(reg_x0 * x_ratio)))
            src_y = max(0, min(src_h - 1, int(reg_y0 * y_ratio)))
            # ceil the span so we never sample fewer source pixels than we cover
            src_w_slice = max(1, min(src_w - src_x, int(math.ceil(region_w * x_ratio))))
            src_h_slice = max(1, min(src_h - src_y, int(math.ceil(region_h * y_ratio))))

            # Reuse the destination surface while its size is unchanged, so repeated
            # rebuilds (e.g. continuous zooming) do not allocate every frame.
            if (self._map_view_surface is None
                    or self._map_view_surface.get_size() != (region_w, region_h)):
                self._map_view_surface = pygame.Surface((region_w, region_h)).convert()

            sub = src.subsurface(pygame.Rect(src_x, src_y, src_w_slice, src_h_slice))
            pygame.transform.smoothscale(sub, (region_w, region_h), self._map_view_surface)
            self._map_view_key = (id(src), zoom, reg_x0, reg_y0, reg_x0 + region_w, reg_y0 + region_h)
            self._map_view_offset = (reg_x0, reg_y0)

        # Blit at the cached region's CURRENT screen position. Overdraw beyond the
        # map area is harmless — the top/bottom panels are drawn after the map.
        off_x, off_y = self._map_view_offset
        self.screen.blit(self._map_view_surface, (map_x + off_x, map_y + off_y))

    def draw(self):
        """Render a single frame (core rendering pipeline extracted from run() for benchmarking)."""
        self.screen.fill(WHITE)

        # Draw map with camera transform (viewport-only rescale)
        self._blit_map_background()

        # Draw map elements (Phase 4D: inlined from delegate methods)
        self.map_renderer.draw_territories()
        self.map_renderer.draw_movement_arrows()
        self.map_renderer.draw_battle_markers()
        self.map_renderer.draw_alliance_markers()
        self.map_renderer.draw_overflow_indicators()

        # Draw UI panels (Phase 4D: inlined from delegate method)
        self.ui_renderer.draw_top_panel()
        self.draw_order_sidebar()
        self.draw_bottom_ui()

    def _cleanup(self):
        """Clean up network resources on game exit.
        Safe to call multiple times (idempotent). Called from run() exit path.
        Note: replay/logger finalization is handled by show_recap_if_ended(), not here."""
        # Close network connection if still active
        if self.network_connection is not None:
            try:
                if hasattr(self.network_connection, 'stop'):
                    self.network_connection.stop()
                elif hasattr(self.network_connection, 'disconnect'):
                    self.network_connection.disconnect()
            except Exception:
                pass  # Best-effort cleanup on exit
            self.network_connection = None

    def run(self):
        """
        Main game loop - handles events, updates state, and renders frames.
        
        This is the core game loop that runs at 60 FPS. It handles:
        1. Event processing (clicks, hover, keyboard)
        2. Game state updates (battles, construction, income)
        3. Frame rendering (map, UI, tooltips)
        4. FPS timing
        
        The method contains the complete event handling system with priority-based
        click detection and tooltip management. It's a large method (483 lines)
        that should be refactored in Phase 2.
        
        Event Handling Priority:
        1. Victory screen buttons (if game ended)
        2. Battle popup buttons (if popup visible)
        3. Bottom UI buttons (training, building, orders)
        4. Army composition circle (opens army UI)
        5. Building icons (quick-build from map)
        6. Training icons (quick-train from map)
        7. Plot selection
        8. Territory selection
        
        Rendering Order:
        1. Background color
        2. Territory polygons
        3. Territory overlays (highlights)
        4. Movement arrows
        5. Battle markers
        6. Building plots and icons
        7. Bottom UI panel
        8. Territory info panel
        9. Tooltips (hover-based)
        10. Battle popup (if visible)
        11. Victory screen (if game ended)
        
        Side Effects:
        - Updates self.running flag
        - Modifies game_state on player actions
        - Changes UI state (selected territory, plot, etc.)
        - Manages tooltip display state
        
        Note: This method is synchronous and blocks until the game exits.
        """
        logger.info("\n" + "="*60)
        logger.debug("[DEBUG] GAME STARTED - DEBUG VERSION ACTIVE")
        logger.info("="*60)
        logger.debug(f"[DEBUG] MAP_HEIGHT = {MAP_HEIGHT}")
        logger.debug(f"[DEBUG] WINDOW_HEIGHT = {WINDOW_HEIGHT}")
        running = True
        self.return_to_main_menu = False  # Flag for returning to main menu

        # Reset planning and game timers so they start from now (after loading screen),
        # not from when initialize_game() was called during deferred loading
        self.game_start_time = time.time()
        if self.game_state and self.game_state.planning_phase_start_time is not None:
            self.game_state.planning_phase_start_time = time.time()
        # Simultaneous mode: reset sim_state timer too
        if self.sim_state is not None and hasattr(self.sim_state, 'timer_start_time'):
            self.sim_state.timer_start_time = time.monotonic()
            self.sim_state.planning_phase_start_time = time.monotonic()

        # Reset clock timer before game loop starts
        # Call tick() twice so get_time() has valid previous tick reference
        self.clock.tick()
        self.clock.tick()
        # Seed the float frame clock used for delta_time (see below)
        self._last_frame_time = time.perf_counter()

        while running:
            # Calculate delta time for animations
            # Use a float clock rather than Clock.get_time(), which returns INTEGER
            # milliseconds. At high frame rates that quantization is severe: measured
            # in an uncapped loop, 100% of frames reported delta_time == 0.0 and the
            # summed delta ran at 250% of real time. Even at 1-2ms frames the error
            # is up to 50% per frame, which visibly changes animation speed.
            _now = time.perf_counter()
            delta_time = _now - self._last_frame_time
            self._last_frame_time = _now
            # Cap delta_time to prevent animation jumps on first frame or frame drops
            delta_time = min(delta_time, 0.1)  # Max 100ms per frame

            # Process sound queue (play queued sounds sequentially)
            self.sound_manager.process_sound_queue()

            # Process Steam callbacks (overlay notifications, achievement popups)
            steam_manager.run_callbacks()

            # Process network messages (multiplayer)
            if self.multiplayer_mode:
                self._process_network_messages()

            # While paused, shift wall-clock timers forward by delta_time each frame
            # so get_remaining_planning_time() stays frozen (counteracts advancing time.time())
            if self.is_game_paused:
                if (self.game_state and self.game_state.planning_phase_start_time is not None):
                    self.game_state.planning_phase_start_time += delta_time
                if (self.sim_state is not None and
                        self.sim_state.planning_phase_start_time is not None):
                    self.sim_state.planning_phase_start_time += delta_time

            # === GAME UPDATE SECTION (skipped when paused in single-player) ===
            if not self.is_game_paused:
                # Update army movement animations
                self.game_state.update_animations(delta_time)

                # Simultaneous mode: Check if animations just completed during execution phase
                if (self.sim_state is not None and
                    self.sim_state.sim_phase == 'executing' and
                    not self.game_state.active_animations and
                    self.sim_state.phase_manager is not None and
                    not self.sim_state.phase_manager.animations_complete):
                    logger.info(f"[MAIN] Animations complete in sim mode, calling on_animations_complete")
                    self.sim_state.phase_manager.on_animations_complete()

                # Update hero ability bubble animations (unified system)
                for effect_key in self._bubble_configs:
                    self._update_hero_bubbles(effect_key, delta_time)

                # Update castle upgrade particle effects
                self.map_renderer.update_castle_upgrade_effects(delta_time)

                # Update hero ability visual effects (burst + arc particles)
                self.map_renderer.update_ability_effects(delta_time)

                # Sync and update embargo persistent bubble effects
                self.map_renderer.sync_embargo_effects()
                self.map_renderer.update_embargo_effects(delta_time)

                # Sync and update production glow effects (for buildings with active training)
                self.map_renderer.sync_production_glow_effects()
                self.map_renderer.update_production_glow_effects(delta_time)

                # Update floating chat notifications (polls for new messages)
                if self.chat_notification_effect:
                    self.chat_notification_effect.update(delta_time)

                # Announce the local player's hero deaths (battles, Regicide)
                self._show_hero_death_notifications()

                # Check and trigger turn announcement effect if needed
                if self.game_state.turn_announcement_active and self.turn_announcement_effect is None:
                    # Trigger new turn announcement
                    player_num = self.game_state.current_player + 1
                    player_name = self.game_state.get_player_name(self.game_state.current_player)
                    self.turn_announcement_effect = TurnAnnouncementEffect(
                        WINDOW_WIDTH,
                        WINDOW_HEIGHT,
                        player_number=player_num,
                        player_name=player_name,
                        on_complete=self.game_state._complete_turn_announcement
                    )

                # Update turn announcement effect
                if self.turn_announcement_effect:
                    self.turn_announcement_effect.update(delta_time)

                    if self.turn_announcement_effect.is_finished():
                        self.turn_announcement_effect.cleanup()
                        self.turn_announcement_effect = None

                # Update enhanced battle interface (cinematic battle UI)
                if self.enhanced_battle_ui is not None:
                    self.enhanced_battle_ui.update(delta_time)

                # Update forced defend popup timer (auto-close after 10 seconds)
                self.update_forced_defend_popup(delta_time)

                # Battle Reports: promote newly captured reports and clear them once the
                # viewer's planning phase ends (single owner of both transitions).
                self._update_battle_reports(delta_time)

            # Victory/defeat cinematic sequence detection and update
            # Runs outside is_game_paused check so the cinematic plays even when paused
            # Skip for campaign missions (they have their own victory system)
            _is_campaign = self.tutorial_mission and getattr(self.tutorial_mission, 'active', False)
            if not _is_campaign:
                if self.game_state.phase == 'ended' and not self.victory_sequence_active:
                    if not self.victory_sequence_pending:
                        # Victory just detected - start waiting for animations to finish
                        self.victory_sequence_pending = True
                    elif self._all_animations_complete():
                        # All animations done - start the cinematic
                        self._start_victory_sequence()

                if self.victory_sequence_active:
                    if self._update_victory_sequence(delta_time):
                        # Cinematic finished - exit game loop to show recap
                        self.return_to_main_menu = True
                        running = False

            # Start-game camera zoom animation (runs even when paused - visual only)
            if self.start_camera_animation and self.start_camera_animation.active:
                self.start_camera_animation.update(delta_time)
                # Sync camera state after animation updates
                self.camera_offset = self.camera.offset.copy()
                self.camera_zoom = self.camera.zoom

            # Camera pan requested from the sidebar (runs even when paused - visual only)
            self._update_sidebar_pan(delta_time)

            # FPS OPT: Set is_zoom_animating flag for rendering pipeline to use fast paths.
            # Covers start animation, campaign mission zoom, and mouse-wheel zoom settling.
            _start_anim_active = (self.start_camera_animation is not None
                                  and self.start_camera_animation.active)
            _mission_anim_active = (self.tutorial_mission is not None
                                    and hasattr(self.tutorial_mission, 'camera_animation')
                                    and self.tutorial_mission.camera_animation is not None
                                    and getattr(self.tutorial_mission.camera_animation, 'active', False))
            # Advance smooth mouse-wheel zoom, then tick the settle timer.
            # update_zoom() is a no-op unless a wheel zoom is in flight, so it never
            # fights the campaign/start camera animations, which drive zoom directly.
            if self.camera.update_zoom(delta_time):
                self.camera_zoom = self.camera.zoom
                self.camera_offset = list(self.camera.offset)
            self.camera.update_zoom_settle(delta_time)
            self.is_zoom_animating = (_start_anim_active or _mission_anim_active
                                      or self.camera.is_zoom_settling)
            # NOTE: the map no longer needs re-invalidating when zoom activity ends.
            # That existed to undo the nearest-neighbour downgrade used during zoom,
            # which forced one full-map smoothscale on the settle frame (a ~53ms
            # hitch). _blit_map_background() now smoothscales only the visible slice
            # (~2.5ms), so it uses full quality on every frame and never needs a
            # catch-up rescale.

            # Check if planning timer has expired (sequential mode only)
            # Skip during mission intro when game is paused
            _timer_check_allowed = True
            if self.tutorial_mission:
                if hasattr(self.tutorial_mission, 'game_paused') and self.tutorial_mission.game_paused:
                    _timer_check_allowed = False
            if self.game_state.game_mode == 'sequential' and _timer_check_allowed and not self.is_game_paused:
                self.game_state.check_planning_timer_expired()

            # Simultaneous mode: check for deferred execution from AI background thread
            # Must run before timer checks to process pending execution promptly
            if self.sim_state is not None:
                self.sim_state.check_deferred_execution()

            # Simultaneous mode: update timers and check for auto-ready
            if self.sim_state is not None and self.sim_state.sim_phase == 'planning' and not self.is_game_paused:
                local_player = self.get_local_player()
                was_ready = self.sim_state.players_ready.get(local_player, False)

                # PRE-EXPIRE: Convert movement orders BEFORE update_timers() calls mark_ready().
                # mark_ready() sets players_ready=True, after which add_order() silently rejects.
                # This mirrors the End Turn button flow (convert first, mark ready second).
                if not was_ready:
                    timer_remaining = self.sim_state.player_timers.get(local_player, 999)
                    if timer_remaining - delta_time <= 0:
                        # Timer will expire this frame — convert movement orders now
                        logger.info(f"[SIM] Timer about to expire for player {local_player} - pre-converting {len(self.game_state.movement_orders)} movement orders")
                        for order in self.game_state.movement_orders:
                            sim_order = {
                                'type': 'movement',
                                'player_id': local_player,
                                'from_territory': order.from_territory,
                                'to_territory': order.to_territory,
                                'army_count': order.army_count,
                                'unit_ids': order.unit_ids if hasattr(order, 'unit_ids') else []
                            }
                            self.sim_state.add_order(local_player, sim_order)
                        # Reset unit statuses before clearing orders (same as End Turn button)
                        for order in self.game_state.movement_orders:
                            if hasattr(order, 'unit_ids') and order.unit_ids:
                                garrison = self.game_state.territory_garrisons.get(order.from_territory, {}).get(local_player)
                                if garrison and 'units' in garrison:
                                    for unit in garrison['units']:
                                        if unit.get('id') in order.unit_ids:
                                            unit['status'] = 'ready'
                                            unit['order'] = None
                        self.game_state.movement_orders.clear()

                # Now update timers — mark_ready() will be called, but orders are already saved
                self.sim_state.update_timers(delta_time)

                # Check if local player just became ready due to timer expiration
                is_ready_now = self.sim_state.players_ready.get(local_player, False)
                if not was_ready and is_ready_now:
                    # MULTIPLAYER: Send SIM_PLAYER_READY with orders to host (mirrors End Turn button)
                    # Without this, the host never receives the client's orders on timer expiry
                    if self.multiplayer_mode:
                        orders_to_send = list(self.sim_state.player_orders.get(local_player, []))
                        self._send_action_to_remote(MessageType.SIM_PLAYER_READY, {
                            'player_id': local_player,
                            'orders': orders_to_send
                        })
                        logger.info(f"[SIM] Timer expired - sent ready signal with {len(orders_to_send)} orders")

                # MULTIPLAYER: Host sends periodic timer sync to client (every 2 seconds)
                if self.multiplayer_mode and self.local_player_index == 0:
                    if self._sim_last_timer_sync is None:
                        self._sim_last_timer_sync = 0
                    self._sim_last_timer_sync += delta_time
                    if self._sim_last_timer_sync >= 2.0:
                        self._sim_send_timer_update()
                        self._sim_last_timer_sync = 0

            # BATTLE SOUND: Play once when battles are created for the local (human) player
            if not self.is_game_paused and self.game_state.pending_battles and not self._battle_sound_played:
                local_player = self.get_local_player()
                should_play = False

                if self.sim_state is not None:
                    # Simultaneous mode: play if any pending battle has local player as resolver
                    if self.sim_state.sim_phase == 'resolving':
                        for battle in self.game_state.pending_battles:
                            if getattr(battle, 'resolver', None) == local_player:
                                should_play = True
                                break
                else:
                    # Sequential mode: play if current player is the local human player
                    if self.game_state.turn_phase == 'battles':
                        if self.game_state.current_player == local_player:
                            should_play = True

                if should_play:
                    from global_sound import play_battle_sound, play_spell_sound
                    play_battle_sound()
                    # Layer Reinforce sound alongside battle sound for richer audio
                    play_spell_sound('Reinforce')
                    self._battle_sound_played = True

            # Reset battle sound flag when not in battle phase
            if self.game_state.turn_phase != 'battles':
                if self.sim_state is None or self.sim_state.sim_phase != 'resolving':
                    self._battle_sound_played = False

            # SIMULTANEOUS MODE: Auto-resolve battles where AI is the resolver (with delay)
            if (not self.is_game_paused and
                self.sim_state is not None and
                self.sim_state.sim_phase == 'resolving' and
                self.game_state.pending_battles and
                self.enhanced_battle_ui is None):  # Don't auto-resolve if battle UI is open
                # Check if the next battle's resolver is an AI
                next_battle = self.game_state.pending_battles[0]
                resolver = getattr(next_battle, 'resolver', None)
                if resolver is not None and resolver >= 0 and self.game_state.player_is_ai[resolver]:
                    # Track when this AI battle was first detected (for 2-second delay)
                    if self._ai_battle_delay_timer is None:
                        self._ai_battle_delay_timer = 0.0
                        self._ai_battle_territory = next_battle.territory
                        logger.info(f"[SIM] AI battle detected at {next_battle.territory} - showing grey marker for 2 seconds")

                    # Check if we're still on the same battle
                    if self._ai_battle_territory != next_battle.territory:
                        # New battle, reset timer
                        self._ai_battle_delay_timer = 0.0
                        self._ai_battle_territory = next_battle.territory
                        logger.info(f"[SIM] New AI battle detected at {next_battle.territory} - resetting timer")

                    # Increment timer
                    self._ai_battle_delay_timer += delta_time

                    # Only auto-resolve after 2 seconds
                    if self._ai_battle_delay_timer >= 2.0:
                        logger.info(f"[SIM] Auto-resolving battle at {next_battle.territory} - AI player {resolver} is resolver")
                        # Reset timer for next battle
                        self._ai_battle_delay_timer = 0.0
                        self._ai_battle_territory = None

                        # Store battle info before resolution
                        battle = next_battle
                        territory = battle.territory

                        # Auto-resolve the battle
                        self.game_state.resolve_battle(0)  # Resolve first pending battle
                        # Clear sequential mode flag - sim mode uses complete_round() instead
                        self.game_state.ready_to_advance_turn = False

                        # Get new owner after resolution
                        new_owner = self.game_state.territory_owners.get(territory, -1)

                        # Check for alliance marker (allied victory)
                        alliance_marker = None
                        if battle.resolved and hasattr(battle, 'team_members_map'):
                            winner = battle.winner
                            if winner is not None and winner in battle.team_members_map:
                                winning_team_members = battle.team_members_map[winner]
                                original_owner = getattr(battle, 'original_owner', -1)
                                original_owner_team = self.game_state.player_teams[original_owner] if original_owner >= 0 else -1
                                winner_team = -1 if winner == -1 else self.game_state.player_teams[winner]
                                is_defensive = (original_owner >= 0 and original_owner_team == winner_team)
                                if winner != -1 and len(winning_team_members) > 1 and not is_defensive:
                                    alliance_marker = {
                                        'type': 'alliance',
                                        'territory': territory,
                                        'players': winning_team_members,
                                        'chooser': self.sim_state.phase_manager.alliance_handler.determine_chooser(
                                            territory, winning_team_members
                                        )
                                    }
                                    self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)
                                    logger.info(f"[SIM] AI battle created alliance marker, chooser: {alliance_marker['chooser']}")

                        # MULTIPLAYER: Send battle result to clients
                        if self.multiplayer_mode and self.local_player_index == 0:
                    
                            battle_data = {
                                'territory': territory,
                                'winner': battle.winner if battle.resolved else -1,
                                'surviving_armies': getattr(battle, 'surviving_armies', 0),
                                'new_owner': new_owner
                            }
                            # Include surviving units composition for sync
                            if new_owner is not None and territory:
                                garrison = self.game_state.territory_garrisons.get(territory, {})
                                winner_garrison = garrison.get(new_owner, {})
                                units = winner_garrison.get('units', [])
                                if units:
                                    battle_data['surviving_units'] = [
                                        {'id': u.get('id', i), 'type': u.get('type', 'Swordsman'), 'status': 'moved'}
                                        for i, u in enumerate(units)
                                    ]
                            if alliance_marker:
                                battle_data['alliance_marker'] = alliance_marker
                            # Battle Reports ride along: a client APPLIES this result rather
                            # than running resolve_battle(), so without this the defending
                            # client would never learn what happened in its own territory.
                            if self.game_state.last_battle_reports:
                                battle_data['battle_reports'] = list(self.game_state.last_battle_reports)
                            self._send_action_to_remote(MessageType.BATTLE_RESOLVE, battle_data)
                            logger.info(f"[HOST] Broadcast AI battle result: {territory} -> player {new_owner}")

                        # Capital Assault: sync battle-based eliminations to sim_state
                        # game_state.eliminate_player() runs inside resolve_battle(), but
                        # sim_state.eliminate_player() is not called from that path
                        if self.game_state.victory_condition == "Capital Assault":
                            for pid in range(self.game_state.num_players):
                                if (pid not in self.sim_state.eliminated_players and
                                    all(owner != pid for owner in self.game_state.territory_owners.values())):
                                    self.sim_state.eliminate_player(pid)
                                    logger.info(f"[SIM] Synced elimination of Player {pid + 1} to sim_state after AI battle")

                        # Check if all battles resolved
                        if not self.game_state.pending_battles:
                            logger.info(f"[SIM] All battles resolved. Alliance markers: {len(self.sim_state.phase_manager.pending_alliance_markers)}")
                            if not self.sim_state.phase_manager.pending_alliance_markers:
                                self.sim_state.complete_round()
                else:
                    # Not an AI battle, reset the timer tracking
                    if self._ai_battle_delay_timer is not None:
                        self._ai_battle_delay_timer = 0.0
                        self._ai_battle_territory = None

            # SIMULTANEOUS MODE: Auto-resolve alliance markers where AI is the chooser (with delay)
            if (not self.is_game_paused and
                self.sim_state is not None and
                self.sim_state.sim_phase == 'resolving' and
                not self.game_state.pending_battles and  # Only after all battles resolved
                self.sim_state.phase_manager.pending_alliance_markers and
                not getattr(self, 'alliance_choice_popup_visible', False)):  # Don't auto-resolve if popup is open
                # Check if the next alliance marker's chooser is an AI
                next_marker = self.sim_state.phase_manager.pending_alliance_markers[0]
                chooser = next_marker.get('chooser')
                if chooser is not None and self.game_state.player_is_ai[chooser]:
                    # Track when this AI alliance marker was first detected (for 2-second delay)
                    if self._ai_alliance_delay_timer is None:
                        self._ai_alliance_delay_timer = 0.0
                        self._ai_alliance_territory = next_marker['territory']
                        logger.info(f"[SIM] AI alliance marker detected at {next_marker['territory']} - showing grey marker for 2 seconds")

                    # Check if we're still on the same marker
                    if self._ai_alliance_territory != next_marker['territory']:
                        # New marker, reset timer
                        self._ai_alliance_delay_timer = 0.0
                        self._ai_alliance_territory = next_marker['territory']
                        logger.info(f"[SIM] New AI alliance marker detected at {next_marker['territory']} - resetting timer")

                    # Increment timer
                    self._ai_alliance_delay_timer += delta_time

                    # Only auto-resolve after 2 seconds
                    if self._ai_alliance_delay_timer >= 2.0:
                        territory = next_marker['territory']
                        allied_players = next_marker['players']
                        logger.info(f"[SIM] Auto-resolving alliance marker at {territory} - AI player {chooser} is chooser")

                        # AI logic: Choose player with least territories; if tied, random
                        territory_counts = {}
                        for player_id in allied_players:
                            count = sum(1 for t, owner in self.game_state.territory_owners.items() if owner == player_id)
                            territory_counts[player_id] = count

                        min_territories = min(territory_counts.values())
                        candidates = [p for p, c in territory_counts.items() if c == min_territories]

                        chosen_owner = random.choice(candidates)
                        logger.info(f"[SIM] AI chose player {chosen_owner} (had {territory_counts[chosen_owner]} territories, candidates: {candidates})")

                        # Assign territory
                        self.sim_state.phase_manager.alliance_handler.assign_territory(territory, chosen_owner)

                        # MULTIPLAYER: Broadcast alliance choice to clients
                        if self.multiplayer_mode and self.local_player_index == 0:
                    
                            self._send_action_to_remote(MessageType.SIM_ALLIANCE_CHOICE, {
                                'territory': territory,
                                'new_owner': chosen_owner
                            })
                            logger.info(f"[HOST] Broadcast AI SIM_ALLIANCE_CHOICE: {territory} -> player {chosen_owner}")

                        # Reset timer for next marker
                        self._ai_alliance_delay_timer = 0.0
                        self._ai_alliance_territory = None

                        # Remove this marker from pending
                        self.sim_state.phase_manager.pending_alliance_markers.pop(0)

                        # Check if all alliance markers resolved
                        if not self.sim_state.phase_manager.pending_alliance_markers:
                            logger.info(f"[SIM] All alliance markers resolved. Completing round.")
                            self.sim_state.complete_round()
                else:
                    # Not an AI alliance marker, reset the timer tracking
                    if self._ai_alliance_delay_timer is not None:
                        self._ai_alliance_delay_timer = 0.0
                        self._ai_alliance_territory = None

            # SIMULTANEOUS MODE: Check if a new round started and trigger AI planning
            # Skip if game has ended - no new rounds after victory/defeat
            if (not self.is_game_paused and self.sim_state is not None
                    and self.last_sim_round is not None and self.game_state.phase != 'ended'):
                current_round = self.sim_state.round_number
                if current_round != self.last_sim_round:
                    logger.info(f"[SIMULTANEOUS] New round detected: {self.last_sim_round} -> {current_round}")
                    self.last_sim_round = current_round

                    # Trigger turn announcement for the new round (Turn X)
                    if self.turn_announcement_effect is None:
                        self.turn_announcement_effect = TurnAnnouncementEffect(
                            WINDOW_WIDTH,
                            WINDOW_HEIGHT,
                            custom_text=f"Turn {current_round}",
                            on_complete=None  # No callback needed for sim mode
                        )
                        logger.info(f"[SIMULTANEOUS] Triggered Turn {current_round} announcement")

                    # Trigger AI planning for the new round
                    if self.sim_ai is not None and self.sim_state.sim_phase == 'planning':
                        logger.info(f"[SIMULTANEOUS] Triggering AI planning for round {current_round}")
                        self.sim_ai.start_planning_phase()

            # Handle AI player turn (optimized: check on player change OR phase change OR turn announcement ending)
            player_changed = self.game_state.current_player != self.previous_ai_check
            phase_changed = self.game_state.phase != self.previous_phase
            announcement_ended = self.previous_turn_announcement and not self.game_state.turn_announcement_active

            if player_changed or phase_changed or announcement_ended:
                self.previous_ai_check = self.game_state.current_player
                self.previous_phase = self.game_state.phase
                self.previous_turn_announcement = self.game_state.turn_announcement_active

                # Don't process AI turns while game is paused
                if not self.is_game_paused:
                    # Handle setup phase (AI claiming starting territories)
                    if (self.game_state.is_ai_player() and
                        self.game_state.phase == 'setup'):
                        self.handle_ai_setup()
                    # Handle playing phase (normal AI turn) - SEQUENTIAL MODE ONLY
                    # In simultaneous mode, AI is handled separately by sim_ai
                    elif (self.game_state.is_ai_player() and
                        self.game_state.phase == 'playing' and
                        self.game_state.turn_phase == 'planning' and
                        not self.game_state.turn_announcement_active and
                        self.sim_state is None):
                        self.handle_ai_turn()

            # Detect turn changes and clear UI selections
            if self.game_state.current_player != self.previous_player:
                self.clear_ui_selections()
                self.previous_player = self.game_state.current_player
                # Auto-close Players window at each turn advance — per-turn state
                # (transfer caps, already-sent locks) changes, so the window must refresh
                # from scratch next time it's opened.
                if self.players_window_visible and self.players_window is not None:
                    self.players_window.close()

            # Simultaneous mode: close Players window when leaving planning phase
            if self.sim_state is not None and self.players_window_visible:
                if self.sim_state.sim_phase != 'planning':
                    if self.players_window is not None:
                        self.players_window.close()

            # Update mouse position every frame for hover detection
            self.mouse_pos = pygame.mouse.get_pos()
            
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                # Window focus tracking — throttle FPS when unfocused (Steam: don't burn CPU in background)
                elif event.type == pygame.ACTIVEEVENT:
                    if hasattr(event, 'gain') and hasattr(event, 'state'):
                        # state & 2 = keyboard/window focus, state & 6 = input focus
                        if event.state & 6:
                            self._window_focused = bool(event.gain)

                # Music track ended — advance to next track (always process, even during blocking)
                elif event.type == MUSIC_END_EVENT:
                    music_manager.handle_music_end_event()

                # Block all input during turn announcement
                elif self.game_state.turn_announcement_active:
                    continue  # Ignore all events during turn announcement

                # Block all input during victory/defeat cinematic
                elif self.victory_sequence_active:
                    continue  # No interaction during cinematic animation

                # Players window (non-pausing modal) — consume relevant events while open.
                # Takes priority over tutorial/AI-turn blocking so it can always be closed.
                elif self.players_window_visible and self.players_window is not None:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.players_window.handle_click(event.pos)
                        continue
                    if event.type == pygame.KEYDOWN:
                        if self.players_window.handle_key(event):
                            continue
                        # Swallow other keydowns so they don't leak to the game.
                        continue
                    if event.type == pygame.MOUSEMOTION:
                        # Let mouse motion through for hover state in the window,
                        # but don't let it drag the camera or move map selection.
                        continue
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        # Right-click / middle-click consumed — no camera drag while modal open.
                        continue
                    if event.type == pygame.MOUSEWHEEL:
                        continue
                    # Non-UI events (QUIT already handled above) fall through to default.

                # Tutorial mission: selectively block input based on current step
                elif (self.tutorial_mission
                      and self.tutorial_mission.active
                      and not self.tutorial_mission.is_action_allowed('camera')):
                    # When camera is locked, block almost everything except ESC for menu/skip
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        # ESC skips visible transmission before toggling menu
                        if (hasattr(self.tutorial_mission, 'skip_transmission')
                                and self.tutorial_mission.skip_transmission()):
                            pass  # Transmission skipped, consume ESC
                        elif self.game_menu_visible:
                            self.game_menu_visible = False
                            self._unpause_game()
                        else:
                            self.game_menu_visible = True
                            self._pause_game()
                    elif event.type == pygame.MOUSEBUTTONDOWN and (self.game_menu_visible or self.options_menu_visible):
                        # Allow menu clicks when menu is open
                        if event.button == 1:
                            handled_result = self.mouse.handle_left_click(event.pos)
                            if isinstance(handled_result, tuple):
                                handled, should_quit = handled_result
                                if should_quit:
                                    running = False
                    elif event.type == pygame.MOUSEWHEEL and not (self.game_menu_visible or self.options_menu_visible):
                        # The camera is locked, but reading the sidebar is not: scroll it
                        self.handle_sidebar_wheel(event.y)
                    continue  # Block all other input

                # Block action input during AI player turns (but allow hovering and menu)
                # Don't block during 'setup' or 'ended' phases
                # SIMULTANEOUS MODE: Don't block - human can always act during planning phase
                elif self.game_state.is_ai_player() and self.game_state.phase not in ('setup', 'ended') and self.sim_state is None:
                    # Allow these events during AI turns:
                    # - MOUSEMOTION (for hovering/tooltips)
                    # - KEYDOWN ESC (for menu access)
                    # - MOUSEWHEEL (for zoom)
                    # - MOUSEBUTTONDOWN in sidebar area (for Action Log, etc.)
                    # - MOUSEBUTTONDOWN when any menu is open (for menu interaction)
                    if event.type == pygame.MOUSEMOTION:
                        # Process hover detection during AI turns
                        self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())
                        self.mouse.handle_mouse_motion(event.pos)
                        continue  # Skip other MOUSEMOTION processing
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        # ESC skips visible transmission before toggling menu
                        if (self.tutorial_mission
                                and hasattr(self.tutorial_mission, 'skip_transmission')
                                and self.tutorial_mission.skip_transmission()):
                            pass  # Transmission skipped, consume ESC
                        # Allow ESC to toggle menu during AI turns
                        elif self.options_menu_visible:
                            # Close options menu and return to game menu
                            self.options_menu_visible = False
                            self.game_menu_visible = True
                            self.resolution_dropdown_open = False
                            # Reset temp settings
                            self.temp_resolution = self.current_resolution
                            self.temp_fullscreen = self.is_fullscreen
                            self.temp_vsync = self.vsync
                            self.temp_fps_limit = self.fps_limit
                        elif self.game_menu_visible:
                            # Close game menu
                            self.game_menu_visible = False
                            self._unpause_game()
                        else:
                            # Open game menu
                            self.game_menu_visible = True
                            self._pause_game()
                        continue  # Processed ESC, skip other handling
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_F2:
                        # Collapsing the sidebar is local UI, allowed while the AI plays
                        self._handle_sidebar_hotkey()
                        continue
                    elif event.type == pygame.MOUSEWHEEL:
                        # Handle options menu scrolling or camera zoom during AI turns
                        if self.options_menu_visible:
                            # Scroll the options menu content
                            scroll_amount = 30  # Pixels per scroll
                            self.options_menu_scroll_offset -= event.y * scroll_amount
                            # Clamp immediately to prevent flicker (max_scroll calculated in draw)
                            self.options_menu_scroll_offset = max(0, min(self.options_menu_scroll_offset, self.options_menu_max_scroll))
                        elif not self.game_menu_visible:
                            # Handle zoom when no menu is open
                            self.handle_camera_zoom(event.y)
                        continue  # Processed, skip other processing
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        # During AI turns, allow clicks only on: an open menu, the
                        # top panel, and the sidebar's bookmark tabs / collapse button
                        # (see _is_ai_turn_click_allowed — it follows the live sidebar
                        # layout, so the tabs stay clickable when collapsed).
                        if self._is_ai_turn_click_allowed(event.pos):
                            # Click is in allowed area - process it
                            if event.button == 1:  # Left click
                                handled_result = self.mouse.handle_left_click(event.pos)
                                if isinstance(handled_result, tuple):
                                    handled, should_quit = handled_result
                                    if should_quit:
                                        running = False
                            continue  # Processed, skip further event handling
                        else:
                            # Click is in map/bottom area - block it
                            continue
                    else:
                        continue  # Block all other events (other keys, etc.)

                elif event.type == pygame.USEREVENT + 1:
                    # Battle animation timer - transition from resolving to result
                    if self.battle_popup_visible and self.battle_popup_state == 'resolving':
                        self.battle_popup_state = 'result'
                        pygame.time.set_timer(pygame.USEREVENT + 1, 0)  # Cancel timer

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        # Handle disconnect dialog click (highest priority)
                        if self.show_disconnect_dialog and self.disconnect_exit_button:
                            if self.disconnect_exit_button.collidepoint(event.pos):
                                # Exit to main menu
                                self.return_to_main_menu = True
                                running = False
                                continue

                        # Block map interactions when enhanced battle UI is active
                        if self.enhanced_battle_ui is not None:
                            # Only handle battle UI clicks, block everything else
                            self.handle_battle_popup_click(event.pos)
                            continue

                        # Handle forced defend popup clicks (sim mode - overwhelming force notification)
                        if self.forced_defend_popup_visible:
                            if self.handle_forced_defend_click(event.pos):
                                continue

                        # Delegate to mouse handler (handles all priorities)
                        handled_result = self.mouse.handle_left_click(event.pos)

                        # Check if we need to quit (from victory screen or game menu)
                        if isinstance(handled_result, tuple):
                            handled, should_quit = handled_result
                            if should_quit:
                                running = False

                    elif event.button == 3:  # Right click
                        # Block right-clicks when enhanced battle UI is active
                        if self.enhanced_battle_ui is not None:
                            continue
                        # Cancel ability targeting on right-click (same as ESC)
                        if self.ability_targeting_active:
                            self.ability_targeting_active = False
                            self.ability_targeting_hero = None
                            self.ability_targeting_ability_index = None
                            self.ability_targeting_ability_name = None
                            continue
                        # Unit context menu (bottom-UI army strip): right-click a unit
                        # icon to open it, right-click again to dismiss. Handled here
                        # rather than in handle_right_click() so it works in any turn
                        # phase, matching the left-click selection it complements.
                        if self.handle_unit_context_menu_right_click(event.pos):
                            continue
                        # Right-click for movement orders (only in planning phase)
                        if self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
                            self.mouse.handle_right_click(event.pos)
                
                elif event.type == pygame.MOUSEMOTION:
                    # Camera controls (Phase 2D: drag only, edge scrolling moved to main loop)
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())

                    # Enhanced battle interface hover tracking (blocks map hover when active)
                    if self.enhanced_battle_ui is not None:
                        self.enhanced_battle_ui.handle_mouse_motion(event.pos)
                        # Don't process map hover when battle UI is active
                        continue

                    # Mouse motion hover tracking (delegated to mouse handler)
                    self.mouse.handle_mouse_motion(event.pos)

                    # Slider dragging (options menu sliders)
                    if self.dragging_slider and self.options_menu_visible:
                        mouse_x = event.pos[0]
                        
                        if self.dragging_slider == 'pan_speed' and self.gameplay_pan_speed_slider:
                            slider_track, min_speed, max_speed, thumb_rect = self.gameplay_pan_speed_slider
                            # Calculate position accounting for drag offset
                            adjusted_x = mouse_x - self.drag_offset
                            rel_x = adjusted_x - slider_track.x
                            slider_pos = max(0, min(1, rel_x / slider_track.width))
                            self.temp_camera_pan_speed = min_speed + slider_pos * (max_speed - min_speed)
                        
                        elif self.dragging_slider == 'zoom_speed' and self.gameplay_zoom_speed_slider:
                            slider_track, min_zoom_speed, max_zoom_speed, thumb_rect = self.gameplay_zoom_speed_slider
                            # Calculate position accounting for drag offset
                            adjusted_x = mouse_x - self.drag_offset
                            rel_x = adjusted_x - slider_track.x
                            slider_pos = max(0, min(1, rel_x / slider_track.width))
                            self.temp_camera_zoom_speed = min_zoom_speed + slider_pos * (max_zoom_speed - min_zoom_speed)

                        # Audio volume slider dragging with live preview
                        elif self.dragging_slider == 'master_volume' and self.audio_master_slider:
                            slider_track = self.audio_master_slider[0]
                            adjusted_x = mouse_x - self.drag_offset
                            rel_x = adjusted_x - slider_track.x
                            self.temp_master_volume = max(0.0, min(1.0, rel_x / slider_track.width))
                            # Live preview: apply volume change immediately
                            music_manager.set_master_volume(self.temp_master_volume)
                            sound_manager.set_volume(self.temp_sfx_volume * self.temp_master_volume)

                        elif self.dragging_slider == 'music_volume' and self.audio_music_slider:
                            slider_track = self.audio_music_slider[0]
                            adjusted_x = mouse_x - self.drag_offset
                            rel_x = adjusted_x - slider_track.x
                            self.temp_music_volume = max(0.0, min(1.0, rel_x / slider_track.width))
                            music_manager.set_music_volume(self.temp_music_volume)

                        elif self.dragging_slider == 'sfx_volume' and self.audio_sfx_slider:
                            slider_track = self.audio_sfx_slider[0]
                            adjusted_x = mouse_x - self.drag_offset
                            rel_x = adjusted_x - slider_track.x
                            self.temp_sfx_volume = max(0.0, min(1.0, rel_x / slider_track.width))
                            sound_manager.set_volume(self.temp_sfx_volume * self.temp_master_volume)
                
                elif event.type == pygame.KEYDOWN:
                    # Space/ESC skips the battle bar volley animation while the
                    # enhanced battle interface is open (it is modal, so the key
                    # must not fall through to normal game shortcuts).
                    if (self.enhanced_battle_ui is not None
                            and self.enhanced_battle_ui.handle_key(event)):
                        pass  # Animation skipped, consume the key
                    # ESC skips visible campaign transmission before normal handling
                    elif (event.key == pygame.K_ESCAPE
                            and self.tutorial_mission
                            and hasattr(self.tutorial_mission, 'skip_transmission')
                            and self.tutorial_mission.skip_transmission()):
                        pass  # Transmission skipped, consume ESC
                    else:
                        # Keyboard input (Phase 2A: extracted to method)
                        self.handle_keyboard_input(event)
                
                elif event.type == pygame.MOUSEWHEEL:
                    # Options menu scrolling (when options menu is open)
                    if self.options_menu_visible:
                        # Scroll the options menu content
                        scroll_amount = 30  # Pixels per scroll
                        self.options_menu_scroll_offset -= event.y * scroll_amount
                        # Clamp immediately to prevent flicker (max_scroll calculated in draw)
                        self.options_menu_scroll_offset = max(0, min(self.options_menu_scroll_offset, self.options_menu_max_scroll))
                    # Camera zoom (Phase 2D: mouse wheel)
                    # Block mouse wheel when menus are open or tutorial camera locked
                    elif not self.game_menu_visible:
                        if not (self.tutorial_mission
                                and self.tutorial_mission.active
                                and not self.tutorial_mission.is_action_allowed('camera')):
                            self.handle_camera_zoom(event.y)
                
                elif event.type == pygame.MOUSEBUTTONUP:
                    # Stop slider dragging when mouse button released
                    if event.button == 1:  # Left mouse button
                        self.dragging_slider = None
                        self.drag_offset = 0

            # DEFENSIVE CHECK: Detect unintended fullscreen mode changes
            # This catches cases where pygame or Windows might drop fullscreen unexpectedly
            current_flags = self.screen.get_flags()
            current_is_fullscreen = bool(current_flags & pygame.FULLSCREEN)
            if current_is_fullscreen != self.is_fullscreen:
                logger.warning(f"WARNING: Display mode mismatch detected!")
                logger.info(f"   Expected: {'FULLSCREEN' if self.is_fullscreen else 'WINDOWED'}")
                logger.info(f"   Actual:   {'FULLSCREEN' if current_is_fullscreen else 'WINDOWED'}")
                logger.info(f"   Attempting to restore expected mode...")

                # Attempt to restore the expected mode.
                # Routed through set_display_mode so VSync is re-applied: a bare
                # set_mode() here would silently and permanently drop SCALED/vsync
                # mid-game, with nothing in the UI reflecting that it had gone.
                try:
                    current_size = self.screen.get_size()
                    self.screen, self.vsync_active = set_display_mode(
                        current_size, self.is_fullscreen, self.vsync)
                    _set_app_icon()
                    logger.info(f"[OK] Restored {'fullscreen' if self.is_fullscreen else 'windowed'} mode")
                except Exception as e:
                    logger.error(f"[ERROR] Failed to restore display mode: {e}")
                    logger.info(f"   Updating internal state to match actual mode")
                    self.is_fullscreen = current_is_fullscreen

            # Keyboard camera control (Phase 2D: continuous per-frame)
            # Must be outside event loop to allow smooth continuous scrolling
            # Tutorial gate: block camera movement when camera not allowed
            _tutorial_camera_ok = not self._is_tutorial_blocking('camera')

            keys = pygame.key.get_pressed()
            if _tutorial_camera_ok:
                self.handle_keyboard_camera(keys)

            # Edge scrolling (Phase 2D: continuous per-frame)
            # Check mouse position every frame for smooth edge scrolling
            mouse_pos = pygame.mouse.get_pos()
            if _tutorial_camera_ok:
                # delta_time drives the Map Edge dwell delay (not the pan speed,
                # which stays per-frame as before)
                self.handle_edge_scrolling(mouse_pos, delta_time)
            
            # Tutorial mission: update logic before rendering so camera animation applies this frame
            if self._is_tutorial_active() and not self.is_game_paused:
                tutorial_result = self.tutorial_mission.update(delta_time)
                # Handle victory/defeat sequence exit to campaign screen. Both exit to
                # the campaign screen, but only victory ('campaign') plays the outro
                # cutscene — defeat returns 'campaign_defeat' so the caller can skip it.
                if tutorial_result == 'exit_campaign':
                    return 'campaign'
                if tutorial_result == 'exit_campaign_defeat':
                    return 'campaign_defeat'
                self.tutorial_mission.update_ai_turn(delta_time)
                # Sync camera state after tutorial animation updates
                self.camera_offset = self.camera.offset
                self.camera_zoom = self.camera.zoom

            # Drawing
            self.screen.fill(WHITE)

            # Draw map (Phase 2D: transform with camera!)
            # Viewport-only rescale — see _blit_map_background() for why this is not
            # a full-map scale (it was 16-53ms per zoom change; now ~0.3-2.5ms).
            self._blit_map_background()

            # Draw territories (Phase 4D: inlined from delegate methods)
            self.map_renderer.draw_territories()

            # Draw silence fog overlay if any player is silenced
            self.draw_silence_fog_overlay()

            # Draw hero ability bubbles (unified system)
            for effect_key in self._bubble_configs:
                self._draw_hero_bubbles(effect_key)

            # Draw movement arrows (orders) (Phase 4D: inlined)
            self.map_renderer.draw_movement_arrows()

            # Draw battle markers (Phase 4D: inlined)
            self.map_renderer.draw_battle_markers()

            # SIMULTANEOUS MODE: Draw alliance markers and overflow indicators (Phase 4D: inlined)
            self.map_renderer.draw_alliance_markers()
            self.map_renderer.draw_overflow_indicators()

            # Draw castle upgrade particle effects (after battle markers, before UI)
            self.map_renderer.render_castle_upgrade_effects()

            # Draw hero ability visual effects (burst + arc particles, same layer as castle upgrades)
            self.map_renderer.render_ability_effects()

            # Draw embargo persistent bubble effects (on enemy territories while embargo active)
            self.map_renderer.render_embargo_effects()

            # Draw top panel (Phase 4D: inlined from delegate method)
            self.ui_renderer.draw_top_panel()

            # Always draw order sidebar and bottom UI panels
            # During AI turns, draw empty panels (just backgrounds, no interactive content)
            # In simultaneous mode, all players interact simultaneously, so no AI turn concept
            is_ai_turn = self.game_state.is_ai_player() and self.game_state.phase == 'playing' and self.sim_state is None

            if is_ai_turn:
                # During AI turns, allow sidebar (for spectating Action Log, etc.)
                # but draw empty bottom panel (no interactive content)
                self.draw_order_sidebar()
                self.draw_empty_bottom_ui_panel()
            else:
                # Draw full interactive UI for human players
                self.draw_order_sidebar()
                self.draw_bottom_ui()
            
            # Draw chat input box (appears above bottom UI when active) (Phase 4D: inlined)
            self.ui_renderer.draw_chat_input()

            # Draw floating chat notifications (top-left of map, below top panel)
            if self.chat_notification_effect:
                self.chat_notification_effect.render(self.screen)

            # P7 fix: removed duplicate building button hover tracking here —
            # already handled in update_frame_tooltips() called at line 9373

            # Tutorial mission: render overlay (below menus so Menu renders on top)
            if self._is_tutorial_active():
                self.tutorial_mission.render(self.screen)

            # Battle Report popups: above the map, below the modal battle/menu layer
            self.draw_battle_reports()

            # Draw battle popup (on top of everything)
            self.draw_battle_popup()

            # Battle Report detail screen (full result panel, defender's point of view)
            self.draw_battle_report_detail()

            # Draw alliance choice popup (simultaneous mode - territory ownership decision)
            self.draw_alliance_choice_popup()

            # Draw forced defend popup (simultaneous mode - overwhelming force notification)
            self.draw_forced_defend_popup()

            # Draw the unit right-click context menu last so it covers the bottom UI
            # (same "draw dropdown options last" rule the options menu dropdown follows)
            if self.unit_context_menu:
                self.draw_unit_context_menu()

            # Draw victory/defeat cinematic (on top of everything else)
            if self.victory_sequence_active:
                self._render_victory_sequence()

            # Draw Players window (non-pausing modal) — drawn beneath the game menu
            # so Menu always takes priority if both are somehow open together.
            if self.players_window_visible and self.players_window is not None:
                self.players_window.draw(self.screen)

            # Draw game menu (on top of everything, if visible) (Phase 4D: inlined)
            if self.game_menu_visible:
                self.ui_renderer.draw_game_menu()

            # Draw save dialog (on top of game menu, if visible)
            if self.save_dialog_active:
                # Update cursor blink timer
                self.save_name_cursor_timer += self.clock.get_time()
                if self.save_name_cursor_timer >= 500:
                    self.save_name_cursor_visible = not self.save_name_cursor_visible
                    self.save_name_cursor_timer = 0
                self.ui_renderer.draw_save_dialog()

            # Update save feedback timer and render feedback in map area
            if self.save_feedback_timer > 0:
                self.save_feedback_timer -= self.clock.get_time()
                if self.save_feedback_timer <= 0:
                    self.save_feedback_message = None
                else:
                    self.ui_renderer.draw_save_feedback()

            # Draw options menu (on top of game menu, if visible) (Phase 4D: inlined)
            if self.options_menu_visible:
                self.ui_renderer.draw_options_menu()

            # Draw disconnect dialog (multiplayer only, on top of everything)
            if self.show_disconnect_dialog:
                self.draw_disconnect_dialog()

            # Update and render tooltips (Phase 2C: extracted to method)
            # MUST happen after all drawing, before display.flip()
            self.update_frame_tooltips()

            # Render spectator mode banner (multiplayer)
            self.render_spectator_banner()

            # Render turn announcement effect (on top of everything)
            if self.turn_announcement_effect:
                self.turn_announcement_effect.render(self.screen)

            # Render Master Negotiator particle effect (green particles around screen edges)
            self.render_master_negotiator_particles()

            # Render AI thinking indicator (SEQUENTIAL MODE ONLY)
            # In simultaneous mode, all players plan at once - no AI thinking indicator needed
            if (self.game_state.is_ai_player() and
                self.game_state.phase == 'playing' and
                self.game_state.turn_phase == 'planning' and
                self.sim_state is None):
                self.render_ai_thinking_indicator()

            # (Tutorial update moved to before rendering for camera animation sync)

            # Update click flash timer (decrement if active)
            if self.click_flash_timer > 0:
                dt = self.clock.get_time()  # Milliseconds since last frame
                self.click_flash_timer -= dt
                if self.click_flash_timer <= 0:
                    self.clicked_element = None  # Clear flash when timer expires

            # Draw cursor last — targeting circle during ability targeting,
            # attack cursor over enemy/neutral territories with army selected,
            # custom cursor otherwise
            if self.ability_targeting_active:
                self.draw_targeting_cursor()
            elif self._should_show_attack_cursor():
                draw_attack_cursor(self.screen)
            else:
                draw_custom_cursor(self.screen)

            # Update display
            pygame.display.flip()
            # Frame pacing: manual cap > vsync (safety-capped) > FPS constant,
            # and always throttled hard when unfocused (Steam: don't burn CPU in
            # the background). Never an uncapped tick() — see resolve_frame_cap.
            self.clock.tick(resolve_frame_cap(
                self.fps_limit, self.vsync_active, self._window_focused,
                FPS, UNFOCUSED_FPS))

        # Clean up resources (network, replay, logger) before exiting
        self._cleanup()

        # Return to main menu if flag is set, otherwise quit
        if self.return_to_main_menu:
            return 'main_menu'
        else:
            return 'quit'
    
    # ========================================================================
    # PHASE 2A: EVENT HANDLERS
    # 
    # Event handlers are extracted from the run() method to improve
    # readability and maintainability. Each handler focuses on one type
    # of user interaction.
    #
    # Event handling priority order:
    # 1. Game menu clicks (if menu visible - modal overlay)
    # 2. Top panel clicks (menu button)
    # 3. Victory screen clicks (if game ended)
    # 4. Battle popup clicks (if popup visible)
    # 5. Bottom UI clicks (if in UI area)
    # 6. Map area clicks (if in map area)
    # 7. Keyboard input (any time)
    # ========================================================================
    
    def handle_game_menu_click(self, pos):
        """
        Handle clicks on game menu buttons.
        
        The game menu is a modal overlay that appears when self.game_menu_visible is True.
        It contains three buttons:
        - Resume Game: Closes menu and returns to game
        - Options: Opens options menu (not yet implemented)
        - Quit to Main Menu: Exits the game (for now, until main menu is implemented)
        
        Args:
            pos: (x, y) tuple of click position in screen coordinates
            
        Returns:
            tuple: (handled, should_quit)
                handled: True if click was on a menu button
                should_quit: True if quit button was clicked
        
        Side Effects:
            - May set self.game_menu_visible = False (resume button)
            - May print message about options menu not being implemented
        """
        if not self.game_menu_visible:
            return (False, False)

        # If save dialog is active, handle its clicks instead of menu clicks
        if self.save_dialog_active:
            return self._handle_save_dialog_click(pos)

        # Resume Game button
        if self.menu_resume_button:
            if self.menu_resume_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('menu_button', 'resume')
                self.game_menu_visible = False
                self._unpause_game()
                return (True, False)

        # Save Game button (campaign only, set by ui_renderer when enabled)
        if self.menu_save_button:
            if self.menu_save_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('menu_button', 'save')
                # Open save dialog with default name
                self.save_dialog_active = True
                self.save_name_input = f"Turn {self.game_state.turn_number}"
                self.save_name_cursor_visible = True
                self.save_name_cursor_timer = 0
                self.game_menu_visible = False
                return (True, False)

        # Options button
        if self.menu_options_button:
            if self.menu_options_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('menu_button', 'options')
                # Open options menu
                self.options_menu_visible = True
                self.game_menu_visible = False  # Hide game menu
                self.options_menu_scroll_offset = 0  # Reset scroll to top
                # Reset temp settings to current settings
                self.temp_resolution = self.current_resolution
                self.temp_fullscreen = self.is_fullscreen
                self.temp_vsync = self.vsync
                self.temp_fps_limit = self.fps_limit
                # Reset temp gameplay settings
                self.temp_edge_scrolling_enabled = self.edge_scrolling_enabled
                self.temp_edge_scrolling_mode = self.edge_scrolling_mode
                self.temp_tooltips_enabled = self.tooltips_enabled
                self.temp_tooltip_delay_ms = self.tooltip_delay_ms
                self.temp_camera_pan_speed = self.camera_pan_speed
                self.temp_camera_zoom_speed = self.camera_zoom_speed
                self.temp_show_fps = self.show_fps
                self.resolution_dropdown_open = False  # Close dropdown if it was open
                return (True, False)
        
        # Quit to Main Menu button
        if self.menu_quit_button:
            if self.menu_quit_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('menu_button', 'quit')
                # Stop any playing transmission voice before leaving
                from global_sound import stop_transmission_sound
                stop_transmission_sound()
                # Return to main menu
                self.return_to_main_menu = True
                return (True, True)
        
        # Click was on menu overlay but not on any button - consume click anyway
        # This prevents clicks from passing through the menu to the game
        return (True, False)

    def _handle_save_dialog_click(self, pos):
        """Handle clicks on the save name dialog buttons."""
        if self.save_dialog_save_button and self.save_dialog_save_button.collidepoint(pos):
            self._execute_save_game()
            return (True, False)

        if self.save_dialog_cancel_button and self.save_dialog_cancel_button.collidepoint(pos):
            self.sound_manager.play_ui_click()
            self.trigger_click_flash('save_dialog', 'cancel')
            self.save_dialog_active = False
            self.game_menu_visible = True  # Return to game menu
            return (True, False)

        # Consume click on dialog overlay
        return (True, False)

    def _execute_save_game(self):
        """Perform the actual save game operation."""
        self.sound_manager.play_ui_click()
        self.trigger_click_flash('save_dialog', 'save')

        save_name = self.save_name_input.strip()
        if not save_name:
            save_name = f"Turn {self.game_state.turn_number}"

        from save_manager import save_game
        result = save_game(self.game_state, self.tutorial_mission, save_name)

        self.save_dialog_active = False
        if result:
            self.save_feedback_message = "Saved!"
            self.save_feedback_is_error = False
            self.save_feedback_timer = 2000  # Show for 2 seconds
            self.game_menu_visible = True  # Return to game menu showing feedback
        else:
            self.save_feedback_message = "Save failed!"
            self.save_feedback_is_error = True
            self.save_feedback_timer = 2000
            self.game_menu_visible = True

    def handle_save_dialog_keydown(self, event):
        """Handle keyboard input for the save name dialog."""
        if not self.save_dialog_active:
            return False

        if event.key == pygame.K_RETURN:
            self._execute_save_game()
            return True
        elif event.key == pygame.K_ESCAPE:
            self.save_dialog_active = False
            self.game_menu_visible = True
            return True
        elif event.key == pygame.K_BACKSPACE:
            self.save_name_input = self.save_name_input[:-1]
            return True
        elif event.unicode and len(self.save_name_input) < 50:
            # Filter out control characters, allow printable chars
            if event.unicode.isprintable():
                self.save_name_input += event.unicode
            return True

        return True  # Consume all keys while dialog is open

    @property
    def is_game_paused(self):
        """True when game should be paused (single-player menu/options open)."""
        return self.game_paused and not self.multiplayer_mode

    def execute_gold_transfer(self, sender_idx, recipient_idx, amount):
        """Player-initiated gold transfer entry point.

        Applies locally (optimistic — sender's client shows the deduction
        immediately) and, if multiplayer, broadcasts a GOLD_TRANSFER message
        so remote peers mirror the balance change.

        Returns the amount actually sent (0 if rejected / invalid).
        """
        sent = self.game_state.transfer_gold(sender_idx, recipient_idx, amount)
        if sent > 0 and self.multiplayer_mode and self.network_connection is not None:
            # Broadcast the actual (post-clamp) amount so peers converge on the same value.
            self._send_action_to_remote(MessageType.GOLD_TRANSFER, {
                'player_index': sender_idx,
                'recipient_index': recipient_idx,
                'amount': sent,
                'turn_number': self.game_state.turn_number,
            })
        return sent

    def _pause_game(self):
        """Pause the game (single-player only). Called when game menu opens."""
        if self.multiplayer_mode or self.game_paused:
            return
        self.game_paused = True
        self._pause_start_time = time.time()
        # Pause any playing transmission voice line so it resumes when unpaused
        from global_sound import pause_transmission_sound
        pause_transmission_sound()

    def _unpause_game(self):
        """Unpause the game. Called when game menu closes via Resume or ESC."""
        if not self.game_paused:
            return
        self.game_paused = False
        self._pause_start_time = None
        # Resume any paused transmission voice line
        from global_sound import unpause_transmission_sound
        unpause_transmission_sound()

    def handle_options_menu_click(self, pos):
        """
        Handle clicks on options menu controls.
        
        The options menu contains:
        - Resolution dropdown (with expandable options list)
        - Fullscreen checkbox
        - Apply button (applies settings)
        - Back button (returns to game menu without applying)
        
        Args:
            pos: (x, y) tuple of click position in screen coordinates
            
        Returns:
            tuple: (handled, should_quit)
                handled: True if click was on an options control
                should_quit: Always False (options menu can't quit game)
        
        Side Effects:
            - May toggle self.temp_fullscreen
            - May change self.temp_resolution
            - May open/close resolution dropdown
            - May apply settings via self.apply_display_settings()
            - May close options menu and reopen game menu
        """
        if not self.options_menu_visible:
            return (False, False)
        
        # Resolution dropdown button
        if self.resolution_dropdown_button:
            if self.resolution_dropdown_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('options_control', 'resolution_dropdown')
                # Toggle dropdown
                self.resolution_dropdown_open = not self.resolution_dropdown_open
                return (True, False)
        
        # Resolution dropdown options (if open)
        if self.resolution_dropdown_open and self.resolution_option_buttons:
            for option_rect, resolution in self.resolution_option_buttons:
                if option_rect.collidepoint(pos):
                    self.sound_manager.play_ui_click()
                    self.trigger_click_flash('resolution_option', f"{resolution[0]}x{resolution[1]}")
                    # Set temp resolution
                    self.temp_resolution = resolution
                    # Close dropdown
                    self.resolution_dropdown_open = False
                    return (True, False)
        
        # Fullscreen checkbox
        if self.fullscreen_checkbox:
            if self.fullscreen_checkbox.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('options_control', 'fullscreen_checkbox')
                # Toggle fullscreen
                self.temp_fullscreen = not self.temp_fullscreen
                # When enabling fullscreen, automatically use native resolution
                if self.temp_fullscreen:
                    self.temp_resolution = self.native_resolution
                return (True, False)

        # VSync checkbox
        if getattr(self, 'display_vsync_checkbox', None):
            if self.display_vsync_checkbox.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('options_control', 'vsync_checkbox')
                self.temp_vsync = not self.temp_vsync
                return (True, False)

        # FPS limit cycle button
        if getattr(self, 'display_fps_limit_dropdown', None):
            if self.display_fps_limit_dropdown.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('options_control', 'fps_limit')
                self.temp_fps_limit = self._cycle_fps_limit(self.temp_fps_limit)
                return (True, False)

        # ===== GAMEPLAY CONTROLS =====
        
        # Edge Scrolling checkbox
        if self.gameplay_edge_scrolling_checkbox:
            if self.gameplay_edge_scrolling_checkbox.collidepoint(pos):
                self.trigger_click_flash('gameplay_control', 'edge_scrolling')
                self.temp_edge_scrolling_enabled = not self.temp_edge_scrolling_enabled
                return (True, False)
        
        # Edge Scrolling Mode dropdown
        if self.gameplay_edge_scroll_mode_dropdown:
            if self.gameplay_edge_scroll_mode_dropdown.collidepoint(pos):
                self.trigger_click_flash('gameplay_control', 'edge_scroll_mode')
                # Toggle between modes
                if self.temp_edge_scrolling_mode == "map_edge":
                    self.temp_edge_scrolling_mode = "window_edge"
                else:
                    self.temp_edge_scrolling_mode = "map_edge"
                return (True, False)
        
        # Tooltips checkbox
        if self.gameplay_tooltips_checkbox:
            if self.gameplay_tooltips_checkbox.collidepoint(pos):
                self.trigger_click_flash('gameplay_control', 'tooltips')
                self.temp_tooltips_enabled = not self.temp_tooltips_enabled
                return (True, False)
        
        # Tooltip Delay dropdown
        if self.gameplay_tooltip_delay_dropdown:
            if self.gameplay_tooltip_delay_dropdown.collidepoint(pos):
                self.trigger_click_flash('gameplay_control', 'tooltip_delay')
                # Cycle through delays: 300ms -> 500ms -> 700ms -> 1000ms -> Never -> 300ms
                if self.temp_tooltip_delay_ms == 300:
                    self.temp_tooltip_delay_ms = 500
                elif self.temp_tooltip_delay_ms == 500:
                    self.temp_tooltip_delay_ms = 700
                elif self.temp_tooltip_delay_ms == 700:
                    self.temp_tooltip_delay_ms = 1000
                elif self.temp_tooltip_delay_ms == 1000:
                    self.temp_tooltip_delay_ms = -1  # Never
                else:  # -1 (Never)
                    self.temp_tooltip_delay_ms = 300
                return (True, False)
        
        # Camera Pan Speed slider
        if self.gameplay_pan_speed_slider:
            slider_track, min_speed, max_speed, thumb_rect = self.gameplay_pan_speed_slider
            
            # Check if click is on thumb (start dragging)
            if thumb_rect.collidepoint(pos):
                self.trigger_click_flash('gameplay_slider', 'pan_speed')
                self.dragging_slider = 'pan_speed'
                # Store offset from thumb center for smooth dragging
                self.drag_offset = pos[0] - thumb_rect.centerx
                return (True, False)
            # Check if click is on track (direct jump to position)
            elif slider_track.collidepoint(pos):
                self.trigger_click_flash('gameplay_slider', 'pan_speed')
                # Calculate new value based on click position
                rel_x = pos[0] - slider_track.x
                slider_pos = max(0, min(1, rel_x / slider_track.width))
                self.temp_camera_pan_speed = min_speed + slider_pos * (max_speed - min_speed)
                return (True, False)
        
        # Camera Zoom Speed slider
        if self.gameplay_zoom_speed_slider:
            slider_track, min_zoom_speed, max_zoom_speed, thumb_rect = self.gameplay_zoom_speed_slider
            
            # Check if click is on thumb (start dragging)
            if thumb_rect.collidepoint(pos):
                self.trigger_click_flash('gameplay_slider', 'zoom_speed')
                self.dragging_slider = 'zoom_speed'
                # Store offset from thumb center for smooth dragging
                self.drag_offset = pos[0] - thumb_rect.centerx
                return (True, False)
            # Check if click is on track (direct jump to position)
            elif slider_track.collidepoint(pos):
                self.trigger_click_flash('gameplay_slider', 'zoom_speed')
                # Calculate new value based on click position
                rel_x = pos[0] - slider_track.x
                slider_pos = max(0, min(1, rel_x / slider_track.width))
                self.temp_camera_zoom_speed = min_zoom_speed + slider_pos * (max_zoom_speed - min_zoom_speed)
                return (True, False)
        
        # Show FPS checkbox
        if self.gameplay_fps_checkbox:
            if self.gameplay_fps_checkbox.collidepoint(pos):
                self.trigger_click_flash('gameplay_control', 'show_fps')
                self.temp_show_fps = not self.temp_show_fps
                return (True, False)

        # ===== AUDIO VOLUME SLIDERS =====
        # Master Volume slider
        if self.audio_master_slider:
            slider_track, min_val, max_val, thumb_rect = self.audio_master_slider
            if thumb_rect.collidepoint(pos):
                self.trigger_click_flash('audio_slider', 'master_volume')
                self.dragging_slider = 'master_volume'
                self.drag_offset = pos[0] - thumb_rect.centerx
                return (True, False)
            elif slider_track.collidepoint(pos):
                self.trigger_click_flash('audio_slider', 'master_volume')
                rel_x = pos[0] - slider_track.x
                self.temp_master_volume = max(0.0, min(1.0, rel_x / slider_track.width))
                music_manager.set_master_volume(self.temp_master_volume)
                sound_manager.set_volume(self.temp_sfx_volume * self.temp_master_volume)
                return (True, False)

        # Music Volume slider
        if self.audio_music_slider:
            slider_track, min_val, max_val, thumb_rect = self.audio_music_slider
            if thumb_rect.collidepoint(pos):
                self.trigger_click_flash('audio_slider', 'music_volume')
                self.dragging_slider = 'music_volume'
                self.drag_offset = pos[0] - thumb_rect.centerx
                return (True, False)
            elif slider_track.collidepoint(pos):
                self.trigger_click_flash('audio_slider', 'music_volume')
                rel_x = pos[0] - slider_track.x
                self.temp_music_volume = max(0.0, min(1.0, rel_x / slider_track.width))
                music_manager.set_music_volume(self.temp_music_volume)
                return (True, False)

        # SFX Volume slider
        if self.audio_sfx_slider:
            slider_track, min_val, max_val, thumb_rect = self.audio_sfx_slider
            if thumb_rect.collidepoint(pos):
                self.trigger_click_flash('audio_slider', 'sfx_volume')
                self.dragging_slider = 'sfx_volume'
                self.drag_offset = pos[0] - thumb_rect.centerx
                return (True, False)
            elif slider_track.collidepoint(pos):
                self.trigger_click_flash('audio_slider', 'sfx_volume')
                rel_x = pos[0] - slider_track.x
                self.temp_sfx_volume = max(0.0, min(1.0, rel_x / slider_track.width))
                sound_manager.set_volume(self.temp_sfx_volume * self.temp_master_volume)
                return (True, False)

        # ===== END GAMEPLAY CONTROLS =====
        
        # Apply button
        if self.options_apply_button:
            if self.options_apply_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('options_button', 'apply')
                # Apply display settings. VSync is passed through so the display is
                # rebuilt with (or without) SCALED — it cannot be toggled on a live
                # surface, and a later set_mode() would silently drop it.
                width, height = self.temp_resolution
                success = self.apply_display_settings(
                    width, height, self.temp_fullscreen, vsync=self.temp_vsync)
                self.fps_limit = self.temp_fps_limit

                # Apply gameplay settings
                self.edge_scrolling_enabled = self.temp_edge_scrolling_enabled
                self.edge_scrolling_mode = self.temp_edge_scrolling_mode
                self.tooltips_enabled = self.temp_tooltips_enabled
                self.tooltip_delay_ms = self.temp_tooltip_delay_ms
                self.hover_delay = self.tooltip_delay_ms  # Update hover delay
                self.camera_pan_speed = self.temp_camera_pan_speed
                self.camera_zoom_speed = self.temp_camera_zoom_speed
                self.show_fps = self.temp_show_fps

                # Apply audio settings
                self.master_volume = self.temp_master_volume
                self.music_volume = self.temp_music_volume
                self.sfx_volume = self.temp_sfx_volume
                music_manager.set_master_volume(self.master_volume)
                music_manager.set_music_volume(self.music_volume)
                sound_manager.set_volume(self.sfx_volume * self.master_volume)

                # Save settings to config.json
                self.save_settings()
                
                if success:
                    # Close options menu and return to game menu
                    self.options_menu_visible = False
                    self.game_menu_visible = True
                    self.resolution_dropdown_open = False
                    # Reset slider dragging state
                    self.dragging_slider = None
                    self.drag_offset = 0
                else:
                    logger.error("Failed to apply display settings")
                return (True, False)
        
        # Reset to Defaults button
        if self.options_reset_button:
            if self.options_reset_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('options_button', 'reset')
                # Reset all temp settings to defaults
                self.reset_settings_to_defaults()
                return (True, False)
        
        # Back button
        if self.options_back_button:
            if self.options_back_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('options_button', 'back')
                # Close options menu and return to game menu without applying
                self.options_menu_visible = False
                self.game_menu_visible = True
                self.resolution_dropdown_open = False
                # Reset slider dragging state
                self.dragging_slider = None
                self.drag_offset = 0
                # Reset temp settings
                self.temp_resolution = self.current_resolution
                self.temp_fullscreen = self.is_fullscreen
                self.temp_vsync = self.vsync
                self.temp_fps_limit = self.fps_limit
                # Reset temp gameplay settings
                self.temp_edge_scrolling_enabled = self.edge_scrolling_enabled
                self.temp_edge_scrolling_mode = self.edge_scrolling_mode
                self.temp_tooltips_enabled = self.tooltips_enabled
                self.temp_tooltip_delay_ms = self.tooltip_delay_ms
                self.temp_camera_pan_speed = self.camera_pan_speed
                self.temp_camera_zoom_speed = self.camera_zoom_speed
                self.temp_show_fps = self.show_fps
                # Revert audio volumes to saved values (undo live preview)
                self.temp_master_volume = self.master_volume
                self.temp_music_volume = self.music_volume
                self.temp_sfx_volume = self.sfx_volume
                music_manager.set_master_volume(self.master_volume)
                music_manager.set_music_volume(self.music_volume)
                sound_manager.set_volume(self.sfx_volume * self.master_volume)
                return (True, False)
        
        # Click was on menu overlay but not on any control - consume click anyway
        # This prevents clicks from passing through the menu to the game
        # Also close dropdown if it was open and click wasn't on dropdown area
        if self.resolution_dropdown_open:
            # Check if click was outside dropdown area
            click_outside_dropdown = True
            if self.resolution_dropdown_button:
                # Create a rect that encompasses dropdown button and options
                dropdown_area = self.resolution_dropdown_button.copy()
                if self.resolution_option_buttons:
                    # Extend to include all options
                    for option_rect, _ in self.resolution_option_buttons:
                        dropdown_area = dropdown_area.union(option_rect)
                
                if dropdown_area.collidepoint(pos):
                    click_outside_dropdown = False
            
            if click_outside_dropdown:
                self.resolution_dropdown_open = False
        
        return (True, False)
    
    def handle_top_panel_click(self, pos):
        """
        Handle clicks on top panel buttons.
        
        The top panel contains the Menu button which opens the game menu.
        
        Args:
            pos: (x, y) tuple of click position in screen coordinates
            
        Returns:
            bool: True if click was handled, False otherwise
        
        Side Effects:
            - May set self.game_menu_visible = True (menu button)
        """
        # Only handle clicks in top panel area
        if pos[1] >= TOP_PANEL_HEIGHT:
            return False
        
        # Menu button
        if self.menu_button:
            if self.menu_button.collidepoint(pos):
                self.sound_manager.play_ui_click()
                self.trigger_click_flash('top_button', 'menu')
                self.game_menu_visible = True
                self._pause_game()
                return True

        # Players button — opens non-pausing player list / gold transfer window
        if self.players_button and self.players_button.collidepoint(pos):
            self.sound_manager.play_ui_click()
            self.trigger_click_flash('top_button', 'players')
            if self.players_window is None:
                from players_window import PlayersWindow
                self.players_window = PlayersWindow(self)
            self.players_window_visible = True
            return True

        return False
    
    def handle_victory_screen_click(self, pos):
        """
        Handle clicks on victory screen buttons (Phase 2A extraction).
        
        The victory screen appears when game phase is 'ended'. It contains
        two buttons: Restart (starts new game) and Quit (exits application).
        
        Args:
            pos: (x, y) tuple of click position in screen coordinates
            
        Returns:
            tuple: (handled, should_quit)
                handled: True if click was on a victory screen button
                should_quit: True if quit button was clicked
        
        Side Effects:
            - May call self.restart_game() if restart button clicked
        
        Phase Context:
            Only processes clicks when self.game_state.phase == 'ended'
        """
        if self.game_state.phase != 'ended':
            return False, False

        # Check main menu button - set flag to return to main menu and exit game loop
        if self.main_menu_button and self.main_menu_button.collidepoint(pos):
            self.return_to_main_menu = True
            return True, True

        return False, False
    
    def handle_battle_popup_click(self, pos):
        """
        Handle clicks on battle popup buttons (Phase 2A extraction).
        
        The battle popup has two states with different buttons:
        - 'initial': Shows resolve button (starts battle resolution)
        - 'result': Shows close button (dismisses popup)
        
        The 'resolving' state is an animation state with no clickable buttons.
        
        Args:
            pos: (x, y) tuple of click position in screen coordinates
            
        Returns:
            bool: True if click was handled by battle popup
        
        Side Effects:
            - May resolve battle via self.game_state.resolve_battle()
            - May change self.battle_popup_state ('initial' â†’ 'resolving')
            - May close popup by setting self.battle_popup_visible = False
            - May set timer for auto-transition (resolving â†’ result)
            - Stores battle result in self.battle_result for display
        
        Phase Context:
            Only processes clicks when self.battle_popup_visible is True
        """
        if not self.battle_popup_visible:
            return False

        # Delegate to enhanced battle interface if active
        if self.enhanced_battle_ui is not None:
            result = self.enhanced_battle_ui.handle_click(pos)

            if result == 'close':
                # Battle interface closed - finalize battle and clean up
                self._finalize_enhanced_battle()
                return True
            elif result == 'resolve':
                # Resolve button clicked - resolve battle NOW and pass actual result to UI
                # This ensures the battle report shows correct survivor counts
                battle = self.game_state.pending_battles[self.selected_battle_index]
                territory = battle.territory

                # Resolve the actual battle in game state (this removes battle from pending_battles)
                self.game_state.resolve_battle(self.selected_battle_index)

                # Get actual survivors from resolved battle
                actual_winner = battle.winner if battle.resolved else -1
                actual_survivors = getattr(battle, 'surviving_armies', 0)

                # Determine attacker/defender survivors based on winner
                if actual_winner == self.enhanced_battle_ui.attacker_player:
                    attacker_survivors = actual_survivors
                    defender_survivors = 0
                elif actual_winner in self.enhanced_battle_ui.defender_players:
                    attacker_survivors = 0
                    defender_survivors = actual_survivors
                else:
                    # Tie or neutral outcome
                    attacker_survivors = 0
                    defender_survivors = 0

                # Get surviving units from garrison for accurate unit breakdown
                surviving_units = None
                if actual_winner is not None and actual_winner >= 0:
                    garrison = self.game_state.territory_garrisons.get(territory, {})
                    winner_garrison = garrison.get(actual_winner, {})
                    surviving_units = winner_garrison.get('units', [])

                # Pass actual result to battle interface for accurate report display
                self.enhanced_battle_ui.set_actual_battle_result(
                    winner=actual_winner,
                    attacker_survivors=attacker_survivors,
                    defender_survivors=defender_survivors,
                    surviving_units=surviving_units
                )

                # Store resolved battle info for _finalize_enhanced_battle() to use
                # (battle is already removed from pending_battles at this point)
                self._resolved_battle_info = {
                    'battle': battle,
                    'territory': territory,
                    'winner': actual_winner,
                    'surviving_armies': actual_survivors,
                    'new_owner': self.game_state.territory_owners.get(territory, -1),
                    # Stash the Battle Reports now: resolve_battle() ran on THIS click but
                    # the broadcast happens on the later CLOSE click, by which time another
                    # battle could have overwritten game_state.last_battle_reports.
                    'battle_reports': list(self.game_state.last_battle_reports),
                }
                return True

            # Click consumed by interface (animation in progress or no button hit)
            return True

        # LEGACY FALLBACK: Old popup system (kept for safety, should not be reached)
        # Check resolve button (in initial state)
        if self.battle_popup_state == 'initial':
            if self.resolve_battle_button:
                if self.resolve_battle_button.collidepoint(pos):
                    # Store battle info before resolving (will be removed from list)
                    battle = self.game_state.pending_battles[self.selected_battle_index]
                    territory = battle.territory
                    armies_copy = dict(battle.armies)  # Copy armies before resolution
                    compositions_copy = dict(battle.army_compositions) if hasattr(battle, 'army_compositions') else {}
                    has_keep = (hasattr(battle, 'keep_bonus_player') and
                               battle.keep_bonus_player is not None and
                               battle.keep_bonus > 0)
                    defender = battle.original_owner

                    # Resolve the battle
                    self.game_state.resolve_battle(self.selected_battle_index)

                    # Get the new territory owner after resolution
                    new_owner = self.game_state.territory_owners.get(territory, -1)

                    # Store result for display
                    self.battle_result = {
                        'territory': territory,
                        'armies': armies_copy,  # Store armies for animation
                        'compositions': compositions_copy,  # Store unit compositions
                        'has_keep': has_keep,  # Store if Keep battle
                        'defender': defender,  # Store defender player
                        'winner': battle.winner if battle.resolved else -1,
                        'surviving_armies': getattr(battle, 'surviving_armies', 0),
                        'dice_results': getattr(battle, 'dice_results', None)
                    }

                    # MULTIPLAYER: Send battle result to remote player
                    if self.multiplayer_mode:
                
                        battle_data = {
                            'territory': territory,
                            'winner': battle.winner if battle.resolved else -1,
                            'surviving_armies': getattr(battle, 'surviving_armies', 0),
                            'new_owner': new_owner
                        }
                        # Include surviving units composition for sync
                        if new_owner is not None and territory:
                            garrison = self.game_state.territory_garrisons.get(territory, {})
                            winner_garrison = garrison.get(new_owner, {})
                            units = winner_garrison.get('units', [])
                            if units:
                                battle_data['surviving_units'] = [
                                    {'id': u.get('id', i), 'type': u.get('type', 'Swordsman'), 'status': 'moved'}
                                    for i, u in enumerate(units)
                                ]
                        # Check for alliance marker in simultaneous mode (legacy path)
                        if self.sim_state is not None and battle.resolved and hasattr(battle, 'team_members_map'):
                            winner_idx = battle.winner
                            if winner_idx is not None and winner_idx in battle.team_members_map:
                                winning_team = battle.team_members_map[winner_idx]
                                orig_owner = getattr(battle, 'original_owner', -1)
                                if len(winning_team) > 1 and orig_owner != winner_idx:
                                    alliance_marker = {
                                        'type': 'alliance',
                                        'territory': territory,
                                        'players': winning_team,
                                        'chooser': self.sim_state.phase_manager.alliance_handler.determine_chooser(
                                            territory, winning_team
                                        )
                                    }
                                    battle_data['alliance_marker'] = alliance_marker
                                    self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)
                        # Battle Reports ride along: a client APPLIES this result rather
                        # than running resolve_battle(), so without this the defending
                        # client would never learn what happened in its own territory.
                        if self.game_state.last_battle_reports:
                            battle_data['battle_reports'] = list(self.game_state.last_battle_reports)
                        self._send_action_to_remote(MessageType.BATTLE_RESOLVE, battle_data)

                    # Transition to resolving animation
                    self.battle_popup_state = 'resolving'
                    # Auto-transition to result after a short delay
                    pygame.time.set_timer(pygame.USEREVENT + 1, 1500)  # 1.5 seconds
                    return True
        
        # Check close button (in result state)
        elif self.battle_popup_state == 'result':
            if self.close_popup_button:
                if self.close_popup_button.collidepoint(pos):
                    # Close popup
                    self.battle_popup_visible = False
                    self.selected_battle_index = None
                    self.battle_popup_state = 'initial'
                    self.battle_result = None  # Clear stored result

                    # Check if all battles are resolved and turn should advance
                    # Skip in simultaneous mode - sim mode uses complete_round() instead
                    if self.game_state.ready_to_advance_turn and self.sim_state is None:
                        logger.info(f"[TURN_DEBUG] battle_popup close (close_btn): advancing turn")
                        self.game_state._advance_to_next_player()

                        # MULTIPLAYER: Send TURN_END to remote player
                        if self.multiplayer_mode:

                            self._send_action_to_remote(MessageType.TURN_END, {})
                            self._send_full_state_sync()  # Sync fix: authoritative state at turn boundary

                            # Send state checksum for desync detection (any client to host)
                            if self.local_player_index != 0:
                                checksum = self.game_state.calculate_state_checksum()
                                self._send_action_to_remote(MessageType.STATE_CHECKSUM, {
                                    'checksum': checksum,
                                    'turn_number': self.game_state.turn_number
                                })
                                # Sync logger: record snapshot + checksum on client
                                _cl = getattr(self.game_state, 'sync_logger', None)
                                if _cl:
                                    _cl.record_turn_snapshot(self.game_state.turn_number)
                                    _cl.record_checksum(self.game_state.turn_number, checksum)

                    return True

            # In result state, click anywhere outside close button also closes popup
            self.battle_popup_visible = False
            self.selected_battle_index = None
            self.battle_popup_state = 'initial'
            self.battle_result = None

            # Check if all battles are resolved and turn should advance
            # Skip in simultaneous mode - sim mode uses complete_round() instead
            if self.game_state.ready_to_advance_turn and self.sim_state is None:
                logger.info(f"[TURN_DEBUG] battle_popup close (click_outside): advancing turn")
                self.game_state._advance_to_next_player()

                # MULTIPLAYER: Send TURN_END to remote player
                if self.multiplayer_mode:

                    self._send_action_to_remote(MessageType.TURN_END, {})
                    self._send_full_state_sync()  # Sync fix: authoritative state at turn boundary

                    # Send state checksum for desync detection (any client to host)
                    if self.local_player_index != 0:
                        checksum = self.game_state.calculate_state_checksum()
                        self._send_action_to_remote(MessageType.STATE_CHECKSUM, {
                            'checksum': checksum,
                            'turn_number': self.game_state.turn_number
                        })
                        # Sync logger: record snapshot + checksum on client
                        _cl = getattr(self.game_state, 'sync_logger', None)
                        if _cl:
                            _cl.record_turn_snapshot(self.game_state.turn_number)
                            _cl.record_checksum(self.game_state.turn_number, checksum)

            return True

        # Resolving state: Ignore clicks (animation in progress)
        # Return True to consume the click and prevent it from reaching map handlers
        return True

    def _finalize_enhanced_battle(self):
        """
        Finalize battle after enhanced interface animation completes.

        Handles multiplayer sync and cleanup.
        Called when Close button is clicked in REPORT state.
        NOTE: Battle is already resolved when FIGHT button is clicked.
        """
        if self.enhanced_battle_ui is None:
            return

        # Get battle info from stored resolved battle (battle was already resolved on FIGHT click)
        if self._resolved_battle_info is None:
            logger.warning("[WARNING] _finalize_enhanced_battle called but no resolved battle info found")
            self.enhanced_battle_ui = None
            self.battle_popup_visible = False
            self.selected_battle_index = None
            return

        battle = self._resolved_battle_info['battle']
        territory = self._resolved_battle_info['territory']
        new_owner = self._resolved_battle_info['new_owner']
        stashed_battle_reports = self._resolved_battle_info.get('battle_reports', [])

        # Clear stored battle info
        self._resolved_battle_info = None

        # SIMULTANEOUS MODE: Check for allied victory and alliance markers BEFORE sending network message
        alliance_marker = None
        if self.sim_state is not None:
            # Check if allies won together - need alliance marker for territory ownership choice
            # BUT NOT for defensive victories - original owner keeps territory
            if battle.resolved and hasattr(battle, 'team_members_map'):
                winner = battle.winner
                if winner is not None and winner in battle.team_members_map:
                    winning_team_members = battle.team_members_map[winner]

                    # Check if this was a defensive victory (original owner is on winning team)
                    original_owner = getattr(battle, 'original_owner', -1)
                    original_owner_team = self.game_state.player_teams[original_owner] if original_owner >= 0 else -1
                    winner_team = -1 if winner == -1 else self.game_state.player_teams[winner]

                    is_defensive_victory = (original_owner >= 0 and original_owner_team == winner_team)

                    if winner == -1:
                        # Neutral won the battle — no alliance markers needed
                        pass
                    elif len(winning_team_members) > 1 and not is_defensive_victory:
                        # Multiple allies captured enemy/neutral territory - create alliance marker
                        logger.info(f"[SIM] Allied offensive victory at {territory}! Team members: {winning_team_members}")
                        alliance_marker = {
                            'type': 'alliance',
                            'territory': territory,
                            'players': winning_team_members,
                            'chooser': self.sim_state.phase_manager.alliance_handler.determine_chooser(
                                territory, winning_team_members
                            )
                        }
                        self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)
                        logger.info(f"[SIM] Alliance marker created, chooser: {alliance_marker['chooser']}")
                    elif len(winning_team_members) > 1 and is_defensive_victory:
                        # Defensive victory - original owner keeps territory, no alliance marker
                        logger.info(f"[SIM] Defensive victory at {territory} - original owner {original_owner} retains territory")

        # MULTIPLAYER: Send battle result to remote player
        if self.multiplayer_mode:
    
            battle_data = {
                'territory': territory,
                'winner': battle.winner if battle.resolved else -1,
                'surviving_armies': getattr(battle, 'surviving_armies', 0),
                'new_owner': new_owner
            }
            # Include surviving units composition for sync
            # Extract from garrison after battle resolution
            if new_owner is not None and territory:
                garrison = self.game_state.territory_garrisons.get(territory, {})
                winner_garrison = garrison.get(new_owner, {})
                units = winner_garrison.get('units', [])
                if units:
                    # Serialize units for network transmission
                    battle_data['surviving_units'] = [
                        {'id': u.get('id', i), 'type': u.get('type', 'Swordsman'), 'status': 'moved'}
                        for i, u in enumerate(units)
                    ]
            # Include alliance marker info for simultaneous mode
            if alliance_marker:
                battle_data['alliance_marker'] = alliance_marker
            # Battle Reports ride along: a client APPLIES this result rather
            # than running resolve_battle(), so without this the defending
            # client would never learn what happened in its own territory.
            if stashed_battle_reports:
                battle_data['battle_reports'] = list(stashed_battle_reports)
            self._send_action_to_remote(MessageType.BATTLE_RESOLVE, battle_data)

        # Clean up the interface
        self.enhanced_battle_ui = None
        self.battle_popup_visible = False
        self.selected_battle_index = None

        # Notify tutorial mission that battle popup was dismissed by the player,
        # so deferred voice lines can play after the report is closed
        if self._is_tutorial_active():
            self.tutorial_mission.notify_event('battle_popup_closed')

        # SIMULTANEOUS MODE: Check if all battles resolved
        if self.sim_state is not None:
            # Capital Assault: sync battle-based eliminations to sim_state
            # game_state.eliminate_player() runs inside resolve_battle(), but
            # sim_state.eliminate_player() is not called from that path
            if self.game_state.victory_condition == "Capital Assault":
                for pid in range(self.game_state.num_players):
                    if (pid not in self.sim_state.eliminated_players and
                        all(owner != pid for owner in self.game_state.territory_owners.values())):
                        self.sim_state.eliminate_player(pid)
                        logger.info(f"[SIM] Synced elimination of Player {pid + 1} to sim_state after battle")

            if len(self.game_state.pending_battles) == 0:
                logger.info(f"[SIM] All battles resolved. Alliance markers: {len(self.sim_state.phase_manager.pending_alliance_markers)}, sim_phase: {self.sim_state.sim_phase}")
                # Guard: only complete round if still in 'resolving' phase
                # Prevents double round advancement if round was already completed (e.g. by alliance marker auto-resolve)
                if self.sim_state.sim_phase != 'resolving':
                    logger.info(f"[SIM] Skipping complete_round - sim_phase already '{self.sim_state.sim_phase}'")
                elif self.sim_state.phase_manager and not self.sim_state.phase_manager.pending_alliance_markers:
                    # In multiplayer, only host calls complete_round (broadcasts SIM_ROUND_COMPLETE)
                    # Client waits for SIM_ROUND_COMPLETE from host
                    if not self.multiplayer_mode or self.local_player_index == 0:
                        self.sim_state.complete_round()
                    else:
                        logger.info(f"[CLIENT] Waiting for SIM_ROUND_COMPLETE from host")
            return

        # SEQUENTIAL MODE: Check if all battles resolved and turn should advance
        if self.game_state.ready_to_advance_turn:
            logger.info(f"[TURN_DEBUG] _finalize_enhanced_battle: advancing turn (ready_to_advance={self.game_state.ready_to_advance_turn})")
            self.game_state._advance_to_next_player()

            # MULTIPLAYER: Send TURN_END to remote player
            if self.multiplayer_mode:

                self._send_action_to_remote(MessageType.TURN_END, {})
                self._send_full_state_sync()  # Sync fix: authoritative state at turn boundary

                # Send state checksum for desync detection (any client to host)
                if self.local_player_index != 0:
                    checksum = self.game_state.calculate_state_checksum()
                    self._send_action_to_remote(MessageType.STATE_CHECKSUM, {
                        'checksum': checksum,
                        'turn_number': self.game_state.turn_number
                    })
                    # Sync logger: record snapshot + checksum on client
                    _cl = getattr(self.game_state, 'sync_logger', None)
                    if _cl:
                        _cl.record_turn_snapshot(self.game_state.turn_number)
                        _cl.record_checksum(self.game_state.turn_number, checksum)

    def handle_keyboard_input(self, event):
        """
        Handle keyboard input.
        
        Wrapper that delegates to keyboard handler.
        
        Args:
            event: pygame keyboard event (KEYDOWN type)
            
        Returns:
            bool: True if key was handled
        """
        # Save dialog keyboard input takes priority over all other keyboard handling
        if self.save_dialog_active:
            return self.handle_save_dialog_keydown(event)

        # ESC dismisses the unit context menu first, so it doesn't also open the game menu
        if event.key == pygame.K_ESCAPE and self.unit_context_menu:
            self.unit_context_menu = None
            return True

        # ESC then closes the Battle Report detail screen, and failing that clears any
        # outstanding report popups - in both cases instead of opening the game menu.
        if event.key == pygame.K_ESCAPE and self.battle_report_detail_ui is not None:
            self.close_battle_report_detail()
            return True
        if event.key == pygame.K_ESCAPE and self.battle_report_popups:
            self.close_all_battle_reports()
            return True

        # Prepare UI state for handler
        ui_state = {
            'options_menu_visible': self.options_menu_visible,
            'game_menu_visible': self.game_menu_visible,
            'chat_input_active': self.chat_input_active,
            'chat_input_text': self.chat_input_text,
            'chat_channel': self.chat_channel,
            'selected_plot': self.selected_plot,
            'selected_territory': getattr(self, 'selected_territory', None),
            'hovered_territory': getattr(self, 'hovered_territory', None),
            'selected_barracks': self.selected_barracks,
            'resolution_dropdown_open': self.resolution_dropdown_open,
            'temp_resolution': self.temp_resolution,
            'current_resolution': self.current_resolution,
            'temp_fullscreen': self.temp_fullscreen,
            'is_fullscreen': self.is_fullscreen,
            'ability_targeting_active': self.ability_targeting_active,
            'multiplayer_mode': self.multiplayer_mode,
            'local_player_index': self.local_player_index,
            'game_instance': self,  # Pass Game instance for network send
        }
        
        # Delegate to keyboard handler
        handled, updates = self.keyboard.handle_keyboard_event(event, self.game_state, ui_state)
        
        # Apply updates
        for key, value in updates.items():
            if key == 'clear_button_tooltip':
                self.clear_button_tooltip()
            elif key == 'toggle_sidebar':
                # F2 — an action, not an attribute to set
                self._handle_sidebar_hotkey()
            else:
                setattr(self, key, value)

        # Handle pause/unpause when game menu is toggled via keyboard (ESC key)
        if 'game_menu_visible' in updates:
            if updates['game_menu_visible']:
                self._pause_game()
            elif not self.options_menu_visible:
                # Only unpause if not transitioning to options submenu
                self._unpause_game()

        return handled

    def handle_bottom_ui_click(self, pos):
        """
        Handle clicks on bottom UI elements (Phase 2A extraction).
        
        The bottom UI contains all control buttons and contextual panels. This handler
        processes clicks in the bottom UI area (y >= MAP_HEIGHT) and handles various
        UI elements based on current game state.
        
        UI Elements Handled:
            - End Turn button
            - Action Log toggle
            - Training buttons (S/A/P/C when Barracks selected)
            - Training queue cancel buttons
            - Demolish Barracks button
            - Army composition UI (Select All, Deselect All, individual units)
            - Territory info plot buttons
            - Building buttons (Farm, Mine, Barracks, Keep, Square)
            - Cancel construction button
            - Demolish building button
        
        Click Handling Order:
            1. End Turn button (always visible)
            2. Action Log toggle (always visible)
            3. Training buttons (context: Barracks selected)
            4. Queue cancel buttons (context: Barracks selected)
            5. Demolish Barracks button (context: Barracks selected)
            6. Army composition buttons (context: show_army_composition=True)
            7. Territory info plot buttons (context: territory info visible)
            8. Building buttons (context: plot selected)
            9. Cancel/Demolish buttons (context: plot selected)
        
        Args:
            pos: Mouse position (x, y) tuple
        
        Returns:
            bool: True if click was handled by bottom UI, False otherwise
        
        Side Effects:
            - May advance turn (End Turn button)
            - May toggle UI panels (Action Log, Army Composition)
            - May start/cancel training
            - May start/cancel construction
            - May select plots or barracks
            - May clear selections
            - Clears tooltips when appropriate
        
        Phase Context:
            Extracted in Phase 2A to reduce run() method complexity.
            This is the most complex handler due to multiple contextual UIs.
        """
        # Only handle clicks in bottom UI area during playing phase
        if self.game_state.phase != 'playing' or pos[1] < MAP_HEIGHT:
            return False

        # MULTIPLAYER: Block input if spectating (except for ESC menu, camera controls)
        if not self.is_local_player_active():
            return False

        # End Turn button
        if self.end_turn_button and self.end_turn_button.collidepoint(pos):
                # Tutorial hook: block End Turn if not allowed
                if (self.tutorial_mission
                        and self.tutorial_mission.active
                        and not self.tutorial_mission.is_action_allowed('end_turn')):
                    return True  # Silently consume the click

                self.trigger_click_flash('bottom_button', 'end_turn')

                # Tutorial hook: notify end turn event
                if self._is_tutorial_active():
                    self.tutorial_mission.notify_event('end_turn')

                # SIMULTANEOUS MODE: Mark player ready instead of advancing turn
                if self.sim_state is not None:
                    # Guard: reject clicks if not in planning phase or already ready
                    # Prevents rapid double-clicks from marking player ready for the NEXT round,
                    # which would cause execution to trigger from the AI background thread
                    local_player = self.get_local_player()
                    if self.sim_state.sim_phase != 'planning':
                        logger.debug(f"[SIM] End Turn click ignored - phase is '{self.sim_state.sim_phase}', not 'planning'")
                        return True  # Consume click but do nothing
                    if self.sim_state.players_ready.get(local_player, False):
                        logger.debug(f"[SIM] End Turn click ignored - player {local_player} already ready")
                        return True  # Consume click but do nothing

                    # Convert human player's movement orders from game_state to sim_state queue
                    for order in self.game_state.movement_orders:
                        sim_order = {
                            'type': 'movement',
                            'player_id': local_player,
                            'from_territory': order.from_territory,
                            'to_territory': order.to_territory,
                            'army_count': order.army_count,
                            'unit_ids': order.unit_ids if hasattr(order, 'unit_ids') else []
                        }
                        self.sim_state.add_order(local_player, sim_order)
                        logger.debug(f"[SIM] Converted order: {order.from_territory} -> {order.to_territory}")

                    # Clear the game_state movement orders (they're now in sim_state)
                    # Reset unit statuses first
                    for order in self.game_state.movement_orders:
                        if hasattr(order, 'unit_ids') and order.unit_ids:
                            garrison = self.game_state.territory_garrisons.get(order.from_territory, {}).get(local_player)
                            if garrison and 'units' in garrison:
                                for unit in garrison['units']:
                                    if unit.get('id') in order.unit_ids:
                                        unit['status'] = 'ready'
                                        unit['order'] = None
                    self.game_state.movement_orders.clear()

                    # Now mark the player as ready
                    self.sim_state.mark_ready(local_player)

                    # MULTIPLAYER: Send SIM_PLAYER_READY with orders to host
                    if self.multiplayer_mode:
                
                        # Include orders in the ready message so host can merge them
                        orders_to_send = []
                        for order in self.sim_state.player_orders.get(local_player, []):
                            orders_to_send.append(order)
                        self._send_action_to_remote(MessageType.SIM_PLAYER_READY, {
                            'player_id': local_player,
                            'orders': orders_to_send
                        })
                        logger.info(f"[SIM] Sent ready signal with {len(orders_to_send)} orders")

                # SEQUENTIAL MODE: Normal turn advancement
                elif self.multiplayer_mode:
            
                    if self.game_state.turn_phase == 'planning' and len(self.game_state.movement_orders) > 0:
                        # Serialize all movement orders to send to remote player
                        orders_data = []
                        for order in self.game_state.movement_orders:
                            orders_data.append({
                                'from_territory': order.from_territory,
                                'to_territory': order.to_territory,
                                'unit_ids': order.unit_ids
                            })
                        # Orders will execute - send to remote player so they see animations
                        self._send_action_to_remote(MessageType.EXECUTE_ORDERS, {'orders': orders_data})

                    # Send TURN_END (turn is ending, remote player will advance)
                    self._send_action_to_remote(MessageType.TURN_END, {})
                    self._send_full_state_sync()  # Sync fix: authoritative state at turn boundary

                    # Advance to next player
                    self.game_state.next_player()
                else:
                    # Single-player sequential mode
                    # Advance to next player
                    # Note: Units/buildings will spawn in _complete_turn_announcement callback
                    self.game_state.next_player()

                self.selected_plot = None
                self.selected_barracks = None
                self.selected_keep = None
                self.selected_hero = None
                self.selected_territory_info = None
                self.clear_ability_targeting()
                self.show_army_composition = False
                self.selected_army_units = []
                return True
        
        # Training buttons (only when Barracks is actually selected)
        if self.selected_barracks and self.train_buttons:
            for unit_type, button_rect in self.train_buttons.items():
                if button_rect.collidepoint(pos):
                    self.trigger_click_flash('training', unit_type)
                    territory, barracks_plot_index = self.selected_barracks
                    # Shared training path (local execute + sim/network sync + feedback)
                    self._try_start_training(territory, barracks_plot_index, unit_type)
                    return True

        # Queue cancel buttons (only when Barracks is actually selected)
        if self.selected_barracks and self.queue_cancel_buttons:
            for cancel_rect, queue_index in self.queue_cancel_buttons:
                if cancel_rect.collidepoint(pos):
                    # Tutorial hook: block cancel training during tutorial unless allowed
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('cancel_training')):
                        return True  # Silently block
                    self.trigger_click_flash('queue_cancel', queue_index)
                    territory, barracks_plot_index = self.selected_barracks

                    # SIMULTANEOUS MODE: Also remove the queued train order
                    if self.sim_state is not None:
                        # Get the unit_type being cancelled from the training queue
                        training_queue = self.game_state.training_queue.get(territory, {}).get(barracks_plot_index, [])
                        if queue_index < len(training_queue):
                            unit_type_being_cancelled = training_queue[queue_index][0]  # (unit_type, turns)
                            local_player = self.get_local_player()
                            orders = self.sim_state.player_orders.get(local_player, [])
                            # Find and remove ONE matching train order
                            for order in orders:
                                if (order.get('type') == 'train' and
                                    order.get('territory') == territory and
                                    order.get('barracks_plot') == barracks_plot_index and
                                    order.get('unit_type') == unit_type_being_cancelled):
                                    orders.remove(order)
                                    logger.debug(f"[SIM] Removed queued train order: {unit_type_being_cancelled} in {territory}")
                                    break  # Only remove one matching order

                    self.game_state.cancel_training(territory, barracks_plot_index, queue_index)
                    # Sync fix: send training cancel to remote in sequential mode
                    if self.multiplayer_mode and self.sim_state is None:
                        self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                            'cancel_type': 'training',
                            'territory': territory,
                            'barracks_plot': barracks_plot_index,
                            'queue_index': queue_index,
                            'player_index': self.game_state.current_player
                        })
                    return True

        # Demolish Barracks button (only when Barracks is actually selected)
        if self.selected_barracks and self.demolish_barracks_button is not None:
            if self.demolish_barracks_button.collidepoint(pos):
                # Tutorial hook: block demolish during tutorial unless allowed
                if (self.tutorial_mission
                        and self.tutorial_mission.active
                        and not self.tutorial_mission.is_action_allowed('demolish')):
                    return True  # Silently block
                # No new actions while simultaneous mode resolves battles (the map
                # quick-icons already enforced this; the bottom panel did not)
                if self._is_sim_resolving():
                    return True
                self.trigger_click_flash('demolish', 'barracks')
                territory = self.demolish_barracks_territory
                barracks_plot_index = self.demolish_barracks_plot_index

                # SIMULTANEOUS MODE: Also remove any queued train orders for this barracks
                if self.sim_state is not None:
                    local_player = self.get_local_player()
                    orders = self.sim_state.player_orders.get(local_player, [])
                    orders_to_remove = []
                    for order in orders:
                        if (order.get('type') == 'train' and
                            order.get('territory') == territory and
                            order.get('barracks_plot') == barracks_plot_index):
                            orders_to_remove.append(order)
                    for order in orders_to_remove:
                        orders.remove(order)
                        logger.debug(f"[SIM] Removed queued train order (barracks demolished): {order.get('unit_type')} in {territory}")

                if self.game_state.destroy_building(territory, barracks_plot_index):
                    # Sync fix: send demolish to remote players (both sequential and simultaneous)
                    if self.multiplayer_mode:
                        self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                            'cancel_type': 'demolish',
                            'territory': territory,
                            'plot_index': barracks_plot_index,
                            'player_index': self.game_state.current_player
                        })
                    self.selected_barracks = None
                    self.selected_keep = None
                    self.clear_button_tooltip()
                return True

        # Castle upgrade button (only when Keep is actually selected)
        if self.selected_keep and self.castle_upgrade_button:
            if self.castle_upgrade_button.collidepoint(pos):
                # No new actions while simultaneous mode resolves battles (the map
                # quick-icons already enforced this; the bottom panel did not)
                if self._is_sim_resolving():
                    return True
                self.trigger_click_flash('upgrade_castle', None)
                territory, keep_plot_index = self.selected_keep

                # SIMULTANEOUS MODE: Queue upgrade_castle order for sync
                if self.sim_state is not None:
                    if self.game_state.start_castle_upgrade(territory, keep_plot_index):
                        upgrade_order = {
                            'type': 'upgrade_castle',
                            'player_id': self.game_state.current_player,
                            'territory': territory,
                            'plot_index': keep_plot_index
                        }
                        local_player = self.get_local_player()
                        self.sim_state.add_order(local_player, upgrade_order)
                        logger.debug(f"[SIM] Queued castle upgrade order in {territory}")
                        self.clear_button_tooltip()
                    else:
                        self._show_action_failure_feedback()
                else:
                    # SEQUENTIAL MODE: Execute immediately
                    if self.game_state.start_castle_upgrade(territory, keep_plot_index):
                        # Sync fix: send castle upgrade to remote in sequential mode
                        if self.multiplayer_mode:
                            self._send_action_to_remote(MessageType.BUILDING_ORDER, {
                                'territory': territory,
                                'plot_index': keep_plot_index,
                                'building_type': 'CastleUpgrade',
                                'player_index': self.game_state.current_player
                            })
                        self.clear_button_tooltip()
                    else:
                        self._show_action_failure_feedback()
                return True

        # Castle upgrade cancel button (only when Keep is actually selected)
        if self.selected_keep and self.castle_upgrade_cancel_button:
            if self.castle_upgrade_cancel_button.collidepoint(pos):
                self.trigger_click_flash('cancel_castle_upgrade', None)
                territory, keep_plot_index = self.selected_keep

                # SIMULTANEOUS MODE: Also remove the queued upgrade_castle order
                if self.sim_state is not None:
                    local_player = self.get_local_player()
                    orders = self.sim_state.player_orders.get(local_player, [])
                    orders_to_remove = []
                    for order in orders:
                        if (order.get('type') == 'upgrade_castle' and
                            order.get('territory') == territory and
                            order.get('plot_index') == keep_plot_index):
                            orders_to_remove.append(order)
                    for order in orders_to_remove:
                        orders.remove(order)
                        logger.debug(f"[SIM] Removed queued upgrade_castle order in {territory}")

                if self.game_state.cancel_castle_upgrade(territory, keep_plot_index):
                    # Sync fix: send castle upgrade cancel to remote in sequential mode
                    if self.multiplayer_mode and self.sim_state is None:
                        self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                            'cancel_type': 'castle_upgrade',
                            'territory': territory,
                            'keep_plot': keep_plot_index,
                            'player_index': self.game_state.current_player
                        })
                    self.clear_button_tooltip()
                return True

        # Hero cancel button (only when Keep is actually selected, check BEFORE training buttons)
        if self.selected_keep and self.hero_cancel_button:
            if self.hero_cancel_button.collidepoint(pos):
                self.trigger_click_flash('hero_cancel', 'training')
                territory, keep_plot_index = self.selected_keep

                # SIMULTANEOUS MODE: Also remove the queued train_hero order
                if self.sim_state is not None:
                    local_player = self.get_local_player()
                    orders = self.sim_state.player_orders.get(local_player, [])
                    # Find and remove the train_hero order for this territory/plot
                    orders_to_remove = []
                    for order in orders:
                        if (order.get('type') == 'train_hero' and
                            order.get('territory') == territory and
                            order.get('keep_plot_index') == keep_plot_index):
                            orders_to_remove.append(order)
                    for order in orders_to_remove:
                        orders.remove(order)
                        logger.debug(f"[SIM] Removed queued train_hero order: {order.get('hero_type')} in {territory}")

                self.game_state.cancel_hero_training(territory, keep_plot_index)
                # Sync fix: send hero training cancel to remote in sequential mode
                if self.multiplayer_mode and self.sim_state is None:
                    self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                        'cancel_type': 'hero_training',
                        'territory': territory,
                        'keep_plot': keep_plot_index,
                        'player_index': self.game_state.current_player
                    })
                return True

        # Hero training buttons (only when Keep is actually selected)
        if self.selected_keep and self.hero_train_buttons:
            for hero_type, button_rect in self.hero_train_buttons.items():
                if button_rect.collidepoint(pos):
                    # Campaign mission hook: block hero training when mission disallows it.
                    # Checked only once a hero button is actually hit — checking it before
                    # the hit-test swallowed every other bottom-panel click (e.g. Demolish Keep).
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('train_hero')):
                        return True  # Silently block
                    # No new actions while simultaneous mode resolves battles (the map
                    # quick-icons already enforced this; the bottom panel did not)
                    if self._is_sim_resolving():
                        return True
                    self.trigger_click_flash('hero_training', hero_type)
                    territory, keep_plot_index = self.selected_keep

                    # SIMULTANEOUS MODE: Queue hero training order for sync
                    # Execute locally for visual feedback, queue for sync to other players
                    if self.sim_state is not None:
                        if self.game_state.start_hero_training(territory, keep_plot_index, hero_type):
                            # Queue order for sync - remote players will execute this
                            train_hero_order = {
                                'type': 'train_hero',
                                'player_id': self.game_state.current_player,
                                'territory': territory,
                                'keep_plot_index': keep_plot_index,
                                'hero_type': hero_type
                            }
                            local_player = self.get_local_player()
                            self.sim_state.add_order(local_player, train_hero_order)
                            logger.debug(f"[SIM] Queued hero training order: {hero_type} in {territory}")
                            self.clear_button_tooltip()
                        else:
                            self._show_action_failure_feedback()
                    else:
                        # SEQUENTIAL MODE: Execute immediately
                        if self.game_state.start_hero_training(territory, keep_plot_index, hero_type):
                            # Sync fix: send hero training order to remote in sequential mode
                            if self.multiplayer_mode:
                                self._send_action_to_remote(MessageType.HERO_TRAINING_ORDER, {
                                    'territory': territory,
                                    'keep_plot': keep_plot_index,
                                    'hero_type': hero_type,
                                    'player_index': self.game_state.current_player
                                })
                            self.clear_button_tooltip()
                        else:
                            self._show_action_failure_feedback()
                    return True

        # Demolish Keep button (only when Keep is actually selected)
        if self.selected_keep and self.demolish_keep_button:
            if self.demolish_keep_button.collidepoint(pos):
                # Tutorial hook: block demolish during tutorial unless allowed
                if (self.tutorial_mission
                        and self.tutorial_mission.active
                        and not self.tutorial_mission.is_action_allowed('demolish')):
                    return True  # Silently block
                # No new actions while simultaneous mode resolves battles (the map
                # quick-icons already enforced this; the bottom panel did not)
                if self._is_sim_resolving():
                    return True
                self.trigger_click_flash('demolish', 'keep')
                territory = self.demolish_keep_territory
                keep_plot_index = self.demolish_keep_plot_index

                # SIMULTANEOUS MODE: Also remove any queued train_hero orders for this keep
                if self.sim_state is not None:
                    local_player = self.get_local_player()
                    orders = self.sim_state.player_orders.get(local_player, [])
                    orders_to_remove = []
                    for order in orders:
                        if (order.get('type') == 'train_hero' and
                            order.get('territory') == territory and
                            order.get('keep_plot_index') == keep_plot_index):
                            orders_to_remove.append(order)
                    for order in orders_to_remove:
                        orders.remove(order)
                        logger.debug(f"[SIM] Removed queued train_hero order (keep demolished): {order.get('hero_type')} in {territory}")

                if self.game_state.destroy_building(territory, keep_plot_index):
                    # Sync fix: send demolish to remote players (both sequential and simultaneous)
                    if self.multiplayer_mode:
                        self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                            'cancel_type': 'demolish',
                            'territory': territory,
                            'plot_index': keep_plot_index,
                            'player_index': self.game_state.current_player
                        })
                    self.selected_keep = None
                    self.clear_button_tooltip()
                return True

        # Army composition buttons (when army composition UI visible)
        if self.show_army_composition and self.army_composition_buttons:
            # Select All button
            if self.select_all_button:
                if self.select_all_button.collidepoint(pos):
                    self.trigger_click_flash('army_comp', 'select_all')
                    if self.army_composition_territory:
                        # Get units from the specific player's garrison (multi-garrison support)
                        player = self.army_composition_player if self.army_composition_player is not None else self.game_state.current_player
                        garrison = self.game_state.territory_garrisons.get(self.army_composition_territory, {}).get(player)
                        if garrison:
                            units = garrison.get('units', [])
                            self.selected_army_units = [u['id'] for u in units if u['status'] == 'ready']
                    return True
            
            # Deselect All button
            if self.deselect_all_button:
                if self.deselect_all_button.collidepoint(pos):
                    self.trigger_click_flash('army_comp', 'deselect_all')
                    self.selected_army_units = []
                    return True
            
            # Individual unit buttons
            for button_rect, unit_id in self.army_composition_buttons:
                if button_rect.collidepoint(pos):
                    self.trigger_click_flash('army_unit', unit_id)
                    keys = pygame.key.get_mods()
                    if keys & pygame.KMOD_CTRL:
                        # CTRL+Click: Toggle in selection
                        if unit_id in self.selected_army_units:
                            self.selected_army_units.remove(unit_id)
                        else:
                            self.selected_army_units.append(unit_id)
                    else:
                        # Regular click: Replace selection
                        self.selected_army_units = [unit_id]
                    return True
        
        # Territory info plot buttons (only if no Keep or Barracks is already selected)
        if self.selected_territory_info and not self.selected_keep and not self.selected_barracks and self.territory_info_plot_buttons:
            for plot_rect, territory, plot_index in self.territory_info_plot_buttons:
                # Circular collision detection
                plot_center_x = plot_rect.centerx
                plot_center_y = plot_rect.centery
                plot_radius = plot_rect.width // 2
                distance = ((pos[0] - plot_center_x) ** 2 + (pos[1] - plot_center_y) ** 2) ** 0.5
                if distance <= plot_radius:
                    if self.game_state.territory_owners.get(territory, -1) == self.game_state.current_player:
                        # Check if this plot has a Barracks
                        has_barracks = (territory in self.game_state.buildings and
                                      plot_index in self.game_state.buildings[territory] and
                                      self.game_state.buildings[territory][plot_index] == 'Barracks')

                        # Check if this plot has a Keep
                        has_keep = (territory in self.game_state.buildings and
                                   plot_index in self.game_state.buildings[territory] and
                                   self.game_state.buildings[territory][plot_index] == 'Keep')

                        if has_barracks:
                            # Tutorial hook: block barracks click in bottom UI when not allowed
                            if (self.tutorial_mission
                                    and self.tutorial_mission.active
                                    and not self.tutorial_mission.is_action_allowed('click_barracks')):
                                return True  # Silently block
                            # Select Barracks for training UI
                            self.selected_barracks = (territory, plot_index)
                            self.selected_keep = None
                            self.selected_plot = None
                            self.selected_territory_info = None
                            self.game_state.deselect_army()
                            play_structure_sound('Barracks')
                        elif has_keep:
                            # Tutorial hook: block keep click in bottom UI when not allowed
                            if (self.tutorial_mission
                                    and self.tutorial_mission.active
                                    and not self.tutorial_mission.is_action_allowed('click_keep')):
                                return True  # Silently block
                            # Select Keep for hero training UI
                            self.selected_keep = (territory, plot_index)
                            self.selected_barracks = None
                            self.selected_plot = None
                            self.selected_territory_info = None
                            self.game_state.deselect_army()
                            play_structure_sound('Keep')
                        else:
                            # Tutorial hook: block plot selection in bottom UI when not allowed
                            if (self.tutorial_mission
                                    and self.tutorial_mission.active
                                    and not self.tutorial_mission.is_action_allowed('click_plots')):
                                return True  # Silently block
                            # Select plot for building UI
                            self.selected_plot = (territory, plot_index)
                            self.selected_barracks = None
                            self.selected_keep = None
                            self.selected_territory_info = None
                            self.game_state.deselect_army()
                            # Play structure sound: completed building or construction sound
                            completed_building = self.game_state.buildings.get(territory, {}).get(plot_index)
                            if completed_building:
                                play_structure_sound(completed_building)
                            else:
                                play_structure_sound('Construction')
                        return True

        # Building-related buttons (when plot is selected)
        if self.selected_plot:
            # Building buttons
            if self.building_buttons:
                try:
                    if self.building_buttons:
                        for building_name, button_rect in self.building_buttons.items():
                            if button_rect.collidepoint(pos):
                                self.trigger_click_flash('building', building_name)
                                territory, plot_index = self.selected_plot
                                # Shared build path (local execute + sim/network sync + feedback)
                                if self._try_start_construction(territory, plot_index, building_name):
                                    self.selected_plot = None
                                    self.clear_button_tooltip()
                                return True
                except Exception as e:
                    logger.error(f"Error in building buttons: {e}")
            
            # Cancel construction button
            if self.cancel_button is not None:
                if self.cancel_button.collidepoint(pos):
                    # Tutorial hook: block cancel construction during tutorial unless allowed
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('cancel_construction')):
                        return True  # Silently block
                    self.trigger_click_flash('cancel', 'construction')
                    territory, plot_index = self.selected_plot

                    # SIMULTANEOUS MODE: Also remove the queued build order
                    if self.sim_state is not None:
                        local_player = self.get_local_player()
                        orders = self.sim_state.player_orders.get(local_player, [])
                        # Find and remove the build order for this territory/plot
                        orders_to_remove = []
                        for order in orders:
                            if (order.get('type') == 'build' and
                                order.get('territory') == territory and
                                order.get('plot_index') == plot_index):
                                orders_to_remove.append(order)
                        for order in orders_to_remove:
                            orders.remove(order)
                            logger.debug(f"[SIM] Removed queued build order: {order.get('building_type')} in {territory}")

                    result = self.game_state.cancel_construction(territory, plot_index)
                    if result:
                        self.selected_plot = None
                        self.clear_button_tooltip()
                    return True

            # Demolish building button
            if self.demolish_button is not None:
                if self.demolish_button.collidepoint(pos):
                    # Tutorial hook: block demolish during tutorial unless allowed
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('demolish')):
                        return True  # Silently block
                    # No new actions while simultaneous mode resolves battles (the map
                    # quick-icons already enforced this; the bottom panel did not)
                    if self._is_sim_resolving():
                        return True
                    self.trigger_click_flash('demolish', 'building')
                    territory, plot_index = self.selected_plot
                    result = self.game_state.destroy_building(territory, plot_index)
                    if result:
                        # Sync fix: send demolish to remote players (both sequential and simultaneous)
                        if self.multiplayer_mode:
                            self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                                'cancel_type': 'demolish',
                                'territory': territory,
                                'plot_index': plot_index,
                                'player_index': self.game_state.current_player
                            })
                        self.selected_plot = None
                        self.clear_button_tooltip()
                    return True

        # Hero ability buttons (when hero is selected)
        if self.selected_hero and self.hero_ability_buttons:
            for (hero_name, ability_index), button_rect in self.hero_ability_buttons.items():
                if button_rect.collidepoint(pos):
                    # Only the selected hero's abilities; a click on a slot is always
                    # consumed (cooldown / silence / passive simply do nothing)
                    if hero_name == self.selected_hero:
                        self.try_cast_hero_ability(hero_name, ability_index)
                    return True

        # Click not handled by any bottom UI element
        return False
    
    def start_sidebar_camera_pan(self, territory):
        """Smoothly pan the map to `territory` (order card / hero portrait click).

        Centres the territory in the VISIBLE map - left of the sidebar panel when it is
        open (layout.panel_x), the full width when it is collapsed. Refused (returns
        False) while the tutorial locks the camera or another camera animation runs
        (start-of-game zoom, a mission's scripted camera).
        """
        center = self.scaled_centers.get(territory)
        if center is None or self._is_tutorial_blocking('camera'):
            return False
        if self.start_camera_animation is not None and self.start_camera_animation.active:
            return False
        mission_anim = getattr(self.tutorial_mission, 'camera_animation', None) if self.tutorial_mission else None
        if mission_anim is not None and getattr(mission_anim, 'active', False):
            return False
        from campaign_utils import CameraPanAnimation
        # Make the handler current first (the Game keeps its own offset/zoom mirrors)
        self.camera.offset = list(self.camera_offset)
        self.camera.zoom = self.camera_zoom
        self._sidebar_pan = CameraPanAnimation(
            self.camera, center, UIConstants.SIDEBAR_CAMERA_PAN_SECONDS,
            self.get_sidebar_layout().panel_x, MAP_HEIGHT)
        self._sidebar_pan_offset = list(self.camera.offset)
        return True

    def _update_sidebar_pan(self, delta_time):
        """Advance the sidebar camera pan; cancelled when anything else moved the camera."""
        pan = self._sidebar_pan
        if pan is None:
            return
        if list(self.camera_offset) != self._sidebar_pan_offset or self.camera.zoom != self.camera_zoom:
            # Dragged / scrolled / zoomed since our last step: the player took over
            self._sidebar_pan = None
            return
        self.camera.offset = list(self.camera_offset)
        still_active = pan.update(min(delta_time, 0.05))
        self.camera_offset = list(self.camera.offset)
        self._sidebar_pan_offset = list(self.camera_offset)
        if not still_active:
            self._sidebar_pan = None

    def handle_order_sidebar_click(self, pos):
        """
        Handle clicks on order sidebar buttons (Phase 2B extraction).
        
        Manages the movement order sidebar that appears during planning phase.
        Handles three types of buttons:
        1. Toggle button - Expands/collapses sidebar
        2. Individual cancel buttons - Cancels specific movement order
        3. Cancel all button - Cancels all movement orders
        
        The sidebar is only interactive during planning phase. When collapsed,
        only the toggle button is visible. When expanded, all buttons appear.
        
        Args:
            pos: (x, y) tuple of click position in screen coordinates
        
        Returns:
            bool: True if click was handled, False otherwise
        
        Side Effects:
            - May toggle self.game_state.sidebar_expanded
            - May cancel individual movement orders
            - May cancel all movement orders
        
        Phase Context:
            Active during playing phase (both planning and battle turn phases).
            Part of Phase 2B to complete event handler extraction.
        """
        # Only active during playing phase (planning or battle)
        if self.game_state.phase != 'playing':
            return False
        
        # Check bookmark tabs — drawn in every state (sticking out of the panel, or at
        # the screen edge when collapsed), so they are tested in every state too.
        if self.sidebar_tab_buttons:
            for tab_id, tab_rect in self.sidebar_tab_buttons.items():
                if tab_rect.collidepoint(pos):
                    # Tutorial gate: block tabs not in allowed list. A locked bookmark
                    # does nothing at all — it doesn't even open a collapsed panel.
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('sidebar_tab', tab_name=tab_id)):
                        return True  # Silently consume click
                    # Click flash on the bookmark (its sprite brightens briefly)
                    self.trigger_click_flash('sidebar_tab', tab_id)
                    # A bookmark on the collapsed sidebar opens it on that tab
                    if not self.game_state.sidebar_expanded:
                        self.toggle_sidebar(expand=True)
                    # Switch to clicked tab
                    self.game_state.active_sidebar_tab = tab_id

                    # Clear hero selection when switching away from Heroes tab
                    if tab_id != 'heroes':
                        self.selected_hero = None

                    return True
        
        # Check individual order cancel buttons (only if expanded)
        # Order controls answer only on the Action Queue tab (belt and braces: their
        # rects are also cleared on other tabs by draw_order_sidebar)
        on_queue = self.game_state.active_sidebar_tab == 'action_queue'
        if self.game_state.sidebar_expanded and on_queue and self.order_cancel_buttons:
            # Format: (rect, order, player_order_index) — index access, see ui_renderer
            for button in self.order_cancel_buttons:
                if button[0].collidepoint(pos):
                    # Tutorial hook: block order cancellation during tutorial unless allowed
                    if (self.tutorial_mission
                            and self.tutorial_mission.active
                            and not self.tutorial_mission.is_action_allowed('cancel_order')):
                        return True  # Silently block
                    # Find the clicked order by identity: its position in the full list can
                    # differ from its position among this player's orders
                    order = button[1]
                    self.trigger_click_flash('sidebar_cancel_order', getattr(order, 'order_id', None))
                    full_index = next((i for i, o in enumerate(self.game_state.movement_orders)
                                       if o is order), None)
                    if full_index is not None and self.game_state.cancel_movement_order(full_index):
                        # MULTIPLAYER: Notify remote players about cancelled order.
                        # Sent only on success, with the per-player index (the receiver
                        # maps it back through get_full_order_index()).
                        if self.multiplayer_mode:
                            self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                                'player_order_index': button[2],
                                'player_index': self.local_player_index
                            })
                    return True

        # Check cancel all button (only if expanded)
        if self.game_state.sidebar_expanded and self.cancel_all_button:
            if self.cancel_all_button.collidepoint(pos):
                # Tutorial hook: block cancel all orders during tutorial unless allowed
                if (self.tutorial_mission
                        and self.tutorial_mission.active
                        and not self.tutorial_mission.is_action_allowed('cancel_all_orders')):
                    return True  # Silently block
                self.trigger_click_flash('sidebar_cancel_all', None)
                # Cancel only the orders the sidebar shows — other players' orders
                # (e.g. AI orders in the same planning phase) must survive
                self.game_state.cancel_all_orders(player=self.order_sidebar_player)
                # MULTIPLAYER: Notify remote players about cancel-all
                if self.multiplayer_mode:
                    self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                        'cancel_all': True,
                        'player_index': self.local_player_index
                    })
                return True

        # Action Log filter chips
        if self.game_state.sidebar_expanded and self.game_state.active_sidebar_tab == 'action_log':
            for filter_id, chip_rect in (getattr(self, 'sidebar_log_chips', None) or {}).items():
                if chip_rect.collidepoint(pos):
                    self.trigger_click_flash('sidebar_log_filter', filter_id)
                    self.set_sidebar_log_filter(filter_id)
                    return True

        # Order card body (not its Cancel Order button, checked above): flash the card
        # and pan the map to the order's destination
        if self.game_state.sidebar_expanded and on_queue and UIConstants.SIDEBAR_CAMERA_PAN:
            for card_rect, entry in (self.order_card_rects or []):
                if card_rect.collidepoint(pos):
                    self.trigger_click_flash('sidebar_order_card', (entry.from_territory, entry.to_territory))
                    self.start_sidebar_camera_pan(entry.to_territory)
                    return True
        
        return False
    
    def handle_battle_marker_click(self, pos):
        """
        Handle clicks on battle markers to open enhanced battle interface.

        Battle markers (crossed swords icons) appear on territories during the
        battles phase when there are pending battles. Clicking a marker opens
        the cinematic battle interface with side-by-side panels, strength bars,
        particle combat animation, victory/defeat splash, and battle report.

        Only works when:
        - In battles phase (phase='playing', turn_phase='battles')
        - Battle interface is not already active
        - Valid battle markers exist

        Args:
            pos: (x, y) tuple of click position in screen coordinates

        Returns:
            bool: True if click was handled, False otherwise

        Side Effects:
            - Creates EnhancedBattleInterface instance
            - Sets self.selected_battle_index to clicked battle
            - Sets self.battle_popup_visible = True
        """
        # MULTIPLAYER: Block if spectating
        if not self.is_local_player_active():
            return False

        # Only active during battles phase
        # Sequential mode: turn_phase == 'battles'
        # Simultaneous mode: sim_phase == 'resolving'
        in_battle_phase = False
        if self.game_state.phase == 'playing':
            if self.game_state.turn_phase == 'battles':
                in_battle_phase = True
            elif self.sim_state is not None:
                if self.sim_state.sim_phase == 'resolving':
                    in_battle_phase = True

        if not in_battle_phase:
            return False

        # Only if interface not already active
        if self.enhanced_battle_ui is not None or self.battle_popup_visible:
            return False

        # Check battle markers
        if self.battle_markers:
            for i, marker_rect in enumerate(self.battle_markers):
                if marker_rect and marker_rect.collidepoint(pos):
                    if i < len(self.game_state.pending_battles):
                        battle = self.game_state.pending_battles[i]

                        # In simultaneous mode, only the resolver can click the battle marker
                        # The resolver is the player with highest effective strength
                        if self.sim_state is not None:
                            resolver = getattr(battle, 'resolver', None)
                            local_player = self.get_local_player()
                            if resolver is not None and resolver != local_player:
                                logger.error(f"[BATTLE] Player {local_player} cannot click - resolver is player {resolver}")
                                return False  # Not the resolver, can't click

                        self.selected_battle_index = i
                        self.battle_popup_visible = True

                        # Clear all hover states before showing battle interface
                        # This prevents tooltip getting stuck from last hovered element
                        self.hovered_territory = None
                        self.hovered_army = None
                        self.hovered_plot = None
                        self.hover_start_time = None
                        self.hover_target_territory = None
                        self.hover_target_army = None
                        self.show_tooltip_territory = None
                        self.show_tooltip_army = None
                        self.hover_start_time_button = None
                        self.hover_target_button = None
                        self.show_tooltip_button = None
                        self.hovered_composition_button = None

                        # Create enhanced battle interface
                        from ui.effects.battle_interface import EnhancedBattleInterface
                        self.enhanced_battle_ui = EnhancedBattleInterface(
                            screen=self.screen,
                            game_state=self.game_state,
                            battle_index=i,
                            font_manager=self.font_manager,
                            current_player_index=self.game_state.current_player
                        )
                        return True

        return False

    def _handle_resolve_all_battles_click(self):
        """
        Handle click on the "Resolve Remaining Battles" button.

        Plays UI click sound, triggers click flash, then auto-resolves
        all pending battles where the local player is the resolver.
        No battle reports are shown.
        """
        self.sound_manager.play_ui_click()
        self.trigger_click_flash('top_button', 'resolve_all_battles')
        self._resolve_all_pending_battles()

    def _resolve_all_pending_battles(self):
        """
        Auto-resolve all pending battles where the local player is the resolver.

        Resolves battles silently (no battle reports or UI feedback).
        Handles multiplayer sync, alliance markers (sim mode), Capital Assault
        elimination sync, and turn/round advancement after all battles are done.

        Called by _handle_resolve_all_battles_click() when the player clicks
        the "Resolve Remaining Battles" button during battle phase.
        """
        local_player = self.get_local_player()
        safety_limit = 100  # Prevent infinite loop
        iterations = 0

        while self.game_state.pending_battles and iterations < safety_limit:
            iterations += 1

            # Find the first battle where we're the resolver
            # (resolve_battle pops from list, so we must re-scan each iteration)
            resolvable_idx = None
            for idx, b in enumerate(self.game_state.pending_battles):
                if self.sim_state is not None:
                    # Simultaneous mode: only resolve battles where we're the designated resolver
                    if getattr(b, 'resolver', None) == local_player:
                        resolvable_idx = idx
                        break
                else:
                    # Sequential mode: current player resolves all battles on their turn
                    resolvable_idx = idx
                    break

            if resolvable_idx is None:
                break  # No more battles for us to resolve

            battle = self.game_state.pending_battles[resolvable_idx]
            territory = battle.territory

            # Resolve the battle (removes it from pending_battles)
            self.game_state.resolve_battle(resolvable_idx)

            # In sim mode, clear the sequential ready flag — sim mode uses complete_round() instead
            if self.sim_state is not None:
                self.game_state.ready_to_advance_turn = False

            new_owner = self.game_state.territory_owners.get(territory, -1)

            # Handle alliance markers in simultaneous mode
            # (same logic as _finalize_enhanced_battle)
            alliance_marker = None
            if self.sim_state is not None and battle.resolved and hasattr(battle, 'team_members_map'):
                winner = battle.winner
                if winner is not None and winner in battle.team_members_map:
                    winning_team_members = battle.team_members_map[winner]
                    original_owner = getattr(battle, 'original_owner', -1)
                    original_owner_team = self.game_state.player_teams[original_owner] if original_owner >= 0 else -1
                    winner_team = -1 if winner == -1 else self.game_state.player_teams[winner]
                    is_defensive = (original_owner >= 0 and original_owner_team == winner_team)
                    if winner != -1 and len(winning_team_members) > 1 and not is_defensive:
                        alliance_marker = {
                            'type': 'alliance',
                            'territory': territory,
                            'players': winning_team_members,
                            'chooser': self.sim_state.phase_manager.alliance_handler.determine_chooser(
                                territory, winning_team_members
                            )
                        }
                        self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)

            # Multiplayer: send battle result to remote players (same pattern as AI auto-resolve)
            if self.multiplayer_mode:
                battle_data = {
                    'territory': territory,
                    'winner': battle.winner if battle.resolved else -1,
                    'surviving_armies': getattr(battle, 'surviving_armies', 0),
                    'new_owner': new_owner
                }
                # Include surviving units composition for garrison sync
                if new_owner is not None and territory:
                    garrison = self.game_state.territory_garrisons.get(territory, {})
                    winner_garrison = garrison.get(new_owner, {})
                    units = winner_garrison.get('units', [])
                    if units:
                        battle_data['surviving_units'] = [
                            {'id': u.get('id', i), 'type': u.get('type', 'Swordsman'), 'status': 'moved'}
                            for i, u in enumerate(units)
                        ]
                if alliance_marker:
                    battle_data['alliance_marker'] = alliance_marker
                # Battle Reports ride along: a client APPLIES this result rather
                # than running resolve_battle(), so without this the defending
                # client would never learn what happened in its own territory.
                if self.game_state.last_battle_reports:
                    battle_data['battle_reports'] = list(self.game_state.last_battle_reports)
                self._send_action_to_remote(MessageType.BATTLE_RESOLVE, battle_data)

            # Capital Assault: sync battle-based eliminations to sim_state
            if self.sim_state is not None and self.game_state.victory_condition == "Capital Assault":
                for pid in range(self.game_state.num_players):
                    if (pid not in self.sim_state.eliminated_players and
                        all(owner != pid for owner in self.game_state.territory_owners.values())):
                        self.sim_state.eliminate_player(pid)
                        logger.info(f"[SIM] Synced elimination of Player {pid + 1} to sim_state after auto-resolve")

        # Post-loop: advance turn or complete round
        if not self.game_state.pending_battles:
            if self.sim_state is not None:
                # Simultaneous mode: complete round if no pending alliance markers
                if self.sim_state.sim_phase == 'resolving':
                    if not self.sim_state.phase_manager.pending_alliance_markers:
                        if not self.multiplayer_mode or self.local_player_index == 0:
                            self.sim_state.complete_round()
                        else:
                            logger.info(f"[CLIENT] Waiting for SIM_ROUND_COMPLETE from host")
            else:
                # Sequential mode: advance to next player
                if self.game_state.ready_to_advance_turn:
                    logger.info(f"[TURN_DEBUG] _resolve_all_pending_battles: advancing turn")
                    self.game_state._advance_to_next_player()
                    if self.multiplayer_mode:
                        self._send_action_to_remote(MessageType.TURN_END, {})
                        self._send_full_state_sync()
                        # Send state checksum for desync detection (any client to host)
                        if self.local_player_index != 0:
                            checksum = self.game_state.calculate_state_checksum()
                            self._send_action_to_remote(MessageType.STATE_CHECKSUM, {
                                'checksum': checksum,
                                'turn_number': self.game_state.turn_number
                            })
                            # Sync logger: record snapshot + checksum on client
                            _cl = getattr(self.game_state, 'sync_logger', None)
                            if _cl:
                                _cl.record_turn_snapshot(self.game_state.turn_number)
                                _cl.record_checksum(self.game_state.turn_number, checksum)

        # Clear the button rect (button disappears after click)
        self.resolve_all_battles_button = None

    def handle_alliance_marker_click(self, pos, marker):
        """
        Handle clicks on alliance markers to show ownership choice UI.

        Alliance markers appear in simultaneous mode when multiple allied armies
        capture the same territory. The player with the biggest army (chooser)
        can click to choose who owns the territory.

        Args:
            pos: (x, y) tuple of click position in screen coordinates
            marker: Alliance marker data with territory, players, chooser

        Returns:
            bool: True if click was handled, False otherwise
        """
        # Only in simultaneous mode during resolution phase
        if self.sim_state is None:
            return False

        if self.sim_state.sim_phase != 'resolving':
            return False

        # Only the chooser can assign ownership
        current_player = self.game_state.current_player
        chooser = marker.get('chooser')

        if current_player != chooser:
            logger.info(f"[ALLIANCE] Player {current_player} clicked but chooser is {chooser}")
            return False

        # Show the alliance ownership choice popup
        territory = marker['territory']
        allied_players = marker['players']

        logger.info(f"[ALLIANCE] Showing ownership choice for {territory}, allies: {allied_players}")

        # Store alliance marker data for the popup
        self.alliance_choice_popup_visible = True
        self.alliance_choice_territory = territory
        self.alliance_choice_players = allied_players
        self.alliance_choice_chooser = chooser

        return True

    def draw_alliance_choice_popup(self):
        """
        Draw the alliance ownership choice popup.

        Shows a polished panel using IGOptMenuBG.png allowing the chooser to select
        which allied player should own the captured territory.
        Uses GMenuButton.png for player option buttons with player names in their color.
        """
        if not getattr(self, 'alliance_choice_popup_visible', False):
            return

        territory = self.alliance_choice_territory
        players = self.alliance_choice_players

        # Scale factor based on reference resolution (1600x900)
        scale = WINDOW_WIDTH / 1600.0

        # Popup dimensions - generous padding for the PNG border
        border_padding = int(60 * scale)  # Increased padding inside the PNG border
        title_height = int(55 * scale)
        separator_margin = int(22 * scale)
        button_height = int(50 * scale)
        button_spacing = int(18 * scale)
        bottom_padding = int(50 * scale)

        # Calculate content width and popup size
        content_width = int(320 * scale)
        popup_width = content_width + 2 * border_padding
        popup_height = (border_padding + title_height + separator_margin +
                       len(players) * (button_height + button_spacing) + bottom_padding)

        popup_x = (WINDOW_WIDTH - popup_width) // 2
        popup_y = (WINDOW_HEIGHT - popup_height) // 2

        # Store popup rect for click handling
        self.alliance_choice_popup_rect = pygame.Rect(popup_x, popup_y, popup_width, popup_height)

        # PERFORMANCE: Reuse cached overlay instead of allocating full-screen SRCALPHA every frame
        if self._cached_alliance_overlay is None or self._cached_alliance_overlay.get_size() != (WINDOW_WIDTH, WINDOW_HEIGHT):
            self._cached_alliance_overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            self._cached_alliance_overlay.fill((0, 0, 0, 120))
        self.screen.blit(self._cached_alliance_overlay, (0, 0))

        # PERFORMANCE: Cache scaled background — only rescale when popup size changes
        target_size = (popup_width, popup_height)
        if self._cached_alliance_bg_size != target_size:
            self._cached_alliance_bg = pygame.transform.scale(self.ingame_options_menu_bg, target_size)
            self._cached_alliance_bg_size = target_size
        self.screen.blit(self._cached_alliance_bg, (popup_x, popup_y))

        # Draw title "Choose the Territory Owner"
        title_font = self.font_manager.get_font(int(20 * scale), 'bold')
        title_text = self._get_cached_text("Choose the Territory Owner", title_font, WHITE)
        title_rect = title_text.get_rect(centerx=popup_x + popup_width // 2,
                                         top=popup_y + int(32 * scale))
        self.screen.blit(title_text, title_rect)

        # Draw white separator line below title (closer to title)
        separator_y = popup_y + border_padding + title_height - int(22 * scale)
        line_margin = int(28 * scale)
        pygame.draw.line(self.screen, WHITE,
                        (popup_x + border_padding + line_margin, separator_y),
                        (popup_x + popup_width - border_padding - line_margin, separator_y), 2)

        # Draw player options as buttons using GMenuButton.png
        self.alliance_choice_buttons = []
        button_y = separator_y + separator_margin + int(8 * scale)
        button_x = popup_x + border_padding
        button_width = content_width

        for player_id in players:
            # Use get_player_name which returns custom name or generates default
            player_name = self.game_state.get_player_name(player_id)
            player_color = self.game_state.player_colors[player_id]

            # Button rect
            button_rect = pygame.Rect(button_x, button_y, button_width, button_height)
            self.alliance_choice_buttons.append((button_rect, player_id))

            # Draw button using GMenuButton.png with hover/click feedback
            self.helpers.draw_feedback_button(
                button_rect, player_color, self.mouse_pos, self.clicked_element,
                'alliance_choice', f'player_{player_id}',
                text=None,  # We'll draw custom colored text
                bg_image=self.menu_button_img
            )

            # Draw player name in their player color (with generous left padding)
            label_font = self.font_manager.get_font(int(15 * scale), 'regular')
            text_left_padding = int(28 * scale)  # Generous left padding inside button
            text_area_x = button_x + text_left_padding
            text_area_width = button_width - text_left_padding - int(18 * scale)

            # Truncate player name if too long
            display_name = player_name
            name_surface = self._get_cached_text(display_name, label_font, player_color)
            while name_surface.get_width() > text_area_width and len(display_name) > 10:
                display_name = display_name[:-4] + "..."
                name_surface = self._get_cached_text(display_name, label_font, player_color)

            # Center text vertically within button
            name_rect = name_surface.get_rect(
                left=text_area_x,
                centery=button_y + button_height // 2
            )
            self.screen.blit(name_surface, name_rect)

            button_y += button_height + button_spacing

    def handle_alliance_choice_click(self, pos):
        """
        Handle clicks on the alliance ownership choice popup.

        Args:
            pos: Click position (x, y)

        Returns:
            bool: True if click was handled
        """
        if not getattr(self, 'alliance_choice_popup_visible', False):
            return False

        # Check if click is outside popup (dismiss)
        if self.alliance_choice_popup_rect:
            if not self.alliance_choice_popup_rect.collidepoint(pos):
                self.alliance_choice_popup_visible = False
                return True

        # Check player option buttons
        if self.alliance_choice_buttons:
            for button_rect, player_id in self.alliance_choice_buttons:
                if button_rect.collidepoint(pos):
                    # Assign territory to chosen player
                    territory = self.alliance_choice_territory
                    logger.info(f"[ALLIANCE] Player chose to assign {territory} to player {player_id}")

                    # Use phase manager to resolve the alliance marker
                    self.sim_state.phase_manager.resolve_alliance_marker(territory, player_id)

                    # Send alliance choice to other players in multiplayer
                    # Both host and client need to send - host broadcasts to clients, client sends to host
                    if self.multiplayer_mode:
                
                        self._send_action_to_remote(MessageType.SIM_ALLIANCE_CHOICE, {
                            'territory': territory,
                            'new_owner': player_id
                        })
                        logger.debug(f"[NETWORK] Sent SIM_ALLIANCE_CHOICE: {territory} -> player {player_id}")

                    # Close popup
                    self.alliance_choice_popup_visible = False
                    return True

        return True  # Consume clicks inside popup

    # ========== FORCED DEFEND POPUP ==========

    # ==================================================================
    # Battle Reports (on-map summaries for a defender)
    # ==================================================================

    MAX_BATTLE_REPORTS_SHOWN = 20  # Matches GameState.MAX_BATTLE_REPORTS_PER_PLAYER

    def _get_report_viewer(self):
        """
        The player whose Battle Reports should currently be on screen.

        In multiplayer that is always the local slot. In single-player it is the
        player whose turn it is, so hotseat works: get_local_player() returns the
        first non-AI player, which would be 0 for BOTH humans in a 2-human game.
        """
        if self.multiplayer_mode and self.local_player_index is not None:
            return self.local_player_index
        if self.sim_state is not None:
            # Everyone plans at once, so "whose turn is it" is meaningless here, and
            # sim code temporarily swaps current_player while running each player's
            # orders -- reading it could hand back an AI slot.
            return self.get_local_player()
        return self.game_state.current_player

    def _viewer_in_planning(self):
        """
        Whether the viewer's own planning phase is currently running.

        This governs CLEARING, and is deliberately separate from
        _battle_reports_visible(): reports are queued before a turn begins and the
        turn announcement plays first, so keying the clear on visibility would
        destroy every report during the very announcement that precedes the turn
        they belong to.
        """
        gs = self.game_state
        if gs.phase != 'playing':
            return False

        viewer = self._get_report_viewer()
        if self.sim_state is not None:
            if self.sim_state.sim_phase != 'planning':
                return False
            return not self.sim_state.players_ready.get(viewer, False)
        return gs.current_player == viewer and gs.turn_phase == 'planning'

    def _battle_reports_visible(self):
        """
        Whether reports may be drawn and may accept clicks right now.

        Stricter than _viewer_in_planning(): the turn_announcement_active guard is
        load-bearing, not cosmetic, because the event loop `continue`s past every
        mouse and keyboard event while an announcement plays, so a popup drawn then
        would silently swallow clicks.
        """
        if not self._viewer_in_planning():
            return False
        if self.game_state.turn_announcement_active:
            return False
        if self.victory_sequence_active or self.victory_sequence_pending:
            return False
        return True

    def queue_battle_report(self, report):
        """
        Add one report snapshot to its defender's queue (bounded).

        In multiplayer only the local slot is kept: the resolver also captures the
        reports of REMOTE defenders (it is the machine that ran resolve_battle), and
        those belong to the other player, who receives them over the network. Keeping
        them here would pile up queues this client can never display.

        In single-player every human is kept, so hotseat works -- each player sees
        their own reports as their turn comes round.
        """
        defender = report.get('defender')
        if defender is None or defender < 0:
            return
        if self.multiplayer_mode and self.local_player_index is not None:
            if defender != self.local_player_index:
                return
        queue = self.battle_report_queues.setdefault(defender, [])
        queue.append(report)
        if len(queue) > self.MAX_BATTLE_REPORTS_SHOWN:
            del queue[:len(queue) - self.MAX_BATTLE_REPORTS_SHOWN]

    def _update_battle_reports(self, delta_time):
        """
        Single per-frame owner of Battle Report promotion AND clearing.

        Clearing here rather than at each End Turn site means every way a planning
        phase can end is covered by one place: the End Turn button, planning-timer
        expiry, simultaneous-mode auto-ready and mark_ready(), a network TURN_END,
        and AI takeover.
        """
        # Drain whatever resolve_battle() produced since the last frame. This is what
        # catches AI-resolved battles, which have no main.py call site of their own.
        inbox = getattr(self.game_state, 'battle_report_inbox', None)
        if inbox:
            for report in inbox:
                self.queue_battle_report(report)
            del inbox[:]

        viewer = self._get_report_viewer()
        in_planning = self._viewer_in_planning()
        owner = self._battle_report_planning_owner

        # Clear on the TRANSITION OUT of a planning phase, never merely because we are
        # not in one. Battles resolve while nobody is planning -- in simultaneous mode
        # that is the 'resolving' phase, where the viewer IS the defender -- so a
        # "not in planning, therefore clear" rule wipes each report on the very frame
        # it was captured, and the feature never shows anything.
        if owner is not None and (not in_planning or owner != viewer):
            self.battle_report_queues[owner] = []
            self._battle_report_planning_owner = None
            owner = None

        if not in_planning:
            self.battle_report_popups = []
            self.battle_report_rects = []
            return

        # Their planning phase is running: remember whose, so we know what to clear
        # when it ends.
        self._battle_report_planning_owner = viewer

        if not self._battle_reports_visible():
            # Temporarily hidden (turn announcement, victory cinematic) but NOT over:
            # keep the queue, since reports are captured before the announcement that
            # opens the very turn they belong to.
            if self.battle_report_popups:
                self.battle_report_popups = []
                self.battle_report_rects = []
            return

        self.battle_report_popups = self.battle_report_queues.get(viewer, [])

    def _battle_report_anchor(self, report):
        """
        Screen position of a report's territory, or None when it cannot be placed.

        Uses the same chain every territory-anchored visual uses: the pre-scaled world
        centre, transformed by the camera, so the popup tracks pans and zooms.
        """
        territory = report.get('territory')
        if territory not in self.scaled_centers:
            return None
        return self.world_to_screen(self.scaled_centers[territory])

    def _get_battle_report_bounds(self):
        """The map band a popup must stay inside (between the top and bottom panels)."""
        return (0, TOP_PANEL_HEIGHT, WINDOW_WIDTH, BOTTOM_UI_Y)

    def draw_battle_reports(self):
        """Draw the viewer's Battle Report popups and rebuild their clickable rects."""
        self.battle_report_rects = []
        if not self.battle_report_popups or self.battle_report_detail_ui is not None:
            return
        if not self._battle_reports_visible():
            return

        if self.battle_report_renderer is None:
            from ui.battle_report_popup import BattleReportPopupRenderer
            self.battle_report_renderer = BattleReportPopupRenderer(self)

        self.battle_report_rects = self.battle_report_renderer.draw(
            self.screen, self.battle_report_popups,
            self._get_battle_report_bounds(), self._battle_report_anchor)

    def _battle_report_rect_at(self, pos):
        """
        The (rect, action, report) under `pos`, or None.

        Iterated in REVERSE draw order so the popup rendered on top -- the one the
        player can actually see -- is the one that wins an overlapping click.
        """
        for entry in reversed(self.battle_report_rects):
            if entry[0].collidepoint(pos):
                return entry
        return None

    def _battle_reports_accept_clicks(self):
        """
        Whether Battle Reports may consume clicks right now.

        They sit at Priority 0, above everything, so they must stand down whenever a
        higher modal is open -- otherwise they would steal clicks from the game menu
        and options menu, which live at Priority 3/4.
        """
        if not self.battle_report_rects:
            return False
        if self.battle_report_detail_ui is not None:
            return False
        if (self.game_menu_visible or self.options_menu_visible
                or self.save_dialog_active or self.battle_popup_visible):
            return False
        if getattr(self, 'alliance_choice_popup_visible', False):
            return False
        if self.game_state.phase == 'ended':
            return False
        return True

    def handle_battle_report_click(self, pos):
        """
        Priority 0 click handling for Battle Reports.

        Deliberately NOT modal: a click that misses every popup returns False and
        falls through to normal play, so reports never block the map underneath.
        """
        if not self._battle_reports_accept_clicks():
            return False

        hit = self._battle_report_rect_at(pos)
        if hit is None:
            return False

        _rect, action, report = hit
        self.sound_manager.play_ui_click()
        self.trigger_click_flash('battle_report', action)

        if action == 'close':
            self.dismiss_battle_report(report)
        elif action == 'detail':
            self.open_battle_report_detail(report)
        return True

    def dismiss_battle_report(self, report):
        """Remove one report from the viewer's queue and from the screen."""
        viewer = self._get_report_viewer()
        queue = self.battle_report_queues.get(viewer)
        if queue and report in queue:
            queue.remove(report)
        if report in self.battle_report_popups:
            self.battle_report_popups.remove(report)
        self.battle_report_rects = []

    def close_all_battle_reports(self):
        """Clear every outstanding report for the viewer (the top-bar button)."""
        viewer = self._get_report_viewer()
        self.battle_report_queues[viewer] = []
        self.battle_report_popups = []
        self.battle_report_rects = []
        self.close_all_battle_reports_button = None

    def _handle_close_all_battle_reports_click(self):
        """Top-bar 'Close All Battle Reports' button."""
        self.sound_manager.play_ui_click()
        self.trigger_click_flash('top_button', 'close_all_battle_reports')
        self.close_all_battle_reports()

    def open_battle_report_detail(self, report):
        """
        Open the full battle result screen for a report, from the DEFENDER's side.

        Built from the stored snapshot rather than a battle index: the Battle object
        was popped from pending_battles the instant it resolved, so there is nothing
        left to read.
        """
        from ui.effects.battle_interface import EnhancedBattleInterface
        try:
            self.battle_report_detail_ui = EnhancedBattleInterface(
                screen=self.screen,
                game_state=self.game_state,
                battle_index=None,
                font_manager=self.font_manager,
                current_player_index=report.get('defender', 0),
                report_snapshot=report,
            )
        except Exception as exc:  # pragma: no cover - defensive, never blocks play
            logger.warning("Could not open battle report detail: %s", exc)
            self.battle_report_detail_ui = None
            return
        self._battle_report_detail_source = report
        # Clear hover state so nothing underneath keeps highlighting behind the modal.
        self.battle_report_rects = []

    def close_battle_report_detail(self):
        """
        Close the detail screen and drop the report it was showing.

        Uses its own path rather than _finalize_enhanced_battle(), which would
        re-broadcast a BATTLE_RESOLVE network message and re-create alliance markers
        for a battle that was already resolved and finalised long ago.
        """
        self.battle_report_detail_ui = None
        report = getattr(self, '_battle_report_detail_source', None)
        self._battle_report_detail_source = None
        if report is not None:
            self.dismiss_battle_report(report)

    def handle_battle_report_detail_click(self, pos):
        """Route a click into the open detail screen. Modal: always consumes."""
        ui = self.battle_report_detail_ui
        if ui is None:
            return False
        if ui.handle_click(pos) == 'close' or ui.is_finished():
            self.close_battle_report_detail()
        return True

    def draw_battle_report_detail(self):
        """Render the detail screen, if one is open."""
        if self.battle_report_detail_ui is not None:
            self.battle_report_detail_ui.render()

    def _queue_forced_defend_popup(self, territory: str, intended_target: str):
        """
        Queue a forced defend notification popup.

        Multiple forced defends will show one after another.
        Each popup auto-closes after 10 seconds or when user clicks Close.

        Args:
            territory: Territory where the army was forced to defend
            intended_target: Territory the army was trying to attack
        """
        message = {
            'territory': territory,
            'intended_target': intended_target
        }
        self.forced_defend_popup_queue.append(message)

        # If no popup currently showing, show the first one
        if not self.forced_defend_popup_visible:
            self._show_next_forced_defend_popup()

    def _show_next_forced_defend_popup(self):
        """Show the next forced defend popup from the queue."""
        if not self.forced_defend_popup_queue:
            self.forced_defend_popup_visible = False
            self.forced_defend_popup_current = None
            return

        # Pop the next message and show it
        self.forced_defend_popup_current = self.forced_defend_popup_queue.pop(0)
        self.forced_defend_popup_visible = True
        self.forced_defend_popup_timer = 10.0  # 10 seconds auto-close

        # Also add to action log
        territory = self.forced_defend_popup_current['territory']
        target = self.forced_defend_popup_current['intended_target']
        self.game_state.add_message(
            f"Your army in {territory} was forced to defend! "
            f"The enemy's overwhelming strength stopped your attack on {target}."
        )

    def _close_forced_defend_popup(self):
        """Close current forced defend popup and show next if any."""
        self.forced_defend_popup_visible = False
        self.forced_defend_popup_current = None

        # Show next popup if any in queue
        if self.forced_defend_popup_queue:
            self._show_next_forced_defend_popup()

    def update_forced_defend_popup(self, dt: float):
        """
        Update forced defend popup timer.

        Called each frame to decrement auto-close timer.

        Args:
            dt: Delta time in seconds since last frame
        """
        if self.forced_defend_popup_visible and self.forced_defend_popup_timer > 0:
            self.forced_defend_popup_timer -= dt
            if self.forced_defend_popup_timer <= 0:
                self._close_forced_defend_popup()

    def draw_forced_defend_popup(self):
        """
        Draw the forced defend notification popup.

        Shows a modal dialog informing the player their attack was stopped
        due to overwhelming enemy strength. Has a Close button and auto-closes
        after 10 seconds.
        """
        if not self.forced_defend_popup_visible or not self.forced_defend_popup_current:
            return

        territory = self.forced_defend_popup_current['territory']
        target = self.forced_defend_popup_current['intended_target']

        # Scale factor based on reference resolution (1600x900)
        scale_x = WINDOW_WIDTH / 1600
        scale_y = WINDOW_HEIGHT / 900
        scale = min(scale_x, scale_y)

        # Popup dimensions (increased for longer territory names)
        popup_width = int(550 * scale)
        popup_height = int(240 * scale)
        popup_x = (WINDOW_WIDTH - popup_width) // 2
        popup_y = (WINDOW_HEIGHT - popup_height) // 2

        self.forced_defend_popup_rect = pygame.Rect(popup_x, popup_y, popup_width, popup_height)

        # Draw semi-transparent overlay (cached to avoid 5.44MB SRCALPHA alloc per frame)
        size = (WINDOW_WIDTH, WINDOW_HEIGHT)
        if self._cached_defend_overlay is None or self._cached_defend_overlay.get_size() != size:
            self._cached_defend_overlay = pygame.Surface(size, pygame.SRCALPHA)
            self._cached_defend_overlay.fill((0, 0, 0, 150))
        overlay = self._cached_defend_overlay
        self.screen.blit(overlay, (0, 0))

        # Draw popup background
        pygame.draw.rect(self.screen, (40, 35, 30), self.forced_defend_popup_rect)
        pygame.draw.rect(self.screen, (180, 150, 100), self.forced_defend_popup_rect, 3)

        # Draw title
        title_font = self.font  # Use default font
        title_text = "Attack Stopped!"
        title_surface = self._get_cached_text(title_text, title_font, (255, 80, 80))
        title_x = popup_x + (popup_width - title_surface.get_width()) // 2
        title_y = popup_y + int(15 * scale)
        self.screen.blit(title_surface, (title_x, title_y))

        # Draw message
        msg_font = self.font
        line1 = f"Your army in {territory} was forced to defend!"
        line2 = f"The enemy's overwhelming strength stopped"
        line3 = f"your attack on {target}."

        msg_y = popup_y + int(55 * scale)
        line_height = int(25 * scale)

        for line in [line1, line2, line3]:
            line_surface = self._get_cached_text(line, msg_font, (220, 210, 190))
            line_x = popup_x + (popup_width - line_surface.get_width()) // 2
            self.screen.blit(line_surface, (line_x, msg_y))
            msg_y += line_height

        # Draw Close button
        button_width = int(100 * scale)
        button_height = int(35 * scale)
        button_x = popup_x + (popup_width - button_width) // 2
        button_y = popup_y + popup_height - int(50 * scale)

        self.forced_defend_close_button = pygame.Rect(button_x, button_y, button_width, button_height)

        # Button background
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = self.forced_defend_close_button.collidepoint(mouse_pos)
        btn_color = (100, 80, 60) if is_hovered else (70, 60, 50)
        pygame.draw.rect(self.screen, btn_color, self.forced_defend_close_button)
        pygame.draw.rect(self.screen, (180, 150, 100), self.forced_defend_close_button, 2)

        # Button text
        btn_text = "Close"
        btn_surface = self._get_cached_text(btn_text, msg_font, (220, 210, 190))
        btn_text_x = button_x + (button_width - btn_surface.get_width()) // 2
        btn_text_y = button_y + (button_height - btn_surface.get_height()) // 2
        self.screen.blit(btn_surface, (btn_text_x, btn_text_y))

    def handle_forced_defend_click(self, pos) -> bool:
        """
        Handle clicks on the forced defend popup.

        Args:
            pos: (x, y) tuple of click position

        Returns:
            bool: True if click was handled (consumed), False otherwise
        """
        if not self.forced_defend_popup_visible:
            return False

        # Check Close button
        if self.forced_defend_close_button and self.forced_defend_close_button.collidepoint(pos):
            self._close_forced_defend_popup()
            return True

        # Check click outside popup (also closes)
        if self.forced_defend_popup_rect and not self.forced_defend_popup_rect.collidepoint(pos):
            self._close_forced_defend_popup()
            return True

        return True  # Consume clicks inside popup

    def _can_cast_from_sidebar(self):
        """May the viewer cast hero abilities from the sidebar right now?

        Mirrors the bottom-bar Hero UI: the game is in play, it is the viewer's turn to
        act (casting uses game_state.current_player, and in sequential single-player
        is_local_player_active() is True even during AI turns), the viewer is active
        (multiplayer / simultaneous Ready), and no battle resolution is under way (the
        bottom bar hides the Hero UI then).
        """
        gs = self.game_state
        if gs is None or gs.phase != 'playing':
            return False
        if gs.current_player != self.get_local_player() or not self.is_local_player_active():
            return False
        if self._is_sim_resolving():
            return False
        if gs.turn_phase == 'battles' and gs.pending_battles:
            return False
        return True

    def handle_heroes_tab_click(self, pos):
        """
        Handle clicks on hero selection buttons in the Heroes sidebar tab.

        When a hero is clicked in the Heroes tab, it becomes selected and
        the bottom panel UI switches to show the Hero UI with details,
        abilities, and information.

        Args:
            pos: (x, y) tuple of click position in screen coordinates

        Returns:
            bool: True if click was handled, False otherwise

        Side Effects:
            - Sets self.selected_hero to the clicked hero name
            - Clears other UI selections (territory, plot, barracks, keep)
        """
        # Ability icons on the hero cards: cast exactly like the bottom-bar buttons
        # (shared try_cast_hero_ability), only when it's the viewer's turn to act
        for (hero_name, ability_index), icon_rect in (getattr(self, 'sidebar_hero_ability_buttons', None) or {}).items():
            if icon_rect.collidepoint(pos):
                if self._can_cast_from_sidebar():
                    self.try_cast_hero_ability(hero_name, ability_index, flash_type='sidebar_hero_ability')
                return True

        # Check if we have hero selection buttons stored
        if not self.hero_selection_buttons:
            return False

        # Check each hero button
        for hero_name, hero_rect in self.hero_selection_buttons.items():
            if hero_rect.collidepoint(pos):
                # Hero clicked - select it (click flash on the card)
                self.trigger_click_flash('sidebar_hero_card', hero_name)
                self.selected_hero = hero_name

                # The portrait also pans the map to the hero's Keep
                portrait = (getattr(self, 'hero_portrait_rects', None) or {}).get(hero_name)
                if portrait is not None and portrait.collidepoint(pos) and UIConstants.SIDEBAR_CAMERA_PAN:
                    hero_data = self.game_state.heroes.get(self.get_local_player(), {}).get(hero_name, {})
                    if hero_data.get('keep_territory'):
                        self.start_sidebar_camera_pan(hero_data['keep_territory'])

                # Play hero selection voice line
                from global_sound import play_hero_select_sound
                play_hero_select_sound(hero_name)

                # Deselect other UI elements
                self.selected_plot = None
                self.selected_barracks = None
                self.selected_keep = None
                self.selected_territory_info = None
                self.game_state.selected_army = None  # Clear army selection
                self.show_army_composition = False  # Close army composition UI
                self.selected_army_units = []  # Clear unit selection

                return True

        return False

    def handle_technology_tab_click(self, pos, right_click=False):
        """
        Handle clicks on technology buttons in the Technology sidebar tab.

        When a technology is clicked:
        - Left-click on available tech: start research
        - Right-click on researching tech: cancel research with full refund
        - If already researched: no action
        - If locked: show feedback (via screen flash already handled by button system)

        Args:
            pos: (x, y) tuple of click position in screen coordinates
            right_click: True if this is a right-click

        Returns:
            bool: True if click was handled, False otherwise

        Side Effects:
            - May start or cancel research
        """
        # Block research during simultaneous mode resolution phase. The tree still looks
        # normal then, so a click on a technology explains why nothing happens.
        if self._is_sim_resolving():
            if any(rect.collidepoint(pos) for rect in (self.technology_buttons or {}).values()):
                self.show_action_error('wrong_phase')
                return True
            return False

        # Check if we have technology buttons stored
        if not self.technology_buttons:
            return False

        # Check each technology button
        for tech_id, tech_rect in self.technology_buttons.items():
            if tech_rect.collidepoint(pos):
                # Find the technology data
                tech = None
                for t in self.game_state.technologies:
                    if t['id'] == tech_id:
                        tech = t
                        break

                if not tech:
                    return False

                # Click flash on the tech tile (the renderer already reads
                # ('technology_button', id) from clicked_element, but nothing set it)
                self.trigger_click_flash('technology_button', tech_id)

                # Check if this tech is being researched
                is_researching = False
                if self.game_state.current_player in self.game_state.research_in_progress:
                    research = self.game_state.research_in_progress[self.game_state.current_player]
                    if research['tech_id'] == tech_id:
                        is_researching = True

                # Handle right-click to cancel research
                if right_click and is_researching:
                    self.game_state.cancel_research()
                    # Sync fix: send research cancel to remote in sequential mode
                    if self.multiplayer_mode and self.sim_state is None:
                        self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                            'cancel_type': 'research',
                            'tech_id': tech_id,
                            'player_index': self.game_state.current_player
                        })
                    # SIMULTANEOUS MODE: Remove queued research order
                    if self.sim_state is not None:
                        local_player = self.get_local_player()
                        orders = self.sim_state.player_orders.get(local_player, [])
                        # Remove research order for this tech
                        self.sim_state.player_orders[local_player] = [
                            o for o in orders
                            if not (o.get('type') == 'research' and o.get('tech_id') == tech_id)
                        ]
                        logger.debug(f"[SIM] Removed research order for tech {tech_id}")
                    return True

                # Handle left-click to start research
                if not right_click:
                    # Tutorial gating: check if research is allowed for this tech
                    if (self.tutorial_mission
                            and self.tutorial_mission.active):
                        if not self.tutorial_mission.is_action_allowed('research', tech_id=tech_id):
                            logger.info(f"[TUTORIAL] Research blocked: {tech['name']}")
                            return True  # Block silently

                    # Check per-player state
                    current_player = self.game_state.current_player
                    is_available = tech_id in self.game_state.player_tech_available[current_player]
                    is_researched = tech_id in self.game_state.player_tech_researched[current_player]

                    if is_available and not is_researched and not is_researching:
                        # SIMULTANEOUS MODE: Queue research order and execute locally
                        if self.sim_state is not None:
                            if self.game_state.start_research(tech_id):
                                # Queue order for sync
                                research_order = {
                                    'type': 'research',
                                    'player_id': current_player,
                                    'tech_id': tech_id
                                }
                                local_player = self.get_local_player()
                                self.sim_state.add_order(local_player, research_order)
                                logger.debug(f"[SIM] Queued research order: {tech_id}")
                            else:
                                self._show_action_failure_feedback()
                        else:
                            # SEQUENTIAL MODE: Execute immediately
                            if self.game_state.start_research(tech_id):
                                # Sync fix: send research order to remote in sequential mode
                                if self.multiplayer_mode:
                                    self._send_action_to_remote(MessageType.RESEARCH_ORDER, {
                                        'tech_id': tech_id,
                                        'player_index': current_player
                                    })
                            else:
                                self._show_action_failure_feedback()
                        return True
                    elif is_researched:
                        # Already researched - just feedback
                        logger.info(f"Already researched: {tech['name']}")
                        return True
                    elif is_researching:
                        # Already researching - feedback
                        logger.info(f"Already researching: {tech['name']}")
                        return True
                    else:
                        # Locked technology
                        logger.info(f"Technology locked: {tech['name']}")
                        return True

        return False

    def handle_mouse_motion(self, pos):
        """
        Handle mouse motion for hover detection (Phase 2C extraction, Phase 2D camera update).
        
        Manages hover detection and highlighting for map elements. Uses a dual
        system: instant visual highlights (no delay) and delayed tooltips.
        
        NOW CAMERA-AWARE: Converts screen position to world position for accurate
        hover detection with camera offset and zoom.
        
        Detects hover over:
        - Armies (priority 1) - within army circle radius
        - Territories (priority 2) - if not over army
        - Map buttons (building/training icons)
        
        Instant Highlights (no delay):
        - Sets self.hovered_army / self.hovered_territory
        - Visual feedback appears immediately
        - Suppressed when hovering map buttons
        
        Delayed Tooltips (500ms delay):
        - Starts/resets hover timer
        - Tooltips appear after hover_delay
        - Disabled when plot selected or hovering buttons
        
        Args:
            pos: (x, y) tuple of mouse position in screen coordinates
        
        Side Effects:
            - Updates self.mouse_pos (for tooltip positioning)
            - Updates self.hovered_army / self.hovered_territory (instant)
            - Updates self.hover_target_army / self.hover_target_territory (delayed)
            - Updates self.hover_start_time (tooltip timer)
            - Clears self.show_tooltip_* flags (reset for new target)
        
        Phase Context:
            Part of Phase 2C to separate hover system from run() method.
            Updated in Phase 2D to work with camera offset and zoom.
        """
        # Block hover detection when menus are open
        if self.game_menu_visible or self.options_menu_visible:
            # Clear hover states
            self.hovered_territory = None
            self.hovered_army = None
            self.hovered_plot = None
            self.hover_target_territory = None
            self.hover_target_army = None
            self.hover_start_time = None
            return
        
        # Store SCREEN position for tooltip rendering (tooltips render in screen space)
        self.mouse_pos = pos
        
        # Convert screen position to world position for hover detection
        # This makes hover work correctly with camera offset and zoom!
        world_pos = self.screen_to_world(pos)
        
        # Only track territory/army hover when in map area (not top panel, bottom UI, or sidebar).
        # The sidebar check covers the panel body, bookmark tabs and collapse button,
        # and follows collapse/expand (live layout).
        in_sidebar = self.is_point_over_sidebar(pos)
        # The unit context menu can overlap the map when it flips upward - nothing
        # beneath it may highlight while it is open.
        ctx_menu_rect = self._get_unit_context_menu_rect()
        in_context_menu = bool(ctx_menu_rect and ctx_menu_rect.collidepoint(pos))
        # Battle Report popups float over the map, so territories beneath one must not
        # highlight or show tooltips while the cursor is on it.
        in_battle_report = bool(self._battle_report_rect_at(pos))
        # The map ends at BOTTOM_UI_Y (= TOP_PANEL_HEIGHT + MAP_HEIGHT). Comparing with
        # MAP_HEIGHT (a height, not a y) left the lowest TOP_PANEL_HEIGHT px of the map
        # with no hover highlight at all.
        in_map_area = (TOP_PANEL_HEIGHT <= pos[1] < BOTTOM_UI_Y
                       and not in_sidebar and not in_context_menu
                       and not in_battle_report)
        if in_map_area:
            # Check if hovering over an army first (takes priority over territory)
            # NOTE: scaled_centers are in WORLD coordinates, so compare with world_pos!
            # Two-pass, mirroring get_army_at_pos(): a visible circle always beats a
            # banner from a neighbouring territory that happens to overlap it.
            # Unlike clicking, hover considers EVERY garrison regardless of owner,
            # so allied/enemy stacks highlight too (existing behaviour, preserved).
            # PERFORMANCE: index inbound animations once instead of rescanning the
            # animation list per territory (was O(T*A)).
            incoming_by_territory = {}
            for anim in self.game_state.active_animations:
                if anim.to_territory not in incoming_by_territory:
                    incoming_by_territory[anim.to_territory] = set()
                incoming_by_territory[anim.to_territory].add(anim.player)

            army_circle_hit = None
            army_banner_hit = None
            for territory, (cx, cy) in self.scaled_centers.items():
                if self.game_state.get_territory_total_armies(territory) <= 0:
                    continue

                garrisons = self.game_state.territory_garrisons.get(territory, {})
                num_garrisons = self.get_effective_garrison_count(
                    territory, garrisons, incoming_by_territory.get(territory, set())
                )

                # Multi-garrison (allied reinforcement): every garrison gets its own
                # circle + banner, so test them all.
                for player_index in sorted(garrisons.keys()):
                    anchor = self.get_garrison_anchor(territory, cx, cy, player_index,
                                                      num_garrisons)
                    if anchor is None:
                        continue
                    anchor_x, anchor_y, army_count = anchor

                    if self.point_in_army_circle(world_pos[0], world_pos[1],
                                                 anchor_x, anchor_y):
                        army_circle_hit = territory
                        break

                    if self.point_in_army_banner(world_pos[0], world_pos[1],
                                                 anchor_x, anchor_y,
                                                 player_index, army_count):
                        # Keep the LAST match: later = drawn on top = topmost banner
                        army_banner_hit = territory

                if army_circle_hit:
                    break

            # Check if hovering over a plot (takes priority over territory for tooltips)
            # HOISTED above the army resolution so hover mirrors the click priority
            # exactly: circle > plot > banner. get_plot_at_pos only scans the current
            # player's territories while playing, so this is cheap and side-effect free.
            plot_at_pos = self.get_plot_at_pos(world_pos)

            # Resolve which army (if any) the cursor is on, using the click precedence
            if army_circle_hit:
                army_at_pos = army_circle_hit   # a visible circle beats a plot
            elif plot_at_pos:
                army_at_pos = None              # a plot beats a banner
            else:
                army_at_pos = army_banner_hit

            # Get territory at current position (if not over army)
            # get_territory_at_pos also needs to work with camera - we'll update it separately
            territory_at_pos = None
            if not army_at_pos:
                territory_at_pos = self.get_territory_at_pos(world_pos)
                # Tutorial hook: filter out non-interactive territories
                if (territory_at_pos and self.tutorial_mission
                        and self.tutorial_mission.active
                        and not self.tutorial_mission.is_territory_interactive(territory_at_pos)):
                    territory_at_pos = None

            # Check if hovering over map button (building or training icon)
            hovering_map_button = (self.hover_target_button and
                                  self.hover_target_button[0] in ['map_building', 'map_training'])
            # Check if hovering over "Resolve Remaining Battles" button (below top panel)
            hovering_resolve_btn = (getattr(self, 'resolve_all_battles_button', None) and
                                   self.resolve_all_battles_button.collidepoint(self.mouse_pos))
            # "Close All Battle Reports" shares that slot during the planning phase, so
            # it needs the same suppression or the territory under it would glow.
            if (getattr(self, 'close_all_battle_reports_button', None)
                    and self.close_all_battle_reports_button.collidepoint(self.mouse_pos)):
                hovering_resolve_btn = True

            # INSTANT HIGHLIGHTS (no delay)
            # Suppress territory glow when hovering over map buttons OR plots OR alliance popup is open
            alliance_popup_open = getattr(self, 'alliance_choice_popup_visible', False)
            if not hovering_map_button and not hovering_resolve_btn and not alliance_popup_open:
                # Army-vs-plot precedence is already resolved above (circle > plot >
                # banner), so do NOT re-suppress the army highlight on plot_at_pos here.
                # That used to kill the highlight even where a click WOULD select the army.
                self.hovered_army = army_at_pos
                if not self.hovered_army and not plot_at_pos:
                    self.hovered_territory = territory_at_pos
                else:
                    self.hovered_territory = None
            else:
                # Clear hover when over map buttons or plots or alliance popup is open
                self.hovered_army = None
                self.hovered_territory = None

            # DELAYED TOOLTIPS - Start/reset timer
            # Territory and army tooltips suppressed when:
            # 1. Currently hovering over a map building/training icon
            # 2. Currently hovering over a plot itself
            # 3. Alliance choice popup is open
            # 4. Hovering over "Resolve Remaining Battles" button
            # Both territory and army tooltips show regardless of which building
            # UI is open (barracks, keep, plot selection, etc.)
            should_track_territory = (not hovering_map_button and
                                     not hovering_resolve_btn and
                                     not plot_at_pos and
                                     not alliance_popup_open)
            should_track_army = (not hovering_map_button and
                                not hovering_resolve_btn and
                                not alliance_popup_open)

            # Check if we're hovering over something new (army or territory tracked independently)
            army_changed = (army_at_pos != self.hover_target_army)
            territory_changed = (territory_at_pos != self.hover_target_territory)

            if should_track_army and army_changed:
                # Army hover target changed - reset timer and update army tracking
                self.hover_start_time = pygame.time.get_ticks()
                self.hover_target_army = army_at_pos
                self.show_tooltip_army = None
                # Also update territory tracking if allowed
                if should_track_territory:
                    self.hover_target_territory = territory_at_pos
                    self.show_tooltip_territory = None
            elif should_track_territory and territory_changed:
                # Territory hover target changed - reset timer and update
                self.hover_start_time = pygame.time.get_ticks()
                self.hover_target_territory = territory_at_pos
                self.show_tooltip_territory = None
                # Also update army tracking (always allowed here since territory tracking is more restrictive)
                self.hover_target_army = army_at_pos
                self.show_tooltip_army = None

            # Clear suppressed tracking targets
            if not should_track_territory:
                if self.hover_target_territory:
                    self.hover_target_territory = None
                    self.show_tooltip_territory = None
            if not should_track_army:
                if self.hover_target_army:
                    self.hover_target_army = None
                    self.show_tooltip_army = None
        else:
            # Mouse outside map area (top panel, bottom UI, sidebar, tab buttons, or
            # over the unit context menu) - clear hover states
            self.hovered_army = None
            self.hovered_territory = None
            self.hover_target_army = None
            self.hover_target_territory = None
            self.show_tooltip_army = None
            self.show_tooltip_territory = None
            # Don't reset hover_start_time here - button hover tracking will manage it
    
    def update_frame_tooltips(self):
        """
        Update button hover tracking, check tooltip timers, and render tooltips (Phase 2C extraction).
        
        This method MUST be called after all drawing is complete each frame, in this order:
        1. Track button hover (after draw_bottom_ui draws buttons)
        2. Check tooltip timers (for both map and button tooltips)
        3. Render tooltips (on top of everything)
        
        Frame Order Dependencies:
        - MUST be called after draw_bottom_ui() (needs button rects)
        - MUST be called after draw_battle_popup() (tooltips on top)
        - MUST be called after draw_victory_screen() (tooltips on top)
        - MUST be called before pygame.display.flip() (render to screen)
        
        Button Hover Tracking:
        - Only tracks when plot is selected (building buttons shown)
        - Uses update_button_hover() helper from Phase 1D
        - Clears hover when plot deselected
        
        Tooltip Timers:
        - Map tooltip timer: Shows army/territory tooltips after delay
        - Button tooltip timer: Shows button tooltips after delay
        - Both use same hover_delay (500ms)
        
        Tooltip Rendering Priority:
        - Map area: button tooltip > army tooltip > territory tooltip
        - Bottom UI area: button tooltip only
        
        Side Effects:
            - Updates self.hover_target_button (button hover)
            - Updates self.show_tooltip_* flags (timer-activated tooltips)
            - Renders tooltips to screen
        
        Phase Context:
            Part of Phase 2C to separate tooltip system from run() method.
            Prepares for camera movement (tooltips need camera-adjusted positions).
        
        Future Features:
            Camera movement will need to adjust tooltip positions.
            Minimap will add its own tooltip rendering here.
        """
        # Block all tooltip processing when menus are open
        if self.game_menu_visible or self.options_menu_visible:
            # Clear any active tooltips
            self.hover_start_time = None
            self.hover_start_time_button = None
            self.show_tooltip_territory = None
            self.show_tooltip_army = None
            self.show_tooltip_button = None
            return
        
        # Track building button hover (must happen after draw_bottom_ui every frame)
        # This ensures hover state is always properly managed
        if self.selected_plot:
            mouse_pos = pygame.mouse.get_pos()
            current_hover = None
            # Only track if we're showing building buttons (plot is empty)
            if self.building_buttons:
                for building_name, button_rect in self.building_buttons.items():
                    if button_rect.collidepoint(mouse_pos):
                        current_hover = ('building', building_name)
                        break
            
            # Update hover tracking using helper (Phase 1D)
            self.update_button_hover(current_hover, 'building')
        else:
            # No plot selected - clear building button hover if that's what was set
            if self.hover_target_button and self.hover_target_button[0] == 'building':
                self.hover_target_button = None
                self.show_tooltip_button = None
                self.hover_start_time_button = None

        # Track territorial bonuses button hover (top panel)
        if self.bonuses_button_rect:
            if self.bonuses_button_rect.collidepoint(self.mouse_pos):
                self.update_button_hover(('territorial_bonuses', None), 'territorial_bonuses')
            else:
                # Clear bonuses button hover if moving away
                if self.hover_target_button and self.hover_target_button[0] == 'territorial_bonuses':
                    self.update_button_hover(None, 'territorial_bonuses')
        else:
            # Clear bonuses button hover if button doesn't exist
            if self.hover_target_button and self.hover_target_button[0] == 'territorial_bonuses':
                self.hover_target_button = None
                self.show_tooltip_button = None
                self.hover_start_time_button = None

        # Track "Resolve Remaining Battles" button hover (below top panel)
        if getattr(self, 'resolve_all_battles_button', None):
            if self.resolve_all_battles_button.collidepoint(self.mouse_pos):
                self.update_button_hover(('resolve_all_battles', None), 'resolve_all_battles')
            else:
                # Clear resolve button hover if moving away
                if self.hover_target_button and self.hover_target_button[0] == 'resolve_all_battles':
                    self.update_button_hover(None, 'resolve_all_battles')
        else:
            # Clear resolve button hover if button doesn't exist
            if self.hover_target_button and self.hover_target_button[0] == 'resolve_all_battles':
                self.hover_target_button = None
                self.show_tooltip_button = None
                self.hover_start_time_button = None

        # Check tooltip timer every frame (automatic tooltip appearance)
        # THIS MUST HAPPEN AFTER ALL DRAWING where hover is tracked

        # Check MAP tooltip timer (army/territory)
        if self.hover_start_time is not None:
            current_time = pygame.time.get_ticks()
            elapsed = current_time - self.hover_start_time
            if elapsed >= self.hover_delay:
                # Time has elapsed - show map tooltips
                self.show_tooltip_army = self.hover_target_army
                self.show_tooltip_territory = self.hover_target_territory
        
        # Check BUTTON tooltip timer (separate, independent)
        if self.hover_start_time_button is not None:
            current_time = pygame.time.get_ticks()
            elapsed = current_time - self.hover_start_time_button
            if elapsed >= self.hover_delay:
                # Time has elapsed - show button tooltip
                self.show_tooltip_button = self.hover_target_button
        
        # Draw hover tooltips (on top of everything else)
        # Check if in map area and NOT over the sidebar (live layout: follows collapse).
        # BOTTOM_UI_Y, not MAP_HEIGHT: the latter is a height, and cut tooltips off
        # for the lowest TOP_PANEL_HEIGHT px of the map.
        in_map_area = (TOP_PANEL_HEIGHT <= self.mouse_pos[1] < BOTTOM_UI_Y
                       and not self.is_point_over_sidebar(self.mouse_pos))
        in_top_panel = self.mouse_pos[1] < TOP_PANEL_HEIGHT
        # Bottom-UI button tooltips keep their original rightmost-250 px cut-off. This
        # is a bottom-panel rule (it stops unit tooltips lingering at the panel's right
        # end), independent of whether the sidebar above is collapsed.
        in_bottom_ui = (self.mouse_pos[1] >= BOTTOM_UI_Y
                        and self.mouse_pos[0] < WINDOW_WIDTH - UIConstants.SIDEBAR_WIDTH)

        # Check top panel FIRST (has priority over map area)
        if in_top_panel and self.show_tooltip_button:
            # Show button tooltip for top panel buttons (territorial bonuses, etc.)
            self.draw_button_tooltip(self.mouse_pos, self.show_tooltip_button)
        elif in_map_area:  # Only show tooltip when hovering map area (not sidebar, not top panel)
            # Show button tooltip for map building/training/hero icons or resolve-all-battles button first
            if self.show_tooltip_button and self.show_tooltip_button[0] in ['map_building', 'map_training', 'map_hero_training', 'resolve_all_battles']:
                self.draw_button_tooltip(self.mouse_pos, self.show_tooltip_button)
            # Show army tooltip if hovering over an army, otherwise show territory tooltip
            # Use show_tooltip_* variables which have the delay applied
            elif self.show_tooltip_army:
                self.draw_army_hover_tooltip(self.mouse_pos, self.show_tooltip_army)
            elif self.show_tooltip_territory:
                self.draw_territory_hover_tooltip(self.mouse_pos)
        elif in_bottom_ui and self.show_tooltip_button:
            # Show button tooltip (only in bottom UI area - prevents tooltips from persisting over sidebar)
            # Purpose: Fix bug where army unit tooltips would persist when hovering over sidebar panels
            if self.show_tooltip_button[0] == 'hero_ability':
                # Hero ability tooltip - special handling
                hero_name, ability_index = self.show_tooltip_button[1]
                self.draw_ability_tooltip(self.mouse_pos, hero_name, ability_index)
            else:
                # Regular button tooltip (buildings, training, army units, etc.)
                self.draw_button_tooltip(self.mouse_pos, self.show_tooltip_button)
        elif (self.show_tooltip_button and self.show_tooltip_button[0] == 'sidebar_hero_ability'
              and self.is_point_over_sidebar_panel(self.mouse_pos)):
            # Ability icon on a sidebar hero card: the LOCAL player's cooldowns
            hero_name, ability_index = self.show_tooltip_button[1]
            self.draw_ability_tooltip(self.mouse_pos, hero_name, ability_index, player=self.get_local_player())
        elif self.show_tooltip_button and self.show_tooltip_button[0] == 'territory_lore':
            # Territory preview tooltip — drawn even past sidebar_x since the preview
            # image extends into that region of the bottom panel
            if self.mouse_pos[1] >= BOTTOM_UI_Y:
                self.draw_button_tooltip(self.mouse_pos, self.show_tooltip_button)

        # Sidebar hover label (e.g. "6× Swordsmen" over an order card's unit chip),
        # set by the sidebar renderer this frame and drawn on top of everything
        self._draw_sidebar_tooltip()

    def _draw_sidebar_tooltip(self):
        """Draw the short sidebar hover label set this frame, left of the cursor
        (the panel sits at the screen's right edge), kept on screen."""
        tooltip = getattr(self, 'sidebar_tooltip', None)
        if not tooltip:
            return
        text, (mx, my) = tooltip
        surf = self.sidebar_widgets.tooltip(text)
        x = max(4, min(mx - surf.get_width() - 10, WINDOW_WIDTH - surf.get_width() - 4))
        y = max(4, min(my - surf.get_height() - 6, WINDOW_HEIGHT - surf.get_height() - 4))
        self.screen.blit(surf, (x, y))
    
    # ========================================
    # PHASE 2D: CAMERA MOVEMENT METHODS
    # ========================================
    
    def handle_camera_drag(self, pos, buttons):
        """
        Handle camera dragging with middle mouse button.
        
        Wrapper that delegates to camera handler.
        """
        # Sync state to camera handler
        self.camera.offset = self.camera_offset
        self.camera.zoom = self.camera_zoom
        self.camera.drag_start = self.camera_drag_start
        
        # Delegate to camera handler
        self.camera.handle_drag(pos, buttons, BOTTOM_UI_Y)
        
        # Sync state back
        self.camera_offset = self.camera.offset
        self.camera_zoom = self.camera.zoom
        self.camera_drag_start = self.camera.drag_start
    
    def handle_edge_scrolling(self, pos, delta_time=0.0):
        """
        Handle edge scrolling when mouse is near map area edges.
        
        Wrapper that delegates to camera handler.
        
        delta_time (seconds) feeds the Map Edge dwell timer, which holds the
        scroll back until the cursor has stayed in an edge band long enough —
        see MAP_EDGE_SCROLL_DELAY in input/camera_handler.py.
        """
        # Sync state to camera handler
        self.camera.offset = self.camera_offset
        self.camera.zoom = self.camera_zoom
        
        # Delegate to camera handler
        self.camera.handle_edge_scrolling(
            pos, 
            self.edge_scrolling_enabled, 
            self.edge_scrolling_mode, 
            self.camera_pan_speed,
            TOP_PANEL_HEIGHT,
            BOTTOM_UI_Y,
            delta_time
        )
        
        # Sync state back
        self.camera_offset = self.camera.offset
        self.camera_zoom = self.camera.zoom
        self.debug_edge_scroll = self.camera.debug_edge_scroll
    
    def handle_keyboard_camera(self, keys):
        """
        Handle keyboard camera panning (arrow keys).
        
        Wrapper that delegates to camera handler.
        """
        # Sync state to camera handler
        self.camera.offset = self.camera_offset
        self.camera.zoom = self.camera_zoom
        
        # Delegate to camera handler
        self.camera.handle_keyboard(keys, self.camera_pan_speed)
        
        # Sync state back
        self.camera_offset = self.camera.offset
        self.camera_zoom = self.camera.zoom
        self.debug_keyboard_scroll = self.camera.debug_keyboard_scroll
    
    def handle_camera_zoom(self, delta):
        """
        Handle camera zoom with mouse wheel (Phase 2D).
        
        Zooms camera in or out, centered on the current mouse position.
        This creates a "zoom to cursor" effect like in professional RTS games,
        where the point under the cursor stays in the same place after zoom.
        
        Zoom Mechanics:
        - Scroll up (delta > 0): Zoom in (multiply by 1.1)
        - Scroll down (delta < 0): Zoom out (multiply by 0.9)
        - Clamped to min/max zoom levels (0.5x to 2.0x)
        
        Zoom to Cursor Algorithm:
        1. Get world position under cursor BEFORE zoom
        2. Apply new zoom level
        3. Get world position under cursor AFTER zoom
        4. Adjust camera offset to compensate for difference
        5. Result: Point under cursor stays fixed!
        
        This makes zoom feel intuitive and professional.
        
        Args:
            delta: Mouse wheel delta (positive = scroll up/zoom in, negative = scroll down/zoom out)
        
        Side Effects:
            - Updates self.camera_zoom (new zoom level)
            - Updates self.camera_offset (to keep cursor point fixed)
            - Calls clamp_camera_to_bounds() to enforce map limits
        
        Example:
            Cursor at screen (400, 300)
            World pos before: (300, 200)
            Zoom: 1.5 â†’ 1.65 (zoom in)
            World pos after would be: (342, 231) without offset adjustment
            Offset adjusted to keep world pos at (300, 200)
            Result: Territory under cursor doesn't move!
        
        Phase Context:
            Part of Phase 2D camera system.
            Makes camera fully controllable (pan + zoom).
        """
        # Sidebar first: over the panel the wheel scrolls the tab (or does nothing),
        # never the map underneath
        if self.handle_sidebar_wheel(delta):
            return

        # Sync state to camera handler before zoom
        self.camera.offset = self.camera_offset
        self.camera.zoom = self.camera_zoom
        
        # Delegate to camera handler
        mouse_pos = pygame.mouse.get_pos()
        zoom_applied = self.camera.handle_zoom(delta, mouse_pos, self.camera_zoom_speed, TOP_PANEL_HEIGHT)
        
        # Sync state back from camera handler
        self.camera_offset = self.camera.offset
        self.camera_zoom = self.camera.zoom
    
    def save_settings(self):
        """
        Save current game settings to config.json via global settings manager.

        Saves all user-configurable settings:
        - Display settings (resolution, fullscreen)
        - Gameplay settings (edge scrolling, tooltips, camera speeds, etc.)

        Settings are saved in JSON format for easy editing and portability.
        Creates config.json in the same directory as the game.

        Returns:
            bool: True if save successful, False if error occurred
        """
        from settings_manager import settings

        # Update global settings from current game state
        settings.update_from_game(self)

        return True  # settings.save() is called in update_from_game()
    
    def load_settings(self):
        """
        Load game settings from config.json.
        
        Attempts to load saved settings from config.json.
        If file doesn't exist or is corrupted, uses default values.
        
        This is called during __init__ after default values are set,
        so defaults are always available as fallback.
        
        Validates all loaded values to ensure they're within acceptable ranges.
        
        Returns:
            bool: True if settings loaded successfully, False if using defaults
        """
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
            
            # Load display settings
            if "display" in config:
                display = config["display"]
                
                # Resolution (validate it's in available list)
                if "resolution" in display:
                    resolution = tuple(display["resolution"])  # Convert list back to tuple
                    if resolution in self.available_resolutions:
                        self.current_resolution = resolution
                        self.temp_resolution = resolution
                
                # Fullscreen
                if "fullscreen" in display:
                    self.is_fullscreen = bool(display["fullscreen"])
                    self.temp_fullscreen = self.is_fullscreen
                    self.temp_vsync = self.vsync
                    self.temp_fps_limit = self.fps_limit
            
            # Load gameplay settings
            if "gameplay" in config:
                gameplay = config["gameplay"]
                
                # Edge scrolling enabled
                if "edge_scrolling_enabled" in gameplay:
                    self.edge_scrolling_enabled = bool(gameplay["edge_scrolling_enabled"])
                    self.temp_edge_scrolling_enabled = self.edge_scrolling_enabled
                
                # Edge scrolling mode
                if "edge_scrolling_mode" in gameplay:
                    mode = gameplay["edge_scrolling_mode"]
                    if mode in ["map_edge", "window_edge"]:
                        self.edge_scrolling_mode = mode
                        self.temp_edge_scrolling_mode = mode
                
                # Tooltips enabled
                if "tooltips_enabled" in gameplay:
                    self.tooltips_enabled = bool(gameplay["tooltips_enabled"])
                    self.temp_tooltips_enabled = self.tooltips_enabled
                
                # Tooltip delay
                if "tooltip_delay_ms" in gameplay:
                    delay = int(gameplay["tooltip_delay_ms"])
                    # Validate: must be one of the allowed values
                    if delay in [300, 500, 700, 1000, -1]:
                        self.tooltip_delay_ms = delay
                        self.temp_tooltip_delay_ms = delay
                        self.hover_delay = delay  # Update hover delay
                
                # Camera pan speed
                if "camera_pan_speed" in gameplay:
                    speed = float(gameplay["camera_pan_speed"])
                    # Validate: 5-20 range
                    if 5.0 <= speed <= 20.0:
                        self.camera_pan_speed = speed
                        self.temp_camera_pan_speed = speed
                
                # Camera zoom speed
                if "camera_zoom_speed" in gameplay:
                    speed = float(gameplay["camera_zoom_speed"])
                    # Validate: 0.05-0.30 range
                    if 0.05 <= speed <= 0.30:
                        self.camera_zoom_speed = speed
                        self.temp_camera_zoom_speed = speed
                
                # Show FPS
                if "show_fps" in gameplay:
                    self.show_fps = bool(gameplay["show_fps"])
                    self.temp_show_fps = self.show_fps
            
            logger.info("[OK] Settings loaded from config.json")
            return True
            
        except FileNotFoundError:
            logger.info("[INFO]  No config.json found, using default settings")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"WARNING:  Corrupted config.json, using default settings: {e}")
            return False
        except Exception as e:
            logger.warning(f"WARNING:  Error loading settings, using defaults: {e}")
            return False
    
    def reset_settings_to_defaults(self):
        """
        Reset all settings to their default values.

        Resets both current and temp settings to default resolution and default settings.
        Does NOT save to config.json (user must click Apply to save).

        This is called when user clicks "Reset to Defaults" button.

        Default values:
        - Display: Default resolution (chosen from 1280x720, 1600x900, 1920x1080), fullscreen on
        - Edge Scrolling: Enabled, map edge mode
        - Tooltips: Enabled, 500ms delay
        - Camera: 10.0 pan speed, 0.15 zoom speed
        - FPS Counter: Off
        """
        # Display settings - use default resolution from settings (not native)
        # This ensures we use a supported resolution even if native is scaled
        self.temp_resolution = self.default_resolution
        self.temp_fullscreen = True
        self.temp_vsync = False   # opt-in, matches settings defaults
        self.temp_fps_limit = 0   # no manual cap

        # Gameplay settings
        self.temp_edge_scrolling_enabled = True
        self.temp_edge_scrolling_mode = "window_edge"
        self.temp_tooltips_enabled = True
        self.temp_tooltip_delay_ms = 500
        self.temp_camera_pan_speed = 10.0
        self.temp_camera_zoom_speed = 0.15
        self.temp_show_fps = False

        # Audio settings — defaults match settings_manager
        self.temp_master_volume = 0.8
        self.temp_music_volume = 0.5
        self.temp_sfx_volume = 0.5
        # Live preview the reset
        music_manager.set_master_volume(0.8)
        music_manager.set_music_volume(0.5)
        sound_manager.set_volume(0.5 * 0.8)

        logger.info(f"🔄 Settings reset to defaults: {self.default_resolution[0]}x{self.default_resolution[1]} (click Apply to save)")

    def update_master_negotiator_particles(self, delta_time):
        """
        Update Master Negotiator particle system - green particles around screen edges.

        Args:
            delta_time: Time elapsed since last update (seconds)
        """
        # Only update if Master Negotiator is active
        if self.game_state.master_negotiator_activation_time is None:
            # Clear particles if effect is not active
            self.master_negotiator_particles.clear()
            return

        # Particle configuration
        PARTICLES_PER_SECOND = 120
        MIN_PARTICLE_LIFETIME = 1.0
        MAX_PARTICLE_LIFETIME = 2.0
        PARTICLE_SIZE = 3
        EDGE_WIDTH = 100  # How far from edge to spawn particles

        # Green shades for Master Negotiator
        GREEN_SHADES = [
            (0, 150, 0),      # Dark green
            (50, 200, 50),    # Medium green
            (100, 255, 100),  # Bright green
            (150, 255, 150),  # Light green
            (200, 255, 200)   # Very light green
        ]

        # Spawn new particles
        self.master_negotiator_particle_spawn_accumulator += delta_time
        particles_to_spawn = int(self.master_negotiator_particle_spawn_accumulator * PARTICLES_PER_SECOND)
        self.master_negotiator_particle_spawn_accumulator -= particles_to_spawn / PARTICLES_PER_SECOND

        for _ in range(particles_to_spawn):
            # Randomly choose an edge: 0=top, 1=right, 2=bottom, 3=left
            edge = random.randint(0, 3)

            if edge == 0:  # Top edge
                x = random.uniform(0, WINDOW_WIDTH)
                y = random.uniform(0, EDGE_WIDTH)
            elif edge == 1:  # Right edge
                x = random.uniform(WINDOW_WIDTH - EDGE_WIDTH, WINDOW_WIDTH)
                y = random.uniform(0, WINDOW_HEIGHT)
            elif edge == 2:  # Bottom edge
                x = random.uniform(0, WINDOW_WIDTH)
                y = random.uniform(WINDOW_HEIGHT - EDGE_WIDTH, WINDOW_HEIGHT)
            else:  # Left edge
                x = random.uniform(0, EDGE_WIDTH)
                y = random.uniform(0, WINDOW_HEIGHT)

            particle = {
                'x': x,
                'y': y,
                'color': random.choice(GREEN_SHADES),
                'size': PARTICLE_SIZE,
                'lifetime': random.uniform(MIN_PARTICLE_LIFETIME, MAX_PARTICLE_LIFETIME),
                'age': 0.0,
                'max_opacity': random.uniform(0.5, 0.9),
                'vy': random.uniform(-15, -30)  # Slow upward drift
            }
            self.master_negotiator_particles.append(particle)

        # Update existing particles
        for particle in self.master_negotiator_particles:
            particle['age'] += delta_time
            particle['y'] += particle['vy'] * delta_time  # Drift upward

        # P9 fix: O(n) list comprehension instead of O(n*k) list.remove() loop
        self.master_negotiator_particles = [
            p for p in self.master_negotiator_particles
            if p['age'] < p['lifetime']
        ]

    def render_master_negotiator_particles(self):
        """
        Render green particles around screen edges for Master Negotiator effect.
        """
        # Update particles first (this spawns new particles if ability is active)
        delta_time = self.clock.get_time() / 1000.0  # Convert ms to seconds
        self.update_master_negotiator_particles(delta_time)

        # Early return if no particles to render
        if not self.master_negotiator_particles:
            return

        # PERFORMANCE: Reuse cached surface instead of allocating full-screen SRCALPHA every frame
        if self._cached_negotiator_surface is None or self._cached_negotiator_surface.get_size() != (WINDOW_WIDTH, WINDOW_HEIGHT):
            self._cached_negotiator_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        self._cached_negotiator_surface.fill((0, 0, 0, 0))  # Clear with transparent
        temp_surface = self._cached_negotiator_surface

        # Draw all particles
        for particle in self.master_negotiator_particles:
            # Calculate opacity based on age
            progress = particle['age'] / particle['lifetime']

            if progress < 0.3:
                # Fade in
                opacity = (progress / 0.3) * particle['max_opacity']
            elif progress < 0.7:
                # Hold
                opacity = particle['max_opacity']
            else:
                # Fade out
                fade_progress = (progress - 0.7) / 0.3
                opacity = (1.0 - fade_progress) * particle['max_opacity']

            # Apply opacity to particle color
            r, g, b = particle['color']
            alpha = int(255 * opacity)
            color_with_alpha = (r, g, b, alpha)

            # Draw particle as a circle
            x = int(particle['x'])
            y = int(particle['y'])
            pygame.draw.circle(temp_surface, color_with_alpha, (x, y), particle['size'])

        # Blit the particle surface onto the main screen
        self.screen.blit(temp_surface, (0, 0))

    # AI Player Management Methods
    def render_spectator_banner(self):
        """
        Render a banner at the top of screen showing spectator mode.
        Displays which player's turn it is and that local player is spectating.
        """
        if not self.multiplayer_mode or self.is_local_player_active():
            return  # Don't show if not spectating

        # Banner dimensions
        banner_height = 50
        banner_width = 500
        banner_x = (WINDOW_WIDTH - banner_width) // 2
        banner_y = TOP_PANEL_HEIGHT + 20  # Just below top panel

        # PERFORMANCE: Cache banner background surface (static shape)
        if self._cached_spectator_banner is None or self._cached_spectator_banner.get_size() != (banner_width, banner_height):
            self._cached_spectator_banner = pygame.Surface((banner_width, banner_height), pygame.SRCALPHA)
            pygame.draw.rect(self._cached_spectator_banner, (0, 0, 0, 180),
                           self._cached_spectator_banner.get_rect(), border_radius=10)
        self.screen.blit(self._cached_spectator_banner, (banner_x, banner_y))

        # Border
        pygame.draw.rect(self.screen, (200, 200, 200),
                        (banner_x, banner_y, banner_width, banner_height),
                        2, border_radius=10)

        # PERFORMANCE: Cache text surface — only re-render when player changes
        current_player_num = self.game_state.current_player + 1
        banner_text = f"Player {current_player_num}'s Turn - Spectating..."
        if self._cached_spectator_text is None or self._cached_spectator_text[0] != banner_text:
            text_surface = self._get_cached_text(banner_text, self.large_font, (255, 255, 100))
            self._cached_spectator_text = (banner_text, text_surface)
        text_surface = self._cached_spectator_text[1]
        text_rect = text_surface.get_rect(center=(banner_x + banner_width // 2, banner_y + banner_height // 2))
        self.screen.blit(text_surface, text_rect)

    def render_ai_thinking_indicator(self):
        """Render visual indicator when AI is thinking (above bottom UI panel)"""
        # Position indicator just above the bottom UI panel
        indicator_height = 80
        indicator_y = BOTTOM_UI_Y - indicator_height

        # PERFORMANCE: Cache the overlay surface instead of creating every frame
        if self._ai_indicator_overlay is None:
            self._ai_indicator_overlay = pygame.Surface((WINDOW_WIDTH, indicator_height), pygame.SRCALPHA)
            self._ai_indicator_overlay.fill((0, 0, 0, 120))
        self.screen.blit(self._ai_indicator_overlay, (0, indicator_y))

        # PERFORMANCE: Cache fonts instead of creating every frame
        # Phase 7: AI indicator uses Cinzel Bold 38px for title, SemiBold 26px for subtitle (20% smaller)
        if self._ai_indicator_title_font is None:
            self._ai_indicator_title_font = self.font_manager.get_bold_font(38)
            self._ai_indicator_subtitle_font = self.font_manager.get_font(26)

        # Campaign mission hook: allow mission to override AI thinking text
        mission = getattr(self, 'tutorial_mission', None)
        if mission and hasattr(mission, 'get_ai_thinking_text') and mission.active:
            title_str, subtitle_str = mission.get_ai_thinking_text()
        else:
            # Default: show individual player name and difficulty
            player_name = self.game_state.get_player_name(self.game_state.current_player)
            difficulty_names = ['Easy', 'Medium', 'Hard']
            difficulty = difficulty_names[self.game_state.player_ai_difficulty[self.game_state.current_player]]
            title_str = f"{player_name} Thinking..."
            subtitle_str = f"({difficulty} Difficulty)"

        # Use cached text rendering for the indicator text
        title_text = self._get_cached_text(title_str, self._ai_indicator_title_font, (255, 255, 100))
        subtitle_text = self._get_cached_text(subtitle_str, self._ai_indicator_subtitle_font, (200, 200, 200))

        # Position text in the center of the indicator bar (above bottom UI)
        title_rect = title_text.get_rect(center=(WINDOW_WIDTH // 2, indicator_y + indicator_height // 2 - 15))
        subtitle_rect = subtitle_text.get_rect(center=(WINDOW_WIDTH // 2, indicator_y + indicator_height // 2 + 15))

        self.screen.blit(title_text, title_rect)
        self.screen.blit(subtitle_text, subtitle_rect)

    def draw_empty_bottom_ui_panel(self):
        """Draw empty bottom UI panel during AI turns (background only, no interactive content)"""
        # Draw bottom UI background
        bottom_rect = pygame.Rect(0, BOTTOM_UI_Y, WINDOW_WIDTH, BOTTOM_UI_HEIGHT)

        if self.bottom_panel_image:
            self.screen.blit(self.bottom_panel_image, (0, BOTTOM_UI_Y))
        else:
            pygame.draw.rect(self.screen, (220, 220, 220), bottom_rect)

        # Draw top border line
        pygame.draw.line(self.screen, (100, 100, 100), (0, BOTTOM_UI_Y), (WINDOW_WIDTH, BOTTOM_UI_Y), 2)

    def initialize_ai_players(self):
        """
        Create AIPlayer instances for all AI-controlled players.

        This method lazy-initializes AI players the first time they're needed.
        Each AI player is created with their assigned difficulty level.
        """
        from ai_player import AIPlayer
        self.ai_players = {}
        for i in range(self.game_state.num_players):
            if self.game_state.player_is_ai[i]:
                difficulty = self.game_state.player_ai_difficulty[i]
                self.ai_players[i] = AIPlayer(i, difficulty)
                difficulty_name = ['Easy', 'Medium', 'Hard'][difficulty]
                logger.info(f"[AI] Initialized AI Player {i+1} ({difficulty_name})")

    def handle_ai_turn(self):
        """
        Execute the AI player's turn.

        This method is called each frame when it's an AI player's turn and they're
        in the planning phase. The AIPlayer instance handles all decision-making
        and action execution asynchronously.

        The AI system will:
        1. Analyze the current game state
        2. Make strategic decisions (buildings, attacks, tech, heroes)
        3. Execute actions with timing delays
        4. End the turn automatically
        """
        # Initialize AI players if not already done
        if not self.ai_players:
            self.initialize_ai_players()

        current_player = self.game_state.current_player

        # Check if AI player exists and hasn't already started their turn
        if current_player in self.ai_players:
            ai_player = self.ai_players[current_player]

            # Only execute if AI hasn't started yet (prevent multiple calls per turn)
            if not hasattr(ai_player, 'turn_in_progress') or not ai_player.turn_in_progress:
                ai_player.execute_turn(self.game_state)

    def handle_ai_setup(self):
        """
        Handle AI player starting territory selection during setup phase.

        During setup, AI players wait for the HUMAN to click a territory
        to choose their starting location. This allows manual selection of
        AI starting positions for strategic balance.

        This method just displays a message - the actual claiming happens
        when the human clicks a territory (same flow as human players).
        """
        # AI waits for human to select their starting territory
        # The territory claiming happens through normal click handling
        # No automatic selection - user controls all starting positions
        pass


if __name__ == "__main__":
    from main_menu import MainMenu
    from integrated_setup import IntegratedSetup
    from campaign_screen import CampaignScreen, MissionScreen, MISSION_DATA
    from network.multiplayer_setup import MultiplayerSetup
    from recap_screen import RecapScreen
    from loading_screen import LoadingScreen
    from settings_manager import settings
    from achievement_manager import achievement_manager
    from steam_integration import steam_manager

    def show_recap_if_ended(game):
        """Show post-game recap screen after any game that progressed past setup."""
        if not hasattr(game, 'game_state') or game.game_state.phase == 'setup':
            return

        # Game logger: finalize and save log file (before recap, after game ends)
        if hasattr(game.game_state, 'game_logger') and game.game_state.game_logger:
            game.game_state.game_logger.finalize_and_save()

        # Sync logger: finalize and save multiplayer state sync log
        if hasattr(game.game_state, 'sync_logger') and game.game_state.sync_logger:
            game.game_state.sync_logger.finalize_and_save()

        # Player Level: record XP earned first so level achievements can detect new level
        from player_level import player_level_manager
        xp_result = player_level_manager.record_game_xp(game)

        # Record game result and check for newly earned achievements (after XP update)
        newly_earned = achievement_manager.record_game_result(game)

        end_stats = game.game_state.get_end_game_stats()
        player_names = [game.game_state.get_player_name(i) for i in range(game.game_state.num_players)]
        player_colors = game.game_state.player_colors[:game.game_state.num_players]
        winner = getattr(game.game_state, 'winner', -1)

        # Pass replay recorder to recap screen for "Save Replay" button
        replay_recorder = getattr(game.game_state, 'replay_recorder', None)

        # Start recap music (Northern Honour on loop)
        music_manager.start_recap_music()

        recap = RecapScreen(
            screen=game.screen,
            player_stats=end_stats,
            player_names=player_names,
            player_colors=player_colors,
            winner_index=winner,
            num_players=game.game_state.num_players,
            newly_earned_achievements=newly_earned,
            xp_result=xp_result,
            replay_recorder=replay_recorder
        )
        recap_result = recap.run()

        # Stop recap music, restart menu music
        music_manager.stop()
        music_manager.start_menu_music()

        # Propagate Alt+F4 from recap screen to caller
        if recap_result == 'quit':
            return 'quit'

    # Load settings first
    logger.info("\n" + "="*60)
    logger.info("LOADING SETTINGS")
    logger.info("="*60)
    settings.load()
    logger.info("="*60 + "\n")

    # Set Windows App User Model ID BEFORE pygame.init() so the taskbar treats
    # this as its own app (not python.exe).  Must be called before any window
    # creation — pygame.init() can trigger early OS icon caching on Windows 11.
    import sys
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AvareonWar.WarOfAvareon')
        except Exception:
            pass

    # Initialize pygame for main menu
    pygame.init()

    # Load and set window/taskbar icon early — must be set before first set_mode
    # on Windows.  _load_app_icon()/_set_app_icon() are defined at MODULE level
    # (above class Game) so they also exist when main.py is imported rather than
    # run as a script; _app_icon is reused after every set_mode call to prevent
    # pygame from reverting to the default Python icon.
    _loaded_icon = _load_app_icon()
    if _loaded_icon is not None:
        try:
            pygame.display.set_icon(_loaded_icon)
        except Exception:
            pass

    # Initialize Steamworks SDK (no-op if Steam not running or SteamworksPy not installed)
    steam_manager.initialize()

    # Wait for Steam to load user stats before syncing achievements —
    # SetAchievement silently fails until RequestCurrentStats callback fires
    steam_manager.pump_until_stats_ready()

    # Bi-directional Steam achievement sync:
    # 1. Pull achievements from Steam that are missing locally (recovers from config resets)
    # 2. Push locally-earned achievements to Steam (catches offline unlocks)
    from achievement_manager import achievement_manager
    achievement_manager.sync_from_steam()
    achievement_manager.sync_to_steam()

    # If Steam is available, use Steam persona name as player name
    if steam_manager.is_available:
        steam_name = steam_manager.get_player_name()
        if steam_name:
            settings.set_player_name(steam_name)
            settings.save()

    # Register Steam shutdown as atexit handler so it runs on any exit path
    import atexit
    atexit.register(steam_manager.shutdown)

    # Initialize menu-only sounds for fast startup (game sounds deferred to loading screen)
    from global_sound import initialize_menu_sounds, sound_manager
    initialize_menu_sounds()

    # Initialize music system and apply saved volume settings
    from music_manager import music_manager, MUSIC_END_EVENT
    master_vol = settings.get('master_volume', 0.8)
    music_vol = settings.get('music_volume', 0.5)
    sfx_vol = settings.get('sfx_volume', 0.5)
    music_manager.set_master_volume(master_vol)
    music_manager.set_music_volume(music_vol)
    # Apply effective SFX volume (sfx * master) to sound effects
    sound_manager.set_volume(sfx_vol * master_vol)
    # Create initial window for main menu using settings
    initial_resolution = settings.get_resolution()
    initial_fullscreen = settings.is_fullscreen()

    # Centralized so VSync is applied here too (see display_utils)
    screen, _ = set_display_mode(
        initial_resolution, initial_fullscreen, settings.get('vsync', False))

    pygame.display.set_caption("War of Avareon")
    _set_app_icon()  # Re-apply icon after display creation
    pygame.mouse.set_visible(False)  # Hide system cursor — custom cursor drawn via utils/cursor.py

    # Check for Steam invite auto-connect launch parameter (+connect ip:port)
    # When a friend accepts a Steam invite, the game is launched with this argument.
    # Steam may pass the connect string as two args (+connect ip:port) or as a single
    # arg (+connect ip:port) depending on platform — handle both cases.
    _steam_connect_target = None
    for _i, _arg in enumerate(sys.argv):
        if _arg == '+connect' and _i + 1 < len(sys.argv):
            _steam_connect_target = sys.argv[_i + 1]
        elif _arg.startswith('+connect '):
            # Single-arg form: Steam passed the entire "+connect ip:port" as one argument
            _steam_connect_target = _arg[len('+connect '):]
    if _steam_connect_target:
        logger.info(f"Steam invite detected: will auto-connect to {_steam_connect_target}")

    # Main menu loop
    # Book of Tales scenarios: id (book_of_tales.SCENARIOS 'id') -> launch info, in
    # the same shape as the campaign loop's _MISSION_REGISTRY. Defined at this level
    # (not inside the loop) because _launch_saved_game also reads it to reload a
    # saved Tale. 'map_id' is the map_data map whose geometry the Tale plays on;
    # the config copy of it is what Game.initialize_game() actually reads.
    _TALE_REGISTRY = {
        'tale_1': {
            'import': ('tale_lack_of_funds', 'TaleLackOfFunds'),
            'map': 'maps/azincournean_highlands/map.png',
            'map_id': 'azincournean_highlands',
            'config': {
                'map_id': 'azincournean_highlands',
                'num_players': 4,
                # 0 = player (Londic Empire), 1 = Aelatanaic Tribes (Medium AI),
                # 2 = Heilonic Kingdoms (Hard AI), 3 = Kingdom of Daurels (Hard AI)
                'player_is_ai': [False, True, True, True],
                'player_ai_difficulty': [0, 1, 2, 2],
                'player_teams': [0, 1, 2, 3],
                'win_condition': 'Total Conquest',
                'taxation_level': 0,
                'player1_territory': 'Generax',
                'player2_territory': 'Leyana',
                'player3_territory': 'Entaron',
                'player4_territory': 'Daurels',
            },
        },
        'tale_2': {
            # Final Breaths: Avareon geometry with Campaign Mission 3's territories
            # and background (the Tale enables Mission 3's territory set itself)
            'import': ('tale_final_breaths', 'TaleFinalBreaths'),
            'map': 'assets/CampaignMaps/Campaign3Map.png',
            'map_id': 'avareon',
            'config': {
                'map_id': 'avareon',
                'num_players': 3,
                # 0 = player (Zjoal Empire), 1 = Kerunian Empire (Hard AI),
                # 2 = Nordian Rebels (never acts — the Tale ends its turns)
                'player_is_ai': [False, True, True],
                'player_ai_difficulty': [0, 2, 0],
                'player_teams': [0, 1, 2],
                'win_condition': 'Total Conquest',
                'taxation_level': 0,
                # The Rebels start with no land, so they get no start territory
                'player1_territory': 'Lunedale',
                'player2_territory': 'Affrancian Uplands',
            },
        },
    }

    def _run_registered_mission(screen, mission_id, mission_info, music_manager):
        """
        Run one campaign mission or Book of Tales scenario from its registry entry.

        Flow: intro cutscene -> LoadingScreen (fresh game) -> mission object ->
        game.run() -> outro cutscene (victory only) -> recap -> cleanup.
        Shared by the campaign loop (_MISSION_REGISTRY) and the Book of Tales
        branch (_TALE_REGISTRY), so both launch paths stay identical.

        Returns (game_result, screen). The caller decides what to do with
        'quit'; a recap-screen quit exits here, as it always has.
        """
        import importlib
        import map_data as _map_data
        from cutscene_player import CutscenePlayer

        # Stop menu music before cutscene/loading
        music_manager.stop()

        # Play pre-mission cutscene if one exists for this mission
        intro_cutscene = CutscenePlayer(screen, f"{mission_id}_intro")
        if intro_cutscene.has_cutscene:
            intro_cutscene.run()

        # Dynamic import of mission class
        module = importlib.import_module(mission_info['import'][0])
        MissionClass = getattr(module, mission_info['import'][1])

        # Create game with campaign map, load assets via loading screen.
        # A 'map_id' in the config makes initialize_game() load that map's
        # geometry; without one it defaults to Avareon.
        game = Game(existing_screen=screen, campaign_map=mission_info['map'])
        screen = game.screen
        # Pass mission_id so loading screen shows mission-specific tips
        # (unknown ids, e.g. tales, fall back to a generic tip)
        loading = LoadingScreen(screen, game, mission_info['config'], mission_id=mission_id)
        loading.run()

        # Start game music after loading completes
        music_manager.start_game_music()

        mission_obj = MissionClass(game.game_state, game)
        game.tutorial_mission = mission_obj
        game.game_state.tutorial_mission = mission_obj
        _map_data.set_tutorial_mission(mission_obj)

        game_result = game.run()

        # Stop game music before outro cutscene / recap
        music_manager.stop()

        # Post-mission outro cutscene — victory only. A defeat returns
        # 'campaign_defeat' from Game.run(), failing this check on purpose.
        if game_result == 'campaign':
            outro_cutscene = CutscenePlayer(screen, f"{mission_id}_outro")
            if outro_cutscene.has_cutscene:
                outro_cutscene.run()

        if show_recap_if_ended(game) == 'quit':
            pygame.quit()
            sys.exit()

        # Clean up mission reference and territory filtering
        _map_data.set_tutorial_mission(None)
        if mission_info.get('cleanup_territories', True):
            _map_data.clear_enabled_territories()
            _map_data.clear_territory_display_names()

        return game_result, screen

    def _launch_saved_game(screen, save_data, music_manager):
        """
        Load a saved campaign game from save_data and run it.

        Flow: LoadingScreen (init fresh game) -> overwrite state from save ->
        create mission -> restore mission state -> game.run() -> cleanup.

        Returns game_result ('quit', 'campaign', 'campaign_defeat', 'main_menu', etc.)
        """
        import importlib
        import map_data as _map_data
        from save_manager import deserialize_game_state

        metadata = save_data.get('metadata', {})
        game_config = save_data.get('game_config', {})
        mission_id = metadata.get('mission_id', '')

        # Look up mission registry to get map path and class
        # Reuse the same _MISSION_REGISTRY defined inside the campaign loop
        _SAVE_MISSION_REGISTRY = {
            'mission_2': {'import': ('campaign_mission_2', 'Mission2'), 'map': 'assets/CampaignMaps/Campaign2Map.png'},
            'mission_3': {'import': ('campaign_mission_3', 'Mission3'), 'map': 'assets/CampaignMaps/Campaign3Map.png'},
            'mission_4': {'import': ('campaign_mission_4', 'Mission4'), 'map': 'assets/CampaignMaps/Campaign4Map.png'},
            'mission_5': {'import': ('campaign_mission_5', 'Mission5'), 'map': 'assets/CampaignMaps/Campaign5Map.png'},
            'mission_6': {'import': ('campaign_mission_6', 'Mission6'), 'map': 'assets/CampaignMaps/Campaign6Map.png'},
            'mission_7': {'import': ('campaign_mission_7', 'Mission7'), 'map': 'assets/CampaignMaps/Campaign6Map.png'},
        }
        # Book of Tales scenarios save through the same path; their entries also
        # carry 'map_id' (e.g. Azincournean Highlands), which must be reloaded.
        _SAVE_MISSION_REGISTRY.update(_TALE_REGISTRY)

        mission_info = _SAVE_MISSION_REGISTRY.get(mission_id)
        if not mission_info:
            logger.error(f"Cannot load save: unknown mission_id '{mission_id}'")
            return None

        # Build setup config from saved game_config
        setup_config = {
            'num_players': game_config.get('num_players', 2),
            'player_is_ai': game_config.get('player_is_ai', [False, True]),
            'player_ai_difficulty': game_config.get('player_ai_difficulty', [0, 0]),
            'player_teams': game_config.get('player_teams', [0, 1]),
            'win_condition': game_config.get('victory_condition', 'Total Conquest'),
            'taxation_level': game_config.get('taxation_level', 0),
        }
        # Non-Avareon missions (Book of Tales) must load their own map geometry,
        # or the saved territory names would be applied to Avareon's polygons.
        if mission_info.get('map_id'):
            setup_config['map_id'] = mission_info['map_id']

        # Dynamic import of mission class
        module = importlib.import_module(mission_info['import'][0])
        MissionClass = getattr(module, mission_info['import'][1])

        # Stop menu music before loading
        music_manager.stop()

        # Create game with campaign map, run loading screen
        game = Game(existing_screen=screen, campaign_map=mission_info['map'])
        screen = game.screen
        loading = LoadingScreen(screen, game, setup_config, mission_id=mission_id)
        loading.run()

        # Create mission object FIRST — constructor calls _setup_initial_state() which
        # sets territory filtering, display names, flag icons, and initial game state.
        # We overwrite the game state AFTER so saved data takes precedence.
        mission_obj = MissionClass(game.game_state, game)

        # NOW overwrite the freshly initialized game state with saved data
        # (this replaces the initial territory owners, armies, buildings, etc. set by the mission)
        deserialize_game_state(game.game_state, save_data.get('game_state', {}))

        # Restore player config from save (names, colors, etc.)
        if 'player_names' in game_config:
            game.game_state.player_names = list(game_config['player_names'])
        if 'player_colors' in game_config:
            # Convert inner lists back to tuples (JSON deserializes tuples as lists)
            game.game_state.player_colors = [tuple(c) for c in game_config['player_colors']]

        # Restore mission-specific state from save (skips intro, restores quest progress, etc.)
        mission_state = save_data.get('mission_state', {})
        if hasattr(mission_obj, 'restore_save_state'):
            mission_obj.restore_save_state(mission_state)

        # Reset XP earned to 0 — prevents exploit where player saves, finishes game (earning XP),
        # then reloads and replays the same section to double-count pre-save XP.
        # Only post-load actions will count toward XP.
        gs = game.game_state
        for p in range(gs.num_players):
            if p in gs.player_stats and 'xp_earned' in gs.player_stats[p]:
                gs.player_stats[p]['xp_earned'] = 0

        # Log hero state after deserialization for debugging
        for p, heroes in gs.heroes.items():
            if heroes:
                hero_names = list(heroes.keys())
                logger.info(f"Save load: Player {p} heroes restored: {hero_names}")

        # Wire up mission references
        game.tutorial_mission = mission_obj
        game.game_state.tutorial_mission = mission_obj
        _map_data.set_tutorial_mission(mission_obj)

        # Stop any lingering transmission sound from skipped intro
        from global_sound import stop_transmission_sound
        stop_transmission_sound()

        # Start game music
        music_manager.start_game_music()

        game_result = game.run()

        # Stop game music
        music_manager.stop()

        # Post-mission outro cutscene — victory only. A defeat returns
        # 'campaign_defeat' from Game.run(), which deliberately fails this check.
        if game_result == 'campaign':
            from cutscene_player import CutscenePlayer
            outro_cutscene = CutscenePlayer(screen, f"{mission_id}_outro")
            if outro_cutscene.has_cutscene:
                outro_cutscene.run()

        if show_recap_if_ended(game) == 'quit':
            pygame.quit()
            sys.exit()

        # Clean up mission reference and territory filtering
        _map_data.set_tutorial_mission(None)
        _map_data.clear_enabled_territories()
        _map_data.clear_territory_display_names()

        return game_result

    while True:
        # Re-fetch the live display surface each iteration. Toggling VSync requires
        # pygame.display.quit(), which DESTROYS the previous Surface object — a
        # cached `screen` then raises "display Surface quit" when a screen is
        # constructed from it (e.g. CampaignScreen). set_mode() alone never
        # invalidated surfaces, so this only became possible once VSync existed.
        _live = current_surface()
        if _live is not None:
            screen = _live

        # If launched via Steam invite, skip main menu and go directly to multiplayer join
        if _steam_connect_target:
            action = 'steam_invite_join'
        else:
            main_menu = MainMenu(screen)
            # Start menu music after MainMenu is loaded (avoids playing over black screen).
            # Guard with is_playing() so returning from recap/recreate doesn't restart.
            if not music_manager.is_playing():
                music_manager.start_menu_music()
            action = main_menu.run()

        if action == 'quit':
            pygame.quit()
            sys.exit()
        elif action == 'recreate_window':
            # Display settings changed in options - recreate window
            pygame.display.quit()
            pygame.init()
            # Reload icon surface (old one invalidated by display.quit)
            try:
                _app_icon = pygame.image.load(_ico_path)
                pygame.display.set_icon(_app_icon)
            except Exception:
                pass

            # Re-register music end event after pygame reinit
            pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
            # Restart menu music (pygame reinit kills mixer state)
            music_manager.start_menu_music()

            # Reload settings and recreate window
            settings.load()
            initial_resolution = settings.get_resolution()
            initial_fullscreen = settings.is_fullscreen()

            # Centralized so VSync is applied here too (see display_utils)
            screen, _ = set_display_mode(
                initial_resolution, initial_fullscreen, settings.get('vsync', False))

            pygame.display.set_caption("War of Avareon")
            _set_app_icon()  # Re-apply icon after window recreation
            pygame.mouse.set_visible(False)  # Re-hide cursor after window recreation
            continue
        elif action == 'campaign':
            # Campaign loop: campaign screen <-> mission screens
            while True:
                screen = current_surface() or screen
                campaign = CampaignScreen(screen)
                mission_id = campaign.run()

                if mission_id == 'quit':
                    # Alt+F4 pressed — exit entire app
                    pygame.quit()
                    sys.exit()
                if mission_id is None:
                    # User clicked Return to Main Menu
                    break

                # Saved Games button clicked — open save browser
                if mission_id == 'saved_games':
                    from save_browser import SaveBrowser
                    screen = current_surface() or screen
                    browser = SaveBrowser(screen)
                    browser_result = browser.run()

                    if browser_result and browser_result.get('action') == 'quit':
                        pygame.quit()
                        sys.exit()

                    if browser_result and browser_result.get('action') == 'load':
                        # Load saved game flow
                        save_data = browser_result['save_data']
                        _load_result = _launch_saved_game(screen, save_data, music_manager)
                        if _load_result == 'quit':
                            pygame.quit()
                            sys.exit()
                    # Return to campaign screen (regardless of load/back)
                    continue

                if mission_id == 'book_of_tales':
                    # Book of Tales scenario picker (bottom-right icon on the
                    # Campaign screen). Launching a tale runs it, then reopens the
                    # Book of Tales; Return (or ESC) goes back to the Campaign screen.
                    from book_of_tales import BookOfTales
                    while True:
                        screen = current_surface() or screen
                        # Menu music stops for a tale; restart it on the way back
                        if not music_manager.is_playing():
                            music_manager.start_menu_music()
                        tales_result = BookOfTales(screen).run()
                        action = tales_result.get('action') if tales_result else None
                        if action == 'quit':
                            pygame.quit()
                            sys.exit()
                        if action != 'launch':
                            break
                        tale_id = tales_result.get('scenario_id')
                        tale_info = _TALE_REGISTRY.get(tale_id)
                        if not tale_info:
                            logger.error(f"Book of Tales: no registry entry for '{tale_id}'")
                            continue
                        game_result, screen = _run_registered_mission(
                            screen, tale_id, tale_info, music_manager)
                        if game_result == 'quit':
                            pygame.quit()
                            sys.exit()
                    continue

                # User selected a mission - open mission screen
                mission_data = MISSION_DATA.get(mission_id, {})
                mission = MissionScreen(screen, mission_id, mission_data)
                result = mission.run()

                # Alt+F4 on mission screen — exit entire app
                if result == 'quit':
                    pygame.quit()
                    sys.exit()

                # Check if user launched a mission
                if result and result.startswith('launch_'):
                    launched_mission = result[len('launch_'):]

                    # Phase 2D: Unified campaign mission launcher
                    # All missions share the same launch/run/cleanup pattern, differing only in
                    # config (players, territories), map path, and mission class.
                    # Mission 1 (tutorial) is special: 2 players, no territory cleanup.
                    _MISSION_REGISTRY = {
                        'mission_1': {
                            'import': ('tutorial_mission', 'TutorialMission'),
                            'map': 'assets/CampaignMaps/Campaign1Map.png',
                            'config': {
                                'num_players': 2,
                                'player_is_ai': [False, True],
                                'player_ai_difficulty': [0, 0],
                                'player_teams': [0, 1],
                                'win_condition': 'Total Conquest',
                                'taxation_level': 0,
                                'player1_territory': 'Lunedale',
                                'player2_territory': 'Free Cities',
                            },
                            'cleanup_territories': False,  # Tutorial doesn't filter territories
                        },
                        'mission_2': {
                            'import': ('campaign_mission_2', 'Mission2'),
                            'map': 'assets/CampaignMaps/Campaign2Map.png',
                            'config': {
                                'num_players': 4,
                                'player_is_ai': [False, True, True, True],
                                'player_ai_difficulty': [0, 0, 0, 0],
                                'player_teams': [0, 1, 2, 3],
                                'win_condition': 'Total Conquest',
                                'taxation_level': 0,
                                'player1_territory': 'Lobardia',
                                'player2_territory': 'Elletian Isles',
                                'player3_territory': 'Venexia',
                                'player4_territory': 'Valeonia',
                            },
                        },
                        'mission_3': {
                            'import': ('campaign_mission_3', 'Mission3'),
                            'map': 'assets/CampaignMaps/Campaign3Map.png',
                            'config': {
                                'num_players': 4,
                                'player_is_ai': [False, True, True, True],
                                'player_ai_difficulty': [0, 0, 0, 0],
                                'player_teams': [0, 1, 2, 3],
                                'win_condition': 'Total Conquest',
                                'taxation_level': 0,
                                'player1_territory': 'Zjoal Islands',
                                'player2_territory': 'Free Cities',
                                'player3_territory': 'Damlére',
                                'player4_territory': 'Ahtep',
                            },
                        },
                        'mission_4': {
                            'import': ('campaign_mission_4', 'Mission4'),
                            'map': 'assets/CampaignMaps/Campaign4Map.png',
                            'config': {
                                'num_players': 4,
                                'player_is_ai': [False, True, True, True],
                                'player_ai_difficulty': [0, 0, 0, 0],
                                'player_teams': [0, 1, 2, 3],
                                'win_condition': 'Total Conquest',
                                'taxation_level': 0,
                                'player1_territory': 'Aelatania',
                                'player2_territory': 'Londia',
                                'player3_territory': 'Valeonia',
                                'player4_territory': 'Amennia',
                            },
                        },
                        'mission_5': {
                            'import': ('campaign_mission_5', 'Mission5'),
                            'map': 'assets/CampaignMaps/Campaign5Map.png',
                            'config': {
                                'num_players': 3,
                                'player_is_ai': [False, True, True],
                                'player_ai_difficulty': [0, 0, 0],
                                'player_teams': [0, 0, 1],
                                'win_condition': 'Total Conquest',
                                'taxation_level': 0,
                                'player1_territory': 'Nordica',
                                'player2_territory': 'Elletian Isles',
                                'player3_territory': 'Aelatania',
                            },
                        },
                        'mission_6': {
                            'import': ('campaign_mission_6', 'Mission6'),
                            'map': 'assets/CampaignMaps/Campaign6Map.png',
                            'config': {
                                'num_players': 4,
                                'player_is_ai': [False, True, True, True],
                                'player_ai_difficulty': [0, 0, 0, 0],
                                'player_teams': [0, 1, 2, 3],
                                'win_condition': 'Total Conquest',
                                'taxation_level': 0,
                                'player1_territory': 'Aelatania',
                                'player2_territory': 'Lobardia',
                                'player3_territory': 'Venexia',
                                'player4_territory': 'Valeonia',
                            },
                        },
                        'mission_7': {
                            'import': ('campaign_mission_7', 'Mission7'),
                            'map': 'assets/CampaignMaps/Campaign6Map.png',  # Same map as Mission 6
                            'config': {
                                'num_players': 2,
                                'player_is_ai': [False, True],
                                'player_ai_difficulty': [0, 2],
                                'player_teams': [0, 1],
                                'win_condition': 'Total Conquest',
                                'taxation_level': 0,
                                'player1_territory': 'Courtieux',
                                'player2_territory': 'Nordica',
                            },
                        },
                    }

                    mission_info = _MISSION_REGISTRY.get(launched_mission)
                    if mission_info:
                        game_result, screen = _run_registered_mission(
                            screen, launched_mission, mission_info, music_manager)
                        if game_result == 'quit':
                            pygame.quit()
                            sys.exit()

                    # After mission completes, loop back to campaign screen
                    continue
                # Mission screen returned without launch - loop back to campaign screen

            continue
        elif action == 'custom_game':
            # Seamless transition: reuse existing screen
            # Create game instance with existing screen
            # Game.__init__() loads settings directly from SettingsManager
            game = Game(existing_screen=screen)

            # Update screen reference in case Game resized it
            screen = game.screen

            # Show unified integrated setup (player config + territory selection in one screen)
            integrated_setup = IntegratedSetup(game.screen)
            setup_config = integrated_setup.run()

            if setup_config == 'quit':
                # Alt+F4 pressed — exit entire app
                pygame.quit()
                sys.exit()
            if setup_config is None:
                # User cancelled setup - return to main menu
                logger.info("Setup cancelled - returning to main menu")

                # Reload settings (in case they were changed)
                settings.load()

                # Screen already exists, just continue to main menu
                continue

            # Stop menu music before loading screen
            music_manager.stop()

            # Show loading screen (deferred asset loading + "click to start")
            loading = LoadingScreen(screen, game, setup_config)
            loading.run()

            # Start game music after loading completes
            music_manager.start_game_music()

            # Attach game logger for custom games (not campaign)
            from game_logger import GameLogger
            if hasattr(game, 'game_state') and game.game_state:
                game.game_state.game_logger = GameLogger(game.game_state)

            # Attach sync logger for multiplayer games (desync diagnosis)
            if hasattr(game, 'game_state') and game.game_state and game.multiplayer_mode:
                from sync_logger import SyncLogger
                game_id = game.game_state.game_logger.game_id if game.game_state.game_logger else None
                game.game_state.sync_logger = SyncLogger(
                    game.game_state, game.local_player_index,
                    is_host=(game.local_player_index == 0), game_id=game_id
                )

            # Attach replay recorder for custom games (not campaign)
            from replay_recorder import ReplayRecorder
            if hasattr(game, 'game_state') and game.game_state:
                game.game_state.replay_recorder = ReplayRecorder(game.game_state)

            # Run game
            result = game.run()

            # Stop game music before recap
            music_manager.stop()

            # Show post-game recap screen if game ended with a winner
            if show_recap_if_ended(game) == 'quit':
                pygame.quit()
                sys.exit()

            # If game returns 'main_menu', loop back to main menu
            if result == 'main_menu':
                # Save any settings changes from in-game
                settings.update_from_game(game)

                # Seamless transition: keep screen, just reload settings
                settings.load()

                # Update screen reference (in case display settings changed)
                screen = game.screen

                # Check if we need to resize for main menu
                initial_resolution = settings.get_resolution()
                initial_fullscreen = settings.is_fullscreen()
                # Refresh first: a VSync toggle during the game destroys the old
                # display Surface, so the cached `screen` may be dead here.
                screen = current_surface() or screen
                current_size = screen.get_size()
                current_flags = screen.get_flags()
                current_is_fullscreen = bool(current_flags & pygame.FULLSCREEN)

                # Only recreate if settings changed
                if current_size != initial_resolution or current_is_fullscreen != initial_fullscreen:
                    # Centralized so VSync is applied here too (see display_utils)
                    screen, _ = set_display_mode(
                        initial_resolution, initial_fullscreen, settings.get('vsync', False))
                    _set_app_icon()  # Re-apply icon after display recreation
                    pygame.mouse.set_visible(False)  # Re-hide cursor after display recreation

                continue
            else:
                # Game exited normally (quit)
                pygame.quit()
                sys.exit()
        elif action == 'steam_invite_join':
            # Auto-join multiplayer game via Steam invite (+connect ip:port)
            # Parse host address from the connect target
            connect_target = _steam_connect_target
            _steam_connect_target = None  # Clear so subsequent loops go to main menu

            # Parse IP and port from connect string (format: "ip:port")
            if ':' in connect_target:
                host_ip, port_str = connect_target.rsplit(':', 1)
                try:
                    port = int(port_str)
                except ValueError:
                    port = 7777
            else:
                host_ip = connect_target
                port = 7777

            logger.info(f"Steam invite: connecting to {host_ip}:{port}")

            # Stop menu music
            music_manager.stop()

            # Connect as client — reuses _run_join_setup logic from multiplayer_setup
            from network.client import NetworkClient
            from network.territory_selector import TerritorySelector

            client = NetworkClient()
            player_name = settings.get_player_name()

            if not client.connect(host_ip, port=port, player_name=player_name):
                logger.warning(f"Steam invite: failed to connect to {host_ip}:{port}")
                # Fall back to main menu
                music_manager.start_menu_music()
                continue

            logger.info(f"Steam invite: connected to {host_ip}:{port}")
            local_player_index = getattr(client, 'player_index', 1)

            # Show territory selection screen as client
            selector = TerritorySelector(
                screen, client, is_host=False,
                num_players=4,
                victory_condition=0,
                taxation_level=0,
                turn_mode=0,
                lobby_state=None,
                local_player_index=local_player_index
            )
            result = selector.run()

            if result == 'quit':
                # Alt+F4 pressed — exit entire app
                client.disconnect()
                pygame.quit()
                sys.exit()
            if not result or (isinstance(result, tuple) and len(result) == 2 and result[0] == 'kicked'):
                # Cancelled or kicked — disconnect and return to main menu
                client.disconnect()
                music_manager.start_menu_music()
                continue

            # Unpack result and build config (same as multiplayer flow)
            lobby_state, victory_condition, taxation_level, turn_mode, neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer = result
            final_player_index = selector.local_player_index
            client.player_index = final_player_index

            # Build game config from lobby state (reuse MultiplayerSetup's builder)
            # Create a lightweight instance just for the config builder method
            mp_setup_tmp = MultiplayerSetup.__new__(MultiplayerSetup)
            mp_setup_tmp.victory_options = ["Domination (45+)", "Capital Assault", "Total Conquest"]
            mp_setup_tmp.turn_mode_options = ["Sequential", "Simultaneous"]
            config = mp_setup_tmp._build_config_from_lobby(
                lobby_state, victory_condition, taxation_level, turn_mode,
                neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer
            )

            # Initialize and run game (same as regular multiplayer flow)
            game = Game(existing_screen=screen, network_connection=client)
            screen = game.screen
            game.local_player_index = final_player_index

            loading = LoadingScreen(screen, game, config, network_connection=client)
            loading.run()

            music_manager.start_game_music()

            from game_logger import GameLogger
            if hasattr(game, 'game_state') and game.game_state:
                game.game_state.game_logger = GameLogger(game.game_state)

            # Attach sync logger for multiplayer (Steam invite client, always multiplayer)
            if hasattr(game, 'game_state') and game.game_state:
                from sync_logger import SyncLogger
                game_id = game.game_state.game_logger.game_id if game.game_state.game_logger else None
                game.game_state.sync_logger = SyncLogger(
                    game.game_state, game.local_player_index,
                    is_host=False, game_id=game_id
                )

            from replay_recorder import ReplayRecorder
            if hasattr(game, 'game_state') and game.game_state:
                game.game_state.replay_recorder = ReplayRecorder(game.game_state)

            result = game.run()

            music_manager.stop()
            if show_recap_if_ended(game) == 'quit':
                client.disconnect()
                pygame.quit()
                sys.exit()

            # Cleanup client connection
            client.disconnect()

            if result == 'main_menu':
                settings.load()
                initial_resolution = settings.get_resolution()
                initial_fullscreen = settings.is_fullscreen()
                # Centralized so VSync is applied here too (see display_utils)
                screen, _ = set_display_mode(
                    initial_resolution, initial_fullscreen, settings.get('vsync', False))
                _set_app_icon()
                pygame.mouse.set_visible(False)
                continue
            else:
                pygame.quit()
                sys.exit()

        elif action == 'multiplayer':
            # Multiplayer setup flow
            game = Game(existing_screen=screen)
            screen = game.screen

            # Show multiplayer setup
            multiplayer_setup = MultiplayerSetup(game.screen)
            setup_result = multiplayer_setup.run()

            if setup_result == 'quit':
                # Alt+F4 pressed — exit entire app
                pygame.quit()
                sys.exit()
            if setup_result is None:
                # User cancelled - return to main menu
                logger.info("Multiplayer setup cancelled - returning to main menu")
                settings.load()
                continue

            # Unpack setup result
            mode, network_connection, setup_config = setup_result
            logger.info(f"Multiplayer mode: {mode}")

            # Initialize game with config and network connection
            game = Game(existing_screen=screen, network_connection=network_connection)
            screen = game.screen

            # Set local player index based on mode
            if mode == 'host':
                game.local_player_index = 0  # Host is Player 1
            elif mode == 'client':
                game.local_player_index = network_connection.get_player_index()  # Get from server

            # Stop menu music before multiplayer loading
            music_manager.stop()

            # Show loading screen with multiplayer readiness sync
            loading = LoadingScreen(screen, game, setup_config,
                                    network_connection=network_connection)
            loading.run()

            # Start game music after loading completes
            music_manager.start_game_music()

            # Attach game logger for multiplayer games
            from game_logger import GameLogger
            if hasattr(game, 'game_state') and game.game_state:
                game.game_state.game_logger = GameLogger(game.game_state)

            # Attach sync logger for multiplayer games (desync diagnosis)
            if hasattr(game, 'game_state') and game.game_state:
                from sync_logger import SyncLogger
                game_id = game.game_state.game_logger.game_id if game.game_state.game_logger else None
                game.game_state.sync_logger = SyncLogger(
                    game.game_state, game.local_player_index,
                    is_host=(game.local_player_index == 0), game_id=game_id
                )

            # Attach replay recorder for multiplayer games
            from replay_recorder import ReplayRecorder
            if hasattr(game, 'game_state') and game.game_state:
                game.game_state.replay_recorder = ReplayRecorder(game.game_state)

            # Run game
            result = game.run()

            # Stop game music before recap
            music_manager.stop()

            # Show post-game recap screen if game ended with a winner
            if show_recap_if_ended(game) == 'quit':
                # Cleanup network before exit
                if mode == 'host':
                    network_connection.stop()
                elif mode == 'client':
                    network_connection.disconnect()
                pygame.quit()
                sys.exit()

            # Cleanup network connection
            if mode == 'host':
                network_connection.stop()
            elif mode == 'client':
                network_connection.disconnect()

            # Handle game exit
            if result == 'main_menu':
                settings.update_from_game(game)
                settings.load()
                screen = game.screen

                # Check if we need to resize
                initial_resolution = settings.get_resolution()
                initial_fullscreen = settings.is_fullscreen()
                # Refresh first: a VSync toggle during the game destroys the old
                # display Surface, so the cached `screen` may be dead here.
                screen = current_surface() or screen
                current_size = screen.get_size()
                current_flags = screen.get_flags()
                current_is_fullscreen = bool(current_flags & pygame.FULLSCREEN)

                if current_size != initial_resolution or current_is_fullscreen != initial_fullscreen:
                    # Centralized so VSync is applied here too (see display_utils)
                    screen, _ = set_display_mode(
                        initial_resolution, initial_fullscreen, settings.get('vsync', False))
                    _set_app_icon()  # Re-apply icon after display recreation
                    pygame.mouse.set_visible(False)  # Re-hide cursor after display recreation

                continue
            else:
                pygame.quit()
                sys.exit()
        elif action == 'replays':
            # Replay browser and viewer flow
            from replay_browser import ReplayBrowser
            from replay_viewer import ReplayViewer

            while True:
                screen = current_surface() or screen
                browser = ReplayBrowser(screen)
                browser_result = browser.run()

                if browser_result and browser_result.get('action') == 'quit':
                    # Alt+F4 pressed — exit entire app
                    pygame.quit()
                    sys.exit()

                if not browser_result or browser_result.get('action') == 'back':
                    # Return to main menu
                    break

                if browser_result.get('action') == 'watch':
                    replay_path = browser_result.get('path')
                    if replay_path:
                        viewer = ReplayViewer(screen, replay_path)
                        viewer_result = viewer.run()
                        if viewer_result == 'quit':
                            # Alt+F4 pressed in viewer — exit entire app
                            pygame.quit()
                            sys.exit()
                        # After viewer exits, loop back to browser
                        continue
                break
            continue