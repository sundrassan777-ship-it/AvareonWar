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

        # PERFORMANCE: Reuse rendering surface instead of creating new one each frame
        self._cached_surface = None
        self._cached_surface_size = 0

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

    def render(self, screen, world_to_screen_func=None, zoom_scale=1.0):
        """
        Render the rotating sunrays.

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

        # Scale ray dimensions based on zoom
        scaled_ray_length = RAY_LENGTH * zoom_scale
        scaled_base_width = RAY_BASE_WIDTH * zoom_scale
        scaled_tip_width = RAY_TIP_WIDTH * zoom_scale

        # PERFORMANCE: Reuse temporary surface for alpha blending
        # Size it to fit all rays plus margin (minimum 50px to ensure visibility)
        surface_size = max(50, int(scaled_ray_length * 2.5))
        if self._cached_surface is None or self._cached_surface_size != surface_size:
            self._cached_surface = pygame.Surface((surface_size, surface_size), pygame.SRCALPHA)
            self._cached_surface_size = surface_size
        temp_surface = self._cached_surface
        temp_surface.fill((0, 0, 0, 0))  # Clear for reuse
        surface_center = surface_size // 2

        # Draw each ray with independent pulse timing
        for ray_index, base_angle in enumerate(self.ray_base_angles):
            current_angle = base_angle + self.rotation_angle
            # Each ray has its own pulse alpha
            pulse_alpha = self._calculate_pulse_alpha(ray_index)
            self._draw_ray(
                temp_surface, surface_center, surface_center,
                current_angle, scaled_ray_length, scaled_base_width,
                scaled_tip_width, pulse_alpha
            )

        # Blit centered on building position
        blit_x = int(self.center_x - surface_center)
        blit_y = int(self.center_y - surface_center)
        screen.blit(temp_surface, (blit_x, blit_y))

    def _draw_ray(self, surface, cx, cy, angle, length, base_width, tip_width, pulse_alpha):
        """
        Draw a single ray with gradient fade.

        Args:
            surface: Surface to draw on
            cx, cy: Center position
            angle: Ray direction in radians
            length: Ray length in pixels
            base_width: Width at base
            tip_width: Width at tip
            pulse_alpha: Current pulse opacity multiplier
        """
        r, g, b = self.player_color

        # Draw ray as a series of trapezoids from base to tip
        # Each segment fades in opacity
        for i in range(RAY_SEGMENTS):
            # Progress along the ray (0.0 = base, 1.0 = tip)
            start_progress = i / RAY_SEGMENTS
            end_progress = (i + 1) / RAY_SEGMENTS

            # Distance from center
            start_dist = start_progress * length
            end_dist = end_progress * length

            # Width at this segment (linear interpolation)
            start_width = base_width + (tip_width - base_width) * start_progress
            end_width = base_width + (tip_width - base_width) * end_progress

            # Alpha fades towards tip with base brightness floor
            # RAY_BASE_BRIGHTNESS ensures tips stay visible (0.5 = 50% brightness at tip)
            fade_factor = RAY_BASE_BRIGHTNESS + (1.0 - RAY_BASE_BRIGHTNESS) * (1.0 - start_progress ** 1.5)
            segment_alpha = fade_factor * pulse_alpha
            alpha = int(255 * segment_alpha)

            if alpha < 5:
                continue  # Skip nearly invisible segments

            color_with_alpha = (r, g, b, alpha)

            # Calculate the 4 corners of this segment
            # Perpendicular direction for width
            perp_angle = angle + math.pi / 2
            cos_perp = math.cos(perp_angle)
            sin_perp = math.sin(perp_angle)
            cos_ray = math.cos(angle)
            sin_ray = math.sin(angle)

            # Start edge (closer to center)
            start_x = cx + cos_ray * start_dist
            start_y = cy + sin_ray * start_dist

            # End edge (further from center)
            end_x = cx + cos_ray * end_dist
            end_y = cy + sin_ray * end_dist

            # 4 corners of the trapezoid
            half_start_w = start_width / 2
            half_end_w = end_width / 2

            points = [
                (start_x - cos_perp * half_start_w, start_y - sin_perp * half_start_w),
                (start_x + cos_perp * half_start_w, start_y + sin_perp * half_start_w),
                (end_x + cos_perp * half_end_w, end_y + sin_perp * half_end_w),
                (end_x - cos_perp * half_end_w, end_y - sin_perp * half_end_w),
            ]

            pygame.draw.polygon(surface, color_with_alpha, points)

    def update_color(self, new_color):
        """
        Update the player color (in case territory ownership changes).

        Args:
            new_color: New (r, g, b) color tuple
        """
        self.player_color = new_color

    def is_finished(self):
        """
        Check if effect should be removed.

        Note: This effect never finishes on its own - it must be explicitly
        removed when production stops.

        Returns:
            bool: Always False (continuous effect)
        """
        return False
