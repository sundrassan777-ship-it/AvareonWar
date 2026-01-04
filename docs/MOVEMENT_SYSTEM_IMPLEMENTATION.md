# Advanced Army Movement - Implementation Plan (Updated)

**Feature:** TIER 2B - Feature #17  
**Date:** December 28, 2024  
**Status:** 🚀 READY TO IMPLEMENT

---

## 🎯 Updated Requirements

### 1. Layout Adjustments
- **Map Area:** 70% of screen space (increased from 60%)
- **Bottom UI:** Smaller, more compact
- **Order Sidebar:** Unchanged (right side)

### 2. Future Camera Support
- **Zoom:** In/out capability
- **Pan:** Move around large maps
- **Code Structure:** Camera-ready from day 1

---

## 🗺️ Updated Layout Specification

### Screen Division (1400x900 example)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Top Bar (60px)                                                             ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┫
┃                                                          ┃                ┃
┃                                                          ┃  Order Sidebar ┃
┃                                                          ┃  (250px wide)  ┃
┃                                                          ┃                ┃
┃                   MAP AREA                               ┃  Full height   ┃
┃                   (70% of screen)                        ┃  from top bar  ┃
┃                   ~630px height                          ┃  to bottom     ┃
┃                   (1150px wide)                          ┃                ┃
┃                                                          ┃                ┃
┃                                                          ┃                ┃
┃                                                          ┃                ┃
┃                                                          ┃                ┃
┃                                                          ┃                ┃
┃                                                          ┃                ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━┫
┃ Action Log (150px height - compact)           │ End Turn Button          ┃
┃                                                │ (200x60px)               ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Top Bar:        60px  (4%)
Map Area:       630px (70%)
Bottom UI:      150px (17%)
Order Sidebar:  250px (from top to bottom)
Margins:        Remaining space

Total Height: 900px
```

---

## 🎥 Camera System Architecture

### Core Concept

**Separation of Coordinates:**
- **World Coordinates:** Absolute positions of territories (never change)
- **Screen Coordinates:** Where things are drawn (affected by camera)
- **Camera Transform:** Converts world → screen

### Camera State Variables

```python
class GameState:
    def __init__(self):
        # Existing fields...
        
        # NEW: Camera system
        self.camera_x = 0          # Camera offset X (world units)
        self.camera_y = 0          # Camera offset Y (world units)
        self.camera_zoom = 1.0     # Zoom level (1.0 = normal, 2.0 = 2x zoom)
        
        # Camera constraints
        self.min_zoom = 0.5        # Maximum zoom out
        self.max_zoom = 3.0        # Maximum zoom in
```

### Coordinate Conversion Functions

```python
def world_to_screen(self, world_x, world_y):
    """Convert world coordinates to screen coordinates"""
    # Apply zoom
    screen_x = world_x * self.camera_zoom
    screen_y = world_y * self.camera_zoom
    
    # Apply camera offset
    screen_x -= self.camera_x
    screen_y -= self.camera_y
    
    return (screen_x, screen_y)

def screen_to_world(self, screen_x, screen_y):
    """Convert screen coordinates to world coordinates"""
    # Reverse camera offset
    world_x = screen_x + self.camera_x
    world_y = screen_y + self.camera_y
    
    # Reverse zoom
    world_x /= self.camera_zoom
    world_y /= self.camera_zoom
    
    return (world_x, world_y)
```

### Drawing with Camera

```python
# OLD WAY (camera-unaware):
def draw_territory(territory):
    x, y = territory.position
    pygame.draw.polygon(screen, color, points)

# NEW WAY (camera-aware):
def draw_territory(territory):
    # Convert world position to screen position
    world_x, world_y = territory.position
    screen_x, screen_y = self.world_to_screen(world_x, world_y)
    
    # Convert all polygon points
    screen_points = [self.world_to_screen(px, py) for px, py in points]
    
    pygame.draw.polygon(screen, color, screen_points)
```

### Click Detection with Camera

```python
# OLD WAY:
def handle_click(screen_x, screen_y):
    for territory in territories:
        if point_in_polygon((screen_x, screen_y), territory.polygon):
            return territory

# NEW WAY:
def handle_click(screen_x, screen_y):
    # Convert screen click to world coordinates
    world_x, world_y = self.screen_to_world(screen_x, screen_y)
    
    # Check against world coordinates
    for territory in territories:
        if point_in_polygon((world_x, world_y), territory.polygon):
            return territory
```

---

## 📐 Updated Map Dimensions

### Map Viewport

```python
# Map area rectangle
MAP_X = 0
MAP_Y = 60          # Below top bar
MAP_WIDTH = 1150    # Screen width - sidebar width
MAP_HEIGHT = 630    # 70% of (900 - 60 top bar - 150 bottom)

# Map viewport rect
MAP_RECT = pygame.Rect(MAP_X, MAP_Y, MAP_WIDTH, MAP_HEIGHT)
```

### Future Camera Controls

```python
# Mouse wheel zoom (future)
def handle_mouse_wheel(event):
    if event.y > 0:  # Scroll up
        self.camera_zoom = min(self.camera_zoom * 1.1, self.max_zoom)
    else:  # Scroll down
        self.camera_zoom = max(self.camera_zoom / 1.1, self.min_zoom)

# Click-drag pan (future)
def handle_mouse_drag(dx, dy):
    self.camera_x += dx / self.camera_zoom
    self.camera_y += dy / self.camera_zoom
```

---

## 🔧 Implementation Strategy

### Phase 1: Core Order System (2-3 hours)

**Camera Considerations:**
- ✅ Store territory positions in world coordinates
- ✅ Implement world_to_screen() and screen_to_world()
- ✅ Use camera transform for all drawing
- ✅ Use reverse transform for all clicks

**Code Structure:**

```python
# In game_state.py
class GameState:
    def __init__(self):
        # Camera (start at 1.0 zoom, 0 offset)
        self.camera_x = 0
        self.camera_y = 0
        self.camera_zoom = 1.0
        
        # Order system
        self.selected_army = None
        self.movement_orders = []
        self.turn_phase = 'planning'
    
    def world_to_screen(self, world_x, world_y):
        """Convert world coords to screen coords"""
        screen_x = (world_x * self.camera_zoom) - self.camera_x
        screen_y = (world_y * self.camera_zoom) - self.camera_y
        return (int(screen_x), int(screen_y))
    
    def screen_to_world(self, screen_x, screen_y):
        """Convert screen coords to world coords"""
        world_x = (screen_x + self.camera_x) / self.camera_zoom
        world_y = (screen_y + self.camera_y) / self.camera_zoom
        return (world_x, world_y)
```

```python
# In main.py
def handle_left_click(self, pos):
    screen_x, screen_y = pos
    
    # Convert to world coordinates
    world_x, world_y = self.game_state.screen_to_world(screen_x, screen_y)
    
    # Check which territory clicked (using world coords)
    clicked_territory = self.get_territory_at_world_pos(world_x, world_y)
    
    if clicked_territory:
        self.game_state.select_army(clicked_territory)

def draw_territories(self):
    for territory_name, polygon_points in map_data.territories.items():
        # Convert each point to screen coordinates
        screen_points = [
            self.game_state.world_to_screen(wx, wy)
            for wx, wy in polygon_points
        ]
        
        # Draw using screen coordinates
        pygame.draw.polygon(self.screen, color, screen_points)
```

**Deliverable:** 
- Order system works
- Camera transform in place
- Future-proof for zoom/pan

---

### Phase 2: Visual Indicators (1-2 hours)

**Camera Considerations:**
- ✅ Arrows use world coordinates for endpoints
- ✅ Convert to screen for drawing
- ✅ Arrow thickness independent of zoom (optional)

**Arrow Drawing with Camera:**

```python
def draw_movement_arrows(self):
    for order in self.game_state.movement_orders:
        # Get world positions of territory centers
        from_world = map_data.get_territory_center(order.from_territory)
        to_world = map_data.get_territory_center(order.to_territory)
        
        # Convert to screen coordinates
        from_screen = self.game_state.world_to_screen(*from_world)
        to_screen = self.game_state.world_to_screen(*to_world)
        
        # Draw arrow (screen coordinates)
        self.draw_arrow(from_screen, to_screen, order.army_count)
```

**Army Selection with Camera:**

```python
def draw_army_number(self, territory):
    # Get world position
    world_center = map_data.get_territory_center(territory)
    
    # Convert to screen
    screen_x, screen_y = self.game_state.world_to_screen(*world_center)
    
    # Draw number at screen position
    text = self.font.render(str(armies), True, WHITE)
    text_rect = text.get_rect(center=(screen_x, screen_y))
    self.screen.blit(text, text_rect)
```

**Deliverable:**
- Arrows transform correctly
- Selection works with camera
- All visual elements camera-aware

---

### Phase 3: Order Execution (2 hours)

**Camera Considerations:**
- ✅ Execution logic is camera-independent (uses world data)
- ✅ Only display is affected by camera
- ✅ No special camera handling needed in this phase

**Implementation:**
```python
def execute_all_orders(self):
    # Logic works in world space (territory names, army counts)
    # No camera transforms needed
    for order in self.movement_orders:
        # Process order (camera-independent)
        pass
```

**Deliverable:**
- Order execution works
- Battle creation works
- Phase transitions work

---

### Phase 4: Battle Resolution UI (2 hours)

**Camera Considerations:**
- ✅ Battle markers use world positions
- ✅ Popup is screen-space (not affected by camera)
- ✅ Territory highlighting uses camera transform

**Battle Marker Drawing:**

```python
def draw_battle_markers(self):
    for battle in self.game_state.pending_battles:
        # Get world position of territory center
        world_x, world_y = map_data.get_territory_center(battle.territory)
        
        # Convert to screen
        screen_x, screen_y = self.game_state.world_to_screen(world_x, world_y)
        
        # Draw crossed swords at screen position
        self.draw_crossed_swords((screen_x, screen_y))
```

**Battle Popup (Screen Space):**

```python
def show_battle_popup(self, battle):
    # Popup always centered on screen (not affected by camera)
    popup_x = WINDOW_WIDTH // 2 - 250  # Center
    popup_y = WINDOW_HEIGHT // 2 - 225
    
    # Draw popup at fixed screen position
    pygame.draw.rect(self.screen, color, (popup_x, popup_y, 500, 450))
```

**Deliverable:**
- Battle markers transform correctly
- Popup always visible on screen
- Battle resolution works

---

### Phase 5: Polish & Testing (1-2 hours)

**Camera Considerations:**
- ✅ Test at different zoom levels (even though zoom = 1.0 for now)
- ✅ Verify all coordinates use correct system
- ✅ Ensure nothing breaks when camera offset changes

**Testing Checklist:**
```python
# Test with simulated zoom
self.camera_zoom = 1.5  # Test at 1.5x zoom
# ... test all features ...

self.camera_zoom = 0.7  # Test at 0.7x zoom  
# ... test all features ...

# Test with simulated pan
self.camera_x = 100
self.camera_y = 50
# ... test all features ...
```

**Deliverable:**
- All features work with camera system
- Code ready for future zoom/pan
- No camera-related bugs

---

## 📏 Updated UI Element Sizes

### Compact Bottom Bar

```python
# Action Log (left side)
ACTION_LOG_X = 0
ACTION_LOG_Y = 690  # MAP_Y + MAP_HEIGHT
ACTION_LOG_WIDTH = 750
ACTION_LOG_HEIGHT = 150  # Reduced from 200

# End Turn Button (right side)
END_TURN_X = 800
END_TURN_Y = 720  # Centered vertically in bottom bar
END_TURN_WIDTH = 200  # Reduced from 250
END_TURN_HEIGHT = 60  # Reduced from 80

# Font sizes (slightly smaller)
LOG_FONT_SIZE = 14   # Was 16
BUTTON_FONT_SIZE = 20  # Was 24
```

### Order Sidebar (Unchanged)

```python
SIDEBAR_X = 1150  # WINDOW_WIDTH - SIDEBAR_WIDTH
SIDEBAR_Y = 60    # Below top bar
SIDEBAR_WIDTH = 250
SIDEBAR_HEIGHT = 840  # Full height from top to bottom
```

---

## 🎨 Camera-Aware Drawing Checklist

**Must Use Camera Transform:**
- [x] Territory polygons
- [x] Territory centers (army numbers)
- [x] Movement arrows
- [x] Battle markers (crossed swords)
- [x] Selection glow effects
- [x] Adjacent territory highlights

**Always Screen Space (No Transform):**
- [x] Top bar (player info, gold, turn)
- [x] Order sidebar
- [x] Action log
- [x] End Turn button
- [x] Battle popup window
- [x] UI borders and backgrounds

**Click Detection:**
- [x] Territory clicks: Use screen_to_world()
- [x] Army number clicks: Use screen_to_world()
- [x] UI buttons: Use screen coordinates directly
- [x] Order sidebar: Use screen coordinates directly

---

## 🔍 Camera System Benefits

### Current (Phase 1-5)
- Camera at zoom = 1.0, offset = (0, 0)
- All code camera-aware
- No visible difference to player
- But: Future-proof!

### Future (After Phase 5)
- Can add zoom with mouse wheel
- Can add pan with click-drag
- Minimal code changes needed
- Just enable the controls!

---

## 💡 Implementation Tips

### Tip 1: Territory Center Calculation

**Add to map_data.py:**
```python
def get_territory_center(territory_name):
    """Get the center point of a territory"""
    points = territories[territory_name]
    
    # Calculate centroid
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    
    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)
    
    return (center_x, center_y)
```

### Tip 2: Debug Camera Visualization

**Add temporary debug display:**
```python
def draw_camera_debug(self):
    # Show camera info (top-left corner)
    debug_text = f"Zoom: {self.camera_zoom:.2f} | Offset: ({self.camera_x}, {self.camera_y})"
    text = self.debug_font.render(debug_text, True, (255, 255, 0))
    self.screen.blit(text, (10, 10))
```

### Tip 3: Safe Division for Camera

```python
def screen_to_world(self, screen_x, screen_y):
    # Protect against division by zero
    if self.camera_zoom == 0:
        self.camera_zoom = 0.01
    
    world_x = (screen_x + self.camera_x) / self.camera_zoom
    world_y = (screen_y + self.camera_y) / self.camera_zoom
    return (world_x, world_y)
```

### Tip 4: Maintain Map Bounds

```python
def clamp_camera(self):
    """Keep camera within map bounds"""
    # Define map world bounds
    min_x, min_y = 0, 0
    max_x, max_y = 1200, 800  # Your map size
    
    # Clamp camera position
    self.camera_x = max(min_x, min(self.camera_x, max_x))
    self.camera_y = max(min_y, min(self.camera_y, max_y))
```

---

## 🎯 Phase 1 Implementation Plan

### Step 1: Add Camera to GameState (10 min)

```python
# In game_state.py __init__
self.camera_x = 0
self.camera_y = 0
self.camera_zoom = 1.0
```

### Step 2: Add Coordinate Conversion (15 min)

```python
# In game_state.py
def world_to_screen(self, world_x, world_y):
    screen_x = (world_x * self.camera_zoom) - self.camera_x
    screen_y = (world_y * self.camera_zoom) - self.camera_y
    return (int(screen_x), int(screen_y))

def screen_to_world(self, screen_x, screen_y):
    if self.camera_zoom == 0:
        self.camera_zoom = 0.01
    world_x = (screen_x + self.camera_x) / self.camera_zoom
    world_y = (screen_y + self.camera_y) / self.camera_zoom
    return (world_x, world_y)
```

### Step 3: Add Territory Center Helper (15 min)

```python
# In map_data.py
def get_territory_center(territory_name):
    """Calculate center point of territory polygon"""
    points = territories[territory_name]
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)
    return (center_x, center_y)
```

### Step 4: Update Territory Drawing (20 min)

```python
# In main.py
def draw_territory(self, territory_name):
    polygon_points = map_data.territories[territory_name]
    
    # Convert all points to screen coordinates
    screen_points = [
        self.game_state.world_to_screen(wx, wy)
        for wx, wy in polygon_points
    ]
    
    # Draw polygon
    pygame.draw.polygon(self.screen, color, screen_points)
```

### Step 5: Update Click Detection (20 min)

```python
# In main.py
def handle_left_click(self, pos):
    screen_x, screen_y = pos
    
    # Skip if clicked on UI
    if self.is_ui_element(screen_x, screen_y):
        return
    
    # Convert to world coordinates
    world_x, world_y = self.game_state.screen_to_world(screen_x, screen_y)
    
    # Find clicked territory
    for territory_name, polygon in map_data.territories.items():
        if point_in_polygon((world_x, world_y), polygon):
            # Handle territory click
            break
```

### Step 6: Add Order System (60 min)

```python
# In game_state.py
class MovementOrder:
    def __init__(self, from_territory, to_territory, army_count, player):
        self.from_territory = from_territory
        self.to_territory = to_territory
        self.army_count = army_count
        self.player = player

# Add to GameState
self.selected_army = None  # (territory_name, army_count)
self.movement_orders = []
self.turn_phase = 'planning'

def select_army(self, territory):
    """Select an army for movement"""
    # Validate ownership and unmoved armies
    # Set self.selected_army
    
def add_movement_order(self, from_territory, to_territory):
    """Create a new movement order"""
    # Validate order
    # Create MovementOrder object
    # Add to self.movement_orders
```

### Step 7: Test Phase 1 (20 min)

```
- Click army numbers (camera transform works)
- Right-click to create orders (transforms work)
- Orders stored correctly
- No visual feedback yet (that's Phase 2)
```

---

## 📊 Updated Progress Tracker

### Session 1: Phase 1 - Core + Camera (2-3 hours)
- [ ] Camera system added
- [ ] Coordinate conversion working
- [ ] Territory drawing camera-aware
- [ ] Click detection camera-aware
- [ ] Order system implemented
- [ ] Camera-ready for future zoom/pan

### Session 2: Phase 2 - Visuals (1-2 hours)
- [ ] Movement arrows (camera-aware)
- [ ] Selection glow (camera-aware)
- [ ] Order sidebar (screen-space)
- [ ] End Turn button (screen-space)

### Session 3: Phase 3 - Execution (2 hours)
- [ ] Execute all orders
- [ ] Auto-capture logic
- [ ] Battle detection
- [ ] Phase transitions

### Session 4: Phase 4 - Battles (2 hours)
- [ ] Battle markers (camera-aware)
- [ ] Battle popup (screen-space)
- [ ] Battle resolution
- [ ] Result display

### Session 5: Phase 5 - Polish (1-2 hours)
- [ ] Order cancellation
- [ ] Edge case testing
- [ ] Camera system testing
- [ ] Final polish

---

## 🚀 Ready to Start!

**Adjusted for your requirements:**
- ✅ Map takes 70% of space
- ✅ Bottom UI more compact
- ✅ Camera system from day 1
- ✅ Future zoom/pan ready
- ✅ Clean coordinate separation

**When you're ready, say:**
*"Let's implement Phase 1!"*

And we'll start building! 🎮

---

**Last Updated:** December 28, 2024  
**Status:** ✅ Ready for Implementation  
**Camera Support:** ✅ Built-in from start  
**Map Size:** ✅ 70% of screen
