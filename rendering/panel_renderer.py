# -*- coding: utf-8 -*-
# rendering/panel_renderer.py
# Panel rendering coordinator

"""
Panel Renderer
==============

This module coordinates panel rendering using a delegator pattern.

The PanelRenderer acts as an organizational layer that groups panel rendering
methods together. This provides better code organization while maintaining
access to game state.

Methods Coordinated (773 lines total):
- Bottom UI panel (buttons, context panels)
- Order sidebar (movement orders, action log, chat)
- Territory info panel
- Barracks training panel

Extracted from main.py during Phase 4 of refactoring.
"""

import pygame


class PanelRenderer:
    """
    Coordinates panel rendering.
    
    This class acts as a router/coordinator for panel rendering, organizing
    the various panel methods into a cohesive interface.
    
    Design Pattern: Delegator/Coordinator
    - PanelRenderer doesn't duplicate logic
    - Methods delegate to Game class renderers
    - Provides organizational structure
    - Maintains access to game state
    """
    
    def __init__(self, game_instance):
        """
        Initialize panel renderer with game instance.
        
        Args:
            game_instance: Reference to Game instance for delegation
        """
        self.game = game_instance
    
    def render_panels_layer(self):
        """
        Render the complete panels layer.
        
        This includes:
        - Bottom UI panel
        - Right sidebar (if expanded)
        """
        # Bottom UI (always visible)
        self.game.draw_bottom_ui()
        
        # Right sidebar (if expanded)
        if self.game.game_state.sidebar_expanded:
            self.game.draw_order_sidebar()