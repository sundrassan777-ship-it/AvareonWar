# -*- coding: utf-8 -*-
"""
Selection rings and order arrows as light (order FX pass, 2026-10).

The light kit's additions (ui/effects/light_fx.py): cached ring frames and
points along open paths. The marks (ui/effects/order_fx_effect.py): the
selection ring, the order arrows and the destination reticle, styled in
ui/effects/order_fx_style.py.

Unit tests draw on blank surfaces, so they need no Game; the game integration
is tested further down.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

from config.constants import COLOR_ARROW_MOVEMENT, COLOR_ARROW_HOVERED, COLOR_ARROW_ALLY  # noqa: E402
from ui.effects.light_fx import SoftRing, path_beads, path_lengths, path_point  # noqa: E402
from ui.effects.hero_fx_effect import FxView  # noqa: E402
from ui.effects.order_fx_style import ORDER_FX_STYLE, ORDER_FX_STYLES, get_order_fx_style  # noqa: E402
from ui.effects.order_fx_effect import OrderLight, OrderArrow  # noqa: E402

RADIUS = 20   # plot radius in px for the unit tests


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((400, 300))
    yield


def _unbudgeted(light):
    """No per-frame time budgets: tests must not depend on speed."""
    light.glow._budget.ms = light.tint._budget.ms = 10 ** 6
    light.glow._budget.count = light.tint._budget.count = 10 ** 6
    for ring in light._rings:
        ring._budget.ms = ring._budget.count = 10 ** 6
    return light


@pytest.fixture
def light():
    return _unbudgeted(OrderLight())


def _blank(size=(400, 300), colour=(0, 0, 0)):
    surface = pygame.Surface(size)
    surface.fill(colour)
    return surface


def _view(screen, zoom=1.0, radius=RADIUS, ax=0.0, ay=0.0):
    return FxView(screen, ax, ay, zoom, radius)


def _light_at(surface, x, y):
    return sum(surface.get_at((int(x), int(y)))[:3])


def _total(surface):
    return sum(pygame.image.tostring(surface, 'RGB'))


# ========================================
# Light kit additions
# ========================================

class TestPaths:

    def test_beads_are_evenly_spaced_between_start_and_stop(self):
        line = [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0)]
        beads = path_beads(line, 10.0, start=5.0, stop=85.0)
        assert [round(s, 6) for _, _, s in beads] == [5, 15, 25, 35, 45, 55, 65, 75, 85]
        # Arc length 55 is 5 px down the second segment
        x, y, s = beads[5]
        assert (round(x, 6), round(y, 6)) == (50.0, 5.0)

    def test_point_and_tangent_along_a_path(self):
        line = [(0.0, 0.0), (30.0, 40.0)]
        lengths = path_lengths(line)
        assert lengths == [0.0, 50.0]
        x, y, tx, ty = path_point(line, lengths, 25.0)
        assert (round(x, 6), round(y, 6), round(tx, 6), round(ty, 6)) == (15.0, 20.0, 0.6, 0.8)
        # Clamped to the ends
        assert path_point(line, lengths, 99.0)[:2] == (30.0, 40.0)


def _free_ring(width=0.1):
    """A SoftRing without the per-frame build budget."""
    ring = SoftRing(width)
    ring._budget.ms = ring._budget.count = 10 ** 6
    return ring


class TestRingFrames:

    def test_frames_are_cached_per_radius_colour_and_level(self):
        ring = _free_ring()
        first = ring.frame(30, (0, 255, 0), 12)
        assert first is ring.frame(30, (0, 255, 0), 12)
        assert ring.frame(31, (0, 255, 0), 12) is not first
        assert ring.frames_built == 2
        # A brighter level adds more light
        assert _total(ring.frame(30, (0, 255, 0), 24)) > _total(first)

    def test_tint_frames_quantize_alpha(self):
        ring = _free_ring()
        assert ring.tint_frame(30, (0, 255, 0), 95) is ring.tint_frame(30, (0, 255, 0), 98)
        assert ring.tint_frame(30, (0, 255, 0), 3) is None   # rounds to nothing

    def test_builds_wait_for_the_next_frame_once_the_budget_is_spent(self):
        ring = SoftRing(0.1)
        ring.begin_frame()
        built = [ring.frame(20 + i, (255, 255, 255), 10) for i in range(SoftRing.BUILDS_PER_FRAME + 3)]
        assert None in built
        ring.begin_frame()
        assert ring.frame(20 + SoftRing.BUILDS_PER_FRAME + 2, (255, 255, 255), 10) is not None


# ========================================
# Selection ring
# ========================================

class TestSelectionRing:

    def test_ring_surrounds_the_target_and_leaves_its_centre_alone(self, light):
        screen = _blank()
        light.draw_selection(_view(screen), 200, 150, RADIUS, clock=0.3)
        ring = RADIUS + ORDER_FX_STYLE['selection']['ring']['gap'] * RADIUS
        assert _light_at(screen, 200, 150) == 0
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            assert _light_at(screen, 200 + math.cos(a) * ring, 150 + math.sin(a) * ring) > 60
        # Nothing past where the pulses end
        reach = ring * ORDER_FX_STYLE['selection']['pulses']['reach'] + 12
        assert _light_at(screen, 200 + reach, 150) == 0

    def test_ring_follows_the_plot_radius(self, light):
        ring_style = ORDER_FX_STYLE['selection']['ring']
        for plot_radius in (16, 24):
            screen = _blank()
            light.draw_selection(_view(screen, radius=plot_radius), 200, 150, plot_radius, clock=0.3)
            ring = plot_radius * (1.0 + ring_style['gap'])
            assert _light_at(screen, 200 + ring, 150) > 60
            assert _light_at(screen, 200 + plot_radius * 0.5, 150) == 0

    def test_pulses_grow_outward_and_fade(self, light):
        calls = []
        real = light.pulse_ring.frame

        def spy(radius, colour, level):
            calls.append((radius, level))
            return real(radius, colour, level)

        light.pulse_ring.frame = spy
        pulses = ORDER_FX_STYLE['selection']['pulses']
        step = pulses['period'] / 20.0
        # One pulse (the first of each pair of calls) from just after it leaves the ring
        for i in range(2, 19):
            light.draw_selection(_view(_blank()), 200, 150, RADIUS, clock=i * step)
        first = calls[::pulses['count']]
        radii = [r for r, _ in first]
        levels = [lv for _, lv in first]
        assert radii == sorted(radii) and radii[-1] > radii[0] * 1.5
        assert levels[2:] == sorted(levels[2:], reverse=True) and levels[-1] < levels[2]

    def test_nothing_new_is_built_once_warm(self, light):
        view = _view(_blank())
        period = ORDER_FX_STYLE['selection']['pulses']['period']
        frames = int(2 * period * 60)
        for i in range(frames):
            light.begin_frame()
            light.draw_selection(view, 200, 150, RADIUS, clock=i / 60.0)
        built = (light.glow.sprites_built, light.tint.sprites_built,
                 [ring.frames_built for ring in light._rings])
        for i in range(frames, frames + 120):
            light.begin_frame()
            light.draw_selection(view, 200, 150, RADIUS, clock=i / 60.0)
        assert (light.glow.sprites_built, light.tint.sprites_built,
                [ring.frames_built for ring in light._rings]) == built

    def test_off_screen_ring_draws_nothing(self, light):
        screen = _blank()
        light.draw_selection(_view(screen), -300, 150, RADIUS, clock=0.3)
        assert _total(screen) == 0


# ========================================
# Arrows
# ========================================

def _arrow_path(light, arrow, zoom=1.0, radius=RADIUS, lift=0):
    return light._path(arrow, _view(_blank(), zoom, radius), lift)


class TestArrows:

    def test_arrow_stops_outside_both_banners(self, light):
        arrows = ORDER_FX_STYLE['arrows']
        arrow = OrderArrow([(40, 150), (360, 150)])
        path = _arrow_path(light, arrow)
        tip_x, tip_y = path.tip
        assert math.hypot(tip_x - 360, tip_y - 150) >= arrows['end_gap'] * RADIUS - 0.5
        half = max(2, int(arrows['size'] * RADIUS) & ~1) >> 1
        x, y, _ = path.beads[0]
        assert math.hypot(x + half - 40, y + half - 150) >= arrows['start_gap'] * RADIUS - 1.5

    def test_short_routes_still_get_a_head(self, light):
        path = _arrow_path(light, OrderArrow([(190, 150), (215, 150)]))
        assert path.head and path.beads

    def test_opposite_routes_run_side_by_side(self, light):
        there = _arrow_path(light, OrderArrow([(60, 150), (340, 150)]))
        back = _arrow_path(light, OrderArrow([(340, 150), (60, 150)]))
        mid_there = there.beads[len(there.beads) // 2]
        mid_back = back.beads[len(back.beads) // 2]
        # Bowed to the right of travel: below the line one way, above it the other
        assert mid_there[1] > 150 > mid_back[1]
        assert mid_there[1] - mid_back[1] > ORDER_FX_STYLE['arrows']['size'] * RADIUS * 2

    def test_two_hop_passes_through_the_waypoint(self, light):
        arrow = OrderArrow([(40, 250), (200, 60), (360, 250)])
        path = _arrow_path(light, arrow)
        spacing = ORDER_FX_STYLE['arrows']['size'] * RADIUS
        half = max(2, int(ORDER_FX_STYLE['arrows']['size'] * RADIUS) & ~1) >> 1
        nearest = min(math.hypot(x + half - 200, y + half - 60) for x, y, _ in path.beads)
        assert nearest <= spacing
        # The badge sits on the first leg
        assert path.badge[0] < 200

    def test_crests_flow_from_source_to_target(self, light):
        arrow = OrderArrow([(40, 150), (360, 150)])
        path = _arrow_path(light, arrow)

        def brightest_x(clock):
            screen = _blank()
            light.draw_arrows(_view(screen), [arrow], clock)
            # Brightness along the shaft beads, away from the head
            samples = [(x, _light_at(screen, x + 4, y + 4)) for x, y, _ in path.beads[3:-3]]
            return max(samples, key=lambda s: s[1])[0]

        flow = ORDER_FX_STYLE['arrows']['flow']
        assert brightest_x(0.1 / flow) > brightest_x(0.0)

    def test_hovered_arrows_are_gold_and_allies_cyan(self, light):
        assert light.arrow_colours['own'][0] == COLOR_ARROW_MOVEMENT
        assert light.arrow_colours['hovered'][0] == COLOR_ARROW_HOVERED
        assert light.arrow_colours['ally'][0] == COLOR_ARROW_ALLY

    def test_cancelled_arrows_fade_out(self, light):
        arrow = OrderArrow([(40, 150), (360, 150)], 'cancelled')
        totals = []
        for fade in (1.0, 0.5, 0.0):
            arrow.fade = fade
            screen = _blank()
            light.draw_arrows(_view(screen), [arrow], 0.0)
            totals.append(_total(screen))
        assert totals[0] > totals[1] > totals[2] == 0

    def test_off_screen_arrows_draw_nothing(self, light):
        screen = _blank()
        light.draw_arrows(_view(screen), [OrderArrow([(-900, -900), (-600, -700)])], 0.0)
        assert _total(screen) == 0

    def test_panning_reuses_the_geometry(self, light):
        arrow = OrderArrow([(40, 150), (360, 150)])
        screen = _blank()
        light.draw_arrows(_view(screen), [arrow], 0.0)
        built = light.paths_built
        moved = _blank()
        light.draw_arrows(_view(moved, ax=-25.0, ay=10.0), [arrow], 0.0)
        assert light.paths_built == built
        # The same picture, moved
        assert screen.subsurface((25, 0, 375, 290)).get_at((100, 150)) == moved.get_at((100, 160))

    def test_badges_on_top_with_the_count_and_colour(self, light):
        drawn = []
        arrows = [OrderArrow([(40, 150), (360, 150)], 'hovered', 12), OrderArrow([(40, 60), (360, 60)])]
        light.draw_arrows(_view(_blank()), arrows, 0.0, badge=lambda pos, n, c: drawn.append((pos, n, c)))
        assert len(drawn) == 1   # no count, no badge
        (x, y), count, colour = drawn[0]
        assert count == 12 and colour == COLOR_ARROW_HOVERED and 180 < x < 220

    def test_nothing_new_is_built_once_warm(self, light):
        view = _view(_blank())
        arrows = [OrderArrow([(40, 150), (360, 150)]), OrderArrow([(60, 40), (300, 260)], 'ally')]
        for i in range(120):
            light.begin_frame()
            light.draw_arrows(view, arrows, i / 60.0)
        built = (light.glow.sprites_built, light.tint.sprites_built, light.paths_built)
        for i in range(120, 240):
            light.begin_frame()
            light.draw_arrows(view, arrows, i / 60.0)
        assert (light.glow.sprites_built, light.tint.sprites_built, light.paths_built) == built


# ========================================
# Reticle
# ========================================

class TestReticle:

    def test_ring_and_four_ticks(self, light):
        reticle = ORDER_FX_STYLE['reticle']
        screen = _blank()
        light.draw_reticle(_view(screen), 200, 150, 14, 'attack', clock=0.0)
        ring = 14 + reticle['gap'] * RADIUS
        assert _light_at(screen, 200, 150) == 0
        assert _light_at(screen, 200 + ring * 0.7071, 150 + ring * 0.7071) > 40
        ticks = reticle['ticks']
        mid = ring + (ticks['gap'] + ticks['travel'] * 0.5 + ticks['length'] * 0.5) * RADIUS
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            assert _light_at(screen, 200 + dx * mid, 150 + dy * mid) > 40
        # Not between the ticks, outside the ring
        assert _light_at(screen, 200 + mid * 0.7071, 150 + mid * 0.7071) < _light_at(screen, 200 + mid, 150)

    def test_attack_is_red_and_merge_cyan(self, light):
        red, cyan = _blank(), _blank()
        light.draw_reticle(_view(red), 200, 150, 14, 'attack', clock=0.0)
        light.draw_reticle(_view(cyan), 200, 150, 14, 'merge', clock=0.0)
        ring = 14 + ORDER_FX_STYLE['reticle']['gap'] * RADIUS
        r, g, b, _ = red.get_at((200 + int(ring), 150))
        assert r > g and r > b
        r, g, b, _ = cyan.get_at((200 + int(ring), 150))
        assert b > r and g > r


# ========================================
# Styles
# ========================================

class TestStyles:

    def test_both_looks_have_a_style_and_unknown_looks_get_2d(self):
        assert set(ORDER_FX_STYLES) == {'2d', '3d'}
        assert get_order_fx_style('elsewhere') is ORDER_FX_STYLES['2d']

    def test_every_arrow_kind_and_reticle_kind_has_a_colour(self):
        assert set(ORDER_FX_STYLE['arrows']['kinds']) == {'own', 'ally', 'hovered', 'cancelled'}
        assert set(ORDER_FX_STYLE['reticle']['kinds']) == {'attack', 'merge'}

    def test_prewarm_builds_the_arrow_and_ring_sprites(self):
        light = OrderLight()
        light.prewarm(range(16, 25))
        built = light.glow.sprites_built
        view = _view(_blank(), radius=20)
        light.begin_frame()
        light.draw_arrows(view, [OrderArrow([(40, 150), (360, 150)])], 0.0)
        assert light.glow.sprites_built == built
