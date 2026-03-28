"""
Ability Polygon Burst Effect

Territory polygon bubble effect for hero ability activations.
Spawns rising colored circles inside a territory polygon, matching the
visual style of existing hero aura bubbles (Defiance, Haste, Safe Haven).

Supports two modes:
- One-shot (default): All bubbles spawn at once, fade over ~1 second.
  Used by Aggressive Diplomacy.
- Continuous (continuous=True): Bubbles spawn gradually at a low rate,
  each living ~1 second. Runs until stop() is called.
  Used by Embargo (persists on enemy territories until embargo expires).

Visual design:
- Bubbles spawn at random positions inside the territory polygon
- Each bubble: rises upward, expands 30%, fades from alpha 150 to 0
- Filled circles with 1px border (same as existing aura bubbles)
- Optional bubble_scale multiplier for larger/smaller bubbles
- Optional border_flash: draws fading polygon outline during first 0.8s

Integration:
    - Triggered from MapRenderer.trigger_ability_effect()
    - Managed by MapRenderer.sync_embargo_effects() for persistent mode
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

DURATION = 1.0             # Each bubble's lifetime (seconds)
SPAWN_STAGGER = 0.15       # One-shot mode: stagger start over this window (seconds)
RISE_SPEED = 7.5           # Upward drift speed (px/s, matches Defiance/Haste)
INITIAL_RADIUS_MIN = 1.5   # Min bubble radius (px)
INITIAL_RADIUS_MAX = 3.0   # Max bubble radius (px)
INITIAL_ALPHA = 150        # Starting alpha (matches existing bubbles)
EXPAND_FACTOR = 0.3        # Bubbles grow 30% over their lifetime
MAX_SPAWN_ATTEMPTS = 15    # Rejection sampling attempts per bubble

# Continuous mode constants
CONTINUOUS_SPAWN_INTERVAL = 0.4   # Spawn new bubbles every 400ms (reduced for FPS with many territories)
CONTINUOUS_BUBBLES_PER_SPAWN = 2  # Bubbles per spawn cycle (reduced for FPS with many territories)

# Border flash constants (optional fading polygon outline on activation)
BORDER_FLASH_DURATION = 0.8       # Duration of border flash (seconds)
BORDER_FLASH_ALPHA_START = 200    # Starting alpha for border outline
BORDER_FLASH_LINE_WIDTH = 2       # Line width for border outline

# ========================================
# ABILITY POLYGON BURST EFFECT CLASS
# ========================================

class AbilityPolygonBurstEffect:
    """
    Territory polygon bubble effect with one-shot or continuous mode.

    One-shot mode (default):
        All bubbles spawn at once and fade over ~1 second.
        Used by Aggressive Diplomacy.

    Continuous mode (continuous=True):
        Bubbles spawn gradually at a low rate, each living ~1 second.
        Runs indefinitely until stop() is called, then existing bubbles
        fade out and the effect completes.
        Used by Embargo (persists on enemy territories until embargo expires).
    """

    def __init__(self, polygon, color, num_bubbles=60, world_coords=True,
                 continuous=False, bubble_scale=1.0, border_flash=False):
        """
        Args:
            polygon: List of (x, y) tuples defining territory polygon (world coords)
            color: (r, g, b) tuple for bubble color
            num_bubbles: Number of bubbles for one-shot mode (ignored in continuous)
            world_coords: If True, polygon is in world coordinates
            continuous: If True, spawn bubbles continuously until stop() is called
            bubble_scale: Multiplier for bubble radii (default 1.0)
            border_flash: If True, draw fading polygon outline during first 0.8s
        """
        self.polygon = polygon
        self.color = color
        self.world_coords = world_coords
        self.continuous = continuous
        self.bubble_scale = bubble_scale
        self.border_flash = border_flash
        self.elapsed = 0.0
        self.is_complete = False
        self._cached_surface = None
        self._stopping = False  # True after stop() called, lets existing bubbles fade

        # Pre-compute bounding box for rejection sampling
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

        # Bubble list (managed differently in one-shot vs continuous)
        self.bubbles = []

        if continuous:
            # Continuous mode: start with a few bubbles, spawn more over time
            self._spawn_timer = 0.0
            for _ in range(CONTINUOUS_BUBBLES_PER_SPAWN):
                self._spawn_bubble()
        else:
            # One-shot mode: generate all bubbles at once
            for _ in range(num_bubbles):
                pos = self._random_point_in_polygon()
                if pos:
                    self.bubbles.append({
                        'world_x': pos[0],
                        'world_y': pos[1],
                        'initial_radius': random.uniform(INITIAL_RADIUS_MIN,
                                                         INITIAL_RADIUS_MAX)
                                         * self.bubble_scale,
                        'radius': 0.0,
                        'alpha': 0,
                        'offset_y': 0.0,
                        'age': -random.uniform(0, SPAWN_STAGGER),  # Negative = delayed
                    })

    def _spawn_bubble(self):
        """Spawn a single bubble at a random position inside the polygon."""
        pos = self._random_point_in_polygon()
        if pos:
            self.bubbles.append({
                'world_x': pos[0],
                'world_y': pos[1],
                'initial_radius': random.uniform(INITIAL_RADIUS_MIN,
                                                 INITIAL_RADIUS_MAX)
                                 * self.bubble_scale,
                'radius': 0.0,
                'alpha': 0,
                'offset_y': 0.0,
                'age': 0.0,
            })

    def _random_point_in_polygon(self):
        """Generate a random point inside the polygon via rejection sampling."""
        min_x, min_y, max_x, max_y = self.bbox
        for _ in range(MAX_SPAWN_ATTEMPTS):
            x = random.uniform(min_x, max_x)
            y = random.uniform(min_y, max_y)
            if self._point_in_polygon(x, y, self.polygon):
                return (x, y)
        return None

    @staticmethod
    def _point_in_polygon(x, y, polygon):
        """Ray-casting point-in-polygon test (matches main.py implementation)."""
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

    def stop(self):
        """
        Stop spawning new bubbles (continuous mode only).
        Existing bubbles will finish their lifecycle and fade out naturally.
        Effect auto-completes once all remaining bubbles have expired.
        """
        self._stopping = True

    def update(self, delta_time):
        """Update bubble positions and lifetimes."""
        if self.is_complete:
            return

        self.elapsed += delta_time

        # Continuous mode: spawn new bubbles periodically
        if self.continuous and not self._stopping:
            self._spawn_timer += delta_time
            if self._spawn_timer >= CONTINUOUS_SPAWN_INTERVAL:
                self._spawn_timer = 0.0
                for _ in range(CONTINUOUS_BUBBLES_PER_SPAWN):
                    self._spawn_bubble()

        # Update all bubbles
        expired = []
        for bubble in self.bubbles:
            bubble['age'] += delta_time

            if bubble['age'] < 0:
                # One-shot mode: bubble hasn't spawned yet (delayed)
                bubble['alpha'] = 0
                continue

            if bubble['age'] >= DURATION:
                # Bubble has expired
                bubble['alpha'] = 0
                expired.append(bubble)
                continue

            # Rise upward
            bubble['offset_y'] -= RISE_SPEED * delta_time

            # Calculate lifecycle progress (0.0 to 1.0)
            progress = bubble['age'] / DURATION

            # Expand 30% over lifetime
            bubble['radius'] = bubble['initial_radius'] * (1.0 + EXPAND_FACTOR * progress)

            # Fade from INITIAL_ALPHA to 0
            bubble['alpha'] = int(INITIAL_ALPHA * (1.0 - progress))

        # Remove expired bubbles (continuous mode recycles, one-shot lets them expire)
        for bubble in expired:
            self.bubbles.remove(bubble)

        # Check completion
        if self.continuous:
            # Complete only after stopping AND all bubbles have expired
            if self._stopping and len(self.bubbles) == 0:
                self.is_complete = True
        else:
            # One-shot: complete when all bubbles have expired
            if not self.bubbles:
                self.is_complete = True
            # Safety: also complete after max duration
            elif self.elapsed >= DURATION + SPAWN_STAGGER + 0.1:
                self.is_complete = True

    def render(self, screen, world_to_screen_func=None):
        """Render all bubbles as filled circles with border."""
        if self.is_complete or not self.bubbles:
            return

        # Reuse cached SRCALPHA surface
        screen_size = (screen.get_width(), screen.get_height())
        if (self._cached_surface is None
                or self._cached_surface.get_size() != screen_size):
            self._cached_surface = pygame.Surface(screen_size, pygame.SRCALPHA)
        else:
            self._cached_surface.fill((0, 0, 0, 0))
        temp_surface = self._cached_surface

        r, g, b = self.color
        # Pre-compute darker border color
        border_r = max(0, r - 40)
        border_g = max(0, g - 40)
        border_b = max(0, b - 40)

        # Draw border flash: fading polygon outline during first BORDER_FLASH_DURATION seconds
        if self.border_flash and self.elapsed < BORDER_FLASH_DURATION:
            flash_progress = self.elapsed / BORDER_FLASH_DURATION
            flash_alpha = int(BORDER_FLASH_ALPHA_START * (1.0 - flash_progress))
            if flash_alpha > 0 and len(self.polygon) >= 3:
                # Convert polygon to screen coords
                if self.world_coords and world_to_screen_func:
                    screen_poly = [world_to_screen_func(p) for p in self.polygon]
                else:
                    screen_poly = list(self.polygon)
                int_poly = [(int(p[0]), int(p[1])) for p in screen_poly]
                # Brighter color for flash outline
                flash_r = min(255, r + 60)
                flash_g = min(255, g + 60)
                flash_b = min(255, b + 60)
                pygame.draw.polygon(temp_surface, (flash_r, flash_g, flash_b, flash_alpha),
                                    int_poly, BORDER_FLASH_LINE_WIDTH)

        for bubble in self.bubbles:
            if bubble['alpha'] <= 0:
                continue

            world_x = bubble['world_x']
            world_y = bubble['world_y'] + bubble['offset_y']

            if self.world_coords and world_to_screen_func:
                sx, sy = world_to_screen_func((world_x, world_y))
            else:
                sx, sy = world_x, world_y

            x = int(sx)
            y = int(sy)

            # Skip off-screen bubbles
            if (x < -10 or x > screen.get_width() + 10
                    or y < -10 or y > screen.get_height() + 10):
                continue

            alpha = bubble['alpha']
            radius = max(1, int(bubble['radius']))

            # Filled circle with alpha (matches existing bubble style)
            pygame.draw.circle(temp_surface, (r, g, b, alpha), (x, y), radius)

            # 1px border for visibility (slightly more opaque, like _get_bubble_surface)
            border_alpha = min(255, alpha + 50)
            pygame.draw.circle(temp_surface,
                               (border_r, border_g, border_b, border_alpha),
                               (x, y), radius, 1)

        screen.blit(temp_surface, (0, 0))

    def is_finished(self):
        """Check if the effect has completed."""
        return self.is_complete
