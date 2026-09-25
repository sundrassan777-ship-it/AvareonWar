# -*- coding: utf-8 -*-
"""
Per-map territory borders (maps/manifest.json "draw_borders").

The Azincournean Highlands art has faint painted borders, so the map renderer
outlines every territory there; Avareon's art has its own borders and must stay
untouched. rendering/map_renderer.py draw_territories() reads
map_data.current_map_draws_borders() on each overlay rebuild.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data  # noqa: E402


def test_azincournean_highlands_draws_borders():
    map_data.load_map('azincournean_highlands')
    assert map_data.current_map_draws_borders() is True


def test_avareon_does_not_draw_borders():
    map_data.load_map('avareon')
    assert map_data.current_map_draws_borders() is False


def test_legacy_avareon_load_does_not_draw_borders():
    # Game.__init__ uses the legacy loader; it must behave like Avareon
    map_data.load_polygons()
    assert map_data.current_map_draws_borders() is False
