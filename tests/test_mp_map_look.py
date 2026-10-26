# -*- coding: utf-8 -*-
"""
2D and 3D players in one multiplayer game (map_data "Map looks").

Each PC shows its own look - its picture, outlines and plots - and the network only ever
carries territory names, so the game is the same: a lobby claim shows on both looks, a
click picks the same territory on either, and rounds with moves and battles end in
identical state on every PC. Real Game objects over tests/mp_harness.py; each seat's look
is set as if chosen in its own Options.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mp_harness as h  # noqa: E402
from mp_harness import make_session  # noqa: E402,F401  (pytest fixture)
import map_data  # noqa: E402
from network.state_snapshot import build_snapshot  # noqa: E402
from network_config import MessageType  # noqa: E402

MIXES = [{0: '3d', 1: '2d'}, {0: '2d', 1: '3d'}]


def state(gs):
    return json.loads(json.dumps(build_snapshot(gs)))


def assert_identical(session):
    reference = state(session.gs(0))
    for index in session.peers:
        assert state(session.gs(index)) == reference, f'peer {index} differs from the host'


def assert_mixed(session, looks):
    """Each PC really shows its own look: different outlines, the same territories."""
    games = {i: session.game(i) for i in session.peers}
    for index, game in games.items():
        assert game.map_look == looks[index]
    a, b = games[0], games[1]
    assert list(a.scaled_polygons) == list(b.scaled_polygons)
    assert any(a.scaled_centers[t] != b.scaled_centers[t] for t in a.scaled_centers)


@pytest.mark.parametrize('looks', MIXES, ids=['host-3d', 'client-3d'])
def test_sequential_battle_is_identical_on_2d_and_3d(make_session, looks):
    session = make_session(num_players=2, looks=looks)
    assert_mixed(session, looks)
    a, b, _ = h.adjacent_triple()
    session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Cavalry', 'Cavalry', 'Cavalry')),
                               h.place(gs, b, 0, h.units('Archer'))))
    h.set_turn(session, 1)
    client = session.game(1)
    assert client.game_state.add_movement_order_for_units(a, b, [0, 1, 2])
    h.click_end_turn(client)
    session.step_until(lambda: any(bt.territory == b for bt in client.game_state.pending_battles))
    h.open_battle(client, b)
    h.fight(client)
    h.close_battle(client)
    session.run_until_quiet()
    assert_identical(session)
    assert session.gs(0).current_player == 0


@pytest.mark.parametrize('looks', MIXES, ids=['host-3d', 'client-3d'])
def test_simultaneous_round_is_identical_on_2d_and_3d(make_session, looks):
    session = make_session(num_players=2, turn_mode='simultaneous', looks=looks)
    assert_mixed(session, looks)
    a, b, _ = h.adjacent_triple()
    x, y, _ = h.adjacent_triple(avoid=set(h.spread_territories(4)) | {a, b})
    session.on_all(lambda gs: (h.place(gs, a, 1, h.units('Swordsman', 'Swordsman', 'Archer')), h.place(gs, b, 1),
                               h.place(gs, x, 0, h.units('Pikeman')), h.place(gs, y, 0)))
    assert session.game(1).game_state.add_movement_order_for_units(a, b, [0, 1])
    assert session.game(0).game_state.add_movement_order_for_units(x, y, [0])
    h.click_end_turn(session.game(1))
    session.step_all()
    h.click_end_turn(session.game(0))
    session.run_until_quiet()
    for index in session.peers:
        assert session.game(index).sim_state.round_number == 2
        assert h.garrison_summary(session.gs(index), b) == {1: ['Swordsman', 'Swordsman']}
        assert h.garrison_summary(session.gs(index), y) == {0: ['Pikeman']}
    owners = [dict(session.gs(i).territory_owners) for i in session.peers]
    assert owners[0] == owners[1]


@pytest.mark.parametrize('looks', MIXES, ids=['host-3d', 'client-3d'])
def test_a_click_picks_the_same_territory_in_either_look(make_session, looks):
    """Each PC hit-tests its own outlines: a plot (inside its territory in both looks)
    picks that territory on the 2D PC and on the 3D PC."""
    session = make_session(num_players=2, looks=looks)
    picked = 0
    for name in list(session.game(0).scaled_plots)[:40]:
        for game in (session.game(0), session.game(1)):
            if not game.scaled_plots.get(name):
                continue
            hit = game.get_territory_at_pos(game.scaled_plots[name][0])
            if hit is not None:
                assert hit == name
                picked += 1
    assert picked > 40


def test_lobby_claims_show_on_both_looks(monkeypatch):
    """Host lobby in 3D, client lobby in 2D: the host's random starts and a client's
    claim arrive as territory names and show on each PC's own map."""
    import pygame
    from network.territory_selector import TerritorySelector
    pygame.init()
    screen = pygame.display.set_mode((1600, 900))
    map_data.load_map('avareon')
    net = h.Network()
    monkeypatch.setattr(map_data, 'map_look', lambda: '3d')
    host = TerritorySelector(screen, net.server, is_host=True, local_player_index=0)
    host_look = map_data.get_current_look()
    client_conn = net.add_client(1, "P2")
    net.server.message_queue.receive_message({
        'type': MessageType.LOBBY_JOIN, 'data': {'player_index': 1, 'player_name': "P2"}})
    host._process_network_messages()
    monkeypatch.setattr(map_data, 'map_look', lambda: '2d')
    client = TerritorySelector(screen, client_conn, is_host=False, local_player_index=1)
    client._process_network_messages()
    assert host_look == '3d' and map_data.get_current_look() == '2d'
    some = next(iter(host.scaled_polygons))
    assert host.scaled_polygons[some] != client.scaled_polygons[some]          # each its own look

    assert host.randomize_starting_positions()
    client._process_network_messages()
    picks = [host.lobby_state.slots[i].territory for i in (0, 1)]
    assert all(picks) and [client.lobby_state.slots[i].territory for i in (0, 1)] == picks
    # Each PC finds the claimed territory on its own map: a click inside it on that PC's
    # outline (its own look) picks it
    for selector in (host, client):
        for territory in picks:
            polygon = selector.scaled_polygons[territory]
            point = _inside(polygon)
            assert selector.get_territory_at_pos(point) == territory


def _inside(polygon):
    """A point inside a polygon: its centroid, or else a point between the centroid and a
    vertex (concave shapes)."""
    cx, cy = map_data.calculate_polygon_centroid(polygon)
    candidates = [(cx, cy)] + [((cx + x) / 2, (cy + y) / 2) for x, y in polygon]
    for point in candidates:
        if map_data.point_in_polygon(point, polygon):
            return point
    raise AssertionError('no inside point found')
