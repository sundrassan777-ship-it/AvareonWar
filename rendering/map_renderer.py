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
from ui.effects.production_glow_effect import ProductionGlowEffect, ProductionRays
from ui.effects.construction_dust_effect import ConstructionDust, VARIANT_BUILD, VARIANT_UPGRADE
from ui.effects.plot_fx_style import get_plot_fx_style, plot_phase
from ui.effects.hero_fx_style import get_hero_fx_style
from ui.effects.hero_fx_effect import HeroLight, HeroAura, HeroAbilityEffect, FxView, stable_seed
from ui.effects.order_fx_style import get_order_fx_style
from ui.effects.order_fx_effect import OrderLight, OrderArrow
from ui.effects.marker_fx_style import get_marker_fx_style
from ui.effects.marker_fx_effect import MarkerLight, MarkerState

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

    # Thin ink outline around every territory on maps with "draw_borders" in the
    # manifest (see map_data.current_map_draws_borders). RGBA; the width is
    # camera_zoom * this factor, at least 1 px (1 px at the default zoom).
    TERRITORY_BORDER_COLOR = (35, 25, 15, 170)
    TERRITORY_BORDER_WIDTH_PER_ZOOM = 0.5
    
    def __init__(self, game_instance):
        """
        Initialize map renderer with game instance.

        Args:
            game_instance: Reference to Game instance for state access
        """
        self.game = game_instance
        # The battle markers on the map: {territory: MarkerState}
        self.battle_effects = {}
        # The alliance arrival markers (simultaneous mode, allied armies arriving at
        # the same territory): {territory: MarkerState}
        self.alliance_effects = {}
        self._marker_labels = {}         # "#N" -> (shadow, label) surfaces
        # Dictionary to store active production glow effects: {(territory, plot_index): ProductionGlowEffect}
        # Tracks Barracks with units in training queue, and Keep/Castle with hero in training
        self.production_glow_effects = {}
        self._production_glow_version = -1  # FPS OPT: Track training version for dirty check
        # Persistent plot effects (production light rays, construction dust): one
        # shared clock, advanced by update_plot_effects() in the main loop's update
        # section (so it stops while the game is paused), and shared renderers styled
        # by the map look - both looks share one style today, ui/effects/plot_fx_style.py
        self._plot_fx_clock = 0.0
        self._plot_fx_style = get_plot_fx_style(map_data.get_current_look())
        self._plot_phases = {}   # (territory, plot_index) -> stable animation offset
        # Hero ability effects as light (ui/effects/hero_fx_effect.py): one shared
        # renderer, the passive auras of the selected hero and the Embargo embers,
        # both synced from game state (see update_hero_effects)
        self._hero_fx_style = get_hero_fx_style(map_data.get_current_look())
        self._hero_aura_sync = None      # what the aura territories were computed for
        self._embargo_sync = None        # what the ember territories were computed for
        # The selection ring, order arrows and destination reticles as light
        # (ui/effects/order_fx_effect.py), drawn from the same clock
        self._order_fx_style = get_order_fx_style(map_data.get_current_look())
        # Battle and alliance markers and the army overflow warning as light
        # (ui/effects/marker_fx_effect.py), drawn from the same clock
        self._marker_fx_style = get_marker_fx_style(map_data.get_current_look())
        self._build_plot_fx_renderers()
        # Active hero ability casts (HeroAbilityEffect), drawn in two layers
        self.ability_effects = []
        self._ability_casts = 0          # makes each cast's random parts differ

        # Image caching system to avoid expensive transformations every frame
        # FPS OPT: Static glow circles replace old rotating ring system
        # Cache pre-rendered glow surfaces: key = (color, radius_rounded)
        self.static_glow_cache = {}
        # Cache scaled flag images: key = (player, tier, width, height)
        self.scaled_flag_cache = {}
        # Cache scaled building icons: key = (building_type, size)
        self.scaled_building_cache = {}
        # Grey-tinted variants for buildings not owned by the viewing player.
        # Keyed the same way (building_type, size) — see get_cached_greyed_building().
        self.greyed_building_cache = {}
        # Pre-rendered 3-ring plot borders, keyed by (radius, player_color).
        self._plot_chrome_cache = {}
        self._PLOT_CHROME_CACHE_MAX = 64
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
        # FPS OPT: cache for draw_territory_overlay(), which previously allocated a
        # fresh surface and re-filled the polygon on every call — including every
        # frame of a campaign/tutorial highlight's alpha pulse.
        # Keyed by (territory, camera_state, color, quantized_alpha, outline).
        self._territory_overlay_cache = {}
        self._TERRITORY_OVERLAY_CACHE_MAX = 64
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

    def rebuild_scale_caches(self):
        """
        Rebuild the caches derived from game.scaled_polygons after the map scale changes.

        BUG FIX: `territory_bounding_boxes` and `multi_zoom_cache` are built once in
        __init__ from the polygons as scaled at that moment. `apply_display_settings()`
        re-derives `scale_factor` and re-rounds every polygon on a resolution change,
        but never rebuilt these — so afterwards they still held the OLD scale
        (0.163 at 1280x720 vs 0.211 at 1600x900 vs 0.256 at 1920x1080, a 57% swing).
        That left territory polygons misaligned with the map background, and stale
        bounding boxes made culling and AABB hit-testing wrong.

        Map switching was never affected: MapRenderer is constructed inside
        initialize_game(), which calls _reload_map_assets() first.

        Call this from any path that changes `game.scaled_polygons` after construction.
        """
        self.territory_bounding_boxes = {}
        self._precompute_territory_bounding_boxes()
        self.multi_zoom_cache = {}
        self._precompute_multi_zoom_polygons()

        # Anything derived from the old screen projection is now invalid
        self.cached_screen_polygons = {}
        self.cached_screen_plots = {}
        self.last_camera_state = None
        self._overlay_cache_surface = None
        self._overlay_cache_camera = None
        self._hover_surface = None
        self._last_hover_territory = None
        self._last_hover_camera_state = None
        self._territory_overlay_cache = {}
        # Plot effect frames were converted to the old display format; rebuild them
        # (~5 ms). Production effects themselves look their plots up every frame, so
        # they already follow the new scale.
        self._build_plot_fx_renderers()

    def _build_plot_fx_renderers(self):
        """
        (Re)create the shared plot and hero effect renderers and pre-build their
        bases (their frames carry the display format and the map scale).
        """
        self.production_rays = ProductionRays(self._plot_fx_style['rays'])
        self.production_rays.prewarm(self._plot_radius_range())
        self.construction_dust = ConstructionDust(self._plot_fx_style['dust'])
        self.hero_light = HeroLight(self.game.scaled_polygons, self._hero_fx_style)
        self.hero_light.prewarm(self._plot_radius_range())
        self.hero_auras = {key: HeroAura(self.hero_light, key) for key in self._hero_fx_style['auras']}
        self.embargo_embers = HeroAura(self.hero_light, 'embargo')
        self._hero_aura_sync = None
        self._embargo_sync = None
        self.order_light = OrderLight(self._order_fx_style)
        self.order_light.prewarm(self._plot_radius_range())
        self.marker_light = MarkerLight(self._marker_fx_style)
        self.marker_light.prewarm(self._plot_radius_range())

    def _plot_phase(self, territory, plot_index):
        """A plot's stable animation offset (plot_fx_style.plot_phase), cached."""
        key = (territory, plot_index)
        phase = self._plot_phases.get(key)
        if phase is None:
            phase = self._plot_phases[key] = plot_phase(territory, plot_index)
        return phase

    def _plot_radius(self, ui_scale=None):
        """
        The on-screen plot radius in px, as draw_plots_original() draws it. Plot
        effects are sized by this (not camera_zoom), so they always match the plot.
        """
        if ui_scale is None:
            ui_scale = self.game.get_ui_scale_factor()
        return int(EMPTY_PLOT_RADIUS * ui_scale)

    @staticmethod
    def _plot_radius_range():
        """Every plot radius the zoom range gives (ui_scale is 1.0 - 1.5,
        CameraHandler.get_ui_scale_factor)."""
        return range(int(EMPTY_PLOT_RADIUS * 1.0), int(EMPTY_PLOT_RADIUS * 1.5) + 1)

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
        # Smaller circle, shifted up so the flag pole sits inside it.
        # SHARED with hit-testing via Game.get_army_circle_hit() - keep in sync.
        draw_radius = int(radius * ARMY_CIRCLE_DRAW_SCALE)
        draw_y = y - int(radius * ARMY_CIRCLE_DRAW_LIFT)

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

    def _blit_plot_chrome(self, x, y, radius, player_color):
        """
        Draw the three-ring border around a completed plot, from a cached surface.

        FPS OPT: this was three `pygame.draw.circle` calls per completed plot, every
        frame (~0.87ms for 228 plots). The rings depend only on (radius, colour), so
        they are pre-rendered once per combination and blitted.
        """
        cache_key = (radius, player_color)
        chrome = self._plot_chrome_cache.get(cache_key)
        if chrome is None:
            size = radius * 2 + 2
            centre = size // 2
            chrome = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(chrome, BLACK, (centre, centre), radius, 1)
            pygame.draw.circle(chrome, player_color, (centre, centre), radius - 1, 3)
            pygame.draw.circle(chrome, BLACK, (centre, centre), radius - 4, 1)
            if len(self._plot_chrome_cache) > self._PLOT_CHROME_CACHE_MAX:
                self._plot_chrome_cache.clear()
            self._plot_chrome_cache[cache_key] = chrome

        self.game.screen.blit(chrome, chrome.get_rect(center=(x, y)))

    def get_cached_greyed_building(self, building_type, building_icon, size):
        """
        Get the GREYED (not-owned-by-viewer) variant of a scaled building icon.

        FPS OPT: `_render_completed_plot` used to build this per plot, per frame —
        `cached_icon.copy()` plus a pooled overlay fill plus a BLEND_RGBA_MULT blit.
        On a crowded map most buildings belong to someone else, so that ran for
        nearly every visible building every frame. The result depends only on
        (building_type, size), so it caches exactly like the plain scaled icon.

        Args:
            building_type: Type of building (e.g. 'Farm', 'Barracks')
            building_icon: The unscaled source icon
            size: Target size (width and height)

        Returns:
            Scaled, grey-tinted building surface
        """
        cache_key = (building_type, size)

        if cache_key in self.greyed_building_cache:
            return self.greyed_building_cache[cache_key]

        base = self.get_cached_scaled_building(building_type, building_icon, size)
        greyed = base.copy()
        grey_overlay = pygame.Surface((size, size), pygame.SRCALPHA)
        grey_overlay.fill((128, 128, 128, 180))
        greyed.blit(grey_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.greyed_building_cache[cache_key] = greyed
        return greyed

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

        # FPS OPT: this had NO cache at all — it allocated a fresh SRCALPHA surface
        # and re-filled a 455-1027 point polygon on EVERY call. Campaign/tutorial
        # highlight steps call it every frame with a pulsing alpha, so it ran
        # continuously for the whole highlight. Quantizing the alpha to 16 steps
        # makes the result cacheable with no visible change to the pulse.
        quantized_alpha = (int(alpha) // 16) * 16
        camera_state = (self.game.camera_offset[0], self.game.camera_offset[1],
                        self.game.camera_zoom)
        cache_key = (territory, camera_state, tuple(color), quantized_alpha, bool(outline))

        cached = self._territory_overlay_cache.get(cache_key)
        if cached is None:
            border_width = max(1, int(1.5 * self.game.camera_zoom)) if outline else 0
            margin = border_width + 2
            xs = [p[0] for p in screen_polygon]
            ys = [p[1] for p in screen_polygon]
            bbox_x = max(0, int(min(xs) - margin))
            bbox_y = max(0, int(min(ys) - margin))
            # Cap to the screen as well as flooring at 1 — an unclamped bbox grows
            # with zoom squared and can be far larger than the visible area.
            screen_w = self.game.screen.get_width()
            screen_h = self.game.screen.get_height()
            bbox_w = max(1, min(int(max(xs) - min(xs) + margin * 2), screen_w - bbox_x))
            bbox_h = max(1, min(int(max(ys) - min(ys) + margin * 2), screen_h - bbox_y))

            # Small SRCALPHA surface (supports mixed alphas for fill + outline)
            overlay = pygame.Surface((bbox_w, bbox_h), pygame.SRCALPHA)
            local_polygon = [(p[0] - bbox_x, p[1] - bbox_y) for p in screen_polygon]

            pygame.draw.polygon(overlay, (*color, quantized_alpha), local_polygon)
            if outline:
                pygame.draw.lines(overlay, (*color, 255), True, local_polygon, border_width)

            # Bounded: the camera_state in the key means entries die on every camera
            # move, so clear wholesale rather than growing without limit.
            if len(self._territory_overlay_cache) > self._TERRITORY_OVERLAY_CACHE_MAX:
                self._territory_overlay_cache.clear()
            cached = (overlay, (bbox_x, bbox_y))
            self._territory_overlay_cache[cache_key] = cached

        self.game.screen.blit(cached[0], cached[1])
    def draw_territories(self):
        """Draw territory overlays, markers and ownership colors"""
        # Once per frame, before any selection ring, reticle, order arrow or marker
        self.order_light.begin_frame()
        self.marker_light.begin_frame()
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

            # Maps whose art has faint borders (manifest "draw_borders") get a thin
            # ink outline on every territory. Drawn into this cached overlay, so it
            # costs nothing on static frames; width scales with zoom like the
            # hover/selection outlines.
            draw_borders = map_data.current_map_draws_borders()
            border_polygons = []

            for territory in self.game.scaled_polygons.keys():
                # Skip disabled territories (campaign mission filtering)
                if not map_data.is_territory_enabled(territory):
                    continue
                # PERFORMANCE: Skip off-screen territories
                if not self.is_territory_on_screen(territory):
                    continue

                owner = self.game.game_state.territory_owners.get(territory, -1)
                screen_polygon = self.get_cached_screen_polygon(territory)
                if not screen_polygon:
                    continue

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

                    pygame.draw.polygon(self.fullscreen_overlay, (*color, 80), screen_polygon)
                else:
                    # Unowned territory: fill + stronger border to distinguish from non-territory areas
                    pygame.draw.polygon(self.fullscreen_overlay, (200, 200, 200, 45), screen_polygon)
                    if not draw_borders:  # Bordered maps outline every territory below instead
                        pygame.draw.lines(self.fullscreen_overlay, (220, 220, 220, 120), True, screen_polygon, 1)

                if draw_borders:
                    border_polygons.append(screen_polygon)

            # Borders after ALL fills, so a neighbour's fill never half-covers a shared edge
            if border_polygons:
                border_width = max(1, int(self.game.camera_zoom * self.TERRITORY_BORDER_WIDTH_PER_ZOOM))
                for screen_polygon in border_polygons:
                    pygame.draw.lines(self.fullscreen_overlay, self.TERRITORY_BORDER_COLOR, True,
                                      screen_polygon, border_width)

            # Store cache state.
            # FPS OPT: reference, not .copy(). This used to copy the whole
            # SRCALPHA overlay (5.76MB at 1600x900) on EVERY camera delta — i.e.
            # every frame while panning or zooming — purely so the cached content
            # would survive the next rebuild's fill(). But `fullscreen_overlay` is
            # written nowhere else (it is filled and redrawn only inside this
            # block), so the cache can simply alias it: on a hit we blit the
            # surface untouched since the last rebuild, and on a miss we refill it.
            self._overlay_cache_surface = self.fullscreen_overlay
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

                    # Clamp to screen bounds. FPS OPT: the width/height were
                    # previously only floored at 1, never capped to the screen, so a
                    # large territory at high zoom allocated a surface far bigger than
                    # anything visible (~1000x1000 = 4MB at zoom 4) — and this runs on
                    # every camera delta. Off-screen parts cannot be seen anyway, and
                    # pygame clips the polygon draw to the surface.
                    screen_w = self.game.screen.get_width()
                    screen_h = self.game.screen.get_height()
                    bbox_x = max(0, int(bbox_x))
                    bbox_y = max(0, int(bbox_y))
                    bbox_w = max(1, min(int(bbox_w), screen_w - bbox_x))
                    bbox_h = max(1, min(int(bbox_h), screen_h - bbox_y))

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

        # Tutorial / campaign target territory: a faint gold wash (cached: a steady
        # alpha); the gold light running round its border is drawn under the plots
        # (render_hero_effects_under -> _draw_objective_rim)
        objective = self._objective_territory()
        if objective:
            style = self._order_fx_style['objective']
            self.draw_territory_overlay(objective, style['colour'], alpha=style['fill_alpha'])

        # Fifth pass: Draw building plots and their icons FIRST
        # Plots drawn before armies so army flags appear on top!
        # Draw production glow effects BEFORE plots (so glow appears behind building icons)
        # Hero auras and Embargo embers under the plots, like the production rays
        self.render_hero_effects_under()
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

            # Count flag slots via the shared helper, so the drawn layout and the
            # click/hover hit boxes can never disagree. Passes the per-frame
            # animation index to keep the O(1) lookup.
            num_garrisons = self.game.get_effective_garrison_count(
                territory, garrisons,
                incoming_animations_by_territory.get(territory, set())
            )

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

                # The selection ring round the drawn army circle (SHARED constants),
                # under the circle and banner
                circle_radius = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)
                circle_y_offset = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT)
                self.order_light.draw_selection(self._hero_fx_view(), glow_x, glow_y - circle_y_offset,
                                                circle_radius, self._plot_fx_clock)

            # Draw the destination reticle of the selected army's orders
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
                        # The reticle round the army circle the arrow points at, in the
                        # order kind's colour (attack / own / ally, as the arrow and card)
                        kind = self.game.game_state.order_kind(order.player, territory)
                        circle_radius = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)
                        circle_y_offset = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT)
                        self.order_light.draw_reticle(self._hero_fx_view(), x, y - circle_y_offset, circle_radius,
                                                      kind, self._plot_fx_clock)
                        break

            # PERFORMANCE: Use cached ui_scale (pre-computed above)
            # Removed redundant: ui_scale = self.game.get_ui_scale_factor()

            # Apply zoom-based scaling to army circles
            scaled_army_radius = int(ARMY_CIRCLE_RADIUS * ui_scale)
            
            # Base color
            army_color = color
            
            # Resolve which player actually holds this territory's single garrison
            # (not necessarily the territory owner). HOISTED above the hover test
            # because the banner hit test needs it; reuses garrison_army_counts
            # instead of re-reading the garrison dicts.
            garrison_player = None
            for player_index, count in garrison_army_counts.items():
                if count > 0:
                    garrison_player = player_index
                    break
            if garrison_player is None:
                garrison_player = owner

            # Check for hover (using screen position)
            # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
            is_hovering = False
            mouse_screen_x, mouse_screen_y = self.game.mouse_pos
            if self.game.point_in_army_circle(mouse_screen_x, mouse_screen_y,
                                              x, y, space='screen'):
                is_hovering = True
            elif num_garrisons <= 1:
                # Banner is a hover target too, so the ring brightens anywhere the
                # banner is clickable. Only runs when the circle test missed; costs
                # a dict lookup plus two Surface attribute reads.
                is_hovering = self.game.point_in_army_banner(
                    mouse_screen_x, mouse_screen_y, x, y,
                    garrison_player, total_armies, space='screen'
                )
            
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

                    # Get flag position for this garrison (world coords).
                    # Bounds-check like the selected-garrison path above does: the index
                    # is stored per garrison and the ring shrinks when one leaves, so a
                    # stale index would raise IndexError mid-frame and kill the game.
                    if (not flag_positions
                            or garrison_position_idx >= len(flag_positions)):
                        logger.warning(
                            "Garrison position %s out of range for %s (%s flag positions)",
                            garrison_position_idx, territory, len(flag_positions or []))
                        continue
                    flag_world_x, flag_world_y = flag_positions[garrison_position_idx]
                    flag_screen_x, flag_screen_y = self.game.world_to_screen((flag_world_x, flag_world_y))

                    # Draw rotating ring for this garrison at flag position
                    garrison_color = self.game.game_state.get_player_color(player_index)

                    # Determine flag tier based on this garrison's army count.
                    # HOISTED above the hover test because the banner hit test needs it.
                    flag_tier = self.game.get_army_flag_tier(garrison_armies)

                    # Check for hover/click on this specific garrison
                    # PHASE 2 OPTIMIZATION: Use distance squared to avoid expensive sqrt
                    garrison_is_hovering = False
                    if self.game.point_in_army_circle(mouse_screen_x, mouse_screen_y,
                                                      flag_screen_x, flag_screen_y,
                                                      space='screen'):
                        garrison_is_hovering = True
                    else:
                        # This garrison's banner is a hover target too. Each garrison in
                        # an allied-reinforced territory gets its own banner, so the
                        # highlight follows whichever banner the cursor is actually over.
                        garrison_is_hovering = self.game.point_in_army_banner(
                            mouse_screen_x, mouse_screen_y,
                            flag_screen_x, flag_screen_y,
                            player_index, garrison_armies, space='screen'
                        )

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

                    # Get the appropriate flag icon for this player and tier
                    if player_index in self.game.army_flag_icons and flag_tier in self.game.army_flag_icons[player_index]:
                        flag_icon = self.game.army_flag_icons[player_index][flag_tier]

                        if flag_icon:
                            # Geometry from the SHARED helper - identical rectangle to the
                            # one the click and hover passes test against.
                            banner = self.game.get_army_banner_rect(
                                flag_screen_x, flag_screen_y,
                                player_index, garrison_armies, space='screen'
                            )
                            banner_left, banner_top, flag_width, flag_height = banner

                            # Get cached scaled flag (PERFORMANCE: cached to avoid expensive scaling)
                            scaled_flag = self.get_cached_scaled_flag(
                                player_index, flag_tier, flag_icon,
                                int(flag_width), int(flag_height)
                            )
                            self.game.screen.blit(scaled_flag, (int(banner_left), int(banner_top)))

            else:
                # SINGLE GARRISON: Draw one flag at territory center
                # (garrison_player was resolved above, before the hover test)

                # Determine which flag tier to use based on army count
                flag_tier = self.game.get_army_flag_tier(total_armies)

                # Get the appropriate flag icon for this player and tier
                if garrison_player in self.game.army_flag_icons and flag_tier in self.game.army_flag_icons[garrison_player]:
                    flag_icon = self.game.army_flag_icons[garrison_player][flag_tier]

                    if flag_icon:
                        # Geometry comes from the SHARED helper so the drawn banner and
                        # the click/hover hit box are the same rectangle by construction.
                        # Pole base sits on the circle anchor; banner extends upward.
                        banner = self.game.get_army_banner_rect(
                            x, y, garrison_player, total_armies, space='screen'
                        )
                        banner_left, banner_top, flag_width, flag_height = banner

                        # Get cached scaled flag (PERFORMANCE: cached to avoid expensive scaling)
                        scaled_flag = self.get_cached_scaled_flag(
                            garrison_player, flag_tier, flag_icon,
                            int(flag_width), int(flag_height)
                        )
                        self.game.screen.blit(scaled_flag, (int(banner_left), int(banner_top)))
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
                        # Scale the flag (in-transit armies are not selectable)
                        flag_height = int(scaled_army_radius * ARMY_FLAG_HEIGHT_RATIO)
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
        """Draw the arrows of planned movement orders, as light (OrderLight.draw_arrows).

        One arrow per route (from, to) with the summed army count on its badge,
        plus the red, shaking arrows of auto-cancelled orders fading out.

        In simultaneous mode:
        - Shows player's own queued orders
        - Also shows allied players' queued orders (in a different shade)
        - Does NOT show enemy orders
        """
        sim_state = getattr(self.game, 'sim_state', None)
        if sim_state is not None and sim_state.sim_phase == 'planning':
            # SIMULTANEOUS MODE: Draw from sim_state.player_orders
            arrows = self._sim_order_arrows(sim_state)
        else:
            arrows = self._order_arrows()
        arrows.extend(self._cancelling_order_arrows())
        if not arrows:
            return
        # Arrows run between army circles, which sit above their banners' anchors
        lift = int(ARMY_CIRCLE_RADIUS * self.game.get_ui_scale_factor() * ARMY_CIRCLE_DRAW_LIFT)
        self.order_light.draw_arrows(self._hero_fx_view(), arrows, self._plot_fx_clock, lift=lift,
                                     badge=self._draw_order_badge)

    def _draw_order_badge(self, pos, count, colour):
        """An arrow's army count badge (drawn by OrderLight over all the arrows)."""
        self.game.helpers.draw_circle_badge(pos, count, border_color=colour)

    def _order_source_world(self, territory, player):
        """
        Where an order's arrow starts, in world coordinates: the ordering player's
        flag in a territory with several garrisons, else the territory centre.
        """
        from_cx, from_cy = self.game.scaled_centers[territory]
        garrisons = self.game.game_state.territory_garrisons.get(territory, {})
        # Count only non-empty garrisons for positioning
        occupied = sum(1 for g in garrisons.values() if g.get('unmoved', 0) + g.get('moved', 0) > 0)
        if occupied <= 1 or player is None:
            return (from_cx, from_cy)
        flag_positions = self.game.game_state.get_flag_positions_for_territory(
            territory, from_cx, from_cy, occupied
        )
        # The player's flag slot: non-empty garrisons before theirs
        garrison_index = 0
        for player_index in sorted(garrisons.keys()):
            if player_index == player:
                break
            if garrisons[player_index].get('unmoved', 0) + garrisons[player_index].get('moved', 0) > 0:
                garrison_index += 1
        if garrison_index < len(flag_positions):
            return flag_positions[garrison_index]
        return (from_cx, from_cy)

    def _order_arrows(self):
        """The turn's movement orders as OrderArrows (turn-by-turn mode)."""
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

        hovered_route = getattr(self.game, 'sidebar_hovered_route', None)
        centers = self.game.scaled_centers
        gs = self.game.game_state
        arrows = []
        for (from_territory, to_territory), total_count in route_counts.items():
            if from_territory not in centers or to_territory not in centers:
                continue
            first_order = route_first_order[(from_territory, to_territory)]
            points = [self._order_source_world(from_territory, first_order.player)]
            # Captain 2-hop: bent through the intermediate territory
            intermediate = getattr(first_order, 'intermediate_territory', None)
            if intermediate and intermediate in centers:
                points.append(centers[intermediate])
            points.append(centers[to_territory])
            # Coloured by kind (attack / own / ally, the 2-hop's by its final target);
            # gold while its Action Queue card is under the mouse
            if hovered_route == (from_territory, to_territory):
                kind = 'hovered'
            else:
                kind = gs.order_kind(first_order.player, to_territory)
            arrows.append(OrderArrow(points, kind, total_count))
        return arrows

    def _cancelling_order_arrows(self):
        """
        The arrows of orders auto-cancelled due to overflow, as red OrderArrows
        that shake and fade out over ARROW_CANCEL_DURATION seconds. Expired
        entries are dropped from game_state.cancelling_arrows (visual only).
        """
        if not hasattr(self.game, 'game_state') or not self.game.game_state:
            return []
        cancelling = self.game.game_state.cancelling_arrows
        if not cancelling:
            return []

        now = time.time()
        arrows = []
        live = []
        for entry in cancelling:
            elapsed = now - entry['start_time']
            from_terr = entry['from_territory']
            to_terr = entry['to_territory']
            if (elapsed >= ARROW_CANCEL_DURATION or from_terr not in self.game.scaled_centers
                    or to_terr not in self.game.scaled_centers):
                continue
            live.append(entry)
            # Progress 0.0 -> 1.0 over the animation duration
            progress = elapsed / ARROW_CANCEL_DURATION
            # Shake offset: decreasing amplitude sine wave
            shake = math.sin(elapsed * ARROW_CANCEL_SHAKE_FREQ) * ARROW_CANCEL_SHAKE_AMP * (1.0 - progress)
            arrows.append(OrderArrow([self.game.scaled_centers[from_terr], self.game.scaled_centers[to_terr]],
                                     'cancelled', entry['army_count'], fade=1.0 - progress, shake=shake))
        cancelling[:] = live
        return arrows

    def _sim_order_arrows(self, sim_state):
        """Movement arrows for simultaneous mode, as OrderArrows.

        Shows player's own orders and allied players' orders, coloured by kind
        (attack / own / ally); allied players' are dimmer and don't flow.

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

        hovered_route = getattr(self.game, 'sidebar_hovered_route', None)
        centers = self.game.scaled_centers
        gs = self.game.game_state
        arrows = []
        for (from_territory, to_territory, is_ally), (total_count, order_player) in route_counts.items():
            if from_territory not in centers or to_territory not in centers:
                continue
            points = [self._order_source_world(from_territory, order_player), centers[to_territory]]
            # An own order turns gold while its Action Queue card is under the mouse
            if not is_ally and hovered_route == (from_territory, to_territory):
                kind = 'hovered'
            else:
                kind = gs.order_kind(order_player, to_territory)
            arrows.append(OrderArrow(points, kind, total_count, allied=is_ally))
        return arrows

    def _marker_state(self, effects, territory, greyed_out):
        """
        The MarkerState of a marker on this territory, created when it first shows
        (it fades in from then). greyed_out is re-evaluated every frame (it used to
        be decided once, so a stale colour survived turn changes).
        """
        state = effects.get(territory)
        if state is None:
            phase = (stable_seed('marker', territory) & 0xFFFF) / 65536.0 * 8.0
            state = effects[territory] = MarkerState(greyed_out, phase, self._plot_fx_clock)
        state.greyed_out = greyed_out
        return state

    def _marker_appear(self, state):
        """0-1: how far a marker has faded in since it first showed."""
        appear = self._marker_fx_style['marker']['appear']
        return min(1.0, max(0.0, (self._plot_fx_clock - state.born) / appear)) if appear > 0 else 1.0

    def _draw_marker_label(self, text, x, y):
        """A marker's "#N" label centred on (x, y), with a dark shadow (readable on any map colour)."""
        surfaces = self._marker_labels.get(text)
        if surfaces is None:
            font = self.game.small_font
            shadow = self._marker_fx_style['marker']['label_shadow']
            surfaces = self._marker_labels[text] = (font.render(text, True, shadow),
                                                    font.render(text, True, WHITE))
        shadow_surface, label = surfaces
        rect = label.get_rect(center=(x, y))
        self.game.screen.blit(shadow_surface, rect.move(1, 1))
        self.game.screen.blit(label, rect)

    def draw_battle_markers(self):
        """
        Draw the battle markers as light (ui/effects/marker_fx_effect.py): crossed
        swords over coral-red light where it is the viewing player's battle to
        resolve (click it), ash grey where someone else resolves it.
        """
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
            # Forget the markers when not in battle phase
            self.battle_effects.clear()
            return

        view = self._hero_fx_view()
        click_radius = self.marker_light.click_radius(view.radius)
        label_offset = (self.marker_light.icon_half_height('battle', view.radius)
                        + int(self._marker_fx_style['marker']['label_gap'] * view.radius)
                        + self.game.small_font.get_height() // 2)

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

            # Check if this battle is clickable by the local player.
            # Red = your battle to resolve (click it), Grey = AI/other player resolves
            greyed_out = False
            if hasattr(self.game, 'sim_state') and self.game.sim_state is not None:
                # Simultaneous mode: only the resolver can click
                resolver = getattr(battle, 'resolver', None)
                local_player = self.game.get_local_player()
                if resolver is not None and resolver != local_player:
                    greyed_out = True
            else:
                # Sequential mode: only the player whose turn it is resolves battles.
                # Comparing with the local player covers AI turns AND a remote human's
                # turn in multiplayer (only AI turns were greyed before).
                if self.game.game_state.current_player != self.game.get_local_player():
                    greyed_out = True

            # Keyed by territory name (stable identity), not list index, so a marker
            # keeps its phase when other battles resolve and indices shift
            state = self._marker_state(self.battle_effects, territory, greyed_out)
            self.marker_light.draw_marker(view, screen_x, screen_y, 'battle', greyed_out,
                                          self._plot_fx_clock, state.phase, self._marker_appear(state))

            # Battle number below the icon
            self._draw_marker_label(f"#{i+1}", screen_x, screen_y + label_offset)

            # Clickable area: the icon and the ring, growing with the zoom
            self.game.battle_markers.append(pygame.Rect(screen_x - click_radius, screen_y - click_radius,
                                                        click_radius * 2, click_radius * 2))

        # Forget the markers of battles that no longer exist
        removed_territories = set(self.battle_effects.keys()) - active_battle_territories
        for territory_key in removed_territories:
            del self.battle_effects[territory_key]

    def draw_alliance_markers(self):
        """
        Draw the alliance arrival markers as light (simultaneous mode only): a
        sword over the allies' green where the viewing player chooses the new
        owner, ash grey where an ally chooses.

        Alliance markers appear when multiple allied armies arrive at the same
        territory during resolution phase. The player with the biggest army
        can click the marker to assign territory ownership.
        """
        # Clear alliance markers list first
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

        view = self._hero_fx_view()
        click_radius = self.marker_light.click_radius(view.radius)
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

            # Greyed out when the viewing player is not the chooser
            greyed_out = False
            chooser = marker.get('chooser')
            if chooser is not None and chooser != self.game.get_local_player():
                greyed_out = True

            state = self._marker_state(self.alliance_effects, territory, greyed_out)
            self.marker_light.draw_marker(view, screen_x, screen_y, 'alliance', greyed_out,
                                          self._plot_fx_clock, state.phase, self._marker_appear(state))

            # Store clickable area for this alliance marker
            # Only the chooser (biggest army) can click, but store all markers for UI
            self.game.alliance_markers.append({
                'rect': pygame.Rect(screen_x - click_radius, screen_y - click_radius,
                                   click_radius * 2, click_radius * 2),
                'territory': territory,
                'players': marker['players'],
                'chooser': marker['chooser']
            })

        # Forget the markers of territories that no longer have alliance arrivals
        removed_territories = set(self.alliance_effects.keys()) - active_territories
        for territory in removed_territories:
            del self.alliance_effects[territory]

    def draw_overflow_indicators(self):
        """
        Draw the overflow warning (an amber ring of light breathing fast, pulses
        running outward) on territories with excess armies.

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

        view = self._hero_fx_view()
        # Round the army circle (SHARED constants, as the selection ring and reticle)
        ui_scale = self.game.get_ui_scale_factor()
        circle_radius = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)
        circle_y_offset = int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT)
        for territory in overflow_territories:
            if territory not in self.game.scaled_centers:
                continue
            screen_x, screen_y = self.game.world_to_screen(self.game.scaled_centers[territory])
            self.marker_light.draw_overflow(view, screen_x, screen_y - circle_y_offset, circle_radius,
                                            self._plot_fx_clock)

    def trigger_castle_upgrade_effect(self, territory, plot_index):
        """
        Show a Keep -> Castle upgrade finishing as light: gold rays, a flare, rings
        and sparks at the plot (plot_fx_style 'castle_complete'), played through the
        hero ability cue engine with the ability casts.

        Args:
            territory: Name of the territory
            plot_index: Index of the plot containing the upgraded Keep
        """
        plots = self.game.scaled_plots.get(territory)
        if not plots or plot_index >= len(plots):
            return
        seed = stable_seed('castle', territory, plot_index, self._ability_casts)
        self._ability_casts += 1
        effect = HeroAbilityEffect(self.hero_light, self._plot_fx_style['castle_complete'],
                                   {'keep': plots[plot_index]}, seed)
        if effect.cues:
            self.ability_effects.append(effect)

    # ========================================
    # HERO ABILITY VISUAL EFFECTS
    # ========================================

    # How many Keeps' worth of anchors one cast may light at most (Extort Populace
    # fires at every Keep and Castle of the caster); the effects cull themselves
    # off screen, so this only bounds a pathological case
    MAX_ABILITY_POINTS = 40

    def trigger_ability_effect(self, ability_name, target_territory,
                               player_index, source_territory=None):
        """
        Show a hero ability cast as light (ui/effects/hero_fx_effect.py), styled
        per ability in ui/effects/hero_fx_style.py 'abilities'.

        Resolves the anchors the ability's cues use - the target, the caster
        hero's Keep, the territory, points inside it, arc ends, the caster's
        Keeps, the enemies' territories... - and starts one HeroAbilityEffect.

        Args:
            ability_name: Name of the ability
            target_territory: Territory where ability lands (None for immediate abilities)
            player_index: Player who activated the ability
            source_territory: Where an arc starts (Royal Charisma: the target it
                takes units from; Valorous Charge: the hero's Keep)
        """
        spec = self._hero_fx_style['abilities'].get(ability_name)
        gs = self.game.game_state
        if spec is None or gs is None:
            return
        seed = stable_seed(ability_name, target_territory, source_territory, player_index,
                           self._ability_casts)
        self._ability_casts += 1
        anchors = self._ability_anchors(ability_name, spec, target_territory, player_index,
                                        source_territory, seed)
        effect = HeroAbilityEffect(self.hero_light, spec, anchors, seed)
        if effect.cues:
            self.ability_effects.append(effect)

    def _caster_keep(self, ability_name, player_index):
        """(territory, world position of the Keep plot) of the player's hero with this ability."""
        gs = self.game.game_state
        for hero, data in sorted(gs.heroes.get(player_index, {}).items()):
            abilities = gs.HERO_TYPES.get(hero, {}).get('abilities', [])
            if not any(a.get('name') == ability_name for a in abilities):
                continue
            territory = data.get('keep_territory')
            plots = self.game.scaled_plots.get(territory) or []
            plot = data.get('keep_plot', 0)
            if plot is not None and 0 <= plot < len(plots):
                return territory, plots[plot]
            if territory in self.game.scaled_centers:
                return territory, self.game.scaled_centers[territory]
        return None

    def _keep_plots(self, owners, territories=None):
        """World positions of the Keep / Castle plots of these owners."""
        gs = self.game.game_state
        positions = []
        for territory, buildings in sorted(gs.buildings.items()):
            if gs.territory_owners.get(territory, -1) not in owners:
                continue
            if territories is not None and territory not in territories:
                continue
            plots = self.game.scaled_plots.get(territory) or []
            for plot_index, building in sorted(buildings.items()):
                if building in ('Keep', 'Castle') and plot_index < len(plots):
                    positions.append(plots[plot_index])
        return positions

    def _ability_anchors(self, ability_name, spec, target_territory, player_index,
                         source_territory, seed):
        """The world points / territory lists an ability's cues are anchored to."""
        import random as _random
        gs = self.game.game_state
        centres = self.game.scaled_centers
        polygons = self.game.scaled_polygons
        rng = _random.Random(seed)
        anchors = {}

        keep = self._caster_keep(ability_name, player_index)
        if keep is not None:
            anchors['keep'] = keep[1]

        if target_territory in centres:
            anchors['target'] = centres[target_territory]
            if target_territory in polygons:
                anchors['territory'] = [target_territory]
                if spec.get('points'):
                    anchors['points'] = self.hero_light.points_inside(
                        target_territory, spec['points'], seed)
            # Four points around the target (Relentless Charge: cavalry arriving)
            cx, cy = centres[target_territory]
            anchors['satellites'] = []
            for i in range(4):
                angle = (math.pi / 2) * i + rng.uniform(-0.3, 0.3)
                offset = rng.uniform(14.0, 22.0)
                anchors['satellites'].append((cx + offset * math.cos(angle),
                                              cy + offset * math.sin(angle)))

        # Arcs: the hero's Keep end lands on the Keep plot, the other on the centre
        def place(territory):
            if keep is not None and territory == keep[0]:
                return keep[1]
            return centres.get(territory)

        if source_territory is not None:
            anchors['source'] = place(source_territory)
            anchors['dest'] = place(target_territory)

        # The caster's own Keeps and Castles (Extort Populace)
        anchors['keeps'] = self._keep_plots({player_index})[:self.MAX_ABILITY_POINTS]

        # Up to five of the caster's territories (Master Negotiator)
        owned = sorted(t for t, o in gs.territory_owners.items() if o == player_index and t in polygons)
        anchors['territories'] = rng.sample(owned, min(5, len(owned)))

        # The players the caster's abilities hit (Embargo): their territories, and
        # up to three of their Keeps
        if hasattr(gs, 'ability_enemies'):
            enemies = set(gs.ability_enemies(player_index))
        else:
            enemies = {o for o in gs.territory_owners.values() if o not in (-1, player_index)}
        anchors['enemy_territories'] = sorted(
            t for t, o in gs.territory_owners.items() if o in enemies and t in polygons)
        enemy_keeps = self._keep_plots(enemies)
        anchors['enemy_keeps'] = rng.sample(enemy_keeps, min(3, len(enemy_keeps)))
        return anchors

    def update_ability_effects(self, delta_time):
        """Update all active hero ability visual effects."""
        for effect in self.ability_effects[:]:
            effect.update(delta_time)
            if effect.is_finished():
                self.ability_effects.remove(effect)

    def render_ability_effects(self):
        """
        Render the hero ability effects' parts that go over the plots and armies
        (flares, rings, sparks, comets, the Silence curtain). Their parts under
        the plots are drawn by render_hero_effects_under().
        """
        if not self.ability_effects:
            return
        view = self._hero_fx_view()
        for effect in self.ability_effects:
            effect.render_over(view)

    # Passive auras: the hero shown, its aura and the game_state getter of the
    # territories it covers (for the viewing player)
    HERO_AURAS = {
        'Seledra Rennervail': ('defiance', 'get_defiance_protected_territories'),
        'Vearen Asford': ('haste', 'get_haste_affected_territories'),
        'Darius Brennhen': ('safe_haven', 'get_safe_haven_territories'),
        'Regnus Aevencourne': ('safe_haven', 'get_safe_haven_territories'),
    }

    def update_hero_effects(self, delta_time):
        """
        Sync the passive aura and the Embargo embers with game state and ease
        their fades. Called from the game loop's update section (skipped while
        paused). Territory sets are recomputed only when what they depend on
        changes (selection, player, the hero's Keep, ownership) - not per frame.
        """
        gs = self.game.game_state
        if gs is None:
            return
        shown = None
        hero = self.game.selected_hero
        entry = self.HERO_AURAS.get(hero)
        if entry is not None:
            key, getter = entry
            player = gs.current_player
            hero_data = gs.heroes.get(player, {}).get(hero) or {}
            sync = (hero, player, hero_data.get('keep_territory'), gs._territory_owners_version)
            if sync != self._hero_aura_sync:
                self._hero_aura_sync = sync
                covered = getattr(gs, getter)(player) if hero_data else ()
                self.hero_auras[key].set_territories(
                    t for t in covered if t in self.game.scaled_polygons)
            shown = key
        for key, aura in self.hero_auras.items():
            aura.update(delta_time, key == shown)

        # Embargo: embers over every territory of the embargoed players
        blocked = tuple(sorted(gs.embargo_blocked_players))
        if blocked:
            sync = (blocked, gs._territory_owners_version)
            if sync != self._embargo_sync:
                self._embargo_sync = sync
                self.embargo_embers.set_territories(
                    t for t, owner in gs.territory_owners.items()
                    if owner in blocked and t in self.game.scaled_polygons)
        self.embargo_embers.update(delta_time, bool(blocked))

    def _hero_fx_view(self):
        """This frame's FxView: the camera's world_to_screen as an affine map."""
        world_to_screen = self.game.world_to_screen
        ax, ay = world_to_screen((0.0, 0.0))
        zoom = world_to_screen((1000.0, 0.0))[0] - ax
        return FxView(self.game.screen, ax, ay, zoom / 1000.0, self._plot_radius())

    def render_hero_effects_under(self):
        """
        The hero effects that belong under the plots and armies: the selected
        hero's aura, the Embargo embers and the under layer of ability casts
        (ray bursts, border light, fireflies, Regicide's drain). Called from
        draw_territories() just before the production rays and the plots.
        """
        # Once per frame, before any hero light is drawn (the over layer comes later)
        self.hero_light.begin_frame()
        self._draw_objective_rim()
        auras = [aura for aura in self.hero_auras.values() if aura.visible]
        if self.embargo_embers.visible:
            auras.append(self.embargo_embers)
        if not auras and not self.ability_effects:
            return
        view = self._hero_fx_view()
        for aura in auras:
            aura.render(view, self._plot_fx_clock)
        for effect in self.ability_effects:
            effect.render_under(view)

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

                    # Create effect if not already active. It keeps (territory, plot_index),
                    # not a position: render looks the plot up every frame
                    if (territory, plot_index) not in self.production_glow_effects:
                        effect = ProductionGlowEffect(territory, plot_index,
                                                      gs.get_player_color(owner))
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

    def _objective_territory(self):
        """The territory a tutorial / campaign step points at (get_highlight_territory), or None."""
        mission = getattr(self.game, 'tutorial_mission', None)
        if not mission or not getattr(mission, 'active', False):
            return None
        territory = mission.get_highlight_territory()
        return territory if territory in self.game.scaled_polygons else None

    def _draw_objective_rim(self):
        """
        Gold light running round the target territory's border - the hero aura
        border light (HeroLight.draw_outline) in the guidance gold, under the plots.
        """
        territory = self._objective_territory()
        if not territory:
            return
        style = self._order_fx_style['objective']
        rim = style['rim']
        light = self.hero_light
        levels = light.shimmer_levels(rim['base'], rim['wave'], rim['intensity'])
        shift = int(self._plot_fx_clock * rim['wave_speed'] * 256.0) & 255
        light.draw_outline(self._hero_fx_view(), light.outline((territory,)), tuple(style['colour']),
                           light.light_colour(style['colour'], style['white_mix']), rim, levels, shift, 1.0)

    def update_plot_effects(self, delta_time):
        """
        Advance the shared clock of the persistent plot effects (production rays,
        construction dust).

        Called from the main loop's update section, which is skipped while the game
        is paused, so the effects pause with it. Every effect animates from this one
        clock - there is no per-effect state to update.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        self._plot_fx_clock += delta_time

    def render_production_glow_effects(self):
        """
        Render the light rays of every producing plot.

        Called just before draw_plots(), so the plots cover the inner ends of the
        rays and the light seems to come from behind them. Rays are sized by the
        plot radius (not camera_zoom) so they match the plot at every zoom.
        """
        # Plots are only drawn while playing (draw_plots_original); no rays around
        # plots that aren't there
        if not self.production_glow_effects or self.game.game_state.phase != 'playing':
            return

        screen = self.game.screen
        screen_w, screen_h = screen.get_size()
        radius = self._plot_radius()
        reach = self.production_rays.reach(radius)
        clock = self._plot_fx_clock
        rays = self.production_rays
        scaled_plots = self.game.scaled_plots
        world_to_screen = self.game.world_to_screen

        for effect in self.production_glow_effects.values():
            plots = scaled_plots.get(effect.territory)
            if not plots or effect.plot_index >= len(plots):
                continue
            # Same projection and truncation as the plot itself (draw_plots_original)
            sx, sy = world_to_screen(plots[effect.plot_index])
            x, y = int(sx), int(sy)
            # Off-screen: skip before touching the shared frames (no rotation needed)
            if x < -reach or x > screen_w + reach or y < -reach or y > screen_h + reach:
                continue
            effect.render(screen, x, y, radius, clock, rays)

    def _draw_all_plots_unified(self, ui_scale, scaled_empty_plot_radius, building_letter_font):
        """
        FPS OPTIMIZATION Phase 3.1: Unified plot rendering in single pass.

        Completed buildings, plots under construction and empty plots in one loop
        (they used to be three separate passes, since removed).

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
        # Construction dust caps how many new sprites it makes per frame (no hitch)
        self.construction_dust.begin_frame()

        for territory, plots in self.game.scaled_plots.items():
            owner = self.game.game_state.territory_owners.get(territory, -1)
            if owner < 0:
                continue

            # FPS OPT: skip whole off-screen territories BEFORE projecting their plots.
            # The per-plot off-screen test below only ran after get_cached_screen_plots()
            # had already projected every plot, so zoomed-in views still paid for the
            # ~90% of territories that are nowhere near the viewport.
            if not self.is_territory_on_screen(territory):
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

        # A Keep being upgraded to a Castle gets construction dust with gold glints
        # (it used to show nothing on the map until the completion burst). Everyone
        # sees it, like the Castle icon that shows from the first turn of the upgrade.
        upgrading = (building == 'Keep' and
                     self.game.game_state.is_upgrading_to_castle(territory, plot_index))
        if upgrading:
            phase = self._plot_phase(territory, plot_index)
            self.construction_dust.draw_back(self.game.screen, x, y, scaled_empty_plot_radius,
                                             self._plot_fx_clock, phase, VARIANT_UPGRADE)

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
            # FPS OPT: the greyed (not-owned) variant is fully cacheable — it depends
            # only on (building_type, icon_size). Only hover/click, which apply to at
            # most one plot, still need a per-frame copy. Previously EVERY non-owned
            # building did copy + overlay fill + BLEND_RGBA_MULT every frame.
            is_greyed = (owner != current_player)
            needs_effects = (is_clicking or is_hovering)

            if needs_effects:
                if is_greyed:
                    display_icon = self.get_cached_greyed_building(
                        icon_building, building_icon, icon_size).copy()
                else:
                    display_icon = cached_icon.copy()
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
            elif is_greyed:
                # Cached grey variant — no per-frame copy or blend
                display_icon = self.get_cached_greyed_building(
                    icon_building, building_icon, icon_size)
            else:
                display_icon = cached_icon

            icon_rect = display_icon.get_rect(center=(x, y))
            self.game.screen.blit(display_icon, icon_rect)
        else:
            letter_surface = building_letter_font.render(letter, True, WHITE)
            letter_rect = letter_surface.get_rect(center=(x, y))
            self.game.screen.blit(letter_surface, letter_rect)

        # Draw layered border (cached: 3 draw.circle calls per plot, per frame)
        player_color = self.game.game_state.get_player_color(owner)
        self._blit_plot_chrome(x, y, scaled_empty_plot_radius, player_color)

        if upgrading:
            self.construction_dust.draw_front(self.game.screen, x, y, scaled_empty_plot_radius,
                                              self._plot_fx_clock, phase, VARIANT_UPGRADE)

        # Selection ring
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
            # Round the plot's rim (scaled_empty_plot_radius already carries ui_scale)
            self.order_light.draw_selection(self._hero_fx_view(), x, y, scaled_empty_plot_radius,
                                            self._plot_fx_clock)
        elif self._mission_beckons(territory, plot_index, building):
            self.order_light.draw_beckon(self._hero_fx_view(), x, y, scaled_empty_plot_radius,
                                         self._plot_fx_clock)

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

        # Construction dust: clouds behind the plot now, motes and chips over it after
        # the rings. Stateless (clock + plot phase), so it is right in every game mode
        # with nothing to sync - it draws wherever under_construction says. Everyone
        # sees it, like the construction disc itself.
        phase = self._plot_phase(territory, plot_index)
        self.construction_dust.draw_back(self.game.screen, x, y, scaled_empty_plot_radius,
                                         self._plot_fx_clock, phase, VARIANT_BUILD)

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

        self.construction_dust.draw_front(self.game.screen, x, y, scaled_empty_plot_radius,
                                          self._plot_fx_clock, phase, VARIANT_BUILD)

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

        # Tutorial / campaign hook: the gold "click here" on the plot a step points at
        # (not while it is selected - the panel's highlighted button takes over)
        if (self.game.selected_plot != (territory, plot_index)
                and self._mission_beckons(territory, plot_index)):
            self.order_light.draw_beckon(self._hero_fx_view(), x, y, scaled_empty_plot_radius,
                                         self._plot_fx_clock)

    def _mission_beckons(self, territory, plot_index, building=None):
        """
        Whether a tutorial / campaign step points at this plot: a highlighted plot,
        or a Barracks the step's 'barracks_<territory>' button highlight names.
        """
        mission = getattr(self.game, 'tutorial_mission', None)
        if not mission or not getattr(mission, 'active', False):
            return False
        if mission.should_highlight_plot(territory, plot_index):
            return True
        return building == 'Barracks' and mission.should_highlight_button(f'barracks_{territory}')

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

        # Mission gate: each ring shows exactly when its clicks are taken - main.py
        # handle_map_area_click tests the building ring under 'click_plots' and the
        # training ring under 'click_barracks' (the training ring used to hide under
        # 'click_plots' too, so in tutorial steps 18-19 it was invisible but clickable)
        mission = getattr(self.game, 'tutorial_mission', None)
        mission_on = mission is not None and getattr(mission, 'active', False)
        building_ring = not mission_on or mission.is_action_allowed('click_plots')
        training_ring = not mission_on or mission.is_action_allowed('click_barracks')

        scaled_plot_surface_size = int(PLOT_SURFACE_SIZE * ui_scale)
        scaled_plot_center_offset = scaled_plot_surface_size // 2

        # Draw quick-access building icons around selected empty plot
        if building_ring and self.game.selected_plot and self.game.game_state.phase == 'playing':
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
                        
                        # Per-type rules (Fortress territory has no Keep; one Keep / Training
                        # Grounds / Square per territory) — the same check start_construction()
                        # refuses with. The old local copy missed the Square and Fortress rules,
                        # so those icons showed green for a build that would be refused.
                        can_build_keep = self.game.game_state.get_building_type_block_reason(
                            territory, building_name) is None
                        
                        # Tutorial lock: force red if building type not allowed
                        _tutorial_locked = False
                        if hasattr(self.game, 'tutorial_mission') and self.game.tutorial_mission and self.game.tutorial_mission.active:
                            _tutorial_locked = not self.game.tutorial_mission.is_action_allowed(
                                'build', building_type=building_name, territory=territory)

                        # Base color - consider affordability, building limit, and one-per-territory restriction
                        if _tutorial_locked:
                            icon_color = COLOR_ICON_LOCKED  # Grey (tutorial/mission locked)
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

                        # Tutorial hook: the gold glow round the icon the mission points at
                        if (self.game._is_tutorial_active()
                                and self.game.tutorial_mission.should_highlight_button(f'building_{building_name}')):
                            self.game.tutorial_glow.circle(self.game.screen, (icon_x, icon_y), scaled_icon_click_radius)

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

                            # Tint if building is unavailable: grey when locked by the
                            # tutorial/mission, red when a game rule refuses it
                            if _tutorial_locked or not (can_afford and can_build_this_turn and can_build_keep):
                                red_overlay = self.get_reusable_surface(icon_size, icon_size)
                                red_overlay.fill((140, 140, 140, 255) if _tutorial_locked else (255, 100, 100, 100))
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
        if training_ring and self.game.selected_barracks and self.game.game_state.phase == 'playing':
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
                gs = self.game.game_state
                current_gold = gs.player_gold[gs.current_player]
                # IMPORTANT: Use total armies (all garrisons) for army limit check
                current_armies = gs.get_territory_total_armies(territory)
                at_army_limit = current_armies >= gs.MAX_ARMIES_PER_TERRITORY
                # Command limit: show red hue when player's total army count >= limit
                at_command_limit = gs.get_player_army_count(gs.current_player) >= gs.player_command_limit[gs.current_player]
                
                # Get current queue
                queue_count = 0
                if (territory in self.game.game_state.training_queue and 
                    barracks_plot_index in self.game.game_state.training_queue[territory]):
                    queue_count = len(self.game.game_state.training_queue[territory][barracks_plot_index])
                # Same limit start_training() enforces (was `< 5`: a full queue looked available)
                can_queue = queue_count < self.game.game_state.MAX_TRAINING_QUEUE
                
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
                        _tutorial_locked = not self.game.tutorial_mission.is_action_allowed(
                            'train', unit_type=unit_type, territory=territory)

                    # Check if player can afford and can train
                    can_afford = current_gold >= cost
                    can_train = can_afford and can_queue and not at_army_limit and not at_command_limit and not _tutorial_locked

                    # Check for hover
                    is_hovering = (distance_to_mouse_sq < scaled_icon_click_radius ** 2)

                    # Check for click flash
                    is_clicking = (self.game.clicked_element and
                                  self.game.clicked_element[0] == 'map_training' and
                                  self.game.clicked_element[1] == unit_type)

                    # Tutorial hook: the gold glow round the icon the mission points at
                    if (self.game._is_tutorial_active()
                            and self.game.tutorial_mission.should_highlight_button(f'training_{unit_type}')):
                        self.game.tutorial_glow.circle(self.game.screen, (icon_x, icon_y), scaled_icon_click_radius)

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

                        # Tint if cannot train (only affects RGB, not alpha): grey when
                        # locked by the tutorial/mission, red when a game rule refuses it
                        if not can_train:
                            # PERFORMANCE: Use reusable surface from pool
                            red_overlay = self.get_reusable_surface(icon_size, icon_size)
                            red_overlay.fill((140, 140, 140, 255) if _tutorial_locked else (255, 100, 100, 128))
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
                        if can_train:
                            icon_color = COLOR_ICON_AVAILABLE
                        else:
                            icon_color = COLOR_ICON_LOCKED if _tutorial_locked else COLOR_ICON_UNAVAILABLE
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
        
        Two rendering passes:
        1. Plots - completed buildings (letter icons F/M/B/K/Q), plots under
           construction and empty plots, in one loop (_draw_all_plots_unified())
        2. Quick-access icons - orbiting around selected plots (_draw_quick_access_icons())
        
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
        
        # Calculate scaled sizes for UI elements (plot effects use the same radius)
        scaled_empty_plot_radius = self._plot_radius(ui_scale)
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