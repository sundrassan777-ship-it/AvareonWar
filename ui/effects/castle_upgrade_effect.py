"""
Castle Upgrade Effect

Visual effect for Keep -> Castle upgrades featuring:
- One-time golden particle explosion
- 4-5 shades of gold particles
- Three animation phases:
  1. Initial explosion outward (0-0.5s)
  2. Circular swirling motion (0.5-2.5s)
  3. Upward float and fade out (2.5-3.5s)
- Pygame primitives only - no custom particle assets

Integration:
    - Triggered when a Keep is upgraded to a Castle
    - One-time effect (not looping)
    - Total duration: 3.5 seconds
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

# Five shades of gold from dark to light
DARK_GOLD = (184, 134, 11)      # Dark goldenrod
MEDIUM_DARK_GOLD = (218, 165, 32)  # Goldenrod
GOLD = (255, 215, 0)            # Gold
LIGHT_GOLD = (255, 223, 77)     # Light gold
VERY_LIGHT_GOLD = (255, 236, 139)  # Very light gold

GOLD_SHADES = [DARK_GOLD, MEDIUM_DARK_GOLD, GOLD, LIGHT_GOLD, VERY_LIGHT_GOLD]

# Animation phase durations (in seconds)
EXPLOSION_DURATION = 0.5    # Phase 1: Explosion outward
SWIRL_DURATION = 2.0        # Phase 2: Circular swirling
FLOAT_DURATION = 1.0        # Phase 3: Float upward and fade
TOTAL_DURATION = EXPLOSION_DURATION + SWIRL_DURATION + FLOAT_DURATION  # 3.5s

# ========================================
# CASTLE UPGRADE EFFECT CLASS
# ========================================

class CastleUpgradeEffect:
    """
    Golden particle explosion effect for Keep -> Castle upgrades.

    Three-phase animation:
    1. Explosion: Particles burst outward from center
    2. Swirl: Particles circle around the area
    3. Float: Particles drift upward and fade away

    Uses only Pygame circle primitives - no custom particle assets required.
    """

    def __init__(self, center_pos, num_particles=140, world_coords=False):
        """
        Initialize the castle upgrade particle effect.

        Args:
            center_pos: (x, y) tuple for effect center (castle location)
            num_particles: Number of particles (default 140, reduced by 30% from 200)
            world_coords: If True, center_pos is in world coordinates (requires world_to_screen conversion)
        """
        self.world_coords = world_coords
        if world_coords:
            # Store world position, will convert to screen each frame
            self.world_center_x, self.world_center_y = center_pos
            self.center_x, self.center_y = center_pos  # Will be updated in render
        else:
            # Screen coordinates (for backwards compatibility)
            self.center_x, self.center_y = center_pos
            self.world_center_x, self.world_center_y = center_pos

        self.num_particles = num_particles
        self.elapsed = 0.0
        self.is_complete = False

        # Initialize particles with random properties
        self.particles = []
        for i in range(num_particles):
            # Random angle for explosion direction
            angle = random.uniform(0, 2 * math.pi)

            # Random speed for explosion (some particles go faster/farther)
            # 50% smaller then increased 20%, then increased 30%: 48-120 -> 62-156
            speed = random.uniform(62, 156)  # pixels per second

            # Random gold shade
            color = random.choice(GOLD_SHADES)

            # Particle size - tiny pixels only (1px)
            size = 1

            # Random rotation speed for swirl phase (some clockwise, some counter)
            # Reduced by 40%: was -2.0 to 2.0, now -1.2 to 1.2
            rotation_speed = random.uniform(-1.2, 1.2)  # radians per second

            # Slightly randomize the swirl radius for variation
            swirl_radius_factor = random.uniform(0.8, 1.2)

            # Random vertical speed for float phase - 50% smaller
            float_speed = random.uniform(15, 30)  # pixels per second upward

            self.particles.append({
                'angle': angle,
                'speed': speed,
                'color': color,
                'size': size,
                'rotation_speed': rotation_speed,
                'swirl_radius_factor': swirl_radius_factor,
                'float_speed': float_speed,
                # Store position RELATIVE to center (offset from center in world space)
                'offset_x': 0.0,
                'offset_y': 0.0,
                # Extra vertical offset for float phase
                'float_offset_y': 0.0
            })

    def update(self, delta_time):
        """
        Update particle positions based on current animation phase.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        if self.is_complete:
            return

        self.elapsed += delta_time

        # Check if effect is complete
        if self.elapsed >= TOTAL_DURATION:
            self.is_complete = True
            return

        # Determine current phase
        if self.elapsed < EXPLOSION_DURATION:
            # Phase 1: Explosion with rotation
            self._update_explosion(delta_time)
        elif self.elapsed < EXPLOSION_DURATION + SWIRL_DURATION:
            # Phase 2: Continue swirling (seamless continuation from explosion)
            self._update_swirl(delta_time)
        else:
            # Phase 3: Float and fade
            self._update_float(delta_time)

    def _update_explosion(self, delta_time):
        """Update particles during explosion phase with deceleration and early swirl."""
        # Calculate deceleration factor based on progress through explosion phase
        explosion_progress = self.elapsed / EXPLOSION_DURATION  # 0.0 to 1.0

        # Exponential deceleration: particles slow down as they approach end of explosion
        # At start (0.0): decel_factor = 1.0 (full speed)
        # At end (1.0): decel_factor ~= 0.1 (10% speed)
        decel_factor = math.exp(-3.0 * explosion_progress)  # e^(-3*t)

        for particle in self.particles:
            # Calculate distance to travel this frame with deceleration
            current_speed = particle['speed'] * decel_factor
            distance = current_speed * delta_time

            # Start adding rotation during explosion phase
            # Rotation increases as explosion progresses (0% rotation at start, 100% at end)
            rotation_influence = explosion_progress  # 0.0 to 1.0
            particle['angle'] += particle['rotation_speed'] * delta_time * rotation_influence

            # Move particle outward from center (update offset)
            particle['offset_x'] += distance * math.cos(particle['angle'])
            particle['offset_y'] += distance * math.sin(particle['angle'])

    def _update_swirl(self, delta_time):
        """Update particles during swirl phase - seamless continuation of rotation."""
        # Particles continue rotating around the center from their current positions
        for particle in self.particles:
            # Calculate current radius from offset
            current_radius = math.sqrt(particle['offset_x'] ** 2 + particle['offset_y'] ** 2)

            # Only rotate if particle has moved away from center
            if current_radius > 0.1:
                current_angle = math.atan2(particle['offset_y'], particle['offset_x'])

                # Apply rotation (same as during explosion phase)
                current_angle += particle['rotation_speed'] * delta_time

                # Update offset position while maintaining current radius
                particle['offset_x'] = current_radius * math.cos(current_angle)
                particle['offset_y'] = current_radius * math.sin(current_angle)

    def _update_float(self, delta_time):
        """Update particles during float and fade phase."""
        # Particles drift upward (separate float offset)
        for particle in self.particles:
            particle['float_offset_y'] -= particle['float_speed'] * delta_time

    def render(self, screen, world_to_screen_func=None):
        """
        Render all particles at current animation state.

        Args:
            screen: Pygame surface to render to
            world_to_screen_func: Function to convert world coords to screen coords (for camera support)
        """
        if self.is_complete:
            return

        # Update screen center position if using world coordinates
        if self.world_coords and world_to_screen_func:
            self.center_x, self.center_y = world_to_screen_func((self.world_center_x, self.world_center_y))

        # P1 fix: reuse cached SRCALPHA surface instead of creating new one each frame
        screen_size = (screen.get_width(), screen.get_height())
        if not hasattr(self, '_cached_surface') or self._cached_surface is None or self._cached_surface.get_size() != screen_size:
            self._cached_surface = pygame.Surface(screen_size, pygame.SRCALPHA)
        else:
            self._cached_surface.fill((0, 0, 0, 0))
        temp_surface = self._cached_surface

        # Calculate opacity based on phase
        if self.elapsed < EXPLOSION_DURATION:
            # Phase 1: Full opacity during explosion
            opacity = 1.0
        elif self.elapsed < EXPLOSION_DURATION + SWIRL_DURATION:
            # Phase 2: Full opacity during swirl
            opacity = 1.0
        else:
            # Phase 3: Fade out during float
            phase_elapsed = self.elapsed - (EXPLOSION_DURATION + SWIRL_DURATION)
            fade_progress = phase_elapsed / FLOAT_DURATION
            opacity = 1.0 - fade_progress  # Fade from 1.0 to 0.0

        # Draw particles
        for particle in self.particles:
            # Calculate world position (center + offset + float offset)
            world_x = self.world_center_x + particle['offset_x']
            world_y = self.world_center_y + particle['offset_y'] + particle['float_offset_y']

            # Convert to screen coordinates
            if self.world_coords and world_to_screen_func:
                screen_x, screen_y = world_to_screen_func((world_x, world_y))
            else:
                # Direct screen coordinates (backwards compatibility)
                screen_x = self.center_x + particle['offset_x']
                screen_y = self.center_y + particle['offset_y'] + particle['float_offset_y']

            x = int(screen_x)
            y = int(screen_y)

            # Skip if off-screen (optimization)
            if x < -10 or x > screen.get_width() + 10 or y < -10 or y > screen.get_height() + 10:
                continue

            # Apply opacity to particle color
            r, g, b = particle['color']
            alpha = int(255 * opacity)
            color_with_alpha = (r, g, b, alpha)

            # Draw particle as a circle
            pygame.draw.circle(temp_surface, color_with_alpha, (x, y), particle['size'])

        # Blit the particle surface onto the main screen
        screen.blit(temp_surface, (0, 0))

    def is_finished(self):
        """
        Check if the effect has completed.

        Returns:
            bool: True if effect is finished, False otherwise
        """
        return self.is_complete
