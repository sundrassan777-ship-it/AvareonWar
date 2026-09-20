# -*- coding: utf-8 -*-
"""
Regression tests: army BANNERS are first-class click/hover targets.

Before this change the banner was only half-clickable and never hoverable:

  - render  (map_renderer) drew the banner spanning anchor_y - flag_height .. anchor_y
  - click   (get_army_at_pos) tested only anchor_y - flag_height/2 .. anchor_y,
            so the flag cloth - the part the eye actually goes to - was dead
  - hover   (handle_mouse_motion, and the renderer's own ring-brightening test)
            ignored the banner entirely, so nothing hinted it was clickable

Three passes each recomputed the geometry independently and disagreed. They now
all route through Game.get_army_banner_rect() / get_effective_garrison_count() /
get_garrison_anchor(), so they cannot drift apart again.

These tests pin the helpers' contract and the two-pass hit ordering. The visual
side (ring brightening) is inherently a render concern and is covered manually.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import (
    ARMY_CIRCLE_RADIUS,
    ARMY_CIRCLE_DRAW_LIFT,
    ARMY_CIRCLE_DRAW_SCALE,
    ARMY_FLAG_HEIGHT_RATIO,
    DEFAULT_ARMY_FLAG_ASPECT,
)


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
    g.initialize_game({
        'num_players': 2,
        'player_is_ai': [False, True],
        'player_ai_difficulty': [None, 'Normal'],
    })
    g.game_state.phase = 'playing'
    g.game_state.turn_phase = 'planning'
    g.game_state.current_player = 0
    return g


def _clear_armies(game):
    """Strip every garrison so a test controls the whole map."""
    game.game_state.territory_garrisons.clear()
    game.game_state.active_animations = []


def _place(game, territory, player, count=3, owner=None):
    """Give `player` a garrison in `territory` and return its world center."""
    game.game_state.territory_owners[territory] = player if owner is None else owner
    game.game_state.add_garrison(territory, player, unmoved=count)
    return game.scaled_centers[territory]


def _banner(game, territory, player, count, space='world'):
    cx, cy = game.scaled_centers[territory]
    return game.get_army_banner_rect(cx, cy, player, count, space=space)


# ============================================================================
# Banner geometry
# ============================================================================

class TestBannerGeometry:
    """get_army_banner_rect() is the single source of truth for banner shape."""

    def test_banner_hangs_upward_from_the_anchor(self, game):
        """Pole base sits ON the circle anchor; the banner extends upward."""
        left, top, width, height = game.get_army_banner_rect(500.0, 400.0, 0, 3)

        assert top == pytest.approx(400.0 - height), "banner top is not height above the anchor"
        assert top + height == pytest.approx(400.0), "banner bottom is not AT the anchor"
        assert left == pytest.approx(500.0 - width / 2.0), "banner is not horizontally centred"

    def test_width_follows_the_source_art_aspect(self, game):
        """Width comes from the flag PNG's aspect, not from the circle radius."""
        aspect = game.get_army_flag_aspect(0, 3)
        assert aspect is not None

        _, _, width, height = game.get_army_banner_rect(500.0, 400.0, 0, 3)
        assert width / height == pytest.approx(aspect)

    def test_height_matches_the_shared_ratio(self, game):
        """Height is ARMY_CIRCLE_RADIUS * ui_scale * ARMY_FLAG_HEIGHT_RATIO."""
        game.camera_zoom = 1.0  # world == screen scale, so no zoom division
        expected = ARMY_CIRCLE_RADIUS * game.get_ui_scale_factor() * ARMY_FLAG_HEIGHT_RATIO

        _, _, _, height = game.get_army_banner_rect(0.0, 0.0, 0, 3, space='screen')
        assert height == pytest.approx(expected)

    @pytest.mark.parametrize("zoom", [1.65, 2.5, 4.0])
    def test_world_footprint_shrinks_as_you_zoom_in(self, game, zoom):
        """World-space size is divided by zoom so the SCREEN size stays constant."""
        game.camera_zoom = zoom
        _, _, w_world, h_world = game.get_army_banner_rect(0.0, 0.0, 0, 3, space='world')
        _, _, w_screen, h_screen = game.get_army_banner_rect(0.0, 0.0, 0, 3, space='screen')

        assert h_world == pytest.approx(h_screen / zoom)
        assert w_world == pytest.approx(w_screen / zoom)

    def test_tier_change_resizes_the_banner(self, game):
        """Tiers use different art with different aspects, so the box must follow."""
        # 4 armies -> tier 1, 10 armies -> tier 3
        assert game.get_army_flag_tier(4) == 1
        assert game.get_army_flag_tier(10) == 3

        aspect_small = game.get_army_flag_aspect(0, 4)
        aspect_large = game.get_army_flag_aspect(0, 10)
        if aspect_small == pytest.approx(aspect_large):
            pytest.skip("this player's tier art happens to share an aspect ratio")

        _, _, w_small, _ = game.get_army_banner_rect(0.0, 0.0, 0, 4)
        _, _, w_large, _ = game.get_army_banner_rect(0.0, 0.0, 0, 10)
        assert w_small != pytest.approx(w_large)


class TestWorldScreenConsistency:
    """world_to_screen is a uniform scale+offset, so the two spaces must agree."""

    def test_world_rect_projects_onto_the_screen_rect(self, game):
        territory = next(iter(game.scaled_centers))
        cx, cy = game.scaled_centers[territory]

        w_left, w_top, w_width, w_height = game.get_army_banner_rect(cx, cy, 0, 3, space='world')
        sx, sy = game.world_to_screen((cx, cy))
        s_left, s_top, s_width, s_height = game.get_army_banner_rect(sx, sy, 0, 3, space='screen')

        proj_left, proj_top = game.world_to_screen((w_left, w_top))

        assert proj_left == pytest.approx(s_left, abs=1e-6)
        assert proj_top == pytest.approx(s_top, abs=1e-6)
        assert w_width * game.camera_zoom == pytest.approx(s_width, abs=1e-6)
        assert w_height * game.camera_zoom == pytest.approx(s_height, abs=1e-6)


class TestMissingArt:
    """No banner drawn => nothing may be hit-tested."""

    def test_unknown_player_has_no_aspect(self, game):
        assert game.get_army_flag_aspect(999, 3) is None

    def test_no_art_means_no_rect_and_no_hit(self, game):
        assert game.get_army_banner_rect(500.0, 400.0, 999, 3) is None
        assert game.point_in_army_banner(500.0, 400.0, 500.0, 400.0, 999, 3) is False

    def test_zero_height_art_falls_back_to_default_aspect(self, game, pygame_display):
        """Degenerate art must not divide by zero."""
        pygame = pygame_display
        game.army_flag_icons.setdefault(0, {})[1] = pygame.Surface((10, 0))
        assert game.get_army_flag_aspect(0, 1) == pytest.approx(DEFAULT_ARMY_FLAG_ASPECT)


# ============================================================================
# The headline fix: the whole banner is clickable
# ============================================================================

class TestBannerIsFullyClickable:

    def test_top_of_the_cloth_selects_the_army(self, game):
        """THE regression. The old half-height box missed this point entirely."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        _, top, _, height = game.get_army_banner_rect(cx, cy, 0, 3)
        # 10% down from the very top of the banner - deep inside the old dead zone
        probe_y = top + height * 0.1

        assert game.get_army_at_pos((cx, probe_y)) == (territory, 0)

    def test_old_half_height_box_really_did_miss_it(self, game):
        """Documents the bug: the probe above sits ABOVE the old box's top edge."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        _, top, _, height = game.get_army_banner_rect(cx, cy, 0, 3)
        probe_y = top + height * 0.1
        old_box_top = cy - height / 2.0

        assert probe_y < old_box_top, "probe is not in the previously-dead region"

    def test_point_just_outside_the_banner_misses(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        left, top, width, height = game.get_army_banner_rect(cx, cy, 0, 3)

        assert game.get_army_at_pos((left - 2.0, top + height * 0.25)) is None
        assert game.get_army_at_pos((left + width + 2.0, top + height * 0.25)) is None
        assert game.get_army_at_pos((cx, top - 2.0)) is None

    def test_circle_still_selects(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        assert game.get_army_at_pos((cx, cy)) == (territory, 0)

    def test_mode_circle_ignores_the_banner(self, game):
        """PRIORITY 3 uses mode='circle' so banners cannot outrank plots."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        _, top, _, height = game.get_army_banner_rect(cx, cy, 0, 3)
        probe = (cx, top + height * 0.1)

        assert game.get_army_at_pos(probe, mode='circle') is None
        assert game.get_army_at_pos(probe, mode='banner') == (territory, 0)

    def test_enemy_garrison_is_not_clickable(self, game):
        """Selection semantics unchanged: only the current player's garrison."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 1, count=3)
        game.game_state.current_player = 0

        _, top, _, height = game.get_army_banner_rect(cx, cy, 1, 3)
        assert game.get_army_at_pos((cx, top + height * 0.1)) is None
        assert game.get_army_at_pos((cx, cy)) is None


class TestCircleMatchesTheDrawnRing:
    """
    The hit circle must be the ring you can SEE.

    MapRenderer._draw_army_circle() draws the ring at 0.75 * radius, lifted
    0.35 * radius above the anchor. Hit-testing used a FULL-radius circle centred
    ON the anchor, so it reached 0.60 * radius (9-14 screen px) BELOW the visible
    ring and selected armies from empty map below the circle.
    """

    def test_hit_circle_is_lifted_above_the_anchor(self, game):
        cx, cy, radius = game.get_army_circle_hit(500.0, 400.0, space='screen')
        base = ARMY_CIRCLE_RADIUS * game.get_ui_scale_factor()

        assert cx == pytest.approx(500.0)
        assert cy == pytest.approx(400.0 - base * ARMY_CIRCLE_DRAW_LIFT)
        assert radius == pytest.approx(base * ARMY_CIRCLE_DRAW_SCALE)

    def test_hit_circle_bottom_matches_the_drawn_ring_bottom(self, game):
        """The whole point: no reach below what is drawn."""
        game.camera_zoom = 1.0
        base = ARMY_CIRCLE_RADIUS * game.get_ui_scale_factor()

        _, cy, radius = game.get_army_circle_hit(0.0, 0.0, space='screen')
        drawn_bottom = base * (ARMY_CIRCLE_DRAW_SCALE - ARMY_CIRCLE_DRAW_LIFT)

        assert cy + radius == pytest.approx(drawn_bottom)
        assert cy + radius < base, "hit circle still reaches a full radius below the anchor"

    @pytest.mark.parametrize("zoom", [1.65, 2.5, 4.0])
    def test_just_below_the_visible_ring_is_not_selectable(self, game, zoom):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)
        game.camera_zoom = zoom
        game.camera.zoom = zoom

        _, circle_y, radius = game.get_army_circle_hit(cx, cy)
        just_below = circle_y + radius + (3.0 / zoom)

        assert game.get_army_at_pos((cx, just_below)) is None

    @pytest.mark.parametrize("zoom", [1.65, 2.5, 4.0])
    def test_the_ring_itself_is_still_selectable(self, game, zoom):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)
        game.camera_zoom = zoom
        game.camera.zoom = zoom

        _, circle_y, _ = game.get_army_circle_hit(cx, cy)
        assert game.get_army_at_pos((cx, circle_y)) == (territory, 0)

    def test_old_full_radius_probe_is_now_rejected(self, game):
        """Documents the bug: a point a full radius below the anchor used to hit."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        base_world = (ARMY_CIRCLE_RADIUS * game.get_ui_scale_factor()) / game.camera_zoom
        old_probe = (cx, cy + base_world * 0.9)  # inside the OLD circle, outside the new

        assert game.get_army_at_pos(old_probe) is None

    def test_banner_never_extends_below_the_anchor(self, game):
        """The banner was never the cause - it stops exactly at the pole base."""
        _, top, _, height = game.get_army_banner_rect(500.0, 400.0, 0, 3)
        assert top + height == pytest.approx(400.0)

    def test_hover_agrees_with_click_below_the_ring(self, game):
        """Hover must not highlight where a click would miss."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        _, circle_y, radius = game.get_army_circle_hit(cx, cy)
        just_below_world = (cx, circle_y + radius + (3.0 / game.camera_zoom))
        sx, sy = game.world_to_screen(just_below_world)

        game.handle_mouse_motion((int(sx), int(sy)))
        assert game.hovered_army is None
        assert game.get_army_at_pos(just_below_world) is None


class TestCircleBeatsBanner:
    """A visible circle must always win over an overlapping neighbour's banner."""

    def test_circle_wins_when_a_banner_covers_it(self, game):
        _clear_armies(game)

        # Find two territories where one sits far enough ABOVE the other that its
        # banner (which hangs upward) cannot reach, but close enough horizontally
        # that we can construct the overlap synthetically.
        names = list(game.scaled_centers.keys())[:2]
        lower, upper = names[0], names[1]

        cx, cy = _place(game, lower, 0, count=3)
        _place(game, upper, 0, count=3)

        # Put the upper territory's anchor directly below-ish so its banner, which
        # extends upward, swallows the lower territory's circle.
        _, _, _, height = game.get_army_banner_rect(cx, cy, 0, 3)
        game.scaled_centers[upper] = (cx, cy + height * 0.5)

        # Probe exactly at the lower territory's circle centre. It is inside the
        # upper territory's banner too, so ordering decides the winner.
        assert game.point_in_army_banner(
            cx, cy, cx, cy + height * 0.5, 0, 3), "test setup did not create an overlap"

        assert game.get_army_at_pos((cx, cy)) == (lower, 0)


# ============================================================================
# Multi-garrison / allied reinforcement
# ============================================================================

class TestEffectiveGarrisonCount:
    """Slot count must match the renderer or hit boxes land where no flag is."""

    def test_single_garrison(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        _place(game, territory, 0, count=3)

        assert game.get_effective_garrison_count(territory) == 1

    def test_empty_garrisons_are_not_counted(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        _place(game, territory, 0, count=3)
        game.game_state.add_garrison(territory, 1, unmoved=0)

        assert game.get_effective_garrison_count(territory) == 1

    def test_two_live_garrisons(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        _place(game, territory, 0, count=3)
        game.game_state.add_garrison(territory, 1, unmoved=2)

        assert game.get_effective_garrison_count(territory) == 2

    def test_inbound_arrival_widens_the_layout(self, game):
        """Flags must not jump when a movement animation lands."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        _place(game, territory, 0, count=3)

        assert game.get_effective_garrison_count(
            territory, incoming_players={1}) == 2

    def test_allied_reinforcement_rule(self, game):
        """
        An OWNED territory whose only future garrison is not the owner uses the
        2-slot layout, matching where the animation is flying to.

        The click path used to lack this rule, so mid-animation the flag was drawn
        ~25 world units off-centre while the click test still probed the centre -
        the army was briefly unclickable.
        """
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        # Owner is player 0, but the only garrison present belongs to ally 1
        game.game_state.territory_owners[territory] = 0
        game.game_state.add_garrison(territory, 1, unmoved=3)

        assert game.get_effective_garrison_count(
            territory, incoming_players={1}) == 2

    def test_owner_reinforcing_itself_stays_single(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        _place(game, territory, 0, count=3)

        assert game.get_effective_garrison_count(
            territory, incoming_players={0}) == 1


class TestMultiGarrisonBanners:
    """Allied-reinforced territories show one banner per garrison."""

    def test_each_garrison_gets_its_own_anchor(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)
        game.game_state.add_garrison(territory, 1, unmoved=2)

        num = game.get_effective_garrison_count(territory)
        a0 = game.get_garrison_anchor(territory, cx, cy, 0, num)
        a1 = game.get_garrison_anchor(territory, cx, cy, 1, num)

        assert a0 is not None and a1 is not None
        assert (a0[0], a0[1]) != (a1[0], a1[1]), "garrisons share an anchor"

    def test_your_own_banner_selects_you_in_a_stack(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)
        game.game_state.add_garrison(territory, 1, unmoved=2)
        game.game_state.current_player = 0

        num = game.get_effective_garrison_count(territory)
        ax, ay, count = game.get_garrison_anchor(territory, cx, cy, 0, num)
        _, top, _, height = game.get_army_banner_rect(ax, ay, 0, count)

        assert game.get_army_at_pos((ax, top + height * 0.1)) == (territory, 0)

    def test_allys_banner_does_not_select_your_garrison(self, game):
        """Clicking an ally's banner must not open YOUR composition UI."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)
        game.game_state.add_garrison(territory, 1, unmoved=2)
        game.game_state.current_player = 0

        num = game.get_effective_garrison_count(territory)
        ax, ay, count = game.get_garrison_anchor(territory, cx, cy, 1, num)
        _, top, _, height = game.get_army_banner_rect(ax, ay, 1, count)

        result = game.get_army_at_pos((ax, top + height * 0.1))
        # Either nothing, or - if the ally's banner overlaps your own - yours.
        # It must never report the ally's garrison.
        assert result is None or result == (territory, 0)

    def test_anchor_is_none_for_a_player_with_no_armies(self, game):
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)

        assert game.get_garrison_anchor(territory, cx, cy, 1) is None

    def test_anchors_are_stable_across_repeated_calls(self, game):
        """Slot assignment must not shuffle between the click/hover/render passes."""
        _clear_armies(game)
        territory = next(iter(game.scaled_centers))
        cx, cy = _place(game, territory, 0, count=3)
        game.game_state.add_garrison(territory, 1, unmoved=2)

        num = game.get_effective_garrison_count(territory)
        first = game.get_garrison_anchor(territory, cx, cy, 0, num)
        for _ in range(5):
            assert game.get_garrison_anchor(territory, cx, cy, 0, num) == first
