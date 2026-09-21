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


class TestPulsedIconCache:
    """The pulsing battle icon must not smoothscale every frame."""

    def test_cache_is_populated_and_bounded(self, battle_ui):
        ui, _, _ = battle_ui
        if not ui.battle_icon:
            pytest.skip("battle icon asset not available")

        for i in range(600):
            ui.elapsed = i * 0.01
            ui.render()

        from ui.effects.battle_interface import ICON_PULSE_CACHE_MAX
        assert ui._pulsed_icon_cache
        assert len(ui._pulsed_icon_cache) <= ICON_PULSE_CACHE_MAX

    def test_cached_surface_is_reused(self, battle_ui):
        ui, _, _ = battle_ui
        if not ui.battle_icon:
            pytest.skip("battle icon asset not available")

        ui.elapsed = 0.3
        ui.render()
        snapshot = dict(ui._pulsed_icon_cache)
        assert snapshot

        ui.render()  # same elapsed -> same quantised step -> no new entry
        for step, surface in snapshot.items():
            assert ui._pulsed_icon_cache[step] is surface
