# -*- coding: utf-8 -*-
# input/mouse_handler.py
# Mouse input handling coordinator

"""
Mouse Handler
=============

This module coordinates all mouse input for the game using a delegator pattern.

The MouseHandler acts as an organizational layer that routes mouse events to
the appropriate handling methods in the Game class. This provides better
code organization while maintaining access to game state.

Methods Coordinated (1,211 lines total):
- Map clicks (territory, army, plot selection)
- Right-click orders (movement, attack)
- UI clicks (panels, menus, buttons)
- Hover detection (tooltips, highlights)

Extracted from main.py during Phase 3 of refactoring.
"""

import pygame


class MouseHandler:
    """
    Coordinates mouse input handling.
    
    This class acts as a router/coordinator for mouse events, organizing
    the 12 different mouse handling methods into a cohesive interface.
    
    Design Pattern: Delegator
    - MouseHandler doesn't duplicate logic
    - Methods delegate to Game class handlers
    - Provides organizational structure
    - Maintains access to game state
    """
    
    def __init__(self, game_instance, top_panel_height, bottom_ui_y, window_width):
        """
        Initialize mouse handler with game instance and layout values.
        
        Args:
            game_instance: Reference to Game instance for delegation
            top_panel_height: Height of top panel
            bottom_ui_y: Y position where bottom UI starts
            window_width: Window width
        """
        self.game = game_instance
        self.top_panel_height = top_panel_height
        self.bottom_ui_y = bottom_ui_y
        self.window_width = window_width
    
    def update_layout(self, top_panel_height, bottom_ui_y, window_width):
        """
        Update layout values (called when resolution changes).
        
        Args:
            top_panel_height: New top panel height
            bottom_ui_y: New bottom UI Y position
            window_width: New window width
        """
        self.top_panel_height = top_panel_height
        self.bottom_ui_y = bottom_ui_y
        self.window_width = window_width
    
    def handle_left_click(self, pos):
        """
        Route left-click to appropriate handler based on screen area.
        
        Args:
            pos: Click position (x, y)
            
        Returns:
            bool or tuple: True if handled, or (handled, should_quit) tuple
        """
        # L1: Click priority chain (highest to lowest). First match consumes the click.
        # 1. Victory screen  2. Battle popup  2.5. Alliance choice popup
        # 3. Options menu    4. Game menu     5. Top panel
        # 6. Battle markers  6.5. Alliance markers  7. Order sidebar / tabs
        # 8. Bottom UI       9. Map area (territory selection, movement orders)

        # Priority 1: Victory screen - only intercept if NOT using cinematic sequence
        # During victory_sequence_pending, let clicks through so battles can still be resolved
        if (self.game.game_state.phase == 'ended'
                and not self.game.victory_sequence_pending
                and not self.game.victory_sequence_active):
            return self.game.handle_victory_screen_click(pos)  # Returns (handled, should_quit)
        
        # Priority 2: Battle popup (if visible)
        if self.game.battle_popup_visible:
            return self.game.handle_battle_popup_click(pos)

        # Priority 2.5: Alliance choice popup (simultaneous mode)
        if getattr(self.game, 'alliance_choice_popup_visible', False):
            return self.game.handle_alliance_choice_click(pos)

        # Priority 3: Options menu (if visible)
        if self.game.options_menu_visible:
            return self.game.handle_options_menu_click(pos)  # Returns (handled, should_quit)
        
        # Priority 4: Game menu (if visible)
        if self.game.game_menu_visible:
            return self.game.handle_game_menu_click(pos)  # Returns (handled, should_quit)
        
        # Priority 5: Top panel
        if pos[1] < self.top_panel_height:
            return self.game.handle_top_panel_click(pos)
        
        # Priority 6: Battle markers
        if hasattr(self.game, 'battle_markers'):
            for i, marker_rect in enumerate(self.game.battle_markers):
                if marker_rect and marker_rect.collidepoint(pos):
                    return self.game.handle_battle_marker_click(pos)

        # Priority 6.5: Alliance markers (simultaneous mode)
        # Blue particle effects that appear when allies capture territory together
        # M21: Validate marker has 'rect' key before accessing it
        if hasattr(self.game, 'alliance_markers') and self.game.alliance_markers:
            for marker in self.game.alliance_markers:
                if 'rect' in marker and marker['rect'] and marker['rect'].collidepoint(pos):
                    return self.game.handle_alliance_marker_click(pos, marker)

        # Priority 7: Order sidebar (expanded or collapsed)
        # M20: Always check toggle button regardless of sidebar state, so the rect
        # is tested whether sidebar is expanded or collapsed. This prevents the button
        # from becoming unresponsive when sidebar state gets out of sync.
        if hasattr(self.game, 'sidebar_toggle_button') and self.game.sidebar_toggle_button:
            if self.game.sidebar_toggle_button.collidepoint(pos):
                # Toggle sidebar expansion/collapse
                self.game.game_state.sidebar_expanded = not self.game.game_state.sidebar_expanded
                return True

        if self.game.game_state.sidebar_expanded:
            sidebar_x = self.window_width - 250
            if pos[0] >= sidebar_x:
                # Always check tab buttons first (they're on the left edge, outside sidebar_x)
                # But we still handle content inside the sidebar here
                if self.game.game_state.active_sidebar_tab == 'action_queue':
                    handled = self.game.handle_order_sidebar_click(pos)
                    if handled:
                        return handled
                elif self.game.game_state.active_sidebar_tab == 'action_log':
                    # Action log is read-only — consume click to prevent map interaction
                    return True
                elif self.game.game_state.active_sidebar_tab == 'heroes':
                    # MULTIPLAYER: Block hero tab clicks for spectators
                    if not self.game.is_local_player_active():
                        return True  # Block but don't process
                    handled = self.game.handle_heroes_tab_click(pos)
                    if handled:
                        return handled
                elif self.game.game_state.active_sidebar_tab == 'technology':
                    # MULTIPLAYER: Block technology tab clicks for spectators
                    if not self.game.is_local_player_active():
                        return True  # Block but don't process
                    handled = self.game.handle_technology_tab_click(pos)
                    if handled:
                        return handled

                # Consume click even if no tab handler matched — prevent map fallthrough
                return True

            # Tab buttons stick out to the LEFT of the sidebar, so check them separately
            # They're at (sidebar_x - tab_width), so pos[0] < sidebar_x
            if pos[0] < sidebar_x and pos[0] >= sidebar_x - 40:  # Tab width is ~40px
                # This could be a tab button click
                handled = self.game.handle_order_sidebar_click(pos)
                if handled:
                    return handled
        
        # Priority 8: Bottom UI
        if pos[1] >= self.bottom_ui_y:
            return self.game.handle_bottom_ui_click(pos)
        
        # Priority 9: Map area
        return self.game.handle_map_area_click(pos)
    
    def handle_right_click(self, pos):
        """
        Handle right-click for orders.
        
        Args:
            pos: Click position (x, y)
            
        Returns:
            bool: True if click was handled
        """
        return self.game.handle_right_click(pos)
    
    def handle_mouse_motion(self, pos):
        """
        Handle mouse motion for hover effects.
        
        Args:
            pos: Mouse position (x, y)
        """
        self.game.handle_mouse_motion(pos)
    
    def get_click_area(self, pos):
        """
        Determine which area of the screen was clicked.
        
        Useful for debugging and analytics.
        
        Args:
            pos: Click position (x, y)
            
        Returns:
            str: Area name ('top_panel', 'map', 'bottom_ui', 'sidebar', etc.)
        """
        if self.game.game_state.phase == 'ended':
            return 'victory_screen'
        
        if self.game.battle_popup_visible:
            return 'battle_popup'
        
        if self.game.game_menu_visible:
            return 'game_menu'
        
        if self.game.options_menu_visible:
            return 'options_menu'
        
        if pos[1] < self.top_panel_height:
            return 'top_panel'
        
        if pos[1] >= self.bottom_ui_y:
            return 'bottom_ui'
        
        if self.game.game_state.sidebar_expanded:
            sidebar_x = self.window_width - 250
            if pos[0] >= sidebar_x:
                return 'sidebar'
        
        return 'map_area'