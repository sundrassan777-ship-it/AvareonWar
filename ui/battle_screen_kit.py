# -*- coding: utf-8 -*-
"""
Battle screen kit - the battle screen's controls in the game's ornate style
(EnhancedBattleInterface, ui/effects/battle_interface.py).

- draw_button(): CampaignBTN with baked hover / flash states (SidebarWidgets.button_sprite,
  as the bottom panel's buttons) and a light label with a drop shadow. The label is in
  the battle screen's own font: the sidebar and bottom panel kits cap their text at
  their panels' size, too small for a full-screen dialog at 1440p.
- The Skip button's label carries a fast-forward mark (Cinzel has no arrow glyphs);
  key_hint() is the keycap under it ("Space").
- icon(): an image file as a square icon, optionally framed by the game's IconBorder
  (unit and hero portraits, as the bottom panel's forces grid); shadow_text(): text with
  a 1 px drop shadow; separator(): the sidebar's fading gold rule with a diamond. The
  report (ui/battle_screen_panels.py) is built from these.
- ScrollView: a surface in a rect of its own, scrolled with the mouse wheel when it
  outgrows it (faded edges, a scrollbar) - the report's body, the preview's sides.

Everything is baked once and kept between battles (a new interface opens for every
battle) until the display changes, so opening a battle builds nothing it built before.
"""

import pygame

from rendering.bottom_panel_kit import LIGHT_TEXT, SHADOW
from rendering.sidebar_widgets import SidebarWidgets, GOLD, GOLD_DARK, PARCHMENT, PARCHMENT_DIM
from utils.surface_utils import crop_to_opaque, get_campaign_button_image, load_cached_image

# CampaignBTN's height / width once cropped (1502x297) - fallback aspect
_BUTTON_ASPECT_FALLBACK = 297 / 1502.0
LABEL_CACHE_MAX = 64
ICON_CACHE_MAX = 64
ART_CACHE_MAX = 16
KEYCAP_FILL = (18, 12, 8, 190)
TOOLTIP_FILL = (24, 16, 14, 238)   # As the sidebar's tooltips
ICON_BORDER_PATH = 'assets/mapicons/IconBorder.png'
ICON_BORDER_BRIGHTEN = 51  # +20%, as the game's own icon_border (main.py)


class _BakeHost:
    """SidebarWidgets host for baking sprites only (button_sprite() reads none of it)."""
    ui_scale = 1.0
    font_manager = None
    screen = None
    mouse_pos = (-1, -1)
    clicked_element = None

    @staticmethod
    def is_sidebar_animating():
        return False


# Rebuilt when the display changes (the sprites carry its format)
_shared = {}


def _kit():
    display = pygame.display.get_surface()
    key = display.get_size() if display is not None else None
    if _shared.get('key') != key:
        _shared.clear()
        _shared.update(key=key, widgets=SidebarWidgets(_BakeHost()), labels={}, icons={}, art={})
    return _shared


def _cached(store, limit, key, build):
    cache = _kit()[store]
    surf = cache.get(key)
    if surf is None:
        if len(cache) >= limit:
            cache.clear()
        surf = cache[key] = build()
    return surf


def _cached_label(key, build):
    return _cached('labels', LABEL_CACHE_MAX, key, build)


def _load(path, keep=False):
    """
    An image decoded from disk, or None when it is missing. keep=True decodes it once per
    process (load_cached_image) - the panel art and the icon frame, scaled to many sizes.
    An icon's own image is dropped once its small icon is baked (1024 px each).
    """
    try:
        if keep:
            return load_cached_image(path, alpha=True)
        return pygame.image.load(path).convert_alpha()
    except (pygame.error, FileNotFoundError, OSError):
        return None


def image(path):
    """A full-size image decoded once per process (shared panel art), or None."""
    return _load(path, keep=True)


def icon(path, size, bordered=False, crop=False, source=None):
    """
    An image file as a size x size icon. `bordered` frames it with the game's gold
    IconBorder, the portrait inset by 1 px (square unit and hero portraits); `crop`
    trims transparent margins first and keeps the aspect (the level shield). `source`:
    the image already decoded (the game's own icons), so the file is not read again. A
    missing image gives an empty (or just framed) icon.
    """
    def build():
        side = max(2, int(size))
        surf = pygame.Surface((side, side), pygame.SRCALPHA)
        image = source if source is not None else _load(path)
        inset = 1 if bordered else 0
        if image is not None and crop:
            image = crop_to_opaque(image, threshold=40)
            w, h = image.get_size()
            fit = side / float(max(w, h))
            scaled = pygame.transform.smoothscale(image, (max(1, int(w * fit)), max(1, int(h * fit))))
            surf.blit(scaled, scaled.get_rect(center=(side // 2, side // 2)))
        elif image is not None:
            surf.blit(pygame.transform.smoothscale(image, (side - 2 * inset, side - 2 * inset)),
                      (inset, inset))
        border = _load(ICON_BORDER_PATH, keep=True) if bordered else None
        if border is not None:
            frame = pygame.transform.smoothscale(border, (side, side))
            frame.fill((ICON_BORDER_BRIGHTEN,) * 3, special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(frame, (0, 0))
        return surf
    return _cached('icons', ICON_CACHE_MAX, ('icon', path, int(size), bordered, crop), build)


def art(path, size):
    """An image file smoothscaled to `size` (panel art), cached; None when it is missing."""
    cache = _kit()['art']
    key = (path, int(size[0]), int(size[1]))
    if key not in cache:
        if len(cache) >= ART_CACHE_MAX:
            cache.clear()
        full = _load(path, keep=True)
        cache[key] = pygame.transform.smoothscale(full, key[1:]) if full is not None else None
    return cache[key]


def shadow_text(text, font, color):
    """`text` with a 1 px drop shadow, on one transparent surface."""
    def build():
        label = font.render(text, True, color)
        shadow = font.render(text, True, SHADOW)
        surf = pygame.Surface((label.get_width() + 1, label.get_height() + 1), pygame.SRCALPHA)
        surf.blit(shadow, (1, 1))
        surf.blit(label, (0, 0))
        return surf
    return _cached_label(('text', text, font, color), build)


def bronze_plate(size, border, fill):
    """The carved bronze frame (TableBorder, as the turn banner) round a `fill`, cached."""
    bx, by = border
    return _kit()['widgets'].nine_slice('bronze', size, (bx, by, bx, by), fill)


def separator(width, color=GOLD):
    """The sidebar's thin gold rule fading at both ends, with a centre diamond."""
    return _kit()['widgets'].separator(width, color)


def tooltip_box(title, title_color, lines, title_font, body_font, scale, max_width):
    """
    A hover tooltip in the sidebar's style - a dark box with a bronze edge - holding a
    title in its colour, a gold rule and parchment lines (wrapped to `max_width`). Built
    once per text.
    """
    def build():
        def s(value):
            return max(1, int(value * scale))
        pad = s(10)
        inner = max_width - 2 * pad
        heading = shadow_text(title, title_font, title_color)
        rows = [shadow_text(part, body_font, PARCHMENT)
                for line in lines for part in _wrap_words(line, body_font, inner)]
        width = min(max_width, max([heading.get_width()] + [row.get_width() for row in rows]) + 2 * pad)
        rule = separator(width - 2 * pad)
        height = (pad + heading.get_height() + s(4) + rule.get_height() + s(4)
                  + sum(row.get_height() for row in rows) + pad)
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(surf, TOOLTIP_FILL, surf.get_rect(), border_radius=s(4))
        pygame.draw.rect(surf, GOLD_DARK, surf.get_rect(), 1, border_radius=s(4))
        y = pad
        surf.blit(heading, (pad, y))
        y += heading.get_height() + s(4)
        surf.blit(rule, (pad, y))
        y += rule.get_height() + s(4)
        for row in rows:
            surf.blit(row, (pad, y))
            y += row.get_height()
        return surf
    return cached(('tooltip', title, title_color, tuple(lines), title_font, body_font, scale,
                   max_width), build)


def _wrap_words(text, font, max_width):
    """Greedy word wrap to `max_width`."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.size(trial)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    return lines + ([current] if current else [])


def cached(key, build):
    """A small surface built once by `build()` and kept (labels, marks), keyed by `key`."""
    return _cached_label(('custom',) + tuple(key), build)


# Scrolling (the battle report's body, the preview's sides), px at 1600x900
SCROLL_STEP = 40        # A wheel notch
SCROLL_BAR = 6          # Scrollbar width
SCROLL_BAR_GAP = 8      # Between the content and its scrollbar
SCROLL_FADE = 18        # The fade at an edge with more beyond it
SCROLL_TRACK = (34, 22, 22)


class ScrollView:
    """
    A surface shown in a rect of its own: as it is when it fits, otherwise scrolled with
    the mouse wheel (wheel()) - faded at an edge with more beyond it, a gold scrollbar
    SCROLL_BAR_GAP right of the rect. Its scratch surface and fade masks are made once,
    so a frame only blits.
    """

    def __init__(self, surface, rect, scale):
        self.surface = surface
        self.rect = pygame.Rect(rect)
        self.scale = scale
        self.max_offset = max(0, surface.get_height() - self.rect.height)
        self.offset = 0          # px scrolled away at the top
        self._scratch = None
        self._masks = {}

    @property
    def scrollable(self):
        return self.max_offset > 0

    def wheel(self, dy):
        """pygame MOUSEWHEEL y (+ up). Returns True if the view moved."""
        if not self.scrollable:
            return False
        before = self.offset
        step = max(1, int(SCROLL_STEP * self.scale))
        self.offset = max(0, min(self.max_offset, self.offset - dy * step))
        return self.offset != before

    def draw(self, screen):
        if not self.scrollable:
            screen.blit(self.surface, self.rect.topleft)
            return
        width, height = self.rect.size
        if self._scratch is None:
            self._scratch = pygame.Surface((width, height), pygame.SRCALPHA)
        scratch = self._scratch
        scratch.fill((0, 0, 0, 0))
        # MAX onto a clear surface copies the pixels exactly (alpha included)
        scratch.blit(self.surface, (0, 0), pygame.Rect(0, self.offset, width, height),
                     special_flags=pygame.BLEND_RGBA_MAX)
        fade_top, fade_bottom = self.offset > 0, self.offset < self.max_offset
        if fade_top or fade_bottom:
            scratch.blit(self._mask(fade_top, fade_bottom), (0, 0),
                         special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(scratch, self.rect.topleft)
        bar_w = max(2, int(SCROLL_BAR * self.scale))
        track = pygame.Rect(self.rect.right + int(SCROLL_BAR_GAP * self.scale), self.rect.top,
                            bar_w, height)
        thumb_h = max(bar_w * 3, int(height * height / float(self.surface.get_height())))
        thumb_y = track.top + int((height - thumb_h) * self.offset / float(self.max_offset))
        pygame.draw.rect(screen, SCROLL_TRACK, track, border_radius=bar_w // 2)
        pygame.draw.rect(screen, GOLD, pygame.Rect(track.x, thumb_y, bar_w, thumb_h),
                         border_radius=bar_w // 2)

    def _mask(self, fade_top, fade_bottom):
        """Alpha multiplier fading the top / bottom edge (RGB 255: only alpha changes)."""
        key = (fade_top, fade_bottom)
        mask = self._masks.get(key)
        if mask is None:
            width, height = self.rect.size
            mask = pygame.Surface((width, height), pygame.SRCALPHA)
            mask.fill((255, 255, 255, 255))
            fade = max(1, min(height // 3, int(SCROLL_FADE * self.scale)))
            for i in range(fade):
                alpha = int(255 * (i + 1) / float(fade + 1))
                if fade_top:
                    pygame.draw.line(mask, (255, 255, 255, alpha), (0, i), (width, i))
                if fade_bottom:
                    y = height - 1 - i
                    pygame.draw.line(mask, (255, 255, 255, alpha), (0, y), (width, y))
            self._masks[key] = mask
        return mask


def button_height(width):
    """Height of an ornate button `width` wide (the art's own aspect)."""
    image = get_campaign_button_image()
    aspect = (image.get_height() / float(image.get_width())) if image else _BUTTON_ASPECT_FALLBACK
    return max(12, int(round(width * aspect)))


def button_state(rect, mouse_pos, flashing=False):
    """'flash' while the button's click flash runs, 'hover' under the cursor, else 'normal'."""
    if flashing:
        return 'flash'
    if mouse_pos is not None and rect.collidepoint(mouse_pos):
        return 'hover'
    return 'normal'


def draw_button(screen, rect, label, font, state='normal', mark=None, color=LIGHT_TEXT):
    """
    An ornate button with its label centred.

    Args:
        mark: None, or 'skip' for the fast-forward mark after the label
        color: the label's colour (the main menu windows' primary action is gold)
    """
    sprite = _kit()['widgets'].button_sprite('campaign', rect.size, state=state)
    screen.blit(sprite, rect.topleft)
    text = _cached_label(('label', label, font, mark, color),
                         lambda: _bake_label(label, font, mark, color))
    screen.blit(text, text.get_rect(center=rect.center))


def key_hint(text, font):
    """A keycap: `text` in dim parchment on a dark rounded plate with a bronze edge."""
    def build():
        label = font.render(text, True, PARCHMENT_DIM)
        pad_x = max(6, label.get_height() // 2)
        pad_y = max(2, label.get_height() // 6)
        surf = pygame.Surface((label.get_width() + 2 * pad_x, label.get_height() + 2 * pad_y),
                              pygame.SRCALPHA)
        radius = max(3, surf.get_height() // 4)
        pygame.draw.rect(surf, KEYCAP_FILL, surf.get_rect(), border_radius=radius)
        pygame.draw.rect(surf, GOLD_DARK, surf.get_rect(), 1, border_radius=radius)
        surf.blit(label, (pad_x, pad_y))
        return surf
    return _cached_label(('keycap', text, font), build)


def _bake_label(label, font, mark, color=LIGHT_TEXT):
    """Label (+ mark) with a 1 px drop shadow, on one transparent surface."""
    text = font.render(label, True, color)
    shadow = font.render(label, True, SHADOW)
    h = text.get_height()
    mark_w = 0
    gap = 0
    if mark == 'skip':
        mark_w = int(h * 0.62)
        gap = max(3, h // 4)
    surf = pygame.Surface((text.get_width() + gap + mark_w + 1, h + 1), pygame.SRCALPHA)
    surf.blit(shadow, (1, 1))
    surf.blit(text, (0, 0))
    if mark == 'skip':
        x = text.get_width() + gap
        _draw_fast_forward(surf, x + 1, 1, mark_w, h, SHADOW)
        _draw_fast_forward(surf, x, 0, mark_w, h, color)
    return surf


def _draw_fast_forward(surf, x, y, w, h, color):
    """Two arrowheads side by side (fast-forward), vertically centred on the text's caps."""
    tri_w = w / 2.0
    tri_h = h * 0.42
    top = y + h * 0.5 - tri_h / 2.0
    for i in range(2):
        left = x + i * tri_w
        pygame.draw.polygon(surf, color, [(left, top), (left + tri_w, top + tri_h / 2.0),
                                          (left, top + tri_h)])
