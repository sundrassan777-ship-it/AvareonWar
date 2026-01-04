# Plot Placement Tool - Design Document

## ðŸŽ¯ Purpose
Interactive tool for placing building plots within territories. Plots are strategic locations where players can construct buildings (Farms, Mines, Barracks, Fortresses, Markets).

---

## ðŸ“Š Plot System Overview

### What are Plots?
- **Definition**: Designated locations within a territory where buildings can be constructed
- **Purpose**: Create strategic variety between territories and provide clear building locations
- **Visual**: Small markers/icons within territory boundaries

### Strategic Design:
- **Small territories**: 1-2 plots (e.g., "The Comet", "Venexia")
- **Medium territories**: 2-3 plots (most territories)
- **Large/Important territories**: 3-4 plots (e.g., "Orlais", "Amennia", "Azincourne")
- **Capitals/Strategic locations**: Maximum 4 plots

---

## ðŸ› ï¸ Tool Functionality

### Similar to polygon_tool.py:
- Interactive map display
- Select territory from list
- Click to place plot markers
- Auto-save progress to JSON
- Resume capability
- Visual feedback

### Core Features:

**1. Territory Selection**
- List of all 39 territories
- Current territory highlighted
- Shows number of plots placed: "Orlais: 3/4 plots"
- Suggested plot count based on territory size

**2. Plot Placement**
- Click within territory polygon to place plot
- Plot appears as marker (circle or square)
- Visual feedback: green for valid, red if outside territory
- Minimum spacing between plots (prevent overlap)

**3. Plot Management**
- Click existing plot to remove it
- Arrow keys to navigate territories
- Number keys (1-4) to auto-suggest plot count
- 'R' to remove all plots from current territory

**4. Data Storage**
```json
{
  "Orlais": [
    {"x": 450, "y": 320},
    {"x": 480, "y": 350},
    {"x": 420, "y": 340}
  ],
  "Amennia": [
    {"x": 750, "y": 650},
    {"x": 780, "y": 680}
  ]
}
```

---

## ðŸŽ¨ UI Design

### Main Window:
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                                â”‚  PLOT PLACEMENT     â”‚
â”‚                                â”‚                     â”‚
â”‚         MAP DISPLAY            â”‚  Current Territory: â”‚
â”‚     (with territory borders)   â”‚    [Orlais]         â”‚
â”‚                                â”‚                     â”‚
â”‚      [plot markers shown]      â”‚  Plots: 3/4         â”‚
â”‚                                â”‚                     â”‚
â”‚                                â”‚  Suggested: 4       â”‚
â”‚                                â”‚                     â”‚
â”‚                                â”‚  === CONTROLS ===   â”‚
â”‚                                â”‚                     â”‚
â”‚                                â”‚  Click - Place plot â”‚
â”‚                                â”‚  Click plot - Removeâ”‚
â”‚                                â”‚  1-4 keys - Suggest â”‚
â”‚                                â”‚  R - Reset territoryâ”‚
â”‚                                â”‚  LEFT/RIGHT - Nav   â”‚
â”‚                                â”‚  S - Save           â”‚
â”‚                                â”‚  ESC - Quit         â”‚
â”‚                                â”‚                     â”‚
â”‚                                â”‚  === PROGRESS ===   â”‚
â”‚                                â”‚  Completed: 15/39   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Visual Markers:
- **Empty plot**: Green circle (hollow)
- **Selected plot**: Yellow circle (to remove)
- **Invalid placement**: Red circle (outside polygon or too close)
- **Plot radius**: ~10 pixels
- **Minimum spacing**: 30 pixels between plots

---

## ðŸ”§ Technical Implementation

### File Structure:
```python
# plot_tool.py
class PlotTool:
    def __init__(self):
        # Load map and territory polygons
        # Initialize plot data structure
        # Set up UI
    
    def select_territory(self, territory_name):
        # Switch to territory for plot placement
    
    def place_plot(self, position):
        # Validate position (inside polygon, not too close to others)
        # Add to current territory's plots
    
    def remove_plot(self, position):
        # Find nearest plot to click position
        # Remove from territory's plots
    
    def suggest_plot_count(self, territory_name):
        # Based on territory size/importance
        # Return recommended number (1-4)
    
    def save_plots(self):
        # Save to plots.json
        # UTF-8 encoding support
    
    def load_plots(self):
        # Load existing plots.json if exists
```

### Data Integration:
```python
# In map_data.py (to be added)
TERRITORY_PLOTS = {}  # Loaded from plots.json

def load_plots():
    """Load plot positions from JSON file"""
    with open('plots.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_plots(territory):
    """Get list of plot positions for a territory"""
    return TERRITORY_PLOTS.get(territory, [])
```

---

## ðŸ“‹ Suggested Plot Counts

### Recommendation Algorithm:
```python
def suggest_plot_count(territory_name):
    # Small/isolated territories
    small = ["The Comet", "Venexia", "Cinto", "Ahtep", "Liadnon", "Quil'en"]
    
    # Strategic/large territories
    large = ["Orlais", "Amennia", "Azincourne", "Espoia", "Naragonthid", 
             "Anodia", "Sordia", "Linan"]
    
    if territory_name in small:
        return 1
    elif territory_name in large:
        return 4
    else:
        return 2  # Most territories get 2-3 plots
```

### Territory Classifications:
- **1 Plot** (7 territories): Small, isolated, or low importance
- **2 Plots** (15 territories): Standard territories
- **3 Plots** (12 territories): Medium-large territories
- **4 Plots** (5 territories): Strategic capitals and major territories

---

## âœ… Validation Rules

### Plot Placement Requirements:
1. **Inside territory**: Must be within polygon bounds
2. **Minimum spacing**: 30 pixels from other plots
3. **Not on border**: At least 15 pixels from territory edge
4. **Maximum per territory**: 4 plots
5. **Visual clarity**: Should be visible and clickable

### Edge Cases:
- Very small territories might only fit 1 plot
- Large territories can spread plots across the region
- Irregular shapes need manual adjustment
- Strategic placement near territory center preferred

---

## ðŸŽ® Workflow

### User Experience:
1. **Start tool**: `python plot_tool.py`
2. **See current territory**: Highlighted with border
3. **See suggestion**: "Suggested plots: 3"
4. **Click to place**: Plots appear as green circles
5. **Click plot to remove**: If misplaced
6. **Navigate**: Arrow keys to next territory
7. **Save progress**: Auto-saves, or press 'S'
8. **Resume later**: Loads previous progress

### Time Estimate:
- **Per territory**: 30-60 seconds
- **Total time**: 20-40 minutes for all 39 territories
- Faster than polygon tool (simpler task)

---

## ðŸš€ Implementation Priority

**Create plot_tool.py BEFORE implementing buildings!**

**Reason**: 
- Buildings need plot positions to know where to display
- Tool provides clean data structure
- Manual editing of JSON would be tedious
- Visual tool ensures good placement

**Next Steps:**
1. Create plot_tool.py (similar to polygon_tool.py)
2. Place plots for all 39 territories
3. Save to plots.json
4. Load plots in main game
5. Then implement building construction system

---

## ðŸ’¡ Future Enhancements

### Possible Additions:
- **Auto-placement**: Algorithm to suggest plot positions
- **Plot types**: Different plot types for different building types
- **Visual preview**: Show building icon while placing
- **Grid snap**: Optional grid for aligned placement
- **Undo/Redo**: Full history of plot changes

---

**Status**: Design Complete - Ready for Implementation
**Estimated Development Time**: 1-2 hours
**Dependencies**: map_data.py, territory_polygons.json
**Outputs**: plots.json
