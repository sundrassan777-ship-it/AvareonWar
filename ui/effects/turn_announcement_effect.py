"""
Turn Announcement Effect

Comprehensive turn transition effect featuring:
- Screen darkening overlay (semi-transparent black)
- Green particle explosion/recede effect
- Player turn announcement text in growing/shrinking box
- Synchronized timing across all elements
- Completion callback for game resumption

Timeline (customizable):
    0.0s - 0.5s:   Particles expand + Text box grows
    0.5s - 1.25s:  Pause with text displayed (0.75s hold)
    1.25s - 2.25s: Particles recede + Text box shrinks + Fade out
    2.25s:         Effect complete, callback triggered

Integration:
    - Triggered at turn start in game_state.py
    - Blocks all input during animation
    - Executes turn start logic via callback after completion
"""

import pygame
import math
from ui.effects.edge_wave_effect import EdgeWaveEffect

# ========================================
# CONSTANTS
# ========================================

# Overlay darkness (0.0 = transparent, 1.0 = fully black)
OVERLAY_DARKNESS = 0.85  # 85% darkness

# Text box styling
TEXT_BOX_COLOR = (40, 40, 40)  # Dark gray background
TEXT_BOX_BORDER_COLOR = (100, 255, 100)  # Bright green border
TEXT_BOX_BORDER_WIDTH = 3  # pixels

TEXT_COLOR = (255, 255, 255)  # White text
TEXT_SIZE = 60  # Font size

# Animation timing
# Reduced by 25% for faster, snappier turn transitions
PAUSE_DURATION = 0.375  # How long to hold at full expansion (seconds) (was 0.5625s, originally 0.75s)

# ========================================
# TURN ANNOUNCEMENT EFFECT CLASS
# ========================================

class TurnAnnouncementEffect:
    """
    Combined turn announcement effect with particles, overlay, and text.

    Manages three synchronized elements:
    1. Darkening screen overlay
    2. Green particle effect (EdgeWaveEffect)
    3. Player turn announcement text box

    All elements expand, pause, and recede together in perfect sync.
    """

    def __init__(self, screen_width, screen_height, player_number,
                 num_particles=600, on_complete=None):
        """
        Initialize the turn announcement effect.

        Args:
            screen_width: Width of the game window
            screen_height: Height of the game window
            player_number: The player number to display (1, 2, 3, etc.)
            num_particles: Number of green particles (default 600)
            on_complete: Callback function to call when effect completes
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.player_number = player_number
        self.on_complete = on_complete

        self.elapsed = 0.0
        self.is_complete = False

        # Center of screen for text positioning
        self.center_x = screen_width / 2
        self.center_y = screen_height / 2

        # Create the particle effect with custom pause duration
        # We need to temporarily modify PAUSE_DURATION in edge_wave_effect
        # Or we can manage timing ourselves - let's manage it ourselves
        self.particle_effect = EdgeWaveEffect(
            screen_width,
            screen_height,
            num_particles=num_particles
        )

        # Override the particle effect's pause duration
        import ui.effects.edge_wave_effect as wave_module
        self.original_pause_duration = wave_module.PAUSE_DURATION
        wave_module.PAUSE_DURATION = PAUSE_DURATION
        wave_module.TOTAL_DURATION = (wave_module.EXPLOSION_DURATION +
                                      PAUSE_DURATION +
                                      wave_module.RECEDE_DURATION)

        # Recreate particle effect with new timing
        self.particle_effect = EdgeWaveEffect(
            screen_width,
            screen_height,
            num_particles=num_particles
        )

        # Font for text
        try:
            self.font = pygame.font.Font(None, TEXT_SIZE)
        except Exception:
            self.font = pygame.font.SysFont('arial', TEXT_SIZE)

        # Generate text surface
        self.text = f"Player {player_number}'s Turn"
        self.text_surface = self.font.render(self.text, True, TEXT_COLOR)
        self.text_width = self.text_surface.get_width()
        self.text_height = self.text_surface.get_height()

        # Text box padding
        self.box_padding = 40  # pixels around text

        # Calculate full text box size
        self.full_box_width = self.text_width + (self.box_padding * 2)
        self.full_box_height = self.text_height + (self.box_padding * 2)

        # PERFORMANCE: Cache smoothscaled text surfaces by quantized size
        self._scaled_text_cache = {}

        # Track phases for synchronized animation
        self.explosion_duration = wave_module.EXPLOSION_DURATION
        self.pause_duration = PAUSE_DURATION
        self.recede_duration = wave_module.RECEDE_DURATION
        self.total_duration = wave_module.TOTAL_DURATION

    def update(self, delta_time):
        """
        Update the effect animation.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        if self.is_complete:
            return

        self.elapsed += delta_time

        # Update particle effect
        self.particle_effect.update(delta_time)

        # Check if complete
        if self.elapsed >= self.total_duration:
            self.is_complete = True

            # Call completion callback
            if self.on_complete:
                self.on_complete()

    def render(self, screen):
        """
        Render the turn announcement effect.

        Rendering order:
        1. Darkening overlay
        2. Particle effect
        3. Text box with border
        4. Text

        Args:
            screen: Pygame surface to render to
        """
        if self.is_complete:
            return

        # 1. Render darkening overlay
        self._render_overlay(screen)

        # 2. Render particle effect
        self.particle_effect.render(screen)

        # 3. Render text box and text
        self._render_text_box(screen)

    def _render_overlay(self, screen):
        """Render semi-transparent black overlay to darken the screen."""
        # PERFORMANCE: Non-SRCALPHA surface + set_alpha (per-surface alpha is faster than per-pixel)
        if not hasattr(self, '_cached_overlay') or self._cached_overlay is None:
            self._cached_overlay = pygame.Surface((self.screen_width, self.screen_height))
            self._cached_overlay.fill((0, 0, 0))
        overlay = self._cached_overlay

        # Calculate overlay opacity based on phase
        if self.elapsed < self.explosion_duration:
            progress = self.elapsed / self.explosion_duration
            opacity = progress * OVERLAY_DARKNESS
        elif self.elapsed < self.explosion_duration + self.pause_duration:
            opacity = OVERLAY_DARKNESS
        else:
            recede_time = self.elapsed - (self.explosion_duration + self.pause_duration)
            progress = recede_time / self.recede_duration
            opacity = (1.0 - progress) * OVERLAY_DARKNESS

        # Per-surface alpha: single multiply during blit instead of per-pixel
        alpha = int(255 * opacity)
        overlay.set_alpha(alpha)
        screen.blit(overlay, (0, 0))

    def _render_text_box(self, screen):
        """Render the text box that grows/shrinks with animation."""
        # Calculate current box size based on phase
        if self.elapsed < self.explosion_duration:
            # Grow during explosion (ease-out cubic to match particles)
            progress = self.elapsed / self.explosion_duration
            eased_progress = 1 - math.pow(1 - progress, 3)
            scale = eased_progress
            text_opacity = min(1.0, progress * 2.0)  # Fade in text
        elif self.elapsed < self.explosion_duration + self.pause_duration:
            # Full size during pause
            scale = 1.0
            text_opacity = 1.0
        else:
            # Shrink during recede (ease-in cubic to match particles)
            recede_time = self.elapsed - (self.explosion_duration + self.pause_duration)
            progress = recede_time / self.recede_duration
            eased_progress = math.pow(progress, 3)
            scale = 1.0 - eased_progress

            # Fade out text
            text_opacity = 1.0 - progress

        # Calculate current box dimensions
        current_box_width = int(self.full_box_width * scale)
        current_box_height = int(self.full_box_height * scale)

        # Calculate box position (centered on screen)
        box_x = int(self.center_x - current_box_width / 2)
        box_y = int(self.center_y - current_box_height / 2)

        # Don't render if box is too small
        if current_box_width < 10 or current_box_height < 10:
            return

        # Create surface for box with alpha
        box_surface = pygame.Surface((current_box_width, current_box_height), pygame.SRCALPHA)

        # Draw background
        bg_alpha = int(255 * text_opacity * 0.9)  # Slightly transparent
        pygame.draw.rect(box_surface, (*TEXT_BOX_COLOR, bg_alpha),
                        box_surface.get_rect())

        # Draw border
        border_alpha = int(255 * text_opacity)
        pygame.draw.rect(box_surface, (*TEXT_BOX_BORDER_COLOR, border_alpha),
                        box_surface.get_rect(), TEXT_BOX_BORDER_WIDTH)

        # Blit box to screen
        screen.blit(box_surface, (box_x, box_y))

        # Render text if box is large enough (> 20% of full size)
        if scale > 0.2:
            # Scale the text to match box size
            scaled_text_width = int(self.text_width * scale)
            scaled_text_height = int(self.text_height * scale)

            # Only render if text is visible
            if scaled_text_width > 5 and scaled_text_height > 5:
                # Scale the text surface
                # PERFORMANCE: Cache smoothscale by quantized size (avoid per-frame smoothscale)
                q_tw = max(5, ((scaled_text_width + 2) // 5) * 5)
                q_th = max(5, ((scaled_text_height + 2) // 5) * 5)
                cache_key = (q_tw, q_th)
                if cache_key not in self._scaled_text_cache:
                    self._scaled_text_cache[cache_key] = pygame.transform.smoothscale(
                        self.text_surface, (q_tw, q_th))
                scaled_text = self._scaled_text_cache[cache_key]

                # Apply opacity to scaled text
                scaled_text.set_alpha(int(255 * text_opacity))

                # Calculate text position (centered in box)
                text_x = int(self.center_x - scaled_text_width / 2)
                text_y = int(self.center_y - scaled_text_height / 2)

                # Blit scaled text
                screen.blit(scaled_text, (text_x, text_y))

    def is_finished(self):
        """
        Check if the effect has completed.

        Returns:
            bool: True if effect is finished, False otherwise
        """
        return self.is_complete

    def cleanup(self):
        """Clean up resources and restore original module constants."""
        # Restore original pause duration
        import ui.effects.edge_wave_effect as wave_module
        wave_module.PAUSE_DURATION = self.original_pause_duration
        wave_module.TOTAL_DURATION = (wave_module.EXPLOSION_DURATION +
                                      self.original_pause_duration +
                                      wave_module.RECEDE_DURATION)
