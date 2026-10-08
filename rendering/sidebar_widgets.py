# -*- coding: utf-8 -*-
"""
Sidebar widget kit — shared drawing for the right sidebar's tabs.

The sidebar used to be drawn with flat pygame.draw.rect boxes, hardcoded offsets and
one-off scrollbars copied between tabs. This module gives every tab the same building
blocks, all pre-rendered and cached so a frame costs blits, not surface creation:

- nine_slice()          frame art (ResourceSlot wood / TableBorder bronze) stretched to any
                        size with fixed-thickness borders and our own fill in the middle
- card()                a framed card with baked hover / flash / selected / locked states
- button_sprite() / draw_button()
                        ornate buttons from the CampaignBTN / BattleBar art, tintable
- section_header(), separator(), draw_progress_bar(), draw_scrollbar()
- fit_rotated_label()   bookmark labels fitted to the tab with padding (shrink or 2 lines)
- tab_sprite()          bookmark sprites in two swappable styles (ribbon / plaque)
- text() / font()       sidebar text, capped at SIDEBAR_TEXT_MAX_SCALE

Text scale: the panel is a fixed 250 px wide while the game's fonts grow with
ui_scale (at 2560x1440 they are ~60% larger), so sidebar text is capped at
SIDEBAR_TEXT_MAX_SCALE times its 1600x900 size to keep content fitting.

Fonts: FontManager caches fonts by (size, weight), so Game.small_font and
Game.small_font_italic are the SAME object (set_italic() on one changes both). The
sidebar builds its own Font objects so its italic and upright text stay independent.

Hover / flash convention: an element is "hovered" when the cursor is on it and the
sidebar is not sliding; it "flashes" while game.clicked_element equals its flash key
(set by game.trigger_click_flash(type, id) in the click handler).
"""

from collections import OrderedDict

import pygame

from utils.surface_utils import crop_to_opaque, load_cached_image, get_campaign_button_image
from utils.logger import get_logger

logger = get_logger(__name__)

# Sidebar text grows with the screen at most this much (see module docstring)
SIDEBAR_TEXT_MAX_SCALE = 1.15

# Palette (gold trim / parchment text that suits the maroon tapestry)
GOLD = (212, 170, 80)
GOLD_DARK = (120, 86, 34)
GOLD_LIGHT = (245, 214, 140)
PARCHMENT = (226, 210, 178)
PARCHMENT_DIM = (176, 160, 134)
BRONZE_EDGE = (138, 98, 50)

# Frame art: path and the measured border thickness of the SOURCE image (L, T, R, B).
# Measured by scanning from the centre outward (see CHANGELOG 2026-10-08):
#   ResourceSlot.png 1318x402 - wooden beams, opaque black middle (we replace it)
#   TableBorder.png  1436x887 - thin carved bronze, transparent middle
FRAMES = {
    'wood': ('assets/ResourceSlot.png', (81, 65, 84, 65)),
    'bronze': ('assets/TableBorder.png', (66, 56, 55, 44)),
}

# Bookmark styles: 'ribbon' (tapestry cut + gold trim, the default) and 'plaque' (dark
# plaque with a gold frame). The original flat 'classic' tabs were removed once the
# ribbons were approved.
TAB_STYLES = ('ribbon', 'plaque')

_STATE_ADD = {'hover': 28, 'flash': 62}    # Brightness added for hover / click flash


class SidebarWidgets:
    """Cached drawing helpers for the sidebar. One instance per Game."""

    TEXT_CACHE_MAX = 900
    SPRITE_CACHE_MAX = 400

    def __init__(self, game):
        self.game = game
        self.invalidate()

    def invalidate(self):
        """Drop every cache (resolution / display-format change)."""
        self._fonts = {}
        self._text = OrderedDict()
        self._sprites = OrderedDict()
        self._art = {}

    # ------------------------------------------------------------------ caches

    def _get(self, key):
        sprite = self._sprites.get(key)
        if sprite is not None:
            self._sprites.move_to_end(key)
        return sprite

    def _put(self, key, sprite):
        self._sprites[key] = sprite
        if len(self._sprites) > self.SPRITE_CACHE_MAX:
            self._sprites.popitem(last=False)
        return sprite

    # ------------------------------------------------------------------ text

    @property
    def scale(self):
        """Sidebar text scale: the game's ui_scale, capped (see module docstring)."""
        return min(getattr(self.game, 'ui_scale', 1.0) or 1.0, SIDEBAR_TEXT_MAX_SCALE)

    # role -> (base px at 1600x900, bold, italic)
    FONT_ROLES = {
        'title': (15, True, False),
        'heading': (13, True, False),
        'body': (12, False, False),
        'body_bold': (12, True, False),
        'small': (10, False, False),
        'small_bold': (10, True, False),
        'italic': (11, False, True),
        'digits': (15, True, False),
    }

    def font(self, role, px=None):
        """A sidebar font. `px` overrides the role's scaled size (label fitting)."""
        base, bold, italic = self.FONT_ROLES.get(role, self.FONT_ROLES['body'])
        # Roles never drop below 9 px (at 1280x720 the 10 px 'small' role scaled to 8 px,
        # unreadable for the Action Log's battle details); explicit px (label fitting)
        # keeps its own minimum
        size = max(7, int(round(px))) if px is not None else max(9, int(round(base * self.scale)))
        key = (size, bold, italic)
        font = self._fonts.get(key)
        if font is None:
            fm = getattr(self.game, 'font_manager', None)
            path = None
            if fm is not None and getattr(fm, 'fonts_loaded', False):
                path = fm.cinzel_bold_path if bold else fm.cinzel_semibold_path
            try:
                font = pygame.font.Font(path, size) if path else pygame.font.SysFont('arial', size, bold=bold)
            except (pygame.error, OSError, FileNotFoundError) as exc:
                logger.warning(f"Sidebar font {key} fell back to Arial: {exc}")
                font = pygame.font.SysFont('arial', size, bold=bold)
            font.set_italic(italic)
            self._fonts[key] = font
        return font

    def text(self, text, role, color, px=None):
        """Cached rendered text (own LRU: the log alone outgrows the shared 200-entry one)."""
        key = (text, role, color, px, self.scale)
        surf = self._text.get(key)
        if surf is not None:
            self._text.move_to_end(key)
            return surf
        surf = self.font(role, px).render(str(text), True, color)
        self._text[key] = surf
        if len(self._text) > self.TEXT_CACHE_MAX:
            self._text.popitem(last=False)
        return surf

    def fit_text(self, text, role, max_w):
        """`text` shortened with an ellipsis so it renders within max_w pixels."""
        font = self.font(role)
        if font.size(text)[0] <= max_w:
            return text
        while text and font.size(text + '…')[0] > max_w:
            text = text[:-1]
        return (text.rstrip() + '…') if text else '…'

    def wrap(self, text, role, max_w):
        """Pixel-width word wrap. Words longer than a line are hard-broken."""
        font = self.font(role)
        lines, line = [], ''
        for word in str(text).split():
            candidate = (line + ' ' + word) if line else word
            if font.size(candidate)[0] <= max_w:
                line = candidate
                continue
            if line:
                lines.append(line)
            while font.size(word)[0] > max_w and len(word) > 1:
                cut = len(word)
                while cut > 1 and font.size(word[:cut])[0] > max_w:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        if line:
            lines.append(line)
        return lines or ['']

    # ------------------------------------------------------------------ art

    def _frame_art(self, frame):
        if frame not in self._art:
            path, insets = FRAMES[frame]
            self._art[frame] = (load_cached_image(path, alpha=True), insets)
        return self._art[frame]

    def _button_art(self, art):
        key = ('button', art)
        if key not in self._art:
            if art == 'campaign':
                image = get_campaign_button_image()
            else:  # 'battlebar'
                raw = load_cached_image('assets/BattleBar.png', alpha=True)
                image = crop_to_opaque(raw, threshold=128) if raw else None
            self._art[key] = image
        return self._art[key]

    @staticmethod
    def display_alpha(surface):
        """`surface` converted to the display's alpha pixel format when a display exists.

        Composed SRCALPHA sprites (cards, icons) are blitted every frame; in the
        display's own format pygame blends them without a per-pixel format conversion.
        """
        if pygame.display.get_init() and pygame.display.get_surface() is not None:
            try:
                return surface.convert_alpha()
            except pygame.error:
                pass
        return surface

    # ------------------------------------------------------------------ icons

    def icon(self, path, size, crop=False, frame=False):
        """An image file as a size x size icon (aspect kept, centred), cached."""
        key = ('icon_path', path, int(size), crop, frame)
        cached = self._get(key)
        if cached is not None:
            return cached
        return self._put(key, self._make_icon(load_cached_image(path, alpha=True), size, crop, frame))

    def icon_surface(self, key, surface, size, crop=False, frame=False):
        """An already-loaded surface (unit portrait, army flag) as an icon, cached by `key`."""
        full_key = ('icon_surf', key, int(size), crop, frame, id(surface))
        cached = self._get(full_key)
        if cached is not None:
            return cached
        return self._put(full_key, self._make_icon(surface, size, crop, frame))

    @staticmethod
    def _make_icon(image, size, crop, frame):
        size = max(2, int(size))
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        if image is None:
            return surf
        if crop:
            image = crop_to_opaque(image, threshold=40)
        iw, ih = image.get_size()
        inner = size - (2 if frame else 0)
        scale = min(inner / float(iw), inner / float(ih))
        scaled = pygame.transform.smoothscale(image, (max(1, int(iw * scale)), max(1, int(ih * scale))))
        surf.blit(scaled, scaled.get_rect(center=(size // 2, size // 2)))
        if frame:
            # Thin gold frame: the unit portraits are opaque squares
            pygame.draw.rect(surf, GOLD_DARK, surf.get_rect(), 1)
        return surf

    # ------------------------------------------------------------------ nine-slice

    def nine_slice(self, frame, size, border, fill=None):
        """Frame art stretched to `size` with fixed-thickness borders.

        Args:
            frame: 'wood' or 'bronze' (FRAMES).
            size: (w, h) of the result.
            border: Destination border thickness in px (int, or (l, t, r, b)).
            fill: Middle fill — an (r, g, b[, a]) colour, a ((top), (bottom)) vertical
                gradient pair, or None for transparent. The art's own middle is never
                used (ResourceSlot's is opaque black).

        Returns a cached SRCALPHA surface. Falls back to a plain bordered box if the
        art is missing.
        """
        w, h = int(size[0]), int(size[1])
        if isinstance(border, int):
            border = (border, border, border, border)
        key = ('nine', frame, w, h, tuple(border), _fill_key(fill))
        cached = self._get(key)
        if cached is not None:
            return cached

        surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        dl, dt, dr, db = border
        # Fill first, inset by half the border so it never peeks outside the frame
        if fill is not None:
            inner = pygame.Rect(dl // 2, dt // 2, max(1, w - (dl + dr) // 2), max(1, h - (dt + db) // 2))
            _paint_fill(surf, inner, fill)

        image, (sl, st, sr, sb) = self._frame_art(frame)
        if image is None:
            pygame.draw.rect(surf, BRONZE_EDGE, surf.get_rect(), max(1, min(border)))
            return self._put(key, surf)

        iw, ih = image.get_size()
        sx = (0, sl, iw - sr, iw)
        sy = (0, st, ih - sb, ih)
        dx = (0, dl, w - dr, w)
        dy = (0, dt, h - db, h)
        for row in range(3):
            for col in range(3):
                if row == 1 and col == 1:
                    continue  # middle: our fill, never the art's
                src = pygame.Rect(sx[col], sy[row], sx[col + 1] - sx[col], sy[row + 1] - sy[row])
                dst_w, dst_h = dx[col + 1] - dx[col], dy[row + 1] - dy[row]
                if src.w <= 0 or src.h <= 0 or dst_w <= 0 or dst_h <= 0:
                    continue
                piece = pygame.transform.smoothscale(image.subsurface(src), (dst_w, dst_h))
                surf.blit(piece, (dx[col], dy[row]))
        return self._put(key, surf)

    def card(self, frame, size, border, fill, state='normal'):
        """A framed card with a baked interaction state.

        state: 'normal' | 'hover' | 'flash' | 'selected' | 'locked'. Each variant is
        baked once (no per-frame copies); 'selected' adds a gold inner outline.
        """
        key = ('card', frame, int(size[0]), int(size[1]), border if isinstance(border, int) else tuple(border),
               _fill_key(fill), state)
        cached = self._get(key)
        if cached is not None:
            return cached
        surf = self.nine_slice(frame, size, border, fill).copy()
        _apply_state(surf, state)
        if state == 'selected':
            b = border if isinstance(border, int) else border[0]
            pygame.draw.rect(surf, GOLD_LIGHT, surf.get_rect().inflate(-b, -b), 2, border_radius=3)
        return self._put(key, surf)

    # ------------------------------------------------------------------ buttons

    def button_sprite(self, art, size, tint=None, state='normal'):
        """Ornate button art scaled to `size`, optionally tinted, in a baked state."""
        w, h = int(size[0]), int(size[1])
        key = ('btn', art, w, h, tint, state)
        cached = self._get(key)
        if cached is not None:
            return cached
        image = self._button_art(art)
        surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        if image is not None:
            surf.blit(pygame.transform.smoothscale(image, (w, h)), (0, 0))
        else:
            pygame.draw.rect(surf, (90, 60, 40), surf.get_rect(), border_radius=4)
            pygame.draw.rect(surf, GOLD, surf.get_rect(), 2, border_radius=4)
        if tint is not None:
            # Multiply keeps the art's shading; RGBA_MULT leaves alpha (the shape) intact
            surf.fill((tint[0], tint[1], tint[2], 255), special_flags=pygame.BLEND_RGBA_MULT)
        _apply_state(surf, state)
        return self._put(key, surf)

    def draw_button(self, rect, label, art='campaign', tint=None, flash_key=None,
                    locked=False, role='body_bold', text_color=PARCHMENT, viewport=None):
        """Draw an ornate button; returns True while hovered.

        Hover brightens it, a matching game.clicked_element flashes it, `locked`
        dims it (and suppresses hover). Click handling stays with the caller.
        """
        hovering = (not locked) and self.hover(rect, viewport)
        if locked:
            state = 'locked'
        elif flash_key is not None and getattr(self.game, 'clicked_element', None) == flash_key:
            state = 'flash'
        elif hovering:
            state = 'hover'
        else:
            state = 'normal'
        self.blit_button(self.game.screen, rect, label, art, tint, state, role, text_color)
        return hovering

    def blit_button(self, surface, rect, label, art='campaign', tint=None, state='normal',
                    role='body_bold', text_color=PARCHMENT):
        """Draw a button in a given state onto any surface (no hover logic).

        Used by draw_button() and by pre-composed sprites (e.g. order cards), which
        decide the state themselves.
        """
        surface.blit(self.button_sprite(art, rect.size, tint, state), rect.topleft)
        if label:
            color = (150, 140, 128) if state == 'locked' else text_color
            label_surf = self.text(self.fit_text(label, role, rect.w - 24), role, color)
            surface.blit(label_surf, label_surf.get_rect(center=rect.center))

    # ------------------------------------------------------------------ decorations

    def separator(self, width, color=GOLD):
        """Thin gold rule fading at both ends, with a small centre diamond."""
        width = max(8, int(width))
        key = ('sep', width, color)
        cached = self._get(key)
        if cached is not None:
            return cached
        surf = pygame.Surface((width, 7), pygame.SRCALPHA)
        fade = max(1, width // 5)
        for x in range(width):
            a = 255
            if x < fade:
                a = int(255 * x / fade)
            elif x >= width - fade:
                a = int(255 * (width - 1 - x) / fade)
            surf.set_at((x, 3), (*color, a))
        c = width // 2
        pygame.draw.polygon(surf, color, [(c, 0), (c + 3, 3), (c, 6), (c - 3, 3)])
        return self._put(key, surf)

    def section_header(self, text, width, color=GOLD_LIGHT, role='heading'):
        """Centred heading with a separator underneath (one cached surface)."""
        key = ('hdr', text, int(width), color, role, self.scale)
        cached = self._get(key)
        if cached is not None:
            return cached
        label = self.text(self.fit_text(text, role, width - 8), role, color)
        rule = self.separator(width)
        surf = pygame.Surface((int(width), label.get_height() + 3 + rule.get_height()), pygame.SRCALPHA)
        surf.blit(label, label.get_rect(midtop=(int(width) // 2, 0)))
        surf.blit(rule, (0, label.get_height() + 3))
        return self._put(key, surf)

    def tooltip(self, text):
        """Small dark label with a gold border (hover hints), cached per text."""
        key = ('tooltip', text, self.scale)
        cached = self._get(key)
        if cached is not None:
            return cached
        label = self.text(text, 'body_bold', PARCHMENT)
        surf = pygame.Surface((label.get_width() + 14, label.get_height() + 8), pygame.SRCALPHA)
        pygame.draw.rect(surf, (24, 16, 14, 238), surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, GOLD_DARK, surf.get_rect(), 1, border_radius=4)
        surf.blit(label, (7, 4))
        return self._put(key, surf)

    def draw_progress_bar(self, rect, frac, fill=(196, 150, 60), track=(28, 20, 16)):
        """Gold-bordered progress bar (two rect fills, no surfaces)."""
        frac = max(0.0, min(1.0, float(frac)))
        screen = self.game.screen
        pygame.draw.rect(screen, track, rect, border_radius=3)
        if frac > 0:
            inner = rect.inflate(-4, -4)
            inner.w = max(1, int(inner.w * frac))
            pygame.draw.rect(screen, fill, inner, border_radius=2)
        pygame.draw.rect(screen, GOLD_DARK, rect, 1, border_radius=3)

    def draw_scrollbar(self, track_rect, scroll_state):
        """Dark track with a gold thumb. Draws nothing when everything fits."""
        thumb = scroll_state.thumb(track_rect.y, track_rect.h)
        if thumb is None:
            return
        screen = self.game.screen
        pygame.draw.rect(screen, (34, 22, 22), track_rect, border_radius=3)
        y, h = thumb
        pygame.draw.rect(screen, GOLD, pygame.Rect(track_rect.x, y, track_rect.w, h), border_radius=3)

    # ------------------------------------------------------------------ interaction

    def hover(self, rect, viewport=None):
        """Cursor on `rect` (and inside `viewport`), sidebar not sliding."""
        if rect is None or self.game.is_sidebar_animating():
            return False
        pos = self.game.mouse_pos
        if viewport is not None and not viewport.collidepoint(pos):
            return False
        return rect.collidepoint(pos)

    @staticmethod
    def clip_hit(rect, viewport):
        """`rect` clipped to the scroll viewport, or None when fully scrolled away.

        Click rects are stored clipped, so a card half-hidden under the header can't
        take a click meant for the header.
        """
        clipped = rect.clip(viewport)
        return clipped if clipped.w > 0 and clipped.h > 0 else None

    def begin_clip(self, rect):
        """Clip drawing to `rect`; returns the previous clip for end_clip()."""
        previous = self.game.screen.get_clip()
        self.game.screen.set_clip(rect)
        return previous

    def end_clip(self, previous):
        self.game.screen.set_clip(previous)

    def band(self, w, h, rgba):
        """A translucent band of any size from one reused surface (blit with area)."""
        key = ('band', rgba)
        surf = self._get(key)
        need_w, need_h = max(1, int(w)), max(1, int(h))
        if surf is None or surf.get_width() < need_w or surf.get_height() < need_h:
            surf = pygame.Surface((max(need_w, 260), max(need_h, 1200)), pygame.SRCALPHA)
            surf.fill(rgba)
            self._put(key, surf)
        return surf, pygame.Rect(0, 0, need_w, need_h)

    # ------------------------------------------------------------------ bookmarks

    def common_label_px(self, labels, max_len, max_thick, min_px=8):
        """One font size for ALL bookmark labels: the largest at which every label fits.

        Fitting each label on its own made them different sizes (at 1280x720
        "Technology" shrank to 8 px while "Heroes" stayed at 12). Shared sizing keeps
        the column consistent, mirroring how the rest of the UI scales its text.
        """
        base_px = int(round(12 * self.scale))
        key = ('label_px', tuple(labels), int(max_len), int(max_thick), base_px)
        cached = self._get(key)
        if cached is not None:
            return cached
        px = base_px
        while px > min_px:
            font = self.font('body', px)
            if all(font.size(label)[0] <= max_len and font.get_height() <= max_thick for label in labels):
                break
            px -= 1
        return self._put(key, px)

    def fit_rotated_label(self, text, max_len, max_thick, color, base_px=None):
        """Bookmark label rotated to read top-to-bottom, fitted inside the tab.

        Tries, in order: one line at the base size shrinking to 85%; two lines
        (split at a space) at up to the base size; one line shrinking to 8 px.
        `max_len` is along the tab's length (its height), `max_thick` across it.
        """
        base_px = int(round(base_px if base_px is not None else 12 * self.scale))
        key = ('label', text, int(max_len), int(max_thick), color, base_px)
        cached = self._get(key)
        if cached is not None:
            return cached

        def single(px):
            return self.font('body', px).render(text, True, color)

        surf = None
        for px in range(base_px, max(7, int(base_px * 0.85)) - 1, -1):
            candidate = single(px)
            if candidate.get_width() <= max_len and candidate.get_height() <= max_thick:
                surf = candidate
                break
        if surf is None and ' ' in text:
            words = text.split(' ')
            mid = max(1, len(words) // 2)
            lines = (' '.join(words[:mid]), ' '.join(words[mid:]))
            for px in range(base_px, 7, -1):
                font = self.font('body', px)
                rendered = [font.render(line, True, color) for line in lines]
                line_h = font.get_linesize() - 2
                width = max(r.get_width() for r in rendered)
                height = line_h * 2
                if width <= max_len and height <= max_thick:
                    surf = pygame.Surface((width, height), pygame.SRCALPHA)
                    for i, r in enumerate(rendered):
                        surf.blit(r, r.get_rect(midtop=(width // 2, i * line_h)))
                    break
        if surf is None:
            px = base_px
            surf = single(px)
            while px > 7 and (surf.get_width() > max_len or surf.get_height() > max_thick):
                px -= 1
                surf = single(px)
        return self._put(key, pygame.transform.rotate(surf, -90))

    def tab_sprite(self, style, label, size, state, texture_src=None, label_px=None):
        """One bookmark, fully baked (fill, trim, glow, label).

        Args:
            style: 'ribbon' | 'plaque' (anything else falls back to 'ribbon').
            label: Display name.
            size: (w, h).
            state: 'inactive' | 'hover' | 'flash' | 'active' | 'active_hover' |
                   'locked' | 'highlight' (tutorial: green trim).
            texture_src: (image, src_rect) the ribbon fill is cut from — the scaled
                panel tapestry at the tab's own height, so its pattern continues the
                panel's. Keyed by (id(image), rect), so the cut happens only on a miss.
        """
        w, h = int(size[0]), int(size[1])
        tex_key = None
        if texture_src is not None and texture_src[0] is not None:
            tex_key = (id(texture_src[0]), tuple(texture_src[1]))
        key = ('tab', style, label, w, h, state, tex_key, self.scale, label_px)
        cached = self._get(key)
        if cached is not None:
            return cached
        texture = None
        if tex_key is not None:
            image, src = texture_src
            src = pygame.Rect(src).clip(image.get_rect())
            if src.w > 0 and src.h > 0:
                texture = pygame.transform.smoothscale(image.subsurface(src), (w, h))
        builder = self._plaque_tab if style == 'plaque' else self._ribbon_tab
        self._label_px = label_px  # shared size for this tab column (common_label_px)
        surf = builder(label, w, h, state, texture)
        return self._put(key, surf)

    def _label_for(self, label, w, h, color, notch=0):
        pad = max(8, int(7 * self.scale))
        return self.fit_rotated_label(label, h - 2 * pad, w - 10 - notch, color,
                                      base_px=getattr(self, '_label_px', None))

    def tab_label_space(self, w, h, notch=True):
        """(max_len, max_thick) available for a label in a w x h tab."""
        pad = max(8, int(7 * self.scale))
        return h - 2 * pad, w - 10 - (max(4, w // 7) if notch else 0)

    def _ribbon_tab(self, label, w, h, state, texture):
        """Tapestry ribbon: cut from the panel texture, gold trim, swallowtail notch."""
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if texture is not None:
            surf.blit(texture, (0, 0))
        else:
            surf.fill((92, 40, 46))
        # Brightness per state: inactive tabs recede, hover clearly lifts, the active
        # one is fully lit and warmed so it reads as selected at a glance
        mult = {'inactive': 105, 'hover': 190, 'flash': 230, 'locked': 62,
                'highlight': 150, 'active': 255, 'active_hover': 255}.get(state, 105)
        surf.fill((mult, mult, mult, 255), special_flags=pygame.BLEND_RGBA_MULT)
        warm = {'active': (46, 16, 10), 'active_hover': (62, 28, 18), 'flash': (40, 26, 14),
                'hover': (14, 8, 4)}.get(state)
        if warm:
            surf.fill(warm, special_flags=pygame.BLEND_RGB_ADD)

        notch = max(4, w // 7)
        # Swallowtail: cut a shallow V into the outer (left) edge
        pygame.draw.polygon(surf, (0, 0, 0, 0), [(0, h // 2 - notch * 2), (notch, h // 2), (0, h // 2 + notch * 2)])

        trim = (95, 200, 95) if state == 'highlight' else ((96, 86, 70) if state == 'locked' else GOLD)
        active = state in ('active', 'active_hover')
        # Gold trim on top, bottom and the notched left edge; the active tab has no
        # inner (right) trim so it merges into the panel
        pygame.draw.line(surf, trim, (0, 0), (w - 1, 0), 2)
        pygame.draw.line(surf, trim, (0, h - 2), (w - 1, h - 2), 2)
        pygame.draw.lines(surf, trim, False, [(1, 0), (1, h // 2 - notch * 2), (notch + 1, h // 2),
                                              (1, h // 2 + notch * 2), (1, h - 1)], 2)
        if not active:
            pygame.draw.line(surf, GOLD_DARK, (w - 1, 0), (w - 1, h - 1), 1)
        else:
            # Persistent soft inner glow: three fading gold strokes inside the trim.
            # Drawn on an overlay and BLENDED in — pygame.draw writes alpha directly,
            # which would punch translucent holes into the tab instead of glowing.
            glow = pygame.Surface((w, h), pygame.SRCALPHA)
            for i, alpha in enumerate((190, 110, 55, 24)):
                inset = 3 + i * 2
                pygame.draw.rect(glow, (*GOLD_LIGHT, alpha),
                                 pygame.Rect(inset + notch // 2, inset, w - inset - notch // 2, h - 2 * inset),
                                 2 if i == 0 else 1)
            surf.blit(glow, (0, 0))

        # Labels lighter than the plaque ones: the tapestry behind them is busy
        # (owner feedback: inactive text was hard to read on it)
        color = {'active': (255, 240, 204), 'active_hover': (255, 246, 218), 'hover': (250, 236, 204),
                 'flash': (255, 246, 218), 'locked': (150, 138, 124), 'highlight': (225, 248, 225)
                 }.get(state, (222, 208, 180))
        text = self._label_for(label, w, h, color, notch)
        center = (w // 2 + notch // 2, h // 2)
        # 1 px dark drop shadow lifts the text off the pattern
        shadow = self._label_for(label, w, h, (24, 10, 10), notch)
        surf.blit(shadow, shadow.get_rect(center=(center[0] + 1, center[1] + 1)))
        surf.blit(text, text.get_rect(center=center))
        return surf

    def _plaque_tab(self, label, w, h, state, texture):
        """Dark plaque with a gold frame; the active one gets a lit frame + inner glow."""
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        base = {'inactive': (34, 24, 20), 'hover': (52, 38, 30), 'flash': (78, 58, 40), 'locked': (24, 22, 20),
                'highlight': (30, 52, 30), 'active': (70, 30, 34), 'active_hover': (82, 38, 40)}.get(state, (34, 24, 20))
        pygame.draw.rect(surf, base, surf.get_rect(), border_radius=4)
        lit = state in ('active', 'active_hover', 'flash')
        frame = (95, 200, 95) if state == 'highlight' else (GOLD_LIGHT if lit else (GOLD_DARK if state == 'locked' else GOLD))
        pygame.draw.rect(surf, frame, surf.get_rect(), 2, border_radius=4)
        pygame.draw.rect(surf, GOLD_DARK, surf.get_rect().inflate(-6, -6), 1, border_radius=3)
        if lit:
            # Inner glow on an overlay, blended (see _ribbon_tab)
            glow = pygame.Surface((w, h), pygame.SRCALPHA)
            for i, alpha in enumerate((90, 45)):
                pygame.draw.rect(glow, (*GOLD_LIGHT, alpha), glow.get_rect().inflate(-8 - 4 * i, -8 - 4 * i), 2,
                                 border_radius=3)
            surf.blit(glow, (0, 0))
        color = (255, 238, 196) if lit else ((118, 108, 98) if state == 'locked' else PARCHMENT_DIM)
        text = self._label_for(label, w, h, color)
        surf.blit(text, text.get_rect(center=(w // 2, h // 2)))
        return surf

    # Technology tree connectors: state -> (shaft/head colour, outline colour, glow colour or None)
    TECH_ARROW_STYLE = {
        'locked': ((196, 152, 72), (52, 32, 12), None),          # bronze: path still closed
        'open': ((120, 225, 120), (20, 60, 20), (90, 235, 90)),  # green + glow: next tech researchable
        'done': ((96, 168, 96), (22, 48, 22), None),             # muted green: both researched
    }

    def tech_arrow(self, length, state):
        """Downward connector between two tech buttons (shaft + chevron head), cached.

        Replaces the plain grey line + triangle. 'open' (prerequisite researched) is
        green with a soft glow so a newly available path stands out at a glance.
        """
        length = max(6, int(length))
        key = ('tech_arrow', length, state)
        cached = self._get(key)
        if cached is not None:
            return cached
        color, outline, glow = self.TECH_ARROW_STYLE.get(state, self.TECH_ARROW_STYLE['locked'])
        width = 20
        cx = width // 2
        head = max(4, min(8, length // 3))
        shaft_end = length - head
        surf = pygame.Surface((width, length), pygame.SRCALPHA)
        if glow:
            # Soft glow under the arrow: wide translucent strokes, blended in
            halo = pygame.Surface((width, length), pygame.SRCALPHA)
            for stroke, alpha in ((12, 40), (8, 70)):
                pygame.draw.line(halo, (*glow, alpha), (cx, 0), (cx, length - 2), stroke)
            surf.blit(halo, (0, 0))
        # Shaft: dark outline then the coloured core
        pygame.draw.rect(surf, outline, pygame.Rect(cx - 3, 0, 6, max(1, shaft_end)))
        pygame.draw.rect(surf, color, pygame.Rect(cx - 2, 0, 4, max(1, shaft_end)))
        # Chevron head pointing down
        tip = (cx, length - 1)
        points = [(cx - 7, shaft_end - 1), tip, (cx + 7, shaft_end - 1)]
        pygame.draw.polygon(surf, color, points)
        pygame.draw.polygon(surf, outline, points, 1)
        return self._put(key, self.display_alpha(surf))

    def pulse_ring(self, size, color=(100, 255, 100)):
        """Tutorial highlight ring, cached; the caller sets its alpha per frame."""
        key = ('ring', int(size[0]), int(size[1]), color)
        cached = self._get(key)
        if cached is None:
            cached = pygame.Surface((int(size[0]), int(size[1])), pygame.SRCALPHA)
            pygame.draw.rect(cached, (*color, 255), cached.get_rect(), 3)
            self._put(key, cached)
        return cached


# ---------------------------------------------------------------------- helpers

def _fill_key(fill):
    if fill is None:
        return None
    if isinstance(fill, tuple) and fill and isinstance(fill[0], tuple):
        return ('grad',) + tuple(tuple(c) for c in fill)
    return tuple(fill)


def _paint_fill(surf, rect, fill):
    """Solid colour or a ((top), (bottom)) vertical gradient into `rect`."""
    if isinstance(fill, tuple) and fill and isinstance(fill[0], tuple):
        top, bottom = fill
        steps = max(1, rect.h)
        for i in range(rect.h):
            t = i / float(steps)
            color = tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(len(top)))
            pygame.draw.line(surf, color, (rect.x, rect.y + i), (rect.right - 1, rect.y + i))
    else:
        surf.fill(fill, rect)


def _apply_state(surf, state):
    """Bake an interaction state into a sprite (alpha / shape untouched)."""
    if state in _STATE_ADD:
        add = _STATE_ADD[state]
        surf.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
    elif state == 'locked':
        surf.fill((120, 120, 120, 255), special_flags=pygame.BLEND_RGBA_MULT)
