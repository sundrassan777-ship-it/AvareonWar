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
         │     (game_state/ package)            │
         │  - Territory ownership               │
         │  - Garrison system                   │
         │  - Building management               │
         │  - Movement orders                   │
         │  - Battle resolution                 │
         │  - Hero system                       │
         │  - Economy and diplomacy             │
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

**Game Logic** (game_state/ package):
- All game rules and state (8 files, mixin decomposition)
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
- `game_state/` - Game rules and state (mixin package)
- `map_renderer.py` - Map visualization
- `ui_renderer.py` - UI overlays
- `mouse_handler.py` - Mouse input routing
- `camera_handler.py` - Viewport management

### **3. Data-Driven Design**

Game data in JSON files (project root directory):
- `territory_polygons.json` - Map geometry
- `economic_data.json` - Territory economies
- `plots.json` - Building plot locations
- `territory_bonuses.json` - Territory bonus assignments
- `campaign_data.json` - Campaign mission text data
- `cutscene_data.json` - Cutscene definitions

Benefits:
- Easy to modify without code changes
- Tools can edit data files (Plot_Tool, Economic_Tool, Polygon_Tool, etc.)
- Clear separation of data/logic

---

## 📦 Module Organization

### **Tier 1: Core Systems**

**main.py** (~13,000 lines)
- Game loop orchestration
- Phase management
- Window management
- Event handling
- Top-level coordination

**game_state/** (~8,605 lines across 8 files)
- `__init__.py` - GameState class, turn management, coordinates, chat, diplomacy
- `data_definitions.py` - HERO_TYPES, BUILDING_TYPES, technologies, BONUS_TYPES
- `garrison.py` - GarrisonMixin: multi-garrison system, legacy sync
- `heroes.py` - HeroMixin: training, abilities, queries
- `buildings.py` - BuildingMixin: construction, training, upgrades, tech
- `economy.py` - EconomyMixin: income, costs, taxation, bonuses
- `military.py` - MilitaryMixin: orders, battles, movement, casualties
- `victory.py` - VictoryMixin: victory checks, elimination

### **Tier 2: Subsystems**

**Rendering** (rendering/):
- `map_renderer.py` (~3,690 lines) - Map drawing, territory overlays, plots, arrows, battle markers
- `ui_renderer.py` (~2,553 lines) - UI panels, buttons, info displays
- `panel_renderer.py` - Panel layout coordination
- `helpers.py` (755 lines) - Drawing utilities

**Input** (input/):
- `mouse_handler.py` (192 lines) - Click routing
- `keyboard_handler.py` - Key handling
- `camera_handler.py` - Camera/viewport management

**Configuration** (config/):
- `constants.py` - Game constants (window, colors, timing, camera)
- `font_manager.py` - Font loading and management

**UI Systems** (ui/):
- `scaler.py` - Dynamic UI scaling
- `effects/` - 9 effect modules (battle, sparkles, turn announcements, hero abilities, etc.)

**AI System** (5 files):
- `ai_player.py` - Main AI controller
- `ai_strategy.py` - Strategic evaluation, threat detection
- `ai_economy.py` - Building decisions, tech upgrades
- `ai_military.py` - Combat, troop movement, tactics
- `ai_hero.py` - Hero training and abilities

**Networking** (network/):
- `server.py` - TCP server for multiplayer (up to 4 players)
- `client.py` - Network client
- `protocol.py` - Message serialization
- `message_queue.py` - Thread-safe queue
- `upnp.py` - UPnP port forwarding and public IP detection

**Simultaneous Mode** (simultaneous/):
- `sim_state.py` - SimultaneousGameState wrapper
- `sim_phase_manager.py` - Phase transitions
- `sim_conflict_resolver.py` - Crossing armies, battles
- `sim_alliance_handler.py` - Allied territory capture
- `sim_ai.py` - AI adapter for simultaneous mode

### **Tier 3: Tools & Data**

**Tools** (root + tools/):
- Plot_Tool.py, Economic_Tool.py, Polygon_Tool.py, Adjacency_Tool.py - Map/data editors
- Bonus_Tool.py, Campaign_Text_Tool.py, Cutscene_Tool.py - Content editors
- tools/stress_test_generator.py - Late-game scenario generator

**Data** (JSON files in project root):
- `territory_polygons.json` - Map geometry
- `economic_data.json` - Territory economy definitions
- `plots.json` - Building plot locations
- `territory_bonuses.json` - Territory bonus assignments
- `campaign_data.json` - Campaign mission text
- `cutscene_data.json` - Cutscene definitions

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
    clock.tick(80)  # 80 FPS
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

All game state in the `game_state/` package:

```python
class GameState(GarrisonMixin, HeroMixin, BuildingMixin,
                EconomyMixin, MilitaryMixin, VictoryMixin):
    # Core state attributes (game_state/__init__.py)
    self.territory_owners = {}     # {territory_name: player_index}
    self.player_gold = [0] * N     # list indexed by player (NOT dict)
    self.phase = 'setup'           # 'setup', 'playing', 'ended'
    self.turn_phase = 'planning'   # 'planning', etc.
    self.buildings = {}            # {territory: {plot_idx: building_type}}
    self.under_construction = {}   # {territory: {plot_idx: (type, turns_left)}}
    self.territory_garrisons = {}  # {territory: {garrison_id: {unit_type: count}}}
    self.armies = {}               # legacy counter (use get_territory_total_armies() instead)
    self.training_queue = {}       # {territory: {barracks_plot: [(type, turns_left)]}}
    self.movement_orders = []      # [MovementOrder objects]
    self.pending_battles = []      # [Battle objects]
    self.turn_number = 1
```

**Note:** The garrison system is authoritative for army counts. Always use
`get_territory_total_armies(territory)` instead of reading `self.armies[]` directly.

### **State Modification Rules:**

1. **Only game_state/ methods modify state**
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
4. Gold deducted, added to under_construction
   ↓
5. Each turn: turns_left decremented
   ↓
6. When turns_left == 0:
   ↓
7. Move to self.buildings (completed)
   ↓
8. Start providing benefits
```

### **Building Storage:**

```python
# Under construction:
self.under_construction[territory] = {
    plot_index: (building_type, turns_left)
    # e.g. {0: ('Farm', 1)}
}

# Completed:
self.buildings[territory] = {
    plot_index: building_type
    # e.g. {0: 'Farm', 1: 'Mine'}
}
```

---

## ⚔️ Battle System Architecture

### **Battle Flow:**

```
1. Army moves into enemy territory
   ↓
2. Battle scheduled (pending_battles list)
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
   - Unit counter system (composition)
   - Keep bonus (+2 effective armies)
   - Veterancy bonus (+15% per level)
   ↓
8. Determine winner
   ↓
9. Apply casualties (veterancy-aware priority)
   ↓
10. Update territory ownership
```

### **Battle Calculation:**

```python
def resolve_battle(self, battle_index):
    """Two-phase Keep battle or simple field battle.
    Defined in game_state/military.py. Called by index into self.battles list."""
    # Get battle participants from self.battles[battle_index]
    # Calculate effective strength per unit type with counter system:
    #   countered enemy type: 2.0x effectiveness
    #   countering enemy type: 0.5x effectiveness
    #   neutral matchup: 1.0x effectiveness
    # Keep bonus: +2 effective armies for defender (flat, not multiplier)
    # Veterancy: +15% effective strength per unit level
    # Winner = higher total effective strength
    # Casualties scaled by strength ratio
    # Casualty priority: lowest level dies first, then countered > neutral > advantaged
```

**Note:** `MovementOrder` is a simple data class (defined in `game_state/__init__.py`).
It has NO `execute()` method. Order execution is handled by `execute_all_orders()` in
`game_state/military.py`.

---

## 💰 Economic System Architecture

### **Income Calculation:**

```python
def calculate_player_income(player):
    income = 0

    for territory in owned_territories(player):
        # Base income (from economic_data.json, typically 5-20 per territory)
        income += get_base_income(territory)

        # Building bonuses (values from BUILDING_TYPES in data_definitions.py)
        for building in territory_buildings(territory):
            if building.type == 'Farm':
                income += 10       # Farm value = 10 gold
            elif building.type == 'Mine':
                income += 15       # Mine value = 15 gold
            # Square provides 1.5x multiplier on territory income

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

**Plot Tool** (Plot_Tool.py):
- Visual plot placement
- Saves to plots.json
- Real-time preview

**Economic Tool** (Economic_Tool.py):
- Edit territory incomes
- Edit terrain types
- Saves to economic_data.json

**Polygon Tool** (Polygon_Tool.py):
- Edit territory shapes
- Saves to territory_polygons.json

**Adjacency Tool** (Adjacency_Tool.py):
- Edit territory connections
- Graph visualization

**Bonus Tool** (Bonus_Tool.py):
- Edit territorial bonus assignments
- Saves to territory_bonuses.json

**Campaign Text Tool** (Campaign_Text_Tool.py):
- WYSIWYG editor for campaign mission text
- Saves to campaign_data.json

**Cutscene Tool** (Cutscene_Tool.py):
- Cutscene editor (camera rects, audio, subtitles)
- Saves to cutscene_data.json

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

### **Fully Implemented Systems:**

**AI Players** (5 files, fully operational):
- Multi-difficulty AI (Easy, Normal, Hard)
- Strategic evaluation, threat detection, ally awareness
- Economic decisions, tech upgrades, hero management
- Adaptive military tactics

**Multiplayer** (network/ package, fully operational):
- TCP server supporting up to 4 players
- State synchronization via message protocol
- UPnP port forwarding for internet play
- Simultaneous turn mode with conflict resolution

### **Not Yet Implemented:**

**Save/Load:**
- Serialization system
- File format design
- Mid-game save/resume

---

## 📐 Design Patterns Used

### **1. Model-View-Controller (MVC)**

- **Model:** game_state/ package
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

### **4. Data-Driven Orders**

Orders are data objects, executed centrally:
```python
class MovementOrder:
    # Simple data class (no execute method)
    # from_territory, to_territory, army_count, player, unit_ids
    pass

# Execution handled by game_state/military.py:
def execute_all_orders(self):
    # Processes all MovementOrder objects in self.movement_orders
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
3. **80 FPS cap** - Prevents excessive CPU use (FPS = 80 in config/constants.py)
4. **Surface caching** - Icon, text, overlay, and font caches avoid per-frame allocation
5. **BLEND_RGBA_MULT** - Efficient tint overlays instead of per-pixel operations

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

**Last Updated:** February 27, 2026
**Architecture Version:** Phase 7 Complete (mixin decomposition)
