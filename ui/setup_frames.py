# -*- coding: utf-8 -*-
"""
Framed art for the game setup screens (Custom Game + multiplayer lobby).

- dropdown_box(): the Taxation / Victory / Turn Mode selectors, framed with the wooden
  ResourceSlot beams (nine-sliced so the beams keep their thickness however wide the
  box is — a plain stretch of the 1318x402 art squashes the top/bottom beams to a
  sliver) around the screens' existing fill colour.
- table_frame(): the carved bronze TableBorder around the multiplayer player rows,
  the same frame the Custom Game player table uses.

Both are cached per size / state; a frame costs one blit. Content inside a framed
box should start at content_inset() so text and arrows clear the beams.
"""

from rendering.sidebar_widgets import FRAMES, render_nine_slice
from utils.surface_utils import load_cached_image

import pygame

_STATE_ADD = {'hover': 28, 'open': 28}   # Brightness added for hover / open (sidebar cards use 28)
_DISABLED_MULT = (150, 150, 150, 255)    # Read-only selectors (multiplayer clients)


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

    def dropdown_box(self, size, fill, state='normal'):
        """Wood-framed selector box. state: 'normal' | 'hover' | 'open' | 'disabled'."""
        size = (int(size[0]), int(size[1]))
        key = ('dropdown', size, tuple(fill), state)
        surf = self._cache.get(key)
        if surf is None:
            image, insets = self._art('wood')
            beam = self.beam(size[1])
            # The fill reaches under the beams' inner half so no gap shows at the edge
            surf = render_nine_slice(image, insets, size, beam, fill=tuple(fill))
            if state in _STATE_ADD:
                add = _STATE_ADD[state]
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
