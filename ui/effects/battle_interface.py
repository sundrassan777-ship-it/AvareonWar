"""
Enhanced Battle Interface

A cinematic multi-phase battle interface featuring:
- Side-by-side attacker/defender panels with BattlePlayerScreen.png backgrounds
- Strength comparison bars with particle combat animation
- Victory/defeat splash screens with zoom animation
- Battle report summary

Integration:
    - Replaces simple battle popup in main.py
    - Used when battle marker is clicked during battles phase
    - Pre-calculates battle result before animation, applies after

States:
    SETUP -> ANIMATING -> SPLASH -> REPORT -> Done
"""

import pygame
import math
import random
from enum import Enum, auto

from config.constants import WINDOW_WIDTH, WINDOW_HEIGHT, WHITE, BLACK
from utils.logger import get_logger
from utils.surface_utils import crop_to_opaque

logger = get_logger(__name__)

# ========================================
# CONSTANTS
# ========================================

# Overlay darkness (semi-transparent black)
OVERLAY_ALPHA = 180

# Reference resolution for scaling (all pixel values tuned for this)
REFERENCE_WIDTH = 1600
REFERENCE_HEIGHT = 900

# Panel layout (values are for reference resolution, will be scaled)
PANEL_GAP_REF = 120  # Gap between panels for battle icon and button
PANEL_WIDTH_RATIO = 0.35  # Each panel takes 35% of screen width
PANEL_HEIGHT_RATIO = 0.55  # Panel height as ratio of screen height
PANEL_TOP_MARGIN_REF = 105  # Top margin for panels
PANEL_CONTENT_PADDING_REF = 100  # Major padding inside panels for BattlePlayerScreen.png

# Strength bar dimensions (fill and PNG can be sized independently)
BAR_FILL_WIDTH_RATIO = 0.20  # Fill width as ratio of screen width
BAR_PNG_WIDTH_RATIO = 0.27  # PNG width as ratio of screen width (adjust separately from fill)
BAR_FILL_HEIGHT_REF = 40  # Height for the colored fill area
BAR_PNG_HEIGHT_REF = 400  # Height for BattleBar.png overlay
BAR_TOP_MARGIN_REF = 30  # Gap below panels (for PNG positioning)
BAR_FILL_OFFSET_REF = -30  # Move fill up relative to PNG (negative = up)
BAR_BORDER_WIDTH = 2

# Battle icon pulsation settings
ICON_PULSE_MIN_SCALE = 1.0  # Minimum scale (normal size)
ICON_PULSE_MAX_SCALE = 1.08  # Maximum scale (8% larger)
ICON_PULSE_SPEED = 1.0  # Pulsations per second (slower, more dramatic)

# Button dimensions (reference resolution)
RESOLVE_BUTTON_WIDTH_REF = 180
RESOLVE_BUTTON_HEIGHT_REF = 50
CLOSE_BUTTON_WIDTH_REF = 150
CLOSE_BUTTON_HEIGHT_REF = 45

# Animation timing
ANIMATION_MIN_DURATION = 3.0  # Minimum animation duration (seconds)
ANIMATION_MAX_DURATION = 5.0  # Maximum animation duration (seconds)

# Splash timing (seconds)
SPLASH_GROW_DURATION = 0.5
SPLASH_HOLD_DURATION = 2.0
SPLASH_SHRINK_DURATION = 0.5
SPLASH_TARGET_SCALE = 0.75  # 75% of original size

# Particle settings
PARTICLES_PER_BAR = 600  # Dense particle stream
PARTICLE_MIN_SIZE_REF = 2
PARTICLE_MAX_SIZE_REF = 4
PARTICLE_MIN_LIFETIME = 0.08  # Particle lifetime (slower for visibility)
PARTICLE_MAX_LIFETIME = 0.20  # Longer traversal time
PARTICLE_ARC_HEIGHT = 0  # No arc - purely horizontal

# Text settings (reference resolution)
TEXT_LINE_HEIGHT_REF = 38  # Increased vertical spacing between lines
TEXT_PADDING_REF = 20  # Padding for fallback (not BattlePlayerScreen)
REPORT_LINE_SPACING_REF = 8  # Extra spacing in battle report


# ========================================
# BATTLE INTERFACE STATE
# ========================================

class BattleInterfaceState(Enum):
    """State machine states for the battle interface."""
    SETUP = auto()      # Two panels, Resolve button
    ANIMATING = auto()  # Bars shooting particles
    SPLASH = auto()     # Victory/defeat image scaling
    REPORT = auto()     # Battle summary, Close button


# ========================================
# BATTLE SPLASH EFFECT
# ========================================

class BattleSplashEffect:
    """
    Victory/defeat image scaling animation.

    Timeline:
    - 0.0s - 0.5s:   Grow from dot to 75% (ease-out cubic)
    - 0.5s - 2.5s:   Hold at 75%
    - 2.5s - 3.0s:   Shrink to dot (ease-in cubic)
    """

    def __init__(self, image, screen_width, screen_height):
        """
        Initialize splash effect.

        Args:
            image: pygame.Surface of victory/defeat image
            screen_width: Width of screen for centering
            screen_height: Height of screen for centering
        """
        self.original_image = image
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.elapsed = 0.0
        self.is_complete = False

        # Pre-calculate total duration
        self.total_duration = SPLASH_GROW_DURATION + SPLASH_HOLD_DURATION + SPLASH_SHRINK_DURATION

        # Store original dimensions for scaling
        self.original_width = image.get_width()
        self.original_height = image.get_height()

    def update(self, delta_time):
        """
        Update animation progress.

        Args:
            delta_time: Time since last update in seconds
        """
        self.elapsed += delta_time

        if self.elapsed >= self.total_duration:
            self.is_complete = True

    def _get_current_scale(self):
        """
        Calculate current scale based on elapsed time.

        Returns:
            float: Scale factor (0.0 to SPLASH_TARGET_SCALE)
        """
        if self.elapsed < SPLASH_GROW_DURATION:
            # Growing phase (ease-out cubic)
            progress = self.elapsed / SPLASH_GROW_DURATION
            eased = 1 - math.pow(1 - progress, 3)
            return eased * SPLASH_TARGET_SCALE

        elif self.elapsed < SPLASH_GROW_DURATION + SPLASH_HOLD_DURATION:
            # Hold phase
            return SPLASH_TARGET_SCALE

        else:
            # Shrinking phase (ease-in cubic)
            shrink_elapsed = self.elapsed - SPLASH_GROW_DURATION - SPLASH_HOLD_DURATION
            progress = min(1.0, shrink_elapsed / SPLASH_SHRINK_DURATION)
            eased = math.pow(progress, 3)
            return SPLASH_TARGET_SCALE * (1 - eased)

    def render(self, screen):
        """
        Render the splash image at current scale.

        Args:
            screen: pygame.Surface to render to
        """
        scale = self._get_current_scale()

        # Don't render if scale is too small
        if scale < 0.01:
            return

        # Calculate scaled dimensions
        scaled_width = int(self.original_width * scale)
        scaled_height = int(self.original_height * scale)

        if scaled_width < 1 or scaled_height < 1:
            return

        # Scale the image
        scaled_image = pygame.transform.smoothscale(
            self.original_image,
            (scaled_width, scaled_height)
        )

        # Center on screen
        x = (self.screen_width - scaled_width) // 2
        y = (self.screen_height - scaled_height) // 2

        screen.blit(scaled_image, (x, y))

    def is_finished(self):
        """Check if animation is complete."""
        return self.is_complete


# ========================================
# BATTLE BAR PARTICLE EFFECT
# ========================================

class BattleBarParticleEffect:
    """
    Particle effect for strength bar combat animation.

    Two bars shoot particles at each other. At the end:
    - Loser's bar is empty
    - Winner's bar shows survivor ratio
    """

    def __init__(self, attacker_bar_rect, defender_bar_rect,
                 attacker_color, defender_color,
                 attacker_initial_fill, defender_initial_fill,
                 attacker_final_fill, defender_final_fill,
                 duration, seed=None, bar_border_img=None, bar_png_width=None,
                 bar_fill_offset=None, bar_png_height=None, ui_scale=1.0):
        """
        Initialize particle combat effect.

        Args:
            attacker_bar_rect: pygame.Rect for attacker strength bar
            defender_bar_rect: pygame.Rect for defender strength bar
            attacker_color: RGB tuple for attacker particles
            defender_color: RGB tuple for defender particles
            attacker_initial_fill: Initial fill ratio (0.0-1.0) for attacker bar
            defender_initial_fill: Initial fill ratio (0.0-1.0) for defender bar
            attacker_final_fill: Final fill ratio after animation
            defender_final_fill: Final fill ratio after animation
            duration: Total animation duration in seconds
            seed: Random seed for deterministic animation (for multiplayer sync)
            bar_border_img: Optional pygame.Surface for bar border (BattleBar.png)
            bar_png_width: Optional width for PNG (if different from fill width)
            bar_fill_offset: Scaled offset for fill positioning
            bar_png_height: Scaled height for PNG overlay
            ui_scale: Scale factor for particle sizes
        """
        self.attacker_rect = attacker_bar_rect
        self.defender_rect = defender_bar_rect
        self.attacker_color = attacker_color
        self.defender_color = defender_color
        self.bar_border_img = bar_border_img
        self.ui_scale = ui_scale
        # PNG dimensions - use passed values or defaults
        self.bar_png_width = bar_png_width if bar_png_width else attacker_bar_rect.width
        self.bar_fill_offset = bar_fill_offset if bar_fill_offset is not None else BAR_FILL_OFFSET_REF
        self.bar_png_height = bar_png_height if bar_png_height else BAR_PNG_HEIGHT_REF

        # Pre-scale bar border to avoid smoothscale per frame
        self._scaled_bar_border = None
        if self.bar_border_img:
            self._scaled_bar_border = pygame.transform.smoothscale(
                self.bar_border_img, (self.bar_png_width, self.bar_png_height))

        # Bar fill states
        self.attacker_initial = attacker_initial_fill
        self.defender_initial = defender_initial_fill
        self.attacker_final = attacker_final_fill
        self.defender_final = defender_final_fill

        self.duration = duration
        self.elapsed = 0.0
        self.is_complete = False

        # Set random seed for deterministic behavior
        if seed is not None:
            random.seed(seed)

        # Initialize particle lists
        self.attacker_particles = []
        self.defender_particles = []

        # Particle spawn timing - spawn more frequently for flash effect
        self.spawn_interval = duration / PARTICLES_PER_BAR
        self.last_spawn_time = 0.0

        # Create reusable surface for particles
        self.particle_surface = None

    def _vary_color(self, color, variation=30):
        """
        Add slight variation to a color.

        Args:
            color: RGB tuple
            variation: Max variation per channel

        Returns:
            RGB tuple with variation applied
        """
        r, g, b = color
        return (
            max(0, min(255, r + random.randint(-variation, variation))),
            max(0, min(255, g + random.randint(-variation, variation))),
            max(0, min(255, b + random.randint(-variation, variation)))
        )

    def _spawn_particle(self, from_attacker=True):
        """
        Spawn a new particle from one bar toward the other.

        Particles travel horizontally in a straight line (flash-like effect).

        Args:
            from_attacker: If True, spawn from attacker bar toward defender
        """
        if from_attacker:
            # Spawn from right edge of attacker bar, toward defender bar
            start_x = self.attacker_rect.right
            start_y = random.uniform(self.attacker_rect.top + 5, self.attacker_rect.bottom - 5)
            end_x = self.defender_rect.left
            end_y = start_y  # Horizontal movement - same Y
            color = self._vary_color(self.attacker_color)
        else:
            # Spawn from left edge of defender bar, toward attacker bar
            start_x = self.defender_rect.left
            start_y = random.uniform(self.defender_rect.top + 5, self.defender_rect.bottom - 5)
            end_x = self.attacker_rect.right
            end_y = start_y  # Horizontal movement - same Y
            color = self._vary_color(self.defender_color)

        # Scale particle sizes based on resolution
        min_size = max(1, int(PARTICLE_MIN_SIZE_REF * self.ui_scale))
        max_size = max(2, int(PARTICLE_MAX_SIZE_REF * self.ui_scale))

        particle = {
            'start_x': start_x,
            'start_y': start_y,
            'end_x': end_x,
            'end_y': end_y,
            'arc_height': PARTICLE_ARC_HEIGHT,  # No arc - horizontal flash
            'lifetime': random.uniform(PARTICLE_MIN_LIFETIME, PARTICLE_MAX_LIFETIME),
            'age': 0.0,
            'color': color,
            'size': random.randint(min_size, max_size)
        }

        if from_attacker:
            self.attacker_particles.append(particle)
        else:
            self.defender_particles.append(particle)

    def _calculate_particle_position(self, particle):
        """
        Calculate current position of a particle along its arc.

        Args:
            particle: Particle dict

        Returns:
            (x, y) tuple of current position
        """
        progress = min(1.0, particle['age'] / particle['lifetime'])

        # Linear interpolation for x and y
        x = particle['start_x'] + (particle['end_x'] - particle['start_x']) * progress
        y = particle['start_y'] + (particle['end_y'] - particle['start_y']) * progress

        # Add parabolic arc (peaks at middle of trajectory)
        arc_offset = particle['arc_height'] * math.sin(progress * math.pi)
        y -= arc_offset  # Negative because y increases downward

        return (int(x), int(y))

    def update(self, delta_time):
        """
        Update particle positions and spawn new particles.

        Args:
            delta_time: Time since last update in seconds
        """
        self.elapsed += delta_time

        # Check if animation is complete
        if self.elapsed >= self.duration:
            self.is_complete = True
            return

        # Spawn new particles periodically
        if self.elapsed - self.last_spawn_time >= self.spawn_interval:
            self._spawn_particle(from_attacker=True)
            self._spawn_particle(from_attacker=False)
            self.last_spawn_time = self.elapsed

        # Update existing particles
        for particle in self.attacker_particles + self.defender_particles:
            particle['age'] += delta_time

        # Remove dead particles
        self.attacker_particles = [p for p in self.attacker_particles if p['age'] < p['lifetime']]
        self.defender_particles = [p for p in self.defender_particles if p['age'] < p['lifetime']]

    def _get_current_fills(self):
        """
        Get current bar fill ratios based on animation progress.

        Returns:
            (attacker_fill, defender_fill) tuple
        """
        progress = min(1.0, self.elapsed / self.duration)

        # Ease-in-out for smooth transition
        if progress < 0.5:
            eased = 2 * progress * progress
        else:
            eased = 1 - math.pow(-2 * progress + 2, 2) / 2

        # Interpolate between initial and final fills
        attacker_fill = self.attacker_initial + (self.attacker_final - self.attacker_initial) * eased
        defender_fill = self.defender_initial + (self.defender_final - self.defender_initial) * eased

        return (attacker_fill, defender_fill)

    def render(self, screen):
        """
        Render strength bars and particles.

        Args:
            screen: pygame.Surface to render to
        """
        # Get current fill ratios
        attacker_fill, defender_fill = self._get_current_fills()

        # Calculate fill Y position (offset from bar rect for independent positioning)
        fill_y = self.attacker_rect.top + self.bar_fill_offset

        # Draw bar backgrounds (empty) at offset position
        attacker_fill_rect = pygame.Rect(
            self.attacker_rect.left, fill_y,
            self.attacker_rect.width, self.attacker_rect.height
        )
        defender_fill_rect = pygame.Rect(
            self.defender_rect.left, fill_y,
            self.defender_rect.width, self.defender_rect.height
        )
        pygame.draw.rect(screen, DARK_GRAY, attacker_fill_rect)
        pygame.draw.rect(screen, DARK_GRAY, defender_fill_rect)

        # Draw bar fills at offset position
        if attacker_fill > 0:
            fill_rect = pygame.Rect(
                self.attacker_rect.left,
                fill_y,
                int(self.attacker_rect.width * attacker_fill),
                self.attacker_rect.height
            )
            pygame.draw.rect(screen, self.attacker_color, fill_rect)

        if defender_fill > 0:
            fill_rect = pygame.Rect(
                self.defender_rect.left,
                fill_y,
                int(self.defender_rect.width * defender_fill),
                self.defender_rect.height
            )
            pygame.draw.rect(screen, self.defender_color, fill_rect)

        # Draw bar borders using BattleBar.png if available
        # P2 fix: use pre-scaled bar border instead of smoothscale per frame
        if self._scaled_bar_border:
            # Center PNG both vertically and horizontally over the fill area
            png_offset_y = (self.attacker_rect.height - self.bar_png_height) // 2
            attacker_png_x = self.attacker_rect.centerx - self.bar_png_width // 2
            defender_png_x = self.defender_rect.centerx - self.bar_png_width // 2
            screen.blit(self._scaled_bar_border, (attacker_png_x, self.attacker_rect.top + png_offset_y))
            screen.blit(self._scaled_bar_border, (defender_png_x, self.defender_rect.top + png_offset_y))
        else:
            pygame.draw.rect(screen, WHITE, self.attacker_rect, BAR_BORDER_WIDTH)
            pygame.draw.rect(screen, WHITE, self.defender_rect, BAR_BORDER_WIDTH)

        # Create particle surface if needed
        if self.particle_surface is None:
            self.particle_surface = pygame.Surface(
                (screen.get_width(), screen.get_height()),
                pygame.SRCALPHA
            )
        else:
            self.particle_surface.fill((0, 0, 0, 0))

        # Draw particles (flash-like horizontal streaks)
        for particle in self.attacker_particles + self.defender_particles:
            x, y = self._calculate_particle_position(particle)
            # Calculate opacity based on lifetime (bright flash that fades)
            age_ratio = particle['age'] / particle['lifetime']
            alpha = int(255 * (1 - age_ratio * 0.7))  # Fade faster for flash effect
            color_with_alpha = (*particle['color'], alpha)
            pygame.draw.circle(self.particle_surface, color_with_alpha, (x, y), particle['size'])

        screen.blit(self.particle_surface, (0, 0))

    def is_finished(self):
        """Check if animation is complete."""
        return self.is_complete


# Import DARK_GRAY for bar backgrounds
DARK_GRAY = (60, 60, 60)


# ========================================
# ENHANCED BATTLE INTERFACE
# ========================================

class EnhancedBattleInterface:
    """
    Main battle interface controller.

    Manages:
    - State machine transitions
    - Panel rendering with BattlePlayerScreen.png
    - Button handling (Resolve, Close)
    - Pre-calculation of battle result before animation
    - Integration with game loop
    """

    def __init__(self, screen, game_state, battle_index, font_manager,
                 current_player_index, on_complete_callback=None):
        """
        Initialize the enhanced battle interface.

        Args:
            screen: pygame.Surface to render to
            game_state: GameState object with battle data
            battle_index: Index of battle in pending_battles
            font_manager: FontManager for text rendering
            current_player_index: Index of the player viewing the battle
            on_complete_callback: Function to call when interface closes
        """
        self.screen = screen
        self.game_state = game_state
        self.battle_index = battle_index
        self.font_manager = font_manager
        self.current_player = current_player_index
        self.on_complete = on_complete_callback

        # Get screen dimensions
        self.screen_width = screen.get_width()
        self.screen_height = screen.get_height()

        # Initialize state
        self.state = BattleInterfaceState.SETUP
        self.elapsed = 0.0
        self.is_finished_flag = False

        # Pre-calculated battle result (populated when Resolve is clicked)
        self.battle_result = None
        self.animation_duration = 0.0
        self.animation_seed = None

        # Sub-effects
        self.particle_effect = None
        self.splash_effect = None

        # UI state
        self.mouse_pos = (0, 0)
        self.clicked_button = None

        # Load assets
        self._load_assets()

        # Calculate layout
        self._calculate_layout()

        # Extract battle data for display
        self._extract_battle_data()

    def _load_assets(self):
        """Load all required image assets."""
        # Calculate preliminary scale for asset loading
        scale_x = self.screen_width / REFERENCE_WIDTH
        scale_y = self.screen_height / REFERENCE_HEIGHT
        asset_scale = (scale_x + scale_y) / 2

        try:
            # Panel background
            self.panel_bg = pygame.image.load("assets/BattlePlayerScreen.png").convert_alpha()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattlePlayerScreen.png: {e}")
            self.panel_bg = None

        try:
            # Battle icon for center gap
            battle_icon_full = pygame.image.load("assets/mapicons/BattleIcon1.png").convert_alpha()
            # Scale to 25.5% of original, then apply resolution scale
            icon_w, icon_h = battle_icon_full.get_size()
            icon_scale = 0.255 * asset_scale
            self.battle_icon = pygame.transform.smoothscale(
                battle_icon_full,
                (int(icon_w * icon_scale), int(icon_h * icon_scale))
            )
            # Store base dimensions for pulsation animation
            self.battle_icon_base_w = self.battle_icon.get_width()
            self.battle_icon_base_h = self.battle_icon.get_height()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattleIcon1.png: {e}")
            self.battle_icon = None
            self.battle_icon_base_w = 0
            self.battle_icon_base_h = 0

        try:
            # Button background
            btn_full = pygame.image.load("assets/CampaignBTN.png").convert_alpha()
            # Crop to opaque content
            self.button_bg = crop_to_opaque(btn_full, threshold=128)
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load CampaignBTN.png: {e}")
            self.button_bg = None

        try:
            # Victory/defeat splash images
            self.victory_img = pygame.image.load("assets/victoryscrn.png").convert_alpha()
            self.defeat_img = pygame.image.load("assets/defeatscrn.png").convert_alpha()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load victory/defeat images: {e}")
            self.victory_img = None
            self.defeat_img = None

        try:
            # BattleBar.png for strength bar borders
            self.bar_border_img = pygame.image.load("assets/BattleBar.png").convert_alpha()
            self.bar_border_original_h = self.bar_border_img.get_height()
        except (pygame.error, FileNotFoundError) as e:
            logger.warning(f"Could not load BattleBar.png: {e}")
            self.bar_border_img = None
            # C2 fix: BAR_HEIGHT was undefined — use BAR_PNG_HEIGHT_REF instead
            self.bar_border_original_h = BAR_PNG_HEIGHT_REF

        # Get fonts (scaled based on reference resolution)
        ui_scale = self.screen_height / REFERENCE_HEIGHT
        self.title_font = self.font_manager.get_bold_font(int(24 * ui_scale))
        self.text_font = self.font_manager.get_font(int(16 * ui_scale))
        self.small_font = self.font_manager.get_font(int(14 * ui_scale))
        self.button_font = self.font_manager.get_font(int(14 * ui_scale))  # Smaller button text

    def _calculate_layout(self):
        """Calculate positions and sizes for all UI elements.

        All pixel values are scaled based on screen size relative to
        the reference resolution (1600x900).
        """
        # Calculate scale factors based on reference resolution
        self.scale_x = self.screen_width / REFERENCE_WIDTH
        self.scale_y = self.screen_height / REFERENCE_HEIGHT
        # Use average for uniform scaling of most elements
        self.scale = (self.scale_x + self.scale_y) / 2

        # Scale helper function
        def s(value):
            """Scale a pixel value based on resolution."""
            return int(value * self.scale)

        # Scaled values from reference constants
        panel_gap = s(PANEL_GAP_REF)
        panel_top_margin = s(PANEL_TOP_MARGIN_REF)
        self.panel_content_padding = s(PANEL_CONTENT_PADDING_REF)
        self.bar_fill_height = s(BAR_FILL_HEIGHT_REF)
        self.bar_png_height = s(BAR_PNG_HEIGHT_REF)
        self.bar_top_margin = s(BAR_TOP_MARGIN_REF)
        self.bar_fill_offset = int(BAR_FILL_OFFSET_REF * self.scale)  # Keep sign
        resolve_button_width = s(RESOLVE_BUTTON_WIDTH_REF)
        resolve_button_height = s(RESOLVE_BUTTON_HEIGHT_REF)
        close_button_width = s(CLOSE_BUTTON_WIDTH_REF)
        close_button_height = s(CLOSE_BUTTON_HEIGHT_REF)
        self.text_line_height = s(TEXT_LINE_HEIGHT_REF)
        self.text_padding = s(TEXT_PADDING_REF)
        self.report_line_spacing = s(REPORT_LINE_SPACING_REF)

        # Panel dimensions
        self.panel_width = int(self.screen_width * PANEL_WIDTH_RATIO)
        self.panel_height = int(self.screen_height * PANEL_HEIGHT_RATIO)

        # Panel positions (centered with gap)
        total_width = self.panel_width * 2 + panel_gap
        left_x = (self.screen_width - total_width) // 2

        self.attacker_panel_rect = pygame.Rect(
            left_x,
            panel_top_margin,
            self.panel_width,
            self.panel_height
        )

        self.defender_panel_rect = pygame.Rect(
            left_x + self.panel_width + panel_gap,
            panel_top_margin,
            self.panel_width,
            self.panel_height
        )

        # Battle icon position (centered in gap)
        gap_center_x = left_x + self.panel_width + panel_gap // 2
        self.icon_center_x = gap_center_x  # Store for pulsation rendering
        if self.battle_icon:
            icon_y = panel_top_margin + s(50)
            self.icon_center_y = icon_y + self.battle_icon.get_height() // 2  # Center Y for pulsation
            self.battle_icon_pos = (
                gap_center_x - self.battle_icon.get_width() // 2,
                icon_y
            )
            # Resolve button positioned below battle icon (reduced gap)
            button_y = icon_y + self.battle_icon.get_height() + s(8)
        else:
            self.battle_icon_pos = (gap_center_x, panel_top_margin + s(50))
            self.icon_center_y = panel_top_margin + s(80)
            button_y = panel_top_margin + s(130)

        # Resolve button (below battle icon in gap)
        self.resolve_button_rect = pygame.Rect(
            gap_center_x - resolve_button_width // 2,
            button_y,
            resolve_button_width,
            resolve_button_height
        )

        # Strength bars (below panels)
        # Fill and PNG can have independent widths
        bar_y = self.attacker_panel_rect.bottom + self.bar_top_margin
        bar_fill_width = int(self.screen_width * BAR_FILL_WIDTH_RATIO)
        self.bar_png_width = int(self.screen_width * BAR_PNG_WIDTH_RATIO)

        # Attacker bar - aligned with attacker panel (fill dimensions)
        self.attacker_bar_rect = pygame.Rect(
            self.attacker_panel_rect.centerx - bar_fill_width // 2,
            bar_y,
            bar_fill_width,
            self.bar_fill_height
        )

        # Defender bar - aligned with defender panel (fill dimensions)
        self.defender_bar_rect = pygame.Rect(
            self.defender_panel_rect.centerx - bar_fill_width // 2,
            bar_y,
            bar_fill_width,
            self.bar_fill_height
        )

        # Report panel (centered, used in REPORT state)
        report_width = int(self.screen_width * 0.4)
        report_height = int(self.screen_height * 0.6)
        self.report_panel_rect = pygame.Rect(
            (self.screen_width - report_width) // 2,
            (self.screen_height - report_height) // 2,
            report_width,
            report_height
        )

        # Close button (bottom of report panel)
        self.close_button_rect = pygame.Rect(
            self.report_panel_rect.centerx - close_button_width // 2,
            self.report_panel_rect.bottom - close_button_height - s(20),
            close_button_width,
            close_button_height
        )

        # P2/P3 fix: pre-scale battle bar borders and panel backgrounds (constant sizes)
        self._scaled_bar_border = None
        if self.bar_border_img:
            self._scaled_bar_border = pygame.transform.smoothscale(
                self.bar_border_img, (self.bar_png_width, self.bar_png_height))
        self._scaled_panel_bg = None
        self._scaled_report_bg = None
        if self.panel_bg:
            self._scaled_panel_bg = pygame.transform.smoothscale(
                self.panel_bg, (self.attacker_panel_rect.width, self.attacker_panel_rect.height))
            self._scaled_report_bg = pygame.transform.smoothscale(
                self.panel_bg, (self.report_panel_rect.width, self.report_panel_rect.height))

    def _extract_battle_data(self):
        """Extract battle information for display."""
        battle = self.game_state.pending_battles[self.battle_index]

        self.territory = battle.territory

        # Identify attacker and defenders
        # Attacker is the player who moved into the territory (not the original owner)
        original_owner = battle.original_owner

        self.attacker_player = None
        self.defender_players = []

        # SIMULTANEOUS MODE: Use battle.attackers list if available (correctly computed by sim_phase_manager)
        # This ensures allied defenders aren't mistakenly identified as attackers
        if hasattr(battle, 'attackers') and battle.attackers:
            # Use the pre-computed attackers list
            if len(battle.attackers) >= 1:
                self.attacker_player = battle.attackers[0]  # First attacker is shown on left panel

            # First, check if there are any non-attackers (true defenders)
            non_attackers = [p for p in battle.armies.keys() if p not in battle.attackers]

            if non_attackers:
                # There are true defenders (e.g., territory owner or allies)
                self.defender_players = non_attackers
            else:
                # All participants are attackers (multi-way attack on neutral territory)
                # Show other attackers as opponents on the right side for UI purposes
                for player_index in battle.attackers[1:]:  # Skip first attacker (shown on left)
                    if player_index in battle.armies:  # Only include those with armies
                        self.defender_players.append(player_index)
        else:
            # SEQUENTIAL MODE FALLBACK: Original logic based on owner
            all_participants = list(battle.armies.keys())
            for player_index in all_participants:
                # Check if this is the territory owner (defender)
                if player_index == original_owner and original_owner >= 0:
                    self.defender_players.append(player_index)
                else:
                    # Non-owner - first one is attacker, rest are "defenders" (opponents)
                    if self.attacker_player is None:
                        self.attacker_player = player_index
                    else:
                        # Additional non-owners are opponents (e.g., two players arriving at neutral)
                        self.defender_players.append(player_index)

            # If no clear attacker found, use first non-owner
            if self.attacker_player is None and len(battle.armies) > 0:
                self.attacker_player = list(battle.armies.keys())[0]

        # Add allied defenders (allies who contribute to defense but aren't in battle.armies directly)
        if hasattr(battle, 'allied_defenders'):
            for ally in battle.allied_defenders:
                if ally not in self.defender_players:
                    self.defender_players.append(ally)

        # If no defenders found, add original owner ONLY if it's a valid player (>= 0)
        # Don't add -1 (neutral) as a defender
        if not self.defender_players and original_owner is not None and original_owner >= 0:
            self.defender_players.append(original_owner)

        # Get army compositions
        self.attacker_composition = {}
        if self.attacker_player is not None and self.attacker_player in battle.army_compositions:
            self.attacker_composition = battle.army_compositions[self.attacker_player].copy()

        # Aggregate defender compositions
        self.defender_composition = {}
        for def_player in self.defender_players:
            if def_player in battle.army_compositions:
                for unit_type, count in battle.army_compositions[def_player].items():
                    self.defender_composition[unit_type] = self.defender_composition.get(unit_type, 0) + count

        # Get army counts
        self.attacker_count = battle.armies.get(self.attacker_player, 0) if self.attacker_player is not None else 0
        self.defender_count = sum(battle.armies.get(p, 0) for p in self.defender_players)

        # Check for Keep
        self.has_keep = (hasattr(battle, 'keep_bonus_player') and
                        battle.keep_bonus_player is not None)
        self.keep_bonus = getattr(battle, 'keep_bonus', 0)

        # Get player colors
        self.attacker_color = self.game_state.get_player_color(self.attacker_player) if self.attacker_player is not None else (200, 200, 200)

        # Defender color = territory owner color (if valid), otherwise use first defender's color
        if original_owner is not None and original_owner >= 0:
            self.defender_color = self.game_state.get_player_color(original_owner)
        elif self.defender_players:
            self.defender_color = self.game_state.get_player_color(self.defender_players[0])
        else:
            self.defender_color = (200, 200, 200)

        # Calculate effective strengths for display
        self._calculate_effective_strengths()

    def _calculate_effective_strengths(self):
        """Calculate effective strengths for display on panels."""
        battle = self.game_state.pending_battles[self.battle_index]

        # Use game_state's calculation method if available
        if hasattr(self.game_state, 'calculate_army_effective_strength'):
            # Calculate attacker strength (including veterancy bonus)
            if self.attacker_player is not None and self.attacker_composition:
                atk_avg_levels = self.game_state.get_unit_avg_levels(self.territory, self.attacker_player)
                self.attacker_strength = self.game_state.calculate_army_effective_strength(
                    self.attacker_composition,
                    self.defender_composition,
                    self.attacker_player,
                    self.territory,
                    unit_avg_levels=atk_avg_levels
                )
            else:
                self.attacker_strength = 0.0

            # Calculate defender strength (including veterancy bonus)
            if self.defender_composition:
                def_player = self.defender_players[0] if self.defender_players else None
                def_avg_levels = self.game_state.get_unit_avg_levels(self.territory, def_player) if def_player is not None else None
                base_strength = self.game_state.calculate_army_effective_strength(
                    self.defender_composition,
                    self.attacker_composition,
                    def_player,
                    self.territory,
                    unit_avg_levels=def_avg_levels
                )
                self.defender_strength = base_strength + (self.keep_bonus if self.has_keep else 0)
            else:
                self.defender_strength = self.keep_bonus if self.has_keep else 0.0
        else:
            # Fallback to simple army counts
            self.attacker_strength = float(self.attacker_count)
            self.defender_strength = float(self.defender_count) + (self.keep_bonus if self.has_keep else 0)

        # Calculate bar fill proportions
        if self.attacker_strength >= self.defender_strength and self.attacker_strength > 0:
            self.attacker_fill = 1.0
            self.defender_fill = self.defender_strength / self.attacker_strength if self.attacker_strength > 0 else 0.0
        elif self.defender_strength > 0:
            self.defender_fill = 1.0
            self.attacker_fill = self.attacker_strength / self.defender_strength
        else:
            self.attacker_fill = 0.5
            self.defender_fill = 0.5

    def _pre_calculate_battle_result(self):
        """
        Pre-calculate battle outcome before animation.

        Stores result for animation display without applying to game state yet.
        """
        battle = self.game_state.pending_battles[self.battle_index]

        # Generate deterministic seed for animation (for multiplayer sync)
        # Use battle territory name and turn number for reproducibility
        seed_str = f"{battle.territory}_{self.game_state.turn_number}"
        self.animation_seed = hash(seed_str) % (2**31)

        # Calculate animation duration deterministically
        random.seed(self.animation_seed)
        self.animation_duration = random.uniform(ANIMATION_MIN_DURATION, ANIMATION_MAX_DURATION)

        # Pre-calculate battle outcome using existing game logic
        # This simulates the battle without modifying game state

        # Store initial armies for survivor calculation
        initial_attacker = self.attacker_count
        initial_defender = self.defender_count

        # Determine winner based on effective strength
        if self.attacker_strength > self.defender_strength:
            self.winner = self.attacker_player
            # Estimate survivors (simplified)
            strength_diff = self.attacker_strength - self.defender_strength
            survivor_ratio = min(1.0, strength_diff / self.attacker_strength) if self.attacker_strength > 0 else 0
            self.attacker_survivors = max(1, int(initial_attacker * (0.3 + 0.7 * survivor_ratio)))
            self.defender_survivors = 0
        elif self.defender_strength > self.attacker_strength:
            self.winner = self.defender_players[0] if self.defender_players else None
            strength_diff = self.defender_strength - self.attacker_strength
            survivor_ratio = min(1.0, strength_diff / self.defender_strength) if self.defender_strength > 0 else 0
            self.defender_survivors = max(1, int(initial_defender * (0.3 + 0.7 * survivor_ratio)))
            self.attacker_survivors = 0
        else:
            # Tie - both bars drain to empty; actual winner determined by dice
            # set_actual_battle_result() will update winner/survivors with real values
            self.winner = self.attacker_player  # placeholder, overwritten by actual result
            self.attacker_survivors = 0
            self.defender_survivors = 0

        # Calculate final bar fills
        # Perfect tie: both drain to 0 (visually shows evenly matched before dice)
        if self.attacker_survivors == 0 and self.defender_survivors == 0:
            self.attacker_final_fill = 0.0
            self.defender_final_fill = 0.0
        elif self.winner == self.attacker_player:
            self.attacker_final_fill = self.attacker_survivors / initial_attacker if initial_attacker > 0 else 0
            self.defender_final_fill = 0.0
        else:
            self.attacker_final_fill = 0.0
            self.defender_final_fill = self.defender_survivors / initial_defender if initial_defender > 0 else 0

        # Determine if current player won
        self.current_player_won = (self.winner == self.current_player)

        # Calculate unit type breakdown for current player
        # Estimate which units survived/were lost proportionally
        current_player_composition = None
        current_player_survivors = 0
        current_player_total = 0

        if self.current_player == self.attacker_player:
            current_player_composition = self.attacker_composition.copy()
            current_player_survivors = self.attacker_survivors
            current_player_total = initial_attacker
        elif self.current_player in self.defender_players:
            current_player_composition = self.defender_composition.copy()
            current_player_survivors = self.defender_survivors
            current_player_total = initial_defender

        # Calculate unit breakdown for current player
        # Use a two-pass approach to ensure totals match exactly
        unit_breakdown = {}
        if current_player_composition and current_player_total > 0:
            # First pass: calculate preliminary survivors proportionally
            survivor_ratio = current_player_survivors / current_player_total
            preliminary = {}
            for unit_type, count in current_player_composition.items():
                survived = int(count * survivor_ratio)
                preliminary[unit_type] = {'original': count, 'survived': survived}

            # Calculate difference between sum and actual survivors
            calculated_sum = sum(p['survived'] for p in preliminary.values())
            difference = current_player_survivors - calculated_sum

            # Second pass: adjust to match actual total
            # Sort by original count (descending) to adjust largest units first
            sorted_types = sorted(preliminary.keys(),
                                  key=lambda t: preliminary[t]['original'],
                                  reverse=True)

            for unit_type in sorted_types:
                if difference == 0:
                    break
                original = preliminary[unit_type]['original']
                current_survived = preliminary[unit_type]['survived']

                if difference > 0:
                    # Need to add survivors - can't exceed original count
                    can_add = min(difference, original - current_survived)
                    preliminary[unit_type]['survived'] += can_add
                    difference -= can_add
                elif difference < 0:
                    # Need to remove survivors - can't go below 0
                    can_remove = min(-difference, current_survived)
                    preliminary[unit_type]['survived'] -= can_remove
                    difference += can_remove

            # Build final breakdown with lost counts
            for unit_type, data in preliminary.items():
                lost = data['original'] - data['survived']
                unit_breakdown[unit_type] = {
                    'original': data['original'],
                    'survived': data['survived'],
                    'lost': lost
                }

        # Store battle result
        self.battle_result = {
            'winner': self.winner,
            'attacker_survivors': self.attacker_survivors,
            'defender_survivors': self.defender_survivors,
            'attacker_lost': initial_attacker - self.attacker_survivors,
            'defender_lost': initial_defender - self.defender_survivors,
            'unit_breakdown': unit_breakdown  # Unit type breakdown for current player
        }

    def _start_animation(self):
        """Start the particle combat animation."""
        self.state = BattleInterfaceState.ANIMATING
        self.elapsed = 0.0

        # Create particle effect with bar border image and scaled dimensions
        self.particle_effect = BattleBarParticleEffect(
            attacker_bar_rect=self.attacker_bar_rect,
            defender_bar_rect=self.defender_bar_rect,
            attacker_color=self.attacker_color,
            defender_color=self.defender_color,
            attacker_initial_fill=self.attacker_fill,
            defender_initial_fill=self.defender_fill,
            attacker_final_fill=self.attacker_final_fill,
            defender_final_fill=self.defender_final_fill,
            duration=self.animation_duration,
            seed=self.animation_seed,
            bar_border_img=self.bar_border_img,
            bar_png_width=self.bar_png_width,
            bar_fill_offset=self.bar_fill_offset,
            bar_png_height=self.bar_png_height,
            ui_scale=self.scale
        )

    def _start_splash(self):
        """Start the victory/defeat splash animation."""
        self.state = BattleInterfaceState.SPLASH
        self.elapsed = 0.0

        # Choose appropriate image
        if self.current_player_won:
            image = self.victory_img
        else:
            image = self.defeat_img

        if image:
            self.splash_effect = BattleSplashEffect(
                image=image,
                screen_width=self.screen_width,
                screen_height=self.screen_height
            )
        else:
            # Skip splash if no image
            self._start_report()

    def _start_report(self):
        """Start the battle report display."""
        self.state = BattleInterfaceState.REPORT
        self.elapsed = 0.0

    def update(self, delta_time):
        """
        Update the interface state.

        Args:
            delta_time: Time since last update in seconds
        """
        self.elapsed += delta_time

        if self.state == BattleInterfaceState.ANIMATING:
            if self.particle_effect:
                self.particle_effect.update(delta_time)
                if self.particle_effect.is_finished():
                    # Wait 0.5 seconds after animation completes
                    if self.elapsed >= self.animation_duration + 0.5:
                        self._start_splash()

        elif self.state == BattleInterfaceState.SPLASH:
            if self.splash_effect:
                self.splash_effect.update(delta_time)
                if self.splash_effect.is_finished():
                    self._start_report()

    def set_actual_battle_result(self, winner: int, attacker_survivors: int,
                                  defender_survivors: int, surviving_units: list = None):
        """
        Update the battle result with actual values from game_state.resolve_battle().

        This replaces the pre-calculated estimates with the real battle outcome.
        Should be called immediately after game_state.resolve_battle().

        Args:
            winner: Actual winner player index
            attacker_survivors: Actual number of attacker survivors
            defender_survivors: Actual number of defender survivors
            surviving_units: List of surviving unit dicts with 'type' key
        """
        # Update internal survivor counts
        self.winner = winner
        self.attacker_survivors = attacker_survivors
        self.defender_survivors = defender_survivors
        self.current_player_won = (winner == self.current_player)

        # Recalculate unit breakdown with actual survivors
        if self.current_player == self.attacker_player:
            current_player_composition = self.attacker_composition.copy()
            current_player_survivors = attacker_survivors
            current_player_total = self.attacker_count
        elif self.current_player in self.defender_players:
            current_player_composition = self.defender_composition.copy()
            current_player_survivors = defender_survivors
            current_player_total = self.defender_count
        else:
            current_player_composition = {}
            current_player_survivors = 0
            current_player_total = 0

        # If we have actual surviving units, use them for precise breakdown
        unit_breakdown = {}
        if surviving_units and self.current_player_won:
            # Count survivors by type from actual data
            survivor_counts = {}
            for unit in surviving_units:
                unit_type = unit.get('type', 'Swordsman')
                survivor_counts[unit_type] = survivor_counts.get(unit_type, 0) + 1

            # Build breakdown comparing original to survivors
            for unit_type, original_count in current_player_composition.items():
                survived = survivor_counts.get(unit_type, 0)
                lost = original_count - survived
                unit_breakdown[unit_type] = {
                    'original': original_count,
                    'survived': survived,
                    'lost': lost
                }
        elif current_player_composition and current_player_total > 0:
            # Fallback: proportional calculation (for losers or if no unit data)
            survivor_ratio = current_player_survivors / current_player_total if current_player_total > 0 else 0
            preliminary = {}
            for unit_type, count in current_player_composition.items():
                survived = int(count * survivor_ratio)
                preliminary[unit_type] = {'original': count, 'survived': survived}

            # Adjust to match actual total
            calculated_sum = sum(p['survived'] for p in preliminary.values())
            difference = current_player_survivors - calculated_sum

            sorted_types = sorted(preliminary.keys(),
                                  key=lambda t: preliminary[t]['original'],
                                  reverse=True)

            for unit_type in sorted_types:
                if difference == 0:
                    break
                original = preliminary[unit_type]['original']
                current_survived = preliminary[unit_type]['survived']

                if difference > 0:
                    can_add = min(difference, original - current_survived)
                    preliminary[unit_type]['survived'] += can_add
                    difference -= can_add
                elif difference < 0:
                    can_remove = min(-difference, current_survived)
                    preliminary[unit_type]['survived'] -= can_remove
                    difference += can_remove

            for unit_type, data in preliminary.items():
                lost = data['original'] - data['survived']
                unit_breakdown[unit_type] = {
                    'original': data['original'],
                    'survived': data['survived'],
                    'lost': lost
                }

        # Update battle_result with actual values
        self.battle_result = {
            'winner': winner,
            'attacker_survivors': attacker_survivors,
            'defender_survivors': defender_survivors,
            'attacker_lost': self.attacker_count - attacker_survivors,
            'defender_lost': self.defender_count - defender_survivors,
            'unit_breakdown': unit_breakdown
        }

    def handle_click(self, pos):
        """
        Handle mouse click events.

        Args:
            pos: (x, y) tuple of click position

        Returns:
            str or None: 'resolve', 'close', or None if no button clicked
        """
        if self.state == BattleInterfaceState.SETUP:
            if self.resolve_button_rect.collidepoint(pos):
                self._pre_calculate_battle_result()
                self._start_animation()
                return 'resolve'

        elif self.state == BattleInterfaceState.REPORT:
            if self.close_button_rect.collidepoint(pos):
                self.is_finished_flag = True
                return 'close'

        return None

    def handle_mouse_motion(self, pos):
        """
        Handle mouse movement for hover effects.

        Args:
            pos: (x, y) tuple of mouse position
        """
        self.mouse_pos = pos

    def _wrap_text(self, text, font, max_width):
        """
        Wrap text to fit within max_width, returning list of lines.

        Tries to break on word boundaries first, then character boundaries
        if a single word is too long.

        Args:
            text: Text string to wrap
            font: pygame.Font to measure with
            max_width: Maximum width in pixels

        Returns:
            List of text lines that fit within max_width
        """
        # First check if text fits as-is
        if font.size(text)[0] <= max_width:
            return [text]

        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            # Check if adding this word would exceed max_width
            test_line = f"{current_line} {word}".strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                # Current line is full, start new line
                if current_line:
                    lines.append(current_line)

                # Check if single word fits
                if font.size(word)[0] <= max_width:
                    current_line = word
                else:
                    # Word too long - break by character
                    current_line = ""
                    for char in word:
                        test = current_line + char
                        if font.size(test)[0] <= max_width:
                            current_line = test
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = char

        # Add remaining text
        if current_line:
            lines.append(current_line)

        return lines if lines else [text]

    def _render_overlay(self):
        """Render the semi-transparent dark overlay."""
        # FPS OPT: Cache overlay surface (avoids fullscreen SRCALPHA alloc every frame)
        if not hasattr(self, '_cached_overlay') or self._cached_overlay.get_size() != (self.screen_width, self.screen_height):
            self._cached_overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
            self._cached_overlay.fill((0, 0, 0, OVERLAY_ALPHA))
        self.screen.blit(self._cached_overlay, (0, 0))

    def _render_panel(self, rect, title, title_color, territory, composition,
                      effective_strength, is_defender=False):
        """
        Render a battle information panel.

        Args:
            rect: pygame.Rect for panel bounds
            title: Player name to display
            title_color: Color for player name
            territory: Territory name
            composition: Dict of unit_type -> count
            effective_strength: Calculated effective strength
            is_defender: If True, show Keep info if applicable
        """
        # P3 fix: use pre-scaled panel background instead of smoothscale per frame
        if self._scaled_panel_bg:
            self.screen.blit(self._scaled_panel_bg, rect.topleft)
        elif self.panel_bg:
            self.screen.blit(pygame.transform.smoothscale(self.panel_bg, (rect.width, rect.height)), rect.topleft)
        else:
            # Fallback solid color
            pygame.draw.rect(self.screen, (40, 40, 60), rect)
            pygame.draw.rect(self.screen, WHITE, rect, 2)

        # Content area with major padding for BattlePlayerScreen.png
        padding = self.panel_content_padding if self.panel_bg else self.text_padding
        content_x = rect.left + padding
        content_width = rect.width - padding * 2
        y = rect.top + padding

        # Player name (colored) - wrap if too long
        name_lines = self._wrap_text(title, self.title_font, content_width)
        for line in name_lines:
            name_surface = self.title_font.render(line, True, title_color)
            name_rect = name_surface.get_rect(centerx=rect.centerx, top=y)
            self.screen.blit(name_surface, name_rect)
            y += self.text_line_height
        y += int(5 * self.scale)  # Extra spacing after name

        # Territory
        territory_text = f"Territory: {territory}"
        territory_surface = self.text_font.render(territory_text, True, WHITE)
        self.screen.blit(territory_surface, (content_x, y))
        y += self.text_line_height

        # Army Composition header
        comp_header = self.text_font.render("Army Composition:", True, WHITE)
        self.screen.blit(comp_header, (content_x, y))
        y += self.text_line_height - int(5 * self.scale)

        # Separator line
        pygame.draw.line(self.screen, WHITE,
                        (content_x, y),
                        (content_x + content_width, y),
                        1)
        y += int(12 * self.scale)

        # Unit counts
        if composition:
            for unit_type, count in sorted(composition.items()):
                unit_text = f"{count} {unit_type}"
                unit_surface = self.small_font.render(unit_text, True, WHITE)
                self.screen.blit(unit_surface, (content_x + int(10 * self.scale), y))
                y += self.text_line_height - int(8 * self.scale)
        else:
            no_units = self.small_font.render("No units", True, (150, 150, 150))
            self.screen.blit(no_units, (content_x + int(10 * self.scale), y))
            y += self.text_line_height - int(8 * self.scale)

        # Keep indicator (defender only)
        if is_defender and self.has_keep:
            y += int(8 * self.scale)
            keep_text = f"Territory has a Keep. (+{self.keep_bonus})"
            keep_surface = self.small_font.render(keep_text, True, (255, 200, 100))
            self.screen.blit(keep_surface, (content_x + int(10 * self.scale), y))
            y += self.text_line_height

        # Effective Strength
        y += 12
        strength_text = f"Effective Strength: {effective_strength:.1f}"
        strength_surface = self.text_font.render(strength_text, True, WHITE)
        self.screen.blit(strength_surface, (content_x, y))

    def _render_button(self, rect, text, bg_image=None):
        """
        Render a button with hover/click effects.

        Args:
            rect: pygame.Rect for button bounds
            text: Text to display on button
            bg_image: Optional background image
        """
        is_hovering = rect.collidepoint(self.mouse_pos)

        if bg_image:
            # FPS OPT: Cache scaled+darkened base button image (avoids smoothscale+copy+Surface every frame)
            if not hasattr(self, '_button_base_cache'):
                self._button_base_cache = {}
            btn_key = (id(bg_image), rect.width, rect.height)
            if btn_key not in self._button_base_cache:
                scaled_img = pygame.transform.smoothscale(bg_image, (rect.width, rect.height))
                darkened = scaled_img.copy()
                dark_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                dark_surface.fill((100, 100, 100, 255))
                darkened.blit(dark_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                self._button_base_cache[btn_key] = darkened

            if is_hovering:
                # Only .copy() + brighten for the hovered button (rare — 1 at a time)
                modified_img = self._button_base_cache[btn_key].copy()
                bright_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                bright_surface.fill((40, 40, 40, 0))
                modified_img.blit(bright_surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
                self.screen.blit(modified_img, rect.topleft)
            else:
                # FPS OPT: Blit directly from cache — no .copy() needed
                self.screen.blit(self._button_base_cache[btn_key], rect.topleft)
        else:
            # Fallback solid color button
            color = (80, 80, 120) if not is_hovering else (100, 100, 150)
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, WHITE, rect, 2)

        # FPS OPT: Cache button text render (avoids font.render() every frame)
        if not hasattr(self, '_button_text_cache'):
            self._button_text_cache = {}
        if text not in self._button_text_cache:
            self._button_text_cache[text] = self.button_font.render(text, True, WHITE)
        text_surface = self._button_text_cache[text]
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def _render_strength_bars(self):
        """Render the strength comparison bars using BattleBar.png as border."""
        # Calculate fill Y position (offset from bar rect for independent positioning)
        fill_y = self.attacker_bar_rect.top + self.bar_fill_offset

        # Draw bar backgrounds (dark fill area) at offset position
        attacker_fill_rect = pygame.Rect(
            self.attacker_bar_rect.left, fill_y,
            self.attacker_bar_rect.width, self.attacker_bar_rect.height
        )
        defender_fill_rect = pygame.Rect(
            self.defender_bar_rect.left, fill_y,
            self.defender_bar_rect.width, self.defender_bar_rect.height
        )
        pygame.draw.rect(self.screen, DARK_GRAY, attacker_fill_rect)
        pygame.draw.rect(self.screen, DARK_GRAY, defender_fill_rect)

        # Draw fills at offset position
        if self.attacker_fill > 0:
            fill_width = int(self.attacker_bar_rect.width * self.attacker_fill)
            fill_rect = pygame.Rect(
                self.attacker_bar_rect.left,
                fill_y,
                fill_width,
                self.attacker_bar_rect.height
            )
            pygame.draw.rect(self.screen, self.attacker_color, fill_rect)

        if self.defender_fill > 0:
            fill_width = int(self.defender_bar_rect.width * self.defender_fill)
            fill_rect = pygame.Rect(
                self.defender_bar_rect.left,
                fill_y,
                fill_width,
                self.defender_bar_rect.height
            )
            pygame.draw.rect(self.screen, self.defender_color, fill_rect)

        # Draw borders using BattleBar.png if available
        # P2 fix: use pre-scaled bar border instead of smoothscale per frame
        if self._scaled_bar_border:
            # Center PNG both vertically and horizontally over the fill area
            png_offset_y = (self.attacker_bar_rect.height - self.bar_png_height) // 2
            attacker_png_x = self.attacker_bar_rect.centerx - self.bar_png_width // 2
            defender_png_x = self.defender_bar_rect.centerx - self.bar_png_width // 2
            self.screen.blit(self._scaled_bar_border, (attacker_png_x, self.attacker_bar_rect.top + png_offset_y))
            self.screen.blit(self._scaled_bar_border, (defender_png_x, self.defender_bar_rect.top + png_offset_y))
        else:
            # Fallback to simple rectangle borders
            pygame.draw.rect(self.screen, WHITE, self.attacker_bar_rect, BAR_BORDER_WIDTH)
            pygame.draw.rect(self.screen, WHITE, self.defender_bar_rect, BAR_BORDER_WIDTH)

    def _render_setup(self):
        """Render the SETUP state (panels, icon, resolve button)."""
        # Render panels
        attacker_name = self.game_state.get_player_name(self.attacker_player) if self.attacker_player is not None else "Unknown"
        self._render_panel(
            self.attacker_panel_rect,
            attacker_name,
            self.attacker_color,
            self.territory,
            self.attacker_composition,
            self.attacker_strength,
            is_defender=False
        )

        defender_name = "Defenders"
        if self.defender_players:
            if len(self.defender_players) == 1:
                defender_name = self.game_state.get_player_name(self.defender_players[0])
            else:
                defender_name = f"{len(self.defender_players)} Defenders"
        self._render_panel(
            self.defender_panel_rect,
            defender_name,
            self.defender_color,
            self.territory,
            self.defender_composition,
            self.defender_strength,
            is_defender=True
        )

        # Render battle icon with pulsation animation
        if self.battle_icon and self.battle_icon_base_w > 0:
            # Calculate pulse scale using sine wave for smooth animation
            pulse_progress = (math.sin(self.elapsed * ICON_PULSE_SPEED * 2 * math.pi) + 1) / 2
            current_scale = ICON_PULSE_MIN_SCALE + (ICON_PULSE_MAX_SCALE - ICON_PULSE_MIN_SCALE) * pulse_progress

            # Scale the icon
            scaled_w = int(self.battle_icon_base_w * current_scale)
            scaled_h = int(self.battle_icon_base_h * current_scale)
            scaled_icon = pygame.transform.smoothscale(self.battle_icon, (scaled_w, scaled_h))

            # Center it at the stored center position
            icon_x = self.icon_center_x - scaled_w // 2
            icon_y = self.icon_center_y - scaled_h // 2
            self.screen.blit(scaled_icon, (icon_x, icon_y))

        # Render resolve button
        self._render_button(self.resolve_button_rect, "Resolve Battle", self.button_bg)

        # Render strength bars
        self._render_strength_bars()

    def _render_animating(self):
        """Render the ANIMATING state (particle combat)."""
        # Render panels (static during animation)
        attacker_name = self.game_state.get_player_name(self.attacker_player) if self.attacker_player is not None else "Unknown"
        self._render_panel(
            self.attacker_panel_rect,
            attacker_name,
            self.attacker_color,
            self.territory,
            self.attacker_composition,
            self.attacker_strength,
            is_defender=False
        )

        defender_name = "Defenders"
        if self.defender_players:
            if len(self.defender_players) == 1:
                defender_name = self.game_state.get_player_name(self.defender_players[0])
        self._render_panel(
            self.defender_panel_rect,
            defender_name,
            self.defender_color,
            self.territory,
            self.defender_composition,
            self.defender_strength,
            is_defender=True
        )

        # Render battle icon with pulsation animation
        if self.battle_icon and self.battle_icon_base_w > 0:
            # Calculate pulse scale using sine wave for smooth animation
            pulse_progress = (math.sin(self.elapsed * ICON_PULSE_SPEED * 2 * math.pi) + 1) / 2
            current_scale = ICON_PULSE_MIN_SCALE + (ICON_PULSE_MAX_SCALE - ICON_PULSE_MIN_SCALE) * pulse_progress

            # Scale the icon
            scaled_w = int(self.battle_icon_base_w * current_scale)
            scaled_h = int(self.battle_icon_base_h * current_scale)
            scaled_icon = pygame.transform.smoothscale(self.battle_icon, (scaled_w, scaled_h))

            # Center it at the stored center position
            icon_x = self.icon_center_x - scaled_w // 2
            icon_y = self.icon_center_y - scaled_h // 2
            self.screen.blit(scaled_icon, (icon_x, icon_y))

        # Render particle effect (includes animated bars)
        if self.particle_effect:
            self.particle_effect.render(self.screen)

    def _render_splash(self):
        """Render the SPLASH state (victory/defeat image)."""
        if self.splash_effect:
            self.splash_effect.render(self.screen)

    def _render_report(self):
        """Render the REPORT state (battle summary with unit type breakdown)."""
        # P3 fix: use pre-scaled report panel background
        if self._scaled_report_bg:
            self.screen.blit(self._scaled_report_bg, self.report_panel_rect.topleft)
        elif self.panel_bg:
            self.screen.blit(pygame.transform.smoothscale(
                self.panel_bg, (self.report_panel_rect.width, self.report_panel_rect.height)),
                self.report_panel_rect.topleft)
        else:
            pygame.draw.rect(self.screen, (40, 40, 60), self.report_panel_rect)
            pygame.draw.rect(self.screen, WHITE, self.report_panel_rect, 2)

        # Content with major padding for BattlePlayerScreen.png
        padding = self.panel_content_padding if self.panel_bg else self.text_padding
        content_x = self.report_panel_rect.left + padding
        content_width = self.report_panel_rect.width - padding * 2
        y = self.report_panel_rect.top + padding
        center_x = self.report_panel_rect.centerx

        # Title
        title = self.title_font.render("Battle Report:", True, WHITE)
        title_rect = title.get_rect(centerx=center_x, top=y)
        self.screen.blit(title, title_rect)
        y += self.text_line_height + self.report_line_spacing

        # Territory name
        territory_text = self.text_font.render(self.territory, True, WHITE)
        territory_rect = territory_text.get_rect(centerx=center_x, top=y)
        self.screen.blit(territory_text, territory_rect)
        y += self.text_line_height + self.report_line_spacing + int(5 * self.scale)

        # Separator
        pygame.draw.line(self.screen, WHITE,
                        (content_x, y),
                        (content_x + content_width, y),
                        1)
        y += int(15 * self.scale)

        # Victory/Defeat
        if self.current_player_won:
            result_text = "VICTORY"
            result_color = (100, 255, 100)
        else:
            result_text = "DEFEAT"
            result_color = (255, 100, 100)

        result_surface = self.title_font.render(result_text, True, result_color)
        result_rect = result_surface.get_rect(centerx=center_x, top=y)
        self.screen.blit(result_surface, result_rect)
        y += self.text_line_height + self.report_line_spacing + int(5 * self.scale)

        # Separator
        pygame.draw.line(self.screen, WHITE,
                        (content_x, y),
                        (content_x + content_width, y),
                        1)
        y += int(15 * self.scale)

        # Battle summary
        if self.battle_result:
            # "Your Units:" header
            your_units_header = self.text_font.render("Your Units:", True, WHITE)
            self.screen.blit(your_units_header, (content_x, y))
            y += self.text_line_height

            # Unit type breakdown for current player
            unit_breakdown = self.battle_result.get('unit_breakdown', {})
            if unit_breakdown:
                for unit_type, data in sorted(unit_breakdown.items()):
                    lost = data['lost']
                    survived = data['survived']
                    original = data['original']

                    if survived == 0:
                        unit_text = f"  {unit_type}: {lost} lost (all)"
                        text_color = (255, 150, 150)  # Reddish for total loss
                    elif lost == 0:
                        unit_text = f"  {unit_type}: {survived} survived (no losses)"
                        text_color = (150, 255, 150)  # Greenish for no losses
                    else:
                        unit_text = f"  {unit_type}: {lost} lost, {survived} survived"
                        text_color = WHITE

                    unit_surface = self.small_font.render(unit_text, True, text_color)
                    self.screen.blit(unit_surface, (content_x, y))
                    y += self.text_line_height - int(8 * self.scale)
            else:
                # Fallback if no breakdown available
                no_data = self.small_font.render("  No unit data available", True, (150, 150, 150))
                self.screen.blit(no_data, (content_x, y))
                y += self.text_line_height - int(8 * self.scale)

            # Add spacing before total summary
            y += self.report_line_spacing

            # Total summary line
            if self.current_player == self.attacker_player:
                total_lost = self.battle_result['attacker_lost']
                total_survived = self.battle_result['attacker_survivors']
            else:
                total_lost = self.battle_result['defender_lost']
                total_survived = self.battle_result['defender_survivors']

            total_text = f"Total: {total_lost} lost, {total_survived} survived"
            total_surface = self.text_font.render(total_text, True, WHITE)
            self.screen.blit(total_surface, (content_x, y))

        # Close button
        self._render_button(self.close_button_rect, "Close", self.button_bg)

    def render(self):
        """Render the current state of the interface."""
        # Always render overlay first
        self._render_overlay()

        # Render based on state
        if self.state == BattleInterfaceState.SETUP:
            self._render_setup()
        elif self.state == BattleInterfaceState.ANIMATING:
            self._render_animating()
        elif self.state == BattleInterfaceState.SPLASH:
            self._render_splash()
        elif self.state == BattleInterfaceState.REPORT:
            self._render_report()

    def is_finished(self):
        """Check if interface should close."""
        return self.is_finished_flag

    def get_battle_result(self):
        """
        Get the pre-calculated battle result.

        Returns:
            dict with 'winner', 'attacker_survivors', 'defender_survivors', etc.
            or None if battle hasn't been resolved yet.
        """
        return self.battle_result
