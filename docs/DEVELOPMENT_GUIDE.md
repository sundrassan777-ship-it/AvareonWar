# Avareon War - Development Guide

**Purpose:** Guide for developers and Claude Code

**Target Audience:** AI assistants, new developers

---

## 🚀 Getting Started

### For Claude Code:

1. **Read Documentation First:**
   - README.md - Project overview
   - ARCHITECTURE.md - System design
   - MODULE_GUIDE.md - Detailed modules
   - GAME_MECHANICS.md - Game rules

2. **Understand Current State:**
   - Check USER_STORIES_PROGRESS.md
   - See what's implemented
   - Know what's pending

3. **Before Making Changes:**
   - Read relevant module docs
   - Understand existing patterns
   - Check QUICK_REFERENCE.md

---

## 🎯 Development Workflow

### 1. Planning

**Before writing code:**
- [ ] Identify which module(s) to modify
- [ ] Read module documentation
- [ ] Understand data flow
- [ ] Check for similar existing code
- [ ] Plan changes carefully

### 2. Implementation

**While coding:**
- [ ] Follow existing patterns
- [ ] Match code style
- [ ] Add docstrings
- [ ] Comment complex logic
- [ ] Keep changes focused

### 3. Testing

**After coding:**
- [ ] Test feature manually
- [ ] Check edge cases
- [ ] Verify no regressions
- [ ] Test with different scenarios

---

## 📐 Design Patterns to Follow

### 1. Separation of Concerns

**Game Logic** (game_state.py):
```python
# ✅ Good
def conquer_territory(self, territory, player):
    self.territory_owners[territory] = player
    self.add_action_log(f"{player} conquered {territory}")

# ❌ Bad
def conquer_territory(self, territory, player):
    self.territory_owners[territory] = player
    self.screen.blit(...)  # NO! No rendering in game logic
```

**Rendering** (rendering/):
```python
# ✅ Good
def draw_territory(self, territory):
    owner = self.game.game_state.get_territory_owner(territory)
    color = PLAYER_COLORS[owner]
    # Draw...

# ❌ Bad
def draw_territory(self, territory):
    self.game.game_state.territory_owners[territory] = player  # NO! No state modification
```

### 2. State Access Pattern

**Always use methods, not direct access:**
```python
# ✅ Good
owner = game_state.get_territory_owner(territory)
game_state.set_territory_armies(territory, 10)

# ❌ Bad
owner = game_state.territory_owners[territory]  # Direct access
game_state.territory_armies[territory] = 10     # Direct modification
```

### 3. Delegation Pattern

**In main.py:**
```python
# ✅ Good
def draw_territories(self):
    self.map_renderer.draw_territories()  # Delegate

# ❌ Bad
def draw_territories(self):
    # 100 lines of rendering code...  # Don't do all work here
```

---

## 🔧 Common Tasks

### Adding a New Building Type

**1. Define in constants.py:**
```python
BUILDING_TYPES = {
    'NewBuilding': {
        'cost': 25,
        'construction_turns': 2,
        'income_bonus': 4
    }
}
```

**2. Add to game_state.py:**
```python
def get_building_income(self, territory):
    buildings = self.completed_buildings.get(territory, {})
    income = 0
    for building in buildings.values():
        if building['type'] == 'Farm':
            income += 2
        elif building['type'] == 'NewBuilding':  # Add here
            income += 4
    return income
```

**3. Update UI (ui_renderer.py or main.py):**
```python
# Add to building menu
building_types = ['Farm', 'Mine', 'NewBuilding']  # Add here
```

**4. Test:**
- Can build it?
- Cost correct?
- Construction time correct?
- Income applies?

---

### Adding a New Unit Type

**1. Define in constants.py:**
```python
UNIT_TYPES = {
    'NewUnit': {
        'cost': 15,
        'strength': 1.3,
        'special': 'description'
    }
}
```

**2. Add to game_state.py:**
```python
def calculate_unit_strength(self, unit_type, count):
    strengths = {
        'Infantry': 1.0,
        'Cavalry': 1.2,
        'NewUnit': 1.3,  # Add here
    }
    return count * strengths.get(unit_type, 1.0)
```

**3. Update recruitment UI:**
```python
# Add to recruitment menu
unit_types = ['Infantry', 'Cavalry', 'NewUnit']
```

**4. Test:**
- Can recruit?
- Cost correct?
- Strength correct?
- Shows in tooltips?

---

### Adding a New UI Element

**1. Choose location:**
- Top panel? → ui_renderer.py: draw_top_panel()
- Menu? → ui_renderer.py: draw_game_menu()
- Sidebar? → ui_renderer.py: _draw_xxx_content()
- Map overlay? → map_renderer.py

**2. Draw the element:**
```python
def draw_my_element(self):
    # Calculate position
    x = 100
    y = 200
    
    # Draw background
    rect = pygame.Rect(x, y, 200, 50)
    pygame.draw.rect(self.game.screen, (50, 50, 50), rect)
    
    # Draw text
    text = self.game.font.render("My Element", True, WHITE)
    self.game.screen.blit(text, (x + 10, y + 10))
    
    # Store rect for clicks
    self.game.my_element_rect = rect
```

**3. Handle clicks (mouse_handler.py):**
```python
# Add to priority list
if self.game.my_element_rect and self.game.my_element_rect.collidepoint(pos):
    return self.game.handle_my_element_click(pos)
```

**4. Add click handler (main.py):**
```python
def handle_my_element_click(self, pos):
    # Handle the click
    print("Element clicked!")
    return True
```

---

### Modifying Game Rules

**Always in game_state.py:**

**Example: Change battle calculations**
```python
def calculate_battle_strength(self, player, territory, army_count):
    # Base strength
    strength = army_count * 10
    
    # Add your modifications here
    if self.has_special_bonus(territory):
        strength *= 1.2
    
    # Existing modifiers
    if self.has_keep(territory):
        strength *= 1.5
    
    return strength
```

**Test thoroughly:**
- Edge cases
- Balance implications
- UI updates correctly

---

## 🐛 Debugging Tips

### Common Issues:

**1. Click not working?**
- Check mouse_handler.py priority
- Check rect stored correctly
- Check if higher priority consumes click

**2. State not updating?**
- Check if method called
- Check if validation passes
- Check if phase correct

**3. UI not showing?**
- Check if drawn in correct layer
- Check z-order (draw order)
- Check if hidden by modal

**4. Crash on startup?**
- Check imports
- Check JSON file format
- Check missing resources

---

## 📝 Code Style

### Docstrings:

```python
def my_method(self, param1, param2):
    """
    Brief description of what method does.
    
    Longer description if needed. Explain:
    - Purpose
    - Side effects
    - Important notes
    
    Args:
        param1: Description
        param2: Description
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When param invalid
    """
    pass
```

### Comments:

```python
# Good: Explain WHY
# Calculate adjusted strength based on terrain
strength *= terrain_modifier

# Bad: Explain WHAT (code already shows what)
# Multiply strength by terrain modifier
strength *= terrain_modifier
```

### Naming:

```python
# ✅ Good
def calculate_player_income(player):
    territory_count = len(owned_territories)
    
# ❌ Bad
def calc_inc(p):
    tc = len(ot)
```

---

## 🧪 Testing Checklist

### Before Committing:

- [ ] Game launches without errors
- [ ] New feature works as expected
- [ ] Existing features still work
- [ ] No console errors
- [ ] UI displays correctly
- [ ] Clicks work properly
- [ ] Edge cases handled
- [ ] Performance acceptable

### Specific Tests:

**For Game Logic Changes:**
- [ ] Works in all phases
- [ ] State stays consistent
- [ ] No negative values
- [ ] Validation works

**For UI Changes:**
- [ ] Visible at all resolutions
- [ ] Text readable
- [ ] Buttons clickable
- [ ] Tooltips work
- [ ] No visual glitches

**For Rendering Changes:**
- [ ] Draws at 60 FPS
- [ ] Scales with zoom
- [ ] Camera works
- [ ] No flickering

---

## 🚫 Common Mistakes to Avoid

### 1. Breaking Separation

```python
# ❌ Don't mix concerns
def draw_territory(self):
    # Drawing code...
    self.game_state.territory_owners[terr] = player  # NO!
```

### 2. Direct State Access

```python
# ❌ Don't access directly
armies = game_state.territory_armies[terr]

# ✅ Use methods
armies = game_state.get_territory_armies(terr)
```

### 3. Forgetting Layout Values

```python
# ❌ Don't use bare constants in UI
y = 900  # Hard-coded!

# ✅ Use layout values
y = self.BOTTOM_UI_Y
```

### 4. Not Handling Errors

```python
# ❌ Don't assume success
building_queue[territory].append(...)

# ✅ Validate first
if territory in building_queue:
    building_queue[territory].append(...)
```

---

## 📚 Resources

### Documentation:
- ARCHITECTURE.md - Design overview
- MODULE_GUIDE.md - Detailed module info
- GAME_MECHANICS.md - Game rules
- QUICK_REFERENCE.md - Quick lookups

### Tools:
- plot_tool.py - Visual plot editing
- economic_tool.py - Economy editing
- adjacency_tool.py - Adjacency editing

### Data Files:
- territory_polygons.json - Map shapes
- economic_data.json - Economies/terrain
- plots.json - Building locations

---

## 🎯 Best Practices Summary

1. **Read docs first** - Understand before changing
2. **Follow patterns** - Match existing code style
3. **Separate concerns** - Logic vs rendering vs input
4. **Use methods** - Not direct state access
5. **Test thoroughly** - Manual testing required
6. **Document changes** - Docstrings and comments
7. **Keep focused** - One feature at a time
8. **Ask for help** - Check docs, reference code

---

**Last Updated:** January 5, 2026
