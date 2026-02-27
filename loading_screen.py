# -*- coding: utf-8 -*-
# loading_screen.py
# Loading screen with progress bar for deferred asset loading

"""
Loading Screen Module
=====================

Shows a progress bar while deferring game asset loading (sounds, images, fonts)
to after menu/setup. Replaces the old pattern of loading everything at startup.

Single-player: after loading completes, shows "Click any button to start".
Multiplayer: exchanges GAME_READY handshake so both players start together.
"""

import sys
import pygame

from network_config import MessageType
from network.protocol import NetworkProtocol
from global_sound import get_game_sound_tasks
from utils.logger import get_logger

logger = get_logger(__name__)


class LoadingScreen:
    """
    Renders a progress bar while executing deferred asset loading tasks,
    then waits for player input (and multiplayer readiness) before starting.
    """

    def __init__(self, screen, game, setup_config, network_connection=None):
        """
        Args:
            screen: Pygame display surface
            game: Game instance (Game.__init__ already called)
            setup_config: Config dict to pass to game.initialize_game()
            network_connection: NetworkServer (host) or NetworkClient (client), or None for SP
        """
        self.screen = screen
        self.game = game
        self.setup_config = setup_config
        self.network_connection = network_connection

        # Loading state
        self.progress = 0.0            # 0.0 to 1.0
        self.current_label = ""        # Currently executing task label
        self.loading_complete = False

        # Multiplayer readiness state
        self.is_multiplayer = network_connection is not None
        # Host = local player index 0, client = anything else
        self.is_host = self.is_multiplayer and getattr(game, 'local_player_index', 0) == 0
        self.local_ready = False       # This player clicked "start"
        self.all_players_ready = False  # All remote players have sent GAME_READY
        self.remote_ready_players = set()  # Player indices that sent GAME_READY
        self.protocol = NetworkProtocol() if self.is_multiplayer else None

        # Determine how many remote players we expect (for host readiness check)
        self.expected_remote_count = 0
        if self.is_host and network_connection:
            # Host expects GAME_READY from each connected client
            # setup_config tells us num_players; host is player 0
            num_players = setup_config.get('num_players', 2)
            # Only count human players (non-AI) besides the host
            player_is_ai = setup_config.get('player_is_ai', [False] * num_players)
            for i in range(1, num_players):
                if not player_is_ai[i]:
                    self.expected_remote_count += 1

        # Clock for frame timing
        self.clock = pygame.time.Clock()

        # Load visual assets for the loading screen itself
        self._load_screen_assets()

    def _load_screen_assets(self):
        """Load logo and create fonts for the loading screen itself."""
        sw, sh = self.screen.get_size()

        # Load game logo (same as main menu)
        self.logo = None
        try:
            raw_logo = pygame.image.load('assets/GameLogo.png').convert_alpha()
            # Scale logo to fit ~40% of screen width, preserving aspect ratio
            target_w = int(sw * 0.4)
            logo_w, logo_h = raw_logo.get_size()
            scale = target_w / logo_w
            self.logo = pygame.transform.smoothscale(
                raw_logo, (target_w, int(logo_h * scale))
            )
        except pygame.error:
            logger.warning("Could not load GameLogo.png for loading screen")

        # Load Cinzel font for consistent look with the rest of the game
        self.font_large = None
        self.font_small = None
        try:
            font_size_large = max(16, int(sh * 0.032))
            font_size_small = max(12, int(sh * 0.022))
            self.font_large = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size_large)
            self.font_small = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size_small)
        except (pygame.error, FileNotFoundError):
            # Fallback to system font if Cinzel not available
            logger.warning("Could not load Cinzel font for loading screen, using system font")
            self.font_large = pygame.font.SysFont('arial', max(16, int(sh * 0.032)))
            self.font_small = pygame.font.SysFont('arial', max(12, int(sh * 0.022)))

    def _build_task_list(self):
        """Build ordered list of (label, callable) loading tasks."""
        tasks = []

        # Deferred game sound loading — campaign includes transmission voice lines,
        # custom/multiplayer skips them (~75 fewer files to load)
        is_campaign = getattr(self.game, 'campaign_map', None) is not None
        tasks.extend(get_game_sound_tasks(is_campaign=is_campaign))

        # Initialize game state and load all game images/fonts as one task
        def _init_game():
            self.game.initialize_game(self.setup_config)
        tasks.append(("Initializing game", _init_game))

        return tasks

    def _draw(self):
        """Render one frame of the loading screen."""
        sw, sh = self.screen.get_size()

        # Dark background
        self.screen.fill((15, 15, 25))

        # Draw logo centered in upper third
        if self.logo:
            logo_rect = self.logo.get_rect(centerx=sw // 2, centery=int(sh * 0.3))
            self.screen.blit(self.logo, logo_rect)

        # Progress bar near the bottom of the screen (~2cm above edge)
        bar_width = int(sw * 0.6)
        bar_height = max(24, int(sh * 0.035))
        bar_x = (sw - bar_width) // 2
        bar_y = sh - bar_height - 75  # ~2cm above bottom edge

        # Background rect (dark grey)
        pygame.draw.rect(self.screen, (50, 50, 60),
                         (bar_x, bar_y, bar_width, bar_height))

        # Fill rect (gold/amber, proportional to progress)
        fill_width = int(bar_width * self.progress)
        if fill_width > 0:
            pygame.draw.rect(self.screen, (200, 170, 50),
                             (bar_x, bar_y, fill_width, bar_height))

        # Border rect (dark gold outline)
        pygame.draw.rect(self.screen, (120, 100, 40),
                         (bar_x, bar_y, bar_width, bar_height), 2)

        # Percentage text centered inside bar
        pct_text = f"{int(self.progress * 100)}%"
        pct_surface = self.font_large.render(pct_text, True, (255, 255, 255))
        pct_rect = pct_surface.get_rect(center=(sw // 2, bar_y + bar_height // 2))
        self.screen.blit(pct_surface, pct_rect)

        # Below bar: show task label while loading, replace with prompt when complete
        label_y = bar_y + bar_height + 15
        if self.loading_complete:
            # Replace task label with the "click to start" prompt
            if not self.is_multiplayer:
                prompt = "Click any key to continue"
                color = (220, 200, 120)
            elif self.all_players_ready:
                prompt = "Click any key to continue"
                color = (220, 200, 120)
            else:
                prompt = "Waiting for other players..."
                color = (180, 160, 100)
            prompt_surface = self.font_large.render(prompt, True, color)
            prompt_rect = prompt_surface.get_rect(centerx=sw // 2, top=label_y)
            self.screen.blit(prompt_surface, prompt_rect)
        elif self.current_label:
            # Show current task label while still loading
            label_surface = self.font_small.render(self.current_label, True, (180, 180, 180))
            label_rect = label_surface.get_rect(centerx=sw // 2, top=label_y)
            self.screen.blit(label_surface, label_rect)

        pygame.display.flip()

    def run(self):
        """Execute all tasks with progress bar, then wait for start signal."""
        tasks = self._build_task_list()
        total_tasks = len(tasks)

        # Phase 1: Execute each loading task with progress updates
        for i, (label, task_fn) in enumerate(tasks):
            self.current_label = label
            self.progress = i / total_tasks
            self._draw()

            # Pump events during loading to keep window responsive
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            # Execute the loading task
            try:
                task_fn()
            except Exception as e:
                logger.error(f"Loading task '{label}' failed: {e}")
                # Continue loading remaining tasks even if one fails

            self.clock.tick(60)

        # Loading complete
        self.progress = 1.0
        self.loading_complete = True
        self.current_label = "Loading complete"
        self._draw()

        # Phase 2: Multiplayer - send GAME_READY to remote players
        if self.is_multiplayer:
            self._send_game_ready()

        # Phase 3: Wait for player input (and multiplayer readiness)
        # Single-player: any click/keypress starts the game
        # Multiplayer: must also wait for all remote players to be ready
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                    if not self.is_multiplayer:
                        # Single-player: start immediately on click/key
                        waiting = False
                    elif self.all_players_ready:
                        # Multiplayer: only allow start when all players ready
                        waiting = False

            # Poll for multiplayer readiness messages
            if self.is_multiplayer and not self.all_players_ready:
                self._poll_network_ready()

            self._draw()
            self.clock.tick(30)

    def _send_game_ready(self):
        """Send GAME_READY to remote player(s) indicating loading is done."""
        player_index = getattr(self.game, 'local_player_index', 0)
        message = self.protocol.create_game_ready(player_index)

        if self.is_host:
            # Host broadcasts to all connected clients
            self.network_connection.broadcast_message(message)
        else:
            # Client sends to server (which forwards to host)
            self.network_connection.send_message(message)

        logger.info(f"Sent GAME_READY (player {player_index})")

        # If host has no remote human players (all AI), skip waiting
        if self.is_host and self.expected_remote_count == 0:
            self.all_players_ready = True

    def _poll_network_ready(self):
        """Non-blocking check for incoming GAME_READY messages."""
        if not self.network_connection:
            return

        # Drain the message queue looking for GAME_READY
        # PING/PONG is handled by network threads automatically, so we only
        # need to process game-level messages here
        max_msgs = 20  # Prevent infinite loop on queue flooding
        for _ in range(max_msgs):
            msg = self.network_connection.message_queue.get_incoming_message()
            if msg is None:
                break

            msg_type = msg.get('type')

            if msg_type == MessageType.GAME_READY:
                remote_player = msg.get('data', {}).get('player_index')
                logger.info(f"Received GAME_READY from player {remote_player}")

                if self.is_host:
                    # Host tracks which clients are ready
                    if remote_player is not None:
                        self.remote_ready_players.add(remote_player)

                    # Check if all expected remote players are ready
                    if len(self.remote_ready_players) >= self.expected_remote_count:
                        # All clients loaded — broadcast GAME_READY back to confirm
                        confirm = self.protocol.create_game_ready(0)
                        self.network_connection.broadcast_message(confirm)
                        self.all_players_ready = True
                        logger.info("All players ready — game starting")
                else:
                    # Client: receiving GAME_READY from host means everyone is ready
                    self.all_players_ready = True
                    logger.info("Host confirmed all players ready — game starting")
            else:
                # Non-GAME_READY messages during loading are unexpected but harmless;
                # log them for debugging
                logger.debug(f"Received unexpected message during loading: {msg_type}")
