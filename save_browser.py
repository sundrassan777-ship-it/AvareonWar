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

Visual style matches the campaign house pattern used by MissionScreen
(campaign_screen.py) and RecapScreen: CampaignBG background + OptionsMenuBG
ornate wooden panel + CampaignBTN ornate buttons + Cinzel text.
"""

import pygame
from config.constants import WHITE
from save_manager import scan_saves, delete_save, load_save_file
from global_sound import sound_manager
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.cursor import draw_custom_cursor
from utils.logger import get_logger
from utils.surface_utils import load_cached_image, get_campaign_button_image
from display_utils import menu_frame_cap

logger = get_logger(__name__)

# UI colors — campaign house style. Brass for headings and the primary action,
# warm parchment tones for body text so they sit correctly on the dark wood panel.
BRASS_COLOR = (181, 166, 66)
# Dark brown title on the light parchment band of CampaignBG.png. This is the
# exact value CampaignScreen renders its "Campaign" title in (campaign_screen.py:125),
# reused so the two titles match. Brass has almost no contrast on that band.
TITLE_BROWN = (80, 50, 20)
INFO_TEXT = (226, 216, 190)   # Parchment-warm off-white
DIM_TEXT = (168, 156, 128)    # Warm dim — secondary cells and disabled button labels
ROW_ALT = (255, 255, 255, 12)
ROW_HOVER = (255, 255, 255, 26)
ROW_SELECTED = (181, 166, 66, 46)
FALLBACK_BG = (20, 20, 30)    # Only if CampaignBG.png fails to load

# Aspect ratio of CampaignBTN.png once cropped to its opaque bounds (1502x297).
# Used as a fallback if the asset fails to load.
_BTN_ASPECT_FALLBACK = 0.1977

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
        s = self.ui_scale

        # State
        self.done = False
        self.result = None
        self.selected_index = -1
        self.hovered_index = -1
        self.hovered_button = None
        self.clicked_button = None
        self.scroll_offset = 0
        self.max_scroll = 0

        # Confirm delete dialog
        self.confirm_delete = False
        self.delete_target_index = -1

        # Load save list (metadata only — full data loaded on demand)
        self.saves = scan_saves()

        # --- Assets (decoded once per process, rescaled per instance) ---
        raw_bg = load_cached_image("assets/CampaignBG.png", alpha=False)
        self.bg_image = (pygame.transform.smoothscale(raw_bg, (self.width, self.height))
                         if raw_bg is not None else None)
        if raw_bg is None:
            logger.warning("SaveBrowser: could not load CampaignBG.png")

        self.panel_image = load_cached_image("assets/OptionsMenuBG.png", alpha=True)
        if self.panel_image is None:
            logger.warning("SaveBrowser: could not load OptionsMenuBG.png")

        self.btn_image = get_campaign_button_image()
        if self.btn_image is None:
            logger.warning("SaveBrowser: could not load CampaignBTN.png")
        if self.btn_image is not None:
            bw, bh = self.btn_image.get_size()
            self.btn_aspect = bh / bw
        else:
            self.btn_aspect = _BTN_ASPECT_FALLBACK

        # --- Fonts (direct Font(), NOT font_manager — it remaps weights bolder) ---
        font_path = 'assets/fonts/Cinzel-Regular.ttf'
        bold_path = 'assets/fonts/Cinzel-SemiBold.ttf'
        self.title_font = pygame.font.Font(bold_path, max(20, int(48 * s)))
        self.header_font = pygame.font.Font(bold_path, max(14, int(22 * s)))
        self.row_font = pygame.font.Font(font_path, max(14, int(24 * s)))
        self.small_font = pygame.font.Font(font_path, max(12, int(20 * s)))
        self.btn_font = pygame.font.Font(font_path, max(16, int(24 * s)))
        self.primary_font = pygame.font.Font(bold_path, max(16, int(24 * s)))
        self.dialog_title_font = pygame.font.Font(bold_path, max(16, int(28 * s)))
        self.dialog_msg_font = pygame.font.Font(font_path, max(14, int(20 * s)))

        # --- Layout ---
        # Title sits on the parchment band above the panel. Pre-rendered once.
        self.title_surface = self.title_font.render("Saved Games", True, TITLE_BROWN)
        self.title_rect = self.title_surface.get_rect(
            centerx=self.width // 2, top=int(30 * s))

        # Bottom buttons — height derives from the cropped button art's aspect,
        # mirroring MissionScreen (campaign_screen.py:519-529).
        btn_width = int(400 * s)
        btn_height = int(btn_width * self.btn_aspect)
        btn_y = self.height - btn_height - int(30 * s)
        btn_margin = int(40 * s)
        btn_spacing = int(20 * s)

        self.btn_back = pygame.Rect(btn_margin, btn_y, btn_width, btn_height)
        self.btn_load = pygame.Rect(
            self.width - btn_margin - btn_width, btn_y, btn_width, btn_height)
        self.btn_delete = pygame.Rect(
            self.btn_load.left - btn_spacing - btn_width, btn_y, btn_width, btn_height)

        # Ornate panel between the title and the button row
        panel_margin = int(60 * s)
        panel_top = self.title_rect.bottom + int(20 * s)
        panel_bottom = btn_y - int(20 * s)
        self.panel_rect = pygame.Rect(
            panel_margin, panel_top,
            max(1, self.width - 2 * panel_margin),
            max(1, panel_bottom - panel_top)
        )

        # Inner content area. Padding is asymmetric because OptionsMenuBG.png's
        # carved border is much wider on the left. Values proven by recap_screen.
        pad_left = int(215 * s)
        pad_right = int(230 * s)
        pad_top = int(150 * s)
        pad_bottom = int(145 * s)
        self.list_rect = pygame.Rect(
            self.panel_rect.x + pad_left,
            self.panel_rect.y + pad_top,
            max(1, self.panel_rect.width - pad_left - pad_right),
            max(1, self.panel_rect.height - pad_top - pad_bottom)
        )

        # Header / rows split. rows_rect is the single source of truth for
        # hit-testing, clipping and scroll bounds — keep them derived from it.
        self.header_h = int(52 * s)
        self.divider_y = self.list_rect.y + self.header_h
        self.rows_rect = pygame.Rect(
            self.list_rect.x,
            self.divider_y + int(4 * s),
            self.list_rect.width,
            max(1, self.list_rect.bottom - self.divider_y - int(4 * s))
        )
        self.row_height = max(1, int(64 * s))
        self.scroll_gutter = int(16 * s)
        self.content_w = max(1, self.rows_rect.width - self.scroll_gutter)

        # Columns as fractions of rows_rect.width so they stay proportional at
        # any aspect ratio: (label, start_fraction, end_fraction, alignment)
        self.columns = [
            ("Mission",   0.00, 0.30, 'left'),
            ("Save Name", 0.30, 0.62, 'left'),
            ("Date",      0.62, 0.86, 'left'),
            ("Turn",      0.86, 1.00, 'right'),
        ]
        self.col_pad = int(12 * s)

        # --- Pre-built surfaces (never allocate per-frame) ---
        if self.panel_image is not None:
            self._scaled_panel = pygame.transform.smoothscale(
                self.panel_image, self.panel_rect.size)
            self._scaled_panel.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
        else:
            self._scaled_panel = pygame.Surface(self.panel_rect.size, pygame.SRCALPHA)
            self._scaled_panel.fill((30, 24, 16, 230))
            pygame.draw.rect(self._scaled_panel, BRASS_COLOR,
                             self._scaled_panel.get_rect(), 2)

        # One reusable surface per row state
        row_size = (self.content_w, self.row_height)
        self._row_alt = pygame.Surface(row_size, pygame.SRCALPHA)
        self._row_alt.fill(ROW_ALT)
        self._row_hover = pygame.Surface(row_size, pygame.SRCALPHA)
        self._row_hover.fill(ROW_HOVER)
        self._row_selected = pygame.Surface(row_size, pygame.SRCALPHA)
        self._row_selected.fill(ROW_SELECTED)

        # Dim used only behind the confirmation dialog
        self._dim_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._dim_overlay.fill((0, 0, 0, 150))

        # Dialog panel, scaled to the dialog rect from _confirm_dialog_rects()
        dialog_rect = self._confirm_dialog_rects()[0]
        if self.panel_image is not None:
            self._scaled_dialog = pygame.transform.smoothscale(
                self.panel_image, dialog_rect.size)
            self._scaled_dialog.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
        else:
            self._scaled_dialog = pygame.Surface(dialog_rect.size, pygame.SRCALPHA)
            self._scaled_dialog.fill((30, 24, 16, 240))
            pygame.draw.rect(self._scaled_dialog, BRASS_COLOR,
                             self._scaled_dialog.get_rect(), 2)

        # Caches. id(font) is a stable key here because every font is held as an
        # instance attribute for this object's whole lifetime.
        self._btn_cache = {}
        self._text_cache = {}
        self._fit_cache = {}

        self._recompute_scroll_bounds()

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

        # Update hovered row. rows_rect starts below the divider, so no header
        # allowance is needed here.
        self.hovered_index = -1
        if not self.confirm_delete and self.rows_rect.collidepoint(mouse_pos):
            relative_y = mouse_pos[1] - self.rows_rect.y + self.scroll_offset
            if relative_y >= 0:
                idx = int(relative_y // self.row_height)
                if 0 <= idx < len(self.saves):
                    self.hovered_index = idx

        # Update hovered button (disabled buttons must not light up)
        self.hovered_button = None
        if self.confirm_delete:
            _dialog, confirm_rect, cancel_rect = self._confirm_dialog_rects()
            if confirm_rect.collidepoint(mouse_pos):
                self.hovered_button = 'confirm_delete'
            elif cancel_rect.collidepoint(mouse_pos):
                self.hovered_button = 'confirm_cancel'
        else:
            if self.btn_back.collidepoint(mouse_pos):
                self.hovered_button = 'back'
            elif self.btn_load.collidepoint(mouse_pos) and self.selected_index >= 0:
                self.hovered_button = 'load'
            elif self.btn_delete.collidepoint(mouse_pos) and self.selected_index >= 0:
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
            self.clicked_button = 'back'
            self.result = {'action': 'back'}
            self.done = True
        elif self.btn_load.collidepoint(mouse_pos) and self.selected_index >= 0:
            sound_manager.play_ui_click()
            self.clicked_button = 'load'
            self._load_selected()
        elif self.btn_delete.collidepoint(mouse_pos) and self.selected_index >= 0:
            sound_manager.play_ui_click()
            self.clicked_button = 'delete'
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
        _dialog, confirm_rect, cancel_rect = self._confirm_dialog_rects()

        if confirm_rect.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'confirm_delete'
            self._delete_selected(self.delete_target_index)
            self.confirm_delete = False
        elif cancel_rect.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'confirm_cancel'
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
            # The list shrank: re-derive scroll bounds and drop stale text surfaces
            self._recompute_scroll_bounds()
            self.scroll_offset = min(self.scroll_offset, self.max_scroll)
            self._text_cache.clear()
            self._fit_cache.clear()

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _recompute_scroll_bounds(self):
        """Re-derive max_scroll. Must never be done from the render path."""
        total_h = len(self.saves) * self.row_height
        self.max_scroll = max(0, total_h - self.rows_rect.height)

    def _confirm_dialog_rects(self):
        """
        Single source of truth for the confirm dialog's geometry, used by both
        the click handler and the renderer so hit-testing can never drift.

        Inner offsets are fractions of the dialog, not N * ui_scale: the ornate
        border's on-screen thickness scales with the panel it is drawn into, so
        this small dialog needs proportional padding, not the panel's ~205px.
        """
        s = self.ui_scale
        dw = int(660 * s)
        # Keep the frame's native 1979x1503 aspect so the border is not distorted
        dh = int(dw * 1503 / 1979)
        dialog = pygame.Rect((self.width - dw) // 2, (self.height - dh) // 2, dw, dh)

        bw = int(200 * s)
        bh = max(1, int(bw * self.btn_aspect))
        by = dialog.bottom - int(0.24 * dh) - bh
        confirm_rect = pygame.Rect(dialog.x + int(0.16 * dw), by, bw, bh)
        cancel_rect = pygame.Rect(dialog.right - int(0.16 * dw) - bw, by, bw, bh)
        return dialog, confirm_rect, cancel_rect

    def _col_rect(self, index, y, height):
        """Rect of one column cell at row position y."""
        _label, f0, f1, _align = self.columns[index]
        x0 = self.rows_rect.x + int(f0 * self.content_w)
        x1 = self.rows_rect.x + int(f1 * self.content_w)
        return pygame.Rect(x0, y, max(1, x1 - x0), height)

    def _fit_text(self, text, font, max_w):
        """Truncate text with an ellipsis so it fits max_w pixels."""
        key = (text, id(font), max_w)
        cached = self._fit_cache.get(key)
        if cached is not None:
            return cached

        result = text
        if font.size(text)[0] > max_w:
            trimmed = text
            while trimmed and font.size(trimmed + "...")[0] > max_w:
                trimmed = trimmed[:-1]
            result = (trimmed + "...") if trimmed else "..."

        if len(self._fit_cache) > 512:
            self._fit_cache.clear()
        self._fit_cache[key] = result
        return result

    def _cached_text(self, text, font, color):
        """Render text with caching."""
        key = (text, id(font), color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 512:
                self._text_cache.clear()
            surf = font.render(text, True, color)
            self._text_cache[key] = surf
        return surf

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self):
        """Render the full browser screen."""
        if self.bg_image:
            self.screen.blit(self.bg_image, (0, 0))
        else:
            self.screen.fill(FALLBACK_BG)

        # No full-screen dim here: the ornate panel is opaque, and dimming would
        # mute the parchment band that the dark brown title relies on.
        self.screen.blit(self.title_surface, self.title_rect)
        self.screen.blit(self._scaled_panel, self.panel_rect)

        self._render_list()

        has_selection = self.selected_index >= 0
        self._render_btn(self.btn_back, "Return", 'back',
                         self.btn_font, WHITE, enabled=True)
        self._render_btn(self.btn_delete, "Delete", 'delete',
                         self.btn_font, WHITE, enabled=has_selection)
        self._render_btn(self.btn_load, "Load", 'load',
                         self.primary_font, BRASS_COLOR, enabled=has_selection)

        if self.confirm_delete:
            self._render_confirm_dialog()

        # Reset click state after paint, so the press tint lasts exactly one frame
        self.clicked_button = None

    def _render_list(self):
        """Render the save list header and rows inside the ornate panel."""
        # Column headers
        for i, (label, _f0, _f1, _align) in enumerate(self.columns):
            self._draw_cell(i, self.list_rect.y, self.header_h,
                            label, self.header_font, BRASS_COLOR)

        # Divider under the header
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (self.list_rect.x, self.divider_y),
                         (self.list_rect.right, self.divider_y),
                         max(1, int(2 * self.ui_scale)))

        if not self.saves:
            msg = self._fit_text(
                "No saved games found. Save your game from the in-game menu during a campaign.",
                self.row_font, self.content_w)
            surf = self._cached_text(msg, self.row_font, DIM_TEXT)
            self.screen.blit(surf, (
                self.rows_rect.x + (self.content_w - surf.get_width()) // 2,
                self.rows_rect.y + int(40 * self.ui_scale)))
            return

        # Clip to the row area so scrolled rows cannot paint over the header
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(self.rows_rect)

        for i, save in enumerate(self.saves):
            row_y = self.rows_rect.y - self.scroll_offset + i * self.row_height

            if row_y + self.row_height < self.rows_rect.y:
                continue
            if row_y >= self.rows_rect.bottom:
                break

            # Row background (pre-built surfaces, no per-frame allocation)
            if i == self.selected_index:
                self.screen.blit(self._row_selected, (self.rows_rect.x, row_y))
                pygame.draw.rect(
                    self.screen, BRASS_COLOR,
                    pygame.Rect(self.rows_rect.x, row_y,
                                self.content_w, self.row_height),
                    max(1, int(2 * self.ui_scale)))
            elif i == self.hovered_index:
                self.screen.blit(self._row_hover, (self.rows_rect.x, row_y))
            elif i % 2 == 0:
                self.screen.blit(self._row_alt, (self.rows_rect.x, row_y))

            self._draw_cell(0, row_y, self.row_height,
                            save.get('mission_text', '?'), self.row_font, INFO_TEXT)
            self._draw_cell(1, row_y, self.row_height,
                            save.get('save_name', 'Unnamed'), self.row_font, WHITE)
            self._draw_cell(2, row_y, self.row_height,
                            save.get('datetime', '?'), self.small_font, DIM_TEXT)
            self._draw_cell(3, row_y, self.row_height,
                            str(save.get('turn_number', '?')), self.row_font, INFO_TEXT)

        self.screen.set_clip(prev_clip)

        self._draw_scroll_indicator()

    def _draw_cell(self, index, y, height, text, font, color):
        """Draw one column cell, truncated to its column and vertically centred."""
        cell = self._col_rect(index, y, height)
        inner_w = max(1, cell.width - 2 * self.col_pad)
        surf = self._cached_text(self._fit_text(text, font, inner_w), font, color)
        text_y = y + (height - surf.get_height()) // 2
        if self.columns[index][3] == 'right':
            text_x = cell.right - self.col_pad - surf.get_width()
        else:
            text_x = cell.x + self.col_pad
        self.screen.blit(surf, (text_x, text_y))

    def _draw_scroll_indicator(self):
        """Slim brass scroll indicator — visual only, the wheel does the scrolling."""
        if self.max_scroll <= 0:
            return

        total_h = len(self.saves) * self.row_height
        track_w = max(2, int(6 * self.ui_scale))
        track_x = self.rows_rect.right - track_w
        radius = max(1, track_w // 2)

        pygame.draw.rect(self.screen, (54, 42, 28),
                         pygame.Rect(track_x, self.rows_rect.y,
                                     track_w, self.rows_rect.height),
                         border_radius=radius)

        thumb_h = max(int(20 * self.ui_scale),
                      int(self.rows_rect.height * self.rows_rect.height / total_h))
        thumb_h = min(thumb_h, self.rows_rect.height)
        travel = self.rows_rect.height - thumb_h
        thumb_y = self.rows_rect.y + int(travel * (self.scroll_offset / self.max_scroll))

        pygame.draw.rect(self.screen, BRASS_COLOR,
                         pygame.Rect(track_x, thumb_y, track_w, thumb_h),
                         border_radius=radius)

    def _btn_surface(self, size, state):
        """
        Cached, fully tinted ornate button surface.
        Bounded by construction: at most a few sizes x 4 states.
        """
        key = (size[0], size[1], state)
        surf = self._btn_cache.get(key)
        if surf is None:
            surf = pygame.transform.smoothscale(self.btn_image, size)
            mult = (60, 60, 60, 255) if state == 'disabled' else (100, 100, 100, 255)
            surf.fill(mult, special_flags=pygame.BLEND_RGBA_MULT)
            if state == 'click':
                surf.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif state == 'hover':
                surf.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self._btn_cache[key] = surf
        return surf

    def _render_btn(self, rect, text, btn_id, font, text_color, enabled=True):
        """Render a CampaignBTN.png-based button with hover/click/disabled states."""
        if not enabled:
            state = 'disabled'
        elif self.clicked_button == btn_id:
            state = 'click'
        elif self.hovered_button == btn_id:
            state = 'hover'
        else:
            state = 'normal'

        if self.btn_image is not None:
            self.screen.blit(self._btn_surface(rect.size, state), rect)
        else:
            # Fallback if the ornate button art is missing
            fill = (70, 60, 40) if state in ('hover', 'click') else (50, 42, 28)
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pygame.draw.rect(self.screen, BRASS_COLOR if enabled else DIM_TEXT,
                             rect, 1, border_radius=6)

        surf = self._cached_text(text, font, text_color if enabled else DIM_TEXT)
        self.screen.blit(surf, surf.get_rect(center=rect.center))

    def _render_confirm_dialog(self):
        """Render delete confirmation dialog on the ornate panel."""
        self.screen.blit(self._dim_overlay, (0, 0))

        dialog, confirm_rect, cancel_rect = self._confirm_dialog_rects()
        self.screen.blit(self._scaled_dialog, dialog)

        title = self._cached_text("Delete Save?", self.dialog_title_font, BRASS_COLOR)
        self.screen.blit(title, (
            dialog.centerx - title.get_width() // 2,
            dialog.y + int(0.30 * dialog.height)))

        msg = self._cached_text("This action cannot be undone.",
                                self.dialog_msg_font, INFO_TEXT)
        self.screen.blit(msg, (
            dialog.centerx - msg.get_width() // 2,
            dialog.y + int(0.43 * dialog.height)))

        # "Delete" is the primary action here, marked by the brass label
        self._render_btn(confirm_rect, "Delete", 'confirm_delete',
                         self.btn_font, BRASS_COLOR)
        self._render_btn(cancel_rect, "Cancel", 'confirm_cancel',
                         self.btn_font, WHITE)
