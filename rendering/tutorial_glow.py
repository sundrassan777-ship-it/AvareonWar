# -*- coding: utf-8 -*-
"""
Tutorial Glow

The gold glow round a control a campaign mission or the tutorial points at - a
build or training button, a sidebar tab, a technology, End Turn, Select All, a
quick-access icon on the map (order FX pass, 2026-10: gold is the colour of the
player's input to give). Additive light hugging the control's outline
(light_fx.GlowFrame), breathing; styled by order_fx_style GUIDE.

One per Game (Game.tutorial_glow), shared by the bottom panel, the sidebar and
the map renderer.
"""

import math

import pygame

from ui.effects.light_fx import GlowFrame
from ui.effects.order_fx_style import GUIDE

ADD = pygame.BLEND_RGB_ADD


class TutorialGlow:
    """Draws the breathing gold glow round rectangles, circles and button sprites."""

    def __init__(self, style=GUIDE, scale=1.0):
        self.style = style
        self.colour = tuple(style['colour'])
        self.frames = GlowFrame(reach=style['reach'] * scale)

    def level(self, seconds=None):
        """This moment's brightness level (1..GlowFrame.LEVELS), breathing."""
        t = pygame.time.get_ticks() / 1000.0 if seconds is None else seconds
        s = self.style
        b = s['base'] + s['amplitude'] * (0.5 + 0.5 * math.sin(2.0 * math.pi * s['breath'] * t))
        return max(1, int(GlowFrame.LEVELS * b + 0.5))

    def rect(self, screen, rect, corner=4, seconds=None):
        """Glow round a (rounded) rectangle."""
        rect = pygame.Rect(rect)
        surface, pad = self.frames.frame(rect.size, self.colour, self.level(seconds), 'rect', corner)
        screen.blit(surface, (rect.x - pad, rect.y - pad), special_flags=ADD)

    def circle(self, screen, centre, radius, seconds=None):
        """Glow round a circle."""
        size = (2 * int(radius), 2 * int(radius))
        surface, pad = self.frames.frame(size, self.colour, self.level(seconds), 'circle')
        screen.blit(surface, (int(centre[0]) - int(radius) - pad, int(centre[1]) - int(radius) - pad),
                    special_flags=ADD)

    def sprite(self, screen, rect, sprite, key, seconds=None):
        """Glow round a sprite's silhouette (an ornate button), cached under key."""
        rect = pygame.Rect(rect)
        surface, pad = self.frames.frame(rect.size, self.colour, self.level(seconds), 'sprite',
                                         sprite=sprite, sprite_key=key)
        screen.blit(surface, (rect.x - pad, rect.y - pad), special_flags=ADD)
