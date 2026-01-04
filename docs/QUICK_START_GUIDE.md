# War of Avareon - Quick Start Guide

**Version:** 2.0  
**Last Updated:** January 3, 2026  
**Status:** Ready to Play!  

---

## 🎮 **Getting Started in 5 Minutes**

### **Prerequisites**

- Python 3.8 or higher
- Pygame library

### **Installation**

```bash
# 1. Install Python (if not already installed)
# Download from https://www.python.org/downloads/

# 2. Install Pygame
pip install pygame

# 3. Navigate to game directory
cd war-of-avareon

# 4. Run the game!
python3 main.py
```

---

## 🕹️ **How to Play**

### **Game Objective**

**Win by controlling 30 territories!**

### **Basic Controls**

| Action | Control |
|--------|---------|
| **Select Territory** | Click on territory |
| **Move Army** | Click army, then click destination |
| **Open Chat** | Press ENTER |
| **End Turn** | Press SPACE |
| **Scroll Map** | Arrow keys |
| **Scroll Chat/Log** | Mouse wheel (over sidebar) |
| **Split Army** | Select army, press S |
| **Merge Armies** | Select army, press M |

---

## 📊 **Game Flow**

### **Turn Phases**

**1. Planning Phase** (Your Turn)
- Queue movement orders
- Build buildings
- Train units
- Review territory info

**2. Battle Phase** (Automatic)
- Movement orders execute
- Battles resolve
- Results displayed

**3. Income Phase** (Automatic)
- Collect gold from territories
- Buildings provide bonuses
- Training completes

### **Turn Sequence**

```
Start Turn
    ↓
Queue Orders → Build → Train Units
    ↓
Press SPACE (End Turn)
    ↓
Battles Resolve
    ↓
Collect Income
    ↓
Next Player's Turn
```

---

## 🏰 **Core Mechanics**

### **Movement**

1. Click your army
2. Click adjacent territory
3. Order queued (see Action Queue tab)
4. Press SPACE to execute

**Rules:**
- Can only move to adjacent territories
- Multiple moves can be queued
- All moves execute at end of turn
- Attacks resolve as battles

### **Combat**

**Battle Calculation:**
- **Attacker Strength** = Unit composition
- **Defender Strength** = Garrison + Keep bonus
- **Winner** = Higher strength
- **Loser** = Army destroyed

**Unit Strengths:**
- Infantry: 2 strength each
- Cavalry: 3 strength each
- Siege: 4 strength each

**Defensive Bonuses:**
- Keep building: +2 defense

**Sequential Battles:**
1. Attack garrison first
2. If garrison defeated, attack Keep
3. Territory captured if both defeated

### **Economy**

**Income Sources:**
- Territory base income (50/75/100 per turn)
- Farm: +50 gold/turn
- Market: +100 gold/turn
- Mine: +75 gold/turn

**Spending:**
- Buildings: 100-300 gold
- Units: 50-150 gold each
- Keep your gold positive!

### **Buildings**

**Building Types:**

| Building | Cost | Benefit |
|----------|------|---------|
| Farm | 100g | +50 income/turn |
| Barracks | 200g | Train units |
| Keep | 300g | +2 defense, garrison storage |
| Market | 200g | +100 income/turn |
| Mine | 150g | +75 income/turn |

**Building Rules:**
- One building per territory per turn
- Requires available plot
- Instant construction
- Immediate benefits

### **Unit Training**

**Requirements:**
- Barracks building in territory
- Sufficient gold
- Under 30-unit limit

**Training Process:**
1. Click territory with barracks
2. Click "Train Units" in bottom panel
3. Select unit type
4. Units added to training queue
5. Complete after specified turns

**Unit Types:**

| Unit | Cost | Training Time | Strength |
|------|------|---------------|----------|
| Infantry | 50g | 1 turn | 2 |
| Cavalry | 100g | 2 turns | 3 |
| Siege | 150g | 3 turns | 4 |

---

## 🎨 **UI Guide**

### **Top Panel**

Shows:
- Current player turn
- Turn number
- Turn phase
- Gold amount
- Income per turn

### **Map Area**

Displays:
- Territories (colored by owner)
- Armies (circles with numbers)
- Buildings (icons on plots)
- Selection highlight (bright green)

### **Bottom Panel**

**Territory Info:**
- Territory name
- Owner
- Income
- Buildings
- Garrison composition

**Building Controls:**
- Available building types
- Costs
- Build buttons

**Army Controls:**
- Selected army info
- Unit composition
- Split/Merge buttons

### **Right Sidebar (6 Tabs)**

**Technology** (Coming Soon)
- Tech tree
- Research options

**Heroes** (Coming Soon)
- Hero management
- Special abilities

**Action Queue** ✅
- Queued movement orders
- Cancel buttons
- Order review

**Action Log** ✅
- Game event history
- Scrollable
- Full game record

**Quests** (Coming Soon)
- Active quests
- Rewards
- Progress

**Chat** ✅
- Player communication
- Timestamps
- Scrollable history

---

## 💬 **Using Chat**

### **Opening Chat**

Press **ENTER** to activate chat input

### **Sending Messages**

1. Type your message (max 100 chars)
2. Press **ENTER** to send
3. Press **ESC** to cancel

### **Reading Chat**

- Newest messages at bottom
- Scroll up with mouse wheel
- Player names in faction colors
- Timestamps show [HH:MM:SS]

---

## 🎯 **Strategy Tips**

### **Early Game**

1. **Expand quickly** - Control more territories
2. **Build Farms** - Secure income
3. **Train Infantry** - Cheap and effective
4. **Defend borders** - Build Keeps on frontiers

### **Mid Game**

1. **Build Barracks** - Continuous unit production
2. **Train Cavalry** - Stronger units
3. **Build Markets** - Scale income
4. **Control choke points** - Strategic positions

### **Late Game**

1. **Mass armies** - Combine for big attacks
2. **Build Siege** - Strongest units
3. **Coordinate attacks** - Multiple fronts
4. **Secure victory** - Push for 30 territories

### **Advanced Tactics**

**Army Splitting:**
- Split large armies for multiple fronts
- Leave garrisons in conquered territories
- Keep mobile strike forces

**Territory Defense:**
- Keep + garrison = strong defense
- Prioritize border territories
- Don't spread too thin

**Economic Management:**
- Balance military and economy
- Don't spend all gold
- Plan building chains

---

## 🐛 **Troubleshooting**

### **Game Won't Start**

**Error:** `ModuleNotFoundError: No module named 'pygame'`
**Solution:** Install pygame: `pip install pygame`

**Error:** `FileNotFoundError: *.json`
**Solution:** Ensure all .json files are in game directory

### **Performance Issues**

**Lag or stuttering:**
1. Close other applications
2. Reduce window size in main.py:
   ```python
   WINDOW_WIDTH = 1280
   WINDOW_HEIGHT = 720
   ```

### **Display Issues**

**Sidebar cut off:**
- Window too small for resolution
- Increase window size or reduce UI scale

**Text not readable:**
- Font size too small
- Adjust font sizes in main.py

### **Gameplay Issues**

**Can't move armies:**
- Check turn phase (must be Planning)
- Verify territories are adjacent
- Ensure army hasn't moved this turn

**Can't build:**
- Check gold (need sufficient funds)
- Verify plot available
- One building per territory per turn

**Chat not working:**
- Press ENTER to activate
- Type message
- Press ENTER to send

---

## 📚 **Learning Resources**

### **In-Game Help**

- **Hover tooltips** - Hover over elements for info
- **Action Log** - Review all game events
- **Territory Info** - Click territories for details

### **Documentation**

- `SESSION_COMPLETE.md` - Complete feature documentation
- `TECHNICAL_REFERENCE.md` - Developer reference
- `game-user-stories.md` - Feature list and status
- `QUICK_REFERENCE.md` - Command reference

---

## 🎮 **Sample Game Walkthrough**

### **Turn 1 - Early Setup**

```
1. Review starting territories (4 territories)
2. Check starting gold (500g)
3. Select strongest territory
4. Build Farm (100g) → Income +50/turn
5. Queue army movement to adjacent enemy territory
6. Press SPACE to end turn
```

### **Turn 2 - First Battle**

```
1. Battle resolves automatically
2. Territory captured if won
3. Collect income (200g)
4. Build another Farm
5. Queue more movements
6. Press SPACE
```

### **Turn 5 - Scaling Up**

```
1. Now have ~6 territories, 400g income/turn
2. Build Barracks in central territory
3. Start training Infantry (50g each)
4. Build Keep on border territory
5. Continue expanding
```

### **Turn 10 - Mid Game**

```
1. Control ~12 territories
2. Have 3 barracks producing units
3. Multiple armies on different fronts
4. Using chat to coordinate (if multiplayer)
5. Reviewing Action Log for battle results
```

### **Turn 20 - Endgame Push**

```
1. Control ~25 territories
2. Need 5 more for victory
3. Mass armies for final push
4. Split armies to attack multiple fronts
5. Victory at 30 territories!
```

---

## 🏆 **Achievements (Informal)**

**First Steps:**
- ✅ Win your first battle
- ✅ Build your first building
- ✅ Train your first unit
- ✅ Capture 5 territories

**Intermediate:**
- ✅ Control 15 territories
- ✅ Earn 1000 gold in one turn
- ✅ Win with 30+ strength army
- ✅ Build all 5 building types

**Advanced:**
- ✅ Win the game (30 territories)
- ✅ Win without losing any territory
- ✅ Win in under 15 turns
- ✅ Win with 50+ territories controlled

---

## 🆘 **Getting Help**

### **Common Questions**

**Q: How do I save my game?**
A: Save/load not yet implemented. Play session completes in one sitting.

**Q: Can I play multiplayer?**
A: Local multiplayer (hotseat). Network multiplayer coming soon.

**Q: How do I undo a move?**
A: Cancel order in Action Queue tab before ending turn.

**Q: What's the maximum army size?**
A: 30 units per territory (garrison or army).

**Q: Can I replay battles?**
A: Review results in Action Log tab.

---

## 🎊 **Have Fun!**

War of Avareon is a deep strategy game with many paths to victory. Experiment with different strategies, learn from defeats, and enjoy conquering the map!

**Remember:**
- 🎯 Goal: 30 territories
- 💰 Economy matters
- 🏰 Defense is important
- ⚔️ Attack when strong
- 📊 Plan ahead

**Good luck, Commander!** 🎮

---

*Quick Start Guide v2.0*  
*Last Updated: January 3, 2026*  
*Enjoy the game!*
