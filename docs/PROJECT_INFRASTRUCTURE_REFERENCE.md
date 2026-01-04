# Project Infrastructure & Tools Reference

**Date:** December 30, 2024  
**Purpose:** Document all project files and tools used by Phase 3  
**Status:** Reference Documentation  

---

## ðŸ“ Complete Project File Structure

```
/mnt/project/
â”œâ”€â”€ main.py                          # Main game loop and rendering
â”œâ”€â”€ game_state.py                    # Game state and logic
â”œâ”€â”€ map_data.py                      # Map data and territory definitions
â”œâ”€â”€ economic_data.json               # Territory economic values
â”œâ”€â”€ plots.json                       # Building plot locations
â”œâ”€â”€ territory_polygons.json          # Territory boundary polygons
â”œâ”€â”€ adjacency_tool.py                # Territory adjacency queries
â”œâ”€â”€ economic_tool.py                 # Economic data access
â”œâ”€â”€ plot_tool.py                     # Building plot queries
â”œâ”€â”€ polygon_tool.py                  # Territory polygon rendering
â”œâ”€â”€ README.md                        # Project overview
â”œâ”€â”€ QUICK_REFERENCE.md               # Quick commands reference
â””â”€â”€ docs/                            # Documentation (NEW in this session)
    â”œâ”€â”€ DOCUMENTATION_INDEX.md
    â”œâ”€â”€ PROJECT_STATUS_UPDATE.md
    â”œâ”€â”€ sessions/
    â”œâ”€â”€ guides/
    â”œâ”€â”€ features/
    â””â”€â”€ bugfixes/
```

---

## ðŸ—ºï¸ Core Map System

### map_data.py

**Purpose:** Central map data provider and territory information

**Key Functions Used in Phase 3:**

```python
# Territory queries
map_data.get_all_territories() 
# Returns: List of all territory names
# Used in: Turn cycle, status reset loops

map_data.are_adjacent(territory1, territory2)
# Returns: Boolean - whether territories share border
# Used in: Order validation, movement rules

map_data.get_territory_center(territory)
# Returns: (x, y) tuple - territory center coordinates
# Used in: Army circle positioning, arrow drawing

map_data.get_territory_income(territory)
# Returns: Integer - base income value for territory
# Used in: Income calculation, economic display
```

**Usage in Phase 3:**
```python
# Example from order validation:
if not map_data.are_adjacent(from_territory, to_territory):
    self.add_message("Territories are not adjacent!")
    return False

# Example from turn cycle:
for territory in map_data.get_all_territories():
    self.armies[territory] = self.armies_unmoved[territory] + self.armies_moved[territory]
```

**Dependencies:** None (standalone module)

---

## ðŸ’° Economic System

### economic_data.json

**Purpose:** Stores base economic values for all territories

**Structure:**
```json
{
  "TerritoryName": {
    "base_income": 30,
    "resource_type": "agricultural",
    "economic_tier": 2
  }
}
```

**Access Method:**
```python
income = map_data.get_territory_income(territory)
```

**Used In:**
- Income calculation at turn end
- Territory info panel display
- Economic tooltips

**Phase 3 Impact:** None - economic values unchanged

---

### economic_tool.py

**Purpose:** Economic data access utilities

**Key Functions:**
```python
economic_tool.get_income(territory)
# Returns base income for territory

economic_tool.calculate_modified_income(territory, buildings)
# Returns income with building bonuses applied
```

**Usage in Phase 3:**
- Territory income display in UI panel
- Income calculation when collecting gold
- Economic tooltips on hover

**Note:** Used but not modified in this session

---

## ðŸ“ Plot & Polygon System

### plots.json

**Purpose:** Defines building plot locations within territories

**Structure:**
```json
{
  "TerritoryName": [
    {"x": 100, "y": 150, "type": "standard"},
    {"x": 120, "y": 160, "type": "standard"}
  ]
}
```

**Access Method:**
```python
plots = plot_tool.get_plots(territory)
```

**Used In:**
- Building plot rendering
- Plot click detection
- Construction system

**Phase 3 Impact:** None - plots unchanged, but UI shares space with composition UI

---

### plot_tool.py

**Purpose:** Building plot query utilities

**Key Functions:**
```python
plot_tool.get_plots(territory)
# Returns list of plot dictionaries for territory

plot_tool.get_plot_count(territory)
# Returns number of available plots

plot_tool.is_valid_plot(territory, plot_index)
# Validates plot exists
```

**Usage in Phase 3:**
- Territory info panel shows plot count
- Building UI integration
- Plot availability checks

**Note:** Used but not modified in this session

---

### territory_polygons.json

**Purpose:** Stores territory boundary polygons for rendering

**Structure:**
```json
{
  "TerritoryName": {
    "coordinates": [[x1, y1], [x2, y2], ...],
    "center": [cx, cy]
  }
}
```

**Access Method:**
```python
polygon = polygon_tool.get_polygon(territory)
```

**Used In:**
- Territory rendering
- Border drawing
- Click detection (point-in-polygon)
- Hover detection

**Phase 3 Impact:** Used for territory selection and composition UI triggering

---

### polygon_tool.py

**Purpose:** Territory polygon utilities

**Key Functions:**
```python
polygon_tool.get_polygon(territory)
# Returns polygon coordinates

polygon_tool.point_in_polygon(point, polygon)
# Tests if point is inside territory
# Used for: Click detection

polygon_tool.get_scaled_polygon(polygon, zoom, offset)
# Returns scaled polygon for current view
# Used for: Rendering at different zoom levels
```

**Usage in Phase 3:**
- Detecting which territory was clicked
- Determining when to open composition UI
- Rendering territory selection highlights

**Note:** Critical for UI interaction, not modified

---

### adjacency_tool.py

**Purpose:** Territory adjacency queries and pathfinding

**Key Functions:**
```python
adjacency_tool.get_adjacent_territories(territory)
# Returns list of neighboring territories
# Used in: Order validation

adjacency_tool.are_adjacent(territory1, territory2)
# Boolean check for adjacency
# Used in: Movement validation

adjacency_tool.find_path(start, end)
# Finds shortest path between territories
# Used in: Future AI pathfinding (not yet implemented)
```

**Usage in Phase 3:**
```python
# Critical for order validation:
if not map_data.are_adjacent(from_territory, to_territory):
    return False  # Can't move to non-adjacent territory

# Used in right-click handler:
if map_data.are_adjacent(source_territory, clicked_territory):
    # Valid move order
    create_order(source_territory, clicked_territory)
```

**Note:** Essential for movement rules, not modified

---

## ðŸ”§ How Tools Are Used in Phase 3

### Data Flow

**1. Territory Selection:**
```
User clicks map
    â†“
polygon_tool.point_in_polygon() â†’ Determine which territory
    â†“
Show composition UI for that territory
```

**2. Order Creation:**
```
User right-clicks destination
    â†“
adjacency_tool.are_adjacent() â†’ Validate adjacency
    â†“
map_data.get_territory_center() â†’ Get coordinates for arrow
    â†“
Create MovementOrder with unit_ids
```

**3. UI Display:**
```
Territory info panel
    â†“
economic_tool.get_income() â†’ Get base income
    â†“
plot_tool.get_plot_count() â†’ Get building slots
    â†“
Display in bottom panel
```

**4. Turn Cycle:**
```
Next player turn
    â†“
map_data.get_all_territories() â†’ Loop through all
    â†“
Reset army statuses for each territory
```

---

## ðŸ“Š Tool Dependencies

### Dependency Graph

```
main.py
  â”œâ”€â”€ game_state.py
  â”œâ”€â”€ map_data.py
  â”‚   â”œâ”€â”€ economic_data.json
  â”‚   â”œâ”€â”€ plots.json
  â”‚   â””â”€â”€ territory_polygons.json
  â”œâ”€â”€ polygon_tool.py â†’ territory_polygons.json
  â”œâ”€â”€ plot_tool.py â†’ plots.json
  â”œâ”€â”€ economic_tool.py â†’ economic_data.json
  â””â”€â”€ adjacency_tool.py â†’ map_data.py
```

### Import Structure

**main.py imports:**
```python
import map_data
import polygon_tool
import plot_tool
# Uses these for rendering and interaction
```

**game_state.py imports:**
```python
import map_data
import economic_tool
import adjacency_tool
# Uses these for game logic and validation
```

**Tools are standalone:** Each tool is self-contained and can be used independently

---

## ðŸŽ¯ Which Tools Phase 3 Uses

### Heavily Used (Every Frame)

**polygon_tool.py**
- Territory rendering
- Click detection
- Selection highlights
- Used: Every frame during rendering

**map_data.py**
- Territory queries
- Adjacency checks
- Center coordinates for armies
- Used: Constantly throughout game loop

---

### Regularly Used (Game Events)

**adjacency_tool.py**
- Order validation (every order creation)
- Movement rules (every right-click)
- Used: Every time player interacts with map

**economic_tool.py**
- Territory info display (when territory selected)
- Income calculation (every turn end)
- Used: On selection and turn boundaries

**plot_tool.py**
- Building plot display (when territory selected)
- Plot availability (when building)
- Used: When interacting with territories

---

### Data Files (Static)

**economic_data.json**
- Loaded once at startup
- Referenced for income values
- Not modified at runtime

**plots.json**
- Loaded once at startup
- Referenced for plot positions
- Not modified at runtime

**territory_polygons.json**
- Loaded once at startup
- Referenced for rendering
- Not modified at runtime

---

## ðŸ” Tool Integration Points

### 1. Composition UI Opening

**Files Involved:** main.py, map_data.py, polygon_tool.py

```python
# User clicks army
clicked_territory = None
for territory in map_data.get_all_territories():
    polygon = polygon_tool.get_polygon(territory)
    if polygon_tool.point_in_polygon(mouse_pos, polygon):
        clicked_territory = territory
        break

if clicked_territory and has_armies:
    # Open composition UI
    self.show_army_composition = True
    self.army_composition_territory = clicked_territory
```

---

### 2. Order Validation

**Files Involved:** game_state.py, map_data.py, adjacency_tool.py

```python
def add_movement_order_for_units(self, from_territory, to_territory, unit_ids):
    # Validate adjacency
    if not map_data.are_adjacent(from_territory, to_territory):
        self.add_message("Territories are not adjacent!")
        return False
    
    # Rest of order creation...
```

---

### 3. Territory Info Display

**Files Involved:** main.py, economic_tool.py, plot_tool.py

```python
def draw_territory_info_panel(self):
    territory = self.selected_territory_info
    
    # Get economic info
    income = economic_tool.get_income(territory)
    
    # Get plot info
    plot_count = plot_tool.get_plot_count(territory)
    
    # Display in UI panel
    self.screen.blit(income_text, ...)
    self.screen.blit(plot_text, ...)
```

---

### 4. Arrow Drawing

**Files Involved:** main.py, map_data.py

```python
def draw_movement_arrows(self):
    for order in self.game_state.movement_orders:
        # Get coordinates
        from_center = map_data.get_territory_center(order.from_territory)
        to_center = map_data.get_territory_center(order.to_territory)
        
        # Draw arrow from center to center
        pygame.draw.line(self.screen, color, from_center, to_center)
```

---

## ðŸ“ Why Tools Weren't Modified

### Reasons for Not Changing Tools

**1. Well-Designed Interfaces**
- Tools provide clean APIs
- No need to change internal implementation
- map_data.are_adjacent() works perfectly as-is

**2. Separation of Concerns**
- Tools handle data access
- main.py handles rendering
- game_state.py handles logic
- Clear boundaries = no need to mix

**3. Stability**
- Existing tools are tested and working
- No bugs in tool functionality
- "If it ain't broke, don't fix it"

**4. Phase 3 Focus**
- Phase 3 is about army management
- Not about map data or adjacency
- Tools provide infrastructure, not features

---

## ðŸ”„ Data Flow Example

### Complete Flow: Creating Split Orders

```
1. User clicks army (main.py)
   â†“
2. polygon_tool identifies territory
   â†“
3. main.py opens composition UI
   â†“
4. User selects units 1-3
   â†“
5. User right-clicks destination
   â†“
6. adjacency_tool validates adjacency
   â†“
7. game_state creates order with unit_ids
   â†“
8. map_data.get_territory_center() for arrow
   â†“
9. main.py draws yellow arrow
   â†“
10. User clicks End Turn
    â†“
11. game_state executes orders
    â†“
12. map_data.get_all_territories() for updates
    â†“
13. Turn advances
```

**Tools used:** 5 (polygon_tool, adjacency_tool, map_data, main.py, game_state.py)  
**Tools modified:** 2 (main.py, game_state.py)  
**Tools unchanged but essential:** 3 (polygon_tool, adjacency_tool, map_data)

---

## ðŸ’¡ Best Practices for Using Tools

### Do's

âœ… **Use tool functions** - Don't reimplement adjacency checking  
âœ… **Trust tool data** - Don't second-guess map_data coordinates  
âœ… **Cache when appropriate** - Tool results are stable within a frame  
âœ… **Handle errors** - Tools may return None if data missing  

### Don'ts

âŒ **Don't modify tool data directly** - Use tool functions  
âŒ **Don't bypass tools** - Always use adjacency_tool for adjacency  
âŒ **Don't duplicate tool logic** - Reuse existing functions  
âŒ **Don't assume tool state** - Always check return values  

---

## ðŸ”® Future Tool Enhancements

### Potential Additions (Not in Current Phase)

**map_data.py:**
- `get_territories_within_range(territory, distance)` - For AI planning
- `get_territory_strategic_value(territory)` - For AI targeting

**adjacency_tool.py:**
- `find_shortest_path(start, end)` - For AI pathfinding
- `get_movement_cost(from, to)` - For terrain effects

**economic_tool.py:**
- `get_total_player_income(player)` - For player comparison
- `get_territory_value_with_buildings(territory)` - For investment decisions

**plot_tool.py:**
- `get_optimal_building_placement(territory)` - For AI building
- `get_available_plot_count(territory)` - For expansion planning

**These would support future AI and advanced features**

---

## ðŸ“š Tool Documentation

### Where to Find More

**Each tool has inline documentation:**
```python
def are_adjacent(territory1, territory2):
    """
    Check if two territories share a border.
    
    Args:
        territory1: Name of first territory
        territory2: Name of second territory
    
    Returns:
        Boolean: True if territories are adjacent
    """
```

**README.md** - Project overview and setup  
**QUICK_REFERENCE.md** - Quick command reference  

---

## âœ… Summary

### Tools Status

| Tool | Purpose | Used in Phase 3? | Modified? | Critical? |
|------|---------|------------------|-----------|-----------|
| map_data.py | Map queries | âœ… Yes | âŒ No | âœ… Critical |
| adjacency_tool.py | Adjacency | âœ… Yes | âŒ No | âœ… Critical |
| economic_tool.py | Economy | âœ… Yes | âŒ No | âš ï¸ Important |
| plot_tool.py | Building plots | âœ… Yes | âŒ No | âš ï¸ Important |
| polygon_tool.py | Territory polygons | âœ… Yes | âŒ No | âœ… Critical |
| economic_data.json | Economic values | âœ… Yes | âŒ No | ðŸ“Š Data |
| plots.json | Plot positions | âœ… Yes | âŒ No | ðŸ“Š Data |
| territory_polygons.json | Territory shapes | âœ… Yes | âŒ No | ðŸ“Š Data |

---

### Integration Summary

**Phase 3 builds on existing infrastructure:**
- Uses all 5 tool files
- Uses all 3 data files
- Modifies 2 core files (main.py, game_state.py)
- Adds 0 new tool files
- **Total project stability maintained!** âœ…

**All tools continue to work exactly as before**  
**No breaking changes to tool APIs**  
**Full backward compatibility**

---

## ðŸŽ¯ Key Takeaway

**Phase 3 successfully integrates with all existing project infrastructure.**

The individual army management system:
- âœ… Uses existing tools correctly
- âœ… Respects tool APIs
- âœ… Maintains project architecture
- âœ… Adds no tool dependencies
- âœ… Works seamlessly with existing systems

**The tools are the foundation. Phase 3 is the feature built on top.**

---

**Last Updated:** December 30, 2024  
**Status:** Complete infrastructure reference âœ…  
**Purpose:** Document all project tools and their usage in Phase 3
