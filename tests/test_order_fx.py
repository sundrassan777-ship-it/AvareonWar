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

from config.constants import (COLOR_ARROW_ATTACK, COLOR_ARROW_MOVE, COLOR_ARROW_REINFORCE,  # noqa: E402
                              COLOR_ARROW_HOVERED, COLOR_ARROW_CANCELLED)
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
    budgets = [light.glow._budget, light.tint._budget] + [ring._budget for ring in light._rings]
    for budget in budgets:
        budget.ms = budget.count = budget.left = 10 ** 6
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
        # Dimmed, so no colour channel saturates and the crests stand out
        arrow = OrderArrow([(40, 150), (360, 150)], fade=0.6)
        path = _arrow_path(light, arrow)
        half = max(2, int(ORDER_FX_STYLE['arrows']['size'] * RADIUS) & ~1) >> 1

        def profile(clock):
            screen = _blank()
            light.draw_arrows(_view(screen), [arrow], clock)
            # Brightness at each shaft bead, away from the head
            return [_light_at(screen, x + half, y + half) for x, y, _ in path.beads[3:-3]]

        def match(before, after, shift):
            """How well `after` is `before` moved `shift` beads toward the target."""
            if shift >= 0:
                return sum(a * b for a, b in zip(before, after[shift:]))
            return sum(a * b for a, b in zip(before[-shift:], after))

        flow = ORDER_FX_STYLE['arrows']['flow']
        before, after = profile(0.0), profile(0.1 / flow)
        assert before != after
        forward = max(match(before, after, s) for s in range(1, 9))
        backward = max(match(before, after, -s) for s in range(1, 9))
        assert forward > backward

    def test_kinds_take_the_action_queue_colours(self, light):
        assert light.arrow_colours['attack'][0] == COLOR_ARROW_ATTACK
        assert light.arrow_colours['own'][0] == COLOR_ARROW_MOVE
        assert light.arrow_colours['ally'][0] == COLOR_ARROW_REINFORCE
        assert light.arrow_colours['hovered'][0] == COLOR_ARROW_HOVERED
        assert light.arrow_colours['cancelled'][0] == COLOR_ARROW_CANCELLED
        # Same hue families as the cards: attack red, move blue, reinforce green
        r, g, b = COLOR_ARROW_ATTACK
        assert r > g and r > b
        r, g, b = COLOR_ARROW_MOVE
        assert b > r and b > g
        r, g, b = COLOR_ARROW_REINFORCE
        assert g > r and g > b

    def test_an_allys_order_is_dimmer_and_does_not_flow(self, light):
        def picture(allied, clock):
            screen = _blank()
            light.draw_arrows(_view(screen), [OrderArrow([(40, 150), (360, 150)], 'attack', allied=allied)],
                              clock)
            return screen

        assert _total(picture(True, 0.0)) < _total(picture(False, 0.0)) * 0.8
        flow = ORDER_FX_STYLE['arrows']['flow']
        still = pygame.image.tostring(picture(True, 0.0), 'RGB')
        assert pygame.image.tostring(picture(True, 0.3 / flow), 'RGB') == still
        moving = pygame.image.tostring(picture(False, 0.0), 'RGB')
        assert pygame.image.tostring(picture(False, 0.3 / flow), 'RGB') != moving

    def test_a_cancelled_arrow_fizzles_bead_by_bead(self, light):
        from ui.effects.order_fx_effect import _fizzled
        beads = list(range(60))
        assert _fizzled(beads, 1.0) == beads
        lit = [len(_fizzled(beads, fade)) for fade in (0.9, 0.6, 0.3, 0.05)]
        assert lit == sorted(lit, reverse=True) and lit[0] > 40 and lit[-1] < 10
        # A bead that has gone out stays out as the arrow fades further
        assert set(_fizzled(beads, 0.3)) <= set(_fizzled(beads, 0.6))

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

    def test_the_ring_takes_the_order_kinds_colour(self, light):
        ring = 14 + ORDER_FX_STYLE['reticle']['gap'] * RADIUS
        colours = {}
        for kind in ('attack', 'own', 'ally'):
            screen = _blank()
            light.draw_reticle(_view(screen), 200, 150, 14, kind, clock=0.0)
            colours[kind] = screen.get_at((200 + int(ring), 150))[:3]
        r, g, b = colours['attack']
        assert r > g and r > b
        r, g, b = colours['own']
        assert b > r and b > g
        r, g, b = colours['ally']
        assert g > r and g > b

    def test_only_an_attack_has_ticks(self, light):
        reticle = ORDER_FX_STYLE['reticle']
        ticks = reticle['ticks']
        ring = 14 + reticle['gap'] * RADIUS
        mid = ring + (ticks['gap'] + ticks['travel'] * 0.5 + ticks['length'] * 0.5) * RADIUS
        for kind, has_ticks in (('attack', True), ('own', False), ('ally', False)):
            screen = _blank()
            light.draw_reticle(_view(screen), 200, 150, 14, kind, clock=0.0)
            assert (_light_at(screen, 200 + mid, 150) > 40) == has_ticks, kind


# ========================================
# Styles
# ========================================

class TestStyles:

    def test_both_looks_have_a_style_and_unknown_looks_get_2d(self):
        assert set(ORDER_FX_STYLES) == {'2d', '3d'}
        assert get_order_fx_style('elsewhere') is ORDER_FX_STYLES['2d']

    def test_every_arrow_kind_and_reticle_kind_has_a_colour(self):
        assert set(ORDER_FX_STYLE['arrows']['kinds']) == {'attack', 'own', 'ally', 'hovered', 'cancelled'}
        assert set(ORDER_FX_STYLE['reticle']['kinds']) == {'attack', 'own', 'ally'}

    def test_prewarm_builds_the_arrow_and_ring_sprites(self):
        light = OrderLight()
        light.prewarm(range(16, 25))
        built = light.glow.sprites_built
        view = _view(_blank(), radius=20)
        light.begin_frame()
        light.draw_arrows(view, [OrderArrow([(40, 150), (360, 150)])], 0.0)
        assert light.glow.sprites_built == built


# ========================================
# Game integration
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


@pytest.fixture
def home(game):
    """A territory of player 0 near the screen centre with an army and a Barracks on plot 0,
    and its neighbours with armies of player 1; the selection and orders are undone afterwards."""
    import map_data
    gs = game.game_state
    width, height = game.screen.get_size()
    territory = min((t for t in game.scaled_centers if game.scaled_plots.get(t)),
                    key=lambda t: (game.world_to_screen(game.scaled_centers[t])[0] - width / 2) ** 2
                    + (game.world_to_screen(game.scaled_centers[t])[1] - height / 2) ** 2)
    for t, owner in [(territory, 0)] + [(n, 1) for n in map_data.get_neighbors(territory)]:
        gs.territory_owners[t] = owner
        gs.armies[t] = 6
        gs.territory_garrisons[t] = {owner: {'unmoved': 6, 'moved': 0}}
    gs.buildings.setdefault(territory, {})[0] = 'Barracks'
    gs._territory_owners_version += 1
    yield territory
    gs.selected_army = None
    gs.movement_orders.clear()
    gs.cancelling_arrows.clear()
    game.selected_barracks = None
    game.sidebar_hovered_route = None


def _spy(monkeypatch, light, name):
    calls = []
    real = getattr(light, name)

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(light, name, spy)
    return calls


def _zoom(game, zoom, centre=None):
    """Set the camera zoom, centred on the world point `centre` (if given), as the game does."""
    game.camera.zoom = zoom
    if centre is not None:
        width, height = game.screen.get_size()
        game.camera.offset = [centre[0] - width / 2.0 / zoom, centre[1] - height / 2.0 / zoom]
    game.camera.clamp_to_bounds()
    game.camera_zoom = game.camera.zoom
    game.camera_offset = list(game.camera.offset)
    game.cached_zoom_level = None


class TestSelectionInGame:

    def test_selected_army_is_ringed_round_its_circle(self, game, home, monkeypatch):
        from config.constants import ARMY_CIRCLE_RADIUS, ARMY_CIRCLE_DRAW_SCALE, ARMY_CIRCLE_DRAW_LIFT
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_selection')
        game.game_state.selected_army = (home, 6)
        game.draw()
        assert len(calls) == 1
        view, x, y, radius, clock = calls[0]
        ui_scale = game.get_ui_scale_factor()
        cx, cy = game.world_to_screen(game.scaled_centers[home])
        assert (x, y) == (cx, cy - int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT))
        assert radius == int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)

    @pytest.mark.parametrize('which', ['min', 'max'])
    def test_selected_building_ring_follows_the_plot_radius(self, game, home, monkeypatch, which):
        from config.constants import EMPTY_PLOT_RADIUS
        _zoom(game, game.camera.min_zoom if which == 'min' else game.camera.max_zoom,
              centre=game.scaled_plots[home][0])
        try:
            calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_selection')
            game.selected_barracks = (home, 0)
            game.draw()
            assert len(calls) == 1
            # The plot radius itself - no second ui_scale (the old ring floated off the plot)
            assert calls[0][3] == int(EMPTY_PLOT_RADIUS * game.get_ui_scale_factor())
        finally:
            _zoom(game, game.camera.min_zoom)

    def test_selection_ring_animates_from_the_plot_effect_clock(self, game, home, monkeypatch):
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_selection')
        game.game_state.selected_army = (home, 6)
        game.draw()
        game.update_map_effects(0.25)
        game.draw()
        assert calls[1][4] == pytest.approx(calls[0][4] + 0.25)


class _SimPlanning:
    """The parts of SimultaneousGameState the arrows read, in the planning phase."""

    sim_phase = 'planning'

    def __init__(self, player_orders):
        self.player_orders = player_orders


class TestArrowsInGame:

    def test_one_arrow_per_route_with_the_summed_count(self, game, home, monkeypatch):
        import map_data
        from game_state import MovementOrder
        gs = game.game_state
        target = sorted(map_data.get_neighbors(home))[0]
        gs.movement_orders.extend([MovementOrder(home, target, 2, 0), MovementOrder(home, target, 3, 0)])
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_arrows')
        game.map_renderer.draw_movement_arrows()
        arrows = calls[0][1]
        assert len(calls) == 1 and len(arrows) == 1
        arrow = arrows[0]
        assert (arrow.kind, arrow.count) == ('attack', 5)   # into player 1's territory
        assert arrow.points == (game.scaled_centers[home], game.scaled_centers[target])

    @pytest.mark.parametrize('owner, kind', [(1, 'attack'), (-1, 'attack'), (0, 'own'), (2, 'ally')])
    def test_arrows_take_the_order_kind(self, game, home, monkeypatch, owner, kind):
        import map_data
        from game_state import MovementOrder
        gs = game.game_state
        target = sorted(map_data.get_neighbors(home))[0]
        monkeypatch.setattr(gs, 'player_teams', [0, 1, 0])   # player 2 allied to 0
        monkeypatch.setitem(gs.territory_owners, target, owner)
        gs.movement_orders.append(MovementOrder(home, target, 2, 0))
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_arrows')
        game.map_renderer.draw_movement_arrows()
        assert calls[0][1][0].kind == kind
        # The Action Queue card agrees
        assert game.ui_renderer._order_kind(0, target) == kind

    def test_a_two_hop_takes_its_final_targets_kind(self, game, home, monkeypatch):
        import map_data
        from game_state import MovementOrder
        gs = game.game_state
        via = sorted(map_data.get_neighbors(home))[0]
        onward = next(t for t in sorted(map_data.get_neighbors(via)) if t != home)
        monkeypatch.setitem(gs.territory_owners, via, 0)
        monkeypatch.setitem(gs.territory_owners, onward, 0)
        gs.movement_orders.append(MovementOrder(home, onward, 2, 0, intermediate_territory=via))
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_arrows')
        game.map_renderer.draw_movement_arrows()
        assert calls[0][1][0].kind == 'own'

    def test_lift_matches_the_army_circle(self, game, home, monkeypatch):
        import map_data
        from game_state import MovementOrder
        from config.constants import ARMY_CIRCLE_RADIUS, ARMY_CIRCLE_DRAW_LIFT
        lifts = []
        light = game.map_renderer.order_light
        real = light.draw_arrows
        monkeypatch.setattr(light, 'draw_arrows',
                            lambda view, arrows, clock, lift=0, badge=None: lifts.append(lift)
                            or real(view, arrows, clock, lift=lift, badge=badge))
        game.game_state.movement_orders.append(
            MovementOrder(home, sorted(map_data.get_neighbors(home))[0], 2, 0))
        game.map_renderer.draw_movement_arrows()
        assert lifts == [int(ARMY_CIRCLE_RADIUS * game.get_ui_scale_factor() * ARMY_CIRCLE_DRAW_LIFT)]

    def test_two_hop_order_bends_through_its_waypoint(self, game, home, monkeypatch):
        import map_data
        from game_state import MovementOrder
        via = sorted(map_data.get_neighbors(home))[0]
        onward = next(t for t in sorted(map_data.get_neighbors(via)) if t != home)
        game.game_state.movement_orders.append(
            MovementOrder(home, onward, 2, 0, intermediate_territory=via))
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_arrows')
        game.map_renderer.draw_movement_arrows()
        assert calls[0][1][0].points[1] == game.scaled_centers[via]

    def test_arrow_starts_at_the_players_flag_when_garrisons_share_a_territory(self, game, home, monkeypatch):
        import map_data
        from game_state import MovementOrder
        gs = game.game_state
        gs.territory_garrisons[home] = {0: {'unmoved': 4, 'moved': 0}, 1: {'unmoved': 3, 'moved': 0}}
        try:
            gs.movement_orders.append(MovementOrder(home, sorted(map_data.get_neighbors(home))[0], 2, 0))
            calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_arrows')
            game.map_renderer.draw_movement_arrows()
            cx, cy = game.scaled_centers[home]
            flags = gs.get_flag_positions_for_territory(home, cx, cy, 2)
            assert calls[0][1][0].points[0] == tuple(float(v) for v in flags[0])
        finally:
            gs.territory_garrisons[home] = {0: {'unmoved': 6, 'moved': 0}}

    def test_cancelled_orders_shake_and_fade_then_go(self, game, home, monkeypatch):
        import time
        import map_data
        from config.constants import ARROW_CANCEL_DURATION
        gs = game.game_state
        target = sorted(map_data.get_neighbors(home))[0]
        gs.cancelling_arrows.extend([
            {'from_territory': home, 'to_territory': target, 'army_count': 3,
             'start_time': time.time() - ARROW_CANCEL_DURATION / 2},
            {'from_territory': home, 'to_territory': target, 'army_count': 4,
             'start_time': time.time() - ARROW_CANCEL_DURATION * 2},   # over
        ])
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_arrows')
        game.map_renderer.draw_movement_arrows()
        arrows = calls[0][1]
        assert len(arrows) == 1 and arrows[0].kind == 'cancelled' and arrows[0].count == 3
        assert 0.3 < arrows[0].fade < 0.7
        assert len(gs.cancelling_arrows) == 1

    def test_simultaneous_planning_shows_allies_dimmed_and_cancels(self, game, home, monkeypatch):
        import time
        import map_data
        gs = game.game_state
        neighbours = sorted(map_data.get_neighbors(home))
        monkeypatch.setattr(gs, 'player_teams', [0, 0, 1])   # players 0 and 1 allied
        monkeypatch.setattr(game, 'sim_state', _SimPlanning({
            0: [{'type': 'movement', 'from_territory': home, 'to_territory': neighbours[0], 'army_count': 2}],
            1: [{'type': 'movement', 'from_territory': neighbours[1], 'to_territory': home, 'army_count': 3}],
            2: [{'type': 'movement', 'from_territory': neighbours[2], 'to_territory': home, 'army_count': 9}],
        }), raising=False)
        gs.cancelling_arrows.append({'from_territory': home, 'to_territory': neighbours[0], 'army_count': 1,
                                     'start_time': time.time()})
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_arrows')
        game.map_renderer.draw_movement_arrows()
        kinds = sorted((a.kind, a.count, a.allied) for a in calls[0][1])
        # Ours goes into the ally's territory (reinforce); the ally's reinforces ours and
        # is marked as an ally's; the enemy's order (player 2) is not shown; the cancel
        # animation is
        assert kinds == [('ally', 2, False), ('ally', 3, True), ('cancelled', 1, False)]


class TestReticlesInGame:

    @pytest.mark.parametrize('to_own', [False, True], ids=['attack', 'move'])
    def test_selected_armys_destinations_get_a_reticle(self, game, home, monkeypatch, to_own):
        import map_data
        from game_state import MovementOrder
        gs = game.game_state
        target = sorted(map_data.get_neighbors(home))[0]
        if to_own:
            gs.territory_owners[target] = 0
            gs.territory_garrisons[target] = {0: {'unmoved': 6, 'moved': 0}}
        gs.movement_orders.append(MovementOrder(home, target, 2, 0))
        gs.selected_army = (home, 6)
        calls = _spy(monkeypatch, game.map_renderer.order_light, 'draw_reticle')
        game.draw()
        assert [c[4] for c in calls] == ['own' if to_own else 'attack']
        # Not while the army isn't selected
        gs.selected_army = None
        calls.clear()
        game.draw()
        assert calls == []
