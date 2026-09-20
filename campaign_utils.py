# -*- coding: utf-8 -*-
# campaign_utils.py
# Shared utilities for campaign missions (2, 3, 4+).
#
# Phase 2C refactoring: extracted duplicated classes that were copy-pasted
# across campaign_mission_2.py, campaign_mission_3.py, and campaign_mission_4.py.
# Each class was ~identical in all missions; this module is the single source of truth.
#
# Contains:
#   - TransmissionOverlay: text overlay with speaker header (~120 lines, was duplicated x3)
#   - CameraPanAnimation: smooth camera pan between territories (~50 lines, was duplicated x2)
#   - CameraZoomAnimation: smooth camera zoom to a territory (~40 lines, was duplicated x3)
#   - update_endgame_sequence / render_endgame_sequence: victory/defeat animation helpers
#     (~80 lines each, were duplicated x3 for victory and x3 for defeat = 6 copies total)

import pygame


# ============================================================================
# TRANSMISSION OVERLAY
# ============================================================================

class TransmissionOverlay:
    """Renders the Transmission Board with speaker header, flush at top-left of map area.

    Extracted from campaign_mission_2/3/4 where it was duplicated identically.
    Used during intro sequences and gameplay events to display narrative text.
    """

    def __init__(self, screen_width, screen_height, text, top_panel_height, speaker=""):
        self.text = text
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.top_panel_height = top_panel_height
        self.speaker = speaker

        # Board dimensions: ~29% screen width (full image including transparent padding)
        self.width = int(screen_width * 0.29)

        # TransmissionBG.png has transparent padding around the visible wooden board.
        # These fractions (measured from the source image) let us align the header
        # with the visible board area and eliminate visual gaps.
        BG_LEFT_FRAC = 0.069   # 6.9% left/right transparent margin
        BG_TOP_FRAC = 0.200    # 20% top transparent margin

        # Load and scale body background (TransmissionBG.png)
        try:
            raw_bg = pygame.image.load('assets/TransmissionBG.png').convert_alpha()
        except pygame.error:
            raw_bg = None

        if raw_bg:
            aspect = raw_bg.get_height() / raw_bg.get_width()
            self.body_height = int(self.width * aspect)
            self.bg_surface = pygame.transform.smoothscale(raw_bg, (self.width, self.body_height))
        else:
            self.body_height = int(screen_height * 0.12)
            self.bg_surface = None

        # Calculate visible body area insets (in scaled pixels)
        bg_left_inset = int(self.width * BG_LEFT_FRAC)
        bg_top_inset = int(self.body_height * BG_TOP_FRAC)
        visible_body_width = self.width - 2 * bg_left_inset

        # Load and scale speaker header (SpeakerBG.png) to match visible body width
        try:
            raw_header = pygame.image.load('assets/SpeakerBG.png').convert_alpha()
        except pygame.error:
            raw_header = None

        if raw_header:
            header_aspect = raw_header.get_height() / raw_header.get_width()
            natural_header_h = int(visible_body_width * header_aspect)
            self.header_height = int(natural_header_h * 0.2)  # 20% of natural height
            self.header_surface = pygame.transform.smoothscale(
                raw_header, (visible_body_width, self.header_height))
        else:
            self.header_height = int(screen_height * 0.03)
            self.header_surface = None

        self.header_width = visible_body_width

        # Header: flush at screen left edge, just below top panel
        self.header_x = 0
        self.header_y = top_panel_height

        # Body: shifted left so visible board edge aligns with screen edge,
        # shifted up so visible board top touches header bottom
        self.body_x = -bg_left_inset
        self.body_y = self.header_y + self.header_height - bg_top_inset

        # Keep self.height for text padding calculations
        self.height = self.body_height

        # Body text font
        try:
            self.font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(14, int(screen_height / 47)))
        except (FileNotFoundError, OSError):
            self.font = pygame.font.SysFont('serif', max(14, int(screen_height / 47)))

        # Speaker name font (bold, slightly smaller)
        try:
            self.speaker_font = pygame.font.Font('assets/fonts/Cinzel-Bold.ttf', max(13, int(screen_height / 52)))
        except (FileNotFoundError, OSError):
            self.speaker_font = pygame.font.SysFont('serif', max(13, int(screen_height / 52)), bold=True)

    def set_text(self, text, speaker=None):
        """Update the displayed text and optionally the speaker."""
        self.text = text
        if speaker is not None:
            self.speaker = speaker

    def render(self, screen):
        """Draw the speaker header + transmission board overlay."""
        # Draw body first (TransmissionBG.png) -- its transparent padding won't cover the header
        if self.bg_surface:
            screen.blit(self.bg_surface, (self.body_x, self.body_y))
        else:
            panel_rect = pygame.Rect(self.body_x, self.body_y, self.width, self.body_height)
            bg = pygame.Surface((self.width, self.body_height), pygame.SRCALPHA)
            bg.fill((20, 20, 30, 220))
            screen.blit(bg, (self.body_x, self.body_y))
            pygame.draw.rect(screen, (180, 160, 100), panel_rect, 2)

        # Draw speaker header (SpeakerBG.png) on top
        if self.header_surface:
            screen.blit(self.header_surface, (self.header_x, self.header_y))
        else:
            hdr_bg = pygame.Surface((self.header_width, self.header_height), pygame.SRCALPHA)
            hdr_bg.fill((40, 30, 20, 230))
            screen.blit(hdr_bg, (self.header_x, self.header_y))
            pygame.draw.rect(screen, (180, 160, 100),
                             pygame.Rect(self.header_x, self.header_y,
                                         self.header_width, self.header_height), 2)

        # Draw speaker name centered on header
        if self.speaker:
            speaker_surface = self.speaker_font.render(self.speaker, True, (255, 255, 240))
            sx = self.header_x + (self.header_width - speaker_surface.get_width()) // 2
            sy = self.header_y + (self.header_height - speaker_surface.get_height()) // 2
            screen.blit(speaker_surface, (sx, sy))

        # Render wrapped text inside the visible body area
        padding_x = int(self.width * 0.12)
        padding_y = int(self.body_height * 0.25)
        text_area_width = self.width - 2 * padding_x
        self._render_wrapped_text(screen, self.text, self.body_x + padding_x,
                                  self.body_y + padding_y, text_area_width)

    def _render_wrapped_text(self, screen, text, x, y, max_width):
        """Render text with word wrapping."""
        words = text.split(' ')
        lines = []
        current_line = ''
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            test_surface = self.font.render(test_line, True, (255, 255, 255))
            if test_surface.get_width() > max_width and current_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)

        line_height = self.font.get_linesize()
        for i, line in enumerate(lines):
            line_surface = self.font.render(line, True, (255, 255, 240))
            screen.blit(line_surface, (x, y + i * line_height))


# ============================================================================
# CAMERA PAN ANIMATION
# ============================================================================

class CameraPanAnimation:
    """Smooth camera pan from current position to a target territory center.

    Extracted from campaign_mission_2 and campaign_mission_3 where it was
    duplicated identically. Uses ease-in-out quadratic for smooth motion.

    The .active attribute is True while animating. update() returns True while
    still animating, False when complete (same convention as missions 2/3).
    """

    def __init__(self, camera_handler, target_center_world, duration, screen_width, map_area_height):
        self.camera = camera_handler
        self.target_center = target_center_world
        self.duration = duration
        self.screen_width = screen_width
        self.map_area_height = map_area_height
        self.elapsed = 0.0
        self.active = True

        # Calculate start center from current camera position
        screen_cx = screen_width / 2.0
        screen_cy = map_area_height / 2.0
        self.start_center = (
            self.camera.offset[0] + screen_cx / self.camera.zoom,
            self.camera.offset[1] + screen_cy / self.camera.zoom
        )

    def update(self, delta_time):
        """Update animation each frame. Returns True while still animating."""
        if not self.active:
            return False

        self.elapsed += delta_time
        progress = min(1.0, self.elapsed / self.duration)

        # Ease-in-out quadratic for smooth pan
        if progress < 0.5:
            eased = 2 * progress * progress
        else:
            eased = 1 - pow(-2 * progress + 2, 2) / 2

        # Interpolate center position
        current_x = self.start_center[0] + (self.target_center[0] - self.start_center[0]) * eased
        current_y = self.start_center[1] + (self.target_center[1] - self.start_center[1]) * eased

        # Update camera offset
        screen_cx = self.screen_width / 2.0
        screen_cy = self.map_area_height / 2.0
        self.camera.offset[0] = current_x - screen_cx / self.camera.zoom
        self.camera.offset[1] = current_y - screen_cy / self.camera.zoom
        self.camera.clamp_to_bounds()

        if progress >= 1.0:
            self.active = False
        return self.active


# ============================================================================
# CAMERA ZOOM ANIMATION
# ============================================================================

class CameraZoomAnimation:
    """Smooth camera zoom animation centered on a target point.

    Extracted from campaign_mission_2, 3, and 4 where it was duplicated.
    Uses ease-out cubic for smooth deceleration.

    API (matches missions 2/3 convention):
      - .active is True while animating
      - update() returns True while still animating, False when complete

    Note: Mission 4 previously had an inverted return value (True=done) and
    a different constructor signature. The unified version uses the missions 2/3
    signature and return convention. Mission 4 callers were updated accordingly.
    """

    def __init__(self, camera_handler, start_zoom, target_zoom, duration, target_center_world,
                 screen_width, map_area_height):
        self.camera = camera_handler
        self.start_zoom = start_zoom
        self.target_zoom = target_zoom
        self.duration = duration
        self.target_center = target_center_world
        self.screen_width = screen_width
        self.map_area_height = map_area_height
        self.elapsed = 0.0
        self.active = True

        # Cancel any in-flight smooth wheel zoom: this animation drives
        # camera.zoom directly, and a pending target would fight it.
        if hasattr(self.camera, 'cancel_zoom_interpolation'):
            self.camera.cancel_zoom_interpolation()

        # Set starting zoom and position
        self.camera.zoom = start_zoom
        self._update_camera_position(0.0)

    def update(self, delta_time):
        """Update animation each frame. Returns True while still animating."""
        if not self.active:
            return False
        self.elapsed += delta_time
        progress = min(1.0, self.elapsed / self.duration)

        # Ease-out cubic for smooth deceleration
        eased = 1.0 - pow(1.0 - progress, 3)

        # Interpolate zoom continuously.
        # This used to be quantized to 0.2 steps (`round(raw_zoom * 5) / 5`) purely to
        # limit how often the map rescale and the production-glow sprite cache were
        # invalidated — which made the intro visibly STEP rather than glide. Both of
        # those costs are gone: the map now rescales only the visible slice (~2.5ms
        # instead of up to 53ms) and glow frames are shared and quantized internally.
        self.camera.zoom = self.start_zoom + (self.target_zoom - self.start_zoom) * eased

        # Keep target centered
        self._update_camera_position(eased)

        if progress >= 1.0:
            # Snap to exact target on final frame for precision
            self.camera.zoom = self.target_zoom
            self._update_camera_position(1.0)
            self.active = False
        return self.active

    def _update_camera_position(self, progress):
        """Adjust camera offset to keep target_center in screen center."""
        screen_cx = self.screen_width / 2.0
        screen_cy = self.map_area_height / 2.0
        self.camera.offset[0] = self.target_center[0] - screen_cx / self.camera.zoom
        self.camera.offset[1] = self.target_center[1] - screen_cy / self.camera.zoom
        self.camera.clamp_to_bounds()


# ============================================================================
# VICTORY / DEFEAT SEQUENCE HELPERS
# ============================================================================
# These functions implement the shared fade -> image_grow -> image_hold -> exit
# animation pattern used by all campaign missions for victory and defeat screens.
#
# Each mission stores its own state attributes (victory_phase, victory_timer, etc.)
# and calls these helpers from its _update_victory_sequence / _update_defeat_sequence
# and _render_victory_sequence / _render_defeat_sequence methods.
#
# Extracted to eliminate ~80 lines of duplication per sequence type per mission
# (6 copies total: 3 victory + 3 defeat across missions 2, 3, 4).

def update_endgame_sequence(mission, delta_time, sequence_type):
    """Update a victory or defeat animation sequence.

    Args:
        mission: The mission instance (must have the standard sequence state attributes).
        delta_time: Frame time delta.
        sequence_type: 'victory' or 'defeat'.

    Returns:
        'exit' when the sequence is complete and the mission should exit,
        None otherwise.

    Expected mission attributes for sequence_type='victory':
        _pending_victory, transmission_overlay, victory_sequence_active,
        victory_phase, victory_timer, victory_image, victory_fade_alpha,
        victory_image_scale
    (Similarly prefixed with 'defeat_' for sequence_type='defeat'.)
    """
    # Attribute name prefixes differ between victory and defeat
    pending_attr = f'_pending_{sequence_type}'
    active_attr = f'{sequence_type}_sequence_active'
    phase_attr = f'{sequence_type}_phase'
    timer_attr = f'{sequence_type}_timer'
    image_attr = f'{sequence_type}_image'
    fade_alpha_attr = f'{sequence_type}_fade_alpha'
    image_scale_attr = f'{sequence_type}_image_scale'

    # Image file for victory vs defeat
    image_file = 'assets/victoryscrn.png' if sequence_type == 'victory' else 'assets/defeatscrn.png'

    # Wait for transmission to finish (timer is incremented by gameplay timer block in update())
    if getattr(mission, pending_attr, False):
        if not mission.transmission_overlay:
            # Transmission expired (cleared by gameplay timer) -- start animation
            setattr(mission, pending_attr, False)
            setattr(mission, active_attr, True)
            setattr(mission, phase_attr, 'fade')
            setattr(mission, timer_attr, 0.0)
            # Load the victory/defeat image
            try:
                setattr(mission, image_attr, pygame.image.load(image_file).convert_alpha())
            except pygame.error:
                setattr(mission, image_attr, None)
        return None

    if not getattr(mission, active_attr, False):
        return None

    # Advance timer
    timer = getattr(mission, timer_attr) + delta_time
    setattr(mission, timer_attr, timer)
    phase = getattr(mission, phase_attr)

    if phase == 'fade':
        # 0.5s black overlay fade-in
        fade_duration = 0.5
        progress = min(timer / fade_duration, 1.0)
        setattr(mission, fade_alpha_attr, int(255 * progress))
        if progress >= 1.0:
            setattr(mission, phase_attr, 'image_grow')
            setattr(mission, timer_attr, 0.0)

    elif phase == 'image_grow':
        # 0.3s image scale-up with ease-out quadratic
        grow_duration = 0.3
        progress = min(timer / grow_duration, 1.0)
        setattr(mission, image_scale_attr, 0.75 * (1.0 - (1.0 - progress) ** 2))
        if progress >= 1.0:
            setattr(mission, phase_attr, 'image_hold')
            setattr(mission, timer_attr, 0.0)

    elif phase == 'image_hold':
        # Hold for 5 seconds then exit
        hold_duration = 5.0
        if timer >= hold_duration:
            setattr(mission, phase_attr, 'exit')
            return 'exit'

    return None


def render_endgame_sequence(mission, screen, sequence_type):
    """Render a victory or defeat animation sequence overlay.

    Args:
        mission: The mission instance (must have the standard sequence state attributes).
        screen: The pygame screen surface to draw on.
        sequence_type: 'victory' or 'defeat'.
    """
    active_attr = f'{sequence_type}_sequence_active'
    phase_attr = f'{sequence_type}_phase'
    fade_alpha_attr = f'{sequence_type}_fade_alpha'
    image_attr = f'{sequence_type}_image'
    image_scale_attr = f'{sequence_type}_image_scale'

    if not getattr(mission, active_attr, False):
        return

    screen_width, screen_height = screen.get_size()

    # Draw black overlay (fade)
    fade_alpha = getattr(mission, fade_alpha_attr, 0)
    if fade_alpha > 0:
        overlay = pygame.Surface((screen_width, screen_height))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(fade_alpha)
        screen.blit(overlay, (0, 0))

    # Draw image (grows from center)
    phase = getattr(mission, phase_attr)
    image = getattr(mission, image_attr, None)
    if phase in ('image_grow', 'image_hold') and image:
        img_width, img_height = image.get_size()
        scale = max(0.01, getattr(mission, image_scale_attr, 0.0))
        scaled_width = int(img_width * scale)
        scaled_height = int(img_height * scale)

        if scaled_width > 0 and scaled_height > 0:
            scaled_img = pygame.transform.smoothscale(image, (scaled_width, scaled_height))
            x = (screen_width - scaled_width) // 2
            y = (screen_height - scaled_height) // 2
            screen.blit(scaled_img, (x, y))
