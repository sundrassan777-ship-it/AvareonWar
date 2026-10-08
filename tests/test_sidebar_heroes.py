# -*- coding: utf-8 -*-
"""
Sidebar overhaul P4 — Heroes tab cards and the hero-ability logic shared with the
bottom-bar Hero UI (get_hero_ability_status / draw_hero_ability_icon /
try_cast_hero_ability).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERO = 'Aidam Narn'
TRAINEE = 'Erec Silvyr'


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


@pytest.fixture
def game(pygame_display):
    from main import Game
    g = Game()
    g.initialize_game({'num_players': 2, 'player_is_ai': [False, True], 'player_ai_difficulty': [None, 1]})
    g.apply_display_settings(1600, 900, False)
    gs = g.game_state
    gs.phase = 'playing'
    gs.turn_phase = 'planning'
    gs.current_player = 0
    g.tutorial_mission = None
    territories = list(g.scaled_polygons)
    for i, t in enumerate(territories):
        gs.territory_owners[t] = i % 2
    own = [t for t in territories if gs.territory_owners[t] == 0]
    gs.heroes.setdefault(0, {})[HERO] = {'keep_territory': own[0], 'keep_plot': 0, 'status': 'active'}
    gs.hero_ownership[0].add(HERO)
    gs.hero_training_queue.setdefault(own[1], {})[0] = (TRAINEE, 1, 200)
    gs.active_sidebar_tab = 'heroes'
    g.mouse_pos = (0, 0)
    return g


def _ability(game, index):
    return game.game_state.HERO_TYPES[HERO]['abilities'][index]


def _active_index(game):
    return next(i for i, a in enumerate(game.game_state.HERO_TYPES[HERO]['abilities']) if a['type'] == 'active')


# ============================================================================
# SHARED STATUS
# ============================================================================

class TestAbilityStatus:

    def test_ready_cooldown_silence_passive(self, game):
        gs = game.game_state
        i = _active_index(game)
        assert gs.get_hero_ability_status(0, HERO, i)['castable']
        gs.hero_ability_cooldowns.setdefault(0, {}).setdefault(HERO, {})[_ability(game, i)['name']] = 2
        status = gs.get_hero_ability_status(0, HERO, i)
        assert status['cooldown'] == 2 and not status['castable']
        gs.hero_ability_cooldowns[0][HERO] = {}
        gs.hero_silence_status[0] = 1
        assert not gs.get_hero_ability_status(0, HERO, i)['castable']
        passive = [k for k, a in enumerate(gs.HERO_TYPES[HERO]['abilities']) if a['type'] == 'passive']
        for k in passive:
            assert not gs.get_hero_ability_status(0, HERO, k)['castable']
        assert gs.get_hero_ability_status(0, HERO, 9) is None


# ============================================================================
# THE HEROES TAB
# ============================================================================

class TestHeroCards:

    def test_cards_and_rects(self, game):
        game.draw_order_sidebar()
        assert HERO in game.hero_selection_buttons
        assert TRAINEE not in game.hero_selection_buttons      # training cards aren't selectable
        assert {(HERO, i) for i in range(3)} <= set(game.sidebar_hero_ability_buttons)
        assert HERO in game.hero_portrait_rects

    def test_training_progress(self, game):
        entries = game.ui_renderer._hero_entries(0)
        training = [info for kind, hero, info in entries if kind == 'training']
        total = game.game_state.HERO_TYPES[TRAINEE]['training_time']
        assert training == [{'keep': training[0]['keep'], 'remaining': 1, 'total': total}]

    def test_card_click_selects_and_flashes(self, game):
        game.draw_order_sidebar()
        rect = game.hero_selection_buttons[HERO]
        portrait = game.hero_portrait_rects[HERO]
        game.mouse.handle_left_click(portrait.center)     # on the card, off the icons
        assert game.selected_hero == HERO
        assert game.clicked_element == ('sidebar_hero_card', HERO)
        assert rect.collidepoint(portrait.center)

    def test_scrolls_when_cards_do_not_fit(self, game):
        gs = game.game_state
        own = [t for t, o in gs.territory_owners.items() if o == 0]
        for i, hero in enumerate(['Halon Nextroy', 'Seledra Rennervail', 'Vearen Asford']):
            gs.heroes[0][hero] = {'keep_territory': own[2 + i], 'keep_plot': 0, 'status': 'active'}
        game.draw_order_sidebar()
        assert game.sidebar_scroll['heroes'].max_offset > 0


class TestSidebarCasting:

    def _click_icon(self, game, index):
        game.draw_order_sidebar()
        game.mouse.handle_left_click(game.sidebar_hero_ability_buttons[(HERO, index)].center)

    def test_targeted_ability_enters_targeting_mode(self, game, monkeypatch):
        i = _active_index(game)
        monkeypatch.setattr(game.game_state, 'activate_hero_ability', lambda h, k: 'requires_targeting')
        self._click_icon(game, i)
        assert game.ability_targeting_active
        assert (game.ability_targeting_hero, game.ability_targeting_ability_index) == (HERO, i)
        assert game.clicked_element == ('sidebar_hero_ability', (HERO, i))

    def test_immediate_ability_plays_its_effect(self, game, monkeypatch):
        i = _active_index(game)
        effects = []
        monkeypatch.setattr(game.game_state, 'activate_hero_ability', lambda h, k: True)
        monkeypatch.setattr(game.map_renderer, 'trigger_ability_effect', lambda *a: effects.append(a))
        self._click_icon(game, i)
        assert effects and effects[0][0] == _ability(game, i)['name']

    def test_refusal_shows_its_message(self, game, monkeypatch):
        i = _active_index(game)
        shown = []
        game.game_state.last_action_error = None
        monkeypatch.setattr(game.game_state, 'activate_hero_ability', lambda h, k: 'Keep territory is full')
        monkeypatch.setattr(game, 'show_action_error', lambda *a, **k: shown.append(k.get('message')))
        self._click_icon(game, i)
        assert shown == ['Keep territory is full']

    def test_no_cast_when_it_is_not_your_turn(self, game, monkeypatch):
        calls = []
        monkeypatch.setattr(game.game_state, 'activate_hero_ability', lambda h, k: calls.append(1) or True)
        game.game_state.current_player = 1           # an AI is acting
        self._click_icon(game, _active_index(game))
        assert calls == []

    def test_no_cast_on_cooldown(self, game, monkeypatch):
        i = _active_index(game)
        calls = []
        monkeypatch.setattr(game.game_state, 'activate_hero_ability', lambda h, k: calls.append(1) or True)
        game.game_state.hero_ability_cooldowns.setdefault(0, {}).setdefault(HERO, {})[_ability(game, i)['name']] = 2
        self._click_icon(game, i)
        assert calls == []


class TestBottomBarSharesTheLogic:

    def test_bottom_bar_casts_through_the_shared_helper(self, game, monkeypatch):
        i = _active_index(game)
        monkeypatch.setattr(game.game_state, 'activate_hero_ability', lambda h, k: 'requires_targeting')
        game.selected_hero = HERO
        game.draw_bottom_ui()
        rect = game.hero_ability_buttons[(HERO, i)]
        game.handle_bottom_ui_click(rect.center)
        assert game.ability_targeting_active
        assert game.clicked_element == ('hero_ability', (HERO, i))

    def test_stale_bottom_ability_rects_are_cleared(self, game):
        import pygame
        game.hero_ability_buttons = {(HERO, 0): pygame.Rect(10, 10, 20, 20)}
        game.selected_hero = None
        game.draw_bottom_ui()
        assert game.hero_ability_buttons == {}


class TestAbilityTooltip:

    def test_hover_survives_the_bottom_bar_tracker(self, game):
        """Own hover type: the bottom bar releases 'hero_ability' every frame."""
        game.draw_order_sidebar()
        game.mouse_pos = game.sidebar_hero_ability_buttons[(HERO, 0)].center
        game.draw_order_sidebar()
        game.selected_hero = HERO
        game.draw_bottom_ui()
        assert game.hover_target_button == ('sidebar_hero_ability', (HERO, 0))

    def test_tooltip_uses_the_local_player(self, game, monkeypatch):
        calls = []
        monkeypatch.setattr(game, 'draw_ability_tooltip', lambda *a, **k: calls.append((a, k)))
        game.draw_order_sidebar()
        game.mouse_pos = game.sidebar_hero_ability_buttons[(HERO, 0)].center
        game.draw_order_sidebar()
        game.show_tooltip_button = ('sidebar_hero_ability', (HERO, 0))
        game.hover_start_time_button = None
        game.update_frame_tooltips()
        assert calls and calls[-1][1].get('player') == 0

    def test_switching_tab_releases_the_hover(self, game):
        game.draw_order_sidebar()
        game.mouse_pos = game.sidebar_hero_ability_buttons[(HERO, 0)].center
        game.draw_order_sidebar()
        game.game_state.active_sidebar_tab = 'action_log'
        game.draw_order_sidebar()
        assert game.hover_target_button is None
        assert game.sidebar_hero_ability_buttons == {}
