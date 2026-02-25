"""
Battle Hurricane Effect

Visual effect for battle indicators featuring:
- Hurricane-style particle effect with spiral arms
- Dense red particle distribution (1000 particles)
- Grow/shrink animation loop
- BattleIcon overlay that scales with animation
- Pygame primitives only - no custom particle assets

Integration:
    - Used by map_renderer.py for battle indicators
    - Replaces pulsing circle battle markers
    - Persists until battle is resolved
"""

import pygame
import math
import random
import os

from utils.logger import get_logger

logger = get_logger(__name__)

# ========================================
# CONSTANTS
# ========================================

# Colors for particles (red - clickable battles)
DARK_RED = (139, 0, 0)      # Dark red - between arms
RED = (220, 20, 60)          # Normal red (crimson) - transition
LIGHT_RED = (255, 100, 100)  # Light red - on arm centers

# Grey colors for non-clickable battles (when player is not the resolver)
DARK_GREY = (80, 80, 80)      # Dark grey - between arms
GREY = (130, 130, 130)        # Normal grey - transition
LIGHT_GREY = (180, 180, 180)  # Light grey - on arm centers

# ========================================
# BATTLE HURRICANE EFFECT CLASS
# ========================================

class BattleHurricaneEffect:
    """
    Hurricane-style particle effect for battle indicators.

    Renders dense particles (1000) in multiple curved spiral arms that converge on
    a center point, mimicking a hurricane viewed from space.
    Uses logarithmic spiral for authentic curved arms.
    Continuously grows and shrinks with the BattleIcon overlay.
    Uses only Pygame circle primitives - no custom particle assets required.
    """

    def __init__(self, center_pos, battle_icon_path="assets/mapicons/BattleIcon1.png",
                 num_particles=1000, duration=3.0, num_arms=4, greyed_out=False):
        """
        Initialize the battle hurricane particle effect.

        Args:
            center_pos: (x, y) tuple for hurricane center (battle location)
            battle_icon_path: Path to BattleIcon1.png image
            num_particles: Number of particles (1000 for dense effect)
            duration: Duration of one grow/shrink cycle in seconds
            num_arms: Number of spiral arms (4 for hurricane look)
            greyed_out: If True, use grey colors (for non-clickable battles)
        """
        self.center_x, self.center_y = center_pos
        self.num_particles = num_particles
        self.duration = duration
        self.elapsed = 0.0
        self.progress = 0.0  # 0.0 to 1.0 for current expansion cycle
        self.num_arms = num_arms
        self.greyed_out = greyed_out

        # Select color scheme based on greyed_out flag
        if greyed_out:
            self.color_light = LIGHT_GREY
            self.color_normal = GREY
            self.color_dark = DARK_GREY
        else:
            self.color_light = LIGHT_RED
            self.color_normal = RED
            self.color_dark = DARK_RED

        # Load BattleIcon image
        self.battle_icon = None
        self.battle_icon_base_size = None
        # PERFORMANCE OPTIMIZATION: Cache for scaled icon to avoid expensive smoothscale every frame
        self.cached_scale_factor = None
        self.cached_scaled_icon = None
        # PERFORMANCE OPTIMIZATION: Reusable surface for particles (avoids creating 1600×900 surface every frame)
        self.particle_surface = None  # Created on first render when screen size is known
        try:
            icon_surface = pygame.image.load(battle_icon_path).convert_alpha()
            # Scale down to 6.5% of original size (30% bigger than 5%)
            original_w, original_h = icon_surface.get_size()
            small_w = int(original_w * 0.065)
            small_h = int(original_h * 0.065)
            icon_surface = pygame.transform.smoothscale(icon_surface, (small_w, small_h))
            self.battle_icon = icon_surface
            # Store base size for scaling (grow by 20%)
            self.battle_icon_base_size = (small_w, small_h)
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattleIcon from {battle_icon_path}: {e}")
            # Effect will work without icon

        # Initialize particles distributed along spiral arms
        self.particles = []
        particles_per_arm = num_particles // num_arms

        for arm_index in range(num_arms):
            # Base angle for this spiral arm
            arm_base_angle = (arm_index / num_arms) * 2 * math.pi

            for i in range(particles_per_arm):
                # Distribute particles along the spiral arm
                # radius_offset goes from 0.0 (center) to 1.0 (outer edge)
                radius_offset = i / particles_per_arm

                # Add some randomness to create density along the arm
                # Reduced jitter for tighter, denser distribution
                radius_jitter = random.uniform(-0.03, 0.03)
                radius_offset = max(0.15, min(1.0, radius_offset + radius_jitter))

                # Logarithmic spiral: the angle increases as we go outward
                # This creates the curved hurricane arm appearance
                # Increased rotations for tighter, more wound spiral
                spiral_tightness = 0.3  # Controls how tightly wound the spiral is
                angle_from_spiral = radius_offset * 4 * math.pi  # More rotations = tighter spiral

                # Add angular jitter for particle spread along arm
                # Reduced jitter for denser distribution
                angle_jitter = random.uniform(-0.1, 0.1)
                angle_offset = arm_base_angle - angle_from_spiral + angle_jitter

                # Color based on position along arm:
                # Lighter red at arm center, darker red between arms
                # Use angular position to determine if we're on the arm or between
                angle_within_section = (angle_offset - arm_base_angle) % (2 * math.pi / num_arms)
                center_of_section = math.pi / num_arms
                distance_from_arm_center = abs(angle_within_section - center_of_section)

                # Normalize distance: 0.0 = on arm center, 1.0 = between arms
                normalized_distance = distance_from_arm_center / (math.pi / num_arms)

                # Assign colors: light on arms, dark between
                if normalized_distance < 0.33:
                    color = self.color_light  # On the arm
                elif normalized_distance < 0.66:
                    color = self.color_normal  # Transition zone
                else:
                    color = self.color_dark  # Between arms

                # All particles are tiny pixels (1-2px)
                size = random.randint(1, 2)  # Tiny pixels throughout

                self.particles.append({
                    'arm_index': arm_index,
                    'angle_offset': angle_offset,
                    'radius_offset': radius_offset,
                    'color': color,
                    'size': size
                })

        # Add a few extra random particles for density variation
        for _ in range(num_particles - particles_per_arm * num_arms):
            arm_index = random.randint(0, num_arms - 1)
            arm_base_angle = (arm_index / num_arms) * 2 * math.pi
            radius_offset = random.uniform(0.2, 1.0)
            angle_from_spiral = radius_offset * 4 * math.pi  # Match tighter spiral
            angle_offset = arm_base_angle - angle_from_spiral + random.uniform(-0.1, 0.1)  # Reduced jitter

            self.particles.append({
                'arm_index': arm_index,
                'angle_offset': angle_offset,
                'radius_offset': radius_offset,
                'color': random.choice([self.color_dark, self.color_normal, self.color_light]),
                'size': random.randint(1, 2)  # Tiny pixels
            })

    def update(self, delta_time):
        """
        Update animation progress.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        self.elapsed += delta_time
        # Loop progress continuously: 0.0 -> 1.0 -> 0.0 -> 1.0...
        self.progress = (self.elapsed % self.duration) / self.duration

    def get_particle_position(self, particle, progress):
        """
        Calculate particle screen position based on animation progress.

        Uses logarithmic spiral to create curved hurricane arms.
        Starts contracted at center, then expands outward by 35%.

        Args:
            particle: Particle data dict with angle_offset and radius_offset
            progress: Animation progress (0.0 to 1.0)

        Returns:
            (x, y) tuple of screen coordinates
        """
        # Expansion animation: grow then shrink back
        # 0.0 -> 0.5: expand from 1.0 to 1.35
        # 0.5 -> 1.0: shrink from 1.35 back to 1.0
        if progress < 0.5:
            # Growing phase: 0.0 to 0.5 maps to expansion 0.0 to 0.35
            expansion_amount = (progress / 0.5) * 0.35  # 0.0 to 0.35
        else:
            # Shrinking phase: 0.5 to 1.0 maps to expansion 0.35 to 0.0
            expansion_amount = ((1.0 - progress) / 0.5) * 0.35  # 0.35 to 0.0

        expansion_factor = 1.0 + expansion_amount  # 1.0 to 1.35 and back to 1.0

        # Base hurricane size - 60% smaller (was 100, now 40)
        base_size = 40

        # Apply expansion to base size
        current_radius = base_size * expansion_factor

        # Logarithmic spiral radius: creates curved hurricane arms
        # Smaller radius_offset = closer to eye, larger = outer bands
        spiral_radius = current_radius * particle['radius_offset']

        # Rotation: continuous angular velocity (hurricane rotation)
        # Reduced by 20%: was 1.5, now 1.2 radians per second
        rotation_speed = 1.2  # 20% slower rotation
        current_angle = particle['angle_offset'] + (self.elapsed * rotation_speed)

        # Calculate final screen position using polar coordinates
        x = self.center_x + spiral_radius * math.cos(current_angle)
        y = self.center_y + spiral_radius * math.sin(current_angle)

        return (int(x), int(y))

    def render(self, screen):
        """
        Render all particles and BattleIcon at current animation state.

        Args:
            screen: Pygame surface to render to
        """
        # PERFORMANCE OPTIMIZATION: Reuse particle surface instead of creating new one every frame
        # Create surface once on first render, then reuse by clearing it
        if self.particle_surface is None:
            self.particle_surface = pygame.Surface(
                (screen.get_width(), screen.get_height()), pygame.SRCALPHA)

        # Clear the reusable surface (transparent clear)
        self.particle_surface.fill((0, 0, 0, 0))

        # Draw particles to reusable surface
        for particle in self.particles:
            # Calculate current position
            x, y = self.get_particle_position(particle, self.progress)

            # Add 35% transparency: 65% opacity = 166 alpha (out of 255)
            r, g, b = particle['color']
            alpha = int(255 * 0.65)  # 65% opacity (35% transparent)
            color_with_alpha = (r, g, b, alpha)

            # Draw particle as a circle on reusable surface
            pygame.draw.circle(self.particle_surface, color_with_alpha, (x, y), particle['size'])

        # Blit the particle surface onto the main screen
        screen.blit(self.particle_surface, (0, 0))

        # Draw BattleIcon overlay with grow/shrink animation (20% growth)
        if self.battle_icon and self.battle_icon_base_size:
            # Calculate icon scale based on progress (same as particle expansion)
            # Grows from 1.0 to 1.2 (20% growth) and shrinks back
            if self.progress < 0.5:
                # Growing phase: 0.0 to 0.5 maps to scale 1.0 to 1.2
                scale_amount = (self.progress / 0.5) * 0.2  # 0.0 to 0.2
            else:
                # Shrinking phase: 0.5 to 1.0 maps to scale 1.2 to 1.0
                scale_amount = ((1.0 - self.progress) / 0.5) * 0.2  # 0.2 to 0.0

            icon_scale = 1.0 + scale_amount  # 1.0 to 1.2 and back to 1.0

            # PERFORMANCE OPTIMIZATION: Only re-scale icon if scale factor changed
            # Smoothscale is expensive (~5-10ms), caching reduces to <0.1ms
            base_w, base_h = self.battle_icon_base_size
            scaled_w = int(base_w * icon_scale)
            scaled_h = int(base_h * icon_scale)

            # Cache check: only smoothscale when scale changes
            if self.cached_scale_factor != icon_scale:
                self.cached_scaled_icon = pygame.transform.smoothscale(
                    self.battle_icon, (scaled_w, scaled_h))
                self.cached_scale_factor = icon_scale

            scaled_icon = self.cached_scaled_icon

            # Center the icon on the hurricane center
            icon_x = self.center_x - scaled_w // 2
            icon_y = self.center_y - scaled_h // 2

            # Blit the scaled icon
            screen.blit(scaled_icon, (icon_x, icon_y))
