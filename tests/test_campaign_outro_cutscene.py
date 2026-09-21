# -*- coding: utf-8 -*-
"""
Regression tests: the post-mission outro cutscene must play on VICTORY only.

Every campaign mission used to return the same 'exit_campaign' sentinel from both
its victory and its defeat branch, so Game.run() returned 'campaign' either way and
main.py played the winner's cinematic to a player who had just lost.

The contract these tests pin down:
  mission.update() -> 'exit_campaign'        on victory  (outro cutscene plays)
                   -> 'exit_campaign_defeat' on defeat   (no cutscene)
  Game.run()       -> 'campaign' / 'campaign_defeat' respectively
  main.py gates every CutscenePlayer outro on game_result == 'campaign'.

These are source-level (AST) checks on purpose: the bug lives in six near-duplicate
mission files, and driving each mission to a real defeat needs a full pygame game.
"""

import ast
import io
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Missions with a defeat path. tutorial_mission (mission 1) has none and is
# checked separately - it may only ever return the victory sentinel.
DEFEAT_MISSIONS = [
    'campaign_mission_2.py',
    'campaign_mission_3.py',
    'campaign_mission_4.py',
    'campaign_mission_5.py',
    'campaign_mission_6.py',
    'campaign_mission_7.py',
]


def _parse(filename):
    with io.open(os.path.join(ROOT, filename), encoding='utf-8') as f:
        return ast.parse(f.read(), filename=filename)


def _all_update_methods(tree):
    """Every class-level update() in the module.

    Mission modules also define helper classes with an update() of their own
    (e.g. CameraAnimation), so callers must pick the one that actually drives the
    victory/defeat sequences rather than the first match.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == 'update':
                    found.append(item)
    return found


def _sequence_exit_returns(update_fn):
    """Map 'victory'/'defeat' -> the sentinel that branch returns.

    Walks update()'s body in order. A call to (_)update_victory_sequence /
    (_)update_defeat_sequence arms the next `if result == 'exit':` block, whose
    return value is the sentinel for that branch.
    """
    found = {}
    pending = None
    for stmt in ast.walk(update_fn):
        for call in ast.walk(stmt):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                name = call.func.attr.lstrip('_')
                if name == 'update_victory_sequence':
                    pending = 'victory'
                elif name == 'update_defeat_sequence':
                    pending = 'defeat'
        if isinstance(stmt, ast.If) and pending:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant):
                    if isinstance(sub.value.value, str):
                        found[pending] = sub.value.value
                        pending = None
                        break
    return found


def _mission_exit_returns(filename):
    """Sentinels returned by the mission's own update(), keyed 'victory'/'defeat'."""
    for update_fn in _all_update_methods(_parse(filename)):
        returns = _sequence_exit_returns(update_fn)
        if returns:
            return returns
    pytest.fail("no update() in %s drives a victory/defeat sequence" % filename)


@pytest.mark.parametrize('filename', DEFEAT_MISSIONS)
def test_defeat_returns_its_own_sentinel(filename):
    """Defeat must NOT reuse the victory sentinel - that is what played the cutscene."""
    returns = _mission_exit_returns(filename)

    assert returns.get('victory') == 'exit_campaign', (
        "%s: victory branch should return 'exit_campaign', got %r"
        % (filename, returns.get('victory'))
    )
    assert returns.get('defeat') == 'exit_campaign_defeat', (
        "%s: defeat branch should return 'exit_campaign_defeat' so main.py skips "
        "the outro cutscene, got %r" % (filename, returns.get('defeat'))
    )


def test_tutorial_mission_has_victory_sentinel_only():
    """Mission 1 has no defeat path; it must still use the victory sentinel."""
    returns = _mission_exit_returns('tutorial_mission.py')

    assert returns.get('victory') == 'exit_campaign'
    assert 'defeat' not in returns


def _game_run(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'Game':
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == 'run':
                    return item
    pytest.fail('Game.run() not found in main.py')


def test_game_run_maps_both_sentinels():
    """Game.run() must translate each mission sentinel to a distinct result."""
    run_fn = _game_run(_parse('main.py'))

    mapping = {}
    for node in ast.walk(run_fn):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == 'tutorial_result'
                and isinstance(test.comparators[0], ast.Constant)):
            continue
        sentinel = test.comparators[0].value
        for sub in node.body:
            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant):
                mapping[sentinel] = sub.value.value

    assert mapping.get('exit_campaign') == 'campaign'
    assert mapping.get('exit_campaign_defeat') == 'campaign_defeat'


def test_outro_cutscenes_are_gated_on_victory_only():
    """Every outro CutscenePlayer in main.py sits behind game_result == 'campaign'."""
    tree = _parse('main.py')

    gates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == 'game_result'
                and isinstance(test.comparators[0], ast.Constant)):
            continue
        constructs_cutscene = any(
            isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            and sub.func.id == 'CutscenePlayer'
            for sub in ast.walk(node)
        )
        if constructs_cutscene:
            gates.append(test.comparators[0].value)

    # Two call sites: a freshly launched mission and a loaded save.
    assert len(gates) == 2, "expected 2 outro cutscene call sites, found %d" % len(gates)
    assert all(g == 'campaign' for g in gates), (
        "an outro cutscene is reachable for a non-victory result: %r" % (gates,)
    )
