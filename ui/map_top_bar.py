# -*- coding: utf-8 -*-
"""
Map top bar of the game setup screens (Custom Game + multiplayer lobby).

The wooden strip above the setup map holds, left to right:

    [Randomize         ]
    [Starting Positions]     (<) [ MAP NAME ] (>)     [Show Borders]

- Randomize Starting Positions: a wood button (ResourceSlot beams), its label on two
  lines so it is as wide as Show Borders (owner request). The screen gives every
  active player a random start (map_data.pick_starting_territories()). In the lobby
  only the host may press it; clients see it greyed with a tooltip saying so.
- The map name sits on TextBar.png (gold bar, dark window) so it reads on the wood;
  the round medallion arrows (and a click on the name) change the map. Clients and
  single-map installs get the name bar without arrows.
- Show Borders: the same wood button; its inside glows while borders are shown.

Both screens used to carry their own copy of plain triangle arrows, a brass map name and
a small checkbox. Now they share this widget and only act on what handle_click() returns
- change the widget, not one screen (as ui/additional_options_overlay.py).

Every control highlights on hover, flashes on click and plays the UI click sound.
Sprites are built once per size / state and cached: a frame costs blits only.
"""

import pygame

import map_data
from rendering.sidebar_widgets import GOLD, GOLD_DARK, GOLD_LIGHT
from ui.setup_frames import SetupFrames
from utils.logger import get_logger
from utils.surface_utils import crop_to_opaque, load_cached_image

logger = get_logger(__name__)

FLASH_MS = 120      # Click flash length (the Additional Options window's)

RANDOMIZE_LABEL = "Randomize Starting Positions"
# Normally on two lines: both buttons then share one width (the widest line) and one
# font size, close to Show Borders' own width (owner: the one-line button was too wide)
RANDOMIZE_LINES = ("Randomize", "Starting Positions")
# Fallbacks for a strip too low for two lines (no supported resolution): one line, then
# this shorter text below MIN_LABEL_PX (owner: OK). The tooltip names the whole action.
RANDOMIZE_LABEL_SHORT = "Randomize Starts"
BORDERS_LABEL = "Show Borders"
MIN_LABEL_PX = 12
MIN_TWO_LINE_PX = 10   # Two-line labels may be this small (720p)

# Returned by handle_click() for a click on a control that is shown but may not be used
# here (a client's greyed Randomize, a client's map name): the click is used up, nothing
# happens and no sound plays.
BLOCKED = 'blocked'

# Hover / flash brightness for the name bar and arrows (buttons: ui/setup_frames.py)
_STATE_ADD = {'hover': 28, 'flash': 62}

FONT_SEMIBOLD = 'assets/fonts/Cinzel-SemiBold.ttf'
FONT_BOLD = 'assets/fonts/Cinzel-Bold.ttf'

LABEL_COLOR = GOLD_LIGHT              # Button label on the dark fill
LABEL_COLOR_LIT = (44, 28, 10)        # Dark label on the glowing (toggle on) fill
LABEL_COLOR_DISABLED = (150, 150, 150)
NAME_COLOR = GOLD_LIGHT               # Map name on the TextBar's dark window

# TextBar.png (1536x1024, a gold bar in a mostly transparent canvas). Cropped to its
# opaque body by crop_to_opaque(threshold=128) = (46, 362, 1438, 170). In that crop
# (measured 2026-10-15): each spear-tip end cap is TEXTBAR_CAP px wide (kept whole, the
# straight middle stretches), and the dark window spans x 242..1199, y 42..122.
TEXTBAR_PATH = 'assets/TextBar.png'
TEXTBAR_CAP = 250
TEXTBAR_WINDOW = (242, 42, 1199, 122)    # left, top, right, bottom in the crop

# Medallion arrows (owner choice): dark disc, gold rim, faceted gold chevron
MEDALLION_OUTLINE = (18, 11, 5)
MEDALLION_DISC_TOP = (62, 46, 30)
MEDALLION_DISC_BOTTOM = (16, 10, 6)
CHEVRON_LIGHT = (240, 206, 124)       # Upper facet (TextBar's pyramids are faceted alike)
CHEVRON_DARK = (176, 132, 54)         # Lower facet
HALO = (255, 214, 120)                # Hover glow around the medallion

_textbar_art = []   # Process-wide cropped TextBar (decoding the PNG costs ~40 ms)


def _textbar():
    """TextBar.png cropped to its opaque body, or None if it is missing."""
    if not _textbar_art:
        raw = load_cached_image(TEXTBAR_PATH, alpha=True)
        _textbar_art.append(crop_to_opaque(raw, threshold=128) if raw else None)
    return _textbar_art[0]


class MapTopBar:
    """The setup screens' map top bar (see module docstring). One per screen."""

    ELEMENTS = ('randomize', 'prev', 'name', 'next', 'borders')

    def __init__(self, scale=1.0):
        self.scale = scale or 1.0
        self.frames = SetupFrames(self.scale)
        self.area = (0, 0)          # (x, width) of the map panel
        self.band_h = 0             # Height of the wooden strip above the map
        self.can_change_map = True  # Arrows shown + name clickable (host / Custom Game)
        self.randomize_enabled = True  # False: greyed (multiplayer client)
        self.map_names = []
        self.hovered = None
        self._flash = (None, 0)     # (element, ticks) of the last click
        self._layout = None
        self._layout_key = None
        self._fonts = {}
        self._text = {}
        self._sprites = {}

    # ------------------------------------------------------------------ setup

    def set_geometry(self, area_x, area_w, band_h):
        """Where the bar lives: the map panel's x / width and the strip's height (the
        map's top edge). Called from the screens' _initialize_map()."""
        self.area = (int(area_x), int(area_w))
        self.band_h = int(band_h)
        # Fixed name bar width from the longest map name: the arrows never move
        self.map_names = [map_data.get_map_display_name(mid) for mid in map_data.get_map_ids()]

    def configure(self, can_change_map=True, randomize_enabled=True):
        """Who may do what: map arrows / name click, and whether Randomize works."""
        self.can_change_map = bool(can_change_map)
        self.randomize_enabled = bool(randomize_enabled)

    def is_enabled(self, element):
        if element == 'randomize':
            return self.randomize_enabled
        if element in ('prev', 'next', 'name'):
            return self.can_change_map
        return element == 'borders'

    # ------------------------------------------------------------------ fonts / text

    def _font(self, path, px):
        key = (path, int(px))
        font = self._fonts.get(key)
        if font is None:
            try:
                font = pygame.font.Font(path, int(px))
            except (FileNotFoundError, pygame.error, OSError) as exc:
                logger.warning(f"Map top bar font {path} fell back to default: {exc}")
                font = pygame.font.Font(None, int(px))
            self._fonts[key] = font
        return font

    def _render_text(self, path, px, text, color):
        key = (path, int(px), text, tuple(color))
        surf = self._text.get(key)
        if surf is None:
            surf = self._font(path, px).render(text, True, color)
            if len(self._text) > 64:
                self._text.clear()
            self._text[key] = surf
        return surf

    # ------------------------------------------------------------------ layout

    def _line_gap(self, px):
        """Space between two label lines (between their ink, not their line boxes)."""
        return max(1, int(round(px * 0.15)))

    def _ink(self, px, text):
        """Bounding rect of the visible glyphs of `text` in its rendered surface. Labels
        are placed by their ink: Cinzel's line box has a lot of empty room above and
        below its capitals, and two lines only fit the button stacked by ink."""
        return self._render_text(FONT_SEMIBOLD, px, text, LABEL_COLOR).get_bounding_rect()

    def _lines_height(self, lines, px):
        return sum(self._ink(px, t).h for t in lines) + self._line_gap(px) * (len(lines) - 1)

    def _fit_labels(self, text_h, inset, room, band):
        """(Randomize label lines, font px) for both buttons.

        Two lines at the biggest size up to ~20% of the strip that fits the button's
        height (`text_h`) and the `room` beside the selector, never below
        MIN_TWO_LINE_PX. A strip too low for two lines falls back to one line: the full
        label, then RANDOMIZE_LABEL_SHORT below MIN_LABEL_PX.
        """
        def width(lines, px):
            font = self._font(FONT_SEMIBOLD, px)
            return max(font.size(t)[0] for t in tuple(lines) + (BORDERS_LABEL,)) + 2 * inset

        px0 = max(MIN_TWO_LINE_PX, int(round(band * 0.2)))
        tries = [(RANDOMIZE_LINES, px) for px in range(px0, MIN_TWO_LINE_PX - 1, -1)]
        px0 = max(MIN_LABEL_PX, int(round(band * 0.25)))
        tries += [((RANDOMIZE_LABEL,), px) for px in range(px0, MIN_LABEL_PX - 1, -1)]
        tries += [((RANDOMIZE_LABEL_SHORT,), px) for px in range(px0, 8, -1)]
        for lines, px in tries:
            if self._lines_height(lines, px) <= text_h and width(lines, px) <= room:
                return tuple(lines), px
        logger.warning(f"Map top bar: buttons do not fit beside the map selector "
                       f"({self.area[1]} px wide panel, {band} px strip)")
        return tuple(tries[-1][0]), tries[-1][1]

    def layout(self):
        """Every rect of the bar (cached until the geometry / permissions change).

        Sizes follow the strip's height. The two buttons share one width and one font
        size; Randomize's label is on two lines (see _fit_labels()). The centre selector
        is centred on the map panel.

        Returns a dict: rects 'randomize', 'borders', 'name' (the whole TextBar),
        'name_window' (its dark window), 'prev' / 'next' (None without arrows), plus
        'label_lines' (Randomize's label, one tuple entry per line), 'label_px',
        'name_px'.
        """
        key = (self.area, self.band_h, self.can_change_map, tuple(self.map_names))
        if self._layout is not None and self._layout_key == key:
            return self._layout

        area_x, area_w = self.area
        band = max(24, self.band_h)
        cy = int(round(band * 0.38))              # Centre line, inside the visible wood
        h = max(24, int(round(band * 0.68)))      # Button height: room for two label lines
        margin = max(8, int(round(band * 0.21)))  # From the map panel's edges
        gap = max(6, int(round(band * 0.18)))     # Between a button and the selector
        d = int(round(band * 0.54))               # Medallion diameter
        arrow_gap = max(2, int(round(d * 0.12)))  # Medallion to the bar's spear tip
        nb = int(round(band * 0.75))              # Name bar height
        inset = self.frames.button_inset(h)
        # Label room inside the beams, 1 px of air above and below
        text_h = h - 2 * self.frames.button_beam(h) - 2

        art = _textbar()
        art_w, art_h = art.get_size() if art else (1438, 170)
        k = nb / float(art_h)
        cap = int(round(TEXTBAR_CAP * k))
        name_pad = max(4, int(round(nb * 0.12)))
        name_px = max(10, int(round(nb * 0.36)))
        names = self.map_names or ['']
        name_w = max(self._font(FONT_BOLD, name_px).size(n)[0] for n in names)
        bar_w = name_w + 2 * cap + 2 * name_pad
        centre_w = bar_w + (2 * (d + arrow_gap) if self.can_change_map else 0)
        room = (area_w - centre_w) // 2 - margin - gap   # Widest a side button may be

        # Both buttons: one font size, one width (the widest label line)
        lines, label_px = self._fit_labels(text_h, inset, room, band)
        font = self._font(FONT_SEMIBOLD, label_px)
        button_w = max(font.size(t)[0] for t in lines + (BORDERS_LABEL,)) + 2 * inset

        top = cy - h // 2
        centre_x = area_x + area_w // 2
        name = pygame.Rect(centre_x - bar_w // 2, cy - nb // 2, bar_w, nb)
        wl, wt, wr, wb = TEXTBAR_WINDOW
        out = {
            'randomize': pygame.Rect(area_x + margin, top, button_w, h),
            'borders': pygame.Rect(area_x + area_w - margin - button_w, top, button_w, h),
            'name': name,
            'name_window': pygame.Rect(name.x + int(round(wl * k)), name.y + int(round(wt * k)),
                                       bar_w - int(round(wl * k)) - int(round((art_w - wr) * k)),
                                       int(round((wb - wt) * k))),
            'prev': None,
            'next': None,
            'label_lines': lines,
            'label_px': label_px,
            'name_px': name_px,
        }
        if self.can_change_map:
            out['prev'] = pygame.Rect(name.left - arrow_gap - d, cy - d // 2, d, d)
            out['next'] = pygame.Rect(name.right + arrow_gap, cy - d // 2, d, d)

        self._layout, self._layout_key = out, key
        return out

    # ------------------------------------------------------------------ input

    def element_at(self, pos):
        """The control under `pos` (shown ones only), or None."""
        lay = self.layout()
        for element in self.ELEMENTS:
            rect = lay.get(element)
            if rect is not None and rect.collidepoint(pos):
                return element
        return None

    def update_hover(self, pos):
        self.hovered = self.element_at(pos)

    def clear_hover(self):
        """Nothing hovered (a modal window covers the bar)."""
        self.hovered = None

    def handle_click(self, pos):
        """Left click. Returns the element clicked ('randomize', 'prev', 'next', 'name',
        'borders') for the screen to act on, BLOCKED for a control this player may not
        use, or None when the click missed the bar."""
        element = self.element_at(pos)
        if element is None:
            return None
        if not self.is_enabled(element):
            return BLOCKED
        from global_sound import sound_manager
        sound_manager.play_ui_click()
        self._flash = (element, pygame.time.get_ticks())
        return element

    def is_flashing(self, element):
        name, ticks = self._flash
        return name == element and pygame.time.get_ticks() - ticks < FLASH_MS

    def state(self, element):
        """'disabled' / 'flash' / 'hover' / 'normal' for drawing `element`."""
        if not self.is_enabled(element):
            return 'disabled'
        if self.is_flashing(element):
            return 'flash'
        return 'hover' if self.hovered == element else 'normal'

    def tooltip_key(self):
        """config/setup_tooltips.py key for the hovered control, or None."""
        if self.hovered == 'randomize':
            return 'randomize_starts' if self.randomize_enabled else 'randomize_starts_host_only'
        return None

    # ------------------------------------------------------------------ sprites

    def _button(self, rect, lines, px, state, lit):
        """Wood button with its label, one or more centred lines (cached per look)."""
        key = ('button', rect.size, tuple(lines), px, state, lit)
        surf = self._sprites.get(key)
        if surf is None:
            surf = self.frames.wood_button(rect.size, state, lit).copy()
            if state == 'disabled':
                color = LABEL_COLOR_DISABLED
            else:
                color = LABEL_COLOR_LIT if lit else LABEL_COLOR
            # Lines stacked by their ink (see _ink()), the block centred in the button
            inks = [self._ink(px, line) for line in lines]
            gap = self._line_gap(px)
            y = (rect.h - (sum(ink.h for ink in inks) + gap * (len(lines) - 1))) // 2
            for line, ink in zip(lines, inks):
                text = self._render_text(FONT_SEMIBOLD, px, line, color)
                surf.blit(text, ((rect.w - ink.w) // 2 - ink.x, y - ink.y))
                y += ink.h + gap
            self._sprites[key] = surf
        return surf

    def _name_bar(self, size, state):
        """TextBar.png at `size`: end caps kept whole, the straight middle stretched."""
        key = ('bar', size, state)
        surf = self._sprites.get(key)
        if surf is None:
            w, h = size
            art = _textbar()
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            if art is None:
                # Missing art: a plain dark bar with a gold edge
                pygame.draw.rect(surf, (24, 18, 12), surf.get_rect(), border_radius=4)
                pygame.draw.rect(surf, GOLD, surf.get_rect(), 2, border_radius=4)
            else:
                art_w, art_h = art.get_size()
                cap = min(w // 2, int(round(TEXTBAR_CAP * h / float(art_h))))
                pieces = (
                    (pygame.Rect(0, 0, TEXTBAR_CAP, art_h), 0, cap),
                    (pygame.Rect(TEXTBAR_CAP, 0, art_w - 2 * TEXTBAR_CAP, art_h), cap, w - 2 * cap),
                    (pygame.Rect(art_w - TEXTBAR_CAP, 0, TEXTBAR_CAP, art_h), w - cap, cap),
                )
                for src, x, width in pieces:
                    if width > 0:
                        surf.blit(pygame.transform.smoothscale(art.subsurface(src), (width, h)), (x, 0))
            if state in _STATE_ADD:
                add = _STATE_ADD[state]
                surf.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
            self._sprites[key] = surf
        return surf

    def _medallion(self, d, direction, state):
        """Round arrow button, `d` px across, pointing left (-1) or right (+1).

        Drawn 4x larger and scaled down (pygame's shapes are not anti-aliased). The
        sprite has `pad` px of room around the disc for the hover halo; it is blitted at
        rect.topleft - pad.
        """
        key = ('arrow', d, direction, state)
        surf = self._sprites.get(key)
        if surf is not None:
            return surf
        ss = 4
        pad = self.medallion_pad(d)
        full = d + 2 * pad
        big = pygame.Surface((full * ss, full * ss), pygame.SRCALPHA)
        c = full * ss / 2.0
        r = d * ss / 2.0

        if state in ('hover', 'flash'):
            # Soft gold halo: rings from faint (outside) to stronger (at the rim)
            rings = 10
            for i in range(rings):
                t = i / float(rings - 1)
                radius = r + pad * ss * (1.0 - t)
                pygame.draw.circle(big, (*HALO, int(12 + 70 * t)), (c, c), radius)

        # Rim: dark outline, then gold slightly raised (darker lower edge = bevel)
        pygame.draw.circle(big, MEDALLION_OUTLINE, (c, c), r)
        pygame.draw.circle(big, GOLD_DARK, (c, c), r * 0.93)
        pygame.draw.circle(big, GOLD, (c, c - r * 0.03), r * 0.86)
        # Light catching the upper rim
        arc = pygame.Rect(0, 0, int(r * 1.62), int(r * 1.62))
        arc.center = (c, c - r * 0.03)
        pygame.draw.arc(big, GOLD_LIGHT, arc, 0.35, 2.8, max(1, int(r * 0.07)))

        # Dark disc with a vertical gradient, then its inner edge
        inner = r * 0.70
        top_y = int(c - inner)
        rows = max(1, int(2 * inner))
        for i in range(rows):
            y = top_y + i
            dy = y + 0.5 - c
            half = (inner * inner - dy * dy) ** 0.5 if abs(dy) < inner else 0
            if half <= 0:
                continue
            t = i / float(rows)
            color = tuple(int(MEDALLION_DISC_TOP[j] + (MEDALLION_DISC_BOTTOM[j] - MEDALLION_DISC_TOP[j]) * t)
                          for j in range(3))
            pygame.draw.line(big, color, (c - half, y), (c + half, y))
        pygame.draw.circle(big, MEDALLION_OUTLINE, (c, c), inner, max(1, int(r * 0.05)))

        # Faceted chevron pointing right (flipped for left), nudged to its optical centre
        nudge = r * 0.05
        tip = (c + r * 0.50 + nudge, c)
        back_top = (c - r * 0.27 + nudge, c - r * 0.46)
        back_bottom = (c - r * 0.27 + nudge, c + r * 0.46)
        back_mid = (c - r * 0.12 + nudge, c)
        pygame.draw.polygon(big, CHEVRON_LIGHT, [tip, back_top, back_mid])
        pygame.draw.polygon(big, CHEVRON_DARK, [tip, back_mid, back_bottom])
        pygame.draw.polygon(big, MEDALLION_OUTLINE, [tip, back_top, back_mid, back_bottom],
                            max(1, int(r * 0.06)))

        if direction < 0:
            big = pygame.transform.flip(big, True, False)
        surf = pygame.transform.smoothscale(big, (full, full))
        if state in _STATE_ADD:
            add = _STATE_ADD[state]
            surf.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
        self._sprites[key] = surf
        return surf

    @staticmethod
    def medallion_pad(d):
        """Room around a medallion sprite for its hover halo."""
        return max(3, int(round(d * 0.28)))

    # ------------------------------------------------------------------ drawing

    def draw(self, screen, map_name, borders_on):
        """Draw the bar. `borders_on`: Show Borders glows while True."""
        lay = self.layout()
        px = lay['label_px']
        for element, lines, lit in (('randomize', lay['label_lines'], False),
                                    ('borders', (BORDERS_LABEL,), bool(borders_on))):
            rect = lay[element]
            screen.blit(self._button(rect, lines, px, self.state(element), lit), rect.topleft)

        # Map name on the TextBar; it only reacts when a click changes the map
        name_rect = lay['name']
        name_state = self.state('name') if self.can_change_map else 'normal'
        screen.blit(self._name_bar(name_rect.size, name_state), name_rect.topleft)
        text = self._render_text(FONT_BOLD, lay['name_px'], map_name, NAME_COLOR)
        window = lay['name_window']
        screen.blit(text, text.get_rect(center=(window.centerx, window.centery + 1)))

        for element, direction in (('prev', -1), ('next', 1)):
            rect = lay[element]
            if rect is None:
                continue
            sprite = self._medallion(rect.w, direction, self.state(element))
            pad = self.medallion_pad(rect.w)
            screen.blit(sprite, (rect.x - pad, rect.y - pad))
