# -*- coding: utf-8 -*-
# ui/scaler.py
# UI scaling system for dynamic resolution support

"""
UI Scaling System
=================

This module provides dynamic UI scaling that adjusts panel sizes based on window resolution.

Classes:
    UIScaler: Calculates UI layout dimensions for any window size
    UIConstants: Centralized UI layout constants

The UIScaler solves the problem of fixed pixel values creating blank space or cramped UIs
at different resolutions. Instead of fixed heights, we use proportions of the window height
with min/max constraints.

Design Philosophy:
    - Top panel: Small, fixed height (doesn't need to scale much)
    - Bottom UI: Scales proportionally with window height (23-25% of window)
    - Map area: Gets remaining space
    - Sidebar: Matches map height

Benefits:
    - No blank spaces at any resolution
    - UI elements stay in roughly the same visual positions
    - Proportions maintained across resolutions
    - Professional appearance at all sizes
"""


class UIScaler:
    """
    Dynamic UI scaling system that adjusts panel sizes based on window resolution.
    """
    
    @staticmethod
    def calculate_ui_layout(window_width, window_height):
        """
        Calculate all UI dimensions for a given window size.
        
        Args:
            window_width: Window width in pixels
            window_height: Window height in pixels
            
        Returns:
            dict with keys: top_height, bottom_height, map_height, bottom_y, sidebar_height, sidebar_width
            
        Example:
            >>> layout = UIScaler.calculate_ui_layout(1920, 1080)
            >>> layout['bottom_height']
            253
        """
        # Top panel: Fixed small height (scales slightly for very large resolutions)
        # 40px base, +1px per 100px of height above 850
        top_height = 40 + max(0, (window_height - 850) // 100)
        top_height = min(top_height, 60)  # Cap at 60px
        
        # Bottom UI: 23-25% of window height (maintains proportion)
        # This ensures bottom UI scales with window while keeping reasonable size
        # L17: 0.235 chosen to match the reference 1600x900 layout where bottom panel = 212px
        # (212 / 900 ≈ 0.235). Constrained to 180-300px to stay usable at extremes.
        bottom_height_ratio = 0.235  # 23.5% of window height
        bottom_height = int(window_height * bottom_height_ratio)
        
        # Apply constraints to keep bottom UI usable
        bottom_height = max(180, min(bottom_height, 300))  # Between 180-300px
        
        # Map area: Gets all remaining space
        map_height = window_height - top_height - bottom_height
        
        # Bottom UI Y position: Right after map
        bottom_y = top_height + map_height
        
        # Sidebar: Matches map height exactly (no gaps)
        sidebar_height = map_height
        
        return {
            'top_height': top_height,
            'bottom_height': bottom_height,
            'map_height': map_height,
            'bottom_y': bottom_y,
            'sidebar_height': sidebar_height,
            'sidebar_width': 250  # Fixed for now, could scale in future
        }


class UIConstants:
    """
    Centralized UI layout constants for easy adjustment and maintainability.
    
    This class contains all the magic numbers used throughout the UI rendering code.
    Extracting these constants makes it easier to:
    - Adjust UI layout globally
    - Understand what values mean
    - Maintain consistency
    - Prevent errors from typos
    
    Note: SIDEBAR_HEIGHT is dynamically calculated and updated when resolution changes.
          Access it via the ui_layout dict or update this class when resolution changes.
    """
    
    # ===== SIDEBAR DIMENSIONS =====
    SIDEBAR_WIDTH = 250  # Width of right sidebar (action queue, chat, etc.)
    SIDEBAR_HEIGHT = 0   # Height matches map height (dynamic, set at runtime)
    
    # ===== MESSAGE DISPLAY =====
    # Pixels per message - used for calculating how many messages fit
    PIXELS_PER_MESSAGE_SELECTION = 40  # Conservative estimate for selecting messages
    PIXELS_PER_MESSAGE_SCROLL = 40     # Conservative estimate for scroll limits
    MESSAGE_MAX_CHARS = 28             # Maximum characters per line before wrapping
    
    # ===== TAB SYSTEM =====
    TAB_WIDTH = 40           # Width of vertical tab buttons sticking out from sidebar
    TAB_PADDING_TOP = 45     # Padding at top of tab button area
    TAB_PADDING_BOTTOM = 45  # Padding at bottom of tab button area

    # ===== COLLAPSE / EXPAND (ui/sidebar_layout.py) =====
    SIDEBAR_SLIDE_MS = 150       # Duration of the collapse/expand slide
    SIDEBAR_TOGGLE_HEIGHT = 37   # Collapse button above the tabs (fits in TAB_PADDING_TOP)
    
    # ===== SCROLLBAR =====
    SCROLLBAR_WIDTH = 4        # Width of scrollbar track and thumb
    SCROLLBAR_OFFSET = 8       # Distance from right edge of sidebar
    SCROLLBAR_THUMB_MIN = 20   # Minimum height of scrollbar thumb
    
    # ===== CONTENT SPACING =====
    HEADER_OFFSET = 45         # Y offset for content below header
    BOTTOM_RESERVE = 40        # Space reserved at bottom for scroll indicator
    SIDEBAR_CONTENT_PADDING = 100  # Total padding for sidebar content (header + footer)
    
    @classmethod
    def update_sidebar_height(cls, height):
        """Update the dynamic SIDEBAR_HEIGHT value."""
        cls.SIDEBAR_HEIGHT = height