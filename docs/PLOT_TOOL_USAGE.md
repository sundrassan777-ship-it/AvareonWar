# Plot Tool - Quick Start Guide

## ðŸš€ How to Use

### 1. Run the Tool
```bash
python plot_tool.py
```

### 2. Place Plots
- **Current territory** is highlighted in blue
- **Click inside the territory** to place a green plot marker
- **Click on a plot** to remove it
- Plots must be at least 30 pixels apart

### 3. Navigate
- **LEFT/RIGHT arrows**: Move between territories
- **R**: Clear all plots from current territory
- **S**: Save progress (also auto-saves after each change)
- **ESC**: Quit and save

---

## ðŸ“Š Plot Placement Guidelines

### Suggested Plot Counts:

**1 Plot** (Small/Isolated):
- The Comet, Venexia, RÃ©via, Cinto, Ahtep, Liadnon, Quil'en

**2-3 Plots** (Standard/Medium):
- Most territories fall in this category
- Place plots spread across the territory

**4 Plots** (Strategic/Large):
- Orlais, Amennia, Azincourne, Espoia, Naragonthid
- Anodia, Sordia, Linan, Nefrid, Odatria

### Placement Tips:
- âœ… Space plots evenly across the territory
- âœ… Keep plots away from borders (15px minimum)
- âœ… Keep plots 30px apart from each other
- âœ… Place near territory center when possible
- âŒ Don't place plots too close to edges (hard to click in game)
- âŒ Don't cluster all plots in one corner

---

## ðŸŽ¨ Visual Guide

```
Territory Border
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                             â”‚
â”‚    O           O            â”‚  O = Plot locations
â”‚                             â”‚  (green circles)
â”‚                             â”‚
â”‚           O                 â”‚  Space them out!
â”‚                             â”‚
â”‚                             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**Good Spacing:**
```
    O       O
         
         O       O
```

**Bad Spacing (too close):**
```
    O O
    O O
```

---

## âš¡ Speed Tips

### Fast Workflow:
1. **Look at territory size** (small, medium, large)
2. **Click 1-4 times** based on size
3. **Space evenly** across the territory
4. **Press RIGHT arrow** to next territory
5. Repeat for all 39 territories

### Time Estimate:
- Simple territories: 20-30 seconds
- Complex territories: 40-60 seconds
- **Total time: 20-40 minutes** for all 39

---

## ðŸ› Troubleshooting

### Plot won't place:
- âŒ Too close to another plot (30px minimum)
- âŒ Outside territory border
- âŒ Already have 4 plots (maximum)

### Can't see plots:
- âœ… Make sure you're looking at current territory (blue highlight)
- âœ… Plots appear as green circles with black outline
- âœ… Other territories' plots shown as gray

### Lost progress:
- âœ… Tool auto-saves after each change
- âœ… Load previous progress by running tool again
- âœ… Progress saved in `plots.json`

---

## ðŸ“ Output

**File created**: `plots.json`

**Format**:
```json
{
  "Orlais": [
    [450, 320],
    [480, 350],
    [420, 340],
    [460, 380]
  ],
  "Amennia": [
    [750, 650],
    [780, 680]
  ]
}
```

---

## âœ… After Completion

Once you've placed plots for all 39 territories:

1. **plots.json** will be in your project directory
2. This file will be loaded by the main game
3. Plots will appear as clickable locations for building construction
4. Buildings will display as icons on these plot positions

---

## ðŸŽ¯ What's Next?

After completing plot placement:
1. âœ… Territory Income System
2. âœ… Resource Display
3. âœ… Building Construction UI
4. âœ… Army Recruitment

**You're building the foundation for the entire economic system!** ðŸ—ï¸

---

**Ready? Run `python plot_tool.py` and let's place some plots!** ðŸš€
