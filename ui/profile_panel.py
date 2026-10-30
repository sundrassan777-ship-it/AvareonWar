# -*- coding: utf-8 -*-
"""
The main menu's Profile window - the player card (Menu Glow-up, agreed with the owner
2026-10-30; phase 3), drawn with the menu windows' kit (ui/menu_kit.py):

- The card (left): the chosen portrait large, the name (typed on the card; a Steam name
  is read-only, with a "Steam" tag), the title under it, the level medallion with the XP
  shown (it used to appear only when hovering the level bar), Custom / Multiplayer stat
  tiles, and the achievements earned with a View button (opens the Achievements window;
  closing that brings the card back as it was left).
- The pickers (right): every title as a chip (locked ones say what earns them on hover),
  the hero portraits and the achievement-reward portraits (locked ones grey with a
  padlock; hover says what unlocks them).
- Cancel / Save. Enter saves; Esc cancels (while typing the name it only stops typing).

The window edits MainMenu's pending values (temp_player_name / temp_player_icon /
temp_selected_title); MainMenu reads them on opening (_open_profile: the Steam name) and
writes them (_save_profile). Win rates count at least as many games as wins: the "games
finished" counters arrived after the wins counters (b00c2e7), so an older profile has more
wins than games (210 wins of 8 games read 2625%).
"""

import pygame

from achievement_manager import achievement_manager, ALL_REWARD_ICON_PATHS, ALL_TITLES
from config.constants import CLICK_FLASH_DURATION_MS
from global_sound import sound_manager
from player_level import player_level_manager, MAX_LEVEL
from rendering.bottom_panel_kit import GOLD_TEXT
from rendering.sidebar_widgets import GOLD, GOLD_DARK, GOLD_LIGHT, PARCHMENT, PARCHMENT_DIM
from ui.menu_kit import WindowAnim, PARCHMENT_FAINT

TROPHY_ICON = 'assets/achievements/GeneralAchievementsIcon.png'
NAME_MAX = 20
RULE = (138, 98, 50, 90)

# Layout, px at 1600x900 (window-local; the window is 1220 x 806 there)
CONTENT_INSET = 28
BODY_TOP = 52               # Board top to the card and the pickers
BODY_GAP = 12               # The body's bottom to the footer
CARD_WIDTH = 350
CARD_GAP = 30
CARD_PAD = 20
PORTRAIT = 124
NAME_HEIGHT = 44
TITLE_HEIGHT = 24
COIN = 58
LEVEL_BAR = 8
TILE_HEIGHT = 76
TILE_GAP = 10
ACH_ROW = 40
TROPHY_SMALL = 30
HEAD_HEIGHT = 30
SUB_HEIGHT = 24
TITLE_COLS = 4
TITLE_CHIP = 34
TITLE_GAP = 8
PICK_ICON = 58
PICK_GAP = 9
PICK_COLS = 9
FOOTER_GAP = 16
BUTTON_WIDTH = 230
BUTTON_GAP = 20


def win_line(wins, finished):
    """(played, '210 played · 100%') - the games played never fewer than the wins (see the
    module docstring)."""
    played = max(int(finished or 0), int(wins or 0))
    rate = f"{round(100 * wins / played)}%" if played else "–"
    return played, f"{played:,} played · {rate}"


class ProfilePanel:
    """The Profile window over a MainMenu (`menu`), drawn with a MenuKit (`kit`)."""

    title = "Profile"

    def __init__(self, menu, kit):
        self.menu = menu
        self.kit = kit
        self.anim = WindowAnim()
        self.editing = False         # Typing the name
        self.hover = None
        self.mouse = (0, 0)
        self._flash = None
        self._layout = None
        self._load()

    # ------------------------------------------------------------ data

    def _load(self):
        """Titles, portraits, level and stats as they are now."""
        achievements = achievement_manager.get_all_achievements()
        by_title, by_icon = {}, {}
        for a in achievements:
            for kind, rid in ((a.get('reward_type'), a.get('reward_id')),
                              (a.get('reward_type_2'), a.get('reward_id_2'))):
                if kind == 'title' and rid:
                    by_title[rid] = a
                elif kind == 'icon' and rid:
                    by_icon[rid] = a
        self.titles = [(t, bool(by_title.get(t) and by_title[t]['earned']), by_title.get(t))
                       for t in ALL_TITLES]
        menu = self.menu
        self.heroes = [(0, None, "Default")] + [
            (i + 1, f"assets/heroes/{name}", menu.hero_icon_names[i + 1] if i + 1 < len(menu.hero_icon_names)
             else name) for i, name in enumerate(menu.HERO_ICON_FILES)]
        rewards = [(p, menu.reward_icon_names.get(p, p.split('/')[-1].replace('.png', '')),
                    bool(by_icon.get(p) and by_icon[p]['earned']), by_icon.get(p))
                   for p in ALL_REWARD_ICON_PATHS]
        # Unlocked first (as the old panel), each part in the game's own order
        self.rewards = [r for r in rewards if r[2]] + [r for r in rewards if not r[2]]
        self.level = player_level_manager.get_progress()
        stats = achievement_manager.stats
        self.custom = (stats.get('custom_game_ai_wins', 0), stats.get('custom_games_ai_finished', 0))
        self.multi = (stats.get('multiplayer_wins', 0), stats.get('multiplayer_games_finished', 0))
        self.earned = sum(1 for a in achievements if a['earned'])
        self.total = len(achievements)
        self._layout = None

    def portrait_path(self, icon):
        """The image of a saved icon: None for the default '?', a hero, a reward path."""
        if isinstance(icon, str):
            return icon if icon in ALL_REWARD_ICON_PATHS else None
        for key, path, _name in self.heroes:
            if key == icon:
                return path
        return None

    # ------------------------------------------------------------ open / close

    def prewarm(self):
        """Decode the portraits once and build the card's sprites now (MainMenu creation)."""
        k = self.kit
        paths = [p for _k, p, _n in self.heroes if p] + list(ALL_REWARD_ICON_PATHS)
        k.preload_icons(paths, [k.px(PICK_ICON) - 2, k.px(PORTRAIT) - 2])
        k.preload_icons([TROPHY_ICON], [k.px(TROPHY_SMALL)])
        for _key, path, _name in self.heroes:
            for state in ('normal', 'hover'):
                k.medal(path, k.px(PICK_ICON), True, state, glow=False)
        for path, _name, unlocked, _ach in self.rewards:
            for state in ('normal', 'hover'):
                k.medal(path, k.px(PICK_ICON), unlocked, state, glow=False)
        scratch = pygame.Surface(self.rect().size, pygame.SRCALPHA)
        self.draw(scratch, 0, 0)
        L = self.layout()
        size = next(iter(L['titles'].values())).size if L['titles'] else (10, 10)
        for title, unlocked, _ach in self.titles:
            k.title_chip(size, title, True, False, 'normal')
            k.title_chip(size, title, False, not unlocked, 'hover')
        self.kit.backdrop()

    def open(self):
        """Opened with MainMenu's pending values already set (_open_profile)."""
        achievement_manager.load()
        self._load()
        self.editing = False
        self.hover = None
        self.anim.open()

    def close(self):
        self.editing = False
        self.anim.close()

    def update(self, dt):
        self.anim.update(dt)

    # ------------------------------------------------------------ geometry

    def rect(self):
        return self.kit.window_rect()

    def layout(self):
        """Window-local rects (computed once per opening)."""
        if self._layout is not None:
            return self._layout
        k = self.kit
        px = k.px
        w, h = self.rect().size
        b = k.border()
        inner_x = b + px(CONTENT_INSET)
        inner_w = w - 2 * inner_x
        L = {}
        btn_w, btn_h = k.button_size(BUTTON_WIDTH)
        footer_y = h - b - px(FOOTER_GAP) - btn_h
        total = 2 * btn_w + px(BUTTON_GAP)
        L['cancel'] = pygame.Rect((w - total) // 2, footer_y, btn_w, btn_h)
        L['save'] = pygame.Rect(L['cancel'].right + px(BUTTON_GAP), footer_y, btn_w, btn_h)
        top = b + px(BODY_TOP)
        body_h = footer_y - px(BODY_GAP) - top
        card = pygame.Rect(inner_x, top, px(CARD_WIDTH), body_h)
        L['card'] = card
        pad = px(CARD_PAD)
        # The card's content, centred top to bottom in it
        content_h = (px(PORTRAIT) + px(10) + px(NAME_HEIGHT) + px(2) + px(TITLE_HEIGHT) + px(18)
                     + px(COIN) + px(18) + px(TILE_HEIGHT) + px(16) + px(ACH_ROW))
        y = card.y + max(pad, (card.h - content_h) // 2)
        L['portrait'] = pygame.Rect(card.centerx - px(PORTRAIT) // 2, y, px(PORTRAIT), px(PORTRAIT))
        y += px(PORTRAIT) + px(10)
        L['name'] = pygame.Rect(card.x + pad, y, card.w - 2 * pad, px(NAME_HEIGHT))
        y += px(NAME_HEIGHT) + px(2)
        L['title_line'] = pygame.Rect(card.x + pad, y, card.w - 2 * pad, px(TITLE_HEIGHT))
        y += px(TITLE_HEIGHT) + px(18)
        L['level'] = pygame.Rect(card.x + pad, y, card.w - 2 * pad, px(COIN))
        y += px(COIN) + px(18)
        tile_w = (card.w - 2 * pad - px(TILE_GAP)) // 2
        L['tiles'] = [pygame.Rect(card.x + pad, y, tile_w, px(TILE_HEIGHT)),
                      pygame.Rect(card.x + pad + tile_w + px(TILE_GAP), y, tile_w, px(TILE_HEIGHT))]
        y += px(TILE_HEIGHT) + px(16)
        L['ach'] = pygame.Rect(card.x + pad, y, card.w - 2 * pad, px(ACH_ROW))
        view = k.small_button("View", 'normal')
        vpad = k.small_button_pad()
        vw, vh = view.get_width() - 2 * vpad, view.get_height() - 2 * vpad
        L['view'] = pygame.Rect(L['ach'].right - vw, L['ach'].centery - vh // 2 + px(4), vw, vh)

        # Pickers, right of the card
        x0 = card.right + px(CARD_GAP)
        pw = inner_x + inner_w - x0
        y = top
        L['title_head'] = pygame.Rect(x0, y, pw, px(HEAD_HEIGHT))
        no_title = k.text("No title", 'pick_note', PARCHMENT_DIM)
        L['no_title'] = pygame.Rect(x0 + pw - no_title.get_width(), y + (px(HEAD_HEIGHT) - no_title.get_height()) // 2,
                                    no_title.get_width(), no_title.get_height())
        y += px(HEAD_HEIGHT) + px(8)
        cw = (pw - (TITLE_COLS - 1) * px(TITLE_GAP)) // TITLE_COLS
        titles = {}
        for i, (title, _unlocked, _ach) in enumerate(self.titles):
            col, row = i % TITLE_COLS, i // TITLE_COLS
            titles[title] = pygame.Rect(x0 + col * (cw + px(TITLE_GAP)),
                                        y + row * (px(TITLE_CHIP) + px(TITLE_GAP)), cw, px(TITLE_CHIP))
        L['titles'] = titles
        rows = -(-len(self.titles) // TITLE_COLS)
        y += rows * px(TITLE_CHIP) + max(0, rows - 1) * px(TITLE_GAP) + px(22)
        L['portrait_head'] = pygame.Rect(x0, y, pw, px(HEAD_HEIGHT))
        y += px(HEAD_HEIGHT) + px(2)
        L['heroes_head'] = pygame.Rect(x0, y, pw, px(SUB_HEIGHT))
        y += px(SUB_HEIGHT) + px(4)
        portraits = {}
        step = px(PICK_ICON) + px(PICK_GAP)
        for i, (key, _path, _name) in enumerate(self.heroes):
            portraits[key] = pygame.Rect(x0 + (i % PICK_COLS) * step, y + (i // PICK_COLS) * step,
                                         px(PICK_ICON), px(PICK_ICON))
        y += -(-len(self.heroes) // PICK_COLS) * step + px(10)
        L['rewards_head'] = pygame.Rect(x0, y, pw, px(SUB_HEIGHT))
        y += px(SUB_HEIGHT) + px(4)
        for i, (path, _name, _unlocked, _ach) in enumerate(self.rewards):
            portraits[path] = pygame.Rect(x0 + (i % PICK_COLS) * step, y + (i // PICK_COLS) * step,
                                          px(PICK_ICON), px(PICK_ICON))
        L['portraits'] = portraits
        L['pick_bottom'] = y + -(-len(self.rewards) // PICK_COLS) * step - px(PICK_GAP)
        L['footer_top'] = footer_y
        self._layout = L
        return L

    # ------------------------------------------------------------ hit-testing

    def _local(self, pos):
        rect = self.rect()
        return pos[0] - rect.x, pos[1] - rect.y

    def element_at(self, pos):
        L = self.layout()
        x, y = self._local(pos)
        for key in ('cancel', 'save'):
            if L[key].collidepoint(x, y):
                return ('button', key)
        if L['view'].collidepoint(x, y):
            return ('view',)
        if L['name'].collidepoint(x, y):
            return ('name',)
        if L['no_title'].collidepoint(x, y):
            return ('no_title',)
        for title, r in L['titles'].items():
            if r.collidepoint(x, y):
                return ('title', title)
        for key, r in L['portraits'].items():
            if r.collidepoint(x, y):
                return ('portrait', key)
        return None

    def part_rect(self, element):
        """A control's rect on screen (tests, previews)."""
        L = self.layout()
        kind = element[0]
        if kind == 'button':
            r = L[element[1]]
        elif kind in ('view', 'name', 'no_title'):
            r = L[kind]
        elif kind == 'title':
            r = L['titles'][element[1]]
        else:
            r = L['portraits'][element[1]]
        return r.move(self.rect().topleft)

    def update_hover(self, pos):
        self.mouse = pos
        self.hover = self.element_at(pos) if self.anim.interactive else None

    # ------------------------------------------------------------ input

    def _click(self, element):
        sound_manager.play_ui_click()
        self._flash = (element, pygame.time.get_ticks() + CLICK_FLASH_DURATION_MS)

    def _unlocked_icon(self, key):
        if isinstance(key, str):
            return any(p == key and unlocked for p, _n, unlocked, _a in self.rewards)
        return True

    def handle_click(self, pos):
        """A left click: 'save' | 'cancel' | 'view' for MainMenu, else None."""
        if not self.anim.interactive:
            return None
        element = self.element_at(pos)
        menu = self.menu
        if element == ('name',):
            if not menu._steam_name_active:
                self.editing = True
            return None
        self.editing = False
        if element is None:
            return None
        kind = element[0]
        if kind == 'button':
            self._click(element)
            return element[1]
        if kind == 'view':
            self._click(element)
            return 'view'
        if kind == 'no_title':
            if menu.temp_selected_title is not None:
                self._click(element)
                menu.temp_selected_title = None
        elif kind == 'title':
            unlocked = next((u for t, u, _a in self.titles if t == element[1]), False)
            if unlocked and menu.temp_selected_title != element[1]:
                self._click(element)
                menu.temp_selected_title = element[1]
        elif kind == 'portrait':
            if self._unlocked_icon(element[1]) and menu.temp_player_icon != element[1]:
                self._click(element)
                menu.temp_player_icon = element[1]
        return None

    def handle_escape(self):
        """Esc while typing the name stops typing (True); else MainMenu cancels (False)."""
        if self.editing:
            self.editing = False
            return True
        return False

    def handle_key(self, event):
        """Typing edits the name while editing; Enter ends the typing, or else saves ('save')."""
        menu = self.menu
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.editing:
                self.editing = False
                return None
            return 'save'
        if not self.editing:
            return None
        if event.key == pygame.K_BACKSPACE:
            menu.temp_player_name = menu.temp_player_name[:-1]
        elif event.unicode and event.unicode.isprintable() and len(menu.temp_player_name) < NAME_MAX:
            menu.temp_player_name += event.unicode
        return None

    def _state(self, element):
        if self._flash and self._flash[0] == element and pygame.time.get_ticks() < self._flash[1]:
            return 'flash'
        if self.hover == element:
            return 'hover'
        return 'normal'

    # ------------------------------------------------------------ drawing (WindowStage)

    def static_key(self):
        return ('profile',)     # The fixed parts never change while the window is open

    def draw(self, surface, ox, oy):
        self.draw_static(surface, ox, oy)
        self.draw_dynamic(surface, ox, oy)

    def draw_static(self, surface, ox, oy):
        """Board, title plate, the card's plate / level / stats, the pickers' headings and
        portraits (their highlights and the choices are dynamic)."""
        k = self.kit
        px = k.px
        L = self.layout()
        w, h = self.rect().size
        surface.blit(k.window((w, h)), (ox, oy))
        banner = k.banner(self.title)
        surface.blit(banner, (ox + (w - banner.get_width()) // 2, oy - k.banner_overhang()))
        card = L['card'].move(ox, oy)
        surface.blit(k.card_plate(card.size), card.topleft)
        self._draw_level(surface, L['level'].move(ox, oy))
        for r, (label, (wins, finished)) in zip(L['tiles'], (("Custom games", self.custom),
                                                             ("Multiplayer", self.multi))):
            self._draw_tile(surface, r.move(ox, oy), label, wins, finished)
        ach = L['ach'].move(ox, oy)
        surface.fill(RULE[:3], (ach.x, ach.y, ach.w, 1))
        trophy = k.icon(TROPHY_ICON, px(TROPHY_SMALL))
        ty = ach.centery - trophy.get_height() // 2 + px(4)
        surface.blit(trophy, (ach.x, ty))
        x = ach.x + trophy.get_width() + px(10)
        num = k.text(str(self.earned), 'ach_num', GOLD_LIGHT)
        rest = k.text(f"of {self.total} achievements", 'ach_line', PARCHMENT)
        cy = ach.centery + px(4)
        surface.blit(num, (x, cy - num.get_height() // 2))
        surface.blit(rest, (x + num.get_width() + px(6), cy - rest.get_height() // 2))

        # Pickers
        unlocked_titles = sum(1 for _t, u, _a in self.titles if u)
        self._draw_heading(surface, L['title_head'].move(ox, oy), "Title",
                           f"{unlocked_titles} of {len(self.titles)} unlocked")
        self._draw_heading(surface, L['portrait_head'].move(ox, oy), "Portrait", None)
        self._draw_sub(surface, L['heroes_head'].move(ox, oy), "Heroes")
        unlocked_rewards = sum(1 for _p, _n, u, _a in self.rewards if u)
        self._draw_sub(surface, L['rewards_head'].move(ox, oy),
                       f"Achievement rewards · {unlocked_rewards} of {len(self.rewards)} unlocked")
        pad = k.medal_pad()
        size = px(PICK_ICON)
        for key, path, _name in self.heroes:
            r = L['portraits'][key].move(ox, oy)
            surface.blit(k.medal(path, size, True, glow=False), (r.x - pad, r.y - pad))
        for path, _name, unlocked, _ach in self.rewards:
            r = L['portraits'][path].move(ox, oy)
            surface.blit(k.medal(path, size, unlocked, glow=False), (r.x - pad, r.y - pad))

    def _draw_heading(self, surface, r, text, note):
        k = self.kit
        head = k.text(text.upper(), 'pick_head', GOLD, spacing=0.14)
        surface.blit(head, (r.x, r.centery - head.get_height() // 2))
        if note:
            n = k.text(note, 'pick_note', PARCHMENT_DIM)
            surface.blit(n, (r.x + head.get_width() + k.px(12), r.centery - n.get_height() // 2 + k.px(1)))

    def _draw_sub(self, surface, r, text):
        k = self.kit
        sub = k.text(text.upper(), 'pick_sub', PARCHMENT_DIM, spacing=0.12)
        surface.blit(sub, (r.x, r.centery - sub.get_height() // 2))

    def _draw_level(self, surface, r):
        k = self.kit
        px = k.px
        lv = self.level
        coin = k.coin(px(COIN))
        cpad = k.coin_pad()
        surface.blit(coin, (r.x - cpad, r.y - cpad))
        num = k.text(str(lv['level']), 'lvl_num', GOLD_LIGHT)
        surface.blit(num, num.get_rect(center=(r.x + px(COIN) // 2, r.y + px(COIN) // 2)))
        x = r.x + px(COIN) + px(12)
        meta_w = r.right - x
        top = k.text(f"Level {lv['level']}", 'lvl', PARCHMENT)
        surface.blit(top, (x, r.y + px(2)))
        at_max = lv['level'] >= MAX_LEVEL or not lv.get('xp_for_next')
        bar = k.bar((meta_w, px(LEVEL_BAR)), 1.0 if at_max else lv['progress_fraction'])
        bar_y = r.y + px(2) + top.get_height() + px(5)
        surface.blit(bar, (x, bar_y))
        if at_max:
            left, right = k.text("Max level", 'lvl_small', PARCHMENT_DIM), None
        else:
            left = k.text(f"{lv['xp_into_level']:,} / {lv['xp_for_next']:,} XP", 'lvl_small', PARCHMENT_DIM)
            right = k.text(f"Level {lv['level'] + 1} next", 'lvl_small', PARCHMENT_DIM)
        row_y = bar_y + bar.get_height() + px(5)
        surface.blit(left, (x, row_y))
        if right:
            surface.blit(right, (r.right - right.get_width(), row_y))

    def _draw_tile(self, surface, r, label, wins, finished):
        k = self.kit
        px = k.px
        surface.blit(k.tile(r.size), r.topleft)
        _played, line = win_line(wins, finished)
        x, y = r.x + px(10), r.y + px(8)
        key = k.text(label.upper(), 'tile_k', PARCHMENT_DIM, spacing=0.12)
        surface.blit(key, (x, y))
        y += key.get_height() + px(2)
        value = k.text(f"{wins:,}", 'tile_v', GOLD_LIGHT)
        surface.blit(value, (x, y))
        word = k.text("wins", 'tile_s', PARCHMENT_DIM)
        surface.blit(word, (x + value.get_width() + px(6), y + value.get_height() - word.get_height() - px(4)))
        y += value.get_height()
        sub = k.text(k.fit(line, 'tile_s', r.w - px(20)), 'tile_s', PARCHMENT_DIM)
        surface.blit(sub, (x, y))

    def draw_dynamic(self, surface, ox, oy):
        """The chosen portrait, the name, the title line, the choices and highlights, the
        buttons and a tooltip."""
        k = self.kit
        px = k.px
        L = self.layout()
        menu = self.menu

        # The card's portrait, name and title
        portrait = L['portrait'].move(ox, oy)
        icon = menu.temp_player_icon
        big = k.medal(self.portrait_path(icon), portrait.w, True)
        pad = k.medal_pad()
        surface.blit(big, (portrait.x - pad, portrait.y - pad))
        self._draw_name(surface, L['name'].move(ox, oy))
        line = L['title_line'].move(ox, oy)
        title = menu.temp_selected_title
        if title:
            text = k.text(title.upper(), 'ptitle', GOLD_TEXT, spacing=0.2)
            rule_color = GOLD_DARK
        else:
            text = k.text("NO TITLE", 'ptitle', PARCHMENT_FAINT, spacing=0.2)
            rule_color = (70, 52, 30)
        tx = line.centerx - text.get_width() // 2
        surface.blit(text, (tx, line.centery - text.get_height() // 2))
        rule_w = px(26)
        for rx in (tx - px(10) - rule_w, tx + text.get_width() + px(10)):
            surface.fill(rule_color, (rx, line.centery, rule_w, 1))

        view = L['view'].move(ox, oy)
        sprite = k.small_button("View", self._state(('view',)))
        vpad = k.small_button_pad()
        surface.blit(sprite, (view.x - vpad, view.y - vpad))

        # Titles
        for t, unlocked, _ach in self.titles:
            r = L['titles'][t].move(ox, oy)
            on = t == title
            state = 'normal' if (on or not unlocked) else self._state(('title', t))
            surface.blit(k.title_chip(r.size, t, on, not unlocked, state), r.topleft)
        no_title = L['no_title'].move(ox, oy)
        lit = self._state(('no_title',)) != 'normal'
        text = k.text("No title", 'pick_note', GOLD_LIGHT if lit else PARCHMENT_DIM)
        surface.blit(text, no_title.topleft)
        surface.fill(GOLD if lit else GOLD_DARK, (no_title.x, no_title.bottom, no_title.w, 1))

        # The hovered portrait lit, the chosen one ringed
        size = px(PICK_ICON)
        hovered = self.hover[1] if self.hover and self.hover[0] == 'portrait' else None
        if hovered is not None and self._unlocked_icon(hovered):
            r = L['portraits'][hovered].move(ox, oy)
            path = self.portrait_path(hovered) if not isinstance(hovered, str) else hovered
            sprite = k.medal(path, size, True, self._state(('portrait', hovered)), glow=False)
            surface.blit(sprite, (r.x - pad, r.y - pad))
        if icon in L['portraits']:
            r = L['portraits'][icon].move(ox, oy)
            surface.blit(k.ring(r.size), (r.x - k.ring_offset(), r.y - k.ring_offset()))

        for key, label in (('cancel', "Cancel"), ('save', "Save")):
            k.draw_button(surface, L[key].move(ox, oy), label, self._state(('button', key)),
                          primary=(key == 'save'))
        self._draw_tooltip(surface)

    def _draw_name(self, surface, r):
        k = self.kit
        px = k.px
        menu = self.menu
        steam = menu._steam_name_active
        name = menu.temp_player_name or ""
        tag = k.tag("Steam") if steam else None
        room = r.w - (tag.get_width() + px(8) if tag else 0)
        text = k.text(k.fit(name, 'pname', room) if name else " ", 'pname', PARCHMENT)
        total = text.get_width() + (tag.get_width() + px(8) if tag else 0)
        x = r.centerx - total // 2
        y = r.centery - text.get_height() // 2
        surface.blit(text, (x, y))
        if tag:
            surface.blit(tag, (x + text.get_width() + px(8), r.centery - tag.get_height() // 2))
        elif self.editing or self.hover == ('name',):
            # The underline that says "type here": gold while typing, bronze on hover
            color = GOLD if self.editing else GOLD_DARK
            surface.fill(color, (r.x + px(20), r.bottom - px(4), r.w - px(40), max(1, px(2)) if self.editing else 1))
            if self.editing and (pygame.time.get_ticks() // 500) % 2 == 0:
                cx = x + (text.get_width() if name else 0) + px(2)
                pygame.draw.line(surface, GOLD_LIGHT, (cx, r.y + px(8)), (cx, r.bottom - px(9)), max(1, px(2)))

    def _draw_tooltip(self, surface):
        """What a locked title / portrait needs, or whose portrait it is."""
        if not self.hover or self.hover[0] not in ('title', 'portrait'):
            return
        k = self.kit
        if self.hover[0] == 'title':
            t = self.hover[1]
            _t, unlocked, ach = next(entry for entry in self.titles if entry[0] == t)
            head, lines = t, self._source_lines(unlocked, ach)
        else:
            key = self.hover[1]
            if isinstance(key, str):
                entry = next(r for r in self.rewards if r[0] == key)
                head, lines = entry[1], self._source_lines(entry[2], entry[3])
            else:
                entry = next(h for h in self.heroes if h[0] == key)
                head, lines = entry[2], ["Hero portrait" if key else "No portrait"]
        tip = k.tooltip(head, tuple(lines))
        x, y = self.mouse[0] + k.px(18), self.mouse[1] + k.px(20)
        bounds = surface.get_rect()
        if x + tip.get_width() > bounds.right:
            x = self.mouse[0] - tip.get_width() - k.px(12)
        if y + tip.get_height() > bounds.bottom:
            y = self.mouse[1] - tip.get_height() - k.px(12)
        surface.blit(tip, (x, y))

    @staticmethod
    def _source_lines(unlocked, ach):
        if ach is None:
            return ["Coming soon"]
        if unlocked:
            return [f"From: {ach['name']}"]
        return [f"Unlock: {ach['name']}", ach['description']]
