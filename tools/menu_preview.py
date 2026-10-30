# -*- coding: utf-8 -*-
"""
Main Menu Windows Preview (dev tool)

The real MainMenu with its new-style windows (ui/menu_kit.py: the Options window now;
Achievements and Profile next), to check their look at several screen sizes and their
frame cost. Settings are never saved: settings.save() is switched off here, so Apply,
Reset to Defaults and the rest change nothing on disk (config.json stays as it is).

Run from the game folder:
    py tools/menu_preview.py                      live main menu, Options open (1600x900)
    py tools/menu_preview.py --size 1280x720      another window size
    py tools/menu_preview.py --sheet DIR          stills of every tab at 720p / 900p / 1080p,
                                                  a hovered row, a held slider, a dimmed
                                                  row, the opening drop - PNGs in DIR
    py tools/menu_preview.py --bench              frame cost with the window open and opening
                                                  (avg / p95 / worst ms) + smoothscale calls

Live: the menu as in the game (Esc closes the window, then quits; the Options button
opens it again). Apply with a display change would re-create the window in the game -
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


def make_menu(size):
    """A MainMenu on a fresh display of `size`, with the Options window open and settled."""
    pygame.display.set_mode(size)
    import main_menu
    menu = main_menu.MainMenu(pygame.display.get_surface())
    menu._open_options()
    menu.options_panel.anim.finish()
    return menu


def frame(menu, mouse=None):
    """One frame as MainMenu.run() draws it, with the mouse at `mouse` (hover)."""
    if mouse is not None:
        menu.options_panel.update_hover(mouse)
    menu.render()


def centre(menu, element):
    return menu.options_panel.part_rect(element).center


def sheet(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for size in SIZES:
        menu = make_menu(size)
        panel = menu.options_panel
        tag = f"{size[0]}x{size[1]}"
        for tab in ('display', 'gameplay', 'audio'):
            panel.select_tab(tab)
            frame(menu, (0, 0))
            frame(menu, (0, 0))   # second frame: drawn over the settled snapshot
            pygame.image.save(menu.screen, os.path.join(out_dir, f"options_{tab}_{tag}.png"))
        if size != (1600, 900):
            continue
        # States, at 1600x900: a hovered switch row, a hovered tab, a held slider, a dimmed row
        panel.select_tab('display')
        frame(menu, centre(menu, ('switch', 'vsync')))
        pygame.image.save(menu.screen, os.path.join(out_dir, f"state_hover_switch_{tag}.png"))
        frame(menu, centre(menu, ('tab', 'audio')))
        pygame.image.save(menu.screen, os.path.join(out_dir, f"state_hover_tab_{tag}.png"))
        panel.select_tab('audio')
        panel.dragging = 'music_volume'
        frame(menu, centre(menu, ('slider', 'music_volume')))
        panel.release()
        pygame.image.save(menu.screen, os.path.join(out_dir, f"state_held_slider_{tag}.png"))
        panel.select_tab('gameplay')
        menu.temp_tooltips_enabled = False
        menu.temp_edge_scrolling_enabled = False
        frame(menu, centre(menu, ('choice', 'edge_mode', 1)))
        pygame.image.save(menu.screen, os.path.join(out_dir, f"state_dimmed_rows_{tag}.png"))
        menu.temp_vsync = True
        panel.select_tab('display')
        frame(menu, (0, 0))
        pygame.image.save(menu.screen, os.path.join(out_dir, f"state_vsync_on_{tag}.png"))
        # The opening drop, part of the way in
        menu._close_options()
        panel.anim.finish()
        menu._open_options()
        for name, progress in (('open_25', 0.25), ('open_60', 0.6)):
            panel.anim.progress = progress
            frame(menu, (0, 0))
            pygame.image.save(menu.screen, os.path.join(out_dir, f"{name}_{tag}.png"))
    print(f"Wrote stills to {out_dir}")


def bench(size=(1600, 900), frames=600):
    menu = make_menu(size)
    panel = menu.options_panel
    calls = {'smoothscale': 0}
    real = pygame.transform.smoothscale

    def counting(*args, **kwargs):
        calls['smoothscale'] += 1
        return real(*args, **kwargs)

    def run(label, setup, moves):
        times = []
        for i in range(frames):
            setup(i)
            start = time.perf_counter()
            frame(menu, moves[i % len(moves)])
            times.append((time.perf_counter() - start) * 1000.0)
        times.sort()
        avg = sum(times) / len(times)
        print(f"{label:<34} avg {avg:5.2f} ms   p95 {times[int(len(times) * 0.95)]:5.2f}   "
              f"worst {times[-1]:5.2f}")

    # Warm every sprite first (tabs, states), then count smoothscale calls in steady use
    for tab in ('display', 'gameplay', 'audio'):
        panel.select_tab(tab)
        for row in panel.tab_rows():
            for element in list(panel._layout().parts):
                if element[1] == row.key:
                    frame(menu, menu.options_panel.part_rect(element).center)
    pygame.transform.smoothscale = counting
    moves = [(0, 0)] + [panel.part_rect(e).center for e in panel._layout().parts
                        if e[0] in ('switch', 'left', 'right', 'choice', 'slider')]
    run("settled, mouse over the controls", lambda i: None, moves)

    def opening(i):
        if i % 36 == 0:
            # Back to the start of the drop - not 0, which would close the window and make
            # the next frame capture the menu again (a once-per-opening cost)
            panel.anim.progress = 1e-6
        panel.anim.update(FRAME)
    menu._close_options()
    panel.anim.finish()
    menu._open_options()
    run("opening drop + fade (loop)", opening, [(0, 0)])
    pygame.transform.smoothscale = real
    print(f"smoothscale calls after warm-up: {calls['smoothscale']}")


def live(size):
    pygame.display.set_mode(size)
    pygame.display.set_caption("Main menu windows preview")
    import main_menu
    menu = main_menu.MainMenu(pygame.display.get_surface())
    menu._open_options()
    while True:
        result = menu.run()
        if result != 'recreate_window':
            break
        menu.result = None      # Apply with a display change: the game would re-create it


def main():
    parser = argparse.ArgumentParser(description='Main menu windows preview')
    parser.add_argument('--size', default='1600x900', help='window size, e.g. 1280x720')
    parser.add_argument('--sheet', help='write stills (PNGs) into this folder and exit')
    parser.add_argument('--bench', action='store_true', help="print the window's frame cost and exit")
    args = parser.parse_args()
    size = tuple(int(v) for v in args.size.lower().split('x'))
    if args.sheet:
        sheet(args.sheet)
    elif args.bench:
        bench(size)
    else:
        live(size)
    pygame.quit()


if __name__ == '__main__':
    main()
