# One Building Per Territory Per Turn - Strategic Limit

**Date:** December 29, 2024  
**Feature:** Building construction limit (one per territory per turn)  
**Status:** âœ… FULLY IMPLEMENTED!

---

## ðŸŽ¯ What's New

### Strategic Constraint

**Rule:** You can only start **one building per territory per turn**

**Why:** Encourages strategic thinking and planning

**Impact:** Significant gameplay depth increase!

---

## ðŸ“‹ The Rules

### Basic Rule

**Per Turn:**
- âœ… Can build 1 building on Territory A
- âœ… Can build 1 building on Territory B  
- âœ… Can build 1 building on Territory C
- âŒ Cannot build 2 buildings on Territory A

**Example:**
```
Turn 1:
- DamlÃ©re: Build Farm âœ“
- Liadnon: Build Mine âœ“
- DamlÃ©re: Build Mine âœ— (already built Farm!)

Turn 2:
- DamlÃ©re: Build Mine âœ“ (new turn, limit reset!)
```

---

### Canceling Construction

**Rule:** Canceling frees up your building slot

**Scenario:**
```
1. Build Farm in DamlÃ©re
2. Realize you need Mine instead
3. Cancel Farm construction â†’ Get refund
4. Build Mine in DamlÃ©re âœ“

Same turn, same territory, but allowed!
```

**Why:** You haven't actually committed to building yet

---

### Demolishing Buildings

**Rule:** Demolishing counts as your building action

**Scenario:**
```
1. Demolish Farm in DamlÃ©re â†’ Get 50% refund
2. Try to build Mine in DamlÃ©re âœ—
   Message: "Only one building per territory per turn!"

Must wait until next turn to build!
```

**Why:** Demolishing is a significant action that consumes your turn's construction effort

---

## ðŸ’¡ Strategic Impact

### Forces Planning

**Before (No Limit):**
```
Have 300 gold?
â†’ Build 3 Farms on same territory
â†’ Instant development
â†’ No planning needed
```

**After (With Limit):**
```
Have 300 gold?
â†’ Build 1 Farm on Territory A
â†’ Build 1 Mine on Territory B
â†’ Build 1 Farm on Territory C
â†’ Spread development strategically!
```

---

### Encourages Territory Expansion

**Goal:** Build multiple buildings per turn

**Solution:** Control more territories!

**Benefit:** Rewards conquest and expansion

**Example:**
```
Player with 3 territories:
â†’ 3 buildings per turn maximum

Player with 10 territories:
â†’ 10 buildings per turn maximum!

Expansion = More building capacity!
```

---

### Long-Term Planning

**Can't rush development:**
```
Territory with 4 plots:
â†’ Minimum 4 turns to fully develop
â†’ Must plan which buildings and when
â†’ Prioritize based on strategy
```

**Forces decisions:**
- Farm first? (Immediate income)
- Mine first? (Higher income)
- Barracks first? (Military strength)
- Keep first? (Defense)
- Square first? (Income multiplier)

---

### Makes Demolishing Costly

**Before:** Demolish and rebuild freely

**After:** Demolishing consumes your turn!

**Scenario:**
```
Built wrong building by mistake?
â†’ Demolish: Lose 50% gold
â†’ Can't rebuild this turn
â†’ Wait until next turn
â†’ Very costly mistake!

Better to plan carefully!
```

---

## ðŸŽ® Gameplay Examples

### Example 1: Efficient Development

**Goal:** Maximize income

**Strategy:**
```
Turn 1:
- Territory A: Farm (+10 income)
- Territory B: Farm (+10 income)
- Territory C: Farm (+10 income)
Total: +30 income next turn

Turn 2:
- Territory A: Mine (+15 income)
- Territory B: Mine (+15 income)
- Territory C: Mine (+15 income)
Total: +60 additional income

Efficient parallel development!
```

---

### Example 2: Strategic Pivot

**Situation:** Need to change strategy

**Actions:**
```
Turn 1:
- Territory A: Start building Farm

Mid-turn:
- Enemy attacks Territory B!
- Need Keep for defense!

Solution:
- Cancel Farm construction
- Build Keep on Territory A instead!

Works because we canceled first!
```

---

### Example 3: Demolish Cost

**Situation:** Wrong building built

**Actions:**
```
Turn 1:
- Territory A: Has Farm
- Realize Mine would be better
- Demolish Farm: Get 15g refund (50% of 30g)
- Try to build Mine: âœ— Blocked!

Turn 2:
- Build Mine: âœ“ Now allowed

Cost: 
- Lost 15 gold (demolish loss)
- Lost 1 turn (couldn't build immediately)
- Total setback: Significant!
```

---

### Example 4: Multi-Territory Strategy

**Situation:** 6 territories, 180 gold

**Optimal:**
```
Build on 6 different territories:
- Territory A: Farm (30g)
- Territory B: Farm (30g)
- Territory C: Farm (30g)
- Territory D: Mine (40g)
- Territory E: Mine (40g)
- Territory F: Barracks (50g)

Total: 220g needed (need 40 more gold)
Choose 5 to build this turn
```

**Sub-Optimal:**
```
Try to build 6 on one territory:
âœ— Can only build 1
âœ— Wastes potential
âœ— Slower development
```

---

## ðŸ”§ Technical Implementation

### Tracking System

**Data Structure:**
```python
self.buildings_started_this_turn = set()
# Set of territory names
# Example: {'DamlÃ©re', 'Liadnon', 'Frontier'}
```

**Why a set:**
- Fast O(1) lookup
- No duplicates
- Easy to clear
- Memory efficient

---

### Check When Starting Construction

**In start_construction():**
```python
# Check one building per territory per turn limit
if territory in self.buildings_started_this_turn:
    self.add_message("Only one building per territory per turn!")
    return False

# ... proceed with construction ...

# Mark this territory as having started construction
self.buildings_started_this_turn.add(territory)
```

---

### Cancel Construction (Allow Rebuilding)

**In cancel_construction():**
```python
# Remove from construction
del self.under_construction[territory][plot_index]

# Allow building again on this territory this turn
self.buildings_started_this_turn.discard(territory)

self.add_message("Construction canceled, refund given")
```

**Why discard:** Removes from set if present, no error if not

---

### Demolish Building (Block Rebuilding)

**In destroy_building():**
```python
# Remove building
del self.buildings[territory][plot_index]

# Mark this territory as having used its building action
self.buildings_started_this_turn.add(territory)

self.add_message("Building demolished, 50% refund given")
```

---

### Clear at Turn End

**In _advance_to_next_player():**
```python
def _advance_to_next_player(self):
    # Clear building limit tracking for new turn
    self.buildings_started_this_turn.clear()
    
    # ... rest of turn advance logic ...
```

**When:** At start of new player's turn
**Effect:** Everyone can build again

---

## ðŸ“Š Edge Cases

### Case 1: Start and Cancel Same Turn

**Scenario:**
```
1. Build Farm
2. Cancel Farm
3. Build Mine
```

**Result:** âœ“ Allowed (cancel frees slot)

---

### Case 2: Demolish Then Try to Build

**Scenario:**
```
1. Demolish completed Farm
2. Try to build Mine
```

**Result:** âœ— Blocked (demolish used slot)

---

### Case 3: Multiple Cancels

**Scenario:**
```
1. Build Farm
2. Cancel Farm
3. Build Mine
4. Cancel Mine
5. Build Keep
```

**Result:** âœ“ All allowed (each cancel frees slot)

---

### Case 4: Build on Multiple Territories

**Scenario:**
```
1. Build on Territory A
2. Build on Territory B
3. Build on Territory C
```

**Result:** âœ“ All allowed (different territories)

---

### Case 5: Try to Build Twice Same Territory

**Scenario:**
```
1. Build Farm on Territory A
2. Try to build Mine on Territory A
```

**Result:** âœ— Blocked
**Message:** "Only one building per territory per turn!"

---

## âœ… What's Working

**Limit Enforcement:**
- âœ… Check before starting construction
- âœ… Block second building on same territory
- âœ… Clear message to player
- âœ… Tracks all construction starts

**Cancel Handling:**
- âœ… Remove from tracking set
- âœ… Allow rebuilding
- âœ… Full refund preserved
- âœ… Seamless workflow

**Demolish Handling:**
- âœ… Add to tracking set
- âœ… Block rebuilding
- âœ… 50% refund preserved
- âœ… Appropriate penalty

**Turn Reset:**
- âœ… Clear at turn end
- âœ… Fresh start each turn
- âœ… No carryover
- âœ… Clean implementation

---

## ðŸŽ¯ Strategic Depth Analysis

### Decision Complexity

**Before:**
- "Do I have gold?" â†’ Yes â†’ Build
- Simple resource check

**After:**
- "Do I have gold?" â†’ Yes
- "Which territory?" â†’ Must choose
- "What building?" â†’ Must prioritize
- "Can I wait?" â†’ Time consideration
- Complex strategic decision!

---

### Territory Value

**Before:**
- Territory value = Income + Plot count

**After:**
- Territory value = Income + Plot count + Building slots per turn
- More territories = More building capacity
- Expansion more valuable!

---

### Mistake Cost

**Before:**
- Wrong building? Demolish and rebuild
- Cost: 50% of building cost

**After:**
- Wrong building? Demolish
- Cost: 50% of building cost + 1 turn delay
- Much more costly!
- Encourages careful planning

---

## ðŸ’ª Benefits

### For New Players

**Learning:**
- Forces understanding of buildings
- Encourages strategic thinking
- Learn prioritization
- Understand territory importance

**Progression:**
- Can't overwhelm with options
- Gradual development feels natural
- Time to learn each building
- Clear decision points

---

### For Experienced Players

**Strategy:**
- Deep planning required
- Multiple viable strategies
- Risk/reward decisions
- Long-term thinking

**Skill Expression:**
- Optimal building order
- Territory prioritization
- Timing of expansions
- Recovery from mistakes

---

## ðŸ§ª Testing Scenarios

### Test 1: Basic Limit âœ…

**Steps:**
1. Build Farm on Territory A
2. Try to build Mine on Territory A
3. **Expected:** Blocked with message
4. **Message:** "Only one building per territory per turn!"

---

### Test 2: Multi-Territory âœ…

**Steps:**
1. Build on Territory A
2. Build on Territory B
3. Build on Territory C
4. **Expected:** All succeed

---

### Test 3: Cancel and Rebuild âœ…

**Steps:**
1. Build Farm on Territory A
2. Cancel construction
3. Build Mine on Territory A
4. **Expected:** Mine construction succeeds

---

### Test 4: Demolish Block âœ…

**Steps:**
1. Demolish building on Territory A
2. Try to build on Territory A
3. **Expected:** Blocked with message

---

### Test 5: Turn Reset âœ…

**Steps:**
1. Build on Territory A (blocked for rest of turn)
2. End turn
3. New turn starts
4. Build on Territory A
5. **Expected:** Succeeds (limit reset)

---

## ðŸŽŠ Summary

**Feature:** One building per territory per turn âœ…  
**Implementation:** Complete with cancel/demolish handling âœ…  
**Strategic Impact:** Significant depth increase âœ…  
**Quality:** Production-ready! âœ…

**What It Does:**
- Limits building spam âœ“
- Encourages planning âœ“
- Makes territory count valuable âœ“
- Increases decision complexity âœ“
- Makes mistakes costly âœ“

**How It Works:**
- Track territories built on âœ“
- Check before building âœ“
- Clear on cancel âœ“
- Block on demolish âœ“
- Reset each turn âœ“

**Result:**
- More strategic gameplay! ðŸŽ®
- Better pacing! â±ï¸
- Meaningful choices! ðŸ¤”
- Higher skill ceiling! ðŸ“ˆ

---

**Last Updated:** December 29, 2024  
**Status:** Implemented & Tested âœ…  
**Files:** game_state.py (1,096 lines)  
**Quality:** Excellent! ðŸš€
