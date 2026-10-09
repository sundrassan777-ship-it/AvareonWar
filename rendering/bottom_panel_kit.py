# -*- coding: utf-8 -*-
"""
Bottom panel kit — shared drawing for the sections of the bottom UI panel.

The bottom panel is split into sections by the wooden pillar separators
(Separator1.png). Every section follows the same pattern:

    centred headline
    ───────◆─────── gold rule
    content (centred, or left-aligned lists)

This module gives every view (End Turn, Territory, Army, Hero, ...) the same building
blocks so they line up and look alike:

- section_rect()      content rect between two pillars (one source of geometry for
                      drawing and tests)
- header() / rule() / vertical_rule()
                      centred headline + gold rule, plain rules, the upright rule of a
                      "T" divider (art from SidebarWidgets.separator())
- ornate_button()     CampaignBTN buttons whose wooden window is tinted (the gold frame
                      stays gold), with baked hover / flash / locked states
- battlebar()         BattleBar.png frame with a coloured fill (planning timer)
- font() / text helpers
                      fonts sized by the PANEL HEIGHT, not ui_scale: the panel is capped
                      at 300 px, so at 2560x1440 (ui_scale 1.6) the game fonts no longer
                      fit it. Sizes are their 1600x900 values times panel_height / 211.

Hover / flash convention (same as the sidebar): a control is hovered when the cursor
is on it; it flashes while game.clicked_element equals its flash key (set by
game.trigger_click_flash(type, id) in the click handler). Click handling stays in
main.py handle_bottom_ui_click().
"""

import pygame

from utils.surface_utils import (BAR_FRAME_CROP, BAR_FILL_LEFT, BAR_FILL_RIGHT, BAR_FILL_TOP,
                                 BAR_FILL_BOTTOM, BAR_FILL_HIDDEN_LEFT, get_campaign_button_image,
                                 load_cached_image)
from utils.logger import get_logger

logger = get_logger(__name__)

# Panel height at the 1600x900 reference layout (int(900 * 0.235)); font and spacing
# sizes below are given at this height
REFERENCE_PANEL_HEIGHT = 211

# The wooden beam along the panel's top edge (plus its shadow) covers ~11% of the
# art's height at any size; content starts below it. A little air at the bottom too.
CONTENT_TOP_FRAC = 0.12
CONTENT_BOTTOM_FRAC = 0.045
# Space between a pillar's edge and a section's content, at the reference height
SECTION_PAD_REF = 10
# Left margin of the leftmost section (no pillar there, just the screen edge)
EDGE_PAD_REF = 14

# role -> (px at the reference panel height, bold, italic)
FONT_ROLES = {
    'title': (21, True, False),       # Player / territory / hero / army names
    'heading': (16, True, False),     # Section headlines (Building Plots, Forces, ...)
    'body': (14, False, False),
    'body_bold': (14, True, False),
    'small': (12, False, False),
    'small_bold': (12, True, False),
    'small_italic': (12, False, True),
    'button': (15, True, False),
    'lore': (16, False, True),
}

# Inner (wood) tints of the ornate buttons. Owner-approved 2026-10-08.
TINT_END_TURN = (120, 220, 110)          # Green
TINT_END_TURN_HIGHLIGHT = (150, 255, 130)  # Tutorial highlight: brighter green
TINT_LOCKED = (170, 170, 170)            # Greyed: the action is refused right now
TINT_SELECT_ARMY = (160, 175, 200)       # Steel - not green, so it isn't read as End Turn
TINT_SELECT_ALL = (110, 160, 240)        # Blue
TINT_DESELECT_ALL = (230, 90, 80)        # Red

# Colours
GOLD_TEXT = (238, 206, 132)              # Section headlines
LIGHT_TEXT = (240, 228, 200)             # Button labels / values on wood
LOCKED_TEXT = (150, 140, 128)
SHADOW = (12, 8, 4)
BAR_TRACK = (20, 16, 14)

# The CampaignBTN art's height / width once cropped (1502x297) - fallback aspect
_BUTTON_ASPECT_FALLBACK = 297 / 1502.0

_STATE_ADD = {'hover': 28, 'flash': 62}  # Matches SidebarWidgets


class BottomPanelKit:
    """Cached drawing helpers for the bottom panel. One instance per Game."""

    SPRITE_CACHE_MAX = 200

    def __init__(self, game):
        self.game = game
        self.invalidate()

    def invalidate(self):
        """Drop every cache (resolution / display-format change)."""
        self._fonts = {}
        self._sprites = {}
        self._bar_frame_src = None

    def _cache(self, key, build):
        sprite = self._sprites.get(key)
        if sprite is None:
            if len(self._sprites) >= self.SPRITE_CACHE_MAX:
                self._sprites.clear()
            sprite = build()
            self._sprites[key] = sprite
        return sprite

    # ------------------------------------------------------------------ geometry

    @property
    def panel_top(self):
        return self.game.bottom_panel_geometry()[0]

    @property
    def panel_height(self):
        return self.game.bottom_panel_geometry()[1]

    @property
    def scale(self):
        """Panel scale: 1.0 at the 1600x900 reference (panel height 211 px)."""
        return max(0.5, self.panel_height / float(REFERENCE_PANEL_HEIGHT))

    def px(self, value):
        """A reference-size length scaled with the panel height."""
        return max(1, int(round(value * self.scale)))

    def content_top(self):
        return self.panel_top + int(round(self.panel_height * CONTENT_TOP_FRAC))

    def content_bottom(self):
        return self.panel_top + self.panel_height - int(round(self.panel_height * CONTENT_BOTTOM_FRAC))

    def section_rect(self, left_x, right_x):
        """Content rect of the section between two pillars centred on left_x / right_x.

        left_x None means the section starts at the screen's left edge (no pillar).
        """
        pillar_w = getattr(self.game, 'separator_width', 30) or 30
        pad = self.px(SECTION_PAD_REF)
        if left_x is None:
            left = self.px(EDGE_PAD_REF)
        else:
            left = int(left_x) + pillar_w // 2 + pad
        right = int(right_x) - pillar_w // 2 - pad
        top = self.content_top()
        return pygame.Rect(left, top, max(1, right - left), max(1, self.content_bottom() - top))

    # ------------------------------------------------------------------ text

    def font(self, role):
        """A Cinzel font for `role`, sized by the panel height (see module docstring)."""
        base, bold, italic = FONT_ROLES.get(role, FONT_ROLES['body'])
        size = max(9, int(round(base * self.scale)))
        key = (size, bold, italic)
        font = self._fonts.get(key)
        if font is None:
            fm = self.game.font_manager
            weight = 'semibold' if bold else 'regular'
            # Italic fonts are separate objects (never set_italic() a shared font)
            font = fm.get_italic_font(size, weight) if italic else fm.get_font(size, weight)
            self._fonts[key] = font
        return font

    def text(self, text, role, color):
        """Cached rendered text (game's shared text cache, keyed by font id)."""
        return self.game._get_cached_text(str(text), self.font(role), color)

    def fit(self, text, role, max_w):
        """`text` shortened with an ellipsis so it renders within max_w pixels."""
        font = self.font(role)
        text = str(text)
        if font.size(text)[0] <= max_w:
            return text
        while text and font.size(text + '…')[0] > max_w:
            text = text[:-1]
        return (text.rstrip() + '…') if text else '…'

    def wrap(self, text, role, max_w, max_lines=2):
        """Word-wrap to at most max_lines; the last line is ellipsized if needed."""
        if max_lines <= 1:
            return [self.fit(text, role, max_w)]
        font = self.font(role)
        words = str(text).split()
        lines, line = [], ''
        for i, word in enumerate(words):
            candidate = (line + ' ' + word) if line else word
            if font.size(candidate)[0] <= max_w or not line:
                line = candidate
                continue
            lines.append(line)
            line = word
            if len(lines) == max_lines - 1:
                # Everything left goes on the last line
                line = ' '.join(words[i:])
                break
        if line:
            lines.append(line)
        lines = lines[:max_lines] or ['']
        lines[-1] = self.fit(lines[-1], role, max_w)
        return lines

    def line_height(self, role):
        """Vertical step for one line of `role` text (Cinzel's linesize is roomy)."""
        return int(self.font(role).get_linesize() * 0.92)

    def blit_text(self, surf_text, pos, shadow_text=None):
        """Blit text, with an optional 1 px drop shadow under it."""
        screen = self.game.screen
        if shadow_text is not None:
            off = max(1, self.px(1))
            screen.blit(shadow_text, (pos[0] + off, pos[1] + off))
        screen.blit(surf_text, pos)

    def centered_text(self, text, role, color, centerx, y, shadow=True):
        """Draw `text` centred on centerx with its top at y; returns its height."""
        surf = self.text(text, role, color)
        x = centerx - surf.get_width() // 2
        self.blit_text(surf, (x, y), self.text(text, role, SHADOW) if shadow else None)
        return surf.get_height()

    def left_text(self, text, role, color, x, y, shadow=True):
        """Draw `text` with its top-left at (x, y); returns its width."""
        surf = self.text(text, role, color)
        self.blit_text(surf, (x, y), self.text(text, role, SHADOW) if shadow else None)
        return surf.get_width()

    # ------------------------------------------------------------------ rules

    def rule_gap(self):
        """Space above and below a rule."""
        return self.px(4)

    def rule_height(self):
        return 7  # SidebarWidgets.separator() art height

    def rule(self, rect, y, width_frac=0.92):
        """Gold rule centred in `rect` at y; returns the y just below it (plus a gap)."""
        width = max(8, int(rect.w * width_frac))
        art = self.game.sidebar_widgets.separator(width)
        self.game.screen.blit(art, (rect.centerx - width // 2, y))
        return y + art.get_height() + self.rule_gap()

    def vertical_rule(self, x, y0, y1):
        """Upright gold rule from y0 to y1, centred on x."""
        height = max(8, int(y1 - y0))
        art = self.game.sidebar_widgets.vertical_separator(height)
        self.game.screen.blit(art, (x - art.get_width() // 2, y0))

    def header(self, rect, text, color=GOLD_TEXT, role='heading', y=None, max_lines=1, spacing=0):
        """Centred headline (wrapped / fitted) and a gold rule under it.

        `spacing` adds that many px above AND below the rule (sections with spare
        height, e.g. Territory Info, so the headline doesn't feel cramped).
        Returns the y where the section's content starts.
        """
        y = rect.top if y is None else y
        step = self.line_height(role)
        for line in self.wrap(text, role, rect.w, max_lines):
            self.centered_text(line, role, color, rect.centerx, y)
            y += step
        return self.rule(rect, y + self.px(1) + spacing) + spacing

    def header_height(self, text, role='heading', width=None, max_lines=1, spacing=0):
        """Height header() would take (lines + rule + gaps) - for layout planning."""
        lines = len(self.wrap(text, role, width, max_lines)) if width else 1
        return (lines * self.line_height(role) + self.px(1) + self.rule_height() + self.rule_gap()
                + 2 * spacing)

    # ------------------------------------------------------------------ buttons

    def button_height(self, width):
        """Height of an ornate button `width` wide (the art's own aspect)."""
        image = get_campaign_button_image()
        aspect = (image.get_height() / float(image.get_width())) if image else _BUTTON_ASPECT_FALLBACK
        return max(12, int(round(width * aspect)))

    def button_state(self, rect, flash_key, locked=False, hover_pos=None):
        """'normal' | 'hover' | 'flash' | 'locked' for a button at `rect`."""
        if locked:
            return 'locked'
        if flash_key is not None and getattr(self.game, 'clicked_element', None) == flash_key:
            return 'flash'
        pos = self.game.mouse_pos if hover_pos is None else hover_pos
        if pos is not None and rect.collidepoint(pos):
            return 'hover'
        return 'normal'

    def ornate_button(self, rect, label, inner_tint, flash_key=None, locked=False,
                      role='button', hover_pos=None):
        """CampaignBTN with a tinted wooden window and a centred label.

        A locked button uses the grey tint whatever `inner_tint` is (refused actions
        are grey across the UI). Returns the state drawn ('hover' while hovered).
        """
        state = self.button_state(rect, flash_key, locked, hover_pos)
        tint = TINT_LOCKED if locked else inner_tint
        sprite = self.game.sidebar_widgets.button_sprite('campaign', rect.size, state=state, inner_tint=tint)
        self.game.screen.blit(sprite, rect.topleft)
        if label:
            color = LOCKED_TEXT if locked else LIGHT_TEXT
            # Leave the gold end caps clear (~16% of the width each side)
            fitted = self.fit(label, role, int(rect.w * 0.66))
            surf = self.text(fitted, role, color)
            pos = (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2)
            self.blit_text(surf, pos, self.text(fitted, role, SHADOW))
        return state

    def button_outline(self, size, color=(100, 255, 100), thickness=3):
        """Tutorial highlight band that traces an ornate button's shape (pointed caps).

        Built from the button art's alpha mask: the mask grown by `thickness` px in
        every direction, minus the button itself, so the band hugs the outline instead
        of boxing it. Returned surface is (w + 2t, h + 2t) - blit it at the button's
        top-left minus (t, t). Cached per size; the caller sets its alpha per frame
        (the same convention as SidebarWidgets.pulse_ring()).
        """
        w, h = int(size[0]), int(size[1])
        t = max(1, int(thickness))

        def build():
            sprite = self.game.sidebar_widgets.button_sprite('campaign', (w, h))
            button = pygame.mask.from_surface(sprite, 100)
            grown = pygame.mask.Mask((w + 2 * t, h + 2 * t))
            # Union of the mask shifted to every offset within a radius-t disc
            for dx in range(-t, t + 1):
                for dy in range(-t, t + 1):
                    if dx * dx + dy * dy <= t * t:
                        grown.draw(button, (t + dx, t + dy))
            grown.erase(button, (t, t))
            return grown.to_surface(setcolor=(*color, 255), unsetcolor=(0, 0, 0, 0))
        return self._cache(('outline', w, h, color, t), build)

    # ------------------------------------------------------------------ BattleBar

    def battlebar_height(self, width):
        """Height of the BattleBar frame `width` wide (the cropped art's aspect)."""
        return max(8, int(round(width * BAR_FRAME_CROP[3] / float(BAR_FRAME_CROP[2]))))

    def _bar_frame(self, size):
        def build():
            if self._bar_frame_src is None:
                raw = load_cached_image("assets/BattleBar.png", alpha=True)
                if raw is None:
                    logger.warning("BottomPanelKit: BattleBar.png missing - plain timer frame")
                    return None
                self._bar_frame_src = raw.subsurface(pygame.Rect(BAR_FRAME_CROP)).copy()
            return pygame.transform.smoothscale(self._bar_frame_src, size)
        return self._cache(('bar_frame', size), build)

    def _bar_fill(self, size, color):
        """Vertical gradient (lighter top) in `color`, built once per size/colour."""
        def build():
            surf = pygame.Surface(size)
            w, h = size
            top = tuple(min(255, int(c * 1.35) + 20) for c in color)
            bottom = tuple(int(c * 0.7) for c in color)
            for y in range(h):
                t = y / float(max(1, h - 1))
                pygame.draw.line(surf, tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)), (0, y), (w, y))
            return surf
        return self._cache(('bar_fill', size, color), build)

    def battlebar(self, rect, frac, fill_color, text=None, role='small_bold'):
        """BattleBar frame over a fill showing `frac` (0..1), with optional centred text."""
        screen = self.game.screen
        crop_w, crop_h = BAR_FRAME_CROP[2], BAR_FRAME_CROP[3]
        sx, sy = rect.w / float(crop_w), rect.h / float(crop_h)
        fill_rect = pygame.Rect(rect.x + round(BAR_FILL_LEFT * sx), rect.y + round(BAR_FILL_TOP * sy),
                                max(1, round((BAR_FILL_RIGHT - BAR_FILL_LEFT) * sx)),
                                max(1, round((BAR_FILL_BOTTOM - BAR_FILL_TOP) * sy)))
        hidden = round(BAR_FILL_HIDDEN_LEFT * sx)
        screen.fill(BAR_TRACK, fill_rect)
        frac = max(0.0, min(1.0, float(frac)))
        if frac > 0:
            width = hidden + round((fill_rect.w - hidden) * frac)
            fill = self._bar_fill(fill_rect.size, tuple(fill_color))
            screen.blit(fill, fill_rect.topleft, area=pygame.Rect(0, 0, width, fill_rect.h))
        frame = self._bar_frame(rect.size)
        if frame is not None:
            screen.blit(frame, rect.topleft)
        else:
            pygame.draw.rect(screen, GOLD_TEXT, fill_rect.inflate(4, 4), 2)
        if text:
            surf = self.text(text, role, LIGHT_TEXT)
            pos = (fill_rect.centerx - surf.get_width() // 2, fill_rect.centery - surf.get_height() // 2)
            self.blit_text(surf, pos, self.text(text, role, SHADOW))
        return fill_rect
