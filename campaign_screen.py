# -*- coding: utf-8 -*-
# campaign_screen.py
# Campaign screen with background and return button

"""
Campaign Screen
===============

Displays the campaign screen with CampaignBG.png background
and a Return to Main Menu button at the bottom.
"""

import pygame
import pygame.gfxdraw
import sys
import json
import math
from utils.surface_utils import crop_to_opaque
import os
from config.constants import WHITE, BLACK, GRAY
from global_sound import sound_manager
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.cursor import draw_custom_cursor
from utils.logger import get_logger
from display_utils import menu_frame_cap

logger = get_logger(__name__)

# Brass gold color for special button text (matching integrated_setup)
BRASS_COLOR = (181, 166, 66)


class CampaignScreen:
    """
    Campaign screen displaying background image and a return button.
    Modeled after IntegratedSetup's button styling.
    """

    def __init__(self, screen):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        self.clock = pygame.time.Clock()

        # State
        self.cancelled = False
        self.selected_mission = None  # Set when a mission button is clicked
        self.hovered_button = None
        self.clicked_button = None
        self.current_page = 0  # Pagination: page 0 = missions 1-5, page 1 = missions 6-10, etc.

        # Load assets
        self.bg_image = pygame.image.load("assets/CampaignBG.png").convert()
        self.bg_image = pygame.transform.smoothscale(self.bg_image, (self.width, self.height))

        self.button_bg_image = pygame.image.load("assets/MainMenuButtonNew.png").convert_alpha()
        self.campaign_btn_image = pygame.image.load("assets/CampaignBTN.png").convert_alpha()

        # Calculate UI scale based on screen height (matching integrated_setup pattern)
        self.ui_scale = self.height / 1080.0

        # All campaign mission buttons (across all pages)
        self.all_mission_buttons = [
            {'id': 'mission_1', 'text': 'Chapter 1: Rise of Affrancia'},
            {'id': 'mission_2', 'text': 'Chapter 2: Early Eastern Conquests'},
            {'id': 'mission_3', 'text': 'Chapter 3: Storms above the West'},
            {'id': 'mission_4', 'text': 'Chapter 4: Domination'},
            {'id': 'mission_5', 'text': 'Chapter 5: The First War'},
            {'id': 'mission_6', 'text': 'Chapter 6: The Second War'},
            {'id': 'mission_7', 'text': 'Chapter 7: The Fall'},
            # Greyed-out placeholder for future content
            {'id': 'coming_soon', 'text': 'Coming Soon...', 'disabled': True},
        ]

        # Pagination constants — 4 missions per page for balanced layout
        self.MISSIONS_PER_PAGE = 4
        self.total_pages = max(1, (len(self.all_mission_buttons) + self.MISSIONS_PER_PAGE - 1) // self.MISSIONS_PER_PAGE)

        # Layout for campaign buttons - preserve CampaignBTN.png visible aspect ratio
        # The PNG has large transparent padding; crop to opaque content (alpha > 128)
        self.campaign_btn_image = crop_to_opaque(self.campaign_btn_image, threshold=128)
        img_w, img_h = self.campaign_btn_image.get_size()
        self.campaign_btn_width = int(750 * self.ui_scale)
        self.campaign_btn_height = int(self.campaign_btn_width * img_h / img_w)
        self.campaign_btn_spacing = int(55 * self.ui_scale)
        self.campaign_btn_x = (self.width - self.campaign_btn_width) // 2
        self.top_padding = int(120 * self.ui_scale)

        # Pulse timer for arrow animation — slow breathing glow for visibility
        self._arrow_pulse_time = 0.0

        # Pagination arrow sizing and positioning
        arrow_size = int(65 * self.ui_scale)  # Arrow triangle bounding box size
        arrow_margin = int(30 * self.ui_scale)  # Gap between arrow and mission button column
        # Vertical center of the mission button column
        max_buttons_height = self.MISSIONS_PER_PAGE * (self.campaign_btn_height + self.campaign_btn_spacing) - self.campaign_btn_spacing
        arrow_center_y = self.top_padding + max_buttons_height // 2
        # Left arrow: to the left of the button column
        self.left_arrow_rect = pygame.Rect(
            self.campaign_btn_x - arrow_margin - arrow_size,
            arrow_center_y - arrow_size // 2,
            arrow_size, arrow_size
        )
        # Right arrow: to the right of the button column
        self.right_arrow_rect = pygame.Rect(
            self.campaign_btn_x + self.campaign_btn_width + arrow_margin,
            arrow_center_y - arrow_size // 2,
            arrow_size, arrow_size
        )

        # Build visible buttons for current page
        self._update_visible_buttons()

        # Font for campaign buttons
        campaign_font_size = max(14, int(24 * self.ui_scale))
        self.campaign_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', campaign_font_size)

        # Tooltip font (matching main menu tooltip style)
        tooltip_font_size = max(14, int(20 * self.ui_scale))
        self.tooltip_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', tooltip_font_size)

        # Title font and position — golden "Campaign" text centered above buttons
        title_font_size = max(20, int(48 * self.ui_scale))
        self.title_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', title_font_size)
        self.title_surface = self.title_font.render("Campaign", True, (80, 50, 20))
        self.title_rect = self.title_surface.get_rect(
            centerx=self.width // 2,
            bottom=self.top_padding - int(15 * self.ui_scale)
        )

        # Return button layout - centered at bottom of screen
        button_width = int(400 * self.ui_scale)
        button_height = int(67 * self.ui_scale)
        button_x = (self.width - button_width) // 2
        button_y = self.height - button_height - int(30 * self.ui_scale)

        self.return_button_rect = pygame.Rect(button_x, button_y, button_width, button_height)

        # Font for return button (matching integrated_setup: Cinzel-Regular, size 29 scaled)
        font_size = max(16, int(29 * self.ui_scale))
        self.button_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size)

        # Saved Games square button (bottom-left, matching Replays button pattern)
        save_btn_size = int(120 * self.ui_scale)
        save_btn_margin = int(20 * self.ui_scale)
        self.save_games_button_rect = pygame.Rect(
            save_btn_margin,
            self.height - save_btn_size - save_btn_margin,
            save_btn_size, save_btn_size
        )
        # Load saved games button icon
        self.save_games_icon = None
        try:
            icon = pygame.image.load('assets/SaveGameButton.png').convert_alpha()
            self.save_games_icon = pygame.transform.smoothscale(icon, (save_btn_size, save_btn_size))
        except Exception as e:
            logger.warning(f"Could not load SaveGameButton.png: {e}")
        # Load icon border frame (same as main menu square buttons)
        self.icon_border = None
        try:
            border = pygame.image.load('assets/mapicons/IconBorder.png').convert_alpha()
            # 2px larger than button (1px per side) to fully contain icon edges
            self.icon_border = pygame.transform.smoothscale(border, (save_btn_size + 2, save_btn_size + 2))
        except Exception as e:
            logger.warning(f"Could not load IconBorder.png: {e}")

    def _update_visible_buttons(self):
        """Recalculate which mission buttons are visible on the current page and assign rects"""
        start = self.current_page * self.MISSIONS_PER_PAGE
        end = start + self.MISSIONS_PER_PAGE
        self.campaign_buttons = self.all_mission_buttons[start:end]
        for i, btn in enumerate(self.campaign_buttons):
            btn_y = self.top_padding + i * (self.campaign_btn_height + self.campaign_btn_spacing)
            btn['rect'] = pygame.Rect(self.campaign_btn_x, btn_y, self.campaign_btn_width, self.campaign_btn_height)

    def run(self):
        """Main loop - returns mission_id string if mission clicked, None if cancelled"""
        while not self.cancelled and not self.selected_mission:
            delta_time = min(self.clock.get_time() / 1000.0, 0.05)
            self._arrow_pulse_time += delta_time
            self.handle_events()
            self.render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()
            self.clock.tick(menu_frame_cap())

        return self.selected_mission

    def handle_events(self):
        """Process input events"""
        mouse_pos = pygame.mouse.get_pos()

        # Update hover state (includes pagination arrows and saved games button)
        self.hovered_button = None
        if self.save_games_button_rect.collidepoint(mouse_pos):
            self.hovered_button = 'saved_games'
        elif self.return_button_rect.collidepoint(mouse_pos):
            self.hovered_button = 'return'
        elif self.current_page > 0 and self.left_arrow_rect.collidepoint(mouse_pos):
            self.hovered_button = 'page_left'
        elif self.current_page < self.total_pages - 1 and self.right_arrow_rect.collidepoint(mouse_pos):
            self.hovered_button = 'page_right'
        else:
            for btn in self.campaign_buttons:
                if btn['rect'].collidepoint(mouse_pos):
                    # Disabled buttons still get hover (for tooltip) but use special id
                    self.hovered_button = btn['id']
                    break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # Alt+F4: signal caller to exit the entire app
                self.selected_mission = 'quit'
                self.cancelled = True
                return

            # Music track ended — advance to next track
            elif event.type == _MUSIC_END_EVENT:
                _music_manager.handle_music_end_event()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.cancelled = True

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.save_games_button_rect.collidepoint(mouse_pos):
                        sound_manager.play_ui_click()
                        self.clicked_button = 'saved_games'
                        self.selected_mission = 'saved_games'
                    elif self.return_button_rect.collidepoint(mouse_pos):
                        sound_manager.play_ui_click()
                        self.clicked_button = 'return'
                        self.cancelled = True
                    elif self.current_page > 0 and self.left_arrow_rect.collidepoint(mouse_pos):
                        # Navigate to previous page
                        sound_manager.play_ui_click()
                        self.clicked_button = 'page_left'
                        self.current_page -= 1
                        self._update_visible_buttons()
                    elif self.current_page < self.total_pages - 1 and self.right_arrow_rect.collidepoint(mouse_pos):
                        # Navigate to next page
                        sound_manager.play_ui_click()
                        self.clicked_button = 'page_right'
                        self.current_page += 1
                        self._update_visible_buttons()
                    else:
                        # Campaign mission buttons - open mission screen (skip disabled)
                        for btn in self.campaign_buttons:
                            if btn.get('disabled'):
                                continue
                            if btn['rect'].collidepoint(mouse_pos):
                                sound_manager.play_ui_click()
                                self.clicked_button = btn['id']
                                self.selected_mission = btn['id']
                                break

    def render(self):
        """Render campaign screen"""
        # Draw background
        self.screen.blit(self.bg_image, (0, 0))

        # Draw "Campaign" title above buttons
        self.screen.blit(self.title_surface, self.title_rect)

        # Draw campaign mission buttons (current page only)
        for btn in self.campaign_buttons:
            self._draw_campaign_button(btn)

        # Draw pagination arrows (only when relevant pages exist)
        if self.current_page > 0:
            self._draw_page_arrow(self.left_arrow_rect, 'left', 'page_left')
        if self.current_page < self.total_pages - 1:
            self._draw_page_arrow(self.right_arrow_rect, 'right', 'page_right')

        # Draw return button (matching integrated_setup style)
        self._draw_return_button()

        # Draw Saved Games square button (bottom-left)
        self._draw_saved_games_button()

        # Reset clicked state after render
        self.clicked_button = None

    def _draw_tooltip(self, text, pos):
        """Draw a tooltip near mouse position, matching main menu style. Supports multi-line via newline."""
        font = self.tooltip_font
        pad = int(6 * self.ui_scale)
        lines = text.split('\n')
        line_surfaces = [font.render(line, True, WHITE) for line in lines]
        line_h = font.get_linesize()
        tw = max(s.get_width() for s in line_surfaces) + pad * 2
        th = len(line_surfaces) * line_h + pad * 2
        tx = min(pos[0] + 15, self.width - tw - 5)
        ty = max(pos[1] - th - 5, 5)
        bg = pygame.Surface((tw, th), pygame.SRCALPHA)
        bg.fill((30, 30, 50, 220))
        pygame.draw.rect(bg, (150, 150, 150), (0, 0, tw, th), 1)
        self.screen.blit(bg, (tx, ty))
        for i, surf in enumerate(line_surfaces):
            self.screen.blit(surf, (tx + pad, ty + pad + i * line_h))

    def _draw_campaign_button(self, btn):
        """Draw a campaign mission button using CampaignBTN.png"""
        rect = btn['rect']
        is_hovered = (self.hovered_button == btn['id'])
        is_clicked = (self.clicked_button == btn['id'])
        is_disabled = btn.get('disabled', False)

        # Draw button background using CampaignBTN.png
        scaled_bg = pygame.transform.smoothscale(
            self.campaign_btn_image,
            (rect.width, rect.height)
        )

        button_surface = scaled_bg.copy()

        if is_disabled:
            # Heavy darkening for greyed-out disabled look
            button_surface.fill((50, 50, 50, 255), special_flags=pygame.BLEND_RGBA_MULT)
        else:
            # Base darkening (consistent with other buttons)
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

            if is_clicked:
                # Bright flash on click
                button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif is_hovered:
                # Subtle brightness on hover
                button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)

        self.screen.blit(button_surface, rect)

        # Draw text — grey for disabled, white for normal
        text_color = GRAY if is_disabled else WHITE
        text_surface = self.campaign_font.render(btn['text'], True, text_color)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

        # Tooltip for disabled "Coming Soon" button on hover
        if is_disabled and is_hovered:
            self._draw_tooltip(
                "The history of Avareon is always in the making.\n"
                "Who knows what shall come up after the Second War...",
                pygame.mouse.get_pos()
            )

    def _draw_page_arrow(self, rect, direction, btn_id):
        """Draw a pagination arrow (triangle) with hover/click effects, slow pulse, and size breathing.
        direction: 'left' or 'right'
        """
        is_hovered = (self.hovered_button == btn_id)
        is_clicked = (self.clicked_button == btn_id)

        # Slow color pulse (3-second cycle)
        pulse = (math.sin(self._arrow_pulse_time * 2.0 * math.pi / 3.0) + 1.0) / 2.0  # 0..1
        pulse_boost = int(25 * pulse)

        # Build triangle points at fixed size from rect center
        cx, cy = rect.centerx, rect.centery
        half_w = rect.width // 2
        half_h = rect.height // 2
        if direction == 'left':
            points = [(cx - half_w, cy), (cx + half_w, cy - half_h), (cx + half_w, cy + half_h)]
        else:
            points = [(cx + half_w, cy), (cx - half_w, cy - half_h), (cx - half_w, cy + half_h)]

        # Choose color based on state — dark brown base with slow pulse glow
        if is_clicked:
            color = (60, 40, 20)
        elif is_hovered:
            color = (45, 28, 12)
        else:
            # Pulsing base: oscillates between (30,18,8) and (55,43,33)
            color = (30 + pulse_boost, 18 + pulse_boost, 8 + pulse_boost)

        pygame.gfxdraw.filled_polygon(self.screen, points, color)
        pygame.gfxdraw.aapolygon(self.screen, points, color)

    def _draw_return_button(self):
        """Draw the Return to Main Menu button with integrated_setup styling"""
        rect = self.return_button_rect
        is_hovered = (self.hovered_button == 'return')
        is_clicked = (self.clicked_button == 'return')

        # Draw button background using MainMenuButtonNew.png
        if self.button_bg_image:
            scaled_bg = pygame.transform.smoothscale(
                self.button_bg_image,
                (rect.width, rect.height)
            )

            button_surface = scaled_bg.copy()
            # Base darkening (matching integrated_setup enabled button style)
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

            if is_clicked:
                # More brightness on click
                button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif is_hovered:
                # Subtle brightness on hover
                button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)

            self.screen.blit(button_surface, rect)

        # Draw text (white, Cinzel-Regular - matching integrated_setup return button)
        text_surface = self.button_font.render("Return", True, WHITE)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def _draw_saved_games_button(self):
        """Draw the Saved Games square button (bottom-left) with icon and border."""
        rect = self.save_games_button_rect
        is_hovered = (self.hovered_button == 'saved_games')
        is_clicked = (self.clicked_button == 'saved_games')

        # Draw icon or fallback
        if self.save_games_icon:
            btn_surf = self.save_games_icon.copy()
        else:
            # Fallback: dark square with text
            btn_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            btn_surf.fill((40, 40, 55, 200))

        # Apply hover/click brightness (same pattern as main_menu _draw_replays_button)
        if is_clicked:
            bright = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bright.fill((100, 100, 100, 100))
            btn_surf.blit(bright, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif is_hovered:
            bright = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bright.fill((50, 50, 50, 50))
            btn_surf.blit(bright, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.screen.blit(btn_surf, rect.topleft)

        # Draw border frame on top (offset -1 to center enlarged border)
        if self.icon_border:
            self.screen.blit(self.icon_border, (rect.x - 1, rect.y - 1))

        # Tooltip on hover (matching main menu tooltip style)
        if is_hovered:
            self._draw_tooltip("Saved Games", pygame.mouse.get_pos())


# Load mission data from JSON file (edited via Campaign_Text_Tool.py)
CAMPAIGN_DATA_PATH = os.path.join(os.path.dirname(__file__), 'campaign_data.json')

def load_mission_data():
    """Load mission data from campaign_data.json"""
    try:
        with open(CAMPAIGN_DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback empty data if file missing or corrupt
        return {}

MISSION_DATA = load_mission_data()


class MissionScreen:
    """
    Mission detail screen showing briefing, lore, objectives, and characters
    for a specific campaign mission. Uses tabbed navigation with a scrollable
    text content panel.
    """

    # Tab definitions
    TABS = ['briefing', 'lore', 'objectives', 'characters']
    TAB_LABELS = {'briefing': 'Briefing', 'lore': 'Lore', 'objectives': 'Objectives', 'characters': 'Characters'}

    def __init__(self, screen, mission_id, mission_data):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        self.clock = pygame.time.Clock()
        self.mission_id = mission_id
        self.mission_data = mission_data

        # State
        self.done = False
        self.result = None  # 'return' to go back to campaign
        self.selected_tab = 'briefing'
        self.hovered_button = None
        self.clicked_button = None
        self.scroll_offset = 0  # Pixel offset for text scrolling

        # UI scale
        self.ui_scale = self.height / 1080.0

        # Load assets
        self.bg_image = pygame.image.load("assets/CampaignBG.png").convert()
        self.bg_image = pygame.transform.smoothscale(self.bg_image, (self.width, self.height))

        raw_btn_image = pygame.image.load("assets/CampaignBTN.png").convert_alpha()
        self.btn_image = crop_to_opaque(raw_btn_image, threshold=128)

        self.panel_image = pygame.image.load("assets/OptionsMenuBG.png").convert_alpha()

        # Button aspect ratio from cropped image
        btn_img_w, btn_img_h = self.btn_image.get_size()
        self.btn_aspect = btn_img_h / btn_img_w

        # --- Layout calculations ---

        # Top tab buttons (4 across, centered)
        tab_btn_width = int(350 * self.ui_scale)
        tab_btn_height = int(tab_btn_width * self.btn_aspect)
        tab_spacing = int(15 * self.ui_scale)
        total_tabs_width = 4 * tab_btn_width + 3 * tab_spacing
        tab_start_x = (self.width - total_tabs_width) // 2
        tab_y = int(30 * self.ui_scale)

        self.tab_buttons = {}
        for i, tab_id in enumerate(self.TABS):
            x = tab_start_x + i * (tab_btn_width + tab_spacing)
            self.tab_buttons[tab_id] = pygame.Rect(x, tab_y, tab_btn_width, tab_btn_height)

        # Bottom buttons
        bottom_btn_width = int(400 * self.ui_scale)
        bottom_btn_height = int(bottom_btn_width * self.btn_aspect)
        bottom_y = self.height - bottom_btn_height - int(30 * self.ui_scale)
        bottom_margin = int(40 * self.ui_scale)

        self.return_button_rect = pygame.Rect(bottom_margin, bottom_y, bottom_btn_width, bottom_btn_height)
        self.launch_button_rect = pygame.Rect(
            self.width - bottom_btn_width - bottom_margin, bottom_y,
            bottom_btn_width, bottom_btn_height
        )

        # Content panel (between tabs and bottom buttons)
        panel_margin = int(60 * self.ui_scale)
        panel_top = tab_y + tab_btn_height + int(20 * self.ui_scale)
        panel_bottom = bottom_y - int(20 * self.ui_scale)
        self.panel_rect = pygame.Rect(
            panel_margin, panel_top,
            self.width - 2 * panel_margin, panel_bottom - panel_top
        )

        # Text area inside panel (with inner padding - asymmetric for ornate border)
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

        # Fonts
        self.tab_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(14, int(22 * self.ui_scale)))
        self.btn_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(16, int(24 * self.ui_scale)))
        self.launch_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', max(16, int(24 * self.ui_scale)))
        self.text_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(16, int(24 * self.ui_scale)))
        # Header font for rich text (lines starting with ## in mission data)
        self.header_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', max(16, int(24 * self.ui_scale)))

        # Pre-wrap text for each tab so scrolling is efficient
        self._wrapped_text_cache = {}

    def _get_wrapped_lines(self, tab_id):
        """Word-wrap text for the given tab, caching the result.

        Returns list of (text, is_header) tuples. Lines starting with ## in the
        source text are treated as headers and rendered in Cinzel-SemiBold.
        """
        if tab_id in self._wrapped_text_cache:
            return self._wrapped_text_cache[tab_id]

        raw_text = self.mission_data.get(tab_id, '')
        lines = []
        for paragraph in raw_text.split('\n'):
            if not paragraph.strip():
                lines.append(('', False))
                continue

            # Check for header markup (## at start of line)
            is_header = paragraph.strip().startswith('##')
            if is_header:
                paragraph = paragraph.strip().lstrip('#').strip()
                font = self.header_font
            else:
                font = self.text_font

            words = paragraph.split()
            current_line = ''
            for word in words:
                test = (current_line + ' ' + word).strip()
                if font.size(test)[0] <= self.text_rect.width:
                    current_line = test
                else:
                    if current_line:
                        lines.append((current_line, is_header))
                    current_line = word
            if current_line:
                lines.append((current_line, is_header))

        self._wrapped_text_cache[tab_id] = lines
        return lines

    def run(self):
        """Main loop - returns 'return' to go back to campaign screen"""
        while not self.done:
            self.handle_events()
            self.render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()
            self.clock.tick(menu_frame_cap())

        return self.result

    def handle_events(self):
        mouse_pos = pygame.mouse.get_pos()

        # Update hover state
        self.hovered_button = None
        if self.return_button_rect.collidepoint(mouse_pos):
            self.hovered_button = 'return'
        elif self.launch_button_rect.collidepoint(mouse_pos):
            self.hovered_button = 'launch'
        else:
            for tab_id, rect in self.tab_buttons.items():
                if rect.collidepoint(mouse_pos):
                    self.hovered_button = tab_id
                    break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # Alt+F4: signal caller to exit the entire app
                self.result = 'quit'
                self.done = True
                return

            # Music track ended — advance to next track
            elif event.type == _MUSIC_END_EVENT:
                _music_manager.handle_music_end_event()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.result = 'return'
                    self.done = True

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.return_button_rect.collidepoint(mouse_pos):
                        sound_manager.play_ui_click()
                        self.clicked_button = 'return'
                        self.result = 'return'
                        self.done = True
                    elif self.launch_button_rect.collidepoint(mouse_pos):
                        # Launch the selected campaign mission
                        sound_manager.play_ui_click()
                        self.clicked_button = 'launch'
                        self.result = f'launch_{self.mission_id}'
                        self.done = True
                    else:
                        for tab_id, rect in self.tab_buttons.items():
                            if rect.collidepoint(mouse_pos):
                                sound_manager.play_ui_click()
                                self.clicked_button = tab_id
                                if self.selected_tab != tab_id:
                                    self.selected_tab = tab_id
                                    self.scroll_offset = 0  # Reset scroll on tab change
                                break

                # Mouse wheel scrolling for text content
                elif event.button == 4:  # Scroll up
                    self.scroll_offset = max(0, self.scroll_offset - int(30 * self.ui_scale))
                elif event.button == 5:  # Scroll down
                    self._scroll_down()

    def _get_line_height(self, is_header):
        """Return line height for regular or header text"""
        return self.header_font.get_linesize() if is_header else self.text_font.get_linesize()

    def _get_total_content_height(self):
        """Calculate total height of all wrapped lines for current tab"""
        lines = self._get_wrapped_lines(self.selected_tab)
        return sum(self._get_line_height(is_h) for _, is_h in lines)

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

    def _scroll_down(self):
        """Scroll text down, clamped to content height"""
        total_content_height = self._get_total_content_height()
        max_scroll = max(0, total_content_height - self.text_rect.height)
        self.scroll_offset = min(max_scroll, self.scroll_offset + int(30 * self.ui_scale))

    def render(self):
        # Background
        self.screen.blit(self.bg_image, (0, 0))

        # Tab buttons
        for tab_id, rect in self.tab_buttons.items():
            self._draw_btn(rect, self.TAB_LABELS[tab_id], tab_id,
                           self.tab_font, is_selected=(tab_id == self.selected_tab))

        # Content panel
        self._draw_content_panel()

        # Bottom buttons
        self._draw_btn(self.return_button_rect, 'Return', 'return', self.btn_font)
        self._draw_btn(self.launch_button_rect, 'Launch Chapter', 'launch', self.launch_font)

        # Reset clicked state
        self.clicked_button = None

    def _draw_btn(self, rect, text, btn_id, font, is_selected=False):
        """Draw a CampaignBTN.png-based button with hover/click/selected states"""
        is_hovered = (self.hovered_button == btn_id)
        is_clicked = (self.clicked_button == btn_id)

        scaled_bg = pygame.transform.smoothscale(self.btn_image, (rect.width, rect.height))
        button_surface = scaled_bg.copy()

        if is_selected:
            # Selected tab: brighter base (permanent highlight)
            button_surface.fill((140, 140, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
        else:
            # Normal darkened base
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

        if is_clicked:
            button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
        elif is_hovered:
            button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)

        self.screen.blit(button_surface, rect)

        # Text - brass gold for Launch Chapter, white for everything else
        text_color = BRASS_COLOR if btn_id == 'launch' else WHITE
        text_surface = font.render(text, True, text_color)
        text_r = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_r)

    def _draw_content_panel(self):
        """Draw the OptionsMenuBG panel and render scrollable text inside"""
        # Scale and draw panel background
        scaled_panel_raw = pygame.transform.smoothscale(
            self.panel_image,
            (self.panel_rect.width, self.panel_rect.height)
        )
        # Darken the panel for better text readability (reduced from 140 to 100 for darker background)
        scaled_panel_raw.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(scaled_panel_raw, self.panel_rect)

        # Render text with clipping to text_rect area
        lines = self._get_wrapped_lines(self.selected_tab)

        # Create clipping surface for text scrolling
        clip_surface = pygame.Surface((self.text_rect.width, self.text_rect.height), pygame.SRCALPHA)
        clip_surface.fill((0, 0, 0, 0))

        y = -self.scroll_offset
        for text, is_header in lines:
            lh = self._get_line_height(is_header)
            if y + lh > 0 and y < self.text_rect.height:
                # Only render visible lines
                if text:
                    font = self.header_font if is_header else self.text_font
                    # Headers use brass gold color, regular text is white
                    color = BRASS_COLOR if is_header else WHITE
                    line_surface = font.render(text, True, color)
                    clip_surface.blit(line_surface, (0, y))
            y += lh
            if y > self.text_rect.height:
                break  # No need to process lines below visible area

        self.screen.blit(clip_surface, self.text_rect)

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
