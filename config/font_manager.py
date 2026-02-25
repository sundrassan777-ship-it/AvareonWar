"""
Font Manager Module
Centralized font loading and caching system for custom fonts (Cinzel).
Provides consistent font access across the game with performance optimization.
"""

import pygame
import os

from utils.logger import get_logger

logger = get_logger(__name__)


class FontManager:
    """
    Manages loading, caching, and retrieval of custom fonts.

    Purpose:
    - Load Cinzel fonts (Regular and SemiBold) with fallback to Arial
    - Cache fonts by (size, weight) to avoid recreating fonts every frame
    - Provide convenient methods for getting fonts of different sizes and weights
    - Maintain 60fps by reusing cached font objects
    """

    def __init__(self):
        """Initialize the font manager with empty cache."""
        self.font_cache = {}  # Cache: {(size, weight): pygame.Font}
        self.cinzel_regular_path = None
        self.cinzel_semibold_path = None
        self.cinzel_bold_path = None
        self.fonts_loaded = False

    def load_fonts(self, base_path):
        """
        Load Cinzel font files from the assets directory.

        Args:
            base_path: Base path to the game directory (where assets/ is located)

        Returns:
            bool: True if fonts loaded successfully, False if fallback to system font
        """
        # Construct paths to Cinzel fonts
        cinzel_regular = os.path.join(base_path, "assets", "fonts", "Cinzel-Regular.ttf")
        cinzel_semibold = os.path.join(base_path, "assets", "fonts", "Cinzel-SemiBold.ttf")
        cinzel_bold = os.path.join(base_path, "assets", "fonts", "Cinzel-Bold.ttf")

        # Check if fonts exist
        if os.path.exists(cinzel_regular) and os.path.exists(cinzel_semibold) and os.path.exists(cinzel_bold):
            self.cinzel_regular_path = cinzel_regular
            self.cinzel_semibold_path = cinzel_semibold
            self.cinzel_bold_path = cinzel_bold
            self.fonts_loaded = True
            logger.info(f"Loaded Cinzel fonts (Regular, SemiBold, Bold) from {base_path}/assets/fonts/")
            return True
        else:
            logger.warning(f"Cinzel fonts not found at {base_path}/assets/fonts/")
            logger.warning("Will fallback to system font (Arial)")
            self.fonts_loaded = False
            return False

    def get_font(self, size, weight='regular'):
        """
        Get a font of the specified size and weight.
        Returns cached font if available, otherwise creates and caches it.

        Font Weight Mapping (user preference: bolder fonts):
        - 'regular' → Cinzel-SemiBold.ttf (body text, descriptions)
        - 'semibold' → Cinzel-Bold.ttf (headers, titles)

        Args:
            size: Font size in pixels (int)
            weight: Font weight - 'regular' or 'semibold' (str)

        Returns:
            pygame.Font: The requested font object
        """
        # Check cache first
        cache_key = (size, weight)
        if cache_key in self.font_cache:
            return self.font_cache[cache_key]

        # Create new font
        if self.fonts_loaded:
            # Use Cinzel fonts with shifted weights (user preference)
            if weight == 'semibold':
                font_path = self.cinzel_bold_path  # Bold for headers/titles
            else:  # 'regular' or any other value defaults to semibold
                font_path = self.cinzel_semibold_path  # SemiBold for body text

            try:
                font = pygame.font.Font(font_path, size)
            except Exception as e:
                logger.error(f"Error loading font size {size} weight {weight}: {e}")
                logger.warning("Falling back to system font")
                font = pygame.font.SysFont('arial', size, bold=(weight == 'semibold'))
        else:
            # Fallback to system font (Arial)
            font = pygame.font.SysFont('arial', size, bold=(weight == 'semibold'))

        # Cache and return
        self.font_cache[cache_key] = font
        return font

    def get_bold_font(self, size):
        """
        Convenience method to get Bold font (for headers/titles).

        Note: Returns Cinzel-Bold.ttf (shifted from original SemiBold mapping).

        Args:
            size: Font size in pixels (int)

        Returns:
            pygame.Font: Bold font of the requested size
        """
        return self.get_font(size, weight='semibold')

    def clear_cache(self):
        """
        Clear the font cache.
        Useful if fonts need to be reloaded or for memory management.
        """
        self.font_cache.clear()
        logger.debug("Font cache cleared")

    def get_cache_info(self):
        """
        Get information about the current font cache.

        Returns:
            dict: Cache statistics (number of cached fonts, sizes, weights)
        """
        sizes = set()
        weights = set()
        for size, weight in self.font_cache.keys():
            sizes.add(size)
            weights.add(weight)

        return {
            'num_fonts': len(self.font_cache),
            'sizes': sorted(sizes),
            'weights': sorted(weights),
            'fonts_loaded': self.fonts_loaded
        }
