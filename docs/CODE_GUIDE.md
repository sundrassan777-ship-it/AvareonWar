# Code Modification Guide

**Living knowledge base for developers working on AvareonWar**

This guide provides module-specific guidance on when and how to modify different parts of the codebase. Use this as your primary reference when implementing features, fixing bugs, or making balance changes.

---

## Table of Contents

1. [Logging System](#logging-system) - Structured logging
2. [game_state package](#game_state-package) - Core game logic
3. [main.py](#mainpy) - Main game loop and UI
   - [Battle Reports](#battle-reports) - Defender-side battle summaries
4. [AI System](#ai-system) - AI decision making
5. [Network System](#network-system) - Multiplayer
6. [Simultaneous Mode](#simultaneous-mode) - Simultaneous turn mode
7. [Rendering System](#rendering-system) - Map and UI rendering
8. [Input System](#input-system) - Mouse, keyboard, camera
9. [Sound System](#sound-system) - Audio and sound effects
10. [Campaign System](#campaign-system) - Campaign missions and scripting
11. [map_data.py](#map_datapy) - Territory data
12. [Quick Navigation](#quick-navigation) - Where to find things
13. [Achievement System](#achievement-system) - Achievements, rewards, tracking
14. [Recap Screen](#recap-screen) - Post-game statistics
15. [Loading Screen](#loading-screen) - Deferred asset loading + multiplayer sync
16. [Replay System](#replay-system) - Recording, viewer, browser
17. [Campaign Save System](#campaign-save-system) - Save/load campaign progress
18. [Browser Screens](#browser-screens-saved-games--replays) - Saved Games + Replays UI
19. [Book of Tales Screen](#book-of-tales-screen) - Tale picker, description markup, launch registry
20. [Tale I: Lack of Funds](#tale-i-lack-of-funds-tale_lack_of_fundspy) - Built-in-AI tale, Popularity
21. [Tale II: Final Breaths](#tale-ii-final-breaths-tale_final_breathspy) - Hold-out tale, attack cap, forced attacks, Rebels

---

## Logging System

**What it does:** Structured logging with file+console output, log rotation
**File:** `utils/logger.py` (120 lines)
**Used by:** All modules (replaces `print()` throughout codebase)

### Usage

```python
from utils.logger import get_logger
logger = get_logger(__name__)

logger.debug("Detailed info for development")
logger.info("Normal operational messages")
logger.warning("Something unexpected but recoverable")
logger.error("Something failed")
```

### Setup

Called once in `main.py` at startup:
```python
from utils.logger import setup_logging
setup_logging()  # console=INFO, file=DEBUG, rotation=5MB x 3
```

### Key Rules

- **Never use `print()` for game output** — always use `logger.info()` / `logger.debug()` / etc.
- Console shows INFO+ by default; log file captures DEBUG+ for diagnostics
- Log files: `logs/avareonwar.log` (5MB rotation, 3 backups)
- Windows console: UTF-8 encoding forced to prevent mojibake on arrow chars (→)
- Runtime level change: `set_level(logging.DEBUG)` for debug toggle

### When to Modify

- **Add new log category:** No action needed — just use `get_logger(__name__)` in your module
- **Change default levels:** Edit `DEFAULT_CONSOLE_LEVEL` / `DEFAULT_FILE_LEVEL` in `utils/logger.py`
- **Suppress noisy library:** Add `logging.getLogger('library').setLevel(logging.WARNING)` in `setup_logging()`

### Sync Logger (`sync_logger.py`)

**What it does:** Multiplayer-only per-participant logging for state sync verification and desync diagnosis.
**Output:** `Logs/sync/{game_id}_P{idx}_{host|client}_{date}.json`

**Records:**
- All gameplay actions (orders, battles, turn ends) with timestamps and source (local/remote)
- Comprehensive state snapshots at every turn boundary
- Checksum comparisons between host and clients
- Field-level desync diffs (computed by host, sent to client via DESYNC_DIFF message)

**When to modify:**
- **Add new action type to log:** Add to `LOGGED_ACTION_TYPES` frozenset in `sync_logger.py`
- **Add new state field to snapshots:** Update `build_state_detail()` in `sync_logger.py` AND `calculate_state_checksum()` in `game_state/__init__.py`
- **Change desync detection flow:** `main.py` STATE_CHECKSUM handler → STATE_DETAIL_REQUEST/RESPONSE/DESYNC_DIFF handlers
- **Change log output format:** `finalize_and_save()` in `sync_logger.py`

---

## game_state package

**What it does:** Core game logic - territories, armies, buildings, economy, battles
**Size:** ~8,605 lines across 8 files
**Location:** `game_state/` package (decomposed from former monolithic `game_state.py`)
**Dependencies:** map_data.py (territory definitions)
**Used by:** main.py (UI), ai_player.py (AI), network/protocol.py (sync)

**Package files:**
| File | Purpose | Lines (approx) |
|------|---------|----------------|
| `game_state/__init__.py` | GameState class, UNIT_TYPES, turn mgmt, coordinates, chat, diplomacy | ~1,064 |
| `game_state/data_definitions.py` | BUILDING_TYPES, HERO_TYPES, BONUS_TYPES, build_technologies() | ~683 |
| `game_state/military.py` | Orders, battles, movement, casualties | ~3,162 |
| `game_state/economy.py` | Income, costs, taxation, bonuses | ~390 |
| `game_state/buildings.py` | Construction, training, upgrades, tech | ~1,070 |
| `game_state/heroes.py` | Hero training, abilities, queries | ~1,467 |
| `game_state/garrison.py` | Multi-garrison system, legacy sync | ~796 |
| `game_state/victory.py` | Victory checks, elimination | ~284 |

### Constants

**UNIT_TYPES** — `game_state/__init__.py` (line ~204)
```python
MAX_ARMIES_PER_TERRITORY = 15

UNIT_TYPES = {
    'Swordsman': {'cost': 25, 'counters': 'Pikeman', 'countered_by': 'Archer'},
    'Archer': {'cost': 20, 'counters': 'Swordsman', 'countered_by': 'Cavalry'},
    'Pikeman': {'cost': 30, 'counters': 'Cavalry', 'countered_by': 'Swordsman'},
    'Cavalry': {'cost': 40, 'counters': 'Archer', 'countered_by': 'Pikeman'}
}
```

**BUILDING_TYPES** — `game_state/data_definitions.py` (line ~26)
```python
building_types = {
    'Farm': {'cost': 30, 'effect': 'income', 'value': 10, 'time': 1},
    'Mine': {'cost': 40, 'effect': 'income', 'value': 15, 'time': 1},
    'Barracks': {'cost': 50, 'effect': 'recruitment', 'value': True, 'time': 1},
    'Keep': {'cost': 100, 'effect': 'defense', 'value': 2, 'time': 2},
    'Square': {'cost': 60, 'effect': 'multiplier', 'value': 1.5, 'time': 1},
    'Training Grounds': {'cost': 50, 'effect': 'training', 'value': 15, 'time': 1}
}
```

### When to Modify

#### ✅ Add New Unit Type

**Steps:**
1. Add entry to `UNIT_TYPES` dict in `game_state/__init__.py` (line ~204)
   ```python
   'YourUnit': {
       'cost': 35,
       'letter': 'Y',
       'name': 'YourUnit',
       'strength': 1.0,              # Base strength multiplier (Captain = 0.25)
       'counters': 'SomeUnit',       # Who this unit beats (None for no counters)
       'countered_by': 'OtherUnit',  # Who beats this unit (None for no counters)
   }
   ```
2. Add icon to `assets/mapicons/YourUnitIcon.png`
3. Update counter chain to maintain balance (must be circular for combat units)
4. Update ALL hardcoded unit type lists (grep for `'Swordsman', 'Archer', 'Pikeman', 'Cavalry'`):
   - `main.py`: icon loading, training UI, composition display, tooltips, click detection
   - `ai_military.py`: COUNTERS, COUNTERED_BY, composition dicts, unit_costs
   - `simultaneous/sim_phase_manager.py`: counter dict
   - `rendering/map_renderer.py`: training icons
   - `input/keyboard_handler.py`: training shortcuts
5. Add stat tracking: `player_stats` init, `_unit_stat_map` in `buildings.py`, `game_logger.py`
6. Test training in `start_training()` method (`game_state/buildings.py`)
7. Test combat in `resolve_battle()` method (`game_state/military.py`)
8. Update `GAME_MECHANICS.md`, `QUICK_REFERENCE.md`, `CHANGELOG.md`

**Reference: Captain unit (support type)** — See `tests/test_captain.py` for comprehensive examples.
Captain uses `strength: 0.25`, `counters: None`, `army_bonus: 0.20`, and has extended 2-hop movement via `army_has_captain()` / `find_2hop_path()` in `military.py`.

**Methods to check:**
- `start_training()` — Validates unit type, deducts cost (`game_state/buildings.py`)
- `resolve_battle()` — Uses counter relationships (`game_state/military.py`)
- `calculate_army_effective_strength()` — Computes unit matchups, applies `strength` multiplier and Captain army bonus (`game_state/military.py`)

#### ✅ Add New Building Type

**Steps:**
1. Add entry to `BUILDING_TYPES` dict in `game_state/data_definitions.py` (line ~26)
   ```python
   'YourBuilding': {
       'cost': 50,
       'letter': 'Y',
       'effect': 'income',  # or 'defense', 'recruitment', 'multiplier'
       'value': 20,         # income amount or bonus value
       'time': 1            # turns to build
   }
   ```
2. Add icon to `assets/mapicons/YourBuilding.png`
3. Update `calculate_player_income()` / `calculate_territory_income()` if `effect: 'income'` (`game_state/economy.py`)
4. Update `apply_combat_modifiers()` if affects combat
5. Test building construction in `start_construction()` method (`game_state/buildings.py`)
6. Update `GAME_MECHANICS.md` and `QUICK_REFERENCE.md`

**Methods to check:**
- `start_construction()` — Validates building, deducts cost, starts construction (`game_state/buildings.py`)
- `calculate_player_income()` / `calculate_territory_income()` — Processes income effects (`game_state/economy.py`)
- `get_effective_building_cost()` — Applies tech discounts

#### ✅ Change Game Balance

**Unit costs:**
- Modify `UNIT_TYPES[unit_name]['cost']`
- Test with AI at all difficulty levels
- Update `QUICK_REFERENCE.md`

**Building costs:**
- Modify `building_types[building_name]['cost']`
- Test economy with AI
- Update `QUICK_REFERENCE.md`

**Income values:**
- Building income: `building_types[name]['value']`
- Territory base income: Edit `economic_data.json`
- Town Square multiplier: `building_types['Square']['value']`
- Multiple Squares in same territory compound: `multiplier *= value` (not `= value`)

**Army limit:**
- Change `MAX_ARMIES_PER_TERRITORY` (currently 15)
- Affects spam prevention and territory capacity
- Order validation uses `_get_effective_capacity()` which accounts for outgoing orders (armies leaving the destination)
- Cancelling an outgoing order triggers `_revalidate_incoming_orders()` which auto-cancels excess incoming orders (last-added first) with red shake animation
- Safety net: `_enforce_army_limits()` clamps all per-player garrisons after arrivals and battle resolution
- Called from both `game_state/military.py` (sequential) and `sim_phase_manager.py` (simultaneous)

#### ✅ Modify Combat Mechanics

**Battle resolution:** `game_state/military.py` (line ~2008)
```python
def resolve_battle(self, battle):
    # Modify combat calculation here
```

**Counter multipliers:**
- Currently: Counter = 2.0x, Countered = 0.5x, Neutral = 1x
- Change in `calculate_army_effective_strength()` method (`game_state/military.py`)
- Update `GAME_MECHANICS.md` with new values

**Keep defense bonus:**
- Currently: +2 effective units for defender
- Change in `resolve_battle()` where Keep bonus applied (`game_state/military.py`)
- ⚠️ In `_process_arrivals()` the bonus is added to `player_armies[owner]` but is **not
  units**: it travels as `battle.keep_bonus`. The two places that fabricate default
  Swordsmen for a participant without units (the team-composition fallback and the
  attacker-garrison loop) must exclude it. When they didn't, a Keep defending alone showed
  "2 Swordsman" on the pre-battle screen with a wrong strength (fixed 2026-09-25).

**Casualty calculation:**
- Modify casualty formula in `_apply_battle_casualties_simple()` (`game_state/military.py`, line ~1657)
- Formula: `casualties = loser_count * (loser_strength / winner_strength)`, min 1
- Same formula applied in `_resolve_keep_battle()` Phase 1 (`game_state/military.py`, line ~1424)
- Keep Phase 2 uses fixed numerical comparison (unchanged)

#### ✅ Modify Veterancy/Experience System

**Key constants** (in `game_state/__init__.py`):
- `LEVEL_XP_PER_LEVEL`, `LEVEL_XP_CUMULATIVE`, `MAX_LEVEL`
- `UNIT_LEVEL_STRENGTH_BONUS` (0.15 = +15% per level)
- `BUILDING_LEVEL_INCOME_BONUS` (0.10 = +10% per level)
- `BUILDING_XP_PER_TURN` (20), `BATTLE_XP_PER_KILL` (10), `HERO_KEEP_DESTROY_XP` (100)

**Unit XP/Level data model:**
- Every unit dict has `'xp': 0, 'level': 0` — ~25 creation points across the game_state package
- `award_unit_xp(unit, amount)` — adds XP and auto-levels up
- `get_unit_avg_levels(units)` — returns `{unit_type: avg_level}` for strength calc

**Strength calculation:**
- `calculate_army_effective_strength(composition, enemy_comp, unit_avg_levels=None)`
- Level bonus: `1.0 + avg_level * UNIT_LEVEL_STRENGTH_BONUS` per unit type
- Propagated through `_calculate_battle_strengths()` and `_resolve_keep_battle()`
- Also updated in `ui/effects/battle_interface.py` display

**Casualty priority:**
- `apply_casualties_with_priority()` — sorts all units by `(level ASC, counter_tier ASC)`
- Level overrides counter type: a Level 0 advantaged unit dies before a Level 1 countered unit
- `apply_multi_garrison_casualties()` — allies die first, owner last (within each: level-based)

**Battle XP awards** (in `_update_battle_results()`):
- Only winners get XP. Formula: `enemies_killed * 10 + enemy_level_bonus + (100 if hero_keep_destroyed)`
- `battle.enemy_level_xp_bonus` pre-computed in `_calculate_battle_strengths()`
- `battle._keep_had_hero` checked before `destroy_buildings()` clears heroes

**Building XP:**
- `self.building_xp = {territory: {plot_index: {'xp': int, 'level': int}}}`
- `award_building_xp(territory, plot_index, amount)` — adds XP, auto-levels
- `_tick_building_xp()` — called from `_complete_turn_announcement()`, +20/turn to Farms/Mines
- Income bonus in `calculate_player_income()` and `calculate_territory_income()`
- Cleanup in `destroy_buildings()`, `destroy_building()`, `destroy_all_buildings()`

**Animation pipeline (XP preservation):**
- `ArmyAnimation.units` — stores actual unit dicts extracted from garrison
- `execute_all_orders()` extracts units into `extracted_units` list → passed to animation
- `_process_arrivals()` aggregates `moving_units` dict and reuses actual unit dicts
- `sim_phase_manager.py` also carries units through animation

**UI display** (main.py):
- Army composition grid: XP bars + level shields in `draw_army_composition_ui()`
- Building info: XP bars + shields in `draw_territory_info_panel()`
- Tooltips: `draw_button_tooltip()` handles 4-tuple `(type, status, level, xp)` for units
- Asset: `level_shield_icon` loaded from `assets/upgrades/LevelDisplay.png`

#### ✅ Add New Technology

**Steps:**
1. Find technology tree data structure (search for `player_technologies`)
2. Add new tech with effect type:
   ```python
   {
       'name': 'Your Tech',
       'cost': 100,
       'prerequisites': ['Other Tech'],
       'effect_type': 'unit_cost_reduction',  # or 'income_boost', etc.
       'effect_value': 15  # percentage or absolute value
   }
   ```
3. Implement effect in appropriate method:
   - Cost reduction: `get_effective_cost()` (`game_state/economy.py`, line ~23)
   - Income boost: `calculate_player_income()` / `calculate_territory_income()` (`game_state/economy.py`)
   - Combat bonus: `resolve_battle()` or `calculate_army_effective_strength()` (`game_state/military.py`)
4. Add tech icon to `assets/upgrades/`
5. Test research cost and effect
6. Update `GAME_MECHANICS.md`

**Existing tech effects:**
- `player_royal_decree_discount` - Hero/Keep cost reduction
- `player_training_cost_discount` - Swordsman/Pikeman 20% off
- `player_cavalry_cost_discount` - Cavalry 25% off
- `player_farm_income_bonus` - Farmer Subsidies +50% farms
- `player_mine_income_bonus` - Mining Efficiency +50% mines
- `player_archer_keep_strength` - Battlement Archery bonus

#### ✅ Change Victory Conditions

**All three victory conditions are implemented:**

| Condition | Threshold | Team Behavior |
|-----------|-----------|---------------|
| Domination (45+) | 45 territories | Team counts aggregated |
| Capital Assault | Capture enemy capitals | Allies can't eliminate each other |
| Total Conquest | All 57 territories | Team counts aggregated |

**Methods in `game_state/victory.py`:**
- `check_victory()` - Main entry point; universal last-team-standing check runs first, then routes to specific condition
- `_check_last_team_standing()` - Universal check: if only 1 team has territories, that team wins (all modes)
- `_check_domination_victory()` - Aggregates team territory counts (45+ threshold)
- `_check_capital_assault_victory()` - Checks last team standing (Capital Assault specific)
- `_check_total_conquest_victory()` - Aggregates team territory counts (all territories)
- `eliminate_player()` - Called when capital captured (neutralizes territories)
- `eliminate_player_disconnect()` - Called on disconnect timeout (distributes territories to allies or neutralizes)

**`check_victory()` also marks players with 0 territories as eliminated** (adds to `game_state.eliminated_players`). Eliminated players are skipped in turn order (`_advance_to_next_player`).

**When adding new territory ownership change paths**, always call `check_victory()` afterwards. See audit table in plan file for all existing paths.

**Team-based logic:**
```python
# Domination/Total Conquest aggregate by team:
if hasattr(self, 'player_teams') and self.player_teams:
    team_counts = {}  # team_id -> total territories
    for player_id, count in enumerate(territory_counts):
        team_id = self.player_teams[player_id]
        team_counts[team_id] = team_counts.get(team_id, 0) + count
    # Check if any team meets threshold
```

**Capital Assault ally protection:**
- All elimination paths include `are_allies()` check
- Prevents allies from eliminating each other when capturing capitals
- 5 code locations: 4 in sequential mode, 1 in sim_phase_manager.py

#### ✅ Victory/Defeat Cinematic (Custom & Multiplayer Games)

**Flow:** `phase='ended'` → wait for animations → fade to black → victory/defeat PNG → auto-recap

**State variables in main.py `Game.__init__`:**
- `victory_sequence_pending` - Waiting for animations to finish
- `victory_sequence_active` - Cinematic is playing
- `victory_phase` - Current animation phase: 'fade' | 'image_grow' | 'image_hold'

**Methods in main.py:**
- `_is_victory_for_local_player()` - Determines win/loss perspective (supports teams)
- `_all_animations_complete()` - Checks no animations/battles/UI pending
- `_start_victory_sequence()` - Loads image, initializes cinematic
- `_update_victory_sequence()` - Phase state machine (fade 0.5s → grow 0.3s → hold 5s)
- `_render_victory_sequence()` - Draws black overlay + scaled PNG

**Images:** `assets/victoryscrn.png`, `assets/defeatscrn.png`

**Input blocking:** Event loop blocks all input during `victory_sequence_active`
**Mouse handler:** `mouse_handler.py` line 86 guards `phase=='ended'` to allow battle clicks during pending state

**Campaign missions** have their own victory system (tutorial_mission hook) - the cinematic is skipped when a campaign mission is active.

#### ✅ Modify Economy

**Income calculation:** `calculate_player_income()` / `calculate_territory_income()` in `game_state/economy.py`
- Base income from `economic_data.json`
- Building bonuses from `building_types`
- Tech multipliers from research
- Town Square 1.5× multiplier (compounds: multiple Squares use `*=`)
- `calculate_player_territorial_bonuses()` is cached per player, invalidated via `invalidate_territorial_bonus_cache()` on ownership changes

**Taxation:** `apply_taxation()` in `game_state/economy.py`
- Applied at turn end BEFORE income collection
- Deducts percentage of leftover gold from previous turn
- 5 levels: 0% (no tax), 25%, 50%, 75%, 100%
- Configured in game setup (not changeable mid-game)
- `taxation_level` is clamped to valid `tax_rates` index range (bounds-safe)
- Modify tax_rates list to change percentages: `[0.0, 0.25, 0.5, 0.75, 1.0]`
- Called from `_advance_to_next_player()` (`game_state/__init__.py`, line ~696)
- Generates log message if tax > 0

**Training queue format:** `{territory: {barracks_plot_index: [(unit_type, turns_remaining, cost_paid), ...]}}`
- `cost_paid` stores the actual gold deducted at training start (for accurate cancel refunds)
- Legacy 2-tuple entries `(unit_type, turns)` are handled with fallback recalculation
- Use index access `entry[0]`, `entry[1]` — not destructuring — to survive format changes

**Research tracking format:** `{player_id: {'tech_id': str, 'turns_remaining': int, 'cost_paid': int}}`
- `cost_paid` stores actual gold deducted (for accurate cancel refunds)
- Legacy entries without `cost_paid` fall back to recalculation

**Starting resources:**
- Find `__init__` method
- Look for `player_gold` initialization
- Currently grants starting gold

#### ✅ Modify Gold Transfer (ally-to-ally gold sending)

**What it does:** Humans may send gold to allied players during the Planning phase. Setup picks a per-recipient cap (Disabled / 25% / 50% / 75% / 100% of sender's current gold). One transfer per (sender → recipient) pair per turn/round.

**Files involved:**
- `integrated_setup.py` — custom game dropdown in Additional Options overlay (`SetupConfig.gold_transfer`, `SetupScreen.overlay_gold_transfer`)
- `network/territory_selector.py` + `network/lobby.py` + `network/multiplayer_setup.py` — multiplayer lobby dropdown + sync
- `main.py` — `initialize_game()` sets `game_state.gold_transfer_pct`; `execute_gold_transfer()` applies locally then broadcasts; `_handle_remote_gold_transfer()` mirrors remote transfers
- `game_state/__init__.py` — `gold_transfer_pct`, `gold_transfers_this_turn` (cleared in `_advance_to_next_player`)
- `game_state/economy.py` — `can_transfer_gold()`, `get_transfer_cap()`, `transfer_gold()`
- `simultaneous/sim_state.py` — `gold_transfers_this_round` (cleared in `start_planning_phase`)
- `players_window.py` — the "Players" modal UI (table, input field, Send button, tooltips)
- `rendering/ui_renderer.py` — "Players" button in `draw_top_panel`
- `network_config.py`, `network/protocol.py`, `network/server.py` — `GOLD_TRANSFER` message type + factory + server relay
- `sync_logger.py` — `GOLD_TRANSFER` in `LOGGED_ACTION_TYPES`
- `save_manager.py` — serialize `gold_transfer_pct` + `gold_transfers_this_turn`

**Key rules/invariants:**
- Cap is floored to integer (`(gold * pct) // 100`)
- Transfer amount clamps to `[1, cap]` per keystroke and again at send time
- Campaigns force `gold_transfer_pct == 0` (campaign setup_config never sets the key, so the default applies)
- AI players never send — `can_transfer_gold` rejects AI senders
- Eliminated (defeated) vs Left (disconnected) get distinct tooltip wording
- Optimistic UI: sender deducts instantly, then broadcasts. Remote peers mirror without revalidating (since peer's turn view may lag).
- Transfers are recorded as `gold_transfer` events in replays but not shown as timeline icons — the balance change appears in the state diff.

#### ✅ Modify Territorial Bonuses

**What it does:** Each territory grants one of 9 bonus types to its owner. Bonuses stack globally.

**Files involved:**
- `territory_bonuses.json` - Territory → bonus_type mappings (57 territories, used as default/fixed assignments)
- `game_state/data_definitions.py` - BONUS_TYPES definition (line ~347)
- `game_state/economy.py` - Cost reduction and income bonus integration
- `game_state/military.py` - Unit strength bonus integration
- `map_data.py` - Bonus loading, `randomize_territory_bonuses()`, `apply_territory_bonuses()`
- `Bonus_Tool.py` - Assignment tool for configuring fixed bonuses
- `main.py` - `initialize_game()` acts on `randomize_bonuses` flag

**Bonus types and values:**
```python
BONUS_TYPES = {
    'income_bonus': +3%,        # Applied to total income per territory
    'tech_cost': -5%,           # Tech research cost reduction per territory
    'unit_cost': -5%,           # Unit training cost reduction per territory
    'hero_cost': -3%,           # Hero training cost reduction per territory
    'pikeman_str': +10%,        # Pikeman strength bonus per territory
    'archer_str': +10%,         # Archer strength bonus per territory
    'swordsman_str': +10%,      # Swordsman strength bonus per territory
    'cavalry_str': +10%,        # Cavalry strength bonus per territory
    'building_cost': -15%       # Building cost reduction per territory
}
```

**To change fixed bonus assignments:**
1. Run `Bonus_Tool.py` (interactive GUI tool)
2. Navigate territories with arrow keys or click
3. Press number keys 1-9 to assign bonus type
4. Press S to save (validates all 57 territories assigned)
5. Restart game to load new bonuses

**Randomized bonuses (Additional Options toggle):**
- Enabled via "Randomize Territory Bonuses" checkbox in Additional Options (custom + multiplayer setup)
- `map_data.randomize_territory_bonuses()` distributes 9 bonus types equally (6 each + 3 random extras)
- Campaign missions always use fixed bonuses (they never set `randomize_bonuses=True`)
- Multiplayer: host generates mapping in `territory_selector._launch_game()`, sends via LOBBY_LAUNCH settings; client applies via `map_data.apply_territory_bonuses()`

**Neutral Armies (Additional Options toggle):**
- Placement logic in `main.py` after player territory assignment (~line 606)
- Uses player_index `-1` in garrison system (`game_state.add_garrison(territory, -1, ...)`)
- Battle detection in `game_state/military.py` `_process_arrivals()` — `has_neutral_garrison` variable + `elif` defender branch
- Player -1 guards in battle resolution: skip hero abilities/gold, use "Neutral" in log messages
- Gray flag icons: tinted from player 0's flags in `main.py` flag loading section
- Multiplayer sync: `game_seed` in `setup_config` seeds deterministic `random.Random`
- Campaign excluded implicitly (never sets `neutral_armies=True`)

**To add new bonus type:**
1. Add entry to `BONUS_TYPES` in `game_state/data_definitions.py` (line ~347)
2. Add integration point:
   - Cost bonus: `get_effective_cost()` or `get_effective_tech_cost()` (`game_state/economy.py`)
   - Income bonus: `calculate_player_income()` (`game_state/economy.py`)
   - Strength bonus: `calculate_army_effective_strength()` (`game_state/military.py`)
3. Add color to `Bonus_Tool.py` BONUS_TYPES dict (line 41)
4. Update `GAME_MECHANICS.md` and `QUICK_REFERENCE.md`

**To change bonus values:**
1. Modify `BONUS_TYPES['bonus_type']['value']` in `game_state/data_definitions.py`
2. Values are percentages (3 = +3%, -5 = -5%)
3. Test stacking behavior (multiple territories with same bonus)
4. Update `QUICK_REFERENCE.md` with new values

**Integration points:**
- **Income:** `calculate_player_income()` (`game_state/economy.py`) - Applied after all territory income summed
- **Building costs:** `get_effective_cost()` (`game_state/economy.py`, line ~23) - Checked for 'building_cost' bonus
- **Unit costs:** `get_effective_cost()` (`game_state/economy.py`, line ~23) - Checked for 'unit_cost' bonus
- **Hero costs:** `get_effective_cost()` (`game_state/economy.py`, line ~23) - Checked for 'hero_cost' bonus
- **Tech costs:** `get_effective_tech_cost()` (`game_state/economy.py`) - Separate method for research
- **Unit strength:** `calculate_army_effective_strength()` (`game_state/military.py`) - Per-unit-type bonuses

**How bonuses work:**
- Bonuses recalculate dynamically based on current territory ownership
- Cache is invalidated via `invalidate_territorial_bonus_cache()` whenever `territory_owners` changes
- **CRITICAL:** Any code that modifies `territory_owners[x]` MUST call `invalidate_territorial_bonus_cache()` afterward
- Capturing a bonus territory gives benefits immediately
- Losing a bonus territory removes benefits immediately
- Multiple territories with same bonus stack (e.g., 2× income_bonus = +6% total)
- Bonuses apply globally to all player actions (not per-territory)

**UI display:**
- Bonus button in top panel (right of phase indicator) shows active bonuses on hover
- Tooltip always shows YOUR bonuses (automatically detects human player in single-player, uses local_player_index in multiplayer)
- Works correctly regardless of player slot (1-4) or whose turn it is
- Territory info in bottom panel shows territory's bonus type
- Tooltip format: "+6% Income", "-10% Technology Research Cost" (no territory counts)

### When NOT to Modify game_state

❌ **Rendering** → Use `rendering/map_renderer.py`, `rendering/ui_renderer.py`
❌ **Input handling** → Use `input/mouse_handler.py`, `input/keyboard_handler.py`
❌ **UI layout** → Use `main.py` or `rendering/ui_renderer.py`
❌ **Visual effects** → Use `ui/effects/` directory
❌ **Asset loading** → Use `main.py` or rendering modules
❌ **Camera/zoom** → Use `input/camera_handler.py`
❌ **Network protocol** → Use `network/protocol.py`

### Key Methods Reference

| Method | Purpose | File | Line (approx) |
|--------|---------|------|---------------|
| `__init__()` | Initialize game state | `game_state/__init__.py` | ~202 |
| `start_construction()` | Start building construction | `game_state/buildings.py` | Search |
| `start_training()` | Queue unit for training | `game_state/buildings.py` | Search |
| `create_movement_order()` | Create army movement | `game_state/military.py` | Search |
| `execute_all_orders()` | Process all movement orders | `game_state/military.py` | Search |
| `resolve_battle()` | Combat resolution | `game_state/military.py` | ~2008 |
| `calculate_player_income()` | Generate player income | `game_state/economy.py` | Search |
| `calculate_territory_income()` | Territory-level income | `game_state/economy.py` | Search |
| `apply_taxation()` | Deduct taxation at turn end | `game_state/economy.py` | ~261 |
| `check_victory()` | Check win conditions | `game_state/victory.py` | Search |
| `get_effective_cost()` | Apply tech discounts | `game_state/economy.py` | ~23 |
| `calculate_army_effective_strength()` | Unit matchup calculation | `game_state/military.py` | Search |

---

## main.py

**What it does:** Main game loop, UI rendering, event handling
**Size:** ~13,000 lines
**Dependencies:** pygame, game_state, rendering modules, input modules
**Pure UI layer:** No game logic (delegates to game_state package)

### When to Modify

#### ✅ Add UI Element

**New panel/window:**
1. Add rendering code in `Game.draw_ui()` or delegate to `rendering/ui_renderer.py`
2. Add click detection in `Game.handle_mouse_click()` with priority
3. Load assets in `Game.__init__()` if needed
4. Update `rendering/ui_renderer.py` for complex UI

**New button:**
1. Define button rect in UI layout calculation
2. Add click handler in appropriate priority level
3. Draw button in rendering phase
4. Consider using `rendering/ui_renderer.py` for consistency

#### ✅ Add Button Tooltip (Lines 4227-4500)

**Tooltip types supported:**
- `'building'` / `'map_building'` - Building tooltips
- `'training'` / `'map_training'` - Unit training tooltips
- `'hero_training'` / `'map_hero_training'` - Hero training tooltips
- `'army_unit_tooltip'` - Army unit composition tooltips
- `'resource_slot'` - Top panel resource stat tooltips (no visual hover)
- `'territorial_bonuses'` - Territorial bonuses button tooltip

**Adding new tooltip:**
1. Define hover tracking in rendering code using `update_button_hover()`
2. Add tooltip definition in `draw_button_tooltip()` with button_type
3. Use font sizes: `'normal_bold'` for titles, `'small'` for descriptions
4. Clear hover with `update_button_hover(None, 'your_type')` when not hovering

**Tooltip clearing pattern (Lines 6843-6962):**
- Track hover state with boolean flag: `any_button_hovered = False`
- Set flag to `True` when hovering over any button in the group
- After loop: `if not any_button_hovered: update_button_hover(None, 'button_type')`
- Purpose: Prevents tooltips from persisting when mouse moves away

#### ✅ Modify Battle Interface

**Battle resolution flow:**
1. Player clicks territory with battle marker → `EnhancedBattleInterface` opens
2. Player clicks FIGHT → `game_state.resolve_battle()` called immediately
3. Actual survivors passed to UI via `set_actual_battle_result()`
4. Battle info stored in `_resolved_battle_info` for deferred cleanup
5. Player clicks CLOSE → cleanup applied using stored info

**Key method in battle_interface.py:**
```python
def set_actual_battle_result(self, winner: int, attacker_survivors: int,
                             defender_survivors: int, surviving_units: list = None):
    """Update the battle result with actual values from game_state.resolve_battle()."""
    # Recalculates unit_breakdown using actual surviving_units list
```

**Important:** Battle resolution happens on FIGHT click (not CLOSE). This ensures:
- Accurate survivor counts displayed (not estimates)
- Correct unit-by-unit breakdown in report (which Archers/Cavalry survived)
- Battle cleanup happens separately from resolution
- The real result reaches `set_actual_battle_result()` while the animation is still at
  `elapsed ≈ 0`, so it calls `BattleBarVolleyEffect.retarget()` to re-aim the bars at the
  true outcome without disturbing the volley rhythm

##### Bar animation: `BattleBarVolleyEffect`

Modelled on BFME2's War of the Ring auto-resolve. **Visual layer only** — it never touches
`resolve_battle()` or the dice.

**How it works:**
- Both bars are **mirrored**: the attacker anchors at its left edge, the defender at its
  right, so both erode inward toward the centre. `_render_strength_bars()` (the static
  SETUP-state draw) must match `_fill_rect()` or the bar jumps when the animation starts.
  The defender's `BattleBar.png` frame is flipped — the asset is not symmetric.
- Depletion is **stepwise**, not a continuous slide. Each volley fires one blast per side;
  when a blast lands, the chunk it destroyed flashes white-hot **in place** for
  `BURN_DURATION`, then vanishes and the fill steps down.
- The volley count scales with total army size on a log curve, clamped to
  `[VOLLEY_MIN, VOLLEY_MAX]`. The duration falls out of the schedule (it is no longer drawn
  up front), is clamped to `[ANIMATION_MIN_DURATION, ANIMATION_MAX_DURATION]`, and
  `_start_animation()` reads it back into `self.animation_duration`.
- Chunk sizes are jittered then **normalised to sum exactly to the damage**, so the bars
  land precisely on their final fill. `_finish()` also snaps to the final value.

**When modifying, watch for:**
- **Use the private RNG.** The schedule draws from `random.Random(seed)`, never the global
  `random`. `_pre_calculate_battle_result()` still calls `random.seed()` on the global RNG
  immediately before `resolve_battle()` rolls its tie dice — leave that alone, removing it
  changes tie outcomes. `TestDeterminism.test_does_not_disturb_the_global_rng` guards this.
- **Nothing is allocated per frame.** Fills, burn chunks and bar backgrounds are drawn
  straight to the screen; lances, impact bursts and the frame flare are pre-rendered in
  `__init__`. The old version cleared and blitted a full-screen SRCALPHA surface every
  frame — do not reintroduce that.
- **Render order matters.** Lances draw *before* the frame PNG, so a tail still inside the
  firing bar is hidden by the frame's end cap; each lance is also clipped to the far side of
  its muzzle. The frame flare and impact bursts draw *after* the PNG.
- **`BattleBar.png` stores non-zero RGB under fully transparent pixels.** Any additive blit
  of it lights up the whole rectangle. The flare uses `BLEND_RGB_ADD` (which leaves alpha
  untouched) plus a normal alpha blit, so transparency is respected.
- **The flare is one sprite faded with `set_alpha`.** Pre-rendering a sprite per fade step
  cost ~21 ms up front — a visible hitch on the Resolve click. `set_alpha` is sticky, so the
  render path sets it unconditionally on every blit.
- **`retarget()` must keep the RNG stream aligned.** `_split_damage()` draws its weights even
  when damage is zero, so re-running the build with a fresh `random.Random(seed)` reproduces
  identical fire times.
- **Survivor → fill conversion.** Use `_survivor_fill()`, which scales by the side's
  *initial* fill. A raw `survivors / count` makes a weaker side that wins end with a longer
  bar than it started with.

**Skip:** clicking anywhere during ANIMATING, or pressing Space/ESC, calls
`skip_animation()` → `BattleBarVolleyEffect.skip()`. `handle_click()` returns `'skip'`, which
main.py's existing fall-through consumes; the key is wired in main.py's KEYDOWN branch ahead
of the campaign-transmission skip.

**Tests:** `tests/test_battle_bar_volley.py`

**Storage pattern in main.py:**
```python
self._resolved_battle_info = {
    'battle': battle_copy,
    'winner': winner,
    'attacker_survivors': attacker_survivors,
    'defender_survivors': defender_survivors,
    'surviving_units': surviving_units
}
```

#### ✅ Modify "Resolve Remaining Battles" Button

**What it does:** Auto-resolves all pending battles for the local player without battle reports.

- **Button rendering:** `rendering/ui_renderer.py` → `_draw_resolve_all_battles_button()` (below top panel, uses GMenuButton.png)
- **Click handling:** `input/mouse_handler.py` (Priority 5.5) → `main.py` `_handle_resolve_all_battles_click()`
- **Core resolution:** `main.py` `_resolve_all_pending_battles()` — loops resolving battles, handles multiplayer sync, alliance markers, Capital Assault elimination, turn/round advancement
- **Hover/tooltip:** `main.py` `handle_hover()` — suppresses territory/army hover, tracks button hover for tooltip
- **Visibility:** Only during battle phase, when local player has resolvable battles, no battle UI open, not tutorial

#### ✅ Add Visual Effect

**Effect types:**
- Battle map markers (hurricane spiral) → `ui/effects/battleeffect.py` — 1000 particles in 4 spiral arms
- Alliance markers (blue hurricane) → `ui/effects/alliance_marker_effect.py` — 600 particles in 3 spiral arms
- Production glow (sunrays) → `ui/effects/production_glow_effect.py` — 8 rotating ray trapezoids
- Castle upgrades (golden explosion) → `ui/effects/castle_upgrade_effect.py` — 140 gold particles, 3 phases
- Battle bar combat (volleys) → `ui/effects/battle_interface.py` (BattleBarVolleyEffect) — discrete blasts, pre-rendered sprites
- Sparkle particles → `ui/effects/sparkle_effect.py`
- Turn announcements → `ui/effects/turn_announcement_sparkle.py`
- Hero ability bursts (explode/implode) → `ui/effects/ability_burst_effect.py` — configurable particles, phase durations, particle_size, flash_ring, delay
- Hero ability arcs (territory-to-territory) → `ui/effects/ability_arc_effect.py` — configurable particle_size, arc_height
- Hero ability polygon bubbles (territory fill) → `ui/effects/ability_polygon_burst_effect.py` — rising circles, bubble_scale, border_flash
- Vow of Silence wave (full-screen sweep) → `ui/effects/ability_silence_wave_effect.py` — 400 crimson particles sweeping left→right

**Key techniques used across effects:**
- `pygame.draw.circle` for particle rendering (1-4px sizes)
- `pygame.draw.polygon` for tapered ray/trapezoid shapes
- `pygame.SRCALPHA` surfaces for per-pixel alpha transparency
- Reusable surfaces to avoid per-frame allocation

**Steps:**
1. Create effect class in `ui/effects/your_effect.py`
2. Implement `__init__()`, `update(dt)`, `render(screen)`, `is_finished()` interface
3. Instantiate in `Game.__init__()` or when triggered
4. Update in `Game.update()` method
5. Render in `Game.draw_effects()` or appropriate phase

#### ✅ Modify Camera/Zoom

**Don't modify main.py** - Use `input/camera_handler.py` instead

**Camera controls:**
- Pan: Arrow keys or edge scrolling
- Zoom: Mouse wheel
- Handler: `CameraHandler` class in `input/camera_handler.py`

#### ✅ Change Window Size

**Method 1: Settings (recommended)**
Edit `config.json`:
```json
{
  "resolution": [1920, 1080],
  "fullscreen": true
}
```

**Method 2: Code**
Edit `config/constants.py`:
```python
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
```

**Auto-scaling:** UI automatically scales via `ui/scaler.py`

### When NOT to Modify

❌ **Game rules/logic** → Use `game_state/` package
❌ **Territory data** → Use `map_data.py` or data files
❌ **AI decisions** → Use `ai_player.py` and AI modules
❌ **Network sync** → Use `network/` directory

### Key Methods Reference

| Method | Purpose | Line (approx) |
|--------|---------|---------------|
| `__init__()` | Initialize pygame, load assets | ~97 |
| `run()` | Main game loop | Search |
| `handle_events()` | Process pygame events | Search |
| `handle_mouse_click()` | Click detection with priority | Search |
| `draw_map()` | Delegates to MapRenderer | Search |
| `draw_ui()` | Delegates to UIRenderer | Search |
| `update()` | Update animations, effects | Search |
| `get_army_banner_rect()` | **Banner geometry - single source of truth** | Search |
| `get_effective_garrison_count()` | Flag slot count (must match renderer) | Search |
| `get_garrison_anchor()` | One garrison's circle/banner anchor | Search |
| `get_army_at_pos()` | Army hit-test (`mode='circle'/'banner'/'both'`) | Search |

### Army selection: circles AND banners

**The banner (flag) above an army circle is a first-class click/hover target, not
decoration.** Three passes need its geometry and they must agree:

| Pass | Where |
|------|-------|
| Click | `Game.get_army_at_pos()` (world space) |
| Hover state | `Game.handle_mouse_motion()` (world space) |
| Render + ring brightening | `MapRenderer.draw_territories()` (screen space) |

**All three MUST go through the shared helpers** - `get_army_banner_rect()`,
`get_effective_garrison_count()`, `get_garrison_anchor()`. They used to open-code the
geometry separately and drifted: the click box was only half the banner's height (so the
flag cloth was unclickable), hover ignored the banner entirely, and the click path was
missing the allied-reinforcement slot rule the other two had.

**Banner geometry:** height = `ARMY_CIRCLE_RADIUS * ui_scale * ARMY_FLAG_HEIGHT_RATIO`
(both in `config/constants.py`), width from the source PNG's aspect ratio. The pole base
sits ON the circle anchor and the banner hangs UPWARD: `top = anchor_y - height`,
`bottom = anchor_y`. Never inline the ratio again.

**Circle geometry:** the ring is NOT drawn at `ARMY_CIRCLE_RADIUS`. It is drawn at
`ARMY_CIRCLE_DRAW_SCALE` (0.75) of it and lifted `ARMY_CIRCLE_DRAW_LIFT` (0.35) above the
anchor, so the flag pole sits inside it. Use `get_army_circle_hit()` /
`point_in_army_circle()` - never hit-test a full-radius circle centred on the anchor, which
reaches 0.60 * radius (9-14 screen px) BELOW the visible ring and selects armies from empty
map. The faint glow halo around the ring is decoration and is deliberately NOT clickable.

**The anchor is the pole base, not the circle centre.** `scaled_centers[territory]` and
`get_flag_positions_for_territory()` both give the pole base; the ring is drawn above it and
the banner hangs above that.

**Click priority is circle > plot > banner**, split across `handle_map_area_click()`:

- PRIORITY 3 - `get_army_at_pos(world_pos, mode='circle')`
- PRIORITY 4 - `get_plot_at_pos()`
- PRIORITY 4.5 - `get_army_at_pos(world_pos, mode='banner')`

The banner's full-height box overlaps building plots, including through the flag art's
large transparent margins, so testing banners before plots would silently steal plot
clicks. `handle_mouse_motion()` mirrors this ordering exactly, so anywhere the ring
brightens, a click selects.

Within `mode='both'`, **every** circle is tested before **any** banner: at minimum zoom a
banner is ~30 world units tall while sibling flags sit on a radius-25 ring, so a banner
routinely covers a neighbouring territory's circle. The banner pass keeps the **last**
match, because the renderer iterates `scaled_centers` in the same order - last = drawn on
top.

**Multi-garrison (allied reinforcement):** each garrison gets its own circle AND banner at
its own `get_flag_positions_for_territory()` slot. Hover highlights any garrison's banner;
clicking still only ever selects the current player's garrison.

**When adding a hit target near armies:** derive its rect from a shared helper and add it
to all three passes, or it will drift the same way.

Tests: `tests/test_army_banner_selection.py`

---

### Unit selection strip: right-click context menu

The bottom-UI unit icon grid (`draw_army_composition_ui()`) supports **right-click on a
unit icon** to open a small drop-down, so partial garrison selections can be built without
holding CTRL. The options adapt to the current selection:

| Selection state (within the shown garrison) | Options |
|---|---|
| No *other* unit selected | Select, Cancel |
| Other units selected, this one is not | Select, **Add to Group**, Cancel |
| Other units selected and this one is too | Select, **Remove from Group**, Cancel |

`Select` replaces `selected_army_units` (plain left-click); `Add`/`Remove from Group` is the
same toggle CTRL+click performs - the label just reflects which way it will go. Options are
frozen at open time so they cannot flip while the menu is on screen.

**State** (`main.py`):
- `self.unit_context_menu` - `{'unit_id', 'territory', 'player', 'anchor', 'items'}` or `None`
- `self.unit_context_menu_rects` - `[(rect, action_id), ...]`, rebuilt every draw

**Methods** (all in `main.py`):
| Method | Role |
|---|---|
| `handle_unit_context_menu_right_click(pos)` | Opens/dismisses. Hooked in the event loop's `button == 3` branch **before** the planning-phase gate, so it works in any turn phase |
| `_get_unit_context_menu_rect()` | Sole source of geometry - both draw and hit-test derive from it, so they cannot desync |
| `_close_stale_unit_context_menu()` | Drops a menu whose garrison/unit is gone |
| `draw_unit_context_menu()` | Drawn late in `run()` (with the other popups) so it covers the bottom UI |
| `handle_unit_context_menu_click(pos)` | **Priority 0.5** in `mouse_handler.handle_left_click()` (Battle Reports took Priority 0) |

**It is modal.** While open it is near the top of the click chain and consumes *every*
left-click: an item runs its action, anything else just closes it. Hover underneath is
suppressed in two places - `draw_army_composition_ui()` swaps `self.mouse_pos` for a
`hover_pos` that is voided inside the menu rect (this also gates the unit tooltip), and
`handle_mouse_motion()` excludes the menu rect from `in_map_area` (the menu overlaps the
map when it flips upward).

**Placement:** prefers down-and-right of the icon, flips to up-and-right when it would run
past `WINDOW_HEIGHT`, and is clamped to the screen horizontally.

**Highlight colours are explicit, not `lighten_color()`/`brighten_color()`.** Those scale
multiplicatively, so against the near-black panel `(40, 35, 30)` they shift each channel by
a few points and the feedback is invisible. The menu uses literal `(82, 72, 55)` for hover
and `(150, 126, 76)` for the click flash. Use the helpers only on mid-brightness bases.

Tests: `tests/test_unit_context_menu.py`

---

### Right sidebar: collapse, bookmarks and hit-testing

The right sidebar (Technology / Heroes / Action Queue / Action Log / Quests / Chat) is an
**overlay**: the map is drawn full-width underneath it (`MAP_WIDTH = WINDOW_WIDTH`, camera
clamp and culling use the window width), so collapsing it needs no viewport change.

**States** (`game_state.sidebar_expanded`, not saved; every new game starts expanded):

| State | Panel | Bookmark tabs | Collapse button |
|---|---|---|---|
| Expanded | `[W - SIDEBAR_WIDTH, W)` | stick out to the panel's left | above the tabs, `>>` |
| Collapsed | off-screen (`panel_x == W`) | flush with the right screen edge | above the tabs, `<<` |
| Sliding | animated `panel_x` (150 ms, smoothstep) | travel with the panel | travels too |

**Single source of truth — never recompute `WINDOW_WIDTH - 250`:**
- `ui/sidebar_layout.py` (pure): `sidebar_progress()`, `reverse_anim_start()`,
  `compute_sidebar_layout()` → `SidebarLayout(progress, panel_x, tab_x, top, height, panel_visible)`.
- `Game` wrappers (main.py, "SIDEBAR LAYOUT & COLLAPSE"): `get_sidebar_layout()`,
  `is_sidebar_animating()`, `is_point_on_sidebar_chrome(pos)` (tabs + button),
  `is_point_over_sidebar_panel(pos)` (panel body, bounded to `TOP_PANEL_HEIGHT..BOTTOM_UI_Y`),
  `is_point_over_sidebar(pos)` (either), `_is_ai_turn_click_allowed(pos)`.
- Every consumer goes through them: left click (mouse_handler Priority 7), `get_click_area()`,
  right click, map hover (`handle_mouse_motion`), tooltips (`update_frame_tooltips`), the mouse
  wheel (`handle_camera_zoom`) and the AI-turn click whitelist. The old code hardcoded 250/40
  in four places and ignored the collapsed state in three.

**Toggling:** `toggle_sidebar(expand=None, animate=True)` → True if the state changed.
- Collapsing is refused while `can_collapse_sidebar()` is False: the active mission's
  `is_action_allowed('toggle_sidebar')`. The tutorial always refuses it (button drawn dimmed);
  campaign missions / Tales refuse only while they block every action (intro, pause, endgame).
  **Expanding is always allowed**, so the panel can never get stuck closed.
- Inputs: the round button (`sidebar_toggle_button`), **F2** (`keyboard_handler` →
  `{'toggle_sidebar': True}` → `_handle_sidebar_hotkey()`, plus the AI-turn branch of `run()`),
  and a bookmark click while collapsed (opens the panel on that tab, after the tutorial's
  `sidebar_tab` gate — a locked bookmark does nothing).
- `_handle_sidebar_hotkey()` ignores F2 while chat input, a menu, the save dialog, the Players
  window, a battle UI/popup, Battle Report detail, the alliance popup or the victory sequence is
  up, or the game has ended.
- Toggling clears `ui_renderer.tech_particles` (they store absolute screen positions).

**Drawing** (`draw_order_sidebar()`): panel at `layout.panel_x` → bookmarks
(`ui_renderer._draw_sidebar_tab_buttons(panel_x, …)`) → round button
(`_draw_sidebar_toggle_button` / cached `_get_sidebar_toggle_sprite`, built from
`assets/mapicons/CircleBorder.png` over a solid underlay) → order badge on the Action Queue
bookmark while collapsed (`_draw_sidebar_order_badge`, **local player's** orders only) →
content only while `panel_visible`. When fully collapsed it clears `technology_buttons`,
`hero_selection_buttons`, `order_cancel_buttons` and `cancel_all_button` — stale rects would
otherwise still catch clicks on the map beneath.

**During the slide** panel-body clicks are consumed but not dispatched, and the tech tooltip
and tech particles are skipped (the content moves under a still cursor).

#### When to Modify

✅ **Add a new sidebar tab:** add it to `game_state.sidebar_tabs`, both `tab_names` dicts
(`ui_renderer._draw_sidebar_tab_buttons`), a `_draw_*_content(sidebar_x, …)` branch in
`draw_order_sidebar()` and, if clickable, a branch in mouse_handler Priority 7. Position
everything relative to `sidebar_x` — it moves during the slide.

✅ **Anything that must know whether a point is "over the sidebar":** call
`is_point_over_sidebar()` / `is_point_over_sidebar_panel()`. Do not compare with
`WINDOW_WIDTH - UIConstants.SIDEBAR_WIDTH` — it is wrong while collapsed or sliding.

✅ **Change the slide or button size:** `UIConstants.SIDEBAR_SLIDE_MS`,
`SIDEBAR_TOGGLE_HEIGHT` (ui/scaler.py; the button must fit in `TAB_PADDING_TOP`).

✅ **Let a mission keep the sidebar open:** return False for `'toggle_sidebar'` from its
`is_action_allowed()`.

⚠️ Click/hover rects are rebuilt in `draw_order_sidebar()`, so tests must draw the sidebar
before hit-testing it. Tests: `tests/test_sidebar_collapse.py`.

### Battle Reports

On-map summaries shown to a **defender** on the turn after their territory was attacked.
The attacker has always had the full battle result screen; the defender previously had
nothing but the map changing colour.

**Files**

| File | Role |
|---|---|
| `game_state/military.py` | Capture: `_capture_battle_reports()`, `_capture_uncontested_report()`, `_split_structure_losses()`, `_should_report_to()` |
| `game_state/__init__.py` | `last_battle_reports` (this battle only) and `battle_report_inbox` (append-only) |
| `ui/battle_report_popup.py` | `BattleReportPopupRenderer` - geometry, drawing, hit rects |
| `main.py` | Queues, per-frame update, click/hover/ESC, Detail screen, network send/receive |
| `rendering/ui_renderer.py` | `_draw_close_all_battle_reports_button()` |
| `input/mouse_handler.py` | Priority 0 (popups) and Priority 5.6 (Close All) |

Tests: `test_battle_reports.py`, `test_battle_report_popup.py`,
`test_battle_report_integration.py`, `test_battle_report_network.py`.

#### When to modify

**`heroes_slain`** — names of the defender's heroes killed in that battle (their Keep fell),
taken from `_battle_hero_deaths` (reset per `resolve_battle()`). A defending multiplayer client
never runs the battle, so the `BATTLE_RESOLVE` receiver turns these into
`hero_death_events` for the "Our Hero, X, has been slain in Y!" toast.

**Adding a field to a report** — add it in `_make_battle_report()` and keep it
JSON-safe. The snapshot crosses the network, so **no tuples** (JSON turns them into
lists), no sets, no game objects. `_send_action_to_remote()` has no `try/except` around
`encode_message()`, so an unencodable value crashes the game loop.

**Changing what a popup says** — `build_report_lines()`. The panel height derives from
`len(lines)`, so extra lines are safe.

**Changing where the capture happens** — read this first:

- **The hook must stay in `resolve_battle()`, not `_update_battle_results()`.** The
  perfect-dice-tie path calls `destroy_buildings()` inside
  `_handle_battle_tie_with_dice()` *before* `_update_battle_results()` runs, and that
  method early-returns for a tie. A hook there silently misses ties.
- It sits after `_enforce_army_limits()` and before `pending_battles.pop()`, the only
  point where `winner`, `player_compositions` and the final garrison are all valid on
  **all three** branches (Keep battle, normal battle, dice tie).

#### Rules that are easy to break

**Defender is `battle.original_owner` only.** Allied co-defenders are excluded on
purpose: after resolution the garrison holds only the winner's units, so an ally would
always read as "everything lost" even when the territory held.

**Never read `player_compositions` for the report.** `resolve_battle()` substitutes a
phantom `{'Swordsman': count}` when a player has no recorded composition — and for a
**Keep or Fortress defending alone**, that count is the Keep bonus itself. Use
`battle.army_compositions`, which is only ever populated from a real garrison, so an
absent entry correctly means "no units, the Keep fought alone".

**Structures split into destroyed vs captured.** Champion of the People (Seledra)
preserves Farms/Mines *for the conqueror* — they survive and change owner.
`structures_captured` is non-zero only when that ability fired.

**There are TWO uncontested-capture paths, and both need the hook.**
`military.py _process_arrivals()` covers sequential mode; `sim_phase_manager.py
_process_arrivals()` has its own copy for simultaneous mode. Neither creates a `Battle`,
so `resolve_battle()` never runs and nothing else would tell the owner their territory is
gone. Both call `_capture_uncontested_report()` immediately after `destroy_buildings()`
and **before** `check_victory()`, which can eliminate the owner and make them ineligible.

**Eligibility is judged pre-battle.** `check_victory()` runs inside the battle and can
eliminate a defender who just lost their last territory; reading `eliminated_players`
afterwards lets a battle retroactively suppress its own report.

**Hero abilities must stay silent.** Aggressive Diplomacy (Halon Nextroy) takes territory
in real time. It avoids both hooks only because it sets `territory_owners` directly and
inlines its own building destruction instead of calling `destroy_buildings()`. That is an
accident of structure, not a guarantee — `test_battle_reports.py` pins it.

#### Every ownership-change path, audited

Swept from `grep "territory_owners\[...\] ="`. If you add a new way for a territory to
change hands, add it here and decide which column it belongs in.

| Path | Reports? | Why |
|---|---|---|
| `military.py resolve_battle()` (all 3 branches) | **yes** | `_capture_battle_reports()` |
| `military.py _process_arrivals()` uncontested | **yes** | `_capture_uncontested_report()` |
| `sim_phase_manager.py _process_arrivals()` uncontested | **yes** | sim's own copy of the above |
| `main.py` `BATTLE_RESOLVE` handler | **yes** | reports ride on the message |
| `heroes.py:750` Aggressive Diplomacy | no | resolves in real time (by design) |
| `military.py:2937`, `sim_phase_manager.py:901` | no | neutral territory — there is no defender |
| `sim_alliance_handler.assign_territory()`, `SIM_ALLIANCE_CHOICE` | no | ally-to-ally; the capture itself already reported |
| `victory.py` elimination redistribution | no | the loser is already out of the game |
| `campaign_mission_6.py:1356` | no | scripted faction handover, keeps armies and buildings |
| `tale_lack_of_funds.py _revolt_territory()` | no | Popularity revolt (scripted handover); announced by the T1Revolt transmission |
| `tale_final_breaths.py _rebel_territory()` | no | Rebellion (scripted handover); announced by a toast + the T2R1 / T2R+ transmission |
| `SIM_ROUND_COMPLETE` / `FULL_STATE_SYNC` bulk sync | no | desync correction, not a fresh loss |
| `keyboard_handler.py`, setup phase | no | debug cheats and game setup |

**Multiplayer is covered without extra work for uncontested captures**, because arrivals
are processed *locally on every machine* — sequential clients run `execute_all_orders()`
from the `EXECUTE_ORDERS` handler, and `sim_phase_manager._on_animations_complete()` is
not host-gated. Only *battles* need the network payload, because a client applies those
rather than resolving them. No duplicates result: `queue_battle_report()` keeps only the
local slot in multiplayer, so the attacker's machine discards the defender's copy.

**Dead code that would become a gap if revived** (all currently zero-caller / zero-sender):
`sim_phase_manager._apply_battle_result()`, `_resolve_battle_combat()`,
`resolve_current_battle()`, and the `SIM_BATTLE_RESULT` handler in `main.py`. Any of these
applies a battle outcome without producing a report.

#### Anchoring: the popup belongs to the map, not the view

Placement derives **only** from the territory centre, and is **centred on it in both
axes**. It is deliberately **not clamped into the viewport**: a popup parked against the
screen edge reads as a HUD element and lies about where the battle happened.

Centred rather than sitting *above* the territory, so the popup is visible whenever its
territory is. Placing it above meant a territory within one popup-height of the top of the
map band had its report culled entirely while the territory was still in plain view, which
looked like a missing report.

`draw()` handles the consequences instead:
- **culls** any popup whose rect no longer intersects the map band
- **clips** the whole pass to that band, so a popup low on the map cannot paint over the
  bottom UI panel (the clip is saved and restored — it is shared surface state)
- **clips the hit rects too**, via `rect.clip(band)`. A button half hidden under a panel
  must not take clicks there, or the Priority 0 handler would swallow them before the
  panel underneath ever sees them.

Residual trade-off: the buttons sit at the bottom of the board, so a territory centred
within half a popup of a band edge can have them clipped away, leaving the report readable
but not clickable. Panning slightly, or "Close All Battle Reports", covers that.

#### Readability: dark board, light text

The raw board art is mid-tone wood. Dark text on it measured **2.58:1** contrast at the
real 12px size — below even the 3:1 large-text floor — so `BOARD_DARKEN` is multiplied
into the cached scaled surface once per size and the text is light instead. That gives
12.4:1 for the body lines, 9.4:1 for DEFENDED and 5.6:1 for LOST.

Use `BLEND_RGBA_MULT`, never `BLEND_RGB_MULT`, which ignores the alpha channel and would
square off the board's feathered edges. If you restyle, **re-measure at 12px** — a colour
that looks fine in a zoomed mockup can fail badly at the size it actually renders.

#### Visibility: two predicates, not one

| Predicate | Governs |
|---|---|
| `_viewer_in_planning()` | **clearing** |
| `_battle_reports_visible()` | **drawing and clicks** (adds the turn-announcement and cinematic guards) |

They are separate for a reason. Reports are queued *before* the turn announcement that
opens the turn they belong to. Keying the clear on visibility destroyed every report
during that announcement, and the feature looked completely dead in play while every
unit test passed.

**Clearing happens on the TRANSITION OUT of a planning phase, never merely because we
are not in one.** `_battle_report_planning_owner` records whose planning phase is
running; when it ends (or the viewer changes), that player's queue is emptied once.

This matters most in **simultaneous mode**. Battles resolve during the `'resolving'`
phase, when nobody is planning — and because every player plans at once, the viewer *is*
the defender at that moment. A "not in planning, therefore clear" rule wiped each report
on the very frame it was captured, so nothing ever appeared. Sequential mode hid the bug:
there, battles resolve during the *attacker's* turn, so the defender's queue was never
the one being cleared.

`_get_report_viewer()` also returns `get_local_player()` in simultaneous mode, not
`current_player`: "whose turn is it" is meaningless when everyone plans together, and sim
code temporarily swaps `current_player` while running each player's orders, which could
otherwise hand back an AI slot.

The `turn_announcement_active` guard is load-bearing, not cosmetic: the event loop
`continue`s past every mouse and keyboard event while an announcement plays, so a popup
drawn then would silently swallow clicks.

`_get_report_viewer()` returns `local_player_index` in multiplayer, else
`game_state.current_player` — **not** `get_local_player()`, which returns the first
non-AI player and would be 0 for both humans in hotseat.

#### Click priority

Reports are **Priority 0** but **not modal**, unlike the unit context menu: a click that
misses every popup returns `False` and falls through to the map. `_battle_reports_accept_clicks()`
stands the handler down while the game menu, options menu, save dialog or battle popup is
open — without that, a Priority 0 check would steal clicks from menus at Priority 3/4.
Overlapping popups are hit-tested in **reverse** draw order, so the visible one wins.

#### Detail screen

`EnhancedBattleInterface(report_snapshot=...)` opens directly in the REPORT state.
`_load_assets()` and `_calculate_layout()` still run (they are battle-data free, and the
layout is the only producer of `report_panel_rect`, `close_button_rect` and the text
metrics); `_extract_battle_data()` is skipped because the `Battle` is popped the instant
it resolves. `current_player` is set to the defender so the totals line reads
`defender_lost` / `defender_survivors`.

**Do not route its close through `_finalize_enhanced_battle()`** — that would re-broadcast
a `BATTLE_RESOLVE` message and re-create alliance markers for a battle finalised long ago.
Use `close_battle_report_detail()`.

#### Multiplayer

**A client never runs `resolve_battle()`** — the `BATTLE_RESOLVE` handler applies the
winner, garrison and ownership directly. The capture hook therefore never fires on the
defending client, the one player who needs the report, so reports ride along on that
message as a `battle_reports` key.

- It is a key on the **existing** payload, not a new message type:
  `validate_message_data()` has no `BATTLE_RESOLVE` branch, the server relays the original
  bytes, and the receiver reads via `.get()`, so older builds ignore it.
- **Do not bump `NETWORK_VERSION`** for an additive key. `server.py` compares versions by
  exact string (despite the "MAJOR only" comment in `network_config.py`), so any bump locks
  out every peer on the old build.
- There are **four** send sites. Three read `game_state.last_battle_reports` live;
  `_finalize_enhanced_battle()` must use the copy stashed in `_resolved_battle_info`,
  because it broadcasts on the CLOSE click, arbitrary frames after `resolve_battle()` ran
  on the FIGHT click, by which time another battle could have overwritten the live list.
- `queue_battle_report()` keeps only the local slot in multiplayer. The resolver also
  captures reports for remote defenders (it ran the battle); they reach their owner over
  the wire, and keeping them would build queues this client can never display.

#### Deliberately NOT wired in

`save_manager.py`, `replay_recorder.py`, `calculate_state_checksum()` and
`_send_full_state_sync()`. Reports are per-viewer UI state that legitimately differs
between host and client — putting them in the checksum would cause **false desyncs**.

---

## AI System

**Modules:** `ai_player.py`, `ai_strategy.py`, `ai_military.py`, `ai_economy.py`, `ai_hero.py`
**Total:** ~4,508 lines
**Difficulty levels:** Easy (0), Medium (1), Hard (2) - all fully implemented

### ai_player.py (~911 lines)

**What it does:** Main AI controller with threading
**Entry point:** Called by main game loop when AI turn

**Threading model (H6):**
- Uses `ThreadPoolExecutor(max_workers=1)` per AI player instance (not raw `Thread()`)
- Thread pool created in `__init__()`, reused across turns to avoid thread creation overhead
- Call `shutdown()` when AI player is no longer needed to clean up the worker thread

**Animation waiting (H8):**
- Uses `threading.Event` (`_animation_done`) instead of `time.sleep()` polling
- External code can call `notify_animation_complete()` to wake the AI thread immediately
- Falls back to 100ms timeout if event not signaled (backward-compatible)

#### When to Modify

✅ **Add new AI decision type:**
1. Add method to `AIPlayer` class
2. Call from `make_decisions()` method
3. Use thread-safe access to game state
4. Test at all difficulty levels

✅ **Change AI turn timing:**
- Readability pauses (thinking `decision_delay_*`, 0.5 s between actions, the final 1.0 s,
  battle-resolution beats) all go through **`AIPlayer._pace(game_state, seconds)`** — never
  call `time.sleep()` for pacing directly, or missions cannot speed it up.
- `_pace()` multiplies by the active mission's optional **`ai_delay_scale`** (default 1.0).
  Tale I sets 0.0 for fast AI turns. Animation waits are deliberately not scaled.
- Adjust threading/locking as needed

✅ **Mission hooks the built-in AI respects** (for missions that use `ai_player` instead of a
scripted AI, i.e. `block_ai` is `False`):
- `is_ai_target_allowed(attacker, territory)` — read through
  `ai_military.mission_allows_ai_target()` in `AttackPlanner.find_reachable_enemies()`
  (disallowed = neither a target nor passable) and as a last-line guard in
  `_execute_action_internal()` for `'move'` and targeted `'hero_ability'` actions.
  Without the hook (custom games, missions 1-7) everything is allowed.
- `is_action_allowed('train' | 'build', ...)` — already queried by `start_training()` /
  `start_construction()` for every player, so a mission can gate the AI by checking
  `game_state.current_player`.
- `is_action_allowed('train_hero', territory=, hero_type=)` — `start_hero_training()` has
  **no** mission check of its own (the player is stopped in the UI), so the built-in AI asks
  through `ai_military.mission_allows_ai_action()`, both when planning
  (`HeroManager.plan_hero_actions()`) and executing. Tale II forbids Heroes for everyone;
  Tale I's gate refuses only player 0, so its AI still trains them.
- `get_ai_attack_cap(attacker, territory)` → int or None — the most units this AI may send
  against one target **per turn** (Tale II). Read through `ai_military.mission_ai_attack_cap()`,
  which never caps moves into the AI's own land. Applied in
  `AttackPlanner.select_attack_targets()` (planned units per target) and as a last-line guard
  in `_execute_action_internal('move')`, which subtracts the units this player already has
  ordered at that target (`gs.movement_orders`) — so orders a mission placed itself count too.
- `ai_delay_scale` — see above.

✅ **Integrate notify_animation_complete():**
- Call `ai_player.notify_animation_complete()` from game loop when animations finish
- This wakes the AI thread immediately, reducing idle wait time

### ai_strategy.py (~460 lines)

**What it does:** Territory evaluation, threat assessment, strategic planning

**Key classes:**
- `TerritoryScorer` - Evaluates territory strategic value (0-100)
- `ThreatAnalyzer` - Calculates threat to territories, finds threatened areas
- `OpportunityDetector` - Finds expansion targets and weak enemies (caches own `TerritoryScorer`)
- `StrategyEvaluator` - Main coordinator (caches all three above)

**Army API pattern (H11):**
- `get_territory_total_armies()` for threat assessment (enemy + allied garrisons)
- `territory_garrisons[player_index]` for own available forces
- `ThreatAnalyzer.calculate_territory_threat()` uses effective garrison (includes +10 keep defense bonus via M15)

#### When to Modify

✅ **Change territory priority:**
- Modify scoring in `TerritoryScorer.calculate_territory_value()`
- Adjust threat detection weights in `ThreatAnalyzer`
- Change expansion priorities in `OpportunityDetector`

✅ **Add new strategic factor:**
- Add to territory evaluation scoring
- Update `calculate_territory_threat()`
- Test impact on AI behavior

### ai_military.py (~1060 lines)

**What it does:** Combat decisions, army movement, attack planning

**Mission target hook:** module-level `mission_allows_ai_target(game_state, player_index,
territory)` returns the active mission's `is_ai_target_allowed()` verdict (True when no
mission / no hook). Any new AI code path that picks an attack or conquest target must call it.
Siblings: `mission_ai_attack_cap()` (per-target unit cap) and `mission_allows_ai_action()`
(the mission's `is_action_allowed()` for actions the engine doesn't gate itself) — any new
path that sends units at a target or trains Heroes must call them too.

**Counter composition:** `ArmyComposer.calculate_counter_composition()` counters only combat
units. Captains have no counter (`COUNTERED_BY['Captain'] is None`); when they were the most
common enemy unit the AI used to try training unit type `None`.

**Key classes:**
- `ArmyComposer` - Calculates optimal unit composition (counter system)
- `AttackPlanner` - Selects targets, scores attacks (caches `TerritoryScorer`)
- `DefenseCoordinator` - Reinforcement and repositioning moves (shared helpers: `_get_territories_with_available_garrison`, `_try_queue_move`)
- `TrainingPlanner` - Unit training decisions
- `MilitaryCommander` - Main coordinator

**Keep defense bonus (M15):**
- `_score_attack_target()` adds +10 to enemy effective strength when target has Keep
- This is a flat bonus (not percentage), making keeps consistently valuable

**BFS reachability pre-computation (H5):**
- `select_attack_targets()` pre-computes BFS reachability for all garrison territories
- Stored in `precomputed_reachability` dict before the scoring loop
- Avoids redundant O(n) BFS calls inside the O(n) territory loop (was O(n^2+) overall)

#### When to Modify

✅ **Change attack behavior:**
- Modify `AttackPlanner._score_attack_target()` scoring logic
- Adjust `_calculate_garrison_needed()` for garrison requirements
- Change `DefenseCoordinator` reinforcement strategies

✅ **Add unit composition strategy:**
- Update `TrainingPlanner._select_unit_type()` decisions
- Modify `ArmyComposer.calculate_counter_composition()` ratios
- Balance unit type priorities

**Tiered attack aggression (war economy):**
- Gold tiers at 1200/2400/4000g reduce garrison requirements (-1/-2/-3) and attack min_ratio (-0.2/-0.4/-0.5)
- Max attacks per turn: 4/5/7 at each tier (default 3)
- `plan_training()` skips territories at MAX_ARMIES_PER_TERRITORY

### ai_economy.py (~1040 lines)

**What it does:** Building priorities, tech research, economic planning

**Key classes:**
- `BuildingPlanner` - Building placement scoring (caches `TerritoryScorer` and `ThreatAnalyzer`)
- `TechResearcher` - Technology research priority by difficulty
- `BudgetAllocator` - Gold allocation across spending categories
- `EconomyManager` - Main coordinator

**Dynamic building types (M14):**
- `select_building_action()` iterates `game_state.building_types.keys()` instead of hardcoded list
- New building types added to `game_state.building_types` are automatically considered

#### When to Modify

✅ **Change building priorities:**
- Modify `_score_building()` pipeline (base scores + modifiers)
- Adjust economic vs military balance in `BudgetAllocator`
- Change tech research order in `TechResearcher.TECH_PRIORITIES`

✅ **Add new economic strategy:**
- Add modifier functions to building scoring pipeline
- Update `BudgetAllocator.allocate_budget()` for new strategic modes
- Modify resource allocation percentages

**War economy system (multi-tier gold thresholds):**
- `select_buildings_to_demolish()` returns a list of buildings to demolish (not just one)
- Gold tiers: 1200g (tier 1), 2400g (tier 2), 4000g (tier 3)
- Higher tiers demolish more economy buildings (Farm→Mine→Market), boost tech scores, force research
- `_adjust_tech_score()` accepts `gold_tier` param for multiplied scores (1.25x/1.5x/2.0x)
- Demolition no longer requires all plots to be occupied

### ai_hero.py (~750 lines)

**What it does:** Hero ability management, hero training selection

**Key classes:**
- `HeroSelector` - Chooses which heroes to train (difficulty-specific priorities)
- `AbilityExecutor` - Scores and selects abilities (caches `TerritoryScorer`, difficulty-aware via M30)
- `HeroManager` - Main coordinator

**Difficulty-aware ability scoring (M30):**
- `evaluate_ability_usage()` accepts `difficulty` parameter
- Scores multiplied by difficulty modifier: Easy=0.5x, Normal=0.8x, Hard=1.0x
- Lower scores mean fewer abilities pass `MIN_ABILITY_THRESHOLD` (15.0)
- This makes Easy AI use abilities less optimally (not just less frequently)

**Hero training queue structure:**
- `hero_training_queue` is `{territory_name: {plot_index: (hero_type, training_time)}}` — keyed by territory, NOT player
- `_count_training_heroes()` and `_get_training_hero_types()` iterate all queue entries filtered by territory owner
- `_find_keep_for_training()` checks if territory already in queue (not player in queue)

#### When to Modify

✅ **Add new hero ability:**
1. Add scoring method `_score_your_ability()` to `AbilityExecutor`
2. Add entry to `_ability_scorers` dispatch dict in `__init__()`
3. Test ability effectiveness at all difficulty levels
4. Balance usage priority (base score 60+ = "use when ready")

### When NOT to Modify AI

❌ **Change game rules** → Use `game_state/` package
❌ **Cheat/give AI advantages** → Difficulty should affect decision quality, not resources
❌ **Modify rendering** → AI doesn't touch rendering

### Testing AI Changes

```bash
# Run AI strategy tests
pytest tests/test_ai_strategy.py

# 40-turn stress tests (sequential mode)
python tests/test_ffa_sequential_40turn.py
python tests/test_2v2_sequential_40turn.py

# 40-turn stress tests (simultaneous mode)
python tests/test_ffa_simultaneous_40turn.py
python tests/test_2v2_simultaneous_40turn.py

# All 4 tests validate: army limits, garrison consistency, gold, territory ownership
# Plus AI behavior analysis, building analysis, hero analysis
```

---

## Network System

**Modules:** `network/server.py`, `network/client.py`, `network/protocol.py`, `network/message_queue.py`, `network/lobby.py`, `network/territory_selector.py`, `network/multiplayer_setup.py`, `network/upnp.py`
**Total:** ~4,900+ lines
**Status:** Full 2-4 player multiplayer with AI slots, reconnection support, UPnP internet play

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        HOST (Player 0)                       │
│  ┌─────────────────┐     ┌─────────────────────────────────┐│
│  │  NetworkServer  │────▶│  Game Loop (authoritative)      ││
│  │  (multi-client) │     │  - Runs all game logic          ││
│  └────────┬────────┘     │  - Executes AI turns            ││
│           │              │  - Broadcasts state changes     ││
│           │              └─────────────────────────────────┘│
└───────────┼─────────────────────────────────────────────────┘
            │ TCP
    ┌───────┴───────┬───────────────┐
    ▼               ▼               ▼
┌────────┐    ┌────────┐      ┌────────┐
│Client 1│    │Client 2│      │Client 3│
│(P1)    │    │(P2)    │      │(P3)    │
└────────┘    └────────┘      └────────┘
```

### Key Design Decisions

| Decision | Implementation |
|----------|----------------|
| Authority | Host-authoritative (runs all logic, AI, battles) |
| Player count | 2-4 flexible (host + up to 3 clients) |
| AI slots | Configurable per-slot (Easy/Medium/Hard) |
| Disconnect | AI takes over immediately, player can reconnect |
| Reconnection | Name + password authentication (5-min window) |
| Host disconnect | Game ends for all clients |
| Allied vision | Allies see each other's movement arrows |
| Internet play | UPnP auto port-forward + public IP detection (graceful LAN fallback) |

### network/upnp.py (~150 lines)

**What it does:** Automates router port-forwarding via UPnP IGD protocol for internet play

**Key Class:** `UPnPManager` — full lifecycle: discover IGD → map port → detect public IP → cleanup

**When to Modify:**
- Change UPnP timeout/description → `network_config.py` constants `UPNP_DISCOVERY_TIMEOUT`, `UPNP_DESCRIPTION`
- Change public IP detection APIs → `PUBLIC_IP_APIS` list in `network/upnp.py`
- Change UI status messages → `get_status_text()` in `UPnPManager`
- Change port mapping protocol (e.g. UDP) → `_setup_worker()` addportmapping call

**Integration points:** `server.setup_upnp()` starts it, `server.stop()` cleans up, `territory_selector._draw_host_ip()` polls status

### network/server.py (~1,000 lines)

**What it does:** Multi-client TCP server for 2-4 player multiplayer

**Key Classes:**
- `NetworkServer` - Main server managing multiple clients
- `ClientConnection` - Per-client state (socket, buffer, player info)
- `DisconnectedPlayer` - Reconnection info storage

**Key Methods:**
```python
broadcast_message(msg, exclude=None)  # Send to all clients
send_to_player(idx, msg)              # Send to specific player
kick_player(idx, reason)              # Kick player from lobby
reserve_slot(idx)                     # Reserve slot for AI
set_game_started(started)             # Enable reconnection mode
_relay_to_other_clients(raw, from_idx) # Relay client msg to other clients (3+ player)
```

**Message Relay (3+ player support):** The server relays gameplay messages from one client to all other clients via `_RELAY_MESSAGE_TYPES` set. This enables real-time sync in 3+ player games (orders, battles, chat, hero abilities, turn ends). Raw bytes are relayed for zero overhead; the sender is excluded to prevent echoes.

#### When to Modify

✅ **Add new network message type:**
1. Define in `network_config.py` MessageType class
2. Add handler in `_handle_received_message()` if server needs to process it
3. Update `NetworkClient` to send/receive
4. Add handler in `main.py _handle_network_message()`
5. If the message is a gameplay event other clients need to see, add it to `_RELAY_MESSAGE_TYPES` in `server.py`
6. Test with host and multiple clients

✅ **Sync a new game action in sequential multiplayer:**
Every action that modifies game state must send a network message. Pattern:
1. After `game_state.action()` succeeds, call `_send_action_to_remote(MessageType.XXX, {...})`
2. For sim mode: queue order via `sim_state.add_order()` instead (sent via SIM_PLAYER_READY)
3. For cancels: use `ORDER_REMOVE` with `cancel_type` field (training/castle_upgrade/hero_training/research/demolish)
4. `FULL_STATE_SYNC` sent by host at every turn boundary as safety net (sequential mode)
5. `SIM_ROUND_COMPLETE` sent by host at every round end as safety net (simultaneous mode)
6. All randomness must be resolved on sender side; include results in message (e.g., Royal Charisma stolen_units)
7. Send messages in **both modes** — don't guard with `self.sim_state is None` unless sequential-only logic

✅ **Adding state to sync safety nets:**
When adding new game state fields that could diverge between host and client:
1. Add to `_send_full_state_sync()` state_data dict (sequential mode safety net)
2. Add to `_sim_broadcast_round_complete()` authoritative_data dict (sim mode safety net)
3. Add apply logic in both `FULL_STATE_SYNC` and `SIM_ROUND_COMPLETE` handlers
4. Consider adding to `calculate_state_checksum()` in `game_state/__init__.py` for desync detection

✅ **Client SIM_ROUND_COMPLETE handler must mirror host's `complete_round()`:**
When adding new per-round logic in `sim_state.complete_round()`, ensure the client handler in
`main.py _handle_network_message(SIM_ROUND_COMPLETE)` calls the same methods. Currently both call:
`collect_income()`, `finish_constructions()`, `finish_research()`, `finish_castle_upgrades()`, `_tick_building_xp()`

⚠️ **Do NOT call `finish_training()` or `finish_hero_training()` in the client handler.**
The host already runs these in `complete_round()` and sends the results (garrisons with trained units,
decremented training_queue) in the authoritative SIM_ROUND_COMPLETE data. Calling them again on the
client would double-decrement training timers and spawn duplicate units into garrisons (desync).

⚠️ **Client must call `start_planning_phase()` BEFORE applying host's authoritative state.**
`start_planning_phase()` resets all 'moved' units to 'ready'. The host's garrisons contain newly trained
units with 'moved' status. If authoritative garrisons are applied before `start_planning_phase()`, the
reset would incorrectly change newly trained units to 'ready'.

✅ **Change connection settings:**
- Modify in `network_config.py`:
  - `MAX_CLIENTS = 3` (host + 3 = 4 players)
  - `CONNECTION_TIMEOUT = 15.0` seconds
  - `RECONNECTION_TIMEOUT = 60.0` seconds (server.py now uses this constant)
  - `HEARTBEAT_INTERVAL = 5.0` seconds

✅ **Change disconnect behavior:**
- `_disconnect_client()` handles client disconnect
- `game_started` flag determines reconnection vs removal
- AI takeover triggered via `PLAYER_DISCONNECT` message

### network/client.py (~558 lines)

**What it does:** Network client for joining multiplayer games

**Key Features:**
- Automatic reconnection with password
- Heartbeat/ping response
- Disconnect detection with reason

**Key Methods:**
```python
connect(host, port, player_name)      # Initial connection
reconnect(host, port, name, password) # Reconnect after disconnect
send_message(message)                 # Queue message to server
is_connected()                        # Check connection status
```

#### When to Modify

✅ **Add reconnection features:**
- Modify `_handle_reconnect_accept()` for state sync
- Update `reconnect()` for new authentication

✅ **Change disconnect detection:**
- `disconnected` flag set on host disconnect
- `disconnect_reason` provides user-facing message

### network/protocol.py

**What it does:** Message serialization, state sync

**Key Message Categories:**
```python
# Connection
CONNECT_REQUEST, CONNECT_ACCEPT, CONNECT_REJECT, DISCONNECT

# Lobby
LOBBY_STATE, LOBBY_JOIN, LOBBY_LEAVE, LOBBY_KICK
LOBBY_SLOT_UPDATE, LOBBY_COUNTDOWN, LOBBY_LAUNCH

# Reconnection
RECONNECT_REQUEST, RECONNECT_ACCEPT, RECONNECT_REJECT
PLAYER_DISCONNECT, AI_TAKEOVER

# Gameplay
MOVEMENT_ORDER, BUILDING_ORDER, TRAINING_ORDER
EXECUTE_ORDERS, BATTLE_RESOLVE, TURN_END

# Simultaneous Mode
SIM_PLAYER_READY, SIM_ALL_READY, SIM_TIMER_UPDATE
SIM_BATTLE_RESULT, SIM_ALLIANCE_CHOICE, SIM_ROUND_COMPLETE
```

### network/lobby.py (~514 lines)

**What it does:** Lobby state management

**Key Classes:**
- `LobbySlot` - Per-slot state (human/AI/empty, color, team, territory)
- `LobbyState` - Full lobby state with serialization

### network/territory_selector.py (~2,053 lines)

**What it does:** Multiplayer lobby UI with territory selection

**Features:**
- Player slot configuration (Human/AI/Empty)
- AI difficulty per-slot (Easy/Medium/Hard)
- Color and team selection
- Territory claiming with first-come-wins
- Host-only kick and launch controls

### main.py Network Integration

**Key Attributes:**
```python
self.network_connection      # NetworkServer (host) or NetworkClient (client)
self.multiplayer_mode        # True if networked game
self.local_player_index      # 0 for host, 1-3 for clients
```

**Key Methods:**
```python
_process_network_messages()   # Process incoming messages
_handle_network_message(msg)  # Route message to handler
_send_action_to_remote(type, data)  # Send action to network
```

**Adding new message handler in main.py:**
```python
# In _handle_network_message():
elif msg_type == MessageType.YOUR_NEW_MESSAGE:
    data = message.get('data', {})
    # Handle the message
    self.game_state.do_something(data)
```

### Multiplayer Mode Checks

**Always guard network code:**
```python
# Check if multiplayer before accessing network
if self.multiplayer_mode:
    self._send_action_to_remote(MessageType.SOME_ACTION, data)

# Check if host (player 0)
if self.local_player_index == 0:
    # Host-only logic

# Check if client
if self.local_player_index != 0:
    # Client-only logic
```

### When NOT to Modify Network

❌ **Game logic** → Use `game_state/` package (network just syncs state)
❌ **UI rendering** → Network doesn't handle rendering
❌ **AI decisions** → AI runs on host only, network syncs results

### Testing Network Changes

```bash
# Run network tests
pytest tests/test_network_server.py
pytest tests/test_network_protocol.py

# Manual testing (2-4 players)
# Terminal 1 (Host):
python main.py --multiplayer --host

# Terminal 2-4 (Clients):
python main.py --multiplayer --join <host_ip>

# Test checklist:
# [ ] Host creates lobby, clients join
# [ ] AI slot configuration works
# [ ] Territory selection syncs
# [ ] Game launches for all players
# [ ] Orders sync correctly
# [ ] Battles resolve for all
# [ ] Client disconnect → AI takeover
# [ ] Host disconnect → game ends
# [ ] Reconnection with password works
```

---

## Simultaneous Mode

**Modules:** `simultaneous/sim_state.py`, `simultaneous/sim_phase_manager.py`, `simultaneous/sim_conflict_resolver.py`, `simultaneous/sim_alliance_handler.py`, `simultaneous/sim_ai.py`
**Total:** ~3,425 lines
**Status:** Complete, available in single-player and multiplayer

The simultaneous mode is a separate turn system where all players plan their moves at the same time, then orders execute together.

### Architecture Overview

```
┌─────────────────────────────────────────────┐
│  PLANNING PHASE                              │
│  - All players queue orders simultaneously   │
│  - Orders hidden from other players          │
│  - Ends when all click End Turn OR timer     │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│  EXECUTION PHASE                             │
│  - All movements animate simultaneously      │
│  - UI is view-only                           │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│  RESOLUTION PHASE                            │
│  - Resolve crossing army conflicts           │
│  - Resolve battles                           │
│  - Handle alliance arrivals                  │
│  - Apply income/progression                  │
└─────────────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `sim_state.py` | Wraps GameState, adds per-player orders, ready flags, timers |
| `sim_phase_manager.py` | Phase transitions, order execution |
| `sim_conflict_resolver.py` | Crossing armies, multi-army battles |
| `sim_alliance_handler.py` | Allied territory capture, overflow |
| `sim_ai.py` | AI adapter with simulated delay |

### Clicked Orders Run Twice Unless Skipped

The local human's build / train / research / castle / hero-training clicks are **executed
immediately** (visual feedback) **and** queued with `sim_state.add_order()` (sync). The
executor must skip that player's queued copies: `SimPhaseManager._executed_at_click()` checks
`sim_state.click_executed_player`, which `main.py` sets to the local human in single-player
**and** multiplayer. Don't use `local_player_index` for this — it is multiplayer-only (and
also switches off garrison validation for other players' orders); using it applied every
map-icon training twice in single-player (two units, double gold).

All three build/train inputs (map quick-icons, bottom panel, keyboard shortcuts) go through
`Game._try_start_construction()` / `_try_start_training()`: local execute + sim order *or*
sequential-multiplayer `BUILDING_ORDER`/`TRAINING_ORDER` + sim-resolving gate + failure
toast. Don't add a fourth copy.

### When to Modify

✅ **Change timer settings:**
- Modify `BASE_TIMER` and `MASTER_PLANNER_BONUS` in `sim_state.py`

✅ **Change conflict resolution rules:**
- Modify `SimConflictResolver.resolve_crossing_conflict()` for crossing armies
- Modify `SimConflictResolver.resolve_multi_army_battle()` for 3+ armies

✅ **Change alliance handling:**
- Modify `SimAllianceHandler.determine_chooser()` for who picks territory
- Modify `SimAllianceHandler.calculate_allied_casualties()` for damage distribution

✅ **Change AI behavior:**
- Modify `SimultaneousAI.THINKING_DELAY` for AI planning time
- Modify `SimultaneousAI._make_ai_decisions()` for decision logic
- AI uses `_selected_unit_ids` dict to track units across multiple movement orders
- Reset at start of each planning session to prevent selecting same unit twice

✅ **Change unit spawn behavior:**
- `finish_training()` in `game_state/buildings.py` spawns units with 'moved' status
- Called AFTER `start_planning_phase()` in `sim_state.py` to preserve status
- Haste ability exception handled in `finish_training()`

✅ **Change battle UI sides (attacker/defender):**
- `battle.attackers` list stored in `sim_phase_manager._create_battle_conflict()`
- `battle_interface.py` uses this list to determine left (attacker) vs right (defender)

✅ **Change alliance choice UI:**
- `main.py:draw_alliance_choice_popup()` - Uses IGOptMenuBG.png and GMenuButton.png
- Player names displayed in their player color via `get_player_name()`
- Defensive victories skip the popup (original owner retains control)

### Setup Integration

Turn Mode dropdown added to:
- `integrated_setup.py` - Single-player setup
- `territory_selector.py` - Multiplayer setup

### Network Messages

Simultaneous-specific messages in `network_config.py`:
- `SIM_PLAYER_READY` - Player finished planning
- `SIM_ALL_READY` - All ready, merged orders attached
- `SIM_TIMER_UPDATE` - Timer sync between host/client
- `SIM_BATTLE_RESULT` - Battle outcome from resolver
- `SIM_ALLIANCE_CHOICE` - Territory owner selection
- `SIM_ROUND_COMPLETE` - Round finished, carries authoritative state

### State Synchronization (Multiplayer Sim Mode)

The host is authoritative. At round end, `SIM_ROUND_COMPLETE` broadcasts state to prevent desync.

**Synced in SIM_ROUND_COMPLETE (main.py `_sim_broadcast_round_complete()`):**

| Data | Purpose | Location |
|------|---------|----------|
| `player_gold` | Prevents income calculation drift | Line ~1920 |
| `territory_owners` | Battle results synchronized | Line ~1922 |
| `eliminated_players` | Skip income/construction for eliminated | Line ~1924 |
| `heroes` | Hero passive abilities (Haste, Defiance) | Line ~1926 |
| `hero_training_queue` | In-progress training with timers | Line ~1928 |
| `hero_ability_cooldowns` | Ability availability | Line ~1933 |
| `hero_silence_status` | Vow of Silence effect | Line ~1938 |
| `player_tech_researched` | Completed technologies | Line ~1944 |
| `research_in_progress` | Current research timers | Line ~1948 |
| `player_tech_available` | Unlocked tech tree nodes | Line ~1952 |
| `tech_effects` | 10 derived bonus arrays | Line ~1956 |

**Tech Effect Arrays (inside `tech_effects`):**
- `royal_decree_discount` - Royal Decree: 15% off Heroes/Keeps
- `training_cost_discount` - Improved Training: 20% off Swordsmen/Pikemen
- `cavalry_cost_discount` - Animal Handling: 25% off Cavalry
- `archer_keep_strength_bonus` - Battlement Archery: +50% Archer strength at Keeps
- `farm_destruction_gold_bonus` - Raze the Countryside: +30g on enemy Farm destruction
- `cavalry_strength_bonus` - Cavalry Tactics: +33% Cavalry strength
- `divide_conquer_bonus` - Divide and Conquer: +20% Pikemen/Swordsmen strength
- `barracks_cost_discount` - Makeshift Barracks: 25% off Barracks
- `barracks_full_refund` - Makeshift Barracks: 100% demolish refund
- `hero_keep_defense_bonus` - Last Resort: +100% Keep/Castle defense with heroes

✅ **Add new synced state:**
1. Add to `authoritative_data` dict in `_sim_broadcast_round_complete()` (main.py ~1917)
2. Add handler in `SIM_ROUND_COMPLETE` receiver (main.py ~1643)
3. Test with 2-player multiplayer sim mode

✅ **Fix cancel action not syncing:**
- Cancel handlers must remove queued orders from `sim_state.player_orders[local_player]`
- Pattern: Filter out orders matching type and relevant IDs
```python
if self.sim_state is not None:
    local_player = self.get_local_player()
    orders = self.sim_state.player_orders.get(local_player, [])
    self.sim_state.player_orders[local_player] = [
        o for o in orders
        if not (o.get('type') == 'order_type' and o.get('key') == value)
    ]
```

### Testing Simultaneous Mode

```bash
# Test single-player
# 1. Start new game from Custom Game
# 2. Select "Simultaneous" in Turn Mode dropdown
# 3. Play game with AI opponents
# 4. Verify timer, waiting indicator, and phase transitions

# Test multiplayer
# 1. Host game with Turn Mode: Simultaneous
# 2. Join from another machine
# 3. Verify both players see planning phase
# 4. Test crossing army conflicts
# 5. Test alliance arrivals (if allies)
```

---

## Rendering System

**Modules:** `rendering/map_renderer.py`, `rendering/ui_renderer.py`, `rendering/panel_renderer.py`, `rendering/helpers.py`
**Total:** ~6,832 lines
**Pure rendering:** No game logic (reads from game_state)

### rendering/map_renderer.py (~3,690 lines)

**What it does:** Territory overlays, plots, arrows, battle markers

#### When to Modify

✅ **Add new map visual:**
1. Add rendering code in appropriate method
2. Read data from game_state (never modify it)
3. Use `DrawingHelpers` for common shapes
4. Test with different zoom levels

✅ **Change territory colors:**
- Modify color calculation in territory rendering
- Update player colors in `game_state/__init__.py` (not here)
- Capital territories are darkened by 30% (0.7× RGB) to distinguish them
- Removed: Previously territories with moved units had dark overlay (50,50,50,40) - removed to avoid confusion with capital highlighting

✅ **Territory borders (per map):**
- Maps with `"draw_borders": true` in `maps/manifest.json` (currently Azincournean
  Highlands) get a thin ink outline on every territory, drawn in `draw_territories()`
  inside the cached ownership-overlay rebuild — after all fills, so neighbours never
  half-cover a shared edge. Zero cost on static frames; ~1 ms per rebuild while panning.
- Colour / thickness: `MapRenderer.TERRITORY_BORDER_COLOR` and
  `TERRITORY_BORDER_WIDTH_PER_ZOOM` (width = zoom × factor, min 1 px).
- Avareon leaves the flag off (its art has painted borders). The setup-screen preview and
  the replay viewer render maps separately and do not draw these borders.

### rendering/ui_renderer.py (~2,553 lines)

**What it does:** UI panels, buttons, info displays

#### When to Modify

✅ **Add new UI panel:**
1. Define panel layout
2. Add rendering method
3. Read game state data
4. Update panel in `render_panels()`

✅ **Change panel layout:**
- Modify panel positioning
- Adjust element sizes
- Update using `UIScaler` for responsive design

✅ **Top Panel Resource Slots (Lines 329-407):**
- Visual resource display: Taxation, Command Limit, Gold, Income
- Location: Centered between Territory Bonus button and right edge
- Hover tooltips without visual highlighting
- Always shows LOCAL player's stats (not current turn player in multiplayer/AI games)
- Icons scale at 65% height, 1.4x wider (rectangular shape)
- Text uses `small_font`, icons from `assets/mapicons/`

✅ **Action Log Filtering (Lines 1106-1210):**
- Filters messages to show only LOCAL player's events
- Uses regex pattern matching for "Player X" references
- Replaces "Player X" with actual player names (e.g., "Editoreus", "AI (Medium)")
- Security: Prevents players from naming themselves "Player 2" to see opponent messages
- Message storage: Plain strings in `game_state.messages[]`

### rendering/map_extension.py — the strip past the map's east edge

**Why:** the map background is left-aligned (camera `min_x = 0`). On a 16:9 window at the
minimum zoom (1.65) it ends before the window's right edge — 1600x900: map ends at x=1427, a
173 px gap; 1280x720: 181 px; 3440x1440: ~1030 px. 16:10 and 4:3 have no gap. The frame is
filled WHITE first, and the right sidebar used to hide the strip. With a collapsible sidebar it
must be filled — **without changing the zoom**.

**What it draws** (`MapEastExtension`, owned by `Game.map_east_extension`):
- **Painted override:** `'<background path without .png>_east.png'`
  (`east_extension_override_path()`), e.g. `maps/azincournean_highlands/map_east.png`,
  `assets/map_east.png`, `assets/CampaignMaps/Campaign3Map_east.png`. Scaled to the map's
  height; its left edge must continue the map's right edge. Past its end: the average colour of
  its rightmost column.
- **Generated (default):** `MAP_EAST_MODE = 'stretch'` continues each row's edge colour straight
  east (averaged over the last 6 source px), blurs it (`MAP_EAST_BLUR_FACTOR`), keeps a thin
  crisp band at the seam (`MAP_EAST_CRISP_BAND`) and fades into `MAP_EAST_FOG_COLOR` (warm dark
  parchment). Past its end: solid fog. `'mirror'` reflects the map's last strip instead — more
  texture, but it reverses geography (on Azincournean the NE coast bent back south-west), which
  is why stretch is the default.

**Cost:** built once per `(id(map_image_original), window width, map width, min zoom,
override path, mode)` and stored at reduced density (≤ `MAP_EAST_MAX_PIXELS`, ~8 MB) — any zoom
that shows a gap draws fewer screen px per source px than `window_w / src_w`, so this is
lossless. Per frame it costs one blit while static; zoom changes rescale only the visible
slice (same viewport-cache pattern as `_blit_map_background`, Y margin only). Benchmarks:
`TestMapEastEdgePerformance` in `tests/test_fps_benchmark.py`.

**Built lazily** from `_blit_map_east_extension()` (called by `_blit_map_background()` when
`map_x + scaled_map_width < screen width`), never at load — the tutorial and mission 2 bake
cloud cover into `map_image_original` after loading.

#### When to Modify

✅ **Anything that changes `map_image_original`** (new map, re-convert after `set_mode()`,
drawing into it in place) must call `Game._invalidate_map_background_caches()`. In-place edits
keep the same `id()`, so the id-keyed caches cannot notice them — the cloud-cover bakes in
`tutorial_mission.py` / `campaign_mission_2.py` call it for that reason.

✅ **Tune the look:** constants in `config/constants.py` (`MAP_EAST_*`). For one map, prefer a
painted `_east.png` over changing the generator.

### rendering/helpers.py (~527 lines)

**What it does:** Drawing utilities (text, shapes, borders)

#### When to Modify

✅ **Add new drawing utility:**
1. Add static method to `DrawingHelpers`
2. Keep it reusable and generic
3. Document parameters clearly

### Performance Patterns (FPS Optimization)

The codebase uses several performance patterns. Follow these when adding new rendering code:

**Dirty-flag caching (skip work entirely when state unchanged):**
- `_overlay_cache_surface` (map_renderer.py) - Cached territory overlay, keyed by `(camera_offset, camera_zoom, territory_owners_version)`
- `_income_cache` / `_army_count_cache` (economy.py / military.py) - Cached per-player calculations, invalidated via `invalidate_income_cache()` / `invalidate_army_count_cache()` with 30-frame periodic fallback
- `_training_version` (game_state/__init__.py) - Version counter for production glow sync; map_renderer skips `sync_production_glow_effects()` when unchanged
- **Pattern:** Increment `game_state._territory_owners_version` or `_training_version` at every mutation site; consumers check version and skip work when unchanged

**Surface caching:**
- `_ui_icon_cache` (main.py) - Cache scaled icons/portraits: `cache_key = ("prefix_name", size)`
- `_text_cache` (main.py) - Cache static text: `self._get_cached_text(text, font, color)` — used by 128+ call sites
- `_rotated_tab_text_cache` (main.py) - Cache rotated text surfaces
- `_sidebar_toggle_sprites` (main.py) - Round sidebar collapse button, one sprite per (size, direction, state)
- `MapEastExtension` (rendering/map_extension.py) - East map extension + its scaled visible slice (see that section)
- `text_cache` (ui_renderer.py) - UIRenderer's own text cache: `self._get_cached_text(text, font, color)`
- `_SHARED_SPRITE_CACHE` (production_glow_effect.py) - 16 pre-rendered rotation frames, keyed by `(quantized_zoom, player_color)` and **shared process-wide** across all effect instances (bounded LRU). Instances hold a reference via `_sprite_cache`.
- `_scaled_text_cache` (turn_announcement_effect.py) - Smoothscale cache by quantized (width, height)

**Always `.convert()` / `.convert_alpha()` loaded images — including backgrounds:**
- An unconverted surface stays in *file* pixel format, so **every blit** of it (or of anything
  scaled from it) performs a per-pixel format conversion. Measured on the 4096x3072 map:
  **9.26ms per frame unconverted vs 0.15ms converted.**
- `transform.scale()` / `smoothscale()` output **inherits the source format**, so converting
  the original is what matters — converting the scaled copy is too late.
- Map backgrounds load through `_load_map_background()` (main.py), which uses `.convert()`
  (opaque bottom layer). **New map backgrounds must be fully opaque**; transparency would be
  flattened rather than blended. Use `.convert_alpha()` for anything that needs real alpha.
- `.convert()` bakes in the *current display's* pixel format — **re-convert after any
  `set_mode()`** (resolution, fullscreen, or flag change), as `apply_display_settings()` does.

**Scale only what is visible (never the whole map):**
- `Game._blit_map_background()` (main.py) scales just the visible slice of the map background.
  Scaling the FULL map cost `zoom²` — 8.98M pixels (36MB) at zoom 4.0, i.e. 16.1ms nearest /
  **53.1ms smoothscale** — versus 0.31ms / 2.50ms for a viewport-sized slice.
- It over-renders a 192px margin **only when zoom is unchanged**, so panning re-blits the
  cached surface at a new offset rather than rescaling. Skipping the margin while zooming
  matters: the cache is invalidated every frame then, so the extra pixels are pure waste.
- Both render paths (`draw()` and the live loop in `run()`) call this one method — they
  previously held duplicated scaling logic, so a fix had to be applied twice.
- Derive source rects from `surface.get_size()`, **not** the `ORIGINAL_MAP_*` constants, so
  alternate map backgrounds and the black fallback keep working.

**Rebuild scale-derived caches when `scale_factor` changes:**
- `MapRenderer.territory_bounding_boxes` and `multi_zoom_cache` are derived from
  `game.scaled_polygons`. Any path that re-scales those polygons after construction must call
  `MapRenderer.rebuild_scale_caches()`, as `apply_display_settings()` does.
- Skipping it left the caches at the old scale: after 1600x900 → 1280x720 the cached projection
  was **418px** off, misaligning polygons with the map and breaking AABB hit-testing.
- Guarded by `tests/test_resolution_caches.py`.

**Cache, don't copy, full-screen overlays:**
- `_overlay_cache_surface` aliases `fullscreen_overlay` rather than `.copy()`-ing it. The copy
  cost 5.76MB per camera delta (i.e. every frame while panning/zooming) and existed only so the
  content survived the next `fill()` — safe to alias because nothing else writes that surface.
- **Clamp bbox-sized surfaces to the screen**, not just to a minimum of 1. Polygon screen
  bounding boxes grow with zoom squared; unclamped they allocated ~4MB at zoom 4.0 for area that
  is not visible. pygame clips the draw for you.

**Never key a cache on a raw continuous float (quantize it):**
- Keying on an un-quantized zoom/scale/alpha float means the cache **never hits** while that
  value animates. `ProductionGlowEffect` keyed its sprite cache on the raw zoom and so rebuilt
  16 surfaces per effect per zoom change — ~150ms frames with ~100 producing buildings.
- Quantize the key (glow: 0.1 zoom steps; flags: 5px; static glows: 3px) and, where the cached
  result depends only on shared inputs, share one cache across instances rather than per-object.
- Known remaining instances of this bug: `battleeffect.py` and `alliance_marker_effect.py`
  cache on a continuously-animated scale float, so they `smoothscale` every frame.

**Surface reuse:**
- `_get_overlay_surface()` (ui_renderer.py) - Reusable full-screen SRCALPHA surface for modals
- Small clipped SRCALPHA surfaces instead of full-screen where possible (hover overlay ~200x150, battle hurricane ~120x120)
- Never create `pygame.Surface((width, height), SRCALPHA)` in a per-frame method without reuse
- Prefer non-SRCALPHA + `set_alpha()` over SRCALPHA when per-pixel alpha isn't needed (faster blit)

**Algorithmic:**
- Pre-index lookups (e.g., `route_first_order` dict in map_renderer.py) instead of nested loops
- AABB bounding box pre-check in `get_territory_at_pos()` before expensive polygon ray-casting
- Pre-computed sin/cos lookup table in battleeffect.py (360 entries, avoids 1400+ trig calls per frame)
- `crop_to_circle()` uses BLEND_RGBA_MULT (never per-pixel get_at/set_at)

**Benchmarking:**
- Run `python -m pytest tests/test_fps_benchmark.py -v -s` to measure FPS
- Use `tools/stress_test_generator.py` to create worst-case scenarios
- Thresholds: Idle 60+ FPS, Stress 50+ FPS
- Current (2026-03-04): Idle 67.8 FPS, Late Game Stress 59.6 FPS, Movement Arrows 57.7 FPS

### When NOT to Modify Rendering

❌ **Game logic** → Use `game_state/` package
❌ **Input handling** → Use `input/` modules
❌ **AI decisions** → Use `ai_*` modules

---

## Input System

**Modules:** `input/mouse_handler.py`, `input/keyboard_handler.py`, `input/camera_handler.py`
**Total:** ~1,165 lines
**Delegator pattern:** Handles input, delegates actions to game_state

### input/mouse_handler.py (~236 lines)

**What it does:** Mouse input delegation with click priority

#### When to Modify

✅ **Add new clickable element:**
1. Add detection in priority order (popup → UI → map)
2. Delegate action to appropriate module
3. Return True if handled (prevents lower priority)

✅ **Change click priorities:**
- Modify priority order in `handle_left_click()` (the numbered chain in its comment)
- Current: Popups → UI elements → Map territories

✅ **Clickable mission overlay (drawn in `mission.render()`):**
- Define `handle_click(pos) -> bool` on the mission. Priority 4.5 calls it for an active
  mission — below every modal (battle popup, options, save dialog, game menu), above the
  top panel, sidebar, bottom UI and map. Return True to consume the click (Tale I swallows
  every click on its widget so the map beneath never gets selected).

⚠️ **Sidebar hit-testing goes through the live layout** (see "Right sidebar: collapse,
bookmarks and hit-testing" in the main.py section). Priority 7 tests the collapse button, then
the bookmark tabs (a hit always consumes the click), then `is_point_over_sidebar_panel()`.
The panel body only exists above the bottom UI: without that bound, bottom-panel buttons in
the rightmost 250 px (e.g. "Demolish Keep" at 1600x900) were swallowed.

### input/keyboard_handler.py (~530 lines)

**What it does:** Keyboard shortcuts and commands

#### When to Modify

✅ **Add new keyboard shortcut:**
1. Add key detection in `handle_keydown()`
2. Trigger appropriate game action
3. Document in `QUICK_REFERENCE.md`

Order matters: options menu → game menu → **F2 (sidebar)** → ability targeting (swallows every
key) → chat input → building/training shortcuts. A shortcut that must work while targeting a
hero ability goes above that block. An update that is an *action* rather than an attribute
(like `'toggle_sidebar'`) needs its own branch in `Game.handle_keyboard_input()`'s update loop,
which otherwise `setattr`s every key. Keys used during AI turns must also be handled in the
AI-turn branch of `run()` (it only passes ESC, F2, the wheel and whitelisted clicks).

### input/camera_handler.py (399 lines)

**What it does:** Camera pan, zoom, edge scrolling

#### When to Modify

✅ **Change camera behavior:**
- Modify pan speed, zoom speed
- Adjust edge scrolling sensitivity
- Change zoom limits (min/max)

#### Edge Scrolling: the two modes and the Map Edge dwell delay

`handle_edge_scrolling(pos, enabled, mode, pan_speed, top_panel_height, bottom_ui_y, delta_time)`

Only the vertical trigger band differs between the modes — the horizontal bands are
identical:

| | `map_edge` | `window_edge` |
|---|---|---|
| Band position | Inside the map viewport (just below the top panel, just above the bottom UI) | The physical window border |
| Over the UI panels | Returns early, never scrolls | Keeps scrolling |
| Start delay | **`MAP_EDGE_SCROLL_DELAY` (0.2s) dwell** | None — instant |

**Why the dwell exists:** the Map Edge band sits *inside* the viewport, so a player
moving the cursor down to a bottom-UI button crosses it and used to drag the camera
along. `_map_edge_dwell` accumulates `delta_time` while the cursor is inside any band
and resets the moment it leaves one — including via the early return when the cursor
reaches the UI panels. Scrolling only starts once the accumulator passes the delay.

**If you touch this code:**
- Every early return must reset `_map_edge_dwell`, or stale credit lets a later
  transit scroll instantly.
- One shared accumulator covers all four bands, so sliding from the left band into the
  bottom-left corner keeps scrolling without a fresh wait. That is intentional.
- `debug_edge_scroll` is cleared on every non-scrolling frame and cannot carry dwell
  state — the accumulator needs its own field.
- `delta_time` is used **only** for the dwell. The pan itself is still per-frame
  (`offset += scroll / zoom`); converting it to per-second is a separate change.
- Window Edge behaviour is deliberately untouched — there, entering the band means the
  cursor is at the screen border, which is always intentional.

⚠️ **`edge_scrolling_mode` legacy values:** settings once defaulted to `'push'`, which
matched neither branch and produced a hybrid mode (map-edge geometry without the
map-area guard). `SettingsManager._validate_and_clean_settings()` now coerces anything
outside `("map_edge", "window_edge")` to the default, `window_edge`.

---

## map_data.py

**What it does:** Multi-map data loader — territory polygons, adjacency graph, plots, economy, bonuses, fortress territories
**Data source:** Per-map JSON files in `maps/<map_id>/` directories, manifest in `maps/manifest.json`
**Key globals:** `TERRITORY_POLYGONS`, `TERRITORY_CENTERS`, `ADJACENCIES`, `FORTRESS_TERRITORIES`, `_current_map_id`

### Multi-Map Architecture

- `maps/manifest.json` — Registry of all available maps (id, display_name, has_background,
  optional `draw_borders` → `current_map_draws_borders()`, used by the map renderer)
- `maps/<map_id>/` — Per-map data directory containing:
  - `territory_polygons.json`, `plots.json`, `economic_data.json`
  - `territory_bonuses.json`, `adjacencies.json`, `fortress_territories.json`
- `load_map(map_id)` — Primary entry point: loads all data from map directory into globals
- `load_polygons()` — Legacy backward-compat entry point (loads Avareon from root-level files)
- Campaign missions 1-7 use the Avareon map via `load_polygons()`; a registry `config` with
  `'map_id'` (Book of Tales, e.g. Tale I on `azincournean_highlands`) makes
  `Game.initialize_game()` call `load_map(map_id)` instead

### When to Modify

✅ **Add new map:**
1. Create directory `maps/<map_id>/` with all 6 JSON files (empty `{}` or `[]` initially)
2. Add entry to `maps/manifest.json`
3. Use tools with `--map <map_id>` to define territories
4. Optionally add `map.png` to the map directory

✅ **Add territory to existing map:**
1. Use `Polygon_Tool.py --map <map_id>` to draw polygon
2. Use `Economic_Tool.py --map <map_id>` to set income tier
3. Use `Plot_Tool.py --map <map_id>` to place building plots
4. Use `Adjacency_Tool.py --map <map_id>` to set neighbors
5. Use `Bonus_Tool.py --map <map_id>` to assign bonus

✅ **Mark territory as fortress:**
- Edit `maps/<map_id>/fortress_territories.json` — add territory name to the list
- Fortress territories get +2 innate defense and cannot build Keeps

✅ **Change adjacency:**
- Use `Adjacency_Tool.py --map <map_id>` — saves to `adjacencies.json`
- Avareon also has hardcoded fallback adjacencies in `_AVAREON_ADJACENCIES`

### When NOT to Modify

❌ **Edit JSON files manually** → Use the editor tools
❌ **Game logic** → Use `game_state/` package

### Editor Tools

| Tool | Purpose | Usage |
|------|---------|-------|
| `Polygon_Tool.py` | Edit territory shapes | `py Polygon_Tool.py --map <map_id>` |
| `Plot_Tool.py` | Edit building plot positions | `py Plot_Tool.py --map <map_id>` |
| `Economic_Tool.py` | Edit territory income | `py Economic_Tool.py --map <map_id>` |
| `Adjacency_Tool.py` | Edit territory connections | `py Adjacency_Tool.py --map <map_id>` |
| `Bonus_Tool.py` | Edit territory bonuses | `py Bonus_Tool.py --map <map_id>` |

**Important:** Always use tools, not manual JSON editing. Omit `--map` to edit the default Avareon map.

---

## Shared Utilities

### Surface Utilities (`utils/surface_utils.py`)

**What it does:** Shared pygame surface manipulation functions used across multiple UI modules.

**Functions:**
- `crop_to_opaque(surface, threshold=128)` - Crops a surface to its opaque bounding box (removes transparent padding). Used during asset loading for CampaignBTN.png and similar button images.

**Used by:** `achievement_panel.py`, `campaign_screen.py`, `recap_screen.py`, `ui/effects/battle_interface.py`, `Campaign_Text_Tool.py`

**When to modify:**
- Adding a new UI module that loads button/icon images with transparent padding - import and use `crop_to_opaque`
- Adding new surface manipulation helpers - add them here rather than as local methods

---

## Quick Navigation

### "I want to..."

**...add a new Book of Tales scenario**
→ `book_of_tales.py` `SCENARIOS` + `main.py` `_TALE_REGISTRY` + a mission module (template: `tale_lack_of_funds.py`)

**...tune Tale I's Popularity / revolts / AI rules**
→ constants at the top of `tale_lack_of_funds.py`

**...tune Tale II's difficulty (attack cap, forced attacks, rebellions)**
→ constants at the top of `tale_final_breaths.py`

**...restrict or speed up the built-in AI from a mission**
→ mission `is_ai_target_allowed()` / `get_ai_attack_cap()` / `is_action_allowed()` /
`ai_delay_scale` (see AI System → mission hooks)

**...tax one player differently (mission)**
→ `gs.player_taxation_override[player] = level`, read via `gs.get_taxation_level(player)`

**...start a player with techs already researched**
→ add to `player_tech_researched`, then `gs.apply_tech_effect(player, tech, announce=False)`

**...outline territories on a map**
→ `"draw_borders": true` in `maps/manifest.json`; style in `MapRenderer.TERRITORY_BORDER_*`

**...add a new unit type**
→ `game_state/__init__.py` line ~204, add to `UNIT_TYPES`

**...add a new building**
→ `game_state/data_definitions.py` line ~26, add to `BUILDING_TYPES`

**...change unit/building costs**
→ `game_state/__init__.py` `UNIT_TYPES` and `game_state/data_definitions.py` `BUILDING_TYPES` dicts

**...modify combat mechanics**
→ `game_state/military.py` `resolve_battle()` method (line ~2008)

**...change AI behavior**
→ `ai_strategy.py`, `ai_military.py`, or `ai_economy.py` depending on type

**...add UI element**
→ `main.py` for simple, `rendering/ui_renderer.py` for complex

**...add campaign features**
→ `campaign_screen.py` - Campaign screen UI and logic
→ `campaign_mission_*.py` - Mission modules (see [Campaign System](#campaign-system))
→ `campaign_data.json` - Mission text data (edit with `Campaign_Text_Tool.py`)
→ `Campaign_Text_Tool.py` - WYSIWYG editor for campaign mission text
→ `map_data.py` - Territory filtering (`set_enabled_territories`, `set_territory_display_names`)

**...add visual effect**
→ `ui/effects/` directory, create new effect class

**...modify camera/zoom**
→ `input/camera_handler.py`

**...add keyboard shortcut**
→ `input/keyboard_handler.py`

**...change the right sidebar's collapse / slide / bookmarks, or test whether a point is over it**
→ `ui/sidebar_layout.py` + `Game.get_sidebar_layout()` / `is_point_over_sidebar()` / `toggle_sidebar()` / `draw_order_sidebar()` (main.py)

**...change what fills the strip past the map's east edge**
→ `rendering/map_extension.py` + `MAP_EAST_*` in `config/constants.py`, or paint `<map background>_east.png`

**...add new territory**
→ Use `Polygon_Tool.py`, `Economic_Tool.py`, `Plot_Tool.py`

**...change map adjacency**
→ Use `Adjacency_Tool.py` or edit `map_data.py` `ADJACENCY`

**...add research/tech**
→ `game_state/data_definitions.py` technology tree, implement effect in appropriate submodule

**...add logging to a module**
→ `from utils.logger import get_logger` then `logger = get_logger(__name__)`

**...modify network protocol**
→ `network/protocol.py`

**...change victory conditions**
→ `game_state/victory.py` `check_victory()` method

**...balance the economy**
→ Adjust costs in `game_state/economy.py`, `game_state/data_definitions.py`, and `economic_data.json`

---

## Common Mistakes to Avoid

### ❌ Modifying game logic in rendering code
**Wrong:** Adding territory ownership logic in `map_renderer.py`
**Right:** Read ownership from `game_state`, only render visuals

### ❌ Accessing game state directly from UI
**Wrong:** Clicking territory in `main.py` directly changes `game_state.territory_owners`
**Right:** Call `game_state.some_method()` that encapsulates the logic

### ❌ Editing JSON files manually
**Wrong:** Opening `territory_polygons.json` in text editor
**Right:** Use `Polygon_Tool.py` for visual editing with validation

### ❌ Making AI cheat
**Wrong:** Giving AI extra gold or removing fog of war
**Right:** Make AI smarter by improving decision logic

### ❌ Hardcoding the sidebar's position
`WINDOW_WIDTH - 250` (or `- UIConstants.SIDEBAR_WIDTH`) is wrong whenever the sidebar is
collapsed or sliding. Use `Game.is_point_over_sidebar()` / `get_sidebar_layout()`.

### ❌ Hardcoding values
**Wrong:** `if cost == 25:` (magic number)
**Right:** `if cost == UNIT_TYPES['Swordsman']['cost']:`

### ❌ Modifying garrison counts without syncing units list
**Wrong:** `garrison['unmoved'] -= 1` (count diverges from actual units)
**Right:** Modify the units list, then call `self._sync_garrison_counts(territory, player_index)` to reconcile counts.
The `_sync_garrison_counts()` method scans units by status ('ready'/'ordered' → unmoved, 'moved' → moved) and corrects any desync.

### ❌ Using print() for output
**Wrong:** `print(f"Battle resolved: {winner}")`
**Right:** `logger.info(f"Battle resolved: {winner}")` using `from utils.logger import get_logger`

### ❌ Skipping documentation updates
**Wrong:** Adding feature without updating `GAME_MECHANICS.md`
**Right:** Update docs whenever you change game rules/balance

### ❌ Swallowing `pygame.QUIT` in screen classes
**Wrong:** `if event.type == pygame.QUIT: self.cancelled = True` (returns to previous screen instead of exiting)
**Right:** Return a `'quit'` signal that propagates up to the main loop, where `pygame.quit(); sys.exit()` is called.
All screens must distinguish Alt+F4 (exit app) from Escape (go back). Callers must check `== 'quit'` **before** `is None` / `not result`.

---

## Sound & Music System

**What it does:** Audio playback for UI interactions, game events, hero voice lines, and background music
**Size:** 281 lines (sound_manager.py) + ~525 lines (global_sound.py) + ~140 lines (music_manager.py)
**Dependencies:** pygame.mixer (SFX channels), pygame.mixer.music (streaming music)
**Used by:** main.py, game_state package, all menu modules

### Files

- [sound_manager.py](../sound_manager.py) - SFX system with playback, queuing, volume control
- [global_sound.py](../global_sound.py) - Global SFX instance and helper functions
- [music_manager.py](../music_manager.py) - Background music system (3 categories: menu, game, recap)

### Architecture

**Sound Categories:**
- `general` - UI clicks, event notifications (BattleSound, CastleCompleted, DefaultMouseClick, ResearchCompleted)
- `denial` - Programmatically generated denial tone for action failures (no asset file)
- `armycomp` - Army composition sounds (7 random files)
- `seledra` - Hero Seledra voice lines (SeledraRecruit + SeledraSpeech1-5)

**Key Features:**
- Overlap prevention (same category won't play twice while playing)
- Queue system for sequential playback (Research → Castle → Hero priority)
- Anti-repeat logic (prevents same sound twice in a row)
- Per-category volume control
- Player-specific sounds (only local player hears their actions)

### When to Modify

#### ✅ Action Failure Feedback Pattern

When the game refuses something the player tried, it plays the denial sound and shows a
red **toast** (top-left of the map, `chat_notification_effect.add_system_notification()`).
There is exactly one way to do this — **never add a new popup or ad-hoc message.**

**Where the text lives:** `config/action_error_messages.py` → `ACTION_ERROR_MESSAGES`
(`code → text`, `{placeholders}`, `\n` for a line break). Every entry has a comment saying
when the player sees it — the owner edits these texts directly, so keep that comment
accurate and never hard-code a player-facing error text anywhere else.
`format_action_error(code, **fmt)` never raises (unknown code → `DEFAULT_ACTION_ERROR`,
mismatched placeholder → raw text + log warning).

**The flow:**
1. The game-state method records `self.last_action_error = "<code>"` (and optionally
   `self.last_action_error_args = {...}` for placeholders) before `return False`.
2. The `main.py` call site calls `self._show_action_failure_feedback()` in its failure branch.
3. That reads + clears both fields and calls `Game.show_action_error(code, **fmt)`
   (sound + toast). Call `show_action_error()` directly for UI-only refusals
   (e.g. `'wrong_phase'`, `'target_blocked'`).

**Rules:**
- **Every action method resets both fields on entry** (`start_construction/training/
  research/castle_upgrade/hero_training`, `add_movement_order_for_units`,
  `activate_hero_ability`). The AI, network handlers and the sim executor call the same
  methods and never read the code — without the reset their leftovers were shown for a later,
  unrelated failure. Code-less refusals (tutorial blocks) must stay code-less → silent.
- **Hero abilities:** `execute_*` refusals go through `HeroMixin._ability_refusal(code, **fmt)`,
  which records the code and still returns `(False, text)` — the AI reads `result[0]`, the
  network code logs the text. `main.py` clears the code before a targeted cast.
- **R1 — tint instead of toast:** if a control is **red** (a rule refuses it), **grey** (tutorial/
  mission lock) or hidden when the action would be refused, it needs no toast. A button
  that *looks* available but is refused is a bug: fix its tint. The tint must use the same
  check as the action (`get_building_type_block_reason()`, `MAX_TRAINING_QUEUE`,
  `get_effective_tech_cost()`, `tutorial_mission.is_action_allowed()` — campaign missions
  and the Tale only block through `is_action_allowed`, `is_button_locked` is tutorial-only).
- **Hidden territories never produce errors:** `get_territory_at_pos()` skips territories a
  mission hides (`map_data.is_territory_enabled`); map clicks and ability targeting use it.
- **Stay silent:** right-click without selected units, destination == source, modal/AI-turn
  input blocks. **Inside a modal** (Players window) the toast is hidden behind the overlay —
  show the table text in the modal's own feedback line (`PlayersWindow._show_send_error`).
- **Repeats merge:** an identical consecutive toast refreshes the newest one instead of
  stacking; long / `\n` texts wrap onto several lines.

**Adding a new failure:** add a `'code': "Text!"` entry (with its "when" comment) to the
table, set the code in the game-state method (or call `show_action_error` from the UI), and
make sure the call site calls `_show_action_failure_feedback()`. Test it like
`tests/test_action_feedback_phase5.py` (code set by the method + one toast at the call site).

**Hero deaths (news, not an error):** `HeroMixin._record_hero_death()` appends
`(owner, hero, territory)` to `game_state.hero_death_events` (battle capture of the Keep, and
Regicide — not a self-demolished Keep). `Game._show_hero_death_notifications()` drains it
every frame and shows the local player's own deaths as `'hero_slain'` **without** the denial
sound. A defending multiplayer client gets them via the Battle Report's `heroes_slain`.

Tests: `tests/test_action_feedback_*.py`, `tests/test_hero_slain_notification.py`.

#### ⚠️ Adding Files to `general` Category
Adding/removing files from `assets/sounds/general/` shifts alphabetical indices used by `play_ui_click()`, `play_castle_complete_sound()`, `play_research_complete_sound()`, and `play_battle_sound()`. Update ALL index references in `global_sound.py` and `sound_manager.py`.

#### ✅ Add New Sound Category

**Steps:**
1. Create folder in `assets/sounds/[category_name]`
2. Add sound files (.mp3, .wav, .ogg)
3. In `global_sound.py` `initialize_sounds()`:
   ```python
   num_category = sound_manager.load_sounds_from_folder('category', 'assets/sounds/category')
   print(f"[Sound Manager] Loaded {num_category} category sounds")
   ```
4. Create helper function if needed:
   ```python
   def play_category_sound(use_queue=False):
       if use_queue:
           sound_manager.queue_sound('category', 0)
       else:
           return sound_manager.play_specific('category', 0)
   ```

**Files affected:**
- `global_sound.py` - Add loading and helper functions
- Game logic file (e.g., `game_state/buildings.py`) - Add trigger points

#### ✅ Change Background Music

**Music categories:** menu (all menus), game (during gameplay), recap (post-game recap screen)
**Music files:** `assets/music/` — all tracks play for menu and game except `Northern Honour - Recap Screen.mp3` (recap only)
**Key class:** `MusicManager` in `music_manager.py` — uses `pygame.mixer.music` for streaming

**To add a new music track:** Drop MP3 into `assets/music/`. It auto-discovers on startup.
**To change category behavior:** Edit `start_menu_music()`, `start_game_music()`, `start_recap_music()` in `music_manager.py`
**To change transition timing:** Edit `main.py` main loop (search for `music_manager.stop()` / `music_manager.start_`)

**Volume pipeline:** `effective_volume = music_volume * master_volume` (set via options sliders)
**SFX volume pipeline:** `effective_volume = sfx_volume * master_volume` applied via `sound_manager.set_volume()`
**Settings persistence:** `master_volume`, `music_volume`, `sfx_volume` in `settings_manager.py`

#### ✅ Add New Hero Voice Lines

**Steps:**
1. Create folder `assets/sounds/heroes/[heroname]`
2. Add files: `[HeroName]Recruit.mp3` (index 0) and speech files (indices 1+)
3. Add to `initialize_sounds()` in `global_sound.py`:
   ```python
   num_hero = sound_manager.load_sounds_from_folder('heroname', 'assets/sounds/heroes/heroname')
   ```
4. Add recruitment function:
   ```python
   def play_hero_recruit_sound(hero_name, use_queue=False):
       if hero_name == 'Your Hero Name':
           if use_queue:
               sound_manager.queue_sound('heroname', 0)
           else:
               return sound_manager.play_specific('heroname', 0)
   ```
5. Add selection function:
   ```python
   def play_hero_select_sound(hero_name):
       if hero_name == 'Your Hero Name':
           # Implement anti-repeat logic like Seledra (see lines 108-126)
   ```

**Files affected:**
- `global_sound.py` - Add hero loading and functions
- `game_state/heroes.py` `finish_hero_training()` - Add recruitment trigger
- `main.py` hero selection handler - Add selection trigger

#### ✅ Add Event Sound (Research, Castle, etc.)

**Steps:**
1. Add sound file to `assets/sounds/general/` folder
2. Note: Adding files changes alphabetical indices! Update all existing index references.
3. Add helper function in `global_sound.py`:
   ```python
   def play_event_sound(use_queue=False):
       # EventName.mp3 at index X (check alphabetical order!)
       if use_queue:
           sound_manager.queue_sound('general', X)
       else:
           return sound_manager.play_specific('general', X)
   ```
4. Add trigger in appropriate game logic method (e.g., in the `game_state/` package):
   ```python
   # Play event sound for local player only
   should_play_sound = (owner == self.current_player)
   if self.network_mode and should_play_sound:
       should_play_sound = (self.current_player == self.local_player_index)

   if should_play_sound:
       from global_sound import play_event_sound, sound_manager
       # Check if higher priority sound is playing
       is_sound_playing = any(
           channel and channel.get_busy()
           for channel in sound_manager.currently_playing.values()
       )
       play_event_sound(use_queue=is_sound_playing)
   ```

**CRITICAL:** When adding files to `general` folder, update ALL index references:
- `play_ui_click()` - DefaultMouseClick.mp3 index
- `play_research_complete_sound()` - ResearchCompleted.mp3 index
- `play_castle_complete_sound()` - CastleCompleted.mp3 index

**Sound Priority System:**
Order of execution in `game_state/__init__.py` `end_turn()` determines priority:
```python
self.finish_research()         # Priority 1 (plays immediately)
self.finish_castle_upgrades()  # Priority 2 (queues if research playing)
self.finish_hero_training()    # Priority 3 (queues if anything playing)
```

#### ✅ Add UI Click Sound to New Menu

**Steps:**
1. Import sound manager:
   ```python
   from global_sound import sound_manager
   ```
2. Add to button click handlers:
   ```python
   if button_rect.collidepoint(pos):
       sound_manager.play_ui_click()
       # ... rest of button logic
   ```

**Files with UI click sounds:**
- `main_menu.py` - Main menu buttons
- `integrated_setup.py` - Setup screen interactions + territory map clicks
- `multiplayer_setup.py` - Multiplayer setup buttons (host/join/back, exit, join screen)
- `territory_selector.py` - Launch, return, dropdowns, territory map clicks
- `main.py` - In-game menu and options

#### ✅ Adjust Sound Volume

**Individual Sound:**
In `global_sound.py` `initialize_sounds()`:
```python
sounds = sound_manager.sound_categories['general']
sounds[2].set_volume(sound_manager.volume * 2.5)  # 2.5x louder
```

**Entire Category:**
```python
sound_manager.set_category_volume('general', 1.5)  # 1.5x master volume
```

**Volume Guidelines:**
- UI clicks: 2.0x (loud and punchy)
- Event notifications: 2.5x (very loud, celebration sounds)
- Background/ambient: 0.5-0.8x (subtle)
- Castle upgrades: 1.5x (moderate celebration)

### Sound Queue System

**How it works:**
1. `process_sound_queue()` called every frame in main game loop
2. Checks if any sound is currently playing
3. If nothing playing, pops first sound from queue and plays it
4. Sounds use `use_queue=True` parameter to queue instead of playing immediately

**When to use queuing:**
- Multiple events occurring simultaneously (research + hero finish)
- Want specific playback order (priority system)
- Prevent overlap of important sounds

**Example from the game_state package:**
```python
# Check if a sound is currently playing
is_sound_playing = any(
    channel and channel.get_busy()
    for channel in sound_manager.currently_playing.values()
)
# Queue if something is playing, otherwise play immediately
play_hero_recruit_sound(hero_type, use_queue=is_sound_playing)
```

### Player-Specific Sound Logic

**Always check ownership in multiplayer:**
```python
# Single-player check
should_play_sound = (owner == self.current_player)

# Multiplayer check (add this)
if self.network_mode and should_play_sound:
    should_play_sound = (self.current_player == self.local_player_index)

if should_play_sound:
    # Play sound
```

**Why:** In multiplayer, both players run the same game logic. Without this check, both players would hear all sounds (including opponent actions). This ensures only the player who performed the action hears the sound.

### Common Pitfalls

**❌ Not updating indices after adding sounds**
When adding a file to an existing category, alphabetical order changes! Example:
```python
# Before adding CastleCompleted.mp3:
# Index 0: DefaultMouseClick.mp3
# Index 1: ResearchCompleted.mp3

# After adding CastleCompleted.mp3:
# Index 0: CastleCompleted.mp3  ← NEW
# Index 1: DefaultMouseClick.mp3  ← SHIFTED
# Index 2: ResearchCompleted.mp3  ← SHIFTED

# Must update ALL existing references!
```

**❌ Forgetting player-specific checks**
Without multiplayer checks, opponent actions trigger sounds for local player.

**❌ Wrong priority order**
If `finish_hero_training()` runs before `finish_research()`, hero sound plays first and research gets skipped. Order matters!

**❌ Playing UI clicks during gameplay**
UI clicks should only play in menus, not for gameplay actions (selecting territories, moving armies, etc.)

---

## Testing Checklist

When making changes, test:

### Game Logic Changes
- [ ] Run with AI opponents (all difficulty levels)
- [ ] Test edge cases (0 armies, full territories, etc.)
- [ ] Verify no crashes or illegal moves
- [ ] Check balance (not too easy/hard)
- [ ] Run `pytest tests/test_ai_strategy.py` if available

### UI Changes
- [ ] Test at different resolutions (1600x900, 1920x1080)
- [ ] Test with different zoom levels
- [ ] Check click detection works correctly
- [ ] Verify no visual glitches or overlaps
- [ ] Test with different player counts (2-4)

### Network Changes
- [ ] Run `pytest tests/test_network_server.py`
- [ ] Test with two clients on same LAN
- [ ] Verify state synchronization
- [ ] Test disconnection/reconnection
- [ ] Check for race conditions

### Balance Changes
- [ ] Play 10+ turns with new values
- [ ] Test with AI at all difficulties
- [ ] Verify intended strategy is viable
- [ ] Check no dominant strategy emerged
- [ ] Update `QUICK_REFERENCE.md` with new values

---

## Campaign System

**What it does:** Scripted single-player campaign missions with cinematic sequences, custom AI behavior, and quest tracking
**Files:** `campaign_mission_*.py` (one per mission), `campaign_screen.py` (UI)
**Dependencies:** `game_state/` package, `map_data.py` (territory filtering)
**Used by:** `main.py` (launch handlers)

### Architecture

Campaign missions are self-contained modules that:
1. Filter territories to a subset of the map
2. Override display names for territories
3. Control AI behavior (dormant/awakened states)
4. Run cinematic intro sequences with camera animations
5. Track quest completion and victory conditions
6. Show narrative transmissions during gameplay

**Key Systems:**
- **Territory Filtering:** `map_data.set_enabled_territories()` limits visible territories
- **Display Names:** `map_data.set_territory_display_names()` renames territories for the mission
- **AI Control:** `block_ai` property prevents normal AI, mission handles turns (missions 2-7).
  Alternative (Tale I): leave `block_ai` False and restrict the built-in AI with
  `is_ai_target_allowed()` / `is_action_allowed()` / `ai_delay_scale` — see AI System.
- **Shared Utilities:** `campaign_utils.py` contains shared classes used by missions 2-4+:
  - `TransmissionOverlay` - narrative text overlay with speaker header
  - `CameraPanAnimation` - smooth camera pan between territories
  - `CameraZoomAnimation` - smooth camera zoom to a territory
  - `update_endgame_sequence()` / `render_endgame_sequence()` - victory/defeat animation helpers

### Mission Exit Contract (victory vs defeat)

`Game.run()` calls `mission.update(delta_time)` every frame ([main.py](../main.py),
in the `_is_tutorial_active()` block). The sentinel a mission returns decides whether
the **outro cutscene plays**, so victory and defeat must never share one:

| `mission.update()` returns | `Game.run()` returns | Outro cutscene | Recap |
|----------------------------|----------------------|----------------|-------|
| `None`                     | (keeps running)      | -              | -     |
| `'exit_campaign'`          | `'campaign'`         | **Yes**        | Yes   |
| `'exit_campaign_defeat'`   | `'campaign_defeat'`  | **No**         | Yes   |

**When adding a mission:** the defeat branch MUST return `'exit_campaign_defeat'`.
Returning `'exit_campaign'` from defeat is the bug that played the victory cinematic
to a player who had just lost (missions 2-7, fixed 2026-09-21). The victory branch
keeps `'exit_campaign'`.

The two outro call sites in [main.py](../main.py) both gate on
`game_result == 'campaign'` - one for a freshly launched mission, one in
`_launch_saved_game()` for a loaded save. Both are covered by
[tests/test_campaign_outro_cutscene.py](../tests/test_campaign_outro_cutscene.py),
which asserts the sentinels at the AST level across every mission file.

Everything *after* the cutscene block - `show_recap_if_ended()` (which also records
player XP and checks achievements), `map_data` cleanup, and the return to the campaign
screen - runs for both results. A defeat still shows the recap.

`tutorial_mission.py` (mission 1) has no defeat path at all, so it only ever returns
the victory sentinel.

### Files

- [campaign_utils.py](../campaign_utils.py) - Shared campaign utilities (TransmissionOverlay, camera animations, endgame sequences)
- [campaign_screen.py](../campaign_screen.py) - Campaign menu UI
- [tutorial_mission.py](../tutorial_mission.py) - Tutorial mission (Lobardia)
- [campaign_mission_2.py](../campaign_mission_2.py) - Early Eastern Conquests (9 territories, 4 players)
- [campaign_mission_3.py](../campaign_mission_3.py) - Storms above the West
- [campaign_mission_4.py](../campaign_mission_4.py) - Domination (21 territories, 4 factions, hybrid custom AI)
- [campaign_mission_5.py](../campaign_mission_5.py) - The First War (17 territories, 3 factions, allied team vs empire)
- [campaign_mission_6.py](../campaign_mission_6.py) - The Second War (33 territories, 3 factions, 4 sequential quests, dynamic AI)
- [campaign_mission_7.py](../campaign_mission_7.py) - The Fall (41 territories, 2 factions, garrison-enforced AI)
- [tale_lack_of_funds.py](../tale_lack_of_funds.py) - Book of Tales, Tale I (Azincournean Highlands, built-in AI + Popularity) — see "Tale I: Lack of Funds"
- [tale_final_breaths.py](../tale_final_breaths.py) - Book of Tales, Tale II (Mission 3 map, hold out 15 turns, capped + forced Kerunian attacks, Nordian Rebels) — see "Tale II: Final Breaths"
- `campaign_data.json` - Mission text data (edit with `Campaign_Text_Tool.py`)
- [cutscene_player.py](../cutscene_player.py) - Cutscene player (Ken Burns camera + crossfade + audio + subtitles)
- [Cutscene_Tool.py](../Cutscene_Tool.py) - Cutscene editor tool
- `cutscene_data.json` - Cutscene definitions per mission (edit with `Cutscene_Tool.py`)
- `assets/cutscenes/` - Cutscene background images and audio files

### Mission 2 Reference (campaign_mission_2.py)

**Territories:** Révia, Venexia, Valeonia, Velognia, The Holy Land, Lobardia, Elland, Lentria, Elletian Isles

**Players:**
- Player 0: Human (Green) - Lobardia
- Player 1: Elletic Tribes (Yellow) - 4 territories
- Player 2: Heilonic Tribes (Blue) - 2 territories
- Player 3: Chiefdom of Valeonia (Red) - 2 territories

**AI Behavior States:**
- `dormant` - AI does nothing, 3-second turns
- `awakened` - AI trains Swordsmen, attacks player 0 only

**Awakening Triggers:**
| Faction | Trigger |
|---------|---------|
| Elletic Tribes | Player has >10 armies in one territory OR attacks their territory |
| Heilonic Tribes | Elletic defeated OR player attacks their territory |
| Valeonia | Both Elletic AND Heilonic defeated OR player attacks their territory |
| All factions | Player attacks Valeonia (special cascade) |

### Mission 4 Reference (campaign_mission_4.py)

**Territories:** 21 territories (Aelatania through Venexia region)

**Players:**
- Player 0: Human (Blue) - Aelatania, Duchy of Daurels, Courtieux (3 territories)
- Player 1: Eastern Kingdoms (Green) - 9 territories
- Player 2: Confederation of the Leuse (Red) - 4 territories
- Player 3: Ahtep Empire (Yellow) - 5 territories

**AI Behavior:** Hybrid custom AI (not dormant/awakened pattern)
- All 3 AI factions attack only the human player, never each other
- **Ramp limit:** Turn N → max N attack orders + N reinforcement orders
- **Defensive minimums:** Eastern Kingdoms ≥1, Confederation ≥3, Ahtep Empire ≥5 units in border territories
- Continuously trains troops and builds structures
- 0.5s fast AI turns

**Special Features:**
- 7 territory display name overrides
- Pre-assigned hero: Regnus Aevencourne (Brennhen clone, `trainable: False`)
- Hero training icons hidden via `should_hide_hero_training()` method
- Flag remapping: Player 0→Blue, Player 1→Green, Player 2→Red, Player 3→Yellow
- Starting gold: 200g (human), 100g (EK), 250g (CotL), 5000g (Ahtep)

### When to Modify

#### Required Patterns (All Missions)

- **Cap `delta_time`:** Every `update()` method must start with `delta_time = min(delta_time, 0.05)`
- **Clean up in `deactivate()`:** Call `map_data.clear_enabled_territories()` to restore full map
- **try/finally for `current_player` swaps:** When temporarily changing `current_player` for AI actions, wrap in try/finally to restore on exception
- **Graceful exit:** Use `self._done = True` or result flags — never `pygame.quit(); sys.exit()`
- **Pass `speaker` to `TransmissionOverlay.set_text()`:** Both on creation and on reuse

#### ✅ Add New Campaign Mission

**Steps:**
1. Create `campaign_mission_N.py` based on `campaign_mission_2.py` template
   - Import shared utilities: `from campaign_utils import TransmissionOverlay, CameraPanAnimation, CameraZoomAnimation, update_endgame_sequence, render_endgame_sequence`
2. Define constants:
   ```python
   MISSION_N_TERRITORIES = ["Territory1", "Territory2", ...]
   MISSION_N_DISPLAY_NAMES = {"InternalName": "DisplayName", ...}
   TERRITORY_SETUP = {...}  # Initial units/buildings per territory
   ```
3. Create `MissionN` class with required methods:
   - `__init__()` - Setup territory filtering, initial state
   - `update(delta_time)` - Frame update, returns 'exit_campaign' when done
   - `update_ai_turn(delta_time)` - AI turn handling
   - `render(screen)` - Draw mission overlays
   - `is_action_allowed(action_type, **kwargs)` - Gate player actions
   - `notify_event(event_type, **kwargs)` - Receive game events
   - `_cleanup()` - Restore state on exit
4. Add launch handler in `main.py` (~line 12650):
   ```python
   elif launched_mission == 'mission_N':
       from campaign_mission_N import MissionN, MISSION_N_TERRITORIES, MISSION_N_DISPLAY_NAMES
       map_data.set_enabled_territories(MISSION_N_TERRITORIES)
       map_data.set_territory_display_names(MISSION_N_DISPLAY_NAMES)
       # ... initialize game state
       game.campaign_mission = MissionN(game.game_state, game)
   ```
5. Add mission button to `campaign_screen.py`

#### ✅ Add Cinematic Intro Sequence

**In your mission class:**
```python
INTRO_SEQUENCE = [
    ("zoom_to", "StartTerritory", ""),           # Zoom camera
    ("wait", 6.0, "Narrative text here"),        # Show text for 6 seconds
    ("show_timer", 8.0, "Timer explanation"),    # Show timer bar + text
    ("pan_to", "OtherTerritory", ""),            # Pan camera
    ("wait", 5.0, "More narrative"),
    ("start_game", 0, ""),                       # End intro, begin gameplay
]
```

#### ✅ Add Pre/Post-Mission Cutscene

**Overview:** Cutscenes play before mission start (intro) and after victory (outro). Authored via `Cutscene_Tool.py`, stored in `cutscene_data.json`.

**Steps:**
1. Place background images in `assets/cutscenes/` (any resolution, larger = more pan range)
2. Place audio files in `assets/cutscenes/` (.mp3, .wav, .ogg)
3. Run `python Cutscene_Tool.py` to open the editor
4. Select the cutscene ID (e.g. `mission_2_intro`) from the top bar
5. Click "+" to add slides, "Load Image" to set background
6. Drag camera rects A (blue) and B (red) to set start/end viewports
7. Set pan duration, crossfade, easing, audio, subtitle in the right panel
8. Click "Preview" (or P key) to test
9. Save with Ctrl+S

**Data format (cutscene_data.json):**
```json
{
  "mission_1_intro": {
    "slides": [{
      "image": "assets/cutscenes/bg.png",
      "camera_a": {"x": 200, "y": 100, "width": 800, "height": 450, "rotation": 0},
      "camera_b": {"x": 600, "y": 300, "width": 1200, "height": 675, "rotation": 0},
      "pan_duration": 8.0,
      "crossfade_duration": 0,
      "easing": "ease_in_out",
      "audio": "assets/cutscenes/voice.mp3",
      "audio_volume": 1.0,
      "audio_start_delay": 0.5,
      "music": "assets/cutscenes/bg_music.mp3",
      "music_volume": 0.4,
      "music_start_delay": 0.0,
      "subtitle": "Narration text here..."
    }]
  }
}
```

**Dual-track audio:** Each slide has independent voice (`audio`) and music (`music`) channels with separate volume and delay. Music persists across slides if the same file path is used (no restart); crossfades when the track changes; fades out if the next slide has no music.

**Integration:** Automatic. `main.py` checks for `{mission_id}_intro` and `{mission_id}_outro` keys. If present, cutscene plays; if absent, no-op.

**Player controls:** ESC or left-click to skip (0.5s fade-to-black).

**MP4 Export:** Click "Export MP4" in Cutscene_Tool.py to export the selected cutscene as a video file. Options: include/exclude subtitles, include/exclude audio. Export uses [cutscene_exporter.py](../cutscene_exporter.py) which renders frames offscreen and pipes to ffmpeg (bundled via `imageio-ffmpeg`). Two-pass: silent video first, then audio muxing via ffmpeg `filter_complex`.

#### ✅ Add AI Awakening Trigger

**In `_awaken_faction()` method:**
```python
def _awaken_faction(self, faction_id, reason):
    if self.faction_awakened.get(faction_id, False):
        return
    self.faction_awakened[faction_id] = True

    # Custom transmission per faction/reason
    if faction_id == 1 and reason == 'attack':
        self._queue_transmission("They declared war!", 5.0)
```

#### ✅ Add Quest Tracking

**In `__init__()`:**
```python
self.quest_log = [
    {'text': 'Defeat Faction A', 'completed': False},
    {'text': 'Capture Territory X', 'completed': False},
]
```

**In event handlers:**
```python
def _on_faction_defeated(self, faction_id):
    self.quest_log[faction_id - 1]['completed'] = True
```

#### ✅ Gate Player Actions

**In `is_action_allowed()`:**
```python
def is_action_allowed(self, action_type, **kwargs):
    if action_type == 'build' and kwargs.get('building_type') == 'Keep':
        return False  # Disable Keep building
    if action_type == 'sidebar_tab' and kwargs.get('tab_name') == 'heroes':
        return False  # Hide Heroes tab
    if action_type == 'toggle_sidebar':
        return False  # Keep the right sidebar open (the tutorial does this)
    return True
```

### Campaign Transmission Voice Lines

**Naming:** `T{N}.mp3` for Mission 1, `M{X}T{N}.mp3` for Mission 2+, and for Book of Tales
`T{tale}T{N}.mp3` plus named lines (Tale I: `T1T1`-`T1T3`, `T1Revolt`, `T1TWin`, `T1TLoss`;
Tale II: `T2T1`-`T2T3`, `T2R1`, `T2R+`, `T2W`, `T2L`).
`global_sound.get_transmission_length(key)` returns a loaded line's length (0.0 if missing);
Tale II keeps each line on screen for `max(duration, length)`, because the text expiring
stops the voice.
Placed in `assets/sounds/transmissions/`. Loaded by `global_sound.load_transmission_sounds()`
using filename stem as key (only for games with a `campaign_map`, which tales have).

**Global features (main.py / global_sound.py — no per-mission work needed):**
- `play_transmission_sound(key)` auto-stops any previous voice before playing new one
- `_pause_game()` calls `pause_transmission_sound()` — voice pauses when game menu opens
- `_unpause_game()` calls `unpause_transmission_sound()` — voice resumes when game menu closes
- "Quit to Main Menu" button calls `stop_transmission_sound()` — voice stops on exit
- **ESC skips visible transmission** — `main.py` intercepts ESC in 3 event-loop locations (camera-locked, AI turns, general KEYDOWN) and calls `mission.skip_transmission()`. If a transmission was visible, it's dismissed and the voice stops; otherwise ESC falls through to normal game menu toggle.

**Per-mission voice requirements checklist:**

1. **Define `INTRO_STEP_TO_VOICE`** — dict mapping intro step indices to voice keys (e.g. `{1: "M3T1", 2: "M3T2"}`)
2. **`_execute_intro_step()`** — after `_show_transmission(text)`, look up voice key and call `play_transmission_sound(key)`. On `pan_to` steps, call `stop_transmission_sound()`. On `wait` steps with no text, call `stop_transmission_sound()`.
3. **`__init__`** — add `self._intro_pause_timer = 0.0`
4. **`update()` intro pause block** — before intro timing, check `_intro_pause_timer > 0`. Decrement by delta_time, advance to next step when expired. Return early during pause (1s silent gap between consecutive voiced intro steps).
5. **`update()` intro timer expiry** — when intro step timer expires and next step has text: call `stop_transmission_sound()`, clear overlay, set `_intro_pause_timer = 1.0`. Otherwise advance immediately.
6. **`_queue_transmission(text, duration, voice_key=None)`** — accept optional voice key, store `(text, duration, voice_key)` tuples in queue.
7. **`_start_pending_transmission()`** — unpack voice_key from tuple, call `play_transmission_sound(key)` if present.
8. **`update()` gameplay transmission timer expiry** — call `stop_transmission_sound()` when text expires.
9. **Gameplay transmissions gate on `_is_gameplay_idle()`** — no battle popup, no turn announcement, `turn_phase == 'planning'` or `phase == 'ended'`.
10. **Victory/defeat** — call `play_transmission_sound()` directly alongside `_show_transmission()` for victory/defeat voice lines.
11. **`_end_intro_sequence()`** — call `stop_transmission_sound()` to stop any lingering intro voice.
12. **`_cleanup()`** — call `stop_transmission_sound()` to stop voice on mission exit.
13. **`skip_transmission()`** — ESC-to-skip method. Hides overlay, stops voice, advances to next step (intro) or resets timer (gameplay). For tutorial event-driven steps (duration=0), only hides overlay without advancing. Returns True if skipped, False otherwise. Called from `main.py` ESC handlers.

**Implemented in:** All 4 missions — Mission 1 (`tutorial_mission.py`), Mission 2 (`campaign_mission_2.py`), Mission 3 (`campaign_mission_3.py`), Mission 4 (`campaign_mission_4.py`). Tale I (`tale_lack_of_funds.py`) follows the same checklist with a data-driven variant: `INTRO_SEQUENCE` entries carry their own `(speaker, text, voice_key, duration)` and queued lines are `(speaker, text, voice_key, duration)` tuples.

### Testing Checklist

- [ ] Territory filtering works (only mission territories visible)
- [ ] Display names show correctly in tooltips
- [ ] Intro sequence plays with correct timing
- [ ] Camera animations smooth
- [ ] AI starts dormant, awakens on triggers
- [ ] Awakened AI attacks player only (not other AI)
- [ ] Transmissions appear at correct times
- [ ] Transmissions wait for battle report to close
- [ ] Quests mark complete when conditions met
- [ ] Victory sequence plays when all quests done
- [ ] Flag icons match player colors
- [ ] Defeated AI turns are skipped
- [ ] Clean exit restores normal game state
- [ ] Voice plays with each transmission
- [ ] Voice pauses on game menu open, resumes on close
- [ ] Voice stops on mission exit / quit to menu
- [ ] 1s silent gap between consecutive voiced intro steps
- [ ] Voice stops on camera pan during intro
- [ ] ESC skips visible transmission and stops voice
- [ ] ESC opens game menu when no transmission visible
- [ ] Tutorial event-driven steps: ESC hides text but doesn't advance step

---

## Achievement System

**Files:** `achievement_manager.py` (definitions, logic), `achievement_panel.py` (UI helper), `steam_integration.py` (Steam sync)
**Integration:** `main_menu.py` (button/panel/profile), `recap_screen.py` (preview popup), `main.py` (post-game hook), `settings_manager.py` (persistence)

**Architecture:** Singleton `AchievementManager` owns all definitions and stat tracking. `AchievementPanel` is a UI helper class created by `MainMenu` to render panel content. Achievement data persisted to `config.json` via `settings_manager`.

**Steam integration:** `steam_integration.py` provides `SteamManager` singleton. On startup: `initialize()` calls `SteamInit()` + `RequestCurrentStats()`, then `pump_until_stats_ready()` waits for stats callback before `sync_to_steam()`. Achievement IDs are encoded to bytes before passing to SteamworksPy (no argtypes on achievement methods). Steam persona name auto-updates `settings.player_name` on startup; profile panel shows "(Steam)" indicator and disables name editing when Steam is active. **Friend invites:** `can_invite()` checks Steam is initialized, `get_online_friends()` enumerates friends via `GetFriendCount`/`GetFriendByIndex`/`GetFriendPersonaName`, `invite_friend(steam_id, connect_string)` sends invite via `InviteFriend` with host IP:port. Invited friends receive Steam notification; accepting launches game with `+connect ip:port` arg.

**Data flow:** Game ends → `show_recap_if_ended()` → `achievement_manager.record_game_result(game)` → detects mode, increments stats, checks thresholds → returns newly earned list → `RecapScreen` shows preview popups → user returns to main menu → achievement panel shows all achievements. Campaign missions set `gs.winner = 0` and `gs.phase = 'ended'` in their `_start_victory` method to trigger this flow.

**Achievement definitions:** Hardcoded in `ACHIEVEMENTS` list in `achievement_manager.py`. Each has id, name, description, category, icon path, reward_type (None/title/icon), reward_id, stat_key, stat_threshold. Dual-reward achievements use optional `reward_type_2`/`reward_id_2` fields.

**Categories:** general, campaign, training, conquest. Defined in `CATEGORIES` list.

**Reward types:** `'title'` (shown in profile dropdown), `'icon'` (selectable in profile icon grid). `ALL_TITLES` and `ALL_REWARD_ICON_PATHS` lists define all possible rewards. Dual rewards supported via `reward_type_2`/`reward_id_2` — lookups and UI handle both slots automatically.

### When to Modify

- **Add new achievement**: Add dict to `ACHIEVEMENTS` list in `achievement_manager.py`. If it uses a new stat_key, ensure the stat is incremented in `record_game_result()`.
- **Add new category**: Add to `CATEGORIES` and `CATEGORY_LABELS` in `achievement_manager.py`.
- **Add new reward icon**: Add icon file to `assets/achievements/RewardsIcons/`, add path to `ALL_REWARD_ICON_PATHS` in `achievement_manager.py`.
- **Add new stat trigger**: Extend `record_game_result()` in `achievement_manager.py` to increment the new stat based on game conditions.
- **Add campaign bonus achievement**: Add tracking flag in mission `__init__`, update the flag in existing event handlers (e.g., `_check_attack_awakening`, `_on_faction_defeated`), expose via `get_bonus_conditions()`. Stats are bridged to `achievement_manager` automatically by `record_game_result()`.
- **Change achievement panel layout**: Modify `achievement_panel.py` draw methods.
- **Change preview popup**: Modify `_draw_achievement_preview()` / `_update_achievement_preview()` in `recap_screen.py`.
- **Change profile title/icon UI**: Modify `_draw_profile_panel()` in `main_menu.py`.
- **Change Steam achievement sync**: Modify `steam_integration.py` (`unlock_achievement`, `pump_until_stats_ready`). Achievement IDs must be bytes-encoded.
- **Change Steam friend invites**: Modify `steam_integration.py` (`can_invite`, `get_online_friends`, `invite_friend`). Friend picker UI in `network/territory_selector.py` (`_draw_friend_picker`, `_handle_friend_picker_click`). Auto-connect via `+connect` launch param handled in `main.py` (`steam_invite_join` action).
- **Change Steam name behavior**: Modify `_open_profile()` in `main_menu.py` (detection) and `_draw_profile_panel()` (UI). Startup auto-set in `main.py`.

## Recap Screen

`recap_screen.py` - Post-game statistics screen shown after every game ends (custom, campaign, multiplayer).

**Architecture:** Modeled on `MissionScreen` in `campaign_screen.py` (same background, tab buttons, content panel).

**Stat Tracking:** The game_state package has `player_stats` dict (init in `__init__`), incremented via `_track_stat()` at 13 hook points across training, combat, construction, income, and research methods. `get_end_game_stats()` packages stats with calculated `territories_owned`.

**Integration:** `main.py` calls `show_recap_if_ended(game)` after each `game.run()` at 5 sites (custom, 3 campaign missions, multiplayer).

### When to Modify

- **Add new stat column**: Add to `TAB_COLUMNS` in `recap_screen.py`, add tracking hook in `game_state/__init__.py` (init in `player_stats` + increment via `_track_stat`)
- **Add new tab**: Add to `TABS`, `TAB_LABELS`, `TAB_COLUMNS` in `recap_screen.py`
- **Change table layout**: Modify `_draw_table()` in `recap_screen.py`

## Loading Screen

`loading_screen.py` - Loading screen shown between setup and gameplay. Defers game asset loading (sounds, images, fonts) to after menu/setup for faster startup.

**Architecture:** `LoadingScreen(screen, game, setup_config, network_connection)` builds a task list from `get_game_sound_tasks()` (11 sound categories) + `game.initialize_game()` (images, fonts, GameState). Renders progress bar at 30 FPS, then waits for player input.

**Sound Split:** `global_sound.py` provides `initialize_menu_sounds()` (3 files, called at startup) and `get_game_sound_tasks()` (136 files, deferred to loading screen).

**Multiplayer Sync:** Uses `GAME_READY` message type (`network_config.py`). Host collects GAME_READY from all clients, then broadcasts confirmation. Both sides wait for "click to start" after all ready.

### When to Modify

- **Add new deferred sound category**: Add entry in `get_game_sound_tasks()` in `global_sound.py`
- **Change loading screen visuals**: Modify `_draw()` in `loading_screen.py`
- **Add new loading task**: Append to `_build_task_list()` in `loading_screen.py`
- **Change multiplayer sync logic**: Modify `_send_game_ready()` / `_poll_network_ready()` in `loading_screen.py`

## Player Level System

**Files:** `player_level.py` (logic), `settings_manager.py` (persistence), `main_menu.py` (profile UI), `recap_screen.py` (recap UI)

The player level system tracks persistent XP across games. XP is accumulated during gameplay via `_track_stat(player, 'xp_earned', amount)` hooks in `game_state/buildings.py`, `heroes.py`, and `military.py`. At game end, `player_level_manager.record_game_xp(game)` reads the accumulated stat, applies eligibility checks, halving, and end-of-game bonuses, then persists via `settings_manager`.

**Architecture:**
- `player_level.py`: Singleton `PlayerLevelManager`, tiered XP formula (`XP_TIERS`), `xp_for_level()`/`level_from_xp()` conversion, `record_game_xp()` end-of-game calculation
- `game_state/`: 10 hook sites use `_track_stat(player, 'xp_earned', amount)` — stats tracked for all players, only human player's read at game end
- `main_menu.py`: Gold-filled level bar in profile panel (to the right of name input)
- `recap_screen.py`: Animated XP bar after achievement popups with level-up particle burst

### When to Modify

- **Change XP amounts per action**: Edit constants in `player_level.py` (`XP_UNIT_TRAINED`, `XP_BUILDING_BUILT`, etc.)
- **Change level progression formula**: Edit `XP_TIERS` list in `player_level.py`
- **Add new XP-granting action**: Add `self._track_stat(player_index, 'xp_earned', amount)` at the event site in `game_state/`
- **Change end-of-game bonuses**: Edit `_calculate_end_bonus()` in `player_level.py`
- **Change eligibility/halving rules**: Edit `_has_enemy_player()` / `_should_halve()` in `player_level.py`
- **Change profile level bar appearance**: Edit `_draw_profile_panel()` in `main_menu.py`
- **Change recap XP bar animation**: Edit `_update_xp_bar()` / `_draw_xp_bar()` in `recap_screen.py`

## Version Info

**Last Updated:** February 2026
**Codebase Size:** ~30,000 lines
**For questions:** See `DEVELOPMENT_GUIDE.md` or ask in project channel

**Related Documentation:**
- `GAME_MECHANICS.md` - Detailed game rules
- `ARCHITECTURE.md` - System design patterns
- `QUICK_REFERENCE.md` - Values and constants
- `DEVELOPMENT_GUIDE.md` - Development workflows
- `USER_STORIES_PROGRESS.md` - Feature status

## Replay System

**Files:** `replay_recorder.py` (recording), `replay_viewer.py` (viewer), `replay_browser.py` (browser)
**Integration:** `game_state/__init__.py` (snapshot hook), `simultaneous/sim_state.py` (sim mode hook), `main.py` (attach recorder + browser/viewer routing), `recap_screen.py` (Save Replay button), `main_menu.py` (Replays button)

**When to modify:**
- Add new game state fields → update `replay_recorder.py` `_serialize_state()` to include the new field
- Change movement order format → update `_serialize_state()` movement_orders section
- Add new event types → use `replay_recorder.buffer_event()` from the relevant game_state mixin
- Change replay viewer UI → modify `replay_viewer.py` `_render_*()` methods
- Change replay **browser** UI → see [Browser Screens](#browser-screens-saved-games--replays); `replay_browser.py` shares its layout with `save_browser.py`, so change both
- Change replay file format → increment `version` field in `finalize_and_save()`, handle migration in `load_replay()`

**Architecture notes:**
- State Snapshot approach: records full GameState at turn boundaries (not action replay)
- Snapshots stored in memory during gameplay, saved to disk on user request from Recap screen
- Replay files: gzip-compressed JSON in `Replays/` folder
- Viewer is standalone (own rendering, no MapRenderer/UIRenderer dependency)
- Zero FPS impact: snapshot runs once per turn boundary via `_advance_to_next_player()` hook

## Campaign Save System

**Files:** `save_manager.py` (serialize/deserialize/IO), `save_browser.py` (browser UI)
**Integration:** `rendering/ui_renderer.py` (Save button + dialog), `main.py` (click handling + load flow), `campaign_screen.py` (Saved Games button), `campaign_mission_2-7.py` (get_save_state/restore_save_state)

**When to modify:**
- Add new game state fields → update `save_manager.py` `serialize_game_state()` AND `deserialize_game_state()` (must handle both directions + type conversions)
- Add new campaign mission → add `get_save_state()` / `restore_save_state()` methods, add entry to `_SAVE_MISSION_REGISTRY` in main.py and `_MISSION_TEXTS` in save_manager.py
- Change mission-specific state → update the mission's `get_save_state()` / `restore_save_state()` methods
- Change save browser UI → see [Browser Screens](#browser-screens-saved-games--replays); `save_browser.py` shares its layout with `replay_browser.py`, so change both
- Change save file format → increment `SAVE_VERSION` in save_manager.py

**Architecture notes:**
- Serialization pattern mirrors `replay_recorder._serialize_state()` plus config/eliminated players
- Each mission class owns its own state via `get_save_state()` / `restore_save_state()`
- Load flow: LoadingScreen initializes fresh GameState → `deserialize_game_state()` overwrites → mission constructor → `restore_save_state()`
- Tutorial (Mission 1) save is disabled (too complex to serialize step machine)
- Save disabled during: AI turns, intro sequences, victory/defeat sequences
- Save files: gzip-compressed JSON in `Saves/` folder
- Atomic writes via tempfile + os.replace()

## Browser Screens (Saved Games / Replays)

**Files:** `save_browser.py` (`SaveBrowser`), `replay_browser.py` (`ReplayBrowser`)
**Shared helpers:** `utils/surface_utils.py` — `load_cached_image()`, `get_campaign_button_image()`, `crop_to_opaque()`
**Integration:** `main.py` constructs each fresh on every open and blocks on `run()`

These two screens are deliberate near-duplicates — the same list-inside-an-ornate-frame
layout with different columns. **Change one, change the other.**

### House style

Both follow the campaign pattern shared with `campaign_screen.MissionScreen` and
`recap_screen.RecapScreen`:

| Element | Asset / value |
|---|---|
| Background | `assets/CampaignBG.png`, smoothscaled full screen, **no dim overlay** |
| Panel | `assets/OptionsMenuBG.png`, darkened with `fill((100,100,100,255), BLEND_RGBA_MULT)` |
| Buttons | `assets/CampaignBTN.png`, cropped to opaque bounds (1502x297, aspect ~0.1977) |
| Title | `TITLE_BROWN = (80, 50, 20)` — matches `CampaignScreen`'s "Campaign" title |
| Headers, primary label | `BRASS_COLOR = (181, 166, 66)` |
| Fonts | `Cinzel-Regular` / `Cinzel-SemiBold` loaded directly via `pygame.font.Font` |

- **Do not darken the background.** The title is dark brown because it sits on the light
  parchment band of `CampaignBG.png`; a dim overlay makes it unreadable.
- **Do not route fonts through `config/font_manager.py`.** It remaps weights one step
  bolder (`regular`→SemiBold), which breaks the match with the campaign screens.
- The primary action (Load / Watch) gets a brass label, mirroring "Launch Chapter"; the
  other buttons are white, and disabled ones use `DIM_TEXT`.

### Geometry contract

`rows_rect` is the single source of truth for hit-testing, clipping and scroll bounds. It
starts *below* the header divider, so hover mapping needs no header allowance.

- `content_w = rows_rect.width - scroll_gutter`. Columns and row backgrounds use
  `content_w`; only the scroll indicator may use the gutter.
- Columns are `(label, start_fraction, end_fraction, alignment)` **fractions of
  `content_w`**, never absolute pixels, so they stay proportional on ultrawide.
- Inner panel padding is asymmetric (`215 / 230 / 150 / 145` x `ui_scale`, L/R/T/B)
  because the carved border of `OptionsMenuBG.png` is wider on the left. These are tuned
  by eye against a rendered frame — **if you change the panel rect, re-check them**, or
  content will sit on the border.
- The confirm dialog uses **fractional** padding, not `N * ui_scale`. The border's
  on-screen thickness scales with the panel it is drawn into, so a 660-wide dialog needs
  ~16% padding, not the panel's ~215 px. Its size keeps the frame's native 1979x1503
  aspect so the border is not distorted.

### Rules that keep it correct

- **`max_scroll` is never assigned from the render path.** Call
  `_recompute_scroll_bounds()` from `__init__` and after a delete. It used to be a render
  side effect, so it lagged a frame and stayed `0` for an empty list.
- **Clip rows to `rows_rect`**, or scrolled rows paint over the column header.
- **`_confirm_dialog_rects()` is the only place dialog geometry is computed.** Both the
  click handler and the renderer call it. Duplicating the maths silently breaks
  hit-testing the next time the look changes — which is exactly what happened before.
- **Never build surfaces per frame.** Panel, dialog, row backgrounds and tinted buttons
  are pre-built in `__init__` or cached by size. `smoothscale` should appear only in
  `__init__` and in `_btn_surface()`'s cache-miss branch — that is the acceptance check.
- **Assets are decoded once per process** via `load_cached_image()`. Both browsers are
  rebuilt on every open, and `ReplayBrowser` is rebuilt every time the viewer exits, so
  re-opening must stay cheap (~29 ms). `crop_to_opaque()` uses
  `Surface.get_bounding_rect()`, not a per-pixel scan — the old version cost 276 ms.
- Every asset load has a `None` fallback path. `main.py` has no `try` around
  `browser.run()`, so an uncaught error takes down the campaign loop, not just the screen.

### Behaviour contract (do not break)

`main.py` consumes these result dicts and nothing else:

- `SaveBrowser` → `{'action': 'load', 'path': str, 'save_data': dict}` / `{'action': 'back'}` / `{'action': 'quit'}`
- `ReplayBrowser` → `{'action': 'watch', 'path': str}` / `{'action': 'back'}` / `{'action': 'quit'}`

Also preserve: `_MUSIC_END_EVENT` forwarding (menu music stops between tracks without it),
`sound_manager.play_ui_click()` on every actionable click, `draw_custom_cursor()` as the
**last** blit before `flip()`, click-to-select then click-again-to-open, ESC = back (or
close the dialog only), RETURN = open, and wheel scrolling via legacy buttons 4/5.

### Where the two differ

| | `SaveBrowser` | `ReplayBrowser` |
|---|---|---|
| Title | "Saved Games" | "Replays" |
| Columns | Mission, Save Name, Date, Turn | Date, Players, Turns, Winner, Duration |
| Rows | single line, `row_height = 64 * s` | two lines (+ `mode - victory` sub-line), `78 * s` |
| Buttons | Return / Delete / **Load** | Back / Delete / **Watch** |
| List source | `save_manager.scan_saves()` | `ReplayBrowser._scan_replays()` |

## Book of Tales Screen

**File:** `book_of_tales.py` (`BookOfTales`)
**Launched from:** the square icon button in the **bottom-right** corner of `CampaignScreen`
(mirror of Saved Games in the bottom-left). `CampaignScreen.run()` returns the sentinel
`'book_of_tales'`, and `main.py`'s campaign loop runs a small loop: open `BookOfTales`,
run the launched tale, reopen `BookOfTales`; Return/ESC goes back to the Campaign screen.

- **Adding or editing tales:** edit the module-level `SCENARIOS` list (`id`, `name`,
  `description`, optional `'hidden': True` to keep a tale off the list). Buttons keep fixed
  slots from the top and paginate automatically (triangle arrows under the column) once the
  list outgrows the column.
- **Description markup** (parsed by the static `_wrap_text()`, which returns
  `(text, underlined, indent_px)` tuples — use index access, the format may grow):
  - `'\n'` is a line break, `'\n\n'` an empty line;
  - a leading `'_'` draws the line underlined (headings like "Objectives:"), via a separate
    `body_font_underline` instance — `set_underline()` mutates the Font, so never call it on
    the shared `body_font`;
  - a line starting with `'- '` is a list item whose wrapped lines get a hanging indent.
- **Launching:** `_launch_selected()` sets `{'action': 'launch', 'scenario_id': id}` and closes
  the screen. `main.py` looks the id up in **`_TALE_REGISTRY`** (defined next to
  `_launch_saved_game()`, same shape as the campaign `_MISSION_REGISTRY`: `import`, `map`,
  `config`, plus `map_id`) and runs it through **`_run_registered_mission()`** — the helper the
  campaign loop also uses (intro cutscene → `LoadingScreen` → mission → `game.run()` → outro on
  victory → recap → cleanup). To add a tale: a `SCENARIOS` entry + a `_TALE_REGISTRY` entry +
  its mission module; saves work automatically because `_launch_saved_game()` merges
  `_TALE_REGISTRY` into its registry (and passes `map_id` through — non-Avareon geometry).
  Add a `save_manager._MISSION_TEXTS` label too.
- **Results:** `{'action': 'back'}` / `{'action': 'quit'}` / `{'action': 'launch', 'scenario_id': ...}`.
- **Description scrolling:** mouse wheel (buttons 4/5) over the panel scrolls the body by one
  line; the heading and divider stay fixed. Wrapping and `desc_max_scroll` are computed in
  `_select_tale()` only, never from render. Select tales through `_select_tale()`, not by
  setting `selected_index` directly, or the description stays empty.
- **Look:** background `BookOfTalesBG.png`; description panel `IGOptMenuBG.png` (not darkened;
  text padding is a *fraction* of the panel because the frame is stretched); tale buttons are
  the cropped `CampaignBTN.png` with the Campaign mission-button tints, plus MissionScreen's
  brighter base (x140) and a brass outline traced from the art's alpha mask (cached per size
  in `_outline_cache`) for the selected tale. The title is white (`TITLE_COLOR`), not the Campaign
  title's brown: brown is unreadable on this background's dark vault. Return / Launch copy SaveBrowser's Return / Load
  geometry and `_btn_surface` / `_render_btn` tint states; Launch is disabled (no hover, no
  click, dim label) until a tale is selected.
- **Campaign screen corner buttons** share `CampaignScreen._draw_icon_button(rect, icon,
  btn_id, tooltip)`. Change hover/flash/border there so both stay identical.
  `BTNBookOfTales.png` is 3:2, so it is centre-cropped to a square at load, not squashed.

## Tale I: Lack of Funds (`tale_lack_of_funds.py`)

**First Book of Tales scenario** (`mission_id = 'tale_1'`, class `TaleLackOfFunds`). It follows
the campaign mission interface (update / render / notify_event / is_action_allowed /
get_quest_log / get_save_state / restore_save_state), but differs from missions 2-7 in three
ways worth knowing before copying it:

1. **Non-Avareon map.** It plays on the Azincournean Highlands. The map is chosen by
   `'map_id': 'azincournean_highlands'` in the `_TALE_REGISTRY` config (read by
   `Game.initialize_game()`), with `'map': 'maps/azincournean_highlands/map.png'` as the
   `campaign_map` image. All 55 territories stay enabled; the 13 unassigned ones are neutral
   with one random unit each (`gs.set_garrison_armies(t, -1, ...)`).
2. **Built-in AI, restricted by hooks** instead of a scripted AI. `block_ai` is `False` and
   `update_ai_turn()` does nothing, so `ai_player` plays (and resolves its own battles) at the
   registry difficulties (Yellow Medium, Green/Red Hard). The rules live in
   **`is_ai_target_allowed(attacker, territory)`** (see AI System → mission hooks):
   AI factions never target each other; Red/Green never take neutral land and attack the
   player only after `hostile[faction]` flips (on an `order_created` notify from the player
   against that faction); Yellow targets nothing for its first `YELLOW_NO_ATTACK_TURNS` (3).
   Yellow's Barracks training is blocked for `YELLOW_NO_TRAINING_TURNS` (2) through
   `is_action_allowed('train')`, which `start_training()` queries for every player.
   `faction_turns` counts AI turns on `turn_announcement_done`. `ai_delay_scale = 0.0` removes
   the AI's readability pauses, and `update()` completes AI turn announcements instantly
   (as missions 5-7 do), so AI turns take ~0.5-1.5 s.
3. **Popularity** — a Tale-only mechanic (rules in GAME_MECHANICS.md, numbers in
   QUICK_REFERENCE.md). All tuning is in the `POPULARITY` / `REVOLT_*` constants at the top.
   - `_on_player_turn_start()` (from `turn_announcement_done` for player 0) rolls the revolt
     **before** applying the drop, guarded by `_last_decay_turn` (one roll + drop per
     `gs.turn_number`; turn 0 skipped).
   - `_revolt_territory()` hands a territory to Yellow with its units and buildings: cancels
     the player's orders touching it, moves the garrison unit-for-unit, bumps
     `_territory_owners_version` and invalidates income / army-count / bonus caches (the same
     set a conquest does). It does **not** fire `territory_conquered` or create a Battle Report.
   - The widget (label + `BattleBar.png` frame + `CampaignBTN.png` "Invest N Gold" button) is
     drawn in `render()`; its layout is rebuilt only when the screen size, `ui_scale`, map
     bottom or chat-box state changes (`_widget_key`). The bar value eases
     (`_display_popularity`) so drops visibly drain. Clicks arrive through the generic
     `handle_click()` hook (mouse_handler Priority 4.5); the flash uses
     `main.trigger_click_flash('tale_button', 'invest')`.
- **No Hero training for the player:** `should_hide_hero_training()` + `is_action_allowed('train_hero')`
  for player 0 only.
- **Intro / transmissions:** `INTRO_SEQUENCE` (zoom to Generax, then T1T1-T1T3) runs in
  `_update_intro()` with gameplay paused; `transmission_queue` holds gameplay lines (T1Revolt)
  until `_is_gameplay_idle()`. Victory/defeat play T1TWin / T1TLoss, then the shared
  `campaign_utils` endgame sequence. `restore_save_state()` never replays the intro.
- **Randomised setup** (buildings, scattered units, neutral guards) uses `self.rng`; tests pass
  a seeded `random.Random`.
- **Victory** = Yellow owns nothing (`'exit_campaign'`); **defeat** = Generax conquered
  (`'exit_campaign_defeat'`). The achievement `campaign_tale_1` comes from the generic
  `campaign_{mission_id}_completed` stat.
- **Tests:** `tests/test_tale_lack_of_funds.py` (a real Game on the Highlands; conftest reloads
  Avareon before every test, so the module re-loads its map in an autouse fixture).

## Tale II: Final Breaths (`tale_final_breaths.py`)

**Second Book of Tales scenario** (`mission_id = 'tale_2'`, class `TaleFinalBreaths`). Same
interface and structure as Tale I (copy from either); what is different:

1. **Map:** Avareon geometry (`'map_id': 'avareon'`) with Campaign Mission 3's background
   (`assets/CampaignMaps/Campaign3Map.png`) and territory set — the Tale calls
   `map_data.set_enabled_territories(MISSION_3_TERRITORIES)` (imported from
   `campaign_mission_3.py`) and clears it in `_cleanup()`. 3 players, all on separate teams.
   Mission 3's five extra territories (Zjoal Islands, Leimarch, Liadnon, Ahtep, Anodia) are
   neutral and empty.
2. **Setup** (`_setup_initial_state()`): Keeps on plot 0 of `KEEP_TERRITORIES`, Lunedale's
   upgraded to a Castle (`gs.castle_upgrades['Lunedale'] = {0: True}`); every other plot of
   each faction is filled from `BUILD_MIX` with Tale I's `allocate_building_counts()`
   (largest remainder, `None` = empty plot). Each army = 1 Captain + random basic units
   (sizes from `LARGE/MEDIUM_ARMY_TERRITORIES` / `DEFAULT_ARMY_SIZE`).
   - **Pre-researched techs** go through `GameState.apply_tech_effect(player, tech,
     announce=False)` — the effect chain extracted from `finish_research()`. Never set the
     tech attributes by hand (missions 5/7 do, and missed some); then add the next row of
     each column to `player_tech_available`.
   - **100% taxation for the player only:** `gs.player_taxation_override = {PLAYER: 4}`.
     `GameState.get_taxation_level(player)` reads the override, falling back to the game-wide
     `taxation_level`; `apply_taxation()` and the top bar use it. Not saved — the Tale sets it
     again in `restore_save_state()` and clears it in `_cleanup()`.
   - Kerunian command limit raised to `RED_COMMAND_LIMIT` (200): they start with 88 units,
     and at 100 their 7000 gold had nowhere to go, so attacks dried up after the first waves.
     This (not the attack cap) is the main difficulty dial.
   - Optional `KERUNIAN_REINFORCEMENTS` (off): `_spawn_kerunian_reinforcements()` adds ready
     units to Kerunian territories at the start of their turn, before the forced attack
     (ids = lowest free in that garrison, the engine's convention). Very strong — see the
     constant's comment before enabling it.
3. **Kerunian AI** = built-in (`block_ai` False on their turn), limited by:
   - **`get_ai_attack_cap()`** — `attack_cap_for_turn(turn) = turn // 2 + ATTACK_CAP_BASE`
     units per target per turn (visible turn = `gs.turn_number + 1`). See AI System →
     mission hooks for where it is enforced.
   - **Forced attacks** — `_on_kerunian_turn_start()` (from `turn_announcement_done` for
     player 1, once per `gs.turn_number`) orders `FORCED_ATTACK_TARGETS` attack(s) itself,
     **before** the AI plans: Lunedale / Free Cities first when reachable
     (`FORCED_ATTACK_OBJECTIVES_FIRST`), otherwise the Zjoal border territory with the best
     odds; up to the cap, leaving `FORCED_ATTACK_KEEP` units in each source. The AI's own
     attacks then share whatever cap is left at that target.
4. **Nordian Rebels** (player 2) never act: `block_ai` is True only on their turn,
   `execute_ai_turn_override()` does nothing and `update_ai_turn()` calls `gs.next_player()`
   as soon as their planning phase starts. `is_ai_target_allowed()` keeps them in their own
   land. **Rebellions** (`_on_player_turn_start()`, `rebellions_for_turn()`): random Zjoal
   territories outside `REBELLION_IMMUNE` change hands via `_rebel_territory()` (Tale I's
   `_revolt_territory()` pattern), with a red toast through
   `chat_notification_effect.add_system_notification()` (no denial sound).
   - **They are never eliminated.** With 0 territories `check_victory()` silently adds them to
     `gs.eliminated_players` (Total Conquest never calls the destructive `eliminate_player()`);
     `update()` discards them from it every frame, so they keep their (empty) turn and show
     as active in the Players window. Tale win/lose ignores them.
5. **No Heroes for anyone:** `is_action_allowed('train_hero')` is always False and
   `should_hide_hero_training()` True; the built-in AI checks the same gate.
6. **Intro / transmissions** — same machinery as Tale I (copied, not shared): `INTRO_SEQUENCE`
   (zoom to Lunedale, then T2T1-T2T3, all spoken by `ADVISOR_SPEAKER` "Advisor Valcerque")
   runs in `_update_intro()` with gameplay paused; ESC skips a line; `restore_save_state()`
   never replays it. Rebellions queue **one** line per turn that had any (`T2R1` the first
   time — `_rebellion_announced`, saved — then `T2R+`), played at the next idle moment.
   Victory/defeat wait for queued lines, then play `T2W` / `T2L` before the shared endgame
   sequence. `_show_transmission()` uses `max(duration, recording length)`.
   Optional cutscenes `tale_2_intro` / `tale_2_outro` (Cutscene_Tool.py) play around the tale.
- **Turn logic:** `_on_player_turn_start()` (guarded by `_last_turn_handled`): victory when a
  player turn starts with `gs.turn_number >= HOLD_TURNS` and both objectives held; otherwise
  the rebellions. **Defeat** the moment Lunedale or Free Cities isn't the player's
  (`_check_objectives()` on `territory_conquered` and every `update()`, so any capture path
  counts). An engine-ended game with `gs.winner == PLAYER` (Kerunians wiped out) is a
  victory too. Exits through the shared endgame sequence (no transmission to wait for).
  The achievement `campaign_tale_2` ("Final Breaths", no reward) comes from the generic
  `campaign_{mission_id}_completed` stat, so victory must set `gs.winner = PLAYER` (it does).
- **Turns widget:** Tale I's Popularity widget without the button — "Turns to Hold: N" over a
  `BattleBar.png` frame (crop constants imported from `tale_lack_of_funds.py`), bar =
  `_display_remaining / HOLD_TURNS`, eased. `handle_click()` only swallows clicks on it.
- **Balance** lives in the constants at the top (`RED_COMMAND_LIMIT`, `ATTACK_CAP_BASE`,
  `FORCED_ATTACK_*`, `KERUNIAN_REINFORCEMENTS`, `REBELLION_*`). Their comments record the
  simulation results they were tuned with: once both objectives hold 15 units no single
  Kerunian stack breaks them, so pressure has to come from a steady supply of attackers.
- **Tests:** `tests/test_tale_final_breaths.py` (a real Game on Avareon; conftest's Avareon
  reload is the right map here).

## Replay Viewer HUD (playback screen)

**File:** `replay_viewer.py` (`ReplayViewer`)
**Launched from:** `main.py` under `action == 'replays'`, after `ReplayBrowser` returns
`{'action': 'watch', 'path': ...}`. Returns `'main_menu'` or `'quit'`.

This is the playback screen, **not** the Replays list — that is `replay_browser.py`, and it
follows the "Browser Screens" section above instead.

### Why it is skinned differently from the browsers

The browsers are full-screen ornate panels. The viewer is a **HUD over the live game map**,
so it wears the *in-game* chrome rather than the campaign frames:

| Element | Asset / value |
|---|---|
| Top bar | `assets/TopPanel.jpg`, pre-scaled to `(width, top_bar_height)` |
| Bottom bar | `assets/BottomBar.jpg`, pre-scaled to `(width, bottom_bar_height)` |
| Info panel | `assets/RightPanel.jpg`, pre-scaled to `info_panel_rect.size` |
| Wide buttons (Speed, Exit) | `assets/GMenuButton.png` + the house tint table |
| Square buttons (playback) | drawn carved plate — `PLATE_BG (54,42,28)` + brass border |
| Dividers | `BRASS_COLOR`, `max(1, int(2 * ui_scale))` |
| Body / secondary text | `INFO_TEXT (226,216,190)` / `DIM_TEXT (168,156,128)` |
| Fonts | `Cinzel-Regular` / `Cinzel-SemiBold` via direct `pygame.font.Font` |

- **`CampaignBG.png` / `OptionsMenuBG.png` are deliberately not used here.** Framing the map
  shrinks it; the map must stay edge to edge.
- **The square playback buttons must not wear `GMenuButton.png`.** That art is 1317x417, so
  squashing it square visibly distorts it. They use `_draw_plate()` instead, which takes the
  same hover/press lift.
- **Do not route fonts through `config/font_manager.py`** — same reason as the browsers: it
  remaps every weight one step bolder.

### Button state tint table

Identical to `replay_browser._btn_surface()`, so the two screens match:

| State | Operation |
|---|---|
| normal | `MULT (100,100,100,255)` |
| hover | normal + `ADD (40,40,40,0)` |
| click | normal + `ADD (80,80,80,0)` |

`clicked_button` is set in `_handle_left_click()` and cleared at the end of `_render()`, so
the press tint lasts exactly one frame.

### The invariant that keeps input working

Every rect is a **named instance attribute** built once in `_build_layout()`.
`_handle_events()` and `_handle_left_click()` hit-test them *by attribute name* and map them
to **hover-ID strings**: `'play_pause'`, `'step_back'`, `'step_forward'`, `'speed'`, `'exit'`,
`f'pov_{id}'`. `_btn_state()` matches on those same strings.

**Rename a rect or an ID on one side only and input breaks silently** — no exception, the
button simply stops responding. Restyling is safe precisely because it only touches
`_build_layout()` constants and the `_render_*` bodies.

### Geometry contract

- **`_build_layout()` must run before `_load_map_assets()`**, which derives `scale_factor`,
  `min_zoom` and the scaled polygon/plot tables from `map_rect`. Changing a bar height after
  the assets load leaves the map scaled to the old viewport.
- **`_scrub_timeline()` derives its fraction from `timeline_rect.x / .width`**, so the drawn
  track must be exactly the clickable rect. Draw the fill and handle *inside* it, never
  around it.
- **`info_content_rect` is the single source of truth for the info panel.** The y-cursor
  flows through it *and* `max_info_scroll` is derived from it. Mixing it with the raw
  `info_panel_rect` (which includes `RightPanel.jpg`'s carved border) makes scrolling stop
  short or overrun — that is exactly what the padding rework had to fix.
- Text in the panel is fitted with `_fit_text()` (ported from `replay_browser.py:460`).
  The panel is only `320 * s` wide, so names and log lines must be measured in **pixels**,
  not cut at a character count.

### Rules that keep it correct

- **Never allocate a `Surface` per frame.** `_render_map()` draws one polygon overlay per
  *owned territory per frame*; those go through `_get_overlay()`, which caches by size and
  wipes on reuse. Building icons go through `_get_scaled_icon()` (`smoothscale` is keyed to
  `camera_zoom`, so uncached it re-ran for every building every frame).
- Every texture load has a `None` fallback and every draw site handles it — `main.py` has no
  `try` around `viewer.run()`, so an uncaught error takes down the campaign loop.
- `_text_cache` and `_fit_cache` are bounded (512 entries). The action log and turn readout
  produce fresh strings on most snapshots.
- Preserve `_MUSIC_END_EVENT` forwarding, `sound_manager.play_ui_click()` on every actionable
  click, and `draw_custom_cursor()` as the **last** blit before `flip()`.

### Known non-goals

- The window is never resizable (`pygame.RESIZABLE` appears nowhere in the codebase and
  `display_utils.set_display_mode()` passes only `FULLSCREEN` or `0`), and the viewer has no
  options menu, so it deliberately has **no `VIDEORESIZE` handling**. `_build_layout()` exists
  to centralise geometry, not to support live resizing.
- `camera_offset` is unclamped, so the map can be panned fully off-screen. Pre-existing.
