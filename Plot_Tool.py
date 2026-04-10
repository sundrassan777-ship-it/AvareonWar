# -*- coding: utf-8 -*-
# plot_tool.py
# Interactive tool for placing building plots within territories

"""
PLOT PLACEMENT TOOL
This tool helps you place building plots within each territory.
Plots are locations where players can construct buildings (Farms, Barracks, etc.)
Click within a territory to place plots, then navigate to the next territory.
"""

import pygame
import json
import sys
import os
import map_data

# Multi-map support: --map <map_id> CLI argument selects which map to edit (default: avareon)
_tool_map_id = 'avareon'
for i, arg in enumerate(sys.argv):
    if arg == '--map' and i + 1 < len(sys.argv):
        _tool_map_id = sys.argv[i + 1]
_tool_map_dir = f'maps/{_tool_map_id}'

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

# Plot placement settings
PLOT_RADIUS = 10
MIN_PLOT_SPACING = 30  # Minimum pixels between plots
MIN_EDGE_DISTANCE = 15  # Minimum distance from territory edge

# Territory classifications for suggested plot counts
SMALL_TERRITORIES = ["The Comet", "Venexia", "Révia", "Cinto", "Ahtep", "Liadnon"]
LARGE_TERRITORIES = ["Orlais", "Amennia", "Espoia", "Anodia", "Sordia", "Linan", "Nefrid", "Odatria"]

class PlotTool:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Building Plot Placement Tool")
        self.clock = pygame.time.Clock()

        # Multi-map state
        self.current_map_id = _tool_map_id
        self.current_map_dir = _tool_map_dir

        # Load polygons
        map_data.load_polygons()
        if not map_data.TERRITORY_POLYGONS:
            print("ERROR: No territory polygons loaded!")
            sys.exit(1)

        # Load the map image
        self._load_map_image()

        # Camera system (same as Adjacency_Tool and Economic_Tool!)
        self.camera_offset = [0.0, 0.0]  # [x, y] in world coordinates
        self.camera_zoom = 0.3            # Start zoomed out to see full 4096x3072 map
        self.camera_drag_start = None     # For middle-mouse drag

        # Camera configuration
        self.camera_min_zoom = 0.2        # Can zoom out to see whole 4096x3072 map
        self.camera_max_zoom = 6.0        # Can zoom in very close
        self.edge_scroll_speed = 5
        self.edge_scroll_margin = 20
        self.keyboard_scroll_speed = 10

        # Map scaling cache (for performance)
        self.cached_scaled_map = None
        self.cached_zoom_level = None

        # State
        self.territories = list(map_data.TERRITORY_POLYGONS.keys())
        self.current_territory_index = 0
        self.plots = {}  # territory_name -> list of (x, y) positions
        
        # Load existing plots if available
        self.load_plots()
        
        # UI state
        self.hovered_plot = None  # For deletion highlighting
        
        # Fonts
        self.font = pygame.font.Font(None, 20)
        self.large_font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 18)


    
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


    # ========================================
    # PLOT MANAGEMENT METHODS
    # ========================================

    def _load_map_image(self):
        """Load (or reload) the map background image for the current map."""
        map_png = os.path.join(self.current_map_dir, 'map.png')
        if not os.path.exists(map_png):
            map_png = "assets/map.png"
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
        # Invalidate scaled map cache if it exists
        if hasattr(self, 'cached_scaled_map'):
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
        self.save_plots()
        self.current_map_id = map_ids[new_idx]
        self.current_map_dir = f'maps/{self.current_map_id}'
        print(f"Switched to map: {self.current_map_id}")
        self._load_map_image()
        _md.load_map(self.current_map_id)
        self.territories = list(map_data.TERRITORY_POLYGONS.keys())
        self.current_territory_index = 0
        self.hovered_plot = None
        self.load_plots()

    def load_plots(self):
        """Load previously saved plots if they exist"""
        self.plots = {}  # Clear existing data first
        try:
            with open(os.path.join(self.current_map_dir, 'plots.json'), 'r', encoding='utf-8') as f:
                self.plots = json.load(f)
            print(f"Loaded plots for {len(self.plots)} territories")
        except FileNotFoundError:
            print("No existing plots found, starting fresh")
    
    def save_plots(self):
        """Save all plots to JSON file"""
        with open(os.path.join(self.current_map_dir, 'plots.json'), 'w', encoding='utf-8') as f:
            json.dump(self.plots, f, indent=2, ensure_ascii=False)
        print(f"Saved plots for {len(self.plots)} territories")
    
    def get_current_territory(self):
        """Get the name of the current territory"""
        if self.current_territory_index < len(self.territories):
            return self.territories[self.current_territory_index]
        return None
    
    def suggest_plot_count(self, territory):
        """Suggest number of plots based on territory size/importance"""
        if territory in SMALL_TERRITORIES:
            return 1
        elif territory in LARGE_TERRITORIES:
            return 4
        else:
            return 2  # Default for medium territories
    
    def is_valid_plot_position(self, territory, pos):
        """Check if a position is valid for plot placement"""
        x, y = pos
        
        # Must be inside territory polygon
        polygon = map_data.TERRITORY_POLYGONS[territory]
        if not map_data.point_in_polygon(pos, polygon):
            return False
        
        # Check distance from other plots in this territory
        existing_plots = self.plots.get(territory, [])
        for plot_pos in existing_plots:
            px, py = plot_pos
            distance = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if distance < MIN_PLOT_SPACING:
                return False
        
        return True
    
    def add_plot(self, territory, pos):
        """Add a plot to the territory"""
        if territory not in self.plots:
            self.plots[territory] = []
        
        # Check if we haven't exceeded reasonable limits
        if len(self.plots[territory]) >= 4:
            print(f"Territory already has 4 plots (maximum)")
            return False
        
        if self.is_valid_plot_position(territory, pos):
            self.plots[territory].append(list(pos))
            print(f"Added plot to {territory} at {pos}")
            self.save_plots()  # Auto-save
            return True
        else:
            print(f"Invalid plot position")
            return False
    
    def remove_plot(self, territory, click_pos):
        """Remove the plot nearest to click position"""
        if territory not in self.plots or not self.plots[territory]:
            return False
        
        # Find nearest plot
        min_distance = float('inf')
        nearest_plot = None
        
        for plot_pos in self.plots[territory]:
            px, py = plot_pos
            cx, cy = click_pos
            distance = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if distance < min_distance:
                min_distance = distance
                nearest_plot = plot_pos
        
        # Remove if clicked close enough
        if nearest_plot and min_distance < PLOT_RADIUS + 5:
            self.plots[territory].remove(nearest_plot)
            print(f"Removed plot from {territory}")
            self.save_plots()  # Auto-save
            return True
        
        return False
    
    def clear_territory_plots(self, territory):
        """Remove all plots from a territory"""
        if territory in self.plots:
            self.plots[territory] = []
            self.save_plots()
            print(f"Cleared all plots from {territory}")
    
    def get_plot_at_pos(self, territory, pos):
        """Get plot at position (for hover highlighting)"""
        if territory not in self.plots:
            return None
        
        for plot_pos in self.plots[territory]:
            px, py = plot_pos
            cx, cy = pos
            distance = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if distance < PLOT_RADIUS + 5:
                return plot_pos
        
        return None
    

    # ========================================
    # RENDERING METHODS
    # ========================================

    
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
    
    def draw_plots(self):
        """Draw all plots on the map (with camera transformations)"""
        territory = self.get_current_territory()
        
        # Draw plots for current territory
        if territory and territory in self.plots:
            for plot_pos in self.plots[territory]:
                # Transform world coordinates to screen coordinates
                screen_pos = self.world_to_screen(plot_pos)
                px, py = int(screen_pos[0]), int(screen_pos[1])
                
                # Check if this plot is hovered
                is_hovered = (self.hovered_plot and 
                            plot_pos[0] == self.hovered_plot[0] and 
                            plot_pos[1] == self.hovered_plot[1])
                
                color = YELLOW if is_hovered else GREEN
                
                # Scale plot radius by zoom for visibility
                scaled_radius = int(PLOT_RADIUS * self.camera_zoom)
                scaled_radius = max(3, min(scaled_radius, 20))  # Clamp between 3 and 20
                
                # Draw filled circle
                pygame.draw.circle(self.screen, color, (px, py), scaled_radius)
                # Draw outline
                pygame.draw.circle(self.screen, BLACK, (px, py), scaled_radius, 2)
        
        # Draw plots for other territories (faded)
        for other_territory, plots in self.plots.items():
            if other_territory != territory:
                for plot_pos in plots:
                    # Transform world coordinates to screen coordinates
                    screen_pos = self.world_to_screen(plot_pos)
                    px, py = int(screen_pos[0]), int(screen_pos[1])
                    
                    # Scale plot radius by zoom
                    scaled_radius = int((PLOT_RADIUS - 2) * self.camera_zoom)
                    scaled_radius = max(2, min(scaled_radius, 18))  # Clamp
                    
                    pygame.draw.circle(self.screen, (100, 100, 100), (px, py), scaled_radius)


    def draw_map(self):
        """Draw the map with camera transformation"""
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

        # Highlight current territory
        territory = self.get_current_territory()
        if territory:
            self.draw_territory_overlay(territory, BLUE, alpha=60, outline=True)
        
        # Draw plots
        self.draw_plots()

    def draw_ui(self):
        """Draw UI panel"""
        camera_info = f"Camera: {self.camera_zoom:.1f}x zoom | Offset: ({int(self.camera_offset[0])}, {int(self.camera_offset[1])})"
        camera_text = self.small_font.render(camera_info, True, WHITE)
        camera_bg = pygame.Rect(5, 5, camera_text.get_width() + 10, camera_text.get_height() + 6)
        pygame.draw.rect(self.screen, (0, 0, 0, 180), camera_bg)
        self.screen.blit(camera_text, (10, 8))

        # Draw separator line at right side of window
        ui_panel_x = WINDOW_WIDTH - UI_PANEL_WIDTH
        pygame.draw.line(self.screen, BLACK, (ui_panel_x, 0), (ui_panel_x, WINDOW_HEIGHT), 2)

        ui_x = ui_panel_x + 15
        ui_y = 20

        # Map selector (M key to cycle)
        import map_data as _md
        map_label = self.small_font.render("Map [M]:", True, (100, 100, 100))
        self.screen.blit(map_label, (ui_x, ui_y))
        map_name = self.font.render(_md.get_map_display_name(self.current_map_id), True, BLUE)
        self.screen.blit(map_name, (ui_x + map_label.get_width() + 6, ui_y))
        ui_y += 28

        # Title
        title = self.large_font.render("Plot Placement", True, BLACK)
        self.screen.blit(title, (ui_x, ui_y))
        ui_y += 50
        
        # Current territory
        territory = self.get_current_territory()
        if territory:
            # Territory name (wrapped if needed)
            name_lines = self.wrap_text(territory, self.font, UI_PANEL_WIDTH - 30)
            for line in name_lines:
                text = self.font.render(line, True, BLUE)
                self.screen.blit(text, (ui_x, ui_y))
                ui_y += 28
            
            ui_y += 10
            
            # Progress
            progress_text = self.font.render(f"Territory {self.current_territory_index + 1}/{len(self.territories)}", True, BLACK)
            self.screen.blit(progress_text, (ui_x, ui_y))
            ui_y += 30
            
            # Plots count
            current_plots = len(self.plots.get(territory, []))
            suggested = self.suggest_plot_count(territory)
            plots_text = self.font.render(f"Plots: {current_plots}/4", True, BLACK)
            self.screen.blit(plots_text, (ui_x, ui_y))
            ui_y += 25
            
            # Suggested count
            suggest_text = self.small_font.render(f"Suggested: {suggested}", True, (100, 100, 100))
            self.screen.blit(suggest_text, (ui_x, ui_y))
            ui_y += 40
        
        # Instructions
        instructions = [
            "=== CONTROLS ===",
            "",
            "Click - Place plot",
            "Click plot - Remove",
            "R - Clear territory",
            "",
            "LEFT/RIGHT - Navigate",
            "S - Save",
            "ESC - Quit",
            "",
            "=== PLOT GUIDE ===",
            "Small territories: 1 plot",
            "Medium: 2-3 plots",
            "Large/Strategic: 4 plots",
            "",
            "Green = Plot location",
            "Yellow = Hovered (remove)",
            "",
            "Space plots 30px apart",
            "Keep away from edges"
        ]
        
        for line in instructions:
            if line.startswith("==="):
                text = self.font.render(line, True, BLACK)
            else:
                text = self.small_font.render(line, True, BLACK)
            self.screen.blit(text, (ui_x, ui_y))
            ui_y += 22
        
        # Completion count
        ui_y = WINDOW_HEIGHT - 60
        completed = sum(1 for t in self.territories if t in self.plots and self.plots[t])
        completion_text = self.font.render(f"Completed: {completed}/{len(self.territories)}", True, GREEN)
        self.screen.blit(completion_text, (ui_x, ui_y))
    
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
                        
                        # Convert screen position to world position
                        world_pos = self.screen_to_world(event.pos)
                        territory = self.get_current_territory()
                        if territory:
                            # Try to remove plot first
                            if not self.remove_plot(territory, world_pos):
                                # If no plot removed, try to add
                                self.add_plot(territory, world_pos)

                elif event.type == pygame.MOUSEMOTION:
                    # Camera drag
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())

                    # Update hovered plot (ignore UI panel area)
                    territory = self.get_current_territory()
                    if territory and event.pos[0] < WINDOW_WIDTH - UI_PANEL_WIDTH:
                        # Convert screen position to world position for hover detection
                        world_pos = self.screen_to_world(event.pos)
                        self.hovered_plot = self.get_plot_at_pos(territory, world_pos)
                    else:
                        self.hovered_plot = None

                elif event.type == pygame.MOUSEWHEEL:
                    # Camera zoom
                    self.handle_camera_zoom(event.y)
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_n:  # Next territory
                        if self.current_territory_index < len(self.territories) - 1:
                            self.current_territory_index += 1
                    
                    elif event.key == pygame.K_p:  # Previous territory
                        if self.current_territory_index > 0:
                            self.current_territory_index -= 1
                    
                    elif event.key == pygame.K_r:  # Clear territory
                        territory = self.get_current_territory()
                        if territory:
                            self.clear_territory_plots(territory)
                    
                    elif event.key == pygame.K_s:  # Save
                        self.save_plots()
                        print("Plots saved!")
                    
                    elif event.key == pygame.K_m:  # Cycle to next map
                        self._switch_map()

                    elif event.key == pygame.K_ESCAPE:  # Quit
                        self.save_plots()
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
        print("")
        print("=== Summary ===")
        completed = sum(1 for t in self.territories if t in self.plots and self.plots[t])
        print(f"Plots placed for {completed}/{len(self.territories)} territories")
        print(f"Progress saved to '{os.path.join(self.current_map_dir, 'plots.json')}'")



if __name__ == "__main__":
    print("=== Building Plot Placement Tool ===")
    print("This tool helps you place building plots within territories")
    print("")
    print("Controls:")
    print("- Click within territory to place plot")
    print("- Click existing plot to remove it")
    print("- Middle-drag to pan camera")
    print("- Mouse wheel to zoom")
    print("- Arrow keys to pan")
    print("- N/P to navigate territories")
    print("- R to clear all plots from current territory")
    print("- S to save progress")
    print("")
    print("Loading...")
    
    tool = PlotTool()
    tool.run()
