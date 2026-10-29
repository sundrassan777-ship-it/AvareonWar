# -*- coding: utf-8 -*-
"""
Battle screen panels - the battle screen's content (EnhancedBattleInterface,
ui/effects/battle_interface.py), composed once onto cached surfaces.

The battle report (Phase 2, owner 2026-10-28/29): VICTORY / DEFEAT and what happened to
the territory, the viewer's army (fought / lost / survived per unit type), then the
outcome, every line with an icon - the Keep, each building type destroyed / captured,
the heroes slain there, the XP and a line per level-up of the viewer's survivors.

- report_view(): the wording, from the result, the viewer's unit breakdown and
  GameState.battle_outcome() (or the same keys of a stored Battle Report). No pygame.
- compose_report(): draws a view with the battle screen kit (ui/battle_screen_kit.py), as
  a header that stays put and a body that scrolls when the report outgrows its panel.
- report_icons() / prewarm(): every icon a report can show, baked before the first one.

Cinzel has no arrow / check / star glyphs, so the report uses columns, "-" and "x".
"""

import pygame

from config.constants import UNIT_PLURALS
from rendering.sidebar_widgets import GOLD, GOLD_DARK, GOLD_LIGHT, PARCHMENT
from ui import battle_screen_kit as kit
from ui.battle_report_popup import COLOR_DEFENDED, COLOR_LOST

# Tones of the report's lines
TONE_COLORS = {
    'good': PARCHMENT,
    'bad': COLOR_LOST,
    'xp': GOLD_LIGHT,
    'plain': PARCHMENT,
}
RESULT_TEXT = {'victory': "Victory", 'defeat': "Defeat", 'no_victor': "No Victor"}
RESULT_COLORS = {'victory': COLOR_DEFENDED, 'defeat': COLOR_LOST, 'no_victor': GOLD_LIGHT}
NUMBER_DIM = (198, 184, 158)  # A dash for no losses, 0 survivors (readable on the wood)

UNIT_ICON = 'assets/mapicons/{}Icon.png'
BUILDING_ICON = 'assets/mapicons/{}Icon.png'      # The building's name without spaces
KEEP_ICONS = {'Keep': 'assets/mapicons/KeepIcon.png', 'Castle': 'assets/mapicons/CastleIcon.png'}
XP_ICON = 'assets/upgrades/LevelDisplay.png'
# A report from before the buildings were listed by type has only their counts
RAZED_ICON = 'assets/mapicons/PlotIcon.png'
CAPTURED_ICON = 'assets/mapicons/FarmIcon.png'
BUILDING_PLURALS = {'Barracks': 'Barracks', 'Training Grounds': 'Training Grounds'}

# Layout, in px at 1600x900 (times the battle screen's scale)
ROW_HEIGHT = 30
ICON_SIZE = 24
ICON_GAP = 9
COLUMN_WIDTH = 78
SECTION_GAP = 12
COLUMNS = ("Fought", "Lost", "Survived")


def _plural(count, singular, plural):
    return singular if count == 1 else plural


def _counted(count, name, plurals):
    """'Farm' / '2 Farms' (one goes unnumbered)."""
    if count == 1:
        return name
    return f"{count} {plurals.get(name, name + 's')}"


def _building_icon(name):
    return BUILDING_ICON.format(name.replace(' ', ''))


def report_icons():
    """(path, style) of every icon a report can show (see report_view)."""
    from game_state.data_definitions import BUILDING_TYPES, HERO_TYPES
    specs = [(UNIT_ICON.format(unit_type), 'framed') for unit_type in UNIT_PLURALS]
    specs += [(path, None) for path in KEEP_ICONS.values()]
    specs += [(_building_icon(name), None) for name in BUILDING_TYPES if name != 'Keep']
    specs += [(RAZED_ICON, None), (CAPTURED_ICON, None), (XP_ICON, 'cropped')]
    specs += [(info['icon'], 'framed') for info in HERO_TYPES.values() if info.get('icon')]
    return list(dict.fromkeys(specs))


def prewarm(scale, sources=None):
    """
    Bake every icon a report can show at this scale, before the first battle (each
    image is 1024 px: decoding them as the first report's splash began cost ~130 ms).
    `sources`: {path: surface} the game has already decoded, so nothing is read twice.
    """
    sources = sources or {}
    size = max(1, int(ICON_SIZE * scale))
    for path, style in report_icons():
        kit.icon(path, size, bordered=style == 'framed', crop=style == 'cropped',
                 source=sources.get(path))


def _hero_icon(name):
    from game_state.data_definitions import HERO_TYPES
    return (HERO_TYPES.get(name) or {}).get('icon')


def report_view(territory, won, unit_breakdown, outcome, ours):
    """
    The report's words.

    Args:
        territory: the territory's display name
        won: True / False for the viewer, None when no army survived
        unit_breakdown: {unit_type: {'original', 'survived', 'lost'}} of the viewer's units
        outcome: GameState.battle_outcome() for the viewer, or a stored report's same
            keys; {} (an older report) leaves the outcome lines out
        ours(player): True for the viewer and their allies

    Returns:
        {'result', 'headline', 'units': [(type, fought, lost, survived)],
         'lines': [(icon path or None, icon style, text, tone)]} - the style 'framed'
        (portraits: the gold IconBorder), 'cropped' (transparent margins trimmed) or None
    """
    previous_owner = outcome.get('previous_owner', -1)
    ours_before = previous_owner is not None and previous_owner >= 0 and ours(previous_owner)

    if won is None:
        result, headline = 'no_victor', f"Both armies fell at {territory}"
    elif not outcome:
        result, headline = ('victory' if won else 'defeat'), territory
    elif won:
        result = 'victory'
        headline = f"{territory} held" if (outcome.get('held') and ours_before) else f"{territory} captured"
    else:
        result = 'defeat'
        headline = f"{territory} lost" if ours_before else f"Repelled at {territory}"

    units = [(unit_type, data.get('original', 0), data.get('lost', 0), data.get('survived', 0))
             for unit_type, data in sorted(unit_breakdown.items())]

    lines = []
    keep, keep_name = outcome.get('keep'), outcome.get('keep_name') or 'Keep'
    if keep == 'destroyed':
        lines.append((KEEP_ICONS.get(keep_name), None, f"{keep_name} destroyed",
                      'bad' if ours_before else 'good'))
    elif keep == 'held':
        lines.append((KEEP_ICONS.get(keep_name), None, f"{keep_name} held",
                      'good' if ours_before else 'bad'))

    destroyed_by_type = outcome.get('buildings_destroyed')
    if destroyed_by_type is not None:
        # Each building type with its own icon (owner, 2026-10-29)
        for name, count in sorted(destroyed_by_type.items()):
            lines.append((_building_icon(name), None,
                          f"{_counted(count, name, BUILDING_PLURALS)} destroyed",
                          'bad' if ours_before else 'plain'))
        for name, count in sorted((outcome.get('buildings_captured') or {}).items()):
            text = (f"{_counted(count, name, BUILDING_PLURALS)} taken by the enemy" if ours_before
                    else f"{_counted(count, name, BUILDING_PLURALS)} captured")
            lines.append((_building_icon(name), None, text, 'bad' if ours_before else 'good'))
    else:
        # An older report: counts only (a fallen Keep is one of structures_destroyed)
        razed = max(0, outcome.get('structures_destroyed', 0) - (1 if keep == 'destroyed' else 0))
        if razed:
            lines.append((RAZED_ICON, None,
                          f"{razed} {_plural(razed, 'building', 'buildings')} destroyed",
                          'bad' if ours_before else 'plain'))
        captured = outcome.get('structures_captured', 0)
        if captured:
            text = (f"{captured} {_plural(captured, 'building', 'buildings')} taken by the enemy"
                    if ours_before else
                    f"{captured} {_plural(captured, 'building', 'buildings')} captured")
            lines.append((CAPTURED_ICON, None, text, 'bad' if ours_before else 'good'))

    for owner, hero in outcome.get('heroes_slain') or []:
        if ours(owner):
            lines.append((_hero_icon(hero), 'framed', f"Hero slain: {hero}", 'bad'))
        else:
            lines.append((_hero_icon(hero), 'framed', f"Enemy hero slain: {hero}", 'good'))

    xp = outcome.get('xp_per_unit', 0)
    if xp:
        lines.append((XP_ICON, 'cropped', f"+{xp} XP for each survivor", 'xp'))
        # One line per level-up, with the unit's portrait (owner: every line has an icon)
        for unit_type, level, count in outcome.get('level_ups') or []:
            name = UNIT_PLURALS.get(unit_type, unit_type) if count > 1 else unit_type
            lines.append((UNIT_ICON.format(unit_type), 'framed',
                          f"{count} {name} reached level {level}", 'xp'))

    return {'result': result, 'headline': headline, 'units': units, 'lines': lines}


def compose_report(view, width, fonts, scale):
    """
    The report's content (above its Close button) on two transparent surfaces: the
    header (caption, VICTORY / DEFEAT, what happened to the territory), which stays
    put, and the body (the army table, the outcome), which scrolls when the report is
    taller than its panel.

    Args:
        view: report_view()
        width: content width, px
        fonts: {'caption', 'banner', 'headline', 'heading', 'columns', 'body'}
        scale: the battle screen's scale (1.0 at 1600x900)

    Returns:
        (header, body)
    """
    def s(value):
        return max(1, int(value * scale))

    def centred(surf, top):
        blits.append((surf, ((width - surf.get_width()) // 2, top)))

    # VICTORY / DEFEAT under a small caption, and what happened to the territory
    blits, y = [], 0
    caption = kit.shadow_text("Battle Report", fonts['caption'], GOLD)
    centred(caption, y)
    y += caption.get_height() + s(2)
    banner = kit.shadow_text(RESULT_TEXT[view['result']], fonts['banner'],
                             RESULT_COLORS[view['result']])
    centred(banner, y)
    y += banner.get_height() + s(2)
    for line in _wrap(view['headline'], fonts['headline'], width):
        surf = kit.shadow_text(line, fonts['headline'], PARCHMENT)
        centred(surf, y)
        y += surf.get_height()
    y += s(SECTION_GAP)
    rule = kit.separator(int(width * 0.9))
    centred(rule, y)
    y += rule.get_height() + s(SECTION_GAP)
    header = _flatten(width, y, blits)

    # The viewer's army: one row per unit type, then the total
    blits, y, rules = [], 0, []
    col_w = s(COLUMN_WIDTH)
    centres = [width - col_w // 2 - (len(COLUMNS) - 1 - i) * col_w for i in range(len(COLUMNS))]
    title = kit.shadow_text("Your Army", fonts['heading'], GOLD_LIGHT)
    title_h = title.get_height()
    blits.append((title, (0, y)))
    for centre, name in zip(centres, COLUMNS):
        label = kit.shadow_text(name, fonts['columns'], GOLD_LIGHT)
        blits.append((label, (centre - label.get_width() // 2, y + title_h - label.get_height())))
    y += title_h + s(6)

    icon_size = s(ICON_SIZE)
    row_h = max(icon_size + 2, s(ROW_HEIGHT))
    text_x = icon_size + s(ICON_GAP)
    if view['units']:
        for unit_type, fought, lost, survived in view['units']:
            mid = y + row_h // 2
            blits.append((kit.icon(UNIT_ICON.format(unit_type), icon_size, bordered=True),
                          (0, mid - icon_size // 2)))
            name = kit.shadow_text(unit_type, fonts['body'], PARCHMENT)
            blits.append((name, (text_x, mid - name.get_height() // 2)))
            _numbers(blits, centres, mid, fonts['body'], fought, lost, survived)
            y += row_h
        if len(view['units']) > 1:          # (one unit type: its row is the total)
            rules.append((y + s(3), centres[0] - col_w // 2))
            y += s(7)
            total = [sum(unit[i] for unit in view['units']) for i in (1, 2, 3)]
            mid = y + row_h // 2
            label = kit.shadow_text("Total", fonts['heading'], GOLD_LIGHT)
            blits.append((label, (text_x, mid - label.get_height() // 2)))
            _numbers(blits, centres, mid, fonts['heading'], *total)
            y += row_h
    else:
        none = kit.shadow_text("No units fought here", fonts['body'], NUMBER_DIM)
        blits.append((none, (0, y + (row_h - none.get_height()) // 2)))
        y += row_h

    # The outcome: the Keep, the buildings, heroes, XP and level-ups
    if view['lines']:
        y += s(SECTION_GAP)
        rule = kit.separator(int(width * 0.9))
        centred(rule, y)
        y += rule.get_height() + s(SECTION_GAP)
        line_h = fonts['body'].get_linesize()
        for icon_path, style, text, tone in view['lines']:
            wrapped = _wrap(text, fonts['body'], width - text_x)
            block_h = max(row_h, line_h * len(wrapped))
            if icon_path:
                blits.append((kit.icon(icon_path, icon_size, bordered=style == 'framed',
                                       crop=style == 'cropped'),
                              (0, y + (block_h - icon_size) // 2)))
            top = y + (block_h - line_h * len(wrapped)) // 2
            for i, line in enumerate(wrapped):
                blits.append((kit.shadow_text(line, fonts['body'], TONE_COLORS[tone]),
                              (text_x, top + i * line_h)))
            y += block_h
    body = _flatten(width, y, blits, rules)
    return header, body


def _flatten(width, height, blits, rules=()):
    """One transparent surface with `blits` on it (and thin gold `rules`: (y, left))."""
    surface = pygame.Surface((width, max(1, height)), pygame.SRCALPHA)
    for line_y, left in rules:
        pygame.draw.line(surface, GOLD_DARK, (left, line_y), (width - 1, line_y), 1)
    for surf, pos in blits:
        surface.blit(surf, pos)
    return surface


def _numbers(blits, centres, mid, font, fought, lost, survived):
    """The three columns of a row: fought, lost (red, or a dash), survived."""
    cells = [
        (str(fought), PARCHMENT),
        (f"−{lost}" if lost else "—", COLOR_LOST if lost else NUMBER_DIM),
        (str(survived), NUMBER_DIM if survived == 0 else (COLOR_DEFENDED if lost == 0 else PARCHMENT)),
    ]
    for centre, (text, color) in zip(centres, cells):
        surf = kit.shadow_text(text, font, color)
        blits.append((surf, (centre - surf.get_width() // 2, mid - surf.get_height() // 2)))


def _wrap(text, font, max_width, max_lines=2):
    """
    Word-wrap `text` to `max_width`. Two lines are balanced (no lone last word, a
    break after a comma when one is close); past `max_lines` the last line is cut
    with an ellipsis.
    """
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.size(trial)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) == 2:
        best = None
        for cut in range(1, len(words)):
            first, second = " ".join(words[:cut]), " ".join(words[cut:])
            w1, w2 = font.size(first)[0], font.size(second)[0]
            if w1 > max_width or w2 > max_width:
                continue
            # The wider line, a little less after a comma (a natural break)
            cost = max(w1, w2) - (font.size(" ")[0] * 6 if first.endswith(',') else 0)
            if best is None or cost < best[0]:
                best = (cost, [first, second])
        if best is not None:
            lines = best[1]
    if len(lines) > max_lines:
        last = " ".join(lines[max_lines - 1:])
        while last and font.size(last + "...")[0] > max_width:
            last = last[:-1]
        lines = lines[:max_lines - 1] + [last.rstrip() + "..."]
    return lines or [text]
