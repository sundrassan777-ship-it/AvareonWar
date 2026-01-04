# War of Avareon - Technical Reference Guide
## Complete System Documentation for Future Development

**Version:** 2.0  
**Last Updated:** January 3, 2026  
**Status:** Production Ready  

---

## 📋 **Quick Navigation**

1. [System Architecture](#system-architecture)
2. [File Structure](#file-structure)
3. [Key Data Structures](#key-data-structures)
4. [UI System](#ui-system)
5. [Game Loop](#game-loop)
6. [Event System](#event-system)
7. [Rendering Pipeline](#rendering-pipeline)
8. [State Management](#state-management)
9. [How to Add Features](#how-to-add-features)
10. [API Reference](#api-reference)

---

## 🏗️ **System Architecture**

### **High-Level Overview**

```
┌──────────────────────────────────────────────────┐
│                  GAME LOOP (60 FPS)              │
│                    (main.py)                     │
└────────┬──────────────────────────────────┬──────┘
         │                                   │
    ┌────▼─────┐                      ┌─────▼─────┐
    │  Events  │                      │ Rendering │
    │ Keyboard │                      │  Pipeline │
    │  Mouse   │                      │  draw_*() │
    └────┬─────┘                      └─────┬─────┘
         │                                   │
    ┌────▼──────────────────────────────────▼────┐
    │          GAME STATE (game_state.py)        │
    │  • Territory ownership                     │
    │  • Army positions                          │
    │  • Buildings                               │
    │  • Orders                                  │
    │  • Resources                               │
    └────┬───────────────────────────────────────┘
         │
    ┌────▼─────┐
    │   Data   │
    │  .json   │
    │  files   │
    └──────────┘
```

### **Core Components**

**1. Game Class (main.py)**
- Manages pygame window and event loop
- Handles all rendering
- Processes user input
- Calls GameState methods for game logic

**2. GameState Class (game_state.py)**
- Stores all game state
- Implements game rules
- Manages turn progression
- Handles combat, movement, economy

**3. Data Files (.json)**
- Territory polygons (visual)
- Economic data (income, buildings)
- Plot locations (buildings)

**4. Tool Scripts (_tool.py)**
- Helper utilities
- Data validation
- Development aids

---

## 📁 **File Structure**

### **Core Game Files**

```
main.py (6,284 lines)
├── UIConstants class
│   └── All UI layout constants
├── Game class
│   ├── __init__() - Initialization
│   ├── run() - Main game loop
│   ├── Event Handlers
│   │   ├── handle_click()
│   │   ├── handle_keyboard_input()
│   │   └── handle_camera_zoom()
│   ├── Rendering Methods
│   │   ├── draw() - Master draw method
│   │   ├── draw_map()
│   │   ├── draw_top_panel()
│   │   ├── draw_bottom_ui()
│   │   ├── draw_order_sidebar() ← NEW
│   │   │   ├── _draw_sidebar_tab_buttons()
│   │   │   ├── _draw_action_queue_content()
│   │   │   ├── _draw_action_log_content()
│   │   │   ├── _draw_chat_content()
│   │   │   └── _draw_placeholder_tab_content()
│   │   ├── draw_chat_input() ← NEW
│   │   ├── draw_tooltips()
│   │   └── draw_popups()
│   └── Utility Methods
│       ├── screen_to_world()
│       ├── world_to_screen()
│       └── get_territory_at_pos()
```

```
game_state.py (2,511 lines)
├── GameState class
│   ├── State Variables
│   │   ├── self.territories
│   │   ├── self.armies
│   │   ├── self.players
│   │   ├── self.movement_orders
│   │   ├── self.chat_messages ← NEW
│   │   └── self.sidebar_tabs ← NEW
│   ├── Turn Management
│   │   ├── end_turn()
│   │   ├── execute_phase()
│   │   └── check_victory()
│   ├── Movement System
│   │   ├── can_move_to()
│   │   ├── queue_movement()
│   │   └── execute_movements()
│   ├── Combat System
│   │   ├── resolve_battle()
│   │   ├── calculate_strength()
│   │   └── sequential_battles()
│   ├── Economy System
│   │   ├── collect_income()
│   │   ├── spend_gold()
│   │   └── calculate_territory_income()
│   ├── Building System
│   │   ├── can_build()
│   │   ├── build()
│   │   └── get_building_benefits()
│   ├── Recruitment System
│   │   ├── can_recruit()
│   │   ├── queue_recruitment()
│   │   └── process_recruitment_queue()
│   ├── Message System
│   │   ├── add_message() ← MODIFIED
│   │   └── add_chat_message() ← NEW
│   └── Utility Methods
│       ├── get_adjacent_territories()
│       ├── get_territory_by_id()
│       └── get_player_color()
```

### **Data Files**

```
economic_data.json
├── territory_incomes (base income per territory)
├── building_definitions (types, costs, benefits)
└── unit_definitions (types, costs, stats)

plots.json
├── 85 building plot locations
└── territory associations

territory_polygons.json
├── 50 territory polygon definitions
└── visual boundary data
```

### **Tool Files**

```
adjacency_tool.py - Territory adjacency definitions
economic_tool.py - Economic data management
map_data.py - Map rendering data
plot_tool.py - Plot location management
polygon_tool.py - Polygon processing utilities
```

---

## 🗂️ **Key Data Structures**

### **Territory**

```python
{
    'id': 5,
    'name': 'Rohan',
    'owner': 0,  # Player index (0-3)
    'base_income': 75,  # Low (50), Medium (75), High (100)
    'buildings': [
        {'type': 'Farm', 'plot_id': 12},
        {'type': 'Keep', 'plot_id': 13}
    ],
    'garrison': {
        'infantry': 5,
        'cavalry': 2,
        'siege': 0
    },
    'recruitment_queue': [
        {'type': 'infantry', 'turns_remaining': 1},
        {'type': 'cavalry', 'turns_remaining': 2}
    ]
}
```

### **Army**

```python
{
    'id': 0,
    'territory_id': 5,
    'owner': 0,
    'units': {
        'infantry': 10,
        'cavalry': 5,
        'siege': 2
    },
    'status': 'ready'  # or 'ordered', 'moving', 'in_combat'
}
```

### **Movement Order**

```python
{
    'army_id': 0,
    'from_territory': 5,
    'to_territory': 12,
    'is_attack': True  # False for friendly movement
}
```

### **Building**

```python
{
    'type': 'Farm',  # Farm, Barracks, Keep, Market, Mine
    'plot_id': 12,
    'territory_id': 5,
    'owner': 0,
    'built_turn': 15
}
```

### **Chat Message** ← NEW

```python
('12:34:56', 0, 'Hello everyone!')
# (timestamp, player_id, message)
```

### **Player**

```python
{
    'id': 0,
    'name': 'Player 1',
    'faction': 'Gondor',
    'color': (100, 150, 255),
    'gold': 1500,
    'income_per_turn': 275,
    'alive': True
}
```

---

## 🎨 **UI System**

### **Layout Overview**

```
┌─────────────────────────────────────────────────────┐
│  TOP PANEL (40px height)                            │
│  Player stats, gold, income                         │
├─────────────────────────────────────┬───────────────┤
│                                     │  SIDEBAR      │
│                                     │  (250x610)    │
│                                     │               │
│          MAP AREA                   │  6 Tabs:      │
│          (610px height)             │  • Tech       │
│                                     │  • Heroes     │
│                                     │  • Queue      │
│                                     │  • Log        │
│                                     │  • Quests     │
│                                     │  • Chat       │
├─────────────────────────────────────┴───────────────┤
│  BOTTOM UI (200px height)                           │
│  Territory info, building controls, army controls   │
└─────────────────────────────────────────────────────┘
```

### **Sidebar Tab System**

**Tab Structure:**
```python
# Tab list
self.sidebar_tabs = [
    'technology',   # Placeholder
    'heroes',       # Placeholder
    'action_queue', # Functional
    'action_log',   # Functional
    'quests',       # Placeholder
    'chat'          # Functional
]

# Active tab
self.active_sidebar_tab = 'action_queue'

# Tab buttons (rendered on left edge)
# Each tab: 40px wide x ~86px tall
# Rotated text, exclusive selection
```

**Adding a New Tab:**

1. Add to tab list:
```python
self.sidebar_tabs.append('diplomacy')
```

2. Add display name:
```python
tab_names = {
    # ...
    'diplomacy': 'Diplomacy'
}
```

3. Create content method:
```python
def _draw_diplomacy_content(self, sidebar_x, sidebar_y, 
                            sidebar_width, sidebar_height, 
                            content_start_y):
    # Draw header
    # Draw content
    pass
```

4. Add to switch statement:
```python
elif active_tab == 'diplomacy':
    self._draw_diplomacy_content(...)
```

### **Scrolling System**

**Components:**
- Scroll offset tracking (per tab)
- Mouse wheel event handling
- Scrollbar rendering
- Position indicator text

**Implementation:**
```python
# State
self.chat_scroll_offset = 0  # 0 = newest visible
self.action_log_scroll_offset = 0

# Scrolling
if delta > 0:  # Scroll up (older)
    offset = min(offset + 1, max_scroll)
else:  # Scroll down (newer)
    offset = max(offset - 1, 0)

# Max scroll calculation
approx_visible = height // UIConstants.PIXELS_PER_MESSAGE_SCROLL
max_scroll = max(0, total_messages - approx_visible)
```

### **Chat System**

**Input Flow:**
```
1. User presses ENTER
2. chat_input_active = True
3. Draw input box with cursor
4. Capture keystrokes
5. ENTER → send_message()
6. ESC → cancel input
7. chat_input_active = False
```

**Message Display:**
```python
# Format: [HH:MM:SS] PlayerName: message
timestamp = "12:34:56"
player_name = f"Player {player_id + 1}"
player_color = get_player_color(player_id)

# Render with word wrapping
# Newest at bottom
# Scrollable
```

---

## 🔄 **Game Loop**

### **Main Loop Structure**

```python
def run(self):
    clock = pygame.time.Clock()
    running = True
    
    while running:
        # 1. EVENT HANDLING
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                self.handle_keyboard_input(event)
            elif event.type == pygame.MOUSEWHEEL:
                self.handle_camera_zoom(event.y)
        
        # 2. UPDATE CURSOR BLINK (chat)
        self.cursor_blink_time += clock.get_time()
        
        # 3. RENDERING
        self.draw()
        
        # 4. FRAME RATE (60 FPS)
        clock.tick(FPS)
```

### **Turn Execution**

```python
def end_turn(self):
    # Phase 1: Planning → Battle
    self.turn_phase = 'battle'
    
    # Phase 2: Execute movements
    self.execute_movements()
    
    # Phase 3: Resolve battles
    for battle in self.battles:
        self.resolve_battle(battle)
    
    # Phase 4: Battle → Income
    self.turn_phase = 'income'
    
    # Phase 5: Collect income
    self.collect_income()
    
    # Phase 6: Process recruitment
    self.process_recruitment_queue()
    
    # Phase 7: Income → Planning (next turn)
    self.current_turn += 1
    self.turn_phase = 'planning'
    
    # Phase 8: Check victory
    self.check_victory()
```

---

## ⚡ **Event System**

### **Click Handler Priority**

```python
def handle_click(self, pos):
    # Priority 1: Modal popups
    if self.showing_battle_modal:
        return self.handle_battle_modal_click(pos)
    
    if self.showing_victory_screen:
        return self.handle_victory_screen_click(pos)
    
    # Priority 2: Top panel
    if self.handle_top_panel_click(pos):
        return True
    
    # Priority 3: Bottom UI
    if self.handle_bottom_ui_click(pos):
        return True
    
    # Priority 4: Sidebar
    if self.handle_sidebar_click(pos):
        return True
    
    # Priority 5: Map
    return self.handle_map_click(pos)
```

### **Keyboard Handler Priority**

```python
def handle_keyboard_input(self, event):
    # Priority 1: Chat input (if active)
    if self.chat_input_active:
        return self.handle_chat_input(event)
    
    # Priority 2: ESC (close popups)
    if event.key == pygame.K_ESCAPE:
        return self.handle_escape()
    
    # Priority 3: ENTER (open chat)
    if event.key == pygame.K_RETURN:
        self.chat_input_active = True
        return True
    
    # Priority 4: Space (end turn)
    if event.key == pygame.K_SPACE:
        return self.handle_end_turn()
    
    # Priority 5: Arrow keys (camera)
    if event.key in [K_UP, K_DOWN, K_LEFT, K_RIGHT]:
        return self.handle_camera_scroll(event.key)
    
    # Priority 6: Shortcuts (S, M, etc.)
    return self.handle_shortcuts(event.key)
```

---

## 🎨 **Rendering Pipeline**

### **draw() Method Flow**

```python
def draw(self):
    # 1. Clear screen
    self.screen.fill(BLACK)
    
    # 2. Draw map
    self.draw_map()
    
    # 3. Draw UI panels
    self.draw_top_panel()
    self.draw_bottom_ui()
    self.draw_order_sidebar()  # NEW: 6-tab sidebar
    
    # 4. Draw overlays
    if self.chat_input_active:
        self.draw_chat_input()  # NEW: Chat input box
    
    # 5. Draw tooltips
    if self.tooltip_timer >= 0.5:
        self.draw_tooltip()
    
    # 6. Draw popups (highest layer)
    if self.showing_battle_modal:
        self.draw_battle_modal()
    
    if self.showing_victory_screen:
        self.draw_victory_screen()
    
    # 7. Update display
    pygame.display.flip()
```

### **Map Rendering**

```python
def draw_map(self):
    # 1. Draw territory polygons
    for territory in self.game_state.territories:
        polygon = get_polygon(territory.id)
        color = get_faction_color(territory.owner)
        
        # Draw fill (semi-transparent)
        pygame.draw.polygon(self.screen, color + (128,), polygon)
        
        # Draw outline
        pygame.draw.polygon(self.screen, WHITE, polygon, 2)
    
    # 2. Draw selected territory highlight
    if self.selected_territory:
        polygon = get_polygon(self.selected_territory.id)
        pygame.draw.polygon(self.screen, BRIGHT_GREEN, polygon, 5)
    
    # 3. Draw armies
    for army in self.game_state.armies:
        pos = get_territory_center(army.territory_id)
        strength = calculate_strength(army)
        
        # Draw army icon
        pygame.draw.circle(self.screen, BLACK, pos, 20)
        pygame.draw.circle(self.screen, army_color, pos, 18)
        
        # Draw strength number
        text = font.render(str(strength), True, WHITE)
        self.screen.blit(text, text_rect)
    
    # 4. Draw building icons
    for building in self.game_state.buildings:
        icon = get_building_icon(building.type)
        pos = get_plot_position(building.plot_id)
        self.screen.blit(icon, pos)
```

---

## 💾 **State Management**

### **State Variables (GameState)**

```python
class GameState:
    def __init__(self):
        # Game info
        self.current_turn = 1
        self.turn_phase = 'planning'  # 'planning', 'battle', 'income'
        self.winner = -1
        
        # Players
        self.num_players = 4
        self.current_player = 0
        self.players = [...]
        
        # Map
        self.territories = [...]
        self.armies = [...]
        self.buildings = []
        
        # Orders
        self.movement_orders = []
        
        # Messages
        self.messages = []  # Action log (unlimited)
        self.chat_messages = []  # Chat (unlimited)
        
        # UI State
        self.sidebar_expanded = True  # Always
        self.sidebar_tabs = [...]
        self.active_sidebar_tab = 'action_queue'
```

### **State Variables (Game)**

```python
class Game:
    def __init__(self):
        # Game state reference
        self.game_state = GameState()
        
        # Camera
        self.camera_offset = [0, 0]
        self.camera_zoom = 1.0
        
        # Selection
        self.selected_territory = None
        self.selected_army = None
        self.hovered_territory = None
        
        # UI State
        self.showing_battle_modal = False
        self.showing_victory_screen = False
        self.tooltip_timer = 0
        
        # Chat state (NEW)
        self.chat_input_active = False
        self.chat_input_text = ""
        self.cursor_blink_time = 0
        
        # Scroll state (NEW)
        self.chat_scroll_offset = 0
        self.action_log_scroll_offset = 0
        
        # UI elements (for click detection)
        self.sidebar_tab_buttons = {}
        self.order_cancel_buttons = []
        self.cancel_all_button = None
```

### **State Persistence**

Currently, state is **not persisted** between sessions.

**To Add Save/Load:**

```python
import json

def save_game(self, filename):
    state = {
        'turn': self.current_turn,
        'phase': self.turn_phase,
        'players': self.players,
        'territories': self.territories,
        'armies': self.armies,
        'buildings': self.buildings,
        # ... all relevant state
    }
    
    with open(filename, 'w') as f:
        json.dump(state, f, indent=2)

def load_game(self, filename):
    with open(filename, 'r') as f:
        state = json.load(f)
    
    self.current_turn = state['turn']
    self.turn_phase = state['phase']
    # ... restore all state
```

---

## 🛠️ **How to Add Features**

### **Adding a New Building Type**

**Step 1: Update economic_data.json**
```json
{
  "building_definitions": {
    "Temple": {
      "cost": 200,
      "benefit_type": "income",
      "benefit_value": 150,
      "description": "Religious building providing income"
    }
  }
}
```

**Step 2: Add icon/visual**
```python
# In draw_building_icons()
elif building.type == 'Temple':
    color = (255, 215, 0)  # Gold
    pygame.draw.circle(self.screen, color, pos, 8)
```

**Step 3: Add to building menu**
```python
# In draw_bottom_ui() building section
temple_button = pygame.Rect(...)
if temple_button.collidepoint(mouse_pos):
    # Draw hover effect
```

**Done!** New building type integrated.

---

### **Adding a New Unit Type**

**Step 1: Define unit in economic_data.json**
```json
{
  "unit_definitions": {
    "Archer": {
      "cost": 75,
      "attack": 3,
      "defense": 2,
      "training_time": 1
    }
  }
}
```

**Step 2: Update recruitment UI**
```python
# Add button in barracks panel
archer_button = pygame.Rect(...)
archer_text = "Train Archer (75g)"
```

**Step 3: Update strength calculation**
```python
def calculate_strength(self, army):
    strength = 0
    strength += army['infantry'] * 2
    strength += army['cavalry'] * 3
    strength += army['siege'] * 4
    strength += army.get('archer', 0) * 2.5  # New
    return strength
```

**Done!** New unit type integrated.

---

### **Adding Message Filtering to Action Log**

**Step 1: Add filter state**
```python
# In Game.__init__()
self.action_log_filter = 'all'  # 'all', 'battles', 'income', 'buildings'
```

**Step 2: Add filter UI**
```python
# In _draw_action_log_content()
filter_buttons = {
    'all': pygame.Rect(...),
    'battles': pygame.Rect(...),
    'income': pygame.Rect(...),
    'buildings': pygame.Rect(...)
}

for filter_type, button_rect in filter_buttons.items():
    color = BLUE if filter_type == self.action_log_filter else GRAY
    pygame.draw.rect(self.screen, color, button_rect)
```

**Step 3: Filter messages**
```python
# Before displaying
if self.action_log_filter != 'all':
    filtered_messages = []
    for msg in all_messages:
        if message_matches_filter(msg, self.action_log_filter):
            filtered_messages.append(msg)
    messages_to_show = filtered_messages
```

**Step 4: Add click handling**
```python
# In handle_sidebar_click()
for filter_type, button_rect in filter_buttons.items():
    if button_rect.collidepoint(pos):
        self.action_log_filter = filter_type
        return True
```

**Done!** Message filtering implemented.

---

## 📚 **API Reference**

### **GameState Methods**

#### **Movement**

```python
def queue_movement(self, army_id, to_territory_id):
    """
    Queue a movement order for an army.
    
    Args:
        army_id: ID of army to move
        to_territory_id: Destination territory ID
        
    Returns:
        bool: True if order queued, False if invalid
    """

def can_move_to(self, from_territory_id, to_territory_id):
    """
    Check if movement is valid (adjacency, ownership).
    
    Args:
        from_territory_id: Source territory
        to_territory_id: Destination territory
        
    Returns:
        bool: True if movement allowed
    """

def cancel_movement_order(self, order_index):
    """
    Cancel a specific movement order.
    
    Args:
        order_index: Index in movement_orders list
    """

def cancel_all_orders(self):
    """Cancel all queued movement orders."""
```

#### **Combat**

```python
def resolve_battle(self, attacker_id, defender_id, territory_id):
    """
    Resolve a battle between two armies.
    
    Args:
        attacker_id: Attacking army ID
        defender_id: Defending army ID (or None for garrison)
        territory_id: Territory where battle occurs
        
    Returns:
        dict: Battle results with winner, casualties, etc.
    """

def calculate_strength(self, army):
    """
    Calculate total army strength.
    
    Args:
        army: Army dict with unit composition
        
    Returns:
        int: Total strength value
    """
```

#### **Economy**

```python
def collect_income(self):
    """Collect income for all players at end of turn."""

def calculate_territory_income(self, territory_id):
    """
    Calculate income from a single territory.
    
    Args:
        territory_id: Territory to calculate
        
    Returns:
        int: Total income (base + building bonuses)
    """

def spend_gold(self, player_id, amount):
    """
    Spend gold if player has enough.
    
    Args:
        player_id: Player spending gold
        amount: Amount to spend
        
    Returns:
        bool: True if spent, False if insufficient
    """
```

#### **Buildings**

```python
def can_build(self, territory_id, building_type):
    """
    Check if building can be constructed.
    
    Args:
        territory_id: Where to build
        building_type: Type of building
        
    Returns:
        bool: True if can build
    """

def build(self, territory_id, plot_id, building_type):
    """
    Construct a building.
    
    Args:
        territory_id: Territory
        plot_id: Plot location
        building_type: Building type
        
    Returns:
        bool: True if built, False if failed
    """
```

#### **Messages**

```python
def add_message(self, message):
    """
    Add message to action log.
    
    Args:
        message: Text message to log
    """

def add_chat_message(self, player_id, message):
    """
    Add chat message with timestamp.
    
    Args:
        player_id: Player sending message
        message: Message text
    """
```

---

### **Game (Rendering) Methods**

#### **Drawing**

```python
def draw():
    """Master draw method. Calls all sub-draw methods."""

def draw_map():
    """Draw territories, armies, buildings."""

def draw_top_panel():
    """Draw player stats, turn info."""

def draw_bottom_ui():
    """Draw territory info, building controls."""

def draw_order_sidebar():
    """Draw 6-tab sidebar system."""

def draw_chat_input():
    """Draw chat input box if active."""
```

#### **Event Handling**

```python
def handle_click(pos):
    """
    Handle mouse click.
    
    Args:
        pos: (x, y) tuple
        
    Returns:
        bool: True if click handled
    """

def handle_keyboard_input(event):
    """
    Handle keyboard input.
    
    Args:
        event: pygame.KEYDOWN event
        
    Returns:
        bool: True if input handled
    """

def handle_camera_zoom(delta):
    """
    Handle mouse wheel (zoom or scroll).
    
    Args:
        delta: Wheel delta (+1 up, -1 down)
    """
```

---

## 🔧 **Constants Reference**

### **UIConstants**

```python
# Sidebar
SIDEBAR_WIDTH = 250          # Sidebar panel width
SIDEBAR_HEIGHT = 610         # Sidebar panel height

# Messages
PIXELS_PER_MESSAGE_SELECTION = 40  # For calculating visible messages
PIXELS_PER_MESSAGE_SCROLL = 40     # For scroll limit calculations
MESSAGE_MAX_CHARS = 28             # Word wrap limit

# Tabs
TAB_WIDTH = 40              # Tab button width
TAB_PADDING_TOP = 45        # Top padding for tabs
TAB_PADDING_BOTTOM = 45     # Bottom padding for tabs

# Scrollbar
SCROLLBAR_WIDTH = 4         # Scrollbar track/thumb width
SCROLLBAR_OFFSET = 8        # Distance from right edge
SCROLLBAR_THUMB_MIN = 20    # Minimum thumb height

# Spacing
HEADER_OFFSET = 45          # Content Y offset
BOTTOM_RESERVE = 40         # Bottom space reserve
SIDEBAR_CONTENT_PADDING = 100  # Total content padding
```

### **Window Constants**

```python
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 850
TOP_PANEL_HEIGHT = 40
BOTTOM_UI_HEIGHT = 200
MAP_HEIGHT = 610
FPS = 60
```

---

## 🎓 **Development Best Practices**

### **Code Style**

1. **Method Naming:**
   - Public: `draw_sidebar()`
   - Private: `_draw_chat_content()`
   - Handlers: `handle_click()`

2. **Variable Naming:**
   - Constants: `SIDEBAR_WIDTH`
   - Instance: `self.chat_scroll_offset`
   - Local: `msg_y`, `scroll_pos`

3. **Documentation:**
   - All public methods need docstrings
   - Complex logic needs inline comments
   - Use type hints where helpful

### **Testing**

1. **Always test:**
   - Compilation (`python3 -m py_compile`)
   - Functionality (manual testing)
   - Edge cases (boundary conditions)

2. **Test checklist for new features:**
   - [ ] Feature works as intended
   - [ ] No new bugs introduced
   - [ ] Existing features still work
   - [ ] UI looks professional
   - [ ] Code is documented

### **Git Workflow** (if using version control)

```bash
# Feature branch
git checkout -b feature/diplomacy-system

# Regular commits
git commit -m "Add diplomacy data structure"
git commit -m "Implement alliance UI"
git commit -m "Add treaty validation"

# Merge when complete
git checkout main
git merge feature/diplomacy-system
```

---

## 📝 **Troubleshooting Guide**

### **Common Issues**

**Issue:** Chat messages not showing newest  
**Solution:** Check `PIXELS_PER_MESSAGE_SELECTION` is set correctly (40)

**Issue:** Scrolling goes too far  
**Solution:** Verify `max_scroll` calculation includes message count check

**Issue:** Sidebar overlaps bottom UI  
**Solution:** Check `SIDEBAR_HEIGHT` matches `MAP_HEIGHT`

**Issue:** Tab buttons not clickable  
**Solution:** Verify `sidebar_tab_buttons` dict is populated correctly

**Issue:** Chat input not responding  
**Solution:** Check `chat_input_active` is True and event priority is correct

---

## 🚀 **Performance Optimization**

### **Current Performance**

- **60 FPS** maintained at all times
- **No lag** with 50 territories, 100+ armies
- **Instant** UI response

### **If Performance Issues Arise:**

**1. Reduce Rendering:**
```python
# Only redraw changed areas
dirty_rects = []
for rect in changed_areas:
    pygame.display.update(rect)
```

**2. Cache Expensive Calculations:**
```python
# Cache territory polygons
if not hasattr(self, '_polygon_cache'):
    self._polygon_cache = {}
```

**3. Limit Draw Calls:**
```python
# Batch similar draw operations
all_army_positions = [get_pos(a) for a in armies]
pygame.draw.circles(screen, color, all_army_positions)
```

---

## 📚 **Additional Resources**

### **External Dependencies**

- **Pygame:** Graphics and input handling
- **JSON:** Data storage format
- **Python 3.8+:** Core language

### **Learning Resources**

- Pygame documentation: https://www.pygame.org/docs/
- Python documentation: https://docs.python.org/3/
- Game development patterns: https://gameprogrammingpatterns.com/

---

## ✅ **Quick Checklist for New Developers**

**Getting Started:**
- [ ] Read this document
- [ ] Read SESSION_COMPLETE.md
- [ ] Read updated game-user-stories.md
- [ ] Review main.py and game_state.py structure
- [ ] Understand data structures
- [ ] Run the game and explore features

**Before Making Changes:**
- [ ] Understand what you're changing
- [ ] Check if constants should be used
- [ ] Plan UI changes on paper first
- [ ] Test in isolation if possible

**After Making Changes:**
- [ ] Test compilation
- [ ] Test functionality
- [ ] Check for regressions
- [ ] Update documentation
- [ ] Comment complex code

---

*Document Version: 2.0*  
*Last Updated: January 3, 2026*  
*Status: Complete and Production-Ready*
