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
│   ├── manifest.json            # Map registry (id, display_name, has_background, draw_borders)
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
- [book_of_tales.py](book_of_tales.py) - Book of Tales scenario picker (opened from the Campaign screen's bottom-right icon; description markup; Launch runs the tale via `main.py` `_TALE_REGISTRY`)
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

**Game Setup Screens (shared by Custom Game + multiplayer lobby):**
- [ui/additional_options_overlay.py](ui/additional_options_overlay.py) - Additional Options modal (Neutral Armies, Randomize Bonuses, Gold Transfer, Starting Gold); read-only view for multiplayer clients
- [ui/setup_tooltip.py](ui/setup_tooltip.py) - (i) label marks + multi-line hover tooltips on the setup screens
- [config/setup_tooltips.py](config/setup_tooltips.py) - Setup tooltip wording, edited by the owner
- [ui/setup_frames.py](ui/setup_frames.py) - Wood-framed selector boxes (ResourceSlot) + bronze TableBorder frame for the lobby player rows

**Players Window (Gold Transfer UI):**
- [players_window.py](players_window.py) - Non-pausing modal listing all players (Name/Controller/Team/Color/Status columns) with ally gold-transfer input + Send button

**Player Level System:**
- [player_level.py](player_level.py) - Player level/XP logic, tiered progression formula, persistence, end-of-game calculation

**Steam (joining through Steam: CODE_GUIDE "Steam joining (SDR bridge)"):**
- [steam_integration.py](steam_integration.py) - `steam_manager`: achievements, invites, start-up `+connect`, join requests (callback 337), hosting rich presence + hosting friends, kill switches
- [steam_networking.py](steam_networking.py) - `steam_net`: ctypes binding to Steam's flat API (networking sockets / relay, rich presence, `GetLaunchCommandLine`, the join-request callback) - SteamworksPy has none of these
- [network/steam_bridge.py](network/steam_bridge.py) - `steam_bridge`: copies the game's TCP stream over Steam connections through 127.0.0.1 (server and client unchanged)
- [steam_sdr_test.py](steam_sdr_test.py) - `--sdr-test` diagnostics window (shipped as a support tool)
- [docs/steam/rich_presence.vdf](docs/steam/rich_presence.vdf) - Steam friends-list text ("Hosting a lobby"), uploaded in Steamworks (Community → Rich Presence)

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

**Book of Tales Scenarios:**
- [tale_lack_of_funds.py](tale_lack_of_funds.py) - Tale I: Lack of Funds (Azincournean Highlands, 4 factions, built-in AI restricted by mission hooks, Popularity/revolt mechanic, voiced intro/outro)
- [tale_final_breaths.py](tale_final_breaths.py) - Tale II: Final Breaths (Avareon + Campaign Mission 3 territories/map, 3 factions, hold Lunedale + Free Cities 15 turns, capped + forced Kerunian attacks, passive Nordian Rebels taking land by rebellion, 100% player-only taxation, no Heroes, voiced intro/rebellion/outro lines)

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
- [tests/test_sim_ai_budget.py](tests/test_sim_ai_budget.py) - Simultaneous AI keeps only the purchases it can pay for, in its priority order (the Hero it wanted is trained that round), a Hero and a Castle upgrade of one Keep kept apart, no gold held back for a Hero at a Keep a Hero lives in, the "Hero Training Cost" territory bonus lowers the Hero price
- [tests/test_ai_legal_plans.py](tests/test_ai_legal_plans.py) - The built-in AI plans only what the game accepts: Hero training at a free Keep (not one housing a Hero or upgrading), no Castle tech without a Castle, a target 2 steps away gets a staging move into the friendly territory between (accepted in both turn modes)
- [tests/test_team_battles.py](tests/test_team_battles.py) - Allies fighting together (both turn modes): a joint defence keeps the territory with its owner, each ally keeps their own survivors (defending allies fall first, attacking allies share by army size), defending losses never on the attackers, a team's full strength at a Keep, the owner's Battle Report, kill credit per ally, a losing ally's Scavenge the Fallen
- [tests/test_unit_ids.py](tests/test_unit_ids.py) - Every unit of a garrison has its own id: simultaneous arrivals and sequential ally reinforcement take the lowest free id (`next_free_unit_id`), the FFA game's Leimarch round 9 repro, whole army moves next round (every PC), the AI never names a unit twice
- [tests/test_ability_queued_units.py](tests/test_ability_queued_units.py) - Decisive Strike / Royal Charisma / Valorous Charge taking queued units (`_take_unit`): counters (the banner) follow the units, the units leave their planned moves (empty move or two-hop move without its Captain cancelled), the panel's selection list untouched, a struck client's surviving units still march (two PCs)
- [tests/test_move_fitting.py](tests/test_move_fitting.py) - The simultaneous host fits moves instead of refusing them: shortened to the units still there (Blue's round 35, single PC + two PCs), a unit named twice goes once, friendly destinations kept at the army cap (reinforcements stay home, latest first, chain), attacks untouched, an AI ability among the round's orders never makes units up, notices for shortened / refused moves
- [tests/test_round_end_client.py](tests/test_round_end_client.py) - A simultaneous client's round end: SIM_ROUND_COMPLETE waits for the client's own moves (Blue's round 10 race: the Battle Report for a territory lost undefended, no line about a cancelled Keep), the host's round-end Action Log lines reach the client (its own trained unit after the round marker, each line once), an older host changes nothing
- [tests/test_keep_battles.py](tests/test_keep_battles.py) - Several attackers at one Keep fight each other first (weaker attacker fights, winner takes the Keep, report names the assaulting attacker, XP / kill credit, seeded dice tie), team games (defending team's leader is not an attacker, allied attackers are one side)
- [tests/test_battle_report_popup.py](tests/test_battle_report_popup.py) - Popup text/geometry and the report-only battle interface
- [tests/test_battle_report_integration.py](tests/test_battle_report_integration.py) - Battle Report wiring against a real `Game`
- [tests/test_battle_report_network.py](tests/test_battle_report_network.py) - Battle Reports reaching a defending multiplayer client
- [tests/test_drawing_helpers.py](tests/test_drawing_helpers.py) - `draw_feedback_button()` fallback when its background image is missing
- [tests/test_tale_lack_of_funds.py](tests/test_tale_lack_of_funds.py) - Tale I: setup, AI rules/hooks, Popularity, widget click, transmissions, endgame + achievement, save/restore, Keep-only battle + Demolish Keep regressions
- [tests/test_tale_final_breaths.py](tests/test_tale_final_breaths.py) - Tale II: setup (plots, armies, techs, taxation), per-target attack cap (planner + move guard), forced attacks, Heroes ban incl. AI gate, rebellions + Rebels never eliminated, transmissions, endgame + achievement, widget, save/restore, Captain counter-composition regression
- [tests/test_map_borders.py](tests/test_map_borders.py) - Per-map territory borders flag (`draw_borders` in the manifest)
- [tests/test_action_feedback_bugfixes.py](tests/test_action_feedback_bugfixes.py) + `test_action_feedback_phase2.py`…`phase7.py` - Action error toasts: stale-code reset, re-order rollback, order cancel by identity, hidden territories, shared build/train path, tints, message table, army-order/hero-ability/other refusals
- [tests/test_hero_slain_notification.py](tests/test_hero_slain_notification.py) - "Our Hero, X, has been slain in Y!" toast (battle, Regicide, multiplayer defender via Battle Report)
- [tests/test_sidebar_collapse.py](tests/test_sidebar_collapse.py) - Collapsible right sidebar (layout math, hit-testing, round button / F2 / bookmarks, slide, tutorial lock, order badge), east map extension, bottom-strip hover/tooltip fix
- [tests/test_sidebar_widgets.py](tests/test_sidebar_widgets.py) - Sidebar widget kit: 9-slice, cards, label fitting, `content_geometry`, `ScrollState`, ribbon bookmarks
- [tests/test_sidebar_action_queue.py](tests/test_sidebar_action_queue.py) - Action Queue cards (order kind incl. allies, composition, scrolling, CANCEL ALL, Submitted), sidebar mouse wheel, route highlight, camera pan
- [tests/test_action_log_model.py](tests/test_action_log_model.py) - Action Log model (classification, grouping, turn bands, incremental), log/chat scrolling, per-player message privacy, ability victims / enemy-only abilities, filter chips, unread badges
- [tests/test_sidebar_heroes.py](tests/test_sidebar_heroes.py) - Heroes tab cards, shared ability status/cast with the bottom Hero UI, portrait pan
- [tests/test_sidebar_tech.py](tests/test_sidebar_tech.py) - Tech arrow states, grid fit at 720p/900p/1080p, centring
- [tests/test_sidebar_feedback.py](tests/test_sidebar_feedback.py) - Pixel audit: every sidebar control highlights on hover and flashes on click
- [tests/test_font_italic.py](tests/test_font_italic.py) - Italic only where intended: separate italic font objects, no shared font left italic after resolution changes
- [tests/test_bottom_panel.py](tests/test_bottom_panel.py) - Bottom panel overhaul at 720p/900p/1080p/1440p: kit geometry, End Turn section + state rules, Territory view (plots fill, Forces grid, Select Army, hero portrait, hover labels), empty plot buttons, Army view (T divider, 15-unit grid), Hero view (fixed portrait, Keep pan), building views (finished / under-construction plot incl. Confiscate label + XP bar, Barracks queue + hotkeys, Keep grid / hero card / castle states / training progress / Hero Limit), full-width button tooltips, orphaned tooltips dropped when the view switches
- [tests/test_cutscene_volume.py](tests/test_cutscene_volume.py) - Cutscene voice/music follow the master volume (muted game = silent cutscenes)
- [tests/test_setup_options.py](tests/test_setup_options.py) - Setup screens: Additional Options window (inside the frame at 720p-1440p, confirm/cancel/Escape, read-only client view, map hover blocked), Starting Gold (typing, clamp, Custom + lobby + network + `initialize_game`), label tooltips, wood/bronze frames and lobby row layout
- [tests/test_game_logger.py](tests/test_game_logger.py) - Per-game JSON log: round records list their battles / buildings, rounds numbered from 1 in both modes, the unfinished last round written, sequential rounds still counted once player 0 is out
- [tests/test_upnp.py](tests/test_upnp.py) - UPnP setup without a network (miniupnpc 2.3 raising "Success" = no router found), discovery retry, `is_complete()` only after the public-IP lookup, join-address order
- [tests/test_steam_invite.py](tests/test_steam_invite.py) - Lobby Steam invites: connect string carries LAN + public address, "Wait..." until UPnP is done, 30 s re-invite cooldown + countdown layout, "Join IP:" tooltip per UPnP result
- [tests/test_steam_networking.py](tests/test_steam_networking.py) - Steam flat-API binding against a fake DLL: struct layouts, init order + kill switches, message copy/release, status callback, the emulated join-request callback
- [tests/test_steam_bridge.py](tests/test_steam_bridge.py) - Steam bridge over a fake relay + real sockets / server / client: bytes both ways without loss, graceful closes (no resets), refusals reach the joiner, failure wording, rate limit, "not hosting" ends the attempt at once (no address attempts), Cancel
- [tests/test_steam_join.py](tests/test_steam_join.py) - Joining from Steam: launch `+connect` (Steam's command line first), join requests (dedupe, age, menus + Join Game screen take them, a second request for the joined host dropped), in-game toast, Connecting screen, every multiplayer screen pumps Steam
- [tests/test_steam_presence.py](tests/test_steam_presence.py) - Hosting presence (set while the lobby is open, cleared however it ends), hosting friends, the lobby's "or via Steam" note at 720p-1080p, Join Game "Steam Friends" / "Direct IP" tabs (join, scroll, empty state, layout, hover/flash), the uploaded rich presence token
- [tests/mp_harness.py](tests/mp_harness.py) - Multiplayer test harness: 2-4 real `Game`s in one process over the real server/client logic with in-memory sockets (`Session`, `make_session` fixture, input helpers). Fails a test when a received message raised (`Game.network_message_errors`, checked by `Peer.step()` and the fixture teardown). Every audit finding is fixed: no `xfail` markers are left in the `test_mp_*` files
- [tests/test_mp_transport.py](tests/test_mp_transport.py) - Sequence numbers (PONG/DISCONNECT exempt, per connection), disconnect notices (lobby + in game, send failures, once), refused rejoin, requeue order, real sockets (large frames to a slow reader, refusal reasons, `connect_any` skipping a dead address / stopping at a refusal), invite connect strings + "could not reach" reasons
- [tests/test_mp_lobby.py](tests/test_mp_lobby.py) - Lobby leave/join by server index, launch rules + tooltip, shared seed/map/config, loading screen (keeps messages, Escape, host skips leavers, lost host), real-socket connect -> lobby -> launch -> loading handshake, chosen colours + army flags in game, client slot updates (own colour/team only), territory claims (host's clock orders them, only map territories, broken timestamps, name not applied)
- [tests/test_mp_sequential.py](tests/test_mp_sequential.py) / [tests/test_mp_simultaneous.py](tests/test_mp_simultaneous.py) / [tests/test_mp_progression.py](tests/test_mp_progression.py) - Sequential / simultaneous sync and achievements/XP for the local player and for every member of a winning team (multiplayer audit findings); multiplayer wins need a human enemy
- [tests/test_mp_battles.py](tests/test_mp_battles.py) - Seeded battle replay on receivers (seed + full survivors, hero/Keep/report once, early result held, disagreeing replay corrected, seedless fallback with allies, FIGHT on a vanished battle, dice ties reproduce)
- [tests/test_mp_foundations.py](tests/test_mp_foundations.py) - State snapshot round trip / per-PC chat / AI flags / cleared work in progress / income, Decisive Strike + Valorous Charge picks, integer default unit ids
- [tests/test_mp_seq_flow.py](tests/test_mp_seq_flow.py) - Sequential multiplayer (the turn owner is the truth): a 3-player turn identical everywhere, a 4-player full round, only the owner sends TURN_END, receivers never advance on their own, TURN_END waits for the replay, messages wait for our turn-start effects, a stale clock never cuts a turn short, only the owner's timer ends the turn (C2), desync reported + corrected at EXECUTE_ORDERS, a 3-player battle, AFK (untouched battles, report left open, abandoned window), final state at game end
- [tests/test_mp_validation.py](tests/test_mp_validation.py) - Who may send what: relayed messages carry their sender, missing player fields filled in, host-only types and claims for other slots dropped (L5), sequential actions / TURN_END only from the turn owner, battle results only for a real battle and from its resolver, the simultaneous host keeps its own replay, alliance choices only from the chooser and for an ally, Hero abilities only with your own Hero, gold transfer rules (allies, once per turn, capped, only when on), a message that raises is skipped and the game goes on
- [tests/test_mp_seq_ai.py](tests/test_mp_seq_ai.py) - Sequential multiplayer computer players + takeover: only the host runs the AI (C1), the AI's moves / battles reach every PC (queued from its worker thread, kept in order), a player leaving while planning / after their moves / during their battles has the turn finished by the AI on the host, anti-farming with AI takeovers, snapshots summarised in logs, the disconnect chat notice comes from "System" (not the host)
- [tests/test_mp_sim_flow.py](tests/test_mp_sim_flow.py) - Simultaneous multiplayer: host state wins at execution start, 3- and 4-player rounds end identical (incl. per-PC current_player), round end clears leftovers, host-only AI battles / choices / round ends, SIM_READY_STATE waiting list, client timers ready only themselves, AFK (90 s own / 180 s host, report left open, host's own window), round end waits for the host's open battle report + keeps its alliance marker in its round, late alliance choice / stale popup never end the next round, AI takeover while planning / resolving, order validation (units used twice, count from unit list), alliance marker removal by territory, knocked-out players never hold up a round (after a battle or mid-round), clients record every round (game log + replay)

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
- [rendering/map_extension.py](rendering/map_extension.py) - Fills the strip past the map's east edge at low zoom (generated edge-stretch fading into fog, or a painted `<background>_east.png`)
- [rendering/sidebar_widgets.py](rendering/sidebar_widgets.py) - `SidebarWidgets` (`game.sidebar_widgets`): cached drawing kit for the right sidebar (capped text, 9-sliced wood/bronze frames, cards, buttons, chips, ribbons, tech arrows, scrollbars, clip helpers)
- [rendering/bottom_panel_kit.py](rendering/bottom_panel_kit.py) - `BottomPanelKit` (`game.bottom_panel_kit`): bottom panel sections (`section_rect`), centred headline + gold rule, CampaignBTN buttons with a tinted wooden window, BattleBar timer, T-divider rule, traced tutorial outline; fonts sized by panel height
- [rendering/action_log_model.py](rendering/action_log_model.py) - Pure Action Log model: message classification, grouping by turn, per-player visibility, filter chips (`FILTERS`), badge categories

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
- [network/steam_bridge.py](network/steam_bridge.py) - Joining through Steam's relay (no port forwarding): the loopback bridge between Steam connections and the unchanged TCP server / client
- [network/state_snapshot.py](network/state_snapshot.py) - Whole-game snapshots (`build_snapshot` / `apply_snapshot`) on top of the save serializer, for "this is the true state" messages
- [network/lobby.py](network/lobby.py) - Multiplayer lobby management
- [network/multiplayer_setup.py](network/multiplayer_setup.py) - Multiplayer configuration UI
- [network/territory_selector.py](network/territory_selector.py) - Multiplayer territory selection UI

**UI & Effects:**
- [ui/scaler.py](ui/scaler.py) - Dynamic UI scaling
- [ui/sidebar_layout.py](ui/sidebar_layout.py) - Right sidebar geometry + collapse slide (single source of truth for "is this point over the sidebar"), tab content area (`content_geometry`), pixel `ScrollState`
- [ui/effects/](ui/effects/) - 14 effect modules (battle, sparkles, turn announcements, hero ability burst/arc/polygon/silence wave, alliance markers, castle upgrade, production glow, chat notifications, etc.)

**Configuration:**
- [config/constants.py](config/constants.py) - All game constants (window, colors, timing, camera)
- [config/font_manager.py](config/font_manager.py) - Font loading and caching (one shared object per size/weight; italic via `get_italic_font()`, never `set_italic()` on a `get_font()` result)
- [config/action_error_messages.py](config/action_error_messages.py) - Every player-facing "action refused" toast text (+ `hero_slain`), edited by the owner — each entry commented with when it shows

### Data Files (JSON)

- `economic_data.json` - Territory economy definitions (root-level = Avareon, backward compat)
- `territory_polygons.json` (~1.6 MB) - Map geometry (root-level = Avareon, backward compat)
- `plots.json` - Building location coordinates (root-level = Avareon, backward compat)
- `territory_bonuses.json` - Territory bonus assignments (root-level = Avareon, backward compat)
- `maps/manifest.json` - Map registry (all available maps; `"draw_borders": true` outlines every territory, e.g. Azincournean Highlands)
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
- **A unit joining a garrison takes `next_free_unit_id(units)`** (lowest free id in that garrison) — never `len(units)` or 0..n-1 when appending to existing units. Duplicate ids made the host refuse every order naming the twins (FFA game 2026-10-14, see CODE_GUIDE "Common Mistakes").

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
- Modify combat → `game_state/military.py` resolve_battle() method — any randomness must use its `rng` parameter (multiplayer replays battles from the resolver's seed). Several attackers at one Keep → `_fight_for_the_keep()` (they fight each other first); the Keep's side is `battle.keep_bonus_player` (simultaneous battles are keyed by TEAM LEADER, not always the owner). See "Several attackers at one Keep" + "Team battles - sides and keys" in CODE_GUIDE.md. **A battle key is a TEAM (lowest player index), never assume one player** - use `_battle_sides()` / `_battle_side()`; survivors per player via `_side_survivors()`
- Resolve a battle from a new place → `main.py` `_resolve_battle_locally()` + `_battle_resolve_payload()` (never call `resolve_battle()` directly in multiplayer code); receiving side `_handle_remote_battle_resolve()`. See "Battle sync" in CODE_GUIDE.md
- A hero ability that picks units at random → ship the picks (`picked_units` / Royal Charisma `stolen_units`), receivers pass `pre_selected_units`
- A hero ability that takes units out of a garrison → `GarrisonMixin._take_unit(garrison, unit)` (counters right for queued units, the unit leaves its planned move)
- Whole-game "true state" message → `network/state_snapshot.py` (new GameState fields go into `save_manager.serialize/deserialize_game_state`)
- Modify battle bar volley animation → `ui/effects/battle_interface.py` (`BattleBarVolleyEffect`)
- Modify "Resolve Remaining Battles" button → `rendering/ui_renderer.py` `_draw_resolve_all_battles_button()`, `main.py` `_resolve_all_pending_battles()`
- Simultaneous-mode order checks at round start → `simultaneous/sim_phase_manager.py` `_validate_orders()` / `_claim_movement_units()` (shorten, refuse only when no unit can go) + `_finalize_movement_orders()` / `_fit_moves_to_room()` (after the round's other orders: units still there, friendly destinations at the cap); the player's notice → `main.py` `_report_shortened_moves()`. See "Orders" + "Fitting the moves" in CODE_GUIDE.md
- Simultaneous-mode AI spending → `simultaneous/sim_ai.py` `_fit_actions_to_gold()` / `_gold_cost()` (a new purchase type needs a cost there). Price of a Hero → always `gs.get_hero_cost(hero, player)`
- Change AI behavior → `ai_strategy.py`, `ai_military.py`, or `ai_economy.py` (AI code resolves battles with `game_state.resolve_battle_shared()`, never `resolve_battle()` - multiplayer replays them). **An AI pick must pass the same checks as the game method that executes it** (Hero Keep = `start_hero_training()` Keep rules, research = `start_research()` Castle rule, moves only to neighbours) - a refused plan wastes the turn and, in simultaneous mode, its reserved gold
- Notice an AI order the game refuses → the sim log (`Movement rejected - <reason>`, `SKIPPING ...`); sequential: `ai_player._execute_action_internal()` warnings
- Add UI element → `main.py` or `rendering/ui_renderer.py`
- Add visual effect → `ui/effects/` directory
- Change floating chat notifications → `ui/effects/chat_notification_effect.py`
- Modify camera/zoom → `input/camera_handler.py`
- Collapse/expand the right sidebar, its bookmarks, F2, or test whether a point is over it → `ui/sidebar_layout.py` + `main.py` `get_sidebar_layout()` / `is_point_over_sidebar()` / `toggle_sidebar()` / `draw_order_sidebar()`. **Never hardcode `WINDOW_WIDTH - 250`** — wrong while collapsed or sliding. See "Right sidebar" in CODE_GUIDE.md
- Change what fills the strip past the map's east edge → `rendering/map_extension.py` + `MAP_EAST_*` in `config/constants.py`, or paint `<map background>_east.png`. Anything that changes `map_image_original` (incl. drawing into it in place) must call `Game._invalidate_map_background_caches()`
- Change a sidebar tab's content / look → `rendering/ui_renderer.py` `_draw_<tab>_content()` using `rendering/sidebar_widgets.py`; layout via `ui/sidebar_layout.content_geometry()` (tapestry centre `panel_x + 135`), scrolling via `game.sidebar_scroll[tab]` (`ScrollState`). Every clickable control needs hover + click flash and a row in `tests/test_sidebar_feedback.py`. See "Right sidebar: tab content, widget kit and extras" in CODE_GUIDE.md
- Sidebar extras (route highlight, camera pan, log filter chips, unread badges) → `UIConstants.SIDEBAR_*` flags in `ui/scaler.py`; code in `main.py` (`start_sidebar_camera_pan`, `_sidebar_unread_totals`, `set_sidebar_log_filter`) + `map_renderer.draw_movement_arrows` (`COLOR_ARROW_HOVERED`)
- Change Action Log grouping / categories / colours → `rendering/action_log_model.py` (`_RULES`, `FILTERS`, `BADGE_CATEGORIES`) + `ui_renderer.LOG_CATEGORY_COLORS`
- **Log a message about one player's own action** → `gs.add_player_message(player, text)`, never a bare unnamed `add_message` (the Action Log shows unnamed lines to EVERY player). Ability hitting other players → name them (`gs.ability_victims_line`). "All enemies" abilities → `gs.ability_enemies(caster)`. See "Action Log privacy" in CODE_GUIDE.md
- Change edge scrolling / Map Edge start delay → `input/camera_handler.py` (`handle_edge_scrolling()`, `MAP_EDGE_SCROLL_DELAY`)
- Modify army/banner selection or hover → `main.py` `get_army_banner_rect()` / `get_army_at_pos()` / `handle_mouse_motion()` + `rendering/map_renderer.py` (all three must share the helpers)
- Modify unit right-click context menu (bottom UI army strip) → `main.py` `handle_unit_context_menu_right_click()` / `_get_unit_context_menu_rect()` / `draw_unit_context_menu()` / `handle_unit_context_menu_click()` + `input/mouse_handler.py` (Priority 0)
- Add territory → Use `Polygon_Tool.py`, `Economic_Tool.py`, `Plot_Tool.py` (use `--map <map_id>` for non-default maps)
- Add/modify map → `maps/manifest.json` (registry), `maps/<map_id>/` (data files), `map_data.py` (loader)
- Fortress territories → `maps/<map_id>/fortress_territories.json`, `map_data.is_fortress_territory()`, `game_state/military.py` (defense), `game_state/buildings.py` (Keep restriction)
- Change network → `network/protocol.py`
- Add a message clients send / decide who may send it → `network/server.py` `_CLIENT_MESSAGE_TYPES` (else dropped from clients) + `_SENDER_FIELDS` (acting-player field, must be the sender); receivers: `main.py` `_message_sender()` (stamp; None = host, trusted) / `_refusal_for()` (`_TURN_OWNER_MESSAGES`) + checks in the handler. See "Who may send what" in CODE_GUIDE.md
- Change multiplayer sync logging/desync diagnosis → `sync_logger.py`, `main.py` `_report_snapshot_divergence()` (receiver diffs its state against the owner's snapshot) + the turn-snapshot hooks
- Change internet play / UPnP → `network/upnp.py` and `network_config.py`
- Change what a Steam invite carries / how the invited PC connects → `server.get_join_addresses()` + `territory_selector._invite_connect_string()` (`+connect steam-<id>,ip1:port,ip2:port` - the Steam target first), `network/client.py` `parse_connect_targets()` / `connect_any()` / `connect_steam()` / `unreachable_reason()`; re-invite wait `INVITE_COOLDOWN_SECONDS`
- Change joining through Steam (relay bridge, failure wording, closing) → `network/steam_bridge.py` (`describe_end()` for the wording) + `steam_networking.py`. **Every screen of the multiplayer flow must call `steam_manager.run_callbacks()` each frame** (a friend's Steam join reaches the host only through it - add the screen to `TestEveryScreenPumpsSteam`), and never close a socket with unread data (Windows resets it). See "Steam joining (SDR bridge)" in CODE_GUIDE.md
- Change what friends see while you host (rich presence) → `steam_integration.set_hosting_presence()` / `clear_hosting_presence()` + `territory_selector._update_hosting_presence()`; the friends-list text is `docs/steam/rich_presence.vdf` (upload it again in Steamworks after a change)
- Change the Join Game screen's Steam Friends list → `network/multiplayer_setup.py` (`HostingFriendsList`, `_get_host_ip()`, `_draw_friend_rows()`, `_join_screen_layout()`); the friends come from `steam_manager.get_hosting_friends()`
- Steam join requests (invite accepted / "Join Game" while the game runs) → `steam_manager.take_join_request()`, taken by the main menu, the multiplayer menu and the Join Game screen; in a game a toast (`main.py` `_notify_steam_join_request()`); after a join `drop_join_requests_for()`
- Multiplayer stats / Conquest achievements → count only with a human enemy (`player_level.has_human_opponent()`)
- Modify simultaneous mode → `simultaneous/sim_state.py`, `sim_conflict_resolver.py`
- Simultaneous multiplayer flow → host: `main.py` `_sim_start_execution_phase()` (validate + apply non-movement + `SIM_ALL_READY{snapshot, movement_orders}`) / `_sim_broadcast_round_complete()` (snapshot); client: `_sim_apply_all_ready()` / `_sim_apply_round_complete()` (restore `current_player` = local after a snapshot; SIM_ROUND_COMPLETE is held until the client's own moves played out; the host's round-end Action Log lines `round_end_messages` / `round_start_messages` replace the client's copy). Per-frame work: `_update_simultaneous()` (timers, `SIM_READY_STATE`, host-only AI resolvers / choosers, `_sim_afk_watchdog()`, new-round AI). **Any new "end the round now?" check must use `Game._sim_round_may_end()`** (it waits for an open battle report of ours). See "Multiplayer model (the host is the truth)" in CODE_GUIDE.md
- Sequential multiplayer flow → owner (`Game._is_turn_owner_of()`: the human's PC, the HOST for computer players): `main.py` `_end_local_turn()` (End Turn + timer), GameState hooks `on_orders_executing` → `_on_orders_executing()` (`EXECUTE_ORDERS{snapshot}`), `shared_battle_resolver` → `_resolve_and_share_battle()` (the AI's battles), `on_turn_advanced` → `_on_turn_advanced()` (`TURN_END{snapshot}`); sends from the AI's worker thread are queued for the main loop (`_send_action_to_remote()` / `_flush_thread_messages()`); receivers: `_handle_remote_execute_orders()` / `_handle_remote_turn_end()` (+ `GameState._after_turn_advance()`). Per-frame: `_update_sequential_turn()` (`_update_ai_turn_start()` - host-only AI, owner-only timer, `_seq_afk_watchdog()`, final state). **Only the turn owner's PC may advance a turn** (`GameState.may_advance_turn()` / `Game._owns_current_turn()`). See "Sequential multiplayer: the turn owner is the truth" in CODE_GUIDE.md
- AI takeover of a disconnected player → `main.py` `_take_over_disconnected_player()` + `SimultaneousAI.ensure_player()` (simultaneous) / `_continue_turn_as_ai()` + `handle_ai_turn()` (sequential: finishes their current turn on the host)
- Knocked-out players in simultaneous mode → `sim_state.eliminated_players` follows `game_state.eliminated_players` (`start_planning_phase()` adopts it, `sim_state.sync_eliminations()` after battles + per frame on the host). Round records (game log / sync log / replay) → `sim_state.record_round_boundary()` (host: end of `complete_round()`; clients: after SIM_ROUND_COMPLETE)
- Simultaneous AFK timings → `Game.SIM_AFK_RESOLVE_SECONDS` / `SIM_HOST_FALLBACK_SECONDS` / `SIM_AI_ACTION_DELAY` in `main.py`
- Sequential AFK timings → `Game.SEQ_AFK_RESOLVE_SECONDS` / `SEQ_BATTLE_FALLBACK_SECONDS` in `main.py` (`_seq_afk_watchdog()`)
- Modify victory/elimination → `game_state/victory.py` (check_victory, eliminate_player, eliminate_player_disconnect)
- Modify Battle Reports (capture) → `game_state/military.py` `_capture_battle_reports()` / `_capture_uncontested_report()` — hook lives in `resolve_battle()`, NOT `_update_battle_results()` (the tie path destroys buildings first and early-returns)
- Modify Battle Report popup visuals → `ui/battle_report_popup.py`
- Modify Battle Report show/hide rules → `main.py` `_viewer_in_planning()` (clearing) vs `_battle_reports_visible()` (drawing) — these are deliberately separate
- Modify "Close All Battle Reports" button → `rendering/ui_renderer.py` `_draw_close_all_battle_reports_button()` + `main.py` `close_all_battle_reports()`
- Modify Battle Report detail screen → `ui/effects/battle_interface.py` `report_snapshot` ctor path + `main.py` `open_battle_report_detail()`
- Modify disconnect elimination → `network/server.py` (_cleanup_expired_reconnects), `main.py` (DISCONNECT_ELIMINATION handler) — inactive while `RECONNECT_ENABLED` is False (`network_config.py`)
- Change how clients drop / get refused → `network/server.py` `_disconnect_client()` (every removal; LOBBY_LEAVE vs PLAYER_DISCONNECT to host + clients) / `_reject_connection()` + `network/client.py` `_connection_failed()` (first reason wins). See "Connection lifecycle" in CODE_GUIDE.md
- Change how a multiplayer game starts (Host / Join / Steam invite) → `network/multiplayer_setup.py` `build_multiplayer_config()` / `run_client_lobby()` + `main.py` `_play_multiplayer_game()` — one path for all three, never a per-path copy
- Change lobby launch rules → `network/lobby.py` `launch_blocker()` + `config/setup_tooltips.py` `launch_<reason>`
- Write a multiplayer sync test → `tests/mp_harness.py` (`Session`, `click_end_turn`, `fight`, ...)
- Add a network message handler in `main.py` → `_apply_network_message()` (called through the `_handle_network_message()` guard, which logs + skips a message that raises)
- Chat line written by the game (not a player) → `gs.add_system_chat_message(text)`; show a chat sender via `gs.chat_sender_name()` / `chat_sender_color()` (never `add_chat_message(0, ...)` - it reads as the host)
- Who won, for one player (achievements, XP, victory screen) → `gs.is_winner(player)` (the winner or a teammate), never `gs.winner == player`; this PC's player → `player_level.local_human_index(game)`
- Modify anti-win-farming XP → `player_level.py` (_is_disconnect_farming, DISCONNECT_FARMING_XP_THRESHOLD; AI takeovers count via `gs.ai_takeover_xp`)
- Add new achievement → `achievement_manager.py` ACHIEVEMENTS list
- Add achievement reward icon → `achievement_manager.py` ALL_REWARD_ICON_PATHS
- Change achievement panel UI → `achievement_panel.py`
- Add campaign cutscene → Use `Cutscene_Tool.py`, data in `cutscene_data.json`
- Modify cutscene player → `cutscene_player.py` (volume = slide volume × `master_volume`, passed by every in-game `CutscenePlayer(...)` call)
- Change a bottom panel view (End Turn, Territory, empty plot, finished / under-construction plot, Barracks, Keep, Army, Hero) → `main.py` view method using `rendering/bottom_panel_kit.py`; section geometry via `_section_layout()` / `_*_view_layout()`, **never fixed x offsets**; text sized by `kit.font(role)` (panel height, not `ui_scale`). New buttons: `kit.ornate_button()` + rect reset in `draw_bottom_ui()` + `handle_bottom_ui_click()` + a hover/flash test in `tests/test_bottom_panel.py`. See "Bottom panel: sections, kit and views" in CODE_GUIDE.md
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
- Add / change an Additional Options setting → `ui/additional_options_overlay.py` `ROWS` + `config/setup_tooltips.py` + both screens' open/Confirm handlers (+ `network/lobby.py` settings for multiplayer). **Never** edit one screen's copy — there is one shared window. See "Game Setup Screens" in CODE_GUIDE.md
- Change Starting Gold limits → `STARTING_GOLD_DEFAULT/MIN/MAX` in `config/constants.py`; clamp with `clamp_starting_gold()`. Lobby → game goes through `lobby_state.starting_gold`, not the selector's result tuple
- Reword a setup-screen tooltip (Turn Mode, Taxation, Victory, Additional Options rows) → `config/setup_tooltips.py`
- Change the setup screens' framed selectors / lobby player frame → `ui/setup_frames.py` (`WOOD_TINT` darkens the beams); lobby row positions are derived in `territory_selector._calculate_ui_layout()`
- Modify Players window UI → `players_window.py`
- Change top-bar Players button → `rendering/ui_renderer.py` `draw_top_panel()` + `main.py` `handle_top_panel_click()`
- Change Steam achievement sync → `steam_integration.py`
- Change Steam friend invites → `steam_integration.py` (can_invite, get_online_friends, invite_friend)
- Change Steam invite UI → `network/territory_selector.py` (friend picker modal)
- Change Steam invite auto-connect → `main.py` (`steam_invite_join` action, `+connect` launch param - read by `steam_manager.launch_connect_target()`, Steam's launch command line first, argv as fallback)
- Change Steam player name behavior → `main_menu.py` `_open_profile()` + `_draw_profile_panel()`
- Multiplayer lobby → `network/lobby.py`; lobby UI / slot seating / launch → `network/territory_selector.py` (slot = the server's player index, never look players up by name; a client's slot update changes only its own colour / team)
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
- Add/edit Book of Tales scenarios → `book_of_tales.py` `SCENARIOS` + `main.py` `_TALE_REGISTRY` (launched via `_run_registered_mission()`) + a mission module. See "Book of Tales Screen" in CODE_GUIDE.md
- Tune Tale I (Popularity, revolts, AI rules, transmissions) → constants at the top of `tale_lack_of_funds.py`. See "Tale I: Lack of Funds" in CODE_GUIDE.md
- Tune Tale II (attack cap, forced attacks, rebellions, taxation) → constants at the top of `tale_final_breaths.py`. See "Tale II: Final Breaths" in CODE_GUIDE.md
- Restrict / speed up the built-in AI from a mission → mission `is_ai_target_allowed()` (read by `ai_military.mission_allows_ai_target()`), `get_ai_attack_cap()` (per-target unit cap, read by `ai_military.mission_ai_attack_cap()`), `is_action_allowed('train' | 'train_hero')` (AI asks `ai_military.mission_allows_ai_action()` for heroes), `ai_delay_scale` (read by `ai_player._pace()`)
- Tax one player differently from a mission → `gs.player_taxation_override[player] = level` (read by `gs.get_taxation_level()`)
- Start a player with researched techs → `gs.apply_tech_effect(player, tech, announce=False)` (shared with `finish_research()`); never set tech attributes by hand
- Clickable mission overlay → mission `handle_click(pos)` (`input/mouse_handler.py` Priority 4.5) + draw in `render()`
- Territory border outlines → `maps/manifest.json` `draw_borders` + `rendering/map_renderer.py` `draw_territories()` / `TERRITORY_BORDER_*`
- Change Campaign screen corner icon buttons (Saved Games / Book of Tales) → `campaign_screen.py` `_draw_icon_button()`
- Add save state to new mission → add `get_save_state()`/`restore_save_state()` + update `_SAVE_MISSION_REGISTRY` in main.py
- Add / reword an action error toast → `config/action_error_messages.py` (text) + set `last_action_error` in the game-state method + `_show_action_failure_feedback()` at the call site. Red/grey/hidden controls need no toast (fix the tint instead). See "Action Failure Feedback Pattern" in CODE_GUIDE.md
- Build/train from any input (map icon, bottom panel, keyboard) → `main.py` `_try_start_construction()` / `_try_start_training()` — never a separate copy
- Add a button tooltip / hover system → call `update_button_hover(current, type)` **every frame** while its buttons are drawn (`None` when nothing is hovered); `update_frame_tooltips()` drops a hover whose system didn't run that frame (`_release_orphaned_button_hover()`). See "Orphaned tooltips" in CODE_GUIDE.md
- Hero death toast → `HeroMixin._record_hero_death()` + `main.py` `_show_hero_death_notifications()` (+ Battle Report `heroes_slain` for multiplayer defenders)

## Notes
<!-- Any additional notes or context for Claude Code -->

### Workflow Preferences
- **Pause between phases**: When working through a multi-phase plan, always pause after completing each phase and wait for explicit user approval before starting the next one. Do NOT auto-continue.
- **Empty messages are NOT approval**: If the user sends an empty message or a message with only system reminders, do NOT treat it as a "go ahead". Wait for explicit instructions.

## Plan Mode
- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any. 