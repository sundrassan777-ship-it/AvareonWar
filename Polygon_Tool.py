# -*- coding: utf-8 -*-
# polygon_tool.py
# Interactive tool for defining territory polygons

"""
WINDOW SIZE CONFIGURATION:
This tool should use the same window size as your main game.
Adjust WINDOW_WIDTH and WINDOW_HEIGHT below to match your main.py settings.
"""

import pygame
import json
import sys
import os

# Multi-map support: --map <map_id> CLI argument selects which map to edit (default: avareon)
_tool_map_id = 'avareon'
for i, arg in enumerate(sys.argv):
    if arg == '--map' and i + 1 < len(sys.argv):
        _tool_map_id = sys.argv[i + 1]
_tool_map_dir = f'maps/{_tool_map_id}'

# Initialize Pygame
pygame.init()

# Constants - ADJUST THESE TO MATCH YOUR MAIN.PY
WINDOW_WIDTH = 1600  # Should match main.py
WINDOW_HEIGHT = 850  # Should match main.py
MAP_WIDTH = 4096  # Original map width (updated 2026-01-24 for high-res map)
MAP_HEIGHT = 3072  # Original map height (updated 2026-01-24 for high-res map)
UI_PANEL_WIDTH = 300  # Fixed width for UI panel on right side
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
CYAN = (0, 255, 255)

def _load_territory_list(map_dir):
    """Load territory name list from maps/<map_id>/territories.json.
    Returns empty list if file not found."""
    path = os.path.join(map_dir, 'territories.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

class PolygonTool:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Territory Polygon Definition Tool - Camera: Drag/Scroll/Arrows/Wheel")
        self.clock = pygame.time.Clock()

        # Multi-map state
        self.current_map_id = _tool_map_id
        self.current_map_dir = _tool_map_dir
        self.territories = _load_territory_list(self.current_map_dir)

        # Load the map image
        self._load_map_image()

        # Camera system (same as main game!)
        self.camera_offset = [0.0, 0.0]  # [x, y] in world coordinates
        self.camera_zoom = 1.5            # Start at reasonable zoom
        self.camera_drag_start = None     # For middle-mouse drag
        
        # Camera configuration
        self.camera_min_zoom = 1.0        # Can zoom out to see whole map
        self.camera_max_zoom = 6.0        # Can zoom in very close for precise polygon drawing!
        self.edge_scroll_speed = 5
        self.edge_scroll_margin = 20
        self.keyboard_scroll_speed = 10
        
        # Map scaling cache (for performance)
        self.cached_scaled_map = None
        self.cached_zoom_level = None
        
        # State
        self.current_territory_index = 0
        self.current_points = []  # Points for current polygon (in WORLD coordinates!)
        self.completed_polygons = {}  # territory_name -> list of points
        
        # Mouse state for toggle drawing (click to start, click to stop)
        self.drawing_active = False
        self.last_point_pos = None  # In WORLD coordinates!
        self.min_point_distance = 2.3  # Minimum pixels between auto-generated points
        
        # Try to load existing progress
        self.load_progress()
        
        # Fonts
        self.font = pygame.font.Font(None, 24)
        self.large_font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 20)
    
    def _load_map_image(self):
        """Load (or reload) the map background image for the current map."""
        map_png = os.path.join(self.current_map_dir, 'map.png')
        if not os.path.exists(map_png):
            map_png = "assets/map.png"  # Fallback for avareon
        try:
            self.map_image_original = pygame.image.load(map_png)
            if self.map_image_original.get_width() != MAP_WIDTH or self.map_image_original.get_height() != MAP_HEIGHT:
                self.map_image = pygame.transform.scale(self.map_image_original, (MAP_WIDTH, MAP_HEIGHT))
            else:
                self.map_image = self.map_image_original.copy()
        except pygame.error as e:
            print(f"Error loading map image: {e}")
            self.map_image_original = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
            self.map_image_original.fill((0, 0, 0))
            self.map_image = self.map_image_original.copy()
        # Invalidate scaled map cache
        self.cached_scaled_map = None
        self.cached_zoom_level = None

    def _switch_map(self):
        """Cycle to the next map in the manifest and reload all data."""
        import map_data as _md
        map_ids = _md.get_map_ids()
        if len(map_ids) <= 1:
            return
        current_idx = map_ids.index(self.current_map_id) if self.current_map_id in map_ids else 0
        new_idx = (current_idx + 1) % len(map_ids)
        # Save current work BEFORE switching directories
        self.save_progress()
        self.current_map_id = map_ids[new_idx]
        self.current_map_dir = f'maps/{self.current_map_id}'
        print(f"Switched to map: {self.current_map_id}")
        self._load_map_image()
        self.territories = _load_territory_list(self.current_map_dir)
        self.current_territory_index = 0
        self.current_points = []
        self.last_point_pos = None
        self.drawing_active = False
        self.load_progress()

    def load_progress(self):
        """Load previously saved polygons if they exist (UTF-8 safe)"""
        # Clear existing data first (ensures maps don't bleed into each other)
        self.completed_polygons = {}
        poly_path = os.path.join(self.current_map_dir, 'territory_polygons.json')
        try:
            with open(poly_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.completed_polygons = data
                print(f"Loaded {len(self.completed_polygons)} existing polygons")

                # Skip to first incomplete territory
                for i, territory in enumerate(self.territories):
                    if territory not in self.completed_polygons:
                        self.current_territory_index = i
                        break
                else:
                    # All complete
                    self.current_territory_index = len(self.territories) - 1
        except FileNotFoundError:
            print("No existing progress found, starting fresh")
    
    def save_progress(self):
        """Save all completed polygons to JSON file (UTF-8 safe)"""
        poly_path = os.path.join(self.current_map_dir, 'territory_polygons.json')
        with open(poly_path, 'w', encoding='utf-8') as f:
            json.dump(self.completed_polygons, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.completed_polygons)} polygons")
    
    # ========================================
    # CAMERA TRANSFORMATION METHODS
    # ========================================
    
    def screen_to_world(self, screen_pos):
        """Convert screen coordinates to world coordinates (accounting for camera)"""
        screen_x, screen_y = screen_pos
        world_x = (screen_x / self.camera_zoom) + self.camera_offset[0]
        world_y = (screen_y / self.camera_zoom) + self.camera_offset[1]
        return (world_x, world_y)
    
    def world_to_screen(self, world_pos):
        """Convert world coordinates to screen coordinates (accounting for camera)"""
        world_x, world_y = world_pos
        screen_x = (world_x - self.camera_offset[0]) * self.camera_zoom
        screen_y = (world_y - self.camera_offset[1]) * self.camera_zoom
        return (screen_x, screen_y)
    
    def clamp_camera_to_bounds(self):
        """Prevent camera from scrolling off the map"""
        visible_width = WINDOW_WIDTH / self.camera_zoom
        visible_height = WINDOW_HEIGHT / self.camera_zoom
        
        max_offset_x = max(0, MAP_WIDTH - visible_width)
        max_offset_y = max(0, MAP_HEIGHT - visible_height)
        
        self.camera_offset[0] = max(0, min(self.camera_offset[0], max_offset_x))
        self.camera_offset[1] = max(0, min(self.camera_offset[1], max_offset_y))
    
    # ========================================
    # CAMERA CONTROL METHODS
    # ========================================
    
    def handle_camera_drag(self, pos, buttons):
        """Handle middle-mouse camera dragging"""
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
        """Handle edge scrolling"""
        x, y = pos
        scroll_x = 0
        scroll_y = 0
        
        # Dynamic speed based on zoom
        base_speed = 10.0 * (self.camera_zoom / self.camera_min_zoom)
        
        # Horizontal edges
        if x < self.edge_scroll_margin:
            distance_from_edge = self.edge_scroll_margin - x
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_x = -base_speed * speed_multiplier
        elif x > WINDOW_WIDTH - self.edge_scroll_margin:
            distance_from_edge = x - (WINDOW_WIDTH - self.edge_scroll_margin)
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_x = base_speed * speed_multiplier
        
        # Vertical edges
        if y < self.edge_scroll_margin:
            distance_from_edge = self.edge_scroll_margin - y
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_y = -base_speed * speed_multiplier
        elif y > WINDOW_HEIGHT - self.edge_scroll_margin:
            distance_from_edge = y - (WINDOW_HEIGHT - self.edge_scroll_margin)
            speed_multiplier = distance_from_edge / self.edge_scroll_margin
            scroll_y = base_speed * speed_multiplier
        
        if scroll_x != 0 or scroll_y != 0:
            self.camera_offset[0] += scroll_x / self.camera_zoom
            self.camera_offset[1] += scroll_y / self.camera_zoom
            self.clamp_camera_to_bounds()
    
    def handle_keyboard_camera(self, keys):
        """Handle keyboard camera panning (arrow keys)"""
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
    
    def handle_camera_zoom(self, delta):
        """Handle camera zoom with mouse wheel"""
        mouse_pos = pygame.mouse.get_pos()
        world_pos_before = self.screen_to_world(mouse_pos)
        
        zoom_factor = 1.1 if delta > 0 else 0.9
        new_zoom = self.camera_zoom * zoom_factor
        new_zoom = max(self.camera_min_zoom, min(self.camera_max_zoom, new_zoom))
        
        if new_zoom != self.camera_zoom:
            self.camera_zoom = new_zoom
            
            world_pos_after = self.screen_to_world(mouse_pos)
            self.camera_offset[0] += world_pos_before[0] - world_pos_after[0]
            self.camera_offset[1] += world_pos_before[1] - world_pos_after[1]
            
            self.clamp_camera_to_bounds()
    
    def get_current_territory(self):
        """Get the name of the current territory being defined"""
        if self.current_territory_index < len(self.territories):
            return self.territories[self.current_territory_index]
        return None
    
    def load_existing_polygon(self):
        """Load existing polygon for current territory into editing mode"""
        territory = self.get_current_territory()
        if territory and territory in self.completed_polygons:
            self.current_points = self.completed_polygons[territory].copy()
            if self.current_points:
                self.last_point_pos = self.current_points[-1]
            print(f"Loaded existing polygon for {territory} ({len(self.current_points)} points) - ready to edit!")
            return True
        return False
    
    def is_current_territory_complete(self):
        """Check if current territory already has a saved polygon"""
        territory = self.get_current_territory()
        return territory in self.completed_polygons if territory else False
    
    def complete_current_polygon(self):
        """
        Save the current polygon and move to next territory.
        
        If polygon has 3+ points: Save it
        If polygon has 0 points: Delete existing polygon (allows E > R > ENTER to delete)
        If polygon has 1-2 points: Do nothing (invalid polygon)
        """
        territory = self.get_current_territory()
        if not territory:
            return
        
        if len(self.current_points) >= 3:
            # Valid polygon - save it
            self.completed_polygons[territory] = self.current_points.copy()
            self.save_progress()
            print(f"Completed {territory} with {len(self.current_points)} points")

            self.current_points = []
            self.last_point_pos = None
            self.drawing_active = False  # Turn off drawing mode
            self.current_territory_index += 1

        elif len(self.current_points) == 0:
            # Empty polygon - delete if exists
            if territory in self.completed_polygons:
                del self.completed_polygons[territory]
                self.save_progress()
                print(f"Deleted polygon for {territory}")
            else:
                print(f"No polygon to delete for {territory}")

            self.current_points = []
            self.last_point_pos = None
            self.drawing_active = False  # Turn off drawing mode
            self.current_territory_index += 1
            
        else:
            # 1-2 points - invalid, do nothing
            print(f"Invalid polygon - need at least 3 points (have {len(self.current_points)})")
    
    def undo_last_point(self):
        """Remove the last clicked point"""
        if self.current_points:
            self.current_points.pop()
            # Update last_point_pos
            if self.current_points:
                self.last_point_pos = self.current_points[-1]
            else:
                self.last_point_pos = None
    
    def reset_current_polygon(self):
        """Clear all points for current territory"""
        self.current_points = []
        self.last_point_pos = None
        self.drawing_active = False  # Turn off drawing mode

    def skip_territory(self):
        """Skip current territory and move to next"""
        self.current_points = []
        self.last_point_pos = None
        self.drawing_active = False  # Turn off drawing mode
        self.current_territory_index += 1
    
    def previous_territory(self):
        """Go back to previous territory"""
        if self.current_territory_index > 0:
            self.current_territory_index -= 1
            territory = self.get_current_territory()
            # Load the polygon if it exists
            if territory in self.completed_polygons:
                self.current_points = self.completed_polygons[territory].copy()
                if self.current_points:
                    self.last_point_pos = self.current_points[-1]
                else:
                    self.last_point_pos = None
            else:
                self.current_points = []
                self.last_point_pos = None
    
    def draw_polygon(self, points, color, thickness=2, filled=False):
        """Draw a polygon from a list of points (world coords transformed to screen)"""
        if len(points) < 2:
            return
        
        # Transform all points from world to screen coordinates!
        screen_points = [self.world_to_screen(p) for p in points]
        screen_points = [(int(x), int(y)) for x, y in screen_points]
        
        if filled and len(screen_points) >= 3:
            # Create a semi-transparent surface for whole screen
            surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            pygame.draw.polygon(surface, color + (80,), screen_points)
            self.screen.blit(surface, (0, 0))
        
        # Draw outline (using screen coordinates)
        pygame.draw.lines(self.screen, color, False, screen_points, thickness)
        
        # Draw line from last point to first (closing line) if more than 2 points
        if len(screen_points) > 2:
            pygame.draw.line(self.screen, color, screen_points[-1], screen_points[0], thickness)
        
        # Draw points as circles (using screen coordinates)
        for point in screen_points:
            pygame.draw.circle(self.screen, color, point, 5)
    
    def draw_completed_polygons(self):
        """Draw all completed polygons with transparency"""
        for territory, points in self.completed_polygons.items():
            # Skip the current territory if we're editing it
            if territory == self.get_current_territory():
                continue
            self.draw_polygon(points, GREEN, thickness=1, filled=True)
    
    def draw_ui(self):
        """Draw UI instructions and current territory info"""
        # Draw camera info at top of screen
        camera_info = f"Camera: {self.camera_zoom:.1f}x zoom | Offset: ({int(self.camera_offset[0])}, {int(self.camera_offset[1])})"
        camera_text = self.small_font.render(camera_info, True, WHITE)
        camera_bg = pygame.Rect(5, 5, camera_text.get_width() + 10, camera_text.get_height() + 6)
        pygame.draw.rect(self.screen, (0, 0, 0, 180), camera_bg)
        self.screen.blit(camera_text, (10, 8))

        # Draw UI background panel on right side of screen (fixed position)
        ui_panel_x = WINDOW_WIDTH - UI_PANEL_WIDTH
        ui_rect = pygame.Rect(ui_panel_x, 0, UI_PANEL_WIDTH, WINDOW_HEIGHT)
        pygame.draw.rect(self.screen, (240, 240, 240), ui_rect)
        pygame.draw.line(self.screen, BLACK, (ui_panel_x, 0), (ui_panel_x, WINDOW_HEIGHT), 2)

        ui_x = ui_panel_x + 15
        ui_y = 10

        # Map selector (M key to cycle)
        import map_data as _md
        map_label = self.small_font.render("Map [M]:", True, (100, 100, 100))
        self.screen.blit(map_label, (ui_x, ui_y))
        map_name = self.font.render(_md.get_map_display_name(self.current_map_id), True, BLUE)
        self.screen.blit(map_name, (ui_x + map_label.get_width() + 6, ui_y))
        ui_y += 28

        # Current territory
        territory = self.get_current_territory()
        if territory:
            # Territory name (can wrap if needed)
            title = self.large_font.render("Current Territory:", True, BLACK)
            self.screen.blit(title, (ui_x, ui_y))
            ui_y += 45
            
            # Draw territory name (might be long)
            name_lines = self.wrap_text(territory, self.large_font, UI_PANEL_WIDTH - 30)
            for line in name_lines:
                name_surface = self.large_font.render(line, True, BLUE)
                self.screen.blit(name_surface, (ui_x, ui_y))
                ui_y += 40
            
            ui_y += 10
            
            progress_text = self.font.render(f"Territory {self.current_territory_index + 1} of {len(self.territories)}", True, BLACK)
            self.screen.blit(progress_text, (ui_x, ui_y))
            ui_y += 30
            
            # Show if territory is already complete
            if self.is_current_territory_complete():
                status_text = self.font.render("Status: COMPLETED", True, GREEN)
                self.screen.blit(status_text, (ui_x, ui_y))
                ui_y += 25
                hint_text = self.small_font.render("(Press E to edit)", True, (100, 100, 100))
                self.screen.blit(hint_text, (ui_x, ui_y))
                ui_y += 30
            else:
                status_text = self.font.render("Status: Not started", True, (150, 150, 150))
                self.screen.blit(status_text, (ui_x, ui_y))
                ui_y += 35
            
            points_text = self.font.render(f"Points: {len(self.current_points)}", True, BLACK)
            self.screen.blit(points_text, (ui_x, ui_y))
            ui_y += 30

            # Drawing mode indicator
            if self.drawing_active:
                draw_status = self.font.render("DRAWING: ON", True, GREEN)
            else:
                draw_status = self.font.render("DRAWING: OFF", True, (150, 150, 150))
            self.screen.blit(draw_status, (ui_x, ui_y))
            ui_y += 30
        else:
            done_text = self.large_font.render("ALL DONE!", True, GREEN)
            self.screen.blit(done_text, (ui_x, ui_y))
            ui_y += 60
        
        # Instructions
        instructions = [
            "=== CAMERA ===",
            "",
            "Middle-Drag - Pan camera",
            "Mouse Wheel - Zoom in/out",
            "Arrow Keys - Pan camera",
            "Edge of screen - Auto-scroll",
            "",
            "=== DRAWING ===",
            "",
            "Left Click - Toggle draw",
            "Move mouse - Auto-add",
            "",
            "=== EDITING ===",
            "",
            "E - Edit existing polygon",
            "D - Delete polygon",
            "BACKSPACE - Undo point",
            "R - Reset polygon",
            "",
            "=== CONTROLS ===",
            "",
            "ENTER - Save polygon",
            "S - Skip territory",
            "TAB - Previous territory",
            "SPACE - Next territory",
            "ESC - Save & Quit",
            "",
            "=== TIP ===",
            "",
            "To replace: Press E,",
            "then R, draw new, ENTER.",
            "To delete: Press D.",
            "Zoom to 6x for detail!"
        ]
        
        for i, line in enumerate(instructions):
            if line.startswith("==="):
                text = self.font.render(line, True, BLACK)
            else:
                text = self.small_font.render(line, True, BLACK)
            self.screen.blit(text, (ui_x, ui_y + i * 24))
        
        # Completed count at bottom
        completed_text = self.font.render(f"Completed: {len(self.completed_polygons)}/{len(self.territories)}", True, GREEN)
        self.screen.blit(completed_text, (ui_x, WINDOW_HEIGHT - 80))
    
    def wrap_text(self, text, font, max_width):
        """Wrap text to fit within max_width"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines if lines else [text]
    
    def add_point_if_far_enough(self, pos):
        """Add a point only if it's far enough from the last point"""
        if not self.current_points:
            self.current_points.append(pos)
            self.last_point_pos = pos
            return True
        
        # Calculate distance from last point
        last_x, last_y = self.last_point_pos
        new_x, new_y = pos
        distance = ((new_x - last_x) ** 2 + (new_y - last_y) ** 2) ** 0.5
        
        if distance >= self.min_point_distance:
            self.current_points.append(pos)
            self.last_point_pos = pos
            return True
        
        return False
    
    def run(self):
        """Main loop with camera controls"""
        running = True
        
        while running:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click - toggle drawing mode
                        # Ignore clicks on UI panel
                        if event.pos[0] >= WINDOW_WIDTH - UI_PANEL_WIDTH:
                            continue
                        # Toggle drawing mode on/off
                        self.drawing_active = not self.drawing_active
                        # If we just started drawing, add the first point
                        if self.drawing_active:
                            world_pos = self.screen_to_world(event.pos)
                            if world_pos[0] < MAP_WIDTH and world_pos[1] < MAP_HEIGHT:
                                self.add_point_if_far_enough(world_pos)
                
                elif event.type == pygame.MOUSEMOTION:
                    # Camera drag
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())

                    # If drawing is active and over map (not UI panel), add points continuously
                    if self.drawing_active and event.pos[0] < WINDOW_WIDTH - UI_PANEL_WIDTH:
                        world_pos = self.screen_to_world(event.pos)
                        if world_pos[0] < MAP_WIDTH and world_pos[1] < MAP_HEIGHT:
                            self.add_point_if_far_enough(world_pos)
                
                elif event.type == pygame.MOUSEWHEEL:
                    # Camera zoom
                    self.handle_camera_zoom(event.y)
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:  # Enter - complete polygon
                        self.complete_current_polygon()
                    
                    elif event.key == pygame.K_BACKSPACE:  # Undo last point
                        self.undo_last_point()
                    
                    elif event.key == pygame.K_r:  # Reset current polygon
                        self.reset_current_polygon()
                    
                    elif event.key == pygame.K_s:  # Skip territory
                        self.skip_territory()
                    
                    elif event.key == pygame.K_TAB:  # Previous territory (changed from LEFT to avoid conflict)
                        self.previous_territory()
                    
                    elif event.key == pygame.K_SPACE:  # Next territory (changed from RIGHT for clarity)
                        if self.current_territory_index < len(self.territories) - 1:
                            self.current_territory_index += 1
                            self.current_points = []
                            self.last_point_pos = None
                    
                    elif event.key == pygame.K_e:  # Edit existing polygon
                        if self.load_existing_polygon():
                            # Successfully loaded - ready to edit
                            pass
                        else:
                            print("No existing polygon to edit for this territory")
                    
                    elif event.key == pygame.K_d:  # Delete existing polygon
                        territory = self.get_current_territory()
                        if territory and territory in self.completed_polygons:
                            del self.completed_polygons[territory]
                            self.save_progress()
                            self.current_points = []
                            self.last_point_pos = None
                            print(f"Deleted polygon for {territory}")
                        else:
                            print("No polygon to delete for this territory")
                    
                    elif event.key == pygame.K_m:  # Cycle to next map
                        self._switch_map()

                    elif event.key == pygame.K_ESCAPE:  # Quit
                        self.save_progress()
                        running = False
            
            # Continuous camera controls (outside event loop)
            keys = pygame.key.get_pressed()
            self.handle_keyboard_camera(keys)
            
            # Edge scrolling
            mouse_pos = pygame.mouse.get_pos()
            self.handle_edge_scrolling(mouse_pos)
            
            # Drawing
            self.screen.fill(WHITE)
            
            # Draw map with camera transformation!
            scaled_map_width = int(MAP_WIDTH * self.camera_zoom)
            scaled_map_height = int(MAP_HEIGHT * self.camera_zoom)
            
            # Cache scaled map for performance
            if self.cached_zoom_level != self.camera_zoom:
                self.cached_scaled_map = pygame.transform.smoothscale(
                    self.map_image_original,
                    (scaled_map_width, scaled_map_height)
                )
                self.cached_zoom_level = self.camera_zoom
            
            map_x = int(-self.camera_offset[0] * self.camera_zoom)
            map_y = int(-self.camera_offset[1] * self.camera_zoom)
            self.screen.blit(self.cached_scaled_map, (map_x, map_y))
            
            # Draw completed polygons (green, semi-transparent)
            self.draw_completed_polygons()
            
            # Draw current polygon (yellow)
            if self.current_points:
                self.draw_polygon(self.current_points, YELLOW, thickness=3, filled=True)
            
            # Draw UI
            self.draw_ui()
            
            # Update display
            pygame.display.flip()
            self.clock.tick(FPS)
        
        # Final save before quitting
        self.save_progress()
        pygame.quit()
        
        print("\n=== Summary ===")
        print(f"Completed {len(self.completed_polygons)}/{len(self.territories)} territories")
        print("Progress saved to 'territory_polygons.json'")
        print("You can run this tool again to continue where you left off!")

if __name__ == "__main__":
    print("=== Territory Polygon Definition Tool ===")
    print("This tool helps you define clickable regions for each territory")
    print("Click around the borders of each territory, then press ENTER")
    print("\nLoading...")
    
    tool = PolygonTool()
    tool.run()