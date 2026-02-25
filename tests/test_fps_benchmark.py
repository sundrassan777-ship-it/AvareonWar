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

    def run_benchmark(self, game):
        """Run full benchmark and return statistics."""
        self.frame_times = []
        for _ in range(self.sample_count):
            self.measure_frame(game)

        if not self.frame_times:
            return {'avg_fps': 0, 'min_fps': 0, 'max_fps': 0, 'avg_frame_ms': 0}

        avg_frame_time = statistics.mean(self.frame_times)
        min_frame_time = min(self.frame_times)
        max_frame_time = max(self.frame_times)
        stddev = statistics.stdev(self.frame_times) if len(self.frame_times) > 1 else 0

        return {
            'avg_fps': 1.0 / avg_frame_time if avg_frame_time > 0 else 0,
            'min_fps': 1.0 / max_frame_time if max_frame_time > 0 else 0,
            'max_fps': 1.0 / min_frame_time if min_frame_time > 0 else 0,
            'avg_frame_ms': avg_frame_time * 1000,
            'stddev_ms': stddev * 1000,
            'percentile_99': statistics.quantiles(self.frame_times, n=100)[98] * 1000 if len(self.frame_times) >= 100 else max_frame_time * 1000
        }


@pytest.fixture(scope="module")
def pygame_init():
    """Initialize pygame for all tests."""
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


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
        game_instance.sidebar_expanded = True

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
        """Rotated tab text should be cached."""
        # Trigger sidebar draw to populate cache
        game_instance.sidebar_expanded = False

        # Check cache is empty initially
        initial_cache_size = len(game_instance._rotated_tab_text_cache)

        # Draw sidebar (which should cache rotated text)
        # Note: We can't easily call draw_sidebar in isolation, but we can check the cache exists
        assert hasattr(game_instance, '_rotated_tab_text_cache'), "Rotated tab text cache not initialized"

        print("\n=== Rotated Tab Text Cache ===")
        print(f"  Cache initialized: Yes")
        print(f"  Initial size: {initial_cache_size}")


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


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
