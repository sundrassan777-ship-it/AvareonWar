# Changelog

All notable changes to the AvareonWar project.

## 2026-09-22 - Battle Report anchoring, a multi-garrison crash, and two UI labels

- **Battle Report popups are now anchored to the map, not the view.** They were clamped
  into the map band, so panning away parked one against the screen edge — it read as a
  floating HUD element and misreported where the battle happened. Placement now derives
  only from the territory centre, **centred on it in both axes** so the report is visible
  whenever its territory is; `draw()` culls popups that scroll out of the band and clips
  the pass to it so nothing paints over the UI panels. Hit rects are clipped to the
  visible part too, so a button half hidden under a panel does not take clicks there.
  - Residual trade-off: the buttons sit at the bottom of the board, so a territory centred
    within half a popup of a band edge can have them clipped away — the report stays
    readable, and "Close All Battle Reports" still clears it.

- **Fixed `IndexError: list index out of range` in `draw_territories()`** (unrelated to
  Battle Reports; found during playtesting). `assign_garrison_position()` keeps each
  garrison's ring index stable across frames and deletes entries for garrisons that leave,
  but never renumbered the survivors. Three garrisons at 0/1/2 where #0 departs left #2
  pointing at index 2 of a ring that is now only two points long, and the next frame
  raised. Out-of-range entries are compacted into free slots (everyone else keeps their
  position), the fallback path is clamped, and the draw site bounds-checks and logs
  instead of raising — matching the guard the selected-garrison path above it already had.

- **Cancel construction button now reads just "Cancel"** instead of
  `Cancel {building_type} (100%)`, which overflowed the button for longer building names.
  The plot panel directly above it already names the building.

- **Hero training countdown now reads "3 turns remaining"** instead of
  `Training: 3 turns remaining`, which overran its column in the Heroes tab. Also fixed
  the singular case, which previously read "1 turns remaining".

## 2026-09-21 - Battle Reports: defenders finally see what happened to them

- **Why:** When an enemy attacked you, the only feedback was the map changing colour.
  With 10+ territories it was impossible to tell whether a border province had held, what
  it cost, or what was lost. The attacker got a full battle result screen; the defender
  got nothing.
- **What:** On the turn after you are attacked, a small `TransmissionBG` panel appears over
  each attacked territory showing **DEFENDED** (dark green) or **LOST** (dark red),
  underlined, with left-aligned counts beneath - units lost/remaining and structures
  destroyed/remaining. **Detail** opens the full battle result screen from *your* side (the
  attacker saw a victory; you see the same fight as a defeat), **Close** dismisses one, and
  **Close All Battle Reports** appears in the top-bar slot the "Resolve Remaining Battles"
  button uses. Everything disappears when your planning phase ends.
- Reports are defender-only, transient (not saved, not in replays) and are **excluded from
  the state checksum and full-state sync** - per-viewer UI state legitimately differs
  between host and client, and including it would have produced false desyncs.

### Capture (`game_state/military.py`)

- `resolve_battle()` discarded every per-type casualty figure it computed, so there was no
  data to report. It now snapshots the building layout up front and calls
  `_capture_battle_reports()` once at the end, after `_enforce_army_limits()`.
- **The hook cannot live in `_update_battle_results()`.** On the perfect-dice-tie path,
  `destroy_buildings()` runs inside `_handle_battle_tie_with_dice()` *before*
  `_update_battle_results()` is reached, and that method early-returns for a tie - a hook
  there missed ties entirely and reported zero structures destroyed.
- Unit counts are **exact**, read from the post-battle garrison, not the proportional
  estimate `battle_interface.set_actual_battle_result()` has to use.
- **Uncontested captures also report.** Walking into an undefended territory creates no
  `Battle`, so it is captured separately in `_process_arrivals()`. It was previously the
  easiest loss of all to miss. **Simultaneous mode has its own copy of that path** in
  `sim_phase_manager.py` and needs the same hook — without it, losing an undefended
  territory in a simultaneous game stayed completely silent.
- **A Keep or Fortress defending alone** still creates a battle: the owner is put into
  `player_armies` with a count equal to the Keep bonus even with an empty garrison, and
  `resolve_battle()` then substitutes a phantom `{'Swordsman': keep_bonus}` composition.
  The report reads `battle.army_compositions`, which is only ever populated from a real
  garrison, so a Keep-only defence no longer claims units the defender never had.
- **Champion of the People** (Seledra) preserves Farms/Mines *for the conqueror*: those
  plots survive and change owner. Counting them as destroyed would be wrong, ignoring them
  would under-report the loss, so building losses are split into
  `structures_destroyed` and `structures_captured`, and the popup grows a third line
  (" - 2 Structures Captured") only when that ability fired.
- **Aggressive Diplomacy (Halon Nextroy) deliberately produces no report** - it resolves in
  real time. It is isolated from both hooks today only by accident of structure, so
  `tests/test_battle_reports.py` pins that with an explicit guard test.
- Eligibility is judged on **pre-battle** state: `check_victory()` runs inside the battle
  and can eliminate a defender who just lost their last territory, which would otherwise
  let a battle retroactively suppress its own report.

### UI (`ui/battle_report_popup.py`, `main.py`, `rendering/ui_renderer.py`)

- Popups anchor to `scaled_centers` through `world_to_screen()`, so they track the camera,
  but their **size uses the resolution scale, not the zoom-driven one** - they stay
  readable at every zoom instead of ballooning. Rects are clamped to the map band.
- The board art is scaled uniformly from its measured proportions (solid area: 7.0% inset
  left, 6.9% right, 20.1% top, **20.5% bottom** - `campaign_utils.py` never documented that
  last one) rather than stretched, so the wood grain is never squashed.
- **Readability:** the board is darkened on blit and the text is light, rather than dark
  text on bare wood, which measured only 2.58:1 contrast at 12px. Now 12.4:1 for the body
  lines, 9.4:1 for DEFENDED (light green) and 5.6:1 for LOST (light red).
- The title underline is drawn with `pygame.draw.line`, **not** `font.set_underline()`:
  `FontManager` hands out one shared font object per (size, weight) and `_get_cached_text()`
  does not key on underline state, so setting it would have leaked into unrelated UI - the
  same bug `small_font_italic` already has.
- **Clearing is keyed on the transition OUT of a planning phase**, never on "not currently
  in one". Two separate bugs came from getting this wrong: reports are queued *before* the
  turn announcement that opens the turn they belong to, and - in **simultaneous mode** -
  battles resolve during the `'resolving'` phase, when nobody is planning and the viewer
  *is* the defender, so the report was wiped on the very frame it was captured and nothing
  ever appeared. Sequential mode hid that second one, because there battles resolve during
  the *attacker's* turn.
- `_get_report_viewer()` returns the local human in simultaneous mode rather than
  `current_player`: everyone plans at once, and sim code temporarily swaps
  `current_player` while running each player's orders.
- Reports take **Priority 0** in the click chain but are **not modal**: a click that misses
  every popup falls through to the map, and the handler stands down while a higher modal is
  open so it cannot steal clicks from the game/options menu at Priority 3/4.
- The Detail screen gets **its own close path** rather than reusing
  `_finalize_enhanced_battle()`, which would re-broadcast a `BATTLE_RESOLVE` message and
  re-create alliance markers for a battle finalised long ago.
- `EnhancedBattleInterface` gained an optional `report_snapshot` argument that opens it
  directly in the REPORT state without touching `pending_battles` - the `Battle` object is
  popped the instant it resolves, so for a report there is nothing left to read.

### Multiplayer (`main.py`)

- **A client never runs `resolve_battle()`** - the `BATTLE_RESOLVE` handler applies the
  result directly - so the capture hook never fires for a defending client, the one player
  who needs the report. Reports now ride along on that message.
- Added as a key on the **existing** payload, not a new message type:
  `validate_message_data()` has no `BATTLE_RESOLVE` branch, the server relays the original
  bytes, and the receiver reads via `.get()`, so older builds ignore it harmlessly.
  `NETWORK_VERSION` is deliberately **not** bumped - the server compares versions by exact
  string, so a bump would lock out every peer for a purely additive key.
- `_finalize_enhanced_battle()` broadcasts on the CLOSE click, arbitrary frames after
  `resolve_battle()` ran on the FIGHT click, so its reports are stashed in
  `_resolved_battle_info` instead of read live from `last_battle_reports`, which another
  battle could have overwritten by then.

### Also fixed

- **`draw_feedback_button()` crashed on a missing background image.** Every image-backed
  button (Menu, Players, Resolve Remaining Battles) passes `base_color=None` and relies on
  `bg_image`; a failed `pygame.image.load()` is caught at startup and leaves that image
  `None`, so the solid-colour fallback was handed `None` for both and raised
  "invalid color argument". A missing PNG now degrades to a plain button.

### Tests

- **Added** `tests/test_battle_reports.py` - capture rules, the tie path, Keep-only
  defences, Champion of the People, the Aggressive Diplomacy guard, JSON round-tripping.
- **Added** `tests/test_battle_report_popup.py` - line text, geometry, and the report-only
  battle interface.
- **Added** `tests/test_battle_report_integration.py` - promote/clear cycle, click routing
  and the top-bar button against a real `Game`.
- **Added** `tests/test_battle_report_network.py` - the defending-client path and wire safety.
- **Added** `tests/test_drawing_helpers.py` - the missing-image button fallback.

## 2026-09-21 - Map Edge scrolling now waits 200ms before panning

- **Why:** Map Edge mode puts its 20px trigger band *inside* the map viewport, directly
  above the bottom UI panel and below the top panel. Moving the cursor down to a bottom-UI
  button crossed that band and dragged the camera along - the player wanted a button, not
  a pan.
- **Fix:** `handle_edge_scrolling()` now requires the cursor to dwell inside a band for
  `MAP_EDGE_SCROLL_DELAY` (0.2s) before scrolling starts. A quick transit accumulates too
  little time to fire; holding at the edge still pans, with the same proximity ramp as
  before. The accumulator resets whenever the cursor leaves every band, including via the
  early return that fires when it reaches the UI panels.
- Applies to all four bands, for a consistent feel. One shared accumulator, so sliding
  from one band into an adjacent corner does not re-trigger the wait.
- **Window Edge mode is unchanged** - its band is the physical window border, so entering
  it is always intentional.
- `delta_time` is now threaded from the main loop into `handle_edge_scrolling()`. It
  drives *only* the dwell timer; the pan movement remains per-frame as before.
- **Also fixed:** `edge_scrolling_mode` defaulted to the stale value `'push'`, which
  matched neither `"map_edge"` nor `"window_edge"`. It fell through to the map-edge
  geometry but skipped the map-area guard, so fresh installs got a hybrid mode that
  scrolled over the UI panels while the options menu labelled it "Window Edge". The
  default is now `window_edge`, and `SettingsManager._validate_and_clean_settings()`
  coerces any legacy or unrecognised value to it.
- **Added** `tests/test_edge_scroll_delay.py` - covers the transit case, the dwell case,
  both reset paths, all four bands, Window Edge being untouched, and the legacy mode
  coercion.

## 2026-09-21 - Fixed: outro cutscene played after campaign defeat

- **Bug:** the post-mission cinematic, meant as a reward for winning, also played after a
  **defeat** in campaign missions 2-7 (reported on mission 3).
- **Root cause:** victory and defeat were indistinguishable at the mission -> game boundary.
  Every mission's `update()` returned the same `'exit_campaign'` sentinel from both its
  victory branch and its defeat branch, so `Game.run()` returned `'campaign'` either way and
  both outro call sites in `main.py` fired. Their `# only after victory` comments were wrong.
- **Fix:** defeat now returns a distinct `'exit_campaign_defeat'`, which `Game.run()` maps to
  `'campaign_defeat'`. The existing `game_result == 'campaign'` gates are therefore correct
  for the first time. Chosen over sniffing `game_state.winner == 0` at the call site, because
  `winner` is also written by the generic `check_victory()` path.
- **Defeat flow is now:** defeat screen -> recap (stats, XP, achievements) -> campaign menu,
  with no cinematic. Victory is unchanged.
- Covers both call sites: a freshly launched mission and a loaded campaign save
  (`_launch_saved_game`).
- `tutorial_mission.py` (mission 1) was never affected - it has no defeat path.
- **Added** `tests/test_campaign_outro_cutscene.py` - AST-level regression tests pinning the
  sentinel contract across all seven mission files plus both `main.py` gates. The bug lived in
  six near-duplicate files, exactly the shape that regresses silently.

## 2026-09-21 - Battle bar volley animation (BFME2 auto-resolve style)

- **Why:** the battle bars drained in a single continuous eased slide while ~600 circle
  particles streamed steadily between them. It read as "a bar sliding", not as a fight.
  Reference: BFME2, War of the Ring, auto-resolve.
- **Reworked** `BattleBarParticleEffect` into **`BattleBarVolleyEffect`**
  (`ui/effects/battle_interface.py`):
  - **Stepwise depletion.** Each volley fires one blast per side; on impact the chunk it
    destroyed flashes white-hot in place, then burns away and the fill steps down. Chunk
    sizes are jittered but normalised to sum exactly to the damage, so the bars land
    precisely on their final fill.
  - **Volley count scales with army size** (log curve, clamped 3-14). The animation
    duration now falls out of the schedule instead of being drawn up front, clamped to
    2.0-6.0s (was a flat random 3.0-5.0s).
  - **Mirrored bars.** The defender bar is anchored at its right edge, so both bars erode
    inward toward the centre "VS". Its `BattleBar.png` frame is flipped to match.
  - **One travelling blast per shot** instead of a continuous particle stream - a tapered,
    motion-blurred lance in the shooter's colour, with a white-hot tip.
  - **Impact burst** of a white-hot core, radiating spikes and a coloured glow, plus a
    flare that lights up the bar's ornate frame artwork.
  - Shots interleave between the two sides, so the hits trade rather than land together.
- **Bars now animate to the real battle result.** `set_actual_battle_result()` calls
  `retarget()`, which rebuilds the chunk split from a freshly seeded RNG so the volley
  rhythm is unchanged. Fixes the strength-tie case, where the pre-calculated estimate
  drained both bars to empty and the report then named a winner anyway.
- **Fixed survivor → bar fill conversion.** It used a raw `survivors / count`, which made a
  weaker side that won end with a *longer* bar than it started with. Now scaled by the
  side's initial fill.
- **Added a skip:** clicking anywhere during the animation, or pressing Space/ESC, jumps
  straight to the final bar state and the splash. There was previously no way to shorten a
  single battle animation.
- **Performance:**
  - Dropped the full-screen SRCALPHA surface that was allocated, cleared and blitted every
    frame. Nothing is allocated per frame now - fills and burn chunks draw straight to the
    screen, everything else is a pre-rendered sprite. Render+update measures 0.89 ms/frame
    against 1.16 ms/frame for the old particle surface *alone*.
  - Fixed the pulsing battle icon being `smoothscale`d uncached every frame in both the
    SETUP and ANIMATING states (flagged in `docs/PERFORMANCE_ROADMAP.md`). The pulse scale
    is quantised to 1/64 and cached, and both states now share one helper.
  - The frame flare is a single sprite faded with `set_alpha`; pre-rendering a sprite per
    fade step cost ~21 ms up front, a visible hitch on the Resolve click. Construction is
    5.4 ms, down from 24.3 ms.
- **Battle logic untouched** - `resolve_battle()`, casualties and the tie dice are unchanged,
  including the existing global `random.seed()` in `_pre_calculate_battle_result()`. The
  effect draws only from its own `random.Random(seed)`, so multiplayer clients stay in sync.
- Tests:
  - `tests/test_battle_bar_volley.py` (51 tests - chunk split, volley scaling, determinism,
    playback, skip, retarget, mirrored geometry, sprite/render contracts)
  - `tests/test_battle_interface_integration.py` (17 tests - drives the real interface over a
    real GameState: state machine, derived duration, retarget, click/key skip, icon cache)

## 2026-09-21 - Right-click context menu on army composition unit icons

- **Why:** building a partial selection out of a garrison required CTRL + left-click on
  each unit icon. The only keyboard-free options were "select one" or "Select All", which
  made mouse-only play awkward.
- **Added:** right-clicking a unit icon in the bottom-UI strip opens a small drop-down
  anchored to that icon:
  - no *other* unit of that garrison selected -> **Select**, **Cancel**
  - other units selected, this one is not -> **Select**, **Add to Group**, **Cancel**
  - other units selected and this one is too -> **Select**, **Remove from Group**, **Cancel**
  `Select` replaces the selection; Add/Remove from Group is the CTRL+click toggle, with the
  label reflecting which way it will go. Options are frozen at open time.
- **Modal while open:** Priority 0 in the left-click chain, so it consumes every click -
  clicking outside closes it with no action (a dismissing right-click on the map does NOT
  also issue a movement order), and nothing beneath the drop-down is clickable
  or hoverable (hover is suppressed in both `draw_army_composition_ui()` and
  `handle_mouse_motion()`). ESC and a second right-click also dismiss it.
- **Placement:** opens down-and-right of the icon, flips up over the map when it would run
  past the bottom of the screen, clamped to stay on screen horizontally.
- **Styling:** dark panel with a thin golden border, white Cinzel `small_font` labels.
  Hover and click highlights use literal colours, not `lighten_color()`/`brighten_color()` -
  those scale multiplicatively and are invisible against a near-black panel.
- Also bounds-checked the "Unit Selection Info" instruction list (it grew a line) so it
  cannot spill past the bottom panel, and scaled its line spacing with `ui_scale`.
- Tests: `tests/test_unit_context_menu.py` (23 tests - options, actions, modal contract,
  placement, staleness, draw path, hover suppression)
- Files: `main.py`, `input/mouse_handler.py`, `tests/test_unit_context_menu.py`

## 2026-09-20 - Army circle hit area now matches the ring you can see

- **Reported:** hovering and clicking ~2mm BELOW the army circle still selected the army.
- **Cause:** not the new banner box - the banner stops exactly at the anchor and never
  reaches below it. It was the **circle**, and it had always been wrong.
  `_draw_army_circle()` draws the ring at **0.75 x** `ARMY_CIRCLE_RADIUS`, lifted **0.35 x**
  above the anchor (so the flag pole sits inside it), but all three passes hit-tested a
  **full-radius** circle centred **on** the anchor. The hit circle therefore reached
  `0.60 * radius` below the visible ring - measured **9.0 px** at min zoom, **13.5 px** at
  max - and picked up clicks on empty map. Widening the banner target simply made it
  noticeable.
- **Fix:** new `Game.get_army_circle_hit()` / `point_in_army_circle()`, derived from new
  `ARMY_CIRCLE_DRAW_SCALE` (0.75) and `ARMY_CIRCLE_DRAW_LIFT` (0.35) in
  `config/constants.py`. Click, hover and the renderer's own ring-brightening test all use
  it, and `_draw_army_circle()` plus the pulsing selection glow now derive their geometry
  from the same two constants (4 duplicated sites hoisted).
- The glow halo is excluded from the hit area on purpose: it is a soft alpha-35 decoration,
  not the object you aim at.
- Net effect: the clickable circle is exactly the drawn ring, and the banner covers
  everything above it. Nothing below the ring responds any more.
- Tests: `TestCircleMatchesTheDrawnRing` (7 tests) in
  `tests/test_army_banner_selection.py`, covering all three zoom levels.
- Files: `main.py`, `rendering/map_renderer.py`, `config/constants.py`

## 2026-09-20 - Army banners are fully selectable

- **Problem:** players expect to click the banner (flag), not just the small circle under
  it. The banner was only *half* clickable and never hoverable, so it read as decoration.
- **Cause:** the render, click and hover passes each computed the banner's geometry
  independently and disagreed:
  - render drew it spanning `anchor_y - flag_height` .. `anchor_y`
  - click tested only `anchor_y - flag_height/2` .. `anchor_y` - **the bottom half**, i.e.
    the thin pole, while the flag cloth was dead
  - hover (both the `hovered_army` state and the renderer's ring-brightening) ignored the
    banner entirely, so nothing ever hinted it was clickable
- **Fix:** one shared source of truth. New `Game.get_army_banner_rect()` /
  `point_in_army_banner()` / `get_effective_garrison_count()` / `get_garrison_anchor()`,
  used by all three passes. Hit area is now the **full** drawn banner, with width derived
  from the flag art's real aspect ratio instead of a fixed `2 x radius`.
- **Click priority is now circle > plot > banner** (`handle_map_area_click` PRIORITY 3 /
  4 / 4.5). The taller banner box overlaps building plots - including through the flag
  art's transparent margins - so banners resolve *after* plots and plot clicking is
  unchanged. `handle_mouse_motion` mirrors the same ordering.
- Circles are tested across **all** territories before any banner: at min zoom a banner is
  ~30 world units tall against a radius-25 sibling ring, so banners routinely overlap a
  neighbour's circle.
- **Two bugs fixed along the way:**
  1. The click path lacked the allied-reinforcement slot rule that render and hover both
     had, so mid-animation the flag was drawn ~25 world units off-centre while the click
     test still probed the territory centre - the garrison was briefly unclickable.
  2. Hovering a circle that overlapped a plot killed the army highlight even though
     clicking there *did* select the army.
- Magic number `3.3` (4 sites) hoisted to `ARMY_FLAG_HEIGHT_RATIO`, plus
  `DEFAULT_ARMY_FLAG_ASPECT`, in `config/constants.py`.
- **Cost:** 0.036 ms/frame worst case (banner test for all 57 territories, circle missing
  every time) = 0.2% of a 60 FPS budget. All 19 FPS benchmarks pass.
- Multi-garrison territories keep one banner per garrison; hover highlights any of them,
  clicking still only selects your own.
- Tests: `tests/test_army_banner_selection.py` (29 tests)
- Files: `main.py`, `rendering/map_renderer.py`, `config/constants.py`

## 2026-09-20 - Fixed: "display Surface quit" crash after toggling VSync

- **Bug:** enabling VSync and then opening the Campaign screen crashed with
  `pygame.error: display Surface quit` at `CampaignScreen(screen)`.
- **Cause:** applying VSync requires `pygame.display.quit()` + `init()`, and that **destroys
  the current display Surface object**. `main()` keeps the surface in a local `screen` and
  passes it to screens constructed later, so that reference was dead. Plain `set_mode()`
  never invalidated surfaces, so long-lived `screen` references had always been safe — the
  hazard only appeared once VSync could recreate the display.
- **Fix, two parts:**
  1. `set_display_mode()` now records the mode it established and **returns the existing
     surface unchanged when nothing needs to change**. Redundant calls (returning to the
     menu, re-applying the same settings) no longer destroy live surfaces. A genuine change
     still re-initialises.
  2. `main()` re-fetches the live surface via new `display_utils.current_surface()` at the
     top of its loop, and before constructing `CampaignScreen` / `SaveBrowser` /
     `ReplayBrowser` or inspecting the surface on the return-to-menu paths.
- **Side benefit:** VSync after a resolution change now measures 6.06ms/165Hz (was
  8.92ms/112Hz) — the redundant second re-initialisation is gone.
- Files: `display_utils.py`, `main.py`

## 2026-09-20 - Smooth (eased) mouse-wheel zoom

- Mouse-wheel zoom previously jumped a full notch per event. `handle_zoom()` now sets a
  **target** and `CameraHandler.update_zoom(delta_time)` eases toward it, called once per frame
  from the main loop. A single notch now spans ~22 frames instead of 1.
- **Frame-rate independent** smoothing (`1 - exp(-rate * dt)`), so the feel is identical at
  30/60/165 FPS — measured settle times 0.400s / 0.367s / 0.358s for the same notch.
- **Zoom-to-cursor holds for the whole interpolation.** The anchor (cursor position at the wheel
  event) is re-applied every step: the world point under it is sampled before the step and
  restored after. Measured drift across a full ease: **0.088 world px** (~0.2 screen px) where
  the camera is free to move. At map edges `clamp_to_bounds()` legitimately moves the camera and
  the anchor cannot hold — unchanged from the original behaviour.
- **Rapid notches accumulate**: each compounds from `target_zoom`, not the current eased value,
  so spinning the wheel does not lose notches.
- `is_zoom_settling` now covers the interpolation, so the renderer keeps treating the camera as
  active for its whole duration.
- **`cancel_zoom_interpolation()`** is called by `CameraAnimation` / `CameraZoomAnimation` and
  `reset_camera()`. Those drive `camera.zoom` directly, and a pending wheel target would
  otherwise pull the camera back mid-animation.
- **Benchmarks updated**: `handle_zoom()` no longer moves the camera by itself, so the wheel-zoom
  scenarios now call `update_zoom()` too. Without that they would have rendered static frames and
  reported inflated FPS.
- New `tests/test_camera_zoom.py` (10 tests) covering easing, accumulation, cursor anchoring,
  clamping, frame-rate independence, and the animation/reset interactions.
- Files: `input/camera_handler.py`, `main.py`, `tutorial_mission.py`, `campaign_utils.py`,
  `tests/test_fps_benchmark.py`, `tests/test_camera_zoom.py` *(new)*

## 2026-09-20 - Feature: VSync toggle + FPS limit (both options menus)

- **New settings:** `vsync` (bool, default **False** — opt-in so nothing changes for existing
  players on upgrade) and `fps_limit` (int, `0` = no manual cap). Added to both `SETTING_TYPES`
  and `defaults` in `settings_manager.py`; a key missing from `defaults` is deleted from
  config.json on every load, so both are required.
- **New `display_utils.py`** centralizes display creation. Every `pygame.display.set_mode()`
  call in `main.py` (17 sites) now routes through `set_display_mode()`. Three measured pygame
  behaviours make this necessary:
  1. `vsync=1` **without `pygame.SCALED` is silently ignored** — accepted, no error, frames
     unsynchronized (~1.3-1.9ms flips). Real VSync needs `SCALED`.
  2. **VSync is lost by any later `set_mode()`**, even one passing `vsync=1` and `SCALED` again
     (5.99ms → 0.95ms → 1.26ms). Only `display.quit()` + `display.init()` restores it. Since
     `apply_display_settings()` *is* the resolution path, without this VSync would have died the
     first time a player changed resolution and never returned.
  3. **The achieved state cannot be read back** — `get_flags()` does not report the SCALED bit.
     Tracked explicitly as `game.vsync_active`.
- **Graceful fallback:** if a driver refuses `SCALED`/`vsync=1`, `set_display_mode()` falls back
  to the previous flags so the game always launches; the achieved state is reported back.
- **Frame limiter** (`resolve_frame_cap`): manual cap > VSync (safety-capped at 240) > `FPS`
  constant, with `UNFOCUSED_FPS` when the window loses focus. Deliberately **never uncapped** —
  see the `delta_time` fix below.
- **`delta_time` now uses `time.perf_counter()`** instead of `Clock.get_time()`, which returns
  **integer milliseconds**. Measured in an uncapped loop: **100% of frames reported
  `delta_time == 0.0`**, with summed delta running at 250% of real time. Even at 1-2ms frames
  the quantization error reaches 50% per frame, visibly changing animation speed.
- **The per-frame defensive display guard** now routes through the helper — a bare `set_mode()`
  there would have silently and permanently dropped VSync mid-game.
- **UI:** VSync checkbox + FPS Limit cycle button in *both* options menus, each following its
  file's existing idiom. The FPS control displays "VSync" while VSync is on, since the monitor
  paces frames then. Options: `Unlimited, 60, 80, 120, 144, 165, 240` (`FPS_LIMIT_OPTIONS`).
- **Other screens** (menu, setup, cutscene, recap, loading, replay/save browsers, MP setup —
  14 call sites) now honour `fps_limit` via `menu_frame_cap()` instead of a hard-coded 60.
  VSync needs no handling there, being a property of the display surface.
- Verified end-to-end through the real `Game` path: vsync OFF 1.87ms (534Hz) → ON 6.27ms
  (160Hz) → **still synced after a resolution change** (8.92ms) → back to 6.06ms (165Hz) →
  OFF again 1.56ms. Settings round-trip through config.json and survive validation.
- Files: `display_utils.py` *(new)*, `main.py`, `main_menu.py`, `settings_manager.py`,
  `rendering/ui_renderer.py`, `config/constants.py`, + 11 screen modules

## 2026-09-20 - Fixed: renderer caches went stale after an in-game resolution change

- **Bug:** `MapRenderer.territory_bounding_boxes` and `multi_zoom_cache` are built once in
  `__init__` from `game.scaled_polygons`. `apply_display_settings()` re-derives `scale_factor`
  and re-rounds every polygon on a resolution change, but never rebuilt those caches — so they
  kept the **old** scale. Measured impact after switching 1600x900 → 1280x720:
  bounding boxes off by **178px**, multi-zoom polygons by **427px**, and the cached screen
  projection by **418px** versus a direct `world_to_screen()`. In practice: territory polygons
  visibly misaligned with the map background, and AABB hit-testing selected the wrong territory.
- **Fix:** new `MapRenderer.rebuild_scale_caches()`, called from `apply_display_settings()`.
  Rebuilds both pre-computed caches and clears everything derived from the old projection.
- Map *switching* was never affected — `MapRenderer` is constructed inside `initialize_game()`,
  which calls `_reload_map_assets()` first, so it always saw the correct map's polygons.
- **New regression tests:** `tests/test_resolution_caches.py` (4 tests) assert the caches track
  `scale_factor` across resolution changes and a round trip. Verified the tests genuinely fail
  without the fix (418px projection error). They skip themselves when the environment refuses
  the resolution change (e.g. a fullscreen window under `SDL_VIDEODRIVER=dummy`), since the
  regression cannot be exercised there.

## 2026-09-20 - Performance: overlay copy removal, surface clamping, overlay caching

- **Removed a 5.76MB full-screen surface copy per camera delta** (`map_renderer.py`). The
  ownership-overlay cache did `_overlay_cache_surface = fullscreen_overlay.copy()` on every
  camera move, purely so the cached content survived the next rebuild's `fill()`. But
  `fullscreen_overlay` is written nowhere else, so the cache can simply alias it.
- **Clamped hover/overlay surfaces to the screen.** Bounding-box sizes were floored at 1 but
  never capped, so a large territory at high zoom allocated a surface far bigger than anything
  visible (~1000x1000 = 4MB at zoom 4.0) — on every camera delta. Off-screen area cannot be
  seen and pygame clips the polygon draw anyway.
- **Cached `draw_territory_overlay()`**, which previously had *no* cache — it allocated a fresh
  SRCALPHA surface and re-filled a 455-1027 point polygon on every call, and campaign/tutorial
  highlight steps call it every frame with a pulsing alpha. Alpha is quantized to 16 steps so
  the result is cacheable with no visible change to the pulse.
- **FPS counter** now refreshes ~4x/second instead of every frame (`ui_renderer.py`). The string
  changed almost every frame, so each frame added a new entry to the very text cache it used —
  and a value updating 60+ times a second is unreadable regardless.

| Scenario | Baseline | Now |
|---|---|---|
| Panning @ zoom 3.0 | 39.9 FPS | **79.2 FPS** (+98%) |
| Static @ max zoom | 66.1 FPS | **236.3 FPS** (+257%) |
| Mouse-wheel zoom | 16.9 FPS | **41.3 FPS** (+145%) |
| Zooming with 99 glows | 6.6 FPS | **38.9 FPS** (+486%) |

- Files: `rendering/map_renderer.py`, `rendering/ui_renderer.py`, `main.py`

## 2026-09-20 - Campaign intro zoom is now continuous instead of stepped

- **Removed the 0.2-step zoom quantization** from both camera animation classes:
  `CameraAnimation.update()` (`tutorial_mission.py`, mission 1) and
  `CameraZoomAnimation.update()` (`campaign_utils.py`, missions 2-7).
- That `round(raw_zoom * 5) / 5` existed purely to limit how often the map rescale and the
  production-glow sprite cache were invalidated — it was a **performance workaround that made
  the intro visibly step rather than glide**. Both underlying costs are now gone (viewport-only
  map rescale, shared/quantized glow frames), so the workaround is no longer needed.
- Measured: the 1.5s intro sweep now produces **88 distinct zoom values across 90 frames**
  (previously ~12).
- **Verified no Z-SCALE regression.** `map_renderer` pre-scales polygons at 7 discrete
  `ZOOM_LEVELS` and corrects with `zoom_ratio = actual_zoom / nearest_zoom`; continuous zoom
  leans on that correction far more heavily. Compared the cached projection against a direct
  `world_to_screen()` projection at ten zoom values chosen to fall *between* the pre-computed
  levels (e.g. 2.61, nearest 2.80, ratio 0.932): **maximum error 0.000 px at every value.**
  Territory polygons track continuous zoom exactly.
- **Honest trade-off:** the zoom-sweep benchmark drops from 126.7 to 49.0 FPS (≈ the original
  50.0 FPS baseline), because the sweep now rescales on every frame rather than every ~8th.
  The animation is genuinely smooth where it was previously both stepped *and* 50 FPS, so this
  buys smoothness at no cost relative to the original. The remaining per-frame cost is camera-delta
  cache invalidation (`_overlay_cache_surface` + screen-polygon rebuild), measurable as the gap
  between a static frame (218.5 FPS / 6.4ms) and a panning frame (70.8 FPS / 15.6ms) — addressed
  by the culling/overlay-cache work that follows.

- Files: `tutorial_mission.py`, `campaign_utils.py`

## 2026-09-20 - Performance: viewport-only map rescale (replaces full-map scaling)

- **The whole map was rescaled on every zoom change** (`main.py`), building a surface of
  `(map_width * zoom, map_height * zoom)` from the 4096x3072 source — so the cost grew as
  **zoom squared** even though at most a viewport-sized slice is ever visible. At 1600x900
  that is 1.53M pixels at zoom 1.65 but **8.98M pixels (36MB) at zoom 4.0**. Measured:
  full-map `scale` 16.1ms, full-map `smoothscale` **53.1ms**, versus viewport `scale` 0.31ms
  and viewport `smoothscale` 2.50ms.
- **New `Game._blit_map_background()`** scales only the visible slice, used by both render
  paths (`draw()` and the live loop in `run()` — previously duplicated logic).
  - Source rect is derived from the **actual source surface size**, not the `ORIGINAL_MAP_*`
    constants, so it works for any map background and the black fallback surface.
  - Clips to `BOTTOM_UI_Y`, so the strip the bottom panel covers is never scaled.
- **Adaptive margin:** the cached slice is over-rendered by 192px per side *only when the zoom
  is unchanged*. Panning then re-blits the cached surface at a new offset instead of rescaling
  (a naive viewport rescale regressed panning from 69.8 to 49.9 FPS, because the old full-map
  cache happened to make panning free). While zoom changes every frame the margin is skipped,
  since the cache is invalidated regardless — that recovered ~25% on continuous-zoom FPS.
- **Quality improved, not traded:** because a viewport `smoothscale` is affordable every frame,
  the nearest-neighbour downgrade used during zoom animations is gone, along with the
  `cached_zoom_level = None` settle-invalidate that forced one full-map `smoothscale` (a
  guaranteed ~53ms hitch) whenever a zoom ended. The map is now full quality on every frame.
- Corrected a stale comment claiming `is_zoom_animating` made the pipeline skip "smoothscale,
  overlay rebuild" — `map_renderer.py` has never read that flag.

**Cumulative measured results (1600x900, original baseline → now):**

| Scenario | Baseline | Now | Gain |
|---|---|---|---|
| Zooming with 99 production glows | 6.6 FPS (213.9ms worst) | **37.2 FPS** (33.1ms) | +460% |
| Static @ max zoom | 66.1 FPS | **207.7 FPS** | +214% |
| Campaign-intro zoom sweep | 50.0 FPS | **126.7 FPS** | +153% |
| Mouse-wheel zoom | 16.9 FPS (75.5ms worst) | **39.7 FPS** (33.3ms) | +135% |
| Panning @ zoom 3.0 | 39.9 FPS | **70.7 FPS** | +77% |
| 107 buildings | 64.3 FPS | **161.0 FPS** | +150% |
| 171 banners | 59.4 FPS | **135.0 FPS** | +127% |

- Files: `main.py`

## 2026-09-20 - Performance: map background .convert() + shared production-glow sprite cache

Two fixes with large, measured FPS impact. Benchmarks: `py -m pytest tests/test_fps_benchmark.py -v -s`

- **Map background was never `.convert()`ed** (`main.py`) — the only image in the file
  not converted to display format. An unconverted 4096x3072 RGBA surface stays in *file*
  format and `transform.scale()` output inherits it, so the per-frame `screen.blit()` of
  the map was a per-pixel format conversion + alpha blend of ~1.4M pixels.
  - Measured blit of the scaled map: **9.26ms unconverted → 0.15ms converted** (`.convert_alpha()` = 0.74ms).
  - Both shipped backgrounds verified fully opaque (0 non-opaque pixels), so `.convert()` is
    lossless here. New map backgrounds must be opaque.
  - Centralized in `_load_map_background()`, used by `Game.__init__` and `_reload_map_assets()`
    (so it applies to Azincournean Highlands and future maps, including the black fallback).
  - `apply_display_settings()` now re-converts after `set_mode()`, since `.convert()` bakes in
    the display's pixel format and a resolution/fullscreen change can invalidate it.
- **ProductionGlowEffect rebuilt its 16-frame sprite cache on every zoom change**
  (`ui/effects/production_glow_effect.py`) — the cache key was the *raw continuous zoom float*,
  so every producing building rebuilt all 16 frames on every mouse-wheel tick and every frame
  of a campaign intro zoom. With ~100 producing buildings that is ~1,600 surface allocations
  and ~12,600 polygon draws in a single frame.
  - Zoom is now quantized to 0.1 steps (`ZOOM_QUANTIZE_STEPS`), capping rebuilds at ~24 across
    the whole 1.65-4.0 zoom range.
  - Sprite frames depend only on `(quantized zoom, player colour)` — ray angles are identical
    per instance and frames are baked at full alpha — so they are now shared process-wide via
    `_SHARED_SPRITE_CACHE` (bounded LRU). ~100 rebuilds per zoom change become **one**.
  - **Bug fix:** `update_color()` did not invalidate the cache, so a glow kept the previous
    owner's colour after a territory changed hands until the zoom happened to change.
  - Removed the now-duplicated instance `_draw_ray()` (superseded by module-level `_draw_ray_on()`).

**Measured results (1600x900, before → after):**

| Scenario | Before | After |
|---|---|---|
| Zooming with 99 production glows | 6.6 FPS (213.9ms worst) | **19.7 FPS** (63.6ms worst) |
| Static @ max zoom | 66.1 FPS | **211.7 FPS** |
| Campaign-intro zoom sweep | 50.0 FPS | **119.3 FPS** |
| Panning @ zoom 3.0 | 39.9 FPS | **69.8 FPS** |
| 107 buildings on map | 64.3 FPS | **163.7 FPS** |
| 171 banners on map | 59.4 FPS | **137.5 FPS** |

Mouse-wheel zoom (16.9 → 20.5 FPS) remains the weakest scenario; it is dominated by the
full-map rescale, addressed separately.

- Files: `main.py`, `ui/effects/production_glow_effect.py`

## 2026-09-20 - Fixed: FPS benchmark suite could not run (NameError)

- **Bug:** All 8 tests in `tests/test_fps_benchmark.py` errored at setup with `NameError: name '_set_app_icon' is not defined`, making the performance suite completely unrunnable.
- **Cause:** `_app_icon`, `_ico_path` and `def _set_app_icon()` were declared inside the `if __name__ == "__main__":` block. That block never executes when `main.py` is *imported* rather than run as a script, so `Game.__init__` (which calls `_set_app_icon()` after `set_mode`) raised `NameError` for any importer — tests, benchmarks, and tooling. Running the game normally was unaffected, which is why this went unnoticed.
- **Fix:** Hoisted the icon helpers to module level (above `class Game`) and split loading from applying:
  - `_load_app_icon()` — loads and caches the icon; safe to call before `pygame.display` is initialized.
  - `_set_app_icon()` — unchanged behaviour, now lazily loads via `_load_app_icon()`.
  - The `__main__` block now calls `_load_app_icon()` + `pygame.display.set_icon()` instead of redefining them.
- **Result:** `py -m pytest tests/test_fps_benchmark.py` → 8 passed. Icon behaviour when running the game is unchanged.
- Files: `main.py`, `.gitignore`

## 2026-04-18 - Gold Transfer Feature (ally-to-ally gold sending)

- **Feature:** Players can now send gold to their allies during the Planning phase.
  - **Setup:** New "Gold Transfer" dropdown in Additional Options (custom game + multiplayer lobby). Options: Disabled, Enabled (25%), Enabled (50%), Enabled (75%), Enabled (100%). Default = Disabled.
  - **Rule:** Per-recipient cap = `floor(pct × sender's current gold)`. One transfer per (sender → recipient) pair per turn/round. Humans only (AI does not transfer gold). Campaigns always force Disabled.
  - **Players window:** New "Players" button in top-left of the top UI bar (next to Menu). Opens a non-pausing modal listing all players with columns: Name, Controller, Team, Color, Status (Playing/Eliminated/Left), Transfer Gold input, Send button.
  - **Input field:** Digit-only, capped at 7 digits, auto-clamps to the recipient's current cap on every keystroke.
  - **Tooltips:** Disabled rows show the reason on hover (enemy, self, eliminated, left, already-sent this turn, not-in-planning-phase, not-your-turn, disabled-feature).
  - **Feedback:** "Transfer successful." toast after a successful send; field + button lock for the rest of the turn.
- **Multiplayer:** Sender applies optimistically (instant local deduction) then broadcasts `GOLD_TRANSFER` message. Remote peers mirror the balance change without re-validation. Relayed to 3+ player games via the host.
- **Persistence:** Transfers are reflected in replay state diffs (with an annotating `gold_transfer` event); `gold_transfer_pct` and `gold_transfers_this_turn` are serialized into campaign saves.
- **New file:** `players_window.py`
- **Modified:** `integrated_setup.py`, `main.py`, `game_state/__init__.py`, `game_state/economy.py`, `simultaneous/sim_state.py`, `rendering/ui_renderer.py`, `network_config.py`, `network/protocol.py`, `network/server.py`, `network/lobby.py`, `network/territory_selector.py`, `network/multiplayer_setup.py`, `sync_logger.py`, `save_manager.py`

## 2026-04-18 - Bug Fix: Phantom flags after Fortress mutual elimination

- **Fix:** Attacking a neutral Fortress territory with a mutual-elimination outcome left both attacker's and defender's flags visible on the map.
  - Root cause: `_update_battle_results` early-returns when `winner == -1 and surviving_armies == 0`, trusting the dice-tie path to have cleared garrisons. The Keep two-phase combat path also reaches this branch (via neutral defender), but does not pre-clear.
  - Fix: clear `territory_garrisons[territory]` and `army_units[territory]` inside the early-return branch so both callers are covered.
- **Modified:** game_state/military.py (`_update_battle_results`)

## 2026-04-10 - Multi-Map Support + Fortress Territories

- **Feature:** Multi-map support — game now supports 5 maps (Avareon + 4 new placeholders)
  - Maps stored in `maps/` directory with per-map JSON data (polygons, plots, economy, bonuses, adjacencies, fortress territories)
  - `maps/manifest.json` registry defines available maps with metadata
  - Map selection via up/down arrows in both single-player and multiplayer setup screens
  - Host selects map in multiplayer; clients sync automatically
  - Maps without background PNGs show dark surface with polygon outlines
- **Feature:** Fortress territory mechanic — territories with innate +2 defense
  - Fortress territories cannot build Keeps (defense is innate)
  - Defense works identically to Keep Phase 2 battle (type-neutral)
  - Shown in territory hover tooltip and bottom bar info panel
  - AI aware: skips Keep building, accounts for fortress defense in threat assessment
- **Refactor:** `map_data.py` — module refactored for multi-map support
  - New `load_map(map_id)` function loads all data from map directory
  - Adjacencies now loadable from JSON (previously hardcoded); legacy fallback preserved
  - New globals: `FORTRESS_TERRITORIES`, `_current_map_id`
  - New accessors: `get_map_manifest()`, `get_map_ids()`, `get_map_display_name()`, `is_fortress_territory()`
  - Backward-compatible `load_polygons()` still works for campaigns and tools
- **Infrastructure:** Save/replay files now store `map_id` for multi-map games
- **Infrastructure:** Network protocol version bumped to 1.4.0 (map_id in SETUP_CONFIG)
- **Tools:** All dev tools (Polygon, Plot, Economic, Bonus, Adjacency) support `--map <map_id>` CLI arg
- **Tools:** Adjacency_Tool now saves to `adjacencies.json` instead of modifying Python source
- **New maps (placeholder data):** Azincournean Highlands, Naragonthid, Far East, Nordian Mountains
- **Modified:** map_data.py, main.py, integrated_setup.py, network/territory_selector.py, network/multiplayer_setup.py, network_config.py, game_state/military.py, game_state/buildings.py, ai_economy.py, ai_strategy.py, save_manager.py, replay_recorder.py, replay_viewer.py, all 5 dev tools
- **New files/dirs:** maps/ directory structure, maps/manifest.json

## 2026-03-28 - Cutscene MP4 Export

- **Feature:** Export cutscenes to MP4 video from the Cutscene Tool
  - New "Export MP4" button in Cutscene_Tool.py with options modal
  - Toggle subtitles on/off, toggle audio (voiceover + music) on/off
  - "Current" exports the selected cutscene; "All" exports every cutscene concatenated into one file (1s black gap between each)
  - Exports at 1920x1080 @ 60 FPS using H.264 encoding
  - Two-pass: renders frames offscreen then muxes audio via ffmpeg filter_complex
  - Progress bar overlay with ESC cancellation support
- **New file:** `cutscene_exporter.py` — offscreen frame renderer + ffmpeg piping
- **New dependency:** `imageio-ffmpeg>=0.4.0` (bundles static ffmpeg binary, no manual install)
- **Modified:** Cutscene_Tool.py, requirements.txt, requirements-dev.txt

## 2026-03-28 - Action Failure Feedback + Campaign Mission 7 Fix

- **Feature:** Denied actions (not enough gold, command limit, etc.) now show a floating notification in the top-left map area and play a denial sound
  - "Not enough resources." for gold failures (training, building, research, hero, castle upgrade)
  - "Cannot train more units — Command Limit reached." for command limit
  - Additional messages for army limit, queue full, hero limit
- **Feature:** `ChatNotificationEffect.add_system_notification()` for non-chat floating messages
- **Feature:** Programmatically generated denial tone in `global_sound.py` (no asset file needed)
- **Fix:** Training icons (both map quick-access and bottom bar) now show red hue when command limit is reached, consistent with how army limit and affordability are shown
- **Fix:** Campaign Mission 7: pre-research rows 0-1 for human player (was row 0 only), fixing training being blocked from turn 1 because ~90 starting units exceeded the 75 default command limit
- **Infrastructure:** `game_state.last_action_error` attribute for categorized failure feedback between game_state methods and UI layer
- **Modified:** game_state/__init__.py, game_state/buildings.py, game_state/heroes.py, global_sound.py, ui/effects/chat_notification_effect.py, rendering/map_renderer.py, main.py, campaign_mission_7.py

## 2026-03-27 - Enhanced Hero Ability Visual Effects + Battle Sound

- **Enhancement:** All 12 active hero abilities now have more prominent, dramatic visual effects
  - Larger particles (2px), flash rings, multi-layer combo effects across the board
  - **Vow of Silence:** NEW full-screen crimson particle wave sweeping left to right (~2.5s)
  - **Reinforce:** 180 particles, flash ring, longer float
  - **Extort Populace:** 40 particles/plot + gold polygon shimmer per territory
  - **Embargo:** Implosion bursts at enemy Keeps on activation + larger persistent bubbles (1.5x scale)
  - **Master Negotiator:** NEW green burst at Keep + green polygon bubbles on owned territories
  - **Aggressive Diplomacy:** 90 bubbles with border flash + center burst in orange
  - **Levy:** 8 staggered burst points + gold polygon overlay
  - **Royal Charisma:** 120 particles, white/gold palette, taller arc, source implosion burst
  - **Regicide:** 160 particles, contracting flash ring, dark aftermath particles
  - **Decisive Strike:** 180 particles, flash ring shockwave + delayed secondary burst
  - **Valorous Charge:** 120 particles, departure burst at Keep
  - **Relentless Charge:** 160 particles, flash ring + 4 staggered satellite bursts
- **Enhancement:** Battle sound now layers ReinforceSound.mp3 alongside BattleSound.mp3 for richer audio
- **New file:** `ui/effects/ability_silence_wave_effect.py` — screen-space crimson wave effect
- **Enhanced:** `AbilityBurstEffect` — new params: particle_size, flash_ring, delay
- **Enhanced:** `AbilityArcEffect` — new params: particle_size, arc_height
- **Enhanced:** `AbilityPolygonBurstEffect` — new params: bubble_scale, border_flash
- **Modified:** ability_burst_effect.py, ability_arc_effect.py, ability_polygon_burst_effect.py, map_renderer.py, main.py

## 2026-03-24 - Multiplayer State Sync Verification Logging

- **Feature:** New `sync_logger.py` — per-participant sync logs for multiplayer games
  - Records all gameplay actions (orders, battles, turn ends) with timestamps
  - Captures comprehensive state snapshots at every turn boundary
  - Logs checksum comparisons between host and clients
  - On desync: host requests client's full state, computes field-level diff, sends back to client
  - Both host and client log the diff for post-game diagnosis
  - Output: `Logs/sync/{game_id}_P{idx}_{host|client}_{date}.json`
- **Enhancement:** `calculate_state_checksum()` now covers ~15 previously missing fields
  - Added: territory_garrisons, hero_training_queue, hero_ability_cooldowns, hero_silence_status
  - Added: hero_ownership, eliminated_players, disconnect_eliminations
  - Added: embargo_blocked_players, player_master_negotiator_active, all 10 tech effect arrays
  - Desyncs in these fields are now detected and corrected instead of silently diverging
- **Network:** 3 new message types for desync diagnosis (v1.3.0)
  - STATE_DETAIL_REQUEST (host→client), STATE_DETAIL_RESPONSE (client→host), DESYNC_DIFF (host→client)
  - Network version bumped to 1.3.0
- **Modified:** sync_logger.py (new), game_state/__init__.py, network_config.py, network/protocol.py, main.py, simultaneous/sim_state.py

## 2026-03-24 - Fix 3+ Player Multiplayer Real-Time Sync

- **Bug Fix:** Server-side message relay for 3+ player games
  - Client messages were only forwarded to host, not relayed to other clients
  - Added `_relay_to_other_clients()` in server with `_RELAY_MESSAGE_TYPES` set
  - All gameplay messages (orders, battles, chat, hero abilities, turn ends) now relayed
  - Raw byte relay for zero re-encoding overhead; sender excluded to prevent echoes
- **Bug Fix:** Host now sends FULL_STATE_SYNC after receiving client TURN_END
  - Previously only sent when the host ended its own turn
  - Ensures all clients have authoritative state at every turn boundary
- **Bug Fix:** STATE_CHECKSUM no longer hardcoded to player 1
  - Changed `local_player_index == 1` to `!= 0` at 4 locations
  - All non-host players now send checksums for desync detection
- **Bug Fix:** `_sim_execute_merged_orders` missing order types
  - Added handling for demolish, upgrade_castle, train_hero, hero_ability orders
  - Wrapped non-movement order execution in try/finally for current_player safety
- **Modified:** network/server.py, main.py

## 2026-03-21 - Resolve Remaining Battles Button

- **Feature:** "Resolve Remaining Battles" button during Battle Phase
  - Appears below the phase indicator when the local player has pending battles
  - Auto-resolves all battles where the player is the resolver (no battle reports)
  - Uses GMenuButton.png with hover highlighting and tooltip
  - Supports sequential mode, simultaneous mode, and multiplayer sync
  - Hidden during tutorial missions and when battle UI is already open
- **Modified:** main.py, rendering/ui_renderer.py, input/mouse_handler.py, docs/CODE_GUIDE.md

## 2026-03-21 - Campaign Save/Load System

- **Feature:** Campaign Save Game
  - Save button in the in-game pause menu (campaign missions 2-7, disabled for tutorial)
  - Save dialog with custom save name input (defaults to "Turn N")
  - Duplicate names auto-append (1), (2), etc.
  - Saves stored as gzip-compressed JSON in Saves/ directory
  - Disabled during AI turns, intro sequences, and victory/defeat sequences with hover tooltips explaining why
- **Feature:** Saved Games Browser
  - Accessible via square button (bottom-left) on both campaign screen pages
  - Scrollable list with Mission, Save Name, Date, and Turn columns
  - Load and Delete buttons with confirmation dialog
  - Uses SaveGameButton.png icon with IconBorder.png frame
- **New files:** save_manager.py, save_browser.py
- **Modified:** campaign_mission_2-7.py (get_save_state/restore_save_state methods), campaign_screen.py, rendering/ui_renderer.py, main.py, input/mouse_handler.py

## 2026-03-21 - Disconnect Elimination + Universal Last-Team-Standing Victory

- **Feature:** Multiplayer disconnect elimination
  - When a multiplayer player disconnects and fails to reconnect within 60 seconds, they are eliminated
  - Eliminated player's territories distributed round-robin to living allies, or neutralized if no allies
  - All armies, buildings, heroes, and gold are destroyed
  - Chat notifications shown for disconnect ("AI taking over") and elimination events
  - New `DISCONNECT_ELIMINATION` network message type (network version 1.2.0)
- **Feature:** Universal last-team-standing victory condition
  - Any player with 0 territories is marked as eliminated and skipped in turn order
  - If only one team has territories remaining, that team wins — regardless of victory condition
  - Applies to all game modes (Custom, Multiplayer) and all victory types (Domination, Total Conquest, Capital Assault)
  - Fixes: game no longer continues after all enemies are eliminated in Domination/Total Conquest modes
- **Feature:** Anti-win-farming protection
  - If all enemies were eliminated via disconnect and none had >= 50 XP from gameplay actions, no XP is awarded
  - Prevents exploiting disconnect elimination for easy XP
- **Fix:** Aggressive Diplomacy hero ability now triggers victory check after territory capture
- **Fix:** Client now runs `check_victory()` after receiving `BATTLE_RESOLVE` for proper sync
- **Fix:** `FULL_STATE_SYNC` and `SIM_ROUND_COMPLETE` now include `eliminated_players` and `disconnect_eliminations` for safety net sync

## 2026-03-21 - Floating Chat Notifications

- **Feature:** Chat messages now briefly appear as floating notifications in the top-left of the map area
  - Messages display for 5 seconds then fade out over 1 second
  - Up to 5 messages stack vertically; excess messages push oldest out immediately
  - Player name shown in faction color (bold), message in white, team tag in blue
  - Dark semi-transparent background for readability over map terrain
  - Respects team/all channel visibility filtering
  - New effect module: `ui/effects/chat_notification_effect.py`

## 2026-03-20 - Campaign Mission 7: The Fall

- **Feature:** Added two achievements for Mission 7
  - "The Fall" — completion achievement for winning Chapter 7 (Campaign7Achiev.png icon, no reward)
  - "Spending Spree" — bonus achievement for winning without ever exceeding 3500 gold (Campaign7BonusAchiev.png icon, rewards The Governor Icon)
- **Feature:** New campaign mission "Chapter 7: The Fall"
  - 41 territories (Mission 6 map + Damlére, Free Cities, Lunedale, Affrancian Uplands, March of Auverne, Carnae, Vense, Zjoal Islands)
  - 2 factions: Human (Blue, 23 territories) vs Central Alliance (Red AI, 18 territories)
  - Custom AI with garrison enforcement on 6 core territories (minimum 13 armies)
  - 5 pre-assigned heroes across both factions
  - Intro sequence with camera zoom/pan and 3 transmissions
  - Victory/defeat transmissions with dynamic speaker based on defeat cause
  - Victory: conquer all Central Alliance territories
  - Defeat: lose Courtieux (King Aidam Narn), Lunedale (General Neil Hévilneu), or all territories

## 2026-03-18 - Fix Simultaneous Mode Multiplayer Bugs

- **Bug fix (CRITICAL):** Client garrison desync — duplicate units spawned every round
  - Root cause: Client's SIM_ROUND_COMPLETE handler called `finish_training()` on already-processed
    training queues from host, double-decrementing timers and spawning duplicate units into garrisons
  - Also: `start_planning_phase()` ran AFTER applying host garrisons, resetting newly trained units'
    'moved' status to 'ready' — then `finish_training()` re-added them with 'moved', creating duplicates
  - Fix: Moved `start_planning_phase()` before authoritative override, removed `finish_training()` call
    (host already ran it, authoritative garrisons/training_queue are the final word)
- **Bug fix (HIGH):** Timer expiry discarded all movement orders in simultaneous mode
  - Root cause: `update_timers()` called `mark_ready()` which set `players_ready=True`, then
    `add_order()` silently rejected orders because the player was already marked ready
  - Fix: Detect when timer is about to expire, convert movement orders BEFORE `update_timers()`
    calls `mark_ready()` — mirrors the End Turn button flow (convert first, mark ready second)

## 2026-03-18 - Icon Fix + Alt+F4 Exits Entire App

- **Bug fix:** Missing `_set_app_icon()` call after fullscreen reapply in `apply_display_settings` — taskbar icon could revert to default Python icon on Windows with display scaling
- **Enhancement:** Alt+F4 (`pygame.QUIT`) now exits the entire app from any screen
  - Previously, Alt+F4 on setup/selector/recap/replay screens just returned to the previous screen
  - All screens now propagate a `'quit'` signal; callers in main.py detect it and call `pygame.quit(); sys.exit()`
  - Affected screens: IntegratedSetup, TerritorySelector, MultiplayerSetup, CampaignScreen, MissionScreen, RecapScreen, ReplayBrowser, ReplayViewer

## 2026-03-18 - Steam Invite Friend for Multiplayer

- **Feature:** "Invite Friend" button in multiplayer lobby (host-only, territory selector)
  - Disabled with "(Steam not connected)" hint when Steam is unavailable
  - Opens modal friend picker panel showing online Steam friends
  - Each friend has an "Invite" / "Invited" button; sends Steam game invite with host IP:port
  - Scrollable list with mouse wheel support, close via X / Escape / click outside
- **Feature:** Auto-connect on Steam invite accept
  - When invited friend accepts, game launches with `+connect ip:port` command-line argument
  - Parses `+connect` from `sys.argv`, skips main menu, auto-joins host's lobby as client
  - Falls back to main menu on connection failure
- **Steam integration:** Added `can_invite()`, `get_online_friends()`, `invite_friend()` to `SteamManager`
  - Uses SteamworksPy `GetFriendCount`/`GetFriendByIndex`/`GetFriendPersonaName` for friend enumeration
  - Uses `InviteFriend(steam_id, connect_string)` for sending invites

## 2026-03-18 - Fix Multiplayer Loading Screen Host Stuck

- **Bug fix (CRITICAL):** Host permanently stuck on "Waiting for other players..." in multiplayer loading screen
  - Root cause: `LoadingScreen` created a fresh `NetworkProtocol()` with seq=0, but the server's anti-replay check
    had already tracked higher seq numbers from the lobby phase — client's GAME_READY silently rejected as duplicate
  - Fix: Reuse `network_connection.protocol` instead of creating a fresh instance
- **Bug fix (MEDIUM):** Client misinterpreted host's initial "I'm ready" broadcast as "all players ready"
  - Host now only broadcasts GAME_READY as confirmation after ALL clients (and host) are ready
  - Prevents client from prematurely exiting loading screen before true all-ready confirmation

## 2026-03-16 - Multiplayer Sync Deep Audit (Phase 2)

- **Bug fix (HIGH):** Client SIM_ROUND_COMPLETE handler missing `finish_castle_upgrades()` and `_tick_building_xp()`
  - Castle upgrades never completed on client in simultaneous mode (timers never decremented)
  - Building veterancy XP (Farms/Mines) never progressed on client
  - Now mirrors host's `sim_state.complete_round()` logic
- **Bug fix (HIGH):** Demolish not synced in simultaneous mode
  - All 3 demolish send paths guarded by `self.sim_state is None`, only sending in sequential mode
  - Building state diverged permanently when player demolished during sim planning phase
  - Removed guard so demolish syncs in both modes
- **Enhancement:** SIM_ROUND_COMPLETE now includes building state safety net
  - Added: buildings, under_construction, training_queue, castle_upgrades, castle_upgrades_in_progress, building_xp, hero_ownership
  - Client applies authoritative building state after local round-end processing
  - Previously only gold, garrisons, heroes, research were synced — buildings had no correction mechanism
- **Enhancement:** Added embargo_blocked_players and player_master_negotiator_active to both FULL_STATE_SYNC and SIM_ROUND_COMPLETE
  - Transient hero ability state now has safety net if ability message is lost
- **Bug fix (MEDIUM):** FULL_STATE_SYNC silently dropped during battles/animations
  - Previously returned early, losing the sync correction entirely
  - Now queues pending data and applies after battles/animations clear
- **Enhancement:** Expanded STATE_CHECKSUM with under_construction, training_queue, castle_upgrades, castle_upgrades_in_progress
  - More divergence types now detected by checksum mismatch → triggers corrective FULL_STATE_SYNC
- **Docs:** Updated CODE_GUIDE.md with sync safety net guidance for future multiplayer changes

## 2026-03-16 - Multiplayer Sync Audit & Fix

- **Bug fix (CRITICAL):** Hero abilities were never synced in sequential multiplayer mode
  - All 11 hero abilities (Royal Charisma, Aggressive Diplomacy, Levy, Reinforce, etc.) caused immediate desync
  - Fixed by removing `sim_state is not None` gate on ability network send (affects both targeted and immediate abilities)
- **Bug fix (CRITICAL):** Multiple game actions not synced in sequential multiplayer mode
  - Training orders, castle upgrades, research, hero training all executed locally without notifying remote player
  - Added network sends for: training start/cancel, castle upgrade start/cancel, research start/cancel, hero training start/cancel
  - Added completion notifications at turn start for castle upgrades and hero training
- **Bug fix (MEDIUM):** Royal Charisma random desync in simultaneous mode
  - `random.sample()` was called independently on host and client, selecting different stolen units
  - Fixed by including stolen unit IDs in network message; receiver uses host's selections
- **Enhancement:** Added FULL_STATE_SYNC safety net for sequential multiplayer mode
  - Host sends authoritative state (gold, territories, garrisons, buildings, research, heroes, tech effects) at every turn boundary
  - On checksum mismatch, host sends corrective FULL_STATE_SYNC (replaces TODO)
- **Protocol:** Added `RESEARCH_ORDER` and `HERO_TRAINING_ORDER` message types; extended `ORDER_REMOVE` with `cancel_type` field for training/castle/hero/research cancels
- **Protocol:** Bumped `NETWORK_VERSION` to 1.1.0

## 2026-03-15 - Add New Music Tracks

- **New content:** Added 8 new music tracks
  - 7 tracks added to Game Music + Main Menu rotation: Battlefield Sunset, Late Night Dance, Morning Star, Night Before the Battle, On the Market, Sad Knight Different Version, Soul of the Nation
  - 1 track added to Recap Screen rotation: Northern Warrior Cmaj (joins existing Northern Honour)
  - Recap screen now randomly picks from multiple recap tracks instead of always playing the same one

## 2026-03-15 - Fix Steam Achievements + Steam Player Name

- **Bug fix:** Steam achievements silently failed to unlock despite in-game achievements working
  - Root cause: `RequestCurrentStats()` was never called after `SteamInit()` — required by Steamworks before `SetAchievement`/`GetAchievement`/`StoreStats` will function
  - Added `RequestCurrentStats()` call in `initialize()` and `pump_until_stats_ready()` to block until stats are loaded before syncing
  - Fixed achievement ID encoding: SteamworksPy achievement methods lack `argtypes`, so strings must be explicitly encoded to bytes
- **New feature:** Player name auto-populated from Steam persona name when running via Steam
  - Profile name field shows Steam name with "(Steam)" indicator and is non-editable
  - Steam name auto-saved to settings on startup, used everywhere (profile, multiplayer, in-game)
  - Without Steam, name editing works as before
- **Enhancement:** Added `steam_manager.run_callbacks()` to main menu loop for Steam overlay support in menus

## 2026-03-10 - Campaign Mission 6: The Second War

- **New feature:** Implemented Campaign Mission 6 "The Second War"
  - 3 factions: Human (Red) vs Northern Powers (Blue, Hard AI) + Independent States (Yellow, Med AI)
  - 33 playable territories with alliance system (player_teams [0, 1, 1])
  - 4 sequential quests with progressive territory transfers and unlock chain
  - Dynamic AI: Blue activates when Red attacks Yellow (max 1 army), angers when Red attacks Blue (max 3 armies)
  - Yellow AI: passive toward Red, trains up to 6 armies per territory, fortifies own only
  - Territory attack restrictions: Red blocked from targeting certain territories until quests unlock them
  - Heroes: Vearen Asford (Leuse Valley) and Halon Nextroy (Valeonia) pre-assigned
  - Research: Red/Yellow rows 0-2, Blue rows 0-5 (all 3 columns)
  - Victory: Complete all 4 quests. Defeat: Red loses all 4 core territories simultaneously
- **New hook:** `is_attack_target_blocked()` in main.py right-click handler for campaign territory restrictions
- **campaign_screen.py:** Updated Mission 6 title from "TBD" to "The Second War"

## 2026-03-10 - Fix Victory Not Triggering After Uncontested Captures

- **Bug fix:** Victory conditions (Domination, Total Conquest) never triggered when all territory captures were uncontested (no battles)
- Root cause: `check_victory()` was only called after battle resolution and Capital Assault eliminations — never after undefended territory captures for other victory modes
- `game_state/military.py`: Added `check_victory()` call after every uncontested territory capture, moved outside the Capital Assault guard
- `simultaneous/sim_phase_manager.py`: Added `check_victory()` after uncontested captures and unconditionally after battle resolution

## 2026-03-08 - Captain Dies Last in Combat

- **Balance:** Captains now always die last in casualty priority, regardless of unit level or counter matchup
- Lore justification: Captains are behind the army as support units
- `game_state/military.py`: Added Captain check as primary sort key in `apply_casualties_with_priority()`

## 2026-03-08 - Neutral Armies Game Mode

- **New feature:** Activate the "Neutral Armies" Additional Options toggle for custom games and multiplayer
- All unclaimed territories start with 1-2 hostile units (random Swordsman/Archer/Pikeman/Cavalry composition)
- Territories adjacent to player starts get 1 unit; others get 2
- Neutral garrisons defend when attacked (trigger battles) but never move, build, or take turns
- Once defeated, neutral armies are gone permanently (no respawn)
- `main.py`: Placement logic after territory assignment using seeded RNG for multiplayer determinism
- `game_state/military.py`: `has_neutral_garrison` check in `_process_arrivals()`, neutral defender branch, player -1 guards in battle resolution
- `main.py`: Gray flag icons created by tinting player 0's flags
- `network/multiplayer_setup.py`: Added `game_seed` to setup config for deterministic sync
- AI, victory conditions, simultaneous mode all work without changes (existing -1 guards sufficient)

## 2026-03-08 - Randomize Territory Bonuses Feature

- **New feature:** Activate the existing "Randomize Territory Bonuses" Additional Options toggle
- `map_data.py`: Added `randomize_territory_bonuses()` (balanced distribution: 6 per type + 3 random) and `apply_territory_bonuses()` (multiplayer client sync)
- `main.py`: `initialize_game()` now acts on `randomize_bonuses` flag — generates or applies randomized mapping
- `network/territory_selector.py`: Host generates mapping in `_launch_game()`, injects into LOBBY_LAUNCH settings; client extracts and stores it
- `network/multiplayer_setup.py`: Passes `bonus_mapping` through to setup config for client-side application
- Campaign missions unaffected (they never set `randomize_bonuses=True`)

## 2026-03-08 - Fix Hero Training Bypass in Campaign Mission 3

- **Bug fix:** Hero training buttons were visible and clickable in campaign mission 3, allowing players to train heroes when only pre-assigned Serthus Diarcess should be available
- Added `should_hide_hero_training()` to `campaign_mission_3.py` (missions 4/5/6 already had it)
- Added `is_action_allowed('train_hero')` defense-in-depth check in `main.py` hero training click handler

## 2026-03-06 - Background Music System & Volume Controls

- **New feature: Background music** with 3 categories (menu, game, recap)
- `music_manager.py` (new): MusicManager class using pygame.mixer.music for streaming playback
  - Menu Music: plays across all menus uninterrupted, intro track first on fresh session
  - Game Music: starts after loading screen, random track order
  - Recap Music: loops "Northern Honour - Recap Screen.mp3" during post-game recap
  - No-repeat-within-2-songs shuffling for menu and game categories
  - MUSIC_END_EVENT forwarding in all screen event loops
- **Functional volume sliders** replacing "Coming Soon" placeholders in both options menus
  - Master Volume: multiplier on both music and SFX (default 80%)
  - Music Volume: controls background music (default 50%)
  - SFX Volume: controls all sound effects (default 50%)
  - Live preview while dragging sliders, revert on Cancel
  - Persisted to config.json via settings_manager
- Music transition points: menu→loading (stop), loading→game (start game), game→recap (start recap), recap→menu (restart menu)
- Files: `music_manager.py` (new), `settings_manager.py`, `main.py`, `main_menu.py`, `rendering/ui_renderer.py`, `campaign_screen.py`, `integrated_setup.py`, `recap_screen.py`, `replay_browser.py`, `replay_viewer.py`, `network/multiplayer_setup.py`, `network/territory_selector.py`

## 2026-03-06 - Replay System

- **New feature: Game replay recording and playback** for custom games (vs AI) and multiplayer
- `replay_recorder.py`: Records full game state snapshots at each turn boundary in memory. Snapshots include territory ownership, armies, garrisons, buildings, heroes, tech, economy, movement orders, and player stats. Saved on demand from Recap screen as gzip-compressed JSON to `Replays/` folder.
- `replay_viewer.py`: Standalone replay viewer with own map rendering. Features: timeline scrubber, play/pause/step/speed controls, player POV switching, right-side info panel (player stats, turn events, action log), territory hover tooltips, camera pan/zoom.
- `replay_browser.py`: File browser listing saved replays with metadata (date, players, turns, winner, duration). Watch and delete actions with confirmation dialog.
- "Save Replay" button added to Recap screen (left side, grays out to "Replay Saved" after save)
- "Replays" button added to main menu (between Multiplayer and Options)
- Hook points: `game_state/__init__.py` `_advance_to_next_player()`, `simultaneous/sim_state.py` `_advance_round()`
- Zero FPS impact during gameplay — snapshots run once per turn boundary, not per frame
- Files: `replay_recorder.py` (new), `replay_viewer.py` (new), `replay_browser.py` (new), `recap_screen.py`, `main_menu.py`, `main.py`, `game_state/__init__.py`, `simultaneous/sim_state.py`

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
