# ðŸ”§ Quick Fix - None Check Added

## âœ… What Was Fixed

The crash was caused by checking `collidepoint()` on buttons that were set to `None`.

### The Error:
```
AttributeError: 'NoneType' object has no attribute 'collidepoint'
```

### The Problem:
```python
# We set these to None at the start
self.cancel_button = None
self.demolish_button = None

# But then checked them without verifying they're not None
if hasattr(self, 'cancel_button'):  # âœ“ Has attribute
    if self.cancel_button.collidepoint(event.pos):  # âŒ CRASH if None!
```

**Note:** `hasattr()` returns `True` even if the attribute is `None`!

---

## ðŸ”§ The Fix

Changed both button checks to:

```python
# Cancel button
if hasattr(self, 'cancel_button') and self.cancel_button is not None:
    if self.cancel_button.collidepoint(event.pos):
        # Safe to call!

# Demolish button  
if hasattr(self, 'demolish_button') and self.demolish_button is not None:
    if self.demolish_button.collidepoint(event.pos):
        # Safe to call!
```

---

## ðŸŽ® Test Now!

1. **Download main.py** (934 lines) above â¬†ï¸
2. **Run:** `python main.py`
3. **Build and complete a Farm**
4. **Click the plot**
5. **Click Demolish** â†’ Should work without crashing! âœ…

---

## ðŸ“Š Expected Console Output

When clicking Demolish:

```
DEBUG: building_buttons = {}
DEBUG: Checking 0 building buttons...
DEBUG: building_buttons is empty or None!
DEBUG: Cancel button exists!  â† Will skip (is None)
DEBUG: Demolish button exists!
DEBUG: demolish_button rect = <rect(400, 742, 140, 35)>
DEBUG: Checking collidepoint...
DEBUG: Demolish button clicked!
DEBUG: Calling destroy_building(North Affrancia, 0)
ðŸ—ï¸ destroy_building called for North Affrancia plot 0
âœ… Building destroyed! Refunded 15 gold
DEBUG: destroy_building returned True
```

---

**The crash is fixed! Both buttons should work perfectly now!** ðŸŽ‰
