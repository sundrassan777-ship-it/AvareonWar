# -*- coding: utf-8 -*-
"""
The one-line explanations under each setting in the main menu's Options window
(ui/options_panel.py).

Edit the wording here. Keep each to about one line - a longer one wraps onto a second
line under the setting's name. The keys are the window's rows:

- Display tab:  resolution, fullscreen, vsync, fps_limit, show_fps, map_look
- Gameplay tab: edge_scrolling, edge_mode, tooltips, tooltip_delay, pan_speed, zoom_speed
- Audio tab:    master_volume, music_volume, sfx_volume

map_look shows only while the 3D map look can be chosen (MAP_3D_AVAILABLE).
"""

OPTION_HINTS = {
    # Display ---------------------------------------------------------------
    'resolution': "Size of the game window. Changes when you press Apply.",
    'fullscreen': "Fill the whole screen instead of a window.",
    'vsync': "Draw in step with your monitor to stop tearing. Takes over from the FPS limit.",
    'fps_limit': "The most frames per second the game draws.",
    'show_fps': "A frame counter in the corner of the screen.",
    'map_look': "The flat parchment map or the 3D relief map.",

    # Gameplay --------------------------------------------------------------
    'edge_scrolling': "Move the map by pushing the mouse against an edge.",
    'edge_mode': "The edges of the screen, or the map's edges by the top and bottom bars.",
    'tooltips': "Explanations when you hover over buttons.",
    'tooltip_delay': "How long to hover before a tooltip appears.",
    'pan_speed': "How fast the map scrolls at the edges and with the keyboard.",
    'zoom_speed': "How far one mouse-wheel notch zooms.",

    # Audio -----------------------------------------------------------------
    'master_volume': "Every sound in the game at once.",
    'music_volume': "Menu and in-game music.",
    'sfx_volume': "Clicks, armies, battles and voices.",
}
