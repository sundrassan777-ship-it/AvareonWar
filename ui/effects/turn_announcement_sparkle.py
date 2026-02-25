"""
Turn Announcement Effect with Sparkle Particles

Alternative version using sparkle effect instead of expanding rectangle.

Comprehensive turn transition effect featuring:
- Screen darkening overlay (semi-transparent black)
- Random green sparkle particles across screen
- Player turn announcement text in growing/shrinking box
- Synchronized timing across all elements
- Completion callback for game resumption

Timeline (customizable):
    0.0s - 0.375s: Screen darkens + Sparkles begin + Text box grows
    0.375s - 0.75s: Hold with sparkles + Text displayed
    0.75s - 1.5s: Sparkles fade + Text box shrinks + Screen lightens
    1.5s: Effect complete, callback triggered

Integration:
    - Triggered at turn start in game_state.py
    - Blocks all input during animation
    - Executes turn start logic via callback after completion
"""

import pygame
import math
from ui.effects.sparkle_effect import SparkleEffect

# ========================================
# CONSTANTS
# ========================================

# Overlay darkness (0.0 = transparent, 1.0 = fully black)
OVERLAY_DARKNESS = 0.68  # 68% darkness (was 85%, reduced by 20%)

# Text box styling
TEXT_BOX_COLOR = (40, 40, 40)  # Dark gray background
TEXT_BOX_BORDER_COLOR = (218, 165, 32)  # Golden border (goldenrod)
TEXT_BOX_BORDER_WIDTH = 3  # pixels

TEXT_COLOR = (255, 255, 255)  # White text
TEXT_SIZE = 60  # Font size

# Animation timing
# Reduced by 25% for faster, snappier turn transitions
PAUSE_DURATION = 0.375  # How long to hold at full expansion (seconds)

# ========================================
# TURN ANNOUNCEMENT EFFECT CLASS
# ========================================

class TurnAnnouncementEffect:
    """
    Combined turn announcement effect with sparkle particles, overlay, and text.

    Manages three synchronized elements:
    1. Darkening screen overlay
    2. Random sparkle particle effect (SparkleEffect)
    3. Player turn announcement text box

    All elements expand, pause, and recede together in perfect sync.
    """

    def __init__(self, screen_width, screen_height, player_number=None,
                 player_name=None, custom_text=None, on_complete=None):
        """
        Initialize the turn announcement effect.

        Args:
            screen_width: Width of the game window
            screen_height: Height of the game window
            player_number: The player number to display (1, 2, 3, etc.) - used if player_name not provided
            player_name: Custom player name to display (e.g., "Empire of Naragonthid")
            custom_text: Fully custom text to display (e.g., "Turn 1" for simultaneous mode)
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

        # Animation phase durations (matching original timing)
        self.explosion_duration = 0.375  # Text grows
        self.pause_duration = PAUSE_DURATION
        self.recede_duration = 0.75  # Text shrinks
        self.total_duration = self.explosion_duration + self.pause_duration + self.recede_duration

        # Create the sparkle particle effect
        # Duration matches total effect duration
        self.sparkle_effect = SparkleEffect(
            screen_width,
            screen_height,
            duration=self.total_duration
        )

        # Font for text
        try:
            self.font = pygame.font.Font(None, TEXT_SIZE)
        except Exception:
            self.font = pygame.font.SysFont('arial', TEXT_SIZE)

        # Generate text surface - priority: custom_text > player_name > player_number
        if custom_text:
            self.text = custom_text
        elif player_name:
            self.text = f"{player_name}'s Turn"
        else:
            self.text = f"Player {player_number}'s Turn"

        # Smart wrapping: if text too wide for screen, split into two lines
        max_text_width = int(screen_width * 0.75)
        single_line = self.font.render(self.text, True, TEXT_COLOR)
        if single_line.get_width() > max_text_width and player_name:
            # Two lines: player name on top, "'s Turn" below
            line1 = self.font.render(player_name, True, TEXT_COLOR)
            line2 = self.font.render("'s Turn", True, TEXT_COLOR)
            line_spacing = 6
            total_w = max(line1.get_width(), line2.get_width())
            total_h = line1.get_height() + line_spacing + line2.get_height()
            # Compose into a single SRCALPHA surface (centered per line)
            self.text_surface = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
            self.text_surface.blit(line1, ((total_w - line1.get_width()) // 2, 0))
            self.text_surface.blit(line2, ((total_w - line2.get_width()) // 2,
                                           line1.get_height() + line_spacing))
        else:
            self.text_surface = single_line

        self.text_width = self.text_surface.get_width()
        self.text_height = self.text_surface.get_height()

        # Text box padding
        self.box_padding = 40  # pixels around text

        # Calculate full text box size
        self.full_box_width = self.text_width + (self.box_padding * 2)
        self.full_box_height = self.text_height + (self.box_padding * 2)

    def update(self, delta_time):
        """
        Update the effect animation.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        if self.is_complete:
            return

        self.elapsed += delta_time

        # Update sparkle effect
        self.sparkle_effect.update(delta_time)

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
        2. Sparkle particle effect
        3. Text box with border
        4. Text

        Args:
            screen: Pygame surface to render to
        """
        if self.is_complete:
            return

        # 1. Render darkening overlay
        self._render_overlay(screen)

        # 2. Render sparkle effect
        self.sparkle_effect.render(screen)

        # 3. Render text box and text
        self._render_text_box(screen)

    def _render_overlay(self, screen):
        """Render semi-transparent black overlay to darken the screen."""
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)

        # Calculate overlay opacity based on phase
        if self.elapsed < self.explosion_duration:
            # Fade in during explosion
            progress = self.elapsed / self.explosion_duration
            opacity = progress * OVERLAY_DARKNESS
        elif self.elapsed < self.explosion_duration + self.pause_duration:
            # Full darkness during pause
            opacity = OVERLAY_DARKNESS
        else:
            # Fade out during recede
            recede_time = self.elapsed - (self.explosion_duration + self.pause_duration)
            progress = recede_time / self.recede_duration
            opacity = (1.0 - progress) * OVERLAY_DARKNESS

        # Draw overlay
        alpha = int(255 * opacity)
        overlay.fill((0, 0, 0, alpha))
        screen.blit(overlay, (0, 0))

    def _render_text_box(self, screen):
        """Render the text box that grows/shrinks with animation."""
        # Calculate current box size based on phase
        if self.elapsed < self.explosion_duration:
            # Grow during explosion (ease-out cubic)
            progress = self.elapsed / self.explosion_duration
            eased_progress = 1 - math.pow(1 - progress, 3)
            scale = eased_progress
            text_opacity = min(1.0, progress * 2.0)  # Fade in text
        elif self.elapsed < self.explosion_duration + self.pause_duration:
            # Full size during pause
            scale = 1.0
            text_opacity = 1.0
        else:
            # Shrink during recede (ease-in cubic)
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
                scaled_text = pygame.transform.smoothscale(
                    self.text_surface,
                    (scaled_text_width, scaled_text_height)
                )

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
        """Clean up resources."""
        # No cleanup needed for sparkle version
        pass
