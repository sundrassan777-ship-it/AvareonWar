# -*- coding: utf-8 -*-
"""
Main menu window kit - the look shared by the main menu's windows (Options now;
Achievements and Profile next): a bronze-framed window over the dimmed menu, a bronze
title plate, gold rules, parchment text, the battle screen's ornate buttons, and the
windows' own controls (switch, arrows, two-way choice, slider, tab).

Agreed with the owner on the "Menu Glow-up" mockup (2026-10-30): bronze frame, the
battle screens' palette and buttons, a window about three quarters of the screen.

- Sizes are px at 1600x900 times `scale` = min(W / 1600, H / 900) - the game's ui_scale,
  which keeps growing past 900p (the old menu panels stopped at 900p sizes).
- Fonts: the Cinzel files loaded directly, as the campaign / browser screens do
  (config/font_manager maps every weight one step bolder - CODE_GUIDE "Browser Screens").
- Every sprite is baked once per screen size and state and kept between MainMenus, so a
  frame only blits; a window prewarms its sprites when the menu is made.
- WindowAnim: a window's open / close - an eased drop with a fade, the menu behind dimming
  with it. WindowStage draws it cheaply: the menu captured once (plain and dimmed), the
  window's fixed parts baked into that picture, only opaque surfaces faded (pygame's
  translucent full-screen blits cost 3-12 ms; see _blit_faded for the alpha-255 trap).
  Measured at 1600x900 (tools/menu_preview.py --bench): ~0.6 ms a settled frame, ~2.4 ms
  an opening one.
"""

from collections import OrderedDict

import pygame

from config.constants import CINZEL_BOLD, CINZEL_REGULAR, CINZEL_SEMIBOLD
from rendering.bottom_panel_kit import LIGHT_TEXT, SHADOW
from rendering.sidebar_widgets import (GOLD, GOLD_DARK, GOLD_LIGHT, PARCHMENT, PARCHMENT_DIM,
                                       _apply_state)
from ui import battle_screen_kit as kit
from ui.effects.light_fx import vignette_surface
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------- palette
PARCHMENT_FAINT = (125, 113, 95)      # Off / locked values
WARN = (240, 180, 80)                 # "2 unsaved changes"
WINDOW_FILL = ((44, 34, 24), (18, 13, 9))         # The window's dark board, top -> bottom
BANNER_FILL = ((62, 51, 36), (31, 25, 17))        # As the battle screen's banner
TAB_FILL = ((62, 51, 36), (31, 25, 17))
TAB_FILL_ON = ((95, 72, 41), (46, 34, 21))
WELL_FILL = ((15, 10, 6), (29, 20, 13))           # Recessed boxes (arrows, switch, slider)
WELL_EDGE = (106, 74, 34)
SWITCH_ON_FILL = ((110, 66, 16), (196, 138, 46))
SWITCH_ON_EDGE = (224, 184, 96)
CHOICE_ON_FILL = ((226, 180, 90), (154, 108, 38))
CHOICE_ON_TEXT = (30, 20, 8)
SLIDER_FILL = ((125, 79, 23), (240, 200, 96))     # Left -> right
ROW_RULE = (138, 98, 50, 72)
GLOW = (255, 196, 70)

# ---------------------------------------------------------------- geometry, px at 1600x900
WINDOW_SIZE = (1220, 806)
WINDOW_DROP = 7          # The window sits this much below the screen's middle
WINDOW_BORDER = 16       # Bronze frame thickness
WINDOW_MARGIN = 20       # Least room left round the window on narrow screens
BANNER_HEIGHT = 64
BANNER_PAD = 56          # Text to the plate's ends (the diamonds sit inside)
BANNER_BORDER = 12

# Fonts: role -> (weight, px at 1600x900)
FONT_ROLES = {
    'banner': ('semibold', 31),
    'tab': ('semibold', 18),
    'name': ('semibold', 21),
    'name_sub': ('semibold', 18),
    'hint': ('regular', 14),
    'value': ('semibold', 18),
    'value_small': ('regular', 15),
    'state': ('semibold', 15),
    'choice': ('semibold', 15),
    'button': ('semibold', 17),
    'note': ('regular', 15),
}
_FONT_FILES = {'regular': CINZEL_REGULAR, 'semibold': CINZEL_SEMIBOLD, 'bold': CINZEL_BOLD}

# ---------------------------------------------------------------- animation
OPEN_SECONDS = 0.30
CLOSE_SECONDS = 0.22
DROP_PX = 40             # The window drops in from this far above (px at 1600x900)
MAX_STEP = 1.0 / 60.0    # Seconds of animation one frame may advance at most
FADE_END = 0.85          # The window / the dimming are fully faded in at this drop level

SUPERSAMPLE = 4          # Round shapes are drawn this much larger, then smoothscaled down
TEXT_CACHE_MAX = 800


def ease_out(t):
    """Cubic ease-out on [0, 1] - fast start, gentle landing."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


class WindowAnim:
    """
    A window's open / close: `progress` runs 0 -> 1 over OPEN_SECONDS when opening and
    back over CLOSE_SECONDS when closing; reversing mid-way continues from where it is.
    `level` (eased) drives the drop, the fade and the backdrop's dimming.
    """

    def __init__(self):
        self.progress = 0.0
        self.opening = False

    def open(self):
        self.opening = True

    def close(self):
        self.opening = False

    def finish(self):
        """Jump to the end of the current direction (tests, previews)."""
        self.progress = 1.0 if self.opening else 0.0

    def update(self, dt):
        # A slow frame (the first one captures the menu) must not make the drop jump ahead:
        # the animation takes at most a 60 fps step per frame
        dt = min(dt, MAX_STEP)
        if self.opening:
            self.progress = min(1.0, self.progress + dt / OPEN_SECONDS)
        else:
            self.progress = max(0.0, self.progress - dt / CLOSE_SECONDS)

    @property
    def level(self):
        return ease_out(self.progress)

    @property
    def visible(self):
        return self.progress > 0.0

    @property
    def settled_open(self):
        return self.opening and self.progress >= 1.0

    @property
    def interactive(self):
        """Hover and clicks count once the window has landed (WindowStage draws it from a
        fixed picture while it moves)."""
        return self.settled_open


class WindowStage:
    """
    Draws a menu window over the menu cheaply. Large translucent blits are slow in pygame
    (a full-screen dimming at partial alpha ~12 ms; an opaque surface faded with
    set_alpha ~0.6 ms), so:

    - The menu is captured once when the window starts to show, plain and dimmed (its
      buttons cannot change under a window). Opening / closing cross-fades the two and
      fades + drops one opaque picture of the window (its title plate apart).
    - Once landed, the window's unchanging parts (window.draw_static: board, title, row
      names...) are baked into the dimmed menu - again whenever window.static_key()
      changes - so a frame is one opaque blit plus window.draw_dynamic (its controls).

    The window provides: anim (WindowAnim), title, rect() (screen rect), draw(surface, ox,
    oy) (everything), draw_static / draw_dynamic and static_key().
    """

    def __init__(self, kit):
        self.kit = kit
        self.reset()

    def reset(self):
        """Forget the captured menu (the window closed: the next one captures it afresh)."""
        self.plain = self.dim = None
        self.settled = self.settled_key = None
        self.picture = self.picture_for = None
        self.banner = None

    def draw(self, screen, window, render_menu):
        if self.plain is None:
            render_menu()
            self.plain = screen.copy()
            screen.blit(self.kit.backdrop(), (0, 0))
            self.dim = screen.copy()
        rect = window.rect()
        if window.anim.settled_open:
            key = window.static_key()
            if self.settled is None or key != self.settled_key:
                self.settled = self.dim.copy()
                window.draw_static(self.settled, rect.x, rect.y)
                self.settled_key = key
            screen.blit(self.settled, (0, 0))
            window.draw_dynamic(screen, rect.x, rect.y)
            self.picture_for = None    # The window may change: picture it again when it leaves
            return
        level = window.anim.level
        # The fades end a little before the drop does (FADE_END): a translucent blit costs
        # ~2-3 ms a big surface, an opaque one ~0.2 ms, so the drop's last half is cheap
        fade = min(1.0, level / FADE_END)
        screen.blit(self.dim, (0, 0))
        _blit_faded(screen, self.plain, (0, 0), int(round(255 * (1.0 - fade))))
        if self.picture is None or self.picture_for != window.anim.opening:
            # The window as it is now, on the dimmed menu under it (opaque: a cheap fade)
            self.picture = self.dim.subsurface(rect).copy()
            window.draw(self.picture, 0, 0)
            self.picture_for = window.anim.opening
            self.banner = self.kit.banner(window.title).copy()   # Own copy: set_alpha below
        alpha = int(round(255 * fade))
        drop = int(round(self.kit.px(DROP_PX) * (1.0 - level)))
        _blit_faded(screen, self.picture, (rect.x, rect.y - drop), alpha)
        _blit_faded(screen, self.banner, (rect.x + (rect.w - self.banner.get_width()) // 2,
                                          rect.y - self.kit.banner_overhang() - drop), alpha)


def _blit_faded(screen, surface, pos, alpha):
    """
    `surface` at `alpha`: skipped at 0, and at 255 blitted with no surface alpha at all -
    pygame takes a slow path for a surface alpha of exactly 255 (~12 ms full-screen vs ~1 ms
    at any other value), which made the last frames of a window's drop stutter.
    """
    if alpha <= 0:
        return
    surface.set_alpha(None if alpha >= 255 else alpha)
    screen.blit(surface, pos)


# Each screen size's baked text and sprites, kept between MainMenus (one is made every time
# the game returns to the menu), so the windows' sprites are built once per size. Fonts are
# NOT shared: a Font dies with pygame.quit() (using one afterwards crashes the process), a
# baked surface does not.
_SHARED = {}


class MenuKit:
    """Cached drawing pieces for the main menu's windows, for one screen size."""

    def __init__(self, screen_size):
        self.screen_size = (int(screen_size[0]), int(screen_size[1]))
        width, height = self.screen_size
        self.scale = min(width / 1600.0, height / 900.0)
        shared = _SHARED.setdefault(self.screen_size, {
            'text': OrderedDict(), 'sprites': {}, 'backdrop': None})
        self._shared = shared
        self._fonts = {}                 # This MainMenu's own (see _SHARED)
        self._text = shared['text']
        self._sprites = shared['sprites']

    # ------------------------------------------------------------ units, fonts, text

    def px(self, value):
        """A length in px at 1600x900, at this screen's scale (at least 1)."""
        return max(1, int(round(value * self.scale)))

    def font(self, role):
        weight, size = FONT_ROLES[role]
        return self.font_px(weight, size)

    def font_px(self, weight, size):
        px = max(8, int(round(size * self.scale)))
        key = (weight, px)
        font = self._fonts.get(key)
        if font is None:
            try:
                font = pygame.font.Font(_FONT_FILES[weight], px)
            except (FileNotFoundError, OSError, pygame.error):
                logger.warning(f"Cinzel {weight} missing - using Arial")
                font = pygame.font.SysFont('arial', px, bold=(weight != 'regular'))
            self._fonts[key] = font
        return font

    def text(self, text, role, color, shadow=True, spacing=0.0):
        """
        `text` in a font role, with a drop shadow (1 px, 2 px from 24 px up) and optional
        letter spacing (`spacing` em, for the title plate and tabs). Cached.
        """
        key = (text, role, color, shadow, spacing)
        surf = self._text.get(key)
        if surf is not None:
            self._text.move_to_end(key)
            return surf
        font = self.font(role)
        surf = _render_text(font, text, color, SHADOW if shadow else None,
                            2 if font.get_height() >= 24 else 1, spacing)
        self._text[key] = surf
        if len(self._text) > TEXT_CACHE_MAX:
            self._text.popitem(last=False)
        return surf

    def fit(self, text, role, max_width):
        """`text`, cut with an ellipsis to `max_width` in a role's font."""
        font = self.font(role)
        if font.size(text)[0] <= max_width:
            return text
        while text and font.size(text + "...")[0] > max_width:
            text = text[:-1]
        return text.rstrip() + "..."

    def wrap(self, text, role, max_width, max_lines=2):
        """Greedy word wrap in a role's font, at most `max_lines` (the last one cut to fit)."""
        font = self.font(role)
        lines, current = [], ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if font.size(trial)[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines - 1] + [self.fit(" ".join(lines[max_lines - 1:]), role, max_width)]
        return lines

    def _sprite(self, key, build):
        surf = self._sprites.get(key)
        if surf is None:
            surf = self._sprites[key] = build()
        return surf

    # ------------------------------------------------------------ window chrome

    def window_rect(self):
        """The window's rect on screen (its title plate rises banner_overhang() above it)."""
        width, height = self.screen_size
        w = min(self.px(WINDOW_SIZE[0]), width - 2 * self.px(WINDOW_MARGIN))
        h = min(self.px(WINDOW_SIZE[1]), height - self.banner_overhang() - self.px(WINDOW_MARGIN) // 2)
        top = max(self.banner_overhang(), (height - h) // 2 + self.px(WINDOW_DROP))
        top = min(top, height - h)
        return pygame.Rect((width - w) // 2, top, w, h)

    def border(self):
        return self.px(WINDOW_BORDER)

    def banner_overhang(self):
        """How far the title plate rises above the window's top edge."""
        return self.px(BANNER_HEIGHT) // 2

    def window(self, size):
        """The bronze-framed window board."""
        b = self.border()
        return kit.bronze_plate(size, (b, b), WINDOW_FILL)

    def banner(self, title):
        """The title plate: spaced gold capitals on the battle screen's bronze plate."""
        def build():
            text = self.text(title.upper(), 'banner', GOLD_LIGHT, spacing=0.16)
            h = self.px(BANNER_HEIGHT)
            w = text.get_width() + 2 * self.px(BANNER_PAD)
            b = self.px(BANNER_BORDER)
            plate = kit.bronze_plate((w, h), (b, b), BANNER_FILL).copy()
            plate.blit(text, text.get_rect(center=(w // 2, h // 2)))
            d = max(3, self.px(6))
            for cx in (self.px(26), w - self.px(26)):
                _diamond(plate, (cx, h // 2), d, GOLD)
            return plate
        return self._sprite(('banner', title), build)

    def rule(self, width):
        """The gold rule with a centre diamond (as the battle report's)."""
        return kit.separator(width)

    def backdrop(self):
        """The dimming over the menu while a window is open (baked once)."""
        if self._shared['backdrop'] is None:
            self._shared['backdrop'] = vignette_surface(self.screen_size, (8, 5, 3), 128, 232,
                                                        inner=0.25, outer=1.3)
        return self._shared['backdrop']

    # ------------------------------------------------------------ buttons

    def button_size(self, width):
        """An ornate button `width` px wide (at 1600x900); its height follows the art."""
        w = self.px(width)
        return w, kit.button_height(self.px(230))

    def draw_button(self, surface, rect, label, state, primary=False):
        """The battle screen's ornate button; the primary action's label is gold."""
        kit.draw_button(surface, rect, label, self.font('button'), state=state,
                        color=GOLD_LIGHT if primary else LIGHT_TEXT)

    # ------------------------------------------------------------ tabs

    def tab(self, size, label, on, state):
        """A tab: a bronze plate, lit with a glow when it is the open tab."""
        def build():
            w, h = size
            pad = self.px(10)
            surf = pygame.Surface((w + 2 * pad, h + 2 * pad), pygame.SRCALPHA)
            if on:
                surf.blit(_soft_glow((w, h), pad, GLOW, 70), (0, 0),
                          special_flags=pygame.BLEND_RGBA_MAX)
            b = self.px(10)
            plate = kit.bronze_plate((w, h), (b, b), TAB_FILL_ON if on else TAB_FILL).copy()
            _apply_state(plate, state)
            surf.blit(plate, (pad, pad), special_flags=0 if on else pygame.BLEND_RGBA_MAX)
            color = GOLD_LIGHT if on else (PARCHMENT if state != 'normal' else PARCHMENT_DIM)
            text = self.text(label.upper(), 'tab', color, spacing=0.1)
            surf.blit(text, text.get_rect(center=(pad + w // 2, pad + h // 2)))
            return surf
        return self._sprite(('tab', size, label, on, state), build)

    # ------------------------------------------------------------ rows

    def row_hover(self, size):
        """A hovered row: a gold wash fading to the right, and a gold bar at its left edge."""
        def build():
            w, h = size
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            span = max(1, int(w * 0.75))
            for x in range(span):
                alpha = int(28 * (1.0 - x / float(span)))
                pygame.draw.line(surf, (GOLD[0], GOLD[1], GOLD[2], alpha), (x, 0), (x, h - 1))
            pygame.draw.rect(surf, GOLD, (0, 0, max(2, self.px(3)), h))
            return surf
        return self._sprite(('row_hover', size), build)

    def row_rule(self, width):
        def build():
            surf = pygame.Surface((width, 1), pygame.SRCALPHA)
            surf.fill(ROW_RULE)
            return surf
        return self._sprite(('row_rule', width), build)

    def branch(self, size):
        """The little gold elbow before a dependent row's name (Scroll From, Tooltip Delay)."""
        def build():
            w, h = size
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.line(surf, GOLD_DARK, (0, 0), (0, h - 1))
            pygame.draw.line(surf, GOLD_DARK, (0, h - 1), (w - 1, h - 1))
            return surf
        return self._sprite(('branch', size), build)

    # ------------------------------------------------------------ controls

    def switch(self, size, on, state):
        """An on / off switch: a recessed pill, lit gold with its knob right when on."""
        def build():
            return _bake_switch(size, on, self.px(8), state)
        return self._sprite(('switch', size, on, state), build)

    def switch_pad(self):
        """The glow margin round a switch sprite."""
        return self.px(8)

    def well(self, size, radius):
        """A recessed dark box (the arrows' value box, the two-way choice's track)."""
        def build():
            return _bake_well(size, radius)
        return self._sprite(('well', size, radius), build)

    def arrow(self, size, direction, state):
        """A chevron button inside the arrows' box; brighter with a soft wash on hover."""
        def build():
            w, h = size
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            lit = state in ('hover', 'flash')
            if lit:
                surf.fill((GOLD[0], GOLD[1], GOLD[2], 30 if state == 'hover' else 60))
            _chevron(surf, (w // 2, h // 2), max(4, int(h * 0.2)), direction,
                     GOLD_LIGHT if lit else GOLD, max(2, self.px(2)))
            if state == 'locked':
                _apply_state(surf, 'locked')
            return surf
        return self._sprite(('arrow', size, direction, state), build)

    def choice(self, size, on, state):
        """One side of a two-way choice: a gold pill when chosen, a faint wash on hover."""
        def build():
            w, h = size
            if on:
                surf = _bake_pill((w, h), CHOICE_ON_FILL, None, glow=None)
                _apply_state(surf, state)
                return surf
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            if state in ('hover', 'flash'):
                alpha = 26 if state == 'hover' else 52
                pill = _bake_pill((w, h), ((GOLD[0], GOLD[1], GOLD[2], alpha),) * 2, None, glow=None)
                surf.blit(pill, (0, 0))
            return surf
        return self._sprite(('choice', size, on, state), build)

    def slider_track(self, size):
        def build():
            return _bake_well(size, size[1] // 2)
        return self._sprite(('slider_track', size), build)

    def slider_fill(self, size):
        """The track's gold fill at full length (blitted cut to the value)."""
        def build():
            w, h = size
            surf = _bake_pill(size, None, None, glow=None, horizontal=SLIDER_FILL)
            return surf
        return self._sprite(('slider_fill', size), build)

    def knob(self, diameter, state):
        """The gold knob of a switch or slider, with a soft glow when hovered / held."""
        def build():
            return _bake_knob(diameter, self.px(6), state)
        return self._sprite(('knob', diameter, state), build)

    def knob_pad(self):
        return self.px(6)

    def dot(self, diameter, color):
        """A small glowing dot (the unsaved-changes mark)."""
        def build():
            pad = diameter
            surf = _soft_glow((diameter, diameter), pad, color, 110, shape='round')
            surf.blit(_disc(diameter, color), (pad, pad))
            return surf
        return self._sprite(('dot', diameter, color), build)


# ==================================================================== baking helpers

def _render_text(font, text, color, shadow_color, shadow_offset, spacing):
    """Text (optionally letter-spaced) over its drop shadow on one transparent surface."""
    if spacing <= 0:
        label = font.render(text, True, color)
        if shadow_color is None:
            return label
        shadow = font.render(text, True, shadow_color)
        surf = pygame.Surface((label.get_width() + shadow_offset, label.get_height() + shadow_offset),
                              pygame.SRCALPHA)
        surf.blit(shadow, (shadow_offset, shadow_offset))
        surf.blit(label, (0, 0))
        return surf
    gap = int(round(font.get_height() * spacing * 0.75))
    glyphs = [font.render(ch, True, color) for ch in text]
    widths = [font.size(ch)[0] for ch in text]
    width = sum(widths) + gap * max(0, len(text) - 1)
    off = shadow_offset if shadow_color is not None else 0
    surf = pygame.Surface((max(1, width + off), font.get_height() + off), pygame.SRCALPHA)
    if shadow_color is not None:
        x = 0
        for ch, w in zip(text, widths):
            surf.blit(font.render(ch, True, shadow_color), (x + off, off))
            x += w + gap
    x = 0
    for glyph, w in zip(glyphs, widths):
        surf.blit(glyph, (x, 0))
        x += w + gap
    return surf


def _diamond(surf, centre, r, color):
    cx, cy = centre
    pygame.draw.polygon(surf, color, [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)])


def _chevron(surf, centre, r, direction, color, width):
    """A '<' or '>' chevron, drawn large and scaled down for smooth edges."""
    k = SUPERSAMPLE
    w, h = surf.get_size()
    big = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    big.fill((color[0], color[1], color[2], 0))   # No dark fringe when scaled down
    cx, cy = centre[0] * k, centre[1] * k
    rr = r * k
    dx = rr // 2 if direction > 0 else -(rr // 2)
    points = [(cx - dx, cy - rr), (cx + dx, cy), (cx - dx, cy + rr)]
    pygame.draw.lines(big, color, False, points, width * k)
    for p in points:
        pygame.draw.circle(big, color, p, width * k // 2)
    surf.blit(pygame.transform.smoothscale(big, (w, h)), (0, 0))


def _gradient(size, fill, horizontal=False):
    """A surface of `size` filled with a colour or a (start, end) gradient."""
    w, h = size
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    if fill is None:
        return surf
    if isinstance(fill[0], tuple):
        start, end = fill
        steps = w if horizontal else h
        for i in range(steps):
            t = i / float(max(1, steps - 1))
            color = tuple(int(start[c] + (end[c] - start[c]) * t) for c in range(len(start)))
            if horizontal:
                pygame.draw.line(surf, color, (i, 0), (i, h - 1))
            else:
                pygame.draw.line(surf, color, (0, i), (w - 1, i))
    else:
        surf.fill(fill)
    return surf


def _rounded_mask(size, radius):
    """A white rounded rectangle on transparent, drawn large and scaled down (smooth edges)."""
    k = SUPERSAMPLE
    w, h = size
    big = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    big.fill((255, 255, 255, 0))                  # White throughout: only alpha shapes it
    pygame.draw.rect(big, (255, 255, 255, 255), big.get_rect(), border_radius=radius * k)
    return pygame.transform.smoothscale(big, (w, h))


def _bake_pill(size, fill, edge, glow=None, horizontal=None, radius=None):
    """A rounded shape filled with `fill` (or a `horizontal` gradient) and an optional edge."""
    w, h = size
    radius = h // 2 if radius is None else radius
    body = _gradient(size, horizontal if horizontal is not None else fill, horizontal is not None)
    body.blit(_rounded_mask(size, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if edge is not None:
        k = SUPERSAMPLE
        big = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
        big.fill((edge[0], edge[1], edge[2], 0))
        pygame.draw.rect(big, edge, big.get_rect(), k, border_radius=radius * k)
        body.blit(pygame.transform.smoothscale(big, (w, h)), (0, 0))
    return body


def _bake_well(size, radius):
    """A recessed box: dark gradient, a shadow along its top, a bronze edge."""
    w, h = size
    body = _gradient(size, WELL_FILL)
    # pygame.draw does not blend, so the shade is its own surface, blitted (blended) on
    shade = pygame.Surface((w, max(1, h // 4)), pygame.SRCALPHA)
    for y in range(shade.get_height()):
        alpha = int(120 * (1.0 - y / float(shade.get_height())))
        pygame.draw.line(shade, (0, 0, 0, alpha), (0, y), (w - 1, y))
    body.blit(shade, (0, 0))
    body.blit(_rounded_mask(size, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    body.blit(_bake_pill(size, None, WELL_EDGE, radius=radius), (0, 0))
    return body


def _soft_glow(size, pad, color, alpha, shape='rect'):
    """
    A soft halo `pad` px round a `size` shape - 'rect' (a plate), 'pill' or 'round' -
    fading to nothing exactly at the sprite's edge (a blur wider than `pad` would be cut
    off there, showing a square). Drawn as rings from the faint outside in, then softened.
    The surface is the glow's colour throughout with only the alpha varying, so it leaves
    no dark fringe. Put it on an empty sprite with BLEND_RGBA_MAX (a plain blit onto a
    clear surface would darken it).
    """
    w, h = size
    pad = max(2, int(pad))
    full = (w + 2 * pad, h + 2 * pad)
    surf = pygame.Surface(full, pygame.SRCALPHA)
    surf.fill((color[0], color[1], color[2], 0))
    for i in range(pad, -1, -1):
        t = i / float(pad)
        a = int(alpha * (1.0 - t) ** 2)
        rect = pygame.Rect(pad - i, pad - i, w + 2 * i, h + 2 * i)
        if shape == 'round':
            pygame.draw.ellipse(surf, (color[0], color[1], color[2], a), rect)
        else:
            radius = rect.h // 2 if shape == 'pill' else max(1, h // 6) + i
            pygame.draw.rect(surf, (color[0], color[1], color[2], a), rect, border_radius=radius)
    # Soften the rings' steps
    half = pygame.transform.smoothscale(surf, (max(2, full[0] // 2), max(2, full[1] // 2)))
    return pygame.transform.smoothscale(half, full)


def _disc(diameter, color):
    """A smooth-edged filled circle (drawn large, scaled down)."""
    k = SUPERSAMPLE
    big = pygame.Surface((diameter * k, diameter * k), pygame.SRCALPHA)
    big.fill((color[0], color[1], color[2], 0))
    pygame.draw.circle(big, color, (diameter * k // 2, diameter * k // 2), diameter * k // 2)
    return pygame.transform.smoothscale(big, (diameter, diameter))


def _bake_knob(diameter, pad, state):
    """A gold knob: a dark ring round a gold disc lit from the top left."""
    k = SUPERSAMPLE
    size = diameter + 2 * pad
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    if state in ('hover', 'flash') and pad > 0:
        surf.blit(_soft_glow((diameter, diameter), pad, GLOW, 120 if state == 'hover' else 170,
                             shape='round'), (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
    big = pygame.Surface((diameter * k, diameter * k), pygame.SRCALPHA)
    big.fill((42, 28, 16, 0))
    r = diameter * k // 2
    c = (r, r)
    pygame.draw.circle(big, (42, 28, 16), c, r)
    inner = r - max(k, diameter * k // 11)
    # Disc shading: dark bronze at the rim to pale gold at the top-left highlight
    rim, mid, light = (122, 85, 36), (212, 170, 80), (255, 241, 201)
    steps = 24
    for i in range(steps):
        t = i / float(steps - 1)
        rad = int(inner * (1.0 - 0.75 * t))
        color = _mix(rim, mid, min(1.0, t * 2)) if t < 0.5 else _mix(mid, light, (t - 0.5) * 2)
        off = int(inner * 0.28 * t)
        pygame.draw.circle(big, color, (c[0] - off, c[1] - off), rad)
    disc = pygame.transform.smoothscale(big, (diameter, diameter))
    if state == 'hover':
        disc.fill((24, 24, 24), special_flags=pygame.BLEND_RGB_ADD)
    elif state == 'flash':
        disc.fill((48, 48, 48), special_flags=pygame.BLEND_RGB_ADD)
    elif state == 'locked':
        _apply_state(disc, 'locked')
    surf.blit(disc, (pad, pad))
    return surf


def _bake_switch(size, on, pad, state):
    """The switch's pill (with a gold glow when on) and its knob, left or right."""
    w, h = size
    surf = pygame.Surface((w + 2 * pad, h + 2 * pad), pygame.SRCALPHA)
    if on:
        if state != 'locked':
            surf.blit(_soft_glow((w, h), pad, GLOW, 90, shape='pill'), (0, 0),
                      special_flags=pygame.BLEND_RGBA_MAX)
        pill = _bake_pill(size, SWITCH_ON_FILL, SWITCH_ON_EDGE)
    else:
        pill = _bake_well(size, h // 2)
    _apply_state(pill, state)
    glowing = on and state != 'locked'
    # Over the glow: blend; on an empty sprite: copy exactly (a blend would darken its edge)
    surf.blit(pill, (pad, pad), special_flags=0 if glowing else pygame.BLEND_RGBA_MAX)
    inset = max(2, h // 10)
    d = h - 2 * inset
    knob = _bake_knob(d, 0, 'locked' if state == 'locked' else 'normal')
    kx = pad + (w - inset - d if on else inset)
    surf.blit(knob, (kx, pad + inset))
    return surf


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
