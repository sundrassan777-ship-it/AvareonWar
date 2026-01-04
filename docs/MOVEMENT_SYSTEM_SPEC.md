# Advanced Army Movement & Battle System - Specification

**Feature:** TIER 2B - Feature #17 (Replaces Combat Preview)  
**Name:** Advanced Army Movement & Battle System  
**Date:** December 28, 2024  
**Status:** ðŸ“‹ SPECIFICATION PHASE

---

## ðŸŽ¯ Overview

Transform the current immediate-execution movement system into a professional turn-based order system with:
- Planning phase for issuing movement orders
- Visual indicators for planned moves
- Simultaneous execution at turn end
- Dedicated battle resolution phase
- No more misclick frustration!

---

## ðŸ“Š Current System vs New System

### Current System (To Be Replaced)

**Flow:**
```
1. Click Territory A â†’ selects it
2. Click Territory B â†’ army moves IMMEDIATELY
3. Combat resolves IMMEDIATELY
4. Turn continues
```

**Problems:**
- âŒ Misclicks cause immediate disasters
- âŒ No planning or coordination
- âŒ Can't see overall strategy
- âŒ No undo capability
- âŒ Feels unpolished

---

### New System (To Be Implemented)

**Flow:**
```
PLANNING PHASE:
1. Click army number â†’ selects army
2. Right-click adjacent territory â†’ creates movement order
3. Visual arrow appears showing planned move
4. Repeat for all desired moves
5. Click "END TURN" button

EXECUTION PHASE:
6. All armies move simultaneously
7. Empty neutrals captured automatically
8. Battles created for enemy encounters

BATTLE PHASE (if battles exist):
9. Crossed swords appear over battle territories
10. Click battle territory â†’ view details
11. Click "RESOLVE" â†’ see result
12. Repeat for all battles
13. Next player's turn begins
```

**Benefits:**
- âœ… No misclick disasters
- âœ… Plan coordinated attacks
- âœ… Undo orders before committing
- âœ… Professional strategy game feel
- âœ… Industry standard approach

---

## ðŸ—ï¸ System Architecture

### Turn Phase System

**Three Turn Phases:**

1. **Planning Phase** (`turn_phase = 'planning'`)
   - Default phase during player's turn
   - Player issues movement orders
   - Can select armies, create orders, cancel orders
   - Ends when player clicks "END TURN"

2. **Execution Phase** (`turn_phase = 'execution'`)
   - Brief phase (happens automatically)
   - All movement orders execute
   - Battles detected and created
   - Empty neutrals auto-captured
   - Transitions to Battles phase or next player

3. **Battles Phase** (`turn_phase = 'battles'`)
   - Only entered if battles exist
   - Player must click each battle to resolve
   - Shows battle details and results
   - Ends when all battles resolved â†’ next player

---

## ðŸ’¾ Data Structures

### New Game State Fields

```python
class GameState:
    def __init__(self):
        # Existing fields...
        
        # NEW: Army selection
        self.selected_army = None  # (territory_name, army_count) or None
        
        # NEW: Movement orders queue
        self.movement_orders = []  # List of MovementOrder objects
        
        # NEW: Battle queue
        self.pending_battles = []  # List of Battle objects
        
        # NEW: Turn phase tracking
        self.turn_phase = 'planning'  # 'planning', 'execution', 'battles'
```

---

### MovementOrder Object

```python
class MovementOrder:
    def __init__(self, from_territory, to_territory, army_count, player):
        self.from_territory = str      # Source territory name
        self.to_territory = str        # Destination territory name
        self.army_count = int          # Number of armies to move
        self.player = int              # Player index who issued order
        self.order_id = int            # Unique ID for cancellation
```

**Example:**
```python
order = MovementOrder(
    from_territory="Amennia",
    to_territory="Brundisium",
    army_count=5,
    player=0
)
```

---

### Battle Object

```python
class Battle:
    def __init__(self, territory, attacker_player, attacking_armies, 
                 defender_player, defending_armies, has_fortress):
        self.territory = str           # Territory where battle occurs
        self.attacker_player = int     # Attacking player index
        self.attacking_armies = int    # Number of attacking armies
        self.defender_player = int     # Defending player index (-1 = neutral)
        self.defending_armies = int    # Number of defending armies
        self.has_fortress = bool       # Does defender have fortress?
        self.resolved = bool           # Has battle been resolved?
        self.result = dict or None     # Result after resolution
```

**Example:**
```python
battle = Battle(
    territory="Tarentum",
    attacker_player=0,
    attacking_armies=5,
    defender_player=1,
    defending_armies=3,
    has_fortress=True,
    resolved=False,
    result=None
)
```

---

## ðŸŽ® User Interactions

### 1. Army Selection

**How to Select:**
- Click on army NUMBER display (not territory background)
- Territory must be owned by current player
- Territory must have unmoved armies

**Visual Feedback:**
- Selected army: Green glow around the number
- Selected territory: Highlighted border
- Other territories: Dimmed slightly

**Deselection:**
- Click selected army again â†’ deselect
- Click different army â†’ switch selection
- Issue movement order â†’ stays selected for next order

**Validation:**
```python
def can_select_army(territory):
    âœ“ Territory owned by current player
    âœ“ Territory has unmoved armies > 0
    âœ“ Turn phase is 'planning'
```

---

### 2. Movement Order Creation

**How to Create:**
- Right-click on adjacent territory
- Must have army selected
- Target must be adjacent to selected army's territory

**Visual Feedback:**
- Arrow drawn from source to destination
- Arrow color: Green (valid move)
- Arrow includes army count badge
- Source territory shows reduced army count preview

**Order Queue Display:**
- Sidebar shows list of pending orders
- Each order shows: "5 armies: Amennia â†’ Brundisium"
- Cancel button (X) next to each order

**Validation:**
```python
def can_create_order(from_territory, to_territory):
    âœ“ Army is selected
    âœ“ Territories are adjacent
    âœ“ Source has unmoved armies
    âœ“ Turn phase is 'planning'
    âœ“ No duplicate order from same territory
```

---

### 3. Order Cancellation

**How to Cancel:**
- Click the (X) button next to order in sidebar
- OR: Click on the arrow itself

**Visual Feedback:**
- Arrow disappears
- Order removed from sidebar
- Army count preview updates

**Effect:**
- Order removed from queue
- Armies available for new orders

---

### 4. End Turn

**How to End Turn:**
- Click "END TURN" button (large, prominent)
- Keyboard shortcut: ENTER or SPACEBAR

**Confirmation:**
- If no orders: "No moves this turn. End turn anyway?"
- If orders exist: Execute immediately

**Visual Feedback:**
- Button greys out during execution
- "Executing orders..." message appears
- Armies animate moving (optional enhancement)

---

### 5. Battle Resolution

**How to Resolve:**
- Click on territory with crossed swords marker
- Battle popup appears with details
- Click "RESOLVE BATTLE" button

**Battle Popup Contents:**
```
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘     BATTLE AT TARENTUM          â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘                                  â•‘
â•‘  Attacker (Player 1):           â•‘
â•‘    5 armies                      â•‘
â•‘                                  â•‘
â•‘  Defender (Player 2):           â•‘
â•‘    3 armies (+2 Fortress)       â•‘
â•‘                                  â•‘
â•‘  Predicted Outcome:             â•‘
â•‘    Close battle!                â•‘
â•‘                                  â•‘
â•‘  [  RESOLVE BATTLE  ]           â•‘
â•‘                                  â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
```

**After Resolution:**
```
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘     BATTLE RESULT               â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘                                  â•‘
â•‘  Armies eliminated!             â•‘
â•‘  2 attackers storm Fortress...  â•‘
â•‘  Fortress holds!                â•‘
â•‘  Attack repelled!               â•‘
â•‘                                  â•‘
â•‘  [      CONTINUE      ]         â•‘
â•‘                                  â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
```

---

## ðŸŽ¨ Visual Design Specifications

### Movement Arrows

**Arrow Appearance:**
```
Source Territory
      â”‚
      â”‚  â† Green arrow (3px thick)
      â†“
      â”‚
Target Territory

Badge on arrow: [5] â† Number of armies
```

**Arrow Properties:**
- Color: Green (0, 200, 0)
- Thickness: 3 pixels
- Style: Solid line with arrowhead
- Arrowhead: Triangle, 10px wide
- Badge: White circle with black number

**Multiple Arrows:**
```
Territory A
    â”œâ”€â”€â†’ Territory B  [5]
    â”œâ”€â”€â†’ Territory C  [3]
    â””â”€â”€â†’ Territory D  [2]
```

**Arrow Drawing Code Pseudocode:**
```python
def draw_movement_arrow(from_pos, to_pos, army_count):
    # Draw line
    pygame.draw.line(screen, GREEN, from_pos, to_pos, 3)
    
    # Draw arrowhead
    angle = calculate_angle(from_pos, to_pos)
    draw_triangle(to_pos, angle, size=10)
    
    # Draw badge
    mid_point = midpoint(from_pos, to_pos)
    draw_circle(mid_point, radius=12, color=WHITE)
    draw_text(mid_point, str(army_count), color=BLACK)
```

---

### Battle Markers

**Crossed Swords Icon:**
```
    âš”ï¸
  /   \
 /     \
/       \

Positioned over territory center
Size: 32x32 pixels
```

**Alternative (ASCII):**
```
  â•±â•²
 â•±  â•²
â•± âš” â•²
â•²    â•±
 â•²  â•±
  â•²â•±
```

**Battle Territory Highlighting:**
- Red pulsing glow around border
- Pulse frequency: 1 second cycle
- Brightness: 50% â†’ 100% â†’ 50%

**Battle Counter Badge:**
```
Top-right corner of screen:
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  âš”ï¸ 3 BATTLES   â”‚
â”‚   PENDING       â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

### End Turn Button

**Button Design:**
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                        â”‚
â”‚      END TURN          â”‚
â”‚                        â”‚
â”‚    (ENTER/SPACE)       â”‚
â”‚                        â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

Size: 200px x 80px
Position: Bottom-right corner
Color: Green (when active)
       Grey (when disabled)
```

**Button States:**
1. **Active** (Planning phase, can end turn)
   - Color: Bright green (100, 200, 100)
   - Text: "END TURN"
   - Border: Dark green (50, 150, 50)
   - Hover: Lighter green

2. **Executing** (Orders executing)
   - Color: Grey (150, 150, 150)
   - Text: "EXECUTING..."
   - Border: Dark grey
   - Not clickable

3. **Battles Phase** (Waiting for battle resolution)
   - Text: "RESOLVE BATTLES"
   - Color: Red (200, 100, 100)
   - Pulsing effect
   - Not clickable (must resolve battles first)

---

### Order Queue Sidebar

**Location:** Right side of screen, below player info

**Design:**
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  MOVEMENT ORDERS        â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚                         â”‚
â”‚  5 â†’  Amennia          â”‚
â”‚    â†’  Brundisium    [X] â”‚
â”‚                         â”‚
â”‚  3 â†’  Cannae           â”‚
â”‚    â†’  Tarentum      [X] â”‚
â”‚                         â”‚
â”‚  2 â†’  Roma             â”‚
â”‚    â†’  Arretium      [X] â”‚
â”‚                         â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚  [   CANCEL ALL   ]     â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

Width: 250px
Entry height: 50px
```

**Entry Format:**
- Army count (large font)
- Arrow symbol
- Source territory name
- Destination territory name
- [X] cancel button

---

### Army Selection Indicator

**Selected Army Visual:**
```
Territory with selected army:

    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚  Amennia    â”‚  â† Green glow border (3px)
    â”‚             â”‚
    â”‚     â”â”â”â”â”“   â”‚  â† Selected army number
    â”‚     â”ƒ 5 â”ƒ   â”‚     (boxed in green)
    â”‚     â”—â”â”â”â”›   â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**Unselected Armies:**
```
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚  Brundisium â”‚  â† Normal border
    â”‚             â”‚
    â”‚      3      â”‚  â† Normal army number
    â”‚             â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**Selected Army Properties:**
- Border: Green glow, 3px thick, slight pulse
- Number box: Green rectangle behind number
- Brightness: Slightly increased
- Other territories: Dimmed to 70% brightness

---

## ðŸ“± UI Layout Specification

### Full Screen Layout

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  PLAYER TURN â”‚ GOLD: 150 â”‚ INCOME: 45/turn â”‚ TURN: 5    â”‚ â† Top bar
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚                                                          â”‚
â”‚                                                          â”‚
â”‚                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                       â”‚
â”‚         â†“[5]       â”‚  Territory  â”‚                       â”‚
â”‚      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”    â”‚             â”‚      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”‚
â”‚      â”‚Selectedâ”‚    â”‚      3      â”‚      â”‚ Enemy   â”‚     â”‚
â”‚      â”‚  â”â”â”â”“  â”‚    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜      â”‚   âš”ï¸   â”‚     â”‚ â† Map area
â”‚      â”‚  â”ƒ5 â”ƒ  â”‚                          â”‚    4    â”‚     â”‚   with arrows
â”‚      â”‚  â”—â”â”â”›  â”‚                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â”‚   and markers
â”‚      â””â”€â”€â”€â”€â”€â”€â”€â”€â”˜                                          â”‚
â”‚                                                          â”‚
â”‚                                                          â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚                                 â”‚  MOVEMENT ORDERS       â”‚
â”‚  [ACTION LOG]                  â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”‚
â”‚  - Player 1's turn             â”‚  â”‚ 5 â†’ Amennia     â”‚  â”‚
â”‚  - Farm completed              â”‚  â”‚   â†’ Brundisium [X]â”‚  â”‚
â”‚                                 â”‚  â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤  â”‚
â”‚                                 â”‚  â”‚ 3 â†’ Cannae      â”‚  â”‚ â† Orders
â”‚                                 â”‚  â”‚   â†’ Tarentum  [X]â”‚  â”‚   sidebar
â”‚                                 â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚
â”‚                                 â”‚  [  CANCEL ALL  ]      â”‚
â”‚                                 â”‚                        â”‚
â”‚                                 â”‚  âš”ï¸ 2 BATTLES         â”‚
â”‚                                 â”‚    PENDING             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
â”‚                                                          â”‚
â”‚                    [    END TURN    ]                    â”‚ â† Big button
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**Screen Sections:**
1. **Top Bar** (60px height): Turn info, gold, income
2. **Map Area** (60% of screen): Game map with visual indicators
3. **Action Log** (20% bottom-left): Message history
4. **Orders Sidebar** (20% right): Movement orders and battle info
5. **End Turn Button** (80px height): Bottom-center, prominent

---

## ðŸ”„ User Flow Diagrams

### Complete Turn Flow

```
START TURN (Planning Phase)
â”‚
â”œâ”€â†’ Select Army
â”‚   â”‚
â”‚   â”œâ”€â†’ Right-click adjacent territory
â”‚   â”‚   â”‚
â”‚   â”‚   â””â”€â†’ Movement order created
â”‚   â”‚       â””â”€â†’ Arrow appears
â”‚   â”‚           â””â”€â†’ Order added to sidebar
â”‚   â”‚
â”‚   â””â”€â†’ Repeat for more orders
â”‚
â”œâ”€â†’ Review Orders
â”‚   â”‚
â”‚   â”œâ”€â†’ Cancel unwanted orders
â”‚   â”‚
â”‚   â””â”€â†’ Satisfied with plan
â”‚
â””â”€â†’ Click "END TURN"
    â”‚
    â””â”€â†’ EXECUTION PHASE (automatic)
        â”‚
        â”œâ”€â†’ All armies move simultaneously
        â”‚
        â”œâ”€â†’ Empty neutrals auto-captured
        â”‚   â””â”€â†’ Messages: "Captured [Territory]"
        â”‚
        â””â”€â†’ Enemy encounters create battles
            â”‚
            â”œâ”€â†’ NO BATTLES?
            â”‚   â””â”€â†’ Income collected
            â”‚       â””â”€â†’ Next player's turn
            â”‚
            â””â”€â†’ BATTLES EXIST?
                â””â”€â†’ BATTLE PHASE
                    â”‚
                    â”œâ”€â†’ Crossed swords appear
                    â”‚
                    â”œâ”€â†’ "X battles pending" shown
                    â”‚
                    â”œâ”€â†’ Click battle territory
                    â”‚   â”‚
                    â”‚   â””â”€â†’ Battle popup appears
                    â”‚       â”‚
                    â”‚       â””â”€â†’ Click "RESOLVE"
                    â”‚           â”‚
                    â”‚           â””â”€â†’ Result shown
                    â”‚               â”‚
                    â”‚               â””â”€â†’ Click "CONTINUE"
                    â”‚                   â”‚
                    â”‚                   â””â”€â†’ Battle marked resolved
                    â”‚
                    â””â”€â†’ All battles resolved?
                        â””â”€â†’ Income collected
                            â””â”€â†’ Next player's turn
```

---

### Army Selection Flow

```
PLANNING PHASE ACTIVE
â”‚
â””â”€â†’ Click on territory
    â”‚
    â”œâ”€â†’ Territory owned by current player?
    â”‚   â”‚
    â”‚   â”œâ”€â†’ NO â†’ Nothing happens
    â”‚   â”‚
    â”‚   â””â”€â†’ YES â†’ Click on army number?
    â”‚       â”‚
    â”‚       â”œâ”€â†’ NO (clicked background) â†’ Nothing
    â”‚       â”‚
    â”‚       â””â”€â†’ YES (clicked number) â†’ Has unmoved armies?
    â”‚           â”‚
    â”‚           â”œâ”€â†’ NO â†’ Message: "No armies can move"
    â”‚           â”‚
    â”‚           â””â”€â†’ YES â†’ Army selected!
    â”‚               â”‚
    â”‚               â”œâ”€â†’ Green glow appears
    â”‚               â”œâ”€â†’ Adjacent territories highlighted
    â”‚               â””â”€â†’ Ready for movement order
```

---

### Movement Order Flow

```
ARMY SELECTED
â”‚
â””â”€â†’ Right-click on territory
    â”‚
    â”œâ”€â†’ Territory adjacent?
    â”‚   â”‚
    â”‚   â”œâ”€â†’ NO â†’ Nothing happens
    â”‚   â”‚
    â”‚   â””â”€â†’ YES â†’ Create order?
    â”‚       â”‚
    â”‚       â”œâ”€â†’ Check: Already have order from this territory?
    â”‚       â”‚   â”‚
    â”‚       â”‚   â”œâ”€â†’ YES â†’ Cancel existing order first
    â”‚       â”‚   â”‚
    â”‚       â”‚   â””â”€â†’ NO â†’ Proceed
    â”‚       â”‚
    â”‚       â””â”€â†’ ORDER CREATED
    â”‚           â”‚
    â”‚           â”œâ”€â†’ Arrow drawn
    â”‚           â”œâ”€â†’ Added to sidebar
    â”‚           â”œâ”€â†’ Army stays selected (for chaining)
    â”‚           â””â”€â†’ Can issue more orders
```

---

### Battle Resolution Flow

```
BATTLE PHASE ACTIVE
â”‚
â”œâ”€â†’ Pending battles shown
â”‚   â”‚
â”‚   â”œâ”€â†’ Crossed swords on territories
â”‚   â”œâ”€â†’ "X battles pending" badge
â”‚   â””â”€â†’ Red glow on battle territories
â”‚
â””â”€â†’ Click battle territory
    â”‚
    â””â”€â†’ BATTLE POPUP APPEARS
        â”‚
        â”œâ”€â†’ Show battle details:
        â”‚   - Attacker armies
        â”‚   - Defender armies
        â”‚   - Fortress bonus (if any)
        â”‚   - Predicted outcome
        â”‚
        â””â”€â†’ Click "RESOLVE BATTLE"
            â”‚
            â””â”€â†’ Run combat calculation
                â”‚
                â”œâ”€â†’ RESULT: Victory
                â”‚   â””â”€â†’ Territory captured
                â”‚       â””â”€â†’ Show survivors
                â”‚
                â”œâ”€â†’ RESULT: Defeat
                â”‚   â””â”€â†’ Attack repelled
                â”‚       â””â”€â†’ Show defender survivors
                â”‚
                â””â”€â†’ RESULT: Fortress Holds
                    â””â”€â†’ Special message
                        â””â”€â†’ Both armies destroyed
                â”‚
                â””â”€â†’ Click "CONTINUE"
                    â”‚
                    â””â”€â†’ Battle marked resolved
                        â”‚
                        â””â”€â†’ More battles?
                            â”‚
                            â”œâ”€â†’ YES â†’ Return to battle selection
                            â”‚
                            â””â”€â†’ NO â†’ All battles complete!
                                â””â”€â†’ Income collected
                                    â””â”€â†’ Next player's turn
```

---

## âš™ï¸ Technical Implementation Details

### Right-Click Detection

```python
# In main.py event handler
for event in pygame.event.get():
    if event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == 1:  # Left click
            handle_left_click(event.pos)
        elif event.button == 3:  # Right click
            handle_right_click(event.pos)
```

---

### Order Execution Algorithm

```python
def execute_all_orders(self):
    """Execute all movement orders simultaneously"""
    
    # Step 1: Validate all orders still valid
    valid_orders = []
    for order in self.movement_orders:
        if self.validate_order(order):
            valid_orders.append(order)
        else:
            # Order became invalid (territory captured, etc.)
            self.add_message(f"Order cancelled: {order.from_territory} â†’ {order.to_territory}")
    
    # Step 2: Group orders by destination (for battles)
    destinations = {}
    for order in valid_orders:
        if order.to_territory not in destinations:
            destinations[order.to_territory] = []
        destinations[order.to_territory].append(order)
    
    # Step 3: Process each destination
    for territory, orders in destinations.items():
        current_owner = self.territory_owners[territory]
        
        # Case 1: Neutral empty territory
        if current_owner == -1 and self.get_total_armies(territory) == 0:
            # Auto-capture by first order
            self.auto_capture(orders[0])
        
        # Case 2: Owned by moving player (friendly merge)
        elif current_owner == self.current_player:
            # Merge all armies
            self.merge_armies(orders)
        
        # Case 3: Enemy territory (battle!)
        else:
            # Create battle
            self.create_battle(territory, orders)
    
    # Step 4: Clear order queue
    self.movement_orders = []
    
    # Step 5: Transition to battle phase if needed
    if len(self.pending_battles) > 0:
        self.turn_phase = 'battles'
    else:
        self.next_player()
```

---

### Battle Creation

```python
def create_battle(self, territory, attacking_orders):
    """Create a battle from movement orders"""
    
    # Sum all attacking armies
    total_attackers = sum(order.army_count for order in attacking_orders)
    attacker_player = attacking_orders[0].player
    
    # Get defender info
    defender_player = self.territory_owners[territory]
    defending_armies = self.get_total_armies(territory)
    has_fortress = self.has_fortress(territory)
    
    # Create battle object
    battle = Battle(
        territory=territory,
        attacker_player=attacker_player,
        attacking_armies=total_attackers,
        defender_player=defender_player,
        defending_armies=defending_armies,
        has_fortress=has_fortress,
        resolved=False,
        result=None
    )
    
    # Add to queue
    self.pending_battles.append(battle)
    
    # Remove attacking armies from source territories
    for order in attacking_orders:
        self.armies_unmoved[order.from_territory] -= order.army_count
```

---

### Battle Resolution

```python
def resolve_battle(self, battle_index):
    """Resolve a specific battle"""
    
    battle = self.pending_battles[battle_index]
    
    # Use existing combat logic
    result = self.calculate_combat(
        attacking_force=battle.attacking_armies,
        defending_armies=battle.defending_armies,
        has_fortress=battle.has_fortress
    )
    
    # Apply result
    if result['attacker_wins']:
        # Capture territory
        self.territory_owners[battle.territory] = battle.attacker_player
        self.armies_moved[battle.territory] = result['survivors']
        self.armies_unmoved[battle.territory] = 0
        
        # Destroy buildings
        self.destroy_all_buildings(battle.territory)
        
    elif result['fortress_holds']:
        # Special case: fortress holds
        self.armies_unmoved[battle.territory] = 0
        self.armies_moved[battle.territory] = 0
        # Fortress survives
        
    else:
        # Defender wins
        remaining = result['defender_survivors']
        # Update defender armies
        self.armies_unmoved[battle.territory] = remaining
        self.armies_moved[battle.territory] = 0
    
    # Store result
    battle.resolved = True
    battle.result = result
    
    # Check if all battles resolved
    if all(b.resolved for b in self.pending_battles):
        self.pending_battles = []
        self.turn_phase = 'planning'
        self.next_player()
```

---

## ðŸŽ¯ Edge Cases & Considerations

### 1. Territory Captured During Execution

**Scenario:**
```
Player 1 has orders:
- Order A: Territory X â†’ Territory Y (5 armies)
- Order B: Territory Z â†’ Territory X (3 armies)

Order A executes first, leaving X empty.
Order B targets now-empty friendly territory.
```

**Solution:**
- Validate all orders before execution
- Group simultaneous orders
- All armies leave source at same time
- Destinations determined by initial state

---

### 2. Multiple Armies Attacking Same Territory

**Scenario:**
```
Player 1 has orders:
- 5 armies from Territory A â†’ Enemy Territory X
- 3 armies from Territory B â†’ Enemy Territory X

Total: 8 armies attacking X
```

**Solution:**
- Sum all attacking armies
- Create single battle with combined force
- Combat calculation uses total

---

### 3. Circular Movement Orders

**Scenario:**
```
Order 1: A â†’ B
Order 2: B â†’ C
Order 3: C â†’ A
```

**Solution:**
- All orders execute simultaneously
- Armies "swap" positions
- No conflict because execution is atomic

---

### 4. Order Cancelled After Execution Started

**Solution:**
- Disable cancellation once "END TURN" clicked
- All buttons greyed out during execution
- Must wait for completion

---

### 5. No Battles to Resolve

**Scenario:**
- All movements were to neutral/friendly territories
- No enemies encountered

**Solution:**
- Skip battle phase entirely
- Go directly to next player
- No crossed swords appear

---

### 6. Player Disconnects During Battle Phase

**Solution:**
- Auto-resolve remaining battles
- Apply results automatically
- Continue to next player

---

### 7. Maximum Orders Limit

**Consideration:**
- Should there be a limit? (e.g., 10 orders per turn)
- Or unlimited orders?

**Recommendation:**
- No limit initially
- Can add limit later if needed for balance

---

## ðŸ“ Implementation Phases

### Phase 1: Core Order System â±ï¸ 2-3 hours

**Tasks:**
1. Add new data structures to GameState
2. Implement army selection (left-click on number)
3. Implement movement order creation (right-click)
4. Add order queue management
5. Create order validation logic

**Deliverable:**
- Can select armies
- Can create movement orders
- Orders stored in queue
- No visual indicators yet (basic functionality only)

---

### Phase 2: Visual Indicators â±ï¸ 1-2 hours

**Tasks:**
1. Draw movement arrows
2. Army selection glow effect
3. Order queue sidebar
4. End Turn button (basic)

**Deliverable:**
- Arrows appear for orders
- Selected armies highlighted
- Can see all pending orders
- Can click End Turn

---

### Phase 3: Order Execution â±ï¸ 2 hours

**Tasks:**
1. Implement execute_all_orders()
2. Auto-capture logic for neutral territories
3. Battle detection and creation
4. Turn phase transitions

**Deliverable:**
- Orders execute at turn end
- Empty neutrals captured automatically
- Battles created for enemy encounters
- Phase system working

---

### Phase 4: Battle Phase UI â±ï¸ 2 hours

**Tasks:**
1. Crossed swords markers
2. Battle popup window
3. Battle resolution UI
4. Result display

**Deliverable:**
- Can click battles to view
- Battle details shown
- Resolution works
- Results displayed clearly

---

### Phase 5: Polish & Testing â±ï¸ 1-2 hours

**Tasks:**
1. Order cancellation
2. Animation improvements
3. Sound effects (optional)
4. Edge case testing
5. Bug fixes

**Deliverable:**
- Smooth user experience
- No critical bugs
- Professional feel
- Ready for play

---

**Total Estimated Time: 8-10 hours**

---

## âœ… Success Criteria

### Must Have (Critical)

- [  ] Can select armies by clicking number
- [  ] Can issue movement orders via right-click
- [  ] Visual arrows show planned moves
- [  ] Can cancel orders before execution
- [  ] End Turn button executes all orders
- [  ] Empty neutrals captured automatically
- [  ] Enemy encounters create battles
- [  ] Battle phase requires manual resolution
- [  ] Crossed swords mark battle locations
- [  ] Battle popup shows details
- [  ] Combat uses existing fortress logic
- [  ] All battles must be resolved before next turn

### Should Have (Important)

- [  ] Order queue sidebar
- [  ] Selected army visual feedback
- [  ] Multiple orders from same territory
- [  ] Combined attacks work correctly
- [  ] Clear phase transitions
- [  ] Professional UI appearance

### Nice to Have (Optional)

- [  ] Army movement animation
- [  ] Sound effects
- [  ] Battle prediction in popup
- [  ] Order reordering
- [  ] Undo last order shortcut
- [  ] Keyboard shortcuts for common actions

---

## ðŸ”§ Technical Constraints

### Must Work With:

- âœ… Existing combat system (two-stage with fortress)
- âœ… Existing army tracking (moved/unmoved)
- âœ… Existing building system
- âœ… Existing territory ownership
- âœ… Existing turn system

### Can Modify:

- âœ… Turn flow (add phases)
- âœ… Mouse input handling (add right-click)
- âœ… UI layout (add sidebar, buttons)
- âœ… Message system (battle results)

### Cannot Break:

- âŒ Save/load functionality
- âŒ Victory conditions
- âŒ Economic system
- âŒ Building construction
- âŒ Multiplayer compatibility (if added later)

---

## ðŸ“ Notes & Considerations

### Design Philosophy

**"Plan Your Turn, Execute Your Plan"**
- Emphasis on strategic thinking
- No rush decisions
- Learn from seeing results
- Feels like a real strategy game

### Inspiration

Similar systems in:
- **Advance Wars**: Plan phase â†’ Execute phase
- **XCOM**: Action points â†’ Execute all â†’ Results
- **Civilization VI**: Move units â†’ Attack â†’ Resolve
- **Fire Emblem**: Plan turn â†’ Execute â†’ Combat

### Future Enhancements

Could add later:
- Retreat option during battles
- Ambush/terrain bonuses
- Weather effects
- Special abilities
- Alliance/team battles

---

## ðŸŽ¯ Next Steps

1. **Review this specification** âœ… (You are here)
2. **Design UI mockups** (Next document)
3. **Get approval** (From you!)
4. **Implement Phase 1** (Core order system)
5. **Iterate through phases**
6. **Test and polish**
7. **Deploy!**

---

**Specification Complete!**  
**Ready for UI Design Mockups!** ðŸŽ¨

---

**Document Version:** 1.0  
**Last Updated:** December 28, 2024  
**Status:** Ready for Review
