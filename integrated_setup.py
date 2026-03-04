# -*- coding: utf-8 -*-
# integrated_setup.py
# Integrated setup window with map preview and territory selection

"""
Integrated Setup Window
=======================

This module provides an integrated setup experience that combines:
- Interactive map display with territory selection
- Player configuration (Human/AI, difficulty)
- Win condition and taxation settings (placeholders)
- Launch game functionality

Replaces the old GameSetup modal dialog with a full-featured setup screen.
"""

import pygame
import sys
import map_data
from config.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT,
    WHITE, BLACK, GRAY, DARK_GRAY,
    PLAYER_COLORS, NEUTRAL_COLOR  # L3: Single source of truth for player colors
)
from utils.colors import lighten_color, brighten_color
from global_sound import sound_manager  # Global sound manager for UI clicks
from utils.logger import get_logger
from utils.cursor import draw_custom_cursor

logger = get_logger(__name__)


# ===========================================
# SETUP-SPECIFIC COLORS
# ===========================================

# L3: PLAYER_COLORS and NEUTRAL_COLOR now imported from config/constants.py
# (eliminates duplication with game_state.py)

# UI colors
PANEL_BG = (40, 40, 50)          # Dark Gray
TEXT_COLOR = (255, 255, 255)      # White
TEXT_COLOR_DIM = (180, 180, 180)  # Dim Gray
BUTTON_COLOR = (70, 120, 200)     # Blue
BUTTON_DISABLED = (100, 100, 100) # Gray
BRASS_COLOR = (181, 166, 66)      # Brass-like color for borders
PARCHMENT_COLOR = (62, 54, 38)    # Subtle parchment-like color for table cells
PARCHMENT_HOVER = (72, 64, 48)    # Slightly lighter on hover
PARCHMENT_CLICK = (92, 84, 68)    # Flash on click
RADIO_SELECTED = (100, 200, 100)  # Green
RADIO_UNSELECTED = (200, 200, 200) # Light Gray
BUTTON_HOVER_COLOR = (60, 60, 80) # Slightly lighter panel

# ===========================================
# CONFIGURATION STATE CLASS
# ===========================================

class SetupConfig:
    """
    Configuration state for game setup.

    Tracks all player settings using a table-based approach with slots.
    """

    def __init__(self):
        # Player slots (up to 4 slots, can be empty)
        # Each slot: {'active': bool, 'type': 'Human'/'AI', 'difficulty': 0-2,
        #             'color': 0-3, 'territory': None, 'team': 0-3}
        self.player_slots = [
            {'active': True, 'type': 'Human', 'difficulty': 1, 'color': 0, 'territory': None, 'team': 0},
            {'active': True, 'type': 'AI', 'difficulty': 1, 'color': 1, 'territory': None, 'team': 1},
            {'active': False, 'type': 'AI', 'difficulty': 1, 'color': 2, 'territory': None, 'team': 2},
            {'active': False, 'type': 'AI', 'difficulty': 1, 'color': 3, 'territory': None, 'team': 3}
        ]

        # Available colors (indices into PLAYER_COLORS)
        self.available_colors = ['Red', 'Blue', 'Green', 'Yellow']

        # Available teams
        self.available_teams = ['1', '2', '3', '4']

        # Difficulty options
        self.difficulty_options = ["Easy", "Medium", "Hard"]

        # Taxation level (0=0%, 1=25%, 2=50%, 3=75%, 4=100%)
        self.taxation_level = 0

        # Taxation options
        self.taxation_options = ["0% (No Tax)", "25% Tax", "50% Tax", "75% Tax", "100% Tax"]

        # Victory condition (0=Domination, 1=Capital Assault, 2=Total Conquest)
        self.victory_condition = 0

        # Victory condition options
        self.victory_options = ["Domination (45+)", "Capital Assault", "Total Conquest"]

        # Turn mode (0=Sequential, 1=Simultaneous)
        self.turn_mode = 0

        # Turn mode options
        self.turn_mode_options = ["Sequential", "Simultaneous"]

        # Turn mode tooltips
        self.turn_mode_tooltips = {
            "Sequential": "Players take turns one at a time",
            "Simultaneous": "All players plan at once, then orders execute together"
        }

    @property
    def num_players(self):
        """Get number of active players"""
        return sum(1 for slot in self.player_slots if slot['active'])

    @property
    def player_is_ai(self):
        """Legacy property: list of AI flags for active players"""
        return [slot['type'] == 'AI' for slot in self.player_slots if slot['active']]

    @property
    def player_difficulty(self):
        """Legacy property: list of difficulties for active players"""
        return [slot['difficulty'] for slot in self.player_slots if slot['active']]

    @property
    def player_territory(self):
        """Legacy property: list of territories for active players"""
        return [slot['territory'] for slot in self.player_slots if slot['active']]

    # S1 fix: Legacy property setters now write to underlying player_slots data
    # instead of writing to a temporary list from the getter (which was silently discarded).
    # Note: these setters are currently unused but kept for API compatibility.
    @property
    def player1_is_ai(self):
        return self.player_is_ai[0]

    @player1_is_ai.setter
    def player1_is_ai(self, value):
        active_slots = [s for s in self.player_slots if s['active']]
        if active_slots:
            active_slots[0]['type'] = 'AI' if value else 'Human'

    @property
    def player2_is_ai(self):
        return self.player_is_ai[1]

    @player2_is_ai.setter
    def player2_is_ai(self, value):
        active_slots = [s for s in self.player_slots if s['active']]
        if len(active_slots) > 1:
            active_slots[1]['type'] = 'AI' if value else 'Human'

    @property
    def player1_difficulty(self):
        return self.player_difficulty[0]

    @player1_difficulty.setter
    def player1_difficulty(self, value):
        active_slots = [s for s in self.player_slots if s['active']]
        if active_slots:
            active_slots[0]['difficulty'] = value

    @property
    def player2_difficulty(self):
        return self.player_difficulty[1]

    @player2_difficulty.setter
    def player2_difficulty(self, value):
        active_slots = [s for s in self.player_slots if s['active']]
        if len(active_slots) > 1:
            active_slots[1]['difficulty'] = value

    @property
    def player1_territory(self):
        return self.player_territory[0]

    @player1_territory.setter
    def player1_territory(self, value):
        active_slots = [s for s in self.player_slots if s['active']]
        if active_slots:
            active_slots[0]['territory'] = value

    @property
    def player2_territory(self):
        return self.player_territory[1]

    @player2_territory.setter
    def player2_territory(self, value):
        active_slots = [s for s in self.player_slots if s['active']]
        if len(active_slots) > 1:
            active_slots[1]['territory'] = value

    def get_active_slot_index(self, slot_index):
        """Convert slot index to active player index (skipping inactive slots)"""
        active_count = 0
        for i, slot in enumerate(self.player_slots):
            if slot['active']:
                if i == slot_index:
                    return active_count
                active_count += 1
        return None

    def can_select_territory(self, territory, slot_idx):
        """Check if slot can select this territory"""
        # Can't select territory already selected by another active player
        for i, slot in enumerate(self.player_slots):
            if i != slot_idx and slot['active'] and slot['territory'] == territory:
                return False
        return True

    def set_territory(self, slot_idx, territory):
        """Set territory for slot (or deselect if clicking own)"""
        if self.player_slots[slot_idx]['territory'] == territory:
            self.player_slots[slot_idx]['territory'] = None  # Deselect
        else:
            self.player_slots[slot_idx]['territory'] = territory

    def get_player_territory(self, active_player_idx):
        """Get territory for active player (by active index, not slot index)"""
        active_count = 0
        for slot in self.player_slots:
            if slot['active']:
                if active_count == active_player_idx:
                    return slot['territory']
                active_count += 1
        return None

    def is_color_used(self, color_idx, exclude_slot=None):
        """Check if a color is already used by another active player"""
        for i, slot in enumerate(self.player_slots):
            if i != exclude_slot and slot['active'] and slot['color'] == color_idx:
                return True
        return False

    def is_ready(self):
        """Check if configuration is ready to launch"""
        active_slots = [slot for slot in self.player_slots if slot['active']]

        # Need at least 2 active players
        if len(active_slots) < 2:
            return False

        # All active players must have selected a territory
        if any(slot['territory'] is None for slot in active_slots):
            return False

        # All territories must be unique
        territories = [slot['territory'] for slot in active_slots]
        if len(set(territories)) != len(territories):
            return False

        # All colors must be unique
        colors = [slot['color'] for slot in active_slots]
        if len(set(colors)) != len(colors):
            return False

        return True


# ===========================================
# MAP PREVIEW CLASS
# ===========================================

class MapPreview:
    """
    Map display and territory selection system for setup window.

    Renders the game map at a fixed zoom level showing all territories.
    Handles territory hover effects and click selection.
    """

    def __init__(self, screen, bounds, config):
        self.screen = screen
        self.bounds = bounds
        self.config = config

        # Load map image
        try:
            map_image_original = pygame.image.load("assets/map.png")
        except (FileNotFoundError, pygame.error, OSError):
            # Fallback if map image not found
            map_image_original = pygame.Surface((ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT))
            map_image_original.fill((50, 80, 50))  # Dark green fallback

        # Load top and bottom bar images
        try:
            self.top_bar_original = pygame.image.load("assets/TopBar.jpg")
        except (FileNotFoundError, pygame.error, OSError):
            self.top_bar_original = None

        try:
            self.bottom_bar_original = pygame.image.load("assets/BottomBar.jpg")
        except (FileNotFoundError, pygame.error, OSError):
            self.bottom_bar_original = None

        # Calculate scaling to fill horizontal space (ignore vertical - map is asymmetric)
        width_scale = bounds.width / ORIGINAL_MAP_WIDTH
        self.scale_factor = width_scale * 1.0  # 100% to maximize map size

        # Scale map image
        map_width = int(ORIGINAL_MAP_WIDTH * self.scale_factor)
        map_height = int(ORIGINAL_MAP_HEIGHT * self.scale_factor)
        self.map_image = pygame.transform.smoothscale(map_image_original, (map_width, map_height))

        # Calculate centering offset (center horizontally, vertically center in available space)
        self.offset_x = bounds.x + (bounds.width - map_width) // 2
        self.offset_y = bounds.y + (bounds.height - map_height) // 2

        # Scale and position top/bottom bars (aligned to map edges, not covering map)
        if self.top_bar_original:
            bar_width = bounds.width
            bar_height = int(self.top_bar_original.get_height() * (bar_width / self.top_bar_original.get_width()))
            # Flip the top bar 180 degrees
            scaled_bar = pygame.transform.smoothscale(self.top_bar_original, (bar_width, bar_height))
            self.top_bar = pygame.transform.rotate(scaled_bar, 180)
            # Position bottom of top bar at top edge of map
            self.top_bar_rect = pygame.Rect(bounds.x, self.offset_y - bar_height, bar_width, bar_height)
        else:
            self.top_bar = None

        if self.bottom_bar_original:
            bar_width = bounds.width
            bar_height = int(self.bottom_bar_original.get_height() * (bar_width / self.bottom_bar_original.get_width()))
            self.bottom_bar = pygame.transform.smoothscale(self.bottom_bar_original, (bar_width, bar_height))
            # Position top of bottom bar at bottom edge of map
            self.bottom_bar_rect = pygame.Rect(bounds.x, self.offset_y + map_height, bar_width, bar_height)
        else:
            self.bottom_bar = None

        # Scale polygons
        self.scaled_polygons = {}
        for territory, polygon in map_data.TERRITORY_POLYGONS.items():
            self.scaled_polygons[territory] = [
                (int(x * self.scale_factor + self.offset_x),
                 int(y * self.scale_factor + self.offset_y))
                for x, y in polygon
            ]

        # Territory state
        self.hovered_territory = None
        self.click_feedback_territory = None
        self.click_feedback_timer = 0.0

    def update(self, dt):
        """Update animations"""
        if self.click_feedback_timer > 0:
            self.click_feedback_timer -= dt
            if self.click_feedback_timer <= 0:
                self.click_feedback_territory = None

    def _get_territory_at_screen_pos(self, pos):
        """Find which territory contains the given screen position"""
        # Check territories in reverse order (same as map_data.get_territory_at_position)
        for territory in reversed(list(self.scaled_polygons.keys())):
            polygon = self.scaled_polygons[territory]
            if map_data.point_in_polygon(pos, polygon):
                return territory
        return None

    def update_hover(self, mouse_pos):
        """Update hover state"""
        if not self.bounds.collidepoint(mouse_pos):
            self.hovered_territory = None
            return

        # Find territory at screen position using scaled polygons
        self.hovered_territory = self._get_territory_at_screen_pos(mouse_pos)

    def handle_territory_click(self, pos):
        """Handle click on map territory"""
        if not self.bounds.collidepoint(pos):
            return False

        # Find territory at screen position using scaled polygons
        territory = self._get_territory_at_screen_pos(pos)

        if territory:
            # Find which slot to assign this to
            slot_idx = None

            # First, check if clicking on an already selected territory (for deselection)
            for i, slot in enumerate(self.config.player_slots):
                if slot['active'] and slot['territory'] == territory:
                    slot_idx = i
                    break

            # If not clicking on selected territory, find next active slot without territory
            if slot_idx is None:
                for i, slot in enumerate(self.config.player_slots):
                    if slot['active'] and slot['territory'] is None:
                        slot_idx = i
                        break

            # If all active slots have territories, do nothing
            if slot_idx is None:
                return False

            # Validate and set territory
            if self.config.can_select_territory(territory, slot_idx):
                sound_manager.play_ui_click()
                self.config.set_territory(slot_idx, territory)
                self.click_feedback_territory = territory
                self.click_feedback_timer = 0.15  # 150ms flash
                return True

        return False

    def render(self):
        """Render map preview with territory overlays"""
        # Draw map background
        self.screen.blit(self.map_image, (self.offset_x, self.offset_y))

        # Draw territory overlays for selected territories (by slot)
        for slot in self.config.player_slots:
            if slot['active'] and slot['territory']:
                territory = slot['territory']
                if territory in self.scaled_polygons:
                    polygon = self.scaled_polygons[territory]
                    color = PLAYER_COLORS[slot['color']]

                    # Click feedback (brighter)
                    if territory == self.click_feedback_territory and self.click_feedback_timer > 0:
                        self._draw_territory_overlay(polygon, brighten_color(color, 0.4), alpha=120)
                    else:
                        self._draw_territory_overlay(polygon, color, alpha=80)

        # Draw hover highlight
        if self.hovered_territory and self.hovered_territory in self.scaled_polygons:
            polygon = self.scaled_polygons[self.hovered_territory]

            # Determine hover color based on ownership
            color = NEUTRAL_COLOR
            for slot in self.config.player_slots:
                if slot['active'] and self.hovered_territory == slot['territory']:
                    color = PLAYER_COLORS[slot['color']]
                    break

            self._draw_territory_overlay(polygon, color, alpha=60, outline=True)

        # Draw selection borders (thick borders for selected territories)
        for slot in self.config.player_slots:
            if slot['active'] and slot['territory']:
                territory = slot['territory']
                if territory in self.scaled_polygons:
                    polygon = self.scaled_polygons[territory]
                    color = PLAYER_COLORS[slot['color']]
                    pygame.draw.lines(self.screen, color, True, polygon, 4)

        # Draw top and bottom bars
        if self.top_bar:
            self.screen.blit(self.top_bar, self.top_bar_rect)
        if self.bottom_bar:
            self.screen.blit(self.bottom_bar, self.bottom_bar_rect)

    def _draw_territory_overlay(self, polygon, color, alpha=100, outline=False):
        """Draw semi-transparent overlay on territory"""
        # P4 fix: reuse cached SRCALPHA overlay surface instead of creating new one each call
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        if not hasattr(self, '_cached_overlay') or self._cached_overlay is None or self._cached_overlay.get_size() != (screen_width, screen_height):
            self._cached_overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
        else:
            self._cached_overlay.fill((0, 0, 0, 0))
        overlay = self._cached_overlay

        # Draw filled polygon
        pygame.draw.polygon(overlay, (*color, alpha), polygon)

        # Draw outline if requested
        if outline:
            pygame.draw.lines(overlay, (*color, 255), True, polygon, 3)

        # Blit to screen
        self.screen.blit(overlay, (0, 0))


# ===========================================
# CONFIG PANEL CLASS
# ===========================================

class ConfigPanel:
    """
    Left panel UI for game configuration.

    Manages all configuration widgets: radio buttons, dropdowns,
    and action buttons.
    """

    def __init__(self, screen, bounds, config):
        self.screen = screen
        self.bounds = bounds
        self.config = config

        # Load left panel background image
        try:
            left_panel_original = pygame.image.load("assets/LeftPanel.png")
            # Scale to fit the panel bounds (match height, scale width proportionally)
            panel_height = bounds.height
            panel_width = bounds.width
            # Scale to fill entire panel
            self.left_panel_bg = pygame.transform.smoothscale(left_panel_original, (panel_width, panel_height))
        except (FileNotFoundError, pygame.error, OSError):
            self.left_panel_bg = None

        # Load table border image
        try:
            self.table_border_original = pygame.image.load("assets/TableBorder.png")
        except (FileNotFoundError, pygame.error, OSError):
            self.table_border_original = None
        self.table_border = None
        self.table_border_rect = None

        # Load button background (same as Main Menu)
        try:
            self.button_bg_image = pygame.image.load('assets/MainMenuButtonNew.png').convert_alpha()
        except Exception as e:
            logger.warning(f"Error loading button background: {e}")
            self.button_bg_image = None

        # Fonts
        try:
            self.title_font = pygame.font.Font(None, 48)
            self.header_font = pygame.font.Font(None, 32)
            self.label_font = pygame.font.Font(None, 24)
            self.button_font = pygame.font.Font(None, 28)
        except (FileNotFoundError, pygame.error, OSError):
            self.title_font = pygame.font.SysFont('arial', 48, bold=True)
            self.header_font = pygame.font.SysFont('arial', 32, bold=True)
            self.label_font = pygame.font.SysFont('arial', 24)
            self.button_font = pygame.font.SysFont('arial', 28)

        # UI state
        self.hovered_element = None
        self.clicked_element = None

        # Dropdown state
        self.active_dropdown = None  # Which dropdown is open: 'slot0_player', 'slot1_color', etc.
        self.hovered_dropdown_item = None  # Which item in the dropdown is hovered

        # Layout
        self._calculate_layout()

    def _calculate_layout(self):
        """Calculate positions for all UI elements - TABLE LAYOUT"""
        # Scale-aware calculations
        panel_width = self.bounds.width
        panel_height = self.bounds.height

        # Base measurements at 1600x900 (reference resolution)
        base_panel_width = 560  # 35% of 1600
        scale = panel_width / base_panel_width

        # Margins and border - use smaller fixed border to maximize table space
        border_thickness = 70  # Fixed for consistent ornate border appearance
        base_margin = int(8 * scale)  # Very minimal scaled margin for maximum table width

        # Total margin includes border thickness
        margin = base_margin + border_thickness

        self.ui_elements = {}
        y = int(20 * scale)

        # Title (centered within ornate border)
        title_height = int(40 * scale)
        self.ui_elements['title'] = pygame.Rect(margin, y, panel_width - 2*margin, title_height)
        y += int(50 * scale)

        # Table header
        table_y = y + int(20 * scale)  # Add padding at top (increased from 10 to 20px - moved 10px down)
        header_row_height = int(37 * scale)  # Header row height (reduced from 40 by 3px)
        row_height = int(45 * scale)  # Data row height (8px taller than header - additional 5px increase)

        # Calculate available space for table content
        available_width = panel_width - 2 * margin

        # Reserve space for border padding (moderate to fit within stretched border)
        border_padding_horizontal = int(12 * scale)
        usable_width = available_width - (2 * border_padding_horizontal)

        # Column spacing
        col_spacing = int(10 * scale)  # Good spacing for column separation
        spacing_total = 4 * col_spacing

        # Calculate column widths using proportional distribution
        # Reference proportions from 1600x900: 58:83:76:153:67 (total 437)
        # This ensures columns scale proportionally and fit within available space
        total_proportion = 437.0
        columns_width = usable_width - spacing_total

        col_active_w = int(columns_width * 58.0 / total_proportion)
        col_player_w = int(columns_width * 83.0 / total_proportion)
        col_color_w = int(columns_width * 76.0 / total_proportion)
        col_territory_w = int(columns_width * 153.0 / total_proportion)
        col_team_w = int(columns_width * 67.0 / total_proportion)

        # Calculate total table width
        total_col_width = col_active_w + col_player_w + col_color_w + col_territory_w + col_team_w + spacing_total

        # Center table within the available space
        table_start_x = margin + (available_width - total_col_width) // 2

        col_active_x = table_start_x
        col_player_x = col_active_x + col_active_w + col_spacing
        col_color_x = col_player_x + col_player_w + col_spacing
        col_territory_x = col_color_x + col_color_w + col_spacing
        col_team_x = col_territory_x + col_territory_w + col_spacing

        # Store column positions for rendering
        self.table_cols = {
            'active': (col_active_x, col_active_w),
            'player': (col_player_x, col_player_w),
            'color': (col_color_x, col_color_w),
            'territory': (col_territory_x, col_territory_w),
            'team': (col_team_x, col_team_w)
        }

        # Header row (centered)
        table_width = total_col_width
        table_left = table_start_x
        self.ui_elements['table_header'] = pygame.Rect(table_left, table_y, table_width, header_row_height)
        y = table_y + header_row_height

        # Scaled element sizes
        checkbox_size = int(20 * scale)
        checkbox_offset_x = int(10 * scale)
        checkbox_offset_y = (row_height - checkbox_size) // 2
        cell_padding = int(5 * scale)

        # Player slot rows (4 rows)
        # Add 6px gap between header and first row
        header_to_rows_gap = int(6 * scale)
        self.header_to_rows_gap = header_to_rows_gap  # Store for use in rendering
        for i in range(4):
            row_y = y + header_to_rows_gap + i * row_height

            # Active checkbox (centered vertically in scaled row)
            self.ui_elements[f'slot{i}_active'] = pygame.Rect(
                col_active_x + checkbox_offset_x,
                row_y + checkbox_offset_y,
                checkbox_size,
                checkbox_size
            )

            # Player type dropdown (Human/AI + difficulty)
            self.ui_elements[f'slot{i}_player'] = pygame.Rect(
                col_player_x,
                row_y + cell_padding,
                col_player_w,
                row_height - 2*cell_padding
            )

            # Color dropdown
            self.ui_elements[f'slot{i}_color'] = pygame.Rect(
                col_color_x,
                row_y + cell_padding,
                col_color_w,
                row_height - 2*cell_padding
            )

            # Territory display (non-interactive)
            self.ui_elements[f'slot{i}_territory'] = pygame.Rect(
                col_territory_x,
                row_y + cell_padding,
                col_territory_w,
                row_height - 2*cell_padding
            )

            # Team dropdown
            self.ui_elements[f'slot{i}_team'] = pygame.Rect(
                col_team_x,
                row_y + cell_padding,
                col_team_w,
                row_height - 2*cell_padding
            )

        y += 4 * row_height + int(30 * scale)  # Add scaled bottom padding

        # Taxation dropdown (below table, above buttons)
        taxation_label_height = int(25 * scale)
        taxation_dropdown_height = int(40 * scale)
        taxation_y = y + int(60 * scale)  # 60px gap from table (moved down 50px from original 10px)

        self.ui_elements['taxation_label'] = pygame.Rect(margin, taxation_y, panel_width - 2*margin, taxation_label_height)
        self.ui_elements['taxation_dropdown'] = pygame.Rect(margin, taxation_y + taxation_label_height + int(5 * scale),
                                                             panel_width - 2*margin, taxation_dropdown_height)

        y = taxation_y + taxation_label_height + taxation_dropdown_height + int(20 * scale)  # Update y position

        # Victory condition dropdown (below taxation dropdown, above buttons)
        victory_label_height = int(25 * scale)
        victory_dropdown_height = int(40 * scale)
        victory_y = y + int(10 * scale)  # 10px gap from taxation

        self.ui_elements['victory_label'] = pygame.Rect(margin, victory_y, panel_width - 2*margin, victory_label_height)
        self.ui_elements['victory_dropdown'] = pygame.Rect(margin, victory_y + victory_label_height + int(5 * scale),
                                                            panel_width - 2*margin, victory_dropdown_height)

        y = victory_y + victory_label_height + victory_dropdown_height + int(20 * scale)  # Update y position

        # Turn mode dropdown (below victory condition dropdown, above buttons)
        turn_mode_label_height = int(25 * scale)
        turn_mode_dropdown_height = int(40 * scale)
        turn_mode_y = y + int(10 * scale)  # 10px gap from victory

        self.ui_elements['turn_mode_label'] = pygame.Rect(margin, turn_mode_y, panel_width - 2*margin, turn_mode_label_height)
        self.ui_elements['turn_mode_dropdown'] = pygame.Rect(margin, turn_mode_y + turn_mode_label_height + int(5 * scale),
                                                              panel_width - 2*margin, turn_mode_dropdown_height)

        y = turn_mode_y + turn_mode_label_height + turn_mode_dropdown_height + int(20 * scale)  # Update y position

        # Buttons (bottom of panel, positioned using base_margin to align with border)
        # 33% taller: 50 * 1.33 ≈ 67
        button_height = int(67 * scale)
        button_spacing = int(80 * scale)  # Increased from 60 to 80 for more space between buttons
        button_y = panel_height - int(167 * scale)  # Adjusted for taller buttons and increased spacing
        self.ui_elements['launch_button'] = pygame.Rect(margin, button_y, panel_width - 2*margin, button_height)
        button_y += button_spacing
        self.ui_elements['return_button'] = pygame.Rect(margin, button_y, panel_width - 2*margin, button_height)

        # Calculate table border position and size (as outer shell)
        if self.table_border_original:
            # Table spans from header to last row (include top padding)
            table_top = table_y  # Use table_y instead of header.y to include top padding
            # Calculate actual table dimensions based on header and rows
            # Add extra internal padding to fill ornate border gaps: 8px top, 18px bottom
            # Include header-to-rows gap
            actual_table_height = header_row_height + header_to_rows_gap + (4 * row_height) + int(10 * scale) + int(8 * scale) + int(18 * scale)  # Header + gap + 4 rows + bottom padding + extra padding

            # Border padding to create shell effect (border sits outside table)
            border_padding_horizontal = int(2 * scale)  # Extremely minimal horizontal padding
            border_padding_vertical = int(18 * scale)  # More space on top/bottom

            # Border dimensions include padding on all sides
            border_width = total_col_width + (2 * border_padding_horizontal)
            border_height = actual_table_height + (2 * border_padding_vertical)
            border_x = table_start_x - border_padding_horizontal  # Move border left
            border_y = table_top - border_padding_vertical  # Move border up

            # Scale border to match table dimensions plus padding
            # Use non-uniform scaling to make border wider without making it taller
            # Stretch horizontally by 1.15x to accommodate wider table
            stretched_border_width = int(border_width * 1.15)
            self.table_border = pygame.transform.smoothscale(self.table_border_original, (stretched_border_width, border_height))
            # Center the stretched border over the table
            border_x_centered = border_x - (stretched_border_width - border_width) // 2
            self.table_border_rect = pygame.Rect(border_x_centered, border_y, stretched_border_width, border_height)

        # Store scale for font sizing
        self.ui_scale = scale

    def update_hover(self, mouse_pos):
        """Update hover state"""
        if not self.bounds.collidepoint(mouse_pos):
            self.hovered_element = None
            self.hovered_dropdown_item = None
            return

        # If a dropdown is active, check if hovering over dropdown items first
        if self.active_dropdown:
            dropdown_items = self._get_dropdown_items_rects(self.active_dropdown)
            for i, item_rect in enumerate(dropdown_items):
                if item_rect.collidepoint(mouse_pos):
                    self.hovered_dropdown_item = i
                    self.hovered_element = None
                    return

        # Not hovering over dropdown items
        self.hovered_dropdown_item = None

        # Check all interactive elements
        for element_name, rect in self.ui_elements.items():
            if rect.collidepoint(mouse_pos):
                # Skip non-interactive elements
                if 'title' in element_name or 'table_header' in element_name:
                    continue

                # Territory is read-only (set by clicking map)
                if 'territory' in element_name:
                    continue

                self.hovered_element = element_name
                return

        self.hovered_element = None

    def handle_click(self, pos):
        """Handle click on UI element - TABLE VERSION"""
        if not self.bounds.collidepoint(pos):
            # Click outside panel - close any open dropdown
            if self.active_dropdown:
                self.active_dropdown = None
                return 'config_changed'
            return None

        # If a dropdown is active, check if clicking on dropdown items
        if self.active_dropdown:
            dropdown_items = self._get_dropdown_items_rects(self.active_dropdown)
            for i, item_rect in enumerate(dropdown_items):
                if item_rect.collidepoint(pos):
                    # User clicked on dropdown item - apply selection
                    sound_manager.play_ui_click()
                    self._apply_dropdown_selection(self.active_dropdown, i)
                    self.active_dropdown = None
                    return 'config_changed'

            # Check if clicking on the dropdown button itself (toggle close)
            if self.active_dropdown == 'taxation':
                button_key = 'taxation_dropdown'
                if button_key in self.ui_elements and self.ui_elements[button_key].collidepoint(pos):
                    # Toggle close the dropdown
                    self.active_dropdown = None
                    return None
            elif self.active_dropdown == 'victory':
                button_key = 'victory_dropdown'
                if button_key in self.ui_elements and self.ui_elements[button_key].collidepoint(pos):
                    # Toggle close the dropdown
                    self.active_dropdown = None
                    return None
            elif self.active_dropdown == 'turn_mode':
                button_key = 'turn_mode_dropdown'
                if button_key in self.ui_elements and self.ui_elements[button_key].collidepoint(pos):
                    # Toggle close the dropdown
                    self.active_dropdown = None
                    return None
            else:
                slot_idx = int(self.active_dropdown.split('_')[0].replace('slot', ''))
                dropdown_type = self.active_dropdown.split('_')[1]
                button_key = f'slot{slot_idx}_{dropdown_type}'

                if button_key in self.ui_elements and self.ui_elements[button_key].collidepoint(pos):
                    # Toggle close the dropdown
                    self.active_dropdown = None
                    return None

            # Click somewhere else - close dropdown
            self.active_dropdown = None
            return None

        # Check what was clicked
        for element_name, rect in self.ui_elements.items():
            if rect.collidepoint(pos):
                self.clicked_element = element_name

                # Handle slot checkboxes
                for i in range(4):
                    if element_name == f'slot{i}_active':
                        sound_manager.play_ui_click()
                        # Toggle active state
                        self.config.player_slots[i]['active'] = not self.config.player_slots[i]['active']

                        if not self.config.player_slots[i]['active']:
                            # If deactivating, clear territory selection
                            self.config.player_slots[i]['territory'] = None
                        else:
                            # If activating, assign first available unused color
                            current_color = self.config.player_slots[i]['color']
                            if self.config.is_color_used(current_color, exclude_slot=i):
                                # Current color is in use, find first available
                                for color_idx in range(4):
                                    if not self.config.is_color_used(color_idx, exclude_slot=i):
                                        self.config.player_slots[i]['color'] = color_idx
                                        break
                        return 'config_changed'

                    # Handle player type/difficulty dropdown (only if active)
                    elif element_name == f'slot{i}_player':
                        if self.config.player_slots[i]['active']:
                            sound_manager.play_ui_click()
                            self.active_dropdown = f'slot{i}_player'
                        return None

                    # Handle color dropdown (only if active)
                    elif element_name == f'slot{i}_color':
                        if self.config.player_slots[i]['active']:
                            sound_manager.play_ui_click()
                            self.active_dropdown = f'slot{i}_color'
                        return None

                    # Handle team dropdown (only if active)
                    elif element_name == f'slot{i}_team':
                        if self.config.player_slots[i]['active']:
                            sound_manager.play_ui_click()
                            self.active_dropdown = f'slot{i}_team'
                        return None

                # Handle taxation dropdown
                if element_name == 'taxation_dropdown':
                    sound_manager.play_ui_click()
                    self.active_dropdown = 'taxation'
                    return None

                # Handle victory condition dropdown
                if element_name == 'victory_dropdown':
                    sound_manager.play_ui_click()
                    self.active_dropdown = 'victory'
                    return None

                # Handle turn mode dropdown
                if element_name == 'turn_mode_dropdown':
                    sound_manager.play_ui_click()
                    self.active_dropdown = 'turn_mode'
                    return None

                # Handle buttons
                if element_name == 'return_button':
                    sound_manager.play_ui_click()
                    return 'cancel'
                elif element_name == 'launch_button':
                    if self.config.is_ready():
                        sound_manager.play_ui_click()
                        return 'launch'
                    return None

        return None

    def _get_dropdown_items_rects(self, dropdown_id):
        """Get list of rectangles for dropdown menu items"""
        # Handle taxation dropdown separately
        if dropdown_id == 'taxation':
            button_rect = self.ui_elements['taxation_dropdown']
            menu_x = button_rect.x
            menu_y = button_rect.bottom
            item_width = button_rect.width
            item_height = int(30 * self.ui_scale)  # Slightly taller for readability
            items = self.config.taxation_options

            # Create rectangles for each item
            item_rects = []
            for i, item in enumerate(items):
                item_rect = pygame.Rect(menu_x, menu_y + i * item_height, item_width, item_height)
                item_rects.append(item_rect)
            return item_rects

        # Handle victory condition dropdown separately
        if dropdown_id == 'victory':
            button_rect = self.ui_elements['victory_dropdown']
            menu_x = button_rect.x
            menu_y = button_rect.bottom
            item_width = button_rect.width
            item_height = int(30 * self.ui_scale)  # Slightly taller for readability
            items = self.config.victory_options

            # Create rectangles for each item
            item_rects = []
            for i, item in enumerate(items):
                item_rect = pygame.Rect(menu_x, menu_y + i * item_height, item_width, item_height)
                item_rects.append(item_rect)
            return item_rects

        # Handle turn mode dropdown separately
        if dropdown_id == 'turn_mode':
            button_rect = self.ui_elements['turn_mode_dropdown']
            menu_x = button_rect.x
            menu_y = button_rect.bottom
            item_width = button_rect.width
            item_height = int(30 * self.ui_scale)  # Slightly taller for readability
            items = self.config.turn_mode_options

            # Create rectangles for each item
            item_rects = []
            for i, item in enumerate(items):
                item_rect = pygame.Rect(menu_x, menu_y + i * item_height, item_width, item_height)
                item_rects.append(item_rect)
            return item_rects

        # Parse dropdown_id: 'slot0_player', 'slot1_color', etc.
        slot_idx = int(dropdown_id.split('_')[0].replace('slot', ''))
        dropdown_type = dropdown_id.split('_')[1]

        # Get the button rectangle
        button_rect = self.ui_elements[dropdown_id]

        # Calculate dropdown menu position (below button, scaled)
        menu_x = button_rect.x
        menu_y = button_rect.bottom
        item_width = button_rect.width
        item_height = int(25 * self.ui_scale)

        # Get items based on dropdown type
        if dropdown_type == 'player':
            # Use profile name from settings for human player option
            from settings_manager import settings
            player_name = settings.get_player_name()

            # Check if another slot already has Human selected
            human_available = True
            for i, other_slot in enumerate(self.config.player_slots):
                if i != slot_idx and other_slot['active'] and other_slot['type'] == 'Human':
                    human_available = False
                    break

            # Only include Human option if it's available or this slot already has it
            if human_available or self.config.player_slots[slot_idx]['type'] == 'Human':
                items = [player_name, 'AI (Easy)', 'AI (Medium)', 'AI (Hard)']
            else:
                items = ['AI (Easy)', 'AI (Medium)', 'AI (Hard)']
        elif dropdown_type == 'color':
            # Only show colors not used by other active players
            items = []
            for color_idx, color_name in enumerate(self.config.available_colors):
                if not self.config.is_color_used(color_idx, exclude_slot=slot_idx):
                    items.append(color_name)
        elif dropdown_type == 'team':
            items = self.config.available_teams
        else:
            items = []

        # Create rectangles for each item
        item_rects = []
        for i, item in enumerate(items):
            item_rect = pygame.Rect(menu_x, menu_y + i * item_height, item_width, item_height)
            item_rects.append(item_rect)

        return item_rects

    def _apply_dropdown_selection(self, dropdown_id, item_index):
        """Apply the selected dropdown item"""
        # Handle taxation dropdown separately
        if dropdown_id == 'taxation':
            self.config.taxation_level = item_index
            return

        # Handle victory condition dropdown separately
        if dropdown_id == 'victory':
            self.config.victory_condition = item_index
            return

        # Handle turn mode dropdown separately
        if dropdown_id == 'turn_mode':
            self.config.turn_mode = item_index
            return

        # Parse dropdown_id
        slot_idx = int(dropdown_id.split('_')[0].replace('slot', ''))
        dropdown_type = dropdown_id.split('_')[1]
        slot = self.config.player_slots[slot_idx]

        if dropdown_type == 'player':
            # Use profile name from settings for human player option
            from settings_manager import settings
            player_name = settings.get_player_name()

            # Check if another slot already has Human selected
            human_available = True
            for i, other_slot in enumerate(self.config.player_slots):
                if i != slot_idx and other_slot['active'] and other_slot['type'] == 'Human':
                    human_available = False
                    break

            # Build items list based on human availability
            if human_available or self.config.player_slots[slot_idx]['type'] == 'Human':
                items = [player_name, 'AI (Easy)', 'AI (Medium)', 'AI (Hard)']
            else:
                items = ['AI (Easy)', 'AI (Medium)', 'AI (Hard)']

            selected = items[item_index]

            # Check if selected item is the human player option
            if selected == player_name:
                # Double-check that human is still available (shouldn't happen, but be safe)
                for i, other_slot in enumerate(self.config.player_slots):
                    if i != slot_idx and other_slot['active'] and other_slot['type'] == 'Human':
                        # Another active slot is already Human - don't allow this change
                        return
                slot['type'] = 'Human'
            else:
                # It's an AI option
                slot['type'] = 'AI'
                if 'Easy' in selected:
                    slot['difficulty'] = 0
                elif 'Medium' in selected:
                    slot['difficulty'] = 1
                elif 'Hard' in selected:
                    slot['difficulty'] = 2

        elif dropdown_type == 'color':
            # Get available colors
            available_colors = []
            for color_idx in range(4):
                if not self.config.is_color_used(color_idx, exclude_slot=slot_idx):
                    available_colors.append(color_idx)
            if item_index < len(available_colors):
                slot['color'] = available_colors[item_index]

        elif dropdown_type == 'team':
            slot['team'] = item_index

    def render(self):
        """Render config panel - TABLE VERSION"""
        # Draw background image or fallback color
        if self.left_panel_bg:
            self.screen.blit(self.left_panel_bg, (self.bounds.x, self.bounds.y))
        else:
            pygame.draw.rect(self.screen, PANEL_BG, self.bounds)

        # Draw right border separator
        pygame.draw.line(self.screen, GRAY, (self.bounds.right, 0), (self.bounds.right, self.bounds.height), 2)

        # Title (scaled font, Cinzel SemiBold)
        title_font_size = max(24, int(48 * self.ui_scale))
        title_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', title_font_size)
        title_text = title_font.render("Game Setup", True, TEXT_COLOR)
        title_rect = title_text.get_rect(center=(self.bounds.centerx, self.ui_elements['title'].centery))
        self.screen.blit(title_text, title_rect)

        # Draw table
        self._draw_table()

        # Taxation dropdown (below table)
        self._draw_taxation_section()

        # Victory condition dropdown (below taxation)
        self._draw_victory_section()

        # Turn mode dropdown (below victory condition)
        self._draw_turn_mode_section()

        # Buttons
        self._draw_button('return_button', "Return to Main Menu", enabled=True)
        self._draw_button('launch_button', "Launch Game", enabled=self.config.is_ready())

        # Draw active dropdown on top of everything
        if self.active_dropdown:
            self._draw_dropdown_menu()

    def _draw_table(self):
        """Draw the player configuration table"""
        # Draw table border first (as outer shell)
        if self.table_border and self.table_border_rect:
            self.screen.blit(self.table_border, self.table_border_rect)

        # Get header rect (needed for both parchment and header drawing)
        header_rect = self.ui_elements['table_header']

        # Draw parchment background for entire table area (inside border)
        # Calculate based on border position to fill completely to the border edges
        if self.table_border_rect:
            # Use border's inner area (accounting for border padding)
            # Reduce padding by 6px on top and bottom to close gaps with ornate border
            border_padding_horizontal = int(12 * self.ui_scale)
            border_padding_vertical = int(18 * self.ui_scale) - int(6 * self.ui_scale)  # Reduce by 6px

            parchment_left = self.table_border_rect.left + border_padding_horizontal
            parchment_top = self.table_border_rect.top + border_padding_vertical
            parchment_width = self.table_border_rect.width - (2 * border_padding_horizontal)
            parchment_height = self.table_border_rect.height - (2 * border_padding_vertical)

            table_area_rect = pygame.Rect(parchment_left, parchment_top, parchment_width, parchment_height)
            pygame.draw.rect(self.screen, PARCHMENT_COLOR, table_area_rect)
        else:
            # Fallback if border not available
            parchment_top = header_rect.top - int(8 * self.ui_scale)
            table_area_height = header_rect.height + 4 * (self.ui_elements['slot0_player'].height + int(10 * self.ui_scale)) + int(8 * self.ui_scale) + int(18 * self.ui_scale)
            table_area_rect = pygame.Rect(header_rect.left, parchment_top, header_rect.width, table_area_height)
            pygame.draw.rect(self.screen, PARCHMENT_COLOR, table_area_rect)

        # Table header (no outer border - only separator line below)

        # Header labels (scaled font, moved 5px lower, Cinzel SemiBold, reduced size)
        headers = [('Active', 'active'), ('Player', 'player'), ('Color', 'color'), ('Territory', 'territory'), ('Team', 'team')]
        font_size = max(12, int(16 * self.ui_scale))  # Increased minimum for readability
        small_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', font_size)
        header_text_offset = int(5 * self.ui_scale)  # Move text 5px lower

        for label, col_key in headers:
            col_x, col_w = self.table_cols[col_key]
            text = small_font.render(label, True, TEXT_COLOR)
            text_rect = text.get_rect(center=(col_x + col_w // 2, header_rect.centery + header_text_offset))
            self.screen.blit(text, text_rect)

        # Thick separator line between header and rows (brass color)
        separator_y = header_rect.bottom
        pygame.draw.line(self.screen, BRASS_COLOR,
                        (header_rect.left, separator_y),
                        (header_rect.right, separator_y), 2)

        # Player rows
        for i in range(4):
            self._draw_player_row(i)

    def _draw_player_row(self, slot_idx):
        """Draw a single player slot row in the table"""
        slot = self.config.player_slots[slot_idx]

        # Get actual row dimensions from UI elements
        header_rect = self.ui_elements['table_header']
        first_cell = self.ui_elements[f'slot{slot_idx}_player']
        row_height = first_cell.height + int(10 * self.ui_scale)  # Cell height + padding
        row_y = self.ui_elements['table_header'].bottom + self.header_to_rows_gap + slot_idx * row_height

        # Row separator line (only horizontal line at bottom of each row except last)
        # No outer borders on sides or bottom of table

        # Dim the row if inactive
        alpha_mod = 1.0 if slot['active'] else 0.4

        # Active checkbox
        checkbox_rect = self.ui_elements[f'slot{slot_idx}_active']
        hovered = (self.hovered_element == f'slot{slot_idx}_active')
        self._draw_checkbox(checkbox_rect, slot['active'], hovered)

        # Player type/difficulty cell
        player_rect = self.ui_elements[f'slot{slot_idx}_player']
        hovered = (self.hovered_element == f'slot{slot_idx}_player') and slot['active']
        if slot['active']:
            if slot['type'] == 'Human':
                # Use profile name from settings
                from settings_manager import settings
                player_text = settings.get_player_name()
            else:
                diff_name = self.config.difficulty_options[slot['difficulty']]
                player_text = f"AI ({diff_name})"
        else:
            player_text = "-"
        self._draw_table_cell(player_rect, player_text, hovered, alpha_mod, clickable=slot['active'])

        # Color cell
        color_rect = self.ui_elements[f'slot{slot_idx}_color']
        hovered = (self.hovered_element == f'slot{slot_idx}_color') and slot['active']
        if slot['active']:
            color_value = PLAYER_COLORS[slot['color']]
            self._draw_color_cell(color_rect, color_value, hovered, alpha_mod)
        else:
            self._draw_table_cell(color_rect, "-", False, alpha_mod, clickable=False)

        # Territory cell (read-only)
        territory_rect = self.ui_elements[f'slot{slot_idx}_territory']
        if slot['active']:
            territory_text = slot['territory'] if slot['territory'] else "-"
            if len(territory_text) > 20:
                territory_text = territory_text[:17] + "..."
        else:
            territory_text = "-"
        self._draw_table_cell(territory_rect, territory_text, False, alpha_mod, clickable=False)

        # Team cell
        team_rect = self.ui_elements[f'slot{slot_idx}_team']
        hovered = (self.hovered_element == f'slot{slot_idx}_team') and slot['active']
        if slot['active']:
            team_text = self.config.available_teams[slot['team']]
        else:
            team_text = "-"
        self._draw_table_cell(team_rect, team_text, hovered, alpha_mod, clickable=slot['active'])

    def _draw_checkbox(self, rect, checked, hovered):
        """Draw a checkbox"""
        # Background
        bg_color = lighten_color(PANEL_BG, 0.3) if hovered else lighten_color(PANEL_BG, 0.1)
        pygame.draw.rect(self.screen, bg_color, rect, border_radius=3)
        pygame.draw.rect(self.screen, TEXT_COLOR, rect, 1, border_radius=3)

        # Checkmark
        if checked:
            # Draw an X mark
            pygame.draw.line(self.screen, RADIO_SELECTED, (rect.x + 4, rect.y + 4), (rect.right - 4, rect.bottom - 4), 2)
            pygame.draw.line(self.screen, RADIO_SELECTED, (rect.right - 4, rect.y + 4), (rect.x + 4, rect.bottom - 4), 2)

    def _fit_text_to_width(self, text, font, max_width):
        """Fit text to width by trying smaller font or truncating"""
        # Try rendering with current font
        text_surface = font.render(text, True, TEXT_COLOR)
        if text_surface.get_width() <= max_width:
            return text

        # Try abbreviations for common AI difficulty text
        abbreviations = {
            'AI (Easy)': 'AI Easy',
            'AI (Medium)': 'AI Med',
            'AI (Hard)': 'AI Hard'
        }

        if text in abbreviations:
            abbrev_text = abbreviations[text]
            abbrev_surface = font.render(abbrev_text, True, TEXT_COLOR)
            if abbrev_surface.get_width() <= max_width:
                return abbrev_text

        # If still too wide, truncate with ellipsis
        truncated = text
        while len(truncated) > 3:
            truncated = truncated[:-1]
            test_text = truncated + "..."
            test_surface = font.render(test_text, True, TEXT_COLOR)
            if test_surface.get_width() <= max_width:
                return test_text

        return "..."

    def _draw_table_cell(self, rect, text, hovered, alpha_mod=1.0, clickable=True):
        """Draw a table cell with text"""
        # Subtle parchment background with hover/click states
        if clickable:
            if self.clicked_element and rect.collidepoint(pygame.mouse.get_pos()):
                bg_color = tuple(int(c * alpha_mod) for c in PARCHMENT_CLICK)
            elif hovered:
                bg_color = tuple(int(c * alpha_mod) for c in PARCHMENT_HOVER)
            else:
                bg_color = tuple(int(c * alpha_mod) for c in PARCHMENT_COLOR)
        else:
            # For inactive cells, use exact parchment color (no dimming)
            bg_color = PARCHMENT_COLOR

        pygame.draw.rect(self.screen, bg_color, rect, border_radius=3)

        # Brass border
        brass_color_dimmed = tuple(int(c * alpha_mod) for c in BRASS_COLOR)
        pygame.draw.rect(self.screen, brass_color_dimmed, rect, 1, border_radius=3)

        # Text (scaled font, Cinzel Regular, further reduced size)
        text_color = tuple(int(c * alpha_mod) for c in TEXT_COLOR)
        font_size = max(10, int(11 * self.ui_scale))  # Increased minimum for readability
        cell_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size)

        # Fit text to available width (leave some padding)
        max_text_width = rect.width - int(8 * self.ui_scale)
        fitted_text = self._fit_text_to_width(text, cell_font, max_text_width)

        text_surface = cell_font.render(fitted_text, True, text_color)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def _draw_color_cell(self, rect, color_value, hovered, alpha_mod=1.0):
        """Draw a color cell with color swatch"""
        # Subtle parchment background with hover/click states
        if self.clicked_element and rect.collidepoint(pygame.mouse.get_pos()):
            bg_color = tuple(int(c * alpha_mod) for c in PARCHMENT_CLICK)
        elif hovered:
            bg_color = tuple(int(c * alpha_mod) for c in PARCHMENT_HOVER)
        else:
            bg_color = tuple(int(c * alpha_mod) for c in PARCHMENT_COLOR)

        pygame.draw.rect(self.screen, bg_color, rect, border_radius=3)

        # Brass border
        brass_color_dimmed = tuple(int(c * alpha_mod) for c in BRASS_COLOR)
        pygame.draw.rect(self.screen, brass_color_dimmed, rect, 1, border_radius=3)

        # Color swatch (centered, larger since no text)
        swatch_size = int(20 * self.ui_scale)  # Larger since it's the only element
        swatch_rect = pygame.Rect(rect.centerx - swatch_size // 2, rect.centery - swatch_size // 2, swatch_size, swatch_size)
        swatch_color = tuple(int(c * alpha_mod) for c in color_value)
        pygame.draw.rect(self.screen, swatch_color, swatch_rect)
        pygame.draw.rect(self.screen, TEXT_COLOR, swatch_rect, 1)

    def _draw_player_section(self, player_num, is_ai, difficulty):
        """Draw player configuration section"""
        # Label
        label_key = f'player{player_num}_label'
        label_text = self.header_font.render(f"Player {player_num}", True, TEXT_COLOR)
        self.screen.blit(label_text, self.ui_elements[label_key])

        # Radio buttons
        human_key = f'player{player_num}_human_radio'
        ai_key = f'player{player_num}_ai_radio'

        # Use profile name from settings for human player radio button
        from settings_manager import settings
        player_name = settings.get_player_name()
        self._draw_radio_button(human_key, player_name, not is_ai)
        self._draw_radio_button(ai_key, "AI", is_ai)

        # Difficulty dropdown (only if AI)
        if is_ai:
            difficulty_key = f'player{player_num}_difficulty'
            difficulty_text = self.config.difficulty_options[difficulty]
            self._draw_dropdown(difficulty_key, difficulty_text)

    def _draw_radio_button(self, key, text, selected):
        """Draw radio button"""
        rect = self.ui_elements[key]
        hovered = (self.hovered_element == key)

        circle_center = (rect.x + 12, rect.centery)
        circle_color = RADIO_SELECTED if selected else RADIO_UNSELECTED

        # Hover glow
        if hovered:
            pygame.draw.circle(self.screen, BUTTON_HOVER_COLOR, circle_center, 14, 0)

        # Radio circle
        pygame.draw.circle(self.screen, circle_color, circle_center, 10, 0)
        pygame.draw.circle(self.screen, TEXT_COLOR, circle_center, 10, 2)

        # Inner dot if selected
        if selected:
            pygame.draw.circle(self.screen, TEXT_COLOR, circle_center, 5, 0)

        # Label
        label_text = self.label_font.render(text, True, TEXT_COLOR)
        label_rect = label_text.get_rect(midleft=(rect.x + 30, rect.centery))
        self.screen.blit(label_text, label_rect)

    def _draw_dropdown(self, key, text):
        """Draw dropdown selector"""
        rect = self.ui_elements[key]
        hovered = (self.hovered_element == key)

        # Background
        bg_color = lighten_color(PANEL_BG, 0.3) if hovered else lighten_color(PANEL_BG, 0.1)
        pygame.draw.rect(self.screen, bg_color, rect, border_radius=5)
        pygame.draw.rect(self.screen, GRAY, rect, 2, border_radius=5)

        # Text
        dropdown_text = self.label_font.render(text, True, TEXT_COLOR)
        text_rect = dropdown_text.get_rect(midleft=(rect.x + 10, rect.centery))
        self.screen.blit(dropdown_text, text_rect)

        # Dropdown arrow
        arrow_points = [
            (rect.right - 15, rect.centery - 5),
            (rect.right - 10, rect.centery),
            (rect.right - 15, rect.centery + 5)
        ]
        pygame.draw.polygon(self.screen, TEXT_COLOR, arrow_points)

    def _draw_button(self, key, text, enabled):
        """Draw button with Main Menu style"""
        rect = self.ui_elements[key]
        hovered = (self.hovered_element == key)
        clicked = (self.clicked_element == key)

        # Draw custom button background (Main Menu style)
        if self.button_bg_image:
            # Scale the button background to match the button rect size
            scaled_button_bg = pygame.transform.smoothscale(
                self.button_bg_image,
                (rect.width, rect.height)
            )

            # Darken the button base, then add brightness for states
            button_surface = scaled_button_bg.copy()

            if not enabled:
                # Gray out disabled buttons (darkest)
                button_surface.fill((80, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)
            else:
                # Darken all enabled buttons (similar to Main Menu)
                button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

                if clicked:
                    # More brightness than hover on click
                    button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
                elif hovered:
                    # Subtle brightness on hover
                    button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)

            self.screen.blit(button_surface, rect)
        else:
            # Fallback to brass border style
            pygame.draw.rect(self.screen, BRASS_COLOR, rect, 2, border_radius=8)

        # Text color - brass for Launch Game button, white/gray for others
        if key == 'launch_button':
            text_color = BRASS_COLOR if enabled else GRAY
        else:
            text_color = GRAY if not enabled else WHITE

        # Text (size 29 scaled - matching Main Menu)
        # Use Cinzel-Bold for Launch Game button, Cinzel-Regular for Return button
        button_font_size = max(16, int(29 * self.ui_scale))
        if key == 'launch_button':
            button_font = pygame.font.Font('assets/fonts/Cinzel-Bold.ttf', button_font_size)
        else:
            button_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', button_font_size)
        button_text = button_font.render(text, True, text_color)
        text_rect = button_text.get_rect(center=rect.center)
        self.screen.blit(button_text, text_rect)

    def _draw_taxation_section(self):
        """Draw taxation level dropdown section (below table, above buttons)"""
        # Label
        label_rect = self.ui_elements['taxation_label']
        label_font_size = max(14, int(20 * self.ui_scale))
        label_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', label_font_size)
        label_text = label_font.render("Taxation Level:", True, TEXT_COLOR)
        label_text_rect = label_text.get_rect(midleft=(label_rect.x, label_rect.centery))
        self.screen.blit(label_text, label_text_rect)

        # Dropdown button
        dropdown_rect = self.ui_elements['taxation_dropdown']
        hovered = (self.hovered_element == 'taxation_dropdown')

        # Draw dropdown background (parchment color with brass border)
        pygame.draw.rect(self.screen, PARCHMENT_COLOR, dropdown_rect, border_radius=5)
        border_color = BRASS_COLOR if hovered else (120, 100, 80)
        pygame.draw.rect(self.screen, border_color, dropdown_rect, 2, border_radius=5)

        # Current selection text
        current_text = self.config.taxation_options[self.config.taxation_level]
        dropdown_font_size = max(12, int(18 * self.ui_scale))
        dropdown_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', dropdown_font_size)
        text_surface = dropdown_font.render(current_text, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(midleft=(dropdown_rect.x + int(10 * self.ui_scale), dropdown_rect.centery))
        self.screen.blit(text_surface, text_rect)

        # Dropdown arrow
        arrow_size = int(5 * self.ui_scale)
        arrow_points = [
            (dropdown_rect.right - int(15 * self.ui_scale), dropdown_rect.centery - arrow_size),
            (dropdown_rect.right - int(10 * self.ui_scale), dropdown_rect.centery),
            (dropdown_rect.right - int(15 * self.ui_scale), dropdown_rect.centery + arrow_size)
        ]
        pygame.draw.polygon(self.screen, TEXT_COLOR, arrow_points)

    def _draw_victory_section(self):
        """Draw victory condition dropdown section (below taxation dropdown, above buttons)"""
        # Label
        label_rect = self.ui_elements['victory_label']
        label_font_size = max(14, int(20 * self.ui_scale))
        label_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', label_font_size)
        label_text = label_font.render("Victory Condition:", True, TEXT_COLOR)
        label_text_rect = label_text.get_rect(midleft=(label_rect.x, label_rect.centery))
        self.screen.blit(label_text, label_text_rect)

        # Dropdown button
        dropdown_rect = self.ui_elements['victory_dropdown']
        hovered = (self.hovered_element == 'victory_dropdown')

        # Draw dropdown background (parchment color with brass border)
        pygame.draw.rect(self.screen, PARCHMENT_COLOR, dropdown_rect, border_radius=5)
        border_color = BRASS_COLOR if hovered else (120, 100, 80)
        pygame.draw.rect(self.screen, border_color, dropdown_rect, 2, border_radius=5)

        # Current selection text
        current_text = self.config.victory_options[self.config.victory_condition]
        dropdown_font_size = max(12, int(18 * self.ui_scale))
        dropdown_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', dropdown_font_size)
        text_surface = dropdown_font.render(current_text, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(midleft=(dropdown_rect.x + int(10 * self.ui_scale), dropdown_rect.centery))
        self.screen.blit(text_surface, text_rect)

        # Dropdown arrow
        arrow_size = int(5 * self.ui_scale)
        arrow_points = [
            (dropdown_rect.right - int(15 * self.ui_scale), dropdown_rect.centery - arrow_size),
            (dropdown_rect.right - int(10 * self.ui_scale), dropdown_rect.centery),
            (dropdown_rect.right - int(15 * self.ui_scale), dropdown_rect.centery + arrow_size)
        ]
        pygame.draw.polygon(self.screen, TEXT_COLOR, arrow_points)

    def _draw_turn_mode_section(self):
        """Draw turn mode dropdown section (below victory condition, above buttons)"""
        # Label
        label_rect = self.ui_elements['turn_mode_label']
        label_font_size = max(14, int(20 * self.ui_scale))
        label_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', label_font_size)
        label_text = label_font.render("Turn Mode:", True, TEXT_COLOR)
        label_text_rect = label_text.get_rect(midleft=(label_rect.x, label_rect.centery))
        self.screen.blit(label_text, label_text_rect)

        # Dropdown button
        dropdown_rect = self.ui_elements['turn_mode_dropdown']
        hovered = (self.hovered_element == 'turn_mode_dropdown')

        # Draw dropdown background (parchment color with brass border)
        pygame.draw.rect(self.screen, PARCHMENT_COLOR, dropdown_rect, border_radius=5)
        border_color = BRASS_COLOR if hovered else (120, 100, 80)
        pygame.draw.rect(self.screen, border_color, dropdown_rect, 2, border_radius=5)

        # Current selection text with tooltip hint
        current_option = self.config.turn_mode_options[self.config.turn_mode]
        tooltip = self.config.turn_mode_tooltips.get(current_option, "")
        current_text = current_option
        dropdown_font_size = max(12, int(18 * self.ui_scale))
        dropdown_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', dropdown_font_size)
        text_surface = dropdown_font.render(current_text, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(midleft=(dropdown_rect.x + int(10 * self.ui_scale), dropdown_rect.centery))
        self.screen.blit(text_surface, text_rect)

        # Draw tooltip if hovered
        if hovered and tooltip:
            tooltip_font_size = max(10, int(14 * self.ui_scale))
            tooltip_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', tooltip_font_size)
            tooltip_surface = tooltip_font.render(tooltip, True, TEXT_COLOR_DIM)
            tooltip_rect = tooltip_surface.get_rect(midleft=(dropdown_rect.x + int(10 * self.ui_scale), dropdown_rect.bottom + int(5 * self.ui_scale)))
            self.screen.blit(tooltip_surface, tooltip_rect)

        # Dropdown arrow
        arrow_size = int(5 * self.ui_scale)
        arrow_points = [
            (dropdown_rect.right - int(15 * self.ui_scale), dropdown_rect.centery - arrow_size),
            (dropdown_rect.right - int(10 * self.ui_scale), dropdown_rect.centery),
            (dropdown_rect.right - int(15 * self.ui_scale), dropdown_rect.centery + arrow_size)
        ]
        pygame.draw.polygon(self.screen, TEXT_COLOR, arrow_points)

    def _draw_dropdown_menu(self):
        """Draw the active dropdown menu overlaying content"""
        if not self.active_dropdown:
            return

        # Get dropdown items
        item_rects = self._get_dropdown_items_rects(self.active_dropdown)

        # Handle taxation dropdown separately (simpler rendering)
        if self.active_dropdown == 'taxation':
            items = self.config.taxation_options
            font_size = max(12, int(16 * self.ui_scale))
            dropdown_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size)

            for i, (item_rect, item_text) in enumerate(zip(item_rects, items)):
                is_hovered = (self.hovered_dropdown_item == i)

                # Background
                if is_hovered:
                    bg_color = lighten_color(BUTTON_COLOR, 0.3)
                else:
                    bg_color = PARCHMENT_COLOR

                pygame.draw.rect(self.screen, bg_color, item_rect, border_radius=3)
                pygame.draw.rect(self.screen, BRASS_COLOR if is_hovered else GRAY, item_rect, 1, border_radius=3)

                # Text
                text_surface = dropdown_font.render(item_text, True, TEXT_COLOR)
                text_rect = text_surface.get_rect(midleft=(item_rect.x + int(10 * self.ui_scale), item_rect.centery))
                self.screen.blit(text_surface, text_rect)
            return

        # Handle victory condition dropdown separately (simpler rendering)
        if self.active_dropdown == 'victory':
            items = self.config.victory_options
            font_size = max(12, int(16 * self.ui_scale))
            dropdown_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size)

            for i, (item_rect, item_text) in enumerate(zip(item_rects, items)):
                is_hovered = (self.hovered_dropdown_item == i)

                # Background
                if is_hovered:
                    bg_color = lighten_color(BUTTON_COLOR, 0.3)
                else:
                    bg_color = PARCHMENT_COLOR

                pygame.draw.rect(self.screen, bg_color, item_rect, border_radius=3)
                pygame.draw.rect(self.screen, BRASS_COLOR if is_hovered else GRAY, item_rect, 1, border_radius=3)

                # Text
                text_surface = dropdown_font.render(item_text, True, TEXT_COLOR)
                text_rect = text_surface.get_rect(midleft=(item_rect.x + int(10 * self.ui_scale), item_rect.centery))
                self.screen.blit(text_surface, text_rect)
            return

        # Handle turn mode dropdown separately
        if self.active_dropdown == 'turn_mode':
            items = self.config.turn_mode_options
            font_size = max(12, int(16 * self.ui_scale))
            dropdown_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size)

            for i, (item_rect, item_text) in enumerate(zip(item_rects, items)):
                is_hovered = (self.hovered_dropdown_item == i)

                # Background
                if is_hovered:
                    bg_color = lighten_color(BUTTON_COLOR, 0.3)
                else:
                    bg_color = PARCHMENT_COLOR

                pygame.draw.rect(self.screen, bg_color, item_rect, border_radius=3)
                pygame.draw.rect(self.screen, BRASS_COLOR if is_hovered else GRAY, item_rect, 1, border_radius=3)

                # Text with tooltip
                text_surface = dropdown_font.render(item_text, True, TEXT_COLOR)
                text_rect = text_surface.get_rect(midleft=(item_rect.x + int(10 * self.ui_scale), item_rect.centery))
                self.screen.blit(text_surface, text_rect)
            return

        # Parse dropdown_id for player slots
        slot_idx = int(self.active_dropdown.split('_')[0].replace('slot', ''))
        dropdown_type = self.active_dropdown.split('_')[1]

        # Get item labels
        if dropdown_type == 'player':
            # Use profile name from settings for human player option
            from settings_manager import settings
            player_name = settings.get_player_name()

            # Check if another slot already has Human selected
            human_available = True
            for i, other_slot in enumerate(self.config.player_slots):
                if i != slot_idx and other_slot['active'] and other_slot['type'] == 'Human':
                    human_available = False
                    break

            # Only include Human option if it's available or this slot already has it
            if human_available or self.config.player_slots[slot_idx]['type'] == 'Human':
                items = [player_name, 'AI (Easy)', 'AI (Medium)', 'AI (Hard)']
            else:
                items = ['AI (Easy)', 'AI (Medium)', 'AI (Hard)']
        elif dropdown_type == 'color':
            items = []
            for color_idx, color_name in enumerate(self.config.available_colors):
                if not self.config.is_color_used(color_idx, exclude_slot=slot_idx):
                    items.append(color_name)
        elif dropdown_type == 'team':
            items = self.config.available_teams
        else:
            items = []

        # Draw each dropdown item (scaled font, Cinzel Regular, further reduced size)
        font_size = max(10, int(14 * self.ui_scale))  # Further reduced from 16
        dropdown_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size)
        for i, (item_rect, item_text) in enumerate(zip(item_rects, items)):
            # Determine if this item is hovered
            is_hovered = (self.hovered_dropdown_item == i)

            # Background
            if is_hovered:
                bg_color = lighten_color(BUTTON_COLOR, 0.3)
            else:
                bg_color = lighten_color(PANEL_BG, 0.2)

            pygame.draw.rect(self.screen, bg_color, item_rect)
            pygame.draw.rect(self.screen, GRAY, item_rect, 1)

            # For color dropdown, draw color swatch (scaled)
            if dropdown_type == 'color':
                # Find the actual color index for this item
                available_colors = []
                for color_idx in range(4):
                    if not self.config.is_color_used(color_idx, exclude_slot=slot_idx):
                        available_colors.append(color_idx)

                if i < len(available_colors):
                    color_idx = available_colors[i]
                    color_value = PLAYER_COLORS[color_idx]

                    # Draw color swatch (centered, larger since no text)
                    swatch_size = int(20 * self.ui_scale)
                    swatch_rect = pygame.Rect(item_rect.centerx - swatch_size // 2, item_rect.centery - swatch_size // 2, swatch_size, swatch_size)
                    pygame.draw.rect(self.screen, color_value, swatch_rect)
                    pygame.draw.rect(self.screen, TEXT_COLOR, swatch_rect, 1)
            else:
                # Regular text-only item - fit to available width
                max_text_width = item_rect.width - int(8 * self.ui_scale)
                fitted_text = self._fit_text_to_width(item_text, dropdown_font, max_text_width)
                text_surface = dropdown_font.render(fitted_text, True, TEXT_COLOR)
                text_rect = text_surface.get_rect(center=item_rect.center)
                self.screen.blit(text_surface, text_rect)

    def _draw_territory_status(self):
        """Draw territory selection status"""
        rect = self.ui_elements['territory_status']

        # Background
        pygame.draw.rect(self.screen, lighten_color(PANEL_BG, 0.1), rect, border_radius=5)
        pygame.draw.rect(self.screen, GRAY, rect, 2, border_radius=5)

        # Title
        title_text = self.label_font.render("Territory Selection", True, TEXT_COLOR)
        title_rect = title_text.get_rect(midtop=(rect.centerx, rect.y + 10))
        self.screen.blit(title_text, title_rect)

        # Player status (dynamic for all players)
        y_offset = rect.y + 35
        for player_index in range(self.config.num_players):
            territory = self.config.get_player_territory(player_index)
            territory_text = territory if territory else "Not selected"
            player_color = PLAYER_COLORS[player_index]

            # Truncate long territory names to fit
            if len(territory_text) > 15:
                territory_text = territory_text[:12] + "..."

            player_text = self.label_font.render(f"P{player_index + 1}: {territory_text}", True, player_color)
            player_rect = player_text.get_rect(midleft=(rect.x + 20, y_offset))
            self.screen.blit(player_text, player_rect)
            y_offset += 22  # Smaller spacing for 4 players


# ===========================================
# MAIN INTEGRATED SETUP CLASS
# ===========================================

class IntegratedSetup:
    """
    Main setup window orchestrator.

    Manages event loop, coordinates between MapPreview and ConfigPanel,
    and returns configuration for game launch.
    """

    def __init__(self, screen, num_players=2):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()

        # Load map data
        if not map_data.TERRITORY_POLYGONS:
            map_data.load_polygons()

        # Configuration state
        self.config = SetupConfig()

        # Layout
        self.left_panel_width = int(self.width * 0.35)
        left_bounds = pygame.Rect(0, 0, self.left_panel_width, self.height)
        right_bounds = pygame.Rect(self.left_panel_width, 0, self.width - self.left_panel_width, self.height)

        # Components
        self.config_panel = ConfigPanel(self.screen, left_bounds, self.config)
        self.map_preview = MapPreview(self.screen, right_bounds, self.config)

        # State
        self.setup_complete = False
        self.cancelled = False
        self.clock = pygame.time.Clock()

    def run(self):
        """Main setup loop - returns config dict or None if cancelled"""
        while not self.setup_complete and not self.cancelled:
            dt = self.clock.tick(60) / 1000.0  # Delta time in seconds

            self.handle_events()
            self.update(dt)
            self.render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()

        if self.cancelled:
            return None

        return self.get_config()

    def handle_events(self):
        """Process events"""
        mouse_pos = pygame.mouse.get_pos()

        # Update hover states
        self.config_panel.update_hover(mouse_pos)
        self.map_preview.update_hover(mouse_pos)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.cancelled = True

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.cancelled = True

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    # Priority 1: Config panel
                    if mouse_pos[0] < self.left_panel_width:
                        result = self.config_panel.handle_click(mouse_pos)
                        if result == 'cancel':
                            self.cancelled = True
                        elif result == 'launch':
                            self.setup_complete = True

                    # Priority 2: Map territory selection
                    else:
                        self.map_preview.handle_territory_click(mouse_pos)

    def update(self, dt):
        """Update animations and state"""
        self.map_preview.update(dt)

        # Reset clicked state after a frame
        self.config_panel.clicked_element = None

    def render(self):
        """Render setup window"""
        # Clear screen
        self.screen.fill(BLACK)

        # Render components
        self.map_preview.render()
        self.config_panel.render()

    def get_config(self):
        """Convert setup state to config dict for game initialization"""
        # Get only active slots
        active_slots = [slot for slot in self.config.player_slots if slot['active']]

        config_dict = {
            'num_players': len(active_slots),
            'player_is_ai': [slot['type'] == 'AI' for slot in active_slots],
            'player_ai_difficulty': [slot['difficulty'] for slot in active_slots],
            'player_colors': [slot['color'] for slot in active_slots],  # NEW: color indices
            'player_teams': [slot['team'] for slot in active_slots],    # NEW: team assignments
            'win_condition': self.config.victory_options[self.config.victory_condition],  # Victory condition string
            'taxation_level': self.config.taxation_level,  # Integer 0-4 (0=0%, 1=25%, 2=50%, 3=75%, 4=100%)
            'game_mode': 'simultaneous' if self.config.turn_mode == 1 else 'sequential'  # Turn mode
        }

        # Add territory keys dynamically (for backwards compatibility)
        for i, slot in enumerate(active_slots):
            config_dict[f'player{i+1}_territory'] = slot['territory']

        return config_dict
