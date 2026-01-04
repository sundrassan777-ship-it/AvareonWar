# Economic Tool - Quick Start Guide

## Ã°Å¸Å¡â‚¬ How to Use

### 1. Run the Tool
```bash
python economic_tool.py
```

### 2. Assign Economic Tiers
- **Current territory** is highlighted with its tier color
- **Press 1, 2, or 3** to assign economic tier
- **LEFT/RIGHT arrows**: Navigate between territories
- **S**: Save progress (also auto-saves)
- **ESC**: Quit

---

## Ã°Å¸â€™Â° Economic Tier System

### Tier 1 - Poor/Remote (10 gold/turn)
**Color**: Light Green
**Description**: Small, remote, or economically weak territories
**Suggested Territories**:
- The Comet (tiny, isolated)
- Venexia (remote)
- RÃƒÂ©via (small)
- Elletia (corner)
- Cinto (small)
- Ahtep (remote)
- Liadnon (small)
- Quil'en (isolated)
- Sstep (remote)
- Conda (small)
- Ahara (remote)
- Oucine (small)

**Total Suggested**: ~12 territories

### Tier 2 - Standard (20 gold/turn)
**Color**: Gold/Yellow
**Description**: Average territories - most of the map
**Strategy**: Default for most territories
**Total Suggested**: ~20 territories

### Tier 3 - Wealthy/Strategic (30 gold/turn)
**Color**: Dark Orange
**Description**: Major cities, trade centers, strategic locations
**Suggested Territories**:
- Orlais (major city, capital)
- Amennia (strategic region)
- Azincourne (capital)
- Naragonthid (large, important)
- Espoia (central trade hub)
- Linan (strategic position)
- Sordia (central location)

**Total Suggested**: ~7 territories

---

## Ã°Å¸Å½Â¨ Visual Guide

### Map Display:
All territories are colored by their economic tier:
- **Light Green** = Tier 1 (10g)
- **Gold** = Tier 2 (20g)
- **Dark Orange** = Tier 3 (30g)

### Current Territory:
- Highlighted with thick outline
- Shows current tier assignment
- Displays income value

---

## Ã°Å¸â€œÅ  Statistics Panel

The tool shows real-time statistics:
```
Tier 1: 12 (31%)
Tier 2: 20 (51%)
Tier 3: 7 (18%)
Average: 19.2g/territory
```

### Balance Guidelines:
- **Tier 1**: 25-35% of territories
- **Tier 2**: 50-60% of territories
- **Tier 3**: 15-25% of territories

This creates good strategic variety!

---

## Ã°Å¸Å½Â¯ Assignment Strategy

### Consider:
1. **Territory Size**: Larger = higher tier
2. **Strategic Position**: Central = higher tier
3. **Plot Count**: More plots = higher tier potential
4. **Geographic Features**: Islands/corners = lower tier
5. **Lore/Importance**: Capitals = highest tier

### Example Decisions:
- **The Comet**: Tiny island Ã¢â€ â€™ Tier 1
- **Orlais**: Major city, central Ã¢â€ â€™ Tier 3
- **Vense**: Medium territory Ã¢â€ â€™ Tier 2
- **Amennia**: Strategic, many plots Ã¢â€ â€™ Tier 3

---

## Ã¢Å¡Â¡ Speed Tips

### Fast Workflow:
1. **Start with suggestions**: Tool highlights suggested tier
2. **Press number key** (1, 2, or 3) to assign
3. **Press RIGHT arrow** immediately to next territory
4. Review all 39 territories in 10-15 minutes!

### Quick Decisions:
- If suggestion looks good Ã¢â€ â€™ Accept it
- If territory seems important Ã¢â€ â€™ Upgrade to next tier
- If territory seems weak Ã¢â€ â€™ Downgrade to lower tier

---

## Ã°Å¸â€œÂ Output

**File created**: `economic_data.json`

**Format**:
```json
{
  "Orlais": 3,
  "Amennia": 3,
  "The Comet": 1,
  "Vense": 2
}
```

Simple! Just territory name Ã¢â€ â€™ tier number.

---

## Ã¢Å“â€¦ After Completion

Once you've assigned all territories:

1. **economic_data.json** will be in your project directory
2. This file will be loaded by the main game
3. Each territory will generate gold per turn based on its tier
4. Income will be displayed in territory tooltips

---

## Ã°Å¸Å½Â® Strategic Impact

### High-Value Territories Become:
- Ã°Å¸Å½Â¯ **Priority conquest targets**
- Ã°Å¸â€ºÂ¡Ã¯Â¸Â **Worth defending heavily**
- Ã°Å¸â€™Âª **Economic power bases**
- Ã¢Å¡â€Ã¯Â¸Â **Hotly contested**

### Low-Value Territories:
- Ã°Å¸â€œÂ **Strategic buffers**
- Ã°Å¸Å¡Â¶ **Stepping stones**
- Ã°Å¸â€™Â¤ **Less contested**
- Ã°Å¸â€”ÂºÃ¯Â¸Â **Expansion filler**

This creates **natural strategic geography**!

---

## Ã°Å¸â€™Â¡ Pro Tips

### For Balanced Gameplay:
- **Spread Tier 3** territories across the map (not clustered)
- **Give each player access** to high-value territories
- **Remote corners** should be lower tier (rewards expansion)
- **Central territories** higher tier (rewards control)

### For Different Playstyles:
- **Aggressive players**: Fight for Tier 3 territories
- **Economic players**: Control many Tier 2 territories
- **Defensive players**: Fortify high-income regions

---

## Ã°Å¸â€Â§ Adjustment Later

Can't decide now? That's fine!

- Tool saves progress automatically
- Run it again anytime to adjust
- Economic balance can be tweaked after testing
- Easy to rebalance during development

---

## Ã°Å¸Å¡â‚¬ What's Next?

After assigning economic tiers:

### Phase 1: Implement Income System
1. Load economic_data.json in game
2. Calculate income per territory
3. Collect gold at turn end
4. Display in UI

### Phase 2: Show Income Info
5. Display income in territory tooltips
6. Show total income in player panel
7. Income messages when collecting gold

### Phase 3: Building System
8. Use gold to construct buildings
9. Buildings boost income further
10. Complete economic loop!

---

**Ready to assign economic power? Run `python economic_tool.py` and shape the economic geography of your world!** Ã°Å¸â€™Â°Ã°Å¸â€”ÂºÃ¯Â¸Â

**Time estimate**: 10-15 minutes to assign all 39 territories
