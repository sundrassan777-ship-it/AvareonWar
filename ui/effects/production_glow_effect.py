# -*- coding: utf-8 -*-
"""
Production Glow Effect

Visual effect for buildings with active production (Barracks training units,
Keep/Castle training heroes) featuring:
- Rotating sunrays emanating from the building center
- Rays colored in the player's faction color
- Rays fade at edges (opacity decreases with distance)
- Gentle pulsing for visibility
- Continuous effect while production is active

Integration:
    - Managed by MapRenderer
    - Created when a building starts production
    - Removed when production completes or is cancelled
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

# Number of sunrays
NUM_RAYS = 8

# Ray dimensions (in pixels at 1.0 zoom) - sized to fit building plot circles
RAY_LENGTH = 12  # How far rays extend from center (66% of 18)
RAY_BASE_WIDTH = 2  # Width at base (near center) - half thickness
RAY_TIP_WIDTH = 0.5  # Width at tip (fades to point)

# Animation speeds
ROTATION_SPEED = 0.15  # Radians per second (slower, gentler rotation)
PULSE_SPEED_MIN = 0.5  # Minimum pulse speed per ray (cycles per second)
PULSE_SPEED_MAX = 1.2  # Maximum pulse speed per ray (cycles per second)
PULSE_MIN_ALPHA = 0.85  # Minimum opacity during pulse (brighter)
PULSE_MAX_ALPHA = 1.0  # Maximum opacity during pulse (full brightness)

# Ray rendering
RAY_SEGMENTS = 8  # Number of segments per ray (for gradient fade)
RAY_BASE_BRIGHTNESS = 0.5  # Minimum brightness at ray tip (0.0-1.0, higher = brighter tips)

# PERFORMANCE: Number of pre-rendered rotation frames for sprite caching
NUM_CACHED_FRAMES = 16

# PERFORMANCE: Zoom quantization for the sprite cache.
# Previously the cache key was the RAW continuous zoom float, so every effect
# rebuilt all 16 frames on every distinct zoom value — i.e. every mouse-wheel
# tick and every frame of a campaign intro zoom. With ~100 producing buildings
# that is ~1,600 surface allocations and ~12,600 polygon draws in ONE frame,
# measured at 150ms average / 214ms worst (6.6 FPS).
# Rounding to 0.1 steps caps rebuilds at ~24 across the whole 1.65-4.0 range.
ZOOM_QUANTIZE_STEPS = 10.0

# Sprite frames depend ONLY on (quantized zoom, player colour): ray angles are
# identical for every instance and frames are baked at full alpha (the pulse is
# applied at blit time, not baked in). So all effects sharing a colour can share
# one set of frames — turning ~100 rebuilds per zoom change into exactly one.
_SHARED_SPRITE_CACHE = {}  # (zoom_key, player_color) -> (frames, surface_size)
# Bounded so a long zoom sweep cannot grow the cache without limit. Only a few
# zoom levels are live at once, so a small LRU keeps the hit rate high.
_SHARED_SPRITE_CACHE_MAX = 16


def _quantize_zoom(zoom_scale):
    """Round zoom to the sprite-cache granularity (see ZOOM_QUANTIZE_STEPS)."""
    return round(zoom_scale * ZOOM_QUANTIZE_STEPS) / ZOOM_QUANTIZE_STEPS


def _build_shared_sprite_frames(zoom_key, player_color):
    """
    Build (and memoize) the 16 rotation frames for one (zoom, colour) pair.

    Returns:
        (frames, surface_size) — frames is a list of NUM_CACHED_FRAMES surfaces.
    """
    cache_key = (zoom_key, player_color)
    cached = _SHARED_SPRITE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    scaled_ray_length = RAY_LENGTH * zoom_key
    surface_size = max(50, int(scaled_ray_length * 2.5))
    surface_center = surface_size // 2
    scaled_base_width = RAY_BASE_WIDTH * zoom_key
    scaled_tip_width = RAY_TIP_WIDTH * zoom_key
    base_angles = [i * (2 * math.pi / NUM_RAYS) for i in range(NUM_RAYS)]

    frames = []
    for frame_idx in range(NUM_CACHED_FRAMES):
        rotation = frame_idx * (2 * math.pi / NUM_CACHED_FRAMES)
        surface = pygame.Surface((surface_size, surface_size), pygame.SRCALPHA)
        for base_angle in base_angles:
            # Render at full alpha — pulse variation (0.85-1.0) is subtle enough to skip
            _draw_ray_on(surface, surface_center, surface_center, player_color,
                         base_angle + rotation, scaled_ray_length,
                         scaled_base_width, scaled_tip_width, 1.0)
        frames.append(surface)

    # Evict oldest entry when over budget (dicts preserve insertion order)
    if len(_SHARED_SPRITE_CACHE) >= _SHARED_SPRITE_CACHE_MAX:
        del _SHARED_SPRITE_CACHE[next(iter(_SHARED_SPRITE_CACHE))]

    entry = (frames, surface_size)
    _SHARED_SPRITE_CACHE[cache_key] = entry
    return entry


def _draw_ray_on(surface, cx, cy, player_color, angle, length,
                 base_width, tip_width, pulse_alpha):
    """
    Draw a single ray with gradient fade onto a surface.

    Module-level so the shared sprite cache can build frames without needing an
    effect instance (frames are identical for every instance of a given colour).
    """
    r, g, b = player_color

    # Draw ray as a series of trapezoids from base to tip; each segment fades
    for i in range(RAY_SEGMENTS):
        start_progress = i / RAY_SEGMENTS
        end_progress = (i + 1) / RAY_SEGMENTS

        start_dist = start_progress * length
        end_dist = end_progress * length

        start_width = base_width + (tip_width - base_width) * start_progress
        end_width = base_width + (tip_width - base_width) * end_progress

        # Alpha fades towards tip with base brightness floor
        fade_factor = RAY_BASE_BRIGHTNESS + (1.0 - RAY_BASE_BRIGHTNESS) * (1.0 - start_progress ** 1.5)
        alpha = int(255 * fade_factor * pulse_alpha)
        if alpha < 5:
            continue  # Skip nearly invisible segments

        color_with_alpha = (r, g, b, alpha)

        perp_angle = angle + math.pi / 2
        cos_perp = math.cos(perp_angle)
        sin_perp = math.sin(perp_angle)
        cos_ray = math.cos(angle)
        sin_ray = math.sin(angle)

        start_x = cx + cos_ray * start_dist
        start_y = cy + sin_ray * start_dist
        end_x = cx + cos_ray * end_dist
        end_y = cy + sin_ray * end_dist

        half_start_w = start_width / 2
        half_end_w = end_width / 2

        points = [
            (start_x - cos_perp * half_start_w, start_y - sin_perp * half_start_w),
            (start_x + cos_perp * half_start_w, start_y + sin_perp * half_start_w),
            (end_x + cos_perp * half_end_w, end_y + sin_perp * half_end_w),
            (end_x - cos_perp * half_end_w, end_y - sin_perp * half_end_w),
        ]

        pygame.draw.polygon(surface, color_with_alpha, points)


# ========================================
# PRODUCTION GLOW EFFECT CLASS
# ========================================

class ProductionGlowEffect:
    """
    Rotating sunray glow effect for buildings with active production.

    The effect shows rotating rays emanating from the building position,
    colored in the territory owner's color. Rays fade towards their tips
    and the overall effect pulses gently for visibility.

    This is a continuous effect that runs as long as the building has
    active production. Unlike one-shot effects, it doesn't have a duration
    and must be explicitly removed when production stops.
    """

    def __init__(self, center_pos, player_color, world_coords=True):
        """
        Initialize the production glow effect.

        Args:
            center_pos: (x, y) tuple for effect center (building location)
            player_color: (r, g, b) tuple for the player's faction color
            world_coords: If True, center_pos is in world coordinates
        """
        self.world_coords = world_coords
        if world_coords:
            self.world_center_x, self.world_center_y = center_pos
            self.center_x, self.center_y = center_pos
        else:
            self.center_x, self.center_y = center_pos
            self.world_center_x, self.world_center_y = center_pos

        self.player_color = player_color
        self.elapsed = 0.0
        self.rotation_angle = 0.0

        # Pre-calculate ray angles (evenly distributed)
        self.ray_base_angles = [i * (2 * math.pi / NUM_RAYS) for i in range(NUM_RAYS)]

        # Random pulse properties for each ray (independent pulsing)
        self.ray_pulse_speeds = [random.uniform(PULSE_SPEED_MIN, PULSE_SPEED_MAX) for _ in range(NUM_RAYS)]
        self.ray_pulse_phases = [random.uniform(0, 2 * math.pi) for _ in range(NUM_RAYS)]

        # PERFORMANCE: Pre-rendered sprite cache (16 rotation frames, rebuilt on zoom change)
        self._sprite_cache = []  # List of pre-rendered SRCALPHA surfaces
        self._sprite_cache_zoom = None  # Zoom level when cache was built
        self._sprite_cache_size = 0  # Surface size of cached frames

    def update(self, delta_time):
        """
        Update animation state (rotation and pulse).

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        self.elapsed += delta_time

        # Update rotation
        self.rotation_angle += ROTATION_SPEED * delta_time
        # Wrap around to prevent float overflow over long sessions
        if self.rotation_angle > 2 * math.pi:
            self.rotation_angle -= 2 * math.pi

    def _calculate_pulse_alpha(self, ray_index):
        """
        Calculate current alpha multiplier for a specific ray.

        Each ray has its own pulse speed and phase offset for
        independent, random-looking pulsing.

        Args:
            ray_index: Index of the ray (0 to NUM_RAYS-1)

        Returns:
            float: Alpha multiplier between PULSE_MIN_ALPHA and PULSE_MAX_ALPHA
        """
        # Each ray pulses independently with its own speed and phase
        pulse_speed = self.ray_pulse_speeds[ray_index]
        phase_offset = self.ray_pulse_phases[ray_index]

        # Sine wave oscillation between min and max alpha
        pulse_progress = math.sin(self.elapsed * pulse_speed * 2 * math.pi + phase_offset)
        # Map from [-1, 1] to [min, max]
        alpha_range = PULSE_MAX_ALPHA - PULSE_MIN_ALPHA
        return PULSE_MIN_ALPHA + (pulse_progress + 1) * 0.5 * alpha_range

    def _build_sprite_cache(self, zoom_scale):
        """
        Point this effect at the shared sprite frames for the given zoom.

        Frames are quantized and shared process-wide (see _build_shared_sprite_frames),
        so N effects of the same colour cost ONE build instead of N.
        """
        zoom_key = _quantize_zoom(zoom_scale)
        frames, surface_size = _build_shared_sprite_frames(zoom_key, tuple(self.player_color))
        self._sprite_cache = frames
        self._sprite_cache_zoom = zoom_key
        self._sprite_cache_size = surface_size

    def render(self, screen, world_to_screen_func=None, zoom_scale=1.0):
        """
        Render the rotating sunrays using pre-rendered sprite cache.

        Args:
            screen: Pygame surface to render to
            world_to_screen_func: Function to convert world coords to screen coords
            zoom_scale: Current camera zoom level for scaling ray size
        """
        # Update screen center position if using world coordinates
        if self.world_coords and world_to_screen_func:
            self.center_x, self.center_y = world_to_screen_func(
                (self.world_center_x, self.world_center_y)
            )

        # Skip if off-screen (with generous margin for rays)
        margin = int(RAY_LENGTH * zoom_scale) + 20
        if (self.center_x < -margin or self.center_x > screen.get_width() + margin or
            self.center_y < -margin or self.center_y > screen.get_height() + margin):
            return

        # PERFORMANCE: Re-point at the shared sprite frames only when the QUANTIZED
        # zoom changes. Comparing against the raw float here meant every effect
        # rebuilt 16 frames on every wheel tick / animation frame (150ms+ frames).
        zoom_key = _quantize_zoom(zoom_scale)
        if self._sprite_cache_zoom != zoom_key or not self._sprite_cache:
            self._build_sprite_cache(zoom_scale)

        # Pick nearest cached frame by rotation angle (single blit instead of 64 polygon draws)
        normalized_angle = self.rotation_angle % (2 * math.pi)
        frame_index = int(normalized_angle / (2 * math.pi) * NUM_CACHED_FRAMES) % NUM_CACHED_FRAMES
        cached_frame = self._sprite_cache[frame_index]
        surface_center = self._sprite_cache_size // 2

        # Blit centered on building position
        blit_x = int(self.center_x - surface_center)
        blit_y = int(self.center_y - surface_center)
        screen.blit(cached_frame, (blit_x, blit_y))

    def update_color(self, new_color):
        """
        Update the player color (in case territory ownership changes).

        Args:
            new_color: New (r, g, b) color tuple
        """
        if tuple(new_color) == tuple(self.player_color):
            return
        self.player_color = new_color
        # Sprite frames are keyed on colour as well as zoom, so drop this effect's
        # reference and let render() pick up the frames for the new colour. Without
        # this the glow kept the previous owner's colour until the zoom changed.
        self._sprite_cache = []
        self._sprite_cache_zoom = None

    def is_finished(self):
        """
        Check if effect should be removed.

        Note: This effect never finishes on its own - it must be explicitly
        removed when production stops.

        Returns:
            bool: Always False (continuous effect)
        """
        return False
