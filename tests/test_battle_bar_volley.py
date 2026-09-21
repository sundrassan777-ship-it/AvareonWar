"""
Tests for BattleBarVolleyEffect - the volley-based battle bar animation.

These cover the parts that must be exactly right: the chunk split has to sum to
the damage taken so the bars land precisely on their final fill, the schedule has
to be reproducible from the seed (multiplayer clients run it independently), and
the mirrored defender bar has to anchor on the opposite edge.

Pure logic - no display is opened. Sprite building uses plain SRCALPHA surfaces
with no convert_alpha(), so it works headless.
"""

import math
import os

import pygame
import pytest

# Headless video driver so pygame.Surface works without a window
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from ui.effects.battle_interface import (  # noqa: E402
    BattleBarVolleyEffect,
    ANIMATION_MIN_DURATION,
    ANIMATION_MAX_DURATION,
    VOLLEY_MIN,
    VOLLEY_MAX,
    BURN_DURATION,
    PROJECTILE_TRAVEL,
    FRAME_GLOW_DURATION,
)


ATTACKER_COLOR = (40, 60, 200)
DEFENDER_COLOR = (200, 50, 40)


@pytest.fixture(scope='module', autouse=True)
def _pygame_init():
    """Initialize pygame once for the module (no display needed)."""
    pygame.init()
    yield
    pygame.quit()


def make_effect(attacker_initial=1.0, defender_initial=0.6,
                attacker_final=0.4, defender_final=0.0,
                seed=12345, attacker_count=30, defender_count=18,
                ui_scale=1.0):
    """
    Build an effect with sane default geometry.

    Returns:
        BattleBarVolleyEffect instance
    """
    return BattleBarVolleyEffect(
        attacker_bar_rect=pygame.Rect(100, 500, 320, 40),
        defender_bar_rect=pygame.Rect(900, 500, 320, 40),
        attacker_color=ATTACKER_COLOR,
        defender_color=DEFENDER_COLOR,
        attacker_initial_fill=attacker_initial,
        defender_initial_fill=defender_initial,
        attacker_final_fill=attacker_final,
        defender_final_fill=defender_final,
        seed=seed,
        bar_border_img=None,
        bar_png_width=400,
        bar_fill_offset=-30,
        bar_png_height=200,
        ui_scale=ui_scale,
        attacker_count=attacker_count,
        defender_count=defender_count,
    )


def make_border(width=400, height=200):
    """
    Build a stand-in for BattleBar.png.

    Deliberately stores bright RGB under fully transparent pixels, like the real
    asset does - the frame flare must not light those up.

    Returns:
        pygame.Surface with per-pixel alpha
    """
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    surf.fill((255, 255, 255, 0))                      # transparent, but not black
    pygame.draw.rect(surf, (200, 170, 60, 255), surf.get_rect(), 6)
    return surf


def make_effect_with_border(seed=5):
    """
    Build an effect that has a frame image, so the flare sprite exists.

    Returns:
        BattleBarVolleyEffect instance
    """
    return BattleBarVolleyEffect(
        attacker_bar_rect=pygame.Rect(100, 500, 320, 40),
        defender_bar_rect=pygame.Rect(900, 500, 320, 40),
        attacker_color=ATTACKER_COLOR,
        defender_color=DEFENDER_COLOR,
        attacker_initial_fill=1.0,
        defender_initial_fill=0.6,
        attacker_final_fill=0.4,
        defender_final_fill=0.0,
        seed=seed,
        bar_border_img=make_border(),
        bar_png_width=400,
        bar_fill_offset=-30,
        bar_png_height=200,
        ui_scale=1.0,
        attacker_count=20,
        defender_count=20,
    )


def run_to_completion(effect, step=1.0 / 60.0, max_seconds=30.0):
    """
    Tick an effect until it reports finished.

    Args:
        effect: BattleBarVolleyEffect
        step: Delta time per tick
        max_seconds: Safety bound

    Returns:
        Number of ticks taken
    """
    ticks = 0
    while not effect.is_finished() and ticks * step < max_seconds:
        effect.update(step)
        ticks += 1
    assert effect.is_finished(), "effect never completed"
    return ticks


# ----------------------------------------------------------------------
# Chunk split
# ----------------------------------------------------------------------

class TestChunkSplit:
    """The chunks must account for exactly the damage each side takes."""

    def test_chunks_sum_to_damage(self):
        effect = make_effect(attacker_initial=1.0, attacker_final=0.4,
                             defender_initial=0.6, defender_final=0.0)

        atk = effect.sides[effect.ATTACKER]
        dfn = effect.sides[effect.DEFENDER]

        assert sum(atk['chunks']) == pytest.approx(1.0 - 0.4, abs=1e-9)
        assert sum(dfn['chunks']) == pytest.approx(0.6 - 0.0, abs=1e-9)

    def test_both_sides_get_same_number_of_chunks(self):
        effect = make_effect()
        assert len(effect.sides[0]['chunks']) == len(effect.sides[1]['chunks'])

    def test_chunks_are_all_positive_when_damage_taken(self):
        effect = make_effect(defender_initial=1.0, defender_final=0.0)
        assert all(c > 0 for c in effect.sides[effect.DEFENDER]['chunks'])

    def test_undamaged_side_gets_zero_chunks(self):
        """A side that takes no damage still gets a chunk list, all zeros."""
        effect = make_effect(attacker_initial=1.0, attacker_final=1.0)
        chunks = effect.sides[effect.ATTACKER]['chunks']
        assert chunks  # same length as the other side
        assert all(c == 0.0 for c in chunks)

    def test_negative_damage_does_not_grow_the_bar(self):
        """Defensive: a final fill above the initial must not inflate the bar."""
        effect = make_effect(attacker_initial=0.5, attacker_final=0.9)
        assert all(c == 0.0 for c in effect.sides[effect.ATTACKER]['chunks'])
        run_to_completion(effect)
        # _finish() snaps to the declared final regardless
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.9)


# ----------------------------------------------------------------------
# Volley count
# ----------------------------------------------------------------------

class TestVolleyCount:
    """Volley count scales with army size, within hard bounds."""

    def test_rises_with_army_size(self):
        small = make_effect(attacker_count=2, defender_count=2)
        large = make_effect(attacker_count=300, defender_count=300)
        assert len(large.sides[0]['chunks']) > len(small.sides[0]['chunks'])

    @pytest.mark.parametrize('atk,dfn', [
        (0, 0), (1, 1), (5, 3), (40, 40), (500, 500), (5000, 5000),
    ])
    def test_clamped_to_bounds(self, atk, dfn):
        effect = make_effect(attacker_count=atk, defender_count=dfn)
        count = len(effect.sides[0]['chunks'])
        assert VOLLEY_MIN <= count <= VOLLEY_MAX

    @pytest.mark.parametrize('atk,dfn', [
        (0, 0), (1, 1), (5, 3), (40, 40), (500, 500), (5000, 5000),
    ])
    def test_duration_stays_in_window(self, atk, dfn):
        effect = make_effect(attacker_count=atk, defender_count=dfn)
        assert ANIMATION_MIN_DURATION <= effect.duration <= ANIMATION_MAX_DURATION

    def test_last_shot_lands_before_the_end(self):
        """Every hit must have room to land and burn before the effect finishes."""
        effect = make_effect(attacker_count=400, defender_count=400)
        last_land = max(shot['land_t'] for shot in effect.volleys)
        assert last_land + BURN_DURATION < effect.duration


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------

class TestDeterminism:
    """Multiplayer clients build the schedule independently from the seed."""

    @staticmethod
    def _signature(effect):
        return [(s['shooter'], s['target'], round(s['fire_t'], 9), round(s['chunk'], 9))
                for s in effect.volleys]

    def test_same_seed_same_schedule(self):
        a = make_effect(seed=98765)
        b = make_effect(seed=98765)
        assert a.duration == b.duration
        assert self._signature(a) == self._signature(b)

    def test_different_seed_different_schedule(self):
        a = make_effect(seed=1)
        b = make_effect(seed=2)
        assert self._signature(a) != self._signature(b)

    def test_does_not_disturb_the_global_rng(self):
        """
        The effect must use a private RNG. game_state.resolve_battle() draws from
        the global one right after the animation starts, so a stray reseed here
        would change battle outcomes.
        """
        import random
        random.seed(4242)
        expected = [random.random() for _ in range(5)]

        random.seed(4242)
        make_effect(seed=777)
        actual = [random.random() for _ in range(5)]

        assert actual == expected


# ----------------------------------------------------------------------
# Playback
# ----------------------------------------------------------------------

class TestPlayback:
    """Bars must land exactly on their final fill, in visible steps."""

    def test_lands_exactly_on_final_fill(self):
        effect = make_effect(attacker_initial=1.0, attacker_final=0.37,
                             defender_initial=0.8, defender_final=0.0)
        run_to_completion(effect)
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.37)
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(0.0)

    def test_depletion_is_stepwise(self):
        """
        The fill should sit still between hits and drop at them - that is the
        whole point of the rework, so assert it rather than trusting the eye.
        """
        effect = make_effect(attacker_initial=1.0, attacker_final=0.2,
                             attacker_count=40, defender_count=40)
        seen = []
        step = 1.0 / 60.0
        while not effect.is_finished():
            effect.update(step)
            seen.append(effect.sides[effect.ATTACKER]['current'])

        distinct = sorted(set(round(v, 6) for v in seen), reverse=True)
        expected_steps = len(effect.sides[effect.ATTACKER]['chunks'])
        # One level per volley, plus the starting level
        assert len(distinct) <= expected_steps + 1
        # And it really does hold still: most frames repeat the previous value
        holds = sum(1 for a, b in zip(seen, seen[1:]) if a == b)
        assert holds > len(seen) * 0.8

    def test_fill_never_increases(self):
        effect = make_effect(attacker_initial=1.0, attacker_final=0.3)
        step = 1.0 / 60.0
        previous = effect.sides[effect.ATTACKER]['current']
        while not effect.is_finished():
            effect.update(step)
            current = effect.sides[effect.ATTACKER]['current']
            assert current <= previous + 1e-9
            previous = current

    def test_fill_never_goes_negative(self):
        effect = make_effect(defender_initial=0.5, defender_final=0.0)
        step = 1.0 / 30.0
        while not effect.is_finished():
            effect.update(step)
            assert effect.sides[effect.DEFENDER]['current'] >= 0.0

    def test_survives_a_single_huge_delta(self):
        """A lag spike must not strand chunks or leave the bar mid-burn."""
        effect = make_effect(attacker_initial=1.0, attacker_final=0.25)
        effect.update(99.0)
        assert effect.is_finished()
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.25)

    def test_update_after_completion_is_inert(self):
        effect = make_effect()
        run_to_completion(effect)
        final = effect.sides[effect.ATTACKER]['current']
        effect.update(1.0)
        assert effect.sides[effect.ATTACKER]['current'] == final


# ----------------------------------------------------------------------
# Skip
# ----------------------------------------------------------------------

class TestSkip:
    """Skipping mid-animation must land on the same state as playing it out."""

    def test_skip_lands_on_final_fills(self):
        effect = make_effect(attacker_initial=1.0, attacker_final=0.45,
                             defender_initial=0.7, defender_final=0.0)
        effect.update(0.5)
        effect.skip()
        assert effect.is_finished()
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.45)
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(0.0)

    def test_skip_clears_transient_visuals(self):
        effect = make_effect()
        # Run far enough in that something is mid-flight or mid-burn
        effect.update(0.4 + PROJECTILE_TRAVEL / 2)
        effect.skip()
        for side in effect.sides:
            assert side['burn'] is None
            assert side['flash'] is None
            assert side['glow_t0'] is None
        assert all(shot['landed'] for shot in effect.volleys)

    def test_skip_before_any_shot(self):
        effect = make_effect(attacker_final=0.1)
        effect.skip()
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.1)


# ----------------------------------------------------------------------
# Retarget
# ----------------------------------------------------------------------

class TestRetarget:
    """Re-aiming at the real battle result must not disturb the rhythm."""

    def test_preserves_timing(self):
        effect = make_effect(attacker_final=0.4, defender_final=0.0)
        before_times = [round(s['fire_t'], 9) for s in effect.volleys]
        before_duration = effect.duration

        effect.retarget(0.0, 0.55)

        after_times = [round(s['fire_t'], 9) for s in effect.volleys]
        assert after_times == before_times
        assert effect.duration == before_duration

    def test_changes_the_landing_point(self):
        effect = make_effect(attacker_initial=1.0, attacker_final=0.4,
                             defender_initial=0.9, defender_final=0.0)
        effect.retarget(0.0, 0.55)
        run_to_completion(effect)
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.0)
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(0.55)

    def test_retarget_flips_the_winner(self):
        """The strength-tie case: estimate drains both bars, reality has a winner."""
        effect = make_effect(attacker_initial=1.0, attacker_final=0.0,
                             defender_initial=1.0, defender_final=0.0)
        effect.retarget(0.62, 0.0)
        run_to_completion(effect)
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.62)
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(0.0)


# ----------------------------------------------------------------------
# Mirrored geometry
# ----------------------------------------------------------------------

class TestMirroring:
    """The defender bar is anchored on the opposite edge."""

    def test_attacker_anchors_left(self):
        effect = make_effect()
        side = effect.sides[effect.ATTACKER]
        rect = effect._fill_rect(side, 0.5)
        assert rect.left == side['rect'].left
        assert rect.width == side['rect'].width // 2

    def test_defender_anchors_right(self):
        effect = make_effect()
        side = effect.sides[effect.DEFENDER]
        rect = effect._fill_rect(side, 0.5)
        assert rect.right == side['rect'].right
        assert rect.width == side['rect'].width // 2

    def test_tips_face_each_other(self):
        """Both bars erode toward the centre, so the tips close in on the gap."""
        effect = make_effect()
        atk, dfn = effect.sides
        full_gap = effect._fill_tip_x(dfn, 1.0) - effect._fill_tip_x(atk, 1.0)
        empty_gap = effect._fill_tip_x(dfn, 0.0) - effect._fill_tip_x(atk, 0.0)
        assert empty_gap > full_gap

    def test_empty_and_full_extremes(self):
        effect = make_effect()
        for side in effect.sides:
            assert effect._fill_rect(side, 0.0).width == 0
            assert effect._fill_rect(side, 1.0).width == side['rect'].width

    def test_fill_ratio_is_clamped(self):
        effect = make_effect()
        side = effect.sides[effect.DEFENDER]
        assert effect._fill_rect(side, 5.0).width == side['rect'].width
        assert effect._fill_rect(side, -3.0).width == 0

    def test_chunk_rect_sits_at_the_inner_tip(self):
        effect = make_effect()
        atk, dfn = effect.sides
        # Attacker erodes right-to-left: the doomed slice is at the right end
        atk_chunk = effect._chunk_rect(atk, 0.6, 0.8)
        assert atk_chunk.right == pytest.approx(effect._fill_tip_x(atk, 0.8), abs=1)
        # Defender erodes left-to-right: the doomed slice is at the left end
        dfn_chunk = effect._chunk_rect(dfn, 0.6, 0.8)
        assert dfn_chunk.left == pytest.approx(effect._fill_tip_x(dfn, 0.8), abs=1)
        assert atk_chunk.width > 0 and dfn_chunk.width > 0

    def test_muzzles_face_the_gap(self):
        effect = make_effect()
        atk, dfn = effect.sides
        assert effect._muzzle_x(atk) == atk['rect'].right
        assert effect._muzzle_x(dfn) == dfn['rect'].left


# ----------------------------------------------------------------------
# Rendering smoke tests
# ----------------------------------------------------------------------

class TestRender:
    """render() must not blow up in any phase, at any ui_scale."""

    @pytest.mark.parametrize('ui_scale', [0.5, 1.0, 2.0])
    def test_renders_every_frame_without_error(self, ui_scale):
        screen = pygame.Surface((1600, 900))
        effect = make_effect(ui_scale=ui_scale, attacker_count=60, defender_count=60)
        step = 1.0 / 60.0
        while not effect.is_finished():
            effect.update(step)
            effect.render(screen)
        effect.render(screen)  # once more after completion

    def test_sprites_are_prebuilt_not_per_frame(self):
        """Sprites are built once in __init__; render must not rebuild them."""
        effect = make_effect()
        screen = pygame.Surface((1600, 900))
        lances = [side['lance'] for side in effect.sides]
        flashes = [side['flash_frames'] for side in effect.sides]
        glows = [side['glow'] for side in effect.sides]

        for _ in range(120):
            effect.update(1.0 / 60.0)
            effect.render(screen)

        assert [side['lance'] for side in effect.sides] == lances
        assert [side['flash_frames'] for side in effect.sides] == flashes
        assert [side['glow'] for side in effect.sides] == glows

    def test_flash_frame_count(self):
        effect = make_effect()
        for side in effect.sides:
            assert len(side['flash_frames']) > 1
            assert all(f.get_size() == side['flash_frames'][0].get_size()
                       for f in side['flash_frames'])

    def test_lances_point_opposite_ways(self):
        """
        The attacker's streak has its bright head on the right, the defender's on
        the left - otherwise one side's blast would fly tail-first.
        """
        effect = make_effect(ui_scale=1.0)

        def head_side(sprite):
            w, h = sprite.get_size()
            mid = h // 2
            left_alpha = sprite.get_at((1, mid))[3]
            right_alpha = sprite.get_at((w - 2, mid))[3]
            return 'right' if right_alpha > left_alpha else 'left'

        assert head_side(effect.sides[effect.ATTACKER]['lance']) == 'right'
        assert head_side(effect.sides[effect.DEFENDER]['lance']) == 'left'

    def test_frame_flare_is_built_from_the_border(self):
        assert make_effect().sides[0]['glow'] is None  # no border -> no flare

        with_border = make_effect_with_border()
        for side in with_border.sides:
            assert side['glow'] is not None
            assert side['glow'].get_size() == side['border'].get_size()

    def test_frame_flare_leaves_transparent_pixels_transparent(self):
        """
        BattleBar.png stores bright RGB under its transparent pixels, so the
        flare must key off alpha - otherwise the whole rectangle lights up.
        """
        glow = make_effect_with_border().sides[0]['glow']
        # Centre of make_border() is transparent; it must stay that way
        assert glow.get_at((200, 100))[3] == 0
        # The frame outline itself must actually be visible, and brighter than
        # the artwork it was built from
        assert glow.get_at((2, 100))[3] > 0
        assert sum(glow.get_at((2, 100))[:3]) > sum((200, 170, 60))

    def test_frame_flare_alpha_is_set_on_every_blit(self):
        """
        The flare is one sprite faded with set_alpha, which is sticky - so every
        frame of the flare must set it rather than inherit the last value.
        """
        effect = make_effect_with_border()
        screen = pygame.Surface((1600, 900))
        side = effect.sides[effect.DEFENDER]

        # Drive it to the moment of a hit, then sample the alpha as it decays
        alphas = []
        while not effect.is_finished():
            effect.update(1.0 / 60.0)
            effect.render(screen)
            if side['glow_t0'] is not None:
                age = effect.elapsed - side['glow_t0']
                if age < FRAME_GLOW_DURATION:
                    alphas.append((round(age, 4), side['glow'].get_alpha()))

        assert alphas, "no frame flare was ever rendered"
        # Alpha must fall as the flare ages, and reach the floor by the end
        first_hit = [a for t, a in alphas if t < 0.02]
        last_hit = [a for t, a in alphas if t > FRAME_GLOW_DURATION * 0.9]
        assert first_hit and last_hit
        assert max(first_hit) > max(last_hit)

    def test_renders_without_a_border_image(self):
        """bar_border_img=None must fall back to plain outlines, not crash."""
        screen = pygame.Surface((1600, 900))
        effect = make_effect()
        assert effect.sides[0]['border'] is None
        assert effect.sides[0]['glow'] is None
        effect.update(0.5)
        effect.render(screen)
