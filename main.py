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
import threading
from collections import deque
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
from rendering.bottom_panel_kit import (BottomPanelKit, TINT_END_TURN, TINT_END_TURN_HIGHLIGHT,
                                        TINT_SELECT_ARMY, TINT_SELECT_ALL, TINT_DESELECT_ALL,
                                        TINT_DEMOLISH, TINT_CONFISCATE,
                                        GOLD_TEXT as BOTTOM_GOLD_TEXT, EDGE_PAD_REF as EDGE_PAD_REF_PX)
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
        # Network messages held back, in arrival order, because this PC cannot apply the
        # first of them yet: a battle result or turn end that arrives while our own copy
        # of the move is still animating (the battle does not exist here yet), or - in
        # sequential mode - anything that arrives while our turn announcement still has to
        # run the turn-start effects. Released by _release_held_network_messages() once
        # that has happened (or after a limit).
        self._held_network_messages = []
        self._held_network_since = None
        # Types of received messages that raised while being applied (logged and
        # skipped, see _handle_network_message). The test harness fails on any.
        self.network_message_errors = []
        # Messages "sent" from another thread (the sequential AI's turn runs on a worker
        # thread on the host): queued here in order and sent by the main loop
        # (_flush_thread_messages). Message encoding is not thread-safe, and a main-thread
        # send flushes this queue first, so the order of events is kept.
        self._outgoing_from_threads = deque()

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
        # Territory view Forces section: Select Army button rect, and (rect, hero_name)
        # of the current player's clickable hero portrait (reset every frame)
        self.select_army_button = None
        self.forces_hero_button = None
        self.hero_view_portrait_button = None  # Hero view: (portrait rect, hero_name)
        self.keep_hero_button = None  # Keep view: (hero card rect, hero_name)
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
        # Simultaneous multiplayer: last (round, ready players) the host broadcast
        # (SIM_READY_STATE), and the resolving-phase clocks of the AFK rules
        self._sim_last_ready_state = None
        self._sim_resolving_since = None
        self._sim_local_battle_activity = None
        # Sequential multiplayer: the battles-phase clocks of the turn owner's AFK rules,
        # and whether the final state of a game that ended in our turn went out
        self._seq_battles_since = None
        self._seq_battle_activity = None
        self._final_state_sent = False

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

    def bottom_panel_geometry(self):
        """(top y, height) of the bottom UI panel - the module globals, which
        apply_display_settings() rewrites on a resolution change. Read by the
        bottom panel kit (rendering/bottom_panel_kit.py)."""
        return BOTTOM_UI_Y, BOTTOM_UI_HEIGHT

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

        # Starting Gold (Additional Options, 0-10,000). GameState starts everyone on the
        # default; campaign missions and tales never set the key and assign their own
        # gold later, so they are unaffected.
        if 'starting_gold' in setup_config:
            self.game_state.starting_gold = clamp_starting_gold(setup_config['starting_gold'])
            self.game_state.player_gold = [self.game_state.starting_gold] * len(self.game_state.player_gold)

        # The colours chosen in the lobby / Custom Game (they were ignored, M14): indices
        # into PLAYER_COLORS - a list in player order (Custom Game) or {slot: index} (lobby).
        # A loaded save's colours are RGB values and applied by the save path instead.
        # player_color_indices also picks each player's army flags (Red/Blue/... Flag).
        self.player_color_indices = list(range(self.game_state.num_players))
        chosen = setup_config.get('player_colors')
        if isinstance(chosen, (list, dict)):
            pairs = chosen.items() if isinstance(chosen, dict) else enumerate(chosen)
            for player, color_index in pairs:
                try:
                    player = int(player)                    # JSON object keys are strings
                except (TypeError, ValueError):
                    continue
                if (0 <= player < self.game_state.num_players and type(color_index) is int
                        and 0 <= color_index < len(PLAYER_COLORS)):
                    self.player_color_indices[player] = color_index
                    self.game_state.player_colors[player] = PLAYER_COLORS[color_index]

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

        # A new game: nothing of a previous one's turn bookkeeping carries over
        self._seq_battles_since = None
        self._seq_battle_activity = None
        self._final_state_sent = False

        # Wrap with SimultaneousGameState if in simultaneous mode
        self.sim_state = None  # Simultaneous mode state wrapper
        self.sim_ai = None  # Simultaneous mode AI adapter
        if game_mode == 'simultaneous':
            from simultaneous import SimultaneousGameState, SimPhaseManager, SimultaneousAI
            import ai_player  # For AI decision logic
            self.sim_state = SimultaneousGameState(self.game_state)
            self.sim_state.phase_manager = SimPhaseManager(self.sim_state)
            # The AI plans on the host only (or in single-player). Clients used to plan
            # for the AI slots too, with their own random choices; the host's orders are
            # the ones that count and reach clients in its execution snapshot.
            if not (self.multiplayer_mode and self.local_player_index not in (None, 0)):
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
        # Load all 4 player flag colors (Red, Blue, Green, Yellow) - each player's flags in
        # the colour chosen for them (player_color_indices), so flags match the territories
        player_flag_colors = ['Red', 'Blue', 'Green', 'Yellow']
        color_indices = getattr(self, 'player_color_indices', None) or []
        for player_index in range(len(player_flag_colors)):
            color_index = color_indices[player_index] if player_index < len(color_indices) else player_index
            color_name = player_flag_colors[color_index]
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
        # Territory of the battle the window shows. pending_battles shifts when another
        # player's battle resolves while the window is open, so FIGHT looks the battle up
        # by territory (the saved index could point at a different battle - or past the
        # end of the list).
        self.selected_battle_territory = None
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
        # Hover systems (update_button_hover types) that ran this frame - a hover whose
        # system did not run is dropped in update_frame_tooltips() (orphaned tooltips)
        self._hover_systems_this_frame = set()

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
        # Bottom panel kit: section geometry, headline + gold rule, ornate buttons,
        # BattleBar timer (rendering/bottom_panel_kit.py). Cleared on resolution change.
        self.bottom_panel_kit = BottomPanelKit(self)
        
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
        self.bottom_panel_tooltip = None  # Same, for the bottom panel (Forces icons)

        # Track previous player and phase for AI turn optimization
        self.previous_ai_check = -1
        self.previous_phase = None
        self.previous_turn_announcement = False

        # Initialize rendering coordinators (Phase 4: Rendering organization)
        self.map_renderer = MapRenderer(self)

        # Connect map_renderer to game_state for visual effects
        self.game_state.map_renderer = self.map_renderer

        # Sequential multiplayer: the turn owner's PC sends each turn's result (TURN_END
        # with a state snapshot), and the other PCs never advance a turn on their own.
        # (Turn-start completions are no longer sent - UNIT_COMPLETE re-added units every
        # PC had already trained itself, H1 - every PC runs them from the same state.)
        # The same owner sends EXECUTE_ORDERS when the turn's moves start, and the AI's
        # battles are seeded and sent (the host plays the computer players' turns).
        if self.multiplayer_mode and self.sim_state is None:
            self.game_state.on_turn_advanced = self._on_turn_advanced
            self.game_state.turn_advance_gate = self._owns_current_turn
            self.game_state.on_orders_executing = self._on_orders_executing
            self.game_state.shared_battle_resolver = self._resolve_and_share_battle

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

    def _process_network_messages(self):
        """Process incoming network messages from remote player"""
        if not self.network_connection:
            return

        # Messages queued by another thread (the host's sequential AI turn) go out first
        self._flush_thread_messages()

        # Check for disconnection
        if hasattr(self.network_connection, 'disconnected') and self.network_connection.disconnected:
            if not self.disconnect_dialog_shown:
                self.disconnect_dialog_shown = True
                reason = getattr(self.network_connection, 'disconnect_reason', 'Unknown reason')
                logger.info(f"[NETWORK] Connection lost: {reason}")
                # Set flag to show disconnect dialog
                self.show_disconnect_dialog = True
                self.disconnect_dialog_reason = reason

        # Messages held back earlier go first, in their original order
        if self._held_network_messages:
            self._release_held_network_messages()

        # Process all queued messages
        while True:
            msg = self.network_connection.message_queue.get_incoming_message()
            if not msg:
                break

            if self._held_network_messages:
                # Something earlier is still waiting - keep the arrival order
                self._held_network_messages.append(msg)
                continue
            self._handle_network_message(msg)

    # Longest a message may be held back (see _hold_network_message) before it is applied
    # anyway - our own animations and turn announcement always finish well within this
    _NETWORK_HOLD_LIMIT = 15.0  # seconds

    # ========== WHO MAY SEND WHAT (multiplayer audit, Phase 7) ==========
    # The server stamps every client message with the index of the connection it came on
    # (from_player_index) and drops any that names another player as the actor. Each PC
    # then checks what that player may do now. The host is the authority: its messages
    # carry no stamp and are never refused (it also plays the computer players' turns).

    # Sequential mode: only the player whose turn it is acts - their turn's actions, moves,
    # battles and turn end. (Accepted from anyone before: e.g. a TURN_END from another
    # player replaced the whole game with their snapshot.)
    _TURN_OWNER_MESSAGES = frozenset({
        MessageType.MOVEMENT_ORDER,
        MessageType.BUILDING_ORDER,
        MessageType.TRAINING_ORDER,
        MessageType.ORDER_REMOVE,
        MessageType.RESEARCH_ORDER,
        MessageType.HERO_TRAINING_ORDER,
        MessageType.EXECUTE_ORDERS,
        MessageType.BATTLE_RESOLVE,
        MessageType.TURN_END,
        MessageType.GOLD_TRANSFER,
        MessageType.SIM_HERO_ABILITY,
    })

    @staticmethod
    def _message_sender(message):
        """
        The client a received message came from - the index the server stamped on it - or
        None for the host (the host's own messages carry no stamp and are trusted).
        """
        sender = message.get('from_player_index')
        if isinstance(sender, int) and not isinstance(sender, bool):
            return sender
        return None

    def _refusal_for(self, msg_type, sender):
        """
        Why the client `sender` may not send `msg_type` now (None: it may). Checks that
        hold for every message; the handlers check the rest (a battle's resolver, an
        alliance marker's chooser, a hero's owner, a gold transfer's limits).
        """
        if sender is None:
            return None
        gs = self.game_state
        if gs is None or not (0 <= sender < gs.num_players):
            return "not a player of this game"
        if self.sim_state is None and msg_type in self._TURN_OWNER_MESSAGES:
            if gs.current_player != sender or gs.player_is_ai[sender]:
                return f"it is Player {gs.current_player + 1}'s turn"
        return None

    def _turn_start_pending(self):
        """
        Sequential multiplayer: this PC's turn announcement is still running, and with it
        the turn-start effects (finished buildings / training / research, cooldowns) it
        runs at its end. The new turn's messages wait for it: the turn owner's state
        snapshot already contains those effects, so applying it first had them run twice.
        """
        gs = self.game_state
        return (self.multiplayer_mode and self.sim_state is None and gs is not None
                and gs.phase == 'playing' and gs.turn_announcement_active)

    def _battles_may_still_appear(self):
        """
        True while this PC's own copy of a move is still playing out, so battles it has
        not detected yet may still appear (they are created when the armies arrive).
        """
        gs = self.game_state
        if gs is None:
            return False
        if gs.active_animations or getattr(gs, 'pending_arrivals', None):
            return True
        if self.sim_state is not None and self.sim_state.sim_phase == 'executing':
            pm = self.sim_state.phase_manager
            return pm is not None and not pm.animations_complete
        return False

    def _hold_network_message(self, message):
        """
        Keep a message this PC cannot apply yet - and, behind it, every message that
        arrives later, so the order is kept - until _release_held_network_messages().
        """
        if not self._held_network_messages:
            self._held_network_since = time.monotonic()
        self._held_network_messages.append(message)

    def _release_held_network_messages(self):
        """Replay held messages, in order, once what they wait for has happened."""
        waited = time.monotonic() - (self._held_network_since or time.monotonic())
        timed_out = waited > self._NETWORK_HOLD_LIMIT
        if (self._battles_may_still_appear() or self._turn_start_pending()) and not timed_out:
            return
        if timed_out:
            logger.warning(f"[NETWORK] Held messages waited {waited:.1f}s - applying them anyway")
        held = self._held_network_messages
        self._held_network_messages = []
        self._held_network_since = None
        for i, message in enumerate(held):
            self._handle_network_message(message, allow_hold=not timed_out)
            if self._held_network_messages:
                # A later message had to wait again (new movement started meanwhile):
                # keep the rest behind it, in order
                self._held_network_messages.extend(held[i + 1:])
                break

    def _handle_network_message(self, message: dict, allow_hold: bool = True):
        """
        Handle a single network message from a remote player (see
        _apply_network_message). A message that raises while being applied is logged
        and skipped: the exception used to escape the frame and close the game for
        this player. The next state snapshot (turn end / round end) heals whatever
        the message left half-applied.
        """
        try:
            self._apply_network_message(message, allow_hold)
        except Exception:
            msg_type = message.get('type') if isinstance(message, dict) else None
            logger.exception(f"[NETWORK] Failed to apply {msg_type} - message skipped")
            self.network_message_errors.append(msg_type)

    def _apply_network_message(self, message: dict, allow_hold: bool = True):
        """
        Handle a single network message from remote player.

        Args:
            message: Decoded message dict with 'type' and 'data' keys
            allow_hold: False when replaying held messages after the hold limit -
                apply them now, never hold them again
        """
        msg_type = message.get('type')
        data = message.get('data', {})

        logger.debug(f"[NETWORK] Received {msg_type}: {self._payload_for_log(data)}")

        # VALIDATION: Ensure local_player_index is initialized
        if self.local_player_index is None:
            logger.error("[NETWORK] ERROR: local_player_index not initialized, cannot process message")
            return

        # Sequential mode: our turn announcement still has to run this turn's start effects
        # - whatever the new turn brings waits for it (see _turn_start_pending)
        if allow_hold and self._turn_start_pending():
            self._hold_network_message(message)
            return

        # A client may only send what it may do now (the host is never refused)
        sender = self._message_sender(message)
        refusal = self._refusal_for(msg_type, sender)
        if refusal:
            logger.warning(f"[NETWORK] REJECTED {msg_type} from Player {sender + 1}: {refusal}")
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
            self._handle_remote_gold_transfer(data, sender=self._message_sender(message))

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
            # The turn owner's planned moves begin (sequential mode): its state + the
            # same moves here
            self._handle_remote_execute_orders(data)

        elif msg_type == MessageType.BATTLE_RESOLVE:
            # Remote player resolved a battle - replay it here (seeded), or apply the
            # result (older / seedless senders). May hold the message (and those after
            # it) until our own copy of the move has arrived and created the battle.
            self._handle_remote_battle_resolve(message, allow_hold=allow_hold)

        elif msg_type == MessageType.TURN_END:
            # Another player's turn ended (sequential mode): its result, then the next turn
            self._handle_remote_turn_end(message, allow_hold=allow_hold)

        elif msg_type == MessageType.CHAT_MESSAGE:
            # Remote player sent a chat message
            player_index = data.get('player_index', 0)
            message = data.get('message', '')

            # VALIDATION: Check if player_index is valid
            if player_index is None or player_index < 0 or player_index >= self.game_state.num_players:
                logger.warning(f"[NETWORK] REJECTED: Invalid chat player_index: {player_index}")
                return

            # Keep the channel: team chat used to arrive as 'all' chat on every PC, so
            # enemies could read it (the displays filter by channel once it is kept)
            channel = data.get('channel', 'all')
            if channel not in ('all', 'team'):
                channel = 'all'

            if message:
                logger.debug(f"[NETWORK] Received {channel} chat from Player {player_index + 1}: {message}")
                self.game_state.add_chat_message(player_index, message, channel)

        elif msg_type == MessageType.DISCONNECT:
            # Remote player disconnected (legacy 1v1 message)
            logger.info("[NETWORK] Remote player disconnected")

        elif msg_type == MessageType.PLAYER_DISCONNECT:
            # A specific player disconnected - AI takes over their slot
            player_index = data.get('player_index')
            ai_takeover = data.get('ai_takeover', True)
            # Log the raw index: "player_index + 1" crashed on a message without one
            logger.info(f"[NETWORK] Player index {player_index} disconnected - AI takeover: {ai_takeover}")

            if ai_takeover and player_index is not None:
                # Mark player as AI-controlled using existing player_is_ai list
                if 0 <= player_index < len(self.game_state.player_is_ai):
                    # The AI plays their empire from now on (Medium); the host also starts
                    # it planning / resolving for them (simultaneous mode)
                    self._take_over_disconnected_player(player_index)
                    logger.info(f"[NETWORK] Player {player_index + 1} is now AI-controlled")

                    # Track which players disconnected (for potential reconnection)
                    if not hasattr(self.game_state, 'disconnected_players'):
                        self.game_state.disconnected_players = set()
                    self.game_state.disconnected_players.add(player_index)

                    # Chat notification: inform all players about the disconnect
                    player_name = self.game_state.player_names[player_index] if self.game_state.player_names[player_index] else f"Player {player_index + 1}"
                    # A system line: sent as player 0 it read as written by the host
                    self.game_state.add_system_chat_message(f"{player_name} has disconnected. AI taking over.")

        elif msg_type == MessageType.DISCONNECT_ELIMINATION:
            # Player eliminated after reconnect timeout (60s) — both host and clients process this
            player_index = data.get('player_index')
            if player_index is not None and 0 <= player_index < self.game_state.num_players:
                logger.info(f"[NETWORK] Player {player_index + 1} eliminated (disconnect timeout)")

                # Chat notification
                player_name = self.game_state.player_names[player_index] if self.game_state.player_names[player_index] else f"Player {player_index + 1}"
                self.game_state.add_system_chat_message(f"{player_name} has been disconnected and eliminated.")

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
            # A client finished planning; its orders travel WITH this message. Host only:
            # clients learn who is ready from SIM_READY_STATE (the host's own ready used
            # to reach them after the round it belonged to had ended).
            player_id = data.get('player_id')
            orders = data.get('orders', [])

            # VALIDATION: Player ID must be valid
            if player_id is None or player_id < 0 or player_id >= self.game_state.num_players:
                logger.warning(f"[NETWORK] REJECTED: Invalid player_id {player_id} in SIM_PLAYER_READY (num_players={self.game_state.num_players})")
                return

            if self.sim_state is None or self.local_player_index != 0:
                return

            if self.sim_state.sim_phase != 'planning' or self.sim_state.players_ready.get(player_id, False):
                logger.warning(f"[SIM] Late or repeated SIM_PLAYER_READY from player {player_id} - "
                               f"phase '{self.sim_state.sim_phase}', orders discarded")
                return

            logger.info(f"[NETWORK] Player {player_id} marked ready with {len(orders)} orders (simultaneous mode)")
            # Store the player's orders (replacing anything stale)
            self.sim_state.player_orders[player_id] = []
            for order in orders:
                if isinstance(order, dict):
                    order['player_id'] = player_id  # Ensure player_id is set
                    self.sim_state.add_order(player_id, order)
                    logger.info(f"[SIM] Received order from Player {player_id}: {order.get('type')} "
                                f"{order.get('from_territory', order.get('territory'))} -> {order.get('to_territory')}")

            # When this completes the set, execution starts from the main loop
            # (sim_state.check_deferred_execution -> _sim_start_execution_phase)
            self.sim_state.mark_ready(player_id)

        elif msg_type == MessageType.SIM_READY_STATE:
            # Host -> client: who is ready this round. Sets only OTHER players' flags
            # (display only - no mark_ready side effects); this PC's own readiness is
            # its own. Messages for another round are stale and ignored.
            if self.sim_state is not None and self.local_player_index != 0:
                ready = set(data.get('ready') or [])
                if (data.get('round') == self.sim_state.round_number
                        and self.sim_state.sim_phase == 'planning'):
                    for pid in self.sim_state.players_ready:
                        if pid != self.local_player_index:
                            self.sim_state.players_ready[pid] = pid in ready

        elif msg_type == MessageType.SIM_ALL_READY:
            # Host started the round's execution (client receives this): its state
            # snapshot + the movement orders it validated
            if self.sim_state is not None and self.local_player_index != 0:
                self._sim_apply_all_ready(data)

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
            # Legacy: nothing sends this any more (every PC replays a battle from
            # BATTLE_RESOLVE's seed, and the server takes this type from no client). Its
            # old apply - new owner plus a bare army count, no units, no cache refresh -
            # would only corrupt the territory, so it is ignored.
            logger.warning(f"[NETWORK] Ignored legacy SIM_BATTLE_RESULT for {data.get('territory')}")

        elif msg_type == MessageType.SIM_HERO_ABILITY:
            # Hero ability used by another player - apply the effect locally
            player_id = data.get('player_id')
            hero_name = data.get('hero_name')
            ability_index = data.get('ability_index')
            ability_name = data.get('ability_name')
            target = data.get('target')  # For targeted abilities
            logger.debug(f"[NETWORK] Received SIM_HERO_ABILITY: Player {player_id} used {hero_name}'s {ability_name}")

            # A client casts only with a Hero of its own, and only that Hero's ability (the
            # host is never refused). Any player's ability, any Hero, was run as sent.
            sender = self._message_sender(message)
            if sender is not None and self.game_state is not None:
                hero = self.game_state.heroes.get(sender, {}).get(hero_name) if player_id == sender else None
                abilities = self.game_state.HERO_TYPES.get(hero_name, {}).get('abilities', [])
                ability_ok = (isinstance(ability_index, int) and 0 <= ability_index < len(abilities)
                              and abilities[ability_index].get('name') == ability_name)
                if not hero or not ability_ok:
                    logger.warning(f"[NETWORK] REJECTED: {ability_name} of {hero_name} from Player "
                                   f"{sender + 1} - not their Hero / not its ability")
                    return

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
                            # The caster's random picks: every PC removes the same units
                            # (each used to roll its own random.sample)
                            self.game_state.execute_decisive_strike(
                                target, player_id, pre_selected_units=data.get('picked_units'))
                        elif ability_name == 'Valorous Charge':
                            self.game_state.execute_valorous_charge(
                                target, player_id, pre_selected_units=data.get('picked_units'))

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
            # Territory ownership assignment from alliance arrival (from the chooser)
            territory = data.get('territory')
            new_owner = data.get('new_owner')
            logger.info(f"[NETWORK] Alliance choice: {territory} assigned to player {new_owner}")

            if self.sim_state is not None and territory:
                pm = self.sim_state.phase_manager
                sender = self._message_sender(message)
                if pm is not None and sender is not None:
                    # A client may choose only for a marker it is the chooser of, and only
                    # one of the allies who took the territory (the host - AI choices, AFK
                    # fallback - is never refused). Any choice from anyone was applied.
                    marker = next((m for m in pm.pending_alliance_markers
                                   if m.get('territory') == territory), None)
                    if (marker is None or marker.get('chooser') != sender
                            or new_owner not in (marker.get('players') or [])):
                        logger.warning(f"[NETWORK] REJECTED: Alliance choice for {territory} from "
                                       f"Player {sender + 1} (marker: {marker})")
                        return
                if pm is not None:
                    # Same as on the chooser's PC: owner + overflow mark (the old handler
                    # set the owner by hand and its overflow check never ran)
                    pm.alliance_handler.assign_territory(territory, new_owner)
                    # Remove this territory's marker (sync with the chooser)
                    pm.pending_alliance_markers = [
                        m for m in pm.pending_alliance_markers
                        if m.get('territory') != territory
                    ]
                    logger.info(f"[NETWORK] Removed alliance marker for {territory}, {len(pm.pending_alliance_markers)} remaining")
                    # Our popup for this territory has nothing left to choose
                    self._close_alliance_choice_popup(territory)

                    # HOST: Complete round if no more battles/markers after client resolved alliance
                    # (only while resolving: a late choice used to end the NEXT round)
                    if self.local_player_index == 0 and self._sim_round_may_end():
                        logger.info(f"[HOST] All conflicts resolved after remote alliance choice, completing round")
                        self.sim_state.complete_round()

                # Remove from alliance arrivals
                if territory in self.sim_state.alliance_arrivals:
                    del self.sim_state.alliance_arrivals[territory]

        elif msg_type == MessageType.SIM_ROUND_COMPLETE:
            # Round finished, start new planning phase (client receives this)
            if self.sim_state is not None and self.local_player_index != 0:
                self._sim_apply_round_complete(data)

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
            elif cancel_type == 'construction':
                # A cancelled construction (sequential mode): refund the owner here too
                territory = data.get('territory')
                plot_index = data.get('plot_index')
                if (territory is not None and plot_index is not None
                        and self.game_state.territory_owners.get(territory) == remote_player_index):
                    self.game_state.cancel_construction(territory, plot_index)
                    logger.info(f"[NETWORK] Player {remote_player_index} cancelled construction in {territory} plot {plot_index}")
                else:
                    logger.warning(f"[NETWORK] ORDER_REMOVE construction cancel rejected: {data}")
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

    def _handle_remote_gold_transfer(self, data: dict, sender=None):
        """Apply a gold transfer that happened on a remote peer.

        The sender has already deducted locally and broadcast the actual
        post-clamp amount, so we mirror the balance change without re-running the
        sender-side rules that depend on timing (the transfer cap). What a transfer can
        never be is checked (Phase 7 of the multiplayer audit) when a client sent it -
        `sender`, the index the server stamped on it (None: the host, trusted): the
        sender's own gold, only in a game with gold transfer on, to an ally, once per pair
        per turn, at most what the sender has. A client could send gold from anyone to
        anyone (an enemy's gold to itself), even in games without gold transfer.
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

        tracker = (self.sim_state.gold_transfers_this_round
                   if self.sim_state is not None
                   else self.game_state.gold_transfers_this_turn)
        if sender is not None:
            gs = self.game_state
            refusal = None
            if sender_idx != sender:
                refusal = f"sent as Player {sender_idx + 1}"
            elif getattr(gs, 'gold_transfer_pct', 0) <= 0:
                refusal = "gold transfer is off in this game"
            elif recipient_idx == sender_idx or not gs.are_allies(sender_idx, recipient_idx):
                refusal = "the recipient is not an ally"
            elif recipient_idx in gs.eliminated_players:
                refusal = "the recipient is out of the game"
            elif (sender_idx, recipient_idx) in tracker:
                refusal = "already sent to this player this turn"
            if refusal:
                logger.warning(f"[NETWORK] REJECTED: GOLD_TRANSFER from Player {sender + 1}: {refusal}")
                return
            # Never more than the sender has
            amount = min(amount, max(0, gs.player_gold[sender_idx]))
            if amount <= 0:
                logger.warning(f"[NETWORK] REJECTED: GOLD_TRANSFER from Player {sender + 1}: no gold")
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
        tracker.add((sender_idx, recipient_idx))

        # Action log parity — remote peers log the transfer too so everyone sees it.
        sender_name = self.game_state.get_player_name(sender_idx)
        recipient_name = self.game_state.get_player_name(recipient_idx)
        self.game_state.add_message(f"{sender_name} sent {amount}g to {recipient_name}.")

        logger.info(f"[NETWORK] Applied remote GOLD_TRANSFER: {sender_idx} -> {recipient_idx} for {amount}g")

    # ========== SEQUENTIAL MODE: THE TURN OWNER IS THE TRUTH ==========
    # The PC whose player is taking the turn plays it; every other PC replays it:
    #   EXECUTE_ORDERS{snapshot}  the owner's state as its planned moves set off
    #                             (moves included) - apply it, run the same moves
    #   BATTLE_RESOLVE            each battle, replayed from the owner's seed
    #   TURN_END{snapshot}        the owner's state after the turn advanced - apply it
    #                             and start the next turn from it
    # Receivers never advance a turn on their own (GameState.may_advance_turn). This
    # replaces the host's FULL_STATE_SYNC, which was sent before the host's own moves ran
    # and applied whenever it arrived (C5), the turn-start UNIT_COMPLETE /
    # BUILDING_COMPLETE messages (duplicate units, H1) and STATE_CHECKSUM.

    def _handle_remote_execute_orders(self, data):
        """
        Sequential multiplayer: the turn owner pressed End Turn (or its planning timer ran
        out) with planned moves. Take its state - every action of its turn so far, the
        moves included - and run the same moves here, so the same armies arrive and the
        same battles appear on every PC. (Older senders: the bare order list.)
        """
        gs = self.game_state
        snapshot = data.get('snapshot')
        if snapshot:
            from network.state_snapshot import apply_snapshot
            self._report_snapshot_divergence(snapshot, "when their moves began")
            apply_snapshot(gs, snapshot)
        else:
            for order_data in data.get('orders', []):
                from_territory = order_data.get('from_territory')
                to_territory = order_data.get('to_territory')
                unit_ids = order_data.get('unit_ids', [])
                if unit_ids:
                    gs.add_movement_order_for_units(from_territory, to_territory, unit_ids)
                else:
                    gs.add_movement_order(from_territory, to_territory)
        logger.info(f"[NETWORK] Player {data.get('player_index')} executes {len(gs.movement_orders)} orders")
        if gs.movement_orders:
            # Same as on the owner's PC: animations, then arrivals and battles (this PC
            # does not advance the turn afterwards - the owner's TURN_END does)
            gs.execute_all_orders()

    def _handle_remote_turn_end(self, message, allow_hold=True):
        """
        Sequential multiplayer: another player's turn ended. TURN_END carries the turn
        owner's state after the turn advanced: take it, then start the new turn here (the
        announcement, whose end runs the turn-start effects - the same on every PC).

        Waits while this PC still replays the owner's moves, so armies are not cut off
        mid-march. This PC never advances on its own: it used to advance from its own
        replay AND from TURN_END (a skipped turn), on top of a stale host sync.
        """
        gs = self.game_state
        data = message.get('data', {})
        if self.sim_state is not None:
            return  # simultaneous mode plays rounds, not turns
        if allow_hold and self._battles_may_still_appear():
            self._hold_network_message(message)
            return
        snapshot = data.get('snapshot')
        if snapshot:
            from network.state_snapshot import apply_snapshot
            apply_snapshot(gs, snapshot)
            # The rest of a turn advance (selection, logs, the announcement)
            gs._after_turn_advance()
        else:
            # Older sender without a snapshot: advance here
            gs._advance_to_next_player()
        logger.info(f"[NETWORK] Player {data.get('player_index')} ended their turn - now Player "
                    f"{gs.current_player + 1}'s turn {gs.turn_number} ({gs.phase})")
        sync_logger = getattr(gs, 'sync_logger', None)
        if sync_logger:
            sync_logger.record_turn_snapshot(gs.turn_number)

    def _report_snapshot_divergence(self, snapshot, context):
        """
        Desync diagnostics: this PC's state should equal the turn owner's snapshot that is
        about to replace it. Differences are logged (and recorded by the sync logger,
        which used to rely on STATE_CHECKSUM); the snapshot corrects them either way.
        """
        try:
            import json
            from network.state_snapshot import build_snapshot
            from sync_logger import SyncLogger
            local = json.loads(json.dumps(build_snapshot(self.game_state)))
            diff = SyncLogger.compute_state_diff(snapshot, local)
        except Exception as exc:  # diagnostics only - never block the game
            logger.warning(f"[SYNC] Could not compare with the turn owner's state: {exc}")
            return
        if not diff:
            return
        logger.warning(f"[SYNC] This PC's state differed from the turn owner's {context}: "
                       f"{len(diff)} fields ({', '.join(list(diff)[:5])}) - corrected")
        sync_logger = getattr(self.game_state, 'sync_logger', None)
        if sync_logger:
            sync_logger.record_desync(self.game_state.turn_number, diff)

    def _send_action_to_remote(self, action_type: str, data: dict):
        """
        Send an action to the remote player.

        Safe from any thread: a call from another thread (the sequential AI's turn on the
        host) is queued and sent by the main loop; a main-thread send first sends what
        other threads queued, so messages leave in the order things happened.

        Args:
            action_type: Type of action (e.g., MessageType.MOVEMENT_ORDER)
            data: Action data dict
        """
        if not self.network_connection:
            return
        if threading.current_thread() is not threading.main_thread():
            self._outgoing_from_threads.append((action_type, data))
            return
        self._flush_thread_messages()
        self._send_now(action_type, data)

    def _flush_thread_messages(self):
        """Main thread: send the messages other threads queued, in order."""
        while self._outgoing_from_threads:
            action_type, data = self._outgoing_from_threads.popleft()
            self._send_now(action_type, data)

    @staticmethod
    def _payload_for_log(data):
        """The message data for a log line - a state snapshot (~80 KB) is summarised.
        Logging it whole wrote it to the log file and console twice per turn."""
        if isinstance(data, dict) and 'snapshot' in data:
            return {key: ('<state snapshot>' if key == 'snapshot' else value)
                    for key, value in data.items()}
        return data

    def _send_now(self, action_type: str, data: dict):
        """Encode and send one message (main thread only - see _send_action_to_remote)."""
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
        logger.info(f"[NETWORK] Sent {action_type} (seq={current_seq}): {self._payload_for_log(data)}")

    # ========== SIMULTANEOUS MODE NETWORK HELPERS ==========

    def _sim_start_execution_phase(self):
        """
        Host starts the execution phase when all players are ready (main loop, via
        sim_state.check_deferred_execution).

        The host is the single source of truth for the round:
        1. crossing conflicts are resolved (forced defenders keep their armies home),
        2. every order is validated and all NON-movement orders are applied here
           (builds, training, research, castle upgrades, demolitions, hero abilities,
           hero training - remote players' included),
        3. SIM_ALL_READY carries a snapshot of that state plus the validated movement
           orders; clients apply the snapshot and run exactly those movements,
        4. the host starts the same movements.
        Every PC therefore has the same armies on the same roads, and detects the same
        arrivals and battles. (Clients used to run the raw merged order list on their own
        state, including orders the host rejected.)
        """
        if self.sim_state is None or self.sim_state.phase_manager is None:
            return
        pm = self.sim_state.phase_manager

        # Step 1: Detect crossing conflicts BEFORE anything executes
        forced_defenders = []
        resolved_orders = dict(self.sim_state.player_orders)  # Copy for modification
        if pm.conflict_resolver:
            resolver = pm.conflict_resolver
            crossing_conflicts = resolver.detect_crossing_conflicts(self.sim_state.player_orders)
            resolved_orders = resolver.resolve_crossing_conflicts(
                self.sim_state.player_orders, crossing_conflicts
            )
            forced_defenders = resolver.get_forced_defenders()

        # Step 2: validate + apply the non-movement orders on the host
        movement_orders = pm.begin_authoritative_execution(resolved_orders)
        self.sim_state.merged_orders = movement_orders
        logger.info(f"[SIM] Starting execution phase with {len(movement_orders)} movement orders")

        # Step 3: the clients get the resulting state + the movement to run
        if self.multiplayer_mode:
            from network.state_snapshot import build_snapshot
            self._send_action_to_remote(MessageType.SIM_ALL_READY, {
                'round': self.sim_state.round_number,
                'snapshot': build_snapshot(self.game_state),
                'movement_orders': movement_orders,
                'forced_defenders': [
                    {'player_id': fd.get('player_id'), 'territory': fd.get('territory'),
                     'intended_target': fd.get('intended_target'), 'forced_by': fd.get('forced_by')}
                    for fd in forced_defenders
                ]
            })

        # Process forced defenders for host (host doesn't receive SIM_ALL_READY)
        local_player = self.get_local_player()
        for fd in forced_defenders:
            if fd.get('player_id') == local_player:
                fd_territory = fd.get('territory')
                fd_target = fd.get('intended_target')
                logger.info(f"[SIM] Host forced to defend in {fd_territory} (was attacking {fd_target})")
                self._queue_forced_defend_popup(fd_territory, fd_target)

        # Step 4: the armies set off (with no movement the arrivals run at once)
        pm._execute_movement_orders(movement_orders)

    def _sim_apply_round_complete(self, data):
        """
        Client: the host finished the round (SIM_ROUND_COMPLETE). Nothing of the old
        round may linger here - an open battle window, battles or alliance markers this
        PC still showed (they used to stay forever when the states had drifted) - and the
        new round starts from the host's state.
        """
        round_number = data.get('round_number', self.sim_state.round_number + 1)
        logger.info(f"[NETWORK] Round {round_number} complete - starting new planning phase")
        gs = self.game_state
        pm = self.sim_state.phase_manager

        # The old round is over everywhere
        self._close_battle_window()
        self.alliance_choice_popup_visible = False
        if pm is not None:
            pm.pending_battles = []
            pm.pending_alliance_markers = []
            pm._sim_pending_arrivals = []
        gs.movement_orders.clear()
        for orders in self.sim_state.player_orders.values():
            orders.clear()

        # This PC's own round-end bookkeeping - for its Action Log (income lines,
        # finished buildings and research). Every value it produces is replaced by the
        # host's snapshot below. (Training is NOT run here: the host's snapshot already
        # holds the new units, and finishing it twice would duplicate them.)
        original_player = gs.current_player
        try:
            for player_id in range(gs.num_players):
                if player_id not in self.sim_state.eliminated_players:
                    gs.collect_income(player_id)
                    gs.current_player = player_id
                    gs.finish_constructions()
                    gs.finish_research()
                    gs.finish_castle_upgrades()
                    gs._tick_building_xp()
                    gs._tick_training_grounds_xp()
        finally:
            gs.current_player = original_player

        # New planning phase BEFORE the snapshot: start_planning_phase() resets 'moved'
        # units to 'ready', and the snapshot's statuses (new units 'moved') must win
        self.sim_state.round_number = round_number
        self.sim_state.start_planning_phase()

        snapshot = data.get('snapshot')
        if snapshot:
            from network.state_snapshot import apply_snapshot
            apply_snapshot(gs, snapshot)
            # current_player is per PC in simultaneous mode (the snapshot has the host's)
            gs.current_player = self.get_local_player()
        # sim_state keeps a LIST (eliminate_player() appends; a set crashed it)
        self.sim_state.eliminated_players = list(dict.fromkeys(data.get('eliminated_players') or []))
        for player_id in self.sim_state.eliminated_players:
            self.sim_state.players_ready[player_id] = True  # no longer participates
        self.sim_state.overflow_territories = dict(data.get('overflow_territories') or {})
        logger.info(f"[NETWORK] Client round complete processing done")

    def _sim_apply_all_ready(self, data):
        """
        Client: the host started the round's execution (SIM_ALL_READY). Take over its
        state - every player's builds, training, research and abilities already applied
        - and run exactly the movement orders it validated.
        """
        if self.sim_state is None or self.sim_state.phase_manager is None:
            return
        pm = self.sim_state.phase_manager
        snapshot = data.get('snapshot')
        movement_orders = data.get('movement_orders') or []
        logger.info(f"[NETWORK] All players ready - executing {len(movement_orders)} movement orders")

        # Forced defenders - queue popup if local player was forced to defend
        for fd in data.get('forced_defenders') or []:
            if fd.get('player_id') == self.local_player_index:
                logger.info(f"[NETWORK] Forced to defend in {fd.get('territory')} (was attacking {fd.get('intended_target')})")
                # Queue popup notification (will show one at a time with auto-close)
                self._queue_forced_defend_popup(fd.get('territory'), fd.get('intended_target'))

        if snapshot:
            from network.state_snapshot import apply_snapshot
            apply_snapshot(self.game_state, snapshot)
            # Simultaneous mode: current_player is per PC - always the local player (the
            # UI acts for it). The host's snapshot carries the HOST's.
            self.game_state.current_player = self.get_local_player()

        self.sim_state.merged_orders = movement_orders
        self.sim_state.sim_phase = 'executing'
        # Reset phase_manager state for this execution (animation completion callback)
        pm.execution_complete = False
        pm.animations_complete = False
        pm._sim_pending_arrivals = []
        pm._execute_movement_orders(movement_orders)

    def _sim_broadcast_round_complete(self, round_number: int):
        """
        Host broadcasts round completion to all clients.

        Called via callback from sim_state.complete_round() when the round finishes
        (after all battles and alliance markers are resolved), so the state is the new
        round's: income collected, buildings / research / training finished.

        Carries a full game state snapshot (network/state_snapshot.py) plus the
        simultaneous-mode round data. It replaces a hand-maintained field list that
        kept missing fields (turn number, tech limits, Captain discount, stats ...).

        Args:
            round_number: The new round number after completion
        """
        if not self.multiplayer_mode or self.local_player_index != 0:
            return

        logger.info(f"[HOST] Broadcasting SIM_ROUND_COMPLETE (round {round_number})")
        from network.state_snapshot import build_snapshot
        self._send_action_to_remote(MessageType.SIM_ROUND_COMPLETE, {
            'round_number': round_number,
            'snapshot': build_snapshot(self.game_state),
            # sim_state round data (not part of GameState)
            'eliminated_players': list(self.sim_state.eliminated_players) if self.sim_state else [],
            'overflow_territories': dict(self.sim_state.overflow_territories) if self.sim_state else {},
        })

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

    # ========== SIMULTANEOUS MODE: PER-FRAME UPDATE ==========
    # The main loop's simultaneous-mode work in one place: Game.run() calls
    # _update_simultaneous() every frame, and the multiplayer test harness calls the
    # same method (so tests run this exact code, not a copy).

    # Multiplayer AFK rules for the resolving phase (owner decision 2026-10-10): a
    # resolver who has not touched their battles for this long gets them resolved on
    # their own PC...
    SIM_AFK_RESOLVE_SECONDS = 90.0
    # ...and after this long the host settles whatever is still open (a player who is
    # away, frozen or stuck) so the round can never stall
    SIM_HOST_FALLBACK_SECONDS = 180.0
    # How long an AI resolver / chooser waits before acting (its grey marker shows meanwhile)
    SIM_AI_ACTION_DELAY = 2.0

    def _update_simultaneous(self, delta_time):
        """One frame of simultaneous-mode bookkeeping (see the comment above)."""
        sim = self.sim_state
        if sim is None:
            return
        # Execution deferred by mark_ready() (AI planning thread, or the multiplayer host,
        # which always starts it here) - before the timer checks so it starts promptly
        sim.check_deferred_execution()
        if self.is_game_paused:
            return
        if sim.sim_phase == 'planning':
            self._update_sim_planning_timers(delta_time)
        self._sim_broadcast_ready_state()
        self._auto_resolve_ai_battle(delta_time)
        self._auto_resolve_ai_alliance_marker(delta_time)
        self._sim_afk_watchdog()
        self._sim_check_new_round()

    def _update_sim_planning_timers(self, delta_time):
        """Planning timers: the local player's timer running out readies them (with their
        planned moves); the host also keeps the clients' timer displays in step."""
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
                self._sim_queue_local_movement_orders(local_player)

        # Now update timers — mark_ready() will be called, but orders are already saved
        self.sim_state.update_timers(delta_time)

        # Check if local player just became ready due to timer expiration
        is_ready_now = self.sim_state.players_ready.get(local_player, False)
        if not was_ready and is_ready_now:
            # Without this the host never receives a client's orders on timer expiry
            self._sim_send_local_ready(local_player, "Timer expired")

        # MULTIPLAYER: Host sends periodic timer sync to client (every 2 seconds)
        if self.multiplayer_mode and self.local_player_index == 0:
            if self._sim_last_timer_sync is None:
                self._sim_last_timer_sync = 0
            self._sim_last_timer_sync += delta_time
            if self._sim_last_timer_sync >= 2.0:
                self._sim_send_timer_update()
                self._sim_last_timer_sync = 0

    def _sim_queue_local_movement_orders(self, local_player):
        """
        Turn the local player's planned moves (game_state.movement_orders, drawn as
        arrows) into simultaneous-mode orders and clear them. End Turn and the planning
        timer both do this before marking the player ready - add_order() refuses orders
        after that.
        """
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

        # Reset the units' statuses before clearing the orders (they move at execution)
        for order in self.game_state.movement_orders:
            if hasattr(order, 'unit_ids') and order.unit_ids:
                garrison = self.game_state.territory_garrisons.get(order.from_territory, {}).get(local_player)
                if garrison and 'units' in garrison:
                    for unit in garrison['units']:
                        if unit.get('id') in order.unit_ids:
                            unit['status'] = 'ready'
                            unit['order'] = None
        self.game_state.movement_orders.clear()

    def _sim_send_local_ready(self, local_player, reason):
        """
        Client: tell the host we are ready and hand over this round's orders
        (SIM_PLAYER_READY). The host sends nothing - its readiness reaches the clients in
        SIM_READY_STATE, and its own SIM_PLAYER_READY could arrive after the round it
        belonged to had already ended.
        """
        if not self.multiplayer_mode or self.local_player_index == 0:
            return
        orders_to_send = list(self.sim_state.player_orders.get(local_player, []))
        self._send_action_to_remote(MessageType.SIM_PLAYER_READY, {
            'player_id': local_player,
            'orders': orders_to_send
        })
        logger.info(f"[SIM] {reason} - sent ready signal with {len(orders_to_send)} orders")

    def _sim_broadcast_ready_state(self):
        """
        Host: send SIM_READY_STATE whenever the set of ready players changes, so every
        client's "Waiting for: ..." list is right. Compared every frame on the main
        thread, so readiness set by an AI planning thread is reported too.
        """
        if not (self.multiplayer_mode and self.local_player_index == 0):
            return
        sim = self.sim_state
        if sim.sim_phase != 'planning':
            return
        state = (sim.round_number,
                 tuple(sorted(pid for pid, ready in sim.players_ready.items() if ready)))
        if state == self._sim_last_ready_state:
            return
        self._sim_last_ready_state = state
        self._send_action_to_remote(MessageType.SIM_READY_STATE, {
            'round': state[0],
            'ready': list(state[1]),
        })

    def _sim_round_may_end(self):
        """
        Simultaneous mode, on the PC that ends rounds (host / single-player): is nothing
        of this round left? No battle, no alliance choice - and no battle report of ours
        still open. Our own battle's result goes out (and its alliance marker is queued)
        only when its report window closes (_finalize_enhanced_battle, which then ends the
        round itself); ending the round under an open report lost that choice and left a
        stale marker in the next round. Outside the resolving phase there is nothing to
        end (a late message used to end the NEXT round).
        """
        sim = self.sim_state
        if sim is None or sim.sim_phase != 'resolving':
            return False
        pm = sim.phase_manager
        return (not self.game_state.pending_battles
                and not (pm is not None and pm.pending_alliance_markers)
                and self._resolved_battle_info is None)

    def _close_alliance_choice_popup(self, territory):
        """The alliance choice for `territory` was made elsewhere (by the host, or its
        chooser on another PC): close our popup for it, nothing is left to choose."""
        if (getattr(self, 'alliance_choice_popup_visible', False)
                and getattr(self, 'alliance_choice_territory', None) == territory):
            self.alliance_choice_popup_visible = False

    def _is_ai_slot(self, player):
        """A real player slot the AI controls (incl. a taken-over human)."""
        return (player is not None and 0 <= player < self.game_state.num_players
                and bool(self.game_state.player_is_ai[player]))

    def _auto_resolve_ai_battle(self, delta_time):
        """
        Resolve a battle whose resolver is an AI, after a short delay (its grey marker
        shows meanwhile). Host / single-player only: clients get the result from the
        host - they used to resolve AI battles themselves, with their own dice.
        """
        if self.multiplayer_mode and self.local_player_index != 0:
            return
        sim = self.sim_state
        battles = self.game_state.pending_battles
        if not (sim.sim_phase == 'resolving' and battles and self.enhanced_battle_ui is None):
            return  # (also: never while a battle window is open)
        # The first battle with an AI resolver - not just battle #1, which may be a human's
        index = next((i for i, b in enumerate(battles)
                      if self._is_ai_slot(getattr(b, 'resolver', None))), None)
        if index is None:
            # Not an AI battle, reset the timer tracking
            if self._ai_battle_delay_timer is not None:
                self._ai_battle_delay_timer = 0.0
                self._ai_battle_territory = None
            return

        next_battle = battles[index]
        resolver = next_battle.resolver
        # Track when this AI battle was first detected (for the delay)
        if self._ai_battle_delay_timer is None:
            self._ai_battle_delay_timer = 0.0
            self._ai_battle_territory = next_battle.territory
            logger.info(f"[SIM] AI battle detected at {next_battle.territory} - showing grey marker for {self.SIM_AI_ACTION_DELAY}s")
        if self._ai_battle_territory != next_battle.territory:
            # New battle, reset timer
            self._ai_battle_delay_timer = 0.0
            self._ai_battle_territory = next_battle.territory
            logger.info(f"[SIM] New AI battle detected at {next_battle.territory} - resetting timer")
        self._ai_battle_delay_timer += delta_time
        if self._ai_battle_delay_timer < self.SIM_AI_ACTION_DELAY:
            return

        logger.info(f"[SIM] Auto-resolving battle at {next_battle.territory} - AI player {resolver} is resolver")
        # Reset timer for next battle
        self._ai_battle_delay_timer = 0.0
        self._ai_battle_territory = None

        # Multiplayer: seeded, so the clients replay it
        battle, battle_seed = self._resolve_battle_locally(index)
        territory = battle.territory
        # Clear sequential mode flag - sim mode uses complete_round() instead
        self.game_state.ready_to_advance_turn = False

        # Check for alliance marker (allied victory, shared rule)
        alliance_marker = self._alliance_marker_for(battle, territory)
        if alliance_marker:
            sim.phase_manager.pending_alliance_markers.append(alliance_marker)
            logger.info(f"[SIM] AI battle created alliance marker, chooser: {alliance_marker['chooser']}")

        # MULTIPLAYER: Send battle result to clients (seed + outcome)
        if self.multiplayer_mode:
            self._send_action_to_remote(MessageType.BATTLE_RESOLVE, self._battle_resolve_payload(
                battle, territory, battle_seed, alliance_marker,
                self.game_state.last_battle_reports))
            logger.info(f"[HOST] Broadcast AI battle result: {territory} -> "
                        f"player {self.game_state.territory_owners.get(territory, -1)}")

        # Capital Assault: sync battle-based eliminations to sim_state
        self._sync_battle_eliminations_to_sim("after AI battle")

        # Check if all battles resolved
        if not self.game_state.pending_battles:
            logger.info(f"[SIM] All battles resolved. Alliance markers: {len(sim.phase_manager.pending_alliance_markers)}")
            if self._sim_round_may_end():
                sim.complete_round()

    def _auto_resolve_ai_alliance_marker(self, delta_time):
        """
        Allied capture whose chooser is an AI: pick the new owner after a short delay.
        Host / single-player only (clients get SIM_ALLIANCE_CHOICE; they used to pick
        their own owner with their own random tie-break).
        """
        if self.multiplayer_mode and self.local_player_index != 0:
            return
        sim = self.sim_state
        markers = sim.phase_manager.pending_alliance_markers if sim.phase_manager else []
        if not (sim.sim_phase == 'resolving' and not self.game_state.pending_battles and markers
                and not getattr(self, 'alliance_choice_popup_visible', False)):
            return
        index = next((i for i, m in enumerate(markers) if self._is_ai_slot(m.get('chooser'))), None)
        if index is None:
            # Not an AI alliance marker, reset the timer tracking
            if self._ai_alliance_delay_timer is not None:
                self._ai_alliance_delay_timer = 0.0
                self._ai_alliance_territory = None
            return

        next_marker = markers[index]
        if self._ai_alliance_delay_timer is None:
            self._ai_alliance_delay_timer = 0.0
            self._ai_alliance_territory = next_marker['territory']
            logger.info(f"[SIM] AI alliance marker detected at {next_marker['territory']} - showing grey marker for {self.SIM_AI_ACTION_DELAY}s")
        if self._ai_alliance_territory != next_marker['territory']:
            # New marker, reset timer
            self._ai_alliance_delay_timer = 0.0
            self._ai_alliance_territory = next_marker['territory']
            logger.info(f"[SIM] New AI alliance marker detected at {next_marker['territory']} - resetting timer")
        self._ai_alliance_delay_timer += delta_time
        if self._ai_alliance_delay_timer < self.SIM_AI_ACTION_DELAY:
            return

        # Reset timer for next marker
        self._ai_alliance_delay_timer = 0.0
        self._ai_alliance_territory = None
        self._auto_choose_alliance_owner(index, f"AI player {next_marker.get('chooser')} is chooser")

    def _auto_choose_alliance_owner(self, marker_index, reason):
        """
        Give an allied capture to the ally with the fewest territories (ties at random)
        - the AI chooser's rule, also used when the host settles an absent player's
        choice. Multiplayer host: SIM_ALLIANCE_CHOICE goes out BEFORE the round can end,
        so clients never see the round end before the choice.
        """
        pm = self.sim_state.phase_manager
        marker = pm.pending_alliance_markers[marker_index]
        territory = marker['territory']
        allied_players = marker['players']
        logger.info(f"[SIM] Auto-resolving alliance marker at {territory} - {reason}")

        # AI logic: Choose player with least territories; if tied, random
        territory_counts = {}
        for player_id in allied_players:
            count = sum(1 for t, owner in self.game_state.territory_owners.items() if owner == player_id)
            territory_counts[player_id] = count
        min_territories = min(territory_counts.values())
        candidates = [p for p, c in territory_counts.items() if c == min_territories]
        chosen_owner = random.choice(candidates)
        logger.info(f"[SIM] Chose player {chosen_owner} (had {territory_counts[chosen_owner]} territories, candidates: {candidates})")

        # MULTIPLAYER: Broadcast alliance choice to clients
        if self.multiplayer_mode and self.local_player_index == 0:
            self._send_action_to_remote(MessageType.SIM_ALLIANCE_CHOICE, {
                'territory': territory,
                'new_owner': chosen_owner
            })
            logger.info(f"[HOST] Broadcast SIM_ALLIANCE_CHOICE: {territory} -> player {chosen_owner}")

        # Assign territory and remove this marker from pending
        pm.alliance_handler.assign_territory(territory, chosen_owner)
        pm.pending_alliance_markers.pop(marker_index)
        # The host settling its own choice: its popup has nothing left to choose
        self._close_alliance_choice_popup(territory)

        # Check if all alliance markers resolved
        if self._sim_round_may_end():
            logger.info(f"[SIM] All alliance markers resolved. Completing round.")
            self.sim_state.complete_round()

    def _sim_afk_watchdog(self):
        """
        Multiplayer AFK rules for the resolving phase, so a round never waits forever:
        - after SIM_AFK_RESOLVE_SECONDS without the local player touching a battle, this
          PC resolves the battles (and alliance choices) that are theirs;
        - a battle report left open that long after FIGHT is closed: the battle's result
          goes out only when its window closes, so it held up the whole round;
        - after SIM_HOST_FALLBACK_SECONDS of resolving, the host settles every battle and
          choice still open (an absent, frozen or stuck player's).
        Single-player has nobody to wait for, so it never auto-resolves.
        """
        if not self.multiplayer_mode:
            return
        sim = self.sim_state
        now = time.monotonic()
        if sim.sim_phase != 'resolving':
            self._sim_resolving_since = None
            return
        if self._sim_resolving_since is None:
            self._sim_resolving_since = now
            self._sim_local_battle_activity = now
        info = self._resolved_battle_info
        if (info is not None and self.enhanced_battle_ui is not None
                and now - info.get('fought_at', now) >= self.SIM_AFK_RESOLVE_SECONDS):
            logger.info(f"[SIM] Battle report for {info.get('territory')} left open - closing it")
            self._finalize_enhanced_battle()
            self._sim_local_battle_activity = now
            return
        # A battle window still waiting for FIGHT whose battle was settled meanwhile (the
        # host's fallback below, replayed here) has nothing left to fight
        self._close_stale_battle_window()
        if (self.enhanced_battle_ui is not None or self.battle_popup_visible
                or getattr(self, 'alliance_choice_popup_visible', False)):
            # Busy with a battle / a choice - not idle
            self._sim_local_battle_activity = now

        local = self.get_local_player()
        battles = self.game_state.pending_battles
        markers = sim.phase_manager.pending_alliance_markers if sim.phase_manager else []
        idle = now - self._sim_local_battle_activity
        if idle >= self.SIM_AFK_RESOLVE_SECONDS:
            if any(getattr(b, 'resolver', None) == local for b in battles):
                logger.info(f"[SIM] Player {local} idle {idle:.0f}s - resolving their battles")
                self._sim_local_battle_activity = now
                self._resolve_all_pending_battles()
                return
            mine = next((i for i, m in enumerate(markers) if m.get('chooser') == local), None)
            if mine is not None and not battles:
                self._sim_local_battle_activity = now
                if self.local_player_index == 0:
                    self._auto_choose_alliance_owner(mine, f"player {local} idle")
                else:
                    # A client's choice goes through the normal path (assign + send)
                    marker = markers[mine]
                    owner = min(marker['players'], key=lambda p: (
                        sum(1 for o in self.game_state.territory_owners.values() if o == p), p))
                    self._send_action_to_remote(MessageType.SIM_ALLIANCE_CHOICE, {
                        'territory': marker['territory'], 'new_owner': owner})
                    sim.phase_manager.resolve_alliance_marker(marker['territory'], owner)
                return

        if self.local_player_index == 0 and now - self._sim_resolving_since >= self.SIM_HOST_FALLBACK_SECONDS:
            # Every battle / choice still open - the host's own too (a window left open
            # counts as "busy" above, so the idle rule never covers a host who walked away
            # from one). The round itself still waits for a battle report of ours that is
            # open (_sim_round_may_end); that one closes by the rule above.
            if battles:
                logger.warning(f"[HOST] Resolving phase open {now - self._sim_resolving_since:.0f}s - "
                               f"settling the remaining battles")
                self._resolve_all_pending_battles(any_resolver=True)
                self._close_stale_battle_window()
            elif markers:
                logger.warning("[HOST] Settling a pending alliance choice")
                self._auto_choose_alliance_owner(0, "host fallback")

    def _close_stale_battle_window(self):
        """A battle window still before FIGHT whose battle is no longer pending (resolved
        by the AFK rules or by another PC): close it. FIGHT would close it anyway (see
        handle_battle_popup_click) - this just doesn't leave it on screen until then."""
        if (self.enhanced_battle_ui is not None and self._resolved_battle_info is None
                and self._selected_battle_current_index() is None):
            logger.info(f"[BATTLE] Battle at {self.selected_battle_territory} was settled meanwhile - "
                        f"closing the battle window")
            self._close_battle_window()

    def _sim_check_new_round(self):
        """A new round started: "Turn N" announcement, and the AI starts planning."""
        if self.last_sim_round is None or self.game_state.phase == 'ended':
            return  # no new rounds after victory/defeat
        current_round = self.sim_state.round_number
        if current_round == self.last_sim_round:
            return
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

        # Trigger AI planning for the new round (host / single-player only - clients
        # have no sim_ai)
        if self.sim_ai is not None and self.sim_state.sim_phase == 'planning':
            logger.info(f"[SIMULTANEOUS] Triggering AI planning for round {current_round}")
            self.sim_ai.start_planning_phase()

    def _take_over_disconnected_player(self, player_index):
        """
        A player left a running game: the AI plays their empire from now on, at Medium
        (owner decision). Every PC marks the slot as AI; the host also gives the slot an
        AIPlayer and, in a simultaneous planning phase, lets it plan this round. In the
        resolving phase their battles / choices are picked up by the AI auto-resolve.
        Sequential mode: the host plays computer players' turns, and finishes the current
        turn for them if it was theirs (_continue_turn_as_ai).
        """
        gs = self.game_state
        if not (0 <= player_index < gs.num_players):
            return
        # The action XP they had earned themselves - a win against an empire whose player
        # left at once must not count (player_level._is_disconnect_farming)
        if not gs.player_is_ai[player_index] and player_index not in gs.ai_takeover_xp:
            gs.ai_takeover_xp[player_index] = gs.player_stats.get(player_index, {}).get('xp_earned', 0)
        gs.player_is_ai[player_index] = True
        gs.player_ai_difficulty[player_index] = 1  # Medium
        if (self.sim_state is None and self.local_player_index == 0
                and gs.phase == 'playing' and gs.current_player == player_index):
            self._continue_turn_as_ai(player_index)
        sim = self.sim_state
        if sim is not None and self.sim_ai is not None and self.local_player_index == 0:
            self.sim_ai.ensure_player(player_index, 1)
            if sim.sim_phase == 'planning' and not sim.players_ready.get(player_index, False):
                # Their orders never reached us (they travel with SIM_PLAYER_READY)
                sim.player_orders[player_index] = []
                self.sim_ai.ai_ready[player_index] = False
                self.sim_ai._start_ai_planning(player_index)
                logger.info(f"[HOST] AI took over Player {player_index + 1} - planning their round")

    def _continue_turn_as_ai(self, player):
        """
        Host, sequential mode: `player` left during their own turn - finish it for them as
        the AI. Their turn would otherwise never end: every PC waited for their TURN_END.
        - turn announcement still running: the AI starts when it ends (as any AI turn);
        - planning: their planned moves are dropped (they would be mixed with the AI's) and
          the AI plays the turn;
        - their moves were under way: once our replay of them has finished, the turn ends
          here (still running: _process_arrivals ends it - the host owns the turn now);
        - battles: what is left is fought here, then the turn ends.
        """
        gs = self.game_state
        logger.info(f"[HOST] Player {player + 1} left during their turn ({gs.turn_phase}) - the AI finishes it")
        if gs.turn_announcement_active:
            return
        if gs.turn_phase == 'planning':
            gs.cancel_all_orders(player=player)
            self.handle_ai_turn()
        elif gs.turn_phase == 'execution':
            if not (gs.active_animations or gs.pending_arrivals):
                gs._advance_to_next_player()
        elif gs.turn_phase == 'battles':
            # Seeded and sent like any battle, then the turn advances (TURN_END)
            self._resolve_all_pending_battles()

    # ========== SEQUENTIAL MODE: TURN OWNERSHIP ==========

    # Sequential multiplayer AFK rules for the turn owner's battles (the other players
    # wait for them): untouched this long -> resolved on the owner's PC; a battle report
    # left open this long after FIGHT closes...
    SEQ_AFK_RESOLVE_SECONDS = 90.0
    # ...and after this long in the battles phase everything still open is resolved,
    # even with a battle window open (a player who walked away from one)
    SEQ_BATTLE_FALLBACK_SECONDS = 180.0

    def _is_turn_owner_of(self, player):
        """
        Sequential multiplayer: does this PC play `player`'s turns? A human player's own
        PC; the HOST for computer players (lobby AI slots, and empires the AI took over
        when their player left). The owner advances the turn and sends its result; every
        other PC replays it and waits for TURN_END. Single-player / simultaneous: always.
        (AI turns used to run on every PC, each with its own random choices - C1.)
        """
        if not self.multiplayer_mode or self.sim_state is not None:
            return True
        gs = self.game_state
        if player is None or not (0 <= player < gs.num_players):
            return False
        if gs.player_is_ai[player]:
            return self.local_player_index == 0
        return player == self.local_player_index

    def _owns_current_turn(self):
        """Does this PC play the current turn (GameState.turn_advance_gate)? See
        _is_turn_owner_of()."""
        return self._is_turn_owner_of(self.game_state.current_player)

    def _ai_turn_running(self):
        """The current player's AI is still playing its turn here (on its worker thread)."""
        ai = self.ai_players.get(self.game_state.current_player) if self.ai_players else None
        return bool(ai is not None and getattr(ai, 'turn_in_progress', False))

    def _on_turn_advanced(self, previous_player):
        """
        GameState hook (_advance_to_next_player): a turn just ended on this PC. If this PC
        played it - our own turn, or a computer player's on the host - the other PCs get
        its result: TURN_END with the state snapshot, sent only now that the turn has
        really ended (moves arrived, battles fought). They apply it and start the next
        turn from it. May run on the AI's worker thread: the snapshot is taken now, the
        send is queued for the main loop (_send_action_to_remote).
        """
        if not (self.multiplayer_mode and self.sim_state is None
                and self._is_turn_owner_of(previous_player)):
            return
        from network.state_snapshot import build_snapshot
        self._send_action_to_remote(MessageType.TURN_END, {
            'player_index': previous_player,
            'snapshot': build_snapshot(self.game_state),
        })
        sync_logger = getattr(self.game_state, 'sync_logger', None)
        if sync_logger:
            sync_logger.record_turn_snapshot(self.game_state.turn_number)

    def _on_orders_executing(self):
        """
        GameState hook (execute_all_orders, before anything moves): if this PC owns the
        turn, the other PCs get EXECUTE_ORDERS with its state - the planned moves included
        - and replay the same moves (_handle_remote_execute_orders). One place for every
        way a turn's moves start: End Turn, the planning timer and the AI. May run on the
        AI's worker thread (the snapshot is taken now, the send is queued).
        """
        if not (self.multiplayer_mode and self.sim_state is None and self._owns_current_turn()):
            return
        from network.state_snapshot import build_snapshot
        gs = self.game_state
        self._send_action_to_remote(MessageType.EXECUTE_ORDERS, {
            'player_index': gs.current_player,
            'snapshot': build_snapshot(gs),
        })

    def _resolve_and_share_battle(self, battle_index):
        """
        GameState.shared_battle_resolver - how the turn owner resolves a battle in
        sequential multiplayer; the AI's resolve_battle_shared() lands here (on the host).
        Seeded, and the result sent (BATTLE_RESOLVE), so every PC replays the same battle -
        the AI used to resolve with its own dice and tell nobody. Runs on the AI's worker
        thread (the send is queued for the main loop).

        Returns:
            bool: True if the battle was resolved
        """
        battle, seed = self._resolve_battle_locally(battle_index)
        if self.multiplayer_mode and self.sim_state is None and self._owns_current_turn():
            self._send_action_to_remote(MessageType.BATTLE_RESOLVE, self._battle_resolve_payload(
                battle, battle.territory, seed, None, list(self.game_state.last_battle_reports)))
        return bool(battle.resolved)

    def _end_local_turn(self, reason="End Turn"):
        """
        The local player ends their sequential-mode turn: the End Turn button and, in
        multiplayer, the planning timer - one path for both.

        Multiplayer: refused while the button is greyed (armies moving, battles open) - the
        click used to send the turn's messages again (M4). The other PCs then get
        EXECUTE_ORDERS (moves starting) and TURN_END (turn over) from the GameState hooks
        (_on_orders_executing, _on_turn_advanced). Single-player: next_player() itself
        refuses those states with a message.

        Returns:
            bool: True if the turn was ended (or its moves started)
        """
        gs = self.game_state
        if self.multiplayer_mode:
            if gs.turn_phase == 'execution' or (gs.turn_phase == 'battles' and gs.pending_battles):
                logger.debug(f"[TURN] {reason} ignored - turn phase '{gs.turn_phase}'")
                return False
        logger.info(f"[TURN] Player {gs.current_player + 1} ends the turn ({reason})")
        gs.next_player()
        return True

    def _update_sequential_turn(self, delta_time):
        """
        One frame of sequential-mode turn bookkeeping - Game.run() and the multiplayer test
        harness call this same method: starting a computer player's turn (multiplayer: on
        the host only), the planning timer (multiplayer: on the turn owner's PC only), the
        multiplayer AFK rules for battles, and the final state at game end.
        """
        gs = self.game_state
        if self.sim_state is not None:
            return
        self._update_ai_turn_start()
        if gs.game_mode != 'sequential':
            return
        # Planning timer - skipped during a mission intro that pauses the game
        timer_allowed = not (self.tutorial_mission
                             and getattr(self.tutorial_mission, 'game_paused', False))
        if timer_allowed and not self.is_game_paused:
            if not self.multiplayer_mode:
                gs.check_planning_timer_expired()
            elif self._owns_current_turn() and gs.planning_time_expired():
                # Only the turn owner's timer ends the turn (every PC used to end it on its
                # own clock: moves ran on one PC only, or the turn passed twice - C2)
                if gs.player_is_ai[gs.current_player]:
                    # The host's computer player, as in single-player; its moves still go
                    # out through the EXECUTE_ORDERS hook
                    gs.check_planning_timer_expired()
                else:
                    # Through the End Turn path, so the planned moves reach the other PCs
                    gs.add_message("Planning time expired! Executing turn...")
                    self._end_local_turn("planning time expired")
        if self.multiplayer_mode:
            self._seq_afk_watchdog()
            self._send_final_state_if_owner()

    def _update_ai_turn_start(self):
        """
        Start a computer player's turn once its planning phase begins (checked when the
        current player, the game phase or the turn announcement changes). Multiplayer:
        only the turn owner - the host - runs the AI; every PC used to run its own copy,
        with its own random choices, and nothing was sent (C1).
        """
        gs = self.game_state
        player_changed = gs.current_player != self.previous_ai_check
        phase_changed = gs.phase != self.previous_phase
        announcement_ended = self.previous_turn_announcement and not gs.turn_announcement_active
        if not (player_changed or phase_changed or announcement_ended):
            return
        self.previous_ai_check = gs.current_player
        self.previous_phase = gs.phase
        self.previous_turn_announcement = gs.turn_announcement_active

        # Don't process AI turns while game is paused
        if self.is_game_paused:
            return
        # Handle setup phase (AI claiming starting territories)
        if gs.is_ai_player() and gs.phase == 'setup':
            self.handle_ai_setup()
        # Handle playing phase (normal AI turn) - SEQUENTIAL MODE ONLY
        # In simultaneous mode, AI is handled separately by sim_ai
        elif (gs.is_ai_player() and gs.phase == 'playing' and gs.turn_phase == 'planning'
                and not gs.turn_announcement_active and self._owns_current_turn()):
            self.handle_ai_turn()

    def _seq_afk_watchdog(self):
        """
        Sequential multiplayer AFK rules for the turn owner's battles, which everyone else
        waits for (the planning phase already has its timer):
        - untouched for SEQ_AFK_RESOLVE_SECONDS (an open battle window counts as busy) ->
          resolved on the owner's PC;
        - a battle report left open that long after FIGHT is closed - the turn only
          advances when it closes;
        - after SEQ_BATTLE_FALLBACK_SECONDS of battles everything still open is resolved,
          even with a battle window open.
        Also covers battles left over when the game ended (the victory screen waits for
        them on every PC), and a computer player's turn on the host whose AI stopped with
        battles still open (never while its AI is still at work).
        """
        gs = self.game_state
        now = time.monotonic()
        if not (self.multiplayer_mode and self.sim_state is None
                and gs.turn_phase == 'battles' and gs.phase in ('playing', 'ended')
                and self._owns_current_turn() and not self._ai_turn_running()):
            self._seq_battles_since = None
            return
        if self._seq_battles_since is None:
            self._seq_battles_since = now
            self._seq_battle_activity = now
        info = self._resolved_battle_info
        if (info is not None and self.enhanced_battle_ui is not None
                and now - info.get('fought_at', now) >= self.SEQ_AFK_RESOLVE_SECONDS):
            logger.info(f"[TURN] Battle report for {info.get('territory')} left open - closing it")
            self._seq_battle_activity = now
            self._finalize_enhanced_battle()
            return
        if self.enhanced_battle_ui is not None or self.battle_popup_visible:
            self._seq_battle_activity = now   # busy with a battle
        if not gs.pending_battles:
            return
        idle = now - self._seq_battle_activity
        if idle >= self.SEQ_AFK_RESOLVE_SECONDS or now - self._seq_battles_since >= self.SEQ_BATTLE_FALLBACK_SECONDS:
            logger.info(f"[TURN] Player {gs.current_player + 1}'s battles untouched - resolving them")
            self._seq_battle_activity = now
            self._resolve_all_pending_battles()
            # A battle window still before FIGHT has nothing left to fight
            self._close_stale_battle_window()

    def _send_final_state_if_owner(self):
        """
        Sequential multiplayer: the game ended during a turn this PC played (our own, or a
        computer player's on the host) - send the final state once (TURN_END with the
        snapshot; no turn follows, so the turn-advance hook never fires). Waits until the
        moves and battles are done (and the AI has stopped), so every battle result went
        out first. Every PC's recap and progression then use the same numbers.
        """
        gs = self.game_state
        if gs.phase != 'ended' or self._final_state_sent:
            return
        if not (self.multiplayer_mode and self.sim_state is None and self._owns_current_turn()):
            return
        if (gs.active_animations or gs.pending_arrivals or gs.pending_battles
                or self.enhanced_battle_ui is not None or self.battle_popup_visible
                or self._ai_turn_running()):
            return
        self._final_state_sent = True
        from network.state_snapshot import build_snapshot
        self._send_action_to_remote(MessageType.TURN_END, {
            'player_index': gs.current_player,
            'snapshot': build_snapshot(gs),
            'final': True,
        })
        logger.info("[TURN] Game over in a turn this PC played - final state sent")

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
        # Same rule as achievements and player-level XP (GameState.is_winner)
        return self.game_state.is_winner(self.get_local_player())

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
            if getattr(self, 'bottom_panel_kit', None) is not None:
                self.bottom_panel_kit.invalidate()
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
        # This system ran this frame (see _release_orphaned_button_hover)
        self._hover_systems_this_frame.add(hover_type)

    def _release_orphaned_button_hover(self):
        """
        Drop the button hover if the system that owns it did not run this frame.

        A hover system only releases its hover while its buttons are drawn. When a
        click or key switched to another view, the old system stopped running and its
        hover stayed forever: the tooltip followed the mouse around the bottom panel
        (Territory view plot icon clicked -> Barracks / Keep / plot view), or the map
        (quick-access build / train icon hovered when Escape deselected the plot, or
        the multiplayer turn passed). Every system calls update_button_hover() each
        frame while its UI is shown, so "did not run" means "its buttons are gone".
        Called once per frame by update_frame_tooltips(), after all drawing.
        """
        target = self.hover_target_button
        if target and target[0] not in self._hover_systems_this_frame:
            self.clear_button_tooltip()
        self._hover_systems_this_frame = set()

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
                            # Same for the other two abilities that pick units at random
                            elif ability_name == 'Decisive Strike':
                                ability_data['picked_units'] = getattr(
                                    self.game_state, '_last_decisive_strike_removed', None)
                            elif ability_name == 'Valorous Charge':
                                ability_data['picked_units'] = getattr(
                                    self.game_state, '_last_valorous_charge_moved', None)
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
    
    # Territory view section widths, as fractions of the panel right of the End Turn
    # pillar: Info / Building Plots / Forces / Lore (260 / 400 / 315 / 315 px at
    # 1600 wide - the pre-overhaul sizes, now proportional instead of fixed px)
    TERRITORY_VIEW_WEIGHTS = (0.2016, 0.31, 0.2442, 0.2442)
    # Unit order in the Forces grid (column-major), then the hero
    FORCES_UNIT_ORDER = ('Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain')

    def _section_layout(self, names, weights):
        """
        Split the panel right of the End Turn pillar into sections.

        `weights` are fractions of that space, one per name. Returns
        {'pillars': [x, ...] (between sections), 'rects': {name: content rect}}.
        One source of geometry for drawing and the tests.
        """
        kit = self.bottom_panel_kit
        start = int(WINDOW_WIDTH * self.END_TURN_SECTION_FRAC)
        avail = WINDOW_WIDTH - start
        edges = [start]
        acc = float(start)
        for weight in weights[:-1]:
            acc += avail * weight
            edges.append(int(round(acc)))
        # The last section ends at the screen edge (no pillar there)
        edges.append(WINDOW_WIDTH + self.separator_width // 2)
        rects = {name: kit.section_rect(edges[i], edges[i + 1]) for i, name in enumerate(names)}
        return {'pillars': edges[1:-1], 'rects': rects}

    def _territory_view_layout(self):
        """Territory view sections: info / plots / forces / lore (see _section_layout)."""
        return self._section_layout(('info', 'plots', 'forces', 'lore'), self.TERRITORY_VIEW_WEIGHTS)

    # Army view section widths (fractions right of the End Turn pillar): Army Info
    # (status + Select/Deselect All), Units (5-wide grid), Unit Selection Info
    ARMY_VIEW_WEIGHTS = (0.36, 0.25, 0.39)

    def _army_view_layout(self):
        """Army view sections: info / units / help (see _section_layout)."""
        return self._section_layout(('info', 'units', 'help'), self.ARMY_VIEW_WEIGHTS)

    def _draw_info_list_section(self, rect, title, items, bullets=True):
        """
        Centred headline + gold rule, then left-aligned text: bullet points with a
        hanging indent, or (bullets=False) one paragraph per item. Each item wraps to
        the section width; spacing between items grows to use the height (capped);
        drops to the small font if the body font does not fit; bounds-checked.
        Shared by the Army view's Unit Selection Info and the Hero view's Hero Info.
        """
        y = self.bottom_panel_kit.header(rect, title)
        self._draw_info_list(pygame.Rect(rect.left, y, rect.w, rect.bottom - y), items, bullets)

    def _draw_info_list(self, area, items, bullets=True):
        """
        The body of _draw_info_list_section() in `area` (also used under the Keep
        view's Hero Info headline, above its Demolish button).

        items: plain strings (bulleted when `bullets`, in the secondary colour), or
        (text, colour, bulleted) tuples for a line of its own colour / without bullet.
        """
        kit = self.bottom_panel_kit
        y = area.top
        avail = area.h
        entries = [(item, BROWN_TEXT_SECONDARY, bullets) if isinstance(item, str) else item
                   for item in items]

        def wrapped(role):
            indent = kit.font(role).size("- ")[0]
            return indent, [kit.wrap(text, role, area.w - (indent if bulleted else 0), max_lines=4)
                            for text, _color, bulleted in entries]

        role = 'body'
        indent, blocks = wrapped(role)
        if sum(len(b) for b in blocks) * kit.line_height(role) > avail:
            role = 'small'
            indent, blocks = wrapped(role)
        line_h = kit.line_height(role)
        n_lines = sum(len(b) for b in blocks)
        gap = max(0, min(kit.px(6), (avail - n_lines * line_h) // max(1, len(blocks))))
        for block, (_text, color, bulleted) in zip(blocks, entries):
            for i, line in enumerate(block):
                if y + line_h > area.bottom + 1:
                    return  # bounds check - never render past the section
                if not bulleted:
                    kit.left_text(line, role, color, area.left, y)
                elif i == 0:
                    kit.left_text("- " + line, role, color, area.left, y)
                else:
                    kit.left_text(line, role, color, area.left + indent, y)
                y += line_h
            y += gap

    def _army_limit_color(self, count):
        """Colour of an "Army Limit" / "Total" count: red at the limit, yellow from 3
        below it (12/15), cream otherwise. Shared by the Territory and Army views."""
        max_armies = self.game_state.MAX_ARMIES_PER_TERRITORY
        if count >= max_armies:
            return (232, 82, 70)
        if count >= max_armies - 3:
            return (242, 202, 82)
        return BROWN_TEXT_PRIMARY

    def _can_select_army_in(self, territory):
        """
        True when the Forces section's Select Army button works for `territory`:
        planning phase, the local player's turn, and the current player has a
        garrison with units there (own or allied territory). Same garrison the map
        banner opens (_select_army_garrison); greyed out otherwise (owner choice).
        """
        gs = self.game_state
        if gs.phase != 'playing' or gs.turn_phase != 'planning':
            return False
        if not self.is_local_player_active():
            return False
        garrison = gs.territory_garrisons.get(territory, {}).get(gs.current_player)
        return bool(garrison and garrison.get('units'))

    def _forces_entries(self, territory):
        """
        Cells of the Forces grid, in display order.

        Units of every garrison in the territory, one cell per type with a count
        ({'kind': 'unit', 'name', 'count'}), then any hero residing in a Keep there
        ({'kind': 'hero', 'name', 'player'}).
        """
        gs = self.game_state
        entries = []
        if gs.get_territory_total_armies(territory) > 0:
            composition = gs.get_unit_composition(territory)
            order = list(self.FORCES_UNIT_ORDER) + sorted(t for t in composition if t not in self.FORCES_UNIT_ORDER)
            for unit_type in order:
                if composition.get(unit_type, 0) > 0:
                    entries.append({'kind': 'unit', 'name': unit_type, 'count': composition[unit_type]})
        for player, heroes in gs.heroes.items():
            for hero_name, hero_data in heroes.items():
                if hero_data.get('keep_territory') == territory:
                    entries.append({'kind': 'hero', 'name': hero_name, 'player': player})
        return entries

    def _draw_forces_section(self, rect, territory, armies):
        """
        Forces section of the Territory view:

            Forces
            ---<>---
            [ Select Army ]      steel CampaignBTN, greyed when unavailable
            [icon] x 2   [icon] x 1
            [icon] x 2   [hero]          2 columns x 3 rows, column-major
            ---<>---
            Army Limit: 7/15     red at the limit, yellow from 12
        """
        kit = self.bottom_panel_kit
        y = kit.header(rect, "Forces")

        # Select Army: opens the current player's garrison here (the same path as
        # clicking its banner on the map). Rect stored even when greyed; the click
        # handler re-checks _can_select_army_in().
        button_w = min(rect.w, kit.px(170))
        button = pygame.Rect(0, y, button_w, kit.button_height(button_w))
        button.centerx = rect.centerx
        kit.ornate_button(button, "Select Army", TINT_SELECT_ARMY,
                          flash_key=('bottom_button', 'select_army'),
                          locked=not self._can_select_army_in(territory), role='body_bold')
        self.select_army_button = button

        # Bottom block (rule + Army Limit) anchored to the section bottom; the grid
        # takes whatever is between
        limit_h = kit.line_height('body_bold')
        limit_y = rect.bottom - limit_h
        rule_y = limit_y - kit.rule_gap() - kit.rule_height()
        grid_top = button.bottom + kit.px(4)
        grid_area = pygame.Rect(rect.left, grid_top, rect.w, max(1, rule_y - kit.rule_gap() - grid_top))
        self._draw_forces_grid(grid_area, self._forces_entries(territory))

        kit.rule(rect, rule_y)
        kit.centered_text(f"Army Limit: {armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY}",
                          'body_bold', self._army_limit_color(armies), rect.centerx, limit_y)

    def _draw_forces_grid(self, area, entries):
        """
        The Forces icon grid inside `area`: up to 2 columns x 3 rows, filled
        column-major, centred. Units show "icon x N"; a hero shows its portrait
        alone. The current player's own hero is clickable (opens its Hero view) and
        its rect is stored in self.forces_hero_button as (rect, hero_name).
        """
        kit = self.bottom_panel_kit
        gs = self.game_state
        self.forces_hero_button = None
        self.forces_cells = []  # (icon rect, entry) drawn this frame - hover + tests
        if not entries:
            kit.centered_text("No forces", 'body', (170, 165, 155), area.centerx,
                              area.top + (area.h - kit.line_height('body')) // 2)
            return

        rows = 3
        entries = entries[:rows * 2]  # 5 unit types + a hero always fit
        row_gap = kit.px(3)
        icon = max(12, min(kit.px(34), (area.h - row_gap * (rows - 1)) // rows))
        text_gap = kit.px(5)
        count_w = kit.font('body_bold').size("× 15")[0]
        cell_w = icon + text_gap + count_w
        # Two FIXED column slots, and the 3-row grid anchored at its top: a lone column
        # stays in the left slot and a short column starts at the top row (owner:
        # centring each case read badly). The span is halfway between the tight
        # original (columns 16 px apart) and 78% of the section, which the owner found
        # too far apart.
        tight = 2 * cell_w + kit.px(16)
        span = min(area.w, max(tight, (tight + int(area.w * 0.78)) // 2))
        x0 = area.centerx - span // 2
        col_x = (x0, x0 + span - cell_w)
        grid_h = rows * icon + (rows - 1) * row_gap
        y0 = area.top + max(0, (area.h - grid_h) // 2)
        hover_pos = self.mouse_pos

        for i, entry in enumerate(entries):
            col, row = divmod(i, rows)
            icon_rect = pygame.Rect(col_x[col], y0 + row * (icon + row_gap), icon, icon)
            self.forces_cells.append((icon_rect, entry))
            # Hover label (unit / hero name, like the Action Queue's unit chips), drawn
            # at the end of the frame by _draw_bottom_panel_tooltip()
            if hover_pos is not None and icon_rect.collidepoint(hover_pos):
                if entry['kind'] == 'unit':
                    name = entry['name'] if entry['count'] == 1 else \
                        self.ui_renderer.UNIT_PLURALS.get(entry['name'], entry['name'])
                    self.bottom_panel_tooltip = (f"{entry['count']}× {name}", hover_pos)
                else:
                    self.bottom_panel_tooltip = (entry['name'], hover_pos)

            if entry['kind'] == 'unit':
                unit_type = entry['name']
                unit_icon = self.unit_icons.get(unit_type)
                if unit_icon:
                    self.screen.blit(self._get_cached_scaled_surface(
                        unit_icon, f'unit_{unit_type}', icon - 2, icon - 2), (icon_rect.x + 1, icon_rect.y + 1))
                    if self.icon_border:
                        self.screen.blit(self._get_cached_scaled_surface(
                            self.icon_border, 'icon_border', icon, icon), icon_rect.topleft)
                else:
                    # Fallback: letter tile
                    pygame.draw.rect(self.screen, (90, 70, 50), icon_rect)
                    pygame.draw.rect(self.screen, (212, 170, 80), icon_rect, 1)
                    letter = self.game_state.UNIT_TYPES.get(unit_type, {}).get('letter', unit_type[0])
                    kit.centered_text(letter, 'body_bold', WHITE, icon_rect.centerx,
                                      icon_rect.centery - kit.line_height('body_bold') // 2)
                count_text = kit.text(f"× {entry['count']}", 'body_bold', BROWN_TEXT_PRIMARY)
                kit.blit_text(count_text, (icon_rect.right + text_gap, icon_rect.centery - count_text.get_height() // 2),
                              kit.text(f"× {entry['count']}", 'body_bold', (12, 8, 4)))
            else:
                # Hero portrait, no count. Only the current player's own hero is
                # clickable (draw_hero_ui shows the current player's heroes only).
                hero_name = entry['name']
                clickable = entry['player'] == gs.current_player
                flash_key = ('bottom_button', ('forces_hero', hero_name))
                is_clicking = clickable and self.clicked_element == flash_key
                is_hovering = clickable and icon_rect.collidepoint(self.mouse_pos)
                portrait = self.hero_images.get(hero_name)
                if portrait:
                    base = self._get_cached_scaled_surface(portrait, f'hero_{hero_name}', icon, icon)
                    self.screen.blit(self._apply_icon_overlay(base, is_clicking, is_hovering), icon_rect.topleft)
                else:
                    pygame.draw.rect(self.screen, (150, 100, 200), icon_rect)
                    letter = gs.HERO_TYPES.get(hero_name, {}).get('letter', hero_name[0])
                    kit.centered_text(letter, 'body_bold', WHITE, icon_rect.centerx,
                                      icon_rect.centery - kit.line_height('body_bold') // 2)
                frame = (255, 232, 160) if (is_hovering or is_clicking) else (212, 170, 80)
                pygame.draw.rect(self.screen, frame, icon_rect, 2 if clickable else 1)
                if clickable:
                    self.forces_hero_button = (icon_rect.copy(), hero_name)

    def _select_hero(self, hero_name):
        """
        Open the Hero view for one of the current player's heroes.

        Shared by the sidebar Heroes tab and the Territory view's Forces grid so both
        behave the same: select it, play its voice line, clear every other
        bottom-panel selection. Callers do their own click flash (and the sidebar its
        camera pan).
        """
        self.selected_hero = hero_name

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

        # Section geometry (pillars + content rects) - shared with the tests
        kit = self.bottom_panel_kit
        layout = self._territory_view_layout()
        rects = layout['rects']
        for pillar_x in layout['pillars']:
            self.draw_separator(pillar_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # === SECTION 1: TERRITORY INFO ===
        # Centred name (display name for campaign renames) + rule, then one left-aligned
        # line per fact. Long names / owners / bonuses wrap to two lines.
        info = rects['info']
        display_territory = map_data.get_display_name(territory)
        # Extra space around the rule: the facts below rarely fill the section
        # (owner: a little more padding makes the area feel filled)
        y = kit.header(info, display_territory, color=BROWN_TEXT_HEADING, role='title', max_lines=2,
                       spacing=kit.px(4))
        line_h = kit.line_height('body')
        facts = []  # (text, color, role), drawn below in one pass

        if owner == -1:
            facts.append(("Owner: Neutral", BROWN_TEXT_PRIMARY, 'body_bold'))
        else:
            facts.append((f"Owner: {self.game_state.get_player_name(owner)}",
                          self.game_state.get_player_color(owner), 'body_bold'))
        facts.append((f"Income: +{total_income}G/turn", BROWN_GOLD, 'body'))

        # Territorial bonus (if territory has one). Format: "+3% Income" or "-5% Unit Cost"
        bonus_type = map_data.get_territory_bonus(territory)
        if bonus_type and bonus_type in self.game_state.BONUS_TYPES:
            bonus_info = self.game_state.BONUS_TYPES[bonus_type]
            formatted_bonus = f"{bonus_info['format'].format(bonus_info['value'])} {bonus_info['display']}"
            facts.append((f"Bonus: {formatted_bonus}", WHITE, 'body'))

        # Fortress defense indicator (brighter red than before: (150, 50, 50) was
        # unreadable on the wood)
        if map_data.is_fortress_territory(territory):
            facts.append(("Fortress (+2 Defense)", (225, 95, 80), 'body'))

        # One fact per line (wrapped to 2), left-aligned. The space between facts grows
        # to use the section's height (owner: the bottom was mostly empty), capped so
        # a short list doesn't scatter; bounds-checked against the section bottom.
        wrapped = [(kit.wrap(text, role, info.w, max_lines=2), color, role) for text, color, role in facts]
        total_h = sum(len(lines) for lines, _c, _r in wrapped) * line_h
        fact_gap = max(kit.px(2), min(kit.px(16), (info.bottom - y - total_h) // max(1, len(wrapped))))
        for lines, color, role in wrapped:
            for line in lines:
                if y + line_h > info.bottom:
                    break
                kit.left_text(line, role, color, info.left, y)
                y += line_h
            y += fact_gap

        # === SECTION 2: BUILDING PLOTS ===
        # Plots are sized for 3 so that 3 plots fill the section (owner request); fewer
        # plots keep that size and are centred
        plots = rects['plots']
        y = kit.header(plots, "Building Plots")
        self.territory_info_plot_buttons = []
        if owner != -1 and plot_count > 0:  # Only show plots for owned territories with plots
            plot_spacing = kit.px(10)
            slots = max(3, plot_count)
            avail_h = plots.bottom - y
            plot_size = max(24, min(avail_h, (plots.w - plot_spacing * (slots - 1)) // slots))
            row_w = plot_count * plot_size + (plot_count - 1) * plot_spacing
            plots_x = plots.centerx - row_w // 2
            plot_y = y + max(0, (avail_h - plot_size) // 2)

            for plot_index in range(plot_count):  # Use actual plot count
                plot_x = plots_x + plot_index * (plot_size + plot_spacing)

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
        else:
            note = "Unclaimed territory" if owner == -1 else "No building plots"
            kit.centered_text(note, 'body', (170, 165, 155), plots.centerx,
                              y + (plots.bottom - y - kit.line_height('body')) // 2)

        # === SECTION 3: FORCES ===
        self._draw_forces_section(rects['forces'], territory, armies)

        # === SECTION 4: LORE (or the territory preview image) ===
        lore = rects['lore']
        self.territory_preview_rect = None
        if lore.w >= kit.px(120):  # Graceful degradation on very narrow screens
            if SHOW_TERRITORY_PREVIEW_IMAGE:
                # Framed preview image (16:9 at most) with a hint line under it
                border_padding = 8
                hint_h = kit.line_height('small')
                border_height = max(20, lore.h - hint_h - 4)
                preview_img_height = border_height - border_padding * 2
                preview_img_width = max(16, min(int(preview_img_height * 16 / 9), lore.w - border_padding * 2))
                border_width = preview_img_width + border_padding * 2
                frame_x = lore.centerx - border_width // 2
                frame_y = lore.top
                img_x = frame_x + border_padding
                img_y = frame_y + border_padding

                # Draw border frame (cached by size to avoid per-frame scaling)
                if self._preview_border_original:
                    if self._scaled_preview_border_size != (border_width, border_height):
                        self._scaled_preview_border = pygame.transform.smoothscale(
                            self._preview_border_original, (border_width, border_height))
                        self._scaled_preview_border_size = (border_width, border_height)
                    self.screen.blit(self._scaled_preview_border, (frame_x, frame_y))

                # Territory preview image or black fallback inside the border
                preview_surface = self._get_territory_preview(territory, preview_img_width, preview_img_height)
                if preview_surface:
                    self.screen.blit(preview_surface, (img_x, img_y))
                else:
                    pygame.draw.rect(self.screen, (0, 0, 0),
                                     (img_x, img_y, preview_img_width, preview_img_height))

                # Store rect for hover detection (lore tooltip)
                self.territory_preview_rect = pygame.Rect(img_x, img_y, preview_img_width, preview_img_height)
                kit.centered_text("Hover over the picture to learn more.", 'small', (190, 180, 160),
                                  lore.centerx, frame_y + border_height + 4)
            else:
                # Italic lore text from the top of the section. Brighter than the old brass
                # (205, 170, 110) with a drop shadow: owner found it hard to read on wood.
                lore_text = map_data.get_territory_lore(territory) or "No lore available for this territory."
                line_h = int(kit.font('lore').get_linesize() * 1.15)
                max_lines = max(1, lore.h // max(1, line_h))
                lore_lines = kit.wrap(lore_text, 'lore', lore.w, max_lines=max_lines)
                ly = lore.top  # From the top (centring left an odd gap above short lore)
                for ln in lore_lines:
                    if ly + line_h > lore.bottom + line_h // 3:
                        break  # bounds-check - never render past the container
                    kit.left_text(ln, 'lore', (238, 216, 172), lore.left, ly)
                    ly += line_h

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
    
    # Right edge of the End Turn section: the pillar between it and the next section
    # (310 px at 1600 wide). Every bottom panel view starts its first section here.
    END_TURN_SECTION_FRAC = 0.194

    def _end_turn_section_rect(self):
        """Content rect of the leftmost (End Turn) section, shared by every view."""
        return self.bottom_panel_kit.section_rect(None, int(WINDOW_WIDTH * self.END_TURN_SECTION_FRAC))

    def _display_turn_number(self):
        """Turn number shown above the planning timer (1-based).

        Simultaneous mode counts rounds itself (sim_state.round_number starts at 1);
        sequential game_state.turn_number counts completed rounds from 0.
        """
        if self.sim_state is not None:
            return getattr(self.sim_state, 'round_number', 1)
        return self.game_state.turn_number + 1

    def _end_turn_button_state(self):
        """
        (state, label) of the End Turn button.

        state: 'normal' | 'highlight' (tutorial points at it) | 'locked' (greyed: the
        click would be refused). Pulled out of the drawing code so the rules can be
        tested without inspecting pixels. Later rules win, as before: a sequential
        lock or a simultaneous-mode state overrides a tutorial highlight.
        """
        state, label = 'normal', "End Turn"

        if self._is_tutorial_active():
            if self.tutorial_mission.should_highlight_button('end_turn'):
                state = 'highlight'
            elif (self.tutorial_mission.is_button_locked('end_turn')
                    or not self.tutorial_mission.is_action_allowed('end_turn')):
                # Grey locked. is_action_allowed() is the check the click uses; campaign
                # missions and the Tale only block through it (intro, pause, endgame),
                # so is_button_locked() alone left the button looking clickable.
                state = 'locked'

        # SEQUENTIAL MODE: next_player() refuses while armies are still moving or
        # battles are unresolved - grey the button instead of letting it look clickable
        if self.sim_state is None and (
                self.game_state.turn_phase == 'execution'
                or (self.game_state.turn_phase == 'battles' and self.game_state.pending_battles)):
            state = 'locked'

        # SIMULTANEOUS MODE: grey while this player is ready or during resolution
        if self.sim_state is not None:
            if self.sim_state.sim_phase == 'planning':
                if self.sim_state.players_ready.get(self.get_local_player(), False):
                    state, label = 'locked', "Waiting..."
            elif self.sim_state.sim_phase in ('executing', 'resolving'):
                state = 'locked'
                label = "Resolving..." if self.sim_state.sim_phase == 'resolving' else "Executing..."

        return state, label

    def _planning_timer_info(self):
        """
        What sits under "Turn X:" in the End Turn section.

        Returns ('timer', remaining, limit), ('waiting', [player names]) or None (no
        timer: not the planning phase, or a mission hides it).
        """
        # Check mission's is_timer_visible() if active, otherwise show during planning
        show_timer = self.game_state.turn_phase == 'planning'
        if self._is_tutorial_active():
            # Mission controls timer visibility (intro sequence hides/shows it)
            if hasattr(self.tutorial_mission, 'is_timer_visible'):
                show_timer = show_timer and self.tutorial_mission.is_timer_visible()
            else:
                show_timer = False  # Tutorial mission hides timer by default

        if self.sim_state is not None:
            # SIMULTANEOUS MODE: its own timer, or "Waiting for: X, Y" once ready
            if self.sim_state.sim_phase != 'planning':
                return None
            local_player = self.get_local_player()
            if self.sim_state.players_ready.get(local_player, False):
                return ('waiting', self.sim_state.get_waiting_player_names())
            return ('timer', self.sim_state.get_remaining_time(local_player),
                    self.sim_state._get_timer_limit(local_player))

        if not show_timer:
            return None
        # SEQUENTIAL MODE: standard timer
        remaining_time = self.game_state.get_remaining_planning_time()
        time_limit = self.game_state.player_planning_time_limit[self.game_state.current_player]
        # During mission intro, show full timer bar (static, not counting down)
        if self.tutorial_mission and getattr(self.tutorial_mission, 'intro_active', False):
            remaining_time = time_limit
        return ('timer', remaining_time, time_limit)

    def _draw_player_info_section(self):
        """
        Draw the leftmost (End Turn) section of the bottom UI, shared by every view.

        Centred stack (owner-designed 2026-10-08):
            player name (player colour)
            ---<>--- gold rule
            [ End Turn ]   CampaignBTN, green wood; grey when refused
            ---<>--- gold rule
            Turn X:
            [ BattleBar planning timer ]  (or "Waiting for: ..." in simultaneous mode)
            Elapsed Game Time (grey, small)
        """
        if self.game_state.phase == 'playing':
            self._draw_end_turn_section(self._end_turn_section_rect())

        # Pillar between this section and the view's first section
        separator_x = int(WINDOW_WIDTH * self.END_TURN_SECTION_FRAC)
        self.draw_separator(separator_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

    def _draw_end_turn_section(self, rect):
        """
        Layout + drawing of the End Turn section inside `rect` (see the caller).

        Gaps shrink to fit the panel (180 px tall at 1280x720); if it still doesn't
        fit (720p and a player name that wraps), the elapsed time line is dropped.
        The block is centred vertically when there is room to spare.
        """
        kit = self.bottom_panel_kit
        gs = self.game_state

        # --- Player name: one line in the title font, else two lines a size smaller
        player_color = gs.get_player_color(gs.current_player)
        player_name = gs.get_player_name(gs.current_player)
        name_role = 'title'
        name_lines = [player_name]
        if kit.font('title').size(player_name)[0] > rect.w:
            name_role = 'heading'
            name_lines = kit.wrap(player_name, name_role, rect.w, max_lines=2)

        # --- Sizes of every row
        button_w = min(rect.w, kit.px(220))
        button_h = kit.button_height(button_w)
        bar_w = min(rect.w, kit.px(236))
        bar_h = kit.battlebar_height(bar_w)
        timer = self._planning_timer_info()
        waiting_lines = []
        if timer is not None and timer[0] == 'waiting':
            waiting_lines = (self._wrap_waiting_text(timer[1], rect.w, kit.font('small'))
                             if timer[1] else ["All players ready..."])
        elif timer is not None and (timer[1] is None or timer[2] <= 0):
            timer = None  # No time limit: only "Turn X" shows
        show_elapsed = self.game_start_time is not None

        name_h = len(name_lines) * kit.line_height(name_role)
        rule_h = kit.rule_height()
        turn_h = kit.line_height('body_bold')
        small_h = kit.line_height('small')
        if timer is None:
            timer_h = 0
        elif timer[0] == 'waiting':
            timer_h = len(waiting_lines) * small_h
        else:
            timer_h = bar_h

        def stack_height(gap, elapsed):
            """(height of the whole block, number of gaps) for a given gap."""
            rows = [name_h, rule_h, button_h, rule_h, turn_h]
            if timer_h:
                rows.append(timer_h)
            if elapsed:
                rows.append(small_h)
            return sum(rows) + gap * (len(rows) - 1), len(rows) - 1

        # Largest gap (up to 6 px at the reference size) that fits; drop the elapsed
        # time line only if even 1 px gaps overflow
        fixed, n_gaps = stack_height(0, show_elapsed)
        if fixed + n_gaps > rect.h and show_elapsed:
            show_elapsed = False
            fixed, n_gaps = stack_height(0, False)
        gap = max(1, min(kit.px(6), (rect.h - fixed) // max(1, n_gaps)))
        height, _ = stack_height(gap, show_elapsed)
        y = rect.top + max(0, (rect.h - height) // 2)
        cx = rect.centerx

        # 1. Player name
        for line in name_lines:
            kit.centered_text(line, name_role, player_color, cx, y)
            y += kit.line_height(name_role)
        y += gap
        # 2. Rule
        kit.rule(rect, y)
        y += rule_h + gap

        # 3. End Turn button
        state, label = self._end_turn_button_state()
        end_turn_rect = pygame.Rect(0, y, button_w, button_h)
        end_turn_rect.centerx = cx
        tint = TINT_END_TURN_HIGHLIGHT if state == 'highlight' else TINT_END_TURN
        kit.ornate_button(end_turn_rect, label, tint, flash_key=('bottom_button', 'end_turn'),
                          locked=(state == 'locked'))
        if state == 'highlight':
            # Tutorial hook: pulsing green band tracing the highlighted End Turn
            # button's shape (pointed end caps included), not a box around it
            thickness = max(2, kit.px(3))
            ring = kit.button_outline(end_turn_rect.size, thickness=thickness)
            ring.set_alpha(int(150 + 105 * (0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 200.0))))
            self.screen.blit(ring, (end_turn_rect.x - thickness, end_turn_rect.y - thickness))
        self.end_turn_button = end_turn_rect
        y += button_h + gap

        # 4. Rule
        kit.rule(rect, y)
        y += rule_h + gap

        # 5. "Turn X:" and the planning timer under it
        kit.centered_text(f"Turn {self._display_turn_number()}:", 'body_bold', BOTTOM_GOLD_TEXT, cx, y)
        y += turn_h
        if timer is not None:
            y += gap
            if timer[0] == 'waiting':
                for line in waiting_lines:
                    kit.centered_text(line, 'small', (200, 195, 185), cx, y)
                    y += small_h
            else:
                bar_rect = pygame.Rect(0, y, bar_w, bar_h)
                bar_rect.centerx = cx
                self._draw_planning_timer(bar_rect, timer[1], timer[2])
                y += bar_h

        # 6. Elapsed game time (grey: information only)
        if show_elapsed:
            elapsed_seconds = int(time.time() - self.game_start_time)
            hours = elapsed_seconds // 3600
            minutes = (elapsed_seconds % 3600) // 60
            seconds = elapsed_seconds % 60
            kit.centered_text(f"Elapsed Game Time: {hours:02d}:{minutes:02d}:{seconds:02d}",
                              'small', (170, 165, 155), cx, y + gap)

        # Command Limit and Gold/Income live in the top panel

    def _wrap_waiting_text(self, player_names: list, max_width: int, font=None) -> list:
        """
        Wrap 'Waiting for: X, Y, Z' text into multiple lines if too long.

        Args:
            player_names: List of player names waiting
            max_width: Maximum width in pixels
            font: Font the lines are drawn with (default self.small_font)

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

            test_width = (font or self.small_font).size(test_text)[0]

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

    def _draw_planning_timer(self, rect, remaining_time, time_limit):
        """
        Draw the planning timer as a BattleBar frame in `rect` (End Turn section).

        Used by both sequential and simultaneous modes. The fill empties from right
        to left and turns green -> yellow -> red as time runs out; m:ss sits on it.

        Args:
            rect: Frame rect (height from bottom_panel_kit.battlebar_height())
            remaining_time: Remaining time in seconds
            time_limit: Total time limit in seconds
        """
        if remaining_time is None or time_limit <= 0:
            return
        time_ratio = max(0.0, min(1.0, remaining_time / time_limit))
        if time_ratio > 0.5:
            bar_color = (90, 190, 80)    # Green
        elif time_ratio > 0.25:
            bar_color = (215, 190, 70)   # Yellow
        else:
            bar_color = (210, 80, 70)    # Red
        minutes = int(remaining_time // 60)
        seconds = int(remaining_time % 60)
        self.bottom_panel_kit.battlebar(rect, time_ratio, bar_color, text=f"{minutes}:{seconds:02d}")

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
    
    # Empty plot view: building buttons are separated by this fraction of their size
    EMPTY_PLOT_GAP_FRAC = 0.4

    def _empty_plot_button_layout(self, show_limit_line):
        """
        (button_size, gap, row_y, limit_y) of the empty plot view's building buttons.

        The buttons start where the old title did (25% of the width) and are as big
        as the panel's content height allows (owner: fill it vertically), shrinking
        only if all building types would not fit the width. With the "Building limit
        reached" line shown, it takes the top of the content area and the row sits
        below it. One source of geometry for drawing and the tests.
        """
        kit = self.bottom_panel_kit
        start_x = int(WINDOW_WIDTH * 0.25)
        top, bottom = kit.content_top(), kit.content_bottom()
        limit_y = top
        if show_limit_line:
            top += kit.line_height('body_bold') + kit.px(4)
        count = max(1, len(self.game_state.building_types))
        avail_w = WINDOW_WIDTH - start_x - kit.px(EDGE_PAD_REF_PX)
        by_width = int(avail_w / (count + (count - 1) * self.EMPTY_PLOT_GAP_FRAC))
        size = max(24, min(bottom - top, by_width))
        gap = int(size * self.EMPTY_PLOT_GAP_FRAC)
        row_y = top + max(0, (bottom - top - size) // 2)
        return size, gap, row_y, limit_y

    # Building views' ornate Demolish / Cancel button width (reference px, scaled by the
    # panel): wide enough for "Demolish (100%)" at every resolution, since a label only
    # gets 66% of the button (measured 2026-10-09: 170 px ellipsized it)
    BUILDING_BUTTON_W_REF = 210
    # Plot building view: text column width cap (the longest description, Training
    # Grounds, fits on one line) and the Farm/Mine XP BattleBar width
    PLOT_VIEW_COLUMN_W_REF = 540
    BUILDING_XP_BAR_W_REF = 280

    def _plot_building_view_layout(self):
        """
        {'icon': rect, 'column': rect} of the plot view of a finished or
        under-construction building.

        The icon takes the size and spot of the empty plot view's first building button,
        so it does not jump when construction starts; the text column starts right of it
        and spans the content height. One source of geometry for drawing and the tests.
        """
        kit = self.bottom_panel_kit
        size, _gap, row_y, _limit_y = self._empty_plot_button_layout(False)
        icon = pygame.Rect(int(WINDOW_WIDTH * 0.25), row_y, size, size)
        col_x = icon.right + kit.px(24)
        col_w = max(40, min(kit.px(self.PLOT_VIEW_COLUMN_W_REF),
                            WINDOW_WIDTH - col_x - kit.px(EDGE_PAD_REF_PX)))
        top = kit.content_top()
        return {'icon': icon, 'column': pygame.Rect(col_x, top, col_w, kit.content_bottom() - top)}

    def _building_xp_view(self, territory, plot_index):
        """Farm/Mine veterancy for the plot view: level, XP bar fill (0..1), bar label
        and income bonus %. Same maths as the pre-redesign panel."""
        gs = self.game_state
        data = gs.get_building_xp_data(territory, plot_index)
        level, xp = data['level'], data['xp']
        if level < gs.MAX_LEVEL:
            prev_t = gs.LEVEL_XP_CUMULATIVE[level - 1] if level > 0 else 0
            next_t = gs.LEVEL_XP_CUMULATIVE[level]
            in_level, needed = xp - prev_t, next_t - prev_t
            fill = max(0.0, min(1.0, in_level / needed)) if needed > 0 else 0.0
            label = f"{in_level}/{needed} XP"
        else:
            fill, label = 1.0, "MAX"
        return {'level': level, 'fill': fill, 'label': label,
                'bonus_pct': int(level * gs.BUILDING_LEVEL_INCOME_BONUS * 100)}

    def _draw_plot_building_icon(self, building_type, rect, greyed):
        """
        The building's round icon in the plot view, drawn like the empty plot view's
        buttons (icon at 80% of the circle + circle border). greyed (under
        construction): a greyscale copy, slightly dimmed, cached per building and size.
        """
        radius = rect.w // 2
        image = self.building_icons.get(building_type)
        if image:
            icon_size = int(radius * 1.6)
            icon = self._get_cached_ui_icon(image, building_type, icon_size)
            if greyed:
                # PERFORMANCE: greyscale once per (building, size), never per frame.
                # _ui_icon_cache is cleared on resolution change.
                key = ('grey_building', building_type, icon_size)
                grey = self._ui_icon_cache.get(key)
                if grey is None:
                    grey = pygame.transform.grayscale(icon)
                    grey.fill((205, 205, 205, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    self._ui_icon_cache[key] = grey
                icon = grey
            self.screen.blit(icon, icon.get_rect(center=rect.center))
            if self.circle_border:
                border = self._get_cached_ui_icon(self.circle_border, 'circle_border', rect.w)
                self.screen.blit(border, border.get_rect(center=rect.center))
        else:
            # Fallback when the icon art is missing: a letter disc
            fill = (120, 120, 120) if greyed else (100, 160, 100)
            pygame.draw.circle(self.screen, fill, rect.center, radius)
            pygame.draw.circle(self.screen, BLACK, rect.center, radius, 2)
            letter = self.game_state.building_types.get(building_type, {}).get('letter', '?')
            letter_surf = self._get_cached_text(letter, self.font, WHITE)
            self.screen.blit(letter_surf, letter_surf.get_rect(center=rect.center))

    def _draw_building_level_row(self, xp, role, x, y):
        """Farm/Mine level line in the plot view: one shield per level, "Level N" and
        the income bonus (just "Level 0" before the first level)."""
        kit = self.bottom_panel_kit
        level = xp['level']
        if level <= 0:
            kit.left_text("Level 0", role, BROWN_TEXT_SECONDARY, x, y)
            return
        if self.level_shield_icon:
            # The shield art has a wide transparent margin (it drew as dots at text
            # height): crop it to the opaque shield once, then scale to the line
            cropped = self._ui_icon_cache.get('level_shield_cropped')
            if cropped is None:
                from utils.surface_utils import crop_to_opaque
                cropped = crop_to_opaque(self.level_shield_icon)
                self._ui_icon_cache['level_shield_cropped'] = cropped
            line_h = kit.line_height(role)
            sh = max(8, int(line_h * 0.9))
            sw = max(6, int(round(sh * cropped.get_width() / float(max(1, cropped.get_height())))))
            shield = self._get_cached_scaled_surface(cropped, 'level_shield_bldg_view', sw, sh)
            for _ in range(level):
                self.screen.blit(shield, (x, y + (line_h - sh) // 2))
                x += sw + kit.px(2)
            x += kit.px(4)
        x += kit.left_text(f"Level {level}", f"{role}_bold", (232, 180, 60), x, y)
        if xp['bonus_pct'] > 0:
            kit.left_text(f"  (+{xp['bonus_pct']}% income)", role, (150, 210, 140), x, y)

    def _draw_plot_building_view(self, building_type, under_construction, lines, button_label,
                                 button_tint, flash_key, locked=False, xp=None):
        """
        Plot view of a finished or under-construction building (owner-designed
        2026-10-09): the building's icon on the left; right of it the name as a
        headline, a rule, the description lines (+ the Farm/Mine level row and XP
        BattleBar), a rule and the Demolish / Cancel button. Under construction, the
        icon and headline are greyed out. The blocks are spread over the content height.

        Returns the button rect (the caller stores it for handle_bottom_ui_click()).
        """
        kit = self.bottom_panel_kit
        layout = self._plot_building_view_layout()
        col = layout['column']
        self._draw_plot_building_icon(building_type, layout['icon'], greyed=under_construction)

        title_h = kit.header_height(building_type, role='title')
        bar_w = min(col.w, kit.px(self.BUILDING_XP_BAR_W_REF))
        bar_h = kit.battlebar_height(bar_w)
        button_w = min(col.w, kit.px(self.BUILDING_BUTTON_W_REF))
        button_h = kit.button_height(button_w)
        rule_h = kit.rule_height() + kit.rule_gap()
        level_gap = kit.px(3)  # Between the level row and its XP bar

        def wrapped(role):
            return [part for line in lines for part in kit.wrap(line, role, col.w, max_lines=2)]

        def stack_height(role, text_lines):
            line_h = kit.line_height(role)
            height = title_h + len(text_lines) * line_h + rule_h + button_h
            if xp is not None:
                height += line_h + level_gap + bar_h
            return height

        # Body font, or the small one if the stack would not fit the content height
        role = 'body'
        text_lines = wrapped(role)
        if stack_height(role, text_lines) > col.h:
            role = 'small'
            text_lines = wrapped(role)
        line_h = kit.line_height(role)

        # Spare height becomes the gaps before each block after the headline (text,
        # XP, rule, button), capped; what is left over centres the stack vertically
        blocks = 3 + (1 if xp is not None else 0)
        spare = max(0, col.h - stack_height(role, text_lines))
        gap = min(kit.px(10), spare // blocks)
        y = col.top + (spare - gap * blocks) // 2

        heading_color = (168, 160, 148) if under_construction else BROWN_TEXT_HEADING
        y = kit.header(col, building_type, color=heading_color, role='title', y=y, align='left')
        y += gap
        for line in text_lines:
            kit.left_text(line, role, BROWN_TEXT_SECONDARY, col.left, y)
            y += line_h
        if xp is not None:
            y += gap
            self._draw_building_level_row(xp, role, col.left, y)
            y += line_h + level_gap
            kit.battlebar(pygame.Rect(col.left, y, bar_w, bar_h), xp['fill'], (185, 155, 80),
                          text=xp['label'])
            y += bar_h
        y = kit.rule(col, y + gap, width_frac=1.0)
        button = pygame.Rect(col.left, y + gap, button_w, button_h)
        kit.ornate_button(button, button_label, button_tint, flash_key=flash_key, locked=locked)
        return button

    def _draw_building_ui_section(self):
        """
        Draw building UI when plot is selected.
        
        Phase 5: Extracted from draw_bottom_ui() for maintainability.
        Shows different content based on plot state:
        - Completed building (Farm, Mine, Square, Training Grounds): icon, headline,
          description (+ level and XP bar for Farm/Mine), Demolish
          (_draw_plot_building_view)
        - Under construction (any type): greyed icon and headline, description,
          turns left, Cancel (_draw_plot_building_view)
        - Empty plot: the building buttons

        A finished Barracks / Keep never gets here: it opens draw_training_ui() /
        draw_keep_ui() instead.
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
            # Finished building (Farm, Mine, Square, Training Grounds - Barracks and Keep
            # have their own views): icon, headline, rule, description (+ level row and
            # XP bar for Farm/Mine), rule, Demolish. Owner-designed 2026-10-09.
            building_info = self.game_state.building_types[building]
            lines = [self._get_building_effect_text(building_info['effect'], building_info['value'])]
            xp = self._building_xp_view(territory, plot_index) if building in ('Farm', 'Mine') else None
            # Confiscate (Erec Silvyr): a Farm/Mine demolish refunds 175%, not 50% (the
            # destroy_building() rule). The button used to say 50% either way.
            has_confiscate = (building in ('Farm', 'Mine') and
                              self.game_state.player_has_silvyr(self.game_state.current_player))
            label, tint = (("Demolish (175%)", TINT_CONFISCATE) if has_confiscate
                           else ("Demolish (50%)", TINT_DEMOLISH))
            # Greyed while the tutorial/mission forbids it - the click handler checks the same
            self.demolish_button = self._draw_plot_building_view(
                building, False, lines, label, tint, ('demolish', 'building'),
                locked=bool(self._is_tutorial_blocking('demolish')), xp=xp)

        elif under_construction:
            # Under construction (any building type, Barracks and Keep included): greyed
            # icon and headline, description + turns left, rule, Cancel
            building_type = under_construction[0]  # entry is (building_type, turns_remaining, cost)
            turns_remaining = under_construction[1]
            building_info = self.game_state.building_types[building_type]
            lines = [self._get_building_effect_text(building_info['effect'], building_info['value']),
                     f"- Completes in {turns_remaining} turn{'s' if turns_remaining != 1 else ''}."]
            # Just "Cancel": the headline already names the building
            self.cancel_button = self._draw_plot_building_view(
                building_type, True, lines, "Cancel", TINT_DEMOLISH, ('cancel', 'construction'),
                locked=bool(self._is_tutorial_blocking('cancel_construction')))

        else:
            # Empty plot - show building options. No "Territory - Plot X" title any
            # more (owner request): the buttons grow to fill the panel's height instead.
            # Check if can build this turn
            can_build = territory not in self.game_state.buildings_started_this_turn
            current_gold = self.game_state.player_gold[self.game_state.current_player]

            # Geometry shared with the tests (_empty_plot_button_layout)
            button_size, button_gap, row_y, limit_y = self._empty_plot_button_layout(not can_build)
            if not can_build:
                # Where the title used to be - only shown when it applies
                self.bottom_panel_kit.left_text("Building limit reached this turn", 'body_bold',
                                                (232, 82, 70), build_ui_x, limit_y)

            # Building options - arranged horizontally
            button_x = build_ui_x  # Start position for horizontal layout
            build_ui_y = row_y
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

                # Circular button center and radius (size from _empty_plot_button_layout)
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
                button_x += button_size + button_gap  # Move right for next button
    
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
        # Territory view Forces section controls (drawn only in that view)
        self.select_army_button = None
        self.forces_hero_button = None
        self.forces_cells = []
        self.bottom_panel_tooltip = None  # Re-set by the hovered Forces icon
        self.hero_view_portrait_button = None  # Hero view portrait (pans to its Keep)
        self.keep_hero_button = None  # Keep view: the Keep's hero card (opens the Hero view)
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

    # Hero view section widths (fractions right of the End Turn pillar): the same as
    # the Army view, so the pillars stay put when switching between the two
    HERO_VIEW_WEIGHTS = ARMY_VIEW_WEIGHTS

    def _hero_view_layout(self):
        """Hero view sections: general / abilities / info (see _section_layout)."""
        return self._section_layout(('general', 'abilities', 'info'), self.HERO_VIEW_WEIGHTS)

    def draw_hero_ui(self):
        """
        Draw the Hero view (a hero selected from the Heroes tab or the Forces grid).

        Sections (owner-designed 2026-10-09), each a centred headline + gold rule:
            General:   hero name; portrait on the left, title and location to its right
            Abilities: the three ability icons in a centred row
            Hero Info: what happens when a hero dies (shared list section)
        """
        hero_name = self.selected_hero

        # Get hero data
        current_player = self.game_state.current_player
        if current_player not in self.game_state.heroes:
            return
        if hero_name not in self.game_state.heroes[current_player]:
            return

        hero_data = self.game_state.heroes[current_player][hero_name]
        hero_info = self.game_state.HERO_TYPES[hero_name]
        hero_letter = hero_info['letter']

        kit = self.bottom_panel_kit
        layout = self._hero_view_layout()
        rects = layout['rects']
        for pillar_x in layout['pillars']:
            self.draw_separator(pillar_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # === SECTION 1: GENERAL ===
        general = rects['general']
        y = kit.header(general, hero_name, color=BROWN_TEXT_HEADING, role='title', spacing=kit.px(3))

        # Text to the right of the portrait: title line(s), then "Location: X"
        description_lines = hero_info.get('description', ['Unknown hero'])
        location = map_data.get_display_name(hero_data['keep_territory'])  # Campaign renames
        title_color = (232, 170, 100)   # Lighter bronze than before: readable on the wood
        label_color = (200, 200, 205)   # Silvery "Location:" label
        value_color = (245, 235, 210)   # Cream value
        text_gap = kit.px(14)

        # Portrait: as tall as the space under the headline allows (100 px at most at
        # the reference size), at a FIXED spot 15% into the section and centred
        # vertically. It used to be centred together with the text, so heroes with
        # longer titles shifted it sideways (owner feedback 2026-10-09).
        area_h = general.bottom - y
        icon_size = max(24, min(area_h, kit.px(100)))
        icon_x = general.left + int(general.w * 0.15)
        icon_y = y + max(0, (area_h - icon_size) // 2)
        icon_rect = pygame.Rect(icon_x, icon_y, icon_size, icon_size)
        self.hero_view_portrait_rect = icon_rect  # For the tests (position is fixed)
        # Clicking the portrait pans the map to the hero's Keep, like the portrait on
        # the sidebar Heroes tab card (same UIConstants.SIDEBAR_CAMERA_PAN switch)
        portrait_clickable = UIConstants.SIDEBAR_CAMERA_PAN
        portrait_flash = ('bottom_button', ('hero_portrait', hero_name))
        portrait_hover = portrait_clickable and icon_rect.collidepoint(self.mouse_pos)
        portrait_click = portrait_clickable and self.clicked_element == portrait_flash
        if portrait_clickable:
            self.hero_view_portrait_button = (icon_rect, hero_name)

        # The text column takes whatever width is left right of the portrait
        max_text_w = max(40, general.right - icon_rect.right - text_gap)
        title_lines = [kit.fit(line, 'italic', max_text_w) for line in description_lines]
        label_w = kit.font('body_bold').size("Location: ")[0]
        location_text = kit.fit(location, 'body', max(20, max_text_w - label_w))

        if self.hero_images.get(hero_name):
            # PERFORMANCE: cached scaled portrait (keyed by size); hover/click brighten it
            portrait = self._get_cached_scaled_surface(
                self.hero_images[hero_name], f'hero_{hero_name}', icon_size, icon_size)
            self.screen.blit(self._apply_icon_overlay(portrait, portrait_click, portrait_hover),
                             icon_rect.topleft)
        else:
            # Fallback: letter tile
            pygame.draw.rect(self.screen, (150, 100, 200), icon_rect, border_radius=8)
            kit.centered_text(hero_letter, 'title', WHITE, icon_rect.centerx,
                              icon_rect.centery - kit.line_height('title') // 2)
        frame_color = (255, 232, 160) if (portrait_hover or portrait_click) else (212, 170, 80)
        pygame.draw.rect(self.screen, frame_color, icon_rect, max(2, kit.px(3)), border_radius=6)

        # Text starts level with the portrait's top edge (it used to be centred on the
        # portrait, so its start moved with the number of title lines)
        title_h = kit.line_height('italic')
        line_gap = kit.px(6)
        tx = icon_rect.right + text_gap
        ty = icon_rect.top + kit.px(2)
        for line in title_lines:
            kit.left_text(line, 'italic', title_color, tx, ty)
            ty += title_h
        ty += line_gap
        label_drawn_w = kit.left_text("Location: ", 'body_bold', label_color, tx, ty)
        kit.left_text(location_text, 'body', value_color, tx + label_drawn_w, ty)

        # === SECTION 2: ABILITIES ===
        # Three icons in a centred row, as big as the section allows (80 px at most at
        # the reference size). Availability + drawing are shared with the sidebar
        # Heroes tab (game_state.get_hero_ability_status / draw_hero_ability_icon).
        abilities_rect = rects['abilities']
        y = kit.header(abilities_rect, "Abilities")
        slots = 3
        ability_spacing = kit.px(14)
        ability_size = max(24, min(kit.px(80), abilities_rect.bottom - y,
                                   (abilities_rect.w - ability_spacing * (slots - 1)) // slots))
        row_w = slots * ability_size + (slots - 1) * ability_spacing
        ability_x = abilities_rect.centerx - row_w // 2
        ability_y = y + max(0, (abilities_rect.bottom - y - ability_size) // 2)

        # Clear ability buttons dict
        self.hero_ability_buttons = {}

        # Track ability button hover
        current_ability_hover = None
        digit_font = kit.font('title')  # Cooldown digits on the icon

        for i in range(slots):
            ability_rect = pygame.Rect(ability_x + i * (ability_size + ability_spacing), ability_y,
                                       ability_size, ability_size)

            # Store button rect for click detection
            self.hero_ability_buttons[(hero_name, i)] = ability_rect

            status = self.game_state.get_hero_ability_status(current_player, hero_name, i)
            if status is not None:
                is_hovering = ability_rect.collidepoint(self.mouse_pos)
                if is_hovering:
                    # Track hover for tooltip (both active and passive abilities)
                    current_ability_hover = ('hero_ability', (hero_name, i))
                is_clicking = status['castable'] and self.clicked_element == ('hero_ability', (hero_name, i))
                self.draw_hero_ability_icon(ability_rect, hero_name, i, status, is_hovering, is_clicking,
                                            digit_font)
            else:
                # No ability at this slot - draw empty placeholder
                pygame.draw.rect(self.screen, (60, 60, 60), ability_rect, border_radius=5)
                pygame.draw.rect(self.screen, (40, 40, 40), ability_rect, 2, border_radius=5)

        # Update button hover tracking for ability buttons
        self.update_button_hover(current_ability_hover, 'hero_ability')

        # === SECTION 3: HERO INFO ===
        self._draw_info_list_section(rects['info'], "Hero Info", [
            # Original wording, now wrapped to the section instead of hand-split lines
            "A Hero is slain when a Keep they are residing at is conquered.",
            "Hero can be re-summoned in a Keep after their death.",
        ] + (["Click the portrait to view the Hero's Keep on the map."]
             if UIConstants.SIDEBAR_CAMERA_PAN else []))  # Bulleted, like Unit Selection Info

    # Barracks view section widths (fractions right of the End Turn pillar): Barracks
    # (5 unit buttons) / Training Queue (4 slots) / Barracks Info (2 columns + Demolish).
    # Checked to fit at 720p-1440p (2026-10-09): unit buttons 57-102 px, queue slots
    # 27-46 px tall, the longest queue text fits at 720p.
    BARRACKS_VIEW_WEIGHTS = (0.36, 0.28, 0.36)
    # Extra px (reference size) above and below the headline rules in this view
    BARRACKS_HEADER_SPACING_REF = 3
    # Share of the spare height above the unit button row (0.5 = centred)
    BARRACKS_UNIT_ROW_TOP_FRAC = 0.35
    TRAINING_UNIT_ORDER = ('Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain')
    # Keyboard shortcuts listed in Barracks Info (input/keyboard_handler._TRAINING_SHORTCUTS)
    TRAINING_HOTKEYS = (('S', 'Swordsman'), ('A', 'Archer'), ('P', 'Pikeman'),
                        ('C', 'Cavalry'), ('T', 'Captain'))

    def _barracks_view_layout(self):
        """Barracks view sections: units / queue / info (see _section_layout)."""
        return self._section_layout(('units', 'queue', 'info'), self.BARRACKS_VIEW_WEIGHTS)

    def _header_with_count(self, rect, title, count_text, count_color, spacing=0):
        """kit.header() with a count after the title in its own colour, e.g.
        "Training Queue (4/4)" with the count red when full. `spacing` as in
        kit.header() (px above and below the rule). Returns the content y."""
        kit = self.bottom_panel_kit
        role = 'heading'
        full = f"{title} {count_text}"
        title_w = kit.font(role).size(title + " ")[0]
        x = rect.centerx - kit.font(role).size(full)[0] // 2
        kit.left_text(title + " ", role, BOTTOM_GOLD_TEXT, x, rect.top)
        kit.left_text(count_text, role, count_color, x + title_w, rect.top)
        return kit.rule(rect, rect.top + kit.line_height(role) + kit.px(1) + spacing) + spacing

    def _draw_section_button(self, rect, label, tint, flash_key, locked=False):
        """
        A rule and a centred ornate button at the bottom of a section (Barracks Info /
        Hero Info: Demolish). Returns (button_rect, y): y is where the rule starts,
        i.e. the bottom of the space left for the section's other content.
        """
        kit = self.bottom_panel_kit
        button_w = min(rect.w, kit.px(self.BUILDING_BUTTON_W_REF))
        button_h = kit.button_height(button_w)
        button = pygame.Rect(0, rect.bottom - button_h, button_w, button_h)
        button.centerx = rect.centerx
        rule_y = button.top - kit.rule_gap() - kit.rule_height()
        kit.rule(rect, rule_y)
        kit.ornate_button(button, label, tint, flash_key=flash_key, locked=locked)
        return button, rule_y - kit.rule_gap()

    def _draw_queue_row(self, rect, text, color, cancel_flash_key, cancel_locked):
        """
        One training-queue entry: a stretched ResourceSlot wood frame (owner choice)
        with the entry text on the left and a small red X on the right. Shared by the
        Barracks queue and the Keep's Training Status. Returns the X's rect.
        """
        kit = self.bottom_panel_kit
        border = max(3, int(rect.h * 0.17))
        # Cached per size (SidebarWidgets.nine_slice) - no per-frame surfaces
        frame = self.sidebar_widgets.nine_slice('wood', rect.size, border, fill=(30, 22, 16))
        self.screen.blit(frame, rect.topleft)

        x_size = max(10, rect.h - 2 * border - 2)
        cancel = pygame.Rect(0, 0, x_size, x_size)
        cancel.midright = (rect.right - border - kit.px(4), rect.centery)
        if cancel_locked:
            # Greyed while the tutorial/mission forbids cancelling
            fill, edge, mark = (80, 80, 80), (60, 60, 60), (130, 130, 130)
        else:
            fill, edge, mark = (170, 62, 50), (226, 186, 110), WHITE
            if self.clicked_element == cancel_flash_key:
                fill = brighten_color(fill, 0.4)
            elif cancel.collidepoint(self.mouse_pos):
                fill = lighten_color(fill, 0.2)
        pygame.draw.rect(self.screen, fill, cancel, border_radius=3)
        pygame.draw.rect(self.screen, edge, cancel, 1, border_radius=3)
        x_role = 'small_bold'
        x_surf = kit.text("X", x_role, mark)
        self.screen.blit(x_surf, x_surf.get_rect(center=cancel.center))

        text_x = rect.left + border + kit.px(6)
        avail = max(20, cancel.left - kit.px(6) - text_x)
        role = 'small'
        kit.left_text(kit.fit(text, role, avail), role, color, text_x,
                      rect.centery - kit.font(role).get_height() // 2)
        return cancel

    def _draw_fact_columns(self, rect, columns):
        """
        Side-by-side columns of (text, colour) lines in `rect`: each column's lines are
        left-aligned, and the columns are centred together as one block with a fixed
        gap between them (centring each in its own half pushed them to the edges).
        Body font, or small if the longest column does not fit the height; the lines
        are spaced to use it (capped). Bounds-checked. Returns the font role used.
        """
        kit = self.bottom_panel_kit
        rows = max(len(col) for col in columns)
        role = 'body' if rows * kit.line_height('body') <= rect.h else 'small'
        line_h = kit.line_height(role)
        gap = max(0, min(kit.px(6), (rect.h - rows * line_h) // max(1, rows)))
        col_gap = kit.px(40)
        max_col_w = max(20, (rect.w - col_gap * (len(columns) - 1)) // len(columns))
        fitted = [[(kit.fit(text, role, max_col_w), color) for text, color in col] for col in columns]
        widths = [max(kit.font(role).size(text)[0] for text, _color in col) for col in fitted]
        x = rect.left + max(0, (rect.w - sum(widths) - col_gap * (len(columns) - 1)) // 2)
        for col, col_w in zip(fitted, widths):
            y = rect.top + gap // 2
            for text, color in col:
                if y + line_h > rect.bottom + 1:
                    break  # bounds check - never render past the section
                kit.left_text(text, role, color, x, y)
                y += line_h + gap
            x += col_w + col_gap
        return role

    def draw_training_ui(self):
        """
        Draw the Barracks view (a finished Barracks selected).

        Sections (owner-designed 2026-10-09), each a centred headline + gold rule:
            Barracks:            the five unit training buttons in a centred row
            Training Queue (n/4): the queued units in 4 fixed slots (ResourceSlot rows)
            Hotkeys:             the training hotkeys, then a rule and the Demolish button
        The headlines have a little extra space around their rules.
        """
        territory, barracks_plot_index = self.selected_barracks
        gs = self.game_state
        kit = self.bottom_panel_kit
        current_player = gs.current_player
        layout = self._barracks_view_layout()
        rects = layout['rects']
        for pillar_x in layout['pillars']:
            self.draw_separator(pillar_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        current_gold = gs.player_gold[current_player]
        queue = gs.training_queue.get(territory, {}).get(barracks_plot_index, [])
        queue_count = len(queue)
        # Display armies in territory (include ALL garrisons)
        current_armies = gs.get_territory_total_armies(territory)
        at_army_limit = current_armies >= gs.MAX_ARMIES_PER_TERRITORY
        # Command limit: player's total army count against their limit
        command_count = gs.get_player_army_count(current_player)
        command_limit = gs.player_command_limit[current_player]
        at_command_limit = command_count >= command_limit
        can_queue = queue_count < gs.MAX_TRAINING_QUEUE  # same limit as start_training()

        # === SECTION 1: BARRACKS (unit buttons) ===
        # The old gold / queue / armies lines and "Not enough gold" status are gone (the
        # queue count is in its headline); the buttons' red tint shows refusals
        units_rect = rects['units']
        # A little more air between the headlines and their rules (owner: the rule sat
        # too close to "Barracks"); all three sections use it so the rules stay level
        header_spacing = kit.px(self.BARRACKS_HEADER_SPACING_REF)
        y = kit.header(units_rect, "Barracks", spacing=header_spacing)
        button_spacing = kit.px(10)
        slots = len(self.TRAINING_UNIT_ORDER)
        button_size = max(24, min(kit.px(72), units_rect.bottom - y,
                                  (units_rect.w - button_spacing * (slots - 1)) // slots))
        row_w = slots * button_size + (slots - 1) * button_spacing
        button_x = units_rect.centerx - row_w // 2
        # Spare height above the row: a bit less than half (owner: the centred row sat
        # a little far below the rule)
        button_y = y + max(0, int((units_rect.bottom - y - button_size) * self.BARRACKS_UNIT_ROW_TOP_FRAC))

        # Unit type colors (for fallback letter buttons)
        unit_colors = {
            'Swordsman': (100, 100, 150),  # Blue-gray
            'Archer': (100, 150, 100),     # Green
            'Pikeman': (120, 90, 70),      # Brown
            'Cavalry': (180, 140, 60),     # Gold
            'Captain': (160, 120, 180)     # Purple
        }

        self.train_buttons = {}
        for unit_type in self.TRAINING_UNIT_ORDER:
            unit_info = gs.UNIT_TYPES[unit_type]
            # Use discounted cost for affordability check (fixes red tint persisting after discount)
            unit_cost = gs.get_effective_cost(unit_type, unit_info['cost'])
            can_afford = current_gold >= unit_cost
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

            train_button_rect = pygame.Rect(button_x, button_y, button_size, button_size)
            is_hovering = train_button_rect.collidepoint(self.mouse_pos)
            is_clicking = (self.clicked_element and
                           self.clicked_element[0] == 'training' and
                           self.clicked_element[1] == unit_type)

            unit_icon = self.unit_icons.get(unit_type)
            if unit_icon:
                # PERFORMANCE: cached scaled icon (fixes 80->40 FPS drop)
                icon_size = button_size - 4  # Slightly smaller than button
                cached_icon = self._get_cached_ui_icon(unit_icon, f'unit_{unit_type}', icon_size)

                # Working copy only when an overlay is needed
                display_icon = cached_icon
                if not is_available or is_clicking or is_hovering:
                    display_icon = cached_icon.copy()
                    overlays = self._cached_training_overlays.setdefault(icon_size, {})
                    # Tint when unavailable (cached by icon_size): grey when locked by
                    # the tutorial/mission, red when a game rule refuses it
                    if not is_available:
                        tint_key = 'grey' if training_locked else 'red'
                        if tint_key not in overlays:
                            s = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            s.fill((110, 110, 110, 255) if training_locked else (255, 100, 100, 128))
                            overlays[tint_key] = s
                        display_icon.blit(overlays[tint_key], (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    # Hover/click brightness (cached by icon_size)
                    if is_clicking or is_hovering:
                        key = 'bright' if is_clicking else 'light'
                        if key not in overlays:
                            s = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                            s.fill((100, 100, 100, 100) if is_clicking else (50, 50, 50, 50))
                            overlays[key] = s
                        display_icon.blit(overlays[key], (0, 0), special_flags=pygame.BLEND_RGB_ADD)

                self.screen.blit(display_icon, display_icon.get_rect(center=train_button_rect.center))
                # Border 2 px larger than the icon (1 px per side) to contain its edges
                if self.icon_border:
                    cached_border = self._get_cached_ui_icon(self.icon_border, 'icon_border', icon_size + 2)
                    self.screen.blit(cached_border, cached_border.get_rect(center=train_button_rect.center))
            else:
                # Fallback letter button: grey when locked by the tutorial/mission,
                # red when a game rule refuses it
                if is_available:
                    button_color = unit_colors[unit_type]
                else:
                    button_color = (120, 120, 120) if training_locked else (200, 100, 100)
                self.draw_letter_button(train_button_rect, unit_info['letter'], button_color,
                                        letter_color=WHITE, button_type='training', button_id=unit_type)

            # Tutorial hook: pulsing green border on a highlighted button
            if self._is_tutorial_active():
                if self.tutorial_mission.should_highlight_button(f'training_{unit_type}'):
                    pulse = int(180 + 75 * math.sin(pygame.time.get_ticks() / 200.0))
                    pygame.draw.rect(self.screen, (50, 255, 50, pulse), train_button_rect, 3)

            self.train_buttons[unit_type] = train_button_rect
            button_x += button_size + button_spacing

        # === SECTION 2: TRAINING QUEUE (n/4) ===
        queue_rect = rects['queue']
        max_queue = gs.MAX_TRAINING_QUEUE
        count_color = (232, 82, 70) if queue_count >= max_queue else BOTTOM_GOLD_TEXT
        y = self._header_with_count(queue_rect, "Training Queue", f"({queue_count}/{max_queue})", count_color,
                                    spacing=header_spacing)
        slot_gap = kit.px(5)
        slot_h = max(16, (queue_rect.bottom - y - slot_gap * (max_queue - 1)) // max_queue)
        self.queue_cancel_buttons = []
        # Tutorial hook: grey out the X buttons unless cancelling is allowed (the click
        # handler blocks it with the same check)
        cancel_locked = bool(self._is_tutorial_blocking('cancel_training'))
        if queue:
            for i, entry in enumerate(queue[:max_queue]):
                unit_type, turns_remaining = entry[0], entry[1]  # (unit_type, turns, cost_paid)
                if i == 0:
                    # First in queue - currently training
                    if turns_remaining == 0:
                        # Training paused due to army limit
                        text, color = f"{unit_type} (Army Limit Reached)", (232, 82, 70)
                    else:
                        turn_word = "turn" if turns_remaining == 1 else "turns"
                        text, color = f"{unit_type} (training... {turns_remaining} {turn_word})", (120, 210, 105)
                else:
                    text, color = f"{unit_type} (waiting)", (180, 174, 164)
                # Fixed slot positions: rows never shift with the queue length
                row = pygame.Rect(queue_rect.left, y + i * (slot_h + slot_gap), queue_rect.w, slot_h)
                cancel_rect = self._draw_queue_row(row, text, color, ('queue_cancel', i), cancel_locked)
                self.queue_cancel_buttons.append((cancel_rect, i))
        else:
            kit.centered_text("No units in queue", 'body', BROWN_TEXT_SECONDARY, queue_rect.centerx,
                              y + kit.px(6))

        # === SECTION 3: HOTKEYS (+ Demolish) ===
        # Was "Barracks Info" with gold / armies / command lines too; the owner dropped
        # those (2026-10-09), so only the hotkeys remain and the headline says so
        info_rect = rects['info']
        y = kit.header(info_rect, "Hotkeys", spacing=header_spacing)
        # Demolish refund depends on the Makeshift Barracks upgrade. Just "Demolish":
        # the headline names the building and the longer label did not fit the button.
        refund_percent = "100%" if gs.player_barracks_full_refund[current_player] else "50%"
        self.demolish_barracks_button, rows_bottom = self._draw_section_button(
            info_rect, f"Demolish ({refund_percent})", TINT_DEMOLISH, ('demolish', 'barracks'),
            locked=bool(self._is_tutorial_blocking('demolish')))
        self.demolish_barracks_territory = territory
        self.demolish_barracks_plot_index = barracks_plot_index

        # Hotkeys (Captain = T was missing from the old list) in two columns, S/A/P and
        # C/T: five lines in one column only fit in the small font
        hotkeys = [(f"[{key}] {unit}", BROWN_TEXT_SECONDARY) for key, unit in self.TRAINING_HOTKEYS]
        self._draw_fact_columns(pygame.Rect(info_rect.left, y, info_rect.w, max(1, rows_bottom - y)),
                                [hotkeys[:3], hotkeys[3:]])

        # Track button hover for tooltips (will be drawn with delay in main loop)
        mouse_pos = pygame.mouse.get_pos()
        current_hover = None
        for unit_type, button_rect in self.train_buttons.items():
            if button_rect.collidepoint(mouse_pos):
                current_hover = ('training', unit_type)
                break
        self.update_button_hover(current_hover, 'training')

    # Keep view section widths (fractions right of the End Turn pillar): Keep (4x2 hero
    # portraits) / Castle upgrade / Training Status / Hero Info (+ Demolish). Checked to
    # fit at 720p-1440p (2026-10-09): portraits 55-98 px, Castle icon 107-205 px.
    KEEP_VIEW_WEIGHTS = (0.28, 0.15, 0.22, 0.35)
    KEEP_HERO_COLUMNS = 4
    CASTLE_UPGRADE_COST = 150  # game_state.start_castle_upgrade() UPGRADE_COST

    def _keep_view_layout(self):
        """Keep view sections: heroes / castle / training / info (see _section_layout)."""
        return self._section_layout(('heroes', 'castle', 'training', 'info'), self.KEEP_VIEW_WEIGHTS)

    def _castle_section_geometry(self, rect):
        """(icon rect, bar rect) of the Castle upgrade section: the icon as big as the
        section allows above the progress bar's slot, both centred. The icon keeps
        this spot in every state (available / upgrading / Castle)."""
        kit = self.bottom_panel_kit
        bar_h = kit.px(22)
        gap = kit.px(5)
        size = max(24, min(kit.px(144), rect.w, rect.h - bar_h - gap))
        top = rect.top + max(0, (rect.h - size - gap - bar_h) // 2)
        icon = pygame.Rect(0, top, size, size)
        icon.centerx = rect.centerx
        bar_w = min(rect.w, int(size * 1.05))
        bar = pygame.Rect(0, icon.bottom + gap, bar_w, bar_h)
        bar.centerx = rect.centerx
        return icon, bar

    def _draw_keep_hero_card(self, area, hero_name):
        """
        Keep view: the hero residing at this Keep - portrait, then the name and title
        (1-2 lines) to its right, the pair centred in `area`. The whole card opens the
        Hero view like the Territory view's Forces portrait (_select_hero); hover and
        click flash brighten the portrait and its frame. Stores self.keep_hero_button
        = (card rect, hero_name) for handle_bottom_ui_click().
        """
        kit = self.bottom_panel_kit
        gap = kit.px(12)
        size = max(24, min(kit.px(90), area.h, int(area.w * 0.4)))
        text_w = max(40, area.w - size - gap)
        name_role = 'heading' if kit.font('heading').size(hero_name)[0] <= text_w else 'body_bold'
        name = kit.fit(hero_name, name_role, text_w)
        title = ' '.join(self.game_state.HERO_TYPES.get(hero_name, {}).get('description', []))
        title_lines = kit.wrap(title, 'italic', text_w, max_lines=2) if title else []
        block_w = max([kit.font(name_role).size(name)[0]] +
                      [kit.font('italic').size(line)[0] for line in title_lines])
        x = area.left + max(0, (area.w - size - gap - block_w) // 2)
        # Spare height: a bit less above than below, like the portrait grid
        top = area.top + max(0, int((area.h - size) * self.BARRACKS_UNIT_ROW_TOP_FRAC))
        portrait_rect = pygame.Rect(x, top, size, size)
        card = portrait_rect.union(pygame.Rect(portrait_rect.right, top, gap + block_w, size))

        flash_key = ('bottom_button', ('keep_hero', hero_name))
        is_clicking = self.clicked_element == flash_key
        is_hovering = card.collidepoint(self.mouse_pos)
        image = self.hero_images.get(hero_name)
        if image:
            base = self._get_cached_scaled_surface(image, f'hero_{hero_name}', size, size)
            self.screen.blit(self._apply_icon_overlay(base, is_clicking, is_hovering), portrait_rect.topleft)
        else:
            # Fallback: letter tile
            pygame.draw.rect(self.screen, (150, 100, 200), portrait_rect, border_radius=6)
            letter = self.game_state.HERO_TYPES.get(hero_name, {}).get('letter', hero_name[0])
            kit.centered_text(letter, 'title', WHITE, portrait_rect.centerx,
                              portrait_rect.centery - kit.line_height('title') // 2)
        frame = (255, 232, 160) if (is_hovering or is_clicking) else (212, 170, 80)
        pygame.draw.rect(self.screen, frame, portrait_rect, max(2, kit.px(2)), border_radius=4)

        # Name (gold) and title (bronze italic, as in the Hero view), centred on the portrait
        name_h = kit.line_height(name_role)
        title_h = kit.line_height('italic')
        text_h = name_h + kit.px(3) + len(title_lines) * title_h
        tx = portrait_rect.right + gap
        ty = portrait_rect.centery - text_h // 2
        kit.left_text(name, name_role, BOTTOM_GOLD_TEXT, tx, ty)
        ty += name_h + kit.px(3)
        for line in title_lines:
            kit.left_text(line, 'italic', (232, 170, 100), tx, ty)
            ty += title_h
        self.keep_hero_button = (card, hero_name)

    def _draw_hero_training_progress(self, rect, hero_type, turns_remaining):
        """Keep view Training Status: the hero in a ResourceSlot row with its X, then a
        progress bar and "N turns remaining" - the sidebar Heroes tab's training card
        style (ui_renderer._draw_hero_card). Returns the X's rect."""
        kit = self.bottom_panel_kit
        slot_gap = kit.px(5)
        row_h = max(16, (rect.h - 3 * slot_gap) // 4)  # Same row height as the Barracks queue
        row = pygame.Rect(rect.left, rect.top, rect.w, row_h)
        cancel = self._draw_queue_row(row, hero_type, (245, 235, 210), ('hero_cancel', 'training'), False)

        # done / total turns; total from HERO_TYPES training_time (as the sidebar card)
        total = max(1, int(self.game_state.HERO_TYPES.get(hero_type, {}).get('training_time', turns_remaining) or 1))
        total = max(total, int(turns_remaining))
        frac = (total - turns_remaining) / float(total)
        bar = pygame.Rect(0, row.bottom + kit.px(10), int(rect.w * 0.9), max(6, kit.px(12)))
        bar.centerx = rect.centerx
        pygame.draw.rect(self.screen, (28, 20, 16), bar, border_radius=3)
        if frac > 0:
            fill = bar.inflate(-4, -4)
            fill.w = max(1, int(fill.w * frac))
            pygame.draw.rect(self.screen, (196, 150, 60), fill, border_radius=2)
        pygame.draw.rect(self.screen, (120, 86, 34), bar, 1, border_radius=3)
        self.keep_training_bar = (bar, frac)  # For the tests
        turn_word = "turn" if turns_remaining == 1 else "turns"
        kit.centered_text(f"{turns_remaining} {turn_word} remaining", 'small', (226, 210, 178),
                          rect.centerx, bar.bottom + kit.px(4))
        return cancel

    def draw_keep_ui(self):
        """
        Draw the Keep view (a finished Keep or Castle selected).

        Sections (owner-designed 2026-10-09):
            Keep / Castle:   headline + rule, the hero portraits in a fixed 4x2 grid
            Castle upgrade:  no headline - the upgrade icon (available / upgrading with
                             its turns bar and X / Castle done, not clickable)
            Training Status: headline + rule, the hero in training (ResourceSlot row
                             with X) + progress bar, as on the sidebar Heroes tab
            Hero Info:       headline + rule, Hero Limit and the rules, then a rule and
                             the Demolish button
        """
        territory, keep_plot_index = self.selected_keep
        gs = self.game_state
        kit = self.bottom_panel_kit
        current_player = gs.current_player
        layout = self._keep_view_layout()
        rects = layout['rects']
        for pillar_x in layout['pillars']:
            self.draw_separator(pillar_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)
        # Same headline spacing as the Barracks view (owner: rule a bit below the text)
        header_spacing = kit.px(self.BARRACKS_HEADER_SPACING_REF)

        current_gold = gs.player_gold[current_player]
        _, display_name = gs.get_keep_display_info(territory, keep_plot_index)  # Keep or Castle

        # Check if Keep is training
        is_training = (territory in gs.hero_training_queue and
                       keep_plot_index in gs.hero_training_queue[territory])

        # The trained hero residing at this Keep, if any (one per Keep / Castle)
        keep_hero = next((name for name, hero_data in gs.heroes.get(current_player, {}).items()
                          if hero_data['keep_territory'] == territory
                          and hero_data['keep_plot'] == keep_plot_index), None)
        keep_has_hero = keep_hero is not None

        # Hero limit (3, or 4 with Heroic Fortitude - player_hero_limit holds the current value)
        current_hero_count = len(gs.hero_ownership[current_player])
        hero_limit = gs.player_hero_limit[current_player]
        hero_limit_reached = current_hero_count >= hero_limit

        # Campaign mission 4: skip drawing hero training buttons entirely
        # when the active mission hides hero training (pre-assigned hero only)
        _hide_hero_training = (
            gs.tutorial_mission and
            hasattr(gs.tutorial_mission, 'should_hide_hero_training') and
            gs.tutorial_mission.should_hide_hero_training()
        )

        # Keep is being upgraded to a Castle: start_hero_training() refuses, so the
        # buttons must show it (they used to look available)
        keep_upgrading = gs.is_upgrading_to_castle(territory, keep_plot_index)

        # A mission that forbids hero training but still shows the buttons (the base
        # tutorial): grey them out, like other tutorial-locked controls
        hero_training_locked = bool(
            self.tutorial_mission and self.tutorial_mission.active
            and not self.tutorial_mission.is_action_allowed('train_hero'))

        # === SECTION 1: KEEP / CASTLE - hero portraits ===
        heroes_rect = rects['heroes']
        y = kit.header(heroes_rect, display_name, spacing=header_spacing)
        # Filter out campaign-only heroes (trainable: False) from the training menu
        hero_types_list = [h for h in gs.HERO_TYPES.keys() if gs.HERO_TYPES[h].get('trainable', True)]
        if keep_hero:
            # This Keep's hero (owner request 2026-10-09): portrait + name + title,
            # clickable like the Territory view's Forces portrait. It replaces the
            # grid - a Keep holds one hero, so every portrait there would be red.
            self._draw_keep_hero_card(pygame.Rect(heroes_rect.left, y, heroes_rect.w, heroes_rect.bottom - y),
                                      keep_hero)
            hero_types_list = []
        columns = self.KEEP_HERO_COLUMNS
        rows = max(1, -(-len(hero_types_list) // columns))
        spacing = kit.px(8)
        button_size = max(20, min(kit.px(72), (heroes_rect.bottom - y - spacing * (rows - 1)) // rows,
                                  (heroes_rect.w - spacing * (columns - 1)) // columns))
        grid_w = columns * button_size + (columns - 1) * spacing
        grid_h = rows * button_size + (rows - 1) * spacing
        grid_x = heroes_rect.centerx - grid_w // 2
        # Spare height: a bit less above than below, like the Barracks unit row
        grid_y = y + max(0, int((heroes_rect.bottom - y - grid_h) * self.BARRACKS_UNIT_ROW_TOP_FRAC))

        # All hero buttons use purple color (fallback letter buttons)
        hero_color_purple = (150, 100, 200)
        discount_percent = gs.player_royal_decree_discount[current_player]
        for idx, hero_type in enumerate(hero_types_list):
            if _hide_hero_training:
                break  # Skip all hero training button drawing
            hero_info = gs.HERO_TYPES[hero_type]
            hero_cost = hero_info['cost']
            # Apply Royal Decree discount for display
            if discount_percent > 0:
                hero_cost = int(hero_cost * (100 - discount_percent) / 100)
            can_afford = current_gold >= hero_cost
            already_owned = hero_type in gs.hero_ownership[current_player]
            is_disabled = (is_training or already_owned or keep_has_hero or hero_limit_reached
                           or not can_afford or keep_upgrading or hero_training_locked)

            # Fixed slots, filled row by row (4 per row)
            col, row = idx % columns, idx // columns
            train_button_rect = pygame.Rect(grid_x + col * (button_size + spacing),
                                            grid_y + row * (button_size + spacing),
                                            button_size, button_size)

            if hero_type in self.hero_images and self.hero_images[hero_type]:
                is_hovering = train_button_rect.collidepoint(self.mouse_pos)
                is_clicking = (self.clicked_element and
                               self.clicked_element[0] == 'hero_training' and
                               self.clicked_element[1] == hero_type)
                # Cached scaling + icon overlay helpers (no per-frame scale/tint)
                base_icon = self._get_cached_scaled_surface(
                    self.hero_images[hero_type], f'hero_{hero_type}', button_size, button_size)
                # Grey when locked by the tutorial/mission, red when a game rule refuses it
                hero_image_scaled = self._apply_icon_overlay(
                    base_icon, is_clicking, is_hovering,
                    enabled=not is_disabled,
                    disabled_tint=(110, 110, 110, 150) if hero_training_locked else (200, 0, 0, 120))
                self.screen.blit(hero_image_scaled, train_button_rect.topleft)
                # Border 2 px larger than the icon (1 px per side) to contain its edges
                if self.icon_border:
                    scaled_border = self._get_cached_scaled_surface(
                        self.icon_border, 'icon_border', button_size + 2, button_size + 2)
                    self.screen.blit(scaled_border, (train_button_rect.x - 1, train_button_rect.y - 1))
            else:
                # Fallback to letter button
                if hero_training_locked:
                    button_color = (120, 120, 120)  # Locked by tutorial/mission (grey)
                elif is_disabled:
                    button_color = (200, 100, 100)  # Disabled (red)
                else:
                    button_color = hero_color_purple  # Enabled (purple)
                self.draw_letter_button(train_button_rect, hero_info['letter'], button_color,
                                        letter_color=WHITE, button_type='hero_training',
                                        button_id=hero_type)

            self.hero_train_buttons[hero_type] = train_button_rect

        # === SECTION 2: CASTLE UPGRADE (no headline) ===
        castle_rect = rects['castle']
        icon_rect, bar_rect = self._castle_section_geometry(castle_rect)
        self.castle_icon_rect = icon_rect  # For the tests (fixed spot in every state)
        try:
            is_castle = gs.is_castle(territory, keep_plot_index)
            is_upgrading = gs.is_upgrading_to_castle(territory, keep_plot_index)
        except Exception as e:
            logger.error(f"ERROR in Castle upgrade check: {e}")
            is_castle = False
            is_upgrading = False

        # Castle hover tracking (tooltip), applied at the end of this method
        self.castle_button_is_hovering = False
        self.castle_button_rect_for_hover = None
        icon_w = icon_rect.w

        def draw_border():
            # Border 2 px larger than the icon (1 px per side) to contain its edges
            if self.icon_border:
                border = self._get_cached_scaled_surface(self.icon_border, 'icon_border', icon_w + 2, icon_w + 2)
                self.screen.blit(border, (icon_rect.x - 1, icon_rect.y - 1))

        def draw_fallback(color, line1, line2):
            # Text tile when the upgrade icon art is missing
            pygame.draw.rect(self.screen, color, icon_rect)
            pygame.draw.rect(self.screen, (218, 165, 32), icon_rect, 3, border_radius=5)
            kit.centered_text(line1, 'body_bold', BLACK, icon_rect.centerx,
                              icon_rect.centery - kit.line_height('body_bold'), shadow=False)
            if line2:
                kit.centered_text(line2, 'small', BLACK, icon_rect.centerx, icon_rect.centery, shadow=False)

        if is_castle:
            # Upgrade done (owner choice): the icon in full colour, not clickable, with an
            # "Upgrade Finished" caption in the bar's slot (not "Castle": the headline
            # beside it already says that). No button rect, no tooltip.
            if self.castle_upgrade_icon:
                self.screen.blit(self._get_cached_scaled_surface(
                    self.castle_upgrade_icon, 'castle_upgrade', icon_w, icon_w), icon_rect.topleft)
                draw_border()
            else:
                draw_fallback((200, 200, 100), "CASTLE", "")
            # The section is narrow (107 px at 720p): small bold if body bold won't fit
            caption = "Upgrade Finished"
            role = 'body_bold' if kit.font('body_bold').size(caption)[0] <= castle_rect.w else 'small_bold'
            kit.centered_text(kit.fit(caption, role, castle_rect.w), role, BOTTOM_GOLD_TEXT,
                              bar_rect.centerx, bar_rect.centery - kit.line_height(role) // 2)

        elif is_upgrading:
            # Upgrading: yellow-tinted icon + "N turns" bar with a cancel X
            turns_remaining = gs.castle_upgrades_in_progress[territory][keep_plot_index]
            is_button_hovering = icon_rect.collidepoint(self.mouse_pos)
            is_button_clicking = (self.clicked_element and self.clicked_element[0] == 'upgrade_castle')
            if self.castle_upgrade_icon:
                # PERFORMANCE: the yellow tint is baked once per size (it used to allocate
                # an overlay Surface every frame); hover/click via the shared helper
                key = ('castle_upgrade_yellow', icon_w)
                tinted = self._ui_icon_cache.get(key)
                if tinted is None:
                    tinted = self._get_cached_scaled_surface(
                        self.castle_upgrade_icon, 'castle_upgrade', icon_w, icon_w).copy()
                    tinted.fill((255, 220, 100, 120), special_flags=pygame.BLEND_RGBA_MULT)
                    self._ui_icon_cache[key] = tinted
                self.screen.blit(self._apply_icon_overlay(tinted, is_button_clicking, is_button_hovering),
                                 icon_rect.topleft)
                draw_border()
            else:
                color = (200, 200, 100)  # Yellow for upgrading
                if is_button_hovering and not is_button_clicking:
                    color = lighten_color(color, 0.2)
                draw_fallback(color, "UPGRADE", "TO CASTLE")

            # Progress bar under the icon (as before, now sized to the section)
            pygame.draw.rect(self.screen, (220, 220, 220), bar_rect)
            pygame.draw.rect(self.screen, (218, 165, 32), bar_rect, 2)
            turn_word = "turn" if turns_remaining == 1 else "turns"
            turns_surf = kit.text(f"{turns_remaining} {turn_word}", 'small', (100, 100, 0))
            self.screen.blit(turns_surf, (bar_rect.x + kit.px(5),
                                          bar_rect.y + (bar_rect.h - turns_surf.get_height()) // 2))

            # Cancel button (X) at the bar's right end
            cancel_size = max(10, bar_rect.h - 4)
            cancel_rect = pygame.Rect(0, 0, cancel_size, cancel_size)
            cancel_rect.midright = (bar_rect.right - kit.px(3), bar_rect.centery)
            cancel_color = (150, 100, 100)
            if self.clicked_element and self.clicked_element[0] == 'cancel_castle_upgrade':
                cancel_color = brighten_color(cancel_color, 0.4)
            elif cancel_rect.collidepoint(self.mouse_pos):
                cancel_color = lighten_color(cancel_color, 0.2)
            pygame.draw.rect(self.screen, cancel_color, cancel_rect)
            pygame.draw.rect(self.screen, BLACK, cancel_rect, 1)
            x_surf = kit.text("X", 'small_bold', WHITE)
            self.screen.blit(x_surf, x_surf.get_rect(center=cancel_rect.center))
            self.castle_upgrade_cancel_button = cancel_rect

            # Tooltip over the icon (not over the X)
            castle_hover = is_button_hovering and not cancel_rect.collidepoint(self.mouse_pos)
            self.castle_button_is_hovering = castle_hover
            self.castle_button_rect_for_hover = icon_rect if castle_hover else None

        else:
            # Upgrade available (or refused: hero training / not enough gold)
            button_enabled = not is_training and current_gold >= self.CASTLE_UPGRADE_COST
            is_hovering = icon_rect.collidepoint(self.mouse_pos)
            is_clicking = (self.clicked_element and self.clicked_element[0] == 'upgrade_castle')
            if self.castle_upgrade_icon:
                base_icon = self._get_cached_scaled_surface(
                    self.castle_upgrade_icon, 'castle_upgrade', icon_w, icon_w)
                self.screen.blit(self._apply_icon_overlay(base_icon, is_clicking, is_hovering,
                                                          enabled=button_enabled), icon_rect.topleft)
                draw_border()
            else:
                color = (100, 150, 200) if button_enabled else (150, 100, 100)
                if button_enabled:
                    if is_clicking:
                        color = brighten_color(color, 0.4)
                    elif is_hovering:
                        color = lighten_color(color, 0.2)
                draw_fallback(color, "UPGRADE", "TO CASTLE")
            # Store button for click handling (only if enabled)
            self.castle_upgrade_button = icon_rect if button_enabled else None
            # Tooltip even when disabled (it explains why)
            self.castle_button_is_hovering = is_hovering
            self.castle_button_rect_for_hover = icon_rect if is_hovering else None

        # === SECTION 3: TRAINING STATUS ===
        training_rect = rects['training']
        y = kit.header(training_rect, "Training Status", spacing=header_spacing)
        self.keep_training_bar = None
        if is_training:
            # Format: (hero_type, turns_remaining[, paid_cost]) - index access
            entry = gs.hero_training_queue[territory][keep_plot_index]
            hero_type, turns_remaining = entry[0], entry[1]
            self.hero_cancel_button = self._draw_hero_training_progress(
                pygame.Rect(training_rect.left, y, training_rect.w, training_rect.bottom - y),
                hero_type, turns_remaining)
        else:
            kit.centered_text("No hero in training", 'body', BROWN_TEXT_SECONDARY, training_rect.centerx,
                              y + kit.px(6))

        # === SECTION 4: HERO INFO (+ Demolish) ===
        info_rect = rects['info']
        y = kit.header(info_rect, "Hero Info", spacing=header_spacing)
        # Mission hook: grey out demolish only when the mission disallows it — the
        # same test the click handler uses. (It used to grey out for ANY active
        # mission, so Keeps looked undemolishable in missions that allow it.)
        # Castles refund 50% too (upgrade cost included, destroy_building()).
        self.demolish_keep_button, rows_bottom = self._draw_section_button(
            info_rect, "Demolish (50%)", TINT_DEMOLISH, ('demolish', 'keep'),
            locked=bool(self._is_tutorial_blocking('demolish')))
        self.demolish_keep_territory = territory
        self.demolish_keep_plot_index = keep_plot_index
        # Hero Limit first (red once reached - 3, or 4 with Heroic Fortitude), then the rules
        limit_color = (232, 82, 70) if hero_limit_reached else BROWN_TEXT_PRIMARY
        self._draw_info_list(pygame.Rect(info_rect.left, y, info_rect.w, max(1, rows_bottom - y)), [
            (f"Hero Limit: {current_hero_count}/{hero_limit}", limit_color, False),
            "Each Hero can only be trained once.",
            "Each Keep or Castle can only have one Hero.",
            "Heroes are slain upon Keep or Castle's destruction.",
        ])

        # Track button hover for tooltips (will be drawn with delay in main loop)
        mouse_pos = pygame.mouse.get_pos()
        current_hover = None
        for hero_type, button_rect in self.hero_train_buttons.items():
            if button_rect.collidepoint(mouse_pos):
                current_hover = ('hero_training', hero_type)
                break
        self.update_button_hover(current_hover, 'hero_training')

        # Castle upgrade button hover tracking (must come AFTER hero_training to take precedence)
        if self.castle_button_is_hovering:
            self.update_button_hover(('castle', 'castle_upgrade'), 'castle')
        elif self.hover_target_button and self.hover_target_button[0] == 'castle':
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

        # Section geometry (pillars + content rects) - shared with the tests
        kit = self.bottom_panel_kit
        gs = self.game_state
        layout = self._army_view_layout()
        rects = layout['rects']
        for pillar_x in layout['pillars']:
            self.draw_separator(pillar_x, BOTTOM_UI_Y, BOTTOM_UI_HEIGHT)

        # Clear old button state before creating new buttons
        self.army_composition_buttons = []
        self.select_all_button = None
        self.deselect_all_button = None

        # === SECTION 1: ARMY INFO ===
        # "Army: <territory>" centred in the garrison player's colour (not the
        # territory owner's), then a rule with an upright rule hanging from it (a T):
        # status counts on the left, Select / Deselect All on the right.
        info = rects['info']
        display_territory = map_data.get_display_name(territory)  # Campaign renames
        player_color = gs.get_player_color(player) if player != -1 else BROWN_TEXT_PRIMARY
        # Extra space around the rule (owner: the lines needed more breathing room)
        header_spacing = kit.px(3)
        y = kit.header(info, f"Army: {display_territory}", color=player_color, role='title',
                       spacing=header_spacing)
        # The T hangs from the rule's centre diamond: kit.rule() centres the art on
        # info.centerx, and the diamond sits mid-art, 3 px below the art's top
        rule_top = y - header_spacing - kit.rule_gap() - kit.rule_height()
        split_x = info.centerx
        kit.vertical_rule(split_x, rule_top + 3, info.bottom)
        col_pad = kit.px(10)
        left = pygame.Rect(info.left, y, split_x - col_pad - info.left, info.bottom - y)
        right = pygame.Rect(split_x + col_pad, y, info.right - split_x - col_pad, info.bottom - y)

        # Left column. Total = this garrison's units, coloured by how close the
        # TERRITORY is to the army limit (all garrisons count towards it) - the same
        # colours as the Territory view's Army Limit
        territory_total = gs.get_territory_total_armies(territory)
        facts = [
            (f"Total: {total}/{gs.MAX_ARMIES_PER_TERRITORY}", self._army_limit_color(territory_total), 'body_bold'),
            (f"Ready to Move: {ready_count}", (120, 210, 105), 'body'),  # Green: can be ordered
            (f"Moved: {moved_count}", (180, 174, 164), 'body'),          # Grey: exhausted
            (f"Ordered: {ordered_count}", (238, 206, 92), 'body'),       # Yellow: has an order
        ]
        line_h = kit.line_height('body')
        fact_gap = max(kit.px(3), min(kit.px(14), (left.h - len(facts) * line_h) // len(facts)))
        # The lines stay left-aligned with each other, but the block is centred in the
        # column (owner: it sat far from the T's upright, hugging the pillar)
        texts = [(kit.fit(text, role, left.w), color, role) for text, color, role in facts]
        block_w = max(kit.font(role).size(text)[0] for text, _c, role in texts)
        fx = left.left + max(0, (left.w - block_w) // 2)
        fy = left.top + kit.px(2)
        for text, color, role in texts:
            if fy + line_h > left.bottom + 1:
                break  # bounds check
            kit.left_text(text, role, color, fx, fy)
            fy += line_h + fact_gap

        # Right column: Select All (blue) / Deselect All (red) + selection count,
        # centred vertically. Hover uses hover_pos (the context menu blocks it).
        button_w = min(right.w, kit.px(150))
        button_h = kit.button_height(button_w)
        selected_h = kit.line_height('small_bold')
        gap = kit.px(10)  # Owner: the two buttons sat too close together
        block_h = 2 * button_h + selected_h + 2 * gap
        by = right.top + max(0, (right.h - block_h) // 2)
        select_all_rect = pygame.Rect(0, by, button_w, button_h)
        select_all_rect.centerx = right.centerx
        deselect_all_rect = select_all_rect.move(0, button_h + gap)
        kit.ornate_button(select_all_rect, "Select All", TINT_SELECT_ALL,
                          flash_key=('army_comp', 'select_all'), role='body_bold', hover_pos=hover_pos)
        kit.ornate_button(deselect_all_rect, "Deselect All", TINT_DESELECT_ALL,
                          flash_key=('army_comp', 'deselect_all'), role='body_bold', hover_pos=hover_pos)
        self.select_all_button = select_all_rect
        self.deselect_all_button = deselect_all_rect
        kit.centered_text(f"Selected: {len(self.selected_army_units)}", 'small_bold', (140, 195, 245),
                          right.centerx, deselect_all_rect.bottom + gap)

        # === SECTION 2: UNITS ===
        # "Units" + rule, then the unit buttons: 5 per row, up to 3 rows (the army
        # limit), sized to fit the section (smaller at 1280x720) and centred
        units_rect = rects['units']
        grid_y = kit.header(units_rect, "Units")
        buttons_per_row = 5
        max_rows = 3
        button_spacing = max(2, kit.px(5))
        button_size = max(16, min(
            kit.px(45),
            (units_rect.bottom - grid_y - button_spacing * (max_rows - 1)) // max_rows,
            (units_rect.w - button_spacing * (buttons_per_row - 1)) // buttons_per_row))
        grid_w = buttons_per_row * button_size + (buttons_per_row - 1) * button_spacing
        grid_x = units_rect.centerx - grid_w // 2
        # Veterancy: XP bar and shields drawn OVER the button icon (no extra vertical space)
        xp_bar_height = max(2, kit.px(3))   # Height of XP progress bar (overlaid at bottom edge)
        row_height = button_size + button_spacing

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

        # === SECTION 3: UNIT SELECTION INFO ===
        self._draw_info_list_section(rects['help'], "Unit Selection Info", [
            "Click to select",
            "CTRL+Click for multi-select",
            "Right-click unit for options",
            "Right-click destination to command",
            "Click elsewhere to close",
        ])

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

            # Sequential mode: planning timer (multiplayer: the turn owner's PC only), the
            # multiplayer AFK rules for battles, the final state (see _update_sequential_turn)
            self._update_sequential_turn(delta_time)

            # Simultaneous mode: deferred execution, planning timers, ready-state broadcast,
            # AI battles / alliance choices, AFK rules, new rounds (see _update_simultaneous)
            if self.sim_state is not None:
                self._update_simultaneous(delta_time)

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

            # (A computer player's turn is started by _update_sequential_turn() above -
            # _update_ai_turn_start(); multiplayer: on the host only)

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
                battle_index = self._selected_battle_current_index()
                if battle_index is None:
                    # Another player resolved this battle while the window was open (a
                    # remote result shifts pending_battles): nothing left to fight here
                    logger.warning(f"[BATTLE] Battle at {self.selected_battle_territory} is no "
                                   f"longer pending - closing the battle window")
                    self._close_battle_window()
                    return True

                # Resolve the actual battle in game state (this removes battle from
                # pending_battles); multiplayer: seeded, so the other PCs replay it
                battle, battle_seed = self._resolve_battle_locally(battle_index)
                territory = battle.territory

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
                alliance_marker = self._alliance_marker_for(battle, territory)
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
                    'alliance_marker': alliance_marker,
                    # The network message is built NOW, from the battle's outcome. It is
                    # sent on CLOSE; the territory could hold something else by then (the
                    # old code read the garrison at CLOSE and sometimes sent no survivors).
                    'payload': (self._battle_resolve_payload(
                        battle, territory, battle_seed, alliance_marker,
                        self.game_state.last_battle_reports) if self.multiplayer_mode else None),
                    # When FIGHT was pressed: a report left open this long is closed by
                    # the simultaneous-mode AFK rules (_sim_afk_watchdog)
                    'fought_at': time.monotonic(),
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
                    battle_index = self._selected_battle_current_index()
                    if battle_index is None:
                        # Resolved by someone else while the popup was open
                        self._close_battle_window()
                        return True
                    battle = self.game_state.pending_battles[battle_index]
                    territory = battle.territory
                    armies_copy = dict(battle.armies)  # Copy armies before resolution
                    compositions_copy = dict(battle.army_compositions) if hasattr(battle, 'army_compositions') else {}
                    has_keep = (hasattr(battle, 'keep_bonus_player') and
                               battle.keep_bonus_player is not None and
                               battle.keep_bonus > 0)
                    defender = battle.original_owner

                    # Resolve the battle (multiplayer: seeded, replayed by the other PCs)
                    battle, battle_seed = self._resolve_battle_locally(battle_index)

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

                    # Simultaneous mode: allied capture -> alliance marker (shared rule)
                    alliance_marker = self._alliance_marker_for(battle, territory)
                    if alliance_marker:
                        self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)

                    # MULTIPLAYER: Send battle result to remote player (seed + outcome)
                    if self.multiplayer_mode:
                        self._send_action_to_remote(MessageType.BATTLE_RESOLVE, self._battle_resolve_payload(
                            battle, territory, battle_seed, alliance_marker,
                            self.game_state.last_battle_reports))

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
                    self.selected_battle_territory = None
                    self.battle_popup_state = 'initial'
                    self.battle_result = None  # Clear stored result

                    # Check if all battles are resolved and turn should advance
                    # Skip in simultaneous mode - sim mode uses complete_round() instead
                    # (Multiplayer: TURN_END goes out from the turn-advance hook)
                    if self.game_state.ready_to_advance_turn and self.sim_state is None:
                        logger.info(f"[TURN_DEBUG] battle_popup close (close_btn): advancing turn")
                        self.game_state._advance_to_next_player()

                    return True

            # In result state, click anywhere outside close button also closes popup
            self.battle_popup_visible = False
            self.selected_battle_index = None
            self.selected_battle_territory = None
            self.battle_popup_state = 'initial'
            self.battle_result = None

            # Check if all battles are resolved and turn should advance
            # Skip in simultaneous mode - sim mode uses complete_round() instead
            # (Multiplayer: TURN_END goes out from the turn-advance hook)
            if self.game_state.ready_to_advance_turn and self.sim_state is None:
                logger.info(f"[TURN_DEBUG] battle_popup close (click_outside): advancing turn")
                self.game_state._advance_to_next_player()

            return True

        # Resolving state: Ignore clicks (animation in progress)
        # Return True to consume the click and prevent it from reaching map handlers
        return True

    # ========== BATTLE RESOLUTION + NETWORK SYNC (shared by every resolve site) ==========

    def _resolve_battle_locally(self, battle_index):
        """
        Resolve pending_battles[battle_index] on this PC and return (battle, seed).

        Every place that resolves a battle - FIGHT, Resolve Remaining Battles, AI
        auto-resolve - goes through here. In multiplayer the battle's random parts (tie
        dice, Safe Haven retreat) come from a fresh seed that the BATTLE_RESOLVE message
        carries, so the other PCs replay the identical battle
        (_handle_remote_battle_resolve). Single-player passes no rng: unchanged
        behaviour, seed None.
        """
        battle = self.game_state.pending_battles[battle_index]
        seed = None
        rng = None
        if self.multiplayer_mode:
            seed = random.getrandbits(31)
            rng = random.Random(seed)
        self.game_state.resolve_battle(battle_index, rng=rng)
        return battle, seed

    def _alliance_marker_for(self, battle, territory):
        """
        Simultaneous mode: the alliance marker for a battle just resolved - allies who
        captured a territory together choose its new owner - or None. A defensive win
        (the original owner's team held) and a neutral win need no marker.
        """
        if self.sim_state is None or not battle.resolved or not hasattr(battle, 'team_members_map'):
            return None
        winner = battle.winner
        if winner is None or winner == -1 or winner not in battle.team_members_map:
            return None
        winning_team_members = battle.team_members_map[winner]
        original_owner = getattr(battle, 'original_owner', -1)
        original_owner_team = self.game_state.player_teams[original_owner] if original_owner >= 0 else -1
        winner_team = self.game_state.player_teams[winner]
        if len(winning_team_members) <= 1 or (original_owner >= 0 and original_owner_team == winner_team):
            return None
        return {
            'type': 'alliance',
            'territory': territory,
            'players': winning_team_members,
            'chooser': self.sim_state.phase_manager.alliance_handler.determine_chooser(
                territory, winning_team_members
            )
        }

    def _battle_resolve_payload(self, battle, territory, seed, alliance_marker=None,
                                battle_reports=None):
        """
        BATTLE_RESOLVE data for a battle this PC just resolved. Build it right after
        resolve_battle() - the garrisons it carries must be the battle's outcome, not
        whatever the territory holds when the report window is closed.

        battle_seed: receivers replay the battle from it (full side effects).
        garrisons:   the territory's garrisons after the battle with FULL unit dicts
                     (type, xp, level) - the replay is checked against them, and they are
                     the fallback when a replay is impossible. (The old message carried
                     only {id, type, status}: survivors lost their veterancy.)
        surviving_units: the winner's units, for receivers without the new path.
        """
        gs = self.game_state
        new_owner = gs.territory_owners.get(territory, -1)
        garrisons = gs.territory_garrisons.get(territory, {})

        def plain(unit):
            return {k: v for k, v in unit.items() if k != 'order'}

        data = {
            'territory': territory,
            'winner': battle.winner if battle.resolved else -1,
            'surviving_armies': getattr(battle, 'surviving_armies', 0),
            'new_owner': new_owner,
            'battle_seed': seed,
            'garrisons': {
                str(player): {
                    'unmoved': g.get('unmoved', 0),
                    'moved': g.get('moved', 0),
                    'units': [plain(u) for u in g.get('units', [])],
                }
                for player, g in garrisons.items()
            },
        }
        winner_units = garrisons.get(new_owner, {}).get('units', []) if new_owner is not None else []
        if winner_units:
            data['surviving_units'] = [plain(u) for u in winner_units]
        if alliance_marker:
            data['alliance_marker'] = alliance_marker
        if battle_reports:
            # Only read by receivers that cannot replay the battle (they generate
            # their own reports when they do)
            data['battle_reports'] = list(battle_reports)
        return data

    def _sync_battle_eliminations_to_sim(self, context):
        """
        Capital Assault: game_state.eliminate_player() runs inside resolve_battle(), but
        sim_state keeps its own eliminated list that path never updates - mirror any
        player left without territories.
        """
        if self.sim_state is None or self.game_state.victory_condition != "Capital Assault":
            return
        for pid in range(self.game_state.num_players):
            if (pid not in self.sim_state.eliminated_players and
                    all(owner != pid for owner in self.game_state.territory_owners.values())):
                self.sim_state.eliminate_player(pid)
                logger.info(f"[SIM] Synced elimination of Player {pid + 1} to sim_state {context}")

    def _selected_battle_current_index(self):
        """
        Where the battle the window shows sits in pending_battles NOW, or None if it is
        gone (another player resolved it while the window was open). Looked up by
        territory: the index saved at marker click shifts when an earlier battle is
        resolved by someone else.
        """
        battles = self.game_state.pending_battles
        territory = self.selected_battle_territory
        if territory is None:
            index = self.selected_battle_index
            return index if index is not None and 0 <= index < len(battles) else None
        for i, battle in enumerate(battles):
            if battle.territory == territory:
                return i
        return None

    def _close_battle_window(self):
        """Drop the battle window and its selection (nothing left to resolve in it)."""
        self.enhanced_battle_ui = None
        self.battle_popup_visible = False
        self.selected_battle_index = None
        self.selected_battle_territory = None
        self._resolved_battle_info = None

    def _in_battle_phase(self):
        """Battles are being fought now (sequential 'battles' / simultaneous 'resolving')."""
        if self.sim_state is not None:
            return self.sim_state.sim_phase == 'resolving'
        return self.game_state.turn_phase == 'battles'

    def _apply_battle_outcome(self, territory, data):
        """
        Put a remote battle's outcome into this territory as-is: owner + garrisons from
        the message. The fallback when the battle cannot be replayed here (older sender,
        battle missing), and the correction when our replay came out differently.
        """
        gs = self.game_state
        new_owner = data.get('new_owner')
        gs.territory_owners[territory] = new_owner
        gs._territory_owners_version += 1  # FPS OPT: Invalidate overlay cache
        gs.invalidate_territorial_bonus_cache()  # Ownership changed
        # Ownership drives income and army totals too (these caches were left stale)
        gs.invalidate_income_cache()
        gs.invalidate_army_count_cache()

        garrisons = data.get('garrisons')
        if isinstance(garrisons, dict):
            # Every garrison left in the territory, full unit dicts (incl. allies)
            gs.territory_garrisons[territory] = {
                int(player): {
                    'unmoved': g.get('unmoved', 0),
                    'moved': g.get('moved', 0),
                    'units': [dict(u) for u in g.get('units', [])],
                }
                for player, g in garrisons.items()
            }
            gs.sync_legacy_garrison_data(territory)
        else:
            # Older senders: only the winner's units. Clear ALL garrisons first (losers'
            # armies are destroyed), then set the winner's (just fought, can't move).
            # Without a unit list set_garrison_armies() falls back to default Swordsmen.
            if territory in gs.territory_garrisons:
                gs.territory_garrisons[territory].clear()
            gs.set_garrison_armies(territory, new_owner, unmoved=0,
                                   moved=data.get('surviving_armies', 0),
                                   units=data.get('surviving_units'))

    def _enforce_remote_battle_outcome(self, territory, data, apply=True):
        """
        After replaying a remote battle: if our result differs from the resolver's (the
        two PCs' states had already drifted apart), the resolver's outcome for this
        territory wins - it is what that player saw. apply=False (the simultaneous-mode
        host, whose replay stands): the difference is only logged.
        """
        gs = self.game_state

        def summary(garrisons):
            return {int(player): sorted((u.get('type'), u.get('id'), u.get('level') or 0)
                                        for u in g.get('units', []))
                    for player, g in garrisons.items() if g.get('units')}

        expected_owner = data.get('new_owner')
        mismatch = expected_owner is not None and gs.territory_owners.get(territory) != expected_owner
        garrisons = data.get('garrisons')
        if isinstance(garrisons, dict):
            mismatch = mismatch or summary(garrisons) != summary(gs.territory_garrisons.get(territory, {}))
        if mismatch and not apply:
            logger.warning(f"[NETWORK] Replayed battle at {territory} differs from the resolver's "
                           f"result - keeping ours (the host's result stands)")
        elif mismatch:
            logger.warning(f"[NETWORK] Replayed battle at {territory} differs from the resolver's "
                           f"result - applying theirs")
            self._apply_battle_outcome(territory, data)

    def _handle_remote_battle_resolve(self, message, allow_hold=True):
        """
        Another player resolved a battle: make the same battle happen here.

        With 'battle_seed' the battle is REPLAYED with the resolver's seed, so
        resolve_battle() produces every side effect here as well - destroyed buildings,
        slain heroes, Pillage / Scavenge gold, Safe Haven, stats, this PC's Battle
        Reports and hero-death toasts. The old path below only set the owner and the
        survivors, so the losing side kept its buildings and heroes. The replay is then
        checked against the resolver's result (_enforce_remote_battle_outcome).

        Without a seed (older senders, tests) or without the battle here, the result is
        applied as sent (_apply_battle_outcome).

        A result can arrive while our own copy of the move is still animating - the
        battle does not exist here yet. Then the message (and everything after it) is
        held until it does (_hold_network_message).
        """
        data = message.get('data', {})
        gs = self.game_state
        territory = data.get('territory')
        seed = data.get('battle_seed')
        new_owner = data.get('new_owner')
        surviving_armies = data.get('surviving_armies', 0)  # Bug 3 fix: default 0 prevents None < 0 TypeError
        alliance_marker = data.get('alliance_marker')  # For simultaneous mode
        battle_reports = data.get('battle_reports') or []  # Defender summaries
        logger.info(f"[NETWORK] Remote player resolved battle at {territory}")

        index = next((i for i, b in enumerate(gs.pending_battles) if b.territory == territory), None)
        if index is None and allow_hold and self._battles_may_still_appear():
            logger.info(f"[NETWORK] Battle result for {territory} arrived before our armies did - holding it")
            self._hold_network_message(message)
            return

        # A client's result counts only for a battle that exists here, and only from the
        # player who resolves it (simultaneous mode: its designated resolver - the turn
        # owner in sequential mode is checked in _refusal_for). The host's results (AI,
        # AFK fallback, its own battles) are always taken. A client's result for a
        # territory without a battle used to be applied as sent: any owner, any army.
        sender = self._message_sender(message)
        if sender is not None:
            if index is None:
                logger.warning(f"[NETWORK] REJECTED: Battle result for {territory} from Player "
                               f"{sender + 1} - no pending battle there")
                return
            resolver = getattr(gs.pending_battles[index], 'resolver', None)
            if self.sim_state is not None and resolver is not None and resolver != sender:
                logger.warning(f"[NETWORK] REJECTED: Battle result for {territory} from Player "
                               f"{sender + 1} - Player {resolver + 1} resolves it")
                return

        if index is not None and isinstance(seed, int):
            # Replay the resolver's battle
            gs.resolve_battle(index, rng=random.Random(seed))
            if self.sim_state is not None:
                # Simultaneous mode ends rounds via complete_round(), never the sequential flag
                gs.ready_to_advance_turn = False
            # A different result means the states had drifted apart. Sequential mode: the
            # turn owner's result wins (its TURN_END would bring it anyway). Simultaneous
            # mode on the host - the authority for the round - our own replay stands, so a
            # client cannot claim a battle result its seed does not give; the round's end
            # snapshot brings everyone to it.
            self._enforce_remote_battle_outcome(
                territory, data, apply=not (self.sim_state is not None and self.local_player_index == 0))
        else:
            if index is None and not self._in_battle_phase():
                logger.warning(f"[NETWORK] REJECTED: Battle result for {territory} - no pending battle found")
                return
            # VALIDATION: Basic sanity checks on battle result
            if new_owner is None or surviving_armies is None or surviving_armies < 0:
                logger.warning(f"[NETWORK] REJECTED: Invalid battle result - new_owner={new_owner}, surviving_armies={surviving_armies}")
                return
            if index is None:
                # The battle is gone here (e.g. we resolved it ourselves meanwhile) - the
                # resolver's outcome still decides the territory
                logger.warning(f"[NETWORK] No pending battle at {territory} - applying the resolver's result")
            self._apply_battle_outcome(territory, data)
            if index is not None:
                gs.pending_battles.pop(index)
                logger.info(f"[NETWORK] Removed battle for {territory}, {len(gs.pending_battles)} battles remaining")

            # Capital Assault: run full elimination on client for battle-captured capitals
            if (self.sim_state is not None and
                gs.victory_condition == "Capital Assault" and
                hasattr(gs, 'player_starting_territories')):
                for player_index, capital in gs.player_starting_territories.items():
                    if (capital == territory and player_index != new_owner and
                        player_index not in self.sim_state.eliminated_players and
                        not gs.are_allies(new_owner, player_index)):
                        gs.eliminate_player(player_index)
                        self.sim_state.eliminate_player(player_index)
                        logger.info(f"[NETWORK] Capital Assault: eliminated Player {player_index + 1} on client")

            # Battle Reports: the resolver captured these, so queue any addressed to us.
            # On this path this PC never ran the battle, so the message is its ONLY
            # source for them (a replay generates its own instead).
            for report in battle_reports:
                if isinstance(report, dict):
                    self.queue_battle_report(report)
                    # Heroes that died in this battle: queue them for the "Our Hero, X,
                    # has been slain in Y!" toast (the drain shows only the local
                    # player's own heroes).
                    for hero in report.get('heroes_slain') or []:
                        gs.hero_death_events.append(
                            (report.get('defender'), hero, report.get('territory')))

            # Universal last-team-standing: check victory after the territory change
            # (resolve_battle() does this itself on the replay path)
            gs.check_victory()

        # SIMULTANEOUS MODE: Handle alliance marker if sent
        if alliance_marker and self.sim_state is not None:
            if hasattr(self.sim_state, 'phase_manager') and self.sim_state.phase_manager:
                self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)
                logger.info(f"[NETWORK] Added alliance marker for {territory}, chooser: {alliance_marker.get('chooser')}")

        # Capital Assault: battle eliminations into sim_state (as on the resolver's PC)
        self._sync_battle_eliminations_to_sim("after remote battle")

        # Check if all battles resolved
        if len(gs.pending_battles) == 0:
            if self.sim_state is not None:
                # SIMULTANEOUS MODE: Check alliance markers
                pm = self.sim_state.phase_manager
                markers_pending = len(pm.pending_alliance_markers) if pm else 0
                logger.info(f"[NETWORK] All battles resolved (sim mode). Alliance markers: {markers_pending}")

                # HOST: Complete round if no more battles/markers (and no report of ours open)
                if self.local_player_index == 0 and self._sim_round_may_end():
                    logger.info(f"[HOST] All conflicts resolved after remote battle, completing round")
                    self.sim_state.complete_round()
            else:
                # SEQUENTIAL MODE: Set ready to advance turn
                logger.info("[NETWORK] All battles resolved, ready to advance turn")
                gs.ready_to_advance_turn = True

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
            self._close_battle_window()
            return

        territory = self._resolved_battle_info['territory']
        # Both built on the FIGHT click, from the battle's outcome
        alliance_marker = self._resolved_battle_info.get('alliance_marker')
        payload = self._resolved_battle_info.get('payload')

        # Clear stored battle info
        self._resolved_battle_info = None

        # SIMULTANEOUS MODE: allied capture -> the allies choose the new owner. Queued now
        # (not on FIGHT) so the choice comes up after the battle report is closed.
        if alliance_marker and self.sim_state is not None:
            self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)
            logger.info(f"[SIM] Alliance marker created at {territory}, chooser: {alliance_marker['chooser']}")

        # MULTIPLAYER: Send battle result to remote player (seed + outcome, see
        # _battle_resolve_payload - the other PCs replay the battle from the seed)
        if self.multiplayer_mode and payload is not None:
            self._send_action_to_remote(MessageType.BATTLE_RESOLVE, payload)

        # Clean up the interface
        self.enhanced_battle_ui = None
        self.battle_popup_visible = False
        self.selected_battle_index = None
        self.selected_battle_territory = None

        # Notify tutorial mission that battle popup was dismissed by the player,
        # so deferred voice lines can play after the report is closed
        if self._is_tutorial_active():
            self.tutorial_mission.notify_event('battle_popup_closed')

        # SIMULTANEOUS MODE: Check if all battles resolved
        if self.sim_state is not None:
            # Capital Assault: sync battle-based eliminations to sim_state
            self._sync_battle_eliminations_to_sim("after battle")

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

        # SEQUENTIAL MODE: Check if all battles resolved and turn should advance.
        # Multiplayer: the turn-advance hook (_on_turn_advanced) sends TURN_END with the
        # state snapshot - AFTER the battle result above, so every PC replays it first.
        if self.game_state.ready_to_advance_turn:
            logger.info(f"[TURN_DEBUG] _finalize_enhanced_battle: advancing turn (ready_to_advance={self.game_state.ready_to_advance_turn})")
            self.game_state._advance_to_next_player()

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
                    self._sim_queue_local_movement_orders(local_player)

                    # Now mark the player as ready
                    self.sim_state.mark_ready(local_player)

                    # MULTIPLAYER client: Send SIM_PLAYER_READY with orders to host
                    self._sim_send_local_ready(local_player, "End Turn")

                # SEQUENTIAL MODE (single-player and multiplayer): the same path the
                # multiplayer planning timer takes. Note: Units/buildings will spawn in
                # _complete_turn_announcement callback
                else:
                    self._end_local_turn("End Turn")

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

        # Keep view: the Keep's own hero opens its Hero view, like the Territory view's
        # Forces portrait and the sidebar Heroes tab
        if self.selected_keep and self.keep_hero_button:
            card_rect, hero_name = self.keep_hero_button
            if card_rect.collidepoint(pos):
                self.trigger_click_flash('bottom_button', ('keep_hero', hero_name))
                self._select_hero(hero_name)
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
        
        # Hero view portrait: pan the map to the hero's Keep, like the portrait on the
        # sidebar Heroes tab card (start_sidebar_camera_pan refuses during tutorial
        # camera locks and scripted camera moves)
        if self.selected_hero and self.hero_view_portrait_button:
            portrait_rect, hero_name = self.hero_view_portrait_button
            if portrait_rect.collidepoint(pos):
                self.trigger_click_flash('bottom_button', ('hero_portrait', hero_name))
                hero_data = self.game_state.heroes.get(self.game_state.current_player, {}).get(hero_name, {})
                if hero_data.get('keep_territory'):
                    self.start_sidebar_camera_pan(hero_data['keep_territory'])
                return True

        # Territory view Forces section: Select Army opens the current player's garrison
        # here (same path as clicking its banner); greyed = consumed with no action
        if self.selected_territory_info and self.select_army_button and self.select_army_button.collidepoint(pos):
            territory = self.selected_territory_info
            if self._can_select_army_in(territory):
                # No button flash: the view switches at once, and _select_army_garrison()
                # flashes the army's banner on the map instead
                self._select_army_garrison((territory, self.game_state.current_player))
            return True

        # Territory view Forces section: own hero portrait opens its Hero view, exactly
        # like selecting it in the sidebar Heroes tab
        if self.selected_territory_info and self.forces_hero_button:
            hero_rect, hero_name = self.forces_hero_button
            if hero_rect.collidepoint(pos):
                self.trigger_click_flash('bottom_button', ('forces_hero', hero_name))
                self._select_hero(hero_name)
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
                        # Sequential multiplayer: the other PCs started this building from
                        # its BUILDING_ORDER, so they must cancel it too (it was never sent:
                        # they kept the building and the charge, H4). Simultaneous mode
                        # only removed the queued build order above.
                        if self.multiplayer_mode and self.sim_state is None:
                            self._send_action_to_remote(MessageType.ORDER_REMOVE, {
                                'cancel_type': 'construction',
                                'territory': territory,
                                'plot_index': plot_index,
                                'player_index': self.game_state.current_player
                            })
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
                        # FIGHT finds the battle by territory (the index can shift)
                        self.selected_battle_territory = battle.territory
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

    def _resolve_all_pending_battles(self, any_resolver=False):
        """
        Auto-resolve all pending battles where the local player is the resolver.

        Resolves battles silently (no battle reports or UI feedback).
        Handles multiplayer sync, alliance markers (sim mode), Capital Assault
        elimination sync, and turn/round advancement after all battles are done.

        Called by _handle_resolve_all_battles_click() when the player clicks
        the "Resolve Remaining Battles" button during battle phase, and by the
        simultaneous-mode AFK rules (_sim_afk_watchdog).

        Args:
            any_resolver: Simultaneous multiplayer host fallback - also settle battles
                whose resolver is another player (absent / stuck)
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
                    # (the host's fallback takes any battle)
                    if any_resolver or getattr(b, 'resolver', None) == local_player:
                        resolvable_idx = idx
                        break
                else:
                    # Sequential mode: current player resolves all battles on their turn
                    resolvable_idx = idx
                    break

            if resolvable_idx is None:
                break  # No more battles for us to resolve

            # Resolve the battle (removes it from pending_battles); multiplayer: seeded,
            # so the other PCs replay it
            battle, battle_seed = self._resolve_battle_locally(resolvable_idx)
            territory = battle.territory

            # In sim mode, clear the sequential ready flag — sim mode uses complete_round() instead
            if self.sim_state is not None:
                self.game_state.ready_to_advance_turn = False

            # Handle alliance markers in simultaneous mode (shared rule)
            alliance_marker = self._alliance_marker_for(battle, territory)
            if alliance_marker:
                self.sim_state.phase_manager.pending_alliance_markers.append(alliance_marker)

            # Multiplayer: send battle result to remote players (seed + outcome)
            if self.multiplayer_mode:
                self._send_action_to_remote(MessageType.BATTLE_RESOLVE, self._battle_resolve_payload(
                    battle, territory, battle_seed, alliance_marker,
                    self.game_state.last_battle_reports))

            # Capital Assault: sync battle-based eliminations to sim_state
            self._sync_battle_eliminations_to_sim("after auto-resolve")

        # Post-loop: advance turn or complete round
        if not self.game_state.pending_battles:
            if self.sim_state is not None:
                # Simultaneous mode: complete round if no pending alliance markers (and
                # no battle report of ours still open - see _sim_round_may_end)
                if self._sim_round_may_end():
                    if not self.multiplayer_mode or self.local_player_index == 0:
                        self.sim_state.complete_round()
                    else:
                        logger.info(f"[CLIENT] Waiting for SIM_ROUND_COMPLETE from host")
            else:
                # Sequential mode: advance to next player - unless a battle report of ours
                # is still open (the AFK fallback resolves the rest under it): closing it
                # advances (_finalize_enhanced_battle), after its result has been sent.
                # Multiplayer: TURN_END goes out from the turn-advance hook.
                if self.game_state.ready_to_advance_turn and self._resolved_battle_info is None:
                    logger.info(f"[TURN_DEBUG] _resolve_all_pending_battles: advancing turn")
                    self.game_state._advance_to_next_player()

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
                    pm = self.sim_state.phase_manager if self.sim_state is not None else None
                    if (pm is None or self.sim_state.sim_phase != 'resolving'
                            or not any(m.get('territory') == territory
                                       for m in pm.pending_alliance_markers)):
                        # Already chosen elsewhere (the host's AFK fallback) - a second
                        # choice used to end the next round as well
                        logger.info(f"[ALLIANCE] Choice for {territory} was already made - closing the popup")
                        self.alliance_choice_popup_visible = False
                        return True
                    logger.info(f"[ALLIANCE] Player chose to assign {territory} to player {player_id}")

                    # Send alliance choice to other players in multiplayer
                    # Both host and client need to send - host broadcasts to clients, client sends to host.
                    # BEFORE resolving locally: on the host that can end the round, and
                    # SIM_ROUND_COMPLETE must not reach the clients ahead of the choice.
                    if self.multiplayer_mode:
                        self._send_action_to_remote(MessageType.SIM_ALLIANCE_CHOICE, {
                            'territory': territory,
                            'new_owner': player_id
                        })
                        logger.debug(f"[NETWORK] Sent SIM_ALLIANCE_CHOICE: {territory} -> player {player_id}")

                    # Use phase manager to resolve the alliance marker
                    self.sim_state.phase_manager.resolve_alliance_marker(territory, player_id)

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
                # Select it (voice line + clear other selections) - shared with the
                # bottom panel's Forces portrait
                self._select_hero(hero_name)

                # The portrait also pans the map to the hero's Keep
                portrait = (getattr(self, 'hero_portrait_rects', None) or {}).get(hero_name)
                if portrait is not None and portrait.collidepoint(pos) and UIConstants.SIDEBAR_CAMERA_PAN:
                    hero_data = self.game_state.heroes.get(self.get_local_player(), {}).get(hero_name, {})
                    if hero_data.get('keep_territory'):
                        self.start_sidebar_camera_pan(hero_data['keep_territory'])

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
            self._hover_systems_this_frame = set()  # Start the next frame clean
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

        # A hover whose buttons were not drawn this frame (view switched by a click or
        # key) must not keep its tooltip following the mouse
        self._release_orphaned_button_hover()

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
        # Bottom-UI button tooltips work across the panel's full width. They used to be
        # cut off in the rightmost 250 px (a leftover from when the sidebar reached the
        # bottom of the screen); since the bottom panel overhaul the empty-plot building
        # buttons fill the width, so Training Grounds - the last one - lost its tooltip.
        # Every bottom-panel hover system clears its own tooltip when the mouse leaves
        # its buttons, so nothing lingers there.
        in_bottom_ui = self.mouse_pos[1] >= BOTTOM_UI_Y

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
        self._draw_bottom_panel_tooltip()

    def _draw_bottom_panel_tooltip(self):
        """Draw the bottom panel's hover label (Forces icon name) above the cursor,
        in the same style as the sidebar's, kept on screen."""
        tooltip = getattr(self, 'bottom_panel_tooltip', None)
        if not tooltip:
            return
        text, (mx, my) = tooltip
        surf = self.sidebar_widgets.tooltip(text)
        x = max(4, min(mx - surf.get_width() // 2, WINDOW_WIDTH - surf.get_width() - 4))
        y = max(4, my - surf.get_height() - 10)
        self.screen.blit(surf, (x, y))

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
        # draw_bottom_ui() resets the Forces-icon hover label every frame, but it does not
        # run during AI turns: a label hovered when the turn ended stayed frozen on screen
        # until the AI finished (update_frame_tooltips draws it at the frame's end)
        self.bottom_panel_tooltip = None
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

        # A player the AI took over mid-game (multiplayer: they left) has no AIPlayer yet -
        # they used to be created once, at the first AI turn, so the empire never moved (M13)
        if (current_player not in self.ai_players
                and self.game_state.player_is_ai[current_player]):
            from ai_player import AIPlayer
            difficulty = self.game_state.player_ai_difficulty[current_player]
            self.ai_players[current_player] = AIPlayer(current_player, 1 if difficulty is None else difficulty)
            logger.info(f"[AI] Created AI Player {current_player + 1} for a takeover")

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
        intro_cutscene = CutscenePlayer(screen, f"{mission_id}_intro",
                                        master_volume=music_manager.master_volume)
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
            outro_cutscene = CutscenePlayer(screen, f"{mission_id}_outro",
                                            master_volume=music_manager.master_volume)
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
            outro_cutscene = CutscenePlayer(screen, f"{mission_id}_outro",
                                            master_volume=music_manager.master_volume)
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

    def _play_multiplayer_game(screen, mode, network_connection, setup_config):
        """
        Loading screen, game and recap for one multiplayer game. Hosting, Join Game and
        Steam-invite joins all come through here, so the flows cannot drift apart again
        (the Steam-invite copy had already lost the map choice).

        Closes the network connection before returning.

        Args:
            mode: 'host' or 'client'
            network_connection: NetworkServer (host) or NetworkClient (client)
            setup_config: Game config from network.multiplayer_setup.build_multiplayer_config()

        Returns:
            (outcome, screen): outcome 'main_menu' or 'quit' (exit the app)
        """
        game = Game(existing_screen=screen, network_connection=network_connection)
        screen = game.screen
        # Host is Player 1; a client keeps the slot the server assigned when it joined
        game.local_player_index = 0 if mode == 'host' else network_connection.get_player_index()

        def close_connection():
            if mode == 'host':
                network_connection.stop()
            else:
                network_connection.disconnect()

        # Stop menu music before multiplayer loading
        music_manager.stop()

        # Loading screen with multiplayer readiness sync. Escape (or a lost host) ends it
        # early - back to the menu without starting the game.
        loading = LoadingScreen(screen, game, setup_config,
                                network_connection=network_connection)
        if loading.run() != 'start':
            logger.info(f"Multiplayer game not started ({loading.result}) - returning to menu")
            close_connection()
            return 'main_menu', screen

        # Start game music after loading completes
        music_manager.start_game_music()

        if hasattr(game, 'game_state') and game.game_state:
            # Attach game logger for multiplayer games
            from game_logger import GameLogger
            game.game_state.game_logger = GameLogger(game.game_state)

            # Attach sync logger for multiplayer games (desync diagnosis)
            from sync_logger import SyncLogger
            game_id = game.game_state.game_logger.game_id if game.game_state.game_logger else None
            game.game_state.sync_logger = SyncLogger(
                game.game_state, game.local_player_index,
                is_host=(mode == 'host'), game_id=game_id
            )

            # Attach replay recorder for multiplayer games
            from replay_recorder import ReplayRecorder
            game.game_state.replay_recorder = ReplayRecorder(game.game_state)

        # Run game
        result = game.run()

        # Stop game music before recap
        music_manager.stop()

        # Show post-game recap screen if game ended with a winner
        if show_recap_if_ended(game) == 'quit':
            close_connection()
            return 'quit', screen

        close_connection()

        if result != 'main_menu':
            return 'quit', screen

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

        return 'main_menu', screen

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

            # Connect as client, then the same lobby + game flow as Join Game
            # (network.multiplayer_setup.run_client_lobby, _play_multiplayer_game)
            from network.client import NetworkClient
            from network.multiplayer_setup import run_client_lobby

            client = NetworkClient()
            player_name = settings.get_player_name()

            if not client.connect(host_ip, port=port, player_name=player_name):
                logger.warning(f"Steam invite: failed to connect to {host_ip}:{port}: "
                               f"{client.disconnect_reason}")
                # Say why (lobby full, version mismatch, ...), then the main menu
                MultiplayerSetup(screen)._show_error(
                    "Could not join the game" +
                    (f": {client.disconnect_reason}" if client.disconnect_reason else ""))
                music_manager.start_menu_music()
                continue

            logger.info(f"Steam invite: connected to {host_ip}:{port}")
            lobby_result = run_client_lobby(screen, client)

            if lobby_result == 'quit':
                # Alt+F4 pressed — exit entire app
                client.disconnect()
                pygame.quit()
                sys.exit()
            if lobby_result is None or lobby_result[0] in ('kicked', 'lost'):
                # Left, kicked or lost the host — disconnect and return to main menu
                client.disconnect()
                if lobby_result is not None:
                    MultiplayerSetup(screen)._show_error(
                        f"You were kicked from the lobby: {lobby_result[1]}"
                        if lobby_result[0] == 'kicked'
                        else f"Lost connection to the host: {lobby_result[1]}")
                music_manager.start_menu_music()
                continue

            _, client, config = lobby_result
            outcome, screen = _play_multiplayer_game(screen, 'client', client, config)
            if outcome == 'quit':
                pygame.quit()
                sys.exit()
            continue

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

            # Loading, game and recap (shared with Steam-invite joins)
            outcome, screen = _play_multiplayer_game(screen, mode, network_connection, setup_config)
            if outcome == 'quit':
                pygame.quit()
                sys.exit()
            continue
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