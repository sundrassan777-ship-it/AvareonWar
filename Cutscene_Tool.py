# -*- coding: utf-8 -*-
# Cutscene_Tool.py
# Interactive WYSIWYG editor for campaign cutscenes

"""
Cutscene Editor Tool
====================

Visual editor for creating campaign cutscenes. Allows:
- Loading background PNG images per slide
- Setting camera viewport rects A and B (with 16:9 aspect ratio enforcement)
- Adjusting pan duration, crossfade duration, easing, rotation
- Adding subtitle text and audio per slide
- Previewing cutscenes inline via CutscenePlayer
- Saving/loading cutscene definitions to cutscene_data.json

Controls:
- Middle mouse drag: Pan the image viewport
- Mouse wheel (on image): Zoom in/out
- Mouse wheel (on selected rect): Rotate rect
- Left click on rect: Select it (A=blue, B=red)
- Left drag on rect center: Move it
- Left drag on rect corner: Resize (16:9 locked)
- Arrow keys: Pan the image viewport
- Ctrl+S / S: Save
- ESC: Save and quit
- P: Preview current cutscene

Run: python Cutscene_Tool.py
"""

import pygame
import json
import sys
import os
import math

# Initialize Pygame
pygame.init()

# Window constants
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 800
UI_PANEL_WIDTH = 350  # Wider panel for more fields
TOP_BAR_HEIGHT = 50
STATUS_BAR_HEIGHT = 30
FPS = 60

# Image preview area bounds
PREVIEW_X = 0
PREVIEW_Y = TOP_BAR_HEIGHT
PREVIEW_WIDTH = WINDOW_WIDTH - UI_PANEL_WIDTH
PREVIEW_HEIGHT = WINDOW_HEIGHT - TOP_BAR_HEIGHT - STATUS_BAR_HEIGHT

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_GRAY = (40, 40, 40)
MED_GRAY = (80, 80, 80)
LIGHT_GRAY = (200, 200, 200)
PANEL_BG = (50, 50, 55)
RED = (255, 80, 80)
BLUE = (80, 130, 255)
GREEN = (80, 200, 80)
YELLOW = (255, 220, 80)
BRASS_COLOR = (181, 166, 66)
HIGHLIGHT = (100, 140, 200)

# Aspect ratio for camera rects (16:9)
ASPECT_RATIO = 16.0 / 9.0

# Corner handle size for rect resizing (in screen pixels)
HANDLE_SIZE = 8

# All possible cutscene IDs (7 missions x intro/outro)
CUTSCENE_IDS = [
    'mission_1_intro', 'mission_1_outro',
    'mission_2_intro', 'mission_2_outro',
    'mission_3_intro', 'mission_3_outro',
    'mission_4_intro', 'mission_4_outro',
    'mission_5_intro', 'mission_5_outro',
    'mission_6_intro', 'mission_6_outro',
    'mission_7_intro', 'mission_7_outro',
]

# Easing options
EASING_OPTIONS = ['ease_in_out', 'linear', 'ease_in', 'ease_out']

# Data file path
DATA_FILE = 'cutscene_data.json'


class CutsceneTool:
    """Interactive cutscene editor tool."""

    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Cutscene Editor Tool")
        self.clock = pygame.time.Clock()

        # Initialize clipboard access for Ctrl+V paste support
        pygame.scrap.init()

        # Fonts
        try:
            self.font = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', 15)
            self.font_bold = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', 15)
            self.font_small = pygame.font.Font('assets/fonts/Cinzel-Regular.ttf', 13)
            self.font_title = pygame.font.Font('assets/fonts/Cinzel-SemiBold.ttf', 17)
        except (FileNotFoundError, OSError):
            self.font = pygame.font.Font(None, 18)
            self.font_bold = pygame.font.Font(None, 18)
            self.font_small = pygame.font.Font(None, 16)
            self.font_title = pygame.font.Font(None, 22)

        # Camera system for navigating the loaded image
        self.camera_offset = [0.0, 0.0]
        self.camera_zoom = 0.3
        self.camera_drag_start = None
        self.camera_min_zoom = 0.1
        self.camera_max_zoom = 4.0
        self.edge_scroll_speed = 5
        self.edge_scroll_margin = 20
        self.keyboard_scroll_speed = 10

        # Loaded image (current slide's background)
        self.loaded_image = None       # pygame.Surface of the current slide's image
        self.loaded_image_path = ''    # Path string
        self.image_width = 0
        self.image_height = 0

        # Cutscene data: {cutscene_id: {slides: [...]}}
        self.all_data = {}
        self.load_data()

        # Current selection state
        self.current_cutscene_idx = 0   # Index into CUTSCENE_IDS
        self.current_slide_idx = 0      # Index into current cutscene's slides

        # Camera rect interaction state
        self.selected_rect = None       # 'a' or 'b' or None
        self.dragging_rect = False      # Currently dragging a rect's center
        self.dragging_corner = None     # Which corner is being dragged (0-3, clockwise from top-left)
        self.drag_offset = (0, 0)       # Offset from rect origin to mouse position at drag start

        # Text input state -- which field is being edited
        self.active_field = None        # String key of the field being typed into
        self.field_text = ''            # Current text buffer for the active field
        self.field_cursor = 0           # Cursor position in field_text

        # Status message
        self.status_message = ''
        self.status_timer = 0.0

        # UI button rects (computed in draw methods)
        self.cutscene_btn_rects = []    # (rect, cutscene_idx) pairs
        self.slide_nav_rects = {}       # 'prev', 'next', 'add', 'remove'
        self.action_btn_rects = {}      # 'load_image', 'load_audio', 'preview', 'save'
        self.field_rects = {}           # field_name -> pygame.Rect (for click-to-edit)
        self.easing_btn_rect = None     # Rect for easing cycle button

        # Hovered elements
        self.hovered_btn = None

        # Export modal state
        self._export_modal_active = False
        self._export_options = {'subtitles': True, 'audio': True}
        self._export_modal_rects = {}  # Button/checkbox rects for the modal
        self._export_progress = None   # Float 0.0-1.0 during export, None otherwise

        # Load current slide's image if data exists
        self._sync_slide_image()

    # ========================================================================
    # DATA PERSISTENCE
    # ========================================================================

    def load_data(self):
        """Load cutscene data from JSON file."""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.all_data = json.load(f)
                print(f"Loaded cutscene data: {len(self.all_data)} cutscenes")
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading {DATA_FILE}: {e}")
                self.all_data = {}
        else:
            self.all_data = {}

    def save_data(self):
        """Save cutscene data to JSON file."""
        # Commit any active field edit before saving
        self._commit_field_edit()

        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.all_data, f, indent=2, ensure_ascii=False)
        self._set_status(f"Saved to {DATA_FILE}")
        print(f"Saved cutscene data: {len(self.all_data)} cutscenes")

    # ========================================================================
    # CURRENT DATA ACCESSORS
    # ========================================================================

    @property
    def current_cutscene_id(self):
        """Get the current cutscene ID string."""
        return CUTSCENE_IDS[self.current_cutscene_idx]

    def _get_current_cutscene(self):
        """Get the current cutscene dict, creating it if needed."""
        cid = self.current_cutscene_id
        if cid not in self.all_data:
            self.all_data[cid] = {'slides': []}
        return self.all_data[cid]

    def _get_slides(self):
        """Get the slides list for the current cutscene."""
        return self._get_current_cutscene().get('slides', [])

    def _get_current_slide(self):
        """Get the current slide dict, or None if no slides exist."""
        slides = self._get_slides()
        if 0 <= self.current_slide_idx < len(slides):
            return slides[self.current_slide_idx]
        return None

    def _ensure_slide_exists(self):
        """Ensure at least one slide exists for the current cutscene."""
        cutscene = self._get_current_cutscene()
        if 'slides' not in cutscene:
            cutscene['slides'] = []
        if len(cutscene['slides']) == 0:
            cutscene['slides'].append(self._new_slide())
            self.current_slide_idx = 0

    def _new_slide(self):
        """Create a new empty slide dict with default values."""
        return {
            'image': '',
            'camera_a': {'x': 0, 'y': 0, 'width': 800, 'height': 450, 'rotation': 0},
            'camera_b': {'x': 200, 'y': 100, 'width': 800, 'height': 450, 'rotation': 0},
            'pan_duration': 5.0,
            'crossfade_duration': 1.0,
            'easing': 'ease_in_out',
            'audio': '',
            'audio_volume': 1.0,
            'audio_start_delay': 0.0,
            'music': '',
            'music_volume': 0.4,
            'music_start_delay': 0.0,
            'subtitle': '',
        }

    # ========================================================================
    # IMAGE LOADING
    # ========================================================================

    def _sync_slide_image(self):
        """Load the image referenced by the current slide (if it changed)."""
        slide = self._get_current_slide()
        if slide is None:
            self.loaded_image = None
            self.loaded_image_path = ''
            return

        image_path = slide.get('image', '')
        if image_path == self.loaded_image_path:
            return  # Already loaded

        if image_path and os.path.exists(image_path):
            try:
                self.loaded_image = pygame.image.load(image_path).convert_alpha()
                self.loaded_image_path = image_path
                self.image_width = self.loaded_image.get_width()
                self.image_height = self.loaded_image.get_height()
                # Reset camera to fit image
                self._fit_camera_to_image()
                print(f"Loaded image: {image_path} ({self.image_width}x{self.image_height})")
            except pygame.error as e:
                print(f"Error loading image {image_path}: {e}")
                self.loaded_image = None
                self.loaded_image_path = ''
        else:
            self.loaded_image = None
            self.loaded_image_path = ''

    def _fit_camera_to_image(self):
        """Set camera zoom and offset to fit the loaded image in the preview area."""
        if not self.loaded_image:
            return
        zoom_x = PREVIEW_WIDTH / self.image_width
        zoom_y = PREVIEW_HEIGHT / self.image_height
        self.camera_zoom = min(zoom_x, zoom_y) * 0.95  # 95% to leave a small margin
        self.camera_zoom = max(self.camera_min_zoom, min(self.camera_max_zoom, self.camera_zoom))
        # Center the image
        visible_w = PREVIEW_WIDTH / self.camera_zoom
        visible_h = PREVIEW_HEIGHT / self.camera_zoom
        self.camera_offset[0] = -(visible_w - self.image_width) / 2
        self.camera_offset[1] = -(visible_h - self.image_height) / 2

    def _open_file_dialog(self, filetypes, title="Open File"):
        """Open a native file dialog using tkinter and return the selected path."""
        try:
            # Import tkinter only when needed (comes with Python stdlib)
            import tkinter as tk
            from tkinter import filedialog

            # Create a hidden root window
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            file_path = filedialog.askopenfilename(
                title=title,
                filetypes=filetypes,
            )

            root.destroy()

            # Convert to relative path if possible (relative to project root)
            if file_path:
                try:
                    rel_path = os.path.relpath(file_path)
                    # Use forward slashes for cross-platform JSON compatibility
                    rel_path = rel_path.replace('\\', '/')
                    return rel_path
                except ValueError:
                    # On Windows, relpath fails across drives
                    return file_path.replace('\\', '/')
            return ''
        except ImportError:
            self._set_status("tkinter not available - type path manually")
            return ''

    def _load_image_dialog(self):
        """Open file dialog to select a cutscene background image."""
        path = self._open_file_dialog(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")],
            title="Select Cutscene Background Image"
        )
        if path:
            slide = self._get_current_slide()
            if slide:
                slide['image'] = path
                self.loaded_image_path = ''  # Force reload
                self._sync_slide_image()

                # Auto-set camera rects to reasonable defaults based on image size
                if self.loaded_image:
                    w = self.image_width
                    h = self.image_height
                    # Camera A: centered, covering 60% of image width (16:9)
                    a_w = int(w * 0.6)
                    a_h = int(a_w / ASPECT_RATIO)
                    a_x = (w - a_w) // 2
                    a_y = (h - a_h) // 2
                    slide['camera_a'] = {'x': a_x, 'y': a_y, 'width': a_w, 'height': a_h, 'rotation': 0}

                    # Camera B: slightly offset and different zoom
                    b_w = int(w * 0.5)
                    b_h = int(b_w / ASPECT_RATIO)
                    b_x = (w - b_w) // 2 + int(w * 0.1)
                    b_y = (h - b_h) // 2 + int(h * 0.05)
                    slide['camera_b'] = {'x': b_x, 'y': b_y, 'width': b_w, 'height': b_h, 'rotation': 0}

    def _load_audio_dialog(self):
        """Open file dialog to select a voiceover audio file for the current slide."""
        path = self._open_file_dialog(
            filetypes=[("Audio files", "*.mp3 *.wav *.ogg"), ("All files", "*.*")],
            title="Select Voiceover Audio"
        )
        if path:
            slide = self._get_current_slide()
            if slide:
                slide['audio'] = path
                self._set_status(f"Voice set: {os.path.basename(path)}")

    def _load_music_dialog(self):
        """Open file dialog to select a music track for the current slide."""
        path = self._open_file_dialog(
            filetypes=[("Audio files", "*.mp3 *.wav *.ogg"), ("All files", "*.*")],
            title="Select Music Track"
        )
        if path:
            slide = self._get_current_slide()
            if slide:
                slide['music'] = path
                self._set_status(f"Music set: {os.path.basename(path)}")

    # ========================================================================
    # CAMERA SYSTEM (adapted from Polygon_Tool pattern)
    # ========================================================================

    def screen_to_world(self, screen_pos):
        """Convert screen coordinates to world (image) coordinates."""
        sx, sy = screen_pos
        # Offset for the preview area position
        world_x = ((sx - PREVIEW_X) / self.camera_zoom) + self.camera_offset[0]
        world_y = ((sy - PREVIEW_Y) / self.camera_zoom) + self.camera_offset[1]
        return (world_x, world_y)

    def world_to_screen(self, world_pos):
        """Convert world (image) coordinates to screen coordinates."""
        wx, wy = world_pos
        screen_x = (wx - self.camera_offset[0]) * self.camera_zoom + PREVIEW_X
        screen_y = (wy - self.camera_offset[1]) * self.camera_zoom + PREVIEW_Y
        return (screen_x, screen_y)

    def clamp_camera_to_bounds(self):
        """Prevent camera from scrolling too far off the image."""
        if not self.loaded_image:
            return
        visible_w = PREVIEW_WIDTH / self.camera_zoom
        visible_h = PREVIEW_HEIGHT / self.camera_zoom
        max_x = max(0, self.image_width - visible_w)
        max_y = max(0, self.image_height - visible_h)
        # Allow some negative offset so image can be centered when smaller than viewport
        self.camera_offset[0] = max(-visible_w * 0.3, min(self.camera_offset[0], max_x + visible_w * 0.3))
        self.camera_offset[1] = max(-visible_h * 0.3, min(self.camera_offset[1], max_y + visible_h * 0.3))

    def handle_camera_drag(self, pos, buttons):
        """Handle middle-mouse camera dragging."""
        if buttons[1]:  # Middle mouse button
            if self.camera_drag_start is None:
                self.camera_drag_start = pos
            else:
                dx = pos[0] - self.camera_drag_start[0]
                dy = pos[1] - self.camera_drag_start[1]
                self.camera_offset[0] -= dx / self.camera_zoom
                self.camera_offset[1] -= dy / self.camera_zoom
                self.clamp_camera_to_bounds()
            self.camera_drag_start = pos
        else:
            self.camera_drag_start = None

    def handle_edge_scrolling(self, pos):
        """Handle edge scrolling when mouse is near preview area edges."""
        x, y = pos
        # Only scroll when mouse is in the preview area
        if x >= PREVIEW_WIDTH or y < TOP_BAR_HEIGHT or y >= WINDOW_HEIGHT - STATUS_BAR_HEIGHT:
            return

        scroll_x = 0
        scroll_y = 0
        base_speed = 10.0 * (self.camera_zoom / self.camera_min_zoom)

        if x < PREVIEW_X + self.edge_scroll_margin:
            dist = self.edge_scroll_margin - (x - PREVIEW_X)
            scroll_x = -base_speed * (dist / self.edge_scroll_margin)
        elif x > PREVIEW_X + PREVIEW_WIDTH - self.edge_scroll_margin:
            dist = x - (PREVIEW_X + PREVIEW_WIDTH - self.edge_scroll_margin)
            scroll_x = base_speed * (dist / self.edge_scroll_margin)

        if y < PREVIEW_Y + self.edge_scroll_margin:
            dist = self.edge_scroll_margin - (y - PREVIEW_Y)
            scroll_y = -base_speed * (dist / self.edge_scroll_margin)
        elif y > PREVIEW_Y + PREVIEW_HEIGHT - self.edge_scroll_margin:
            dist = y - (PREVIEW_Y + PREVIEW_HEIGHT - self.edge_scroll_margin)
            scroll_y = base_speed * (dist / self.edge_scroll_margin)

        if scroll_x != 0 or scroll_y != 0:
            self.camera_offset[0] += scroll_x / self.camera_zoom
            self.camera_offset[1] += scroll_y / self.camera_zoom
            self.clamp_camera_to_bounds()

    def handle_keyboard_camera(self, keys):
        """Handle arrow key camera panning."""
        scroll_x = 0
        scroll_y = 0
        if keys[pygame.K_LEFT]:
            scroll_x = -self.keyboard_scroll_speed
        if keys[pygame.K_RIGHT]:
            scroll_x = self.keyboard_scroll_speed
        if keys[pygame.K_UP]:
            scroll_y = -self.keyboard_scroll_speed
        if keys[pygame.K_DOWN]:
            scroll_y = self.keyboard_scroll_speed

        if scroll_x != 0 or scroll_y != 0:
            self.camera_offset[0] += scroll_x / self.camera_zoom
            self.camera_offset[1] += scroll_y / self.camera_zoom
            self.clamp_camera_to_bounds()

    def handle_camera_zoom(self, delta, mouse_pos):
        """Handle camera zoom with mouse wheel (zoom toward cursor)."""
        # Only zoom when mouse is in preview area
        mx, my = mouse_pos
        if mx >= PREVIEW_WIDTH or my < TOP_BAR_HEIGHT or my >= WINDOW_HEIGHT - STATUS_BAR_HEIGHT:
            return

        world_before = self.screen_to_world(mouse_pos)
        zoom_factor = 1.1 if delta > 0 else 0.9
        new_zoom = self.camera_zoom * zoom_factor
        new_zoom = max(self.camera_min_zoom, min(self.camera_max_zoom, new_zoom))

        if new_zoom != self.camera_zoom:
            self.camera_zoom = new_zoom
            world_after = self.screen_to_world(mouse_pos)
            self.camera_offset[0] += world_before[0] - world_after[0]
            self.camera_offset[1] += world_before[1] - world_after[1]
            self.clamp_camera_to_bounds()

    # ========================================================================
    # RECT INTERACTION (selecting, dragging, resizing camera rects)
    # ========================================================================

    def _get_rect_screen_corners(self, cam_rect):
        """Get the 4 corners of a camera rect in screen coordinates."""
        x = cam_rect['x']
        y = cam_rect['y']
        w = cam_rect['width']
        h = cam_rect['height']
        corners_world = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return [self.world_to_screen(c) for c in corners_world]

    def _get_rect_screen_bounds(self, cam_rect):
        """Get the bounding rect in screen coordinates."""
        corners = self._get_rect_screen_corners(cam_rect)
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        return pygame.Rect(int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))

    def _point_in_rect(self, point, cam_rect):
        """Check if a screen point is inside a camera rect."""
        bounds = self._get_rect_screen_bounds(cam_rect)
        return bounds.collidepoint(point)

    def _point_near_corner(self, point, cam_rect):
        """Check if a screen point is near any corner of a camera rect. Returns corner index 0-3 or None."""
        corners = self._get_rect_screen_corners(cam_rect)
        px, py = point
        for i, (cx, cy) in enumerate(corners):
            if abs(px - cx) < HANDLE_SIZE and abs(py - cy) < HANDLE_SIZE:
                return i
        return None

    def _handle_rect_mousedown(self, mouse_pos):
        """Handle left-click on camera rects. Returns True if a rect was clicked."""
        slide = self._get_current_slide()
        if not slide:
            return False

        cam_a = slide.get('camera_a')
        cam_b = slide.get('camera_b')
        if not cam_a or not cam_b:
            return False

        # Check corners first (for resize), then body (for drag)
        # Check both rects, prioritize the selected one
        rects_to_check = [('b', cam_b), ('a', cam_a)]
        if self.selected_rect == 'a':
            rects_to_check = [('a', cam_a), ('b', cam_b)]

        for rect_id, cam_rect in rects_to_check:
            corner = self._point_near_corner(mouse_pos, cam_rect)
            if corner is not None:
                self.selected_rect = rect_id
                self.dragging_corner = corner
                self.dragging_rect = False
                return True

        for rect_id, cam_rect in rects_to_check:
            if self._point_in_rect(mouse_pos, cam_rect):
                self.selected_rect = rect_id
                self.dragging_rect = True
                self.dragging_corner = None
                # Calculate drag offset (in world coords)
                world_mouse = self.screen_to_world(mouse_pos)
                self.drag_offset = (world_mouse[0] - cam_rect['x'], world_mouse[1] - cam_rect['y'])
                return True

        return False

    def _handle_rect_mousemotion(self, mouse_pos):
        """Handle mouse movement while dragging a rect or corner."""
        slide = self._get_current_slide()
        if not slide or not self.selected_rect:
            return

        cam_key = f'camera_{self.selected_rect}'
        cam_rect = slide.get(cam_key)
        if not cam_rect:
            return

        world_mouse = self.screen_to_world(mouse_pos)

        if self.dragging_rect:
            # Move the rect center
            cam_rect['x'] = world_mouse[0] - self.drag_offset[0]
            cam_rect['y'] = world_mouse[1] - self.drag_offset[1]

        elif self.dragging_corner is not None:
            # Resize from corner, maintaining 16:9 aspect ratio
            # Anchor is the opposite corner
            x = cam_rect['x']
            y = cam_rect['y']
            w = cam_rect['width']
            h = cam_rect['height']

            # Determine anchor point (opposite corner)
            if self.dragging_corner == 0:    # Top-left dragged -> anchor is bottom-right
                anchor_x, anchor_y = x + w, y + h
            elif self.dragging_corner == 1:  # Top-right -> anchor is bottom-left
                anchor_x, anchor_y = x, y + h
            elif self.dragging_corner == 2:  # Bottom-right -> anchor is top-left
                anchor_x, anchor_y = x, y
            else:                            # Bottom-left -> anchor is top-right
                anchor_x, anchor_y = x + w, y

            # Compute new width from mouse distance, enforce aspect ratio
            new_w = abs(world_mouse[0] - anchor_x)
            new_h = new_w / ASPECT_RATIO
            new_w = max(50, new_w)  # Minimum size
            new_h = max(50 / ASPECT_RATIO, new_h)

            # Set new position based on which corner is anchored
            if self.dragging_corner == 0:
                cam_rect['x'] = anchor_x - new_w
                cam_rect['y'] = anchor_y - new_h
            elif self.dragging_corner == 1:
                cam_rect['x'] = anchor_x
                cam_rect['y'] = anchor_y - new_h
            elif self.dragging_corner == 2:
                cam_rect['x'] = anchor_x
                cam_rect['y'] = anchor_y
            else:
                cam_rect['x'] = anchor_x - new_w
                cam_rect['y'] = anchor_y

            cam_rect['width'] = new_w
            cam_rect['height'] = new_h

    def _handle_rect_mouseup(self):
        """Handle mouse release after dragging."""
        self.dragging_rect = False
        self.dragging_corner = None

    def _handle_rect_scroll(self, delta):
        """Rotate the selected rect when scrolling over it."""
        slide = self._get_current_slide()
        if not slide or not self.selected_rect:
            return False

        cam_key = f'camera_{self.selected_rect}'
        cam_rect = slide.get(cam_key)
        if not cam_rect:
            return False

        # Check if mouse is over the selected rect
        mouse_pos = pygame.mouse.get_pos()
        if self._point_in_rect(mouse_pos, cam_rect):
            current_rot = cam_rect.get('rotation', 0)
            cam_rect['rotation'] = current_rot + delta * 1.0  # 1 degree per scroll tick
            return True
        return False

    # ========================================================================
    # TEXT FIELD INPUT
    # ========================================================================

    def _start_field_edit(self, field_name, current_value):
        """Begin editing a text/numeric field."""
        self._commit_field_edit()  # Commit any previous edit
        self.active_field = field_name
        self.field_text = str(current_value)
        self.field_cursor = len(self.field_text)

    def _commit_field_edit(self):
        """Commit the current field edit to the slide data."""
        if not self.active_field:
            return

        slide = self._get_current_slide()
        if not slide:
            self.active_field = None
            return

        field = self.active_field
        text = self.field_text

        # Parse and apply the value based on field type
        if field == 'subtitle':
            slide['subtitle'] = text
        elif field == 'pan_duration':
            try:
                slide['pan_duration'] = max(0.1, float(text))
            except ValueError:
                pass
        elif field == 'crossfade_duration':
            try:
                slide['crossfade_duration'] = max(0.0, float(text))
            except ValueError:
                pass
        elif field == 'audio_start_delay':
            try:
                slide['audio_start_delay'] = max(0.0, float(text))
            except ValueError:
                pass
        elif field == 'audio_volume':
            try:
                slide['audio_volume'] = max(0.0, min(2.0, float(text)))
            except ValueError:
                pass
        elif field == 'music_start_delay':
            try:
                slide['music_start_delay'] = max(0.0, float(text))
            except ValueError:
                pass
        elif field == 'music_volume':
            try:
                slide['music_volume'] = max(0.0, min(2.0, float(text)))
            except ValueError:
                pass
        elif field.startswith('cam_'):
            # Fields like cam_a_x, cam_a_y, cam_a_width, cam_a_height, cam_a_rotation
            parts = field.split('_')  # ['cam', 'a'/'b', 'x'/'y'/'width'/'height'/'rotation']
            if len(parts) == 3:
                rect_id = parts[1]
                prop = parts[2]
                cam_key = f'camera_{rect_id}'
                if cam_key in slide:
                    try:
                        val = float(text)
                        slide[cam_key][prop] = val
                        # Enforce aspect ratio when width or height changes
                        if prop == 'width':
                            slide[cam_key]['height'] = val / ASPECT_RATIO
                        elif prop == 'height':
                            slide[cam_key]['width'] = val * ASPECT_RATIO
                    except ValueError:
                        pass

        self.active_field = None
        self.field_text = ''

    def _handle_field_keydown(self, event):
        """Handle keyboard input for text field editing."""
        if not self.active_field:
            return False

        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            self._commit_field_edit()
            return True
        elif event.key == pygame.K_ESCAPE:
            self.active_field = None
            self.field_text = ''
            return True
        elif event.key == pygame.K_BACKSPACE:
            if self.field_cursor > 0:
                self.field_text = self.field_text[:self.field_cursor - 1] + self.field_text[self.field_cursor:]
                self.field_cursor -= 1
            return True
        elif event.key == pygame.K_DELETE:
            if self.field_cursor < len(self.field_text):
                self.field_text = self.field_text[:self.field_cursor] + self.field_text[self.field_cursor + 1:]
            return True
        elif event.key == pygame.K_LEFT:
            self.field_cursor = max(0, self.field_cursor - 1)
            return True
        elif event.key == pygame.K_RIGHT:
            self.field_cursor = min(len(self.field_text), self.field_cursor + 1)
            return True
        elif event.key == pygame.K_HOME:
            self.field_cursor = 0
            return True
        elif event.key == pygame.K_END:
            self.field_cursor = len(self.field_text)
            return True
        elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
            # Ctrl+V: Paste from clipboard
            try:
                clipboard_text = pygame.scrap.get(pygame.SCRAP_TEXT)
                if clipboard_text:
                    # Decode bytes to string, strip null terminator
                    paste = clipboard_text.decode('utf-8', errors='ignore').rstrip('\x00')
                    # Replace newlines with spaces (single-line fields)
                    paste = paste.replace('\r\n', ' ').replace('\n', ' ')
                    self.field_text = self.field_text[:self.field_cursor] + paste + self.field_text[self.field_cursor:]
                    self.field_cursor += len(paste)
            except Exception:
                pass
            return True
        elif event.key == pygame.K_a and (event.mod & pygame.KMOD_CTRL):
            # Ctrl+A: Select all (replace entire field on next typed character)
            self.field_cursor = len(self.field_text)
            return True
        elif event.unicode and event.unicode.isprintable():
            self.field_text = self.field_text[:self.field_cursor] + event.unicode + self.field_text[self.field_cursor:]
            self.field_cursor += 1
            return True

        return False

    # ========================================================================
    # SLIDE NAVIGATION
    # ========================================================================

    def _select_cutscene(self, idx):
        """Switch to a different cutscene."""
        self._commit_field_edit()
        self.current_cutscene_idx = idx
        self.current_slide_idx = 0
        self.selected_rect = None
        self.loaded_image_path = ''  # Force image reload
        self._sync_slide_image()

    def _nav_slide(self, direction):
        """Navigate to previous (-1) or next (+1) slide."""
        self._commit_field_edit()
        slides = self._get_slides()
        new_idx = self.current_slide_idx + direction
        if 0 <= new_idx < len(slides):
            self.current_slide_idx = new_idx
            self.selected_rect = None
            self.loaded_image_path = ''
            self._sync_slide_image()

    def _add_slide(self):
        """Add a new slide after the current one."""
        self._commit_field_edit()
        cutscene = self._get_current_cutscene()
        if 'slides' not in cutscene:
            cutscene['slides'] = []
        new_slide = self._new_slide()
        insert_idx = self.current_slide_idx + 1
        cutscene['slides'].insert(insert_idx, new_slide)
        self.current_slide_idx = insert_idx
        self.selected_rect = None
        self.loaded_image_path = ''
        self._sync_slide_image()
        self._set_status(f"Added slide {insert_idx + 1}")

    def _remove_slide(self):
        """Remove the current slide."""
        slides = self._get_slides()
        if len(slides) <= 1:
            self._set_status("Cannot remove the last slide")
            return
        self._commit_field_edit()
        slides.pop(self.current_slide_idx)
        self.current_slide_idx = min(self.current_slide_idx, len(slides) - 1)
        self.selected_rect = None
        self.loaded_image_path = ''
        self._sync_slide_image()
        self._set_status(f"Removed slide")

    # ========================================================================
    # PREVIEW
    # ========================================================================

    def _preview_cutscene(self):
        """Launch the CutscenePlayer to preview the current cutscene."""
        self._commit_field_edit()
        self.save_data()  # Save first so player reads latest data

        try:
            from cutscene_player import CutscenePlayer
            player = CutscenePlayer(self.screen, self.current_cutscene_id)
            if player.has_cutscene:
                player.run()
                self._set_status("Preview complete")
            else:
                self._set_status("No cutscene data to preview -- add slides and images first")
        except Exception as e:
            self._set_status(f"Preview error: {e}")

    # ========================================================================
    # MP4 EXPORT
    # ========================================================================

    def _open_export_modal(self):
        """Open the export options modal dialog."""
        self._commit_field_edit()
        self._export_modal_active = True

    def _draw_export_modal(self):
        """Draw the export options modal overlay on top of the tool UI."""
        # Semi-transparent dark overlay behind the modal
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        # Modal box dimensions
        modal_w = 380
        modal_h = 300
        modal_x = (WINDOW_WIDTH - modal_w) // 2
        modal_y = (WINDOW_HEIGHT - modal_h) // 2

        # Draw modal background with border
        modal_rect = pygame.Rect(modal_x, modal_y, modal_w, modal_h)
        pygame.draw.rect(self.screen, PANEL_BG, modal_rect, border_radius=8)
        pygame.draw.rect(self.screen, BRASS_COLOR, modal_rect, 2, border_radius=8)

        # Title
        title = self.font_title.render("Export MP4", True, WHITE)
        self.screen.blit(title, (modal_x + (modal_w - title.get_width()) // 2, modal_y + 16))

        # Resolution info
        info = self.font_small.render("1920x1080 @ 60 FPS", True, LIGHT_GRAY)
        self.screen.blit(info, (modal_x + (modal_w - info.get_width()) // 2, modal_y + 46))

        # Checkboxes
        self._export_modal_rects = {}
        check_x = modal_x + 40
        check_y = modal_y + 80
        check_size = 18
        check_gap = 36

        # Subtitle checkbox
        sub_rect = pygame.Rect(check_x, check_y, check_size, check_size)
        self._export_modal_rects['subtitles'] = sub_rect
        pygame.draw.rect(self.screen, WHITE, sub_rect, 1, border_radius=3)
        if self._export_options['subtitles']:
            # Draw checkmark
            inner = sub_rect.inflate(-6, -6)
            pygame.draw.rect(self.screen, GREEN, inner, border_radius=2)
        sub_label = self.font.render("Include subtitles", True, WHITE)
        self.screen.blit(sub_label, (check_x + check_size + 10, check_y))

        # Audio checkbox
        check_y += check_gap
        aud_rect = pygame.Rect(check_x, check_y, check_size, check_size)
        self._export_modal_rects['audio'] = aud_rect
        pygame.draw.rect(self.screen, WHITE, aud_rect, 1, border_radius=3)
        if self._export_options['audio']:
            inner = aud_rect.inflate(-6, -6)
            pygame.draw.rect(self.screen, GREEN, inner, border_radius=2)
        aud_label = self.font.render("Include audio", True, WHITE)
        self.screen.blit(aud_label, (check_x + check_size + 10, check_y))

        # Buttons -- 3 in a row: Export Current | Export All | Cancel
        btn_w = 105
        btn_h = 34
        btn_y = modal_y + modal_h - btn_h - 24
        btn_gap = 10
        total_btn_w = btn_w * 3 + btn_gap * 2
        btn_start_x = modal_x + (modal_w - total_btn_w) // 2
        mouse_pos = pygame.mouse.get_pos()

        # Export Current button
        export_rect = pygame.Rect(btn_start_x, btn_y, btn_w, btn_h)
        self._export_modal_rects['export'] = export_rect
        is_hovered = export_rect.collidepoint(mouse_pos)
        bg = (60, 120, 60) if is_hovered else (50, 100, 50)
        pygame.draw.rect(self.screen, bg, export_rect, border_radius=5)
        pygame.draw.rect(self.screen, GREEN, export_rect, 1, border_radius=5)
        exp_label = self.font.render("Current", True, WHITE)
        self.screen.blit(exp_label, (export_rect.x + (btn_w - exp_label.get_width()) // 2,
                                     export_rect.y + (btn_h - exp_label.get_height()) // 2))

        # Export All button
        export_all_rect = pygame.Rect(btn_start_x + btn_w + btn_gap, btn_y, btn_w, btn_h)
        self._export_modal_rects['export_all'] = export_all_rect
        is_hovered = export_all_rect.collidepoint(mouse_pos)
        bg = (60, 100, 120) if is_hovered else (45, 80, 100)
        pygame.draw.rect(self.screen, bg, export_all_rect, border_radius=5)
        pygame.draw.rect(self.screen, YELLOW, export_all_rect, 1, border_radius=5)
        all_label = self.font.render("All", True, WHITE)
        self.screen.blit(all_label, (export_all_rect.x + (btn_w - all_label.get_width()) // 2,
                                     export_all_rect.y + (btn_h - all_label.get_height()) // 2))

        # Cancel button
        cancel_rect = pygame.Rect(btn_start_x + (btn_w + btn_gap) * 2, btn_y, btn_w, btn_h)
        self._export_modal_rects['cancel'] = cancel_rect
        is_hovered = cancel_rect.collidepoint(mouse_pos)
        bg = (100, 60, 60) if is_hovered else (80, 50, 50)
        pygame.draw.rect(self.screen, bg, cancel_rect, border_radius=5)
        pygame.draw.rect(self.screen, RED, cancel_rect, 1, border_radius=5)
        can_label = self.font.render("Cancel", True, WHITE)
        self.screen.blit(can_label, (cancel_rect.x + (btn_w - can_label.get_width()) // 2,
                                     cancel_rect.y + (btn_h - can_label.get_height()) // 2))

    def _handle_export_modal_click(self, pos):
        """Handle mouse clicks within the export modal."""
        # Check checkbox clicks
        for key in ('subtitles', 'audio'):
            rect = self._export_modal_rects.get(key)
            if rect and rect.collidepoint(pos):
                self._export_options[key] = not self._export_options[key]
                return

        # Check export current button
        rect = self._export_modal_rects.get('export')
        if rect and rect.collidepoint(pos):
            self._export_modal_active = False
            self._start_export()
            return

        # Check export all button
        rect = self._export_modal_rects.get('export_all')
        if rect and rect.collidepoint(pos):
            self._export_modal_active = False
            self._start_export_all()
            return

        # Check cancel button
        rect = self._export_modal_rects.get('cancel')
        if rect and rect.collidepoint(pos):
            self._export_modal_active = False
            return

    def _start_export(self):
        """Open file save dialog and begin the export process."""
        import tkinter as tk
        from tkinter import filedialog

        # Use tkinter file dialog for save path
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        # Default filename based on cutscene ID
        default_name = f"{self.current_cutscene_id}.mp4"

        output_path = filedialog.asksaveasfilename(
            title="Export Cutscene as MP4",
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4")],
            initialfile=default_name,
        )
        root.destroy()

        if not output_path:
            self._set_status("Export cancelled")
            return

        # Save cutscene data first (so exporter reads latest)
        self.save_data()

        # Run the export with progress overlay
        self._run_export(output_path)

    def _run_export(self, output_path):
        """Execute the export process with a progress overlay."""
        try:
            from cutscene_exporter import CutsceneExporter, _get_ffmpeg_path
        except ImportError as e:
            self._set_status(f"Export error: {e}")
            return

        # Check ffmpeg availability before starting
        if not _get_ffmpeg_path():
            self._set_status("ffmpeg not found. Install: pip install imageio-ffmpeg")
            return

        self._export_progress = 0.0
        cancelled = False

        def progress_callback(progress):
            """Called by the exporter to update progress and check for cancellation."""
            self._export_progress = progress
            # Redraw the progress overlay
            self._draw_export_progress()
            pygame.display.flip()

            # Pump events to check for ESC cancellation
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return False
            return True

        try:
            exporter = CutsceneExporter(
                self.current_cutscene_id,
                include_subtitles=self._export_options['subtitles'],
                include_audio=self._export_options['audio'],
            )

            if not exporter.has_cutscene:
                self._set_status("No cutscene data to export")
                self._export_progress = None
                return

            success = exporter.export(output_path, progress_callback=progress_callback)

            if success:
                # Show file size in status
                try:
                    size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    self._set_status(f"Exported: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
                except OSError:
                    self._set_status(f"Exported: {os.path.basename(output_path)}")
            else:
                if self._export_progress is not None and self._export_progress < 1.0:
                    self._set_status("Export cancelled")
                else:
                    self._set_status("Export failed -- check console for details")

        except Exception as e:
            self._set_status(f"Export error: {e}")

        self._export_progress = None

    def _start_export_all(self):
        """Open file save dialog and export all cutscenes concatenated into one MP4."""
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        output_path = filedialog.asksaveasfilename(
            title="Export All Cutscenes as MP4",
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4")],
            initialfile="all_cutscenes.mp4",
        )
        root.destroy()

        if not output_path:
            self._set_status("Export cancelled")
            return

        # Save cutscene data first (so exporter reads latest)
        self.save_data()

        self._run_export_all(output_path)

    def _run_export_all(self, output_path):
        """Export all cutscenes that have data into a single concatenated MP4."""
        try:
            from cutscene_exporter import export_all_cutscenes, _get_ffmpeg_path
        except ImportError as e:
            self._set_status(f"Export error: {e}")
            return

        if not _get_ffmpeg_path():
            self._set_status("ffmpeg not found. Install: pip install imageio-ffmpeg")
            return

        self._export_progress = 0.0

        def progress_callback(progress):
            """Called by the exporter to update progress and check for cancellation."""
            self._export_progress = progress
            self._draw_export_progress()
            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return False
            return True

        try:
            # Export all cutscene IDs in order
            success = export_all_cutscenes(
                CUTSCENE_IDS,
                output_path,
                include_subtitles=self._export_options['subtitles'],
                include_audio=self._export_options['audio'],
                progress_callback=progress_callback,
            )

            if success:
                try:
                    size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    self._set_status(f"Exported all: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
                except OSError:
                    self._set_status(f"Exported all: {os.path.basename(output_path)}")
            else:
                if self._export_progress is not None and self._export_progress < 1.0:
                    self._set_status("Export cancelled")
                else:
                    self._set_status("Export failed -- check console for details")

        except Exception as e:
            self._set_status(f"Export error: {e}")

        self._export_progress = None

    def _draw_export_progress(self):
        """Draw a progress overlay during export. Called each frame by the exporter."""
        # Redraw the normal tool UI underneath
        self.screen.fill(BLACK)
        self.draw_image_preview()
        self.draw_top_bar()
        self.draw_right_panel()
        self.draw_status_bar()

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Progress box
        box_w = 400
        box_h = 130
        box_x = (WINDOW_WIDTH - box_w) // 2
        box_y = (WINDOW_HEIGHT - box_h) // 2

        pygame.draw.rect(self.screen, PANEL_BG, (box_x, box_y, box_w, box_h), border_radius=8)
        pygame.draw.rect(self.screen, BRASS_COLOR, (box_x, box_y, box_w, box_h), 2, border_radius=8)

        # Title
        title = self.font_title.render("Exporting...", True, WHITE)
        self.screen.blit(title, (box_x + (box_w - title.get_width()) // 2, box_y + 16))

        # Progress bar
        bar_margin = 30
        bar_x = box_x + bar_margin
        bar_y = box_y + 56
        bar_w = box_w - bar_margin * 2
        bar_h = 20
        progress = self._export_progress or 0.0

        # Bar background
        pygame.draw.rect(self.screen, DARK_GRAY, (bar_x, bar_y, bar_w, bar_h), border_radius=4)
        # Bar fill
        fill_w = max(0, int(bar_w * progress))
        if fill_w > 0:
            pygame.draw.rect(self.screen, GREEN, (bar_x, bar_y, fill_w, bar_h), border_radius=4)
        # Bar border
        pygame.draw.rect(self.screen, MED_GRAY, (bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)

        # Percentage text
        pct_text = self.font.render(f"{int(progress * 100)}%", True, WHITE)
        self.screen.blit(pct_text, (box_x + (box_w - pct_text.get_width()) // 2, bar_y + bar_h + 6))

        # Cancel hint
        hint = self.font_small.render("Press ESC to cancel", True, LIGHT_GRAY)
        self.screen.blit(hint, (box_x + (box_w - hint.get_width()) // 2, bar_y + bar_h + 28))

    # ========================================================================
    # STATUS BAR
    # ========================================================================

    def _set_status(self, message):
        """Set a status bar message that auto-clears after a few seconds."""
        self.status_message = message
        self.status_timer = 3.0

    # ========================================================================
    # DRAWING
    # ========================================================================

    def draw_top_bar(self):
        """Draw the top bar with cutscene selector and slide navigation."""
        # Background
        pygame.draw.rect(self.screen, DARK_GRAY, (0, 0, WINDOW_WIDTH, TOP_BAR_HEIGHT))
        pygame.draw.line(self.screen, MED_GRAY, (0, TOP_BAR_HEIGHT - 1), (WINDOW_WIDTH, TOP_BAR_HEIGHT - 1))

        # Cutscene selector buttons (scrollable horizontally)
        x = 10
        y = 8
        btn_h = TOP_BAR_HEIGHT - 16
        self.cutscene_btn_rects = []

        for i, cid in enumerate(CUTSCENE_IDS):
            # Short label: "M1 Intro", "M1 Outro", etc.
            parts = cid.split('_')
            label = f"M{parts[1][0]} {'In' if parts[2] == 'intro' else 'Out'}"

            text_surf = self.font_small.render(label, True, WHITE)
            btn_w = text_surf.get_width() + 16
            btn_rect = pygame.Rect(x, y, btn_w, btn_h)

            # Highlight current selection
            if i == self.current_cutscene_idx:
                pygame.draw.rect(self.screen, HIGHLIGHT, btn_rect, border_radius=4)
            elif btn_rect.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(self.screen, MED_GRAY, btn_rect, border_radius=4)
            else:
                pygame.draw.rect(self.screen, (60, 60, 65), btn_rect, border_radius=4)

            # Show dot indicator if cutscene has data
            if cid in self.all_data and self.all_data[cid].get('slides'):
                pygame.draw.circle(self.screen, GREEN, (btn_rect.right - 6, btn_rect.top + 6), 3)

            self.screen.blit(text_surf, (x + 8, y + (btn_h - text_surf.get_height()) // 2))
            self.cutscene_btn_rects.append((btn_rect, i))
            x += btn_w + 4

        # Slide navigation (right side of top bar)
        slides = self._get_slides()
        num_slides = len(slides)
        slide_label = f"Slide {self.current_slide_idx + 1}/{max(1, num_slides)}"
        slide_text = self.font_bold.render(slide_label, True, YELLOW)

        nav_x = WINDOW_WIDTH - UI_PANEL_WIDTH - 230
        self.screen.blit(slide_text, (nav_x, y + (btn_h - slide_text.get_height()) // 2))

        # Navigation buttons: < > + -
        btn_x = nav_x + slide_text.get_width() + 12
        for label, key in [('<', 'prev'), ('>', 'next'), ('+', 'add'), ('-', 'remove')]:
            btn_rect = pygame.Rect(btn_x, y, 30, btn_h)
            color = MED_GRAY
            if btn_rect.collidepoint(pygame.mouse.get_pos()):
                color = HIGHLIGHT
            pygame.draw.rect(self.screen, color, btn_rect, border_radius=4)
            lbl = self.font_bold.render(label, True, WHITE)
            self.screen.blit(lbl, (btn_x + (30 - lbl.get_width()) // 2, y + (btn_h - lbl.get_height()) // 2))
            self.slide_nav_rects[key] = btn_rect
            btn_x += 34

    def draw_image_preview(self):
        """Draw the image preview area with camera rect overlays."""
        # Clip to preview area
        clip_rect = pygame.Rect(PREVIEW_X, PREVIEW_Y, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.screen.set_clip(clip_rect)

        # Background
        self.screen.fill((30, 30, 35), clip_rect)

        if self.loaded_image:
            # Draw the image at current camera position/zoom
            scaled_w = int(self.image_width * self.camera_zoom)
            scaled_h = int(self.image_height * self.camera_zoom)

            img_x = int(-self.camera_offset[0] * self.camera_zoom) + PREVIEW_X
            img_y = int(-self.camera_offset[1] * self.camera_zoom) + PREVIEW_Y

            # Only scale if visible
            if img_x < PREVIEW_X + PREVIEW_WIDTH and img_y < PREVIEW_Y + PREVIEW_HEIGHT and \
               img_x + scaled_w > PREVIEW_X and img_y + scaled_h > PREVIEW_Y:
                scaled_img = pygame.transform.smoothscale(self.loaded_image, (scaled_w, scaled_h))
                self.screen.blit(scaled_img, (img_x, img_y))

            # Draw camera rects
            slide = self._get_current_slide()
            if slide:
                cam_a = slide.get('camera_a')
                cam_b = slide.get('camera_b')
                if cam_a:
                    self._draw_camera_rect(cam_a, BLUE, 'A', self.selected_rect == 'a')
                if cam_b:
                    self._draw_camera_rect(cam_b, RED, 'B', self.selected_rect == 'b')
        else:
            # No image loaded -- show help text
            help_text = self.font.render("No image loaded. Click 'Load Image' in the right panel.", True, LIGHT_GRAY)
            self.screen.blit(help_text, (
                PREVIEW_X + (PREVIEW_WIDTH - help_text.get_width()) // 2,
                PREVIEW_Y + PREVIEW_HEIGHT // 2
            ))

        # Camera info overlay (top-left of preview)
        zoom_text = self.font_small.render(f"Zoom: {self.camera_zoom:.2f}x", True, WHITE)
        info_bg = pygame.Surface((zoom_text.get_width() + 10, zoom_text.get_height() + 6), pygame.SRCALPHA)
        info_bg.fill((0, 0, 0, 140))
        self.screen.blit(info_bg, (PREVIEW_X + 5, PREVIEW_Y + 5))
        self.screen.blit(zoom_text, (PREVIEW_X + 10, PREVIEW_Y + 8))

        # Reset clip
        self.screen.set_clip(None)

    def _draw_camera_rect(self, cam_rect, color, label, is_selected):
        """Draw a camera viewport rectangle on the preview."""
        corners = self._get_rect_screen_corners(cam_rect)
        int_corners = [(int(c[0]), int(c[1])) for c in corners]

        # Draw filled semi-transparent overlay
        if is_selected:
            overlay = pygame.Surface((PREVIEW_WIDTH, PREVIEW_HEIGHT), pygame.SRCALPHA)
            pygame.draw.polygon(overlay, (*color, 30), [(c[0] - PREVIEW_X, c[1] - PREVIEW_Y) for c in int_corners])
            self.screen.blit(overlay, (PREVIEW_X, PREVIEW_Y))

        # Draw outline
        line_width = 3 if is_selected else 2
        pygame.draw.lines(self.screen, color, True, int_corners, line_width)

        # Draw corner handles
        for cx, cy in int_corners:
            handle_rect = pygame.Rect(cx - HANDLE_SIZE // 2, cy - HANDLE_SIZE // 2, HANDLE_SIZE, HANDLE_SIZE)
            pygame.draw.rect(self.screen, color, handle_rect)
            pygame.draw.rect(self.screen, WHITE, handle_rect, 1)

        # Draw label at top-left
        lbl_surf = self.font_bold.render(label, True, color)
        lbl_x = int_corners[0][0] + 6
        lbl_y = int_corners[0][1] + 6
        # Label background
        lbl_bg = pygame.Surface((lbl_surf.get_width() + 8, lbl_surf.get_height() + 4), pygame.SRCALPHA)
        lbl_bg.fill((0, 0, 0, 180))
        self.screen.blit(lbl_bg, (lbl_x - 4, lbl_y - 2))
        self.screen.blit(lbl_surf, (lbl_x, lbl_y))

        # Draw rotation indicator if non-zero
        rotation = cam_rect.get('rotation', 0)
        if abs(rotation) > 0.01:
            rot_text = self.font_small.render(f"{rotation:.1f}°", True, color)
            rot_x = int_corners[1][0] - rot_text.get_width() - 6
            rot_y = int_corners[1][1] + 6
            self.screen.blit(rot_text, (rot_x, rot_y))

    def draw_right_panel(self):
        """Draw the right-side properties panel with fixed action buttons at bottom."""
        panel_x = WINDOW_WIDTH - UI_PANEL_WIDTH
        panel_bottom = WINDOW_HEIGHT - STATUS_BAR_HEIGHT
        panel_rect = pygame.Rect(panel_x, TOP_BAR_HEIGHT, UI_PANEL_WIDTH, panel_bottom - TOP_BAR_HEIGHT)

        # Background
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)
        pygame.draw.line(self.screen, MED_GRAY, (panel_x, TOP_BAR_HEIGHT), (panel_x, panel_bottom))

        slide = self._get_current_slide()
        x = panel_x + 10
        field_w = UI_PANEL_WIDTH - 20

        # Action buttons always pinned at the bottom of the panel
        btn_area_height = self._draw_action_buttons(x, panel_bottom, field_w)
        # Properties area extends from top bar to the button area
        props_bottom = panel_bottom - btn_area_height - 6

        # Clip properties area so fields don't overlap buttons
        props_clip = pygame.Rect(panel_x, TOP_BAR_HEIGHT, UI_PANEL_WIDTH, props_bottom - TOP_BAR_HEIGHT)
        self.screen.set_clip(props_clip)

        y = TOP_BAR_HEIGHT + 10

        # Title
        title = self.font_title.render("Slide Properties", True, BRASS_COLOR)
        self.screen.blit(title, (x, y))
        y += title.get_height() + 8

        if not slide:
            no_slide = self.font.render("No slides. Click '+' to add.", True, LIGHT_GRAY)
            self.screen.blit(no_slide, (x, y))
            self.screen.set_clip(None)
            return

        # Image path (inline)
        img_path = slide.get('image', '') or '(none)'
        img_display = os.path.basename(img_path) if img_path != '(none)' else img_path
        self._draw_label(x, y, f"Image: {img_display}")
        y += 16

        # Separator
        y = self._draw_separator(x, y, field_w)

        # Camera A properties (compact)
        self._draw_label(x, y, "Camera A:", BLUE)
        y += 16
        cam_a = slide.get('camera_a', {})
        y = self._draw_rect_fields(x, y, field_w, cam_a, 'a')

        # Camera B properties (compact)
        self._draw_label(x, y, "Camera B:", RED)
        y += 16
        cam_b = slide.get('camera_b', {})
        y = self._draw_rect_fields(x, y, field_w, cam_b, 'b')

        # Separator
        y = self._draw_separator(x, y, field_w)

        # Pan duration + Crossfade on same row using inline fields
        half = (field_w - 6) // 2
        y = self._draw_inline_field(x, y, half, "Pan:", 'pan_duration',
                                     f"{slide.get('pan_duration', 5.0):.1f}")
        # Crossfade on same line (draw at offset)
        self._draw_inline_field_at(x + half + 6, y - 20, half, "Fade:", 'crossfade_duration',
                                    f"{slide.get('crossfade_duration', 1.0):.1f}")

        # Easing (inline)
        self._draw_label(x, y, "Easing:")
        easing = slide.get('easing', 'ease_in_out')
        easing_rect = pygame.Rect(x + 65, y - 2, field_w - 65, 18)
        color = HIGHLIGHT if easing_rect.collidepoint(pygame.mouse.get_pos()) else MED_GRAY
        pygame.draw.rect(self.screen, color, easing_rect, border_radius=3)
        easing_text = self.font_small.render(easing, True, WHITE)
        self.screen.blit(easing_text, (easing_rect.x + 4, easing_rect.y + 2))
        self.easing_btn_rect = easing_rect
        y += 20

        # Separator
        y = self._draw_separator(x, y, field_w)

        # Voiceover: file + volume/delay on one compact group
        audio_path = slide.get('audio', '') or '(none)'
        audio_display = os.path.basename(audio_path) if audio_path != '(none)' else audio_path
        self._draw_label(x, y, f"Voice: {audio_display}")
        y += 16
        # Volume and delay side-by-side
        y = self._draw_inline_field(x, y, half, "Vol:", 'audio_volume',
                                     f"{slide.get('audio_volume', 1.0):.2f}")
        self._draw_inline_field_at(x + half + 6, y - 20, half, "Dly:", 'audio_start_delay',
                                    f"{slide.get('audio_start_delay', 0.0):.1f}")

        # Music: file + volume/delay on one compact group
        music_path = slide.get('music', '') or '(none)'
        music_display = os.path.basename(music_path) if music_path != '(none)' else music_path
        self._draw_label(x, y, f"Music: {music_display}")
        y += 16
        # Volume and delay side-by-side
        y = self._draw_inline_field(x, y, half, "Vol:", 'music_volume',
                                     f"{slide.get('music_volume', 0.4):.2f}")
        self._draw_inline_field_at(x + half + 6, y - 20, half, "Dly:", 'music_start_delay',
                                    f"{slide.get('music_start_delay', 0.0):.1f}")

        # Separator
        y = self._draw_separator(x, y, field_w)

        # Subtitle (multi-line with word wrapping)
        y = self._draw_subtitle_field(x, y, field_w, 'subtitle', slide.get('subtitle', ''))

        # Reset clip
        self.screen.set_clip(None)

    def _draw_label(self, x, y, text, color=LIGHT_GRAY):
        """Draw a small label."""
        surf = self.font_small.render(text, True, color)
        self.screen.blit(surf, (x, y))

    def _draw_separator(self, x, y, w):
        """Draw a horizontal separator line."""
        y += 2
        pygame.draw.line(self.screen, MED_GRAY, (x, y), (x + w, y))
        return y + 4

    def _draw_rect_fields(self, x, y, field_w, cam_rect, rect_id):
        """Draw the numeric fields for a camera rect (x, y, w, h, rot) in a compact 2-column layout."""
        half_w = (field_w - 6) // 2
        row_h = 19
        # Row 1: X / Y    Row 2: W / H    Row 3: Rot (full width)
        rows = [
            [('x', f"{cam_rect.get('x', 0):.0f}", 'X:'),
             ('y', f"{cam_rect.get('y', 0):.0f}", 'Y:')],
            [('width', f"{cam_rect.get('width', 800):.0f}", 'W:'),
             ('height', f"{cam_rect.get('height', 450):.0f}", 'H:')],
            [('rotation', f"{cam_rect.get('rotation', 0):.1f}", 'Rot:')],
        ]

        for row in rows:
            for col_idx, (prop, value, lbl_text) in enumerate(row):
                field_name = f"cam_{rect_id}_{prop}"
                is_full = len(row) == 1  # Full-width field (rotation)

                col_x = x + col_idx * (half_w + 6)
                lbl_surf = self.font_small.render(lbl_text, True, LIGHT_GRAY)
                self.screen.blit(lbl_surf, (col_x, y))

                input_x = col_x + lbl_surf.get_width() + 3
                input_w = (field_w - lbl_surf.get_width() - 3) if is_full else (half_w - lbl_surf.get_width() - 3)
                input_rect = pygame.Rect(input_x, y - 1, input_w, row_h - 2)
                self.field_rects[field_name] = input_rect

                is_active = self.active_field == field_name
                bg_color = (70, 80, 100) if is_active else (60, 60, 65)
                pygame.draw.rect(self.screen, bg_color, input_rect, border_radius=3)
                if is_active:
                    pygame.draw.rect(self.screen, HIGHLIGHT, input_rect, 1, border_radius=3)

                display_text = self.field_text if is_active else value
                val_surf = self.font_small.render(display_text, True, WHITE)
                # Temporarily save and set clip for this input box only
                prev_clip = self.screen.get_clip()
                self.screen.set_clip(input_rect)
                self.screen.blit(val_surf, (input_x + 3, y))
                self.screen.set_clip(prev_clip)

                if is_active and pygame.time.get_ticks() % 1000 < 500:
                    cx = input_x + 3 + self.font_small.size(self.field_text[:self.field_cursor])[0]
                    pygame.draw.line(self.screen, WHITE, (cx, y + 1), (cx, y + row_h - 4))

            y += row_h

        return y

    def _draw_editable_field(self, x, y, field_w, label, field_name, value, wide=False):
        """Draw a labeled editable field. Returns new y position."""
        self._draw_label(x, y, label)
        y += 16

        input_rect = pygame.Rect(x, y, field_w, 20 if not wide else 36)
        self.field_rects[field_name] = input_rect

        is_active = self.active_field == field_name
        bg_color = (70, 80, 100) if is_active else (60, 60, 65)
        pygame.draw.rect(self.screen, bg_color, input_rect, border_radius=3)
        if is_active:
            pygame.draw.rect(self.screen, HIGHLIGHT, input_rect, 1, border_radius=3)

        display_text = self.field_text if is_active else value
        val_surf = self.font_small.render(display_text, True, WHITE)
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(input_rect)
        self.screen.blit(val_surf, (x + 4, y + 2))
        self.screen.set_clip(prev_clip)

        if is_active and pygame.time.get_ticks() % 1000 < 500:
            cursor_x = x + 4 + self.font_small.size(self.field_text[:self.field_cursor])[0]
            pygame.draw.line(self.screen, WHITE, (cursor_x, y + 2), (cursor_x, y + 16))

        return y + input_rect.height + 4

    def _draw_subtitle_field(self, x, y, field_w, field_name, value):
        """Draw a multi-line subtitle text field with word wrapping."""
        self._draw_label(x, y, "Subtitle:")
        y += 16

        is_active = self.active_field == field_name
        display_text = self.field_text if is_active else value

        # Word-wrap the text to fit within the field (with padding)
        wrapped = self._wrap_text_for_field(display_text, field_w - 10)
        line_h = 16
        num_lines = max(2, len(wrapped))  # Minimum 2 visible lines
        field_h = num_lines * line_h + 8  # 8px vertical padding

        input_rect = pygame.Rect(x, y, field_w, field_h)
        self.field_rects[field_name] = input_rect

        bg_color = (70, 80, 100) if is_active else (60, 60, 65)
        pygame.draw.rect(self.screen, bg_color, input_rect, border_radius=3)
        if is_active:
            pygame.draw.rect(self.screen, HIGHLIGHT, input_rect, 1, border_radius=3)

        # Render each wrapped line
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(input_rect)
        text_y = y + 4
        for line_text, _start_idx in wrapped:
            line_surf = self.font_small.render(line_text, True, WHITE)
            self.screen.blit(line_surf, (x + 5, text_y))
            text_y += line_h
        self.screen.set_clip(prev_clip)

        # Cursor rendering when active
        if is_active and pygame.time.get_ticks() % 1000 < 500:
            line_idx, x_offset = self._get_cursor_in_wrapped(wrapped, self.field_cursor)
            cx = x + 5 + x_offset
            cy = y + 4 + line_idx * line_h
            pygame.draw.line(self.screen, WHITE, (cx, cy), (cx, cy + line_h - 2))

        return y + field_h + 4

    def _wrap_text_for_field(self, text, max_width):
        """Word-wrap text to fit within max_width pixels. Returns list of (line_text, start_char_idx)."""
        if not text:
            return [('', 0)]

        words = text.split(' ')
        lines = []
        current_line_words = []
        line_start_char = 0

        for word in words:
            test_line = ' '.join(current_line_words + [word])
            if self.font_small.size(test_line)[0] <= max_width or not current_line_words:
                current_line_words.append(word)
            else:
                line_text = ' '.join(current_line_words)
                lines.append((line_text, line_start_char))
                line_start_char += len(line_text) + 1  # +1 for the space separator
                current_line_words = [word]

        if current_line_words:
            lines.append((' '.join(current_line_words), line_start_char))

        return lines if lines else [('', 0)]

    def _get_cursor_in_wrapped(self, wrapped_lines, cursor_pos):
        """Find which wrapped line the cursor falls on and its x-pixel offset."""
        for i, (line_text, start_idx) in enumerate(wrapped_lines):
            end_idx = start_idx + len(line_text)
            if cursor_pos <= end_idx or i == len(wrapped_lines) - 1:
                local_pos = max(0, min(cursor_pos - start_idx, len(line_text)))
                x_offset = self.font_small.size(line_text[:local_pos])[0]
                return i, x_offset
        return 0, 0

    def _draw_inline_field(self, x, y, w, label, field_name, value):
        """Draw a compact label+input on one line. Returns new y."""
        return self._draw_inline_field_at(x, y, w, label, field_name, value)

    def _draw_inline_field_at(self, x, y, w, label, field_name, value):
        """Draw a compact label+input at a specific position. Returns new y (y + row height)."""
        row_h = 20
        lbl_surf = self.font_small.render(label, True, LIGHT_GRAY)
        self.screen.blit(lbl_surf, (x, y))

        input_x = x + lbl_surf.get_width() + 3
        input_w = w - lbl_surf.get_width() - 3
        input_rect = pygame.Rect(input_x, y - 1, input_w, row_h - 2)
        self.field_rects[field_name] = input_rect

        is_active = self.active_field == field_name
        bg_color = (70, 80, 100) if is_active else (60, 60, 65)
        pygame.draw.rect(self.screen, bg_color, input_rect, border_radius=3)
        if is_active:
            pygame.draw.rect(self.screen, HIGHLIGHT, input_rect, 1, border_radius=3)

        display_text = self.field_text if is_active else value
        val_surf = self.font_small.render(display_text, True, WHITE)
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(input_rect)
        self.screen.blit(val_surf, (input_x + 3, y))
        self.screen.set_clip(prev_clip)

        if is_active and pygame.time.get_ticks() % 1000 < 500:
            cx = input_x + 3 + self.font_small.size(self.field_text[:self.field_cursor])[0]
            pygame.draw.line(self.screen, WHITE, (cx, y + 1), (cx, y + row_h - 4))

        return y + row_h

    def _draw_action_buttons(self, x, panel_bottom, field_w):
        """
        Draw action buttons pinned to the bottom of the panel.
        Draws upward from panel_bottom. Returns total height used by the button area.
        """
        btn_h = 28
        btn_gap = 4

        buttons = [
            ('save', 'Save (Ctrl+S)', BRASS_COLOR),
            ('export', 'Export MP4', GREEN),
            ('preview', 'Preview (P)', YELLOW),
            ('load_music', 'Load Music', BLUE),
            ('load_audio', 'Load Voice', BLUE),
            ('load_image', 'Load Image', GREEN),
        ]

        # Draw from bottom to top
        y = panel_bottom - btn_h - 4  # 4px margin from bottom
        for key, label, color in buttons:
            btn_rect = pygame.Rect(x, y, field_w, btn_h)
            self.action_btn_rects[key] = btn_rect

            is_hovered = btn_rect.collidepoint(pygame.mouse.get_pos())
            bg_color = (80, 85, 90) if is_hovered else (60, 60, 65)
            pygame.draw.rect(self.screen, bg_color, btn_rect, border_radius=5)
            pygame.draw.rect(self.screen, color, btn_rect, 1, border_radius=5)

            lbl = self.font.render(label, True, color)
            self.screen.blit(lbl, (x + (field_w - lbl.get_width()) // 2, y + (btn_h - lbl.get_height()) // 2))

            y -= btn_h + btn_gap

        # Return total height consumed by the button area
        total_height = len(buttons) * (btn_h + btn_gap) + 4
        return total_height

    def draw_status_bar(self):
        """Draw the status bar at the bottom."""
        bar_y = WINDOW_HEIGHT - STATUS_BAR_HEIGHT
        pygame.draw.rect(self.screen, DARK_GRAY, (0, bar_y, WINDOW_WIDTH, STATUS_BAR_HEIGHT))
        pygame.draw.line(self.screen, MED_GRAY, (0, bar_y), (WINDOW_WIDTH, bar_y))

        # Left: current cutscene and slide info
        info = f"{self.current_cutscene_id} | Slide {self.current_slide_idx + 1}/{max(1, len(self._get_slides()))}"
        if self.selected_rect:
            info += f" | Selected: Camera {self.selected_rect.upper()}"
        info_surf = self.font_small.render(info, True, LIGHT_GRAY)
        self.screen.blit(info_surf, (10, bar_y + (STATUS_BAR_HEIGHT - info_surf.get_height()) // 2))

        # Right: status message
        if self.status_message and self.status_timer > 0:
            msg_surf = self.font_small.render(self.status_message, True, GREEN)
            self.screen.blit(msg_surf, (WINDOW_WIDTH - msg_surf.get_width() - 10,
                                        bar_y + (STATUS_BAR_HEIGHT - msg_surf.get_height()) // 2))

    # ========================================================================
    # MAIN LOOP
    # ========================================================================

    def run(self):
        """Main event loop."""
        # Enable key repeat for text input
        pygame.key.set_repeat(400, 30)

        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0

            # Update status timer
            if self.status_timer > 0:
                self.status_timer -= dt

            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.save_data()
                    running = False

                # Export modal intercepts all input when active
                elif self._export_modal_active:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self._export_modal_active = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_export_modal_click(event.pos)
                    continue

                elif event.type == pygame.KEYDOWN:
                    # Text field input takes priority
                    if self._handle_field_keydown(event):
                        continue

                    mods = pygame.key.get_mods()
                    if event.key == pygame.K_ESCAPE:
                        self.save_data()
                        running = False
                    elif event.key == pygame.K_s and (mods & pygame.KMOD_CTRL):
                        self.save_data()
                    elif event.key == pygame.K_s and not (mods & pygame.KMOD_CTRL):
                        self.save_data()
                    elif event.key == pygame.K_p:
                        self._preview_cutscene()
                    elif event.key == pygame.K_DELETE:
                        # Deselect rect
                        self.selected_rect = None

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_pos = event.pos

                    if event.button == 1:  # Left click
                        handled = False

                        # Check top bar cutscene buttons
                        for btn_rect, idx in self.cutscene_btn_rects:
                            if btn_rect.collidepoint(mouse_pos):
                                self._select_cutscene(idx)
                                handled = True
                                break

                        # Check slide navigation buttons
                        if not handled:
                            for key, rect in self.slide_nav_rects.items():
                                if rect.collidepoint(mouse_pos):
                                    if key == 'prev':
                                        self._nav_slide(-1)
                                    elif key == 'next':
                                        self._nav_slide(1)
                                    elif key == 'add':
                                        self._add_slide()
                                    elif key == 'remove':
                                        self._remove_slide()
                                    handled = True
                                    break

                        # Check action buttons
                        if not handled:
                            for key, rect in self.action_btn_rects.items():
                                if rect.collidepoint(mouse_pos):
                                    if key == 'load_image':
                                        self._load_image_dialog()
                                    elif key == 'load_audio':
                                        self._load_audio_dialog()
                                    elif key == 'load_music':
                                        self._load_music_dialog()
                                    elif key == 'export':
                                        self._open_export_modal()
                                    elif key == 'preview':
                                        self._preview_cutscene()
                                    elif key == 'save':
                                        self.save_data()
                                    handled = True
                                    break

                        # Check easing button
                        if not handled and self.easing_btn_rect and self.easing_btn_rect.collidepoint(mouse_pos):
                            slide = self._get_current_slide()
                            if slide:
                                current = slide.get('easing', 'ease_in_out')
                                idx = EASING_OPTIONS.index(current) if current in EASING_OPTIONS else 0
                                slide['easing'] = EASING_OPTIONS[(idx + 1) % len(EASING_OPTIONS)]
                            handled = True

                        # Check text field clicks
                        if not handled:
                            for field_name, rect in self.field_rects.items():
                                if rect.collidepoint(mouse_pos):
                                    # Get current value for this field
                                    slide = self._get_current_slide()
                                    if slide:
                                        if field_name.startswith('cam_'):
                                            parts = field_name.split('_')
                                            cam_key = f"camera_{parts[1]}"
                                            prop = parts[2]
                                            val = slide.get(cam_key, {}).get(prop, 0)
                                        else:
                                            val = slide.get(field_name, '')
                                        self._start_field_edit(field_name, val)
                                    handled = True
                                    break

                        # Check camera rect interaction (in preview area)
                        if not handled and mouse_pos[0] < PREVIEW_WIDTH and mouse_pos[1] >= TOP_BAR_HEIGHT:
                            if not self._handle_rect_mousedown(mouse_pos):
                                # Click on empty space -- deselect
                                self._commit_field_edit()
                                self.selected_rect = None

                    elif event.button == 3:  # Right click -- deselect
                        self._commit_field_edit()
                        self.selected_rect = None

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        self._handle_rect_mouseup()

                elif event.type == pygame.MOUSEMOTION:
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())
                    if self.dragging_rect or self.dragging_corner is not None:
                        self._handle_rect_mousemotion(event.pos)

                elif event.type == pygame.MOUSEWHEEL:
                    mouse_pos = pygame.mouse.get_pos()
                    # Try rotating selected rect first
                    if self.selected_rect and self._handle_rect_scroll(event.y):
                        pass
                    else:
                        # Otherwise zoom the camera
                        self.handle_camera_zoom(event.y, mouse_pos)

            # Continuous input (arrow keys for camera)
            keys = pygame.key.get_pressed()
            if not self.active_field:  # Don't pan while typing
                self.handle_keyboard_camera(keys)
                self.handle_edge_scrolling(pygame.mouse.get_pos())

            # Render
            self.screen.fill(BLACK)
            self.draw_image_preview()
            self.draw_top_bar()
            self.draw_right_panel()
            self.draw_status_bar()
            # Draw export modal overlay on top of everything when active
            if self._export_modal_active:
                self._draw_export_modal()
            pygame.display.flip()

        pygame.quit()


# ========================================================================
# ENTRY POINT
# ========================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("CUTSCENE EDITOR TOOL")
    print("=" * 60)
    print()
    print("Controls:")
    print("  Middle mouse drag  - Pan the image viewport")
    print("  Mouse wheel        - Zoom in/out (or rotate selected rect)")
    print("  Left click on rect - Select camera rect A (blue) or B (red)")
    print("  Drag rect center   - Move the rect")
    print("  Drag rect corner   - Resize (16:9 locked)")
    print("  Arrow keys         - Pan the viewport")
    print("  P                  - Preview current cutscene")
    print("  Ctrl+S / S         - Save")
    print("  ESC                - Save and quit")
    print()

    tool = CutsceneTool()
    tool.run()
