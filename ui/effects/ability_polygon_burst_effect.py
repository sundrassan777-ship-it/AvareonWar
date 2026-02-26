"""
Ability Polygon Burst Effect

One-shot territory polygon bubble burst for hero ability activations.
Spawns rising colored circles inside a territory polygon, matching the
visual style of existing hero aura bubbles (Defiance, Haste, Safe Haven).

Visual design:
- Bubbles spawn at random positions inside the territory polygon
- Each bubble: rises upward, expands 30%, fades from alpha 150 to 0
- Filled circles with 1px border (same as existing aura bubbles)
- Staggered spawn over first 0.15s for natural appearance
- Total duration: ~1.0 second

Integration:
    - Triggered from MapRenderer.trigger_ability_effect()
    - Used by Aggressive Diplomacy (fire orange bubbles filling conquered territory)
    - One-time effect (not looping)
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

DURATION = 1.0             # Total effect duration (seconds)
SPAWN_STAGGER = 0.15       # Bubbles stagger their start over this window (seconds)
RISE_SPEED = 7.5           # Upward drift speed (px/s, matches Defiance/Haste)
INITIAL_RADIUS_MIN = 1.5   # Min bubble radius (px)
INITIAL_RADIUS_MAX = 3.0   # Max bubble radius (px)
INITIAL_ALPHA = 150        # Starting alpha (matches existing bubbles)
EXPAND_FACTOR = 0.3        # Bubbles grow 30% over their lifetime
MAX_SPAWN_ATTEMPTS = 15    # Rejection sampling attempts per bubble

# ========================================
# ABILITY POLYGON BURST EFFECT CLASS
# ========================================

class AbilityPolygonBurstEffect:
    """
    One-shot territory polygon bubble burst effect.

    Spawns rising colored circles inside a territory polygon for ~1 second,
    matching the visual style of existing hero aura bubbles (Defiance, Haste).

    Used by:
    - Aggressive Diplomacy (fire orange bubbles filling conquered territory)
    """

    def __init__(self, polygon, color, num_bubbles=60, world_coords=True):
        """
        Args:
            polygon: List of (x, y) tuples defining territory polygon (world coords)
            color: (r, g, b) tuple for bubble color
            num_bubbles: Number of bubbles to spawn (default 60)
            world_coords: If True, polygon is in world coordinates
        """
        self.color = color
        self.world_coords = world_coords
        self.elapsed = 0.0
        self.is_complete = False
        self._cached_surface = None

        # Pre-compute bounding box for rejection sampling
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

        # Generate all bubble positions inside polygon via rejection sampling
        self.bubbles = []
        for _ in range(num_bubbles):
            pos = self._random_point_in_polygon(polygon)
            if pos:
                self.bubbles.append({
                    'world_x': pos[0],
                    'world_y': pos[1],
                    'initial_radius': random.uniform(INITIAL_RADIUS_MIN,
                                                     INITIAL_RADIUS_MAX),
                    'radius': 0.0,    # Updated each frame
                    'alpha': 0,       # Updated each frame
                    'offset_y': 0.0,  # Accumulated upward drift
                    # Stagger start so bubbles don't all appear at once
                    'delay': random.uniform(0, SPAWN_STAGGER),
                })

    def _random_point_in_polygon(self, polygon):
        """Generate a random point inside the polygon via rejection sampling."""
        min_x, min_y, max_x, max_y = self.bbox
        for _ in range(MAX_SPAWN_ATTEMPTS):
            x = random.uniform(min_x, max_x)
            y = random.uniform(min_y, max_y)
            if self._point_in_polygon(x, y, polygon):
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

    def update(self, delta_time):
        """Update bubble positions and lifetimes."""
        if self.is_complete:
            return

        self.elapsed += delta_time

        # Check if all bubbles have finished their lifecycle
        max_bubble_end = DURATION + SPAWN_STAGGER
        if self.elapsed >= max_bubble_end:
            self.is_complete = True
            return

        for bubble in self.bubbles:
            t = self.elapsed - bubble['delay']
            if t < 0:
                # Bubble hasn't spawned yet
                bubble['alpha'] = 0
                continue

            if t >= DURATION:
                # Bubble has finished
                bubble['alpha'] = 0
                continue

            # Rise upward
            bubble['offset_y'] -= RISE_SPEED * delta_time

            # Calculate lifecycle progress (0.0 to 1.0)
            progress = t / DURATION

            # Expand 30% over lifetime
            bubble['radius'] = bubble['initial_radius'] * (1.0 + EXPAND_FACTOR * progress)

            # Fade from INITIAL_ALPHA to 0
            bubble['alpha'] = int(INITIAL_ALPHA * (1.0 - progress))

    def render(self, screen, world_to_screen_func=None):
        """Render all bubbles as filled circles with border."""
        if self.is_complete:
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
