# -*- coding: utf-8 -*-
# Campaign_Text_Tool.py
# Interactive WYSIWYG editor for campaign mission text

"""
CAMPAIGN TEXT EDITOR TOOL
=========================
Edit campaign mission text directly on the OptionsMenuBG panel, exactly as it
appears in-game. Type directly into the panel with a blinking cursor.
- Single centered panel matching MissionScreen rendering
- Top bar: mission and tab selectors
- Ctrl+S to save, text stored in campaign_data.json

Header markup: lines starting with ## are rendered as brass-gold Cinzel-SemiBold headers.
"""

import pygame
import json
import sys
import os

# Initialize Pygame
pygame.init()

# --- Constants ---
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
DARK_GRAY = (40, 40, 40)
DARKER_GRAY = (25, 25, 25)
LIGHT_GRAY = (180, 180, 180)
BRASS_COLOR = (181, 166, 66)
CURSOR_COLOR = (220, 220, 220)
SELECTION_COLOR = (60, 80, 140, 120)
STATUS_GREEN = (80, 200, 80)

# File path for campaign data
DATA_PATH = os.path.join(os.path.dirname(__file__), 'campaign_data.json')

# Mission IDs and tabs
MISSION_IDS = ['mission_1', 'mission_2', 'mission_3', 'mission_4', 'mission_5', 'mission_6']
TABS = ['briefing', 'lore', 'objectives', 'characters']
TAB_LABELS = {'briefing': 'Briefing', 'lore': 'Lore', 'objectives': 'Objectives', 'characters': 'Characters'}


class CampaignTextTool:
    """WYSIWYG editor - type directly into the OptionsMenuBG panel"""

    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Campaign Text Editor")
        self.clock = pygame.time.Clock()
        self.running = True

        # Load data
        self.data = self._load_data()

        # Current selection
        self.current_mission = 'mission_1'
        self.current_tab = 'briefing'

        # Editor state
        self.lines = []  # List of strings, one per line (raw lines split by \n)
        self.cursor_row = 0
        self.cursor_col = 0
        self.scroll_offset = 0  # Pixel offset for scrolling
        self.cursor_blink_timer = 0
        self.cursor_visible = True
        self.selection_start = None  # (row, col) or None
        self.status_message = ""
        self.status_timer = 0

        # Load current text into editor
        self._load_current_text()

        # Load assets
        self.panel_image = pygame.image.load("assets/OptionsMenuBG.png").convert_alpha()

        # Crop campaign button image for selectors
        raw_btn = pygame.image.load("assets/CampaignBTN.png").convert_alpha()
        self.btn_image = self._crop_to_opaque(raw_btn)

        # UI scale based on window height (matching MissionScreen's approach)
        self.ui_scale = WINDOW_HEIGHT / 1080.0

        # Fonts matching MissionScreen sizes
        self.text_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(16, int(24 * self.ui_scale)))
        self.header_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', max(16, int(24 * self.ui_scale)))
        self.ui_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', 15)
        self.ui_font_bold = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', 15)
        self.status_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', 14)

        # Layout
        self.top_bar_height = 60
        self.status_bar_height = 30
        self.hotkey_bar_height = 22

        # Panel area (matching MissionScreen layout proportions)
        panel_margin = int(60 * self.ui_scale)
        panel_top = self.top_bar_height + int(15 * self.ui_scale)
        panel_bottom = WINDOW_HEIGHT - self.status_bar_height - self.hotkey_bar_height - int(10 * self.ui_scale)
        self.panel_rect = pygame.Rect(
            panel_margin, panel_top,
            WINDOW_WIDTH - 2 * panel_margin, panel_bottom - panel_top
        )

        # Text area inside panel (matching MissionScreen's asymmetric padding)
        text_pad_left = int(250 * self.ui_scale)
        text_pad_right = int(80 * self.ui_scale)
        text_pad_top = int(140 * self.ui_scale)
        text_pad_bottom = int(110 * self.ui_scale)
        self.text_rect = pygame.Rect(
            self.panel_rect.x + text_pad_left,
            self.panel_rect.y + text_pad_top,
            self.panel_rect.width - text_pad_left - text_pad_right,
            self.panel_rect.height - text_pad_top - text_pad_bottom
        )

        # Mission selector buttons
        self._build_selector_buttons()

        # Hovered/clicked state for buttons
        self.hovered_btn = None

        # Enable key repeat for smooth typing
        pygame.key.set_repeat(400, 30)

    def _build_selector_buttons(self):
        """Build mission and tab selector button rects in the top bar"""
        btn_h = 36
        btn_y = (self.top_bar_height - btn_h) // 2

        # Mission buttons on the left side
        self.mission_buttons = {}
        x = 10
        for mid in MISSION_IDS:
            label = self.data.get(mid, {}).get('title', mid)
            # Truncate long titles
            if len(label) > 25:
                label = label[:22] + '...'
            w = max(120, self.ui_font.size(label)[0] + 30)
            self.mission_buttons[mid] = {'rect': pygame.Rect(x, btn_y, w, btn_h), 'label': label}
            x += w + 8

        # Tab buttons on the right side of top bar
        self.tab_buttons = {}
        # Start from right edge and work backwards to align right
        total_tab_w = sum(max(100, self.ui_font.size(TAB_LABELS[t])[0] + 30) for t in TABS) + 8 * (len(TABS) - 1)
        x = WINDOW_WIDTH - total_tab_w - 10
        for tab in TABS:
            label = TAB_LABELS[tab]
            w = max(100, self.ui_font.size(label)[0] + 30)
            self.tab_buttons[tab] = {'rect': pygame.Rect(x, btn_y, w, btn_h), 'label': label}
            x += w + 8

    @staticmethod
    def _crop_to_opaque(surface, threshold=128):
        """Crop surface to opaque content"""
        w, h = surface.get_size()
        top, bottom, left, right = h, 0, w, 0
        for y in range(h):
            for x in range(w):
                if surface.get_at((x, y)).a > threshold:
                    top = min(top, y)
                    bottom = max(bottom, y)
                    left = min(left, x)
                    right = max(right, x)
        crop_rect = pygame.Rect(left, top, right - left + 1, bottom - top + 1)
        return surface.subsurface(crop_rect).copy()

    def _load_data(self):
        """Load campaign data from JSON"""
        try:
            with open(DATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Create default structure
            data = {}
            for mid in MISSION_IDS:
                data[mid] = {
                    'title': mid.replace('_', ' ').title(),
                    'briefing': '', 'lore': '', 'objectives': '', 'characters': ''
                }
            return data

    def _save_data(self):
        """Save campaign data to JSON"""
        self._store_current_text()
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        self.status_message = "Saved to campaign_data.json"
        self.status_timer = 180  # ~3 seconds at 60fps

    def _load_current_text(self):
        """Load text for current mission/tab into editor lines"""
        mission = self.data.get(self.current_mission, {})
        raw = mission.get(self.current_tab, '')
        self.lines = raw.split('\n') if raw else ['']
        self.cursor_row = 0
        self.cursor_col = 0
        self.scroll_offset = 0
        self.selection_start = None

    def _store_current_text(self):
        """Store editor lines back to data dict"""
        text = '\n'.join(self.lines)
        if self.current_mission not in self.data:
            self.data[self.current_mission] = {
                'title': self.current_mission.replace('_', ' ').title(),
                'briefing': '', 'lore': '', 'objectives': '', 'characters': ''
            }
        self.data[self.current_mission][self.current_tab] = text

    def _get_line_font(self, line):
        """Return the font for a given raw line (header or regular)"""
        if line.strip().startswith('##'):
            return self.header_font
        return self.text_font

    def _get_line_height(self, line):
        """Get pixel height for a raw line"""
        return self._get_line_font(line).get_linesize()

    def _get_y_for_row(self, target_row):
        """Get the y pixel position for a given row (relative to text area, before scroll)"""
        y = 0
        for r in range(min(target_row, len(self.lines))):
            y += self._get_line_height(self.lines[r])
        return y

    def _draw_scroll_indicator(self, x, y, width, height, total_content):
        """Draw a scroll position indicator bar showing current position in text"""
        if total_content <= 0:
            return
        # Thumb height proportional to visible area vs total content
        visible_ratio = height / total_content
        indicator_height = max(int(20 * self.ui_scale), int(height * visible_ratio))
        # Thumb position proportional to scroll offset
        scroll_range = total_content - height
        if scroll_range > 0:
            scroll_ratio = self.scroll_offset / scroll_range
        else:
            scroll_ratio = 0
        indicator_y = y + int((height - indicator_height) * scroll_ratio)
        # Track background
        track_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (60, 60, 80, 100), track_rect, border_radius=2)
        # Thumb
        indicator_rect = pygame.Rect(x, indicator_y, width, indicator_height)
        pygame.draw.rect(self.screen, (150, 150, 170, 180), indicator_rect, border_radius=2)

    def _get_total_content_height(self):
        """Total pixel height of all lines"""
        return sum(self._get_line_height(line) for line in self.lines)

    def _ensure_cursor_visible(self):
        """Scroll so cursor row is visible within text_rect"""
        cursor_y = self._get_y_for_row(self.cursor_row)
        cursor_lh = self._get_line_height(self.lines[self.cursor_row])

        # If cursor is above visible area, scroll up
        if cursor_y < self.scroll_offset:
            self.scroll_offset = cursor_y

        # If cursor is below visible area, scroll down
        if cursor_y + cursor_lh > self.scroll_offset + self.text_rect.height:
            self.scroll_offset = cursor_y + cursor_lh - self.text_rect.height

    def _get_selection_range(self):
        """Return (start_row, start_col, end_row, end_col) sorted, or None"""
        if self.selection_start is None:
            return None
        sr, sc = self.selection_start
        er, ec = self.cursor_row, self.cursor_col
        if (sr, sc) > (er, ec):
            sr, sc, er, ec = er, ec, sr, sc
        return sr, sc, er, ec

    def _delete_selection(self):
        """Delete selected text, return True if selection existed"""
        sel = self._get_selection_range()
        if sel is None:
            return False
        sr, sc, er, ec = sel
        before = self.lines[sr][:sc]
        after = self.lines[er][ec:]
        self.lines[sr:er + 1] = [before + after]
        self.cursor_row = sr
        self.cursor_col = sc
        self.selection_start = None
        return True

    def _get_selected_text(self):
        """Get selected text as string"""
        sel = self._get_selection_range()
        if sel is None:
            return ''
        sr, sc, er, ec = sel
        if sr == er:
            return self.lines[sr][sc:ec]
        parts = [self.lines[sr][sc:]]
        for r in range(sr + 1, er):
            parts.append(self.lines[r])
        parts.append(self.lines[er][:ec])
        return '\n'.join(parts)

    def _insert_text(self, text):
        """Insert text at cursor, handling newlines"""
        self._delete_selection()
        insert_lines = text.split('\n')
        if len(insert_lines) == 1:
            line = self.lines[self.cursor_row]
            self.lines[self.cursor_row] = line[:self.cursor_col] + insert_lines[0] + line[self.cursor_col:]
            self.cursor_col += len(insert_lines[0])
        else:
            line = self.lines[self.cursor_row]
            before = line[:self.cursor_col]
            after = line[self.cursor_col:]
            self.lines[self.cursor_row] = before + insert_lines[0]
            for i, il in enumerate(insert_lines[1:-1], 1):
                self.lines.insert(self.cursor_row + i, il)
            last_idx = self.cursor_row + len(insert_lines) - 1
            self.lines.insert(last_idx, insert_lines[-1] + after)
            self.cursor_row = last_idx
            self.cursor_col = len(insert_lines[-1])
        self._ensure_cursor_visible()

    def _click_to_cursor(self, mouse_x, mouse_y):
        """Convert mouse position to (row, col) within raw lines"""
        # Convert mouse position to content-space coordinates
        rel_y = mouse_y - self.text_rect.y + self.scroll_offset
        rel_x = mouse_x - self.text_rect.x

        # Find which row was clicked
        y = 0
        row = len(self.lines) - 1  # Default to last line
        for r in range(len(self.lines)):
            lh = self._get_line_height(self.lines[r])
            if rel_y < y + lh:
                row = r
                break
            y += lh

        # Find column within the row
        line = self.lines[row]
        font = self._get_line_font(line)
        col = len(line)
        for c in range(len(line) + 1):
            w = font.size(line[:c])[0]
            if w >= rel_x:
                col = c
                break

        return row, col

    def handle_events(self):
        mouse_pos = pygame.mouse.get_pos()

        # Update hover state for buttons
        self.hovered_btn = None
        for mid, bd in self.mission_buttons.items():
            if bd['rect'].collidepoint(mouse_pos):
                self.hovered_btn = ('mission', mid)
                break
        if not self.hovered_btn:
            for tab, bd in self.tab_buttons.items():
                if bd['rect'].collidepoint(mouse_pos):
                    self.hovered_btn = ('tab', tab)
                    break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._store_current_text()
                self.running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # Mission buttons
                    clicked_btn = False
                    for mid, bd in self.mission_buttons.items():
                        if bd['rect'].collidepoint(mouse_pos):
                            self._store_current_text()
                            self.current_mission = mid
                            self._load_current_text()
                            self._build_selector_buttons()
                            clicked_btn = True
                            break
                    # Tab buttons
                    if not clicked_btn:
                        for tab, bd in self.tab_buttons.items():
                            if bd['rect'].collidepoint(mouse_pos):
                                self._store_current_text()
                                self.current_tab = tab
                                self._load_current_text()
                                clicked_btn = True
                                break
                    # Click in text area - position cursor
                    if not clicked_btn and self.text_rect.collidepoint(mouse_pos):
                        self.cursor_row, self.cursor_col = self._click_to_cursor(mouse_pos[0], mouse_pos[1])
                        self.selection_start = None

                # Scroll
                elif event.button == 4:
                    if self.panel_rect.collidepoint(mouse_pos):
                        self.scroll_offset = max(0, self.scroll_offset - 30)
                elif event.button == 5:
                    if self.panel_rect.collidepoint(mouse_pos):
                        max_scroll = max(0, self._get_total_content_height() - self.text_rect.height)
                        self.scroll_offset = min(max_scroll, self.scroll_offset + 30)

            elif event.type == pygame.KEYDOWN:
                mods = pygame.key.get_mods()
                ctrl = mods & pygame.KMOD_CTRL
                shift = mods & pygame.KMOD_SHIFT

                if ctrl and event.key == pygame.K_s:
                    self._save_data()
                elif ctrl and event.key == pygame.K_a:
                    self.selection_start = (0, 0)
                    self.cursor_row = len(self.lines) - 1
                    self.cursor_col = len(self.lines[-1])
                elif ctrl and event.key == pygame.K_c:
                    text = self._get_selected_text()
                    if text:
                        pygame.scrap.put(pygame.SCRAP_TEXT, text.encode('utf-8'))
                elif ctrl and event.key == pygame.K_v:
                    try:
                        clip = pygame.scrap.get(pygame.SCRAP_TEXT)
                        if clip:
                            text = clip.decode('utf-8').rstrip('\x00')
                            self._insert_text(text)
                    except Exception:
                        pass
                elif ctrl and event.key == pygame.K_x:
                    text = self._get_selected_text()
                    if text:
                        pygame.scrap.put(pygame.SCRAP_TEXT, text.encode('utf-8'))
                        self._delete_selection()

                elif event.key == pygame.K_BACKSPACE:
                    if not self._delete_selection():
                        if self.cursor_col > 0:
                            line = self.lines[self.cursor_row]
                            self.lines[self.cursor_row] = line[:self.cursor_col - 1] + line[self.cursor_col:]
                            self.cursor_col -= 1
                        elif self.cursor_row > 0:
                            prev = self.lines[self.cursor_row - 1]
                            self.cursor_col = len(prev)
                            self.lines[self.cursor_row - 1] = prev + self.lines[self.cursor_row]
                            del self.lines[self.cursor_row]
                            self.cursor_row -= 1
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_DELETE:
                    if not self._delete_selection():
                        line = self.lines[self.cursor_row]
                        if self.cursor_col < len(line):
                            self.lines[self.cursor_row] = line[:self.cursor_col] + line[self.cursor_col + 1:]
                        elif self.cursor_row < len(self.lines) - 1:
                            self.lines[self.cursor_row] = line + self.lines[self.cursor_row + 1]
                            del self.lines[self.cursor_row + 1]

                elif event.key == pygame.K_RETURN:
                    self._delete_selection()
                    line = self.lines[self.cursor_row]
                    self.lines[self.cursor_row] = line[:self.cursor_col]
                    self.lines.insert(self.cursor_row + 1, line[self.cursor_col:])
                    self.cursor_row += 1
                    self.cursor_col = 0
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_LEFT:
                    if shift and self.selection_start is None:
                        self.selection_start = (self.cursor_row, self.cursor_col)
                    elif not shift:
                        self.selection_start = None
                    if self.cursor_col > 0:
                        self.cursor_col -= 1
                    elif self.cursor_row > 0:
                        self.cursor_row -= 1
                        self.cursor_col = len(self.lines[self.cursor_row])
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_RIGHT:
                    if shift and self.selection_start is None:
                        self.selection_start = (self.cursor_row, self.cursor_col)
                    elif not shift:
                        self.selection_start = None
                    if self.cursor_col < len(self.lines[self.cursor_row]):
                        self.cursor_col += 1
                    elif self.cursor_row < len(self.lines) - 1:
                        self.cursor_row += 1
                        self.cursor_col = 0
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_UP:
                    if shift and self.selection_start is None:
                        self.selection_start = (self.cursor_row, self.cursor_col)
                    elif not shift:
                        self.selection_start = None
                    if self.cursor_row > 0:
                        self.cursor_row -= 1
                        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_row]))
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_DOWN:
                    if shift and self.selection_start is None:
                        self.selection_start = (self.cursor_row, self.cursor_col)
                    elif not shift:
                        self.selection_start = None
                    if self.cursor_row < len(self.lines) - 1:
                        self.cursor_row += 1
                        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_row]))
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_HOME:
                    if shift and self.selection_start is None:
                        self.selection_start = (self.cursor_row, self.cursor_col)
                    elif not shift:
                        self.selection_start = None
                    self.cursor_col = 0
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_END:
                    if shift and self.selection_start is None:
                        self.selection_start = (self.cursor_row, self.cursor_col)
                    elif not shift:
                        self.selection_start = None
                    self.cursor_col = len(self.lines[self.cursor_row])
                    self._ensure_cursor_visible()

                elif event.key == pygame.K_ESCAPE:
                    self._store_current_text()
                    self.running = False

                else:
                    # Regular character input
                    if event.unicode and event.unicode.isprintable():
                        self._delete_selection()
                        line = self.lines[self.cursor_row]
                        self.lines[self.cursor_row] = line[:self.cursor_col] + event.unicode + line[self.cursor_col:]
                        self.cursor_col += len(event.unicode)
                        self._ensure_cursor_visible()

    def render(self):
        self.screen.fill(DARKER_GRAY)

        # Top bar background
        pygame.draw.rect(self.screen, DARK_GRAY, (0, 0, WINDOW_WIDTH, self.top_bar_height))

        # Mission selector buttons
        for mid, bd in self.mission_buttons.items():
            self._draw_selector_btn(bd['rect'], bd['label'], mid == self.current_mission,
                                    self.hovered_btn == ('mission', mid))

        # Tab selector buttons
        for tab, bd in self.tab_buttons.items():
            self._draw_selector_btn(bd['rect'], bd['label'], tab == self.current_tab,
                                    self.hovered_btn == ('tab', tab))

        # Draw the panel with text
        self._draw_panel()

        # Hotkey bar (below panel)
        self._draw_hotkey_bar()

        # Status bar
        self._draw_status_bar()

        pygame.display.flip()

    def _draw_selector_btn(self, rect, label, is_selected, is_hovered):
        """Draw a compact selector button"""
        scaled_bg = pygame.transform.smoothscale(self.btn_image, (rect.width, rect.height))
        btn_surface = scaled_bg.copy()

        if is_selected:
            btn_surface.fill((140, 140, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
        else:
            btn_surface.fill((80, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)

        if is_hovered and not is_selected:
            btn_surface.fill((30, 30, 30, 0), special_flags=pygame.BLEND_RGBA_ADD)

        self.screen.blit(btn_surface, rect)

        font = self.ui_font_bold if is_selected else self.ui_font
        color = WHITE if is_selected else LIGHT_GRAY
        text_surface = font.render(label, True, color)
        text_r = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_r)

    def _draw_panel(self):
        """Draw the OptionsMenuBG panel with editable text directly on it"""
        # Panel background
        scaled_panel = pygame.transform.smoothscale(
            self.panel_image, (self.panel_rect.width, self.panel_rect.height)
        )
        # Darken the panel for better text readability (reduced from 140 to 100 for darker background)
        scaled_panel.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(scaled_panel, self.panel_rect)

        # Create a clipping surface for the text area
        clip = pygame.Surface((self.text_rect.width, self.text_rect.height), pygame.SRCALPHA)
        clip.fill((0, 0, 0, 0))

        sel = self._get_selection_range()
        y = -self.scroll_offset  # Start with scroll offset applied

        for row, line in enumerate(self.lines):
            is_header = line.strip().startswith('##')
            font = self.header_font if is_header else self.text_font
            # Headers use brass gold color, regular text is white
            color = BRASS_COLOR if is_header else WHITE
            lh = font.get_linesize()

            # Only render lines within visible area (with some margin)
            if y + lh > 0 and y < self.text_rect.height:
                # Selection highlight
                if sel:
                    sr, sc, er, ec = sel
                    if sr <= row <= er:
                        if sr == er:
                            x1 = font.size(line[:sc])[0]
                            x2 = font.size(line[:ec])[0]
                        elif row == sr:
                            x1 = font.size(line[:sc])[0]
                            x2 = font.size(line)[0] + 5
                        elif row == er:
                            x1 = 0
                            x2 = font.size(line[:ec])[0]
                        else:
                            x1 = 0
                            x2 = font.size(line)[0] + 5
                        sel_surface = pygame.Surface((max(1, x2 - x1), lh), pygame.SRCALPHA)
                        sel_surface.fill(SELECTION_COLOR)
                        clip.blit(sel_surface, (x1, y))

                # Render text
                if line:
                    text_surface = font.render(line, True, color)
                    clip.blit(text_surface, (0, y))

                # Cursor
                if row == self.cursor_row and self.cursor_visible:
                    cx = font.size(line[:self.cursor_col])[0]
                    pygame.draw.line(clip, CURSOR_COLOR, (cx, y + 2), (cx, y + lh - 2), 2)

            y += lh
            if y > self.text_rect.height + 50:
                break  # Stop rendering far below visible area

        self.screen.blit(clip, self.text_rect)

        # Scroll position indicator (only when content overflows)
        total_content_height = self._get_total_content_height()
        max_scroll = max(0, total_content_height - self.text_rect.height)
        if max_scroll > 0:
            bar_w = int(4 * self.ui_scale)
            bar_x = self.text_rect.right - int(44 * self.ui_scale)
            bar_top = self.text_rect.y + int(8 * self.ui_scale)
            bar_h = self.text_rect.height - int(46 * self.ui_scale)  # 8 top + 38 bottom inset
            self._draw_scroll_indicator(bar_x, bar_top,
                                        bar_w, bar_h, total_content_height)

    def _draw_hotkey_bar(self):
        """Draw hotkey reference bar below the panel"""
        bar_y = WINDOW_HEIGHT - self.status_bar_height - self.hotkey_bar_height
        pygame.draw.rect(self.screen, DARK_GRAY, (0, bar_y, WINDOW_WIDTH, self.hotkey_bar_height))
        hotkeys = "Ctrl+S Save  |  Ctrl+C/V/X Copy/Paste/Cut  |  Ctrl+A Select All  |  ## = Header  |  Esc Close"
        hk_surface = self.status_font.render(hotkeys, True, GRAY)
        hk_r = hk_surface.get_rect(centerx=WINDOW_WIDTH // 2, centery=bar_y + self.hotkey_bar_height // 2)
        self.screen.blit(hk_surface, hk_r)

    def _draw_status_bar(self):
        """Draw bottom status bar"""
        bar_y = WINDOW_HEIGHT - self.status_bar_height
        pygame.draw.rect(self.screen, DARK_GRAY, (0, bar_y, WINDOW_WIDTH, self.status_bar_height))

        # Left: cursor position
        pos_text = f"Ln {self.cursor_row + 1}, Col {self.cursor_col + 1}  |  {len(self.lines)} lines"
        pos_surface = self.status_font.render(pos_text, True, LIGHT_GRAY)
        self.screen.blit(pos_surface, (10, bar_y + 7))

        # Center: status message (save confirmation etc.)
        if self.status_timer > 0:
            msg_surface = self.status_font.render(self.status_message, True, STATUS_GREEN)
            msg_r = msg_surface.get_rect(center=(WINDOW_WIDTH // 2, bar_y + self.status_bar_height // 2))
            self.screen.blit(msg_surface, msg_r)

        # Right: current mission/tab indicator
        indicator = f"{self.data.get(self.current_mission, {}).get('title', self.current_mission)}  >  {TAB_LABELS[self.current_tab]}"
        ind_surface = self.status_font.render(indicator, True, LIGHT_GRAY)
        ind_r = ind_surface.get_rect(right=WINDOW_WIDTH - 10, centery=bar_y + self.status_bar_height // 2)
        self.screen.blit(ind_surface, ind_r)

    def run(self):
        """Main loop"""
        # Initialize scrap (clipboard) system
        pygame.scrap.init()

        while self.running:
            self.handle_events()

            # Cursor blink
            self.cursor_blink_timer += 1
            if self.cursor_blink_timer >= 30:
                self.cursor_visible = not self.cursor_visible
                self.cursor_blink_timer = 0

            # Status message countdown
            if self.status_timer > 0:
                self.status_timer -= 1

            self.render()
            self.clock.tick(FPS)

        pygame.quit()


if __name__ == '__main__':
    tool = CampaignTextTool()
    tool.run()
