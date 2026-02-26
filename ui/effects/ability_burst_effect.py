"""
Ability Burst Effect

Reusable one-shot particle burst for hero ability activations.
Configurable behaviors: explode (outward), implode (inward collapse).

Visual design:
- 1px particles in 5-shade color palettes
- Three animation phases with configurable durations:
  Burst (0.5s) -> Swirl (configurable, default 1.5s) -> Float+Fade (configurable, default 1.0s)
- Set swirl_duration=0 for explosion-only mode (Levy: burst + quick fade, no swirl)
- Set swirl_duration=2.0 to match CastleUpgradeEffect timing (Decisive Strike)
- World-coordinate support with camera tracking
- Cached SRCALPHA surface for performance

Integration:
    - Triggered from MapRenderer.trigger_ability_effect()
    - One-time effect (not looping)
    - Pattern mirrors CastleUpgradeEffect
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

# Animation phase durations (in seconds)
BURST_DURATION = 0.5      # Phase 1: Particles burst outward/inward
SWIRL_DURATION = 1.5      # Phase 2: Circular swirling
FLOAT_DURATION = 1.0      # Phase 3: Float upward and fade
TOTAL_DURATION = BURST_DURATION + SWIRL_DURATION + FLOAT_DURATION  # 3.0s

# Particle physics constants
EXPLODE_SPEED_MIN = 55     # Min initial explosion speed (px/s)
EXPLODE_SPEED_MAX = 145    # Max initial explosion speed (px/s)
IMPLODE_SPEED_MIN = 40     # Min initial implosion speed (px/s)
IMPLODE_SPEED_MAX = 110    # Max initial implosion speed (px/s)
RAIN_SPEED_MIN = 20        # Min rain fall speed (px/s)
RAIN_SPEED_MAX = 60        # Max rain fall speed (px/s)
RAIN_SPREAD = 50           # Horizontal spread for rain spawn (px)
FLOAT_SPEED_MIN = 15       # Min upward drift in float phase (px/s)
FLOAT_SPEED_MAX = 30       # Max upward drift in float phase (px/s)
ROTATION_SPEED_MAX = 1.2   # Max swirl rotation speed (rad/s)
DECEL_FACTOR = 3.0         # Exponential deceleration constant

# Implode-specific: initial radius ring where particles start
IMPLODE_RADIUS_MIN = 50    # Min starting distance from center (px)
IMPLODE_RADIUS_MAX = 120   # Max starting distance from center (px)

# ========================================
# ABILITY BURST EFFECT CLASS
# ========================================

class AbilityBurstEffect:
    """
    One-shot particle burst effect for hero ability activations.

    Three-phase animation:
    1. Burst: Particles move outward (explode), inward (implode), or downward (rain)
    2. Swirl: Particles circle around the area
    3. Float: Particles drift upward and fade away

    Behaviors:
    - 'explode': Particles burst outward from center (Decisive Strike, Relentless Charge, Levy)
    - 'implode': Particles start in a ring and collapse inward (Regicide)
    """

    def __init__(self, center_pos, color_palette, num_particles=120,
                 behavior='explode', world_coords=True,
                 swirl_duration=None, float_duration=None):
        """
        Args:
            center_pos: (x, y) tuple for effect center
            color_palette: List of 5 RGB tuples (dark to light shades)
            num_particles: Number of particles (default 120)
            behavior: 'explode', 'implode', or 'rain'
            world_coords: If True, center_pos is in world coordinates
            swirl_duration: Override swirl phase duration (default: SWIRL_DURATION=1.5s).
                            Set to 0 for explosion-only mode.
            float_duration: Override float phase duration (default: FLOAT_DURATION=1.0s)
        """
        self.world_coords = world_coords
        self.behavior = behavior

        # Configurable phase durations (allows matching CastleUpgradeEffect or explosion-only)
        self.burst_duration = BURST_DURATION
        self.swirl_duration = swirl_duration if swirl_duration is not None else SWIRL_DURATION
        self.float_duration = float_duration if float_duration is not None else FLOAT_DURATION
        self.total_duration = (self.burst_duration + self.swirl_duration
                               + self.float_duration)

        if world_coords:
            self.world_center_x, self.world_center_y = center_pos
            self.center_x, self.center_y = center_pos
        else:
            self.center_x, self.center_y = center_pos
            self.world_center_x, self.world_center_y = center_pos

        self.num_particles = num_particles
        self.elapsed = 0.0
        self.is_complete = False
        self._cached_surface = None

        # Initialize particles based on behavior
        self.particles = []
        for _ in range(num_particles):
            particle = self._create_particle(color_palette)
            self.particles.append(particle)

    def _create_particle(self, color_palette):
        """Create a single particle with properties based on behavior mode."""
        angle = random.uniform(0, 2 * math.pi)
        color = random.choice(color_palette)
        rotation_speed = random.uniform(-ROTATION_SPEED_MAX, ROTATION_SPEED_MAX)
        swirl_radius_factor = random.uniform(0.8, 1.2)
        float_speed = random.uniform(FLOAT_SPEED_MIN, FLOAT_SPEED_MAX)

        if self.behavior == 'explode':
            # Start at center, burst outward
            speed = random.uniform(EXPLODE_SPEED_MIN, EXPLODE_SPEED_MAX)
            return {
                'angle': angle,
                'speed': speed,
                'color': color,
                'size': 1,
                'rotation_speed': rotation_speed,
                'swirl_radius_factor': swirl_radius_factor,
                'float_speed': float_speed,
                'offset_x': 0.0,
                'offset_y': 0.0,
                'float_offset_y': 0.0
            }

        elif self.behavior == 'implode':
            # Start in a ring around center, collapse inward
            radius = random.uniform(IMPLODE_RADIUS_MIN, IMPLODE_RADIUS_MAX)
            speed = random.uniform(IMPLODE_SPEED_MIN, IMPLODE_SPEED_MAX)
            return {
                'angle': angle,
                'speed': speed,
                'color': color,
                'size': 1,
                'rotation_speed': rotation_speed,
                'swirl_radius_factor': swirl_radius_factor,
                'float_speed': float_speed,
                # Start at ring position, will move toward center
                'offset_x': radius * math.cos(angle),
                'offset_y': radius * math.sin(angle),
                'float_offset_y': 0.0,
                'initial_radius': radius
            }

        else:  # 'rain'
            # Start above center, spread horizontally, fall downward
            speed = random.uniform(RAIN_SPEED_MIN, RAIN_SPEED_MAX)
            horizontal_offset = random.uniform(-RAIN_SPREAD, RAIN_SPREAD)
            vertical_offset = random.uniform(-60, -20)  # Start 20-60px above center
            return {
                'angle': angle,
                'speed': speed,
                'color': color,
                'size': 1,
                'rotation_speed': rotation_speed * 0.5,  # Gentler swirl for rain
                'swirl_radius_factor': swirl_radius_factor,
                'float_speed': float_speed,
                'offset_x': horizontal_offset,
                'offset_y': vertical_offset,
                'float_offset_y': 0.0
            }

    def update(self, delta_time):
        """Update particle positions based on current animation phase."""
        if self.is_complete:
            return

        self.elapsed += delta_time

        if self.elapsed >= self.total_duration:
            self.is_complete = True
            return

        if self.elapsed < self.burst_duration:
            self._update_burst(delta_time)
        elif self.elapsed < self.burst_duration + self.swirl_duration:
            self._update_swirl(delta_time)
        else:
            self._update_float(delta_time)

    def _update_burst(self, delta_time):
        """Phase 1: Particles move according to behavior mode with deceleration."""
        progress = self.elapsed / self.burst_duration
        decel = math.exp(-DECEL_FACTOR * progress)

        for particle in self.particles:
            current_speed = particle['speed'] * decel

            if self.behavior == 'explode':
                # Move outward from center
                rotation_influence = progress
                particle['angle'] += particle['rotation_speed'] * delta_time * rotation_influence
                distance = current_speed * delta_time
                particle['offset_x'] += distance * math.cos(particle['angle'])
                particle['offset_y'] += distance * math.sin(particle['angle'])

            elif self.behavior == 'implode':
                # Move inward toward center
                current_radius = math.sqrt(
                    particle['offset_x'] ** 2 + particle['offset_y'] ** 2
                )
                if current_radius > 2.0:
                    # Move toward center with some rotation
                    inward_angle = math.atan2(
                        -particle['offset_y'], -particle['offset_x']
                    )
                    # Add slight spiral by blending inward angle with rotation
                    spiral_angle = inward_angle + particle['rotation_speed'] * 0.3
                    distance = current_speed * delta_time
                    particle['offset_x'] += distance * math.cos(spiral_angle)
                    particle['offset_y'] += distance * math.sin(spiral_angle)

            else:  # 'rain'
                # Fall downward with slight horizontal drift
                distance = current_speed * delta_time
                particle['offset_y'] += distance  # Move down
                # Gentle horizontal sway
                particle['offset_x'] += math.sin(
                    self.elapsed * 3 + particle['angle']
                ) * delta_time * 8

    def _update_swirl(self, delta_time):
        """Phase 2: Particles swirl around their current positions."""
        for particle in self.particles:
            current_radius = math.sqrt(
                particle['offset_x'] ** 2 + particle['offset_y'] ** 2
            )
            if current_radius > 0.1:
                current_angle = math.atan2(
                    particle['offset_y'], particle['offset_x']
                )
                current_angle += particle['rotation_speed'] * delta_time
                particle['offset_x'] = current_radius * math.cos(current_angle)
                particle['offset_y'] = current_radius * math.sin(current_angle)

    def _update_float(self, delta_time):
        """Phase 3: Particles drift upward and fade."""
        for particle in self.particles:
            particle['float_offset_y'] -= particle['float_speed'] * delta_time

    def render(self, screen, world_to_screen_func=None):
        """Render all particles at current animation state."""
        if self.is_complete:
            return

        # Update screen center from world coordinates
        if self.world_coords and world_to_screen_func:
            self.center_x, self.center_y = world_to_screen_func(
                (self.world_center_x, self.world_center_y)
            )

        # Reuse cached SRCALPHA surface
        screen_size = (screen.get_width(), screen.get_height())
        if (self._cached_surface is None
                or self._cached_surface.get_size() != screen_size):
            self._cached_surface = pygame.Surface(screen_size, pygame.SRCALPHA)
        else:
            self._cached_surface.fill((0, 0, 0, 0))
        temp_surface = self._cached_surface

        # Calculate opacity based on phase
        if self.elapsed < self.burst_duration + self.swirl_duration:
            opacity = 1.0
        else:
            phase_elapsed = self.elapsed - (self.burst_duration + self.swirl_duration)
            fade_duration = max(0.01, self.float_duration)  # Avoid division by zero
            opacity = 1.0 - (phase_elapsed / fade_duration)

        # Draw particles
        for particle in self.particles:
            world_x = self.world_center_x + particle['offset_x']
            world_y = (self.world_center_y + particle['offset_y']
                       + particle['float_offset_y'])

            if self.world_coords and world_to_screen_func:
                screen_x, screen_y = world_to_screen_func((world_x, world_y))
            else:
                screen_x = self.center_x + particle['offset_x']
                screen_y = (self.center_y + particle['offset_y']
                            + particle['float_offset_y'])

            x = int(screen_x)
            y = int(screen_y)

            # Skip off-screen particles
            if (x < -10 or x > screen.get_width() + 10
                    or y < -10 or y > screen.get_height() + 10):
                continue

            r, g, b = particle['color']
            alpha = int(255 * max(0.0, opacity))
            pygame.draw.circle(temp_surface, (r, g, b, alpha), (x, y),
                               particle['size'])

        screen.blit(temp_surface, (0, 0))

    def is_finished(self):
        """Check if the effect has completed."""
        return self.is_complete
