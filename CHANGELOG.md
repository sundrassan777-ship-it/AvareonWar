# Changelog

All notable changes to the AvareonWar project.

## 2026-03-05 - Battle Sound Effect

- Play BattleSound.mp3 once when battles are created for the local player at end of turn
- Sequential mode: plays when current player is the local human player
- Simultaneous mode: plays only when local player is the battle resolver
- Fixed sound index shift bug caused by adding BattleSound.mp3 to general/ folder (CastleCompleted, DefaultMouseClick, ResearchCompleted indices were all off by 1)
- Files: `global_sound.py`, `sound_manager.py`, `main.py`

## 2026-03-04 - FPS Performance Optimization (5-Phase)

- **Phase 1 - Territory Overlay:** Dirty-flag cache for territory overlay (version counter skips redraw when camera/ownership unchanged), small clipped hover surface (~200x150) instead of full-screen (1920x1080)
- **Phase 2 - Calculation Caching:** Income and army count calculations cached with dirty-flag invalidation + 30-frame periodic fallback safety net; event-driven production glow sync via `_training_version` counter
- **Phase 3 - AABB Hit-Testing:** Bounding box pre-check on `get_territory_at_pos()` skips ~90% of polygon ray-casting tests
- **Phase 4 - Font Caching:** 128 `font.render()` calls in main.py + 6 in ui_renderer.py replaced with `_get_cached_text()` lookups
- **Phase 5 - Effect Optimizations:**
  - TurnAnnouncementEffect: Non-SRCALPHA overlay + cached smoothscale text by quantized size
  - BattleHurricaneEffect: 1000→700 particles, pre-computed sin/cos LUT (360 entries), small ~120x120 surface instead of full-screen
  - ProductionGlowEffect: 16 pre-rendered rotation frames (single blit instead of 64 polygon draws per frame), rebuilt on zoom change
- **Results (1600x900):** Late Game Stress 41.3→59.6 FPS (+44%), Movement Arrows 35.9→57.7 FPS (+61%)
- **Files modified:** `rendering/map_renderer.py`, `game_state/__init__.py`, `game_state/economy.py`, `game_state/military.py`, `game_state/buildings.py`, `game_state/heroes.py`, `game_state/victory.py`, `main.py`, `rendering/ui_renderer.py`, `ui/effects/turn_announcement_effect.py`, `ui/effects/battleeffect.py`, `ui/effects/production_glow_effect.py`

## 2026-03-04 - Expanded Main Menu Options Panel

- Main menu Options now matches in-game Options with all the same settings
- Added Edge Scrolling Mode toggle (Map Edge / Window Edge), conditional on Edge Scrolling enabled
- Added Tooltip Delay cycle (0.3s / 0.5s / 0.7s / 1.0s / Never), conditional on Tooltips enabled
- Added Pan Speed and Zoom Speed sliders with drag support
- Added Audio section placeholder (Coming Soon)
- Added scrollable content area with scrollbar for overflow at lower resolutions
- File: `main_menu.py`

## 2026-03-04 - Overwhelming Advantage: Zero-Casualty Victories

- **Balance change:** When the winner's effective strength is 10x or more the loser's, the winner suffers 0 casualties instead of the previous minimum of 1
- Applies to normal battles and Keep Phase 1 (both attacker and garrison winning)
- New constant `OVERWHELMING_ADVANTAGE_RATIO = 10` in `data_definitions.py` for easy tuning

## 2026-03-02 - Captain Unit Type

- **New unit:** Captain — support unit trained in Barracks (75g, 1 turn, keyboard: T)
  - 0.25 base strength (weaker than any combat unit, including countered ones at 0.5)
  - No counter relationships (always neutral 1.0 effectiveness)
  - +12% strength bonus to all other units in army (non-stacking — multiple Captains don't stack)
  - Extended movement: army with Captain can move 2 territories to allied destination through allied intermediate
  - Cannot attack across 2 territories (reinforcement only)
  - Animation: bent 2-hop path through intermediate territory
  - AI: strategic training when army ≥8 and no Captain present (25% chance)
- **Enhancement:** Heroic Fortitude technology now also reduces Captain cost from 75g to 50g
- **Files added:** `tests/test_captain.py` (23 tests)

## 2026-03-02 - Game Logging System

- **New feature:** Per-game JSON logging for custom and multiplayer games
  - Creates `Logs/` folder with log files named `{8-digit-ID}_{YYYY-MM-DD}.json`
  - Game metadata: version, player count, total turns, duration, win condition, winner
  - Per-player heroes trained with turn numbers, tech researched with turn numbers
  - Per-turn data: units built per type (Pikeman/Archer/Swordsman/Cavalry), buildings built per type (Farm/Mine/Square/Barracks/Training Grounds/Keep), units lost, regions controlled, battles
  - Hybrid data collection: snapshot-based deltas for units/losses + event-based for heroes/tech/buildings/battles
  - Hooks in heroes.py, buildings.py, military.py, sim_state.py; wired in main.py
  - Campaign missions excluded (no log created)
  - `turn_number` now properly incremented as a round counter in sequential mode

## 2026-03-02 - Network Security Hardening

- **Security:** Removed debug logging of reconnection password (credential leak)
- **Security:** Switched password comparison to `hmac.compare_digest()` (timing attack prevention)
- **Security:** Increased reconnection password from 8 to 16 characters (stronger entropy)
- **Security:** Added `validate_message_data()` in protocol.py — validates player_index (0-3), ai_difficulty (0-2), team (0-3), army_count (1-999), plot_index (0-10), victory/tax/turn-mode ranges, chat channel values
- **Security:** Added chat message length cap (500 chars) to prevent oversized messages
- **Security:** Added player name sanitization — strips Unicode control characters, null bytes, enforces 32-char limit
- **Security:** Added per-client sequence number validation to reject replay/duplicate messages
- **Security:** Added reconnection rate limiting (5 attempts per 30s per IP) to prevent brute-force

## 2026-03-01 - Campaign Mission 5: The First War

- **New feature:** Implemented Campaign Mission 5 "The First War"
  - 3 factions: Human (Red) + Elletic Rebels (Yellow, allied) vs Azincourne Empire (Blue)
  - 17 playable territories with alliance system (player_teams [0, 0, 1])
  - Normal AI handles both AI players (alliance-aware via are_allies())
  - Victory: liberate 9 specific territories (controlled by either allied player)
  - Defeat: Elletic Isles falls to Azincourne, or human loses all territories
  - 2 quest objectives, intro zoom/transmission sequence, flag icon remapping
  - Human starts with Efficient Farming I + Master Planner I pre-researched
  - Territory rename: "The Holy Land" → "Neimer Coast", "Elletian Isles" → "Elletic Isles"
  - Bonus achievement: win without losing any starting allied territories
  - Updated campaign screen, mission registry, achievement entries

## 2026-03-01 - Player Level Achievements

- **New feature:** 12 achievements for reaching player levels 5, 10, 20, 30, 40, 50, 75, 100, 150, 200, 250, 500
  - Category: General
  - Level 5 has no reward; levels 10-500 each unlock a title reward (Scout, Soldier, Sergeant, Corporal, Lieutenant, High Lieutenant, Commander, High Commander, Captain, Marshal, High Marshal)
  - Uses special `player_level` stat_key resolved from `PlayerLevelManager` instead of cumulative stats
  - Achievement check now runs **after** XP recording so level changes are detected
  - Icons: `assets/achievements/AchievementIcons/Level{N}.png`

## 2026-02-27 - Player Level System

- **New feature:** Persistent Player Level system with XP earned from gameplay actions and end-of-game bonuses
  - **New file:** `player_level.py` — core XP/level logic, tiered progression formula, persistence via `settings_manager`
  - **XP actions:** unit training (+2), building (+2), neutral conquest (+2), enemy uncontested conquest (+4), battle conquest (+8), hero training (+4), hero kill (+10), hero ability (+2), tech research (+4)
  - **End-of-game bonuses:** defeat (+25), victory (+50, doubled to 100 in MP vs equal/more humans), campaign first-time win (+100)
  - **Eligibility:** Campaign always; Custom/MP only if >=1 enemy exists; no XP on premature quit
  - **Halving:** All XP halved if player's team outnumbers enemy team
  - **Profile panel:** Level bar with gold fill displayed to the right of player name in main menu Profile
  - **Recap screen:** Animated XP bar after achievement popups with 2s fill animation, golden particle burst on level-up
  - Level formula: 100 XP/level (1-10), 250 (11-20), 500 (21-40), 1000 (41-100), 2500 (101-200), 5000 (201-500), 10000 (501-10000); max level 10,000
  - XP hooks in `game_state/buildings.py`, `heroes.py`, `military.py` (10 sites total)

## 2026-02-27 - Fix Territory Bonuses Not Updating After Conquest

- **Bug fix:** Territorial bonuses (income, unit cost, building cost, unit strength, etc.) were permanently cached from game start and never refreshed when territories changed ownership
  - **Root cause:** `calculate_player_territorial_bonuses()` cached results keyed by `(player_index, turn_number)`, but `turn_number` was never incremented — it stayed at 0 the entire game, so the cache was never invalidated
  - **Fix:** Replaced broken turn-number cache with explicit invalidation via `invalidate_territorial_bonus_cache()`, called at all 15 ownership-change sites across `game_state/`, `simultaneous/`, `main.py`, campaign missions, keyboard handler, and tutorial
  - Bonuses now correctly update in real-time when territories are conquered, lost, or transferred

## 2026-02-27 - Training Grounds Building

- **New building:** Training Grounds (50g, 1 turn) — grants +15 XP per turn to all units garrisoned in the territory
  - One per territory limit (like Keep)
  - AI evaluates based on army presence and frontline status
  - Keyboard shortcut: T
  - Destroyed on conquest (not preserved by Champion of the People)

## 2026-02-27 - Multiplayer Bug Fixes (ORDER_REMOVE + Reconnect Timeout)

- **Bug fix:** Implemented `ORDER_REMOVE` network handler — was a silent no-op stub causing multiplayer desyncs when a player cancelled movement orders
  - **Receive side** (`_handle_remote_order_remove`): now calls `cancel_movement_order()` / `cancel_all_orders()` with player validation and try/finally current_player swap
  - **Send side**: cancel-order and cancel-all-orders sidebar clicks now send `ORDER_REMOVE` messages with `order_index` or `cancel_all` flag + `player_index`
- **Bug fix:** Reconnection timeout mismatch — `server.py` hardcoded 300s instead of using `RECONNECTION_TIMEOUT` (60s) from `network_config.py`
  - `server.py` now imports and uses `RECONNECTION_TIMEOUT` constant

## 2026-02-27 - Loading Screen Gameplay Tips

- **New feature:** Added gameplay tips to loading screen, displayed above the progress bar
- Custom games: 50 general tips randomly selected (units, buildings, heroes, tech, economy)
- Campaign missions: 3 mission-specific tips per mission (missions 1-4), randomly selected
- "TIP:" label rendered in Cinzel-Bold gold; tip text in white, word-wrapped to bar width
- `loading_screen.py`: added `CUSTOM_TIPS`, `CAMPAIGN_TIPS` data, `_select_tip()`, `_wrap_text()`, tip rendering
- `main.py`: passes `mission_id` to `LoadingScreen` for campaign-specific tip selection

## 2026-02-27 - Deferred Asset Loading with Loading Screen

- **New feature:** Added loading screen with progress bar between setup and gameplay
- Only menu sounds (3 files) load at startup; game sounds (~136 files) deferred to loading screen
- `global_sound.py`: split into `initialize_menu_sounds()` (startup) + `get_game_sound_tasks()` (deferred)
- New file `loading_screen.py`: `LoadingScreen` class with progress bar, "click to start" prompt
- Multiplayer: `GAME_READY` network message ensures both players finish loading before game starts
- Loading screen used in all 3 game modes: custom game, campaign, multiplayer

## 2026-02-26 - Hero Ability Visual Effects (Phase 2: Immediate Abilities)

- **New feature:** Added particle visual effects for 3 immediate (non-targeted) hero abilities
- **Reinforce:** Silver/steel explosion at hero's Keep territory (120 particles, explosion only)
- **Extort Populace:** Gold explosion at each Keep/Castle building plot the player owns
- **Embargo:** Dark red polygon-filling bubbles on all enemy territories simultaneously

## 2026-02-26 - Hero Ability Visual Effects (Phase 1: Targeted Abilities)

- **New feature:** Added particle visual effects for all 7 targeted hero abilities
- **Aggressive Diplomacy:** Fire-orange polygon-filling bubble burst (Defiance-style rising circles, one-shot ~1s)
- **Decisive Strike:** Blue castle-upgrade-style explosion (140 particles, explode + swirl + float, 3.5s)
- **Regicide:** Dark purple inward implosion (particles spiral toward center)
- **Levy:** 5 small gold explosions at random territory polygon points (explosion only, no swirl)
- **Relentless Charge:** Dust/brown outward explosion
- **Royal Charisma:** Gold particle arc from target territory to Narn's Keep (bezier curve)
- **Valorous Charge:** Blue/white particle arc from Keep to target territory
- New effect classes: `ui/effects/ability_burst_effect.py`, `ui/effects/ability_arc_effect.py`, `ui/effects/ability_polygon_burst_effect.py`
- Effects triggered on both local execution and network replay paths
- World-coordinate based (tracks camera zoom/pan), cached SRCALPHA surfaces, consistent with existing art style

## 2026-02-26 - ESC to Skip Campaign Transmissions

- **New feature:** Pressing ESC during a visible campaign transmission now skips it (hides overlay, stops voice audio). If no transmission is visible, ESC opens the game menu as usual.
- Works across all 4 campaign missions (tutorial, missions 2-4), during both intro sequences and gameplay transmissions.
- Tutorial event-driven steps (duration=0): ESC hides the text but does not advance the step — player still needs to perform the required action.
- Added `skip_transmission()` method to `TutorialMission`, `Mission2`, `Mission3`, `Mission4`.
- Modified `main.py` ESC handling in 3 event-loop locations (camera-locked, AI turns, general KEYDOWN).

## 2026-02-26 - QA Audit #8: Comprehensive Codebase Audit (40 fixes across 31 files)

### CRITICAL Bug Fixes (3)
- **sim_state `.get()` on list crash** — `player_teams` is a list; `.get()` caused `AttributeError`. Fixed to index-based access with bounds checking.
- **battle_interface undefined `BAR_HEIGHT`** — Except block referenced undefined variable, causing `NameError` if BattleBar.png was missing. Changed to `BAR_PNG_HEIGHT_REF`.
- **campaign_mission_4 missing speaker param** — `_show_transmission()` didn't pass `speaker` to `set_text()` on overlay reuse, causing wrong speaker display.

### HIGH Bug Fixes (12)
- **Garrison cleanup** — `heroes.py` used `del territory_garrisons[t]` instead of `= {}` convention; `victory.py` didn't clean up allied garrisons in non-owned territories during elimination.
- **AI ally exclusion** — Added `are_allies()` checks to 7 hero ability scorers, frontier detection, counterattack risk, and military threat assessment to prevent AI treating allies as enemies.
- **Castle upgrade cost** — AI budget calculation used 100 instead of correct 150 for Castle upgrades.
- **campaign_mission_4 try/finally** — AI `current_player` swap wasn't wrapped in try/finally; exception would leave wrong player active.
- **campaign_mission_5/6 territory cleanup** — Missing `map_data.clear_enabled_territories()` in `deactivate()`.
- **map_renderer dynamic resolution** — Hardcoded `WINDOW_WIDTH`/`WINDOW_HEIGHT` replaced with `screen.get_width()`/`get_height()`.
- **network/client thread safety** — Buffer overflow disconnection state writes now wrapped with `_state_lock`.
- **sim_ai ready flag race** — Reordered `mark_ready()` before `ai_ready` flag to activate order rejection guard.
- **recap_screen graceful exit** — Replaced `pygame.quit(); sys.exit()` with graceful result return.

### HIGH Performance Fixes (9)
- **SRCALPHA surface caching** — Cached full-screen SRCALPHA surfaces in 6 UI effects (castle_upgrade, sparkle, edge_wave, turn_announcement ×2, integrated_setup, territory_selector).
- **battle_interface pre-scaling** — Pre-scaled bar borders (4 per-frame smoothscale calls) and panel backgrounds (2 per-frame) at layout time.
- **main_menu font caching** — Added `_font_cache` dict replacing 10+ per-frame `pygame.font.Font()` filesystem calls. Cached pre-scaled button background.
- **main.py duplicate hover tracking** — Removed redundant building button hover code (already in `update_frame_tooltips()`).
- **O(n) particle cleanup** — Replaced O(n×k) `list.remove()` loop with O(n) list comprehension for Master Negotiator particles.

### MEDIUM Bug Fixes (11)
- **Accurate refunds** — Training queue now stores `(unit_type, turns, cost_paid)` and research stores `cost_paid` in its dict. Cancel operations refund the exact amount paid instead of recalculating (which could differ if bonuses changed).
- **Square multiplier stacking** — Changed `multiplier = value` to `multiplier *= value` so multiple Squares compound correctly.
- **Action log overflow** — Messages now stop rendering past overlay bottom boundary.
- **Victory overlay type conflict** — `_render_victory_sequence` (non-SRCALPHA) and `draw_victory_screen` (SRCALPHA) now use separate cached surfaces.
- **Merge glow zoom scaling** — Cyan reinforcement glow radius now scales with `ui_scale` matching the red attack glow.
- **AI hardcoded plot count** — `_score_master_negotiator` now uses `map_data.get_plots()` instead of assuming 3 plots per territory.
- **delta_time cap** — campaign_mission_4 now caps `delta_time` at 0.05s, matching missions 2/3/tutorial.
- **Cutscene graceful exit** — `cutscene_player.py` QUIT event sets `_done = True` instead of `sys.exit()`.
- **Taxation bounds check** — `apply_taxation` now clamps `taxation_level` to valid `tax_rates` index range.
- **Identical branches** — Collapsed duplicate if/else in campaign_mission_3 Uhmayya AI enemy selection.

### MEDIUM Performance Fixes (5)
- **Territorial bonus caching** — `calculate_player_territorial_bonuses()` cached per (player, turn_number) to avoid re-iterating 57 territories on every cost calculation.
- **Tooltip surface reuse** — `draw_tooltip_box` reuses cached SRCALPHA surface when size matches.
- **Chat input surface reuse** — `draw_chat_input` reuses cached SRCALPHA surface instead of per-frame allocation.
- **Achievement panel `.copy()` reduction** — Removed unnecessary `.copy()` on cached bg/icon/border surfaces; copy only when modifying in-place for unearned darkening.

### Documentation
- **CLAUDE.md** — Added best practices from audit: deferred refunds, campaign mission patterns, surface cache separation, ally exclusion, multiplier stacking, bounds checking, graceful exits.

## 2026-02-25 - QA Review Fixes (R1-R12)

### Bug Fixes
- **R2: `player_teams.get()` crash** — `player_teams` is a list, not dict. Team chat would crash with `AttributeError`. Fixed to use index-based access.
- **R4: TurnCache missing under-construction Keeps** — AI could redundantly prioritize building a second Keep while one was under construction. Added under_construction check.
- **R4: Inconsistent cache dict access** — `ai_strategy.py` used direct indexing (`cache.territory_armies[key]`) which would KeyError on missing keys. Changed to `.get(key, 0)` matching other AI files.
- **R7: sim_ai thread safety** — `_selected_unit_ids` was shared across all AI threads. One thread resetting it could wipe another's data. Made per-player keyed.
- **R8: Castle scoring gap** — `_BUILDING_VALUES` dict was missing `'Castle'` entry; territories with Castles scored 0. Added Castle: 9.0.
- **R8: Allied garrison validation** — `add_movement_order` validated against territory owner's garrison instead of current player's, failing in allied scenarios.

### Dead Code Removal (~250 lines)
- **R3:** Removed `calculate_army_base_strength()` (had KeyError bug on non-existent `'strength'` key, 0 callers)
- **R3:** Removed legacy `can_move_army()` / `move_army()` (0 callers, replaced by order/animation system)

### Test Fixes (132→170 passing)
- **R1:** Rewrote 21 `test_network_server.py` tests for multi-client API (`ClientConnection` dict pattern)
- **R1:** Fixed 8 `test_fixes.py` tests (method renames, `caplog` instead of `capsys`)
- **R1:** Fixed 9 `test_ai_strategy.py` tests (added `get_territory_total_armies`, `are_allies`, `has_fortress` to MockGameState)

### Code Quality
- **R9:** Replaced stale line-number references in military.py comments with method name references
- **R10:** Added periodic pruning of `_connection_attempts` dict in server.py (prevents slow memory leak)
- **R11:** Moved `get_building_xp_data()` / `award_building_xp()` from MilitaryMixin to BuildingMixin
- **R12:** Normalized `BONUS_TYPES` from class attribute to instance attribute (matches HERO_TYPES/building_types pattern)

## 2026-02-25 - Phase 7: game_state.py Decomposition

### Architecture
- **Decomposed `game_state.py` (8,719 lines) into `game_state/` package (8 files)**
  - `__init__.py` (1,064 lines) — Core: `__init__`, turn management, coordinates, chat, diplomacy, `MovementOrder`/`ArmyAnimation`/`Battle` classes
  - `data_definitions.py` (683 lines) — `HERO_TYPES`, `BUILDING_TYPES`, `BONUS_TYPES`, `build_technologies()`
  - `garrison.py` (796 lines) — `GarrisonMixin`: multi-garrison system, legacy sync, unit movement
  - `heroes.py` (1,467 lines) — `HeroMixin`: training, 9 ability executions, hero queries, cooldowns
  - `buildings.py` (1,070 lines) — `BuildingMixin`: construction, training, castle upgrades, tech research
  - `economy.py` (390 lines) — `EconomyMixin`: income, costs, taxation, territorial bonuses
  - `military.py` (3,162 lines) — `MilitaryMixin`: armies, movement orders, battle resolution, arrivals
  - `victory.py` (284 lines) — `VictoryMixin`: victory checks, player elimination
- **Mixin pattern** — GameState inherits from all 6 mixins. All `self.xxx` cross-domain calls work unchanged. Zero import changes needed for 31+ external files.
- **`from game_state import GameState`** still works — package `__init__.py` exports everything.

## 2026-02-25 - Phase 6: Network Hardening & Best Practices

### Security (6A)
- **Connection rate limiting** - Added per-IP rate limiting to server (max 5 connections per 10s window). Prevents connection spam/DoS.
- **Message schema validation** - Enabled existing `validate_message()` in the server's receive path. Validates required fields (`type`, `seq`, `data`) and that message type is a known `MessageType` enum value. Unknown/malformed messages are logged and dropped.

### Best Practices (6C)
- **Deduplicated `brighten_color()`** - Was identical implementation to `lighten_color()` with different default amount. Now delegates to `lighten_color()` (~26 lines saved).
- **`cutscene_player.py` print→logger** - Replaced 3 `print()` statements with `logger.warning()`. Added logger import.
- **Keyboard dispatch dicts** - Replaced building (5-branch) and training (4-branch) if/elif chains with `_BUILDING_SHORTCUTS` and `_TRAINING_SHORTCUTS` module-level dicts.
- **`sim_ai.py` init fix** - Initialized `_selected_unit_ids` in `__init__` and removed `hasattr` guard.

## 2026-02-25 - Phase 5: Rendering & AI Optimization

### Performance - Rendering (5A)
- **UIRenderer smoothscale caching** - Cached 9 per-frame `pygame.transform.scale()` calls in `draw_top_panel()` (4 slot backgrounds + 4 icons), `draw_game_menu()`, and `draw_options_menu()`. Surfaces only re-scale on window resize.
- **AchievementPanel smoothscale caching** - Cached ~27 per-frame `smoothscale()` calls (category buttons, achievement backgrounds, icons, icon borders). Only re-scales when panel dimensions change.
- **Extracted `utils/surface_utils.py`** - `crop_to_opaque()` function was duplicated in 5 files; unified with complete guard clause. ~75 lines eliminated.

### Performance - AI System (5B)
- **TurnCache** - New `TurnCache` class pre-computes commonly reused values once per AI turn: `owned_territories`, `territory_count`, `territory_armies` (dict for all 57 territories), `player_income`, `player_army_count`, `player_has_keep`, `threats`. Eliminates ~580+ redundant computations per AI turn (territory_count recomputed 9x, owned_territories 7x, get_territory_total_armies 500+x, find_threatened_territories 2x, calculate_player_income 3-10x, get_player_army_count 5-10x).
- **BFS deque** - Replaced `list.pop(0)` O(n) with `collections.deque.popleft()` O(1) in `find_reachable_enemies()`.
- **Expansion targets set** - Replaced O(n) linear scan `any(t[0] == neighbor for t in targets)` with O(1) `seen_targets` set in `find_expansion_targets()`.
- **Building config to __init__** - Moved `building_configs` dict from `_score_building()` body to `BuildingPlanner.__init__()`. Was recreated 75-125x per turn.
- **Dispatch dicts** - Replaced if/elif chains: building values (5-branch), budget allocation (5-branch).
- **Consolidated duplicate computations** - `territory_count` computed once per method instead of 2x in `_score_attack_target()`. `find_threatened_territories()` called once (at threshold 30), filtered for threshold 40 reuse.

## 2026-02-25 - Phase 5A: Extract `crop_to_opaque` to shared utility

### Refactoring
- **Extracted `utils/surface_utils.py`** - New shared module containing `crop_to_opaque()` function that was duplicated across 5 files:
  - `achievement_panel.py` - static method removed, now imports from shared utility
  - `campaign_screen.py` - static method removed, now imports from shared utility
  - `recap_screen.py` - static method removed, now imports from shared utility
  - `ui/effects/battle_interface.py` - static method removed, now imports from shared utility
  - `Campaign_Text_Tool.py` - static method removed, now imports from shared utility
- **Unified guard clause** - Some copies had `if bottom < top` only, others had `if bottom < top or right < left`. Shared version uses the complete guard and returns `surface.copy()` (safe fallback).
- **Net reduction:** ~75 lines of duplicated code eliminated

### New Files
- `utils/surface_utils.py` - Shared surface manipulation utilities

### Modified Files
- `achievement_panel.py` - Replaced local `_crop_to_opaque` with import from `utils.surface_utils`
- `campaign_screen.py` - Replaced local `_crop_to_opaque` with import from `utils.surface_utils`
- `recap_screen.py` - Replaced local `_crop_to_opaque` with import from `utils.surface_utils`
- `ui/effects/battle_interface.py` - Replaced local `_crop_to_opaque` with import from `utils.surface_utils`
- `Campaign_Text_Tool.py` - Replaced local `_crop_to_opaque` with import from `utils.surface_utils`
- `docs/CODE_GUIDE.md` - Added Shared Utilities section documenting `utils/surface_utils.py`

## 2026-02-25 - Phase 2C: Extract Shared Campaign Utilities

### Refactoring
- **Extracted `campaign_utils.py`** - New shared module containing campaign classes that were duplicated across missions 2, 3, and 4:
  - `TransmissionOverlay` (~120 lines, was duplicated x3) - narrative text overlay with speaker header
  - `CameraPanAnimation` (~50 lines, was duplicated x2) - smooth camera pan between territories
  - `CameraZoomAnimation` (~40 lines, was duplicated x3) - smooth camera zoom to territory
  - `update_endgame_sequence()` / `render_endgame_sequence()` (~80 lines, was duplicated x6) - victory/defeat animation helpers
- **Fixed CameraZoomAnimation return value inconsistency in Mission 4** - Mission 4's old version returned True=done (inverted from missions 2/3 which return True=still-animating). Unified to match missions 2/3 convention; Mission 4 caller updated to check `.active` instead.
- **Net reduction:** ~700 lines of duplicated code eliminated

### New Files
- `campaign_utils.py` - Shared campaign utilities

### Modified Files
- `campaign_mission_2.py` - Replaced local TransmissionOverlay, CameraPanAnimation, CameraZoomAnimation, victory/defeat sequences with imports from campaign_utils
- `campaign_mission_3.py` - Replaced local TransmissionOverlay, CameraPanAnimation, CameraZoomAnimation, victory/defeat sequences with imports from campaign_utils
- `campaign_mission_4.py` - Replaced local TransmissionOverlay, CameraZoomAnimation, victory/defeat sequences with imports from campaign_utils; fixed CameraZoomAnimation constructor call and return value handling
- `docs/CODE_GUIDE.md` - Updated Campaign System section to document campaign_utils.py and shared utilities

## 2026-02-24 - Campaign Missions 5 & 6 Infrastructure + Campaign Screen Pagination

### New Feature
- **Campaign missions 5 & 6 placeholder stubs** — Full duck-typed interface implementations with no-op defaults, ready to be fleshed out with actual mission logic.
- **Campaign screen pagination** — Arrow buttons (left/right) allow navigating between pages of 5 missions each. Page 1 shows missions 1-5, page 2 shows mission 6+. Arrows only appear when additional pages exist.

### New Files
- `campaign_mission_5.py` — Mission5 class (placeholder stub with full interface)
- `campaign_mission_6.py` — Mission6 class (placeholder stub with full interface)

### Modified Files
- `campaign_screen.py` — Added missions 5-6 to button list, added pagination state/arrows/page navigation
- `main.py` — Added `elif` launch blocks for mission_5 and mission_6 in campaign loop
- `campaign_data.json` — Added placeholder entries for mission_5 and mission_6
- `cutscene_data.json` — Added empty intro/outro slide entries for missions 5 and 6
- `Campaign_Text_Tool.py` — Added mission_5, mission_6 to MISSION_IDS
- `Cutscene_Tool.py` — Added mission_5/6 intro/outro to CUTSCENE_IDS
- `achievement_manager.py` — Added completion and bonus achievement entries for missions 5 and 6
- `.claude/CLAUDE.md` — Added new mission files to project structure

## 2026-02-19 - Campaign Mission 4 Voice Lines

### New Feature
- **Mission 4 transmission voice lines** - 8 voiced transmissions (M4T1-M4T8) covering intro cinematic (4 steps), faction defeat announcements (Eastern Kingdoms/Confederation), victory, and defeat. Defeat uses "Nobleman" speaker (Regnus is dead). All campaigns now fully voiced.
- **Refactored Mission 4 transmission system** - Replaced single-slot `pending_transmission` with queue-based `transmission_queue` + `_queue_transmission()` / `_start_pending_transmission()` / `_is_gameplay_idle()` helpers matching M2/M3 pattern. Fixes missing battle_popup and turn_announcement idle checks.

### Modified Files
- `campaign_mission_4.py` - Added `INTRO_STEP_TO_VOICE`, voice playback in intro/gameplay/victory/defeat, inter-transmission pause, `_show_transmission()` / `_queue_transmission()` / `_start_pending_transmission()` / `_is_gameplay_idle()` helpers, stop on cleanup. Updated 5 transmission durations.
- `docs/CODE_GUIDE.md` - Updated "Implemented in" to include all 4 missions.

## 2026-02-18 - Campaign Cutscene System

### New Feature
- **Campaign cutscenes** - Cinematic Ken Burns-style cutscenes play before and after each campaign mission. Each cutscene is a sequence of slides with smooth camera pan/zoom/rotation between two viewport rects, crossfade transitions between slides, dual-track audio (voiceover + music with independent volume/delay), and subtitle text overlay. Music persists across slides when the same track is used. Skippable with ESC or left-click.
- **Cutscene Editor Tool** - WYSIWYG editor (`Cutscene_Tool.py`) for authoring cutscenes. Supports draggable camera rects (16:9 locked), pan/zoom/easing controls, subtitle text, dual-track audio (Load Voice + Load Music buttons with volume/delay fields), tkinter file dialogs, and inline preview.

### New Files
- `cutscene_player.py` - CutscenePlayer class (blocking screen with Ken Burns rendering, crossfade, audio, subtitles)
- `Cutscene_Tool.py` - Standalone cutscene editor tool (1600x900, camera system, rect interaction, numeric fields)
- `cutscene_data.json` - Cutscene definitions per mission
- `assets/cutscenes/` - Directory for cutscene images and audio

### Modified Files
- `main.py` - Added cutscene playback at 8 integration points (4 missions x intro + outro) in the campaign loop
- `docs/CODE_GUIDE.md` - Added cutscene files to Campaign System section, added "Add Pre/Post-Mission Cutscene" guidance
- `.claude/CLAUDE.md` - Added cutscene system files, updated data files list and quick links

## 2026-02-16 - Structure On-Click Sounds

### New Feature
- **Structure click sounds** - Clicking a completed structure plays a building-specific sound (Farm, Mine, Barracks, Keep, Square). Clicking an empty plot or under-construction building plays a construction sound. 6 sound files loaded from `assets/sounds/structures/`.

### Modified Files
- `global_sound.py` - Load `structures` sound category, added `play_structure_sound()` convenience function with name-to-index mapping.
- `main.py` - Import `play_structure_sound`, trigger sounds in plot click handler (Priority 4) for Barracks, Keep, and else (completed/empty/construction) branches.

## 2026-02-16 - Campaign Mission 3 Voice Lines

### New Feature
- **Mission 3 transmission voice lines** - 19 voiced transmissions (M3T1-M3T17 + M3T15a/M3T15b/M3T15c) covering intro cinematic, faction awakening (Nordia/Uhmayya), defectors, alliance, betrayal, per-faction defeat (Affrancia/Nordia/Uhmayya), victory, and defeat. Follows same voice pattern as Missions 1 & 2.
- **Per-faction defeat voice lines** - M3T15 split into M3T15a (Affrancia), M3T15b (Nordia), M3T15c (Uhmayya) for unique voice per defeated faction.

### Modified Files
- `campaign_mission_3.py` - Added `INTRO_STEP_TO_VOICE` mapping, voice playback in intro/gameplay/victory/defeat, inter-transmission pause for intro, voice stop on cleanup. Updated 10 transmission durations. `_queue_transmission` now accepts `voice_key` param.
- `docs/CODE_GUIDE.md` - Added "Campaign Transmission Voice Lines" section documenting global and per-mission voice requirements checklist for consistent implementation across all missions.

## 2026-02-15 - Campaign Mission 2 Voice Lines

### New Feature
- **Mission 2 transmission voice lines** - 21 voiced transmissions (M2T1-M2T21) covering intro cinematic, faction awakening, faction defeat, victory, and defeat sequences. Identical behavior to Mission 1: voice plays on transmission show, cuts on new, 1s pause between consecutive intro transmissions.
- **Multi-mission sound loading** - `global_sound.py` now loads all transmission files by filename stem (e.g. "T1", "M2T1") instead of regex-parsing T-numbers, supporting any mission prefix.

### Modified Files
- `global_sound.py` - Changed `_transmission_sounds` to string keys. `load_transmission_sounds()` uses filename stem. `play_transmission_sound()` accepts string or int (backward compat).
- `campaign_mission_2.py` - Added `INTRO_STEP_TO_VOICE` mapping, voice playback in intro/gameplay/victory/defeat, inter-transmission pause for intro, voice stop on cleanup. Updated 14 transmission durations per spec.

## 2026-02-12 - Campaign Mission 4: Domination

### New Feature
- **Campaign Mission 4 ("Domination")** - 21-territory mission with 4 factions. Human player (Blue) faces Eastern Kingdoms (Green, 9 territories), Confederation of the Leuse (Red, 4 territories), and Ahtep Empire (Yellow, 5 territories). All AI factions attack only the human player, never each other.
- **Hybrid custom AI** - AI ramps up over turns (turn N → max N attacks + N reinforcements). Defensive minimums per faction (1/3/5 units in border territories). Continuous troop training and structure building.
- **Custom hero: Regnus Aevencourne** - Campaign-only clone of Darius Brennhen with same abilities (Reinforce, Safe Haven, Scavenge the Fallen). Pre-assigned at Aelatania Keep. `trainable: False` hides from normal training menu.
- **Hero training icon hiding** - Mission 4 hides hero training buttons from Keep UI via `should_hide_hero_training()`. Scoped to this mission only.
- **Territory display name overrides** - 7 territories renamed for narrative context (e.g., Northern Heilonia → Southern Londia, The Holy Land → Neimer Coast).
- **Flag remapping** - Player colors: Blue/Green/Red/Yellow with corresponding flag icons.

### New Files
- `campaign_mission_4.py` - Full mission class with config, territory setup, hybrid AI, intro sequence, victory/defeat, cleanup

### Modified Files
- `game_state.py` - Added Regnus Aevencourne to HERO_TYPES (trainable: False). Updated `player_has_darius_brennhen()`, `execute_reinforce()`, `get_safe_haven_territories()`, and battle resolution Safe Haven to also check for Regnus.
- `main.py` - Added mission_4 launch block. Added hero training icon hiding check (`should_hide_hero_training`). Added Regnus to keyboard shortcuts and safe haven bubble check.

## 2026-02-11 - Internet Multiplayer (UPnP)

### New Feature
- **UPnP auto port-forwarding** - When hosting a game, automatically maps port 7777 on the router via UPnP IGD protocol so friends on different networks can connect without manual router configuration.
- **Public IP detection** - Detects and displays the host's public IP address (from UPnP IGD or HTTP API fallback) so it can be shared with remote players.
- **Dynamic lobby IP display** - Lobby screen now shows public IP with "Internet play ready!" status when UPnP succeeds, or falls back to LAN IP with helpful message if unavailable.
- **Crash-safe cleanup** - UPnP port mappings are automatically removed on game end, server stop, or unexpected exit via atexit handler.

### New Files
- `network/upnp.py` - UPnPManager class: async discovery, port mapping, public IP detection, cleanup lifecycle

### Modified Files
- `network/server.py` - Added UPnP lifecycle integration (setup_upnp, get_display_ip, cleanup in stop)
- `network/multiplayer_setup.py` - Trigger UPnP setup after server start in host flow
- `network/territory_selector.py` - Dynamic IP display with UPnP status line and color coding
- `network_config.py` - Added UPNP_DISCOVERY_TIMEOUT and UPNP_DESCRIPTION constants
- `network/__init__.py` - Added UPnPManager to package exports

### Dependencies
- `miniupnpc` (optional) - `pip install miniupnpc`. Game works without it (LAN-only fallback).

## 2026-02-10 - Achievement System

### New Feature
- **Achievement system** - Full achievement framework with definitions, persistent stat tracking, and unlock checking. Achievements have categories (General, Campaign, Training, Conquest) and can reward Titles or Icons.
- **Main menu achievement button** - Top-left icon button (mirrors profile button) opens a sliding achievement panel using the same OptionsMenuBG.png system.
- **Achievement panel** - Category filter buttons (CampaignBTN.png), name search, scrollable achievement list with AchievementFull.png item backgrounds. Earned achievements sorted to top (most recent first), unearned greyed out.
- **Recap screen achievement preview** - Newly earned achievements flash in at bottom-center of recap screen with AchievementPreview.png background, hold 3 seconds, then fade out. Multiple achievements shown sequentially.
- **Profile title system** - Dropdown in profile panel to select earned titles. Locked titles greyed out with hover tooltips showing how to unlock.
- **Profile reward icons** - Reward icons from achievements shown in profile icon grid. Unlocked icons selectable, locked icons greyed out with hover tooltips. Supports both int (hero) and string (reward path) icon IDs.
- **Persistent tracking** - Achievement stats and earned achievements saved to config.json via settings_manager. Tracks custom_game_ai_wins, multiplayer_wins, campaign_missions_completed.
- **Training achievements**: Apprentice (1 AI win), Initiate (10 wins), Aspirant Soldier (100 wins, title reward), Proven Soldier (200 wins, icon reward).
- **Conquest achievements (Multiplayer)**: A Step Into the World (1 win), Contender (10 wins, title), High Contender (50 wins, icon), Rival (100 wins, title), Conqueror (500 wins, title+icon dual reward), Devastator (1000 wins, title+icon dual reward).
- **Dual reward system** - Achievements can now grant both a title and an icon via `reward_type_2`/`reward_id_2` fields. All lookups, panel display, and unlock methods handle dual rewards.
- **Campaign achievements**: Rise of Affrancia (Ch.1), Early Eastern Conquests (Ch.2), Storms above the West (Ch.3) — completion achievements with no rewards.
- **Campaign bonus achievements**: "The Taller They Are..." (attack Valeonia first in Ch.2, LordVenderfornet icon reward), "Storming Nordia" (conquer Nordia while Affrancia holds 5+ territories in Ch.3, Lei icon reward).
- **Campaign achievement tracking fix** - Missions now set `gs.winner`/`gs.phase` on victory so `record_game_result()` processes them. Campaign detection switched from `campaign_map` to `mission_id` attribute (fixes Mission 3 which uses default map).

### New Files
- `achievement_manager.py` - Singleton achievement definitions, stat tracking, persistence, checking logic
- `achievement_panel.py` - Achievement list panel UI helper (category filters, search, scrollable list)

### Modified Files
- `settings_manager.py` - Added achievement_stats, earned_achievements, selected_title persistence keys
- `main_menu.py` - Achievement button/panel, profile title dropdown, reward icons in icon grid
- `main.py` - Hook achievement_manager.record_game_result() into show_recap_if_ended()
- `recap_screen.py` - Achievement preview popup with timed fade animation

### Asset Changes
- Renamed `assets/achievements/AchievementIsons/` to `AchievementIcons/` (typo fix)
- Copied SwordsmanIcon.png into AchievementIcons/ for achievement #4

## 2026-02-09 - Veterancy/Experience System

### New Feature
- **Unit veterancy system** - Units gain XP from battles and level up (max level 5). Each level grants +15% effective strength (up to +75% at level 5). XP thresholds: 30/45/50/55/60 per level (cumulative: 30/75/125/180/240).
- **Battle XP awards** - Winning survivors earn (10 + enemy_level) XP per enemy killed, shared equally. Destroying a Hero Keep grants +100 bonus XP. Losing side earns nothing.
- **Veterancy-aware casualties** - Casualty priority is now: PRIMARY level ASC (lowest level dies first), SECONDARY counter tier ASC. Higher-level veterans survive battles over raw recruits, regardless of unit type.
- **Building XP system** - Farms and Mines gain +20 XP per turn passively. Each level grants +10% income bonus (up to +50% at level 5). Applied before tech multipliers.
- **Unit XP preserved through movement** - Animation pipeline carries actual unit dicts (with xp/level) so XP is preserved when units move between territories, reinforce allies, or conquer new territories.
- **UI: XP bars and level shields** - Army composition grid shows brass-colored XP progress bars below each unit and golden shield icons (LevelDisplay.png) above for each level. Building info panel shows XP bars and shields for Farms/Mines. Tooltips display "Level X | XP: current/next" and bonus percentages.
- **Building XP cleanup** - Building XP properly cleaned up on destruction. Champion of the People preserves saved Farm/Mine XP. Conquest clears building XP for destroyed buildings only.

### Modified Files
- `game_state.py` - Constants, data model, helpers, unit creation points, casualty priority, strength calc, battle XP, building XP, income bonus, edge cases
- `main.py` - Army composition UI (XP bars, shields, tooltips), building info UI, asset loading
- `ui/effects/battle_interface.py` - Veterancy-aware strength calculation display
- `simultaneous/sim_phase_manager.py` - Animation pipeline carries unit dicts with XP

## 2026-02-09 - Strength-Scaled Battle Casualties

### Balance Change
- **Battle casualties now scale with effective strength ratio** - Winner casualties = `loser_count * (loser_strength / winner_strength)`. Sending counter units into battle now dramatically reduces losses. Previously, winner always lost armies equal to loser's army count regardless of strength advantage (e.g., 6 Swordsmen vs 4 Pikemen lost 4 units; now loses ~1).
- Applied to both normal battles (`_apply_battle_casualties_simple`) and Keep battle Phase 1 (`_resolve_keep_battle`). Keep Phase 2 unchanged.

## 2026-02-08 - Victory/Defeat Cinematic for Custom & Multiplayer Games

### Enhancement
- **Cinematic victory/defeat animation** - Custom and multiplayer games now show a campaign-style cinematic when a victory condition is met: screen fades to black (0.5s), victory or defeat PNG grows in (0.3s), holds for 5 seconds, then auto-transitions to the recap screen.
- **Animation-aware sequencing** - The cinematic waits for all ongoing animations (army movement, battles, turn announcements) to complete before starting, so the victory screen no longer appears over active gameplay.
- **Win/loss perspective** - Shows `victoryscrn.png` if the local player (or their team) won, `defeatscrn.png` if they lost.
- **No button needed** - Replaces the old "Return to Main Menu" text overlay with a fully automated cinematic sequence.
- Campaign missions unaffected (they retain their own victory/defeat system).

## 2026-02-08 - Army Limit Validation: Outgoing Order Awareness

### Bug Fix
- **Army limit now accounts for outgoing orders** - When reinforcing a territory, the validation subtracts armies that are ordered to leave, so a territory with 15 armies and an outgoing order for all 15 correctly shows 0 effective occupancy. Previously this blocked all incoming reinforcements.
- **Cascade cancel on order cancellation** - Cancelling an outgoing order triggers `_revalidate_incoming_orders()` which auto-cancels excess incoming orders (last-added first) to prevent overflow.
- **Red shake animation** - Auto-cancelled arrows display a brief red shaking animation before disappearing, giving visual feedback on cascade cancels.
- **Execution-time check updated** - `execute_all_orders()` safety net now uses net-aware capacity (subtracts outgoing from destination).
- New helpers: `_get_effective_capacity()`, `_revalidate_incoming_orders()` in `game_state.py`
- New constants: `COLOR_ARROW_CANCELLED`, `ARROW_CANCEL_DURATION/SHAKE_FREQ/SHAKE_AMP` in `config/constants.py`
- New rendering: `_draw_cancelling_arrows()` in `rendering/map_renderer.py`

## 2026-02-08 - Post-Game Recap Screen

### New Feature: Recap Screen
- **Post-game statistics screen** - Tabbed table UI shown after every game (custom, campaign, multiplayer)
- **4 stat tabs**: General, Units, Buildings, Economy - each with 4 sortable columns
- **Cumulative stat tracking** - 12 stats tracked via `player_stats` dict in `game_state.py` with 13 hook points
- **Sortable table** - Click column headers to sort ascending/descending
- **Winner highlight** - Gold border on winning player's row
- New file: `recap_screen.py` (modeled on `MissionScreen` in `campaign_screen.py`)

## 2026-02-08 - AI Bug Fixes: Army Cap, Hero Training, War Economy

### Bug Fixes
- **Army over-limit safety net** - Added `_enforce_army_limits()` in `game_state.py` to clamp per-player garrisons to MAX_ARMIES_PER_TERRITORY (15) after arrivals and battle resolution. Also called from `sim_phase_manager.py` for simultaneous mode.
- **Hero training queue key mismatch** - Fixed 3 methods in `ai_hero.py` (`_count_training_heroes`, `_get_training_hero_types`, `_find_keep_for_training`) that accessed `hero_training_queue[player_index]` but queue is keyed by territory name. AI was endlessly retrying hero training.
- **Training army cap check** - Added territory army limit check in `ai_military.py` `plan_training()` to skip territories at MAX_ARMIES_PER_TERRITORY.

### Balance Changes
- **Territory income rebalance** - Reduced tier income from 10/20/30 to 10/15/20 gold per turn. Total map income drops 22% (1020g → 795g). Makes economy buildings more impactful relative to base income, reduces gold hoarding.
- **Proportional threshold adjustment** - Scaled all gold-dependent AI thresholds by ×0.78 to maintain same game timing: war economy tiers (1500/3000/5000 → 1200/2400/4000), conquest push (3000/5000 → 2400/4000), strong economy (300 income → 230, 200g → 150g), hero enable (400g → 300g), demolition (3000 → 2400).

### AI Behavior Improvements
- **Multi-tier war economy** - Tiered gold thresholds (1200/2400/4000g) in `ai_economy.py`:
  - Demolish economy buildings (Farm/Mine) in favor of Barracks/Keeps at high gold
  - Removed "all plots occupied" requirement for demolition
  - Tech score multipliers: 1.25x/1.5x/2.0x at each tier
  - Forced research at gold tier 2+
- **Tiered attack aggression** - In `ai_military.py`:
  - Garrison reduction: -1/-2/-3 at gold tiers 1/2/3
  - Attack min_ratio reduced by 0.2/0.4/0.5 at each tier
  - Max attacks: 4/5/7 at each tier
- **Reduced log noise** - Training/hero failure warnings changed to debug level in `ai_player.py`

### Test Infrastructure
- Updated 4 stress test scripts (FFA+2v2, sequential+simultaneous) with:
  - Tightened validators (exact garrison consistency, per-player army limits for sim mode)
  - AI behavior analysis, building analysis, hero analysis sections
  - Fixed hero display key (`keep_territory` instead of `territory`)

### Test Results (All 4 tests PASS with 0 validation errors)
- Sequential FFA: 23 turns to victory, 145 battles, 48 Barracks, 13 Keeps
- Sequential 2v2: 23 turns to victory, 144 battles, 59 Barracks, 14 Keeps
- Simultaneous FFA: 40 rounds, 163 battles, 44 Barracks, 30 Keeps
- Simultaneous 2v2: 40 rounds, 113 battles, 53 Barracks, 29 Keeps

---

## 2026-02-07 - Comprehensive Code Quality Pass (66 Improvements + 4 Bug Fixes)

### Bug Fixes (User-Reported, Post-Testing)
- **Unicode log encoding** - Fixed arrow chars (→) showing as mojibake on Windows console; added `sys.stdout.reconfigure(encoding='utf-8')` in logger setup
- **Battle marker colors** - Fixed stale colors when battles resolve; cache now keyed by territory name instead of list index
- **Garrison count desync** - Added `_sync_garrison_counts()` to reconcile unmoved/moved counts with actual units list after modifications
- **Crossing army enforcement** - Fixed duplicate conflict pairs when multiple orders go same direction; orders now aggregated before pairing, all route orders cancelled for weaker side

### Critical Fixes (C1-C8)
- **C1: Font caching** - Cached `pygame.font.Font(None, 16)` at init instead of creating per-frame for every visible keep
- **C2: Icon caching** - Cached `smoothscale()` + overlay surfaces for castle/building icons via `_get_cached_scaled_surface()` and `_apply_icon_overlay()`
- **C3: Bare except removal** - Replaced all 26+ bare `except:` clauses with specific exception types across 12+ files
- **C4: Structured logging** - Replaced 494+ `print()` calls with `logging` module; new `utils/logger.py` with file+console output, log rotation
- **C5: Multiplayer cheat guard** - Added guard at top of `_handle_cheat_code()` blocking cheats in multiplayer mode
- **C6: Monotonic time** - Replaced `time.time()` with `time.monotonic()` in network client (prevents NTP/DST false timeouts)
- **C7: Missing method** - Added `mark_overflow_territory()` to `sim_state.py` (was called but didn't exist)
- **C8: Order deduplication** - Added hash-based dedup in sim mode to prevent duplicate army movement

### High Priority Fixes (H1-H11)
- **H1: Button image caching** - Cached `pygame.transform.scale()` for button backgrounds in `rendering/helpers.py`
- **H2: Magic number extraction** - Extracted 50+ magic numbers to named constants in `config/constants.py`
- **H3: LRU text cache** - Switched text cache from FIFO to `OrderedDict` LRU eviction
- **H4: Message queue limit** - Added `maxsize=1000` to network message queue
- **H5: AI reachability cache** - Pre-computed BFS reachability once per turn (was O(n³))
- **H6: AI thread pool** - Replaced per-turn `Thread()` creation with `ThreadPoolExecutor(max_workers=4)`
- **H7: Network thread safety** - Added `threading.Lock()` for client state (`connected`, `socket`, `running`)
- **H8: AI animation events** - Replaced `time.sleep(0.1)` polling with `threading.Event` callback
- **H9: Sim mode ready timeout** - Added 120s timeout for player ready (prevents infinite hang)
- **H10: AI planning timeout** - Added 30s safety timeout for AI planning thread
- **H11: Army API standardization** - Replaced legacy `armies[]` with `get_territory_total_armies()` in AI

### Medium Priority Improvements (M1-M31)
- **M1: Camera clamp on resize** - Clamp camera offset when resolution changes
- **M2: Dead debug code cleanup** - Removed 26 commented-out OLD DEBUG prints from sim/ files
- **M3-M4: Effect cleanup** - Added per-frame effect container cleanup and pool size enforcement
- **M5: MessageType enum** - Converted to `str, enum.Enum` with `from_string()` classmethod
- **M6: Sequence validation** - Added sequence number tracking per player in network protocol
- **M8-M9: AI code dedup** - Generic `_score_building()` method, garrison-check helper extracted
- **M10-M11: Dispatch tables** - Hero ability and client message handler dispatch dicts
- **M12-M13: God method split** - `execute_all_orders()` split into helpers; `_resolve_keep_battle()` split into phases
- **M14-M15: AI accuracy** - Dynamic building types, keep defense bonus in threat calc
- **M16-M28: Various** - UI helper extraction, null checks, bounds validation, return value checking
- **M29: Client validation** - Added `validate_message()` call in client
- **M30: Difficulty-aware AI** - Ability scores scaled by difficulty level
- **M31: Timeout docs** - Added relationship documentation and assertions for network timeouts

### Low Priority Improvements (L1-L17)
- **L1: Click priority docs** - Documented 11-level priority chain in mouse_handler.py
- **L2-L5: Constants/types** - Color organization, type hints on protocol, player color dedup
- **L6-L10: Validation** - Zoom bounds, settings type/load validation, resolution fallback
- **L11: Variable naming** - Standardized to `player_index` throughout
- **L12-L17: Documentation** - Protocol version, scaler ratios, timeout relationships

### New Files
- `utils/logger.py` - Structured logging module with RotatingFileHandler
- `tests/test_code_quality_fixes.py` - 55 tests validating all code quality fixes

### Test Results
- 55/55 tests passing

---

## 2026-02-07 - AI Logic Improvements (5 Fixes)

### Bug Fixes
- **H11: Standardized army API in AI** - Replaced legacy `game_state.armies.get()` with `get_territory_total_armies()` in `ai_hero.py` for all 8 enemy defense and capacity checks in ability scoring
- **M14: Dynamic building types** - Replaced hardcoded building type list in `ai_economy.py` with `game_state.building_types.keys()`
- **M15: Keep defense bonus in threat calc** - AI threat calculation now adds +10 effective defense for keeps; attack scoring uses +10 flat bonus instead of 1.2x multiplier

### Performance Improvements
- **M23: Cached scorer/analyzer instances** - `TerritoryScorer` and `ThreatAnalyzer` cached in `__init__` of 4 classes instead of per-call instantiation

### Enhancements
- **M30: Difficulty-aware ability scoring** - Ability scores multiplied by difficulty (Easy=0.5x, Normal=0.8x, Hard=1.0x) so Easy AI uses abilities less optimally

---

## 2026-02-06 - FPS Optimization Pass (8 Bottlenecks Fixed)

### Performance Improvements
- **crop_to_circle() 500x speedup** - Replaced O(n²) pixel loop with mask-based BLEND_RGBA_MULT
- **Hero bubble bounding box rejection** - Defiance, Haste, Safe Haven bubbles now skip expensive polygon containment check when outside bounding box
- **Movement arrow pre-indexing** - Eliminated O(n²) nested loop searching orders per route
- **Surface reuse** - UIRenderer modal overlays and production glow effects reuse surfaces instead of allocating each frame
- **Caching additions** - Rotated sidebar text, hero portrait scaling, 11 static text labels now cached

### Benchmark Results (1600x900)
| Scenario | Average FPS | Frame Time |
|----------|-------------|------------|
| Idle Map | 71.4 | 14.0ms |
| Hero Panel | 73.3 | 13.7ms |
| Late Game Stress (4p, 57 territories) | 41.3 | 24.2ms |
| Movement Arrows (20 orders) | 42.2 | 23.7ms |

### New Files
- `tests/test_fps_benchmark.py` - FPS benchmark suite (baseline, stress, regression tests)
- `tools/stress_test_generator.py` - Late-game scenario generator for performance testing

### Modified Files
- `rendering/helpers.py` - crop_to_circle mask optimization
- `main.py` - Bubble bounding box rejection, text/portrait caching
- `rendering/ui_renderer.py` - Reusable overlay surface
- `rendering/map_renderer.py` - Movement arrow route pre-indexing
- `ui/effects/production_glow_effect.py` - Surface reuse per effect

---

## 2026-02-06 - Production Glow Effect for Active Buildings

### Added
- **Production Glow Effect** - Visual feedback for buildings with active production
  - Rotating sunrays emanate from Barracks (training units) and Keep/Castle (training heroes)
  - Rays colored in the territory owner's faction color
  - Rays fade at edges for soft glow appearance
  - Gentle pulsing animation for visibility
  - Scales with camera zoom level
  - Effect automatically appears/disappears when training starts/completes

### Technical Details
- New file: `ui/effects/production_glow_effect.py` - ProductionGlowEffect class
- Updated: `rendering/map_renderer.py` - Added effect tracking, sync, update, and render methods
- Updated: `main.py` - Added sync/update calls in game loop, clear on restart
- Effect rendered behind building icons (before `draw_plots()`)

---

## 2026-02-04 - Campaign Mission 2: Early Eastern Conquests

### Added
- **New Campaign Mission** - "Early Eastern Conquests" with 9 territories and 4 factions
  - Human player (Green) starts in Lobardia
  - Elletic Tribes (Yellow) - 4 territories, awakens on large army or attack
  - Heilonic Tribes (Blue) - 2 territories, awakens when Elletic defeated or attacked
  - Chiefdom of Valeonia (Red) - 2 territories, awakens when both others defeated or attacked

- **Territory Filtering System** in `map_data.py`
  - `set_enabled_territories()` / `clear_enabled_territories()` - Limit visible territories
  - `set_territory_display_names()` / `get_display_name()` - Override territory names per mission

- **Dormant/Awakened AI System**
  - AI factions start dormant (3-second turns, no actions)
  - Awaken on triggers (attack, army count, other faction defeat)
  - Awakened AI trains Swordsmen and attacks player only (never other AI)

- **Cinematic Intro Sequence**
  - Camera zoom/pan animations to territories
  - Transmission overlay for narrative text
  - Timer bar introduction with 20-second pulsation highlight

- **Mission Features**
  - Quest tracking with completion markers
  - Delayed transmissions (wait for battle report to close)
  - Skipped turns for defeated factions
  - Victory sequence with fade and image
  - Flag icon remapping for faction colors

### Technical Details
- Files: `campaign_mission_2.py` (~1200 lines), updates to `map_data.py`, `main.py`
- Territory display names: "The Holy Land" → "Neimer Coast", etc.
- Special cascade: Attacking Valeonia awakens ALL other factions

---

## 2026-02-02 - Battle Report Survivor Count Fix

### Fixed
- **Battle Report showing wrong survivor count** - Report now shows actual survivors instead of estimates
  - Problem: `EnhancedBattleInterface` pre-calculated survivors using its own formula before battle resolution
  - Fix: Battle is now resolved when FIGHT is clicked, actual result passed to UI via `set_actual_battle_result()`
  - Surviving units are read from actual garrison data for precise unit-by-unit breakdown
  - Example: Battle with 3 units (Archer, Pikeman, Swordsman), 2 survived → now correctly shows which 2

- **AI selecting same unit for multiple movements** - Eliminated warning spam about duplicate unit IDs
  - Problem: When AI queued 3 moves from same territory, all got `unit_ids: [0]` (same unit)
  - Fix: Added `_selected_unit_ids` tracking in `sim_ai.py` to prevent double-selection
  - Each unit ID now only selected once per planning session

---

## 2026-02-02 - Victory Conditions Team-Based Fixes

### Fixed
- **Domination (45+) not working team-wise** - Victory now checks combined team territory count
  - Teams win when their combined territories reach 45+, not individual players
  - Solo players still win individually at 45+ territories
- **Total Conquest not working team-wise** - Victory now checks combined team territory count
  - Teams win when they control all territories together, not individual players
  - Solo players still win individually when controlling all territories
- **Capital Assault ally protection** - Allies can no longer accidentally eliminate each other
  - Added `are_allies()` check to all 5 elimination paths (4 sequential, 1 simultaneous)
  - Updated `_is_player_eliminated()` to only trigger when enemy captures capital

---

## 2026-02-02 - Capital Assault Victory Condition Fix

### Fixed
- **Capital Assault not working in Simultaneous Mode** - Players were not eliminated when their capital was captured
  - Added `_check_capital_assault_eliminations()` method to check if captured territory is a capital
  - Updated `_is_player_eliminated()` to also check for capital loss in Capital Assault mode
  - Added elimination checks after undefended territory capture and battle resolution
  - Added `check_victory()` calls after any elimination to properly detect game end

---

## 2026-02-01 - Research & Cancel Action Sync Fixes

### Fixed
- **Research Cancel Not Removing Orders** - Cancelling research now removes queued 'research' order from `sim_state.player_orders`
- **Research State Not Synced** - Host now broadcasts research state in SIM_ROUND_COMPLETE:
  - `player_tech_researched` - completed technologies per player
  - `research_in_progress` - current research with remaining turns
  - `player_tech_available` - unlocked techs in tree
  - `tech_effects` - all 10 derived effect arrays (cost discounts, strength bonuses)
- **Cancel Actions Not Removing Orders** - Fixed all cancel/demolish actions in sim mode:
  - Cancel building construction → removes 'build' order
  - Cancel unit training → removes 'train' order
  - Cancel hero training → removes 'train_hero' order
  - Cancel castle upgrade → removes 'upgrade_castle' order
  - Cancel research → removes 'research' order
  - Demolish barracks → removes 'train' orders for that barracks
  - Demolish keep → removes 'train_hero' orders for that keep
- **Hero Training Double-Speed on Client** - Removed duplicate `finish_hero_training()` call that caused double-decrement
- **Reinforce Ability Not Visible on Host** - Changed SIM_HERO_ABILITY handler to execute immediate abilities directly

### Added
- **Tech Effect Arrays Sync** - All technology bonuses now synchronized:
  - `royal_decree_discount`, `training_cost_discount`, `cavalry_cost_discount`
  - `archer_keep_strength_bonus`, `farm_destruction_gold_bonus`, `cavalry_strength_bonus`
  - `divide_conquer_bonus`, `barracks_cost_discount`, `barracks_full_refund`, `hero_keep_defense_bonus`

---

## 2026-02-01 - Comprehensive Debug System for Simultaneous Mode

### Added
- **sim_debug.py** - Centralized debug logging system for sim multiplayer mode
  - Configurable log levels: NONE, ERROR, NETWORK, SYNC, BATTLE, STATE, PHASE, DETAIL, ALL
  - Category-specific log methods: `sim_log.sync()`, `sim_log.battle()`, `sim_log.network()`, etc.
  - Multiplayer context awareness (HOST/CLIENT prefix)
  - Round number tracking in output
  - State summary helper for debugging sync issues
  - Easy enable/disable: `enable_verbose()`, `enable_sync_only()`, `disable_debug()`

### Changed
- **All sim files** - Replaced 100+ verbose `print()` statements with structured `sim_log` calls
  - Original debug output commented out (not deleted) for reference
  - New output is cleaner, categorized, and can be filtered by level
  - Sync-critical messages highlighted for easy identification

### Usage
```python
from simultaneous import sim_log, set_debug_level, SimDebugLevel

# Show all output (default)
set_debug_level(SimDebugLevel.ALL)

# Show only sync-related messages (for debugging multiplayer issues)
enable_sync_only()

# Disable all debug output (production)
disable_debug()
```

---

## 2026-02-01 - Multi-Client (3-4 Player) Validation Fixes

### Fixed
- **Player Index Bounds Validation** - All order handlers (movement, building, training) now validate player_index is in valid range `[0, num_players)`
- **SIM_PLAYER_READY Validation** - Added player_id bounds checking to prevent invalid player orders from being stored
- **3+ Player Fallback Warning** - Now logs warning when player_index field is missing in 3-4 player games (previously silently fell back to 2-player logic)

---

## 2026-02-01 - Multiplayer Simultaneous Mode Sync Fixes

### Fixed
- **Alliance Chooser Desync** - Replaced `random.choice()` with deterministic `min(candidates)` for tied armies
- **Hero Abilities Not Executed** - Implemented actual hero ability execution in sim mode via `game_state.activate_hero_ability()`
- **Hero Training Not Executed** - Implemented actual hero training execution in sim mode via `game_state.start_hero_training()`
- **Unit Composition Lost After Battle** - Added `surviving_units` to BATTLE_RESOLVE message, preserves Archers/Cavalry/Pikemen
- **Forced Defenders Not Synced** - Added `SIM_FORCED_DEFEND` broadcast for crossing conflict notifications
- **State Sync Gaps** - Enhanced SIM_ROUND_COMPLETE with authoritative data:
  - `player_gold` - prevents float/calculation divergence
  - `territory_owners` - ensures battle results synchronized
  - `eliminated_players` - for income/construction skip logic
- **Duplicate mark_ready Calls** - Added guard to prevent callback spam

### Changed
- **sim_ai.py** - Fixed hero orders to include required fields (territory, keep_plot, hero_type, ability_name)
- **sim_phase_manager.py** - Hero ability/training now call actual game_state methods
- **sim_state.py** - Added `on_forced_defend_callback` for host broadcasts

---

## 2026-02-01 - Multiplayer Expansion: 2-4 Players with AI & Alliances

### Added
- **Full 2-4 Player Multiplayer** - Expanded from 1v1 to support up to 4 players
  - Host + up to 3 clients via TCP
  - Configurable player slots (Human/AI/Empty)
  - Per-slot AI difficulty (Easy/Medium/Hard)
  - Team/alliance system with shared vision
  - Allied movement arrows visible to teammates

- **Lobby System Overhaul**
  - `network/lobby.py` - New LobbySlot and LobbyState classes
  - Player type dropdown (Human/AI Easy/Medium/Hard/Empty)
  - Color and team selection per player
  - Territory claiming with first-come-wins
  - Host kick functionality
  - Launch countdown system

- **Reconnection System**
  - Password-based authentication (8-char generated on join)
  - 5-minute reconnection window after disconnect
  - AI takes over immediately on disconnect
  - Full state sync on successful reconnect
  - `RECONNECT_REQUEST`, `RECONNECT_ACCEPT`, `RECONNECT_REJECT` messages

- **Disconnect Handling**
  - Client disconnect → AI takeover (game continues)
  - Host disconnect → Game ends for all clients
  - `PLAYER_DISCONNECT`, `AI_TAKEOVER` messages
  - Proper disconnect detection on client side

- **Network Protocol Extensions**
  - `MAX_CLIENTS = 3` (host + 3 = 4 players)
  - 14 new message types for lobby and reconnection
  - Multi-client broadcast with exclusion support
  - Per-player targeted messaging

### Changed
- **network/server.py** - Complete rewrite for multi-client support (~900 lines)
  - `select.select()` for multi-socket I/O
  - `ClientConnection` dataclass per client
  - `DisconnectedPlayer` for reconnection tracking
  - Thread-safe client dict with locking
  - `broadcast_message()`, `send_to_player()`, `kick_player()` methods
  - Reserved slots system for AI configuration

- **network/client.py** - Enhanced disconnect detection
  - `disconnected` flag set on host disconnect
  - `disconnect_reason` for user-facing messages
  - All disconnect paths properly flagged

- **network/territory_selector.py** - Expanded lobby UI
  - Moved from root to `network/` folder
  - Player slot configuration UI
  - AI difficulty dropdown
  - Host-only controls

- **main.py** - Multiplayer message handlers
  - `PLAYER_DISCONNECT` handler with AI takeover
  - `player_is_ai` list updated on disconnect
  - `disconnected_players` set for reconnection tracking

### Fixed
- **Server slot assignment** - Now respects lobby AI configuration
- **Double execution on client** - Only host triggers order execution
- **Client arrival tracking** - Uses phase_manager for proper sync
- **Alliance choice sync** - Host broadcasts to all clients
- **Round complete broadcast** - Clients receive SIM_ROUND_COMPLETE
- **Client disconnect isolation** - Single disconnect doesn't affect others
- **Battle resolution sync** - Includes alliance marker in BATTLE_RESOLVE
- **AI battle/alliance resolution** - Network sync for AI-resolved conflicts
- **Action blocking during resolution** - Building/training/research blocked
- **Client arrow persistence** - Proper cleanup between turns
- **Ghost army issues** - Clear ALL garrisons on battle resolve
- **Client as resolver** - Bidirectional sync, only host completes round
- **Building/training visibility** - Set current_player before remote orders
- **Battle UI multi-way display** - Show all attackers in neutral battles

### Documentation
- Updated `CODE_GUIDE.md` with comprehensive Network System section
- Updated `GAME_MECHANICS.md` with Multiplayer System section
- Updated `QUICK_REFERENCE.md` with network message types

---

## 2026-01-31 - Simultaneous Mode Bug Fixes & UI Improvements

### Fixed
- **Master Planner upgrades not increasing timer** - Fixed incorrect attribute name (`research_completed` → `player_tech_researched`) and tech IDs (`master_planner_1` → `tech_2_0`, `master_planner_2` → `tech_2_3`) in `sim_state.py`
- **Newly trained units starting as "Ready to Move"** - Moved `finish_training()` to run AFTER `start_planning_phase()` so newly spawned units keep their 'moved' status
- **Battle UI showing wrong sides** - Added `battle.attackers` list to properly identify attackers (left) vs defenders (right) in battle interface
- **Allied defender stealing territory** - Defensive victories now correctly keep original owner in control instead of showing alliance choice popup
- **Timer expiry not executing orders** - Added unit status reset when timer expires (matches End Turn button behavior)
- **Territory hover during alliance popup** - Disabled territory highlighting while alliance choice popup is visible

### Changed
- **Alliance Choice UI** - Redesigned using `IGOptMenuBG.png` background and `GMenuButton.png` buttons
  - Player names now displayed in their player color
  - Removed army count display and color squares
  - Added generous padding and proper spacing
  - White separator line below "Choose the Territory Owner" title

### Documentation
- Updated `GAME_MECHANICS.md` with defensive battle rules, newly trained unit status, alliance UI
- Updated `CODE_GUIDE.md` with simultaneous mode modification guidance

---

## 2026-01-30 - Simultaneous Turn Mode

### Added
- **Simultaneous Turn Mode** - New alternative game mode where all players plan at the same time
  - All players queue orders simultaneously during planning phase
  - Orders hidden from other players until execution
  - All movements animate simultaneously during execution phase
  - Available in both single-player (vs AI) and multiplayer

- **simultaneous/ Module** (~1,200 lines total)
  - `sim_state.py` - SimultaneousGameState wrapper with per-player order queues, ready flags, timers
  - `sim_phase_manager.py` - Phase transitions, order execution coordination
  - `sim_conflict_resolver.py` - Crossing army conflict resolution, multi-army battles
  - `sim_alliance_handler.py` - Allied territory capture, ownership assignment, overflow handling
  - `sim_ai.py` - AI adapter with simulated thinking delay

- **UI Components for Simultaneous Mode**
  - Turn Mode dropdown in game setup screens (Sequential/Simultaneous)
  - Planning timer per-player (60s base + Master Planner bonuses)
  - "Waiting..." button state when player is ready
  - "Waiting for: X, Y" indicator showing players still planning
  - Blue particle alliance marker (click to assign territory ownership)
  - Red glow overflow indicator for territories exceeding army limit

- **Network Protocol Extensions**
  - SIM_PLAYER_READY, SIM_ALL_READY, SIM_TIMER_UPDATE messages
  - SIM_BATTLE_RESULT, SIM_ALLIANCE_CHOICE, SIM_ROUND_COMPLETE messages
  - turn_mode parameter in SETUP_COMPLETE message

### Changed
- Added `game_mode` flag to GameState (`'sequential'` or `'simultaneous'`)
- main.py now initializes SimultaneousGameState when mode is simultaneous
- End Turn button behavior changed for simultaneous mode (marks ready instead of ending turn)

---

## 2026-01-27 - Campaign Screen & Multiplayer UI Polish

### Added
- **Campaign Screen** - New `campaign_screen.py` module
  - Campaign button in Main Menu is now fully clickable with matching design (no longer grayed out placeholder)
  - Opens campaign screen with `CampaignBG.png` background
  - 4 mission buttons using `CampaignBTN.png` with proper aspect-ratio cropping
  - "Return to Main Menu" button at bottom, styled identically to Integrated Setup
- **Mission Screen** - `MissionScreen` class in `campaign_screen.py`
  - Tabbed navigation: Briefing, Lore, Objectives, Characters
  - Scrollable text content panel using `OptionsMenuBG.png`
  - Selected tab highlighted with brighter styling
  - Return button (bottom-left) and Launch Chapter button (bottom-right, not yet functional)
  - Placeholder mission data for 4 chapters
- **Campaign Text Tool** - New `Campaign_Text_Tool.py` standalone WYSIWYG editor
  - Left panel: text editor with line numbers, cursor, selection, syntax highlighting for `##` headers
  - Right panel: live preview matching in-game MissionScreen rendering
  - Top bar: mission and tab selector buttons
  - Supports Ctrl+S save, Ctrl+C/V/X copy/paste, Ctrl+A select all, scrolling
  - Reads/writes `campaign_data.json`
- **campaign_data.json** - Externalized mission text data (was hardcoded in campaign_screen.py)
  - `campaign_screen.py` now loads MISSION_DATA from this JSON file
- **UI Click Sounds** - Added `sound_manager.play_ui_click()` to all multiplayer screens
  - `territory_selector.py` - Launch, Return, dropdown toggles, dropdown item selections, territory map clicks
  - `integrated_setup.py` - Territory map clicks (buttons/dropdowns already had sounds)

### Changed
- Removed placeholder/coming-soon logic from Campaign button in `main_menu.py`
- Added campaign action handling in `main.py` main loop
- **Host Waiting Screen** - Increased OptionsMenuBG panel size for better text/button padding (width 840, expanded top/bottom margins)

---

## 2026-01-24 - Territory Expansion & Map Overhaul

### Changed
- **Territory System Overhaul** - Complete rebuild from scratch
  - Increased territories from 39 to 57 (+18 territories)
  - Split 6 large regions into 19 smaller territories:
    - Azincourne → Courtieux, Aelatania, Londia, Northern Heilonia, Duchy of Daurels (5)
    - Naragonthid → Valeonia, Velognia, Leuse Valley, Nordica (4)
    - Elletia → Lobardia, Lentria, Elland (3)
    - Quil'en → Amorian Shores, Southern Quil'en, Northern Quil'en (3)
    - South Affrancia → March of Auverne, Affrancian Uplands (2)
    - North Affrancia → Lunedale, Free Cities (2)
  - Added 5 completely new territories: Zjoal Islands, Leimarch, Fahlaan Dunes, The Holy Land, Elletian Isles
  - Wiped and rebuilt all territory data for complete consistency:
    - `territory_polygons.json` - All 57 polygons redrawn
    - `economic_data.json` - All 57 economic tiers reassigned
    - `plots.json` - All 57 building plot locations placed
    - `territory_bonuses.json` - All 57 territorial bonuses redistributed
    - `map_data.py` ADJACENCIES - All 57 adjacency relationships redefined
  - Updated `Polygon_Tool.py` TERRITORIES list to 57 territories
  - Backup created: `data_backup_2026-01-24/` (preserves original 39-territory data)

### Notes
- Domination victory threshold updated to 45 territories (~79% of 57 total)
- Average income per territory target: ~20 gold
- Territorial bonuses evenly distributed (~6-7 territories per bonus type)
- All existing 33 territories (unchanged names) retained with redrawn polygons
- Map image remains at 1269×903 pixels (ORIGINAL_MAP_WIDTH × ORIGINAL_MAP_HEIGHT)

## Phase 5+ - AI & Multiplayer Systems (December 2025 - January 2026)

### Added
- **AI Player System** (3,247 lines)
  - `ai_player.py` - Main AI controller with threading
  - `ai_strategy.py` - Strategic evaluation and threat detection
  - `ai_military.py` - Combat decisions and troop movement
  - `ai_economy.py` - Building and technology decisions
  - `ai_hero.py` - Hero training and ability management

- **Network/Multiplayer System** (1,160 lines)
  - `network/server.py` - TCP server for 1v1 multiplayer
  - `network/client.py` - Network client
  - `network/protocol.py` - Message serialization
  - `network/message_queue.py` - Thread-safe message queue

- **Enhanced UI System** (1,100+ lines)
  - `main_menu.py` - Main menu with game mode selection
  - `integrated_setup.py` - Setup window with map preview
  - `multiplayer_setup.py` - Multiplayer configuration
  - `ui/effects/` - 6 effect modules for visual polish

- **Settings & Configuration**
  - `settings_manager.py` - Game settings persistence
  - Enhanced configuration system

- **Taxation System** (January 2026)
  - 5-level taxation system (0%, 25%, 50%, 75%, 100%)
  - Configurable during game setup (single-player and multiplayer)
  - Applied at turn end before income collection
  - Deducts percentage of leftover gold from previous turn
  - Encourages active resource spending each turn
  - UI display in top panel (when taxation > 0%)
  - Game log messages showing tax deductions
  - Modified files: `integrated_setup.py`, `multiplayer_setup.py`, `game_state.py`, `main.py`, `rendering/ui_renderer.py`

- **Territorial Bonus System** (January 2026)
  - 9 bonus types assigned to 39 territories
  - Global stacking bonuses based on territory ownership
  - Bonus types: Income (+3%), Tech Cost (-5%), Unit Cost (-5%), Hero Cost (-3%), Pikeman/Archer/Swordsman/Cavalry Strength (+10%), Building Cost (-15%)
  - Automatic recalculation on territory conquest/loss
  - UI bonus button in top panel (right of phase indicator) with hover tooltip
  - Territory info displays bonus type in bottom panel
  - Bonus button scales with resolution for proper display at all sizes
  - Assignment tool (`Bonus_Tool.py`) for configuring territory bonuses
  - Data stored in `territory_bonuses.json` (39 pre-configured assignments)

- **Sound System** (January 2026)
  - Full audio system with pygame.mixer integration
  - Sound categories: UI clicks, army composition, hero voice lines, event notifications
  - **UI Sounds**:
    - DefaultMouseClick.mp3 for all menu buttons (main menu, setup screens, in-game menus)
    - Army composition UI opening (7 random sounds from armycomp folder)
  - **Event Sounds**:
    - ResearchCompleted.mp3 when research finishes (2.5x volume - very loud)
    - CastleCompleted.mp3 when castle upgrades finish (1.5x volume)
  - **Hero Voice Lines**:
    - Seledra Rennervail: recruitment sound + 5 random selection voice lines
    - Anti-repeat logic prevents same voice line twice in a row
  - **Advanced Features**:
    - Sound queue system for sequential playback (Research → Castle → Hero priority)
    - Overlap prevention (same category won't play while current sound playing)
    - Per-category volume control with individual sound adjustments
    - Player-specific sounds (multiplayer: only local player hears their actions)
  - Modified files: `sound_manager.py` (new), `global_sound.py` (new), `main.py`, `game_state.py`, `main_menu.py`, `integrated_setup.py`, `multiplayer_setup.py`
  - Documentation: Added comprehensive Sound System section to `CODE_GUIDE.md`

### Changed
- **Visual Improvements** (January 2026)
  - Removed dark overlay on territories with moved units to avoid confusion with capital territory highlighting
  - Capital territories now clearly distinguished by 30% darkened color (only visual indicator using dimmed appearance)
  - Modified file: `rendering/map_renderer.py` (removed lines 577-588)

- **Top Panel Resource Slots** (January 2026)
  - Visual resource display replacing text-based stats in top panel
  - 4 slots: Taxation, Command Limit, Gold, Income (left to right)
  - Centered between Territory Bonus button and right edge
  - Always shows LOCAL player's stats (not current turn player in multiplayer/AI games)
  - Hover tooltips with explanations (no visual hover highlight)
  - Rectangular slot icons (65% height, 1.4x wider than square)
  - Assets: `ResourceSlot.png`, `TXTPTS.png`, `CMDPTS.png`, `GLDPTS.png`, `INCPTS.png`
  - Modified files: `main.py` (asset loading), `rendering/ui_renderer.py` (rendering + tooltips)

- **Action Log Player Filtering** (January 2026)
  - Filters game messages to show only LOCAL player's events
  - Replaces "Player X" with actual player names in display (e.g., "Editoreus", "AI (Medium)")
  - Security: Prevents players from naming themselves "Player 2" to see opponent messages
  - Uses regex pattern matching for "Player X" + custom name detection
  - Chat already uses actual player names (no changes needed)
  - Modified files: `rendering/ui_renderer.py` (lines 1106-1210)

### Fixed
- **Technology Tab Crash** - Added missing `current_player` variable in `_draw_technology_content()` method (`rendering/ui_renderer.py:1587`)
- **Persistent Unit Tooltips** - Unit tooltips (Pikeman, Archer, Swordsman, Cavalry) no longer persist when hovering over UI panels. Fixed by:
  - Adding `in_bottom_ui` check to tooltip rendering logic (`main.py:9170`)
  - Adding hover clearing logic for army unit buttons (`main.py:6958-6961`)
  - Tooltips now only show when actively hovering over the actual button
- **Action Queue Badge Removed** - Removed red notification badge from Action Queue tab button for cleaner UI (`rendering/ui_renderer.py:2189-2200`)
  - Integration points: Income calculation, cost methods (units/buildings/heroes/tech), strength calculation, refund calculations
  - Modified files: `map_data.py`, `game_state.py`, `rendering/ui_renderer.py`, `main.py`
  - New files: `territory_bonuses.json`, `Bonus_Tool.py`

### Changed
- Codebase expanded from ~13,800 to ~30,000 lines
- main.py grew from 5,309 to 9,750 lines
- game_state.py grew from 1,732 to 7,425 lines

---

## Phase 4 - Refactoring & Modularization (January 2026)

### Goals Achieved
- ✅ Simplified main.py event loop (77% reduction in complexity)
- ✅ Extracted rendering logic to dedicated modules
- ✅ Separated input handling from game logic
- ✅ Improved code organization and maintainability

### Results
- **Total reduction:** 2,037 lines extracted from main.py
- **main.py:** 8,093 → 5,309 lines (34.4% reduction)
- **game_state.py:** 1,845 → 1,732 lines (6.1% reduction)
- **New modules created:**
  - `rendering/map_renderer.py` - Territory and map rendering (992 lines)
  - `rendering/ui_renderer.py` - UI panels and overlays (1,236 lines)
  - `rendering/helpers.py` - Drawing utilities (755 lines)
  - `input/mouse_handler.py` - Mouse input delegation (192 lines)

### Bugs Fixed During Refactoring
1. Territory hover not working after modularization
2. UI rendering order issues (panels behind map)
3. Camera offset not passed to renderers
4. Movement arrow click detection broken
5. Plot rendering optimization needed
6. Tooltip positioning incorrect after panel extraction
7. Selected territory highlight lost
8. Button click detection broken in UI renderer
9. Income panel not showing building counts

### Lessons Learned
- **Separation of concerns is critical** - Game logic, rendering, and input should never mix
- **Pass by reference carefully** - Ensure data flows correctly between modules
- **Test incrementally** - Small commits caught bugs faster
- **Document cross-module dependencies** - Helps future maintenance

### Patterns Established
- **Delegator Pattern** for input handling
- **Renderer Pattern** with helper utilities
- **State-View Separation** between GameState and Game class
- **Module Docstrings** with architecture diagrams

---

## Earlier Phases

See git history for detailed commit logs of Phases 1-3.
