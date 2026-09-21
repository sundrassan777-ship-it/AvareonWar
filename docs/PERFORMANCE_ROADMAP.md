# Performance Roadmap

Deferred rendering/performance work, with the reasoning and measurements behind each
decision. Written after the 2026-09-20 optimization pass so a future maintainer can tell
what was already tried, what was deliberately *not* done, and why.

**Measure before implementing anything here.** Several items on this list looked
compelling before the September pass and are now nearly worthless, because the dominant
costs moved. The benchmark suite exists precisely to prevent optimizing from intuition.

```
py -m pytest tests/test_fps_benchmark.py -v -s
BENCH_LABEL=my-change BENCH_OUT=after.json py -m pytest tests/test_fps_benchmark.py -q
```

---

## Where things stand (2026-09-20, 1600x900)

| Scenario | Before | After | Gain |
|---|---|---|---|
| Zooming with 99 production glows | 6.6 FPS / 213.9 ms worst | **42.5 FPS / 30.7 ms** | +540% |
| Static @ max zoom | 66.1 FPS / 16.1 ms | **240.7 FPS / 5.2 ms** | +264% |
| Banner density (171 banners) | 59.4 FPS | **142.2 FPS** | +140% |
| Building density (107 buildings) | 64.3 FPS | **164.7 FPS** | +156% |
| Mouse-wheel zoom | 16.9 FPS / 75.5 ms | **43.3 FPS / 29.0 ms** | +157% |
| Panning @ zoom 3.0 | 39.9 FPS | **83.0 FPS** | +108% |
| Campaign-intro zoom sweep | 50.0 FPS | **54.9 FPS** | +10% |

What actually mattered, in order: the map background was never `.convert()`ed (9.26 ms →
0.15 ms **per frame**); production glows rebuilt a 16-frame sprite cache per building per
zoom change; the entire map was rescaled on every zoom change (up to 53 ms); and a 5.76 MB
full-screen surface was copied on every camera delta.

The zoom sweep gained least because it deliberately traded FPS for smoothness — the 0.2-step
zoom quantization was removed, so it now renders ~88 distinct zoom values instead of ~12.

---

## Deferred: small, safe, low value

These were investigated and consciously skipped. Doing them is not wrong, but do not expect
a measurable frame-rate change.

### `assign_garrison_position()` mutates game state from the render loop
`rendering/map_renderer.py` calls `game_state/garrison.py::assign_garrison_position()` once
per garrison per frame. It builds a list and a `set()`, and **deletes entries from
`garrison_positions`** — i.e. the renderer mutates game state while drawing.

- **Why deferred:** it does not appear in the top 20 entries of a `cProfile` of the draw
  loop. The correctness risk of changing it outweighed an unmeasurable gain.
- **Why it still deserves attention:** it is a design smell, not a performance one. A render
  pass should not mutate simulation state; if garrison bookkeeping is ever wrong in a way
  that correlates with *rendering*, this is the first place to look.
- **Approach:** compute positions once per frame (or behind a garrison-version counter) and
  have the renderer read them.

### Zoom-based level of detail (LOD)
Skipping inner rings, building letters and glow halos below a zoom threshold.

- **Why deferred:** the justification evaporated. Building count is now **flat** — 0 / 99 /
  107 buildings measure 165.4 / 165.9 / 164.7 FPS — and 114 extra banners cost ~2 FPS. LOD
  would have traded visible detail for ~2%, inside run-to-run noise.
- **When to revisit:** if entity counts grow substantially (much larger maps, many more
  plots per territory), re-measure `TestCrowdedMapPerformance` first. Only implement if
  density actually shows a slope.

---

## Deferred: real bugs, small impact

### `battleeffect.py` / `alliance_marker_effect.py` caches never hit
Both do:

```python
icon_scale = 1.0 + scale_amount          # derived from self.progress, a continuous float
if self.cached_scale_factor != icon_scale:
    self.cached_scaled_icon = pygame.transform.smoothscale(...)
```

`icon_scale` changes almost every frame, so the comparison is essentially always true and
the effect `smoothscale`s **every frame** — despite the comment claiming "caching reduces to
<0.1ms". Verified by reading the animation source; not yet measured in a frame budget.

- **Fix:** quantize the cache key, exactly as `ProductionGlowEffect` now does
  (`round(scale * N) / N`). Small, self-contained, low risk.
- **Why deferred:** these are transient effects (a battle, an alliance marker), not
  continuous per-frame costs across many entities like the production glow was.

**Done for `battle_interface.py` (2026-09-21).** The same bug lived in the pulsing battle
icon, which had no cache at all and `smoothscale`d every frame in both the SETUP and
ANIMATING states, in two duplicated copies. Both now go through
`EnhancedBattleInterface._render_pulsed_icon()`, which quantizes the pulse scale to 1/64 and
caches into a bounded dict. `battleeffect.py` and `alliance_marker_effect.py` are still
outstanding.

### Pre-existing `TestDominationVictory` failures
3 tests in `tests/test_victory.py` fail: `test_winner_at_threshold`,
`test_sets_phase_ended` (phase stays `'playing'`), `test_sets_winner` (`winner` stays `-1`).

**Confirmed pre-existing** — they fail at tag `pre-vsync-optimization` (`0effbdf`), before
any of this work. Unrelated to rendering. Check first whether the tests encode stale
expectations (a changed win-condition default or threshold) rather than a real regression;
296 other tests pass.

---

## Not attempted: larger structural changes

Ordered by expected value. All are substantially more invasive than anything in the
September pass, and none should be started without a fresh profile.

### 1. Polygon simplification
Avareon has **57 territories / 25,934 vertices** (avg 455, max 1027); Azincournean has
55 / 13,263. The renderer's own comment assumed "30-80 vertices". Roughly 31% of vertices
collapse to duplicates once scaled by ~0.21, so they cost work and produce nothing.

- **Gain:** every polygon fill, outline and projection scales with vertex count — this is
  the single largest remaining structural lever.
- **Risk:** territory borders are gameplay-visible and hand-authored. Simplification must be
  offline (a tool pass writing simplified polygons alongside the originals), tolerance-driven,
  and visually diffed. Do **not** simplify at runtime.
- **Watch:** `map_data.point_in_polygon()` hit-testing must use the same geometry the player
  sees, or clicks will disagree with the borders.

### 2. Dirty-rect / partial-screen updates
Only repaint regions that changed, rather than the whole frame.

- **Gain:** large for a static camera, which is the common case during planning.
- **Risk:** high. Every effect, popup and overlay must report its damaged region correctly;
  a single missed rect leaves visible smears. The current architecture redraws everything
  unconditionally, so this is a broad change.

### 3. GPU texture path for the map (`pygame._sdl2`)
Upload the map once as a texture and let the GPU handle scale/pan.

- **Gain:** would make the map background essentially free at any zoom.
- **Risk:** `pygame._sdl2` is a separate rendering model; mixing it with `Surface.blit()` for
  everything else is the hard part. Likely an all-or-nothing renderer rewrite.
- **Note:** `set_display_mode()` already creates a `SCALED` renderer when VSync is on, so
  some groundwork exists.

### 4. Overlay reuse across camera deltas (offset-shifting)
`_overlay_cache_surface` is invalidated by *any* camera change. When only the offset moves
(panning at fixed zoom), the overlay content is unchanged — it could be re-blitted at a new
position, with only newly-exposed edges redrawn. This is the same trick
`_blit_map_background()` already uses with its 192 px margin.

- **Gain:** panning is already 83 FPS, so this is refinement rather than rescue.

### 5. Pre-baked map mipmap tiers
Pre-scale the map at each `ZOOM_LEVELS` entry and pick the nearest, instead of scaling the
visible slice each time.

- **Gain:** now small — viewport `smoothscale` costs ~2.5 ms and only runs when the view
  actually changes.
- **Cost:** memory. A full pre-scaled map at zoom 4.0 is ~36 MB, which is precisely what the
  viewport rescale was introduced to avoid.

### 6. Sprite-batching plots and banners
Composite per-territory icons into a single atlas blit.

- **Gain:** minimal today — density is flat (see LOD above).

### 7. Retire the dual camera state
`Game` mirrors `camera_zoom` / `camera_offset` alongside `CameraHandler.zoom` / `.offset`,
and the two must be synced by hand every frame. `MapRenderer` and `Game.draw()` read the
mirrors, so forgetting a sync renders a stale frame — a trap that has to be worked around in
every benchmark (`sync_camera()` in `tests/test_fps_benchmark.py` exists solely for this).

- **Gain:** no performance change; removes a recurring correctness hazard.
- **Risk:** mechanical but wide — every reader of `game.camera_*` must move to `game.camera.*`.

---

## Rules worth keeping

Learned the hard way during this pass; the full versions live in
[CODE_GUIDE.md](CODE_GUIDE.md) under "Performance Patterns".

1. **`.convert()` every loaded image**, backgrounds included. An unconverted surface makes
   every blit of it a per-pixel format conversion. `transform.scale()` output inherits the
   source format, so converting the original is what counts.
2. **Never key a cache on a raw continuous float.** Quantize it, or the cache never hits.
3. **Scale only what is visible.** Full-map work grows as zoom², viewport work does not.
4. **Cache, don't copy**, full-screen surfaces; and clamp bbox-sized surfaces to the screen.
5. **Rebuild scale-derived caches** when `scale_factor` changes (`rebuild_scale_caches()`).
6. **A benchmark that renders the same frame N times measures nothing.** The original suite
   reported ~60 FPS while live zooming ran at 6.6. Drive state with `before_frame`, and
   assert on `worst_frame_ms` — a 50 ms hitch is invisible in an average.
