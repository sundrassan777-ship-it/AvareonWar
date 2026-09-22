# -*- coding: utf-8 -*-
# replay_viewer.py
# Replay viewer for recorded game replays

"""
Replay Viewer
=============

Standalone screen for watching recorded game replays. Renders the map with
territory ownership, army counts, buildings, and movement orders from
serialized state snapshots.

Features:
- Timeline bar for scrubbing through turns
- Playback controls (play/pause, step, speed)
- Player POV selector (switch which player's stats are highlighted)
- Info panel showing turn events, player resources
- Camera pan/zoom

Does NOT reuse MapRenderer/UIRenderer (too tightly coupled to live Game).
Instead provides its own simplified map rendering optimized for replay viewing.
"""

import pygame
import pygame.gfxdraw
import math
import os
import map_data
from config.constants import (
    ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT,
    WHITE, PLAYER_COLORS,
)
from replay_recorder import ReplayRecorder
from global_sound import sound_manager
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.cursor import draw_custom_cursor
from utils.logger import get_logger
from display_utils import menu_frame_cap

logger = get_logger(__name__)

# --- UI palette -------------------------------------------------------------
# The viewer is a HUD laid over the game map, so it wears the in-game bar
# textures (TopPanel/BottomBar/RightPanel) rather than the ornate campaign panel
# frames used by replay_browser.py -- the map has to stay edge to edge.
# Colour literals are the shared house values (see replay_browser.py:37-47).
BRASS_COLOR = (181, 166, 66)     # headings, dividers, borders, timeline fill
INFO_TEXT = (226, 216, 190)      # parchment-warm off-white, body text
DIM_TEXT = (168, 156, 128)       # secondary text (replaced three ad-hoc greys)
PLATE_BG = (54, 42, 28)          # carved plate fill behind the square buttons
TIMELINE_BG = (54, 42, 28)       # house scroll-track brown
TIMELINE_FILL = BRASS_COLOR
TIMELINE_HANDLE = BRASS_COLOR
NEUTRAL_COLOR = (100, 100, 100)

# Button state tint table -- the canonical house values, identical to
# replay_browser._btn_surface(). Applied to the button art with BLEND_RGBA_MULT
# (base) then BLEND_RGBA_ADD (hover/press lift).
BTN_MULT_NORMAL = (100, 100, 100, 255)
BTN_ADD_HOVER = (40, 40, 40, 0)
BTN_ADD_CLICK = (80, 80, 80, 0)

# Used only when the corresponding texture fails to load.
DARK_BG = (20, 20, 30)
PANEL_BG = (30, 24, 16, 235)
BAR_BG = (28, 22, 14, 240)


class ReplayViewer:
    """
    Standalone replay viewer screen.

    Loads a replay file, displays the map at each snapshot, and provides
    timeline navigation, playback controls, and player POV switching.

    Usage:
        viewer = ReplayViewer(screen, replay_path)
        result = viewer.run()  # Returns 'main_menu' or None
    """

    # Playback speed options
    SPEEDS = [0.5, 1.0, 2.0, 4.0]
    SPEED_LABELS = ['0.5x', '1x', '2x', '4x']

    def __init__(self, screen, replay_path):
        """
        Args:
            screen: Pygame display surface
            replay_path: Path to .replay.json.gz or .replay.json file
        """
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        self.clock = pygame.time.Clock()

        # Load replay data
        self.replay_data = ReplayRecorder.load_replay(replay_path)
        if not self.replay_data:
            logger.error(f"Failed to load replay: {replay_path}")
            self.done = True
            self.result = 'main_menu'
            return

        self.metadata = self.replay_data['metadata']
        self.snapshots = self.replay_data['snapshots']
        self.num_players = self.metadata['num_players']
        self.player_info = self.metadata['players']

        # State
        self.done = False
        self.result = None
        self.current_snapshot_index = 0
        self.selected_pov = -1  # -1 = spectator (all), 0+ = specific player
        self.hovered_button = None
        # Set on click, cleared at the end of _render() so the press tint lasts
        # exactly one frame (the replay_browser.py:533 contract).
        self.clicked_button = None

        # Playback state
        self.playing = False
        self.speed_index = 1  # Default 1x
        self.playback_timer = 0.0
        self.seconds_per_snapshot = 2.0  # Base: 2 seconds per snapshot at 1x

        # Camera state (simplified — no CameraHandler dependency)
        self.camera_offset = [0.0, 0.0]
        self.camera_zoom = 1.0
        self.camera_drag_start = None
        self.camera_drag_offset_start = None

        # Info panel scroll
        self.info_scroll_offset = 0
        self.max_info_scroll = 0

        # --- Layout (every rect lives in _build_layout) ---
        self._build_layout()

        # --- Load map and assets ---
        self._load_map_assets()

        # --- Fonts ---
        # Cinzel only, at house sizes with legibility floors (~0.55 x base).
        # Deliberately NOT config/font_manager.py: get_font() remaps every weight
        # one step bolder, which breaks the match with the campaign screens.
        font_path = 'assets/fonts/Cinzel-Regular.ttf'
        bold_font_path = 'assets/fonts/Cinzel-SemiBold.ttf'
        self.font = pygame.font.Font(font_path, max(14, int(20 * self.ui_scale)))
        self.small_font = pygame.font.Font(font_path, max(12, int(17 * self.ui_scale)))
        self.title_font = pygame.font.Font(bold_font_path, max(16, int(26 * self.ui_scale)))
        self.header_font = pygame.font.Font(bold_font_path, max(14, int(22 * self.ui_scale)))

        # Text caches for rendering performance
        self._text_cache = {}
        self._fit_cache = {}

        # Pre-compute territory polygon bounding boxes for hit-testing
        self._territory_bboxes = {}
        for territory, polygon in self.scaled_polygons.items():
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            self._territory_bboxes[territory] = (min(xs), min(ys), max(xs), max(ys))

        # Hovered territory for info display
        self.hovered_territory = None

        # Timeline dragging state
        self._timeline_dragging = False

        logger.info(f"ReplayViewer initialized: {len(self.snapshots)} snapshots, "
                    f"{self.num_players} players")

    def _build_layout(self):
        """
        Compute every rect the viewer uses -- the single source of truth for
        geometry.

        MUST run before _load_map_assets(), which derives scale_factor and
        min_zoom from map_rect.

        The rect ATTRIBUTE NAMES here are a contract with _handle_events() and
        _handle_left_click(), which hit-test them by name and map them to the
        hover-ID strings 'play_pause' / 'step_back' / 'step_forward' / 'speed' /
        'exit' / 'pov_<id>'. Rename one side only and input breaks silently.
        """
        s = self.ui_scale = self.height / 1080.0

        # The bars are textured now (TopPanel.jpg / BottomBar.jpg), so they need
        # a little more depth than the old flat fills did.
        self.top_bar_height = int(56 * s)
        self.bottom_bar_height = int(112 * s)
        self.info_panel_width = int(320 * s)

        # Map area -- feeds scale_factor / min_zoom in _load_map_assets()
        self.map_rect = pygame.Rect(
            0, self.top_bar_height,
            self.width - self.info_panel_width,
            self.height - self.top_bar_height - self.bottom_bar_height
        )

        # Info panel rect (right side)
        self.info_panel_rect = pygame.Rect(
            self.width - self.info_panel_width, self.top_bar_height,
            self.info_panel_width,
            self.height - self.top_bar_height - self.bottom_bar_height
        )

        # Inner content area of the info panel. RightPanel.jpg has a carved left
        # edge, hence the larger left inset. _render_info_panel() flows its
        # y-cursor inside this rect AND derives max_info_scroll from it -- using
        # the raw panel rect for one and this rect for the other breaks scrolling.
        pad_l, pad_r = int(18 * s), int(14 * s)
        pad_t, pad_b = int(12 * s), int(10 * s)
        self.info_content_rect = pygame.Rect(
            self.info_panel_rect.x + pad_l,
            self.info_panel_rect.y + pad_t,
            self.info_panel_rect.width - pad_l - pad_r,
            self.info_panel_rect.height - pad_t - pad_b
        )

        # Timeline scrubber. _scrub_timeline() derives its fraction from
        # timeline_rect.x / .width, so the drawn track must equal this rect.
        timeline_margin = int(28 * s)
        self.timeline_rect = pygame.Rect(
            timeline_margin,
            self.height - self.bottom_bar_height + int(20 * s),
            self.width - 2 * timeline_margin,
            int(14 * s)
        )

        # Playback control buttons, centred below the timeline. The row is
        # 3 square buttons + a double-width speed button + 3 gaps.
        btn_size = int(40 * s)
        btn_y = self.timeline_rect.bottom + int(14 * s)
        btn_spacing = int(10 * s)
        speed_w = btn_size * 2
        controls_width = 3 * btn_size + speed_w + 3 * btn_spacing
        controls_x = (self.width - controls_width) // 2

        self.btn_step_back = pygame.Rect(controls_x, btn_y, btn_size, btn_size)
        self.btn_play_pause = pygame.Rect(
            controls_x + btn_size + btn_spacing, btn_y, btn_size, btn_size)
        self.btn_step_forward = pygame.Rect(
            controls_x + 2 * (btn_size + btn_spacing), btn_y, btn_size, btn_size)
        self.btn_speed = pygame.Rect(
            controls_x + 3 * (btn_size + btn_spacing), btn_y, speed_w, btn_size)

        # Exit wears GMenuButton.png, so size it to that art's aspect
        # (417/1317) instead of a literal -- a squashed plate reads as a bug.
        exit_w = int(132 * s)
        exit_h = max(1, int(exit_w * (417 / 1317)))
        self.btn_exit = pygame.Rect(
            self.width - timeline_margin - exit_w,
            btn_y + (btn_size - exit_h) // 2,
            exit_w, exit_h
        )

        # Player POV buttons (top bar)
        self.pov_buttons = []
        pov_btn_size = int(32 * s)
        pov_x = int(24 * s)
        pov_y = (self.top_bar_height - pov_btn_size) // 2
        # "All" button (spectator)
        self.pov_buttons.append(
            ('all', pygame.Rect(pov_x, pov_y, int(56 * s), pov_btn_size)))
        pov_x += int(66 * s)
        # Per-player buttons
        for p in range(self.num_players):
            self.pov_buttons.append(
                (p, pygame.Rect(pov_x, pov_y, pov_btn_size, pov_btn_size)))
            pov_x += pov_btn_size + int(8 * s)

    def _load_map_assets(self):
        """Load and scale map image, polygons, centers, and icon assets."""
        # Load map data for the replay's map (multi-map support)
        replay_map_id = self.metadata.get('map_id', 'avareon')
        map_data.load_map(replay_map_id)

        # Load map image from map directory or fallback
        map_dir = map_data.get_map_directory(replay_map_id)
        map_png = os.path.join(map_dir, 'map.png')
        map_loaded = False
        if os.path.exists(map_png):
            try:
                self.map_image_original = pygame.image.load(map_png).convert()
                map_loaded = True
            except pygame.error:
                pass
        if not map_loaded and replay_map_id == 'avareon':
            try:
                self.map_image_original = pygame.image.load("assets/map.png").convert()
                map_loaded = True
            except pygame.error:
                pass
        if not map_loaded:
            # Fallback: dark surface
            self.map_image_original = pygame.Surface(
                (ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT))
            self.map_image_original.fill((0, 0, 0))

        # Calculate scale factor to fit map in map_rect
        width_scale = self.map_rect.width / ORIGINAL_MAP_WIDTH
        height_scale = self.map_rect.height / ORIGINAL_MAP_HEIGHT
        self.scale_factor = min(width_scale, height_scale)

        self.map_width = int(ORIGINAL_MAP_WIDTH * self.scale_factor)
        self.map_height = int(ORIGINAL_MAP_HEIGHT * self.scale_factor)

        # Scale map image
        self.map_image = pygame.transform.smoothscale(
            self.map_image_original, (self.map_width, self.map_height))

        # Scale polygons and centers
        self.scaled_polygons = {}
        self.scaled_centers = {}
        for territory, polygon in map_data.TERRITORY_POLYGONS.items():
            self.scaled_polygons[territory] = [
                (round(x * self.scale_factor), round(y * self.scale_factor))
                for x, y in polygon
            ]
        for territory, center in map_data.TERRITORY_CENTERS.items():
            self.scaled_centers[territory] = (
                round(center[0] * self.scale_factor),
                round(center[1] * self.scale_factor)
            )

        # Scale plot positions
        self.scaled_plots = {}
        for territory, plots in map_data.TERRITORY_PLOTS.items():
            self.scaled_plots[territory] = [
                (round(x * self.scale_factor), round(y * self.scale_factor))
                for x, y in plots
            ]

        # Set initial camera zoom to fit map in viewport
        self.camera_zoom = max(
            self.map_rect.width / max(self.map_width, 1),
            self.map_rect.height / max(self.map_height, 1),
        )
        self.min_zoom = self.camera_zoom
        self.max_zoom = self.camera_zoom * 3.0

        # --- HUD chrome textures ---
        # Same treatment as the live game (main.py:431-443, :491-502): load once,
        # pre-scale to the final rect size, fall back to None so every draw site
        # can degrade to a flat fill rather than crash.
        self.top_panel_image = self._load_bar_texture(
            "assets/TopPanel.jpg", (self.width, self.top_bar_height))
        self.bottom_bar_image = self._load_bar_texture(
            "assets/BottomBar.jpg", (self.width, self.bottom_bar_height))
        self.right_panel_image = self._load_bar_texture(
            "assets/RightPanel.jpg", self.info_panel_rect.size)

        # Wide button art, used for the Speed and Exit buttons.
        try:
            self.menu_button_img = pygame.image.load(
                "assets/GMenuButton.png").convert_alpha()
        except pygame.error as e:
            logger.warning("Could not load GMenuButton.png: %s. "
                           "Using carved-plate fallback." % e)
            self.menu_button_img = None

        # Load building icons (filenames use "Icon" suffix, e.g. FarmIcon.png)
        self.building_icons = {}
        building_names = ['Farm', 'Mine', 'Barracks', 'Keep', 'Square', 'Training Grounds']
        for name in building_names:
            icon_file = name.replace(' ', '') + 'Icon.png'
            try:
                icon = pygame.image.load(
                    f"assets/mapicons/{icon_file}").convert_alpha()
                self.building_icons[name] = icon
            except pygame.error:
                self.building_icons[name] = None

        # Per-frame allocation caches (see the rendering rules in CLAUDE.md).
        # _icon_cache: building icons scaled per zoom level, keyed (name, size).
        # _overlay_cache: SRCALPHA scratch surfaces for territory fills, keyed by
        # size -- _render_map used to allocate one PER OWNED TERRITORY PER FRAME.
        self._icon_cache = {}
        self._overlay_cache = {}
        # Tinted GMenuButton art, keyed (size, state).
        self._btn_cache = {}

    def _load_bar_texture(self, path, size):
        """
        Load one HUD chrome texture, pre-scaled to its final size.

        Returns None (and logs) when the art is missing, so callers fall back to
        a flat fill. Mirrors main.py's top/right panel loading.
        """
        try:
            image = pygame.image.load(path)
            return pygame.transform.scale(image, (max(1, size[0]), max(1, size[1])))
        except pygame.error as e:
            logger.warning("Could not load %s: %s. Using solid colour fallback." % (path, e))
            return None

    def _get_overlay(self, w, h):
        """
        A cleared SRCALPHA scratch surface of exactly (w, h).

        CLAUDE.md rendering rule: never allocate a Surface per frame. _render_map
        draws one polygon overlay per OWNED TERRITORY per frame, so these are
        cached by size and wiped on reuse instead of rebuilt. Each caller draws
        and blits before the next one asks, so sharing an entry is safe.
        """
        key = (w, h)
        surf = self._overlay_cache.get(key)
        if surf is None:
            if len(self._overlay_cache) > 256:
                self._overlay_cache.clear()
            surf = pygame.Surface(key, pygame.SRCALPHA)
            self._overlay_cache[key] = surf
        else:
            surf.fill((0, 0, 0, 0))
        return surf

    def _get_scaled_icon(self, name, size):
        """
        Building icon scaled to `size`, cached by (name, size).

        smoothscale is expensive and the icon size is keyed to camera_zoom, so
        without this every building on the map was rescaled every frame.
        """
        key = (name, size)
        icon = self._icon_cache.get(key)
        if icon is None:
            base = self.building_icons.get(name)
            if not base:
                return None
            if len(self._icon_cache) > 256:
                self._icon_cache.clear()
            icon = pygame.transform.smoothscale(base, (size, size))
            self._icon_cache[key] = icon
        return icon

    # ========== Coordinate Conversion ==========

    def world_to_screen(self, world_pos):
        """Convert world (scaled map) coordinates to screen coordinates."""
        wx, wy = world_pos
        sx = (wx - self.camera_offset[0]) * self.camera_zoom + self.map_rect.x
        sy = (wy - self.camera_offset[1]) * self.camera_zoom + self.map_rect.y
        return (int(sx), int(sy))

    def screen_to_world(self, screen_pos):
        """Convert screen coordinates to world (scaled map) coordinates."""
        sx, sy = screen_pos
        wx = (sx - self.map_rect.x) / self.camera_zoom + self.camera_offset[0]
        wy = (sy - self.map_rect.y) / self.camera_zoom + self.camera_offset[1]
        return (wx, wy)

    def _get_territory_at_screen_pos(self, screen_pos):
        """Find which territory is under the given screen position."""
        world_pos = self.screen_to_world(screen_pos)
        for territory in reversed(list(self.scaled_polygons.keys())):
            bbox = self._territory_bboxes.get(territory)
            if bbox:
                min_x, min_y, max_x, max_y = bbox
                if world_pos[0] < min_x or world_pos[0] > max_x:
                    continue
                if world_pos[1] < min_y or world_pos[1] > max_y:
                    continue
            if map_data.point_in_polygon(world_pos, self.scaled_polygons[territory]):
                return territory
        return None

    # ========== Snapshot Data Access ==========

    def _get_current_snapshot(self):
        """Get the currently displayed snapshot dict."""
        if 0 <= self.current_snapshot_index < len(self.snapshots):
            return self.snapshots[self.current_snapshot_index]
        return self.snapshots[0] if self.snapshots else None

    def _get_state(self):
        """Get the 'state' dict from the current snapshot."""
        snap = self._get_current_snapshot()
        return snap['state'] if snap else {}

    def _get_player_color(self, player_index):
        """Get color for a player from replay metadata."""
        if player_index < 0 or player_index >= self.num_players:
            return NEUTRAL_COLOR
        info = self.player_info[player_index]
        color = info.get('color')
        if color:
            return tuple(color[:3])
        if player_index < len(PLAYER_COLORS):
            return PLAYER_COLORS[player_index]
        return NEUTRAL_COLOR

    def _get_player_name(self, player_index):
        """Get display name for a player from replay metadata."""
        if 0 <= player_index < len(self.player_info):
            name = self.player_info[player_index].get('name')
            if name:
                return name
        return f"Player {player_index + 1}"

    # ========== Main Loop ==========

    def run(self):
        """Main loop — blocks until user exits."""
        if self.done:
            return self.result

        while not self.done:
            dt = self.clock.tick(menu_frame_cap()) / 1000.0
            dt = min(dt, 0.05)  # Cap delta time to prevent jumps
            self._update(dt)
            self._handle_events()
            self._render()
            draw_custom_cursor(self.screen)
            pygame.display.flip()

        return self.result

    def _update(self, dt):
        """Update playback state."""
        if self.playing:
            speed = self.SPEEDS[self.speed_index]
            self.playback_timer += dt * speed
            if self.playback_timer >= self.seconds_per_snapshot:
                self.playback_timer -= self.seconds_per_snapshot
                if self.current_snapshot_index < len(self.snapshots) - 1:
                    self.current_snapshot_index += 1
                else:
                    # Reached end — stop playback
                    self.playing = False
                    self.playback_timer = 0.0

    def _handle_events(self):
        """Process input events."""
        mouse_pos = pygame.mouse.get_pos()

        # Update hovered territory
        if self.map_rect.collidepoint(mouse_pos):
            self.hovered_territory = self._get_territory_at_screen_pos(mouse_pos)
        else:
            self.hovered_territory = None

        # Update hover state for buttons
        self.hovered_button = None
        if self.btn_play_pause.collidepoint(mouse_pos):
            self.hovered_button = 'play_pause'
        elif self.btn_step_back.collidepoint(mouse_pos):
            self.hovered_button = 'step_back'
        elif self.btn_step_forward.collidepoint(mouse_pos):
            self.hovered_button = 'step_forward'
        elif self.btn_speed.collidepoint(mouse_pos):
            self.hovered_button = 'speed'
        elif self.btn_exit.collidepoint(mouse_pos):
            self.hovered_button = 'exit'
        else:
            for pov_id, rect in self.pov_buttons:
                if rect.collidepoint(mouse_pos):
                    self.hovered_button = f'pov_{pov_id}'
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
                    self.result = 'main_menu'
                    self.done = True
                elif event.key == pygame.K_SPACE:
                    self.playing = not self.playing
                    self.playback_timer = 0.0
                elif event.key == pygame.K_LEFT:
                    self._step_back()
                elif event.key == pygame.K_RIGHT:
                    self._step_forward()
                elif event.key == pygame.K_0:
                    self.selected_pov = -1
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    p = event.key - pygame.K_1
                    if p < self.num_players:
                        self.selected_pov = p

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self._handle_left_click(mouse_pos)
                elif event.button == 2:
                    # Middle mouse: start camera drag
                    self.camera_drag_start = mouse_pos
                    self.camera_drag_offset_start = list(self.camera_offset)
                elif event.button == 4:
                    # Scroll up: zoom in (or scroll info panel)
                    if self.info_panel_rect.collidepoint(mouse_pos):
                        self.info_scroll_offset = max(0, self.info_scroll_offset - 30)
                    elif self.map_rect.collidepoint(mouse_pos):
                        self._zoom_at(mouse_pos, 1.15)
                elif event.button == 5:
                    # Scroll down: zoom out (or scroll info panel)
                    if self.info_panel_rect.collidepoint(mouse_pos):
                        self.info_scroll_offset = min(
                            self.max_info_scroll, self.info_scroll_offset + 30)
                    elif self.map_rect.collidepoint(mouse_pos):
                        self._zoom_at(mouse_pos, 1 / 1.15)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self._timeline_dragging = False
                elif event.button == 2:
                    self.camera_drag_start = None

            elif event.type == pygame.MOUSEMOTION:
                # Camera drag
                if self.camera_drag_start and self.camera_drag_offset_start:
                    dx = mouse_pos[0] - self.camera_drag_start[0]
                    dy = mouse_pos[1] - self.camera_drag_start[1]
                    self.camera_offset[0] = self.camera_drag_offset_start[0] - dx / self.camera_zoom
                    self.camera_offset[1] = self.camera_drag_offset_start[1] - dy / self.camera_zoom

                # Timeline drag
                if self._timeline_dragging:
                    self._scrub_timeline(mouse_pos[0])

    def _handle_left_click(self, mouse_pos):
        """Handle left mouse button click."""
        # Playback controls
        if self.btn_play_pause.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'play_pause'
            self.playing = not self.playing
            self.playback_timer = 0.0
        elif self.btn_step_back.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'step_back'
            self._step_back()
        elif self.btn_step_forward.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'step_forward'
            self._step_forward()
        elif self.btn_speed.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'speed'
            self.speed_index = (self.speed_index + 1) % len(self.SPEEDS)
        elif self.btn_exit.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.clicked_button = 'exit'
            self.result = 'main_menu'
            self.done = True

        # Timeline click
        elif self.timeline_rect.collidepoint(mouse_pos):
            self._timeline_dragging = True
            self._scrub_timeline(mouse_pos[0])

        # POV buttons
        else:
            for pov_id, rect in self.pov_buttons:
                if rect.collidepoint(mouse_pos):
                    sound_manager.play_ui_click()
                    self.clicked_button = f'pov_{pov_id}'
                    self.selected_pov = -1 if pov_id == 'all' else pov_id
                    break

    def _step_back(self):
        """Step one snapshot backward."""
        if self.current_snapshot_index > 0:
            self.current_snapshot_index -= 1
            self.playing = False
            self.playback_timer = 0.0

    def _step_forward(self):
        """Step one snapshot forward."""
        if self.current_snapshot_index < len(self.snapshots) - 1:
            self.current_snapshot_index += 1
            self.playing = False
            self.playback_timer = 0.0

    def _scrub_timeline(self, screen_x):
        """Scrub timeline to position based on screen x coordinate."""
        fraction = (screen_x - self.timeline_rect.x) / max(self.timeline_rect.width, 1)
        fraction = max(0.0, min(1.0, fraction))
        new_index = int(fraction * (len(self.snapshots) - 1))
        self.current_snapshot_index = max(0, min(new_index, len(self.snapshots) - 1))

    def _zoom_at(self, screen_pos, factor):
        """Zoom camera centered on the given screen position."""
        old_world = self.screen_to_world(screen_pos)
        self.camera_zoom = max(self.min_zoom, min(self.max_zoom, self.camera_zoom * factor))
        new_world = self.screen_to_world(screen_pos)
        # Adjust offset so the point under cursor stays in place
        self.camera_offset[0] += old_world[0] - new_world[0]
        self.camera_offset[1] += old_world[1] - new_world[1]

    # ========== Rendering ==========

    def _render(self):
        """Render the full replay viewer."""
        self.screen.fill(DARK_BG)

        # Map area
        self._render_map()

        # Info panel (right side)
        self._render_info_panel()

        # Top bar (turn indicator + POV buttons)
        self._render_top_bar()

        # Bottom bar (timeline + controls)
        self._render_bottom_bar()

        # Reset click state after painting, so the press tint lasts exactly one
        # frame (matches replay_browser._render).
        self.clicked_button = None

    def _render_map(self):
        """Render the map with territory colors, armies, buildings, and orders."""
        state = self._get_state()
        if not state:
            return

        territory_owners = state.get('territory_owners', {})

        # Clip rendering to map rect
        self.screen.set_clip(self.map_rect)

        # Draw base map image
        map_screen_pos = self.world_to_screen((0, 0))
        scaled_w = int(self.map_width * self.camera_zoom)
        scaled_h = int(self.map_height * self.camera_zoom)

        # Only re-scale if needed (rough LOD)
        if not hasattr(self, '_cached_map_surface') or self._cached_map_zoom != self.camera_zoom:
            # Use smoothscale for the map background
            target_w = max(1, scaled_w)
            target_h = max(1, scaled_h)
            # Limit max scale to avoid huge surfaces
            if target_w > 8000 or target_h > 8000:
                target_w = min(target_w, 8000)
                target_h = min(target_h, 8000)
            self._cached_map_surface = pygame.transform.smoothscale(
                self.map_image, (target_w, target_h))
            self._cached_map_zoom = self.camera_zoom

        self.screen.blit(self._cached_map_surface, map_screen_pos)

        # Draw territory color overlays
        for territory, polygon in self.scaled_polygons.items():
            owner = territory_owners.get(territory, -1)
            if owner < 0:
                continue  # Neutral — no overlay

            color = self._get_player_color(owner)
            # Transform polygon to screen coordinates
            screen_poly = [self.world_to_screen(p) for p in polygon]

            # Semi-transparent color overlay
            # Use a small surface for the polygon bounding box
            xs = [p[0] for p in screen_poly]
            ys = [p[1] for p in screen_poly]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            w = max_x - min_x + 1
            h = max_y - min_y + 1
            if w <= 0 or h <= 0 or w > 4000 or h > 4000:
                continue

            overlay = self._get_overlay(w, h)
            local_poly = [(x - min_x, y - min_y) for x, y in screen_poly]
            pygame.draw.polygon(overlay, (*color, 80), local_poly)
            pygame.draw.polygon(overlay, (*color, 160), local_poly, 2)
            self.screen.blit(overlay, (min_x, min_y))

        # Draw hover highlight
        if self.hovered_territory and self.hovered_territory in self.scaled_polygons:
            polygon = self.scaled_polygons[self.hovered_territory]
            screen_poly = [self.world_to_screen(p) for p in polygon]
            xs = [p[0] for p in screen_poly]
            ys = [p[1] for p in screen_poly]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            w = max_x - min_x + 1
            h = max_y - min_y + 1
            if 0 < w <= 4000 and 0 < h <= 4000:
                hover_surf = self._get_overlay(w, h)
                local_poly = [(x - min_x, y - min_y) for x, y in screen_poly]
                pygame.draw.polygon(hover_surf, (255, 255, 255, 40), local_poly)
                pygame.draw.polygon(hover_surf, (255, 255, 255, 200), local_poly, 2)
                self.screen.blit(hover_surf, (min_x, min_y))

        # Draw army counts at territory centers
        garrisons = state.get('territory_garrisons', {})
        armies = state.get('armies', {})
        for territory, center in self.scaled_centers.items():
            owner = territory_owners.get(territory, -1)
            # Use garrison total or fallback to armies dict
            total = 0
            if territory in garrisons:
                for p_str, g in garrisons[territory].items():
                    total += g.get('unmoved', 0) + g.get('moved', 0)
            if total == 0:
                total = armies.get(territory, 0)

            if total <= 0:
                continue

            screen_pos = self.world_to_screen(center)
            # Draw flag icon or army count circle
            color = self._get_player_color(owner) if owner >= 0 else NEUTRAL_COLOR
            radius = max(8, int(14 * self.camera_zoom * self.ui_scale))
            pygame.draw.circle(self.screen, color, screen_pos, radius)
            pygame.draw.circle(self.screen, WHITE, screen_pos, radius, 1)

            # Army count text
            count_text = self._cached_text(str(total), self.small_font, WHITE)
            text_rect = count_text.get_rect(center=screen_pos)
            self.screen.blit(count_text, text_rect)

        # Draw building icons at plot positions
        buildings = state.get('buildings', {})
        for territory, plots in buildings.items():
            if territory not in self.scaled_plots:
                continue
            for plot_str, building_type in plots.items():
                plot_idx = int(plot_str)
                plot_positions = self.scaled_plots[territory]
                if plot_idx >= len(plot_positions):
                    continue
                plot_pos = plot_positions[plot_idx]
                screen_pos = self.world_to_screen(plot_pos)

                icon_size = max(12, int(18 * self.camera_zoom * self.ui_scale))
                scaled_icon = self._get_scaled_icon(building_type, icon_size)
                if scaled_icon:
                    icon_rect = scaled_icon.get_rect(center=screen_pos)
                    self.screen.blit(scaled_icon, icon_rect)
                else:
                    # Fallback: small colored dot
                    pygame.draw.circle(self.screen, BRASS_COLOR, screen_pos, 4)

        # Draw movement order arrows
        orders = state.get('movement_orders', [])
        for order in orders:
            from_t = order.get('from', '')
            to_t = order.get('to', '')
            player = order.get('player', 0)
            if from_t in self.scaled_centers and to_t in self.scaled_centers:
                from_pos = self.world_to_screen(self.scaled_centers[from_t])
                to_pos = self.world_to_screen(self.scaled_centers[to_t])
                color = self._get_player_color(player)
                pygame.draw.line(self.screen, color, from_pos, to_pos, max(2, int(3 * self.camera_zoom)))

                # Draw arrowhead
                dx = to_pos[0] - from_pos[0]
                dy = to_pos[1] - from_pos[1]
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 10:
                    ndx, ndy = dx / dist, dy / dist
                    arrow_len = max(8, int(12 * self.camera_zoom))
                    # Arrowhead triangle
                    tip = to_pos
                    left = (int(tip[0] - arrow_len * ndx + arrow_len * 0.4 * ndy),
                            int(tip[1] - arrow_len * ndy - arrow_len * 0.4 * ndx))
                    right = (int(tip[0] - arrow_len * ndx - arrow_len * 0.4 * ndy),
                             int(tip[1] - arrow_len * ndy + arrow_len * 0.4 * ndx))
                    pygame.draw.polygon(self.screen, color, [tip, left, right])

        # Reset clip
        self.screen.set_clip(None)

    def _render_info_panel(self):
        """Render the right-side info panel with turn events and player stats."""
        state = self._get_state()
        snap = self._get_current_snapshot()
        if not state or not snap:
            return

        # Panel background -- the in-game right sidebar texture
        if self.right_panel_image:
            self.screen.blit(self.right_panel_image, self.info_panel_rect)
        else:
            panel_surf = self._get_overlay(
                self.info_panel_rect.width, self.info_panel_rect.height)
            panel_surf.fill(PANEL_BG)
            self.screen.blit(panel_surf, self.info_panel_rect)

        # Brass divider on the left edge, at the house line width
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (self.info_panel_rect.x, self.info_panel_rect.y),
                         (self.info_panel_rect.x, self.info_panel_rect.bottom),
                         max(1, int(2 * self.ui_scale)))

        # Content flows inside info_content_rect, and max_info_scroll at the end
        # of this method is derived from the SAME rect -- mixing the two rects
        # is what silently breaks scrolling.
        content = self.info_content_rect
        x = content.x
        y = content.y - self.info_scroll_offset
        max_y = content.bottom

        # --- Player stats section ---
        header = self._cached_text("Player Stats", self.header_font, BRASS_COLOR)
        if y + header.get_height() < max_y:
            self.screen.blit(header, (x, y))
        y += header.get_height() + int(8 * self.ui_scale)

        player_gold = state.get('player_gold', [])
        player_stats = state.get('player_stats', {})

        # Determine which players to show (POV or all)
        if self.selected_pov >= 0:
            players_to_show = [self.selected_pov]
        else:
            players_to_show = list(range(self.num_players))

        for p in players_to_show:
            # No early break: y also MEASURES the content for
            # max_info_scroll below. Stopping at max_y made the scroll
            # bound depend on the scroll position, so the panel only
            # revealed a little more content per drag. The per-item
            # guards below already skip drawing what is off-panel.
            color = self._get_player_color(p)
            name = self._get_player_name(p)

            # Player name with color dot
            dot_radius = int(6 * self.ui_scale)
            if content.y <= y <= max_y:
                pygame.draw.circle(self.screen, color, (x + dot_radius, y + dot_radius + 2), dot_radius)
            name_x = x + dot_radius * 2 + int(6 * self.ui_scale)
            name_surf = self._cached_text(
                self._fit_text(name, self.font, content.right - name_x),
                self.font, WHITE)
            if content.y <= y <= max_y:
                self.screen.blit(name_surf, (name_x, y))
            y += name_surf.get_height() + int(4 * self.ui_scale)

            # Gold
            gold = player_gold[p] if p < len(player_gold) else 0
            gold_text = self._cached_text(f"  Gold: {gold}", self.small_font, INFO_TEXT)
            if content.y <= y <= max_y:
                self.screen.blit(gold_text, (x, y))
            y += gold_text.get_height() + int(2 * self.ui_scale)

            # Territory count
            territory_owners = state.get('territory_owners', {})
            terr_count = sum(1 for v in territory_owners.values() if v == p)
            terr_text = self._cached_text(f"  Territories: {terr_count}", self.small_font, INFO_TEXT)
            if content.y <= y <= max_y:
                self.screen.blit(terr_text, (x, y))
            y += terr_text.get_height() + int(2 * self.ui_scale)

            # Army count
            garrisons = state.get('territory_garrisons', {})
            total_armies = 0
            for t_garrs in garrisons.values():
                if str(p) in t_garrs:
                    g = t_garrs[str(p)]
                    total_armies += g.get('unmoved', 0) + g.get('moved', 0)
            army_text = self._cached_text(f"  Armies: {total_armies}", self.small_font, INFO_TEXT)
            if content.y <= y <= max_y:
                self.screen.blit(army_text, (x, y))
            y += army_text.get_height() + int(8 * self.ui_scale)

        # --- Turn events section ---
        y += int(5 * self.ui_scale)
        events_header = self._cached_text("Turn Events", self.header_font, BRASS_COLOR)
        if content.y <= y <= max_y:
            self.screen.blit(events_header, (x, y))
        y += events_header.get_height() + int(6 * self.ui_scale)

        events = snap.get('events', [])
        if not events:
            no_events = self._cached_text("  No events", self.small_font, DIM_TEXT)
            if content.y <= y <= max_y:
                self.screen.blit(no_events, (x, y))
            y += no_events.get_height() + int(4 * self.ui_scale)
        else:
            for event in events:
                event_str = self._fit_text(
                    f"  {self._format_event(event)}", self.small_font, content.width)
                event_surf = self._cached_text(event_str, self.small_font, INFO_TEXT)
                if content.y <= y <= max_y:
                    self.screen.blit(event_surf, (x, y))
                y += event_surf.get_height() + int(3 * self.ui_scale)

        # --- Action log section ---
        y += int(8 * self.ui_scale)
        log_header = self._cached_text("Action Log", self.header_font, BRASS_COLOR)
        if content.y <= y <= max_y:
            self.screen.blit(log_header, (x, y))
        y += log_header.get_height() + int(6 * self.ui_scale)

        messages = snap.get('messages', [])
        # Show last 20 messages (most recent first)
        recent_messages = messages[-20:] if messages else []
        for msg in reversed(recent_messages):
            # Fit to the panel in PIXELS. The old 50-character cut was blind to
            # font size and overflowed the panel once the fonts grew.
            display_msg = self._fit_text(f"  {msg}", self.small_font, content.width)
            # INFO_TEXT rather than DIM_TEXT: RightPanel.jpg is a busy damask, and
            # the dimmer secondary colour washes out against it.
            msg_surf = self._cached_text(display_msg, self.small_font, INFO_TEXT)
            if content.y <= y <= max_y:
                self.screen.blit(msg_surf, (x, y))
            y += msg_surf.get_height() + int(2 * self.ui_scale)

        # Hovered territory info at bottom
        if self.hovered_territory:
            self._render_territory_tooltip()

        # Update max scroll -- measured against the same content rect the
        # y-cursor flowed through above.
        total_content_height = y + self.info_scroll_offset - content.y
        self.max_info_scroll = max(0, total_content_height - content.height)

    def _render_territory_tooltip(self):
        """Render tooltip for hovered territory at bottom of info panel."""
        state = self._get_state()
        territory = self.hovered_territory
        if not territory or not state:
            return

        owner = state.get('territory_owners', {}).get(territory, -1)
        owner_name = self._get_player_name(owner) if owner >= 0 else "Neutral"

        # Build tooltip lines
        lines = [territory, f"Owner: {owner_name}"]

        # Army info from garrisons
        garrisons = state.get('territory_garrisons', {}).get(territory, {})
        for p_str, g in garrisons.items():
            total = g.get('unmoved', 0) + g.get('moved', 0)
            if total > 0:
                p_name = self._get_player_name(int(p_str))
                lines.append(f"  {p_name}: {total} armies")

        # Buildings
        buildings = state.get('buildings', {}).get(territory, {})
        if buildings:
            bldg_list = ', '.join(buildings.values())
            lines.append(f"Buildings: {bldg_list}")

        # Draw tooltip box at the bottom of the info panel. Line height comes
        # from the font rather than a literal, so it tracks the house font sizes.
        line_h = self.small_font.get_height() + int(3 * self.ui_scale)
        tooltip_h = len(lines) * line_h + int(14 * self.ui_scale)
        content = self.info_content_rect
        tooltip_rect = pygame.Rect(
            content.x,
            content.bottom - tooltip_h,
            content.width,
            tooltip_h
        )

        # Background: carved plate + brass frame, matching the button plates
        tip_surf = self._get_overlay(tooltip_rect.width, tooltip_rect.height)
        tip_surf.fill((*PLATE_BG, 242))
        pygame.draw.rect(tip_surf, BRASS_COLOR,
                         (0, 0, tooltip_rect.width, tooltip_rect.height),
                         max(1, int(2 * self.ui_scale)))
        self.screen.blit(tip_surf, tooltip_rect)

        # Text
        text_x = tooltip_rect.x + int(8 * self.ui_scale)
        text_w = tooltip_rect.width - int(16 * self.ui_scale)
        ty = tooltip_rect.y + int(7 * self.ui_scale)
        for i, line in enumerate(lines):
            font = self.header_font if i == 0 else self.small_font
            color = BRASS_COLOR if i == 0 else INFO_TEXT
            surf = self._cached_text(self._fit_text(line, font, text_w), font, color)
            self.screen.blit(surf, (text_x, ty))
            ty += line_h

    def _render_top_bar(self):
        """Render top bar with turn info and POV selector."""
        snap = self._get_current_snapshot()
        if not snap:
            return

        # Background -- the in-game top panel texture
        if self.top_panel_image:
            self.screen.blit(self.top_panel_image, (0, 0))
        else:
            top_surf = self._get_overlay(self.width, self.top_bar_height)
            top_surf.fill(BAR_BG)
            self.screen.blit(top_surf, (0, 0))

        # Brass divider along the bottom edge, at the house line width
        border_w = max(1, int(2 * self.ui_scale))
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (0, self.top_bar_height - border_w),
                         (self.width, self.top_bar_height - border_w), border_w)

        # POV buttons
        for pov_id, rect in self.pov_buttons:
            is_selected = (pov_id == 'all' and self.selected_pov == -1) or \
                          (pov_id != 'all' and self.selected_pov == pov_id)
            is_hovered = self.hovered_button == f'pov_{pov_id}'

            state = self._btn_state('pov_%s' % pov_id)
            frame_w = max(1, int(2 * self.ui_scale))

            if pov_id == 'all':
                # "All" (spectator) -- carved plate, brass framed when active
                self._draw_plate(rect, state, is_selected=is_selected)
                text = self._cached_text(
                    "All", self.small_font, BRASS_COLOR if is_selected else INFO_TEXT)
                self.screen.blit(text, text.get_rect(center=rect.center))
            else:
                # Player colour swatch, framed to match the rest of the chrome
                color = self._get_player_color(pov_id)
                pygame.draw.rect(self.screen, color, rect, border_radius=3)
                if is_selected:
                    pygame.draw.rect(self.screen, BRASS_COLOR, rect, frame_w, border_radius=3)
                elif is_hovered:
                    pygame.draw.rect(self.screen, INFO_TEXT, rect, 1, border_radius=3)
                else:
                    pygame.draw.rect(self.screen, PLATE_BG, rect, 1, border_radius=3)

        # Turn info (right side of top bar)
        turn = snap.get('turn', 0)
        current_player = snap.get('current_player', 0)
        total_snaps = len(self.snapshots)
        snap_idx = self.current_snapshot_index + 1

        # Right-aligned readout: the turn number carries the emphasis (brass,
        # title weight), the rest trails it on the same baseline.
        detail_text = f"Snapshot {snap_idx}/{total_snaps}"
        if current_player < self.num_players:
            p_name = self._get_player_name(current_player)
            detail_text += f"  |  {p_name}'s turn"

        turn_surf = self._cached_text(f"Turn {turn}", self.title_font, BRASS_COLOR)
        detail_surf = self._cached_text("  |  " + detail_text, self.font, INFO_TEXT)
        gap = int(20 * self.ui_scale)
        group_w = turn_surf.get_width() + detail_surf.get_width()
        group_x = self.width - group_w - gap

        self.screen.blit(turn_surf,
                         (group_x, (self.top_bar_height - turn_surf.get_height()) // 2))
        self.screen.blit(detail_surf,
                         (group_x + turn_surf.get_width(),
                          (self.top_bar_height - detail_surf.get_height()) // 2))

        # Victory condition and game mode (centre). Skipped rather than drawn
        # through the readout if the window is too narrow to hold both.
        vc = self.metadata.get('victory_condition', '')
        mode = self.metadata.get('game_mode', '')
        meta_text = f"{vc}  •  {mode.title()}"
        meta_surf = self._cached_text(meta_text, self.small_font, DIM_TEXT)
        meta_x = (self.width - meta_surf.get_width()) // 2
        meta_y = (self.top_bar_height - meta_surf.get_height()) // 2
        pov_right = self.pov_buttons[-1][1].right if self.pov_buttons else 0
        if meta_x > pov_right + gap and meta_x + meta_surf.get_width() < group_x - gap:
            self.screen.blit(meta_surf, (meta_x, meta_y))

    def _render_bottom_bar(self):
        """Render bottom bar with timeline and playback controls."""
        # Background -- the in-game bottom bar texture
        bar_y = self.height - self.bottom_bar_height
        if self.bottom_bar_image:
            self.screen.blit(self.bottom_bar_image, (0, bar_y))
        else:
            bar_surf = self._get_overlay(self.width, self.bottom_bar_height)
            bar_surf.fill(BAR_BG)
            self.screen.blit(bar_surf, (0, bar_y))

        # Brass divider along the top edge
        border_w = max(1, int(2 * self.ui_scale))
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (0, bar_y), (self.width, bar_y), border_w)

        # Timeline bar
        self._render_timeline()

        # Playback controls. The glyphs are DRAWN, not typed: Cinzel ships no
        # play/pause characters (cf. the fallback note at main_menu.py:1850).
        self._render_button(self.btn_step_back, None, 'step_back', glyph='step_back')
        self._render_button(self.btn_play_pause, None, 'play_pause',
                            glyph='pause' if self.playing else 'play')
        self._render_button(self.btn_step_forward, None, 'step_forward',
                            glyph='step_forward')

        # Speed and Exit are wide enough for the GMenuButton art
        self._render_button(self.btn_speed, self.SPEED_LABELS[self.speed_index],
                            'speed', wide=True)
        self._render_button(self.btn_exit, "Exit", 'exit', wide=True)

    def _render_timeline(self):
        """Render the timeline scrubber bar."""
        # Background track -- carved brown, fully rounded like the house
        # scrollbars (replay_browser.py:639-652)
        radius = self.timeline_rect.height // 2
        pygame.draw.rect(self.screen, TIMELINE_BG, self.timeline_rect, border_radius=radius)

        # Fill up to current position
        if len(self.snapshots) > 1:
            fraction = self.current_snapshot_index / (len(self.snapshots) - 1)
        else:
            fraction = 1.0

        fill_width = int(self.timeline_rect.width * fraction)
        if fill_width > 0:
            fill_rect = pygame.Rect(
                self.timeline_rect.x, self.timeline_rect.y,
                fill_width, self.timeline_rect.height
            )
            pygame.draw.rect(self.screen, TIMELINE_FILL, fill_rect, border_radius=radius)

        # Handle / thumb
        handle_x = self.timeline_rect.x + fill_width
        handle_radius = max(4, int(11 * self.ui_scale))
        handle_y = self.timeline_rect.centery
        pygame.draw.circle(self.screen, TIMELINE_HANDLE, (handle_x, handle_y), handle_radius)
        pygame.draw.circle(self.screen, PLATE_BG, (handle_x, handle_y),
                           handle_radius, max(1, int(2 * self.ui_scale)))

        # Turn markers (tick marks for each round boundary)
        if len(self.snapshots) > 2:
            seen_turns = set()
            for i, snap in enumerate(self.snapshots):
                turn = snap.get('turn', 0)
                if turn not in seen_turns and turn > 0:
                    seen_turns.add(turn)
                    tick_x = self.timeline_rect.x + int(
                        (i / (len(self.snapshots) - 1)) * self.timeline_rect.width)
                    tick_top = self.timeline_rect.y - 2
                    tick_bottom = self.timeline_rect.bottom + 2
                    pygame.draw.line(self.screen, DIM_TEXT,
                                     (tick_x, tick_top), (tick_x, tick_bottom), 1)

    def _btn_state(self, btn_id):
        """Resolve a control's visual state from the hover / click ids."""
        if self.clicked_button == btn_id:
            return 'click'
        if self.hovered_button == btn_id:
            return 'hover'
        return 'normal'

    def _btn_surface(self, size, state):
        """
        GMenuButton.png tinted for `state`, cached by (size, state).

        Canonical house tint table, identical to replay_browser._btn_surface():
        MULT to the base level, then ADD to lift it on hover / press.
        """
        key = (size, state)
        surf = self._btn_cache.get(key)
        if surf is None:
            if len(self._btn_cache) > 64:
                self._btn_cache.clear()
            surf = pygame.transform.smoothscale(self.menu_button_img, size)
            surf.fill(BTN_MULT_NORMAL, special_flags=pygame.BLEND_RGBA_MULT)
            if state == 'click':
                surf.fill(BTN_ADD_CLICK, special_flags=pygame.BLEND_RGBA_ADD)
            elif state == 'hover':
                surf.fill(BTN_ADD_HOVER, special_flags=pygame.BLEND_RGBA_ADD)
            self._btn_cache[key] = surf
        return surf

    def _draw_plate(self, rect, state, is_selected=False):
        """
        Carved plate behind a square control.

        The square playback buttons deliberately do NOT use GMenuButton.png:
        that art is 1317x417, so squashing it square visibly distorts it. A drawn
        plate in the same palette reads correctly at any size, and takes the same
        hover / press lift as the art does.
        """
        lift = {'click': 48, 'hover': 24}.get(state, 0)
        fill = tuple(min(255, c + lift) for c in PLATE_BG)
        radius = max(3, int(4 * self.ui_scale))
        border = max(1, int(2 * self.ui_scale))
        pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        pygame.draw.rect(self.screen,
                         BRASS_COLOR if (is_selected or state != 'normal') else (120, 104, 60),
                         rect, border, border_radius=radius)

    def _draw_glyph(self, rect, kind, color):
        """
        Draw a playback glyph (play / pause / step) centred in `rect`.

        Antialiased polygons via gfxdraw -- the same idiom as the campaign
        pagination arrows (campaign_screen.py:349-376). These cannot be text:
        Cinzel has no play or pause glyph.
        """
        cx, cy = rect.center
        size = int(min(rect.width, rect.height) * 0.30)
        if size < 3:
            return
        bar_w = max(2, size // 3)

        def poly(points):
            pts = [(int(px), int(py)) for px, py in points]
            pygame.gfxdraw.filled_polygon(self.screen, pts, color)
            pygame.gfxdraw.aapolygon(self.screen, pts, color)

        def bar(left, top, w, h):
            pygame.draw.rect(self.screen, color,
                             (int(left), int(top), int(w), int(h)))

        if kind == 'play':
            poly([(cx - size * 0.5, cy - size), (cx - size * 0.5, cy + size),
                  (cx + size, cy)])
        elif kind == 'pause':
            gap = max(2, size // 3)
            bar(cx - gap - bar_w, cy - size, bar_w, size * 2)
            bar(cx + gap, cy - size, bar_w, size * 2)
        elif kind == 'step_back':
            poly([(cx + size, cy - size), (cx + size, cy + size), (cx - size * 0.2, cy)])
            bar(cx - size - bar_w * 0.2, cy - size, bar_w, size * 2)
        elif kind == 'step_forward':
            poly([(cx - size, cy - size), (cx - size, cy + size), (cx + size * 0.2, cy)])
            bar(cx + size - bar_w * 0.8, cy - size, bar_w, size * 2)

    def _render_button(self, rect, text, btn_id, glyph=None, wide=False):
        """
        Paint one control.

        wide=True wears the GMenuButton art (Speed, Exit); everything else gets a
        drawn carved plate. `glyph`, when given, replaces the text label.
        """
        state = self._btn_state(btn_id)

        if wide and self.menu_button_img is not None:
            self.screen.blit(self._btn_surface(rect.size, state), rect)
        else:
            self._draw_plate(rect, state)

        if glyph:
            self._draw_glyph(rect, glyph,
                             BRASS_COLOR if state != 'normal' else INFO_TEXT)
        elif text:
            surf = self._cached_text(text, self.font, WHITE)
            self.screen.blit(surf, surf.get_rect(center=rect.center))

    # ========== Utility ==========

    def _cached_text(self, text, font, color):
        """
        Render text with caching.

        Bounded: the action log and turn readout produce a fresh string on most
        snapshots, so an unbounded cache grew for the whole session.
        """
        key = (text, id(font), color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 512:
                self._text_cache.clear()
            surf = font.render(text, True, color)
            self._text_cache[key] = surf
        return surf

    def _fit_text(self, text, font, max_w):
        """
        Truncate text with an ellipsis so it fits max_w pixels.

        Same helper as replay_browser.py:460. The info panel is only 320*s wide,
        so player names and log lines have to be measured, not guessed at.
        """
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

    def _format_event(self, event):
        """Format an event dict into a human-readable string."""
        etype = event.get('type', 'unknown')
        if etype == 'battle':
            territory = event.get('territory', '?')
            winner = event.get('winner', -1)
            winner_name = self._get_player_name(winner) if winner >= 0 else '?'
            return f"Battle at {territory} — {winner_name} wins"
        elif etype == 'building_started':
            building = event.get('building', '?')
            territory = event.get('territory', '?')
            return f"Built {building} in {territory}"
        elif etype == 'hero_trained':
            hero = event.get('hero_type', '?')
            player = event.get('player', 0)
            return f"{self._get_player_name(player)} trained {hero}"
        elif etype == 'tech_researched':
            tech = event.get('tech_id', '?')
            player = event.get('player', 0)
            return f"{self._get_player_name(player)} researched {tech}"
        elif etype == 'movement':
            frm = event.get('from', '?')
            to = event.get('to', '?')
            count = event.get('army_count', 0)
            return f"Moved {count} from {frm} to {to}"
        else:
            return str(event)
