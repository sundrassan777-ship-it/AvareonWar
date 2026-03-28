"""
Ability Silence Wave Effect

Full-screen crimson particle wave sweeping left to right for Vow of Silence.
A dense wall of red ember particles crashes across the screen in a wavy pattern,
leaving trailing sparks that drift upward and fade.

Visual design:
- Screen-space effect (not world coordinates) — covers full screen regardless of camera
- ~800 dense particles form a thick wave band that fully obscures the tint edge
- Wave front is wavy/organic (sine-based per-row offset), not a straight vertical line
- Soft-edged red tint overlay follows the wave front (gradient fade at leading edge)
- Total duration: ~2.5s (1.5s sweep + 1.0s fade)

Integration:
    - Triggered from MapRenderer.trigger_ability_effect() for Vow of Silence
    - Managed in MapRenderer.ability_effects list (auto-removed when finished)
"""

import pygame
import math
import random

# ========================================
# CONSTANTS
# ========================================

# Animation phase durations (in seconds)
SWEEP_DURATION = 1.5       # Phase 1: Wave sweeps from left to right
FADE_DURATION = 1.0        # Phase 2: Trailing embers fade out
TOTAL_DURATION = SWEEP_DURATION + FADE_DURATION  # 2.5s

# Wave band properties
WAVE_BAND_WIDTH = 300      # Width of the particle wave band (px) — wider for full coverage

# Wavy front: sine-based per-row offset so the wave crashes organically
WAVE_AMPLITUDE = 60        # Max horizontal offset from base wave front (px)
WAVE_FREQUENCY = 3.0       # Number of sine cycles across screen height

# Particle physics
PARTICLE_DRIFT_Y_MIN = -20   # Min upward drift speed (px/s, negative = up)
PARTICLE_DRIFT_Y_MAX = -60   # Max upward drift speed (px/s)
PARTICLE_SCATTER_Y = 15      # Random vertical scatter from initial position (px)

# Tint overlay
TINT_ALPHA = 30              # Peak alpha of red tint overlay behind wave front
TINT_GRADIENT_WIDTH = 120    # Width of soft gradient at tint leading edge (px)
TINT_GRADIENT_STEPS = 8      # Number of gradient strips (balance quality vs perf)

# Color palette: 5 shades of crimson/dark red
SILENCE_PALETTE = [
    (100, 0, 0),
    (160, 20, 20),
    (200, 40, 40),
    (255, 60, 60),
    (255, 100, 80),
]

# ========================================
# ABILITY SILENCE WAVE EFFECT CLASS
# ========================================

class AbilitySilenceWaveEffect:
    """
    Full-screen crimson particle wave for Vow of Silence.

    Two-phase animation:
    1. Sweep: A dense, wavy band of red ember particles crashes from left edge
       to right edge. A soft-edged red tint follows behind the wave front.
    2. Fade: All remaining particles drift upward and fade out. Tint fades to 0.

    Screen-space effect — position is independent of camera/world coordinates.
    """

    def __init__(self, screen_width, screen_height, num_particles=800):
        """
        Args:
            screen_width: Width of the screen
            screen_height: Height of the screen
            num_particles: Number of ember particles (default 800 for dense coverage)
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.num_particles = num_particles
        self.elapsed = 0.0
        self.is_complete = False
        self._cached_surface = None

        # Pre-compute per-row wavy offset (sine wave across screen height)
        # Used to make the wave front organic instead of a straight vertical line
        self._wave_offsets = []
        for row_y in range(screen_height):
            # Sine wave with slight randomness baked in at init for natural look
            offset = WAVE_AMPLITUDE * math.sin(
                WAVE_FREQUENCY * 2 * math.pi * row_y / screen_height
            )
            self._wave_offsets.append(offset)

        # Initialize particles distributed across the wave band
        # Dense enough to fully cover the tint edge behind them
        self.particles = []
        for _ in range(num_particles):
            # Vertical position: random across full screen height
            y = random.uniform(-20, screen_height + 20)
            # X offset within the wave band
            x_offset = random.uniform(0, WAVE_BAND_WIDTH)
            # Vertical scatter for ragged look
            y_scatter = random.uniform(-PARTICLE_SCATTER_Y, PARTICLE_SCATTER_Y)
            # Upward drift speed (embers float up)
            drift_y = random.uniform(PARTICLE_DRIFT_Y_MIN, PARTICLE_DRIFT_Y_MAX)
            # Color from crimson palette
            color = random.choice(SILENCE_PALETTE)
            # Particle size: 2-3px for dense coverage
            size = random.randint(2, 3)
            # Individual speed variation (tight range so band stays cohesive)
            speed_factor = random.uniform(0.9, 1.1)

            self.particles.append({
                'base_y': y + y_scatter,
                'x_offset': x_offset,
                'drift_y': drift_y,
                'color': color,
                'size': size,
                'speed_factor': speed_factor,
                # Accumulated vertical drift (applied during and after sweep)
                'accumulated_drift_y': 0.0,
            })

    def update(self, delta_time):
        """Update wave position and particle drift."""
        if self.is_complete:
            return

        self.elapsed += delta_time

        if self.elapsed >= TOTAL_DURATION:
            self.is_complete = True
            return

        # Update vertical drift for all particles (embers float upward continuously)
        for particle in self.particles:
            particle['accumulated_drift_y'] += particle['drift_y'] * delta_time

    def _get_wave_offset(self, y):
        """Get the wavy x-offset for a given y position (sine-based)."""
        row = max(0, min(int(y), self.screen_height - 1))
        return self._wave_offsets[row]

    def render(self, screen, world_to_screen_func=None):
        """
        Render the wave effect. world_to_screen_func is accepted but ignored
        (screen-space effect, included for interface compatibility with ability_effects list).
        """
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

        # Calculate base wave front position
        if self.elapsed < SWEEP_DURATION:
            # Sweep phase: wave front moves from left to right
            sweep_progress = self.elapsed / SWEEP_DURATION
            # Ease-in-out for smooth motion
            sweep_smooth = sweep_progress * sweep_progress * (3 - 2 * sweep_progress)
            # Base wave front x position (from -WAVE_BAND_WIDTH to screen_width)
            base_wave_x = -WAVE_BAND_WIDTH + (self.screen_width + WAVE_BAND_WIDTH) * sweep_smooth
            particle_opacity = 1.0
            tint_fade = 1.0
        else:
            # Fade phase: wave has passed, particles linger and fade
            fade_elapsed = self.elapsed - SWEEP_DURATION
            fade_progress = fade_elapsed / FADE_DURATION
            base_wave_x = self.screen_width + WAVE_BAND_WIDTH  # Wave has passed off-screen
            particle_opacity = max(0.0, 1.0 - fade_progress)
            tint_fade = max(0.0, 1.0 - fade_progress)

        # Draw red tint overlay with soft gradient at leading edge
        # The tint covers everything behind the wave front, with a gradient fade at the edge
        current_tint_alpha = int(TINT_ALPHA * tint_fade)
        if current_tint_alpha > 0:
            # Use the middle of the screen for the wavy offset reference
            mid_wave_offset = self._get_wave_offset(self.screen_height // 2)
            tint_right_base = base_wave_x + WAVE_BAND_WIDTH * 0.5 + mid_wave_offset

            # Solid tint region (well behind the wave front)
            solid_right = int(max(0, tint_right_base - TINT_GRADIENT_WIDTH))
            if solid_right > 0:
                temp_surface.fill((120, 0, 0, current_tint_alpha),
                                  (0, 0, min(solid_right, self.screen_width),
                                   self.screen_height))

            # Gradient strips from solid_right to tint_right_base (softens the edge)
            strip_width = max(1, TINT_GRADIENT_WIDTH // TINT_GRADIENT_STEPS)
            for i in range(TINT_GRADIENT_STEPS):
                strip_x = solid_right + i * strip_width
                if strip_x >= self.screen_width:
                    break
                if strip_x < 0:
                    continue
                # Alpha fades from current_tint_alpha to 0 across gradient
                grad_alpha = int(current_tint_alpha * (1.0 - i / TINT_GRADIENT_STEPS))
                if grad_alpha > 0:
                    w = min(strip_width, self.screen_width - strip_x)
                    temp_surface.fill((120, 0, 0, grad_alpha),
                                      (strip_x, 0, w, self.screen_height))

        # Draw particles with wavy offset applied to each particle's y-position
        for particle in self.particles:
            # Particle y: base position + accumulated upward drift
            py = particle['base_y'] + particle['accumulated_drift_y']
            # Get wavy x offset for this particle's y position
            wave_offset = self._get_wave_offset(py)
            # Calculate particle x position: base wave front + wave offset + individual offset
            px = base_wave_x + wave_offset + particle['x_offset'] * particle['speed_factor']

            x = int(px)
            y = int(py)

            # Skip off-screen particles
            if (x < -10 or x > self.screen_width + 10
                    or y < -20 or y > self.screen_height + 20):
                continue

            r, g, b = particle['color']
            alpha = int(255 * max(0.0, particle_opacity))
            if alpha <= 0:
                continue

            pygame.draw.circle(temp_surface, (r, g, b, alpha), (x, y),
                               particle['size'])

        screen.blit(temp_surface, (0, 0))

    def is_finished(self):
        """Check if the effect has completed."""
        return self.is_complete
