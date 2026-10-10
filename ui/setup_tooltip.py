# -*- coding: utf-8 -*-
"""
Hover tooltips for the game setup screens (Custom Game + multiplayer lobby).

Replaces the one-line Turn Mode hint that used to appear under the dropdown. A
setting's label ("Turn Mode:", "Taxation Level:", ...) gets a small (i) mark; hovering
the label or the mark shows a multi-line box in the in-game tooltip style (dark
panel, gold border, parchment text — as SidebarWidgets.tooltip()). The wording lives
in config/setup_tooltips.py.

Everything is cached per key / size: a frame costs blits only.
"""

import pygame

from config.setup_tooltips import SETUP_TOOLTIPS
from utils.logger import get_logger

logger = get_logger(__name__)

# In-game tooltip palette (rendering/sidebar_widgets.py)
BG = (24, 16, 14, 238)
BORDER = (120, 86, 34)          # GOLD_DARK
TITLE = (212, 170, 80)          # GOLD
TERM = (245, 214, 140)          # GOLD_LIGHT
TEXT = (226, 210, 178)          # PARCHMENT
MARK = (181, 166, 66)           # Setup screens' brass
MARK_HOVER = (245, 214, 140)

FONT_BOLD = 'assets/fonts/Cinzel-Bold.ttf'
FONT_SEMIBOLD = 'assets/fonts/Cinzel-SemiBold.ttf'
FONT_REGULAR = 'assets/fonts/Cinzel-Regular.ttf'

CURSOR_OFFSET = (16, 20)        # Box sits below-right of the pointer


class SetupTooltips:
    """Info marks + tooltip boxes for one screen (one instance per screen)."""

    def __init__(self, scale):
        self.scale = scale or 1.0
        self._fonts = {}
        self._cache = {}

    def _font(self, path, base_px, minimum):
        size = max(minimum, int(round(base_px * self.scale)))
        key = (path, size)
        if key not in self._fonts:
            try:
                self._fonts[key] = pygame.font.Font(path, size)
            except (FileNotFoundError, pygame.error, OSError) as exc:
                logger.warning(f"Setup tooltip font {path} fell back to default: {exc}")
                self._fonts[key] = pygame.font.Font(None, size)
        return self._fonts[key]

    # ------------------------------------------------------------------ info mark

    def mark_size(self):
        return max(12, int(round(16 * self.scale)))

    def mark(self, hovered=False):
        """Small circled 'i' that tells the player the label has a tooltip."""
        key = ('mark', hovered)
        surf = self._cache.get(key)
        if surf is None:
            size = self.mark_size()
            color = MARK_HOVER if hovered else MARK
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, color, (size // 2, size // 2), size // 2, max(1, size // 10))
            text = self._font(FONT_BOLD, 11, 8).render("i", True, color)
            surf.blit(text, text.get_rect(center=(size // 2, size // 2 + 1)))
            self._cache[key] = surf
        return surf

    def draw_label_mark(self, screen, label_rect, hovered=False):
        """Draw the mark right of a label; returns the label + mark hover rect."""
        size = self.mark_size()
        gap = max(4, int(round(6 * self.scale)))
        mark_rect = pygame.Rect(label_rect.right + gap, label_rect.centery - size // 2, size, size)
        screen.blit(self.mark(hovered), mark_rect)
        return label_rect.union(mark_rect)

    # ------------------------------------------------------------------ box

    def _wrap(self, font, text, max_w):
        lines, line = [], ''
        for word in text.split():
            candidate = f"{line} {word}" if line else word
            if font.size(candidate)[0] <= max_w or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines

    def box(self, key):
        """The rendered tooltip for SETUP_TOOLTIPS[key] (cached), or None."""
        spec = SETUP_TOOLTIPS.get(key)
        if spec is None:
            return None
        cache_key = ('box', key)
        surf = self._cache.get(cache_key)
        if surf is not None:
            return surf

        s = self.scale
        pad = int(round(10 * s))
        width = int(round(330 * s))
        text_w = width - 2 * pad
        title_font = self._font(FONT_BOLD, 15, 11)
        term_font = self._font(FONT_SEMIBOLD, 13, 10)
        body_font = self._font(FONT_REGULAR, 13, 10)
        para_gap = int(round(6 * s))

        # (font, text, colour, gap_before)
        lines = [(title_font, spec.get('title', ''), TITLE, 0)]
        for term, body in spec.get('entries', []):
            first = True
            if term:
                lines.append((term_font, term, TERM, para_gap))
                first = False
            for wrapped in self._wrap(body_font, body, text_w):
                lines.append((body_font, wrapped, TEXT, para_gap if first else 0))
                first = False

        height = pad
        rendered = []
        rule_y = None
        for i, (font, text, color, gap) in enumerate(lines):
            text_surf = font.render(text, True, color)
            height += gap
            rendered.append((text_surf, height))
            height += text_surf.get_height()
            if i == 0:
                # Gold rule under the title, with room either side of it
                rule_y = height + para_gap // 2
                height += para_gap
        height += pad

        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(surf, BG, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, BORDER, surf.get_rect(), 1, border_radius=4)
        pygame.draw.line(surf, BORDER, (pad, rule_y), (width - pad, rule_y), 1)
        for text_surf, y in rendered:
            surf.blit(text_surf, (pad, y))
        self._cache[cache_key] = surf
        return surf

    def draw(self, screen, key, mouse_pos):
        """Draw tooltip `key` near the cursor, flipped / clamped to stay on screen."""
        surf = self.box(key)
        if surf is None:
            return None
        sw, sh = screen.get_size()
        w, h = surf.get_size()
        x = mouse_pos[0] + CURSOR_OFFSET[0]
        y = mouse_pos[1] + CURSOR_OFFSET[1]
        if x + w > sw - 4:
            x = mouse_pos[0] - w - 8
        if y + h > sh - 4:
            y = mouse_pos[1] - h - 8
        rect = pygame.Rect(max(4, x), max(4, y), w, h)
        screen.blit(surf, rect)
        return rect
