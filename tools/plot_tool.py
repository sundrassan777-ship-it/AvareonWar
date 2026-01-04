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
import map_data

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 850
MAP_WIDTH = 1269
MAP_HEIGHT = 903
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
SMALL_TERRITORIES = ["The Comet", "Venexia", "RÃ©via", "Cinto", "Ahtep", "Liadnon", "Quil'en"]
LARGE_TERRITORIES = ["Orlais", "Amennia", "Azincourne", "Espoia", "Naragonthid", 
                     "Anodia", "Sordia", "Linan", "Nefrid", "Odatria"]

class PlotTool:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Building Plot Placement Tool")
        self.clock = pygame.time.Clock()
        
        # Load polygons
        map_data.load_polygons()
        if not map_data.TERRITORY_POLYGONS:
            print("ERROR: No territory polygons loaded!")
            sys.exit(1)
        
        # Load the map image
        try:
            self.map_image = pygame.image.load("assets/map.jpg")
            self.map_image = pygame.transform.scale(self.map_image, (MAP_WIDTH, MAP_HEIGHT))
        except pygame.error as e:
            print(f"Error loading map: {e}")
            sys.exit(1)
        
        # State
        self.territories = list(map_data.TERRITORY_POLYGONS.keys())
        self.current_territory_index = 0
        self.plots = {}  # territory_name -> list of (x, y) positions
        
        # Load existing plots if available
        self.load_plots()
        
        # UI state
        self.hovered_plot = None  # For deletion highlighting
        
        # Fonts
        self.font = pygame.font.Font(None, 24)
        self.large_font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 18)
    
    def load_plots(self):
        """Load previously saved plots if they exist"""
        try:
            with open('plots.json', 'r', encoding='utf-8') as f:
                self.plots = json.load(f)
            print(f"Loaded plots for {len(self.plots)} territories")
        except FileNotFoundError:
            print("No existing plots found, starting fresh")
    
    def save_plots(self):
        """Save all plots to JSON file"""
        with open('plots.json', 'w', encoding='utf-8') as f:
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
    
    def draw_territory_overlay(self, territory, color, alpha=100, outline=False):
        """Draw a colored overlay on a territory"""
        if territory not in map_data.TERRITORY_POLYGONS:
            return
        
        polygon = map_data.TERRITORY_POLYGONS[territory]
        surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
        
        pygame.draw.polygon(surface, (*color, alpha), polygon)
        
        if outline:
            pygame.draw.lines(surface, (*color, 255), True, polygon, 3)
        
        self.screen.blit(surface, (0, 0))
    
    def draw_plots(self):
        """Draw all plots on the map"""
        territory = self.get_current_territory()
        
        # Draw plots for current territory
        if territory and territory in self.plots:
            for plot_pos in self.plots[territory]:
                px, py = plot_pos
                
                # Check if this plot is hovered
                is_hovered = (self.hovered_plot and 
                            plot_pos[0] == self.hovered_plot[0] and 
                            plot_pos[1] == self.hovered_plot[1])
                
                color = YELLOW if is_hovered else GREEN
                
                # Draw filled circle
                pygame.draw.circle(self.screen, color, (int(px), int(py)), PLOT_RADIUS)
                # Draw outline
                pygame.draw.circle(self.screen, BLACK, (int(px), int(py)), PLOT_RADIUS, 2)
        
        # Draw plots for other territories (faded)
        for other_territory, plots in self.plots.items():
            if other_territory != territory:
                for plot_pos in plots:
                    px, py = plot_pos
                    pygame.draw.circle(self.screen, (100, 100, 100), (int(px), int(py)), PLOT_RADIUS - 2)
    
    def draw_ui(self):
        """Draw UI panel"""
        # Draw separator line
        pygame.draw.line(self.screen, BLACK, (MAP_WIDTH, 0), (MAP_WIDTH, WINDOW_HEIGHT), 2)
        
        ui_x = MAP_WIDTH + 15
        ui_y = 20
        
        # Title
        title = self.large_font.render("Plot Placement", True, BLACK)
        self.screen.blit(title, (ui_x, ui_y))
        ui_y += 50
        
        # Current territory
        territory = self.get_current_territory()
        if territory:
            # Territory name (wrapped if needed)
            name_lines = self.wrap_text(territory, self.font, 280)
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
        """Main loop"""
        running = True
        
        while running:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        if event.pos[0] < MAP_WIDTH:  # Click on map
                            territory = self.get_current_territory()
                            if territory:
                                # Try to remove plot first
                                if not self.remove_plot(territory, event.pos):
                                    # If no plot removed, try to add
                                    self.add_plot(territory, event.pos)
                
                elif event.type == pygame.MOUSEMOTION:
                    # Update hovered plot
                    territory = self.get_current_territory()
                    if territory and event.pos[0] < MAP_WIDTH:
                        self.hovered_plot = self.get_plot_at_pos(territory, event.pos)
                    else:
                        self.hovered_plot = None
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:  # Previous territory
                        if self.current_territory_index > 0:
                            self.current_territory_index -= 1
                    
                    elif event.key == pygame.K_RIGHT:  # Next territory
                        if self.current_territory_index < len(self.territories) - 1:
                            self.current_territory_index += 1
                    
                    elif event.key == pygame.K_r:  # Clear territory
                        territory = self.get_current_territory()
                        if territory:
                            self.clear_territory_plots(territory)
                    
                    elif event.key == pygame.K_s:  # Save
                        self.save_plots()
                        print("âœ… Plots saved!")
                    
                    elif event.key == pygame.K_ESCAPE:  # Quit
                        self.save_plots()
                        running = False
            
            # Drawing
            self.screen.fill(WHITE)
            
            # Draw map
            self.screen.blit(self.map_image, (0, 0))
            
            # Highlight current territory
            territory = self.get_current_territory()
            if territory:
                self.draw_territory_overlay(territory, BLUE, alpha=60, outline=True)
            
            # Draw plots
            self.draw_plots()
            
            # Draw UI
            self.draw_ui()
            
            pygame.display.flip()
            self.clock.tick(FPS)
        
        pygame.quit()
        print("\n=== Summary ===")
        completed = sum(1 for t in self.territories if t in self.plots and self.plots[t])
        print(f"Plots placed for {completed}/{len(self.territories)} territories")
        print("Progress saved to 'plots.json'")

if __name__ == "__main__":
    print("=== Building Plot Placement Tool ===")
    print("This tool helps you place building plots within territories")
    print("\nControls:")
    print("- Click within territory to place plot")
    print("- Click existing plot to remove it")
    print("- LEFT/RIGHT arrows to navigate territories")
    print("- R to clear all plots from current territory")
    print("- S to save progress")
    print("\nLoading...")
    
    tool = PlotTool()
    tool.run()
