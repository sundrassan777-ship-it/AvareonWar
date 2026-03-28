"""
Ability Arc Effect

Particle stream that travels along a bezier curve between two territory centers.
Used for abilities that move things between territories (Royal Charisma, Valorous Charge).

Visual design:
- Configurable particle size (default 1px) launched in staggered waves along a quadratic bezier curve
- Two phases: Travel (1.5s, staggered launch over first 0.8s) -> Arrival burst + fade (1.0s) = 2.5s total
- Configurable arc height for taller/shorter arcs
- World-coordinate support with camera tracking
- Cached SRCALPHA surface for performance

Integration:
    - Triggered from MapRenderer.trigger_ability_effect() for arc-type abilities
    - One-time effect (not looping)
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

# Animation phase durations (in seconds)
TRAVEL_DURATION = 1.5      # Phase 1: Particles travel source -> destination
ARRIVAL_DURATION = 1.0     # Phase 2: Arrival burst and fade at destination
TOTAL_DURATION = TRAVEL_DURATION + ARRIVAL_DURATION  # 2.5s

# Particle launch timing
LAUNCH_WINDOW = 0.8        # All particles launched within this window (staggered)

# Bezier curve control point offset (how high the arc peaks above the midpoint)
ARC_HEIGHT_FACTOR = 0.35   # Peak height = 35% of source-dest distance

# Particle spread around the curve (perpendicular scatter in px)
CURVE_SPREAD = 8

# Arrival burst radius (how far particles scatter on arrival)
ARRIVAL_BURST_RADIUS = 30
ARRIVAL_BURST_SPEED_MIN = 15
ARRIVAL_BURST_SPEED_MAX = 40

# ========================================
# ABILITY ARC EFFECT CLASS
# ========================================

class AbilityArcEffect:
    """
    Particle stream traveling along a bezier curve between two territories.

    Two-phase animation:
    1. Travel: Particles follow a quadratic bezier curve from source to destination,
       launched in staggered waves for a streaming effect
    2. Arrival: Particles burst outward at destination and fade away

    Used by:
    - Royal Charisma (target territory -> Narn's Keep, white/gold)
    - Valorous Charge (Hevilneu's Keep -> target territory, light blue/white)
    """

    def __init__(self, source_pos, dest_pos, color_palette, num_particles=80,
                 world_coords=True, particle_size=1, arc_height=None):
        """
        Args:
            source_pos: (x, y) tuple for arc start point
            dest_pos: (x, y) tuple for arc end point
            color_palette: List of 5 RGB tuples (dark to light shades)
            num_particles: Number of particles (default 80)
            world_coords: If True, positions are in world coordinates
            particle_size: Radius of each particle circle (default 1px)
            arc_height: Override arc height factor (default ARC_HEIGHT_FACTOR=0.35)
        """
        self.world_coords = world_coords
        self.particle_size = particle_size

        if world_coords:
            self.world_source_x, self.world_source_y = source_pos
            self.world_dest_x, self.world_dest_y = dest_pos
        else:
            self.world_source_x, self.world_source_y = source_pos
            self.world_dest_x, self.world_dest_y = dest_pos

        self.elapsed = 0.0
        self.is_complete = False
        self._cached_surface = None

        # Calculate bezier control point (midpoint raised upward for arc)
        mid_x = (self.world_source_x + self.world_dest_x) / 2
        mid_y = (self.world_source_y + self.world_dest_y) / 2
        # Distance between source and dest
        dx = self.world_dest_x - self.world_source_x
        dy = self.world_dest_y - self.world_source_y
        distance = math.sqrt(dx * dx + dy * dy)
        # Control point is above the midpoint (negative Y = up in screen coords)
        height_factor = arc_height if arc_height is not None else ARC_HEIGHT_FACTOR
        arc_peak = distance * height_factor
        self.ctrl_x = mid_x
        self.ctrl_y = mid_y - arc_peak

        # Initialize particles with staggered launch times
        self.particles = []
        for _ in range(num_particles):
            # Stagger launch: each particle starts traveling at a different time
            launch_time = random.uniform(0, LAUNCH_WINDOW)
            color = random.choice(color_palette)
            # Perpendicular spread (scatter around the curve)
            spread = random.uniform(-CURVE_SPREAD, CURVE_SPREAD)
            # Arrival burst properties
            burst_angle = random.uniform(0, 2 * math.pi)
            burst_speed = random.uniform(ARRIVAL_BURST_SPEED_MIN,
                                         ARRIVAL_BURST_SPEED_MAX)
            # Slight speed variation so particles don't all arrive at once
            travel_speed = random.uniform(0.85, 1.15)

            self.particles.append({
                'launch_time': launch_time,
                'color': color,
                'size': 1,
                'spread': spread,
                'travel_speed': travel_speed,
                'burst_angle': burst_angle,
                'burst_speed': burst_speed,
                # Current screen position (updated each frame)
                'screen_x': 0.0,
                'screen_y': 0.0,
                # Burst offset (applied during arrival phase)
                'burst_offset_x': 0.0,
                'burst_offset_y': 0.0,
                # Whether particle has arrived at destination
                'arrived': False
            })

    def _bezier_point(self, t):
        """
        Calculate point on quadratic bezier curve at parameter t (0-1).

        Quadratic bezier: B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        P0 = source, P1 = control, P2 = destination
        """
        inv_t = 1.0 - t
        x = (inv_t * inv_t * self.world_source_x
             + 2 * inv_t * t * self.ctrl_x
             + t * t * self.world_dest_x)
        y = (inv_t * inv_t * self.world_source_y
             + 2 * inv_t * t * self.ctrl_y
             + t * t * self.world_dest_y)
        return x, y

    def _bezier_tangent(self, t):
        """
        Calculate tangent direction on bezier curve at parameter t.
        Used to orient the perpendicular spread.

        Derivative: B'(t) = 2(1-t)(P1-P0) + 2t(P2-P1)
        """
        inv_t = 1.0 - t
        dx = (2 * inv_t * (self.ctrl_x - self.world_source_x)
              + 2 * t * (self.world_dest_x - self.ctrl_x))
        dy = (2 * inv_t * (self.ctrl_y - self.world_source_y)
              + 2 * t * (self.world_dest_y - self.ctrl_y))
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.001:
            return 0.0, -1.0
        return dx / length, dy / length

    def update(self, delta_time):
        """Update particle positions along the bezier curve."""
        if self.is_complete:
            return

        self.elapsed += delta_time

        if self.elapsed >= TOTAL_DURATION:
            self.is_complete = True
            return

        for particle in self.particles:
            if self.elapsed < TRAVEL_DURATION:
                # Phase 1: Travel along bezier curve
                time_since_launch = self.elapsed - particle['launch_time']
                if time_since_launch < 0:
                    # Particle hasn't launched yet -- stay at source
                    particle['screen_x'] = self.world_source_x
                    particle['screen_y'] = self.world_source_y
                    continue

                # Calculate progress along curve (0 to 1)
                # Effective travel time = TRAVEL_DURATION - launch_time
                effective_duration = TRAVEL_DURATION - particle['launch_time']
                if effective_duration <= 0:
                    effective_duration = 0.1
                t = min(1.0, (time_since_launch / effective_duration)
                        * particle['travel_speed'])

                # Ease-in-out for smooth motion: smoothstep
                t_smooth = t * t * (3 - 2 * t)

                # Get position on bezier curve
                bx, by = self._bezier_point(t_smooth)

                # Apply perpendicular spread
                tx, ty = self._bezier_tangent(t_smooth)
                # Perpendicular = rotate tangent 90 degrees
                perp_x = -ty
                perp_y = tx
                bx += perp_x * particle['spread']
                by += perp_y * particle['spread']

                particle['screen_x'] = bx
                particle['screen_y'] = by

                if t >= 1.0:
                    particle['arrived'] = True

            else:
                # Phase 2: Arrival burst at destination
                if not particle['arrived']:
                    # Late particles snap to destination
                    particle['screen_x'] = self.world_dest_x
                    particle['screen_y'] = self.world_dest_y
                    particle['arrived'] = True

                # Burst outward from destination
                arrival_elapsed = self.elapsed - TRAVEL_DURATION
                burst_distance = particle['burst_speed'] * arrival_elapsed
                particle['burst_offset_x'] = (burst_distance
                                               * math.cos(particle['burst_angle']))
                particle['burst_offset_y'] = (burst_distance
                                               * math.sin(particle['burst_angle']))

    def render(self, screen, world_to_screen_func=None):
        """Render all particles at current animation state."""
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

        # Calculate opacity
        if self.elapsed < TRAVEL_DURATION:
            opacity = 1.0
        else:
            arrival_elapsed = self.elapsed - TRAVEL_DURATION
            opacity = 1.0 - (arrival_elapsed / ARRIVAL_DURATION)

        for particle in self.particles:
            # Skip particles that haven't launched yet
            if (self.elapsed < TRAVEL_DURATION
                    and self.elapsed < particle['launch_time']):
                continue

            # World position = curve position + burst offset
            world_x = particle['screen_x'] + particle['burst_offset_x']
            world_y = particle['screen_y'] + particle['burst_offset_y']

            # Convert to screen coordinates
            if self.world_coords and world_to_screen_func:
                sx, sy = world_to_screen_func((world_x, world_y))
            else:
                sx, sy = world_x, world_y

            x = int(sx)
            y = int(sy)

            # Skip off-screen particles
            if (x < -10 or x > screen.get_width() + 10
                    or y < -10 or y > screen.get_height() + 10):
                continue

            r, g, b = particle['color']
            alpha = int(255 * max(0.0, opacity))
            pygame.draw.circle(temp_surface, (r, g, b, alpha), (x, y),
                               self.particle_size)

        screen.blit(temp_surface, (0, 0))

    def is_finished(self):
        """Check if the effect has completed."""
        return self.is_complete
