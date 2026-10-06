# Avareon War - Quick Reference

**Purpose:** Quick lookup for common information

---

## 🎮 Game Controls

**Mouse:**
- Left Click: Select/Order
- Right Click: Deselect
- Mouse Wheel: Zoom
- Middle Drag: Pan Camera

**Army unit selection (bottom UI icon strip):**
- Left Click a unit icon: select just that unit
- CTRL + Left Click: add/remove that unit from the selection
- **Right Click a unit icon: context menu** - Select / Add to Group /
  Remove from Group / Cancel (mouse-only alternative to CTRL+click)
- Right Click a destination territory: order the selected units there

**Keyboard:**
- Arrow Keys: Pan Camera
- +/-: Zoom
- Space: End Turn
- Esc: Cancel/Close
- C: Chat
- M: Menu

---

## 📊 Game Stats

**Map:** 57 territories
**Players:** 1-8
**Building Types:** 6
**Unit Types:** 5
**Starting Gold:** 100
**Turn Structure:** 4 phases

---

## 🌍 Territory Income Tiers

| Tier | Income/turn | Count | Examples |
|------|-------------|-------|----------|
| 1 | 10g | 25 | Ahara, Ajuna, Anodia, Sstep... |
| 2 | 15g | 19 | Aelatania, Carnae, Conda... |
| 3 | 20g | 13 | Courtieux, Duchy of Daurels, Free Cities... |

Total map income: 795g/turn (~199g/player with 4 players)

---

## 🏗️ Building Quick Reference

| Building | Cost | Turns | Effect |
|----------|------|-------|--------|
| Farm | 30g | 1 | +10 income/turn |
| Mine | 40g | 1 | +15 income/turn |
| Barracks | 50g | 1 | Enable recruitment |
| Keep | 100g | 2 | +2 defense armies |
| Square | 60g | 1 | 1.5× income multiplier |
| Training Grounds | 50g | 1 | +15 XP/turn to units |

---

## 💰 Taxation Levels

| Level | Rate | Effect |
|-------|------|--------|
| 0 | 0% | No taxation (default) |
| 1 | 25% | Moderate gold loss |
| 2 | 50% | High gold loss |
| 3 | 75% | Very high gold loss |
| 4 | 100% | All leftover gold removed |

**When Applied:** End of turn, BEFORE income collection
**Configured:** Game setup only (cannot change mid-game)
**Strategy:** Encourages spending resources each turn

---

## 🤝 Gold Transfer Caps

| Setting | Per-recipient cap | Notes |
|---------|-------------------|-------|
| Disabled | — | Feature off (default; always forced in campaigns) |
| Enabled (25%) | `floor(0.25 × gold)` | 25% of sender's current gold |
| Enabled (50%) | `floor(0.50 × gold)` | 50% of sender's current gold |
| Enabled (75%) | `floor(0.75 × gold)` | 75% of sender's current gold |
| Enabled (100%) | `floor(1.00 × gold)` | All of sender's current gold |

**Rules at a glance:**
- One transfer per (sender → recipient) pair per turn/round
- Humans only; Planning phase only; allies only
- Input field auto-clamps to cap (max 7 digits typed)
- Configured in setup Additional Options, not changeable mid-game

---

## 🏆 Territorial Bonus Reference

**57 territories grant bonuses. Each territory has ONE bonus. Bonuses stack globally.**

| Bonus Type | Value | Applies To | Count |
|------------|-------|------------|-------|
| Income Bonus | +3% | Total income | TBD (~6-7 territories) |
| Tech Cost | -5% | Technology research | TBD (~6-7 territories) |
| Unit Cost | -5% | Unit training (S/A/P/C/Captain) | TBD (~6-7 territories) |
| Hero Cost | -3% | Hero recruitment | TBD (~6-7 territories) |
| Pikeman Strength | +10% | Pikeman combat | TBD (~6-7 territories) |
| Archer Strength | +10% | Archer combat | TBD (~6-7 territories) |
| Swordsman Strength | +10% | Swordsman combat | TBD (~6-7 territories) |
| Cavalry Strength | +10% | Cavalry combat | TBD (~6-7 territories) |
| Building Cost | -15% | All buildings | TBD (~6-7 territories) |

**Note:** Bonus distribution counts to be finalized after using Bonus_Tool.py to assign all 57 territories.

**Stacking Examples:**
- Own 2 income territories → +6% total income
- Own 3 tech territories → -15% research costs
- Own 4 archer territories → +40% archer strength

**Notes:**
- Bonuses update automatically when conquering/losing territories
- Cost bonuses have 1 gold minimum (can't go below 1g)
- Strength bonuses apply to base strength before multipliers
- Pre-configured in `territory_bonuses.json`

---

## ⚔️ Unit Quick Reference

| Unit | Cost | Strength | Counters | Countered By |
|------|------|----------|----------|--------------|
| Swordsman | 25g | 1.0 | Pikeman | Archer |
| Archer | 20g | 1.0 | Swordsman | Cavalry |
| Pikeman | 30g | 1.0 | Cavalry | Swordsman |
| Cavalry | 40g | 1.0 | Archer | Pikeman |
| Captain | 75g (50g w/ Heroic Fortitude) | 0.25 | None | None |

Counter advantage: 2.0× effective strength (countered: 0.5×). Training: 1 turn per unit.

**Captain (Support Unit):** +12% strength to all other units in army (non-stacking). Enables 2-hop movement to allied territories through an allied intermediate territory. Cannot attack across 2 territories. Keyboard shortcut: T.

---

## 🎖️ Veterancy Quick Reference

**XP Thresholds:**

| Level | XP Needed | Cumulative | Unit Strength Bonus | Building Income Bonus |
|-------|-----------|------------|--------------------|-----------------------|
| 1 | 30 | 30 | +15% | +10% |
| 2 | 45 | 75 | +30% | +20% |
| 3 | 50 | 125 | +45% | +30% |
| 4 | 55 | 180 | +60% | +40% |
| 5 | 60 | 240 | +75% | +50% |

**XP Sources:**

| Source | XP Amount | Notes |
|--------|-----------|-------|
| Battle kill | 10 + enemy_level | Per enemy killed, each survivor |
| Hero Keep destroy | +100 flat | When destroying Keep with Hero |
| Building passive | +20/turn | Farms/Mines only |

**Constants (game_state/__init__.py):**
- `LEVEL_XP_PER_LEVEL = [30, 45, 50, 55, 60]`
- `LEVEL_XP_CUMULATIVE = [30, 75, 125, 180, 240]`
- `MAX_LEVEL = 5`
- `UNIT_LEVEL_STRENGTH_BONUS = 0.15` (+15% per level)
- `BUILDING_LEVEL_INCOME_BONUS = 0.10` (+10% per level)
- `BUILDING_XP_PER_TURN = 20`
- `BATTLE_XP_PER_KILL = 10`
- `HERO_KEEP_DESTROY_XP = 100`

**Casualty Priority:** Level ASC → Counter Tier ASC (low-level die first)

---

## 🏆 Player Level System

**Persistence:** `config.json` via `settings_manager` (`player_xp`, `campaign_missions_xp_claimed`)

**Level Progression (XP per level):**

| Level Range | XP/Level | Cumulative at Tier End |
|-------------|----------|----------------------|
| 1-10 | 100 | 900 |
| 11-20 | 250 | 3,400 |
| 21-40 | 500 | 13,400 |
| 41-100 | 1,000 | 73,400 |
| 101-200 | 2,500 | 323,400 |
| 201-500 | 5,000 | 1,823,400 |
| 501-10000 | 10,000 | 96,823,400 |

Max level: 10,000.

**XP Per Action:**

| Action | XP |
|--------|-----|
| Train a unit | +2 |
| Build a building | +2 |
| Conquer neutral territory | +2 |
| Conquer enemy territory (no battle) | +4 |
| Conquer enemy territory (with battle) | +8 |
| Train a hero | +4 |
| Kill a hero | +10 |
| Use active hero ability | +2 |
| Research a technology | +4 |

**End-of-Game Bonuses:**

| Condition | XP |
|-----------|-----|
| Custom/MP defeat | +25 |
| Custom/MP victory | +50 |
| MP victory (enemy humans >= your humans) | +100 |
| Campaign first-time mission win | +100 |

**Eligibility:** Campaign always. Custom/MP only if >=1 enemy exists. No XP on premature quit.
**Halving:** All XP halved if player's team has more players than enemy team.

**Key Files:** `player_level.py` (logic), `settings_manager.py` (persistence), `main_menu.py` (profile UI), `recap_screen.py` (recap UI)

---

## 📖 Tale I: Lack of Funds Quick Reference

Book of Tales, map Azincournean Highlands (55 territories; income tiers 10/15/20g =
32/17/6 territories). Tuning constants: top of `tale_lack_of_funds.py`.

| Faction | Idx | Colour | Capital | Gold | AI | Territories | Starting armies |
|---------|-----|--------|---------|------|----|-------------|-----------------|
| Londic Empire (player) | 0 | Blue | Generax | 750 | — | 10 | Generax: 2 Pike, 1 Archer, 1 Sword, 1 Captain; +2 Sword, 2 Cav, 2 Archer scattered |
| Aelatanaic Tribes | 1 | Yellow | Leyana | 1500 | Medium | 14 | 1-2 random / territory |
| Heilonic Kingdoms | 2 | Green | Entaron | 2500 | Hard | 10 | 2-6 random / territory |
| Kingdom of Daurels | 3 | Red | Daurels | 2000 | Hard | 8 | 2-6 random / territory |
| Neutral | -1 | — | — | — | — | 13 | 1 random / territory |

**Buildings:** Green/Red every plot filled — 25% Mine, 25% Farm, 30% Barracks, 10% Training
Grounds, 10% Square, no Keeps. Player: Barracks (Generax), Square (Lires) + 4 Farms, 2 Mines.
Yellow: Barracks (Atoney, Leyana) + 4 Farms, 2 Mines.

**AI rules:** AIs never target each other · Green/Red never take neutral land and attack the
player only after an attack order against them · Yellow: no conquest turns 1-3, no training
turns 1-2 · AI pauses removed (`AI_DELAY_SCALE = 0.0`).

| Popularity | Value |
|------------|-------|
| Start / max | 100 |
| Drop per player turn (from turn 2) | 6, 11, 16, 21… (`DECAY_START` 6, `DECAY_STEP` +5) |
| Invest | +10 pop, drop resets to 6, cost 100g +10g per use |
| Revolt chance (rolled before the drop) | 2% per missing point (`REVOLT_CHANCE_PER_POINT`), max 1 territory/turn |
| Revolt eligibility | 10g lands < 100 · 15g lands ≤ 75 · 20g lands ≤ 50 · Generax never |

| Popularity | 94 | 83 | 75 | 67 | 50 |
|------------|----|----|----|----|----|
| Revolt chance | 12% | 34% | 50% | 66% | 100% |

**Transmissions** (`assets/sounds/transmissions/`): intro T1T1 (8s), T1T2 (7s), T1T3 (6s) ·
revolt T1Revolt (3s) · victory T1TWin (7s) · defeat T1TLoss (4s).
**Achievement:** `campaign_tale_1` "Lack of Funds" (stat `campaign_tale_1_completed`, no reward).

---

## 📖 Tale II: Final Breaths Quick Reference

Book of Tales, Avareon geometry + Campaign Mission 3 territories/background. Tuning
constants: top of `tale_final_breaths.py`. Hold Lunedale + Free Cities for `HOLD_TURNS` (15).

| Faction | Idx | Colour | Gold | AI | Territories | Notes |
|---------|-----|--------|------|----|-------------|-------|
| Zjoal Empire (player) | 0 | Blue | 200 | — | 17 (79 units) | 100% taxation (`PLAYER_TAXATION_LEVEL` 4), 15 techs pre-researched |
| Kerunian Empire | 1 | Red | 7000 | Hard | 13 (88 units) | command limit 200 (`RED_COMMAND_LIMIT`) |
| Nordian Rebels | 2 | Yellow | 0 | never acts | 0 | gains land only by rebellion |
| Neutral | -1 | — | — | — | 5 (empty) | Zjoal Islands, Leimarch, Liadnon, Ahtep, Anodia |

**Plots:** Keeps — Lunedale (Castle), Affrancian Uplands, March of Auverne, Carnae. Rest:
Zjoal 20 Barracks / 3 Mine / 3 Farm / 1 empty; Kerunian 14 Barracks / 2 Mine / 2 Farm / 1 Square.
**Armies:** 1 Captain each + random basics; 12 / 8 / 3 (Zjoal) / 5 (Kerunian).
**Zjoal techs:** `tech_1_0`-`1_6`, `tech_0_0`-`0_2`, `tech_2_0`-`2_4` (next: `tech_0_3`, `tech_2_5`).

| Rule | Value |
|------|-------|
| Kerunian cap per target per turn | `turn // 2 + ATTACK_CAP_BASE` (10) → T1 10, T10 15, T15 17 |
| Forced Kerunian attacks | `FORCED_ATTACK_TARGETS` 1/turn, objectives first, `FORCED_ATTACK_KEEP` 1 unit stays home |
| Rebellions | 1 on turns 2 and 4, then 1 every turn from turn 6 (12 total) |
| Never rebel | Lunedale, Free Cities, Damlére, Oucine |
| Kerunian reinforcements | off (`KERUNIAN_REINFORCEMENTS` (min, max) per territory per turn) |
| Heroes | nobody can train them |

**Achievement:** `campaign_tale_2` "Final Breaths" (stat `campaign_tale_2_completed`, no reward).
**Cutscenes:** `tale_2_intro` / `tale_2_outro` (optional).

---

## 🗺️ Terrain Effects

*Terrain system not yet implemented. Combat uses counter system and Keep bonus only.*

**Keep Bonus:** +2 effective armies for defender

---

## 🔄 Phase Flowchart

```
Planning Phase
    ↓
Give Orders
    ↓
Orders Phase
    ↓
Execute Orders
    ↓
Battles Phase
    ↓
Resolve Battles
    ↓
Income Phase
    ↓
Collect Income
    ↓
Next Turn
    ↓
(Repeat)
```

---

## 🌐 Multiplayer Quick Reference

**Network Configuration (network_config.py):**
| Setting | Value | Description |
|---------|-------|-------------|
| DEFAULT_PORT | 7777 | Server listen port |
| MAX_CLIENTS | 3 | Host + 3 = 4 players |
| CONNECTION_TIMEOUT | 15.0s | No response = disconnect |
| RECONNECTION_TIMEOUT | 60.0s | Window to reconnect (network_config.py; server.py uses 300s) |
| HEARTBEAT_INTERVAL | 5.0s | Ping frequency |

**Player Slots:**
| Slot | Index | Options |
|------|-------|---------|
| Host | 0 | Always Human |
| Slot 1 | 1 | Human / AI Easy/Med/Hard / Empty |
| Slot 2 | 2 | Human / AI Easy/Med/Hard / Empty |
| Slot 3 | 3 | Human / AI Easy/Med/Hard / Empty |

**Key Network Message Types:**
```python
# Lobby
LOBBY_STATE, LOBBY_JOIN, LOBBY_LEAVE, LOBBY_KICK
LOBBY_SLOT_UPDATE, LOBBY_COUNTDOWN, LOBBY_LAUNCH

# Reconnection
RECONNECT_REQUEST, RECONNECT_ACCEPT, RECONNECT_REJECT
PLAYER_DISCONNECT, AI_TAKEOVER

# Gameplay
MOVEMENT_ORDER, BUILDING_ORDER, TRAINING_ORDER
EXECUTE_ORDERS, BATTLE_RESOLVE, TURN_END

# Simultaneous
SIM_PLAYER_READY, SIM_ALL_READY, SIM_TIMER_UPDATE
SIM_BATTLE_RESULT, SIM_ALLIANCE_CHOICE, SIM_ROUND_COMPLETE
```

**Disconnect Behavior:**
| Event | Result |
|-------|--------|
| Client disconnect | AI takes over, game continues |
| Host disconnect | Game ends for all |
| Reconnect within 5 min | Resume control from AI |

**Common Network Methods:**
```python
# Check multiplayer mode
if self.multiplayer_mode:
    # Network code here

# Check if host
if self.local_player_index == 0:
    # Host-only code

# Send to network
self._send_action_to_remote(MessageType.X, data)

# Server broadcast
server.broadcast_message(msg, exclude=player_idx)
server.send_to_player(player_idx, msg)
```

---

## 🔄 Simultaneous Mode Quick Reference

**Timer Settings:**
| Upgrade | Timer |
|---------|-------|
| Base | 60 seconds |
| + Master Planner I | 90 seconds |
| + Master Planner II | 120 seconds |

**Key Behaviors:**
- All players plan simultaneously
- Orders hidden until execution
- Trained units: spawn with "Moved" status (can't move that turn)
- Defensive battles: original owner keeps territory
- Alliance arrivals: biggest army clicks blue marker to assign owner

**Phase Flow:** Planning → Execution → Resolution → Next Round

---

## 📁 File Locations

**Main code:**
- main.py
- game_state/ (package: __init__.py, military.py, economy.py, buildings.py, heroes.py, garrison.py, victory.py, data_definitions.py)
- map_data.py

**Rendering:**
- rendering/map_renderer.py
- rendering/ui_renderer.py
- rendering/helpers.py

**Input:**
- input/mouse_handler.py
- input/keyboard_handler.py

**Book of Tales:**
- book_of_tales.py (picker, `SCENARIOS`)
- tale_lack_of_funds.py (Tale I)
- tale_final_breaths.py (Tale II)
- main.py `_TALE_REGISTRY` + `_run_registered_mission()`

**Data (root directory):**
- economic_data.json
- territory_polygons.json
- plots.json

**Tools (root directory, PascalCase):**
- Plot_Tool.py
- Economic_Tool.py
- Adjacency_Tool.py

---

## 🎯 Common Methods

**Game State (game_state/ package):**
```python
game_state.territory_owners[territory]       # Direct attribute access (no getter)
game_state.get_territory_total_armies(territory)  # Use this, NOT self.armies[]
game_state.calculate_player_income(player)    # economy.py
game_state.calculate_territory_income(territory, player)  # economy.py
game_state.create_movement_order(from_t, to_t, count, composition)  # military.py
game_state.start_construction(territory, plot_idx, building_type)   # buildings.py
game_state.calculate_army_effective_strength(composition, enemy_comp)  # military.py
game_state.execute_all_orders()               # military.py
```

**Main Game:**
```python
game.handle_map_click(pos)
game.handle_bottom_ui_click(pos)
game.advance_to_orders_phase()
game.resolve_battle(battle_index)
```

---

## 🐛 Debug Commands

**Run game:**
```bash
python main.py
```

**Run tools:**
```bash
python Plot_Tool.py
python Economic_Tool.py
```

**Clear cache:**
```bash
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

---

## 📝 Quick Code Snippets

**Add territory income:**
```python
income = game_state.calculate_player_income(player)
```

**Check if can build:**
```python
can_build = game_state.can_build_on_plot(territory, plot_id)
```

**Create movement order:**
```python
game_state.create_movement_order(from_terr, to_terr, army_count)
```

**Get army composition:**
```python
composition = game_state.get_territory_composition(territory)
# Returns: {'Swordsman': 5, 'Cavalry': 2, 'Archer': 0, 'Pikeman': 0}
```

---

## 🎨 Common Colors

**Players:**
```python
PLAYER_COLORS = {
    1: (200, 50, 50),    # Red
    2: (50, 50, 200),    # Blue
    3: (50, 200, 50),    # Green
    4: (200, 200, 50),   # Yellow
    5: (200, 50, 200),   # Magenta
    6: (50, 200, 200),   # Cyan
    7: (200, 120, 50),   # Orange
    8: (120, 50, 200),   # Purple
}
```

**UI Colors:**
```python
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED_TEXT_PRIMARY = (220, 90, 90)
RED_ACCENT_BRIGHT = (255, 70, 70)
```

---

## 📐 Layout Constants

**Dynamic (calculated):**
```python
WINDOW_WIDTH       # Screen width
WINDOW_HEIGHT      # Screen height
TOP_PANEL_HEIGHT   # Top panel
BOTTOM_UI_Y        # Bottom panel start
MAP_HEIGHT         # Map area height
```

**Static (constants.py):**
```python
MIN_ZOOM = 0.5
MAX_ZOOM = 2.0
CAMERA_SPEED = 10
EDGE_SCROLL_SPEED = 15
```

---

## 🔧 Common Fixes

**Game won't start:**
1. Check Python version (3.7+)
2. Install Pygame: `pip install pygame`
3. Check file paths
4. Clear Python cache

**UI not showing:**
1. Check screen resolution
2. Verify asset files exist
3. Check rendering order
4. Clear cache

**Click not working:**
1. Check mouse_handler priority
2. Verify rect stored
3. Check phase restrictions
4. Debug with prints

**State not updating:**
1. Check method called
2. Verify validation passes
3. Check correct phase
4. Look for early returns

---

## 📚 Doc Quick Links

- **README.md** - Project overview
- **ARCHITECTURE.md** - System design
- **CODE_GUIDE.md** - Living knowledge base (module-specific guidance)
- **GAME_MECHANICS.md** - Game rules
- **USER_STORIES_PROGRESS.md** - Feature status
- **DEVELOPMENT_GUIDE.md** - How to develop

---

## 🖥️ Display & Frame Pacing Settings

Stored in `config.json` via `settings_manager`. Both keys must exist in **`SETTING_TYPES`
and `defaults`** — a key missing from `defaults` is deleted from config.json on every load.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `vsync` | bool | `False` | Sync frames to the monitor. Opt-in (off keeps pre-2026-09 behaviour) |
| `fps_limit` | int | `0` | Manual FPS cap; `0` = no manual cap |
| `fullscreen` | bool | `True` | Fullscreen mode |
| `resolution` | list | detected | Window resolution |

**FPS limit options** (`config/constants.py FPS_LIMIT_OPTIONS`): `0 (Unlimited), 60, 80,
120, 144, 165, 240`. Frame cap priority: manual limit → VSync (safety-capped 240) → `FPS`
(80) → `UNFOCUSED_FPS` (10) when the window loses focus.

**Creating the window:** always `display_utils.set_display_mode(size, fullscreen, vsync)`,
never `pygame.display.set_mode()` directly. VSync requires `pygame.SCALED` *and* a freshly
initialised display; it is silently lost by any later `set_mode()`, and the achieved state
cannot be read back from `get_flags()` (tracked as `game.vsync_active`).

---

## 🎯 Most Important Files

For Claude Code, read these first:
1. README.md
2. ARCHITECTURE.md
3. CODE_GUIDE.md
4. GAME_MECHANICS.md

For quick answers:
1. This file (QUICK_REFERENCE.md)
2. CODE_GUIDE.md

---

**Last Updated:** September 20, 2026
