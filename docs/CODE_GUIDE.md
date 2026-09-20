# Code Modification Guide

**Living knowledge base for developers working on AvareonWar**

This guide provides module-specific guidance on when and how to modify different parts of the codebase. Use this as your primary reference when implementing features, fixing bugs, or making balance changes.

---

## Table of Contents

1. [Logging System](#logging-system) - Structured logging
2. [game_state package](#game_state-package) - Core game logic
3. [main.py](#mainpy) - Main game loop and UI
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
- Battle bar combat (particles) → `ui/effects/battle_interface.py` (BattleBarParticleEffect) — 600 circle particles
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
- Modify decision delays in `make_decisions()`
- Adjust threading/locking as needed

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
- Modify priority order in `handle_click()`
- Current: Popups → UI elements → Map territories

### input/keyboard_handler.py (~530 lines)

**What it does:** Keyboard shortcuts and commands

#### When to Modify

✅ **Add new keyboard shortcut:**
1. Add key detection in `handle_keydown()`
2. Trigger appropriate game action
3. Document in `QUICK_REFERENCE.md`

### input/camera_handler.py (399 lines)

**What it does:** Camera pan, zoom, edge scrolling

#### When to Modify

✅ **Change camera behavior:**
- Modify pan speed, zoom speed
- Adjust edge scrolling sensitivity
- Change zoom limits (min/max)

---

## map_data.py

**What it does:** Multi-map data loader — territory polygons, adjacency graph, plots, economy, bonuses, fortress territories
**Data source:** Per-map JSON files in `maps/<map_id>/` directories, manifest in `maps/manifest.json`
**Key globals:** `TERRITORY_POLYGONS`, `TERRITORY_CENTERS`, `ADJACENCIES`, `FORTRESS_TERRITORIES`, `_current_map_id`

### Multi-Map Architecture

- `maps/manifest.json` — Registry of all available maps (id, display_name, has_background)
- `maps/<map_id>/` — Per-map data directory containing:
  - `territory_polygons.json`, `plots.json`, `economic_data.json`
  - `territory_bonuses.json`, `adjacencies.json`, `fortress_territories.json`
- `load_map(map_id)` — Primary entry point: loads all data from map directory into globals
- `load_polygons()` — Legacy backward-compat entry point (loads Avareon from root-level files)
- Campaign missions always use the Avareon map via `load_polygons()`

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

When a player action fails (e.g., not enough gold, command limit), the game shows a floating notification + plays a denial sound. The pattern:

1. **Game state method** (e.g., `start_training()`) sets `self.last_action_error = "gold"` before `return False`
2. **main.py call site** calls `self._show_action_failure_feedback()` in the `else` branch
3. The helper reads `last_action_error`, maps it to a user-facing message, plays `play_action_denied()`, and calls `chat_notification_effect.add_system_notification(msg)`

**Error codes:** `"gold"`, `"command_limit"`, `"army_limit"`, `"queue_full"`, `"hero_limit"`

**To add a new failure type:** Set `self.last_action_error = "new_code"` in the game state method, add the code→message mapping in `Game._ACTION_ERROR_MESSAGES`.

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
- **AI Control:** `block_ai` property prevents normal AI, mission handles turns
- **Shared Utilities:** `campaign_utils.py` contains shared classes used by missions 2-4+:
  - `TransmissionOverlay` - narrative text overlay with speaker header
  - `CameraPanAnimation` - smooth camera pan between territories
  - `CameraZoomAnimation` - smooth camera zoom to a territory
  - `update_endgame_sequence()` / `render_endgame_sequence()` - victory/defeat animation helpers

### Files

- [campaign_utils.py](../campaign_utils.py) - Shared campaign utilities (TransmissionOverlay, camera animations, endgame sequences)
- [campaign_screen.py](../campaign_screen.py) - Campaign menu UI
- [tutorial_mission.py](../tutorial_mission.py) - Tutorial mission (Lobardia)
- [campaign_mission_2.py](../campaign_mission_2.py) - Early Eastern Conquests (9 territories, 4 players)
- [campaign_mission_3.py](../campaign_mission_3.py) - Storms above the West
- [campaign_mission_4.py](../campaign_mission_4.py) - Domination (21 territories, 4 factions, hybrid custom AI)
- [campaign_mission_5.py](../campaign_mission_5.py) - The First War (17 territories, 3 factions, allied team vs empire)
- [campaign_mission_6.py](../campaign_mission_6.py) - The Second War (33 territories, 3 factions, 4 sequential quests, dynamic AI)
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
    return True
```

### Campaign Transmission Voice Lines

**Naming:** `T{N}.mp3` for Mission 1, `M{X}T{N}.mp3` for Mission 2+. Placed in `assets/sounds/transmissions/`. Loaded by `global_sound.load_transmission_sounds()` using filename stem as key.

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

**Implemented in:** All 4 missions — Mission 1 (`tutorial_mission.py`), Mission 2 (`campaign_mission_2.py`), Mission 3 (`campaign_mission_3.py`), Mission 4 (`campaign_mission_4.py`).

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
- Change save browser UI → modify `save_browser.py` `_render_*()` methods
- Change save file format → increment `SAVE_VERSION` in save_manager.py

**Architecture notes:**
- Serialization pattern mirrors `replay_recorder._serialize_state()` plus config/eliminated players
- Each mission class owns its own state via `get_save_state()` / `restore_save_state()`
- Load flow: LoadingScreen initializes fresh GameState → `deserialize_game_state()` overwrites → mission constructor → `restore_save_state()`
- Tutorial (Mission 1) save is disabled (too complex to serialize step machine)
- Save disabled during: AI turns, intro sequences, victory/defeat sequences
- Save files: gzip-compressed JSON in `Saves/` folder
- Atomic writes via tempfile + os.replace()
