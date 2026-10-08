# -*- coding: utf-8 -*-
# rendering/ui_renderer.py
# UI overlay rendering - REAL extraction (Phase 4, Phase 2)

"""
UI Renderer
===========

This module handles UI overlay rendering with REAL extracted code.

The UIRenderer contains the actual rendering logic for UI overlays
(not just coordination), extracted from main.py to reduce clutter.

Methods Extracted (1,147 lines):
- draw_top_panel() - Menu button, player stats, FPS
- draw_chat_input() - Chat input box
- draw_battle_popup() - Battle resolution modal
- draw_game_menu() - Game menu overlay
- draw_options_menu() - Settings/options modal

Extracted from main.py during Phase 4, Phase 2 of refactoring.
"""

import math
import os
import time
import pygame
import random
from collections import OrderedDict
from config.constants import *
from ui.scaler import UIConstants
from ui.sidebar_layout import compute_tab_rects
from utils.logger import get_logger
import map_data

logger = get_logger(__name__)


class UIRenderer:
    """
    Handles UI overlay rendering with extracted code.
    
    This class contains the actual UI rendering methods extracted from Game class.
    Methods access Game instance state as needed, but logic is isolated here.
    
    Pattern: Extracted Logic with Game Reference
    - Real extraction (not delegation)
    - Methods access self.game for state
    - Logic organized in dedicated module
    """
    
    def __init__(self, game_instance, layout_values):
        """
        Initialize UI renderer with game instance and layout values.

        Args:
            game_instance: Reference to Game instance for state access
            layout_values: Dict with layout constants (window_width, window_height, etc.)
        """
        self.game = game_instance
        self.update_layout(layout_values)

        # Tech tree particle system for Ruthless Ingenuity effect
        self.tech_particles = []
        self.particle_spawn_accumulator = 0.0

        # H3: Text surface cache using LRU (Least Recently Used) eviction.
        # OrderedDict allows O(1) move_to_end on hit and popitem(last=False) for LRU eviction.
        # Old FIFO approach caused thrashing when cache was full (new entries evicted immediately).
        # Key: (text, font_id, color_tuple), Value: rendered pygame.Surface
        self.text_cache = OrderedDict()
        self.TEXT_CACHE_MAX_SIZE = 200  # Limit cache size to prevent memory bloat

        # FPS counter throttling — the displayed value refreshes ~4x/second instead
        # of every frame (see draw_top_panel). Rendering it per frame added a new
        # text-cache entry each frame, churning the very cache it used.
        self._fps_text_surface = None
        self._fps_text_updated_at = 0

        # FPS OPTIMIZATION: Reusable overlay surface for modal dialogs
        # Avoids creating full-screen SRCALPHA surfaces (5.44MB each) every frame
        self._reusable_overlay = None
        self._reusable_overlay_size = (0, 0)

        # FPS OPTIMIZATION 5A: Cache scaled resource slot surfaces
        # Slot background and icons only change on window resize, not per-frame
        self._cached_scaled_slot = None
        self._cached_scaled_slot_size = (0, 0)
        self._cached_scaled_icons = {}  # keyed by id(icon)
        self._cached_scaled_icon_size = (0, 0)

        # FPS OPTIMIZATION 5A: Cache scaled menu background surfaces
        # Menu backgrounds only change on window resize
        self._cached_game_menu_bg = None
        self._cached_game_menu_bg_size = (0, 0)
        self._cached_options_menu_bg = None
        self._cached_options_menu_bg_size = (0, 0)

    def update_layout(self, layout_values):
        """
        Update layout values (called when resolution changes).

        Args:
            layout_values: Dict with updated layout constants
        """
        self.WINDOW_WIDTH = layout_values['window_width']
        self.WINDOW_HEIGHT = layout_values['window_height']
        self.TOP_PANEL_HEIGHT = layout_values['top_panel_height']
        self.BOTTOM_UI_Y = layout_values['bottom_ui_y']
        self.BOTTOM_UI_HEIGHT = layout_values['bottom_ui_height']
        self.MAP_HEIGHT = layout_values['map_height']

        # FPS OPTIMIZATION 4.1: Clear text cache when resolution changes
        # (fonts may be different sizes at different resolutions)
        if hasattr(self, 'text_cache'):
            self.clear_text_cache()

        # FPS OPTIMIZATION 5A: Invalidate scale caches on resize
        # Scaled surfaces depend on window dimensions, must be regenerated
        if hasattr(self, '_cached_scaled_slot'):
            self._cached_scaled_slot = None
            self._cached_scaled_icons = {}
        if hasattr(self, '_cached_game_menu_bg'):
            self._cached_game_menu_bg = None
        if hasattr(self, '_cached_options_menu_bg'):
            self._cached_options_menu_bg = None

    def get_cached_text(self, text, font, color, font_id="default"):
        """
        FPS OPTIMIZATION 4.1: Get a cached text surface or render and cache it.

        For static text that doesn't change (menu titles, labels, headers),
        this eliminates expensive font.render() calls every frame.

        Args:
            text: The text string to render
            font: pygame.Font object to use
            color: RGB tuple for text color
            font_id: Identifier for the font (to differentiate fonts in cache)

        Returns:
            pygame.Surface: The rendered text surface
        """
        # Ensure color is a tuple for hashing
        if isinstance(color, list):
            color = tuple(color)

        cache_key = (text, font_id, color)

        if cache_key in self.text_cache:
            # H3: LRU eviction - mark this entry as recently used
            self.text_cache.move_to_end(cache_key)
            return self.text_cache[cache_key]

        # Render and cache
        surface = font.render(text, True, color)

        # H3: LRU eviction - evict least recently used entry when cache is full
        if len(self.text_cache) >= self.TEXT_CACHE_MAX_SIZE:
            self.text_cache.popitem(last=False)  # Evict oldest (least recently used)
        self.text_cache[cache_key] = surface

        return surface

    def clear_text_cache(self):
        """Clear the text cache (call when resolution changes or fonts reload)."""
        self.text_cache = OrderedDict()

    def _get_overlay_surface(self):
        """
        Get a reusable full-screen overlay surface.

        PERFORMANCE: Avoids creating new full-screen SRCALPHA surfaces (5.44MB each)
        every frame for modal dialogs. Surface is cleared and reused.

        Returns:
            pygame.Surface: Cleared SRCALPHA surface at current window dimensions
        """
        target_size = (self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        if self._reusable_overlay is None or self._reusable_overlay_size != target_size:
            self._reusable_overlay = pygame.Surface(target_size, pygame.SRCALPHA)
            self._reusable_overlay_size = target_size
        # Clear for reuse
        self._reusable_overlay.fill((0, 0, 0, 0))
        return self._reusable_overlay

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
        if not self.game.battle_popup_visible:
            return
        
        # Get battle reference (only needed for 'initial' state)
        battle = None
        if self.game.selected_battle_index is not None and self.game.selected_battle_index < len(self.game.game_state.pending_battles):
            battle = self.game.game_state.pending_battles[self.game.selected_battle_index]
        
        # For result/resolving states, we use stored battle_result
        if self.game.battle_popup_state != 'initial' and not self.game.battle_result:
            return  # No data to display
        
        # Semi-transparent overlay - PERFORMANCE: Reuse surface
        overlay = self._get_overlay_surface()
        overlay.fill((0, 0, 0, 180))
        self.game.screen.blit(overlay, (0, 0))
        
        # M22: Modal window proportional to window size instead of hardcoded 500x500.
        # At 1600x900 reference, 500/1600 = 31.25% width, 500/900 = 55.5% height.
        # Use min to ensure modal fits on smaller screens.
        modal_width = min(500, int(self.WINDOW_WIDTH * 0.3125))
        modal_height = min(500, int(self.WINDOW_HEIGHT * 0.555))
        modal_x = (self.WINDOW_WIDTH - modal_width) // 2
        modal_y = (self.MAP_HEIGHT - modal_height) // 2
        
        # Draw modal background
        modal_rect = pygame.Rect(modal_x, modal_y, modal_width, modal_height)
        pygame.draw.rect(self.game.screen, (40, 40, 40), modal_rect)
        pygame.draw.rect(self.game.screen, (200, 200, 200), modal_rect, 4)
        
        # Title - use display name for campaign mission territory renaming
        territory_name = battle.territory if battle else self.game.battle_result.get('territory', 'Unknown')
        display_territory = map_data.get_display_name(territory_name)
        title_text = self.game._get_cached_text(f"Battle at {display_territory}", self.game.large_font, WHITE)
        title_rect = title_text.get_rect(center=(self.WINDOW_WIDTH // 2, modal_y + 30))
        self.game.screen.blit(title_text, title_rect)
        
        y_pos = modal_y + 80
        
        # Delegate to state-specific methods
        if self.game.battle_popup_state == 'initial':
            self.game._draw_battle_popup_initial(battle, modal_x, modal_y, modal_height, y_pos)
        
        elif self.game.battle_popup_state == 'resolving':
            self.game._draw_battle_popup_resolving(modal_x, modal_y, y_pos)
        
        elif self.game.battle_popup_state == 'result':
            self.game._draw_battle_popup_result(modal_x, modal_y, modal_height, y_pos)
    

    def draw_chat_input(self):
        """
        Draw chat input box above bottom UI panel.

        Appears when user presses ENTER.
        Shows current typed text with cursor.
        TAB toggles between ALL and TEAM channels.
        """
        if not self.game.chat_input_active:
            return

        # Chat input dimensions - just above bottom UI
        input_height = 40
        input_y = self.BOTTOM_UI_Y - input_height - 5  # 5px gap above bottom UI
        input_x = 10
        input_width = self.WINDOW_WIDTH - 20

        # MP4 fix: Reuse cached surface instead of allocating SRCALPHA every frame
        chat_size = (input_width, input_height)
        if not hasattr(self, '_cached_chat_input_surface') or self._cached_chat_input_surface is None or self._cached_chat_input_surface.get_size() != chat_size:
            self._cached_chat_input_surface = pygame.Surface(chat_size, pygame.SRCALPHA)
        else:
            self._cached_chat_input_surface.fill((0, 0, 0, 0))
        input_surface = self._cached_chat_input_surface
        pygame.draw.rect(input_surface, (40, 40, 40, 240), (0, 0, input_width, input_height))

        # Border color based on channel: blue for ALL, green for TEAM
        current_channel = getattr(self.game, 'chat_channel', 'all')
        border_color = (100, 200, 100) if current_channel == 'team' else (100, 200, 255)
        pygame.draw.rect(input_surface, border_color, (0, 0, input_width, input_height), 3)
        self.game.screen.blit(input_surface, (input_x, input_y))

        # Draw channel indicator with color coding
        channel_text = "[TEAM]" if current_channel == 'team' else "[ALL]"
        channel_color = (100, 200, 100) if current_channel == 'team' else (100, 200, 255)
        channel_surface = self.get_cached_text(channel_text, self.game.small_font, channel_color, "small")
        self.game.screen.blit(channel_surface, (input_x + 10, input_y + 12))

        # Draw current text being typed (after channel indicator)
        text_x = input_x + 10 + channel_surface.get_width() + 10
        chat_text = self.get_cached_text(self.game.chat_input_text, self.game.small_font, WHITE, "small")
        self.game.screen.blit(chat_text, (text_x, input_y + 12))

        # Draw blinking cursor
        import time
        if int(time.time() * 2) % 2 == 0:  # Blink every 0.5 seconds
            cursor_x = text_x + chat_text.get_width() + 2
            pygame.draw.line(self.game.screen, WHITE,
                           (cursor_x, input_y + 10),
                           (cursor_x, input_y + input_height - 10), 2)

        # Draw instructions with TAB toggle hint
        instructions = self.get_cached_text("TAB: channel | ENTER: send | ESC: cancel", self.game.small_font, (150, 150, 150), "small")
        inst_rect = instructions.get_rect(right=input_x + input_width - 10, centery=input_y + input_height // 2)
        self.game.screen.blit(instructions, inst_rect)
    

    def draw_top_panel(self):
        """
        Draw top panel spanning full screen width.
        
        Phase A: UI Redesign - Top Panel
        This panel contains:
        - Menu button (opens game menu)
        - Player stats (armies, income, gold)
        - Other game controls
        """
        # Top panel background (custom image or fallback to light gray)
        panel_rect = pygame.Rect(0, 0, self.WINDOW_WIDTH, self.TOP_PANEL_HEIGHT)
        
        # Use custom image if available, otherwise fallback to solid color
        if self.game.top_panel_image:
            # Blit image with bottom edge aligned to bottom of top panel
            self.game.screen.blit(self.game.top_panel_image, (0, 0))
        else:
            # Fallback: solid color background
            pygame.draw.rect(self.game.screen, (220, 220, 220), panel_rect)
        
        # Border at bottom (over the image)
        pygame.draw.line(self.game.screen, (100, 100, 100), 
                        (0, self.TOP_PANEL_HEIGHT - 1), 
                        (self.WINDOW_WIDTH, self.TOP_PANEL_HEIGHT - 1), 2)
        
        # Menu button (left side) - uses GMenuButton.png with white text and hover/click effects
        # Scaled based on 1600×900 reference resolution for all screen sizes
        scale = self.WINDOW_WIDTH / 1600.0
        menu_button_width = int(140 * scale)
        menu_button_height = int(26 * scale)
        menu_button_x = int(10 * scale)
        menu_button_y = int(6 * scale)
        menu_button_rect = pygame.Rect(menu_button_x, menu_button_y, menu_button_width, menu_button_height)
        self.game.helpers.draw_feedback_button(menu_button_rect, None,  # No base color needed
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'top_button', 'menu',
                                  text="M e n u", text_color=WHITE, font=self.game.small_font_bold,
                                  bg_image=self.game.menu_button_img)  # GMenuButton.png as background
        self.game.menu_button = menu_button_rect

        # Players button — sibling of Menu, opens non-pausing modal list of all players
        players_button_x = menu_button_x + menu_button_width + int(8 * scale)
        players_button_rect = pygame.Rect(players_button_x, menu_button_y, menu_button_width, menu_button_height)
        self.game.helpers.draw_feedback_button(players_button_rect, None,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'top_button', 'players',
                                  text="P l a y e r s", text_color=WHITE, font=self.game.small_font_bold,
                                  bg_image=self.game.menu_button_img)
        self.game.players_button = players_button_rect

        # Phase indicator (center of top panel)
        if hasattr(self.game.game_state, 'turn_phase') and hasattr(self.game.game_state, 'phase'):
            if self.game.game_state.phase == 'playing':
                # Check for simultaneous mode - use sim_state's phase instead
                sim_state = getattr(self.game, 'sim_state', None)
                if sim_state is not None:
                    # Simultaneous mode: show sim phase and turn number
                    sim_phase = sim_state.sim_phase
                    turn_num = sim_state.round_number
                    if sim_phase == 'planning':
                        phase_text = f"PLANNING - TURN {turn_num}"
                        phase_color = (100, 200, 100)  # Green
                        bg_color = (40, 80, 40)  # Dark green
                    elif sim_phase == 'executing':
                        phase_text = f"EXECUTING - TURN {turn_num}"
                        phase_color = (200, 200, 100)  # Yellow
                        bg_color = (80, 80, 40)  # Dark yellow
                    elif sim_phase == 'resolving':
                        phase_text = f"RESOLVING - TURN {turn_num}"
                        phase_color = (255, 100, 100)  # Red
                        bg_color = (100, 40, 40)  # Dark red
                    else:
                        phase_text = f"TURN {turn_num}"
                        phase_color = (150, 150, 150)  # Gray
                        bg_color = (60, 60, 60)  # Dark gray
                # Sequential mode: use game_state's turn_phase
                elif self.game.game_state.turn_phase == 'planning':
                    phase_text = "PLANNING PHASE"
                    phase_color = (100, 200, 100)  # Green
                    bg_color = (40, 80, 40)  # Dark green
                elif self.game.game_state.turn_phase == 'execution':
                    phase_text = "EXECUTION PHASE"
                    phase_color = (200, 200, 100)  # Yellow
                    bg_color = (80, 80, 40)  # Dark yellow
                elif self.game.game_state.turn_phase == 'battles':
                    phase_text = "BATTLE PHASE"
                    phase_color = (255, 100, 100)  # Red
                    bg_color = (100, 40, 40)  # Dark red
                else:
                    phase_text = "UNKNOWN PHASE"
                    phase_color = (150, 150, 150)  # Gray
                    bg_color = (60, 60, 60)  # Dark gray

                # Phase indicator rectangle (centered)
                phase_width = 200
                phase_height = 32
                phase_x = (self.WINDOW_WIDTH - phase_width) // 2
                phase_y = (self.TOP_PANEL_HEIGHT - phase_height) // 2

                phase_rect = pygame.Rect(phase_x, phase_y, phase_width, phase_height)

                # Draw background
                pygame.draw.rect(self.game.screen, bg_color, phase_rect, border_radius=5)
                # Draw border
                pygame.draw.rect(self.game.screen, phase_color, phase_rect, 2, border_radius=5)

                # Draw phase text (centered) - Phase 2: Use SemiBold for phase indicator
                phase_text_surface = self.get_cached_text(phase_text, self.game.small_font_bold, phase_color, "small_bold")
                phase_text_rect = phase_text_surface.get_rect(center=phase_rect.center)
                self.game.screen.blit(phase_text_surface, phase_text_rect)

                # "Resolve Remaining Battles" button (below top panel, overlaying map)
                # Shown during battle phase when local player has resolvable battles
                self._draw_resolve_all_battles_button(scale)

                # "Close All Battle Reports" button (same slot, planning phase instead)
                self._draw_close_all_battle_reports_button(scale)

                # Territorial Bonuses button (right of phase indicator)
                # Scale button size with top panel height (80% of panel height, matching phase indicator scaling)
                button_size = int(self.TOP_PANEL_HEIGHT * 0.8)  # 80% of panel height (32px at 40px panel, scales up)
                button_spacing = max(10, int(button_size * 0.3))  # Spacing scales with button (10px base, 30% of button size)

                bonuses_button_x = phase_x + phase_width + button_spacing
                bonuses_button_y = (self.TOP_PANEL_HEIGHT - button_size) // 2
                bonuses_button_rect = pygame.Rect(bonuses_button_x, bonuses_button_y, button_size, button_size)

                # FPS OPTIMIZATION 6.2: Use pre-loaded bonus icon instead of loading from disk
                # Scale the pre-loaded icon if size changed (or first use)
                if not hasattr(self.game, 'bonus_button_icon_size') or self.game.bonus_button_icon_size != button_size:
                    try:
                        # Use pre-loaded original icon if available, fall back to disk load
                        original_icon = getattr(self.game, 'bonus_button_icon_original', None)
                        if original_icon is None:
                            original_icon = pygame.image.load('assets/BonusButton.png')
                        self.game.bonus_button_icon = pygame.transform.scale(original_icon, (button_size, button_size))
                        self.game.bonus_button_icon_size = button_size
                    except (FileNotFoundError, pygame.error, OSError):
                        self.game.bonus_button_icon = None
                        self.game.bonus_button_icon_size = button_size

                # Draw icon first
                if self.game.bonus_button_icon:
                    self.game.screen.blit(self.game.bonus_button_icon, bonuses_button_rect.topleft)

                # Draw hover effect on top (semi-transparent white overlay, scales with button)
                is_hovering = bonuses_button_rect.collidepoint(self.game.mouse_pos)
                if is_hovering:
                    hover_surface = pygame.Surface((button_size, button_size), pygame.SRCALPHA)
                    hover_surface.fill((255, 255, 255, 60))  # Semi-transparent white
                    self.game.screen.blit(hover_surface, bonuses_button_rect.topleft)

                # Store rect for hover tracking
                self.game.bonuses_button_rect = bonuses_button_rect
            else:
                # Clear bonuses button rect when not in playing phase
                self.game.bonuses_button_rect = None

        # Connection status indicator (multiplayer only)
        connection_status_width = 0
        if self.game.multiplayer_mode:
            connection_status_width = self._draw_connection_status()

        # Resource slots positioning (always visible, fills space to right of phase indicator)
        # Purpose: Calculate positions for 4 resource slots (Taxation, Command, Gold, Income)
        # Calculate after connection status to account for its width

        # Determine left boundary (after phase indicator or bonus button if visible)
        phase_width = 200  # Phase indicator width
        phase_x = (self.WINDOW_WIDTH - phase_width) // 2

        if self.game.game_state.phase == 'playing' and hasattr(self.game, 'bonuses_button_rect'):
            # During playing phase, start after bonus button
            button_size = int(self.TOP_PANEL_HEIGHT * 0.8)
            button_spacing = max(10, int(button_size * 0.3))
            slots_left_boundary = self.game.bonuses_button_rect.right + button_spacing
        else:
            # Otherwise, start after phase indicator
            slots_left_boundary = phase_x + phase_width + 20

        # Calculate right boundary (account for connection status if present)
        slots_right_boundary = self.WINDOW_WIDTH - 20
        if connection_status_width > 0:
            slots_right_boundary -= connection_status_width + 30

        # Calculate available width and slot sizing to fill the space
        # Scaling: All measurements scale proportionally with resolution
        available_width = slots_right_boundary - slots_left_boundary
        slot_spacing = max(8, int(self.WINDOW_WIDTH * 0.006))  # Scales with width (~10px at 1600px)
        slot_width = (available_width - 3 * slot_spacing) // 4  # Divide remaining space by 4
        slot_height = int(self.TOP_PANEL_HEIGHT * 0.65)  # Height is 65% of panel height (shorter)
        slots_y = (self.TOP_PANEL_HEIGHT - slot_height) // 2

        # Store slot positions and dimensions for rendering below
        slot_positions = [
            slots_left_boundary + i * (slot_width + slot_spacing)
            for i in range(4)
        ]
        slot_size = (slot_width, slot_height)  # (width, height) tuple

        # Resource slots rendering (Taxation, Command, Gold, Income)
        # Purpose: Display LOCAL player's stats (not current turn player)
        # Shows "my" resources in multiplayer/AI games, similar to Territory Bonus tooltip
        if slot_positions and hasattr(self.game.game_state, 'current_player'):
            # Determine which player's stats to show
            if self.game.multiplayer_mode:
                # Multiplayer: Show LOCAL player's stats (host or client)
                player = self.game.local_player_index if self.game.local_player_index is not None else 0
            else:
                # Single-player: Show the HUMAN player's stats (find non-AI)
                player = 0
                for i in range(self.game.game_state.num_players):
                    if not self.game.game_state.player_is_ai[i]:
                        player = i
                        break

            # Get stat values
            gold = self.game.game_state.player_gold[player]
            income = self.game.game_state.calculate_player_income(player)
            current_command = self.game.game_state.get_player_army_count(player)
            command_limit = self.game.game_state.player_command_limit[player]

            tax_percentages = [0, 25, 50, 75, 100]
            # Per-player level (a mission may tax one player only, e.g. Tale II)
            gs = self.game.game_state
            if hasattr(gs, 'get_taxation_level'):
                tax_level = gs.get_taxation_level(player)
            else:
                tax_level = getattr(gs, 'taxation_level', 0)
            tax_pct = tax_percentages[max(0, min(tax_level, len(tax_percentages) - 1))]

            # Command limit color coding (green ≤ 80%, yellow 80-100%, red > 100%)
            ratio = current_command / command_limit if command_limit > 0 else 0
            if ratio <= 0.8:
                command_color = (0, 255, 0)  # Green
            elif ratio <= 1.0:
                command_color = (255, 255, 0)  # Yellow
            else:
                command_color = (255, 0, 0)  # Red

            # Prepare slot data: (icon, value_text, value_color)
            slot_data = [
                (self.game.taxation_icon, f"{tax_pct}%", BROWN_TEXT_PRIMARY),
                (self.game.command_icon, f"{current_command}/{command_limit}", command_color),
                (self.game.gold_icon, str(gold), BROWN_TEXT_PRIMARY),
                (self.game.income_icon, f"+{income}", BROWN_TEXT_PRIMARY),
            ]

            # Render each slot (slot_size is (width, height) tuple)
            # Scaling: Icon and padding scale with slot dimensions
            slot_width, slot_height = slot_size
            icon_height = int(slot_height * 0.65)  # Icon height 65% of slot height
            icon_width = int(icon_height * 1.4)  # Icon width is 40% wider (rectangular, not square)
            left_padding = max(5, int(slot_width * 0.05))  # Left padding for icon
            right_padding = max(8, int(slot_width * 0.10))  # Right padding for text (more space from edge)

            # Slot names for tooltip tracking
            slot_names = ['taxation', 'command_limit', 'gold', 'income']
            any_slot_hovered = False

            for i, (icon, value_text, text_color) in enumerate(slot_data):
                slot_x = slot_positions[i]

                # Create rect for hover detection (no visual hover effect)
                slot_rect = pygame.Rect(slot_x, slots_y, slot_width, slot_height)
                is_hovering = slot_rect.collidepoint(self.game.mouse_pos)

                # Track hover for tooltip (without visual feedback)
                if is_hovering:
                    any_slot_hovered = True
                    slot_name = slot_names[i]
                    current_hover = ('resource_slot', slot_name)
                    self.game.update_button_hover(current_hover, 'resource_slot')

                # FPS OPTIMIZATION 5A: Cache scaled slot background (only changes on resize)
                target_slot_size = (slot_width, slot_height)
                if self._cached_scaled_slot is None or self._cached_scaled_slot_size != target_slot_size:
                    self._cached_scaled_slot = pygame.transform.scale(self.game.resource_slot_img, target_slot_size)
                    self._cached_scaled_slot_size = target_slot_size
                self.game.screen.blit(self._cached_scaled_slot, (slot_x, slots_y))

                # FPS OPTIMIZATION 5A: Cache scaled icons (only change on resize)
                icon_id = id(icon)
                target_icon_size = (icon_width, icon_height)
                if icon_id not in self._cached_scaled_icons or self._cached_scaled_icon_size != target_icon_size:
                    self._cached_scaled_icons[icon_id] = pygame.transform.scale(icon, target_icon_size)
                    self._cached_scaled_icon_size = target_icon_size
                scaled_icon = self._cached_scaled_icons[icon_id]
                icon_x = slot_x + left_padding
                icon_y = slots_y + (slot_height - icon_height) // 2
                self.game.screen.blit(scaled_icon, (icon_x, icon_y))

                # FPS OPT: Cache resource slot text (changes only on turn change)
                text_surface = self.get_cached_text(value_text, self.game.small_font, text_color, "small")
                text_rect = text_surface.get_rect(
                    midright=(slot_x + slot_width - right_padding, slots_y + slot_height // 2)
                )
                self.game.screen.blit(text_surface, text_rect)

            # Clear tooltip if no slot is being hovered
            # Purpose: Ensure tooltip only shows when actively hovering over a slot
            if not any_slot_hovered:
                self.game.update_button_hover(None, 'resource_slot')

        # FPS counter (top-right corner, if enabled)
        if self.game.show_fps:
            # Refresh ~4x/second rather than every frame. The FPS string changes
            # almost every frame, so rendering it through get_cached_text() added a
            # new cache entry per frame (churning the cache it was meant to use) —
            # and a value updating 60+ times a second is unreadable anyway.
            now = pygame.time.get_ticks()
            if now - self._fps_text_updated_at >= 250 or self._fps_text_surface is None:
                fps = int(self.game.clock.get_fps())
                self._fps_text_surface = self.get_cached_text(
                    f"FPS: {fps}", self.game.small_font, BROWN_TEXT_SECONDARY, "small")
                self._fps_text_updated_at = now
            fps_rect = self._fps_text_surface.get_rect(topright=(self.WINDOW_WIDTH - 10, 2))
            self.game.screen.blit(self._fps_text_surface, fps_rect)

    def _draw_resolve_all_battles_button(self, scale):
        """
        Draw "Resolve Remaining Battles" button below the top panel during battle phase.

        Appears only when the local player has pending battles to resolve.
        Uses GMenuButton.png background with hover highlighting.
        Hidden during tutorial missions and when battle UI is open.
        """
        game = self.game
        gs = game.game_state

        # Clear rect by default — only set when button is visible
        game.resolve_all_battles_button = None

        # Guard: only during battle phase with pending battles
        if not gs.pending_battles:
            return
        in_battle_phase = False
        sim_state = getattr(game, 'sim_state', None)
        if gs.turn_phase == 'battles':
            in_battle_phase = True
        elif sim_state is not None and sim_state.sim_phase == 'resolving':
            in_battle_phase = True
        if not in_battle_phase:
            return

        # Guard: not when battle UI is open, game paused, or tutorial (mission 1) active
        if game.enhanced_battle_ui is not None or game.battle_popup_visible:
            return
        if game.is_game_paused:
            return
        # Only hide for the actual tutorial mission (mission_1), not other campaign missions
        if (game.tutorial_mission and game.tutorial_mission.active
                and getattr(game.tutorial_mission, 'mission_id', '') == 'mission_1'):
            return

        # Guard: local player must have at least one resolvable battle
        local_player = game.get_local_player()
        has_resolvable = False
        for battle in gs.pending_battles:
            if sim_state is not None:
                if getattr(battle, 'resolver', None) == local_player:
                    has_resolvable = True
                    break
            else:
                # Sequential mode: current player resolves all battles on their turn
                if gs.current_player == local_player:
                    has_resolvable = True
                    break
        if not has_resolvable:
            return

        # Position: centered horizontally, just below top panel border
        btn_width = int(260 * scale)
        btn_height = int(32 * scale)
        btn_x = (self.WINDOW_WIDTH - btn_width) // 2
        btn_y = self.TOP_PANEL_HEIGHT + int(4 * scale)
        btn_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)

        # Render using GMenuButton.png with hover/click feedback
        game.helpers.draw_feedback_button(
            btn_rect, None,
            game.mouse_pos, game.clicked_element,
            'top_button', 'resolve_all_battles',
            text="Resolve Remaining Battles",
            text_color=(255, 255, 255),
            font=game.small_font_bold,
            bg_image=game.menu_button_img
        )

        # Store rect for click detection and hover tracking
        game.resolve_all_battles_button = btn_rect

    def _draw_close_all_battle_reports_button(self, scale):
        """
        Draw "Close All Battle Reports" below the top panel during the planning phase.

        Occupies the same slot as "Resolve Remaining Battles". The two can never
        collide: this one is planning-phase only, that one is battles-phase only.

        Mirrors _draw_resolve_all_battles_button()'s guard stack, including clearing
        the rect first every frame so a stale rect cannot keep consuming clicks.
        """
        game = self.game

        # Clear rect by default - only set when the button is visible
        game.close_all_battle_reports_button = None

        # Guard: the viewer must actually have reports on screen
        if not getattr(game, 'battle_report_popups', None):
            return
        if not game._battle_reports_visible():
            return

        # Guard: not while the detail screen or another modal is open, or when paused
        if game.battle_report_detail_ui is not None:
            return
        if game.enhanced_battle_ui is not None or game.battle_popup_visible:
            return
        if game.is_game_paused:
            return
        # Only hide for the actual tutorial mission (mission_1), not other campaigns
        if (game.tutorial_mission and game.tutorial_mission.active
                and getattr(game.tutorial_mission, 'mission_id', '') == 'mission_1'):
            return

        # Position: identical geometry to the Resolve button so they share the slot
        btn_width = int(260 * scale)
        btn_height = int(32 * scale)
        btn_x = (self.WINDOW_WIDTH - btn_width) // 2
        btn_y = self.TOP_PANEL_HEIGHT + int(4 * scale)
        btn_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)

        game.helpers.draw_feedback_button(
            btn_rect, None,
            game.mouse_pos, game.clicked_element,
            'top_button', 'close_all_battle_reports',
            text="Close All Battle Reports",
            text_color=(255, 255, 255),
            font=game.small_font_bold,
            bg_image=game.menu_button_img
        )

        # Store rect for click detection and hover tracking
        game.close_all_battle_reports_button = btn_rect

    def _draw_connection_status(self):
        """
        Draw connection status indicator for multiplayer.
        Shows colored dot and latency information.

        Returns:
            int: Width of the status indicator (for layout adjustment)
        """
        # Determine connection status
        is_connected = False
        latency_ms = 0

        if self.game.network_connection:
            is_connected = self.game.network_connection.message_queue.is_connected()
            # Get latency from last PONG response
            if hasattr(self.game.network_connection, 'last_ping_latency'):
                latency_ms = int(self.game.network_connection.last_ping_latency * 1000)

        # Choose color based on connection status and latency
        if not is_connected:
            status_color = (255, 50, 50)  # Red - disconnected
            status_text = "Disconnected"
        elif latency_ms > 500:
            status_color = (255, 165, 0)  # Orange - high latency
            status_text = f"{latency_ms}ms"
        elif latency_ms > 200:
            status_color = (255, 255, 0)  # Yellow - moderate latency
            status_text = f"{latency_ms}ms"
        else:
            status_color = (50, 255, 50)  # Green - good connection
            status_text = f"{latency_ms}ms" if latency_ms > 0 else "Connected"

        # Draw status indicator
        indicator_x = self.WINDOW_WIDTH - 15
        indicator_y = self.TOP_PANEL_HEIGHT // 2

        # Draw circle (connection dot)
        pygame.draw.circle(self.game.screen, status_color, (indicator_x, indicator_y), 6)
        pygame.draw.circle(self.game.screen, (0, 0, 0), (indicator_x, indicator_y), 6, 1)  # Border

        # Draw status text (latency or status)
        text_surface = self.get_cached_text(status_text, self.game.small_font, BROWN_TEXT_PRIMARY, "small")
        text_rect = text_surface.get_rect(midright=(indicator_x - 12, indicator_y))
        self.game.screen.blit(text_surface, text_rect)

        # Return total width used for layout adjustment
        return text_rect.width + 30


    def _get_save_disabled_reason(self):
        """Check if Save Game should be disabled and return the reason, or None if enabled."""
        mission = self.game.tutorial_mission
        if mission is None:
            return None  # Not campaign — button won't be shown at all

        if getattr(mission, 'mission_id', '') == 'mission_1':
            return "Cannot save game in the Tutorial mission."

        gs = self.game.game_state
        if gs and gs.current_player != 0:
            return "Can only save during your turn."

        if getattr(mission, 'intro_active', False):
            return "Cannot save during intro sequence."

        if (getattr(mission, 'victory_sequence_active', False) or
                getattr(mission, 'defeat_sequence_active', False)):
            return "Cannot save during victory/defeat sequence."

        return None

    def draw_game_menu(self):
        """
        Draw the game menu modal overlay.

        Shows Resume Game, Save Game (campaign only), Options, and Quit buttons.
        Save Game is only shown during campaign missions and disabled during
        tutorial, AI turns, intro, and victory/defeat sequences.
        """
        # H7 fix: Use dedicated menu overlay (non-SRCALPHA) to avoid corrupting
        # _reusable_overlay which other code (battle popups) expects to be SRCALPHA.
        size = (self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        if not hasattr(self, '_menu_overlay') or self._menu_overlay is None or self._menu_overlay.get_size() != size:
            self._menu_overlay = pygame.Surface(size)
            self._menu_overlay.set_alpha(180)
            self._menu_overlay.fill((0, 0, 0))
        self.game.screen.blit(self._menu_overlay, (0, 0))

        # Determine if we're in campaign mode (show Save button)
        is_campaign = self.game.tutorial_mission is not None
        save_disabled_reason = self._get_save_disabled_reason() if is_campaign else None

        # Menu panel (centered) - Scaled based on 1600x900 reference resolution
        scale = self.WINDOW_WIDTH / 1600.0
        menu_width = int(400 * scale)
        # Taller panel when campaign (4 buttons) vs non-campaign (3 buttons)
        menu_height = int(420 * scale) if is_campaign else int(350 * scale)
        menu_x = (self.WINDOW_WIDTH - menu_width) // 2
        menu_y = (self.WINDOW_HEIGHT - menu_height) // 2

        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)

        # FPS OPTIMIZATION 5A: Cache scaled game menu background
        menu_size = (menu_width, menu_height)
        if self._cached_game_menu_bg is None or self._cached_game_menu_bg_size != menu_size:
            self._cached_game_menu_bg = pygame.transform.scale(self.game.ingame_menu_bg, menu_size)
            self._cached_game_menu_bg_size = menu_size
        self.game.screen.blit(self._cached_game_menu_bg, (menu_x, menu_y))

        # Title
        title_text = self.get_cached_text("Game Menu", self.game.large_font, WHITE, "large")
        title_rect = title_text.get_rect(centerx=menu_x + menu_width // 2, y=menu_y + int(38 * scale))
        self.game.screen.blit(title_text, title_rect)

        # Separator line
        pygame.draw.line(self.game.screen, (150, 150, 150),
                        (menu_x + int(40 * scale), menu_y + int(83 * scale)),
                        (menu_x + menu_width - int(40 * scale), menu_y + int(83 * scale)), 2)

        # Button dimensions
        button_width = int(300 * scale)
        button_height = int(60 * scale)
        button_x = menu_x + (menu_width - button_width) // 2
        button_spacing = int(70 * scale)

        # Resume Game button
        resume_y = menu_y + int(105 * scale)
        resume_rect = pygame.Rect(button_x, resume_y, button_width, button_height)
        self.game.helpers.draw_feedback_button(resume_rect, None,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'menu_button', 'resume',
                                  text="Resume Game", text_color=WHITE, font=self.game.font_bold,
                                  bg_image=self.game.menu_button_img)
        self.game.menu_resume_button = resume_rect

        # Track next button Y position
        next_y = resume_y + button_spacing

        # Save Game button (campaign only)
        self.game.menu_save_button = None
        if is_campaign:
            save_rect = pygame.Rect(button_x, next_y, button_width, button_height)
            if save_disabled_reason:
                # Draw disabled button (dimmed, no hover/click effects)
                # Manually draw the darkened button bg without feedback
                self.game.helpers.draw_feedback_button(save_rect, None,
                                          (-1, -1), None,  # fake mouse pos + no click = no hover/click effects
                                          'menu_button', 'save_disabled',
                                          text="Save Game", text_color=(120, 120, 120), font=self.game.font_bold,
                                          bg_image=self.game.menu_button_img)
                # Show tooltip on hover explaining why save is disabled
                if save_rect.collidepoint(self.game.mouse_pos):
                    self._draw_save_disabled_tooltip(save_rect, save_disabled_reason, scale)
            else:
                self.game.helpers.draw_feedback_button(save_rect, None,
                                          self.game.mouse_pos, self.game.clicked_element,
                                          'menu_button', 'save',
                                          text="Save Game", text_color=WHITE, font=self.game.font_bold,
                                          bg_image=self.game.menu_button_img)
                self.game.menu_save_button = save_rect
            next_y += button_spacing

        # Options button
        options_rect = pygame.Rect(button_x, next_y, button_width, button_height)
        self.game.helpers.draw_feedback_button(options_rect, None,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'menu_button', 'options',
                                  text="Options", text_color=WHITE, font=self.game.font_bold,
                                  bg_image=self.game.menu_button_img)
        self.game.menu_options_button = options_rect

        # Quit to Main Menu button
        quit_y = next_y + button_spacing
        quit_rect = pygame.Rect(button_x, quit_y, button_width, button_height)
        self.game.helpers.draw_feedback_button(quit_rect, None,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'menu_button', 'quit',
                                  text="Quit to Main Menu", text_color=WHITE, font=self.game.font_bold,
                                  bg_image=self.game.menu_button_img)
        self.game.menu_quit_button = quit_rect

        # Save feedback is rendered separately via draw_save_feedback() in the main game area

    def _draw_save_disabled_tooltip(self, button_rect, reason, scale):
        """Draw tooltip above the disabled Save button explaining why it's disabled."""
        tooltip_font = self.game.small_font
        text_surf = tooltip_font.render(reason, True, (255, 220, 150))
        tw, th = text_surf.get_size()
        pad = int(8 * scale)
        # Position tooltip above the button, centered
        tx = button_rect.centerx - (tw + pad * 2) // 2
        ty = button_rect.top - th - pad * 2 - int(5 * scale)
        bg_rect = pygame.Rect(tx, ty, tw + pad * 2, th + pad * 2)
        # Dark background with border
        pygame.draw.rect(self.game.screen, (30, 30, 30), bg_rect, border_radius=4)
        pygame.draw.rect(self.game.screen, (100, 100, 100), bg_rect, 1, border_radius=4)
        self.game.screen.blit(text_surf, (tx + pad, ty + pad))

    def draw_save_dialog(self):
        """
        Draw the save game name input dialog.

        Modal overlay with text input field, Save and Cancel buttons.
        Shown when player clicks Save Game in the game menu.
        """
        # Dark overlay
        size = (self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        if not hasattr(self, '_menu_overlay') or self._menu_overlay is None or self._menu_overlay.get_size() != size:
            self._menu_overlay = pygame.Surface(size)
            self._menu_overlay.set_alpha(180)
            self._menu_overlay.fill((0, 0, 0))
        self.game.screen.blit(self._menu_overlay, (0, 0))

        scale = self.WINDOW_WIDTH / 1600.0

        # Dialog panel
        dialog_width = int(450 * scale)
        dialog_height = int(250 * scale)
        dialog_x = (self.WINDOW_WIDTH - dialog_width) // 2
        dialog_y = (self.WINDOW_HEIGHT - dialog_height) // 2

        # Background (reuse ingame menu bg, scaled to dialog size)
        dialog_size = (dialog_width, dialog_height)
        dialog_bg = pygame.transform.scale(self.game.ingame_menu_bg, dialog_size)
        self.game.screen.blit(dialog_bg, (dialog_x, dialog_y))

        # Title
        title_text = self.get_cached_text("Save Game", self.game.large_font, WHITE, "large")
        title_rect = title_text.get_rect(centerx=dialog_x + dialog_width // 2,
                                          y=dialog_y + int(25 * scale))
        self.game.screen.blit(title_text, title_rect)

        # Separator
        sep_y = dialog_y + int(65 * scale)
        pygame.draw.line(self.game.screen, (150, 150, 150),
                        (dialog_x + int(30 * scale), sep_y),
                        (dialog_x + dialog_width - int(30 * scale), sep_y), 2)

        # "Save name:" label
        label_text = self.get_cached_text("Save name:", self.game.font_bold, (200, 200, 200), "save_label")
        self.game.screen.blit(label_text, (dialog_x + int(35 * scale), dialog_y + int(80 * scale)))

        # Text input field
        input_x = dialog_x + int(35 * scale)
        input_y = dialog_y + int(105 * scale)
        input_width = dialog_width - int(70 * scale)
        input_height = int(35 * scale)
        input_rect = pygame.Rect(input_x, input_y, input_width, input_height)
        pygame.draw.rect(self.game.screen, (40, 40, 50), input_rect, border_radius=4)
        pygame.draw.rect(self.game.screen, (150, 150, 150), input_rect, 1, border_radius=4)

        # Render input text with blinking cursor
        display_text = self.game.save_name_input
        cursor_char = "|" if self.game.save_name_cursor_visible else ""
        input_surf = self.game.font_bold.render(display_text + cursor_char, True, WHITE)
        # Clip text to fit input field
        clip_rect = pygame.Rect(0, 0, input_width - int(12 * scale), input_height)
        text_y = input_y + (input_height - input_surf.get_height()) // 2
        self.game.screen.blit(input_surf, (input_x + int(6 * scale), text_y), area=clip_rect)

        # Save and Cancel buttons
        btn_width = int(150 * scale)
        btn_height = int(50 * scale)
        btn_y = dialog_y + int(165 * scale)
        btn_gap = int(30 * scale)

        # Save button (left)
        save_x = dialog_x + dialog_width // 2 - btn_width - btn_gap // 2
        save_rect = pygame.Rect(save_x, btn_y, btn_width, btn_height)
        self.game.helpers.draw_feedback_button(save_rect, None,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'save_dialog', 'save',
                                  text="Save", text_color=WHITE, font=self.game.font_bold,
                                  bg_image=self.game.menu_button_img)
        self.game.save_dialog_save_button = save_rect

        # Cancel button (right)
        cancel_x = dialog_x + dialog_width // 2 + btn_gap // 2
        cancel_rect = pygame.Rect(cancel_x, btn_y, btn_width, btn_height)
        self.game.helpers.draw_feedback_button(cancel_rect, None,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'save_dialog', 'cancel',
                                  text="Cancel", text_color=WHITE, font=self.game.font_bold,
                                  bg_image=self.game.menu_button_img)
        self.game.save_dialog_cancel_button = cancel_rect

    def draw_save_feedback(self):
        """Draw save feedback message in the top-left corner of the map area (visible and large)."""
        if not self.game.save_feedback_message or self.game.save_feedback_timer <= 0:
            return

        scale = self.WINDOW_WIDTH / 1600.0
        # Use large font for visibility
        font = self.game.large_font

        # Fade out in the last 500ms
        alpha = min(255, int(self.game.save_feedback_timer * 255 / 500))

        # Red for a failure, green for success (a failed save used to be shown in green)
        is_error = getattr(self.game, 'save_feedback_is_error', False)
        text_color = (255, 100, 100) if is_error else (100, 255, 100)
        text_surf = font.render(self.game.save_feedback_message, True, text_color)
        if alpha < 255:
            text_surf.set_alpha(alpha)

        # Position: top-left of map area with padding (below top panel)
        pad_x = int(20 * scale)
        pad_y = int(75 * scale)  # Below top panel
        tw, th = text_surf.get_size()

        # Dark background pill for readability
        bg_pad = int(12 * scale)
        bg_rect = pygame.Rect(pad_x - bg_pad, pad_y - bg_pad // 2,
                              tw + bg_pad * 2, th + bg_pad)
        bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surf.fill((0, 0, 0, min(180, int(alpha * 0.7))))
        self.game.screen.blit(bg_surf, bg_rect.topleft)

        self.game.screen.blit(text_surf, (pad_x, pad_y))

    def draw_options_menu(self):
        """
        Draw the options menu modal overlay with scrolling support.
        
        Shows a larger menu (600x700 - 3x main menu size) with settings:
        - Display: Resolution dropdown and fullscreen checkbox
        - Audio: Volume sliders (placeholder for now)
        - Gameplay: Various toggles and sliders
        - Apply and Back buttons
        
        Content is scrollable if it exceeds the menu height.
        Scrollbar appears on right side when content is scrollable.
        
        All controls have hover highlighting and click flash feedback.
        Background is semi-transparent overlay that disables other UI.
        """
        # H7 fix: Reuse dedicated _menu_overlay (same as draw_game_menu)
        size = (self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        if not hasattr(self, '_menu_overlay') or self._menu_overlay is None or self._menu_overlay.get_size() != size:
            self._menu_overlay = pygame.Surface(size)
            self._menu_overlay.set_alpha(180)
            self._menu_overlay.fill((0, 0, 0))
        self.game.screen.blit(self._menu_overlay, (0, 0))

        # Menu panel (centered, 3x size of main menu) - Scaled based on 1600×900 reference
        # Uses IGOptMenuBG.png as background image
        scale = self.WINDOW_WIDTH / 1600.0
        menu_width = int(600 * scale)
        menu_height = int(750 * scale)  # Increased from 700 to prevent button overflow
        menu_x = (self.WINDOW_WIDTH - menu_width) // 2
        menu_y = (self.WINDOW_HEIGHT - menu_height) // 2

        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)

        # FPS OPTIMIZATION 5A: Cache scaled options menu background
        # Only re-scales when menu dimensions change (i.e., on window resize)
        options_menu_size = (menu_width, menu_height)
        if self._cached_options_menu_bg is None or self._cached_options_menu_bg_size != options_menu_size:
            self._cached_options_menu_bg = pygame.transform.scale(self.game.ingame_options_menu_bg, options_menu_size)
            self._cached_options_menu_bg_size = options_menu_size
        self.game.screen.blit(self._cached_options_menu_bg, (menu_x, menu_y))

        # Border padding - adjust content area to fit within the decorative border
        # Increased padding to ensure content fits nicely within the border
        border_padding_x = int(50 * scale)  # Left/right padding (increased from 30)
        border_padding_y_top = int(100 * scale)  # Top padding (increased significantly for title clearance)
        border_padding_y_bottom = int(50 * scale)  # Bottom padding (increased from 30)

        # Title (with padding adjustment - uses border padding for proper positioning)
        # FPS OPTIMIZATION 4.1: cached
        title_text = self.get_cached_text("Options", self.game.large_font, WHITE, "large")
        title_rect = title_text.get_rect(centerx=menu_x + menu_width // 2, y=menu_y + int(45 * scale))
        self.game.screen.blit(title_text, title_rect)

        # Separator line (with padding adjustment) - moved down 4px
        pygame.draw.line(self.game.screen, (150, 150, 150),
                        (menu_x + border_padding_x + int(10 * scale), menu_y + int(74 * scale)),
                        (menu_x + menu_width - border_padding_x - int(10 * scale), menu_y + int(74 * scale)), 2)

        # Define scrollable content area (adjusted for border)
        content_area_y = menu_y + int(85 * scale)
        content_area_height = menu_height - int(85 * scale) - int(70 * scale) - border_padding_y_bottom
        button_area_y = menu_y + menu_height - int(70 * scale) - border_padding_y_bottom

        # Create a subsurface for clipping scrollable content (with border padding)
        content_clip_rect = pygame.Rect(menu_x + border_padding_x, content_area_y,
                                       menu_width - 2 * border_padding_x, content_area_height)

        # Save original clip and set new clip area for content
        original_clip = self.game.screen.get_clip()
        self.game.screen.set_clip(content_clip_rect)

        # Apply scroll offset to content rendering (with border padding)
        content_y = content_area_y - self.game.options_menu_scroll_offset
        section_x = menu_x + border_padding_x + int(10 * scale)
        section_width = menu_width - 2 * border_padding_x - int(20 * scale)
        
        # Track where content starts (for calculating total height)
        content_start_y = content_y
        
        # ===== DISPLAY SETTINGS SECTION ===== (FPS OPTIMIZATION 4.1: cached)
        display_header = self.get_cached_text("Display Settings", self.game.font, WHITE, "font")
        self.game.screen.blit(display_header, (section_x, content_y))
        content_y += 35
        
        # Display settings box - dark brown background
        # Height grown from 140 to fit the VSync + FPS Limit row
        display_box = pygame.Rect(section_x, content_y, section_width, 185)
        pygame.draw.rect(self.game.screen, (60, 40, 30), display_box, border_radius=5)  # Dark brown
        pygame.draw.rect(self.game.screen, (100, 100, 100), display_box, 2, border_radius=5)
        
        # Resolution label and dropdown
        # FPS OPTIMIZATION 4.1: Use cached text for static label
        res_label = self.get_cached_text("Resolution:", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(res_label, (section_x + 15, content_y + 15))
        
        # Resolution dropdown button
        dropdown_x = section_x + 120
        dropdown_y = content_y + 10
        dropdown_width = 240
        dropdown_height = 35
        dropdown_rect = pygame.Rect(dropdown_x, dropdown_y, dropdown_width, dropdown_height)
        
        # Draw dropdown button
        dropdown_color = (70, 70, 80)
        self.game.helpers.draw_feedback_button(dropdown_rect, dropdown_color,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'options_control', 'resolution_dropdown',
                                  text=f"{self.game.temp_resolution[0]}x{self.game.temp_resolution[1]}",
                                  text_color=WHITE, font=self.game.small_font)
        self.game.resolution_dropdown_button = dropdown_rect
        
        # Draw dropdown arrow (use 'v' instead of Unicode ▼ for Cinzel font compatibility)
        # FPS OPTIMIZATION 4.1: Use cached text for static arrow
        arrow_text = self.get_cached_text("v", self.game.small_font, WHITE, "small_font")
        arrow_rect = arrow_text.get_rect(right=dropdown_x + dropdown_width - 10, centery=dropdown_y + dropdown_height // 2)
        self.game.screen.blit(arrow_text, arrow_rect)

        # Store dropdown position for later rendering (draw it last so it's on top)

        # Fullscreen checkbox
        checkbox_y = content_y + 65
        checkbox_x = section_x + 15
        checkbox_size = 25
        checkbox_rect = pygame.Rect(checkbox_x, checkbox_y, checkbox_size, checkbox_size)
        
        # Draw checkbox
        checkbox_color = (70, 70, 80)
        self.game.helpers.draw_feedback_button(checkbox_rect, checkbox_color,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'options_control', 'fullscreen_checkbox',
                                  text="", border_width=2)
        self.game.fullscreen_checkbox = checkbox_rect
        
        # Draw checkmark if enabled
        # FPS OPTIMIZATION 4.1: Use cached text for static checkmark
        if self.game.temp_fullscreen:
            checkmark = self.get_cached_text("X", self.game.font_bold, (100, 255, 100), "font_bold")
            checkmark_rect = checkmark.get_rect(center=checkbox_rect.center)
            self.game.screen.blit(checkmark, checkmark_rect)

        # Fullscreen label
        # FPS OPTIMIZATION 4.1: Use cached text for static label
        fullscreen_label = self.get_cached_text("Fullscreen Mode", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(fullscreen_label, (checkbox_x + checkbox_size + 10, checkbox_y + 3))
        
        # Current resolution indicator
        current_text = self.game._get_cached_text(
            f"Current: {self.game.current_resolution[0]}x{self.game.current_resolution[1]} {'(Fullscreen)' if self.game.is_fullscreen else '(Windowed)'}",
            self.game.small_font, (200, 200, 200)
        )
        self.game.screen.blit(current_text, (section_x + 15, checkbox_y + 35))

        # Note about fullscreen using native resolution
        note_text = self.game._get_cached_text(
            f"Note: Fullscreen always uses native resolution ({self.game.native_resolution[0]}x{self.game.native_resolution[1]})",
            self.game.small_font, (150, 150, 150)
        )
        self.game.screen.blit(note_text, (section_x + 15, checkbox_y + 55))

        # ---- VSync checkbox + FPS limit dropdown (same row) ----
        vsync_y = checkbox_y + 80
        vsync_checkbox = pygame.Rect(section_x + 15, vsync_y, 20, 20)
        self.game.helpers.draw_feedback_button(vsync_checkbox, (70, 70, 80),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'options_control', 'vsync_checkbox',
                                  text="", border_width=2)
        if self.game.temp_vsync:
            vs_mark = self.get_cached_text("X", self.game.font_bold, (100, 255, 100), "font_bold")
            self.game.screen.blit(vs_mark, vs_mark.get_rect(center=vsync_checkbox.center))
        self.game.display_vsync_checkbox = vsync_checkbox

        vsync_label = self.get_cached_text("VSync", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(vsync_label, (section_x + 43, vsync_y + 2))

        # FPS limit cycle button. When VSync is on the monitor paces frames, so the
        # manual cap is shown as inactive rather than implying it still applies.
        fps_label = self.get_cached_text("FPS Limit:", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(fps_label, (section_x + 120, vsync_y + 2))

        fps_rect = pygame.Rect(section_x + 195, vsync_y - 3, 110, 25)
        if self.game.temp_vsync:
            fps_value_text = "VSync"
            fps_btn_color = (55, 55, 62)
        elif self.game.temp_fps_limit and self.game.temp_fps_limit > 0:
            fps_value_text = f"{self.game.temp_fps_limit}"
            fps_btn_color = (70, 70, 80)
        else:
            fps_value_text = "Unlimited"
            fps_btn_color = (70, 70, 80)
        self.game.helpers.draw_feedback_button(fps_rect, fps_btn_color,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'options_control', 'fps_limit',
                                  text=fps_value_text, text_color=WHITE,
                                  font=self.game.small_font, border_width=1)
        fps_arrow = self.get_cached_text("v", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(fps_arrow, fps_arrow.get_rect(
            right=fps_rect.right - 8, centery=fps_rect.centery))
        self.game.display_fps_limit_dropdown = fps_rect

        content_y += 200  # Adjusted for the VSync/FPS row
        
        # ===== AUDIO SETTINGS SECTION =====
        audio_header = self.get_cached_text("Audio Settings", self.game.font, WHITE, "font")
        self.game.screen.blit(audio_header, (section_x, content_y))
        content_y += 35

        # Audio settings box
        audio_box_height = 155
        audio_box = pygame.Rect(section_x, content_y, section_width, audio_box_height)
        pygame.draw.rect(self.game.screen, (60, 40, 30), audio_box, border_radius=5)
        pygame.draw.rect(self.game.screen, (100, 80, 60), audio_box, 2, border_radius=5)

        audio_x = section_x + 15
        audio_y = content_y + 12
        audio_slider_x = audio_x + 10
        audio_slider_width = section_width - 60
        audio_slider_height = 6

        # Master Volume slider
        master_label = self.game._get_cached_text(
            f"Master Volume: {int(self.game.temp_master_volume * 100)}%", self.game.small_font, WHITE)
        self.game.screen.blit(master_label, (audio_x, audio_y))
        audio_y += 20

        slider_track = pygame.Rect(audio_slider_x, audio_y, audio_slider_width, audio_slider_height)
        pygame.draw.rect(self.game.screen, (60, 60, 70), slider_track, border_radius=3)
        thumb_pos = self.game.temp_master_volume
        thumb_x = int(audio_slider_x + thumb_pos * audio_slider_width)
        thumb_rect = pygame.Rect(thumb_x - 8, audio_y - 4, 16, 14)
        self.game.helpers.draw_feedback_button(thumb_rect, (100, 150, 100),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'audio_slider', 'master_volume',
                                  text="", border_width=1)
        self.game.audio_master_slider = (slider_track, 0.0, 1.0, thumb_rect)
        audio_y += 22

        # Music Volume slider
        music_label = self.game._get_cached_text(
            f"Music Volume: {int(self.game.temp_music_volume * 100)}%", self.game.small_font, WHITE)
        self.game.screen.blit(music_label, (audio_x, audio_y))
        audio_y += 20

        slider_track = pygame.Rect(audio_slider_x, audio_y, audio_slider_width, audio_slider_height)
        pygame.draw.rect(self.game.screen, (60, 60, 70), slider_track, border_radius=3)
        thumb_pos = self.game.temp_music_volume
        thumb_x = int(audio_slider_x + thumb_pos * audio_slider_width)
        thumb_rect = pygame.Rect(thumb_x - 8, audio_y - 4, 16, 14)
        self.game.helpers.draw_feedback_button(thumb_rect, (100, 150, 100),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'audio_slider', 'music_volume',
                                  text="", border_width=1)
        self.game.audio_music_slider = (slider_track, 0.0, 1.0, thumb_rect)
        audio_y += 22

        # SFX Volume slider
        sfx_label = self.game._get_cached_text(
            f"SFX Volume: {int(self.game.temp_sfx_volume * 100)}%", self.game.small_font, WHITE)
        self.game.screen.blit(sfx_label, (audio_x, audio_y))
        audio_y += 20

        slider_track = pygame.Rect(audio_slider_x, audio_y, audio_slider_width, audio_slider_height)
        pygame.draw.rect(self.game.screen, (60, 60, 70), slider_track, border_radius=3)
        thumb_pos = self.game.temp_sfx_volume
        thumb_x = int(audio_slider_x + thumb_pos * audio_slider_width)
        thumb_rect = pygame.Rect(thumb_x - 8, audio_y - 4, 16, 14)
        self.game.helpers.draw_feedback_button(thumb_rect, (100, 150, 100),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'audio_slider', 'sfx_volume',
                                  text="", border_width=1)
        self.game.audio_sfx_slider = (slider_track, 0.0, 1.0, thumb_rect)

        content_y += audio_box_height + 15
        
        # ===== GAMEPLAY SETTINGS SECTION ===== (FPS OPTIMIZATION 4.1: cached)
        gameplay_header = self.get_cached_text("Gameplay Settings", self.game.font, WHITE, "font")
        self.game.screen.blit(gameplay_header, (section_x, content_y))
        content_y += 35
        
        # Gameplay settings box - dark brown background
        gameplay_box_height = 240
        gameplay_box = pygame.Rect(section_x, content_y, section_width, gameplay_box_height)
        pygame.draw.rect(self.game.screen, (60, 40, 30), gameplay_box, border_radius=5)  # Dark brown
        pygame.draw.rect(self.game.screen, (100, 100, 100), gameplay_box, 2, border_radius=5)
        
        # Interior content
        gp_x = section_x + 15
        gp_y = content_y + 15
        
        # 1. Edge Scrolling checkbox
        edge_scroll_checkbox = pygame.Rect(gp_x, gp_y, 20, 20)
        checkbox_color = (70, 70, 80)
        self.game.helpers.draw_feedback_button(edge_scroll_checkbox, checkbox_color,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'gameplay_control', 'edge_scrolling',
                                  text="", border_width=2)
        # FPS OPTIMIZATION 4.1: Use cached text for static checkmark and label
        if self.game.temp_edge_scrolling_enabled:
            checkmark = self.get_cached_text("X", self.game.font_bold, (100, 255, 100), "font_bold")
            checkmark_rect = checkmark.get_rect(center=edge_scroll_checkbox.center)
            self.game.screen.blit(checkmark, checkmark_rect)

        edge_scroll_label = self.get_cached_text("Edge Scrolling", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(edge_scroll_label, (gp_x + 28, gp_y + 2))
        self.game.gameplay_edge_scrolling_checkbox = edge_scroll_checkbox
        
        gp_y += 28
        
        # 2. Edge Scrolling Mode dropdown (indented, only if edge scrolling enabled)
        if self.game.temp_edge_scrolling_enabled:
            # FPS OPTIMIZATION 4.1: Use cached text for static label
            mode_label = self.get_cached_text("  Mode:", self.game.small_font, WHITE, "small_font")
            self.game.screen.blit(mode_label, (gp_x + 10, gp_y))
            
            mode_dropdown_x = gp_x + 70
            mode_dropdown_y = gp_y - 3
            mode_dropdown_width = 120
            mode_dropdown_height = 25
            mode_dropdown_rect = pygame.Rect(mode_dropdown_x, mode_dropdown_y, mode_dropdown_width, mode_dropdown_height)
            
            mode_text = "Map Edge" if self.game.temp_edge_scrolling_mode == "map_edge" else "Window Edge"
            self.game.helpers.draw_feedback_button(mode_dropdown_rect, (70, 70, 80),
                                      self.game.mouse_pos, self.game.clicked_element,
                                      'gameplay_control', 'edge_scroll_mode',
                                      text=mode_text, text_color=WHITE, font=self.game.small_font,
                                      border_width=1)
            
            # Draw dropdown arrow (use 'v' instead of Unicode ▼ for Cinzel font compatibility)
            # FPS OPTIMIZATION 4.1: Use cached text for static arrow
            arrow = self.get_cached_text("v", self.game.small_font, WHITE, "small_font")
            arrow_rect = arrow.get_rect(right=mode_dropdown_x + mode_dropdown_width - 5, centery=mode_dropdown_y + mode_dropdown_height // 2)
            self.game.screen.blit(arrow, arrow_rect)

            self.game.gameplay_edge_scroll_mode_dropdown = mode_dropdown_rect
            gp_y += 30
        else:
            self.game.gameplay_edge_scroll_mode_dropdown = None

        # 3. Show Tooltips checkbox
        tooltips_checkbox = pygame.Rect(gp_x, gp_y, 20, 20)
        self.game.helpers.draw_feedback_button(tooltips_checkbox, checkbox_color,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'gameplay_control', 'tooltips',
                                  text="", border_width=2)
        # FPS OPTIMIZATION 4.1: Use cached text for static checkmark and label
        if self.game.temp_tooltips_enabled:
            checkmark = self.get_cached_text("X", self.game.font_bold, (100, 255, 100), "font_bold")
            checkmark_rect = checkmark.get_rect(center=tooltips_checkbox.center)
            self.game.screen.blit(checkmark, checkmark_rect)

        tooltips_label = self.get_cached_text("Show Tooltips", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(tooltips_label, (gp_x + 28, gp_y + 2))
        self.game.gameplay_tooltips_checkbox = tooltips_checkbox
        
        gp_y += 28
        
        # 4. Tooltip Delay dropdown (indented, only if tooltips enabled)
        if self.game.temp_tooltips_enabled:
            # FPS OPTIMIZATION 4.1: Use cached text for static label
            delay_label = self.get_cached_text("  Delay:", self.game.small_font, WHITE, "small_font")
            self.game.screen.blit(delay_label, (gp_x + 10, gp_y))
            
            delay_dropdown_x = gp_x + 70
            delay_dropdown_y = gp_y - 3
            delay_dropdown_width = 80
            delay_dropdown_height = 25
            delay_dropdown_rect = pygame.Rect(delay_dropdown_x, delay_dropdown_y, delay_dropdown_width, delay_dropdown_height)
            
            # Format delay text
            if self.game.temp_tooltip_delay_ms == -1:
                delay_text = "Never"
            else:
                delay_text = f"{self.game.temp_tooltip_delay_ms / 1000:.1f}s"
            
            self.game.helpers.draw_feedback_button(delay_dropdown_rect, (70, 70, 80),
                                      self.game.mouse_pos, self.game.clicked_element,
                                      'gameplay_control', 'tooltip_delay',
                                      text=delay_text, text_color=WHITE, font=self.game.small_font,
                                      border_width=1)
            
            # Draw dropdown arrow (use 'v' instead of Unicode ▼ for Cinzel font compatibility)
            # FPS OPTIMIZATION 4.1: Use cached text for static arrow
            arrow = self.get_cached_text("v", self.game.small_font, WHITE, "small_font")
            arrow_rect = arrow.get_rect(right=delay_dropdown_x + delay_dropdown_width - 5, centery=delay_dropdown_y + delay_dropdown_height // 2)
            self.game.screen.blit(arrow, arrow_rect)

            self.game.gameplay_tooltip_delay_dropdown = delay_dropdown_rect
            gp_y += 30
        else:
            self.game.gameplay_tooltip_delay_dropdown = None
        
        # 5. Camera Pan Speed slider
        pan_label = self.game._get_cached_text(f"Pan Speed: {int(self.game.temp_camera_pan_speed)}", self.game.small_font, WHITE)
        self.game.screen.blit(pan_label, (gp_x, gp_y))
        gp_y += 20
        
        # Slider track
        slider_x = gp_x + 10
        slider_width = section_width - 60
        slider_height = 6
        slider_track = pygame.Rect(slider_x, gp_y, slider_width, slider_height)
        pygame.draw.rect(self.game.screen, (60, 60, 70), slider_track, border_radius=3)
        
        # Slider thumb
        min_speed = 5.0
        max_speed = 20.0
        thumb_pos = (self.game.temp_camera_pan_speed - min_speed) / (max_speed - min_speed)
        thumb_x = int(slider_x + thumb_pos * slider_width)
        thumb_rect = pygame.Rect(thumb_x - 8, gp_y - 4, 16, 14)
        self.game.helpers.draw_feedback_button(thumb_rect, (100, 150, 100),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'gameplay_slider', 'pan_speed',
                                  text="", border_width=1)
        # Store slider data including thumb rect for drag detection
        self.game.gameplay_pan_speed_slider = (slider_track, min_speed, max_speed, thumb_rect)
        
        gp_y += 22
        
        # 6. Camera Zoom Speed slider
        zoom_label = self.game._get_cached_text(f"Zoom Speed: {self.game.temp_camera_zoom_speed:.2f}", self.game.small_font, WHITE)
        self.game.screen.blit(zoom_label, (gp_x, gp_y))
        gp_y += 20
        
        # Slider track
        slider_track = pygame.Rect(slider_x, gp_y, slider_width, slider_height)
        pygame.draw.rect(self.game.screen, (60, 60, 70), slider_track, border_radius=3)
        
        # Slider thumb
        min_zoom_speed = 0.05
        max_zoom_speed = 0.30
        thumb_pos = (self.game.temp_camera_zoom_speed - min_zoom_speed) / (max_zoom_speed - min_zoom_speed)
        thumb_x = int(slider_x + thumb_pos * slider_width)
        thumb_rect = pygame.Rect(thumb_x - 8, gp_y - 4, 16, 14)
        self.game.helpers.draw_feedback_button(thumb_rect, (100, 150, 100),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'gameplay_slider', 'zoom_speed',
                                  text="", border_width=1)
        # Store slider data including thumb rect for drag detection
        self.game.gameplay_zoom_speed_slider = (slider_track, min_zoom_speed, max_zoom_speed, thumb_rect)
        
        gp_y += 22
        
        # 7. Show FPS checkbox
        fps_checkbox = pygame.Rect(gp_x, gp_y, 20, 20)
        self.game.helpers.draw_feedback_button(fps_checkbox, checkbox_color,
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'gameplay_control', 'show_fps',
                                  text="", border_width=2)
        # FPS OPTIMIZATION 4.1: Use cached text for static checkmark and label
        if self.game.temp_show_fps:
            checkmark = self.get_cached_text("X", self.game.font_bold, (100, 255, 100), "font_bold")
            checkmark_rect = checkmark.get_rect(center=fps_checkbox.center)
            self.game.screen.blit(checkmark, checkmark_rect)

        fps_label = self.get_cached_text("Show FPS Counter", self.game.small_font, WHITE, "small_font")
        self.game.screen.blit(fps_label, (gp_x + 28, gp_y + 2))
        self.game.gameplay_fps_checkbox = fps_checkbox
        
        content_y += gameplay_box_height + 15
        
        # Calculate total content height
        total_content_height = content_y - content_start_y
        
        # Restore original clip rect (buttons should be outside scrollable area)
        self.game.screen.set_clip(original_clip)
        
        # Calculate max scroll and store for mouse wheel handler
        max_scroll = max(0, total_content_height - content_area_height)
        self.game.options_menu_max_scroll = max_scroll  # Store for wheel handler
        
        # Draw scrollbar if content is scrollable
        if total_content_height > content_area_height:
            # Scrollbar background track
            scrollbar_x = menu_x + menu_width - 20
            scrollbar_y = content_area_y
            scrollbar_width = 8
            scrollbar_track_height = content_area_height
            
            track_rect = pygame.Rect(scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_track_height)
            pygame.draw.rect(self.game.screen, (40, 40, 50), track_rect, border_radius=4)
            
            # Calculate scrollbar thumb size and position
            visible_ratio = content_area_height / total_content_height
            thumb_height = max(30, int(scrollbar_track_height * visible_ratio))
            
            # Clamp scroll offset
            self.game.options_menu_scroll_offset = max(0, min(self.game.options_menu_scroll_offset, max_scroll))
            
            # Calculate thumb position
            if max_scroll > 0:
                scroll_ratio = self.game.options_menu_scroll_offset / max_scroll
                thumb_y = scrollbar_y + int((scrollbar_track_height - thumb_height) * scroll_ratio)
            else:
                thumb_y = scrollbar_y
            
            # Draw scrollbar thumb
            thumb_rect = pygame.Rect(scrollbar_x, thumb_y, scrollbar_width, thumb_height)
            pygame.draw.rect(self.game.screen, (100, 100, 120), thumb_rect, border_radius=4)
            
            # Add subtle border to thumb
            pygame.draw.rect(self.game.screen, (120, 120, 140), thumb_rect, 1, border_radius=4)
        
        # ===== BOTTOM BUTTONS (outside scrollable area) =====
        # All three buttons in one line with equal sizes
        button_y = button_area_y + int(15 * scale)
        button_width = int(150 * scale)  # Same width for all three buttons
        button_height = int(35 * scale)  # Same height for all three buttons
        button_spacing = int(15 * scale)

        # Separator line above buttons (with border padding)
        pygame.draw.line(self.game.screen, (100, 100, 100),
                        (menu_x + border_padding_x + int(10 * scale), button_area_y),
                        (menu_x + menu_width - border_padding_x - int(10 * scale), button_area_y), 2)

        # Calculate total width for three buttons and center them
        total_width = button_width * 3 + button_spacing * 2
        start_x = menu_x + (menu_width - total_width) // 2

        # Apply button (use bold font)
        apply_rect = pygame.Rect(start_x, button_y, button_width, button_height)
        self.game.helpers.draw_feedback_button(apply_rect, (80, 150, 80),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'options_button', 'apply',
                                  text="Apply", text_color=WHITE, font=self.game.font_bold)
        self.game.options_apply_button = apply_rect

        # Reset to Defaults button (middle position, same size as others)
        reset_x = start_x + button_width + button_spacing
        reset_rect = pygame.Rect(reset_x, button_y, button_width, button_height)
        self.game.helpers.draw_feedback_button(reset_rect, (120, 120, 80),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'options_button', 'reset',
                                  text="Reset", text_color=WHITE, font=self.game.font_bold)
        self.game.options_reset_button = reset_rect

        # Back button (use bold font)
        back_x = reset_x + button_width + button_spacing
        back_rect = pygame.Rect(back_x, button_y, button_width, button_height)
        self.game.helpers.draw_feedback_button(back_rect, (150, 80, 80),
                                  self.game.mouse_pos, self.game.clicked_element,
                                  'options_button', 'back',
                                  text="Back", text_color=WHITE, font=self.game.font_bold)
        self.game.options_back_button = back_rect
        
        # ===== DRAW DROPDOWN OPTIONS LAST (on top of everything) =====
        # This ensures the dropdown list isn't covered by other UI elements
        if self.game.resolution_dropdown_open:
            self.game.resolution_option_buttons = []
            option_y = dropdown_y + dropdown_height + 2
            
            # Create a semi-transparent background for the dropdown list
            dropdown_list_height = len(self.game.available_resolutions) * 32
            dropdown_bg = pygame.Rect(dropdown_x, option_y, dropdown_width, dropdown_list_height)
            pygame.draw.rect(self.game.screen, (50, 50, 60), dropdown_bg)
            pygame.draw.rect(self.game.screen, (100, 100, 100), dropdown_bg, 2)
            
            for resolution in self.game.available_resolutions:
                option_rect = pygame.Rect(dropdown_x, option_y, dropdown_width, 30)
                
                # Highlight current selection
                if resolution == self.game.temp_resolution:
                    option_color = (90, 90, 100)
                else:
                    option_color = (60, 60, 70)
                
                # Add "(Native)" marker for native resolution
                if resolution == self.game.native_resolution:
                    res_text = f"{resolution[0]}x{resolution[1]} (Native)"
                else:
                    res_text = f"{resolution[0]}x{resolution[1]}"
                
                self.game.helpers.draw_feedback_button(option_rect, option_color,
                                          self.game.mouse_pos, self.game.clicked_element,
                                          'resolution_option', f"{resolution[0]}x{resolution[1]}",
                                          text=res_text,
                                          text_color=WHITE, font=self.game.small_font,
                                          border_width=1)
                
                self.game.resolution_option_buttons.append((option_rect, resolution))
                option_y += 32
    
    # ========================================================================
    # ACTION QUEUE (sidebar overhaul P2)
    # ========================================================================
    # kind -> (label, title colour, text colour, card fill gradient (top, bottom))
    ORDER_KIND_STYLE = {
        # Fills kept dark and slightly muted so the cards sit on the tapestry, not on it
        'attack': ('Attack', (255, 128, 104), (255, 216, 202), ((62, 24, 20), (34, 12, 10))),
        'own': ('Move', (146, 186, 255), (210, 225, 255), ((26, 34, 62), (13, 17, 34))),
        'ally': ('Reinforce Ally', (140, 224, 140), (210, 245, 210), ((24, 50, 30), (11, 27, 15))),
    }
    ORDER_KIND_ICONS = {'attack': 'assets/mapicons/BattleIcon1.png', 'ally': 'assets/mapicons/AllianceIcon1.png'}
    UNIT_ORDER = ('Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain')
    UNIT_PLURALS = {'Swordsman': 'Swordsmen', 'Archer': 'Archers', 'Pikeman': 'Pikemen',
                    'Cavalry': 'Cavalry', 'Captain': 'Captains'}
    CANCEL_TINT = (255, 108, 96)

    def _order_kind(self, player, to_territory):
        """'own' / 'ally' / 'attack' — mirrors game_state/military.py (create order).

        The old card was red whenever the target owner differed from the player, so a
        reinforcement into an ally's territory looked like an attack.
        """
        gs = self.game.game_state
        owner = gs.territory_owners.get(to_territory, -1)
        if owner == player:
            return 'own'
        if owner is not None and owner >= 0 and player is not None and player >= 0 and gs.are_allies(player, owner):
            return 'ally'
        return 'attack'

    def _order_composition(self, from_territory, player, unit_ids, army_count):
        """[(unit_type, count)] for an order, or [(None, army_count)] when unknown.

        Orders carry unit ids; their types live on the source garrison's unit dicts.
        Count-only orders (no unit_ids) fall back to the plain army count.
        """
        counts = {}
        if unit_ids:
            wanted = set(unit_ids)
            garrison = self.game.game_state.territory_garrisons.get(from_territory, {}).get(player, {}) or {}
            for unit in garrison.get('units', []) or []:
                if unit.get('id') in wanted:
                    unit_type = unit.get('type') or 'Swordsman'
                    counts[unit_type] = counts.get(unit_type, 0) + 1
        if not counts:
            return [(None, army_count)]
        ordered = [(t, counts.pop(t)) for t in self.UNIT_ORDER if t in counts]
        return ordered + sorted(counts.items(), key=lambda item: str(item[0]))

    def _queue_entries(self, local_player):
        """Cards to show: queued orders, then (simultaneous mode, after Ready) the
        orders already submitted — read-only, since sim_state refuses changes then."""
        from types import SimpleNamespace
        gs = self.game.game_state
        entries = []
        for i, order in enumerate(o for o in gs.movement_orders if o.player == local_player):
            entries.append(SimpleNamespace(
                order=order, index=i, submitted=False, player=order.player,
                from_territory=order.from_territory, to_territory=order.to_territory,
                army_count=order.army_count, unit_ids=getattr(order, 'unit_ids', None) or [],
                via=getattr(order, 'intermediate_territory', None)))
        sim_state = getattr(self.game, 'sim_state', None)
        if sim_state is not None and getattr(sim_state, 'players_ready', {}).get(local_player, False):
            for order in sim_state.player_orders.get(local_player, []) or []:
                if order.get('type') != 'movement':
                    continue
                # Sim order dicts don't carry the Captain 2-hop via-territory
                entries.append(SimpleNamespace(
                    order=None, index=None, submitted=True, player=local_player,
                    from_territory=order.get('from_territory'), to_territory=order.get('to_territory'),
                    army_count=order.get('army_count', 0), unit_ids=order.get('unit_ids') or [], via=None))
        return entries

    def _queue_entry_key(self, entry):
        """Everything a card's look depends on (changes -> the card is re-laid out)."""
        owner = self.game.game_state.territory_owners.get(entry.to_territory, -1)
        return (id(entry.order) if entry.order is not None else None, entry.from_territory,
                entry.to_territory, entry.army_count, tuple(entry.unit_ids), entry.via,
                entry.submitted, owner)

    def _order_card_layout(self, entry, width):
        """Measure one card (memoised per entry key + width + text scale)."""
        w = self.game.sidebar_widgets
        key = (self._queue_entry_key(entry), int(width), w.scale)
        cache = self.__dict__.setdefault('_queue_layout_cache', OrderedDict())
        lay = cache.get(key)
        if lay is not None:
            cache.move_to_end(key)
            return lay
        lay = self._measure_order_card(entry, width)
        lay['key'] = key
        cache[key] = lay
        if len(cache) > 256:
            cache.popitem(last=False)
        return lay

    def _measure_order_card(self, entry, width):
        """Layout of one card. Returns a dict the compose step uses unchanged."""
        w = self.game.sidebar_widgets
        s = w.scale
        border = max(7, int(round(8 * s)))
        pad = border + 5
        inner_w = width - 2 * pad
        body_h = w.font('body').get_linesize()
        small_h = w.font('small_bold').get_linesize()
        kind = self._order_kind(entry.player, entry.to_territory)

        # Route: "From ➜ To" on one line when it fits, else "From" / "➜ To"
        arrow_w = int(16 * s) + 8
        from_name, to_name = str(entry.from_territory), str(entry.to_territory)
        one_line = w.font('body').size(from_name)[0] + arrow_w + w.font('body').size(to_name)[0] <= inner_w
        if one_line:
            route = [(from_name, to_name)]
        else:
            route = [(w.fit_text(from_name, 'body', inner_w), None),
                     (None, w.fit_text(to_name, 'body', inner_w - arrow_w))]

        # Unit composition chips, wrapped into rows
        icon = int(round(20 * s))
        rows, row_w = [[]], 0
        for unit_type, count in self._order_composition(entry.from_territory, entry.player,
                                                        entry.unit_ids, entry.army_count):
            label = f"×{count}" if unit_type else f"{count} unit{'s' if count != 1 else ''}"
            chip_w = (icon + 3 if unit_type else 0) + w.font('small_bold').size(label)[0] + 8
            if rows[-1] and row_w + chip_w > inner_w:
                rows.append([])
                row_w = 0
            rows[-1].append((unit_type, label, chip_w))
            row_w += chip_w
        chip_row_h = max(icon, small_h)

        icon_px = max(small_h, int(16 * s))
        button_h = 0 if entry.submitted else max(20, int(round(22 * s)))
        height = (pad + icon_px + 4 + body_h * len(route)
                  + (body_h if entry.via else 0) + 5 + chip_row_h * len(rows) + 3 * (len(rows) - 1)
                  + (6 + button_h if button_h else 0) + pad)

        # Hover areas of the unit chips (card-local), for the "6× Swordsmen" tooltip.
        # Mirrors the chip placement in _compose_order_card exactly.
        chip_hits = []
        chip_y = pad + icon_px + 4 + body_h * len(route) + (body_h if entry.via else 0) + 5
        for row in rows:
            x = pad
            for chip in row:          # chip = (unit_type, label, chip_w)
                if chip[0]:
                    chip_hits.append((pygame.Rect(x, chip_y, chip[2] - 8, chip_row_h), chip[0], chip[1]))
                x += chip[2]
            chip_y += chip_row_h + 3

        return {'kind': kind, 'border': border, 'pad': pad, 'route': route, 'arrow_w': arrow_w,
                'rows': rows, 'icon': icon, 'icon_px': icon_px, 'chip_row_h': chip_row_h,
                'button_h': button_h, 'body_h': body_h, 'small_h': small_h, 'height': height,
                'width': int(width), 'chip_hits': chip_hits}

    @staticmethod
    def _order_button_rect(lay, card_rect, scale):
        """Cancel Order button inside a card (same rect for drawing and clicking)."""
        pad = lay['pad']
        bw = min(card_rect.w - 2 * pad, int(round(118 * scale)))
        button = pygame.Rect(0, 0, bw, lay['button_h'])
        button.midbottom = (card_rect.centerx, card_rect.bottom - pad + 2)
        return button

    @staticmethod
    def _draw_route_arrow(surface, x, cy, length, color):
        """Small drawn arrow (shaft + chevron head) between territory names."""
        head = max(4, length // 3)
        pygame.draw.line(surface, color, (x, cy), (x + length - 2, cy), 2)
        pygame.draw.lines(surface, color, False, [(x + length - head - 1, cy - head), (x + length - 1, cy),
                                                  (x + length - head - 1, cy + head)], 2)

    def _compose_order_card(self, entry, lay, card_state, button_state, cancel_locked):
        """One card fully drawn onto its own surface, cached per interaction state.

        PERFORMANCE: drawing a card piece by piece (frame, ~10 texts, icons, button)
        every frame cost ~0.65 ms with 40 orders; a composed card is one blit. The
        cache holds a handful of states per visible card (normal / hover / button
        hover / flash / locked) and is keyed by the card's layout key.
        """
        key = (lay['key'], card_state, button_state, cancel_locked)
        cache = self.__dict__.setdefault('_queue_card_cache', OrderedDict())
        surf = cache.get(key)
        if surf is not None:
            cache.move_to_end(key)
            return surf

        game = self.game
        w = game.sidebar_widgets
        label, title_color, text_color, fill = self.ORDER_KIND_STYLE[lay['kind']]
        width, height, pad = lay['width'], lay['height'], lay['pad']
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        surf.blit(w.card('wood', (width, height), lay['border'], fill, card_state), (0, 0))
        rect = surf.get_rect()

        x0, y = pad, pad
        # Title row: kind icon + kind label (+ "Submitted" marker)
        icon_px = lay['icon_px']
        icon_path = self.ORDER_KIND_ICONS.get(lay['kind'])
        if icon_path:
            icon = w.icon(icon_path, icon_px, crop=True)
        else:
            flags = getattr(game, 'army_flag_icons', {}).get(entry.player, {}) or {}
            icon = w.icon_surface(('flag', entry.player), flags.get(1), icon_px, crop=True)
        if icon is not None:
            surf.blit(icon, icon.get_rect(midleft=(x0, y + icon_px // 2)))
        title = label.upper() + ('  •  SUBMITTED' if entry.submitted else '')
        title_surf = w.text(w.fit_text(title, 'small_bold', width - 2 * pad - icon_px - 6), 'small_bold', title_color)
        surf.blit(title_surf, title_surf.get_rect(midleft=(x0 + icon_px + 6, y + icon_px // 2)))
        y += icon_px + 4

        # Route
        for from_name, to_name in lay['route']:
            x = x0
            if from_name:
                text = w.text(from_name, 'body', text_color)
                surf.blit(text, (x, y))
                x += text.get_width() + 4
            if to_name:
                self._draw_route_arrow(surf, x, y + lay['body_h'] // 2, lay['arrow_w'] - 8, title_color)
                x += lay['arrow_w']
                text = w.text(w.fit_text(to_name, 'body', width - pad - x), 'body', text_color)
                surf.blit(text, (x, y))
            y += lay['body_h']
        if entry.via:
            via = w.text(w.fit_text(f"via {entry.via}", 'italic', width - 2 * pad), 'italic', (200, 190, 170))
            surf.blit(via, (x0 + 4, y))
            y += lay['body_h']
        y += 5

        # Unit composition chips
        for row in lay['rows']:
            x = x0
            for unit_type, chip_label, chip_w in row:
                if unit_type:
                    icon = w.icon_surface(('unit', unit_type), getattr(game, 'unit_icons', {}).get(unit_type),
                                          lay['icon'], frame=True)
                    surf.blit(icon, (x, y + (lay['chip_row_h'] - lay['icon']) // 2))
                    x += lay['icon'] + 3
                count = w.text(chip_label, 'small_bold', (236, 226, 204))
                surf.blit(count, count.get_rect(midleft=(x, y + lay['chip_row_h'] // 2)))
                x += count.get_width() + 8
            y += lay['chip_row_h'] + 3

        # Cancel Order (queued orders only)
        if lay['button_h']:
            button = self._order_button_rect(lay, rect, w.scale)
            w.blit_button(surf, button, 'Cancel Order', art='campaign', tint=self.CANCEL_TINT,
                          state='locked' if cancel_locked else button_state, role='small_bold')

        # Display alpha format: noticeably faster to blend every frame
        surf = self.game.sidebar_widgets.display_alpha(surf)
        cache[key] = surf
        if len(cache) > 96:
            cache.popitem(last=False)
        return surf

    def _draw_order_card(self, entry, lay, rect, viewport, cancel_locked):
        """Blit one (cached) card at `rect`; returns the clipped Cancel Order rect or None."""
        game = self.game
        w = game.sidebar_widgets
        button = self._order_button_rect(lay, rect, w.scale) if lay['button_h'] else None
        over_button = button is not None and not cancel_locked and w.hover(button, viewport)
        card_state = 'hover' if (w.hover(rect, viewport) and not over_button) else 'normal'
        button_state = 'normal'
        if button is not None and not cancel_locked:
            flash_key = ('sidebar_cancel_order', getattr(entry.order, 'order_id', None))
            if getattr(game, 'clicked_element', None) == flash_key:
                button_state = 'flash'
            elif over_button:
                button_state = 'hover'
        game.screen.blit(self._compose_order_card(entry, lay, card_state, button_state, cancel_locked),
                         rect.topleft)
        return w.clip_hit(button, viewport) if button is not None else None

    def _draw_action_queue_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """Action Queue tab: the local player's queued orders as wooden cards.

        Each card: order kind (Attack / Move / Reinforce Ally, coloured fill + icon),
        "From ➜ To" (plus "via X" for Captain 2-hop moves), unit composition chips and a
        Cancel Order button. The list scrolls (mouse wheel, pixel ScrollState) inside a
        clipped viewport that ends above the pinned CANCEL ALL footer — the old cards
        could run underneath it. In simultaneous mode, orders already submitted with
        Ready are listed read-only ("Submitted").

        PERFORMANCE: card layouts are memoised per order and each visible card is a
        pre-composed surface (see _compose_order_card), so a frame costs one blit per
        visible card regardless of queue length.

        Click rects (consumed by Game.handle_order_sidebar_click):
            order_cancel_buttons: [(clipped rect, order, player_order_index)] - visible only
            cancel_all_button:    rect or None
            order_card_rects:     [(clipped rect, entry)] - visible cards
        """
        from ui.sidebar_layout import content_geometry, SCROLLBAR_W
        game = self.game
        w = game.sidebar_widgets
        screen = game.screen
        local_player = game.get_local_player()

        # Reset every frame, BEFORE any early return: otherwise the X of the last
        # cancelled order stayed clickable and hit whatever order came next.
        game.order_cancel_buttons = []
        game.order_card_rects = []
        game.cancel_all_button = None
        # Player whose orders this sidebar shows — the CANCEL ALL button cancels only these
        game.order_sidebar_player = local_player

        full = content_geometry(sidebar_x, sidebar_y, sidebar_height, panel_width=sidebar_width)
        half = min(full.center_x - full.x, full.right - full.center_x)
        header = w.section_header("Action Queue", 2 * half, role='title')
        screen.blit(header, (full.center_x - half, content_start_y))
        list_top = content_start_y + header.get_height() + 8

        entries = self._queue_entries(local_player)
        if not entries:
            empty = w.text("No orders queued", 'body', (200, 170, 150))
            screen.blit(empty, empty.get_rect(center=(full.center_x, list_top + 30)))
            hint_y = list_top + 50
            for line in w.wrap("Select an army, then right-click a territory to give an order.", 'italic',
                               full.width - 10):
                hint = w.text(line, 'italic', (170, 150, 130))
                screen.blit(hint, hint.get_rect(midtop=(full.center_x, hint_y)))
                hint_y += hint.get_height()
            game.sidebar_scroll['action_queue'].set_content(0, 0)
            return

        # Tutorial/mission locks: the clicks are refused, so the buttons look locked
        mission = getattr(game, 'tutorial_mission', None)
        cancel_locked = bool(mission and mission.active and not mission.is_action_allowed('cancel_order'))
        cancel_all_locked = bool(mission and mission.active and not mission.is_action_allowed('cancel_all_orders'))

        has_queued = any(not e.submitted for e in entries)
        btn_h = max(28, int(round(34 * w.scale)))
        footer_h = (btn_h + 18) if has_queued else 8
        geo = content_geometry(sidebar_x, sidebar_y, sidebar_height, header_h=list_top - sidebar_y,
                               footer_h=footer_h, panel_width=sidebar_width, scrollbar=True)
        viewport = pygame.Rect(geo.x, geo.top, geo.width, max(1, geo.bottom - geo.top))

        # Lay the cards out top-down (layouts memoised, so this is cheap per frame)
        gap = 6
        items = []
        y = 0
        submitted_started = False
        for entry in entries:
            if entry.submitted and not submitted_started:
                submitted_started = True
                sub_hdr = w.section_header("Submitted", geo.width, role='heading')
                items.append(('header', sub_hdr, y, sub_hdr.get_height()))
                y += sub_hdr.get_height() + gap
            lay = self._order_card_layout(entry, geo.width)
            items.append(('card', (entry, lay), y, lay['height']))
            y += lay['height'] + gap
        content_h = max(0, y - gap)

        scroll = game.sidebar_scroll['action_queue']
        scroll.set_content(content_h, viewport.h)
        top = viewport.y - scroll.view_top()

        previous_clip = w.begin_clip(viewport)
        try:
            for kind, payload, item_y, item_h in items:
                screen_y = top + item_y
                if screen_y + item_h < viewport.top:
                    continue
                if screen_y > viewport.bottom:
                    break
                if kind == 'header':
                    screen.blit(payload, (viewport.x, screen_y))
                    continue
                entry, lay = payload
                rect = pygame.Rect(viewport.x, screen_y, viewport.w, item_h)
                cancel_rect = self._draw_order_card(entry, lay, rect, viewport, cancel_locked)
                card_hit = w.clip_hit(rect, viewport)
                if card_hit is not None:
                    game.order_card_rects.append((card_hit, entry))
                    # Unit chip tooltip ("6× Swordsmen"), drawn at the end of the frame
                    if w.hover(card_hit, viewport):
                        mx, my = game.mouse_pos
                        for hit, unit_type, chip_label in lay['chip_hits']:
                            if hit.move(rect.topleft).collidepoint(mx, my):
                                count = chip_label.lstrip('×')
                                name = unit_type if count == '1' else self.UNIT_PLURALS.get(unit_type, unit_type)
                                game.sidebar_tooltip = (f"{count}× {name}", (mx, my))
                                break
                if cancel_rect is not None and entry.order is not None:
                    # Format: (rect, order, player_order_index). The order object identifies
                    # the order to cancel locally; the index (among this player's orders) is
                    # what the ORDER_REMOVE network message carries.
                    game.order_cancel_buttons.append((cancel_rect, entry.order, entry.index))
        finally:
            w.end_clip(previous_clip)

        w.draw_scrollbar(pygame.Rect(geo.right + 2, viewport.y, SCROLLBAR_W, viewport.h), scroll)

        # CANCEL ALL — pinned below the list, centred on the visible tapestry
        if has_queued:
            bw = min(full.width, int(round(190 * w.scale)))
            cancel_all = pygame.Rect(0, 0, bw, btn_h)
            cancel_all.midbottom = (full.center_x, sidebar_y + sidebar_height - 10)
            w.draw_button(cancel_all, 'Cancel All', art='campaign', tint=self.CANCEL_TINT,
                          flash_key=('sidebar_cancel_all', None), locked=cancel_all_locked, role='heading')
            game.cancel_all_button = cancel_all
    
    # ========================================================================
    # ACTION LOG + CHAT (sidebar overhaul P3)
    # ========================================================================
    # category -> marker / tint colour
    LOG_CATEGORY_COLORS = {
        'battle': (236, 120, 100), 'conquest': (236, 172, 92), 'economy': (226, 198, 112),
        'construction': (204, 178, 136), 'training': (160, 196, 232), 'research': (140, 196, 255),
        'hero': (206, 156, 240), 'orders': (176, 188, 202), 'victory': (245, 214, 140),
        'error': (255, 104, 86), 'other': (200, 190, 176),
    }
    LOG_CHILD_COLOR = (172, 160, 144)

    @staticmethod
    def _mix(a, b, t):
        return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def _layout_log_row(self, row, width, first):
        """Pixel layout of one model row: (height, draw spec). Pure measuring, no drawing."""
        w = self.game.sidebar_widgets
        if row.kind in ('section', 'turn'):
            line_h = w.font('heading').get_linesize()
            top = 0 if first else 10
            return top + line_h + 8, {'kind': 'band', 'text': row.text.upper(), 'top': top, 'h': line_h + 8}
        if row.kind == 'subturn':
            line_h = w.font('italic').get_linesize()
            top = 0 if first else 4
            return top + line_h + 2, {'kind': 'subturn', 'text': row.text, 'top': top}
        if row.kind == 'victory':
            line_h = w.font('heading').get_linesize()
            lines = []
            for text in row.text.split('\n'):
                lines.extend(w.wrap(text, 'heading', width - 16))
            top = 0 if first else 8
            return top + 12 + line_h * len(lines), {'kind': 'victory', 'lines': lines, 'top': top, 'line_h': line_h}
        if row.kind == 'banner':
            line_h = w.font('body_bold').get_linesize()
            lines = w.wrap(row.text, 'body_bold', width - 14)
            top = 0 if first else 7
            return top + line_h * len(lines) + 1, {'kind': 'banner', 'lines': lines, 'top': top,
                                                   'line_h': line_h, 'category': row.category}
        # 'entry'
        if row.indent == 0:
            role, dx = 'body', 14
            top = 0 if first else 6
        else:
            role, dx = 'small', 14 + 10 * (row.indent - 1)
            top = 1
        line_h = w.font(role).get_linesize()
        lines = w.wrap(row.text, role, width - dx)
        return top + line_h * len(lines), {'kind': 'entry', 'lines': lines, 'top': top, 'line_h': line_h,
                                           'role': role, 'dx': dx, 'indent': row.indent,
                                           'category': row.category}

    def _update_log_layout(self, width):
        """Bring the Action Log model + its pixel layout up to date (incremental).

        Returns (items, ys, total_h, grew_px): items[i] = (height, spec, row) and
        ys[i] = its content-space y. Only rows changed since the last frame are
        measured; nothing scans the whole history per frame any more.
        """
        from rendering.action_log_model import ActionLogModel
        game = self.game
        gs = game.game_state
        w = game.sidebar_widgets
        state = self.__dict__.setdefault('_log_state', {'model': ActionLogModel(), 'items': [], 'ys': [],
                                                        'total': 0, 'key': None})
        model = state['model']
        names = [gs.get_player_name(i) for i in range(gs.num_players)]
        changed = model.update(gs.messages, game.get_local_player(), names,
                               getattr(game, 'sidebar_log_filter', None))
        key = (int(width), w.scale)
        if key != state['key']:
            state['key'] = key
            changed = 0
            state['items'], state['ys'], state['total'] = [], [], 0
        if changed is None:
            return state['items'], state['ys'], state['total'], 0
        rows = model.rows
        old_total = state['total']
        rebuilt = changed == 0
        items = state['items'][:changed]
        ys = state['ys'][:changed]
        y = (ys[-1] + items[-1][0]) if items else 0
        for i in range(changed, len(rows)):
            height, spec = self._layout_log_row(rows[i], width, first=(i == 0))
            items.append((height, spec, rows[i]))
            ys.append(y)
            y += height
        state['items'], state['ys'], state['total'] = items, ys, y
        grew = 0 if rebuilt else max(0, y - old_total)
        return items, ys, y, grew

    def _draw_log_item(self, spec, x, y, width):
        """Draw one laid-out Action Log row at content-column x, screen y."""
        game = self.game
        w = game.sidebar_widgets
        screen = game.screen
        kind = spec['kind']
        y += spec['top']
        if kind == 'band':
            surf, area = w.band(width, spec['h'], (212, 170, 80, 38))
            screen.blit(surf, (x, y), area)
            pygame.draw.line(screen, (150, 112, 52), (x, y), (x + width - 1, y), 1)
            pygame.draw.line(screen, (150, 112, 52), (x, y + spec['h'] - 1), (x + width - 1, y + spec['h'] - 1), 1)
            label = w.text(spec['text'], 'heading', (245, 214, 140))
            screen.blit(label, label.get_rect(center=(x + width // 2, y + spec['h'] // 2)))
        elif kind == 'subturn':
            label = w.text(w.fit_text(spec['text'], 'italic', width - 30), 'italic', (186, 170, 150))
            screen.blit(label, (x + 2, y))
            line_y = y + label.get_height() // 2
            if x + label.get_width() + 10 < x + width:
                pygame.draw.line(screen, (110, 84, 48), (x + label.get_width() + 8, line_y), (x + width - 1, line_y), 1)
        elif kind == 'victory':
            block = pygame.Rect(x, y, width, 12 + spec['line_h'] * len(spec['lines']))
            surf, area = w.band(block.w, block.h, (60, 40, 14, 170))
            screen.blit(surf, block.topleft, area)
            pygame.draw.rect(screen, (212, 170, 80), block, 1, border_radius=3)
            ly = y + 6
            for line in spec['lines']:
                label = w.text(line, 'heading', (245, 214, 140))
                screen.blit(label, label.get_rect(midtop=(x + width // 2, ly)))
                ly += spec['line_h']
        elif kind == 'banner':
            color = self.LOG_CATEGORY_COLORS.get(spec['category'], (220, 200, 170))
            self._draw_log_marker(x + 4, y + spec['line_h'] // 2, color, big=True)
            ly = y
            for line in spec['lines']:
                screen.blit(w.text(line, 'body_bold', self._mix(color, (255, 240, 215), 0.35)), (x + 14, ly))
                ly += spec['line_h']
        else:  # entry
            color = self.LOG_CATEGORY_COLORS.get(spec['category'], (220, 200, 170))
            if spec['indent'] == 0:
                self._draw_log_marker(x + 4, y + spec['line_h'] // 2, color)
                text_color = self._mix(color, (238, 226, 204), 0.55)
            else:
                text_color = self.LOG_CHILD_COLOR
            ly = y
            for line in spec['lines']:
                screen.blit(w.text(line, spec['role'], text_color), (x + spec['dx'], ly))
                ly += spec['line_h']

    def _draw_log_marker(self, cx, cy, color, big=False):
        """Small category diamond in front of a log line."""
        r = 4 if big else 3
        pygame.draw.polygon(self.game.screen, color, [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)])

    def _draw_scrolling_list(self, items, ys, total_h, viewport, scroll, draw_item):
        """Draw the rows of a bottom-anchored list that intersect the viewport."""
        import bisect
        w = self.game.sidebar_widgets
        scroll.set_content(total_h, viewport.h)
        view_top = scroll.view_top()
        # Short lists sit at the top of the viewport
        origin = viewport.y - view_top
        first = max(0, bisect.bisect_right(ys, view_top) - 1)
        previous_clip = w.begin_clip(viewport)
        try:
            for i in range(first, len(items)):
                screen_y = origin + ys[i]
                if screen_y > viewport.bottom:
                    break
                draw_item(items[i], screen_y)
        finally:
            w.end_clip(previous_clip)

    def _draw_action_log_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """
        Action Log tab: the game's event log, organised and readable.

        Grouped by turn ("Turn k" bands, "<Name>'s turn" sub-headings), each entry with
        a category colour + marker (battle, conquest, economy, buildings, training,
        research, heroes, orders, warnings), battle details nested under their battle
        heading, victory/elimination as one block. Model: rendering/action_log_model.py.

        Scrolling: pixel ScrollState anchored at the bottom - the newest entry is always
        visible at offset 0, and the view holds still while new entries arrive if the
        reader has scrolled back. (The old message-count offset used the UNFILTERED
        count, so it scrolled past the end, and could hide the newest lines.)
        """
        from ui.sidebar_layout import content_geometry, SCROLLBAR_W
        game = self.game
        w = game.sidebar_widgets
        screen = game.screen

        full = content_geometry(sidebar_x, sidebar_y, sidebar_height, panel_width=sidebar_width)
        half = min(full.center_x - full.x, full.right - full.center_x)
        header = w.section_header("Action Log", 2 * half, role='title')
        screen.blit(header, (full.center_x - half, content_start_y))
        list_top = content_start_y + header.get_height() + 8

        geo = content_geometry(sidebar_x, sidebar_y, sidebar_height, header_h=list_top - sidebar_y,
                               footer_h=8, panel_width=sidebar_width, scrollbar=True)
        viewport = pygame.Rect(geo.x, geo.top, geo.width, max(1, geo.bottom - geo.top))
        items, ys, total_h, grew = self._update_log_layout(geo.width)
        scroll = game.sidebar_scroll['action_log']
        if grew:
            scroll.on_content_grew(grew)

        if not items:
            empty = w.text("No events yet", 'body', (200, 170, 150))
            screen.blit(empty, empty.get_rect(center=(full.center_x, list_top + 30)))
            scroll.set_content(0, viewport.h)
            return

        self._draw_scrolling_list(items, ys, total_h, viewport, scroll,
                                  lambda item, y: self._draw_log_item(item[1], viewport.x, y, viewport.w))
        w.draw_scrollbar(pygame.Rect(geo.right + 2, viewport.y, SCROLLBAR_W, viewport.h), scroll)

    def _update_chat_layout(self, width):
        """Chat messages laid out in pixels; re-filtered only when a message arrives."""
        game = self.game
        gs = game.game_state
        w = game.sidebar_widgets
        viewer = game.get_local_player()
        source = gs.chat_messages
        key = (id(source), viewer, int(width), w.scale)
        state = self.__dict__.setdefault('_chat_state', {'key': None, 'count': 0, 'items': [], 'ys': [],
                                                         'total': 0, 'visible': 0})
        if state['key'] != key or len(source) < state['count']:
            state.update(key=key, count=0, items=[], ys=[], total=0, visible=0)
        if len(source) == state['count']:
            return state['items'], state['ys'], state['total'], 0

        # Team chat is filtered per viewer; filtering is per message, so the visible
        # list only grows at its end and new entries can be appended
        visible = gs.get_visible_chat_messages(viewer)
        old_total = state['total']
        y = state['total']
        name_h = w.font('small_bold').get_linesize()
        body_h = w.font('body').get_linesize()
        for message in visible[state['visible']:]:
            # Format: (timestamp, player_id, message[, channel]) - index access (old saves: 3-tuple)
            timestamp, player_id, text = message[0], message[1], message[2]
            channel = message[3] if len(message) > 3 else 'all'
            lines = w.wrap(text, 'body', width - 6)
            height = 6 + name_h + body_h * len(lines)
            state['items'].append((height, {'time': timestamp, 'player': player_id, 'team': channel == 'team',
                                            'lines': lines, 'name_h': name_h, 'body_h': body_h}))
            state['ys'].append(y)
            y += height
        grew = 0 if state['visible'] == 0 else max(0, y - old_total)
        state.update(count=len(source), visible=len(visible), total=y)
        return state['items'], state['ys'], state['total'], grew

    def _draw_chat_item(self, spec, x, y, width):
        """One chat message: '[time] [TEAM] Name:' line, then the wrapped text."""
        game = self.game
        gs = game.game_state
        w = game.sidebar_widgets
        screen = game.screen
        y += 6
        time_surf = w.text(f"[{spec['time']}]", 'small', (150, 140, 128))
        screen.blit(time_surf, (x, y))
        nx = x + time_surf.get_width() + 5
        if spec['team']:
            team = w.text("[TEAM]", 'small_bold', (110, 210, 110))
            screen.blit(team, (nx, y))
            nx += team.get_width() + 5
        name = w.text(w.fit_text(f"{gs.get_player_name(spec['player'])}:", 'small_bold', x + width - nx),
                      'small_bold', gs.get_player_color(spec['player']))
        screen.blit(name, (nx, y))
        ly = y + spec['name_h']
        for line in spec['lines']:
            screen.blit(w.text(line, 'body', (226, 216, 196)), (x + 6, ly))
            ly += spec['body_h']

    def _draw_chat_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """
        Chat tab: message history, newest at the bottom.

        Format: [timestamp] [TEAM]? PlayerName: message. Team messages are filtered by
        the viewer's alliance (get_visible_chat_messages, local player). Pixel scrolling
        anchored at the bottom, like the Action Log - the old offset used the
        unfiltered message count and scrolled past the end.
        """
        from ui.sidebar_layout import content_geometry, SCROLLBAR_W
        game = self.game
        w = game.sidebar_widgets
        screen = game.screen

        full = content_geometry(sidebar_x, sidebar_y, sidebar_height, panel_width=sidebar_width)
        half = min(full.center_x - full.x, full.right - full.center_x)
        header = w.section_header("Chat", 2 * half, role='title')
        screen.blit(header, (full.center_x - half, content_start_y))
        list_top = content_start_y + header.get_height() + 8

        geo = content_geometry(sidebar_x, sidebar_y, sidebar_height, header_h=list_top - sidebar_y,
                               footer_h=8, panel_width=sidebar_width, scrollbar=True)
        viewport = pygame.Rect(geo.x, geo.top, geo.width, max(1, geo.bottom - geo.top))
        items, ys, total_h, grew = self._update_chat_layout(geo.width)
        scroll = game.sidebar_scroll['chat']
        if grew:
            scroll.on_content_grew(grew)

        if not items:
            empty = w.text("No messages yet", 'body', (200, 170, 150))
            screen.blit(empty, empty.get_rect(center=(full.center_x, list_top + 30)))
            hint = w.text("Press ENTER to chat", 'italic', (170, 150, 130))
            screen.blit(hint, hint.get_rect(center=(full.center_x, list_top + 54)))
            scroll.set_content(0, viewport.h)
            return

        self._draw_scrolling_list(items, ys, total_h, viewport, scroll,
                                  lambda item, y: self._draw_chat_item(item[1], viewport.x, y, viewport.w))
        w.draw_scrollbar(pygame.Rect(geo.right + 2, viewport.y, SCROLLBAR_W, viewport.h), scroll)

    # ========================================================================
    # HEROES (sidebar overhaul P4)
    # ========================================================================
    HERO_CARD_FILL = ((36, 26, 23, 238), (20, 14, 13, 238))
    HERO_TITLE_COLOR = (214, 160, 96)

    def _hero_entries(self, local_player):
        """(kind, hero, info) for the local player's active heroes, then those in training."""
        gs = self.game.game_state
        entries = []
        for hero, data in (gs.heroes.get(local_player, {}) or {}).items():
            entries.append(('active', hero, {'keep': data.get('keep_territory', '?')}))
        for territory, keeps in gs.hero_training_queue.items():
            if gs.territory_owners.get(territory, -1) != local_player:
                continue
            for keep_plot, entry in keeps.items():
                # Format: (hero_type, turns_remaining[, paid_cost]) - index access (old saves: 2-tuple)
                hero, remaining = entry[0], entry[1]
                total = max(1, int(gs.HERO_TYPES.get(hero, {}).get('training_time', remaining) or 1))
                entries.append(('training', hero, {'keep': territory, 'remaining': int(remaining),
                                                   'total': max(total, int(remaining))}))
        return entries

    def _hero_card_layout(self, kind, hero, info, width):
        """Measure one hero card (memoised: text wrapping/fitting is the costly part)."""
        key = (kind, hero, info.get('keep'), info.get('remaining'), info.get('total'), int(width),
               self.game.sidebar_widgets.scale)
        cache = self.__dict__.setdefault('_hero_layout_cache', OrderedDict())
        lay = cache.get(key)
        if lay is None:
            lay = self._measure_hero_card(kind, hero, info, width)
            cache[key] = lay
            if len(cache) > 64:
                cache.popitem(last=False)
        return lay

    def _measure_hero_card(self, kind, hero, info, width):
        """Measure one hero card (card-local rects for portrait / ability icons)."""
        w = self.game.sidebar_widgets
        s = w.scale
        border = max(8, int(round(9 * s)))
        pad = border + 6
        inner_w = width - 2 * pad
        name_h = w.font('heading').get_linesize()
        italic_h = w.font('italic').get_linesize()
        small_h = w.font('small').get_linesize()
        portrait = int(round(46 * s))
        text_x = pad + portrait + 8
        text_w = width - pad - text_x
        title = ' '.join(self.game.game_state.HERO_TYPES.get(hero, {}).get('description', []) or [])
        # Up to three lines (owner feedback: "High Commander of Affrancian Union" needs
        # three); anything longer ends the third line with an ellipsis, never vanishes
        title_lines = w.wrap(title, 'italic', text_w) if title else []
        if len(title_lines) > 3:
            title_lines = title_lines[:2] + [w.fit_text(' '.join(title_lines[2:]), 'italic', text_w)]
        location = w.fit_text(f"Keep: {info['keep']}", 'small', text_w)
        body_h = max(portrait, italic_h * len(title_lines) + 3 + small_h)

        y = pad
        name_y = y
        y += name_h + 2
        rule1_y = y
        y += 7 + 5
        body_y = y
        y += body_h + 5
        rule2_y = y
        y += 7 + 6
        icons = []
        if kind == 'active':
            icon = int(round(32 * s))
            gap = max(6, int(round(10 * s)))
            total = 3 * icon + 2 * gap
            start = (width - total) // 2
            for i in range(3):
                icons.append(pygame.Rect(start + i * (icon + gap), y, icon, icon))
            y += icon
            bar = None
        else:
            bar = pygame.Rect(pad, y, inner_w, max(10, int(round(12 * s))))
            y += bar.h + 4 + small_h
        height = y + pad
        return {'border': border, 'pad': pad, 'inner_w': inner_w, 'name_y': name_y, 'rule1_y': rule1_y,
                'body_y': body_y, 'rule2_y': rule2_y, 'portrait': pygame.Rect(pad, body_y, portrait, portrait),
                'text_x': text_x, 'title_lines': title_lines, 'location': location, 'italic_h': italic_h,
                'icons': icons, 'bar': bar, 'height': height, 'width': int(width)}

    def _compose_hero_card(self, kind, hero, info, lay, state):
        """Static part of a hero card (frame, name, portrait, title, location, rules,
        progress bar) on one cached surface; ability icons are drawn live on top."""
        key = (kind, hero, info.get('keep'), info.get('remaining'), info.get('total'), lay['width'],
               self.game.sidebar_widgets.scale, state)
        cache = self.__dict__.setdefault('_hero_card_cache', OrderedDict())
        surf = cache.get(key)
        if surf is not None:
            cache.move_to_end(key)
            return surf

        game = self.game
        w = game.sidebar_widgets
        width, height = lay['width'], lay['height']
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        surf.blit(w.card('bronze', (width, height), lay['border'], self.HERO_CARD_FILL, state), (0, 0))
        training = kind == 'training'

        # Name (prominent, gold) over a gold rule
        name_color = (232, 196, 120) if training else (250, 222, 150)
        name = w.text(w.fit_text(hero, 'heading', lay['inner_w']), 'heading', name_color)
        surf.blit(name, name.get_rect(midtop=(width // 2, lay['name_y'])))
        surf.blit(w.separator(lay['inner_w']), (lay['pad'], lay['rule1_y']))

        # Portrait (dimmed while in training) + title + location
        portrait_rect = lay['portrait']
        image = getattr(game, 'hero_images', {}).get(hero)
        portrait = w.icon_surface(('hero', hero), image, portrait_rect.w, frame=True)
        if training:
            portrait = portrait.copy()
            portrait.fill((150, 150, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(portrait, portrait_rect.topleft)
        ty = lay['body_y']
        for line in lay['title_lines']:
            surf.blit(w.text(line, 'italic', self.HERO_TITLE_COLOR), (lay['text_x'], ty))
            ty += lay['italic_h']
        surf.blit(w.text(lay['location'], 'small', (200, 188, 168)), (lay['text_x'], ty + 3))
        surf.blit(w.separator(lay['inner_w'], color=(150, 112, 52)), (lay['pad'], lay['rule2_y']))

        # Training: progress bar + turns remaining
        if training and lay['bar'] is not None:
            done = info['total'] - info['remaining']
            frac = done / float(info['total'])
            bar = lay['bar']
            pygame.draw.rect(surf, (28, 20, 16), bar, border_radius=3)
            if frac > 0:
                fill = bar.inflate(-4, -4)
                fill.w = max(1, int(fill.w * frac))
                pygame.draw.rect(surf, (196, 150, 60), fill, border_radius=2)
            pygame.draw.rect(surf, (120, 86, 34), bar, 1, border_radius=3)
            remaining = info['remaining']
            label = w.text(f"{remaining} {'turn' if remaining == 1 else 'turns'} remaining", 'small',
                           (226, 210, 178))
            surf.blit(label, label.get_rect(midtop=(width // 2, bar.bottom + 4)))

        # Display alpha format: noticeably faster to blend every frame
        surf = self.game.sidebar_widgets.display_alpha(surf)
        cache[key] = surf
        if len(cache) > 48:
            cache.popitem(last=False)
        return surf

    def _hero_ability_sprite(self, hero, index, size, status, hovering, clicking, disabled):
        """One ability icon composed once per look (shared draw helper, cached).

        PERFORMANCE: drawing the icons live (icon, overlays, spell border, digits) for
        three hero cards cost ~0.2 ms per frame; a composed sprite is one blit. Keyed
        by everything that changes the look, so cooldowns / hover / flash stay exact.
        """
        key = (hero, index, size, status['type'], status['cooldown'], hovering, clicking, disabled,
               self.game.sidebar_widgets.scale)
        cache = self.__dict__.setdefault('_hero_icon_cache', OrderedDict())
        sprite = cache.get(key)
        if sprite is None:
            sprite = pygame.Surface((size, size), pygame.SRCALPHA)
            self.game.draw_hero_ability_icon(pygame.Rect(0, 0, size, size), hero, index, status, hovering,
                                             clicking, self.game.sidebar_widgets.font('digits'),
                                             disabled=disabled, surface=sprite)
            sprite = self.game.sidebar_widgets.display_alpha(sprite)
            cache[key] = sprite
            if len(cache) > 96:
                cache.popitem(last=False)
        else:
            cache.move_to_end(key)
        return sprite

    def _draw_heroes_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """Heroes tab: the local player's heroes as bronze cards, then those in training.

        Active hero card: name (gold, underlined) / portrait + title + Keep location /
        the three ability icons - hoverable (tooltip after the usual delay) and castable
        exactly like the bottom-bar Hero UI (shared helpers: get_hero_ability_status,
        draw_hero_ability_icon, try_cast_hero_ability), dimmed when it's not your turn.
        Clicking the card selects the hero (bottom-bar Hero UI), as before.
        Training card: dimmed portrait, progress bar and turns remaining.
        Scrolls (top-anchored ScrollState) when the cards don't fit.

        Click rects: hero_selection_buttons {hero: rect}, sidebar_hero_ability_buttons
        {(hero, i): rect}, hero_portrait_rects {hero: rect} - all clipped to the viewport.
        """
        from ui.sidebar_layout import content_geometry, SCROLLBAR_W
        game = self.game
        gs = game.game_state
        w = game.sidebar_widgets
        screen = game.screen
        local_player = game.get_local_player()

        game.hero_selection_buttons = {}
        game.sidebar_hero_ability_buttons = {}
        game.hero_portrait_rects = {}
        current_hover = None

        full = content_geometry(sidebar_x, sidebar_y, sidebar_height, panel_width=sidebar_width)
        half = min(full.center_x - full.x, full.right - full.center_x)
        header = w.section_header("Heroes", 2 * half, role='title')
        screen.blit(header, (full.center_x - half, content_start_y))
        y = content_start_y + header.get_height() + 4

        # Hero limit (counts heroes in training too)
        count = len(gs.hero_ownership.get(local_player, ())) if isinstance(gs.hero_ownership, dict) else 0
        limit = gs.player_hero_limit[local_player] if 0 <= local_player < len(gs.player_hero_limit) else 0
        limit_text = w.text(f"Hero Limit: {count}/{limit}", 'small_bold', (222, 200, 120))
        screen.blit(limit_text, limit_text.get_rect(midtop=(full.center_x, y)))
        list_top = y + limit_text.get_height() + 8

        entries = self._hero_entries(local_player)
        scroll = game.sidebar_scroll['heroes']
        if not entries:
            empty = w.text("No heroes yet", 'body', (200, 170, 150))
            screen.blit(empty, empty.get_rect(center=(full.center_x, list_top + 30)))
            hint = w.text("Train heroes from Keeps", 'italic', (170, 150, 130))
            screen.blit(hint, hint.get_rect(center=(full.center_x, list_top + 54)))
            scroll.set_content(0, 0)
            game.update_button_hover(None, 'sidebar_hero_ability')
            return

        geo = content_geometry(sidebar_x, sidebar_y, sidebar_height, header_h=list_top - sidebar_y,
                               footer_h=8, panel_width=sidebar_width, scrollbar=True)
        viewport = pygame.Rect(geo.x, geo.top, geo.width, max(1, geo.bottom - geo.top))

        # Lay out: section header, cards, (second section header, cards)
        gap = 8
        items, y, last_kind = [], 0, None
        for kind, hero, info in entries:
            if kind != last_kind:
                label = "Active Heroes" if kind == 'active' else "Heroes in Training"
                hdr = w.section_header(label, geo.width, role='heading')
                items.append(('header', hdr, y, hdr.get_height()))
                y += hdr.get_height() + 6
                last_kind = kind
            lay = self._hero_card_layout(kind, hero, info, geo.width)
            items.append(('card', (kind, hero, info, lay), y, lay['height']))
            y += lay['height'] + gap
        scroll.set_content(max(0, y - gap), viewport.h)
        top = viewport.y - scroll.view_top()

        # Casting from the sidebar follows the bottom bar's rules (see Game._can_cast_from_sidebar)
        can_cast = game._can_cast_from_sidebar()
        previous_clip = w.begin_clip(viewport)
        try:
            for item_kind, payload, item_y, item_h in items:
                screen_y = top + item_y
                if screen_y + item_h < viewport.top:
                    continue
                if screen_y > viewport.bottom:
                    break
                if item_kind == 'header':
                    screen.blit(payload, (viewport.x, screen_y))
                    continue
                kind, hero, info, lay = payload
                rect = pygame.Rect(viewport.x, screen_y, viewport.w, item_h)
                icon_rects = [r.move(rect.topleft) for r in lay['icons']]
                over_icon = any(w.hover(r, viewport) for r in icon_rects)
                if kind == 'active' and game.selected_hero == hero:
                    state = 'selected'
                elif kind == 'active' and getattr(game, 'clicked_element', None) == ('sidebar_hero_card', hero):
                    state = 'flash'
                elif kind == 'active' and w.hover(rect, viewport) and not over_icon:
                    state = 'hover'
                else:
                    state = 'normal'
                screen.blit(self._compose_hero_card(kind, hero, info, lay, state), rect.topleft)

                hit = w.clip_hit(rect, viewport)
                portrait_hit = w.clip_hit(lay['portrait'].move(rect.topleft), viewport)
                if portrait_hit is not None:
                    game.hero_portrait_rects[hero] = portrait_hit
                if kind != 'active':
                    continue
                if hit is not None:
                    game.hero_selection_buttons[hero] = hit

                # Ability icons: live (cooldowns / hover / click flash change every turn)
                for i, icon_rect in enumerate(icon_rects):
                    status = gs.get_hero_ability_status(local_player, hero, i)
                    if status is None:
                        continue
                    hovering = w.hover(icon_rect, viewport)
                    if hovering:
                        current_hover = ('sidebar_hero_ability', (hero, i))
                    clicking = (status['castable'] and can_cast
                                and getattr(game, 'clicked_element', None) == ('sidebar_hero_ability', (hero, i)))
                    disabled = status['type'] == 'active' and not (status['castable'] and can_cast)
                    screen.blit(self._hero_ability_sprite(hero, i, icon_rect.w, status, hovering, clicking,
                                                          disabled), icon_rect.topleft)
                    icon_hit = w.clip_hit(icon_rect, viewport)
                    if icon_hit is not None:
                        game.sidebar_hero_ability_buttons[(hero, i)] = icon_hit
        finally:
            w.end_clip(previous_clip)

        w.draw_scrollbar(pygame.Rect(geo.right + 2, viewport.y, SCROLLBAR_W, viewport.h), scroll)
        # Tooltip for the hovered ability (own hover type: the bottom bar's 'hero_ability'
        # tracker releases its hover every frame and would cancel ours)
        game.update_button_hover(current_hover, 'sidebar_hero_ability')

    def _draw_technology_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """Draw Technology tab content with 3x7 button grid."""
        # Get current player (needed for castle requirement checks and other player-specific data)
        current_player = self.game.game_state.current_player

        # Initialize technology button storage for click detection
        if not hasattr(self.game, 'technology_buttons'):
            self.game.technology_buttons = {}
        self.game.technology_buttons = {}

        # Store hovered tech info for tooltip drawing at the end
        hovered_tech_info = None

        # Header (FPS OPTIMIZATION 4.1: cached)
        header_y = content_start_y
        header_text = self.get_cached_text("Technology Tree", self.game.font, WHITE, "font")
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.game.screen.blit(header_text, header_rect)

        # Separator
        pygame.draw.line(self.game.screen, RED_SEPARATOR,
                        (sidebar_x + 30, header_y + 30),
                        (sidebar_x + sidebar_width - 10, header_y + 30), 2)

        # Calculate button grid layout to fill available space
        grid_start_y = header_y + 50
        available_height = sidebar_y + sidebar_height - grid_start_y - 10  # Leave 10px margin at bottom

        # Button dimensions (reduced by 15% for smaller icons, square buttons)
        button_width = 54  # Reduced from 64 to make tech icons 15% smaller
        button_height = button_width  # Square icons

        # Spacing between buttons (increased by additional 75% from 9)
        v_spacing = 32
        h_spacing = 10

        # Calculate starting X to center the 3-column grid (move right for centering)
        total_grid_width = (button_width * 3) + (h_spacing * 2)
        grid_start_x = sidebar_x + (sidebar_width - total_grid_width) // 2 + 9  # +9 pixels to the right (5+4)

        # Draw arrows connecting technologies in columns (drawn first, so buttons appear on top)
        arrow_color = (150, 150, 150)
        for col in range(3):
            for row in range(6):  # Only rows 0-5 have arrows (not the bottom row)
                # Calculate positions for current and next button
                current_x = grid_start_x + col * (button_width + h_spacing)
                current_y = grid_start_y + row * (button_height + v_spacing)
                next_y = grid_start_y + (row + 1) * (button_height + v_spacing)

                # Arrow starts at bottom center of current button
                arrow_start_x = current_x + button_width // 2
                arrow_start_y = current_y + button_height

                # Arrow ends at top center of next button
                arrow_end_x = current_x + button_width // 2
                arrow_end_y = next_y

                # Draw the arrow line
                pygame.draw.line(self.game.screen, arrow_color,
                                (arrow_start_x, arrow_start_y),
                                (arrow_end_x, arrow_end_y), 2)

                # Draw arrowhead (small triangle pointing down, increased by additional 75% to match spacing)
                arrowhead_size = 7
                arrowhead_points = [
                    (arrow_end_x, arrow_end_y),  # Tip
                    (arrow_end_x - arrowhead_size, arrow_end_y - arrowhead_size),  # Left
                    (arrow_end_x + arrowhead_size, arrow_end_y - arrowhead_size)   # Right
                ]
                pygame.draw.polygon(self.game.screen, arrow_color, arrowhead_points)

        # Draw 3 columns x 7 rows of technology buttons
        for col in range(3):
            for row in range(7):
                # Find technology data for this position
                tech = None
                for t in self.game.game_state.technologies:
                    if t['column'] == col and t['row'] == row:
                        tech = t
                        break

                if not tech:
                    continue

                # Calculate button position
                button_x = grid_start_x + col * (button_width + h_spacing)
                button_y = grid_start_y + row * (button_height + v_spacing)
                button_rect = pygame.Rect(button_x, button_y, button_width, button_height)

                # Determine button color based on state (LOCAL player only)
                tech_id = tech['id']
                # Show LOCAL player's tech status
                if self.game.multiplayer_mode:
                    local_player = self.game.local_player_index if self.game.local_player_index is not None else 0
                else:
                    local_player = 0
                    for i in range(self.game.game_state.num_players):
                        if not self.game.game_state.player_is_ai[i]:
                            local_player = i
                            break
                is_researched = tech_id in self.game.game_state.player_tech_researched[local_player]
                is_available = tech_id in self.game.game_state.player_tech_available[local_player]

                # Check if special requirements are met (LOCAL player)
                requirements_met = True
                if tech.get('requires_castle', False):
                    if not self.game.game_state.player_has_castle(local_player):
                        requirements_met = False

                # Check if player can afford the technology (LOCAL player)
                can_afford = True
                # Same cost formula start_research() charges (Silvyr +33% AND territorial
                # tech discounts). The old local copy only applied Silvyr, so a discounted
                # tech could look unaffordable while clicking it worked.
                tech_cost = self.game.game_state.get_effective_tech_cost(tech.get('cost', 0), local_player)

                # Only one research at a time: while another tech is being researched,
                # start_research() refuses every other tech, so they must not look available
                active_research = self.game.game_state.research_in_progress.get(local_player)
                other_research_active = bool(active_research) and active_research.get('tech_id') != tech_id

                # Tutorial/mission lock (checked here so the icon tint can show it — the
                # icon covers the red base colour that used to be the only hint)
                # (is_action_allowed('research') is the check the click uses; missions that
                # only block through it would otherwise still look available)
                mission = getattr(self.game, 'tutorial_mission', None)
                tutorial_locked = bool(
                    mission and mission.active
                    and (mission.is_button_locked(f'technology_{tech_id}')
                         or not mission.is_action_allowed('research', tech_id=tech_id)))

                if is_available and tech_cost > 0:
                    current_gold = self.game.game_state.player_gold[local_player]
                    if current_gold < tech_cost:
                        can_afford = False

                if is_researched:
                    # Already researched: green
                    base_color = (60, 120, 60)
                elif is_available and requirements_met and other_research_active:
                    # Available, but waiting for the current research to finish: grey
                    base_color = (80, 80, 80)
                elif is_available and requirements_met:
                    # Available to research: blue
                    base_color = (80, 120, 180)
                elif is_available and not requirements_met:
                    # Available but requirements not met: red (same as locked)
                    base_color = (100, 50, 50)
                else:
                    # Not yet available: red tint
                    base_color = (100, 50, 50)

                # Tutorial gating: lock unavailable buttons, highlight allowed buttons
                tutorial_highlight = False
                if (hasattr(self.game, 'tutorial_mission') and self.game.tutorial_mission
                        and self.game.tutorial_mission.active):
                    btn_id = f'technology_{tech_id}'
                    # Check if button is locked by tutorial
                    if self.game.tutorial_mission.is_button_locked(btn_id):
                        base_color = (100, 50, 50)  # Red tint to match normal "unavailable" appearance
                    # Check if button should be highlighted
                    elif self.game.tutorial_mission.should_highlight_button(btn_id):
                        tutorial_highlight = True
                        base_color = (80, 180, 80)  # Green for highlighted

                # Draw button with feedback (hover, click)
                final_color, is_hovering, is_clicking = self.game.helpers.draw_feedback_button(
                    button_rect, base_color,
                    self.game.mouse_pos, self.game.clicked_element,
                    'technology_button', tech['id'],
                    text=None,  # We'll draw text manually for better control
                    border_color=(100, 100, 100),
                    border_width=2
                )

                # Tutorial highlight: draw pulsing green glow border
                if tutorial_highlight:
                    pulse = 0.5 + 0.5 * math.sin(time.time() * 4.0)
                    glow_alpha = int(150 + 100 * pulse)
                    glow_rect = button_rect.inflate(6, 6)
                    glow_surface = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
                    pygame.draw.rect(glow_surface, (100, 255, 100, glow_alpha), glow_surface.get_rect(), 3, border_radius=4)
                    self.game.screen.blit(glow_surface, glow_rect.topleft)

                # Store button rect for click detection
                self.game.technology_buttons[tech['id']] = button_rect

                # Check if this technology is being researched by LOCAL player (not current_player)
                # FIX: Use local_player consistently for all tech tree checks
                # This prevents showing opponent's research progress in your tech tree
                is_researching = False
                turns_remaining = 0
                if local_player in self.game.game_state.research_in_progress:
                    research = self.game.game_state.research_in_progress[local_player]
                    if research['tech_id'] == tech['id']:
                        is_researching = True
                        turns_remaining = research['turns_remaining']

                # Draw technology icon if available
                icon_path = tech.get('icon')
                if icon_path and os.path.exists(icon_path):
                    try:
                        # Load and cache the icon
                        if not hasattr(self, 'tech_icons'):
                            self.tech_icons = {}

                        # Scale icons to fill the button (buttons are 54x54 squares, 15% smaller than original 64)
                        # Cache key includes size so icons recalculate when dimensions change
                        cache_key = f"{icon_path}_{button_width}_{button_height}"
                        if cache_key not in self.tech_icons:
                            icon = pygame.image.load(icon_path)
                            self.tech_icons[cache_key] = pygame.transform.scale(icon, (button_width, button_height))

                        # FPS OPT: Determine tint state, cache tinted icon variants
                        # Only .copy() when hover/click effects need to modify the surface in-place
                        if is_researched:
                            tint_color = (60, 120, 60)
                            blend_amount = 128
                        elif is_researching:
                            tint_color = (200, 200, 100)
                            blend_amount = 100
                        elif tutorial_locked:
                            # Locked by the tutorial/mission: greyed out (it used to look normal)
                            tint_color = (110, 110, 110)
                            blend_amount = 120
                        elif is_available and not requirements_met:
                            tint_color = (200, 100, 100)
                            blend_amount = 120
                        elif is_available and not can_afford:
                            tint_color = (200, 100, 100)
                            blend_amount = 120
                        elif not is_available:
                            tint_color = (200, 100, 100)
                            blend_amount = 120
                        elif other_research_active:
                            # Another tech is being researched: greyed out until it finishes
                            tint_color = (110, 110, 110)
                            blend_amount = 120
                        else:
                            tint_color = None
                            blend_amount = 0

                        # FPS OPT: Cache tinted icon variant (avoids .copy() + tint every frame)
                        if not hasattr(self, '_tech_tinted_cache'):
                            self._tech_tinted_cache = {}
                        tint_cache_key = (cache_key, tint_color, blend_amount)

                        if tint_color:
                            if tint_cache_key not in self._tech_tinted_cache:
                                tinted = self.tech_icons[cache_key].copy()
                                # FPS OPT: Cache tint surface by (size, color, alpha)
                                if not hasattr(self, '_tech_tint_surfaces'):
                                    self._tech_tint_surfaces = {}
                                ts_key = (button_width, button_height, tint_color, blend_amount)
                                if ts_key not in self._tech_tint_surfaces:
                                    ts = pygame.Surface((button_width, button_height))
                                    ts.fill(tint_color)
                                    ts.set_alpha(blend_amount)
                                    self._tech_tint_surfaces[ts_key] = ts
                                tinted.blit(self._tech_tint_surfaces[ts_key], (0, 0), special_flags=pygame.BLEND_MULT)
                                self._tech_tinted_cache[tint_cache_key] = tinted
                            base_icon = self._tech_tinted_cache[tint_cache_key]
                        else:
                            base_icon = self.tech_icons[cache_key]

                        # Only .copy() for hover/click effects (rare — 1 button at a time)
                        if is_hovering or is_clicking:
                            icon = base_icon.copy()
                            if is_hovering:
                                if not hasattr(self, '_tech_brighten_surface') or self._tech_brighten_size != (button_width, button_height):
                                    self._tech_brighten_surface = pygame.Surface((button_width, button_height))
                                    self._tech_brighten_surface.fill((51, 51, 51))
                                    self._tech_brighten_size = (button_width, button_height)
                                icon.blit(self._tech_brighten_surface, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            if is_clicking:
                                if not hasattr(self, '_tech_flash_surface') or self._tech_flash_size != (button_width, button_height):
                                    self._tech_flash_surface = pygame.Surface((button_width, button_height))
                                    self._tech_flash_surface.fill((102, 102, 102))
                                    self._tech_flash_size = (button_width, button_height)
                                icon.blit(self._tech_flash_surface, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            self.game.screen.blit(icon, (button_x, button_y))
                        else:
                            # FPS OPT: Blit directly from cache — no .copy() needed
                            self.game.screen.blit(base_icon, (button_x, button_y))

                        # PERFORMANCE OPTIMIZATION: Cache tech border scaling (21 buttons = 21× smoothscale without cache)
                        # This was causing ~30% FPS drop when technology panel open
                        # Border is 2px larger than icon (1px per side) to fully contain icon edges
                        if self.game.icon_border:
                            cached_border = self.game._get_cached_tech_border(self.game.icon_border, button_width + 2, button_height + 2)
                            self.game.screen.blit(cached_border, (button_x - 1, button_y - 1))
                    except Exception as e:
                        logger.warning(f"Failed to load tech icon {icon_path}: {e}")

                # Draw turns remaining if researching
                if is_researching:
                    turns_text = f"{turns_remaining} turn{'s' if turns_remaining != 1 else ''}"
                    turns_surface = self.get_cached_text(turns_text, self.game.small_font, (255, 255, 100), "small")
                    turns_rect = turns_surface.get_rect(centerx=button_x + button_width // 2,
                                                       y=button_y + button_height - 18)
                    # Draw semi-transparent background for better visibility
                    bg_rect = pygame.Rect(turns_rect.x - 2, turns_rect.y - 1,
                                         turns_rect.width + 4, turns_rect.height + 2)
                    bg_surface = pygame.Surface((bg_rect.width, bg_rect.height))
                    bg_surface.set_alpha(180)
                    bg_surface.fill((0, 0, 0))
                    self.game.screen.blit(bg_surface, bg_rect)
                    self.game.screen.blit(turns_surface, turns_rect)
                elif not icon_path:
                    # Draw technology name if no icon (for placeholder techs)
                    name_lines = self._wrap_text(tech['name'], button_width - 8, self.game.small_font)
                    text_y = button_y + (button_height - len(name_lines) * 14) // 2

                    for line in name_lines:
                        # Choose text color based on state
                        if is_researched:
                            text_color = (200, 255, 200)
                        elif is_available:
                            text_color = WHITE
                        else:
                            text_color = (180, 120, 120)

                        text_surface = self.get_cached_text(line, self.game.small_font, text_color, "small")
                        text_rect = text_surface.get_rect(centerx=button_x + button_width // 2, y=text_y)
                        self.game.screen.blit(text_surface, text_rect)
                        text_y += 14

                # Store tooltip info for later drawing (so it appears on top)
                if is_hovering:
                    # Bronze color for upgrade name and labels
                    bronze_color = (180, 120, 60)
                    gold_color = (200, 160, 0)  # Darker gold for better readability
                    black_color = (0, 0, 0)

                    # Line 1: Research Name (bold, bronze)
                    tooltip_lines = [
                        [("normal_bold", tech['name'], bronze_color)],
                    ]

                    # Add cost and turns info if available
                    base_cost = tech.get('cost', 0)
                    turns = tech.get('turns', 0)

                    # Get effective cost (includes Silvyr bonus and territorial bonuses) - LOCAL player
                    cost = self.game.game_state.get_effective_tech_cost(base_cost, local_player)

                    # Apply Ruthless Ingenuity (Erec Silvyr): -1 turn (min 1)
                    if self.game.game_state.player_has_silvyr(local_player):
                        turns = max(1, turns - 1)

                    if cost > 0:
                        # Line 2: Gold Cost (label in gold, value in black)
                        tooltip_lines.append([
                            ("small", "Gold Cost:", gold_color),
                            ("small", f" {cost}", black_color)
                        ])

                    if turns > 0:
                        # Line 3: Research Time (label in gold, value in black)
                        tooltip_lines.append([
                            ("small", "Research Time:", gold_color),
                            ("small", f" {turns} turn{'s' if turns != 1 else ''}", black_color)
                        ])

                    # Line 4: Effect (label in gold, description in black)
                    # Split description by newlines
                    description_lines = tech['description'].split('\n')
                    for i, desc_line in enumerate(description_lines):
                        if i == 0:
                            # First line with "Effect:" label
                            tooltip_lines.append([
                                ("small", "Effect:", gold_color),
                                ("small", f" {desc_line.strip()}", black_color)
                            ])
                        else:
                            # Continuation lines (indented)
                            tooltip_lines.append([("small", f"  {desc_line.strip()}", black_color)])

                    # Add special requirements
                    if tech.get('requires_castle', False):
                        has_castle = self.game.game_state.player_has_castle(current_player)
                        if has_castle:
                            tooltip_lines.append([("small", "Requires: Castle", (100, 255, 100))])
                        else:
                            tooltip_lines.append([("small", "Requires: Castle", (255, 100, 100))])

                    # Status lines
                    if is_researched:
                        tooltip_lines.append([("small", "Status: Researched", (100, 255, 100))])
                    elif is_researching:
                        tooltip_lines.append([("small", f"Status: Researching ({turns_remaining} turn{'s' if turns_remaining != 1 else ''} left)", (200, 160, 0))])  # Darker gold for in-progress
                        tooltip_lines.append([("small", "Right-click to cancel (full refund)", (200, 200, 255))])
                    elif is_available and other_research_active:
                        # Clicking now would be refused — say why instead of "Available"
                        tooltip_lines.append([("small", "Status: Waiting", (200, 200, 200))])
                        tooltip_lines.append([("small", "Another technology is being researched", (200, 150, 150))])
                    elif is_available:
                        tooltip_lines.append([("small", "Status: Available", (100, 200, 255))])
                        tooltip_lines.append([("small", "Left-click to start research", (200, 200, 255))])
                    else:
                        tooltip_lines.append([("small", "Status: Locked", (255, 100, 100))])
                        tooltip_lines.append([("small", "Complete previous research to unlock", (200, 150, 150))])

                    hovered_tech_info = tooltip_lines

        # Render blue particles if Silvyr is active (LOCAL player only)
        if self.game.multiplayer_mode:
            local_player = self.game.local_player_index if self.game.local_player_index is not None else 0
        else:
            local_player = 0
            for i in range(self.game.game_state.num_players):
                if not self.game.game_state.player_is_ai[i]:
                    local_player = i
                    break
        # Skipped while the sidebar slides: particles store absolute screen positions,
        # so ones spawned mid-slide would be left behind when the panel stops.
        sliding = self.game.is_sidebar_animating()
        if self.game.game_state.player_has_silvyr(local_player) and not sliding:
            self._render_tech_tree_particles(sidebar_x, sidebar_y, sidebar_width, sidebar_height)

        # Draw tooltip at the very end so it appears on top of everything
        # (not mid-slide: the buttons are moving under a still cursor)
        if hovered_tech_info and not sliding:
            # Use main.py's draw_tooltip_box for mixed-style rendering support
            self.game.draw_tooltip_box(self.game.mouse_pos, hovered_tech_info)

    def _update_tech_tree_particles(self, delta_time, panel_x, panel_y, panel_width, panel_height):
        """
        Update particle system for Technology Tree (Ruthless Ingenuity effect).

        Args:
            delta_time: Time elapsed since last update (seconds)
            panel_x, panel_y: Top-left corner of tech tree panel
            panel_width, panel_height: Dimensions of tech tree panel
        """
        # Particle configuration
        PARTICLES_PER_SECOND = 80  # Increased for better visibility
        MIN_PARTICLE_LIFETIME = 1.5
        MAX_PARTICLE_LIFETIME = 3.0
        PARTICLE_SIZE = 3  # Slightly larger for better visibility

        # Blue shades for Ruthless Ingenuity
        BLUE_SHADES = [
            (30, 60, 150),    # Dark blue
            (50, 100, 200),   # Medium blue
            (70, 120, 255),   # Bright blue
            (100, 150, 255),  # Light blue
            (130, 180, 255)   # Very light blue
        ]

        # Spawn new particles
        self.particle_spawn_accumulator += delta_time
        particles_to_spawn = int(self.particle_spawn_accumulator * PARTICLES_PER_SECOND)
        self.particle_spawn_accumulator -= particles_to_spawn / PARTICLES_PER_SECOND

        for _ in range(particles_to_spawn):
            # Random position within panel (focus on research icon area, skip header)
            # Start particles below the header (50 pixels down from panel_y)
            icon_area_start_y = 50
            x = panel_x + random.uniform(0, panel_width)
            y = panel_y + icon_area_start_y + random.uniform(0, panel_height - icon_area_start_y)

            particle = {
                'x': x,
                'y': y,
                'color': random.choice(BLUE_SHADES),
                'size': PARTICLE_SIZE,
                'lifetime': random.uniform(MIN_PARTICLE_LIFETIME, MAX_PARTICLE_LIFETIME),
                'age': 0.0,
                'max_opacity': random.uniform(0.4, 0.8),
                'vy': random.uniform(-20, -40)  # Upward velocity
            }
            self.tech_particles.append(particle)

        # Update existing particles
        particles_to_remove = []
        for particle in self.tech_particles:
            particle['age'] += delta_time
            particle['y'] += particle['vy'] * delta_time  # Move upward

            # Remove particles that exceeded their lifetime or left the panel
            if particle['age'] >= particle['lifetime'] or particle['y'] < panel_y:
                particles_to_remove.append(particle)

        # Remove dead particles
        for particle in particles_to_remove:
            self.tech_particles.remove(particle)

    def _render_tech_tree_particles(self, panel_x, panel_y, panel_width, panel_height):
        """
        Render particles for Technology Tree (Ruthless Ingenuity effect).

        Args:
            panel_x, panel_y: Top-left corner of tech tree panel
            panel_width, panel_height: Dimensions of tech tree panel
        """
        # Update particles (use frame time from game clock)
        try:
            delta_time = self.game.clock.get_time() / 1000.0  # Convert ms to seconds
            self._update_tech_tree_particles(delta_time, panel_x, panel_y, panel_width, panel_height)
        except AttributeError:
            # Fallback if clock not available
            delta_time = 1/60.0
            self._update_tech_tree_particles(delta_time, panel_x, panel_y, panel_width, panel_height)

        # If no particles, nothing to render
        if not self.tech_particles:
            return

        # PERFORMANCE: Reuse overlay surface for particle rendering
        temp_surface = self._get_overlay_surface()

        # Draw all particles
        for particle in self.tech_particles:
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
        self.game.screen.blit(temp_surface, (0, 0))

    def _wrap_text(self, text, max_width, font):
        """Helper to wrap text to fit within a width."""
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]

    def _draw_quests_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """Draw quest log content for the Quests tab (used by tutorial missions)."""
        # Title
        title_y = content_start_y
        title_text = self.get_cached_text("Quests", self.game.font, WHITE, "font")
        title_rect = title_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=title_y)
        self.game.screen.blit(title_text, title_rect)

        # Separator
        pygame.draw.line(self.game.screen, (100, 100, 100),
                        (sidebar_x + 30, title_y + 30),
                        (sidebar_x + sidebar_width - 10, title_y + 30), 2)

        # Get quest log from tutorial mission
        tutorial = self.game.game_state.tutorial_mission
        if not tutorial or not tutorial.active:
            # No active tutorial — show placeholder
            msg_text = self.get_cached_text("No active quests", self.game.small_font, (150, 150, 150), "small_font")
            msg_rect = msg_text.get_rect(center=(sidebar_x + sidebar_width // 2, title_y + 60))
            self.game.screen.blit(msg_text, msg_rect)
            return

        quest_log = tutorial.get_quest_log()
        y = title_y + 45
        padding_x = sidebar_x + 35

        # Max text width for word wrapping (sidebar width minus padding on both sides)
        max_text_width = sidebar_width - 40
        line_height = 20

        for quest in quest_log:
            if quest['completed']:
                prefix = "+"
                color = (100, 255, 100)
            else:
                prefix = ">"
                color = (255, 255, 255)

            # Word-wrap quest text to fit sidebar width
            full_text = f"{prefix} {quest['text']}"
            words = full_text.split(' ')
            lines = []
            current_line = ''
            for word in words:
                test_line = f"{current_line} {word}".strip() if current_line else word
                if self.game.small_font.size(test_line)[0] <= max_text_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)

            for line in lines:
                text_surface = self.get_cached_text(line, self.game.small_font, color, "small")
                self.game.screen.blit(text_surface, (padding_x, y))
                y += line_height
            y += 4  # Extra spacing between quests

    def _draw_placeholder_tab_content(self, sidebar_x, sidebar_width, content_start_y, tab_name):
        """Draw placeholder content for tabs that aren't implemented yet."""
        # Title
        title_y = content_start_y
        title_text = self.get_cached_text(tab_name, self.game.font, WHITE, "font")
        title_rect = title_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=title_y)
        self.game.screen.blit(title_text, title_rect)
        
        # Separator
        pygame.draw.line(self.game.screen, (100, 100, 100), 
                        (sidebar_x + 30, title_y + 30),
                        (sidebar_x + sidebar_width - 10, title_y + 30), 2)
        
        # Placeholder message
        # FPS OPTIMIZATION 4.1: Use cached text for static placeholder text
        msg_y = title_y + 60
        msg_text = self.get_cached_text("Coming Soon", self.game.small_font, (150, 150, 150), "small_font")
        msg_rect = msg_text.get_rect(center=(sidebar_x + sidebar_width // 2, msg_y))
        self.game.screen.blit(msg_text, msg_rect)

        # Description
        desc_y = msg_y + 30
        desc_text = self.get_cached_text("This feature will be", self.game.small_font, (120, 120, 120), "small_font")
        desc_rect = desc_text.get_rect(center=(sidebar_x + sidebar_width // 2, desc_y))
        self.game.screen.blit(desc_text, desc_rect)

        desc2_y = desc_y + 20
        desc2_text = self.get_cached_text("implemented later", self.game.small_font, (120, 120, 120), "small_font")
        desc2_rect = desc2_text.get_rect(center=(sidebar_x + sidebar_width // 2, desc2_y))
        self.game.screen.blit(desc2_text, desc2_rect)
    
    def _draw_sidebar_tab_buttons(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height):
        """
        Draw the bookmark tabs on the LEFT side of the sidebar.

        Tabs stick out from the panel's left edge (or sit at the screen edge when the
        sidebar is collapsed): Technology, Heroes, Action Queue, Action Log, Quests, Chat.

        Each tab is a pre-rendered sprite from SidebarWidgets.tab_sprite() in the style
        UIConstants.SIDEBAR_TAB_STYLE ('ribbon' by default): label fitted with padding
        (it used to touch the borders - "Action Queue" was 89 px in a 93 px tab), hover
        highlight, click flash ('sidebar_tab', id) and an always-visible active state
        (lit, inner gold glow, merging into the panel). Tutorial-highlighted tabs get a
        green trim plus a pulsing ring; locked tabs are dimmed.

        Geometry comes from sidebar_layout.compute_tab_rects() - the same rects the
        panel border uses to leave a gap beside the active tab.
        """
        widgets = self.game.sidebar_widgets
        tab_width = UIConstants.TAB_WIDTH
        tabs = self.game.game_state.sidebar_tabs
        rects = [pygame.Rect(r) for r in compute_tab_rects(
            sidebar_x - tab_width, sidebar_y, sidebar_height, len(tabs), tab_width,
            UIConstants.TAB_PADDING_TOP, UIConstants.TAB_PADDING_BOTTOM)]

        # Store tab button rects for click detection
        self.game.sidebar_tab_buttons = {}

        # Tab display names
        tab_names = {
            'technology': 'Technology',
            'heroes': 'Heroes',
            'action_queue': 'Action Queue',
            'action_log': 'Action Log',
            'quests': 'Quests',
            'chat': 'Chat'
        }

        mission = self.game.tutorial_mission if getattr(self.game, 'tutorial_mission', None) else None
        mission_active = bool(mission and mission.active)
        panel_image = getattr(self.game, 'right_panel_image', None)
        clicked = getattr(self.game, 'clicked_element', None)
        style = UIConstants.SIDEBAR_TAB_STYLE
        # One label size for the whole column (consistent; see common_label_px)
        label_px = None
        if rects:
            max_len, max_thick = widgets.tab_label_space(tab_width, rects[0].h)
            label_px = widgets.common_label_px([tab_names[t] for t in tabs], max_len, max_thick)

        for tab_id, tab_rect in zip(tabs, rects):
            is_active = (tab_id == self.game.game_state.active_sidebar_tab)
            tab_locked = False
            highlight = False
            if mission_active:
                if mission.should_highlight_button(f'sidebar_{tab_id}'):
                    highlight = True
                elif not is_active and not mission.is_action_allowed('sidebar_tab', tab_name=tab_id):
                    # Locked tab (the click is refused): dimmed, not just "inactive"
                    tab_locked = True

            hovering = (not tab_locked) and widgets.hover(tab_rect)
            if tab_locked:
                state = 'locked'
            elif clicked == ('sidebar_tab', tab_id):
                state = 'flash'
            elif highlight and not is_active:
                state = 'highlight'
            elif is_active:
                state = 'active_hover' if hovering else 'active'
            else:
                state = 'hover' if hovering else 'inactive'

            # Ribbon fill: the tapestry at this tab's own height, so the pattern runs on
            # from the panel (cut once per size/state - cached)
            # The active ribbon sticks out further than the others (drawn wider to the
            # left) - the click rect stays the same size
            extra = UIConstants.TAB_ACTIVE_EXTEND if (style == 'ribbon' and is_active) else 0
            draw_rect = pygame.Rect(tab_rect.x - extra, tab_rect.y, tab_rect.w + extra, tab_rect.h)
            texture_src = None
            if panel_image is not None:
                rel_y = max(0, tab_rect.y - sidebar_y)
                texture_src = (panel_image, (30, rel_y, draw_rect.w, tab_rect.h))
            sprite = widgets.tab_sprite(style, tab_names[tab_id], draw_rect.size, state, texture_src, label_px)
            self.game.screen.blit(sprite, draw_rect.topleft)
            # Keep the shared rotated-label cache populated (other code inspects it)
            self.game._rotated_tab_text_cache.setdefault(tab_id, sprite)

            # Tutorial highlight: pulsing ring from ONE cached surface (alpha set per
            # frame) instead of a new Surface every frame
            if highlight:
                pulse = 0.5 + 0.5 * math.sin(time.time() * 4.0)
                ring = widgets.pulse_ring(tab_rect.inflate(4, 4).size)
                ring.set_alpha(int(150 + 100 * pulse))
                self.game.screen.blit(ring, tab_rect.inflate(4, 4).topleft)

            # Store for click detection
            self.game.sidebar_tab_buttons[tab_id] = tab_rect

        # Return Y position where content should start (just below sidebar top, since tabs are on left)
        return sidebar_y + 15
