# -*- coding: utf-8 -*-
"""
The multiplayer lobby's chat panel: a collapsible panel on the right of the lobby map,
built like the in-game right sidebar with a single "Chat" bookmark (owner request).

Same art and behaviour as the game's sidebar: RightPanel.jpg tapestry, the ribbon
bookmark, the round gold toggle button above it, the bronze panel edge, the 150 ms
slide, the gold unread count on the bookmark, chat lines drawn exactly as in game.
Those pieces come from rendering/sidebar_widgets.py (SidebarWidgets + the shared panel
chrome functions) and ui/sidebar_layout.py; this panel is the SidebarWidgets host
(it offers ui_scale, font_manager, screen, mouse_pos, clicked_element and
is_sidebar_animating() like a Game does).

Geometry: from the map's top edge to its bottom edge (the wood strips above / below the
map stay free, so the map top bar's Show Borders button is never covered), at the right
edge of the screen. Starts collapsed: only the bookmark (and the round button) show.

Input (the lobby routes it here first, modal windows aside):
- Enter: opens the panel and starts typing; while typing Enter sends (typing goes on),
  TAB switches between everyone and your team, Backspace deletes, Escape stops typing
  (clears the line) - it never leaves the lobby while typing.
- F2 / the round button: collapse or expand. The bookmark opens a collapsed panel.
- Clicks and the mouse wheel over the panel never reach the map underneath.

The chat itself (lines, teams, unread count) is network/lobby_chat.py; sending is the
lobby's send_lobby_chat() (passed in as `send`).
"""

import os
import time

import pygame

from config.font_manager import FontManager
from network.lobby_chat import MAX_LENGTH
from rendering.sidebar_widgets import (SidebarWidgets, GOLD, GOLD_DARK, GOLD_LIGHT, BRONZE_EDGE,
                                       build_toggle_sprite, chat_entry_layout, draw_chat_entry,
                                       draw_panel_border, draw_tab_badge)
from ui.scaler import UIConstants
from ui.sidebar_layout import (ScrollState, SCROLLBAR_W, compute_sidebar_layout, content_geometry,
                               reverse_anim_start, sidebar_progress)
from utils.logger import get_logger
from utils.surface_utils import load_cached_image

logger = get_logger(__name__)

PANEL_ART = 'assets/RightPanel.jpg'
CIRCLE_BORDER = 'assets/mapicons/CircleBorder.png'
GAME_TAB_COUNT = 6          # The game's bookmark column holds 6; one lobby bookmark is that tall
FLASH_MS = 150              # Click flash (CLICK_FLASH_DURATION_MS)
CURSOR_BLINK_MS = 500

# Input field (in-game chat box colours: blue for everyone, green for the team)
INPUT_FILL = (24, 16, 14)
CHANNEL_COLORS = {'all': (100, 200, 255), 'team': (100, 200, 100)}
PLACEHOLDER_COLOR = (170, 150, 130)
TYPED_COLOR = (240, 232, 214)
HINT_COLOR = (170, 150, 130)
UNREAD_BADGE = ((214, 168, 64), (255, 236, 180), (40, 24, 8))   # fill, rim, text (as in game)


class LobbyChatPanel:
    """See module docstring. One per lobby screen."""

    def __init__(self, screen, chat, send, viewer):
        """
        Args:
            screen: The lobby's screen surface.
            chat: network.lobby_chat.LobbyChat with the lines.
            send: send(text, channel) -> bool, the lobby's send_lobby_chat().
            viewer: viewer() -> (slot index, lobby team) of this PC's player.
        """
        self.screen = screen
        self.chat = chat
        self.send = send
        self.viewer = viewer
        w, h = screen.get_size()
        # SidebarWidgets host attributes (as Game): text scale and Cinzel fonts
        self.ui_scale = min(w / 1600.0, h / 900.0)
        self.font_manager = FontManager()
        self.font_manager.load_fonts(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.widgets = SidebarWidgets(self)
        self.mouse_pos = (-1, -1)
        self._flash = (None, 0)

        self.expanded = False           # Owner: starts collapsed
        self._anim_start_ms = None
        self.scroll = ScrollState('bottom')
        self.focused = False            # Typing in the input field
        self.text = ""
        self.channel = 'all'

        self.window_w = w
        self.top = 0
        self.height = h
        self._panel_art = None
        self._circle_border = None
        self._toggle_sprites = {}
        self._tab_flash_cache = {}
        self._layout_cache = {'key': None}

        # Rects from the last frame drawn (click / hover tests)
        self.toggle_rect = None
        self.tab_rect = None
        self.input_rect = None

    # ------------------------------------------------------------------ SidebarWidgets host

    @property
    def clicked_element(self):
        """The control flashing after a click ('toggle' / 'tab' / 'input'), else None."""
        name, ticks = self._flash
        return name if name is not None and pygame.time.get_ticks() - ticks < FLASH_MS else None

    def is_sidebar_animating(self):
        start = self._anim_start_ms
        return start is not None and pygame.time.get_ticks() - start < UIConstants.SIDEBAR_SLIDE_MS

    # ------------------------------------------------------------------ geometry

    def set_geometry(self, window_w, top, height):
        """The panel spans the map's height (`top` = the map's top edge)."""
        self.window_w, self.top, self.height = int(window_w), int(top), max(1, int(height))
        self._panel_art = None          # Rebuilt at the new height
        self._layout_cache = {'key': None}

    def layout(self):
        progress = sidebar_progress(self.expanded, self._anim_start_ms, pygame.time.get_ticks(),
                                    UIConstants.SIDEBAR_SLIDE_MS)
        return compute_sidebar_layout(self.window_w, self.top, self.height, progress,
                                      UIConstants.SIDEBAR_WIDTH, UIConstants.TAB_WIDTH)

    def _chrome_rects(self, layout):
        """(toggle, bookmark) rects - in the tab column, as in game."""
        tab_w = UIConstants.TAB_WIDTH
        toggle = pygame.Rect(layout.tab_x, layout.top + 4, tab_w, UIConstants.SIDEBAR_TOGGLE_HEIGHT)
        tab_h = max(40, int((self.height - UIConstants.TAB_PADDING_TOP
                             - UIConstants.TAB_PADDING_BOTTOM) / GAME_TAB_COUNT))
        tab = pygame.Rect(layout.tab_x, layout.top + UIConstants.TAB_PADDING_TOP, tab_w, tab_h)
        return toggle, tab

    def panel_rect(self, layout=None):
        layout = layout or self.layout()
        return pygame.Rect(layout.panel_x, layout.top, UIConstants.SIDEBAR_WIDTH, layout.height)

    def contains(self, pos):
        """True over anything of the panel on screen: body, bookmark or round button."""
        layout = self.layout()
        toggle, tab = self._chrome_rects(layout)
        if toggle.collidepoint(pos) or tab.collidepoint(pos):
            return True
        return layout.panel_visible and self.panel_rect(layout).collidepoint(pos)

    # ------------------------------------------------------------------ state

    def set_expanded(self, expanded, animate=True):
        """Open / close (slides; reversing mid-slide resumes where it is)."""
        expanded = bool(expanded)
        if expanded == self.expanded:
            return False
        self.expanded = expanded
        self._anim_start_ms = (reverse_anim_start(self._anim_start_ms, pygame.time.get_ticks(),
                                                  UIConstants.SIDEBAR_SLIDE_MS) if animate else None)
        if not expanded:
            self.focused = False
        return True

    def _viewer(self):
        try:
            return self.viewer()
        except Exception as exc:   # The lobby state is being rebuilt - read as nobody's team
            logger.warning(f"Lobby chat: viewer unknown ({exc})")
            return -1, None

    def unread(self):
        index, team = self._viewer()
        return self.chat.unread_count(index, team)

    def _click(self, element):
        from global_sound import sound_manager
        sound_manager.play_ui_click()
        self._flash = (element, pygame.time.get_ticks())

    def focus(self):
        """Open the panel and start typing."""
        self.set_expanded(True)
        self.focused = True

    def unfocus(self, clear=False):
        self.focused = False
        if clear:
            self.text = ""

    # ------------------------------------------------------------------ input

    def update_hover(self, pos):
        self.mouse_pos = pos

    def handle_click(self, pos):
        """Left click. True when it landed on the panel (the lobby stops there)."""
        layout = self.layout()
        toggle, tab = self._chrome_rects(layout)
        if toggle.collidepoint(pos):
            self._click('toggle')
            self.set_expanded(not self.expanded)
            return True
        if tab.collidepoint(pos):
            # As in game: the bookmark opens a collapsed panel (closing is the round
            # button's / F2's job)
            self._click('tab')
            self.set_expanded(True)
            return True
        if layout.panel_visible and self.panel_rect(layout).collidepoint(pos):
            if self.expanded and self.input_rect is not None and self.input_rect.collidepoint(pos):
                self._click('input')
                self.focused = True
            else:
                self.focused = False      # Clicking the list stops typing (keeps the draft)
            return True
        self.focused = False              # Clicked elsewhere in the lobby
        return False

    def handle_wheel(self, pos, wheel_y):
        """Mouse wheel (MOUSEWHEEL y). True when over the open panel (it scrolls)."""
        layout = self.layout()
        if not (self.expanded and layout.panel_visible and self.panel_rect(layout).collidepoint(pos)):
            return False
        if wheel_y:
            step = 3 * self.widgets.font('body').get_linesize()
            self.scroll.scroll(-step if wheel_y > 0 else step)   # Wheel up = older lines
        return True

    def handle_key(self, event):
        """KEYDOWN. True when the chat used the key (the lobby must not act on it)."""
        if event.type != pygame.KEYDOWN:
            return False
        if self.focused:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.text.strip() and self.send(self.text, self.channel):
                    self.scroll.reset()          # Jump to the newest line
                self.text = ""                   # Typing goes on (the field keeps focus)
            elif event.key == pygame.K_TAB:
                self.channel = 'team' if self.channel == 'all' else 'all'
            elif event.key == pygame.K_ESCAPE:
                self.unfocus(clear=True)         # Never leaves the lobby while typing
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                char = getattr(event, 'unicode', '')
                if char and char.isprintable() and len(self.text) < MAX_LENGTH:
                    self.text += char
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.focus()
            return True
        if event.key == pygame.K_F2:
            self.set_expanded(not self.expanded)
            return True
        return False

    # ------------------------------------------------------------------ art

    def _art(self):
        """RightPanel.jpg at the panel's size (as the game's sidebar), built once."""
        if self._panel_art is None:
            image = load_cached_image(PANEL_ART, alpha=False)
            size = (UIConstants.SIDEBAR_WIDTH, self.height)
            if image is None:
                self._panel_art = pygame.Surface(size)
                self._panel_art.fill((40, 40, 40))
            else:
                self._panel_art = pygame.transform.scale(image, size)
        return self._panel_art

    def _toggle_sprite(self, diameter, state):
        key = (diameter, self.expanded, state)
        sprite = self._toggle_sprites.get(key)
        if sprite is None:
            if self._circle_border is None:
                border = load_cached_image(CIRCLE_BORDER, alpha=True)
                if border is not None:
                    # The game brightens CircleBorder by 25 for its plot icons and button
                    border = border.copy()
                    border.fill((25, 25, 25, 0), special_flags=pygame.BLEND_RGB_ADD)
                self._circle_border = border or False
            sprite = build_toggle_sprite(diameter, self.expanded, state, self._circle_border or None)
            self._toggle_sprites[key] = sprite
        return sprite

    # ------------------------------------------------------------------ drawing

    def draw(self):
        """Draw the panel (call every frame, after the map and before modal windows)."""
        if self._anim_start_ms is not None and not self.is_sidebar_animating():
            self._anim_start_ms = None
        layout = self.layout()
        panel = self.panel_rect(layout)
        toggle, tab = self._chrome_rects(layout)
        if layout.panel_visible:
            self.screen.blit(self._art(), panel.topleft)
        self._draw_bookmark(tab, layout)
        if layout.panel_visible:
            draw_panel_border(self.screen, panel, tab if self.expanded else None)
        self._draw_toggle(toggle)
        self.toggle_rect, self.tab_rect = toggle, tab

        if self.expanded and not self.is_sidebar_animating():
            self.chat.mark_seen()        # Open = read
        unread = self.unread()
        if unread > 0:
            draw_tab_badge(self.screen, self.widgets, tab, unread, *UNREAD_BADGE)

        if not layout.panel_visible:
            self.input_rect = None
            return
        self._draw_content(layout)

    def _hovered(self, rect):
        return rect is not None and rect.collidepoint(self.mouse_pos) and not self.is_sidebar_animating()

    def _draw_bookmark(self, tab, layout):
        w = self.widgets
        style = UIConstants.SIDEBAR_TAB_STYLE
        flashing = self.clicked_element == 'tab'
        # The only bookmark is always the active one (as the game's open tab)
        state = 'active_hover' if (flashing or self._hovered(tab)) else 'active'
        extra = UIConstants.TAB_ACTIVE_EXTEND if style == 'ribbon' else 0
        draw_rect = pygame.Rect(tab.x - extra, tab.y, tab.w + extra, tab.h)
        art = self._art()
        rel_y = max(0, min(tab.y - layout.top, art.get_height() - tab.h))
        texture = (art, (30, rel_y, draw_rect.w, tab.h)) if tab.h <= art.get_height() else None
        max_len, max_thick = w.tab_label_space(tab.w, tab.h)
        label_px = w.common_label_px(["Chat"], max_len, max_thick)
        sprite = w.tab_sprite(style, "Chat", draw_rect.size, state, texture, label_px)
        if flashing:
            # The kit's 'flash' look is for an unlit bookmark being opened (dimmer than a
            # lit one); this bookmark is always lit, so its flash is the lit sprite
            # brightened (cached per size: no new surface each frame)
            key = (draw_rect.size, label_px, id(art))
            flash = self._tab_flash_cache.get(key)
            if flash is None:
                flash = sprite.copy()
                flash.fill((48, 48, 48), special_flags=pygame.BLEND_RGB_ADD)
                self._tab_flash_cache = {key: flash}
            sprite = flash
        self.screen.blit(sprite, draw_rect.topleft)

    def _draw_toggle(self, rect):
        if self.clicked_element == 'toggle':
            state = 'click'
        elif self._hovered(rect):
            state = 'hover'
        else:
            state = 'normal'
        diameter = min(rect.width, rect.height) - 1
        sprite = self._toggle_sprite(diameter, state)
        self.screen.blit(sprite, sprite.get_rect(center=rect.center))

    def _input_metrics(self):
        """(field height, hint line height) - the footer pinned under the list."""
        w = self.widgets
        return w.font('body').get_linesize() + 12, w.font('small').get_linesize() + 2

    def _draw_content(self, layout):
        """Header, messages (newest at the bottom) and the input field."""
        w = self.widgets
        screen = self.screen
        x0 = layout.panel_x
        content_start_y = layout.top + 15      # As the game's tabs
        full = content_geometry(x0, layout.top, layout.height, panel_width=UIConstants.SIDEBAR_WIDTH)
        half = min(full.center_x - full.x, full.right - full.center_x)
        header = w.section_header("Chat", 2 * half, role='title')
        screen.blit(header, (full.center_x - half, content_start_y))
        list_top = content_start_y + header.get_height() + 8

        field_h, hint_h = self._input_metrics()
        footer_h = 8 + field_h + 4 + hint_h + 6
        geo = content_geometry(x0, layout.top, layout.height, header_h=list_top - layout.top,
                               footer_h=footer_h, panel_width=UIConstants.SIDEBAR_WIDTH, scrollbar=True)
        viewport = pygame.Rect(geo.x, geo.top, geo.width, max(1, geo.bottom - geo.top))
        self._draw_messages(viewport, full)
        w.draw_scrollbar(pygame.Rect(geo.right + 2, viewport.y, SCROLLBAR_W, viewport.h), self.scroll)

        field = pygame.Rect(full.x, viewport.bottom + 8, full.width, field_h)
        self.input_rect = field
        self._draw_input(field)
        if self.focused:
            hint = w.text(w.fit_text("TAB: team / all   ESC: stop typing", 'small', full.width),
                          'small', HINT_COLOR)
            screen.blit(hint, hint.get_rect(midtop=(full.center_x, field.bottom + 4)))

    def _items(self, width):
        """Visible lines laid out in pixels; rebuilt only when the chat or the viewer's
        team changes. Returns (items, ys, total height, height added since last time)."""
        index, team = self._viewer()
        key = (self.chat.version, index, team, int(width), self.widgets.scale)
        cache = self._layout_cache
        if cache['key'] == key:
            return cache['items'], cache['ys'], cache['total'], 0
        items, ys, y = [], [], 0
        for entry in self.chat.visible(index, team):
            lines, height = chat_entry_layout(self.widgets, entry.text, width)
            items.append((height, entry, lines))
            ys.append(y)
            y += height
        old_total = cache.get('total', 0) if cache['key'] is not None else 0
        same_list = cache['key'] is not None and cache['key'][1:] == key[1:]
        grew = max(0, y - old_total) if same_list else 0
        cache.update(key=key, items=items, ys=ys, total=y)
        return items, ys, y, grew

    def _draw_messages(self, viewport, full):
        w = self.widgets
        items, ys, total_h, grew = self._items(viewport.w)
        if grew:
            self.scroll.on_content_grew(grew)
        if not items:
            self.scroll.set_content(0, viewport.h)
            empty = w.text("No messages yet", 'body', (200, 170, 150))
            self.screen.blit(empty, empty.get_rect(center=(full.center_x, viewport.y + 30)))
            hint = w.text("Press ENTER to chat", 'italic', (170, 150, 130))
            self.screen.blit(hint, hint.get_rect(center=(full.center_x, viewport.y + 54)))
            return
        # Bottom-anchored scrolling as the game's Chat tab: short lists sit at the top
        self.scroll.set_content(total_h, viewport.h)
        origin = viewport.y - self.scroll.view_top()
        previous = w.begin_clip(viewport)
        try:
            for (height, entry, lines), y in zip(items, ys):
                screen_y = origin + y
                if screen_y + height < viewport.y:
                    continue
                if screen_y > viewport.bottom:
                    break
                draw_chat_entry(w, self.screen, viewport.x, screen_y, viewport.w, entry.time,
                                entry.name, entry.color, lines, entry.channel == 'team')
        finally:
            w.end_clip(previous)

    def _draw_input(self, field):
        """The input field: placeholder while idle; channel tag, text tail and a
        blinking cursor while typing. Brightens on hover, flashes on click."""
        w = self.widgets
        screen = self.screen
        flashing = self.clicked_element == 'input'
        hovered = self._hovered(field)
        fill = tuple(min(255, c + (40 if flashing else 14 if hovered and not self.focused else 0))
                     for c in INPUT_FILL)
        pygame.draw.rect(screen, fill, field, border_radius=4)
        rim = GOLD if self.focused else (GOLD_LIGHT if flashing else (GOLD_DARK if hovered else BRONZE_EDGE))
        pygame.draw.rect(screen, rim, field, 2 if self.focused else 1, border_radius=4)

        inner = field.inflate(-12, -4)
        if not self.focused and not self.text:
            placeholder = w.text(w.fit_text("Press Enter to chat", 'italic', inner.w), 'italic',
                                 PLACEHOLDER_COLOR)
            screen.blit(placeholder, placeholder.get_rect(midleft=(inner.x, field.centery)))
            return
        x = inner.x
        if self.focused:
            tag = w.text("[TEAM]" if self.channel == 'team' else "[ALL]", 'small_bold',
                         CHANNEL_COLORS[self.channel])
            screen.blit(tag, tag.get_rect(midleft=(x, field.centery)))
            x += tag.get_width() + 5
        room = inner.right - x - 4
        # Keep the end of the line in view (the part being typed)
        shown = self.text
        font = w.font('body')
        while shown and font.size(shown)[0] > room:
            shown = shown[1:]
        text = w.text(shown, 'body', TYPED_COLOR) if shown else None
        if text is not None:
            screen.blit(text, text.get_rect(midleft=(x, field.centery)))
            x += text.get_width()
        if self.focused and (pygame.time.get_ticks() // CURSOR_BLINK_MS) % 2 == 0:
            pygame.draw.line(screen, TYPED_COLOR, (x + 2, field.y + 6), (x + 2, field.bottom - 7), 2)
