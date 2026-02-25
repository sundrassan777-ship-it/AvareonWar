# -*- coding: utf-8 -*-
# adjacency_tool.py
# Tool for verifying and correcting territory adjacencies

"""
ADJACENCY VERIFICATION TOOL
This tool helps you verify which territories border each other.
Click a territory to see its neighbors highlighted.
Use keyboard to add/remove adjacencies.
"""

import pygame
import json
import sys
import map_data

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 850
MAP_WIDTH = 4096  # Updated 2026-01-24 for high-res map
MAP_HEIGHT = 3072  # Updated 2026-01-24 for high-res map
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
ORANGE = (255, 165, 0)

class AdjacencyTool:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Adjacency Verification Tool")
        self.clock = pygame.time.Clock()
        
        # Load polygons and adjacency data
        map_data.load_polygons()
        if not map_data.TERRITORY_POLYGONS:
            print("ERROR: No territory polygons loaded!")
            sys.exit(1)
        
        # Load the map image - KEEP ORIGINAL HIGH-RES for quality!
        try:
            self.map_image_original = pygame.image.load("assets/map.png")
            if self.map_image_original.get_width() != MAP_WIDTH or self.map_image_original.get_height() != MAP_HEIGHT:
                self.map_image = pygame.transform.scale(self.map_image_original, (MAP_WIDTH, MAP_HEIGHT))
            else:
                self.map_image = self.map_image_original.copy()
        except pygame.error as e:
            print(f"Error loading map: {e}")
            sys.exit(1)

        # Camera system (same as Polygon_Tool!)
        self.camera_offset = [0.0, 0.0]  # [x, y] in world coordinates
        self.camera_zoom = 0.3            # Start zoomed out to see full 4096×3072 map
        self.camera_drag_start = None     # For middle-mouse drag

        # Camera configuration
        self.camera_min_zoom = 0.2        # Can zoom out to see whole 4096×3072 map
        self.camera_max_zoom = 6.0        # Can zoom in very close
        self.edge_scroll_speed = 5
        self.edge_scroll_margin = 20
        self.keyboard_scroll_speed = 10

        # Map scaling cache (for performance)
        self.cached_scaled_map = None
        self.cached_zoom_level = None

        # State
        self.selected_territory = None
        self.hovered_territory = None
        self.adjacencies = map_data.ADJACENCIES.copy()  # Working copy we can modify

        # Fonts
        self.font = pygame.font.Font(None, 20)
        self.large_font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 18)

        # Mode: 'view' or 'add'
        self.mode = 'view'
        self.pending_addition = None  # Territory to add as neighbor
    
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

    def get_territory_at_pos(self, pos):
        """Find which territory contains the given position"""
        # Convert screen position to world position!
        world_pos = self.screen_to_world(pos)
        for territory in reversed(list(map_data.TERRITORY_POLYGONS.keys())):
            polygon = map_data.TERRITORY_POLYGONS[territory]
            if map_data.point_in_polygon(world_pos, polygon):
                return territory
        return None
    
    def is_adjacent(self, territory1, territory2):
        """Check if two territories are marked as adjacent"""
        return territory2 in self.adjacencies.get(territory1, [])
    
    def toggle_adjacency(self, territory1, territory2):
        """Add or remove adjacency between two territories (bidirectional)"""
        # Add/remove territory2 from territory1's neighbors
        if territory1 in self.adjacencies:
            if territory2 in self.adjacencies[territory1]:
                self.adjacencies[territory1].remove(territory2)
                print(f"Removed: {territory1} -x- {territory2}")
            else:
                self.adjacencies[territory1].append(territory2)
                print(f"Added: {territory1} <-> {territory2}")
        else:
            self.adjacencies[territory1] = [territory2]
            print(f"Added: {territory1} <-> {territory2}")
        
        # Add/remove territory1 from territory2's neighbors (bidirectional)
        if territory2 in self.adjacencies:
            if territory1 in self.adjacencies[territory2]:
                self.adjacencies[territory2].remove(territory1)
            else:
                self.adjacencies[territory2].append(territory1)
        else:
            self.adjacencies[territory2] = [territory1]
    
    def save_adjacencies(self):
        """Save the modified adjacency data back to map_data.py"""
        try:
            # Read the current map_data.py file with UTF-8 encoding
            with open('map_data.py', 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find the ADJACENCIES dictionary and replace it
            import_start = content.find('ADJACENCIES = {')
            if import_start == -1:
                print("ERROR: Could not find ADJACENCIES dictionary in map_data.py")
                return False
            
            # Find the end of the dictionary
            brace_count = 0
            i = import_start + len('ADJACENCIES = ')
            start_i = i
            while i < len(content):
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        break
                i += 1
            
            if brace_count != 0:
                print("ERROR: Could not parse ADJACENCIES dictionary")
                return False
            
            # Build new adjacency string
            new_adjacencies = "ADJACENCIES = {\n"
            for territory in sorted(self.adjacencies.keys()):
                neighbors = sorted(self.adjacencies[territory])
                neighbors_str = ', '.join(f'"{n}"' for n in neighbors)
                new_adjacencies += f'    "{territory}": [{neighbors_str}],\n'
            new_adjacencies += "}"
            
            # Replace in content
            new_content = content[:import_start] + new_adjacencies + content[i+1:]
            
            # Write back with UTF-8 encoding
            with open('map_data.py', 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print("\n✅ Adjacencies saved to map_data.py!")
            return True
            
        except Exception as e:
            print(f"ERROR saving adjacencies: {e}")
            return False
    
    def draw_territory_overlay(self, territory, color, alpha=100, outline=False):
        """Draw a colored overlay on a territory (with camera transformations)"""
        if territory not in map_data.TERRITORY_POLYGONS:
            return

        polygon = map_data.TERRITORY_POLYGONS[territory]

        # Transform polygon points from world to screen coordinates
        screen_points = [self.world_to_screen(p) for p in polygon]
        screen_points = [(int(x), int(y)) for x, y in screen_points]

        if len(screen_points) < 3:
            return

        # Create surface for whole screen
        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)

        pygame.draw.polygon(surface, (*color, alpha), screen_points)

        if outline:
            pygame.draw.lines(surface, (*color, 255), True, screen_points, 3)

        self.screen.blit(surface, (0, 0))

    def draw_map(self):
        """Draw the map with territory highlights (with camera transformations)"""
        # Draw base map with camera transformation
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

        # Highlight neighbors of selected territory
        if self.selected_territory:
            neighbors = self.adjacencies.get(self.selected_territory, [])
            for neighbor in neighbors:
                self.draw_territory_overlay(neighbor, GREEN, alpha=80, outline=True)

        # Highlight selected territory
        if self.selected_territory:
            self.draw_territory_overlay(self.selected_territory, BLUE, alpha=100, outline=True)

        # Highlight pending addition
        if self.pending_addition:
            self.draw_territory_overlay(self.pending_addition, ORANGE, alpha=120, outline=True)

        # Highlight hovered territory
        if self.hovered_territory and self.hovered_territory != self.selected_territory:
            self.draw_territory_overlay(self.hovered_territory, YELLOW, alpha=60, outline=True)

        # Draw territory centers (transformed to screen coords)
        for territory, center in map_data.TERRITORY_CENTERS.items():
            screen_pos = self.world_to_screen(center)
            pygame.draw.circle(self.screen, BLACK, (int(screen_pos[0]), int(screen_pos[1])), 3)
    
    def draw_ui(self):
        """Draw UI panel"""
        # Draw camera info at top of screen
        camera_info = f"Camera: {self.camera_zoom:.1f}x zoom | Offset: ({int(self.camera_offset[0])}, {int(self.camera_offset[1])})"
        camera_text = self.small_font.render(camera_info, True, WHITE)
        camera_bg = pygame.Rect(5, 5, camera_text.get_width() + 10, camera_text.get_height() + 6)
        pygame.draw.rect(self.screen, (0, 0, 0, 180), camera_bg)
        self.screen.blit(camera_text, (10, 8))

        # Draw separator at right side of window
        ui_panel_x = WINDOW_WIDTH - UI_PANEL_WIDTH
        pygame.draw.rect(self.screen, (240, 240, 240), pygame.Rect(ui_panel_x, 0, UI_PANEL_WIDTH, WINDOW_HEIGHT))
        pygame.draw.line(self.screen, BLACK, (ui_panel_x, 0), (ui_panel_x, WINDOW_HEIGHT), 2)

        ui_x = ui_panel_x + 15
        ui_y = 20
        
        # Title
        title = self.large_font.render("Adjacency Tool", True, BLACK)
        self.screen.blit(title, (ui_x, ui_y))
        ui_y += 40
        
        # Mode display
        mode_text = f"Mode: {self.mode.upper()}"
        mode_surface = self.font.render(mode_text, True, BLUE if self.mode == 'add' else BLACK)
        self.screen.blit(mode_surface, (ui_x, ui_y))
        ui_y += 30
        
        # Selected territory info
        if self.selected_territory:
            # Territory name
            selected_lines = self.wrap_text(self.selected_territory, self.font, UI_PANEL_WIDTH - 30)
            for line in selected_lines:
                text = self.font.render(line, True, BLUE)
                self.screen.blit(text, (ui_x, ui_y))
                ui_y += 25
            
            ui_y += 10
            
            # Neighbors
            neighbors = self.adjacencies.get(self.selected_territory, [])
            neighbor_text = self.font.render(f"Neighbors: {len(neighbors)}", True, BLACK)
            self.screen.blit(neighbor_text, (ui_x, ui_y))
            ui_y += 30
            
            # List neighbors (scrollable if many)
            y_max = WINDOW_HEIGHT - 350
            for neighbor in sorted(neighbors):
                if ui_y > y_max:
                    more_text = self.small_font.render("(more...)", True, BLACK)
                    self.screen.blit(more_text, (ui_x, ui_y))
                    break
                
                # Wrap neighbor name if long
                neighbor_lines = self.wrap_text(f"• {neighbor}", self.small_font, UI_PANEL_WIDTH - 30)
                for line in neighbor_lines:
                    text = self.small_font.render(line, True, GREEN)
                    self.screen.blit(text, (ui_x, ui_y))
                    ui_y += 20
        
        # Instructions at bottom
        instructions = [
            "=== CAMERA ===",
            "Middle-Drag - Pan",
            "Mouse Wheel - Zoom",
            "Arrow Keys - Pan",
            "Edge scroll - Auto-pan",
            "",
            "=== CONTROLS ===",
            "Left Click - Select",
            "A - Toggle ADD mode",
            "S - Save",
            "ESC - Quit",
            "",
            "=== COLORS ===",
            "Blue = Selected",
            "Green = Neighbors",
            "Orange = Adding",
            "Yellow = Hover"
        ]
        
        ui_y = WINDOW_HEIGHT - len(instructions) * 22 - 20
        for line in instructions:
            if line.startswith("==="):
                text = self.font.render(line, True, BLACK)
            else:
                text = self.small_font.render(line, True, BLACK)
            self.screen.blit(text, (ui_x, ui_y))
            ui_y += 22
    
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
    
    def run(self):
        """Main loop with camera controls"""
        running = True

        while running:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        # Ignore clicks on UI panel
                        if event.pos[0] >= WINDOW_WIDTH - UI_PANEL_WIDTH:
                            continue
                        territory = self.get_territory_at_pos(event.pos)
                        if territory:
                            if self.mode == 'view':
                                self.selected_territory = territory
                                print(f"\n Selected: {territory}")
                                neighbors = self.adjacencies.get(territory, [])
                                print(f"Neighbors: {', '.join(sorted(neighbors))}")

                            elif self.mode == 'add':
                                if self.selected_territory and territory != self.selected_territory:
                                    self.toggle_adjacency(self.selected_territory, territory)
                                    self.pending_addition = None

                elif event.type == pygame.MOUSEMOTION:
                    # Camera drag
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())

                    # Hover detection (ignore UI panel area)
                    if event.pos[0] < WINDOW_WIDTH - UI_PANEL_WIDTH:
                        self.hovered_territory = self.get_territory_at_pos(event.pos)
                        if self.mode == 'add' and self.hovered_territory and self.hovered_territory != self.selected_territory:
                            self.pending_addition = self.hovered_territory
                        elif self.mode == 'view':
                            self.pending_addition = None
                    else:
                        self.hovered_territory = None
                        self.pending_addition = None

                elif event.type == pygame.MOUSEWHEEL:
                    # Camera zoom
                    self.handle_camera_zoom(event.y)

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_a:  # Toggle add mode
                        self.mode = 'add' if self.mode == 'view' else 'view'
                        self.pending_addition = None
                        print(f"Mode: {self.mode}")
                    
                    elif event.key == pygame.K_s:  # Save
                        print("\nSaving adjacencies...")
                        if self.save_adjacencies():
                            print("✅ Save successful!")
                        else:
                            print("❌ Save failed!")
                    
                    elif event.key == pygame.K_ESCAPE:  # Quit
                        running = False

            # Continuous camera controls (outside event loop)
            keys = pygame.key.get_pressed()
            self.handle_keyboard_camera(keys)

            # Edge scrolling
            mouse_pos = pygame.mouse.get_pos()
            self.handle_edge_scrolling(mouse_pos)

            # Drawing
            self.screen.fill(WHITE)
            self.draw_map()
            self.draw_ui()

            pygame.display.flip()
            self.clock.tick(FPS)
        
        pygame.quit()
        print("\nAdjacency tool closed")

if __name__ == "__main__":
    print("=== Adjacency Verification Tool ===")
    print("This tool helps you verify and correct territory adjacencies")
    print("\nControls:")
    print("- Click a territory to select it and see its neighbors (green)")
    print("- Press 'A' to enter ADD mode, then click territories to add/remove as neighbors")
    print("- Press 'S' to save changes to map_data.py")
    print("\nLoading...")
    
    tool = AdjacencyTool()
    tool.run()