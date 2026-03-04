# -*- coding: utf-8 -*-
# rendering/map_renderer.py
# Map rendering - REAL extraction (Phase 4, Phase 1)

"""
Map Renderer
============

This module handles map-related rendering with REAL extracted code.

The MapRenderer contains the actual rendering logic (not just coordination),
extracted from main.py to reduce clutter and improve organization.

Methods Extracted (1,532 lines):
- draw_territory_overlay() - Colored territory fills
- draw_territories() - Territory ownership visualization
- draw_plots() - Building circles and construction
- draw_movement_arrows() - Order visualization
- draw_battle_markers() - Combat indicators

Extracted from main.py during Phase 4, Phase 1 of refactoring.
"""

import pygame
import time
import math
from config.constants import *
import map_data
from utils.colors import brighten_color, lighten_color
from utils.logger import get_logger
from ui.effects.battleeffect import BattleHurricaneEffect
from ui.effects.castle_upgrade_effect import CastleUpgradeEffect
from ui.effects.alliance_marker_effect import AllianceMarkerEffect
from ui.effects.production_glow_effect import ProductionGlowEffect
from ui.effects.ability_burst_effect import AbilityBurstEffect
from ui.effects.ability_arc_effect import AbilityArcEffect
from ui.effects.ability_polygon_burst_effect import AbilityPolygonBurstEffect

logger = get_logger(__name__)


class MapRenderer:
    """
    Handles map rendering with extracted code.
    
    This class contains the actual rendering methods extracted from Game class.
    Methods access Game instance state as needed, but logic is isolated here.
    
    Pattern: Extracted Logic with Game Reference
    - Real extraction (not delegation)
    - Methods access self.game for state
    - Logic organized in dedicated module
    """
    
    def __init__(self, game_instance):
        """
        Initialize map renderer with game instance.

        Args:
            game_instance: Reference to Game instance for state access
        """
        self.game = game_instance
        # Dictionary to store active battle hurricane effects: {battle_index: BattleHurricaneEffect}
        self.battle_effects = {}
        # Dictionary to store active alliance marker effects: {territory: AllianceMarkerEffect}
        # Used in simultaneous mode when allied armies arrive at same territory
        self.alliance_effects = {}
        # List to store active castle upgrade effects
        self.castle_upgrade_effects = []
        # Dictionary to store active production glow effects: {(territory, plot_index): ProductionGlowEffect}
        # Tracks Barracks with units in training queue, and Keep/Castle with hero in training
        self.production_glow_effects = {}
        self._production_glow_version = -1  # FPS OPT: Track training version for dirty check
        # List to store active hero ability visual effects (burst + arc particles)
        self.ability_effects = []
        # Embargo persistent effects: {territory_name: AbilityPolygonBurstEffect}
        # Synced each frame with game_state.embargo_blocked_players
        self.embargo_effects = {}

        # Image caching system to avoid expensive transformations every frame
        # FPS OPT: Static glow circles replace old rotating ring system
        # Cache pre-rendered glow surfaces: key = (color, radius_rounded)
        self.static_glow_cache = {}
        # Cache scaled flag images: key = (player, tier, width, height)
        self.scaled_flag_cache = {}
        # Cache scaled building icons: key = (building_type, size)
        self.scaled_building_cache = {}
        # Cache scaled plot icons: key = (plot_icon_name, size)
        self.scaled_plot_cache = {}
        # Cache scaled unit training icons: key = (unit_type, size)
        self.scaled_unit_cache = {}
        # Cache scaled border icons: key = size
        self.scaled_border_cache = {}

        # Surface reuse pools to avoid creating thousands of surfaces per frame
        # H8 fix: Track overlay size so they can be rebuilt on window resize
        self._overlay_size = (WINDOW_WIDTH, WINDOW_HEIGHT)
        self.fullscreen_overlay = pygame.Surface(self._overlay_size, pygame.SRCALPHA)
        # FPS OPT Phase 1B: Dirty-flag cache for territory ownership overlay
        # Skip fill+draw+blit when camera and ownership haven't changed (static gameplay)
        self._overlay_cache_surface = None  # Cached rendered overlay
        self._overlay_cache_camera = None  # (offset_x, offset_y, zoom) when cached
        self._overlay_cache_version = -1  # game_state._territory_owners_version when cache was built
        # FPS OPT: Hover overlay uses small clipped surface, no longer full-screen
        # Cached between frames when same territory is hovered with same camera state
        self._hover_surface = None  # Small SRCALPHA surface for hover polygon
        self._hover_blit_pos = (0, 0)  # Screen position to blit hover surface
        self._last_hover_territory = None  # Track for cache invalidation
        self._last_hover_camera_state = None  # Track for cache invalidation
        # Pools of reusable surfaces by size for overlays, glows, and effects
        self.surface_pool = {}  # key = (width, height), value = list of surfaces
        self.max_pool_size = 50  # Limit pool size to prevent memory bloat

        # FPS OPT: Cache for cropped-to-circle training icons
        self._cropped_circle_cache = {}  # key = (unit_type, icon_size), value = surface

        # PERFORMANCE OPTIMIZATION: Font caching to avoid creating Font objects every frame
        # Creating pygame.font.Font() is expensive; cache by size for reuse
        self.font_cache = {}  # key = size, value = Font object

        # PERFORMANCE OPTIMIZATION: Territory polygon screen coordinate caching
        # Cache screen-space polygons, invalidate when camera moves/zooms
        # Problem: 39 territories × 30-80 vertices = 1500-3000 transformations/frame
        # Solution: Transform once, cache, reuse until camera changes
        self.cached_screen_polygons = {}  # key = territory, value = list of (x, y) screen coords
        self.last_camera_state = None  # (offset_x, offset_y, zoom)

        # PERFORMANCE OPTIMIZATION: Plot screen position caching
        # Cache screen-space plot positions (similar to polygon caching)
        # Problem: 39 territories × 4 plots × 4 render passes = 624 transformations/frame
        # Solution: Transform once, cache, reuse until camera changes
        self.cached_screen_plots = {}  # key = territory, value = list of (x, y) screen coords

        # Per-frame cached values (reset each frame)
        self.cached_mouse_world_pos = None

        # FPS OPTIMIZATION: Cache building types list (static after game init)
        # Avoids list() conversion every frame in quick-access icon rendering
        self._cached_building_list = None

        # FPS OPTIMIZATION: Pre-compute territory bounding boxes for fast culling
        # Old: is_territory_on_screen() iterated ALL vertices to find min/max every frame
        # New: O(1) lookup of pre-computed bounding boxes
        self.territory_bounding_boxes = {}  # {territory: (min_x, min_y, max_x, max_y)}
        self._precompute_territory_bounding_boxes()

        # FPS OPTIMIZATION 6.0: Multi-zoom polygon cache
        # Pre-compute scaled polygons at discrete zoom levels to eliminate per-frame transformations
        # Old: Transform ALL vertices every frame when camera moves (cache invalidated)
        # New: Pre-compute at 7 zoom levels, snap to nearest, apply cheap offset transformation
        self.ZOOM_LEVELS = [1.65, 2.0, 2.4, 2.8, 3.2, 3.6, 4.0]
        self.multi_zoom_cache = {}  # {(zoom_level, territory): [(x*zoom, y*zoom), ...]}
        self._precompute_multi_zoom_polygons()

        # FPS OPTIMIZATION 6.1: Pre-warm image transformation caches
        # Pre-populate ring, flag, and other image caches at common sizes during startup
        # Eliminates first-frame cache misses and ensures smooth gameplay from the start
        self._prewarm_image_caches()

        # FPS OPTIMIZATION 6.3: Pre-compute screen polygons for initial camera position
        # Ensures the first frame renders without any cache misses
        self._prewarm_screen_polygon_cache()

    def _precompute_territory_bounding_boxes(self):
        """
        FPS OPTIMIZATION: Pre-compute bounding boxes for all territories at startup.

        This enables O(1) culling checks instead of O(V) vertex iteration per territory per frame.
        Called once during __init__ after game instance is available.
        """
        for territory, polygon in self.game.scaled_polygons.items():
            if polygon:
                min_x = min(p[0] for p in polygon)
                max_x = max(p[0] for p in polygon)
                min_y = min(p[1] for p in polygon)
                max_y = max(p[1] for p in polygon)
                self.territory_bounding_boxes[territory] = (min_x, min_y, max_x, max_y)

    def _precompute_multi_zoom_polygons(self):
        """
        FPS OPTIMIZATION 6.0: Pre-compute scaled polygons at discrete zoom levels.

        This eliminates the need to transform ALL vertices every frame during zoom/pan.
        At runtime, we snap to the nearest zoom level and apply a cheap offset transformation.

        Pre-computation time: ~0.5-1s at startup (57 territories × 7 zooms × 50 vertices)
        FPS gain: +10-15 FPS during zooming (eliminates recalculation)
        """
        for zoom in self.ZOOM_LEVELS:
            for territory, world_polygon in self.game.scaled_polygons.items():
                if world_polygon:
                    # Pre-scale polygon coordinates at this zoom level
                    # Store as (x * zoom, y * zoom) - offset and panel_height applied at runtime
                    scaled_polygon = [
                        (point[0] * zoom, point[1] * zoom)
                        for point in world_polygon
                    ]
                    self.multi_zoom_cache[(zoom, territory)] = scaled_polygon

    def _get_nearest_zoom_level(self, zoom):
        """Get the nearest pre-computed zoom level."""
        return min(self.ZOOM_LEVELS, key=lambda z: abs(z - zoom))

    def _prewarm_image_caches(self):
        """
        FPS OPTIMIZATION 6.1: Pre-warm image transformation caches at startup.

        Pre-populates glow, font, and other image caches at common sizes
        to eliminate first-use cache misses.
        """
        # Pre-warm static glow cache for common sizes and player colors
        common_radii = [9, 12, 15, 18, 21, 24, 27, 30]
        if hasattr(self.game, 'game_state'):
            for i in range(4):
                try:
                    color = self.game.game_state.get_player_color(i)
                    for radius in common_radii:
                        self._get_static_glow(color, radius)
                except Exception:
                    pass

        # Pre-warm font cache for common sizes
        common_font_sizes = [12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32]
        for size in common_font_sizes:
            try:
                self.get_cached_font(size)
            except Exception:
                pass

    def _prewarm_screen_polygon_cache(self):
        """
        FPS OPTIMIZATION 6.3: Pre-compute screen polygons for the initial camera position.

        This ensures that the very first frame renders without any cache misses.
        Called once during __init__ after the multi-zoom cache is populated.
        """
        # Initialize the camera state tracking
        self.last_camera_state = (
            self.game.camera_offset[0],
            self.game.camera_offset[1],
            self.game.camera_zoom
        )

        # Pre-compute screen polygons for all territories at the current camera position
        for territory in self.game.scaled_polygons:
            # Skip disabled territories (campaign mission filtering)
            if not map_data.is_territory_enabled(territory):
                continue
            try:
                self.get_cached_screen_polygon(territory)
            except Exception:
                pass  # Ignore errors during pre-warming

    def get_reusable_surface(self, width, height):
        """
        Get a reusable surface from the pool or create a new one.
        Surface is returned cleared and ready to use.

        Args:
            width: Surface width
            height: Surface height

        Returns:
            A cleared pygame.Surface with SRCALPHA
        """
        size_key = (width, height)

        # Try to get from pool
        if size_key in self.surface_pool and self.surface_pool[size_key]:
            surface = self.surface_pool[size_key].pop()
        else:
            # Create new surface if pool is empty
            surface = pygame.Surface((width, height), pygame.SRCALPHA)

        # Clear the surface for reuse
        surface.fill((0, 0, 0, 0))
        # R1 fix: reset per-surface alpha to prevent set_alpha(180) leaking into pool
        surface.set_alpha(255)
        return surface

    def return_surface_to_pool(self, surface):
        """
        Return a surface to the pool for later reuse.

        Args:
            surface: Surface to return to pool
        """
        size_key = (surface.get_width(), surface.get_height())

        # Initialize pool for this size if needed
        if size_key not in self.surface_pool:
            self.surface_pool[size_key] = []

        # Only add to pool if under limit
        if len(self.surface_pool[size_key]) < self.max_pool_size:
            self.surface_pool[size_key].append(surface)

    def _build_glow_surface(self, color, radius):
        """
        Build a pre-rendered glow halo surface for army circles.

        Creates a small SRCALPHA surface with concentric translucent circles
        that produce a soft glow effect around the army circle.

        Args:
            color: RGB tuple of the player color
            radius: Circle radius in pixels

        Returns:
            SRCALPHA surface with glow rings pre-rendered
        """
        # Surface must fit the outer glow ring (radius + glow_margin on each side)
        glow_margin = max(4, radius // 3)
        surf_size = (radius + glow_margin) * 2
        surface = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        center = (surf_size // 2, surf_size // 2)

        # Outer soft glow — large, very translucent
        pygame.draw.circle(surface, (*color, 35), center, radius + glow_margin)
        # Mid glow — slightly brighter
        pygame.draw.circle(surface, (*color, 55), center, radius + glow_margin // 2)

        return surface

    def _get_static_glow(self, color, radius):
        """
        Get cached glow surface for an army circle, building on miss.

        Rounds radius to nearest 3px for cache efficiency during zoom.

        Args:
            color: RGB tuple of the player color
            radius: Circle radius in pixels

        Returns:
            Cached SRCALPHA glow surface
        """
        radius_rounded = int(round(radius / 3.0) * 3)
        radius_rounded = max(3, radius_rounded)
        cache_key = (color, radius_rounded)

        if cache_key not in self.static_glow_cache:
            self.static_glow_cache[cache_key] = self._build_glow_surface(color, radius_rounded)

        return self.static_glow_cache[cache_key]

    def _draw_army_circle(self, screen, x, y, color, radius, is_hovering=False, is_clicking=False):
        """
        Draw a transparent army circle with glowing dark border at the given position.

        Visual design:
        1. Cached glow halo (soft translucent outer rings in player color)
        2. Dark border ring (darker player color, no fill — transparent inside)
        Circle is 25% smaller than the radius and shifted up slightly so the
        flag pole sits naturally inside the ring.

        Args:
            screen: Pygame surface to draw on
            x, y: Screen position (base center for the flag)
            color: RGB tuple of the player color
            radius: Base radius in pixels (will be reduced 25%)
            is_hovering: Whether mouse is hovering over this circle
            is_clicking: Whether this circle is being clicked/selected
        """
        # 25% smaller circle, shifted up so flag sits inside it
        draw_radius = int(radius * 0.75)
        draw_y = y - int(radius * 0.35)

        # Blit pre-cached glow halo centered at draw position
        glow = self._get_static_glow(color, draw_radius)
        glow_rect = glow.get_rect(center=(x, draw_y))
        screen.blit(glow, glow_rect)

        # Border color = darker version of player color (55%)
        dark_color = (int(color[0] * 0.55), int(color[1] * 0.55), int(color[2] * 0.55))

        # Adjust for hover/click brightness
        if is_clicking:
            dark_color = brighten_color(dark_color, 0.4)
        elif is_hovering:
            dark_color = brighten_color(dark_color, 0.2)

        # Transparent inside — only draw the border ring (no fill)
        border_width = max(2, draw_radius // 5)
        pygame.draw.circle(screen, dark_color, (x, draw_y), draw_radius, border_width)

    def get_cached_font(self, size):
        """
        Get or create a cached font at given size.
        PERFORMANCE OPTIMIZATION: Avoid creating Font objects every frame.

        Args:
            size: Font size in pixels

        Returns:
            pygame.font.Font object at specified size
        """
        if size not in self.font_cache:
            self.font_cache[size] = pygame.font.Font(None, size)
        return self.font_cache[size]

    def get_cached_building_list(self):
        """
        FPS OPTIMIZATION: Get cached list of building type keys.

        Avoids list() conversion every frame in quick-access icon rendering.
        Building types are static after game initialization.

        Returns:
            List of building type names
        """
        if self._cached_building_list is None:
            self._cached_building_list = list(self.game.game_state.building_types.keys())
        return self._cached_building_list

    def get_cached_scaled_flag(self, player, tier, flag_icon, width, height):
        """
        Get a scaled flag from cache or create and cache it.

        PERFORMANCE OPTIMIZATION: Round dimensions to reduce cache churn during zoom
        Old: Exact width/height creates new cache entry on every zoom change (1px difference)
        New: Round to nearest 5 pixels - reduces cache entries by 80% while maintaining visual quality

        Args:
            player: Player ID
            tier: Flag tier
            flag_icon: The flag icon to scale
            width: Target width
            height: Target height

        Returns:
            Scaled flag surface
        """
        # Round dimensions to nearest 5 pixels to improve cache hit rate during zoom
        rounded_width = int(round(width / 5.0) * 5)
        rounded_height = int(round(height / 5.0) * 5)
        cache_key = (player, tier, rounded_width, rounded_height)

        if cache_key in self.scaled_flag_cache:
            return self.scaled_flag_cache[cache_key]

        # Scale to rounded dimensions (visually indistinguishable from exact size)
        scaled_flag = pygame.transform.smoothscale(flag_icon, (rounded_width, rounded_height))
        self.scaled_flag_cache[cache_key] = scaled_flag
        return scaled_flag

    def get_cached_scaled_building(self, building_type, building_icon, size):
        """
        Get a scaled building icon from cache or create and cache it.

        Args:
            building_type: Type of building (e.g., 'castle', 'farm')
            building_icon: The building icon to scale
            size: Target size (width and height)

        Returns:
            Scaled building surface
        """
        cache_key = (building_type, size)

        if cache_key in self.scaled_building_cache:
            return self.scaled_building_cache[cache_key]

        scaled_icon = pygame.transform.smoothscale(building_icon, (size, size))
        self.scaled_building_cache[cache_key] = scaled_icon
        return scaled_icon

    def get_cached_scaled_plot(self, plot_icon_name, plot_icon, size):
        """
        Get a scaled plot icon from cache or create and cache it.

        Args:
            plot_icon_name: Name of the plot icon
            plot_icon: The plot icon to scale
            size: Target size (width and height)

        Returns:
            Scaled plot surface
        """
        cache_key = (plot_icon_name, size)

        if cache_key in self.scaled_plot_cache:
            return self.scaled_plot_cache[cache_key]

        scaled_icon = pygame.transform.smoothscale(plot_icon, (size, size))
        self.scaled_plot_cache[cache_key] = scaled_icon
        return scaled_icon

    def get_cached_scaled_unit(self, unit_type, unit_icon, size):
        """
        Get a scaled unit training icon from cache or create and cache it.

        Args:
            unit_type: Type of unit being trained
            unit_icon: The unit icon to scale
            size: Target size (width and height)

        Returns:
            Scaled unit surface
        """
        cache_key = (unit_type, size)

        if cache_key in self.scaled_unit_cache:
            return self.scaled_unit_cache[cache_key]

        scaled_icon = pygame.transform.smoothscale(unit_icon, (size, size))
        self.scaled_unit_cache[cache_key] = scaled_icon
        return scaled_icon

    def get_cached_scaled_border(self, border_icon, size):
        """
        Get a scaled border icon from cache or create and cache it.

        Args:
            border_icon: The border icon to scale
            size: Target size (width and height)

        Returns:
            Scaled border surface
        """
        cache_key = size

        if cache_key in self.scaled_border_cache:
            return self.scaled_border_cache[cache_key]

        scaled_border = pygame.transform.smoothscale(border_icon, (size, size))
        self.scaled_border_cache[cache_key] = scaled_border
        return scaled_border

    def is_point_on_screen(self, world_x, world_y, margin=50):
        """
        Check if a world coordinate point is visible on screen with margin.

        Args:
            world_x: X coordinate in world space
            world_y: Y coordinate in world space
            margin: Extra margin in pixels (default 50 for safety)

        Returns:
            True if point is visible (or close to visible), False otherwise
        """
        # Convert world coords to screen coords
        screen_x, screen_y = self.game.world_to_screen((world_x, world_y))

        # H9 fix: use actual screen dimensions instead of hardcoded constants
        screen_w = self.game.screen.get_width()
        screen_h = self.game.screen.get_height()
        return (-margin <= screen_x <= screen_w + margin and
                -margin <= screen_y <= screen_h + margin)

    def is_territory_on_screen(self, territory):
        """
        Check if any part of a territory polygon is visible on screen.

        FPS OPTIMIZATION: Uses pre-computed bounding boxes for O(1) culling.
        Old: Iterate ALL vertices O(V) per territory per frame
        New: Single bounding box intersection test O(1)

        Args:
            territory: Territory name

        Returns:
            True if territory is at least partially visible, False otherwise
        """
        if territory not in self.territory_bounding_boxes:
            return False

        # Get pre-computed world-space bounding box
        min_x, min_y, max_x, max_y = self.territory_bounding_boxes[territory]

        # Transform bounding box corners to screen space
        screen_min = self.game.world_to_screen((min_x, min_y))
        screen_max = self.game.world_to_screen((max_x, max_y))

        # H9 fix: use actual screen dimensions instead of hardcoded constants
        margin = 100
        screen_w = self.game.screen.get_width()
        screen_h = self.game.screen.get_height()
        screen_left = -margin
        screen_right = screen_w + margin
        screen_top = -margin
        screen_bottom = screen_h + margin

        # Bounding box intersection test
        # Territory is on screen if its bbox overlaps with screen rect
        bbox_left = min(screen_min[0], screen_max[0])
        bbox_right = max(screen_min[0], screen_max[0])
        bbox_top = min(screen_min[1], screen_max[1])
        bbox_bottom = max(screen_min[1], screen_max[1])

        return not (bbox_right < screen_left or bbox_left > screen_right or
                    bbox_bottom < screen_top or bbox_top > screen_bottom)

    def get_cached_screen_polygon(self, territory):
        """
        Get cached screen-space polygon coordinates for a territory.

        FPS OPTIMIZATION 6.0: Uses multi-zoom pre-computed cache for massive speedup.
        Old: Call world_to_screen() for EVERY vertex when camera changes (expensive)
        New: Snap to nearest zoom level, apply cheap offset transformation (just arithmetic)

        Args:
            territory: Name of territory

        Returns:
            list: Screen-space polygon coordinates [(x, y), ...]
        """
        # Check if camera state changed (offset or zoom)
        current_camera_state = (
            self.game.camera_offset[0],
            self.game.camera_offset[1],
            self.game.camera_zoom
        )

        # Invalidate screen cache if camera moved/zoomed
        if current_camera_state != self.last_camera_state:
            self.cached_screen_polygons = {}
            self.cached_screen_plots = {}
            self.last_camera_state = current_camera_state

        # Return cached polygon if available (exact camera state match)
        if territory in self.cached_screen_polygons:
            return self.cached_screen_polygons[territory]

        # Cache miss - use multi-zoom cache with offset transformation
        # This is MUCH faster than calling world_to_screen() per vertex
        nearest_zoom = self._get_nearest_zoom_level(self.game.camera_zoom)
        cache_key = (nearest_zoom, territory)

        if cache_key not in self.multi_zoom_cache:
            # Fallback to old method if not in multi-zoom cache
            if territory not in self.game.scaled_polygons:
                return []
            world_polygon = self.game.scaled_polygons[territory]
            screen_polygon = [self.game.world_to_screen(point) for point in world_polygon]
            self.cached_screen_polygons[territory] = screen_polygon
            return screen_polygon

        # Get pre-computed polygon at nearest zoom level
        precomputed_polygon = self.multi_zoom_cache[cache_key]

        # Apply offset transformation (cheap - just arithmetic)
        # Pre-computed: (x * nearest_zoom, y * nearest_zoom)
        # Need: ((x - offset_x) * actual_zoom, (y - offset_y) * actual_zoom + panel_height)
        # Transform: scale by zoom_ratio, subtract offset * actual_zoom, add panel_height
        offset_x = self.game.camera_offset[0]
        offset_y = self.game.camera_offset[1]
        actual_zoom = self.game.camera_zoom
        zoom_ratio = actual_zoom / nearest_zoom
        panel_height = self.game.TOP_PANEL_HEIGHT if hasattr(self.game, 'TOP_PANEL_HEIGHT') else 50

        # Apply offset and zoom correction
        # screen_x = pre_x * zoom_ratio - offset_x * actual_zoom
        # screen_y = pre_y * zoom_ratio - offset_y * actual_zoom + panel_height
        offset_x_scaled = offset_x * actual_zoom
        offset_y_scaled = offset_y * actual_zoom

        screen_polygon = [
            (
                pre_x * zoom_ratio - offset_x_scaled,
                pre_y * zoom_ratio - offset_y_scaled + panel_height
            )
            for pre_x, pre_y in precomputed_polygon
        ]

        # Cache the result for this exact camera state
        self.cached_screen_polygons[territory] = screen_polygon

        return screen_polygon

    def get_cached_screen_plots(self, territory):
        """
        Get cached screen-space plot positions for a territory.

        PERFORMANCE OPTIMIZATION: Similar to polygon caching, transforms plot positions
        once when camera changes, then reuses until next camera move/zoom.

        Old: 156 plots × 4 render passes × world_to_screen() = 624 calls/frame
        New: Transform once per camera change, O(1) cache lookup

        Args:
            territory: Name of territory

        Returns:
            list: Screen-space plot coordinates [(x, y), ...]
        """
        # Cache already invalidated by get_cached_screen_polygon if camera changed

        # Return cached plots if available
        if territory in self.cached_screen_plots:
            return self.cached_screen_plots[territory]

        # Cache miss - transform and cache
        if territory not in self.game.scaled_plots:
            return []

        world_plots = self.game.scaled_plots[territory]
        screen_plots = [self.game.world_to_screen(pos) for pos in world_plots]
        self.cached_screen_plots[territory] = screen_plots

        return screen_plots

    def draw_territory_overlay(self, territory, color, alpha=100, outline=False):
        """
        Draw a colored overlay on a territory (Phase 2D: camera-aware).

        FPS OPT: Uses small clipped SRCALPHA surface sized to polygon bbox
        instead of full-screen 5.44MB surface. Typical surface ~200x150 pixels.

        Args:
            territory: Name of territory to draw overlay on
            color: RGB tuple (r, g, b)
            alpha: Transparency (0-255)
            outline: Whether to draw border
        """
        screen_polygon = self.get_cached_screen_polygon(territory)
        if not screen_polygon:
            return

        # FPS OPT: Compute screen-space bbox for small clipped surface
        border_width = max(1, int(1.5 * self.game.camera_zoom)) if outline else 0
        margin = border_width + 2
        xs = [p[0] for p in screen_polygon]
        ys = [p[1] for p in screen_polygon]
        bbox_x = max(0, int(min(xs) - margin))
        bbox_y = max(0, int(min(ys) - margin))
        bbox_w = max(1, int(max(xs) - min(xs) + margin * 2))
        bbox_h = max(1, int(max(ys) - min(ys) + margin * 2))

        # Small SRCALPHA surface (supports mixed alphas for fill + outline)
        overlay = pygame.Surface((bbox_w, bbox_h), pygame.SRCALPHA)
        local_polygon = [(p[0] - bbox_x, p[1] - bbox_y) for p in screen_polygon]

        pygame.draw.polygon(overlay, (*color, alpha), local_polygon)
        if outline:
            pygame.draw.lines(overlay, (*color, 255), True, local_polygon, border_width)

        self.game.screen.blit(overlay, (bbox_x, bbox_y))
    def draw_territories(self):
        """Draw territory overlays, markers and ownership colors"""
        # H8 fix: Rebuild overlay surfaces if window was resized
        current_size = (self.game.screen.get_width(), self.game.screen.get_height())
        if current_size != self._overlay_size:
            self._overlay_size = current_size
            self.fullscreen_overlay = pygame.Surface(current_size, pygame.SRCALPHA)
            # Invalidate caches on resize
            self._overlay_cache_surface = None
            self._hover_surface = None
            self._last_hover_territory = None

        # PHASE 1 OPTIMIZATION: Pre-compute values used multiple times per frame
        # Cache mouse position in world coordinates (used for all hover checks)
        mouse_screen_x, mouse_screen_y = self.game.mouse_pos
        self.cached_mouse_world_pos = self.game.screen_to_world((mouse_screen_x, mouse_screen_y))

        # FPS OPT Phase 1B: Dirty-flag cache for territory ownership overlay
        # Skip fill+draw+blit when camera and ownership haven't changed (saves ~5ms during static view)
        current_camera = (self.game.camera_offset[0], self.game.camera_offset[1], self.game.camera_zoom)
        owners_version = self.game.game_state._territory_owners_version
        cache_valid = (
            self._overlay_cache_surface is not None and
            self._overlay_cache_camera == current_camera and
            self._overlay_cache_version == owners_version
        )

        if not cache_valid:
            # Cache miss — rebuild territory ownership overlay
            self.fullscreen_overlay.fill((0, 0, 0, 0))  # Clear once

            for territory in self.game.scaled_polygons.keys():
                # Skip disabled territories (campaign mission filtering)
                if not map_data.is_territory_enabled(territory):
                    continue
                # PERFORMANCE: Skip off-screen territories
                if not self.is_territory_on_screen(territory):
                    continue

                owner = self.game.game_state.territory_owners.get(territory, -1)
                if owner >= 0:
                    color = self.game.game_state.get_player_color(owner)

                    # Check if this is a starting territory (capital) - darken the color
                    is_starting_territory = (
                        hasattr(self.game.game_state, 'player_starting_territories') and
                        territory == self.game.game_state.player_starting_territories.get(owner)
                    )

                    if is_starting_territory:
                        color = (
                            int(color[0] * 0.7),
                            int(color[1] * 0.7),
                            int(color[2] * 0.7)
                        )

                    screen_polygon = self.get_cached_screen_polygon(territory)
                    if screen_polygon:
                        pygame.draw.polygon(self.fullscreen_overlay, (*color, 80), screen_polygon)

            # Store cache state
            self._overlay_cache_surface = self.fullscreen_overlay.copy()
            self._overlay_cache_camera = current_camera
            self._overlay_cache_version = owners_version
            self.game.screen.blit(self.fullscreen_overlay, (0, 0))
        else:
            # Cache hit — just blit the cached surface (skip fill+draw entirely)
            self.game.screen.blit(self._overlay_cache_surface, (0, 0))
        
        # Second pass: Draw hover highlight (semi-transparent owner color)
        # FPS OPT: Use small clipped SRCALPHA surface sized to polygon bbox (~200x150)
        # instead of full-screen 5.44MB surface. Cached when same territory + camera state.
        hovered = self.game.hovered_territory
        if hovered and hovered in self.game.scaled_polygons:
            screen_polygon = self.get_cached_screen_polygon(hovered)

            if screen_polygon:
                # Check if hover cache is valid (same territory + camera state)
                current_camera = (self.game.camera_offset[0], self.game.camera_offset[1], self.game.camera_zoom)
                if (hovered != self._last_hover_territory or
                        current_camera != self._last_hover_camera_state):
                    # Cache miss — rebuild small hover surface
                    self._last_hover_territory = hovered
                    self._last_hover_camera_state = current_camera

                    # Compute screen-space bounding box of polygon with margin for border
                    hover_border_width = max(1, int(1.5 * self.game.camera_zoom))
                    margin = hover_border_width + 2
                    xs = [p[0] for p in screen_polygon]
                    ys = [p[1] for p in screen_polygon]
                    bbox_x = min(xs) - margin
                    bbox_y = min(ys) - margin
                    bbox_w = max(xs) - min(xs) + margin * 2
                    bbox_h = max(ys) - min(ys) + margin * 2

                    # Clamp to screen bounds to avoid negative-size surfaces
                    bbox_x = max(0, int(bbox_x))
                    bbox_y = max(0, int(bbox_y))
                    bbox_w = max(1, int(bbox_w))
                    bbox_h = max(1, int(bbox_h))

                    # Create small SRCALPHA surface (needs two alphas: fill=60, border=255)
                    self._hover_surface = pygame.Surface((bbox_w, bbox_h), pygame.SRCALPHA)
                    self._hover_blit_pos = (bbox_x, bbox_y)

                    # Offset polygon to local surface coordinates
                    local_polygon = [(p[0] - bbox_x, p[1] - bbox_y) for p in screen_polygon]

                    hover_owner = self.game.game_state.territory_owners.get(hovered, -1)
                    if hover_owner >= 0:
                        hover_color = self.game.game_state.get_player_color(hover_owner)
                        pygame.draw.polygon(self._hover_surface, (*hover_color, 60), local_polygon)
                        pygame.draw.lines(self._hover_surface, (*hover_color, 255), True, local_polygon, hover_border_width)
                    else:
                        pygame.draw.polygon(self._hover_surface, (200, 200, 200, 60), local_polygon)
                        pygame.draw.lines(self._hover_surface, (200, 200, 200, 255), True, local_polygon, hover_border_width)

                # Blit cached hover surface (tiny surface, fast blit)
                if self._hover_surface is not None:
                    self.game.screen.blit(self._hover_surface, self._hover_blit_pos)
        else:
            # No territory hovered — invalidate cache
            if self._last_hover_territory is not None:
                self._last_hover_territory = None
                self._hover_surface = None
        
        # Third pass: Draw selected territory highlight (prominent border)
        # Border width scales with zoom for visibility when zoomed in
        selected_border_width = max(1, int(1.5 * self.game.camera_zoom))
        if self.game.selected_territory_info and self.game.selected_territory_info in self.game.scaled_polygons:
            selected_owner = self.game.game_state.territory_owners.get(self.game.selected_territory_info, -1)
            # FPS OPTIMIZATION: Use cached screen polygon instead of transforming every frame
            # Old: Transform 30-80 vertices per frame
            # New: O(1) cache lookup
            screen_polygon = self.get_cached_screen_polygon(self.game.selected_territory_info)
            if screen_polygon:
                if selected_owner >= 0:
                    # Owned territory - use owner's color with thick border
                    selected_color = self.game.game_state.get_player_color(selected_owner)
                    pygame.draw.lines(self.game.screen, selected_color, True, screen_polygon, selected_border_width)
                else:
                    # Neutral territory - use white border
                    pygame.draw.lines(self.game.screen, WHITE, True, screen_polygon, selected_border_width)
        
        # Fourth pass: Draw old selected_territory highlight (for movement)
        if self.game.game_state.selected_territory and self.game.game_state.selected_territory in self.game.scaled_polygons:
            self.draw_territory_overlay(self.game.game_state.selected_territory, (255, 255, 0), alpha=100, outline=True)

        # Tutorial highlight: bright pulsing overlay on target territory
        if (hasattr(self.game, 'tutorial_mission') and self.game.tutorial_mission
                and self.game.tutorial_mission.active):
            hl_territory = self.game.tutorial_mission.get_highlight_territory()
            if hl_territory and hl_territory in self.game.scaled_polygons:
                # Pulsing green highlight using sine wave
                pulse = 0.5 + 0.5 * math.sin(time.time() * 3.0)
                alpha = int(40 + 60 * pulse)  # 40-100 alpha range
                self.draw_territory_overlay(hl_territory, (100, 255, 100), alpha=alpha, outline=True)

        # Fifth pass: Draw building plots and their icons FIRST
        # Plots drawn before armies so army flags appear on top!
        # Draw production glow effects BEFORE plots (so glow appears behind building icons)
        self.render_production_glow_effects()
        self.draw_plots()

        # Sixth pass: Draw center markers and army counts (with flag icons)
        # NOTE: Armies drawn AFTER plots so flags appear on top!

        # PERFORMANCE OPTIMIZATION: Pre-compute incoming animations index once per frame
        # Old: O(T·A) = 39 territories × 100 animations = 3,900 comparisons
        # New: O(A) = 100 animations processed once = 100 operations (97.4% reduction)
        incoming_animations_by_territory = {}
        for anim in self.game.game_state.active_animations:
            if anim.to_territory not in incoming_animations_by_territory:
                incoming_animations_by_territory[anim.to_territory] = set()
            incoming_animations_by_territory[anim.to_territory].add(anim.player)

        # PERFORMANCE OPTIMIZATION: Pre-index movement orders by destination territory
        # Old: O(V×M) = 39 territories × 100 orders = 3,900 comparisons per frame
        # New: O(M) = 100 orders processed once = O(1) lookup per territory (97.4% reduction)
        movement_destinations = {}
        for order in self.game.game_state.movement_orders:
            if order.to_territory not in movement_destinations:
                movement_destinations[order.to_territory] = []
            movement_destinations[order.to_territory].append(order)

        # PERFORMANCE OPTIMIZATION: Cache ui_scale per frame (called 3+ times per territory)
        # Old: 39 territories × 3 calls = 117 redundant calculations
        # New: 1 calculation per frame (99% reduction)
        ui_scale = self.game.get_ui_scale_factor()

        for territory, world_center in self.game.scaled_centers.items():
            if territory not in self.game.game_state.territory_owners:
                continue

            # PERFORMANCE: Skip off-screen armies
            if not self.is_point_on_screen(world_center[0], world_center[1], margin=150):
                continue

            # Transform center from world to screen coordinates (Phase 2D!)
            x, y = self.game.world_to_screen(world_center)

            owner = self.game.game_state.territory_owners[territory]

            # Check if territory has multiple garrisons (allied reinforcement)
            garrisons = self.game.game_state.territory_garrisons.get(territory, {})

            # PERFORMANCE OPTIMIZATION: Pre-compute garrison army counts once to avoid repeated dict.get() calls
            # Old: garrison.get('unmoved', 0) + garrison.get('moved', 0) calculated 3-5 times per garrison
            # New: Calculate once, reuse throughout (saves ~200 dict operations per frame)
            garrison_army_counts = {}
            total_armies = 0
            for player_index, garrison in garrisons.items():
                count = garrison.get('unmoved', 0) + garrison.get('moved', 0)
                garrison_army_counts[player_index] = count
                total_armies += count

            # Count only non-empty garrisons for positioning
            num_garrisons = sum(1 for count in garrison_army_counts.values() if count > 0)

            # IMPORTANT: Check if there are incoming animations to this territory (O(1) lookup now)
            # If so, use the FUTURE garrison count (after arrivals) for flag positioning
            # This prevents flags from "jumping" when animations complete
            incoming_players = incoming_animations_by_territory.get(territory, set())

            if incoming_players:
                # Calculate future garrison count (current + incoming)
                future_garrisons = set()
                for player_index, count in garrison_army_counts.items():
                    if count > 0:
                        future_garrisons.add(player_index)
                future_garrisons.update(incoming_players)
                num_garrisons = len(future_garrisons)

                # IMPORTANT: For allied territories with incoming reinforcements,
                # use at least 2 positions even if only 1 garrison will exist
                # (to match animation destination positioning)
                if owner >= 0 and num_garrisons == 1:
                    # Check if the single garrison is not the owner
                    single_garrison_player = list(future_garrisons)[0]
                    if single_garrison_player != owner:
                        num_garrisons = 2  # Use 2-position layout for allied reinforcement

            # Skip drawing army indicator if territory has 0 armies
            if total_armies == 0:
                continue

            # PERFORMANCE OPTIMIZATION: Pre-compute flag positions ONCE if multi-garrison
            # Old: get_flag_positions_for_territory() called 2+ times per territory (lines 601, 764)
            # New: Calculate once, reuse (eliminates 40-60 math calls per frame)
            flag_positions = None
            if num_garrisons > 1:
                flag_positions = self.game.game_state.get_flag_positions_for_territory(
                    territory, world_center[0], world_center[1], num_garrisons
                )

            # Draw circle for territory center
            if owner >= 0:
                color = self.game.game_state.get_player_color(owner)
            else:
                color = (150, 150, 150)  # Neutral

            # Draw selection glow if this army is selected OR composition UI is open for it
            is_selected = False
            selected_player = None
            if self.game.game_state.selected_army and self.game.game_state.selected_army[0] == territory:
                is_selected = True
                selected_player = self.game.game_state.current_player
            elif self.game.show_army_composition and self.game.army_composition_territory == territory:
                is_selected = True
                selected_player = self.game.army_composition_player if self.game.army_composition_player is not None else self.game.game_state.current_player

            if is_selected:
                # Determine glow position (use flag position for multi-garrison)
                glow_x, glow_y = x, y  # Default to territory center
                if flag_positions and selected_player is not None:
                    # Multi-garrison: draw glow at selected player's flag position (reuse cached positions)
                    garrison_position_idx = self.game.game_state.assign_garrison_position(territory, selected_player, num_garrisons)
                    if garrison_position_idx < len(flag_positions):
                        flag_world_x, flag_world_y = flag_positions[garrison_position_idx]
                        glow_x, glow_y = self.game.world_to_screen((flag_world_x, flag_world_y))

                # Align glow with the army circle (25% smaller, shifted up)
                circle_radius = int(ARMY_CIRCLE_RADIUS * ui_scale * 0.75)
                circle_y_offset = int(ARMY_CIRCLE_RADIUS * ui_scale * 0.35)
                glow_y = glow_y - circle_y_offset

                # Pulsing green glow effect (scales with zoom!)
                pulse = abs(math.sin(time.time() * 2))  # Pulse between 0 and 1
                glow_alpha = int(100 + 100 * pulse)  # Between 100 and 200

                # PERFORMANCE OPTIMIZATION: Reduce glow layers when zoomed out
                glow_layers = 1 if ui_scale < 1.5 else 3

                # Draw glow circles sized to match the smaller army circle
                for i in range(glow_layers):
                    glow_radius = circle_radius + int((3 + i * 3) * ui_scale)
                    # PERFORMANCE: Use reusable surface from pool
                    glow_surface = self.get_reusable_surface(glow_radius * 2 + 10, glow_radius * 2 + 10)
                    pygame.draw.circle(glow_surface, (0, 255, 0, glow_alpha // (i + 1)),
                                     (glow_radius + 5, glow_radius + 5), glow_radius, 3)
                    self.game.screen.blit(glow_surface, (int(glow_x) - glow_radius - 5, int(glow_y) - glow_radius - 5))
                    self.return_surface_to_pool(glow_surface)
            
            # Draw merge/attack destination highlight
            # Check if this territory is receiving an order from selected army OR composition UI
            selected_territory = None
            if self.game.game_state.selected_army:
                selected_territory = self.game.game_state.selected_army[0]
            elif self.game.show_army_composition and self.game.army_composition_territory:
                selected_territory = self.game.army_composition_territory

            if selected_territory:
                # PERFORMANCE: Use pre-indexed movement orders (O(1) lookup instead of O(M) iteration)
                orders_to_here = movement_destinations.get(territory, [])
                for order in orders_to_here:
                    if order.from_territory == selected_territory:
                        # Check if destination is friendly or enemy
                        dest_owner = self.game.game_state.territory_owners.get(territory, -1)

                        # Check if destination is friendly (owned by player OR ally)
                        is_friendly = (dest_owner == order.player or
                                     (dest_owner >= 0 and self.game.game_state.are_allies(order.player, dest_owner)))

                        if is_friendly:
                            # This is a MERGE/REINFORCEMENT destination - draw cyan highlight
                            pulse = abs(math.sin(time.time() * 3))  # Slightly faster pulse
                            glow_alpha = int(120 + 80 * pulse)  # Between 120 and 200

                            # PERFORMANCE: Reduce glow layers when zoomed out (same as selection glow)
                            glow_layers = 1 if ui_scale < 1.5 else 3  # FPS OPTIMIZATION: More aggressive threshold

                            # Draw cyan glow rings (M6 fix: scale with zoom like red glow)
                            for i in range(glow_layers):
                                glow_radius = int((20 + i * 4) * ui_scale)
                                # PERFORMANCE: Use reusable surface from pool
                                glow_surface = self.get_reusable_surface(glow_radius * 2 + 10, glow_radius * 2 + 10)
                                pygame.draw.circle(glow_surface, (0, 200, 200, glow_alpha // (i + 1)),
                                                 (glow_radius + 5, glow_radius + 5), glow_radius, 4)
                                self.game.screen.blit(glow_surface, (int(x) - glow_radius - 5, int(y) - glow_radius - 5))
                                self.return_surface_to_pool(glow_surface)
                        else:
                            # This is an ATTACK destination - draw red highlight
                            pulse = abs(math.sin(time.time() * 3))  # Slightly faster pulse
                            glow_alpha = int(120 + 80 * pulse)  # Between 120 and 200

                            # PERFORMANCE: Use cached ui_scale (pre-computed above)
                            # Removed redundant: ui_scale = self.game.get_ui_scale_factor()

                            # PERFORMANCE: Reduce glow layers when zoomed out (same as selection glow)
                            glow_layers = 1 if ui_scale < 1.5 else 3  # FPS OPTIMIZATION: More aggressive threshold

                            # Draw red glow rings (scaled with zoom)
                            for i in range(glow_layers):
                                glow_radius = int((20 + i * 4) * ui_scale)
                                # PERFORMANCE: Use reusable surface from pool
                                glow_surface = self.get_reusable_surface(glow_radius * 2 + 10, glow_radius * 2 + 10)
                                pygame.draw.circle(glow_surface, (200, 0, 0, glow_alpha // (i + 1)),
                                                 (glow_radius + 5, glow_radius + 5), glow_radius, 4)
                                self.game.screen.blit(glow_surface, (int(x) - glow_radius - 5, int(y) - glow_radius - 5))
                                self.return_surface_to_pool(glow_surface)
                        break

            # PERFORMANCE: Use cached ui_scale (pre-computed above)
            # Removed redundant: ui_scale = self.game.get_ui_scale_factor()

            # Apply zoom-based scaling to army circles
            scaled_army_radius = int(ARMY_CIRCLE_RADIUS * ui_scale)
            
            # Base color
            army_color = color
            
            # Check for hover (using screen position)
            # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
            is_hovering = False
            mouse_screen_x, mouse_screen_y = self.game.mouse_pos
            distance_sq = (x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2
            if distance_sq <= scaled_army_radius ** 2:
                is_hovering = True
            
            # Check for click flash
            is_clicking = (self.game.clicked_element and 
                          self.game.clicked_element[0] == 'army' and 
                          self.game.clicked_element[1] == territory)
            
            # Draw army circle (static circle + glow halo) for all players
            # CRITICAL: Only draw main circle for single-garrison territories
            # For multi-garrison, each garrison gets its own circle at flag position
            if num_garrisons <= 1:
                # FPS OPT: Static circle replaces old rotating ring — shown for ALL players
                # _draw_army_circle handles hover/click brightness internally
                self._draw_army_circle(self.game.screen, int(x), int(y),
                                       army_color, scaled_army_radius,
                                       is_hovering, is_clicking)

            # Draw army flag icon(s) for garrison(s)
            if num_garrisons > 1:
                # MULTI-GARRISON: Draw separate flags AND rings for each garrison
                # Flag positions were already computed above (cached) - reuse them

                # Assign positions to existing garrisons (preserves positions during animations)
                for player_index in sorted(garrisons.keys()):
                    # PERFORMANCE: Use cached garrison_army_counts instead of recalculating
                    garrison_armies = garrison_army_counts.get(player_index, 0)
                    if garrison_armies > 0:
                        self.game.game_state.assign_garrison_position(territory, player_index, num_garrisons)

                # Draw a ring and flag for each garrison
                for player_index in sorted(garrisons.keys()):
                    # PERFORMANCE: Use cached garrison_army_counts instead of recalculating
                    garrison_armies = garrison_army_counts.get(player_index, 0)

                    if garrison_armies == 0:
                        continue  # Skip empty garrisons

                    # Get assigned position index for this garrison
                    garrison_position_idx = self.game.game_state.assign_garrison_position(territory, player_index, num_garrisons)

                    # Get flag position for this garrison (world coords)
                    flag_world_x, flag_world_y = flag_positions[garrison_position_idx]
                    flag_screen_x, flag_screen_y = self.game.world_to_screen((flag_world_x, flag_world_y))

                    # Draw rotating ring for this garrison at flag position
                    garrison_color = self.game.game_state.get_player_color(player_index)

                    # Check for hover/click on this specific garrison
                    # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
                    garrison_is_hovering = False
                    distance_to_flag_sq = (flag_screen_x - mouse_screen_x) ** 2 + (flag_screen_y - mouse_screen_y) ** 2
                    if distance_to_flag_sq <= scaled_army_radius ** 2:
                        garrison_is_hovering = True

                    # Check if this garrison is selected (for army composition UI)
                    # Use army_composition_player to determine which garrison is selected, not current_player
                    is_garrison_selected = (self.game.show_army_composition and
                                           self.game.army_composition_territory == territory and
                                           self.game.army_composition_player == player_index)

                    garrison_is_clicking = (self.game.clicked_element and
                                           self.game.clicked_element[0] == 'army' and
                                           self.game.clicked_element[1] == territory and
                                           player_index == self.game.game_state.current_player) or is_garrison_selected

                    # FPS OPT: Static circle replaces old rotating ring — shown for ALL garrisons
                    # _draw_army_circle handles hover/click brightness internally
                    self._draw_army_circle(self.game.screen, int(flag_screen_x), int(flag_screen_y),
                                           garrison_color, scaled_army_radius,
                                           garrison_is_hovering, garrison_is_clicking)

                    # Determine flag tier based on this garrison's army count
                    flag_tier = self.game.get_army_flag_tier(garrison_armies)

                    # Get the appropriate flag icon for this player and tier
                    if player_index in self.game.army_flag_icons and flag_tier in self.game.army_flag_icons[player_index]:
                        flag_icon = self.game.army_flag_icons[player_index][flag_tier]

                        if flag_icon:
                            # Scale the flag - 33% larger than before (2.5 * 1.33 ≈ 3.3)
                            flag_height = int(scaled_army_radius * 3.3)
                            flag_width = int(flag_icon.get_width() * (flag_height / flag_icon.get_height()))

                            # Get cached scaled flag (PERFORMANCE: cached to avoid expensive scaling)
                            scaled_flag = self.get_cached_scaled_flag(player_index, flag_tier, flag_icon, flag_width, flag_height)

                            # Position flag with pole centered on garrison position, flag extends upward
                            flag_rect = scaled_flag.get_rect(center=(int(flag_screen_x), int(flag_screen_y)))
                            flag_rect.y -= flag_height // 2  # Shift up by half height
                            self.game.screen.blit(scaled_flag, flag_rect)

            else:
                # SINGLE GARRISON: Draw one flag at territory center
                # Find which player actually has the garrison (not necessarily the territory owner)
                garrison_player = None
                for player_index in garrisons.keys():
                    garrison = garrisons[player_index]
                    if garrison.get('unmoved', 0) + garrison.get('moved', 0) > 0:
                        garrison_player = player_index
                        break

                # If no garrison found, fall back to territory owner (shouldn't happen)
                if garrison_player is None:
                    garrison_player = owner

                # Determine which flag tier to use based on army count
                flag_tier = self.game.get_army_flag_tier(total_armies)

                # Get the appropriate flag icon for this player and tier
                if garrison_player in self.game.army_flag_icons and flag_tier in self.game.army_flag_icons[garrison_player]:
                    flag_icon = self.game.army_flag_icons[garrison_player][flag_tier]

                    if flag_icon:
                        # Scale the flag - 33% larger than before (2.5 * 1.33 ≈ 3.3)
                        flag_height = int(scaled_army_radius * 3.3)
                        flag_width = int(flag_icon.get_width() * (flag_height / flag_icon.get_height()))

                        # Get cached scaled flag (PERFORMANCE: cached to avoid expensive scaling)
                        scaled_flag = self.get_cached_scaled_flag(garrison_player, flag_tier, flag_icon, flag_width, flag_height)

                        # Position flag with pole centered on circle, flag extends upward
                        # Move flag up by half its height so the pole (bottom) is at circle center
                        flag_rect = scaled_flag.get_rect(center=(int(x), int(y)))
                        flag_rect.y -= flag_height // 2  # Shift up by half height
                        self.game.screen.blit(scaled_flag, flag_rect)
                    else:
                        # Fallback to number if flag icon failed to load
                        # For single garrison, just show total
                        army_text = self.game.font.render(str(total_armies), True, WHITE)
                        text_rect = army_text.get_rect(center=(int(x), int(y)))
                        self.game.screen.blit(army_text, text_rect)
                else:
                    # Fallback to number if no flag icon available
                    # For single garrison, just show total
                    army_text = self.game.font.render(str(total_armies), True, WHITE)
                    text_rect = army_text.get_rect(center=(int(x), int(y)))
                    self.game.screen.blit(army_text, text_rect)

        # Seventh pass: Draw animated moving armies (AFTER static armies!)
        # Animated armies also drawn last to appear on top of everything
        self.draw_animated_armies()

    def draw_animated_armies(self):
        """
        Draw animated army circles for armies in motion.

        This renders army circles moving from their source territory to their
        destination territory over the duration of the animation.

        Features:
        - Groups multiple orders on the same route and shows combined count
        - Adds subtle wiggle effect to the path for visual interest
        """

        # Group animations by route (from_territory, to_territory, player)
        # This combines multiple orders on the same path
        route_groups = {}
        for anim in self.game.game_state.active_animations:
            route_key = (anim.from_territory, anim.to_territory, anim.player)
            if route_key not in route_groups:
                route_groups[route_key] = {
                    'animations': [],
                    'total_count': 0,
                    'progress': anim.progress  # Use first animation's progress
                }
            route_groups[route_key]['animations'].append(anim)
            route_groups[route_key]['total_count'] += anim.army_count

        # Draw one circle per route with combined count
        for route_key, group_data in route_groups.items():
            from_territory, to_territory, player = route_key

            # Get source and destination positions (in world coordinates)
            # Prefer animation-specific positions (for multi-garrison) over territory centers
            first_anim = group_data['animations'][0]
            if first_anim.from_pos is not None and first_anim.to_pos is not None:
                # Use pre-calculated flag positions
                from_pos = first_anim.from_pos
                to_pos = first_anim.to_pos
            else:
                # Fallback to territory centers
                from_pos = self.game.scaled_centers.get(from_territory)
                to_pos = self.game.scaled_centers.get(to_territory)

            if not from_pos or not to_pos:
                continue

            progress = group_data['progress']

            # Captain 2-hop movement: bent path through intermediate territory
            # If intermediate_territory is set, animate source→intermediate→destination
            intermediate_pos = None
            if first_anim.intermediate_territory:
                intermediate_pos = self.game.scaled_centers.get(first_anim.intermediate_territory)

            if intermediate_pos:
                # 2-segment path: progress 0.0→0.5 = source→intermediate, 0.5→1.0 = intermediate→destination
                if progress <= 0.5:
                    seg_progress = progress * 2.0  # 0.0 to 1.0 for first segment
                    seg_from = from_pos
                    seg_to = intermediate_pos
                else:
                    seg_progress = (progress - 0.5) * 2.0  # 0.0 to 1.0 for second segment
                    seg_from = intermediate_pos
                    seg_to = to_pos
                base_x = seg_from[0] + (seg_to[0] - seg_from[0]) * seg_progress
                base_y = seg_from[1] + (seg_to[1] - seg_from[1]) * seg_progress
                dx = seg_to[0] - seg_from[0]
                dy = seg_to[1] - seg_from[1]
            else:
                # Standard single-segment interpolation
                base_x = from_pos[0] + (to_pos[0] - from_pos[0]) * progress
                base_y = from_pos[1] + (to_pos[1] - from_pos[1]) * progress
                dx = to_pos[0] - from_pos[0]
                dy = to_pos[1] - from_pos[1]

            # Add wiggle effect - perpendicular to movement direction
            # Use sine wave for smooth oscillation
            wiggle_amount = 15  # Pixels of wiggle
            wiggle_frequency = 2  # Number of wiggles along the path

            # Calculate perpendicular direction
            length = math.sqrt(dx * dx + dy * dy)

            if length > 0:
                # Perpendicular vector (rotate 90 degrees)
                perp_x = -dy / length
                perp_y = dx / length

                # Apply wiggle based on progress
                wiggle_offset = math.sin(progress * math.pi * wiggle_frequency) * wiggle_amount
                current_x = base_x + perp_x * wiggle_offset
                current_y = base_y + perp_y * wiggle_offset
            else:
                current_x = base_x
                current_y = base_y

            # Convert to screen coordinates
            screen_pos = self.game.world_to_screen((current_x, current_y))
            screen_x, screen_y = screen_pos

            # Get player color
            player_color = self.game.game_state.get_player_color(player)

            # Apply zoom-based scaling to army circles
            ui_scale = self.game.get_ui_scale_factor()
            scaled_army_radius = int(ARMY_CIRCLE_RADIUS * ui_scale)

            # FPS OPT: Static circle replaces old rotating ring — shown for ALL moving armies
            self._draw_army_circle(self.game.screen, int(screen_x), int(screen_y),
                                   player_color, scaled_army_radius)

            # Draw combined army flag icon
            total_count = group_data['total_count']
            if total_count > 0:
                # Determine which flag tier to use based on army count
                flag_tier = self.game.get_army_flag_tier(total_count)

                # Get the appropriate flag icon for this player and tier
                if player in self.game.army_flag_icons and flag_tier in self.game.army_flag_icons[player]:
                    flag_icon = self.game.army_flag_icons[player][flag_tier]

                    if flag_icon:
                        # Scale the flag - 33% larger than before (2.5 * 1.33 ≈ 3.3)
                        flag_height = int(scaled_army_radius * 3.3)
                        flag_width = int(flag_icon.get_width() * (flag_height / flag_icon.get_height()))

                        # Get cached scaled flag (PERFORMANCE: cached to avoid expensive scaling)
                        scaled_flag = self.get_cached_scaled_flag(player, flag_tier, flag_icon, flag_width, flag_height)

                        # Position flag with pole centered on circle, flag extends upward
                        # Move flag up by half its height so the pole (bottom) is at circle center
                        flag_rect = scaled_flag.get_rect(center=(int(screen_x), int(screen_y)))
                        flag_rect.y -= flag_height // 2  # Shift up by half height
                        self.game.screen.blit(scaled_flag, flag_rect)
                    else:
                        # Fallback to number if flag icon failed to load
                        # Phase 6: Army counts use Cinzel Regular font (already cached in main.py)
                        army_text = self.game.font.render(str(total_count), True, WHITE)
                        text_rect = army_text.get_rect(center=(int(screen_x), int(screen_y)))
                        self.game.screen.blit(army_text, text_rect)
                else:
                    # Fallback to number if no flag icon available
                    # Phase 6: Army counts use Cinzel Regular font (already cached in main.py)
                    army_text = self.game.font.render(str(total_count), True, WHITE)
                    text_rect = army_text.get_rect(center=(int(screen_x), int(screen_y)))
                    self.game.screen.blit(army_text, text_rect)

    def draw_plots(self):
        """
        Draw building plots and their icons.
        
        This is called by draw_territories() to render plots AFTER armies.
        """
        self.draw_plots_original()
    def draw_movement_arrows(self):
        """Draw arrows showing planned movement orders.

        In simultaneous mode:
        - Shows player's own queued orders
        - Also shows allied players' queued orders (in a different shade)
        - Does NOT show enemy orders
        """

        # Check if in simultaneous mode
        sim_state = getattr(self.game, 'sim_state', None)

        if sim_state is not None and sim_state.sim_phase == 'planning':
            # SIMULTANEOUS MODE: Draw from sim_state.player_orders
            self._draw_sim_movement_arrows(sim_state)
            return

        # SEQUENTIAL MODE: Original logic using movement_orders
        # Group orders by (from_territory, to_territory) to show total count
        # PERFORMANCE: Also pre-index first order per route to avoid nested loop later
        route_counts = {}  # (from, to) -> total_army_count
        route_first_order = {}  # (from, to) -> first order (for player info)

        for order in self.game.game_state.movement_orders:
            route = (order.from_territory, order.to_territory)
            if route not in route_counts:
                route_counts[route] = 0
                route_first_order[route] = order  # Store first order for this route
            route_counts[route] += order.army_count
        
        # Draw one arrow per unique route with total count
        for (from_territory, to_territory), total_count in route_counts.items():
            # Get territory centers in world coordinates (already scaled!)
            if from_territory not in self.game.scaled_centers or to_territory not in self.game.scaled_centers:
                continue

            # For multi-garrison territories, use the flag position of the player making the order
            # PERFORMANCE: Use pre-indexed order instead of nested loop search
            first_order = route_first_order.get((from_territory, to_territory))
            order_player = first_order.player if first_order else None

            # Get FROM position - use flag position for multi-garrison, center for single garrison
            from_cx, from_cy = self.game.scaled_centers[from_territory]
            garrisons_from = self.game.game_state.territory_garrisons.get(from_territory, {})
            # Count only non-empty garrisons for positioning
            num_garrisons_from = sum(1 for g in garrisons_from.values() if g.get('unmoved', 0) + g.get('moved', 0) > 0)

            if num_garrisons_from > 1 and order_player is not None:
                # Multi-garrison: Get flag position for the player making the order
                flag_positions = self.game.game_state.get_flag_positions_for_territory(
                    from_territory, from_cx, from_cy, num_garrisons_from
                )

                # Find the garrison index for this player
                garrison_index = 0
                for player_index in sorted(garrisons_from.keys()):
                    if player_index == order_player:
                        break
                    if garrisons_from[player_index].get('unmoved', 0) + garrisons_from[player_index].get('moved', 0) > 0:
                        garrison_index += 1

                if garrison_index < len(flag_positions):
                    from_world = flag_positions[garrison_index]
                else:
                    from_world = (from_cx, from_cy)
            else:
                # Single garrison: Use territory center
                from_world = (from_cx, from_cy)

            to_world = self.game.scaled_centers[to_territory]

            # Captain 2-hop: check if first order has intermediate_territory for bent arrow path
            intermediate_world = None
            if first_order and getattr(first_order, 'intermediate_territory', None):
                intermediate_world = self.game.scaled_centers.get(first_order.intermediate_territory)

            # Transform to screen coordinates (Phase 2D: camera transformation!)
            from_x, from_y = self.game.world_to_screen(from_world)
            to_x, to_y = self.game.world_to_screen(to_world)

            # Arrow color - green for movement orders
            arrow_color = COLOR_ARROW_MOVEMENT

            if intermediate_world:
                # Captain 2-hop: draw bent arrow from→intermediate→destination
                inter_x, inter_y = self.game.world_to_screen(intermediate_world)
                # Draw first segment (from → intermediate)
                pygame.draw.line(self.game.screen, arrow_color, (int(from_x), int(from_y)), (int(inter_x), int(inter_y)), ARROW_LINE_WIDTH)
                # Draw second segment (intermediate → destination) with arrowhead
                pygame.draw.line(self.game.screen, arrow_color, (int(inter_x), int(inter_y)), (int(to_x), int(to_y)), ARROW_LINE_WIDTH)
                # Use second segment direction for arrowhead
                dx = to_x - inter_x
                dy = to_y - inter_y
            else:
                # Standard single-segment arrow
                pygame.draw.line(self.game.screen, arrow_color, (int(from_x), int(from_y)), (int(to_x), int(to_y)), ARROW_LINE_WIDTH)
                dx = to_x - from_x
                dy = to_y - from_y

            # Calculate arrowhead
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
                pygame.draw.polygon(self.game.screen, arrow_color, [
                    (int(to_x), int(to_y)),
                    (int(left_x), int(left_y)),
                    (int(right_x), int(right_y))
                ])

                # Draw army count badge at midpoint (showing TOTAL count)
                if intermediate_world:
                    inter_x_s, inter_y_s = self.game.world_to_screen(intermediate_world)
                    mid_x = int((from_x + inter_x_s) / 2)  # Badge on first segment
                    mid_y = int((from_y + inter_y_s) / 2)
                else:
                    mid_x = int((from_x + to_x) / 2)
                    mid_y = int((from_y + to_y) / 2)

                # Draw badge using helper (Phase 1D)
                self.game.helpers.draw_circle_badge((mid_x, mid_y), total_count, border_color=arrow_color)

        # Draw cascade cancel animations (red shaking arrows that fade out)
        self._draw_cancelling_arrows()

    def _draw_cancelling_arrows(self):
        """Draw red shaking arrows for orders that were auto-cancelled due to overflow.

        These are visual-only entries in game_state.cancelling_arrows that persist
        briefly after the order is removed. Shows a red arrow with shake effect
        that fades out over ARROW_CANCEL_DURATION seconds.
        """
        if not hasattr(self.game, 'game_state') or not self.game.game_state:
            return

        cancelling = self.game.game_state.cancelling_arrows
        if not cancelling:
            return

        now = time.time()
        expired = []

        for i, entry in enumerate(cancelling):
            elapsed = now - entry['start_time']
            if elapsed >= ARROW_CANCEL_DURATION:
                expired.append(i)
                continue

            # Progress 0.0 → 1.0 over the animation duration
            progress = elapsed / ARROW_CANCEL_DURATION

            from_terr = entry['from_territory']
            to_terr = entry['to_territory']
            army_count = entry['army_count']

            if from_terr not in self.game.scaled_centers or to_terr not in self.game.scaled_centers:
                expired.append(i)
                continue

            from_world = self.game.scaled_centers[from_terr]
            to_world = self.game.scaled_centers[to_terr]

            from_x, from_y = self.game.world_to_screen(from_world)
            to_x, to_y = self.game.world_to_screen(to_world)

            # Shake offset: decreasing amplitude sine wave
            shake_offset = math.sin(elapsed * ARROW_CANCEL_SHAKE_FREQ) * ARROW_CANCEL_SHAKE_AMP * (1.0 - progress)
            from_x += shake_offset
            to_x += shake_offset

            # Fade alpha: full → 0 over duration
            alpha = int(255 * (1.0 - progress))

            # Draw arrow line and head on a temporary surface for alpha blending
            # Use a simple approach: draw with fading color (blend toward background)
            fade_r = int(COLOR_ARROW_CANCELLED[0] * (1.0 - progress))
            fade_g = int(COLOR_ARROW_CANCELLED[1] * (1.0 - progress))
            fade_b = int(COLOR_ARROW_CANCELLED[2] * (1.0 - progress))
            arrow_color = (max(fade_r, 1), fade_g, fade_b)

            # Draw main line
            pygame.draw.line(self.game.screen, arrow_color,
                             (int(from_x), int(from_y)), (int(to_x), int(to_y)),
                             ARROW_LINE_WIDTH)

            # Calculate and draw arrowhead
            dx = to_x - from_x
            dy = to_y - from_y
            length = math.sqrt(dx * dx + dy * dy)

            if length > 0:
                dx /= length
                dy /= length
                arrow_size = ARROW_HEAD_SIZE
                arrow_angle = ARROW_HEAD_ANGLE_RAD

                left_x = to_x - arrow_size * (dx * math.cos(arrow_angle) - dy * math.sin(arrow_angle))
                left_y = to_y - arrow_size * (dy * math.cos(arrow_angle) + dx * math.sin(arrow_angle))
                right_x = to_x - arrow_size * (dx * math.cos(arrow_angle) + dy * math.sin(arrow_angle))
                right_y = to_y - arrow_size * (dy * math.cos(arrow_angle) - dx * math.sin(arrow_angle))

                pygame.draw.polygon(self.game.screen, arrow_color, [
                    (int(to_x), int(to_y)),
                    (int(left_x), int(left_y)),
                    (int(right_x), int(right_y))
                ])

                # Draw army count badge at midpoint (fading red)
                mid_x = int((from_x + to_x) / 2)
                mid_y = int((from_y + to_y) / 2)
                self.game.helpers.draw_circle_badge(
                    (mid_x, mid_y), army_count, border_color=arrow_color
                )

        # Remove expired entries (reverse order to keep indices valid)
        for i in reversed(expired):
            cancelling.pop(i)

    def _draw_sim_movement_arrows(self, sim_state):
        """Draw movement arrows for simultaneous mode.

        Shows player's own orders and allied players' orders.
        Uses different colors: green for own, cyan for allied.

        During planning phase:
        - Local player's orders come from game_state.movement_orders (being created in UI)
        - Local player's already queued orders are in sim_state.player_orders[local_player]
        - Allied players' orders are in sim_state.player_orders (only shows allies, not enemies)

        Args:
            sim_state: SimultaneousGameState instance
        """
        # Use LOCAL player, not current_player (in sim mode, current_player may not be the human)
        local_player = self.game.get_local_player()

        # Safe access to player_teams (can be list or dict)
        player_teams = self.game.game_state.player_teams
        if isinstance(player_teams, dict):
            local_team = player_teams.get(local_player, local_player)
        else:
            local_team = player_teams[local_player] if local_player < len(player_teams) else local_player

        # Collect orders to draw
        orders_to_draw = []  # [(order_dict, player_id, is_ally)]

        # 1. Local player's orders from game_state.movement_orders (being created in UI)
        for order in self.game.game_state.movement_orders:
            order_dict = {
                'type': 'movement',
                'from_territory': order.from_territory,
                'to_territory': order.to_territory,
                'army_count': order.army_count
            }
            orders_to_draw.append((order_dict, local_player, False))

        # 2. Local player's already queued orders from sim_state.player_orders
        local_queued_orders = sim_state.player_orders.get(local_player, [])
        for order in local_queued_orders:
            if order.get('type') == 'movement':
                orders_to_draw.append((order, local_player, False))

        # 3. Allied players' orders from sim_state.player_orders (already queued after End Turn)
        for player_id, orders in sim_state.player_orders.items():
            if player_id == local_player:
                continue  # Already handled above

            # Safe access to player_teams for other players
            if isinstance(player_teams, dict):
                player_team = player_teams.get(player_id, player_id)
            else:
                player_team = player_teams[player_id] if player_id < len(player_teams) else player_id

            # Only show allied orders (same team, different player)
            if player_team == local_team:
                for order in orders:
                    if order.get('type') == 'movement':
                        orders_to_draw.append((order, player_id, True))

        # Group by route for count badges
        route_counts = {}  # (from, to, is_ally) -> (total_count, player_id)

        for order, player_id, is_ally in orders_to_draw:
            from_terr = order.get('from_territory')
            to_terr = order.get('to_territory')
            count = order.get('army_count', 1)

            key = (from_terr, to_terr, is_ally)
            if key not in route_counts:
                route_counts[key] = (0, player_id)
            route_counts[key] = (route_counts[key][0] + count, player_id)

        # Draw arrows
        for (from_territory, to_territory, is_ally), (total_count, order_player) in route_counts.items():
            if from_territory not in self.game.scaled_centers or to_territory not in self.game.scaled_centers:
                continue

            # Get FROM position
            from_cx, from_cy = self.game.scaled_centers[from_territory]
            garrisons_from = self.game.game_state.territory_garrisons.get(from_territory, {})
            num_garrisons_from = sum(1 for g in garrisons_from.values() if g.get('unmoved', 0) + g.get('moved', 0) > 0)

            if num_garrisons_from > 1 and order_player is not None:
                flag_positions = self.game.game_state.get_flag_positions_for_territory(
                    from_territory, from_cx, from_cy, num_garrisons_from
                )

                garrison_index = 0
                for player_index in sorted(garrisons_from.keys()):
                    if player_index == order_player:
                        break
                    if garrisons_from[player_index].get('unmoved', 0) + garrisons_from[player_index].get('moved', 0) > 0:
                        garrison_index += 1

                if garrison_index < len(flag_positions):
                    from_world = flag_positions[garrison_index]
                else:
                    from_world = (from_cx, from_cy)
            else:
                from_world = (from_cx, from_cy)

            to_world = self.game.scaled_centers[to_territory]

            # Transform to screen coordinates
            from_x, from_y = self.game.world_to_screen(from_world)
            to_x, to_y = self.game.world_to_screen(to_world)

            # Arrow color - green for own orders, cyan for allied orders
            if is_ally:
                arrow_color = (0, 180, 200)  # Cyan for allies
            else:
                arrow_color = (0, 200, 0)  # Green for own

            # Draw main line
            pygame.draw.line(self.game.screen, arrow_color, (int(from_x), int(from_y)), (int(to_x), int(to_y)), 4)

            # Calculate arrowhead
            dx = to_x - from_x
            dy = to_y - from_y
            length = math.sqrt(dx*dx + dy*dy)

            if length > 0:
                dx /= length
                dy /= length

                arrow_size = 15
                arrow_angle = 0.5236  # 30 degrees

                left_x = to_x - arrow_size * (dx * math.cos(arrow_angle) - dy * math.sin(arrow_angle))
                left_y = to_y - arrow_size * (dy * math.cos(arrow_angle) + dx * math.sin(arrow_angle))
                right_x = to_x - arrow_size * (dx * math.cos(arrow_angle) + dy * math.sin(arrow_angle))
                right_y = to_y - arrow_size * (dy * math.cos(arrow_angle) - dx * math.sin(arrow_angle))

                pygame.draw.polygon(self.game.screen, arrow_color, [
                    (int(to_x), int(to_y)),
                    (int(left_x), int(left_y)),
                    (int(right_x), int(right_y))
                ])

                # Draw army count badge
                mid_x = int((from_x + to_x) / 2)
                mid_y = int((from_y + to_y) / 2)
                self.game.helpers.draw_circle_badge((mid_x, mid_y), total_count, border_color=arrow_color)

    def draw_battle_markers(self):
        """Draw battle markers with hurricane particle effects (Phase 2D: camera-aware)"""
        # Always clear battle markers list first (prevents stale markers from blocking clicks)
        self.game.battle_markers = []

        # Check if we should show battle markers
        # Sequential mode: turn_phase == 'battles'
        # Simultaneous mode: sim_phase == 'resolving' AND pending_battles exist
        show_battles = False

        if self.game.game_state.turn_phase == 'battles':
            show_battles = True
        elif hasattr(self.game, 'sim_state') and self.game.sim_state is not None:
            if self.game.sim_state.sim_phase == 'resolving':
                show_battles = True

        if not show_battles:
            # Clear all battle effects when not in battle phase
            self.battle_effects.clear()
            return

        # Get delta time for animation updates
        delta_time = self.game.clock.get_time() / 1000.0  # Convert milliseconds to seconds

        # Track which battle territories still exist (keyed by territory, not index)
        active_battle_territories = set()

        for i, battle in enumerate(self.game.game_state.pending_battles):
            territory = battle.territory
            active_battle_territories.add(territory)

            # Get world coordinates from scaled centers
            if territory not in self.game.scaled_centers:
                continue

            world_center = self.game.scaled_centers[territory]

            # Transform to screen coordinates (Phase 2D: camera transformation!)
            screen_x, screen_y = self.game.world_to_screen(world_center)
            screen_x = int(screen_x)
            screen_y = int(screen_y)

            # Create or get existing battle effect for this battle
            # FIX: Key by territory name (stable identity) instead of list index
            # to prevent stale colors when battles resolve and indices shift
            if territory not in self.battle_effects:
                # Check if this battle is clickable by the local player
                # In simultaneous mode, only the resolver can click
                # Red = your battle to resolve (click it), Gray = AI/other player resolves
                greyed_out = False
                if hasattr(self.game, 'sim_state') and self.game.sim_state is not None:
                    resolver = getattr(battle, 'resolver', None)
                    local_player = self.game.get_local_player()
                    if resolver is not None and resolver != local_player:
                        greyed_out = True
                else:
                    # Sequential mode: grey out battles during AI turns
                    # (player can't click to resolve these)
                    current = self.game.game_state.current_player
                    if self.game.game_state.player_is_ai[current]:
                        greyed_out = True

                # Create new hurricane effect at battle location
                self.battle_effects[territory] = BattleHurricaneEffect(
                    center_pos=(screen_x, screen_y),
                    num_particles=1000,
                    duration=3.0,
                    num_arms=4,
                    greyed_out=greyed_out
                )
            else:
                # Update center position (in case of camera movement)
                effect = self.battle_effects[territory]
                effect.center_x = screen_x
                effect.center_y = screen_y

            # Update and render the hurricane effect
            effect = self.battle_effects[territory]
            effect.update(delta_time)
            effect.render(self.game.screen)

            # Draw battle number below the effect
            number_text = self.game.small_font.render(f"#{i+1}", True, WHITE)
            number_rect = number_text.get_rect(center=(screen_x, screen_y + 60))
            self.game.screen.blit(number_text, number_rect)

            # Store clickable area for this battle marker (use effect size)
            # Hurricane base size is 40px, max expansion is 54px (40 * 1.35)
            click_radius = 60  # Larger for easier clicking
            self.game.battle_markers.append(pygame.Rect(screen_x - click_radius, screen_y - click_radius,
                                                    click_radius * 2, click_radius * 2))

        # Clean up effects for battles that no longer exist
        removed_territories = set(self.battle_effects.keys()) - active_battle_territories
        for territory_key in removed_territories:
            del self.battle_effects[territory_key]

    def draw_alliance_markers(self):
        """
        Draw alliance markers with blue particle effects (simultaneous mode only).

        Alliance markers appear when multiple allied armies arrive at the same
        territory during resolution phase. The player with the biggest army
        can click the marker to assign territory ownership.
        """
        # Clear alliance markers list first
        if not hasattr(self.game, 'alliance_markers'):
            self.game.alliance_markers = []
        self.game.alliance_markers = []

        # Only show in simultaneous mode during resolution phase
        if not hasattr(self.game, 'sim_state') or self.game.sim_state is None:
            self.alliance_effects.clear()
            return

        if self.game.sim_state.sim_phase != 'resolving':
            self.alliance_effects.clear()
            return

        # Get pending alliance markers from the phase manager
        # These are created when allied armies capture territory together
        if not hasattr(self.game.sim_state, 'phase_manager') or not self.game.sim_state.phase_manager:
            self.alliance_effects.clear()
            return

        pending_markers = self.game.sim_state.phase_manager.pending_alliance_markers
        if not pending_markers:
            self.alliance_effects.clear()
            return

        delta_time = self.game.clock.get_time() / 1000.0
        active_territories = set()

        for marker in pending_markers:
            territory = marker['territory']
            active_territories.add(territory)

            # Get world coordinates
            if territory not in self.game.scaled_centers:
                continue

            world_center = self.game.scaled_centers[territory]
            screen_x, screen_y = self.game.world_to_screen(world_center)
            screen_x = int(screen_x)
            screen_y = int(screen_y)

            # Determine if marker should be greyed out (player is not the chooser)
            greyed_out = False
            chooser = marker.get('chooser')
            if chooser is not None:
                # Get local player (human player viewing this)
                local_player = self.game.get_local_player()
                if chooser != local_player:
                    greyed_out = True

            # Create or update alliance effect
            if territory not in self.alliance_effects:
                self.alliance_effects[territory] = AllianceMarkerEffect(
                    center_pos=(screen_x, screen_y),
                    num_particles=600,
                    duration=3.0,
                    num_arms=3,
                    greyed_out=greyed_out
                )
            else:
                effect = self.alliance_effects[territory]
                effect.center_x = screen_x
                effect.center_y = screen_y
                # Update greyed_out status if it changed (e.g., different chooser)
                if effect.greyed_out != greyed_out:
                    # Recreate effect with new color scheme
                    self.alliance_effects[territory] = AllianceMarkerEffect(
                        center_pos=(screen_x, screen_y),
                        num_particles=600,
                        duration=3.0,
                        num_arms=3,
                        greyed_out=greyed_out
                    )

            # Update and render the effect
            effect = self.alliance_effects[territory]
            effect.update(delta_time)
            effect.render(self.game.screen)

            # Store clickable area for this alliance marker
            # Only the chooser (biggest army) can click, but store all markers for UI
            click_radius = 55
            self.game.alliance_markers.append({
                'rect': pygame.Rect(screen_x - click_radius, screen_y - click_radius,
                                   click_radius * 2, click_radius * 2),
                'territory': territory,
                'players': marker['players'],
                'chooser': marker['chooser']
            })

        # Clean up effects for territories that no longer have alliance arrivals
        removed_territories = set(self.alliance_effects.keys()) - active_territories
        for territory in removed_territories:
            del self.alliance_effects[territory]

    def draw_overflow_indicators(self):
        """
        Draw overflow indicators (red glow + pulse) for territories with excess armies.

        In simultaneous mode, when an alliance arrival assigns territory to a player
        who would exceed the army limit, the overflow is allowed for one turn.
        A visual indicator warns the player to move armies before they disband.
        """
        # Only active in simultaneous mode
        if not hasattr(self.game, 'sim_state') or self.game.sim_state is None:
            return

        overflow_territories = getattr(self.game.sim_state, 'overflow_territories', {})
        if not overflow_territories:
            return

        # Pre-calculate UI scale for performance
        ui_scale = self.game.get_ui_scale_factor()

        for territory in overflow_territories:
            if territory not in self.game.scaled_centers:
                continue

            world_center = self.game.scaled_centers[territory]
            screen_x, screen_y = self.game.world_to_screen(world_center)

            # Pulsing red glow effect
            pulse = abs(math.sin(time.time() * 4))  # Faster pulse for urgency
            glow_alpha = int(100 + 100 * pulse)

            # Reduce glow layers when zoomed out
            glow_layers = 1 if ui_scale < 1.5 else 3

            # Draw red glow rings around overflow territory
            for i in range(glow_layers):
                glow_radius = int((25 + i * 5) * ui_scale)
                glow_surface = self.get_reusable_surface(glow_radius * 2 + 10, glow_radius * 2 + 10)
                pygame.draw.circle(glow_surface, (255, 50, 50, glow_alpha // (i + 1)),
                                 (glow_radius + 5, glow_radius + 5), glow_radius, 4)
                self.game.screen.blit(glow_surface, (int(screen_x) - glow_radius - 5,
                                                    int(screen_y) - glow_radius - 5))
                self.return_surface_to_pool(glow_surface)

    def trigger_castle_upgrade_effect(self, territory, plot_index):
        """
        Trigger a golden particle effect when a Keep is upgraded to Castle.

        Args:
            territory: Name of the territory
            plot_index: Index of the plot containing the upgraded Keep
        """
        # Get plot position in world coordinates
        if territory not in self.game.scaled_plots:
            return
        if plot_index >= len(self.game.scaled_plots[territory]):
            return

        world_plot_pos = self.game.scaled_plots[territory][plot_index]

        # Create effect in world coordinates (will be converted to screen each frame)
        effect = CastleUpgradeEffect(center_pos=world_plot_pos, world_coords=True)
        self.castle_upgrade_effects.append(effect)

    def update_castle_upgrade_effects(self, delta_time):
        """
        Update all active castle upgrade effects.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        # Update all effects
        for effect in self.castle_upgrade_effects[:]:
            effect.update(delta_time)
            # Remove finished effects
            if effect.is_finished():
                self.castle_upgrade_effects.remove(effect)

    def render_castle_upgrade_effects(self):
        """Render all active castle upgrade effects on screen."""
        for effect in self.castle_upgrade_effects:
            effect.render(self.game.screen, world_to_screen_func=self.game.world_to_screen)

    # ========================================
    # HERO ABILITY VISUAL EFFECTS
    # ========================================

    # Color palettes for each targeted hero ability (5 shades each)
    ABILITY_PALETTES = {
        # Decisive Strike: blue shades (explosion only, no swirl)
        'Decisive Strike': [
            (30, 60, 150), (50, 100, 200), (80, 140, 255), (120, 170, 255), (170, 200, 255)
        ],
        # Regicide: dark purple shades (inward implosion, ominous)
        'Regicide': [
            (80, 0, 120), (120, 0, 180), (40, 0, 60), (150, 0, 200), (60, 0, 90)
        ],
        # Levy: gold shades (same as CastleUpgradeEffect, 5 random polygon explosions)
        'Levy': [
            (184, 134, 11), (218, 165, 32), (255, 215, 0), (255, 223, 77), (255, 236, 139)
        ],
        # Relentless Charge: dust/brown shades (cavalry dust cloud)
        'Relentless Charge': [
            (160, 120, 60), (200, 170, 100), (140, 100, 40), (180, 150, 80), (120, 90, 30)
        ],
        # Royal Charisma: blue arc (units stolen from target to Narn's Keep)
        'Royal Charisma': [
            (30, 60, 150), (50, 100, 200), (80, 140, 255), (120, 170, 255), (170, 200, 255)
        ],
        # Valorous Charge: light blue/white arc (troops from Keep to target)
        'Valorous Charge': [
            (200, 220, 255), (150, 180, 220), (255, 255, 255), (170, 200, 240), (220, 235, 255)
        ],
    }

    # Aggressive Diplomacy bubble color (fire orange, polygon-filling bubble burst)
    AGGRESSIVE_DIPLOMACY_COLOR = (255, 120, 30)

    # Embargo bubble color (dark red, polygon-filling bubble burst on enemy territories)
    EMBARGO_COLOR = (160, 20, 20)

    def trigger_ability_effect(self, ability_name, target_territory,
                               player_index, source_territory=None):
        """
        Trigger a visual effect for a hero ability activation.

        Effect types per ability:
        Targeted abilities (target_territory required):
        - Aggressive Diplomacy: polygon-filling rising bubbles (like Defiance aura, one-shot ~1s)
        - Decisive Strike: blue explosion only (burst + quick fade)
        - Regicide: dark purple inward implosion
        - Levy: 5 small gold explosions at random polygon points (explosion only, no swirl)
        - Relentless Charge: dust/brown outward explosion
        - Royal Charisma: blue particle arc from target to Narn's Keep
        - Valorous Charge: blue/white particle arc from Keep to target

        Immediate abilities (target_territory=None, looks up locations from game_state):
        - Reinforce: silver/steel explosion at hero's Keep territory
        - Extort Populace: gold explosion at each Keep/Castle building plot
        - Embargo: dark red polygon-filling bubbles on all enemy territories

        Args:
            ability_name: Name of the ability
            target_territory: Territory where ability lands (None for immediate abilities)
            player_index: Player who activated the ability
            source_territory: Source territory for arc effects (Royal Charisma, Valorous Charge)
        """
        # --- Reinforce: silver/steel explosion at hero's Keep territory ---
        if ability_name == 'Reinforce':
            gs = self.game.game_state
            if gs and player_index in gs.heroes:
                # Find Brennhen or Aevencourne (campaign clone)
                for hero_name in ('Darius Brennhen', 'Regnus Aevencourne'):
                    if hero_name in gs.heroes[player_index]:
                        keep_terr = gs.heroes[player_index][hero_name].get('keep_territory')
                        if keep_terr and keep_terr in self.game.scaled_centers:
                            # Silver/steel burst at Keep location
                            palette = [
                                (160, 170, 180), (192, 192, 192), (220, 220, 230),
                                (200, 205, 210), (240, 240, 245)
                            ]
                            effect = AbilityBurstEffect(
                                center_pos=self.game.scaled_centers[keep_terr],
                                color_palette=palette,
                                num_particles=120,
                                behavior='explode',
                                world_coords=True,
                                swirl_duration=0,
                                float_duration=0.5
                            )
                            self.ability_effects.append(effect)
                        break
            return

        # --- Extort Populace: gold explosion at each Keep/Castle plot ---
        if ability_name == 'Extort Populace':
            gs = self.game.game_state
            if not gs:
                return
            palette = self.ABILITY_PALETTES['Levy']  # Reuse gold palette
            for territory, buildings in gs.buildings.items():
                if gs.territory_owners.get(territory, -1) != player_index:
                    continue
                for plot_index, building_type in buildings.items():
                    if building_type in ('Keep', 'Castle'):
                        # Get building plot position in world coords
                        if (territory in self.game.scaled_plots
                                and plot_index < len(self.game.scaled_plots[territory])):
                            plot_pos = self.game.scaled_plots[territory][plot_index]
                            effect = AbilityBurstEffect(
                                center_pos=plot_pos,
                                color_palette=palette,
                                num_particles=28,
                                behavior='explode',
                                world_coords=True,
                                swirl_duration=0,
                                float_duration=0.5
                            )
                            self.ability_effects.append(effect)
            return

        # --- Embargo: persistent dark red bubbles on all enemy territories ---
        # Creates continuous effects tracked in self.embargo_effects,
        # synced each frame by sync_embargo_effects() until embargo expires
        if ability_name == 'Embargo':
            gs = self.game.game_state
            if not gs:
                return
            for territory, owner in gs.territory_owners.items():
                if owner >= 0 and owner != player_index:
                    if territory not in self.embargo_effects:
                        polygon = self.game.scaled_polygons.get(territory)
                        if polygon:
                            effect = AbilityPolygonBurstEffect(
                                polygon=polygon,
                                color=self.EMBARGO_COLOR,
                                num_bubbles=0,
                                world_coords=True,
                                continuous=True
                            )
                            self.embargo_effects[territory] = effect
            return

        # --- Aggressive Diplomacy: polygon-filling bubble burst ---
        if ability_name == 'Aggressive Diplomacy':
            polygon = self.game.scaled_polygons.get(target_territory)
            if not polygon:
                return
            effect = AbilityPolygonBurstEffect(
                polygon=polygon,
                color=self.AGGRESSIVE_DIPLOMACY_COLOR,
                num_bubbles=60,
                world_coords=True
            )
            self.ability_effects.append(effect)
            return

        # --- Levy: 5 small gold explosions at random points within polygon ---
        if ability_name == 'Levy':
            palette = self.ABILITY_PALETTES['Levy']
            polygon = self.game.scaled_polygons.get(target_territory)
            if not polygon:
                return
            # Pick 5 random points inside the territory polygon
            points = self._random_points_in_polygon(polygon, count=5)
            for point in points:
                # Small explosion at each point: burst only, quick fade, no swirl
                effect = AbilityBurstEffect(
                    center_pos=point,
                    color_palette=palette,
                    num_particles=28,
                    behavior='explode',
                    world_coords=True,
                    swirl_duration=0,       # No swirl phase
                    float_duration=0.5      # Quick fade after explosion
                )
                self.ability_effects.append(effect)
            return

        # --- Arc abilities: Royal Charisma and Valorous Charge ---
        if ability_name in ('Royal Charisma', 'Valorous Charge') and source_territory:
            palette = self.ABILITY_PALETTES.get(ability_name)
            if not palette:
                return
            if source_territory not in self.game.scaled_centers:
                return
            if target_territory not in self.game.scaled_centers:
                return
            source_pos = self.game.scaled_centers[source_territory]
            target_pos = self.game.scaled_centers[target_territory]
            effect = AbilityArcEffect(
                source_pos=source_pos,
                dest_pos=target_pos,
                color_palette=palette,
                num_particles=80,
                world_coords=True
            )
            self.ability_effects.append(effect)
            return

        # --- Decisive Strike: blue explosion only (burst + quick fade, no swirl) ---
        if ability_name == 'Decisive Strike':
            palette = self.ABILITY_PALETTES['Decisive Strike']
            if target_territory not in self.game.scaled_centers:
                return
            target_pos = self.game.scaled_centers[target_territory]
            effect = AbilityBurstEffect(
                center_pos=target_pos,
                color_palette=palette,
                num_particles=140,
                behavior='explode',
                world_coords=True,
                swirl_duration=0,       # No swirl, explosion only
                float_duration=0.5      # Quick fade after explosion
            )
            self.ability_effects.append(effect)
            return

        # --- Default burst abilities: Regicide (implode), Relentless Charge (explode) ---
        palette = self.ABILITY_PALETTES.get(ability_name)
        if not palette:
            return
        if target_territory not in self.game.scaled_centers:
            return
        target_pos = self.game.scaled_centers[target_territory]
        # Regicide uses 'implode', everything else defaults to 'explode'
        behavior = 'implode' if ability_name == 'Regicide' else 'explode'
        effect = AbilityBurstEffect(
            center_pos=target_pos,
            color_palette=palette,
            num_particles=120,
            behavior=behavior,
            world_coords=True
        )
        self.ability_effects.append(effect)

    @staticmethod
    def _point_in_polygon(x, y, polygon):
        """Ray-casting point-in-polygon test for random point sampling."""
        inside = False
        n = len(polygon)
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = ((y - p1y) * (p2x - p1x)
                                       / (p2y - p1y) + p1x)
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def _random_points_in_polygon(self, polygon, count=5, max_attempts=20):
        """
        Generate random points inside a polygon via rejection sampling.

        Used by Levy to spawn explosion effects at random territory locations.

        Args:
            polygon: List of (x, y) tuples defining polygon vertices
            count: Number of points to generate
            max_attempts: Max rejection sampling attempts per point
        Returns:
            List of (x, y) tuples inside the polygon
        """
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        import random
        points = []
        for _ in range(count):
            for _ in range(max_attempts):
                x = random.uniform(min_x, max_x)
                y = random.uniform(min_y, max_y)
                if self._point_in_polygon(x, y, polygon):
                    points.append((x, y))
                    break
        return points

    def update_ability_effects(self, delta_time):
        """Update all active hero ability visual effects."""
        for effect in self.ability_effects[:]:
            effect.update(delta_time)
            if effect.is_finished():
                self.ability_effects.remove(effect)

    def render_ability_effects(self):
        """Render all active hero ability visual effects on screen."""
        for effect in self.ability_effects:
            effect.render(self.game.screen,
                          world_to_screen_func=self.game.world_to_screen)

    def sync_embargo_effects(self):
        """
        Sync persistent embargo bubble effects with game state.

        Creates continuous bubble effects on enemy territories when embargo is active.
        Stops and removes effects when embargo expires (embargo_blocked_players empties).
        Called each frame from the main update loop.
        """
        gs = self.game.game_state
        if not gs:
            return

        embargo_active = len(gs.embargo_blocked_players) > 0

        if not embargo_active and self.embargo_effects:
            # Embargo expired: stop all persistent effects (let bubbles fade out)
            for territory, effect in list(self.embargo_effects.items()):
                effect.stop()
            # Remove finished effects
            for territory in list(self.embargo_effects.keys()):
                if self.embargo_effects[territory].is_finished():
                    del self.embargo_effects[territory]

    def update_embargo_effects(self, delta_time):
        """Update all active embargo persistent effects."""
        for territory in list(self.embargo_effects.keys()):
            effect = self.embargo_effects[territory]
            effect.update(delta_time)
            if effect.is_finished():
                del self.embargo_effects[territory]

    def render_embargo_effects(self):
        """Render all active embargo persistent effects."""
        for effect in self.embargo_effects.values():
            effect.render(self.game.screen,
                          world_to_screen_func=self.game.world_to_screen)

    def sync_production_glow_effects(self):
        """
        Sync production glow effects with current training queues.

        FPS OPT: Skips full building scan when dirty flag is clean.
        Dirty flag set by start_training, finish_training, cancel_training,
        start_hero_training, finish_hero_training, territory capture.
        """
        gs = self.game.game_state
        # FPS OPT: Skip full scan if training queues haven't changed
        current_version = gs._training_version
        if current_version == self._production_glow_version:
            return
        self._production_glow_version = current_version
        currently_training = set()  # Set of (territory, plot_index) with active training

        # Use the local human player for visibility check (not current_player,
        # which changes each turn in sequential mode and would show enemy effects)
        if gs.network_mode and gs.local_player_index is not None:
            viewer_player = gs.local_player_index
        else:
            # Find the first human player as the viewer
            viewer_player = 0
            for i in range(gs.num_players):
                if not gs.player_is_ai[i]:
                    viewer_player = i
                    break

        # Check all territories for buildings with active production
        for territory, buildings in gs.buildings.items():
            owner = gs.territory_owners.get(territory, -1)
            if owner < 0:
                continue

            # Only show effects for viewer's buildings or allied buildings
            if owner != viewer_player and not gs.are_allies(owner, viewer_player):
                continue

            for plot_index, building in buildings.items():
                has_training = False

                if building == 'Barracks':
                    # Check unit training queue
                    if (territory in gs.training_queue and
                        plot_index in gs.training_queue[territory] and
                        len(gs.training_queue[territory][plot_index]) > 0):
                        has_training = True

                elif building == 'Keep':
                    # Check hero training queue (Keep or Castle - both use 'Keep' building type)
                    if (territory in gs.hero_training_queue and
                        plot_index in gs.hero_training_queue[territory]):
                        has_training = True

                if has_training:
                    currently_training.add((territory, plot_index))

                    # Create effect if not already active
                    if (territory, plot_index) not in self.production_glow_effects:
                        world_pos = self.game.scaled_plots[territory][plot_index]
                        player_color = gs.get_player_color(owner)
                        effect = ProductionGlowEffect(
                            center_pos=world_pos,
                            player_color=player_color,
                            world_coords=True
                        )
                        self.production_glow_effects[(territory, plot_index)] = effect
                    else:
                        # Update color in case territory changed ownership
                        current_color = gs.get_player_color(owner)
                        self.production_glow_effects[(territory, plot_index)].update_color(current_color)

        # Remove effects for buildings that stopped production
        to_remove = []
        for key in self.production_glow_effects:
            if key not in currently_training:
                to_remove.append(key)

        for key in to_remove:
            del self.production_glow_effects[key]

    def update_production_glow_effects(self, delta_time):
        """
        Update all active production glow effects.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        for effect in self.production_glow_effects.values():
            effect.update(delta_time)

    def render_production_glow_effects(self):
        """
        Render all active production glow effects on screen.

        Effects are rendered behind buildings to create a glow emanating
        from the building position.
        """
        # Get current zoom scale for proper ray sizing
        zoom_scale = self.game.camera_zoom

        for effect in self.production_glow_effects.values():
            effect.render(
                self.game.screen,
                world_to_screen_func=self.game.world_to_screen,
                zoom_scale=zoom_scale
            )

    def _draw_all_plots_unified(self, ui_scale, scaled_empty_plot_radius, building_letter_font):
        """
        FPS OPTIMIZATION Phase 3.1: Unified plot rendering in single pass.

        Combines _draw_completed_building_plots, _draw_under_construction_plots,
        and _draw_empty_plot_markers into one loop to eliminate redundant iterations.

        Old: 3 separate loops × 39 territories × 4 plots = 468 iterations/frame
        New: 1 loop × 39 territories × 4 plots = 156 iterations/frame

        Rendering order per plot:
        1. Determine plot state (completed > under_construction > empty)
        2. Render based on state

        Args:
            ui_scale: Scale factor based on camera zoom (1.0 to 1.5)
            scaled_empty_plot_radius: Radius for plot circles (zoom-adjusted)
            building_letter_font: Font for building letters
        """
        scaled_plot_surface_size = int(PLOT_SURFACE_SIZE * ui_scale)
        scaled_plot_center_offset = scaled_plot_surface_size // 2
        mouse_screen_x, mouse_screen_y = self.game.mouse_pos
        current_player = self.game.game_state.current_player

        for territory, plots in self.game.scaled_plots.items():
            owner = self.game.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue

            # Get cached screen positions for this territory (single lookup)
            screen_plots = self.get_cached_screen_plots(territory)

            # Get building and construction data for this territory (single lookups)
            territory_buildings = self.game.game_state.buildings.get(territory, {})
            territory_construction = self.game.game_state.under_construction.get(territory, {})

            for plot_index, screen_pos in enumerate(screen_plots):
                # Skip off-screen plots
                if (screen_pos[0] < -100 or screen_pos[0] > self.game.screen.get_width() + 100 or
                    screen_pos[1] < -100 or screen_pos[1] > self.game.screen.get_height() + 100):
                    continue

                x, y = int(screen_pos[0]), int(screen_pos[1])

                # Determine plot state: completed > under_construction > empty
                building = territory_buildings.get(plot_index)
                under_construction = territory_construction.get(plot_index)

                # Common hover/click detection (reused across all states)
                distance_sq = (x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2
                is_hovering = distance_sq <= scaled_empty_plot_radius ** 2
                is_clicking = (self.game.clicked_element and
                              self.game.clicked_element[0] == 'plot' and
                              self.game.clicked_element[1] == (territory, plot_index))

                if building:
                    # === COMPLETED BUILDING ===
                    self._render_completed_plot(
                        territory, plot_index, building, owner, x, y,
                        ui_scale, scaled_empty_plot_radius, scaled_plot_surface_size,
                        scaled_plot_center_offset, building_letter_font,
                        is_hovering, is_clicking, current_player
                    )
                elif under_construction:
                    # === UNDER CONSTRUCTION ===
                    self._render_construction_plot(
                        territory, plot_index, under_construction, owner, x, y,
                        ui_scale, scaled_empty_plot_radius, scaled_plot_surface_size,
                        scaled_plot_center_offset, building_letter_font,
                        is_hovering, is_clicking, current_player
                    )
                else:
                    # === EMPTY PLOT ===
                    self._render_empty_plot(
                        territory, plot_index, owner, x, y,
                        ui_scale, scaled_empty_plot_radius, scaled_plot_surface_size,
                        scaled_plot_center_offset, is_hovering, is_clicking, current_player
                    )

    def _render_completed_plot(self, territory, plot_index, building, owner, x, y,
                               ui_scale, scaled_empty_plot_radius, scaled_plot_surface_size,
                               scaled_plot_center_offset, building_letter_font,
                               is_hovering, is_clicking, current_player):
        """Render a completed building plot (helper for unified loop)."""
        # Get building info
        try:
            building_info = self.game.game_state.building_types[building]
            letter = building_info['letter']
            if building == 'Keep':
                display_letter, _ = self.game.game_state.get_keep_display_info(territory, plot_index)
                letter = display_letter
        except (KeyError, TypeError):
            return

        # Get plot surface from pool
        plot_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)

        # Calculate circle color with feedback
        owner_color = self.game.game_state.get_player_color(owner)
        softened_color = tuple(int(c * 0.7) for c in owner_color)
        circle_color = softened_color
        if is_clicking:
            circle_color = brighten_color(circle_color, 0.4)
        elif is_hovering:
            circle_color = lighten_color(circle_color, 0.2)

        # Draw circle
        pygame.draw.circle(plot_surface, circle_color,
                          (scaled_plot_center_offset, scaled_plot_center_offset),
                          scaled_empty_plot_radius)
        pygame.draw.circle(plot_surface, COLOR_PLOT_BORDER,
                          (scaled_plot_center_offset, scaled_plot_center_offset),
                          scaled_empty_plot_radius, 2)
        self.game.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
        self.return_surface_to_pool(plot_surface)

        # Draw building icon
        icon_building = building
        if building == 'Keep':
            _, display_name = self.game.game_state.get_keep_display_info(territory, plot_index)
            if display_name == 'Castle':
                icon_building = 'Castle'

        if icon_building in self.game.building_icons and self.game.building_icons[icon_building]:
            building_icon = self.game.building_icons[icon_building]
            icon_size = int(scaled_empty_plot_radius * 2)
            cached_icon = self.get_cached_scaled_building(icon_building, building_icon, icon_size)
            needs_effects = (owner != current_player or is_clicking or is_hovering)

            if needs_effects:
                display_icon = cached_icon.copy()
                if owner != current_player:
                    grey_overlay = self.get_reusable_surface(icon_size, icon_size)
                    grey_overlay.fill((128, 128, 128, 180))
                    display_icon.blit(grey_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    self.return_surface_to_pool(grey_overlay)
                if is_clicking:
                    bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                    bright_overlay.fill((100, 100, 100, 100))
                    display_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                    self.return_surface_to_pool(bright_overlay)
                elif is_hovering:
                    light_overlay = self.get_reusable_surface(icon_size, icon_size)
                    light_overlay.fill((50, 50, 50, 50))
                    display_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                    self.return_surface_to_pool(light_overlay)
            else:
                display_icon = cached_icon

            icon_rect = display_icon.get_rect(center=(x, y))
            self.game.screen.blit(display_icon, icon_rect)
        else:
            letter_surface = building_letter_font.render(letter, True, WHITE)
            letter_rect = letter_surface.get_rect(center=(x, y))
            self.game.screen.blit(letter_surface, letter_rect)

        # Draw layered border
        player_color = self.game.game_state.get_player_color(owner)
        pygame.draw.circle(self.game.screen, BLACK, (x, y), scaled_empty_plot_radius, 1)
        pygame.draw.circle(self.game.screen, player_color, (x, y), scaled_empty_plot_radius - 1, 3)
        pygame.draw.circle(self.game.screen, BLACK, (x, y), scaled_empty_plot_radius - 4, 1)

        # Selection glow
        is_selected_hero_keep = False
        if self.game.selected_hero and building == 'Keep':
            if current_player in self.game.game_state.heroes:
                hero_name = self.game.selected_hero
                if hero_name in self.game.game_state.heroes[current_player]:
                    hero_data = self.game.game_state.heroes[current_player][hero_name]
                    if (hero_data['keep_territory'] == territory and
                        hero_data['keep_plot'] == plot_index):
                        is_selected_hero_keep = True

        is_plot_selected = (
            is_selected_hero_keep or
            (self.game.selected_barracks and self.game.selected_barracks == (territory, plot_index)) or
            (self.game.selected_keep and self.game.selected_keep == (territory, plot_index)) or
            (self.game.selected_plot and self.game.selected_plot == (territory, plot_index))
        )

        if is_plot_selected:
            pulse = abs(math.sin(time.time() * 2))
            glow_alpha = int(100 + 100 * pulse)
            for i in range(3):
                glow_radius = int((scaled_empty_plot_radius + i * 5) * ui_scale)
                glow_surface = self.get_reusable_surface(glow_radius * 2 + 10, glow_radius * 2 + 10)
                pygame.draw.circle(glow_surface, (0, 255, 0, glow_alpha // (i + 1)),
                                 (glow_radius + 5, glow_radius + 5), glow_radius, 3)
                self.game.screen.blit(glow_surface, (x - glow_radius - 5, y - glow_radius - 5))
                self.return_surface_to_pool(glow_surface)

    def _render_construction_plot(self, territory, plot_index, under_construction, owner, x, y,
                                  ui_scale, scaled_empty_plot_radius, scaled_plot_surface_size,
                                  scaled_plot_center_offset, building_letter_font,
                                  is_hovering, is_clicking, current_player):
        """Render an under-construction plot (helper for unified loop)."""
        try:
            building_type = under_construction[0]  # entry is (building_type, turns_remaining, cost)
            turns_remaining = under_construction[1]
            building_info = self.game.game_state.building_types[building_type]
            letter = building_info['letter']
        except (KeyError, TypeError, ValueError, IndexError):
            return

        plot_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)
        circle_color = COLOR_CONSTRUCTION
        if is_clicking:
            circle_color = brighten_color(circle_color, 0.4)
        elif is_hovering:
            circle_color = lighten_color(circle_color, 0.2)

        pygame.draw.circle(plot_surface, circle_color,
                          (scaled_plot_center_offset, scaled_plot_center_offset),
                          scaled_empty_plot_radius)
        pygame.draw.circle(plot_surface, COLOR_CONSTRUCTION_BORDER,
                          (scaled_plot_center_offset, scaled_plot_center_offset),
                          scaled_empty_plot_radius, 2)
        self.game.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
        self.return_surface_to_pool(plot_surface)

        # Draw building icon
        if building_type in self.game.building_icons and self.game.building_icons[building_type]:
            building_icon = self.game.building_icons[building_type]
            icon_size = int(scaled_empty_plot_radius * 2)
            cached_icon = self.get_cached_scaled_building(building_type, building_icon, icon_size)
            temp_icon = self.get_reusable_surface(icon_size, icon_size)
            temp_icon.fill((0, 0, 0, 0))
            temp_icon.blit(cached_icon, (0, 0))

            if owner != current_player:
                grey_overlay = self.get_reusable_surface(icon_size, icon_size)
                grey_overlay.fill((128, 128, 128, 180))
                temp_icon.blit(grey_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                self.return_surface_to_pool(grey_overlay)

            if is_clicking:
                bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                bright_overlay.fill((100, 100, 100, 100))
                temp_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                self.return_surface_to_pool(bright_overlay)
            elif is_hovering:
                light_overlay = self.get_reusable_surface(icon_size, icon_size)
                light_overlay.fill((50, 50, 50, 50))
                temp_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                self.return_surface_to_pool(light_overlay)

            temp_icon.set_alpha(180)
            icon_rect = temp_icon.get_rect(center=(x, y))
            self.game.screen.blit(temp_icon, icon_rect)
            self.return_surface_to_pool(temp_icon)
        else:
            letter_surface = building_letter_font.render(letter, True, COLOR_CONSTRUCTION_TEXT)
            letter_rect = letter_surface.get_rect(center=(x, y))
            self.game.screen.blit(letter_surface, letter_rect)

        # Draw layered border
        player_color = self.game.game_state.get_player_color(owner)
        pygame.draw.circle(self.game.screen, BLACK, (x, y), scaled_empty_plot_radius, 1)
        pygame.draw.circle(self.game.screen, player_color, (x, y), scaled_empty_plot_radius - 1, 3)
        pygame.draw.circle(self.game.screen, BLACK, (x, y), scaled_empty_plot_radius - 4, 1)

    def _render_empty_plot(self, territory, plot_index, owner, x, y,
                           ui_scale, scaled_empty_plot_radius, scaled_plot_surface_size,
                           scaled_plot_center_offset, is_hovering, is_clicking, current_player):
        """Render an empty plot marker (helper for unified loop)."""
        plot_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)

        can_build = (owner == current_player and
                    territory not in self.game.game_state.buildings_started_this_turn)

        circle_color = COLOR_EMPTY_PLOT_CAN_BUILD if can_build else COLOR_EMPTY_PLOT_CANNOT_BUILD
        if is_clicking:
            circle_color = brighten_color(circle_color, 0.4)
        elif is_hovering:
            circle_color = lighten_color(circle_color, 0.2)

        pygame.draw.circle(plot_surface, circle_color,
                          (scaled_plot_center_offset, scaled_plot_center_offset),
                          scaled_empty_plot_radius)
        pygame.draw.circle(plot_surface, COLOR_EMPTY_PLOT_BORDER,
                          (scaled_plot_center_offset, scaled_plot_center_offset),
                          scaled_empty_plot_radius, 2)
        self.game.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
        self.return_surface_to_pool(plot_surface)

        # Draw plot icon
        if 'Plot' in self.game.building_icons and self.game.building_icons['Plot']:
            plot_icon = self.game.building_icons['Plot']
            icon_size = int(scaled_empty_plot_radius * 2)
            cached_icon = self.get_cached_scaled_plot('Plot', plot_icon, icon_size)

            # FPS OPT: Only .copy() when effects need to modify the surface in-place
            needs_effects = (not can_build) or is_clicking or is_hovering
            if needs_effects:
                scaled_plot_icon = cached_icon.copy()

                if not can_build:
                    grey_overlay = self.get_reusable_surface(icon_size, icon_size)
                    grey_overlay.fill((128, 128, 128, 180))
                    scaled_plot_icon.blit(grey_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    self.return_surface_to_pool(grey_overlay)

                if is_clicking:
                    bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                    bright_overlay.fill((100, 100, 100, 100))
                    scaled_plot_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                    self.return_surface_to_pool(bright_overlay)
                elif is_hovering:
                    light_overlay = self.get_reusable_surface(icon_size, icon_size)
                    light_overlay.fill((50, 50, 50, 50))
                    scaled_plot_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                    self.return_surface_to_pool(light_overlay)

                icon_rect = scaled_plot_icon.get_rect(center=(x, y))
                self.game.screen.blit(scaled_plot_icon, icon_rect)
            else:
                # FPS OPT: Blit directly from cache — no .copy() needed
                icon_rect = cached_icon.get_rect(center=(x, y))
                self.game.screen.blit(cached_icon, icon_rect)

        # Draw layered border
        player_color = self.game.game_state.get_player_color(owner)
        pygame.draw.circle(self.game.screen, BLACK, (x, y), scaled_empty_plot_radius, 1)
        pygame.draw.circle(self.game.screen, player_color, (x, y), scaled_empty_plot_radius - 1, 3)
        pygame.draw.circle(self.game.screen, BLACK, (x, y), scaled_empty_plot_radius - 4, 1)

        # Tutorial hook: draw pulsing green highlight on plots that should be selected
        if (self.game.game_state.tutorial_mission
                and self.game.game_state.tutorial_mission.should_highlight_plot(territory, plot_index)):
            import math
            pulse = int(180 + 75 * math.sin(pygame.time.get_ticks() / 200.0))
            glow_radius = scaled_empty_plot_radius + 4
            pygame.draw.circle(self.game.screen, (50, 255, 50), (x, y), glow_radius, 3)

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

        for territory, plots in self.game.scaled_plots.items():
            owner = self.game.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue

            # PERFORMANCE OPTIMIZATION: Use cached screen positions instead of world_to_screen every frame
            screen_plots = self.get_cached_screen_plots(territory)

            for plot_index, screen_pos in enumerate(screen_plots):
                # PERFORMANCE: Skip off-screen plots (using screen coordinates now)
                # Screen position is (x, y) tuple - no need to transform
                if (screen_pos[0] < -100 or screen_pos[0] > self.game.screen.get_width() + 100 or
                    screen_pos[1] < -100 or screen_pos[1] > self.game.screen.get_height() + 100):
                    continue

                # Check if completed building exists
                building = None
                if territory in self.game.game_state.buildings:
                    building = self.game.game_state.buildings[territory].get(plot_index)

                if not building:
                    continue  # Skip non-buildings
                
                # Get building info (with error handling)
                try:
                    building_info = self.game.game_state.building_types[building]
                    letter = building_info['letter']

                    # Override for Castle upgrades
                    if building == 'Keep':
                        display_letter, _ = self.game.game_state.get_keep_display_info(territory, plot_index)
                        letter = display_letter
                except (KeyError, TypeError) as e:
                    logger.warning(f"Invalid building type '{building}' in {territory}")
                    continue

                # PERFORMANCE OPTIMIZATION: Use cached screen position (already transformed)
                x, y = int(screen_pos[0]), int(screen_pos[1])

                # PERFORMANCE: Use reusable surface from pool
                plot_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)
                
                # Get owner color and soften it (avoid confusion with army circles)
                owner_color = self.game.game_state.get_player_color(owner)
                # Darken owner color by 30% for buildings (more subtle than armies)
                softened_color = tuple(int(c * 0.7) for c in owner_color)
                
                # Base color
                circle_color = softened_color
                
                # Check for hover
                # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
                is_hovering = False
                mouse_screen_x, mouse_screen_y = self.game.mouse_pos
                distance_sq = (x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2
                if distance_sq <= scaled_empty_plot_radius ** 2:
                    is_hovering = True
                
                # Check for click flash
                is_clicking = (self.game.clicked_element and 
                              self.game.clicked_element[0] == 'plot' and 
                              self.game.clicked_element[1] == (territory, plot_index))
                
                # Apply visual feedback
                if is_clicking:
                    circle_color = brighten_color(circle_color, 0.4)
                elif is_hovering:
                    circle_color = lighten_color(circle_color, 0.2)
                
                # Draw circle
                pygame.draw.circle(plot_surface, circle_color, 
                                 (scaled_plot_center_offset, scaled_plot_center_offset), 
                                 scaled_empty_plot_radius)
                
                # Check if this Keep houses the selected hero
                is_selected_hero_keep = False
                if self.game.selected_hero and building == 'Keep':
                    current_player = self.game.game_state.current_player
                    if current_player in self.game.game_state.heroes:
                        hero_name = self.game.selected_hero
                        if hero_name in self.game.game_state.heroes[current_player]:
                            hero_data = self.game.game_state.heroes[current_player][hero_name]
                            if (hero_data['keep_territory'] == territory and
                                hero_data['keep_plot'] == plot_index):
                                is_selected_hero_keep = True

                # Check if this plot/building is selected
                is_plot_selected = (
                    is_selected_hero_keep or
                    (self.game.selected_barracks and self.game.selected_barracks == (territory, plot_index)) or
                    (self.game.selected_keep and self.game.selected_keep == (territory, plot_index)) or
                    (self.game.selected_plot and self.game.selected_plot == (territory, plot_index))
                )

                # Draw simple border on plot surface
                pygame.draw.circle(plot_surface, COLOR_PLOT_BORDER,
                                 (scaled_plot_center_offset, scaled_plot_center_offset),
                                 scaled_empty_plot_radius, 2)

                self.game.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
                self.return_surface_to_pool(plot_surface)

                # Draw building icon PNG or fallback to letter
                # For Keep buildings, check if upgraded to Castle for icon selection
                icon_building = building
                if building == 'Keep':
                    _, display_name = self.game.game_state.get_keep_display_info(territory, plot_index)
                    if display_name == 'Castle':
                        icon_building = 'Castle'

                if icon_building in self.game.building_icons and self.game.building_icons[icon_building]:
                    building_icon = self.game.building_icons[icon_building]

                    # Scale the icon to fit within the plot circle (about 2x the circle radius)
                    icon_size = int(scaled_empty_plot_radius * 2)

                    # PERFORMANCE OPTIMIZATION: Use selective .copy() strategy
                    # Only copy cached icon when overlays needed (enemy tint/hover/click)
                    # Otherwise use cached icon directly for maximum performance
                    cached_icon = self.get_cached_scaled_building(icon_building, building_icon, icon_size)

                    # Check if we need to apply any overlays
                    needs_effects = (owner != self.game.game_state.current_player or is_clicking or is_hovering)

                    if needs_effects:
                        # Copy only when effects are needed
                        display_icon = cached_icon.copy()

                        # Apply overlays to copy (respects icon's alpha channel transparency)
                        # Grey tint for enemy buildings
                        # FPS OPTIMIZATION: Use pooled surfaces instead of creating new ones
                        if owner != self.game.game_state.current_player:
                            grey_overlay = self.get_reusable_surface(icon_size, icon_size)
                            grey_overlay.fill((128, 128, 128, 180))  # Grey overlay
                            display_icon.blit(grey_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                            self.return_surface_to_pool(grey_overlay)

                        # Hover/click brightness effects
                        if is_clicking:
                            bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                            bright_overlay.fill((100, 100, 100, 100))  # White overlay with transparency
                            display_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            self.return_surface_to_pool(bright_overlay)
                        elif is_hovering:
                            light_overlay = self.get_reusable_surface(icon_size, icon_size)
                            light_overlay.fill((50, 50, 50, 50))  # Lighter white overlay
                            display_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            self.return_surface_to_pool(light_overlay)
                    else:
                        # No effects: use cached icon directly (zero overhead)
                        display_icon = cached_icon

                    # Center and blit the final icon
                    icon_rect = display_icon.get_rect(center=(x, y))
                    self.game.screen.blit(display_icon, icon_rect)
                else:
                    # Fallback to letter if icon not available
                    letter_surface = building_letter_font.render(letter, True, WHITE)
                    letter_rect = letter_surface.get_rect(center=(x, y))
                    self.game.screen.blit(letter_surface, letter_rect)

                # Draw layered border AFTER icon: black - player color - black (thinner than army circles)
                # Get player color for the border
                player_color = self.game.game_state.get_player_color(owner)

                # Outer black border (thin)
                pygame.draw.circle(self.game.screen, BLACK, (int(x), int(y)), scaled_empty_plot_radius, 1)
                # Middle player color border (medium thickness - thinner than army circles)
                pygame.draw.circle(self.game.screen, player_color, (int(x), int(y)), scaled_empty_plot_radius - 1, 3)
                # Inner black border (thin)
                pygame.draw.circle(self.game.screen, BLACK, (int(x), int(y)), scaled_empty_plot_radius - 4, 1)

                # Draw green pulsing selection glow (same as army composition highlight)
                if is_plot_selected:
                    pulse = abs(math.sin(time.time() * 2))  # Pulse between 0 and 1
                    glow_alpha = int(100 + 100 * pulse)  # Between 100 and 200

                    # Get UI scale factor for zoom-based sizing
                    ui_scale = self.game.get_ui_scale_factor()

                    # Draw multiple glow circles for effect (scaled with zoom)
                    for i in range(3):
                        glow_radius = int((scaled_empty_plot_radius + i * 5) * ui_scale)
                        # PERFORMANCE: Use reusable surface from pool
                        glow_surface = self.get_reusable_surface(glow_radius * 2 + 10, glow_radius * 2 + 10)
                        pygame.draw.circle(glow_surface, (0, 255, 0, glow_alpha // (i + 1)),
                                         (glow_radius + 5, glow_radius + 5), glow_radius, 3)
                        self.game.screen.blit(glow_surface, (int(x) - glow_radius - 5, int(y) - glow_radius - 5))
                        self.return_surface_to_pool(glow_surface)
    
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
        
        for territory, plots in self.game.scaled_plots.items():
            owner = self.game.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue

            # PERFORMANCE OPTIMIZATION: Use cached screen positions instead of world_to_screen every frame
            screen_plots = self.get_cached_screen_plots(territory)

            for plot_index, screen_pos in enumerate(screen_plots):
                # PERFORMANCE: Skip off-screen plots (using screen coordinates now)
                if (screen_pos[0] < -100 or screen_pos[0] > self.game.screen.get_width() + 100 or
                    screen_pos[1] < -100 or screen_pos[1] > self.game.screen.get_height() + 100):
                    continue

                # Check if under construction
                under_construction = None
                if territory in self.game.game_state.under_construction:
                    under_construction = self.game.game_state.under_construction[territory].get(plot_index)

                if not under_construction:
                    continue  # Skip non-construction plots

                # Get building info (with error handling)
                try:
                    building_type = under_construction[0]  # entry is (building_type, turns_remaining, cost)
                    turns_remaining = under_construction[1]
                    building_info = self.game.game_state.building_types[building_type]
                    letter = building_info['letter']
                except (KeyError, TypeError, ValueError, IndexError) as e:
                    logger.warning(f"Invalid under_construction data in {territory}: {e}")
                    continue

                # PERFORMANCE OPTIMIZATION: Use cached screen position (already transformed)
                x, y = int(screen_pos[0]), int(screen_pos[1])

                # PERFORMANCE: Use reusable surface from pool
                plot_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)

                # Base color (yellowish for construction)
                circle_color = COLOR_CONSTRUCTION
                
                # Check for hover
                # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
                is_hovering = False
                mouse_screen_x, mouse_screen_y = self.game.mouse_pos
                distance_sq = (x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2
                if distance_sq <= scaled_empty_plot_radius ** 2:
                    is_hovering = True
                
                # Check for click flash
                is_clicking = (self.game.clicked_element and 
                              self.game.clicked_element[0] == 'plot' and 
                              self.game.clicked_element[1] == (territory, plot_index))
                
                # Apply visual feedback
                if is_clicking:
                    circle_color = brighten_color(circle_color, 0.4)
                elif is_hovering:
                    circle_color = lighten_color(circle_color, 0.2)
                
                # Draw circle
                pygame.draw.circle(plot_surface, circle_color, 
                                 (scaled_plot_center_offset, scaled_plot_center_offset), 
                                 scaled_empty_plot_radius)
                
                # Draw simple border on plot surface
                pygame.draw.circle(plot_surface, COLOR_CONSTRUCTION_BORDER,
                                 (scaled_plot_center_offset, scaled_plot_center_offset),
                                 scaled_empty_plot_radius, 2)

                self.game.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
                self.return_surface_to_pool(plot_surface)

                # Draw building icon PNG or fallback to letter
                if building_type in self.game.building_icons and self.game.building_icons[building_type]:
                    building_icon = self.game.building_icons[building_type]

                    # Scale the icon to fit within the plot circle (about 2x the circle radius)
                    icon_size = int(scaled_empty_plot_radius * 2)

                    # PERFORMANCE OPTIMIZATION (Phase 1.4): Use cached icon directly without .copy()
                    # Blit overlays to screen instead of modifying cached surface
                    cached_icon = self.get_cached_scaled_building(building_type, building_icon, icon_size)

                    # Create a temporary surface for combining icon + overlays
                    # This preserves the cache while allowing per-frame effects
                    temp_icon = self.get_reusable_surface(icon_size, icon_size)
                    temp_icon.fill((0, 0, 0, 0))  # Clear with transparency

                    # Blit cached icon to temp surface
                    temp_icon.blit(cached_icon, (0, 0))

                    # Apply grey tint if enemy building under construction
                    if owner != self.game.game_state.current_player:
                        grey_overlay = self.get_reusable_surface(icon_size, icon_size)
                        grey_overlay.fill((128, 128, 128, 180))
                        temp_icon.blit(grey_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                        self.return_surface_to_pool(grey_overlay)

                    # Apply hover/click brightness effects
                    if is_clicking:
                        bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                        bright_overlay.fill((100, 100, 100, 100))
                        temp_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                        self.return_surface_to_pool(bright_overlay)
                    elif is_hovering:
                        light_overlay = self.get_reusable_surface(icon_size, icon_size)
                        light_overlay.fill((50, 50, 50, 50))
                        temp_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                        self.return_surface_to_pool(light_overlay)

                    # Apply slight transparency to indicate construction
                    temp_icon.set_alpha(180)

                    # Blit to screen
                    icon_rect = temp_icon.get_rect(center=(x, y))
                    self.game.screen.blit(temp_icon, icon_rect)
                    self.return_surface_to_pool(temp_icon)
                else:
                    # Fallback to letter if icon not available
                    letter_surface = building_letter_font.render(letter, True, COLOR_CONSTRUCTION_TEXT)
                    letter_rect = letter_surface.get_rect(center=(x, y))
                    self.game.screen.blit(letter_surface, letter_rect)

                # Draw layered border AFTER icon: black - player color - black (thinner than army circles)
                # Get player color for the border
                player_color = self.game.game_state.get_player_color(owner)

                # Outer black border (thin)
                pygame.draw.circle(self.game.screen, BLACK, (int(x), int(y)), scaled_empty_plot_radius, 1)
                # Middle player color border (medium thickness - thinner than army circles)
                pygame.draw.circle(self.game.screen, player_color, (int(x), int(y)), scaled_empty_plot_radius - 1, 3)
                # Inner black border (thin)
                pygame.draw.circle(self.game.screen, BLACK, (int(x), int(y)), scaled_empty_plot_radius - 4, 1)

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
        
        for territory, plots in self.game.scaled_plots.items():
            owner = self.game.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue

            # PERFORMANCE OPTIMIZATION: Use cached screen positions instead of world_to_screen every frame
            screen_plots = self.get_cached_screen_plots(territory)

            for plot_index, screen_pos in enumerate(screen_plots):
                # PERFORMANCE: Skip off-screen plots (using screen coordinates now)
                if (screen_pos[0] < -100 or screen_pos[0] > self.game.screen.get_width() + 100 or
                    screen_pos[1] < -100 or screen_pos[1] > self.game.screen.get_height() + 100):
                    continue

                # Check if plot is empty
                is_empty = True

                if territory in self.game.game_state.buildings:
                    if plot_index in self.game.game_state.buildings[territory]:
                        if self.game.game_state.buildings[territory][plot_index] is not None:
                            is_empty = False

                if territory in self.game.game_state.under_construction:
                    if plot_index in self.game.game_state.under_construction[territory]:
                        is_empty = False

                if not is_empty:
                    continue  # Skip non-empty plots

                # PERFORMANCE OPTIMIZATION: Use cached screen position (already transformed)
                x, y = int(screen_pos[0]), int(screen_pos[1])

                # PERFORMANCE: Use reusable surface from pool
                plot_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)

                # Check if can build on this territory this turn
                can_build = (owner == self.game.game_state.current_player and 
                            territory not in self.game.game_state.buildings_started_this_turn)
                
                # Color: Bright green if can build, gray otherwise
                if can_build:
                    circle_color = COLOR_EMPTY_PLOT_CAN_BUILD
                else:
                    circle_color = COLOR_EMPTY_PLOT_CANNOT_BUILD
                
                # Check for hover
                # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
                is_hovering = False
                mouse_screen_x, mouse_screen_y = self.game.mouse_pos
                distance_sq = (x - mouse_screen_x) ** 2 + (y - mouse_screen_y) ** 2
                if distance_sq <= scaled_empty_plot_radius ** 2:
                    is_hovering = True
                
                # Check for click flash
                is_clicking = (self.game.clicked_element and 
                              self.game.clicked_element[0] == 'plot' and 
                              self.game.clicked_element[1] == (territory, plot_index))
                
                # Apply visual feedback
                if is_clicking:
                    circle_color = brighten_color(circle_color, 0.4)
                elif is_hovering:
                    circle_color = lighten_color(circle_color, 0.2)
                
                # Draw circle
                pygame.draw.circle(plot_surface, circle_color, 
                                 (scaled_plot_center_offset, scaled_plot_center_offset), 
                                 scaled_empty_plot_radius)
                
                # Draw simple border on plot surface
                pygame.draw.circle(plot_surface, COLOR_EMPTY_PLOT_BORDER,
                                 (scaled_plot_center_offset, scaled_plot_center_offset),
                                 scaled_empty_plot_radius, 2)

                self.game.screen.blit(plot_surface, (x - scaled_plot_center_offset, y - scaled_plot_center_offset))
                self.return_surface_to_pool(plot_surface)

                # Draw PlotIcon.png if available
                if 'Plot' in self.game.building_icons and self.game.building_icons['Plot']:
                    plot_icon = self.game.building_icons['Plot']
                    icon_size = int(scaled_empty_plot_radius * 2)
                    cached_icon = self.get_cached_scaled_plot('Plot', plot_icon, icon_size)

                    # FPS OPT: Only .copy() when effects need to modify the surface in-place
                    needs_effects = (not can_build) or is_clicking or is_hovering
                    if needs_effects:
                        scaled_plot_icon = cached_icon.copy()

                        if not can_build:
                            grey_overlay = self.get_reusable_surface(icon_size, icon_size)
                            grey_overlay.fill((128, 128, 128, 180))
                            scaled_plot_icon.blit(grey_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                            self.return_surface_to_pool(grey_overlay)

                        if is_clicking:
                            bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                            bright_overlay.fill((100, 100, 100, 100))
                            scaled_plot_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            self.return_surface_to_pool(bright_overlay)
                        elif is_hovering:
                            light_overlay = self.get_reusable_surface(icon_size, icon_size)
                            light_overlay.fill((50, 50, 50, 50))
                            scaled_plot_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            self.return_surface_to_pool(light_overlay)

                        icon_rect = scaled_plot_icon.get_rect(center=(x, y))
                        self.game.screen.blit(scaled_plot_icon, icon_rect)
                    else:
                        icon_rect = cached_icon.get_rect(center=(x, y))
                        self.game.screen.blit(cached_icon, icon_rect)

                # Draw layered border AFTER icon: black - player color - black (thinner than army circles)
                # Get player color for the border
                player_color = self.game.game_state.get_player_color(owner)

                # Outer black border (thin)
                pygame.draw.circle(self.game.screen, BLACK, (int(x), int(y)), scaled_empty_plot_radius, 1)
                # Middle player color border (medium thickness - thinner than army circles)
                pygame.draw.circle(self.game.screen, player_color, (int(x), int(y)), scaled_empty_plot_radius - 1, 3)
                # Inner black border (thin)
                pygame.draw.circle(self.game.screen, BLACK, (int(x), int(y)), scaled_empty_plot_radius - 4, 1)

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

        # MULTIPLAYER: Hide quick-access icons from spectators (non-active players)
        if self.game.multiplayer_mode and not self.game.is_local_player_active():
            return

        # Tutorial: hide quick-access icons when build/train not allowed
        if hasattr(self.game, 'tutorial_mission') and self.game.tutorial_mission and self.game.tutorial_mission.active:
            if not self.game.tutorial_mission.is_action_allowed('click_plots'):
                return

        scaled_plot_surface_size = int(PLOT_SURFACE_SIZE * ui_scale)
        scaled_plot_center_offset = scaled_plot_surface_size // 2

        # Draw quick-access building icons around selected empty plot
        if self.game.selected_plot and self.game.game_state.phase == 'playing':
            territory, plot_index = self.game.selected_plot
            if territory in self.game.scaled_plots and plot_index < len(self.game.scaled_plots[territory]):
                # PERFORMANCE OPTIMIZATION: Use cached screen positions
                screen_plots = self.get_cached_screen_plots(territory)

                # Get plot position (with error handling)
                try:
                    screen_plot_pos = screen_plots[plot_index]
                except (KeyError, IndexError, TypeError) as e:
                    logger.warning(f"Failed to get plot position for {territory}[{plot_index}]: {e}")
                    return

                # PERFORMANCE OPTIMIZATION: Use cached screen position (already transformed)
                plot_x, plot_y = int(screen_plot_pos[0]), int(screen_plot_pos[1])
                
                # Check if plot is empty
                is_empty = True
                if territory in self.game.game_state.buildings:
                    if plot_index in self.game.game_state.buildings[territory]:
                        if self.game.game_state.buildings[territory][plot_index] is not None:
                            is_empty = False
                
                if territory in self.game.game_state.under_construction:
                    if plot_index in self.game.game_state.under_construction[territory]:
                        is_empty = False
                
                # Only show building options if plot is empty
                if is_empty:
                    # FPS OPTIMIZATION: Use cached building list instead of creating list every frame
                    building_list = self.get_cached_building_list()
                    num_buildings = len(building_list)
                    
                    # Track hover for map building icons
                    mouse_pos = pygame.mouse.get_pos()
                    current_hover = None
                    
                    for i, building_name in enumerate(building_list):
                        building_info = self.game.game_state.building_types[building_name]
                        letter = building_info['letter']
                        # Use centralized cost calculation (applies all discounts: Royal Decree,
                        # Makeshift Barracks, Master Negotiator, territorial bonuses, etc.)
                        cost = self.game.game_state.get_building_cost(building_name)

                        # Calculate position around plot (in screen coordinates)
                        angle = (i / num_buildings) * 2 * math.pi - math.pi / 2  # Start at top
                        icon_x = plot_x + int(scaled_building_icon_radius * math.cos(angle))
                        icon_y = plot_y + int(scaled_building_icon_radius * math.sin(angle))
                        
                        # Check if hovering over this icon
                        # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
                        distance_to_mouse_sq = (mouse_pos[0] - icon_x) ** 2 + (mouse_pos[1] - icon_y) ** 2
                        if distance_to_mouse_sq < scaled_icon_click_radius ** 2:
                            current_hover = ('map_building', building_name)
                        
                        # Check if player can afford and if building is allowed this turn
                        current_gold = self.game.game_state.player_gold[self.game.game_state.current_player]
                        can_afford = current_gold >= cost
                        can_build_this_turn = territory not in self.game.game_state.buildings_started_this_turn
                        
                        # Check one-per-territory restrictions (Keep, Training Grounds)
                        can_build_keep = True
                        if building_name == 'Keep':
                            # Check if already has a Keep (completed or under construction)
                            if self.game.game_state.has_fortress(territory):
                                can_build_keep = False
                            # Check if Keep is under construction
                            if territory in self.game.game_state.under_construction:
                                for plot_idx, entry in self.game.game_state.under_construction[territory].items():
                                    if entry[0] == 'Keep':  # entry is (building_type, turns_remaining, cost)
                                        can_build_keep = False
                                        break
                        elif building_name == 'Training Grounds':
                            # Check if already has Training Grounds (completed or under construction)
                            if self.game.game_state.has_training_grounds(territory):
                                can_build_keep = False
                            if territory in self.game.game_state.under_construction:
                                for plot_idx, entry in self.game.game_state.under_construction[territory].items():
                                    if entry[0] == 'Training Grounds':
                                        can_build_keep = False
                                        break
                        
                        # Tutorial lock: force red if building type not allowed
                        _tutorial_locked = False
                        if hasattr(self.game, 'tutorial_mission') and self.game.tutorial_mission and self.game.tutorial_mission.active:
                            _tutorial_locked = not self.game.tutorial_mission.is_action_allowed('build', building_type=building_name)

                        # Base color - consider affordability, building limit, and one-per-territory restriction
                        if _tutorial_locked:
                            icon_color = COLOR_ICON_UNAVAILABLE  # Red (tutorial locked)
                        elif can_afford and can_build_this_turn and can_build_keep:
                            icon_color = COLOR_ICON_AVAILABLE  # Green
                        else:
                            icon_color = COLOR_ICON_UNAVAILABLE  # Red
                        
                        # Check for hover
                        is_hovering = (distance_to_mouse_sq < scaled_icon_click_radius ** 2)
                        
                        # Check for click flash
                        is_clicking = (self.game.clicked_element and 
                                      self.game.clicked_element[0] == 'map_building' and 
                                      self.game.clicked_element[1] == building_name)
                        
                        # Apply visual feedback
                        if is_clicking:
                            icon_color = brighten_color(icon_color, 0.4)
                        elif is_hovering:
                            icon_color = lighten_color(icon_color, 0.2)
                        
                        # Draw background
                        # PERFORMANCE: Use reusable surface from pool
                        icon_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)
                        pygame.draw.circle(icon_surface, icon_color,
                                         (scaled_plot_center_offset, scaled_plot_center_offset),
                                         scaled_icon_click_radius)
                        pygame.draw.circle(icon_surface, COLOR_ICON_BORDER,
                                         (scaled_plot_center_offset, scaled_plot_center_offset),
                                         scaled_icon_click_radius, 2)
                        self.game.screen.blit(icon_surface, (icon_x - scaled_plot_center_offset, icon_y - scaled_plot_center_offset))
                        self.return_surface_to_pool(icon_surface)

                        # Draw building icon PNG or fallback to letter
                        if building_name in self.game.building_icons and self.game.building_icons[building_name]:
                            building_icon = self.game.building_icons[building_name]

                            # Scale the icon to fit within the click radius (about 2x the radius)
                            icon_size = int(scaled_icon_click_radius * 1.8)

                            # PERFORMANCE OPTIMIZATION (Phase 1.4): Use cached icon directly without .copy()
                            cached_icon = self.get_cached_scaled_building(building_name, building_icon, icon_size)

                            # Create temp surface for combining icon + overlays
                            temp_icon = self.get_reusable_surface(icon_size, icon_size)
                            temp_icon.fill((0, 0, 0, 0))
                            temp_icon.blit(cached_icon, (0, 0))

                            # Apply red tint if building is unavailable (including tutorial lock)
                            if _tutorial_locked or not (can_afford and can_build_this_turn and can_build_keep):
                                red_overlay = self.get_reusable_surface(icon_size, icon_size)
                                red_overlay.fill((255, 100, 100, 100))
                                temp_icon.blit(red_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                                self.return_surface_to_pool(red_overlay)

                            # Apply hover/click brightness effects
                            if is_clicking:
                                bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                                bright_overlay.fill((100, 100, 100, 100))
                                temp_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                                self.return_surface_to_pool(bright_overlay)
                            elif is_hovering:
                                light_overlay = self.get_reusable_surface(icon_size, icon_size)
                                light_overlay.fill((50, 50, 50, 50))
                                temp_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                                self.return_surface_to_pool(light_overlay)

                            # Blit to screen
                            icon_rect = temp_icon.get_rect(center=(icon_x, icon_y))
                            self.game.screen.blit(temp_icon, icon_rect)
                            self.return_surface_to_pool(temp_icon)
                        else:
                            # Fallback to letter if icon not available
                            letter_surface = icon_letter_font.render(letter, True, WHITE)
                            letter_rect = letter_surface.get_rect(center=(icon_x, icon_y))
                            self.game.screen.blit(letter_surface, letter_rect)
                    
                    # Update hover tracking
                    self.game.update_button_hover(current_hover, 'map_building')
                else:
                    # Plot not empty - clear map building hover if that's what was set
                    if self.game.hover_target_button and self.game.hover_target_button[0] == 'map_building':
                        self.game.hover_target_button = None
                        self.game.show_tooltip_button = None
                        self.game.hover_start_time_button = None
        
        # Draw quick-access training icons around selected Barracks
        if self.game.selected_barracks and self.game.game_state.phase == 'playing':
            territory, barracks_plot_index = self.game.selected_barracks
            if territory in self.game.scaled_plots and barracks_plot_index < len(self.game.scaled_plots[territory]):
                # PERFORMANCE OPTIMIZATION: Use cached screen positions
                screen_plots = self.get_cached_screen_plots(territory)

                # Get Barracks position (with error handling)
                try:
                    screen_barracks_pos = screen_plots[barracks_plot_index]
                except (KeyError, IndexError, TypeError) as e:
                    logger.warning(f"Failed to get Barracks position for {territory}[{barracks_plot_index}]: {e}")
                    return

                # PERFORMANCE OPTIMIZATION: Use cached screen position (already transformed)
                plot_x, plot_y = int(screen_barracks_pos[0]), int(screen_barracks_pos[1])
                
                # Draw training icons in a circle around the Barracks
                unit_types = ['Swordsman', 'Archer', 'Pikeman', 'Cavalry', 'Captain']
                num_units = len(unit_types)
                
                # Get current gold and check conditions
                current_gold = self.game.game_state.player_gold[self.game.game_state.current_player]
                # IMPORTANT: Use total armies (all garrisons) for army limit check
                current_armies = self.game.game_state.get_territory_total_armies(territory)
                at_army_limit = current_armies >= self.game.game_state.MAX_ARMIES_PER_TERRITORY
                
                # Get current queue
                queue_count = 0
                if (territory in self.game.game_state.training_queue and 
                    barracks_plot_index in self.game.game_state.training_queue[territory]):
                    queue_count = len(self.game.game_state.training_queue[territory][barracks_plot_index])
                can_queue = queue_count < 5
                
                # Track hover for map training icons
                mouse_pos = pygame.mouse.get_pos()
                current_hover = None
                
                for i, unit_type in enumerate(unit_types):
                    unit_info = self.game.game_state.UNIT_TYPES[unit_type]
                    letter = unit_info['letter']
                    # Use centralized cost calculation (applies all discounts: Improved Training,
                    # Animal Handling, territorial bonuses, etc.)
                    cost = self.game.game_state.get_effective_cost(unit_type, unit_info['cost'])

                    # Calculate position around Barracks (in screen coordinates)
                    angle = (i / num_units) * 2 * math.pi - math.pi / 2  # Start at top
                    icon_x = plot_x + int(scaled_building_icon_radius * math.cos(angle))
                    icon_y = plot_y + int(scaled_building_icon_radius * math.sin(angle))

                    # Check if hovering over this icon
                    # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
                    distance_to_mouse_sq = (mouse_pos[0] - icon_x) ** 2 + (mouse_pos[1] - icon_y) ** 2
                    if distance_to_mouse_sq < scaled_icon_click_radius ** 2:
                        current_hover = ('map_training', unit_type)

                    # Tutorial lock: force unavailable if unit type not allowed
                    _tutorial_locked = False
                    if hasattr(self.game, 'tutorial_mission') and self.game.tutorial_mission and self.game.tutorial_mission.active:
                        _tutorial_locked = not self.game.tutorial_mission.is_action_allowed('train', unit_type=unit_type)

                    # Check if player can afford and can train
                    can_afford = current_gold >= cost
                    can_train = can_afford and can_queue and not at_army_limit and not _tutorial_locked

                    # Check for hover
                    is_hovering = (distance_to_mouse_sq < scaled_icon_click_radius ** 2)

                    # Check for click flash
                    is_clicking = (self.game.clicked_element and
                                  self.game.clicked_element[0] == 'map_training' and
                                  self.game.clicked_element[1] == unit_type)

                    # Draw unit icon PNG or fallback to letter
                    unit_icon = self.game.unit_icons.get(unit_type)

                    if unit_icon:
                        # Use PNG icon
                        icon_size = scaled_icon_click_radius * 2  # Full diameter

                        # FPS OPT: Cache the cropped-to-circle result (avoids crop_to_circle + .copy() every frame)
                        crop_cache_key = (unit_type, int(icon_size))
                        if crop_cache_key not in self._cropped_circle_cache:
                            from rendering.helpers import DrawingHelpers
                            base = self.get_cached_scaled_unit(unit_type, unit_icon, int(icon_size))
                            self._cropped_circle_cache[crop_cache_key] = DrawingHelpers.crop_to_circle(base.copy())
                        cached_cropped = self._cropped_circle_cache[crop_cache_key]

                        # Only .copy() when effects need to modify in-place
                        needs_effects = (not can_train) or is_clicking or is_hovering
                        scaled_icon = cached_cropped.copy() if needs_effects else cached_cropped

                        # Apply red tint if cannot train (only affects RGB, not alpha)
                        if not can_train:
                            # PERFORMANCE: Use reusable surface from pool
                            red_overlay = self.get_reusable_surface(icon_size, icon_size)
                            red_overlay.fill((255, 100, 100, 128))
                            scaled_icon.blit(red_overlay, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
                            self.return_surface_to_pool(red_overlay)

                        # Apply hover/click brightness effects
                        if is_clicking:
                            # PERFORMANCE: Use reusable surface from pool
                            bright_overlay = self.get_reusable_surface(icon_size, icon_size)
                            bright_overlay.fill((100, 100, 100, 100))
                            scaled_icon.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            self.return_surface_to_pool(bright_overlay)
                        elif is_hovering:
                            # PERFORMANCE: Use reusable surface from pool
                            light_overlay = self.get_reusable_surface(icon_size, icon_size)
                            light_overlay.fill((50, 50, 50, 50))
                            scaled_icon.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
                            self.return_surface_to_pool(light_overlay)

                        # Center the icon
                        icon_rect = scaled_icon.get_rect(center=(icon_x, icon_y))
                        self.game.screen.blit(scaled_icon, icon_rect)

                        # Draw circle border frame overlay if available
                        if self.game.circle_border:
                            # Get cached scaled border (PERFORMANCE: cached to avoid expensive scaling)
                            scaled_border = self.get_cached_scaled_border(self.game.circle_border, int(icon_size))
                            border_rect = scaled_border.get_rect(center=(icon_x, icon_y))
                            self.game.screen.blit(scaled_border, border_rect)
                    else:
                        # Fallback to letter with circle background if icon not available
                        icon_color = COLOR_ICON_AVAILABLE if can_train else COLOR_ICON_UNAVAILABLE
                        if is_clicking:
                            icon_color = brighten_color(icon_color, 0.4)
                        elif is_hovering:
                            icon_color = lighten_color(icon_color, 0.2)

                        # PERFORMANCE: Use reusable surface from pool
                        icon_surface = self.get_reusable_surface(scaled_plot_surface_size, scaled_plot_surface_size)
                        pygame.draw.circle(icon_surface, icon_color,
                                         (scaled_plot_center_offset, scaled_plot_center_offset),
                                         scaled_icon_click_radius)
                        pygame.draw.circle(icon_surface, COLOR_ICON_BORDER,
                                         (scaled_plot_center_offset, scaled_plot_center_offset),
                                         scaled_icon_click_radius, 2)
                        self.game.screen.blit(icon_surface, (icon_x - scaled_plot_center_offset, icon_y - scaled_plot_center_offset))
                        self.return_surface_to_pool(icon_surface)

                        letter_surface = icon_letter_font.render(letter, True, WHITE)
                        letter_rect = letter_surface.get_rect(center=(icon_x, icon_y))
                        self.game.screen.blit(letter_surface, letter_rect)
                
                # Update hover tracking
                self.game.update_button_hover(current_hover, 'map_training')

            # Hero training icons removed - too cluttered on map with 8 heroes
            # Heroes are trained from Keep UI only

    def draw_plots_original(self):
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
        if self.game.game_state.phase != 'playing':
            return
        
        # Calculate UI scale factor based on zoom (1.0 at min zoom, 1.5 at max zoom)
        ui_scale = self.game.get_ui_scale_factor()
        
        # Calculate scaled sizes for UI elements
        scaled_empty_plot_radius = int(EMPTY_PLOT_RADIUS * ui_scale)
        scaled_building_icon_radius = int(BUILDING_ICON_RADIUS * ui_scale)
        scaled_icon_click_radius = int(ICON_CLICK_RADIUS * ui_scale)
        
        # PERFORMANCE OPTIMIZATION: Use cached fonts instead of creating new Font objects every frame
        # Calculate fonts for building letters and icon letters
        building_letter_font_size = int(scaled_empty_plot_radius * 1.2)
        building_letter_font = self.get_cached_font(building_letter_font_size)

        icon_letter_font_size = int(scaled_icon_click_radius * 1.2)
        icon_letter_font = self.get_cached_font(icon_letter_font_size)
        
        # FPS OPTIMIZATION Phase 3.1: Combine 3 plot iterations into 1 unified loop
        # Old: 4 separate methods, each iterating all territories and plots (624 plot lookups/frame)
        # New: 1 unified loop that classifies and renders each plot in a single pass
        # Quick-access icons remain separate (only rendered when plot/barracks selected)
        self._draw_all_plots_unified(ui_scale, scaled_empty_plot_radius, building_letter_font)
        self._draw_quick_access_icons(ui_scale, scaled_building_icon_radius,
                                      scaled_icon_click_radius, icon_letter_font)