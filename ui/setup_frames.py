# -*- coding: utf-8 -*-
"""
Framed art for the game setup screens (Custom Game + multiplayer lobby).

- dropdown_box(): the Taxation / Victory / Turn Mode selectors, framed with the wooden
  ResourceSlot beams (nine-sliced so the beams keep their thickness however wide the
  box is — a plain stretch of the 1318x402 art squashes the top/bottom beams to a
  sliver) around the screens' existing fill colour.
- table_frame(): the carved bronze TableBorder around the multiplayer player rows,
  the same frame the Custom Game player table uses.
- wood_button(): the map top bar's buttons (Randomize Starting Positions, Show Borders),
  the same wood beams around a dark parchment fill - or a warm glow while a toggle is
  on (ui/map_top_bar.py).

All are cached per size / state; a frame costs one blit. Content inside a framed
box should start at content_inset() so text and arrows clear the beams.
"""

from rendering.sidebar_widgets import FRAMES, render_nine_slice
from utils.surface_utils import load_cached_image

import pygame

_STATE_ADD = {'hover': 28, 'open': 28}   # Brightness added for hover / open (sidebar cards use 28)
_BUTTON_ADD = {'hover': 28, 'flash': 62}  # Buttons: hover / click flash (the sidebar's values)
_DISABLED_MULT = (150, 150, 150, 255)    # Read-only selectors (multiplayer clients)
WOOD_TINT = (175, 175, 175, 255)         # Darkens the selector beams (owner: raw art too bright)

# Button fill: dark parchment, a little lighter at the top so it reads as raised
BUTTON_FILL_TOP = (76, 66, 47)
BUTTON_FILL_BOTTOM = (46, 39, 27)
# Toggle on (Show Borders): the inside glows - bright amber in the middle, ember at the edges
GLOW_EDGE = (118, 66, 18)
GLOW_CENTRE = (255, 214, 128)


class SetupFrames:
    """Cached framed surfaces for one setup screen."""

    def __init__(self, scale):
        self.scale = scale or 1.0
        self._cache = {}

    def _art(self, frame):
        path, insets = FRAMES[frame]
        return load_cached_image(path, alpha=True), insets

    def beam(self, height):
        """Wooden beam thickness for a selector `height` px tall."""
        return max(4, int(round(height * 0.2)))

    def content_inset(self, height):
        """Where text / arrows may start inside a selector: beam + a little air."""
        return self.beam(height) + max(4, int(round(6 * self.scale)))

    def button_beam(self, height):
        """Wooden beam thickness for a wood_button() `height` px tall: a little thinner
        than a selector's, so two lines of label fit inside (map top bar)."""
        return max(4, int(round(height * 0.16)))

    def button_inset(self, height):
        """Where a wood_button()'s label may start: beam + a little air."""
        return self.button_beam(height) + max(4, int(round(6 * self.scale)))

    def dropdown_box(self, size, fill, state='normal'):
        """Wood-framed selector box. state: 'normal' | 'hover' | 'open' | 'disabled'."""
        size = (int(size[0]), int(size[1]))
        key = ('dropdown', size, tuple(fill), state)
        surf = self._cache.get(key)
        if surf is None:
            image, insets = self._art('wood')
            beam = self.beam(size[1])
            # Beams alone first, darkened (the raw ResourceSlot wood is too bright next
            # to the setup panel), then laid over the fill. The fill reaches under the
            # beams' inner half so no gap shows at the edge.
            frame = render_nine_slice(image, insets, size, beam)
            frame.fill(WOOD_TINT, special_flags=pygame.BLEND_RGBA_MULT)
            surf = pygame.Surface(size, pygame.SRCALPHA)
            surf.fill(tuple(fill), pygame.Rect(beam // 2, beam // 2, size[0] - beam, size[1] - beam))
            surf.blit(frame, (0, 0))
            if state in _STATE_ADD:
                add = _STATE_ADD[state]
                surf.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
            elif state == 'disabled':
                surf.fill(_DISABLED_MULT, special_flags=pygame.BLEND_RGBA_MULT)
            self._cache[key] = surf
        return surf

    def wood_button(self, size, state='normal', lit=False):
        """Wood-framed button without its text (ui/map_top_bar.py draws the label).

        state: 'normal' | 'hover' | 'flash' | 'disabled'. lit: the inside glows (a toggle
        that is on, e.g. Show Borders) instead of the dark parchment fill.
        """
        size = (int(size[0]), int(size[1]))
        key = ('button', size, state, bool(lit))
        surf = self._cache.get(key)
        if surf is None:
            image, insets = self._art('wood')
            beam = self.button_beam(size[1])
            frame = render_nine_slice(image, insets, size, beam)
            frame.fill(WOOD_TINT, special_flags=pygame.BLEND_RGBA_MULT)
            surf = pygame.Surface(size, pygame.SRCALPHA)
            # Fill under the beams' inner half (as dropdown_box) so no gap shows
            inner = pygame.Rect(beam // 2, beam // 2, max(1, size[0] - beam), max(1, size[1] - beam))
            if lit:
                surf.blit(_glow_fill(inner.size), inner.topleft)
            else:
                _vertical_gradient(surf, inner, BUTTON_FILL_TOP, BUTTON_FILL_BOTTOM)
            surf.blit(frame, (0, 0))
            if state in _BUTTON_ADD:
                add = _BUTTON_ADD[state]
                surf.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
            elif state == 'disabled':
                surf.fill(_DISABLED_MULT, special_flags=pygame.BLEND_RGBA_MULT)
            self._cache[key] = surf
        return surf

    def table_border(self):
        """Bronze frame thickness (l/r, t/b) on screen."""
        return max(10, int(round(20 * self.scale))), max(8, int(round(16 * self.scale)))

    def table_frame(self, size, fill=None):
        """Carved bronze frame (transparent middle unless `fill`) for a block of rows."""
        size = (int(size[0]), int(size[1]))
        key = ('table', size, tuple(fill) if fill else None)
        surf = self._cache.get(key)
        if surf is None:
            image, insets = self._art('bronze')
            bx, by = self.table_border()
            surf = render_nine_slice(image, insets, size, (bx, by, bx, by), fill=fill)
            self._cache[key] = surf
        return surf


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _vertical_gradient(surf, rect, top, bottom):
    """Top -> bottom colour gradient into `rect` (one line per row; build time only)."""
    rows = max(1, rect.h - 1)
    for i in range(rect.h):
        pygame.draw.line(surf, _lerp(top, bottom, i / rows), (rect.x, rect.y + i), (rect.right - 1, rect.y + i))


def _glow_fill(size):
    """A soft glow for a lit button's inside: GLOW_CENTRE in the middle fading to
    GLOW_EDGE at the frame. Concentric ellipses drawn at quarter size, then scaled up
    smoothly, which blurs the steps into a gradient."""
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    sw, sh = max(4, w // 4), max(4, h // 4)
    small = pygame.Surface((sw, sh))
    small.fill(GLOW_EDGE)
    steps = 14
    for i in range(steps):
        t = i / (steps - 1)                     # 0 = outermost ring, 1 = centre
        # Outer rings reach past the corners; the wide, flat middle keeps the label lit
        ew = sw * (1.25 - 0.95 * t)
        eh = sh * (1.6 - 1.25 * t)
        ellipse = pygame.Rect(0, 0, max(1, int(ew)), max(1, int(eh)))
        ellipse.center = (sw / 2, sh / 2)
        pygame.draw.ellipse(small, _lerp(GLOW_EDGE, GLOW_CENTRE, t ** 0.8), ellipse)
    return pygame.transform.smoothscale(small, (w, h))
