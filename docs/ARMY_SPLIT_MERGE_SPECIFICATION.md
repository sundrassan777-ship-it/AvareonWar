# Army Split/Merge System - Complete Specification

**Date:** December 30, 2024  
**Feature:** Advanced Army Management System  
**Status:** ðŸ“‹ SPECIFICATION  
**Complexity:** High (multi-phase implementation)

---

## ðŸŽ¯ Overview

A comprehensive army management system with individual army tracking, visual feedback for merges, and granular control over army movements.

---

## ðŸ“‹ Feature Breakdown

### Phase 1: Army Limit (Foundation) â­ IMPLEMENT FIRST
**Priority:** Critical  
**Complexity:** Low  
**Time Estimate:** 30-45 minutes

**Goal:** Prevent army spam by limiting territories to 15 armies maximum

---

### Phase 2: Merge Highlighting (Visual Feedback)
**Priority:** High  
**Complexity:** Medium  
**Time Estimate:** 30-45 minutes

**Goal:** Show visual feedback when armies are merging

---

### Phase 3: Army Composition UI (Advanced Control)
**Priority:** High  
**Complexity:** Very High  
**Time Estimate:** 2-3 hours

**Goal:** Individual army management with detailed UI

---

## ðŸ”¢ PHASE 1: Army Limit System

### Specification

**Limit:** Maximum 15 armies per territory

**Effects when at limit:**
1. Cannot recruit more armies in that territory
2. Training queues in Barracks pause
3. Cannot receive reinforcements (move orders to territory blocked)
4. Clear messaging to player

---

### Implementation Details

**1. Add Constant:**
```python
MAX_ARMIES_PER_TERRITORY = 15
```

**2. Check Before Recruitment:**
```python
def start_training(territory, barracks_plot_index, unit_type):
    # ... existing checks ...
    
    # Check army limit
    current_armies = self.armies.get(territory, 0)
    if current_armies >= MAX_ARMIES_PER_TERRITORY:
        self.add_message(f"Army limit reached! (Max {MAX_ARMIES_PER_TERRITORY} per territory)")
        return False
```

**3. Check Before Spawning:**
```python
def finish_training():
    # ... process queue ...
    
    # Before spawning:
    current_armies = self.armies[territory]
    if current_armies >= MAX_ARMIES_PER_TERRITORY:
        # Pause this unit (don't remove from queue, don't decrement timer)
        self.add_message(f"{territory}: Training paused (army limit reached)")
        continue  # Skip to next Barracks
```

**4. Check Before Reinforcement:**
```python
def execute_move_orders():
    # ... existing code ...
    
    # Before executing move to friendly territory:
    if owner_to == current_player:  # Reinforcement
        current_armies = self.armies[to_territory]
        if current_armies + army_count > MAX_ARMIES_PER_TERRITORY:
            # Block the move
            excess = (current_armies + army_count) - MAX_ARMIES_PER_TERRITORY
            self.add_message(f"Cannot reinforce {to_territory}: Would exceed army limit by {excess}")
            # Armies stay in from_territory
            continue
```

**5. UI Feedback:**
```python
# In recruitment UI:
if current_armies >= MAX_ARMIES_PER_TERRITORY:
    warning_text = "ARMY LIMIT REACHED (15/15)"
    # Display in red
    # Disable train button
```

---

## ðŸŽ¨ PHASE 2: Merge Highlighting

### Specification

**When:** Army is selected AND has a move order to friendly territory

**Visual:** Highlight destination army with special color (cyan/light blue)

**Purpose:** Show player "this army will merge here"

---

### Implementation Details

**1. Detect Merge Situation:**
```python
def is_merging(territory):
    """Check if selected army has move order to friendly territory"""
    if not self.game_state.selected_army:
        return False, None
    
    selected_territory, _ = self.game_state.selected_army
    
    # Check if this territory has a move order
    for order in self.game_state.movement_orders:
        if order.from_territory == selected_territory:
            # Check if destination is friendly
            dest_owner = self.game_state.territory_owners.get(order.to_territory, -1)
            if dest_owner == self.game_state.current_player:
                return True, order.to_territory
    
    return False, None
```

**2. Render Merge Highlight:**
```python
# In draw_territories(), after army selection highlight:
is_merge, merge_dest = self.is_merging()
if is_merge and merge_dest in self.scaled_polygons:
    # Draw cyan highlight around destination army
    cx, cy = self.scaled_centers[merge_dest]
    pygame.draw.circle(self.screen, (0, 200, 200), (cx, cy), 18, 3)  # Cyan ring
```

**3. Tooltip Enhancement:**
```python
# In army hover tooltip:
if has_merge_order:
    lines.append(("small", f"â†’ Merging with {dest_territory}", (0, 150, 150)))
```

---

## ðŸŽ® PHASE 3: Army Composition UI

### Specification

**Core Concept:** Treat each army as an individual unit that can be commanded separately

**UI Location:** Right panel (where army info/territory info shows)

**Visual:** Grid of buttons, each representing 1 army

---

### Data Structure Changes

**Current:**
```python
armies_unmoved = {territory: count}  # Just a number
armies_moved = {territory: count}  # Just a number
```

**New (needed for individual tracking):**
```python
army_units = {
    territory: [
        {'id': 1, 'status': 'ready', 'order': None},
        {'id': 2, 'status': 'ready', 'order': ('move', 'Gondor')},
        {'id': 3, 'status': 'moved', 'order': None},
        # ... up to 15 units
    ]
}
```

**Status values:**
- `'ready'` = Can be commanded (green)
- `'moved'` = Exhausted this turn (gray)
- `'ordered'` = Has pending order (yellow)

---

### UI Layout

**Army Composition Panel:**
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Army Composition: Naragonthid           â”‚
â”‚ Total: 10 armies                        â”‚
â”‚                                         â”‚
â”‚ [1] [2] [3] [4] [5]    â† Army buttons  â”‚
â”‚ [6] [7] [8] [9] [10]   (5 per row)     â”‚
â”‚                                         â”‚
â”‚ Selected: 3 armies                      â”‚
â”‚ â€¢ CTRL+Click to select multiple         â”‚
â”‚ â€¢ Right-click destination to move       â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**Button States:**
- **Green border:** Ready to command
- **Gray fill:** Exhausted (moved)
- **Yellow border:** Has order issued
- **Gold fill:** Currently selected

---

### Button Interactions

**1. Click Individual Army:**
```python
# Single click = select just this army
selected_army_units = [army_id]
```

**2. CTRL+Click:**
```python
# Add to selection
if pygame.key.get_mods() & pygame.KMOD_CTRL:
    if army_id in selected_army_units:
        selected_army_units.remove(army_id)  # Deselect
    else:
        selected_army_units.append(army_id)  # Add to selection
```

**3. Right-Click Destination:**
```python
# Create move order for all selected armies
for army_id in selected_army_units:
    if army_units[territory][army_id]['status'] == 'ready':
        # Create order for this specific army
        create_individual_order(territory, army_id, dest_territory)
```

---

### Hover Tooltips

**Hover over army button:**
```
Army #3
Status: Ready to Command
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Click to select
CTRL+Click for multi-select
```

**If has order:**
```
Army #5
Status: Ordered
Action: Attacking Mordor
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Click to select
```

**If exhausted:**
```
Army #7
Status: Exhausted
Moved this turn
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Cannot command until next turn
```

---

## ðŸ”§ Technical Challenges

### Challenge 1: Data Migration

**Problem:** Current system tracks totals, not individuals

**Solution:** Create migration function
```python
def migrate_to_individual_armies():
    for territory in self.armies.keys():
        total = self.armies[territory]
        unmoved = self.armies_unmoved[territory]
        moved = self.armies_moved[territory]
        
        # Create individual army units
        units = []
        for i in range(unmoved):
            units.append({'id': i, 'status': 'ready', 'order': None})
        for i in range(moved):
            units.append({'id': unmoved + i, 'status': 'moved', 'order': None})
        
        self.army_units[territory] = units
```

---

### Challenge 2: Order System

**Problem:** Current orders are territory-level, need unit-level

**Solution:** Two-tier system
- Keep existing MovementOrder for compatibility
- Add `army_unit_ids` list to orders
- When executing, move specific units

```python
class MovementOrder:
    def __init__(self, from_territory, to_territory, army_count, player, unit_ids=None):
        # ... existing ...
        self.unit_ids = unit_ids or []  # Specific armies to move
```

---

### Challenge 3: UI Complexity

**Problem:** Up to 15 buttons, need scrolling or pagination

**Solution:** Grid layout with 5 per row
```
Row 1: [1] [2] [3] [4] [5]
Row 2: [6] [7] [8] [9] [10]
Row 3: [11] [12] [13] [14] [15]

Each button: 40x40 pixels
Spacing: 5 pixels
Total height: 3 rows Ã— 45 = 135 pixels (fits in panel)
```

---

## ðŸ“Š Implementation Priority

### Immediate (Today):
1. âœ… Phase 1: Army Limit System
   - Foundation for all other features
   - Prevents technical debt
   - Simple to implement

### Next Session:
2. â¸ï¸ Phase 2: Merge Highlighting
   - Visual feedback
   - No data structure changes
   - Medium complexity

3. â¸ï¸ Phase 3: Army Composition UI
   - Major feature
   - Requires data migration
   - High complexity
   - Allow 2-3 hours

---

## ðŸŽ¯ Success Criteria

### Phase 1 Complete When:
- âœ… Cannot recruit beyond 15 armies
- âœ… Training pauses at limit
- âœ… Reinforcements blocked at limit
- âœ… Clear UI feedback

### Phase 2 Complete When:
- âœ… Merging armies show destination highlight
- âœ… Cyan ring around destination
- âœ… Tooltip shows merge info

### Phase 3 Complete When:
- âœ… Individual army buttons displayed
- âœ… Color-coded by status
- âœ… Single-click selection works
- âœ… CTRL+Click multi-select works
- âœ… Can issue orders to selection
- âœ… Hover tooltips show status
- âœ… Orders execute correctly

---

## âš ï¸ Known Limitations

### Army Limit:
- Fixed at 15 (could make configurable later)
- Applies to all players equally
- Cannot be bypassed

### Composition UI:
- Maximum 15 buttons (matches limit)
- No scrolling needed
- Clean, fixed layout

### Performance:
- 15 buttons per territory is manageable
- May need optimization for 50 territories
- Consider lazy loading (only show selected territory)

---

## ðŸš€ Recommended Approach

**For this session:**
1. Implement Phase 1 (Army Limit) completely
2. Test thoroughly
3. Document

**For next session:**
4. Implement Phase 2 (Merge Highlighting)
5. Test
6. Then tackle Phase 3 (Composition UI) as major feature

**Rationale:**
- Army Limit is foundation (prevents spam now)
- Merge Highlighting is quick win
- Composition UI needs dedicated time and focus

---

**Last Updated:** December 30, 2024  
**Status:** Specification Complete  
**Next:** Implement Phase 1 (Army Limit) ðŸš€
