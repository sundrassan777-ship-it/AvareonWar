# -*- coding: utf-8 -*-
"""
The main menu's Options window (ui/options_panel.py, drawn with ui/menu_kit.py - the
"Menu Glow-up", 2026-10-30):

- layout at 720p-1440p: the window and its title plate on screen, every tab's rows above
  the footer, every control inside its row's control column, names and explanations in
  their column (at most two lines), footer buttons apart, the note clear of them
- controls: tabs switch the rows; switches toggle (their names too); arrows step and wrap;
  a choice picks; sliders follow a click and a drag, clamped; FPS Limit is "Set by VSync"
  while VSync is on; dependent rows (Scroll From, Tooltip Delay) ignore clicks while
  their switch is off; volumes preview live; one click sound per action
- Apply / Cancel / Reset to Defaults: Apply saves (display changes re-create the window),
  Cancel and Esc drop the changes, Enter applies, Reset uses the settings manager's own
  defaults; the unsaved-changes count
- feedback: hover brighter than normal, the click flash brighter still
- the drop: no clicks until the window has landed; closing forgets the captured menu
- performance: no smoothscale in steady frames; the alpha-255 fade trap avoided
- the zoom speed fix: the default and anything saved out of range are in the slider's range

Settings are never written: settings.save() is stubbed and the in-memory settings restored.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


@pytest.fixture(scope='module', autouse=True)
def display():
    pygame.init()
    pygame.display.quit()
    pygame.display.init()
    pygame.display.set_mode((1600, 900))
    yield
    pygame.display.set_mode((1600, 900))


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """Counts click sounds and live volume previews; never saves; restores the settings."""
    from global_sound import sound_manager
    from settings_manager import settings
    import main_menu
    before = dict(settings.settings)
    counts = {'clicks': 0, 'previews': 0, 'saves': 0}
    monkeypatch.setattr(sound_manager, 'play_ui_click',
                        lambda *a, **k: counts.__setitem__('clicks', counts['clicks'] + 1))
    monkeypatch.setattr(settings, 'save', lambda *a, **k: counts.__setitem__('saves', counts['saves'] + 1))
    real_preview = main_menu.MainMenu._preview_audio

    def preview(self):
        counts['previews'] += 1
        real_preview(self)
    monkeypatch.setattr(main_menu.MainMenu, '_preview_audio', preview)
    yield counts
    settings.settings.clear()
    settings.settings.update(before)


def make_menu(size=(1600, 900)):
    """A MainMenu at `size` with the Options window open and landed."""
    import main_menu
    if pygame.display.get_surface().get_size() != size:
        pygame.display.set_mode(size)
    menu = main_menu.MainMenu(pygame.display.get_surface())
    menu._open_options()
    menu.options_panel.anim.finish()
    return menu


def click(menu, element):
    menu.handle_click(menu.options_panel.part_rect(element).center)


def row_rect(panel, key):
    rect = panel.rect()
    for row, r in panel._layout().rows:
        if row.key == key:
            return r.move(rect.x, rect.y)
    raise KeyError(key)


def brightness(surface, rect):
    r, g, b = pygame.transform.average_color(surface, rect)[:3]
    return r + g + b


# ------------------------------------------------------------------------------ layout

@pytest.mark.parametrize('size', RESOLUTIONS)
def test_layout_fits(size):
    menu = make_menu(size)
    panel = menu.options_panel
    kit = menu.menu_kit
    screen = pygame.Rect((0, 0), size)
    window = panel.rect()
    assert screen.contains(window)
    assert window.y - kit.banner_overhang() >= 0, "title plate off the top of the screen"
    for tab in ('display', 'gameplay', 'audio'):
        panel.select_tab(tab)
        L = panel._layout()
        board = pygame.Rect(0, 0, *L.size).inflate(-2 * kit.border(), -2 * kit.border())
        footer_top = min(r.top for r in L.buttons.values())
        assert L.rows, tab
        for (row, r), nxt in zip(L.rows, L.rows[1:] + [(None, None)]):
            assert board.contains(r), (tab, row.key)
            assert r.bottom <= footer_top, (tab, row.key, "row runs into the footer")
            if nxt[1] is not None:
                assert not r.colliderect(nxt[1]), (tab, row.key)
            parts = [(e, p) for e, p in L.parts.items() if e[1] == row.key and e[0] != 'slider']
            assert parts, row.key
            for element, part in parts:
                assert r.contains(part), (tab, element)
            # A slider's value sits inside the row too
            if row.kind == 'slider':
                track = L.parts[('track', row.key)]
                value_right = track.right + kit.px(16) + kit.px(58)
                assert value_right <= r.right, row.key
            # Name and explanation fit their column, on at most two lines
            name_x = r.x + kit.px(16) + (kit.px(30) if row.sub else 0)
            room = r.right - kit.px(16) - kit.px(400) - kit.px(20) - name_x
            assert kit.font('name').size(row.label)[0] <= room, row.key
            lines = kit.wrap(row.hint, 'hint', room)
            assert len(lines) <= 2 and not lines[-1].endswith('...'), (row.key, lines)
            assert all(kit.font('hint').size(line)[0] <= room for line in lines), row.key
        buttons = list(L.buttons.values())
        for i, a in enumerate(buttons):
            assert board.contains(a)
            for b in buttons[i + 1:]:
                assert not a.colliderect(b)
        note = kit.text("3 unsaved changes", 'note', (0, 0, 0))
        assert L.note_right - note.get_width() - kit.px(24) > L.buttons['reset'].right


# ------------------------------------------------------------------------------ controls

def test_tabs_switch_rows(quiet):
    menu = make_menu()
    panel = menu.options_panel
    for tab in ('gameplay', 'audio', 'display'):
        click(menu, ('tab', tab))
        assert panel.tab == tab
        assert {row.tab for row, _ in panel._layout().rows} == {tab}
    assert quiet['clicks'] == 3
    click(menu, ('tab', 'display'))      # The open tab: nothing happens
    assert quiet['clicks'] == 3


def test_tab_key_steps_through_tabs():
    menu = make_menu()
    panel = menu.options_panel
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0, unicode='\t'))
    menu.handle_events()
    assert panel.tab == 'gameplay'
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=pygame.KMOD_SHIFT,
                                         unicode='\t'))
    menu.handle_events()
    assert panel.tab == 'display'


def test_switches_toggle_and_their_names_too(quiet):
    menu = make_menu()
    panel = menu.options_panel
    for key, attr in (('fullscreen', 'temp_fullscreen'), ('vsync', 'temp_vsync'),
                      ('show_fps', 'temp_show_fps')):
        before = getattr(menu, attr)
        click(menu, ('switch', key))
        assert getattr(menu, attr) is (not before), key
        r = row_rect(panel, key)
        menu.handle_click((r.x + menu.menu_kit.px(40), r.centery))   # On its name
        assert getattr(menu, attr) is before, key


def test_arrows_step_and_wrap():
    menu = make_menu()
    panel = menu.options_panel
    menu.temp_resolution = (1920, 1080)
    click(menu, ('right', 'resolution'))
    assert menu.temp_resolution == (1280, 720)
    click(menu, ('left', 'resolution'))
    assert menu.temp_resolution == (1920, 1080)
    menu.temp_vsync = False
    menu.temp_fps_limit = 0
    click(menu, ('right', 'fps_limit'))
    assert menu.temp_fps_limit == 60
    click(menu, ('left', 'fps_limit'))
    click(menu, ('left', 'fps_limit'))
    assert menu.temp_fps_limit == 240
    panel.select_tab('gameplay')
    menu.temp_tooltips_enabled = True
    menu.temp_tooltip_delay_ms = 1000
    click(menu, ('right', 'tooltip_delay'))
    assert menu.temp_tooltip_delay_ms == -1          # "Never", as before


def test_value_not_in_the_list_shown_as_it_is():
    """A hand-edited config.json value is shown as it is; the arrows then step from the start."""
    menu = make_menu()
    panel = menu.options_panel
    rows = {row.key: row for row in panel.rows}
    menu.temp_resolution = (2560, 1440)
    menu.temp_fps_limit = 75
    assert panel.value_label(rows['resolution']) == "2560 × 1440"
    assert panel.value_label(rows['fps_limit']) == "75"
    click(menu, ('right', 'fps_limit'))
    assert menu.temp_fps_limit == 60


def test_fps_limit_set_by_vsync():
    menu = make_menu()
    panel = menu.options_panel
    menu.temp_vsync = True
    menu.temp_fps_limit = 120
    click(menu, ('right', 'fps_limit'))
    assert menu.temp_fps_limit == 120
    fps = next(row for row in panel.rows if row.key == 'fps_limit')
    assert panel.is_locked(fps)
    menu.render()
    menu.render()      # Landed: the locked note is drawn, no arrows (nothing raises)


def test_choice_picks(quiet):
    menu = make_menu()
    menu.options_panel.select_tab('gameplay')
    menu.temp_edge_scrolling_enabled = True
    menu.temp_edge_scrolling_mode = 'window_edge'
    click(menu, ('choice', 'edge_mode', 1))
    assert menu.temp_edge_scrolling_mode == 'map_edge'
    clicks = quiet['clicks']
    click(menu, ('choice', 'edge_mode', 1))          # Already chosen: no sound
    assert quiet['clicks'] == clicks
    click(menu, ('choice', 'edge_mode', 0))
    assert menu.temp_edge_scrolling_mode == 'window_edge'


def test_dependent_rows_ignore_clicks_while_off(quiet):
    menu = make_menu()
    panel = menu.options_panel
    panel.select_tab('gameplay')
    menu.temp_edge_scrolling_enabled = False
    menu.temp_tooltips_enabled = False
    menu.temp_edge_scrolling_mode = 'window_edge'
    menu.temp_tooltip_delay_ms = 500
    clicks = quiet['clicks']
    click(menu, ('choice', 'edge_mode', 1))
    click(menu, ('right', 'tooltip_delay'))
    assert menu.temp_edge_scrolling_mode == 'window_edge'
    assert menu.temp_tooltip_delay_ms == 500
    assert quiet['clicks'] == clicks
    # Switched back on, they work again
    click(menu, ('switch', 'edge_scrolling'))
    click(menu, ('choice', 'edge_mode', 1))
    assert menu.temp_edge_scrolling_mode == 'map_edge'


def test_slider_click_and_drag_clamped(quiet):
    from config.constants import CAMERA_ZOOM_SPEED_MIN, CAMERA_ZOOM_SPEED_MAX
    menu = make_menu()
    panel = menu.options_panel
    panel.select_tab('gameplay')
    rect = panel.rect()
    track = panel._layout().parts[('track', 'zoom_speed')].move(rect.x, rect.y)
    menu.handle_click((track.x + track.w * 3 // 4, track.centery))
    span = CAMERA_ZOOM_SPEED_MAX - CAMERA_ZOOM_SPEED_MIN
    assert menu.temp_zoom_speed == pytest.approx(CAMERA_ZOOM_SPEED_MIN + 0.75 * span, abs=span / track.w + 1e-9)
    assert panel.dragging == 'zoom_speed'
    panel.drag_to((track.right + 500, track.centery))
    assert menu.temp_zoom_speed == pytest.approx(CAMERA_ZOOM_SPEED_MAX)
    panel.drag_to((track.x - 500, track.centery))
    assert menu.temp_zoom_speed == pytest.approx(CAMERA_ZOOM_SPEED_MIN)
    # Released with the mouse button (MainMenu.handle_events)
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=track.center))
    menu.handle_events()
    assert panel.dragging is None
    assert quiet['previews'] == 0          # Not a volume


def test_volume_sliders_preview_live(quiet):
    menu = make_menu()
    panel = menu.options_panel
    panel.select_tab('audio')
    rect = panel.rect()
    track = panel._layout().parts[('track', 'music_volume')].move(rect.x, rect.y)
    menu.handle_click((track.x + track.w // 2, track.centery))
    assert menu.temp_music_volume == pytest.approx(0.5, abs=0.01)
    panel.drag_to((track.x + track.w // 4, track.centery))
    assert menu.temp_music_volume == pytest.approx(0.25, abs=0.01)
    assert quiet['previews'] >= 2


# ------------------------------------------------------------------------------ apply / cancel / reset

def test_unsaved_count_and_cancel(quiet):
    from settings_manager import settings
    menu = make_menu()
    panel = menu.options_panel
    assert panel.unsaved() == 0
    full = menu.temp_fullscreen
    click(menu, ('switch', 'show_fps'))
    click(menu, ('switch', 'fullscreen'))
    assert panel.unsaved() == 2
    click(menu, ('button', 'cancel'))
    assert not menu.show_options and not panel.anim.opening
    assert quiet['saves'] == 0
    menu._open_options()
    assert menu.temp_fullscreen == full == settings.is_fullscreen()
    assert panel.unsaved() == 0


def test_apply_saves_and_recreates_for_display_changes(quiet):
    from settings_manager import settings
    menu = make_menu()
    click(menu, ('switch', 'show_fps'))
    show = menu.temp_show_fps
    click(menu, ('button', 'apply'))
    assert settings.get('show_fps') == show
    assert quiet['saves'] == 1
    assert not menu.show_options
    assert menu.result is None                      # No display change
    menu._open_options()
    menu.options_panel.anim.finish()
    click(menu, ('switch', 'fullscreen'))
    click(menu, ('button', 'apply'))
    assert menu.result == 'recreate_window'


def test_enter_applies_escape_cancels(quiet):
    from settings_manager import settings
    menu = make_menu()
    show = settings.get('show_fps')
    click(menu, ('switch', 'show_fps'))
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode='\x1b'))
    menu.handle_events()
    assert not menu.show_options and settings.get('show_fps') == show and quiet['saves'] == 0
    menu._open_options()
    menu.options_panel.anim.finish()
    click(menu, ('switch', 'show_fps'))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode='\r'))
    menu.handle_events()
    assert not menu.show_options and settings.get('show_fps') == (not show) and quiet['saves'] == 1


def test_reset_uses_the_settings_defaults():
    from settings_manager import settings
    menu = make_menu()
    menu.temp_zoom_speed = 0.3
    menu.temp_pan_speed = 19.0
    menu.temp_master_volume = 0.1
    menu.temp_map_3d = True
    click(menu, ('button', 'reset'))
    d = settings.defaults
    assert menu.temp_zoom_speed == d['camera_zoom_speed'] == 0.15
    assert menu.temp_pan_speed == d['camera_pan_speed']
    assert menu.temp_master_volume == d['master_volume']
    assert menu.temp_map_3d == (d['map_style'] == '3d')
    assert menu.temp_resolution == settings.get_default_resolution()
    assert menu.show_options                        # Reset does not close (or save)


# ------------------------------------------------------------------------------ feedback

@pytest.mark.parametrize('element', [('button', 'apply'), ('button', 'cancel'), ('button', 'reset'),
                                     ('tab', 'gameplay'), ('switch', 'vsync'),
                                     ('right', 'resolution'), ('choice', 'map_look', 0)])
def test_hover_then_flash_brighter(element):
    menu = make_menu()
    panel = menu.options_panel
    if element[1] == 'map_look' and not any(row.key == 'map_look' for row in panel.rows):
        pytest.skip("3D map look locked: no Map Look row")
    rect = panel.part_rect(element)
    if element == ('choice', 'map_look', 0):
        menu.temp_map_3d = True                     # "2D" is the side not chosen
    panel.update_hover((1, 1))
    menu.render()
    normal = brightness(menu.screen, rect)
    panel.update_hover(rect.center)
    menu.render()
    hover = brightness(menu.screen, rect)
    panel._flash = (element, pygame.time.get_ticks() + 10000)
    menu.render()
    flash = brightness(menu.screen, rect)
    assert normal < hover < flash, (element, normal, hover, flash)


# ------------------------------------------------------------------------------ the drop

def test_no_clicks_until_landed(quiet):
    menu = make_menu()
    menu._close_options()
    menu.options_panel.anim.finish()
    menu._open_options()
    menu.options_panel.anim.progress = 0.8
    before = menu.temp_show_fps
    menu.handle_click(menu.options_panel.part_rect(('switch', 'show_fps')).center)
    assert menu.temp_show_fps == before and quiet['clicks'] == 0
    menu.options_panel.anim.finish()
    menu.handle_click(menu.options_panel.part_rect(('switch', 'show_fps')).center)
    assert menu.temp_show_fps != before


def test_open_close_cycle_and_slow_frames():
    from ui.menu_kit import OPEN_SECONDS
    menu = make_menu()
    panel = menu.options_panel
    menu._close_options()
    panel.anim.finish()
    menu.render()
    assert menu.window_stage.plain is None          # Closed: the captured menu is dropped
    menu._open_options()
    panel.update(0.5)                               # A slow frame advances at most 1/60 s
    assert panel.anim.progress == pytest.approx((1 / 60.0) / OPEN_SECONDS)
    for _ in range(60):
        panel.update(1 / 120.0)
        menu.render()
    assert panel.anim.settled_open and menu.window_stage.settled is not None


def test_faded_blits_avoid_the_alpha_255_path():
    from ui.menu_kit import _blit_faded
    screen = pygame.Surface((40, 40))
    surf = pygame.Surface((10, 10))
    _blit_faded(screen, surf, (0, 0), 255)
    assert surf.get_alpha() is None
    _blit_faded(screen, surf, (0, 0), 120)
    assert surf.get_alpha() == 120


def test_no_smoothscale_in_steady_frames(monkeypatch):
    menu = make_menu()
    panel = menu.options_panel

    def every_control():
        for tab in ('display', 'gameplay', 'audio'):
            panel.select_tab(tab)
            for element in list(panel._layout().parts):
                if element[0] in ('switch', 'left', 'right', 'choice', 'slider'):
                    panel.update_hover(panel.part_rect(element).center)
                    menu.render()
    every_control()                                  # Warm: hover sprites built once
    calls = []
    real = pygame.transform.smoothscale
    monkeypatch.setattr(pygame.transform, 'smoothscale', lambda *a, **k: calls.append(1) or real(*a, **k))
    every_control()
    assert calls == []


# ------------------------------------------------------------------------------ zoom speed fix

def test_zoom_speed_default_and_saved_values_in_range():
    from config.constants import CAMERA_ZOOM_SPEED, CAMERA_ZOOM_SPEED_MIN, CAMERA_ZOOM_SPEED_MAX
    from settings_manager import settings
    assert CAMERA_ZOOM_SPEED_MIN <= settings.defaults['camera_zoom_speed'] <= CAMERA_ZOOM_SPEED_MAX
    for saved, expected in ((1.1, CAMERA_ZOOM_SPEED), (0.0, CAMERA_ZOOM_SPEED), (0.2, 0.2)):
        settings.settings['camera_zoom_speed'] = saved      # As if read from config.json
        settings._validate_and_clean_settings()
        assert settings.settings['camera_zoom_speed'] == expected, saved


def test_default_zoom_speed_zooms_out_one_step():
    """With the default speed one wheel notch out zooms out a step, not to the furthest zoom
    (the old default 1.1 made the zoom factor 1 - 1.1 < 0)."""
    from config.constants import CAMERA_ZOOM_SPEED
    from input.camera_handler import CameraHandler
    camera = CameraHandler(865, 649, 1600, 900, 649, initial_zoom=1.65)
    for _ in range(4):                               # In a few notches first
        camera.handle_zoom(+1, (800, 400), CAMERA_ZOOM_SPEED, 40)
    zoomed = camera.target_zoom
    assert zoomed > camera.min_zoom
    camera.handle_zoom(-1, (800, 400), CAMERA_ZOOM_SPEED, 40)
    assert camera.target_zoom == pytest.approx(zoomed * (1 - CAMERA_ZOOM_SPEED))
    assert camera.target_zoom > camera.min_zoom
    # The old default: one notch out went straight to the furthest zoom
    camera.handle_zoom(-1, (800, 400), 1.1, 40)
    assert camera.target_zoom == pytest.approx(camera.min_zoom)
