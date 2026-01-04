# Building System Implementation Plan

## 🎨 UI Layout

### Current Layout (Before):
```
┌─────────────────────────────────┬──────────┐
│                                 │          │
│          MAP AREA               │   UI     │
│                                 │  PANEL   │
│                                 │          │
│                                 │          │
└─────────────────────────────────┴──────────┘
```

### New Layout (After):
```
┌─────────────────────────────────┬──────────┐
│                                 │          │
│          MAP AREA               │   UI     │
│         (reduced                │  PANEL   │
│          height)                │  (info)  │
│                                 │          │
├─────────────────────────────────┴──────────┤
│      BOTTOM PANEL (RTS Style)              │
│    Building Menu | Army Controls | Etc.    │
└────────────────────────────────────────────┘
```

**Dimensions**:
- Bottom Panel Height: 180-200px
- Map Height: WINDOW_HEIGHT - BOTTOM_PANEL_HEIGHT
- Right Panel: Unchanged (230px)

---

## 🏗️ Building Selection Flow

### Step 1: Player Clicks Empty Plot
**On Map**:
- Plot highlights
- Building icons appear in circle/ring around plot (radius ~40px):
  ```
        F (Farm)
   
   B              M
 (Barracks)     (Mine)
   
   S              K
 (Square)      (Keep)
  ```
- Just letters, no costs
- Click icon → selects that building type

**In Bottom Panel**:
- Shows detailed building menu
- Each building shows:
  - Icon/Letter
  - Name
  - Cost
  - Effect description
  - "Build" button

### Step 2: Player Selects Building
- Confirms selection in bottom panel
- Gold deducted
- Building enters "construction" status
- Plot shows letter with yellow/orange color
- Message: "Farm construction started in Orlais"

### Step 3: Construction Complete (Next Turn)
- Building completes automatically
- Plot shows letter with solid gray color
- Message: "Farm completed in Orlais!"
- Effects apply immediately

---

## 🎮 Building Management

### Click Completed Building:
**Shows Options in Bottom Panel**:
- Building name and type
- Current effect
- "Destroy" button (50% refund)

### Click Under-Construction Building:
**Shows Options in Bottom Panel**:
- Building name and type
- Completion: "Next turn"
- "Cancel" button (100% refund)

---

## 📋 Building Types (Final)

| Letter | Name | Cost | Effect |
|--------|------|------|--------|
| **F** | Farm | 30g | +10 income/turn |
| **M** | Mine | 40g | +15 income/turn |
| **K** | Keep | 100g | +2 defense in combat |
| **B** | Barracks | 50g | Enable army recruitment |
| **S** | Square | 60g | +50% territory income |

---

## 🎨 Visual Design

### Empty Plot:
- Semi-transparent gray circle (current design)
- Radius: 8px

### Under Construction:
- Larger circle (12px)
- Yellow/orange color (255, 200, 100)
- Letter shown
- Slightly transparent

### Completed Building:
- Larger circle (12px)
- Solid gray (150, 150, 150)
- Letter shown in white
- Fully opaque

### Selected Plot:
- Highlight with yellow outline
- Building icons in ring around it

---

## 💻 Code Structure

### game_state.py Updates:
✅ Already done:
- Building data structure: `buildings[(territory, plot_index)]`
- Construction tracking with turn completion
- `construct_building()`, `cancel_construction()`, `destroy_building()`
- `clear_buildings_in_territory()` on conquest
- Building bonuses in income calculation

### main.py Updates:
Need to implement:
1. **UI Layout**:
   - Adjust map height for bottom panel
   - Create bottom panel area

2. **Plot Click Detection**:
   - `get_plot_at_pos()` - ✅ Done
   - Handle plot clicks in `handle_click()`

3. **Drawing Methods**:
   - `draw_plots()` - ✅ Updated to show buildings
   - `draw_building_selection_ring()` - NEW
   - `draw_bottom_panel()` - NEW

4. **Building Menu UI**:
   - Show building options
   - Handle building selection
   - Show construction status
   - Cancel/destroy buttons

---

## 🎯 Implementation Steps

### Phase 1: UI Framework (30 min)
1. ✅ Add bottom panel constants
2. Update map height calculation
3. Create draw_bottom_panel skeleton
4. Test layout rendering

### Phase 2: Plot Interaction (30 min)
5. ✅ Add get_plot_at_pos method
6. Update handle_click to detect plot clicks
7. Store selected_plot state
8. Highlight selected plot

### Phase 3: Selection Ring (20 min)
9. Create draw_building_selection_ring method
10. Position icons in circle around plot
11. Handle icon clicks
12. Visual feedback on hover

### Phase 4: Bottom Panel Menu (40 min)
13. Draw building list with details
14. Show costs and check affordability
15. Add "Build" buttons
16. Handle building confirmation

### Phase 5: Construction Display (20 min)
17. ✅ Show buildings on plots (letters)
18. Different colors for construction vs complete
19. Update tooltips to show building info

### Phase 6: Management UI (30 min)
20. Click building → show details in bottom panel
21. Add "Cancel" button for construction
22. Add "Destroy" button for completed buildings
23. Confirm actions and update display

### Phase 7: Testing & Polish (30 min)
24. Test full construction flow
25. Test cancel/destroy
26. Test conquest building destruction
27. Visual polish and bug fixes

**Total Estimated Time**: ~3 hours

---

## ❓ Questions for Confirmation

Before I implement, please confirm:

1. **Selection Ring Layout**: 
   - 5 building icons in circle/ring around clicked plot? ✓
   - Icon spacing/radius of ~40px from plot center?

2. **Bottom Panel Content**:
   - Building list with full details (cost, effect, build button)?
   - Or a simpler design?

3. **Colors**:
   - Construction: Yellow/orange (255, 200, 100)? ✓
   - Completed: Gray (150, 150, 150)? ✓
   - Letters in white? ✓

4. **Interaction**:
   - Click icon in ring → immediately opens build confirmation in bottom panel?
   - Or click icon → automatically builds (if affordable)?

5. **Cancel/Destroy Placement**:
   - In bottom panel when clicking building? ✓
   - Or in a popup menu?

---

## 🚀 Ready to Build?

Once you confirm these details, I'll implement the complete system!

**Current Status**: 
- ✅ game_state.py fully updated
- ✅ draw_plots updated to show buildings
- ✅ get_plot_at_pos method added
- ⏳ Bottom panel and selection ring pending
- ⏳ Click handling updates pending

Say "go ahead" or provide any tweaks to the design! 🏗️
