# War of Avareon - Quick Reference Guide

**Last Updated:** December 29, 2024  
**Version:** TIER 2A Complete + Major Polish  
**Status:** Production Ready âœ…

---

## ðŸš€ Quick Start

### Running the Game

```bash
python main.py
```

**Requirements:**
- Python 3.x
- Pygame
- All data files in correct locations

**Files Needed:**
- main.py, game_state.py, map_data.py
- territory_polygons.json
- economic_data.json
- plots.json
- assets/map.jpg

---

## ðŸŽ® How to Play

### Setup Phase

**Goal:** Each player claims 5 starting territories

**Process:**
1. Players alternate turns
2. Click unclaimed territory to claim it
3. Costs 100 gold from starting funds
4. Repeat until both players have 5 territories

**Tips:**
- Spread out for flexibility
- Or cluster for defense
- Consider strategic value (hover to see income)

---

### Playing Phase

Each turn has three phases:

#### 1. Planning Phase ðŸ“

**Issue Movement Orders:**
- Click army circle to select (green highlight)
- Click adjacent territory to create movement order
- Visual arrow shows planned movement
- Repeat for all armies you want to move

**Check Orders:**
- View order sidebar (right side of screen)
- Toggle sidebar: Click arrow icon
- Cancel specific order: Click X button
- Cancel all orders: Click "Cancel All"

**Build Buildings:**
- Click empty plot on owned territory
- Select building type (buttons or keyboard)
- See available gold and building costs
- One building per territory per turn

**Visual Feedback:**
- Green plots = can build here
- Gray plots = can't build (already used or enemy)
- Gold highlights = selected

#### 2. Execution Phase âš¡

**What Happens:**
- Click "End Turn" button
- All movement orders execute simultaneously
- Armies arrive at destinations
- Battles marked with red sword icons

**Automatic:**
- Income collected
- Construction advances
- Turn passes to next player (or battle phase)

#### 3. Battle Phase âš”ï¸

**Resolving Battles:**
1. Click battle marker (red sword)
2. Modal shows battle details
3. Click to resolve battle
4. See sequential phases:
   - Phase 1: Attackers vs Garrison
   - Phase 2: Survivors vs Keep (if present)
5. View results
6. Click to continue to next battle

**Repeat** until all battles resolved, then next player's turn

---

## ðŸ—ï¸ Building System

### Building Types

| Building | Cost | Effect | Build Time | Keyboard |
|----------|------|--------|------------|----------|
| Farm | 30g | +10 income/turn | 1 turn | F |
| Mine | 40g | +15 income/turn | 1 turn | M |
| Barracks | 50g | Recruit armies | 1 turn | B |
| Keep | 100g | +2 defense | 2 turns | K |
| Square | 60g | +50% income | 1 turn | S |

### Building Rules

**One Per Territory Per Turn:**
- Can build on multiple territories
- But only ONE building per territory per turn
- Example: Build Farm on A, Mine on B âœ“
- Example: Build Farm on A, Mine on A âœ—

**Cancel vs Demolish:**
- **Cancel** (under construction):
  - 100% refund
  - Frees building slot for that territory
  - Can build again same turn
  
- **Demolish** (completed building):
  - 50% refund
  - Does NOT consume building slot
  - Can still build if haven't built yet

**Keep Limit:**
- Only one Keep per territory
- No limit on other buildings

**Building Preservation:**
- If you successfully defend, buildings stay
- If you lose territory, buildings destroyed

---

## ðŸŽ¯ Controls & Shortcuts

### Mouse Controls

**Territory Interaction:**
- Click territory â†’ View info panel
- Hover territory â†’ See tooltip
- Click empty space â†’ Close panels

**Army Management:**
- Click army circle â†’ Select army
- Click adjacent territory â†’ Create movement order
- Click away â†’ Deselect

**Plot Interaction:**
- Click plot â†’ Open building menu
- Click plot in info panel â†’ Same as map
- Selecting plot deselects army (and vice versa)

**Orders:**
- Click order X â†’ Cancel that order
- Click "Cancel All" â†’ Cancel all orders
- Toggle sidebar â†’ Arrow icon

**Battles:**
- Click battle marker â†’ Open battle modal
- Click modal â†’ Advance battle
- Battles resolve one at a time

### Keyboard Shortcuts

**Building:**
- F â†’ Farm
- M â†’ Mine
- B â†’ Barracks
- K â†’ Keep
- S â†’ Square

**Other:**
- T â†’ Toggle action log
- ESC â†’ Close modals

---

## ðŸ’° Economy Guide

### Income Sources

**Base Territory Income:**
- Remote (Tier 1): 10g/turn
- Standard (Tier 2): 20g/turn
- Strategic (Tier 3): 30g/turn

**Building Income:**
- Farm: +10g/turn
- Mine: +15g/turn
- Square: +50% to territory total

**Example:**
```
Territory (20g base) + Farm (10g) = 30g
With Square: 30g Ã— 1.5 = 45g/turn!
```

### Income Strategy

**Early Game:**
- Build Farms (cheap, quick income)
- Secure high-value territories
- Expand for more building slots

**Mid Game:**
- Build Mines (better income)
- Add Squares on rich territories
- Build Barracks for armies

**Late Game:**
- Optimize with Squares
- Defend high-income territories with Keeps
- Balance military and economy

---

## âš”ï¸ Combat Guide

### Combat Basics

**Sequential Combat:**
1. **Phase 1:** Attackers vs Garrison
   - 1-for-1 casualties
   - Survivors proceed to Phase 2

2. **Phase 2:** Survivors vs Keep (if present)
   - Keep provides 2 armies of defense
   - 1-for-1 casualties
   - Determine final outcome

**Example:**
```
4 attackers vs 3 garrison + Keep:
Phase 1: 4 vs 3 â†’ 1 attacker survives
Phase 2: 1 vs 2 (Keep) â†’ Keep wins
Result: Territory defended, 0 garrison, Keep survives
```

### Strategic Principles

**Attacking:**
- Need numerical superiority
- Account for garrison AND Keep
- Keep = 2 extra armies
- Total needed = Garrison + 2 (if Keep) + 1 (to win)

**Defending:**
- Garrison protects Keep
- Keep can hold alone (2 armies)
- Buildings preserved on successful defense
- Retreat not possible (fight to the end)

**Force Concentration:**
- Combine armies for attacks
- Split for defense (pending split/merge feature)
- One army per territory is vulnerable

---

## ðŸ“Š Strategic Tips

### Territory Management

**Expansion:**
- More territories = more income
- More territories = more building slots per turn
- Balance quality vs quantity

**Development:**
- One building per territory per turn
- Plan 2-3 turns ahead
- Prioritize high-value territories

**Defense:**
- Keep on border territories
- Garrison + Keep = strong defense
- Don't over-defend interior

### Economic Strategy

**Build Order:**
1. Farms (quick income boost)
2. Mines (better ROI)
3. Squares (on high-income territories)
4. Barracks (when ready to recruit)
5. Keeps (strategic defense)

**Demolish Strategy:**
- Demolish first, then build (doesn't consume slot)
- If built already, wait until next turn
- 50% loss on demolish

### Military Strategy

**Expansion:**
- Attack weak points
- Isolate enemy territories
- Cut off supply lines (block adjacencies)

**Defense:**
- Fortify borders
- Keep reserves inland
- Don't spread too thin

**Timing:**
- Build economy early
- Recruit armies mid-game
- Push for victory late-game

---

## ðŸŽ¨ UI Reference

### Screen Layout

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                                             â”‚
â”‚              MAP AREA                       â”‚
â”‚         (Territory Display)                 â”‚
â”‚                                             â”‚
â”‚  [Orders]  [Battles]  [Hover Info]         â”‚
â”‚  Sidebar   Markers    Tooltip              â”‚
â”‚                                             â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚ Player Info | End Turn | Building Controls â”‚
â”‚ Gold/Income | Button   | (When plot active)â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Color Coding

**Territories:**
- Red: Player 1
- Blue: Player 2
- Green: Player 3 (if active)
- Yellow: Player 4 (if active)
- No color: Neutral

**Plots:**
- Bright Green: Can build here this turn
- Gray: Cannot build (used or enemy)
- Gold: Selected
- Yellow: Under construction

**Armies:**
- Green highlight: Selected
- Darker overlay: Already moved
- Normal: Unmoved, available

**Buildings:**
- Gray circle: Completed
- Yellow circle: Under construction
- Letter indicates type (F/M/B/K/S)

---

## ðŸ“‹ Info Displays

### Territory Info Panel

**Shows:**
- Territory name
- Owner (color-coded)
- Combat power (armies + Keep)
- Buildings (with counts)
- Available plots

**Access:**
- Click any territory
- View on left side of bottom panel
- Plot grid on right (clickable)

### Hover Tooltips

**Shows:**
- Territory name
- Owner
- Combat power (with Keep bonus if present)
- Buildings (e.g., "2 Farms, 1 Mine")
- Available plots (if any)

**Compact and informative!**

### Action Log

**Shows:**
- Recent actions
- Combat results
- Construction updates
- Income collection

**Toggle:** T key or button

---

## ðŸ› Troubleshooting

### Common Issues

**Game Won't Start:**
- Check Python version (3.x)
- Install pygame: `pip install pygame`
- Verify all files present

**Can't Move Army:**
- Already moved? (darker overlay)
- Not adjacent? (check map)
- Not your turn?
- In battle phase? (resolve battles first)

**Can't Build:**
- Already built on this territory? (plots gray)
- Not enough gold?
- Plot occupied?
- Enemy territory?

**Orders Not Executing:**
- Click "End Turn" to execute
- Check if battles need resolution
- Verify orders in sidebar

---

## ðŸ“ˆ Game Progression

### Typical Game Flow

**Turns 1-3:** Setup
- Claim starting territories
- Assess strategic situation
- Plan initial strategy

**Turns 4-10:** Development
- Build Farms for income
- Expand to adjacent territories
- Build economic base

**Turns 11-20:** Growth
- Build Mines and Squares
- Start recruiting armies (when Barracks available)
- Fortify borders with Keeps

**Turns 21-30:** Conquest
- Launch coordinated attacks
- Capture enemy territories
- Push for 30 territory victory

**Turn 30+:** End Game
- All-out warfare
- Economic advantage critical
- Strategic positioning wins

---

## ðŸŽ¯ Victory Conditions

**Current:** First to 30 territories wins!

**Tracking:**
- Live scoreboard shows territory counts
- Victory detected automatically
- Victory screen with options

**Strategy:**
- Economic expansion early
- Military pressure mid-game
- Final push for territory count

---

## ðŸ“š Additional Resources

### Documentation Files

**Core:**
- PROJECT_STATUS.md - Overall project status
- TIER2_PROGRESS.md - Detailed progress tracker
- game-user-stories.md - Complete roadmap

**Features:**
- Sequential battle system docs
- Building limit system docs
- Territory info panel docs
- Visual polish docs

**Tools:**
- polygon_tool.py - Edit territory boundaries
- adjacency_tool.py - Fix adjacencies
- economic_tool.py - Assign income tiers
- plot_tool.py - Place building plots

---

## ðŸŽ® Play Tips

### For New Players

**Start Simple:**
- Focus on economy first
- Build Farms early
- Don't over-expand initially
- Learn combat mechanics

**Then Add:**
- Strategic Keep placement
- Coordinated attacks
- Multi-turn planning
- Building optimization

### For Experienced Players

**Optimize:**
- Calculate income ROI
- Min-max building placement
- Plan 5+ turns ahead
- Master split/merge (when available)

**Advanced:**
- Economic timing attacks
- Fortress breaching strategies
- Resource denial tactics
- Victory condition racing

---

## âœ¨ Summary

**Game Flow:** Setup â†’ Planning â†’ Execution â†’ Battles â†’ Repeat  
**Victory:** 30 territories  
**Strategy:** Balance economy and military  
**Polish:** Professional UI with extensive feedback

**Enjoy the strategic depth!** ðŸŽ®

---

**Last Updated:** December 29, 2024  
**Version:** Production Ready  
**Status:** All core features working âœ…  
**Next Update:** After recruitment and split/merge implementation ðŸš€
