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
    - Rendering pipeline: Map → UI → Tooltips → Popups
    - Tooltip system: Hover-based with 0.5s delay
    - Bottom UI: Training, building, orders, territory info
    - Popup systems: Battles, victory screen, army composition

Architecture:
    Game (main.py) ← uses → GameState (game_state.py)
    Game (main.py) ← uses → map_data (map_data.py)

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
import map_data
from game_state import GameState

# Initialize Pygame
pygame.init()

# Constants - ADJUST THESE TO FIT YOUR SCREEN
WINDOW_WIDTH = 1600  # Adjust this to your screen width
WINDOW_HEIGHT = 850  # Adjust this to your screen height
TOP_PANEL_HEIGHT = 40  # Height of top panel (player controls, stats)
BOTTOM_UI_HEIGHT = 200  # Height of the bottom UI panel (for RTS-style controls)
MAP_WIDTH = WINDOW_WIDTH  # Full width now (no right panel)
MAP_HEIGHT = WINDOW_HEIGHT - BOTTOM_UI_HEIGHT - TOP_PANEL_HEIGHT  # Map height (excluding UI panels)
BOTTOM_UI_Y = TOP_PANEL_HEIGHT + MAP_HEIGHT  # Y position where bottom UI starts (accounting for top panel)
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
GRAY = (150, 150, 150)
DARK_GRAY = (80, 80, 80)
HIGHLIGHT = (255, 255, 0, 100)  # Yellow highlight with transparency

# UI Layout Constants (added during refactoring for maintainability)
class UIConstants:
    """
    Centralized UI layout constants for easy adjustment and maintainability.
    
    This class contains all the magic numbers used throughout the UI rendering code.
    Extracting these constants makes it easier to:
    - Adjust UI layout globally
    - Understand what values mean
    - Maintain consistency
    - Prevent errors from typos
    """
    
    # ===== SIDEBAR DIMENSIONS =====
    SIDEBAR_WIDTH = 250  # Width of right sidebar (action queue, chat, etc.)
    SIDEBAR_HEIGHT = 610  # Height of sidebar (calculated: WINDOW_HEIGHT - TOP - BOTTOM)
    
    # ===== MESSAGE DISPLAY =====
    # Pixels per message - used for calculating how many messages fit
    PIXELS_PER_MESSAGE_SELECTION = 40  # Conservative estimate for selecting messages (was 30, fixed to 40)
    PIXELS_PER_MESSAGE_SCROLL = 40     # Conservative estimate for scroll limits (prevents over-scroll)
    MESSAGE_MAX_CHARS = 28             # Maximum characters per line before wrapping
    
    # ===== TAB SYSTEM =====
    TAB_WIDTH = 40           # Width of vertical tab buttons sticking out from sidebar
    TAB_PADDING_TOP = 45     # Padding at top of tab button area
    TAB_PADDING_BOTTOM = 45  # Padding at bottom of tab button area
    
    # ===== SCROLLBAR =====
    SCROLLBAR_WIDTH = 4        # Width of scrollbar track and thumb
    SCROLLBAR_OFFSET = 8       # Distance from right edge of sidebar
    SCROLLBAR_THUMB_MIN = 20   # Minimum height of scrollbar thumb
    
    # ===== CONTENT SPACING =====
    HEADER_OFFSET = 45         # Y offset for content below header
    BOTTOM_RESERVE = 40        # Space reserved at bottom for scroll indicator
    SIDEBAR_CONTENT_PADDING = 100  # Total padding for sidebar content (header + footer)

# Original map dimensions (for scaling polygons)
ORIGINAL_MAP_WIDTH = 1269
ORIGINAL_MAP_HEIGHT = 903

# ========================================
# PHASE 1A: EXTRACTED CONSTANTS
# ========================================

# Plot and Building Icon Sizes (2x larger for better visibility!)
PLOT_CIRCLE_RADIUS = 24  # Was 12 (2x larger) - KEPT for plots
PLOT_CIRCLE_CENTER_OFFSET = 30  # Was 15 (2x larger)
PLOT_SURFACE_SIZE = 60  # Was 30 (2x larger)
EMPTY_PLOT_RADIUS = 16  # Was 8 (2x larger) - KEPT for plots
BUILDING_ICON_RADIUS = 37  # Was 50 (reduced to 75% per user request - icons were too large)
ICON_CLICK_RADIUS = 21  # Was 28 (reduced to 75% per user request)

# Army and Badge Sizes
ARMY_CIRCLE_RADIUS = 15
BADGE_RADIUS = 16

# Button Sizes
BUTTON_SIZE_SQUARE = 60  # Size for training and building buttons
BUTTON_SPACING = 10

# Hover and Tooltip Settings
HOVER_DELAY_MS = 500  # 0.5 seconds before tooltip appears
TOOLTIP_OFFSET_X = 15
TOOLTIP_OFFSET_Y = 15
TOOLTIP_BORDER_WIDTH = 2
TOOLTIP_SCREEN_MARGIN = 5  # Margin from screen edges

# Tooltip Sizes
TOOLTIP_LINE_HEIGHT = 15
TOOLTIP_WIDTH_TRAINING = 150
TOOLTIP_WIDTH_BUILDING = 200
TOOLTIP_WIDTH_PLOT = 135
TOOLTIP_PADDING = 7

# Arrow Drawing
ARROW_LINE_WIDTH = 4
ARROW_HEAD_SIZE = 15
ARROW_HEAD_ANGLE_RAD = 0.5236  # math.pi / 6 (30 degrees)

# Colors - Plot States
COLOR_PLOT_GRAY = (150, 150, 150, 200)
COLOR_PLOT_BORDER = (50, 50, 50, 255)
COLOR_GOLD_HIGHLIGHT = (255, 215, 0, 255)
COLOR_CONSTRUCTION = (200, 200, 100, 150)
COLOR_CONSTRUCTION_BORDER = (150, 150, 50, 255)
COLOR_CONSTRUCTION_TEXT = (200, 200, 200)
COLOR_EMPTY_PLOT_CAN_BUILD = (100, 220, 100, 180)
COLOR_EMPTY_PLOT_CANNOT_BUILD = (200, 200, 200, 80)
COLOR_EMPTY_PLOT_BORDER = (100, 100, 100, 150)

# Colors - Building/Training Icons
COLOR_ICON_AVAILABLE = (100, 200, 100, 200)
COLOR_ICON_UNAVAILABLE = (200, 100, 100, 200)
COLOR_ICON_BORDER = (50, 50, 50, 255)

# Colors - Arrows
COLOR_ARROW_MOVEMENT = (0, 200, 0)

# Colors - Tooltips
COLOR_TOOLTIP_BG = (50, 50, 50)
COLOR_TOOLTIP_BORDER = (200, 200, 200)

# Colors - Territory Glow
COLOR_TERRITORY_GLOW_FRIENDLY = (0, 255, 0)
COLOR_TERRITORY_GLOW_ENEMY = (255, 0, 0)
COLOR_TERRITORY_GLOW_NEUTRAL = (200, 200, 200)

# ========================================
# PHASE 3: UI TIMING, SPACING, AND ANIMATION CONSTANTS
# ========================================

# Tooltip Timing
TOOLTIP_DELAY_MS = 500  # Delay before showing tooltips (milliseconds)
TOOLTIP_DELAY_BUTTON_MS = 500  # Delay for button tooltips (milliseconds)

# UI Spacing
UI_LINE_SPACING = 30  # Vertical space between text lines
UI_LINE_SPACING_SMALL = 22  # Smaller vertical spacing
UI_LINE_SPACING_LARGE = 40  # Larger vertical spacing
UI_SECTION_SPACING = 40  # Space between UI sections
UI_BUTTON_SPACING = 5  # Horizontal space between buttons
UI_PADDING = 8  # General padding around UI elements
UI_PANEL_PADDING = 10  # Padding inside panels

# Animation Timing
CLICK_FLASH_DURATION_MS = 150  # How long click flash lasts (milliseconds)

# Camera Settings
CAMERA_SCROLL_SPEED = 15  # Edge scrolling speed (pixels per frame)
CAMERA_PAN_SPEED = 10  # Keyboard pan speed (pixels per frame)
CAMERA_ZOOM_SPEED = 0.15  # Zoom increment per scroll

# ========================================

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("War of Avareon")
        self.clock = pygame.time.Clock()
        
        # Load territory polygons
        map_data.load_polygons()
        if not map_data.TERRITORY_POLYGONS:
            print("ERROR: No territory polygons loaded!")
            print("Please run polygon_tool.py first to define territories.")
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
        
        print(f"Window: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        print(f"Map scaled to: {self.map_width}x{self.map_height}")
        print(f"Scale factor: {self.scale_factor:.2f}")
        
        # Load and scale the map image
        try:
            # Load original high-resolution image
            self.map_image_original = pygame.image.load("assets/map.jpg")
            
            # Create scaled version for initial display
            # But keep original for high-quality zooming!
            self.map_image = pygame.transform.scale(self.map_image_original, (self.map_width, self.map_height))
        except pygame.error as e:
            print(f"Error loading map: {e}")
            print("Make sure 'assets/map.jpg' exists!")
            sys.exit(1)
        
        # Scale polygons and centers to match map scaling
        self.scaled_polygons = {}
        self.scaled_centers = {}
        for territory, polygon in map_data.TERRITORY_POLYGONS.items():
            self.scaled_polygons[territory] = [
                (int(x * self.scale_factor), int(y * self.scale_factor)) 
                for x, y in polygon
            ]
        for territory, center in map_data.TERRITORY_CENTERS.items():
            self.scaled_centers[territory] = (
                int(center[0] * self.scale_factor),
                int(center[1] * self.scale_factor)
            )
        
        # Scale plot positions to match map scaling
        self.scaled_plots = {}
        for territory, plots in map_data.TERRITORY_PLOTS.items():
            self.scaled_plots[territory] = [
                (int(x * self.scale_factor), int(y * self.scale_factor))
                for x, y in plots
            ]
        
        # Game state
        self.game_state = GameState(num_players=2)  # Start with 2 players
        
        # UI state
        self.hovered_territory = None
        self.hovered_army = None  # Territory with army being hovered
        self.mouse_pos = (0, 0)  # Track mouse position for tooltip
        self.selected_plot = None  # (territory, plot_index) tuple
        self.selected_barracks = None  # (territory, barracks_plot_index) tuple
        self.hovered_plot = None  # (territory, plot_index) tuple
        self.action_log_visible = False  # Toggle for action log overlay
        self.order_cancel_buttons = []  # List of (rect, order_index) for click detection
        self.cancel_all_button = None  # Rect for cancel all button
        self.sidebar_toggle_button = None  # Rect for sidebar expand/collapse button
        self.resolve_battle_button = None  # Rect for battle resolution button
        self.selected_battle_index = None  # Which battle is selected (None = none selected)
        self.battle_popup_visible = False  # Is battle popup showing?
        self.battle_popup_state = 'initial'  # 'initial', 'resolving', 'result'
        self.close_popup_button = None  # Rect for close popup button
        self.selected_territory_info = None  # Territory clicked for info display
        self.battle_markers = []  # List of rects for clickable battle markers
        self.battle_result = None  # Store result of resolved battle for display
        
        # Chat system state
        self.chat_input_active = False  # Is chat input box open?
        self.chat_input_text = ""  # Current text being typed
        self.chat_scroll_offset = 0  # How many messages to scroll (0 = bottom/newest)
        self.action_log_scroll_offset = 0  # Scroll offset for action log
        
        # Hover delay system (0.5 seconds before showing tooltips)
        self.hover_start_time = None  # When hover began (for map: army/territory)
        self.hover_target_territory = None  # What territory we're hovering over
        self.hover_target_army = None  # What army we're hovering over
        self.hover_delay = HOVER_DELAY_MS  # Delay in milliseconds
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
        
        # Army Composition UI (Phase 3)
        self.show_army_composition = False  # Is composition UI visible?
        self.army_composition_territory = None  # Which territory's composition is shown
        self.selected_army_units = []  # List of selected unit IDs within composition
        self.army_composition_buttons = []  # List of (rect, unit_id) for click detection
        self.hovered_composition_button = None  # Which button is being hovered (for tooltip)
        
        # Font
        self.font = pygame.font.Font(None, 24)
        self.large_font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 18)
        
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
        
        # Map scaling cache (optimization: avoid rescaling every frame)
        self.cached_scaled_map = None     # Cached scaled map image
        self.cached_zoom_level = None     # Zoom level of cached map
        
        # Camera debug state (Phase 2D: temporary for testing)
        self.debug_edge_scroll = None
        self.debug_keyboard_scroll = None
    
    def get_territory_at_pos(self, pos):
        """
        Find which territory the mouse is over using polygon detection.
        
        Args:
            pos: (x, y) tuple in WORLD coordinates (not screen coordinates!)
                 Caller should convert screen to world before calling this.
        
        Returns:
            Territory name or None if no territory at position
        
        Note:
            Phase 2D: Now expects world coordinates. Callers must use
            screen_to_world() before calling this method.
        """
        # Check from end to start to handle overlaps better
        # scaled_polygons are in world coordinates, so pos must also be world coords
        for territory in reversed(list(self.scaled_polygons.keys())):
            polygon = self.scaled_polygons[territory]
            if map_data.point_in_polygon(pos, polygon):
                return territory
        return None
    
    def get_army_at_pos(self, pos):
        """
        Check if clicking on an army number circle.
        
        Now accounts for both camera zoom and UI scaling to ensure click area
        matches the visual army circle size exactly at all zoom levels.
        
        Args:
            pos: (x, y) tuple in WORLD coordinates (not screen coordinates!)
                 Caller should convert screen to world before calling this.
        
        Returns:
            Territory name if click is on an army circle, None otherwise
        
        Note:
            Phase 2D: Now expects world coordinates. Callers must use
            screen_to_world() before calling this method.
            
            Click radius calculation:
            - Visual radius in screen space: ARMY_CIRCLE_RADIUS * ui_scale
            - Convert to world space: (screen_radius / camera_zoom)
            - This ensures click area matches visual size at all zoom levels
        """
        x, y = pos
        
        # Calculate click radius in world space that matches visual size
        # Visual size: ARMY_CIRCLE_RADIUS * ui_scale (in screen space)
        # World size: visual_size / camera_zoom
        ui_scale = self.get_ui_scale_factor()
        click_radius_world = (ARMY_CIRCLE_RADIUS * ui_scale) / self.camera_zoom
        
        # Check all territory centers (scaled_centers are in world coordinates)
        for territory, (cx, cy) in self.scaled_centers.items():
            # Calculate distance from click to center
            distance = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            
            # If within army circle radius (accounting for zoom and UI scale), return territory
            if distance <= click_radius_world:
                # Only return if territory has armies and is owned by current player
                if self.game_state.territory_owners.get(territory, -1) == self.game_state.current_player:
                    if self.game_state.armies_unmoved.get(territory, 0) > 0:
                        return territory
        
        return None
    
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
        
        Applies camera offset and zoom to transform screen position
        (where the mouse is) to the corresponding world position
        (actual map coordinates).
        
        This is used for:
        - Mouse hover detection (find what territory is under cursor)
        - Click detection (find what was clicked)
        - Any input that needs to know "what world position is here?"
        
        Math:
        1. Subtract TOP_PANEL_HEIGHT from Y (convert to map-relative coordinates)
        2. Divide screen position by zoom (undo zoom scaling)
        3. Add camera offset (undo camera panning)
        
        Args:
            screen_pos: (x, y) tuple in screen coordinates (pixels on window)
        
        Returns:
            (x, y) tuple in world coordinates (actual map positions)
        
        Example:
            Mouse at screen position (400, 340)
            TOP_PANEL_HEIGHT: 40, Camera offset: (100, 50), zoom: 2.0
            
            world_x = (400 / 2.0) + 100 = 300
            world_y = ((340 - 40) / 2.0) + 50 = 200
            
            World position: (300, 200)
        
        Phase Context:
            Part of Phase 2D camera system implementation.
            Essential for making hover/click detection work with camera movement.
            Updated in Phase A to account for top panel offset.
        """
        screen_x, screen_y = screen_pos
        
        # Subtract top panel offset from Y coordinate (convert to map-relative)
        map_relative_y = screen_y - TOP_PANEL_HEIGHT
        
        # Undo zoom (divide by zoom), then undo offset (add offset)
        world_x = (screen_x / self.camera_zoom) + self.camera_offset[0]
        world_y = (map_relative_y / self.camera_zoom) + self.camera_offset[1]
        
        return (world_x, world_y)
    
    def world_to_screen(self, world_pos):
        """
        Convert world coordinates to screen coordinates.
        
        Applies camera offset and zoom to transform world position
        (actual map coordinates) to the corresponding screen position
        (where to draw on window).
        
        This is used for:
        - Drawing territories (render polygons on screen)
        - Drawing armies (render circles on screen)
        - Drawing buildings (render icons on screen)
        - Any rendering that needs to know "where to draw this?"
        
        Math:
        1. Subtract camera offset (apply camera panning)
        2. Multiply by zoom (apply zoom scaling)
        
        Args:
            world_pos: (x, y) tuple in world coordinates (actual map positions)
        
        Returns:
            (x, y) tuple in screen coordinates (pixels on window)
        
        Example:
            Territory at world position (500, 400)
            Camera offset: (100, 50), zoom: 2.0
            
            screen_x = (500 - 100) * 2.0 = 800
            screen_y = (400 - 50) * 2.0 = 700
            
            Screen position: (800, 700)
        
        Phase Context:
            Part of Phase 2D camera system implementation.
            Essential for making rendering follow camera movement.
        """
        world_x, world_y = world_pos
        
        # Apply offset (subtract offset), then apply zoom (multiply by zoom)
        screen_x = (world_x - self.camera_offset[0]) * self.camera_zoom
        screen_y = (world_y - self.camera_offset[1]) * self.camera_zoom + TOP_PANEL_HEIGHT  # Offset for top panel
        
        return (screen_x, screen_y)
    
    def get_ui_scale_factor(self):
        """
        Get UI element scale factor based on current zoom level.
        
        Makes UI elements (army circles, plots, building icons) scale with zoom
        for better visibility and easier clicking when zoomed in.
        
        Scaling behavior:
        - At min zoom (1.5x): scale = 1.0 (baseline/current size)
        - At max zoom (4.0x): scale = 1.5 (50% larger than baseline)
        - Linear interpolation between min and max
        
        This makes small UI elements easier to interact with when zoomed in
        while keeping them compact when zoomed out.
        
        Returns:
            float: Scale multiplier for UI element sizes (1.0 to 1.5)
        
        Performance:
            O(1) - simple arithmetic, negligible CPU cost
            No memory allocation, just returns a float
            
        Example usage:
            scale = self.get_ui_scale_factor()
            scaled_radius = ARMY_CIRCLE_RADIUS * scale
            pygame.draw.circle(surface, color, pos, int(scaled_radius))
        """
        # Calculate normalized zoom position (0.0 to 1.0)
        zoom_range = self.camera_max_zoom - self.camera_min_zoom
        zoom_position = (self.camera_zoom - self.camera_min_zoom) / zoom_range
        
        # Scale from 1.0 (at min zoom) to 1.5 (at max zoom)
        # User requested 0.5x larger at max zoom, so 1.0 + 0.5 = 1.5
        scale_factor = 1.0 + (0.5 * zoom_position)
        
        return scale_factor
    
    def lighten_color(self, color, amount=0.2):
        """
        Lighten a color by a percentage for hover effects.
        
        Args:
            color: (r, g, b) or (r, g, b, a) tuple (0-255 values)
            amount: float, percentage to lighten (0.2 = 20% lighter)
        
        Returns:
            (r, g, b) or (r, g, b, a) tuple with lightened color
        
        Example:
            hover_color = self.lighten_color((100, 200, 100), 0.2)
            # Returns (120, 220, 120) - each component increased by 20%
        
        Performance:
            O(1) - just 3-4 multiplications and clamps
            Negligible CPU cost (~0.00001ms)
        """
        if len(color) == 3:
            r, g, b = color
            r = min(255, int(r * (1 + amount)))
            g = min(255, int(g * (1 + amount)))
            b = min(255, int(b * (1 + amount)))
            return (r, g, b)
        else:  # RGBA
            r, g, b, a = color
            r = min(255, int(r * (1 + amount)))
            g = min(255, int(g * (1 + amount)))
            b = min(255, int(b * (1 + amount)))
            return (r, g, b, a)
    
    def brighten_color(self, color, amount=0.4):
        """
        Brighten a color for click flash effects.
        
        More aggressive than lighten - adds brightness for visibility.
        
        Args:
            color: (r, g, b) or (r, g, b, a) tuple (0-255 values)
            amount: float, percentage to brighten (0.4 = 40% brighter)
        
        Returns:
            (r, g, b) or (r, g, b, a) tuple with brightened color
        
        Example:
            click_color = self.brighten_color((100, 200, 100), 0.4)
            # Returns (140, 240, 140) - each component increased by 40%
        
        Performance:
            O(1) - just 3-4 multiplications and clamps
            Negligible CPU cost (~0.00001ms)
        """
        if len(color) == 3:
            r, g, b = color
            r = min(255, int(r * (1 + amount)))
            g = min(255, int(g * (1 + amount)))
            b = min(255, int(b * (1 + amount)))
            return (r, g, b)
        else:  # RGBA
            r, g, b, a = color
            r = min(255, int(r * (1 + amount)))
            g = min(255, int(g * (1 + amount)))
            b = min(255, int(b * (1 + amount)))
            return (r, g, b, a)
    
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
            final_color = self.brighten_color(base_color, 0.4)
        elif is_hovering:
            final_color = self.lighten_color(base_color, 0.2)
        
        # Draw background
        pygame.draw.rect(self.screen, final_color, rect)
        
        # Draw border
        if border_width > 0:
            pygame.draw.rect(self.screen, border_color, rect, border_width)
        
        # Draw text if provided
        if text:
            if font is None:
                font = self.font
            text_surf = font.render(text, True, text_color)
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
        # Normalize lines to (font, text, color) tuples
        normalized_lines = []
        for line in lines:
            if isinstance(line, tuple):
                if len(line) == 3 and isinstance(line[0], str) and line[0] in ['normal', 'small', 'large']:
                    # Already (font_size, text, color) format
                    normalized_lines.append(line)
                elif len(line) == 2:
                    # (text, color) format - use small font
                    normalized_lines.append(("small", line[0], line[1]))
                else:
                    # Unknown tuple format - treat as text
                    normalized_lines.append(("small", str(line), BLACK))
            else:
                # Just text string - use small font and BLACK
                normalized_lines.append(("small", str(line), BLACK))
        
        # Render all lines and calculate required size
        rendered_lines = []
        max_line_width = 0
        total_height = 0
        
        for font_size, text, color in normalized_lines:
            # Select appropriate font
            if font_size == "large":
                font = self.large_font
            elif font_size == "normal":
                font = self.font
            else:  # "small" or default
                font = self.small_font
            
            surf = font.render(text, True, color)
            rendered_lines.append(surf)
            max_line_width = max(max_line_width, surf.get_width())
            total_height += surf.get_height() + line_spacing
        
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
        
        # Adjust if tooltip goes off bottom edge (allow in bottom UI panel)
        if tooltip_y + tooltip_height > WINDOW_HEIGHT:
            tooltip_y = WINDOW_HEIGHT - tooltip_height - 10
        
        # Ensure tooltip doesn't go off left/top edges
        tooltip_x = max(5, tooltip_x)
        tooltip_y = max(5, tooltip_y)
        
        # Create tooltip rect
        tooltip_rect = pygame.Rect(tooltip_x, tooltip_y, tooltip_width, tooltip_height)
        
        # Draw with transparency if requested
        if use_transparency:
            # Create semi-transparent surface
            tooltip_surface = pygame.Surface((tooltip_width, tooltip_height), pygame.SRCALPHA)
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
        
        # Draw text lines
        y = tooltip_y + padding
        for surf in rendered_lines:
            self.screen.blit(surf, (tooltip_x + padding, y))
            y += surf.get_height() + line_spacing
        
        return tooltip_rect
    
    def clamp_camera_to_bounds(self):
        """
        Clamp camera offset to keep view within map bounds.
        
        Prevents camera from scrolling too far off the edge of the map.
        Calculates how much of the map is visible based on current zoom,
        then ensures camera offset doesn't show areas outside the map.
        
        Bounds Logic:
        1. Calculate visible area size in world units (window size / zoom)
        2. Calculate maximum offset (map size - visible size)
        3. Clamp offset to [0, max_offset] range
        
        Map Bounds:
        - Uses self.map_width and self.map_height (scaled map dimensions)
        - Minimum offset: 0 (don't show negative coordinates)
        - Maximum offset: map_size - visible_size (don't show beyond map)
        
        Side Effects:
            Updates self.camera_offset[0] and [1] to clamped values
        
        Example:
            Map: 1000x800 pixels
            Window: 1600x650 (map area)
            Zoom: 2.0
            
            Visible width: 1600 / 2.0 = 800 pixels
            Visible height: 650 / 2.0 = 325 pixels
            
            Max offset X: 1000 - 800 = 200
            Max offset Y: 800 - 325 = 475
            
            Offset clamped to: [0, 200] x [0, 475]
        
        Phase Context:
            Part of Phase 2D camera system implementation.
            Called after every camera movement to enforce bounds.
        """
        # Calculate visible area size in world units
        visible_width = WINDOW_WIDTH / self.camera_zoom
        visible_height = MAP_HEIGHT / self.camera_zoom
        
        # Map bounds (use scaled map dimensions)
        map_width = self.map_width
        map_height = self.map_height
        
        # Clamp horizontal offset
        # Min: 0 (don't show before map starts)
        # Max: map_width - visible_width (don't show past map ends)
        min_x = 0
        max_x = max(0, map_width - visible_width)
        self.camera_offset[0] = max(min_x, min(max_x, self.camera_offset[0]))
        
        # Clamp vertical offset
        # Min: 0 (don't show before map starts)
        # Max: map_height - visible_height (don't show past map ends)
        min_y = 0
        max_y = max(0, map_height - visible_height)
        self.camera_offset[1] = max(min_y, min(max_y, self.camera_offset[1]))
    
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
                final_bg_color = self.brighten_color(bg_color, 0.4)  # Bright flash on click
            elif is_hovering:
                final_bg_color = self.lighten_color(bg_color, 0.2)  # Subtle lightening on hover
        
        # Draw filled background
        pygame.draw.rect(self.screen, final_bg_color, rect)
        
        # Draw border
        pygame.draw.rect(self.screen, border_color, rect, border_width)
        
        # Draw centered letter
        letter_surf = self.large_font.render(letter, True, letter_color)
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
        
        # Draw centered text
        text_surf = self.small_font.render(str(text), True, text_color)
        text_rect = text_surf.get_rect(center=pos)
        self.screen.blit(text_surf, text_rect)
    
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
    
    def draw_territory_overlay(self, territory, color, alpha=100, outline=False):
        """
        Draw a colored overlay on a territory (Phase 2D: camera-aware).
        
        Transforms territory polygon from world to screen coordinates
        before drawing, so overlay follows camera movement and zoom.
        
        Args:
            territory: Name of territory to draw overlay on
            color: RGB tuple (r, g, b)
            alpha: Transparency (0-255)
            outline: Whether to draw border
        """
        if territory not in self.scaled_polygons:
            return
        
        # Get polygon in world coordinates
        world_polygon = self.scaled_polygons[territory]
        
        # Transform to screen coordinates (Phase 2D: camera transformation!)
        screen_polygon = [self.world_to_screen(point) for point in world_polygon]
        
        # Create a surface with per-pixel alpha matching the WINDOW size
        # Must be full WINDOW_HEIGHT to avoid clipping territory overlays near bottom
        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        
        # Draw filled polygon with transparency (now in screen coordinates)
        pygame.draw.polygon(surface, (*color, alpha), screen_polygon)
        
        # Draw outline if requested
        if outline:
            pygame.draw.lines(surface, (*color, 255), True, screen_polygon, 3)
        
        self.screen.blit(surface, (0, 0))
    
    
    # ========================================
    # PHASE 4: EXTRACTED PLOT RENDERING METHODS
    # ========================================
    
    def _draw_completed_building_plots(self, ui_scale, scaled_empty_plot_radius,
                                       building_letter_font):
        """
        Draw circles with letters for completed buildings.
        
        Phase 4: Extracted from draw_plots() for maintainability.
        Handles only fully-constructed buildings (F/M/B/K/Q).
        
        Renders:
        - Background circle (uses EMPTY_PLOT_RADIUS size)
        - Gold ring if selected
        - Building letter icon (F/M/B/K/Q)
        - Hover brightening (+20%)
        - Click flash (+40%)
        
        Args:
            ui_scale: Scale factor based on camera zoom (1.0 to 1.5)
            scaled_empty_plot_radius: Radius for plot circles (zoom-adjusted)
            building_letter_font: Font for building letters
        """
        scaled_plot_surface_size = int(PLOT_SURFACE_SIZE * ui_scale)
        scaled_plot_center_offset = scaled_plot_surface_size // 2
        
        for territory, plots in self.scaled_plots.items():
            owner = self.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue
            
            for plot_index, world_pos in enumerate(plots):
                # Check if completed building exists
                building = None
                if territory in self.game_state.buildings:
                    building = self.game_state.buildings[territory].get(plot_index)
                
                if not building:
                    continue  # Skip non-buildings
                
                # Get building info (with error handling)
                try:
                    building_info = self.game_state.building_types[building]
                    letter = building_info['letter']
                except (KeyError, TypeError) as e:
                    print(f"Warning: Invalid building type '{building}' in {territory}")
                    continue
                
                # Transform to screen coordinates
                x, y = self.world_to_screen(world_pos)
                x, y = int(x), int(y)
                
                # Create surface for building
                plot_surface = pygame.Surface((scaled_plot_surface_size, scaled_plot_surface_size), pygame.SRCALPHA)
                
                # Get owner color and soften it (avoid confusion with army circles)
                owner_color = self.game_state.get_player_color(owner)
                # Darken owner color by 30% for buildings (more subtle than armies)
                softened_color = tuple(int(c * 0.7) for c in owner_color)
                
                # Base color
                circle_color = softened_color
                
                # Check for hover
                is_hovering = False
                mouse_screen_x, mouse_screen_y = self.mouse_pos
                distance = ((x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2) ** 0.5
                if distance <= scaled_empty_plot_radius:
                    is_hovering = True
                
                # Check for click flash
                is_clicking = (self.clicked_element and 
                              self.clicked_element[0] == 'plot' and 
                              self.clicked_element[1] == (territory, plot_index))
                
                # Apply visual feedback
                if is_clicking:
                    circle_color = self.brighten_color(circle_color, 0.4)
                elif is_hovering:
                    circle_color = self.lighten_color(circle_color, 0.2)
                
                # Draw circle
                pygame.draw.circle(plot_surface, circle_color, 
                                 (scaled_plot_center_offset, scaled_plot_center_offset), 
                                 scaled_empty_plot_radius)
                
                # Highlight if selected (Barracks)
                if self.selected_barracks and self.selected_barracks == (territory, plot_index):
                    pygame.draw.circle(plot_surface, COLOR_GOLD_HIGHLIGHT, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_empty_plot_radius, 3)
                elif self.selected_plot and self.selected_plot == (territory, plot_index):
                    pygame.draw.circle(plot_surface, COLOR_GOLD_HIGHLIGHT, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_empty_plot_radius, 3)
                else:
                    pygame.draw.circle(plot_surface, COLOR_PLOT_BORDER, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_empty_plot_radius, 2)
                
                self.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
                
                # Draw letter
                letter_surface = building_letter_font.render(letter, True, WHITE)
                letter_rect = letter_surface.get_rect(center=(x, y))
                self.screen.blit(letter_surface, letter_rect)
    
    def _draw_under_construction_plots(self, ui_scale, scaled_empty_plot_radius,
                                       building_letter_font):
        """
        Draw yellow circles for buildings under construction.
        
        Phase 4: Extracted from draw_plots() for maintainability.
        Shows construction progress with yellowish tint.
        
        Renders:
        - Yellowish background circle
        - Gold ring if selected
        - Building letter (shows what's being built)
        - Hover brightening (+20%)
        - Click flash (+40%)
        
        Args:
            ui_scale: Scale factor based on camera zoom
            scaled_empty_plot_radius: Radius for plot circles
            building_letter_font: Font for building letters
        """
        scaled_plot_surface_size = int(PLOT_SURFACE_SIZE * ui_scale)
        scaled_plot_center_offset = scaled_plot_surface_size // 2
        
        for territory, plots in self.scaled_plots.items():
            owner = self.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue
            
            for plot_index, world_pos in enumerate(plots):
                # Check if under construction
                under_construction = None
                if territory in self.game_state.under_construction:
                    under_construction = self.game_state.under_construction[territory].get(plot_index)
                
                if not under_construction:
                    continue  # Skip non-construction plots
                
                # Get building info (with error handling)
                try:
                    building_type, turns_remaining = under_construction
                    building_info = self.game_state.building_types[building_type]
                    letter = building_info['letter']
                except (KeyError, TypeError, ValueError) as e:
                    print(f"Warning: Invalid under_construction data in {territory}: {e}")
                    continue
                
                # Transform to screen coordinates
                x, y = self.world_to_screen(world_pos)
                x, y = int(x), int(y)
                
                # Create surface
                plot_surface = pygame.Surface((scaled_plot_surface_size, scaled_plot_surface_size), pygame.SRCALPHA)
                
                # Base color (yellowish for construction)
                circle_color = COLOR_CONSTRUCTION
                
                # Check for hover
                is_hovering = False
                mouse_screen_x, mouse_screen_y = self.mouse_pos
                distance = ((x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2) ** 0.5
                if distance <= scaled_empty_plot_radius:
                    is_hovering = True
                
                # Check for click flash
                is_clicking = (self.clicked_element and 
                              self.clicked_element[0] == 'plot' and 
                              self.clicked_element[1] == (territory, plot_index))
                
                # Apply visual feedback
                if is_clicking:
                    circle_color = self.brighten_color(circle_color, 0.4)
                elif is_hovering:
                    circle_color = self.lighten_color(circle_color, 0.2)
                
                # Draw circle
                pygame.draw.circle(plot_surface, circle_color, 
                                 (scaled_plot_center_offset, scaled_plot_center_offset), 
                                 scaled_empty_plot_radius)
                
                # Highlight if selected
                if self.selected_plot and self.selected_plot == (territory, plot_index):
                    pygame.draw.circle(plot_surface, COLOR_GOLD_HIGHLIGHT, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_empty_plot_radius, 3)
                else:
                    pygame.draw.circle(plot_surface, COLOR_CONSTRUCTION_BORDER, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_empty_plot_radius, 2)
                
                self.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
                
                # Draw letter
                letter_surface = building_letter_font.render(letter, True, COLOR_CONSTRUCTION_TEXT)
                letter_rect = letter_surface.get_rect(center=(x, y))
                self.screen.blit(letter_surface, letter_rect)
    
    def _draw_empty_plot_markers(self, ui_scale, scaled_empty_plot_radius):
        """
        Draw small circles for empty plot locations.
        
        Phase 4: Extracted from draw_plots() for maintainability.
        Color indicates whether building is allowed this turn.
        
        Renders:
        - Green circle if can build this turn
        - Gray circle if cannot build (building limit reached)
        - Gold ring if selected
        - Hover brightening (+20%)
        - Click flash (+40%)
        
        Building Limit:
        One building per territory per turn. If already started construction
        this turn, empty plots show gray to indicate restriction.
        
        Args:
            ui_scale: Scale factor based on camera zoom
            scaled_empty_plot_radius: Radius for empty plot markers
        """
        scaled_plot_surface_size = int(PLOT_SURFACE_SIZE * ui_scale)
        scaled_plot_center_offset = scaled_plot_surface_size // 2
        
        for territory, plots in self.scaled_plots.items():
            owner = self.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue
            
            for plot_index, world_pos in enumerate(plots):
                # Check if plot is empty
                is_empty = True
                
                if territory in self.game_state.buildings:
                    if plot_index in self.game_state.buildings[territory]:
                        if self.game_state.buildings[territory][plot_index] is not None:
                            is_empty = False
                
                if territory in self.game_state.under_construction:
                    if plot_index in self.game_state.under_construction[territory]:
                        is_empty = False
                
                if not is_empty:
                    continue  # Skip non-empty plots
                
                # Transform to screen coordinates
                x, y = self.world_to_screen(world_pos)
                x, y = int(x), int(y)
                
                # Create surface
                plot_surface = pygame.Surface((scaled_plot_surface_size, scaled_plot_surface_size), pygame.SRCALPHA)
                
                # Check if can build on this territory this turn
                can_build = (owner == self.game_state.current_player and 
                            territory not in self.game_state.buildings_started_this_turn)
                
                # Color: Bright green if can build, gray otherwise
                if can_build:
                    circle_color = COLOR_EMPTY_PLOT_CAN_BUILD
                else:
                    circle_color = COLOR_EMPTY_PLOT_CANNOT_BUILD
                
                # Check for hover
                is_hovering = False
                mouse_screen_x, mouse_screen_y = self.mouse_pos
                distance = ((x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2) ** 0.5
                if distance <= scaled_empty_plot_radius:
                    is_hovering = True
                
                # Check for click flash
                is_clicking = (self.clicked_element and 
                              self.clicked_element[0] == 'plot' and 
                              self.clicked_element[1] == (territory, plot_index))
                
                # Apply visual feedback
                if is_clicking:
                    circle_color = self.brighten_color(circle_color, 0.4)
                elif is_hovering:
                    circle_color = self.lighten_color(circle_color, 0.2)
                
                # Draw circle
                pygame.draw.circle(plot_surface, circle_color, 
                                 (scaled_plot_center_offset, scaled_plot_center_offset), 
                                 scaled_empty_plot_radius)
                
                # Highlight if selected
                if self.selected_plot and self.selected_plot == (territory, plot_index):
                    pygame.draw.circle(plot_surface, COLOR_GOLD_HIGHLIGHT, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_empty_plot_radius, 3)
                else:
                    pygame.draw.circle(plot_surface, COLOR_EMPTY_PLOT_BORDER, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_empty_plot_radius, 2)
                
                self.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
    
    def _draw_quick_access_icons(self, ui_scale, scaled_building_icon_radius,
                                 scaled_icon_click_radius, icon_letter_font):
        """
        Draw orbiting building/training icons around selected plots.
        
        Phase 4: Extracted from draw_plots() for maintainability.
        Includes both building icons (F/M/B/K/Q) and training icons (S/A/P/C).
        
        Building Icons (F/M/B/K/Q):
        - Shown around selected empty plots
        - Green if can afford, red if cannot
        - Orbiting around the plot in a circle
        - Clickable for quick-building
        
        Training Icons (S/A/P/C):
        - Shown around selected Barracks
        - Green if can train, red if cannot
        - Checks gold, army limit, and queue space
        - Clickable for quick-training
        
        Args:
            ui_scale: Scale factor based on camera zoom
            scaled_building_icon_radius: Orbit radius for icons
            scaled_icon_click_radius: Clickable radius for icons
            icon_letter_font: Font for icon letters
        """
        import math
        
        scaled_plot_surface_size = int(PLOT_SURFACE_SIZE * ui_scale)
        scaled_plot_center_offset = scaled_plot_surface_size // 2
        
        # Draw quick-access building icons around selected empty plot
        if self.selected_plot and self.game_state.phase == 'playing':
            territory, plot_index = self.selected_plot
            if territory in self.scaled_plots and plot_index < len(self.scaled_plots[territory]):
                # Get plot position (with error handling)
                try:
                    world_plot_pos = self.scaled_plots[territory][plot_index]
                except (KeyError, IndexError, TypeError) as e:
                    print(f"Warning: Failed to get plot position for {territory}[{plot_index}]: {e}")
                    return
                
                # Transform to screen coordinates
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
                
                # Only show building options if plot is empty
                if is_empty:
                    building_list = list(self.game_state.building_types.keys())
                    num_buildings = len(building_list)
                    
                    # Track hover for map building icons
                    mouse_pos = pygame.mouse.get_pos()
                    current_hover = None
                    
                    for i, building_name in enumerate(building_list):
                        building_info = self.game_state.building_types[building_name]
                        letter = building_info['letter']
                        cost = building_info['cost']
                        
                        # Calculate position around plot (in screen coordinates)
                        angle = (i / num_buildings) * 2 * math.pi - math.pi / 2  # Start at top
                        icon_x = plot_x + int(scaled_building_icon_radius * math.cos(angle))
                        icon_y = plot_y + int(scaled_building_icon_radius * math.sin(angle))
                        
                        # Check if hovering over this icon
                        distance_to_mouse = ((mouse_pos[0] - icon_x) ** 2 + (mouse_pos[1] - icon_y) ** 2) ** 0.5
                        if distance_to_mouse < scaled_icon_click_radius:
                            current_hover = ('map_building', building_name)
                        
                        # Check if player can afford and if building is allowed this turn
                        current_gold = self.game_state.player_gold[self.game_state.current_player]
                        can_afford = current_gold >= cost
                        can_build_this_turn = territory not in self.game_state.buildings_started_this_turn
                        
                        # Check Keep restriction (only one Keep per territory)
                        can_build_keep = True
                        if building_name == 'Keep':
                            # Check if already has a Keep (completed or under construction)
                            if self.game_state.has_fortress(territory):
                                can_build_keep = False
                            # Check if Keep is under construction
                            if territory in self.game_state.under_construction:
                                for plot_idx, (bldg_type, _) in self.game_state.under_construction[territory].items():
                                    if bldg_type == 'Keep':
                                        can_build_keep = False
                                        break
                        
                        # Base color - consider affordability, building limit, AND Keep restriction
                        if can_afford and can_build_this_turn and can_build_keep:
                            icon_color = COLOR_ICON_AVAILABLE  # Green
                        else:
                            icon_color = COLOR_ICON_UNAVAILABLE  # Red
                        
                        # Check for hover
                        is_hovering = (distance_to_mouse < scaled_icon_click_radius)
                        
                        # Check for click flash
                        is_clicking = (self.clicked_element and 
                                      self.clicked_element[0] == 'map_building' and 
                                      self.clicked_element[1] == building_name)
                        
                        # Apply visual feedback
                        if is_clicking:
                            icon_color = self.brighten_color(icon_color, 0.4)
                        elif is_hovering:
                            icon_color = self.lighten_color(icon_color, 0.2)
                        
                        # Draw background
                        icon_surface = pygame.Surface((scaled_plot_surface_size, scaled_plot_surface_size), pygame.SRCALPHA)
                        pygame.draw.circle(icon_surface, icon_color, 
                                         (scaled_plot_center_offset, scaled_plot_center_offset), 
                                         scaled_icon_click_radius)
                        pygame.draw.circle(icon_surface, COLOR_ICON_BORDER, 
                                         (scaled_plot_center_offset, scaled_plot_center_offset), 
                                         scaled_icon_click_radius, 2)
                        self.screen.blit(icon_surface, (icon_x - scaled_plot_center_offset, icon_y - scaled_plot_center_offset))
                        
                        # Draw letter
                        letter_surface = icon_letter_font.render(letter, True, WHITE)
                        letter_rect = letter_surface.get_rect(center=(icon_x, icon_y))
                        self.screen.blit(letter_surface, letter_rect)
                    
                    # Update hover tracking
                    self.update_button_hover(current_hover, 'map_building')
                else:
                    # Plot not empty - clear map building hover if that's what was set
                    if self.hover_target_button and self.hover_target_button[0] == 'map_building':
                        self.hover_target_button = None
                        self.show_tooltip_button = None
                        self.hover_start_time_button = None
        
        # Draw quick-access training icons around selected Barracks
        if self.selected_barracks and self.game_state.phase == 'playing':
            territory, barracks_plot_index = self.selected_barracks
            if territory in self.scaled_plots and barracks_plot_index < len(self.scaled_plots[territory]):
                # Get Barracks position (with error handling)
                try:
                    world_barracks_pos = self.scaled_plots[territory][barracks_plot_index]
                except (KeyError, IndexError, TypeError) as e:
                    print(f"Warning: Failed to get Barracks position for {territory}[{barracks_plot_index}]: {e}")
                    return
                
                # Transform to screen coordinates
                plot_x, plot_y = self.world_to_screen(world_barracks_pos)
                plot_x, plot_y = int(plot_x), int(plot_y)
                
                # Draw training icons in a circle around the Barracks
                unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
                num_units = len(unit_types)
                
                # Get current gold and check conditions
                current_gold = self.game_state.player_gold[self.game_state.current_player]
                current_armies = self.game_state.armies.get(territory, 0)
                at_army_limit = current_armies >= self.game_state.MAX_ARMIES_PER_TERRITORY
                
                # Get current queue
                queue_count = 0
                if (territory in self.game_state.training_queue and 
                    barracks_plot_index in self.game_state.training_queue[territory]):
                    queue_count = len(self.game_state.training_queue[territory][barracks_plot_index])
                can_queue = queue_count < 5
                
                # Track hover for map training icons
                mouse_pos = pygame.mouse.get_pos()
                current_hover = None
                
                for i, unit_type in enumerate(unit_types):
                    unit_info = self.game_state.UNIT_TYPES[unit_type]
                    letter = unit_info['letter']
                    cost = unit_info['cost']
                    
                    # Calculate position around Barracks (in screen coordinates)
                    angle = (i / num_units) * 2 * math.pi - math.pi / 2  # Start at top
                    icon_x = plot_x + int(scaled_building_icon_radius * math.cos(angle))
                    icon_y = plot_y + int(scaled_building_icon_radius * math.sin(angle))
                    
                    # Check if hovering over this icon
                    distance_to_mouse = ((mouse_pos[0] - icon_x) ** 2 + (mouse_pos[1] - icon_y) ** 2) ** 0.5
                    if distance_to_mouse < scaled_icon_click_radius:
                        current_hover = ('map_training', unit_type)
                    
                    # Check if player can afford and can train
                    can_afford = current_gold >= cost
                    can_train = can_afford and can_queue and not at_army_limit
                    
                    # Base color
                    if can_train:
                        icon_color = COLOR_ICON_AVAILABLE
                    else:
                        icon_color = COLOR_ICON_UNAVAILABLE
                    
                    # Check for hover
                    is_hovering = (distance_to_mouse < scaled_icon_click_radius)
                    
                    # Check for click flash
                    is_clicking = (self.clicked_element and 
                                  self.clicked_element[0] == 'map_training' and 
                                  self.clicked_element[1] == unit_type)
                    
                    # Apply visual feedback
                    if is_clicking:
                        icon_color = self.brighten_color(icon_color, 0.4)
                    elif is_hovering:
                        icon_color = self.lighten_color(icon_color, 0.2)
                    
                    # Draw background
                    icon_surface = pygame.Surface((scaled_plot_surface_size, scaled_plot_surface_size), pygame.SRCALPHA)
                    pygame.draw.circle(icon_surface, icon_color, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_icon_click_radius)
                    pygame.draw.circle(icon_surface, COLOR_ICON_BORDER, 
                                     (scaled_plot_center_offset, scaled_plot_center_offset), 
                                     scaled_icon_click_radius, 2)
                    self.screen.blit(icon_surface, (icon_x - scaled_plot_center_offset, icon_y - scaled_plot_center_offset))
                    
                    # Draw letter
                    letter_surface = icon_letter_font.render(letter, True, WHITE)
                    letter_rect = letter_surface.get_rect(center=(icon_x, icon_y))
                    self.screen.blit(letter_surface, letter_rect)
                
                # Update hover tracking
                self.update_button_hover(current_hover, 'map_training')
    
    def draw_plots(self):
        """
        Draw building plots on territories owned by current player.
        
        Phase 4: Refactored into sub-methods for maintainability.
        Main method now orchestrates four rendering passes:
        1. Completed buildings - Circles with letter icons (F/M/B/K/Q)
        2. Under-construction - Yellowish tint + letter
        3. Empty plots - Small circles (green/gray)
        4. Quick-access icons - Orbiting around selected plots
        
        Each pass is handled by a dedicated method for clarity:
        - _draw_completed_building_plots()
        - _draw_under_construction_plots()
        - _draw_empty_plot_markers()
        - _draw_quick_access_icons()
        
        Visual Indicators:
            - Gold ring: Selected plot or Barracks
            - Green circles: Can build this turn
            - Gray circles: Cannot build (limit reached)
            - Bright green icons: Can afford building/training
            - Red icons: Cannot afford or other restriction
        
        Hover Detection:
            Tracks hover state for map building and training icons
            for tooltip display (with 0.5s delay).
        
        Building Limit:
            One building per territory per turn is enforced visually by
            coloring empty plots gray if limit is reached.
        
        Zoom-Based Scaling:
            Plot circles, building icons, and training icons scale 1.0x to 1.5x
            based on camera zoom for better visibility when zoomed in.
            Building letters scale dynamically to match plot size.
        
        Phase 4 Refactoring Benefits:
            - Each method < 200 lines
            - Clear single responsibilities
            - Much easier to modify individual rendering passes
            - Better code organization
        """
        # Only show plots in playing phase
        if self.game_state.phase != 'playing':
            return
        
        # Calculate UI scale factor based on zoom (1.0 at min zoom, 1.5 at max zoom)
        ui_scale = self.get_ui_scale_factor()
        
        # Calculate scaled sizes for UI elements
        scaled_empty_plot_radius = int(EMPTY_PLOT_RADIUS * ui_scale)
        scaled_building_icon_radius = int(BUILDING_ICON_RADIUS * ui_scale)
        scaled_icon_click_radius = int(ICON_CLICK_RADIUS * ui_scale)
        
        # Calculate fonts for building letters and icon letters
        building_letter_font_size = int(scaled_empty_plot_radius * 1.2)
        building_letter_font = pygame.font.Font(None, building_letter_font_size)
        
        icon_letter_font_size = int(scaled_icon_click_radius * 1.2)
        icon_letter_font = pygame.font.Font(None, icon_letter_font_size)
        
        # Render each plot type using dedicated methods
        self._draw_completed_building_plots(ui_scale, scaled_empty_plot_radius,
                                           building_letter_font)
        self._draw_under_construction_plots(ui_scale, scaled_empty_plot_radius,
                                           building_letter_font)
        self._draw_empty_plot_markers(ui_scale, scaled_empty_plot_radius)
        self._draw_quick_access_icons(ui_scale, scaled_building_icon_radius,
                                      scaled_icon_click_radius, icon_letter_font)
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
        # Check if clicking on map area (not bottom UI)
        if pos[1] >= BOTTOM_UI_Y:
            # Click is in bottom UI - will handle separately
            return
        
        # Convert screen position to world position for click detection
        # This makes clicks work correctly with camera offset and zoom!
        world_pos = self.screen_to_world(pos)
        
        # PRIORITY 1: Check if clicking on a quick-access building icon
        # NOTE: Icons checked FIRST (before armies) so they're clickable when overlapping!
        if self.selected_plot and self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
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
                    
                    import math
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
                            if self.game_state.start_construction(territory, plot_index, building_name):
                                self.selected_plot = None
                                self.selected_territory_info = None
                                self.clear_button_tooltip()  # Clear any lingering tooltips
                            return
        
        # PRIORITY 2: Check if clicking on a quick-access training icon (around Barracks)
        if self.selected_barracks and self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
            territory, barracks_plot_index = self.selected_barracks
            if territory in self.scaled_plots and barracks_plot_index < len(self.scaled_plots[territory]):
                # Get plot position in world coordinates
                world_barracks_pos = self.scaled_plots[territory][barracks_plot_index]
                # Transform to screen coordinates (same as rendering!)
                plot_x, plot_y = self.world_to_screen(world_barracks_pos)
                plot_x, plot_y = int(plot_x), int(plot_y)
                
                # Check if clicking on a training icon
                unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']
                num_units = len(unit_types)
                
                # Get scaled icon sizes for click detection (must match rendering!)
                ui_scale = self.get_ui_scale_factor()
                scaled_building_icon_radius = int(BUILDING_ICON_RADIUS * ui_scale)
                scaled_icon_click_radius = int(ICON_CLICK_RADIUS * ui_scale)
                
                import math
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
                        if self.game_state.start_training(territory, barracks_plot_index, unit_type):
                            # Training started successfully
                            self.clear_button_tooltip()  # Clear any lingering tooltips
                        # Stay on Barracks (don't deselect)
                        return
        
        # PRIORITY 3: Check if clicking on an army number circle (opens composition UI)
        # NOTE: Army check comes AFTER icon checks so icons take precedence when overlapping
        if self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
            army_territory = self.get_army_at_pos(world_pos)
            if army_territory:
                # Trigger click flash for visual feedback
                self.trigger_click_flash('army', army_territory)
                
                # Open army composition UI
                self.show_army_composition = True
                self.army_composition_territory = army_territory
                self.selected_army_units = []  # Clear selection
                
                # Deselect other UI elements
                self.game_state.deselect_army()
                self.selected_plot = None
                self.selected_barracks = None
                self.selected_territory_info = None
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
                
                if has_barracks:
                    # Select Barracks for training UI
                    self.selected_barracks = (territory, plot_index)
                    self.selected_plot = None
                    self.selected_territory_info = None
                    self.game_state.deselect_army()
                    self.show_army_composition = False  # Close composition UI
                    self.selected_army_units = []
                else:
                    # Select plot for building UI
                    self.selected_plot = plot_click
                    self.selected_barracks = None
                    self.selected_territory_info = None
                    self.game_state.deselect_army()
                    self.show_army_composition = False  # Close composition UI
                    self.selected_army_units = []
                return
        
        # Not clicking on a plot - handle territory click
        territory = self.get_territory_at_pos(world_pos)
        if not territory:
            # Clicking on empty space - deselect everything
            self.selected_plot = None
            self.selected_territory_info = None
            self.selected_barracks = None  # Deselect barracks too
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
        """Handle right-click for creating movement orders (Phase 2D: camera-aware)"""
        # Check if clicking on map area (not bottom UI)
        if pos[1] >= BOTTOM_UI_Y:
            return
        
        # Convert screen position to world position (Phase 2D: camera support!)
        world_pos = self.screen_to_world(pos)
        
        # Get the territory clicked
        territory = self.get_territory_at_pos(world_pos)
        if not territory:
            return
        
        # CASE 1: Composition UI is open with selected units
        if self.show_army_composition and self.army_composition_territory and self.selected_army_units:
            from_territory = self.army_composition_territory
            
            # Can't move to same territory
            if from_territory == territory:
                return
            
            # Check if this would exceed army limit (for reinforcements)
            owner_from = self.game_state.territory_owners.get(from_territory, -1)
            owner_to = self.game_state.territory_owners.get(territory, -1)
            if owner_from == owner_to:
                # This is a reinforcement
                current_armies_dest = self.game_state.armies.get(territory, 0)
                reinforcing_count = len(self.selected_army_units)
                if current_armies_dest + reinforcing_count > self.game_state.MAX_ARMIES_PER_TERRITORY:
                    self.game_state.add_message(f"Cannot reinforce {territory}: would exceed army limit!")
                    return
            
            # Create movement order for selected units
            if self.game_state.add_movement_order_for_units(from_territory, territory, self.selected_army_units):
                # Clear selection after issuing order
                self.selected_army_units = []
            return
        
        # CASE 2: Legacy - army selected (old system compatibility)
        if self.game_state.selected_army:
            from_territory, _ = self.game_state.selected_army
            
            # Can't move to same territory
            if from_territory == territory:
                return
            
            # Check if this would exceed army limit (for reinforcements)
            owner_from = self.game_state.territory_owners.get(from_territory, -1)
            owner_to = self.game_state.territory_owners.get(territory, -1)
            if owner_from == owner_to:
                # This is a reinforcement
                current_armies_dest = self.game_state.armies.get(territory, 0)
                reinforcing_count = self.game_state.armies_unmoved.get(from_territory, 0)
                if current_armies_dest + reinforcing_count > self.game_state.MAX_ARMIES_PER_TERRITORY:
                    self.game_state.add_message(f"Cannot reinforce {territory}: would exceed army limit!")
                    return
            
            # Try to create movement order
            self.game_state.add_movement_order(from_territory, territory)
    
    def draw_territories(self):
        """Draw territory overlays, markers and ownership colors"""
        # First pass: Draw all territory overlays
        for territory in self.scaled_polygons.keys():
            owner = self.game_state.territory_owners.get(territory, -1)
            if owner >= 0:
                # Territory is owned - draw colored overlay
                color = self.game_state.get_player_color(owner)
                self.draw_territory_overlay(territory, color, alpha=80)
        
        # Draw territories with moved armies with darker overlay
        if self.game_state.phase == 'playing':
            for territory in self.scaled_polygons.keys():
                if self.game_state.armies_moved[territory] > 0:
                    # Has some moved armies - show darker overlay
                    self.draw_territory_overlay(territory, (50, 50, 50), alpha=40)
        
        # Second pass: Draw hover highlight (semi-transparent owner color)
        if self.hovered_territory and self.hovered_territory in self.scaled_polygons:
            hover_owner = self.game_state.territory_owners.get(self.hovered_territory, -1)
            if hover_owner >= 0:
                # Owned territory - use owner's color for hover
                hover_color = self.game_state.get_player_color(hover_owner)
                self.draw_territory_overlay(self.hovered_territory, hover_color, alpha=60, outline=True)
            else:
                # Neutral territory - use white/light gray
                self.draw_territory_overlay(self.hovered_territory, (200, 200, 200), alpha=60, outline=True)
        
        # Third pass: Draw selected territory highlight (prominent border)
        if self.selected_territory_info and self.selected_territory_info in self.scaled_polygons:
            selected_owner = self.game_state.territory_owners.get(self.selected_territory_info, -1)
            if selected_owner >= 0:
                # Owned territory - use owner's color with thick border
                selected_color = self.game_state.get_player_color(selected_owner)
                # Draw thick outline for selected territory (transform to screen coords!)
                world_polygon = self.scaled_polygons[self.selected_territory_info]
                screen_polygon = [self.world_to_screen(point) for point in world_polygon]
                pygame.draw.lines(self.screen, selected_color, True, screen_polygon, 5)  # 5px thick border
            else:
                # Neutral territory - use white border
                world_polygon = self.scaled_polygons[self.selected_territory_info]
                screen_polygon = [self.world_to_screen(point) for point in world_polygon]
                pygame.draw.lines(self.screen, WHITE, True, screen_polygon, 5)  # 5px thick border
        
        # Fourth pass: Draw old selected_territory highlight (for movement)
        if self.game_state.selected_territory and self.game_state.selected_territory in self.scaled_polygons:
            self.draw_territory_overlay(self.game_state.selected_territory, (255, 255, 0), alpha=100, outline=True)
        
        # Fifth pass: Draw center markers and army counts
        # NOTE: Armies drawn BEFORE plots so plot icons appear on top!
        for territory, world_center in self.scaled_centers.items():
            if territory not in self.game_state.territory_owners:
                continue
            
            # Transform center from world to screen coordinates (Phase 2D!)
            x, y = self.world_to_screen(world_center)
            
            owner = self.game_state.territory_owners[territory]
            
            # Draw circle for territory center
            if owner >= 0:
                color = self.game_state.get_player_color(owner)
            else:
                color = (150, 150, 150)  # Neutral
            
            # Draw selection glow if this army is selected OR composition UI is open for it
            is_selected = False
            if self.game_state.selected_army and self.game_state.selected_army[0] == territory:
                is_selected = True
            elif self.show_army_composition and self.army_composition_territory == territory:
                is_selected = True
            
            if is_selected:
                # Pulsing green glow effect (scales with zoom!)
                import math
                import time
                pulse = abs(math.sin(time.time() * 2))  # Pulse between 0 and 1
                glow_alpha = int(100 + 100 * pulse)  # Between 100 and 200
                
                # Get UI scale factor for zoom-based sizing
                ui_scale = self.get_ui_scale_factor()
                
                # Draw multiple glow circles for effect (scaled with zoom)
                for i in range(3):
                    glow_radius = int((18 + i * 3) * ui_scale)
                    glow_surface = pygame.Surface((glow_radius * 2 + 10, glow_radius * 2 + 10), pygame.SRCALPHA)
                    pygame.draw.circle(glow_surface, (0, 255, 0, glow_alpha // (i + 1)), 
                                     (glow_radius + 5, glow_radius + 5), glow_radius, 3)
                    self.screen.blit(glow_surface, (int(x) - glow_radius - 5, int(y) - glow_radius - 5))
            
            # Draw merge/attack destination highlight
            # Check if this territory is receiving an order from selected army OR composition UI
            selected_territory = None
            if self.game_state.selected_army:
                selected_territory = self.game_state.selected_army[0]
            elif self.show_army_composition and self.army_composition_territory:
                selected_territory = self.army_composition_territory
            
            if selected_territory:
                # Check if selected army has a move order to this territory
                for order in self.game_state.movement_orders:
                    if order.from_territory == selected_territory and order.to_territory == territory:
                        # Check if destination is friendly or enemy
                        dest_owner = self.game_state.territory_owners.get(territory, -1)
                        
                        if dest_owner == order.player:
                            # This is a MERGE destination - draw cyan highlight
                            import math
                            import time
                            pulse = abs(math.sin(time.time() * 3))  # Slightly faster pulse
                            glow_alpha = int(120 + 80 * pulse)  # Between 120 and 200
                            
                            # Draw cyan glow rings
                            for i in range(3):
                                glow_radius = 20 + i * 4
                                glow_surface = pygame.Surface((glow_radius * 2 + 10, glow_radius * 2 + 10), pygame.SRCALPHA)
                                pygame.draw.circle(glow_surface, (0, 200, 200, glow_alpha // (i + 1)), 
                                                 (glow_radius + 5, glow_radius + 5), glow_radius, 4)
                                self.screen.blit(glow_surface, (int(x) - glow_radius - 5, int(y) - glow_radius - 5))
                        else:
                            # This is an ATTACK destination - draw red highlight
                            import math
                            import time
                            pulse = abs(math.sin(time.time() * 3))  # Slightly faster pulse
                            glow_alpha = int(120 + 80 * pulse)  # Between 120 and 200
                            
                            # Draw red glow rings (scaled with zoom)
                            ui_scale = self.get_ui_scale_factor()
                            for i in range(3):
                                glow_radius = int((20 + i * 4) * ui_scale)
                                glow_surface = pygame.Surface((glow_radius * 2 + 10, glow_radius * 2 + 10), pygame.SRCALPHA)
                                pygame.draw.circle(glow_surface, (200, 0, 0, glow_alpha // (i + 1)), 
                                                 (glow_radius + 5, glow_radius + 5), glow_radius, 4)
                                self.screen.blit(glow_surface, (int(x) - glow_radius - 5, int(y) - glow_radius - 5))
                        break
            
            # Apply zoom-based scaling to army circles
            ui_scale = self.get_ui_scale_factor()
            scaled_army_radius = int(ARMY_CIRCLE_RADIUS * ui_scale)
            
            # Base color
            army_color = color
            
            # Check for hover (using screen position)
            is_hovering = False
            mouse_screen_x, mouse_screen_y = self.mouse_pos
            distance = ((x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2) ** 0.5
            if distance <= scaled_army_radius:
                is_hovering = True
            
            # Check for click flash
            is_clicking = (self.clicked_element and 
                          self.clicked_element[0] == 'army' and 
                          self.clicked_element[1] == territory)
            
            # Apply visual feedback
            if is_clicking:
                army_color = self.brighten_color(army_color, 0.4)
            elif is_hovering:
                army_color = self.lighten_color(army_color, 0.2)
            
            pygame.draw.circle(self.screen, army_color, (int(x), int(y)), scaled_army_radius)
            pygame.draw.circle(self.screen, BLACK, (int(x), int(y)), scaled_army_radius, 2)
            
            # Draw army count if > 0 (total armies)
            total_armies = self.game_state.armies_unmoved[territory] + self.game_state.armies_moved[territory]
            if total_armies > 0:
                army_text = self.font.render(str(total_armies), True, WHITE)
                text_rect = army_text.get_rect(center=(int(x), int(y)))
                self.screen.blit(army_text, text_rect)
        
        # Sixth pass: Draw building plots and their icons (AFTER armies!)
        # This ensures plot/barracks icons appear above army circles
        self.draw_plots()
    
    def draw_movement_arrows(self):
        """Draw arrows showing planned movement orders"""
        import math
        
        # Group orders by (from_territory, to_territory) to show total count
        route_counts = {}  # (from, to) -> total_army_count
        
        for order in self.game_state.movement_orders:
            route = (order.from_territory, order.to_territory)
            if route not in route_counts:
                route_counts[route] = 0
            route_counts[route] += order.army_count
        
        # Draw one arrow per unique route with total count
        for (from_territory, to_territory), total_count in route_counts.items():
            # Get territory centers in world coordinates (already scaled!)
            if from_territory not in self.scaled_centers or to_territory not in self.scaled_centers:
                continue
            
            from_world = self.scaled_centers[from_territory]
            to_world = self.scaled_centers[to_territory]
            
            # Transform to screen coordinates (Phase 2D: camera transformation!)
            from_x, from_y = self.world_to_screen(from_world)
            to_x, to_y = self.world_to_screen(to_world)
            
            # Arrow color - green for movement orders
            arrow_color = COLOR_ARROW_MOVEMENT
            
            # Draw main line (slightly thicker)
            pygame.draw.line(self.screen, arrow_color, (int(from_x), int(from_y)), (int(to_x), int(to_y)), ARROW_LINE_WIDTH)
            
            # Calculate arrowhead
            dx = to_x - from_x
            dy = to_y - from_y
            length = math.sqrt(dx*dx + dy*dy)
            
            if length > 0:
                # Normalize direction
                dx /= length
                dy /= length
                
                # Arrowhead size
                arrow_size = ARROW_HEAD_SIZE
                arrow_angle = ARROW_HEAD_ANGLE_RAD
                
                # Calculate arrowhead points
                # Left point
                left_x = to_x - arrow_size * (dx * math.cos(arrow_angle) - dy * math.sin(arrow_angle))
                left_y = to_y - arrow_size * (dy * math.cos(arrow_angle) + dx * math.sin(arrow_angle))
                
                # Right point
                right_x = to_x - arrow_size * (dx * math.cos(arrow_angle) + dy * math.sin(arrow_angle))
                right_y = to_y - arrow_size * (dy * math.cos(arrow_angle) - dx * math.sin(arrow_angle))
                
                # Draw arrowhead
                pygame.draw.polygon(self.screen, arrow_color, [
                    (int(to_x), int(to_y)),
                    (int(left_x), int(left_y)),
                    (int(right_x), int(right_y))
                ])
                
                # Draw army count badge at midpoint (showing TOTAL count)
                mid_x = int((from_x + to_x) / 2)
                mid_y = int((from_y + to_y) / 2)
                
                # Draw badge using helper (Phase 1D)
                self.draw_circle_badge((mid_x, mid_y), total_count, border_color=arrow_color)
    
    def draw_battle_markers(self):
        """Draw battle markers for territories with pending battles (Phase 2D: camera-aware)"""
        if self.game_state.turn_phase != 'battles':
            return
        
        import math  # For pulse effect
        
        # Clear battle markers list
        self.battle_markers = []
        
        for i, battle in enumerate(self.game_state.pending_battles):
            territory = battle.territory
            
            # Get world coordinates from scaled centers
            if territory not in self.scaled_centers:
                continue
            
            world_center = self.scaled_centers[territory]
            
            # Transform to screen coordinates (Phase 2D: camera transformation!)
            screen_x, screen_y = self.world_to_screen(world_center)
            screen_x = int(screen_x)
            screen_y = int(screen_y)
            
            # Check if this battle is selected
            is_selected = (self.selected_battle_index == i)
            
            # Draw pulsing circle for battle (larger if selected)
            pulse = abs(math.sin(pygame.time.get_ticks() / 300))  # Pulse effect
            base_radius = 35 if is_selected else 30
            radius = int(base_radius + pulse * 10)
            alpha = int(180 + pulse * 75) if is_selected else int(150 + pulse * 100)
            
            # Color: Yellow if selected, red if not
            color = (255, 200, 0, alpha) if is_selected else (255, 0, 0, alpha)
            
            # Semi-transparent circle
            battle_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(battle_surface, color, (radius, radius), radius)
            self.screen.blit(battle_surface, (screen_x - radius, screen_y - radius))
            
            # Draw crossed swords icon (use X for compatibility)
            sword_text = self.large_font.render("X", True, WHITE)
            sword_rect = sword_text.get_rect(center=(screen_x, screen_y))
            self.screen.blit(sword_text, sword_rect)
            
            # Draw battle number
            number_text = self.small_font.render(f"#{i+1}", True, WHITE)
            number_rect = number_text.get_rect(center=(screen_x, screen_y + 25))
            self.screen.blit(number_text, number_rect)
            
            # Store clickable area for this battle marker
            self.battle_markers.append(pygame.Rect(screen_x - radius, screen_y - radius, 
                                                    radius * 2, radius * 2))
    
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
            if player in battle.army_compositions:
                comp = battle.army_compositions[player]
                comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])
                player_text = self.font.render(f"Player {player + 1}: {comp_str}", True, player_color)
            else:
                player_text = self.font.render(f"Player {player + 1}: {count} armies", True, player_color)
            
            player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(player_text, player_rect)
            y_pos += 40
        
        y_pos += 20
        
        # Show tactical prediction based on unit types
        pred_text = self.small_font.render("(Unit types and counters will determine victor)", True, (150, 150, 150))
        pred_rect = pred_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
        self.screen.blit(pred_text, pred_rect)
        
        # Resolve button
        button_y = modal_y + modal_height - 80
        resolve_rect = pygame.Rect(WINDOW_WIDTH // 2 - 100, button_y, 200, 50)
        pygame.draw.rect(self.screen, (200, 50, 50), resolve_rect)
        pygame.draw.rect(self.screen, WHITE, resolve_rect, 3)
        button_text = self.font.render("RESOLVE BATTLE", True, WHITE)
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
            # TWO-PHASE KEEP BATTLE DISPLAY
            title = self.font.render("Two-Phase Keep Battle:", True, (255, 200, 100))
            title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(title, title_rect)
            y_pos += 40
            
            # Phase 1 info
            phase1_text = self.small_font.render("Phase 1: Attackers vs Garrison (counters apply)", True, (150, 200, 255))
            phase1_rect = phase1_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(phase1_text, phase1_rect)
            y_pos += 30
            
            # Show compositions with effective strengths
            for player, count in armies.items():
                player_color = self.game_state.get_player_color(player)
                
                if player in compositions:
                    comp = compositions[player]
                    comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])
                    player_text = self.small_font.render(f"Player {player + 1}: {comp_str}", True, player_color)
                else:
                    player_text = self.small_font.render(f"Player {player + 1}: {count} armies", True, player_color)
                
                player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(player_text, player_rect)
                y_pos += 25
            
            y_pos += 10
            
            # Phase 2 info
            phase2_text = self.small_font.render("Phase 2: Remaining attackers vs Keep (+2 armies)", True, (255, 200, 100))
            phase2_rect = phase2_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(phase2_text, phase2_rect)
            y_pos += 30
            
            # Keep is type-neutral
            keep_note = self.small_font.render("(Keep defense is type-neutral)", True, (150, 150, 150))
            keep_note_rect = keep_note.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(keep_note, keep_note_rect)
            
        else:
            # NORMAL BATTLE DISPLAY
            title = self.font.render("Deterministic Combat:", True, (255, 200, 100))
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
                    
                    if enemy_comp:
                        eff_str = self.game_state.calculate_army_effective_strength(comp, enemy_comp)
                        effective_strengths[player] = eff_str
                        
                        player_text = self.small_font.render(
                            f"Player {player + 1}: {comp_str}", 
                            True, player_color
                        )
                        strength_text = self.small_font.render(
                            f"Effective Strength: {eff_str:.1f}",
                            True, (200, 200, 200)
                        )
                    else:
                        player_text = self.small_font.render(f"Player {player + 1}: {comp_str}", True, player_color)
                        strength_text = None
                else:
                    player_text = self.small_font.render(f"Player {player + 1}: {count} armies", True, player_color)
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
                    advantage_text = self.font.render(
                        f"Player {leader + 1} has superior strength!",
                        True, leader_color
                    )
                    advantage_rect = advantage_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                    self.screen.blit(advantage_text, advantage_rect)
                else:
                    tie_text = self.font.render("Perfect tie - dice will decide!", True, (255, 200, 0))
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
            winner_text = self.large_font.render(f"Player {winner + 1} WINS!", True, winner_color)
            winner_rect = winner_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(winner_text, winner_rect)
            y_pos += 50
            
            if surviving > 0:
                surv_text = self.font.render(f"{surviving} armies remain", True, WHITE)
                surv_rect = surv_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(surv_text, surv_rect)
                y_pos += 40
        else:
            tie_text = self.large_font.render("PERFECT TIE!", True, (255, 200, 0))
            tie_rect = tie_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(tie_text, tie_rect)
            y_pos += 50
            
            neutral_text = self.font.render("Territory becomes neutral", True, WHITE)
            neutral_rect = neutral_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(neutral_text, neutral_rect)
            y_pos += 40
        
        # Battle Summary Section
        y_pos += 10
        summary_title = self.font.render("Battle Summary:", True, (200, 200, 200))
        summary_rect = summary_title.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
        self.screen.blit(summary_title, summary_rect)
        y_pos += 30
        
        if has_keep:
            # Keep battle summary
            summary_line1 = self.small_font.render("Two-phase Keep battle", True, (255, 200, 100))
            line1_rect = summary_line1.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
            self.screen.blit(summary_line1, line1_rect)
            y_pos += 25
            
            # Show participants
            for player, count in armies.items():
                player_color = self.game_state.get_player_color(player)
                if player in compositions:
                    comp = compositions[player]
                    comp_str = ", ".join([f"{c} {ut}" for ut, c in sorted(comp.items())])
                    role = "Defender (+Keep)" if player == self.battle_result.get('defender', -1) else "Attacker"
                    player_text = self.small_font.render(f"P{player + 1} ({role}): {comp_str}", True, player_color)
                else:
                    player_text = self.small_font.render(f"Player {player + 1}: {count} armies", True, player_color)
                
                player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(player_text, player_rect)
                y_pos += 22
            
        else:
            # Normal battle summary
            summary_line1 = self.small_font.render("Unit counters determined outcome", True, (150, 200, 255))
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
                        victory_mark = " ✓" if player == winner else ""
                        player_text = self.small_font.render(
                            f"P{player + 1}: {comp_str} (Str: {eff_str:.1f}){victory_mark}", 
                            True, player_color
                        )
                    else:
                        player_text = self.small_font.render(f"P{player + 1}: {comp_str}", True, player_color)
                else:
                    player_text = self.small_font.render(f"Player {player + 1}: {count} armies", True, player_color)
                
                player_rect = player_text.get_rect(center=(WINDOW_WIDTH // 2, y_pos))
                self.screen.blit(player_text, player_rect)
                y_pos += 22
        
        # Close button
        button_y = modal_y + modal_height - 80
        close_rect = pygame.Rect(WINDOW_WIDTH // 2 - 80, button_y, 160, 50)
        pygame.draw.rect(self.screen, (50, 150, 50), close_rect)
        pygame.draw.rect(self.screen, WHITE, close_rect, 3)
        button_text = self.font.render("CLOSE", True, WHITE)
        button_text_rect = button_text.get_rect(center=close_rect.center)
        self.screen.blit(button_text, button_text_rect)
        self.close_popup_button = close_rect
    
    def draw_battle_popup(self):
        """
        Draw modal popup for battle resolution.
        
        Phase 7: Refactored into state-specific sub-methods for maintainability.
        Main method now orchestrates three popup states:
        1. Initial - Show participants (_draw_battle_popup_initial)
        2. Resolving - Show calculations (_draw_battle_popup_resolving)
        3. Result - Show winner and summary (_draw_battle_popup_result)
        
        Each state has clear UI responsibilities and can be modified independently.
        """
        if not self.battle_popup_visible:
            return
        
        # Get battle reference (only needed for 'initial' state)
        battle = None
        if self.selected_battle_index is not None and self.selected_battle_index < len(self.game_state.pending_battles):
            battle = self.game_state.pending_battles[self.selected_battle_index]
        
        # For result/resolving states, we use stored battle_result
        if self.battle_popup_state != 'initial' and not self.battle_result:
            return  # No data to display
        
        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        # Modal window
        modal_width = 500
        modal_height = 500  # Increased from 400 to fit battle summary
        modal_x = (WINDOW_WIDTH - modal_width) // 2
        modal_y = (MAP_HEIGHT - modal_height) // 2
        
        # Draw modal background
        modal_rect = pygame.Rect(modal_x, modal_y, modal_width, modal_height)
        pygame.draw.rect(self.screen, (40, 40, 40), modal_rect)
        pygame.draw.rect(self.screen, (200, 200, 200), modal_rect, 4)
        
        # Title
        territory_name = battle.territory if battle else self.battle_result.get('territory', 'Unknown')
        title_text = self.large_font.render(f"Battle at {territory_name}", True, WHITE)
        title_rect = title_text.get_rect(center=(WINDOW_WIDTH // 2, modal_y + 30))
        self.screen.blit(title_text, title_rect)
        
        y_pos = modal_y + 80
        
        # Delegate to state-specific methods
        if self.battle_popup_state == 'initial':
            self._draw_battle_popup_initial(battle, modal_x, modal_y, modal_height, y_pos)
        
        elif self.battle_popup_state == 'resolving':
            self._draw_battle_popup_resolving(modal_x, modal_y, y_pos)
        
        elif self.battle_popup_state == 'result':
            self._draw_battle_popup_result(modal_x, modal_y, modal_height, y_pos)
    
    def draw_chat_input(self):
        """
        Draw chat input box above bottom UI panel.
        
        Appears when user presses ENTER.
        Shows current typed text with cursor.
        """
        if not self.chat_input_active:
            return
        
        # Chat input dimensions - just above bottom UI
        input_height = 40
        input_y = BOTTOM_UI_Y - input_height - 5  # 5px gap above bottom UI
        input_x = 10
        input_width = WINDOW_WIDTH - 20
        
        # Draw background with slight transparency
        input_surface = pygame.Surface((input_width, input_height), pygame.SRCALPHA)
        pygame.draw.rect(input_surface, (40, 40, 40, 240), (0, 0, input_width, input_height))
        pygame.draw.rect(input_surface, (100, 200, 255), (0, 0, input_width, input_height), 3)  # Blue border
        self.screen.blit(input_surface, (input_x, input_y))
        
        # Draw prompt text
        prompt_text = self.small_font.render("Chat:", True, (150, 150, 150))
        self.screen.blit(prompt_text, (input_x + 10, input_y + 12))
        
        # Draw current text being typed
        text_x = input_x + 60
        chat_text = self.small_font.render(self.chat_input_text, True, WHITE)
        self.screen.blit(chat_text, (text_x, input_y + 12))
        
        # Draw blinking cursor
        import time
        if int(time.time() * 2) % 2 == 0:  # Blink every 0.5 seconds
            cursor_x = text_x + chat_text.get_width() + 2
            pygame.draw.line(self.screen, WHITE, 
                           (cursor_x, input_y + 10), 
                           (cursor_x, input_y + input_height - 10), 2)
        
        # Draw instructions
        instructions = self.small_font.render("ENTER to send | ESC to cancel", True, (150, 150, 150))
        inst_rect = instructions.get_rect(right=input_x + input_width - 10, centery=input_y + input_height // 2)
        self.screen.blit(instructions, inst_rect)
    
    def draw_top_panel(self):
        """
        Draw top panel spanning full screen width.
        
        Phase A: UI Redesign - Top Panel
        This panel will eventually contain:
        - Options/Menu buttons
        - Player stats (armies, income, gold)
        - Other game controls
        
        Currently shows placeholder text.
        """
        # Top panel background (match bottom UI color: light gray)
        panel_rect = pygame.Rect(0, 0, WINDOW_WIDTH, TOP_PANEL_HEIGHT)
        pygame.draw.rect(self.screen, (220, 220, 220), panel_rect)
        
        # Border at bottom
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (0, TOP_PANEL_HEIGHT - 1), 
                        (WINDOW_WIDTH, TOP_PANEL_HEIGHT - 1), 2)
        
        # Placeholder content (left side) - darker text for light background
        placeholder_text = self.small_font.render("Player Controls - Coming Soon", True, (100, 100, 100))
        text_rect = placeholder_text.get_rect(midleft=(20, TOP_PANEL_HEIGHT // 2))
        self.screen.blit(placeholder_text, text_rect)
        
        # Placeholder stats (right side) - example of future content
        if hasattr(self.game_state, 'current_player'):
            player = self.game_state.current_player
            gold = self.game_state.player_gold[player]
            income = self.game_state.calculate_player_income(player)
            
            stats_text = self.small_font.render(
                f"Gold: {gold}  |  Income: +{income}/turn", 
                True, BLACK  # Dark text for visibility on light background
            )
            stats_rect = stats_text.get_rect(midright=(WINDOW_WIDTH - 20, TOP_PANEL_HEIGHT // 2))
            self.screen.blit(stats_text, stats_rect)
    
    def _draw_action_queue_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """Draw Action Queue tab content (movement orders)."""
        # Header
        header_y = content_start_y
        header_text = self.font.render("Action Queue", True, WHITE)
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.screen.blit(header_text, header_rect)
        
        # Draw separator line
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (sidebar_x + 10, header_y + 30),
                        (sidebar_x + sidebar_width - 10, header_y + 30), 2)
        
        # Check if there are any orders
        if len(self.game_state.movement_orders) == 0:
            # Show empty message
            empty_text = self.small_font.render("No actions queued", True, (150, 150, 150))
            empty_rect = empty_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 80))
            self.screen.blit(empty_text, empty_rect)
            return
        
        # Draw each order
        order_y = header_y + UIConstants.HEADER_OFFSET
        order_height = 60
        self.order_cancel_buttons = []  # Store button rects for click detection
        
        for i, order in enumerate(self.game_state.movement_orders):
            if order_y + order_height > sidebar_y + sidebar_height - 10:
                # Too many orders to fit, show scroll indicator
                scroll_text = self.small_font.render("...", True, WHITE)
                self.screen.blit(scroll_text, (sidebar_x + sidebar_width // 2 - 10, order_y))
                break
            
            # Order background
            order_rect = pygame.Rect(sidebar_x + 10, order_y, sidebar_width - 20, order_height - 5)
            pygame.draw.rect(self.screen, (60, 60, 60), order_rect, border_radius=5)
            pygame.draw.rect(self.screen, (0, 200, 0), order_rect, 2, border_radius=5)
            
            # Army count and icon
            count_text = self.font.render(f"🗡 {order.army_count}", True, WHITE)
            self.screen.blit(count_text, (sidebar_x + 20, order_y + 5))
            
            # From territory
            from_text = self.small_font.render(order.from_territory, True, (200, 200, 200))
            from_rect = from_text.get_rect(x=sidebar_x + 20, y=order_y + 28)
            # Truncate if too long
            if from_rect.width > sidebar_width - 80:
                from_text = self.small_font.render(order.from_territory[:15] + "...", True, (200, 200, 200))
            self.screen.blit(from_text, (sidebar_x + 20, order_y + 28))
            
            # Arrow
            arrow_text = self.small_font.render("→", True, (0, 200, 0))
            self.screen.blit(arrow_text, (sidebar_x + 20, order_y + 42))
            
            # To territory
            to_text = self.small_font.render(order.to_territory, True, (200, 200, 200))
            to_rect = to_text.get_rect(x=sidebar_x + 40, y=order_y + 42)
            # Truncate if too long
            if to_rect.width > sidebar_width - 100:
                to_text = self.small_font.render(order.to_territory[:15] + "...", True, (200, 200, 200))
            self.screen.blit(to_text, (sidebar_x + 40, order_y + 42))
            
            # Cancel button (X)
            cancel_button_rect = pygame.Rect(sidebar_x + sidebar_width - 45, order_y + 18, 30, 25)
            pygame.draw.rect(self.screen, (200, 50, 50), cancel_button_rect, border_radius=3)
            cancel_text = self.font.render("✖", True, WHITE)
            cancel_text_rect = cancel_text.get_rect(center=cancel_button_rect.center)
            self.screen.blit(cancel_text, cancel_text_rect)
            
            # Store button rect with order index for click detection
            self.order_cancel_buttons.append((cancel_button_rect, i))
            
            order_y += order_height
    
    def _draw_action_log_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """
        Draw Action Log tab content (Phase C: Migration from bottom panel).
        
        Shows all game messages in the sidebar tab instead of overlay.
        Messages include:
        - Battle results
        - Building completions
        - Army training completions
        - Territory captures
        - Income updates
        """
        # Header
        header_y = content_start_y
        header_text = self.font.render("Action Log", True, WHITE)
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.screen.blit(header_text, header_rect)
        
        # Draw separator line
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (sidebar_x + 10, header_y + 30),
                        (sidebar_x + sidebar_width - 10, header_y + 30), 2)
        
        # Check if there are any messages
        if len(self.game_state.messages) == 0:
            # Show empty message
            empty_text = self.small_font.render("No actions yet", True, (150, 150, 150))
            empty_rect = empty_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 80))
            self.screen.blit(empty_text, empty_rect)
            return
        
        # Get messages to display (oldest to newest)
        all_messages = self.game_state.messages  # Already in chronological order
        total_messages = len(all_messages)
        
        # Calculate approximate visible messages
        # Use generous estimate for selection - rendering loop will stop when full
        available_height = sidebar_y + sidebar_height - (header_y + UIConstants.HEADER_OFFSET) - UIConstants.BOTTOM_RESERVE
        approx_messages_visible = max(5, available_height // UIConstants.PIXELS_PER_MESSAGE_SELECTION)
        
        # Calculate which messages to show based on scroll offset
        # When scroll_offset = 0: Show newest messages (end of list)
        # When scroll_offset > 0: Scroll back in history
        
        # End index is total minus scroll offset
        end_index = total_messages - self.action_log_scroll_offset
        # Start index ensures we don't show more than fits
        start_index = max(0, end_index - approx_messages_visible)
        
        messages_to_show = all_messages[start_index:end_index]
        start_msg_index = start_index
        
        # Draw messages (oldest to newest, top to bottom)
        msg_y = header_y + UIConstants.HEADER_OFFSET
        messages_rendered = 0
        
        for message in messages_to_show:
            # Check if we're out of space
            if msg_y + 40 > sidebar_y + sidebar_height - UIConstants.BOTTOM_RESERVE:
                break
            
            messages_rendered += 1
            
            # Word wrap for long messages (fit in sidebar)
            max_chars = UIConstants.MESSAGE_MAX_CHARS
            if len(message) > max_chars:
                words = message.split()
                line = ""
                for word in words:
                    test_line = line + " " + word if line else word
                    if len(test_line) > max_chars:
                        # Draw current line
                        msg_text = self.small_font.render(line, True, (200, 200, 200))
                        self.screen.blit(msg_text, (sidebar_x + 10, msg_y))
                        msg_y += 18
                        line = word
                        
                        # Check space again
                        if msg_y + 40 > sidebar_y + sidebar_height - UIConstants.BOTTOM_RESERVE:
                            break
                    else:
                        line = test_line
                
                # Draw last line
                if line and msg_y + 20 < sidebar_y + sidebar_height - 40:
                    msg_text = self.small_font.render(line, True, (200, 200, 200))
                    self.screen.blit(msg_text, (sidebar_x + 10, msg_y))
                    msg_y += 18
            else:
                # Short message - draw directly
                msg_text = self.small_font.render(message, True, (200, 200, 200))
                self.screen.blit(msg_text, (sidebar_x + 10, msg_y))
                msg_y += 18
            
            # Add small gap between messages
            msg_y += 5
        
        # Calculate actual end index based on what we rendered
        actual_end_index = start_msg_index + messages_rendered
        
        # Draw scroll position indicator on right side
        if total_messages > messages_rendered:
            # Calculate scroll position
            max_scroll = total_messages - messages_rendered
            scroll_percentage = 1.0 - (self.action_log_scroll_offset / max_scroll) if max_scroll > 0 else 1.0
            
            # Scrollbar dimensions
            scrollbar_x = sidebar_x + sidebar_width - UIConstants.SCROLLBAR_OFFSET
            scrollbar_top = header_y + UIConstants.HEADER_OFFSET
            scrollbar_height = sidebar_y + sidebar_height - scrollbar_top - 10
            
            # Draw scrollbar track
            pygame.draw.rect(self.screen, (60, 60, 60), 
                           (scrollbar_x, scrollbar_top, UIConstants.SCROLLBAR_WIDTH, scrollbar_height))
            
            # Draw scrollbar thumb
            thumb_height = max(UIConstants.SCROLLBAR_THUMB_MIN, int(scrollbar_height * (messages_rendered / total_messages)))
            thumb_y = scrollbar_top + int((scrollbar_height - thumb_height) * scroll_percentage)
            pygame.draw.rect(self.screen, (150, 150, 150), 
                           (scrollbar_x, thumb_y, UIConstants.SCROLLBAR_WIDTH, thumb_height))
            
            # Draw position text
            position_text = f"{actual_end_index}/{total_messages}"
            pos_text_surface = self.small_font.render(position_text, True, (120, 120, 120))
            pos_rect = pos_text_surface.get_rect(right=sidebar_x + sidebar_width - 15, 
                                                  bottom=sidebar_y + sidebar_height - 5)
            self.screen.blit(pos_text_surface, pos_rect)
    
    def _draw_chat_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """
        Draw Chat tab content with message history and scrolling.
        
        Format: [timestamp] PlayerName: message
        Supports scrolling with mouse wheel to view older messages.
        """
        # Header
        header_y = content_start_y
        header_text = self.font.render("Chat", True, WHITE)
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.screen.blit(header_text, header_rect)
        
        # Draw separator line
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (sidebar_x + 10, header_y + 30),
                        (sidebar_x + sidebar_width - 10, header_y + 30), 2)
        
        # Check if there are any messages
        if len(self.game_state.chat_messages) == 0:
            # Show empty message
            empty_text = self.small_font.render("No messages yet", True, (150, 150, 150))
            empty_rect = empty_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 80))
            self.screen.blit(empty_text, empty_rect)
            
            # Instructions
            hint_text = self.small_font.render("Press ENTER to chat", True, (120, 120, 120))
            hint_rect = hint_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 110))
            self.screen.blit(hint_text, hint_rect)
            return
        
        # Get messages to display (oldest to newest)
        all_messages = self.game_state.chat_messages  # Already in chronological order
        total_messages = len(all_messages)
        
        # Calculate approximate visible messages
        # Use generous estimate for selection - rendering loop will stop when full
        available_height = sidebar_y + sidebar_height - (header_y + UIConstants.HEADER_OFFSET) - UIConstants.BOTTOM_RESERVE
        approx_messages_visible = max(5, available_height // UIConstants.PIXELS_PER_MESSAGE_SELECTION)
        
        # Calculate which messages to show based on scroll offset
        # When scroll_offset = 0: Show newest messages (end of list)
        # When scroll_offset > 0: Scroll back in history
        
        # End index is total minus scroll offset
        end_index = total_messages - self.chat_scroll_offset
        # Start index ensures we don't show more than fits
        start_index = max(0, end_index - approx_messages_visible)
        
        messages_to_show = all_messages[start_index:end_index]
        start_msg_index = start_index
        
        # Draw messages (oldest to newest, top to bottom)
        msg_y = header_y + UIConstants.HEADER_OFFSET
        messages_rendered = 0
        
        for idx, (timestamp, player_id, message) in enumerate(messages_to_show):
            # Check if we're out of space
            if msg_y + 40 > sidebar_y + sidebar_height - UIConstants.BOTTOM_RESERVE:
                break
            
            messages_rendered += 1
            
            # Format: [timestamp] PlayerName: message
            player_color = self.game_state.get_player_color(player_id)
            player_name = f"Player {player_id + 1}"
            
            # Draw timestamp in gray
            time_text = self.small_font.render(f"[{timestamp}]", True, (150, 150, 150))
            self.screen.blit(time_text, (sidebar_x + 10, msg_y))
            
            # Draw player name in their color
            name_text = self.small_font.render(player_name + ":", True, player_color)
            name_x = sidebar_x + 10 + time_text.get_width() + 5
            self.screen.blit(name_text, (name_x, msg_y))
            msg_y += 18
            
            # Draw message (word wrapped)
            max_chars = UIConstants.MESSAGE_MAX_CHARS
            if len(message) > max_chars:
                words = message.split()
                line = ""
                for word in words:
                    test_line = line + " " + word if line else word
                    if len(test_line) > max_chars:
                        # Draw current line
                        msg_text = self.small_font.render(line, True, (200, 200, 200))
                        self.screen.blit(msg_text, (sidebar_x + 15, msg_y))
                        msg_y += 16
                        line = word
                        
                        # Check space again
                        if msg_y + 30 > sidebar_y + sidebar_height - 40:
                            break
                    else:
                        line = test_line
                
                # Draw last line
                if line and msg_y + 20 < sidebar_y + sidebar_height - 40:
                    msg_text = self.small_font.render(line, True, (200, 200, 200))
                    self.screen.blit(msg_text, (sidebar_x + 15, msg_y))
                    msg_y += 16
            else:
                # Short message - draw directly
                msg_text = self.small_font.render(message, True, (200, 200, 200))
                self.screen.blit(msg_text, (sidebar_x + 15, msg_y))
                msg_y += 16
            
            # Add gap between messages
            msg_y += 8
        
        # Calculate actual end index based on what we rendered
        actual_end_index = start_msg_index + messages_rendered
        
        # Draw scroll position indicator on right side
        if total_messages > messages_rendered:
            # Calculate scroll position
            max_scroll = total_messages - messages_rendered
            scroll_percentage = 1.0 - (self.chat_scroll_offset / max_scroll) if max_scroll > 0 else 1.0
            
            # Scrollbar dimensions
            scrollbar_x = sidebar_x + sidebar_width - UIConstants.SCROLLBAR_OFFSET
            scrollbar_top = header_y + UIConstants.HEADER_OFFSET
            scrollbar_height = sidebar_y + sidebar_height - scrollbar_top - 10
            
            # Draw scrollbar track
            pygame.draw.rect(self.screen, (60, 60, 60), 
                           (scrollbar_x, scrollbar_top, UIConstants.SCROLLBAR_WIDTH, scrollbar_height))
            
            # Draw scrollbar thumb
            thumb_height = max(UIConstants.SCROLLBAR_THUMB_MIN, int(scrollbar_height * (messages_rendered / total_messages)))
            thumb_y = scrollbar_top + int((scrollbar_height - thumb_height) * scroll_percentage)
            pygame.draw.rect(self.screen, (150, 150, 150), 
                           (scrollbar_x, thumb_y, UIConstants.SCROLLBAR_WIDTH, thumb_height))
            
            # Draw position text
            position_text = f"{actual_end_index}/{total_messages}"
            pos_text_surface = self.small_font.render(position_text, True, (120, 120, 120))
            pos_rect = pos_text_surface.get_rect(right=sidebar_x + sidebar_width - 15, 
                                                  bottom=sidebar_y + sidebar_height - 5)
            self.screen.blit(pos_text_surface, pos_rect)
    
    def _draw_placeholder_tab_content(self, sidebar_x, sidebar_width, content_start_y, tab_name):
        """Draw placeholder content for tabs that aren't implemented yet."""
        # Title
        title_y = content_start_y
        title_text = self.font.render(tab_name, True, WHITE)
        title_rect = title_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=title_y)
        self.screen.blit(title_text, title_rect)
        
        # Separator
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (sidebar_x + 10, title_y + 30),
                        (sidebar_x + sidebar_width - 10, title_y + 30), 2)
        
        # Placeholder message
        msg_y = title_y + 60
        msg_text = self.small_font.render("Coming Soon", True, (150, 150, 150))
        msg_rect = msg_text.get_rect(center=(sidebar_x + sidebar_width // 2, msg_y))
        self.screen.blit(msg_text, msg_rect)
        
        # Description
        desc_y = msg_y + 30
        desc_text = self.small_font.render("This feature will be", True, (120, 120, 120))
        desc_rect = desc_text.get_rect(center=(sidebar_x + sidebar_width // 2, desc_y))
        self.screen.blit(desc_text, desc_rect)
        
        desc2_y = desc_y + 20
        desc2_text = self.small_font.render("implemented later", True, (120, 120, 120))
        desc2_rect = desc2_text.get_rect(center=(sidebar_x + sidebar_width // 2, desc2_y))
        self.screen.blit(desc2_text, desc2_rect)
    
    def _draw_sidebar_tab_buttons(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height):
        """
        Draw tab buttons on the LEFT SIDE of sidebar (Phase B: Vertical Tab System).
        
        Tabs stick out from the left edge like vertical bookmarks:
        - Technology
        - Heroes  
        - Action Queue
        - Action Log
        - Quests
        - Chat
        
        Each tab is a vertical button with 90-degree rotated text.
        Active tab is highlighted. Clicking a tab makes it active.
        
        These tabs cover the full height of the sidebar, distributed evenly.
        """
        # Tab dimensions
        tab_width = UIConstants.TAB_WIDTH
        num_tabs = len(self.game_state.sidebar_tabs)
        
        # Distribute tabs evenly across sidebar height
        # Adjust padding to ensure all tabs fit with equal height
        padding_top = UIConstants.TAB_PADDING_TOP
        padding_bottom = UIConstants.TAB_PADDING_BOTTOM
        available_height = sidebar_height - padding_top - padding_bottom
        
        # Calculate exact height for each tab (no spacing between tabs)
        exact_tab_height = available_height / num_tabs
        actual_tab_height = int(exact_tab_height)  # Round down for consistent height
        tab_spacing = 0  # No spacing - tabs are adjacent
        
        # Store tab button rects for click detection
        self.sidebar_tab_buttons = {}
        
        # Tab display names
        tab_names = {
            'technology': 'Technology',
            'heroes': 'Heroes',
            'action_queue': 'Action Queue',
            'action_log': 'Action Log',
            'quests': 'Quests',
            'chat': 'Chat'
        }
        
        current_y = sidebar_y + padding_top
        
        for tab_id in self.game_state.sidebar_tabs:
            is_active = (tab_id == self.game_state.active_sidebar_tab)
            
            # Tab button rectangle - STICKS OUT to the LEFT of sidebar
            tab_x = sidebar_x - tab_width  # Left of sidebar
            tab_rect = pygame.Rect(tab_x, current_y, tab_width, actual_tab_height)
            
            # Different colors for active/inactive
            if is_active:
                bg_color = (80, 120, 180)  # Blue for active
                border_color = (120, 160, 220)
            else:
                bg_color = (50, 50, 50)  # Dark gray for inactive
                border_color = (100, 100, 100)
            
            # Draw tab button
            pygame.draw.rect(self.screen, bg_color, tab_rect)
            pygame.draw.rect(self.screen, border_color, tab_rect, 2)
            
            # Draw rotated tab name (90 degrees clockwise - read with head tilted right)
            tab_text = self.small_font.render(tab_names[tab_id], True, WHITE)
            rotated_text = pygame.transform.rotate(tab_text, -90)  # Clockwise rotation
            text_rect = rotated_text.get_rect(center=(tab_x + tab_width // 2, current_y + actual_tab_height // 2))
            self.screen.blit(rotated_text, text_rect)
            
            # Add badge for Action Queue if there are orders
            if tab_id == 'action_queue':
                order_count = len(self.game_state.movement_orders)
                if order_count > 0:
                    # Badge at bottom of tab
                    badge_x = tab_x + tab_width // 2
                    badge_y = current_y + actual_tab_height - 15
                    pygame.draw.circle(self.screen, (200, 50, 50), (badge_x, badge_y), 8)
                    pygame.draw.circle(self.screen, WHITE, (badge_x, badge_y), 8, 2)
                    count_text = self.small_font.render(str(order_count), True, WHITE)
                    count_rect = count_text.get_rect(center=(badge_x, badge_y))
                    self.screen.blit(count_text, count_rect)
            
            # Store for click detection
            self.sidebar_tab_buttons[tab_id] = tab_rect
            
            current_y += actual_tab_height
        
        # Return Y position where content should start (just below sidebar top, since tabs are on left)
        return sidebar_y + 15
    
    def draw_order_sidebar(self):
        """
        Draw sidebar with exclusive tab system (Phase B/C).
        
        Features 5 tabs with mutual exclusion:
        - Technology (placeholder)
        - Heroes (placeholder)
        - Action Queue (movement orders)
        - Action Log (game messages)
        - Quests (placeholder)
        
        Only one tab is active at a time. Clicking a tab switches to it.
        
        Visible during both planning and battle phases.
        """
        # Tab display names
        tab_names = {
            'technology': 'Technology',
            'heroes': 'Heroes',
            'action_queue': 'Action Queue',
            'action_log': 'Action Log',
            'quests': 'Quests',
            'chat': 'Chat'
        }
        
        # Collapsed state - just show toggle button with active tab name
        if not self.game_state.sidebar_expanded:
            # Collapsed tab on right edge
            tab_width = UIConstants.TAB_WIDTH
            tab_height = 150  # Taller to fit rotated text + badge
            tab_x = WINDOW_WIDTH - tab_width
            tab_y = (MAP_HEIGHT - tab_height) // 2  # Center vertically
            
            # Draw tab
            tab_rect = pygame.Rect(tab_x, tab_y, tab_width, tab_height)
            pygame.draw.rect(self.screen, (50, 50, 50), tab_rect)
            pygame.draw.rect(self.screen, (100, 100, 100), tab_rect, 3)
            
            # Rotated text: Show active tab name (90 degrees clockwise)
            active_tab_name = tab_names[self.game_state.active_sidebar_tab]
            text_surface = self.small_font.render(active_tab_name, True, WHITE)
            # Rotate 90 degrees clockwise (text reads top-to-bottom)
            rotated_text = pygame.transform.rotate(text_surface, -90)
            text_rect = rotated_text.get_rect(center=(tab_x + tab_width // 2, tab_y + tab_height // 2 - 10))
            self.screen.blit(rotated_text, text_rect)
            
            # Draw order count badge if Action Queue tab and there are orders (at bottom of tab)
            if self.game_state.active_sidebar_tab == 'action_queue':
                order_count = len(self.game_state.movement_orders)
                if order_count > 0:
                    badge_y = tab_y + tab_height - 20
                    # Small badge circle
                    pygame.draw.circle(self.screen, (200, 50, 50), (tab_x + tab_width // 2, badge_y), 10)
                    pygame.draw.circle(self.screen, WHITE, (tab_x + tab_width // 2, badge_y), 10, 2)
                    
                    # Count number
                    count_text = self.small_font.render(str(order_count), True, WHITE)
                    count_rect = count_text.get_rect(center=(tab_x + tab_width // 2, badge_y))
                    self.screen.blit(count_text, count_rect)
            
            # Store button rect for click detection
            self.sidebar_toggle_button = tab_rect
            return
        
        # Expanded state - show full sidebar with tabs
        # Sidebar dimensions (on the right side, below top panel)
        sidebar_width = UIConstants.SIDEBAR_WIDTH
        sidebar_x = WINDOW_WIDTH - sidebar_width  # No margin - flush to edge
        sidebar_y = TOP_PANEL_HEIGHT  # Start below top panel
        sidebar_height = MAP_HEIGHT  # Full height to bottom panel
        
        # Draw sidebar background
        sidebar_rect = pygame.Rect(sidebar_x, sidebar_y, sidebar_width, sidebar_height)
        pygame.draw.rect(self.screen, (40, 40, 40), sidebar_rect)
        pygame.draw.rect(self.screen, (100, 100, 100), sidebar_rect, 3)
        
        # No collapse button - sidebar is always expanded
        self.sidebar_toggle_button = None
        
        # Draw tab buttons on left side and get content start position
        content_start_y = self._draw_sidebar_tab_buttons(sidebar_x, sidebar_y, sidebar_width, sidebar_height)
        
        # Draw content based on active tab
        active_tab = self.game_state.active_sidebar_tab
        
        if active_tab == 'action_queue':
            self._draw_action_queue_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        elif active_tab == 'technology':
            self._draw_placeholder_tab_content(sidebar_x, sidebar_width, content_start_y, "Technology")
        elif active_tab == 'heroes':
            self._draw_placeholder_tab_content(sidebar_x, sidebar_width, content_start_y, "Heroes")
        elif active_tab == 'action_log':
            self._draw_action_log_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        elif active_tab == 'quests':
            self._draw_placeholder_tab_content(sidebar_x, sidebar_width, content_start_y, "Quests")
        elif active_tab == 'chat':
            self._draw_chat_content(sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y)
        
        # Cancel All button at bottom (full width)
        if len(self.game_state.movement_orders) > 0:
            cancel_all_y = sidebar_y + sidebar_height - 50
            cancel_all_rect = pygame.Rect(sidebar_x + 20, cancel_all_y, sidebar_width - 40, 35)
            pygame.draw.rect(self.screen, (150, 50, 50), cancel_all_rect, border_radius=5)
            cancel_all_text = self.font.render("CANCEL ALL", True, WHITE)
            cancel_all_text_rect = cancel_all_text.get_rect(center=cancel_all_rect.center)
            self.screen.blit(cancel_all_text, cancel_all_text_rect)
            self.cancel_all_button = cancel_all_rect
        else:
            self.cancel_all_button = None
    
    def draw_territory_hover_tooltip(self, mouse_pos):
        """Draw comprehensive tooltip when hovering over a territory (Phase 2: Using helper)"""
        if not self.show_tooltip_territory:
            return
        
        territory = self.show_tooltip_territory
        
        # Gather data
        owner = self.game_state.territory_owners.get(territory, -1)
        armies = self.game_state.armies.get(territory, 0)
        
        # Calculate combat power (armies + Keep bonus)
        keep_bonus = 0
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
        
        # Territory name
        lines.append(("normal", territory, BLACK))
        
        # Owner
        if owner == -1:
            lines.append(("normal", "Owner: Neutral", GRAY))
        else:
            owner_color = self.game_state.get_player_color(owner)
            lines.append(("normal", f"Owner: Player {owner + 1}", owner_color))
        
        # Combat Power
        if keep_bonus > 0:
            lines.append(("normal", f"Combat Power: {armies} + {keep_bonus} (Keep)", (150, 50, 50)))
        else:
            lines.append(("normal", f"Combat Power: {armies}", BLACK))
        
        # Unit composition breakdown
        if armies > 0:
            composition = self.game_state.get_unit_composition(territory)
            if composition:
                for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']:
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
        if not button_data:
            return
        
        button_type, button_key = button_data
        lines = []
        
        if button_type == 'training' or button_type == 'map_training':
            # Training button tooltip (UI or map icon)
            unit_type = button_key
            unit_info = self.game_state.UNIT_TYPES[unit_type]
            
            # Get counter name in plural form
            counters_name = unit_info['counters']
            if counters_name == 'Cavalry':
                counters_plural = 'Cavalry'
            else:
                counters_plural = counters_name + 's'
            
            # Keyboard shortcut mapping
            keyboard_shortcuts = {
                'Swordsman': 'S',
                'Archer': 'A',
                'Pikeman': 'P',
                'Cavalry': 'C'
            }
            shortcut = keyboard_shortcuts.get(unit_type, '')
            
            lines = [
                f"Train {unit_type}",
                f"Cost: {unit_info['cost']} Gold",
                f"Counters {counters_plural}",
                "Takes 1 turn to complete",
                f"Shortcut: {shortcut}" if shortcut else ""
            ]
            
            # Remove empty string if no shortcut
            lines = [line for line in lines if line]
            
        elif button_type == 'building' or button_type == 'map_building':
            # Building button tooltip (UI or map icon)
            building_name = button_key
            building_info = self.game_state.building_types[building_name]
            
            # Build description based on effect
            effect = building_info['effect']
            value = building_info['value']
            if effect == 'income':
                description = f"Generates +{value} Gold/turn"
            elif effect == 'defense':
                description = "Provides defense bonus"
            elif effect == 'multiplier':
                description = f"Multiplies territory income x{value}"
            elif effect == 'recruitment':
                description = "Train military units"
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
                'Square': 'Q'
            }
            shortcut = keyboard_shortcuts.get(building_name, '')
            
            lines = [
                f"Construct {building_name}",
                f"Cost: {building_info['cost']} Gold",
                description,
                f"Takes {build_time} turn{'s' if build_time > 1 else ''} to complete",
                f"Shortcut: {shortcut}" if shortcut else ""
            ]
            
            # Remove empty string if no shortcut
            lines = [line for line in lines if line]
            
        elif button_type == 'plot':
            # Simple plot tooltip
            lines = ["Available building plot"]
        
        if not lines:
            return
        
        # Draw using helper (Phase 2)
        # Convert lines to (text, WHITE) tuples for white text
        formatted_lines = [(line, WHITE) for line in lines]
        tooltip_pos = (mouse_pos[0] + 15, mouse_pos[1] + 15)
        self.draw_tooltip_box(tooltip_pos, formatted_lines,
                             bg_color=(50, 50, 50),
                             border_color=(200, 200, 200),
                             padding=7, line_spacing=0)
    
    def clear_button_tooltip(self):
        """Clear button tooltip state (call after actions)"""
        self.hover_target_button = None
        self.show_tooltip_button = None
        self.hover_start_time_button = None
    
    def draw_army_hover_tooltip(self, mouse_pos, territory):
        """Draw army-specific tooltip when hovering over an army circle"""
        if not territory:
            return
        
        # Gather army data
        owner = self.game_state.territory_owners.get(territory, -1)
        total_armies = self.game_state.armies.get(territory, 0)
        unmoved_armies = self.game_state.armies_unmoved.get(territory, 0)
        
        # Build tooltip lines
        lines = []
        
        # Line 1: Territory name
        lines.append(("normal", f"Army in {territory}", BLACK))
        
        # Line 2: Owner
        if owner >= 0:
            owner_color = self.game_state.get_player_color(owner)
            lines.append(("normal", f"Owner: Player {owner + 1}", owner_color))
        
        # Line 3: Total forces
        lines.append(("normal", f"Total Forces: {total_armies}", BLACK))
        
        # Line 3.5: Unit composition breakdown (if armies exist)
        if total_armies > 0:
            composition = self.game_state.get_unit_composition(territory)
            if composition:
                # Sort by unit type for consistent display
                for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']:
                    if unit_type in composition and composition[unit_type] > 0:
                        count = composition[unit_type]
                        # Use Battalion terminology
                        battalion_name = f"{unit_type} Battalion" if count == 1 else f"{unit_type} Battalions"
                        lines.append(("small", f"  {battalion_name}: {count}", (80, 80, 80)))
        
        # Line 4: Available for commands (only for own armies)
        if owner == self.game_state.current_player:
            lines.append(("normal", f"Available for Commands: {unmoved_armies}", (0, 150, 0)))
        
        # Line 5: Check for merge orders
        for order in self.game_state.movement_orders:
            if order.from_territory == territory:
                # This army has a move order
                dest_owner = self.game_state.territory_owners.get(order.to_territory, -1)
                if dest_owner == order.player:
                    # Merging with friendly territory
                    lines.append(("normal", f"â†’ Merging with {order.to_territory}", (0, 180, 180)))
                else:
                    # Attacking
                    lines.append(("normal", f"â†’ Attacking {order.to_territory}", (180, 0, 0)))
                break
        
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
        
        # Clear any stale UI buttons that might interfere
        self.train_buttons = {}
        self.army_composition_buttons = []
        self.select_all_button = None
        self.deselect_all_button = None
        
        # Get territory info
        owner = self.game_state.territory_owners.get(territory, -1)
        armies = self.game_state.armies.get(territory, 0)
        
        # Calculate income for this territory
        base_income = map_data.get_territory_income(territory)
        building_income = 0
        if territory in self.game_state.buildings:
            for plot_index, building_type in self.game_state.buildings[territory].items():
                if building_type == 'Farm':
                    building_income += 10
                elif building_type == 'Mine':
                    building_income += 15
        
        total_income = base_income + building_income
        
        # Get actual plot count for this territory
        plot_count = len(self.scaled_plots.get(territory, []))
        
        # Panel starting position (left side)
        panel_x = 350
        panel_y = BOTTOM_UI_Y + 15
        
        # Draw title
        title_text = self.large_font.render(territory, True, BLACK)
        self.screen.blit(title_text, (panel_x, panel_y))
        panel_y += 35
        
        # Draw owner
        if owner == -1:
            owner_text = self.font.render("Owner: Neutral", True, GRAY)
        else:
            owner_color = self.game_state.get_player_color(owner)
            owner_text = self.font.render(f"Owner: Player {owner + 1}", True, owner_color)
        self.screen.blit(owner_text, (panel_x, panel_y))
        panel_y += 28
        
        # Draw income
        income_text = self.small_font.render(f"Income: +{total_income}G/turn", True, (218, 165, 32))
        self.screen.blit(income_text, (panel_x, panel_y))
        
        # Draw first vertical dividing line (between basic info and building plots)
        divider_x = panel_x + 220
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (divider_x, BOTTOM_UI_Y + 10), 
                        (divider_x, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - 10), 3)
        
        # Draw building plots on the right side of divider
        if owner != -1 and plot_count > 0:  # Only show plots for owned territories with plots
            plots_x = divider_x + 20
            plots_y = BOTTOM_UI_Y + 15
            
            plots_title = self.font.render("Building Plots:", True, BLACK)
            self.screen.blit(plots_title, (plots_x, plots_y))
            plots_y += 30
            
            # Draw plots in a grid
            plot_size = 50
            plot_spacing = 10
            plots_per_row = 6
            
            # Clear plot button storage
            if not hasattr(self, 'territory_info_plot_buttons'):
                self.territory_info_plot_buttons = []
            self.territory_info_plot_buttons = []
            
            for plot_index in range(plot_count):  # Use actual plot count
                row = plot_index // plots_per_row
                col = plot_index % plots_per_row
                
                plot_x = plots_x + col * (plot_size + plot_spacing)
                plot_y = plots_y + row * (plot_size + plot_spacing)
                
                plot_rect = pygame.Rect(plot_x, plot_y, plot_size, plot_size)
                
                # Check plot state
                building = None
                under_construction_data = None
                
                if territory in self.game_state.buildings:
                    building = self.game_state.buildings[territory].get(plot_index)
                
                if territory in self.game_state.under_construction:
                    under_construction_data = self.game_state.under_construction[territory].get(plot_index)
                
                # Draw plot based on state
                if building:
                    # Completed building - gray with building type
                    pygame.draw.rect(self.screen, (150, 150, 150), plot_rect)
                    
                    # Highlight if this plot is selected (either as plot or as Barracks)
                    is_selected_plot = self.selected_plot and self.selected_plot == (territory, plot_index)
                    is_selected_barracks = (self.selected_barracks and 
                                           self.selected_barracks == (territory, plot_index) and
                                           building == 'Barracks')
                    
                    if is_selected_plot or is_selected_barracks:
                        pygame.draw.rect(self.screen, (255, 215, 0), plot_rect, 4)  # Gold highlight
                    else:
                        pygame.draw.rect(self.screen, BLACK, plot_rect, 2)
                    
                    # Building icon/text
                    if building == 'Farm':
                        icon = self.small_font.render("F", True, (50, 150, 50))
                    elif building == 'Mine':
                        icon = self.small_font.render("M", True, (100, 100, 150))
                    elif building == 'Keep':
                        icon = self.small_font.render("K", True, (150, 50, 50))
                    else:
                        icon = self.small_font.render(building[0], True, BLACK)
                    
                    icon_rect = icon.get_rect(center=plot_rect.center)
                    self.screen.blit(icon, icon_rect)
                    
                elif under_construction_data:
                    # Under construction - yellow
                    # under_construction_data is a tuple: (building_type, turns_remaining)
                    building_type, turns_remaining = under_construction_data
                    
                    pygame.draw.rect(self.screen, (200, 200, 100), plot_rect)
                    
                    # Highlight if this plot is selected
                    if self.selected_plot and self.selected_plot == (territory, plot_index):
                        pygame.draw.rect(self.screen, (255, 215, 0), plot_rect, 4)  # Gold highlight
                    else:
                        pygame.draw.rect(self.screen, BLACK, plot_rect, 2)
                    
                    # Progress text - show turns remaining
                    progress_text = self.small_font.render(f"{turns_remaining}", True, BLACK)
                    progress_rect = progress_text.get_rect(center=plot_rect.center)
                    self.screen.blit(progress_text, progress_rect)
                    
                else:
                    # Empty plot
                    # Check if we can build on this territory this turn
                    can_build = (owner == self.game_state.current_player and 
                                territory not in self.game_state.buildings_started_this_turn)
                    
                    # Color: Brighter green if can build, light gray otherwise
                    if can_build:
                        pygame.draw.rect(self.screen, (180, 240, 180), plot_rect)  # Bright light green
                    else:
                        pygame.draw.rect(self.screen, (220, 220, 220), plot_rect)  # Light gray
                    
                    # Highlight if this plot is selected
                    if self.selected_plot and self.selected_plot == (territory, plot_index):
                        pygame.draw.rect(self.screen, (255, 215, 0), plot_rect, 4)  # Gold highlight
                    else:
                        pygame.draw.rect(self.screen, (100, 100, 100), plot_rect, 2)
                    
                    # Plus sign (only show for current player's territories)
                    if owner == self.game_state.current_player:
                        plus_text = self.font.render("+", True, (100, 100, 100))
                        plus_rect = plus_text.get_rect(center=plot_rect.center)
                        self.screen.blit(plus_text, plus_rect)
                
                # Store plot button for click detection
                self.territory_info_plot_buttons.append((plot_rect, territory, plot_index))
        
        # Draw second vertical dividing line (between building plots and army info)
        divider_x2 = divider_x + 400  # Position after building plots
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (divider_x2, BOTTOM_UI_Y + 10), 
                        (divider_x2, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - 10), 3)
        
        # Draw army info section on the right
        army_info_x = divider_x2 + 20
        army_info_y = BOTTOM_UI_Y + 15
        
        # Section title
        army_title = self.font.render("Forces", True, BLACK)
        self.screen.blit(army_title, (army_info_x, army_info_y))
        army_info_y += 30
        
        # Total armies
        armies_text = self.small_font.render(f"Total: {armies}", True, BLACK)
        self.screen.blit(armies_text, (army_info_x, army_info_y))
        army_info_y += 22
        
        # Unit composition breakdown (if armies exist)
        if armies > 0:
            composition = self.game_state.get_unit_composition(territory)
            if composition:
                for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']:
                    if unit_type in composition and composition[unit_type] > 0:
                        count = composition[unit_type]
                        # Use Battalion terminology
                        battalion_name = f"{unit_type} Battalion" if count == 1 else f"{unit_type} Battalions"
                        comp_text = self.small_font.render(f"  {battalion_name}: {count}", True, (80, 80, 80))
                        self.screen.blit(comp_text, (army_info_x, army_info_y))
                        army_info_y += 18
        
        army_info_y += 5  # Small spacing
        
        # Draw army limit indicator
        if armies >= self.game_state.MAX_ARMIES_PER_TERRITORY:
            limit_text = self.small_font.render(f"Army Limit: {armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", True, (180, 0, 0))
        else:
            limit_text = self.small_font.render(f"Army Limit: {armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", True, (100, 100, 100))
        self.screen.blit(limit_text, (army_info_x, army_info_y))
        
        # Track button hover for plot tooltips (will be drawn with delay in main loop)
        if owner == self.game_state.current_player and hasattr(self, 'territory_info_plot_buttons'):
            mouse_pos = pygame.mouse.get_pos()
            current_hover = None
            for plot_rect, terr, plot_idx in self.territory_info_plot_buttons:
                if plot_rect.collidepoint(mouse_pos):
                    # Check what's on this plot
                    existing_building = None
                    if terr in self.game_state.buildings:
                        existing_building = self.game_state.buildings[terr].get(plot_idx)
                    
                    # Only track hover for empty plots (where you can build)
                    if not existing_building:
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
        Width: ~300px
        """
        ui_x = 150  # Starting X position
        ui_y = BOTTOM_UI_Y + 15
        
        if self.game_state.phase == 'playing':
            # Current player
            player_color = self.game_state.get_player_color(self.game_state.current_player)
            player_text = self.font.render(f"Player {self.game_state.current_player + 1}", True, player_color)
            self.screen.blit(player_text, (ui_x, ui_y))
            ui_y += 28
            
            # Gold and income
            current_gold = self.game_state.player_gold[self.game_state.current_player]
            current_income = self.game_state.calculate_player_income(self.game_state.current_player)
            gold_text = self.small_font.render(f"Gold: {current_gold}G (+{current_income}/turn)", True, (218, 165, 32))
            self.screen.blit(gold_text, (ui_x, ui_y))
            ui_y += 24
            
            # End Turn button
            end_turn_rect = pygame.Rect(ui_x, ui_y, 120, 40)
            self.draw_feedback_button(end_turn_rect, (100, 150, 100),
                                      'bottom_button', 'end_turn',
                                      text="End Turn")
            self.end_turn_button = end_turn_rect
            
            # Testing mode indicator
            if self.game_state.testing_mode:
                testing_text = self.small_font.render("â—Ž TESTING MODE: Can control all players", True, (255, 100, 0))
                self.screen.blit(testing_text, (ui_x, ui_y + 95))
        
        # Vertical separator line
        separator_x = 310
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (separator_x, BOTTOM_UI_Y + 10), 
                        (separator_x, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - 10), 
                        3)
    
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
        
        # Panel starting position
        panel_x = 350
        panel_y = BOTTOM_UI_Y + 15
        
        # Header
        title_text = self.large_font.render(f"Selected Army", True, (0, 150, 0))
        self.screen.blit(title_text, (panel_x, panel_y))
        panel_y += UI_SECTION_SPACING
        
        # Territory name
        territory_text = self.font.render(f"Territory: {selected_territory}", True, BLACK)
        self.screen.blit(territory_text, (panel_x, panel_y))
        panel_y += UI_LINE_SPACING
        
        # Army count breakdown
        unmoved = self.game_state.armies_unmoved.get(selected_territory, 0)
        moved = self.game_state.armies_moved.get(selected_territory, 0)
        total = unmoved + moved
        
        # Total armies
        total_text = self.font.render(f"Total Armies: {total}", True, BLACK)
        self.screen.blit(total_text, (panel_x, panel_y))
        panel_y += 28
        
        # Army limit indicator
        limit_color = (180, 0, 0) if total >= self.game_state.MAX_ARMIES_PER_TERRITORY else (100, 100, 100)
        limit_text = self.small_font.render(f"Army Limit: {total}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", True, limit_color)
        self.screen.blit(limit_text, (panel_x + 10, panel_y))
        panel_y += 24
        
        if unmoved > 0:
            # Ready to move (green)
            ready_text = self.small_font.render(f"• {unmoved} ready to move", True, (0, 150, 0))
            self.screen.blit(ready_text, (panel_x + 10, panel_y))
            panel_y += UI_LINE_SPACING_SMALL
            
            if moved > 0:
                # Already moved (gray)
                moved_text = self.small_font.render(f"• {moved} already moved this turn", True, (120, 120, 120))
                self.screen.blit(moved_text, (panel_x + 10, panel_y))
                panel_y += UI_LINE_SPACING_SMALL
        else:
            # All moved (red warning)
            all_moved_text = self.small_font.render(f"• All {moved} armies already moved", True, (180, 0, 0))
            self.screen.blit(all_moved_text, (panel_x + 10, panel_y))
            panel_y += UI_LINE_SPACING_SMALL
        
        panel_y += 10
        
        # Instructions
        hint_text = self.small_font.render("Right-click adjacent territory to move", True, (100, 100, 100))
        self.screen.blit(hint_text, (panel_x, panel_y))
        panel_y += 20
        
        # Deselect hint
        deselect_text = self.small_font.render("Click elsewhere to deselect", True, (100, 100, 100))
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
                instruction = self.font.render("Click on a battlefield to resolve battle", True, BLACK)
                instruction_rect = instruction.get_rect(center=(WINDOW_WIDTH // 2, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT // 2))
                self.screen.blit(instruction, instruction_rect)
            self.train_button = None
            return True  # Handled
        
        # Default instructions when nothing selected
        elif self.game_state.phase != 'playing' or (not self.selected_plot and not self.selected_barracks and not self.game_state.selected_army):
            if self.game_state.phase == 'playing':
                instruction = self.font.render("Click a building plot or Barracks to interact", True, GRAY)
            elif self.game_state.phase == 'setup':
                chosen = self.game_state.territories_chosen[self.game_state.current_player]
                max_territories = self.game_state.max_starting_territories
                instruction = self.large_font.render(f"SETUP: Claim {chosen}/{max_territories} territories", True, BLACK)
            else:
                instruction = self.font.render("", True, BLACK)
            
            instruction_rect = instruction.get_rect(center=(WINDOW_WIDTH // 2, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT // 2))
            self.screen.blit(instruction, instruction_rect)
            self.train_button = None
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
        
        # Clear old building buttons
        self.building_buttons = {}
        self.demolish_button = None
        self.cancel_button = None
        
        # Start building UI
        build_ui_x = 400
        build_ui_y = BOTTOM_UI_Y + 15
        
        # Plot title
        plot_title = self.font.render(f"{territory} - Plot {plot_index + 1}", True, BLACK)
        self.screen.blit(plot_title, (build_ui_x, build_ui_y))
        build_ui_y += 30
        
        if building:
            # Show existing building info
            building_info = self.game_state.building_types[building]
            
            building_text = self.small_font.render(f"{building} ({building_info['letter']})", True, BLUE)
            self.screen.blit(building_text, (build_ui_x, build_ui_y))
            build_ui_y += UI_LINE_SPACING_SMALL
            
            # Show effect
            effect = building_info['effect']
            value = building_info['value']
            
            if effect == 'income':
                effect_text = self.small_font.render(f"+{value} gold/turn", True, GREEN)
            elif effect == 'defense':
                effect_text = self.small_font.render(f"+{value} defense", True, BLUE)
            elif effect == 'multiplier':
                effect_text = self.small_font.render(f"Territory income x{value}", True, GREEN)
            elif effect == 'recruitment':
                effect_text = self.small_font.render("Train military units", True, BLUE)
            else:
                effect_text = self.small_font.render(str(effect), True, BLACK)
            
            self.screen.blit(effect_text, (build_ui_x, build_ui_y))
            build_ui_y += UI_LINE_SPACING_SMALL
            
            build_ui_y += UI_LINE_SPACING_SMALL
            
            # Demolish button
            demolish_rect = pygame.Rect(build_ui_x, build_ui_y, 100, 30)
            self.draw_feedback_button(demolish_rect, (180, 50, 50),
                                      'demolish', 'building',
                                      text="Demolish", font=self.small_font)
            self.demolish_button = demolish_rect
            
        elif under_construction:
            # Show construction info
            building_type, turns_remaining = under_construction
            building_info = self.game_state.building_types[building_type]
            
            construct_text = self.small_font.render(f"Building: {building_type} ({building_info['letter']})", True, (200, 150, 0))
            self.screen.blit(construct_text, (build_ui_x, build_ui_y))
            build_ui_y += UI_LINE_SPACING_SMALL
            
            turns_text = self.small_font.render(f"Turns remaining: {turns_remaining}", True, BLACK)
            self.screen.blit(turns_text, (build_ui_x, build_ui_y))
            build_ui_y += UI_LINE_SPACING_SMALL
            
            build_ui_y += UI_LINE_SPACING_SMALL
            
            # Cancel button
            cancel_rect = pygame.Rect(build_ui_x, build_ui_y, 100, 30)
            self.draw_feedback_button(cancel_rect, (180, 50, 50),
                                      'cancel', 'construction',
                                      text="Cancel", font=self.small_font)
            self.cancel_button = cancel_rect
            
        else:
            # Empty plot - show building options
            # Check if can build this turn
            can_build = territory not in self.game_state.buildings_started_this_turn
            
            if not can_build:
                limit_text = self.small_font.render("Building limit reached this turn", True, (180, 0, 0))
                self.screen.blit(limit_text, (build_ui_x, build_ui_y))
                build_ui_y += UI_LINE_SPACING_SMALL
            
            current_gold = self.game_state.player_gold[self.game_state.current_player]
            
            # Building options - arranged horizontally
            button_x = build_ui_x  # Start position for horizontal layout
            for i, (building_name, info) in enumerate(self.game_state.building_types.items()):
                cost = info['cost']
                letter = info['letter']
                can_afford = current_gold >= cost
                
                # Check Keep restriction (only one Keep per territory)
                can_build_this_building = True
                if building_name == 'Keep':
                    # Check if already has a Keep (completed or under construction)
                    if self.game_state.has_fortress(territory):
                        can_build_this_building = False
                    # Check if Keep is under construction
                    if territory in self.game_state.under_construction:
                        for plot_idx, (bldg_type, _) in self.game_state.under_construction[territory].items():
                            if bldg_type == 'Keep':
                                can_build_this_building = False
                                break
                
                # Button color - consider affordability, building limit, AND Keep restriction
                if can_build and can_afford and can_build_this_building:
                    button_color = (100, 200, 100)  # Green
                else:
                    button_color = (200, 100, 100)  # Red
                
                button_rect = pygame.Rect(button_x, build_ui_y, BUTTON_SIZE_SQUARE, BUTTON_SIZE_SQUARE)
                
                self.draw_feedback_button(button_rect, button_color,
                                          'building', building_name,
                                          text=letter, font=self.font)
                
                # Cost text below button
                cost_text = self.small_font.render(f"{building_name}: {cost}G", True, BLACK)
                self.screen.blit(cost_text, (button_x, build_ui_y + BUTTON_SIZE_SQUARE + 5))
                
                self.building_buttons[building_name] = button_rect
                button_x += BUTTON_SIZE_SQUARE + 30  # Move right for next button (extra space for text)
    
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
        pygame.draw.rect(self.screen, (220, 220, 220), bottom_rect)
        pygame.draw.line(self.screen, BLACK, (0, BOTTOM_UI_Y), (WINDOW_WIDTH, BOTTOM_UI_Y), 2)
        
        # Always draw player info section (left side)
        self._draw_player_info_section()
        
        # Show army composition UI if enabled (Phase 3)
        if self.show_army_composition and self.army_composition_territory:
            # Clear any stale UI buttons
            self.territory_info_plot_buttons = []
            self.train_buttons = {}
            self.queue_cancel_buttons = []
            self.demolish_barracks_button = None
            self.draw_army_composition_ui()
            return
        
        # Show army info if army is selected
        if self.game_state.selected_army and not self.selected_plot and not self.selected_barracks:
            self._draw_army_info_section()
            return
        
        # Show territory info if territory clicked (but no plot selected)
        if self.selected_territory_info and not self.selected_plot:
            self.draw_territory_info_panel()
            return
        
        # Show instruction messages (battle/setup/default)
        if self._draw_instruction_message():
            return  # Instruction was shown, we're done
        
        # Training UI when Barracks selected
        if self.selected_barracks:
            self.draw_training_ui()
            return
        
        # Building UI when plot selected
        if self.selected_plot:
            self._draw_building_ui_section()
            return
    def draw_training_ui(self):
        """Draw training interface when Barracks is selected"""
        territory, barracks_plot_index = self.selected_barracks
        
        # Clear any stale army composition buttons that might interfere
        self.army_composition_buttons = []
        self.select_all_button = None
        self.deselect_all_button = None
        
        # Panel starting position (center of bottom UI)
        panel_x = WINDOW_WIDTH // 2 - 300
        panel_y = BOTTOM_UI_Y + 15
        
        # Draw title
        title_text = self.large_font.render("Barracks", True, BLACK)
        self.screen.blit(title_text, (panel_x, panel_y))
        panel_y += 35
        
        # Draw current gold and income
        current_gold = self.game_state.player_gold[self.game_state.current_player]
        current_income = self.game_state.calculate_player_income(self.game_state.current_player)
        gold_text = self.small_font.render(f"Gold: {current_gold}G (+{current_income}/turn)", True, (218, 165, 32))
        self.screen.blit(gold_text, (panel_x, panel_y))
        panel_y += 28
        
        # Training buttons - one for each unit type (SIMPLIFIED - letters only)
        button_y = panel_y
        button_width = BUTTON_SIZE_SQUARE
        button_height = BUTTON_SIZE_SQUARE
        button_spacing = BUTTON_SPACING
        button_x = panel_x
        
        # Unit type colors (for button backgrounds)
        unit_colors = {
            'Swordsman': (100, 100, 150),  # Blue-gray
            'Archer': (100, 150, 100),     # Green
            'Pikeman': (120, 90, 70),      # Brown
            'Cavalry': (180, 140, 60)      # Gold
        }
        
        # Check army limit
        current_armies = self.game_state.armies.get(territory, 0)
        at_army_limit = current_armies >= self.game_state.MAX_ARMIES_PER_TERRITORY
        
        # Get current queue
        queue_count = 0
        if (territory in self.game_state.training_queue and 
            barracks_plot_index in self.game_state.training_queue[territory]):
            queue_count = len(self.game_state.training_queue[territory][barracks_plot_index])
        
        can_queue = queue_count < 5
        
        # Store training buttons for click detection
        self.train_buttons = {}
        
        # Draw 4 training buttons (one for each unit type)
        for unit_type in ['Swordsman', 'Archer', 'Pikeman', 'Cavalry']:
            unit_info = self.game_state.UNIT_TYPES[unit_type]
            unit_cost = unit_info['cost']
            unit_letter = unit_info['letter']
            
            can_afford = current_gold >= unit_cost
            
            # Determine button color
            if can_afford and can_queue and not at_army_limit:
                button_color = unit_colors[unit_type]  # Type-specific color
            else:
                button_color = (200, 100, 100)  # Red when disabled (consistent with buildings)
            
            # Draw button using helper (Phase 1D) with hover/click feedback (Phase 2)
            train_button_rect = pygame.Rect(button_x, button_y, button_width, button_height)
            self.draw_letter_button(train_button_rect, unit_letter, button_color, letter_color=WHITE,
                                   button_type='training', button_id=unit_type)
            
            # Store button for click detection
            self.train_buttons[unit_type] = train_button_rect
            
            # Move to next button position
            button_x += button_width + button_spacing
        
        # Move panel_y down past the buttons
        panel_y += button_height + 15
        if at_army_limit:
            status_text = self.small_font.render(f"ARMY LIMIT ({current_armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY})", True, (180, 0, 0))
        elif not can_afford:
            status_text = self.small_font.render("Not enough gold", True, (150, 0, 0))
        elif not can_queue:
            status_text = self.small_font.render("Queue full (5/5)", True, (150, 0, 0))
        else:
            status_text = self.small_font.render(f"Queue: {queue_count}/5 | Armies: {current_armies}/{self.game_state.MAX_ARMIES_PER_TERRITORY}", True, (0, 150, 0))
        self.screen.blit(status_text, (panel_x, panel_y))
        panel_y += UI_LINE_SPACING_SMALL
        
        # Draw first vertical divider line (between training controls and queue)
        divider_x = panel_x + 480
        pygame.draw.line(self.screen, (100, 100, 100),
                        (divider_x, BOTTOM_UI_Y + 10),
                        (divider_x, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - 10), 3)
        
        # Draw training queue on the right
        queue_x = divider_x + 20
        queue_y = BOTTOM_UI_Y + 15
        
        queue_title = self.font.render("Training Queue:", True, BLACK)
        self.screen.blit(queue_title, (queue_x, queue_y))
        queue_y += 30
        
        # Initialize queue cancel buttons
        if not hasattr(self, 'queue_cancel_buttons'):
            self.queue_cancel_buttons = []
        self.queue_cancel_buttons = []
        
        # Display queue items
        if (territory in self.game_state.training_queue and 
            barracks_plot_index in self.game_state.training_queue[territory]):
            queue = self.game_state.training_queue[territory][barracks_plot_index]
            
            for i, (unit_type, turns_remaining) in enumerate(queue):
                # Queue item background
                item_rect = pygame.Rect(queue_x, queue_y, 280, 30)
                pygame.draw.rect(self.screen, (220, 220, 220), item_rect)
                pygame.draw.rect(self.screen, BLACK, item_rect, 1)
                
                # Unit info
                if i == 0:
                    # First in queue - currently training
                    if turns_remaining == 0:
                        # Training paused due to army limit
                        unit_text = self.small_font.render(f"{unit_type} (Army Limit Reached)", True, (180, 0, 0))
                    else:
                        unit_text = self.small_font.render(f"{unit_type} (training... {turns_remaining} turn)", True, (0, 100, 0))
                else:
                    # Waiting in queue
                    unit_text = self.small_font.render(f"{unit_type} (waiting)", True, GRAY)
                self.screen.blit(unit_text, (queue_x + 5, queue_y + 7))
                
                # Cancel button
                cancel_rect = pygame.Rect(queue_x + 250, queue_y + 5, 20, 20)
                
                # Base color
                button_color = (200, 100, 100)
                # Check hover
                is_hovering = cancel_rect.collidepoint(self.mouse_pos)
                # Check click
                is_clicking = (self.clicked_element and 
                              self.clicked_element[0] == 'queue_cancel' and 
                              self.clicked_element[1] == i)
                # Apply feedback
                if is_clicking:
                    button_color = self.brighten_color(button_color, 0.4)
                elif is_hovering:
                    button_color = self.lighten_color(button_color, 0.2)
                
                pygame.draw.rect(self.screen, button_color, cancel_rect)
                pygame.draw.rect(self.screen, BLACK, cancel_rect, 1)
                cancel_text = self.small_font.render("X", True, WHITE)
                cancel_text_rect = cancel_text.get_rect(center=cancel_rect.center)
                self.screen.blit(cancel_text, cancel_text_rect)
                
                # Store for click detection
                self.queue_cancel_buttons.append((cancel_rect, i))
                
                queue_y += 35
        else:
            empty_text = self.small_font.render("No units in queue", True, GRAY)
            self.screen.blit(empty_text, (queue_x, queue_y))
        
        # Draw second vertical divider line (between queue and tips)
        divider_x2 = queue_x + 320
        pygame.draw.line(self.screen, (100, 100, 100),
                        (divider_x2, BOTTOM_UI_Y + 10),
                        (divider_x2, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - 10), 3)
        
        # Draw tips and controls section on the right
        tips_x = divider_x2 + 20
        tips_y = BOTTOM_UI_Y + 15
        
        # Section title
        tips_title = self.font.render("Controls", True, BLACK)
        self.screen.blit(tips_title, (tips_x, tips_y))
        tips_y += 35
        
        # Keyboard shortcut hint
        shortcut_text = self.small_font.render("Keyboard Shortcuts:", True, BLACK)
        self.screen.blit(shortcut_text, (tips_x, tips_y))
        tips_y += 20
        
        shortcut_hint = self.small_font.render("S = Swordsman", True, (100, 100, 100))
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 18
        
        shortcut_hint = self.small_font.render("A = Archer", True, (100, 100, 100))
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 18
        
        shortcut_hint = self.small_font.render("P = Pikeman", True, (100, 100, 100))
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 18
        
        shortcut_hint = self.small_font.render("C = Cavalry", True, (100, 100, 100))
        self.screen.blit(shortcut_hint, (tips_x, tips_y))
        tips_y += 30
        
        # Demolish button
        demolish_rect = pygame.Rect(tips_x, tips_y, 180, 30)
        self.draw_feedback_button(demolish_rect, (150, 100, 100),
                                  'demolish', 'barracks',
                                  text="Demolish Barracks (50%)",
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
    
    def draw_army_composition_ui(self):
        """Draw army composition UI for individual army control (Phase 3)"""
        territory = self.army_composition_territory
        if not territory:
            return
        
        # Ensure army units exist for this territory
        units = self.game_state.ensure_army_units_exist(territory)
        
        # Count status
        ready_count = sum(1 for u in units if u['status'] == 'ready')
        moved_count = sum(1 for u in units if u['status'] == 'moved')
        ordered_count = sum(1 for u in units if u['status'] == 'ordered')
        total = len(units)
        
        # MIDDLE SECTION: Army composition info and controls
        middle_x = 350
        panel_y = BOTTOM_UI_Y + 15
        
        # Draw title
        title_text = self.large_font.render(f"Army Composition: {territory}", True, (0, 150, 0))
        self.screen.blit(title_text, (middle_x, panel_y))
        panel_y += UI_SECTION_SPACING
        
        # Total and status summary
        summary_text = self.font.render(f"Total: {total} armies", True, BLACK)
        self.screen.blit(summary_text, (middle_x, panel_y))
        panel_y += UI_LINE_SPACING_SMALL
        
        status_text = self.small_font.render(
            f"({ready_count} ready, {moved_count} moved, {ordered_count} ordered)", 
            True, (100, 100, 100)
        )
        self.screen.blit(status_text, (middle_x, panel_y))
        panel_y += UI_LINE_SPACING
        
        # Selection count
        if self.selected_army_units:
            selected_text = self.small_font.render(
                f"Selected: {len(self.selected_army_units)} armies", 
                True, (0, 120, 180)
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
        
        # Select All button
        select_all_rect = pygame.Rect(middle_x, button_y, 110, 25)
        
        # Base color
        button_color = (100, 150, 200)
        # Check hover
        is_hovering = select_all_rect.collidepoint(self.mouse_pos)
        # Check click
        is_clicking = (self.clicked_element and 
                      self.clicked_element[0] == 'army_comp' and 
                      self.clicked_element[1] == 'select_all')
        # Apply feedback
        if is_clicking:
            button_color = self.brighten_color(button_color, 0.4)
        elif is_hovering:
            button_color = self.lighten_color(button_color, 0.2)
        
        pygame.draw.rect(self.screen, button_color, select_all_rect)
        pygame.draw.rect(self.screen, BLACK, select_all_rect, 2)
        select_all_text = self.small_font.render("Select All", True, WHITE)
        text_rect = select_all_text.get_rect(center=select_all_rect.center)
        self.screen.blit(select_all_text, text_rect)
        self.select_all_button = select_all_rect
        
        # Deselect All button (next to Select All)
        deselect_all_rect = pygame.Rect(middle_x + 120, button_y, 110, 25)
        
        # Base color
        button_color = (150, 100, 100)
        # Check hover
        is_hovering = deselect_all_rect.collidepoint(self.mouse_pos)
        # Check click
        is_clicking = (self.clicked_element and 
                      self.clicked_element[0] == 'army_comp' and 
                      self.clicked_element[1] == 'deselect_all')
        # Apply feedback
        if is_clicking:
            button_color = self.brighten_color(button_color, 0.4)
        elif is_hovering:
            button_color = self.lighten_color(button_color, 0.2)
        
        pygame.draw.rect(self.screen, button_color, deselect_all_rect)
        pygame.draw.rect(self.screen, BLACK, deselect_all_rect, 2)
        deselect_all_text = self.small_font.render("Deselect All", True, WHITE)
        text_rect = deselect_all_text.get_rect(center=deselect_all_rect.center)
        self.screen.blit(deselect_all_text, text_rect)
        self.deselect_all_button = deselect_all_rect
        
        # Draw vertical separator line between middle and right sections
        separator_x = middle_x + 450  # Increased from 375 to 450 for very long names
        pygame.draw.line(self.screen, (100, 100, 100),
                        (separator_x, BOTTOM_UI_Y + 10),
                        (separator_x, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - 10), 3)
        
        # RIGHT SECTION: Army button grid
        grid_x = separator_x + 20
        grid_y = BOTTOM_UI_Y + 15
        
        # Draw army buttons (grid: 5 per row, max 3 rows)
        button_size = 45
        button_spacing = 5
        buttons_per_row = 5
        
        for i, unit in enumerate(units):
            # Calculate button position
            col = i % buttons_per_row
            row = i // buttons_per_row
            
            btn_x = grid_x + col * (button_size + button_spacing)
            btn_y = grid_y + row * (button_size + button_spacing)
            
            button_rect = pygame.Rect(btn_x, btn_y, button_size, button_size)
            
            # Get unit type and its letter
            unit_type = unit.get('type', 'Swordsman')
            unit_letter = self.game_state.UNIT_TYPES[unit_type]['letter']
            
            # Determine colors based on status and selection
            if unit['id'] in self.selected_army_units:
                # Selected - gold fill
                fill_color = (255, 215, 0)
            else:
                # Not selected - very light cream/golden (can brighten for hover feedback)
                # Using (235, 230, 210) instead of pure white (255, 255, 255)
                # This leaves room to brighten to (255, 255, 252) on hover/click
                fill_color = (235, 230, 210)
            
            # Apply hover/click feedback to fill color
            is_hovering = button_rect.collidepoint(self.mouse_pos)
            is_clicking = (self.clicked_element and 
                          self.clicked_element[0] == 'army_unit' and 
                          self.clicked_element[1] == unit['id'])
            
            if is_clicking:
                fill_color = self.brighten_color(fill_color, 0.4)
            elif is_hovering:
                fill_color = self.lighten_color(fill_color, 0.2)
            
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
            unit_text = self.font.render(unit_letter, True, BLACK)
            text_rect = unit_text.get_rect(center=button_rect.center)
            self.screen.blit(unit_text, text_rect)
            
            # Store button for click detection
            self.army_composition_buttons.append((button_rect, unit['id']))
        
        # Third separator line between grid and instructions
        grid_width = buttons_per_row * (button_size + button_spacing)
        instructions_separator_x = grid_x + grid_width + 15
        pygame.draw.line(self.screen, (100, 100, 100),
                        (instructions_separator_x, BOTTOM_UI_Y + 10),
                        (instructions_separator_x, BOTTOM_UI_Y + BOTTOM_UI_HEIGHT - 10), 3)
        
        # INSTRUCTIONS SECTION: To the right of third separator
        instructions_x = instructions_separator_x + 15
        instructions_y = grid_y
        
        instruction_lines = [
            "â€¢ Click to select",
            "â€¢ CTRL+Click for",
            "  multi-select",
            "â€¢ Right-click",
            "  destination to",
            "  command",
            "â€¢ Click elsewhere",
            "  to close"
        ]
        
        for line in instruction_lines:
            inst_text = self.small_font.render(line, True, (100, 100, 100))
            self.screen.blit(inst_text, (instructions_x, instructions_y))
            instructions_y += 18
    
    def draw_action_log_overlay(self):
        """Draw action log as an overlay on the right side of the screen"""
        if not self.action_log_visible:
            return
        
        # Overlay dimensions
        overlay_width = 300
        overlay_height = 400
        overlay_x = WINDOW_WIDTH - overlay_width - 20
        overlay_y = 50
        
        # Draw semi-transparent background
        overlay_surface = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
        pygame.draw.rect(overlay_surface, (40, 40, 40, 230), (0, 0, overlay_width, overlay_height))
        pygame.draw.rect(overlay_surface, WHITE, (0, 0, overlay_width, overlay_height), 2)
        self.screen.blit(overlay_surface, (overlay_x, overlay_y))
        
        # Title
        title_text = self.font.render("Action Log", True, WHITE)
        self.screen.blit(title_text, (overlay_x + 10, overlay_y + 10))
        
        # Close button
        close_rect = pygame.Rect(overlay_x + overlay_width - 30, overlay_y + 5, 25, 25)
        pygame.draw.rect(self.screen, (200, 100, 100), close_rect)
        pygame.draw.rect(self.screen, WHITE, close_rect, 1)
        close_text = self.font.render("X", True, WHITE)
        close_text_rect = close_text.get_rect(center=close_rect.center)
        self.screen.blit(close_text, close_text_rect)
        self.action_log_close_button = close_rect
        
        # Messages
        msg_y = overlay_y + 45
        for message in self.game_state.messages:
            # Wrap long messages
            if len(message) > 35:
                words = message.split()
                line = ""
                for word in words:
                    test_line = line + " " + word if line else word
                    if len(test_line) > 35:
                        msg_text = self.small_font.render(line, True, WHITE)
                        self.screen.blit(msg_text, (overlay_x + 10, msg_y))
                        msg_y += 20
                        line = word
                    else:
                        line = test_line
                if line:
                    msg_text = self.small_font.render(line, True, WHITE)
                    self.screen.blit(msg_text, (overlay_x + 10, msg_y))
                    msg_y += 20
            else:
                msg_text = self.small_font.render(message, True, WHITE)
                self.screen.blit(msg_text, (overlay_x + 10, msg_y))
                msg_y += 20
    
    def draw_victory_screen(self):
        """Draw the victory screen overlay"""
        # Create semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 180), (0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))
        self.screen.blit(overlay, (0, 0))
        
        # Victory text
        winner_color = self.game_state.get_player_color(self.game_state.winner)
        victory_font = pygame.font.Font(None, 72)
        victory_text = victory_font.render(f"PLAYER {self.game_state.winner + 1} WINS!", True, winner_color)
        victory_rect = victory_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 50))
        self.screen.blit(victory_text, victory_rect)
        
        # Restart button
        button_width = 200
        button_height = 50
        restart_rect = pygame.Rect(
            WINDOW_WIDTH // 2 - button_width // 2,
            WINDOW_HEIGHT // 2 + 50,
            button_width,
            button_height
        )
        pygame.draw.rect(self.screen, (100, 200, 100), restart_rect)
        pygame.draw.rect(self.screen, WHITE, restart_rect, 3)
        
        restart_text = self.large_font.render("Restart Game", True, WHITE)
        text_rect = restart_text.get_rect(center=restart_rect.center)
        self.screen.blit(restart_text, text_rect)
        
        self.restart_button = restart_rect
        
        # Quit button
        quit_rect = pygame.Rect(
            WINDOW_WIDTH // 2 - button_width // 2,
            WINDOW_HEIGHT // 2 + 120,
            button_width,
            button_height
        )
        pygame.draw.rect(self.screen, (200, 100, 100), quit_rect)
        pygame.draw.rect(self.screen, WHITE, quit_rect, 3)
        
        quit_text = self.large_font.render("Quit", True, WHITE)
        text_rect = quit_text.get_rect(center=quit_rect.center)
        self.screen.blit(quit_text, text_rect)
        
        self.quit_button = quit_rect
    
    def restart_game(self):
        """Restart the game with a fresh state"""
        self.game_state = GameState(num_players=2)
        print("Game restarted!")
    
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
        print("\n" + "="*60)
        print("ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â½Ãƒâ€šÃ‚Â® GAME STARTED - DEBUG VERSION ACTIVE")
        print("="*60)
        print(f"ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€šÃ‚Â MAP_HEIGHT = {MAP_HEIGHT}")
        print(f"ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¥ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  WINDOW_HEIGHT = {WINDOW_HEIGHT}")
        running = True
        
        while running:
            # Update mouse position every frame for hover detection
            self.mouse_pos = pygame.mouse.get_pos()
            
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                elif event.type == pygame.USEREVENT + 1:
                    # Battle animation timer - transition from resolving to result
                    if self.battle_popup_visible and self.battle_popup_state == 'resolving':
                        self.battle_popup_state = 'result'
                        pygame.time.set_timer(pygame.USEREVENT + 1, 0)  # Cancel timer
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        # Track if click was handled
                        click_handled = False
                        
                        # Check victory screen buttons (Phase 2A: extracted to method)
                        handled, should_quit = self.handle_victory_screen_click(event.pos)
                        if should_quit:
                            running = False
                        if handled:
                            click_handled = True
                        
                        # Check battle popup buttons (Phase 2A: extracted to method)
                        if not click_handled:
                            click_handled = self.handle_battle_popup_click(event.pos)
                        
                        # Check order sidebar buttons (Phase 2B: extracted to method)
                        if not click_handled:
                            click_handled = self.handle_order_sidebar_click(event.pos)
                        
                        # Check battle markers (Phase 2B: extracted to method)
                        if not click_handled:
                            click_handled = self.handle_battle_marker_click(event.pos)
                        
                        # Check bottom UI buttons (Phase 2A: extracted to method)
                        if not click_handled:
                            click_handled = self.handle_bottom_ui_click(event.pos)
                        
                        # If not handled in bottom UI, treat as regular map click
                        if not click_handled and event.pos[1] >= BOTTOM_UI_Y:
                            self.handle_map_area_click(event.pos)
                            click_handled = True
                        
                        # Regular map click (if nothing else handled it)
                        if not click_handled:
                            self.handle_map_area_click(event.pos)
                    
                    elif event.button == 3:  # Right click
                        # Right-click for movement orders (only in planning phase)
                        if self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
                            self.handle_right_click(event.pos)
                
                elif event.type == pygame.MOUSEMOTION:
                    # Camera controls (Phase 2D: drag only, edge scrolling moved to main loop)
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())
                    
                    # Mouse motion hover tracking (Phase 2C: extracted to method)
                    self.handle_mouse_motion(event.pos)
                
                elif event.type == pygame.KEYDOWN:
                    # Keyboard input (Phase 2A: extracted to method)
                    self.handle_keyboard_input(event)
                
                elif event.type == pygame.MOUSEWHEEL:
                    # Camera zoom (Phase 2D: mouse wheel)
                    self.handle_camera_zoom(event.y)
            
            # Keyboard camera control (Phase 2D: continuous per-frame)
            # Must be outside event loop to allow smooth continuous scrolling
            keys = pygame.key.get_pressed()
            self.handle_keyboard_camera(keys)
            
            # Edge scrolling (Phase 2D: continuous per-frame)
            # Check mouse position every frame for smooth edge scrolling
            mouse_pos = pygame.mouse.get_pos()
            self.handle_edge_scrolling(mouse_pos)
            
            # Drawing
            self.screen.fill(WHITE)
            
            # Draw map (Phase 2D: transform with camera!)
            # Optimization: Cache scaled map to avoid rescaling every frame (FPS improvement!)
            # Calculate target size based on camera zoom
            scaled_map_width = int(self.map_width * self.camera_zoom)
            scaled_map_height = int(self.map_height * self.camera_zoom)
            
            # Only rescale if zoom level changed (massive FPS improvement!)
            if self.cached_zoom_level != self.camera_zoom:
                # Zoom changed - rescale from original high-res image
                self.cached_scaled_map = pygame.transform.smoothscale(
                    self.map_image_original, 
                    (scaled_map_width, scaled_map_height)
                )
                self.cached_zoom_level = self.camera_zoom
            
            # Use cached scaled map (no rescaling needed!)
            scaled_map = self.cached_scaled_map
            
            # Position based on camera offset (negative because camera moves opposite to map)
            map_x = int(-self.camera_offset[0] * self.camera_zoom)
            map_y = int(-self.camera_offset[1] * self.camera_zoom) + TOP_PANEL_HEIGHT  # Offset for top panel
            
            # Draw scaled and positioned map
            self.screen.blit(scaled_map, (map_x, map_y))
            
            # Draw territories
            self.draw_territories()
            
            # Draw movement arrows (orders)
            self.draw_movement_arrows()
            
            # Draw battle markers
            self.draw_battle_markers()
            
            # Draw top panel (Phase A: UI Redesign)
            self.draw_top_panel()
            
            # Draw order sidebar
            self.draw_order_sidebar()
            
            # Draw bottom UI
            self.draw_bottom_ui()
            
            # Draw chat input box (appears above bottom UI when active)
            self.draw_chat_input()
            
            # Track building button hover (must happen after draw_bottom_ui every frame)
            # This ensures hover state is always properly managed
            if self.selected_plot:
                mouse_pos = pygame.mouse.get_pos()
                current_hover = None
                # Only track if we're showing building buttons (plot is empty)
                if hasattr(self, 'building_buttons') and self.building_buttons:
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
            
            # Draw battle popup (on top of everything)
            self.draw_battle_popup()
            
            # Draw victory screen (on top of everything else)
            if self.game_state.phase == 'ended':
                self.draw_victory_screen()
            
            # Update and render tooltips (Phase 2C: extracted to method)
            # MUST happen after all drawing, before display.flip()
            self.update_frame_tooltips()
            
#             # ========================================
#             # CAMERA DEBUG OVERLAY (Phase 2D: temporary for testing)
#             # Shows camera offset and zoom values on screen
#             # TODO: Remove this after camera rendering is fully implemented
#             # ========================================
#             debug_y = 10
#             debug_x = 10
#             
#             # Camera offset
#             offset_text = self.small_font.render(
#                 f"Camera Offset: ({self.camera_offset[0]:.1f}, {self.camera_offset[1]:.1f})",
#                 True, RED
#             )
#             self.screen.blit(offset_text, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Map size vs visible size (shows why camera might not move!)
#             visible_w = WINDOW_WIDTH / self.camera_zoom
#             visible_h = MAP_HEIGHT / self.camera_zoom
#             map_bounds_text = self.small_font.render(
#                 f"Map: {self.map_width}x{self.map_height} | Visible: {int(visible_w)}x{int(visible_h)}",
#                 True, RED
#             )
#             self.screen.blit(map_bounds_text, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Camera bounds (max scrollable distance)
#             max_x = max(0, self.map_width - visible_w)
#             max_y = max(0, self.map_height - visible_h)
#             bounds_text = self.small_font.render(
#                 f"Max Offset: ({int(max_x)}, {int(max_y)}) - {'CAN SCROLL' if max_x > 0 or max_y > 0 else 'MAP FITS IN WINDOW!'}",
#                 True, YELLOW if max_x > 0 or max_y > 0 else RED
#             )
#             self.screen.blit(bounds_text, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Camera zoom (with limit indicators)
#             zoom_color = RED
#             zoom_suffix = ""
#             if self.camera_zoom >= self.camera_max_zoom:
#                 zoom_color = YELLOW
#                 zoom_suffix = " - MAX ZOOM"
#             elif self.camera_zoom <= self.camera_min_zoom:
#                 zoom_color = YELLOW
#                 zoom_suffix = " - MIN ZOOM"
#             
#             zoom_text = self.small_font.render(
#                 f"Camera Zoom: {self.camera_zoom:.2f}x ({int(self.camera_zoom * 100)}%){zoom_suffix}",
#                 True, zoom_color
#             )
#             self.screen.blit(zoom_text, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Drag state
#             if self.camera_drag_start is not None:
#                 drag_text = self.small_font.render("DRAGGING (middle mouse)", True, GREEN)
#             else:
#                 drag_text = self.small_font.render("Not dragging", True, GRAY)
#             self.screen.blit(drag_text, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Edge scroll state
#             if self.debug_edge_scroll:
#                 edge_text = self.small_font.render(self.debug_edge_scroll, True, GREEN)
#             else:
#                 edge_text = self.small_font.render("Edge scroll: inactive", True, GRAY)
#             self.screen.blit(edge_text, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Keyboard scroll state
#             if self.debug_keyboard_scroll:
#                 kb_text = self.small_font.render(self.debug_keyboard_scroll, True, GREEN)
#             else:
#                 kb_text = self.small_font.render("Keyboard: inactive", True, GRAY)
#             self.screen.blit(kb_text, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Instructions
#             instructions = self.small_font.render(
#                 "Camera: Middle-drag | Edge scroll | Arrows | Mouse wheel zoom",
#                 True, YELLOW
#             )
#             self.screen.blit(instructions, (debug_x, debug_y))
#             debug_y += 20
#             
#             # Map fit warning (only if zoomed out completely)
#             if max_x <= 0 and max_y <= 0:
#                 warning = self.small_font.render(
#                     "Map fits in window! Zoom in (wheel up) to test camera movement!",
#                     True, RED
#                 )
#                 self.screen.blit(warning, (debug_x, debug_y))
            
            # Update click flash timer (decrement if active)
            if self.click_flash_timer > 0:
                dt = self.clock.get_time()  # Milliseconds since last frame
                self.click_flash_timer -= dt
                if self.click_flash_timer <= 0:
                    self.clicked_element = None  # Clear flash when timer expires
            
            # Update display
            pygame.display.flip()
            self.clock.tick(FPS)
        
        pygame.quit()
        sys.exit()
    
    # ========================================================================
    # PHASE 2A: EVENT HANDLERS
    # 
    # Event handlers are extracted from the run() method to improve
    # readability and maintainability. Each handler focuses on one type
    # of user interaction.
    #
    # Event handling priority order:
    # 1. Victory screen clicks (if game ended)
    # 2. Battle popup clicks (if popup visible)
    # 3. Bottom UI clicks (if in UI area)
    # 4. Map area clicks (if in map area)
    # 5. Keyboard input (any time)
    # ========================================================================
    
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
        
        # Check restart button
        if hasattr(self, 'restart_button') and self.restart_button.collidepoint(pos):
            self.restart_game()
            return True, False
        
        # Check quit button
        if hasattr(self, 'quit_button') and self.quit_button.collidepoint(pos):
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
            - May change self.battle_popup_state ('initial' → 'resolving')
            - May close popup by setting self.battle_popup_visible = False
            - May set timer for auto-transition (resolving → result)
            - Stores battle result in self.battle_result for display
        
        Phase Context:
            Only processes clicks when self.battle_popup_visible is True
        """
        if not self.battle_popup_visible:
            return False
        
        # Check resolve button (in initial state)
        if self.battle_popup_state == 'initial':
            if hasattr(self, 'resolve_battle_button') and self.resolve_battle_button:
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
                    
                    # Transition to resolving animation
                    self.battle_popup_state = 'resolving'
                    # Auto-transition to result after a short delay
                    pygame.time.set_timer(pygame.USEREVENT + 1, 1500)  # 1.5 seconds
                    return True
        
        # Check close button (in result state)
        elif self.battle_popup_state == 'result':
            if hasattr(self, 'close_popup_button') and self.close_popup_button:
                if self.close_popup_button.collidepoint(pos):
                    # Close popup
                    self.battle_popup_visible = False
                    self.selected_battle_index = None
                    self.battle_popup_state = 'initial'
                    self.battle_result = None  # Clear stored result
                    return True
        
        return False
    
    def handle_keyboard_input(self, event):
        """
        Handle keyboard input (Phase 2A extraction).
        
        Supported keyboard shortcuts:
        - TAB: Toggle sidebar (only in planning phase)
        - S/A/P/C: Train units (only when Barracks selected)
            S = Swordsman
            A = Archer
            P = Pikeman
            C = Cavalry
        - F/M/B/K/Q: Build buildings (only when plot selected)
            F = Farm
            M = Mine
            B = Barracks
            K = Keep
            Q = Square (Q for sQuare)
        
        Args:
            event: pygame keyboard event (KEYDOWN type)
            
        Returns:
            bool: True if key was handled
        
        Side Effects:
            - May toggle self.game_state.sidebar_expanded
            - May start unit training via self.game_state.start_training()
            - May start building construction via self.game_state.start_construction()
            - May clear button tooltips
            - May clear selections
        
        Phase Context:
            - TAB only works in 'playing' phase, 'planning' turn_phase
            - Training shortcuts only work when self.selected_barracks is set
            - Building shortcuts only work when self.selected_plot is set
        """
        # ========================================
        # CHAT INPUT HANDLING (highest priority)
        # ========================================
        # When chat is active, handle text input and ignore other shortcuts
        if self.chat_input_active:
            if event.key == pygame.K_RETURN:
                # Send message
                if self.chat_input_text.strip():  # Don't send empty messages
                    self.game_state.add_chat_message(self.game_state.current_player, self.chat_input_text)
                # Close chat input
                self.chat_input_active = False
                self.chat_input_text = ""
                return True
            
            elif event.key == pygame.K_ESCAPE:
                # Cancel chat input
                self.chat_input_active = False
                self.chat_input_text = ""
                return True
            
            elif event.key == pygame.K_BACKSPACE:
                # Delete last character
                self.chat_input_text = self.chat_input_text[:-1]
                return True
            
            else:
                # Add character to chat input
                # Only accept printable characters
                if event.unicode and len(self.chat_input_text) < 100:  # Max 100 chars
                    self.chat_input_text += event.unicode
                return True
        
        # ========================================
        # CHAT OPEN (when not already typing)
        # ========================================
        # ENTER key opens chat input (when not already typing)
        if event.key == pygame.K_RETURN and not self.chat_input_active:
            self.chat_input_active = True
            self.chat_input_text = ""
            return True
        
        # ========================================
        # OTHER KEYBOARD SHORTCUTS (only when chat not active)
        # ========================================
        # Tab key: Toggle sidebar (only in planning phase)
        if event.key == pygame.K_TAB:
            if self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
                self.game_state.sidebar_expanded = not self.game_state.sidebar_expanded
                return True
        
        # Building shortcuts (when plot is selected)
        if self.selected_plot and self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
            territory, plot_index = self.selected_plot
            
            # F = Farm, M = Mine, B = Barracks, K = Keep, Q = Square
            building_name = None
            if event.key == pygame.K_f:
                building_name = 'Farm'
            elif event.key == pygame.K_m:
                building_name = 'Mine'
            elif event.key == pygame.K_b:
                building_name = 'Barracks'
            elif event.key == pygame.K_k:
                building_name = 'Keep'
            elif event.key == pygame.K_q:
                building_name = 'Square'
            
            if building_name:
                if self.game_state.start_construction(territory, plot_index, building_name):
                    self.selected_plot = None
                    self.clear_button_tooltip()
                return True
        
        # Training shortcuts (when Barracks is selected)
        if self.selected_barracks and self.game_state.phase == 'playing' and self.game_state.turn_phase == 'planning':
            territory, barracks_plot_index = self.selected_barracks
            
            # S = Swordsman, A = Archer, P = Pikeman, C = Cavalry
            unit_type = None
            if event.key == pygame.K_s:
                unit_type = 'Swordsman'
            elif event.key == pygame.K_a:
                unit_type = 'Archer'
            elif event.key == pygame.K_p:
                unit_type = 'Pikeman'
            elif event.key == pygame.K_c:
                unit_type = 'Cavalry'
            
            if unit_type:
                self.game_state.start_training(territory, barracks_plot_index, unit_type)
                self.clear_button_tooltip()  # Clear any lingering tooltips
                return True
        
        return False

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
        
        # End Turn button
        if hasattr(self, 'end_turn_button'):
            if self.end_turn_button.collidepoint(pos):
                self.trigger_click_flash('bottom_button', 'end_turn')
                self.game_state.next_player()
                self.selected_plot = None
                self.selected_barracks = None
                self.show_army_composition = False
                self.selected_army_units = []
                return True
        
        # Training buttons (when Barracks selected)
        if hasattr(self, 'train_buttons') and self.train_buttons:
            for unit_type, button_rect in self.train_buttons.items():
                if button_rect.collidepoint(pos):
                    self.trigger_click_flash('training', unit_type)
                    if self.selected_barracks:
                        territory, barracks_plot_index = self.selected_barracks
                        if self.game_state.start_training(territory, barracks_plot_index, unit_type):
                            self.clear_button_tooltip()
                    return True
        
        # Queue cancel buttons (when Barracks selected)
        if hasattr(self, 'queue_cancel_buttons'):
            for cancel_rect, queue_index in self.queue_cancel_buttons:
                if cancel_rect.collidepoint(pos):
                    self.trigger_click_flash('queue_cancel', queue_index)
                    if self.selected_barracks:
                        territory, barracks_plot_index = self.selected_barracks
                        self.game_state.cancel_training(territory, barracks_plot_index, queue_index)
                    return True
        
        # Demolish Barracks button
        if hasattr(self, 'demolish_barracks_button') and self.demolish_barracks_button is not None:
            if self.demolish_barracks_button.collidepoint(pos):
                self.trigger_click_flash('demolish', 'barracks')
                territory = self.demolish_barracks_territory
                barracks_plot_index = self.demolish_barracks_plot_index
                if self.game_state.destroy_building(territory, barracks_plot_index):
                    self.selected_barracks = None
                    self.clear_button_tooltip()
                return True
        
        # Army composition buttons (when army composition UI visible)
        if self.show_army_composition and hasattr(self, 'army_composition_buttons'):
            # Select All button
            if hasattr(self, 'select_all_button') and self.select_all_button:
                if self.select_all_button.collidepoint(pos):
                    self.trigger_click_flash('army_comp', 'select_all')
                    if self.army_composition_territory:
                        units = self.game_state.ensure_army_units_exist(self.army_composition_territory)
                        self.selected_army_units = [u['id'] for u in units if u['status'] == 'ready']
                    return True
            
            # Deselect All button
            if hasattr(self, 'deselect_all_button') and self.deselect_all_button:
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
        
        # Territory info plot buttons
        if self.selected_territory_info and hasattr(self, 'territory_info_plot_buttons'):
            for plot_rect, territory, plot_index in self.territory_info_plot_buttons:
                if plot_rect.collidepoint(pos):
                    if self.game_state.territory_owners.get(territory, -1) == self.game_state.current_player:
                        # Check if this plot has a Barracks
                        has_barracks = (territory in self.game_state.buildings and 
                                      plot_index in self.game_state.buildings[territory] and
                                      self.game_state.buildings[territory][plot_index] == 'Barracks')
                        
                        if has_barracks:
                            # Select Barracks for training UI
                            self.selected_barracks = (territory, plot_index)
                            self.selected_plot = None
                            self.selected_territory_info = None
                            self.game_state.deselect_army()
                        else:
                            # Select plot for building UI
                            self.selected_plot = (territory, plot_index)
                            self.selected_territory_info = None
                            self.game_state.deselect_army()
                        return True
        
        # Building-related buttons (when plot is selected)
        if self.selected_plot:
            # Building buttons
            if hasattr(self, 'building_buttons'):
                try:
                    if self.building_buttons:
                        for building_name, button_rect in self.building_buttons.items():
                            if button_rect.collidepoint(pos):
                                self.trigger_click_flash('building', building_name)
                                territory, plot_index = self.selected_plot
                                if self.game_state.start_construction(territory, plot_index, building_name):
                                    self.selected_plot = None
                                    self.clear_button_tooltip()
                                return True
                except Exception as e:
                    print(f"Error in building buttons: {e}")
            
            # Cancel construction button
            if hasattr(self, 'cancel_button') and self.cancel_button is not None:
                if self.cancel_button.collidepoint(pos):
                    self.trigger_click_flash('cancel', 'construction')
                    territory, plot_index = self.selected_plot
                    result = self.game_state.cancel_construction(territory, plot_index)
                    if result:
                        self.selected_plot = None
                        self.clear_button_tooltip()
                    return True
            
            # Demolish building button
            if hasattr(self, 'demolish_button') and self.demolish_button is not None:
                if self.demolish_button.collidepoint(pos):
                    self.trigger_click_flash('demolish', 'building')
                    territory, plot_index = self.selected_plot
                    result = self.game_state.destroy_building(territory, plot_index)
                    if result:
                        self.selected_plot = None
                        self.clear_button_tooltip()
                    return True
        
        # Click not handled by any bottom UI element
        return False
    
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
        
        # Sidebar is always expanded - no collapse functionality
        
        # Check tab buttons (Phase B: only if expanded)
        if self.game_state.sidebar_expanded and hasattr(self, 'sidebar_tab_buttons'):
            for tab_id, tab_rect in self.sidebar_tab_buttons.items():
                if tab_rect.collidepoint(pos):
                    # Switch to clicked tab
                    self.game_state.active_sidebar_tab = tab_id
                    return True
        
        # Check individual order cancel buttons (only if expanded)
        if self.game_state.sidebar_expanded and hasattr(self, 'order_cancel_buttons'):
            for button_rect, order_index in self.order_cancel_buttons:
                if button_rect.collidepoint(pos):
                    self.game_state.cancel_movement_order(order_index)
                    return True
        
        # Check cancel all button (only if expanded)
        if self.game_state.sidebar_expanded and hasattr(self, 'cancel_all_button') and self.cancel_all_button:
            if self.cancel_all_button.collidepoint(pos):
                self.game_state.cancel_all_orders()
                return True
        
        return False
    
    def handle_battle_marker_click(self, pos):
        """
        Handle clicks on battle markers to open battle popup (Phase 2B extraction).
        
        Battle markers (crossed swords icons) appear on territories during the
        battles phase when there are pending battles. Clicking a marker opens
        the battle popup to show/resolve that specific battle.
        
        Only works when:
        - In battles phase (phase='playing', turn_phase='battles')
        - Battle popup is not already visible
        - Valid battle markers exist
        
        Args:
            pos: (x, y) tuple of click position in screen coordinates
        
        Returns:
            bool: True if click was handled, False otherwise
        
        Side Effects:
            - Sets self.selected_battle_index to clicked battle
            - Sets self.battle_popup_visible = True
            - Sets self.battle_popup_state = 'initial'
        
        Phase Context:
            Only active during battles phase.
            Part of Phase 2B to complete event handler extraction.
        """
        # Only active during battles phase
        if self.game_state.phase != 'playing' or self.game_state.turn_phase != 'battles':
            return False
        
        # Only if popup not already visible
        if self.battle_popup_visible:
            return False
        
        # Check battle markers
        if hasattr(self, 'battle_markers'):
            for i, marker_rect in enumerate(self.battle_markers):
                if marker_rect and marker_rect.collidepoint(pos):
                    if i < len(self.game_state.pending_battles):
                        self.selected_battle_index = i
                        self.battle_popup_visible = True
                        self.battle_popup_state = 'initial'
                        return True
        
        return False
    
    def handle_action_log_click(self, pos):
        """
        Handle click on action log close button (Phase 2B extraction).
        
#         The action log is an overlay that displays game events and messages.
#         It has an X button in the top-right corner to close it.
#         
#         Only works when:
#         - Action log is visible (self.action_log_visible = True)
#         - Close button exists
#         
#         Args:
#             pos: (x, y) tuple of click position in screen coordinates
#         
#         Returns:
#             bool: True if click was handled, False otherwise
#         
#         Side Effects:
#             - Sets self.action_log_visible = False
#         
#         Phase Context:
#             Active in any phase when action log is open.
#             Part of Phase 2B to complete event handler extraction.
#         """
#         # Only if action log is visible
#         if not self.action_log_visible:
#             return False
#         
#         # Check close button
#         if hasattr(self, 'action_log_close_button'):
#             if self.action_log_close_button.collidepoint(pos):
#                 self.action_log_visible = False
#                 return True
#         
#         return False
#     
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
        # Store SCREEN position for tooltip rendering (tooltips render in screen space)
        self.mouse_pos = pos
        
        # Convert screen position to world position for hover detection
        # This makes hover work correctly with camera offset and zoom!
        world_pos = self.screen_to_world(pos)
        
        # Calculate army hover radius in world space that matches visual size
        # (same calculation as click detection for consistency)
        ui_scale = self.get_ui_scale_factor()
        army_hover_radius_world = (ARMY_CIRCLE_RADIUS * ui_scale) / self.camera_zoom
        
        # Only track territory/army hover when in map area (not bottom UI)
        if pos[1] < MAP_HEIGHT:
            # Check if hovering over an army first (takes priority over territory)
            # NOTE: scaled_centers are in WORLD coordinates, so compare with world_pos!
            army_at_pos = None
            for territory, (cx, cy) in self.scaled_centers.items():
                # Distance calculation uses world coordinates
                distance = ((world_pos[0] - cx) ** 2 + (world_pos[1] - cy) ** 2) ** 0.5
                if distance <= army_hover_radius_world:  # Within army circle (matches visual size!)
                    total_armies = self.game_state.armies.get(territory, 0)
                    if total_armies > 0:
                        army_at_pos = territory
                        break
            
            # Get territory at current position (if not over army)
            # get_territory_at_pos also needs to work with camera - we'll update it separately
            territory_at_pos = None
            if not army_at_pos:
                territory_at_pos = self.get_territory_at_pos(world_pos)
            
            # Check if hovering over a plot (takes priority over territory for tooltips)
            plot_at_pos = self.get_plot_at_pos(world_pos)
            
            # Check if hovering over map button (building or training icon)
            hovering_map_button = (self.hover_target_button and 
                                  self.hover_target_button[0] in ['map_building', 'map_training'])
            
            # INSTANT HIGHLIGHTS (no delay)
            # Suppress territory glow when hovering over map buttons OR plots
            if not hovering_map_button and not plot_at_pos:
                self.hovered_army = army_at_pos
                if not self.hovered_army:
                    self.hovered_territory = territory_at_pos
                else:
                    self.hovered_territory = None
            else:
                # Clear hover when over map buttons or plots
                self.hovered_army = None
                self.hovered_territory = None
            
            # DELAYED TOOLTIPS - Start/reset timer
            # Disable territory hover if:
            # 1. Plot is selected (building icons might be shown)
            # 2. Currently hovering over a map building/training icon
            # 3. Currently hovering over a plot itself
            should_track_territory = (not self.selected_plot and 
                                     not self.selected_barracks and
                                     not hovering_map_button and
                                     not plot_at_pos)
            
            # Check if we're hovering over something new
            if should_track_territory and (army_at_pos != self.hover_target_army or territory_at_pos != self.hover_target_territory):
                # Reset timer - we moved to a different target
                self.hover_start_time = pygame.time.get_ticks()
                self.hover_target_army = army_at_pos
                self.hover_target_territory = territory_at_pos
                # Clear tooltip flags until timer expires (checked in main loop)
                self.show_tooltip_army = None
                self.show_tooltip_territory = None
            elif not should_track_territory:
                # Clear territory hover if plot is selected or hovering building icon
                if self.hover_target_territory:
                    self.hover_target_territory = None
                    self.show_tooltip_territory = None
        else:
            # Mouse in bottom UI - clear map hover states
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
        # Track building button hover (must happen after draw_bottom_ui every frame)
        # This ensures hover state is always properly managed
        if self.selected_plot:
            mouse_pos = pygame.mouse.get_pos()
            current_hover = None
            # Only track if we're showing building buttons (plot is empty)
            if hasattr(self, 'building_buttons') and self.building_buttons:
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
        if self.mouse_pos[1] < MAP_HEIGHT:  # Only show tooltip when hovering map area
            # Show button tooltip for map building/training icons first
            if self.show_tooltip_button and self.show_tooltip_button[0] in ['map_building', 'map_training']:
                self.draw_button_tooltip(self.mouse_pos, self.show_tooltip_button)
            # Show army tooltip if hovering over an army, otherwise show territory tooltip
            # Use show_tooltip_* variables which have the delay applied
            elif self.show_tooltip_army:
                self.draw_army_hover_tooltip(self.mouse_pos, self.show_tooltip_army)
            elif self.show_tooltip_territory:
                self.draw_territory_hover_tooltip(self.mouse_pos)
        elif self.show_tooltip_button:
            # Show button tooltip (in bottom UI area)
            self.draw_button_tooltip(self.mouse_pos, self.show_tooltip_button)
    
    # ========================================
    # PHASE 2D: CAMERA MOVEMENT METHODS
    # ========================================
    
    def handle_camera_drag(self, pos, buttons):
        """
        Handle camera dragging with middle mouse button (Phase 2D).
        
        Allows player to click and drag to pan the camera. Uses middle mouse
        button (buttons[1]) to avoid conflicts with left-click selection and
        right-click movement orders.
        
        Only works in map area (not in bottom UI or action log sidebar).
        
        Drag Mechanics:
        - Press middle mouse: Start drag, record position
        - Move mouse with middle held: Calculate delta, move camera
        - Release middle mouse: End drag
        
        Camera offset is updated in world units (independent of zoom), which
        means drag speed feels consistent regardless of zoom level.
        
        Args:
            pos: (x, y) tuple of current mouse position in screen coordinates
            buttons: pygame.mouse.get_pressed() result (button state tuple)
                buttons[0] = left, buttons[1] = middle, buttons[2] = right
        
        Side Effects:
            - Updates self.camera_offset[0] and [1] (pans camera)
            - Updates self.camera_drag_start (tracks drag state)
            - Calls clamp_camera_to_bounds() to enforce map limits
        
        Phase Context:
            Part of Phase 2D camera system.
            Uses MOUSEMOTION event (integrated with hover detection from Phase 2C).
        """
        # Only allow dragging in map area (not in bottom UI)
        if pos[1] >= BOTTOM_UI_Y:
            self.camera_drag_start = None
            return
        
        if buttons[1]:  # Middle mouse button (index 1)
            if self.camera_drag_start is not None:
                # Calculate drag delta (how far mouse moved)
                dx = pos[0] - self.camera_drag_start[0]
                dy = pos[1] - self.camera_drag_start[1]
                
                # Update camera offset
                # Invert delta: dragging right means view moves left (showing what's to the right)
                # Divide by zoom to keep drag speed consistent at all zoom levels
                self.camera_offset[0] -= dx / self.camera_zoom
                self.camera_offset[1] -= dy / self.camera_zoom
                
                # Enforce map bounds
                self.clamp_camera_to_bounds()
            
            # Update drag start for next frame
            self.camera_drag_start = pos
        else:
            # Middle mouse released - end drag
            self.camera_drag_start = None
    
    def handle_edge_scrolling(self, pos):
        """
        Handle edge scrolling when mouse is near map area edges (Phase 2D).
        
        Automatically pans camera when mouse is within edge_scroll_margin
        pixels of the MAP AREA edge (not window edge). This is a classic RTS
        feature that allows camera movement while keeping hands on mouse.
        
        Speed Scaling (User Enhancement):
        - Scales with zoom: 3x faster when fully zoomed in
        - Scales with distance: Closer to edge = faster scrolling
        - Smooth acceleration as you approach edge
        
        Map Area Edges (accounting for top panel):
        - Left edge: x < margin → scroll left
        - Right edge: x > WINDOW_WIDTH - margin → scroll right
        - Top edge: y < TOP_PANEL_HEIGHT + margin → scroll up  
        - Bottom edge: y > (TOP_PANEL_HEIGHT + MAP_HEIGHT) - margin → scroll down
        
        Only scrolls when mouse is in map area, not in top panel, bottom UI, or action log.
        
        Args:
            pos: (x, y) tuple of current mouse position in screen coordinates
        
        Side Effects:
            - Updates self.camera_offset[0] and [1] (pans camera)
            - Calls clamp_camera_to_bounds() to enforce map limits
        
        Phase Context:
            Part of Phase 2D camera system.
            Runs every frame in main loop for smooth continuous scrolling.
        """
        # Only scroll if mouse in map area (not in top panel or bottom UI)
        if pos[1] < TOP_PANEL_HEIGHT or pos[1] >= BOTTOM_UI_Y:
            return
        
        x, y = pos
        scroll_x = 0
        scroll_y = 0
        
        # Calculate base scroll speed (scales with zoom for consistent feel)
        # At min zoom (1.65x): 10 pixels/frame
        # At max zoom (4.0x): ~24 pixels/frame (2.4x faster)
        base_speed = 10.0 * (self.camera_zoom / self.camera_min_zoom)
        
        # Check horizontal edges
        right_edge_limit = WINDOW_WIDTH
        
        if x < self.edge_scroll_margin:
            # Near left edge - scroll left
            # Speed scales with how close to edge (closer = faster)
            distance_from_edge = self.edge_scroll_margin - x
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_x = -base_speed * speed_multiplier
        elif x > right_edge_limit - self.edge_scroll_margin:
            # Near right edge (or action log edge) - scroll right
            distance_from_edge = x - (right_edge_limit - self.edge_scroll_margin)
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_x = base_speed * speed_multiplier
        
        # Check vertical edges (of map area, accounting for top panel!)
        # Convert screen Y to map-relative Y
        map_relative_y = y - TOP_PANEL_HEIGHT
        
        if map_relative_y < self.edge_scroll_margin:
            # Near top edge of map - scroll up
            distance_from_edge = self.edge_scroll_margin - map_relative_y
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_y = -base_speed * speed_multiplier
        elif map_relative_y > MAP_HEIGHT - self.edge_scroll_margin and map_relative_y < MAP_HEIGHT:
            # Near bottom edge of map area - scroll down
            # Must be BEFORE bottom UI (map_relative_y < MAP_HEIGHT)
            distance_from_edge = map_relative_y - (MAP_HEIGHT - self.edge_scroll_margin)
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_y = base_speed * speed_multiplier
        
        # Apply scrolling (adjust for zoom to keep world-space speed consistent)
        if scroll_x != 0 or scroll_y != 0:
            self.camera_offset[0] += scroll_x / self.camera_zoom
            self.camera_offset[1] += scroll_y / self.camera_zoom
            
            # Debug: Store that edge scroll is active
            self.debug_edge_scroll = f"Edge: ({int(scroll_x)}, {int(scroll_y)})"
            
            # Enforce map bounds
            self.clamp_camera_to_bounds()
        else:
            self.debug_edge_scroll = None
    
    def handle_keyboard_camera(self, keys):
        """
        Handle keyboard camera movement (arrow keys only) (Phase 2D).
        
        Allows player to pan camera using keyboard. Uses ONLY arrow keys
        to avoid conflicts with game shortcuts (S = Swordsman, A = Archer, etc.).
        
        WASD removed to prevent conflicts with:
        - S: Swordsman training shortcut
        - A: Archer training shortcut  
        - W: (reserved for future features)
        - D: (reserved for future features)
        
        Keys:
        - Up Arrow: Pan up (decrease y offset to show top)
        - Down Arrow: Pan down (increase y offset to show bottom)
        - Left Arrow: Pan left (decrease x offset to show left)
        - Right Arrow: Pan right (increase x offset to show right)
        
        Scroll speed is in pixels per frame, adjusted for zoom.
        
        Args:
            keys: pygame.key.get_pressed() result (key state array)
                Call in main loop every frame, not just on KEYDOWN events
        
        Side Effects:
            - Updates self.camera_offset[0] and [1] (pans camera)
            - Calls clamp_camera_to_bounds() to enforce map limits
        
        Note:
            This should be called every frame in the main loop, not just
            on KEYDOWN events, to allow smooth continuous scrolling.
        
        Phase Context:
            Part of Phase 2D camera system.
            Called directly in main loop (not event-driven).
        """
        scroll_x = 0
        scroll_y = 0
        
        # Horizontal movement (arrow keys only!)
        if keys[pygame.K_LEFT]:
            # Left Arrow - scroll left
            scroll_x = -self.keyboard_scroll_speed
        if keys[pygame.K_RIGHT]:
            # Right Arrow - scroll right
            scroll_x = self.keyboard_scroll_speed
        
        # Vertical movement (arrow keys only!)
        if keys[pygame.K_UP]:
            # Up Arrow - scroll up
            scroll_y = -self.keyboard_scroll_speed
        if keys[pygame.K_DOWN]:
            # Down Arrow - scroll down
            scroll_y = self.keyboard_scroll_speed
        
        # Apply scrolling (adjust for zoom to keep speed consistent)
        if scroll_x != 0 or scroll_y != 0:
            self.camera_offset[0] += scroll_x / self.camera_zoom
            self.camera_offset[1] += scroll_y / self.camera_zoom
            
            # Debug: Store that keyboard scroll is active
            self.debug_keyboard_scroll = f"Arrows: ({scroll_x}, {scroll_y})"
            
            # Enforce map bounds
            self.clamp_camera_to_bounds()
        else:
            self.debug_keyboard_scroll = None
    
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
            Zoom: 1.5 → 1.65 (zoom in)
            World pos after would be: (342, 231) without offset adjustment
            Offset adjusted to keep world pos at (300, 200)
            Result: Territory under cursor doesn't move!
        
        Phase Context:
            Part of Phase 2D camera system.
            Makes camera fully controllable (pan + zoom).
        """
        # Check if mouse is over sidebar and a scrollable tab is active
        mouse_pos = pygame.mouse.get_pos()
        sidebar_x = WINDOW_WIDTH - 250  # Sidebar position
        
        # If sidebar is expanded and mouse is over it
        if self.game_state.sidebar_expanded and mouse_pos[0] >= sidebar_x:
            active_tab = self.game_state.active_sidebar_tab
            
            # Handle scrolling for scrollable tabs
            if active_tab == 'chat':
                # Calculate approximate visible messages based on sidebar height
                sidebar_height = UIConstants.SIDEBAR_HEIGHT
                content_height = sidebar_height - UIConstants.SIDEBAR_CONTENT_PADDING  # Minus header and padding
                approx_visible = max(5, content_height // UIConstants.PIXELS_PER_MESSAGE_SCROLL)
                
                # Max scroll = total messages minus what fits on screen
                total_msgs = len(self.game_state.chat_messages)
                max_scroll = max(0, total_msgs - approx_visible)
                
                if delta > 0:  # Scroll up (see older messages)
                    self.chat_scroll_offset = min(self.chat_scroll_offset + 1, max_scroll)
                else:  # Scroll down (see newer messages)
                    self.chat_scroll_offset = max(self.chat_scroll_offset - 1, 0)
                return  # Don't zoom camera
            
            elif active_tab == 'action_log':
                # Calculate approximate visible messages based on sidebar height
                sidebar_height = UIConstants.SIDEBAR_HEIGHT
                content_height = sidebar_height - UIConstants.SIDEBAR_CONTENT_PADDING  # Minus header and padding
                approx_visible = max(5, content_height // UIConstants.PIXELS_PER_MESSAGE_SCROLL)
                
                # Max scroll = total messages minus what fits on screen
                total_msgs = len(self.game_state.messages)
                max_scroll = max(0, total_msgs - approx_visible)
                
                if delta > 0:  # Scroll up (see older messages)
                    self.action_log_scroll_offset = min(self.action_log_scroll_offset + 1, max_scroll)
                else:  # Scroll down (see newer messages)
                    self.action_log_scroll_offset = max(self.action_log_scroll_offset - 1, 0)
                return  # Don't zoom camera
        
        # Normal camera zoom behavior (when not scrolling sidebar)
        # Get mouse position before zoom
        mouse_pos = pygame.mouse.get_pos()
        world_pos_before = self.screen_to_world(mouse_pos)
        
        # Calculate new zoom level
        zoom_factor = 1.1 if delta > 0 else 0.9
        new_zoom = self.camera_zoom * zoom_factor
        
        # Clamp zoom to limits (0.5x to 2.0x)
        new_zoom = max(self.camera_min_zoom, min(self.camera_max_zoom, new_zoom))
        
        # Only update if zoom actually changed (not at limits)
        if new_zoom != self.camera_zoom:
            # Update zoom
            self.camera_zoom = new_zoom
            
            # Adjust camera offset to keep world position under cursor
            # This makes zoom feel centered on cursor
            world_pos_after = self.screen_to_world(mouse_pos)
            self.camera_offset[0] += world_pos_before[0] - world_pos_after[0]
            self.camera_offset[1] += world_pos_before[1] - world_pos_after[1]
            
            # Enforce map bounds (prevent scrolling off map after zoom)
            self.clamp_camera_to_bounds()

if __name__ == "__main__":
    game = Game()
    game.run()
