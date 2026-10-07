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
    
    def _draw_action_queue_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """Draw Action Queue tab content (movement orders)."""
        # Header (Phase 2: Use SemiBold for section header)
        # FPS OPTIMIZATION 4.1: Use cached text for static header
        header_y = content_start_y
        header_text = self.get_cached_text("Action Queue", self.game.font_bold, WHITE, "font_bold")
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.game.screen.blit(header_text, header_rect)
        
        # Draw separator line
        pygame.draw.line(self.game.screen, RED_SEPARATOR, 
                        (sidebar_x + 30, header_y + 30),
                        (sidebar_x + sidebar_width - 10, header_y + 30), 2)
        
        # Determine LOCAL player
        if self.game.multiplayer_mode:
            local_player = self.game.local_player_index if self.game.local_player_index is not None else 0
        else:
            local_player = 0
            for i in range(self.game.game_state.num_players):
                if not self.game.game_state.player_is_ai[i]:
                    local_player = i
                    break

        # Filter orders to show only LOCAL player's orders
        local_orders = [order for order in self.game.game_state.movement_orders if order.player == local_player]

        # Reset every frame, BEFORE the empty-list early return: otherwise the X of the
        # last cancelled order stayed clickable and hit whatever order came next.
        self.game.order_cancel_buttons = []
        # Player whose orders this sidebar shows — the CANCEL ALL button cancels only these
        self.game.order_sidebar_player = local_player

        # Check if there are any orders
        if len(local_orders) == 0:
            # Show empty message
            # FPS OPTIMIZATION 4.1: Use cached text for static message
            empty_text = self.get_cached_text("No actions queued", self.game.small_font, RED_TEXT_DIM, "small_font")
            empty_rect = empty_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 80))
            self.game.screen.blit(empty_text, empty_rect)
            return

        # Tutorial/mission lock on cancelling: the click is refused, so grey the X buttons
        mission = getattr(self.game, 'tutorial_mission', None)
        cancel_locked = bool(mission and mission.active and not mission.is_action_allowed('cancel_order'))

        # Draw each order (LOCAL player only)
        order_y = header_y + UIConstants.HEADER_OFFSET
        order_height = 60

        for i, order in enumerate(local_orders):
            if order_y + order_height > sidebar_y + sidebar_height - 10:
                # Too many orders to fit, show scroll indicator
                # FPS OPTIMIZATION 4.1: Use cached text for static indicator
                scroll_text = self.get_cached_text("...", self.game.small_font, WHITE, "small_font")
                self.game.screen.blit(scroll_text, (sidebar_x + sidebar_width // 2 - 10, order_y))
                break

            # Determine if this is an attack (red) or reinforcement (blue)
            target_owner = self.game.game_state.territory_owners.get(order.to_territory)
            is_attack = target_owner is not None and target_owner != order.player

            # Color based on movement type
            movement_color = (255, 100, 100) if is_attack else (100, 150, 255)  # Red for attack, blue for reinforcement
            border_color = (200, 50, 50) if is_attack else (50, 100, 200)

            # Order background
            order_rect = pygame.Rect(sidebar_x + 30, order_y, sidebar_width - 60, order_height - 5)
            pygame.draw.rect(self.game.screen, (60, 60, 60), order_rect, border_radius=5)
            pygame.draw.rect(self.game.screen, border_color, order_rect, 2, border_radius=5)

            # Movement text: "Origin -> Target" format in single line
            movement_text = f"{order.from_territory} -> {order.to_territory}"

            # Truncate if too long
            max_width = sidebar_width - 100
            movement_surface = self.get_cached_text(movement_text, self.game.small_font, movement_color, "small")
            if movement_surface.get_width() > max_width:
                # Try shortening territory names
                from_short = order.from_territory[:10] + "..." if len(order.from_territory) > 10 else order.from_territory
                to_short = order.to_territory[:10] + "..." if len(order.to_territory) > 10 else order.to_territory
                movement_text = f"{from_short} -> {to_short}"
                movement_surface = self.get_cached_text(movement_text, self.game.small_font, movement_color, "small")

            self.game.screen.blit(movement_surface, (sidebar_x + 40, order_y + 8))

            # Army count below
            count_text = self.get_cached_text(f"Units: {order.army_count}", self.game.small_font, (200, 200, 200), "small")
            self.game.screen.blit(count_text, (sidebar_x + 40, order_y + 28))

            # Cancel button (X) - ASCII character for better font compatibility
            # FPS OPTIMIZATION 4.1: Use cached text for static button label
            cancel_button_rect = pygame.Rect(sidebar_x + sidebar_width - 45, order_y + 18, 30, 25)
            # Grey when the tutorial/mission blocks cancelling (it used to look clickable)
            cancel_color = (110, 110, 110) if cancel_locked else (200, 50, 50)
            pygame.draw.rect(self.game.screen, cancel_color, cancel_button_rect, border_radius=3)
            cancel_text = self.get_cached_text("X", self.game.font, WHITE, "font")
            cancel_text_rect = cancel_text.get_rect(center=cancel_button_rect.center)
            self.game.screen.blit(cancel_text, cancel_text_rect)

            # Store (rect, order object, per-player index) for click detection.
            # Format: (rect, order, player_order_index). The order object identifies the
            # order to cancel locally; i (its index among this player's orders) is what the
            # ORDER_REMOVE network message carries. The old format stored only i and used
            # it on the full movement_orders list, cancelling the wrong order.
            self.game.order_cancel_buttons.append((cancel_button_rect, order, i))

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
        # Header (Phase 2: Use SemiBold for section header)
        # FPS OPTIMIZATION 4.1: Use cached text for static header
        header_y = content_start_y
        header_text = self.get_cached_text("Action Log", self.game.font_bold, WHITE, "font_bold")
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.game.screen.blit(header_text, header_rect)
        
        # Draw separator line
        pygame.draw.line(self.game.screen, (100, 100, 100),
                        (sidebar_x + 30, header_y + 30),
                        (sidebar_x + sidebar_width - 10, header_y + 30), 2)

        # Determine LOCAL player (for filtering messages)
        # Purpose: Show only LOCAL player's messages, not opponents' actions
        if self.game.multiplayer_mode:
            local_player = self.game.local_player_index if self.game.local_player_index is not None else 0
        else:
            local_player = 0
            for i in range(self.game.game_state.num_players):
                if not self.game.game_state.player_is_ai[i]:
                    local_player = i
                    break

        # Helper function to check if message belongs to local player
        # Purpose: Parse player indices from messages (supports both "Player X" and custom names)
        def is_local_player_message(msg, local_player_num):
            """
            Check if a message belongs to the local player.
            Returns True if:
            - Message contains "Player X" where X = local_player_num + 1
            - Message contains the local player's custom name (e.g., "Editoreus")
            - Message doesn't contain any player identification (global messages)
            Returns False if:
            - Message only mentions other players
            """
            import re

            # Get local player's custom name (if any)
            local_player_name = self.game.game_state.get_player_name(local_player_num)

            # Method 1: Check for "Player X" pattern (used in most messages)
            player_matches = re.findall(r'Player (\d+)', msg)

            # Method 2: Check if message contains local player's custom name
            # (for messages that might use custom names instead of "Player X")
            has_local_name = local_player_name in msg if local_player_name else False

            # If no player identification found, it's a global message
            if not player_matches and not has_local_name:
                # Check if message contains ANY player name (not just local)
                # If it contains other player names but not ours, filter it out
                for i in range(self.game.game_state.num_players):
                    if i != local_player_num:
                        other_name = self.game.game_state.get_player_name(i)
                        if other_name and other_name in msg:
                            return False  # Message about another player
                # No player identification - global message
                return True

            # If we found local player's name, include message
            if has_local_name:
                return True

            # Check if "Player X" matches local player (convert 0-indexed to 1-indexed)
            local_player_id = str(local_player_num + 1)
            for player_id in player_matches:
                if player_id == local_player_id:
                    return True  # Message involves local player

            # Message only involves other players
            return False

        # Check if there are any messages
        if len(self.game.game_state.messages) == 0:
            # Show empty message
            # FPS OPTIMIZATION 4.1: Use cached text for static message
            empty_text = self.get_cached_text("No actions yet", self.game.small_font, (150, 150, 150), "small_font")
            empty_rect = empty_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 80))
            self.game.screen.blit(empty_text, empty_rect)
            return

        # Helper function to replace "Player X" with actual player names
        # Purpose: Convert generic "Player 1", "Player 2" to custom names like "Editoreus"
        def replace_player_names_in_message(msg):
            """
            Replace all "Player X" patterns in message with actual player names.
            Example: "Player 1 earned 100 gold" -> "Editoreus earned 100 gold"
            """
            import re

            # Find all "Player X" patterns
            def replace_match(match):
                player_num = int(match.group(1))  # Extract number (1-indexed)
                player_index = player_num - 1  # Convert to 0-indexed

                # Get actual player name
                if 0 <= player_index < self.game.game_state.num_players:
                    return self.game.game_state.get_player_name(player_index)
                else:
                    return match.group(0)  # Keep original if invalid

            # Replace all "Player X" with actual names
            return re.sub(r'Player (\d+)', replace_match, msg)

        # Get messages to display (oldest to newest), filtered by local player
        # Purpose: Only show messages that involve the local player or are global
        # Also replace "Player X" with actual player names
        all_messages = [replace_player_names_in_message(msg)
                       for msg in self.game.game_state.messages
                       if is_local_player_message(msg, local_player)]
        total_messages = len(all_messages)
        
        # Calculate approximate visible messages
        # Use generous estimate for selection - rendering loop will stop when full
        available_height = sidebar_y + sidebar_height - (header_y + UIConstants.HEADER_OFFSET) - UIConstants.BOTTOM_RESERVE
        approx_messages_visible = max(5, available_height // UIConstants.PIXELS_PER_MESSAGE_SELECTION)
        
        # Calculate which messages to show based on scroll offset
        # When scroll_offset = 0: Show newest messages (end of list)
        # When scroll_offset > 0: Scroll back in history
        
        # End index is total minus scroll offset
        end_index = total_messages - self.game.action_log_scroll_offset
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

            # Determine message color (dark gold for turn start messages)
            dark_gold = (200, 160, 0)  # Dark gold color
            if "Turn ---" in message or "'s Turn" in message:
                # Turn start message - use dark gold color
                msg_color = dark_gold
            else:
                # Regular message - use normal color
                msg_color = (200, 200, 200)

            # Word wrap for long messages (fit in sidebar)
            max_chars = UIConstants.MESSAGE_MAX_CHARS
            if len(message) > max_chars:
                words = message.split()
                line = ""
                for word in words:
                    test_line = line + " " + word if line else word
                    if len(test_line) > max_chars:
                        # FPS OPT: Cache action log text renders
                        msg_text = self.get_cached_text(line, self.game.small_font, msg_color, "small")
                        self.game.screen.blit(msg_text, (sidebar_x + 30, msg_y))
                        msg_y += 18
                        line = word

                        # Check space again
                        if msg_y + 40 > sidebar_y + sidebar_height - UIConstants.BOTTOM_RESERVE:
                            break
                    else:
                        line = test_line

                # Draw last line
                if line and msg_y + 20 < sidebar_y + sidebar_height - 40:
                    msg_text = self.get_cached_text(line, self.game.small_font, msg_color, "small")
                    self.game.screen.blit(msg_text, (sidebar_x + 30, msg_y))
                    msg_y += 18
            else:
                # Short message - draw directly
                msg_text = self.get_cached_text(message, self.game.small_font, msg_color, "small")
                self.game.screen.blit(msg_text, (sidebar_x + 30, msg_y))
                msg_y += 18

            # Add small gap between messages
            msg_y += 5
        
        # Calculate actual end index based on what we rendered
        actual_end_index = start_msg_index + messages_rendered
        
        # Draw scroll position indicator on right side
        if total_messages > messages_rendered:
            # Calculate scroll position
            max_scroll = total_messages - messages_rendered
            scroll_percentage = 1.0 - (self.game.action_log_scroll_offset / max_scroll) if max_scroll > 0 else 1.0
            
            # Scrollbar dimensions
            scrollbar_x = sidebar_x + sidebar_width - UIConstants.SCROLLBAR_OFFSET
            scrollbar_top = header_y + UIConstants.HEADER_OFFSET
            scrollbar_height = sidebar_y + sidebar_height - scrollbar_top - 10
            
            # Draw scrollbar track
            pygame.draw.rect(self.game.screen, (60, 60, 60), 
                           (scrollbar_x, scrollbar_top, UIConstants.SCROLLBAR_WIDTH, scrollbar_height))
            
            # Draw scrollbar thumb
            thumb_height = max(UIConstants.SCROLLBAR_THUMB_MIN, int(scrollbar_height * (messages_rendered / total_messages)))
            thumb_y = scrollbar_top + int((scrollbar_height - thumb_height) * scroll_percentage)
            pygame.draw.rect(self.game.screen, (150, 150, 150), 
                           (scrollbar_x, thumb_y, UIConstants.SCROLLBAR_WIDTH, thumb_height))
            
            # Draw position text
            position_text = f"{actual_end_index}/{total_messages}"
            pos_text_surface = self.get_cached_text(position_text, self.game.small_font, (120, 120, 120), "small")
            pos_rect = pos_text_surface.get_rect(right=sidebar_x + sidebar_width - 15,
                                                  bottom=sidebar_y + sidebar_height - 5)
            self.game.screen.blit(pos_text_surface, pos_rect)

    def _draw_chat_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """
        Draw Chat tab content with message history and scrolling.

        Format: [timestamp] [TEAM]? PlayerName: message
        Supports scrolling with mouse wheel to view older messages.
        Filters team messages based on viewer's team membership.
        """
        # Header (Phase 2: Use SemiBold for section header)
        # FPS OPTIMIZATION 4.1: Use cached text for static header
        header_y = content_start_y
        header_text = self.get_cached_text("Chat", self.game.font_bold, WHITE, "font_bold")
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.game.screen.blit(header_text, header_rect)

        # Draw separator line
        pygame.draw.line(self.game.screen, (100, 100, 100),
                        (sidebar_x + 30, header_y + 30),
                        (sidebar_x + sidebar_width - 10, header_y + 30), 2)

        # Get viewer's player index for message filtering
        if self.game.multiplayer_mode:
            viewer_player = getattr(self.game, 'local_player_index', 0)
        else:
            viewer_player = self.game.game_state.current_player

        # Get visible messages (filters team chat by alliance)
        all_messages = self.game.game_state.get_visible_chat_messages(viewer_player)
        total_messages = len(all_messages)

        # Check if there are any visible messages
        if total_messages == 0:
            # Show empty message
            # FPS OPTIMIZATION 4.1: Use cached text for static messages
            empty_text = self.get_cached_text("No messages yet", self.game.small_font, (150, 150, 150), "small_font")
            empty_rect = empty_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 80))
            self.game.screen.blit(empty_text, empty_rect)

            # Instructions
            hint_text = self.get_cached_text("Press ENTER to chat", self.game.small_font, (120, 120, 120), "small_font")
            hint_rect = hint_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 110))
            self.game.screen.blit(hint_text, hint_rect)
            return
        
        # Calculate approximate visible messages
        # Use generous estimate for selection - rendering loop will stop when full
        available_height = sidebar_y + sidebar_height - (header_y + UIConstants.HEADER_OFFSET) - UIConstants.BOTTOM_RESERVE
        approx_messages_visible = max(5, available_height // UIConstants.PIXELS_PER_MESSAGE_SELECTION)
        
        # Calculate which messages to show based on scroll offset
        # When scroll_offset = 0: Show newest messages (end of list)
        # When scroll_offset > 0: Scroll back in history
        
        # End index is total minus scroll offset
        end_index = total_messages - self.game.chat_scroll_offset
        # Start index ensures we don't show more than fits
        start_index = max(0, end_index - approx_messages_visible)
        
        messages_to_show = all_messages[start_index:end_index]
        start_msg_index = start_index
        
        # Draw messages (oldest to newest, top to bottom)
        msg_y = header_y + UIConstants.HEADER_OFFSET
        messages_rendered = 0
        
        for idx, msg_tuple in enumerate(messages_to_show):
            # Check if we're out of space
            if msg_y + 40 > sidebar_y + sidebar_height - UIConstants.BOTTOM_RESERVE:
                break

            messages_rendered += 1

            # Handle both 3-tuple (old format) and 4-tuple (new format with channel)
            if len(msg_tuple) == 4:
                timestamp, player_id, message, channel = msg_tuple
            else:
                timestamp, player_id, message = msg_tuple
                channel = 'all'

            # Format: [timestamp] [TEAM]? PlayerName: message
            player_color = self.game.game_state.get_player_color(player_id)
            player_name = self.game.game_state.get_player_name(player_id)

            # FPS OPT: Cache all chat text renders
            time_text = self.get_cached_text(f"[{timestamp}]", self.game.small_font, (150, 150, 150), "small")
            self.game.screen.blit(time_text, (sidebar_x + 30, msg_y))
            name_x = sidebar_x + 30 + time_text.get_width() + 5

            # Draw [TEAM] indicator for team messages (green color)
            if channel == 'team':
                team_text = self.get_cached_text("[TEAM]", self.game.small_font, (100, 200, 100), "small")
                self.game.screen.blit(team_text, (name_x, msg_y))
                name_x += team_text.get_width() + 5

            # Draw player name in their color
            name_text = self.get_cached_text(player_name + ":", self.game.small_font, player_color, "small")
            self.game.screen.blit(name_text, (name_x, msg_y))
            msg_y += 18

            # Draw message (word wrapped)
            max_chars = UIConstants.MESSAGE_MAX_CHARS
            if len(message) > max_chars:
                words = message.split()
                line = ""
                for word in words:
                    test_line = line + " " + word if line else word
                    if len(test_line) > max_chars:
                        msg_text = self.get_cached_text(line, self.game.small_font, (200, 200, 200), "small")
                        self.game.screen.blit(msg_text, (sidebar_x + 30, msg_y))
                        msg_y += 16
                        line = word

                        # Check space again
                        if msg_y + 30 > sidebar_y + sidebar_height - 40:
                            break
                    else:
                        line = test_line

                # Draw last line
                if line and msg_y + 20 < sidebar_y + sidebar_height - 40:
                    msg_text = self.get_cached_text(line, self.game.small_font, (200, 200, 200), "small")
                    self.game.screen.blit(msg_text, (sidebar_x + 30, msg_y))
                    msg_y += 16
            else:
                # Short message - draw directly
                msg_text = self.get_cached_text(message, self.game.small_font, (200, 200, 200), "small")
                self.game.screen.blit(msg_text, (sidebar_x + 30, msg_y))
                msg_y += 16
            
            # Add gap between messages
            msg_y += 8
        
        # Calculate actual end index based on what we rendered
        actual_end_index = start_msg_index + messages_rendered
        
        # Draw scroll position indicator on right side
        if total_messages > messages_rendered:
            # Calculate scroll position
            max_scroll = total_messages - messages_rendered
            scroll_percentage = 1.0 - (self.game.chat_scroll_offset / max_scroll) if max_scroll > 0 else 1.0
            
            # Scrollbar dimensions
            scrollbar_x = sidebar_x + sidebar_width - UIConstants.SCROLLBAR_OFFSET
            scrollbar_top = header_y + UIConstants.HEADER_OFFSET
            scrollbar_height = sidebar_y + sidebar_height - scrollbar_top - 10
            
            # Draw scrollbar track
            pygame.draw.rect(self.game.screen, (60, 60, 60), 
                           (scrollbar_x, scrollbar_top, UIConstants.SCROLLBAR_WIDTH, scrollbar_height))
            
            # Draw scrollbar thumb
            thumb_height = max(UIConstants.SCROLLBAR_THUMB_MIN, int(scrollbar_height * (messages_rendered / total_messages)))
            thumb_y = scrollbar_top + int((scrollbar_height - thumb_height) * scroll_percentage)
            pygame.draw.rect(self.game.screen, (150, 150, 150), 
                           (scrollbar_x, thumb_y, UIConstants.SCROLLBAR_WIDTH, thumb_height))
            
            # Draw position text
            position_text = f"{actual_end_index}/{total_messages}"
            pos_text_surface = self.get_cached_text(position_text, self.game.small_font, (120, 120, 120), "small")
            pos_rect = pos_text_surface.get_rect(right=sidebar_x + sidebar_width - 15,
                                                  bottom=sidebar_y + sidebar_height - 5)
            self.game.screen.blit(pos_text_surface, pos_rect)

    def _draw_heroes_content(self, sidebar_x, sidebar_y, sidebar_width, sidebar_height, content_start_y):
        """Draw Heroes tab content showing active heroes and training progress."""
        # Initialize hero button storage for click detection
        if not hasattr(self.game, 'hero_selection_buttons'):
            self.game.hero_selection_buttons = {}
        self.game.hero_selection_buttons = {}

        # Header
        # FPS OPTIMIZATION 4.1: Use cached text for static header
        header_y = content_start_y
        header_text = self.get_cached_text("Heroes", self.game.font, WHITE, "font")
        header_rect = header_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y)
        self.game.screen.blit(header_text, header_rect)

        # Show LOCAL player's heroes (not current turn player)
        if self.game.multiplayer_mode:
            current_player = self.game.local_player_index if self.game.local_player_index is not None else 0
        else:
            current_player = 0
            for i in range(self.game.game_state.num_players):
                if not self.game.game_state.player_is_ai[i]:
                    current_player = i
                    break

        # Hero limit display (centered below header)
        current_hero_count = len(self.game.game_state.hero_ownership[current_player])
        hero_limit = self.game.game_state.player_hero_limit[current_player]
        limit_text = self.get_cached_text(f"Hero Limit: {current_hero_count}/{hero_limit}", self.game.small_font, (200, 200, 100), "small")
        limit_rect = limit_text.get_rect(centerx=sidebar_x + sidebar_width // 2, y=header_y + 25)
        self.game.screen.blit(limit_text, limit_rect)

        # Separator
        pygame.draw.line(self.game.screen, (100, 100, 100),
                        (sidebar_x + 30, header_y + 50),
                        (sidebar_x + sidebar_width - 10, header_y + 50), 2)

        # Check for heroes
        has_active = (current_player in self.game.game_state.heroes and
                      len(self.game.game_state.heroes[current_player]) > 0)

        has_training = False
        for territory, keeps_dict in self.game.game_state.hero_training_queue.items():
            if self.game.game_state.territory_owners.get(territory, -1) == current_player:
                has_training = True
                break

        if not has_active and not has_training:
            # Empty state
            # FPS OPTIMIZATION 4.1: Use cached text for static messages
            empty_text = self.get_cached_text("No heroes yet", self.game.small_font, (150, 150, 150), "small_font")
            empty_rect = empty_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 100))
            self.game.screen.blit(empty_text, empty_rect)

            hint_text = self.get_cached_text("Train heroes from Keeps", self.game.small_font, (120, 120, 120), "small_font")
            hint_rect = hint_text.get_rect(center=(sidebar_x + sidebar_width // 2, header_y + 130))
            self.game.screen.blit(hint_text, hint_rect)
            return

        hero_y = header_y + 70

        # Active Heroes Section
        if has_active:
            # FPS OPTIMIZATION 4.1: Use cached text for static section title
            section_title = self.get_cached_text("Active Heroes:", self.game.font, (200, 200, 200), "font")
            self.game.screen.blit(section_title, (sidebar_x + 30, hero_y))
            hero_y += 30

            for hero_type, hero_data in self.game.game_state.heroes[current_player].items():
                # Hero box - taller height for better text visibility
                hero_rect = pygame.Rect(sidebar_x + 30, hero_y, sidebar_width - 60, 85)

                # Check if this hero is selected
                is_selected = (self.game.selected_hero == hero_type)

                # Draw background with selection highlight
                if is_selected:
                    # Selected hero: darker background with thick gold border
                    pygame.draw.rect(self.game.screen, (80, 80, 100), hero_rect, border_radius=5)
                    pygame.draw.rect(self.game.screen, (218, 165, 32), hero_rect, 4, border_radius=5)
                else:
                    # Unselected hero: lighter background with thin blue border
                    pygame.draw.rect(self.game.screen, (40, 40, 50), hero_rect, border_radius=5)
                    pygame.draw.rect(self.game.screen, (100, 150, 200), hero_rect, 2, border_radius=5)

                # Store rect for click detection
                self.game.hero_selection_buttons[hero_type] = hero_rect

                # Hero name
                name_text = self.get_cached_text(hero_type, self.game.font, (200, 200, 100), "font")
                self.game.screen.blit(name_text, (sidebar_x + 40, hero_y + 5))

                # Keep location
                location = f"Keep: {hero_data['keep_territory']}"
                location_text = self.get_cached_text(location, self.game.small_font, (150, 150, 150), "small")
                self.game.screen.blit(location_text, (sidebar_x + 40, hero_y + 28))

                # Abilities: Coming Soon text removed per user request

                hero_y += 95  # Adjusted spacing for taller button

        # Training Heroes Section
        if has_training:
            # FPS OPTIMIZATION 4.1: Use cached text for static section title
            section_title = self.get_cached_text("Training:", self.game.font, (200, 200, 200), "font")
            self.game.screen.blit(section_title, (sidebar_x + 30, hero_y))
            hero_y += 30

            for territory, keeps_dict in self.game.game_state.hero_training_queue.items():
                owner = self.game.game_state.territory_owners.get(territory, -1)
                if owner != current_player:
                    continue

                for keep_plot, entry in keeps_dict.items():
                    # H4 fix: handle 3-tuple (hero_type, turns, paid_cost)
                    hero_type, turns_remaining = entry[0], entry[1]
                    # Training box
                    training_rect = pygame.Rect(sidebar_x + 30, hero_y, sidebar_width - 60, 60)
                    pygame.draw.rect(self.game.screen, (60, 50, 50), training_rect, border_radius=5)
                    pygame.draw.rect(self.game.screen, (200, 150, 100), training_rect, 2, border_radius=5)

                    # Hero name
                    name_text = self.get_cached_text(hero_type, self.game.font, (200, 150, 100), "font")
                    self.game.screen.blit(name_text, (sidebar_x + 40, hero_y + 5))

                    # Progress. No "Training:" prefix - the panel is already the
                    # hero training list, and the full label overran its column.
                    # Singular/plural so the last turn does not read "1 turns".
                    progress = "%d %s remaining" % (
                        turns_remaining,
                        "turn" if turns_remaining == 1 else "turns")
                    progress_text = self.get_cached_text(progress, self.game.small_font, (150, 150, 150), "small")
                    self.game.screen.blit(progress_text, (sidebar_x + 40, hero_y + 28))

                    # Location
                    location = f"Keep: {territory}"
                    location_text = self.get_cached_text(location, self.game.small_font, (120, 120, 120), "small")
                    self.game.screen.blit(location_text, (sidebar_x + 40, hero_y + 45))

                    hero_y += 70

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
