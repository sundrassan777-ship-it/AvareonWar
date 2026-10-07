# -*- coding: utf-8 -*-
"""
FPS Performance Benchmark Suite for AvareonWar

Measures rendering performance under various game state conditions.
Manual execution only (not for CI - hardware-dependent).

Run with: pytest tests/test_fps_benchmark.py -v --tb=short
"""

import pytest
import time
import statistics
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FPSMeasurement:
    """Utility class for FPS measurement."""

    def __init__(self, sample_count=60):
        """
        Initialize FPS measurement.

        Args:
            sample_count: Number of frames to measure (default 60 = 1 second at 60 FPS)
        """
        self.sample_count = sample_count
        self.frame_times = []

    def measure_frame(self, game):
        """Measure a single frame's render time."""
        import pygame
        start = time.perf_counter()
        # Call the main draw loop
        game.draw()
        pygame.display.flip()
        end = time.perf_counter()
        self.frame_times.append(end - start)

    def run_benchmark(self, game, before_frame=None, warmup=0):
        """
        Run full benchmark and return statistics.

        Args:
            game: Game instance to render.
            before_frame: Optional callable(frame_index) invoked immediately before
                each measured frame. Use it to move the camera, advance an animation,
                or otherwise change state between frames.

                WHY THIS MATTERS: without it, this benchmark renders the *identical*
                static frame N times, so every camera-keyed cache (cached_zoom_level,
                _overlay_cache_surface, cached_screen_polygons) hits after frame 1.
                That hides the real cost of zooming and panning entirely — the suite
                reported ~60 FPS while live zooming stuttered badly.
            warmup: Frames to render before measuring (not recorded). Useful to warm
                lazily-built caches so the first sample isn't an outlier.
        """
        self.frame_times = []

        for i in range(warmup):
            if before_frame is not None:
                before_frame(i)
            self.measure_frame(game)
        self.frame_times = []

        for i in range(self.sample_count):
            if before_frame is not None:
                before_frame(i)
            self.measure_frame(game)

        if not self.frame_times:
            return {'avg_fps': 0, 'min_fps': 0, 'max_fps': 0, 'avg_frame_ms': 0,
                    'worst_frame_ms': 0, 'stddev_ms': 0, 'percentile_99': 0}

        avg_frame_time = statistics.mean(self.frame_times)
        min_frame_time = min(self.frame_times)
        max_frame_time = max(self.frame_times)
        stddev = statistics.stdev(self.frame_times) if len(self.frame_times) > 1 else 0

        return {
            'avg_fps': 1.0 / avg_frame_time if avg_frame_time > 0 else 0,
            'min_fps': 1.0 / max_frame_time if max_frame_time > 0 else 0,
            'max_fps': 1.0 / min_frame_time if min_frame_time > 0 else 0,
            'avg_frame_ms': avg_frame_time * 1000,
            # Worst single frame — a 50ms hitch is invisible in an average but is
            # exactly what the player perceives as a stutter. Assert on this too.
            'worst_frame_ms': max_frame_time * 1000,
            'stddev_ms': stddev * 1000,
            'percentile_99': statistics.quantiles(self.frame_times, n=100)[98] * 1000 if len(self.frame_times) >= 100 else max_frame_time * 1000
        }


# ============================================================
# RESULTS RECORDING
# ============================================================
# Results are collected in-process and written to a JSON file at session end so
# before/after runs can be compared mechanically instead of by hand-copying
# printed numbers into docs (which is how the stale 2026-03-04 figures arose).
# Override the destination with BENCH_OUT=path/to/results.json

BENCH_RESULTS = {}


def record(name, result, **extra):
    """Record a benchmark result for the JSON dump, and return it unchanged."""
    entry = {k: round(v, 3) for k, v in result.items()}
    entry.update(extra)
    BENCH_RESULTS[name] = entry
    return result


def report(title, result, extra_lines=()):
    """Print a benchmark result in the suite's standard format."""
    print(f"\n=== {title} ===")
    print(f"  Average: {result['avg_fps']:.1f} FPS")
    print(f"  Frame time: {result['avg_frame_ms']:.2f}ms avg")
    print(f"  Worst frame: {result['worst_frame_ms']:.2f}ms  ({result['min_fps']:.1f} FPS)")
    for line in extra_lines:
        print(f"  {line}")


# ============================================================
# SHARED HELPERS
# ============================================================

def sync_camera(game, zoom=None, offset=None, force_rescale=True):
    """
    Apply camera state the way the real render loop does.

    The Game keeps MIRRORS of the camera state (game.camera_zoom / game.camera_offset)
    alongside the CameraHandler itself (game.camera.zoom / .offset). MapRenderer and
    Game.draw() read the mirrors, so a benchmark that sets only game.camera.zoom
    renders a stale frame. main.py keeps them in sync each frame; we must too.
    """
    if zoom is not None:
        game.camera.zoom = zoom
    if offset is not None:
        game.camera.offset = list(offset)
    game.camera.clamp_to_bounds()
    game.camera_zoom = game.camera.zoom
    game.camera_offset = list(game.camera.offset)
    if force_rescale:
        # Force the map rescale path, as a real zoom change would
        game.cached_zoom_level = None


def populate_map(game, buildings_per_territory=0, producing=False,
                 armies=50, garrisons_per_territory=1, single_owner=None):
    """
    Fill the game state with a given entity density.

    Args:
        buildings_per_territory: Barracks per territory (clamped to that territory's
            real plot count — Avareon has 107 plots across 57 territories, NOT 4 each).
        producing: Give each Barracks an active training queue. This is what spawns
            ProductionGlowEffect instances, which rebuild a 16-frame sprite cache on
            every zoom change — the dominant crowded-map cost.
        single_owner: If set, assign every territory to this player. Production glows
            only render for the viewer's own/allied buildings, so use 0 to maximise them.
    """
    gs = game.game_state
    territories = list(game.scaled_polygons.keys())
    num_players = gs.num_players

    for i, territory in enumerate(territories):
        owner = single_owner if single_owner is not None else (i % num_players)
        gs.territory_owners[territory] = owner
        gs.armies[territory] = armies
        if hasattr(gs, 'armies_unmoved'):
            gs.armies_unmoved[territory] = armies

        gs.territory_garrisons[territory] = {
            (owner + k) % num_players: {'unmoved': armies, 'moved': 0}
            for k in range(garrisons_per_territory)
        }

        n_plots = len(game.scaled_plots.get(territory, []))
        count = min(buildings_per_territory, n_plots)
        gs.buildings[territory] = {j: 'Barracks' for j in range(count)}
        gs.training_queue[territory] = (
            {j: [('Swordsman', 2, 30)] for j in range(count)} if producing else {}
        )

    # Bump dirty-flag version counters so the renderer rebuilds its caches
    gs._territory_owners_version += 1
    if hasattr(gs, '_training_version'):
        gs._training_version += 1
    game.map_renderer.sync_production_glow_effects()
    return territories


def glow_effect_count(game):
    """Number of active production glow effects."""
    fx = getattr(game.map_renderer, 'production_glow_effects', None)
    return len(fx) if fx else 0


@pytest.fixture(scope="module")
def pygame_init():
    """Initialize pygame for all tests."""
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


@pytest.fixture(scope="session", autouse=True)
def dump_benchmark_results():
    """Write all recorded benchmark results to JSON at session end."""
    yield
    if not BENCH_RESULTS:
        return
    import json
    from datetime import datetime
    out_path = os.environ.get('BENCH_OUT') or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'benchmark_results.json')
    payload = {
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'label': os.environ.get('BENCH_LABEL', 'unlabeled'),
        'results': BENCH_RESULTS,
    }
    try:
        with open(out_path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, indent=2)
        print(f"\n[benchmark] results written to {out_path}")
    except OSError as exc:
        print(f"\n[benchmark] could not write results: {exc}")


@pytest.fixture
def game_instance(pygame_init):
    """Create a game instance for testing."""
    from main import Game
    game = Game()
    # game_state is None until initialize_game() is called with a setup config
    setup_config = {
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 'Normal'],
    }
    game.initialize_game(setup_config)
    game.game_state.phase = 'playing'
    return game


class TestFPSBaseline:
    """Baseline FPS tests for regression detection."""

    def test_idle_map_fps(self, game_instance):
        """Baseline: Idle map view should maintain 60+ FPS."""
        fps = FPSMeasurement()
        result = fps.run_benchmark(game_instance)

        print(f"\n=== Idle Map FPS ===")
        print(f"  Average: {result['avg_fps']:.1f} FPS")
        print(f"  Min: {result['min_fps']:.1f} FPS")
        print(f"  Max: {result['max_fps']:.1f} FPS")
        print(f"  Frame time: {result['avg_frame_ms']:.2f}ms avg")

        assert result['avg_fps'] >= 60, f"Idle FPS too low: {result['avg_fps']:.1f}"

    def test_sidebar_open_fps(self, game_instance):
        """Sidebar open should not drop FPS below 50."""
        game_instance.game_state.active_sidebar_tab = 'action_queue'
        # The flag lives on game_state (setting it on the Game object did nothing)
        game_instance.game_state.sidebar_expanded = True

        fps = FPSMeasurement()
        result = fps.run_benchmark(game_instance)

        print(f"\n=== Sidebar Open FPS ===")
        print(f"  Average: {result['avg_fps']:.1f} FPS")
        print(f"  Frame time: {result['avg_frame_ms']:.2f}ms avg")

        assert result['avg_fps'] >= 50, f"Sidebar open FPS too low: {result['avg_fps']:.1f}"

    def test_hero_panel_fps(self, game_instance):
        """Hero panel visible should not drop FPS below 50."""
        # Select a hero to trigger hero panel
        game_instance.selected_hero = 'Seledra Rennervail'

        fps = FPSMeasurement()
        result = fps.run_benchmark(game_instance)

        print(f"\n=== Hero Panel FPS ===")
        print(f"  Average: {result['avg_fps']:.1f} FPS")
        print(f"  Frame time: {result['avg_frame_ms']:.2f}ms avg")

        assert result['avg_fps'] >= 50, f"Hero panel FPS too low: {result['avg_fps']:.1f}"


class TestOptimizationRegression:
    """Tests to verify individual optimizations work correctly."""

    def test_crop_to_circle_performance(self, pygame_init):
        """crop_to_circle should complete in under 10ms after optimization."""
        from rendering.helpers import DrawingHelpers

        # Create test surface (100x100 = 10,000 pixels)
        test_surface = pygame_init.Surface((100, 100), pygame_init.SRCALPHA)
        test_surface.fill((255, 0, 0, 255))

        # Warmup
        for _ in range(5):
            DrawingHelpers.crop_to_circle(test_surface)

        # Measure
        times = []
        for _ in range(50):
            start = time.perf_counter()
            DrawingHelpers.crop_to_circle(test_surface)
            end = time.perf_counter()
            times.append((end - start) * 1000)

        avg_ms = statistics.mean(times)
        print(f"\n=== crop_to_circle Performance ===")
        print(f"  Average: {avg_ms:.3f}ms")
        print(f"  Min: {min(times):.3f}ms")
        print(f"  Max: {max(times):.3f}ms")

        # After optimization, should be < 10ms (before: 20-50ms)
        assert avg_ms < 10, f"crop_to_circle too slow: {avg_ms:.2f}ms"

    def test_text_cache_effectiveness(self, game_instance):
        """Text cache should return same surface for same input."""
        # First call - should cache
        surf1 = game_instance._get_cached_text("Test Label", game_instance.font, (255, 255, 255))

        # Second call - should return cached
        surf2 = game_instance._get_cached_text("Test Label", game_instance.font, (255, 255, 255))

        # Should be the SAME object (not just equal)
        assert surf1 is surf2, "Text cache not returning same surface"

        # Different text should return different surface
        surf3 = game_instance._get_cached_text("Different Label", game_instance.font, (255, 255, 255))
        assert surf1 is not surf3, "Text cache returned same surface for different text"

        print("\n=== Text Cache ===")
        print("  Cache hit verified")

    def test_rotated_tab_text_cache(self, game_instance):
        """Rotated tab text is rendered once and reused (expanded and collapsed)."""
        game_instance.draw_order_sidebar()
        cached = dict(game_instance._rotated_tab_text_cache)
        assert cached, "Rotated tab text cache not populated by draw_order_sidebar()"

        # Collapsed: the same bookmark labels, so no new rotations and same surfaces
        game_instance.toggle_sidebar(expand=False, animate=False)
        game_instance.draw_order_sidebar()
        assert game_instance._rotated_tab_text_cache == cached

        print("\n=== Rotated Tab Text Cache ===")
        print(f"  Cached labels: {len(cached)}")

    def test_sidebar_slide_fps(self, game_instance):
        """Collapse/expand slide: panel + content redrawn at a new x every frame."""
        import pygame
        game_instance.game_state.active_sidebar_tab = 'technology'
        slide_ms = 150

        def before(i):
            # Alternate collapse/expand, each frame 15 ms further into the slide
            game_instance.game_state.sidebar_expanded = (i // 10) % 2 == 1
            game_instance._sidebar_anim_start_ms = pygame.time.get_ticks() - (i % 10) * slide_ms // 10

        fps = FPSMeasurement()
        result = record('sidebar_slide', fps.run_benchmark(game_instance, before_frame=before, warmup=3))
        report('Sidebar collapse/expand slide', result)
        assert result['avg_fps'] >= 50, f"Sidebar slide FPS too low: {result['avg_fps']:.1f}"


class TestStressScenarios:
    """Stress tests for late-game performance scenarios."""

    @pytest.fixture
    def stress_game(self, pygame_init):
        """Create a high-load game state for stress testing."""
        from main import Game
        game = Game()
        # game_state is None until initialize_game() is called with a setup config
        setup_config = {
            'num_players': 4,
            'player_is_ai': [False, True, True, True],
            'player_ai_difficulty': [None, 'Normal', 'Normal', 'Normal'],
        }
        game.initialize_game(setup_config)
        game.game_state.phase = 'playing'
        self._populate_stress_state(game)
        return game

    def _populate_stress_state(self, game):
        """Create a high-load game state."""
        import random
        import map_data
        from game_state import MovementOrder

        # Get all territories
        territories = list(game.game_state.territory_owners.keys())

        # Distribute territories among 4 players
        for i, territory in enumerate(territories):
            player = i % 4
            game.game_state.territory_owners[territory] = player
            game.game_state.armies[territory] = 50
            game.game_state.armies_unmoved[territory] = 50

            # Initialize garrisons
            if territory not in game.game_state.territory_garrisons:
                game.game_state.territory_garrisons[territory] = {}
            game.game_state.territory_garrisons[territory][player] = {
                'unmoved': 50,
                'moved': 0
            }

        # Add movement orders (20 orders = late game activity)
        for i in range(20):
            from_t = territories[i % len(territories)]
            neighbors = map_data.get_neighbors(from_t)
            if neighbors:
                order = MovementOrder(
                    from_territory=from_t,
                    to_territory=neighbors[0],
                    army_count=10,
                    player=game.game_state.territory_owners[from_t]
                )
                game.game_state.movement_orders.append(order)

    def test_late_game_stress(self, stress_game):
        """Late game with many armies should maintain 30+ FPS."""
        fps = FPSMeasurement(sample_count=100)
        result = fps.run_benchmark(stress_game)

        print(f"\n=== Late Game Stress Test ===")
        print(f"  Average: {result['avg_fps']:.1f} FPS")
        print(f"  Min: {result['min_fps']:.1f} FPS")
        print(f"  Frame time: {result['avg_frame_ms']:.2f}ms avg")
        print(f"  99th percentile: {result['percentile_99']:.2f}ms")

        assert result['avg_fps'] >= 30, f"Stress FPS too low: {result['avg_fps']:.1f}"

    def test_movement_arrows_performance(self, stress_game):
        """Many movement orders should not tank FPS."""
        # The stress_game already has 20 movement orders
        order_count = len(stress_game.game_state.movement_orders)

        fps = FPSMeasurement(sample_count=60)
        result = fps.run_benchmark(stress_game)

        print(f"\n=== Movement Arrows ({order_count} orders) ===")
        print(f"  Average: {result['avg_fps']:.1f} FPS")
        print(f"  Frame time: {result['avg_frame_ms']:.2f}ms avg")

        assert result['avg_fps'] >= 40, f"Movement arrow FPS too low: {result['avg_fps']:.1f}"


class TestZoomPerformance:
    """
    Zoom/pan performance — the scenarios the original suite could not detect.

    These all drive the camera via before_frame, so the camera-keyed caches are
    invalidated every frame exactly as they are during real play.
    """

    @pytest.fixture
    def zoom_game(self, pygame_init):
        from main import Game
        game = Game()
        game.initialize_game({
            'num_players': 4,
            'player_is_ai': [False, True, True, True],
            'player_ai_difficulty': [None, 'Normal', 'Normal', 'Normal'],
        })
        game.game_state.phase = 'playing'
        populate_map(game, buildings_per_territory=2, armies=50)
        return game

    def test_static_fps_at_max_zoom(self, zoom_game):
        """Steady state at max zoom — isolates per-frame cost from rescale cost."""
        sync_camera(zoom_game, zoom=4.0)
        fps = FPSMeasurement(sample_count=60)
        result = record('static_max_zoom', fps.run_benchmark(zoom_game, warmup=5))
        report('Static FPS @ zoom 4.0', result)
        assert result['avg_fps'] >= 25, f"Max-zoom static FPS too low: {result['avg_fps']:.1f}"

    def test_pan_fps(self, zoom_game):
        """Continuous panning invalidates polygon/overlay caches every frame."""
        sync_camera(zoom_game, zoom=3.0)

        def before(i):
            zoom_game.camera.offset[0] += 0.7
            sync_camera(zoom_game, force_rescale=False)

        fps = FPSMeasurement(sample_count=60)
        result = record('pan_zoom3', fps.run_benchmark(zoom_game, before_frame=before, warmup=5))
        report('Panning @ zoom 3.0', result)
        assert result['avg_fps'] >= 20, f"Panning FPS too low: {result['avg_fps']:.1f}"

    def test_mouse_wheel_zoom_fps(self, zoom_game):
        """Mouse-wheel zoom at the real configured zoom speed (0.078)."""
        top_panel = getattr(zoom_game, 'TOP_PANEL_HEIGHT', 40)
        centre = (zoom_game.screen.get_width() // 2, zoom_game.screen.get_height() // 2)
        sync_camera(zoom_game, zoom=zoom_game.camera.min_zoom)
        direction = [1]

        def before(i):
            # Bounce between min and max zoom so we keep crossing zoom levels
            if zoom_game.camera.target_zoom >= zoom_game.camera.max_zoom - 1e-6:
                direction[0] = -1
            elif zoom_game.camera.target_zoom <= zoom_game.camera.min_zoom + 1e-6:
                direction[0] = 1
            zoom_game.camera.handle_zoom(direction[0], centre, 0.078, top_panel)
            # handle_zoom() now only sets a TARGET; update_zoom() eases toward it.
            # Without this the benchmark would render a static frame and report
            # inflated FPS.
            zoom_game.camera.update_zoom(1.0 / 60.0)
            sync_camera(zoom_game)

        fps = FPSMeasurement(sample_count=60)
        result = record('mouse_wheel_zoom', fps.run_benchmark(zoom_game, before_frame=before, warmup=5))
        report('Mouse-wheel zoom (speed 0.078)', result)
        assert result['avg_fps'] >= 15, f"Wheel-zoom FPS too low: {result['avg_fps']:.1f}"

    def test_zoom_sweep_fps(self, zoom_game):
        """
        The campaign-intro zoom: a real CameraAnimation sweeping min -> max zoom
        over 1.5s, exactly as tutorial_mission / campaign missions 2-7 do.
        """
        from tutorial_mission import CameraAnimation

        centre = next(iter(zoom_game.scaled_centers.values()))
        anim = CameraAnimation(
            zoom_game.camera,
            zoom_game.camera.min_zoom, zoom_game.camera.max_zoom,
            1.5, centre,
            zoom_game.screen.get_width(),
            getattr(zoom_game, 'MAP_HEIGHT', zoom_game.screen.get_height() - 240),
        )

        def before(i):
            anim.update(1.0 / 60.0)
            zoom_game.is_zoom_animating = anim.active
            sync_camera(zoom_game, force_rescale=False)

        fps = FPSMeasurement(sample_count=90)
        result = record('zoom_sweep', fps.run_benchmark(zoom_game, before_frame=before))
        report('Campaign-intro zoom sweep (1.65 -> 4.0)', result)
        assert result['avg_fps'] >= 12, f"Zoom sweep FPS too low: {result['avg_fps']:.1f}"


class TestProductionGlowPerformance:
    """
    ProductionGlowEffect rebuilds 16 pre-rendered sprite frames whenever the raw
    zoom float changes. With many producing buildings that is thousands of polygon
    draws in a single frame — the dominant cause of crowded-map zoom stutter.
    """

    @pytest.fixture
    def glow_game(self, pygame_init):
        from main import Game
        game = Game()
        game.initialize_game({
            'num_players': 4,
            'player_is_ai': [False, True, True, True],
            'player_ai_difficulty': [None, 'Normal', 'Normal', 'Normal'],
        })
        game.game_state.phase = 'playing'
        return game

    def test_static_fps_with_many_glows(self, glow_game):
        """Steady state with ~100 producing buildings (no zoom change)."""
        populate_map(glow_game, buildings_per_territory=2, producing=True, single_owner=0)
        n = glow_effect_count(glow_game)
        sync_camera(glow_game, zoom=glow_game.camera.min_zoom)

        def before(i):
            glow_game.map_renderer.update_production_glow_effects(1.0 / 60.0)

        fps = FPSMeasurement(sample_count=60)
        result = record('glow_static', fps.run_benchmark(glow_game, before_frame=before, warmup=5),
                        glow_effects=n)
        report(f'Static FPS with {n} production glows', result)
        assert result['avg_fps'] >= 25, f"Glow static FPS too low: {result['avg_fps']:.1f}"

    def test_zoom_with_many_glows(self, glow_game):
        """
        THE crowded-map regression test: zoom while many buildings are producing.

        Baseline before optimization measured 113-167ms per frame (6-9 FPS) because
        every effect rebuilt its sprite cache on every distinct zoom float.
        """
        populate_map(glow_game, buildings_per_territory=2, producing=True, single_owner=0)
        n = glow_effect_count(glow_game)
        top_panel = getattr(glow_game, 'TOP_PANEL_HEIGHT', 40)
        centre = (glow_game.screen.get_width() // 2, glow_game.screen.get_height() // 2)
        sync_camera(glow_game, zoom=glow_game.camera.min_zoom)
        direction = [1]

        def before(i):
            if glow_game.camera.target_zoom >= glow_game.camera.max_zoom - 1e-6:
                direction[0] = -1
            elif glow_game.camera.target_zoom <= glow_game.camera.min_zoom + 1e-6:
                direction[0] = 1
            glow_game.camera.handle_zoom(direction[0], centre, 0.078, top_panel)
            glow_game.camera.update_zoom(1.0 / 60.0)
            sync_camera(glow_game)
            glow_game.map_renderer.update_production_glow_effects(1.0 / 60.0)

        fps = FPSMeasurement(sample_count=60)
        result = record('glow_zoom', fps.run_benchmark(glow_game, before_frame=before, warmup=3),
                        glow_effects=n)
        report(f'Zooming with {n} production glows', result,
               [f'(pre-optimization baseline: ~113-167ms per frame)'])
        assert result['worst_frame_ms'] < 100, (
            f"Zoom-with-glows worst frame too slow: {result['worst_frame_ms']:.1f}ms")


class TestCrowdedMapPerformance:
    """
    Documents how frame cost scales with on-map entity count, so a future
    regression in plot/banner rendering is visible rather than anecdotal.
    """

    @pytest.fixture
    def crowd_game(self, pygame_init):
        from main import Game
        game = Game()
        game.initialize_game({
            'num_players': 4,
            'player_is_ai': [False, True, True, True],
            'player_ai_difficulty': [None, 'Normal', 'Normal', 'Normal'],
        })
        game.game_state.phase = 'playing'
        return game

    @pytest.mark.parametrize('buildings', [0, 2, 4])
    def test_building_density(self, crowd_game, buildings):
        """Frame cost vs building count (measured: near-flat, cost is elsewhere)."""
        populate_map(crowd_game, buildings_per_territory=buildings)
        total = sum(len(b) for b in crowd_game.game_state.buildings.values())
        fps = FPSMeasurement(sample_count=50)
        result = record(f'density_buildings_{buildings}',
                        fps.run_benchmark(crowd_game, warmup=5), buildings=total)
        report(f'Building density: {total} buildings', result)
        assert result['avg_fps'] >= 25, f"Density {total} FPS too low: {result['avg_fps']:.1f}"

    @pytest.mark.parametrize('garrisons', [1, 3])
    def test_banner_density(self, crowd_game, garrisons):
        """Frame cost vs banner count."""
        populate_map(crowd_game, buildings_per_territory=2,
                     garrisons_per_territory=garrisons)
        total = sum(len(g) for g in crowd_game.game_state.territory_garrisons.values())
        fps = FPSMeasurement(sample_count=50)
        result = record(f'density_banners_{garrisons}',
                        fps.run_benchmark(crowd_game, warmup=5), banners=total)
        report(f'Banner density: {total} banners', result)
        assert result['avg_fps'] >= 25, f"Banners {total} FPS too low: {result['avg_fps']:.1f}"


class TestMapEastEdgePerformance:
    """
    The zoom range in which the map is narrower than the window.

    At min zoom (1.65) a 16:9 map image ends ~175px before the window's right edge
    (1600x900: at x=1427). The right sidebar used to hide that strip; once it can
    collapse, the strip is filled by the generated east extension
    (rendering/map_extension.py). These scenarios measure that the extension costs
    one blit while static and stays cheap while zoom crosses the gap range.
    """

    @pytest.fixture
    def edge_game(self, pygame_init):
        from main import Game
        game = Game()
        game.initialize_game({
            'num_players': 4,
            'player_is_ai': [False, True, True, True],
            'player_ai_difficulty': [None, 'Normal', 'Normal', 'Normal'],
        })
        game.game_state.phase = 'playing'
        populate_map(game, buildings_per_territory=2, armies=50)
        return game

    def test_static_fps_at_min_zoom(self, edge_game):
        """Fully zoomed out, camera at the map's left edge: the gap is widest."""
        sync_camera(edge_game, zoom=edge_game.camera.min_zoom, offset=(0.0, 0.0))
        fps = FPSMeasurement(sample_count=60)
        result = record('edge_static_min_zoom', fps.run_benchmark(edge_game, warmup=5))
        report('Static FPS @ min zoom (east gap visible)', result)
        assert result['avg_fps'] >= 25, f"Min-zoom static FPS too low: {result['avg_fps']:.1f}"

    def test_zoom_sweep_across_gap(self, edge_game):
        """Bounce zoom 1.65 <-> 1.9: the gap shrinks to zero and reopens every frame."""
        lo = edge_game.camera.min_zoom
        hi = min(1.9, edge_game.camera.max_zoom)
        steps = 20

        def before(i):
            # Triangle wave so every frame lands on a new zoom level (no cache hits)
            phase = i % (2 * steps)
            t = phase / steps if phase <= steps else (2 * steps - phase) / steps
            sync_camera(edge_game, zoom=lo + (hi - lo) * t, offset=(0.0, 0.0),
                        force_rescale=False)

        fps = FPSMeasurement(sample_count=60)
        result = record('edge_zoom_sweep', fps.run_benchmark(edge_game, before_frame=before, warmup=3))
        report(f'Zoom sweep across the east gap ({lo:.2f} <-> {hi:.2f})', result)
        assert result['worst_frame_ms'] < 100, (
            f"East-gap zoom worst frame too slow: {result['worst_frame_ms']:.1f}ms")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
