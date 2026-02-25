# -*- coding: utf-8 -*-
# ui/effects/alliance_marker_effect.py
# Alliance Marker Effect for Simultaneous Mode

"""
Alliance Marker Effect
======================

Visual effect for alliance arrival indicators in simultaneous mode.
When multiple allied armies capture the same territory, a blue particle
marker appears instead of a red battle marker.

Features:
- Hurricane-style particle effect with spiral arms (blue shades)
- Grow/shrink animation loop
- AllianceIcon overlay that scales with animation
- Clickable by the player with biggest army to assign territory

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

# Blue shades for alliance particles (clickable - player is chooser)
DARK_BLUE = (0, 0, 139)          # Dark blue - between arms
BLUE = (30, 144, 255)            # Dodger blue - transition
LIGHT_BLUE = (100, 149, 237)     # Cornflower blue - on arm centers
CYAN_ACCENT = (0, 200, 200)      # Cyan for accent particles

BLUE_SHADES = [DARK_BLUE, BLUE, LIGHT_BLUE, CYAN_ACCENT]

# Grey shades for non-clickable alliance markers (player is not the chooser)
DARK_GREY = (80, 80, 80)         # Dark grey - between arms
GREY = (130, 130, 130)           # Normal grey - transition
LIGHT_GREY = (180, 180, 180)     # Light grey - on arm centers

GREY_SHADES = [DARK_GREY, GREY, LIGHT_GREY]


class AllianceMarkerEffect:
    """
    Hurricane-style particle effect for alliance arrival indicators.

    Renders blue particles in multiple curved spiral arms that converge on
    a center point. Similar to BattleHurricaneEffect but with blue theme
    and alliance icon overlay.
    """

    def __init__(self, center_pos, alliance_icon_path="assets/mapicons/AllianceIcon1.png",
                 num_particles=600, duration=3.0, num_arms=3, greyed_out=False):
        """
        Initialize the alliance marker particle effect.

        Args:
            center_pos: (x, y) tuple for marker center (territory location)
            alliance_icon_path: Path to AllianceIcon1.png image (falls back to no icon)
            num_particles: Number of particles (600 for medium-dense effect)
            duration: Duration of one grow/shrink cycle in seconds
            num_arms: Number of spiral arms (3 for alliance look)
            greyed_out: If True, use grey colors (for non-clickable markers)
        """
        self.center_x, self.center_y = center_pos
        self.num_particles = num_particles
        self.duration = duration
        self.elapsed = 0.0
        self.progress = 0.0
        self.num_arms = num_arms
        self.greyed_out = greyed_out

        # Select color scheme based on greyed_out flag
        if greyed_out:
            self.color_light = LIGHT_GREY
            self.color_normal = GREY
            self.color_dark = DARK_GREY
            self.color_shades = GREY_SHADES
        else:
            self.color_light = LIGHT_BLUE
            self.color_normal = BLUE
            self.color_dark = DARK_BLUE
            self.color_shades = BLUE_SHADES

        # Load AllianceIcon image (optional - effect works without it)
        self.alliance_icon = None
        self.alliance_icon_base_size = None
        self.cached_scale_factor = None
        self.cached_scaled_icon = None
        self.particle_surface = None

        try:
            if os.path.exists(alliance_icon_path):
                icon_surface = pygame.image.load(alliance_icon_path).convert_alpha()
                # Scale down to 6.5% of original size
                original_w, original_h = icon_surface.get_size()
                small_w = int(original_w * 0.065)
                small_h = int(original_h * 0.065)
                icon_surface = pygame.transform.smoothscale(icon_surface, (small_w, small_h))
                self.alliance_icon = icon_surface
                self.alliance_icon_base_size = (small_w, small_h)
        except (pygame.error, FileNotFoundError) as e:
            # Effect works without icon
            pass

        # Initialize particles distributed along spiral arms
        self.particles = []
        particles_per_arm = num_particles // num_arms

        for arm_index in range(num_arms):
            arm_base_angle = (arm_index / num_arms) * 2 * math.pi

            for i in range(particles_per_arm):
                radius_offset = i / particles_per_arm

                # Add randomness for density
                radius_jitter = random.uniform(-0.04, 0.04)
                radius_offset = max(0.15, min(1.0, radius_offset + radius_jitter))

                # Logarithmic spiral for curved arms
                angle_from_spiral = radius_offset * 3.5 * math.pi
                angle_jitter = random.uniform(-0.12, 0.12)
                angle_offset = arm_base_angle - angle_from_spiral + angle_jitter

                # Color based on position
                angle_within_section = (angle_offset - arm_base_angle) % (2 * math.pi / num_arms)
                center_of_section = math.pi / num_arms
                distance_from_arm_center = abs(angle_within_section - center_of_section)
                normalized_distance = distance_from_arm_center / (math.pi / num_arms)

                if normalized_distance < 0.33:
                    color = self.color_light
                elif normalized_distance < 0.66:
                    color = self.color_normal
                else:
                    color = self.color_dark

                size = random.randint(1, 2)

                self.particles.append({
                    'arm_index': arm_index,
                    'angle_offset': angle_offset,
                    'radius_offset': radius_offset,
                    'color': color,
                    'size': size
                })

        # Extra random particles for density variation
        for _ in range(num_particles - particles_per_arm * num_arms):
            arm_index = random.randint(0, num_arms - 1)
            arm_base_angle = (arm_index / num_arms) * 2 * math.pi
            radius_offset = random.uniform(0.2, 1.0)
            angle_from_spiral = radius_offset * 3.5 * math.pi
            angle_offset = arm_base_angle - angle_from_spiral + random.uniform(-0.12, 0.12)

            self.particles.append({
                'arm_index': arm_index,
                'angle_offset': angle_offset,
                'radius_offset': radius_offset,
                'color': random.choice(self.color_shades),
                'size': random.randint(1, 2)
            })

    def update(self, delta_time):
        """Update animation progress."""
        self.elapsed += delta_time
        self.progress = (self.elapsed % self.duration) / self.duration

    def get_particle_position(self, particle, progress):
        """
        Calculate particle screen position based on animation progress.

        Args:
            particle: Particle data dict
            progress: Animation progress (0.0 to 1.0)

        Returns:
            (x, y) tuple of screen coordinates
        """
        # Expansion animation: grow then shrink
        if progress < 0.5:
            expansion_amount = (progress / 0.5) * 0.30
        else:
            expansion_amount = ((1.0 - progress) / 0.5) * 0.30

        expansion_factor = 1.0 + expansion_amount

        # Base alliance marker size (slightly smaller than battle marker)
        base_size = 35

        current_radius = base_size * expansion_factor
        spiral_radius = current_radius * particle['radius_offset']

        # Rotation: continuous angular velocity
        rotation_speed = 1.0
        current_angle = particle['angle_offset'] + (self.elapsed * rotation_speed)

        x = self.center_x + spiral_radius * math.cos(current_angle)
        y = self.center_y + spiral_radius * math.sin(current_angle)

        return (int(x), int(y))

    def render(self, screen):
        """
        Render all particles and optional AllianceIcon.

        Args:
            screen: Pygame surface to render to
        """
        # Create/reuse particle surface
        if self.particle_surface is None:
            self.particle_surface = pygame.Surface(
                (screen.get_width(), screen.get_height()), pygame.SRCALPHA)

        self.particle_surface.fill((0, 0, 0, 0))

        # Draw particles
        for particle in self.particles:
            x, y = self.get_particle_position(particle, self.progress)

            r, g, b = particle['color']
            alpha = int(255 * 0.70)  # 70% opacity
            color_with_alpha = (r, g, b, alpha)

            pygame.draw.circle(self.particle_surface, color_with_alpha, (x, y), particle['size'])

        screen.blit(self.particle_surface, (0, 0))

        # Draw AllianceIcon overlay if available
        if self.alliance_icon and self.alliance_icon_base_size:
            if self.progress < 0.5:
                scale_amount = (self.progress / 0.5) * 0.2
            else:
                scale_amount = ((1.0 - self.progress) / 0.5) * 0.2

            icon_scale = 1.0 + scale_amount

            base_w, base_h = self.alliance_icon_base_size
            scaled_w = int(base_w * icon_scale)
            scaled_h = int(base_h * icon_scale)

            if self.cached_scale_factor != icon_scale:
                self.cached_scaled_icon = pygame.transform.smoothscale(
                    self.alliance_icon, (scaled_w, scaled_h))
                self.cached_scale_factor = icon_scale

            scaled_icon = self.cached_scaled_icon

            icon_x = self.center_x - scaled_w // 2
            icon_y = self.center_y - scaled_h // 2

            screen.blit(scaled_icon, (icon_x, icon_y))
