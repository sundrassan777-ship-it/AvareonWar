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
- The preview (Phase 3): side_view() - a side's player, a row per unit type, a row per
  bonus (no strength: an informed mystery); compose_side_header() / compose_side_body()
  - its fixed top and its rows (which scroll); compose_banner() - the battle's name.

Cinzel has no arrow / check / star glyphs, so the report uses columns, "-" and "x".
"""

import pygame

from config.constants import PLAYER_COLORS, UNIT_PLURALS
from rendering.bottom_panel_kit import SHADOW
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
    # The preview's icons (other sizes)
    for path, style, ref in preview_icons():
        kit.icon(path, max(1, int(ref * scale)), bordered=style == 'framed',
                 crop=style == 'cropped', source=sources.get(path))


def _hero_icon(name):
    from game_state.data_definitions import HERO_TYPES
    return (HERO_TYPES.get(name) or {}).get('icon')


def report_view(territory, won, unit_breakdown, outcome, ours, strengths=None):
    """
    The report's words.

    Args:
        territory: the territory's display name
        won: True / False for the viewer, None when no army survived
        unit_breakdown: {unit_type: {'original', 'survived', 'lost'}} of the viewer's units
        outcome: GameState.battle_outcome() for the viewer, or a stored report's same
            keys; {} (an older report) leaves the outcome lines out
        ours(player): True for the viewer and their allies
        strengths: (the viewer's side's, the enemy's) - the preview keeps them hidden, the
            report shows them (owner, 2026-10-29); None leaves the line out

    Returns:
        {'result', 'headline', 'strengths', 'units': [(type, fought, lost, survived)],
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

    return {'result': result, 'headline': headline, 'units': units, 'lines': lines,
            'strengths': strengths}


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
    if view.get('strengths'):
        # Both strengths, hidden before the fight
        yours, theirs = view['strengths']
        y += s(4)
        line = kit.shadow_text(f"Your strength {yours:.1f}  ·  Enemy {theirs:.1f}",
                               fonts['body'], GOLD_LIGHT)
        centred(line, y)
        y += line.get_height()
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


# ---------------------------------------------------------------- the preview (Phase 3)
# Before the fight (owner, 2026-10-29): a banner naming the battle; per side the player,
# a row per unit type ("2 x Archer", tagged where it counters the enemy or is countered)
# and a row per bonus behind the army's strength, each with its icon - scrolling with the
# mouse wheel when they outgrow the panel. The strength itself is not shown: an informed
# mystery (the bars start full; the fight, then the report, reveal it).

# The bonus list's order (GameState.calculate_army_effective_strength(breakdown=) keys)
BONUS_ORDER = ('vanquish', 'cavalry_tactics', 'battlement_archery', 'divide_and_conquer',
               'territorial', 'veterancy', 'captain', 'keep')
# Each bonus's icon: (path, style - 'framed' / 'cropped' / None, as report_view's)
BONUS_ICONS = {
    'vanquish': ('assets/heroes/abilities/VanquishTheEnemyIcon.png', 'framed'),
    'cavalry_tactics': ('assets/upgrades/CavalryTacticsIcon.png', 'framed'),
    'battlement_archery': ('assets/upgrades/BattlementArcheryIcon.png', 'framed'),
    'divide_and_conquer': ('assets/upgrades/DivideAndConquerIcon.png', 'framed'),
    'territorial': ('assets/BonusButton.png', None),
    'veterancy': ('assets/upgrades/LevelDisplay.png', 'cropped'),
    'captain': ('assets/mapicons/CaptainIcon.png', 'framed'),
    'keep': ('assets/mapicons/KeepIcon.png', None),
}
MATCHUP_STRONG = 1.15  # A unit type's counter factor from here up: its Advantage tag
MATCHUP_WEAK = 0.85    # ... from here down: its Disadvantage tag
MARK_COLORS = {'up': COLOR_DEFENDED, 'down': COLOR_LOST}
MARK_WORDS = {'up': "Advantage", 'down': "Disadvantage"}
FLAG_COLORS = ('Red', 'Blue', 'Green', 'Yellow')    # config.constants PLAYER_COLORS order
FLAG_ICON = 'assets/mapicons/{}Flag1.png'
NEUTRAL_FLAG = 'assets/NeutralFlag.png'
READABLE_LUMINANCE = 140  # A darker player colour is lightened for its name (the 4 player colours are not)
BANNER_FILL = ((62, 51, 36), (31, 25, 17))           # As the turn banner (dark parchment)
BANNER_BORDER = (16, 12)                              # Bronze frame, px at 1600x900
BANNER_PADDING = (34, 8)

# Layout, in px at 1600x900
PREVIEW_ROW = 32         # A unit or bonus row (owner: room to breathe)
UNIT_ROW_ICON = 28
BONUS_ROW_ICON = 24
REACH_ICON = 18          # The unit types a bonus reaches, at the end of its row
BONUS_VALUE_WIDTH = 50


def flag_icon(player, color):
    """The player's army flag: the PLAYER_COLORS entry their colour is (neutral: its own)."""
    if player is None or player < 0:
        return NEUTRAL_FLAG
    colors = [tuple(c) for c in PLAYER_COLORS]
    color = tuple(color[:3])
    index = colors.index(color) if color in colors else player % len(FLAG_COLORS)
    return FLAG_ICON.format(FLAG_COLORS[index])


def readable(color):
    """A player colour light enough to read on the dark wood: same hue, toward warm white."""
    def luminance(rgb):
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    r, g, b = color[:3]
    own = luminance((r, g, b))
    if own >= READABLE_LUMINANCE:
        return (r, g, b)
    warm_white = (255, 240, 215)
    mix = (READABLE_LUMINANCE - own) / (luminance(warm_white) - own)
    return tuple(int(round(c + (w - c) * mix)) for c, w in zip((r, g, b), warm_white))


def _pct(value):
    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"


def bonus_lines(breakdown, composition):
    """
    The bonus rows from calculate_army_effective_strength(breakdown=): one per source and
    amount, [(key, value, label, reach)], in BONUS_ORDER - a source worth different
    amounts to different unit types (veterancy, territories) gets a row per amount.
    `reach`: the unit types it applies to, or [] when that is the whole fighting army
    (Captains aside) or the Captain's own bonus.
    """
    by_key = {}
    for entry in breakdown:
        if entry.get('key') != 'matchup':
            by_key.setdefault(entry['key'], []).append(entry)
    fighting = {unit_type for unit_type, count in composition.items()
                if count > 0 and unit_type != 'Captain'}
    lines = []
    for key in BONUS_ORDER:
        entries = by_key.get(key)
        if not entries:
            continue
        label = entries[0]['label']
        if key == 'keep':
            lines.append((key, f"+{_pct(entries[0]['flat'])}", label, []))
            continue
        by_value = {}
        for entry in entries:
            by_value.setdefault(_pct(entry['pct']), set()).add(entry['unit_type'])
        for value, types in sorted(by_value.items(), key=lambda item: float(item[0]), reverse=True):
            reach = [] if key == 'captain' or types == fighting else sorted(types)
            lines.append((key, f"+{value}%", label, reach))
    return lines


def unit_rows(composition, breakdown):
    """[(unit_type, count, mark)]: mark 'up' / 'down' where it counters / is countered."""
    factors = {entry['unit_type']: entry['factor'] for entry in breakdown
               if entry.get('key') == 'matchup'}
    rows = []
    for unit_type, count in sorted(composition.items()):
        if count <= 0:
            continue
        factor = factors.get(unit_type, 1.0)
        mark = 'up' if factor >= MATCHUP_STRONG else ('down' if factor <= MATCHUP_WEAK else None)
        rows.append((unit_type, count, mark))
    return rows


def matchup_tip(entry):
    """
    The words of a unit type's Advantage / Disadvantage tooltip (owner, 2026-10-29: the
    tag alone did not say where it came from): (title, lines), from its breakdown entry
    ('matchup': the counter factor and the enemy units it is made of).
    """
    unit_type = entry['unit_type']
    ours = UNIT_PLURALS.get(unit_type, unit_type)
    factor = entry['factor']
    title = f"{'Advantage' if factor >= 1 else 'Disadvantage'}  ×{factor:.2f}"
    total = entry.get('enemy_total', 0)
    counters, counters_count = entry.get('counters'), entry.get('counters_count', 0)
    countered_by, countered_count = entry.get('countered_by'), entry.get('countered_by_count', 0)
    lines = []
    if counters_count:
        lines.append(f"{ours} counter {UNIT_PLURALS.get(counters, counters)}: "
                     f"×2 against the enemy's {counters_count}.")
    if countered_count:
        lines.append(f"{UNIT_PLURALS.get(countered_by, countered_by)} counter {ours}: "
                     f"×0.5 against the enemy's {countered_count}.")
    rest = total - counters_count - countered_count
    if rest > 0:
        lines.append(f"×1 against the other {rest} {_plural(rest, 'unit', 'units')}.")
    lines.append(f"Over all {total} enemy {_plural(total, 'unit', 'units')}: ×{factor:.2f} strength.")
    return title, lines


def side_view(role, name, player, color, composition, breakdown, keep=False):
    """One side of the preview: {'role', 'name', 'color', 'flag', 'units', 'empty',
    'bonuses', 'matchups'} (no pygame; no strength - the preview keeps it a mystery).
    'matchups': {unit_type: its breakdown entry} for the tags' tooltips."""
    return {
        'role': role,
        'name': name,
        'color': readable(color),
        'flag': flag_icon(player, color),
        'units': unit_rows(composition, breakdown),
        'empty': "The Keep stands alone" if keep else "No units",
        'bonuses': bonus_lines(breakdown, composition),
        'matchups': {entry['unit_type']: entry for entry in breakdown
                     if entry.get('key') == 'matchup'},
    }


def preview_icons():
    """(path, style, px at 1600x900) of the preview's 1024 px icons, for prewarm() (the
    flags are small files)."""
    specs = [(UNIT_ICON.format(unit_type), 'framed', UNIT_ROW_ICON) for unit_type in UNIT_PLURALS]
    specs += [(UNIT_ICON.format(unit_type), 'framed', REACH_ICON) for unit_type in UNIT_PLURALS]
    specs += [(path, style, BONUS_ROW_ICON) for path, style in BONUS_ICONS.values()]
    return specs


def _mark(surface, x, y, size, mark):
    """An advantage (up) / disadvantage (down) triangle with a dark rim."""
    color = MARK_COLORS[mark]
    if mark == 'up':
        points = [(x + size / 2.0, y), (x + size, y + size), (x, y + size)]
    else:
        points = [(x, y), (x + size, y), (x + size / 2.0, y + size)]
    pygame.draw.polygon(surface, color, points)
    pygame.draw.polygon(surface, SHADOW, points, 1)


def side_indent(width):
    """How far in from the content's edges the rows start: where the separators start."""
    return (width - int(width * 0.9)) // 2


def compose_side_header(view, width, fonts, scale):
    """A side's fixed top: ATTACKING / DEFENDING, the flag and the name, a separator."""
    def s(value):
        return max(1, int(value * scale))
    blits, y = [], 0

    def centred(surf, top):
        blits.append((surf, ((width - surf.get_width()) // 2, top)))

    role = kit.shadow_text(view['role'], fonts['role'], GOLD)
    centred(role, y)
    y += role.get_height() + s(2)
    name_font = fonts['name']
    flag_h = name_font.get_height()
    flag_gap = s(8)
    lines = _wrap(view['name'], name_font, width - flag_h - flag_gap)
    rendered = [kit.shadow_text(line, name_font, view['color']) for line in lines]
    block_w = flag_h + flag_gap + max(text.get_width() for text in rendered)
    block_h = sum(text.get_height() for text in rendered)
    x = (width - block_w) // 2
    blits.append((kit.icon(view['flag'], flag_h, crop=True), (x, y + (block_h - flag_h) // 2)))
    line_y = y
    for text in rendered:
        blits.append((text, (x + flag_h + flag_gap, line_y)))
        line_y += text.get_height()
    y += block_h + s(8)
    rule = kit.separator(int(width * 0.9))
    centred(rule, y)
    y += rule.get_height() + s(10)
    return _flatten(width, y, blits)


def compose_side_body(view, width, fonts, scale):
    """
    A side's rows, which scroll when they outgrow the panel: the army - a row per unit
    type, "2 x Archer", tagged Advantage / Disadvantage - then the bonuses, each with its
    icon, value, name and the unit types it reaches. `width` is the rows' own width.

    Returns:
        (surface, tags): tags [(rect in the surface, unit_type)] - where each tag is, for
        its tooltip (matchup_tip)
    """
    def s(value):
        return max(1, int(value * scale))
    blits, y = [], 0
    tags = []
    row_h = s(PREVIEW_ROW)

    heading = kit.shadow_text("Army", fonts['heading'], GOLD_LIGHT)
    blits.append((heading, (0, y)))
    y += heading.get_height() + s(2)
    icon = s(UNIT_ROW_ICON)
    if view['units']:
        for unit_type, count, mark in view['units']:
            mid = y + row_h // 2
            blits.append((kit.icon(UNIT_ICON.format(unit_type), icon, bordered=True),
                          (0, mid - icon // 2)))
            text = kit.shadow_text(f"{count} × {unit_type}", fonts['body'], PARCHMENT)
            blits.append((text, (icon + s(9), mid - text.get_height() // 2)))
            if mark:
                word = kit.shadow_text(MARK_WORDS[mark], fonts['tag'], MARK_COLORS[mark])
                side = max(6, fonts['tag'].get_height() // 2)
                word_x = width - word.get_width()
                blits.append((word, (word_x, mid - word.get_height() // 2)))
                blits.append((_mark_surface(side, mark), (word_x - side - s(5), mid - side // 2)))
                tag_left = word_x - side - s(5)
                tags.append((pygame.Rect(tag_left - s(4), y, width - tag_left + s(4), row_h), unit_type))
            y += row_h
    else:
        empty = kit.shadow_text(view['empty'], fonts['body'], NUMBER_DIM)
        blits.append((empty, (0, y + (row_h - empty.get_height()) // 2)))
        y += row_h

    if view['bonuses']:
        y += s(SECTION_GAP)
        heading = kit.shadow_text("Bonuses", fonts['heading'], GOLD_LIGHT)
        blits.append((heading, (0, y)))
        y += heading.get_height() + s(2)
        bonus_icon = s(BONUS_ROW_ICON)
        reach_icon = s(REACH_ICON)
        value_right = bonus_icon + s(8) + s(BONUS_VALUE_WIDTH)
        label_x = value_right + s(8)
        for key, value, label, reach in view['bonuses']:
            mid = y + row_h // 2
            path, style = BONUS_ICONS.get(key, (None, None))
            if path:
                blits.append((kit.icon(path, bonus_icon, bordered=style == 'framed',
                                       crop=style == 'cropped'), (0, mid - bonus_icon // 2)))
            value_surf = kit.shadow_text(value, fonts['body'], GOLD_LIGHT)
            blits.append((value_surf, (value_right - value_surf.get_width(), mid - value_surf.get_height() // 2)))
            reach_w = len(reach) * (reach_icon + s(3))
            x = width - reach_w + s(3)
            for unit_type in reach:
                blits.append((kit.icon(UNIT_ICON.format(unit_type), reach_icon, bordered=True),
                              (x, mid - reach_icon // 2)))
                x += reach_icon + s(3)
            label_surf = kit.shadow_text(
                _fit(label, fonts['body'], width - label_x - reach_w - s(6)), fonts['body'], PARCHMENT)
            blits.append((label_surf, (label_x, mid - label_surf.get_height() // 2)))
            y += row_h
    return _flatten(width, y + s(4), blits), tags


def _mark_surface(size, mark):
    """The tag's triangle on its own small surface (cached)."""
    def build():
        surf = pygame.Surface((size + 1, size + 1), pygame.SRCALPHA)
        _mark(surf, 0, 0, size, mark)
        return surf
    return kit.cached(('mark', size, mark), build)


def compose_banner(title, subtitle, fonts, scale):
    """The battle's name over the panels: gold Cinzel in the turn banner's bronze frame."""
    def s(value):
        return max(1, int(value * scale))
    text = kit.shadow_text(title, fonts['banner_title'], GOLD_LIGHT)
    sub = kit.shadow_text(subtitle, fonts['banner_sub'], PARCHMENT) if subtitle else None
    sub_gap = s(14)
    inner_w = text.get_width() + ((sub_gap + sub.get_width()) if sub else 0)
    inner_h = max(text.get_height(), sub.get_height() if sub else 0)
    bx, by = s(BANNER_BORDER[0]), s(BANNER_BORDER[1])
    size = (inner_w + 2 * (bx + s(BANNER_PADDING[0])), inner_h + 2 * (by + s(BANNER_PADDING[1])))
    plate = kit.bronze_plate(size, (bx, by), BANNER_FILL).copy()
    x = (size[0] - inner_w) // 2
    plate.blit(text, (x, (size[1] - text.get_height()) // 2))
    if sub:
        plate.blit(sub, (x + text.get_width() + sub_gap, (size[1] - sub.get_height()) // 2))
    return plate


def _fit(text, font, max_width):
    """`text`, cut with an ellipsis to `max_width`."""
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "...")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."
