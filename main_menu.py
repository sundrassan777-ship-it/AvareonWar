# -*- coding: utf-8 -*-
# main_menu.py
# Main menu screen for the game

"""
Main Menu
=========

The main menu is the entry point for the game, showing buttons for:
- Campaign (placeholder)
- Custom Game (opens integrated setup)
- Multiplayer (opens multiplayer setup for LAN games)
- Options (opens options menu with settings)
- Quit Game (exits application)
"""

import pygame
import sys
from config.constants import WHITE, BLACK, GRAY, DARK_GRAY, GAME_VERSION
from utils.colors import lighten_color, brighten_color
from settings_manager import settings
from global_sound import sound_manager  # Global sound manager for UI clicks
from achievement_manager import achievement_manager, ALL_REWARD_ICON_PATHS, ALL_TITLES
from achievement_panel import AchievementPanel
from utils.logger import get_logger
from utils.cursor import draw_custom_cursor

logger = get_logger(__name__)


class MainMenu:
    """
    Main menu screen with navigation to different game modes and settings.

    Features:
    - Clean button layout
    - Hover and click feedback
    - Options menu integration
    - Return values indicate which mode to launch
    """

    def __init__(self, screen):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()

        # P8 fix: font cache to avoid per-frame pygame.font.Font() filesystem I/O
        self._font_cache = {}

        # Scale factor for UI elements based on screen height
        self.ui_scale = min(1.0, self.height / 900.0)

        # Options panel animation state (define BEFORE loading background)
        self.options_panel_width = int(self.width * 0.5)  # 50% of screen width
        self.options_panel_height = int(self.height * 0.7)  # 70% of screen height
        self.options_panel_x = (self.width - self.options_panel_width) // 2  # Centered
        self.options_panel_y = -self.options_panel_height  # Start off-screen (above)
        self.options_panel_target_y = -self.options_panel_height  # Target position
        # Position slightly lower to cover all buttons (center + 60 pixels down)
        self.options_panel_final_y = (self.height - self.options_panel_height) // 2 + 60
        self.options_animation_speed = 1500  # Pixels per second

        # Profile panel animation state (same dimensions as options)
        self.profile_panel_width = int(self.width * 0.5)
        self.profile_panel_height = int(self.height * 0.7)
        self.profile_panel_x = (self.width - self.profile_panel_width) // 2
        self.profile_panel_y = -self.profile_panel_height
        self.profile_panel_target_y = -self.profile_panel_height
        self.profile_panel_final_y = (self.height - self.profile_panel_height) // 2 + 60
        self.profile_animation_speed = 1500

        # Achievement panel animation state (same dimensions as options/profile)
        self.achievement_panel_width = int(self.width * 0.5)
        self.achievement_panel_height = int(self.height * 0.7)
        self.achievement_panel_x = (self.width - self.achievement_panel_width) // 2
        self.achievement_panel_y = -self.achievement_panel_height
        self.achievement_panel_target_y = -self.achievement_panel_height
        self.achievement_panel_final_y = (self.height - self.achievement_panel_height) // 2 + 60
        self.achievement_animation_speed = 1500

        # Load and scale background image
        self._load_background()

        # Fonts
        try:
            self.title_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', 72)
            self.button_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', 29)  # 20% smaller (was 36)
            self.label_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', 28)
            self.section_header_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', 34)  # Bold section headers
            self.tooltip_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(11, int(14 * self.ui_scale)))
        except Exception as e:
            logger.warning(f"Error loading custom font: {e}")
            # Fallback to default fonts
            self.title_font = pygame.font.SysFont('arial', 72, bold=True)
            self.button_font = pygame.font.SysFont('arial', 29)
            self.label_font = pygame.font.SysFont('arial', 28)
            self.section_header_font = pygame.font.SysFont('arial', 34, bold=True)
            self.tooltip_font = pygame.font.SysFont('arial', max(11, int(14 * self.ui_scale)))

        # UI state
        self.hovered_button = None
        self.clicked_button = None
        self.show_options = False
        self.show_profile = False
        self.show_achievements = False
        self.result = None  # Return value: 'custom_game', 'quit', etc.
        self.hovered_option_element = None  # Track hover state in options panel
        self.hovered_profile_element = None  # Track hover state in profile panel
        self.hovered_achievement_element = None  # Track hover state in achievement panel

        # Temporary settings (not saved until Apply is clicked)
        self.temp_resolution = settings.get_resolution()
        self.temp_fullscreen = settings.is_fullscreen()
        self.temp_edge_scrolling_enabled = settings.get('edge_scrolling_enabled', True)
        self.temp_tooltips_enabled = settings.get('tooltips_enabled', True)
        self.temp_show_fps = settings.get('show_fps', False)
        self.temp_edge_scrolling_mode = settings.get('edge_scrolling_mode', 'map_edge')
        self.temp_tooltip_delay_ms = settings.get('tooltip_delay_ms', 500)
        self.temp_pan_speed = settings.get('camera_pan_speed', 10.0)
        self.temp_zoom_speed = settings.get('camera_zoom_speed', 0.15)

        # Available resolutions
        self.available_resolutions = [
            (1280, 720),
            (1600, 900),
            (1920, 1080)
        ]

        # Dropdown state
        self.resolution_dropdown_open = False

        # Options panel scroll state
        self.options_scroll_offset = 0
        self.options_max_scroll = 0

        # Options slider drag state
        self.options_dragging_slider = None  # 'pan_speed' or 'zoom_speed'
        self.options_drag_offset = 0
        self.options_pan_speed_slider = None  # (track_rect, min_val, max_val, thumb_rect)
        self.options_zoom_speed_slider = None

        # Options UI elements
        self.options_ui_elements = {}

        # Temporary profile settings (not saved until Save is clicked)
        self.temp_player_name = settings.get_player_name()
        self.temp_player_icon = settings.get_player_icon()
        self.temp_selected_title = settings.get_selected_title()
        self.profile_name_active = False  # Whether name input field is active
        self.title_dropdown_open = False  # Title dropdown in profile

        # Profile UI elements
        self.profile_ui_elements = {}

        # Achievement panel helper (handles content rendering and interaction)
        self.achievement_panel_helper = AchievementPanel(self.width, self.height, self.ui_scale)

        # Icon grid scroll state for profile panel
        self.icon_scroll_offset = 0

        # Title dropdown scroll state
        self.title_dropdown_scroll = 0
        self.TITLE_DROPDOWN_VISIBLE = 4  # Max visible options before scrolling

        # Configurable icon display names (modify these to rename icons in the UI)
        # Hero icons: index 0=question mark, indices 1-8=hero portraits
        self.hero_icon_names = [
            "Default",       # 0: Question mark
            "Vearen Asford",        # 1: hero_icons[0]
            "Ethan Nithieln",         # 2: hero_icons[1]
            "Darius Brennhen",      # 3: hero_icons[2]
            "Neil Hévilneu",      # 4: hero_icons[3]
            "Aidam Narn",          # 5: hero_icons[4]
            "Halon Nextroy",       # 6: hero_icons[5]
            "Seledra Rennervail",    # 7: hero_icons[6]
            "Erec Silvyr",        # 8: hero_icons[7]
        ]
        # Reward icon display names (keyed by path, modify to customize)
        self.reward_icon_names = {
            'assets/achievements/AchievementIcons/SwordsmanIcon.png': 'Swordsman',
            'assets/achievements/RewardsIcons/TacticianIcon.png': 'Tactician',
            'assets/achievements/RewardsIcons/Conquest1Icon.png': 'Desolation',
            'assets/achievements/RewardsIcons/Conquest2Icon.png': 'Fiery Desolation',
            'assets/achievements/RewardsIcons/Conquest3Icon.png': 'The Destructor',
            'assets/achievements/RewardsIcons/HannasIcon.png': 'Lord Hannas',
            'assets/achievements/RewardsIcons/KalanIcon.png': 'Lord Kalan',
            'assets/achievements/RewardsIcons/LeiIcon.png': 'Marshal Lei',
            'assets/achievements/RewardsIcons/LordVenderfornet.png': 'Prime Lord Venderfornet',
            'assets/achievements/RewardsIcons/Halberdier.png': 'Halberdier',
            'assets/achievements/RewardsIcons/Ranger.png': 'Ranger',
            'assets/achievements/RewardsIcons/Fighter.png': 'Fighter',
            'assets/achievements/RewardsIcons/Knight.png': 'Knight',
            'assets/achievements/RewardsIcons/AlexiusBrennhen.png': 'Alexius Brennhen',
        }

        # Clock
        self.clock = pygame.time.Clock()

        # Calculate layout
        self._calculate_layout()

    def _load_background(self):
        """Load and scale background image to fit screen"""
        try:
            # Load the background image
            bg = pygame.image.load('assets/bg static.jpeg').convert()

            # Get dimensions
            bg_width = bg.get_width()
            bg_height = bg.get_height()

            # Calculate aspect ratios
            screen_aspect = self.width / self.height
            bg_aspect = bg_width / bg_height

            # Scale to cover screen (like CSS background-size: cover)
            if bg_aspect > screen_aspect:
                # Background is wider - fit height, crop width
                scale_height = self.height
                scale_width = int(scale_height * bg_aspect)
            else:
                # Background is taller - fit width, crop height
                scale_width = self.width
                scale_height = int(scale_width / bg_aspect)

            # Scale the image
            scaled_bg = pygame.transform.smoothscale(bg, (scale_width, scale_height))

            # Create surface and center the scaled background
            self.background = pygame.Surface((self.width, self.height))

            # Calculate position to center crop
            x_offset = (scale_width - self.width) // 2
            y_offset = (scale_height - self.height) // 2

            # Blit the centered portion
            self.background.blit(scaled_bg, (-x_offset, -y_offset))

        except Exception as e:
            logger.warning(f"Error loading background: {e}")
            # Fallback to black background
            self.background = pygame.Surface((self.width, self.height))
            self.background.fill(BLACK)

        # Load logo
        try:
            logo = pygame.image.load('assets/GameLogo.png').convert_alpha()

            # Scale logo to reasonable size (max 42% of screen width - 30% smaller than before)
            max_logo_width = int(self.width * 0.42)
            logo_width = logo.get_width()
            logo_height = logo.get_height()

            if logo_width > max_logo_width:
                scale_factor = max_logo_width / logo_width
                new_width = int(logo_width * scale_factor)
                new_height = int(logo_height * scale_factor)
                self.logo = pygame.transform.smoothscale(logo, (new_width, new_height))
            else:
                self.logo = logo

        except Exception as e:
            logger.warning(f"Error loading logo: {e}")
            self.logo = None

        # Load options panel background
        try:
            options_bg = pygame.image.load('assets/OptionsMenuBG.png').convert_alpha()
            # Scale to match panel dimensions
            self.options_panel_bg = pygame.transform.smoothscale(
                options_bg,
                (self.options_panel_width, self.options_panel_height)
            )
        except Exception as e:
            logger.warning(f"Error loading options panel background: {e}")
            self.options_panel_bg = None

        # Load custom menu button background
        try:
            button_bg = pygame.image.load('assets/MainMenuButtonNew.png').convert_alpha()
            # We'll scale this per button in _draw_button based on button dimensions
            self.button_bg_image = button_bg
        except Exception as e:
            logger.warning(f"Error loading menu button background: {e}")
            self.button_bg_image = None

        # Load profile panel background (same as options panel)
        try:
            profile_bg = pygame.image.load('assets/OptionsMenuBG.png').convert_alpha()
            self.profile_panel_bg = pygame.transform.smoothscale(
                profile_bg,
                (self.profile_panel_width, self.profile_panel_height)
            )
        except Exception as e:
            logger.warning(f"Error loading profile panel background: {e}")
            self.profile_panel_bg = None

        # Load icon border for profile button
        try:
            icon_border = pygame.image.load('assets/mapicons/IconBorder.png').convert_alpha()
            # Brighten the border by 20%
            brightened = icon_border.copy()
            bright_overlay = pygame.Surface(icon_border.get_size(), pygame.SRCALPHA)
            bright_overlay.fill((51, 51, 51, 0))
            brightened.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            self.icon_border = brightened
        except Exception as e:
            logger.warning(f"Error loading icon border: {e}")
            self.icon_border = None

        # Load hero icons for profile (original size - will be pre-scaled later)
        self.hero_icons = []
        hero_icon_files = [
            'asford.png',
            'asten.png',
            'brennhen.png',
            'hevilneu.png',
            'narn.png',
            'nextroy.png',
            'rennervail.png',
            'silvyr.png'
        ]
        for hero_file in hero_icon_files:
            try:
                icon = pygame.image.load(f'assets/heroes/{hero_file}').convert_alpha()
                self.hero_icons.append(icon)
            except Exception as e:
                logger.warning(f"Could not load hero icon {hero_file}: {e}")
                self.hero_icons.append(None)

        # Load achievement button icon
        self.achievement_button_icon = None
        try:
            ach_icon = pygame.image.load('assets/achievements/GeneralAchievementsIcon.png').convert_alpha()
            self.achievement_button_icon = ach_icon  # Will be pre-scaled in _calculate_layout
        except Exception as e:
            logger.warning(f"Error loading achievement icon: {e}")

        # Load achievement panel background (same as options)
        try:
            ach_bg = pygame.image.load('assets/OptionsMenuBG.png').convert_alpha()
            self.achievement_panel_bg = pygame.transform.smoothscale(
                ach_bg, (self.achievement_panel_width, self.achievement_panel_height))
        except Exception as e:
            logger.warning(f"Error loading achievement panel bg: {e}")
            self.achievement_panel_bg = None

        # Load reward icons for profile (will be pre-scaled in _calculate_layout)
        self.reward_icons_raw = {}
        for icon_path in ALL_REWARD_ICON_PATHS:
            try:
                self.reward_icons_raw[icon_path] = pygame.image.load(icon_path).convert_alpha()
            except Exception as e:
                logger.warning(f"Could not load reward icon {icon_path}: {e}")
                self.reward_icons_raw[icon_path] = None

        # Pre-scaled versions for profile panel and profile button (created in _calculate_layout)
        # This avoids expensive smoothscale operations during animation frames
        self.hero_icons_panel_scaled = []  # For 8 icons in profile panel
        self.hero_icons_button_scaled = []  # For profile button
        self.icon_border_panel_scaled = None  # For borders in profile panel
        self.icon_border_button_scaled = None  # For border on profile button

    def _get_cached_font(self, font_path, size):
        """P8 fix: return cached font, creating it only once per (path, size) pair."""
        key = (font_path, size)
        if key not in self._font_cache:
            try:
                self._font_cache[key] = pygame.font.Font(font_path, size)
            except (FileNotFoundError, OSError):
                self._font_cache[key] = pygame.font.SysFont('arial', size, bold=True)
        return self._font_cache[key]

    def _calculate_layout(self):
        """Calculate button positions and pre-scale hero icons"""
        button_width = 400
        button_height = 70
        button_spacing = 20

        center_x = self.width // 2
        start_y = self.height // 2 - 100

        self.buttons = {}
        y = start_y

        button_list = [
            ('campaign', 'Campaign'),
            ('custom_game', 'Custom Game'),
            ('multiplayer', 'Multiplayer'),
            ('options', 'Options'),
            ('quit', 'Quit Game')
        ]

        for button_id, button_text in button_list:
            self.buttons[button_id] = {
                'text': button_text,
                'rect': pygame.Rect(center_x - button_width // 2, y, button_width, button_height)
            }
            y += button_height + button_spacing

        # Profile button in top right corner
        profile_button_size = 60
        profile_button_margin = 20
        self.profile_button_rect = pygame.Rect(
            self.width - profile_button_size - profile_button_margin,
            profile_button_margin,
            profile_button_size,
            profile_button_size
        )

        # Achievement button in top left corner (mirrors profile button)
        self.achievement_button_rect = pygame.Rect(
            profile_button_margin,
            profile_button_margin,
            profile_button_size,
            profile_button_size
        )

        # Pre-scale hero icons for profile panel (done once during layout calculation)
        # This prevents expensive smoothscale operations during every render frame
        icon_size_panel = int(60 * self.ui_scale)
        self.hero_icons_panel_scaled = []
        for hero_icon in self.hero_icons:
            if hero_icon:
                scaled = pygame.transform.smoothscale(hero_icon, (icon_size_panel, icon_size_panel))
                self.hero_icons_panel_scaled.append(scaled)
            else:
                self.hero_icons_panel_scaled.append(None)

        # Pre-scale hero icons for profile button
        self.hero_icons_button_scaled = []
        for hero_icon in self.hero_icons:
            if hero_icon:
                scaled = pygame.transform.smoothscale(hero_icon, (profile_button_size, profile_button_size))
                self.hero_icons_button_scaled.append(scaled)
            else:
                self.hero_icons_button_scaled.append(None)

        # Pre-scale icon borders
        if self.icon_border:
            self.icon_border_panel_scaled = pygame.transform.smoothscale(
                self.icon_border, (icon_size_panel, icon_size_panel)
            )
            self.icon_border_button_scaled = pygame.transform.smoothscale(
                self.icon_border, (profile_button_size, profile_button_size)
            )
        else:
            self.icon_border_panel_scaled = None
            self.icon_border_button_scaled = None

        # Pre-scale achievement button icon
        if self.achievement_button_icon:
            self.achievement_button_icon_scaled = pygame.transform.smoothscale(
                self.achievement_button_icon, (profile_button_size, profile_button_size)
            )
        else:
            self.achievement_button_icon_scaled = None

        # Pre-scale reward icons for profile panel
        self.reward_icons_panel_scaled = {}
        for path, raw_icon in self.reward_icons_raw.items():
            if raw_icon:
                self.reward_icons_panel_scaled[path] = pygame.transform.smoothscale(
                    raw_icon, (icon_size_panel, icon_size_panel))
            else:
                self.reward_icons_panel_scaled[path] = None

        # Pre-scale reward icons for profile button display
        self.reward_icons_button_scaled = {}
        for path, raw_icon in self.reward_icons_raw.items():
            if raw_icon:
                self.reward_icons_button_scaled[path] = pygame.transform.smoothscale(
                    raw_icon, (profile_button_size, profile_button_size))
            else:
                self.reward_icons_button_scaled[path] = None

    def run(self):
        """Main menu loop - returns action to take"""
        while self.result is None:
            dt = self.clock.tick(60) / 1000.0

            # Animate options panel
            self._update_options_animation(dt)

            self.handle_events()
            self.render()
            draw_custom_cursor(self.screen)

            pygame.display.flip()

        return self.result

    def _update_options_animation(self, dt):
        """Smoothly animate the options panel sliding in/out"""
        if self.options_panel_y != self.options_panel_target_y:
            # Calculate distance to move this frame
            distance = self.options_animation_speed * dt

            if self.options_panel_y < self.options_panel_target_y:
                # Sliding down
                self.options_panel_y = min(self.options_panel_y + distance, self.options_panel_target_y)
            else:
                # Sliding up
                self.options_panel_y = max(self.options_panel_y - distance, self.options_panel_target_y)

        # Also animate profile panel
        if self.profile_panel_y != self.profile_panel_target_y:
            distance = self.profile_animation_speed * dt

            if self.profile_panel_y < self.profile_panel_target_y:
                self.profile_panel_y = min(self.profile_panel_y + distance, self.profile_panel_target_y)
            else:
                self.profile_panel_y = max(self.profile_panel_y - distance, self.profile_panel_target_y)

        # Also animate achievement panel
        if self.achievement_panel_y != self.achievement_panel_target_y:
            distance = self.achievement_animation_speed * dt

            if self.achievement_panel_y < self.achievement_panel_target_y:
                self.achievement_panel_y = min(self.achievement_panel_y + distance, self.achievement_panel_target_y)
            else:
                self.achievement_panel_y = max(self.achievement_panel_y - distance, self.achievement_panel_target_y)

    def handle_events(self):
        """Process events"""
        mouse_pos = pygame.mouse.get_pos()

        # Update hover state
        if self.show_achievements:
            # Update hover for achievement panel elements
            self.hovered_achievement_element = self.achievement_panel_helper.get_element_at(mouse_pos)
        elif self.show_profile:
            # Update hover for profile panel elements
            self.hovered_profile_element = None
            # When title dropdown is open, check if mouse is in the dropdown area
            # and prioritize dropdown options over icons underneath
            dd_list_rect = getattr(self, '_title_dropdown_list_rect', None)
            mouse_in_dropdown = (self.title_dropdown_open and dd_list_rect
                                 and dd_list_rect.collidepoint(mouse_pos))
            for element_id, element_data in self.profile_ui_elements.items():
                if 'rect' in element_data and element_data['rect'].collidepoint(mouse_pos):
                    # Skip non-dropdown elements when mouse is inside dropdown area
                    if mouse_in_dropdown and not element_id.startswith('title_option_'):
                        continue
                    self.hovered_profile_element = element_id
                    break
        elif self.show_options:
            # Update hover for options panel elements
            self.hovered_option_element = None
            for element_id, element_data in self.options_ui_elements.items():
                if 'rect' in element_data and element_data['rect'].collidepoint(mouse_pos):
                    self.hovered_option_element = element_id
                    break
        else:
            # Update hover for main menu buttons and profile button
            self.hovered_button = None
            for button_id, button_data in self.buttons.items():
                if button_data['rect'].collidepoint(mouse_pos):
                    self.hovered_button = button_id
                    break

            # Check profile button hover
            if self.profile_button_rect.collidepoint(mouse_pos):
                self.hovered_button = 'profile'

            # Check achievement button hover
            if self.achievement_button_rect.collidepoint(mouse_pos):
                self.hovered_button = 'achievements'

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.result = 'quit'

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # If any panel is open, close it; otherwise quit
                    if self.show_achievements:
                        self._close_achievements()
                    elif self.show_profile:
                        self._close_profile()
                    elif self.show_options:
                        self._close_options()
                    else:
                        self.result = 'quit'

                # Handle text input for achievement search
                elif self.show_achievements:
                    self.achievement_panel_helper.handle_keydown(event)

                # Handle text input for profile name
                elif self.show_profile and self.profile_name_active:
                    if event.key == pygame.K_BACKSPACE:
                        self.temp_player_name = self.temp_player_name[:-1]
                    elif event.key == pygame.K_RETURN or event.key == pygame.K_ESCAPE:
                        self.profile_name_active = False
                    elif len(self.temp_player_name) < 20 and event.unicode.isprintable():
                        self.temp_player_name += event.unicode

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self.handle_click(mouse_pos)
                elif event.button in (4, 5) and self.show_achievements:
                    # Mouse wheel scroll in achievement panel
                    direction = 1 if event.button == 4 else -1
                    max_scroll = getattr(self.achievement_panel_helper, '_max_scroll', 0)
                    self.achievement_panel_helper.handle_scroll(direction, max_scroll)
                elif event.button in (4, 5) and self.show_profile:
                    # Title dropdown scroll takes priority when open and mouse is over it
                    dd_rect = getattr(self, '_title_dropdown_list_rect', None)
                    if self.title_dropdown_open and dd_rect and dd_rect.collidepoint(mouse_pos):
                        max_dd_scroll = getattr(self, '_title_dropdown_max_scroll', 0)
                        if event.button == 4:  # Scroll up
                            self.title_dropdown_scroll = max(0, self.title_dropdown_scroll - 1)
                        else:  # Scroll down
                            self.title_dropdown_scroll = min(max_dd_scroll, self.title_dropdown_scroll + 1)
                    else:
                        # Mouse wheel scroll for profile icon grid
                        scroll_amount = int(30 * self.ui_scale)
                        if event.button == 4:  # Scroll up
                            self.icon_scroll_offset = max(0, self.icon_scroll_offset - scroll_amount)
                        else:  # Scroll down
                            max_scroll = getattr(self, '_icon_max_scroll', 0)
                            self.icon_scroll_offset = min(max_scroll, self.icon_scroll_offset + scroll_amount)
                elif event.button in (4, 5) and self.show_options:
                    # Mouse wheel scroll for options panel content
                    scroll_amount = int(30 * self.ui_scale)
                    if event.button == 4:  # Scroll up
                        self.options_scroll_offset = max(0, self.options_scroll_offset - scroll_amount)
                    else:  # Scroll down
                        self.options_scroll_offset = min(self.options_max_scroll, self.options_scroll_offset + scroll_amount)

            elif event.type == pygame.MOUSEMOTION:
                # Slider drag handling for options panel
                if self.show_options and self.options_dragging_slider:
                    mouse_x = event.pos[0]
                    if self.options_dragging_slider == 'pan_speed' and self.options_pan_speed_slider:
                        track_rect, min_val, max_val, _ = self.options_pan_speed_slider
                        rel_x = (mouse_x - self.options_drag_offset) - track_rect.x
                        slider_pos = max(0, min(1, rel_x / track_rect.width))
                        self.temp_pan_speed = min_val + slider_pos * (max_val - min_val)
                    elif self.options_dragging_slider == 'zoom_speed' and self.options_zoom_speed_slider:
                        track_rect, min_val, max_val, _ = self.options_zoom_speed_slider
                        rel_x = (mouse_x - self.options_drag_offset) - track_rect.x
                        slider_pos = max(0, min(1, rel_x / track_rect.width))
                        self.temp_zoom_speed = min_val + slider_pos * (max_val - min_val)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    # Release slider drag
                    self.options_dragging_slider = None
                    self.options_drag_offset = 0

    def handle_click(self, pos):
        """Handle button clicks"""
        # Check if achievement panel is open
        if self.show_achievements and self.achievement_panel_y > -self.achievement_panel_height + 50:
            result = self.achievement_panel_helper.handle_click(
                pos, self.achievement_panel_x, int(self.achievement_panel_y),
                self.achievement_panel_width, self.achievement_panel_height)
            if result == 'close':
                self._close_achievements()
            return

        # Check if profile panel is open
        if self.show_profile and self.profile_panel_y > -self.profile_panel_height + 50:
            # Check Cancel button
            if 'cancel_button' in self.profile_ui_elements and self.profile_ui_elements['cancel_button']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self._close_profile()
                return

            # Check Save button
            if 'save_button' in self.profile_ui_elements and self.profile_ui_elements['save_button']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self._save_profile()
                self._close_profile()
                return

            # Check player name input field
            if 'name_input' in self.profile_ui_elements and self.profile_ui_elements['name_input']['rect'].collidepoint(pos):
                self.profile_name_active = True
                self.title_dropdown_open = False
                return

            # Check title dropdown toggle
            if 'title_dropdown' in self.profile_ui_elements and self.profile_ui_elements['title_dropdown']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.title_dropdown_open = not self.title_dropdown_open
                self.title_dropdown_scroll = 0  # Reset scroll when toggling
                self.profile_name_active = False
                return

            # Check title dropdown options (if open)
            if self.title_dropdown_open:
                all_title_options = [None] + list(ALL_TITLES)
                for idx in range(len(all_title_options)):
                    opt_key = f'title_option_{idx}'
                    if opt_key in self.profile_ui_elements and self.profile_ui_elements[opt_key]['rect'].collidepoint(pos):
                        opt_data = self.profile_ui_elements[opt_key]
                        if not opt_data.get('locked', False):
                            sound_manager.play_ui_click()
                            self.temp_selected_title = all_title_options[idx]
                            self.title_dropdown_open = False
                        return

                # Click outside dropdown closes it
                self.title_dropdown_open = False

            # Check hero icon selection (indices 0-8: question mark + 8 heroes)
            num_hero_icons = 1 + len(self.hero_icons)
            for i in range(num_hero_icons):
                icon_key = f'icon_{i}'
                if icon_key in self.profile_ui_elements and self.profile_ui_elements[icon_key]['rect'].collidepoint(pos):
                    sound_manager.play_ui_click()
                    self.temp_player_icon = i
                    return

            # Check reward icon selection
            for key, data in self.profile_ui_elements.items():
                if key.startswith('reward_icon_') and data['rect'].collidepoint(pos):
                    reward_idx = int(key.split('_')[-1])
                    unlocked_reward_icons = achievement_manager.get_unlocked_reward_icons()
                    locked_reward_icons = [p for p in ALL_REWARD_ICON_PATHS if p not in unlocked_reward_icons]
                    reward_icon_order = unlocked_reward_icons + locked_reward_icons
                    if reward_idx < len(reward_icon_order):
                        reward_path = reward_icon_order[reward_idx]
                        is_unlocked, _ = achievement_manager.get_reward_icon_info(reward_path)
                        if is_unlocked:
                            sound_manager.play_ui_click()
                            self.temp_player_icon = reward_path
                    return

            # Don't handle menu button clicks if profile panel is open
            return

        # Check if options panel is open
        if self.show_options and self.options_panel_y > -self.options_panel_height + 50:
            # Check Cancel button
            if 'cancel_button' in self.options_ui_elements and self.options_ui_elements['cancel_button']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self._close_options()
                return

            # Check Apply button
            if 'apply_button' in self.options_ui_elements and self.options_ui_elements['apply_button']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self._apply_options()
                self._close_options()
                return

            # Check Reset to Defaults button
            if 'reset_button' in self.options_ui_elements and self.options_ui_elements['reset_button']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self._reset_to_defaults()
                return

            # Resolution dropdown
            if 'resolution_dropdown' in self.options_ui_elements and self.options_ui_elements['resolution_dropdown']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.resolution_dropdown_open = not self.resolution_dropdown_open
                return

            # Resolution options (if dropdown is open)
            if self.resolution_dropdown_open:
                for i, res in enumerate(self.available_resolutions):
                    option_key = f'resolution_option_{i}'
                    if option_key in self.options_ui_elements and self.options_ui_elements[option_key]['rect'].collidepoint(pos):
                        sound_manager.play_ui_click()
                        self.temp_resolution = res
                        self.resolution_dropdown_open = False
                        return

            # Fullscreen checkbox
            if 'fullscreen_checkbox' in self.options_ui_elements and self.options_ui_elements['fullscreen_checkbox']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.temp_fullscreen = not self.temp_fullscreen
                return

            # Edge scrolling checkbox
            if 'edge_scrolling_checkbox' in self.options_ui_elements and self.options_ui_elements['edge_scrolling_checkbox']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.temp_edge_scrolling_enabled = not self.temp_edge_scrolling_enabled
                return

            # Edge scrolling mode (click-to-cycle: map_edge <-> window_edge)
            if 'edge_scroll_mode_dropdown' in self.options_ui_elements and self.options_ui_elements['edge_scroll_mode_dropdown']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                if self.temp_edge_scrolling_mode == "map_edge":
                    self.temp_edge_scrolling_mode = "window_edge"
                else:
                    self.temp_edge_scrolling_mode = "map_edge"
                return

            # Tooltips checkbox
            if 'tooltips_checkbox' in self.options_ui_elements and self.options_ui_elements['tooltips_checkbox']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.temp_tooltips_enabled = not self.temp_tooltips_enabled
                return

            # Tooltip delay (click-to-cycle: 300 -> 500 -> 700 -> 1000 -> Never -> 300)
            if 'tooltip_delay_dropdown' in self.options_ui_elements and self.options_ui_elements['tooltip_delay_dropdown']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                delay_cycle = [300, 500, 700, 1000, -1]
                try:
                    idx = delay_cycle.index(self.temp_tooltip_delay_ms)
                    self.temp_tooltip_delay_ms = delay_cycle[(idx + 1) % len(delay_cycle)]
                except ValueError:
                    self.temp_tooltip_delay_ms = 300
                return

            # Pan Speed slider — thumb click starts drag, track click jumps
            if 'pan_speed_thumb' in self.options_ui_elements and self.options_ui_elements['pan_speed_thumb']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.options_dragging_slider = 'pan_speed'
                thumb_rect = self.options_ui_elements['pan_speed_thumb']['rect']
                self.options_drag_offset = pos[0] - thumb_rect.centerx
                return
            if 'pan_speed_track' in self.options_ui_elements and self.options_ui_elements['pan_speed_track']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                track_rect = self.options_ui_elements['pan_speed_track']['rect']
                rel_x = pos[0] - track_rect.x
                slider_pos = max(0, min(1, rel_x / track_rect.width))
                self.temp_pan_speed = 5.0 + slider_pos * (20.0 - 5.0)
                return

            # Zoom Speed slider — thumb click starts drag, track click jumps
            if 'zoom_speed_thumb' in self.options_ui_elements and self.options_ui_elements['zoom_speed_thumb']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.options_dragging_slider = 'zoom_speed'
                thumb_rect = self.options_ui_elements['zoom_speed_thumb']['rect']
                self.options_drag_offset = pos[0] - thumb_rect.centerx
                return
            if 'zoom_speed_track' in self.options_ui_elements and self.options_ui_elements['zoom_speed_track']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                track_rect = self.options_ui_elements['zoom_speed_track']['rect']
                rel_x = pos[0] - track_rect.x
                slider_pos = max(0, min(1, rel_x / track_rect.width))
                self.temp_zoom_speed = 0.05 + slider_pos * (0.30 - 0.05)
                return

            # Show FPS checkbox
            if 'show_fps_checkbox' in self.options_ui_elements and self.options_ui_elements['show_fps_checkbox']['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.temp_show_fps = not self.temp_show_fps
                return

            # Don't handle menu button clicks if options panel is open
            return

        # Handle achievement button click (top-left)
        if self.achievement_button_rect.collidepoint(pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'achievements'
            self._open_achievements()
            return

        # Handle profile button click
        if self.profile_button_rect.collidepoint(pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'profile'
            self._open_profile()
            return

        # Handle main menu button clicks
        for button_id, button_data in self.buttons.items():
            if button_data['rect'].collidepoint(pos):
                sound_manager.play_ui_click()
                self.clicked_button = button_id

                if button_id == 'campaign':
                    self.result = 'campaign'
                elif button_id == 'custom_game':
                    self.result = 'custom_game'
                elif button_id == 'multiplayer':
                    self.result = 'multiplayer'
                elif button_id == 'options':
                    # Toggle sliding options panel
                    self._open_options()
                elif button_id == 'quit':
                    self.result = 'quit'

                break

    def _open_options(self):
        """Open the sliding options panel"""
        self.show_options = True
        self.options_panel_target_y = self.options_panel_final_y  # Slide to center
        # Reset temporary settings to current settings
        self.temp_resolution = settings.get_resolution()
        self.temp_fullscreen = settings.is_fullscreen()
        self.temp_edge_scrolling_enabled = settings.get('edge_scrolling_enabled', True)
        self.temp_tooltips_enabled = settings.get('tooltips_enabled', True)
        self.temp_show_fps = settings.get('show_fps', False)
        self.temp_edge_scrolling_mode = settings.get('edge_scrolling_mode', 'map_edge')
        self.temp_tooltip_delay_ms = settings.get('tooltip_delay_ms', 500)
        self.temp_pan_speed = settings.get('camera_pan_speed', 10.0)
        self.temp_zoom_speed = settings.get('camera_zoom_speed', 0.15)
        self.resolution_dropdown_open = False
        self.options_scroll_offset = 0
        self.options_dragging_slider = None
        self.options_drag_offset = 0

    def _close_options(self):
        """Close the sliding options panel"""
        self.show_options = False
        self.options_panel_target_y = -self.options_panel_height  # Slide back up
        self.resolution_dropdown_open = False
        self.options_dragging_slider = None
        self.options_drag_offset = 0

    def _open_profile(self):
        """Open the sliding profile panel"""
        self.show_profile = True
        self.profile_panel_target_y = self.profile_panel_final_y
        # Reset temporary settings to current settings
        self.temp_player_name = settings.get_player_name()
        self.temp_player_icon = settings.get_player_icon()
        self.temp_selected_title = settings.get_selected_title()
        self.profile_name_active = False
        self.title_dropdown_open = False

    def _close_profile(self):
        """Close the sliding profile panel"""
        self.show_profile = False
        self.profile_panel_target_y = -self.profile_panel_height
        self.profile_name_active = False
        self.title_dropdown_open = False

    def _save_profile(self):
        """Save current profile settings to global settings"""
        settings.set_player_name(self.temp_player_name)
        settings.set_player_icon(self.temp_player_icon)
        settings.set_selected_title(self.temp_selected_title)
        settings.save()
        logger.info(f"Profile saved: {self.temp_player_name}, Icon: {self.temp_player_icon}, Title: {self.temp_selected_title}")

    def _open_achievements(self):
        """Open the sliding achievement panel"""
        self.show_achievements = True
        self.achievement_panel_target_y = self.achievement_panel_final_y
        self.achievement_panel_helper.reset()

    def _close_achievements(self):
        """Close the sliding achievement panel"""
        self.show_achievements = False
        self.achievement_panel_target_y = -self.achievement_panel_height

    def _apply_options(self):
        """Apply current temporary settings to global settings"""
        # Check if display settings changed
        old_resolution = settings.get_resolution()
        old_fullscreen = settings.is_fullscreen()

        settings.set_resolution(self.temp_resolution[0], self.temp_resolution[1])
        settings.set_fullscreen(self.temp_fullscreen)
        settings.set('edge_scrolling_enabled', self.temp_edge_scrolling_enabled)
        settings.set('tooltips_enabled', self.temp_tooltips_enabled)
        settings.set('show_fps', self.temp_show_fps)
        settings.set('edge_scrolling_mode', self.temp_edge_scrolling_mode)
        settings.set('tooltip_delay_ms', self.temp_tooltip_delay_ms)
        settings.set('camera_pan_speed', self.temp_pan_speed)
        settings.set('camera_zoom_speed', self.temp_zoom_speed)

        settings.save()
        logger.info("Settings applied and saved")

        # If display settings changed, trigger window recreation
        if old_resolution != self.temp_resolution or old_fullscreen != self.temp_fullscreen:
            logger.info("Display settings changed - recreating window...")
            self.result = 'recreate_window'

    def _reset_to_defaults(self):
        """Reset all temp settings to default values (must click Apply to save)"""
        # Get default resolution from settings (intelligently chosen from supported resolutions)
        default_resolution = settings.get_default_resolution()

        # Reset all temp settings to defaults
        self.temp_resolution = default_resolution
        self.temp_fullscreen = True
        self.temp_edge_scrolling_enabled = True
        self.temp_tooltips_enabled = True
        self.temp_show_fps = False
        self.temp_edge_scrolling_mode = "map_edge"
        self.temp_tooltip_delay_ms = 500
        self.temp_pan_speed = 10.0
        self.temp_zoom_speed = 0.15

        logger.info(f"Settings reset to defaults: {default_resolution[0]}x{default_resolution[1]} (click Apply to save)")

    def render(self):
        """Render main menu"""
        # Draw background image
        self.screen.blit(self.background, (0, 0))

        # Draw logo (if loaded)
        if self.logo:
            logo_rect = self.logo.get_rect(center=(self.width // 2, self.height // 2 - 250))
            self.screen.blit(self.logo, logo_rect)
        else:
            # Fallback to text if logo failed to load
            title_text = self.title_font.render("War of Avareon", True, WHITE)
            title_rect = title_text.get_rect(center=(self.width // 2, self.height // 2 - 250))
            self.screen.blit(title_text, title_rect)

        # Buttons
        for button_id, button_data in self.buttons.items():
            self._draw_button(button_id, button_data)

        # Draw profile button in top right corner
        self._draw_profile_button()

        # Draw achievement button in top left corner
        self._draw_achievement_button()

        # Draw sliding options panel
        if self.options_panel_y > -self.options_panel_height:
            self._draw_options_panel()

        # Draw sliding profile panel
        if self.profile_panel_y > -self.profile_panel_height:
            self._draw_profile_panel()

        # Draw sliding achievement panel
        if self.achievement_panel_y > -self.achievement_panel_height:
            self._draw_achievement_panel()

        # Draw tooltips for profile/achievement buttons when no panel is open
        if not self.show_profile and not self.show_achievements and not self.show_options:
            if self.hovered_button == 'profile':
                self._draw_tooltip(self.screen, "Profile", pygame.mouse.get_pos(), self.tooltip_font)
            elif self.hovered_button == 'achievements':
                self._draw_tooltip(self.screen, "Achievements", pygame.mouse.get_pos(), self.tooltip_font)

        # Draw version label in bottom-left corner
        version_text = self.tooltip_font.render(f"Version: {GAME_VERSION}", True, GRAY)
        self.screen.blit(version_text, (10, self.height - version_text.get_height() - 10))

        # Reset clicked state after render
        self.clicked_button = None


    def _draw_button(self, button_id, button_data):
        """Draw a menu button with custom background"""
        rect = button_data['rect']
        text = button_data['text']

        # Determine state
        is_hovered = (self.hovered_button == button_id)
        is_clicked = (self.clicked_button == button_id)

        # Draw custom button background or fallback
        if self.button_bg_image:
            # P5 fix: cache pre-scaled button background instead of smoothscale per frame
            btn_size = (rect.width, rect.height)
            if not hasattr(self, '_scaled_button_bg_cache') or self._scaled_button_bg_cache is None or self._scaled_button_bg_cache.get_size() != btn_size:
                self._scaled_button_bg_cache = pygame.transform.smoothscale(
                    self.button_bg_image, btn_size)
            scaled_button_bg = self._scaled_button_bg_cache

            # Darken the button base, then add brightness for states
            button_surface = scaled_button_bg.copy()
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

            if is_clicked:
                # More brightness than hover on click
                button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif is_hovered:
                # Subtle brightness on hover
                button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)

            self.screen.blit(button_surface, rect)
        else:
            # Fallback to old rectangle style
            if is_clicked:
                bg_color = brighten_color((70, 120, 200), 0.4)
            elif is_hovered:
                bg_color = lighten_color((70, 120, 200), 0.2)
            else:
                bg_color = (70, 120, 200)

            pygame.draw.rect(self.screen, bg_color, rect, border_radius=10)
            pygame.draw.rect(self.screen, (150, 150, 150), rect, 3, border_radius=10)

        # Draw text
        button_text = self.button_font.render(text, True, WHITE)
        text_rect = button_text.get_rect(center=rect.center)
        self.screen.blit(button_text, text_rect)

    def _draw_options_panel(self):
        """Draw the sliding options panel with custom background and controls"""
        panel_x = self.options_panel_x
        panel_y = int(self.options_panel_y)
        panel_w = self.options_panel_width
        panel_h = self.options_panel_height

        # Clear previous UI elements
        self.options_ui_elements = {}

        # Panel background - use custom image if available, otherwise solid color with shadow
        if self.options_panel_bg:
            # Custom background - no shadow needed (design has its own depth)
            self.screen.blit(self.options_panel_bg, (panel_x, panel_y))
        else:
            # Fallback solid color with shadow
            shadow_offset = 8
            shadow_surface = pygame.Surface((panel_w, panel_h))
            shadow_surface.fill((0, 0, 0))
            shadow_surface.set_alpha(80)
            self.screen.blit(shadow_surface, (panel_x + shadow_offset, panel_y + shadow_offset))

            panel_surface = pygame.Surface((panel_w, panel_h))
            panel_surface.fill((45, 45, 55))
            self.screen.blit(panel_surface, (panel_x, panel_y))

        # Border around panel (removed - custom background has its own design)
        # pygame.draw.rect(self.screen, (100, 100, 120),
        #                 (panel_x, panel_y, panel_w, panel_h), 4, border_radius=10)

        # Add padding to account for the ornate border in the custom background (scaled)
        padding_top = int(120 * self.ui_scale)
        padding_bottom = int(120 * self.ui_scale)
        padding_sides = int(120 * self.ui_scale)

        # Title (scaled font)
        title_font_size = max(36, int(72 * self.ui_scale))
        title_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', title_font_size)
        title_text = title_font.render("Options", True, WHITE)
        title_rect = title_text.get_rect(center=(panel_x + panel_w // 2, panel_y + padding_top))
        self.screen.blit(title_text, title_rect)

        # Content area (adjusted for ornate border, scaled)
        content_x = panel_x + padding_sides
        content_y = panel_y + padding_top + int(30 * self.ui_scale)
        label_x_offset = 0
        control_x_offset = int(280 * self.ui_scale)

        # Scaled fonts for options panel
        section_font_size = max(20, int(34 * self.ui_scale))
        label_font_size = max(16, int(28 * self.ui_scale))
        section_font = self._get_cached_font('assets/fonts/Cinzel-SemiBold.ttf', section_font_size)
        label_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', label_font_size)

        # Common control dimensions
        checkbox_x = content_x + control_x_offset
        checkbox_size = int(30 * self.ui_scale)
        dropdown_x = content_x + control_x_offset
        dropdown_width = int(180 * self.ui_scale)
        dropdown_height = int(35 * self.ui_scale)

        # Scrollable content area boundaries (between title and buttons)
        content_area_top = content_y
        buttons_y = panel_y + panel_h - padding_bottom - int(70 * self.ui_scale)
        content_area_bottom = buttons_y - int(15 * self.ui_scale)
        content_area_height = content_area_bottom - content_area_top
        content_width = panel_w - 2 * padding_sides

        # Set clip rect for scrollable content
        content_clip_rect = pygame.Rect(content_x - 5, content_area_top, content_width + 10, content_area_height)
        original_clip = self.screen.get_clip()
        self.screen.set_clip(content_clip_rect)

        # Apply scroll offset to y
        y = content_area_top - self.options_scroll_offset
        content_start_y = y

        # === DISPLAY SECTION ===
        section_text = section_font.render("Display:", True, WHITE)
        self.screen.blit(section_text, (content_x, y))
        y += int(42 * self.ui_scale)

        # Resolution dropdown
        label_text = label_font.render("Resolution:", True, WHITE)
        self.screen.blit(label_text, (content_x + label_x_offset, y))

        dropdown_rect = pygame.Rect(dropdown_x, y - 5, dropdown_width, dropdown_height)
        is_hovered = (self.hovered_option_element == 'resolution_dropdown')
        bg_color = (30, 30, 30) if is_hovered else (20, 20, 20)
        pygame.draw.rect(self.screen, bg_color, dropdown_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), dropdown_rect, 2, border_radius=5)
        dropdown_text = label_font.render(f"{self.temp_resolution[0]}x{self.temp_resolution[1]}", True, WHITE)
        dropdown_text_rect = dropdown_text.get_rect(center=dropdown_rect.center)
        self.screen.blit(dropdown_text, dropdown_text_rect)
        self.options_ui_elements['resolution_dropdown'] = {'rect': dropdown_rect}

        # Store dropdown info for overlay rendering (drawn after clip is restored)
        res_dropdown_overlay_y = y
        y += int(40 * self.ui_scale)

        # Fullscreen checkbox
        label_text = label_font.render("Fullscreen:", True, WHITE)
        self.screen.blit(label_text, (content_x + label_x_offset, y))
        checkbox_rect = pygame.Rect(checkbox_x, y - 5, checkbox_size, checkbox_size)
        is_hovered = (self.hovered_option_element == 'fullscreen_checkbox')
        bg_color = (30, 30, 30) if is_hovered else (20, 20, 20)
        pygame.draw.rect(self.screen, bg_color, checkbox_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), checkbox_rect, 2, border_radius=5)
        if self.temp_fullscreen:
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.left + 6, checkbox_rect.centery),
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8), 3)
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8),
                           (checkbox_rect.right - 6, checkbox_rect.top + 6), 3)
        self.options_ui_elements['fullscreen_checkbox'] = {'rect': checkbox_rect}
        y += int(40 * self.ui_scale)

        # === GAMEPLAY SECTION === (horizontal separator line)
        separator_y = y + int(3 * self.ui_scale)
        pygame.draw.line(self.screen, WHITE, (content_x, separator_y), (content_x + content_width, separator_y), 2)
        y += int(12 * self.ui_scale)
        section_text = section_font.render("Gameplay:", True, WHITE)
        self.screen.blit(section_text, (content_x, y))
        y += int(42 * self.ui_scale)

        # Edge scrolling checkbox (underlined to show sub-option relationship)
        label_text = label_font.render("Edge Scrolling:", True, WHITE)
        self.screen.blit(label_text, (content_x + label_x_offset, y))
        underline_y = y + label_text.get_height() - int(2 * self.ui_scale)
        pygame.draw.line(self.screen, WHITE, (content_x + label_x_offset, underline_y),
                        (content_x + label_x_offset + label_text.get_width(), underline_y), 1)
        checkbox_rect = pygame.Rect(checkbox_x, y - 5, checkbox_size, checkbox_size)
        is_hovered = (self.hovered_option_element == 'edge_scrolling_checkbox')
        bg_color = (30, 30, 30) if is_hovered else (20, 20, 20)
        pygame.draw.rect(self.screen, bg_color, checkbox_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), checkbox_rect, 2, border_radius=5)
        if self.temp_edge_scrolling_enabled:
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.left + 6, checkbox_rect.centery),
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8), 3)
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8),
                           (checkbox_rect.right - 6, checkbox_rect.top + 6), 3)
        self.options_ui_elements['edge_scrolling_checkbox'] = {'rect': checkbox_rect}
        y += int(35 * self.ui_scale)

        # Edge scrolling mode (conditional — only shown when edge scrolling is enabled)
        if self.temp_edge_scrolling_enabled:
            mode_label = label_font.render("Mode:", True, WHITE)
            self.screen.blit(mode_label, (content_x + label_x_offset, y))

            mode_text = "Map Edge" if self.temp_edge_scrolling_mode == "map_edge" else "Window Edge"
            mode_rect = pygame.Rect(dropdown_x, y - 5, dropdown_width, dropdown_height)
            is_hovered = (self.hovered_option_element == 'edge_scroll_mode_dropdown')
            bg_color = (30, 30, 30) if is_hovered else (20, 20, 20)
            pygame.draw.rect(self.screen, bg_color, mode_rect, border_radius=5)
            pygame.draw.rect(self.screen, (100, 100, 100), mode_rect, 2, border_radius=5)
            # Use smaller font so "Window Edge" fits inside the dropdown
            dropdown_label_size = max(14, int(22 * self.ui_scale))
            dropdown_label_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', dropdown_label_size)
            mode_dd_text = dropdown_label_font.render(mode_text, True, WHITE)
            mode_dd_text_rect = mode_dd_text.get_rect(center=mode_rect.center)
            self.screen.blit(mode_dd_text, mode_dd_text_rect)
            self.options_ui_elements['edge_scroll_mode_dropdown'] = {'rect': mode_rect}
            y += int(35 * self.ui_scale)

        # Tooltips checkbox (underlined to show sub-option relationship)
        label_text = label_font.render("Tooltips:", True, WHITE)
        self.screen.blit(label_text, (content_x + label_x_offset, y))
        underline_y = y + label_text.get_height() - int(2 * self.ui_scale)
        pygame.draw.line(self.screen, WHITE, (content_x + label_x_offset, underline_y),
                        (content_x + label_x_offset + label_text.get_width(), underline_y), 1)
        checkbox_rect = pygame.Rect(checkbox_x, y - 5, checkbox_size, checkbox_size)
        is_hovered = (self.hovered_option_element == 'tooltips_checkbox')
        bg_color = (30, 30, 30) if is_hovered else (20, 20, 20)
        pygame.draw.rect(self.screen, bg_color, checkbox_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), checkbox_rect, 2, border_radius=5)
        if self.temp_tooltips_enabled:
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.left + 6, checkbox_rect.centery),
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8), 3)
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8),
                           (checkbox_rect.right - 6, checkbox_rect.top + 6), 3)
        self.options_ui_elements['tooltips_checkbox'] = {'rect': checkbox_rect}
        y += int(35 * self.ui_scale)

        # Tooltip delay (conditional — only shown when tooltips are enabled)
        if self.temp_tooltips_enabled:
            delay_label = label_font.render("Delay:", True, WHITE)
            self.screen.blit(delay_label, (content_x + label_x_offset, y))

            if self.temp_tooltip_delay_ms == -1:
                delay_text = "Never"
            else:
                delay_text = f"{self.temp_tooltip_delay_ms / 1000:.1f}s"
            delay_rect = pygame.Rect(dropdown_x, y - 5, dropdown_width, dropdown_height)
            is_hovered = (self.hovered_option_element == 'tooltip_delay_dropdown')
            bg_color = (30, 30, 30) if is_hovered else (20, 20, 20)
            pygame.draw.rect(self.screen, bg_color, delay_rect, border_radius=5)
            pygame.draw.rect(self.screen, (100, 100, 100), delay_rect, 2, border_radius=5)
            delay_dd_text = label_font.render(delay_text, True, WHITE)
            delay_dd_text_rect = delay_dd_text.get_rect(center=delay_rect.center)
            self.screen.blit(delay_dd_text, delay_dd_text_rect)
            self.options_ui_elements['tooltip_delay_dropdown'] = {'rect': delay_rect}
            y += int(35 * self.ui_scale)

        # Pan Speed slider
        pan_label = label_font.render(f"Pan Speed: {int(self.temp_pan_speed)}", True, WHITE)
        self.screen.blit(pan_label, (content_x + label_x_offset, y))
        y += int(42 * self.ui_scale)

        slider_x = content_x + label_x_offset + int(10 * self.ui_scale)
        slider_width = content_width - int(30 * self.ui_scale)
        slider_height = int(6 * self.ui_scale)
        pan_track_rect = pygame.Rect(slider_x, y, slider_width, slider_height)
        pygame.draw.rect(self.screen, (60, 60, 70), pan_track_rect, border_radius=3)

        pan_min, pan_max = 5.0, 20.0
        pan_thumb_pos = (self.temp_pan_speed - pan_min) / (pan_max - pan_min)
        pan_thumb_x = int(slider_x + pan_thumb_pos * slider_width)
        thumb_w, thumb_h = int(16 * self.ui_scale), int(14 * self.ui_scale)
        pan_thumb_rect = pygame.Rect(pan_thumb_x - thumb_w // 2, y - (thumb_h - slider_height) // 2, thumb_w, thumb_h)
        is_hovered = (self.hovered_option_element == 'pan_speed_thumb')
        thumb_color = (130, 180, 130) if is_hovered else (100, 150, 100)
        pygame.draw.rect(self.screen, thumb_color, pan_thumb_rect, border_radius=3)
        pygame.draw.rect(self.screen, (150, 150, 150), pan_thumb_rect, 1, border_radius=3)

        self.options_ui_elements['pan_speed_track'] = {'rect': pan_track_rect}
        self.options_ui_elements['pan_speed_thumb'] = {'rect': pan_thumb_rect}
        self.options_pan_speed_slider = (pan_track_rect, pan_min, pan_max, pan_thumb_rect)
        y += int(22 * self.ui_scale)

        # Zoom Speed slider
        zoom_label = label_font.render(f"Zoom Speed: {self.temp_zoom_speed:.2f}", True, WHITE)
        self.screen.blit(zoom_label, (content_x + label_x_offset, y))
        y += int(42 * self.ui_scale)

        zoom_track_rect = pygame.Rect(slider_x, y, slider_width, slider_height)
        pygame.draw.rect(self.screen, (60, 60, 70), zoom_track_rect, border_radius=3)

        zoom_min, zoom_max = 0.05, 0.30
        zoom_thumb_pos = (self.temp_zoom_speed - zoom_min) / (zoom_max - zoom_min)
        zoom_thumb_x = int(slider_x + zoom_thumb_pos * slider_width)
        zoom_thumb_rect = pygame.Rect(zoom_thumb_x - thumb_w // 2, y - (thumb_h - slider_height) // 2, thumb_w, thumb_h)
        is_hovered = (self.hovered_option_element == 'zoom_speed_thumb')
        thumb_color = (130, 180, 130) if is_hovered else (100, 150, 100)
        pygame.draw.rect(self.screen, thumb_color, zoom_thumb_rect, border_radius=3)
        pygame.draw.rect(self.screen, (150, 150, 150), zoom_thumb_rect, 1, border_radius=3)

        self.options_ui_elements['zoom_speed_track'] = {'rect': zoom_track_rect}
        self.options_ui_elements['zoom_speed_thumb'] = {'rect': zoom_thumb_rect}
        self.options_zoom_speed_slider = (zoom_track_rect, zoom_min, zoom_max, zoom_thumb_rect)
        y += int(22 * self.ui_scale)

        # Show FPS checkbox
        label_text = label_font.render("Show FPS:", True, WHITE)
        self.screen.blit(label_text, (content_x + label_x_offset, y))
        checkbox_rect = pygame.Rect(checkbox_x, y - 5, checkbox_size, checkbox_size)
        is_hovered = (self.hovered_option_element == 'show_fps_checkbox')
        bg_color = (30, 30, 30) if is_hovered else (20, 20, 20)
        pygame.draw.rect(self.screen, bg_color, checkbox_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), checkbox_rect, 2, border_radius=5)
        if self.temp_show_fps:
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.left + 6, checkbox_rect.centery),
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8), 3)
            pygame.draw.line(self.screen, WHITE,
                           (checkbox_rect.centerx, checkbox_rect.bottom - 8),
                           (checkbox_rect.right - 6, checkbox_rect.top + 6), 3)
        self.options_ui_elements['show_fps_checkbox'] = {'rect': checkbox_rect}
        y += int(40 * self.ui_scale)

        # === AUDIO SECTION (placeholder) === (horizontal separator line)
        separator_y = y + int(3 * self.ui_scale)
        pygame.draw.line(self.screen, WHITE, (content_x, separator_y), (content_x + content_width, separator_y), 2)
        y += int(12 * self.ui_scale)
        audio_header = section_font.render("Audio (Coming Soon):", True, (150, 150, 150))
        self.screen.blit(audio_header, (content_x, y))
        y += int(42 * self.ui_scale)

        audio_box_height = int(90 * self.ui_scale)
        audio_box = pygame.Rect(content_x, y, content_width, audio_box_height)
        pygame.draw.rect(self.screen, (50, 35, 25), audio_box, border_radius=5)
        pygame.draw.rect(self.screen, (80, 80, 80), audio_box, 2, border_radius=5)

        placeholder_lines = [
            "Master Volume: [########__] 80%",
            "Music Volume:  [######____] 60%",
            "SFX Volume:    [#######___] 70%"
        ]
        ph_font_size = max(12, int(20 * self.ui_scale))
        ph_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', ph_font_size)
        ph_y = y + int(10 * self.ui_scale)
        for line in placeholder_lines:
            ph_text = ph_font.render(line, True, (100, 100, 100))
            self.screen.blit(ph_text, (content_x + int(15 * self.ui_scale), ph_y))
            ph_y += int(22 * self.ui_scale)
        y += audio_box_height + int(15 * self.ui_scale)

        # Calculate total content height and max scroll
        total_content_height = y - content_start_y
        self.options_max_scroll = max(0, total_content_height - content_area_height)
        self.options_scroll_offset = max(0, min(self.options_scroll_offset, self.options_max_scroll))

        # Restore clip rect before drawing buttons and overlays
        self.screen.set_clip(original_clip)

        # Draw scrollbar if content overflows
        if self.options_max_scroll > 0:
            scrollbar_width = int(8 * self.ui_scale)
            scrollbar_x = content_x + content_width + int(2 * self.ui_scale)
            scrollbar_track_rect = pygame.Rect(scrollbar_x, content_area_top, scrollbar_width, content_area_height)
            pygame.draw.rect(self.screen, (40, 40, 50), scrollbar_track_rect, border_radius=4)

            # Thumb size proportional to visible area
            thumb_ratio = content_area_height / total_content_height
            scrollbar_thumb_h = max(int(30 * self.ui_scale), int(content_area_height * thumb_ratio))
            scroll_ratio = self.options_scroll_offset / self.options_max_scroll if self.options_max_scroll > 0 else 0
            scrollbar_thumb_y = content_area_top + int(scroll_ratio * (content_area_height - scrollbar_thumb_h))
            scrollbar_thumb_rect = pygame.Rect(scrollbar_x, scrollbar_thumb_y, scrollbar_width, scrollbar_thumb_h)
            pygame.draw.rect(self.screen, (100, 100, 120), scrollbar_thumb_rect, border_radius=4)

        # === BUTTONS (fixed position, outside scroll area) ===
        button_width = int(150 * self.ui_scale)
        button_height = int(50 * self.ui_scale)
        button_spacing = int(20 * self.ui_scale)
        total_buttons_width = button_width * 2 + button_spacing
        buttons_start_x = panel_x + (panel_w - total_buttons_width) // 2

        # Cancel button
        cancel_rect = pygame.Rect(buttons_start_x, buttons_y, button_width, button_height)
        is_hovered = (self.hovered_option_element == 'cancel_button')
        cancel_bg = lighten_color((120, 50, 50), 0.2) if is_hovered else (120, 50, 50)
        pygame.draw.rect(self.screen, cancel_bg, cancel_rect, border_radius=8)
        pygame.draw.rect(self.screen, (150, 150, 150), cancel_rect, 2, border_radius=8)
        cancel_text = self.button_font.render("Cancel", True, WHITE)
        cancel_text_rect = cancel_text.get_rect(center=cancel_rect.center)
        self.screen.blit(cancel_text, cancel_text_rect)
        self.options_ui_elements['cancel_button'] = {'rect': cancel_rect}

        # Apply button
        apply_rect = pygame.Rect(buttons_start_x + button_width + button_spacing, buttons_y,
                                 button_width, button_height)
        is_hovered = (self.hovered_option_element == 'apply_button')
        apply_bg = lighten_color((50, 180, 50), 0.2) if is_hovered else (50, 180, 50)
        pygame.draw.rect(self.screen, apply_bg, apply_rect, border_radius=8)
        pygame.draw.rect(self.screen, (150, 150, 150), apply_rect, 2, border_radius=8)
        apply_text = self.button_font.render("Apply", True, WHITE)
        apply_text_rect = apply_text.get_rect(center=apply_rect.center)
        self.screen.blit(apply_text, apply_text_rect)
        self.options_ui_elements['apply_button'] = {'rect': apply_rect}

        # Reset to Defaults button (centered, below Cancel/Apply buttons)
        reset_button_width = int(300 * self.ui_scale)
        reset_button_height = int(40 * self.ui_scale)
        reset_button_x = panel_x + (panel_w - reset_button_width) // 2
        reset_button_y = buttons_y + button_height + int(15 * self.ui_scale)
        reset_rect = pygame.Rect(reset_button_x, reset_button_y, reset_button_width, reset_button_height)
        is_hovered = (self.hovered_option_element == 'reset_button')
        reset_bg = lighten_color((120, 120, 80), 0.2) if is_hovered else (120, 120, 80)
        pygame.draw.rect(self.screen, reset_bg, reset_rect, border_radius=8)
        pygame.draw.rect(self.screen, (150, 150, 150), reset_rect, 2, border_radius=8)
        reset_text = label_font.render("Reset to Defaults", True, WHITE)
        reset_text_rect = reset_text.get_rect(center=reset_rect.center)
        self.screen.blit(reset_text, reset_text_rect)
        self.options_ui_elements['reset_button'] = {'rect': reset_rect}

        # === DROPDOWN OVERLAYS (drawn last, on top of everything) ===
        if self.resolution_dropdown_open:
            dropdown_y = res_dropdown_overlay_y
            for i, res in enumerate(self.available_resolutions):
                option_rect = pygame.Rect(dropdown_x, dropdown_y, dropdown_width, dropdown_height)
                option_key = f'resolution_option_{i}'
                is_hovered = (self.hovered_option_element == option_key)
                option_bg = lighten_color((60, 60, 70), 0.2) if is_hovered else (60, 60, 70)
                pygame.draw.rect(self.screen, option_bg, option_rect, border_radius=5)
                pygame.draw.rect(self.screen, (150, 150, 150), option_rect, 2, border_radius=5)
                option_text = label_font.render(f"{res[0]}x{res[1]}", True, WHITE)
                option_text_rect = option_text.get_rect(center=option_rect.center)
                self.screen.blit(option_text, option_text_rect)
                self.options_ui_elements[option_key] = {'rect': option_rect}
                dropdown_y += dropdown_height + int(5 * self.ui_scale)

    def _draw_profile_button(self):
        """Draw profile button in top right corner with icon and border"""
        rect = self.profile_button_rect

        # Determine state
        is_hovered = (self.hovered_button == 'profile')
        is_clicked = (self.clicked_button == 'profile')

        # Draw icon background
        icon_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

        # Get current player icon (0 = question mark, 1-7 = hero icons, str = reward icon path)
        current_icon = settings.get_player_icon()

        if isinstance(current_icon, str):
            # Reward icon (stored as path string)
            scaled_reward = self.reward_icons_button_scaled.get(current_icon)
            if scaled_reward:
                icon_surface.blit(scaled_reward, (0, 0))
            else:
                icon_surface.fill((100, 100, 100))
        elif current_icon == 0:
            # Draw question mark for unset icon
            icon_surface.fill((60, 60, 80))
            qm_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', 40)
            qm_text = qm_font.render("?", True, WHITE)
            qm_rect = qm_text.get_rect(center=(rect.width // 2, rect.height // 2))
            icon_surface.blit(qm_text, qm_rect)
        else:
            # Draw actual hero icon using pre-scaled version
            hero_index = current_icon - 1
            if hero_index < len(self.hero_icons_button_scaled) and self.hero_icons_button_scaled[hero_index]:
                icon_surface.blit(self.hero_icons_button_scaled[hero_index], (0, 0))
            else:
                icon_surface.fill((100, 100, 100))

        # Apply hover/click effects
        if is_clicked:
            bright_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bright_overlay.fill((100, 100, 100, 100))
            icon_surface.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif is_hovered:
            light_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            light_overlay.fill((50, 50, 50, 50))
            icon_surface.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        # Draw the icon
        self.screen.blit(icon_surface, rect)

        # Draw border frame overlay using pre-scaled version
        if self.icon_border_button_scaled:
            self.screen.blit(self.icon_border_button_scaled, rect)

    def _draw_achievement_button(self):
        """Draw achievement button in top left corner with icon and border"""
        rect = self.achievement_button_rect

        is_hovered = (self.hovered_button == 'achievements')
        is_clicked = (self.clicked_button == 'achievements')

        # Draw icon background
        icon_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

        if self.achievement_button_icon_scaled:
            icon_surface.blit(self.achievement_button_icon_scaled, (0, 0))
        else:
            # Fallback: dark background with star-like symbol
            icon_surface.fill((60, 60, 80))
            star_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', 30)
            star_text = star_font.render("★", True, WHITE)
            star_rect = star_text.get_rect(center=(rect.width // 2, rect.height // 2))
            icon_surface.blit(star_text, star_rect)

        # Apply hover/click effects
        if is_clicked:
            bright_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bright_overlay.fill((100, 100, 100, 100))
            icon_surface.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif is_hovered:
            light_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            light_overlay.fill((50, 50, 50, 50))
            icon_surface.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.screen.blit(icon_surface, rect)

        # Draw border frame overlay
        if self.icon_border_button_scaled:
            self.screen.blit(self.icon_border_button_scaled, rect)

    def _draw_achievement_panel(self):
        """Draw the sliding achievement panel"""
        panel_x = self.achievement_panel_x
        panel_y = int(self.achievement_panel_y)
        panel_w = self.achievement_panel_width
        panel_h = self.achievement_panel_height

        # Panel background
        if self.achievement_panel_bg:
            self.screen.blit(self.achievement_panel_bg, (panel_x, panel_y))
        else:
            panel_surface = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel_surface.fill((40, 40, 60, 230))
            self.screen.blit(panel_surface, (panel_x, panel_y))

        # Delegate content rendering to achievement panel helper
        self.achievement_panel_helper.draw(
            self.screen, panel_x, panel_y, panel_w, panel_h,
            self.hovered_achievement_element)

    def _draw_tooltip(self, screen, text, pos, font):
        """Draw a tooltip near the mouse position. Supports multi-line text via newline characters."""
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
        screen.blit(bg, (tx, ty))
        for i, surf in enumerate(line_surfaces):
            screen.blit(surf, (tx + pad, ty + pad + i * line_h))

    def _draw_profile_panel(self):
        """Draw the sliding profile panel with player name input and icon selection"""
        panel_x = self.profile_panel_x
        panel_y = int(self.profile_panel_y)
        panel_w = self.profile_panel_width
        panel_h = self.profile_panel_height

        # Clear previous UI elements
        self.profile_ui_elements = {}

        # Panel background
        if self.profile_panel_bg:
            self.screen.blit(self.profile_panel_bg, (panel_x, panel_y))
        else:
            # Fallback solid color with shadow
            shadow_offset = 8
            shadow_surface = pygame.Surface((panel_w, panel_h))
            shadow_surface.fill((0, 0, 0))
            shadow_surface.set_alpha(80)
            self.screen.blit(shadow_surface, (panel_x + shadow_offset, panel_y + shadow_offset))

            panel_surface = pygame.Surface((panel_w, panel_h))
            panel_surface.fill((45, 45, 55))
            self.screen.blit(panel_surface, (panel_x, panel_y))

        # Padding to account for ornate border
        padding_top = int(120 * self.ui_scale)
        padding_bottom = int(120 * self.ui_scale)
        padding_sides = int(120 * self.ui_scale)

        # Title
        title_font_size = max(36, int(72 * self.ui_scale))
        title_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', title_font_size)
        title_text = title_font.render("Profile", True, WHITE)
        title_rect = title_text.get_rect(center=(panel_x + panel_w // 2, panel_y + padding_top))
        self.screen.blit(title_text, title_rect)

        # Content area
        content_x = panel_x + padding_sides
        content_y = panel_y + padding_top + int(60 * self.ui_scale)

        # Scaled fonts
        label_font_size = max(16, int(28 * self.ui_scale))
        label_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', label_font_size)

        # Player Name Section
        y = content_y
        label_text = label_font.render("Player Name:", True, WHITE)
        self.screen.blit(label_text, (content_x, y))
        y += int(35 * self.ui_scale)

        # Name input field
        input_width = int(300 * self.ui_scale)
        input_height = int(40 * self.ui_scale)
        input_rect = pygame.Rect(content_x, y, input_width, input_height)

        # Draw input box (black background)
        is_active = self.profile_name_active
        input_bg = (30, 30, 30) if is_active else (20, 20, 20)
        pygame.draw.rect(self.screen, input_bg, input_rect, border_radius=5)
        pygame.draw.rect(self.screen, WHITE if is_active else (100, 100, 100), input_rect, 2, border_radius=5)

        # Draw current name text
        name_text = label_font.render(self.temp_player_name, True, WHITE)
        name_rect = name_text.get_rect(midleft=(input_rect.left + 10, input_rect.centery))
        self.screen.blit(name_text, name_rect)

        # Draw cursor if active
        if is_active and int(pygame.time.get_ticks() / 500) % 2 == 0:
            cursor_x = name_rect.right + 2
            pygame.draw.line(self.screen, WHITE,
                           (cursor_x, input_rect.top + 8),
                           (cursor_x, input_rect.bottom - 8), 2)

        self.profile_ui_elements['name_input'] = {'rect': input_rect}

        # --- Player Level Bar (to the right of name input) ---
        from player_level import player_level_manager
        level_progress = player_level_manager.get_progress()
        level_bar_spacing = int(20 * self.ui_scale)
        level_bar_width = int(200 * self.ui_scale)
        level_bar_height = input_height  # Same height as name input
        level_bar_x = input_rect.right + level_bar_spacing
        level_bar_y = input_rect.top

        # "Player Level:" label above the bar
        level_label_text = label_font.render("Player Level:", True, WHITE)
        self.screen.blit(level_label_text, (level_bar_x, content_y))

        # Level bar background (same style as name input)
        level_bar_rect = pygame.Rect(level_bar_x, level_bar_y, level_bar_width, level_bar_height)
        pygame.draw.rect(self.screen, (20, 20, 20), level_bar_rect, border_radius=5)

        # Gold fill based on XP progress within current level
        fill_fraction = level_progress['progress_fraction']
        fill_width = int(level_bar_width * fill_fraction)
        if fill_width > 0:
            # Draw gold fill clipped to rounded rect shape using a temporary surface
            fill_surf = pygame.Surface((level_bar_width, level_bar_height), pygame.SRCALPHA)
            pygame.draw.rect(fill_surf, (184, 134, 11), (0, 0, fill_width, level_bar_height), border_radius=5)
            # Clip right side: if fill doesn't cover full width, mask with the full rounded shape
            if fill_width < level_bar_width:
                mask_surf = pygame.Surface((level_bar_width, level_bar_height), pygame.SRCALPHA)
                pygame.draw.rect(mask_surf, (255, 255, 255, 255), (0, 0, level_bar_width, level_bar_height), border_radius=5)
                fill_surf.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(fill_surf, level_bar_rect.topleft)

        # Border
        pygame.draw.rect(self.screen, (100, 100, 100), level_bar_rect, 2, border_radius=5)

        # Center text: "Level: X"
        level_text_str = f"Level: {level_progress['level']}"
        level_text_surf = label_font.render(level_text_str, True, WHITE)
        level_text_rect = level_text_surf.get_rect(center=level_bar_rect.center)
        self.screen.blit(level_text_surf, level_text_rect)

        # Register level bar for hover detection and tooltip
        self.profile_ui_elements['level_bar'] = {
            'rect': level_bar_rect,
            'tooltip': f"XP: {level_progress['xp_into_level']:,} / {level_progress['xp_for_next']:,}",
        }

        y += input_height + int(15 * self.ui_scale)

        # --- Title Selection Section ---
        title_label = label_font.render("Title:", True, WHITE)
        self.screen.blit(title_label, (content_x, y))
        y += int(30 * self.ui_scale)

        # Title dropdown box
        dropdown_width = int(300 * self.ui_scale)
        dropdown_height = int(32 * self.ui_scale)
        dropdown_rect = pygame.Rect(content_x, y, dropdown_width, dropdown_height)

        # Draw dropdown background (black)
        dd_hovered = (self.hovered_profile_element == 'title_dropdown')
        dd_bg = (30, 30, 30) if dd_hovered or self.title_dropdown_open else (20, 20, 20)
        pygame.draw.rect(self.screen, dd_bg, dropdown_rect, border_radius=5)
        pygame.draw.rect(self.screen, WHITE if self.title_dropdown_open else (100, 100, 100), dropdown_rect, 2, border_radius=5)

        # Dropdown text
        title_display = self.temp_selected_title if self.temp_selected_title else "None"
        dd_text = label_font.render(title_display, True, WHITE)
        dd_text_rect = dd_text.get_rect(midleft=(dropdown_rect.left + 10, dropdown_rect.centery))
        self.screen.blit(dd_text, dd_text_rect)

        # Dropdown arrow
        arrow_x = dropdown_rect.right - int(20 * self.ui_scale)
        arrow_y = dropdown_rect.centery
        arrow_size = int(6 * self.ui_scale)
        if self.title_dropdown_open:
            # Up arrow
            points = [(arrow_x, arrow_y - arrow_size), (arrow_x - arrow_size, arrow_y + arrow_size),
                       (arrow_x + arrow_size, arrow_y + arrow_size)]
        else:
            # Down arrow
            points = [(arrow_x, arrow_y + arrow_size), (arrow_x - arrow_size, arrow_y - arrow_size),
                       (arrow_x + arrow_size, arrow_y - arrow_size)]
        pygame.draw.polygon(self.screen, WHITE, points)

        self.profile_ui_elements['title_dropdown'] = {'rect': dropdown_rect}

        # Store dropdown info for deferred rendering (drawn on top of icons)
        self._title_dropdown_rect = dropdown_rect
        self._title_dropdown_content_x = content_x
        self._title_dropdown_width = dropdown_width

        y += dropdown_height + int(15 * self.ui_scale)

        # Icon Selection Section
        label_text = label_font.render("Choose Icon:", True, WHITE)
        self.screen.blit(label_text, (content_x, y))
        y += int(30 * self.ui_scale)

        # --- Scrollable icon grid (7 per row) ---
        icon_size = int(50 * self.ui_scale)
        icon_spacing = int(8 * self.ui_scale)
        icons_per_row = 7

        # Build ordered reward icon list: unlocked first, then locked
        unlocked_reward_icons = achievement_manager.get_unlocked_reward_icons()
        locked_reward_icons = [p for p in ALL_REWARD_ICON_PATHS if p not in unlocked_reward_icons]
        reward_icon_order = unlocked_reward_icons + locked_reward_icons

        # Total icons: 9 hero (question mark + 8 heroes) + reward icons
        num_hero_icons = 1 + len(self.hero_icons)  # question mark + loaded heroes
        total_icons = num_hero_icons + len(reward_icon_order)

        # Pre-calculate buttons_y so we know where the icon grid must stop
        buttons_y = panel_y + panel_h - padding_bottom - 10

        # Calculate visible area for icon grid (between label and buttons)
        icon_grid_top = y
        icon_grid_bottom = buttons_y - int(10 * self.ui_scale)
        icon_grid_height = icon_grid_bottom - icon_grid_top

        # Total content height
        total_rows = (total_icons + icons_per_row - 1) // icons_per_row
        total_content_height = total_rows * (icon_size + icon_spacing) - icon_spacing

        # Clamp scroll offset
        max_scroll = max(0, total_content_height - icon_grid_height)
        self.icon_scroll_offset = max(0, min(self.icon_scroll_offset, max_scroll))
        self._icon_max_scroll = max_scroll

        # Clip to icon grid area
        clip_rect = pygame.Rect(content_x, icon_grid_top,
                                panel_w - padding_sides * 2, icon_grid_height)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(clip_rect)

        # Deferred tooltip info (drawn after clip is restored)
        deferred_tooltip = None
        small_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', max(11, int(14 * self.ui_scale)))

        for i in range(total_icons):
            row = i // icons_per_row
            col = i % icons_per_row
            icon_x = content_x + col * (icon_size + icon_spacing)
            icon_y = icon_grid_top + row * (icon_size + icon_spacing) - self.icon_scroll_offset
            icon_rect = pygame.Rect(icon_x, icon_y, icon_size, icon_size)

            # Skip icons fully outside visible area
            if icon_y + icon_size < icon_grid_top or icon_y > icon_grid_bottom:
                # Still register UI element for click detection if partially visible
                if i < num_hero_icons:
                    self.profile_ui_elements[f'icon_{i}'] = {'rect': icon_rect}
                else:
                    self.profile_ui_elements[f'reward_icon_{i - num_hero_icons}'] = {'rect': icon_rect}
                continue

            if i < num_hero_icons:
                # --- Hero icons (index 0=question mark, 1-8=heroes) ---
                icon_key = f'icon_{i}'
                is_selected = (self.temp_player_icon == i)
                is_hovered = (self.hovered_profile_element == icon_key)
                is_locked = False
                icon_name = self.hero_icon_names[i] if i < len(self.hero_icon_names) else f"Hero {i}"

                icon_surface = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)

                if i == 0:
                    icon_surface.fill((60, 60, 80))
                    qm_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', int(24 * self.ui_scale))
                    qm_text = qm_font.render("?", True, WHITE)
                    qm_rect = qm_text.get_rect(center=(icon_size // 2, icon_size // 2))
                    icon_surface.blit(qm_text, qm_rect)
                else:
                    hero_index = i - 1
                    if hero_index < len(self.hero_icons_panel_scaled) and self.hero_icons_panel_scaled[hero_index]:
                        scaled = pygame.transform.smoothscale(
                            self.hero_icons_panel_scaled[hero_index], (icon_size, icon_size))
                        icon_surface.blit(scaled, (0, 0))
                    else:
                        icon_surface.fill((100, 100, 100))
            else:
                # --- Reward icons ---
                reward_idx = i - num_hero_icons
                reward_path = reward_icon_order[reward_idx]
                icon_key = f'reward_icon_{reward_idx}'
                is_selected = (self.temp_player_icon == reward_path)
                is_hovered = (self.hovered_profile_element == icon_key)
                is_unlocked_reward, unlock_tooltip = achievement_manager.get_reward_icon_info(reward_path)
                is_locked = not is_unlocked_reward
                icon_name = self.reward_icon_names.get(reward_path, reward_path.split('/')[-1].replace('.png', ''))

                icon_surface = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                scaled_reward = self.reward_icons_panel_scaled.get(reward_path)
                if scaled_reward:
                    resized = pygame.transform.smoothscale(scaled_reward, (icon_size, icon_size))
                    icon_surface.blit(resized, (0, 0))
                else:
                    icon_surface.fill((100, 100, 100))

                if is_locked:
                    icon_surface.fill((80, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)

            # Hover effect (suppress when title dropdown covers this icon)
            if is_hovered and not self.title_dropdown_open:
                light_overlay = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                light_overlay.fill((50, 50, 50, 50))
                icon_surface.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

            self.screen.blit(icon_surface, icon_rect)

            # Border
            if self.icon_border_panel_scaled:
                border_scaled = pygame.transform.smoothscale(
                    self.icon_border_panel_scaled, (icon_size, icon_size))
                if i >= num_hero_icons and is_locked:
                    border_scaled = border_scaled.copy()
                    border_scaled.fill((80, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)
                self.screen.blit(border_scaled, icon_rect)

            # Selection indicator
            if is_selected:
                pygame.draw.rect(self.screen, (255, 215, 0), icon_rect, 3, border_radius=5)

            self.profile_ui_elements[icon_key] = {'rect': icon_rect}

            # Collect tooltip for hover (will be drawn after clip restore)
            # Suppress when title dropdown is open to avoid tooltips showing through it
            if is_hovered and not self.title_dropdown_open:
                if i >= num_hero_icons and is_locked:
                    # Show icon name + unlock source for locked reward icons
                    deferred_tooltip = f"{icon_name}\n{unlock_tooltip}"
                else:
                    deferred_tooltip = icon_name

        # Restore clip
        self.screen.set_clip(old_clip)

        # Draw scroll indicator if icons overflow
        if max_scroll > 0:
            scrollbar_x = content_x + icons_per_row * (icon_size + icon_spacing) + int(4 * self.ui_scale)
            scrollbar_w = int(4 * self.ui_scale)
            visible_ratio = icon_grid_height / total_content_height
            indicator_h = max(int(20 * self.ui_scale), int(icon_grid_height * visible_ratio))
            if max_scroll > 0:
                scroll_ratio = self.icon_scroll_offset / max_scroll
            else:
                scroll_ratio = 0
            indicator_y = icon_grid_top + int((icon_grid_height - indicator_h) * scroll_ratio)
            pygame.draw.rect(self.screen, (60, 60, 80), (scrollbar_x, icon_grid_top, scrollbar_w, icon_grid_height), border_radius=2)
            pygame.draw.rect(self.screen, (150, 150, 170), (scrollbar_x, indicator_y, scrollbar_w, indicator_h), border_radius=2)

        # --- Deferred: Draw title dropdown options on top of icons ---
        if self.title_dropdown_open:
            all_title_options = [None] + list(ALL_TITLES)
            option_height = int(28 * self.ui_scale)
            dropdown_list_y = self._title_dropdown_rect.bottom + 2

            # Limit visible area to TITLE_DROPDOWN_VISIBLE items with scrolling
            total_options = len(all_title_options)
            visible_count = min(total_options, self.TITLE_DROPDOWN_VISIBLE)
            visible_height = visible_count * option_height
            max_dd_scroll = max(0, total_options - visible_count)
            self.title_dropdown_scroll = max(0, min(self.title_dropdown_scroll, max_dd_scroll))
            self._title_dropdown_max_scroll = max_dd_scroll

            # Store dropdown list rect for scroll hit-testing
            self._title_dropdown_list_rect = pygame.Rect(
                self._title_dropdown_content_x, dropdown_list_y,
                self._title_dropdown_width, visible_height)

            # Background
            list_bg = pygame.Surface((self._title_dropdown_width, visible_height), pygame.SRCALPHA)
            list_bg.fill((20, 20, 20, 240))
            self.screen.blit(list_bg, (self._title_dropdown_content_x, dropdown_list_y))

            # Clip to visible dropdown area
            old_dd_clip = self.screen.get_clip()
            self.screen.set_clip(self._title_dropdown_list_rect)

            small_dd_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', max(12, int(18 * self.ui_scale)))

            for idx, title_opt in enumerate(all_title_options):
                # Offset by scroll position
                visual_y = dropdown_list_y + (idx - self.title_dropdown_scroll) * option_height
                opt_rect = pygame.Rect(self._title_dropdown_content_x, visual_y,
                                       self._title_dropdown_width, option_height)
                opt_key = f'title_option_{idx}'
                is_opt_hovered = (self.hovered_profile_element == opt_key)

                if title_opt is None:
                    display_text = "None"
                    is_locked_title = False
                else:
                    display_text = title_opt
                    is_unlocked_t, _ = achievement_manager.get_title_info(title_opt)
                    is_locked_title = not is_unlocked_t

                if is_opt_hovered and not is_locked_title:
                    hover_bg = pygame.Surface((self._title_dropdown_width, option_height), pygame.SRCALPHA)
                    hover_bg.fill((80, 80, 120, 150))
                    self.screen.blit(hover_bg, opt_rect)

                text_color = (100, 100, 100) if is_locked_title else WHITE
                opt_text = small_dd_font.render(display_text, True, text_color)
                opt_text_rect = opt_text.get_rect(midleft=(opt_rect.left + 10, opt_rect.centery))
                self.screen.blit(opt_text, opt_text_rect)

                if is_locked_title:
                    lock_text = small_dd_font.render("[Locked]", True, (100, 100, 100))
                    self.screen.blit(lock_text, (opt_rect.right - lock_text.get_width() - int(8 * self.ui_scale), opt_text_rect.y))

                if is_opt_hovered and is_locked_title and title_opt:
                    _, dd_tooltip = achievement_manager.get_title_info(title_opt)
                    deferred_tooltip = dd_tooltip

                self.profile_ui_elements[opt_key] = {'rect': opt_rect, 'locked': is_locked_title}

            # Restore clip
            self.screen.set_clip(old_dd_clip)

            # Border around visible dropdown area
            pygame.draw.rect(self.screen, (100, 100, 100), self._title_dropdown_list_rect, 1)

            # Scroll indicator arrows if there are more options than visible
            if max_dd_scroll > 0:
                arrow_color = (180, 180, 180)
                arrow_x = self._title_dropdown_content_x + self._title_dropdown_width - int(12 * self.ui_scale)
                if self.title_dropdown_scroll > 0:
                    # Up arrow
                    ay = dropdown_list_y + int(6 * self.ui_scale)
                    pygame.draw.polygon(self.screen, arrow_color,
                                        [(arrow_x, ay + 6), (arrow_x - 5, ay + 12), (arrow_x + 5, ay + 12)])
                if self.title_dropdown_scroll < max_dd_scroll:
                    # Down arrow
                    ay = dropdown_list_y + visible_height - int(6 * self.ui_scale)
                    pygame.draw.polygon(self.screen, arrow_color,
                                        [(arrow_x, ay - 6), (arrow_x - 5, ay - 12), (arrow_x + 5, ay - 12)])

        # --- Deferred: Draw tooltip on top of everything ---
        # Check level bar hover for tooltip (not inside icon grid clip region)
        if not deferred_tooltip and self.hovered_profile_element == 'level_bar':
            level_bar_data = self.profile_ui_elements.get('level_bar')
            if level_bar_data and 'tooltip' in level_bar_data:
                deferred_tooltip = level_bar_data['tooltip']
        if deferred_tooltip:
            self._draw_tooltip(self.screen, deferred_tooltip, pygame.mouse.get_pos(), small_font)

        # Cancel and Save buttons at bottom (buttons_y pre-calculated above for icon grid)
        button_width = int(150 * self.ui_scale)
        button_height = int(50 * self.ui_scale)
        button_spacing = int(20 * self.ui_scale)
        total_buttons_width = button_width * 2 + button_spacing
        buttons_start_x = panel_x + (panel_w - total_buttons_width) // 2

        # Cancel button
        cancel_rect = pygame.Rect(buttons_start_x, buttons_y, button_width, button_height)
        is_hovered = (self.hovered_profile_element == 'cancel_button')
        cancel_bg = lighten_color((120, 50, 50), 0.2) if is_hovered else (120, 50, 50)
        pygame.draw.rect(self.screen, cancel_bg, cancel_rect, border_radius=8)
        pygame.draw.rect(self.screen, (150, 150, 150), cancel_rect, 2, border_radius=8)

        cancel_text = self.button_font.render("Cancel", True, WHITE)
        cancel_text_rect = cancel_text.get_rect(center=cancel_rect.center)
        self.screen.blit(cancel_text, cancel_text_rect)

        self.profile_ui_elements['cancel_button'] = {'rect': cancel_rect}

        # Save button
        save_rect = pygame.Rect(buttons_start_x + button_width + button_spacing, buttons_y,
                                button_width, button_height)
        is_hovered = (self.hovered_profile_element == 'save_button')
        save_bg = lighten_color((50, 180, 50), 0.2) if is_hovered else (50, 180, 50)
        pygame.draw.rect(self.screen, save_bg, save_rect, border_radius=8)
        pygame.draw.rect(self.screen, (150, 150, 150), save_rect, 2, border_radius=8)

        save_text = self.button_font.render("Save", True, WHITE)
        save_text_rect = save_text.get_rect(center=save_rect.center)
        self.screen.blit(save_text, save_text_rect)

        self.profile_ui_elements['save_button'] = {'rect': save_rect}
