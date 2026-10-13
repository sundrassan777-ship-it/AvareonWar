"""
Multiplayer setup UI for hosting and joining games.

Handles connection establishment and territory selection for multiplayer mode.
Expanded for 2-4 players with AI support and alliance system.
"""

import pygame
import socket
import threading
import time
from collections import namedtuple
from typing import Optional, Tuple, Dict, List

from network.server import NetworkServer
from network.client import NetworkClient, SteamTarget, parse_connect_targets
from network.protocol import NetworkProtocol
from network.lobby import LobbyState, LobbySlot, SLOT_EMPTY, SLOT_HUMAN, SLOT_AI
from network_config import MessageType
import map_data
from network.territory_selector import TerritorySelector  # Updated import path
from global_sound import sound_manager  # Global sound manager for UI clicks
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.logger import get_logger
from utils.cursor import draw_custom_cursor
from display_utils import menu_frame_cap
from config.constants import STARTING_GOLD_DEFAULT, clamp_starting_gold
from steam_integration import steam_manager

logger = get_logger(__name__)

# The error screen after a failed join: shown at least this long, longer for long
# reasons (Steam's say what to check), at most the maximum (a click / key closes it)
ERROR_MIN_MS = 3000
ERROR_MS_PER_CHAR = 60
ERROR_MAX_MS = 12000

# Join Game screen, Steam Friends tab: friends hosting a lobby, from their Steam rich
# presence (steam_manager.get_hosting_friends - the host's lobby sets it). Shown only
# with Steam; the Direct IP tab is the address box it always was.
FRIENDS_REFRESH_SECONDS = 2.0     # the list is re-read this often
FRIEND_ROWS_VISIBLE = 3           # more scroll (mouse wheel)
FRIEND_ROW_HEIGHT = 64
FRIEND_ROW_SPACING = 6
JOIN_TAB_ROW_HEIGHT = 70          # the title moves up this much to make room for the tabs
NO_FRIENDS_HOSTING = "No friends are hosting right now - ask them to host, or use Direct IP."

# What the Join Game screen returns when a friend was picked on the Steam Friends tab:
# their Steam name and connect targets ("steam-<id>,ip:port,..." - parse_connect_targets)
FriendJoin = namedtuple('FriendJoin', ['name', 'connect'])


class HostingFriendsList:
    """
    The Steam Friends tab's list: friends hosting a lobby, re-read every
    FRIENDS_REFRESH_SECONDS while the tab is shown, scrolled a row at a time.
    """

    def __init__(self, source=None):
        # Late-bound by default, so tests can replace steam_manager.get_hosting_friends
        self._source = source or (lambda: steam_manager.get_hosting_friends())
        self.friends = []
        self.scroll = 0                   # index of the first visible friend
        self._next_refresh = float('-inf')

    def update(self, now: float):
        """Re-read the hosting friends when due (the first call always reads)."""
        if now < self._next_refresh:
            return
        self._next_refresh = now + FRIENDS_REFRESH_SECONDS
        self.friends = list(self._source() or [])
        self.scroll = max(0, min(self.scroll, self.max_scroll()))

    def max_scroll(self) -> int:
        return max(0, len(self.friends) - FRIEND_ROWS_VISIBLE)

    def scroll_by(self, rows: int):
        self.scroll = max(0, min(self.scroll + rows, self.max_scroll()))

    def visible(self) -> List[Dict]:
        return self.friends[self.scroll:self.scroll + FRIEND_ROWS_VISIBLE]


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
CONNECTING_HINT_COLOR = (235, 222, 190)   # parchment: secondary text on the wooden panel

# Option labels: the lobby sends indices, the game config stores the victory name
VICTORY_OPTIONS = ["Domination (45+)", "Capital Assault", "Total Conquest"]
TURN_MODE_OPTIONS = ["Sequential", "Simultaneous"]


def build_multiplayer_config(selector) -> Dict:
    """
    The game config for a lobby that just launched, read from the finished
    TerritorySelector. Host, Join Game and Steam-invite joins all build it here.

    One builder so the flows cannot drift apart again: the Steam-invite copy never
    passed map_id (invited players loaded Avareon whatever map the host picked), and
    every PC rolled its own game_seed (different Neutral Armies). Both now come from
    the selector, where the host's LOBBY_LAUNCH put them.
    """
    setup = MultiplayerSetup.__new__(MultiplayerSetup)
    return setup._build_config_from_lobby(
        selector.lobby_state, selector.victory_condition, selector.taxation_level,
        selector.turn_mode, selector.neutral_armies, selector.randomize_bonuses,
        selector.bonus_mapping, selector.gold_transfer,
        map_id=selector.selected_map, game_seed=selector.game_seed)


def run_client_lobby(screen, client) -> Optional[object]:
    """
    The lobby for a client that is already connected - Join Game and Steam invites.

    Returns:
        ('client', client, config) when the host launches the game,
        'quit' on Alt+F4,
        ('kicked', reason) when the host kicked us,
        ('lost', reason) when the connection to the host dropped,
        None when the player left the lobby.
    The caller disconnects the client for anything but a launch.
    """
    selector = TerritorySelector(
        screen, client, is_host=False,
        num_players=4,  # Support up to 4 players
        victory_condition=0,  # Will be updated from host
        taxation_level=0,
        turn_mode=0,
        lobby_state=None,  # Client creates internally, synced from host
        # The slot the server gave us (CONNECT_ACCEPT); it never changes in the lobby
        local_player_index=client.player_index
    )
    result = selector.run()

    if result == 'quit':
        return 'quit'
    if isinstance(result, tuple) and len(result) == 2 and result[0] == 'kicked':
        return result
    if not result:
        if getattr(client, 'disconnected', False):
            # Host closed the lobby / connection died - say so instead of silently
            # dropping back to the menu
            return ('lost', getattr(client, 'disconnect_reason', '') or "Lost connection to the host")
        return None

    config = build_multiplayer_config(selector)

    active_players = selector.lobby_state.get_active_players()
    logger.info(f"Game configured with {len(active_players)} players (we are slot {client.player_index}):")
    for slot in active_players:
        logger.info(f"  Slot {slot.index}: {slot.player_name} -> {slot.territory} (Team {slot.team + 1})")
    logger.info(f"Settings from host: Victory={config['win_condition']}, Tax={config['taxation_level']}, "
                f"Mode={config['game_mode']}, Map={config.get('map_id')}, Seed={config['game_seed']}")
    return ('client', client, config)


class MultiplayerSetup:
    """
    Multiplayer setup screen.

    Handles host/join selection, connection, and initial setup.
    """

    # Class-level so a bare MultiplayerSetup.__new__() (build_multiplayer_config) has them
    victory_options = VICTORY_OPTIONS
    turn_mode_options = TURN_MODE_OPTIONS

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
            # Join screen: tab labels + friend names, and the friends' status line
            self.list_font = pygame.font.Font(semibold_path, 24)
            self.status_font = pygame.font.Font(regular_path, 17)
        except (FileNotFoundError, pygame.error, OSError):
            self.title_font = pygame.font.Font(None, 72)
            self.subtitle_font = pygame.font.Font(None, 48)
            self.button_font = pygame.font.Font(None, 36)
            self.text_font = pygame.font.Font(None, 32)
            self.small_font = pygame.font.Font(None, 24)
            self.list_font = pygame.font.Font(None, 30)
            self.status_font = pygame.font.Font(None, 22)

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

        # Drawing caches (these screens redraw every frame): scaled art / buttons, text
        self._surface_cache = {}
        self._text_cache = {}

        # A Steam join request the menu took (FriendJoin), joined instead of showing the
        # Join Game screen
        self._pending_join = None

        # Hover and click state tracking (for main menu style button effects)
        self.hovered_button = None
        self.clicked_button = None

        # Taxation configuration (for host)
        self.taxation_level = 0  # 0=0%, 1=25%, 2=50%, 3=75%, 4=100%
        self.taxation_options = ["0% (No Tax)", "25% Tax", "50% Tax", "75% Tax", "100% Tax"]

        # Victory condition configuration (for host)
        self.victory_condition = 0  # 0=Domination, 1=Capital Assault, 2=Total Conquest
        self.victory_options = list(VICTORY_OPTIONS)

        # Turn mode configuration (for host)
        self.turn_mode = 0  # 0=Sequential, 1=Simultaneous
        self.turn_mode_options = list(TURN_MODE_OPTIONS)

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
                # Launch join setup flow (straight to the friend a Steam join request
                # names, if the menu took one)
                pending, self._pending_join = self._pending_join, None
                result = self._run_join_setup(pending)
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
            # Steam callbacks every frame (see steam_manager.run_callbacks)
            steam_manager.run_callbacks()
            # A Steam join request (invite accepted / "Join Game" on a friend) is joined
            # from here too, not only from the main menu (two-PC test 2026-10-13: Join
            # Game pressed twice on this screen did nothing until the main menu)
            if self.result is None:
                join = steam_manager.take_join_request()
                if join is not None:
                    self._pending_join = self._friend_join_from_request(join)
                    self.result = 'join'
            clock.tick(menu_frame_cap())

        return None

    @staticmethod
    def _friend_join_from_request(join):
        """A Steam join request as the Join Game screen's FriendJoin (host's name, targets)."""
        return FriendJoin(steam_manager.join_request_host_name(join) or "your friend", join.connect)

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

        # Joining through Steam's relay too (no port forwarding needed; no-op without Steam)
        server.setup_steam()

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

        # Build config from the launched lobby (shared builder: map_id + game_seed included)
        config = build_multiplayer_config(selector)

        # Log configuration
        active_players = selector.lobby_state.get_active_players()
        logger.info(f"Game configured with {len(active_players)} players:")
        for slot in active_players:
            logger.info(f"  Slot {slot.index}: {slot.player_name} -> {slot.territory} (Team {slot.team + 1})")
        logger.info(f"Settings: Victory={config['win_condition']}, Tax={config['taxation_level']}, "
                    f"Mode={config['game_mode']}, Map={config.get('map_id')}, Seed={config['game_seed']}")

        return ('host', server, config)

    def _run_join_setup(self, choice=None) -> Optional[Tuple]:
        """
        Run join setup flow.

        Args:
            choice: a FriendJoin to join straight away (a Steam join request the menu
                took); None shows the Join Game screen

        Returns:
            Tuple of ('client', client, config) or None if cancelled
        """
        # Show the Join Game screen: an address typed on the Direct IP tab, or a friend
        # picked on the Steam Friends tab / named by a Steam join request (FriendJoin)
        host_ip = choice if choice is not None else self._get_host_ip()
        if host_ip == 'quit':
            # Alt+F4 on the IP screen. It used to be tried as a host name ("quit")
            # and showed a connection error instead of closing the game.
            return 'quit'
        if not host_ip:
            return None
        if isinstance(host_ip, FriendJoin):
            logger.info(f"Joining {host_ip.name} through Steam ('{host_ip.connect}')")
            connect = host_ip.connect
            targets, join_label = parse_connect_targets(connect), f"{host_ip.name}'s game"
        else:
            connect = host_ip
            targets, join_label = parse_connect_targets(host_ip), host_ip

        # Connect to server
        client = NetworkClient()

        # Use profile name from settings
        from settings_manager import settings
        player_name = settings.get_player_name()

        # Behind the "Connecting..." screen (shared with Steam invites in main.py), so
        # the window keeps responding and the player can cancel
        connected = self.connect_with_progress(client, targets, player_name)
        if connected == 'quit':
            return 'quit'
        if connected == 'cancelled':
            return None
        if not connected:
            # Say why (lobby full, version mismatch, nobody hosting, ...)
            reason = client.disconnect_reason
            self._show_error(f"Could not join {join_label}" + (f": {reason}" if reason else ""))
            return None

        logger.info(f"Connected to server at {join_label}")
        # A second request for this host (Join Game pressed twice) is already done
        steam_manager.drop_join_requests_for(connect)

        # Lobby (shared with Steam-invite joins in main.py)
        logger.info("Connected! Starting territory selection...")
        lobby_result = run_client_lobby(self.screen, client)

        if lobby_result == 'quit':
            # Alt+F4 pressed — propagate quit signal
            client.disconnect()
            return 'quit'
        if lobby_result is None:
            # User cancelled
            client.disconnect()
            return None
        if lobby_result[0] == 'kicked':
            client.disconnect()
            self._show_error(f"You were kicked from the lobby: {lobby_result[1]}")
            return None
        if lobby_result[0] == 'lost':
            client.disconnect()
            self._show_error(f"Lost connection to the host: {lobby_result[1]}")
            return None

        return lobby_result

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

    def connect_with_progress(self, client, targets, player_name):
        """
        Join a host while this screen shows "Connecting to X..." with the seconds
        waited and a Cancel button. One path for Join Game (Direct IP), Steam invites
        and join requests from Steam (main.py).

        The connect runs on a worker thread (client.connect_any - Steam first, then the
        addresses): finding a host through Steam can take 15 s, and a window that does
        not handle its events for 5 s is marked "Not Responding" by Windows - it used to
        freeze for as long as the connect took.

        Args:
            client: a new NetworkClient (not reused after a cancel)
            targets: parse_connect_targets() list, tried in order
            player_name: our name for the host's lobby

        Returns:
            True connected, False failed (client.disconnect_reason says why),
            'cancelled' (Cancel / Esc), 'quit' (Alt+F4)
        """
        result = {}
        # Taken by the worker when it reports and by a cancel: a connect that got
        # through just as the player cancelled is always closed again, never leaked
        lock = threading.Lock()

        def work():
            try:
                connected = client.connect_any(targets, player_name=player_name)
            except Exception as e:
                logger.error(f"Joining failed: {e}", exc_info=True)
                client.disconnect_reason = f"Connection error: {e}"
                connected = False
            with lock:
                if connected and client.connect_cancelled:
                    client.disconnect()   # got through just as the player cancelled
                    connected = False
                result['connected'] = connected

        def cancel():
            with lock:
                client.cancel_connect()
                if result.get('connected'):
                    client.disconnect()   # the worker had just got through - leave again

        worker = threading.Thread(target=work, name='mp-connect', daemon=True)
        worker.start()

        # Layout (Join screen style): title, what we are doing, seconds, Cancel. Wider
        # than the Join screen's panel: "Connecting to <Steam name> through Steam..."
        center_x, center_y = self.width // 2, self.height // 2
        cancel_rect = pygame.Rect(center_x - 200, center_y + 80, 400, 70)
        panel_width = min(820, self.width - 80)
        panel_top, panel_bottom = center_y - 190, cancel_rect.bottom + 60
        max_text_width = panel_width - 2 * 90       # inside the frame's pillars
        panel = None
        if self.options_panel_image:
            # Scaled once, not every frame
            panel = pygame.transform.smoothscale(
                self.options_panel_image, (panel_width, panel_bottom - panel_top))
        text_cache = {}

        def text(label, font, color):
            """The label with a dark drop shadow (readable on the wood), cached."""
            key = (label, id(font), color)
            if key not in text_cache:
                face = font.render(label, True, color)
                shadow = font.render(label, True, BLACK)
                surface = pygame.Surface((face.get_width() + 2, face.get_height() + 2),
                                         pygame.SRCALPHA)
                surface.blit(shadow, (2, 2))
                surface.blit(face, (0, 0))
                text_cache[key] = surface
            return text_cache[key]

        fitted_cache = {}

        def fitted(label, fonts):
            """(font, label) that fits inside the frame: the first font wide enough,
            else the smallest with the label shortened (a very long Steam name)."""
            if label not in fitted_cache:
                for font in fonts:
                    if font.size(label)[0] <= max_text_width:
                        fitted_cache[label] = (font, label)
                        break
                else:
                    font, short = fonts[-1], label
                    while short and font.size(short + '...')[0] > max_text_width:
                        short = short[:-1]
                    fitted_cache[label] = (font, short + '...')
            return fitted_cache[label]

        target_names = {}

        def status_lines():
            """What we are doing now, plus a hint while Steam looks for the host."""
            target = client.current_target
            if isinstance(target, SteamTarget):
                if target not in target_names:
                    target_names[target] = steam_manager.friend_name(target.steam_id) or "the host"
                return (f"Connecting to {target_names[target]} through Steam...",
                        "Steam can take up to 15 seconds to find the host")
            if target is not None:
                return f"Connecting to {target[0]}...", ""
            return "Connecting...", ""

        started = time.monotonic()

        def draw(cancel_clicked=False):
            if self.background_image:
                self.screen.blit(self.background_image, (0, 0))
            else:
                self.screen.fill(BLACK)
            if panel is not None:
                self.screen.blit(panel, (center_x - panel_width // 2, panel_top))
            status, hint = status_lines()
            status_font, status = fitted(status, (self.text_font, self.small_font))
            hint_font, hint = fitted(hint, (self.small_font,))
            seconds = int(time.monotonic() - started)
            for label, font, color, y in (
                    ("Joining Game", self.title_font, WHITE, center_y - 120),
                    (status, status_font, WHITE, center_y - 45),
                    (hint, hint_font, CONNECTING_HINT_COLOR, center_y - 5),
                    (f"{seconds} s", self.small_font, CONNECTING_HINT_COLOR, center_y + 32)):
                if label:
                    surface = text(label, font, color)
                    self.screen.blit(surface, surface.get_rect(center=(center_x, y)))
            # Main-menu style button: hover highlight + click flash
            self._draw_join_screen_button(
                cancel_rect, "Cancel", WHITE,
                cancel_rect.collidepoint(pygame.mouse.get_pos()), cancel_clicked)
            draw_custom_cursor(self.screen)
            pygame.display.flip()

        clock = pygame.time.Clock()
        while worker.is_alive():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    # Alt+F4: stop joining and tell the caller to exit the entire app
                    cancel()
                    return 'quit'
                if event.type == _MUSIC_END_EVENT:
                    _music_manager.handle_music_end_event()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    cancel()
                    return 'cancelled'
                if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                        and cancel_rect.collidepoint(event.pos)):
                    sound_manager.play_ui_click()
                    cancel()
                    draw(cancel_clicked=True)     # one frame of click flash
                    return 'cancelled'

            # Steam keeps working meanwhile (overlay, invites)
            steam_manager.run_callbacks()
            draw()
            clock.tick(menu_frame_cap())

        worker.join()
        return result.get('connected', False)

    def _steam_friends_available(self) -> bool:
        """
        Whether the Join Game screen shows the Steam Friends tab: Steam is running and
        friends' rich presence can be read (steam_networking). Hidden without Steam.
        """
        try:
            from steam_networking import steam_net
            return bool(steam_manager.can_invite() and steam_net.available)
        except Exception:
            return False

    def _join_screen_layout(self, steam_tabs: bool) -> Dict:
        """
        Geometry of the Join Game screen (fixed pixel sizes, as the rest of this screen).

        The Direct IP content sits where it always did. With the Steam Friends tab the
        title and the panel top move up JOIN_TAB_ROW_HEIGHT to make room for the tab row,
        and the friends list takes the area of the address box and its Join button.
        """
        button_width, button_height, button_spacing = 400, 70, 20
        text_bar_width = 400
        text_bar_layout_height = 80  # Layout spacing height (for positioning other elements)
        text_bar_visual_height = 400  # Visual height of TextBar.png (unsquished)
        center_x = self.width // 2

        # Vertical layout: label, text bar (layout height), join button, exit button
        # Center the group vertically with slight downward offset for title
        group_height = text_bar_layout_height + button_spacing + 2 * button_height + button_spacing
        start_y = self.height // 2 - group_height // 2 + 30

        # Layout rect (small, for positioning buttons/title relative to text bar)
        bar = pygame.Rect(center_x - text_bar_width // 2, start_y, text_bar_width, text_bar_layout_height)
        # Visual rect (large, for rendering the TextBar.png centered on layout rect)
        bar_visual = pygame.Rect(center_x - text_bar_width // 2, bar.centery - text_bar_visual_height // 2,
                                 text_bar_width, text_bar_visual_height)
        join = pygame.Rect(center_x - button_width // 2, bar.bottom + button_spacing,
                           button_width, button_height)
        exit_rect = pygame.Rect(center_x - button_width // 2, join.bottom + button_spacing,
                                button_width, button_height)

        # Panel background covering the title and every element (space above for the
        # title + label, below the Exit button); 620 wide like the selection screen
        shift = JOIN_TAB_ROW_HEIGHT if steam_tabs else 0
        panel_top = bar.top - 165 - shift
        layout = {
            'center_x': center_x,
            'bar': bar,
            'bar_visual': bar_visual,
            'join': join,
            'exit': exit_rect,
            'panel': pygame.Rect(center_x - 310, panel_top, 620, exit_rect.bottom + 90 - panel_top),
            'title_center': (center_x, bar.top - 70 - shift),
            'label_center': (center_x, bar.top - 30),
            'tabs': {},
            'list': None,
        }
        if steam_tabs:
            # Inside the panel's wooden area (its metal frame takes ~65 px a side)
            tab_w, tab_h, tab_gap = 225, 46, 10
            tab_top = bar.top - 76 - tab_h // 2
            layout['tabs'] = {
                'steam': pygame.Rect(center_x - tab_gap // 2 - tab_w, tab_top, tab_w, tab_h),
                'ip': pygame.Rect(center_x + tab_gap // 2, tab_top, tab_w, tab_h),
            }
            list_top = bar.top - 42
            layout['list'] = pygame.Rect(center_x - 235, list_top, 470, join.bottom - list_top)
        return layout

    @staticmethod
    def _friend_row_rects(list_rect, count):
        """[(row rect, Join button rect)] of the first `count` rows of the friends list."""
        rows = []
        for i in range(count):
            # 12 px on the right stay free for the scrollbar
            row = pygame.Rect(list_rect.x, list_rect.y + i * (FRIEND_ROW_HEIGHT + FRIEND_ROW_SPACING),
                              list_rect.width - 12, FRIEND_ROW_HEIGHT)
            join = pygame.Rect(row.right - 12 - 120, row.centery - 22, 120, 44)
            rows.append((row, join))
        return rows

    def _get_host_ip(self):
        """
        The Join Game screen.

        With Steam: two tabs - "Steam Friends" (shown first: friends hosting a lobby, from
        their Steam rich presence, each with a Join button) and "Direct IP" (the address
        box). Without Steam: the address box only, as it always was. Tab switches tabs.

        Uses MPSetBG.png background, OptionsMenuBG panel, TextBar.png input field, and
        main-menu-style buttons. Supports hold-to-delete backspace.

        Returns:
            The typed address (str), a FriendJoin for a friend picked on the Steam
            Friends tab or named by a Steam join request arriving meanwhile, None if
            cancelled, or 'quit' (Alt+F4)
        """
        # Initialize clipboard support for Ctrl+V paste
        try:
            pygame.scrap.init()
        except Exception:
            pass  # Non-fatal — paste just won't work

        input_text = "127.0.0.1"  # Default to localhost
        cursor_visible = True
        cursor_timer = 0

        # Backspace hold-to-delete state
        backspace_held = False
        backspace_hold_timer = 0
        backspace_initial_delay = 400  # ms before repeat starts
        backspace_repeat_rate = 50  # ms between repeated deletes

        steam_tabs = self._steam_friends_available()
        layout = self._join_screen_layout(steam_tabs)
        tab = 'steam' if steam_tabs else 'ip'
        friends = HostingFriendsList()
        row_buttons = []  # [(Join rect, friend)] as last drawn - what a click picks

        # Hover/click tracking ('join', 'exit', 'tab_<name>' or ('row', steam_id))
        hovered_btn = None
        clicked_btn = None

        clock = pygame.time.Clock()

        while True:
            dt = clock.get_time()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    # Alt+F4: signal caller to exit the entire app
                    return 'quit'

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key == pygame.K_TAB and steam_tabs:
                        tab = 'ip' if tab == 'steam' else 'steam'
                        continue
                    if tab != 'ip':
                        continue  # typing only goes to the address box
                    if event.key == pygame.K_RETURN:
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
                        if event.unicode and event.unicode in '0123456789.':
                            if len(input_text) < 15:  # Max IP length
                                input_text += event.unicode

                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_BACKSPACE:
                        backspace_held = False
                        backspace_hold_timer = 0

                if event.type == getattr(pygame, 'MOUSEWHEEL', -1) and tab == 'steam':
                    friends.scroll_by(-event.y)

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    tab_hit = next((name for name, rect in layout['tabs'].items()
                                    if rect.collidepoint(event.pos)), None)
                    if tab_hit:
                        if tab_hit != tab:
                            sound_manager.play_ui_click()
                            tab = tab_hit
                        clicked_btn = f'tab_{tab_hit}'  # flash for a frame
                    elif layout['exit'].collidepoint(event.pos):
                        sound_manager.play_ui_click()
                        return None
                    elif tab == 'ip' and layout['join'].collidepoint(event.pos):
                        sound_manager.play_ui_click()
                        return input_text if input_text else None
                    elif tab == 'steam':
                        for rect, friend in row_buttons:
                            if rect.collidepoint(event.pos):
                                sound_manager.play_ui_click()
                                return FriendJoin(friend['name'], friend['connect'])

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

            # The friends hosting right now (re-read every FRIENDS_REFRESH_SECONDS)
            if tab == 'steam':
                friends.update(time.monotonic())

            # Update hover state
            hovered_btn = self._join_screen_hover(layout, tab, row_buttons, pygame.mouse.get_pos())

            # --- Render ---
            row_buttons = self._draw_join_screen(layout, tab, input_text, cursor_visible, friends,
                                                 hovered_btn, clicked_btn)

            # Reset click flash after render
            clicked_btn = None

            draw_custom_cursor(self.screen)
            pygame.display.flip()
            # Steam callbacks every frame (see steam_manager.run_callbacks)
            steam_manager.run_callbacks()
            # A Steam join request (invite accepted / "Join Game" on a friend in Steam)
            # is joined from here at once, like a friend picked in the list
            join = steam_manager.take_join_request()
            if join is not None:
                return self._friend_join_from_request(join)
            clock.tick(menu_frame_cap())

    @staticmethod
    def _join_screen_hover(layout, tab, row_buttons, pos):
        """The Join Game screen control under the mouse (ids as in _get_host_ip), or None."""
        for name, rect in layout['tabs'].items():
            if rect.collidepoint(pos):
                return f'tab_{name}'
        if layout['exit'].collidepoint(pos):
            return 'exit'
        if tab == 'ip' and layout['join'].collidepoint(pos):
            return 'join'
        if tab == 'steam':
            for rect, friend in row_buttons:
                if rect.collidepoint(pos):
                    return ('row', friend['steam_id'])
        return None

    def _draw_join_screen(self, layout, tab, input_text, cursor_visible, friends,
                          hovered_btn=None, clicked_btn=None):
        """
        Draw one frame of the Join Game screen.

        Returns:
            [(Join button rect, friend)] of the Steam Friends rows drawn ([] on Direct IP)
        """
        # Background
        if self.background_image:
            self.screen.blit(self.background_image, (0, 0))
        else:
            self.screen.fill(BLACK)

        # Options panel background behind all elements
        panel = layout['panel']
        if self.options_panel_image:
            self.screen.blit(self._scaled(self.options_panel_image, panel.size), panel.topleft)

        # Title
        title_text = self._text(self.title_font, "Join Game", WHITE)
        self.screen.blit(title_text, title_text.get_rect(center=layout['title_center']))

        # Tabs (only with Steam)
        for name, label in (('steam', "Steam Friends"), ('ip', "Direct IP")):
            rect = layout['tabs'].get(name)
            if rect is not None:
                self._draw_join_tab(rect, label, active=(tab == name),
                                    hovered=hovered_btn == f'tab_{name}',
                                    clicked=clicked_btn == f'tab_{name}')

        row_buttons = []
        if tab == 'ip':
            # Label above text bar
            label_text = self._text(self.text_font, "Enter Host IP Address:", LIGHT_GRAY)
            self.screen.blit(label_text, label_text.get_rect(center=layout['label_center']))

            # Text bar input field using TextBar.png (visual rect, larger than layout)
            bar_visual = layout['bar_visual']
            if self.text_bar_image:
                # Offset TextBar.png down to align with input text visually
                self.screen.blit(self._scaled(self.text_bar_image, bar_visual.size),
                                 (bar_visual.x, bar_visual.y + 23))
            else:
                # Fallback: dark rect with border (use layout rect for fallback)
                pygame.draw.rect(self.screen, (20, 20, 20), layout['bar'])
                pygame.draw.rect(self.screen, WHITE, layout['bar'], 2)

            # IP text centered on the visual TextBar (not layout rect) for alignment
            text_surface = self._text(self.text_font, input_text, WHITE)
            text_render_rect = text_surface.get_rect(center=bar_visual.center)
            self.screen.blit(text_surface, text_render_rect)

            # Blinking cursor
            if cursor_visible:
                cursor_x = text_render_rect.right + 3
                cursor_y = bar_visual.centery
                pygame.draw.line(self.screen, WHITE,
                                 (cursor_x, cursor_y - 15), (cursor_x, cursor_y + 15), 2)

            # Join Game button (brass text, main menu style)
            self._draw_join_screen_button(layout['join'], "Join Game", BRASS_COLOR,
                                          hovered_btn == 'join', clicked_btn == 'join')
        else:
            row_buttons = self._draw_friend_rows(layout['list'], friends, hovered_btn, clicked_btn)

        # Exit button (white text, main menu style)
        self._draw_join_screen_button(layout['exit'], "Exit", WHITE,
                                      hovered_btn == 'exit', clicked_btn == 'exit')
        return row_buttons

    def _draw_join_tab(self, rect, label, active, hovered, clicked):
        """
        One Join Game tab: the main menu button art - the open tab as bright as the other
        buttons, with brass text and a brass underline; the other one dimmed - with the
        hover highlight and click flash of every button here.
        """
        if clicked:
            state = 'click'
        elif active:
            state = 'hover' if hovered else 'normal'
        else:
            state = 'dim_hover' if hovered else 'dim'
        surface = self._button_surface(rect.size, state)
        if surface is not None:
            self.screen.blit(surface, rect)
        else:
            shade = {'click': 120, 'hover': 90, 'normal': 75, 'dim_hover': 60}.get(state, 45)
            pygame.draw.rect(self.screen, (shade, shade, shade + 15), rect, border_radius=10)
            pygame.draw.rect(self.screen, BRASS_COLOR if active else GRAY, rect, 2, border_radius=10)
        text = self._text(self.list_font, label, BRASS_COLOR if active else LIGHT_GRAY)
        text_rect = text.get_rect(center=rect.center)
        self.screen.blit(text, text_rect)
        if active:
            pygame.draw.line(self.screen, BRASS_COLOR, (text_rect.left, text_rect.bottom - 2),
                             (text_rect.right, text_rect.bottom - 2), 2)

    def _draw_friend_rows(self, list_rect, friends, hovered_btn=None, clicked_btn=None):
        """
        The Steam Friends tab: one row per friend hosting a lobby (name, their status,
        Join), a scrollbar when there are more than FRIEND_ROWS_VISIBLE, or the hint that
        nobody is hosting.

        Returns:
            [(Join button rect, friend)] as drawn
        """
        visible = friends.visible()
        if not visible:
            # The hint on a dark box like a row's, in the parchment colour the Connecting
            # screen uses for secondary text (grey was too faint on the light wood)
            lines = self._wrap_text(NO_FRIENDS_HOSTING, self.small_font, list_rect.width - 60)
            line_height = self.small_font.get_linesize()
            box = pygame.Rect(0, 0, list_rect.width - 12, len(lines) * line_height + 36)
            box.center = list_rect.center
            self.screen.blit(self._row_background(box.size), box.topleft)
            y = box.centery - len(lines) * line_height // 2
            for line in lines:
                text = self._text(self.small_font, line, CONNECTING_HINT_COLOR)
                self.screen.blit(text, text.get_rect(centerx=box.centerx, y=y))
                y += line_height
            return []

        row_buttons = []
        for friend, (row, join) in zip(visible, self._friend_row_rects(list_rect, len(visible))):
            self.screen.blit(self._row_background(row.size), row.topleft)
            text_width = join.left - row.x - 28
            name = self._text(self.list_font, self._fit_text(self.list_font, friend['name'], text_width), WHITE)
            status = self._text(self.status_font, self._fit_text(
                self.status_font, friend.get('status') or "Hosting a lobby", text_width), LIGHT_GRAY)
            text_top = row.centery - (name.get_height() + status.get_height()) // 2
            self.screen.blit(name, (row.x + 16, text_top))
            self.screen.blit(status, (row.x + 16, text_top + name.get_height()))
            key = ('row', friend['steam_id'])
            self._draw_join_screen_button(join, "Join", BRASS_COLOR, hovered_btn == key,
                                          clicked_btn == key)
            row_buttons.append((join, friend))

        # Scrollbar when the list is longer than the rows shown
        if friends.max_scroll():
            track = pygame.Rect(list_rect.right - 6, list_rect.y, 4,
                                FRIEND_ROWS_VISIBLE * (FRIEND_ROW_HEIGHT + FRIEND_ROW_SPACING)
                                - FRIEND_ROW_SPACING)
            pygame.draw.rect(self.screen, DARK_GRAY, track, border_radius=2)
            thumb_height = max(16, track.height * FRIEND_ROWS_VISIBLE // len(friends.friends))
            thumb_y = track.y + (track.height - thumb_height) * friends.scroll // friends.max_scroll()
            pygame.draw.rect(self.screen, BRASS_COLOR, (track.x, thumb_y, track.width, thumb_height),
                             border_radius=2)
        return row_buttons

    def _row_background(self, size):
        """A friend row's dark, brass-edged background (cached per size)."""
        key = ('friend_row', size)
        surface = self._surface_cache.get(key)
        if surface is None:
            surface = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(surface, (15, 12, 8, 170), surface.get_rect(), border_radius=8)
            pygame.draw.rect(surface, BRASS_COLOR, surface.get_rect(), 1, border_radius=8)
            self._surface_cache[key] = surface
        return surface

    @staticmethod
    def _fit_text(font, text, max_width):
        """`text`, shortened with '...' if it is wider than max_width (long Steam names)."""
        if font.size(text)[0] <= max_width:
            return text
        while text and font.size(text + '...')[0] > max_width:
            text = text[:-1]
        return text.rstrip() + '...'

    def _button_surface(self, size, state='normal'):
        """
        MainMenuButtonNew scaled to `size` and darkened like the main menu, with the
        highlight of `state` ('normal' / 'hover' / 'click'; 'dim' / 'dim_hover' = darker,
        for a tab that is not open); cached. None without the art.
        """
        if not self.button_bg_image:
            return None
        key = ('button', tuple(size), state)
        surface = self._surface_cache.get(key)
        if surface is None:
            # smoothscale makes a new surface, so it can be tinted in place
            surface = pygame.transform.smoothscale(self.button_bg_image, tuple(size))
            # Base darkening (matching main menu; a closed tab darker still)
            base = 70 if state.startswith('dim') else 100
            surface.fill((base, base, base, 255), special_flags=pygame.BLEND_RGBA_MULT)
            # Click flash / hover highlight
            add = {'hover': 40, 'click': 80, 'dim_hover': 30}.get(state, 0)
            if add:
                surface.fill((add, add, add, 0), special_flags=pygame.BLEND_RGB_ADD)
            self._surface_cache[key] = surface
        return surface

    def _scaled(self, image, size):
        """`image` smooth-scaled to `size` (cached - not a new surface every frame)."""
        key = ('scaled', id(image), tuple(size))
        surface = self._surface_cache.get(key)
        if surface is None:
            surface = pygame.transform.smoothscale(image, tuple(size))
            self._surface_cache[key] = surface
        return surface

    def _text(self, font, text, color):
        """`text` rendered in `font` and `color` (cached; dropped wholesale when large)."""
        key = (id(font), text, color)
        surface = self._text_cache.get(key)
        if surface is None:
            if len(self._text_cache) > 256:
                self._text_cache.clear()  # typed addresses add up
            surface = font.render(text, True, color)
            self._text_cache[key] = surface
        return surface

    def _draw_join_screen_button(self, rect, text, text_color, is_hovered, is_clicked):
        """Draw a button on the join screen with main menu styling.

        Reuses the same visual style as the selection screen buttons.
        """
        surface = self._button_surface(rect.size, 'click' if is_clicked else
                                       'hover' if is_hovered else 'normal')
        if surface is not None:
            self.screen.blit(surface, rect)
        else:
            if is_clicked:
                bg_color = (100, 100, 120)
            elif is_hovered:
                bg_color = (80, 80, 100)
            else:
                bg_color = DARK_GRAY
            pygame.draw.rect(self.screen, bg_color, rect, border_radius=10)
            pygame.draw.rect(self.screen, GRAY, rect, 3, border_radius=10)

        button_text = self._text(self.button_font, text, text_color)
        self.screen.blit(button_text, button_text.get_rect(center=rect.center))

    def _build_config_from_lobby(self, lobby_state: LobbyState, victory_condition: int,
                                  taxation_level: int, turn_mode: int,
                                  neutral_armies: bool = False, randomize_bonuses: bool = False,
                                  bonus_mapping: dict = None, gold_transfer: int = 0,
                                  map_id: str = None, game_seed: int = None) -> Dict:
        """
        Build game configuration dict from LobbyState.

        Prefer build_multiplayer_config(selector), which passes everything below from
        the launched lobby.

        Args:
            lobby_state: Finalized lobby state with all players configured
            victory_condition: Victory condition index (0-2)
            taxation_level: Taxation level index (0-4)
            turn_mode: Turn mode index (0=Sequential, 1=Simultaneous)
            neutral_armies: Whether neutral armies are enabled
            randomize_bonuses: Whether territory bonuses are randomized
            bonus_mapping: Host-generated randomized bonus mapping (for client sync)
            map_id: Map the host picked (added to the config when given)
            game_seed: The host's shared random seed from LOBBY_LAUNCH. Without it a
                seed is rolled here - fine for one PC, but then every PC differs.

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
            # Read from lobby_state (not a 9th element of the selector's result tuple)
            'starting_gold': clamp_starting_gold(getattr(lobby_state, 'starting_gold', STARTING_GOLD_DEFAULT)),
            'bonus_mapping': bonus_mapping,  # Host-generated mapping for client sync
            # Seed for neutral army placement: the host's shared seed, so every PC
            # places the same garrisons (a fallback seed only when none was sent)
            'game_seed': game_seed if isinstance(game_seed, int) else int(time.time() * 1000) % (2**31),

            # Full lobby state for reference
            'lobby_state': lobby_state
        }
        if map_id:
            config['map_id'] = map_id

        return config

    @staticmethod
    def _wrap_text(text, font, max_width):
        """Word-wrap `text` into lines no wider than max_width (a single over-long word
        stays on its own line)."""
        lines, line = [], ''
        for word in text.split():
            candidate = f"{line} {word}" if line else word
            if font.size(candidate)[0] <= max_width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines or ['']

    @staticmethod
    def _error_display_ms(message: str) -> int:
        """How long the error screen stays up: long reasons (what to check, Steam's)
        long enough to be read - 3 s for a short message, up to 12 s."""
        return max(ERROR_MIN_MS, min(ERROR_MAX_MS, ERROR_MS_PER_CHAR * len(message)))

    def _show_error(self, message: str):
        """Show error message"""
        clock = pygame.time.Clock()
        showing = True
        start_time = pygame.time.get_ticks()
        shown_ms = self._error_display_ms(message)

        while showing:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                    return

            # Auto-dismiss (3 s for a short message, up to 12 s for a long one)
            if pygame.time.get_ticks() - start_time > shown_ms:
                return

            self.screen.fill(BLACK)

            error_text = self.subtitle_font.render("Error", True, RED)
            error_rect = error_text.get_rect(center=(self.width // 2, self.height // 2 - 50))
            self.screen.blit(error_text, error_rect)

            # Wrapped: connection errors now carry the host's reason and can be long
            line_y = self.height // 2 + 50
            for line in self._wrap_text(message, self.text_font, self.width - 120):
                message_text = self.text_font.render(line, True, WHITE)
                message_rect = message_text.get_rect(center=(self.width // 2, line_y))
                self.screen.blit(message_text, message_rect)
                line_y += self.text_font.get_linesize()

            inst_text = self.small_font.render("Click or press any key to continue", True, LIGHT_GRAY)
            inst_rect = inst_text.get_rect(center=(self.width // 2, self.height - 100))
            self.screen.blit(inst_text, inst_rect)

            draw_custom_cursor(self.screen)
            pygame.display.flip()
            # Steam callbacks every frame (see steam_manager.run_callbacks)
            steam_manager.run_callbacks()
            clock.tick(menu_frame_cap())
