# -*- coding: utf-8 -*-
"""
Integration tests for EnhancedBattleInterface driving BattleBarVolleyEffect.

These exercise the wiring rather than the effect's internals (which
tests/test_battle_bar_volley.py covers): a real GameState with a real pending
battle, the SETUP -> ANIMATING -> SPLASH -> REPORT state machine, the duration
handed back from the volley schedule, the retarget onto the real battle result,
and the click/key skip.

Needs a display surface because the interface loads assets with convert_alpha(),
so it opens a dummy-driver window.
"""

import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import map_data  # noqa: E402  (conftest autouse fixture handles load/cleanup)
from game_state import GameState, Battle  # noqa: E402
from config.font_manager import FontManager  # noqa: E402
from ui.effects.battle_interface import (  # noqa: E402
    BattleInterfaceState,
    EnhancedBattleInterface,
    BattleBarVolleyEffect,
    ANIMATION_MIN_DURATION,
    ANIMATION_MAX_DURATION,
)


@pytest.fixture(scope='module')
def screen():
    """Open a dummy display once so convert_alpha() works."""
    pygame.init()
    surface = pygame.display.set_mode((1600, 900))
    yield surface
    pygame.quit()


@pytest.fixture
def battle_ui(screen):
    """
    Build an EnhancedBattleInterface over a real GameState with a real battle.

    The attacker is clearly stronger, so the outcome is deterministic and no tie
    dice are rolled.
    """
    game = GameState(
        num_players=2,
        player_is_ai=[False, False],
        player_ai_difficulty=[1, 1],
        skip_setup_phase=True,
    )

    territory = map_data.get_all_territories()[0]

    def units(unit_type, count):
        return [game._make_unit(unit_type, i, 'ready') for i in range(count)]

    # Defender holds the territory
    defender_units = units('Swordsman', 6)
    game.territory_owners[territory] = 1
    game.territory_garrisons[territory] = {}
    game.add_garrison(territory, 1, unmoved=6, moved=0, units=defender_units)
    game.army_units[territory] = defender_units[:]
    game.armies[territory] = 6
    game.armies_unmoved[territory] = 6

    battle = Battle(territory)
    battle.original_owner = 1
    battle.add_army(1, 6, {'Swordsman': 6})
    battle.add_army(0, 20, {'Swordsman': 20})
    game.pending_battles = [battle]

    ui = EnhancedBattleInterface(
        screen=screen,
        game_state=game,
        battle_index=0,
        font_manager=FontManager(),
        current_player_index=0,
    )
    return ui, game, territory


def run_animation(ui, step=1.0 / 60.0, max_seconds=30.0):
    """
    Tick the interface until it leaves the ANIMATING state.

    Returns:
        Elapsed simulated seconds
    """
    elapsed = 0.0
    while ui.state == BattleInterfaceState.ANIMATING and elapsed < max_seconds:
        ui.update(step)
        elapsed += step
    assert ui.state != BattleInterfaceState.ANIMATING, "animation never ended"
    return elapsed


class TestStateMachine:
    """The interface must still walk SETUP -> ANIMATING -> ... -> REPORT."""

    def test_starts_in_setup(self, battle_ui):
        ui, _, _ = battle_ui
        assert ui.state == BattleInterfaceState.SETUP
        assert ui.particle_effect is None

    def test_resolve_click_starts_the_volley_effect(self, battle_ui):
        ui, _, _ = battle_ui
        assert ui.handle_click(ui.resolve_button_rect.center) == 'resolve'
        assert ui.state == BattleInterfaceState.ANIMATING
        assert isinstance(ui.particle_effect, BattleBarVolleyEffect)

    def test_duration_comes_from_the_volley_schedule(self, battle_ui):
        """
        The duration is derived from the schedule now, not drawn up front - the
        interface must adopt it or the post-animation hold is mistimed.
        """
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        assert ui.animation_duration == ui.particle_effect.duration
        assert ANIMATION_MIN_DURATION <= ui.animation_duration <= ANIMATION_MAX_DURATION

    def test_reaches_a_later_state(self, battle_ui):
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        run_animation(ui)
        assert ui.state in (BattleInterfaceState.SPLASH, BattleInterfaceState.REPORT)

    def test_renders_in_every_state(self, battle_ui, screen):
        ui, _, _ = battle_ui
        ui.render()
        ui.handle_click(ui.resolve_button_rect.center)
        for _ in range(400):
            ui.update(1.0 / 60.0)
            ui.render()


class TestNoJumpOnResolve:
    """Nothing on screen may jump when Resolve is clicked."""

    def test_icon_pulse_carries_on(self, battle_ui):
        """The icon's pulse (and its glow) runs on a clock the Resolve click does not reset."""
        ui, _, _ = battle_ui
        for _ in range(37):
            ui.update(1.0 / 60.0)
        clock = ui._ambient_clock
        ui.handle_click(ui.resolve_button_rect.center)
        assert ui.elapsed == 0.0               # the state's own clock restarts...
        assert ui._ambient_clock == clock      # ...the pulse's does not
        ui.update(0.25)
        assert ui._ambient_clock == pytest.approx(clock + 0.25)

    def test_setup_bars_match_the_effects_first_frame(self, battle_ui, screen):
        """
        The setup screen and the volley effect paint the bars with the same
        painter at the same clock, so the bars look identical across the click.
        """
        ui, _, _ = battle_ui
        for _ in range(53):
            ui.update(1.0 / 60.0)
        fill_y = ui.attacker_bar_rect.top + ui.bar_fill_offset
        areas = [pygame.Rect(rect.left, fill_y, rect.width, rect.height)
                 for rect in (ui.attacker_bar_rect, ui.defender_bar_rect)]
        ui.render()
        before = [screen.subsurface(area).copy() for area in areas]
        ui.handle_click(ui.resolve_button_rect.center)
        ui.render()
        after = [screen.subsurface(area).copy() for area in areas]
        for a, b in zip(before, after):
            assert pygame.image.tobytes(a, 'RGB') == pygame.image.tobytes(b, 'RGB')


class TestRealResultRetarget:
    """The bars must animate to the real outcome, not the estimate."""

    def test_retarget_moves_the_bars_to_the_real_result(self, battle_ui):
        ui, game, territory = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)

        # Mirror what main.py does right after handle_click returns 'resolve'
        game.resolve_battle(0)
        assert not game.pending_battles, "resolve_battle should consume the battle"

        ui.set_actual_battle_result(
            winner=0, attacker_survivors=13, defender_survivors=0,
            surviving_units=None)

        effect = ui.particle_effect
        assert effect.sides[effect.ATTACKER]['final'] == pytest.approx(
            ui.attacker_final_fill)
        assert effect.sides[effect.DEFENDER]['final'] == pytest.approx(0.0)

        run_animation(ui)
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(
            ui.attacker_final_fill)
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(0.0)

    def test_retarget_does_not_change_the_duration(self, battle_ui):
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        before = ui.particle_effect.duration
        ui.set_actual_battle_result(0, 13, 0, None)
        assert ui.particle_effect.duration == before

    def test_winning_side_bar_does_not_grow(self, battle_ui):
        """
        The attacker starts at fill 1.0 here; whatever the survivor ratio, the
        bar must end at or below where it started.
        """
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        ui.set_actual_battle_result(0, 20, 0, None)  # no losses at all
        assert ui.attacker_final_fill <= ui.attacker_fill + 1e-9

    def test_tie_estimate_is_corrected(self, battle_ui):
        """
        On an exact strength tie the estimate drains both bars; the real result
        has a winner, and the bars must follow it.
        """
        ui, _, _ = battle_ui
        ui.attacker_strength = ui.defender_strength = 10.0
        ui.attacker_fill = ui.defender_fill = 1.0
        ui.handle_click(ui.resolve_button_rect.center)
        assert ui.attacker_final_fill == 0.0 and ui.defender_final_fill == 0.0

        ui.set_actual_battle_result(1, 0, 4, None)
        assert ui.defender_final_fill > 0.0
        run_animation(ui)
        effect = ui.particle_effect
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(
            ui.defender_final_fill)


class TestSkip:
    """Clicking or pressing Space during the animation cuts it short."""

    def test_click_skips(self, battle_ui):
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.5)
        assert ui.handle_click((10, 10)) == 'skip'
        assert ui.particle_effect.is_finished()
        ui.update(1.0 / 60.0)
        assert ui.state != BattleInterfaceState.ANIMATING

    @pytest.mark.parametrize('key', [pygame.K_SPACE, pygame.K_ESCAPE])
    def test_key_skips(self, battle_ui, key):
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.5)
        event = pygame.event.Event(pygame.KEYDOWN, key=key)
        assert ui.handle_key(event) == 'skip'
        assert ui.particle_effect.is_finished()

    def test_skip_lands_on_the_final_fills(self, battle_ui):
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        ui.set_actual_battle_result(0, 13, 0, None)
        ui.update(0.4)
        ui.skip_animation()
        effect = ui.particle_effect
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(
            ui.attacker_final_fill)
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(0.0)

    def test_other_keys_are_ignored(self, battle_ui):
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a)
        assert ui.handle_key(event) is None
        assert ui.state == BattleInterfaceState.ANIMATING

    def test_skip_is_inert_outside_the_animation(self, battle_ui):
        """Space in SETUP must not skip anything - there is nothing running."""
        ui, _, _ = battle_ui
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        assert ui.handle_key(event) is None
        assert ui.skip_animation() is False
        assert ui.state == BattleInterfaceState.SETUP


def _button_pixels(ui, rect):
    """The button's pixels drawn alone on black (the backdrop and effects left out)."""
    ui.screen.fill((0, 0, 0))
    ui._render_button(rect, "Skip", 'skip', mark='skip')
    return pygame.image.tobytes(ui.screen.subsurface(rect), 'RGB')


class TestSkipButton:
    """
    A Skip button under the bars while they fight (owner, 2026-10-28: a click or Space
    skipped the fight, but nothing on screen said so). It skips to the splash, which
    still plays.
    """

    def test_sits_centred_under_the_bars(self, battle_ui):
        ui, _, _ = battle_ui
        rect = ui.skip_button_rect
        fill_bottom = ui.attacker_bar_rect.top + ui.bar_fill_offset + ui.bar_fill_height
        assert rect.top > fill_bottom
        assert rect.centerx == ui.icon_center_x
        assert ui.attacker_bar_rect.right < rect.centerx < ui.defender_bar_rect.left
        assert ui.screen.get_rect().contains(rect)
        assert ui.skip_hint_top > rect.bottom

    def test_resolve_battle_shares_its_slot(self, battle_ui):
        """Owner, 2026-10-28: unified - the button stays put from Resolve to Skip."""
        ui, _, _ = battle_ui
        assert ui.resolve_button_rect == ui.skip_button_rect
        assert ui.resolve_button_rect is not ui.skip_button_rect

    @pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
    def test_fits_every_resolution(self, battle_ui, size):
        _, game, _ = battle_ui
        ui = EnhancedBattleInterface(screen=pygame.Surface(size), game_state=game, battle_index=0,
                                     font_manager=FontManager(), current_player_index=0)
        fill_bottom = ui.attacker_bar_rect.top + ui.bar_fill_offset + ui.bar_fill_height
        assert ui.skip_button_rect.top > fill_bottom
        assert ui.skip_hint_top + ui.hint_font.get_height() < size[1]
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.5)
        ui.render()

    def test_drawn_only_while_the_bars_fight(self, battle_ui):
        ui, _, _ = battle_ui
        drawn = []
        ui._render_skip_button = lambda: drawn.append(ui.state)
        ui.render()
        assert drawn == []                                   # setup
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.5)
        ui.render()
        assert drawn == [BattleInterfaceState.ANIMATING]
        run_animation(ui)
        while ui.state != BattleInterfaceState.REPORT:
            ui.update(0.1)
            ui.render()
        ui.render()
        assert drawn == [BattleInterfaceState.ANIMATING]     # no skip: no flash on the splash

    def test_clicking_it_skips_to_the_splash(self, battle_ui):
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.5)
        assert ui.handle_click(ui.skip_button_rect.center) == 'skip'
        assert ui.particle_effect.is_finished()
        ui.update(1.0 / 60.0)
        assert ui.state == BattleInterfaceState.SPLASH       # the splash still plays

    @pytest.mark.parametrize('how', ['button', 'click anywhere', 'space', 'escape'])
    def test_the_splash_clears_it(self, battle_ui, how):
        """Owner, 2026-10-28: it lingered over the splash (its click flash) - gone at once."""
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.5)
        if how == 'button':
            ui.handle_click(ui.skip_button_rect.center)
        elif how == 'click anywhere':
            ui.handle_click((10, 10))
        else:
            key = pygame.K_SPACE if how == 'space' else pygame.K_ESCAPE
            ui.handle_key(pygame.event.Event(pygame.KEYDOWN, key=key))
        ui.update(1.0 / 60.0)
        assert ui.state == BattleInterfaceState.SPLASH
        drawn = []
        ui._render_skip_button = lambda: drawn.append(ui.state)
        ui.render()
        assert drawn == []

    def test_hover_and_flash_show(self, battle_ui):
        ui, _, _ = battle_ui
        rect = ui.skip_button_rect
        ui.mouse_pos = (0, 0)
        idle = _button_pixels(ui, rect)
        ui.mouse_pos = rect.center
        hovered = _button_pixels(ui, rect)
        ui.mouse_pos = (0, 0)
        ui._trigger_flash('skip')
        flashed = _button_pixels(ui, rect)
        assert hovered != idle
        assert flashed != idle and flashed != hovered

    def test_nothing_is_built_once_it_shows(self, battle_ui):
        """Its sprites and labels are baked once - and kept for the next battle."""
        from ui import battle_screen_kit
        ui, _, _ = battle_ui
        ui.handle_click(ui.resolve_button_rect.center)
        ui.update(0.2)
        ui.render()
        ui.mouse_pos = ui.skip_button_rect.center
        ui.render()
        kit = battle_screen_kit._kit()
        baked = (len(kit['labels']), len(kit['widgets']._sprites))
        for _ in range(5):
            ui.update(1.0 / 60.0)
            ui.render()
        assert (len(kit['labels']), len(kit['widgets']._sprites)) == baked
        # The next battle opens a new interface: the same sprites serve it
        _, game, _ = battle_ui
        again = EnhancedBattleInterface(screen=ui.screen, game_state=game, battle_index=0,
                                        font_manager=ui.font_manager, current_player_index=0)
        again.handle_click(again.resolve_button_rect.center)
        again.update(0.2)
        again.render()
        again.mouse_pos = again.skip_button_rect.center
        again.render()
        assert (len(kit['labels']), len(kit['widgets']._sprites)) == baked


class TestPulsedIconCache:
    """The pulsing battle icon must not smoothscale every frame."""

    def test_cache_is_populated_and_bounded(self, battle_ui):
        ui, _, _ = battle_ui
        if not ui.battle_icon:
            pytest.skip("battle icon asset not available")

        for i in range(600):
            ui._ambient_clock = i * 0.01   # the pulse's clock
            ui.render()

        from ui.effects.battle_interface import ICON_PULSE_CACHE_MAX
        assert ui._pulsed_icon_cache
        assert len(ui._pulsed_icon_cache) <= ICON_PULSE_CACHE_MAX

    def test_cached_surface_is_reused(self, battle_ui):
        ui, _, _ = battle_ui
        if not ui.battle_icon:
            pytest.skip("battle icon asset not available")

        ui._ambient_clock = 0.3
        ui.render()
        snapshot = dict(ui._pulsed_icon_cache)
        assert snapshot

        ui.render()  # same clock -> same quantised step -> no new entry
        for step, surface in snapshot.items():
            assert ui._pulsed_icon_cache[step] is surface
