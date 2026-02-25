# -*- coding: utf-8 -*-
# Bonus_Tool.py
# Interactive tool for assigning territorial bonuses to territories

"""
TERRITORIAL BONUS ASSIGNMENT TOOL
This tool helps you assign bonuses to each territory.
Each territory provides one global bonus to its owner:
- Income Bonus: +3% income per territory
- Tech Cost: -5% technology research cost per territory
- Unit Cost: -5% unit training cost per territory
- Hero Cost: -3% hero training cost per territory
- Pikeman Strength: +10% Pikeman strength per territory
- Archer Strength: +10% Archer strength per territory
- Swordsman Strength: +10% Swordsman strength per territory
- Cavalry Strength: +10% Cavalry strength per territory
- Building Cost: -15% building cost per territory
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
GRAY = (200, 200, 200)

# Bonus types and their colors
BONUS_TYPES = {
    'income_bonus': {'name': 'Income Bonus', 'value': '+3%', 'color': (100, 200, 255), 'key': '1'},
    'tech_cost': {'name': 'Tech Cost', 'value': '-5%', 'color': (200, 100, 255), 'key': '2'},
    'unit_cost': {'name': 'Unit Cost', 'value': '-5%', 'color': (255, 180, 100), 'key': '3'},
    'hero_cost': {'name': 'Hero Cost', 'value': '-3%', 'color': (255, 150, 200), 'key': '4'},
    'pikeman_str': {'name': 'Pikeman Strength', 'value': '+10%', 'color': (100, 200, 100), 'key': '5'},
    'archer_str': {'name': 'Archer Strength', 'value': '+10%', 'color': (200, 255, 100), 'key': '6'},
    'swordsman_str': {'name': 'Swordsman Strength', 'value': '+10%', 'color': (255, 120, 100), 'key': '7'},
    'cavalry_str': {'name': 'Cavalry Strength', 'value': '+10%', 'color': (200, 150, 100), 'key': '8'},
    'building_cost': {'name': 'Building Cost', 'value': '-15%', 'color': (150, 180, 200), 'key': '9'}
}

# Bonus types ordered for display
BONUS_ORDER = [
    'income_bonus', 'tech_cost', 'unit_cost', 'hero_cost',
    'pikeman_str', 'archer_str', 'swordsman_str', 'cavalry_str',
    'building_cost'
]

class BonusTool:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Territorial Bonus Assignment Tool")
        self.clock = pygame.time.Clock()

        # Load polygons
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

        # Camera system (same as Adjacency_Tool!)
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

        # State
        self.territories = sorted(list(map_data.TERRITORY_POLYGONS.keys()))
        self.current_territory_index = 0
        self.territory_bonuses = {}  # territory_name -> bonus_type_id

        # Load existing bonus data if available
        self.load_bonus_data()

        # Fonts
        self.font = pygame.font.Font(None, 22)
        self.large_font = pygame.font.Font(None, 36)
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
    # DATA LOADING/SAVING METHODS
    # ========================================

    def load_bonus_data(self):
        """Load previously saved territorial bonuses if they exist"""
        try:
            with open('territory_bonuses.json', 'r', encoding='utf-8') as f:
                self.territory_bonuses = json.load(f)
            print(f"Loaded bonuses for {len(self.territory_bonuses)} territories")
        except FileNotFoundError:
            print("No existing bonus data found, starting fresh")
            self.territory_bonuses = {}

    def save_bonus_data(self):
        """Save all territorial bonuses to JSON file"""
        # Check if all territories have bonuses assigned
        unassigned = [t for t in self.territories if t not in self.territory_bonuses]
        if unassigned:
            print(f"WARNING: {len(unassigned)} territories still need bonuses assigned!")
            print(f"Unassigned: {', '.join(unassigned[:5])}{'...' if len(unassigned) > 5 else ''}")
            return False

        with open('territory_bonuses.json', 'w', encoding='utf-8') as f:
            json.dump(self.territory_bonuses, f, indent=2, ensure_ascii=False)
        print(f"✓ Saved bonuses for all {len(self.territory_bonuses)} territories")
        return True

    # ========================================
    # TERRITORY HELPER METHODS
    # ========================================

    def get_current_territory(self):
        if self.current_territory_index < len(self.territories):
            return self.territories[self.current_territory_index]
        return None

    def set_bonus(self, territory, bonus_type):
        """Set bonus type for a territory"""
        if bonus_type in BONUS_TYPES:
            self.territory_bonuses[territory] = bonus_type
            print(f"{territory}: {BONUS_TYPES[bonus_type]['name']} ({BONUS_TYPES[bonus_type]['value']})")

    def get_bonus_color(self, bonus_type):
        """Get color for displaying a bonus"""
        if bonus_type in BONUS_TYPES:
            return BONUS_TYPES[bonus_type]['color']
        return GRAY

    def get_statistics(self):
        """Calculate statistics about bonus distribution"""
        bonus_counts = {bt: 0 for bt in BONUS_TYPES.keys()}
        for bonus_type in self.territory_bonuses.values():
            if bonus_type in bonus_counts:
                bonus_counts[bonus_type] += 1

        # Count unassigned territories
        unassigned = len(self.territories) - len(self.territory_bonuses)

        return bonus_counts, unassigned


    # ========================================
    # DRAWING METHODS (WITH CAMERA TRANSFORMS)
    # ========================================

    def draw_territory_overlay(self, territory, color, alpha=100, outline=False):
        """Draw a colored overlay on a territory (with camera transformations)"""
        if territory not in map_data.TERRITORY_POLYGONS:
            return

        polygon = map_data.TERRITORY_POLYGONS[territory]
        
        # Create surface for the overlay
        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)

        # Transform polygon points from world to screen coordinates
        screen_points = [self.world_to_screen(point) for point in polygon]

        # Draw filled polygon
        pygame.draw.polygon(surface, (*color, alpha), screen_points)

        # Draw outline if requested
        if outline:
            pygame.draw.lines(surface, (*color, 255), True, screen_points, 3)

        self.screen.blit(surface, (0, 0))

    def draw_all_territories_by_bonus(self):
        """Draw all territories colored by their bonus type (with camera transformations)"""
        for territory, bonus_type in self.territory_bonuses.items():
            if territory in map_data.TERRITORY_POLYGONS:
                color = self.get_bonus_color(bonus_type)
                self.draw_territory_overlay(territory, color, alpha=60)

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

        # Draw all territories colored by bonus
        self.draw_all_territories_by_bonus()

        # Highlight current territory
        territory = self.get_current_territory()
        if territory:
            current_bonus = self.territory_bonuses.get(territory, None)
            if current_bonus:
                color = self.get_bonus_color(current_bonus)
            else:
                color = (255, 255, 255)  # White for unassigned
            self.draw_territory_overlay(territory, color, alpha=120, outline=True)

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

    def draw_ui(self):
        """Draw UI panel"""
        # Draw camera info at top of screen
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

        # Title
        title = self.large_font.render("Territorial Bonuses", True, BLACK)
        self.screen.blit(title, (ui_x, ui_y))
        ui_y += 45

        # Current territory
        territory = self.get_current_territory()
        if territory:
            # Territory name (wrapped if needed)
            name_lines = self.wrap_text(territory, self.font, UI_PANEL_WIDTH - 30)
            for line in name_lines:
                text = self.font.render(line, True, (0, 0, 200))
                self.screen.blit(text, (ui_x, ui_y))
                ui_y += 26

            ui_y += 10

            # Progress
            progress_text = self.font.render(f"Territory {self.current_territory_index + 1}/{len(self.territories)}", True, BLACK)
            self.screen.blit(progress_text, (ui_x, ui_y))
            ui_y += 28

            # Current bonus
            current_bonus = self.territory_bonuses.get(territory, None)
            if current_bonus:
                bonus_info = BONUS_TYPES[current_bonus]
                bonus_color = bonus_info['color']
                bonus_text = self.font.render(f"{bonus_info['name']}", True, bonus_color)
                self.screen.blit(bonus_text, (ui_x, ui_y))
                ui_y += 24
                value_text = self.small_font.render(f"({bonus_info['value']})", True, BLACK)
                self.screen.blit(value_text, (ui_x, ui_y))
                ui_y += 30
            else:
                unassigned_text = self.font.render("No bonus assigned", True, (200, 0, 0))
                self.screen.blit(unassigned_text, (ui_x, ui_y))
                ui_y += 35

        ui_y += 5

        # Bonus type buttons
        guide_text = self.font.render("=== ASSIGN BONUS ===", True, BLACK)
        self.screen.blit(guide_text, (ui_x, ui_y))
        ui_y += 30

        # Draw bonus buttons (9 total)
        for bonus_type in BONUS_ORDER:
            bonus_info = BONUS_TYPES[bonus_type]
            color = bonus_info['color']

            # Button number
            key_text = self.small_font.render(f"{bonus_info['key']} -", True, BLACK)
            self.screen.blit(key_text, (ui_x, ui_y))

            # Bonus name with color
            name_text = self.small_font.render(f"{bonus_info['name']}", True, color)
            self.screen.blit(name_text, (ui_x + 25, ui_y))

            # Value
            value_text = self.small_font.render(f"({bonus_info['value']})", True, (100, 100, 100))
            self.screen.blit(value_text, (ui_x + 185, ui_y))

            ui_y += 22

        ui_y += 15

        # Controls
        controls = [
            "=== CAMERA ===",
            "Middle-Drag: Pan",
            "Mouse Wheel: Zoom",
            "Arrow Keys: Pan",
            "Edge scroll: Auto-pan",
            "",
            "=== CONTROLS ===",
            "1-9: Assign bonus",
            "N/P: Navigate",
            "S: Save to file",
            "Q: Quit"
        ]

        for line in controls:
            if line.startswith("==="):
                text = self.font.render(line, True, BLACK)
            elif line == "":
                ui_y += 5
                continue
            else:
                text = self.small_font.render(line, True, BLACK)
            self.screen.blit(text, (ui_x, ui_y))
            ui_y += 20 if line.startswith("===") else 18

        ui_y += 15

        # Statistics
        stats_title = self.font.render("=== STATISTICS ===", True, BLACK)
        self.screen.blit(stats_title, (ui_x, ui_y))
        ui_y += 25

        bonus_counts, unassigned = self.get_statistics()

        # Show unassigned count prominently
        if unassigned > 0:
            unassigned_text = self.small_font.render(f"Unassigned: {unassigned}", True, (200, 0, 0))
            self.screen.blit(unassigned_text, (ui_x, ui_y))
            ui_y += 20
        else:
            complete_text = self.small_font.render("All territories assigned!", True, (0, 150, 0))
            self.screen.blit(complete_text, (ui_x, ui_y))
            ui_y += 20

        # Show top 3 bonus counts
        sorted_counts = sorted(bonus_counts.items(), key=lambda x: x[1], reverse=True)
        for bonus_type, count in sorted_counts[:3]:
            if count > 0:
                bonus_name = BONUS_TYPES[bonus_type]['name']
                count_text = self.small_font.render(f"{bonus_name}: {count}", True, (80, 80, 80))
                self.screen.blit(count_text, (ui_x, ui_y))
                ui_y += 18

    def handle_keypress(self, key):
        """Handle keyboard input"""
        territory = self.get_current_territory()
        if not territory:
            return True

        # Navigate with N/P keys (arrows now control camera)
        if key == pygame.K_n:  # Next territory
            self.current_territory_index = (self.current_territory_index + 1) % len(self.territories)
        elif key == pygame.K_p:  # Previous territory
            self.current_territory_index = (self.current_territory_index - 1) % len(self.territories)

        # Assign bonuses with number keys
        elif key == pygame.K_1:
            self.set_bonus(territory, 'income_bonus')
        elif key == pygame.K_2:
            self.set_bonus(territory, 'tech_cost')
        elif key == pygame.K_3:
            self.set_bonus(territory, 'unit_cost')
        elif key == pygame.K_4:
            self.set_bonus(territory, 'hero_cost')
        elif key == pygame.K_5:
            self.set_bonus(territory, 'pikeman_str')
        elif key == pygame.K_6:
            self.set_bonus(territory, 'archer_str')
        elif key == pygame.K_7:
            self.set_bonus(territory, 'swordsman_str')
        elif key == pygame.K_8:
            self.set_bonus(territory, 'cavalry_str')
        elif key == pygame.K_9:
            self.set_bonus(territory, 'building_cost')

        # Save with S key
        elif key == pygame.K_s:
            if self.save_bonus_data():
                print("✓ Successfully saved all territorial bonuses!")
            else:
                print("✗ Cannot save - some territories still unassigned")

        # Quit with Q key
        elif key == pygame.K_q:
            return False

        return True

    # ========================================
    # MAIN LOOP
    # ========================================

    def run(self):
        """Main loop"""
        running = True

        while running:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    running = self.handle_keypress(event.key)

                elif event.type == pygame.MOUSEMOTION:
                    # Camera drag
                    self.handle_camera_drag(event.pos, pygame.mouse.get_pressed())

                elif event.type == pygame.MOUSEWHEEL:
                    # Camera zoom
                    self.handle_camera_zoom(event.y)

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

if __name__ == "__main__":
    print("=== Territorial Bonus Assignment Tool ===")
    print("This tool helps you assign bonuses to each territory")
    print()
    print("Camera Controls:")
    print("- Middle-click drag to pan the map")
    print("- Mouse wheel to zoom in/out")
    print("- WASD keys to pan the map")
    print("- Move mouse to edges for auto-scrolling")
    print()
    print("Controls:")
    print("- Arrow keys to navigate between territories")
    print("- Number keys (1-9) to assign bonuses")
    print("- Press \"S\" to save all bonuses to file")
    print()
    print("Loading...")
    
    tool = BonusTool()
    tool.run()
