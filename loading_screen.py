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
import random
import pygame

from network_config import MessageType
from global_sound import get_game_sound_tasks
from utils.logger import get_logger
from utils.cursor import draw_custom_cursor

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Loading screen tip pools
# Custom game tips — general gameplay info, one is randomly selected per load
# ---------------------------------------------------------------------------
CUSTOM_TIPS = [
    # Units & Combat
    "Swordsmen beat Pikemen, Pikemen beat Cavalry, Cavalry beat Archers, Archers beat Swordsmen.",
    "Counter advantages grant massive strength boost in battle. In 1 on 1 fight, 1 Counter can beat up to 4 Countered armies!",
    "Archers are the cheapest unit at 20 gold, while Cavalry are the most expensive at 40.",
    "Combat in Avareon is deterministic \u2014 the same matchup always produces the same result (except in perfectly tied battles).",
    "In battle, lower-level units are the first to die.",
    "A perfectly tied battle is resolved by a coin flip \u2014 the only element of chance in combat.",
    "You can queue up to 4 units at a single Barracks.",
    "Each unit takes one turn to train and one additional turn to get ready for movement. The unit can still defend while getting ready.",
    "Pikemen are the most expensive infantry at 30 gold, but they hard-counter Cavalry.",
    "Countered units also take priority as casualties \u2014 send the right composition.",
    # Veterancy
    "Units gain experience through combat, reaching up to +75% strength at level 5.",
    "Veteran units survive longer \u2014 casualties are always taken from the lowest-level units first.",
    "Farms and Mines gain experience passively over time, earning up to +50% bonus income at level 5.",
    # Buildings
    "Farms cost 30 gold and generate 10 income per turn - less investment for less profit.",
    "Mines cost 40 gold but generate 15 income per turn \u2014 a stronger investment.",
    "The Square multiplies all income from its territory by 1.5x. Multiple Squares stack.",
    "A Barracks is required to train military units in a territory.",
    "Keeps provide +2 effective defense armies and are required to house Heroes.",
    "Upgrading a Keep to a Castle costs 150 gold and unlocks advanced technologies.",
    "Each territory has a limited number of building plots \u2014 plan your construction carefully.",
    "Demolishing a building refunds 50% of its original cost.",
    "You can only begin constructing one building per territory per turn.",
    # Economy
    "Each territory has a base income ranging from 10 to 20 gold per turn.",
    "Higher taxation encourages spending \u2014 unspent gold is taxed at the end of each turn.",
    "Cancelling a unit in training refunds the exact gold you originally paid.",
    "Two Squares in one territory multiply income by 2.25x.",
    # Heroes
    "You can train up to 3 heroes at once, or 4 with the Heroic Fortitude technology.",
    "Each hero type can only be trained once per player \u2014 choose wisely.",
    "Heroes require a Keep to begin training. If the Keep falls mid-training, the hero is lost.",
    "Darius Brennhen is the cheapest hero at 150 gold and trains in just 2 turns.",
    "Aidam Narn's Legacy of the Empire provides +50% base income from all territories (does not affect income from buildings).",
    "Seledra Rennervail's Defiance protects nearby territories from enemy hero abilities.",
    "Vearen Asford's Pillage rewards 200 gold each time you destroy an enemy Keep.",
    "Erec Silvyr's Confiscate turns demolishing Farms and Mines into profit at 175% refund.",
    "Neil Hevilneu's Decisive Strike can remove half the armies from an enemy territory.",
    "Evain Nithieln's Embargo blocks all enemy income for an entire turn.",
    "A killed hero can be retrained if you still have a Keep, enough gold, and a free hero slot.",
    # Technology
    "The technology tree contains 21 technologies across economy, military, and command.",
    "Castle-tier technologies require owning at least one Castle to research.",
    "Supply and Demand increases Square multipliers from 1.5x to 2.5x per Square and is a significant late-game economy boost.",
    "Timer limits can be increased by researching Master Planner technologies.",
    "Last Resort doubles Keep and Castle defense when a hero is stationed there.",
    "Improved Command technologies raise your army limit from 75 up to 145.",
    # Territorial Bonuses
    "Every territory grants a unique stacking permanent bonus \u2014 from income boosts to unit strength.",
    "Unit strength bonuses from territories apply to all your units of that type everywhere.",
    "Building Cost territories reduce the price of all your buildings by 15% each.",
    # Strategy & General
    "Constructing a Keep in your capital territory in Capital Assault mode is a good defensive option.",
    "Allied players share vision of each other's movement orders.",
    "While winning battles as an alliance, the stronger ally is able to choose the new territory's owner.",
    "Stronger armies force the weaker armies to defend their territory when they meet halfway.",
]

# Campaign mission tips — 3 per mission, one randomly selected per load
CAMPAIGN_TIPS = {
    'mission_1': [
        "Build multiple Barracks to increase your training speed.",
        "Pay attention to the unit counter system \u2014 Swordsmen beat Pikemen, but fall to Archers.",
        "Units gain experience when winning battles, increasing their combat effectiveness.",
    ],
    'mission_2': [
        "Dormant factions won't act until provoked. Choose your expansion order carefully.",
        "Your starting Cavalry are strong against Archers but vulnerable to the enemy's Pikemen.",
        "Attacking one faction may awaken others \u2014 be ready for chain reactions.",
    ],
    'mission_3': [
        "Affrancia will attack from the very first turn \u2014 prioritize your defenses early.",
        "Capturing Affrancian territories for the first time will yield defectors to your cause.",
        "Not all alliances in Avareon are built to last. Keep reserves for the unexpected.",
    ],
    'mission_4': [
        "Your veteran units and pre-researched technologies give you a crucial early advantage.",
        "Enemy factions grow more aggressive with each passing turn \u2014 expand quickly.",
        "The Ahtep Empire is a formidable enemy, but not required to defeat for victory.",
    ],
}


class LoadingScreen:
    """
    Renders a progress bar while executing deferred asset loading tasks,
    then waits for player input (and multiplayer readiness) before starting.
    """

    def __init__(self, screen, game, setup_config, network_connection=None,
                 mission_id=None):
        """
        Args:
            screen: Pygame display surface
            game: Game instance (Game.__init__ already called)
            setup_config: Config dict to pass to game.initialize_game()
            network_connection: NetworkServer (host) or NetworkClient (client), or None for SP
            mission_id: Campaign mission key (e.g. 'mission_1') or None for custom/MP games
        """
        self.screen = screen
        self.game = game
        self.setup_config = setup_config
        self.network_connection = network_connection
        self.mission_id = mission_id

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
        # Reuse the network connection's protocol to maintain correct sequence numbers.
        # A fresh protocol resets seq to 0, which the server's anti-replay check
        # (server.py _handle_received_message) rejects as duplicate since the lobby
        # phase already advanced the server's tracked seq for this client.
        if self.is_multiplayer and network_connection:
            self.protocol = network_connection.protocol
        else:
            self.protocol = None

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

        # Select a random tip based on game mode (campaign mission vs custom)
        self._select_tip()

    def _load_screen_assets(self):
        """Load background image, logo and create fonts for the loading screen."""
        sw, sh = self.screen.get_size()

        # Load background image, scaled to fill the screen
        self.background = None
        try:
            raw_bg = pygame.image.load('assets/LoadingScreen.png').convert()
            self.background = pygame.transform.smoothscale(raw_bg, (sw, sh))
        except pygame.error:
            logger.warning("Could not load LoadingScreen.png for loading screen")

        # Load Cinzel fonts for consistent look with the rest of the game
        self.font_large = None
        self.font_small = None
        self.font_tip_label = None  # Bold font for "TIP:" label
        try:
            font_size_large = max(16, int(sh * 0.032))
            font_size_small = max(12, int(sh * 0.022))
            self.font_large = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size_large)
            self.font_small = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', font_size_small)
            self.font_tip_label = pygame.font.Font('assets/fonts/Cinzel-Bold.ttf', font_size_large)
        except (pygame.error, FileNotFoundError):
            # Fallback to system font if Cinzel not available
            logger.warning("Could not load Cinzel font for loading screen, using system font")
            self.font_large = pygame.font.SysFont('arial', max(16, int(sh * 0.032)))
            self.font_small = pygame.font.SysFont('arial', max(12, int(sh * 0.022)))
            self.font_tip_label = self.font_large

    def _select_tip(self):
        """Select a random tip based on game mode (campaign mission vs custom)."""
        if self.mission_id and self.mission_id in CAMPAIGN_TIPS:
            self.tip_text = random.choice(CAMPAIGN_TIPS[self.mission_id])
        else:
            self.tip_text = random.choice(CUSTOM_TIPS)

    @staticmethod
    def _wrap_text(text, font, max_width):
        """Word-wrap text to fit within max_width. Returns list of line strings."""
        words = text.split(' ')
        lines = []
        current_line = ''
        for word in words:
            test_line = (current_line + ' ' + word).strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines if lines else [text]

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

        # Background image, falling back to dark solid fill
        if self.background:
            self.screen.blit(self.background, (0, 0))
        else:
            self.screen.fill((15, 15, 25))

        # Progress bar near the bottom of the screen (~2cm above edge)
        bar_width = int(sw * 0.6)
        bar_height = max(24, int(sh * 0.035))
        bar_x = (sw - bar_width) // 2
        bar_y = sh - bar_height - 75  # ~2cm above bottom edge

        # Draw tip text just above the progress bar
        if self.tip_text:
            tip_max_width = int(sw * 0.6)  # Same width as progress bar
            tip_lines = self._wrap_text(self.tip_text, self.font_small, tip_max_width)

            # Calculate total height: "TIP:" label + spacing + wrapped tip lines
            label_h = self.font_tip_label.get_linesize()
            line_h = self.font_small.get_linesize()
            spacing = 6
            total_tip_height = label_h + spacing + line_h * len(tip_lines)

            # Position tip block directly above the progress bar with a small gap
            tip_start_y = bar_y - total_tip_height - 15

            # "TIP:" label in gold using Cinzel-Bold
            tip_label_surf = self.font_tip_label.render("TIP:", True, (220, 200, 120))
            tip_label_rect = tip_label_surf.get_rect(centerx=sw // 2, top=tip_start_y)
            self.screen.blit(tip_label_surf, tip_label_rect)

            # Tip content lines in white
            line_y = tip_start_y + label_h + spacing
            for line in tip_lines:
                line_surf = self.font_small.render(line, True, (255, 255, 255))
                line_rect = line_surf.get_rect(centerx=sw // 2, top=line_y)
                self.screen.blit(line_surf, line_rect)
                line_y += line_h

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
            # Replace task label with prompt based on readiness state
            if not self.is_multiplayer:
                # Single-player: just click to start
                prompt = "Click any key to continue"
                color = (220, 200, 120)
            elif not self.local_ready:
                # Multiplayer: local player hasn't clicked yet
                prompt = "Click any key when ready"
                color = (220, 200, 120)
            else:
                # Multiplayer: local player clicked, waiting for others
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

        draw_custom_cursor(self.screen)
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

        # Phase 2: Wait for player input (and multiplayer readiness)
        # Single-player: any click/keypress starts the game
        # Multiplayer: click sends GAME_READY, game auto-starts when all players ready
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
                    elif not self.local_ready:
                        # Multiplayer: first click marks local player as ready
                        self.local_ready = True
                        self._send_game_ready()
                        # If all remote players already ready, start immediately
                        if self.all_players_ready:
                            waiting = False

            # Poll for multiplayer readiness messages
            if self.is_multiplayer and not self.all_players_ready:
                self._poll_network_ready()

            # Auto-start when all players (including local) are ready
            if self.is_multiplayer and self.local_ready and self.all_players_ready:
                waiting = False

            self._draw()
            self.clock.tick(30)

    def _send_game_ready(self):
        """Send GAME_READY to remote player(s) indicating loading is done."""
        player_index = getattr(self.game, 'local_player_index', 0)
        message = self.protocol.create_game_ready(player_index)

        if self.is_host:
            # Host does NOT broadcast its own readiness — only broadcasts
            # confirmation when all remote players are also ready. This prevents
            # the client from misinterpreting "host is ready" as "all ready."
            if len(self.remote_ready_players) >= self.expected_remote_count:
                confirm = self.protocol.create_game_ready(0)
                self.network_connection.broadcast_message(confirm)
                self.all_players_ready = True
                logger.info("All players ready at host click — game starting")
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

                    # Check if all expected remote players AND the host are ready.
                    # Require local_ready so host only broadcasts confirmation
                    # when it has also clicked ready (not just when clients are ready).
                    if self.local_ready and len(self.remote_ready_players) >= self.expected_remote_count:
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
