# -*- coding: utf-8 -*-
"""
Regression tests for smooth (eased) mouse-wheel zoom.

handle_zoom() sets a TARGET; update_zoom() eases toward it each frame. Anything
that drives camera.zoom directly (campaign/start camera animations) must first
call cancel_zoom_interpolation(), or a pending wheel target fights the animation.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_PANEL = 40
DT = 1.0 / 60.0


@pytest.fixture(scope="module")
def pygame_display():
    import pygame
    pygame.init()
    pygame.display.set_mode((1600, 900))
    yield pygame
    pygame.quit()


@pytest.fixture
def camera(pygame_display):
    from input.camera_handler import CameraHandler
    # Map/window sizes matching a 1600x900 game window
    return CameraHandler(865, 649, 1600, 900, 649, initial_zoom=1.65)


def settle(camera, dt=DT, max_frames=500):
    """Run the easing to completion; returns the number of frames taken."""
    frames = 0
    while camera.update_zoom(dt) and frames < max_frames:
        frames += 1
    return frames


def test_wheel_sets_target_without_jumping(camera):
    """A wheel notch must not move the zoom instantly — that was the old behaviour."""
    before = camera.zoom
    assert camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL) is True
    assert camera.zoom == before, "zoom jumped on the event frame instead of easing"
    assert camera.target_zoom > before


def test_zoom_eases_over_multiple_frames(camera):
    camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL)
    frames = settle(camera)
    assert frames > 3, f"eased over only {frames} frames — not smooth"
    assert camera.zoom == pytest.approx(camera.target_zoom, abs=1e-6)


def test_rapid_notches_accumulate(camera):
    """Several notches in one frame compound, rather than each restarting the ease."""
    for _ in range(5):
        camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL)
    assert camera.target_zoom == pytest.approx(1.65 * (1.078 ** 5), abs=1e-6)


def test_zoom_to_cursor_holds_through_easing(camera):
    """
    The world point under the cursor stays put for the WHOLE interpolation.

    Tested at a zoom where the camera is not pinned by clamp_to_bounds(); at min
    zoom the map is narrower than the viewport, so bounds legitimately move the
    camera and the anchor cannot hold (same as the original implementation).
    """
    camera.zoom = 3.0
    camera.target_zoom = 3.0
    camera.offset = [150.0, 120.0]
    camera.clamp_to_bounds()
    anchor = (1100, 300)

    before = camera.screen_to_world(anchor, TOP_PANEL)
    camera.handle_zoom(+1, anchor, 0.078, TOP_PANEL)
    settle(camera)
    after = camera.screen_to_world(anchor, TOP_PANEL)

    drift = max(abs(before[0] - after[0]), abs(before[1] - after[1]))
    # Sub-pixel: 0.5 world px at zoom 3.0 is ~1.5 screen px
    assert drift < 0.5, f"cursor anchor drifted {drift:.3f} world px"


def test_zoom_clamps_to_limits(camera):
    for _ in range(60):
        camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL)
    settle(camera)
    assert camera.zoom == pytest.approx(camera.max_zoom)
    # Further zoom-in at the limit is a no-op
    assert camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL) is False


@pytest.mark.parametrize('fps', [30, 60, 165])
def test_easing_is_frame_rate_independent(camera, fps):
    """Same target and similar duration regardless of frame rate."""
    camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL)
    target = camera.target_zoom
    dt = 1.0 / fps
    frames = settle(camera, dt=dt)
    assert camera.zoom == pytest.approx(target, abs=1e-6)
    elapsed = frames * dt
    assert 0.15 < elapsed < 0.8, f"settle took {elapsed:.3f}s at {fps} FPS"


def test_camera_animation_cancels_pending_wheel_zoom(camera):
    """A campaign/start animation drives zoom directly and must win."""
    from tutorial_mission import CameraAnimation

    camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL)
    assert camera._zoom_interpolating

    CameraAnimation(camera, 1.65, 4.0, 1.5, (400, 300), 1600, 649)
    assert not camera._zoom_interpolating, (
        "pending wheel zoom would fight the camera animation")
    # And update_zoom must not move the camera any more
    assert camera.update_zoom(DT) is False


def test_reset_camera_clears_interpolation(camera):
    camera.handle_zoom(+1, (800, 400), 0.078, TOP_PANEL)
    camera.reset_camera()
    assert not camera._zoom_interpolating
    assert camera.target_zoom == camera.zoom
    assert camera.update_zoom(DT) is False
