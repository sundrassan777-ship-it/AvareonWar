"""
Sparkle Effect

Visual effect featuring:
- Random green particles appearing across the screen
- Each particle has its own lifetime and fade cycle
- Particles spawn continuously during effect duration
- Screen stays dark throughout
- No geometric patterns - pure random sparkle effect

Integration:
    - Alternative to edge wave effect for turn announcements
    - Can be swapped in turn_announcement_effect.py
"""

import pygame
import random
import math

# ========================================
# CONSTANTS
# ========================================

# Five shades of gold from dark to light
DARK_GOLD = (139, 101, 8)          # Dark gold/bronze
MEDIUM_DARK_GOLD = (184, 134, 11)  # Medium gold
GOLD = (218, 165, 32)              # Goldenrod
LIGHT_GOLD = (238, 201, 0)         # Bright gold
VERY_LIGHT_GOLD = (255, 223, 0)    # Light gold/yellow

GOLD_SHADES = [DARK_GOLD, MEDIUM_DARK_GOLD, GOLD, LIGHT_GOLD, VERY_LIGHT_GOLD]

# Particle lifecycle timing
MIN_PARTICLE_LIFETIME = 0.3  # Minimum time a particle exists (seconds)
MAX_PARTICLE_LIFETIME = 0.8  # Maximum time a particle exists (seconds)

# Particle spawn rate - PERFORMANCE OPTIMIZATION: Reduced from 3166 to 1200 for balanced visual/performance
# At 80 FPS: ~15 particles/frame (was 53/frame at 3166)
# Turn announcements: 1800 total particles in 1.5 sec (was 4749)
PARTICLES_PER_SECOND = 1200  # Balanced approach: good visual density + performance

# Particle size range (smallest possible for delicate sparkle effect)
MIN_PARTICLE_SIZE = 1
MAX_PARTICLE_SIZE = 1  # All particles are 1 pixel - tiny and delicate

# ========================================
# SPARKLE EFFECT CLASS
# ========================================

class SparkleEffect:
    """
    Random sparkle particle effect.

    Particles continuously spawn at random screen positions, each with:
    - Random green shade
    - Random lifetime (0.3-0.8 seconds)
    - Fade in → hold → fade out cycle
    - Random size (1-3 pixels)

    Effect runs for a specified total duration.
    """

    def __init__(self, screen_width, screen_height, duration=1.5):
        """
        Initialize the sparkle particle effect.

        Args:
            screen_width: Width of the screen
            screen_height: Height of the screen
            duration: Total duration of the effect (seconds)
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.duration = duration
        self.elapsed = 0.0
        self.is_complete = False

        # Active particles list
        # Each particle: {x, y, color, size, lifetime, age, max_opacity}
        self.particles = []

        # Track time since last spawn for spawn rate control
        self.spawn_accumulator = 0.0

    def update(self, delta_time):
        """
        Update particle lifecycles and spawn new particles.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        if self.is_complete:
            return

        self.elapsed += delta_time

        # Check if effect is complete
        if self.elapsed >= self.duration:
            self.is_complete = True
            # Let existing particles finish their lifecycle
            return

        # Spawn new particles based on spawn rate
        self.spawn_accumulator += delta_time
        particles_to_spawn = int(self.spawn_accumulator * PARTICLES_PER_SECOND)
        self.spawn_accumulator -= particles_to_spawn / PARTICLES_PER_SECOND

        for _ in range(particles_to_spawn):
            self._spawn_particle()

        # Update existing particles ages
        for particle in self.particles:
            particle['age'] += delta_time

        # PERFORMANCE OPTIMIZATION: Filter alive particles in single O(n) pass
        # Old approach was O(n²): iterate + append + remove() for each dead particle
        # New approach: list comprehension is O(n) and much faster
        self.particles = [p for p in self.particles if p['age'] < p['lifetime']]

    def _spawn_particle(self):
        """Spawn a new particle at a random position with random properties.

        Uses biased distribution: denser at edges, less dense toward center.
        """
        # Generate random position
        x = random.uniform(0, self.screen_width)
        y = random.uniform(0, self.screen_height)

        # Calculate distance from center (normalized 0.0 to 1.0)
        center_x = self.screen_width / 2
        center_y = self.screen_height / 2
        dx = abs(x - center_x) / (self.screen_width / 2)
        dy = abs(y - center_y) / (self.screen_height / 2)
        distance_from_center = max(dx, dy)  # Use max for rectangular distribution

        # Density factor based on distance with extended clear radius:
        # At center (0.0 to 0.5): 0% chance (no particles - clear area is 2x larger)
        # At edges (1.0): 200% chance (always keep, sometimes spawn extra)
        # Linear interpolation from 0.5 to 1.0: maps (0.5->0.0) to (1.0->2.0)
        # Formula: (distance - 0.5) * 4.0 = remaps 0.5-1.0 range to 0.0-2.0
        if distance_from_center < 0.3:
            density_factor = 0.0  # Clear area
        else:
            density_factor = (distance_from_center - 0.5) * 4.0  # 0.0 to 2.0

        # Reject particle based on density factor
        if random.random() > density_factor:
            return  # Don't spawn this particle

        # If density > 1.0 and we got lucky, spawn an extra particle nearby
        if density_factor > 1.0 and random.random() < (density_factor - 1.0):
            # Spawn extra particle near this position
            extra_x = x + random.uniform(-20, 20)
            extra_y = y + random.uniform(-20, 20)
            # Clamp to screen bounds
            extra_x = max(0, min(self.screen_width, extra_x))
            extra_y = max(0, min(self.screen_height, extra_y))

            extra_particle = {
                'x': extra_x,
                'y': extra_y,
                'color': random.choice(GOLD_SHADES),
                'size': random.randint(MIN_PARTICLE_SIZE, MAX_PARTICLE_SIZE),
                'lifetime': random.uniform(MIN_PARTICLE_LIFETIME, MAX_PARTICLE_LIFETIME),
                'age': 0.0,
                'max_opacity': random.uniform(0.6, 1.0)
            }
            self.particles.append(extra_particle)

        # Spawn the main particle
        particle = {
            'x': x,
            'y': y,
            'color': random.choice(GOLD_SHADES),
            'size': random.randint(MIN_PARTICLE_SIZE, MAX_PARTICLE_SIZE),
            'lifetime': random.uniform(MIN_PARTICLE_LIFETIME, MAX_PARTICLE_LIFETIME),
            'age': 0.0,
            'max_opacity': random.uniform(0.6, 1.0)  # Some particles dimmer than others
        }
        self.particles.append(particle)

    def _calculate_particle_opacity(self, particle):
        """
        Calculate particle opacity based on its age and lifetime.

        Lifecycle:
        - First 30%: Fade in
        - Middle 40%: Full brightness
        - Last 30%: Fade out

        Args:
            particle: Particle dict with 'age' and 'lifetime'

        Returns:
            float: Opacity from 0.0 to 1.0
        """
        progress = particle['age'] / particle['lifetime']

        if progress < 0.3:
            # Fade in phase
            fade_progress = progress / 0.3
            return fade_progress * particle['max_opacity']
        elif progress < 0.7:
            # Hold phase
            return particle['max_opacity']
        else:
            # Fade out phase
            fade_progress = (progress - 0.7) / 0.3
            return (1.0 - fade_progress) * particle['max_opacity']

    def render(self, screen):
        """
        Render all active particles.

        Args:
            screen: Pygame surface to render to
        """
        if not self.particles:
            return

        # Create a temporary surface with per-pixel alpha for transparency
        temp_surface = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)

        # Draw all particles
        for particle in self.particles:
            # Calculate opacity
            opacity = self._calculate_particle_opacity(particle)

            # Apply opacity to particle color
            r, g, b = particle['color']
            alpha = int(255 * opacity)
            color_with_alpha = (r, g, b, alpha)

            # Draw particle as a circle
            x = int(particle['x'])
            y = int(particle['y'])
            pygame.draw.circle(temp_surface, color_with_alpha, (x, y), particle['size'])

        # Blit the particle surface onto the main screen
        screen.blit(temp_surface, (0, 0))

    def is_finished(self):
        """
        Check if the effect has completed.

        Returns:
            bool: True if effect is finished and all particles are gone
        """
        return self.is_complete and len(self.particles) == 0
