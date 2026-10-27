# -*- coding: utf-8 -*-
"""
Event effects as light (event FX pass, 2026-10).

- the map markers (ui/effects/marker_fx_effect.py, styled in marker_fx_style.py):
  battle and alliance arrival markers, yours or greyed, and the army overflow warning
- a Keep -> Castle upgrade finishing (plot_fx_style 'castle_complete', played by
  the hero ability cue engine)
- the turn banner (ui/effects/turn_announcement_effect.py)
- the Master Negotiator glow (main.py draw_negotiator_glow), for its caster only
- the rising motes those use (light_fx.RisingMotes)

Unit tests draw on blank surfaces, so they need no Game; the game integration
is tested further down.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

from ui.effects.hero_fx_effect import FxView, HeroLight, HeroAbilityEffect  # noqa: E402
from ui.effects.hero_fx_style import HERO_FX_STYLE  # noqa: E402
from ui.effects.light_fx import GlowSprites, TintSprites, RisingMotes  # noqa: E402
from ui.effects.marker_fx_style import MARKER_FX_STYLE, MARKER_FX_STYLES, get_marker_fx_style  # noqa: E402
from ui.effects.marker_fx_effect import MarkerLight, MarkerState  # noqa: E402
from ui.effects.plot_fx_style import PLOT_FX_STYLES  # noqa: E402
from ui.effects import turn_announcement_effect  # noqa: E402
from ui.effects.turn_announcement_effect import TurnAnnouncementEffect  # noqa: E402

RADIUS = 20   # plot radius in px for the unit tests
CENTRE = (200, 150)


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((400, 300))
    yield


def _unbudgeted(light):
    """No per-frame time budgets: tests must not depend on speed."""
    budgets = [light.glow._budget, light.tint._budget]
    for scheme in light._all_schemes():
        budgets += [scheme.ring._budget, scheme.pulse._budget]
    for budget in budgets:
        budget.ms = budget.count = budget.left = 10 ** 6
    return light


@pytest.fixture
def light():
    return _unbudgeted(MarkerLight())


def _blank(size=(400, 300), colour=(0, 0, 0)):
    surface = pygame.Surface(size)
    surface.fill(colour)
    return surface


def _view(screen, radius=RADIUS):
    return FxView(screen, 0.0, 0.0, 1.0, radius)


def _total(surface):
    return sum(pygame.image.tostring(surface, 'RGB'))


def _channels(surface):
    """Summed (R, G, B) of a surface."""
    raw = pygame.image.tostring(surface, 'RGB')
    return sum(raw[0::3]), sum(raw[1::3]), sum(raw[2::3])


def _lit_rect(surface):
    """Bounding rect of every pixel that isn't black."""
    dark = pygame.mask.from_threshold(surface, (0, 0, 0, 255), (1, 1, 1, 255))
    dark.invert()
    rects = dark.get_bounding_rects()
    return rects[0].unionall(rects[1:]) if rects else pygame.Rect(0, 0, 0, 0)


def _marker(light, kind, greyed, radius=RADIUS, clock=1.0, appear=1.0, size=(400, 300)):
    screen = _blank(size)
    light.draw_marker(_view(screen, radius), size[0] // 2, size[1] // 2, kind, greyed, clock, 0.0, appear)
    return screen


# ========================================
# Map markers
# ========================================

class TestMarkers:

    @pytest.mark.parametrize('kind', ['battle', 'alliance'])
    @pytest.mark.parametrize('greyed', [False, True])
    def test_every_kind_and_state_draws_light_round_its_icon(self, light, kind, greyed):
        screen = _marker(light, kind, greyed)
        assert _total(screen) > 0
        # The icon on top in the middle, the light reaching out round it
        assert screen.get_at(CENTRE)[:3] != (0, 0, 0)
        reach = _lit_rect(screen)
        assert reach.width > 3 * RADIUS and reach.height > 3 * RADIUS

    @pytest.mark.parametrize('kind, strongest', [('battle', 0), ('alliance', 1)])
    def test_battles_are_red_and_alliances_green(self, light, kind, strongest):
        """The attack arrows' coral-red and the 'ally' arrows' green (owner, 2026-10-27)."""
        screen = _marker(light, kind, False)
        # Leave the (grey steel) icon out: its middle square
        pygame.draw.rect(screen, (0, 0, 0), pygame.Rect(0, 0, 3 * RADIUS, 3 * RADIUS).move(
            CENTRE[0] - 1.5 * RADIUS, CENTRE[1] - 1.5 * RADIUS))
        channels = _channels(screen)
        assert channels[strongest] == max(channels)

    @pytest.mark.parametrize('kind', ['battle', 'alliance'])
    def test_greyed_is_dimmer_and_without_colour(self, light, kind):
        """Not yours to click: ash grey and dimmer, with no pulses."""
        mine, greyed = _marker(light, kind, False), _marker(light, kind, True)
        assert _total(greyed) < _total(mine)
        r, g, b = _channels(greyed)
        assert max(r, g, b) < 1.4 * min(r, g, b)

    def test_greyed_markers_have_no_pulses(self, light, monkeypatch):
        calls = []
        monkeypatch.setattr(light, '_pulses', lambda *args: calls.append(args))
        _marker(light, 'battle', True)
        assert calls == []
        _marker(light, 'battle', False)
        assert len(calls) == 1

    def test_the_marker_grows_with_the_plot_radius(self, light):
        small = _lit_rect(_marker(light, 'battle', False, radius=16))
        large = _lit_rect(_marker(light, 'battle', False, radius=24))
        assert large.width > small.width and large.height > small.height
        assert light.click_radius(24) > light.click_radius(16)
        assert light.click_radius(16) == int(MARKER_FX_STYLE['marker']['click'] * 16)

    def test_markers_fade_in_as_they_appear(self, light):
        assert _total(_marker(light, 'battle', False, appear=0.0)) == 0
        assert (_total(_marker(light, 'battle', False, appear=0.3))
                < _total(_marker(light, 'battle', False, appear=1.0)))

    def test_markers_animate_with_the_clock(self, light):
        assert (pygame.image.tostring(_marker(light, 'battle', False, clock=1.0), 'RGB')
                != pygame.image.tostring(_marker(light, 'battle', False, clock=1.4), 'RGB'))

    def test_off_screen_markers_draw_nothing(self, light):
        screen = _blank()
        light.draw_marker(_view(screen), -500, 150, 'battle', False, 1.0)
        assert _total(screen) == 0

    def test_icons_are_cached_per_kind_greyed_and_radius(self, light):
        first = light._icon('battle', False, RADIUS)
        assert light._icon('battle', False, RADIUS) is first
        assert light._icon('battle', True, RADIUS) is not first
        assert light._icon('battle', False, RADIUS + 2).get_height() > first.get_height()

    def test_marker_state_keeps_what_the_renderer_needs(self):
        state = MarkerState(True, 1.5, 3.0)
        assert (state.greyed_out, state.phase, state.born) == (True, 1.5, 3.0)


class TestOverflow:

    def test_the_ring_surrounds_the_army_circle(self, light):
        screen = _blank()
        light.draw_overflow(_view(screen), *CENTRE, 12, 1.0)
        ring = 12 + MARKER_FX_STYLE['overflow']['gap'] * RADIUS
        assert sum(screen.get_at((int(CENTRE[0] + ring), CENTRE[1]))[:3]) > 0
        # The army circle itself is left alone
        assert screen.get_at(CENTRE)[:3] == (0, 0, 0)

    def test_amber_not_red(self, light):
        screen = _blank()
        light.draw_overflow(_view(screen), *CENTRE, 12, 1.0)
        r, g, b = _channels(screen)
        assert r > g > b


class TestStyles:

    def test_both_looks_have_a_style_and_unknown_looks_get_2d(self):
        assert set(MARKER_FX_STYLES) == {'2d', '3d'}
        assert get_marker_fx_style('nope') is MARKER_FX_STYLES['2d']

    def test_kinds_take_the_order_arrow_colours(self):
        from config.constants import COLOR_ARROW_ATTACK, COLOR_ARROW_REINFORCE, COLOR_ARROW_CANCELLED
        kinds = MARKER_FX_STYLE['kinds']
        assert kinds['battle']['colour'] == COLOR_ARROW_ATTACK
        assert kinds['alliance']['colour'] == COLOR_ARROW_REINFORCE
        assert MARKER_FX_STYLE['greyed']['colour'] == COLOR_ARROW_CANCELLED

    def test_icons_exist(self):
        for kind in MARKER_FX_STYLE['kinds'].values():
            assert os.path.exists(kind['icon'])

    def test_prewarm_builds_the_mote_sprites(self):
        light = MarkerLight()
        before = light.glow.sprites_built
        light.prewarm(range(16, 25))
        assert light.glow.sprites_built > before


# ========================================
# Castle upgrade finishing
# ========================================

class TestCastleComplete:

    @pytest.mark.parametrize('look', ['2d', '3d'])
    def test_a_gold_cue_timeline_at_the_plot(self, look):
        spec = PLOT_FX_STYLES[look]['castle_complete']
        effect = HeroAbilityEffect(HeroLight({}, HERO_FX_STYLE), spec, {'keep': (200.0, 150.0)}, 1)
        kinds = {type(cue).__name__ for cue in effect.cues}
        assert {'_RaysCue', '_FlareCue', '_RingCue', '_SparksCue'} <= kinds
        assert 1.0 < effect.duration < 3.0
        r, g, b = spec['colour']
        assert r > g > b   # gold

    def test_it_draws_and_ends(self):
        hero_light = HeroLight({}, HERO_FX_STYLE)
        effect = HeroAbilityEffect(hero_light, PLOT_FX_STYLES['2d']['castle_complete'],
                                   {'keep': (200.0, 150.0)}, 1)
        screen = _blank()
        for _ in range(10):
            hero_light.begin_frame()
            effect.update(0.05)
            effect.render_under(_view(screen))
            effect.render_over(_view(screen))
        assert _total(screen) > 0
        effect.update(effect.duration)
        assert effect.is_finished()


# ========================================
# Turn banner
# ========================================

class TestTurnBanner:

    def test_the_timeline_is_unchanged(self):
        effect = TurnAnnouncementEffect(1600, 900, player_number=1)
        assert effect.total_duration == pytest.approx(1.5)
        assert (effect.explosion_duration, effect.pause_duration, effect.recede_duration) == \
            pytest.approx((0.375, 0.375, 0.75))

    def test_on_complete_is_called_once_at_the_end(self):
        calls = []
        effect = TurnAnnouncementEffect(1600, 900, player_number=1, on_complete=lambda: calls.append(1))
        effect.update(1.4)
        assert calls == [] and not effect.is_finished()
        effect.update(0.2)
        effect.update(0.2)
        assert calls == [1] and effect.is_finished()

    @pytest.mark.parametrize('kwargs, text', [
        ({'custom_text': 'Turn 3', 'player_name': 'Empire'}, 'Turn 3'),
        ({'player_name': 'Empire', 'player_number': 2}, "Empire's Turn"),
        ({'player_number': 2}, "Player 2's Turn"),
    ])
    def test_text_rules(self, kwargs, text):
        assert TurnAnnouncementEffect(1600, 900, **kwargs).text == text

    @pytest.mark.parametrize('width', [1280, 1600, 1920])
    def test_a_very_long_name_still_fits_on_screen(self, width):
        name = 'The Most Serene Republic of the Azincournean Highlands'
        effect = TurnAnnouncementEffect(width, width * 9 // 16, player_name=name)
        assert effect.banner.get_width() <= width * turn_announcement_effect.MAX_BANNER_WIDTH

    def test_the_banner_grows_in_holds_and_fades(self):
        effect = TurnAnnouncementEffect(1600, 900, player_name='Empire')
        effect.update(0.05)
        growing = effect._phase()
        effect.update(0.5)
        held = effect._phase()
        effect.update(0.7)
        fading = effect._phase()
        assert growing[0] < 1.0 and held == (1.0, 1.0, 1.0)
        assert fading[0] == 1.0 and fading[1] < 0.5 and fading[2] < 0.5

    def test_it_darkens_the_screen_and_draws_the_banner(self):
        screen = _blank((800, 450), (200, 180, 140))
        effect = TurnAnnouncementEffect(800, 450, player_name='Empire')
        effect.update(0.5)
        for _ in range(8):   # sprites build within the frame budget
            effect.render(screen)
        corner = screen.get_at((5, 5))[:3]
        assert sum(corner) < sum((200, 180, 140)) / 2
        # Gold text on dark parchment in the middle
        assert any(screen.get_at((x, 225))[0] > 180 for x in range(250, 550))

    def test_a_finished_banner_draws_nothing(self):
        screen = _blank((800, 450), (200, 180, 140))
        effect = TurnAnnouncementEffect(800, 450, player_name='Empire')
        effect.update(2.0)
        effect.render(screen)
        assert screen.get_at((5, 5))[:3] == (200, 180, 140)
        effect.cleanup()


# ========================================
# Rising motes
# ========================================

class TestRisingMotes:

    STYLE = {'count': 30, 'life': (1.0, 2.0), 'rise': 20.0, 'sway': 3.0, 'size': (8.0, 12.0),
             'tint': 80, 'tint_size': 1.6}

    def test_motes_rise_from_their_spawn_area(self):
        motes = RisingMotes(self.STYLE, 'test')
        glow, tint = GlowSprites(), TintSprites()
        area = pygame.Rect(150, 150, 100, 40)
        screen = _blank()
        for _ in range(6):   # sprites build within the frame budget
            glow.begin_frame()
            tint.begin_frame()
            motes.draw(screen, glow, (255, 200, 80), 0.7, 1.0,
                       lambda a, b, i: (area.x + a * area.w, area.y + b * area.h), tint, (255, 180, 30))
        lit = _lit_rect(screen)
        assert lit.width > 0
        # Up to `rise` above the area, plus the sway and half the biggest halo round it
        margin = 3 + 8 + 1
        bounds = area.union(area.move(0, -20)).inflate(2 * margin, 2 * margin)
        assert bounds.contains(lit)

    def test_strength_scales_the_light_and_zero_draws_nothing(self):
        motes = RisingMotes(self.STYLE, 'test')
        totals = []
        for strength in (0.0, 0.4, 1.0):
            glow = GlowSprites()
            screen = _blank()
            for _ in range(6):
                screen.fill((0, 0, 0))
                glow.begin_frame()
                motes.draw(screen, glow, (255, 200, 80), 0.7, strength, lambda a, b, i: (200 * a, 300 * b))
            totals.append(_total(screen))
        assert totals[0] == 0 < totals[1] < totals[2]


# ========================================
# Master Negotiator glow: caster only
# ========================================

def _negotiator_shown(caster, ai=(False, True), network=False, local=None, active=True):
    from main import Game
    gs = SimpleNamespace(master_negotiator_activation_time=1000 if active else None,
                         master_negotiator_active_player=caster, player_is_ai=list(ai),
                         network_mode=network, local_player_index=local)
    return Game._negotiator_glow_shown(SimpleNamespace(game_state=gs))


class TestNegotiatorGate:
    """Shown by the rule its spell sound follows (GameState._activate_master_negotiator)."""

    def test_a_human_on_this_pc_sees_it(self):
        assert _negotiator_shown(0)

    def test_an_ai_cast_is_not_shown(self):
        assert not _negotiator_shown(1)

    def test_hot_seat_humans_see_their_own(self):
        assert _negotiator_shown(1, ai=(False, False))

    def test_multiplayer_only_the_local_caster(self):
        assert _negotiator_shown(1, ai=(False, False), network=True, local=1)
        assert not _negotiator_shown(1, ai=(False, False), network=True, local=0)

    def test_nothing_once_the_discount_ends(self):
        assert not _negotiator_shown(0, active=False)


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
    """A territory of player 0 near the screen centre with a Keep on plot 0; battles,
    the simultaneous state and Master Negotiator are undone afterwards."""
    gs = game.game_state
    width, height = game.screen.get_size()
    territory = min((t for t in game.scaled_centers if game.scaled_plots.get(t)),
                    key=lambda t: (game.world_to_screen(game.scaled_centers[t])[0] - width / 2) ** 2
                    + (game.world_to_screen(game.scaled_centers[t])[1] - height / 2) ** 2)
    gs.territory_owners[territory] = 0
    gs.buildings.setdefault(territory, {})[0] = 'Keep'
    gs._territory_owners_version += 1
    sim_state = getattr(game, 'sim_state', None)
    yield territory
    gs.turn_phase = 'planning'
    gs.pending_battles = []
    gs.master_negotiator_activation_time = None
    gs.master_negotiator_active_player = None
    game.sim_state = sim_state
    game.map_renderer.ability_effects.clear()
    game.map_renderer.battle_effects.clear()
    game.map_renderer.alliance_effects.clear()


def _spy(monkeypatch, light, name):
    calls = []
    real = getattr(light, name)

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(light, name, spy)
    return calls


def _zoom(game, zoom):
    game.camera.zoom = zoom
    game.camera.clamp_to_bounds()
    game.camera_zoom = game.camera.zoom
    game.camera_offset = list(game.camera.offset)
    game.cached_zoom_level = None


class TestMarkersInGame:

    def test_a_battle_marker_with_a_click_area_that_follows_the_zoom(self, game, home):
        from game_state import Battle
        gs = game.game_state
        gs.turn_phase = 'battles'
        gs.pending_battles = [Battle(home)]
        sizes = []
        try:
            for zoom in (game.camera.min_zoom, game.camera.max_zoom):
                _zoom(game, zoom)
                game.draw()
                assert len(game.battle_markers) == 1
                radius = game.map_renderer._plot_radius()
                assert game.battle_markers[0].width == 2 * game.map_renderer.marker_light.click_radius(radius)
                sizes.append(game.battle_markers[0].width)
        finally:
            _zoom(game, game.camera.min_zoom)
        assert sizes[1] > sizes[0]
        assert game.map_renderer.battle_effects[home].greyed_out is False

    def test_markers_animate_from_the_plot_effect_clock(self, game, home, monkeypatch):
        from game_state import Battle
        gs = game.game_state
        gs.turn_phase = 'battles'
        gs.pending_battles = [Battle(home)]
        calls = _spy(monkeypatch, game.map_renderer.marker_light, 'draw_marker')
        game.draw()
        game.update_map_effects(0.25)
        game.draw()
        assert calls[1][5] == pytest.approx(calls[0][5] + 0.25)

    def test_an_allys_alliance_marker_is_greyed(self, game, home):
        game.sim_state = SimpleNamespace(sim_phase='resolving', phase_manager=SimpleNamespace(
            pending_alliance_markers=[{'territory': home, 'players': [0, 1], 'chooser': 1}]))
        game.map_renderer.draw_alliance_markers()
        assert game.map_renderer.alliance_effects[home].greyed_out is True
        assert [m['territory'] for m in game.alliance_markers] == [home]

    def test_the_overflow_warning_rings_the_army_circle(self, game, home, monkeypatch):
        from config.constants import ARMY_CIRCLE_RADIUS, ARMY_CIRCLE_DRAW_SCALE, ARMY_CIRCLE_DRAW_LIFT
        calls = _spy(monkeypatch, game.map_renderer.marker_light, 'draw_overflow')
        game.sim_state = SimpleNamespace(overflow_territories={home: 2})
        game.map_renderer.draw_overflow_indicators()
        assert len(calls) == 1
        _, x, y, radius, _ = calls[0]
        ui_scale = game.get_ui_scale_factor()
        cx, cy = game.world_to_screen(game.scaled_centers[home])
        assert (x, y) == (cx, cy - int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_LIFT))
        assert radius == int(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_CIRCLE_DRAW_SCALE)


class TestCastleInGame:

    def test_a_finished_upgrade_plays_a_burst_of_light_that_ends(self, game, home):
        renderer = game.map_renderer
        renderer.ability_effects.clear()
        renderer.trigger_castle_upgrade_effect(home, 0)
        assert len(renderer.ability_effects) == 1
        game.draw()
        game.update_map_effects(5.0)
        assert renderer.ability_effects == []

    def test_a_missing_plot_is_ignored(self, game, home):
        game.map_renderer.trigger_castle_upgrade_effect(home, 99)
        game.map_renderer.trigger_castle_upgrade_effect('Nowhere', 0)
        assert game.map_renderer.ability_effects == []


class TestNegotiatorInGame:

    @pytest.mark.parametrize('caster, shown', [(0, True), (1, False)])
    def test_drawn_over_the_map_for_its_caster(self, game, home, monkeypatch, caster, shown):
        calls = []
        monkeypatch.setattr(game, '_negotiator_motes', None)
        real = RisingMotes.draw
        monkeypatch.setattr(RisingMotes, 'draw', lambda self, *a, **k: (calls.append(1), real(self, *a, **k)))
        gs = game.game_state
        gs.master_negotiator_activation_time = pygame.time.get_ticks() - 5000
        gs.master_negotiator_active_player = caster
        game.draw()
        assert bool(calls) is shown
