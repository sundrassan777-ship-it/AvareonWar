# -*- coding: utf-8 -*-
# tutorial_mission.py
# Tutorial campaign mission - scripted 23-step sequence that teaches game basics.
# Acts as a choreography layer on top of existing game systems.
# All combat, rendering, buildings, armies use existing game code unchanged.

import math
import time
import pygame
import map_data
from utils.logger import get_logger

logger = get_logger(__name__)

# Territories that can be hovered/clicked during the tutorial
# All other territories are visually inactive (no hover, no click response)
TUTORIAL_TERRITORIES = {
    'Zjoal Islands', 'Damlére', 'Lunedale', 'Free Cities',
    'March of Auverne', 'Affrancian Uplands', 'Carnae'
}


class TutorialStep:
    """Configuration for a single tutorial step."""

    def __init__(self, step_id, transmission_text='', transmission_duration=0,
                 allowed_actions=None, highlight_plots=None, highlight_buttons=None,
                 movement_whitelist=None, quest_add=None, quest_complete=None,
                 on_enter=None, highlight_territory=None):
        self.step_id = step_id
        self.transmission_text = transmission_text
        # Duration in seconds. 0 = wait for player action to advance.
        self.transmission_duration = transmission_duration
        # Dict of action permissions. Keys: 'build', 'train', 'move', 'end_turn',
        # 'click_map', 'click_plots', 'camera', 'click_barracks', 'click_army'.
        # Values: True/False, or list of allowed types (e.g. ['Farm']).
        # None/missing key = blocked.
        self.allowed_actions = allowed_actions or {}
        # List of (territory, plot_index) tuples to highlight green
        self.highlight_plots = highlight_plots or []
        # List of button IDs to highlight green: 'end_turn', 'building_Farm',
        # 'training_Swordsman', 'select_all', 'barracks_<territory>'
        self.highlight_buttons = highlight_buttons or []
        # Movement destination whitelist: {from_territory: [allowed_destinations]}
        self.movement_whitelist = movement_whitelist or {}
        # Quest text to add to quest log when entering this step
        self.quest_add = quest_add
        # Quest text to mark as completed when entering this step
        self.quest_complete = quest_complete
        # Callback when entering this step (receives tutorial_mission as arg)
        self.on_enter = on_enter
        # Territory name to highlight with bright overlay (e.g. attack target)
        self.highlight_territory = highlight_territory


class TransmissionOverlay:
    """Renders the Transmission Board with speaker header, flush at top-left of map area."""

    def __init__(self, screen_width, screen_height, text, top_panel_height, speaker=""):
        self.text = text
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.top_panel_height = top_panel_height
        self.speaker = speaker

        # Board dimensions: ~29% screen width (full image including transparent padding)
        self.width = int(screen_width * 0.29)

        # TransmissionBG.png has transparent padding around the visible wooden board.
        # These fractions (measured from the source image) let us align the header
        # with the visible board area and eliminate visual gaps.
        BG_LEFT_FRAC = 0.069   # 6.9% left/right transparent margin
        BG_TOP_FRAC = 0.200    # 20% top transparent margin

        # Load and scale body background (TransmissionBG.png)
        try:
            raw_bg = pygame.image.load('assets/TransmissionBG.png').convert_alpha()
        except pygame.error:
            raw_bg = None

        if raw_bg:
            aspect = raw_bg.get_height() / raw_bg.get_width()
            self.body_height = int(self.width * aspect)
            self.bg_surface = pygame.transform.smoothscale(raw_bg, (self.width, self.body_height))
        else:
            self.body_height = int(screen_height * 0.12)
            self.bg_surface = None

        # Calculate visible body area insets (in scaled pixels)
        bg_left_inset = int(self.width * BG_LEFT_FRAC)
        bg_top_inset = int(self.body_height * BG_TOP_FRAC)
        visible_body_width = self.width - 2 * bg_left_inset

        # Load and scale speaker header (GMenuButton.png) to match visible body width
        try:
            raw_header = pygame.image.load('assets/SpeakerBG.png').convert_alpha()
        except pygame.error:
            raw_header = None

        if raw_header:
            header_aspect = raw_header.get_height() / raw_header.get_width()
            natural_header_h = int(visible_body_width * header_aspect)
            self.header_height = int(natural_header_h * 0.2)  # 20% of natural height
            self.header_surface = pygame.transform.smoothscale(
                raw_header, (visible_body_width, self.header_height))
        else:
            self.header_height = int(screen_height * 0.03)
            self.header_surface = None

        self.header_width = visible_body_width

        # Header: flush at screen left edge, just below top panel
        self.header_x = 0
        self.header_y = top_panel_height

        # Body: shifted left so visible board edge aligns with screen edge,
        # shifted up so visible board top touches header bottom
        self.body_x = -bg_left_inset
        self.body_y = self.header_y + self.header_height - bg_top_inset

        # Keep self.height for text padding calculations
        self.height = self.body_height

        # Body text font
        try:
            self.font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', max(14, int(screen_height / 47)))
        except (FileNotFoundError, OSError):
            self.font = pygame.font.SysFont('serif', max(14, int(screen_height / 47)))

        # Speaker name font (bold, slightly smaller)
        try:
            self.speaker_font = pygame.font.Font('assets/fonts/Cinzel-Bold.ttf', max(13, int(screen_height / 52)))
        except (FileNotFoundError, OSError):
            self.speaker_font = pygame.font.SysFont('serif', max(13, int(screen_height / 52)), bold=True)

    def set_text(self, text, speaker=None):
        """Update the displayed text and optionally the speaker."""
        self.text = text
        if speaker is not None:
            self.speaker = speaker

    def render(self, screen):
        """Draw the speaker header + transmission board overlay."""
        # Draw body first (TransmissionBG.png) — its transparent padding won't cover the header
        if self.bg_surface:
            screen.blit(self.bg_surface, (self.body_x, self.body_y))
        else:
            panel_rect = pygame.Rect(self.body_x, self.body_y, self.width, self.body_height)
            bg = pygame.Surface((self.width, self.body_height), pygame.SRCALPHA)
            bg.fill((20, 20, 30, 220))
            screen.blit(bg, (self.body_x, self.body_y))
            pygame.draw.rect(screen, (180, 160, 100), panel_rect, 2)

        # Draw speaker header (GMenuButton.png) on top
        if self.header_surface:
            screen.blit(self.header_surface, (self.header_x, self.header_y))
        else:
            hdr_bg = pygame.Surface((self.header_width, self.header_height), pygame.SRCALPHA)
            hdr_bg.fill((40, 30, 20, 230))
            screen.blit(hdr_bg, (self.header_x, self.header_y))
            pygame.draw.rect(screen, (180, 160, 100),
                             pygame.Rect(self.header_x, self.header_y,
                                         self.header_width, self.header_height), 2)

        # Draw speaker name centered on header
        if self.speaker:
            speaker_surface = self.speaker_font.render(self.speaker, True, (255, 255, 240))
            sx = self.header_x + (self.header_width - speaker_surface.get_width()) // 2
            sy = self.header_y + (self.header_height - speaker_surface.get_height()) // 2
            screen.blit(speaker_surface, (sx, sy))

        # Render wrapped text inside the visible body area
        padding_x = int(self.width * 0.12)
        padding_y = int(self.body_height * 0.25)
        text_area_width = self.width - 2 * padding_x
        self._render_wrapped_text(screen, self.text, self.body_x + padding_x,
                                  self.body_y + padding_y, text_area_width)

    def _render_wrapped_text(self, screen, text, x, y, max_width):
        """Render text with word wrapping."""
        words = text.split(' ')
        lines = []
        current_line = ''
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            test_surface = self.font.render(test_line, True, (255, 255, 255))
            if test_surface.get_width() > max_width and current_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)

        line_height = self.font.get_linesize()
        for i, line in enumerate(lines):
            line_surface = self.font.render(line, True, (255, 255, 240))
            screen.blit(line_surface, (x, y + i * line_height))


class CameraAnimation:
    """Smooth camera zoom animation from one zoom level to another, centered on a world point."""

    def __init__(self, camera_handler, start_zoom, target_zoom, duration, target_center_world,
                 screen_width, map_area_height):
        self.camera = camera_handler
        self.start_zoom = start_zoom
        self.target_zoom = target_zoom
        self.duration = duration
        self.target_center = target_center_world  # (world_x, world_y)
        self.screen_width = screen_width
        self.map_area_height = map_area_height  # Height of map area (excludes top panel)
        self.elapsed = 0.0
        self.active = True

        # Set starting zoom and position
        self.camera.zoom = start_zoom
        self._update_camera_position(0.0)

    def update(self, delta_time):
        """Update animation each frame. Returns True while still animating."""
        if not self.active:
            return False
        self.elapsed += delta_time
        progress = min(1.0, self.elapsed / self.duration)

        # Ease-out cubic for smooth deceleration
        eased = 1.0 - pow(1.0 - progress, 3)

        # Interpolate zoom continuously.
        # This used to be quantized to 0.2 steps (`round(raw_zoom * 5) / 5`) purely to
        # limit how often the map rescale and the production-glow sprite cache were
        # invalidated — which made the intro visibly STEP rather than glide. Both of
        # those costs are gone: the map now rescales only the visible slice (~2.5ms
        # instead of up to 53ms) and glow frames are shared and quantized internally.
        self.camera.zoom = self.start_zoom + (self.target_zoom - self.start_zoom) * eased

        # Keep target centered
        self._update_camera_position(eased)

        if progress >= 1.0:
            # Snap to exact target on final frame for precision
            self.camera.zoom = self.target_zoom
            self._update_camera_position(1.0)
            self.active = False
        return self.active

    def _update_camera_position(self, progress):
        """Adjust camera offset to keep target_center in screen center."""
        # Screen center in screen coordinates (accounting for top panel offset)
        screen_cx = self.screen_width / 2.0
        screen_cy = self.map_area_height / 2.0

        # Camera offset = world position that appears at screen top-left
        # world_pos = screen_pos / zoom + offset
        # To center target: offset = target - screen_center / zoom
        self.camera.offset[0] = self.target_center[0] - screen_cx / self.camera.zoom
        self.camera.offset[1] = self.target_center[1] - screen_cy / self.camera.zoom
        self.camera.clamp_to_bounds()


class TutorialMission:
    """
    Main tutorial orchestrator. Manages the 23-step scripted sequence.

    Integrates with existing game systems via:
    - is_action_allowed() — gates all player actions
    - get_adjacency_override() — restricts movement destinations
    - should_highlight_plot/button() — visual cues
    - notify_event() — receives events from game hooks
    - update()/render() — called each frame from main.py game loop
    """

    # Sidebar tabs that remain unlocked throughout the tutorial
    ALWAYS_UNLOCKED_TABS = ['quests', 'action_log', 'action_queue', 'chat']

    # Mapping from step_id → transmission voice line number (T1.mp3 - T27.mp3)
    # Only steps with non-empty transmission_text have a voice line.
    STEP_TO_VOICE = {
        2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 9: 7, 11: 8, 12: 9,
        13: 10, 14: 11, 16: 12, 18: 13, 19: 14, 20: 15, 21: 16,
        23: 17, 25: 18, 26: 19, 27: 20, 29: 21, 30: 22, 34: 23,
        35: 24, 36: 25, 37: 26, 39: 27
    }

    def __init__(self, game_state, main_game):
        self.game_state = game_state
        self.main_game = main_game
        self.mission_id = 'mission_1'  # For achievement tracking
        self.current_step_index = 0
        self.step_timer = 0.0  # Timer for timed steps
        self.active = True
        self.block_ai = True  # Prevent normal AI execution

        # Transmission overlay (created when needed)
        self.transmission_overlay = None
        self._tb_visible = False

        # Camera animation (created in step 1)
        self.camera_animation = None

        # Quest log: list of {'text': str, 'completed': bool}
        self.quest_log = []

        # Phase 2: Flag to track if AI turn announcement completed during steps 29-30
        self._ai_announcement_done_pending = False

        # Inter-transmission pause: 1-second gap between consecutive timed transmissions
        self._inter_transmission_pause = 0.0

        # Deferred battle advance: delay step advancement until battle popup is closed
        # so voice lines don't play over the battle report screen
        self._pending_battle_advance = False
        self._pending_conquest_data = None  # Stores (territory, new_owner) for deferred conquest

        # Victory sequence state: freeze game and play ending animation
        self.game_frozen = False  # When True, blocks turn advancement
        self.victory_sequence_active = False
        self.victory_phase = None  # 'fade', 'image_grow', 'image_hold', 'exit'
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0  # 0-255 for fade to black
        self.victory_image = None
        self.victory_image_scale = 0.0  # 0.0 to 1.0 for grow animation

        # Build the step sequence
        self.steps = []
        self._build_steps()

        # Set up initial game state (territories, armies, buildings, gold)
        self._setup_initial_state()

        # Bake cloud cover into map image (covers non-mission territory areas)
        self._bake_cloud_cover()

        # Enter the first step
        self._enter_step(0)

    def _setup_initial_state(self):
        """Configure the game state for the tutorial scenario."""
        gs = self.game_state

        # Swap colors: Player 0 = Blue (human), Player 1 = Red (enemy)
        gs.player_colors[0] = (100, 150, 255)   # Blue for human
        gs.player_colors[1] = (255, 100, 100)    # Red for enemy

        # Swap flag icons to match swapped colors (default: 0=Red, 1=Blue)
        # After swap: Player 0 should use Blue flags, Player 1 should use Red flags
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and 0 in game.army_flag_icons and 1 in game.army_flag_icons:
            game.army_flag_icons[0], game.army_flag_icons[1] = game.army_flag_icons[1], game.army_flag_icons[0]

        # Player 0 (Blue) owns Lunedale — 300 Gold, no starting armies
        # Player name uses profile name from settings (not overridden here)
        gs.territory_owners['Lunedale'] = 0
        gs.invalidate_territorial_bonus_cache()  # Ownership changed
        gs.player_gold[0] = 300

        # Clear default starting armies from Lunedale (initialize_game creates 3 units)
        gs.set_garrison_armies('Lunedale', 0, unmoved=0, moved=0, units=[])
        gs.sync_legacy_garrison_data('Lunedale')

        # Player 1 (Red / Hostile Tribes) — enemy territories with armies and buildings
        gs.player_names[1] = 'Hostile Tribes'

        enemy_territories = {
            'Free Cities': {
                'armies': [{'type': 'Pikeman', 'id': 0, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0}],
                'buildings': {0: 'Farm', 1: 'Farm'}
            },
            'Affrancian Uplands': {
                'armies': [
                    {'type': 'Swordsman', 'id': 0, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0},
                    {'type': 'Swordsman', 'id': 1, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0}
                ],
                'buildings': {0: 'Barracks', 1: 'Farm'}
            },
            'March of Auverne': {
                'armies': [
                    {'type': 'Cavalry', 'id': 0, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0},
                    {'type': 'Pikeman', 'id': 1, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0},
                    {'type': 'Pikeman', 'id': 2, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0},
                    {'type': 'Swordsman', 'id': 3, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0}
                ],
                'buildings': {0: 'Barracks', 1: 'Farm'}
            },
            'Damlére': {
                'armies': [{'type': 'Pikeman', 'id': 0, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0}],
                'buildings': {0: 'Keep'}
            }
        }

        for territory, config in enemy_territories.items():
            gs.territory_owners[territory] = 1
            # Clear any pre-existing garrisons from default game init
            gs.territory_garrisons[territory] = {}
            # Set garrison with army composition
            units = config['armies']
            unmoved = len(units)
            gs.set_garrison_armies(territory, 1, unmoved=unmoved, moved=0, units=units)
            # Set completed buildings
            if territory not in gs.buildings:
                gs.buildings[territory] = {}
            for plot_idx, building_type in config['buildings'].items():
                gs.buildings[territory][plot_idx] = building_type

        # Clear non-mission territories to prevent stale state from previous games
        mission_territories = TUTORIAL_TERRITORIES | {'Lunedale'}
        for territory in list(gs.territory_owners.keys()):
            if territory not in mission_territories:
                gs.territory_owners[territory] = -1
                gs.territory_garrisons[territory] = {}
                gs.buildings[territory] = {}

        # Store starting territories for reference
        gs.player_starting_territories[0] = 'Lunedale'
        gs.player_starting_territories[1] = 'Free Cities'

    def _get_lunedale_plot_index(self):
        """Get the first available (empty) plot index in Lunedale for highlighting."""
        plots = map_data.get_plots('Lunedale')
        existing_buildings = self.game_state.buildings.get('Lunedale', {})
        under_construction = self.game_state.under_construction.get('Lunedale', {})
        for i in range(len(plots)):
            if i not in existing_buildings and i not in under_construction:
                return i
        return 0  # Fallback

    def _bake_cloud_cover(self):
        """Bake cloud cover directly into the map image.

        Loads CampaignMission1Cover.png, converts black background to transparency
        (pixel brightness → alpha), then blits it onto map_image_original.
        This eliminates separate overlay rendering and any UI clipping issues.
        Uses pure pygame (no numpy) for PyInstaller compatibility.
        """
        try:
            raw = pygame.image.load('assets/CampaignMaps/CampaignMission1Cover.png').convert()
        except pygame.error as e:
            logger.warning(f"Could not load CampaignMission1Cover.png: {e}")
            return

        w, h = raw.get_size()

        # Extract raw RGBA pixel data as a bytearray for bulk manipulation.
        # For each pixel, set alpha = max(R, G, B) so black → transparent, white → opaque.
        raw_str = pygame.image.tostring(raw, 'RGBA')
        pixels = bytearray(raw_str)
        for i in range(0, len(pixels), 4):
            pixels[i + 3] = max(pixels[i], pixels[i + 1], pixels[i + 2])

        # Reconstruct surface from modified pixel data
        cover = pygame.image.fromstring(bytes(pixels), (w, h), 'RGBA')

        # Scale cover to match map_image_original if sizes differ
        game = self.main_game
        map_w, map_h = game.map_image_original.get_size()
        if (w, h) != (map_w, map_h):
            cover = pygame.transform.smoothscale(cover, (map_w, map_h))

        # Blit cloud cover onto the original map image
        game.map_image_original.blit(cover, (0, 0))

        # Invalidate cached scaled map so it re-renders with the composited image
        game.cached_scaled_map = None
        game.cached_zoom_level = None

    def _build_steps(self):
        """Define the 23-step tutorial sequence."""
        # Helper: common locked-down state (nothing allowed)
        LOCKED = {}

        # Helper: sidebar tabs always available after step 5
        SIDEBAR_TABS = ['quests', 'action_log', 'action_queue', 'chat']

        # Step 1: Camera zoom starts. After 1 second, step advances (transmission appears).
        # Camera zooms from max (4.0) to min (1.65) over 1.5s. No input.
        self.steps.append(TutorialStep(
            step_id=1,
            transmission_text='',
            transmission_duration=1.0,  # Advance after 1 second
            allowed_actions=LOCKED,
        ))

        # Step 2: First transmission text appears during zoom
        self.steps.append(TutorialStep(
            step_id=2,
            transmission_text="Commander! I have been looking all over for you!",
            transmission_duration=4.0,
            allowed_actions=LOCKED,
        ))

        # Step 3: Second transmission
        self.steps.append(TutorialStep(
            step_id=3,
            transmission_text="We have information that the tribes have been attacking our outlying settlements. The chief wants us to prepare for a potential conflict with them.",
            transmission_duration=10.0,  # Voice line timing
            allowed_actions=LOCKED,
        ))

        # Step 4: Third transmission - prompt to build Farm
        self.steps.append(TutorialStep(
            step_id=4,
            transmission_text="The best defense starts with a solid foundation and good rationing! Start with building a Farm to boost our economic power!",
            transmission_duration=10.0,  # Voice line timing
            allowed_actions=LOCKED,
        ))

        # Step 5: Unlock camera, plots, Farm building. Highlight plot and Farm button.
        # TB disappears briefly for 1s then reappears — handled via on_enter callback
        self.steps.append(TutorialStep(
            step_id=5,
            transmission_text="Select a Plot and build a Farm in our region!",
            transmission_duration=0,  # Wait for player to build Farm
            allowed_actions={
                'camera': True, 'click_map': True, 'click_plots': True,
                'build': ['Farm'], 'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_plots=[],  # Will be set dynamically in on_enter
            highlight_buttons=['building_Farm'],
            quest_add="Build a Farm in Lunedale",
            on_enter=lambda t: t._on_enter_step5(),
        ))

        # Step 6: Farm built. Transmission changes. All highlights removed.
        self.steps.append(TutorialStep(
            step_id=6,
            transmission_text="Farms provide a steady amount of income to our coffers. They, like all buildings, take some time to build.",
            transmission_duration=9.0,
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
        ))

        # Step 7: Prompt to end turn. End Turn highlighted and unlocked.
        self.steps.append(TutorialStep(
            step_id=7,
            transmission_text="Give our people some time to build by ending our current turn.",
            transmission_duration=0,  # Wait for End Turn click
            allowed_actions={
                'camera': True, 'click_map': True, 'end_turn': True,
                'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_buttons=['end_turn'],
        ))

        # Step 8: Enemy turn starts. Wait for turn announcement to finish.
        # Transmission updates after announcement.
        self.steps.append(TutorialStep(
            step_id=8,
            transmission_text='',
            transmission_duration=0,  # Wait for notify_event('turn_announcement_done') for P2
            allowed_actions=LOCKED,
        ))

        # Step 9: Enemy turn — transmission about enemies doing nothing
        self.steps.append(TutorialStep(
            step_id=9,
            transmission_text="Now our enemies are taking actions. It seems that for now, they are doing nothing. Suspicious, is it not?",
            transmission_duration=9.0,
            allowed_actions=LOCKED,
        ))

        # Step 10: End AI turn, then wait for our turn announcement to finish.
        self.steps.append(TutorialStep(
            step_id=10,
            transmission_text='',
            transmission_duration=0,  # Wait for turn_announcement_done for P1
            allowed_actions=LOCKED,
            on_enter=lambda t: t._end_ai_turn(),
        ))

        # Step 11: Buildings finish. Inform player.
        self.steps.append(TutorialStep(
            step_id=11,
            transmission_text="At the start of our turn, our buildings finish! We can now supply our troops with fresh food from our Farm.",
            transmission_duration=8.0,
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
            quest_complete="Build a Farm in Lunedale",
        ))

        # Step 12: Need troops!
        self.steps.append(TutorialStep(
            step_id=12,
            transmission_text="But what troops? The Chief will have our heads to see that we have not yet assembled an army!",
            transmission_duration=7.0,
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
        ))

        # Step 13: Build Barracks. Plots highlighted.
        self.steps.append(TutorialStep(
            step_id=13,
            transmission_text="Build a Barracks in our territory to give us the access to train troops!",
            transmission_duration=0,  # Wait for Barracks build
            allowed_actions={
                'camera': True, 'click_map': True, 'click_plots': True,
                'build': ['Barracks'], 'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_plots=[],  # Set dynamically
            highlight_buttons=['building_Barracks'],
            quest_add="Build a Barracks in Lunedale",
            on_enter=lambda t: t._on_enter_step13(),
        ))

        # Step 14: Barracks built. End turn.
        self.steps.append(TutorialStep(
            step_id=14,
            transmission_text="We have once again exhausted our budget. Let us see what our enemies plot.",
            transmission_duration=0,
            allowed_actions={
                'camera': True, 'click_map': True, 'end_turn': True,
                'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_buttons=['end_turn'],
        ))

        # Step 15: Enemy turn again. Wait for announcement.
        self.steps.append(TutorialStep(
            step_id=15,
            transmission_text='',
            transmission_duration=0,
            allowed_actions=LOCKED,
        ))

        # Step 16: Enemy does nothing, text appears
        self.steps.append(TutorialStep(
            step_id=16,
            transmission_text="Even the Thunder God does not know what these rascals are up to...",
            transmission_duration=5.0,  # Voice line timing
            allowed_actions=LOCKED,
        ))

        # Step 17: End AI turn, then wait for our turn announcement.
        self.steps.append(TutorialStep(
            step_id=17,
            transmission_text='',
            transmission_duration=0,  # Wait for turn_announcement_done P1
            allowed_actions=LOCKED,
            on_enter=lambda t: t._end_ai_turn(),
        ))

        # Step 18: Text about Barracks. Click Barracks to open training.
        self.steps.append(TutorialStep(
            step_id=18,
            transmission_text="As we now have Barracks, we are able to create troops. Let us see what we have available at our disposal.",
            transmission_duration=0,  # Wait for barracks click
            allowed_actions={
                'camera': True, 'click_map': True, 'click_barracks': True,
                'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_buttons=['barracks_Lunedale'],
            quest_complete="Build a Barracks in Lunedale",
        ))

        # Step 19: Barracks open. Train Swordsmen.
        self.steps.append(TutorialStep(
            step_id=19,
            transmission_text="We can train four types of troops. For now, let us train a unit of Swordsmen.",
            transmission_duration=0,  # Wait for training action
            allowed_actions={
                'camera': True, 'click_map': True, 'click_barracks': True,
                'train': ['Swordsman'], 'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_buttons=['training_Swordsman'],
            quest_add="Recruit a unit of Swordsmen in Lunedale",
        ))

        # Step 20: Swordsmen queued. Info about counters. Timed, then end turn.
        self.steps.append(TutorialStep(
            step_id=20,
            transmission_text="Swordsmen are especially good against Pikemen, but beware, they are very weak against Archers. Archers are in turn weak against Cavalry and Cavalry is broken by Pikemen.",
            transmission_duration=14.0,  # Voice line timing
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
            quest_complete="Recruit a unit of Swordsmen in Lunedale",
        ))

        # Step 21: End turn prompt
        self.steps.append(TutorialStep(
            step_id=21,
            transmission_text="Troops take one turn to finish their training. Let us wait.",
            transmission_duration=0,
            allowed_actions={
                'camera': True, 'click_map': True, 'end_turn': True,
                'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_buttons=['end_turn'],
        ))

        # Step 22: Enemy turn. Wait for announcement.
        self.steps.append(TutorialStep(
            step_id=22,
            transmission_text='',
            transmission_duration=0,
            allowed_actions=LOCKED,
        ))

        # Step 23: Enemy does nothing
        self.steps.append(TutorialStep(
            step_id=23,
            transmission_text="Silence. They must be planning something huge.",
            transmission_duration=4.0,  # Voice line timing
            allowed_actions=LOCKED,
        ))

        # Step 24: End AI turn, then wait for our turn announcement.
        # Swordsmen ready override happens in notify_event when announcement done.
        self.steps.append(TutorialStep(
            step_id=24,
            transmission_text='',
            transmission_duration=0,
            allowed_actions=LOCKED,
            on_enter=lambda t: t._end_ai_turn(),
        ))

        # Step 25: Swordsmen ready. Info text.
        self.steps.append(TutorialStep(
            step_id=25,
            transmission_text="Our swordsmen are ready! Usually the newly trained army takes an additional turn to get their weapons, armor and rations in order, but these seem especially eager!",
            transmission_duration=12.0,  # Voice line timing
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
        ))

        # Step 26: Attack Free Cities. Click army composition, select all, order to Free Cities.
        self.steps.append(TutorialStep(
            step_id=26,
            transmission_text="The best defense is the offense! Order our swordsmen to attack the territory to the north and take it over for our chief!",
            transmission_duration=0,
            allowed_actions={
                'camera': True, 'click_map': True, 'click_army': True,
                'move': True, 'sidebar_tabs': SIDEBAR_TABS
            },
            movement_whitelist={'Lunedale': ['Free Cities']},
            highlight_buttons=['select_all'],
            quest_add="Conquer the territory of Free Cities",
            highlight_territory='Free Cities',
        ))

        # Step 27: Attack order created. End turn.
        self.steps.append(TutorialStep(
            step_id=27,
            transmission_text="Let us end our planning turn and send the army into the fray!",
            transmission_duration=0,
            allowed_actions={
                'camera': True, 'click_map': True, 'end_turn': True,
                'sidebar_tabs': SIDEBAR_TABS
            },
            highlight_buttons=['end_turn'],
            highlight_territory='Free Cities',
        ))

        # Step 28: Battle resolves. Player must click battle marker and resolve popup.
        # Camera + click_map allowed so the tutorial camera gate doesn't block all input.
        self.steps.append(TutorialStep(
            step_id=28,
            transmission_text='',
            transmission_duration=0,  # Wait for battle_won event
            allowed_actions={'camera': True, 'click_map': True},
        ))

        # Step 29: First victory! Quest complete, timed transmission.
        self.steps.append(TutorialStep(
            step_id=29,
            transmission_text="Glorious victory! These mongrels did not stand a chance!",
            transmission_duration=4.0,  # Voice line timing
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
            quest_complete="Conquer the territory of Free Cities",
        ))

        # ======================================================================
        # PHASE 2: Extended Tutorial (Steps 30-42)
        # AI counter-attack, technology research, partial freedom conquest
        # ======================================================================

        # Step 30: Short transition after victory (turn already ended after battle)
        # The player's turn ended when they clicked End Turn in step 27, so the AI
        # turn starts automatically after the battle resolves. This is a brief pause.
        self.steps.append(TutorialStep(
            step_id=30,
            transmission_text="Let us see how our enemies respond to our conquest...",
            transmission_duration=5.0,  # Voice line timing
            allowed_actions={
                'camera': True, 'click_map': True,
                'sidebar_tabs': SIDEBAR_TABS
            },
        ))

        # Step 31: Wait for AI turn announcement before scripted attack
        # If announcement already completed during step 29/30, on_enter advances immediately
        self.steps.append(TutorialStep(
            step_id=31,
            transmission_text='',
            transmission_duration=0,  # Wait for turn_announcement_done (AI turn)
            allowed_actions={},
            on_enter=lambda t: t._on_enter_step31(),
        ))

        # Step 32: AI turn - scripted Pikeman attack from Affrancian Uplands to Free Cities
        # Visible army movement animation over ~2 seconds, then advance
        self.steps.append(TutorialStep(
            step_id=32,
            transmission_text='',
            transmission_duration=0,  # Controlled by AI turn timer in update()
            allowed_actions={},  # Locked during AI scripted attack
            on_enter=lambda t: t._execute_scripted_ai_attack(),
        ))

        # Step 33: Auto-resolve the defense battle (player should win - Swordsmen counter Pikemen)
        self.steps.append(TutorialStep(
            step_id=33,
            transmission_text='',
            transmission_duration=0,  # Auto-resolve happens in update_ai_turn()
            allowed_actions={},
        ))

        # Step 34: Defense victory transmission
        self.steps.append(TutorialStep(
            step_id=34,
            transmission_text="Excellent! Our defenses held strong against their counter-attack! Swordsmen truly are the bane of Pikemen.",
            transmission_duration=9.0,  # Voice line timing
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
        ))

        # Step 35: Preparation text - introduce technology
        self.steps.append(TutorialStep(
            step_id=35,
            transmission_text="Now we must prepare for bigger challenges. The Technology Tree holds the key to our advancement!",
            transmission_duration=7.0,  # Voice line timing
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS},
        ))

        # Sidebar tabs with technology added
        SIDEBAR_TABS_WITH_TECH = ['quests', 'action_log', 'action_queue', 'chat', 'technology']

        # Step 36: Technology tab unlock - highlight Efficient Farming I
        self.steps.append(TutorialStep(
            step_id=36,
            transmission_text="Open the Technology tab and research Efficient Farming I to boost our economic output!",
            transmission_duration=0,  # Wait for player to start research
            allowed_actions={
                'camera': True, 'click_map': True,
                'sidebar_tabs': SIDEBAR_TABS_WITH_TECH,
                'research': ['tech_0_0']  # Only allow Efficient Farming I
            },
            highlight_buttons=['technology_tech_0_0', 'sidebar_technology'],
            quest_add="Research Efficient Farming I",
        ))

        # Step 37: Research started - partial freedom begins
        # Show both conquest objectives, then hide transmission after 8 seconds
        # Both quests appear simultaneously
        self.steps.append(TutorialStep(
            step_id=37,
            transmission_text="Excellent! While our scholars work, let us expand our territory. Conquer the Affrancian Uplands and March of Auverne!",
            transmission_duration=9.0,  # Show for 9 seconds, then hide
            allowed_actions={
                'camera': True, 'click_map': True, 'click_army': True,
                'move': True, 'end_turn': True, 'click_barracks': True,
                'click_keep': True, 'click_plots': True,
                'train': ['Swordsman', 'Archer', 'Pikeman', 'Cavalry'],
                'build': ['Farm', 'Barracks', 'Mine'],
                'sidebar_tabs': SIDEBAR_TABS_WITH_TECH,
                'research': True,  # Allow research (column 3 blocked in is_action_allowed)
                'cancel_training': True,
                'cancel_construction': True,
                'demolish': True,
                'cancel_order': True,
                'cancel_all_orders': True
            },
            movement_whitelist={
                'Lunedale': ['Free Cities', 'Affrancian Uplands'],
                'Free Cities': ['Affrancian Uplands', 'Lunedale'],
                'Affrancian Uplands': ['Free Cities', 'March of Auverne', 'Lunedale'],
                'March of Auverne': ['Affrancian Uplands']
            },
            quest_complete="Research Efficient Farming I",
            quest_add=["Conquer Affrancian Uplands", "Conquer March of Auverne"],  # Both quests at once
            on_enter=lambda t: t._setup_partial_freedom(),
        ))

        # Step 38: Transmission hidden, wait for BOTH territories conquered
        # Player has full partial freedom gameplay
        self.steps.append(TutorialStep(
            step_id=38,
            transmission_text='',  # No transmission - board hidden
            transmission_duration=0,  # Wait for both conquests
            allowed_actions={
                'camera': True, 'click_map': True, 'click_army': True,
                'move': True, 'end_turn': True, 'click_barracks': True,
                'click_keep': True, 'click_plots': True,
                'train': ['Swordsman', 'Archer', 'Pikeman', 'Cavalry'],
                'build': ['Farm', 'Barracks', 'Mine'],
                'sidebar_tabs': SIDEBAR_TABS_WITH_TECH,
                'research': True,  # Allow research (column 3 blocked in is_action_allowed)
                'cancel_training': True,
                'cancel_construction': True,
                'demolish': True,
                'cancel_order': True,
                'cancel_all_orders': True
            },
            movement_whitelist={
                'Lunedale': ['Free Cities', 'Affrancian Uplands'],
                'Free Cities': ['Affrancian Uplands', 'Lunedale'],
                'Affrancian Uplands': ['Free Cities', 'March of Auverne', 'Lunedale'],
                'March of Auverne': ['Affrancian Uplands']
            },
        ))

        # Step 39: Both territories conquered - final victory!
        # Game freezes (no turn swap), transmission for 8 seconds, then victory sequence
        self.steps.append(TutorialStep(
            step_id=39,
            transmission_text="Victory is ours! You have proven yourself a capable commander. The realm is secure... for now.",
            transmission_duration=9.0,  # 9 seconds, then fade to black + victory image
            allowed_actions={'camera': True, 'click_map': True, 'sidebar_tabs': SIDEBAR_TABS_WITH_TECH},
            quest_complete=["Conquer Affrancian Uplands", "Conquer March of Auverne"],  # Complete both
            on_enter=lambda t: t._on_enter_victory(),
        ))

    def _on_enter_step5(self):
        """Step 5 enter: set plot highlight to first available plot in Lunedale."""
        plot_idx = self._get_lunedale_plot_index()
        self.steps[4].highlight_plots = [('Lunedale', plot_idx)]

    def _on_enter_step13(self):
        """Step 13 enter: set plot highlight to next available plot in Lunedale."""
        plot_idx = self._get_lunedale_plot_index()
        self.steps[12].highlight_plots = [('Lunedale', plot_idx)]

    def _on_enter_step31(self):
        """Step 31 enter: check if AI turn announcement already completed during step 29/30."""
        if self._ai_announcement_done_pending:
            logger.debug("AI announcement was pending, advancing immediately")
            self._ai_announcement_done_pending = False  # Clear the flag
            self._advance_step()

    def _on_enter_victory(self):
        """Step 39 enter: freeze the game to prevent turn swaps."""
        logger.info("Victory step entered - freezing game")
        self.game_frozen = True

    def get_bonus_conditions(self):
        """Return bonus condition flags for achievement system. Tutorial has none."""
        return {}

    def _start_victory_sequence(self):
        """Start the victory sequence (called when step 39 timer expires)."""
        logger.info("Starting victory sequence")

        # Set game state for achievement tracking
        self.game_state.winner = 0
        self.game_state.phase = 'ended'

        # Clear hover tooltips so they don't persist over victory screen
        game = self.main_game
        game.hovered_territory = None
        game.hovered_army = None
        game.show_tooltip_army = None
        self.victory_sequence_active = True
        self.victory_phase = 'fade'
        self.victory_timer = 0.0
        self.victory_fade_alpha = 0
        self.victory_image_scale = 0.0

        # Load victory image
        try:
            self.victory_image = pygame.image.load('assets/victoryscrn.png').convert_alpha()
            logger.debug(f"Victory image loaded: {self.victory_image.get_size()}")
        except pygame.error as e:
            logger.warning(f"Could not load victoryscrn.png: {e}")
            self.victory_image = None

    def update_victory_sequence(self, delta_time):
        """Update the victory sequence animation. Returns 'exit' when done."""
        if not self.victory_sequence_active:
            return None

        self.victory_timer += delta_time

        if self.victory_phase == 'fade':
            # Fade to black over 0.5 seconds
            fade_duration = 0.5
            progress = min(self.victory_timer / fade_duration, 1.0)
            self.victory_fade_alpha = int(255 * progress)
            if progress >= 1.0:
                self.victory_phase = 'image_grow'
                self.victory_timer = 0.0
                logger.debug("Fade complete, starting image grow")

        elif self.victory_phase == 'image_grow':
            # Image grows from tiny to 75% of full size over 0.3 seconds
            grow_duration = 0.3
            progress = min(self.victory_timer / grow_duration, 1.0)
            # Ease-out for smoother animation, max scale is 0.75 (75% of original)
            self.victory_image_scale = 0.75 * (1.0 - (1.0 - progress) ** 2)
            if progress >= 1.0:
                self.victory_phase = 'image_hold'
                self.victory_timer = 0.0
                logger.debug("Image grow complete, holding for 5 seconds")

        elif self.victory_phase == 'image_hold':
            # Hold for 5 seconds
            hold_duration = 5.0
            if self.victory_timer >= hold_duration:
                self.victory_phase = 'exit'
                logger.debug("Hold complete, exiting to campaign")
                return 'exit'

        return None

    def render_victory_sequence(self, screen):
        """Render the victory sequence overlay."""
        if not self.victory_sequence_active:
            return

        screen_width, screen_height = screen.get_size()

        # Draw black overlay (fade)
        if self.victory_fade_alpha > 0:
            overlay = pygame.Surface((screen_width, screen_height))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(self.victory_fade_alpha)
            screen.blit(overlay, (0, 0))

        # Draw victory image (grows from center)
        if self.victory_phase in ('image_grow', 'image_hold') and self.victory_image:
            img_width, img_height = self.victory_image.get_size()

            # Scale the image
            scale = max(0.01, self.victory_image_scale)  # Minimum scale to avoid zero
            scaled_width = int(img_width * scale)
            scaled_height = int(img_height * scale)

            if scaled_width > 0 and scaled_height > 0:
                scaled_img = pygame.transform.smoothscale(self.victory_image, (scaled_width, scaled_height))

                # Center on screen
                x = (screen_width - scaled_width) // 2
                y = (screen_height - scaled_height) // 2
                screen.blit(scaled_img, (x, y))

    def is_territory_interactive(self, territory_name):
        """Check if a territory can be hovered/clicked during the tutorial."""
        if not self.active:
            return True  # No restriction when tutorial inactive
        return territory_name in TUTORIAL_TERRITORIES

    # ========================================================================
    # FRAME UPDATE AND RENDERING
    # ========================================================================

    def update(self, delta_time):
        """Called every frame from main.py game loop. Returns 'exit_campaign' to exit."""
        if not self.active:
            return None

        # Cap delta_time to prevent animation skipping from large frame hitches
        # (e.g. first frame smoothscale at high zoom can cause multi-second spike)
        delta_time = min(delta_time, 0.05)

        # Update victory sequence if active
        if self.victory_sequence_active:
            result = self.update_victory_sequence(delta_time)
            if result == 'exit':
                return 'exit_campaign'
            return None

        # Update camera animation
        if self.camera_animation and self.camera_animation.active:
            still_active = self.camera_animation.update(delta_time)
            if not still_active:
                logger.debug(f"Camera animation completed, zoom={self.camera_animation.camera.zoom}")

        # Skip turn announcement animation for AI players (fast AI turns)
        gs = self.game_state
        if gs.current_player != 0 and gs.turn_announcement_active:
            game = self.main_game
            if hasattr(game, 'turn_announcement_effect') and game.turn_announcement_effect:
                game.turn_announcement_effect.cleanup()
                game.turn_announcement_effect = None
            gs._complete_turn_announcement()

        # Process inter-transmission pause (1s gap between consecutive timed transmissions)
        if self._inter_transmission_pause > 0:
            self._inter_transmission_pause -= delta_time
            if self._inter_transmission_pause <= 0:
                self._inter_transmission_pause = 0
                self._advance_step()
            return None  # Don't process step timer during pause

        # Update step timer for timed steps
        current = self.steps[self.current_step_index]
        if current.transmission_duration > 0:
            self.step_timer += delta_time
            if self.step_timer >= current.transmission_duration:
                # Special case: step 39 (victory) starts the victory sequence instead of advancing
                if current.step_id == 39:
                    self._start_victory_sequence()
                else:
                    # Check if next step has a transmission — if so, insert 1s pause
                    next_idx = self.current_step_index + 1
                    if next_idx < len(self.steps) and self.steps[next_idx].transmission_text:
                        # Hide current overlay and stop voice during the pause gap
                        self.transmission_overlay = None
                        from global_sound import stop_transmission_sound
                        stop_transmission_sound()
                        self._inter_transmission_pause = 1.0
                    else:
                        # Next step has no text (transition step) — advance immediately
                        self._advance_step()

        return None

    def skip_transmission(self):
        """Skip the currently visible transmission (ESC key).

        Returns True if a transmission was skipped, False otherwise.
        - Timed steps (duration > 0): hide overlay, stop voice, advance immediately.
        - Event-driven steps (duration == 0): hide overlay only — player still
          needs to perform the required action to advance.
        """
        if not self.active or not self.transmission_overlay:
            return False
        # Don't skip during victory cinematic
        if self.victory_sequence_active:
            return False

        from global_sound import stop_transmission_sound
        stop_transmission_sound()
        self.transmission_overlay = None

        current = self.steps[self.current_step_index]
        if current.transmission_duration > 0:
            # Timed step: advance immediately (skip inter-transmission pause)
            self._inter_transmission_pause = 0
            if current.step_id == 39:
                # Final step triggers victory sequence
                self._start_victory_sequence()
            else:
                self._advance_step()
        # Event-driven steps (duration == 0): overlay hidden, step stays active
        return True

    def render(self, screen):
        """Called after normal game rendering to draw tutorial overlay."""
        if not self.active:
            return

        # Victory sequence takes over all rendering
        if self.victory_sequence_active:
            self.render_victory_sequence(screen)
            return

        current = self.steps[self.current_step_index]

        # Draw transmission board if there's text to show
        if current.transmission_text and self.transmission_overlay:
            self.transmission_overlay.render(screen)

    # ========================================================================
    # ACTION GATING
    # ========================================================================

    def is_action_allowed(self, action_type, **kwargs):
        """
        Check if a player action is permitted at the current step.

        Args:
            action_type: 'build', 'train', 'move', 'end_turn', 'click_map',
                        'click_plots', 'camera', 'click_barracks', 'click_army',
                        'sidebar_tab'
            **kwargs: Additional context (building_type, unit_type, from_territory,
                     to_territory, tab_name)

        Returns:
            True if action is allowed, False otherwise.
        """
        if not self.active:
            return True  # Tutorial not active, allow everything

        current = self.steps[self.current_step_index]
        allowed = current.allowed_actions

        if action_type == 'build':
            build_allowed = allowed.get('build')
            if not build_allowed:
                return False
            if isinstance(build_allowed, list):
                return kwargs.get('building_type') in build_allowed
            return bool(build_allowed)

        elif action_type == 'train':
            train_allowed = allowed.get('train')
            if not train_allowed:
                return False
            if isinstance(train_allowed, list):
                return kwargs.get('unit_type') in train_allowed
            return bool(train_allowed)

        elif action_type == 'move':
            move_allowed = allowed.get('move')
            if not move_allowed:
                return False
            # Check movement whitelist
            whitelist = current.movement_whitelist
            if whitelist:
                from_terr = kwargs.get('from_territory', '')
                to_terr = kwargs.get('to_territory', '')
                allowed_targets = whitelist.get(from_terr, [])
                return to_terr in allowed_targets
            return bool(move_allowed)

        elif action_type == 'end_turn':
            return bool(allowed.get('end_turn'))

        elif action_type == 'click_map':
            return bool(allowed.get('click_map'))

        elif action_type == 'click_plots':
            return bool(allowed.get('click_plots'))

        elif action_type == 'camera':
            return bool(allowed.get('camera'))

        elif action_type == 'click_barracks':
            return bool(allowed.get('click_barracks'))

        elif action_type == 'click_army':
            return bool(allowed.get('click_army'))

        elif action_type == 'sidebar_tab':
            tab_name = kwargs.get('tab_name', '')
            # Heroes tab is always locked throughout the tutorial
            if tab_name == 'heroes':
                return False
            tabs_allowed = allowed.get('sidebar_tabs', [])
            return tab_name in tabs_allowed

        elif action_type == 'research':
            # Gate technology research
            research_allowed = allowed.get('research')
            if not research_allowed:
                return False
            # Column 3 (tech_2_*) is always locked throughout the tutorial
            tech_id = kwargs.get('tech_id', '')
            if tech_id.startswith('tech_2_'):
                return False
            if isinstance(research_allowed, list):
                return tech_id in research_allowed
            return bool(research_allowed)

        # Cancel/demolish actions - check if explicitly allowed
        elif action_type == 'cancel_training':
            return bool(allowed.get('cancel_training'))

        elif action_type == 'cancel_construction':
            return bool(allowed.get('cancel_construction'))

        elif action_type == 'demolish':
            return bool(allowed.get('demolish'))

        elif action_type == 'cancel_order':
            return bool(allowed.get('cancel_order'))

        elif action_type == 'cancel_all_orders':
            return bool(allowed.get('cancel_all_orders'))

        return False

    def get_adjacency_override(self, territory):
        """
        Override adjacency for movement restrictions.
        Returns list of allowed neighbors, or None to use normal adjacency.
        Returns empty list [] if whitelist active but territory not in it (blocks all movement).
        """
        if not self.active:
            return None
        current = self.steps[self.current_step_index]
        if current.movement_whitelist:
            # Return empty list if territory not in whitelist - blocks all movement from there
            return current.movement_whitelist.get(territory, [])
        return None

    def should_highlight_plot(self, territory, plot_index):
        """Check if a plot should have a green highlight."""
        if not self.active:
            return False
        current = self.steps[self.current_step_index]
        return (territory, plot_index) in current.highlight_plots

    def get_ai_thinking_text(self):
        """Override AI thinking indicator to show unified 'Enemies thinking...' text."""
        return ("Enemies thinking...", "")

    def should_highlight_button(self, button_id):
        """Check if a button should have a green highlight."""
        if not self.active:
            return False
        current = self.steps[self.current_step_index]
        return button_id in current.highlight_buttons

    def is_button_locked(self, button_id):
        """
        Check if a button should be greyed out (locked).
        This is the inverse of highlighting — buttons not explicitly allowed are locked.
        """
        if not self.active:
            return False

        current = self.steps[self.current_step_index]
        allowed = current.allowed_actions

        # Building buttons: locked if build action doesn't include this type
        if button_id.startswith('building_'):
            building_type = button_id[len('building_'):]
            build_allowed = allowed.get('build')
            if not build_allowed:
                return True
            if isinstance(build_allowed, list):
                return building_type not in build_allowed
            return False

        # Training buttons: locked if train action doesn't include this type
        if button_id.startswith('training_'):
            unit_type = button_id[len('training_'):]
            train_allowed = allowed.get('train')
            if not train_allowed:
                return True
            if isinstance(train_allowed, list):
                return unit_type not in train_allowed
            return False

        # End turn button
        if button_id == 'end_turn':
            return not bool(allowed.get('end_turn'))

        # Technology buttons: check research permissions and column 3 lock
        if button_id.startswith('technology_'):
            tech_id = button_id[len('technology_'):]
            # Column 3 (tech_2_*) is always locked throughout tutorial
            if tech_id.startswith('tech_2_'):
                return True
            # Check general research permission
            research_allowed = allowed.get('research')
            if not research_allowed:
                return True
            if isinstance(research_allowed, list):
                return tech_id not in research_allowed
            return False

        return False

    # ========================================================================
    # EVENT NOTIFICATIONS (called from hooks in other modules)
    # ========================================================================

    def notify_event(self, event_type, **kwargs):
        """
        Receive gameplay events from hooked game systems.

        Events:
            'build_started' — player started construction (building_type, territory)
            'train_started' — player queued training (unit_type, territory)
            'order_created' — movement order created (from_territory, to_territory)
            'end_turn' — player clicked End Turn
            'turn_start' — new turn started (player_index)
            'turn_announcement_done' — turn announcement animation finished (player_index)
            'barracks_clicked' — player clicked a barracks
            'battle_won' — player won a battle (territory)
            'units_trained' — units finished training (territory, units)
            'research_started' — player started research (tech_id)
            'territory_conquered' — territory ownership changed (territory, new_owner)
        """
        if not self.active:
            return

        step = self.steps[self.current_step_index]
        step_id = step.step_id

        # Step 5: Wait for Farm build
        if step_id == 5 and event_type == 'build_started' and kwargs.get('building_type') == 'Farm':
            self._advance_step()

        # Step 7: Wait for End Turn
        elif step_id == 7 and event_type == 'end_turn':
            self._advance_step()

        # Step 8: Wait for turn announcement done (enemy turn P2)
        elif step_id == 8 and event_type == 'turn_announcement_done':
            self._advance_step()

        # Step 9: Timed (handled by update())
        # Step 10: Wait for turn announcement done (our turn P1)
        elif step_id == 10 and event_type == 'turn_announcement_done':
            self._advance_step()

        # Step 13: Wait for Barracks build
        elif step_id == 13 and event_type == 'build_started' and kwargs.get('building_type') == 'Barracks':
            self._advance_step()

        # Step 14: Wait for End Turn
        elif step_id == 14 and event_type == 'end_turn':
            self._advance_step()

        # Step 15: Wait for turn announcement done (enemy turn)
        elif step_id == 15 and event_type == 'turn_announcement_done':
            self._advance_step()

        # Step 17: Wait for turn announcement done (our turn)
        elif step_id == 17 and event_type == 'turn_announcement_done':
            self._advance_step()

        # Step 18: Wait for barracks click
        elif step_id == 18 and event_type == 'barracks_clicked':
            self._advance_step()

        # Step 19: Wait for Swordsman training
        elif step_id == 19 and event_type == 'train_started' and kwargs.get('unit_type') == 'Swordsman':
            self._advance_step()

        # Step 21: Wait for End Turn
        elif step_id == 21 and event_type == 'end_turn':
            self._advance_step()

        # Step 22: Wait for turn announcement done (enemy turn)
        elif step_id == 22 and event_type == 'turn_announcement_done':
            self._advance_step()

        # Step 24: Wait for turn announcement done (our turn — swordsmen ready)
        elif step_id == 24 and event_type == 'turn_announcement_done':
            # Override: set newly trained swordsmen to 'ready' instead of 'moved'
            self._override_swordsmen_ready()
            self._advance_step()

        # Step 26: Wait for attack order to Free Cities
        elif step_id == 26 and event_type == 'order_created':
            if kwargs.get('to_territory') == 'Free Cities':
                self._advance_step()

        # Step 27: Wait for End Turn
        elif step_id == 27 and event_type == 'end_turn':
            self._advance_step()

        # Step 28: Wait for battle won — defer advancement until popup closes
        # so T21 voice line doesn't play over the battle report screen
        elif step_id == 28 and event_type == 'battle_won':
            self._pending_battle_advance = True

        # Step 28: Deferred advance — popup closed by player
        elif step_id == 28 and event_type == 'battle_popup_closed':
            if self._pending_battle_advance:
                self._pending_battle_advance = False
                self._advance_step()

        # ======================================================================
        # PHASE 2 EVENT HANDLERS (Steps 30-39)
        # ======================================================================

        # Steps 29-30: Track if AI turn announcement completes during timed steps
        # The announcement might complete before we reach step 31
        elif step_id in (29, 30) and event_type == 'turn_announcement_done':
            logger.debug(f"AI turn announcement done during step {step_id}, caching for step 31")
            self._ai_announcement_done_pending = True

        # Step 31: Wait for AI turn announcement before scripted attack
        # If announcement already completed (flag set), on_enter will advance
        elif step_id == 31 and event_type == 'turn_announcement_done':
            self._advance_step()

        # Step 33: Wait for defense battle won (auto-resolved)
        elif step_id == 33 and event_type == 'battle_won':
            # Defense successful - advance to victory transmission
            logger.debug(f"Step 33 battle_won received! current_player={self.game_state.current_player}, turn_phase={self.game_state.turn_phase}")
            # Must reset turn_phase BEFORE calling _end_ai_turn(), because next_player()
            # blocks if turn_phase=='battles' and pending_battles is not empty.
            # The battle hasn't been popped yet (that happens after notify_event returns).
            self.game_state.turn_phase = 'planning'
            self._end_ai_turn()  # End AI turn before advancing
            logger.debug(f"After _end_ai_turn: current_player={self.game_state.current_player}, turn_phase={self.game_state.turn_phase}")
            self._advance_step()

        # Step 36: Wait for research started (Efficient Farming I)
        elif step_id == 36 and event_type == 'research_started':
            if kwargs.get('tech_id') == 'tech_0_0':
                self._advance_step()

        # Steps 37-38: Track territory conquests during partial freedom
        # Defer victory step jump until battle popup closes so T27 voice
        # doesn't play over the battle report screen
        elif step_id in (37, 38) and event_type == 'territory_conquered':
            self._on_territory_conquered(
                kwargs.get('territory'),
                kwargs.get('new_owner'),
                deferred=True  # Don't jump to victory yet — wait for popup close
            )

        # Steps 37-38: Deferred victory advance — popup closed by player
        elif step_id in (37, 38) and event_type == 'battle_popup_closed':
            if self._pending_conquest_data:
                territory, new_owner = self._pending_conquest_data
                self._pending_conquest_data = None
                self._on_territory_conquered(territory, new_owner, deferred=False)

    def execute_ai_turn_override(self):
        """
        Called instead of normal AI execution during tutorial.
        Enemy does nothing — the step system controls when next_player() is called.
        This just blocks normal AI logic from running.
        """
        # AI turn ending is controlled by the step system via _end_ai_turn()
        # called from on_enter callbacks of steps that follow AI turns.
        pass

    def update_ai_turn(self, delta_time):
        """
        Handle AI turn timing for scripted sequences.
        Returns True if AI turn is being managed, False otherwise.
        """
        if not self.active:
            return False

        step_id = self.steps[self.current_step_index].step_id

        # Step 32: Scripted AI attack with visible animation
        if step_id == 32 and hasattr(self, 'ai_attack_timer'):
            self.ai_attack_timer += delta_time

            # At 2 seconds, execute the movement orders (triggers animation)
            if self.ai_attack_timer >= 2.0 and not self.ai_orders_executed:
                logger.debug("Executing AI attack orders")
                self.game_state.execute_all_orders()
                self.ai_orders_executed = True

            # At 4 seconds, advance to battle step
            if self.ai_attack_timer >= 4.0:
                logger.debug("AI attack phase complete, advancing to battle")
                self._advance_step()
                # Cleanup state
                del self.ai_attack_timer
                del self.ai_orders_executed
            return True

        # Step 33: Auto-resolve the defense battle
        elif step_id == 33:
            if self.game_state.pending_battles:
                logger.debug("Auto-resolving defense battle")
                self.game_state.resolve_battle(0)

                # Clean up battle state that normally happens through UI popup flow:
                # 1. Remove resolved battles from pending_battles
                self.game_state.pending_battles = [
                    b for b in self.game_state.pending_battles if not b.resolved
                ]
                # 2. Reset turn phase to planning (battles complete)
                self.game_state.turn_phase = 'planning'
                # 3. Clear the ready_to_advance flag
                self.game_state.ready_to_advance_turn = False
                logger.debug(f"Battle cleanup done, pending={len(self.game_state.pending_battles)}, phase={self.game_state.turn_phase}")
            else:
                # No battle (shouldn't happen normally), just advance
                logger.warning("No battle to resolve, advancing")
                self._end_ai_turn()
                self._advance_step()
            return True

        # Steps 37-38: Partial freedom - AI waits 4s then ends turn
        elif step_id >= 37 and self.game_state.current_player == 1:
            if not hasattr(self, 'partial_freedom_ai_timer'):
                self.partial_freedom_ai_timer = 0.0
                logger.debug("Starting partial freedom AI turn timer")

            self.partial_freedom_ai_timer += delta_time

            if self.partial_freedom_ai_timer >= 4.0:
                logger.debug("Partial freedom AI turn complete")
                self._end_ai_turn()
                del self.partial_freedom_ai_timer
            return True

        return False

    def _execute_scripted_ai_attack(self):
        """
        Step 32: Script an AI Pikeman attack from Damlére to Free Cities.
        Called on step 32 enter.
        """
        logger.debug("Setting up scripted AI attack")
        gs = self.game_state

        # Get AI player's garrison in Damlére
        territory = 'Damlére'
        player = 1  # AI player

        garrison = gs.territory_garrisons.get(territory, {}).get(player)
        if garrison:
            # Find Pikeman units (or any available units)
            units = garrison.get('units', [])
            available_units = [u for u in units if u['status'] == 'ready']

            if available_units:
                # Send first available unit to attack Free Cities
                unit_ids = [available_units[0]['id']]
                logger.debug(f"Creating AI attack order: {territory} -> Free Cities, units={unit_ids}")

                success = gs.add_movement_order_for_units(
                    territory, 'Free Cities', unit_ids, player=player
                )
                if success:
                    logger.debug("AI attack order created successfully")
                else:
                    logger.error("Failed to create AI attack order")
            else:
                logger.warning(f"No available units in {territory}")
        else:
            logger.warning(f"No AI garrison in {territory}")

        # Initialize timer for order execution
        self.ai_attack_timer = 0.0
        self.ai_orders_executed = False

    def _setup_partial_freedom(self):
        """
        Step 37: Enable partial freedom mode with quest tracking.
        """
        logger.info("Setting up partial freedom mode")
        self.partial_freedom_mode = True
        self.conquered_targets = set()
        self.conquest_targets = {'Affrancian Uplands', 'March of Auverne'}

    def _on_territory_conquered(self, territory, new_owner, deferred=False):
        """
        Track territory conquests during partial freedom phase.
        Called from notify_event('territory_conquered').

        Args:
            deferred: If True, save pending data but don't jump to victory yet
                      (wait for battle_popup_closed to avoid voice over battle report).
        """
        if not hasattr(self, 'partial_freedom_mode') or not self.partial_freedom_mode:
            return

        if new_owner == 0 and territory in self.conquest_targets:
            self.conquered_targets.add(territory)
            logger.info(f"Territory conquered: {territory}, total: {len(self.conquered_targets)}/{len(self.conquest_targets)}")

            # Mark the corresponding quest as complete immediately
            quest_text = f"Conquer {territory}"
            for quest in self.quest_log:
                if quest['text'] == quest_text and not quest['completed']:
                    quest['completed'] = True
                    logger.info(f"Quest completed: {quest_text}")
                    break

            step_id = self.steps[self.current_step_index].step_id

            # Steps 37-38: Jump directly to victory (step 39) when BOTH are conquered
            # Skip step 38 if we're still in step 37 but both are done
            if step_id in (37, 38) and len(self.conquered_targets) >= len(self.conquest_targets):
                if deferred:
                    # Store pending data — will be processed on battle_popup_closed
                    self._pending_conquest_data = (territory, new_owner)
                    logger.info(f"All territories conquered! Deferring victory until battle popup closes.")
                    return
                logger.info(f"All territories conquered! Jumping to victory step.")
                # Find step 39 (victory) and jump directly to it
                for i, step in enumerate(self.steps):
                    if step.step_id == 39:
                        self.current_step_index = i - 1  # Will be incremented by _advance_step
                        break
                self._advance_step()

    def _end_ai_turn(self):
        """End the AI turn by calling next_player(). Called from step on_enter callbacks."""
        logger.debug(f"Ending AI turn, calling next_player()")
        self.game_state.next_player()

    # ========================================================================
    # INTERNAL: Step management
    # ========================================================================

    def _advance_step(self):
        """Move to the next tutorial step."""
        if self.current_step_index >= len(self.steps) - 1:
            # Tutorial complete — deactivate and unblock the game
            self.active = False
            logger.info("Tutorial complete!")
            # If AI turn is active (stuck on no-op override), end it so game isn't stuck
            if self.game_state.current_player != 0:
                self._end_ai_turn()
            return

        self.current_step_index += 1
        self._enter_step(self.current_step_index)

    def _enter_step(self, index):
        """Initialize state for a new step."""
        self.step_timer = 0.0
        step = self.steps[index]

        # Update quest log - support both single string and list of strings
        if step.quest_complete:
            complete_list = step.quest_complete if isinstance(step.quest_complete, list) else [step.quest_complete]
            for quest_text in complete_list:
                for quest in self.quest_log:
                    if quest['text'] == quest_text:
                        quest['completed'] = True

        if step.quest_add:
            add_list = step.quest_add if isinstance(step.quest_add, list) else [step.quest_add]
            for quest_text in add_list:
                self.quest_log.append({'text': quest_text, 'completed': False})

        # Call on_enter callback
        if step.on_enter:
            step.on_enter(self)

        # Set up transmission overlay and play corresponding voice line
        from global_sound import play_transmission_sound, stop_transmission_sound
        if step.transmission_text:
            self._show_transmission(step.transmission_text)
            # Play voice line for this step (cuts any already-playing transmission voice)
            voice_num = self.STEP_TO_VOICE.get(step.step_id)
            if voice_num:
                play_transmission_sound(voice_num)
        else:
            self.transmission_overlay = None
            # Stop any playing voice when overlay is hidden
            stop_transmission_sound()

        # Step 1: Start camera animation
        if step.step_id == 1:
            self._start_camera_animation()

        logger.debug(f"Entered step {step.step_id}")

    def _show_transmission(self, text, speaker="Thunder Priest"):
        """Show or update the transmission overlay with speaker name."""
        import main as _main
        TOP_PANEL_HEIGHT = _main.TOP_PANEL_HEIGHT
        screen = self.main_game.screen
        sw = screen.get_width()
        sh = screen.get_height()
        if not self.transmission_overlay:
            self.transmission_overlay = TransmissionOverlay(sw, sh, text, TOP_PANEL_HEIGHT, speaker=speaker)
        else:
            self.transmission_overlay.set_text(text, speaker=speaker)

    def _start_camera_animation(self):
        """Initialize camera zoom animation for step 1."""
        import main as _main
        TOP_PANEL_HEIGHT = _main.TOP_PANEL_HEIGHT
        MAP_HEIGHT = _main.MAP_HEIGHT
        camera = self.main_game.camera
        # Use scaled center (camera works in scaled world coordinates)
        target_center = self.main_game.scaled_centers.get('Lunedale',
                            map_data.get_territory_center('Lunedale'))
        screen_width = self.main_game.screen.get_width()
        map_area_height = MAP_HEIGHT  # Map rendering area height

        logger.debug(f"Starting camera animation: target_center={target_center}, "
              f"start_zoom={camera.max_zoom}, target_zoom={camera.min_zoom}, "
              f"screen_width={screen_width}, map_area_height={map_area_height}")

        self.camera_animation = CameraAnimation(
            camera_handler=camera,
            start_zoom=camera.min_zoom,   # 1.65 (zoomed out overview)
            target_zoom=camera.max_zoom,  # 4.0 (zoomed in on Lunedale)
            duration=1.5,
            target_center_world=target_center,
            screen_width=screen_width,
            map_area_height=map_area_height,
        )
        logger.debug(f"Camera animation created, camera.zoom={camera.zoom}, "
              f"offset={camera.offset}")

    def _override_swordsmen_ready(self):
        """Step 24: Override newly trained Swordsmen status from 'moved' to 'ready'."""
        gs = self.game_state
        territory = 'Lunedale'
        if territory in gs.territory_garrisons and 0 in gs.territory_garrisons[territory]:
            garrison = gs.territory_garrisons[territory][0]
            # Move all 'moved' units to 'unmoved' and set their status to 'ready'
            for unit in garrison.get('units', []):
                if unit.get('status') == 'moved':
                    unit['status'] = 'ready'
            moved_count = garrison.get('moved', 0)
            garrison['unmoved'] = garrison.get('unmoved', 0) + moved_count
            garrison['moved'] = 0
            # Sync legacy data
            gs.sync_legacy_garrison_data(territory)

    # ========================================================================
    # QUEST LOG ACCESS (for ui_renderer)
    # ========================================================================

    def get_quest_log(self):
        """Return the quest log list for rendering in the Quests tab."""
        return self.quest_log

    def get_highlight_territory(self):
        """Return the territory name to highlight, or None."""
        if not self.active:
            return None
        return self.steps[self.current_step_index].highlight_territory

    def _cleanup(self):
        """L4 fix: Clean up mission state when exiting (matches other campaign missions)."""
        from global_sound import stop_transmission_sound
        logger.info("Cleaning up tutorial mission")
        stop_transmission_sound()

        # Restore swapped flag icons
        game = self.main_game
        if hasattr(game, 'army_flag_icons') and 0 in game.army_flag_icons and 1 in game.army_flag_icons:
            game.army_flag_icons[0], game.army_flag_icons[1] = game.army_flag_icons[1], game.army_flag_icons[0]

        self.active = False

    def deactivate(self):
        """Deactivate the mission (called on exit)."""
        self._cleanup()
