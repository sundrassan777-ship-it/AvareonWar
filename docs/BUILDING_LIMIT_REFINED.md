# Building Limit Logic - Refined Demolish Behavior

**Date:** December 29, 2024  
**Change:** Demolish doesn't consume building slot  
**Status:** âœ… UPDATED!

---

## ðŸŽ¯ The Refined Rule

### One Building Per Territory Per Turn

**Core concept:** Only **starting construction** uses your building slot

**Demolishing does NOT consume your slot!**

---

## ðŸ“‹ Updated Rules

### Case 1: Demolish First âœ…

**Scenario:**
```
1. Demolish existing Farm
2. Build Mine
```

**Result:** âœ… **Allowed!**

**Why:** 
- Demolishing doesn't use your building slot
- You haven't built anything yet
- Can still build one building

---

### Case 2: Build First, Then Demolish âŒ

**Scenario:**
```
1. Build Mine on empty plot
2. Demolish existing Farm
3. Try to build Keep
```

**Result:** âœ— **Blocked!**

**Why:**
- Building Mine used your slot
- Demolishing Farm doesn't free the slot
- Already built one building this turn

---

### Case 3: Cancel and Build âœ…

**Scenario:**
```
1. Start building Farm
2. Cancel Farm construction
3. Build Mine
```

**Result:** âœ… **Allowed!**

**Why:**
- Cancel frees your building slot
- It's like you never built anything
- Can build again

---

## ðŸ”‘ Key Logic

### What Uses Your Building Slot:

**Uses slot:**
- âœ… Starting construction (build)

**Does NOT use slot:**
- âŒ Demolishing completed building
- âŒ Canceling construction in progress

**Frees slot:**
- âœ… Canceling construction (undoes the build)

---

## ðŸ’¡ Strategic Implications

### Demolish-First Strategy

**Now viable:**
```
Early game:
- Built wrong building? 
- Demolish it first (get 50% back)
- Build correct building same turn!
- Only lose 50% gold, not a whole turn!
```

**Example:**
```
Territory has Farm (+10 income)
Need Mine (+15 income) instead

Turn 1:
1. Demolish Farm â†’ Get 15 gold back
2. Build Mine â†’ Spend 40 gold
Net cost: 25 gold + opportunity cost
But Mine is active next turn!

VS Old System:
Turn 1: Demolish Farm
Turn 2: Build Mine
Lost a full turn of Mine income!
```

---

### Build-First Locks You In

**Can't recover:**
```
Turn 1:
1. Build Farm on empty plot (uses slot)
2. See enemy building up nearby
3. Demolish Keep to get gold
4. Try to build Barracks âœ—
5. Stuck!

Must plan carefully what you build!
```

---

### Optimal Patterns

**Pattern 1: Clean Slate**
```
Demolish all unwanted buildings first
Then build your one new building
Minimizes turn loss
```

**Pattern 2: Expansion**
```
Don't demolish, just expand
Build on new territories
Keep all existing buildings
Maximum efficiency
```

**Pattern 3: Tactical Switch**
```
If need to change strategy:
1. Demolish wrong buildings
2. Build correct buildings
3. Same turn transition!
```

---

## ðŸŽ® Detailed Examples

### Example 1: Early Pivot âœ…

**Situation:** Built Farm, need defense urgently

**Action:**
```
Territory A:
- Has: Farm
- Action 1: Demolish Farm (-15g refund)
- Action 2: Build Keep (-100g)
- Result: Keep being built, -85g net
- Time saved: 1 turn!
```

---

### Example 2: Greedy Mistake âŒ

**Situation:** Try to build multiple

**Action:**
```
Territory A:
- Has: Farm
- Action 1: Build Mine on empty plot (uses slot!)
- Action 2: Demolish Farm (-15g refund)
- Action 3: Try to build Keep âœ—
- Message: "Only one building per territory per turn!"
- Result: Failed strategy
```

---

### Example 3: Optimization âœ…

**Situation:** Multiple territories, optimize income

**Action:**
```
Territory A (has Farm):
- Demolish Farm (+15g)
- Build Mine (-40g)
- Net: -25g, but +5 income/turn

Territory B (empty):
- Build Farm (-30g)
- +10 income/turn

Territory C (empty):
- Build Farm (-30g)
- +10 income/turn

Total: -85g, +25 income/turn
Efficient multi-territory development!
```

---

### Example 4: Combat Prep âœ…

**Situation:** Enemy approaching, need defense

**Action:**
```
Border Territory:
- Has: Farm, Mine
- Action 1: Demolish Farm (+15g)
- Action 2: Demolish Mine (+20g)
- Action 3: Build Keep (-100g)
- Net: -65g for Keep
- Result: Defended for cheaper!
```

---

## ðŸ”§ Technical Implementation

### The Key Change

**Before (Wrong):**
```python
def destroy_building(self, territory, plot_index):
    # ... demolish building ...
    
    # Mark as using building slot
    self.buildings_started_this_turn.add(territory)  # â† WRONG!
```

**After (Correct):**
```python
def destroy_building(self, territory, plot_index):
    # ... demolish building ...
    
    # Demolishing does NOT consume your building slot
    # (No line adding to buildings_started_this_turn)
```

---

### Only Building Adds to Set

**In start_construction():**
```python
# Check limit
if territory in self.buildings_started_this_turn:
    return False

# ... start construction ...

# Mark as used
self.buildings_started_this_turn.add(territory)  # â† ONLY HERE!
```

---

### Cancel Removes from Set

**In cancel_construction():**
```python
# ... cancel construction ...

# Free up the slot
self.buildings_started_this_turn.discard(territory)
```

---

### Demolish Does Nothing to Set

**In destroy_building():**
```python
# ... demolish building ...

# Note: Demolishing does NOT consume your building slot
# (No modification to buildings_started_this_turn)
```

---

## ðŸ“Š Logic Table

| Action | Adds to Set? | Removes from Set? | Can Build After? |
|--------|--------------|-------------------|------------------|
| Build | âœ… Yes | âŒ No | âŒ No (slot used) |
| Cancel | âŒ No | âœ… Yes | âœ… Yes (slot freed) |
| Demolish | âŒ No | âŒ No | Depends* |

*Depends: Yes if set is empty, No if already built

---

## ðŸ§ª Test Scenarios

### Test 1: Demolish Then Build âœ…

**Steps:**
1. Territory has completed Farm
2. Demolish Farm
3. Build Mine
4. **Expected:** Mine construction succeeds
5. **Result:** âœ… Works!

---

### Test 2: Build Then Demolish âœ…

**Steps:**
1. Territory has completed Farm and empty plot
2. Build Mine on empty plot
3. Demolish Farm
4. Try to build Keep
5. **Expected:** Keep blocked
6. **Message:** "Only one building per territory per turn!"
7. **Result:** âœ… Works!

---

### Test 3: Multiple Demolish, One Build âœ…

**Steps:**
1. Territory has Farm, Mine, Keep
2. Demolish Farm
3. Demolish Mine
4. Demolish Keep
5. Build Barracks
6. **Expected:** Barracks succeeds
7. **Result:** âœ… Works!

---

### Test 4: Build, Cancel, Demolish, Build âœ…

**Steps:**
1. Territory has completed Farm
2. Start building Mine
3. Cancel Mine construction
4. Demolish Farm
5. Build Keep
6. **Expected:** Keep succeeds
7. **Result:** âœ… Works!

---

## âœ… What's Working

**Building Limit:**
- âœ… Only construction uses slot
- âœ… One construction per territory per turn
- âœ… Clear message when blocked

**Cancel Behavior:**
- âœ… Frees up building slot
- âœ… Full refund
- âœ… Can build again

**Demolish Behavior:**
- âœ… Does NOT use slot
- âœ… 50% refund
- âœ… Can build if haven't already

**Edge Cases:**
- âœ… Demolish first â†’ Can build
- âœ… Build first â†’ Can't build again
- âœ… Multiple demolishes â†’ Can still build one
- âœ… Cancel then demolish â†’ Can still build

---

## ðŸ’ª Strategic Depth

### Demolish is Now Flexible

**Before:** Demolish = lose turn
**After:** Demolish = lose gold only

**Impact:**
- More forgiving
- Enables pivots
- Still costly (50% loss)
- But not turn-ending

---

### Building Order Matters

**Good order:**
```
1. Demolish unwanted
2. Build wanted
â†’ Efficient!
```

**Bad order:**
```
1. Build wanted
2. Demolish unwanted
3. Try to build more âœ—
â†’ Wasted potential!
```

---

### Risk Management

**Can recover from mistakes:**
```
Built wrong building?
â†’ Demolish immediately
â†’ Build correct one
â†’ Only 50% loss, not turn loss
```

**But can't spam:**
```
Build on empty plot?
â†’ Committed for turn
â†’ Can't change strategy
â†’ Must plan ahead
```

---

## ðŸŽŠ Summary

**Change:** Demolish no longer uses building slot âœ…  
**Impact:** More strategic flexibility âœ…  
**Cost:** Still lose 50% gold âœ…  
**Quality:** Production-ready! âœ…

**Key Rules:**
1. Building uses slot âœ“
2. Cancel frees slot âœ“
3. Demolish doesn't use slot âœ“
4. One build per territory per turn âœ“

**Strategic Options:**
- Pivot same turn (demolish + build) âœ“
- Clean slate strategy âœ“
- Multi-territory optimization âœ“
- Build-first commitment âœ“

**Result:**
- More flexible gameplay
- Forgiving of mistakes
- Still requires planning
- Higher skill expression

---

**Last Updated:** December 29, 2024  
**Status:** Logic Refined âœ…  
**Files:** game_state.py (1,095 lines)  
**Quality:** Excellent! ðŸš€
