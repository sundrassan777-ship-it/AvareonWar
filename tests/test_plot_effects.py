# -*- coding: utf-8 -*-
"""
Plot effects (2026-10-26): production light rays and construction dust.

Producing Barracks / Keeps / Castles show soft rays of light turning behind the
plot (ui/effects/production_glow_effect.py, styled in ui/effects/plot_fx_style.py).
They replaced an 8-ray "star" whose 16 baked frames were 22.5 deg apart: with 8
rays repeating every 45 deg it only ever showed TWO poses, so it "rotated" by
flipping between them every ~2.6 s, and it was sized by camera_zoom while the
plots use ui_scale.

Plots under construction, and Keeps being upgraded to Castles (gold glints),
show dust (ui/effects/construction_dust_effect.py). It is stateless: drawn from
the shared clock and the plot's phase wherever game_state says, nothing synced.

Unit tests cover the shared renderers and the per-plot effect; integration tests
drive MapRenderer with a real Game: who gets which effect, where it is drawn, how
big, and when the clock moves.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from ui.effects.plot_fx_style import (RAY_STYLE, PLOT_FX_STYLES, get_plot_fx_style,  # noqa: E402
                                      plot_phase)
from ui.effects.production_glow_effect import (ProductionRays, ProductionGlowEffect,  # noqa: E402
                                               light_colour)
from ui.effects.construction_dust_effect import (ConstructionDust, VARIANT_BUILD,  # noqa: E402
                                                 VARIANT_UPGRADE)

RED = (255, 100, 100)
BLUE = (100, 150, 255)


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield


def _pixels(surface):
    return pygame.image.tostring(surface, 'RGB')


# ========================================
# ProductionRays (shared renderer)
# ========================================

class TestProductionRays:

    def test_rays_turn_smoothly(self):
        """Regression for the old 2-pose star: the rays change pose many times a second,
        with no long gap between changes (frames at the game's 80 FPS cap)."""
        rays = ProductionRays()
        frame_dt = 1.0 / 80.0
        poses, last, changes = set(), None, []
        for i in range(40):   # half a second
            surface, _ = rays.layer_frames(24, RED, 3.0 + i * frame_dt, 0.0)[0]
            image = _pixels(surface)
            poses.add(image)
            if image != last:
                changes.append(i)
                last = image
        assert len(poses) >= 10, f'only {len(poses)} poses in 0.5 s'
        gaps = [b - a for a, b in zip(changes, changes[1:])]
        assert max(gaps) <= 5, f'the rays stood still for {max(gaps)} frames'

    def test_each_step_moves_the_light_less_than_half_a_pixel(self):
        """The angle step keeps every pose change sub-pixel where the rays are bright
        (1.5-2 deg steps visibly ticked, 2026-10-26)."""
        bright_radius = 1.5 * 24   # px from the centre at the largest plot size
        assert math.radians(RAY_STYLE['angle_step']) * bright_radius < 0.5

    def test_layers_turn_in_opposite_directions(self):
        speeds = [layer['speed'] for layer in RAY_STYLE['layers']]
        assert min(speeds) < 0 < max(speeds)

    def test_size_follows_the_plot_radius(self):
        """Sized by the plot radius (16..24 px), which is what the plot itself uses."""
        rays = ProductionRays()
        small = [half for _, half in rays.layer_frames(16, RED, 0.0, 0.0)]
        large = [half for _, half in rays.layer_frames(24, RED, 0.0, 0.0)]
        for s, l in zip(small, large):
            assert l / s == pytest.approx(24 / 16, rel=0.12)
        # Light reaches well past the plot rim at the smallest size (the old star
        # poked out ~4 px at min zoom)
        assert small[0] >= 16 * 2

    def test_odd_radii_share_the_even_frames(self):
        """Even radii only: 5 sets over the zoom range, at most 1 px off."""
        rays = ProductionRays()
        a = rays.layer_frames(17, RED, 0.0, 0.0)
        b = rays.layer_frames(18, RED, 0.0, 0.0)
        assert [s for s, _ in a] == [s for s, _ in b]

    def test_frames_add_no_light_outside_the_rays(self):
        """Opaque black frames blitted with BLEND_RGB_ADD: black corners add nothing."""
        rays = ProductionRays()
        for surface, half in rays.layer_frames(24, RED, 1.234, 0.3):
            assert surface.get_flags() & pygame.SRCALPHA == 0
            assert tuple(surface.get_at((0, 0)))[:3] == (0, 0, 0)
            assert tuple(surface.get_at((2 * half - 1, 2 * half - 1)))[:3] == (0, 0, 0)
            # ...and some light just outside the plot rim
            ring = [surface.get_at((half + int(26 * math.cos(a)), half + int(26 * math.sin(a))))
                    for a in [i * math.pi / 18 for i in range(36)]]
            assert any(sum(tuple(p)[:3]) > 30 for p in ring)

    def test_frame_sizes_are_even(self):
        """Even sizes keep rotozoom's output centred: odd ones wobble by half a pixel."""
        rays = ProductionRays()
        for radius in range(16, 25):
            for surface, half in rays.layer_frames(radius, RED, 0.77, 0.0):
                assert surface.get_width() == surface.get_height() == 2 * half

    def test_plots_in_one_group_share_one_frame(self):
        """One frame per (size, colour, group, layer), shared by every plot in it."""
        rays = ProductionRays()
        groups = RAY_STYLE['phase_groups']
        first = rays.layer_frames(24, RED, 2.0, 0.01)
        rotations = rays.rotations
        same_group = rays.layer_frames(24, RED, 2.0, 0.99 / groups)
        assert [s for s, _ in same_group] == [s for s, _ in first]
        assert rays.rotations == rotations   # nothing re-rotated for the second plot
        if groups > 1:
            other_group = rays.layer_frames(24, RED, 2.0, 1.0 / groups + 0.01)
            assert [s for s, _ in other_group] != [s for s, _ in first]

    def test_colours_get_their_own_frames(self):
        rays = ProductionRays()
        red = rays.layer_frames(24, RED, 0.0, 0.0)[0][0]
        blue = rays.layer_frames(24, BLUE, 0.0, 0.0)[0][0]
        assert red is not blue
        assert _pixels(red) != _pixels(blue)

    def test_frame_sets_are_bounded(self):
        rays = ProductionRays()
        for i in range(ProductionRays.MAX_SETS + 6):
            rays.layer_frames(24, (i * 10 % 256, 100, 100), 0.0, 0.0)
        assert len(rays._sets) <= ProductionRays.MAX_SETS

    def test_reach_covers_every_frame(self):
        rays = ProductionRays()
        for radius in (16, 20, 24):
            assert rays.reach(radius) >= max(half for _, half in rays.layer_frames(radius, RED, 0.0, 0.0))

    def test_prewarm_builds_the_bases_up_front(self):
        rays = ProductionRays()
        rays.prewarm(range(16, 25))
        assert sorted(rays._grey_bases) == [16, 18, 20, 22, 24]


class TestStyleAndHelpers:

    def test_light_is_the_player_colour_toward_warm_white(self):
        blue = light_colour(BLUE)
        assert blue[2] > blue[0]                       # still blue...
        assert blue[0] > BLUE[0] and blue[1] > BLUE[1]  # ...but lighter

    def test_plot_phase_is_stable_and_spread(self):
        """crc32, not hash(): the same in every run (str hashes are salted per process)."""
        assert plot_phase('Aelatania', 0) == plot_phase('Aelatania', 0)
        phases = {plot_phase(t, i) for t in ('Aelatania', 'Lunedale', 'Sordia') for i in range(3)}
        assert len(phases) == 9
        assert all(0.0 <= p < 1.0 for p in phases)

    def test_both_map_looks_have_a_style(self):
        assert set(PLOT_FX_STYLES) == {'2d', '3d'}
        assert get_plot_fx_style('something else') is PLOT_FX_STYLES['2d']


class TestProductionGlowEffect:

    def test_holds_the_plot_not_a_position(self):
        effect = ProductionGlowEffect('Aelatania', 1, RED)
        assert (effect.territory, effect.plot_index) == ('Aelatania', 1)
        assert effect.phase == plot_phase('Aelatania', 1)

    def test_update_color_switches_frames(self):
        rays = ProductionRays()
        screen = pygame.Surface((200, 200))
        effect = ProductionGlowEffect('Aelatania', 1, RED)
        effect.render(screen, 100, 100, 20, 0.0, rays)
        effect.update_color(BLUE)
        screen.fill((0, 0, 0))
        effect.render(screen, 100, 100, 20, 0.0, rays)
        assert (20, BLUE) in rays._sets
        r, g, b = tuple(screen.get_at((100 + 22, 100)))[:3]
        assert b > r   # blue light now

    def test_render_adds_light_around_the_plot(self):
        rays = ProductionRays()
        screen = pygame.Surface((200, 200))
        screen.fill((0, 0, 0))
        ProductionGlowEffect('Aelatania', 1, RED).render(screen, 100, 100, 20, 0.5, rays)
        assert sum(tuple(screen.get_at((100 + 22, 100)))[:3]) > 0   # halo just past the rim
        assert tuple(screen.get_at((0, 0)))[:3] == (0, 0, 0)         # nothing far away


# ========================================
# ConstructionDust (shared renderer)
# ========================================

def _dust_frame(dust, clock, phase=0.3, variant=VARIANT_BUILD, radius=20, frames=3):
    """Dust of one plot at (100, 100) on black, after letting the sprite budget fill."""
    screen = pygame.Surface((200, 200))
    for _ in range(frames):
        screen.fill((0, 0, 0))
        dust.begin_frame()
        dust.draw_back(screen, 100, 100, radius, clock, phase, variant)
        dust.draw_front(screen, 100, 100, radius, clock, phase, variant)
    return screen


def _is_gold(pixel):
    """Gold glint colours (255, 204, 60) / (255, 232, 130) over black: bright, green
    close to red, blue well below. Sienna dust (green/red ~0.65), cream motes (blue
    ~ red), cream blended over sienna (red/blue < 1.7) and the dark debris chips
    (red <= 108) don't match."""
    r, g, b = tuple(pixel)[:3]
    return r > 110 and g >= 0.78 * r and r >= 1.7 * b


class TestConstructionDust:

    def test_same_moment_same_dust(self):
        """Stateless and deterministic: (clock, phase) fully decide the frame - also
        across instances (fixed particle tables), so every client draws the same."""
        a = _pixels(_dust_frame(ConstructionDust(), 4.2))
        b = _pixels(_dust_frame(ConstructionDust(), 4.2))
        assert a == b

    def test_it_moves(self):
        dust = ConstructionDust()
        assert _pixels(_dust_frame(dust, 4.2)) != _pixels(_dust_frame(dust, 4.3))

    def test_neighbouring_plots_differ(self):
        dust = ConstructionDust()
        assert _pixels(_dust_frame(dust, 4.2, phase=0.1)) != _pixels(_dust_frame(dust, 4.2, phase=0.6))

    def test_dust_stays_around_the_plot(self):
        dust = ConstructionDust()
        radius = 20
        for clock in (0.5, 1.7, 3.1, 6.4):
            screen = _dust_frame(dust, clock, radius=radius)
            drawn = [(x, y) for x in range(0, 200, 2) for y in range(0, 200, 2)
                     if sum(tuple(screen.get_at((x, y)))[:3]) > 0]
            assert drawn, f'no dust at clock {clock}'
            assert all(math.hypot(x - 100, y - 100) < 4 * radius for x, y in drawn)

    def test_upgrade_dust_has_gold_glints(self):
        """Keep -> Castle upgrades: gold glints among the dust; plain construction has none."""
        dust = ConstructionDust()

        def gold_pixels(variant):
            count = 0
            for i in range(12):
                screen = _dust_frame(dust, 2.0 + i * 0.37, variant=variant)
                count += sum(1 for x in range(60, 140) for y in range(40, 160)
                             if _is_gold(screen.get_at((x, y))))
            return count

        assert gold_pixels(VARIANT_UPGRADE) > 0
        assert gold_pixels(VARIANT_BUILD) == 0

    def test_dust_scales_with_the_plot(self):
        dust = ConstructionDust()

        def extent(radius):
            far = 0.0
            for i in range(10):
                screen = _dust_frame(dust, 1.0 + i * 0.41, radius=radius)
                for x in range(0, 200, 2):
                    for y in range(0, 200, 2):
                        if sum(tuple(screen.get_at((x, y)))[:3]) > 0:
                            far = max(far, math.hypot(x - 100, y - 100))
            return far

        assert extent(24) > extent(16) * 1.2

    def test_sprite_building_is_capped_per_frame(self):
        """At most BUILDS_PER_FRAME new sprites a frame (a new zoom never hitches);
        particles whose sprite isn't ready just wait a frame."""
        dust = ConstructionDust()
        screen = pygame.Surface((200, 200))
        dust.begin_frame()
        for i in range(40):   # many plots, same frame
            dust.draw_back(screen, 100, 100, 16 + i % 9, 1.0, i / 40.0)
            dust.draw_front(screen, 100, 100, 16 + i % 9, 1.0, i / 40.0)
        assert dust.sprites_built <= ConstructionDust.BUILDS_PER_FRAME

    def test_no_new_sprites_once_warm(self):
        """After a warm-up the sprite cache covers what the dust needs: nothing is
        allocated per frame any more (the rendering rule in CLAUDE.md)."""
        dust = ConstructionDust()
        for i in range(800):   # 10 s at 80 FPS, one plot size
            _dust_frame(dust, i / 80.0, radius=20, frames=1)
        built = dust.sprites_built
        for i in range(800, 960):
            _dust_frame(dust, i / 80.0, radius=20, frames=1)
        assert dust.sprites_built - built <= 2

    def test_sprite_cache_is_bounded(self):
        dust = ConstructionDust()
        dust.BUILDS_PER_FRAME = 10_000
        for radius in range(16, 25):
            for i in range(60):
                _dust_frame(dust, i * 0.13, phase=i / 60.0, radius=radius, frames=1)
        assert len(dust._sprites) <= ConstructionDust.MAX_SPRITES


# ========================================
# MapRenderer integration (real Game)
# ========================================

@pytest.fixture(scope='module')
def game(display):
    from main import Game
    g = Game()
    g.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 'Normal'],
    })
    g.game_state.phase = 'playing'
    return g


def _visible_plot(game):
    """A (territory, plot_index, x, y) whose plot is well inside the screen."""
    width, height = game.screen.get_size()
    for territory, plots in game.scaled_plots.items():
        for index, pos in enumerate(plots):
            x, y = game.world_to_screen(pos)
            if 150 < x < width - 150 and 150 < y < height - 150:
                return territory, index, int(x), int(y)
    pytest.skip('no plot on screen at the starting camera')


def _set_production(game, territory, plot_index, owner):
    """Make (territory, plot_index) a Barracks of `owner` training one unit, and sync."""
    gs = game.game_state
    gs.territory_owners[territory] = owner
    gs.buildings[territory] = {plot_index: 'Barracks'}
    gs.training_queue[territory] = {plot_index: [('Swordsman', 2, 30)]}
    gs._training_version += 1
    game.map_renderer.sync_production_glow_effects()


@pytest.fixture
def plot(game):
    """A visible plot, with everything this test changes put back afterwards."""
    gs = game.game_state
    territory, index, x, y = _visible_plot(game)
    stores = (gs.buildings, gs.training_queue, gs.under_construction,
              gs.castle_upgrades_in_progress)
    saved = (gs.territory_owners.get(territory), [store.get(territory) for store in stores],
             gs.phase, list(game.scaled_plots[territory]))
    yield territory, index, x, y
    owner, values, phase, scaled = saved
    gs.territory_owners[territory] = owner
    for store, value in zip(stores, values):
        if value is None:
            store.pop(territory, None)
        else:
            store[territory] = value
    gs.phase = phase
    game.scaled_plots[territory] = scaled
    game.map_renderer.cached_screen_plots = {}
    gs._training_version += 1
    game.map_renderer.sync_production_glow_effects()


def _render_rays_on_black(game):
    game.screen.fill((0, 0, 0))
    game.map_renderer.render_production_glow_effects()


def _lit(game, x, y):
    return sum(tuple(game.screen.get_at((x, y)))[:3]) > 0


class TestMapRendererRays:

    def test_own_production_gets_rays(self, game, plot):
        territory, index, x, y = plot
        _set_production(game, territory, index, owner=0)
        assert (territory, index) in game.map_renderer.production_glow_effects
        _render_rays_on_black(game)
        radius = game.map_renderer._plot_radius()
        assert _lit(game, x + radius + 2, y)          # halo just past the rim
        assert not _lit(game, x + 6 * radius, y)      # nothing far away

    def test_enemy_production_gets_no_rays(self, game, plot):
        """Training is private: only the viewer's own and allied buildings show rays."""
        territory, index, x, y = plot
        _set_production(game, territory, index, owner=1)
        assert (territory, index) not in game.map_renderer.production_glow_effects

    def test_rays_follow_the_plot_after_a_rescale(self, game, plot):
        """apply_display_settings() rescales scaled_plots in place; the rays must move
        with the plot (they used to keep the world position they were created at)."""
        territory, index, x, y = plot
        _set_production(game, territory, index, owner=0)
        wx, wy = game.scaled_plots[territory][index]
        shift = 120 / game.camera_zoom   # 120 px on screen
        moved = list(game.scaled_plots[territory])
        moved[index] = (wx + shift, wy)
        game.scaled_plots[territory] = moved
        _render_rays_on_black(game)
        radius = game.map_renderer._plot_radius()
        assert _lit(game, x + 120 + radius + 2, y)
        assert not _lit(game, x - radius - 2, y)

    def test_rays_are_sized_by_the_plot_radius(self, game, plot, monkeypatch):
        territory, index, x, y = plot
        _set_production(game, territory, index, owner=0)
        renderer = game.map_renderer
        for ui_scale, expected in ((1.0, 16), (1.5, 24)):
            monkeypatch.setattr(game, 'get_ui_scale_factor', lambda s=ui_scale: s)
            assert renderer._plot_radius() == expected
            _render_rays_on_black(game)
            assert any(key[0] == expected for key in renderer.production_rays._sets)

    def test_no_rays_outside_the_playing_phase(self, game, plot):
        """Plots are only drawn while playing, so no rays around plots that aren't there."""
        territory, index, x, y = plot
        _set_production(game, territory, index, owner=0)
        game.game_state.phase = 'ended'
        _render_rays_on_black(game)
        radius = game.map_renderer._plot_radius()
        assert not _lit(game, x + radius + 2, y)

    def test_the_clock_moves_only_through_update(self, game, plot):
        """update_plot_effects() runs in the main loop's update section, which is
        skipped while paused: no update, no motion."""
        territory, index, x, y = plot
        _set_production(game, territory, index, owner=0)
        renderer = game.map_renderer
        start = renderer._plot_fx_clock
        _render_rays_on_black(game)
        first = _pixels(game.screen)
        _render_rays_on_black(game)
        assert renderer._plot_fx_clock == start
        assert _pixels(game.screen) == first
        renderer.update_plot_effects(0.5)
        assert renderer._plot_fx_clock == pytest.approx(start + 0.5)
        _render_rays_on_black(game)
        assert _pixels(game.screen) != first

    def test_display_change_rebuilds_the_ray_frames(self, game):
        """Frames are converted to the display format; rebuild_scale_caches() (called on
        every display change) makes fresh ones."""
        before = game.map_renderer.production_rays
        game.map_renderer.rebuild_scale_caches()
        assert game.map_renderer.production_rays is not before
        assert sorted(game.map_renderer.production_rays._grey_bases) == [16, 18, 20, 22, 24]


def _plot_region(game, x, y):
    """The plot's surroundings after drawing all plots on black."""
    game.screen.fill((0, 0, 0))
    game.map_renderer.draw_plots()
    radius = game.map_renderer._plot_radius()
    rect = pygame.Rect(0, 0, radius * 6, radius * 6)
    rect.center = (x, y)
    return game.screen.subsurface(rect.clip(game.screen.get_rect())).copy()


def _animated(game, x, y):
    """Does the plot's surroundings change as the effect clock moves?"""
    renderer = game.map_renderer
    first = _pixels(_plot_region(game, x, y))
    renderer.update_plot_effects(0.7)
    second = _pixels(_plot_region(game, x, y))
    return first != second


class TestMapRendererDust:

    def _set(self, game, territory, plot_index, owner, building=None, constructing=None,
             upgrading=False):
        gs = game.game_state
        gs.territory_owners[territory] = owner
        gs.buildings[territory] = {plot_index: building} if building else {}
        gs.training_queue.pop(territory, None)
        gs.under_construction.pop(territory, None)
        gs.castle_upgrades_in_progress.pop(territory, None)
        if constructing:
            gs.under_construction[territory] = {plot_index: (constructing, 1, 50)}
        if upgrading:
            gs.castle_upgrades_in_progress[territory] = {plot_index: 2}
        gs._training_version += 1
        game.map_renderer.sync_production_glow_effects()

    def test_construction_has_dust(self, game, plot):
        territory, index, x, y = plot
        self._set(game, territory, index, owner=0, constructing='Farm')
        assert _animated(game, x, y)

    def test_enemy_construction_has_dust_too(self, game, plot):
        """Construction is public (the construction disc already shows it to everyone)."""
        territory, index, x, y = plot
        self._set(game, territory, index, owner=1, constructing='Barracks')
        assert _animated(game, x, y)

    def test_finished_buildings_are_still(self, game, plot):
        territory, index, x, y = plot
        self._set(game, territory, index, owner=0, building='Farm')
        assert not _animated(game, x, y)

    def test_upgrading_keep_has_gold_dust(self, game, plot):
        """It used to show nothing on the map until the Castle's completion burst."""
        territory, index, x, y = plot
        self._set(game, territory, index, owner=0, building='Keep', upgrading=True)
        assert _animated(game, x, y)
        gold = 0
        for _ in range(12):
            game.map_renderer.update_plot_effects(0.37)
            region = _plot_region(game, x, y)
            w, h = region.get_size()
            gold += sum(1 for px in range(0, w, 2) for py in range(0, h, 2)
                        if _is_gold(region.get_at((px, py))))
        assert gold > 0

    def test_keep_not_upgrading_is_still(self, game, plot):
        territory, index, x, y = plot
        self._set(game, territory, index, owner=0, building='Keep')
        assert not _animated(game, x, y)

    def test_dust_stands_still_without_update(self, game, plot):
        """No update_plot_effects() (the game is paused) -> the dust holds still."""
        territory, index, x, y = plot
        self._set(game, territory, index, owner=0, constructing='Farm')
        _plot_region(game, x, y)   # let the sprite budget build what this moment needs
        first = _pixels(_plot_region(game, x, y))
        assert _pixels(_plot_region(game, x, y)) == first

    def test_display_change_rebuilds_the_dust(self, game):
        before = game.map_renderer.construction_dust
        game.map_renderer.rebuild_scale_caches()
        assert game.map_renderer.construction_dust is not before
