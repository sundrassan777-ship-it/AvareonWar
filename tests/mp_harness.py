# -*- coding: utf-8 -*-
"""
In-process multiplayer harness (pre-launch multiplayer audit, Phase 1).

Runs 2-4 real Game instances in ONE process and wires them through the REAL network
classes with fake sockets, so tests can reproduce host <-> client sync bugs
deterministically - no threads, no ports, no timing luck.

What is real:
  - NetworkServer._handle_received_message(): validation, sequence check, relay to
    the other clients, forwarding to the host's message queue.
  - NetworkServer._send_to_clients() / NetworkClient._send_to_server(): how the two
    network threads drain their outgoing queues.
  - NetworkClient._handle_received_message(): PING answered at once with PONG,
    everything else queued for the game loop.
  - NetworkProtocol encoding/decoding and sequence numbers.
  - Game._handle_network_message(), _send_action_to_remote() and every game method
    they reach, plus the real click / key handlers the helpers below drive.

What is simulated:
  - Sockets: _FrameSocket.sendall() decodes the frame and hands it straight to the
    other side, so a "send" is delivered immediately and in order.
  - Network threads: Network.flush() runs the drain functions those threads run.
  - The game loop: Peer.step() runs only the multiplayer-relevant part of Game.run()
    (network messages, army animations, the simultaneous-mode "animations finished"
    hand-off, Game._update_simultaneous() / Game._update_sequential_turn() - the SAME
    methods Game.run() calls for timers, AI turns and resolvers, AFK rules, new rounds
    and the final state - and turn announcements with their real duration). Main-loop
    code is never copied here - that would test the copy, not the game; anything a test
    needs is extracted into a method Game.run() calls.
  - The AI's worker threads are real: a test that lets the AI play steps the session
    with tiny real sleeps (and usually patches AIPlayer._pace to a no-op).

Usage:
    session = Session(num_players=2)                 # host 0 + client 1, sequential
    host, client = session.game(0), session.game(1)
    ... arrange identical state on every peer with session.on_all(fn) ...
    click_end_turn(client)
    session.run_until_quiet()
"""

import copy
import gc
import os
import sys
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402
import pytest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data  # noqa: E402
from network.client import NetworkClient  # noqa: E402
from network.server import ClientConnection, NetworkServer  # noqa: E402

# Simulated seconds per Peer.step(). Small enough that network delivery (instant here)
# always happens well inside one army animation (0.5 s) or turn announcement.
STEP_SECONDS = 0.1
# Real TurnAnnouncementEffect runs ~1.5 s before calling _complete_turn_announcement();
# keeping that duration preserves the real ordering of "sync arrives" vs "turn starts".
ANNOUNCEMENT_SECONDS = 1.5
# Fixed seed so neutral armies etc. are identical unless a test wants otherwise
FIXED_GAME_SEED = 12345


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------

class _FrameSocket:
    """Socket stand-in: every sendall() carries exactly one encoded frame, which is
    delivered immediately to the callback (the receiving side's handler)."""

    def __init__(self, deliver):
        self._deliver = deliver
        self.frames = []          # every frame sent through this socket, in order
        self.closed = False

    def sendall(self, data):
        if self.closed:
            raise OSError("harness socket closed")
        frame = bytes(data)
        self.frames.append(frame)
        self._deliver(frame)

    def close(self):
        self.closed = True

    def getpeername(self):
        return ('127.0.0.1', 0)

    # Delivery is push-based, so nothing ever reads from these sockets
    def recv(self, _size):
        raise BlockingIOError()

    def setblocking(self, _flag):
        pass

    def settimeout(self, _timeout):
        pass


class Network:
    """A real NetworkServer (never started) plus real NetworkClients joined to it
    through _FrameSockets. `log` records every frame as (direction, player, type)."""

    def __init__(self):
        self.server = NetworkServer(port=0)
        self.clients = {}         # player_index -> NetworkClient
        self.log = []             # ('c2s' | 's2c', player_index, message type)

    def add_client(self, player_index, name=None):
        """Join a client the way a finished CONNECT handshake would leave it."""
        name = name or f"P{player_index + 1}"
        client = NetworkClient()
        connection = ClientConnection(
            socket=_FrameSocket(lambda frame, i=player_index: self._to_client(i, frame)),
            address=('127.0.0.1', 50000 + player_index),
            player_index=player_index,
            player_name=name,
            password_hash='harness',
            last_pong_time=time.monotonic(),
        )
        with self.server._clients_lock:
            self.server.clients[player_index] = connection
        client.socket = _FrameSocket(lambda frame, i=player_index: self._to_server(i, frame))
        client.player_index = player_index
        client.player_name = name
        with client._state_lock:
            client.connected = True
        client.running = True
        client.message_queue.set_connected(True)
        self.server.message_queue.set_connected(True)
        self.clients[player_index] = client
        return client

    # --- delivery -----------------------------------------------------------

    def _to_server(self, player_index, frame):
        message = self.server.protocol.decode_message(frame)
        self.log.append(('c2s', player_index, message.get('type') if message else None))
        if message:
            self.server._handle_received_message(message, player_index, frame)

    def _to_client(self, player_index, frame):
        client = self.clients.get(player_index)
        if client is None:
            return
        message = client.protocol.decode_message(frame)
        self.log.append(('s2c', player_index, message.get('type') if message else None))
        # Same gate as NetworkClient._receive_from_server()
        if message and client.protocol.validate_message(message):
            client._handle_received_message(message)

    # --- the two network threads ---------------------------------------------

    def flush(self):
        """Drain every outgoing queue, exactly as the network threads would."""
        for _ in range(200):
            busy = False
            for client in list(self.clients.values()):
                if client.message_queue.has_outgoing_messages():
                    busy = True
                    client._send_to_server()
            if self.server.message_queue.has_outgoing_messages():
                busy = True
                self.server._send_to_clients()
            if not busy:
                return
        raise AssertionError("harness network never went quiet")

    def types_sent_by_host(self):
        """Message types the host broadcast, in order (one entry per frame, first client)."""
        first = min(self.clients) if self.clients else None
        return [t for d, i, t in self.log if d == 's2c' and i == first]


# ---------------------------------------------------------------------------
# Game configuration through the real lobby -> config path
# ---------------------------------------------------------------------------

def spread_territories(count):
    """`count` starting territories far apart in the sorted territory list."""
    territories = sorted(map_data.get_all_territories())
    step = max(1, len(territories) // count)
    return [territories[i * step] for i in range(count)]


def build_config(num_players=2, ai_slots=(), turn_mode='sequential', teams=None,
                 territories=None, neutral_armies=False, game_seed=FIXED_GAME_SEED):
    """Setup config built by the real MultiplayerSetup._build_config_from_lobby()."""
    from network.lobby import LobbyState, SLOT_AI, SLOT_HUMAN
    from network.multiplayer_setup import MultiplayerSetup

    territories = territories or spread_territories(num_players)
    lobby = LobbyState(host_name="P1")
    for i in range(num_players):
        slot = lobby.slots[i]
        if i > 0:
            slot.state = SLOT_AI if i in ai_slots else SLOT_HUMAN
            slot.player_name = f"P{i + 1}"
        slot.territory = territories[i]
        if teams is not None:
            slot.team = teams[i]
    lobby.neutral_armies = neutral_armies

    setup = MultiplayerSetup.__new__(MultiplayerSetup)
    return setup._build_config_from_lobby(
        lobby, 0, 0, 1 if turn_mode == 'simultaneous' else 0, neutral_armies,
        map_id='avareon', game_seed=game_seed)


# ---------------------------------------------------------------------------
# Peers and session
# ---------------------------------------------------------------------------

class Peer:
    """One player's Game plus the per-frame driver for it."""

    def __init__(self, game, index):
        self.game = game
        self.index = index
        self._announcement_elapsed = None

    @property
    def gs(self):
        return self.game.game_state

    def step(self, dt=STEP_SECONDS):
        """The multiplayer-relevant part of one Game.run() frame (see module doc)."""
        game = self.game
        gs = game.game_state
        game._process_network_messages()
        gs.update_animations(dt)
        sim = game.sim_state
        # Same hand-off as Game.run(): executing + no animations left -> arrivals
        if (sim is not None and sim.sim_phase == 'executing'
                and not gs.active_animations
                and sim.phase_manager is not None
                and not sim.phase_manager.animations_complete):
            sim.phase_manager.on_animations_complete()
        # Game.run()'s simultaneous-mode frame work - the SAME method: deferred
        # execution start, planning timers, ready-state broadcast, AI resolvers /
        # choosers, AFK rules, new-round AI planning
        if sim is not None:
            game._update_simultaneous(dt)
        else:
            # ...and its sequential-mode work, also the same method: the planning timer
            # (turn owner only), the AFK rules for battles, the final state at game end
            game._update_sequential_turn(dt)
        # Turn announcement: Game.run() starts a TurnAnnouncementEffect whose
        # on_complete is _complete_turn_announcement(); keep its real duration
        if gs.turn_announcement_active:
            if self._announcement_elapsed is None:
                self._announcement_elapsed = 0.0
            self._announcement_elapsed += dt
            if self._announcement_elapsed >= ANNOUNCEMENT_SECONDS:
                self._announcement_elapsed = None
                gs._complete_turn_announcement()
        else:
            self._announcement_elapsed = None

    def busy(self):
        game = self.game
        gs = game.game_state
        queue = game.network_connection.message_queue
        return bool(gs.active_animations or gs.turn_announcement_active
                    or queue.has_incoming_messages()
                    or getattr(game, '_held_network_messages', None))


class Session:
    """Host (player 0) + one client per human seat, all running real Game objects."""

    def __init__(self, num_players=2, ai_slots=(), turn_mode='sequential', teams=None,
                 territories=None, neutral_armies=False, config=None):
        pygame.init()
        map_data.load_polygons()
        self.net = Network()
        self.config = config or build_config(num_players, ai_slots, turn_mode, teams,
                                             territories, neutral_armies)
        self.peers = {}
        self.peers[0] = Peer(make_game(self.net.server, 0, self.config), 0)
        for index in range(1, num_players):
            if index in ai_slots:
                continue
            client = self.net.add_client(index)
            self.peers[index] = Peer(make_game(client, index, self.config), index)
        # Every Game() recreates the display; point them all at the live surface
        surface = pygame.display.get_surface()
        for peer in self.peers.values():
            peer.game.screen = surface

    def game(self, index):
        return self.peers[index].game

    def gs(self, index):
        return self.peers[index].game.game_state

    def on_all(self, fn):
        """Apply the same arrangement to every peer (= a state they agree on)."""
        for peer in self.peers.values():
            fn(peer.game.game_state)

    def flush(self):
        self.net.flush()

    def step_all(self, dt=STEP_SECONDS):
        self.net.flush()
        for peer in self.peers.values():
            peer.step(dt)

    def run_until_quiet(self, max_steps=600):
        """Step every peer until no messages, animations or announcements remain."""
        quiet = 0
        for _ in range(max_steps):
            self.step_all()
            self.net.flush()
            if any(peer.busy() for peer in self.peers.values()):
                quiet = 0
            else:
                quiet += 1
                if quiet >= 3:
                    return
        raise AssertionError("session never went quiet")

    def step_until(self, condition, max_steps=200):
        """Step every peer until condition() is true (fails loudly if it never is)."""
        for _ in range(max_steps):
            if condition():
                return
            self.step_all()
        raise AssertionError("condition never became true")

    def close(self):
        """Free the Games. Each one holds ~400 MB of map art, and a failing test's
        traceback can keep its locals alive, so the fixture empties them explicitly."""
        for peer in self.peers.values():
            peer.game.__dict__.clear()
        self.peers.clear()
        gc.collect()


@pytest.fixture
def make_session():
    """Factory fixture: make_session(**Session kwargs); every session is closed after
    the test, pass or fail. Import it into a test module to use it."""
    sessions = []

    def factory(**kwargs):
        session = Session(**kwargs)
        sessions.append(session)
        return session

    yield factory
    for session in sessions:
        session.close()


def make_game(connection, local_index, config):
    """A real Game for one seat, initialised the way main.py's multiplayer flow does."""
    from main import Game
    game = Game(network_connection=connection)
    game.local_player_index = local_index
    game.initialize_game(copy.deepcopy(config))
    return game


# ---------------------------------------------------------------------------
# State arrangement helpers (apply through Session.on_all to keep peers in step)
# ---------------------------------------------------------------------------

def units(*types, status='ready', level=0, xp=0):
    """Unit dicts with ids 0..n-1."""
    return [{'id': i, 'status': status, 'order': None, 'type': t, 'xp': xp, 'level': level}
            for i, t in enumerate(types)]


def place(gs, territory, owner, unit_list=None, buildings=None):
    """Make `owner` own `territory` with exactly these units/buildings."""
    gs.territory_owners[territory] = owner
    gs._territory_owners_version += 1
    gs.invalidate_territorial_bonus_cache()
    gs.territory_garrisons[territory] = {}
    if unit_list:
        ready = sum(1 for u in unit_list if u['status'] == 'ready')
        gs.set_garrison_armies(territory, owner, unmoved=ready,
                               moved=len(unit_list) - ready,
                               units=copy.deepcopy(unit_list))
    else:
        gs.sync_legacy_garrison_data(territory)
    if buildings is not None:
        if buildings:
            gs.buildings[territory] = dict(buildings)
        else:
            gs.buildings.pop(territory, None)


def adjacent_triple(avoid=None):
    """(A, B, C): B and C both border A; none of them is a starting territory (so an
    arrangement never strips a player of their capital), sorted for determinism."""
    avoid = set(avoid) if avoid is not None else set(spread_territories(4))
    for territory in sorted(map_data.get_all_territories()):
        if territory in avoid:
            continue
        neighbors = sorted(n for n in map_data.get_neighbors(territory) if n not in avoid)
        if len(neighbors) >= 2:
            return territory, neighbors[0], neighbors[1]
    raise AssertionError("map has no territory with two free neighbours")


def far_from(territory, avoid=None):
    """A territory that does NOT border `territory` (and is not a starting territory)."""
    avoid = set(avoid) if avoid is not None else set(spread_territories(4))
    neighbors = set(map_data.get_neighbors(territory))
    for candidate in sorted(map_data.get_all_territories()):
        if candidate != territory and candidate not in neighbors and candidate not in avoid:
            return candidate
    raise AssertionError("no distant territory found")


def set_turn(session, player):
    """Start `player`'s sequential planning phase on every peer (no announcement)."""
    def apply(gs):
        gs.current_player = player
        gs.turn_phase = 'planning'
        gs.turn_announcement_active = False
        gs.planning_phase_start_time = time.time()
    session.on_all(apply)


def battle_at(territory, owner, attacker, resolver=None, defenders=1, attackers=3):
    """A pending Battle: `owner`'s Archers defend, `attacker`'s Cavalry attack."""
    from game_state import Battle
    battle = Battle(territory)
    battle.original_owner = owner
    battle.add_army(owner, defenders, {'Archer': defenders})
    battle.add_army(attacker, attackers, {'Cavalry': attackers})
    battle.resolver = attacker if resolver is None else resolver
    battle.team_members_map = {owner: [owner], attacker: [attacker]}
    battle.attackers = [attacker]
    battle.is_multi_way = False
    return battle


def hero_with_ability(ability_name):
    """(hero_type, ability_index) of the first hero that has this active ability."""
    from game_state.data_definitions import HERO_TYPES
    for hero, info in HERO_TYPES.items():
        for index, ability in enumerate(info.get('abilities', [])):
            if ability.get('name') == ability_name:
                return hero, index
    raise AssertionError(f"no hero has {ability_name}")


def garrison_summary(gs, territory):
    """{player: sorted unit types} for one territory - compares peers' armies."""
    return {player: sorted(u.get('type') for u in data.get('units', []))
            for player, data in gs.territory_garrisons.get(territory, {}).items()}


# ---------------------------------------------------------------------------
# Input helpers: drive the REAL click / key handlers
# ---------------------------------------------------------------------------

def _bottom_rect(x):
    import main
    return pygame.Rect(x, main.BOTTOM_UI_Y + 4, 6, 6)


def click_end_turn(game):
    """Click End Turn through handle_bottom_ui_click()."""
    rect = _bottom_rect(2)
    game.end_turn_button = rect
    return game.handle_bottom_ui_click(rect.center)


def click_cancel_construction(game, territory, plot_index):
    """Select the plot and click its Cancel button."""
    rect = _bottom_rect(40)
    game.selected_plot = (territory, plot_index)
    game.selected_barracks = None
    game.selected_keep = None
    game.building_buttons = {}
    game.cancel_button = rect
    return game.handle_bottom_ui_click(rect.center)


def send_chat(game, text, channel='all'):
    """Type a chat line and press Enter (keyboard handler path)."""
    game.chat_input_active = True
    game.chat_input_text = text
    game.chat_channel = channel
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode='\r', mod=0)
    return game.handle_keyboard_input(event)


def cast_targeted_ability(game, hero, ability_index, target):
    """Enter targeting mode and click `target` (PRIORITY 0 of handle_map_area_click)."""
    import main
    gs = game.game_state
    game.ability_targeting_active = True
    game.ability_targeting_hero = hero
    game.ability_targeting_ability_index = ability_index
    game.ability_targeting_ability_name = gs.HERO_TYPES[hero]['abilities'][ability_index]['name']
    original = game.get_territory_at_pos
    game.get_territory_at_pos = lambda _pos: target
    try:
        game.handle_map_area_click((main.WINDOW_WIDTH // 2, main.TOP_PANEL_HEIGHT + 40))
    finally:
        game.get_territory_at_pos = original


def open_battle(game, territory):
    """Click the battle marker of `territory` (handle_battle_marker_click)."""
    battles = game.game_state.pending_battles
    index = next(i for i, b in enumerate(battles) if b.territory == territory)
    game.battle_markers = [pygame.Rect(10 + 30 * i, 200, 20, 20) for i in range(len(battles))]
    assert game.handle_battle_marker_click(game.battle_markers[index].center)


def fight(game):
    """Press FIGHT in the open battle window (the 'resolve' branch)."""
    game.enhanced_battle_ui.handle_click = lambda _pos: 'resolve'
    return game.handle_battle_popup_click((0, 0))


def close_battle(game):
    """Press Close on the battle report (the 'close' branch)."""
    game.enhanced_battle_ui.handle_click = lambda _pos: 'close'
    return game.handle_battle_popup_click((0, 0))
