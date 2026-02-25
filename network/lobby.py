"""
Lobby state management for 2-4 player multiplayer.

Handles player slots, territory claims, and game launch validation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import hashlib
import time


# Slot state constants
SLOT_EMPTY = "empty"
SLOT_HUMAN = "human"
SLOT_AI = "ai"
SLOT_DISCONNECTED = "disconnected"

# AI difficulty levels
AI_EASY = 0
AI_MEDIUM = 1
AI_HARD = 2

# Player colors (indices match game_state.py color scheme)
PLAYER_COLORS = ["red", "blue", "green", "yellow"]


@dataclass
class LobbySlot:
    """
    Represents a single player slot in the multiplayer lobby.

    Attributes:
        index: Slot index (0-3, where 0 is always host)
        state: Current slot state (empty/human/ai/disconnected)
        player_name: Display name for human players
        password_hash: Hashed password for reconnection (humans only)
        color: Player color index (0-3)
        team: Team index (0-3)
        ai_difficulty: AI difficulty level (0-2, only used when state='ai')
        territory: Selected starting territory name (empty string = not selected)
        is_host: Whether this slot is the host (only slot 0)
    """
    index: int
    state: str = SLOT_EMPTY
    player_name: str = ""
    password_hash: str = ""
    color: int = 0
    team: int = 0
    ai_difficulty: int = AI_MEDIUM
    territory: str = ""
    is_host: bool = False

    def is_active(self) -> bool:
        """Check if this slot is occupied (human or AI)."""
        return self.state in (SLOT_HUMAN, SLOT_AI, SLOT_DISCONNECTED)

    def is_human(self) -> bool:
        """Check if this slot is controlled by a human player."""
        return self.state == SLOT_HUMAN

    def is_ai(self) -> bool:
        """Check if this slot is AI-controlled."""
        return self.state == SLOT_AI

    def is_ready(self) -> bool:
        """Check if this slot is ready to launch (has territory selected)."""
        if not self.is_active():
            return True  # Empty slots are always "ready"
        return len(self.territory) > 0

    def set_password(self, plain_password: str) -> None:
        """Hash and store a password for reconnection."""
        self.password_hash = hashlib.sha256(plain_password.encode()).hexdigest()

    def verify_password(self, plain_password: str) -> bool:
        """Verify a password against stored hash."""
        if not self.password_hash:
            return False
        return hashlib.sha256(plain_password.encode()).hexdigest() == self.password_hash

    def to_dict(self) -> Dict[str, Any]:
        """Serialize slot to dict for network transmission."""
        return {
            "index": self.index,
            "state": self.state,
            "player_name": self.player_name,
            "color": self.color,
            "team": self.team,
            "ai_difficulty": self.ai_difficulty,
            "territory": self.territory,
            "is_host": self.is_host
            # Note: password_hash is never sent over network
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LobbySlot":
        """Deserialize slot from dict."""
        return cls(
            index=data.get("index", 0),
            state=data.get("state", SLOT_EMPTY),
            player_name=data.get("player_name", ""),
            password_hash="",  # Never received from network
            color=data.get("color", 0),
            team=data.get("team", 0),
            ai_difficulty=data.get("ai_difficulty", AI_MEDIUM),
            territory=data.get("territory", ""),
            is_host=data.get("is_host", False)
        )


@dataclass
class TerritoryClaimRecord:
    """Records a territory claim with timestamp for conflict resolution."""
    player_index: int
    territory: str
    timestamp: float = field(default_factory=time.time)


class LobbyState:
    """
    Manages the complete lobby state for host.

    Handles slot management, territory claims, and launch validation.
    Used by host to coordinate lobby; clients receive serialized copies.
    """

    MAX_PLAYERS = 4
    MIN_HUMANS = 1  # At least 1 human required

    def __init__(self, host_name: str = "Host"):
        """Initialize lobby with host in slot 0."""
        self.slots: List[LobbySlot] = []
        self._territory_claims: Dict[str, TerritoryClaimRecord] = {}  # territory -> claim record
        self._pending_claims: List[TerritoryClaimRecord] = []  # For conflict resolution

        # Game settings (host-controlled)
        self.victory_condition: int = 0  # 0=Domination, 1=Capital Assault, 2=Total Conquest
        self.taxation_level: int = 0     # 0-4 (0%/25%/50%/75%/100%)
        self.turn_mode: int = 0          # 0=Sequential, 1=Simultaneous

        # Initialize all 4 slots
        for i in range(self.MAX_PLAYERS):
            slot = LobbySlot(
                index=i,
                state=SLOT_HUMAN if i == 0 else SLOT_EMPTY,
                player_name=host_name if i == 0 else "",
                color=i,  # Default colors: 0=red, 1=blue, 2=green, 3=yellow
                team=i,   # Default: each on own team
                is_host=(i == 0)
            )
            self.slots.append(slot)

    def get_slot(self, index: int) -> Optional[LobbySlot]:
        """Get slot by index (0-3)."""
        if 0 <= index < len(self.slots):
            return self.slots[index]
        return None

    def find_empty_slot(self) -> Optional[int]:
        """Find first empty slot index, or None if full."""
        for slot in self.slots:
            if slot.state == SLOT_EMPTY:
                return slot.index
        return None

    def add_player(self, player_name: str, password_hash: str = "") -> Optional[int]:
        """
        Add a human player to first empty slot.

        Returns:
            Assigned slot index, or None if lobby is full
        """
        slot_idx = self.find_empty_slot()
        if slot_idx is None:
            return None

        slot = self.slots[slot_idx]
        slot.state = SLOT_HUMAN
        slot.player_name = player_name
        slot.password_hash = password_hash
        return slot_idx

    def remove_player(self, index: int) -> bool:
        """
        Remove a player from slot (reset to empty).

        Returns:
            True if player was removed, False if slot was already empty
        """
        slot = self.get_slot(index)
        if slot is None or slot.state == SLOT_EMPTY:
            return False
        if slot.is_host:
            return False  # Cannot remove host

        # Clear territory claim if any
        if slot.territory:
            self._release_territory(slot.territory)

        # Reset slot to empty
        slot.state = SLOT_EMPTY
        slot.player_name = ""
        slot.password_hash = ""
        slot.territory = ""
        return True

    def set_slot_ai(self, index: int, difficulty: int = AI_MEDIUM) -> bool:
        """
        Set a slot to AI-controlled.

        Args:
            index: Slot index (cannot be 0/host)
            difficulty: AI difficulty (0-2)

        Returns:
            True if successful
        """
        slot = self.get_slot(index)
        if slot is None or slot.is_host:
            return False

        # Clear territory claim if switching from human
        if slot.territory:
            self._release_territory(slot.territory)

        slot.state = SLOT_AI
        slot.player_name = f"AI ({['Easy', 'Medium', 'Hard'][difficulty]})"
        slot.password_hash = ""
        slot.ai_difficulty = difficulty
        slot.territory = ""
        return True

    def set_slot_empty(self, index: int) -> bool:
        """
        Set a slot to empty.

        Args:
            index: Slot index (cannot be 0/host)

        Returns:
            True if successful
        """
        return self.remove_player(index)

    def mark_disconnected(self, index: int) -> bool:
        """
        Mark a human player as disconnected (AI takes over).

        Args:
            index: Slot index of disconnected player

        Returns:
            True if successful
        """
        slot = self.get_slot(index)
        if slot is None or slot.state != SLOT_HUMAN:
            return False

        slot.state = SLOT_DISCONNECTED
        return True

    def restore_player(self, index: int) -> bool:
        """
        Restore a disconnected player to human control.

        Args:
            index: Slot index of reconnecting player

        Returns:
            True if successful
        """
        slot = self.get_slot(index)
        if slot is None or slot.state != SLOT_DISCONNECTED:
            return False

        slot.state = SLOT_HUMAN
        return True

    def find_disconnected_slot(self, player_name: str) -> Optional[LobbySlot]:
        """Find a disconnected slot by player name for reconnection."""
        for slot in self.slots:
            if slot.state == SLOT_DISCONNECTED and slot.player_name == player_name:
                return slot
        return None

    def claim_territory(self, player_index: int, territory: str,
                        timestamp: float = None) -> bool:
        """
        Attempt to claim a territory for a player.

        Uses first-come-first-served with timestamp tiebreaker.

        Args:
            player_index: Slot index claiming territory
            territory: Territory name to claim
            timestamp: Claim timestamp (defaults to current time)

        Returns:
            True if claim successful, False if territory taken
        """
        if timestamp is None:
            timestamp = time.time()

        slot = self.get_slot(player_index)
        if slot is None or not slot.is_active():
            return False

        # Check if territory already claimed by someone else
        if territory in self._territory_claims:
            existing = self._territory_claims[territory]
            if existing.player_index != player_index:
                # Territory taken by someone else - compare timestamps
                if existing.timestamp <= timestamp:
                    return False  # Existing claim wins
                # New claim is earlier - swap territories
                self._swap_territory_claim(existing.player_index, player_index, territory)
                return True

        # Release player's previous territory if any
        if slot.territory and slot.territory != territory:
            self._release_territory(slot.territory)

        # Claim the new territory
        slot.territory = territory
        self._territory_claims[territory] = TerritoryClaimRecord(
            player_index=player_index,
            territory=territory,
            timestamp=timestamp
        )
        return True

    def _release_territory(self, territory: str) -> None:
        """Release a territory claim."""
        if territory in self._territory_claims:
            del self._territory_claims[territory]

    def _swap_territory_claim(self, loser_index: int, winner_index: int,
                               territory: str) -> None:
        """Handle territory claim conflict by swapping."""
        # Loser loses their claim
        loser_slot = self.get_slot(loser_index)
        if loser_slot:
            loser_slot.territory = ""

        # Winner gets the territory
        winner_slot = self.get_slot(winner_index)
        if winner_slot:
            # Release winner's old territory first
            if winner_slot.territory:
                self._release_territory(winner_slot.territory)
            winner_slot.territory = territory

        # Update claim record
        self._territory_claims[territory] = TerritoryClaimRecord(
            player_index=winner_index,
            territory=territory,
            timestamp=time.time()
        )

    def set_player_color(self, player_index: int, color: int) -> bool:
        """
        Set a player's color.

        Enforces unique colors - swaps with existing holder if needed.

        Args:
            player_index: Slot index
            color: Color index (0-3)

        Returns:
            True if successful
        """
        slot = self.get_slot(player_index)
        if slot is None or color < 0 or color > 3:
            return False

        # Find who currently has this color
        for other in self.slots:
            if other.index != player_index and other.color == color:
                # Swap colors
                other.color = slot.color
                break

        slot.color = color
        return True

    def set_player_team(self, player_index: int, team: int) -> bool:
        """
        Set a player's team.

        Args:
            player_index: Slot index
            team: Team index (0-3)

        Returns:
            True if successful
        """
        slot = self.get_slot(player_index)
        if slot is None or team < 0 or team > 3:
            return False

        slot.team = team
        return True

    def get_active_players(self) -> List[LobbySlot]:
        """Get list of active (non-empty) slots."""
        return [s for s in self.slots if s.is_active()]

    def get_human_players(self) -> List[LobbySlot]:
        """Get list of human-controlled slots (including disconnected)."""
        return [s for s in self.slots if s.state in (SLOT_HUMAN, SLOT_DISCONNECTED)]

    def get_active_count(self) -> int:
        """Get count of active players."""
        return len(self.get_active_players())

    def get_human_count(self) -> int:
        """Get count of human players (including disconnected)."""
        return len(self.get_human_players())

    def are_allies(self, player1: int, player2: int) -> bool:
        """Check if two players are on the same team."""
        slot1 = self.get_slot(player1)
        slot2 = self.get_slot(player2)
        if slot1 is None or slot2 is None:
            return False
        return slot1.team == slot2.team and slot1.is_active() and slot2.is_active()

    def can_launch(self) -> bool:
        """
        Check if game can be launched.

        Requirements:
        - At least 2 active players
        - At least 1 human player
        - All active players have territories selected
        """
        active = self.get_active_players()
        if len(active) < 2:
            return False

        humans = [s for s in active if s.state in (SLOT_HUMAN, SLOT_DISCONNECTED)]
        if len(humans) < self.MIN_HUMANS:
            return False

        # All active players must have territories
        for slot in active:
            if not slot.territory:
                return False

        return True

    def get_settings(self) -> Dict[str, int]:
        """Get game settings dict."""
        return {
            "victory_condition": self.victory_condition,
            "taxation_level": self.taxation_level,
            "turn_mode": self.turn_mode
        }

    def set_settings(self, settings: Dict[str, int]) -> None:
        """Update game settings from dict."""
        if "victory_condition" in settings:
            self.victory_condition = settings["victory_condition"]
        if "taxation_level" in settings:
            self.taxation_level = settings["taxation_level"]
        if "turn_mode" in settings:
            self.turn_mode = settings["turn_mode"]

    def serialize(self) -> Dict[str, Any]:
        """Serialize full lobby state for network transmission."""
        return {
            "slots": [slot.to_dict() for slot in self.slots],
            "settings": self.get_settings()
        }

    def update_from_network(self, data: Dict[str, Any]) -> None:
        """
        Update lobby state from network data (client-side).

        Args:
            data: Serialized lobby state from host
        """
        # Update slots
        if "slots" in data:
            for slot_data in data["slots"]:
                idx = slot_data.get("index", -1)
                if 0 <= idx < len(self.slots):
                    # Update slot fields (but preserve local password_hash)
                    slot = self.slots[idx]
                    old_hash = slot.password_hash
                    self.slots[idx] = LobbySlot.from_dict(slot_data)
                    self.slots[idx].password_hash = old_hash

        # Update settings
        if "settings" in data:
            self.set_settings(data["settings"])

    def get_player_territories(self) -> Dict[int, str]:
        """Get mapping of player index -> territory for active players."""
        return {
            slot.index: slot.territory
            for slot in self.slots
            if slot.is_active() and slot.territory
        }

    def get_player_teams(self) -> Dict[int, int]:
        """Get mapping of player index -> team for active players."""
        return {
            slot.index: slot.team
            for slot in self.slots
            if slot.is_active()
        }
