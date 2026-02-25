# -*- coding: utf-8 -*-
"""
Production Glow Effect

Visual effect for buildings with active production (Barracks training units,
Keep/Castle training heroes) featuring:
- Radial light rays emanating outward from a circular center (matching round plots)
- Rays taper from bright center to soft edges with smooth gradient
- Glowing appearance via additive blending (BLEND_RGBA_ADD)
- Gentle rotation and independent per-ray pulsing
- Pulsing central glow disc
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

# Radial rays (emanating outward from circular center)
NUM_RAYS = 8                # Number of rays around the circle
RAY_LENGTH = 18             # How far rays extend outward from center (pixels at 1.0 zoom)
RAY_BASE_WIDTH = 3.0        # Width of ray at base (near center)
RAY_TIP_WIDTH = 0.5         # Width at tip (fades to thin line)
RAY_SEGMENTS = 6            # Gradient segments per ray
RAY_BASE_BRIGHTNESS = 0.4   # Minimum brightness at ray tip (0-1, higher = brighter tips)

# Animation
ROTATION_SPEED = 0.2        # Radians per second (gentle rotation)
PULSE_SPEED_MIN = 0.5       # Min pulse speed per ray (cycles/sec)
PULSE_SPEED_MAX = 1.0       # Max pulse speed per ray
PULSE_MIN_ALPHA = 0.6       # Dimmest a ray gets during pulse
PULSE_MAX_ALPHA = 1.0       # Brightest

# Central glow disc (pre-rendered, additively blended)
GLOW_DISC_RADIUS = 10       # Base radius at 1.0 zoom (matches plot circle size)
GLOW_DISC_ALPHA = 100       # Max alpha at center of glow disc
GLOW_PULSE_SPEED = 1.5      # Glow disc pulse speed


# ========================================
# PRODUCTION GLOW EFFECT CLASS
# ========================================

class ProductionGlowEffect:
    """
    Radial glowing ray effect for buildings with active production.

    Renders soft light rays emanating outward from a circular center point
    (matching the round building plot shape). Rays rotate slowly and pulse
    independently. A central glow disc and all rays are additively blended
    for a genuine glowing appearance.

    This is a continuous effect - runs until explicitly removed.
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

        # Pre-calculate ray base angles (evenly distributed around circle)
        self.ray_base_angles = [i * (2 * math.pi / NUM_RAYS) for i in range(NUM_RAYS)]

        # Independent pulse properties per ray
        self.ray_pulse_speeds = [
            random.uniform(PULSE_SPEED_MIN, PULSE_SPEED_MAX) for _ in range(NUM_RAYS)
        ]
        self.ray_pulse_phases = [
            random.uniform(0, 2 * math.pi) for _ in range(NUM_RAYS)
        ]

        # PERFORMANCE: Reuse rendering surface
        self._cached_surface = None
        self._cached_surface_size = 0

        # Pre-rendered glow disc (will be created on first render when zoom is known)
        self._glow_disc = None
        self._glow_disc_zoom = -1

    def update(self, delta_time):
        """Update animation state (rotation and pulse timers)."""
        self.elapsed += delta_time
        self.rotation_angle += ROTATION_SPEED * delta_time
        if self.rotation_angle > 2 * math.pi:
            self.rotation_angle -= 2 * math.pi

    def _get_pulse_alpha(self, ray_index):
        """Get current alpha multiplier for a ray (0.6-1.0 range)."""
        speed = self.ray_pulse_speeds[ray_index]
        phase = self.ray_pulse_phases[ray_index]
        t = math.sin(self.elapsed * speed * 2 * math.pi + phase)
        # Map from [-1, 1] to [PULSE_MIN_ALPHA, PULSE_MAX_ALPHA]
        return PULSE_MIN_ALPHA + (t + 1) * 0.5 * (PULSE_MAX_ALPHA - PULSE_MIN_ALPHA)

    def _ensure_glow_disc(self, zoom_scale):
        """Create/update the pre-rendered glow disc for current zoom."""
        # Round zoom to avoid constant re-rendering
        rounded_zoom = round(zoom_scale * 10) / 10
        if self._glow_disc is not None and self._glow_disc_zoom == rounded_zoom:
            return

        radius = max(3, int(GLOW_DISC_RADIUS * rounded_zoom))
        size = radius * 2 + 4
        disc = pygame.Surface((size, size), pygame.SRCALPHA)
        center = size // 2
        r, g, b = self.player_color
        # Brighter version of player color for glow center
        br = min(255, r + 80)
        bg = min(255, g + 80)
        bb = min(255, b + 80)

        # Radial gradient: bright center → transparent edge
        for rad in range(radius, 0, -1):
            t = rad / radius  # 1.0 at edge, 0.0 at center
            alpha = int(GLOW_DISC_ALPHA * (1.0 - t * t))
            # Blend from bright center color to player color toward edge
            blend = t * t
            cr = int(br * (1 - blend) + r * blend)
            cg = int(bg * (1 - blend) + g * blend)
            cb = int(bb * (1 - blend) + b * blend)
            pygame.draw.circle(disc, (cr, cg, cb, alpha), (center, center), rad)

        self._glow_disc = disc
        self._glow_disc_zoom = rounded_zoom

    def render(self, screen, world_to_screen_func=None, zoom_scale=1.0):
        """
        Render glowing radial rays and central glow disc.

        All rendering uses additive blending for genuine glow appearance.
        """
        # Update screen position from world coordinates
        if self.world_coords and world_to_screen_func:
            self.center_x, self.center_y = world_to_screen_func(
                (self.world_center_x, self.world_center_y)
            )

        # Skip if off-screen
        margin = int(RAY_LENGTH * zoom_scale) + 30
        if (self.center_x < -margin or self.center_x > screen.get_width() + margin or
            self.center_y < -margin or self.center_y > screen.get_height() + margin):
            return

        # Prepare the effect surface (small, centered on building)
        scaled_ray_length = RAY_LENGTH * zoom_scale
        surface_size = max(50, int(scaled_ray_length * 2.5 + 10))

        if self._cached_surface is None or self._cached_surface_size != surface_size:
            self._cached_surface = pygame.Surface((surface_size, surface_size), pygame.SRCALPHA)
            self._cached_surface_size = surface_size
        temp_surface = self._cached_surface
        temp_surface.fill((0, 0, 0, 0))

        scx = surface_size // 2
        scy = surface_size // 2

        # --- Draw rays emanating radially from center ---
        scaled_base_width = RAY_BASE_WIDTH * zoom_scale
        scaled_tip_width = RAY_TIP_WIDTH * zoom_scale

        for ray_index, base_angle in enumerate(self.ray_base_angles):
            current_angle = base_angle + self.rotation_angle
            pulse_alpha = self._get_pulse_alpha(ray_index)
            self._draw_ray(
                temp_surface, scx, scy, current_angle,
                scaled_ray_length, scaled_base_width, scaled_tip_width, pulse_alpha
            )

        # Blit rays with ADDITIVE blending for glow
        blit_x = int(self.center_x - scx)
        blit_y = int(self.center_y - scy)
        screen.blit(temp_surface, (blit_x, blit_y), special_flags=pygame.BLEND_RGBA_ADD)

        # --- Central glow disc (additive, on top of rays) ---
        self._ensure_glow_disc(zoom_scale)
        if self._glow_disc:
            glow_pulse = 1.0 + 0.15 * math.sin(self.elapsed * GLOW_PULSE_SPEED * 2 * math.pi)
            disc_w = int(self._glow_disc.get_width() * glow_pulse)
            disc_h = int(self._glow_disc.get_height() * glow_pulse)
            if disc_w > 2 and disc_h > 2:
                scaled_disc = pygame.transform.scale(self._glow_disc, (disc_w, disc_h))
                dx = int(self.center_x - disc_w // 2)
                dy = int(self.center_y - disc_h // 2)
                screen.blit(scaled_disc, (dx, dy), special_flags=pygame.BLEND_RGBA_ADD)

    def _draw_ray(self, surface, cx, cy, angle, length, base_width, tip_width, pulse_alpha):
        """
        Draw a single radial ray as gradient trapezoid segments emanating outward.

        Ray tapers from base_width at center to tip_width at outer edge,
        with alpha fading toward tip.
        """
        r, g, b = self.player_color
        # Brighter core for inner segments
        br = min(255, r + 60)
        bg = min(255, g + 60)
        bb = min(255, b + 60)

        cos_ray = math.cos(angle)
        sin_ray = math.sin(angle)
        cos_perp = math.cos(angle + math.pi / 2)
        sin_perp = math.sin(angle + math.pi / 2)

        for i in range(RAY_SEGMENTS):
            start_progress = i / RAY_SEGMENTS
            end_progress = (i + 1) / RAY_SEGMENTS

            start_dist = start_progress * length
            end_dist = end_progress * length

            start_w = (base_width + (tip_width - base_width) * start_progress) / 2
            end_w = (base_width + (tip_width - base_width) * end_progress) / 2

            # Alpha fades toward tip with base brightness floor
            fade = RAY_BASE_BRIGHTNESS + (1.0 - RAY_BASE_BRIGHTNESS) * (1.0 - start_progress ** 1.5)
            seg_alpha = int(255 * fade * pulse_alpha)
            if seg_alpha < 5:
                continue

            # Blend from bright core to player color as we go outward
            blend = start_progress
            cr = int(br * (1 - blend) + r * blend)
            cg = int(bg * (1 - blend) + g * blend)
            cb = int(bb * (1 - blend) + b * blend)

            # Trapezoid corners
            sx = cx + cos_ray * start_dist
            sy = cy + sin_ray * start_dist
            ex = cx + cos_ray * end_dist
            ey = cy + sin_ray * end_dist

            points = [
                (sx - cos_perp * start_w, sy - sin_perp * start_w),
                (sx + cos_perp * start_w, sy + sin_perp * start_w),
                (ex + cos_perp * end_w, ey + sin_perp * end_w),
                (ex - cos_perp * end_w, ey - sin_perp * end_w),
            ]
            pygame.draw.polygon(surface, (cr, cg, cb, seg_alpha), points)

    def update_color(self, new_color):
        """Update the player color (in case territory ownership changes)."""
        self.player_color = new_color
        # Force glow disc re-render with new color
        self._glow_disc_zoom = -1

    def is_finished(self):
        """This effect never finishes on its own - must be explicitly removed."""
        return False
