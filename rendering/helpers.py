# -*- coding: utf-8 -*-
# rendering/helpers.py
# Reusable drawing utility functions

"""
Rendering Helpers
=================

This module provides reusable drawing utilities for buttons, tooltips, badges, and separators.

Classes:
    DrawingHelpers: Collection of drawing utility methods

These were extracted from main.py to eliminate code duplication and improve maintainability.
"""

import pygame
from config.constants import *
from utils.colors import lighten_color, brighten_color


class DrawingHelpers:
    """
    Collection of reusable drawing utilities.
    
    This class encapsulates common drawing operations like buttons, tooltips,
    badges, and separators. It's designed to be instantiated with the necessary
    dependencies (screen, fonts, etc.) and then used throughout rendering.
    """
    
    def __init__(self, screen, font, small_font, large_font, separator_image=None, separator_width=3, small_font_bold=None):
        """
        Initialize drawing helpers with necessary dependencies.

        Args:
            screen: pygame.Surface to draw on
            font: Normal pygame.Font
            small_font: Small pygame.Font
            large_font: Large pygame.Font
            separator_image: Optional separator image surface
            separator_width: Width of separator (for centering image)
            small_font_bold: Small bold pygame.Font (Phase 3: for tooltip names)
        """
        self.screen = screen
        self.font = font
        self.small_font = small_font
        self.large_font = large_font
        self.separator_image = separator_image
        self.separator_width = separator_width
        self.small_font_bold = small_font_bold if small_font_bold else small_font  # Fallback to small_font if not provided
        # Cache for scaled+darkened button background images to avoid recreating every frame
        # Key: (id(bg_image), width, height) -> pre-darkened pygame.Surface
        self._button_bg_cache = {}
        # PERFORMANCE: Text rendering cache for button labels (avoids font.render() every frame)
        # Key: (text, id(font), color) -> pygame.Surface
        self.text_cache = {}
        self._text_cache_max_size = 200
    
    def update_separator(self, separator_image, separator_width):
        """Update separator image and width (for resolution changes)."""
        self.separator_image = separator_image
        self.separator_width = separator_width
    
    def draw_feedback_button(self, rect, base_color, mouse_pos, clicked_element,
                            button_type, button_id, text=None, text_color=WHITE,
                            font=None, border_color=BLACK, border_width=2,
                            bg_image=None):
        """
        Draw a button with automatic hover/click feedback.

        This is a reusable button renderer that handles:
        - Hover detection and brightening (+20%)
        - Click flash detection and brightening (+40%)
        - Background fill (solid color or image)
        - Border drawing
        - Optional centered text

        Args:
            rect: pygame.Rect for button bounds
            base_color: RGB tuple for normal button color
            mouse_pos: Current mouse position tuple
            clicked_element: Tuple of (button_type, button_id) for active click, or None
            button_type: String identifier for click tracking (e.g., 'bottom_button')
            button_id: Unique ID within type (e.g., 'end_turn')
            text: Optional text to center in button
            text_color: Color for text (default WHITE)
            font: pygame.Font to use (default self.font)
            border_color: Color for border (default BLACK)
            border_width: Width of border in pixels (default 2)
            bg_image: Optional pygame.Surface to use as button background (with hover/click brightening)

        Returns:
            tuple: (final_color, is_hovering, is_clicking) for additional rendering
        """
        # Check hover
        is_hovering = rect.collidepoint(mouse_pos)

        # Check click flash
        is_clicking = (clicked_element and
                      clicked_element[0] == button_type and
                      clicked_element[1] == button_id)

        # Draw background - either image or solid color
        if bg_image:
            # Cache the scaled + darkened base image to avoid expensive scale/blend every frame
            # Key by image identity and target dimensions (handles resize / different buttons)
            cache_key = (id(bg_image), rect.width, rect.height)
            base_img = self._button_bg_cache.get(cache_key)

            if base_img is None:
                # First time: scale and apply darkening, then store in cache
                scaled_img = pygame.transform.scale(bg_image, (rect.width, rect.height))
                base_img = scaled_img.copy()

                # Apply darkening to the actual image pixels (preserves PNG shape/transparency)
                # Use fill with BLEND_RGBA_MULT to darken while preserving alpha channel
                # Matches main menu darkening: (100, 100, 100) = ~39% brightness
                dark_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                dark_surface.fill((100, 100, 100, 255))  # Same darkening as main menu buttons
                base_img.blit(dark_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                self._button_bg_cache[cache_key] = base_img

            # Apply brightness effect for hover/click (only when active - needs per-frame copy)
            # Matches main menu: 40 for hover, 80 for click
            if is_clicking or is_hovering:
                modified_img = base_img.copy()
                # Brighten by adding light to the image (only affects non-transparent pixels)
                brightness_factor = 80 if is_clicking else 40  # Same values as main menu
                bright_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                bright_surface.fill((brightness_factor, brightness_factor, brightness_factor, 0))
                modified_img.blit(bright_surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
                self.screen.blit(modified_img, rect.topleft)
            else:
                # No hover/click - blit the cached base directly (no copy needed)
                self.screen.blit(base_img, rect.topleft)
        else:
            # Apply visual feedback to color
            final_color = base_color
            if is_clicking:
                final_color = brighten_color(base_color, 0.4)
            elif is_hovering:
                final_color = lighten_color(base_color, 0.2)

            # Draw solid color background
            pygame.draw.rect(self.screen, final_color, rect)

            # Draw border
            if border_width > 0:
                pygame.draw.rect(self.screen, border_color, rect, border_width)

        # Draw text if provided (drawn on top of everything)
        # PERFORMANCE: Use text cache to avoid font.render() every frame for static button labels
        if text:
            if font is None:
                font = self.font
            cache_key = (text, id(font), text_color)
            text_surf = self.text_cache.get(cache_key)
            if text_surf is None:
                if len(self.text_cache) >= self._text_cache_max_size:
                    oldest_key = next(iter(self.text_cache))
                    del self.text_cache[oldest_key]
                text_surf = font.render(text, True, text_color)
                self.text_cache[cache_key] = text_surf
            text_rect = text_surf.get_rect(center=rect.center)
            self.screen.blit(text_surf, text_rect)

        return (base_color, is_hovering, is_clicking)
    
    def draw_tooltip_box(self, pos, lines, max_width=None, bg_color=(255, 255, 220),
                        border_color=BLACK, padding=8, line_spacing=2, use_transparency=False, bottom_ui_y=None):
        """
        Draw a tooltip box with multiple lines of text.
        
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
                   - String: Uses small_font and BLACK
                   - (text, color): Uses small_font with custom color
                   - ("normal", text, color): Uses font
                   - ("small", text, color): Uses small_font
                   - ("small_bold", text, color): Uses small_font_bold (Phase 3: for tooltip names)
                   - ("large", text, color): Uses large_font
            max_width: Optional max width in pixels
            bg_color: RGB or RGBA tuple for background
            border_color: RGB or RGBA tuple for border
            padding: Pixels of padding around text (default 8)
            line_spacing: Pixels between lines (default 2)
            use_transparency: If True, creates semi-transparent surface
            bottom_ui_y: Optional Y coordinate of bottom UI panel to avoid overlap
        
        Returns:
            pygame.Rect: The rect of the drawn tooltip
        """
        # Normalize lines to (font, text, color) tuples
        normalized_lines = []
        for line in lines:
            if isinstance(line, tuple):
                if len(line) == 3 and isinstance(line[0], str) and line[0] in ['normal', 'small', 'small_bold', 'large']:
                    # Already (font_size, text, color) format (Phase 3: added 'small_bold')
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
            # Select appropriate font (Phase 3: added small_bold support)
            if font_size == "large":
                font = self.large_font
            elif font_size == "normal":
                font = self.font
            elif font_size == "small_bold":
                font = self.small_font_bold
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

        # Adjust if tooltip goes off bottom edge
        # Use bottom_ui_y as the boundary if provided (to avoid hiding under bottom UI panel)
        max_bottom = bottom_ui_y if bottom_ui_y is not None else WINDOW_HEIGHT
        if tooltip_y + tooltip_height > max_bottom:
            tooltip_y = max_bottom - tooltip_height - 10

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
    
    def draw_letter_button(self, rect, letter, bg_color, mouse_pos, clicked_element,
                          letter_color=WHITE, border_color=BLACK, border_width=2, 
                          button_type=None, button_id=None):
        """
        Draw a square button with a centered letter.
        
        Supports hover and click visual feedback!
        
        Args:
            rect: pygame.Rect for button position and size
            letter: Single character to display (e.g., 'S', 'F', 'B')
            bg_color: Background color (RGB or RGBA tuple)
            mouse_pos: Current mouse position tuple
            clicked_element: Tuple of (button_type, button_id) for active click, or None
            letter_color: Letter color (default: WHITE)
            border_color: Border color (default: BLACK)
            border_width: Border width in pixels (default: 2)
            button_type: Optional - type for hover/click feedback (e.g., 'training')
            button_id: Optional - identifier for hover/click feedback (e.g., 'Swordsman')
        """
        # Apply hover/click feedback if identifiers provided
        final_bg_color = bg_color
        if button_type and button_id:
            # Check for hover
            is_hovering = rect.collidepoint(mouse_pos)
            
            # Check for click flash
            is_clicking = (clicked_element and 
                          clicked_element[0] == button_type and 
                          clicked_element[1] == button_id)
            
            # Apply visual feedback
            if is_clicking:
                final_bg_color = brighten_color(bg_color, 0.4)
            elif is_hovering:
                final_bg_color = lighten_color(bg_color, 0.2)
        
        # Draw filled background
        pygame.draw.rect(self.screen, final_bg_color, rect)
        
        # Draw border
        pygame.draw.rect(self.screen, border_color, rect, border_width)
        
        # Draw centered letter
        letter_surf = self.large_font.render(letter, True, letter_color)
        letter_rect = letter_surf.get_rect(center=rect.center)
        self.screen.blit(letter_surf, letter_rect)
    
    def draw_circle_badge(self, pos, text, bg_color=WHITE, border_color=None, 
                         text_color=BLACK, radius=None):
        """
        Draw a circular badge with centered text.
        
        Args:
            pos: (x, y) tuple for badge center position
            text: Text to display (will be converted to string)
            bg_color: Background color (default: WHITE)
            border_color: Border color (default: same as bg_color if None)
            text_color: Text color (default: BLACK)
            radius: Badge radius (default: BADGE_RADIUS constant)
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
    
    def draw_separator(self, x_position, bottom_ui_y, bottom_ui_height):
        """
        Draw a vertical separator in the bottom UI panel.
        
        Uses custom separator image if available, falls back to line drawing.
        Separator extends from top to bottom of panel (no margins).
        
        Args:
            x_position: X coordinate for separator (centered on this position)
            bottom_ui_y: Y coordinate where bottom panel starts
            bottom_ui_height: Height of the bottom panel
        """
        separator_start_y = bottom_ui_y  # Start at very top of panel
        separator_height = bottom_ui_height  # Full panel height
        
        if self.separator_image:
            # Draw custom separator image
            # Center the image on x_position
            image_x = x_position - (self.separator_width // 2)
            self.screen.blit(self.separator_image, (image_x, separator_start_y))
        else:
            # Fallback to line drawing
            pygame.draw.line(self.screen, BROWN_SEPARATOR,
                           (x_position, separator_start_y),
                           (x_position, separator_start_y + separator_height), 3)

    def wrap_text_smart(self, text, font, max_width):
        """
        Intelligently wrap text to fit within max_width, breaking at natural points.

        Attempts to break long text into multiple lines by:
        1. Trying to split at spaces (word boundaries)
        2. Preferring breaks near the middle for balanced lines
        3. Handling multiple words if necessary

        Args:
            text: String to wrap
            font: pygame.Font to use for measuring
            max_width: Maximum pixel width for each line

        Returns:
            List of strings (lines), or [text] if no wrapping needed

        Example:
            "South Affrancia" might become ["South", "Affrancia"]
            "Empire of South Affrancia" might become ["Empire of", "South Affrancia"]
        """
        # Check if text fits without wrapping
        text_width = font.size(text)[0]
        if text_width <= max_width:
            return [text]

        # Try to split at spaces
        words = text.split()
        if len(words) == 1:
            # Single long word - can't wrap intelligently, return as-is
            return [text]

        # Try to find best split point (prefer splitting near middle)
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_width = font.size(test_line)[0]

            if test_width <= max_width:
                current_line.append(word)
            else:
                # Current line + word exceeds width
                if current_line:
                    # Save current line and start new one with this word
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Even single word is too long, add it anyway
                    lines.append(word)

        # Add remaining words
        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]

    @staticmethod
    def crop_to_circle(surface):
        """
        Crop a square surface to a circle with transparency.

        Creates a circular mask on the surface, making everything outside
        the circle fully transparent. This is useful for fitting square
        images into circular borders.

        Args:
            surface: pygame.Surface to crop (should be square for best results)

        Returns:
            pygame.Surface: New surface with circular crop and transparency

        Performance: Uses hardware-accelerated BLEND_RGBA_MULT instead of
        per-pixel get_at/set_at (10x+ faster for typical hero portraits).
        """
        size = surface.get_size()
        center_x = size[0] // 2
        center_y = size[1] // 2
        radius = min(center_x, center_y)

        # Create circular mask with white circle on transparent background
        # White pixels preserve original alpha, transparent pixels mask out
        mask_surface = pygame.Surface(size, pygame.SRCALPHA)
        mask_surface.fill((0, 0, 0, 0))
        pygame.draw.circle(mask_surface, (255, 255, 255, 255), (center_x, center_y), radius)

        # Copy original and apply mask using hardware-accelerated blend
        # BLEND_RGBA_MULT multiplies each channel: result = src * mask / 255
        # Where mask is white (255,255,255,255): preserves original pixels
        # Where mask is transparent (0,0,0,0): makes result transparent
        result = surface.copy()
        result.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        return result