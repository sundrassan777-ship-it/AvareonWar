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
import math
import os
import map_data
from config.constants import (
    ORIGINAL_MAP_WIDTH, ORIGINAL_MAP_HEIGHT,
    WHITE, BLACK, PLAYER_COLORS,
)
from replay_recorder import ReplayRecorder
from global_sound import sound_manager
from music_manager import music_manager as _music_manager, MUSIC_END_EVENT as _MUSIC_END_EVENT
from utils.cursor import draw_custom_cursor
from utils.logger import get_logger
from display_utils import menu_frame_cap

logger = get_logger(__name__)

# UI colors
BRASS_COLOR = (181, 166, 66)
DARK_BG = (20, 20, 30)
PANEL_BG = (30, 30, 45, 220)
TIMELINE_BG = (40, 40, 55)
TIMELINE_FILL = (181, 166, 66)
TIMELINE_HANDLE = (255, 215, 0)
BUTTON_BG = (50, 50, 70)
BUTTON_HOVER = (70, 70, 95)
BUTTON_ACTIVE = (90, 90, 120)
INFO_TEXT = (200, 200, 210)
NEUTRAL_COLOR = (100, 100, 100)


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

        # --- Layout calculations ---
        self.ui_scale = self.height / 1080.0

        # Top bar height (player info + turn indicator)
        self.top_bar_height = int(50 * self.ui_scale)

        # Bottom control bar height (timeline + playback controls)
        self.bottom_bar_height = int(100 * self.ui_scale)

        # Right info panel width
        self.info_panel_width = int(320 * self.ui_scale)

        # Map area
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

        # Timeline bar rect (bottom, spanning full width minus margins)
        timeline_margin = int(20 * self.ui_scale)
        timeline_h = int(16 * self.ui_scale)
        self.timeline_rect = pygame.Rect(
            timeline_margin,
            self.height - self.bottom_bar_height + int(15 * self.ui_scale),
            self.width - 2 * timeline_margin,
            timeline_h
        )

        # Playback control button rects (below timeline)
        btn_size = int(36 * self.ui_scale)
        btn_y = self.timeline_rect.bottom + int(12 * self.ui_scale)
        btn_spacing = int(10 * self.ui_scale)
        controls_width = 6 * btn_size + 5 * btn_spacing  # 6 buttons
        controls_x = (self.width - controls_width) // 2

        self.btn_step_back = pygame.Rect(controls_x, btn_y, btn_size, btn_size)
        self.btn_play_pause = pygame.Rect(controls_x + btn_size + btn_spacing, btn_y, btn_size, btn_size)
        self.btn_step_forward = pygame.Rect(controls_x + 2 * (btn_size + btn_spacing), btn_y, btn_size, btn_size)
        self.btn_speed = pygame.Rect(controls_x + 3 * (btn_size + btn_spacing), btn_y, btn_size * 2, btn_size)
        self.btn_exit = pygame.Rect(
            self.width - timeline_margin - btn_size * 3, btn_y,
            btn_size * 3, btn_size
        )

        # Player POV buttons (in top bar)
        self.pov_buttons = []
        pov_btn_size = int(30 * self.ui_scale)
        pov_x = int(20 * self.ui_scale)
        pov_y = (self.top_bar_height - pov_btn_size) // 2
        # "All" button (spectator)
        self.pov_buttons.append(('all', pygame.Rect(pov_x, pov_y, int(50 * self.ui_scale), pov_btn_size)))
        pov_x += int(60 * self.ui_scale)
        # Per-player buttons
        for p in range(self.num_players):
            self.pov_buttons.append((p, pygame.Rect(pov_x, pov_y, pov_btn_size, pov_btn_size)))
            pov_x += pov_btn_size + int(6 * self.ui_scale)

        # --- Load map and assets ---
        self._load_map_assets()

        # --- Fonts ---
        font_path = 'assets/fonts/Cinzel-Regular.ttf'
        bold_font_path = 'assets/fonts/Cinzel-SemiBold.ttf'
        self.font = pygame.font.Font(font_path, max(12, int(16 * self.ui_scale)))
        self.small_font = pygame.font.Font(font_path, max(10, int(13 * self.ui_scale)))
        self.title_font = pygame.font.Font(bold_font_path, max(14, int(20 * self.ui_scale)))
        self.header_font = pygame.font.Font(bold_font_path, max(12, int(16 * self.ui_scale)))

        # Text cache for rendering performance
        self._text_cache = {}

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

    def _load_map_assets(self):
        """Load and scale map image, polygons, centers, and icon assets."""
        # Load map data for the replay's map (multi-map support)
        replay_map_id = self.metadata.get('map_id', 'avareon')
        map_data.load_map(replay_map_id)

        # Load map image from map directory or fallback
        import os
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

        # Load flag icons per player color
        self.flag_icons = {}
        flag_colors = ['Red', 'Blue', 'Green', 'Yellow']
        for p_idx in range(min(self.num_players, len(flag_colors))):
            color_name = flag_colors[p_idx]
            try:
                flag = pygame.image.load(
                    f"assets/mapicons/{color_name}Flag1.png").convert_alpha()
                self.flag_icons[p_idx] = flag
            except pygame.error:
                self.flag_icons[p_idx] = None

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

        # Territory overlay surface (cached, invalidated on snapshot change)
        self._cached_overlay = None
        self._cached_overlay_index = -1

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
            self.playing = not self.playing
            self.playback_timer = 0.0
        elif self.btn_step_back.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self._step_back()
        elif self.btn_step_forward.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self._step_forward()
        elif self.btn_speed.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
            self.speed_index = (self.speed_index + 1) % len(self.SPEEDS)
        elif self.btn_exit.collidepoint(mouse_pos):
            sound_manager.play_ui_click()
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

            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
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
                hover_surf = pygame.Surface((w, h), pygame.SRCALPHA)
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

                icon = self.building_icons.get(building_type)
                if icon:
                    icon_size = max(12, int(18 * self.camera_zoom * self.ui_scale))
                    scaled_icon = pygame.transform.smoothscale(icon, (icon_size, icon_size))
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

        # Panel background
        panel_surf = pygame.Surface(
            (self.info_panel_rect.width, self.info_panel_rect.height), pygame.SRCALPHA)
        panel_surf.fill(PANEL_BG)
        self.screen.blit(panel_surf, self.info_panel_rect)

        # Border line on left edge
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (self.info_panel_rect.x, self.info_panel_rect.y),
                         (self.info_panel_rect.x, self.info_panel_rect.bottom), 1)

        x = self.info_panel_rect.x + int(12 * self.ui_scale)
        y = self.info_panel_rect.y + int(10 * self.ui_scale) - self.info_scroll_offset
        max_y = self.info_panel_rect.bottom - int(5 * self.ui_scale)
        panel_right = self.info_panel_rect.right - int(12 * self.ui_scale)

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
            if y > max_y:
                break
            color = self._get_player_color(p)
            name = self._get_player_name(p)

            # Player name with color dot
            dot_radius = int(6 * self.ui_scale)
            if self.info_panel_rect.y <= y <= max_y:
                pygame.draw.circle(self.screen, color, (x + dot_radius, y + dot_radius + 2), dot_radius)
            name_surf = self._cached_text(name, self.font, WHITE)
            if self.info_panel_rect.y <= y <= max_y:
                self.screen.blit(name_surf, (x + dot_radius * 2 + int(6 * self.ui_scale), y))
            y += name_surf.get_height() + int(4 * self.ui_scale)

            # Gold
            gold = player_gold[p] if p < len(player_gold) else 0
            gold_text = self._cached_text(f"  Gold: {gold}", self.small_font, INFO_TEXT)
            if self.info_panel_rect.y <= y <= max_y:
                self.screen.blit(gold_text, (x, y))
            y += gold_text.get_height() + int(2 * self.ui_scale)

            # Territory count
            territory_owners = state.get('territory_owners', {})
            terr_count = sum(1 for v in territory_owners.values() if v == p)
            terr_text = self._cached_text(f"  Territories: {terr_count}", self.small_font, INFO_TEXT)
            if self.info_panel_rect.y <= y <= max_y:
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
            if self.info_panel_rect.y <= y <= max_y:
                self.screen.blit(army_text, (x, y))
            y += army_text.get_height() + int(8 * self.ui_scale)

        # --- Turn events section ---
        y += int(5 * self.ui_scale)
        events_header = self._cached_text("Turn Events", self.header_font, BRASS_COLOR)
        if self.info_panel_rect.y <= y <= max_y:
            self.screen.blit(events_header, (x, y))
        y += events_header.get_height() + int(6 * self.ui_scale)

        events = snap.get('events', [])
        if not events:
            no_events = self._cached_text("  No events", self.small_font, (120, 120, 130))
            if self.info_panel_rect.y <= y <= max_y:
                self.screen.blit(no_events, (x, y))
            y += no_events.get_height() + int(4 * self.ui_scale)
        else:
            for event in events:
                if y > max_y:
                    break
                event_str = self._format_event(event)
                event_surf = self._cached_text(f"  {event_str}", self.small_font, INFO_TEXT)
                if self.info_panel_rect.y <= y <= max_y:
                    self.screen.blit(event_surf, (x, y))
                y += event_surf.get_height() + int(3 * self.ui_scale)

        # --- Action log section ---
        y += int(8 * self.ui_scale)
        log_header = self._cached_text("Action Log", self.header_font, BRASS_COLOR)
        if self.info_panel_rect.y <= y <= max_y:
            self.screen.blit(log_header, (x, y))
        y += log_header.get_height() + int(6 * self.ui_scale)

        messages = snap.get('messages', [])
        # Show last 20 messages (most recent first)
        recent_messages = messages[-20:] if messages else []
        for msg in reversed(recent_messages):
            if y > max_y:
                break
            # Truncate long messages
            display_msg = msg if len(msg) < 50 else msg[:47] + "..."
            msg_surf = self._cached_text(f"  {display_msg}", self.small_font, (160, 160, 170))
            if self.info_panel_rect.y <= y <= max_y:
                self.screen.blit(msg_surf, (x, y))
            y += msg_surf.get_height() + int(2 * self.ui_scale)

        # Hovered territory info at bottom
        if self.hovered_territory:
            self._render_territory_tooltip()

        # Update max scroll
        total_content_height = y + self.info_scroll_offset - self.info_panel_rect.y
        self.max_info_scroll = max(0, total_content_height - self.info_panel_rect.height)

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

        # Draw tooltip box at bottom of info panel
        tooltip_h = len(lines) * int(18 * self.ui_scale) + int(12 * self.ui_scale)
        tooltip_y = self.info_panel_rect.bottom - tooltip_h - int(5 * self.ui_scale)
        tooltip_rect = pygame.Rect(
            self.info_panel_rect.x + int(5 * self.ui_scale),
            tooltip_y,
            self.info_panel_rect.width - int(10 * self.ui_scale),
            tooltip_h
        )

        # Background
        tip_surf = pygame.Surface((tooltip_rect.width, tooltip_rect.height), pygame.SRCALPHA)
        tip_surf.fill((20, 20, 35, 240))
        pygame.draw.rect(tip_surf, BRASS_COLOR, (0, 0, tooltip_rect.width, tooltip_rect.height), 1)
        self.screen.blit(tip_surf, tooltip_rect)

        # Text
        ty = tooltip_rect.y + int(6 * self.ui_scale)
        for i, line in enumerate(lines):
            font = self.header_font if i == 0 else self.small_font
            color = BRASS_COLOR if i == 0 else INFO_TEXT
            surf = self._cached_text(line, font, color)
            self.screen.blit(surf, (tooltip_rect.x + int(8 * self.ui_scale), ty))
            ty += int(18 * self.ui_scale)

    def _render_top_bar(self):
        """Render top bar with turn info and POV selector."""
        snap = self._get_current_snapshot()
        if not snap:
            return

        # Background
        top_surf = pygame.Surface((self.width, self.top_bar_height), pygame.SRCALPHA)
        top_surf.fill((25, 25, 40, 230))
        self.screen.blit(top_surf, (0, 0))

        # Bottom border
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (0, self.top_bar_height - 1),
                         (self.width, self.top_bar_height - 1), 1)

        # POV buttons
        for pov_id, rect in self.pov_buttons:
            is_selected = (pov_id == 'all' and self.selected_pov == -1) or \
                          (pov_id != 'all' and self.selected_pov == pov_id)
            is_hovered = self.hovered_button == f'pov_{pov_id}'

            if pov_id == 'all':
                # "All" text button
                bg_color = BUTTON_ACTIVE if is_selected else (BUTTON_HOVER if is_hovered else BUTTON_BG)
                pygame.draw.rect(self.screen, bg_color, rect, border_radius=4)
                pygame.draw.rect(self.screen, BRASS_COLOR if is_selected else (100, 100, 110),
                                 rect, 1, border_radius=4)
                text = self._cached_text("All", self.small_font, WHITE)
                text_rect = text.get_rect(center=rect.center)
                self.screen.blit(text, text_rect)
            else:
                # Player color button
                color = self._get_player_color(pov_id)
                pygame.draw.rect(self.screen, color, rect, border_radius=4)
                if is_selected:
                    pygame.draw.rect(self.screen, WHITE, rect, 2, border_radius=4)
                elif is_hovered:
                    pygame.draw.rect(self.screen, (200, 200, 200), rect, 1, border_radius=4)

        # Turn info (right side of top bar)
        turn = snap.get('turn', 0)
        current_player = snap.get('current_player', 0)
        total_snaps = len(self.snapshots)
        snap_idx = self.current_snapshot_index + 1

        turn_text = f"Turn {turn}  |  Snapshot {snap_idx}/{total_snaps}"
        if current_player < self.num_players:
            p_name = self._get_player_name(current_player)
            turn_text += f"  |  {p_name}'s turn"

        turn_surf = self._cached_text(turn_text, self.font, INFO_TEXT)
        turn_x = self.width - turn_surf.get_width() - int(20 * self.ui_scale)
        turn_y = (self.top_bar_height - turn_surf.get_height()) // 2
        self.screen.blit(turn_surf, (turn_x, turn_y))

        # Victory condition and game mode (center)
        vc = self.metadata.get('victory_condition', '')
        mode = self.metadata.get('game_mode', '')
        meta_text = f"{vc}  •  {mode.title()}"
        meta_surf = self._cached_text(meta_text, self.small_font, (140, 140, 150))
        meta_x = (self.width - meta_surf.get_width()) // 2
        meta_y = (self.top_bar_height - meta_surf.get_height()) // 2
        self.screen.blit(meta_surf, (meta_x, meta_y))

    def _render_bottom_bar(self):
        """Render bottom bar with timeline and playback controls."""
        # Background
        bar_y = self.height - self.bottom_bar_height
        bar_surf = pygame.Surface((self.width, self.bottom_bar_height), pygame.SRCALPHA)
        bar_surf.fill((25, 25, 40, 230))
        self.screen.blit(bar_surf, (0, bar_y))

        # Top border
        pygame.draw.line(self.screen, BRASS_COLOR,
                         (0, bar_y), (self.width, bar_y), 1)

        # Timeline bar
        self._render_timeline()

        # Playback control buttons
        self._render_button(self.btn_step_back, "<<", 'step_back')
        play_label = "||" if self.playing else ">"
        self._render_button(self.btn_play_pause, play_label, 'play_pause')
        self._render_button(self.btn_step_forward, ">>", 'step_forward')

        # Speed button
        speed_label = self.SPEED_LABELS[self.speed_index]
        self._render_button(self.btn_speed, speed_label, 'speed')

        # Exit button
        self._render_button(self.btn_exit, "Exit", 'exit')

    def _render_timeline(self):
        """Render the timeline scrubber bar."""
        # Background track
        pygame.draw.rect(self.screen, TIMELINE_BG, self.timeline_rect, border_radius=4)

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
            pygame.draw.rect(self.screen, TIMELINE_FILL, fill_rect, border_radius=4)

        # Handle / thumb
        handle_x = self.timeline_rect.x + fill_width
        handle_radius = int(10 * self.ui_scale)
        handle_y = self.timeline_rect.centery
        pygame.draw.circle(self.screen, TIMELINE_HANDLE, (handle_x, handle_y), handle_radius)
        pygame.draw.circle(self.screen, WHITE, (handle_x, handle_y), handle_radius, 1)

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
                    pygame.draw.line(self.screen, (100, 100, 110),
                                     (tick_x, tick_top), (tick_x, tick_bottom), 1)

    def _render_button(self, rect, text, btn_id):
        """Render a simple rectangular button."""
        is_hovered = self.hovered_button == btn_id
        bg = BUTTON_HOVER if is_hovered else BUTTON_BG
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        pygame.draw.rect(self.screen, (100, 100, 110), rect, 1, border_radius=4)

        text_surf = self._cached_text(text, self.small_font, WHITE)
        text_rect = text_surf.get_rect(center=rect.center)
        self.screen.blit(text_surf, text_rect)

    # ========== Utility ==========

    def _cached_text(self, text, font, color):
        """Render text with caching for performance."""
        key = (text, id(font), color)
        if key not in self._text_cache:
            self._text_cache[key] = font.render(text, True, color)
        return self._text_cache[key]

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
