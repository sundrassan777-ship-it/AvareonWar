# -*- coding: utf-8 -*-
"""
"Not yet" toasts for what a mission has locked (2026-10-27).

The tutorial, the campaign missions and the Book of Tales lock actions step by
step (TutorialMission.is_action_allowed and its campaign twins). Those refusals
used to be silent - a greyed control was thought enough (the old rule R1) - so
ordering an attack on Damlére or clicking a greyed building did nothing at all.
Now every click a mission refuses gets the denial sound and a toast, through the
single path Game.show_action_error (texts: config/action_error_messages.py,
section G). Story moments (camera locked, the enemy's turn) stay silent: the
game drops all input then, like during the AI's turn.

The toasts are drawn below a mission's speech board while one is shown: the
board is drawn over the same corner, after them, and used to hide them.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from config.action_error_messages import ACTION_ERROR_MESSAGES, format_action_error  # noqa: E402


@pytest.fixture(scope='module')
def tutorial():
    """A game with the tutorial mission, at 1600x900."""
    pygame.init()
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


@pytest.fixture
def shown(tutorial, monkeypatch):
    """The (code, args) of every refusal toast shown."""
    calls = []
    monkeypatch.setattr(tutorial, 'show_action_error',
                        lambda code=None, message=None, **fmt: calls.append((code, fmt)))
    return calls


def _at_step(game, step_id):
    """Enter the step directly, on the player's turn, nothing selected, camera on Lunedale."""
    mission = game.tutorial_mission
    mission.active = True
    index = next(i for i, step in enumerate(mission.steps) if step.step_id == step_id)
    mission.current_step_index = index
    mission._enter_step(index)
    mission.camera_animation = None
    gs = game.game_state
    gs.current_player = 0
    gs.turn_phase = 'planning'
    gs.selected_army = None
    gs.active_sidebar_tab = 'action_queue'
    gs.sidebar_expanded = True
    game.selected_plot = game.selected_barracks = game.selected_keep = None
    game.show_army_composition = False
    game.selected_army_units = []
    _look_at(game, 'Lunedale')
    return mission.steps[index]


def _look_at(game, territory):
    """The camera at min zoom, centred on a territory (its neighbours on screen)."""
    zoom = game.camera.min_zoom
    width, height = game.screen.get_size()
    cx, cy = game.scaled_centers[territory]
    game.camera.zoom = zoom
    game.camera.offset = [cx - width / 2.0 / zoom, cy - height / 2.0 / zoom]
    game.camera.clamp_to_bounds()
    game.camera_zoom = game.camera.zoom
    game.camera_offset = list(game.camera.offset)
    game.cached_zoom_level = None


def _screen(game, world):
    x, y = game.world_to_screen(world)
    return int(x), int(y)


def _text(code, **fmt):
    return format_action_error(code, **fmt)


def _plot(game, building):
    """A Lunedale plot holding this building (built on a free plot if there is none)."""
    buildings = game.game_state.buildings.setdefault('Lunedale', {})
    for plot, name in buildings.items():
        if name == building:
            return plot
    plot = next(i for i in range(len(game.scaled_plots['Lunedale'])) if i not in buildings)
    buildings[plot] = building
    return plot


# ========================================
# The texts
# ========================================

class TestTexts:

    @pytest.mark.parametrize('code, fmt, text', [
        ('target_blocked', {'territory': 'Damlére'}, "Cannot target Damlére yet!"),
        ('mission_build_locked', {'building': 'Mine'}, "Mine cannot be built yet!"),
        ('mission_train_locked', {'units': 'Archers'}, "Archers cannot be trained yet!"),
        ('mission_end_turn_locked', {}, "Cannot end the turn yet!"),
        ('mission_research_locked', {'tech': 'Siege Works'}, "Siege Works cannot be researched yet!"),
        ('mission_tab_locked', {'tab': 'Heroes'}, "The Heroes tab is not available yet!"),
        ('mission_heroes_locked', {}, "Heroes cannot be trained in this mission!"),
        ('mission_locked', {}, "Not available yet!"),
    ])
    def test_one_short_line_each(self, code, fmt, text):
        assert code in ACTION_ERROR_MESSAGES
        assert _text(code, **fmt) == text


# ========================================
# Game-state locks (every input path shares them)
# ========================================

class TestGameStateLocks:

    def test_a_locked_route_sets_target_blocked(self, tutorial):
        _at_step(tutorial, 26)
        gs = tutorial.game_state
        units = [{'type': 'Swordsman', 'id': i, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0}
                 for i in range(2)]
        gs.set_garrison_armies('Lunedale', 0, unmoved=2, moved=0, units=units)
        gs.sync_legacy_garrison_data('Lunedale')
        assert not gs.add_movement_order_for_units('Lunedale', 'Damlére', [0, 1], player=0)
        assert (gs.last_action_error, gs.last_action_error_args) == ('target_blocked', {'territory': 'Damlére'})

    def test_any_mission_lock_names_the_building_or_unit(self):
        """The codes don't depend on the tutorial: a campaign mission's lock (Mission 2's
        Keep) gives the same toast."""
        from game_state import GameState
        gs = GameState(num_players=2, player_is_ai=[False, True], player_ai_difficulty=[1, 1],
                       skip_setup_phase=True)
        gs.tutorial_mission = SimpleNamespace(
            is_action_allowed=lambda action, **k: k.get('building_type') != 'Keep' and k.get('unit_type') != 'Captain')
        territory = sorted(gs.territory_owners)[0]
        gs.territory_owners[territory] = 0
        assert not gs.start_construction(territory, 0, 'Keep')
        assert (gs.last_action_error, gs.last_action_error_args) == ('mission_build_locked', {'building': 'Keep'})
        assert not gs.start_training(territory, 0, 'Captain')
        assert (gs.last_action_error, gs.last_action_error_args) == ('mission_train_locked', {'units': 'Captains'})


# ========================================
# The tutorial, click by click
# ========================================

class TestTutorialRefusals:

    def test_attacking_damlere_at_step_26(self, tutorial, shown):
        _at_step(tutorial, 26)
        gs = tutorial.game_state
        units = [{'type': 'Swordsman', 'id': i, 'status': 'ready', 'order': None, 'xp': 0, 'level': 0}
                 for i in range(2)]
        gs.set_garrison_armies('Lunedale', 0, unmoved=2, moved=0, units=units)
        gs.sync_legacy_garrison_data('Lunedale')
        tutorial.show_army_composition = True
        tutorial.army_composition_territory = 'Lunedale'
        tutorial.army_composition_player = 0
        tutorial.selected_army_units = [0, 1]
        tutorial.handle_right_click(_screen(tutorial, tutorial.scaled_centers['Damlére']))
        assert shown == [('target_blocked', {'territory': 'Damlére'})]
        assert not gs.movement_orders
        # Free Cities, the step's target, is taken without a word
        shown.clear()
        tutorial.handle_right_click(_screen(tutorial, tutorial.scaled_centers['Free Cities']))
        assert shown == [] and gs.movement_orders

    def test_a_greyed_building_at_step_5(self, tutorial, shown):
        step = _at_step(tutorial, 5)
        territory, plot = step.highlight_plots[0]
        tutorial.selected_plot = (territory, plot)
        tutorial.draw()
        tutorial.mouse.handle_left_click(tutorial.building_buttons['Mine'].center)
        assert shown == [('mission_build_locked', {'building': 'Mine'})]
        # The Farm the step asks for is built
        shown.clear()
        tutorial.mouse.handle_left_click(tutorial.building_buttons['Farm'].center)
        assert shown == []
        tutorial.game_state.under_construction.get(territory, {}).pop(plot, None)

    def test_a_locked_unit_at_steps_19_and_37(self, tutorial, shown):
        plot = _plot(tutorial, 'Barracks')
        _at_step(tutorial, 19)
        tutorial.selected_barracks = ('Lunedale', plot)
        tutorial.draw()
        tutorial.mouse.handle_left_click(tutorial.train_buttons['Archer'].center)
        assert shown == [('mission_train_locked', {'units': 'Archers'})]
        shown.clear()
        _at_step(tutorial, 37)
        tutorial._try_start_training('Lunedale', plot, 'Captain')
        assert shown == [('mission_train_locked', {'units': 'Captains'})]

    def test_end_turn_before_the_step_asks_for_it(self, tutorial, shown):
        _at_step(tutorial, 6)
        tutorial.draw()
        tutorial.mouse.handle_left_click(tutorial.end_turn_button.center)
        assert shown == [('mission_end_turn_locked', {})]

    def test_a_locked_tab(self, tutorial, shown):
        _at_step(tutorial, 6)
        tutorial.draw()
        tutorial.mouse.handle_left_click(tutorial.sidebar_tab_buttons['heroes'].center)
        assert shown == [('mission_tab_locked', {'tab': 'Heroes'})]
        assert tutorial.game_state.active_sidebar_tab == 'action_queue'

    def test_a_locked_technology(self, tutorial, shown):
        _at_step(tutorial, 37)
        tutorial.game_state.active_sidebar_tab = 'technology'
        tutorial.draw()
        locked = next(tech_id for tech_id in tutorial.technology_buttons if tech_id.startswith('tech_2_'))
        tutorial.handle_technology_tab_click(tutorial.technology_buttons[locked].center)
        name = next(t['name'] for t in tutorial.game_state.technologies if t['id'] == locked)
        assert shown == [('mission_research_locked', {'tech': name})]

    def test_a_plot_the_step_does_not_use(self, tutorial, shown):
        farm = _plot(tutorial, 'Farm')
        _at_step(tutorial, 18)
        tutorial.draw()
        tutorial.mouse.handle_left_click(_screen(tutorial, tutorial.scaled_plots['Lunedale'][farm]))
        assert shown == [('mission_locked', {})]

    def test_cancelling_construction_while_locked(self, tutorial, shown, monkeypatch):
        # Lunedale's plots free again (earlier tests built on them), so step 13 has one
        monkeypatch.setitem(tutorial.game_state.buildings, 'Lunedale', {})
        step = _at_step(tutorial, 13)
        territory, plot = step.highlight_plots[0]
        tutorial.game_state.under_construction.setdefault(territory, {})[plot] = ('Barracks', 1, 50)
        try:
            tutorial.selected_plot = (territory, plot)
            tutorial.draw()
            assert tutorial.cancel_button is not None
            tutorial.mouse.handle_left_click(tutorial.cancel_button.center)
            assert shown == [('mission_locked', {})]
            assert plot in tutorial.game_state.under_construction[territory]
        finally:
            tutorial.game_state.under_construction[territory].pop(plot, None)

    def test_collapsing_the_sidebar(self, tutorial, shown):
        _at_step(tutorial, 6)
        tutorial.draw()
        tutorial.mouse.handle_left_click(tutorial.sidebar_toggle_button.center)
        assert shown == [('mission_locked', {})] and tutorial.game_state.sidebar_expanded
        shown.clear()
        assert not tutorial._handle_sidebar_hotkey()                              # F2
        assert shown == [('mission_locked', {})]


class TestStillSilent:

    def test_story_steps_drop_all_input(self, tutorial):
        """While the Thunder Priest talks with the camera locked, or the enemy moves,
        the game drops every input before any toast could be raised (main.py run loop)."""
        mission = tutorial.tutorial_mission
        for step in mission.steps:
            if not step.allowed_actions:
                _at_step(tutorial, step.step_id)
                assert not mission.is_action_allowed('camera'), step.step_id

    def test_a_clouded_territory(self, tutorial, shown):
        from tutorial_mission import TUTORIAL_TERRITORIES
        _at_step(tutorial, 26)
        lx, ly = tutorial.scaled_centers['Lunedale']
        hidden = min((t for t in tutorial.scaled_centers if t not in TUTORIAL_TERRITORIES),
                     key=lambda t: (tutorial.scaled_centers[t][0] - lx) ** 2
                     + (tutorial.scaled_centers[t][1] - ly) ** 2)
        assert not tutorial.tutorial_mission.is_territory_interactive(hidden)
        tutorial.show_army_composition = True
        tutorial.army_composition_territory = 'Lunedale'
        tutorial.army_composition_player = 0
        tutorial.selected_army_units = [0]
        tutorial.handle_right_click(_screen(tutorial, tutorial.scaled_centers[hidden]))
        assert shown == []


# ========================================
# Toasts under the speech board
# ========================================

class TestToastPlacement:

    def test_below_the_board_while_one_is_shown(self, tutorial):
        _at_step(tutorial, 5)
        board = tutorial.tutorial_mission.transmission_overlay
        assert board is not None
        top = tutorial._notification_top()
        assert top == board.visible_bottom() + 6
        assert top > board.body_y + board.body_height * 0.5                     # really below it
        _at_step(tutorial, 8)                                                     # no speech
        assert tutorial._notification_top() is None

    def test_the_toast_is_drawn_from_that_top(self, tutorial):
        from ui.effects.chat_notification_effect import ChatNotificationEffect
        effect = tutorial.chat_notification_effect
        effect._notifications.clear()
        effect.add_system_notification("Not available yet!")
        surface = pygame.Surface(tutorial.screen.get_size())
        surface.fill((0, 0, 0))
        effect.render(surface, top=300)
        rows = [y for y in range(surface.get_height()) if surface.get_at((40, y))[:3] != (0, 0, 0)]
        assert rows and 299 <= rows[0] <= 304
        effect._notifications.clear()
        assert isinstance(effect, ChatNotificationEffect)

    def test_the_campaign_board_knows_its_bottom_too(self, tutorial):
        from campaign_utils import TransmissionOverlay
        board = TransmissionOverlay(1600, 900, "Hello", 40, speaker="Herald")
        assert board.body_y < board.visible_bottom() <= board.body_y + board.body_height


# ========================================
# Two fixes found on the way
# ========================================

class TestFixes:

    def test_steps_37_and_38_let_a_keep_be_selected(self, tutorial):
        mission = tutorial.tutorial_mission
        _at_step(tutorial, 37)
        assert mission.is_action_allowed('click_keep')
        _at_step(tutorial, 26)
        assert not mission.is_action_allowed('click_keep')

    def test_the_training_ring_shows_when_its_clicks_are_taken(self, tutorial, monkeypatch):
        """Steps 18-19 take quick-access training clicks ('click_barracks') but used to
        hide the ring (it followed 'click_plots'): invisible but clickable."""
        plot = _plot(tutorial, 'Barracks')
        _at_step(tutorial, 19)
        tutorial.selected_barracks = ('Lunedale', plot)
        circles = []
        glow = tutorial.tutorial_glow
        real = glow.circle
        monkeypatch.setattr(glow, 'circle', lambda *a, **k: circles.append(a) or real(*a, **k))
        tutorial.draw()
        # The ring is drawn, the Swordsman icon in it glowing gold
        assert len(circles) == 1
