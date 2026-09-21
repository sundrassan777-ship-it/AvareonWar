# -*- coding: utf-8 -*-
# save_browser.py
# Saved game browser for loading campaign saves

"""
Save Browser
============

Lists saved game files from the Saves/ directory, showing metadata
(mission, save name, date, turn number). Allows selecting a save to
load or deleting old saves.

Follows the ReplayBrowser standalone screen pattern with own event loop.
"""

import pygame
from config.constants import WHITE, BLACK
from save_manager import scan_saves, delete_save, load_save_file
from global_sound import sound_manager
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.cursor import draw_custom_cursor
from utils.logger import get_logger
from display_utils import menu_frame_cap

logger = get_logger(__name__)

# UI colors (matching replay_browser.py)
BRASS_COLOR = (181, 166, 66)
DARK_BG = (20, 20, 30)
PANEL_BG = (30, 30, 45, 220)
ROW_EVEN = (35, 35, 50, 180)
ROW_ODD = (25, 25, 40, 180)
ROW_HOVER = (55, 55, 75, 200)
ROW_SELECTED = (70, 60, 30, 220)
INFO_TEXT = (200, 200, 210)
DIM_TEXT = (130, 130, 140)
BUTTON_BG = (50, 50, 70)
BUTTON_HOVER = (70, 70, 95)
BUTTON_DISABLED = (40, 40, 50)


class SaveBrowser:
    """
    Saved game browser screen.

    Lists .save.json.gz files from Saves/ directory with metadata.
    Returns selected save data or back action.

    Usage:
        browser = SaveBrowser(screen)
        result = browser.run()
        # result = {'action': 'load', 'path': '...', 'save_data': {...}}
        #       or {'action': 'back'}
        #       or {'action': 'quit'}
    """

    def __init__(self, screen):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        self.clock = pygame.time.Clock()
        self.ui_scale = self.height / 1080.0

        # State
        self.done = False
        self.result = None
        self.selected_index = -1
        self.hovered_index = -1
        self.hovered_button = None
        self.scroll_offset = 0
        self.max_scroll = 0

        # Confirm delete dialog
        self.confirm_delete = False
        self.delete_target_index = -1

        # Load save list (metadata only — full data loaded on demand)
        self.saves = scan_saves()

        # --- Layout ---
        font_path = 'assets/fonts/Cinzel-Regular.ttf'
        bold_path = 'assets/fonts/Cinzel-SemiBold.ttf'
        self.title_font = pygame.font.Font(bold_path, max(18, int(28 * self.ui_scale)))
        self.header_font = pygame.font.Font(bold_path, max(12, int(16 * self.ui_scale)))
        self.row_font = pygame.font.Font(font_path, max(12, int(15 * self.ui_scale)))
        self.small_font = pygame.font.Font(font_path, max(10, int(13 * self.ui_scale)))
        self.btn_font = pygame.font.Font(bold_path, max(14, int(18 * self.ui_scale)))

        # List area
        margin = int(60 * self.ui_scale)
        title_h = int(60 * self.ui_scale)
        bottom_h = int(70 * self.ui_scale)
        self.list_rect = pygame.Rect(
            margin, title_h,
            self.width - 2 * margin,
            self.height - title_h - bottom_h
        )
        self.row_height = int(60 * self.ui_scale)

        # Bottom buttons
        btn_width = int(200 * self.ui_scale)
        btn_height = int(44 * self.ui_scale)
        btn_y = self.height - int(55 * self.ui_scale)
        btn_spacing = int(20 * self.ui_scale)

        self.btn_back = pygame.Rect(margin, btn_y, btn_width, btn_height)
        self.btn_load = pygame.Rect(
            self.width - margin - btn_width, btn_y, btn_width, btn_height)
        self.btn_delete = pygame.Rect(
            self.width - margin - 2 * btn_width - btn_spacing, btn_y, btn_width, btn_height)

        # Column layout for list header
        # Columns: Mission | Save Name | Date | Turn
        self.col_mission_x = int(15 * self.ui_scale)
        self.col_name_x = int(300 * self.ui_scale)
        self.col_date_x = int(550 * self.ui_scale)
        self.col_turn_x = int(780 * self.ui_scale)

        # Background image
        try:
            self.bg_image = pygame.image.load("assets/CampaignBG.png").convert()
            self.bg_image = pygame.transform.smoothscale(self.bg_image, (self.width, self.height))
        except pygame.error:
            self.bg_image = None

        # Text cache
        self._text_cache = {}

        logger.info(f"SaveBrowser: found {len(self.saves)} save files")

    def run(self):
        """Main loop — blocks until user selects or exits."""
        while not self.done:
            self.clock.tick(menu_frame_cap())
            self._handle_events()
            self._render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()
        return self.result

    def _handle_events(self):
        """Process input events."""
        mouse_pos = pygame.mouse.get_pos()

        # Update hovered row
        self.hovered_index = -1
        if self.list_rect.collidepoint(mouse_pos) and not self.confirm_delete:
            relative_y = mouse_pos[1] - self.list_rect.y + self.scroll_offset
            header_h = self.row_height
            if relative_y >= header_h:
                idx = int((relative_y - header_h) / self.row_height)
                if 0 <= idx < len(self.saves):
                    self.hovered_index = idx

        # Update hovered button
        self.hovered_button = None
        if not self.confirm_delete:
            if self.btn_back.collidepoint(mouse_pos):
                self.hovered_button = 'back'
            elif self.btn_load.collidepoint(mouse_pos):
                self.hovered_button = 'load'
            elif self.btn_delete.collidepoint(mouse_pos):
                self.hovered_button = 'delete'

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.result = {'action': 'quit'}
                self.done = True
                return

            elif event.type == _MUSIC_END_EVENT:
                _music_manager.handle_music_end_event()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.confirm_delete:
                        self.confirm_delete = False
                    else:
                        self.result = {'action': 'back'}
                        self.done = True
                elif event.key == pygame.K_RETURN and self.selected_index >= 0:
                    self._load_selected()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.confirm_delete:
                        self._handle_confirm_click(mouse_pos)
                    else:
                        self._handle_left_click(mouse_pos)
                elif event.button == 4:
                    self.scroll_offset = max(0, self.scroll_offset - 30)
                elif event.button == 5:
                    self.scroll_offset = min(self.max_scroll, self.scroll_offset + 30)

    def _handle_left_click(self, mouse_pos):
        """Handle left click."""
        if self.btn_back.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.result = {'action': 'back'}
            self.done = True
        elif self.btn_load.collidepoint(mouse_pos) and self.selected_index >= 0:
            sound_manager.play_ui_click()
            self._load_selected()
        elif self.btn_delete.collidepoint(mouse_pos) and self.selected_index >= 0:
            sound_manager.play_ui_click()
            self.confirm_delete = True
            self.delete_target_index = self.selected_index
        elif self.hovered_index >= 0:
            sound_manager.play_ui_click()
            if self.selected_index == self.hovered_index:
                # Double-click to load
                self._load_selected()
            else:
                self.selected_index = self.hovered_index

    def _handle_confirm_click(self, mouse_pos):
        """Handle click during delete confirmation dialog."""
        dialog_w = int(400 * self.ui_scale)
        dialog_h = int(150 * self.ui_scale)
        dialog_x = (self.width - dialog_w) // 2
        dialog_y = (self.height - dialog_h) // 2

        btn_w = int(120 * self.ui_scale)
        btn_h = int(36 * self.ui_scale)
        confirm_rect = pygame.Rect(
            dialog_x + int(40 * self.ui_scale),
            dialog_y + dialog_h - btn_h - int(20 * self.ui_scale),
            btn_w, btn_h
        )
        cancel_rect = pygame.Rect(
            dialog_x + dialog_w - btn_w - int(40 * self.ui_scale),
            dialog_y + dialog_h - btn_h - int(20 * self.ui_scale),
            btn_w, btn_h
        )

        if confirm_rect.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self._delete_selected(self.delete_target_index)
            self.confirm_delete = False
        elif cancel_rect.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.confirm_delete = False

    def _load_selected(self):
        """Load the full save data for the selected save and return it."""
        if 0 <= self.selected_index < len(self.saves):
            save_meta = self.saves[self.selected_index]
            save_data = load_save_file(save_meta['path'])
            if save_data:
                self.result = {
                    'action': 'load',
                    'path': save_meta['path'],
                    'save_data': save_data,
                }
                self.done = True
            else:
                logger.error(f"SaveBrowser: failed to load save file {save_meta['path']}")

    def _delete_selected(self, index):
        """Delete a save file and remove from list."""
        if 0 <= index < len(self.saves):
            delete_save(self.saves[index]['path'])
            self.saves.pop(index)
            if self.selected_index >= len(self.saves):
                self.selected_index = len(self.saves) - 1

    def _render(self):
        """Render the full browser screen."""
        # Background
        if self.bg_image:
            self.screen.blit(self.bg_image, (0, 0))
        else:
            self.screen.fill(DARK_BG)

        # Darken background for readability
        dark_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        dark_overlay.fill((0, 0, 0, 120))
        self.screen.blit(dark_overlay, (0, 0))

        # Title
        title = self._cached_text("Saved Games", self.title_font, BRASS_COLOR)
        self.screen.blit(title, ((self.width - title.get_width()) // 2, int(15 * self.ui_scale)))

        # List panel background
        panel = pygame.Surface(
            (self.list_rect.width, self.list_rect.height), pygame.SRCALPHA)
        panel.fill(PANEL_BG)
        self.screen.blit(panel, self.list_rect)

        # Clip to list area
        self.screen.set_clip(self.list_rect)

        if not self.saves:
            empty_text = self._cached_text(
                "No saved games found. Save your game from the in-game menu during a campaign.",
                self.row_font, DIM_TEXT)
            self.screen.blit(empty_text, (
                self.list_rect.x + int(20 * self.ui_scale),
                self.list_rect.y + int(30 * self.ui_scale)))
        else:
            self._render_list()

        self.screen.set_clip(None)

        # Bottom buttons
        self._render_btn(self.btn_back, "Return", 'back', enabled=True)
        self._render_btn(self.btn_load, "Load", 'load', enabled=self.selected_index >= 0)
        self._render_btn(self.btn_delete, "Delete", 'delete', enabled=self.selected_index >= 0)

        # Delete confirmation dialog
        if self.confirm_delete:
            self._render_confirm_dialog()

    def _render_list(self):
        """Render the save list with header and rows."""
        x = self.list_rect.x
        w = self.list_rect.width

        # Header row
        header_y = self.list_rect.y
        header_bg = pygame.Surface((w, self.row_height), pygame.SRCALPHA)
        header_bg.fill((40, 40, 55, 200))
        self.screen.blit(header_bg, (x, header_y))

        headers = [
            (self.col_mission_x, "Mission"),
            (self.col_name_x, "Save Name"),
            (self.col_date_x, "Date"),
            (self.col_turn_x, "Turn"),
        ]
        for col_x, label in headers:
            surf = self._cached_text(label, self.header_font, BRASS_COLOR)
            self.screen.blit(surf, (x + col_x, header_y + int(18 * self.ui_scale)))

        # Divider
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (x, header_y + self.row_height - 1),
                         (x + w, header_y + self.row_height - 1), 1)

        # Data rows
        y_start = header_y + self.row_height - self.scroll_offset

        for i, save in enumerate(self.saves):
            row_y = y_start + i * self.row_height

            # Skip if outside visible area
            if row_y + self.row_height < self.list_rect.y:
                continue
            if row_y > self.list_rect.bottom:
                break

            # Row background
            if i == self.selected_index:
                bg_color = ROW_SELECTED
            elif i == self.hovered_index:
                bg_color = ROW_HOVER
            elif i % 2 == 0:
                bg_color = ROW_EVEN
            else:
                bg_color = ROW_ODD

            row_bg = pygame.Surface((w, self.row_height), pygame.SRCALPHA)
            row_bg.fill(bg_color)
            self.screen.blit(row_bg, (x, row_y))

            # Row data
            text_y = row_y + int(18 * self.ui_scale)

            # Mission name
            mission_surf = self._cached_text(
                save.get('mission_text', '?'), self.row_font, INFO_TEXT)
            self.screen.blit(mission_surf, (x + self.col_mission_x, text_y))

            # Save name
            name_surf = self._cached_text(
                save.get('save_name', 'Unnamed'), self.row_font, WHITE)
            self.screen.blit(name_surf, (x + self.col_name_x, text_y))

            # Date
            date_surf = self._cached_text(
                save.get('datetime', '?'), self.small_font, DIM_TEXT)
            self.screen.blit(date_surf, (x + self.col_date_x, text_y + int(2 * self.ui_scale)))

            # Turn number
            turn_surf = self._cached_text(
                str(save.get('turn_number', '?')), self.row_font, INFO_TEXT)
            self.screen.blit(turn_surf, (x + self.col_turn_x, text_y))

        # Update max scroll
        total_h = len(self.saves) * self.row_height
        visible_h = self.list_rect.height - self.row_height  # Minus header
        self.max_scroll = max(0, total_h - visible_h)

    def _render_btn(self, rect, text, btn_id, enabled=True):
        """Render a button."""
        is_hovered = self.hovered_button == btn_id and enabled
        if not enabled:
            bg = BUTTON_DISABLED
            text_color = DIM_TEXT
        elif is_hovered:
            bg = BUTTON_HOVER
            text_color = WHITE
        else:
            bg = BUTTON_BG
            text_color = WHITE

        pygame.draw.rect(self.screen, bg, rect, border_radius=6)
        pygame.draw.rect(self.screen, BRASS_COLOR if enabled else DIM_TEXT, rect, 1, border_radius=6)

        surf = self._cached_text(text, self.btn_font, text_color)
        text_rect = surf.get_rect(center=rect.center)
        self.screen.blit(surf, text_rect)

    def _render_confirm_dialog(self):
        """Render delete confirmation dialog overlay."""
        # Dim background
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        # Dialog box
        dialog_w = int(400 * self.ui_scale)
        dialog_h = int(150 * self.ui_scale)
        dialog_x = (self.width - dialog_w) // 2
        dialog_y = (self.height - dialog_h) // 2

        dialog_surf = pygame.Surface((dialog_w, dialog_h), pygame.SRCALPHA)
        dialog_surf.fill((30, 30, 45, 240))
        pygame.draw.rect(dialog_surf, BRASS_COLOR, (0, 0, dialog_w, dialog_h), 2)
        self.screen.blit(dialog_surf, (dialog_x, dialog_y))

        # Title
        title = self._cached_text("Delete Save?", self.header_font, BRASS_COLOR)
        self.screen.blit(title, (
            dialog_x + (dialog_w - title.get_width()) // 2,
            dialog_y + int(20 * self.ui_scale)))

        # Message
        msg = self._cached_text("This action cannot be undone.", self.small_font, INFO_TEXT)
        self.screen.blit(msg, (
            dialog_x + (dialog_w - msg.get_width()) // 2,
            dialog_y + int(55 * self.ui_scale)))

        # Buttons
        btn_w = int(120 * self.ui_scale)
        btn_h = int(36 * self.ui_scale)
        btn_y = dialog_y + dialog_h - btn_h - int(20 * self.ui_scale)

        confirm_rect = pygame.Rect(
            dialog_x + int(40 * self.ui_scale), btn_y, btn_w, btn_h)
        cancel_rect = pygame.Rect(
            dialog_x + dialog_w - btn_w - int(40 * self.ui_scale), btn_y, btn_w, btn_h)

        # Delete button (red tint)
        pygame.draw.rect(self.screen, (120, 40, 40), confirm_rect, border_radius=4)
        pygame.draw.rect(self.screen, (180, 60, 60), confirm_rect, 1, border_radius=4)
        del_text = self._cached_text("Delete", self.btn_font, WHITE)
        self.screen.blit(del_text, del_text.get_rect(center=confirm_rect.center))

        # Cancel button
        pygame.draw.rect(self.screen, BUTTON_BG, cancel_rect, border_radius=4)
        pygame.draw.rect(self.screen, (100, 100, 110), cancel_rect, 1, border_radius=4)
        cancel_text = self._cached_text("Cancel", self.btn_font, WHITE)
        self.screen.blit(cancel_text, cancel_text.get_rect(center=cancel_rect.center))

    def _cached_text(self, text, font, color):
        """Render text with caching."""
        key = (text, id(font), color)
        if key not in self._text_cache:
            self._text_cache[key] = font.render(text, True, color)
        return self._text_cache[key]
