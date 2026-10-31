# -*- coding: utf-8 -*-
# achievement_panel.py
# The main menu's Achievements window - the trophy wall

"""
Achievement Panel
=================

The main menu's Achievements window (Menu Glow-up, agreed with the owner 2026-10-30 -
the "trophy wall"), drawn with the menu windows' kit (ui/menu_kit.py) as the Options
window is:

- A summary: earned out of total with a bar, the achievement closest to done and the
  latest one earned.
- Category chips with counts (All / General / Campaign / Training / Conquest) and a
  search over names and descriptions (typing anywhere starts it; Esc clears it before it
  closes the window).
- Every achievement as a medal, grouped by category: earned ones first (in colour, with
  a soft glow), the rest in the game's own order (grey, a padlock, and a thin progress
  bar for the counted ones). The wall scrolls with the mouse wheel.
- A details card: hovering a medal shows it, clicking one keeps it there - its
  description, the date it was earned or its progress, and its reward (the reward icon
  itself, or the title).

The unchanging parts (window, summary, the visible part of the wall) are baked into
the WindowStage's picture of the menu (again when the filter or the scroll changes);
the chips, the search, the highlights, the card and Close are drawn every frame.
"""

import math
from collections import OrderedDict

import pygame

from achievement_manager import achievement_manager, CATEGORIES, CATEGORY_LABELS
from config.constants import CLICK_FLASH_DURATION_MS
from global_sound import sound_manager
from rendering.bottom_panel_kit import GOLD_TEXT
from rendering.sidebar_widgets import GOLD, GOLD_DARK, GOLD_LIGHT, PARCHMENT, PARCHMENT_DIM
from ui.battle_screen_kit import ScrollView, SCROLL_BAR, SCROLL_BAR_GAP
from ui.menu_kit import WindowAnim, PARCHMENT_FAINT
from utils.logger import get_logger

logger = get_logger(__name__)

TROPHY_ICON = 'assets/achievements/GeneralAchievementsIcon.png'
SEARCH_MAX = 30
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
CARD_CACHE_MAX = 16
PROGRESS_TEXT = (216, 200, 166)

# Layout, px at 1600x900 (window-local; the window is 1220 x 806 there)
CONTENT_INSET = 28
SUMMARY_TOP = 44            # Board top to the summary row
SUMMARY_HEIGHT = 62
TROPHY = 56
SUMMARY_GAP = 18
SUMMARY_BAR = (240, 10)
TOOLS_TOP = 116             # Board top to the chips and the search
CHIP_GAP = 10
SEARCH_SIZE = (250, 38)
BODY_TOP = 168              # Board top to the wall and the card
BODY_GAP = 12               # The body's bottom to the footer
CARD_WIDTH = 372
CARD_GAP = 22               # Between the wall's scrollbar and the card
MEDAL = 74
MEDAL_GAP = (14, 18)        # Across, down (the progress bar sits in the gap below)
MINI_BAR_HEIGHT = 4
GROUP_HEAD = 38             # A category heading's height
GROUP_GAP = 6               # After a category's last row
CARD_PAD = 22
CARD_MEDAL = 132
REWARD_ICON = 44
FOOTER_GAP = 16
BUTTON_WIDTH = 230


def _date(iso):
    """'2026-10-12T...' -> '12 Oct 2026' ('' when missing or unreadable)."""
    try:
        y, m, d = (int(part) for part in str(iso)[:10].split('-'))
        return f"{d} {MONTHS[m - 1]} {y}"
    except (ValueError, IndexError, TypeError):
        return ""


def is_counted(ach):
    """A counted achievement (Win 10 games...) - progress shows; a one-off does not."""
    return (ach.get('stat_threshold') or 0) > 1


def progress(ach):
    """Done share of a counted achievement, 0..1."""
    need = ach.get('stat_threshold') or 0
    if need <= 0:
        return 1.0 if ach['earned'] else 0.0
    return max(0.0, min(1.0, (ach.get('stat_progress') or 0) / float(need)))


def progress_text(ach):
    need = ach.get('stat_threshold') or 0
    have = min(ach.get('stat_progress') or 0, need)
    if ach.get('stat_key') == 'player_level':
        return f"Level {have} / {need}"
    return f"{have:,} / {need:,}"


def rewards(ach):
    """[('icon', name, path) | ('title', title)] - the primary reward, then a second one."""
    found = []
    for kind, rid, name in ((ach.get('reward_type'), ach.get('reward_id'), ach.get('reward_name')),
                            (ach.get('reward_type_2'), ach.get('reward_id_2'), ach.get('reward_name_2'))):
        if kind == 'icon' and rid:
            found.append(('icon', name or "Exclusive Icon", rid))
        elif kind == 'title' and rid:
            found.append(('title', rid))
    return found


class AchievementPanel:
    """The Achievements window over a MainMenu (`menu`), drawn with a MenuKit (`kit`)."""

    title = "Achievements"

    def __init__(self, menu, kit):
        self.menu = menu
        self.kit = kit
        self.anim = WindowAnim()
        self.category = 'all'
        self.search_text = ''
        self.search_active = False
        self.selected = None        # The achievement id the card keeps
        self.hover = None           # ('chip', cat) | ('search',) | ('medal', id) | ('button', 'close')
        self._flash = None
        self._layout = None
        self._grids = {}            # (category, query) -> grid
        self._cards = OrderedDict()
        self.card_content_bottom = {}   # id -> how far down its card's content runs
        self._summary = None
        self._load()

    # ------------------------------------------------------------ data

    def _load(self):
        """The achievements as they are now (definition order), and the summary's facts."""
        self.achievements = achievement_manager.get_all_achievements()
        self.by_id = {a['id']: a for a in self.achievements}
        self.earned_count = sum(1 for a in self.achievements if a['earned'])
        pending = [a for a in self.achievements if not a['earned'] and is_counted(a)]
        self.closest = max(pending, key=progress) if pending else None
        earned = [a for a in self.achievements if a['earned']]
        self.latest = max(earned, key=lambda a: a.get('earned_timestamp') or '') if earned else None
        self._grids = {}
        self._cards = OrderedDict()
        self._summary = None
        self._layout = None          # The chips' widths follow their counts

    def _default_selection(self):
        pick = self.closest or self.latest or (self.achievements[0] if self.achievements else None)
        return pick['id'] if pick else None

    def groups(self):
        """[(category, label, [achievements])] shown under the current chip and search:
        earned first, then the rest, each part in the game's own order."""
        query = self.search_text.strip().lower()
        result = []
        for cat in CATEGORIES:
            if self.category not in ('all', cat):
                continue
            items = [a for a in self.achievements if a['category'] == cat and
                     (not query or query in a['name'].lower() or query in a['description'].lower())]
            if items:
                items = [a for a in items if a['earned']] + [a for a in items if not a['earned']]
                result.append((cat, CATEGORY_LABELS.get(cat, cat.title()), items))
        return result

    def chip_counts(self):
        """[(key, label, 'earned/total')] - All, then each category."""
        chips = [('all', "All", f"{self.earned_count}/{len(self.achievements)}")]
        for cat in CATEGORIES:
            items = [a for a in self.achievements if a['category'] == cat]
            done = sum(1 for a in items if a['earned'])
            chips.append((cat, CATEGORY_LABELS.get(cat, cat.title()), f"{done}/{len(items)}"))
        return chips

    # ------------------------------------------------------------ open / close

    def prewarm(self):
        """
        Decode every icon once and build the wall's sprites now (MainMenu creation), not on
        the window's first frame. MenuKit keeps them per screen size, so a later MainMenu
        (the game makes one each time it returns to the menu) decodes nothing.
        """
        k = self.kit
        paths = sorted({a['icon'] for a in self.achievements})
        k.preload_icons(paths, [k.px(MEDAL) - 2, k.px(CARD_MEDAL) - 2])
        reward_paths = sorted({r[2] for a in self.achievements for r in rewards(a) if r[0] == 'icon'})
        k.preload_icons(reward_paths, [k.px(REWARD_ICON)])
        k.preload_icons([TROPHY_ICON], [k.px(TROPHY)])
        self.selected = self.selected or self._default_selection()
        scratch = pygame.Surface(self.rect().size, pygame.SRCALPHA)
        self.draw(scratch, 0, 0)
        # What the first hovers would otherwise build: lit medals, the card's big medals
        for a in self.achievements:
            k.medal(a['icon'], k.px(MEDAL), a['earned'], 'hover')
            k.medal(a['icon'], k.px(CARD_MEDAL), a['earned'])
        for key, label, count in self.chip_counts():
            k.chip(label, count, False, 'hover')
            k.chip(label, count, True, 'normal')
        self.kit.backdrop()

    def open(self):
        """Opened fresh: the latest achievements, All, no search, the top of the wall."""
        achievement_manager.load()
        self._load()
        self.category = 'all'
        self.search_text = ''
        self.search_active = False
        self.selected = self._default_selection()
        self.hover = None
        self.anim.open()

    def close(self):
        self.search_active = False
        self.anim.close()

    def update(self, dt):
        self.anim.update(dt)

    # ------------------------------------------------------------ geometry

    def rect(self):
        return self.kit.window_rect()

    def layout(self):
        """Window-local rects (computed once): summary, chips row, search, wall, card, Close."""
        if self._layout is not None:
            return self._layout
        k = self.kit
        px = k.px
        w, h = self.rect().size
        b = k.border()
        inner_x = b + px(CONTENT_INSET)
        inner_w = w - 2 * inner_x
        L = {}
        L['summary'] = pygame.Rect(inner_x, b + px(SUMMARY_TOP), inner_w, px(SUMMARY_HEIGHT))
        tools_y = b + px(TOOLS_TOP)
        sw, sh = px(SEARCH_SIZE[0]), px(SEARCH_SIZE[1])
        L['search'] = pygame.Rect(inner_x + inner_w - sw, tools_y, sw, sh)
        L['chips_origin'] = (inner_x, tools_y)
        btn_w, btn_h = k.button_size(BUTTON_WIDTH)
        footer_y = h - b - px(FOOTER_GAP) - btn_h
        L['close'] = pygame.Rect((w - btn_w) // 2, footer_y, btn_w, btn_h)
        body_top = b + px(BODY_TOP)
        body_h = footer_y - px(BODY_GAP) - body_top
        card_w = px(CARD_WIDTH)
        L['card'] = pygame.Rect(inner_x + inner_w - card_w, body_top, card_w, body_h)
        gutter = px(SCROLL_BAR_GAP) + max(2, px(SCROLL_BAR))
        wall_w = inner_w - card_w - px(CARD_GAP) - gutter
        L['wall'] = pygame.Rect(inner_x, body_top, wall_w, body_h)
        # Chips, left to right (their widths come from their text)
        chips = {}
        x = inner_x
        for key, label, count in self.chip_counts():
            sprite = k.chip(label, count, False, 'normal')
            chips[key] = pygame.Rect(x, tools_y, sprite.get_width(), sprite.get_height())
            x += sprite.get_width() + px(CHIP_GAP)
        L['chips'] = chips
        self._layout = L
        return L

    def grid(self):
        """The wall for the current chip and search: its surface, each medal's rect on it
        and its ScrollView (kept until the filter changes; the scroll lives in the view)."""
        key = (self.category, self.search_text.strip().lower())
        grid = self._grids.get(key)
        if grid is None:
            grid = self._grids[key] = self._compose_grid()
        return grid

    def _compose_grid(self):
        k = self.kit
        px = k.px
        L = self.layout()
        wall = L['wall']
        pad = k.medal_pad()
        cell, gx, gy = px(MEDAL), px(MEDAL_GAP[0]), px(MEDAL_GAP[1])
        usable = wall.w - 2 * pad
        cols = max(1, (usable + gx) // (cell + gx))
        groups = self.groups()
        # Measure, then draw
        height = 0
        for _cat, _label, items in groups:
            rows = math.ceil(len(items) / cols)
            height += px(GROUP_HEAD) + rows * (cell + gy) + px(GROUP_GAP)
        surf = pygame.Surface((wall.w, max(1, height)), pygame.SRCALPHA)
        cells = []
        y = 0
        for cat, label, items in groups:
            self._draw_group_head(surf, y, label, cat)
            y += px(GROUP_HEAD)
            for i, a in enumerate(items):
                x = pad + (i % cols) * (cell + gx)
                cy = y + (i // cols) * (cell + gy)
                sprite = k.medal(a['icon'], cell, a['earned'])
                surf.blit(sprite, (x - pad, cy - pad))
                if not a['earned'] and is_counted(a):
                    bar_w = cell - 2 * px(8)
                    surf.blit(k.bar((bar_w, px(MINI_BAR_HEIGHT)), progress(a)),
                              (x + px(8), cy + cell + px(4)))
                cells.append((a['id'], pygame.Rect(x, cy, cell, cell)))
            y += math.ceil(len(items) / cols) * (cell + gy) + px(GROUP_GAP)
        view = ScrollView(surf, pygame.Rect(wall), k.scale)
        return {'surface': surf, 'cells': cells, 'view': view, 'cols': cols}

    def _draw_group_head(self, surf, y, label, cat):
        """A category's heading on the wall: its name, a fading gold rule, earned / total."""
        k = self.kit
        px = k.px
        pad = k.medal_pad()
        items = [a for a in self.achievements if a['category'] == cat]
        done = sum(1 for a in items if a['earned'])
        name = k.text(label.upper(), 'group', GOLD, spacing=0.14)
        count = k.text(f"{done} / {len(items)}", 'group_count', PARCHMENT_DIM)
        cy = y + px(GROUP_HEAD) // 2
        surf.blit(name, (pad, cy - name.get_height() // 2))
        right = surf.get_width() - pad
        surf.blit(count, (right - count.get_width(), cy - count.get_height() // 2))
        x0 = pad + name.get_width() + px(14)
        x1 = right - count.get_width() - px(14)
        span = max(1, x1 - x0)
        for x in range(x0, x1):
            t = (x - x0) / float(span)
            alpha = int(200 * (1.0 - t))
            surf.fill((GOLD_DARK[0], GOLD_DARK[1], GOLD_DARK[2], alpha), (x, cy, 1, 1))

    # ------------------------------------------------------------ hit-testing

    def _local(self, pos):
        rect = self.rect()
        return pos[0] - rect.x, pos[1] - rect.y

    def element_at(self, pos):
        L = self.layout()
        x, y = self._local(pos)
        if L['close'].collidepoint(x, y):
            return ('button', 'close')
        for key, r in L['chips'].items():
            if r.collidepoint(x, y):
                return ('chip', key)
        if L['search'].collidepoint(x, y):
            return ('search',)
        wall = L['wall']
        if wall.collidepoint(x, y):
            grid = self.grid()
            offset = grid['view'].offset
            gx, gy = x - wall.x, y - wall.y + offset
            for ach_id, cell in grid['cells']:
                if cell.collidepoint(gx, gy):
                    return ('medal', ach_id)
        return None

    def medal_rect(self, ach_id):
        """A medal's rect on screen, or None when it is not on the wall (tests, previews)."""
        grid = self.grid()
        wall = self.layout()['wall']
        rect = self.rect()
        for cid, cell in grid['cells']:
            if cid == ach_id:
                return cell.move(rect.x + wall.x, rect.y + wall.y - grid['view'].offset)
        return None

    def part_rect(self, element):
        """A control's rect on screen: ('chip', key), ('search',), ('button', 'close')."""
        L = self.layout()
        rect = self.rect()
        if element[0] == 'chip':
            r = L['chips'][element[1]]
        elif element[0] == 'search':
            r = L['search']
        elif element[0] == 'button':
            r = L['close']
        else:
            return self.medal_rect(element[1])
        return r.move(rect.x, rect.y)

    def update_hover(self, pos):
        self.hover = self.element_at(pos) if self.anim.interactive else None

    # ------------------------------------------------------------ input

    def _click(self, element):
        sound_manager.play_ui_click()
        self._flash = (element, pygame.time.get_ticks() + CLICK_FLASH_DURATION_MS)

    def handle_click(self, pos):
        """A left click: 'close' for MainMenu, else None."""
        if not self.anim.interactive:
            return None
        element = self.element_at(pos)
        self.search_active = bool(element and element[0] == 'search')
        if element is None:
            return None
        if element[0] == 'button':
            self._click(element)
            return 'close'
        if element[0] == 'chip':
            if element[1] != self.category:
                self._click(element)
                self.set_category(element[1])
        elif element[0] == 'medal':
            if element[1] != self.selected:
                self._click(element)
                self.selected = element[1]
        return None

    def set_category(self, category):
        self.category = category
        self.grid()['view'].offset = 0
        self._keep_selection_visible()

    def _keep_selection_visible(self):
        ids = [cid for cid, _cell in self.grid()['cells']]
        if ids and self.selected not in ids:
            self.selected = ids[0]

    def wheel(self, dy):
        """Mouse wheel (+1 up, -1 down): scroll the wall."""
        if self.anim.interactive:
            self.grid()['view'].wheel(dy)

    def handle_escape(self):
        """Esc: clears the search (True), else lets MainMenu close the window (False)."""
        if self.search_text or self.search_active:
            self.search_text = ''
            self.search_active = False
            self._after_search()
            return True
        return False

    def handle_key(self, event):
        """Typing searches (it starts the search from anywhere); Enter leaves the field."""
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.search_active = False
        elif event.key == pygame.K_BACKSPACE:
            if self.search_active and self.search_text:
                self.search_text = self.search_text[:-1]
                self._after_search()
        elif event.unicode and event.unicode.isprintable() and len(self.search_text) < SEARCH_MAX:
            if event.unicode == ' ' and not self.search_active:
                return
            self.search_active = True
            self.search_text += event.unicode
            self._after_search()

    def _after_search(self):
        self.grid()['view'].offset = 0
        self._keep_selection_visible()

    def _state(self, element):
        if self._flash and self._flash[0] == element and pygame.time.get_ticks() < self._flash[1]:
            return 'flash'
        if self.hover == element:
            return 'hover'
        return 'normal'

    # ------------------------------------------------------------ drawing (WindowStage)

    def static_key(self):
        grid = self.grid()
        return (self.category, self.search_text.strip().lower(), grid['view'].offset)

    def draw(self, surface, ox, oy):
        self.draw_static(surface, ox, oy)
        self.draw_dynamic(surface, ox, oy)

    def draw_static(self, surface, ox, oy):
        """Board, title plate, summary and the wall's visible part."""
        k = self.kit
        L = self.layout()
        w, h = self.rect().size
        surface.blit(k.window((w, h)), (ox, oy))
        banner = k.banner(self.title)
        surface.blit(banner, (ox + (w - banner.get_width()) // 2, oy - k.banner_overhang()))
        summary = self._summary_surface()
        surface.blit(summary, (ox + L['summary'].x, oy + L['summary'].centery - summary.get_height() // 2))
        grid = self.grid()
        wall = L['wall'].move(ox, oy)
        if grid['cells']:
            view = grid['view']
            view.rect = wall
            view.draw(surface)
        else:
            query = self.search_text.strip()
            text = k.text(f"No achievement matches “{query}”" if query else "Nothing here yet",
                          'empty', PARCHMENT_DIM)
            surface.blit(text, text.get_rect(center=(wall.centerx, wall.y + wall.h // 3)))

    def draw_dynamic(self, surface, ox, oy):
        """Chips, search, the hovered / chosen medal, the card, Close."""
        k = self.kit
        L = self.layout()
        for key, label, count in self.chip_counts():
            r = L['chips'][key].move(ox, oy)
            on = key == self.category
            surface.blit(k.chip(label, count, on, 'normal' if on else self._state(('chip', key))), r.topleft)
        self._draw_search(surface, L['search'].move(ox, oy))

        # The hovered medal lit and the chosen one ringed, inside the wall only
        grid = self.grid()
        wall = L['wall'].move(ox, oy)
        offset = grid['view'].offset
        hovered = self.hover[1] if self.hover and self.hover[0] == 'medal' else None
        clip = surface.get_clip()
        surface.set_clip(wall.inflate(k.ring_offset() * 2, 0).clip(surface.get_rect()))
        pad = k.medal_pad()
        for ach_id, cell in grid['cells']:
            if ach_id not in (hovered, self.selected):
                continue
            r = cell.move(wall.x, wall.y - offset)
            if r.bottom < wall.top or r.top > wall.bottom:
                continue
            a = self.by_id[ach_id]
            if ach_id == hovered:
                sprite = k.medal(a['icon'], cell.w, a['earned'], self._state(('medal', ach_id)))
                surface.blit(sprite, (r.x - pad, r.y - pad))
            if ach_id == self.selected:
                ring = k.ring(r.size)
                surface.blit(ring, (r.x - k.ring_offset(), r.y - k.ring_offset()))
        surface.set_clip(clip)

        shown = hovered or self.selected
        if shown in self.by_id:
            card = self._card(shown)
            surface.blit(card, L['card'].move(ox, oy).topleft)
        k.draw_button(surface, L['close'].move(ox, oy), "Close", self._state(('button', 'close')))

    def _draw_search(self, surface, r):
        k = self.kit
        px = k.px
        box = k.search_box(r.size, self.search_active)
        pad = k.search_pad()
        surface.blit(box, (r.x - pad, r.y - pad))
        text_x = r.x + r.h
        room = r.right - px(14) - text_x
        if self.search_text:
            shown = self._tail(self.search_text, room)
            text = k.text(shown, 'search', PARCHMENT, shadow=False)
        else:
            text = k.text("Search achievements", 'search', PARCHMENT_FAINT, shadow=False)
        ty = r.centery - text.get_height() // 2
        surface.blit(text, (text_x, ty))
        if self.search_active and (pygame.time.get_ticks() // 500) % 2 == 0:
            cx = text_x + (text.get_width() if self.search_text else 0) + 1
            pygame.draw.line(surface, GOLD_LIGHT, (cx, r.y + px(10)), (cx, r.bottom - px(10)),
                             max(1, px(2)))

    def _tail(self, text, room):
        """The end of `text` that fits `room` px (the search keeps the last letters typed)."""
        font = self.kit.font('search')
        while text and font.size(text)[0] > room:
            text = text[1:]
        return text

    def _summary_surface(self):
        """Trophy, '17 of 44 earned', the bar; closest and latest on the right. Built per open."""
        if self._summary is not None:
            return self._summary
        k = self.kit
        px = k.px
        L = self.layout()
        width, height = L['summary'].size
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        trophy = k.icon(TROPHY_ICON, px(TROPHY))
        surf.blit(trophy, (0, (height - trophy.get_height()) // 2), special_flags=pygame.BLEND_RGBA_MAX)
        x = trophy.get_width() + px(SUMMARY_GAP)
        count = k.text(str(self.earned_count), 'count', GOLD_LIGHT)
        rest = k.text(f"of {len(self.achievements)} earned", 'count_small', PARCHMENT_DIM)
        base = height // 2 + count.get_height() // 2
        surf.blit(count, (x, base - count.get_height()))
        x += count.get_width() + px(8)
        surf.blit(rest, (x, base - rest.get_height() - px(2)))
        x += rest.get_width() + px(SUMMARY_GAP)
        frac = self.earned_count / float(max(1, len(self.achievements)))
        bar = k.bar((px(SUMMARY_BAR[0]), px(SUMMARY_BAR[1])), frac)
        surf.blit(bar, (x, (height - bar.get_height()) // 2))
        lines = []
        if self.closest:
            lines.append(("Closest: ", self.closest['name'], f" · {int(progress(self.closest) * 100)}%"))
        if self.latest:
            lines.append(("Latest: ", self.latest['name'], f" · {_date(self.latest.get('earned_timestamp'))}"))
        row_h = k.font('summary_b').get_linesize()
        y = (height - row_h * len(lines)) // 2
        for lead, name, tail in lines:
            parts = [k.text(lead, 'summary', PARCHMENT_DIM), k.text(name, 'summary_b', GOLD_TEXT),
                     k.text(tail, 'summary', PARCHMENT_DIM)]
            total = sum(p.get_width() for p in parts)
            px_x = width - total
            for p in parts:
                surf.blit(p, (px_x, y))
                px_x += p.get_width()
            y += row_h
        self._summary = surf
        return surf

    def _card(self, ach_id):
        """The details card for one achievement, composed once and kept (a few at a time)."""
        card = self._cards.get(ach_id)
        if card is not None:
            self._cards.move_to_end(ach_id)
            return card
        card = self._compose_card(self.by_id[ach_id])
        self._cards[ach_id] = card
        if len(self._cards) > CARD_CACHE_MAX:
            self._cards.popitem(last=False)
        return card

    def _compose_card(self, a):
        k = self.kit
        px = k.px
        size = self.layout()['card'].size
        w, h = size
        card = k.card_plate(size).copy()
        inner = w - 2 * px(CARD_PAD)
        y = px(CARD_PAD)

        def centred(surface, gap_after):
            nonlocal y
            card.blit(surface, ((w - surface.get_width()) // 2, y))
            y += surface.get_height() + gap_after

        medal = k.medal(a['icon'], px(CARD_MEDAL), a['earned'])
        card.blit(medal, ((w - medal.get_width()) // 2, y - k.medal_pad()))
        y += px(CARD_MEDAL) + px(12)
        centred(k.text(CATEGORY_LABELS.get(a['category'], a['category']).upper(), 'card_cat',
                       PARCHMENT_DIM, spacing=0.18), px(6))
        for line in k.wrap(a['name'], 'card_name', inner, max_lines=2):
            centred(k.text(line, 'card_name', GOLD_LIGHT), 0)
        y += px(8)
        for line in k.wrap(a['description'], 'card_text', inner, max_lines=5):
            centred(k.text(line, 'card_text', PARCHMENT), px(1))
        y += px(10)
        centred(k.rule(inner), px(12))
        if a['earned']:
            when = _date(a.get('earned_timestamp'))
            centred(k.text(f"Earned {when}" if when else "Earned", 'card_status', GOLD_LIGHT), px(14))
        elif is_counted(a):
            centred(k.bar((inner, px(10)), progress(a)), px(6))
            centred(k.text(progress_text(a), 'card_prog', PROGRESS_TEXT), px(14))
        else:
            centred(k.text("Not yet earned", 'card_prog', PARCHMENT_FAINT), px(14))
        found = rewards(a)
        if found:
            centred(k.text("REWARD", 'card_label', PARCHMENT_DIM, spacing=0.18), px(8))
            for reward in found:
                if reward[0] == 'icon':
                    icon = k.icon(reward[2], px(REWARD_ICON))
                    name = k.text(k.fit(reward[1], 'card_reward', inner - icon.get_width() - px(10)),
                                  'card_reward', GOLD_TEXT)
                    row_w = icon.get_width() + px(10) + name.get_width()
                    x = (w - row_w) // 2
                    card.blit(icon, (x, y))
                    pygame.draw.rect(card, GOLD_DARK, (x, y, icon.get_width(), icon.get_height()), 1)
                    card.blit(name, (x + icon.get_width() + px(10),
                                     y + (icon.get_height() - name.get_height()) // 2))
                    y += icon.get_height() + px(8)
                else:
                    centred(k.text(f"Title: “{reward[1]}”", 'card_reward', GOLD_TEXT), px(8))
        self.card_content_bottom[a['id']] = y     # Tests: the content fits the card
        return card
