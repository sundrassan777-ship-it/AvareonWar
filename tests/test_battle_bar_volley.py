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


def make_effect_with_border(seed=5, attacker_count=20, defender_count=20):
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
        attacker_count=attacker_count,
        defender_count=defender_count,
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
            assert side['glow_t0'] is None
        assert all(shot['landed'] for shot in effect.volleys)
        # Nothing more is drawn in flight, and the icon's glow stops flaring
        assert effect.skipped
        assert effect.shot_kick() == 0.0

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

    def test_bolts_leave_from_the_inner_ends(self):
        """Without a frame from the fill's inner end, with one from its spear tip beyond it."""
        atk, dfn = make_effect().sides
        assert atk['tip'][0] == atk['rect'].right
        assert dfn['tip'][0] == dfn['rect'].left

        atk, dfn = make_effect_with_border().sides
        assert atk['tip'][0] > atk['rect'].right
        assert dfn['tip'][0] < dfn['rect'].left


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

    def test_nothing_is_built_during_the_fight_once_prepared(self):
        """
        The shots' light sprites are built while the setup screen shows
        (prewarm_step); the fight itself then builds and skips nothing.
        """
        effect = make_effect_with_border()
        light = effect.light
        while True:
            light.begin_frame()
            if light.prewarm_step():
                break
        built, denied = light.sprites_built(), light.denied()
        screen = pygame.Surface((1600, 900))
        while not effect.is_finished():
            effect.update(1.0 / 120.0)
            effect.render(screen)
        assert light.sprites_built() == built
        assert light.denied() == denied

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


# ----------------------------------------------------------------------
# Shots
# ----------------------------------------------------------------------

def run_until_fired(effect, step=1.0 / 120.0):
    """Tick until every shot has been armed; returns the shots in schedule order."""
    while not all(shot['fired'] for shot in effect.volleys) and not effect.is_finished():
        effect.update(step)
    return effect.volleys


class TestShots:
    """Each shot: a charge, one bolt of light, built when armed, from its own RNG."""

    def test_the_bolt_lands_when_the_chunk_breaks_off(self):
        for shot in run_until_fired(make_effect()):
            assert shot['fx'].land_t == pytest.approx(shot['land_t'])
            assert shot['fx'].fire_t == pytest.approx(shot['fire_t'])

    def test_the_bolt_lands_in_the_doomed_chunk_near_its_front(self):
        effect = make_effect_with_border()
        for shot in run_until_fired(effect):
            target = effect.sides[shot['target']]
            front = shot['end_x']
            back = effect._fill_tip_x(target, shot['aim'] - min(shot['chunk'], shot['aim']))
            sx, ex, ey = shot['fx'].flight
            assert min(front, back) - 1 <= ex <= max(front, back) + 1
            assert abs(ex - front) <= abs(back - front) * 0.3 + 1
            toward = 1 if shot['shooter'] == effect.ATTACKER else -1
            assert (ex - sx) * toward > 0

    def test_aim_skips_burning_and_in_flight_chunks(self):
        """A shot armed at a bar is aimed past what earlier shots are about to destroy."""
        effect = make_effect(defender_initial=0.8)
        target = effect.sides[effect.DEFENDER]
        target['burn'] = {'t0': 0.0, 'chunk': 0.1, 'fx': None}
        flying = next(s for s in effect.volleys if s['target'] == effect.DEFENDER)
        flying['fired'] = True
        assert effect._aim_fill(effect.DEFENDER) == pytest.approx(0.8 - 0.1 - flying['chunk'])

    def test_same_seed_same_shots(self):
        def looks(effect):
            return [(shot['fx'].flight, shot['fx'].sparks, shot['fx'].motes) for shot in run_until_fired(effect)]
        assert looks(make_effect(seed=31337)) == looks(make_effect(seed=31337))
        assert looks(make_effect(seed=31337)) != looks(make_effect(seed=31338))

    def test_playing_does_not_disturb_the_global_rng(self):
        """The shots' looks come from their own RNG, never the global one."""
        import random
        random.seed(99)
        expected = [random.random() for _ in range(5)]
        random.seed(99)
        effect = make_effect(seed=4)
        screen = pygame.Surface((1600, 900))
        while not effect.is_finished():
            effect.update(1.0 / 60.0)
            effect.render(screen)
        assert [random.random() for _ in range(5)] == expected

    def test_the_chunk_breaks_off_as_the_bolt_lands(self):
        fx = run_until_fired(make_effect())[0]['fx']
        assert fx.broken(fx.land_t - 1e-6) == 0.0
        assert fx.broken(fx.land_t) == 1.0


# ----------------------------------------------------------------------
# The charge
# ----------------------------------------------------------------------

class TestCharge:
    """Light gathers from the shooter's remaining bar into its front; the bolt leaves from there."""

    def test_the_bolt_leaves_from_the_shooters_front(self):
        """At the front its bar shows when the charge begins, on the bars' centre line."""
        effect = make_effect_with_border(attacker_count=40, defender_count=40)
        centre = effect.fill_y + effect.sides[0]['rect'].height / 2.0
        seen = set()
        while not effect.is_finished():
            effect.update(1.0 / 120.0)
            for index, shot in enumerate(effect.volleys):
                if shot['fired'] and index not in seen:
                    seen.add(index)
                    shooter = effect.sides[shot['shooter']]
                    burn = shooter['burn']
                    standing = shooter['current'] - (burn['chunk'] * burn['fx'].broken(effect.elapsed)
                                                     if burn is not None and burn['fx'] is not None else 0.0)
                    assert shot['fx'].muzzle[0] == pytest.approx(effect._fill_tip_x(shooter, standing))
                    assert shot['fx'].muzzle[1] == pytest.approx(centre)
                    assert shot['fx'].flight[2] == pytest.approx(centre)    # and flies level

    def test_the_charge_comes_before_the_bolt(self):
        from ui.effects.battle_fx_style import charge_time
        for shot in run_until_fired(make_effect()):
            fx = shot['fx']
            assert shot['fire_t'] - shot['arm_t'] == pytest.approx(charge_time())
            assert fx.charge(shot['arm_t']) == 0.0
            assert 0.0 < fx.charge((shot['arm_t'] + shot['fire_t']) / 2.0) < 1.0
            assert fx.charge(shot['fire_t']) is None
            assert fx.motes

    def test_the_motes_come_from_the_remaining_bar(self):
        effect = make_effect()
        for shot in run_until_fired(effect):
            shooter = effect.sides[shot['shooter']]
            lo, hi = sorted((shot['fx'].muzzle[0], effect._fill_tip_x(shooter, 0.0)))
            for x0, y0, delay, d in shot['fx'].motes:
                assert lo - 1 <= x0 <= hi + 1

    def test_off_fires_from_the_spear_tip(self, monkeypatch):
        """CHARGE_STYLE['enabled'] False: no gathering, the bolt leaves from the frame's spear tip."""
        from ui.effects import battle_fx_style
        monkeypatch.setitem(battle_fx_style.CHARGE_STYLE, 'enabled', False)
        effect = make_effect_with_border()
        for shot in run_until_fired(effect):
            assert shot['arm_t'] == shot['fire_t']
            assert shot['fx'].charge(shot['fire_t'] - 0.01) is None
            assert shot['fx'].motes == []
            assert shot['fx'].muzzle == effect.sides[shot['shooter']]['tip']


# ----------------------------------------------------------------------
# Finale
# ----------------------------------------------------------------------

class TestFinale:
    """The bar left standing gets a finale once the last bolt lands."""

    def test_picks_the_side_left_standing(self):
        effect = make_effect(attacker_final=0.4, defender_final=0.0)
        assert effect.finale_sides() == (effect.ATTACKER, effect.DEFENDER)
        effect.retarget(0.0, 0.55)
        assert effect.finale_sides() == (effect.DEFENDER, effect.ATTACKER)

    def test_no_finale_when_both_bars_empty(self):
        effect = make_effect(attacker_final=0.0, defender_final=0.0)
        assert effect.finale_sides() == (None, None)

    def test_starts_when_the_last_bolt_lands(self):
        effect = make_effect(attacker_final=0.4, defender_final=0.0)
        run_to_completion(effect, step=1.0 / 120.0)
        last = max(shot['fx'].land_t for shot in effect.volleys)
        assert effect.finale_t0 == pytest.approx(last)
        assert effect.finale_t0 < effect.duration
        # The emptied bar's last embers
        assert effect.finale_embers

    def test_runs_on_after_completion_without_moving_the_fills(self):
        effect = make_effect_with_border()
        run_to_completion(effect)
        fills = [side['current'] for side in effect.sides]
        elapsed = effect.elapsed
        screen = pygame.Surface((1600, 900))
        for _ in range(30):
            effect.update(1.0 / 60.0)
            effect.render(screen)
        assert effect.elapsed == pytest.approx(elapsed + 0.5)
        assert [side['current'] for side in effect.sides] == fills

    def test_skip_has_no_finale(self):
        effect = make_effect()
        effect.update(0.5)
        effect.skip()
        assert effect.finale_t0 is None
        effect.update(0.5)
        assert effect.finale_t0 is None


# ----------------------------------------------------------------------
# Turns: one shot at a time
# ----------------------------------------------------------------------

class TestTurns:
    """The sides take turns, one shot at a time (owner, 2026-10-28)."""

    def test_sides_take_turns(self):
        volleys = make_effect().volleys
        shooters = [s['shooter'] for s in volleys]
        assert all(a != b for a, b in zip(shooters, shooters[1:]))
        assert shooters.count(0) == shooters.count(1)

    def test_one_shot_at_a_time(self):
        """A side starts charging only once the bolt before has landed, and a pause."""
        from ui.effects.battle_interface import SHOT_PAUSE
        volleys = run_until_fired(make_effect(attacker_count=60, defender_count=60))
        for before, after in zip(volleys, volleys[1:]):
            assert after['arm_t'] >= before['fx'].land_t + SHOT_PAUSE - 1e-9

    def test_the_winner_fires_last(self):
        """The loser opens, the winner has the last word - and still after the real result flips it."""
        effect = make_effect(attacker_final=0.4, defender_final=0.0)
        assert effect.volleys[0]['shooter'] == effect.DEFENDER
        assert effect.volleys[-1]['shooter'] == effect.ATTACKER
        times = [s['fire_t'] for s in effect.volleys]
        effect.retarget(0.0, 0.55)
        assert effect.volleys[0]['shooter'] == effect.ATTACKER
        assert effect.volleys[-1]['shooter'] == effect.DEFENDER
        assert [s['fire_t'] for s in effect.volleys] == times

    @pytest.mark.parametrize('finals', [(0.4, 0.0), (0.0, 0.3), (0.0, 0.0)])
    def test_an_emptied_bar_never_fires_again(self, finals):
        effect = make_effect(attacker_final=finals[0], defender_final=finals[1])
        seen = set()
        while not effect.is_finished():
            effect.update(1.0 / 120.0)
            for index, shot in enumerate(effect.volleys):
                if shot['fired'] and index not in seen:
                    seen.add(index)
                    assert effect.sides[shot['shooter']]['current'] > 1e-9


# ----------------------------------------------------------------------
# Hits weighted by strength
# ----------------------------------------------------------------------

class TestHitStrength:
    """A hit is as heavy as the army firing it is strong at the time (owner, 2026-10-28)."""

    @pytest.mark.parametrize('seed', [3, 17, 2024, 31337])
    def test_a_weakening_army_hits_softer(self, seed):
        """The loser's hits on the winner shrink as the loser's bar empties."""
        effect = make_effect(attacker_initial=1.0, attacker_final=0.35, defender_initial=0.9,
                             defender_final=0.0, attacker_count=200, defender_count=150, seed=seed)
        taken = effect.sides[effect.ATTACKER]['chunks']      # the defender's hits, in order
        half = len(taken) // 2
        assert sum(taken[:half]) > 1.5 * sum(taken[half:])

    def test_the_bars_still_land_on_the_real_result(self):
        effect = make_effect(attacker_initial=1.0, attacker_final=0.35, defender_initial=0.9,
                             defender_final=0.0, attacker_count=200, defender_count=150)
        assert sum(effect.sides[effect.ATTACKER]['chunks']) == pytest.approx(0.65)
        assert sum(effect.sides[effect.DEFENDER]['chunks']) == pytest.approx(0.9)
        run_to_completion(effect)
        assert effect.sides[effect.ATTACKER]['current'] == pytest.approx(0.35)
        assert effect.sides[effect.DEFENDER]['current'] == pytest.approx(0.0)

    def test_off_gives_the_plain_random_split(self, monkeypatch):
        """HIT_STRENGTH_POWER 0: every army hits alike - only the random spread remains."""
        import ui.effects.battle_interface as bi
        monkeypatch.setattr(bi, 'HIT_STRENGTH_POWER', 0.0)
        import random
        effect = make_effect(seed=99)
        rng = random.Random(99)
        count = len(effect.volleys) // 2
        expected = bi.BattleBarVolleyEffect._split_damage(rng, 1.0 - 0.4, count)
        assert effect.sides[effect.ATTACKER]['chunks'] == pytest.approx(expected)


# ----------------------------------------------------------------------
# Falling pieces
# ----------------------------------------------------------------------

class TestFallingPieces:
    """The chunk a bolt destroys breaks off and falls out of the bar (owner, 2026-10-28)."""

    def test_the_piece_fills_exactly_the_hole(self):
        """The piece covers the chunk the shot destroys, on the bar painter's pixels."""
        effect = make_effect(attacker_count=40, defender_count=40)
        for shot in run_until_fired(effect):
            target = effect.sides[shot['target']]
            chunk = min(shot['chunk'], shot['aim'])
            hole = abs(effect._fill_edge(target, shot['aim']) - effect._fill_edge(target, shot['aim'] - chunk))
            piece = shot['fx'].piece
            assert (piece[1] if piece else 0) == hole

    def test_a_piece_falls_for_half_a_second(self):
        from ui.effects.battle_fx_style import BURN_STYLE
        for shot in run_until_fired(make_effect()):
            assert shot['fx'].end >= shot['fx'].land_t + BURN_STYLE['fall']['duration']

    def test_no_damage_no_piece(self):
        effect = make_effect(attacker_initial=1.0, attacker_final=1.0)
        for shot in run_until_fired(effect):
            if shot['target'] == effect.ATTACKER:
                assert shot['fx'].piece is None

    def test_a_piece_renders_while_falling(self):
        """Drawing a piece mid-fall changes the pixels below the bar."""
        effect = make_effect(attacker_count=10, defender_count=10)
        fx = run_until_fired(effect)[0]['fx']
        assert fx.piece
        left, width = fx.piece
        screen = pygame.Surface((1600, 900))
        screen.fill((0, 0, 0))
        before = screen.copy()
        effect.light.draw_pieces(screen, fx, fx.land_t + 0.3)
        below = pygame.Rect(left - 40, fx.bar.bottom, width + 80, fx.bar.height * 2)
        assert (pygame.image.tobytes(screen.subsurface(below), 'RGB')
                != pygame.image.tobytes(before.subsurface(below), 'RGB'))
