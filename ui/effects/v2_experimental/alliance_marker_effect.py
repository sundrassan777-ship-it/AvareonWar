# -*- coding: utf-8 -*-
# ui/effects/alliance_marker_effect.py
# Alliance Marker Effect for Simultaneous Mode

"""
Alliance Marker Effect
======================

Visual effect for alliance arrival indicators in simultaneous mode.
When multiple allied armies capture the same territory, a blue marker
appears instead of a red battle marker.

Features:
- Double concentric circles rotating around the alliance marker
- Arrow particles spawning outside and converging inward toward center
- Glowing appearance via additive blending (BLEND_RGBA_ADD)
- AllianceIcon overlay that pulses with animation
- Muted grey mode for non-clickable markers

Integration:
    - Used by map_renderer.py for alliance arrival indicators
    - Only appears in simultaneous mode during resolution phase
    - Replaced when territory ownership is assigned
"""

import pygame
import math
import random
import os

# ========================================
# CONSTANTS
# ========================================

# Blue shades for alliance markers
DARK_BLUE = (0, 0, 139)
BLUE = (30, 144, 255)
LIGHT_BLUE = (100, 149, 237)
BRIGHT_BLUE = (140, 180, 255)    # For glow highlights

# Grey shades for non-clickable markers
DARK_GREY = (80, 80, 80)
GREY = (130, 130, 130)
LIGHT_GREY = (180, 180, 180)

# Double circle ring constants (slightly smaller than battle marker)
INNER_RING_RADIUS = 20
OUTER_RING_RADIUS = 28
RING_WIDTH = 2
INNER_RING_SPEED = 0.9
OUTER_RING_SPEED = -0.65
RING_DASH_COUNT = 6           # Fewer dashes (3 arms look)
RING_DASH_RATIO = 0.6

# Arrow particle constants
NUM_ARROWS = 12
ARROW_SPAWN_RADIUS = 42
ARROW_LENGTH = 5
ARROW_HEAD_SIZE = 3
ARROW_SPEED = 30
ARROW_LIFETIME = 1.2
ARROW_SPAWN_RATE = 10

# Central glow
GLOW_SIZE = 75
GLOW_CORE_ALPHA = 70
GLOW_PULSE_SPEED = 2.0


class AllianceMarkerEffect:
    """
    Alliance marker effect with double rotating circles and inward-converging arrows.

    Blue-themed variant of the battle marker effect. Slightly smaller and
    with fewer dashes/arrows for visual distinction.

    Grey-out mode dims everything and disables additive glow.
    """

    def __init__(self, center_pos, alliance_icon_path="assets/mapicons/AllianceIcon1.png",
                 num_particles=300, duration=3.0, num_arms=3, greyed_out=False):
        """
        Initialize the alliance marker effect.

        Args:
            center_pos: (x, y) center of the alliance marker
            alliance_icon_path: Path to AllianceIcon1.png image
            num_particles: Unused (kept for API compatibility)
            duration: Duration of one pulse cycle in seconds
            num_arms: Unused (kept for API compatibility)
            greyed_out: If True, use grey colors and no additive glow
        """
        self.center_x, self.center_y = center_pos
        self.duration = duration
        self.elapsed = 0.0
        self.progress = 0.0
        self.greyed_out = greyed_out

        # Color scheme
        if greyed_out:
            self.color_ring = GREY
            self.color_arrow = LIGHT_GREY
            self.color_glow = GREY
        else:
            self.color_ring = BLUE
            self.color_arrow = LIGHT_BLUE
            self.color_glow = BRIGHT_BLUE

        # Load AllianceIcon image
        self.alliance_icon = None
        self.alliance_icon_base_size = None
        self.cached_scale_factor = None
        self.cached_scaled_icon = None

        try:
            if os.path.exists(alliance_icon_path):
                icon_surface = pygame.image.load(alliance_icon_path).convert_alpha()
                original_w, original_h = icon_surface.get_size()
                small_w = int(original_w * 0.065)
                small_h = int(original_h * 0.065)
                icon_surface = pygame.transform.smoothscale(icon_surface, (small_w, small_h))
                self.alliance_icon = icon_surface
                self.alliance_icon_base_size = (small_w, small_h)
        except (pygame.error, FileNotFoundError):
            pass

        # Pre-render glow surface
        self.glow_surface = None
        if not greyed_out:
            self.glow_surface = self._create_glow_surface()

        # Reusable surface for rings and arrows
        self.effect_surface = None

        # Arrow particles
        self.arrows = []
        self.arrow_spawn_timer = 0.0

    def _create_glow_surface(self):
        """Pre-render a radial gradient glow surface for additive blending."""
        surface = pygame.Surface((GLOW_SIZE, GLOW_SIZE), pygame.SRCALPHA)
        center = GLOW_SIZE // 2
        r, g, b = self.color_glow
        for radius in range(center, 0, -1):
            t = radius / center
            alpha = int(GLOW_CORE_ALPHA * (1.0 - t * t))
            pygame.draw.circle(surface, (r, g, b, alpha), (center, center), radius)
        return surface

    def update(self, delta_time):
        """Update animation and arrow particles."""
        self.elapsed += delta_time
        self.progress = (self.elapsed % self.duration) / self.duration

        # Spawn new arrows
        self.arrow_spawn_timer += delta_time
        spawn_interval = 1.0 / ARROW_SPAWN_RATE
        while self.arrow_spawn_timer >= spawn_interval:
            self.arrow_spawn_timer -= spawn_interval
            angle = random.uniform(0, 2 * math.pi)
            self.arrows.append({
                'angle': angle,
                'distance': ARROW_SPAWN_RADIUS + random.uniform(-4, 4),
                'age': 0.0,
                'speed': ARROW_SPEED + random.uniform(-4, 4),
            })

        # Move arrows inward
        for arrow in self.arrows:
            arrow['age'] += delta_time
            arrow['distance'] -= arrow['speed'] * delta_time

        # Remove expired arrows
        self.arrows = [a for a in self.arrows if a['distance'] > 5 and a['age'] < ARROW_LIFETIME]

        if len(self.arrows) > NUM_ARROWS * 2:
            self.arrows = self.arrows[-NUM_ARROWS * 2:]

    def render(self, screen):
        """Render rotating rings, arrows, glow, and icon."""
        surf_size = GLOW_SIZE + 40
        if self.effect_surface is None or self.effect_surface.get_width() != surf_size:
            self.effect_surface = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        self.effect_surface.fill((0, 0, 0, 0))

        cx = surf_size // 2
        cy = surf_size // 2

        # --- Layer 1: Central glow (additive) ---
        if not self.greyed_out and self.glow_surface:
            glow_pulse = 1.0 + 0.10 * math.sin(self.elapsed * GLOW_PULSE_SPEED)
            scaled_size = int(GLOW_SIZE * glow_pulse)
            scaled_glow = pygame.transform.scale(self.glow_surface, (scaled_size, scaled_size))
            gx = self.center_x - scaled_size // 2
            gy = self.center_y - scaled_size // 2
            screen.blit(scaled_glow, (gx, gy), special_flags=pygame.BLEND_RGBA_ADD)

        # --- Layer 2: Double rotating rings ---
        self._draw_dashed_ring(self.effect_surface, cx, cy, INNER_RING_RADIUS,
                               self.elapsed * INNER_RING_SPEED)
        self._draw_dashed_ring(self.effect_surface, cx, cy, OUTER_RING_RADIUS,
                               self.elapsed * OUTER_RING_SPEED)

        # --- Layer 3: Arrow particles ---
        for arrow in self.arrows:
            self._draw_arrow(self.effect_surface, cx, cy, arrow)

        # Blit effect surface
        blit_x = self.center_x - cx
        blit_y = self.center_y - cy
        if not self.greyed_out:
            screen.blit(self.effect_surface, (blit_x, blit_y), special_flags=pygame.BLEND_RGBA_ADD)
        else:
            screen.blit(self.effect_surface, (blit_x, blit_y))

        # --- Layer 4: Icon overlay ---
        if self.alliance_icon and self.alliance_icon_base_size:
            self._render_icon(screen)

    def _draw_dashed_ring(self, surface, cx, cy, radius, angle_offset):
        """Draw a dashed circle ring as arc segments."""
        r, g, b = self.color_ring
        alpha = 200 if not self.greyed_out else 120

        segment_angle = 2 * math.pi / RING_DASH_COUNT
        dash_angle = segment_angle * RING_DASH_RATIO

        for i in range(RING_DASH_COUNT):
            start_angle = angle_offset + i * segment_angle
            num_points = 6
            points = []
            for j in range(num_points + 1):
                a = start_angle + (dash_angle * j / num_points)
                px = cx + radius * math.cos(a)
                py = cy + radius * math.sin(a)
                points.append((int(px), int(py)))

            for j in range(len(points) - 1):
                pygame.draw.line(surface, (r, g, b, alpha), points[j], points[j + 1], RING_WIDTH)

    def _draw_arrow(self, surface, cx, cy, arrow):
        """Draw a single arrow particle pointing inward toward center."""
        angle = arrow['angle']
        dist = arrow['distance']

        fade_in = min(1.0, arrow['age'] / 0.2)
        fade_out = min(1.0, dist / 12.0)
        overall_alpha = fade_in * fade_out

        if overall_alpha < 0.05:
            return

        r, g, b = self.color_arrow
        alpha = int(220 * overall_alpha)

        # Arrow tip (closer to center)
        tip_x = cx + dist * math.cos(angle)
        tip_y = cy + dist * math.sin(angle)

        # Arrow tail (further from center)
        tail_dist = dist + ARROW_LENGTH
        tail_x = cx + tail_dist * math.cos(angle)
        tail_y = cy + tail_dist * math.sin(angle)

        # Body line
        pygame.draw.line(surface, (r, g, b, alpha),
                         (int(tail_x), int(tail_y)), (int(tip_x), int(tip_y)), 2)

        # Arrow head triangle
        head_base_dist = dist + ARROW_HEAD_SIZE
        perp_angle = angle + math.pi / 2
        hs = ARROW_HEAD_SIZE * 0.6
        p1 = (int(cx + head_base_dist * math.cos(angle) + hs * math.cos(perp_angle)),
              int(cy + head_base_dist * math.sin(angle) + hs * math.sin(perp_angle)))
        p2 = (int(cx + head_base_dist * math.cos(angle) - hs * math.cos(perp_angle)),
              int(cy + head_base_dist * math.sin(angle) - hs * math.sin(perp_angle)))
        tip = (int(tip_x), int(tip_y))

        pygame.draw.polygon(surface, (r, g, b, alpha), [tip, p1, p2])

    def _render_icon(self, screen):
        """Render AllianceIcon with gentle pulse."""
        pulse = 0.04 * math.sin(self.elapsed * 2.0 * math.pi / self.duration)
        icon_scale = 1.0 + 0.04 + pulse

        base_w, base_h = self.alliance_icon_base_size
        scaled_w = int(base_w * icon_scale)
        scaled_h = int(base_h * icon_scale)

        if self.cached_scale_factor != icon_scale:
            self.cached_scaled_icon = pygame.transform.smoothscale(
                self.alliance_icon, (scaled_w, scaled_h))
            self.cached_scale_factor = icon_scale

        icon_x = self.center_x - scaled_w // 2
        icon_y = self.center_y - scaled_h // 2
        screen.blit(self.cached_scaled_icon, (icon_x, icon_y))
