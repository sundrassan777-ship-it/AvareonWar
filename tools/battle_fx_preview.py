# -*- coding: utf-8 -*-
"""
Battle Screen Effects Preview (dev tool)

Live preview of the battle screen (ui/effects/battle_interface.py) over the real
Avareon map, to tune the bar fight's look (ui/effects/battle_fx_style.py) and
check its frame cost: the backdrop, the battle icon, the two strength bars and
the shots they trade (the charge, the bolt, the chunk falling out of the bar) -
up to the victory / defeat splash.

The interface is the game's own EnhancedBattleInterface over a real GameState and
Battle (as tests/test_battle_interface_integration.py builds them); the real
result is handed back with set_actual_battle_result() right after Resolve, as
main.py does.

Run from the game folder:
    py tools/battle_fx_preview.py                    live window (1600x900)
    py tools/battle_fx_preview.py --size 1280x720    another window size
    py tools/battle_fx_preview.py --sheet out.png    stills: setup, shots over time, the finale
    py tools/battle_fx_preview.py --bench            battle screen cost per frame (avg / p95 / worst ms)

Controls (live):
    1-5  battle: skirmish / large battle / close fight / defender wins / full house
         (full house: every unit type on both sides, every bonus the rules allow)
    C    colours: bright / dark / neutral grey defender
    Space  resolve (during the fight: skip)     R  reopen the battle
    S    slow motion (x0.25)     P  pause     Esc  quit
    Mouse  the screen's own buttons: Resolve Battle, Skip (or click anywhere in the
           fight), Close (reopens the battle); the wheel scrolls the side under the
           cursor (or the report) when it outgrows its panel
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

import pygame  # noqa: E402

import map_data  # noqa: E402
from tools.order_fx_preview import OrderPreview  # noqa: E402

FRAME = 1.0 / 120.0   # the owner's fps cap

# name -> (attacker armies, defender armies) of Swordsmen; None: FULL_HOUSE
BATTLES = {
    'skirmish': (4, 3),
    'large battle': (60, 45),
    'close fight': (20, 18),
    'defender wins': (8, 20),
    'full house': None,
}

# 'full house' - the battle preview with everything in it (owner, 2026-10-29: the full
# picture). Player 0 attacks player 1's Keep. Per side (unit type, count, level): every unit
# type, veterancy varied by type. Every strength bonus the rules allow is on for both: Cavalry
# Tactics and Divide and Conquer (researched), Battlement Archery (only the defender has a
# Keep there to use it), Vanquish the Enemy (a hero each), strength territories (owned, two of
# one kind so the amounts differ), a Captain, and the defender's Keep.
FULL_HOUSE = {
    0: [('Swordsman', 4, 2), ('Archer', 3, 1), ('Pikeman', 2, 0), ('Cavalry', 4, 1), ('Captain', 1, 1)],
    1: [('Swordsman', 3, 1), ('Archer', 4, 2), ('Pikeman', 3, 1), ('Cavalry', 2, 3), ('Captain', 1, 0)],
}
FULL_HOUSE_TERRITORIES = {
    0: {'swordsman_str': 2, 'cavalry_str': 1, 'archer_str': 1, 'pikeman_str': 1},
    1: {'archer_str': 2, 'pikeman_str': 1, 'cavalry_str': 1, 'swordsman_str': 1},
}
FULL_HOUSE_TECHS = ('archer_keep_strength', 'cavalry_strength_bonus', 'keep_siege_bonus')
FULL_HOUSE_HEROES = {0: 'Neil H\u00e9vilneu', 1: 'Serthus Diarcess'}   # Vanquish the Enemy

# name -> (attacker colour, defender colour)
COLOURS = {
    'bright': ((255, 100, 100), (100, 150, 255)),
    'dark': ((40, 60, 150), (120, 30, 30)),
    'neutral': ((100, 255, 100), (150, 150, 150)),
}


def backdrop(screen):
    """The map as the game shows it behind the battle screen (drawn once)."""
    preview = OrderPreview(screen, '2d')
    preview.render()
    return screen.copy()


def open_battle(screen, battle, colours):
    """
    A fresh EnhancedBattleInterface for one of BATTLES with one of COLOURS.

    Returns:
        (interface, open ms)
    """
    from config.font_manager import FontManager
    from game_state import GameState, Battle
    from ui.effects.battle_interface import EnhancedBattleInterface

    if BATTLES[battle] is None:
        game = _full_house(colours)
        start = time.perf_counter()
        ui = EnhancedBattleInterface(screen=screen, game_state=game, battle_index=0,
                                     font_manager=FontManager(), current_player_index=0)
        return ui, (time.perf_counter() - start) * 1000
    attackers, defenders = BATTLES[battle]
    game = GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1],
                     skip_setup_phase=True)
    game.player_colors[0], game.player_colors[1] = COLOURS[colours]
    territory = sorted(map_data.get_all_territories())[0]

    def units(unit_type, count):
        return [game._make_unit(unit_type, i, 'ready') for i in range(count)]

    defender_units = units('Swordsman', defenders)
    game.territory_owners[territory] = 1
    # A Keep and a Farm, so the battle report has its outcome lines (no Keep bonus: the
    # fight itself is unchanged)
    game.buildings[territory] = {0: 'Keep', 1: 'Farm'}
    game.territory_garrisons[territory] = {}
    game.add_garrison(territory, 1, unmoved=defenders, moved=0, units=defender_units)
    game.army_units[territory] = defender_units[:]
    game.armies[territory] = defenders
    game.armies_unmoved[territory] = defenders
    fight = Battle(territory)
    fight.original_owner = 1
    fight.add_army(1, defenders, {'Swordsman': defenders})
    fight.add_army(0, attackers, {'Swordsman': attackers})
    game.pending_battles = [fight]

    start = time.perf_counter()
    ui = EnhancedBattleInterface(screen=screen, game_state=game, battle_index=0,
                                 font_manager=FontManager(), current_player_index=0)
    return ui, (time.perf_counter() - start) * 1000


def _full_house(colours):
    """The GameState of the 'full house' battle (FULL_HOUSE), set up the real way."""
    from game_state import GameState, Battle
    from game_state.data_definitions import build_technologies

    game = GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1],
                     skip_setup_phase=True)
    game.player_colors[0], game.player_colors[1] = COLOURS[colours]
    game.turn_number = 12
    territories = sorted(map_data.get_all_territories())
    territory = territories[0]
    owned = {0: [], 1: []}
    for player, wanted in FULL_HOUSE_TERRITORIES.items():
        for bonus, count in wanted.items():
            for name in [t for t in territories
                         if t != territory and t not in owned[0] + owned[1]
                         and map_data.get_territory_bonus(t) == bonus][:count]:
                game.territory_owners[name] = player
                owned[player].append(name)
    game.territory_owners[territory] = 1
    game.invalidate_territorial_bonus_cache()
    techs = [tech for tech in build_technologies() if tech.get('effect_type') in FULL_HOUSE_TECHS]
    for player in (0, 1):
        for tech in techs:
            game.apply_tech_effect(player, tech, announce=False)
    # The heroes: the defender's in its Keep here, the attacker's in a Keep at home
    game.buildings[territory] = {0: 'Keep', 1: 'Farm', 2: 'Barracks'}
    home = owned[0][0]
    game.buildings[home] = {0: 'Keep'}
    for player, keep in ((0, home), (1, territory)):
        hero = FULL_HOUSE_HEROES[player]
        game.heroes.setdefault(player, {})[hero] = {'keep_territory': keep, 'keep_plot': 0}
        game.hero_ownership[player].add(hero)

    def units(player, status):
        result = []
        for unit_type, count, level in FULL_HOUSE[player]:
            for _ in range(count):
                unit = game._make_unit(unit_type, len(result), status)
                unit['level'] = level
                result.append(unit)
        return result

    defender_units, attacker_units = units(1, 'ready'), units(0, 'moved')
    game.territory_garrisons[territory] = {}
    game.add_garrison(territory, 1, unmoved=len(defender_units), moved=0, units=defender_units)
    game.territory_garrisons[territory][0] = {'unmoved': 0, 'moved': len(attacker_units),
                                              'units': attacker_units}
    fight = Battle(territory)
    fight.original_owner = 1
    for player, side in ((1, defender_units), (0, attacker_units)):
        composition = {}
        for unit in side:
            composition[unit['type']] = composition.get(unit['type'], 0) + 1
        fight.add_army(player, len(side), composition)
    fight.keep_bonus = 2
    fight.keep_bonus_player = 1
    fight.original_garrison = len(defender_units)
    game.pending_battles = [fight]
    return game


def resolve(ui):
    """
    Click Resolve, then resolve the real battle and hand its result back as main.py
    does: the survivors, and what the battle did for the report's outcome lines.
    """
    ui.handle_click(ui.resolve_button_rect.center)
    game = ui.game_state
    battle = game.pending_battles[0]
    game.resolve_battle(0)
    winner = battle.winner if battle.resolved else -1
    survivors = getattr(battle, 'surviving_armies', 0) or 0
    units = (game.territory_garrisons.get(battle.territory, {}).get(winner, {}).get('units', [])
             if winner is not None and winner >= 0 else [])
    attacker_won = winner == ui.attacker_player
    ui.set_actual_battle_result(winner, survivors if attacker_won else 0,
                                0 if attacker_won else survivors, units,
                                outcome=game.battle_outcome(battle, ui.current_player))


def bars_area(ui):
    """The strip round both bars and the gap between them (for stills)."""
    left = ui.attacker_bar_rect.centerx - ui.bar_png_width // 2
    right = ui.defender_bar_rect.centerx + ui.bar_png_width // 2
    top = ui.attacker_bar_rect.top + ui.bar_fill_offset - int(ui.bar_fill_height * 2.2)
    bottom = ui.attacker_bar_rect.top + ui.bar_fill_offset + int(ui.bar_fill_height * 3.2)
    return pygame.Rect(left, top, right - left, bottom - top)


def light_counters(ui):
    """(sprites built, sprites skipped for the build budget) of the battle light kit, if any."""
    light = getattr(ui, 'light', None)
    if light is None:
        return None
    return light.sprites_built(), light.denied()


def run_live(size):
    pygame.init()
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption('Battle screen effects preview')
    background = backdrop(screen)
    font = pygame.font.SysFont('consolas', 16)
    clock = pygame.time.Clock()
    battle_names = list(BATTLES)
    colour_names = list(COLOURS)
    battle, colours = battle_names[0], colour_names[0]
    ui, open_ms = open_battle(screen, battle, colours)
    slow = paused = False
    history = []
    from ui.effects.battle_interface import BattleInterfaceState
    while True:
        dt = clock.tick(120) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if event.type == pygame.MOUSEMOTION:
                ui.handle_mouse_motion(event.pos)
            elif event.type == pygame.MOUSEWHEEL:
                ui.handle_wheel(event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if ui.state == BattleInterfaceState.SETUP:
                    if ui.resolve_button_rect.collidepoint(event.pos):
                        resolve(ui)
                elif ui.handle_click(event.pos) == 'close':
                    ui, open_ms = open_battle(screen, battle, colours)
            if event.type == pygame.KEYDOWN:
                reopen = False
                if pygame.K_1 <= event.key <= pygame.K_1 + len(battle_names) - 1:
                    battle = battle_names[event.key - pygame.K_1]
                    reopen = True
                elif event.key == pygame.K_c:
                    colours = colour_names[(colour_names.index(colours) + 1) % len(colour_names)]
                    reopen = True
                elif event.key == pygame.K_r:
                    reopen = True
                elif event.key == pygame.K_s:
                    slow = not slow
                elif event.key == pygame.K_p:
                    paused = not paused
                elif event.key == pygame.K_SPACE:
                    if ui.state == BattleInterfaceState.SETUP:
                        resolve(ui)
                    else:
                        ui.handle_key(event)
                if reopen:
                    ui, open_ms = open_battle(screen, battle, colours)
        if not paused:
            ui.update(min(dt, 0.05) * (0.25 if slow else 1.0))
        screen.blit(background, (0, 0))
        start = time.perf_counter()
        ui.render()
        render_ms = (time.perf_counter() - start) * 1000
        history = (history + [render_ms])[-120:]
        counters = light_counters(ui)
        lines = [
            f"{clock.get_fps():6.1f} FPS   battle screen {sum(history) / len(history):5.2f} ms"
            f" (worst {max(history):5.2f})   opened in {open_ms:.0f} ms"
            + (f"   sprites {counters[0]} skipped {counters[1]}" if counters else ''),
            f"{battle}   colours {colours}   {ui.state.name}"
            f"{'   SLOW' if slow else ''}{'   PAUSED' if paused else ''}",
            '1-5 battle  C colours  Space resolve/skip  R reopen  S slow  P pause  mouse: buttons, wheel',
        ]
        for i, line in enumerate(lines):
            text = font.render(line, True, (255, 255, 255))
            pygame.draw.rect(screen, (0, 0, 0), text.get_rect(topleft=(8, 8 + i * 20)).inflate(8, 2))
            screen.blit(text, (8, 8 + i * 20))
        pygame.display.flip()


def _frame(screen, background, ui, dt):
    ui.update(dt)
    screen.blit(background, (0, 0))
    start = time.perf_counter()
    ui.render()
    return (time.perf_counter() - start) * 1000


def run_sheet(path, size, battles=None, colours=None):
    """
    Per battle and colour set: the whole screen in setup, then the bars over a
    shot exchange (every 0.035 s from the first charge), then the finale.
    """
    from ui.effects.battle_interface import BattleInterfaceState
    pygame.init()
    screen = pygame.display.set_mode(size)
    background = backdrop(screen)
    font = pygame.font.SysFont('consolas', 15)
    cols = 3
    probe, _ = open_battle(screen, 'skirmish', 'bright')
    strip = bars_area(probe)
    cell_w = 720
    cell_h = int(cell_w * strip.height / float(strip.width))
    full_h = int(cell_w * 2 * size[1] / float(size[0]))
    rows = []
    for battle in battles or ('large battle', 'defender wins'):
        for colour_set in colours or ('bright', 'dark', 'neutral'):
            ui, _ = open_battle(screen, battle, colour_set)
            setup = []
            for _ in range(int(0.6 / FRAME)):
                _frame(screen, background, ui, FRAME)
            setup.append(('setup', pygame.transform.smoothscale(screen, (cell_w * 2, full_h))))
            setup.append(('setup bars', pygame.transform.smoothscale(screen.subsurface(strip),
                                                                     (cell_w, cell_h))))
            resolve(ui)
            effect = ui.particle_effect
            first = min(shot['arm_t'] for shot in effect.volleys)
            exchange = [first + 0.035 * k for k in range(cols * 3)]
            last = max(shot['fire_t'] for shot in effect.volleys)
            finale = [last + 0.2 * k for k in range(1, cols + 1)]
            wanted = sorted(exchange + finale)
            stills = []
            t = 0.0
            while wanted and ui.state == BattleInterfaceState.ANIMATING:
                _frame(screen, background, ui, FRAME)
                t += FRAME
                if t >= wanted[0]:
                    stills.append((wanted.pop(0), pygame.transform.smoothscale(screen.subsurface(strip),
                                                                             (cell_w, cell_h))))
            rows.append((f'{battle} / {colour_set}', setup, stills))
    height = 0
    for _, setup, stills in rows:
        height += 20 + full_h + 20 + cell_h * ((len(stills) + cols - 1) // cols) + 20 * ((len(stills) + cols - 1) // cols)
    sheet = pygame.Surface((cell_w * cols, height))
    sheet.fill((30, 30, 30))
    y = 0
    for title, setup, stills in rows:
        sheet.blit(font.render(title, True, (255, 230, 160)), (6, y + 2))
        y += 20
        x = 0
        for name, image in setup:
            sheet.blit(image, (x, y))
            sheet.blit(font.render(name, True, (255, 255, 255)), (x + 6, y + 4))
            x += image.get_width()
        y += full_h
        for i, (t, image) in enumerate(stills):
            col, row = i % cols, i // cols
            top = y + row * (cell_h + 20)
            sheet.blit(font.render(f't={t:.2f}s', True, (255, 255, 255)), (col * cell_w + 6, top + 2))
            sheet.blit(image, (col * cell_w, top + 20))
        y += ((len(stills) + cols - 1) // cols) * (cell_h + 20) + 20
    pygame.image.save(sheet, path)
    print(f'Wrote {path}')
    pygame.quit()


def _stats(costs):
    ordered = sorted(costs)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return sum(costs) / len(costs), p95, ordered[-1]


def run_bench(size, setup_seconds=(0.5, 0.0)):
    """
    The battle screen's render cost per frame (the interface's render(): backdrop,
    panels, icon, bars and effects) in setup and through the fight, at 120 fps
    steps; and how long opening the screen takes. Every row starts from cold
    light caches, as the first battle of a session does (later battles reuse them).
    """
    from ui.effects.battle_interface import BattleInterfaceState
    try:
        from ui.effects import battle_fx_effect
    except ImportError:          # before the light version
        battle_fx_effect = None
    pygame.init()
    screen = pygame.display.set_mode(size)
    background = backdrop(screen)
    print(f'{size[0]}x{size[1]}, frames of {FRAME * 1000:.2f} ms')
    print(f"{'battle':>14} {'colours':>8} {'setup s':>7} {'open ms':>8} {'setup avg':>9} "
          f"{'fight avg':>9} {'p95':>6} {'worst':>6}  light kit")
    for battle in BATTLES:
        for colour_set in ('bright', 'dark'):
            for seconds in setup_seconds:
                if battle_fx_effect is not None:
                    battle_fx_effect._shared.clear()
                ui, open_ms = open_battle(screen, battle, colour_set)
                setup = [_frame(screen, background, ui, FRAME) for _ in range(max(1, int(seconds / FRAME)))]
                before = light_counters(ui)
                resolve(ui)
                fight = []
                while ui.state == BattleInterfaceState.ANIMATING:
                    fight.append(_frame(screen, background, ui, FRAME))
                avg, p95, worst = _stats(fight)
                counters = light_counters(ui)
                kit = ''
                if counters:
                    kit = (f'built {counters[0]} (in fight {counters[0] - before[0]}), '
                           f'skipped in fight {counters[1] - before[1]}')
                print(f'{battle:>14} {colour_set:>8} {seconds:7.2f} {open_ms:8.1f} '
                      f'{sum(setup) / len(setup):9.3f} {avg:9.3f} {p95:6.3f} {worst:6.3f}  {kit}')
    pygame.quit()


def main():
    parser = argparse.ArgumentParser(description='Battle screen effects preview')
    parser.add_argument('--size', default='1600x900', help='window size, e.g. 1280x720')
    parser.add_argument('--sheet', help='write a contact sheet of stills to this PNG and exit')
    parser.add_argument('--battles', help='comma-separated battles for --sheet (default: large battle,defender wins)')
    parser.add_argument('--colours', help='comma-separated colour sets for --sheet (default: all)')
    parser.add_argument('--bench', action='store_true', help="print the battle screen's frame cost and exit")
    args = parser.parse_args()
    size = tuple(int(v) for v in args.size.lower().split('x'))
    if args.bench:
        run_bench(size)
    elif args.sheet:
        run_sheet(args.sheet, size,
                  args.battles.split(',') if args.battles else None,
                  args.colours.split(',') if args.colours else None)
    else:
        run_live(size)


if __name__ == '__main__':
    main()
