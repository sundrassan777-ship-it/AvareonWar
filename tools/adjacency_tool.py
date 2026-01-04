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
        
        # Load the map image
        try:
            self.map_image = pygame.image.load("assets/map.jpg")
            self.map_image = pygame.transform.scale(self.map_image, (MAP_WIDTH, MAP_HEIGHT))
        except pygame.error as e:
            print(f"Error loading map: {e}")
            sys.exit(1)
        
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
    
    def get_territory_at_pos(self, pos):
        """Find which territory contains the given position"""
        for territory in reversed(list(map_data.TERRITORY_POLYGONS.keys())):
            polygon = map_data.TERRITORY_POLYGONS[territory]
            if map_data.point_in_polygon(pos, polygon):
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
            
            print("\nâœ… Adjacencies saved to map_data.py!")
            return True
            
        except Exception as e:
            print(f"ERROR saving adjacencies: {e}")
            return False
    
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
    
    def draw_map(self):
        """Draw the map with territory highlights"""
        # Draw base map
        self.screen.blit(self.map_image, (0, 0))
        
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
        
        # Draw territory centers
        for territory, center in map_data.TERRITORY_CENTERS.items():
            pygame.draw.circle(self.screen, BLACK, center, 3)
    
    def draw_ui(self):
        """Draw UI panel"""
        # Draw separator
        pygame.draw.line(self.screen, BLACK, (MAP_WIDTH, 0), (MAP_WIDTH, WINDOW_HEIGHT), 2)
        
        ui_x = MAP_WIDTH + 15
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
            selected_lines = self.wrap_text(self.selected_territory, self.font, 280)
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
                neighbor_lines = self.wrap_text(f"â€¢ {neighbor}", self.small_font, 280)
                for line in neighbor_lines:
                    text = self.small_font.render(line, True, GREEN)
                    self.screen.blit(text, (ui_x, ui_y))
                    ui_y += 20
        
        # Instructions at bottom
        instructions = [
            "=== CONTROLS ===",
            "",
            "Left Click - Select territory",
            "A - Toggle ADD mode",
            "  (Click territory to add/",
            "   remove as neighbor)",
            "",
            "S - Save to map_data.py",
            "ESC - Quit",
            "",
            "=== COLORS ===",
            "Blue = Selected territory",
            "Green = Current neighbors",
            "Orange = Adding neighbor",
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
        """Main loop"""
        running = True
        
        while running:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
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
                    self.hovered_territory = self.get_territory_at_pos(event.pos)
                    if self.mode == 'add' and self.hovered_territory and self.hovered_territory != self.selected_territory:
                        self.pending_addition = self.hovered_territory
                    elif self.mode == 'view':
                        self.pending_addition = None
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_a:  # Toggle add mode
                        self.mode = 'add' if self.mode == 'view' else 'view'
                        self.pending_addition = None
                        print(f"Mode: {self.mode}")
                    
                    elif event.key == pygame.K_s:  # Save
                        print("\nSaving adjacencies...")
                        if self.save_adjacencies():
                            print("âœ… Save successful!")
                        else:
                            print("âŒ Save failed!")
                    
                    elif event.key == pygame.K_ESCAPE:  # Quit
                        running = False
            
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
