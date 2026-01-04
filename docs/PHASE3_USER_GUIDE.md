# Phase 3 Quick Reference Guide

## Individual Army Management - User Guide

**Version:** 1.0  
**Date:** December 30, 2024  
**Status:** Production-Ready  

---

## Table of Contents
1. [Opening the Composition UI](#opening-the-composition-ui)
2. [Selecting Armies](#selecting-armies)
3. [Creating Orders](#creating-orders)
4. [Understanding Visual Feedback](#understanding-visual-feedback)
5. [Managing Orders](#managing-orders)
6. [Tips & Tricks](#tips--tricks)

---

## Opening the Composition UI

### How to Open
1. Click on an army circle on the map
2. The composition UI appears in the bottom panel

### UI Layout
```
┌───────────┬──────────────────┬────────────┬──────────────┐
│ Player    │  Army Info       │   Grid     │ Instructions │
│ Info      │                  │            │              │
│           │ Territory Name   │ [1][2][3]  │ How to use   │
│ Your gold │ Total: X armies  │ [4][5][6]  │              │
│ income    │ Status counts    │ [7][8][9]  │              │
│           │                  │            │              │
│ [End      │ [Select All]     │            │              │
│  Turn]    │ [Deselect All]   │            │              │
└───────────┴──────────────────┴────────────┴──────────────┘
```

### How to Close
- Click anywhere else on the map
- Click a different army
- Click a building plot
- Click End Turn

---

## Selecting Armies

### Single Selection
**Action:** Click an army button  
**Result:** Replaces current selection  
**Visual:** Clicked button turns gold  

### Multi-Selection
**Action:** Hold CTRL + Click army buttons  
**Result:** Toggles each army in/out of selection  
**Visual:** Gold buttons show selected armies  

### Select All
**Action:** Click "Select All" button  
**Result:** Selects all ready (green border) armies  
**Visual:** All ready armies turn gold  

### Deselect All
**Action:** Click "Deselect All" button  
**Result:** Clears all selections  
**Visual:** All buttons return to white  

---

## Creating Orders

### Basic Order
1. Open composition UI
2. Select armies (any method)
3. Right-click destination territory
4. Order created!

### Multiple Orders (Split Orders)
1. Select first group (e.g., armies 1-3)
2. Right-click first destination
3. Select second group (e.g., armies 4-6)
4. Right-click second destination
5. Continue as needed!

### Order Types
**Attack:** Right-click enemy or neutral territory  
**Reinforce:** Right-click your own territory  
**Stay:** Don't order those armies (leave them green)

---

## Understanding Visual Feedback

### Button Border Colors

**Green (3px thick):**
- Status: Ready
- Meaning: Can be commanded
- Action: Can select and order

**Yellow (3px thick):**
- Status: Ordered
- Meaning: Has pending order
- Action: Order will execute at turn end

**Gray (2px thin):**
- Status: Moved
- Meaning: Already moved this turn
- Action: Cannot select or command

### Button Fill Colors

**Gold:**
- Currently selected
- Will be affected by next order

**White:**
- Not selected
- Won't be affected by next order

### Map Indicators

**Green Glow:**
- Your selected army
- Source of potential orders

**Cyan Glow:**
- Friendly merge destination
- Your armies will reinforce here

**Red Glow:**
- Enemy attack destination
- Your armies will attack here

---

## Managing Orders

### Viewing Orders
Orders appear in the **Action Queue** sidebar (right side)

### Canceling Individual Order
1. Open Action Queue (click collapsed tab if needed)
2. Click [X] button on the order
3. Units return to ready (green) status

### Canceling All Orders
1. Open Action Queue
2. Look for "Cancel All" option (if available)
3. All units return to ready status

### Executing Orders
1. Click "End Turn" button
2. All orders execute simultaneously
3. Battles resolve if conflicts occur
4. Turn advances

---

## Tips & Tricks

### Efficient Selection

**Selecting most armies:**
1. Click "Select All" (selects all 15)
2. CTRL+Click units you want to KEEP (deselects them)
3. Right-click to order remaining
4. Faster than clicking each one!

**Selecting specific range:**
1. Click first army
2. CTRL+Click additional armies
3. Build selection precisely

---

### Strategic Splits

**3-Way Split:**
```
9 armies total:
- 3 armies → Attack Enemy A
- 3 armies → Reinforce Ally B
- 3 armies → Stay (defend)
```

**Multi-Front Assault:**
```
15 armies total:
- 5 armies → Main attack (Enemy A)
- 3 armies → Flanking attack (Enemy B)
- 3 armies → Flanking attack (Enemy C)
- 4 armies → Stay (defend/reserve)
```

**Redistribution:**
```
12 armies total:
- 4 armies → Weak ally A
- 4 armies → Weak ally B
- 4 armies → Weak ally C
Shore up multiple positions at once!
```

---

### Common Patterns

**"Leave One Behind"**
- Select all BUT one army
- Send the rest to attack/reinforce
- One army keeps territory controlled

**"Probe and Main Force"**
- Select 1-2 armies → Send to scout/probe
- Select 8-10 armies → Send as main force
- Flexible response based on intel

**"Cascade Reinforcement"**
- From strong position, reinforce multiple weak territories
- Creates defensive network
- Efficiently distributes forces

---

### Status Management

**Turn Start:**
- All armies reset to ready (green)
- Previous orders cleared
- Fresh planning phase

**After Orders:**
- Ordered armies yellow
- Can still modify before executing
- Cancel and reorder freely

**After Execution:**
- Moved armies gray
- Cannot move again this turn
- Will reset next turn

---

### Avoiding Mistakes

**Can't Select Same Unit Twice:**
If you try to order units that already have orders:
- System blocks with error
- Message shows which armies have orders
- Cancel existing order first, then reorder

**Army Limit Enforcement:**
If reinforcement would exceed 15:
- Order blocked
- Clear error message
- Armies remain at source

**Adjacency Required:**
- Can only order armies to adjacent territories
- Non-adjacent orders rejected
- Check map connections

---

## Keyboard Shortcuts

Currently available:
- **CTRL + Click:** Multi-select toggle
- **ESC:** (Future) Close composition UI
- **Tab:** (Future) Cycle through armies

---

## Advanced Techniques

### Feint and Flank
1. Order small force to obvious target (draw attention)
2. Order main force to real target (unexpected)
3. Execute simultaneously (enemy can't react)

### Rolling Reinforcement
1. Order armies from multiple territories
2. All target same weak ally
3. Mass reinforcement in one turn

### Distributed Defense
1. From central position
2. Order 1-2 armies to each border territory
3. Create defensive perimeter

---

## Troubleshooting

**UI Won't Open:**
- Make sure territory has armies (circle not empty)
- Try clicking directly on the army circle
- Check you're in planning phase

**Can't Select Armies:**
- Gray borders = moved (can't select)
- Yellow borders = already ordered (cancel first)
- Only green borders are selectable

**Orders Not Executing:**
- Click "End Turn" to execute
- Resolve any battles first
- Check for error messages

**Display Shows Wrong Count:**
- This bug is fixed in latest version
- All displays should match (circle, tooltip, panel)
- If not matching, report as bug

---

## Quick Command Reference

| Action | Method |
|--------|--------|
| Open UI | Click army circle |
| Close UI | Click elsewhere |
| Select one | Click button |
| Multi-select | CTRL + Click |
| Select all | Click "Select All" |
| Deselect all | Click "Deselect All" |
| Create order | Right-click destination |
| Cancel order | Click [X] in sidebar |
| Execute orders | Click "End Turn" |

---

## Status Reference

| Color | Status | Can Select? | Can Order? | Meaning |
|-------|--------|-------------|------------|---------|
| Green | Ready | ✅ Yes | ✅ Yes | Available |
| Yellow | Ordered | ❌ No | ❌ No | Has order |
| Gray | Moved | ❌ No | ❌ No | Exhausted |

---

## Examples

### Example 1: Simple Attack
```
Territory A: 10 armies
Goal: Attack Territory B with 5 armies

Steps:
1. Click army in Territory A
2. Click armies 1-5 (or use select all, then CTRL+click 6-10 to deselect)
3. Right-click Territory B
4. Armies 1-5 turn yellow
5. End Turn to execute
```

### Example 2: Split Force
```
Territory A: 9 armies
Goal: 3 attack, 3 reinforce, 3 stay

Steps:
1. Click army in Territory A
2. Click armies 1-3
3. Right-click Enemy Territory (attack)
4. Click armies 4-6
5. Right-click Ally Territory (reinforce)
6. Leave armies 7-9 unselected
7. End Turn to execute
```

### Example 3: Mass Selection
```
Territory A: 15 armies
Goal: Send 13 armies, keep 2

Steps:
1. Click army in Territory A
2. Click "Select All" (all 15 selected)
3. CTRL+Click army 14 (deselect)
4. CTRL+Click army 15 (deselect)
5. Right-click destination (13 selected)
6. End Turn to execute
```

---

## Getting Help

**In-Game Help:**
- Instructions shown in right section of composition UI
- Hover tooltips show territory info
- Error messages explain what went wrong

**Common Issues:**
- Most issues are user error (wrong phase, wrong status)
- Check border colors to understand army status
- Cancel orders if you made a mistake

**Reporting Bugs:**
- Note exact steps to reproduce
- Screenshot helpful
- Check if already fixed in latest version

---

**Last Updated:** December 30, 2024  
**Version:** 1.0  
**Status:** Complete ✅
