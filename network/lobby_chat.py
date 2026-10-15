# -*- coding: utf-8 -*-
"""
Multiplayer lobby chat: the conversation in the lobby before a game.

Owner rules (2026-10-15):
- **Separate from the game's chat.** Lines travel as their own message type, LOBBY_CHAT
  (network_config.py), which the game ignores - a line still in flight at launch never
  shows up in game chat. Nothing is carried into the game.
- **Ends with the lobby.** The history lives in the lobby screen (TerritorySelector) and
  is cleared when the lobby ends: the player leaves, the lobby closes, or the game starts.
- Everyone's lines ('all'), or the sender's current lobby team only ('team', TAB). As in
  game, team lines reach every PC and each PC shows them only to the team: the team is
  the sender's lobby team when the line ARRIVED here (taken from this PC's lobby state,
  not from the message), shown to the sender and to players now on that team.
- "System" lines for players joining / leaving (made on each PC from LOBBY_JOIN /
  LOBBY_LEAVE, never sent).

This module is the model only (no pygame): entries, text cleaning, visibility and the
unread count. The lobby (network/territory_selector.py) sends / receives the lines; the
panel (ui/lobby_chat_panel.py) draws them.
"""

import datetime
import unicodedata
from dataclasses import dataclass
from typing import List, Optional

SYSTEM = 'system'                   # Sender of the lobby's own lines (join / leave)
SYSTEM_NAME = "System"
SYSTEM_COLOR = (230, 196, 120)      # GameState.CHAT_SYSTEM_COLOR (same look as in game)
MAX_LENGTH = 100                    # Characters per line (the in-game chat box's limit)
MAX_ENTRIES = 200                   # Oldest lines are dropped past this
CHANNELS = ('all', 'team')


def clean_text(text) -> str:
    """A chat line as it may be shown: text only, no control characters (line breaks,
    tabs, ...), trimmed and at most MAX_LENGTH characters. '' for anything else."""
    if not isinstance(text, str):
        return ''
    text = ''.join(ch for ch in text if unicodedata.category(ch)[0] != 'C')
    return text.strip()[:MAX_LENGTH].strip()


@dataclass
class LobbyChatEntry:
    serial: int                     # Increasing number (unread counting)
    time: str                       # "HH:MM:SS" when it arrived on this PC
    sender: object                  # Slot index, or SYSTEM
    name: str
    color: tuple
    text: str
    channel: str = 'all'
    team: Optional[int] = None      # Team line: the sender's lobby team when it arrived

    @property
    def is_system(self):
        return self.sender == SYSTEM


class LobbyChat:
    """The lobby's chat history on this PC (see module docstring)."""

    def __init__(self):
        self.entries: List[LobbyChatEntry] = []
        self.version = 0            # Bumped on every change (the panel re-lays out then)
        self._serial = 0
        self._seen_serial = 0       # Lines up to this one have been seen (panel open)

    def _append(self, entry):
        self.entries.append(entry)
        if len(self.entries) > MAX_ENTRIES:
            del self.entries[:len(self.entries) - MAX_ENTRIES]
        self.version += 1
        return entry

    def _next(self):
        self._serial += 1
        return self._serial, datetime.datetime.now().strftime("%H:%M:%S")

    def add_player_line(self, sender, name, color, text, channel='all', team=None):
        """A player's line. Returns the entry, or None when nothing is left of the text
        after clean_text() (an empty line is never shown or sent)."""
        text = clean_text(text)
        if not text:
            return None
        if channel not in CHANNELS:
            channel = 'all'
        serial, time = self._next()
        return self._append(LobbyChatEntry(serial, time, sender, name, tuple(color), text, channel,
                                           team if channel == 'team' else None))

    def add_system_line(self, text):
        """A lobby notice ("Anna joined the lobby"), shown to everyone on this PC."""
        serial, time = self._next()
        return self._append(LobbyChatEntry(serial, time, SYSTEM, SYSTEM_NAME, SYSTEM_COLOR,
                                           clean_text(text) or text, 'all', None))

    def clear(self):
        """The lobby ended: nothing of it is kept (owner)."""
        self.entries = []
        self.version += 1
        self._seen_serial = self._serial

    # ------------------------------------------------------------------ reading

    @staticmethod
    def is_visible(entry, viewer, viewer_team):
        """Everyone sees 'all' lines; a team line shows to its sender and to players
        now on the team it was sent to."""
        if entry.channel != 'team':
            return True
        return entry.sender == viewer or (entry.team is not None and entry.team == viewer_team)

    def visible(self, viewer, viewer_team):
        return [e for e in self.entries if self.is_visible(e, viewer, viewer_team)]

    def unread_count(self, viewer, viewer_team):
        """Lines from OTHER players this viewer can see and has not seen yet (the gold
        count on the Chat bookmark). System lines and their own lines do not count."""
        return sum(1 for e in self.entries
                   if e.serial > self._seen_serial and not e.is_system and e.sender != viewer
                   and self.is_visible(e, viewer, viewer_team))

    def mark_seen(self):
        """Everything so far has been seen (the panel is open)."""
        self._seen_serial = self._serial
