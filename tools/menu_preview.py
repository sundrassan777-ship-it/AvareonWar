# -*- coding: utf-8 -*-
"""
Main Menu Windows Preview (dev tool)

The real MainMenu with its new-style windows (ui/menu_kit.py: Options, Achievements and
Profile), to check their look at several screen sizes and their frame cost.
Settings are never saved: settings.save() is switched off here, so Apply, Reset to
Defaults and the rest change nothing on disk (config.json stays as it is).

Run from the game folder:
    py tools/menu_preview.py                         live main menu, Options open (1600x900)
    py tools/menu_preview.py --window achievements   ... with Achievements open (or profile)
    py tools/menu_preview.py --size 1280x720         another window size
    py tools/menu_preview.py --sheet DIR             stills of both windows at 720p / 900p /
                                                     1080p and their states (hover, held
                                                     slider, dimmed rows, a chip, a search,
                                                     scrolled, the opening drop) - PNGs in DIR
    py tools/menu_preview.py --bench [--window W]    frame cost with the window open and
                                                     opening (avg / p95 / worst ms)

Live: the menu as in the game (Esc closes the window, then quits; the menu's buttons open
the windows again). Apply with a display change would re-create the window in the game -
here it just closes.
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

if '--sheet' in sys.argv or '--bench' in sys.argv:
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

pygame.init()

from settings_manager import settings  # noqa: E402

settings.save = lambda *args, **kwargs: None    # The preview never writes config.json

FRAME = 1.0 / 120.0   # the owner's fps cap
SIZES = ((1280, 720), (1600, 900), (1920, 1080))
WINDOWS = ('options', 'achievements', 'profile')


def panel_of(menu, window):
    return {'options': menu.options_panel, 'achievements': menu.achievements_panel,
            'profile': menu.profile_panel}[window]


def make_menu(size, window='options'):
    """A MainMenu on a fresh display of `size`, with `window` open and landed."""
    pygame.display.set_mode(size)
    import main_menu
    menu = main_menu.MainMenu(pygame.display.get_surface())
    open_window(menu, window)
    panel_of(menu, window).anim.finish()
    return menu


def open_window(menu, window):
    {'options': menu._open_options, 'achievements': menu._open_achievements,
     'profile': menu._open_profile}[window]()


def close_window(menu, window):
    {'options': menu._close_options, 'achievements': menu._close_achievements,
     'profile': menu._close_profile}[window]()


def frame(menu, window, mouse=None):
    """One frame as MainMenu.run() draws it, with the mouse at `mouse` (hover)."""
    if mouse is not None:
        panel_of(menu, window).update_hover(mouse)
    menu.render()


def save(menu, out_dir, name):
    pygame.image.save(menu.screen, os.path.join(out_dir, name))


def options_sheet(out_dir):
    for size in SIZES:
        menu = make_menu(size, 'options')
        panel = menu.options_panel
        tag = f"{size[0]}x{size[1]}"
        for tab in ('display', 'gameplay', 'audio'):
            panel.select_tab(tab)
            frame(menu, 'options', (0, 0))
            frame(menu, 'options', (0, 0))   # Second frame: drawn over the landed picture
            save(menu, out_dir, f"options_{tab}_{tag}.png")
        if size != (1600, 900):
            continue
        centre = lambda element: panel.part_rect(element).center  # noqa: E731
        panel.select_tab('display')
        frame(menu, 'options', centre(('switch', 'vsync')))
        save(menu, out_dir, f"options_hover_switch_{tag}.png")
        frame(menu, 'options', centre(('tab', 'audio')))
        save(menu, out_dir, f"options_hover_tab_{tag}.png")
        panel.select_tab('audio')
        panel.dragging = 'music_volume'
        frame(menu, 'options', centre(('slider', 'music_volume')))
        panel.release()
        save(menu, out_dir, f"options_held_slider_{tag}.png")
        panel.select_tab('gameplay')
        menu.temp_tooltips_enabled = False
        menu.temp_edge_scrolling_enabled = False
        frame(menu, 'options', centre(('choice', 'edge_mode', 1)))
        save(menu, out_dir, f"options_dimmed_rows_{tag}.png")
        menu.temp_vsync = True
        panel.select_tab('display')
        frame(menu, 'options', (0, 0))
        save(menu, out_dir, f"options_vsync_on_{tag}.png")
        opening_stills(menu, 'options', out_dir, tag)


def achievements_sheet(out_dir):
    for size in SIZES:
        menu = make_menu(size, 'achievements')
        panel = menu.achievements_panel
        tag = f"{size[0]}x{size[1]}"
        frame(menu, 'achievements', (0, 0))
        frame(menu, 'achievements', (0, 0))
        save(menu, out_dir, f"achievements_{tag}.png")
        if size != (1600, 900):
            continue
        ids = [cid for cid, _cell in panel.grid()['cells']]
        earned = next((a['id'] for a in panel.achievements if a['earned']), ids[0])
        frame(menu, 'achievements', panel.medal_rect(earned).center)
        save(menu, out_dir, f"achievements_hover_earned_{tag}.png")
        frame(menu, 'achievements', panel.part_rect(('chip', 'campaign')).center)
        save(menu, out_dir, f"achievements_hover_chip_{tag}.png")
        panel.set_category('campaign')
        frame(menu, 'achievements', (0, 0))
        save(menu, out_dir, f"achievements_campaign_{tag}.png")
        panel.set_category('all')
        for _ in range(3):
            panel.wheel(-1)
        frame(menu, 'achievements', (0, 0))
        save(menu, out_dir, f"achievements_scrolled_{tag}.png")
        panel.search_text = 'win'
        panel.search_active = True
        panel._after_search()
        frame(menu, 'achievements', (0, 0))
        save(menu, out_dir, f"achievements_search_{tag}.png")
        panel.search_text = 'zzz'
        panel._after_search()
        frame(menu, 'achievements', (0, 0))
        save(menu, out_dir, f"achievements_search_none_{tag}.png")
        panel.handle_escape()
        opening_stills(menu, 'achievements', out_dir, tag)


def profile_sheet(out_dir):
    for size in SIZES:
        menu = make_menu(size, 'profile')
        panel = menu.profile_panel
        tag = f"{size[0]}x{size[1]}"
        frame(menu, 'profile', (0, 0))
        frame(menu, 'profile', (0, 0))
        save(menu, out_dir, f"profile_{tag}.png")
        if size != (1600, 900):
            continue
        locked_title = next((t for t, unlocked, _a in panel.titles if not unlocked), None)
        if locked_title:
            frame(menu, 'profile', panel.part_rect(('title', locked_title)).center)
            save(menu, out_dir, f"profile_tip_locked_title_{tag}.png")
        locked_icon = next((p for p, _n, unlocked, _a in panel.rewards if not unlocked), None)
        if locked_icon:
            frame(menu, 'profile', panel.part_rect(('portrait', locked_icon)).center)
            save(menu, out_dir, f"profile_tip_locked_icon_{tag}.png")
        frame(menu, 'profile', panel.part_rect(('portrait', 3)).center)
        save(menu, out_dir, f"profile_hover_hero_{tag}.png")
        menu._steam_name_active = False
        panel.editing = True
        frame(menu, 'profile', panel.part_rect(('name',)).center)
        save(menu, out_dir, f"profile_editing_name_{tag}.png")
        panel.editing = False
        menu._steam_name_active = True
        menu.temp_selected_title = None
        menu.temp_player_icon = 0
        frame(menu, 'profile', panel.part_rect(('view',)).center)
        save(menu, out_dir, f"profile_steam_no_title_{tag}.png")
        opening_stills(menu, 'profile', out_dir, tag)


def opening_stills(menu, window, out_dir, tag):
    """The drop part of the way in."""
    panel = panel_of(menu, window)
    close_window(menu, window)
    panel.anim.finish()
    menu.render()
    open_window(menu, window)
    for name, progress in (('open_25', 0.25), ('open_60', 0.6)):
        panel.anim.progress = progress
        frame(menu, window, (0, 0))
        save(menu, out_dir, f"{window}_{name}_{tag}.png")


def bench(size, window, frames=600):
    menu = make_menu(size, window)
    panel = panel_of(menu, window)
    if window == 'options':
        moves = [(0, 0)] + [panel.part_rect(e).center for e in panel._layout().parts
                            if e[0] in ('switch', 'left', 'right', 'choice', 'slider')]
    elif window == 'achievements':
        moves = [(0, 0)] + [panel.medal_rect(cid).center for cid, _c in panel.grid()['cells'][:24]]
    else:
        L = panel.layout()
        moves = [(0, 0)] + [panel.part_rect(('title', t)).center for t in L['titles']] + \
                [panel.part_rect(('portrait', p)).center for p in L['portraits']]
    for m in moves:
        frame(menu, window, m)                    # Warm: hover sprites, cards
    calls = {'smoothscale': 0}
    real = pygame.transform.smoothscale

    def counting(*args, **kwargs):
        calls['smoothscale'] += 1
        return real(*args, **kwargs)

    def run(label, setup, positions):
        times = []
        for i in range(frames):
            setup(i)
            start = time.perf_counter()
            frame(menu, window, positions[i % len(positions)])
            times.append((time.perf_counter() - start) * 1000.0)
        times.sort()
        avg = sum(times) / len(times)
        print(f"{label:<34} avg {avg:5.2f} ms   p95 {times[int(len(times) * 0.95)]:5.2f}   "
              f"worst {times[-1]:5.2f}")

    pygame.transform.smoothscale = counting
    run(f"{window}: landed, mouse moving", lambda i: None, moves)

    def opening(i):
        if i % 36 == 0:
            # Back to the start of the drop - not 0, which would close the window and make
            # the next frame capture the menu again (a once-per-opening cost)
            panel.anim.progress = 1e-6
        panel.anim.update(FRAME)
    close_window(menu, window)
    panel.anim.finish()
    open_window(menu, window)
    run(f"{window}: opening drop (loop)", opening, [(0, 0)])
    pygame.transform.smoothscale = real
    print(f"smoothscale calls after warm-up: {calls['smoothscale']}")


def live(size, window):
    pygame.display.set_mode(size)
    pygame.display.set_caption("Main menu windows preview")
    import main_menu
    menu = main_menu.MainMenu(pygame.display.get_surface())
    open_window(menu, window)
    while True:
        result = menu.run()
        if result != 'recreate_window':
            break
        menu.result = None      # Apply with a display change: the game would re-create it


def main():
    parser = argparse.ArgumentParser(description='Main menu windows preview')
    parser.add_argument('--size', default='1600x900', help='window size, e.g. 1280x720')
    parser.add_argument('--window', default='options', choices=WINDOWS, help='the window to open')
    parser.add_argument('--sheet', help='write stills (PNGs) into this folder and exit')
    parser.add_argument('--bench', action='store_true', help="print the window's frame cost and exit")
    args = parser.parse_args()
    size = tuple(int(v) for v in args.size.lower().split('x'))
    if args.sheet:
        os.makedirs(args.sheet, exist_ok=True)
        options_sheet(args.sheet)
        achievements_sheet(args.sheet)
        profile_sheet(args.sheet)
        print(f"Wrote stills to {args.sheet}")
    elif args.bench:
        bench(size, args.window)
    else:
        live(size, args.window)
    pygame.quit()


if __name__ == '__main__':
    main()
