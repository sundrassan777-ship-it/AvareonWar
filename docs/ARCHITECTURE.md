# Avareon War - Architecture Guide

**Purpose:** Understand the system architecture and design patterns

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Main Game Loop                       │
│                         (main.py)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Planning │→ │  Orders  │→ │ Battles  │→ │  Income  │   │
│  │  Phase   │  │  Phase   │  │  Phase   │  │  Phase   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                           ↓
         ┌─────────────────────────────────────┐
         │        Game State                    │
         │     (game_state.py)                  │
         │  - Territory ownership               │
         │  - Army positions                    │
         │  - Building queues                   │
         │  - Movement orders                   │
         │  - Battle resolution                 │
         └─────────────────────────────────────┘
                ↓                    ↓
    ┌──────────────────┐   ┌──────────────────┐
    │  Input Systems   │   │ Rendering Systems│
    ├──────────────────┤   ├──────────────────┤
    │ - Mouse Handler  │   │ - Map Renderer   │
    │ - Keyboard       │   │ - UI Renderer    │
    │ - Camera         │   │ - Panel Renderer │
    └──────────────────┘   └──────────────────┘
```

---

## 🎯 Core Design Principles

### **1. Separation of Concerns**

**Game Logic** (game_state.py):
- All game rules and state
- No rendering code
- No input handling
- Pure logic and data

**Rendering** (rendering/):
- Only draws to screen
- Reads game state
- Doesn't modify state
- Pure presentation

**Input** (input/, ui/):
- Captures user input
- Translates to game actions
- Routes clicks to handlers
- No game logic

### **2. Single Responsibility**

Each module has ONE clear purpose:
- `game_state.py` - Game rules and state
- `map_renderer.py` - Map visualization
- `ui_renderer.py` - UI overlays
- `mouse_handler.py` - Mouse input routing
- `camera.py` - Viewport management

### **3. Data-Driven Design**

Game data in JSON files:
- `territory_polygons.json` - Map geometry
- `economic_data.json` - Territory economies
- `plots.json` - Building plot locations

Benefits:
- Easy to modify without code changes
- Tools can edit data files
- Clear separation of data/logic

---

## 📦 Module Organization

### **Tier 1: Core Systems**

**main.py** (5,309 lines)
- Game loop orchestration
- Phase management
- Window management
- Top-level coordination

**game_state.py** (1,732 lines)
- Territory ownership
- Army management
- Building queues
- Order execution
- Battle resolution
- Economic calculations

### **Tier 2: Subsystems**

**Rendering** (rendering/):
- `map_renderer.py` (992 lines) - Map drawing
- `ui_renderer.py` (1,236 lines) - UI overlays
- `panel_renderer.py` - Panel coordination
- `helpers.py` (755 lines) - Drawing utilities

**Input** (input/, ui/):
- `mouse_handler.py` (192 lines) - Click routing
- `keyboard_handler.py` - Key handling
- `camera.py` - Viewport control

**Configuration** (config/):
- `constants.py` - Game constants
- `colors.py` - Color definitions

**UI Systems** (ui/):
- `scaler.py` - Dynamic UI scaling

### **Tier 3: Tools & Data**

**Tools** (tools/):
- Map editors
- Data editors
- Development utilities

**Data** (data/):
- JSON data files
- Map definitions

---

## 🔄 Data Flow

### **Input → Logic → Rendering**

```
User Input
    ↓
Mouse/Keyboard Handler
    ↓
Game Method Called
    ↓
Game State Modified
    ↓
Render Loop Draws State
    ↓
Screen Updated
```

**Example: Moving an Army**

1. User clicks army → clicks destination
2. MouseHandler routes click to `handle_map_click()`
3. Game validates move, creates MovementOrder
4. Order stored in `game_state.movement_orders`
5. Next frame, MapRenderer draws arrow
6. User clicks "End Turn"
7. Orders phase executes movement
8. Game state updates army position
9. MapRenderer draws army in new location

---

## 🎮 Game Loop Architecture

### **Main Loop Structure:**

```python
while running:
    # 1. Handle Events
    for event in pygame.event.get():
        handle_input(event)
    
    # 2. Update State (if needed)
    update_game_state()
    
    # 3. Render
    draw_map()
    draw_ui()
    draw_panels()
    
    # 4. Display
    pygame.display.flip()
    clock.tick(60)  # 60 FPS
```

### **Phase Management:**

```python
if current_phase == 'planning':
    # Allow user to give orders
    handle_planning_input()
    
elif current_phase == 'orders':
    # Execute orders
    execute_movement_orders()
    execute_building_orders()
    
elif current_phase == 'battles':
    # Resolve battles
    resolve_all_battles()
    
elif current_phase == 'income':
    # Collect income
    collect_income()
    advance_turn()
```

---

## 🗺️ Rendering Architecture

### **Three-Layer Rendering:**

**Layer 1: Map** (map_renderer.py)
- Territory fills
- Territory borders
- Army circles
- Building plots
- Movement arrows
- Battle markers

**Layer 2: UI Overlays** (ui_renderer.py)
- Top panel (menu, stats)
- Game menu modal
- Options menu
- Battle popup
- Chat input

**Layer 3: Panels** (panel_renderer.py)
- Bottom UI (buttons)
- Right sidebar (tabs, content)
- Territory info panel

### **Coordinate Systems:**

**Screen Coordinates:**
- (0, 0) = top-left
- Used for UI elements
- Fixed positions

**World Coordinates:**
- (0, 0) = top-left of map
- Used for territories/armies
- Affected by camera

**Camera Transformation:**
```python
screen_x = (world_x - camera.x) * zoom
screen_y = (world_y - camera.y) * zoom + TOP_PANEL_HEIGHT
```

---

## 🖱️ Input Architecture

### **Priority-Based Click Handling:**

MouseHandler routes clicks by priority:

```
Priority 1: Modals (battle popup, menus)
Priority 2: Top panel (menu button)
Priority 3: Territory info panel
Priority 4: Sidebar tabs
Priority 5: Sidebar content
Priority 6: Bottom UI
Priority 7: Map (territories, armies)
```

Higher priority = checked first.

### **Click Flow:**

```python
def handle_click(pos):
    # Check highest priority first
    if battle_popup_visible:
        return handle_battle_popup_click(pos)
    
    if game_menu_visible:
        return handle_game_menu_click(pos)
    
    if pos in top_panel:
        return handle_top_panel_click(pos)
    
    # ... continue down priority list
    
    # Lowest priority: map
    return handle_map_click(pos)
```

---

## 📊 State Management

### **Single Source of Truth:**

All game state in `game_state.py`:

```python
class GameState:
    # Territory state
    territory_owners: dict[str, int]
    territory_armies: dict[str, int]
    
    # Building state
    completed_buildings: dict[str, dict]
    building_queue: dict[str, list]
    
    # Order state
    movement_orders: list[MovementOrder]
    
    # Economic state
    player_gold: dict[int, int]
    
    # Phase state
    current_phase: str
    turn_number: int
```

### **State Modification Rules:**

1. **Only game_state.py modifies state**
2. **UI only reads state**
3. **Input calls game methods**
4. **Rendering never changes state**

**Bad:**
```python
# In renderer:
game_state.territory_owners[terr] = player  # ❌ NO!
```

**Good:**
```python
# In game method:
def conquer_territory(self, territory, player):
    self.game_state.territory_owners[territory] = player  # ✅ YES!
```

---

## 🏢 Building System Architecture

### **Building Lifecycle:**

```
1. User clicks plot
   ↓
2. Building menu opens
   ↓
3. User selects building type
   ↓
4. Building added to queue
   ↓
5. Each turn: construction_turns -= 1
   ↓
6. When construction_turns == 0:
   ↓
7. Move to completed_buildings
   ↓
8. Start providing benefits
```

### **Building Storage:**

```python
# Under construction:
building_queue[territory] = [
    {
        'type': 'Farm',
        'plot_id': 'A1',
        'construction_turns': 2
    }
]

# Completed:
completed_buildings[territory] = {
    'A1': {
        'type': 'Farm',
        'level': 1
    }
}
```

---

## ⚔️ Battle System Architecture

### **Battle Flow:**

```
1. Army moves into enemy territory
   ↓
2. Battle scheduled (pending_battles)
   ↓
3. Battles phase begins
   ↓
4. User clicks battle marker
   ↓
5. Battle popup shows participants
   ↓
6. User clicks "Resolve"
   ↓
7. Calculate combat:
   - Base strength
   - Terrain modifiers
   - Keep bonuses
   - Composition bonuses
   ↓
8. Determine winner
   ↓
9. Apply casualties
   ↓
10. Update territory ownership
```

### **Battle Calculation:**

```python
def resolve_battle(attacker, defender, territory):
    # Base strength
    attacker_strength = calculate_strength(attacker)
    defender_strength = calculate_strength(defender)
    
    # Terrain modifier
    defender_strength *= get_terrain_modifier(territory)
    
    # Keep bonus
    if has_keep(territory):
        defender_strength *= 1.5
    
    # Determine winner
    if attacker_strength > defender_strength:
        winner = attacker
    else:
        winner = defender
    
    # Calculate casualties
    casualties = calculate_casualties(...)
    
    return BattleResult(winner, casualties, ...)
```

---

## 💰 Economic System Architecture

### **Income Calculation:**

```python
def calculate_player_income(player):
    income = 0
    
    for territory in owned_territories(player):
        # Base income
        income += get_base_income(territory)
        
        # Building bonuses
        for building in territory_buildings(territory):
            if building.type == 'Farm':
                income += 2
            elif building.type == 'Mine':
                income += 3
    
    return income
```

### **Gold Management:**

```
Income Phase:
  1. Calculate income for each player
  2. Add to player_gold
  3. Display notification

Spending:
  - Buildings cost gold immediately
  - Recruitment costs gold immediately
  - Must have sufficient gold
```

---

## 🎨 UI Scaling Architecture

### **Dynamic Scaling:**

UI scales based on resolution:

```python
class UIConstants:
    @staticmethod
    def update_for_resolution(width, height):
        UIConstants.SIDEBAR_WIDTH = int(width * 0.18)
        UIConstants.BOTTOM_UI_HEIGHT = int(height * 0.12)
        # etc.
```

### **Layout Values:**

**Static** (in constants.py):
- Colors
- Ratios
- Fixed sizes

**Dynamic** (calculated at runtime):
- Window dimensions
- Panel heights
- UI element positions

---

## 🔧 Tool Architecture

### **Development Tools:**

**Plot Tool** (plot_tool.py):
- Visual plot placement
- Saves to plots.json
- Real-time preview

**Economic Tool** (economic_tool.py):
- Edit territory incomes
- Edit terrain types
- Saves to economic_data.json

**Polygon Tool** (polygon_tool.py):
- Edit territory shapes
- Saves to territory_polygons.json

**Adjacency Tool** (adjacency_tool.py):
- Edit territory connections
- Graph visualization

---

## 🧩 Extension Points

### **Easy to Add:**

**New Building Type:**
1. Add to building types list
2. Add income calculation
3. Add to building menu
4. Done!

**New Unit Type:**
1. Add to unit types dict
2. Add to recruitment menu
3. Add to battle calculations
4. Done!

**New Territory:**
1. Add polygon to territory_polygons.json
2. Add economy to economic_data.json
3. Add plots to plots.json
4. Done!

### **Harder to Add:**

**AI Players:**
- Need decision-making system
- Territory evaluation
- Strategic planning

**Multiplayer:**
- Network code
- State synchronization
- Turn management

**Save/Load:**
- Serialization system
- File format design
- Compatibility handling

---

## 📐 Design Patterns Used

### **1. Model-View-Controller (MVC)**

- **Model:** game_state.py
- **View:** rendering/
- **Controller:** input/, main.py

### **2. Delegation Pattern**

Main.py delegates to specialized systems:
```python
def draw_territories(self):
    self.map_renderer.draw_territories()  # Delegates
```

### **3. Observer Pattern**

UI observes game state:
```python
# UI checks state each frame
if game_state.battle_popup_visible:
    draw_battle_popup()
```

### **4. Command Pattern**

Orders are commands:
```python
class MovementOrder:
    def execute(self):
        # Execute the order
```

### **5. State Pattern**

Game phases are states:
```python
if phase == 'planning':
    handle_planning()
elif phase == 'battles':
    handle_battles()
```

---

## 🔒 Invariants

### **Critical Rules:**

1. **Territory ownership is always valid**
   - Every territory has exactly one owner
   - Owner is a valid player number

2. **Army counts are non-negative**
   - Armies >= 0
   - Never negative

3. **Building queue is valid**
   - All plot IDs exist
   - No duplicate plots
   - Construction turns >= 0

4. **Orders are valid**
   - From/to territories exist
   - Territories are adjacent
   - Player owns source territory

5. **Gold is non-negative**
   - Player gold >= 0
   - Can't spend more than you have

---

## 🎯 Performance Considerations

### **Rendering Optimizations:**

1. **Map caching** - Scaled map cached
2. **Polygon caching** - Scaled polygons cached
3. **60 FPS cap** - Prevents excessive CPU use
4. **Dirty rectangles** - Could be added for efficiency

### **State Optimizations:**

1. **Dict lookups** - O(1) territory access
2. **List comprehensions** - Efficient filtering
3. **Lazy evaluation** - Calculate only when needed

### **Memory Management:**

- **Image caching** - Load images once
- **Font caching** - Create fonts once
- **Surface reuse** - Reuse temporary surfaces

---

## 📝 Code Conventions

### **Naming:**

- **Classes:** PascalCase (`GameState`, `MovementOrder`)
- **Functions:** snake_case (`calculate_income`, `draw_territory`)
- **Constants:** UPPER_CASE (`WINDOW_WIDTH`, `MAX_ARMIES`)
- **Private:** _underscore (`_helper_method`)

### **Organization:**

- **Imports** at top
- **Constants** after imports
- **Classes** in logical order
- **Methods** grouped by purpose

### **Documentation:**

- **Docstrings** for all public methods
- **Comments** for complex logic
- **Type hints** where helpful

---

**Last Updated:** January 5, 2026  
**Architecture Version:** Phase 4 Complete
