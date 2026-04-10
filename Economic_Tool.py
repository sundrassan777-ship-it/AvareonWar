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
    "Orlais", "Amennia", "Espoia", "Linan", "Sordia"
]

TIER_1_SUGGESTIONS = [
    "The Comet", "Venexia", "Révia", "Cinto",
    "Ahtep", "Liadnon", "Sstep", "Conda",
    "Ahara", "Oucine"
]

class EconomicTool:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Economic Power Assignment Tool")
        self.clock = pygame.time.Clock()

        # Multi-map state
        self.current_map_id = _tool_map_id
        self.current_map_dir = _tool_map_dir

        # Load polygons and adjacency data
        map_data.load_polygons()
        if not map_data.TERRITORY_POLYGONS:
            print("ERROR: No territory polygons loaded!")
            sys.exit(1)

        # Load the map image
        self._load_map_image()

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
        self.territories = sorted(list(map_data.TERRITORY_POLYGONS.keys()))
        self.current_territory_index = 0
        self.economic_tiers = {}  # territory_name -> tier (1/2/3)

        # Load existing economic data if available
        self.load_economic_data()

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

    def get_territory_at_pos(self, pos):
        """Find which territory contains the given position"""
        # Convert screen position to world position!
        world_pos = self.screen_to_world(pos)
        for territory in reversed(list(map_data.TERRITORY_POLYGONS.keys())):
            polygon = map_data.TERRITORY_POLYGONS[territory]
            if map_data.point_in_polygon(world_pos, polygon):
                return territory
    
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
        self.save_economic_data()
        self.current_map_id = map_ids[new_idx]
        self.current_map_dir = f'maps/{self.current_map_id}'
        print(f"Switched to map: {self.current_map_id}")
        self._load_map_image()
        _md.load_map(self.current_map_id)
        self.territories = sorted(list(map_data.TERRITORY_POLYGONS.keys()))
        self.current_territory_index = 0
        self.load_economic_data()

    def load_economic_data(self):
        """Load previously saved economic tiers if they exist"""
        self.economic_tiers = {}  # Clear existing data first
        try:
            with open(os.path.join(self.current_map_dir, 'economic_data.json'), 'r', encoding='utf-8') as f:
                self.economic_tiers = json.load(f)
            print(f"Loaded economic data for {len(self.economic_tiers)} territories")
        except FileNotFoundError:
            print("No existing economic data found, starting fresh")
            # Initialize with default Tier 2 for all territories
            for territory in self.territories:
                self.economic_tiers[territory] = 2
    
    def save_economic_data(self):
        """Save all economic tiers to JSON file"""
        with open(os.path.join(self.current_map_dir, 'economic_data.json'), 'w', encoding='utf-8') as f:
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

    def draw_all_territories_by_tier(self):
        """Draw all territories colored by their economic tier"""
        for territory, tier in self.economic_tiers.items():
            if territory in map_data.TERRITORY_POLYGONS:
                color = self.get_tier_color(tier)
                self.draw_territory_overlay(territory, color, alpha=60)
    
    def draw_map(self):
        """Draw the map with territory highlights (with camera transformations)"""
        scaled_map_width = int(MAP_WIDTH * self.camera_zoom)
        scaled_map_height = int(MAP_HEIGHT * self.camera_zoom)
        if self.cached_zoom_level != self.camera_zoom:
            self.cached_scaled_map = pygame.transform.smoothscale(self.map_image_original, (scaled_map_width, scaled_map_height))
            self.cached_zoom_level = self.camera_zoom
        map_x = int(-self.camera_offset[0] * self.camera_zoom)
        map_y = int(-self.camera_offset[1] * self.camera_zoom)
        self.screen.blit(self.cached_scaled_map, (map_x, map_y))
        self.draw_all_territories_by_tier()
        territory = self.get_current_territory()
        if territory:
            tier_color = self.get_tier_color(self.economic_tiers.get(territory, 2))
            self.draw_territory_overlay(territory, tier_color, alpha=120, outline=True)
    
    def draw_ui(self):
        """Draw UI panel"""
        camera_info = f"Camera: {self.camera_zoom:.1f}x zoom | Offset: ({int(self.camera_offset[0])}, {int(self.camera_offset[1])})"
        camera_text = self.small_font.render(camera_info, True, WHITE)
        pygame.draw.rect(self.screen, (0, 0, 0, 180), pygame.Rect(5, 5, camera_text.get_width() + 10, camera_text.get_height() + 6))
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
        title = self.large_font.render("Economic Power", True, BLACK)
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
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())
                elif event.type == pygame.MOUSEWHEEL:
                    self.handle_camera_zoom(event.y)
                elif event.type == pygame.KEYDOWN:
                    territory = self.get_current_territory()
                    if event.key == pygame.K_1 and territory:
                        self.set_tier(territory, 1)
                    elif event.key == pygame.K_2 and territory:
                        self.set_tier(territory, 2)
                    elif event.key == pygame.K_3 and territory:
                        self.set_tier(territory, 3)
                    elif event.key == pygame.K_n and self.current_territory_index < len(self.territories) - 1:
                        self.current_territory_index += 1
                    elif event.key == pygame.K_p and self.current_territory_index > 0:
                        self.current_territory_index -= 1
                    elif event.key == pygame.K_s:
                        self.save_economic_data()
                        print("Saved!")
                    elif event.key == pygame.K_m:  # Cycle to next map
                        self._switch_map()
                    elif event.key == pygame.K_ESCAPE:
                        self.save_economic_data()
                        running = False
            keys = pygame.key.get_pressed()
            self.handle_keyboard_camera(keys)

            # Edge scrolling
            mouse_pos = pygame.mouse.get_pos()
            self.handle_edge_scrolling(mouse_pos)
            self.screen.fill(WHITE)
            self.draw_map()
            self.draw_ui()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()
        tc, ai = self.get_statistics()
        print("=== Stats: T1:" + str(tc[1]) + " T2:" + str(tc[2]) + " T3:" + str(tc[3]) + " Avg:" + str(round(ai,1)) + "g")

if __name__ == "__main__":
    print("=== Economic Power Assignment Tool ===")
    print("Controls: 1/2/3 tier | N/P nav | Arrows pan | Wheel zoom | Mid-drag | S save")
    tool = EconomicTool()
    tool.run()
