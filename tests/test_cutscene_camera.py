# -*- coding: utf-8 -*-
"""
Tests: the cutscene camera glides at sub-pixel accuracy.

The player used to cut each slide's camera view at whole picture pixels - every edge
truncated on its own - and stretch the cut to the screen. Enlarged 1-4x (most slides), the
picture froze, then jumped 1-4 px, and its scale wobbled as the cut's width toggled, so parts
of it moved at different moments, sometimes backwards: the stutter the owner saw in the
campaign cutscenes. _plan_axis() now picks the cut so that pygame's smoothscale lands the view
within a fraction of a pixel. These tests track 1 px lines through the real smoothscale.

Also: crossfades keep full brightness, huge pictures shrink from a half-size copy, opaque
pictures load without alpha. See "Cutscene camera" in docs/CODE_GUIDE.md.
"""

import json
import os
import struct
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SCREEN = (1600, 900)  # the owner's resolution
FPS = 120


@pytest.fixture(scope="module")
def pg():
    import pygame
    pygame.init()
    # convert() needs a display; the frames themselves go to offscreen surfaces
    pygame.display.set_mode((64, 64))
    yield pygame
    pygame.quit()


def _player(pg, monkeypatch, slides, size=SCREEN):
    """A CutscenePlayer over the given slides, drawing to an offscreen surface of `size`."""
    from cutscene_player import CutscenePlayer

    def fake_load(self, cutscene_id):
        self.cutscene_data = {'slides': slides}
        self.slides = slides

    monkeypatch.setattr(CutscenePlayer, '_load_cutscene_data', fake_load)
    return CutscenePlayer(pg.Surface(size), 'test_cutscene')


def _line_grid(pg, w, h, step=60):
    """A black picture with 1 px white lines every `step` px; returns it and the lines' x, y."""
    picture = pg.Surface((w, h))
    xs = list(range(step // 2, w, step))
    ys = list(range(step // 2, h, step))
    for x in xs:
        pg.draw.line(picture, (255, 255, 255), (x, 0), (x, h - 1))
    for y in ys:
        pg.draw.line(picture, (255, 255, 255), (0, y), (w - 1, y))
    return picture.convert(), xs, ys


def _line_centres(pg, frame, expected, horizontal):
    """
    Where each line crosses a row (or column) near the frame's middle: the brightness-weighted
    centre around its expected position, in screen px. None for lines near the frame's edge.
    """
    w, h = frame.get_size()
    strip = (0, h // 2 + 3, w, 1) if horizontal else (w // 2 + 3, 0, 1, h)
    values = pg.image.tobytes(frame.subsurface(strip), 'RGB')[0::3]
    limit = w if horizontal else h
    centres = []
    for e in expected:
        if not 40 < e < limit - 40:
            centres.append(None)
            continue
        lo = int(e) - 8
        window = values[lo:lo + 17]
        total = sum(window)
        centres.append(sum((lo + k + 0.5) * v for k, v in enumerate(window)) / total if total else None)
    return centres


def _track(pg, player, xs, ys, progresses):
    """
    Draw slide 0 at each progress and follow its lines. Returns the worst error (px from where
    the line belongs), the largest backward move, and the worst jump beyond the true motion.
    """
    slide = player.slides[0]
    a, b = slide['camera_a'], slide['camera_b']
    frame = pg.Surface(player.screen.get_size())
    sw, sh = frame.get_size()
    worst_error = largest_backward = worst_extra = 0.0
    previous = None
    for progress in progresses:
        frame.fill((0, 0, 0))
        surface, offset = player._scaled_slide(0, progress)
        frame.blit(surface, offset)
        x, y, vw, vh = (a[k] + (b[k] - a[k]) * progress for k in ('x', 'y', 'width', 'height'))
        ideal_x = [(p + 0.5 - x) * sw / vw for p in xs]
        ideal_y = [(p + 0.5 - y) * sh / vh for p in ys]
        seen = _line_centres(pg, frame, ideal_x, True) + _line_centres(pg, frame, ideal_y, False)
        current = [(s, i) if s is not None else None for s, i in zip(seen, ideal_x + ideal_y)]
        for c in current:
            if c:
                worst_error = max(worst_error, abs(c[0] - c[1]))
        if previous:
            for c, p in zip(current, previous):
                if c and p:
                    moved, should = c[0] - p[0], c[1] - p[1]
                    if moved * should < 0:
                        largest_backward = max(largest_backward, abs(moved))
                    worst_extra = max(worst_extra, abs(moved) - abs(should))
        previous = current
    return worst_error, largest_backward, worst_extra


def test_slow_pan_glides(pg, monkeypatch):
    """A slow pan at 1.74x, most slides' zoom. Old crop: 3.04 px off, jumps 1.78 px too far."""
    picture, xs, ys = _line_grid(pg, 1536, 1024)
    slide = {'camera_a': {'x': 100, 'y': 200, 'width': 921, 'height': 518},
             'camera_b': {'x': 104.8, 'y': 201.8, 'width': 921, 'height': 518},
             'pan_duration': 0.5, 'easing': 'linear'}
    player = _player(pg, monkeypatch, [slide])
    player._images[0] = picture
    error, backward, extra = _track(pg, player, xs, ys, [f / 60 for f in range(61)])
    assert error < 0.6
    assert backward < 0.5
    assert extra < 1.0


def test_zoom_glides(pg, monkeypatch):
    """
    Mission 3 intro's opening (4.26x zooming out over 8 s), the worst stutter. Old crop: 5.74 px
    off, lines moving 2.87 px backwards and jumping 3.60 px too far.
    """
    picture, xs, ys = _line_grid(pg, 1536, 1024)
    slide = {'camera_a': {'x': 338.91, 'y': 138.52, 'width': 375.72, 'height': 211.34},
             'camera_b': {'x': 59.65, 'y': 80.61, 'width': 1344.2, 'height': 756.12},
             'pan_duration': 8.0, 'easing': 'linear'}
    player = _player(pg, monkeypatch, [slide])
    player._images[0] = picture
    error, backward, extra = _track(pg, player, xs, ys, [f / (8.0 * FPS) for f in range(60)])
    assert error < 0.6
    assert backward < 0.5
    assert extra < 1.0


def _png_size(path):
    with open(path, 'rb') as f:
        return struct.unpack('>II', f.read(24)[16:24])


@pytest.mark.parametrize('screen', [(1280, 720), SCREEN, (1920, 1080)])
def test_every_slide_covers_the_screen(screen):
    """Every slide's camera path, sampled: the cut stays inside the picture, the scaled cut
    covers the whole screen (no black edge)."""
    from cutscene_player import EASING_FUNCTIONS, _plan_axis
    with open(os.path.join(ROOT, 'cutscene_data.json'), encoding='utf-8') as f:
        data = json.load(f)
    checked = 0
    for cutscene in data.values():
        for slide in cutscene['slides']:
            image = _png_size(os.path.join(ROOT, slide['image']))
            a = slide['camera_a']
            b = slide.get('camera_b', a)
            ease = EASING_FUNCTIONS[slide.get('easing', 'ease_in_out')]
            frames = int(slide.get('pan_duration', 5.0) * FPS)
            for f in range(0, frames + 1, 15):
                p = ease(f / frames)
                for axis, (pos, size) in enumerate((('x', 'width'), ('y', 'height'))):
                    view_size = max(1, a[size] + (b[size] - a[size]) * p)
                    view_pos = a[pos] + (b[pos] - a[pos]) * p
                    start, length, offset, scaled = _plan_axis(view_pos, view_size, image[axis], screen[axis])
                    assert 0 <= start and length >= 1 and start + length <= image[axis]
                    assert offset <= 0 and offset + scaled >= screen[axis]
                    checked += 1
    assert checked > 5000


@pytest.mark.parametrize('worker', [False, True])
def test_crossfade_keeps_full_brightness(pg, monkeypatch, worker):
    """Two white slides at a crossfade's midpoint stay white (both used to fade on black:
    189 of 255). With or without the worker thread run() uses."""
    white = pg.Surface((320, 180))
    white.fill((255, 255, 255))
    view = {'x': 0, 'y': 0, 'width': 320, 'height': 180}
    slides = [{'camera_a': view, 'pan_duration': 2.0, 'easing': 'linear'},
              {'camera_a': view, 'pan_duration': 2.0, 'easing': 'linear', 'crossfade_duration': 1.0}]
    player = _player(pg, monkeypatch, slides, size=(320, 180))
    player._images = {0: white.convert(), 1: white.convert()}
    if worker:
        player._scale_worker = ThreadPoolExecutor(max_workers=1)
    try:
        player._global_elapsed = 1.5  # slide 2 starts at 1.0: halfway through the crossfade
        player.screen.fill((0, 0, 0))
        player._render_cutscene_frame()
    finally:
        if worker:
            player._scale_worker.shutdown()
    assert min(player.screen.get_at((160, 90))[:3]) >= 250


def _mean_difference(pg, one, other):
    """Mean absolute difference of two same-size frames, 0-255: |a-b| = (a-b)+ + (b-a)+."""
    up = one.copy()
    up.blit(other, (0, 0), special_flags=pg.BLEND_RGB_SUB)
    down = other.copy()
    down.blit(one, (0, 0), special_flags=pg.BLEND_RGB_SUB)
    return (sum(pg.transform.average_color(up)[:3]) + sum(pg.transform.average_color(down)[:3])) / 3


def _soft_picture(pg, w, h):
    """A painting-like picture: colour gradients and soft blobs."""
    picture = pg.Surface((w, h))
    for x in range(w):
        pg.draw.line(picture, (x * 255 // w, 90, 255 - x * 255 // w), (x, 0), (x, h - 1))
    for i in range(12):
        pg.draw.circle(picture, ((i * 70) % 256, (i * 40) % 256, (i * 110) % 256),
                       ((i * 157) % w, (i * 89) % h), 30 + (i * 13) % 50)
    soft = pg.transform.smoothscale(pg.transform.smoothscale(picture, (w // 8, h // 8)), (w, h))
    return soft.convert()


def test_huge_picture_shrinks_from_a_half_size_copy(pg, monkeypatch, tmp_path):
    """A picture at least twice the screen gets a half-size copy, used while the view is at
    least twice the screen - and the frame looks the same as from the full picture (on the
    real 4096 px picture: 1-2 of 255 apart)."""
    big = _soft_picture(pg, 1024, 768)
    small = _soft_picture(pg, 400, 300)
    pg.image.save(big, str(tmp_path / 'big.png'))
    pg.image.save(small, str(tmp_path / 'small.png'))
    view = {'x': 30.4, 'y': 41.7, 'width': 900, 'height': 506.25}
    slides = [{'image': str(tmp_path / 'big.png'), 'camera_a': view},
              {'image': str(tmp_path / 'small.png'), 'camera_a': {'x': 0, 'y': 0, 'width': 320, 'height': 180}}]
    player = _player(pg, monkeypatch, slides, size=(320, 180))
    assert set(player._half_images) == {0}

    def frame():
        surface, offset = player._scaled_slide(0, 0.0)
        out = pg.Surface((320, 180))
        out.blit(surface, offset)
        return out

    from_half = frame()
    player._half_images.clear()
    from_full = frame()
    assert _mean_difference(pg, from_half, from_full) < 3.0


def test_opaque_pictures_load_without_alpha(pg, tmp_path):
    """Opaque pictures (RGB, or RGBA with alpha 255 everywhere) load without alpha; one with a
    transparent pixel keeps it."""
    from cutscene_player import CutscenePlayer
    rgb = pg.Surface((8, 8))
    rgb.fill((10, 20, 30))
    opaque = pg.Surface((8, 8), pg.SRCALPHA)
    opaque.fill((10, 20, 30, 255))
    holed = opaque.copy()
    holed.set_at((3, 3), (0, 0, 0, 0))
    for name, surface in (('rgb', rgb), ('opaque', opaque), ('holed', holed)):
        pg.image.save(surface, str(tmp_path / f'{name}.png'))
    assert not CutscenePlayer._load_picture(str(tmp_path / 'rgb.png')).get_flags() & pg.SRCALPHA
    assert not CutscenePlayer._load_picture(str(tmp_path / 'opaque.png')).get_flags() & pg.SRCALPHA
    assert CutscenePlayer._load_picture(str(tmp_path / 'holed.png')).get_flags() & pg.SRCALPHA
