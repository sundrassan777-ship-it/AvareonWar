# -*- coding: utf-8 -*-
"""
Tests for rendering/helpers.py DrawingHelpers.

Focused on draw_feedback_button()'s behaviour when its background image is
missing. Every image-backed button in the game (Menu, Players, Resolve Remaining
Battles, Close All Battle Reports, the alliance popup) passes base_color=None and
relies on bg_image. pygame.image.load() failures are caught at startup and leave
that image as None, so the solid-colour fallback path must cope with both being
None rather than raising "invalid color argument".
"""

import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from config.font_manager import FontManager  # noqa: E402
from rendering.helpers import DrawingHelpers, DEFAULT_BUTTON_COLOR  # noqa: E402


@pytest.fixture(scope='module')
def screen():
    pygame.init()
    pygame.display.set_mode((400, 200))
    surface = pygame.display.get_surface()
    yield surface
    pygame.display.quit()
    pygame.quit()


@pytest.fixture
def helpers(screen):
    font_manager = FontManager()
    font = font_manager.get_font(12)
    bold = font_manager.get_bold_font(12)
    screen.fill((0, 0, 0))
    return DrawingHelpers(screen, font, bold, font)


RECT = pygame.Rect(10, 10, 120, 30)


class TestMissingButtonImage:

    def test_no_image_and_no_colour_does_not_raise(self, helpers):
        """The exact combination a failed GMenuButton.png load produces."""
        helpers.draw_feedback_button(
            RECT, None, (-1, -1), None, 'top_button', 'menu',
            text="Menu", bg_image=None)

    def test_falls_back_to_the_default_colour(self, helpers, screen):
        helpers.draw_feedback_button(
            RECT, None, (-1, -1), None, 'top_button', 'menu', bg_image=None)
        assert screen.get_at(RECT.center)[:3] == DEFAULT_BUTTON_COLOR

    def test_hover_still_brightens_the_fallback(self, helpers, screen):
        helpers.draw_feedback_button(
            RECT, None, RECT.center, None, 'top_button', 'menu', bg_image=None)
        hovered = screen.get_at(RECT.center)[:3]
        assert hovered != DEFAULT_BUTTON_COLOR
        assert sum(hovered) > sum(DEFAULT_BUTTON_COLOR)

    def test_click_flash_still_brightens_the_fallback(self, helpers, screen):
        helpers.draw_feedback_button(
            RECT, None, (-1, -1), ('top_button', 'menu'),
            'top_button', 'menu', bg_image=None)
        clicked = screen.get_at(RECT.center)[:3]
        assert sum(clicked) > sum(DEFAULT_BUTTON_COLOR)

    def test_explicit_colour_is_not_overridden(self, helpers, screen):
        """The fallback must only apply when the caller supplied nothing."""
        helpers.draw_feedback_button(
            RECT, (10, 120, 200), (-1, -1), None,
            'top_button', 'menu', bg_image=None)
        assert screen.get_at(RECT.center)[:3] == (10, 120, 200)
