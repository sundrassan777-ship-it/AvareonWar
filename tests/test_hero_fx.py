# -*- coding: utf-8 -*-
"""
Hero ability effects as light (hero ability FX pass, 2026-10).

The light kit (ui/effects/light_fx.py): glow sprites, tint sprites, the soft
ring, the territory raster and border bead chains. The effects
(ui/effects/hero_fx_effect.py): ability cue timelines and the passive auras,
styled in ui/effects/hero_fx_style.py.

Unit tests use small synthetic "maps" of square territories, so they need no
Game; the game integration is tested further down once it exists.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from ui.effects import light_fx  # noqa: E402
from ui.effects.light_fx import (GlowSprites, TintSprites, SoftRing, TerritoryRaster,  # noqa: E402
                                 bead_chain, smooth_outline)
from ui.effects.hero_fx_style import HERO_FX_STYLE, HERO_FX_STYLES, get_hero_fx_style  # noqa: E402
from ui.effects.hero_fx_effect import (HeroLight, HeroAbilityEffect, HeroAura, FxView,  # noqa: E402
                                       envelope, stable_seed)

GOLD = (255, 180, 30)

# Three 100 x 100 territories in a row: West | Mid | East, and one below Mid
SQUARES = {
    'West': [(0, 0), (100, 0), (100, 100), (0, 100)],
    'Mid': [(100, 0), (200, 0), (200, 100), (100, 100)],
    'East': [(200, 0), (300, 0), (300, 100), (200, 100)],
    'South': [(100, 100), (200, 100), (200, 200), (100, 200)],
}


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((400, 300))
    yield


@pytest.fixture
def light():
    """A HeroLight without the per-frame time budget: tests must not depend on speed."""
    light = HeroLight(SQUARES)
    light.glow._budget.ms = light.tint._budget.ms = 10 ** 6
    return light


def _view(screen=None, zoom=1.0, radius=16):
    screen = screen or pygame.Surface((400, 300))
    return FxView(screen, 0.0, 0.0, zoom, radius)


def _pixels(surface):
    return pygame.image.tostring(surface, 'RGB')


def _blank(size=(400, 300), colour=(0, 0, 0)):
    surface = pygame.Surface(size)
    surface.fill(colour)
    return surface


# ========================================
# Light kit
# ========================================

class TestGlowSprites:

    def test_additive_sprites_add_nothing_at_their_corners(self):
        glow = GlowSprites()
        glow._budget.ms = 10 ** 6
        for profile in ('mote', 'flare', 'bead'):
            sprite = glow.sprite(24, GOLD, GlowSprites.LEVELS, profile)
            assert sprite.get_flags() & pygame.SRCALPHA == 0
            assert tuple(sprite.get_at((0, 0)))[:3] == (0, 0, 0)
            assert sum(tuple(sprite.get_at((12, 12)))[:3]) > 200

    def test_brightness_levels_are_baked_in(self):
        glow = GlowSprites()
        glow._budget.ms = 10 ** 6
        dim = glow.sprite(24, GOLD, 3)
        bright = glow.sprite(24, GOLD, 12)
        assert sum(tuple(dim.get_at((12, 12)))[:3]) < sum(tuple(bright.get_at((12, 12)))[:3])
        assert dim.get_alpha() is None   # no set_alpha: stays on the fast blit path

    def test_build_budget_caps_new_sprites_per_frame(self):
        glow = GlowSprites()
        glow.begin_frame()
        built = [glow.sprite(8 + 2 * i, GOLD, 12) for i in range(100)]
        assert glow.sprites_built <= GlowSprites.BUILDS_PER_FRAME
        assert built.count(None) >= 100 - GlowSprites.BUILDS_PER_FRAME
        glow.begin_frame()
        assert glow.sprite(8, GOLD, 12) is not None   # cached ones always come back

    def test_build_budget_stops_after_its_time(self):
        glow = GlowSprites()
        glow._budget.ms = 0.0
        glow.begin_frame()
        assert glow.sprite(64, GOLD, 12) is not None   # the first build always fits...
        assert glow.sprite(66, GOLD, 12) is None       # ...then the time is spent

    def test_cache_is_bounded(self):
        glow = GlowSprites()
        glow.MAX_SPRITES = 50
        glow._budget.count = glow._budget.ms = 10 ** 6
        glow.begin_frame()
        for i in range(200):
            glow.sprite(4 + 2 * (i % 40), (i, 0, 0), 12)
        assert len(glow._sprites) <= 50

    def test_ladder_is_complete_or_none(self):
        glow = GlowSprites()
        glow._budget.ms = 10 ** 6
        glow.begin_frame()
        ladder = glow.ladder(16, GOLD)
        assert ladder is not None and ladder[0] is None and len(ladder) == GlowSprites.LEVELS + 1
        assert all(s is not None for s in ladder[1:])


class TestTintSprites:

    def test_alpha_is_baked_and_quantized(self):
        tint = TintSprites()
        sprite = tint.sprite(24, GOLD, 128)
        assert sprite.get_flags() & pygame.SRCALPHA
        centre = sprite.get_at((12, 12))
        assert 100 < centre.a < 150 and centre.a > sprite.get_at((1, 12)).a
        assert tint.sprite(24, GOLD, 5) is None   # below the first level: nothing to draw


class TestSoftRing:

    def test_ring_adds_light_on_its_radius_only(self):
        ring = SoftRing(0.16)
        screen = _blank()
        ring.draw(screen, 200, 150, 60, (100, 150, 255), 1.0)
        on = sum(tuple(screen.get_at((260, 150)))[:3])
        centre = sum(tuple(screen.get_at((200, 150)))[:3])
        assert on > 150 and centre == 0

    def test_brightness_scales_the_light(self):
        ring = SoftRing(0.16)
        full, half = _blank(), _blank()
        ring.draw(full, 200, 150, 60, (100, 150, 255), 1.0)
        ring.draw(half, 200, 150, 60, (100, 150, 255), 0.5)
        assert sum(tuple(half.get_at((260, 150)))[:3]) < sum(tuple(full.get_at((260, 150)))[:3])

    def test_tint_ring_is_normal_blend(self):
        ring = SoftRing(0.16)
        screen = _blank(colour=(200, 200, 200))
        ring.draw_tint(screen, 200, 150, 60, (0, 0, 255), 200)
        r, g, b = tuple(screen.get_at((260, 150)))[:3]
        assert b > r and r < 200   # coloured toward blue, not lightened


class TestTerritoryRaster:

    def test_lookup(self):
        raster = TerritoryRaster(SQUARES)
        assert raster.at(50, 50) == 'West'
        assert raster.at(150, 50) == 'Mid'
        assert raster.at(150, 150) == 'South'
        assert raster.at(50, 150) is None
        assert raster.at(-5, 10) is None and raster.at(10_000, 10) is None


class TestBeadChain:

    @pytest.mark.parametrize('square', [
        [(0, 0), (100, 0), (100, 100), (0, 100)],     # clockwise on screen (y down)
        [(0, 0), (0, 100), (100, 100), (100, 0)],     # anticlockwise
    ])
    def test_inset_moves_inside_and_normals_point_out(self, square):
        chain = bead_chain(square, 2.0, inset=10.0)
        xs = [c[0] for c in chain]
        ys = [c[1] for c in chain]
        assert min(xs) > 5 and max(xs) < 95 and min(ys) > 5 and max(ys) < 95
        # Middle of the top edge: outward is up (-y)
        top = min(chain, key=lambda c: abs(c[0] - 50) + c[1])
        assert top[4] < -0.9

    def test_even_spacing(self):
        chain = bead_chain([(0, 0), (100, 0), (100, 100), (0, 100)], 2.0)
        steps = [chain[i + 1][2] - chain[i][2] for i in range(len(chain) - 1)]
        assert max(steps) - min(steps) < 1e-6

    def test_pixel_staircase_is_smoothed_away(self):
        """A rounded diagonal (a staircase of 1 px steps) measures as a diagonal, not
        as the staircase (which is 41% longer and bunches beads up)."""
        stairs = []
        for i in range(60):
            stairs += [(i, i), (i + 1, i)]
        stairs += [(60, 60), (0, 60)]
        smoothed = smooth_outline(stairs)
        length = sum(((smoothed[i][0] - smoothed[i - 1][0]) ** 2
                      + (smoothed[i][1] - smoothed[i - 1][1]) ** 2) ** 0.5 for i in range(len(smoothed)))
        diagonal_triangle = 60 * 2 ** 0.5 + 60 + 60
        assert length < diagonal_triangle * 1.08


# ========================================
# HeroLight
# ========================================

class TestHeroLight:

    def test_outline_drops_shared_borders(self, light):
        outline = light.outline(['West', 'Mid'])
        # No bead on the shared edge x = 100 (between y 10 and 90)
        for territory, _, beads in outline.parts:
            assert not any(abs(x - 100) < 3 and 10 < y < 90 for x, y, *_ in beads)
        # ...but the borders with unlit territories are there
        assert any(abs(x - 200) < 3 for _, _, beads in outline.parts for x, y, *_ in beads)

    def test_outline_is_cached_per_set(self, light):
        assert light.outline(['West', 'Mid']) is light.outline(['Mid', 'West'])
        assert light.outline(['West']) is not light.outline(['West', 'Mid'])

    def test_spawn_points_stay_inside_while_rising(self, light):
        raster = light.raster()
        points = light.spawn_points('South', 8.0)
        assert len(points) == HERO_FX_STYLE['kit']['spawn_points']
        for x, y in points:
            assert raster.at(x, y) == 'South' and raster.at(x, y - 8.0) == 'South'
        assert light.spawn_points('South', 8.0) is points   # picked once

    def test_points_inside_are_spread_and_deterministic(self, light):
        a = light.points_inside('Mid', 8, seed=7)
        b = light.points_inside('Mid', 8, seed=7)
        assert a == b and len(a) == 8
        assert all(light.raster().at(x, y) == 'Mid' for x, y in a)

    def test_bead_positions_are_cached_until_the_camera_moves(self, light):
        outline = light.outline(['West'])
        view = _view()
        first = light.bead_positions(view, outline, 10, 0.5, 0.4)
        assert light.bead_positions(view, outline, 10, 0.5, 0.4) is first
        moved = FxView(view.screen, 5.0, 0.0, 1.0, 16)
        assert light.bead_positions(moved, outline, 10, 0.5, 0.4) is not first

    def test_rays_fade_with_brightness(self, light):
        full, faint = _blank(), _blank()
        light.draw_rays(_view(full), 200, 150, GOLD, 1.0, 0.0, 1.0)
        light.draw_rays(_view(faint), 200, 150, GOLD, 1.0, 0.0, 0.3)
        assert sum(_pixels(faint)) < sum(_pixels(full)) * 0.5


# ========================================
# Ability effects
# ========================================

def _anchors(light, spec):
    return {
        'target': (150.0, 50.0),
        'keep': (130.0, 60.0),
        'territory': ['Mid'],
        'territories': ['Mid', 'East'],
        'points': light.points_inside('Mid', spec.get('points', 0), 1),
        'source': (50.0, 50.0),
        'dest': (250.0, 50.0),
        'keeps': [(130.0, 60.0), (230.0, 60.0)],
        'enemy_territories': ['East', 'South'],
        'enemy_keeps': [(250.0, 50.0)],
        'satellites': [(165.0, 50.0), (150.0, 65.0), (135.0, 50.0), (150.0, 35.0)],
    }


def _play(effect, view, until=None, step=1.0 / 30):
    """Render the effect over its life (or until `until` s); returns the frames' total light."""
    totals = []
    while not effect.is_finished() and (until is None or effect.elapsed < until):
        view.screen.fill((0, 0, 0))
        effect.light.begin_frame()
        effect.render_under(view)
        effect.render_over(view)
        totals.append(sum(_pixels(view.screen)))
        effect.update(step)
    return totals


class TestAbilityEffects:

    @pytest.mark.parametrize('ability', sorted(HERO_FX_STYLE['abilities']))
    def test_every_ability_draws_light_and_finishes(self, light, ability):
        spec = HERO_FX_STYLE['abilities'][ability]
        effect = HeroAbilityEffect(light, spec, _anchors(light, spec), seed=3)
        assert effect.cues and 0.5 < effect.duration < 6.0
        totals = _play(effect, _view())
        assert effect.is_finished()
        assert max(totals) > 0

    def test_same_seed_same_frames(self, light):
        spec = HERO_FX_STYLE['abilities']['Decisive Strike']
        frames = []
        for _ in range(2):
            effect = HeroAbilityEffect(light, spec, _anchors(light, spec), seed=11)
            effect.update(0.2)
            screen = _blank()
            light.begin_frame()
            for _ in range(3):   # fill the sprite caches first
                screen.fill((0, 0, 0))
                effect.render_under(_view(screen))
                effect.render_over(_view(screen))
            frames.append(_pixels(screen))
        assert frames[0] == frames[1]

    def test_each_repeats_its_cues_at_every_point(self, light):
        spec = HERO_FX_STYLE['abilities']['Levy']
        effect = HeroAbilityEffect(light, spec, _anchors(light, spec), seed=1)
        flares = [c for c in effect.cues if type(c).__name__ == '_FlareCue']
        assert len(flares) == spec['points']
        starts = sorted(c.at for c in flares)
        assert starts[1] - starts[0] == pytest.approx(0.1)   # staggered

    def test_missing_anchor_skips_its_cues(self, light):
        spec = HERO_FX_STYLE['abilities']['Levy']
        effect = HeroAbilityEffect(light, spec, {'target': (150.0, 50.0)}, seed=1)
        assert effect.cues == []
        assert effect.is_finished()

    def test_off_screen_effect_draws_nothing(self, light):
        spec = HERO_FX_STYLE['abilities']['Decisive Strike']
        effect = HeroAbilityEffect(light, spec, {'target': (5000.0, 5000.0)}, seed=1)
        assert max(_play(effect, _view(), until=0.5)) == 0

    def test_envelope(self):
        assert envelope(-0.1, 1.0, 0.1, 0.3) == 0.0
        assert envelope(0.05, 1.0, 0.1, 0.3) == pytest.approx(0.5)
        assert envelope(0.5, 1.0, 0.1, 0.3) == 1.0
        assert envelope(1.0, 1.0, 0.1, 0.3) == 0.0


# ========================================
# Passive auras
# ========================================

class TestHeroAura:

    @pytest.mark.parametrize('key', sorted(HERO_FX_STYLE['auras']))
    def test_aura_fades_in_and_out(self, light, key):
        aura = HeroAura(light, key)
        aura.set_territories(['West', 'Mid'])
        assert not aura.visible
        aura.update(0.1, True)
        assert aura.visible and 0.0 < aura.strength < 1.0
        aura.update(5.0, True)
        assert aura.strength == 1.0
        aura.update(5.0, False)
        assert not aura.visible

    def test_aura_draws_light_along_the_outline(self, light):
        aura = HeroAura(light, 'defiance')
        aura.set_territories(['West', 'Mid'])
        aura.update(5.0, True)
        screen = _blank()
        for _ in range(4):
            light.begin_frame()
            aura.render(_view(screen, zoom=1.0), 0.0)
        # Light near the outer border (left edge of West), none in the middle of nowhere
        left = sum(sum(tuple(screen.get_at((x, 50)))[:3]) for x in range(0, 12))
        assert left > 0
        assert tuple(screen.get_at((350, 250)))[:3] == (0, 0, 0)

    def test_aura_does_no_territory_lookups_per_frame(self, light):
        """Outline and spawn points are built once; after that a frame does no
        inside-the-territory tests at all (the old bubbles did one per bubble)."""
        aura = HeroAura(light, 'haste')
        aura.set_territories(['West', 'Mid', 'South'])
        aura.update(5.0, True)
        view = _view()
        light.begin_frame()
        aura.render(view, 0.0)
        raster = light.raster()

        def forbidden(*_):
            raise AssertionError('territory lookup during a frame')

        raster.at = forbidden
        for i in range(30):
            light.begin_frame()
            aura.render(view, i / 30.0)

    def test_firefly_count_follows_territory_area(self, light):
        """The same firefly density in big and small territories (owner, 2026-10-26:
        7 per territory were barely visible)."""
        assert light.area('West') == pytest.approx(10000.0)
        assert light.mote_count('West', {'density': 1.0, 'min': 3}, 30) == 10
        assert light.mote_count('West', {'density': 0.1, 'min': 3}, 30) == 3     # at least min
        assert light.mote_count('West', {'density': 9.0, 'min': 3}, 30) == 30    # at most the table
        assert light.mote_count('West', {}, 12) == 12                            # no density: all
        motes = HERO_FX_STYLE['auras']['defiance']['motes']
        assert light.mote_count('West', motes, motes['count']) >= 14

    def test_aura_set_change_rebuilds_the_outline_only_when_it_changes(self, light):
        aura = HeroAura(light, 'safe_haven')
        aura.set_territories(['West', 'Mid'])
        outline = aura.outline
        aura.set_territories(['Mid', 'West'])
        assert aura.outline is outline
        aura.set_territories(['Mid'])
        assert aura.outline is not outline


# ========================================
# Styles
# ========================================

class TestStyles:

    def test_every_look_has_a_style(self):
        assert get_hero_fx_style('2d') is HERO_FX_STYLES['2d']
        assert get_hero_fx_style('3d') is HERO_FX_STYLES['3d']
        assert get_hero_fx_style('unknown') is HERO_FX_STYLES['2d']

    def test_cue_kinds_are_known(self):
        known = {'rays', 'flare', 'ring', 'sparks', 'rim', 'motes', 'each', 'comets', 'drain',
                 'dust', 'curtain'}

        def kinds(cues):
            for cue in cues:
                yield cue['kind']
                if cue['kind'] == 'each':
                    yield from kinds(cue['cues'])

        for name, spec in HERO_FX_STYLE['abilities'].items():
            assert set(kinds(spec['cues'])) <= known, name

    def test_stable_seed_is_stable(self):
        assert stable_seed('Levy', 'Valeonia') == stable_seed('Levy', 'Valeonia')
        assert stable_seed('Levy', 'Valeonia') != stable_seed('Levy', 'Occiant')


def test_prewarm_builds_the_aura_sprites(light):
    """Selecting a hero never waits for sprites: the aura's outline and fireflies are
    built at load, so they draw on their first frame even with no build budget."""
    light.prewarm(range(16, 25))
    aura = HeroAura(light, 'defiance')
    aura.set_territories(['West', 'Mid'])
    aura.update(5.0, True)
    light.glow._budget = light_fx._BuildBudget(0, 0)
    light.tint._budget = light_fx._BuildBudget(0, 0)
    for radius in (16, 20, 24):
        light.begin_frame()
        assert light._mote_sprites(aura.motes, radius, aura.mote_colour,
                                   tuple(aura.style['colour']), aura.style['motes']['tint_size'],
                                   aura.style['motes']['tint']) is not None
        screen = _blank()
        aura.render(_view(screen, radius=radius), 0.0)
        assert sum(_pixels(screen)) > 0


def _centroid(sprite):
    total = sx = sy = 0
    for y in range(sprite.get_height()):
        for x in range(sprite.get_width()):
            v = sum(tuple(sprite.get_at((x, y)))[:3])
            total += v
            sx += v * x
            sy += v * y
    return sx / total, sy / total


def test_shifted_sprites_move_by_sub_pixels():
    """A dot rising 0.2 px a frame jumped a whole pixel every few frames (owner,
    2026-10-27: the embers stuttered); shifted copies place it within a quarter pixel."""
    glow = GlowSprites()
    glow._budget.ms = glow._budget.count = 10 ** 6
    x0, y0 = _centroid(glow.sprite(16, GOLD, 12))
    for phase, (dx, dy) in ((1, (0, 0.25)), (2, (0, 0.5)), (3, (0, 0.75)), (4, (0.5, 0)),
                            (6, (0.5, 0.5))):
        x, y = _centroid(glow.sprite(16, GOLD, 12, 'mote', phase))
        assert x - x0 == pytest.approx(dx, abs=0.08) and y - y0 == pytest.approx(dy, abs=0.08)


def test_fireflies_use_their_sub_pixel_copies_once_built(light):
    aura = HeroAura(light, 'haste')
    args = (aura.motes, 20, aura.mote_colour, tuple(aura.style['colour']),
            aura.style['motes']['tint_size'], aura.style['motes']['tint'])
    for _ in range(200):                 # within the frame budget, a few frames' work
        light.begin_frame()
        prepared = light._mote_sprites(*args)
    phases = prepared[0][0]
    assert len(phases) == GlowSprites.SUBPIXEL_PHASES
    assert all(ladder is not phases[0] for ladder in phases[1:])
    assert light._mote_sprites(*args) is prepared          # cached once complete


def test_halo_steps_span_the_halos_own_range():
    """12 alpha steps up to the halo's peak (175), not 8 (255 / 12 quantization)."""
    tint = TintSprites()
    tint._budget.ms = tint._budget.count = 10 ** 6
    ladder = tint.alpha_ladder(24, GOLD, 175)
    alphas = [sprite.get_at((12, 12)).a for sprite in ladder[1:]]
    assert len(set(alphas)) == 12 and alphas == sorted(alphas)
    assert 165 <= alphas[-1] <= 176


def test_production_rays_unchanged_by_the_shared_helpers():
    """The ray helpers moved to light_fx; production_glow_effect still exposes them."""
    from ui.effects import production_glow_effect as pge
    assert pge._new_black_surface is light_fx.new_black_surface
    assert pge.light_colour((100, 150, 255)) == light_fx.light_colour(
        (100, 150, 255), pge.RAY_STYLE['white_mix'], pge.RAY_STYLE['warm_white'])


# ========================================
# Game integration (real Game)
# ========================================

@pytest.fixture(scope='module')
def game(display):
    pygame.display.set_mode((1600, 900))
    from main import Game
    g = Game()
    g.initialize_game({
        'num_players': 3,
        'player_is_ai': [False, True, True],
        'player_ai_difficulty': [None, 'Normal', 'Normal'],
    })
    g.game_state.phase = 'playing'
    g.game_state.current_player = 0
    return g


def _keep_with_neighbours(game, player=0):
    """Give `player` a territory on screen and all its neighbours; returns the territory."""
    import map_data
    gs = game.game_state
    width, height = game.screen.get_size()
    for territory, centre in sorted(game.scaled_centers.items()):
        x, y = game.world_to_screen(centre)
        if 300 < x < width - 300 and 250 < y < height - 250 and game.scaled_plots.get(territory):
            for t in [territory] + list(map_data.get_neighbors(territory)):
                gs.territory_owners[t] = player
            gs._territory_owners_version += 1
            return territory
    pytest.skip('no territory on screen at the starting camera')


@pytest.fixture
def seledra(game):
    """Seledra Rennervail (Defiance) in a Keep of player 0, selected; undone afterwards."""
    gs = game.game_state
    keep = _keep_with_neighbours(game)
    gs.heroes.setdefault(0, {})['Seledra Rennervail'] = {
        'keep_territory': keep, 'keep_plot': 0, 'status': 'active'}
    game.selected_hero = 'Seledra Rennervail'
    yield keep
    game.selected_hero = None
    gs.heroes.get(0, {}).pop('Seledra Rennervail', None)
    for _ in range(40):
        game.update_map_effects(1 / 30)


class TestGameIntegration:

    def test_selected_hero_shows_its_aura_over_the_covered_territories(self, game, seledra):
        renderer = game.map_renderer
        for _ in range(20):
            game.update_map_effects(1 / 30)
        aura = renderer.hero_auras['defiance']
        expected = game.game_state.get_defiance_protected_territories(0)
        assert aura.visible and aura.strength == 1.0
        assert set(aura.territories) == set(expected)
        assert not renderer.hero_auras['haste'].visible

    def test_aura_fades_out_when_the_hero_is_deselected(self, game, seledra):
        for _ in range(20):
            game.update_map_effects(1 / 30)
        game.selected_hero = None
        game.update_map_effects(0.1)
        aura = game.map_renderer.hero_auras['defiance']
        assert 0.0 < aura.strength < 1.0
        for _ in range(20):
            game.update_map_effects(1 / 30)
        assert not aura.visible

    def test_aura_territories_are_not_recomputed_every_frame(self, game, seledra, monkeypatch):
        gs = game.game_state
        calls = []
        original = gs.get_defiance_protected_territories
        monkeypatch.setattr(gs, 'get_defiance_protected_territories',
                            lambda p: calls.append(p) or original(p))
        game.map_renderer._hero_aura_sync = None
        for _ in range(30):
            game.update_map_effects(1 / 30)
        assert len(calls) == 1
        gs._territory_owners_version += 1          # ownership changed: recomputed once
        game.update_map_effects(1 / 30)
        assert len(calls) == 2

    def test_aura_is_drawn_under_the_plots(self, game, seledra):
        for _ in range(20):
            game.update_map_effects(1 / 30)
        game.draw()
        with_aura = pygame.image.tostring(game.screen, 'RGB')
        game.selected_hero = None
        for _ in range(30):
            game.update_map_effects(1 / 30)
        game.draw()
        assert pygame.image.tostring(game.screen, 'RGB') != with_aura

    def test_embargo_embers_follow_the_blocked_players(self, game):
        gs = game.game_state
        renderer = game.map_renderer
        for territory in sorted(game.scaled_polygons)[:3]:
            gs.territory_owners[territory] = 1
        gs._territory_owners_version += 1
        gs.embargo_blocked_players[:] = [1]
        try:
            for _ in range(30):
                game.update_map_effects(1 / 30)
            embers = renderer.embargo_embers
            owned_by_1 = {t for t, o in gs.territory_owners.items() if o == 1}
            assert embers.visible and set(embers.territories) == owned_by_1
            game.draw()   # draws without error
        finally:
            gs.embargo_blocked_players[:] = []
        for _ in range(40):
            game.update_map_effects(1 / 30)
        assert not renderer.embargo_embers.visible

    def test_embargo_embers_cover_ai_casts_too(self, game):
        """The embers come from game state, so an Embargo cast by the AI (which
        never reaches trigger_ability_effect) shows them as well."""
        gs = game.game_state
        gs._activate_embargo(1)                    # player 1 (AI) embargoes its enemies
        try:
            for _ in range(30):
                game.update_map_effects(1 / 30)
            assert game.map_renderer.embargo_embers.visible
            assert {gs.territory_owners[t] for t in game.map_renderer.embargo_embers.territories} \
                <= set(gs.embargo_blocked_players)
        finally:
            gs.embargo_blocked_players[:] = []
            for _ in range(40):
                game.update_map_effects(1 / 30)

    def test_silence_fog_is_baked_once(self, game):
        gs = game.game_state
        gs.hero_silence_status[1] = 2
        gs.silence_activation_time = None
        try:
            game.draw_silence_fog_overlay()
            fog = game._cached_silence_fog
            game.screen.fill((200, 200, 200))
            game.draw_silence_fog_overlay()
            assert game._cached_silence_fog is fog
            # Faded in: alpha 255 (a partial alpha would put every blit on pygame's slow
            # path; None would switch the per-pixel alpha off: an opaque red wall)
            assert fog.get_alpha() == 255
            from main import TOP_PANEL_HEIGHT
            middle = game.screen.get_at((fog.get_width() // 2, TOP_PANEL_HEIGHT + fog.get_height() // 2))
            assert middle.r > 150 and middle.g > 120   # the map still shows through
            # A vignette: the edge of the map is redder than its middle
            assert fog.get_at((2, fog.get_height() // 2)).a > fog.get_at(
                (fog.get_width() // 2, fog.get_height() // 2)).a
        finally:
            gs.hero_silence_status[1] = 0

    def test_display_change_rebuilds_the_hero_light(self, game):
        renderer = game.map_renderer
        light = renderer.hero_light
        renderer.rebuild_scale_caches()
        assert renderer.hero_light is not light
        assert renderer.hero_auras['defiance'].light is renderer.hero_light


# ========================================
# Every cast through the game (phase 3)
# ========================================

def _give(game, player, hero, keep):
    gs = game.game_state
    gs.buildings.setdefault(keep, {})[0] = 'Keep'
    gs.heroes.setdefault(player, {})[hero] = {'keep_territory': keep, 'keep_plot': 0, 'status': 'active'}


class TestCastsInGame:

    @pytest.fixture
    def board(self, game):
        """Player 0 owns a territory and its neighbours, the rest belongs to 1 and 2."""
        import map_data
        gs = game.game_state
        saved = (dict(gs.territory_owners), {k: dict(v) for k, v in gs.buildings.items()},
                 {k: dict(v) for k, v in gs.heroes.items()}, gs.hero_ability_cooldowns)
        gs.hero_ability_cooldowns = {}     # no ability on cooldown from an earlier test
        keep = _keep_with_neighbours(game)
        mine = {keep} | set(map_data.get_neighbors(keep))
        for i, t in enumerate(sorted(game.scaled_polygons)):
            if t not in mine:
                gs.territory_owners[t] = 1 + i % 2
        gs._territory_owners_version += 1
        target = next(t for t in sorted(map_data.get_neighbors(keep)) if t in game.scaled_centers)
        enemy = next(t for t, o in sorted(gs.territory_owners.items()) if o == 1 and t in game.scaled_centers)
        game.map_renderer.ability_effects = []
        yield keep, target, enemy
        gs.territory_owners.clear()
        gs.territory_owners.update(saved[0])
        gs.buildings.clear()
        gs.buildings.update(saved[1])
        gs.heroes.clear()
        gs.heroes.update(saved[2])
        gs.hero_ability_cooldowns = saved[3]
        gs._territory_owners_version += 1
        gs.embargo_blocked_players[:] = []
        game.map_renderer.ability_effects = []

    def test_every_active_ability_shows_an_effect(self, game, board):
        """Every active ability in HERO_TYPES has a style and shows on the map when cast."""
        gs = game.game_state
        keep, target, enemy = board
        for hero, info in gs.HERO_TYPES.items():
            _give(game, 0, hero, keep)
        actives = sorted({a['name'] for info in gs.HERO_TYPES.values()
                          for a in info['abilities'] if a['type'] == 'active'})
        for ability in actives:
            assert ability in HERO_FX_STYLE['abilities'], ability
            hero = next(h for h, info in gs.HERO_TYPES.items()
                        if any(a['name'] == ability for a in info['abilities']))
            game.map_renderer.ability_effects = []
            game.play_ability_effect(0, hero, ability, enemy if ability != 'Levy' else keep)
            effects = game.map_renderer.ability_effects
            assert len(effects) == 1 and effects[0].cues, ability
            for _ in range(6):                        # draws without error
                game.update_map_effects(1 / 30)
                game.draw()

    def test_arcs_run_between_the_keep_plot_and_the_target(self, game, board):
        keep, target, enemy = board
        _give(game, 0, 'Aidam Narn', keep)
        game.play_ability_effect(0, 'Aidam Narn', 'Royal Charisma', enemy)
        comets = next(c for c in game.map_renderer.ability_effects[-1].cues
                      if type(c).__name__ == '_CometsCue')
        sx, sy, _, _, dx, dy = comets.curve
        assert (sx, sy) == tuple(game.scaled_centers[enemy])          # from the target...
        assert (dx, dy) == tuple(game.scaled_plots[keep][0])          # ...to the Keep plot

    def test_a_cast_builds_no_territory_borders(self, game, board):
        """Borders are built at load: an Embargo over half the map must not hitch."""
        keep, target, enemy = board
        _give(game, 0, 'Evain Nithieln', keep)
        light = game.map_renderer.hero_light
        built = dict(light._fine)
        start = time.perf_counter()
        game.play_ability_effect(0, 'Evain Nithieln', 'Embargo')
        assert light._fine == built
        assert (time.perf_counter() - start) * 1000 < 40

    def test_ai_cast_sequential_is_shown(self, game, board):
        """The AI calls game_state directly (ai_player.py): its casts used to show nothing."""
        from ai_player import AIPlayer
        gs = game.game_state
        keep, target, enemy = board
        _give(game, 1, 'Evain Nithieln', enemy)
        gs.ability_fx_events = []
        AIPlayer(1, 1)._execute_action_internal(
            gs, 'hero_ability', {'hero_type': 'Evain Nithieln', 'ability_name': 'Embargo', 'target': None})
        assert gs.ability_fx_events == [(1, 'Evain Nithieln', 'Embargo', None)]
        game.update_map_effects(1 / 30)
        assert gs.ability_fx_events == []
        assert len(game.map_renderer.ability_effects) == 1

    def test_ai_cast_simultaneous_is_shown_once(self, game, board):
        from simultaneous.sim_phase_manager import SimPhaseManager
        gs = game.game_state
        keep, target, enemy = board
        _give(game, 1, 'Evain Nithieln', enemy)
        _give(game, 0, 'Evain Nithieln', keep)
        manager = SimPhaseManager.__new__(SimPhaseManager)
        manager.gs = gs
        gs.ability_fx_events = []
        manager._apply_hero_ability_order({'player_id': 1, 'hero_type': 'Evain Nithieln',
                                           'ability_name': 'Embargo', 'target': None})
        assert gs.ability_fx_events == [(1, 'Evain Nithieln', 'Embargo', None)]
        # A human's order is never recorded here (their cast shows when it is made)
        gs.ability_fx_events = []
        manager._apply_hero_ability_order({'player_id': 0, 'hero_type': 'Evain Nithieln',
                                           'ability_name': 'Embargo', 'target': None})
        assert gs.ability_fx_events == []

    def test_casts_finish_and_are_removed(self, game, board):
        keep, target, enemy = board
        _give(game, 0, 'Serthus Diarcess', keep)
        game.play_ability_effect(0, 'Serthus Diarcess', 'Decisive Strike', enemy)
        for _ in range(120):
            game.update_map_effects(1 / 30)
        assert game.map_renderer.ability_effects == []
