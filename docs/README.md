# Avareon War - Project Documentation

**Version:** Phase 7 Complete (February 2026)
**Status:** Production-Ready
**Main File:** `main.py` (~13,000 lines)

---

## Documentation Index

### **Core Documentation:**

1. **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design patterns
2. **[CODE_GUIDE.md](CODE_GUIDE.md)** - Module-specific guidance (living knowledge base)
3. **[GAME_MECHANICS.md](GAME_MECHANICS.md)** - How the game works
4. **[USER_STORIES_PROGRESS.md](USER_STORIES_PROGRESS.md)** - Feature completion status
5. **[DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md)** - Guide for developers/AI assistants
6. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick lookup for common tasks
7. **[TESTING_PLAN_MULTIPLAYER_FIXES.md](TESTING_PLAN_MULTIPLAYER_FIXES.md)** - Multiplayer testing plan

---

## What is Avareon War?

**Avareon War** is a turn-based strategy game built with Pygame featuring:

- **Territory control** - Conquer 57 territories on a fantasy map
- **Army management** - 4 unit types with counter system (Swordsman, Archer, Pikeman, Cavalry)
- **Building system** - 5 building types (Farm, Mine, Barracks, Keep/Castle, Square)
- **Hero system** - 10 unique heroes with 3 abilities each
- **Technology tree** - 21 technologies across 3 columns
- **Economic gameplay** - Gold, income, taxation, territorial bonuses
- **Battle system** - Deterministic combat with counters and veterancy
- **Campaign mode** - 4 missions with cutscenes
- **Multiplayer** - 2-4 players with teams, reconnection, simultaneous turns
- **AI opponents** - 3 difficulty levels (Easy, Medium, Hard)
- **Achievement system** - Stat tracking and persistence

---

## Project Structure

```
AvareonWar/
├── main.py                          # Main game class (~13,000 lines)
├── game_state/                      # Game logic package (~8,600 lines, 8 files)
│   ├── __init__.py                 # GameState class, turn mgmt, diplomacy
│   ├── data_definitions.py         # BUILDING_TYPES, HERO_TYPES, technologies
│   ├── military.py                 # Orders, battles, movement
│   ├── economy.py                  # Income, costs, taxation
│   ├── buildings.py                # Construction, training, upgrades
│   ├── heroes.py                   # Hero training, abilities
│   ├── garrison.py                 # Multi-garrison system
│   └── victory.py                  # Victory checks, elimination
├── map_data.py                      # 57 territory definitions
├── ai_*.py                          # AI system (5 files, ~4,500 lines)
├── campaign_mission_*.py            # Campaign missions (6 files)
├── rendering/                       # Map and UI rendering (~6,800 lines)
├── input/                           # Mouse, keyboard, camera handlers
├── network/                         # Multiplayer (server, client, lobby)
├── simultaneous/                    # Simultaneous turn mode (7 files)
├── ui/                              # UI scaling and 12 effect modules
├── config/                          # Constants and font manager
├── assets/                          # Images, fonts, sounds (380+ files)
├── docs/                            # Documentation (8 markdown files)
├── tests/                           # Unit tests (pytest)
└── tools/                           # Development utilities
```

---

## Quick Start

### **For Claude Code / AI Assistants:**

1. **Read this README first** - Understand the project
2. **Check [USER_STORIES_PROGRESS.md](USER_STORIES_PROGRESS.md)** - See what's done/needed
3. **Review [ARCHITECTURE.md](ARCHITECTURE.md)** - Understand the design
4. **Consult [CODE_GUIDE.md](CODE_GUIDE.md)** - Module-specific guidance
5. **Use [QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick lookups

### **For Human Developers:**

```bash
cd AvareonWar
pip install pygame
python main.py

# Development tools (PascalCase, in root)
python Plot_Tool.py          # Edit building plots
python Economic_Tool.py      # Edit territory economies
python Polygon_Tool.py       # Edit territory polygons
python Cutscene_Tool.py      # Edit campaign cutscenes
```

---

## Project Stats

### **Code Size (~70,000 lines total):**
- **Main Game:** ~13,000 lines (main.py)
- **Game State:** ~8,600 lines (8-file package)
- **Rendering:** ~6,800 lines (4 modules)
- **AI System:** ~4,500 lines (5 modules)
- **Simultaneous Mode:** ~3,400 lines (7 files)
- **Network:** ~4,900 lines (8 files)

### **Game Content:**
- **Territories:** 57
- **Building Types:** 5 (Farm, Mine, Barracks, Keep/Castle, Square)
- **Unit Types:** 4 (Swordsman, Archer, Pikeman, Cavalry)
- **Heroes:** 10 (7 trainable + 3 campaign-only)
- **Technologies:** 21 (3 columns x 7 rows)
- **Campaign Missions:** 4 (+ 2 placeholder stubs)
- **Players:** Up to 4 (Human or AI)

---

## Key Concepts

### **Game Loop:**
```
Planning Phase -> Orders Phase -> Battles Phase -> Income Phase -> Next Turn
```

### **Core Systems:**
- **Territory System** - 57 territories with ownership, armies, bonuses
- **Garrison System** - Multi-garrison army management (authoritative over legacy counters)
- **Building System** - 5 types, construction queue, XP/veterancy for Farms/Mines
- **Army System** - 4 unit types with rock-paper-scissors counter system
- **Battle System** - Deterministic combat (2.0x counter advantage, veterancy, Keep bonus)
- **Hero System** - 10 heroes with active/passive abilities
- **Technology Tree** - 21 techs across economy, military, and utility columns
- **Economic System** - Base income + buildings + Square multipliers + territorial bonuses

---

## For Claude Code

### **Important Patterns:**

**State Management:**
- All game logic in `game_state/` package (6 mixins + data definitions)
- UI only reads state, doesn't modify
- Use `get_territory_total_armies()` not `self.armies[]`

**Rendering:**
- Map rendering: `rendering/map_renderer.py`
- UI overlays: `rendering/ui_renderer.py`
- Never create `pygame.Surface` per-frame — cache everything

**Input:**
- Mouse: `input/mouse_handler.py`
- Keyboard: `input/keyboard_handler.py`
- Camera: `input/camera_handler.py`

### **Common Tasks:**

**Adding a new building type:**
-> See CODE_GUIDE.md "Building System" section

**Adding a new unit type:**
-> See CODE_GUIDE.md "Army/Combat System" section

**Modifying UI:**
-> See CODE_GUIDE.md "Rendering System" section

---

**Last Updated:** February 27, 2026
**Game Version:** Phase 7 Complete
