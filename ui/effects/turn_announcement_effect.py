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
    0.0   - 0.375 s  the screen darkens, the banner grows in with its gold glow
    0.375 - 0.75 s   hold
    0.75  - 1.5 s    the banner, the glow and the darkness fade
    1.5 s            complete: on_complete() is called once

Integration:
    - main.py creates one when game_state.turn_announcement_active is set (its
      on_complete is game_state._complete_turn_announcement) and one per
      simultaneous round ("Turn N"); input is blocked until it completes
    - cleanup() is kept for its callers (campaign missions cut an AI's short)

Cost (1600x900): ~1 ms a frame while held, ~3 ms while fading, ~4 ms while growing.
    - The darkening is a multiply by a baked vignette (0.75 ms). While it fades,
      the darkened copy of the frame is blended over it with a whole-surface
      alpha (~2.3 ms); a per-pixel-alpha vignette with set_alpha() was 4.2 ms.
    - The gold glow is tinted every frame on the four strips round the frame
      (~0.1 ms), so it fades smoothly; cached brightness levels stepped visibly
      and cost ~1.7 ms and ~1 MB each.
    - The banner is smoothscaled each frame while it grows (~0.7 ms, ~0.3 s), and
      its glow scaled with it (~0.7 ms); cached size steps jumped ~36 px at a time.
    - Baked once: the vignette per screen size and the grey glow per banner size
      (kept between turns), the banner per announcement.
"""

import pygame

from ui.effects import light_fx
from ui.effects.light_fx import GlowSprites, GlowFrame, RisingMotes
from ui.effects.order_fx_style import GUIDE_GOLD

MULT = pygame.BLEND_RGB_MULT
ADD = pygame.BLEND_RGB_ADD

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
WRAP_WIDTH = 0.7                      # share of the screen width: a longer "Name's Turn" takes two lines
MAX_BANNER_WIDTH = 0.9                # share of the screen width (a long name gets a smaller font)
GROW_FROM = 0.6                       # the banner's scale as it starts growing in
FULL_SIZE_PX = 1.5                    # the growing banner snaps to full size this close to it

# The gold light round the frame (order_fx_style GUIDE gold, the tutorial glow's)
GLOW_COLOUR = GUIDE_GOLD
GLOW_REACH = 16                       # px outside the frame
GLOW_CORNER = 6                       # the glow's corner rounding, px
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

# Rebuilt when the display or the screen size changes (they carry its format):
# 'key', 'glow' (GlowSprites), 'frames' (GlowFrame, its grey glows),
# 'darken' (the multiply vignette and a scratch copy of the frame).
# (Fonts are not kept: a Font used after pygame.font is shut down and started again
# crashes the process - the multiplayer test harness does that between games)
_shared = {}


def _shared_for(size):
    display = pygame.display.get_surface()
    key = (display.get_size() if display is not None else None, size)
    if _shared.get('key') != key:
        _shared.clear()
        _shared['key'] = key
        _shared['glow'] = GlowSprites()
        _shared['frames'] = GlowFrame(reach=GLOW_REACH)
    return _shared


def _darkening(screen, size):
    """(the vignette as a multiply surface, a scratch surface) at this size, in the screen's format."""
    shared = _shared_for(size)
    pair = shared.get('darken')
    if pair is None:
        vignette = light_fx.vignette_surface(size, (0, 0, 0), OVERLAY_CENTRE_ALPHA, OVERLAY_EDGE_ALPHA,
                                             inner=0.2, outer=1.25)
        darken = pygame.Surface(size, 0, screen)
        darken.fill((255, 255, 255))
        darken.blit(vignette, (0, 0))      # white under the black wash: 255 - its alpha
        pair = shared['darken'] = (darken, pygame.Surface(size, 0, screen))
    return pair


def _font(size):
    try:
        return pygame.font.Font(FONT_PATH, size)
    except (pygame.error, FileNotFoundError, OSError):
        return pygame.font.Font(None, int(size * 1.15))


def _two_lines(font, text):
    """
    The text in two lines, split between words where the wider line is narrowest
    ("Empire of North" / "Angarfen Forest's Turn"): "'s" stays with the name.
    """
    words = text.split()
    best = None
    for i in range(1, len(words)):
        lines = [' '.join(words[:i]), ' '.join(words[i:])]
        widest = max(font.size(line)[0] for line in lines)
        if best is None or widest < best[0]:
            best = (widest, lines)
    return best[1] if best else [text]


def _strips(grey, depth):
    """
    The four sides of a glow surface, depth px deep (inside them is the shape,
    black): their areas and a scratch surface each, for tinting every frame.
    """
    w, h = grey.get_size()
    depth = max(1, min(depth, w // 2, h // 2))
    areas = (pygame.Rect(0, 0, w, depth), pygame.Rect(0, h - depth, w, depth),
             pygame.Rect(0, depth, depth, h - 2 * depth), pygame.Rect(w - depth, depth, depth, h - 2 * depth))
    return [(area, pygame.Surface(area.size, 0, grey)) for area in areas if area.width > 0 and area.height > 0]


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
        # Too wide for the screen: two balanced lines
        lines = [self.text]
        if custom_text is None and player_name and font.size(self.text)[0] > screen_width * WRAP_WIDTH:
            lines = _two_lines(font, self.text)
        # Still too wide (a very long name): a smaller font until the framed banner fits
        room = screen_width * MAX_BANNER_WIDTH - 2 * (FRAME_BORDER[0] + PADDING[0]) * self.scale
        widest = max(font.size(line)[0] for line in lines)
        while size > 16 and widest > room:
            size = max(16, min(size - 2, int(size * room / widest)))
            font = _font(size)
            widest = max(font.size(line)[0] for line in lines)
        self.lines = lines
        self.banner = self._bake_banner(font, lines)

        shared = _shared_for((screen_width, screen_height))
        self.glow = shared['glow']
        # The darkening too (the first turn's), rather than in the first frame
        display = pygame.display.get_surface()
        if display is not None:
            _darkening(display, (screen_width, screen_height))
        # The grey glow round the frame, baked now (kept for later turns): the first
        # frame at full size shouldn't pay for it
        self._glow_grey, self._glow_pad = shared['frames'].grey(self.banner.get_size(), 'rect', GLOW_CORNER)
        self._glow_strips = _strips(self._glow_grey, self._glow_pad + GLOW_CORNER + 1)
        # The growing banner snaps to full size within FULL_SIZE_PX of it
        self._full_scale = 1.0 - FULL_SIZE_PX / float(self.banner.get_width())
        self._mote_colour = light_fx.light_colour(MOTES['colour'], MOTES['white_mix'])

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
        Render the turn announcement effect: the darkening, the gold glow and the
        motes of light, then the banner.

        Args:
            screen: Pygame surface to render to
        """
        if self.is_complete:
            return
        scale, opacity, darkness = self._phase()

        # 1. The darkening vignette
        self._darken(screen, darkness)

        banner = self._banner_at(scale)
        rect = banner.get_rect(center=(int(self.center_x), int(self.center_y)))

        # 2. Gold light round the frame, growing in and fading with it
        self._draw_glow(screen, rect, opacity, banner.get_width() / float(self.banner.get_width()))

        # 3. Motes of light
        self._draw_motes(screen, rect, darkness)

        # 4. The banner
        banner.set_alpha(int(255 * opacity))
        screen.blit(banner, rect)

    def _darken(self, screen, darkness):
        """
        The vignette at this darkness (0-1): a multiply when full; while it comes
        and goes, the darkened copy of the frame blended over it with a
        whole-surface alpha (the fast blend; a per-pixel-alpha surface with
        set_alpha() takes a path ~4x slower).
        """
        if darkness <= 0.0:
            return
        darken, scratch = _darkening(screen, (self.screen_width, self.screen_height))
        if darkness >= 1.0:
            screen.blit(darken, (0, 0), special_flags=MULT)
            return
        scratch.blit(screen, (0, 0))
        scratch.blit(darken, (0, 0), special_flags=MULT)
        scratch.set_alpha(int(255 * darkness))
        screen.blit(scratch, (0, 0))

    def _draw_glow(self, screen, rect, strength, scale=1.0):
        """
        The gold light round the banner (at rect, drawn at this scale of its full
        size) at strength 0-1, tinted this frame (no brightness steps): the grey
        glow times the colour, added. At full size only its four strips are tinted
        (~0.1 ms); while the banner grows, the whole glow is scaled with it (nearest,
        ~0.7 ms - the glow is soft, it looks the same as a smoothscale at half the cost).
        """
        colour = light_fx.scaled_colour(GLOW_COLOUR, GLOW_INTENSITY * strength)
        if not any(colour):
            return
        grey = self._glow_grey
        if scale < 1.0:
            w, h = grey.get_size()
            glow = pygame.transform.scale(grey, (max(1, int(w * scale + 0.5)), max(1, int(h * scale + 0.5))))
            tinted = pygame.Surface(glow.get_size(), 0, glow)
            tinted.fill(colour)
            tinted.blit(glow, (0, 0), special_flags=MULT)
            screen.blit(tinted, tinted.get_rect(center=rect.center), special_flags=ADD)
            return
        x0, y0 = rect.x - self._glow_pad, rect.y - self._glow_pad
        for area, scratch in self._glow_strips:
            scratch.fill(colour)
            scratch.blit(grey, (0, 0), area, special_flags=MULT)
            screen.blit(scratch, (x0 + area.x, y0 + area.y), special_flags=ADD)

    def _banner_at(self, scale):
        """The banner at this scale: smoothscaled each frame while it grows (~0.7 ms
        for ~0.3 s), the baked one once it is within FULL_SIZE_PX of full size."""
        if scale >= self._full_scale:
            return self.banner
        w, h = self.banner.get_size()
        return pygame.transform.smoothscale(self.banner, (max(1, int(w * scale + 0.5)),
                                                          max(1, int(h * scale + 0.5))))

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

        self._motes.draw(screen, glow, self._mote_colour, self.elapsed, strength, spawn)

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
