"""
Territory selection UI for multiplayer setup.

Shows map and allows both players to select their starting territories.
Redesigned to match integrated_setup.py visual style with left panel layout.
Expanded for 2-4 player multiplayer with Type/Color/Team configuration.
"""

import pygame
from typing import Optional, Tuple, Dict, List, Any
import time
import map_data
from settings_manager import settings
from network.protocol import NetworkProtocol
from network.lobby import (
    LobbyState, LobbySlot,
    SLOT_EMPTY, SLOT_HUMAN, SLOT_AI, SLOT_DISCONNECTED,
    AI_EASY, AI_MEDIUM, AI_HARD, PLAYER_COLORS as LOBBY_PLAYER_COLORS
)
from network_config import MessageType
from config.constants import ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT
from settings_manager import settings
from global_sound import sound_manager
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

# UI colors (matching integrated_setup.py)
BRASS_COLOR = (181, 166, 66)
PARCHMENT_COLOR = (62, 54, 38)
PARCHMENT_HOVER = (72, 64, 48)
PARCHMENT_CLICK = (92, 84, 68)
TEXT_COLOR = (255, 255, 255)
TEXT_COLOR_DIM = (180, 180, 180)

# Player colors (matching game_state.py)
PLAYER_COLORS = [
    (255, 100, 100),   # Bright Red - Player 1
    (100, 150, 255),   # Bright Blue - Player 2
    (100, 255, 100),   # Bright Green - Player 3
    (255, 255, 100)    # Bright Yellow - Player 4
]

# Legacy color names
RED = PLAYER_COLORS[0]
BLUE = PLAYER_COLORS[1]
GREEN = PLAYER_COLORS[2]
YELLOW = PLAYER_COLORS[3]

PLAYER_COLOR_NAMES = ["Red", "Blue", "Green", "Yellow"]

# Slot type options for dropdown (Human is not included - it's auto-assigned when players join)
SLOT_TYPE_OPTIONS = [
    ("AI (Easy)", SLOT_AI, AI_EASY),
    ("AI (Medium)", SLOT_AI, AI_MEDIUM),
    ("AI (Hard)", SLOT_AI, AI_HARD),
    ("Empty", SLOT_EMPTY, None)
]

# Team options
TEAM_OPTIONS = ["Team 1", "Team 2", "Team 3", "Team 4"]


class TerritorySelector:
    """
    Territory selection screen for multiplayer.

    Both players select ONE territory each on the same map view.
    Styled to match integrated_setup.py with left panel / right map layout.
    """

    def __init__(self, screen, network_connection, is_host: bool, num_players: int = 4,
                 victory_condition: int = 0, taxation_level: int = 0, turn_mode: int = 0,
                 lobby_state: LobbyState = None, local_player_index: int = 0,
                 host_ip: str = None):
        """
        Initialize territory selector.

        Args:
            screen: Pygame screen surface
            network_connection: NetworkServer or NetworkClient instance
            is_host: True if this player is the host
            num_players: Max number of player slots (2-4)
            victory_condition: Initial victory condition index (0-2)
            taxation_level: Initial taxation level index (0-4)
            turn_mode: Initial turn mode index (0=Sequential, 1=Simultaneous)
            lobby_state: LobbyState instance (created if None for host)
            local_player_index: This player's slot index (0 for host, assigned for clients)
            host_ip: Host's IP address to display in lobby (host only)
        """
        self.screen = screen
        self.width, self.height = screen.get_size()
        self.network_connection = network_connection
        self.is_host = is_host
        self.num_players = num_players
        self.local_player_index = local_player_index
        self.host_ip = host_ip  # Display in lobby for host
        # Reuse the network connection's protocol so the sequence number is continuous
        # across lobby and game phases. Creating a separate instance resets seq to 0,
        # which causes the server's replay detection to reject game-phase messages.
        self.protocol = network_connection.protocol

        # Layout constants - 35% left panel, 65% right map
        self.left_panel_width = int(self.width * 0.35)
        self.border_thickness = 70  # Ornate border thickness

        # UI scale based on panel width
        self.ui_scale = self.left_panel_width / 560

        # Load fonts with Cinzel if available, fallback to default
        try:
            semibold_path = "assets/fonts/Cinzel-SemiBold.ttf"
            bold_path = "assets/fonts/Cinzel-Bold.ttf"
            regular_path = "assets/fonts/Cinzel-Regular.ttf"
            self.title_font = pygame.font.Font(semibold_path, max(24, int(36 * self.ui_scale)))
            self.text_font = pygame.font.Font(semibold_path, max(16, int(20 * self.ui_scale)))
            self.small_font = pygame.font.Font(regular_path, max(12, int(16 * self.ui_scale)))
            self.tiny_font = pygame.font.Font(regular_path, max(10, int(12 * self.ui_scale)))
            # Button fonts - Launch Game uses Bold, Return uses Regular
            self.button_font_bold = pygame.font.Font(bold_path, max(16, int(22 * self.ui_scale)))
            self.button_font_regular = pygame.font.Font(regular_path, max(16, int(22 * self.ui_scale)))
        except (FileNotFoundError, pygame.error, OSError):
            self.title_font = pygame.font.Font(None, max(36, int(48 * self.ui_scale)))
            self.text_font = pygame.font.Font(None, max(24, int(28 * self.ui_scale)))
            self.small_font = pygame.font.Font(None, max(18, int(22 * self.ui_scale)))
            self.tiny_font = pygame.font.Font(None, max(14, int(16 * self.ui_scale)))
            self.button_font_bold = pygame.font.Font(None, max(24, int(28 * self.ui_scale)))
            self.button_font_regular = pygame.font.Font(None, max(24, int(28 * self.ui_scale)))

        # Initialize or use provided LobbyState
        local_player_name = settings.get_player_name()
        if lobby_state is not None:
            self.lobby_state = lobby_state
        elif is_host:
            # Host creates lobby state
            self.lobby_state = LobbyState(host_name=local_player_name)
        else:
            # Client creates empty lobby state (will be populated from network)
            self.lobby_state = LobbyState(host_name="Host")
            # Client updates their own slot name
            client_slot = self.lobby_state.get_slot(local_player_index)
            if client_slot:
                client_slot.player_name = local_player_name
                client_slot.state = SLOT_HUMAN

        # Legacy compatibility: player_names list derived from lobby_state
        self.player_names = [slot.player_name or f"Player {i+1}"
                            for i, slot in enumerate(self.lobby_state.slots)]

        # Territory selections synced from lobby_state
        self.player_selections = [slot.territory or None
                                  for slot in self.lobby_state.slots]
        self.ready_to_start = False  # Set when host sends SETUP_COMPLETE
        self.cancelled = False  # Set when user clicks Return to Main Menu
        self.kicked = False      # Set when client is kicked by host
        self.kick_reason = ""    # Reason for kick (shown to client)

        # Client needs to wait for lobby sync before making selections
        # Host is always synced (owns the lobby state)
        self.lobby_synced = is_host

        # Host can select which slot to assign territories to (for AI slots)
        # Defaults to host's own slot, can click player rows to change
        self.selected_slot_for_territory = local_player_index if is_host else local_player_index

        # Victory condition and taxation settings (host can modify, client receives)
        self.victory_condition = victory_condition
        self.taxation_level = taxation_level
        self.turn_mode = turn_mode
        self.victory_options = ["Domination (45+)", "Capital Assault", "Total Conquest"]
        self.taxation_options = ["0% (No Tax)", "25% Tax", "50% Tax", "75% Tax", "100% Tax"]
        self.turn_mode_options = ["Sequential", "Simultaneous"]
        self.turn_mode_tooltips = {
            "Sequential": "Players take turns one at a time",
            "Simultaneous": "All players plan at once, then orders execute together"
        }

        # Selected map (host can change, synced to clients)
        self.selected_map = map_data.get_map_ids()[0] if map_data.get_map_ids() else 'avareon'

        # Map selector arrow rects and hover state
        self.arrow_up_rect = None
        self.arrow_down_rect = None
        self.hovered_arrow = None  # 'up' or 'down' or None

        # Additional options (host can modify, synced to clients)
        self.neutral_armies = False
        self.randomize_bonuses = False
        self.bonus_mapping = None  # Host-generated randomized bonus mapping for multiplayer sync

        # Additional Options overlay state
        self.overlay_open = False
        self.overlay_neutral_armies = False  # Temp checkbox state while overlay open
        self.overlay_randomize_bonuses = False  # Temp checkbox state while overlay open
        self.overlay_hovered = None  # Hovered overlay element
        self.overlay_clicked = None  # Clicked overlay element (one-frame flash)
        self.overlay_rects = {}  # Computed rects for overlay elements

        # Friend picker modal state (Steam invite — host only)
        self._show_friend_picker = False
        self._friend_list = []  # Cached online Steam friends [{steam_id, name}, ...]
        self._invited_friends = set()  # Steam IDs already invited
        self._friend_scroll_offset = 0  # Scroll position in friend list
        self._friend_picker_rects = {}  # Computed rects for friend picker elements

        # Dropdown state for game settings
        self.victory_dropdown_open = False
        self.taxation_dropdown_open = False
        self.turn_mode_dropdown_open = False

        # Per-slot dropdown state: {slot_index: 'type'|'color'|'team'|None}
        self.active_slot_dropdown: Dict[int, Optional[str]] = {}
        for i in range(num_players):
            self.active_slot_dropdown[i] = None

        # Show Borders checkbox (persisted in settings)
        self.show_borders = settings.get('show_setup_borders', False)
        self.borders_checkbox_rect = None  # Set each frame in render

        # Countdown state (for launch countdown)
        self.countdown_active = False
        self.countdown_seconds = 0

        # Initialize map, polygons, and UI elements
        self._initialize_map()
        self._load_assets()
        self._calculate_ui_layout()

        # Clickable IP address state (host only — click to copy to clipboard)
        self._ip_click_rect = None  # Set each frame in _draw_host_ip()
        self._ip_hovered = False
        self._ip_copied_timer = 0  # Countdown in ms for floating "Copied!" text
        self._ip_copied_pos = (0, 0)  # Mouse position when copy was triggered

        # Initialize pygame.scrap for clipboard copy support
        try:
            pygame.scrap.init()
        except Exception:
            pass  # Non-fatal — clipboard copy just won't work

    # Legacy properties for backwards compatibility with 2-player network mode
    @property
    def player1_selection(self):
        return self.player_selections[0]

    @player1_selection.setter
    def player1_selection(self, value):
        self.player_selections[0] = value

    @property
    def player2_selection(self):
        return self.player_selections[1] if self.num_players > 1 else None

    @player2_selection.setter
    def player2_selection(self, value):
        if self.num_players > 1:
            self.player_selections[1] = value

    def _load_assets(self):
        """Load UI assets (panel background, button images, map bars)."""
        # Load left panel background
        try:
            left_panel_original = pygame.image.load("assets/LeftPanel.png")
            self.left_panel_bg = pygame.transform.smoothscale(
                left_panel_original,
                (self.left_panel_width, self.height)
            )
        except (FileNotFoundError, pygame.error, OSError):
            self.left_panel_bg = None

        # Load button background
        try:
            self.button_bg_image = pygame.image.load('assets/MainMenuButtonNew.png').convert_alpha()
        except (FileNotFoundError, pygame.error, OSError):
            self.button_bg_image = None

        # Load top and bottom bar images for map panel (like integrated_setup)
        try:
            self.top_bar_image = pygame.image.load("assets/TopBar.jpg")
        except (FileNotFoundError, pygame.error, OSError):
            self.top_bar_image = None

        try:
            self.bottom_bar_image = pygame.image.load("assets/BottomBar.jpg")
        except (FileNotFoundError, pygame.error, OSError):
            self.bottom_bar_image = None

        # Load overlay background image for Additional Options popup
        try:
            self.overlay_bg_image = pygame.image.load('assets/InGameMenuBG.png').convert_alpha()
        except (FileNotFoundError, pygame.error, OSError):
            self.overlay_bg_image = None

    def _initialize_map(self):
        """Load and scale map with left panel layout (35% panel, 65% map).
        Supports multiple maps via map_data.load_map()."""
        import os
        map_id = self.selected_map

        # Load map data for selected map
        map_data.load_map(map_id)

        # Load map image — try map directory first, then assets/map.png for avareon
        map_image_original = None
        map_info = map_data.get_map_info(map_id)
        if map_info and map_info.get('has_background', False):
            map_dir = map_data.get_map_directory(map_id)
            map_png_path = os.path.join(map_dir, 'map.png')
            try:
                map_image_original = pygame.image.load(map_png_path).convert()
            except (FileNotFoundError, pygame.error, OSError):
                pass

        if map_image_original is None and map_id == 'avareon':
            try:
                map_image_original = pygame.image.load('assets/map.png').convert()
            except (FileNotFoundError, pygame.error, OSError):
                pass

        if map_image_original is None:
            # Dark fallback — polygon outlines drawn in _draw_map_panel
            map_image_original = pygame.Surface((ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT))
            map_image_original.fill((0, 0, 0))
            self._has_map_background = False
        else:
            self._has_map_background = True

        # Available space for map (right 65%)
        available_width = self.width - self.left_panel_width

        # Scale to fit using correct constants from config (100% like integrated_setup)
        self.scale_factor = available_width / ORIGINAL_MAP_WIDTH

        self.scaled_map_width = int(ORIGINAL_MAP_WIDTH * self.scale_factor)
        self.scaled_map_height = int(ORIGINAL_MAP_HEIGHT * self.scale_factor)

        self.map_image = pygame.transform.smoothscale(
            map_image_original,
            (self.scaled_map_width, self.scaled_map_height)
        )

        # Map offset - center horizontally, center vertically in available space
        self.map_x = self.left_panel_width + (available_width - self.scaled_map_width) // 2
        self.map_y = (self.height - self.scaled_map_height) // 2

        # Scale polygons and centers
        self.scaled_polygons = {}
        self.scaled_centers = {}

        for territory, polygon in map_data.TERRITORY_POLYGONS.items():
            self.scaled_polygons[territory] = [
                (int(x * self.scale_factor) + self.map_x,
                 int(y * self.scale_factor) + self.map_y)
                for x, y in polygon
            ]
            center = map_data.TERRITORY_CENTERS[territory]
            self.scaled_centers[territory] = (
                int(center[0] * self.scale_factor) + self.map_x,
                int(center[1] * self.scale_factor) + self.map_y
            )

        # Hovered territory
        self.hovered_territory = None

        # Top section: (◄) Name (►) — fixed width based on longest map name
        arrow_size = 16
        self._top_arrow_size = arrow_size
        self._top_row_y = 6
        gap = 10
        # Pre-compute fixed layout width using the longest map name
        longest_name = max((map_data.get_map_display_name(mid) for mid in map_data.get_map_ids()), key=len, default="")
        self._selector_fixed_width = self.text_font.size(longest_name)[0]
        total_w = arrow_size + gap + self._selector_fixed_width + gap + arrow_size
        center_x = self.map_x + self.scaled_map_width // 2
        self._selector_start_x = center_x - total_w // 2
        # Compute fixed arrow rects
        name_h = self.text_font.get_height()
        left_x = self._selector_start_x
        right_x = self._selector_start_x + arrow_size + gap + self._selector_fixed_width + gap
        self.arrow_left_rect = pygame.Rect(left_x - 4, self._top_row_y - 4, arrow_size + 8, name_h + 8)
        self.arrow_right_rect = pygame.Rect(right_x - 4, self._top_row_y - 4, arrow_size + 8, name_h + 8)
        self.map_name_click_rect = pygame.Rect(left_x + arrow_size + gap - 4, self._top_row_y - 4, self._selector_fixed_width + 8, name_h + 8)

    def change_map(self, direction):
        """Cycle to next/previous map. Only host can call this.
        direction: +1 (next) or -1 (previous)."""
        if not self.is_host:
            return

        map_ids = map_data.get_map_ids()
        if len(map_ids) <= 1:
            return

        current_idx = map_ids.index(self.selected_map) if self.selected_map in map_ids else 0
        new_idx = (current_idx + direction) % len(map_ids)
        self.selected_map = map_ids[new_idx]

        # Clear all territory selections (territories differ between maps)
        for i in range(len(self.player_selections)):
            self.player_selections[i] = None
        for slot in self.lobby_state.slots:
            slot.territory = None

        # Reinitialize map display
        self._initialize_map()

        # Sync map change to clients
        self._sync_settings_to_client()

        sound_manager.play_ui_click()

    def _calculate_ui_layout(self):
        """Calculate positions for left panel UI elements.

        Player row layout (expanded for 4-player):
        Row 1: [ColorSwatch] [PlayerName]  [KickX]
        Row 2: [Type▼] [Color▼] [Team▼] [Territory]
        """
        margin = self.border_thickness
        content_width = self.left_panel_width - 2 * margin

        # Title position
        self.title_y = int(40 * self.ui_scale)

        # Player info section - starts below title (and IP display area for host)
        # Each player gets a taller row (2-line layout)
        # Extra space for IP display when hosting
        player_section_y = int(115 * self.ui_scale) if self.is_host else int(90 * self.ui_scale)
        row_height = int(75 * self.ui_scale)  # Taller rows for 2-line layout

        self.player_rows = []
        for i in range(self.num_players):
            self.player_rows.append(pygame.Rect(
                margin, player_section_y + i * row_height,
                content_width, row_height - 5
            ))

        # Calculate dropdown dimensions within player row
        # Second line: [Type▼] [Color▼] [Team▼] [Territory]
        self.slot_dropdown_height = int(22 * self.ui_scale)
        dropdown_spacing = int(5 * self.ui_scale)
        # Type dropdown is wider, others are smaller
        type_width = int(85 * self.ui_scale)
        color_width = int(55 * self.ui_scale)
        team_width = int(55 * self.ui_scale)

        # Store dropdown rects per slot (calculated during render based on row position)
        self.slot_dropdown_widths = {
            'type': type_width,
            'color': color_width,
            'team': team_width
        }
        self.slot_dropdown_spacing = dropdown_spacing

        # Victory condition section - below player info
        settings_start_y = player_section_y + self.num_players * row_height + int(20 * self.ui_scale)
        dropdown_height = int(35 * self.ui_scale)
        label_height = int(22 * self.ui_scale)

        self.victory_label_y = settings_start_y
        self.victory_dropdown_rect = pygame.Rect(
            margin, settings_start_y + label_height,
            content_width, dropdown_height
        )

        # Taxation section - below victory
        taxation_start_y = self.victory_dropdown_rect.bottom + int(20 * self.ui_scale)
        self.taxation_label_y = taxation_start_y
        self.taxation_dropdown_rect = pygame.Rect(
            margin, taxation_start_y + label_height,
            content_width, dropdown_height
        )

        # Turn mode section - below taxation
        turn_mode_start_y = self.taxation_dropdown_rect.bottom + int(20 * self.ui_scale)
        self.turn_mode_label_y = turn_mode_start_y
        self.turn_mode_dropdown_rect = pygame.Rect(
            margin, turn_mode_start_y + label_height,
            content_width, dropdown_height
        )

        # Additional Options button — anchored below Turn Mode dropdown
        button_height = int(45 * self.ui_scale)
        button_spacing = int(12 * self.ui_scale)
        options_btn_y = self.turn_mode_dropdown_rect.bottom + int(20 * self.ui_scale)
        self.additional_options_rect = pygame.Rect(
            margin, options_btn_y, content_width, button_height
        )

        # Bottom buttons — stacked downward from Additional Options
        # Invite Friend (host only, below Additional Options)
        if self.is_host:
            invite_y = self.additional_options_rect.bottom + button_spacing
            self.invite_button_rect = pygame.Rect(
                margin, invite_y, content_width, button_height
            )
            next_top = self.invite_button_rect.bottom + button_spacing
        else:
            self.invite_button_rect = None
            next_top = self.additional_options_rect.bottom + button_spacing

        # Launch Game (below Invite Friend / Additional Options)
        self.launch_button_rect = pygame.Rect(
            margin, next_top, content_width, button_height
        )
        # Return to Main Menu (below Launch Game)
        self.return_button_rect = pygame.Rect(
            margin, self.launch_button_rect.bottom + button_spacing,
            content_width, button_height
        )

    def run(self) -> Optional[Tuple[LobbyState, int, int, int]]:
        """
        Run territory selection.

        Returns:
            Tuple of (lobby_state, victory_condition, taxation_level, turn_mode), or None if cancelled.
            The lobby_state contains all player slots with territories, colors, teams.
        """
        clock = pygame.time.Clock()
        running = True

        # Host sends initial lobby state and settings when selector starts
        if self.is_host:
            self._sync_settings_to_client()
            self._broadcast_lobby_state()

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
                        # Close friend picker or overlay first, otherwise exit selector
                        if self._show_friend_picker:
                            self._show_friend_picker = False
                        elif self.overlay_open:
                            self.overlay_open = False
                        else:
                            return None

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        self.handle_click(event.pos)
                    # Mouse wheel scroll for friend picker
                    elif event.button in (4, 5) and self._show_friend_picker:
                        scroll_dir = -1 if event.button == 4 else 1
                        self._friend_scroll_offset = max(0, self._friend_scroll_offset + scroll_dir)

                # MOUSEWHEEL event (SDL2 — preferred over button 4/5)
                if hasattr(pygame, 'MOUSEWHEEL') and event.type == pygame.MOUSEWHEEL:
                    if self._show_friend_picker:
                        self._friend_scroll_offset = max(0, self._friend_scroll_offset - event.y)

                if event.type == pygame.MOUSEMOTION:
                    self.handle_hover(event.pos)

            # Process network messages
            self._process_network_messages()

            # Check if cancelled (Return to Main Menu clicked)
            if self.cancelled:
                return None

            # Check if kicked by host (client only)
            if self.kicked:
                # Return special value indicating kicked - multiplayer_setup will show message
                return ('kicked', self.kick_reason)

            # Check for network disconnection (client only - host disconnect ends lobby)
            if not self.is_host:
                if hasattr(self.network_connection, 'disconnected') and self.network_connection.disconnected:
                    logger.warning("Host disconnected - returning to multiplayer setup")
                    return None

            # Check if ready to start
            if self.ready_to_start:
                # Return lobby_state, settings, additional options, and bonus mapping
                return (self.lobby_state, self.victory_condition, self.taxation_level, self.turn_mode,
                        self.neutral_armies, self.randomize_bonuses, self.bonus_mapping)

            # Tick down "Copied!" feedback timer
            dt = clock.get_time()
            if self._ip_copied_timer > 0:
                self._ip_copied_timer = max(0, self._ip_copied_timer - dt)

            # Render
            self.render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()
            # Reset overlay click flash after frame
            self.overlay_clicked = None
            clock.tick(60)

        return None

    def get_player_territories(self) -> Dict[int, str]:
        """Get mapping of player index -> territory for active players."""
        return self.lobby_state.get_player_territories()

    def get_player_teams(self) -> Dict[int, int]:
        """Get mapping of player index -> team for active players."""
        return self.lobby_state.get_player_teams()

    def handle_click(self, pos):
        """Handle mouse click."""
        # Route clicks to friend picker modal while it's open
        if self._show_friend_picker:
            self._handle_friend_picker_click(pos)
            return

        # Route clicks to overlay handler while overlay is open
        if self.overlay_open:
            self._handle_overlay_click(pos)
            return

        # Check map selector arrow/name clicks (host only)
        if self.is_host and len(map_data.get_map_ids()) > 1:
            if self.arrow_left_rect and self.arrow_left_rect.collidepoint(pos):
                self.change_map(-1)
                return
            if self.arrow_right_rect and self.arrow_right_rect.collidepoint(pos):
                self.change_map(1)
                return
            if self.map_name_click_rect and self.map_name_click_rect.collidepoint(pos):
                self.change_map(1)
                return

        # Check Show Borders checkbox click
        if self.borders_checkbox_rect and self.borders_checkbox_rect.collidepoint(pos):
            self.show_borders = not self.show_borders
            settings.set('show_setup_borders', self.show_borders)
            settings.save()
            sound_manager.play_ui_click()
            return

        # Check if host clicked on the IP address to copy to clipboard
        if self.is_host and self._ip_click_rect and self._ip_click_rect.collidepoint(pos):
            server = self.network_connection
            display_ip = server.get_display_ip() if hasattr(server, 'get_display_ip') else self.host_ip
            if display_ip:
                try:
                    pygame.scrap.put(pygame.SCRAP_TEXT, display_ip.encode('utf-8'))
                    self._ip_copied_timer = 750  # Floating text fades over 0.75s
                    self._ip_copied_pos = pos  # Anchor at click position
                except Exception:
                    pass  # Clipboard not available
            return

        # Check for open slot dropdowns first
        any_slot_dropdown_open = any(v is not None for v in self.active_slot_dropdown.values())
        if any_slot_dropdown_open:
            if not self._handle_slot_dropdown_click(pos):
                # Close all slot dropdowns
                for k in self.active_slot_dropdown:
                    self.active_slot_dropdown[k] = None
            return

        # Close game settings dropdowns if clicking outside
        if self.victory_dropdown_open or self.taxation_dropdown_open or self.turn_mode_dropdown_open:
            if not self._handle_dropdown_click(pos):
                self.victory_dropdown_open = False
                self.taxation_dropdown_open = False
                self.turn_mode_dropdown_open = False
            return

        # Check if Invite Friend button clicked (host only)
        if self.is_host and self.invite_button_rect and self.invite_button_rect.collidepoint(pos):
            from steam_integration import steam_manager
            if steam_manager.can_invite():
                sound_manager.play_ui_click()
                # Refresh friend list and open picker modal
                self._friend_list = steam_manager.get_online_friends()
                self._friend_scroll_offset = 0
                self._show_friend_picker = True
            return

        # Check if Launch Game button clicked
        if self.launch_button_rect.collidepoint(pos):
            sound_manager.play_ui_click()
            if self._can_launch() and self.is_host:
                self._launch_game()
            return

        # Check if Return to Main Menu button clicked
        if self.return_button_rect.collidepoint(pos):
            sound_manager.play_ui_click()
            # Set cancelled flag to exit the lobby
            self.cancelled = True
            return

        # Check kick button clicks (host only) - before row clicks
        if self.is_host and hasattr(self, 'kick_button_rects'):
            for slot_idx, kick_rect in self.kick_button_rects.items():
                if kick_rect.collidepoint(pos):
                    sound_manager.play_ui_click()
                    self._kick_player(slot_idx)
                    return

        # Check slot dropdown clicks (Type/Color/Team) - before row clicks
        if self._check_slot_dropdown_click(pos):
            return

        # Check if host clicked on a player row to select slot for territory assignment
        # This comes AFTER dropdown checks so dropdowns within rows still work
        if self.is_host:
            for i, row_rect in enumerate(self.player_rows):
                if row_rect.collidepoint(pos):
                    # Only allow selecting active (non-empty) slots
                    slot = self.lobby_state.get_slot(i)
                    if slot and slot.is_active():
                        sound_manager.play_ui_click()
                        self.selected_slot_for_territory = i
                        logger.debug(f"Selected slot {i + 1} for territory assignment")
                    return

        # Check game settings dropdown clicks (host only)
        if self.is_host:
            if self.victory_dropdown_rect.collidepoint(pos):
                sound_manager.play_ui_click()
                self.victory_dropdown_open = not self.victory_dropdown_open
                self.taxation_dropdown_open = False
                self.turn_mode_dropdown_open = False
                return
            if self.taxation_dropdown_rect.collidepoint(pos):
                sound_manager.play_ui_click()
                self.taxation_dropdown_open = not self.taxation_dropdown_open
                self.victory_dropdown_open = False
                self.turn_mode_dropdown_open = False
                return
            if self.turn_mode_dropdown_rect.collidepoint(pos):
                sound_manager.play_ui_click()
                self.turn_mode_dropdown_open = not self.turn_mode_dropdown_open
                self.victory_dropdown_open = False
                self.taxation_dropdown_open = False
                return

            # Additional Options button (host only)
            if self.additional_options_rect.collidepoint(pos):
                sound_manager.play_ui_click()
                # Copy current values to temp overlay state
                self.overlay_neutral_armies = self.neutral_armies
                self.overlay_randomize_bonuses = self.randomize_bonuses
                self.overlay_open = True
                return

        # Check if clicked on map (right side)
        if pos[0] >= self.left_panel_width:
            clicked_territory = self.get_territory_at_pos(pos)
            if clicked_territory:
                sound_manager.play_ui_click()
                self.select_territory(clicked_territory)

    def _check_slot_dropdown_click(self, pos) -> bool:
        """Check if a slot dropdown was clicked and open it. Returns True if handled."""
        # Check Type dropdowns
        if hasattr(self, 'slot_type_rects'):
            for slot_idx, rect in self.slot_type_rects.items():
                if rect.collidepoint(pos) and self._can_edit_slot_dropdown(slot_idx, 'type'):
                    sound_manager.play_ui_click()
                    # Toggle this dropdown, close others
                    for k in self.active_slot_dropdown:
                        self.active_slot_dropdown[k] = None
                    self.active_slot_dropdown[slot_idx] = 'type'
                    return True

        # Check Color dropdowns
        if hasattr(self, 'slot_color_rects'):
            for slot_idx, rect in self.slot_color_rects.items():
                if rect.collidepoint(pos) and self._can_edit_slot_dropdown(slot_idx, 'color'):
                    sound_manager.play_ui_click()
                    for k in self.active_slot_dropdown:
                        self.active_slot_dropdown[k] = None
                    self.active_slot_dropdown[slot_idx] = 'color'
                    return True

        # Check Team dropdowns
        if hasattr(self, 'slot_team_rects'):
            for slot_idx, rect in self.slot_team_rects.items():
                if rect.collidepoint(pos) and self._can_edit_slot_dropdown(slot_idx, 'team'):
                    sound_manager.play_ui_click()
                    for k in self.active_slot_dropdown:
                        self.active_slot_dropdown[k] = None
                    self.active_slot_dropdown[slot_idx] = 'team'
                    return True

        return False

    def _handle_slot_dropdown_click(self, pos) -> bool:
        """Handle click on open slot dropdown menu. Returns True if item clicked."""
        for slot_idx, dropdown_type in self.active_slot_dropdown.items():
            if dropdown_type is None:
                continue

            # Get the dropdown rect
            if dropdown_type == 'type' and hasattr(self, 'slot_type_rects'):
                base_rect = self.slot_type_rects.get(slot_idx)
                options = SLOT_TYPE_OPTIONS
            elif dropdown_type == 'color' and hasattr(self, 'slot_color_rects'):
                base_rect = self.slot_color_rects.get(slot_idx)
                options = [(name, i, None) for i, name in enumerate(PLAYER_COLOR_NAMES)]
            elif dropdown_type == 'team' and hasattr(self, 'slot_team_rects'):
                base_rect = self.slot_team_rects.get(slot_idx)
                options = [(name, i, None) for i, name in enumerate(TEAM_OPTIONS)]
            else:
                continue

            if base_rect is None:
                continue

            # Calculate menu rect
            item_height = int(20 * self.ui_scale)
            menu_rect = pygame.Rect(
                base_rect.x,
                base_rect.bottom,
                base_rect.width + int(20 * self.ui_scale),  # Slightly wider for menu
                len(options) * item_height
            )

            if menu_rect.collidepoint(pos):
                index = (pos[1] - menu_rect.y) // item_height
                if 0 <= index < len(options):
                    # For color dropdown, check if color is available
                    if dropdown_type == 'color':
                        used_colors = self._get_used_colors(exclude_slot_idx=slot_idx)
                        if index in used_colors:
                            # Color is already used, don't allow selection
                            return True  # Still consume the click
                    sound_manager.play_ui_click()
                    self._apply_slot_dropdown_selection(slot_idx, dropdown_type, options[index])
                    self.active_slot_dropdown[slot_idx] = None
                    return True

        return False

    def _get_used_colors(self, exclude_slot_idx: int = -1) -> set:
        """Get set of color indices used by active players (excluding a specific slot).

        Args:
            exclude_slot_idx: Slot index to exclude from the check (-1 for none)

        Returns:
            Set of color indices that are already in use
        """
        used_colors = set()
        for i, slot in enumerate(self.lobby_state.slots):
            if i != exclude_slot_idx and slot.is_active():
                used_colors.add(slot.color)
        return used_colors

    def _apply_slot_dropdown_selection(self, slot_idx: int, dropdown_type: str, option: tuple):
        """Apply a slot dropdown selection and send network update."""
        slot = self.lobby_state.get_slot(slot_idx)
        if slot is None:
            return

        if dropdown_type == 'type':
            # option = (display_name, state, ai_difficulty)
            _, new_state, ai_diff = option
            old_state = slot.state
            if new_state == SLOT_EMPTY:
                self.lobby_state.set_slot_empty(slot_idx)
                # Unreserve slot so human clients can join
                if self.is_host and hasattr(self.network_connection, 'unreserve_slot'):
                    self.network_connection.unreserve_slot(slot_idx)
            elif new_state == SLOT_AI:
                self.lobby_state.set_slot_ai(slot_idx, ai_diff if ai_diff is not None else AI_MEDIUM)
                # Reserve slot so no human client gets assigned to it
                if self.is_host and hasattr(self.network_connection, 'reserve_slot'):
                    self.network_connection.reserve_slot(slot_idx)
            # Note: Can't set to human via dropdown (only happens on player join)

        elif dropdown_type == 'color':
            # option = (color_name, color_index, None)
            _, color_idx, _ = option
            # Check if this color is already used by another active player
            used_colors = self._get_used_colors(exclude_slot_idx=slot_idx)
            if color_idx in used_colors:
                logger.warning(f"Color {PLAYER_COLOR_NAMES[color_idx]} is already in use")
                return  # Don't apply the change
            self.lobby_state.set_player_color(slot_idx, color_idx)

        elif dropdown_type == 'team':
            # option = (team_name, team_index, None)
            _, team_idx, _ = option
            self.lobby_state.set_player_team(slot_idx, team_idx)

        # Sync player_selections from lobby_state
        self._sync_from_lobby_state()

        # Send network update
        self._send_slot_update(slot_idx)

    def _send_slot_update(self, slot_idx: int):
        """Send a slot update message over the network."""
        slot = self.lobby_state.get_slot(slot_idx)
        if slot is None:
            return

        slot_data = {
            'state': slot.state,
            'color': slot.color,
            'team': slot.team,
            'ai_difficulty': slot.ai_difficulty,
            'territory': slot.territory
        }

        message = self.protocol.create_lobby_slot_update(slot_idx, slot_data)
        if self.is_host:
            # Host broadcasts to all clients
            self.network_connection.broadcast_message(message)
        else:
            # Client sends to host
            self.network_connection.send_message(message)

    def _kick_player(self, slot_idx: int):
        """Host kicks a player from the lobby."""
        if not self.is_host or slot_idx == 0:
            return

        slot = self.lobby_state.get_slot(slot_idx)
        if slot is None or slot.state != SLOT_HUMAN:
            return

        player_name = slot.player_name
        logger.info(f"Kicking player {player_name} from slot {slot_idx + 1}")

        # Use server's kick_player method to send message AND disconnect the client
        self.network_connection.kick_player(slot_idx, "Kicked by host")

        # Remove player from lobby (this also clears their territory)
        self.lobby_state.remove_player(slot_idx)

        # Sync host's local UI to reflect the removal (clear territory display)
        self._sync_from_lobby_state()

        # Broadcast updated lobby state to remaining clients
        self._broadcast_lobby_state()

    def _broadcast_lobby_state(self):
        """Host broadcasts full lobby state to all clients."""
        if not self.is_host:
            return

        message = self.protocol.create_lobby_state(
            [slot.to_dict() for slot in self.lobby_state.slots],
            self.lobby_state.get_settings()
        )
        self.network_connection.broadcast_message(message)

    def _sync_from_lobby_state(self):
        """Sync local display data from lobby_state."""
        self.player_names = [slot.player_name or f"Player {i+1}"
                            for i, slot in enumerate(self.lobby_state.slots)]
        self.player_selections = [slot.territory or None
                                  for slot in self.lobby_state.slots]

    def _handle_dropdown_click(self, pos) -> bool:
        """Handle clicks on open dropdown menus. Returns True if a dropdown item was clicked."""
        item_height = int(35 * self.ui_scale)

        if self.victory_dropdown_open:
            menu_rect = pygame.Rect(
                self.victory_dropdown_rect.x,
                self.victory_dropdown_rect.bottom,
                self.victory_dropdown_rect.width,
                len(self.victory_options) * item_height
            )
            if menu_rect.collidepoint(pos):
                index = (pos[1] - menu_rect.y) // item_height
                if 0 <= index < len(self.victory_options):
                    sound_manager.play_ui_click()
                    self.victory_condition = index
                    self.lobby_state.victory_condition = index  # Sync to lobby_state for broadcasts
                    self.victory_dropdown_open = False
                    self._sync_settings_to_client()
                    return True

        if self.taxation_dropdown_open:
            menu_rect = pygame.Rect(
                self.taxation_dropdown_rect.x,
                self.taxation_dropdown_rect.bottom,
                self.taxation_dropdown_rect.width,
                len(self.taxation_options) * item_height
            )
            if menu_rect.collidepoint(pos):
                index = (pos[1] - menu_rect.y) // item_height
                if 0 <= index < len(self.taxation_options):
                    sound_manager.play_ui_click()
                    self.taxation_level = index
                    self.lobby_state.taxation_level = index  # Sync to lobby_state for broadcasts
                    self.taxation_dropdown_open = False
                    self._sync_settings_to_client()
                    return True

        if self.turn_mode_dropdown_open:
            menu_rect = pygame.Rect(
                self.turn_mode_dropdown_rect.x,
                self.turn_mode_dropdown_rect.bottom,
                self.turn_mode_dropdown_rect.width,
                len(self.turn_mode_options) * item_height
            )
            if menu_rect.collidepoint(pos):
                index = (pos[1] - menu_rect.y) // item_height
                if 0 <= index < len(self.turn_mode_options):
                    sound_manager.play_ui_click()
                    self.turn_mode = index
                    self.lobby_state.turn_mode = index  # Sync to lobby_state for broadcasts
                    self.turn_mode_dropdown_open = False
                    self._sync_settings_to_client()
                    return True

        return False

    def _can_launch(self) -> bool:
        """Check if game can be launched using LobbyState validation."""
        return self.lobby_state.can_launch()

    def _launch_game(self):
        """Host launches the game."""
        if not self.is_host:
            return

        # Update lobby_state settings
        self.lobby_state.victory_condition = self.victory_condition
        self.lobby_state.taxation_level = self.taxation_level
        self.lobby_state.turn_mode = self.turn_mode
        self.lobby_state.neutral_armies = self.neutral_armies
        self.lobby_state.randomize_bonuses = self.randomize_bonuses

        # Send LOBBY_LAUNCH to all clients with final state
        final_slots = [slot.to_dict() for slot in self.lobby_state.slots]
        settings = self.lobby_state.get_settings()

        # Include map_id in launch settings for multi-map support
        settings['map_id'] = self.selected_map

        # Host generates randomized bonus mapping and includes it in launch settings
        if self.randomize_bonuses:
            import map_data
            self.bonus_mapping = map_data.randomize_territory_bonuses()
            map_data.load_territory_bonuses()  # Restore defaults; initialize_game() re-applies
            settings['bonus_mapping'] = self.bonus_mapping

        message = self.protocol.create_lobby_launch(final_slots, settings)
        self.network_connection.broadcast_message(message)

        self.ready_to_start = True
        logger.info("Launching game with all players!")

    def _sync_settings_to_client(self):
        """Host sends current victory/taxation/turn_mode settings and player name to client."""
        if not self.is_host:
            return

        message = self.protocol.encode_message(MessageType.SETUP_CONFIG, {
            'victory_condition': self.victory_condition,
            'taxation_level': self.taxation_level,
            'turn_mode': self.turn_mode,
            'host_name': self.player_names[0],  # Include host's name for client display
            'neutral_armies': self.neutral_armies,
            'randomize_bonuses': self.randomize_bonuses,
            'map_id': self.selected_map,  # Selected map for multi-map support
        })
        self.network_connection.send_message(message)

    def handle_hover(self, pos):
        """Handle mouse hover."""
        # Block normal hover while friend picker modal is open
        if self._show_friend_picker:
            self.hovered_territory = None
            return

        # Block normal hover while overlay is open
        if self.overlay_open:
            self._update_overlay_hover(pos)
            return

        # Track hover over clickable IP address (host only)
        self._ip_hovered = (self.is_host and self._ip_click_rect is not None
                            and self._ip_click_rect.collidepoint(pos))

        # Track map selector arrow hover (host only)
        self.hovered_arrow = None
        if self.is_host:
            if self.arrow_left_rect and self.arrow_left_rect.collidepoint(pos):
                self.hovered_arrow = 'left'
            elif self.arrow_right_rect and self.arrow_right_rect.collidepoint(pos):
                self.hovered_arrow = 'right'
            elif self.map_name_click_rect and self.map_name_click_rect.collidepoint(pos):
                self.hovered_arrow = 'name'

        if pos[0] >= self.left_panel_width:  # In map area
            self.hovered_territory = self.get_territory_at_pos(pos)
        else:
            self.hovered_territory = None

    def get_territory_at_pos(self, pos) -> Optional[str]:
        """Get territory name at given position."""
        for territory, polygon in self.scaled_polygons.items():
            if self.point_in_polygon(pos, polygon):
                return territory
        return None

    def point_in_polygon(self, point, polygon) -> bool:
        """Check if point is inside polygon using ray casting."""
        x, y = point
        n = len(polygon)
        inside = False

        # S2 fix: initialize xinters to avoid UnboundLocalError on horizontal edges
        xinters = 0
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    def select_territory(self, territory: str):
        """
        Select a territory for the currently selected slot.

        For host: Uses selected_slot_for_territory (can assign to AI slots)
        For client: Uses local_player_index (can only assign to own slot)

        Args:
            territory: Territory name
        """
        # Client must wait for lobby sync before selecting territories
        if not self.lobby_synced:
            logger.debug("Waiting for lobby sync before territory selection...")
            return

        # Host can assign to any selected slot, clients only to their own
        if self.is_host:
            target_player = self.selected_slot_for_territory
        else:
            target_player = self.local_player_index

        # Check if target slot is active
        slot = self.lobby_state.get_slot(target_player)
        if slot is None or not slot.is_active():
            return

        # Use lobby_state to claim territory (handles conflicts)
        timestamp = time.time()
        if self.is_host:
            # Host claims directly in lobby_state for the target slot
            if self.lobby_state.claim_territory(target_player, territory, timestamp):
                self._sync_from_lobby_state()
                # Broadcast update to all clients
                self._send_slot_update(target_player)
                logger.info(f"Player {target_player + 1} selected: {territory}")
        else:
            # Client sends claim request to host
            message = self.protocol.encode_message(MessageType.TERRITORY_SELECT, {
                'player_index': target_player,
                'territory_name': territory,
                'timestamp': timestamp,
                'player_name': self.player_names[target_player]
            })
            self.network_connection.send_message(message)
            logger.debug(f"Player {target_player + 1} requesting: {territory}")

    def _process_network_messages(self):
        """Process incoming network messages."""
        # Process ALL pending messages to ensure kick messages are handled
        # before disconnection is detected
        while True:
            msg = self.network_connection.message_queue.get_incoming_message()
            if not msg:
                break

            msg_type = msg.get('type')
            data = msg.get('data', {})

            if msg_type == MessageType.TERRITORY_SELECT:
                player_index = data.get('player_index')
                territory = data.get('territory_name')
                player_name = data.get('player_name')
                timestamp = data.get('timestamp', time.time())

                if self.is_host:
                    # Host processes territory claim
                    if self.lobby_state.claim_territory(player_index, territory, timestamp):
                        # Update player name if provided
                        slot = self.lobby_state.get_slot(player_index)
                        if slot and player_name:
                            slot.player_name = player_name
                        self._sync_from_lobby_state()
                        # Broadcast update to all clients
                        self._send_slot_update(player_index)
                        logger.info(f"Player {player_index + 1} claimed: {territory}")
                else:
                    # Client receives territory update
                    if 0 <= player_index < self.num_players:
                        slot = self.lobby_state.get_slot(player_index)
                        if slot:
                            slot.territory = territory
                            if player_name:
                                slot.player_name = player_name
                        self._sync_from_lobby_state()
                        logger.info(f"Player {player_index + 1} selected: {territory}")

            elif msg_type == MessageType.LOBBY_STATE:
                # Full lobby state sync (client receives from host)
                if not self.is_host:
                    # Store old player name before update to find our new slot
                    my_name = settings.get_player_name()

                    self.lobby_state.update_from_network(data)

                    # Update settings from lobby state
                    self.victory_condition = self.lobby_state.victory_condition
                    self.taxation_level = self.lobby_state.taxation_level
                    self.turn_mode = self.lobby_state.turn_mode
                    self.neutral_armies = self.lobby_state.neutral_armies
                    self.randomize_bonuses = self.lobby_state.randomize_bonuses

                    # Find our slot by name (host may have reassigned us)
                    # Skip slot 0 (host) - client is never the host
                    # Also handle case where host and client have the same name
                    found_slot = False
                    for slot in self.lobby_state.slots:
                        # Skip host slot - client can never be index 0
                        if slot.index == 0:
                            continue
                        if slot.state == SLOT_HUMAN and slot.player_name == my_name:
                            if slot.index != self.local_player_index:
                                logger.info(f"Reassigned from slot {self.local_player_index + 1} to slot {slot.index + 1}")
                                self.local_player_index = slot.index
                                self.selected_slot_for_territory = slot.index
                            found_slot = True
                            break

                    if not found_slot:
                        logger.warning(f"Could not find our slot by name '{my_name}', keeping index {self.local_player_index + 1}")

                    self._sync_from_lobby_state()
                    self.lobby_synced = True  # Client is now synced with host
                    logger.info(f"Received full lobby state sync (settings: Victory={self.victory_options[self.victory_condition]}, Tax={self.taxation_options[self.taxation_level]}, Mode={self.turn_mode_options[self.turn_mode]})")

            elif msg_type == MessageType.LOBBY_SLOT_UPDATE:
                # Single slot update
                player_index = data.get('player_index')
                if 0 <= player_index < self.num_players:
                    slot = self.lobby_state.get_slot(player_index)
                    if slot:
                        if 'state' in data:
                            slot.state = data['state']
                        if 'color' in data:
                            slot.color = data['color']
                        if 'team' in data:
                            slot.team = data['team']
                        if 'ai_difficulty' in data:
                            slot.ai_difficulty = data['ai_difficulty']
                        if 'territory' in data:
                            slot.territory = data['territory']
                        if 'player_name' in data:
                            slot.player_name = data['player_name']
                    self._sync_from_lobby_state()

                    # If host received this, broadcast to other clients
                    if self.is_host:
                        self._broadcast_lobby_state()

            elif msg_type == MessageType.LOBBY_JOIN:
                # New player joined
                server_assigned_index = data.get('player_index')
                player_name = data.get('player_name', f"Player {server_assigned_index + 1}")

                if self.is_host:
                    # HOST: Find the first EMPTY slot for the new player
                    # Don't overwrite AI slots - find an empty one
                    target_slot_index = None
                    for i in range(self.num_players):
                        slot = self.lobby_state.get_slot(i)
                        if slot and slot.state == SLOT_EMPTY:
                            target_slot_index = i
                            break

                    if target_slot_index is None:
                        logger.warning(f"No empty slots for {player_name}!")
                        # TODO: Could kick the player here
                    else:
                        slot = self.lobby_state.get_slot(target_slot_index)
                        if slot:
                            slot.state = SLOT_HUMAN
                            slot.player_name = player_name
                        self._sync_from_lobby_state()
                        logger.info(f"Player {player_name} joined slot {target_slot_index + 1}")

                        # Send full lobby state to the new client so they see everything
                        self._broadcast_lobby_state()
                else:
                    # CLIENT: Just update the slot as indicated by host
                    if 0 <= server_assigned_index < self.num_players:
                        slot = self.lobby_state.get_slot(server_assigned_index)
                        if slot:
                            slot.state = SLOT_HUMAN
                            slot.player_name = player_name
                        self._sync_from_lobby_state()
                        logger.info(f"Player {player_name} joined slot {server_assigned_index + 1}")

            elif msg_type == MessageType.LOBBY_LEAVE:
                # Player left (host broadcasts this)
                player_index = data.get('player_index')
                if 0 <= player_index < self.num_players:
                    self.lobby_state.remove_player(player_index)
                    self._sync_from_lobby_state()
                    logger.info(f"Player left slot {player_index + 1}")

            elif msg_type == MessageType.LOBBY_KICK:
                # Client received kick notification
                if not self.is_host:
                    kicked_index = data.get('player_index')
                    if kicked_index == self.local_player_index:
                        reason = data.get('reason', 'Kicked by host')
                        logger.warning(f"You have been kicked from the lobby: {reason}")
                        self.kicked = True
                        self.kick_reason = reason
                        # run() loop will check this flag and exit properly
                        return

            elif msg_type == MessageType.LOBBY_COUNTDOWN:
                # Launch countdown update
                self.countdown_active = True
                self.countdown_seconds = data.get('seconds_remaining', 0)
                if self.countdown_seconds <= 0:
                    self.countdown_active = False

            elif msg_type == MessageType.LOBBY_LAUNCH:
                # Game starting - update final state and signal ready
                if 'slots' in data:
                    for slot_data in data['slots']:
                        idx = slot_data.get('index', -1)
                        slot = self.lobby_state.get_slot(idx)
                        if slot:
                            slot.territory = slot_data.get('territory', slot.territory)
                            slot.color = slot_data.get('color', slot.color)
                            slot.team = slot_data.get('team', slot.team)
                if 'settings' in data:
                    self.lobby_state.set_settings(data['settings'])
                    self.victory_condition = self.lobby_state.victory_condition
                    self.taxation_level = self.lobby_state.taxation_level
                    self.turn_mode = self.lobby_state.turn_mode
                    self.neutral_armies = self.lobby_state.neutral_armies
                    self.randomize_bonuses = self.lobby_state.randomize_bonuses
                    # Extract host-generated bonus mapping for randomized bonuses
                    if 'bonus_mapping' in data['settings']:
                        self.bonus_mapping = data['settings']['bonus_mapping']
                    # Extract map_id for multi-map support
                    if 'map_id' in data['settings']:
                        new_map_id = data['settings']['map_id']
                        if new_map_id != self.selected_map:
                            self.selected_map = new_map_id
                            map_data.load_map(new_map_id)
                self._sync_from_lobby_state()
                self.ready_to_start = True
                logger.info("Game launching!")

            elif msg_type == MessageType.SETUP_CONFIG:
                # Client receives settings from host (legacy compatibility)
                if not self.is_host:
                    self.victory_condition = data.get('victory_condition', 0)
                    self.taxation_level = data.get('taxation_level', 0)
                    self.turn_mode = data.get('turn_mode', 0)
                    # Update lobby_state settings
                    self.lobby_state.victory_condition = self.victory_condition
                    self.lobby_state.taxation_level = self.taxation_level
                    self.lobby_state.turn_mode = self.turn_mode
                    # Additional options
                    self.neutral_armies = data.get('neutral_armies', False)
                    self.randomize_bonuses = data.get('randomize_bonuses', False)
                    # Handle map change from host
                    new_map_id = data.get('map_id', 'avareon')
                    if new_map_id != self.selected_map:
                        self.selected_map = new_map_id
                        # Clear territory selections and reinitialize map
                        for i in range(len(self.player_selections)):
                            self.player_selections[i] = None
                        for slot in self.lobby_state.slots:
                            slot.territory = None
                        self._initialize_map()
                        logger.info(f"Map changed to '{new_map_id}' by host")
                    # Update host's player name if provided
                    if 'host_name' in data:
                        host_slot = self.lobby_state.get_slot(0)
                        if host_slot:
                            host_slot.player_name = data.get('host_name')
                    self._sync_from_lobby_state()
                    logger.info(f"Received settings: Victory={self.victory_options[self.victory_condition]}, Tax={self.taxation_options[self.taxation_level]}, Mode={self.turn_mode_options[self.turn_mode]}")

            elif msg_type == MessageType.SETUP_COMPLETE:
                # Host sent start signal (legacy 2-player compatibility)
                if 'player1_territory' in data:
                    slot0 = self.lobby_state.get_slot(0)
                    if slot0:
                        slot0.territory = data.get('player1_territory')
                if 'player2_territory' in data:
                    slot1 = self.lobby_state.get_slot(1)
                    if slot1:
                        slot1.territory = data.get('player2_territory')
                if 'victory_condition' in data:
                    self.victory_condition = data.get('victory_condition')
                    self.lobby_state.victory_condition = self.victory_condition
                if 'taxation_level' in data:
                    self.taxation_level = data.get('taxation_level')
                    self.lobby_state.taxation_level = self.taxation_level
                if 'turn_mode' in data:
                    self.turn_mode = data.get('turn_mode')
                    self.lobby_state.turn_mode = self.turn_mode
                if 'neutral_armies' in data:
                    self.neutral_armies = data.get('neutral_armies')
                    self.lobby_state.neutral_armies = self.neutral_armies
                if 'randomize_bonuses' in data:
                    self.randomize_bonuses = data.get('randomize_bonuses')
                    self.lobby_state.randomize_bonuses = self.randomize_bonuses
                self._sync_from_lobby_state()
                self.ready_to_start = True
                logger.info("Setup complete - starting game!")

    def render(self):
        """Render territory selection screen."""
        self.screen.fill(BLACK)

        # Draw left panel background
        if self.left_panel_bg:
            self.screen.blit(self.left_panel_bg, (0, 0))
        else:
            pygame.draw.rect(self.screen, (40, 40, 50), (0, 0, self.left_panel_width, self.height))

        # Draw map bars and map on right side
        self._draw_map_panel()

        # Draw territory overlays
        self._draw_territory_overlays()

        # Draw left panel UI elements
        self._draw_title()
        self._draw_host_ip()  # Show IP for host to share with players
        self._draw_player_info()
        self._draw_victory_dropdown()
        self._draw_taxation_dropdown()
        self._draw_turn_mode_dropdown()
        self._draw_buttons()

        # Draw dropdown menus (on top of everything)
        self._draw_dropdown_menus()
        self._draw_slot_dropdown_menus()

        # Draw countdown overlay if active
        if self.countdown_active and self.countdown_seconds > 0:
            self._draw_countdown_overlay()

        # Draw hovered territory name
        if self.hovered_territory:
            self._draw_hover_info()

        # Draw warning tooltip for AI slots without territories (host only)
        if self.is_host:
            self._draw_warning_tooltips()

        # Draw Additional Options overlay on top of everything (if open)
        if self.overlay_open:
            self._draw_additional_options_overlay()

        # Draw friend picker modal on top of everything (if open)
        if self._show_friend_picker:
            self._draw_friend_picker()

        # Draw floating "Copied to Clipboard!" text near mouse, fading out
        if self._ip_copied_timer > 0:
            alpha = int(255 * (self._ip_copied_timer / 750))
            copied_surf = self.small_font.render("Copied to Clipboard!", True, WHITE)
            copied_surf.set_alpha(alpha)
            # Position slightly above and to the right of click location
            cx = self._ip_copied_pos[0] + 12
            cy = self._ip_copied_pos[1] - 20
            self.screen.blit(copied_surf, (cx, cy))

        # Draw syncing indicator for clients waiting for lobby state
        if not self.is_host and not self.lobby_synced:
            self._draw_syncing_indicator()

    def _draw_syncing_indicator(self):
        """Draw a 'Syncing...' indicator for clients waiting for lobby state."""
        # Draw centered over the map area
        sync_text = self.text_font.render("Syncing with host...", True, YELLOW)
        sync_rect = sync_text.get_rect(center=(
            self.left_panel_width + (self.width - self.left_panel_width) // 2,
            self.height // 2
        ))

        # Semi-transparent background
        bg_rect = sync_rect.inflate(40, 20)
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 180))
        self.screen.blit(bg_surface, bg_rect)

        # Border and text
        pygame.draw.rect(self.screen, YELLOW, bg_rect, 2)
        self.screen.blit(sync_text, sync_rect)

    def _draw_warning_tooltips(self):
        """Draw tooltip when hovering over warning indicators for AI slots without territories."""
        if not hasattr(self, 'warning_indicator_rects'):
            return

        mouse_pos = pygame.mouse.get_pos()

        for slot_idx, warning_rect in self.warning_indicator_rects.items():
            if warning_rect.collidepoint(mouse_pos):
                # Draw tooltip box with explanation
                tooltip_text = "Starting territory unassigned. Select the AI"
                tooltip_text2 = "player's slot and then their territory on the map."

                # Calculate tooltip dimensions
                line1_surface = self.tiny_font.render(tooltip_text, True, WHITE)
                line2_surface = self.tiny_font.render(tooltip_text2, True, WHITE)

                padding = int(8 * self.ui_scale)
                tooltip_width = max(line1_surface.get_width(), line2_surface.get_width()) + padding * 2
                tooltip_height = line1_surface.get_height() + line2_surface.get_height() + padding * 2 + int(2 * self.ui_scale)

                # Position tooltip to the right of the warning indicator
                tooltip_x = warning_rect.right + int(5 * self.ui_scale)
                tooltip_y = warning_rect.centery - tooltip_height // 2

                # Keep tooltip on screen
                if tooltip_x + tooltip_width > self.left_panel_width - 10:
                    tooltip_x = warning_rect.left - tooltip_width - int(5 * self.ui_scale)
                if tooltip_y < 10:
                    tooltip_y = 10
                if tooltip_y + tooltip_height > self.height - 10:
                    tooltip_y = self.height - tooltip_height - 10

                tooltip_rect = pygame.Rect(tooltip_x, tooltip_y, tooltip_width, tooltip_height)

                # Draw tooltip background
                pygame.draw.rect(self.screen, PARCHMENT_COLOR, tooltip_rect)
                pygame.draw.rect(self.screen, (255, 180, 50), tooltip_rect, 2)  # Orange border

                # Draw tooltip text
                self.screen.blit(line1_surface, (tooltip_x + padding, tooltip_y + padding))
                self.screen.blit(line2_surface, (tooltip_x + padding, tooltip_y + padding + line1_surface.get_height() + int(2 * self.ui_scale)))

                # Only show one tooltip at a time
                break

    def _draw_slot_dropdown_menus(self):
        """Draw open slot dropdown menus (Type/Color/Team)."""
        mouse_pos = pygame.mouse.get_pos()

        for slot_idx, dropdown_type in self.active_slot_dropdown.items():
            if dropdown_type is None:
                continue

            # Get the dropdown rect and options
            if dropdown_type == 'type' and hasattr(self, 'slot_type_rects'):
                base_rect = self.slot_type_rects.get(slot_idx)
                options = [(opt[0], opt) for opt in SLOT_TYPE_OPTIONS]  # (display, full_option)
                current_slot = self.lobby_state.get_slot(slot_idx)
                current_idx = self._get_type_option_index(current_slot)
            elif dropdown_type == 'color' and hasattr(self, 'slot_color_rects'):
                base_rect = self.slot_color_rects.get(slot_idx)
                options = [(name, (name, i, None)) for i, name in enumerate(PLAYER_COLOR_NAMES)]
                current_slot = self.lobby_state.get_slot(slot_idx)
                current_idx = current_slot.color if current_slot else 0
            elif dropdown_type == 'team' and hasattr(self, 'slot_team_rects'):
                base_rect = self.slot_team_rects.get(slot_idx)
                options = [(name, (name, i, None)) for i, name in enumerate(TEAM_OPTIONS)]
                current_slot = self.lobby_state.get_slot(slot_idx)
                current_idx = current_slot.team if current_slot else 0
            else:
                continue

            if base_rect is None:
                continue

            # Draw dropdown menu
            item_height = int(20 * self.ui_scale)
            menu_width = base_rect.width + int(20 * self.ui_scale)
            menu_rect = pygame.Rect(
                base_rect.x,
                base_rect.bottom,
                menu_width,
                len(options) * item_height
            )

            # Background
            pygame.draw.rect(self.screen, PARCHMENT_COLOR, menu_rect)
            pygame.draw.rect(self.screen, BRASS_COLOR, menu_rect, 1)

            # For color dropdown, get used colors to show availability
            used_colors = set()
            if dropdown_type == 'color':
                used_colors = self._get_used_colors(exclude_slot_idx=slot_idx)

            for i, (display_text, _) in enumerate(options):
                item_rect = pygame.Rect(
                    menu_rect.x,
                    menu_rect.y + i * item_height,
                    menu_rect.width,
                    item_height
                )

                # Check if this color is unavailable (for color dropdown)
                is_unavailable = dropdown_type == 'color' and i in used_colors

                # Highlight hovered or selected (but not if unavailable)
                if is_unavailable:
                    pygame.draw.rect(self.screen, DARK_GRAY, item_rect)
                elif item_rect.collidepoint(mouse_pos):
                    pygame.draw.rect(self.screen, PARCHMENT_HOVER, item_rect)
                elif i == current_idx:
                    pygame.draw.rect(self.screen, PARCHMENT_CLICK, item_rect)

                # For color dropdown, draw color swatch instead of text
                if dropdown_type == 'color' and i < len(PLAYER_COLORS):
                    swatch_size = int(12 * self.ui_scale)
                    swatch_x = item_rect.x + 4
                    swatch_y = item_rect.centery - swatch_size // 2
                    swatch_rect = pygame.Rect(swatch_x, swatch_y, swatch_size, swatch_size)

                    # Dim the color if unavailable
                    if is_unavailable:
                        dimmed_color = tuple(c // 2 for c in PLAYER_COLORS[i])
                        pygame.draw.rect(self.screen, dimmed_color, swatch_rect)
                        pygame.draw.rect(self.screen, GRAY, swatch_rect, 1)
                        text_surface = self.tiny_font.render(display_text + " (used)", True, GRAY)
                    else:
                        pygame.draw.rect(self.screen, PLAYER_COLORS[i], swatch_rect)
                        pygame.draw.rect(self.screen, WHITE, swatch_rect, 1)
                        text_surface = self.tiny_font.render(display_text, True, WHITE)

                    text_rect = text_surface.get_rect(midleft=(swatch_rect.right + 4, item_rect.centery))
                    self.screen.blit(text_surface, text_rect)
                else:
                    # Draw text for other dropdowns
                    text_surface = self.tiny_font.render(display_text, True, WHITE)
                    text_rect = text_surface.get_rect(midleft=(item_rect.x + 4, item_rect.centery))
                    self.screen.blit(text_surface, text_rect)

    def _get_type_option_index(self, slot: LobbySlot) -> int:
        """Get the index in SLOT_TYPE_OPTIONS for a slot's current state.

        SLOT_TYPE_OPTIONS: AI Easy=0, AI Medium=1, AI Hard=2, Empty=3
        Human slots return -1 (dropdown not editable for them anyway).
        """
        if slot is None:
            return 3  # Empty
        if slot.state == SLOT_HUMAN or slot.state == SLOT_DISCONNECTED:
            return -1  # Human - dropdown not editable
        elif slot.state == SLOT_AI:
            if slot.ai_difficulty == AI_EASY:
                return 0
            elif slot.ai_difficulty == AI_MEDIUM:
                return 1
            elif slot.ai_difficulty == AI_HARD:
                return 2
            return 1  # Default to Medium
        return 3  # Empty

    def _draw_countdown_overlay(self):
        """Draw launch countdown overlay."""
        # Semi-transparent overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.screen.blit(overlay, (0, 0))

        # Countdown text
        countdown_text = self.title_font.render(f"Game starting in {self.countdown_seconds}...", True, BRASS_COLOR)
        text_rect = countdown_text.get_rect(center=(self.width // 2, self.height // 2))
        self.screen.blit(countdown_text, text_rect)

    def _draw_map_panel(self):
        """Draw map with top and bottom decorative bars (like integrated_setup)."""
        # Available width for right panel
        available_width = self.width - self.left_panel_width

        # Draw top bar (flipped 180 degrees, positioned above map)
        if self.top_bar_image:
            # Scale bar to match panel width
            bar_width = available_width
            # Maintain aspect ratio for bar height
            original_bar_width, original_bar_height = self.top_bar_image.get_size()
            bar_height = int(original_bar_height * (bar_width / original_bar_width))

            scaled_top_bar = pygame.transform.smoothscale(self.top_bar_image, (bar_width, bar_height))
            # Flip 180 degrees
            flipped_top_bar = pygame.transform.rotate(scaled_top_bar, 180)

            # Position above map (align bottom of bar with top of map)
            top_bar_x = self.left_panel_width
            top_bar_y = self.map_y - bar_height
            self.screen.blit(flipped_top_bar, (top_bar_x, top_bar_y))

        # Draw map
        self.screen.blit(self.map_image, (self.map_x, self.map_y))

        # Draw borders for all unselected territories (toggled via Show Borders checkbox)
        if self.show_borders:
            selected_set = set(s for s in self.player_selections if s)
            for territory, polygon in self.scaled_polygons.items():
                if territory not in selected_set:
                    pygame.draw.lines(self.screen, (200, 200, 200), True, polygon, 1)

        # Draw bottom bar (positioned below map)
        if self.bottom_bar_image:
            # Scale bar to match panel width
            bar_width = available_width
            original_bar_width, original_bar_height = self.bottom_bar_image.get_size()
            bar_height = int(original_bar_height * (bar_width / original_bar_width))

            scaled_bottom_bar = pygame.transform.smoothscale(self.bottom_bar_image, (bar_width, bar_height))

            # Position below map (align top of bar with bottom of map)
            bottom_bar_x = self.left_panel_width
            bottom_bar_y = self.map_y + self.scaled_map_height
            self.screen.blit(scaled_bottom_bar, (bottom_bar_x, bottom_bar_y))

        # Draw "Show Borders" checkbox in top-right of map area
        cb_label = self.tiny_font.render("Show Borders", True, BRASS_COLOR)
        cb_size = 14
        cb_x = self.width - cb_label.get_width() - cb_size - 20
        cb_y = 8
        cb_rect = pygame.Rect(cb_x, cb_y, cb_size, cb_size)
        self.borders_checkbox_rect = pygame.Rect(cb_x - 4, cb_y - 4, cb_label.get_width() + cb_size + 28, cb_size + 8)
        pygame.draw.rect(self.screen, BRASS_COLOR, cb_rect, 1)
        if self.show_borders:
            pygame.draw.line(self.screen, BRASS_COLOR, (cb_rect.left + 2, cb_rect.centery), (cb_rect.centerx, cb_rect.bottom - 2), 2)
            pygame.draw.line(self.screen, BRASS_COLOR, (cb_rect.centerx, cb_rect.bottom - 2), (cb_rect.right - 2, cb_rect.top + 2), 2)
        self.screen.blit(cb_label, (cb_x + cb_size + 6, cb_y - 1))

        # Draw map selector arrows and map name (only if multiple maps, host only can click)
        if len(map_data.get_map_ids()) > 1:
            self._draw_map_selector_arrows()

    def _draw_map_selector_arrows(self):
        """Draw (◄) Map Name (►) at top with fixed-width layout."""
        s = self._top_arrow_size
        y = self._top_row_y
        gap = 10
        start_x = self._selector_start_x
        name_h = self.text_font.get_height()

        if self.is_host:
            # Left arrow (◄)
            left_x = start_x
            left_color = (220, 200, 100) if self.hovered_arrow == 'left' else BRASS_COLOR
            pygame.draw.polygon(self.screen, left_color, [
                (left_x, y + name_h // 2),
                (left_x + s, y + name_h // 2 - s // 2),
                (left_x + s, y + name_h // 2 + s // 2),
            ])

            # Right arrow (►)
            right_x = start_x + s + gap + self._selector_fixed_width + gap
            right_color = (220, 200, 100) if self.hovered_arrow == 'right' else BRASS_COLOR
            pygame.draw.polygon(self.screen, right_color, [
                (right_x + s, y + name_h // 2),
                (right_x, y + name_h // 2 - s // 2),
                (right_x, y + name_h // 2 + s // 2),
            ])

        # Map name (centered within fixed-width area, visible for both host and client)
        display_name = map_data.get_map_display_name(self.selected_map)
        name_color = (220, 200, 100) if self.hovered_arrow == 'name' else BRASS_COLOR
        name_surface = self.text_font.render(display_name, True, name_color)
        name_area_x = start_x + s + gap
        name_x = name_area_x + (self._selector_fixed_width - name_surface.get_width()) // 2
        self.screen.blit(name_surface, (name_x, y))

    def _draw_territory_overlays(self):
        """Draw territory selection overlays on the map."""
        for territory in self.scaled_polygons.keys():
            color = None
            alpha = 100

            # Determine color based on selection (check all players)
            # S4 fix: use lobby slot color instead of hardcoded PLAYER_COLORS[index]
            for player_index, selection in enumerate(self.player_selections):
                if territory == selection:
                    if hasattr(self, 'lobby_state') and player_index < len(self.lobby_state.slots):
                        color = PLAYER_COLORS[self.lobby_state.slots[player_index].color]
                    else:
                        color = PLAYER_COLORS[player_index]
                    break

            # If not selected by any player, check if hovered
            if color is None and territory == self.hovered_territory:
                color = YELLOW
                alpha = 50

            # Draw overlay
            # P4 fix: reuse cached SRCALPHA surface instead of creating new one per territory
            if color:
                if not hasattr(self, '_cached_overlay') or self._cached_overlay is None or self._cached_overlay.get_size() != (self.width, self.height):
                    self._cached_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                else:
                    self._cached_overlay.fill((0, 0, 0, 0))
                pygame.draw.polygon(self._cached_overlay, (*color, alpha), self.scaled_polygons[territory])
                self.screen.blit(self._cached_overlay, (0, 0))

                # Draw border
                pygame.draw.polygon(self.screen, color, self.scaled_polygons[territory], 3)

    def _draw_title(self):
        """Draw the title (white text like integrated_setup)."""
        title_text = self.title_font.render("Multiplayer Setup", True, WHITE)
        title_rect = title_text.get_rect(center=(self.left_panel_width // 2, self.title_y))
        self.screen.blit(title_text, title_rect)

    def _draw_host_ip(self):
        """Draw the host IP address and UPnP status for players to connect (host only).

        IP is clickable — copies to clipboard on click, shows hover highlight and
        'Copied!' feedback text.
        """
        if not self.is_host:
            return

        server = self.network_connection

        # Get dynamic IP — updates when UPnP completes and discovers public IP
        display_ip = server.get_display_ip() if hasattr(server, 'get_display_ip') else self.host_ip
        if not display_ip:
            return

        upnp_status = server.get_upnp_status_text() if hasattr(server, 'get_upnp_status_text') else ""
        upnp_complete = server.is_upnp_complete() if hasattr(server, 'is_upnp_complete') else True
        upnp_succeeded = (server.upnp_manager is not None
                          and server.upnp_manager.status == "success") if hasattr(server, 'upnp_manager') else False

        # Position below title, above player rows
        ip_y = self.title_y + int(28 * self.ui_scale)

        # Label changes based on UPnP result
        if upnp_succeeded:
            label_str = "Public IP (click to copy):"
        else:
            label_str = "Join IP:"

        # IP color: lighter green on hover to indicate clickability
        if upnp_succeeded:
            ip_color = (200, 255, 200) if self._ip_hovered else (100, 255, 100)
        else:
            ip_color = (200, 200, 255) if self._ip_hovered else WHITE

        # Draw label and IP address
        label_text = self.small_font.render(label_str, True, WHITE)
        ip_text = self.text_font.render(display_ip, True, ip_color)

        # Center both horizontally
        label_rect = label_text.get_rect(centerx=self.left_panel_width // 2, y=ip_y)
        ip_rect = ip_text.get_rect(centerx=self.left_panel_width // 2, y=ip_y + int(16 * self.ui_scale))

        self.screen.blit(label_text, label_rect)
        self.screen.blit(ip_text, ip_rect)

        # Store rect for click/hover detection
        self._ip_click_rect = ip_rect

    def _draw_player_info(self):
        """Draw player information rows with Type/Color/Team dropdowns.

        Layout per row:
        Line 1: [!] [ColorSwatch] [PlayerName]  [KickX]
        Line 2: [Type▼] [Color▼] [Team▼] [Territory]

        The [!] warning indicator is shown for AI slots without territories (host only).
        """
        # S6 fix: clear stale kick button rects each frame
        self.kick_button_rects = {}
        mouse_pos = pygame.mouse.get_pos()

        # Track warning indicator rects for hover detection
        if not hasattr(self, 'warning_indicator_rects'):
            self.warning_indicator_rects = {}
        self.warning_indicator_rects.clear()

        for i, row_rect in enumerate(self.player_rows):
            slot = self.lobby_state.get_slot(i)
            if slot is None:
                continue

            # Get player color from slot (not fixed index)
            player_color = PLAYER_COLORS[slot.color] if slot.color < len(PLAYER_COLORS) else PLAYER_COLORS[0]
            color_name = PLAYER_COLOR_NAMES[slot.color] if slot.color < len(PLAYER_COLOR_NAMES) else "Red"

            # Check if this row is selected for territory assignment (host only)
            is_selected_for_territory = self.is_host and i == self.selected_slot_for_territory

            # Check if this is an AI slot without territory (show warning to host)
            needs_territory_warning = (self.is_host and
                                       slot.state == SLOT_AI and
                                       not slot.territory)

            # Draw warning indicator (!) to the left of the row for AI without territory
            warning_offset = 0
            if needs_territory_warning:
                warning_size = int(16 * self.ui_scale)
                warning_x = row_rect.x - warning_size - int(4 * self.ui_scale)
                warning_y = row_rect.centery - warning_size // 2
                warning_rect = pygame.Rect(warning_x, warning_y, warning_size, warning_size)
                self.warning_indicator_rects[i] = warning_rect

                # Draw warning circle background (orange/yellow)
                warning_color = (255, 180, 50)  # Orange-yellow
                pygame.draw.circle(self.screen, warning_color,
                                  (warning_rect.centerx, warning_rect.centery),
                                  warning_size // 2)
                pygame.draw.circle(self.screen, WHITE,
                                  (warning_rect.centerx, warning_rect.centery),
                                  warning_size // 2, 1)

                # Draw exclamation mark
                exclaim_surface = self.tiny_font.render("!", True, BLACK)
                exclaim_rect = exclaim_surface.get_rect(center=warning_rect.center)
                self.screen.blit(exclaim_surface, exclaim_rect)

            # Draw row background (highlight if selected for territory assignment)
            if is_selected_for_territory:
                pygame.draw.rect(self.screen, PARCHMENT_HOVER, row_rect)
                pygame.draw.rect(self.screen, player_color, row_rect, 2)  # Colored border
            else:
                pygame.draw.rect(self.screen, PARCHMENT_COLOR, row_rect)
                pygame.draw.rect(self.screen, BRASS_COLOR, row_rect, 1)

            # ===== Line 1: Color swatch, player name, kick button =====
            line1_y = row_rect.y + int(5 * self.ui_scale)

            # Draw color swatch
            swatch_size = int(18 * self.ui_scale)
            swatch_rect = pygame.Rect(
                row_rect.x + int(8 * self.ui_scale),
                line1_y + int(2 * self.ui_scale),
                swatch_size, swatch_size
            )
            pygame.draw.rect(self.screen, player_color, swatch_rect)
            pygame.draw.rect(self.screen, WHITE, swatch_rect, 1)

            # Draw player name
            label_x = swatch_rect.right + int(8 * self.ui_scale)
            player_name = slot.player_name if slot.player_name else f"Player {i + 1}"
            if slot.state == SLOT_EMPTY:
                player_name = "(Empty)"
                name_color = GRAY
            elif slot.state == SLOT_AI:
                name_color = TEXT_COLOR_DIM
            elif slot.state == SLOT_DISCONNECTED:
                player_name = f"{player_name} (DC)"
                name_color = (255, 150, 150)  # Reddish for disconnected
            else:
                name_color = player_color

            # Add host indicator
            if slot.is_host:
                player_name = f"[HOST] {player_name}"

            label_surface = self.small_font.render(player_name, True, name_color)
            self.screen.blit(label_surface, (label_x, line1_y))

            # Draw kick button (X) - host can kick non-host human players
            if self.is_host and not slot.is_host and slot.state == SLOT_HUMAN:
                kick_size = int(18 * self.ui_scale)
                kick_rect = pygame.Rect(
                    row_rect.right - kick_size - int(8 * self.ui_scale),
                    line1_y,
                    kick_size, kick_size
                )
                kick_hovered = kick_rect.collidepoint(mouse_pos)
                kick_color = (255, 100, 100) if kick_hovered else (180, 80, 80)
                pygame.draw.rect(self.screen, kick_color, kick_rect)
                pygame.draw.rect(self.screen, WHITE, kick_rect, 1)
                # Draw X
                x_surface = self.tiny_font.render("X", True, WHITE)
                x_rect = x_surface.get_rect(center=kick_rect.center)
                self.screen.blit(x_surface, x_rect)
                # Store rect for click handling
                if not hasattr(self, 'kick_button_rects'):
                    self.kick_button_rects = {}
                self.kick_button_rects[i] = kick_rect

            # ===== Line 2: Type, Color, Team dropdowns + Territory =====
            line2_y = row_rect.y + int(28 * self.ui_scale)
            dropdown_x = row_rect.x + int(8 * self.ui_scale)
            dropdown_h = self.slot_dropdown_height
            spacing = self.slot_dropdown_spacing

            # Store dropdown rects for this slot
            if not hasattr(self, 'slot_type_rects'):
                self.slot_type_rects = {}
                self.slot_color_rects = {}
                self.slot_team_rects = {}

            # Type dropdown
            type_w = self.slot_dropdown_widths['type']
            type_rect = pygame.Rect(dropdown_x, line2_y, type_w, dropdown_h)
            self.slot_type_rects[i] = type_rect
            self._draw_slot_dropdown(type_rect, self._get_type_display(slot), i, 'type', mouse_pos)
            dropdown_x += type_w + spacing

            # Color dropdown
            color_w = self.slot_dropdown_widths['color']
            color_rect = pygame.Rect(dropdown_x, line2_y, color_w, dropdown_h)
            self.slot_color_rects[i] = color_rect
            self._draw_slot_dropdown(color_rect, color_name, i, 'color', mouse_pos)
            dropdown_x += color_w + spacing

            # Team dropdown
            team_w = self.slot_dropdown_widths['team']
            team_rect = pygame.Rect(dropdown_x, line2_y, team_w, dropdown_h)
            self.slot_team_rects[i] = team_rect
            team_display = f"T{slot.team + 1}"
            self._draw_slot_dropdown(team_rect, team_display, i, 'team', mouse_pos)
            dropdown_x += team_w + spacing

            # Territory display (remaining space) - more generous truncation
            terr_x = dropdown_x
            territory = slot.territory
            if territory:
                # Allow up to 18 chars before truncating to 16 + ".."
                display_text = territory if len(territory) <= 18 else territory[:16] + ".."
                terr_surface = self.tiny_font.render(display_text, True, WHITE)
            else:
                terr_surface = self.tiny_font.render("No territory", True, GRAY)
            self.screen.blit(terr_surface, (terr_x, line2_y + int(3 * self.ui_scale)))

    def _get_type_display(self, slot: LobbySlot) -> str:
        """Get display text for slot type."""
        if slot.state == SLOT_EMPTY:
            return "Empty"
        elif slot.state == SLOT_HUMAN:
            return "Human"
        elif slot.state == SLOT_DISCONNECTED:
            return "Human"  # Show as human (AI controlling)
        elif slot.state == SLOT_AI:
            diff_names = ["Easy", "Med", "Hard"]
            diff = slot.ai_difficulty if 0 <= slot.ai_difficulty < 3 else 1
            return f"AI({diff_names[diff]})"
        return "?"

    def _draw_slot_dropdown(self, rect: pygame.Rect, text: str, slot_idx: int,
                            dropdown_type: str, mouse_pos: tuple):
        """Draw a mini dropdown for slot configuration.

        Args:
            rect: Dropdown rectangle
            text: Current value display text (or color index for 'color' type)
            slot_idx: Slot index (0-3)
            dropdown_type: 'type', 'color', or 'team'
            mouse_pos: Current mouse position
        """
        # Determine if this dropdown is editable by local player
        can_edit = self._can_edit_slot_dropdown(slot_idx, dropdown_type)

        # Check if open
        is_open = self.active_slot_dropdown.get(slot_idx) == dropdown_type

        # Determine background color
        if not can_edit:
            bg_color = DARK_GRAY
        elif is_open:
            bg_color = PARCHMENT_CLICK
        elif rect.collidepoint(mouse_pos):
            bg_color = PARCHMENT_HOVER
        else:
            bg_color = PARCHMENT_COLOR

        # Draw dropdown box
        pygame.draw.rect(self.screen, bg_color, rect)
        pygame.draw.rect(self.screen, BRASS_COLOR if can_edit else GRAY, rect, 1)

        # For color dropdown, draw a color swatch instead of text
        if dropdown_type == 'color':
            # Get the actual color from the slot
            slot = self.lobby_state.get_slot(slot_idx)
            color_idx = slot.color if slot else 0
            swatch_color = PLAYER_COLORS[color_idx] if color_idx < len(PLAYER_COLORS) else PLAYER_COLORS[0]

            # Draw centered color swatch (like integrated_setup)
            swatch_size = int(14 * self.ui_scale)
            swatch_x = rect.x + 4
            swatch_y = rect.centery - swatch_size // 2
            swatch_rect = pygame.Rect(swatch_x, swatch_y, swatch_size, swatch_size)
            pygame.draw.rect(self.screen, swatch_color, swatch_rect)
            pygame.draw.rect(self.screen, WHITE, swatch_rect, 1)
        else:
            # Draw text for type and team dropdowns
            text_color = WHITE if can_edit else TEXT_COLOR_DIM
            text_surface = self.tiny_font.render(text, True, text_color)
            text_rect = text_surface.get_rect(midleft=(rect.x + 3, rect.centery))
            self.screen.blit(text_surface, text_rect)

        # Draw arrow if editable
        if can_edit:
            arrow_x = rect.right - int(8 * self.ui_scale)
            arrow_y = rect.centery
            arrow_size = 3
            arrow_points = [
                (arrow_x - arrow_size, arrow_y - 2),
                (arrow_x + arrow_size, arrow_y - 2),
                (arrow_x, arrow_y + 3)
            ]
            pygame.draw.polygon(self.screen, BRASS_COLOR, arrow_points)

    def _can_edit_slot_dropdown(self, slot_idx: int, dropdown_type: str) -> bool:
        """Check if local player can edit this slot's dropdown.

        Rules:
        - Host can change Type for any slot
        - Players can change their own Color and Team
        - Host can change Color/Team for AI and Empty slots
        """
        slot = self.lobby_state.get_slot(slot_idx)
        if slot is None:
            return False

        if dropdown_type == 'type':
            # Only host can change slot type
            if not self.is_host:
                return False
            if slot_idx == 0:
                return False  # Host slot always human
            # Can't change a HUMAN slot - kick the player first, then change
            if slot.state == SLOT_HUMAN:
                return False
            return True

        elif dropdown_type in ('color', 'team'):
            # Player can change their own color/team
            if slot_idx == self.local_player_index and slot.state == SLOT_HUMAN:
                return True
            # Host can change AI/Empty slots
            if self.is_host and slot.state in (SLOT_AI, SLOT_EMPTY):
                return True
            return False

        return False

    def _draw_victory_dropdown(self):
        """Draw victory condition dropdown."""
        margin = self.border_thickness

        # Label (white text like integrated_setup)
        label_surface = self.text_font.render("Victory Condition:", True, WHITE)
        self.screen.blit(label_surface, (margin, self.victory_label_y))

        # Dropdown box
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = self.victory_dropdown_rect.collidepoint(mouse_pos) and self.is_host

        if self.is_host:
            bg_color = PARCHMENT_HOVER if is_hovered else PARCHMENT_COLOR
        else:
            bg_color = DARK_GRAY  # Disabled appearance for client

        pygame.draw.rect(self.screen, bg_color, self.victory_dropdown_rect)
        pygame.draw.rect(self.screen, BRASS_COLOR, self.victory_dropdown_rect, 2)

        # Current value text
        text_color = WHITE if self.is_host else TEXT_COLOR_DIM
        value_text = self.small_font.render(self.victory_options[self.victory_condition], True, text_color)
        text_rect = value_text.get_rect(midleft=(
            self.victory_dropdown_rect.x + int(10 * self.ui_scale),
            self.victory_dropdown_rect.centery
        ))
        self.screen.blit(value_text, text_rect)

        # Dropdown arrow (only for host)
        if self.is_host:
            arrow_x = self.victory_dropdown_rect.right - int(25 * self.ui_scale)
            arrow_y = self.victory_dropdown_rect.centery
            arrow_points = [
                (arrow_x, arrow_y - 5),
                (arrow_x + 10, arrow_y - 5),
                (arrow_x + 5, arrow_y + 5)
            ]
            pygame.draw.polygon(self.screen, BRASS_COLOR, arrow_points)

    def _draw_taxation_dropdown(self):
        """Draw taxation level dropdown."""
        margin = self.border_thickness

        # Label (white text like integrated_setup)
        label_surface = self.text_font.render("Taxation Level:", True, WHITE)
        self.screen.blit(label_surface, (margin, self.taxation_label_y))

        # Dropdown box
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = self.taxation_dropdown_rect.collidepoint(mouse_pos) and self.is_host

        if self.is_host:
            bg_color = PARCHMENT_HOVER if is_hovered else PARCHMENT_COLOR
        else:
            bg_color = DARK_GRAY  # Disabled appearance for client

        pygame.draw.rect(self.screen, bg_color, self.taxation_dropdown_rect)
        pygame.draw.rect(self.screen, BRASS_COLOR, self.taxation_dropdown_rect, 2)

        # Current value text
        text_color = WHITE if self.is_host else TEXT_COLOR_DIM
        value_text = self.small_font.render(self.taxation_options[self.taxation_level], True, text_color)
        text_rect = value_text.get_rect(midleft=(
            self.taxation_dropdown_rect.x + int(10 * self.ui_scale),
            self.taxation_dropdown_rect.centery
        ))
        self.screen.blit(value_text, text_rect)

        # Dropdown arrow (only for host)
        if self.is_host:
            arrow_x = self.taxation_dropdown_rect.right - int(25 * self.ui_scale)
            arrow_y = self.taxation_dropdown_rect.centery
            arrow_points = [
                (arrow_x, arrow_y - 5),
                (arrow_x + 10, arrow_y - 5),
                (arrow_x + 5, arrow_y + 5)
            ]
            pygame.draw.polygon(self.screen, BRASS_COLOR, arrow_points)

    def _draw_turn_mode_dropdown(self):
        """Draw turn mode dropdown."""
        margin = self.border_thickness

        # Label (white text like integrated_setup)
        label_surface = self.text_font.render("Turn Mode:", True, WHITE)
        self.screen.blit(label_surface, (margin, self.turn_mode_label_y))

        # Dropdown box
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = self.turn_mode_dropdown_rect.collidepoint(mouse_pos) and self.is_host

        if self.is_host:
            bg_color = PARCHMENT_HOVER if is_hovered else PARCHMENT_COLOR
        else:
            bg_color = DARK_GRAY  # Disabled appearance for client

        pygame.draw.rect(self.screen, bg_color, self.turn_mode_dropdown_rect)
        pygame.draw.rect(self.screen, BRASS_COLOR, self.turn_mode_dropdown_rect, 2)

        # Current value text
        text_color = WHITE if self.is_host else TEXT_COLOR_DIM
        value_text = self.small_font.render(self.turn_mode_options[self.turn_mode], True, text_color)
        text_rect = value_text.get_rect(midleft=(
            self.turn_mode_dropdown_rect.x + int(10 * self.ui_scale),
            self.turn_mode_dropdown_rect.centery
        ))
        self.screen.blit(value_text, text_rect)

        # Dropdown arrow (only for host)
        if self.is_host:
            arrow_x = self.turn_mode_dropdown_rect.right - int(25 * self.ui_scale)
            arrow_y = self.turn_mode_dropdown_rect.centery
            arrow_points = [
                (arrow_x, arrow_y - 5),
                (arrow_x + 10, arrow_y - 5),
                (arrow_x + 5, arrow_y + 5)
            ]
            pygame.draw.polygon(self.screen, BRASS_COLOR, arrow_points)

        # Draw tooltip on hover
        if is_hovered:
            current_option = self.turn_mode_options[self.turn_mode]
            tooltip = self.turn_mode_tooltips.get(current_option, "")
            if tooltip:
                tooltip_surface = self.small_font.render(tooltip, True, TEXT_COLOR_DIM)
                tooltip_rect = tooltip_surface.get_rect(midleft=(
                    self.turn_mode_dropdown_rect.x + int(10 * self.ui_scale),
                    self.turn_mode_dropdown_rect.bottom + int(5 * self.ui_scale)
                ))
                self.screen.blit(tooltip_surface, tooltip_rect)

    def _draw_dropdown_menus(self):
        """Draw open dropdown menus."""
        item_height = int(35 * self.ui_scale)

        if self.victory_dropdown_open:
            self._draw_dropdown_items(
                self.victory_dropdown_rect,
                self.victory_options,
                self.victory_condition,
                item_height
            )

        if self.taxation_dropdown_open:
            self._draw_dropdown_items(
                self.taxation_dropdown_rect,
                self.taxation_options,
                self.taxation_level,
                item_height
            )

        if self.turn_mode_dropdown_open:
            self._draw_dropdown_items(
                self.turn_mode_dropdown_rect,
                self.turn_mode_options,
                self.turn_mode,
                item_height
            )

    def _draw_dropdown_items(self, dropdown_rect, options, selected_index, item_height):
        """Draw dropdown menu items."""
        mouse_pos = pygame.mouse.get_pos()

        menu_rect = pygame.Rect(
            dropdown_rect.x,
            dropdown_rect.bottom,
            dropdown_rect.width,
            len(options) * item_height
        )

        # Background
        pygame.draw.rect(self.screen, PARCHMENT_COLOR, menu_rect)
        pygame.draw.rect(self.screen, BRASS_COLOR, menu_rect, 2)

        for i, option in enumerate(options):
            item_rect = pygame.Rect(
                menu_rect.x,
                menu_rect.y + i * item_height,
                menu_rect.width,
                item_height
            )

            # Highlight hovered or selected item
            if item_rect.collidepoint(mouse_pos):
                pygame.draw.rect(self.screen, PARCHMENT_HOVER, item_rect)
            elif i == selected_index:
                pygame.draw.rect(self.screen, PARCHMENT_CLICK, item_rect)

            # Draw text
            text_surface = self.small_font.render(option, True, WHITE)
            text_rect = text_surface.get_rect(midleft=(
                item_rect.x + int(10 * self.ui_scale),
                item_rect.centery
            ))
            self.screen.blit(text_surface, text_rect)

    def _handle_overlay_click(self, pos):
        """Handle clicks within the Additional Options overlay"""
        # Check checkbox clicks
        if 'neutral_cb' in self.overlay_rects and self.overlay_rects['neutral_cb'].collidepoint(pos):
            sound_manager.play_ui_click()
            self.overlay_neutral_armies = not self.overlay_neutral_armies
            self.overlay_clicked = 'neutral_cb'
            return

        if 'randomize_cb' in self.overlay_rects and self.overlay_rects['randomize_cb'].collidepoint(pos):
            sound_manager.play_ui_click()
            self.overlay_randomize_bonuses = not self.overlay_randomize_bonuses
            self.overlay_clicked = 'randomize_cb'
            return

        # Check Confirm button
        if 'confirm_btn' in self.overlay_rects and self.overlay_rects['confirm_btn'].collidepoint(pos):
            sound_manager.play_ui_click()
            self.overlay_clicked = 'confirm_btn'
            # Apply temp values to actual state
            self.neutral_armies = self.overlay_neutral_armies
            self.randomize_bonuses = self.overlay_randomize_bonuses
            self.overlay_open = False
            # Sync new settings to client
            if self.is_host:
                self._sync_settings_to_client()
            return

        # Check Cancel button
        if 'cancel_btn' in self.overlay_rects and self.overlay_rects['cancel_btn'].collidepoint(pos):
            sound_manager.play_ui_click()
            self.overlay_clicked = 'cancel_btn'
            # Discard temp values
            self.overlay_open = False
            return

    def _update_overlay_hover(self, mouse_pos):
        """Update hover state for the Additional Options overlay"""
        self.hovered_territory = None  # Clear normal hover
        self.overlay_hovered = None
        for element_name, rect in self.overlay_rects.items():
            if rect.collidepoint(mouse_pos):
                self.overlay_hovered = element_name
                return

    def _draw_additional_options_overlay(self):
        """Draw the Additional Options modal overlay"""
        screen_w, screen_h = self.screen.get_size()

        # Semi-transparent dark overlay covering entire screen
        dark_overlay = pygame.Surface((screen_w, screen_h))
        dark_overlay.set_alpha(180)
        dark_overlay.fill((0, 0, 0))
        self.screen.blit(dark_overlay, (0, 0))

        # Overlay panel dimensions (scaled from reference 400x300 at 1600x900)
        scale = self.ui_scale
        panel_w = int(400 * scale)
        panel_h = int(300 * scale)
        panel_x = (screen_w - panel_w) // 2
        panel_y = (screen_h - panel_h) // 2

        # Draw InGameMenuBG.png as background, or fallback to solid color
        if self.overlay_bg_image:
            scaled_bg = pygame.transform.smoothscale(self.overlay_bg_image, (panel_w, panel_h))
            self.screen.blit(scaled_bg, (panel_x, panel_y))
        else:
            pygame.draw.rect(self.screen, (40, 40, 50), (panel_x, panel_y, panel_w, panel_h))
            pygame.draw.rect(self.screen, BRASS_COLOR, (panel_x, panel_y, panel_w, panel_h), 2)

        # Title
        title_font_size = max(16, int(26 * scale))
        try:
            title_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', title_font_size)
        except (FileNotFoundError, pygame.error, OSError):
            title_font = self.text_font
        title_surface = title_font.render("Additional Options", True, TEXT_COLOR)
        title_rect = title_surface.get_rect(centerx=panel_x + panel_w // 2, top=panel_y + int(25 * scale))
        self.screen.blit(title_surface, title_rect)

        # Separator line below title
        sep_y = title_rect.bottom + int(10 * scale)
        sep_margin = int(30 * scale)
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (panel_x + sep_margin, sep_y),
                         (panel_x + panel_w - sep_margin, sep_y), 1)

        # Checkbox rows — checkboxes aligned to same x position
        label_font_size = max(13, int(20 * scale))
        try:
            label_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', label_font_size)
        except (FileNotFoundError, pygame.error, OSError):
            label_font = self.small_font
        cb_size = int(22 * scale)
        row_x = panel_x + int(40 * scale)
        row_start_y = sep_y + int(25 * scale)
        row_spacing = int(45 * scale)
        # Fixed checkbox x: right side of panel with margin
        cb_x = panel_x + panel_w - int(40 * scale) - cb_size

        # Row 1: Neutral Armies
        row1_y = row_start_y
        neutral_label = label_font.render("Neutral Armies:", True, TEXT_COLOR)
        self.screen.blit(neutral_label, (row_x, row1_y + (cb_size - neutral_label.get_height()) // 2))
        neutral_cb_rect = pygame.Rect(cb_x, row1_y, cb_size, cb_size)
        self.overlay_rects['neutral_cb'] = neutral_cb_rect
        self._draw_overlay_checkbox(neutral_cb_rect, self.overlay_neutral_armies,
                                     self.overlay_hovered == 'neutral_cb')

        # Row 2: Randomize Territory Bonuses (split across two lines)
        row2_y = row_start_y + row_spacing
        bonus_line1 = label_font.render("Randomize Territory", True, TEXT_COLOR)
        bonus_line2 = label_font.render("Bonuses:", True, TEXT_COLOR)
        line_gap = int(3 * scale)
        total_text_h = bonus_line1.get_height() + line_gap + bonus_line2.get_height()
        line1_y = row2_y
        line2_y = line1_y + bonus_line1.get_height() + line_gap
        self.screen.blit(bonus_line1, (row_x, line1_y))
        self.screen.blit(bonus_line2, (row_x, line2_y))
        # Checkbox at same x as row 1, vertically centered with two-line block
        bonus_cb_y = line1_y + (total_text_h - cb_size) // 2
        bonus_cb_rect = pygame.Rect(cb_x, bonus_cb_y, cb_size, cb_size)
        self.overlay_rects['randomize_cb'] = bonus_cb_rect
        self._draw_overlay_checkbox(bonus_cb_rect, self.overlay_randomize_bonuses,
                                     self.overlay_hovered == 'randomize_cb')

        # Buttons at bottom: Cancel (left) and Confirm (right)
        btn_w = int(130 * scale)
        btn_h = int(45 * scale)
        btn_y = panel_y + panel_h - int(55 * scale)
        btn_gap = int(20 * scale)
        total_btn_width = 2 * btn_w + btn_gap
        btn_start_x = panel_x + (panel_w - total_btn_width) // 2

        cancel_rect = pygame.Rect(btn_start_x, btn_y, btn_w, btn_h)
        confirm_rect = pygame.Rect(btn_start_x + btn_w + btn_gap, btn_y, btn_w, btn_h)
        self.overlay_rects['cancel_btn'] = cancel_rect
        self.overlay_rects['confirm_btn'] = confirm_rect

        self._draw_overlay_button(cancel_rect, "Cancel",
                                   self.overlay_hovered == 'cancel_btn',
                                   self.overlay_clicked == 'cancel_btn')
        self._draw_overlay_button(confirm_rect, "Confirm",
                                   self.overlay_hovered == 'confirm_btn',
                                   self.overlay_clicked == 'confirm_btn')

    def _draw_overlay_checkbox(self, rect, checked, hovered):
        """Draw a checkbox for the Additional Options overlay"""
        from utils.colors import lighten_color
        bg_color = lighten_color((40, 40, 50), 0.3) if hovered else lighten_color((40, 40, 50), 0.1)
        pygame.draw.rect(self.screen, bg_color, rect, border_radius=3)
        pygame.draw.rect(self.screen, TEXT_COLOR, rect, 1, border_radius=3)
        if checked:
            # Draw checkmark (X shape) matching integrated_setup style
            RADIO_SELECTED = (100, 200, 100)
            pygame.draw.line(self.screen, RADIO_SELECTED,
                             (rect.x + 4, rect.y + 4), (rect.right - 4, rect.bottom - 4), 2)
            pygame.draw.line(self.screen, RADIO_SELECTED,
                             (rect.right - 4, rect.y + 4), (rect.x + 4, rect.bottom - 4), 2)

    def _draw_overlay_button(self, rect, text, hovered, clicked):
        """Draw a button for the Additional Options overlay"""
        if self.button_bg_image:
            scaled_bg = pygame.transform.smoothscale(self.button_bg_image, (rect.width, rect.height))
            button_surface = scaled_bg.copy()
            button_surface.fill((100, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if clicked:
                button_surface.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif hovered:
                button_surface.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self.screen.blit(button_surface, rect)
        else:
            bg_color = PARCHMENT_CLICK if clicked else (PARCHMENT_HOVER if hovered else PARCHMENT_COLOR)
            pygame.draw.rect(self.screen, bg_color, rect, border_radius=5)
            pygame.draw.rect(self.screen, BRASS_COLOR, rect, 2, border_radius=5)

        btn_font_size = max(14, int(22 * self.ui_scale))
        try:
            btn_font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', btn_font_size)
        except (FileNotFoundError, pygame.error, OSError):
            btn_font = self.button_font_regular
        text_surface = btn_font.render(text, True, TEXT_COLOR)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    # ------------------------------------------------------------------
    # Friend Picker Modal (Steam Invite)
    # ------------------------------------------------------------------

    def _draw_friend_picker(self):
        """Draw the friend picker modal overlay for Steam invites."""
        screen_w, screen_h = self.screen.get_size()
        scale = self.ui_scale
        mouse_pos = pygame.mouse.get_pos()

        # Semi-transparent dark overlay covering entire screen
        dark_overlay = pygame.Surface((screen_w, screen_h))
        dark_overlay.set_alpha(180)
        dark_overlay.fill((0, 0, 0))
        self.screen.blit(dark_overlay, (0, 0))

        # Panel dimensions — sized to comfortably fit friend list with padding
        panel_w = int(440 * scale)
        panel_h = int(480 * scale)
        panel_x = (screen_w - panel_w) // 2
        panel_y = (screen_h - panel_h) // 2
        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        self._friend_picker_rects['panel'] = panel_rect

        # Draw background (reuse overlay_bg_image or fallback)
        if self.overlay_bg_image:
            scaled_bg = pygame.transform.smoothscale(self.overlay_bg_image, (panel_w, panel_h))
            self.screen.blit(scaled_bg, (panel_x, panel_y))
        else:
            pygame.draw.rect(self.screen, (40, 40, 50), panel_rect)
            pygame.draw.rect(self.screen, BRASS_COLOR, panel_rect, 2)

        # Title
        title_font_size = max(16, int(26 * scale))
        try:
            title_font = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', title_font_size)
        except (FileNotFoundError, pygame.error, OSError):
            title_font = self.text_font
        title_surface = title_font.render("Invite Friend", True, TEXT_COLOR)
        title_rect = title_surface.get_rect(centerx=panel_x + panel_w // 2, top=panel_y + int(40 * scale))
        self.screen.blit(title_surface, title_rect)

        # Close button (X) in top-right corner
        close_size = int(30 * scale)
        close_rect = pygame.Rect(panel_x + panel_w - close_size - int(10 * scale),
                                 panel_y + int(10 * scale), close_size, close_size)
        self._friend_picker_rects['close'] = close_rect
        close_hovered = close_rect.collidepoint(mouse_pos)
        close_color = WHITE if close_hovered else GRAY
        # Draw X
        pygame.draw.line(self.screen, close_color,
                         (close_rect.x + 6, close_rect.y + 6),
                         (close_rect.right - 6, close_rect.bottom - 6), 2)
        pygame.draw.line(self.screen, close_color,
                         (close_rect.right - 6, close_rect.y + 6),
                         (close_rect.x + 6, close_rect.bottom - 6), 2)

        # Separator line below title
        sep_y = title_rect.bottom + int(10 * scale)
        sep_margin = int(25 * scale)
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (panel_x + sep_margin, sep_y),
                         (panel_x + panel_w - sep_margin, sep_y), 1)

        # Friend list area — generous padding to keep content within panel
        list_top = sep_y + int(15 * scale)
        list_bottom = panel_y + panel_h - int(35 * scale)
        list_left = panel_x + int(30 * scale)
        list_right = panel_x + panel_w - int(30 * scale)
        list_width = list_right - list_left
        row_h = int(40 * scale)

        if not self._friend_list:
            # No friends online message
            no_friends_font = self.small_font
            msg = no_friends_font.render("No Steam friends found.", True, TEXT_COLOR_DIM)
            msg_rect = msg.get_rect(center=(panel_x + panel_w // 2,
                                            (list_top + list_bottom) // 2))
            self.screen.blit(msg, msg_rect)
        else:
            # Clamp scroll offset to valid range
            max_visible = (list_bottom - list_top) // row_h
            max_scroll = max(0, len(self._friend_list) - max_visible)
            self._friend_scroll_offset = min(self._friend_scroll_offset, max_scroll)

            # Clear invite button rects for this frame
            self._friend_picker_rects['invite_buttons'] = {}

            # Draw visible friend rows
            visible_start = self._friend_scroll_offset
            y = list_top
            label_font = self.small_font
            invite_btn_w = int(75 * scale)
            invite_btn_h = int(28 * scale)

            for idx in range(visible_start, len(self._friend_list)):
                if y + row_h > list_bottom:
                    break  # Stop rendering past container boundary

                friend = self._friend_list[idx]
                steam_id = friend['steam_id']
                name = friend['name']
                already_invited = steam_id in self._invited_friends

                # Row hover highlight
                row_rect = pygame.Rect(list_left, y, list_width, row_h)
                if row_rect.collidepoint(mouse_pos):
                    highlight = pygame.Surface((list_width, row_h), pygame.SRCALPHA)
                    highlight.fill((255, 255, 255, 20))
                    self.screen.blit(highlight, (list_left, y))

                # Friend name (left-aligned, vertically centered in row)
                name_surface = label_font.render(name, True, TEXT_COLOR)
                # Truncate name if too wide (leave space for invite button)
                max_name_width = list_width - invite_btn_w - int(15 * scale)
                if name_surface.get_width() > max_name_width:
                    # Render truncated name with ellipsis
                    truncated = name
                    while label_font.size(truncated + "...")[0] > max_name_width and len(truncated) > 1:
                        truncated = truncated[:-1]
                    name_surface = label_font.render(truncated + "...", True, TEXT_COLOR)
                name_y = y + (row_h - name_surface.get_height()) // 2
                self.screen.blit(name_surface, (list_left + int(5 * scale), name_y))

                # Invite / Invited button (right-aligned)
                btn_x = list_right - invite_btn_w
                btn_y = y + (row_h - invite_btn_h) // 2
                btn_rect = pygame.Rect(btn_x, btn_y, invite_btn_w, invite_btn_h)
                self._friend_picker_rects['invite_buttons'][steam_id] = btn_rect

                btn_hovered = btn_rect.collidepoint(mouse_pos) and not already_invited
                if already_invited:
                    # "Invited" label — green tint
                    pygame.draw.rect(self.screen, (40, 70, 40), btn_rect, border_radius=4)
                    pygame.draw.rect(self.screen, (100, 200, 100), btn_rect, 1, border_radius=4)
                    btn_text = label_font.render("Invited", True, (100, 200, 100))
                else:
                    # "Invite" button
                    bg_color = PARCHMENT_HOVER if btn_hovered else PARCHMENT_COLOR
                    pygame.draw.rect(self.screen, bg_color, btn_rect, border_radius=4)
                    pygame.draw.rect(self.screen, BRASS_COLOR, btn_rect, 1, border_radius=4)
                    btn_text = label_font.render("Invite", True, TEXT_COLOR)
                btn_text_rect = btn_text.get_rect(center=btn_rect.center)
                self.screen.blit(btn_text, btn_text_rect)

                # Separator line between rows
                sep_line_y = y + row_h - 1
                pygame.draw.line(self.screen, (80, 80, 80),
                                 (list_left, sep_line_y), (list_right, sep_line_y), 1)

                y += row_h

            # Scroll indicators if list is longer than visible area
            if self._friend_scroll_offset > 0:
                # Up arrow indicator
                arrow_text = self.tiny_font.render("▲ more", True, TEXT_COLOR_DIM)
                self.screen.blit(arrow_text,
                                 arrow_text.get_rect(centerx=panel_x + panel_w // 2,
                                                     bottom=list_top - 2))
            if self._friend_scroll_offset < max_scroll:
                # Down arrow indicator
                arrow_text = self.tiny_font.render("▼ more", True, TEXT_COLOR_DIM)
                self.screen.blit(arrow_text,
                                 arrow_text.get_rect(centerx=panel_x + panel_w // 2,
                                                     top=list_bottom + 2))

    def _handle_friend_picker_click(self, pos):
        """Handle clicks within the friend picker modal."""
        # Close button
        close_rect = self._friend_picker_rects.get('close')
        if close_rect and close_rect.collidepoint(pos):
            sound_manager.play_ui_click()
            self._show_friend_picker = False
            return

        # Check invite button clicks
        invite_buttons = self._friend_picker_rects.get('invite_buttons', {})
        for steam_id, btn_rect in invite_buttons.items():
            if btn_rect.collidepoint(pos) and steam_id not in self._invited_friends:
                sound_manager.play_ui_click()
                # Get host IP for connection string
                from steam_integration import steam_manager
                from network_config import DEFAULT_PORT
                server = self.network_connection
                display_ip = (server.get_display_ip()
                              if hasattr(server, 'get_display_ip') else self.host_ip)
                if display_ip:
                    # Include +connect prefix so Steam passes it as a launch parameter
                    # that main.py's sys.argv parser can detect
                    connect_str = f"+connect {display_ip}:{DEFAULT_PORT}"
                    if steam_manager.invite_friend(steam_id, connect_str):
                        self._invited_friends.add(steam_id)
                        logger.info(f"Invited friend {steam_id} with connect string '{connect_str}'")
                return

        # Click outside panel closes it
        panel_rect = self._friend_picker_rects.get('panel')
        if panel_rect and not panel_rect.collidepoint(pos):
            self._show_friend_picker = False

    def _draw_buttons(self):
        """Draw Launch Game and Return to Main Menu buttons."""
        mouse_pos = pygame.mouse.get_pos()
        can_launch = self._can_launch()

        # Additional Options button (visible for all, enabled only for host)
        self._draw_button(
            self.additional_options_rect,
            "Additional Options",
            enabled=self.is_host,
            hovered=self.additional_options_rect.collidepoint(mouse_pos) and self.is_host,
            is_launch_button=False
        )

        # Invite Friend button (host only — disabled when Steam not connected)
        if self.is_host and self.invite_button_rect:
            from steam_integration import steam_manager
            invite_enabled = steam_manager.can_invite()
            self._draw_button(
                self.invite_button_rect,
                "Invite Friend",
                enabled=invite_enabled,
                hovered=self.invite_button_rect.collidepoint(mouse_pos) and invite_enabled,
                is_launch_button=False
            )
            # Draw "Steam not connected" hint when disabled
            if not invite_enabled:
                hint_text = self.tiny_font.render("(Steam not connected)", True, GRAY)
                hint_rect = hint_text.get_rect(
                    centerx=self.invite_button_rect.centerx,
                    top=self.invite_button_rect.bottom + 2
                )
                self.screen.blit(hint_text, hint_rect)

        # Launch Game button (brass text, bold font)
        self._draw_button(
            self.launch_button_rect,
            "Launch Game" if self.is_host else "Waiting for Host...",
            enabled=can_launch and self.is_host,
            hovered=self.launch_button_rect.collidepoint(mouse_pos) and can_launch and self.is_host,
            is_launch_button=True
        )

        # Return to Main Menu button (white text, regular font)
        self._draw_button(
            self.return_button_rect,
            "Return to Main Menu",
            enabled=True,
            hovered=self.return_button_rect.collidepoint(mouse_pos),
            is_launch_button=False
        )

    def _draw_button(self, rect, text, enabled=True, hovered=False, is_launch_button=True):
        """Draw a styled button matching integrated_setup.py styling.

        Args:
            rect: Button rectangle
            text: Button text
            enabled: Whether button is clickable
            hovered: Whether mouse is over button
            is_launch_button: True for Launch Game (brass text, bold), False for Return (white text, regular)
        """
        if self.button_bg_image:
            # Scale button image to fit
            scaled_bg = pygame.transform.smoothscale(self.button_bg_image, (rect.width, rect.height))

            # Apply darkening based on state (matching integrated_setup)
            if not enabled:
                # Disabled: multiply by (80, 80, 80) - darkest
                dark_surface = pygame.Surface((rect.width, rect.height))
                dark_surface.fill((80, 80, 80))
                scaled_bg.blit(dark_surface, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            else:
                # Enabled: multiply by (100, 100, 100) - darker base
                dark_surface = pygame.Surface((rect.width, rect.height))
                dark_surface.fill((100, 100, 100))
                scaled_bg.blit(dark_surface, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

                if hovered:
                    # Add brightness on hover
                    bright_surface = pygame.Surface((rect.width, rect.height))
                    bright_surface.fill((40, 40, 40))
                    scaled_bg.blit(bright_surface, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

            self.screen.blit(scaled_bg, rect)
        else:
            # Fallback: simple rectangle
            if enabled:
                bg_color = PARCHMENT_HOVER if hovered else PARCHMENT_COLOR
            else:
                bg_color = DARK_GRAY
            pygame.draw.rect(self.screen, bg_color, rect)
            pygame.draw.rect(self.screen, BRASS_COLOR, rect, 2)

        # Button text - Launch Game uses brass text + bold font, Return uses white + regular font
        if is_launch_button:
            text_color = BRASS_COLOR if enabled else GRAY
            font = self.button_font_bold
        else:
            text_color = WHITE if enabled else GRAY
            font = self.button_font_regular

        text_surface = font.render(text, True, text_color)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def _draw_hover_info(self):
        """Draw hovered territory name."""
        hover_text = self.small_font.render(self.hovered_territory, True, YELLOW)
        hover_rect = hover_text.get_rect(bottomleft=(self.left_panel_width + 10, self.height - 10))

        # Draw background
        bg_rect = hover_rect.inflate(20, 10)
        pygame.draw.rect(self.screen, BLACK, bg_rect)
        pygame.draw.rect(self.screen, YELLOW, bg_rect, 2)
        self.screen.blit(hover_text, hover_rect)
