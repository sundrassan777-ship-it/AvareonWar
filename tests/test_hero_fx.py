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
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

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
        known = {'rays', 'flare', 'ring', 'sparks', 'rim', 'motes', 'each'}

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
    """Selecting a hero never waits for sprites: the aura's are built at load."""
    light.prewarm(range(16, 25))
    built = light.glow.sprites_built
    aura = HeroAura(light, 'defiance')
    aura.set_territories(['West'])
    aura.update(5.0, True)
    for radius in (16, 20, 24):
        light.begin_frame()
        aura.render(_view(radius=radius), 0.0)
    assert light.glow.sprites_built == built


def test_production_rays_unchanged_by_the_shared_helpers():
    """The ray helpers moved to light_fx; production_glow_effect still exposes them."""
    from ui.effects import production_glow_effect as pge
    assert pge._new_black_surface is light_fx.new_black_surface
    assert pge.light_colour((100, 150, 255)) == light_fx.light_colour(
        (100, 150, 255), pge.RAY_STYLE['white_mix'], pge.RAY_STYLE['warm_white'])
