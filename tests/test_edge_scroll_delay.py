# -*- coding: utf-8 -*-
"""
Regression tests for the Map Edge scrolling dwell delay.

Map Edge puts its 20px trigger band *inside* the map viewport, directly above the
bottom UI panel and below the top panel. Without a dwell requirement, a player
simply travelling down to a bottom-UI button drags the camera along with them.

handle_edge_scrolling() therefore requires the cursor to stay inside a band for
MAP_EDGE_SCROLL_DELAY seconds before it starts scrolling. Window Edge mode is
deliberately exempt: there the band is the physical window border, so entering it
is always intentional.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_PANEL = 40
MAP_HEIGHT_UI = 649
BOTTOM_UI_Y = TOP_PANEL + MAP_HEIGHT_UI  # 689
PAN_SPEED = 10.0
DT = 1.0 / 60.0

# Screen positions used by the tests
IN_BOTTOM_BAND = (800, 680)   # map_relative_y = 640, inside the last 20px
IN_LEFT_BAND = (5, 300)       # x < edge_scroll_margin
MID_MAP = (800, 300)          # no band
ON_BOTTOM_UI = (800, 700)     # past bottom_ui_y - hits the map-area guard


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
    # Map deliberately larger than the viewport on both axes so clamp_to_bounds()
    # does not pin the offset and mask a scroll
    cam = CameraHandler(3000, 2000, 1600, 900, MAP_HEIGHT_UI, initial_zoom=1.65)
    cam.offset = [500.0, 500.0]
    return cam


def scroll(camera, pos, mode="map_edge", dt=DT, frames=1, enabled=True):
    """Run N frames of edge scrolling at a fixed cursor position."""
    for _ in range(frames):
        camera.handle_edge_scrolling(
            pos, enabled, mode, PAN_SPEED, TOP_PANEL, BOTTOM_UI_Y, dt
        )


def test_quick_transit_through_band_does_not_scroll(camera):
    """The reported bug: crossing the bottom band on the way to the UI must not pan."""
    from input.camera_handler import MAP_EDGE_SCROLL_DELAY

    before = list(camera.offset)
    # ~100ms of transit, comfortably under the delay
    frames = int((MAP_EDGE_SCROLL_DELAY / 2) / DT)
    scroll(camera, IN_BOTTOM_BAND, frames=frames)

    assert camera.offset == before
    assert camera.debug_edge_scroll is None


def test_dwelling_past_the_delay_scrolls(camera):
    """Holding the cursor in the band still pans, just after a short wait."""
    from input.camera_handler import MAP_EDGE_SCROLL_DELAY

    before = list(camera.offset)
    frames = int(MAP_EDGE_SCROLL_DELAY / DT) + 2
    scroll(camera, IN_BOTTOM_BAND, frames=frames)

    assert camera.offset[1] > before[1]
    assert camera.debug_edge_scroll is not None


def test_leaving_the_band_resets_the_dwell(camera):
    """Dwell credit must not survive a trip back into the middle of the map."""
    from input.camera_handler import MAP_EDGE_SCROLL_DELAY

    # Accumulate almost enough
    scroll(camera, IN_BOTTOM_BAND, frames=int(MAP_EDGE_SCROLL_DELAY / DT) - 1)
    assert camera.offset[1] == 500.0  # still held back

    scroll(camera, MID_MAP)  # leaves every band
    assert camera._map_edge_dwell == 0.0

    # One frame back in the band must not be enough to fire
    before = list(camera.offset)
    scroll(camera, IN_BOTTOM_BAND)
    assert camera.offset == before


def test_crossing_onto_the_ui_resets_the_dwell(camera):
    """The map-area guard returns early; it must clear the timer as it does."""
    from input.camera_handler import MAP_EDGE_SCROLL_DELAY

    scroll(camera, IN_BOTTOM_BAND, frames=int(MAP_EDGE_SCROLL_DELAY / DT) - 1)
    scroll(camera, ON_BOTTOM_UI)
    assert camera._map_edge_dwell == 0.0

    before = list(camera.offset)
    scroll(camera, IN_BOTTOM_BAND)
    assert camera.offset == before


def test_delay_applies_to_all_four_bands(camera):
    """Left/right/top bands dwell too, so the feel is consistent."""
    from input.camera_handler import MAP_EDGE_SCROLL_DELAY

    before = list(camera.offset)
    scroll(camera, IN_LEFT_BAND, frames=int((MAP_EDGE_SCROLL_DELAY / 2) / DT))
    assert camera.offset == before

    scroll(camera, IN_LEFT_BAND, frames=int(MAP_EDGE_SCROLL_DELAY / DT) + 2)
    assert camera.offset[0] < before[0]


def test_window_edge_mode_is_unchanged(camera):
    """Window Edge must still scroll on the very first frame."""
    before = list(camera.offset)
    scroll(camera, (800, 2), mode="window_edge")

    assert camera.offset[1] < before[1]
    assert camera._map_edge_dwell == 0.0


def test_disabled_edge_scrolling_clears_the_dwell(camera):
    from input.camera_handler import MAP_EDGE_SCROLL_DELAY

    scroll(camera, IN_BOTTOM_BAND, frames=int(MAP_EDGE_SCROLL_DELAY / DT) - 1)
    scroll(camera, IN_BOTTOM_BAND, enabled=False)
    assert camera._map_edge_dwell == 0.0


def test_settings_default_mode_is_window_edge():
    """The old 'push' default matched neither branch and skipped the map-area guard."""
    from settings_manager import settings

    assert settings.defaults['edge_scrolling_mode'] == 'window_edge'


def test_legacy_mode_values_are_coerced():
    """A config.json still holding 'push'/'jump' must normalise on load."""
    from settings_manager import settings

    original = settings.settings.get('edge_scrolling_mode')
    try:
        for legacy in ('push', 'jump', 'nonsense'):
            settings.settings['edge_scrolling_mode'] = legacy
            settings._validate_and_clean_settings()
            assert settings.settings['edge_scrolling_mode'] == 'window_edge'

        # A valid value is left alone
        settings.settings['edge_scrolling_mode'] = 'map_edge'
        settings._validate_and_clean_settings()
        assert settings.settings['edge_scrolling_mode'] == 'map_edge'
    finally:
        settings.settings['edge_scrolling_mode'] = original
