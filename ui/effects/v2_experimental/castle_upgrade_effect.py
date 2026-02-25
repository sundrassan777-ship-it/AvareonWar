"""
Castle Upgrade Effect

Visual effect for Keep -> Castle upgrades featuring:
- Golden particle explosion with motion trails (thick particles + trailing lines)
- Pre-rendered radial glow core with additive blending (peaks during explosion)
- Three animation phases:
  1. Initial explosion outward with glow (0-0.5s)
  2. Circular swirling with fading glow (0.5-2.5s)
  3. Upward float, fade out, and rising golden light pillar (2.5-3.5s)
- Pygame primitives only - no custom particle assets

Inspired by BFME2 War of the Ring mode castle upgrade visuals.

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

# Particle sizes (upgraded from 1px to 2-3px)
PARTICLE_SIZE_MIN = 2
PARTICLE_SIZE_MAX = 3

# Motion trail length (angular offset behind particle for trailing line)
TRAIL_ANGLE_OFFSET = 0.15

# Central glow constants
GLOW_SIZE = 60
GLOW_CENTER_ALPHA = 140

# Rising light pillar during float phase
PILLAR_BASE_WIDTH = 8
PILLAR_TIP_WIDTH = 2
PILLAR_MAX_HEIGHT = 50     # Max height of rising pillar
PILLAR_SEGMENTS = 5


# ========================================
# CASTLE UPGRADE EFFECT CLASS
# ========================================

class CastleUpgradeEffect:
    """
    Enhanced golden particle explosion effect for Keep -> Castle upgrades.

    Three-phase animation with motion trails, central glow, and rising light pillar:
    1. Explosion: Particles burst outward with trailing lines + bright central glow
    2. Swirl: Particles orbit with trails + glow fades gradually
    3. Float: Particles drift upward + golden light pillar rises from center

    Uses Pygame circle/line/polygon primitives - no custom particle assets.
    """

    def __init__(self, center_pos, num_particles=140, world_coords=False):
        """
        Initialize the castle upgrade particle effect.

        Args:
            center_pos: (x, y) tuple for effect center (castle location)
            num_particles: Number of particles (default 140)
            world_coords: If True, center_pos is in world coordinates
        """
        self.world_coords = world_coords
        if world_coords:
            self.world_center_x, self.world_center_y = center_pos
            self.center_x, self.center_y = center_pos
        else:
            self.center_x, self.center_y = center_pos
            self.world_center_x, self.world_center_y = center_pos

        self.num_particles = num_particles
        self.elapsed = 0.0
        self.is_complete = False

        # PERFORMANCE: Reuse rendering surface instead of creating new one each frame
        self._cached_surface = None
        self._cached_surface_size = (0, 0)

        # Pre-render central glow surface for additive blending
        self.glow_surface = self._create_glow_surface()

        # Initialize particles with random properties
        self.particles = []
        for i in range(num_particles):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(62, 156)
            color = random.choice(GOLD_SHADES)
            size = random.randint(PARTICLE_SIZE_MIN, PARTICLE_SIZE_MAX)
            rotation_speed = random.uniform(-1.2, 1.2)
            swirl_radius_factor = random.uniform(0.8, 1.2)
            float_speed = random.uniform(15, 30)

            self.particles.append({
                'angle': angle,
                'speed': speed,
                'color': color,
                'size': size,
                'rotation_speed': rotation_speed,
                'swirl_radius_factor': swirl_radius_factor,
                'float_speed': float_speed,
                # Position offset from center (world space)
                'offset_x': 0.0,
                'offset_y': 0.0,
                # Previous offset for motion trail
                'prev_offset_x': 0.0,
                'prev_offset_y': 0.0,
                # Extra vertical offset for float phase
                'float_offset_y': 0.0
            })

    def _create_glow_surface(self):
        """Pre-render a golden radial gradient glow surface."""
        surface = pygame.Surface((GLOW_SIZE, GLOW_SIZE), pygame.SRCALPHA)
        center = GLOW_SIZE // 2
        r, g, b = LIGHT_GOLD
        for radius in range(center, 0, -1):
            t = radius / center
            alpha = int(GLOW_CENTER_ALPHA * (1.0 - t * t))
            pygame.draw.circle(surface, (r, g, b, alpha), (center, center), radius)
        return surface

    def update(self, delta_time):
        """
        Update particle positions based on current animation phase.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        if self.is_complete:
            return

        self.elapsed += delta_time

        if self.elapsed >= TOTAL_DURATION:
            self.is_complete = True
            return

        if self.elapsed < EXPLOSION_DURATION:
            self._update_explosion(delta_time)
        elif self.elapsed < EXPLOSION_DURATION + SWIRL_DURATION:
            self._update_swirl(delta_time)
        else:
            self._update_float(delta_time)

    def _update_explosion(self, delta_time):
        """Update particles during explosion phase with deceleration and early swirl."""
        explosion_progress = self.elapsed / EXPLOSION_DURATION
        decel_factor = math.exp(-3.0 * explosion_progress)

        for particle in self.particles:
            # Save previous position for motion trail
            particle['prev_offset_x'] = particle['offset_x']
            particle['prev_offset_y'] = particle['offset_y']

            current_speed = particle['speed'] * decel_factor
            distance = current_speed * delta_time

            rotation_influence = explosion_progress
            particle['angle'] += particle['rotation_speed'] * delta_time * rotation_influence

            particle['offset_x'] += distance * math.cos(particle['angle'])
            particle['offset_y'] += distance * math.sin(particle['angle'])

    def _update_swirl(self, delta_time):
        """Update particles during swirl phase - seamless continuation of rotation."""
        for particle in self.particles:
            particle['prev_offset_x'] = particle['offset_x']
            particle['prev_offset_y'] = particle['offset_y']

            current_radius = math.sqrt(particle['offset_x'] ** 2 + particle['offset_y'] ** 2)

            if current_radius > 0.1:
                current_angle = math.atan2(particle['offset_y'], particle['offset_x'])
                current_angle += particle['rotation_speed'] * delta_time

                particle['offset_x'] = current_radius * math.cos(current_angle)
                particle['offset_y'] = current_radius * math.sin(current_angle)

    def _update_float(self, delta_time):
        """Update particles during float and fade phase."""
        for particle in self.particles:
            particle['prev_offset_x'] = particle['offset_x']
            particle['prev_offset_y'] = particle['offset_y']
            particle['float_offset_y'] -= particle['float_speed'] * delta_time

    def render(self, screen, world_to_screen_func=None):
        """
        Render particles, motion trails, glow, and rising pillar.

        Args:
            screen: Pygame surface to render to
            world_to_screen_func: Function to convert world coords to screen coords
        """
        if self.is_complete:
            return

        # Update screen center if using world coordinates
        if self.world_coords and world_to_screen_func:
            self.center_x, self.center_y = world_to_screen_func(
                (self.world_center_x, self.world_center_y))

        # PERFORMANCE: Reuse temporary surface
        sw, sh = screen.get_width(), screen.get_height()
        if self._cached_surface is None or self._cached_surface_size != (sw, sh):
            self._cached_surface = pygame.Surface((sw, sh), pygame.SRCALPHA)
            self._cached_surface_size = (sw, sh)
        temp_surface = self._cached_surface
        temp_surface.fill((0, 0, 0, 0))

        # Calculate opacity based on phase
        if self.elapsed < EXPLOSION_DURATION + SWIRL_DURATION:
            opacity = 1.0
        else:
            phase_elapsed = self.elapsed - (EXPLOSION_DURATION + SWIRL_DURATION)
            fade_progress = phase_elapsed / FLOAT_DURATION
            opacity = 1.0 - fade_progress

        # --- Layer 1: Motion trails + particles ---
        for particle in self.particles:
            world_x = self.world_center_x + particle['offset_x']
            world_y = self.world_center_y + particle['offset_y'] + particle['float_offset_y']

            if self.world_coords and world_to_screen_func:
                screen_x, screen_y = world_to_screen_func((world_x, world_y))
            else:
                screen_x = self.center_x + particle['offset_x']
                screen_y = self.center_y + particle['offset_y'] + particle['float_offset_y']

            x = int(screen_x)
            y = int(screen_y)

            if x < -10 or x > sw + 10 or y < -10 or y > sh + 10:
                continue

            r, g, b = particle['color']
            alpha = int(255 * opacity)
            color_with_alpha = (r, g, b, alpha)

            # Draw motion trail line (from previous position to current)
            prev_world_x = self.world_center_x + particle['prev_offset_x']
            prev_world_y = self.world_center_y + particle['prev_offset_y'] + particle['float_offset_y']

            if self.world_coords and world_to_screen_func:
                prev_sx, prev_sy = world_to_screen_func((prev_world_x, prev_world_y))
            else:
                prev_sx = self.center_x + particle['prev_offset_x']
                prev_sy = self.center_y + particle['prev_offset_y'] + particle['float_offset_y']

            px, py = int(prev_sx), int(prev_sy)

            # Trail line (dimmer than particle head)
            trail_alpha = int(alpha * 0.4)
            if trail_alpha > 5 and (abs(x - px) > 1 or abs(y - py) > 1):
                pygame.draw.line(
                    temp_surface, (r, g, b, trail_alpha),
                    (px, py), (x, y), max(1, particle['size'] - 1)
                )

            # Particle head (bright circle)
            pygame.draw.circle(temp_surface, color_with_alpha, (x, y), particle['size'])

        screen.blit(temp_surface, (0, 0))

        # --- Layer 2: Central glow (strongest during explosion, fades during swirl, off during float) ---
        if self.elapsed < EXPLOSION_DURATION + SWIRL_DURATION:
            self._render_glow(screen)

        # --- Layer 3: Rising light pillar (float phase only) ---
        if self.elapsed >= EXPLOSION_DURATION + SWIRL_DURATION:
            self._render_rising_pillar(screen, opacity)

    def _render_glow(self, screen):
        """Render central glow with intensity based on phase."""
        if self.elapsed < EXPLOSION_DURATION:
            # Full intensity during explosion
            glow_intensity = 1.0
        else:
            # Fade out during swirl phase
            swirl_elapsed = self.elapsed - EXPLOSION_DURATION
            glow_intensity = 1.0 - (swirl_elapsed / SWIRL_DURATION) * 0.8  # Fades to 20%

        # Pulse the glow scale
        pulse = 1.0 + 0.2 * math.sin(self.elapsed * 4.0) * glow_intensity
        scaled_size = int(GLOW_SIZE * pulse)

        if scaled_size < 4:
            return

        scaled_glow = pygame.transform.scale(self.glow_surface, (scaled_size, scaled_size))

        # Apply intensity by adjusting the surface alpha
        if glow_intensity < 1.0:
            scaled_glow.set_alpha(int(255 * glow_intensity))

        glow_x = self.center_x - scaled_size // 2
        glow_y = self.center_y - scaled_size // 2
        screen.blit(scaled_glow, (glow_x, glow_y), special_flags=pygame.BLEND_RGBA_ADD)

    def _render_rising_pillar(self, screen, opacity):
        """
        Render a golden light pillar rising from center during float phase.
        Pillar grows upward and fades out with the rest of the effect.
        """
        phase_elapsed = self.elapsed - (EXPLOSION_DURATION + SWIRL_DURATION)
        pillar_progress = phase_elapsed / FLOAT_DURATION  # 0.0 to 1.0

        # Pillar height grows during float phase
        pillar_height = PILLAR_MAX_HEIGHT * min(1.0, pillar_progress * 2.0)  # Reaches max at 50%

        if pillar_height < 2:
            return

        # Create a small surface for the pillar
        pw = PILLAR_BASE_WIDTH + 4
        ph = int(pillar_height) + 4
        pillar_surface = pygame.Surface((pw, ph), pygame.SRCALPHA)

        cx_local = pw // 2

        r, g, b = LIGHT_GOLD

        # Draw pillar as gradient trapezoid segments (bottom to top, fading)
        for seg in range(PILLAR_SEGMENTS):
            seg_start = seg / PILLAR_SEGMENTS
            seg_end = (seg + 1) / PILLAR_SEGMENTS

            y_start = ph - 2 - int(seg_start * pillar_height)
            y_end = ph - 2 - int(seg_end * pillar_height)

            w_start = (PILLAR_BASE_WIDTH + (PILLAR_TIP_WIDTH - PILLAR_BASE_WIDTH) * seg_start) / 2
            w_end = (PILLAR_BASE_WIDTH + (PILLAR_TIP_WIDTH - PILLAR_BASE_WIDTH) * seg_end) / 2

            # Alpha fades toward top and with overall opacity
            seg_alpha = int(255 * opacity * (1.0 - seg_start * 0.7))
            if seg_alpha < 5:
                continue

            points = [
                (cx_local - w_start, y_start),
                (cx_local + w_start, y_start),
                (cx_local + w_end, y_end),
                (cx_local - w_end, y_end),
            ]
            pygame.draw.polygon(pillar_surface, (r, g, b, seg_alpha), points)

            # Bright core line
            core_alpha = int(seg_alpha * 0.5)
            if core_alpha > 5:
                cr = min(255, r + 60)
                cg = min(255, g + 60)
                cb = min(255, b + 60)
                pygame.draw.line(
                    pillar_surface, (cr, cg, cb, core_alpha),
                    (cx_local, y_start), (cx_local, y_end), 1
                )

        # Blit pillar centered on effect position, growing upward
        blit_x = self.center_x - pw // 2
        blit_y = self.center_y - ph + 2
        screen.blit(pillar_surface, (int(blit_x), int(blit_y)))

    def is_finished(self):
        """Check if the effect has completed."""
        return self.is_complete
