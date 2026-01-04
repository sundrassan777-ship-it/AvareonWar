# Advanced Army Movement System - UI Design Document

**Feature:** TIER 2B - Feature #17  
**Document:** UI/UX Design Mockups  
**Date:** December 28, 2024  
**Status:** 🎨 DESIGN PHASE

---

## 🎨 Design Overview

This document provides detailed visual mockups, color schemes, dimensions, and interactive specifications for all UI elements in the Advanced Army Movement & Battle System.

---

## 🖼️ Screen Layout Mockups

### Full Screen Layout - Planning Phase

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PLAYER 1's TURN  │  💰 150g  │  📈 +45g/turn  │  🔄 Turn 5  │  ⚙️ Settings  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┫
┃                                                          ┃                  ┃
┃                                                          ┃  MOVEMENT ORDERS ┃
┃        ┌─────────────┐                                   ┃ ┌──────────────┐ ┃
┃        │  Amennia    │                                   ┃ │ 📍 5 armies  │ ┃
┃        │   ┏━━━┓     │                                   ┃ │ Amennia →    │ ┃
┃        │   ┃ 5 ┃     │←─────────────────────────────────┃ │ Brundisium ❌│ ┃
┃        │   ┗━━━┛     │  Green glow (selected)            ┃ └──────────────┘ ┃
┃        └─────────────┘                                   ┃                  ┃
┃              │                                            ┃ ┌──────────────┐ ┃
┃              │ [5]  ← Green arrow                        ┃ │ 📍 3 armies  │ ┃
┃              ↓                                            ┃ │ Cannae →     │ ┃
┃        ┌─────────────┐                                   ┃ │ Tarentum   ❌│ ┃
┃        │ Brundisium  │                                   ┃ └──────────────┘ ┃
┃        │             │                                   ┃                  ┃
┃        │      0      │                                   ┃ [CANCEL ALL]     ┃
┃        └─────────────┘                                   ┃                  ┃
┃                           ┌─────────────┐                ┃                  ┃
┃                           │  Tarentum   │  ← Enemy (red) ┃                  ┃
┃                           │             │                ┃                  ┃
┃   MAP AREA                │      3      │                ┃                  ┃
┃   (Territory polygons)    └─────────────┘                ┃                  ┃
┃                                ↑                          ┃                  ┃
┃                           [3]  │  ← Green arrow           ┃                  ┃
┃                                │                          ┃                  ┃
┃                           ┌─────────────┐                ┃                  ┃
┃                           │   Cannae    │                ┃                  ┃
┃                           │      3      │                ┃                  ┃
┃                           └─────────────┘                ┃                  ┃
┃                                                          ┃                  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━┫
┃  📜 ACTION LOG                         ┃  💡 TIPS                           ┃
┃  ─────────────                         ┃  ─────                             ┃
┃  → Player 1's turn                     ┃  Right-click to move armies        ┃
┃  → Farm completed in Roma              ┃  Click army number to select       ┃
┃  → Income: +45 gold                    ┃  Click [X] to cancel orders        ┃
┃                                        ┃                                    ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                                                                              ┃
┃                        ┏━━━━━━━━━━━━━━━━━━━━━━┓                            ┃
┃                        ┃                      ┃                            ┃
┃                        ┃     END TURN        ┃  ← Large, prominent         ┃
┃                        ┃   (SPACE / ENTER)   ┃                            ┃
┃                        ┃                      ┃                            ┃
┃                        ┗━━━━━━━━━━━━━━━━━━━━━━┛                            ┃
┃                                                                              ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Screen Resolution: 1400x900 (recommended minimum)
```

---

### Full Screen Layout - Battle Phase

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PLAYER 1's TURN  │  💰 150g  │  📈 +45g/turn  │  🔄 Turn 5  │  ⚙️ Settings  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┫
┃                                                          ┃                  ┃
┃                                                          ┃  ⚔️ BATTLES       ┃
┃        ┌─────────────┐                                   ┃ ┌──────────────┐ ┃
┃        │  Amennia    │                                   ┃ │              │ ┃
┃        │             │                                   ┃ │  2 BATTLES   │ ┃
┃        │      5      │                                   ┃ │   PENDING    │ ┃
┃        └─────────────┘                                   ┃ │              │ ┃
┃                                                          ┃ └──────────────┘ ┃
┃              ┌─────────────┐                             ┃                  ┃
┃              │ Brundisium  │                             ┃ ┌──────────────┐ ┃
┃              │             │                             ┃ │ Tarentum     │ ┃
┃              │      5      │                             ┃ │ ⚔️ PENDING   │ ┃
┃              └─────────────┘                             ┃ │ [CLICK ME]   │ ┃
┃                           ┌─────────────┐ ← Pulsing red  ┃ └──────────────┘ ┃
┃                           │  Tarentum   │    glow        ┃                  ┃
┃   MAP AREA                │             │                ┃ ┌──────────────┐ ┃
┃   (Territory polygons)    │     ⚔️     │ ← Crossed swords┃ │ Cannae       │ ┃
┃                           │             │                ┃ │ ⚔️ PENDING   │ ┃
┃                           └─────────────┘                ┃ │ [CLICK ME]   │ ┃
┃                                                          ┃ └──────────────┘ ┃
┃                           ┌─────────────┐                ┃                  ┃
┃                           │   Cannae    │ ← Pulsing red  ┃                  ┃
┃                           │             │    glow        ┃                  ┃
┃                           │     ⚔️     │                ┃                  ┃
┃                           └─────────────┘                ┃                  ┃
┃                                                          ┃                  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━┫
┃  📜 ACTION LOG                         ┃  💡 TIPS                           ┃
┃  ─────────────                         ┃  ─────                             ┃
┃  → Armies moved                        ┃  Click battle territories to       ┃
┃  → Captured Brundisium                 ┃  view details and resolve          ┃
┃  → 2 battles created                   ┃                                    ┃
┃  → Resolve battles to continue         ┃                                    ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                                                                              ┃
┃                        ┏━━━━━━━━━━━━━━━━━━━━━━┓                            ┃
┃                        ┃                      ┃  ← Greyed out, disabled     ┃
┃                        ┃  RESOLVE BATTLES    ┃                            ┃
┃                        ┃  (Click battles)    ┃                            ┃
┃                        ┃                      ┃                            ┃
┃                        ┗━━━━━━━━━━━━━━━━━━━━━━┛                            ┃
┃                                                                              ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

## 🎯 UI Element Detailed Specifications

### 1. Army Selection Indicator

**Visual States:**

**UNSELECTED (Default):**
```
┌─────────────────┐
│   Territory     │  Border: 2px solid #333333
│                 │
│        5        │  Number: 36px, white, centered
│                 │
└─────────────────┘
```

**SELECTED:**
```
┏━━━━━━━━━━━━━━━━━┓  Border: 4px solid #00FF00 (green glow)
┃   Territory     ┃  Brightness: +20%
┃                 ┃  Pulse: Subtle (1s cycle, 90%-110% opacity)
┃      ┏━━━┓      ┃
┃      ┃ 5 ┃      ┃  Number box: 50x50px, green background
┃      ┗━━━┛      ┃  Box border: 2px solid #00CC00
┗━━━━━━━━━━━━━━━━━┛
```

**HOVERABLE (Mouse over unselected):**
```
┌─────────────────┐
│   Territory     │  Border: 3px solid #00AA00 (lighter green)
│                 │  Cursor: pointer
│        5        │  Brightness: +10%
│                 │
└─────────────────┘
```

**Dimensions:**
- Border width (selected): 4px
- Border width (unselected): 2px
- Number box size: 50x50px
- Number font size: 36px (bold)
- Glow radius: 8px

**Colors:**
- Selected border: RGB(0, 255, 0) - Bright green
- Number box background: RGB(0, 200, 0, 128) - Semi-transparent green
- Hover border: RGB(0, 170, 0) - Medium green
- Default border: RGB(51, 51, 51) - Dark grey

**Animation:**
- Pulse frequency: 1 second
- Pulse range: 90% to 110% opacity
- Transition: Smooth ease-in-out

---

### 2. Movement Arrow Design

**Arrow Structure:**

```
  Source Territory Center
           │
           │  ┌─────┐
           │  │ [5] │  ← Badge (army count)
           │  └─────┘
           │
           ↓
           │
           ▼  ← Arrowhead (triangle)
           
  Destination Territory Center
```

**Detailed Measurements:**

```
       Start Point (source territory center)
              │
              │ Line: 3px width, RGB(0, 200, 0)
              │
              │
        ┌─────────┐
        │   [5]   │ Badge: 30x30px circle
        └─────────┘ Background: RGB(255, 255, 255)
              │     Border: 2px RGB(0, 200, 0)
              │     Text: 16px bold, black
              │
              │
              ▼
         ╱    ╲   Arrowhead: 16px wide, 12px tall
        ╱      ╲  Color: RGB(0, 200, 0)
       ◀────────▶ Filled triangle
              
       End Point (destination territory center)
```

**Badge Position:**
- Placed at midpoint of line
- Offset: 0px (centered on line)
- Z-index: Above line, below territories

**Multiple Arrows from Same Territory:**
```
  Territory A (center point)
       │
       ├──────────→ [5] → Territory B
       │
       ├──────────→ [3] → Territory C
       │
       └──────────→ [2] → Territory D

Arrows fan out from center
Angle spread: 30° between each arrow
```

**Hover Effect:**
```
When mouse over arrow:
- Line width: 3px → 5px
- Color: RGB(0, 200, 0) → RGB(0, 255, 0) (brighter)
- Badge size: 30x30px → 36x36px
- Cursor: pointer
- Shows tooltip: "Click to cancel order"
```

**Click to Cancel:**
```
When arrow clicked:
- Flash red briefly (200ms)
- Fade out (300ms)
- Remove from queue
- Update sidebar
```

---

### 3. Movement Orders Sidebar

**Full Sidebar Design:**

```
┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  MOVEMENT ORDERS      ┃  Header: 24px bold, white
┣━━━━━━━━━━━━━━━━━━━━━━━┫  Line: 2px solid white
┃                       ┃
┃  ┌─────────────────┐  ┃  ← Order entry (50px height)
┃  │ 📍 5            │  ┃     Background: #2a2a2a
┃  │ Amennia →       │  ┃     Border: 1px solid #444
┃  │ Brundisium   ❌ │  ┃     Padding: 8px
┃  └─────────────────┘  ┃
┃                       ┃  ← 10px gap
┃  ┌─────────────────┐  ┃
┃  │ 📍 3            │  ┃
┃  │ Cannae →        │  ┃
┃  │ Tarentum     ❌ │  ┃
┃  └─────────────────┘  ┃
┃                       ┃
┃  ┌─────────────────┐  ┃
┃  │ 📍 2            │  ┃
┃  │ Roma →          │  ┃
┃  │ Arretium     ❌ │  ┃
┃  └─────────────────┘  ┃
┃                       ┃
┃  [Empty slots]        ┃  ← Fills remaining space
┃                       ┃
┣━━━━━━━━━━━━━━━━━━━━━━━┫
┃                       ┃
┃  ┌─────────────────┐  ┃  ← Cancel All button
┃  │  CANCEL ALL  ❌ │  ┃     40px height
┃  └─────────────────┘  ┃     Red background on hover
┃                       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┛

Width: 250px
Position: Right side of screen
Top: Below player info bar
```

**Order Entry Detail:**

```
┌───────────────────────────┐
│ 📍 5        ← Army count   │  Left section: 60px
│ Amennia →   ← Source       │  Icon: 20x20px
│ Brundisium  ← Destination  │  Font: 14px
│             ❌ ← Cancel    │  Right: 30px for X button
└───────────────────────────┘

Text layout:
Line 1: Icon [space] Count
Line 2: Source name →
Line 3: Destination name

Text color: White
Hover: Background #3a3a3a
```

**Cancel Button (❌):**
- Size: 24x24px
- Position: Top-right of entry
- Color: #ff4444 (red)
- Hover: #ff6666 (lighter red)
- Click: Flash effect
- Font: 18px, bold

**Cancel All Button:**
```
┌─────────────────────┐
│   CANCEL ALL ❌     │  Height: 40px
└─────────────────────┘  Background: #444444
                         Hover: #ff4444 (red)
                         Text: 16px bold, white
                         Border: 2px solid #666
```

**Scrolling:**
- If > 10 orders: Enable scroll
- Scrollbar: 8px width, right edge
- Scrollbar color: #555555
- Thumb color: #888888

---

### 4. End Turn Button

**Button States:**

**ACTIVE (Can End Turn):**
```
┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃                       ┃  Background: RGB(100, 200, 100)
┃      END TURN        ┃  Border: 4px solid RGB(50, 150, 50)
┃   (SPACE / ENTER)    ┃  Shadow: 0 4px 8px rgba(0,0,0,0.3)
┃                       ┃  Size: 250px x 80px
┗━━━━━━━━━━━━━━━━━━━━━━━┛  Font: 28px bold, white
                          Cursor: pointer
```

**HOVER:**
```
┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃                       ┃  Background: RGB(120, 220, 120) (brighter)
┃      END TURN        ┃  Border: 4px solid RGB(80, 180, 80)
┃   (SPACE / ENTER)    ┃  Shadow: 0 6px 12px rgba(0,0,0,0.4)
┃                       ┃  Scale: 105%
┗━━━━━━━━━━━━━━━━━━━━━━━┛  Transition: 0.2s ease
```

**EXECUTING (Disabled):**
```
┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃                       ┃  Background: RGB(120, 120, 120)
┃    EXECUTING...      ┃  Border: 4px solid RGB(80, 80, 80)
┃      ⏳              ┃  Text: Grey
┃                       ┃  Cursor: not-allowed
┗━━━━━━━━━━━━━━━━━━━━━━━┛  Loading spinner icon
```

**BATTLE PHASE (Disabled):**
```
┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃                       ┃  Background: RGB(150, 80, 80)
┃  RESOLVE BATTLES     ┃  Border: 4px solid RGB(100, 50, 50)
┃  (Click battles)     ┃  Pulse: Slow (2s cycle)
┃        ⚔️           ┃  Cursor: not-allowed
┗━━━━━━━━━━━━━━━━━━━━━━━┛
```

**Position:**
- Bottom-center of screen
- Margin-bottom: 20px
- Z-index: 100 (always on top)

**Animations:**
- Hover: Scale 105%, brightness +10%, shadow larger
- Click: Scale 95% for 100ms, then execute
- Disabled: Greyscale filter

---

### 5. Battle Markers (Crossed Swords)

**Icon Design:**

```
     ⚔️
    ╱╲╱╲
   ╱  X  ╲
  ╱   │   ╲
 ╱    │    ╲
      │
   [Handle]

Size: 48x48 pixels
Position: Center of territory
Z-index: Above territory, below popup
```

**Alternative ASCII Art:**
```
    ╱╲
   ╱  ╲
  ╱ ⚔ ╲
  ╲    ╱
   ╲  ╱
    ╲╱
```

**Color Scheme:**
- Swords: Metallic silver RGB(192, 192, 192)
- Outline: Black 2px
- Glow: Red pulsing RGB(255, 0, 0)

**Pulsing Animation:**
```
Cycle: 1.5 seconds
Opacity: 60% → 100% → 60%
Glow radius: 4px → 8px → 4px
Rotation: None (stays fixed)
```

**Territory Highlighting:**
```
Battle territory gets:
- Border: 4px solid red
- Border pulse: Same as icon
- Background tint: +10% red
- Cursor: pointer (clickable)
```

---

### 6. Battle Popup Window

**Popup Design - Before Resolution:**

```
                Screen dims to 70% opacity
                         │
                         ↓
    ╔═══════════════════════════════════════╗
    ║   ⚔️  BATTLE AT TARENTUM  ⚔️         ║  Header: 28px bold
    ╠═══════════════════════════════════════╣  Background: #1a1a1a
    ║                                       ║  Border: 4px solid #ff4444
    ║  👤 Attacker (Player 1):             ║
    ║     ▓▓▓▓▓ 5 armies                   ║  Army bars
    ║                                       ║  Each ▓ = 1 army
    ║  🛡️ Defender (Player 2):             ║
    ║     ▓▓▓ 3 armies                     ║
    ║     🏰 +2 Fortress bonus              ║  Fortress icon
    ║                                       ║
    ║  ─────────────────────────────────    ║  Divider line
    ║                                       ║
    ║  📊 Predicted Outcome:                ║
    ║     ⚠️ Close battle!                 ║  Color-coded:
    ║     Fortress may hold                 ║  Green = Win
    ║                                       ║  Red = Lose
    ║                                       ║  Yellow = Close
    ║  ┌─────────────────────────────────┐  ║
    ║  │                                 │  ║
    ║  │     RESOLVE BATTLE              │  ║  Button: 300x60px
    ║  │                                 │  ║  Green background
    ║  └─────────────────────────────────┘  ║
    ║                                       ║
    ║  (Click outside to view other battles)║  Help text
    ║                                       ║
    ╚═══════════════════════════════════════╝

Size: 500px x 450px
Position: Center of screen
Shadow: 0 8px 32px rgba(0, 0, 0, 0.6)
```

**Popup Design - After Resolution:**

```
    ╔═══════════════════════════════════════╗
    ║   ⚔️  BATTLE RESULT  ⚔️              ║
    ╠═══════════════════════════════════════╣
    ║                                       ║
    ║  Stage 1 (Army Combat):               ║
    ║  5 attackers vs 3 defenders           ║
    ║  → Attacker wins with 2 survivors     ║
    ║                                       ║
    ║  Stage 2 (Fortress Assault):          ║
    ║  2 survivors vs +2 Fortress           ║
    ║  → FORTRESS HOLDS!                    ║  Large text
    ║                                       ║  Colored based on
    ║  ─────────────────────────────────    ║  result
    ║                                       ║
    ║  ✅ Territory still defended!         ║
    ║  ❌ All attackers eliminated          ║
    ║  ❌ All defenders eliminated          ║
    ║  ✅ Fortress survives                 ║
    ║                                       ║
    ║  ┌─────────────────────────────────┐  ║
    ║  │                                 │  ║
    ║  │       CONTINUE                  │  ║  Button: 300x60px
    ║  │                                 │  ║  Blue background
    ║  └─────────────────────────────────┘  ║
    ║                                       ║
    ╚═══════════════════════════════════════╝
```

**Popup Elements:**

**Header:**
- Background: Gradient #2a2a2a to #1a1a1a
- Font: 28px bold, white
- Icons: ⚔️ on both sides, 24x24px
- Padding: 20px

**Content Area:**
- Background: #1a1a1a
- Padding: 30px
- Font: 18px, white
- Line spacing: 1.5

**Army Visualization:**
```
Attacker: ▓▓▓▓▓ 5 armies
          └─┘
Each block = 1 army
Block size: 20x20px
Spacing: 4px
Color: Green for attacker, Blue for defender
```

**Fortress Indicator:**
```
🏰 +2 Fortress bonus
│   │
│   └─ Bonus value (large, yellow)
└───── Castle emoji or icon (32x32px)
```

**Prediction Text Colors:**
- Victory likely: RGB(0, 200, 0) - Green
- Defeat likely: RGB(200, 0, 0) - Red
- Close battle: RGB(200, 200, 0) - Yellow
- Fortress hold: RGB(150, 150, 255) - Light blue

**Resolve Button:**
```
┌─────────────────────────────────┐
│                                 │
│     RESOLVE BATTLE              │  Size: 300x60px
│                                 │  Font: 24px bold
└─────────────────────────────────┘  Hover: Scale 105%

States:
- Default: Green RGB(80, 180, 80)
- Hover: Bright green RGB(100, 200, 100)
- Click: Dark green RGB(60, 160, 60)
```

**Continue Button:**
```
┌─────────────────────────────────┐
│                                 │
│        CONTINUE                 │  Size: 300x60px
│                                 │  Font: 24px bold
└─────────────────────────────────┘

States:
- Default: Blue RGB(80, 120, 180)
- Hover: Bright blue RGB(100, 140, 200)
```

**Close/Dismiss:**
- Click outside popup: Return to battle view
- ESC key: Return to battle view
- Cannot close during battle phase

---

### 7. Battle Counter Badge

**Badge Design:**

```
┌───────────────────┐
│   ⚔️ 3 BATTLES   │  Size: 180px x 60px
│     PENDING       │  Position: Top-right corner
└───────────────────┘  Below settings icon

Colors:
- Background: RGB(180, 50, 50) - Red
- Border: 3px solid RGB(150, 30, 30)
- Text: White, 18px bold
- Icon: ⚔️ 24x24px
- Pulse: Yes (matches battle markers)

Only visible during battle phase
```

**Animations:**
- Appears: Slide in from right (300ms)
- Pulse: 1.5s cycle, same as battle markers
- Updates: Number fades when battle resolved
- Disappears: Fade out when all battles done

---

### 8. Territory Highlighting Effects

**Adjacent Territory Highlighting (When Army Selected):**

```
Selected army: Amennia
Adjacent territories get:

┌─────────────┐
│  Brundisium │  ← Can move here
│             │  Border: 2px dashed green
│      0      │  Opacity: +20%
└─────────────┘  Cursor: crosshair (for right-click)

vs.

┌─────────────┐
│  Tarentum   │  ← Enemy territory
│             │  Border: 2px dashed yellow
│      3      │  Opacity: +20%
└─────────────┘  Cursor: crosshair
```

**Highlighting Rules:**
- Friendly adjacent: Green dashed border
- Enemy adjacent: Yellow dashed border  
- Non-adjacent: Dimmed to 70%
- Border thickness: 2px
- Border style: Dashed (5px dash, 3px gap)

---

## 🎨 Color Palette

### Primary Colors

```
GREEN (Success, Movement, Active):
- Light:  RGB(120, 220, 120) #78DC78
- Medium: RGB(100, 200, 100) #64C864
- Dark:   RGB(80, 180, 80)   #50B450
- Accent: RGB(0, 255, 0)     #00FF00

RED (Battle, Danger, Cancel):
- Light:  RGB(220, 100, 100) #DC6464
- Medium: RGB(200, 80, 80)   #C85050
- Dark:   RGB(180, 50, 50)   #B43232
- Accent: RGB(255, 0, 0)     #FF0000

BLUE (Info, Defender):
- Light:  RGB(120, 160, 220) #78A0DC
- Medium: RGB(100, 140, 200) #648CC8
- Dark:   RGB(80, 120, 180)  #5078B4

YELLOW (Warning, Close):
- Light:  RGB(240, 240, 120) #F0F078
- Medium: RGB(220, 220, 100) #DCDC64
- Dark:   RGB(200, 200, 80)  #C8C850

GREY (Disabled, Background):
- Light:  RGB(170, 170, 170) #AAAAAA
- Medium: RGB(120, 120, 120) #787878
- Dark:   RGB(80, 80, 80)    #505050
- Darker: RGB(40, 40, 40)    #282828
```

### UI Element Color Assignments

```
Selected Army Border:      GREEN Accent
Movement Arrow:            GREEN Medium
Order Queue Background:    GREY Darker
Battle Marker:             RED Accent
Battle Territory Border:   RED Medium
End Turn Button (Active):  GREEN Medium
End Turn Button (Disabled):GREY Medium
Battle Popup Border:       RED Dark
Friendly Highlight:        GREEN Light
Enemy Highlight:           YELLOW Medium
Background Dim:            BLACK 70% opacity
```

---

## 📐 Responsive Design Considerations

### Minimum Screen Resolution

```
Minimum: 1280x800
Recommended: 1400x900
Optimal: 1920x1080
```

### Scaling Rules

**For screens < 1400px wide:**
- Sidebar width: 250px → 200px
- Font sizes: -2px
- Button sizes: -20%
- Map area: Adjusts to remaining space

**For screens > 1920px wide:**
- Maintain aspect ratios
- Center content with margins
- Don't scale fonts beyond 150%

---

## 🖱️ Mouse Cursor States

```
Default territory:        arrow (default)
Selectable army:          pointer
Selected army:            pointer
Adjacent territory:       crosshair (right-click ready)
Movement arrow:           pointer (can cancel)
Order entry [X]:          pointer
Battle territory:         pointer
Popup background:         default (can click to dismiss)
Button hover:             pointer
Disabled element:         not-allowed
```

---

## ⌨️ Keyboard Shortcuts

```
ENTER / SPACE:  End Turn
ESC:            Cancel selection / Close popup
R:              (Reserved for Recruit - future)
1-9:            Select territory by number (future)
U:              Undo last order
A:              Select all armies (future)
```

---

## 🎬 Animation Timings

```
Army Selection Glow:      1.0s cycle (pulse)
Battle Marker Pulse:      1.5s cycle
Movement Arrow Hover:     0.2s transition
Button Hover:             0.2s transition
Button Click:             0.1s (scale down)
Popup Appear:             0.3s (fade + scale)
Popup Dismiss:            0.2s (fade)
Order Cancel:             0.3s (fade out)
Battle Counter Appear:    0.3s (slide in)
Phase Transition:         0.5s (full screen fade)
```

---

## 📱 Accessibility Features

### Color Blind Support

```
Green-Red Color Blindness:
- Add icons to colors (✓ for green, ✗ for red)
- Use patterns in addition to colors
- High contrast mode option

Recommendations:
- Army selection: Add "SELECTED" text
- Arrows: Add directional icons
- Battles: Add "BATTLE" text label
```

### Screen Reader Support

```
All clickable elements need aria-labels:
- "Select army in [Territory]"
- "Move to [Territory] - Right click"
- "Cancel order: [Source] to [Destination]"
- "Resolve battle at [Territory]"
- "End turn"
```

### Text Size Options

```
Small:  100% (default)
Medium: 120%
Large:  150%

Affects: All UI text except map labels
Adjusts: Button sizes proportionally
```

---

## 🎯 UI States Summary

### Global States

1. **Planning Phase**
   - End Turn button: Active (green)
   - Armies: Selectable
   - Orders sidebar: Visible
   - Battle markers: Hidden

2. **Execution Phase**
   - End Turn button: Disabled (grey, "Executing...")
   - Armies: Moving (animated, optional)
   - UI: Partially locked
   - Duration: 1-2 seconds

3. **Battle Phase**
   - End Turn button: Disabled (red, "Resolve Battles")
   - Battle markers: Visible, pulsing
   - Battle counter: Visible
   - Territories: Clickable to resolve

---

## 📋 Implementation Checklist

### Visual Elements to Create

- [ ] Movement arrow sprite/drawing code
- [ ] Crossed swords icon (⚔️)
- [ ] Battle popup window frame
- [ ] Order queue sidebar frame
- [ ] End Turn button (all 3 states)
- [ ] Army selection glow effect
- [ ] Territory highlight overlays
- [ ] Battle counter badge
- [ ] Loading/executing spinner

### UI States to Code

- [ ] Army selection (on/off)
- [ ] Adjacent territory highlighting
- [ ] Order queue display
- [ ] Movement arrow rendering
- [ ] Battle marker placement
- [ ] Popup show/hide
- [ ] Button state changes
- [ ] Phase transitions

### Interactive Elements

- [ ] Left-click army selection
- [ ] Right-click movement order
- [ ] Order cancellation (X button)
- [ ] Cancel All button
- [ ] End Turn button
- [ ] Battle territory click
- [ ] Resolve battle button
- [ ] Continue button
- [ ] ESC key handling
- [ ] ENTER/SPACE key handling

---

## 🎨 Final Design Notes

### Design Philosophy

**"Clear at a Glance, Detailed on Demand"**

- Planning phase: See all orders clearly
- Battle phase: Know where to click
- Results: Understand what happened
- Always: Visual feedback for every action

### Inspiration Sources

- **Advance Wars**: Clear grid, bright colors
- **XCOM**: Tactical planning UI
- **Civilization VI**: Turn-based flow
- **Total War**: Battle resolution
- **Fire Emblem**: Army selection

### Future Enhancements

Could add later:
- Movement path preview (multi-step)
- Unit portraits/icons
- Sound effects on actions
- Battle result animations
- Victory/defeat screens
- Replay battle option
- Statistics tracking

---

**UI Design Complete!** ✨  
**Ready for Implementation!** 🚀

---

**Document Version:** 1.0  
**Last Updated:** December 28, 2024  
**Status:** Ready for Development
