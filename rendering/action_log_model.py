# -*- coding: utf-8 -*-
"""
Action Log model — turns game_state.messages (plain strings) into an organised log.

game_state.messages is a flat list of ~270 kinds of free-text lines with no metadata.
The old sidebar drew it as a wall of text, re-ran a regex filter over the WHOLE
history every frame, and estimated scroll limits from the unfiltered count (so it
scrolled past its end and could hide the newest lines). This module is pure Python
(no pygame) so it is unit-testable; the renderer only lays its rows out in pixels.

STRUCTURE
- Groups: a non-indented line plus the indented lines that follow it ("  Defender
  casualties: ..."). "=== BATTLE in X! ===" banners own their indented details.
  Blocks between two "=====" rule lines (victory / elimination) become one group.
- Turn sections: "--- Player N's Turn ---" headers. The local player's header opens a
  "Turn k" band; another player's header becomes a small "<Name>'s turn" sub-heading.
  Headers are emitted lazily — only when a visible group follows — so a turn whose
  messages are all filtered away leaves no empty heading. Lines before the first
  header sit under "Start of game"; simultaneous mode (no headers) is a flat list.

VISIBILITY (replaces ui_renderer's is_local_player_message)
- A group is shown if its parent or ANY child mentions the local player ("Player N"
  or their name), or if nobody is mentioned at all (global lines).
  The old per-line rule hid an indented detail that only named the opponent even
  inside the local player's own battle, and showed other players' battle details
  orphaned under a hidden header.
- Victory / elimination blocks are always shown (the old filter hid "Player 2
  ELIMINATED!" but kept its "=====" lines, leaving an empty banner).
- An optional category filter (chips, P6) keeps only groups of those categories.

CATEGORIES: classify() — first matching rule wins (see _RULES).

INCREMENTAL: update() processes only new messages and re-derives rows from the last
(possibly still growing) group onward. A list replacement (save load), a shrink (tests
call messages.clear()), or a change of local player / names / filter rebuilds.
"""

import re
from collections import namedtuple

# Row kinds: 'section' (Start of game), 'turn' (Turn k band), 'subturn' (Name's turn),
#            'banner' (battle / movement heading), 'entry' (a line), 'victory' (block)
Row = namedtuple('Row', ['kind', 'text', 'category', 'indent', 'group'])

CATEGORIES = ('battle', 'conquest', 'economy', 'construction', 'training', 'research',
              'hero', 'orders', 'victory', 'error', 'other')

_TURN_RE = re.compile(r"^--- Player (\d+)'s Turn ---$")
_RULE_RE = re.compile(r"^=+$")
_BANNER_RE = re.compile(r"^=== (.+?) ===$")
_PLAYER_RE = re.compile(r'Player (\d+)')

# (category, pattern) checked in order on the raw (un-renamed) message
_RULES = [
    ('victory', re.compile(r"\b(PLAYER|TEAM) \d+ WINS!|ELIMINATED!|Last (player|team) standing|"
                           r"Total conquest|Capital conquered", re.I)),
    ('error', re.compile(r"^(Not enough gold|Cannot |Can't |Hero limit|Command limit|Army limit|"
                         r"Training queue full|Territories are not adjacent|No armies available|"
                         r"No garrison found|This is not a Keep|You already have|This Keep already has|"
                         r"Invalid |Already researching|Some selected armies|Warning:|WARNING:|You don|"
                         r"Only one |Not enough |This is not |This Keep is already|No orders to execute|"
                         r"Error )|is locked!|requires a Castle|Cannot reinforce")),
    ('hero', None),   # built from HERO_TYPES below (hero + ability names)
    ('battle', re.compile(r"[Bb]attle|BATTLE|casualties|\bWINS\b|Phase [12]|\bTIE\b|defended|defends alone|"
                          r"Winner (lost|suffers)|Effective|Participants|Scavenge|Safe Haven|Pillage|"
                          r"Leave Nothing Behind|Keep holds|Keep destroyed|repelled|eliminate each other|"
                          r"rolls:|defense bonus|Two-Phase Combat|allied armies|Raze the Countryside|troops|"
                          r"retaliate|Garrison eliminated|Perfect clash")),
    ('conquest', re.compile(r"conquers |reinforced (ally )?|has revolted|captured|claims ")),
    ('research', re.compile(r"[Rr]esearch|[Tt]echnology")),
    ('training', re.compile(r"\btrained\b|Training (canceled|cancelled|paused)|Training Grounds|"
                            r"started training|[Tt]raining |\bXP\b|reached level")),
    ('construction', re.compile(r"[Cc]omplet|[Cc]onstruction|Castle upgrade|Upgrading Keep|"
                                r"started building|destroyed, \d+ gold|building\(s\) destroyed|"
                                r"[Dd]emolish")),
    ('economy', re.compile(r"earned|[Ii]ncome|[Tt]ax|Embargo|Invested|sent \d+g|\b\d+ [Gg]old\b|gold|"
                           r"% less this turn")),
    ('orders', re.compile(r"^(Order created|Order cancelled|Cancelled \d+ orders|Previous order|"
                          r"Auto-cancelled|Orders cancelled due|Planning time expired|Army overflow)|"
                          r"armies remain in|armies arrive|armies leave|disbanded|[Ee]xecuting|Armies moving")),
]


def _hero_pattern():
    """Hero rule from the game data: every hero's name and ability names.

    "Player 1: Halon Nextroy trained in Lobardia!" says neither "hero" nor any
    keyword, so the names themselves are what identify hero events.
    """
    words = [r"\b[Hh]ero(es)?\b", "silenced", "Silenced", "Veterancy"]
    try:
        from game_state.data_definitions import HERO_TYPES
        names = set(HERO_TYPES)
        for hero in HERO_TYPES.values():
            names.update(ability['name'] for ability in hero.get('abilities', []))
        words.extend(re.escape(name) for name in sorted(names, key=len, reverse=True))
    except (ImportError, AttributeError, KeyError, TypeError):
        pass
    return re.compile('|'.join(words))


_RULES = [(category, pattern if pattern is not None else _hero_pattern()) for category, pattern in _RULES]


def classify(message):
    """Category of one raw message (see _RULES); 'other' when nothing matches."""
    text = message.strip()
    for category, pattern in _RULES:
        if pattern.search(text):
            return category
    return 'other'


def banner_title(message):
    """'=== BATTLE in Lentria! ===' -> 'Battle in Lentria!'; None if not a banner."""
    match = _BANNER_RE.match(message.strip())
    if not match:
        return None
    words = match.group(1).strip().split(' ')
    if words and words[0].isupper() and len(words[0]) > 1:
        words[0] = words[0].capitalize()
    return ' '.join(words)


class ActionLogModel:
    """Incrementally maintained rows for the Action Log (see module docstring)."""

    def __init__(self):
        self.rows = []
        self._reset_state()

    def _reset_state(self):
        self.rows = []
        self._source_id = None
        self._processed = 0
        self._key = None
        self._groups = []          # dicts: kind, parent, children, player, lines
        self._group_row_start = []  # rows length before each group's rows
        self._group_state = []      # (turn_count, pending_header) before each group
        self._in_rule_block = None  # open victory block (list of lines) or None
        # Turn counter + headings waiting for their first visible group, after the
        # last derived group: lets new groups continue without re-deriving everything
        self._state_after_last = (0, (('section', 'Start of game'),))

    # ------------------------------------------------------------------ update

    def update(self, messages, local_player, names, category_filter=None):
        """Bring rows up to date. Returns the index of the first changed row, or None."""
        key = (local_player, tuple(names), tuple(sorted(category_filter)) if category_filter else None)
        if (id(messages) != self._source_id or len(messages) < self._processed or key != self._key):
            self._reset_state()
            self._source_id = id(messages)
            self._key = key
        if len(messages) == self._processed:
            return None

        self.local_player = local_player
        self.names = list(names)
        self.category_filter = set(category_filter) if category_filter else None

        first_changed_group = max(0, len(self._groups) - 1)
        for raw in messages[self._processed:]:
            self._ingest(str(raw))
        self._processed = len(messages)
        return self._derive_rows(first_changed_group)

    def _ingest(self, message):
        """Fold one raw message into the group structure."""
        stripped = message.strip()
        # Victory / elimination blocks: "=====" ... "====="
        if _RULE_RE.match(stripped):
            if self._in_rule_block is None:
                self._in_rule_block = {'kind': 'victory', 'parent': '', 'children': [], 'player': None,
                                       'lines': []}
                self._groups.append(self._in_rule_block)
            else:
                self._in_rule_block = None
            return
        if self._in_rule_block is not None:
            if stripped:
                self._in_rule_block['lines'].append(stripped)
            return
        if not stripped:
            return  # blank spacer lines around blocks

        turn = _TURN_RE.match(stripped)
        if turn:
            self._groups.append({'kind': 'turn', 'parent': stripped, 'children': [],
                                 'player': int(turn.group(1)) - 1})
            return
        indent = len(message) - len(message.lstrip(' '))
        last = self._groups[-1] if self._groups else None
        if indent >= 2 and last is not None and last['kind'] in ('entry', 'banner'):
            last['children'].append(message)
            return
        kind = 'banner' if _BANNER_RE.match(stripped) else 'entry'
        self._groups.append({'kind': kind, 'parent': message, 'children': [], 'player': None})

    # ------------------------------------------------------------------ rows

    def _mentions(self, text):
        """Player indices a line mentions ("Player N" or a player's name)."""
        found = {int(m) - 1 for m in _PLAYER_RE.findall(text)}
        for index, name in enumerate(self.names):
            if name and name in text:
                found.add(index)
        return found

    def _rename(self, text):
        """'Player 2' -> that player's display name."""
        def replace(match):
            index = int(match.group(1)) - 1
            if 0 <= index < len(self.names) and self.names[index]:
                return self.names[index]
            return match.group(0)
        return _PLAYER_RE.sub(replace, text)

    def _group_visible(self, group, category):
        if group['kind'] == 'victory':
            return True
        if self.category_filter is not None and category not in self.category_filter:
            return False
        mentioned = set()
        for line in [group['parent']] + group['children']:
            mentioned |= self._mentions(line)
        return not mentioned or self.local_player in mentioned

    def _derive_rows(self, start_group):
        """Re-emit rows for groups[start_group:] (earlier rows are unchanged)."""
        # `pending` = headings (kind, text) waiting for the next visible group
        if start_group < len(self._group_row_start):
            del self.rows[self._group_row_start[start_group]:]
            turn_count, pending = self._group_state[start_group]
            del self._group_row_start[start_group:]
            del self._group_state[start_group:]
        else:
            start_group = len(self._group_row_start)
            turn_count, pending = self._state_after_last
        first_changed_row = len(self.rows)

        for gi in range(start_group, len(self._groups)):
            group = self._groups[gi]
            self._group_row_start.append(len(self.rows))
            self._group_state.append((turn_count, pending))
            kind = group['kind']
            if kind == 'turn':
                if group['player'] == self.local_player:
                    # A new round: earlier headings that never got content are dropped
                    turn_count += 1
                    pending = (('turn', f"Turn {turn_count}"),)
                else:
                    index = group['player']
                    name = self.names[index] if 0 <= index < len(self.names) and self.names[index] \
                        else f"Player {index + 1}"
                    # Keep a still-pending "Turn k" / "Start of game" band; replace any
                    # sub-heading of an earlier player that showed nothing
                    pending = tuple(p for p in pending if p[0] != 'subturn') + (('subturn', f"{name}'s turn"),)
                continue

            if kind == 'victory':
                category = 'victory'
            else:
                category = classify(group['parent'])
                if category == 'other':
                    for child in group['children']:
                        child_category = classify(child)
                        if child_category != 'other':
                            category = child_category
                            break
            if not self._group_visible(group, category):
                continue
            for heading_kind, heading_text in pending:
                self.rows.append(Row(heading_kind, heading_text, None, 0, gi))
            pending = ()
            if kind == 'victory':
                self.rows.append(Row('victory', '\n'.join(self._rename(l) for l in group['lines']),
                                     'victory', 0, gi))
                continue
            if kind == 'banner':
                self.rows.append(Row('banner', self._rename(banner_title(group['parent'])), category, 0, gi))
            else:
                self.rows.append(Row('entry', self._rename(group['parent'].strip()), category, 0, gi))
            for child in group['children']:
                indent = (len(child) - len(child.lstrip(' '))) // 2
                self.rows.append(Row('entry', self._rename(child.strip()), category,
                                     max(1, min(3, indent)), gi))
        self._state_after_last = (turn_count, pending)
        return first_changed_row


# Display names for the filter chips (P6) and legends
CATEGORY_LABELS = {
    'battle': 'Battles', 'conquest': 'Conquest', 'economy': 'Economy', 'construction': 'Buildings',
    'training': 'Training', 'research': 'Research', 'hero': 'Heroes', 'orders': 'Orders',
    'victory': 'Victory', 'error': 'Warnings', 'other': 'Other',
}
