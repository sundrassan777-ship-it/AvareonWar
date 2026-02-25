# -*- coding: utf-8 -*-
# cutscene_player.py
# Campaign cutscene player -- Ken Burns camera panning over still images

"""
Cutscene Player
===============

Plays cinematic cutscenes before and after campaign missions.
Each cutscene is a sequence of slides, where each slide is a still image
with camera viewport panning from point A to point B (Ken Burns effect).

Features:
- Smooth camera pan/zoom/rotation between two viewport rects per slide
- Crossfade transitions between slides
- Dual-track audio: voiceover + music per slide, each with independent volume/delay
- Subtitle text overlay at bottom of screen
- Skippable with ESC or left-click (fade-to-black exit)

Usage:
    from cutscene_player import CutscenePlayer
    player = CutscenePlayer(screen, "mission_1_intro")
    if player.has_cutscene:
        player.run()
"""

import pygame
import json
import os
import math


# ========================================================================
# EASING FUNCTIONS
# ========================================================================

def _ease_linear(t):
    """Linear interpolation (no easing)."""
    return t

def _ease_in_out(t):
    """Cubic ease-in-out for smooth camera motion."""
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        p = 2.0 * t - 2.0
        return 0.5 * p * p * p + 1.0

def _ease_in(t):
    """Cubic ease-in (slow start, fast end)."""
    return t * t * t

def _ease_out(t):
    """Cubic ease-out (fast start, slow end)."""
    p = t - 1.0
    return p * p * p + 1.0

# Map easing string names to functions
EASING_FUNCTIONS = {
    'linear': _ease_linear,
    'ease_in_out': _ease_in_out,
    'ease_in': _ease_in,
    'ease_out': _ease_out,
}


# ========================================================================
# CUTSCENE PLAYER
# ========================================================================

class CutscenePlayer:
    """
    Blocking cutscene screen that plays a Ken Burns-style cinematic.
    Follows the same pattern as CampaignScreen/RecapScreen -- own event loop,
    receives the screen surface, returns when done.
    """

    # Path to cutscene data file
    DATA_FILE = 'cutscene_data.json'

    # Duration of the fade-to-black when skipping (seconds)
    SKIP_FADE_DURATION = 0.5

    # Duration of fade-in from black at cutscene start (seconds)
    FADE_IN_DURATION = 1.5

    # Duration of fade-out to black at natural cutscene end (seconds)
    FADE_OUT_DURATION = 1.5

    # Duration the "Press ESC to skip" hint stays visible (seconds)
    SKIP_HINT_DURATION = 3.0

    # Audio crossfade duration when transitioning slides (seconds)
    AUDIO_FADE_MS = 500

    # Subtitle bar styling
    SUBTITLE_BAR_ALPHA = 160       # Semi-transparent black bar behind subtitles
    SUBTITLE_MARGIN_BOTTOM = 40    # Pixels from bottom of screen
    SUBTITLE_PADDING_X = 40        # Horizontal padding inside subtitle bar
    SUBTITLE_PADDING_Y = 12        # Vertical padding inside subtitle bar
    SUBTITLE_MAX_WIDTH_RATIO = 0.7 # Max width of subtitle text as ratio of screen width

    # Rotation padding factor -- how much extra to crop around viewport for rotation headroom
    ROTATION_PAD_FACTOR = 0.25

    def __init__(self, screen, cutscene_id):
        """
        Initialize the cutscene player.

        Args:
            screen: The pygame display surface to render onto.
            cutscene_id: String key into cutscene_data.json (e.g. "mission_1_intro").
        """
        self.screen = screen
        self.screen_width = screen.get_width()
        self.screen_height = screen.get_height()
        self.screen_aspect = self.screen_width / self.screen_height
        self.clock = pygame.time.Clock()

        # Load cutscene data
        self.cutscene_data = None
        self.slides = []
        self._load_cutscene_data(cutscene_id)

        # Pre-loaded assets (images and dual-track audio)
        self._images = {}       # slide index -> pygame.Surface
        self._voices = {}       # slide index -> pygame.mixer.Sound (voiceover)
        self._music = {}        # slide index -> pygame.mixer.Sound (background music)
        self._voice_channel = None   # Currently active voiceover channel
        self._music_channel = None   # Currently active music channel
        self._current_music_path = None  # Path of currently playing music (for persistence across slides)

        # Playback state
        self._current_slide = 0
        self._slide_elapsed = 0.0       # Time elapsed within current slide
        self._global_elapsed = 0.0      # Total cutscene elapsed time
        self._slide_start_times = []    # Computed start time for each slide
        self._slide_end_times = []      # Computed end time for each slide
        self._voice_triggered = set()   # Set of slide indices whose voiceover has been triggered
        self._music_triggered = set()   # Set of slide indices whose music has been triggered

        # Skip/exit state
        self._skipping = False
        self._skip_fade_elapsed = 0.0
        self._fade_duration = self.SKIP_FADE_DURATION  # Active fade duration (skip vs natural end)
        self._done = False

        # Reusable rendering surfaces (avoid per-frame allocation)
        self._render_surface_a = pygame.Surface((self.screen_width, self.screen_height))
        self._render_surface_b = pygame.Surface((self.screen_width, self.screen_height))
        self._fade_overlay = pygame.Surface((self.screen_width, self.screen_height))  # Reusable black overlay for fades

        # Font for subtitles and skip hint
        self._subtitle_font = None
        self._hint_font = None
        self._init_fonts()

        # Pre-load assets if cutscene exists
        if self.has_cutscene:
            self._preload_assets()
            self._compute_timeline()

    # ========================================================================
    # DATA LOADING
    # ========================================================================

    def _load_cutscene_data(self, cutscene_id):
        """Load cutscene definition from JSON file."""
        if not os.path.exists(self.DATA_FILE):
            return

        try:
            with open(self.DATA_FILE, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        if cutscene_id in all_data and 'slides' in all_data[cutscene_id]:
            self.cutscene_data = all_data[cutscene_id]
            self.slides = self.cutscene_data['slides']

    @property
    def has_cutscene(self):
        """Returns True if this cutscene has valid data with at least one slide."""
        return len(self.slides) > 0

    # ========================================================================
    # ASSET LOADING
    # ========================================================================

    def _init_fonts(self):
        """Initialize fonts for subtitles and UI hints."""
        # Scale fonts based on screen height (matching game's ui_scale pattern)
        ui_scale = self.screen_height / 1080.0

        # Try Cinzel font (matching game style), fall back to default
        font_path = 'assets/fonts/Cinzel-Regular.ttf'
        bold_font_path = 'assets/fonts/Cinzel-SemiBold.ttf'

        subtitle_size = max(18, int(28 * ui_scale))
        hint_size = max(14, int(20 * ui_scale))

        try:
            self._subtitle_font = pygame.font.Font(bold_font_path, subtitle_size)
            self._hint_font = pygame.font.Font(font_path, hint_size)
        except (FileNotFoundError, OSError):
            # Fallback to default pygame font
            self._subtitle_font = pygame.font.Font(None, subtitle_size)
            self._hint_font = pygame.font.Font(None, hint_size)

    def _preload_assets(self):
        """Pre-load all images and audio files referenced by the cutscene slides."""
        for i, slide in enumerate(self.slides):
            # Load image
            image_path = slide.get('image', '')
            if image_path and os.path.exists(image_path):
                try:
                    img = pygame.image.load(image_path).convert_alpha()
                    self._images[i] = img
                except pygame.error as e:
                    print(f"CutscenePlayer: Could not load image {image_path}: {e}")

            # Load voiceover audio
            audio_path = slide.get('audio')
            if audio_path and os.path.exists(audio_path):
                try:
                    sound = pygame.mixer.Sound(audio_path)
                    # Apply voice volume (default 1.0)
                    sound.set_volume(slide.get('audio_volume', 1.0))
                    self._voices[i] = sound
                except pygame.error as e:
                    print(f"CutscenePlayer: Could not load voiceover {audio_path}: {e}")

            # Load music track
            music_path = slide.get('music')
            if music_path and os.path.exists(music_path):
                try:
                    music = pygame.mixer.Sound(music_path)
                    # Apply music volume (default 0.4 -- lower than voice by default)
                    music.set_volume(slide.get('music_volume', 0.4))
                    self._music[i] = music
                except pygame.error as e:
                    print(f"CutscenePlayer: Could not load music {music_path}: {e}")

    # ========================================================================
    # TIMELINE COMPUTATION
    # ========================================================================

    def _compute_timeline(self):
        """
        Compute the absolute start and end times for each slide,
        accounting for crossfade overlaps.

        Slide N overlaps with slide N-1 by crossfade_duration seconds.
        During the overlap, both slides are rendered with alpha blending.
        """
        self._slide_start_times = []
        self._slide_end_times = []

        current_time = 0.0
        for i, slide in enumerate(self.slides):
            pan_duration = slide.get('pan_duration', 5.0)
            crossfade = slide.get('crossfade_duration', 0.0) if i > 0 else 0.0

            # This slide starts crossfade_duration seconds before the previous slide ends
            start_time = max(0.0, current_time - crossfade)
            end_time = start_time + pan_duration

            self._slide_start_times.append(start_time)
            self._slide_end_times.append(end_time)

            # Next slide starts at this slide's end (minus potential crossfade)
            current_time = end_time

        # Total cutscene duration is the end of the last slide
        self._total_duration = self._slide_end_times[-1] if self._slide_end_times else 0.0

    # ========================================================================
    # MAIN LOOP
    # ========================================================================

    def run(self):
        """
        Main blocking event loop. Plays the cutscene and returns when done.
        Returns None.
        """
        if not self.has_cutscene:
            return

        self._done = False
        self._global_elapsed = 0.0

        while not self._done:
            dt = self.clock.tick(60) / 1000.0  # Delta time in seconds
            # Cap delta time to prevent large jumps (e.g. window drag on Windows)
            dt = min(dt, 0.1)

            self._handle_events()
            self._update(dt)
            self._render()
            pygame.display.flip()

    # ========================================================================
    # EVENT HANDLING
    # ========================================================================

    def _handle_events(self):
        """Process input events -- ESC or left-click to skip."""
        import sys
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._start_skip()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self._start_skip()

    def _start_skip(self, natural=False):
        """Begin the fade-to-black sequence. Uses longer duration for natural endings."""
        if not self._skipping:
            self._skipping = True
            self._skip_fade_elapsed = 0.0
            self._fade_duration = self.FADE_OUT_DURATION if natural else self.SKIP_FADE_DURATION
            # Fade out both audio channels (match fade duration)
            fade_ms = int(self._fade_duration * 1000)
            if self._voice_channel and self._voice_channel.get_busy():
                self._voice_channel.fadeout(fade_ms)
            if self._music_channel and self._music_channel.get_busy():
                self._music_channel.fadeout(fade_ms)

    # ========================================================================
    # UPDATE
    # ========================================================================

    def _update(self, dt):
        """Advance cutscene state by delta time."""
        if self._skipping:
            # Advance skip/end fade
            self._skip_fade_elapsed += dt
            if self._skip_fade_elapsed >= self._fade_duration:
                self._done = True
            return

        # Advance global elapsed time
        self._global_elapsed += dt

        # Check if cutscene has ended naturally
        if self._global_elapsed >= self._total_duration:
            # Start a graceful fade-out at the natural end (longer than skip)
            self._start_skip(natural=True)
            return

        # Trigger audio for slides that have become active
        self._update_audio()

    def _update_audio(self):
        """
        Update both audio channels (voice + music) based on current time.
        Voice: per-slide, fades out when a new slide's voice starts.
        Music: persists across slides if the same track is used; crossfades when track changes.
        """
        for i, slide in enumerate(self.slides):
            start_time = self._slide_start_times[i]

            # --- Voiceover channel ---
            if i not in self._voice_triggered:
                voice_delay = slide.get('audio_start_delay', 0.0)
                voice_trigger = start_time + voice_delay

                if self._global_elapsed >= voice_trigger and i in self._voices:
                    # Fade out previous voice if playing
                    if self._voice_channel and self._voice_channel.get_busy():
                        self._voice_channel.fadeout(self.AUDIO_FADE_MS)
                    # Play this slide's voiceover
                    self._voice_channel = self._voices[i].play()
                    self._voice_triggered.add(i)

            # --- Music channel ---
            if i not in self._music_triggered:
                music_delay = slide.get('music_start_delay', 0.0)
                music_trigger = start_time + music_delay

                if self._global_elapsed >= music_trigger:
                    music_path = slide.get('music', '')

                    if i in self._music:
                        # This slide has a music track
                        if music_path != self._current_music_path:
                            # Different track than what's playing -- crossfade
                            if self._music_channel and self._music_channel.get_busy():
                                self._music_channel.fadeout(self.AUDIO_FADE_MS)
                            self._music_channel = self._music[i].play()
                            self._current_music_path = music_path
                        # Same track -- let it keep playing (no restart)
                        self._music_triggered.add(i)
                    elif not music_path:
                        # No music on this slide -- fade out current music if playing
                        if self._music_channel and self._music_channel.get_busy():
                            self._music_channel.fadeout(self.AUDIO_FADE_MS)
                        self._current_music_path = None
                        self._music_triggered.add(i)

    # ========================================================================
    # RENDERING
    # ========================================================================

    def _render(self):
        """Render the current frame of the cutscene with fade-in/fade-out overlays."""
        self.screen.fill((0, 0, 0))

        if self._skipping:
            # During skip/end: render last frame with increasing black overlay
            self._render_cutscene_frame()
            fade_progress = min(1.0, self._skip_fade_elapsed / self._fade_duration)
            self._fade_overlay.fill((0, 0, 0))
            self._fade_overlay.set_alpha(int(255 * fade_progress))
            self.screen.blit(self._fade_overlay, (0, 0))
            return

        self._render_cutscene_frame()

        # Fade-in from black at the start of the cutscene
        if self._global_elapsed < self.FADE_IN_DURATION:
            fade_in_progress = self._global_elapsed / self.FADE_IN_DURATION
            self._fade_overlay.fill((0, 0, 0))
            self._fade_overlay.set_alpha(int(255 * (1.0 - fade_in_progress)))
            self.screen.blit(self._fade_overlay, (0, 0))

    def _render_cutscene_frame(self):
        """Render the Ken Burns frame for the current global time."""
        t = self._global_elapsed

        # During fade-out, clamp time so the last slide remains visible
        # (otherwise t slightly past _total_duration means no active slides → black frame)
        if self._skipping and self._total_duration > 0 and t >= self._total_duration:
            t = self._total_duration - 0.001

        # Find which slides are active at time t
        # There can be at most 2 active slides during a crossfade
        active_slides = []
        for i in range(len(self.slides)):
            if self._slide_start_times[i] <= t <= self._slide_end_times[i]:
                active_slides.append(i)

        if not active_slides:
            return

        if len(active_slides) == 1:
            # Single slide, no crossfade -- render directly to screen
            idx = active_slides[0]
            slide_progress = self._get_slide_progress(idx, t)
            self._render_slide_to_surface(idx, slide_progress, self.screen)
            self._render_subtitle(idx, 1.0)

        elif len(active_slides) >= 2:
            # Crossfade between the last two active slides
            outgoing_idx = active_slides[-2]
            incoming_idx = active_slides[-1]

            # Compute crossfade progress (0 = fully outgoing, 1 = fully incoming)
            crossfade_duration = self.slides[incoming_idx].get('crossfade_duration', 1.0)
            if crossfade_duration > 0:
                # Time since the incoming slide started
                crossfade_elapsed = t - self._slide_start_times[incoming_idx]
                fade_progress = min(1.0, crossfade_elapsed / crossfade_duration)
            else:
                fade_progress = 1.0

            # Render outgoing slide
            outgoing_progress = self._get_slide_progress(outgoing_idx, t)
            self._render_slide_to_surface(outgoing_idx, outgoing_progress, self._render_surface_a)
            self._render_surface_a.set_alpha(int(255 * (1.0 - fade_progress)))
            self.screen.blit(self._render_surface_a, (0, 0))

            # Render incoming slide
            incoming_progress = self._get_slide_progress(incoming_idx, t)
            self._render_slide_to_surface(incoming_idx, incoming_progress, self._render_surface_b)
            self._render_surface_b.set_alpha(int(255 * fade_progress))
            self.screen.blit(self._render_surface_b, (0, 0))

            # Render subtitle from the incoming slide (fading in)
            self._render_subtitle(incoming_idx, fade_progress)

        # Render skip hint (fades out after SKIP_HINT_DURATION)
        self._render_skip_hint()

    def _get_slide_progress(self, slide_idx, global_time):
        """
        Get the eased progress (0.0 to 1.0) for a slide at the given global time.
        """
        slide = self.slides[slide_idx]
        pan_duration = slide.get('pan_duration', 5.0)
        start_time = self._slide_start_times[slide_idx]

        # Raw linear progress
        elapsed = global_time - start_time
        raw_progress = max(0.0, min(1.0, elapsed / pan_duration)) if pan_duration > 0 else 1.0

        # Apply easing function
        easing_name = slide.get('easing', 'ease_in_out')
        easing_fn = EASING_FUNCTIONS.get(easing_name, _ease_in_out)
        return easing_fn(raw_progress)

    def _render_slide_to_surface(self, slide_idx, progress, target_surface):
        """
        Render a single slide's Ken Burns frame at the given progress to target_surface.

        progress: 0.0 = camera at rect A, 1.0 = camera at rect B.
        """
        slide = self.slides[slide_idx]

        # Get source image
        if slide_idx not in self._images:
            target_surface.fill((0, 0, 0))
            return

        src_image = self._images[slide_idx]
        img_w = src_image.get_width()
        img_h = src_image.get_height()

        # Get camera rects A and B
        cam_a = slide.get('camera_a', {'x': 0, 'y': 0, 'width': img_w, 'height': img_h, 'rotation': 0})
        cam_b = slide.get('camera_b', cam_a)

        # Interpolate camera rect between A and B
        cx = cam_a['x'] + (cam_b['x'] - cam_a['x']) * progress
        cy = cam_a['y'] + (cam_b['y'] - cam_a['y']) * progress
        cw = cam_a['width'] + (cam_b['width'] - cam_a['width']) * progress
        ch = cam_a['height'] + (cam_b['height'] - cam_a['height']) * progress
        crot = cam_a.get('rotation', 0) + (cam_b.get('rotation', 0) - cam_a.get('rotation', 0)) * progress

        # Ensure valid dimensions
        cw = max(1, cw)
        ch = max(1, ch)

        if abs(crot) < 0.01:
            # No rotation -- simple crop and scale
            self._render_simple_crop(src_image, cx, cy, cw, ch, img_w, img_h, target_surface)
        else:
            # With rotation -- need extra padding for rotation headroom
            self._render_rotated_crop(src_image, cx, cy, cw, ch, crot, img_w, img_h, target_surface)

    def _render_simple_crop(self, src_image, cx, cy, cw, ch, img_w, img_h, target_surface):
        """Crop viewport from source image and scale to target surface (no rotation)."""
        # Clamp crop rect to image bounds
        x1 = max(0, int(cx))
        y1 = max(0, int(cy))
        x2 = min(img_w, int(cx + cw))
        y2 = min(img_h, int(cy + ch))

        crop_w = max(1, x2 - x1)
        crop_h = max(1, y2 - y1)

        # Use subsurface for zero-copy crop
        try:
            crop_rect = pygame.Rect(x1, y1, crop_w, crop_h)
            cropped = src_image.subsurface(crop_rect)
        except ValueError:
            target_surface.fill((0, 0, 0))
            return

        # Scale cropped region to fill target surface
        scaled = pygame.transform.smoothscale(cropped, (self.screen_width, self.screen_height))
        target_surface.blit(scaled, (0, 0))

    def _render_rotated_crop(self, src_image, cx, cy, cw, ch, rotation, img_w, img_h, target_surface):
        """
        Crop viewport with rotation from source image.
        Crops a padded area, rotates it, then re-crops the center to the target aspect ratio.
        """
        # Pad the crop area to avoid black corners after rotation
        pad_w = cw * self.ROTATION_PAD_FACTOR
        pad_h = ch * self.ROTATION_PAD_FACTOR

        # Padded crop bounds (clamped to image)
        px1 = max(0, int(cx - pad_w))
        py1 = max(0, int(cy - pad_h))
        px2 = min(img_w, int(cx + cw + pad_w))
        py2 = min(img_h, int(cy + ch + pad_h))

        padded_w = max(1, px2 - px1)
        padded_h = max(1, py2 - py1)

        try:
            padded_rect = pygame.Rect(px1, py1, padded_w, padded_h)
            padded_crop = src_image.subsurface(padded_rect)
        except ValueError:
            target_surface.fill((0, 0, 0))
            return

        # Rotate the padded crop (pygame.transform.rotate expands the surface to fit)
        rotated = pygame.transform.rotate(padded_crop, rotation)
        rot_w = rotated.get_width()
        rot_h = rotated.get_height()

        # Extract the center region matching our target aspect ratio
        # The viewport center in the padded crop was at (cx - px1 + cw/2, cy - py1 + ch/2)
        # After rotation, the center of the rotated surface corresponds to the center of the padded crop
        center_x = rot_w / 2.0
        center_y = rot_h / 2.0

        # Determine the crop size from the rotated surface that covers the original viewport
        # Use the original viewport dimensions (before padding)
        extract_w = min(int(cw), rot_w)
        extract_h = min(int(ch), rot_h)

        ex1 = max(0, int(center_x - extract_w / 2.0))
        ey1 = max(0, int(center_y - extract_h / 2.0))
        ex2 = min(rot_w, ex1 + extract_w)
        ey2 = min(rot_h, ey1 + extract_h)

        final_w = max(1, ex2 - ex1)
        final_h = max(1, ey2 - ey1)

        try:
            final_rect = pygame.Rect(ex1, ey1, final_w, final_h)
            final_crop = rotated.subsurface(final_rect)
        except ValueError:
            target_surface.fill((0, 0, 0))
            return

        # Scale to screen size
        scaled = pygame.transform.smoothscale(final_crop, (self.screen_width, self.screen_height))
        target_surface.blit(scaled, (0, 0))

    # ========================================================================
    # SUBTITLE RENDERING
    # ========================================================================

    def _render_subtitle(self, slide_idx, alpha_factor=1.0):
        """
        Render subtitle text at the bottom of the screen with a semi-transparent bar.

        Args:
            slide_idx: Index of the slide whose subtitle to render.
            alpha_factor: 0.0 to 1.0 for fade-in during crossfade.
        """
        if slide_idx >= len(self.slides):
            return

        subtitle_text = self.slides[slide_idx].get('subtitle', '')
        if not subtitle_text:
            return

        # Word-wrap the subtitle text
        max_text_width = int(self.screen_width * self.SUBTITLE_MAX_WIDTH_RATIO)
        lines = self._wrap_text(subtitle_text, self._subtitle_font, max_text_width)
        if not lines:
            return

        # Render each line to get dimensions
        rendered_lines = []
        total_height = 0
        max_line_width = 0
        for line in lines:
            line_surface = self._subtitle_font.render(line, True, (255, 255, 255))
            rendered_lines.append(line_surface)
            total_height += line_surface.get_height()
            max_line_width = max(max_line_width, line_surface.get_width())

        # Add line spacing
        line_spacing = 4
        total_height += line_spacing * (len(rendered_lines) - 1)

        # Calculate bar dimensions
        bar_width = max_line_width + self.SUBTITLE_PADDING_X * 2
        bar_height = total_height + self.SUBTITLE_PADDING_Y * 2
        bar_x = (self.screen_width - bar_width) // 2
        bar_y = self.screen_height - self.SUBTITLE_MARGIN_BOTTOM - bar_height

        # Draw semi-transparent background bar
        alpha = int(self.SUBTITLE_BAR_ALPHA * alpha_factor)
        bar_surface = pygame.Surface((bar_width, bar_height), pygame.SRCALPHA)
        bar_surface.fill((0, 0, 0, alpha))
        self.screen.blit(bar_surface, (bar_x, bar_y))

        # Draw text lines centered within the bar
        text_alpha = int(255 * alpha_factor)
        y_offset = bar_y + self.SUBTITLE_PADDING_Y
        for line_surface in rendered_lines:
            if alpha_factor < 1.0:
                line_surface.set_alpha(text_alpha)
            text_x = bar_x + (bar_width - line_surface.get_width()) // 2
            self.screen.blit(line_surface, (text_x, y_offset))
            y_offset += line_surface.get_height() + line_spacing

    def _render_skip_hint(self):
        """Render 'Press ESC to skip' hint that fades out after a few seconds."""
        if self._global_elapsed > self.SKIP_HINT_DURATION:
            return

        # Fade out over the last 1 second of the hint duration
        if self._global_elapsed > self.SKIP_HINT_DURATION - 1.0:
            alpha = int(255 * (self.SKIP_HINT_DURATION - self._global_elapsed))
        else:
            alpha = 180  # Slightly faded even at full visibility

        hint_text = self._hint_font.render("Press ESC to skip", True, (200, 200, 200))
        hint_text.set_alpha(alpha)

        # Position at bottom-right with margin
        margin = 20
        x = self.screen_width - hint_text.get_width() - margin
        y = self.screen_height - hint_text.get_height() - margin

        self.screen.blit(hint_text, (x, y))

    # ========================================================================
    # UTILITY
    # ========================================================================

    @staticmethod
    def _wrap_text(text, font, max_width):
        """Word-wrap text to fit within max_width pixels."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]
