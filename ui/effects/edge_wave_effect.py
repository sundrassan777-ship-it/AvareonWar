"""
Edge Wave Effect

Visual effect featuring:
- One-time green particle explosion from screen edges
- 4-5 shades of green particles
- Three animation phases:
  1. Initial explosion inward from edges (0-0.5s)
  2. Wave pattern floating around edges (0.5-1.5s)
  3. Recede toward center and fade (1.5-2.5s)
- Pygame primitives only - no custom particle assets

Integration:
    - Triggered as needed (one-time effect)
    - Total duration: 2.5 seconds
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

# Five shades of green from dark to light
DARK_GREEN = (0, 100, 0)           # Dark green
MEDIUM_DARK_GREEN = (34, 139, 34)  # Forest green
GREEN = (0, 200, 0)                # Lime green
LIGHT_GREEN = (144, 238, 144)      # Light green
VERY_LIGHT_GREEN = (152, 251, 152) # Pale green

GREEN_SHADES = [DARK_GREEN, MEDIUM_DARK_GREEN, GREEN, LIGHT_GREEN, VERY_LIGHT_GREEN]

# Animation phase durations (in seconds)
# Reduced by 25% for faster, snappier animation
EXPLOSION_DURATION = 0.375  # Phase 1: Explosion outward from center (was 0.5s)
PAUSE_DURATION = 0.0        # Phase 2: Brief pause at full expansion (optional)
RECEDE_DURATION = 0.75      # Phase 3: Recede to center and fade (was 1.0s)
TOTAL_DURATION = EXPLOSION_DURATION + PAUSE_DURATION + RECEDE_DURATION  # 1.125s (was 1.5s)

# ========================================
# EDGE WAVE EFFECT CLASS
# ========================================

class EdgeWaveEffect:
    """
    Green particle wave effect from screen edges.

    Two-phase animation:
    1. Explosion: Chaotic particles burst outward from center to edges (with deceleration)
    2. Recede: Particles move back toward center and fade away (with acceleration)

    Uses only Pygame circle primitives - no custom particle assets required.
    """

    def __init__(self, screen_width, screen_height, num_particles=600):
        """
        Initialize the edge wave particle effect.

        Args:
            screen_width: Width of the screen
            screen_height: Height of the screen
            num_particles: Number of particles (default 600)
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.num_particles = num_particles
        self.elapsed = 0.0
        self.is_complete = False

        # Calculate center of screen
        self.center_x = screen_width / 2
        self.center_y = screen_height / 2

        # Initialize particles distributed along a rectangle perimeter
        self.particles = []
        for i in range(num_particles):
            # Randomly choose which edge (0=top, 1=right, 2=bottom, 3=left)
            edge = random.randint(0, 3)

            # Normalized position along the edge (0.0 to 1.0)
            edge_position = random.uniform(0.0, 1.0)

            # Random green shade
            color = random.choice(GREEN_SHADES)

            # Particle size - tiny pixels only (1-2px)
            size = random.randint(1, 2)

            # Random fade start time in recede phase for variety
            fade_start = random.uniform(0.0, 0.3)

            # Add random offsets for chaos/disorder
            # Perpendicular offset (away from edge, toward center or beyond edge)
            perpendicular_offset = random.uniform(-50, 50)  # pixels

            # Parallel offset (along the edge direction) - adds extra variation
            parallel_offset = random.uniform(-30, 30)  # pixels

            self.particles.append({
                'edge': edge,
                'edge_position': edge_position,  # 0.0 to 1.0 along edge
                'perpendicular_offset': perpendicular_offset,
                'parallel_offset': parallel_offset,
                'color': color,
                'size': size,
                'fade_start': fade_start,
                # Current position (calculated each frame)
                'current_x': self.center_x,
                'current_y': self.center_y
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
            # Phase 1: Explosion outward
            self._update_explosion(delta_time)
        elif self.elapsed < EXPLOSION_DURATION + PAUSE_DURATION:
            # Phase 2: Pause (particles hold position)
            self._update_pause(delta_time)
        else:
            # Phase 3: Recede to center
            self._update_recede(delta_time)

    def _update_explosion(self, delta_time):
        """Update particles during explosion phase - chaotic rectangle expands from center to edges with deceleration."""
        # Progress through explosion phase (0.0 to 1.0)
        explosion_progress = self.elapsed / EXPLOSION_DURATION

        # Apply easing function for smooth deceleration
        # Use ease-out cubic: fast start, slow end
        eased_progress = 1 - math.pow(1 - explosion_progress, 3)

        # Keep chaos factor at 100% throughout explosion
        chaos_factor = 1.0

        for particle in self.particles:
            # Calculate rectangle size based on eased progress
            # Rectangle grows from center (0x0) to full screen
            half_width = (self.screen_width / 2) * eased_progress
            half_height = (self.screen_height / 2) * eased_progress

            # Calculate base position on rectangle perimeter
            edge = particle['edge']
            pos = particle['edge_position']

            if edge == 0:  # Top edge
                base_x = self.center_x + (pos * 2 - 1) * half_width  # -half_width to +half_width
                base_y = self.center_y - half_height
                # Apply offsets
                x = base_x + particle['parallel_offset'] * chaos_factor
                y = base_y + particle['perpendicular_offset'] * chaos_factor
            elif edge == 1:  # Right edge
                base_x = self.center_x + half_width
                base_y = self.center_y + (pos * 2 - 1) * half_height
                # Apply offsets
                x = base_x + particle['perpendicular_offset'] * chaos_factor
                y = base_y + particle['parallel_offset'] * chaos_factor
            elif edge == 2:  # Bottom edge
                base_x = self.center_x + (pos * 2 - 1) * half_width
                base_y = self.center_y + half_height
                # Apply offsets
                x = base_x + particle['parallel_offset'] * chaos_factor
                y = base_y + particle['perpendicular_offset'] * chaos_factor
            else:  # Left edge (edge == 3)
                base_x = self.center_x - half_width
                base_y = self.center_y + (pos * 2 - 1) * half_height
                # Apply offsets
                x = base_x + particle['perpendicular_offset'] * chaos_factor
                y = base_y + particle['parallel_offset'] * chaos_factor

            particle['current_x'] = x
            particle['current_y'] = y

    def _update_pause(self, delta_time):
        """Update particles during pause phase - particles hold their position."""
        # Particles simply maintain their current position
        # No updates needed - they stay where explosion left them
        pass

    def _update_recede(self, delta_time):
        """Update particles during recede phase - chaotic rectangle shrinks back to center with acceleration."""
        # Time within recede phase
        recede_time = self.elapsed - (EXPLOSION_DURATION + PAUSE_DURATION)

        # Progress through recede phase (0.0 to 1.0)
        recede_progress = recede_time / RECEDE_DURATION

        # Apply easing function for smooth acceleration
        # Use ease-in cubic: slow start, fast end
        eased_progress = math.pow(recede_progress, 3)

        # Keep chaos factor at 100% throughout recede
        chaos_factor = 1.0

        # Invert progress so rectangle shrinks (1.0 -> 0.0)
        shrink_factor = 1.0 - eased_progress

        # Calculate rectangle size based on shrink factor
        half_width = (self.screen_width / 2) * shrink_factor
        half_height = (self.screen_height / 2) * shrink_factor

        for particle in self.particles:
            # First time entering recede phase - save wave end position and calculate the trajectory
            if 'recede_start_x' not in particle:
                particle['recede_start_x'] = particle['current_x']
                particle['recede_start_y'] = particle['current_y']

                # Calculate where this particle should end up (center)
                particle['recede_end_x'] = self.center_x
                particle['recede_end_y'] = self.center_y

            # Interpolate from wave end position to center based on eased progress
            particle['current_x'] = particle['recede_start_x'] + (particle['recede_end_x'] - particle['recede_start_x']) * eased_progress
            particle['current_y'] = particle['recede_start_y'] + (particle['recede_end_y'] - particle['recede_start_y']) * eased_progress

    def render(self, screen):
        """
        Render all particles at current animation state.

        Args:
            screen: Pygame surface to render to
        """
        if self.is_complete:
            return

        # P1 fix: reuse cached SRCALPHA surface instead of creating new one each frame
        screen_size = (screen.get_width(), screen.get_height())
        if not hasattr(self, '_cached_surface') or self._cached_surface is None or self._cached_surface.get_size() != screen_size:
            self._cached_surface = pygame.Surface(screen_size, pygame.SRCALPHA)
        else:
            self._cached_surface.fill((0, 0, 0, 0))
        temp_surface = self._cached_surface

        # Calculate opacity based on phase
        if self.elapsed < EXPLOSION_DURATION:
            # Phase 1: Fade in during explosion
            explosion_progress = self.elapsed / EXPLOSION_DURATION
            opacity = min(1.0, explosion_progress * 2.0)  # Fade in quickly
        elif self.elapsed < EXPLOSION_DURATION + PAUSE_DURATION:
            # Phase 2: Full opacity during pause
            opacity = 1.0
        else:
            # Phase 3: Fade out during recede
            recede_time = self.elapsed - (EXPLOSION_DURATION + PAUSE_DURATION)

            # Draw particles with individual fade times
            for particle in self.particles:
                # Calculate individual particle opacity
                if recede_time < particle['fade_start']:
                    particle_opacity = 1.0
                else:
                    fade_progress = (recede_time - particle['fade_start']) / (RECEDE_DURATION - particle['fade_start'])
                    particle_opacity = max(0.0, 1.0 - fade_progress)

                x = int(particle['current_x'])
                y = int(particle['current_y'])

                # Skip if off-screen
                if x < -10 or x > screen.get_width() + 10 or y < -10 or y > screen.get_height() + 10:
                    continue

                # Apply opacity to particle color
                r, g, b = particle['color']
                alpha = int(255 * particle_opacity)
                color_with_alpha = (r, g, b, alpha)

                # Draw particle as a circle
                pygame.draw.circle(temp_surface, color_with_alpha, (x, y), particle['size'])

            # Blit the particle surface onto the main screen
            screen.blit(temp_surface, (0, 0))
            return

        # For explosion and wave phases (uniform opacity)
        for particle in self.particles:
            x = int(particle['current_x'])
            y = int(particle['current_y'])

            # Skip if off-screen
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
