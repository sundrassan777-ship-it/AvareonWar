# -*- coding: utf-8 -*-
"""
Turn Announcement Effect

The banner that opens a turn ("Empire of Naragonthid's Turn", or "Turn N" in
simultaneous mode), in the light style of the event FX pass (2026-10): the screen
darkens toward its edges, a carved bronze frame round dark parchment grows in
with the name in Cinzel gold, gold light glows round the frame and motes of gold
light drift up round it and along the bottom of the screen. Then it all fades and
the turn begins. (It replaced a flat black overlay, a grey box and 1200 one-pixel
sparkles a second.)

Timeline (unchanged from the sparkle version):
    0.0   - 0.375 s  the screen darkens, the banner grows in
    0.375 - 0.75 s   hold
    0.75  - 1.5 s    the banner and the darkness fade
    1.5 s            complete: on_complete() is called once

Integration:
    - main.py creates one when game_state.turn_announcement_active is set (its
      on_complete is game_state._complete_turn_announcement) and one per
      simultaneous round ("Turn N"); input is blocked until it completes
    - cleanup() is kept for its callers (campaign missions cut an AI's short)

Cost: the vignette is baked once per screen size and the gold glow once per
banner size, both kept between turns; the banner is baked once per announcement
and its growing sizes once each; a frame is a few blits and one blits() call.
"""

import pygame

from ui.effects import light_fx
from ui.effects.light_fx import GlowSprites, GlowFrame, RisingMotes
from ui.effects.order_fx_style import GUIDE_GOLD

# ========================================
# CONSTANTS
# ========================================

REFERENCE_HEIGHT = 900.0      # sizes below are for a 900 px tall screen, scaled to the real one

# Timing (seconds)
EXPLOSION_DURATION = 0.375    # the banner grows in
PAUSE_DURATION = 0.375        # hold
RECEDE_DURATION = 0.75        # the banner fades
TOTAL_DURATION = EXPLOSION_DURATION + PAUSE_DURATION + RECEDE_DURATION

# The darkening: a vignette, lighter where the banner is, deep toward the edges
OVERLAY_CENTRE_ALPHA = 125
OVERLAY_EDGE_ALPHA = 230

# The banner: Cinzel gold over dark parchment, in the carved bronze frame
FONT_PATH = 'assets/fonts/Cinzel-SemiBold.ttf'
TEXT_SIZE = 56
TEXT_COLOUR = (245, 214, 140)         # sidebar_widgets GOLD_LIGHT
TEXT_SHADOW = (18, 11, 4)
TEXT_SHADOW_OFFSET = 2
FILL_TOP = (62, 51, 36)               # dark parchment, lighter at the top
FILL_BOTTOM = (31, 25, 17)
FRAME_BORDER = (22, 18)               # bronze frame thickness (left/right, top/bottom)
PADDING = (60, 34)                    # text to frame
LINE_SPACING = 6
MAX_BANNER_WIDTH = 0.9                # share of the screen width (a long name gets a smaller font)
GROW_FROM = 0.6                       # the banner's scale as it starts growing in
SCALE_STEPS = 12                      # cached sizes while it grows

# The gold light round the frame (order_fx_style GUIDE gold, the tutorial glow's)
GLOW_COLOUR = GUIDE_GOLD
GLOW_REACH = 16                       # px outside the frame
GLOW_INTENSITY = 0.85

# Motes of gold light drifting up: half round the banner, half along the bottom
# of the screen (where the vignette is darkest)
MOTES = {
    'count': 72,
    'life': (0.7, 1.3),               # seconds
    'rise': 70.0,                     # px over a life
    'sway': 6.0,                      # px
    'size': (16.0, 30.0),             # diameter, px (the soft bloom; the hot core is ~1/4)
    'colour': (255, 196, 70),
    'white_mix': 0.3,
    'banner_share': 0.5,              # the rest rise from the bottom band
    'band': 0.22,                     # height of the bottom band, share of the screen
}

# ========================================
# SHARED (kept between turns)
# ========================================

# (Fonts are not kept: a Font used after pygame.font is shut down and started again
# crashes the process - the multiplayer test harness does that between games)
_vignettes = {}      # (w, h) -> darkening vignette
_light = {}          # 'display': its size, 'glow': GlowSprites, 'frames': GlowFrame


def _vignette(size):
    surface = _vignettes.get(size)
    if surface is None:
        _vignettes.clear()   # one screen size at a time
        surface = _vignettes[size] = light_fx.vignette_surface(
            size, (0, 0, 0), OVERLAY_CENTRE_ALPHA, OVERLAY_EDGE_ALPHA, inner=0.2, outer=1.25)
    return surface


def _font(size):
    try:
        return pygame.font.Font(FONT_PATH, size)
    except (pygame.error, FileNotFoundError, OSError):
        return pygame.font.Font(None, int(size * 1.15))


def _shared_light():
    """The glow sprites and frames, rebuilt when the display changes (they carry its format)."""
    display = pygame.display.get_surface()
    size = display.get_size() if display is not None else None
    if _light.get('display', False) != size:
        _light['display'] = size
        _light['glow'] = GlowSprites()
        _light['frames'] = GlowFrame(reach=GLOW_REACH)
    return _light['glow'], _light['frames']


def _ease_out(p):
    return 1.0 - (1.0 - p) ** 3


# ========================================
# TURN ANNOUNCEMENT EFFECT CLASS
# ========================================

class TurnAnnouncementEffect:
    """
    The turn banner: darkening vignette, the framed name growing in, gold light
    round it and motes of light, all fading out together.
    """

    def __init__(self, screen_width, screen_height, player_number=None,
                 player_name=None, custom_text=None, on_complete=None):
        """
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

        self.explosion_duration = EXPLOSION_DURATION
        self.pause_duration = PAUSE_DURATION
        self.recede_duration = RECEDE_DURATION
        self.total_duration = TOTAL_DURATION

        self.scale = screen_height / REFERENCE_HEIGHT
        self.center_x = screen_width / 2
        self.center_y = screen_height / 2

        # Text - priority: custom_text > player_name > player_number
        if custom_text:
            self.text = custom_text
        elif player_name:
            self.text = f"{player_name}'s Turn"
        else:
            self.text = f"Player {player_number}'s Turn"

        size = max(16, int(TEXT_SIZE * self.scale))
        font = _font(size)
        # Too wide for the screen: the name on one line, "'s Turn" below it
        lines = [self.text]
        if custom_text is None and player_name and font.size(self.text)[0] > screen_width * 0.7:
            lines = [player_name, "'s Turn"]
        # Still too wide (a very long name): a smaller font until the framed banner fits
        room = screen_width * MAX_BANNER_WIDTH - 2 * (FRAME_BORDER[0] + PADDING[0]) * self.scale
        widest = max(font.size(line)[0] for line in lines)
        while size > 16 and widest > room:
            size = max(16, min(size - 2, int(size * room / widest)))
            font = _font(size)
            widest = max(font.size(line)[0] for line in lines)
        self.banner = self._bake_banner(font, lines)
        self._sizes = {}     # scale step -> the banner at that size

        self.glow, frames = _shared_light()
        # The glow round the frame, baked now: the first frame at full size shouldn't pay for it
        self._glow_size = self.banner.get_size()
        self._glow_frames = frames
        frames.frame(self._glow_size, GLOW_COLOUR, GlowFrame.LEVELS, 'rect', 6)
        self._glow_colour = light_fx.light_colour(MOTES['colour'], MOTES['white_mix'])

        self._motes = RisingMotes(MOTES, self.text, self.scale)
        self._from_banner = int(MOTES['count'] * MOTES['banner_share'])

    def _bake_banner(self, font, lines):
        """The framed text at full size (once per announcement)."""
        from rendering.sidebar_widgets import FRAMES, render_nine_slice
        from utils.surface_utils import load_cached_image

        s = self.scale
        shadow_offset = max(1, int(TEXT_SHADOW_OFFSET * s))
        rendered = [(font.render(line, True, TEXT_SHADOW), font.render(line, True, TEXT_COLOUR))
                    for line in lines]
        spacing = int(LINE_SPACING * s)
        text_w = max(text.get_width() for _, text in rendered)
        text_h = sum(text.get_height() for _, text in rendered) + spacing * (len(rendered) - 1)
        bx, by = max(8, int(FRAME_BORDER[0] * s)), max(6, int(FRAME_BORDER[1] * s))
        width = text_w + 2 * (bx + int(PADDING[0] * s))
        height = text_h + 2 * (by + int(PADDING[1] * s))
        path, insets = FRAMES['bronze']
        banner = render_nine_slice(load_cached_image(path), insets, (width, height), (bx, by, bx, by),
                                   fill=(FILL_TOP, FILL_BOTTOM))
        y = (height - text_h) // 2
        for shadow, text in rendered:
            x = (width - text.get_width()) // 2
            banner.blit(shadow, (x + shadow_offset, y + shadow_offset))
            banner.blit(text, (x, y))
            y += text.get_height() + spacing
        return banner

    def update(self, delta_time):
        """
        Update the effect animation.

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        if self.is_complete:
            return

        self.elapsed += delta_time

        if self.elapsed >= self.total_duration:
            self.is_complete = True
            if self.on_complete:
                self.on_complete()

    def _phase(self):
        """(banner scale, banner opacity, darkness) at this moment."""
        t = self.elapsed
        if t < self.explosion_duration:
            p = t / self.explosion_duration
            return GROW_FROM + (1.0 - GROW_FROM) * _ease_out(p), min(1.0, p * 2.0), p
        if t < self.explosion_duration + self.pause_duration:
            return 1.0, 1.0, 1.0
        p = min(1.0, (t - self.explosion_duration - self.pause_duration) / self.recede_duration)
        fade = 1.0 - p * p * (3.0 - 2.0 * p)
        return 1.0, fade, 1.0 - p

    def render(self, screen):
        """
        Render the turn announcement effect: the vignette, the gold glow and the
        motes of light, then the banner.

        Args:
            screen: Pygame surface to render to
        """
        if self.is_complete:
            return
        scale, opacity, darkness = self._phase()

        # 1. The darkening vignette. A partial surface alpha only while it fades
        # (255 keeps the faster blit path during the hold)
        vignette = _vignette((self.screen_width, self.screen_height))
        vignette.set_alpha(int(255 * darkness) if darkness < 1.0 else 255)
        screen.blit(vignette, (0, 0))

        banner = self._banner_at(scale)
        rect = banner.get_rect(center=(int(self.center_x), int(self.center_y)))

        # 2. Gold light round the frame, once the banner is full size
        if scale >= 1.0:
            level = int(GlowFrame.LEVELS * GLOW_INTENSITY * opacity + 0.5)
            if level > 0:
                glow, pad = self._glow_frames.frame(self._glow_size, GLOW_COLOUR, level, 'rect', 6)
                screen.blit(glow, (rect.x - pad, rect.y - pad), special_flags=pygame.BLEND_RGB_ADD)

        # 3. Motes of light
        self._draw_motes(screen, rect, darkness)

        # 4. The banner
        banner.set_alpha(int(255 * opacity))
        screen.blit(banner, rect)

    def _banner_at(self, scale):
        """The banner at this scale, in SCALE_STEPS cached sizes (no per-frame smoothscale)."""
        step = min(SCALE_STEPS, int(round((scale - GROW_FROM) / (1.0 - GROW_FROM) * SCALE_STEPS)))
        if step >= SCALE_STEPS:
            return self.banner
        surface = self._sizes.get(step)
        if surface is None:
            s = GROW_FROM + (1.0 - GROW_FROM) * step / SCALE_STEPS
            w, h = self.banner.get_size()
            surface = self._sizes[step] = pygame.transform.smoothscale(
                self.banner, (max(1, int(w * s)), max(1, int(h * s))))
        return surface

    def _draw_motes(self, screen, rect, strength):
        """
        Motes rising from just outside the banner's frame (the first
        MOTES['banner_share'] of them) and from the bottom band of the screen.
        """
        glow = self.glow
        glow.begin_frame()
        band_top = self.screen_height * (1.0 - MOTES['band'])
        band_h = self.screen_height - band_top
        outline = rect.inflate(2 * GLOW_REACH, 2 * GLOW_REACH)
        w, h = outline.width, outline.height
        perimeter = 2.0 * (w + h)

        def spawn(a, b, index):
            if index >= self._from_banner:
                return a * self.screen_width, band_top + b * band_h
            # A point on the glow's outline, walked round from the top-left corner
            d = a * perimeter
            if d < w:
                return outline.x + d, outline.y
            if d < w + h:
                return outline.right, outline.y + d - w
            if d < 2 * w + h:
                return outline.right - (d - w - h), outline.bottom
            return outline.x, outline.bottom - (d - 2 * w - h)

        self._motes.draw(screen, glow, self._glow_colour, self.elapsed, strength, spawn)

    def is_finished(self):
        """
        Check if the effect has completed.

        Returns:
            bool: True if effect is finished, False otherwise
        """
        return self.is_complete

    def cleanup(self):
        """Kept for callers that end an announcement early; nothing to release."""
        pass
