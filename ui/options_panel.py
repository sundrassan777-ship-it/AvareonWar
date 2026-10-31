# -*- coding: utf-8 -*-
"""
The main menu's Options window (Menu Glow-up, agreed with the owner 2026-10-30):
Display / Gameplay / Audio tabs, one row per setting with a one-line explanation
(config/options_hints.py) and its control:

- switch: on / off (clicking the row's name toggles it too)
- arrows: steps through a list (Resolution, FPS Limit, Tooltip Delay)
- choice: one of two (Map Look 2D / 3D, Scroll From)
- slider: a range with its value on the same line (speeds; volumes preview live)

A row that depends on another dims and ignores clicks while that one is off (Scroll From,
Tooltip Delay) instead of disappearing, so rows never jump; FPS Limit reads "Set by
VSync" while VSync is on.

The window edits MainMenu's pending values (its temp_* attributes): Apply, Cancel, Reset to
Defaults, the live volume preview and the display re-creation stay in MainMenu. Geometry
is computed once per tab (_layout()) and shared by drawing and hit-testing.
"""

import pygame

from config.constants import (CLICK_FLASH_DURATION_MS, FPS_LIMIT_OPTIONS, MAP_3D_AVAILABLE,
                              CAMERA_ZOOM_SPEED_MIN, CAMERA_ZOOM_SPEED_MAX)
from config.options_hints import OPTION_HINTS
from global_sound import sound_manager
from rendering.sidebar_widgets import PARCHMENT, PARCHMENT_DIM
from rendering.bottom_panel_kit import GOLD_TEXT
from ui.menu_kit import WindowAnim, PARCHMENT_FAINT, WARN, CHOICE_ON_TEXT

TABS = (('display', "Display"), ('gameplay', "Gameplay"), ('audio', "Audio"))
TOOLTIP_DELAYS = (300, 500, 700, 1000, -1)       # ms; -1 = never (as before)
PAN_SPEED_RANGE = (5.0, 20.0)

# Layout, px at 1600x900 (window-local; the window is 1220 x 806 there)
CONTENT_INSET = 28       # Board edge to the content
TABS_TOP = 50            # Board top to the tabs
TAB_SIZE = (196, 50)
TAB_GAP = 14
RULE_GAP = 16            # Tabs to the gold rule
ROWS_GAP = 14            # Rule to the first row
ROW_HEIGHT = 70
ROW_PAD = 16             # Inside a row, to its name and its control column
CONTROL_COLUMN = 400
SUB_INDENT = 30          # A dependent row's name, further in
FOOTER_GAP = 16          # Board bottom to the buttons
BUTTON_WIDTH = 230
RESET_WIDTH = 270
BUTTON_GAP = 14
SWITCH_SIZE = (64, 30)
ARROWS_SIZE = (290, 40)
ARROW_WIDTH = 40
CHOICE_HEIGHT = 40
CHOICE_PAD = 18          # Each side of a choice's label
CHOICE_INSET = 3
SLIDER_SIZE = (290, 8)
KNOB = 22
VALUE_WIDTH = 58         # A slider's value, right-aligned in this


def _percent(value):
    return f"{int(round(value * 100))}%"


class Row:
    """One setting: where it is, what it edits (a MainMenu attribute) and its control."""

    def __init__(self, key, tab, label, kind, attr, values=None, labels=None, span=None,
                 fmt=None, depends=None, locked_by=None, locked_text=None, audio=False,
                 sub=False):
        self.key = key
        self.tab = tab
        self.label = label
        self.kind = kind            # 'switch' | 'arrows' | 'choice' | 'slider'
        self.attr = attr
        self.values = values        # arrows / choice
        self.labels = labels
        self.span = span            # slider (min, max)
        self.fmt = fmt              # slider value -> text
        self.depends = depends      # attr that must be on for this row to work
        self.locked_by = locked_by  # attr that, when on, replaces the arrows' value
        self.locked_text = locked_text
        self.audio = audio          # previews the volume live while it changes
        self.sub = sub
        self.hint = OPTION_HINTS.get(key, "")


def build_rows(resolutions):
    """Every row the window shows (the Map Look row only while it can be chosen)."""
    rows = [
        Row('resolution', 'display', "Resolution", 'arrows', 'temp_resolution',
            values=[tuple(r) for r in resolutions],
            labels=[f"{w} × {h}" for w, h in resolutions]),
        Row('fullscreen', 'display', "Fullscreen", 'switch', 'temp_fullscreen'),
        Row('vsync', 'display', "VSync", 'switch', 'temp_vsync'),
        Row('fps_limit', 'display', "FPS Limit", 'arrows', 'temp_fps_limit',
            values=list(FPS_LIMIT_OPTIONS),
            labels=[str(f) if f else "Unlimited" for f in FPS_LIMIT_OPTIONS],
            locked_by='temp_vsync', locked_text="Set by VSync"),
        Row('show_fps', 'display', "Show FPS", 'switch', 'temp_show_fps'),
    ]
    if MAP_3D_AVAILABLE:
        rows.append(Row('map_look', 'display', "Map Look", 'choice', 'temp_map_3d',
                        values=[False, True], labels=["2D", "3D"]))
    rows += [
        Row('edge_scrolling', 'gameplay', "Edge Scrolling", 'switch', 'temp_edge_scrolling_enabled'),
        Row('edge_mode', 'gameplay', "Scroll From", 'choice', 'temp_edge_scrolling_mode',
            values=['window_edge', 'map_edge'], labels=["Window Edge", "Map Edge"],
            depends='temp_edge_scrolling_enabled', sub=True),
        Row('tooltips', 'gameplay', "Tooltips", 'switch', 'temp_tooltips_enabled'),
        Row('tooltip_delay', 'gameplay', "Tooltip Delay", 'arrows', 'temp_tooltip_delay_ms',
            values=list(TOOLTIP_DELAYS),
            labels=[f"{d / 1000:.1f} s" if d > 0 else "Never" for d in TOOLTIP_DELAYS],
            depends='temp_tooltips_enabled', sub=True),
        Row('pan_speed', 'gameplay', "Pan Speed", 'slider', 'temp_pan_speed',
            span=PAN_SPEED_RANGE, fmt=lambda v: str(int(round(v)))),
        Row('zoom_speed', 'gameplay', "Zoom Speed", 'slider', 'temp_zoom_speed',
            span=(CAMERA_ZOOM_SPEED_MIN, CAMERA_ZOOM_SPEED_MAX), fmt=_percent),
        Row('master_volume', 'audio', "Master Volume", 'slider', 'temp_master_volume',
            span=(0.0, 1.0), fmt=_percent, audio=True),
        Row('music_volume', 'audio', "Music", 'slider', 'temp_music_volume',
            span=(0.0, 1.0), fmt=_percent, audio=True),
        Row('sfx_volume', 'audio', "Sound Effects", 'slider', 'temp_sfx_volume',
            span=(0.0, 1.0), fmt=_percent, audio=True),
    ]
    return rows


class _Layout:
    """One tab's geometry, window-local px (origin = the window's top-left)."""

    def __init__(self):
        self.size = (0, 0)
        self.tabs = {}           # tab key -> Rect
        self.rule = None         # (x, y, width)
        self.rows = []           # [(row, Rect)]
        self.parts = {}          # element -> Rect (controls)
        self.buttons = {}        # 'reset' | 'cancel' | 'apply' -> Rect
        self.note_right = 0      # The unsaved-changes note ends here


class OptionsPanel:
    """The Options window over a MainMenu (`menu`), drawn with a MenuKit (`kit`)."""

    def __init__(self, menu, kit):
        self.menu = menu
        self.kit = kit
        self.anim = WindowAnim()
        self.rows = build_rows(menu.available_resolutions)
        self.tab = 'display'
        self.hover = None          # The element under the mouse (see element_at())
        self.hover_row = None      # The row under the mouse (its wash)
        self.dragging = None       # The slider row being dragged
        self._flash = None         # (element, until ms)
        self._baseline = {}
        self._layouts = {}

    # ------------------------------------------------------------ open / close

    def prewarm(self):
        """
        Build every tab's sprites now (MainMenu creation), not on the window's first frame:
        cold, that frame took ~85 ms and the drop started with a jump. Cheap once built -
        MenuKit keeps them for the screen size.
        """
        scratch = pygame.Surface(self.rect().size, pygame.SRCALPHA)
        tab = self.tab
        for key, _label in TABS:
            self.tab = key
            self.draw(scratch, 0, 0)
        self.tab = tab
        self.kit.backdrop()

    def open(self):
        """Opened with MainMenu's pending values just read from the settings."""
        self.tab = 'display'
        self.dragging = None
        self.hover = self.hover_row = None
        self._baseline = {row.attr: self._get(row) for row in self.rows}
        self.anim.open()

    def close(self):
        self.dragging = None
        self.anim.close()

    def update(self, dt):
        self.anim.update(dt)

    # ------------------------------------------------------------ values

    def _get(self, row):
        value = getattr(self.menu, row.attr)
        return tuple(value) if isinstance(value, list) else value

    def _set(self, row, value):
        setattr(self.menu, row.attr, value)
        if row.audio:
            self.menu._preview_audio()

    def is_off(self, row):
        """A dependent row whose switch is off: dimmed, clicks ignored."""
        return row.depends is not None and not getattr(self.menu, row.depends)

    def is_locked(self, row):
        """The arrows replaced by a note (FPS Limit while VSync is on)."""
        return row.locked_by is not None and bool(getattr(self.menu, row.locked_by))

    def _index(self, row):
        value = self._get(row)
        try:
            return row.values.index(value)
        except ValueError:
            return 0

    def value_label(self, row):
        """The arrows' text: the value's label, or the value itself when it is not one of the
        choices (a hand-edited config.json - shown as it is until the arrows change it)."""
        value = self._get(row)
        if value in row.values:
            return row.labels[row.values.index(value)]
        if row.key == 'resolution' and isinstance(value, tuple) and len(value) == 2:
            return f"{value[0]} × {value[1]}"
        if row.key == 'tooltip_delay' and isinstance(value, (int, float)) and value > 0:
            return f"{value / 1000:.1f} s"
        return str(value)

    def unsaved(self):
        """How many settings differ from when the window opened."""
        count = 0
        for row in self.rows:
            before, now = self._baseline.get(row.attr), self._get(row)
            if isinstance(now, float) or isinstance(before, float):
                if before is None or abs(float(now) - float(before)) > 1e-6:
                    count += 1
            elif now != before:
                count += 1
        return count

    def tab_rows(self, tab=None):
        tab = tab or self.tab
        return [row for row in self.rows if row.tab == tab]

    # ------------------------------------------------------------ geometry

    def _layout(self, tab=None):
        tab = tab or self.tab
        layout = self._layouts.get(tab)
        if layout is None:
            layout = self._layouts[tab] = self._build_layout(tab)
        return layout

    def _build_layout(self, tab):
        k = self.kit
        px = k.px
        rect = k.window_rect()
        w, h = rect.size
        b = k.border()
        L = _Layout()
        L.size = (w, h)
        inner_x = b + px(CONTENT_INSET)
        inner_w = w - 2 * inner_x

        tab_w, tab_h, gap = px(TAB_SIZE[0]), px(TAB_SIZE[1]), px(TAB_GAP)
        total = len(TABS) * tab_w + (len(TABS) - 1) * gap
        tabs_y = b + px(TABS_TOP)
        for i, (key, _label) in enumerate(TABS):
            L.tabs[key] = pygame.Rect(w // 2 - total // 2 + i * (tab_w + gap), tabs_y, tab_w, tab_h)
        rule_y = tabs_y + tab_h + px(RULE_GAP)
        L.rule = (inner_x, rule_y, inner_w)

        # Footer: Reset to Defaults on the left, Cancel and Apply on the right
        btn_w, btn_h = k.button_size(BUTTON_WIDTH)
        footer_y = h - b - px(FOOTER_GAP) - btn_h
        apply_r = pygame.Rect(inner_x + inner_w - btn_w, footer_y, btn_w, btn_h)
        cancel_r = pygame.Rect(apply_r.x - px(BUTTON_GAP) - btn_w, footer_y, btn_w, btn_h)
        reset_r = pygame.Rect(inner_x, footer_y, px(RESET_WIDTH), btn_h)
        L.buttons = {'reset': reset_r, 'cancel': cancel_r, 'apply': apply_r}
        L.note_right = cancel_r.x - px(16)

        # Rows: one height for every tab (the longest tab must fit above the footer)
        rows_top = rule_y + px(ROWS_GAP)
        longest = max(len(self.tab_rows(key)) for key, _ in TABS)
        room = footer_y - px(12) - rows_top
        row_h = min(px(ROW_HEIGHT), room // max(1, longest))
        control_x = inner_x + inner_w - px(ROW_PAD) - px(CONTROL_COLUMN)
        y = rows_top
        for row in self.tab_rows(tab):
            row_rect = pygame.Rect(inner_x, y, inner_w, row_h)
            L.rows.append((row, row_rect))
            self._control_parts(L, row, row_rect, control_x)
            y += row_h
        return L

    def _control_parts(self, L, row, row_rect, x):
        k = self.kit
        px = k.px
        cy = row_rect.centery
        if row.kind == 'switch':
            sw = pygame.Rect(x, cy - px(SWITCH_SIZE[1]) // 2, px(SWITCH_SIZE[0]), px(SWITCH_SIZE[1]))
            L.parts[('switch', row.key)] = sw
        elif row.kind == 'arrows':
            box = pygame.Rect(x, cy - px(ARROWS_SIZE[1]) // 2, px(ARROWS_SIZE[0]), px(ARROWS_SIZE[1]))
            L.parts[('box', row.key)] = box
            L.parts[('left', row.key)] = pygame.Rect(box.x, box.y, px(ARROW_WIDTH), box.h)
            L.parts[('right', row.key)] = pygame.Rect(box.right - px(ARROW_WIDTH), box.y,
                                                      px(ARROW_WIDTH), box.h)
        elif row.kind == 'choice':
            font = k.font('choice')
            inset = px(CHOICE_INSET)
            h = px(CHOICE_HEIGHT)
            widths = [font.size(label)[0] + 2 * px(CHOICE_PAD) for label in row.labels]
            box = pygame.Rect(x, cy - h // 2, sum(widths) + 2 * inset, h)
            L.parts[('track', row.key)] = box
            sx = box.x + inset
            for i, sw in enumerate(widths):
                L.parts[('choice', row.key, i)] = pygame.Rect(sx, box.y + inset, sw, h - 2 * inset)
                sx += sw
        elif row.kind == 'slider':
            track = pygame.Rect(x, cy - px(SLIDER_SIZE[1]) // 2, px(SLIDER_SIZE[0]), px(SLIDER_SIZE[1]))
            L.parts[('track', row.key)] = track
            # Easy to grab: the knob's height, and half a knob past either end
            L.parts[('slider', row.key)] = track.inflate(px(KNOB), px(KNOB) + px(8))

    # ------------------------------------------------------------ hit-testing

    def _local(self, pos):
        rect = self.kit.window_rect()
        return pos[0] - rect.x, pos[1] - rect.y

    def element_at(self, pos):
        """The control under a screen position: ('tab', key), ('button', key), ('switch', row),
        ('left' | 'right', row), ('choice', row, i), ('slider', row) or ('row', row); else None."""
        L = self._layout()
        x, y = self._local(pos)
        for key, r in L.buttons.items():
            if r.collidepoint(x, y):
                return ('button', key)
        for key, r in L.tabs.items():
            if r.collidepoint(x, y):
                return ('tab', key)
        for row, row_rect in L.rows:
            if not row_rect.collidepoint(x, y):
                continue
            for part, r in L.parts.items():
                if part[1] == row.key and part[0] in ('switch', 'left', 'right', 'choice', 'slider') \
                        and r.collidepoint(x, y):
                    return part
            return ('row', row.key)
        return None

    def update_hover(self, pos):
        """Called every frame with the mouse position (MainMenu.handle_events)."""
        self.hover = self.element_at(pos) if self.anim.interactive else None
        self.hover_row = self.hover[1] if self.hover and self.hover[0] not in ('tab', 'button') else None

    def part_rect(self, element):
        """A control's rect on screen (tests, previews): e.g. ('choice', 'map_look', 0)."""
        L = self._layout()
        r = L.parts.get(element) or (L.tabs.get(element[1]) if element[0] == 'tab' else None) \
            or (L.buttons.get(element[1]) if element[0] == 'button' else None)
        if r is None:
            return None
        rect = self.kit.window_rect()
        return r.move(rect.x, rect.y)

    # ------------------------------------------------------------ input

    def _row(self, key):
        for row in self.rows:
            if row.key == key:
                return row
        return None

    def _click(self, element):
        """Sound and flash for an actionable click."""
        sound_manager.play_ui_click()
        self._flash = (element, pygame.time.get_ticks() + CLICK_FLASH_DURATION_MS)

    def handle_click(self, pos):
        """A left click: returns 'apply' | 'cancel' | 'reset' for MainMenu, else None."""
        if not self.anim.interactive:
            return None
        element = self.element_at(pos)
        if element is None:
            return None
        kind = element[0]
        if kind == 'button':
            self._click(element)
            return element[1]
        if kind == 'tab':
            if element[1] != self.tab:
                self._click(element)
                self.select_tab(element[1])
            return None
        row = self._row(element[1])
        if row is None or self.is_off(row):
            return None
        if kind == 'row':
            # The name of a switch row toggles it too (the rest of a row does nothing)
            if row.kind != 'switch':
                return None
            element = ('switch', row.key)
            kind = 'switch'
        if kind == 'switch':
            self._click(element)
            self._set(row, not self._get(row))
        elif kind in ('left', 'right'):
            if self.is_locked(row):
                return None
            self._click(element)
            step = -1 if kind == 'left' else 1
            self._set(row, row.values[(self._index(row) + step) % len(row.values)])
        elif kind == 'choice':
            if row.values[element[2]] != self._get(row):
                self._click(element)
                self._set(row, row.values[element[2]])
        elif kind == 'slider':
            sound_manager.play_ui_click()
            self.dragging = row.key
            self.drag_to(pos)
        return None

    def drag_to(self, pos):
        """Mouse moved with a slider held: its value follows the mouse."""
        row = self._row(self.dragging) if self.dragging else None
        if row is None:
            return
        track = self._layout().parts[('track', row.key)]
        x, _y = self._local(pos)
        frac = max(0.0, min(1.0, (x - track.x) / float(max(1, track.w))))
        lo, hi = row.span
        self._set(row, lo + frac * (hi - lo))

    def release(self):
        self.dragging = None

    def select_tab(self, tab):
        self.tab = tab
        self.dragging = None
        self.hover = self.hover_row = None

    def handle_key(self, event):
        """Tab / Shift+Tab step through the tabs."""
        if event.key == pygame.K_TAB:
            keys = [key for key, _ in TABS]
            step = -1 if (event.mod & pygame.KMOD_SHIFT) else 1
            self.select_tab(keys[(keys.index(self.tab) + step) % len(keys)])
            sound_manager.play_ui_click()

    def _state(self, element):
        if self._flash and self._flash[0] == element and pygame.time.get_ticks() < self._flash[1]:
            return 'flash'
        if element[0] == 'slider' and self.dragging == element[1]:
            return 'flash'
        if self.hover == element:
            return 'hover'
        return 'normal'

    # ------------------------------------------------------------ drawing
    # Drawn by ui.menu_kit.WindowStage: the static parts are baked into its picture of the
    # menu (again whenever static_key() changes), the dynamic ones drawn every frame.

    title = "Options"

    def rect(self):
        """The window's rect on screen."""
        return self.kit.window_rect()

    def static_key(self):
        """What the static parts depend on: the tab, and which rows are dimmed."""
        return (self.tab, tuple(self.is_off(row) for row in self.tab_rows()))

    def draw(self, surface, ox, oy):
        """The whole window with its top-left at (ox, oy) on `surface`."""
        self.draw_static(surface, ox, oy)
        self.draw_dynamic(surface, ox, oy)

    def draw_static(self, surface, ox, oy):
        """What changes only with the tab or a dimmed row: board, title, rule, row names."""
        k = self.kit
        L = self._layout()
        w, h = L.size
        surface.blit(k.window((w, h)), (ox, oy))
        banner = k.banner(self.title)
        surface.blit(banner, (ox + (w - banner.get_width()) // 2, oy - k.banner_overhang()))
        rx, ry, rw = L.rule
        surface.blit(k.rule(rw), (ox + rx, oy + ry))
        for row, row_rect in L.rows:
            r = row_rect.move(ox, oy)
            surface.blit(k.row_rule(r.w), (r.x, r.bottom - 1))
            self._draw_row_text(surface, row, r)

    def draw_dynamic(self, surface, ox, oy):
        """What changes every moment: tabs, the hovered row, controls, buttons, the note."""
        k = self.kit
        px = k.px
        L = self._layout()
        for key, label in TABS:
            r = L.tabs[key]
            on = key == self.tab
            sprite = k.tab(r.size, label, on, 'normal' if on else self._state(('tab', key)))
            pad = (sprite.get_width() - r.w) // 2
            surface.blit(sprite, (ox + r.x - pad, oy + r.y - pad))

        for row, row_rect in L.rows:
            off = self.is_off(row)
            if self.hover_row == row.key and not off:
                # The wash goes under the row's text: draw that again over it
                r = row_rect.move(ox, oy)
                surface.blit(k.row_hover((r.w, r.h - 1)), r.topleft)
                self._draw_row_text(surface, row, r)
            draw = {'switch': self._draw_switch, 'arrows': self._draw_arrows,
                    'choice': self._draw_choice, 'slider': self._draw_slider}[row.kind]
            draw(surface, ox, oy, L, row, off)

        for key, label in (('reset', "Reset to Defaults"), ('cancel', "Cancel"), ('apply', "Apply")):
            r = L.buttons[key].move(ox, oy)
            k.draw_button(surface, r, label, self._state(('button', key)), primary=(key == 'apply'))

        count = self.unsaved()
        if count:
            note = k.text(f"{count} unsaved change{'s' if count > 1 else ''}", 'note', WARN)
        else:
            note = k.text("No changes", 'note', PARCHMENT_FAINT)
        cy = oy + L.buttons['cancel'].centery
        nx = ox + L.note_right - note.get_width()
        surface.blit(note, (nx, cy - note.get_height() // 2))
        if count:
            d = px(8)
            dot = k.dot(d, WARN)
            surface.blit(dot, (nx - px(10) - dot.get_width() // 2 - d // 2,
                               cy - dot.get_height() // 2))

    def _draw_row_text(self, surface, row, r):
        """A row's name and explanation, as one block centred in its rect `r` (on screen)."""
        k = self.kit
        px = k.px
        off = self.is_off(row)
        name_x = r.x + px(ROW_PAD) + (px(SUB_INDENT) if row.sub else 0)
        text_room = (r.right - px(ROW_PAD) - px(CONTROL_COLUMN) - px(20)) - name_x
        name = k.text(row.label, 'name_sub' if row.sub else 'name',
                      PARCHMENT_FAINT if off else PARCHMENT)
        hint_lines = [k.text(line, 'hint', (100, 90, 76) if off else PARCHMENT_DIM)
                      for line in k.wrap(row.hint, 'hint', text_room)] if row.hint else []
        gap = px(3)
        block_h = name.get_height() + sum(gap + line.get_height() for line in hint_lines)
        y = r.centery - block_h // 2
        if row.sub:
            elbow = k.branch((px(12), name.get_height() // 2 + px(8)))
            surface.blit(elbow, (name_x - px(22), y - px(8)))
        surface.blit(name, (name_x, y))
        y += name.get_height()
        for line in hint_lines:
            y += gap
            surface.blit(line, (name_x, y))
            y += line.get_height()

    def _draw_switch(self, surface, ox, oy, L, row, off):
        k = self.kit
        sw = L.parts[('switch', row.key)].move(ox, oy)
        on = bool(self._get(row))
        state = 'locked' if off else self._state(('switch', row.key))
        if state == 'normal' and self.hover == ('row', row.key):
            state = 'hover'      # Its name toggles it too: light the switch with it
        sprite = k.switch(sw.size, on, state)
        pad = k.switch_pad()
        surface.blit(sprite, (sw.x - pad, sw.y - pad))
        word = k.text("On" if on else "Off", 'state', GOLD_TEXT if on else PARCHMENT_FAINT)
        surface.blit(word, (sw.right + k.px(14), sw.centery - word.get_height() // 2))

    def _draw_arrows(self, surface, ox, oy, L, row, off):
        k = self.kit
        box = L.parts[('box', row.key)].move(ox, oy)
        surface.blit(k.well(box.size, k.px(4)), box.topleft)
        if self.is_locked(row):
            text = k.text(row.locked_text, 'value_small', PARCHMENT_FAINT)
        else:
            for side, direction in (('left', -1), ('right', 1)):
                part = L.parts[(side, row.key)].move(ox, oy)
                state = 'locked' if off else self._state((side, row.key))
                surface.blit(k.arrow(part.size, direction, state), part.topleft)
            text = k.text(self.value_label(row), 'value', PARCHMENT_FAINT if off else PARCHMENT)
        surface.blit(text, text.get_rect(center=box.center))

    def _draw_choice(self, surface, ox, oy, L, row, off):
        k = self.kit
        track = L.parts[('track', row.key)].move(ox, oy)
        surface.blit(k.well(track.size, track.h // 2), track.topleft)
        current = self._index(row)
        for i, label in enumerate(row.labels):
            part = L.parts[('choice', row.key, i)].move(ox, oy)
            on = i == current
            state = 'locked' if off else ('normal' if on else self._state(('choice', row.key, i)))
            surface.blit(k.choice(part.size, on, state), part.topleft)
            if on:
                color = CHOICE_ON_TEXT
            elif off:
                color = PARCHMENT_FAINT
            else:
                color = PARCHMENT if state != 'normal' else PARCHMENT_DIM
            text = k.text(label.upper(), 'choice', color, shadow=not on)
            surface.blit(text, text.get_rect(center=part.center))

    def _draw_slider(self, surface, ox, oy, L, row, off):
        k = self.kit
        px = k.px
        track = L.parts[('track', row.key)].move(ox, oy)
        surface.blit(k.slider_track(track.size), track.topleft)
        lo, hi = row.span
        value = float(self._get(row))
        frac = max(0.0, min(1.0, (value - lo) / float(hi - lo)))
        fill_w = int(round(track.w * frac))
        if fill_w > 0:
            surface.blit(k.slider_fill(track.size), track.topleft, pygame.Rect(0, 0, fill_w, track.h))
        state = 'locked' if off else self._state(('slider', row.key))
        knob = k.knob(px(KNOB), state)
        surface.blit(knob, knob.get_rect(center=(track.x + fill_w, track.centery)))
        text = k.text(row.fmt(value), 'value', GOLD_TEXT)
        right = track.right + px(16) + px(VALUE_WIDTH)
        surface.blit(text, (right - text.get_width(), track.centery - text.get_height() // 2))
