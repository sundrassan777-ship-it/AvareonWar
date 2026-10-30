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
from config.constants import (WHITE, BLACK, GRAY, DARK_GRAY, GAME_VERSION, OPEN_BETA,
                              MAP_3D_AVAILABLE, CAMERA_ZOOM_SPEED)
import wishlist  # OPEN BETA ONLY: the Wishlist button (remove at full release)
from utils.colors import lighten_color, brighten_color
from settings_manager import settings
from global_sound import sound_manager  # Global sound manager for UI clicks
from achievement_manager import ALL_REWARD_ICON_PATHS
from achievement_panel import AchievementPanel
from steam_integration import steam_manager
from utils.logger import get_logger
from utils.cursor import draw_custom_cursor
from display_utils import menu_frame_cap
from ui.menu_kit import MenuKit, WindowStage
from ui.options_panel import OptionsPanel
from ui.profile_panel import ProfilePanel

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

    # The hero portraits a player can pick (assets/heroes/; player_icon 1-8 in this order,
    # 0 = the default "?") - the corner Profile button and the Profile window
    HERO_ICON_FILES = ('asford.png', 'asten.png', 'brennhen.png', 'hevilneu.png', 'narn.png',
                       'nextroy.png', 'rennervail.png', 'silvyr.png')

    def __init__(self, screen):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()

        # Music end event constant for forwarding to music manager
        from music_manager import MUSIC_END_EVENT
        self._music_end_event = MUSIC_END_EVENT

        # P8 fix: font cache to avoid per-frame pygame.font.Font() filesystem I/O
        self._font_cache = {}

        # Scale factor for UI elements based on screen height
        self.ui_scale = min(1.0, self.height / 900.0)

        # The look shared by the menu's windows (ui/menu_kit.py: bronze window, dimmed
        # menu behind). The Options window (self.options_panel) is made below, once the
        # pending settings and resolutions it edits exist.
        self.menu_kit = MenuKit((self.width, self.height))
        self.window_stage = WindowStage(self.menu_kit)   # Draws a window over the dimmed menu
        # Profile -> View -> Achievements: the Profile comes back as it was left when the
        # Achievements window closes; a window opened once the one before has faded out
        self._return_to_profile = False
        self._queued_open = None

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
        # Connect string of a friend's game chosen in Steam (result 'steam_invite_join')
        self.steam_join_target = None

        # Temporary settings (not saved until Apply is clicked)
        self.temp_resolution = settings.get_resolution()
        self.temp_fullscreen = settings.is_fullscreen()
        self.temp_vsync = settings.get('vsync', False)
        self.temp_fps_limit = settings.get('fps_limit', 0)
        self.temp_edge_scrolling_enabled = settings.get('edge_scrolling_enabled', True)
        self.temp_tooltips_enabled = settings.get('tooltips_enabled', True)
        self.temp_show_fps = settings.get('show_fps', False)
        # 3D map look (map_data.map_look): a row only while MAP_3D_AVAILABLE
        self.temp_map_3d = settings.get('map_style', '2d') == '3d'
        self.temp_edge_scrolling_mode = settings.get('edge_scrolling_mode', 'window_edge')
        self.temp_tooltip_delay_ms = settings.get('tooltip_delay_ms', 500)
        self.temp_pan_speed = settings.get('camera_pan_speed', 10.0)
        self.temp_zoom_speed = settings.get('camera_zoom_speed', CAMERA_ZOOM_SPEED)
        # Audio volume temp settings
        self.temp_master_volume = settings.get('master_volume', 0.8)
        self.temp_music_volume = settings.get('music_volume', 0.5)
        self.temp_sfx_volume = settings.get('sfx_volume', 0.5)

        # Available resolutions
        self.available_resolutions = [
            (1280, 720),
            (1600, 900),
            (1920, 1080)
        ]

        # The Options window: tabs of settings over the temp_* values above
        # (ui/options_panel.py; Apply / Cancel / Reset to Defaults stay here)
        self.options_panel = OptionsPanel(self, self.menu_kit)
        self.options_panel.prewarm()

        # Temporary profile settings (not saved until Save is clicked)
        self.temp_player_name = settings.get_player_name()
        self.temp_player_icon = settings.get_player_icon()
        self.temp_selected_title = settings.get_selected_title()
        self._steam_name_active = False  # True when name is from Steam (non-editable)

        # The Achievements window - the trophy wall (achievement_panel.py, the menu kit)
        self.achievements_panel = AchievementPanel(self, self.menu_kit)
        self.achievements_panel.prewarm()

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

        # The Profile window - the player card (ui/profile_panel.py, the menu kit), over
        # the temp_player_* values above; it uses the icon names just above
        self.profile_panel = ProfilePanel(self, self.menu_kit)
        self.profile_panel.prewarm()

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

        # Load custom menu button background
        try:
            button_bg = pygame.image.load('assets/MainMenuButtonNew.png').convert_alpha()
            # We'll scale this per button in _draw_button based on button dimensions
            self.button_bg_image = button_bg
        except Exception as e:
            logger.warning(f"Error loading menu button background: {e}")
            self.button_bg_image = None

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
        for hero_file in self.HERO_ICON_FILES:
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

        # Load replays button icon (bottom-left corner)
        self.replays_button_icon = None
        try:
            replays_icon = pygame.image.load('assets/ReplaysIcon.png').convert_alpha()
            self.replays_button_icon = replays_icon  # Will be pre-scaled in _calculate_layout
        except Exception as e:
            logger.warning(f"Error loading replays icon: {e}")

        # OPEN BETA ONLY (wishlist.py - remove at full release): the Wishlist button icon
        # (bottom-left corner), the owner's art; None (it failed to load) = a drawn tile.
        self.wishlist_button_icon = None
        if OPEN_BETA:
            try:
                self.wishlist_button_icon = pygame.image.load(wishlist.WISHLIST_ICON_PATH).convert_alpha()
            except (pygame.error, FileNotFoundError) as e:
                logger.info(f"Wishlist icon not there yet ({e}); drawing a fallback tile")

        # Load reward icons for profile (will be pre-scaled in _calculate_layout)
        self.reward_icons_raw = {}
        for icon_path in ALL_REWARD_ICON_PATHS:
            try:
                self.reward_icons_raw[icon_path] = pygame.image.load(icon_path).convert_alpha()
            except Exception as e:
                logger.warning(f"Could not load reward icon {icon_path}: {e}")
                self.reward_icons_raw[icon_path] = None

        # Pre-scaled versions for the profile button (created in _calculate_layout); the
        # Profile window has its own (ui/profile_panel.py, through the menu kit)
        self.hero_icons_button_scaled = []  # For profile button
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

        # Pre-scale hero icons for profile button
        self.hero_icons_button_scaled = []
        for hero_icon in self.hero_icons:
            if hero_icon:
                scaled = pygame.transform.smoothscale(hero_icon, (profile_button_size, profile_button_size))
                self.hero_icons_button_scaled.append(scaled)
            else:
                self.hero_icons_button_scaled.append(None)

        # Pre-scale icon borders (2px larger than icon = 1px per side to fully contain icon edges)
        if self.icon_border:
            self.icon_border_button_scaled = pygame.transform.smoothscale(
                self.icon_border, (profile_button_size + 2, profile_button_size + 2)
            )
        else:
            self.icon_border_button_scaled = None

        # Pre-scale achievement button icon
        if self.achievement_button_icon:
            self.achievement_button_icon_scaled = pygame.transform.smoothscale(
                self.achievement_button_icon, (profile_button_size, profile_button_size)
            )
        else:
            self.achievement_button_icon_scaled = None

        # Replays button in bottom-right corner (same size as profile/achievement buttons)
        self.replays_button_rect = pygame.Rect(
            self.width - profile_button_size - profile_button_margin,
            self.height - profile_button_size - profile_button_margin,
            profile_button_size,
            profile_button_size
        )

        # Pre-scale replays button icon
        if self.replays_button_icon:
            self.replays_button_icon_scaled = pygame.transform.smoothscale(
                self.replays_button_icon, (profile_button_size, profile_button_size)
            )
        else:
            self.replays_button_icon_scaled = None

        # OPEN BETA ONLY (remove at full release): Wishlist button in the bottom-left
        # corner (the only free corner), one version-text line above the version label
        self.wishlist_button_rect = None
        self.wishlist_button_icon_scaled = None
        self.wishlist_glow = None
        if OPEN_BETA:
            self.wishlist_button_rect = pygame.Rect(
                profile_button_margin,
                self.height - profile_button_size - profile_button_margin - self.tooltip_font.get_linesize(),
                profile_button_size,
                profile_button_size
            )
            if self.wishlist_button_icon:
                self.wishlist_button_icon_scaled = pygame.transform.smoothscale(
                    self.wishlist_button_icon, (profile_button_size, profile_button_size))
            # The navy glow round it, idle and hovered (baked once per size)
            self.wishlist_glow = {
                hovered: self._wishlist_glow(profile_button_size, alpha)
                for hovered, alpha in ((False, wishlist.WISHLIST_GLOW_ALPHA),
                                       (True, wishlist.WISHLIST_GLOW_ALPHA_HOVER))}

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
            dt = self.clock.tick(menu_frame_cap()) / 1000.0

            # Animate options panel
            self._update_options_animation(dt)

            self.handle_events()
            self.render()
            draw_custom_cursor(self.screen)

            # Process Steam callbacks in menu (overlay popups, persona updates)
            steam_manager.run_callbacks()

            # A friend's game chosen in Steam (invite accepted / "Join Game" on a friend
            # - now, or earlier during a game): join it, as main.py does for an invite
            # that started the game
            if self.result is None:
                join = steam_manager.take_join_request()
                if join is not None:
                    self.steam_join_target = join.connect
                    self.result = 'steam_invite_join'

            pygame.display.flip()

        return self.result

    def _update_options_animation(self, dt):
        """Animate the windows opening / closing (an eased drop + fade); open a window that
        waited for the one before to fade out (Profile <-> Achievements through View)"""
        for window in self._windows():
            window.update(dt)
        if self._queued_open is not None and not any(w.anim.visible for w in self._windows()):
            open_next, self._queued_open = self._queued_open, None
            open_next()

    def handle_events(self):
        """Process events"""
        mouse_pos = pygame.mouse.get_pos()

        # Update hover state
        if self.show_achievements:
            # The Achievements window lights the chip / medal / button under the mouse
            self.achievements_panel.update_hover(mouse_pos)
        elif self.show_profile:
            # The Profile window lights the title / portrait / button under the mouse
            self.profile_panel.update_hover(mouse_pos)
        elif self.show_options:
            # The Options window lights the control under the mouse
            self.options_panel.update_hover(mouse_pos)
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

            # Check replays button hover (bottom-left)
            if self.replays_button_rect.collidepoint(mouse_pos):
                self.hovered_button = 'replays'

            # OPEN BETA ONLY: Wishlist button hover (bottom-left)
            if self.wishlist_button_rect and self.wishlist_button_rect.collidepoint(mouse_pos):
                self.hovered_button = 'wishlist'

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.result = 'quit'

            # Music track ended — advance to next track
            elif event.type == self._music_end_event:
                from music_manager import music_manager
                music_manager.handle_music_end_event()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # If any panel is open, close it; otherwise quit
                    if self.show_achievements:
                        # A search is cleared first; Esc again closes the window
                        if not self.achievements_panel.handle_escape():
                            self._close_achievements()
                    elif self.show_profile:
                        # Typing the name: Esc stops the typing; else it cancels
                        if not self.profile_panel.handle_escape():
                            self._close_profile()
                    elif self.show_options:
                        self._close_options()
                    else:
                        self.result = 'quit'

                # Options window: Enter applies (as the Apply button), Tab steps the tabs
                elif self.show_options:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        sound_manager.play_ui_click()
                        self._apply_options()
                        self._close_options()
                    else:
                        self.options_panel.handle_key(event)

                # Achievements: typing searches (from anywhere in the window)
                elif self.show_achievements:
                    self.achievements_panel.handle_key(event)

                # Profile: typing the name; Enter saves (or ends the typing)
                elif self.show_profile:
                    if self.profile_panel.handle_key(event) == 'save':
                        sound_manager.play_ui_click()
                        self._save_profile()
                        self._close_profile()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self.handle_click(mouse_pos)
                elif event.button in (4, 5) and self.show_achievements:
                    # Mouse wheel scrolls the trophy wall
                    self.achievements_panel.wheel(1 if event.button == 4 else -1)
            elif event.type == pygame.MOUSEMOTION:
                # A held Options slider follows the mouse (volumes preview live)
                if self.show_options and self.options_panel.dragging:
                    self.options_panel.drag_to(event.pos)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    # Release slider drag
                    self.options_panel.release()

    def handle_click(self, pos):
        """Handle button clicks"""
        # Achievements window: chips, search, medals; Close comes back as an action
        if self.show_achievements:
            if self.achievements_panel.handle_click(pos) == 'close':
                self._close_achievements()
            return

        # Profile window: titles, portraits, the name; Save / Cancel / View come back as actions
        if self.show_profile:
            action = self.profile_panel.handle_click(pos)
            if action == 'save':
                self._save_profile()
                self._close_profile()
            elif action == 'cancel':
                self._close_profile()
            elif action == 'view':
                self._view_achievements_from_profile()
            return

        # Options window: its own controls; Apply / Cancel / Reset come back as actions
        if self.show_options:
            action = self.options_panel.handle_click(pos)
            if action == 'apply':
                self._apply_options()
                self._close_options()
            elif action == 'cancel':
                self._close_options()
            elif action == 'reset':
                self._reset_to_defaults()
            return

        # OPEN BETA ONLY: the Wishlist button opens the full game's store page (overlay,
        # else the Steam client, else the browser - wishlist.open_wishlist_page)
        if self.wishlist_button_rect and self.wishlist_button_rect.collidepoint(pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'wishlist'
            wishlist.open_wishlist_page()
            return

        # Handle replays button click (bottom-left)
        if self.replays_button_rect.collidepoint(pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'replays'
            self.result = 'replays'
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
        """Open the Options window with the saved settings as its pending values"""
        self._end_window_fades(self.options_panel)
        self.show_options = True
        self.hovered_button = None   # The menu behind dims as it is (no lit Options button)
        # Reset temporary settings to current settings
        self.temp_resolution = settings.get_resolution()
        self.temp_fullscreen = settings.is_fullscreen()
        self.temp_vsync = settings.get('vsync', False)
        self.temp_fps_limit = settings.get('fps_limit', 0)
        self.temp_edge_scrolling_enabled = settings.get('edge_scrolling_enabled', True)
        self.temp_tooltips_enabled = settings.get('tooltips_enabled', True)
        self.temp_show_fps = settings.get('show_fps', False)
        self.temp_map_3d = settings.get('map_style', '2d') == '3d'
        self.temp_edge_scrolling_mode = settings.get('edge_scrolling_mode', 'window_edge')
        self.temp_tooltip_delay_ms = settings.get('tooltip_delay_ms', 500)
        self.temp_pan_speed = settings.get('camera_pan_speed', 10.0)
        self.temp_zoom_speed = settings.get('camera_zoom_speed', CAMERA_ZOOM_SPEED)
        self.temp_master_volume = settings.get('master_volume', 0.8)
        self.temp_music_volume = settings.get('music_volume', 0.5)
        self.temp_sfx_volume = settings.get('sfx_volume', 0.5)
        self.options_panel.open()

    def _close_options(self):
        """Close the Options window — revert audio volumes to saved values"""
        self.show_options = False
        self.options_panel.close()
        # Revert audio volumes to saved values (undo live preview)
        self.temp_master_volume = settings.get('master_volume', 0.8)
        self.temp_music_volume = settings.get('music_volume', 0.5)
        self.temp_sfx_volume = settings.get('sfx_volume', 0.5)
        self._preview_audio()

    def _preview_audio(self):
        """Play music and sounds at the pending volumes (the volume sliders' live preview)"""
        from music_manager import music_manager as _mm
        _mm.set_master_volume(self.temp_master_volume)
        _mm.set_music_volume(self.temp_music_volume)
        sound_manager.set_volume(self.temp_sfx_volume * self.temp_master_volume)

    def _open_profile(self, keep=False):
        """Open the Profile window. keep=True: with the choices as they were left (back
        from the Achievements window it opened with View), not re-read from the settings."""
        self._end_window_fades(self.profile_panel)
        self.show_profile = True
        self.hovered_button = None   # The menu behind dims as it is
        if not keep:
            # Reset temporary settings to current settings
            # If Steam is available, use Steam persona name (non-editable)
            if steam_manager.is_available:
                steam_name = steam_manager.get_player_name()
                if steam_name:
                    self.temp_player_name = steam_name
                    self._steam_name_active = True
                else:
                    self.temp_player_name = settings.get_player_name()
                    self._steam_name_active = False
            else:
                self.temp_player_name = settings.get_player_name()
                self._steam_name_active = False
            self.temp_player_icon = settings.get_player_icon()
            self.temp_selected_title = settings.get_selected_title()
        self.profile_panel.open()

    def _close_profile(self):
        """Close the Profile window (Cancel: the choices are dropped on the next opening)"""
        self.show_profile = False
        self.profile_panel.close()

    def _view_achievements_from_profile(self):
        """Profile -> View: the card leaves (its choices kept), the Achievements window opens
        once it has; closing that brings the card back as it was."""
        self.show_profile = False
        self.profile_panel.close()
        self._return_to_profile = True
        self._queued_open = self._open_achievements

    def _save_profile(self):
        """Save current profile settings to global settings"""
        settings.set_player_name(self.temp_player_name)
        settings.set_player_icon(self.temp_player_icon)
        settings.set_selected_title(self.temp_selected_title)
        settings.save()
        logger.info(f"Profile saved: {self.temp_player_name}, Icon: {self.temp_player_icon}, Title: {self.temp_selected_title}")

    def _open_achievements(self):
        """Open the Achievements window (fresh: All, no search, the latest achievements)"""
        self._end_window_fades(self.achievements_panel)
        self.show_achievements = True
        self.hovered_button = None   # The menu behind dims as it is
        self.achievements_panel.open()

    def _close_achievements(self):
        """Close the Achievements window (back to the Profile card when it came from there)"""
        self.show_achievements = False
        self.achievements_panel.close()
        if self._return_to_profile:
            self._return_to_profile = False
            self._queued_open = lambda: self._open_profile(keep=True)

    def _windows(self):
        """The windows drawn with the menu kit over the dimmed menu (WindowStage)."""
        return (self.options_panel, self.achievements_panel, self.profile_panel)

    def _end_window_fades(self, opening=None):
        """A window opening while another still fades out: that one ends at once (the
        stage shows one window at a time). The window being opened itself just turns
        round (WindowAnim reverses from where it is)."""
        for window in self._windows():
            if window is not opening and window.anim.visible and not window.anim.opening:
                window.anim.finish()
                self.window_stage.reset()

    def _apply_options(self):
        """Apply current temporary settings to global settings"""
        # Check if display settings changed
        old_resolution = settings.get_resolution()
        old_fullscreen = settings.is_fullscreen()
        old_vsync = settings.get('vsync', False)

        settings.set_resolution(self.temp_resolution[0], self.temp_resolution[1])
        settings.set_fullscreen(self.temp_fullscreen)
        settings.set('vsync', self.temp_vsync)
        settings.set('fps_limit', self.temp_fps_limit)
        settings.set('edge_scrolling_enabled', self.temp_edge_scrolling_enabled)
        settings.set('tooltips_enabled', self.temp_tooltips_enabled)
        settings.set('show_fps', self.temp_show_fps)
        if MAP_3D_AVAILABLE:   # locked: the saved look stays as it is (and is not read)
            settings.set('map_style', '3d' if self.temp_map_3d else '2d')
        settings.set('edge_scrolling_mode', self.temp_edge_scrolling_mode)
        settings.set('tooltip_delay_ms', self.temp_tooltip_delay_ms)
        settings.set('camera_pan_speed', self.temp_pan_speed)
        settings.set('camera_zoom_speed', self.temp_zoom_speed)
        # Audio settings
        settings.set('master_volume', self.temp_master_volume)
        settings.set('music_volume', self.temp_music_volume)
        settings.set('sfx_volume', self.temp_sfx_volume)
        # Apply audio volumes (already previewing live, but persist the final values)
        from music_manager import music_manager as _mm
        _mm.set_master_volume(self.temp_master_volume)
        _mm.set_music_volume(self.temp_music_volume)
        sound_manager.set_volume(self.temp_sfx_volume * self.temp_master_volume)

        settings.save()
        logger.info("Settings applied and saved")

        # If display settings changed, trigger window recreation
        # VSync is included: it requires pygame.SCALED and a fresh display, so it
        # cannot be toggled on the existing surface.
        if (old_resolution != self.temp_resolution or old_fullscreen != self.temp_fullscreen
                or old_vsync != self.temp_vsync):
            logger.info("Display settings changed - recreating window...")
            self.result = 'recreate_window'

    def _reset_to_defaults(self):
        """Reset all temp settings to default values (must click Apply to save)"""
        # Get default resolution from settings (intelligently chosen from supported resolutions)
        default_resolution = settings.get_default_resolution()

        # Reset all temp settings to the settings manager's own defaults (one source:
        # this used to keep a hand-written copy of them)
        defaults = settings.defaults
        self.temp_resolution = default_resolution
        self.temp_fullscreen = defaults['fullscreen']
        self.temp_vsync = defaults['vsync']
        self.temp_fps_limit = defaults['fps_limit']
        self.temp_edge_scrolling_enabled = defaults['edge_scrolling_enabled']
        self.temp_tooltips_enabled = defaults['tooltips_enabled']
        self.temp_show_fps = defaults['show_fps']
        self.temp_map_3d = defaults['map_style'] == '3d'
        self.temp_edge_scrolling_mode = defaults['edge_scrolling_mode']
        self.temp_tooltip_delay_ms = defaults['tooltip_delay_ms']
        self.temp_pan_speed = defaults['camera_pan_speed']
        self.temp_zoom_speed = defaults['camera_zoom_speed']
        # Audio volume defaults
        self.temp_master_volume = defaults['master_volume']
        self.temp_music_volume = defaults['music_volume']
        self.temp_sfx_volume = defaults['sfx_volume']
        # Live preview the reset
        self._preview_audio()

        logger.info(f"Settings reset to defaults: {default_resolution[0]}x{default_resolution[1]} (click Apply to save)")

    def render(self):
        """Render main menu, with the Options / Achievements / Profile window over it while one is open"""
        window = next((w for w in self._windows() if w.anim.visible), None)
        if window is not None:
            # The menu dims as the window drops in (WindowStage: the menu is captured once,
            # the window's fixed parts baked in, so a frame is mostly one opaque blit)
            self.window_stage.draw(self.screen, window, self._render_menu)
        else:
            self.window_stage.reset()
            self._render_menu()

        # Reset clicked state after render
        self.clicked_button = None

    def _render_menu(self):
        """The menu itself: background, logo, buttons (the windows are drawn over it)"""
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

        # Draw replays button in bottom left corner
        self._draw_replays_button()

        # OPEN BETA ONLY: Wishlist button (bottom-left corner)
        if self.wishlist_button_rect:
            self._draw_wishlist_button()

        # Draw tooltips for profile/achievement buttons when no panel is open
        if not self.show_profile and not self.show_achievements and not self.show_options:
            if self.hovered_button == 'profile':
                self._draw_tooltip(self.screen, "Profile", pygame.mouse.get_pos(), self.tooltip_font)
            elif self.hovered_button == 'achievements':
                self._draw_tooltip(self.screen, "Achievements", pygame.mouse.get_pos(), self.tooltip_font)
            elif self.hovered_button == 'replays':
                self._draw_tooltip(self.screen, "Replays", pygame.mouse.get_pos(), self.tooltip_font)
            elif self.hovered_button == 'wishlist':
                self._draw_tooltip(self.screen, wishlist.WISHLIST_TOOLTIP, pygame.mouse.get_pos(),
                                   self.tooltip_font)

        # Draw version label in bottom-left corner
        version_text = self.tooltip_font.render(f"Version: {GAME_VERSION}", True, GRAY)
        self.screen.blit(version_text, (10, self.height - version_text.get_height() - 10))


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

        # Draw border frame overlay using pre-scaled version (offset -1 to center enlarged border)
        if self.icon_border_button_scaled:
            self.screen.blit(self.icon_border_button_scaled, (rect.x - 1, rect.y - 1))

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

        # Draw border frame overlay (offset -1 to center enlarged border)
        if self.icon_border_button_scaled:
            self.screen.blit(self.icon_border_button_scaled, (rect.x - 1, rect.y - 1))

    def _draw_replays_button(self):
        """Draw replays button in bottom-left corner with icon and border"""
        rect = self.replays_button_rect

        is_hovered = (self.hovered_button == 'replays')
        is_clicked = (self.clicked_button == 'replays')

        # Draw icon background
        icon_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

        if self.replays_button_icon_scaled:
            icon_surface.blit(self.replays_button_icon_scaled, (0, 0))
        else:
            # Fallback: dark background with play symbol
            icon_surface.fill((60, 60, 80))
            play_font = self._get_cached_font('assets/fonts/Cinzel-Regular.ttf', 30)
            play_text = play_font.render("▶", True, WHITE)
            play_rect = play_text.get_rect(center=(rect.width // 2, rect.height // 2))
            icon_surface.blit(play_text, play_rect)

        # Apply hover/click effects (same as achievement/profile buttons)
        if is_clicked:
            bright_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bright_overlay.fill((100, 100, 100, 100))
            icon_surface.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif is_hovered:
            light_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            light_overlay.fill((50, 50, 50, 50))
            icon_surface.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.screen.blit(icon_surface, rect)

        # Draw border frame overlay (offset -1 to center enlarged border)
        if self.icon_border_button_scaled:
            self.screen.blit(self.icon_border_button_scaled, (rect.x - 1, rect.y - 1))

    @staticmethod
    def _wishlist_glow(size, alpha):
        """OPEN BETA ONLY: a soft navy halo round a size x size button, alpha `alpha`
        at its edge fading to nothing over the reach, with rounded corners. Returns
        (surface, reach): blit it at the button's top-left minus (reach, reach)."""
        reach = max(5, int(round(size * wishlist.WISHLIST_GLOW_REACH)))
        glow = pygame.Surface((size + 2 * reach, size + 2 * reach), pygame.SRCALPHA)
        r, g, b = wishlist.WISHLIST_GLOW_COLOUR
        # Outermost ring first; each nearer one is drawn over it (pygame.draw writes
        # the alpha, it doesn't blend), the middle is covered by the icon
        for d in range(reach, 0, -1):
            a = int(alpha * (1.0 - (d - 1) / float(reach)) ** 1.6)
            pygame.draw.rect(glow, (r, g, b, a), pygame.Rect(reach - d, reach - d, size + 2 * d, size + 2 * d),
                             border_radius=d + 2)
        return glow, reach

    def _draw_wishlist_button(self):
        """OPEN BETA ONLY (remove at full release): the Wishlist button in the bottom-left
        corner - the owner's icon (wishlist.WISHLIST_ICON_PATH), or if it fails to load a
        Steam-blue tile with a heart. Hover / click like the other corner buttons."""
        rect = self.wishlist_button_rect
        is_hovered = (self.hovered_button == 'wishlist')
        is_clicked = (self.clicked_button == 'wishlist')

        # The navy glow round it, a little stronger while hovered
        glow, reach = self.wishlist_glow[is_hovered or is_clicked]
        self.screen.blit(glow, (rect.x - reach, rect.y - reach))

        icon_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        if self.wishlist_button_icon_scaled:
            icon_surface.blit(self.wishlist_button_icon_scaled, (0, 0))
        else:
            # Fallback: Steam's dark blue with a light blue heart, drawn (no font glyph needed)
            icon_surface.fill((27, 40, 56))
            w, h = rect.width, rect.height
            r = max(4, w // 7)
            cy = int(h * 0.42)
            heart = (102, 192, 244)
            pygame.draw.circle(icon_surface, heart, (w // 2 - r + 1, cy), r)
            pygame.draw.circle(icon_surface, heart, (w // 2 + r - 1, cy), r)
            pygame.draw.polygon(icon_surface, heart, [
                (w // 2 - 2 * r + 1, cy + r // 3), (w // 2 + 2 * r - 1, cy + r // 3),
                (w // 2, cy + int(2.2 * r))])

        # Same hover / click effects as the other corner buttons
        if is_clicked:
            bright_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bright_overlay.fill((100, 100, 100, 100))
            icon_surface.blit(bright_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif is_hovered:
            light_overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            light_overlay.fill((50, 50, 50, 50))
            icon_surface.blit(light_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.screen.blit(icon_surface, rect)
        if self.icon_border_button_scaled:
            self.screen.blit(self.icon_border_button_scaled, (rect.x - 1, rect.y - 1))

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
