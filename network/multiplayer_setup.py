"""
Multiplayer setup UI for hosting and joining games.

Handles connection establishment and territory selection for multiplayer mode.
Expanded for 2-4 players with AI support and alliance system.
"""

import pygame
import socket
import time
from typing import Optional, Tuple, Dict, List

from network.server import NetworkServer
from network.client import NetworkClient
from network.protocol import NetworkProtocol
from network.lobby import LobbyState, LobbySlot, SLOT_EMPTY, SLOT_HUMAN, SLOT_AI
from network_config import MessageType
import map_data
from network.territory_selector import TerritorySelector  # Updated import path
from global_sound import sound_manager  # Global sound manager for UI clicks
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.logger import get_logger
from utils.cursor import draw_custom_cursor

logger = get_logger(__name__)


# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (64, 64, 64)
GREEN = (0, 200, 0)
RED = (200, 0, 0)
BLUE = (100, 150, 255)
BRASS_COLOR = (181, 166, 66)


class MultiplayerSetup:
    """
    Multiplayer setup screen.

    Handles host/join selection, connection, and initial setup.
    """

    def __init__(self, screen):
        """
        Initialize multiplayer setup.

        Args:
            screen: Pygame screen surface
        """
        self.screen = screen
        self.width, self.height = screen.get_size()

        # Load fonts with Cinzel (matching main menu style), fallback to default
        try:
            regular_path = "assets/fonts/Cinzel-Regular.ttf"
            semibold_path = "assets/fonts/Cinzel-SemiBold.ttf"
            self.title_font = pygame.font.Font(semibold_path, 48)
            self.subtitle_font = pygame.font.Font(semibold_path, 36)
            self.button_font = pygame.font.Font(regular_path, 29)
            self.text_font = pygame.font.Font(regular_path, 28)
            self.small_font = pygame.font.Font(regular_path, 20)
        except (FileNotFoundError, pygame.error, OSError):
            self.title_font = pygame.font.Font(None, 72)
            self.subtitle_font = pygame.font.Font(None, 48)
            self.button_font = pygame.font.Font(None, 36)
            self.text_font = pygame.font.Font(None, 32)
            self.small_font = pygame.font.Font(None, 24)

        # Load assets
        try:
            bg_original = pygame.image.load('assets/MPSetBG.png').convert()
            self.background_image = pygame.transform.smoothscale(bg_original, (self.width, self.height))
        except (FileNotFoundError, pygame.error, OSError):
            self.background_image = None

        try:
            self.button_bg_image = pygame.image.load('assets/MainMenuButtonNew.png').convert_alpha()
        except (FileNotFoundError, pygame.error, OSError):
            self.button_bg_image = None

        # Load options menu panel background (drawn behind title + buttons for visibility)
        try:
            self.options_panel_image = pygame.image.load('assets/OptionsMenuBG.png').convert_alpha()
        except (FileNotFoundError, pygame.error, OSError):
            self.options_panel_image = None

        # Load text bar image for IP input field
        try:
            self.text_bar_image = pygame.image.load('assets/TextBar.png').convert_alpha()
        except (FileNotFoundError, pygame.error, OSError):
            self.text_bar_image = None

        # State
        self.result = None  # 'host', 'join', 'back'
        self.phase = 'select'  # 'select', 'host', 'join'

        # Hover and click state tracking (for main menu style button effects)
        self.hovered_button = None
        self.clicked_button = None

        # Taxation configuration (for host)
        self.taxation_level = 0  # 0=0%, 1=25%, 2=50%, 3=75%, 4=100%
        self.taxation_options = ["0% (No Tax)", "25% Tax", "50% Tax", "75% Tax", "100% Tax"]

        # Victory condition configuration (for host)
        self.victory_condition = 0  # 0=Domination, 1=Capital Assault, 2=Total Conquest
        self.victory_options = ["Domination (45+)", "Capital Assault", "Total Conquest"]

        # Turn mode configuration (for host)
        self.turn_mode = 0  # 0=Sequential, 1=Simultaneous
        self.turn_mode_options = ["Sequential", "Simultaneous"]

        # Buttons for host/join selection - vertically stacked like main menu
        button_width = 400
        button_height = 70
        button_spacing = 20
        center_x = self.width // 2
        # Start buttons at vertical center, offset up to account for 3 buttons
        total_buttons_height = 3 * button_height + 2 * button_spacing
        start_y = self.height // 2 - total_buttons_height // 2 + 40  # Slight offset down for title

        self.host_button = pygame.Rect(
            center_x - button_width // 2,
            start_y,
            button_width,
            button_height
        )

        self.join_button = pygame.Rect(
            center_x - button_width // 2,
            start_y + button_height + button_spacing,
            button_width,
            button_height
        )

        self.back_button = pygame.Rect(
            center_x - button_width // 2,
            start_y + 2 * (button_height + button_spacing),
            button_width,
            button_height
        )

    def run(self) -> Optional[Tuple]:
        """
        Run the multiplayer setup flow.

        Returns:
            Tuple of (mode, network_connection, config) or None if cancelled
            - mode: 'host' or 'client'
            - network_connection: NetworkServer or NetworkClient instance
            - config: Setup configuration dict
        """
        clock = pygame.time.Clock()
        running = True

        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    # Alt+F4: signal caller to exit the entire app
                    return 'quit'

                # Music track ended — advance to next track
                if event.type == _MUSIC_END_EVENT:
                    _music_manager.handle_music_end_event()

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        self.handle_click(event.pos)

            # Check result
            if self.result == 'back':
                return None
            elif self.result == 'host':
                # Launch host setup flow
                result = self._run_host_setup()
                if result:
                    return result
                else:
                    # Reset to selection screen
                    self.result = None
                    self.phase = 'select'
            elif self.result == 'join':
                # Launch join setup flow
                result = self._run_join_setup()
                if result:
                    return result
                else:
                    # Reset to selection screen
                    self.result = None
                    self.phase = 'select'

            # Render
            self.render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()
            clock.tick(60)

        return None

    def handle_click(self, pos):
        """Handle mouse click with flash effect (matching main menu)."""
        if self.phase == 'select':
            # Check each button and set clicked_button for flash effect
            if self.host_button.collidepoint(pos):
                sound_manager.play_ui_click()
                self.clicked_button = 'host'
                self.result = 'host'
            elif self.join_button.collidepoint(pos):
                sound_manager.play_ui_click()
                self.clicked_button = 'join'
                self.result = 'join'
            elif self.back_button.collidepoint(pos):
                sound_manager.play_ui_click()
                self.clicked_button = 'back'
                self.result = 'back'

    def render(self):
        """Render the selection screen with main menu style."""
        if self.phase == 'select':
            # Draw background image or fallback to black
            if self.background_image:
                self.screen.blit(self.background_image, (0, 0))
            else:
                self.screen.fill(BLACK)

            # Update hover state
            mouse_pos = pygame.mouse.get_pos()
            self.hovered_button = None
            if self.host_button.collidepoint(mouse_pos):
                self.hovered_button = 'host'
            elif self.join_button.collidepoint(mouse_pos):
                self.hovered_button = 'join'
            elif self.back_button.collidepoint(mouse_pos):
                self.hovered_button = 'back'

            # Draw options panel background behind title and buttons for visibility
            if self.options_panel_image:
                # Panel spans from above title to below last button, with padding
                panel_top = self.host_button.top - 150  # Above title (+20% padding)
                panel_bottom = self.back_button.bottom + 60  # Below last button (+20% padding)
                panel_height = panel_bottom - panel_top
                panel_width = 620  # Wider frame around buttons (+20%)
                panel_x = self.width // 2 - panel_width // 2
                scaled_panel = pygame.transform.smoothscale(
                    self.options_panel_image, (panel_width, panel_height)
                )
                self.screen.blit(scaled_panel, (panel_x, panel_top))

            # Title - centered above buttons
            title_text = self.title_font.render("Multiplayer", True, WHITE)
            title_rect = title_text.get_rect(center=(self.width // 2, self.host_button.top - 60))
            self.screen.blit(title_text, title_rect)

            # Draw buttons with main menu styling
            self._draw_menu_button('host', self.host_button, "Host Game", BRASS_COLOR)
            self._draw_menu_button('join', self.join_button, "Join Game", BRASS_COLOR)
            self._draw_menu_button('back', self.back_button, "Return", WHITE)

            # Reset click flash after rendering (one-frame flash like main menu)
            self.clicked_button = None

    def _draw_menu_button(self, button_id, rect, text, text_color):
        """Draw a button with main menu styling (image bg, hover/click effects).

        Args:
            button_id: Identifier to check hover/click state
            rect: Button rectangle
            text: Button label
            text_color: Text color when enabled (brass for action buttons, white for return)
        """
        is_hovered = (self.hovered_button == button_id)
        is_clicked = (self.clicked_button == button_id)

        if self.button_bg_image:
            # Scale button background image to button dimensions
            scaled_bg = pygame.transform.smoothscale(
                self.button_bg_image, (rect.width, rect.height)
            )
            button_surface = scaled_bg.copy()

            # Base darkening (matching main menu exactly)
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

            # Click flash or hover highlight
            if is_clicked:
                button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGB_ADD)
            elif is_hovered:
                button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGB_ADD)

            self.screen.blit(button_surface, rect)
        else:
            # Fallback: colored rectangle with border
            if is_clicked:
                bg_color = (100, 100, 120)
            elif is_hovered:
                bg_color = (80, 80, 100)
            else:
                bg_color = DARK_GRAY
            pygame.draw.rect(self.screen, bg_color, rect, border_radius=10)
            pygame.draw.rect(self.screen, GRAY, rect, 3, border_radius=10)

        # Render button text centered
        button_text = self.button_font.render(text, True, text_color)
        button_text_rect = button_text.get_rect(center=rect.center)
        self.screen.blit(button_text, button_text_rect)

    def _run_host_setup(self) -> Optional[Tuple]:
        """
        Run host setup flow.

        Returns:
            Tuple of ('host', server, config) or None if cancelled
        """
        # Start server
        server = NetworkServer()
        if not server.start():
            self._show_error("Failed to start server")
            return None

        # Start UPnP port forwarding in background (non-blocking)
        # Automatically maps port on router for internet play if UPnP available
        server.setup_upnp()

        # Get local IP for initial display (updated with public IP when UPnP completes)
        local_ip = server.get_local_ip()
        logger.info(f"Server started! IP: {local_ip}")

        # Go directly to territory selector / lobby
        # Players can join while host is configuring the game
        from settings_manager import settings
        player_name = settings.get_player_name()

        selector = TerritorySelector(
            self.screen, server, is_host=True,
            num_players=4,  # Support up to 4 players
            victory_condition=self.victory_condition,
            taxation_level=self.taxation_level,
            turn_mode=self.turn_mode,
            lobby_state=None,  # Host creates internally
            local_player_index=0,  # Host is always slot 0
            host_ip=local_ip  # Pass IP for display in lobby
        )
        result = selector.run()

        if result == 'quit':
            # Alt+F4 pressed — propagate quit signal
            server.stop()
            return 'quit'
        if not result:
            # User cancelled
            server.stop()
            return None

        # Unpack return format: (lobby_state, victory_condition, taxation_level, turn_mode, neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer)
        lobby_state, victory_condition, taxation_level, turn_mode, neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer = result

        # Build config from LobbyState
        config = self._build_config_from_lobby(lobby_state, victory_condition, taxation_level, turn_mode,
                                                neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer)
        # Multi-map support: include selected map_id from selector
        config['map_id'] = selector.selected_map

        # Log configuration
        active_players = lobby_state.get_active_players()
        logger.info(f"Game configured with {len(active_players)} players:")
        for slot in active_players:
            logger.info(f"  Slot {slot.index}: {slot.player_name} -> {slot.territory} (Team {slot.team + 1})")
        logger.info(f"Settings: Victory={self.victory_options[victory_condition]}, Tax={taxation_level}, Mode={self.turn_mode_options[turn_mode]}, Map={selector.selected_map}")

        return ('host', server, config)

    def _run_join_setup(self) -> Optional[Tuple]:
        """
        Run join setup flow.

        Returns:
            Tuple of ('client', client, config) or None if cancelled
        """
        # Show IP input screen
        host_ip = self._get_host_ip()
        if not host_ip:
            return None

        # Connect to server
        client = NetworkClient()

        # Show connecting screen
        self._render_connecting(host_ip)
        draw_custom_cursor(self.screen)
        pygame.display.flip()

        # Use profile name from settings
        from settings_manager import settings
        player_name = settings.get_player_name()

        if not client.connect(host_ip, player_name=player_name):
            self._show_error(f"Failed to connect to {host_ip}")
            return None

        logger.info(f"Connected to server at {host_ip}")

        # Get assigned player index from connection accept message
        # The client will receive this during the connection handshake
        local_player_index = getattr(client, 'player_index', 1)  # Default to 1 if not set

        # Show territory selection screen
        # Client doesn't pass settings - receives them from host via network
        logger.info("Connected! Starting territory selection...")
        selector = TerritorySelector(
            self.screen, client, is_host=False,
            num_players=4,  # Support up to 4 players
            victory_condition=0,  # Will be updated from host
            taxation_level=0,
            turn_mode=0,
            lobby_state=None,  # Client creates internally, synced from host
            local_player_index=local_player_index
        )
        result = selector.run()

        if result == 'quit':
            # Alt+F4 pressed — propagate quit signal
            client.disconnect()
            return 'quit'
        if not result:
            # User cancelled
            client.disconnect()
            return None

        # Check if kicked by host
        if isinstance(result, tuple) and len(result) == 2 and result[0] == 'kicked':
            kick_reason = result[1]
            client.disconnect()
            self._show_error(f"You were kicked from the lobby: {kick_reason}")
            return None

        # Unpack return format: (lobby_state, victory_condition, taxation_level, turn_mode, neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer)
        lobby_state, victory_condition, taxation_level, turn_mode, neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer = result

        # Get the potentially updated local_player_index from selector
        # (may have changed from LOBBY_STATE sync if host reassigned us to a different slot)
        final_player_index = selector.local_player_index
        logger.debug(f"Final player index after lobby: {final_player_index}")

        # Update the client's player_index to match the lobby assignment
        # This ensures network_connection.get_player_index() returns the correct slot
        client.player_index = final_player_index

        # Build config from LobbyState
        config = self._build_config_from_lobby(lobby_state, victory_condition, taxation_level, turn_mode,
                                                neutral_armies, randomize_bonuses, bonus_mapping, gold_transfer)
        # Multi-map support: include selected map_id from selector
        config['map_id'] = selector.selected_map

        # Log configuration
        active_players = lobby_state.get_active_players()
        logger.info(f"Game configured with {len(active_players)} players:")
        for slot in active_players:
            logger.info(f"  Slot {slot.index}: {slot.player_name} -> {slot.territory} (Team {slot.team + 1})")
        logger.info(f"Settings from host: Victory={self.victory_options[victory_condition]}, Tax={taxation_level}, Mode={self.turn_mode_options[turn_mode]}, Map={selector.selected_map}")

        return ('client', client, config)

    def _render_host_waiting(self, local_ip: str, exit_button_rect=None, hovered_btn=None, clicked_btn=None):
        """Render waiting for client screen with MPSetBG.png background and OptionsMenuBG panel."""
        # Background
        if self.background_image:
            self.screen.blit(self.background_image, (0, 0))
        else:
            self.screen.fill(BLACK)

        center_x = self.width // 2

        # Calculate panel bounds based on content layout
        # Content: title, status, ip label, ip address, instructions, exit button
        # Use exit_button_rect bottom as reference for panel bottom
        if exit_button_rect:
            panel_bottom = exit_button_rect.bottom + 85
        else:
            panel_bottom = self.height // 2 + 250

        # Panel top: above the title with padding (+20% height = more top space)
        title_y = self.height // 2 - 160
        panel_top = title_y - 135

        # Draw OptionsMenuBG panel
        if self.options_panel_image:
            panel_width = 840  # +35% wider than original 620
            panel_height = panel_bottom - panel_top
            panel_x = center_x - panel_width // 2
            scaled_panel = pygame.transform.smoothscale(
                self.options_panel_image, (panel_width, panel_height)
            )
            self.screen.blit(scaled_panel, (panel_x, panel_top))

        # Title
        title_text = self.title_font.render("Hosting Game", True, WHITE)
        title_rect = title_text.get_rect(center=(center_x, title_y))
        self.screen.blit(title_text, title_rect)

        # Status
        status_y = title_y + 70
        status_text = self.subtitle_font.render("Waiting for player to join...", True, GREEN)
        status_rect = status_text.get_rect(center=(center_x, status_y))
        self.screen.blit(status_text, status_rect)

        # IP Address label
        ip_label_y = status_y + 70
        ip_label = self.text_font.render("Your IP Address:", True, LIGHT_GRAY)
        ip_label_rect = ip_label.get_rect(center=(center_x, ip_label_y))
        self.screen.blit(ip_label, ip_label_rect)

        # IP Address value
        ip_y = ip_label_y + 40
        ip_text = self.subtitle_font.render(local_ip, True, WHITE)
        ip_rect = ip_text.get_rect(center=(center_x, ip_y))
        self.screen.blit(ip_text, ip_rect)

        # Instructions (without "Press ESC to cancel" — replaced by Exit button)
        instructions = [
            "Share this IP address with the other player",
            "They should click 'Join Game' and enter this IP",
            "",
            "Game settings will be configured after connection",
        ]
        y_offset = ip_y + 60
        for instruction in instructions:
            inst_text = self.small_font.render(instruction, True, LIGHT_GRAY)
            inst_rect = inst_text.get_rect(center=(center_x, y_offset))
            self.screen.blit(inst_text, inst_rect)
            y_offset += 30

        # Exit button (white text, main menu style)
        if exit_button_rect:
            is_hovered = (hovered_btn == 'exit')
            is_clicked = (clicked_btn == 'exit')
            self._draw_join_screen_button(exit_button_rect, "Exit", WHITE, is_hovered, is_clicked)

    def _render_connecting(self, host_ip: str):
        """Render connecting screen"""
        self.screen.fill(BLACK)

        title_text = self.title_font.render("Connecting...", True, WHITE)
        title_rect = title_text.get_rect(center=(self.width // 2, self.height // 2 - 50))
        self.screen.blit(title_text, title_rect)

        ip_text = self.text_font.render(f"Connecting to {host_ip}", True, LIGHT_GRAY)
        ip_rect = ip_text.get_rect(center=(self.width // 2, self.height // 2 + 50))
        self.screen.blit(ip_text, ip_rect)

    def _get_host_ip(self) -> Optional[str]:
        """
        Get host IP address from user input.

        Uses MPSetBG.png background, OptionsMenuBG panel, TextBar.png input field,
        and main-menu-style Join Game / Exit buttons. Supports hold-to-delete backspace.

        Returns:
            IP address string or None if cancelled
        """
        # Initialize clipboard support for Ctrl+V paste
        try:
            pygame.scrap.init()
        except Exception:
            pass  # Non-fatal — paste just won't work

        input_text = "127.0.0.1"  # Default to localhost
        input_active = True
        cursor_visible = True
        cursor_timer = 0

        # Backspace hold-to-delete state
        backspace_held = False
        backspace_hold_timer = 0
        backspace_initial_delay = 400  # ms before repeat starts
        backspace_repeat_rate = 50  # ms between repeated deletes

        # Layout: TextBar input + two buttons vertically stacked, centered
        button_width = 400
        button_height = 70
        button_spacing = 20
        text_bar_width = 400
        text_bar_layout_height = 80  # Layout spacing height (for positioning other elements)
        text_bar_visual_height = 400  # Visual height of TextBar.png (unsquished)
        center_x = self.width // 2

        # Vertical layout: label, text bar (layout height), join button, exit button
        # Center the group vertically with slight downward offset for title
        group_height = text_bar_layout_height + button_spacing + 2 * button_height + button_spacing
        start_y = self.height // 2 - group_height // 2 + 30

        # Layout rect (small, for positioning buttons/title relative to text bar)
        text_bar_layout_rect = pygame.Rect(
            center_x - text_bar_width // 2, start_y,
            text_bar_width, text_bar_layout_height
        )
        # Visual rect (large, for rendering the TextBar.png centered on layout rect)
        text_bar_rect = pygame.Rect(
            center_x - text_bar_width // 2,
            text_bar_layout_rect.centery - text_bar_visual_height // 2,
            text_bar_width, text_bar_visual_height
        )
        join_button_rect = pygame.Rect(
            center_x - button_width // 2,
            text_bar_layout_rect.bottom + button_spacing,
            button_width, button_height
        )
        exit_button_rect = pygame.Rect(
            center_x - button_width // 2,
            join_button_rect.bottom + button_spacing,
            button_width, button_height
        )

        # Panel background sizing (covers title + all elements)
        panel_top = text_bar_layout_rect.top - 165  # Space above for title + label
        panel_bottom = exit_button_rect.bottom + 90  # Space below
        panel_width = 620  # Match selection screen panel width

        # Hover/click tracking for buttons
        hovered_btn = None
        clicked_btn = None

        clock = pygame.time.Clock()

        while input_active:
            dt = clock.get_time()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    # Alt+F4: signal caller to exit the entire app
                    return 'quit'

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    elif event.key == pygame.K_RETURN:
                        return input_text if input_text else None
                    elif event.key == pygame.K_BACKSPACE:
                        # Delete one character immediately, start hold timer
                        input_text = input_text[:-1]
                        backspace_held = True
                        backspace_hold_timer = 0
                    elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                        # Ctrl+V: paste from clipboard, filter to valid IP chars
                        try:
                            clipboard_text = pygame.scrap.get(pygame.SCRAP_TEXT)
                            if clipboard_text:
                                paste = clipboard_text.decode('utf-8', errors='ignore').rstrip('\x00')
                                # Keep only valid IP characters
                                filtered = ''.join(c for c in paste if c in '0123456789.')
                                # Clip to max IP length
                                remaining = 15 - len(input_text)
                                if remaining > 0 and filtered:
                                    input_text += filtered[:remaining]
                        except Exception:
                            pass  # Clipboard not available
                    else:
                        # Add character if valid for IP address
                        if event.unicode in '0123456789.':
                            if len(input_text) < 15:  # Max IP length
                                input_text += event.unicode

                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_BACKSPACE:
                        backspace_held = False
                        backspace_hold_timer = 0

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if join_button_rect.collidepoint(event.pos):
                            sound_manager.play_ui_click()
                            clicked_btn = 'join'
                            return input_text if input_text else None
                        elif exit_button_rect.collidepoint(event.pos):
                            sound_manager.play_ui_click()
                            clicked_btn = 'exit'
                            return None

            # Handle backspace hold-to-delete repeating
            if backspace_held and input_text:
                backspace_hold_timer += dt
                if backspace_hold_timer >= backspace_initial_delay:
                    # After initial delay, delete at repeat rate
                    excess = backspace_hold_timer - backspace_initial_delay
                    chars_to_delete = int(excess / backspace_repeat_rate)
                    if chars_to_delete > 0:
                        input_text = input_text[:-chars_to_delete]
                        # Reset excess but keep held state
                        backspace_hold_timer = backspace_initial_delay + (excess % backspace_repeat_rate)

            # Update cursor blink
            cursor_timer += dt
            if cursor_timer >= 500:
                cursor_visible = not cursor_visible
                cursor_timer = 0

            # Update hover state
            mouse_pos = pygame.mouse.get_pos()
            hovered_btn = None
            if join_button_rect.collidepoint(mouse_pos):
                hovered_btn = 'join'
            elif exit_button_rect.collidepoint(mouse_pos):
                hovered_btn = 'exit'

            # --- Render ---
            # Background
            if self.background_image:
                self.screen.blit(self.background_image, (0, 0))
            else:
                self.screen.fill(BLACK)

            # Options panel background behind all elements
            if self.options_panel_image:
                panel_height = panel_bottom - panel_top
                panel_x = center_x - panel_width // 2
                scaled_panel = pygame.transform.smoothscale(
                    self.options_panel_image, (panel_width, panel_height)
                )
                self.screen.blit(scaled_panel, (panel_x, panel_top))

            # Title (positioned relative to layout rect, not visual rect)
            title_text = self.title_font.render("Join Game", True, WHITE)
            title_rect = title_text.get_rect(center=(center_x, text_bar_layout_rect.top - 70))
            self.screen.blit(title_text, title_rect)

            # Label above text bar
            label_text = self.text_font.render("Enter Host IP Address:", True, LIGHT_GRAY)
            label_rect = label_text.get_rect(center=(center_x, text_bar_layout_rect.top - 30))
            self.screen.blit(label_text, label_rect)

            # Text bar input field using TextBar.png (visual rect, larger than layout)
            if self.text_bar_image:
                scaled_bar = pygame.transform.smoothscale(
                    self.text_bar_image, (text_bar_rect.width, text_bar_rect.height)
                )
                # Offset TextBar.png 8px down to align with input text visually
                self.screen.blit(scaled_bar, (text_bar_rect.x, text_bar_rect.y + 23))
            else:
                # Fallback: dark rect with border (use layout rect for fallback)
                pygame.draw.rect(self.screen, (20, 20, 20), text_bar_layout_rect)
                pygame.draw.rect(self.screen, WHITE, text_bar_layout_rect, 2)

            # IP text centered on the visual TextBar (not layout rect) for alignment
            text_surface = self.text_font.render(input_text, True, WHITE)
            text_render_rect = text_surface.get_rect(center=text_bar_rect.center)
            self.screen.blit(text_surface, text_render_rect)

            # Blinking cursor
            if cursor_visible:
                cursor_x = text_render_rect.right + 3
                cursor_y = text_bar_rect.centery
                pygame.draw.line(self.screen, WHITE,
                                 (cursor_x, cursor_y - 15), (cursor_x, cursor_y + 15), 2)

            # Join Game button (brass text, main menu style)
            self._draw_join_screen_button(
                join_button_rect, "Join Game", BRASS_COLOR,
                hovered_btn == 'join', clicked_btn == 'join'
            )

            # Exit button (white text, main menu style)
            self._draw_join_screen_button(
                exit_button_rect, "Exit", WHITE,
                hovered_btn == 'exit', clicked_btn == 'exit'
            )

            # Reset click flash after render
            clicked_btn = None

            draw_custom_cursor(self.screen)
            pygame.display.flip()
            clock.tick(60)

        return None

    def _draw_join_screen_button(self, rect, text, text_color, is_hovered, is_clicked):
        """Draw a button on the join screen with main menu styling.

        Reuses the same visual style as the selection screen buttons.
        """
        if self.button_bg_image:
            scaled_bg = pygame.transform.smoothscale(
                self.button_bg_image, (rect.width, rect.height)
            )
            button_surface = scaled_bg.copy()

            # Base darkening (matching main menu)
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)

            # Click flash or hover highlight
            if is_clicked:
                button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGB_ADD)
            elif is_hovered:
                button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGB_ADD)

            self.screen.blit(button_surface, rect)
        else:
            if is_clicked:
                bg_color = (100, 100, 120)
            elif is_hovered:
                bg_color = (80, 80, 100)
            else:
                bg_color = DARK_GRAY
            pygame.draw.rect(self.screen, bg_color, rect, border_radius=10)
            pygame.draw.rect(self.screen, GRAY, rect, 3, border_radius=10)

        button_text = self.button_font.render(text, True, text_color)
        button_text_rect = button_text.get_rect(center=rect.center)
        self.screen.blit(button_text, button_text_rect)

    def _build_config_from_lobby(self, lobby_state: LobbyState, victory_condition: int,
                                  taxation_level: int, turn_mode: int,
                                  neutral_armies: bool = False, randomize_bonuses: bool = False,
                                  bonus_mapping: dict = None, gold_transfer: int = 0) -> Dict:
        """
        Build game configuration dict from LobbyState.

        Args:
            lobby_state: Finalized lobby state with all players configured
            victory_condition: Victory condition index (0-2)
            taxation_level: Taxation level index (0-4)
            turn_mode: Turn mode index (0=Sequential, 1=Simultaneous)
            neutral_armies: Whether neutral armies are enabled
            randomize_bonuses: Whether territory bonuses are randomized
            bonus_mapping: Host-generated randomized bonus mapping (for client sync)

        Returns:
            Game configuration dict for GameState initialization
        """
        active_slots = lobby_state.get_active_players()
        num_players = len(active_slots)

        # Build player configuration lists
        player_is_ai = []
        player_ai_difficulty = []
        player_territories = {}
        player_colors = {}
        player_teams = {}
        player_names = {}

        # Debug: Log slot states before building config
        logger.debug("Building config from lobby_state:")
        for slot in lobby_state.slots:
            logger.debug(f"  Slot {slot.index}: state={slot.state}, name={slot.player_name}, territory={slot.territory}")

        for slot in lobby_state.slots:
            if slot.is_active():
                is_ai = (slot.state == SLOT_AI) or (slot.state == 'disconnected')
                player_is_ai.append(is_ai)
                player_ai_difficulty.append(slot.ai_difficulty if is_ai else 1)
                player_territories[slot.index] = slot.territory
                player_colors[slot.index] = slot.color
                player_teams[slot.index] = slot.team
                player_names[slot.index] = slot.player_name

        logger.debug(f"Config result: player_is_ai={player_is_ai}")

        # Legacy compatibility: player1_territory, player2_territory
        territories_list = [slot.territory for slot in active_slots]
        player1_territory = territories_list[0] if len(territories_list) > 0 else ""
        player2_territory = territories_list[1] if len(territories_list) > 1 else ""

        config = {
            # Core player configuration
            'num_players': num_players,
            'player_is_ai': player_is_ai,
            'player_ai_difficulty': player_ai_difficulty,

            # Legacy territory fields (for 2-player compatibility)
            'player1_territory': player1_territory,
            'player2_territory': player2_territory,

            # Full territory/team/color mapping (for 2-4 player support)
            'player_territories': player_territories,  # {slot_index: territory_name}
            'player_colors': player_colors,            # {slot_index: color_index}
            'player_teams': player_teams,              # {slot_index: team_index}
            'player_names': player_names,              # {slot_index: player_name}

            # Game settings
            'win_condition': self.victory_options[victory_condition],
            'taxation_level': taxation_level,
            'game_mode': 'simultaneous' if turn_mode == 1 else 'sequential',
            'multiplayer_mode': True,

            # Additional options
            'neutral_armies': neutral_armies,
            'randomize_bonuses': randomize_bonuses,
            'gold_transfer': gold_transfer,
            'bonus_mapping': bonus_mapping,  # Host-generated mapping for client sync
            'game_seed': int(time.time() * 1000) % (2**31),  # Deterministic seed for neutral army placement

            # Full lobby state for reference
            'lobby_state': lobby_state
        }

        return config

    def _show_error(self, message: str):
        """Show error message"""
        clock = pygame.time.Clock()
        showing = True
        start_time = pygame.time.get_ticks()

        while showing:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                    return

            # Auto-dismiss after 3 seconds
            if pygame.time.get_ticks() - start_time > 3000:
                return

            self.screen.fill(BLACK)

            error_text = self.subtitle_font.render("Error", True, RED)
            error_rect = error_text.get_rect(center=(self.width // 2, self.height // 2 - 50))
            self.screen.blit(error_text, error_rect)

            message_text = self.text_font.render(message, True, WHITE)
            message_rect = message_text.get_rect(center=(self.width // 2, self.height // 2 + 50))
            self.screen.blit(message_text, message_rect)

            inst_text = self.small_font.render("Click or press any key to continue", True, LIGHT_GRAY)
            inst_rect = inst_text.get_rect(center=(self.width // 2, self.height - 100))
            self.screen.blit(inst_text, inst_rect)

            draw_custom_cursor(self.screen)
            pygame.display.flip()
            clock.tick(60)
