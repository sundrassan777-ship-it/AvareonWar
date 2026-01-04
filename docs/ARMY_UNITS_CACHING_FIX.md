# Army Units Caching Bug Fix

**Date:** December 30, 2024  
**Issue:** Only 1 army button shows despite having 15 armies  
**Status:** ðŸ”§ FIXED + DEBUG ADDED  

---

## ðŸ› The Problem

### Symptoms
- Territory has 15 armies
- Composition UI only shows 1 button
- Can only command 1 army (the first one)

### Root Cause
**Stale cache!** The army units were created when the UI was first opened (before bug fixes), and the system was reusing the old cached data with only 1 unit.

```python
# Old logic:
if territory not in self.army_units:
    # Create units
    self.army_units[territory] = units

# Problem: Once created, never updated!
```

---

## âœ… The Fix

### Solution: Validate Cache
Always check if cached count matches actual total, and recreate if needed.

```python
def ensure_army_units_exist(self, territory):
    # Get current totals
    total = self.armies.get(territory, 0)
    unmoved = self.armies_unmoved.get(territory, 0)
    moved = self.armies_moved.get(territory, 0)
    
    # Fix mismatch
    if unmoved + moved != total:
        print(f"Warning: Army totals mismatch")
        unmoved = total
        moved = 0
        # UPDATE the actual values
        self.armies_unmoved[territory] = unmoved
        self.armies_moved[territory] = moved
    
    # Check if needs recreation
    needs_recreation = False
    if territory not in self.army_units:
        needs_recreation = True
    elif len(self.army_units[territory]) != total:
        # COUNT MISMATCH - recreate!
        print(f"Recreating: cached {len(self.army_units[territory])}, actual {total}")
        needs_recreation = True
    
    if needs_recreation:
        # Create fresh units based on current totals
        units = []
        for i in range(unmoved):
            units.append({'id': i, 'status': 'ready', 'order': None})
        for i in range(moved):
            units.append({'id': unmoved + i, 'status': 'moved', 'order': None})
        
        self.army_units[territory] = units
    
    return self.army_units[territory]
```

---

## ðŸ” Debug Output Added

When you open the composition UI, you'll now see console output:

```
DEBUG: Naragonthid - Units created: 15, Actual total: 15
DEBUG: armies_unmoved: 15, armies_moved: 0
```

Or if there's a mismatch:

```
Warning: Army totals mismatch in Naragonthid. Total: 15, Unmoved: 1, Moved: 0
Recreating army units for Naragonthid: cached 1, actual 15
DEBUG: Naragonthid - Units created: 15, Actual total: 15
DEBUG: armies_unmoved: 15, armies_moved: 0
```

---

## ðŸ§ª Testing Instructions

### Step 1: Close and Reopen UI
1. If composition UI is open, close it (click elsewhere)
2. Click the army again to reopen
3. **Expected:** Should now see all 15 buttons
4. **Check console:** Look for "Recreating" message

### Step 2: Verify Count
1. Count the buttons in the UI
2. Compare to the number shown in the army circle
3. **Expected:** Should match (15 buttons for 15 armies)

### Step 3: Test Selection
1. Click "Select All"
2. **Expected:** All 15 buttons turn gold
3. Right-click adjacent territory
4. **Expected:** "Order created: 15 armies..."

### Step 4: Check Console Output
Look for these lines:
```
DEBUG: Naragonthid - Units created: 15, Actual total: 15
```

If you see:
```
Recreating army units for Naragonthid: cached 1, actual 15
```

This means the fix worked - it detected the mismatch and recreated!

---

## ðŸŽ¯ What Changed

### File: game_state.py

**Before (lines ~189-225):**
```python
def ensure_army_units_exist(self, territory):
    if territory not in self.army_units:
        # Create once, never check again âŒ
        self.army_units[territory] = units
    return self.army_units[territory]
```

**After (lines ~189-249):**
```python
def ensure_army_units_exist(self, territory):
    # Get current totals
    total = self.armies.get(territory, 0)
    
    # Fix mismatches
    if unmoved + moved != total:
        unmoved = total
        moved = 0
        self.armies_unmoved[territory] = unmoved  # UPDATE!
        self.armies_moved[territory] = moved
    
    # Validate cache âœ…
    needs_recreation = False
    if territory not in self.army_units:
        needs_recreation = True
    elif len(self.army_units[territory]) != total:  # NEW CHECK!
        needs_recreation = True
    
    if needs_recreation:
        # Create fresh units
        self.army_units[territory] = units
    
    return self.army_units[territory]
```

---

### File: main.py

**Added debug output (lines ~2008-2011):**
```python
units = self.game_state.ensure_army_units_exist(territory)

# Debug output
actual_total = self.game_state.armies.get(territory, 0)
print(f"DEBUG: {territory} - Units created: {len(units)}, Actual total: {actual_total}")
print(f"DEBUG: armies_unmoved: {self.game_state.armies_unmoved.get(territory, 0)}, armies_moved: {self.game_state.armies_moved.get(territory, 0)}")
```

---

## ðŸ“Š Why This Happened

### Timeline of Events

**1. Initial Bug (Yesterday):**
- `armies_unmoved` and `armies_moved` weren't tracking correctly
- Only 1 army was counted as unmoved
- User opened composition UI â†’ Created 1 unit

**2. Bug Fixed (Earlier Today):**
- Fixed army totals
- Now `armies` shows 15 correctly
- BUT: army_units still cached with 1 unit!

**3. This Fix (Now):**
- Detects cache is stale (1 != 15)
- Recreates with correct count (15)
- Updates `armies_unmoved` to match

---

## ðŸŽŠ Expected Outcome

After this fix:

1. âœ… Close and reopen composition UI
2. âœ… Console shows "Recreating..." message
3. âœ… All 15 buttons appear
4. âœ… Can select all 15
5. âœ… Can command all 15

**The fix is automatic** - just close and reopen the UI!

---

## ðŸ”§ If It Still Doesn't Work

### Additional Debug Steps

If you still only see 1 button, please share:

1. **Console output** - What does DEBUG show?
2. **Mismatch warning** - Do you see "Army totals mismatch"?
3. **Recreating message** - Do you see "Recreating army units"?
4. **Final counts** - What are the final counts shown?

Example output to share:
```
[Copy and paste all lines starting with "Warning:", "Recreating:", or "DEBUG:"]
```

This will help me see exactly where the issue is!

---

**Last Updated:** December 30, 2024  
**Status:** Fix deployed + debug added  
**Action:** Close and reopen composition UI to test  
**Next:** Share console output if issues persist ðŸ”
