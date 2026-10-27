# -*- coding: utf-8 -*-
"""
Tutorial guidance in gold (tutorial guidance pass, 2026-10).

What a tutorial / campaign step points at is drawn in gold, the colour of the
player's input to give: a "click here" on a plot (OrderLight.draw_beckon), the
target territory's border light, and a glow round a highlighted button, tab or
icon (rendering/tutorial_glow.py on light_fx.GlowFrame).

The guard at the bottom: every highlight a tutorial step declares must be drawn.
Two of them (the Barracks in step 18, Select All in step 26) were declared and
never drawn, and the build buttons' highlight never reached the icon buttons.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

from ui.effects.light_fx import GlowFrame  # noqa: E402
from ui.effects.hero_fx_effect import FxView  # noqa: E402
from ui.effects.order_fx_style import ORDER_FX_STYLE, GUIDE_GOLD  # noqa: E402
from ui.effects.order_fx_effect import OrderLight  # noqa: E402

RADIUS = 20


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((400, 300))
    yield


def _blank(size=(400, 300)):
    surface = pygame.Surface(size)
    surface.fill((0, 0, 0))
    return surface


def _light_at(surface, x, y):
    return sum(surface.get_at((int(x), int(y)))[:3])


# ========================================
# Glow frame
# ========================================

class TestGlowFrame:

    @pytest.mark.parametrize('shape', ['rect', 'circle'])
    def test_light_round_the_shape_and_none_inside(self, shape):
        frames = GlowFrame(reach=8)
        glow, pad = frames.frame((60, 60), GUIDE_GOLD, GlowFrame.LEVELS, shape)
        assert glow.get_size() == (60 + 2 * pad, 60 + 2 * pad)
        centre = pad + 30
        assert _light_at(glow, centre, centre) == 0                 # the control is untouched
        assert _light_at(glow, pad - 1, centre) > 200                # a crisp line on the outline
        assert _light_at(glow, pad - 6, centre) > 0                  # a halo fading outward
        assert _light_at(glow, pad - 6, centre) < _light_at(glow, pad - 1, centre)
        r, g, b, _ = glow.get_at((pad - 1, centre))
        assert r >= g > b                                            # gold

    def test_cached_per_level_and_brighter_levels_add_more_light(self):
        frames = GlowFrame(reach=8)
        dim, _ = frames.frame((40, 30), GUIDE_GOLD, 4)
        bright, _ = frames.frame((40, 30), GUIDE_GOLD, 12)
        assert frames.frame((40, 30), GUIDE_GOLD, 4)[0] is dim
        total = lambda s: sum(pygame.image.tostring(s, 'RGB'))  # noqa: E731
        assert total(bright) > total(dim)


# ========================================
# Beckon ("click here" on a plot)
# ========================================

def _light():
    light = OrderLight()
    budgets = [light.glow._budget, light.tint._budget] + [ring._budget for ring in light._rings]
    for budget in budgets:
        budget.ms = budget.count = budget.left = 10 ** 6
    return light


def _view(screen):
    return FxView(screen, 0.0, 0.0, 1.0, RADIUS)


class TestBeckon:

    def test_gold_ring_round_the_plot_and_a_chevron_above_it(self):
        beckon = ORDER_FX_STYLE['beckon']
        screen = _blank()
        _light().draw_beckon(_view(screen), 200, 170, RADIUS, clock=0.0)
        ring = RADIUS + beckon['gap'] * RADIUS
        assert _light_at(screen, 200, 170) == 0
        r, g, b, _ = screen.get_at((200 + int(ring), 170))
        assert r > b and g > b and r + g > 300
        # The chevron's tip, above the ring (no bob at clock 0)
        tip = 170 - ring - beckon['chevron']['height'] * RADIUS
        assert _light_at(screen, 200, tip) > 150
        # ...pointing down: its arms rise to either side
        arm = beckon['chevron']['arm'] * RADIUS * 0.7
        angle = math.radians(beckon['chevron']['angle'])
        for side in (-1, 1):
            assert _light_at(screen, 200 + side * math.sin(angle) * arm, tip - math.cos(angle) * arm) > 100

    def test_pulses_close_in_on_the_ring(self):
        light = _light()
        radii = []
        real = light.beckon_ring.frame

        def spy(radius, colour, level):
            radii.append(radius)
            return real(radius, colour, level)

        light.beckon_ring.frame = spy
        pulses = ORDER_FX_STYLE['beckon']['pulses']
        for i in range(2, 18):
            light.draw_beckon(_view(_blank()), 200, 170, RADIUS, clock=pulses['period'] * i / 20.0)
        # Per frame: the pulses, then the ring; the first pulse's radius shrinks
        first = radii[::pulses['count'] + 1]
        assert first == sorted(first, reverse=True) and first[0] > first[-1] * 1.4

    def test_off_screen_beckon_draws_nothing(self):
        screen = _blank()
        _light().draw_beckon(_view(screen), -400, 150, RADIUS, clock=0.3)
        assert sum(pygame.image.tostring(screen, 'RGB')) == 0


# ========================================
# The tutorial, step by step
# ========================================

@pytest.fixture(scope='module')
def tutorial(display):
    """A game with the tutorial mission, at 1600x900."""
    pygame.display.set_mode((1600, 900))
    import map_data
    from main import Game
    from tutorial_mission import TutorialMission
    game = Game(campaign_map='assets/CampaignMaps/Campaign1Map.png')
    game.initialize_game({
        'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [0, 0],
        'player_teams': [0, 1], 'win_condition': 'Total Conquest', 'taxation_level': 0,
        'player1_territory': 'Lunedale', 'player2_territory': 'Free Cities',
    })
    game.game_state.phase = 'playing'
    mission = TutorialMission(game.game_state, game)
    game.tutorial_mission = mission
    game.game_state.tutorial_mission = mission
    map_data.set_tutorial_mission(mission)
    yield game
    mission.deactivate()
    map_data.set_tutorial_mission(None)


def _at_step(game, step_id):
    """Enter the step directly (its highlights and on_enter), on the player's turn, nothing selected."""
    mission = game.tutorial_mission
    mission.active = True
    index = next(i for i, step in enumerate(mission.steps) if step.step_id == step_id)
    mission.current_step_index = index
    mission._enter_step(index)
    gs = game.game_state
    gs.current_player = 0
    gs.turn_phase = 'planning'
    gs.selected_army = None
    gs.active_sidebar_tab = 'action_queue'
    game.selected_plot = game.selected_barracks = game.selected_keep = None
    game.show_army_composition = False
    game.selected_army_units = []
    return mission.steps[index]


def _barracks_plot(game):
    """A Barracks in Lunedale (built on its second plot if there is none)."""
    buildings = game.game_state.buildings.setdefault('Lunedale', {})
    for plot, building in buildings.items():
        if building == 'Barracks':
            return plot
    buildings[1] = 'Barracks'
    return 1


class _Drawn:
    """Records the gold guidance drawn in one frame."""

    def __init__(self, game, monkeypatch):
        self.calls = []
        glow = game.tutorial_glow
        for name in ('rect', 'circle', 'sprite'):
            real = getattr(glow, name)
            monkeypatch.setattr(glow, name, self._spy(name, real))
        light = game.map_renderer.order_light
        monkeypatch.setattr(light, 'draw_beckon', self._spy('beckon', light.draw_beckon))
        hero = game.map_renderer.hero_light
        monkeypatch.setattr(hero, 'draw_outline', self._spy('outline', hero.draw_outline))

    def _spy(self, name, real):
        def spy(*args, **kwargs):
            self.calls.append((name, args))
            return real(*args, **kwargs)
        return spy

    def kinds(self):
        return [name for name, _ in self.calls]


# Every highlight a tutorial step may declare, and how to put its control on screen
# (None: on screen as the step starts). test_every_declared_highlight_is_covered
# fails when a step declares one missing here - add its renderer and a case below
CONTEXTS = {
    'end_turn': None,
    'building_Farm': 'select the highlighted plot',
    'building_Barracks': 'select the highlighted plot',
    'barracks_Lunedale': None,
    'training_Swordsman': 'select the Barracks',
    'select_all': 'open the army',
    'sidebar_technology': None,
    'technology_tech_0_0': 'open the Technology tab',
}


def test_every_declared_highlight_is_covered(tutorial):
    declared = set()
    for step in tutorial.tutorial_mission.steps:
        declared.update(step.highlight_buttons)
    assert declared <= set(CONTEXTS), sorted(declared - set(CONTEXTS))


class TestGuidanceInTheGame:

    def test_highlighted_plot_beckons_until_selected(self, tutorial, monkeypatch):
        step = _at_step(tutorial, 5)
        territory, plot = step.highlight_plots[0]
        drawn = _Drawn(tutorial, monkeypatch)
        tutorial.draw()
        beckons = [args for name, args in drawn.calls if name == 'beckon']
        assert len(beckons) == 1
        x, y = tutorial.world_to_screen(tutorial.scaled_plots[territory][plot])
        assert (beckons[0][1], beckons[0][2]) == (int(x), int(y))
        # Selected: the "click here" gives way to the Farm button's glow (panel and map icon)
        drawn.calls.clear()
        tutorial.selected_plot = (territory, plot)
        tutorial.draw()
        assert 'beckon' not in drawn.kinds()
        assert drawn.kinds().count('circle') >= 2

    def test_step_18_marks_the_barracks(self, tutorial, monkeypatch):
        plot = _barracks_plot(tutorial)
        _at_step(tutorial, 18)
        drawn = _Drawn(tutorial, monkeypatch)
        tutorial.draw()
        beckons = [args for name, args in drawn.calls if name == 'beckon']
        x, y = tutorial.world_to_screen(tutorial.scaled_plots['Lunedale'][plot])
        assert [(b[1], b[2]) for b in beckons] == [(int(x), int(y))]

    def test_step_19_glows_round_the_swordsmen(self, tutorial, monkeypatch):
        plot = _barracks_plot(tutorial)
        _at_step(tutorial, 19)
        tutorial.selected_barracks = ('Lunedale', plot)
        drawn = _Drawn(tutorial, monkeypatch)
        tutorial.draw()
        # The portrait in the panel (the map's quick-access icons are hidden in this
        # step: it doesn't allow clicking plots)
        rects = [pygame.Rect(args[1]) for name, args in drawn.calls if name == 'rect']
        assert rects == [tutorial.train_buttons['Swordsman'].inflate(-2, -2)]

    def test_step_26_gold_target_and_select_all(self, tutorial, monkeypatch):
        gs = tutorial.game_state
        units = [{'type': 'Swordsman', 'id': i, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0}
                 for i in range(2)]
        gs.set_garrison_armies('Lunedale', 0, unmoved=2, moved=0, units=units)
        gs.sync_legacy_garrison_data('Lunedale')
        _at_step(tutorial, 26)
        tutorial.show_army_composition = True
        tutorial.army_composition_territory = 'Lunedale'
        tutorial.army_composition_player = 0
        drawn = _Drawn(tutorial, monkeypatch)
        tutorial.draw()
        outlines = [args for name, args in drawn.calls if name == 'outline']
        assert outlines and tuple(outlines[0][2]) == tuple(GUIDE_GOLD)     # Free Cities' border light
        assert drawn.kinds().count('sprite') == 1                           # Select All
        # Once units are selected, the order is the next step: Select All stops glowing
        drawn.calls.clear()
        tutorial.selected_army_units = [0, 1]
        tutorial.draw()
        assert 'sprite' not in drawn.kinds()

    def test_end_turn_glows_gold(self, tutorial, monkeypatch):
        _at_step(tutorial, 7)
        drawn = _Drawn(tutorial, monkeypatch)
        tutorial.draw()
        sprites = [args for name, args in drawn.calls if name == 'sprite']
        assert len(sprites) == 1 and pygame.Rect(sprites[0][1]) == tutorial.end_turn_button

    def test_step_36_glows_round_the_tab_and_the_technology(self, tutorial, monkeypatch):
        _at_step(tutorial, 36)
        drawn = _Drawn(tutorial, monkeypatch)
        tutorial.draw()
        tab = tutorial.sidebar_tab_buttons['technology']
        assert [pygame.Rect(args[1]) for name, args in drawn.calls if name == 'rect'] == [tab]
        drawn.calls.clear()
        tutorial.game_state.active_sidebar_tab = 'technology'
        tutorial.draw()
        rects = [pygame.Rect(args[1]) for name, args in drawn.calls if name == 'rect']
        assert tutorial.technology_buttons['tech_0_0'] in rects

    def test_no_guidance_outside_a_mission(self, tutorial, monkeypatch):
        _at_step(tutorial, 5)
        tutorial.tutorial_mission.active = False
        try:
            drawn = _Drawn(tutorial, monkeypatch)
            tutorial.draw()
            assert drawn.calls == []
        finally:
            tutorial.tutorial_mission.active = True
