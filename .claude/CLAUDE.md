# Claude Code Project Guide

## Project Overview
This document provides context and guidelines for working with this project using Claude Code.

## Project Structure

**AvareonWar** is a turn-based strategy game built with Python and Pygame. ~70,000 lines of code across ~60 modules.

### Directory Layout

```
AvareonWar/
├── [Root: 33 Python modules]    # Core game files (~40,000 lines)
├── game_state/                  # Core game logic package (8 files, mixin decomposition)
├── assets/                      # Images, fonts, icons, sounds (380+ files)
├── config/                      # Game constants, configuration, font manager
├── docs/                        # Documentation (8 markdown files)
├── input/                       # Mouse, keyboard, camera handlers
├── network/                     # Multiplayer (server, client, protocol, lobby, setup, selector)
├── rendering/                   # Map and UI rendering systems
├── simultaneous/                # Simultaneous turn mode system (7 files)
├── Logs/                        # Per-game JSON log files (auto-created)
├── tests/                       # Unit tests (pytest)
├── tools/                       # Development utilities
├── ui/                          # UI scaling and effects (12 effect modules)
├── maps/                        # Multi-map data (manifest + per-map directories)
│   ├── manifest.json            # Map registry (id, display_name, has_background)
│   ├── avareon/                 # Original map data (polygons, plots, economy, bonuses, adjacencies)
│   ├── azincournean_highlands/  # Placeholder map
│   ├── naragonthid/             # Placeholder map
│   ├── far_east/                # Placeholder map
│   └── nordian_mountains/       # Placeholder map
├── utils/                       # Utility functions (colors, logger, surface_utils)
└── CHANGELOG.md                 # Project history and refactoring phases
```

### Core Files (Root Directory)

**Main Entry Points:**
- [main.py](main.py) (~13,000 lines) - Game loop, pygame init, event handling, rendering orchestration
- [game_state/](game_state/) - Core logic package (8 files, mixin decomposition):
  - [__init__.py](game_state/__init__.py) (~1,064 lines) - GameState class, turn mgmt, coordinates, chat, diplomacy
  - [data_definitions.py](game_state/data_definitions.py) (~683 lines) - HERO_TYPES, BUILDING_TYPES, technologies, BONUS_TYPES
  - [garrison.py](game_state/garrison.py) (~796 lines) - GarrisonMixin: multi-garrison system, legacy sync
  - [heroes.py](game_state/heroes.py) (~1,467 lines) - HeroMixin: training, abilities, queries
  - [buildings.py](game_state/buildings.py) (~1,070 lines) - BuildingMixin: construction, training, upgrades, tech
  - [economy.py](game_state/economy.py) (~390 lines) - EconomyMixin: income, costs, taxation, bonuses
  - [military.py](game_state/military.py) (~2,767 lines) - MilitaryMixin: orders, battles, movement, casualties
  - [victory.py](game_state/victory.py) (~284 lines) - VictoryMixin: victory checks, elimination
- [map_data.py](map_data.py) - Multi-map data loader (polygons, adjacencies, plots, economy, bonuses, fortress territories)

**Setup & Menus:**
- [main_menu.py](main_menu.py) - Main menu with game mode selection
- [integrated_setup.py](integrated_setup.py) - Setup window with map preview, territory selection
- [campaign_screen.py](campaign_screen.py) - Campaign screen with background and return button
- [recap_screen.py](recap_screen.py) - Post-game recap/statistics screen (tabbed table UI)
- [loading_screen.py](loading_screen.py) - Loading screen with progress bar for deferred asset loading + multiplayer sync

**Sound & Music:**
- [sound_manager.py](sound_manager.py) - Sound effect management and playback
- [global_sound.py](global_sound.py) - Sound loading, deferred asset tasks
- [music_manager.py](music_manager.py) - Background music system (menu/game/recap categories, pygame.mixer.music)

**Campaign Utilities:**
- [campaign_utils.py](campaign_utils.py) - Shared campaign mission utility functions

**Battle Reports:**
- [ui/battle_report_popup.py](ui/battle_report_popup.py) - On-map defender-side battle summary popups (DEFENDED/LOST, Detail + Close buttons)

**Players Window (Gold Transfer UI):**
- [players_window.py](players_window.py) - Non-pausing modal listing all players (Name/Controller/Team/Color/Status columns) with ally gold-transfer input + Send button

**Player Level System:**
- [player_level.py](player_level.py) - Player level/XP logic, tiered progression formula, persistence, end-of-game calculation

**Game Logging:**
- [game_logger.py](game_logger.py) - Per-game JSON logging (custom/multiplayer only), writes to Logs/ folder
- [sync_logger.py](sync_logger.py) - Multiplayer state sync verification logging, action history, turn snapshots, desync diffs, writes to Logs/sync/

**Replay System (3 files):**
- [replay_recorder.py](replay_recorder.py) - Records game state snapshots in memory, saves gzip-compressed JSON to Replays/ folder
- [replay_viewer.py](replay_viewer.py) - Standalone replay viewer with map rendering, timeline, POV switching, playback controls
- [replay_browser.py](replay_browser.py) - File browser listing saved replays with metadata, watch/delete actions (campaign house style - shares its layout with save_browser.py)

**Campaign Save System (2 files):**
- [save_manager.py](save_manager.py) - Campaign save/load: serialize/deserialize GameState + mission state, file I/O, gzip JSON in Saves/
- [save_browser.py](save_browser.py) - Saved games browser screen with scrollable list, load/delete actions (campaign house style - shares its layout with replay_browser.py)

**Achievement System (2 files):**
- [achievement_manager.py](achievement_manager.py) - Achievement definitions, stat tracking, persistence, checking
- [achievement_panel.py](achievement_panel.py) - Achievement list panel UI (category filters, search, scrollable list)

**Campaign Missions:**
- [tutorial_mission.py](tutorial_mission.py) - Tutorial mission (Lobardia unification)
- [campaign_mission_2.py](campaign_mission_2.py) - Early Eastern Conquests (9 territories, 4 factions, dormant AI)
- [campaign_mission_3.py](campaign_mission_3.py) - Storms above the West (campaign chapter 3)
- [campaign_mission_4.py](campaign_mission_4.py) - Domination (21 territories, 4 factions, hybrid custom AI)
- [campaign_mission_5.py](campaign_mission_5.py) - The First War (17 territories, 3 factions, allied team vs empire)
- [campaign_mission_6.py](campaign_mission_6.py) - The Second War (33 territories, 3 factions, 4 sequential quests, dynamic AI)
- [campaign_mission_7.py](campaign_mission_7.py) - The Fall (41 territories, 2 factions, garrison-enforced AI)

**AI System (5 files):**
- [ai_player.py](ai_player.py) - Main AI controller
- [ai_strategy.py](ai_strategy.py) - Strategic evaluation, threat detection
- [ai_economy.py](ai_economy.py) - Building decisions, tech upgrades
- [ai_military.py](ai_military.py) - Combat, troop movement, tactics
- [ai_hero.py](ai_hero.py) - Hero training and abilities

**Simultaneous Mode (7 files):**
- [simultaneous/sim_state.py](simultaneous/sim_state.py) - SimultaneousGameState wrapper
- [simultaneous/sim_phase_manager.py](simultaneous/sim_phase_manager.py) - Phase transitions
- [simultaneous/sim_conflict_resolver.py](simultaneous/sim_conflict_resolver.py) - Crossing armies, battles
- [simultaneous/sim_alliance_handler.py](simultaneous/sim_alliance_handler.py) - Allied territory capture
- [simultaneous/sim_ai.py](simultaneous/sim_ai.py) - AI adapter for simultaneous mode
- [simultaneous/sim_debug.py](simultaneous/sim_debug.py) - Debug utilities for simultaneous mode

**Cutscene System:**
- [cutscene_player.py](cutscene_player.py) - Cutscene player (Ken Burns camera pan/zoom/rotate, crossfade, audio, subtitles)
- [cutscene_exporter.py](cutscene_exporter.py) - MP4 export: offscreen frame rendering + ffmpeg encoding (used by Cutscene_Tool)

**Development Tools (8 files):**
- [Adjacency_Tool.py](Adjacency_Tool.py) - Territory adjacency editor
- [Economic_Tool.py](Economic_Tool.py) - Economy data editor
- [Plot_Tool.py](Plot_Tool.py) - Building plot location editor
- [Polygon_Tool.py](Polygon_Tool.py) - Territory polygon editor
- [Bonus_Tool.py](Bonus_Tool.py) - Territorial bonus assignment editor
- [Campaign_Text_Tool.py](Campaign_Text_Tool.py) - Campaign mission text WYSIWYG editor
- [Cutscene_Tool.py](Cutscene_Tool.py) - Cutscene editor (camera rects, audio, subtitles)
- [tools/stress_test_generator.py](tools/stress_test_generator.py) - Late-game scenario generator for FPS testing
- [tools/gif_to_spritesheet.py](tools/gif_to_spritesheet.py) - GIF to spritesheet converter

**Performance Tests:**
- [tests/test_fps_benchmark.py](tests/test_fps_benchmark.py) - FPS benchmark suite (run with `py -m pytest tests/test_fps_benchmark.py -v -s`). Covers idle/stress plus zoom, pan, production-glow and entity-density scenarios. Pass `BENCH_LABEL=x BENCH_OUT=file.json` to record results for before/after comparison. **Camera-driven scenarios must change state via `before_frame`** — rendering the same frame N times measures nothing, since every camera-keyed cache hits after frame 1.
- [tests/test_camera_zoom.py](tests/test_camera_zoom.py) - Smooth (eased) mouse-wheel zoom behaviour
- [tests/test_resolution_caches.py](tests/test_resolution_caches.py) - Renderer caches must follow `scale_factor` across resolution changes
- [tests/test_unit_context_menu.py](tests/test_unit_context_menu.py) - Right-click context menu on the army composition unit icons
- [tests/test_battle_bar_volley.py](tests/test_battle_bar_volley.py) - Volley-based battle bar animation (chunk split, determinism, skip, mirrored geometry)
- [tests/test_battle_interface_integration.py](tests/test_battle_interface_integration.py) - EnhancedBattleInterface wiring (state machine, derived duration, retarget, skip)
- [tests/test_campaign_outro_cutscene.py](tests/test_campaign_outro_cutscene.py) - Campaign mission exit sentinels: outro cutscene plays on victory only
- [tests/test_battle_reports.py](tests/test_battle_reports.py) - Battle Report capture rules (tie path, Keep-only defence, Champion of the People, hero-ability guard)
- [tests/test_battle_report_popup.py](tests/test_battle_report_popup.py) - Popup text/geometry and the report-only battle interface
- [tests/test_battle_report_integration.py](tests/test_battle_report_integration.py) - Battle Report wiring against a real `Game`
- [tests/test_battle_report_network.py](tests/test_battle_report_network.py) - Battle Reports reaching a defending multiplayer client
- [tests/test_drawing_helpers.py](tests/test_drawing_helpers.py) - `draw_feedback_button()` fallback when its background image is missing

**Configuration:**
- [network_config.py](network_config.py) - Network constants
- [settings_manager.py](settings_manager.py) - Game settings persistence
- [display_utils.py](display_utils.py) - Centralized display-mode creation (resolution, fullscreen, VSync) + frame-cap resolution. All `set_mode()` calls must go through this.

### Key Subsystems

**Rendering (~6,832 lines):**
- [rendering/map_renderer.py](rendering/map_renderer.py) (~3,690 lines) - Territory overlays, plots, arrows, battle markers
- [rendering/ui_renderer.py](rendering/ui_renderer.py) (~2,553 lines) - UI panels, buttons, info displays
- [rendering/panel_renderer.py](rendering/panel_renderer.py) - Panel layout
- [rendering/helpers.py](rendering/helpers.py) (~527 lines) - Drawing utilities

**Input Handling:**
- [input/mouse_handler.py](input/mouse_handler.py) (~236 lines) - Mouse input delegator
- [input/keyboard_handler.py](input/keyboard_handler.py) - Keyboard handling
- [input/camera_handler.py](input/camera_handler.py) - Camera/viewport management

**Networking:**
- [network/server.py](network/server.py) - TCP server for multiplayer (up to 4 players)
- [network/client.py](network/client.py) - Network client
- [network/protocol.py](network/protocol.py) - Message serialization
- [network/message_queue.py](network/message_queue.py) - Thread-safe queue
- [network/upnp.py](network/upnp.py) - UPnP port forwarding and public IP detection for internet play
- [network/lobby.py](network/lobby.py) - Multiplayer lobby management
- [network/multiplayer_setup.py](network/multiplayer_setup.py) - Multiplayer configuration UI
- [network/territory_selector.py](network/territory_selector.py) - Multiplayer territory selection UI

**UI & Effects:**
- [ui/scaler.py](ui/scaler.py) - Dynamic UI scaling
- [ui/effects/](ui/effects/) - 14 effect modules (battle, sparkles, turn announcements, hero ability burst/arc/polygon/silence wave, alliance markers, castle upgrade, production glow, chat notifications, etc.)

**Configuration:**
- [config/constants.py](config/constants.py) - All game constants (window, colors, timing, camera)
- [config/font_manager.py](config/font_manager.py) - Font loading and caching

### Data Files (JSON)

- `economic_data.json` - Territory economy definitions (root-level = Avareon, backward compat)
- `territory_polygons.json` (~1.6 MB) - Map geometry (root-level = Avareon, backward compat)
- `plots.json` - Building location coordinates (root-level = Avareon, backward compat)
- `territory_bonuses.json` - Territory bonus assignments (root-level = Avareon, backward compat)
- `maps/manifest.json` - Map registry (all available maps)
- `maps/<map_id>/` - Per-map data: territory_polygons.json, plots.json, economic_data.json, territory_bonuses.json, adjacencies.json, fortress_territories.json
- `campaign_data.json` - Campaign mission text data (edit with Campaign_Text_Tool.py)
- `cutscene_data.json` - Cutscene definitions per mission (edit with Cutscene_Tool.py)
- `config.json` - Game settings persistence

**Important:** Edit map data with their respective tools using `--map <map_id>` for non-default maps (Economic_Tool.py, Polygon_Tool.py, Plot_Tool.py, Cutscene_Tool.py).

### Assets

- `assets/fonts/` - Cinzel font family (6 weights)
- `assets/heroes/` - 10 hero images + 26 ability icons
- `assets/cutscenes/` - Cutscene background images and audio files
- `assets/mapicons/` - Units, buildings, flags, markers
- `assets/upgrades/` - 23 upgrade icons
- `assets/achievements/` - Achievement icons, preview images, reward icons
- `assets/sounds/` - Sound effects (army, general, heroes, structures, transmissions)
- `assets/music/` - Background music tracks (7 MP3 files: menu, game, recap)
- `assets/CampaignMaps/` - Campaign map images
- UI images: panels, backgrounds, logos, buttons

### Documentation

**Essential Docs:**
- [docs/README.md](docs/README.md) - Project overview, setup instructions, learning path
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Design patterns, diagrams, cross-module relationships
- [docs/CODE_GUIDE.md](docs/CODE_GUIDE.md) - **LIVING KNOWLEDGE BASE** - Module-specific "when to modify" guidance
- [docs/GAME_MECHANICS.md](docs/GAME_MECHANICS.md) - Game rules and balance (consolidated reference)
- [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) - Development workflows, testing checklists, common tasks
- [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) - Fast lookups, stat tables, common methods
- [docs/USER_STORIES_PROGRESS.md](docs/USER_STORIES_PROGRESS.md) - Feature tracking and project status
- [docs/TESTING_PLAN_MULTIPLAYER_FIXES.md](docs/TESTING_PLAN_MULTIPLAYER_FIXES.md) - Multiplayer testing plan
- [docs/PERFORMANCE_ROADMAP.md](docs/PERFORMANCE_ROADMAP.md) - Deferred performance work, with measurements and rationale. **Read before starting any optimization** — several obvious-looking wins are now worthless.

**Project History:**
- [CHANGELOG.md](CHANGELOG.md) - Version history, refactoring phases, major changes
- [PATCHNOTES.md](PATCHNOTES.md) - **Player-facing** release notes. Written for players, not
  developers: describe what changes in the game, never how it was implemented. Internal work
  (tests, refactors, docs) belongs in CHANGELOG.md only.

### Architecture

**Data Flow:**
```
User Input → Input Handler → Game Method → Game State → Render Loop → Display
```

**Module Dependencies:**
```
main.py (orchestrator)
├── game_state/ (game logic package — 6 mixins + data)
├── rendering/ (visualization)
├── input/ (user input)
├── network/ (multiplayer)
├── ai_player.py (AI control)
└── config/ (constants)
```

**Design Patterns:**
- Separation of concerns (logic vs rendering vs input)
- Single responsibility per module
- Data-driven design (JSON + editor tools)

## Development Guidelines

### Python Executable
- **Always use `py` (Windows py launcher), not `python` or `python3`** — e.g. `py -m pytest`, `py script.py`

### Agent Model
- When launching subagents via the Task tool, always use `model: "opus"` to ensure all agents run on Opus 4.6.

### Code Changes
- Always insert comments in code explaining purpose and goal of changes
- Code comments = basic inline documentation
- Major architectural/usage documentation goes in CODE_GUIDE.md

### Coding Best Practices (Learned from QA Audits)

These rules were derived from ~100+ bugs found across 8 audit rounds. **Follow strictly.**

#### Data Structure Changes
- **Update ALL consumers when changing tuple/list formats.** If you change a 2-tuple `(type, turns)` to a 3-tuple `(type, turns, cost)`, grep the ENTIRE codebase for every unpack site. This was the #1 recurring bug — missed unpack sites caused crashes and silent rendering failures.
- **Prefer index access over destructuring** for tuples that may evolve: use `entry[0]` instead of `type, turns = entry`. Index access survives format changes; destructuring crashes.
- **Update comments** that document tuple/dict formats (e.g., `# Format: (building_type, turns_remaining)`) whenever the format changes.

#### Deferred Actions & Refunds
- **Store actual cost paid with queued/deferred actions.** Training queue stores `(unit_type, turns, cost_paid)`, research stores `cost_paid` in its dict. Never recalculate refund amounts — territorial bonuses, hero effects, or tech discounts may have changed since the gold was originally deducted.
- **This applies to any "pay now, refund later" pattern:** construction, training, research, upgrades.

#### Dual State Systems (game_state + sim_state)
- **Always sync both states.** When `game_state` modifies player status (elimination, victory), `sim_state` must be notified too. Battle-based eliminations in sim mode were missed because `resolve_battle()` only calls `game_state.eliminate_player()`, not `sim_state.eliminate_player()`.
- **Check all code paths.** Uncontested captures, battle victories, and network sync are 3 separate paths that all need the same logic.
- **Don't call `.get()` on lists.** `player_teams` is a list, not a dict — use index access with bounds checking, not `.get()`.

#### Rendering & Pygame
- **Never create `pygame.Surface` per-frame.** Cache overlay surfaces keyed by size. Use `_get_cached_text()` instead of `font.render()`. Existing caches: `_ui_icon_cache`, `_text_cache`, `_hero_overlay_cache`, `_cached_building_overlays`, `_cached_training_overlays`.
- **Don't `.copy()` cached surfaces unnecessarily.** Only copy when the surface will be modified in-place (e.g., `BLEND_RGBA_MULT` darkening). If you're just blitting it onto another surface, use it directly.
- **Don't share cached surfaces between functions that need different surface types.** SRCALPHA vs non-SRCALPHA surfaces are incompatible — use separate cache variables (e.g., `_cached_victory_overlay` vs `_cached_victory_seq_overlay`).
- **All `pygame.image.load()` calls need:** (1) `.convert_alpha()` for PNG transparency performance, (2) `try/except pygame.error` with fallback to `None`.
- **Use `BLEND_RGBA_MULT`** (not `BLEND_RGB_MULT`) for tint overlays — RGB_MULT ignores alpha channel.
- **Clear button rects per-frame** in `draw_bottom_ui()` to prevent ghost clicks from stale rects.
- **`set_alpha()` on pooled/cached surfaces is permanent** — always `.copy()` before modifying alpha, or reset alpha when returning to pool.
- **Bounds-check UI content rendering.** Scrollable lists, action logs, chat messages — always check `if y >= max_y: break` to prevent rendering past container boundaries.
- **Scale ALL visual effects with zoom/ui_scale.** Glow radii, marker sizes, hover highlights — if one code path scales with `ui_scale`, all related paths must too. Inconsistent scaling causes visuals to appear wrong at different zoom levels.

#### Resolution Changes (`apply_display_settings`)
- **Must mirror `__init__` setup.** Any state computed during init (ui_scale, fonts, layout attributes, helpers, cached font sizes) must be recomputed when resolution changes.
- **Use `round()` not `int()`** for polygon/center/plot rescaling (matches `__init__` for smooth edges).
- **Invalidate all caches** (icon, text, font, overlay) after resolution change.

#### Campaign Missions
- **Defeat must return `'exit_campaign_defeat'`, never `'exit_campaign'`.** The victory
  sentinel `'exit_campaign'` is what makes `main.py` play the outro cutscene. Sharing one
  sentinel across both branches played the victory cinematic after a defeat in missions 2-7.
  See "Mission Exit Contract" in CODE_GUIDE.md.
- **Cap `delta_time` in every mission `update()` method.** Use `delta_time = min(delta_time, 0.05)` to prevent animation jumps on lag spikes. All missions (tutorial, 2, 3, 4) must have this.
- **Use `map_data.clear_enabled_territories()` in `deactivate()`.** Campaign missions that enable a subset of territories must clear the filter on exit, or the next game starts with wrong territories.
- **Use try/finally when temporarily swapping `current_player`** for AI actions. If the AI code throws, the player index must be restored.
- **Graceful exit over `sys.exit()`.** Set `self._done = True` or `self.result = 'main_menu'` — never `pygame.quit(); sys.exit()` from inside a subsystem.

#### Network / Multiplayer
- **Always include `player_index`** in network messages — never hardcode `1 if local == 0 else 0` (breaks 3+ player games).
- **Implement all message handlers** — TODO stubs cause silent desyncs (e.g., `ORDER_REMOVE` was a no-op).
- **Atomic file writes** for settings/config: write to temp file, then `os.replace()`. Never truncate before writing.
- **Use locks around state writes in threaded network code.** Buffer overflow disconnection, state transitions — wrap with `with self._state_lock:`.

#### Army/Garrison System
- **Always use `get_territory_total_armies(territory)`** — never read `self.armies[territory]` directly. The legacy counter can be stale; the garrison system is authoritative.
- **Use `territory_garrisons[t] = {}` not `del territory_garrisons[t]`** to clear garrisons — matches the system's convention and avoids KeyError on subsequent access.

#### AI System
- **Route through `game_state.execute_*()` methods** — never duplicate game logic inline in AI code. The AI should call the same methods humans use.
- **Always exclude allies from enemy calculations.** Check `game_state.are_allies(player, other)` in: threat assessment, hero ability targeting, frontier detection, counterattack risk. Every "enemy" loop needs an ally guard.
- **Use actual data, not hardcoded assumptions.** Plot counts come from `map_data.get_plots(territory)`, not a hardcoded `3`. Building costs come from `BUILDING_TYPES`, not magic numbers. Castle upgrade costs are 150, not 100.

#### Multiplier/Stacking Logic
- **Use `*=` not `=` for stacking multipliers.** Multiple buildings with multiplier effects (e.g., two Squares) should compound: `multiplier *= value`, not `multiplier = value`.

#### Error Handling
- **Silent `try/except` hides bugs.** The under_construction ValueError was caught silently, making buildings invisible instead of crashing. When catching broad exceptions in rendering, log a warning so the root cause is discoverable.
- **Guard against `None` before comparisons.** `if winner < 0` crashes when `winner is None`. Always check `if x is None or x < 0`.
- **Bounds-check array indices from configurable values.** If `taxation_level` indexes into `tax_rates[5]`, clamp it: `max(0, min(level, len(rates) - 1))`. External/configurable inputs should never cause IndexError.
- **Identical if/else branches are a code smell.** If both branches do the same thing, collapse them — the condition is either wrong or unnecessary.

### Documentation Updates (CRITICAL - Must Do After Code Changes)

**After ANY substantial code update, you MUST update documentation:**

#### ✅ **When Adding New Features:**
1. **CODE_GUIDE.md** - Add "when to modify" guidance for new module/feature
2. **GAME_MECHANICS.md** - Document new game rules, mechanics, or balance changes
3. **QUICK_REFERENCE.md** - Add new constants, costs, or quick lookup values
4. **CLAUDE.md** - Update project structure if new files/modules added
5. **CHANGELOG.md** - Log the feature addition with date

**Example:** Adding a new unit type
- Update `CODE_GUIDE.md` with unit modification steps
- Update `GAME_MECHANICS.md` with unit stats and counter relationships
- Update `QUICK_REFERENCE.md` with unit cost table
- Update `CHANGELOG.md` with "Added X unit type"

#### ✅ **When Fixing Major Bugs:**
1. **CODE_GUIDE.md** - Update if bug revealed wrong guidance
2. **CHANGELOG.md** - Document the bug fix
3. Add code comments explaining the fix

**Example:** Fixing battle resolution bug
- Update `CODE_GUIDE.md` if combat mechanics section was misleading
- Add comment in `resolve_battle()` explaining the fix
- Log in `CHANGELOG.md`: "Fixed battle calculation error where..."

#### ✅ **When Changing Game Balance:**
1. **GAME_MECHANICS.md** - Update rule descriptions
2. **QUICK_REFERENCE.md** - Update stat tables with new values
3. **CODE_GUIDE.md** - Update balance change examples if needed
4. **CHANGELOG.md** - Log balance changes

**Example:** Changing unit costs
- Update `QUICK_REFERENCE.md` unit cost table
- Update `GAME_MECHANICS.md` if affects strategy significantly
- Log in `CHANGELOG.md`: "Rebalanced unit costs: Cavalry 40→35g"

#### ✅ **When Refactoring/Restructuring:**
1. **CLAUDE.md** - Update project structure section
2. **CODE_GUIDE.md** - Update file paths, line numbers, module guidance
3. **ARCHITECTURE.md** - Update if design patterns changed
4. **CHANGELOG.md** - Document refactoring phase

**Example:** Splitting a large module
- Update `CLAUDE.md` directory layout and file list
- Update `CODE_GUIDE.md` with new module locations
- Update `ARCHITECTURE.md` module dependency diagram

#### ❌ **What NOT to Update:**
- Don't update docs for tiny changes (typo fixes, minor tweaks)
- Don't update line numbers unless doing major refactoring
- Don't update if change is experimental/temporary

### Documentation Priority Order

**Always update in this order:**
1. **CODE_GUIDE.md** - Living knowledge base (most important)
2. **GAME_MECHANICS.md** or **QUICK_REFERENCE.md** - User-facing info
3. **CLAUDE.md** - Project structure (if files added/removed)
4. **CHANGELOG.md** - Historical record

### Quick Checklist

After making code changes, ask yourself:
- [ ] Did I add a new feature? → Update CODE_GUIDE.md + GAME_MECHANICS.md
- [ ] Did I change game balance? → Update QUICK_REFERENCE.md + GAME_MECHANICS.md
- [ ] Did I add/remove files? → Update CLAUDE.md structure section
- [ ] Did I refactor modules? → Update CODE_GUIDE.md file paths
- [ ] Is this a significant change? → Add entry to CHANGELOG.md
- [ ] Did I add code comments explaining why?

## Common Tasks

**For detailed module-specific guidance, see [docs/CODE_GUIDE.md](docs/CODE_GUIDE.md)**

### Quick Links (from CODE_GUIDE.md):
- Add new unit type → `game_state/__init__.py` UNIT_TYPES class attribute
- Add new building → `game_state/data_definitions.py` BUILDING_TYPES dict
- Change balance/costs → `game_state/economy.py` or `economic_data.json`
- Modify combat → `game_state/military.py` resolve_battle() method
- Modify battle bar volley animation → `ui/effects/battle_interface.py` (`BattleBarVolleyEffect`)
- Modify "Resolve Remaining Battles" button → `rendering/ui_renderer.py` `_draw_resolve_all_battles_button()`, `main.py` `_resolve_all_pending_battles()`
- Change AI behavior → `ai_strategy.py`, `ai_military.py`, or `ai_economy.py`
- Add UI element → `main.py` or `rendering/ui_renderer.py`
- Add visual effect → `ui/effects/` directory
- Change floating chat notifications → `ui/effects/chat_notification_effect.py`
- Modify camera/zoom → `input/camera_handler.py`
- Change edge scrolling / Map Edge start delay → `input/camera_handler.py` (`handle_edge_scrolling()`, `MAP_EDGE_SCROLL_DELAY`)
- Modify army/banner selection or hover → `main.py` `get_army_banner_rect()` / `get_army_at_pos()` / `handle_mouse_motion()` + `rendering/map_renderer.py` (all three must share the helpers)
- Modify unit right-click context menu (bottom UI army strip) → `main.py` `handle_unit_context_menu_right_click()` / `_get_unit_context_menu_rect()` / `draw_unit_context_menu()` / `handle_unit_context_menu_click()` + `input/mouse_handler.py` (Priority 0)
- Add territory → Use `Polygon_Tool.py`, `Economic_Tool.py`, `Plot_Tool.py` (use `--map <map_id>` for non-default maps)
- Add/modify map → `maps/manifest.json` (registry), `maps/<map_id>/` (data files), `map_data.py` (loader)
- Fortress territories → `maps/<map_id>/fortress_territories.json`, `map_data.is_fortress_territory()`, `game_state/military.py` (defense), `game_state/buildings.py` (Keep restriction)
- Change network → `network/protocol.py`
- Change multiplayer sync logging/desync diagnosis → `sync_logger.py`, `network_config.py` (message types), `main.py` (hooks)
- Change internet play / UPnP → `network/upnp.py` and `network_config.py`
- Modify simultaneous mode → `simultaneous/sim_state.py`, `sim_conflict_resolver.py`
- Modify victory/elimination → `game_state/victory.py` (check_victory, eliminate_player, eliminate_player_disconnect)
- Modify Battle Reports (capture) → `game_state/military.py` `_capture_battle_reports()` / `_capture_uncontested_report()` — hook lives in `resolve_battle()`, NOT `_update_battle_results()` (the tie path destroys buildings first and early-returns)
- Modify Battle Report popup visuals → `ui/battle_report_popup.py`
- Modify Battle Report show/hide rules → `main.py` `_viewer_in_planning()` (clearing) vs `_battle_reports_visible()` (drawing) — these are deliberately separate
- Modify "Close All Battle Reports" button → `rendering/ui_renderer.py` `_draw_close_all_battle_reports_button()` + `main.py` `close_all_battle_reports()`
- Modify Battle Report detail screen → `ui/effects/battle_interface.py` `report_snapshot` ctor path + `main.py` `open_battle_report_detail()`
- Modify disconnect elimination → `network/server.py` (_cleanup_expired_reconnects), `main.py` (DISCONNECT_ELIMINATION handler)
- Modify anti-win-farming XP → `player_level.py` (_is_disconnect_farming, DISCONNECT_FARMING_XP_THRESHOLD)
- Add new achievement → `achievement_manager.py` ACHIEVEMENTS list
- Add achievement reward icon → `achievement_manager.py` ALL_REWARD_ICON_PATHS
- Change achievement panel UI → `achievement_panel.py`
- Add campaign cutscene → Use `Cutscene_Tool.py`, data in `cutscene_data.json`
- Modify cutscene player → `cutscene_player.py`
- Export cutscene to MP4 → `cutscene_exporter.py` (called from `Cutscene_Tool.py`)
- Modify loading screen → `loading_screen.py`
- Change deferred sound loading → `global_sound.py` `get_game_sound_tasks()`
- Change sound playback → `sound_manager.py`
- Change background music → `music_manager.py`
- Change volume settings → `settings_manager.py` + `music_manager.py`
- Change volume slider UI → `rendering/ui_renderer.py` (in-game) + `main_menu.py` (main menu)
- Change VSync / FPS limit → `display_utils.py` (`set_display_mode`, `resolve_frame_cap`, `menu_frame_cap`) + `settings_manager.py` keys + both options menus
- Create/recreate the display window → **always** `display_utils.set_display_mode()`, never `pygame.display.set_mode()` directly (VSync needs `SCALED` + a fresh display, and is silently lost otherwise)
- Shared campaign utilities → `campaign_utils.py`
- Modify gold transfer feature → `game_state/economy.py` (`can_transfer_gold`, `get_transfer_cap`, `transfer_gold`) + `players_window.py` (UI) + `network/protocol.py` (`GOLD_TRANSFER` msg)
- Change gold transfer cap options → `integrated_setup.py` `gold_transfer_options` + `network/territory_selector.py` `gold_transfer_options`
- Modify Players window UI → `players_window.py`
- Change top-bar Players button → `rendering/ui_renderer.py` `draw_top_panel()` + `main.py` `handle_top_panel_click()`
- Change Steam achievement sync → `steam_integration.py`
- Change Steam friend invites → `steam_integration.py` (can_invite, get_online_friends, invite_friend)
- Change Steam invite UI → `network/territory_selector.py` (friend picker modal)
- Change Steam invite auto-connect → `main.py` (`steam_invite_join` action, `+connect` launch param)
- Change Steam player name behavior → `main_menu.py` `_open_profile()` + `_draw_profile_panel()`
- Multiplayer lobby → `network/lobby.py`
- Modify player level/XP → `player_level.py`
- Change level formula/XP amounts → `player_level.py` constants
- Player level profile UI → `main_menu.py` `_draw_profile_panel()`
- Player level recap screen → `recap_screen.py` XP bar methods
- Modify replay recording → `replay_recorder.py` `_serialize_state()`
- Modify replay viewer UI → `replay_viewer.py` - in-game HUD style (TopPanel/BottomBar/RightPanel + GMenuButton), **not** the campaign frames; keep the rect attribute names and hover-ID strings or input breaks silently. See "Replay Viewer HUD" in CODE_GUIDE.md
- Modify replay browser UI → `replay_browser.py` - **mirror any change into `save_browser.py`**; see "Browser Screens" in CODE_GUIDE.md
- Modify campaign save/load → `save_manager.py` (serialize/deserialize + file I/O)
- Modify save browser UI → `save_browser.py` - **mirror any change into `replay_browser.py`**; see "Browser Screens" in CODE_GUIDE.md
- Load/cache the ornate menu art (CampaignBG / OptionsMenuBG / CampaignBTN) → `utils/surface_utils.py` (`load_cached_image`, `get_campaign_button_image`, `crop_to_opaque`)
- Add save state to new mission → add `get_save_state()`/`restore_save_state()` + update `_SAVE_MISSION_REGISTRY` in main.py

## Notes
<!-- Any additional notes or context for Claude Code -->

### Workflow Preferences
- **Pause between phases**: When working through a multi-phase plan, always pause after completing each phase and wait for explicit user approval before starting the next one. Do NOT auto-continue.
- **Empty messages are NOT approval**: If the user sends an empty message or a message with only system reminders, do NOT treat it as a "go ahead". Wait for explicit instructions.

## Plan Mode
- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any. 