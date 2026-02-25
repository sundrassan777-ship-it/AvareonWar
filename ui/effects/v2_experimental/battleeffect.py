"""
Battle Marker Effect

Visual effect for battle indicators featuring:
- Double concentric circles rotating around the battle marker
- Arrow particles spawning outside and converging inward toward center
- Glowing appearance via additive blending (BLEND_RGBA_ADD)
- BattleIcon overlay that pulses with animation
- Muted grey mode for non-clickable battles (dimmer, no glow)
- Pygame primitives only - no custom particle assets

Integration:
    - Used by map_renderer.py for battle indicators
    - Persists until battle is resolved
"""

import pygame
import math
import random

from utils.logger import get_logger

logger = get_logger(__name__)

# ========================================
# CONSTANTS
# ========================================

# Colors for active battles (red theme)
DARK_RED = (139, 0, 0)
RED = (220, 20, 60)
LIGHT_RED = (255, 100, 100)
BRIGHT_RED = (255, 160, 160)   # For glow highlights

# Grey colors for non-clickable battles
DARK_GREY = (80, 80, 80)
GREY = (130, 130, 130)
LIGHT_GREY = (180, 180, 180)

# Double circle ring constants
INNER_RING_RADIUS = 22      # Inner rotating circle radius
OUTER_RING_RADIUS = 32      # Outer rotating circle radius
RING_WIDTH = 2               # Line width of each ring
INNER_RING_SPEED = 1.0       # Radians/sec (clockwise)
OUTER_RING_SPEED = -0.7      # Radians/sec (counter-clockwise)
# Rings are drawn as dashed arcs (gaps give rotating feel)
RING_DASH_COUNT = 8          # Number of dashes per ring
RING_DASH_RATIO = 0.6        # Fraction of each segment that is filled vs gap

# Arrow particle constants
NUM_ARROWS = 16              # Number of arrow particles active at once
ARROW_SPAWN_RADIUS = 50      # How far out arrows spawn
ARROW_LENGTH = 6             # Arrow body length (pixels)
ARROW_HEAD_SIZE = 3          # Arrow head triangle size
ARROW_SPEED = 35             # Pixels/sec inward travel speed
ARROW_LIFETIME = 1.2         # Seconds to live (from spawn radius to center area)
ARROW_SPAWN_RATE = 14        # Arrows per second

# Central glow (pre-rendered radial gradient, additively blended)
GLOW_SIZE = 90               # Glow surface diameter
GLOW_CORE_ALPHA = 80         # Max alpha at glow center
GLOW_PULSE_SPEED = 2.5       # Pulse speed


# ========================================
# BATTLE HURRICANE EFFECT CLASS
# ========================================

class BattleHurricaneEffect:
    """
    Battle marker effect with double rotating circles and inward-converging arrows.

    Renders two concentric dashed circles rotating in opposite directions
    around the battle icon. Arrow particles spawn at the outer edge and
    travel inward toward the center. All layers are additively blended
    for a glowing appearance.

    Grey-out mode dims everything and disables additive glow.
    """

    def __init__(self, center_pos, battle_icon_path="assets/mapicons/BattleIcon1.png",
                 num_particles=400, duration=3.0, num_arms=4, greyed_out=False):
        """
        Initialize the battle marker effect.

        Args:
            center_pos: (x, y) center of the battle marker
            battle_icon_path: Path to BattleIcon1.png image
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
            self.color_ring = RED
            self.color_arrow = LIGHT_RED
            self.color_glow = BRIGHT_RED

        # Load BattleIcon image
        self.battle_icon = None
        self.battle_icon_base_size = None
        self.cached_scale_factor = None
        self.cached_scaled_icon = None

        try:
            icon_surface = pygame.image.load(battle_icon_path).convert_alpha()
            original_w, original_h = icon_surface.get_size()
            small_w = int(original_w * 0.065)
            small_h = int(original_h * 0.065)
            icon_surface = pygame.transform.smoothscale(icon_surface, (small_w, small_h))
            self.battle_icon = icon_surface
            self.battle_icon_base_size = (small_w, small_h)
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattleIcon from {battle_icon_path}: {e}")

        # Pre-render glow surface for additive blending
        self.glow_surface = None
        if not greyed_out:
            self.glow_surface = self._create_glow_surface(GLOW_SIZE, self.color_glow, GLOW_CORE_ALPHA)

        # PERFORMANCE: Reusable surface for rings and arrows
        self.effect_surface = None

        # Arrow particles list - each arrow has angle, distance, lifetime
        self.arrows = []
        self.arrow_spawn_timer = 0.0

    def _create_glow_surface(self, size, color, max_alpha):
        """Pre-render a radial gradient glow surface for additive blending."""
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        center = size // 2
        r, g, b = color
        for radius in range(center, 0, -1):
            t = radius / center  # 1.0 at edge, 0.0 at center
            alpha = int(max_alpha * (1.0 - t * t))
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
            # Spawn arrow at random angle on outer edge
            angle = random.uniform(0, 2 * math.pi)
            self.arrows.append({
                'angle': angle,
                'distance': ARROW_SPAWN_RADIUS + random.uniform(-5, 5),
                'age': 0.0,
                'speed': ARROW_SPEED + random.uniform(-5, 5),
            })

        # Update arrow positions (move inward)
        for arrow in self.arrows:
            arrow['age'] += delta_time
            arrow['distance'] -= arrow['speed'] * delta_time

        # Remove arrows that reached center area or expired
        self.arrows = [a for a in self.arrows if a['distance'] > 5 and a['age'] < ARROW_LIFETIME]

        # Cap active arrow count
        if len(self.arrows) > NUM_ARROWS * 2:
            self.arrows = self.arrows[-NUM_ARROWS * 2:]

    def render(self, screen):
        """Render rotating rings, arrows, glow, and icon."""
        # PERFORMANCE: Reuse effect surface
        surf_size = GLOW_SIZE + 40  # Enough room for rings + arrows + margin
        if self.effect_surface is None or self.effect_surface.get_width() != surf_size:
            self.effect_surface = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        self.effect_surface.fill((0, 0, 0, 0))

        cx = surf_size // 2
        cy = surf_size // 2

        # --- Layer 1: Central glow (additive, active only) ---
        if not self.greyed_out and self.glow_surface:
            glow_pulse = 1.0 + 0.12 * math.sin(self.elapsed * GLOW_PULSE_SPEED)
            scaled_size = int(GLOW_SIZE * glow_pulse)
            scaled_glow = pygame.transform.scale(self.glow_surface, (scaled_size, scaled_size))
            gx = self.center_x - scaled_size // 2
            gy = self.center_y - scaled_size // 2
            screen.blit(scaled_glow, (gx, gy), special_flags=pygame.BLEND_RGBA_ADD)

        # --- Layer 2: Double rotating rings (dashed circles) ---
        self._draw_dashed_ring(self.effect_surface, cx, cy, INNER_RING_RADIUS,
                               self.elapsed * INNER_RING_SPEED)
        self._draw_dashed_ring(self.effect_surface, cx, cy, OUTER_RING_RADIUS,
                               self.elapsed * OUTER_RING_SPEED)

        # --- Layer 3: Arrow particles converging inward ---
        for arrow in self.arrows:
            self._draw_arrow(self.effect_surface, cx, cy, arrow)

        # Blit the effect surface - additive for active, normal for grey
        blit_x = self.center_x - cx
        blit_y = self.center_y - cy
        if not self.greyed_out:
            screen.blit(self.effect_surface, (blit_x, blit_y), special_flags=pygame.BLEND_RGBA_ADD)
        else:
            screen.blit(self.effect_surface, (blit_x, blit_y))

        # --- Layer 4: BattleIcon overlay (always normal blit, on top) ---
        if self.battle_icon and self.battle_icon_base_size:
            self._render_icon(screen)

    def _draw_dashed_ring(self, surface, cx, cy, radius, angle_offset):
        """
        Draw a dashed circle ring as a series of arc segments.
        Each dash is a short thick arc drawn as connected line segments.
        """
        r, g, b = self.color_ring
        alpha = 200 if not self.greyed_out else 120

        segment_angle = 2 * math.pi / RING_DASH_COUNT
        dash_angle = segment_angle * RING_DASH_RATIO

        for i in range(RING_DASH_COUNT):
            start_angle = angle_offset + i * segment_angle
            # Draw each dash as a series of short line segments (simulates arc)
            num_points = 6
            points = []
            for j in range(num_points + 1):
                a = start_angle + (dash_angle * j / num_points)
                px = cx + radius * math.cos(a)
                py = cy + radius * math.sin(a)
                points.append((int(px), int(py)))

            # Draw connected line segments for this dash
            for j in range(len(points) - 1):
                pygame.draw.line(surface, (r, g, b, alpha), points[j], points[j + 1], RING_WIDTH)

    def _draw_arrow(self, surface, cx, cy, arrow):
        """
        Draw a single arrow particle pointing inward toward center.
        Arrow = line body + small triangular head.
        """
        angle = arrow['angle']
        dist = arrow['distance']

        # Fade in as arrow spawns, fade out as it nears center
        fade_in = min(1.0, arrow['age'] / 0.2)  # Fade in over 0.2s
        fade_out = min(1.0, dist / 15.0)         # Fade out within 15px of center
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

        # Draw arrow body line
        pygame.draw.line(surface, (r, g, b, alpha),
                         (int(tail_x), int(tail_y)), (int(tip_x), int(tip_y)), 2)

        # Draw small arrow head (triangle pointing inward)
        # Two points perpendicular to arrow direction, behind the tip
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
        """Render BattleIcon with gentle pulse."""
        # Gentle pulse: 1.0 to 1.08 scale
        pulse = 0.04 * math.sin(self.elapsed * 2.0 * math.pi / self.duration)
        icon_scale = 1.0 + 0.04 + pulse  # 1.0 to 1.08

        base_w, base_h = self.battle_icon_base_size
        scaled_w = int(base_w * icon_scale)
        scaled_h = int(base_h * icon_scale)

        if self.cached_scale_factor != icon_scale:
            self.cached_scaled_icon = pygame.transform.smoothscale(
                self.battle_icon, (scaled_w, scaled_h))
            self.cached_scale_factor = icon_scale

        icon_x = self.center_x - scaled_w // 2
        icon_y = self.center_y - scaled_h // 2
        screen.blit(self.cached_scaled_icon, (icon_x, icon_y))
