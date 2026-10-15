# -*- coding: utf-8 -*-
"""
"Randomize Starting Positions" (setup screens' map top bar) - the start-position logic:

- map_data.pick_starting_territories(): distinct territories, at least
  RANDOM_START_MIN_TERRITORIES_BETWEEN territories between any two (= 5 moves apart),
  never a Fortress, on every enabled map with 2-4 players; the gap relaxes only when it
  cannot fit; never more picks than candidates
- SetupConfig.randomize_starting_territories() (Custom Game): clears every slot, fills
  only the active ones
- LobbyState.assign_starting_territories() (multiplayer host): the claim records follow
  the new picks, so a later client claim is judged against them
"""

import os
import random
import sys
import time
from collections import deque

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_data  # noqa: E402
from config.constants import RANDOM_START_MIN_TERRITORIES_BETWEEN  # noqa: E402


@pytest.fixture(autouse=True)
def restore_map():
    """Every test leaves Avareon loaded with no territory filter (other tests expect it)."""
    yield
    map_data.clear_enabled_territories()
    map_data.load_map('avareon')


def _moves_between(a, b):
    """Shortest number of moves from a to b over the map's adjacency (independent BFS)."""
    seen = {a: 0}
    queue = deque([a])
    while queue:
        territory = queue.popleft()
        if territory == b:
            return seen[territory]
        for neighbor in map_data.ADJACENCIES.get(territory, []):
            if neighbor not in seen:
                seen[neighbor] = seen[territory] + 1
                queue.append(neighbor)
    return float('inf')


@pytest.fixture
def fake_map(monkeypatch):
    """Install a tiny map: {name: [neighbors]} plus optional fortresses."""
    def install(adjacency, fortresses=()):
        monkeypatch.setattr(map_data, 'TERRITORY_POLYGONS',
                            {t: [(0, 0), (1, 0), (0, 1)] for t in adjacency})
        monkeypatch.setattr(map_data, 'ADJACENCIES', {t: list(n) for t, n in adjacency.items()})
        monkeypatch.setattr(map_data, 'FORTRESS_TERRITORIES', set(fortresses))
    return install


def _line(n):
    """A-B-C-... in a row: n territories, each next to the one before and after."""
    names = [chr(ord('A') + i) for i in range(n)]
    return {name: [names[j] for j in (i - 1, i + 1) if 0 <= j < n] for i, name in enumerate(names)}


# ---------------------------------------------------------------- the real maps


@pytest.mark.parametrize("map_id", map_data.get_map_ids())
@pytest.mark.parametrize("players", [2, 3, 4])
def test_starts_spread_on_every_map(map_id, players):
    """Distinct, no Fortress, at least 4 territories between any two - every seed."""
    map_data.load_map(map_id)
    fortresses = map_data.get_fortress_territories()
    need = RANDOM_START_MIN_TERRITORIES_BETWEEN + 1
    for seed in range(40):
        picks = map_data.pick_starting_territories(players, rng=random.Random(seed))
        assert len(picks) == players
        assert len(set(picks)) == players
        assert not set(picks) & fortresses, (map_id, seed, picks)
        for i, a in enumerate(picks):
            assert a in map_data.TERRITORY_POLYGONS
            for b in picks[i + 1:]:
                assert _moves_between(a, b) >= need, (map_id, seed, a, b)


def test_gap_means_territories_between():
    """The default gap is 4 territories BETWEEN two starts, i.e. 5 moves apart."""
    assert RANDOM_START_MIN_TERRITORIES_BETWEEN == 4


def test_pressing_again_draws_anew():
    map_data.load_map('avareon')
    draws = {tuple(map_data.pick_starting_territories(4, rng=random.Random(seed))) for seed in range(10)}
    assert len(draws) > 1


# ---------------------------------------------------------------- small / odd maps


def test_gap_relaxes_only_as_far_as_needed(fake_map):
    """A line of 5: two starts can be at most 3 territories apart (A and E), so the gap
    of 4 relaxes to 3 - not further - and the picks are the two ends."""
    fake_map(_line(5))
    for seed in range(20):
        picks = map_data.pick_starting_territories(2, rng=random.Random(seed))
        assert set(picks) == {'A', 'E'}


def test_tiny_map_still_gives_everyone_a_territory(fake_map):
    fake_map(_line(4))
    for seed in range(20):
        picks = map_data.pick_starting_territories(4, rng=random.Random(seed))
        assert sorted(picks) == ['A', 'B', 'C', 'D']


def test_never_more_picks_than_candidates(fake_map):
    fake_map(_line(3), fortresses={'B'})
    picks = map_data.pick_starting_territories(4, rng=random.Random(0))
    assert sorted(picks) == ['A', 'C']
    assert map_data.pick_starting_territories(0) == []


def test_routes_through_fortresses_count(fake_map):
    """A Fortress is never a start, but armies march through it: the distance counts it."""
    fake_map(_line(7), fortresses={'C', 'D', 'E'})
    # Candidates A, B, F, G; A-F and A-G and B-G have >= 4 territories between
    for seed in range(20):
        picks = map_data.pick_starting_territories(2, rng=random.Random(seed))
        assert set(picks) in ({'A', 'F'}, {'A', 'G'}, {'B', 'G'})


def test_unconnected_territories_count_as_far(fake_map):
    fake_map({'A': ['B'], 'B': ['A'], 'Island': []})
    for seed in range(20):
        picks = map_data.pick_starting_territories(2, rng=random.Random(seed))
        assert 'Island' in picks


def test_disabled_territories_are_never_picked():
    map_data.load_map('avareon')
    enabled = list(map_data.TERRITORY_POLYGONS)[:20]
    map_data.set_enabled_territories(enabled)
    for seed in range(20):
        picks = map_data.pick_starting_territories(3, rng=random.Random(seed))
        assert len(picks) == 3 and set(picks) <= set(enabled)


# ---------------------------------------------------------------- Custom Game


def test_custom_game_randomize_fills_only_active_slots():
    from integrated_setup import SetupConfig
    map_data.load_map('avareon')
    config = SetupConfig()
    config.selected_map = 'avareon'
    # Slots 0 + 1 active (default); slot 3 active too, slot 2 inactive with a stale pick
    config.player_slots[3]['active'] = True
    config.player_slots[0]['territory'] = 'Aelatania'
    config.player_slots[2]['territory'] = 'Lunedale'

    assigned = config.randomize_starting_territories(rng=random.Random(3))

    assert set(assigned) == {0, 1, 3}
    assert config.player_slots[2]['territory'] is None
    picks = [config.player_slots[i]['territory'] for i in (0, 1, 3)]
    assert all(picks) and len(set(picks)) == 3
    assert config.is_ready()


def test_custom_game_randomize_again_replaces_every_pick():
    from integrated_setup import SetupConfig
    map_data.load_map('avareon')
    config = SetupConfig()
    first = config.randomize_starting_territories(rng=random.Random(1))
    second = config.randomize_starting_territories(rng=random.Random(2))
    assert first != second
    assert [config.player_slots[i]['territory'] for i in (0, 1)] == [second[0], second[1]]


# ---------------------------------------------------------------- multiplayer lobby


def test_lobby_assign_keeps_claims_consistent():
    from network.lobby import LobbyState, SLOT_HUMAN
    map_data.load_map('avareon')
    lobby = LobbyState(host_name="Host")
    lobby.set_slot_ai(1)
    lobby.slots[2].state = SLOT_HUMAN   # a joined client
    lobby.slots[2].player_name = "Client"
    lobby.claim_territory(0, 'Aelatania', time.time())
    lobby.claim_territory(2, 'Lunedale', time.time())

    picks = map_data.pick_starting_territories(3, rng=random.Random(5))
    lobby.assign_starting_territories(dict(zip([0, 1, 2], picks)))

    assert [lobby.slots[i].territory for i in (0, 1, 2)] == picks
    assert lobby.slots[3].territory == ""
    # The claim records hold exactly the new picks (old ones released)
    assert set(lobby._territory_claims) == set(picks)
    assert {rec.player_index for rec in lobby._territory_claims.values()} == {0, 1, 2}

    # A client's later claim of another player's new start is refused...
    assert lobby.claim_territory(2, picks[0], time.time() + 1) is False
    assert lobby.slots[0].territory == picks[0]
    # ...switching their own start to a free territory still works
    free = next(t for t in map_data.TERRITORY_POLYGONS if t not in picks)
    assert lobby.claim_territory(2, free, time.time() + 1) is True
    assert lobby.slots[2].territory == free and picks[2] not in lobby._territory_claims
    assert lobby.can_launch()
