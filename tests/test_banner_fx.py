# -*- coding: utf-8 -*-
"""
The banners waving in a breeze and the selected banner's motes (banner FX pass,
2026-10-31): ui/effects/banner_fx_effect.py, styled in ui/effects/banner_fx_style.py.

Unit tests bake the game's own flag pictures, so they need no Game; the game
integration (MapRenderer's three banner blits and the motes) is tested further
down. That the loading screen builds every pose, so play builds none, is in
test_loading_preload.py (TestTheBanners).
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from config.constants import ARMY_CIRCLE_RADIUS, ARMY_FLAG_HEIGHT_RATIO  # noqa: E402
from ui.effects import banner_fx_effect  # noqa: E402
from ui.effects.banner_fx_effect import (BannerWave, BannerMotes, SUB, art_key, measure_layout,  # noqa: E402
                                         register_art, size_step, size_steps)
from ui.effects.banner_fx_style import BANNER_FX_STYLE, BANNER_FX_STYLES, get_banner_fx_style  # noqa: E402
from ui.effects.order_fx_style import SELECTION  # noqa: E402

COLOURS = ('Red', 'Blue', 'Green', 'Yellow')
WAVE = BANNER_FX_STYLE['wave']


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((400, 300))
    yield


@pytest.fixture(scope='module')
def pictures(display):
    """The game's flag pictures, named as the loader in main.py names them: {name: Surface}."""
    found = {}
    for colour in COLOURS:
        for tier in (1, 2, 3):
            path = os.path.join(ROOT, 'assets', 'mapicons', f'{colour}Flag{tier}.png')
            found[f'{colour}Flag{tier}'] = pygame.image.load(path).convert_alpha()
    neutral = pygame.image.load(os.path.join(ROOT, 'assets', 'NeutralFlag.png')).convert_alpha()
    for tier in (1, 2, 3):
        found[f'NeutralFlag{tier}'] = pygame.transform.smoothscale(neutral, found[f'RedFlag{tier}'].get_size())
    for name, picture in found.items():
        register_art(picture, name)
    return found


@pytest.fixture(scope='module')
def wave(pictures):
    w = BannerWave(BANNER_FX_STYLE)
    w.prewarm(list(pictures.values()), [60, 75])
    return w


def _layout_rows(picture, height):
    """The crossbar's last row + 1 and the cloth's end, in rows of a loop `height` px tall."""
    layout = measure_layout(picture)
    return int(round(layout.hang * height)), int(round(layout.cloth_end * height))


def _fresh_loop(picture, height=75):
    """An unbuilt loop (its pose offsets and fold light are still there to read)."""
    lean = WAVE['lean'] if BANNER_FX_STYLE['wind']['direction'][0] >= 0 else -WAVE['lean']
    return banner_fx_effect._Loop(picture, measure_layout(picture), height, WAVE, lean)


def _rows(surface, top, bottom, left=0, right=None):
    right = surface.get_width() if right is None else right
    return pygame.image.tostring(surface.subsurface((left, top, right - left, bottom - top)), 'RGBA')


def _blank(size=(300, 300)):
    surface = pygame.Surface(size)
    surface.fill((0, 0, 0))
    return surface


def _lit(surface):
    """
    The bounding rect of a blank surface's drawn pixels (not near black: the
    neutral flag's edge column has alpha 1); empty if none.
    """
    mask = pygame.mask.from_threshold(surface, (0, 0, 0, 255), (9, 9, 9, 255))
    mask.invert()
    rects = mask.get_bounding_rects()
    return rects[0].unionall(rects[1:]) if rects else pygame.Rect(0, 0, 0, 0)


# ========================================
# Style
# ========================================

class TestStyle:

    def test_both_looks_share_one_style_and_unknown_looks_use_2d(self):
        assert BANNER_FX_STYLES['2d'] is BANNER_FX_STYLES['3d'] is BANNER_FX_STYLE
        assert get_banner_fx_style('nonsense') is BANNER_FX_STYLE

    def test_the_motes_are_the_selection_green(self):
        assert BANNER_FX_STYLE['motes']['colour'] == SELECTION['colour']
        motes = BannerMotes(BANNER_FX_STYLE['motes'], BANNER_FX_STYLE['warm_white'])
        assert motes.raw == tuple(SELECTION['colour'])

    def test_the_size_steps_cover_the_zoom_range(self):
        steps = size_steps()
        assert steps == [50, 55, 60, 65, 70, 75]
        for ui_scale in (1.0, 1.17, 1.33, 1.5):
            # Static banners and marching ones (int(int(radius * ui_scale) * ratio))
            assert size_step(ARMY_CIRCLE_RADIUS * ui_scale * ARMY_FLAG_HEIGHT_RATIO) in steps
            assert size_step(int(int(ARMY_CIRCLE_RADIUS * ui_scale) * ARMY_FLAG_HEIGHT_RATIO)) in steps


# ========================================
# The flag pictures' parts
# ========================================

class TestLayout:

    def test_every_picture_has_a_crossbar_a_cloth_and_a_pole_in_the_middle(self, pictures):
        for name, picture in pictures.items():
            layout = measure_layout(picture)
            assert layout is not None, name
            assert 0.08 < layout.hang < 0.2, name
            assert layout.cloth_end > 0.8, name
            assert layout.pole_right > layout.pole_left, name
            assert abs((layout.pole_left + layout.pole_right) / 2.0 - 0.5) < 0.06, name

    def test_a_swallow_tails_pole_is_kept_still_up_through_its_notch(self, pictures):
        # RedFlag3's pole shows only between its tails, not below them
        for name in ('RedFlag1', 'RedFlag2', 'RedFlag3'):
            layout = measure_layout(pictures[name])
            assert layout.pole_top < layout.cloth_end - 0.1, name


# ========================================
# One picture's loop of poses
# ========================================

class TestTheLoop:

    def test_the_crossbar_and_pole_stay_still_and_the_tails_move(self, pictures, wave):
        for name, picture in pictures.items():
            loop = wave.loops(art_key(picture))[75]
            frames = loop.frames
            hang, _ = _layout_rows(picture, 75)
            first = frames[0]
            for frame in frames[1:]:
                assert _rows(frame, 0, hang) == _rows(first, 0, hang), name
            # The pole's bottom rows (below every tail; Red's are hidden between them)
            if not name.startswith('Red'):
                left, right = loop.anchor - 2, loop.anchor + 2
                for frame in frames[1:]:
                    assert _rows(frame, 72, 75, left, right) == _rows(first, 72, 75, left, right), name
            # The cloth's lower half moves
            assert _rows(frames[0], 45, 70) != _rows(frames[len(frames) // 2], 45, 70), name

    def test_the_loop_is_seamless_smooth_and_never_still(self, pictures):
        for name in ('RedFlag1', 'BlueFlag2', 'GreenFlag3', 'NeutralFlag1'):
            offsets = _fresh_loop(pictures[name])._offsets
            count = len(offsets)
            motion = []
            for i in range(count):
                step = [abs(b - a) for a, b in zip(offsets[i], offsets[(i + 1) % count])]
                # No row moves more than a pixel between poses (last -> first too):
                # drawn crossfaded from one to the next, the motion is continuous
                assert max(step) <= SUB, (name, i)
                motion.append(sum(step))
            # Always moving, and evenly: a breeze, not bursts
            assert min(motion) > 0, name
            assert max(motion) <= 3 * min(motion), (name, motion)

    def test_no_two_poses_in_a_row_are_the_same_picture(self, pictures, wave):
        frames = wave.loops(art_key(pictures['YellowFlag2']))[60].frames
        for i in range(len(frames)):
            assert (pygame.image.tostring(frames[i], 'RGBA')
                    != pygame.image.tostring(frames[(i + 1) % len(frames)], 'RGBA')), i

    def test_a_later_game_finds_its_pictures_frames_built(self, pictures, wave):
        # A new game loads its flags again: new Surfaces, the same art
        again = pygame.image.load(os.path.join(ROOT, 'assets', 'mapicons', 'BlueFlag1.png')).convert_alpha()
        register_art(again, 'BlueFlag1')
        later = BannerWave(BANNER_FX_STYLE)
        later.prewarm([again], [60, 75])
        assert later.frames_built == 0

    def test_a_new_game_drops_the_frames_of_pictures_it_does_not_show(self, pictures, wave):
        saved = dict(banner_fx_effect._LOOPS)
        try:
            shown, gone = pictures['GreenFlag1'].copy(), pictures['GreenFlag2'].copy()
            register_art(shown, 'TestShown')
            register_art(gone, 'TestGone')
            wave.prewarm([shown, gone], [50])
            wave.keep_only([shown])
            arts = {key[0] for key in banner_fx_effect._LOOPS}
            assert arts == {art_key(shown)}
        finally:
            banner_fx_effect._LOOPS.clear()
            banner_fx_effect._LOOPS.update(saved)

    def test_the_layers_are_dropped_once_every_pose_is_built(self, pictures, wave):
        loop = wave.loops(art_key(pictures['BlueFlag1']))[75]
        assert loop.built == len(loop.frames) == WAVE['frames']
        assert loop._cloth is None and loop._offsets is None


# ========================================
# One breeze over the map
# ========================================

class TestTheBreeze:

    def test_neighbours_ripple_nearly_in_step(self, wave):
        count = wave.count
        for clock in (0.0, 1.3, 7.7):
            a = wave.pose(500.0, 400.0, clock)
            b = wave.pose(600.0, 430.0, clock)          # 100 world px downwind
            assert 0 < (a - b) % count <= 3

    def test_a_marching_banner_carries_on_without_a_jump(self, wave):
        count = wave.count
        for start, end in (((400.0, 300.0), (520.0, 330.0)), ((520.0, 330.0), (400.0, 300.0))):
            clock = 3.0
            poses = []
            for frame in range(61):                      # 0.5 s at 120 fps
                progress = frame / 60.0
                x = start[0] + (end[0] - start[0]) * progress
                y = start[1] + (end[1] - start[1]) * progress
                poses.append(wave.pose(x, y, clock + progress * 0.5))
            # It leaves in its territory's pose and arrives in the next one's...
            assert poses[0] == wave.pose(start[0], start[1], clock)
            assert poses[-1] == wave.pose(end[0], end[1], clock + 0.5)
            # ...a pose at a time, and keeps rippling with or against the breeze
            assert all((b - a) % count in (0, 1) for a, b in zip(poses, poses[1:]))
            assert sum((b - a) % count for a, b in zip(poses, poses[1:])) >= 2

    def test_paused_the_pose_holds(self, wave):
        assert wave.pose(300.0, 200.0, 5.0) == wave.pose(300.0, 200.0, 5.0)


# ========================================
# Drawing
# ========================================

class TestDrawing:

    def test_the_pole_base_is_where_the_plain_flags_was(self, pictures, wave):
        for name in ('BlueFlag1', 'GreenFlag2', 'NeutralFlag3'):
            picture = pictures[name]
            surface, plain = _blank(), _blank()
            assert wave.draw(surface, picture, 150, 250, 75.0, 0.0, 0.0, 0.0)
            flag = pygame.transform.smoothscale(picture, (int(75 * picture.get_width() / picture.get_height()), 75))
            plain.blit(flag, (150 - flag.get_width() // 2, 250 - 75))
            bounds, before = _lit(surface), _lit(plain)
            assert abs(bounds.bottom - before.bottom) <= 1 and abs(bounds.top - before.top) <= 1, name
            # The pole's lowest pixels in the same place
            row = [x for x in range(300) if max(surface.get_at((x, bounds.bottom - 1))[:3]) > 8]
            old = [x for x in range(300) if max(plain.get_at((x, before.bottom - 1))[:3]) > 8]
            assert abs((row[0] + row[-1]) / 2.0 - (old[0] + old[-1]) / 2.0) <= 1.0, name

    def test_between_two_poses_it_is_drawn_crossfaded(self, pictures, wave):
        picture = pictures['RedFlag2']
        loop = wave.loops(art_key(picture))[75]
        frames = loop.frames
        # The breeze halfway from pose 4 to pose 5 at world (0, 0)
        clock = (4.5 / len(frames)) * WAVE['period']
        drawn, pose, following = _blank(), _blank(), _blank()
        assert wave.draw(drawn, picture, 150, 250, 75.0, 0.0, 0.0, clock)
        pose.blit(frames[4], (150 - loop.anchor, 250 - 75))
        following.blit(frames[5], (150 - loop.anchor, 250 - 75))
        # Below fade_top (the rows moving half a pixel or more) a mix of the two;
        # above it, where rows move a quarter pixel at most, the pose alone
        split = 250 - 75 + loop.fade_top
        assert 175 < split < 250
        assert _rows(drawn, 0, split) == _rows(pose, 0, split)
        assert _rows(drawn, split, 300) != _rows(pose, split, 300)
        assert _rows(drawn, split, 300) != _rows(following, split, 300)
        # The frames keep their per-pixel alpha (set_alpha(None) would switch it off):
        # a soft edge pixel still blends with what is under it
        assert all(frame.get_alpha() == 255 for frame in frames)
        edge = _blank((100, 100))
        edge.blit(frames[5], (0, 0))
        soft = [(x, y) for x in range(frames[5].get_width()) for y in range(75)
                if 40 < frames[5].get_at((x, y))[3] < 200 and frames[5].get_at((x, y))[0] > 100]
        assert soft and all(edge.get_at(p)[0] < frames[5].get_at(p)[0] for p in soft)

    def test_an_unknown_picture_is_left_to_the_plain_flag(self, wave):
        surface = _blank()
        stranger = pygame.Surface((20, 30), pygame.SRCALPHA)
        assert not wave.draw(surface, stranger, 150, 250, 75.0, 0.0, 0.0, 0.0)
        assert _lit(surface).width == 0

    def test_a_flag_follows_its_picture_to_any_player(self, pictures, wave):
        # Campaign missions move pictures between players: the frames are the picture's
        for name in ('RedFlag2', 'YellowFlag2'):
            frame, loop = wave.frame(pictures[name], 75.0, 0.0, 0.0, 0.0)
            assert loop is wave.loops(art_key(pictures[name]))[75]

    def test_built_in_play_within_the_budget_never_drawing_nothing(self, pictures):
        fresh = pictures['GreenFlag1'].copy()
        register_art(fresh, 'TestFlagInPlay')
        wave = BannerWave(BANNER_FX_STYLE)
        surface = _blank((800, 300))
        drawn = []
        for frame in range(12):
            wave.begin_frame()
            built = wave.frames_built
            # Twenty banners across the map: twenty poses wanted
            drawn.append([wave.draw(surface, fresh, 20 + 35 * i, 250, 60.0, 80.0 * i, 0.0, frame / 120.0)
                          for i in range(20)])
            assert wave.frames_built - built <= BannerWave.BUILDS_PER_FRAME
        # From the first frame on, every banner waves (the nearest built pose meanwhile)
        assert all(all(row) for row in drawn)

    def test_over_budget_a_new_size_borrows_the_nearest_built_one(self, pictures):
        fresh = pictures['BlueFlag3'].copy()
        register_art(fresh, 'TestFlagSizes')
        wave = BannerWave(BANNER_FX_STYLE)
        wave.prewarm([fresh], [60])
        wave.begin_frame()
        wave._budget.left = 0                           # spent
        surface = _blank()
        assert wave.draw(surface, fresh, 150, 250, 75.0, 0.0, 0.0, 0.0)
        assert _lit(surface).height <= 61


# ========================================
# The selected banner's motes
# ========================================

class TestMotes:

    @pytest.fixture
    def motes(self):
        motes = BannerMotes(BANNER_FX_STYLE['motes'], BANNER_FX_STYLE['warm_white'])
        motes.prewarm(size_steps())
        return motes

    def test_they_light_up_when_a_banner_is_selected(self, motes):
        surface = _blank()
        motes.draw(surface, 'army', 150, 250, 75.0, 2.0)
        assert _lit(surface).width == 0                   # strength 0 on the first frame
        for k in range(1, 21):
            motes.draw(surface, 'army', 150, 250, 75.0, 2.0 + k / 120.0)
        assert _lit(surface).width > 0

    def test_they_rise_from_the_pole_base_to_the_banners_top(self, motes):
        lower = upper = 0
        top_row = bottom_row = None
        for k in range(480):                              # 4 s at 120 fps
            surface = _blank()
            motes.draw(surface, 'army', 150, 250, 75.0, k / 120.0)
            lit = _lit(surface)
            if lit.width == 0:
                continue
            top, bottom = lit.top, lit.bottom
            top_row = top if top_row is None else min(top_row, top)
            bottom_row = bottom if bottom_row is None else max(bottom_row, bottom)
            lower += _lit(surface.subsurface((0, 215, 300, 40))).width > 0
            upper += _lit(surface.subsurface((0, 175, 300, 40))).width > 0
        halo = int(0.15 * 75 * BANNER_FX_STYLE['motes']['tint_size'])
        # Within the banner's height, a halo's reach beyond it at most...
        assert bottom_row <= 250 + halo // 2 + 2
        assert top_row >= 250 - 75 - halo // 2 - 2
        # ...and seen both low and high: they travel up
        assert lower > 100 and upper > 100

    def test_drawing_builds_nothing_once_prewarmed(self, motes):
        built = (motes.glow.sprites_built, motes.tint.sprites_built)
        surface = _blank()
        for k in range(60):
            motes.begin_frame()
            motes.draw(surface, 'army', 150, 250, 50.0 + k * 0.4, k / 60.0)
        assert (motes.glow.sprites_built, motes.tint.sprites_built) == built

    def test_paused_they_hold_still(self, motes):
        for k in range(30):                              # lit up
            motes.draw(_blank(), 'army', 150, 250, 75.0, 1.0 + k / 120.0)
        paused = 1.0 + 29 / 120.0
        surface, again = _blank(), _blank()
        motes.draw(surface, 'army', 150, 250, 75.0, paused)
        motes.draw(again, 'army', 150, 250, 75.0, paused)
        assert _lit(surface).width > 0
        assert pygame.image.tostring(surface, 'RGB') == pygame.image.tostring(again, 'RGB')


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
def armies(game):
    """
    Near the screen centre: a territory of player 0 (12 armies), one shared with
    player 1 (two flags) and an army of player 0 marching between them; all
    undone afterwards.
    """
    import copy
    import map_data
    from game_state import ArmyAnimation
    gs = game.game_state
    kept = (dict(gs.territory_owners), dict(gs.armies), copy.deepcopy(gs.territory_garrisons))
    width, height = game.screen.get_size()
    home = min((t for t in game.scaled_centers if map_data.get_neighbors(t)),
               key=lambda t: (game.world_to_screen(game.scaled_centers[t])[0] - width / 2) ** 2
               + (game.world_to_screen(game.scaled_centers[t])[1] - height / 2) ** 2)
    shared = map_data.get_neighbors(home)[0]
    gs.territory_owners[home] = gs.territory_owners[shared] = 0
    gs.armies[home], gs.armies[shared] = 12, 7
    gs.territory_garrisons[home] = {0: {'unmoved': 12, 'moved': 0}}
    gs.territory_garrisons[shared] = {0: {'unmoved': 4, 'moved': 0}, 1: {'unmoved': 3, 'moved': 0}}
    gs._territory_owners_version += 1
    march = ArmyAnimation(home, shared, 3, 0, [], {})
    march.progress = 0.5
    gs.active_animations.append(march)
    yield home, shared, march
    gs.active_animations.remove(march)
    gs.selected_army = None
    game.show_army_composition = False
    gs.territory_owners, gs.armies, gs.territory_garrisons = kept
    gs._territory_owners_version += 1


def _spy(monkeypatch, target, name):
    calls = []
    real = getattr(target, name)

    def spy(*args):
        result = real(*args)
        calls.append((args, result))
        return result

    monkeypatch.setattr(target, name, spy)
    return calls


class TestInGame:

    def test_every_banner_waves_garrisons_shared_and_marching(self, game, armies, monkeypatch):
        home, shared, march = armies
        calls = _spy(monkeypatch, game.map_renderer.banner_wave, 'draw')
        game.draw()
        worlds = [(args[5], args[6]) for args, _ in calls]
        assert all(result for _, result in calls)
        # The home garrison at its centre...
        assert game.scaled_centers[home] in worlds
        # ...two flags in the shared territory, at its flag positions...
        positions = game.game_state.get_flag_positions_for_territory(shared, *game.scaled_centers[shared], 2)
        assert all(tuple(p) in worlds for p in positions)
        # ...and the marching banner halfway, nowhere near either centre
        (hx, hy), (sx, sy) = game.scaled_centers[home], game.scaled_centers[shared]
        midway = [w for w in worlds if min(abs(w[0] - hx) + abs(w[1] - hy), abs(w[0] - sx) + abs(w[1] - sy)) > 5
                  and w not in positions]
        assert midway

    def test_the_selected_banner_has_motes_at_its_pole_base(self, game, armies, monkeypatch):
        home, _, _ = armies
        calls = _spy(monkeypatch, game.map_renderer.banner_motes, 'draw')
        game.draw()
        assert calls == []                                  # nothing selected
        game.game_state.selected_army = (home, 12)
        game.draw()
        assert len(calls) == 1
        (_, selection, x, y, height, _), _ = calls[0]
        assert (x, y) == game.world_to_screen(game.scaled_centers[home])
        assert height == pytest.approx(ARMY_CIRCLE_RADIUS * game.get_ui_scale_factor() * ARMY_FLAG_HEIGHT_RATIO)

    def test_in_a_shared_territory_they_rise_from_the_chosen_players_flag(self, game, armies, monkeypatch):
        _, shared, _ = armies
        calls = _spy(monkeypatch, game.map_renderer.banner_motes, 'draw')
        game.show_army_composition = True
        game.army_composition_territory = shared
        game.army_composition_player = 1
        game.draw()
        assert len(calls) == 1
        (_, selection, x, y, _, _), _ = calls[0]
        index = game.game_state.assign_garrison_position(shared, 1, 2)
        position = game.game_state.get_flag_positions_for_territory(shared, *game.scaled_centers[shared], 2)[index]
        assert (x, y) == game.world_to_screen(position)
        assert selection == (shared, 1)
