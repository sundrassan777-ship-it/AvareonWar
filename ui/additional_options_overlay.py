# -*- coding: utf-8 -*-
"""
Additional Options window — shared by the Custom Game setup (integrated_setup.py) and
the multiplayer lobby (network/territory_selector.py).

The two screens used to carry near-identical copies of this modal (~200 lines each),
with the title and the Cancel / Confirm buttons drawn on top of the InGameMenuBG frame.
This module owns the window instead:

- Layout is measured from the frame's INNER edge, so the title, both separators, the
  option rows and the buttons always sit inside the carved border. The window height
  is derived from the rows (no scrolling: everything fits from 1280x720 up).
- The background is nine-sliced (corners keep their proportions however tall the
  window gets) and every surface / font / label is cached, not rebuilt each frame.
- Edits go to temporary values; Confirm returns them, Cancel / Escape discards them.
- read_only=True (multiplayer clients) shows the host's choices greyed out with a
  single Close button.

Usage:
    overlay = AdditionalOptionsOverlay(ui_scale, gold_transfer_options)
    overlay.open({'neutral_armies': .., 'randomize_bonuses': .., 'gold_transfer': ..})
    result = overlay.handle_click(pos)      # 'confirm' | 'cancel' | None
    if result == 'confirm': apply(overlay.values)
"""

import pygame

from rendering.sidebar_widgets import render_nine_slice
from utils.surface_utils import load_cached_image
from utils.logger import get_logger

logger = get_logger(__name__)

# Palette (matches the setup screens)
TEXT_COLOR = (255, 255, 255)
TEXT_DISABLED = (150, 150, 150)
BRASS_COLOR = (181, 166, 66)
PANEL_BG = (40, 40, 50)
PARCHMENT_COLOR = (62, 54, 38)
PARCHMENT_HOVER = (72, 64, 48)
PARCHMENT_CLICK = (92, 84, 68)
CHECK_COLOR = (100, 200, 100)
ITEM_HOVER = (123, 157, 216)    # lighten_color(BUTTON_COLOR (70, 120, 200), 0.3)
GRAY = (128, 128, 128)

# InGameMenuBG.png (865x722): the straight part of the carved frame is ~62 px thick;
# the corner ornaments reach ~112 px in. Slicing at 112 keeps the ornaments whole.
BG_PATH = 'assets/InGameMenuBG.png'
BG_SOURCE_WIDTH = 865
BG_SLICE = 112
BG_FRAME = 62
BUTTON_PATH = 'assets/GMenuButton.png'

FONT_REGULAR = 'assets/fonts/Cinzel-Regular.ttf'
FONT_SEMIBOLD = 'assets/fonts/Cinzel-SemiBold.ttf'

FLASH_MS = 120   # Click flash length

# Option rows, top to bottom: (key, control, label lines)
ROWS = (
    ('neutral_armies', 'checkbox', ("Neutral Armies:",)),
    ('randomize_bonuses', 'checkbox', ("Randomize Territory", "Bonuses:")),
    ('gold_transfer', 'dropdown', ("Gold Transfer:",)),
)


class AdditionalOptionsOverlay:
    """Modal Additional Options window (see module docstring)."""

    def __init__(self, ui_scale, gold_transfer_options):
        self.scale = ui_scale or 1.0
        self.gold_transfer_options = list(gold_transfer_options)
        self.is_open = False
        self.read_only = False
        self.values = {}
        self.dropdown_open = False
        self.hovered = None
        self.rects = {}             # Hit rects from the last layout (also read by tests)
        self._flash = (None, 0)     # (element, ticks) of the last click
        self._layout_cache = {}     # screen size -> layout dict
        self._fonts = {}
        self._text = {}
        self._sprites = {}

    # ------------------------------------------------------------------ state

    def open(self, values, read_only=False):
        """Show the window with a copy of `values` to edit."""
        self.values = dict(values)
        self.read_only = read_only
        self.is_open = True
        self.dropdown_open = False
        self.hovered = None

    def close(self):
        self.is_open = False
        self.dropdown_open = False
        self.hovered = None

    def _flash_on(self, element):
        self._flash = (element, pygame.time.get_ticks())

    def is_flashing(self, element):
        name, ticks = self._flash
        return name == element and pygame.time.get_ticks() - ticks < FLASH_MS

    # ------------------------------------------------------------------ fonts / text

    def _font(self, path, base_px, minimum):
        size = max(minimum, int(base_px * self.scale))
        key = (path, size)
        font = self._fonts.get(key)
        if font is None:
            try:
                font = pygame.font.Font(path, size)
            except (FileNotFoundError, pygame.error, OSError) as exc:
                logger.warning(f"Additional Options font {path} fell back to default: {exc}")
                font = pygame.font.Font(None, size)
            self._fonts[key] = font
        return font

    def _title_font(self):
        return self._font(FONT_SEMIBOLD, 26, 16)

    def _label_font(self):
        return self._font(FONT_REGULAR, 20, 13)

    def _small_font(self):
        return self._font(FONT_REGULAR, 16, 11)

    def _button_font(self):
        return self._font(FONT_REGULAR, 22, 14)

    def _render(self, font, text, color):
        key = (id(font), text, color)
        surf = self._text.get(key)
        if surf is None:
            surf = font.render(text, True, color)
            if len(self._text) > 200:
                self._text.clear()
            self._text[key] = surf
        return surf

    # ------------------------------------------------------------------ layout

    def layout(self, screen_size):
        """Every rect of the window for this screen size (cached).

        Measured top-down from the frame's inner edge, so nothing can land on the
        border; the window height is whatever the rows need.
        """
        cached = self._layout_cache.get(tuple(screen_size))
        if cached is not None:
            return cached

        s = self.scale
        screen_w, screen_h = screen_size
        panel_w = int(round(440 * s))
        k = panel_w / BG_SOURCE_WIDTH                      # art -> screen scale
        frame = int(round(BG_FRAME * k))                   # carved border thickness on screen
        pad_x = int(round(26 * s))
        pad_y = int(round(16 * s))

        label_font = self._label_font()
        line_h = label_font.get_height()
        line_gap = int(round(3 * s))
        cb_size = int(round(22 * s))
        dd_w, dd_h = int(round(150 * s)), int(round(28 * s))
        row_gap = int(round(18 * s))
        btn_w, btn_h = int(round(140 * s)), int(round(42 * s))
        btn_gap = int(round(20 * s))

        # Heights first (positions are relative to the panel top, offset below)
        y = frame + pad_y
        title_top = y
        y += self._title_font().get_height()
        sep1_y = y + int(round(12 * s))
        y = sep1_y + int(round(20 * s))
        rows = []
        for key, control, lines in ROWS:
            text_h = len(lines) * line_h + (len(lines) - 1) * line_gap
            control_h = cb_size if control == 'checkbox' else dd_h
            row_h = max(text_h, control_h)
            rows.append((key, control, lines, y, row_h, text_h, control_h))
            y += row_h + row_gap
        y -= row_gap
        sep2_y = y + int(round(20 * s))
        btn_top = sep2_y + int(round(18 * s))
        panel_h = btn_top + btn_h + pad_y + frame

        panel = pygame.Rect((screen_w - panel_w) // 2, (screen_h - panel_h) // 2, panel_w, panel_h)
        inner = pygame.Rect(panel.x + frame, panel.y + frame, panel_w - 2 * frame, panel_h - 2 * frame)
        content = inner.inflate(-2 * pad_x, -2 * pad_y)

        out = {
            'panel': panel,
            'inner': inner,
            'content': content,
            'title_top': panel.y + title_top,
            'sep1_y': panel.y + sep1_y,
            'sep2_y': panel.y + sep2_y,
            'rows': [],
        }
        for key, control, lines, row_y, row_h, text_h, control_h in rows:
            top = panel.y + row_y
            if control == 'checkbox':
                ctrl = pygame.Rect(content.right - cb_size, top + (row_h - cb_size) // 2, cb_size, cb_size)
            else:
                ctrl = pygame.Rect(content.right - dd_w, top + (row_h - dd_h) // 2, dd_w, dd_h)
            out['rows'].append({
                'key': key, 'control': control, 'lines': lines,
                'label_pos': (content.x, top + (row_h - text_h) // 2),
                'line_step': line_h + line_gap,
                'label_rect': pygame.Rect(content.x, top, ctrl.x - content.x, row_h),
                'control_rect': ctrl,
            })

        btn_y = panel.y + btn_top
        pair_w = 2 * btn_w + btn_gap
        out['cancel'] = pygame.Rect(panel.centerx - pair_w // 2, btn_y, btn_w, btn_h)
        out['confirm'] = pygame.Rect(out['cancel'].right + btn_gap, btn_y, btn_w, btn_h)
        out['close'] = pygame.Rect(panel.centerx - btn_w // 2, btn_y, btn_w, btn_h)

        self._layout_cache[tuple(screen_size)] = out
        return out

    def _update_rects(self, screen_size):
        """Hit rects for the current mode (read-only has only Close)."""
        lay = self.layout(screen_size)
        rects = {row['key']: row['control_rect'] for row in lay['rows']}
        if self.read_only:
            rects['close_btn'] = lay['close']
        else:
            rects['cancel_btn'] = lay['cancel']
            rects['confirm_btn'] = lay['confirm']
            if self.dropdown_open:
                dd = rects['gold_transfer']
                for i in range(len(self.gold_transfer_options)):
                    rects[f'gold_transfer_item_{i}'] = pygame.Rect(dd.x, dd.bottom + i * dd.h, dd.w, dd.h)
        self.rects = rects
        return lay

    # ------------------------------------------------------------------ input

    def update_hover(self, pos, screen_size=None):
        self.hovered = None
        if not self.is_open:
            return
        self._update_rects(screen_size or pygame.display.get_surface().get_size())
        # Open list items win over whatever they cover
        for name, rect in self.rects.items():
            if name.startswith('gold_transfer_item_') and rect.collidepoint(pos):
                self.hovered = name
                return
        for name, rect in self.rects.items():
            if rect.collidepoint(pos):
                self.hovered = name
                return

    def handle_click(self, pos, screen_size=None):
        """Click while open. Returns 'confirm', 'cancel' or None. Never falls through."""
        if not self.is_open:
            return None
        self._update_rects(screen_size or pygame.display.get_surface().get_size())

        if self.read_only:
            if self.rects['close_btn'].collidepoint(pos):
                self._click('close_btn')
                self.close()
                return 'cancel'
            return None

        # Open gold-transfer list: pick an item, or any other click just closes it
        if self.dropdown_open:
            for i in range(len(self.gold_transfer_options)):
                if self.rects[f'gold_transfer_item_{i}'].collidepoint(pos):
                    self._click(f'gold_transfer_item_{i}')
                    self.values['gold_transfer'] = i
                    break
            self.dropdown_open = False
            return None

        for key, control, _ in ROWS:
            if self.rects[key].collidepoint(pos):
                self._click(key)
                if control == 'checkbox':
                    self.values[key] = not self.values.get(key, False)
                elif control == 'dropdown':
                    self.dropdown_open = True
                    self._update_rects(screen_size or pygame.display.get_surface().get_size())
                return None

        if self.rects['confirm_btn'].collidepoint(pos):
            self._click('confirm_btn')
            self.close()
            return 'confirm'
        if self.rects['cancel_btn'].collidepoint(pos):
            self._click('cancel_btn')
            self.close()
            return 'cancel'
        return None   # Clicks elsewhere are swallowed (modal)

    def handle_key(self, event):
        """KEYDOWN while open. Escape closes the list first, then the window (= Cancel)."""
        if not self.is_open or event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            if self.dropdown_open:
                self.dropdown_open = False
                return None
            self.close()
            return 'cancel'
        return None

    def _click(self, element):
        from global_sound import sound_manager
        sound_manager.play_ui_click()
        self._flash_on(element)

    # ------------------------------------------------------------------ drawing

    def _dim_surface(self, size):
        key = ('dim', size)
        surf = self._sprites.get(key)
        if surf is None:
            surf = pygame.Surface(size)
            surf.set_alpha(180)
            surf.fill((0, 0, 0))
            self._sprites[key] = surf
        return surf

    def _background(self, panel):
        key = ('bg', panel.size)
        surf = self._sprites.get(key)
        if surf is None:
            image = load_cached_image(BG_PATH, alpha=True)
            if image is None:
                surf = pygame.Surface(panel.size)
                surf.fill(PANEL_BG)
                pygame.draw.rect(surf, BRASS_COLOR, surf.get_rect(), 2)
            else:
                corner = int(round(BG_SLICE * panel.w / BG_SOURCE_WIDTH))
                surf = render_nine_slice(image, (BG_SLICE,) * 4, panel.size, corner, keep_middle=True)
            self._sprites[key] = surf
        return surf

    def _button(self, size, state):
        key = ('btn', size, state)
        surf = self._sprites.get(key)
        if surf is None:
            image = load_cached_image(BUTTON_PATH, alpha=True)
            if image is None:
                surf = pygame.Surface(size, pygame.SRCALPHA)
                fill = {'flash': PARCHMENT_CLICK, 'hover': PARCHMENT_HOVER}.get(state, PARCHMENT_COLOR)
                pygame.draw.rect(surf, fill, surf.get_rect(), border_radius=5)
                pygame.draw.rect(surf, BRASS_COLOR, surf.get_rect(), 2, border_radius=5)
            else:
                # Same treatment as the old overlay: darken, then brighten for hover / click
                surf = pygame.transform.smoothscale(image, size)
                surf.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
                add = {'hover': 40, 'flash': 80}.get(state, 0)
                if add:
                    surf.fill((add, add, add, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self._sprites[key] = surf
        return surf

    def _state(self, element):
        if self.is_flashing(element):
            return 'flash'
        return 'hover' if self.hovered == element else 'normal'

    def draw(self, screen):
        if not self.is_open:
            return
        size = screen.get_size()
        lay = self._update_rects(size)
        panel = lay['panel']

        screen.blit(self._dim_surface(size), (0, 0))
        screen.blit(self._background(panel), panel.topleft)

        # Title, well inside the top border, with a brass rule under it
        title = self._render(self._title_font(), "Additional Options", TEXT_COLOR)
        screen.blit(title, title.get_rect(centerx=panel.centerx, top=lay['title_top']))
        content = lay['content']
        for sep_y in (lay['sep1_y'], lay['sep2_y']):
            pygame.draw.line(screen, BRASS_COLOR, (content.x, sep_y), (content.right, sep_y), 1)

        text_color = TEXT_DISABLED if self.read_only else TEXT_COLOR
        label_font = self._label_font()
        for row in lay['rows']:
            x, y = row['label_pos']
            for line in row['lines']:
                screen.blit(self._render(label_font, line, text_color), (x, y))
                y += row['line_step']
            key, rect = row['key'], row['control_rect']
            active = not self.read_only and (self.hovered == key or (key == 'gold_transfer' and self.dropdown_open))
            if row['control'] == 'checkbox':
                self._draw_checkbox(screen, rect, self.values.get(key, False), active)
            else:
                index = max(0, min(self.values.get(key, 0), len(self.gold_transfer_options) - 1))
                self._draw_dropdown(screen, rect, self.gold_transfer_options[index], active, text_color)

        # Buttons, inside the frame below the second rule
        button_font = self._button_font()
        names = (('close_btn', 'close', "Close"),) if self.read_only else (
            ('cancel_btn', 'cancel', "Cancel"), ('confirm_btn', 'confirm', "Confirm"))
        for element, lay_key, label in names:
            rect = lay[lay_key]
            screen.blit(self._button(rect.size, self._state(element)), rect.topleft)
            text = self._render(button_font, label, TEXT_COLOR)
            screen.blit(text, text.get_rect(center=rect.center))

        # Open list last so it covers the buttons when it reaches that far
        if self.dropdown_open and not self.read_only:
            self._draw_dropdown_items(screen)

    def _draw_checkbox(self, screen, rect, checked, hovered):
        bg = (66, 66, 74) if hovered else (52, 52, 61)   # lighten_color(PANEL_BG, 0.3 / 0.1)
        pygame.draw.rect(screen, bg, rect, border_radius=3)
        border = TEXT_DISABLED if self.read_only else TEXT_COLOR
        pygame.draw.rect(screen, border, rect, 1, border_radius=3)
        if checked:
            color = (90, 130, 90) if self.read_only else CHECK_COLOR
            pygame.draw.line(screen, color, (rect.x + 4, rect.y + 4), (rect.right - 4, rect.bottom - 4), 2)
            pygame.draw.line(screen, color, (rect.right - 4, rect.y + 4), (rect.x + 4, rect.bottom - 4), 2)

    def _draw_dropdown(self, screen, rect, label, hovered, text_color):
        bg = (66, 66, 74) if hovered else (56, 56, 66)   # lighten_color(PANEL_BG, 0.3 / 0.15)
        pygame.draw.rect(screen, bg, rect, border_radius=4)
        pygame.draw.rect(screen, BRASS_COLOR, rect, 1, border_radius=4)
        s = self.scale
        text = self._render(self._small_font(), label, text_color)
        screen.blit(text, text.get_rect(midleft=(rect.x + int(8 * s), rect.centery)))
        if not self.read_only:
            a = int(4 * s)
            pygame.draw.polygon(screen, text_color, [
                (rect.right - int(12 * s), rect.centery - a),
                (rect.right - int(6 * s), rect.centery),
                (rect.right - int(12 * s), rect.centery + a),
            ])

    def _draw_dropdown_items(self, screen):
        font = self._small_font()
        for i, option in enumerate(self.gold_transfer_options):
            rect = self.rects[f'gold_transfer_item_{i}']
            hovered = self.hovered == f'gold_transfer_item_{i}'
            pygame.draw.rect(screen, ITEM_HOVER if hovered else PARCHMENT_COLOR, rect, border_radius=3)
            pygame.draw.rect(screen, BRASS_COLOR if hovered else GRAY, rect, 1, border_radius=3)
            text = self._render(font, option, TEXT_COLOR)
            screen.blit(text, text.get_rect(midleft=(rect.x + int(8 * self.scale), rect.centery)))
