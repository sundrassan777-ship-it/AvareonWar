# Army Training System - Queue-Based Recruitment

**Date:** December 29, 2024  
**Feature:** Queue-Based Army Training (TIER 2B)  
**Status:** âœ… FULLY IMPLEMENTED!  
**Design:** Plot-like UI with training queues

---

## ðŸŽ¯ Design Philosophy

**The training system works exactly like building plots:**
- Click Barracks â†’ Bottom UI panel opens
- Training button (like building buttons)
- Queue system on the right (like order sidebar)
- Future-proof for multiple unit types

**This creates consistency with existing systems!**

---

## ðŸ“‹ How It Works

### Basic Flow

**1. Click a Barracks building on the map**
- Map plot with "B" icon
- Opens training UI in bottom panel

**2. Bottom UI shows training interface**
- Left side: Train button (like building buttons)
- Right side: Training queue (up to 5 units)

**3. Click "Train Swordsman" button**
- Costs 25 gold
- Adds to queue
- Takes 1 turn to train

**4. At start of next turn**
- Unit completes training
- Spawns as "moved" army (can't move this turn)
- Next unit in queue starts training

---

## ðŸ’° Training System Details

### Requirements

**To train a unit:**
- âœ… Must own the territory
- âœ… Must have completed Barracks
- âœ… Must have 25 gold
- âœ… Queue must have space (max 5)

### Training Time
- **1 turn** per unit
- Units train sequentially (not simultaneously in same Barracks)
- Multiple Barracks in territory = multiple queues = simultaneous training!

### Unit Spawning
- Spawns at **start of your turn**
- Spawns as **"moved"** army
- Cannot move until next turn
- Logical: Needs time to consolidate

---

## ðŸŽ® UI Design

### Bottom Panel Layout

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Barracks in [Territory Name]                                â”‚
â”‚ Gold: 150                                                    â”‚
â”‚                                                              â”‚
â”‚ â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”‚   Training Queue:               â”‚
â”‚ â”‚ Train Swordsman    â”‚   â”‚   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”‚
â”‚ â”‚      (25g)         â”‚   â”‚   â”‚ Swordsman (training..â”‚  X  â”‚
â”‚ â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚   â”‚ 1 turn)             â”‚     â”‚
â”‚                           â”‚   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â”‚
â”‚ Queue: 1/5                â”‚   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”‚
â”‚                           â”‚   â”‚ Swordsman (waiting)  â”‚  X  â”‚
â”‚                           â”‚   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜     â”‚
â”‚                           â”‚                                 â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
     â†‘                             â†‘
  Training                       Queue with
   Button                    cancel buttons
```

### Button States

**Green (Can Train):**
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Train Swordsman    â”‚  â† Green background
â”‚      (25g)         â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
Queue: 2/5
```

**Red (Cannot Train):**
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Train Swordsman    â”‚  â† Red background
â”‚      (25g)         â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
Not enough gold
```
or
```
Queue full (5/5)
```

---

## ðŸ“Š Queue System

### Queue Features

**Capacity:** 5 units per Barracks

**Display:**
- First item: "training... X turn(s)"
- Other items: "waiting"
- Each has cancel button (X)

**Training Order:**
- Queue is FIFO (First In, First Out)
- Only first item trains
- When complete, next item starts

**Cancel:**
- Click X button
- Full refund (25 gold)
- Item removed from queue
- Available anytime before completion

---

### Multiple Barracks Strategy

**Example: 4 Barracks in one territory**

```
Barracks 1: [Swordsman] [Swordsman] [Swordsman]
Barracks 2: [Swordsman] [Swordsman]
Barracks 3: [Swordsman] [Swordsman] [Swordsman] [Swordsman]
Barracks 4: [Swordsman]
```

**Result:**
- Turn 1: 4 units training (one per Barracks)
- Turn 2: 4 units spawn, next 4 start
- Turn 3: 4 more units spawn, last 3 start
- Turn 4: 3 units spawn

**Total: 11 units in 4 turns!**

**This encourages building multiple Barracks!**

---

## ðŸ—ï¸ Strategic Implications

### Single vs Multiple Barracks

**One Barracks:**
- 1 unit per turn
- Queue up to 5
- Cost-effective
- Good for defense

**Multiple Barracks:**
- Multiple units per turn
- Multiple queues
- Faster army growth
- Aggressive expansion

**Example:**
```
1 Barracks = 5 units in 5 turns
3 Barracks = 15 units in 5 turns (3x faster!)
```

---

### Queue Planning

**Strategic advantages:**
- Plan ahead (queue 5 turns)
- Lock in production
- Guaranteed units coming
- Can cancel if plans change

**Tactical flexibility:**
- Cancel to get gold back
- Adjust to threats
- Pivot strategies
- No waste

---

### Barracks Protection

**IMPORTANT:** If Barracks is destroyed:
- âŒ Queue is **cleared**
- âŒ **No refund** for queued units
- âŒ Training stops immediately

**Protection strategies:**
- Build Keeps to defend Barracks
- Garrison armies
- Build in interior territories
- Multiple Barracks = redundancy

---

## ðŸ”§ Technical Implementation

### Game State Tracking

**training_queue structure:**
```python
{
    'Territory Name': {
        barracks_plot_index: [
            ('Swordsman', 1),  # Currently training (1 turn left)
            ('Swordsman', 1),  # Waiting in queue
            ('Swordsman', 1),  # Waiting in queue
        ]
    }
}
```

**Each Barracks has its own independent queue!**

---

### Core Methods

**1. start_training(territory, barracks_plot_index, unit_type)**
```python
# Validates ownership, gold, queue space
# Deducts 25 gold
# Adds (unit_type, 1) to queue
# Returns True/False
```

**2. cancel_training(territory, barracks_plot_index, queue_index)**
```python
# Full refund (25 gold)
# Removes item from queue
# Returns True/False
```

**3. clear_training_queue(territory, barracks_plot_index=None)**
```python
# Called when Barracks destroyed
# No refund
# Clears queue
```

**4. finish_training()**
```python
# Called at start of each turn
# Processes first item in each queue
# Spawns army as "moved"
# Advances queue
```

---

### Barracks Destruction

**When player demolishes:**
```python
def destroy_building(territory, plot_index):
    # ... existing code ...
    if building_type == 'Barracks':
        clear_training_queue(territory, plot_index)  # No refund
```

**When territory conquered:**
```python
def destroy_all_buildings(territory):
    # ... existing code ...
    clear_training_queue(territory)  # Clear all queues
```

---

## ðŸŽ¨ UI Implementation

### Barracks Selection

**Map click detection:**
```python
if plot has Barracks:
    selected_barracks = (territory, plot_index)
    selected_plot = None  # Not a plot selection
    # Opens training UI
```

### Training UI Panel

**Layout:**
- Left: Training button area (like building buttons)
- Divider: Vertical line
- Right: Queue display with cancel buttons

**Components:**
1. Title: "Barracks in [Territory]"
2. Gold display
3. Train button (green/red)
4. Status text (queue count or error)
5. Queue items with cancel buttons

---

### Click Handling

**Train button:**
```python
if train_button.collidepoint(mouse):
    start_training(territory, barracks_plot_index, 'Swordsman')
```

**Queue cancel buttons:**
```python
for cancel_rect, queue_index in queue_cancel_buttons:
    if cancel_rect.collidepoint(mouse):
        cancel_training(territory, barracks_plot_index, queue_index)
```

---

## ðŸ“ˆ Strategic Examples

### Example 1: Single Barracks Rush

**Setup:**
- 1 Barracks in border territory
- Queue 5 Swordsmen immediately

**Timeline:**
```
Turn 1: Queue 5 units (125g), first starts training
Turn 2: 1 unit spawns, 4 waiting
Turn 3: 1 unit spawns, 3 waiting
Turn 4: 1 unit spawns, 2 waiting
Turn 5: 1 unit spawns, 1 waiting
Turn 6: 1 unit spawns, queue empty
```

**Result:** 5 units over 5 turns, predictable

---

### Example 2: Multiple Barracks Boom

**Setup:**
- 3 Barracks in strong territory
- Queue 5 units in each (15 total)

**Timeline:**
```
Turn 1: Queue 15 units (375g), 3 start training
Turn 2: 3 spawn, 3 start training (6 total)
Turn 3: 3 spawn, 3 start training (9 total)
Turn 4: 3 spawn, 3 start training (12 total)
Turn 5: 3 spawn, 0 start (15 total, done!)
```

**Result:** 15 units in 5 turns = 3x faster!

---

### Example 3: Queue Management

**Scenario:** Queued 5 units, enemy threatens

**Options:**
1. **Cancel all** â†’ Get 125g back
2. **Let 1 finish** â†’ Get 4x 25g = 100g back
3. **Keep queue** â†’ Units for defense

**Flexibility is key!**

---

## ðŸ’¡ Advanced Tactics

### Queue Staggering

**Strategy:** Don't fill all queues at once
- Turn 1: Queue 2 in each Barracks
- Turn 3: Queue 2 more
- Turn 5: Queue final units

**Benefit:**
- Spreads out gold spending
- Maintains economic flexibility
- Can react to threats
- Steady unit flow

---

### Emergency Cancellation

**Scenario:** Need gold NOW for Keep or emergency

**Action:**
- Cancel queued units
- Get full refund
- Use gold elsewhere
- Restart queue later

**This prevents "gold lock" problems!**

---

### Barracks Redundancy

**Strategy:** Multiple Barracks in different territories

**Benefits:**
- If one is destroyed, others continue
- Distributed production
- Harder for enemy to stop
- Multiple front capabilities

---

## ðŸŽ® Gameplay Impact

### Complete Military Loop

**Before:**
```
Territories â†’ Income â†’ Buildings â†’ More Income
(No military production)
```

**After:**
```
Territories â†’ Income â†’ Buildings â†’ Barracks â†’
Train Units â†’ Armies â†’ Conquest â†’ More Territories! âœ…
```

---

### Strategic Depth

**Players must now balance:**
- **Economic buildings** (long-term income)
- **Barracks buildings** (military infrastructure)
- **Training queues** (military production)
- **Gold reserves** (flexibility)

**Multiple viable strategies:**
1. **Economic â†’ Mass Production** (Build economy, then spam units)
2. **Early Barracks Rush** (Fast military, slow economy)
3. **Balanced Growth** (Mix economy and military)
4. **Quality over Quantity** (Few Barracks, better economy)

---

## âœ… What's Working

### Core Functionality
- âœ… Click Barracks â†’ Training UI opens
- âœ… Train button (green/red states)
- âœ… Queue system (5 unit max)
- âœ… 1-turn training time
- âœ… Sequential training
- âœ… Multiple Barracks = multiple queues
- âœ… Units spawn as "moved"
- âœ… Cancel for full refund
- âœ… Queue cleared on destruction (no refund)

### UI Elements
- âœ… Professional training interface
- âœ… Queue visualization
- âœ… Cancel buttons per item
- âœ… Status indicators
- âœ… Gold tracking
- âœ… Consistent with building UI

### Integration
- âœ… Works with all existing systems
- âœ… Proper turn sequencing
- âœ… Correct army spawning
- âœ… Building destruction handling
- âœ… Territory conquest handling

---

## ðŸ§ª Testing Scenarios

### Test 1: Basic Training âœ…
1. Build Barracks
2. Click Barracks
3. Click Train button
4. **Expected:** Unit added to queue
5. End turn
6. **Expected:** Unit spawns as moved army
7. **Result:** âœ… Works!

### Test 2: Full Queue âœ…
1. Queue 5 units
2. Try to queue 6th
3. **Expected:** "Queue full" message
4. **Result:** âœ… Works!

### Test 3: Cancel with Refund âœ…
1. Queue 3 units (75g spent)
2. Cancel middle one
3. **Expected:** 25g refunded, 50g spent
4. **Result:** âœ… Works!

### Test 4: Barracks Demolished âœ…
1. Queue 5 units
2. Demolish Barracks
3. **Expected:** Queue cleared, no refund
4. **Result:** âœ… Works!

### Test 5: Territory Conquered âœ…
1. Enemy has 3 units queued
2. Conquer territory
3. **Expected:** Queue cleared, no refund
4. **Result:** âœ… Works!

### Test 6: Multiple Barracks âœ…
1. Build 3 Barracks in territory
2. Queue 2 units in each (6 total)
3. End turn
4. **Expected:** 3 units spawn (one per Barracks)
5. **Result:** âœ… Works!

### Test 7: Unit Movement âœ…
1. Train unit
2. End turn (unit spawns)
3. Try to move unit
4. **Expected:** Cannot move (marked as moved)
5. End turn again
6. **Expected:** Can move now
7. **Result:** âœ… Works!

---

## ðŸŽ¯ Future-Proofing

### Multiple Unit Types

**Current:** Only Swordsman

**Future expansion ready:**
```python
unit_types = {
    'Swordsman': {'cost': 25, 'attack': 1, 'defense': 1},
    'Archer': {'cost': 30, 'attack': 1, 'defense': 0, 'range': 2},
    'Cavalry': {'cost': 40, 'attack': 2, 'defense': 1, 'speed': 2},
    'Pikeman': {'cost': 35, 'attack': 1, 'defense': 2},
}
```

**UI ready:**
- Button array (like building buttons)
- Queue shows unit type
- Training time per type
- **Just add buttons!**

---

### Advanced Features

**Possible additions:**
- Unit upgrades
- Veteran units
- Training time modifiers
- Barracks levels
- Special units from special buildings

**System supports all of this!**

---

## ðŸ“Š Balance Considerations

### Current Balance

**Costs:**
- Barracks: 50g (one-time)
- Training: 25g per unit
- Total for 1 unit: 75g

**Comparison:**
- Farm: 30g â†’ +10g/turn (3 turn payoff)
- Unit: 25g â†’ +1 army (permanent)

**Seems balanced!**

---

### Multiple Barracks Cost

**Analysis:**
```
1 Barracks: 50g â†’ 1 unit/turn
2 Barracks: 100g â†’ 2 units/turn (2x production)
3 Barracks: 150g â†’ 3 units/turn (3x production)
```

**Linear scaling encourages multiple Barracks!**

---

## ðŸ“ˆ Progress Update

### TIER 2B Status

**Before:** 40% complete (2/5)  
**After:** 60% complete (3/5) ðŸŽ‰

**Completed:**
- âœ… Movement range (via colors)
- âœ… Combat preview (via tooltips)
- âœ… Terrain effects (Keep defense)
- âœ… **Army recruitment** â† DONE!

**Remaining:**
- â¬œ Army split/merge (2-3 hours)

---

## ðŸš€ Next Steps

**TIER 2B Completion:**
- Army split/merge system
- Then TIER 2 fully complete!

**The recruitment system is production-ready!**

---

## ðŸŽŠ Summary

**Feature:** Queue-Based Army Training âœ…  
**Status:** Fully Implemented  
**Quality:** Production-ready  
**Design:** Consistent with existing systems  
**Future-proof:** Ready for multiple unit types  
**Strategic depth:** Massive!

**What You Get:**
- Click Barracks â†’ Training UI
- Train button (like building buttons)
- Queue system (up to 5 per Barracks)
- 1-turn training time
- Units spawn as "moved"
- Cancel for full refund
- Multiple Barracks = simultaneous training
- Queue cleared on destruction (no refund)
- Professional UI
- Future-proof design

**This completes the economic â†’ military loop!**

The game now has full strategic depth with multiple viable playstyles!

---

**Last Updated:** December 29, 2024  
**Session:** TIER 2B Implementation  
**Status:** Army Recruitment Complete! âœ…  
**Next:** Army Split/Merge System ðŸš€  
**Design:** Exactly as specified! ðŸŽ¯
