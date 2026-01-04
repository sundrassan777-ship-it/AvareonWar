# -*- coding: utf-8 -*-
# economic_tool.py
# Interactive tool for assigning economic tiers to territories

"""
ECONOMIC POWER ASSIGNMENT TOOL
This tool helps you assign economic tiers to each territory.
Each tier determines how much gold the territory generates per turn:
- Tier 1: 10 gold/turn (Remote, small territories)
- Tier 2: 20 gold/turn (Standard territories)
- Tier 3: 30 gold/turn (Strategic capitals, trade centers)
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
ORANGE = (255, 165, 0)

# Tier colors
TIER_1_COLOR = (150, 255, 150)  # Light green
TIER_2_COLOR = (255, 215, 0)    # Gold
TIER_3_COLOR = (255, 140, 0)    # Dark orange

# Economic tier values
TIER_INCOME = {
    1: 10,
    2: 20,
    3: 30
}

# Suggested tier classifications
TIER_3_SUGGESTIONS = [
    "Orlais", "Amennia", "Azincourne", "Naragonthid", 
    "Espoia", "Linan", "Sordia"
]

TIER_1_SUGGESTIONS = [
    "The Comet", "Venexia", "RÃ©via", "Elletia", "Cinto", 
    "Ahtep", "Liadnon", "Quil'en", "Sstep", "Conda", 
    "Ahara", "Oucine"
]

class EconomicTool:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Economic Power Assignment Tool")
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
        self.economic_tiers = {}  # territory_name -> tier (1, 2, or 3)
        
        # Load existing economic data if available
        self.load_economic_data()
        
        # Fonts
        self.font = pygame.font.Font(None, 24)
        self.large_font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 18)
    
    def load_economic_data(self):
        """Load previously saved economic tiers if they exist"""
        try:
            with open('economic_data.json', 'r', encoding='utf-8') as f:
                self.economic_tiers = json.load(f)
            print(f"Loaded economic data for {len(self.economic_tiers)} territories")
        except FileNotFoundError:
            print("No existing economic data found, starting fresh")
            # Initialize with default Tier 2 for all territories
            for territory in self.territories:
                self.economic_tiers[territory] = 2
    
    def save_economic_data(self):
        """Save all economic tiers to JSON file"""
        with open('economic_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.economic_tiers, f, indent=2, ensure_ascii=False)
        print(f"Saved economic data for {len(self.economic_tiers)} territories")
    
    def get_current_territory(self):
        """Get the name of the current territory"""
        if self.current_territory_index < len(self.territories):
            return self.territories[self.current_territory_index]
        return None
    
    def suggest_tier(self, territory):
        """Suggest economic tier based on territory characteristics"""
        if territory in TIER_3_SUGGESTIONS:
            return 3
        elif territory in TIER_1_SUGGESTIONS:
            return 1
        else:
            return 2
    
    def set_tier(self, territory, tier):
        """Set economic tier for a territory"""
        if tier in [1, 2, 3]:
            self.economic_tiers[territory] = tier
            self.save_economic_data()  # Auto-save
            print(f"{territory}: Tier {tier} ({TIER_INCOME[tier]} gold/turn)")
    
    def get_tier_color(self, tier):
        """Get color for displaying a tier"""
        if tier == 1:
            return TIER_1_COLOR
        elif tier == 2:
            return TIER_2_COLOR
        elif tier == 3:
            return TIER_3_COLOR
        return WHITE
    
    def get_statistics(self):
        """Calculate statistics about tier distribution"""
        tier_counts = {1: 0, 2: 0, 3: 0}
        for tier in self.economic_tiers.values():
            tier_counts[tier] += 1
        
        total = len(self.economic_tiers)
        avg_income = sum(TIER_INCOME[tier] for tier in self.economic_tiers.values()) / total if total > 0 else 0
        
        return tier_counts, avg_income
    
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
    
    def draw_all_territories_by_tier(self):
        """Draw all territories colored by their economic tier"""
        for territory, tier in self.economic_tiers.items():
            if territory in map_data.TERRITORY_POLYGONS:
                color = self.get_tier_color(tier)
                self.draw_territory_overlay(territory, color, alpha=60)
    
    def draw_ui(self):
        """Draw UI panel"""
        # Draw separator line
        pygame.draw.line(self.screen, BLACK, (MAP_WIDTH, 0), (MAP_WIDTH, WINDOW_HEIGHT), 2)
        
        ui_x = MAP_WIDTH + 15
        ui_y = 20
        
        # Title
        title = self.large_font.render("Economic Power", True, BLACK)
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
            
            # Current tier
            current_tier = self.economic_tiers.get(territory, 2)
            tier_color = self.get_tier_color(current_tier)
            tier_text = self.large_font.render(f"Tier {current_tier}", True, tier_color)
            self.screen.blit(tier_text, (ui_x, ui_y))
            ui_y += 35
            
            # Income value
            income = TIER_INCOME[current_tier]
            income_text = self.font.render(f"{income} gold/turn", True, BLACK)
            self.screen.blit(income_text, (ui_x, ui_y))
            ui_y += 35
            
            # Suggested tier
            suggested = self.suggest_tier(territory)
            if suggested != current_tier:
                suggest_text = self.small_font.render(f"Suggested: Tier {suggested}", True, (100, 100, 100))
                self.screen.blit(suggest_text, (ui_x, ui_y))
                ui_y += 25
            ui_y += 10
        
        # Tier guide
        guide = [
            "=== TIER GUIDE ===",
            "",
            "1 - Press 1 for Tier 1",
            "    (10 gold/turn)",
            "    Remote, small",
            "",
            "2 - Press 2 for Tier 2",
            "    (20 gold/turn)",
            "    Standard",
            "",
            "3 - Press 3 for Tier 3",
            "    (30 gold/turn)",
            "    Strategic, wealthy",
        ]
        
        for line in guide:
            if line.startswith("==="):
                text = self.font.render(line, True, BLACK)
            elif line.startswith(("1 -", "2 -", "3 -")):
                tier_num = int(line[0])
                color = self.get_tier_color(tier_num)
                text = self.small_font.render(line, True, color)
            else:
                text = self.small_font.render(line, True, BLACK)
            self.screen.blit(text, (ui_x, ui_y))
            ui_y += 22
        
        ui_y += 10
        
        # Controls
        controls = [
            "=== CONTROLS ===",
            "",
            "1/2/3 - Set tier",
            "LEFT/RIGHT - Navigate",
            "S - Save",
            "ESC - Quit",
        ]
        
        for line in controls:
            if line.startswith("==="):
                text = self.font.render(line, True, BLACK)
            else:
                text = self.small_font.render(line, True, BLACK)
            self.screen.blit(text, (ui_x, ui_y))
            ui_y += 22
        
        # Statistics at bottom
        ui_y = WINDOW_HEIGHT - 160
        
        stats_title = self.font.render("=== STATISTICS ===", True, BLACK)
        self.screen.blit(stats_title, (ui_x, ui_y))
        ui_y += 30
        
        tier_counts, avg_income = self.get_statistics()
        
        for tier in [1, 2, 3]:
            count = tier_counts[tier]
            percentage = (count / len(self.territories)) * 100 if self.territories else 0
            color = self.get_tier_color(tier)
            stats_text = self.small_font.render(f"Tier {tier}: {count} ({percentage:.0f}%)", True, color)
            self.screen.blit(stats_text, (ui_x, ui_y))
            ui_y += 20
        
        ui_y += 10
        avg_text = self.small_font.render(f"Average: {avg_income:.1f}g/territory", True, BLACK)
        self.screen.blit(avg_text, (ui_x, ui_y))
    
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
                
                elif event.type == pygame.KEYDOWN:
                    territory = self.get_current_territory()
                    
                    if event.key == pygame.K_1:  # Set Tier 1
                        if territory:
                            self.set_tier(territory, 1)
                    
                    elif event.key == pygame.K_2:  # Set Tier 2
                        if territory:
                            self.set_tier(territory, 2)
                    
                    elif event.key == pygame.K_3:  # Set Tier 3
                        if territory:
                            self.set_tier(territory, 3)
                    
                    elif event.key == pygame.K_LEFT:  # Previous territory
                        if self.current_territory_index > 0:
                            self.current_territory_index -= 1
                    
                    elif event.key == pygame.K_RIGHT:  # Next territory
                        if self.current_territory_index < len(self.territories) - 1:
                            self.current_territory_index += 1
                    
                    elif event.key == pygame.K_s:  # Save
                        self.save_economic_data()
                        print("âœ… Economic data saved!")
                    
                    elif event.key == pygame.K_ESCAPE:  # Quit
                        self.save_economic_data()
                        running = False
            
            # Drawing
            self.screen.fill(WHITE)
            
            # Draw map
            self.screen.blit(self.map_image, (0, 0))
            
            # Draw all territories colored by tier
            self.draw_all_territories_by_tier()
            
            # Highlight current territory
            territory = self.get_current_territory()
            if territory:
                current_tier = self.economic_tiers.get(territory, 2)
                tier_color = self.get_tier_color(current_tier)
                self.draw_territory_overlay(territory, tier_color, alpha=120, outline=True)
            
            # Draw UI
            self.draw_ui()
            
            pygame.display.flip()
            self.clock.tick(FPS)
        
        pygame.quit()
        
        # Final statistics
        tier_counts, avg_income = self.get_statistics()
        print("\n=== Final Statistics ===")
        print(f"Tier 1 (10g): {tier_counts[1]} territories ({tier_counts[1]/len(self.territories)*100:.1f}%)")
        print(f"Tier 2 (20g): {tier_counts[2]} territories ({tier_counts[2]/len(self.territories)*100:.1f}%)")
        print(f"Tier 3 (30g): {tier_counts[3]} territories ({tier_counts[3]/len(self.territories)*100:.1f}%)")
        print(f"Average income: {avg_income:.1f} gold/territory")
        print(f"\nData saved to 'economic_data.json'")

if __name__ == "__main__":
    print("=== Economic Power Assignment Tool ===")
    print("This tool helps you assign economic tiers to territories")
    print("\nTier 1 (10 gold): Remote, small territories")
    print("Tier 2 (20 gold): Standard territories")
    print("Tier 3 (30 gold): Strategic capitals, wealthy regions")
    print("\nControls:")
    print("- Press 1, 2, or 3 to set tier for current territory")
    print("- LEFT/RIGHT arrows to navigate")
    print("- S to save progress")
    print("\nLoading...")
    
    tool = EconomicTool()
    tool.run()
