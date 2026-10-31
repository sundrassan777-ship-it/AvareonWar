# -*- coding: utf-8 -*-
"""
Code Quality Fixes Validation Suite
====================================

Comprehensive tests to verify all code quality improvements made to the
AvareonWar codebase. Covers safe changes, network improvements, AI
refactoring, game logic, settings validation, camera/input, and
meta-level quality checks.

Run with: python -m pytest tests/test_code_quality_fixes.py -v
"""

import pytest
import os
import re
import sys
import enum
import logging
import threading
import struct
import json
import time
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ============================================================================
# Helper utilities
# ============================================================================

def get_game_py_files():
    """
    Return all .py files in the game source (excluding tests/, tools/, dist/).

    These are the files that should have passed through code quality fixes.
    """
    game_files = []
    exclude_dirs = {"tests", "tools", "dist", "__pycache__", ".git", "venv", "env"}

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                game_files.append(os.path.join(root, f))
    return game_files


def read_file_contents(filepath):
    """Read a file and return its text content."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


class _ModuleClock:
    """Stands in for one module's `time`: monotonic() reads this test's clock, everything
    else is the real time module. A wall-clock reading (time.time(), ~1.7e9) never matches it."""

    def __init__(self, now=1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


def _game_state():
    from game_state import GameState
    gs = GameState(num_players=2, player_is_ai=[False, False], player_ai_difficulty=[1, 1],
                   skip_setup_phase=True)
    gs.phase = 'playing'
    return gs


def _garrison(gs, territory, player, count):
    """`player` owns `territory` with `count` ready Swordsmen (orderable)."""
    gs.territory_owners[territory] = player
    units = [gs._make_unit('Swordsman', i, status='ready') for i in range(count)]
    gs.add_garrison(territory, player, unmoved=count, moved=0, units=units)
    gs.armies[territory] = count
    gs.armies_unmoved[territory] = count
    gs.armies_moved[territory] = 0
    gs.army_units[territory] = [u.copy() for u in units]


# ============================================================================
# 1. SAFE Changes Tests
# ============================================================================

class TestBareExceptRemoval:
    def test_no_bare_excepts_in_game_files(self):
        bare_except_pattern = re.compile(r'^\s*except\s*:\s*(#.*)?$', re.MULTILINE)
        violations = []
        for filepath in get_game_py_files():
            content = read_file_contents(filepath)
            for i, line in enumerate(content.splitlines(), 1):
                if bare_except_pattern.match(line):
                    rel_path = os.path.relpath(filepath, PROJECT_ROOT)
                    violations.append(f'{rel_path}:{i}: {line.strip()}')
        assert len(violations) == 0, (
            f'Found {len(violations)} bare except clause(s): ' + '; '.join(violations[:10]))


class TestLogging:
    def test_logger_module_importable(self):
        from utils.logger import get_logger, setup_logging
        assert callable(get_logger)
        assert callable(setup_logging)

    def test_get_logger_returns_logger_instance(self):
        from utils.logger import get_logger
        lgr = get_logger('test_module')
        assert isinstance(lgr, logging.Logger)

    def test_get_logger_shortens_dunder_name(self):
        from utils.logger import get_logger
        lgr = get_logger('__main__')
        assert 'main' in lgr.name

    def test_setup_logging_creates_handlers(self):
        from utils.logger import setup_logging
        setup_logging(enable_file=False)
        root = logging.getLogger()
        assert len(root.handlers) > 0

    def test_set_level_changes_console_level(self):
        from utils.logger import set_level
        set_level(logging.DEBUG)
        set_level(logging.WARNING)


class TestIconCaching:
    def test_game_has_cached_scaled_surface_method(self):
        import pygame
        pygame.init()
        from main import Game
        assert hasattr(Game, '_get_cached_scaled_surface')

    def test_game_has_apply_icon_overlay_method(self):
        import pygame
        pygame.init()
        from main import Game
        assert hasattr(Game, '_apply_icon_overlay')

    def test_drawing_helpers_has_button_bg_cache(self):
        import pygame
        pygame.init()
        from rendering.helpers import DrawingHelpers
        screen = pygame.Surface((100, 100))
        font = pygame.font.Font(None, 12)
        helpers = DrawingHelpers(screen, font, font, font)
        assert hasattr(helpers, '_button_bg_cache')
        assert isinstance(helpers._button_bg_cache, dict)


# ============================================================================
# 2. Network Changes Tests
# ============================================================================

class TestMessageTypeEnum:
    def test_message_type_is_enum(self):
        from network_config import MessageType
        assert issubclass(MessageType, enum.Enum)

    def test_message_type_is_str_mixin(self):
        from network_config import MessageType
        assert issubclass(MessageType, str)

    def test_message_type_equals_string(self):
        from network_config import MessageType
        assert MessageType.CONNECT_REQUEST == 'CONNECT_REQUEST'
        assert MessageType.PING == 'PING'
        assert MessageType.DISCONNECT == 'DISCONNECT'

    def test_message_type_from_string(self):
        from network_config import MessageType
        result = MessageType.from_string('CONNECT_ACCEPT')
        assert result is MessageType.CONNECT_ACCEPT

    def test_message_type_from_string_unknown_raises(self):
        from network_config import MessageType
        with pytest.raises(ValueError, match='Unknown MessageType'):
            MessageType.from_string('NONEXISTENT_TYPE')

    def test_error_code_is_enum(self):
        from network_config import ErrorCode
        assert issubclass(ErrorCode, enum.Enum)
        assert issubclass(ErrorCode, str)

    def test_error_code_from_string(self):
        from network_config import ErrorCode
        result = ErrorCode.from_string('VERSION_MISMATCH')
        assert result is ErrorCode.VERSION_MISMATCH

    def test_error_code_from_string_unknown_raises(self):
        from network_config import ErrorCode
        with pytest.raises(ValueError, match='Unknown ErrorCode'):
            ErrorCode.from_string('NOT_A_REAL_CODE')

    def test_message_type_json_serializable(self):
        from network_config import MessageType
        result = json.dumps({'type': MessageType.PING})
        assert '"PING"' in result


class TestNetworkClient:
    def test_client_timeout_runs_on_the_monotonic_clock(self, monkeypatch):
        """A silent host times the client out after CONNECTION_TIMEOUT seconds of the
        monotonic clock, not a second sooner (the wall clock jumps with NTP and DST)."""
        from network import client as client_module
        from network_config import CONNECTION_TIMEOUT
        clock = _ModuleClock()
        monkeypatch.setattr(client_module, 'time', clock)
        client = client_module.NetworkClient()
        client.last_pong_time = clock.now
        clock.now += CONNECTION_TIMEOUT - 1
        client._check_timeout()
        assert not client.disconnected
        clock.now += 2
        client._check_timeout()
        assert client.disconnected
        assert client.disconnect_reason == "Connection timeout"

    def test_client_has_state_lock(self):
        from network.client import NetworkClient
        client = NetworkClient()
        assert hasattr(client, '_state_lock')
        assert isinstance(client._state_lock, type(threading.Lock()))

    def test_client_has_message_handlers_dispatch(self):
        from network.client import NetworkClient
        client = NetworkClient()
        assert hasattr(client, '_message_handlers')
        assert isinstance(client._message_handlers, dict)
        from network_config import MessageType
        assert MessageType.CONNECT_ACCEPT in client._message_handlers
        assert MessageType.CONNECT_REJECT in client._message_handlers
        assert MessageType.DISCONNECT in client._message_handlers


class TestNetworkServer:
    def test_message_queue_has_max_size(self):
        from network.message_queue import NetworkMessageQueue
        assert hasattr(NetworkMessageQueue, 'MAX_QUEUE_SIZE')
        assert isinstance(NetworkMessageQueue.MAX_QUEUE_SIZE, int)
        assert NetworkMessageQueue.MAX_QUEUE_SIZE > 0

    def test_message_queue_enforces_max_size(self):
        from network.message_queue import NetworkMessageQueue
        mq = NetworkMessageQueue()
        assert mq.send_queue.maxsize == NetworkMessageQueue.MAX_QUEUE_SIZE
        assert mq.recv_queue.maxsize == NetworkMessageQueue.MAX_QUEUE_SIZE

    def test_protocol_has_sequence_numbers(self):
        from network.protocol import NetworkProtocol
        protocol = NetworkProtocol()
        msg1 = protocol.encode_message('TEST_MSG', {'key': 'val'})
        decoded1 = protocol.decode_message(msg1)
        assert 'seq' in decoded1, 'Encoded message must include seq field'
        assert decoded1['seq'] == 0, 'First message should have seq=0'
        msg2 = protocol.encode_message('TEST_MSG2', {})
        decoded2 = protocol.decode_message(msg2)
        assert decoded2['seq'] == 1, 'Second message should have seq=1'

    def test_server_timeout_runs_on_the_monotonic_clock(self, monkeypatch):
        """A client that stops answering is dropped after CONNECTION_TIMEOUT seconds of the
        monotonic clock, not a second sooner."""
        from network import server as server_module
        from network_config import CONNECTION_TIMEOUT
        clock = _ModuleClock()
        monkeypatch.setattr(server_module, 'time', clock)
        server = server_module.NetworkServer()
        server.clients[1] = server_module.ClientConnection(
            socket=Mock(), address=('127.0.0.1', 12345), player_index=1,
            last_pong_time=clock.now, connected=True)
        clock.now += CONNECTION_TIMEOUT - 1
        server._check_timeouts()
        assert 1 in server.clients
        clock.now += 2
        server._check_timeouts()
        assert 1 not in server.clients


# ============================================================================
# 3. AI Changes Tests
# ============================================================================

class TestAIPerformance:
    def test_ai_player_has_thread_pool_attribute(self):
        import pygame
        from concurrent.futures import ThreadPoolExecutor
        pygame.init()
        from ai_player import AIPlayer
        ai = AIPlayer(player_index=1, difficulty=0)
        assert isinstance(ai._thread_pool, ThreadPoolExecutor)
        ai.shutdown()

    def test_ai_player_has_animation_event(self):
        import pygame
        pygame.init()
        from ai_player import AIPlayer
        ai = AIPlayer(player_index=1, difficulty=0)
        assert hasattr(ai, '_animation_done')
        assert isinstance(ai._animation_done, threading.Event)
        ai.shutdown()

    def test_attack_planner_searches_each_garrison_once(self, monkeypatch):
        """select_attack_targets() runs the reachability search once per territory with a
        garrison (H5), not again inside its scoring loop."""
        import pygame
        pygame.init()
        import map_data
        from ai_player import AIPlayer
        from ai_military import AttackPlanner
        gs = _game_state()
        home = sorted(map_data.get_all_territories())[:3]
        for territory in home:
            _garrison(gs, territory, 0, 4)
        ai = AIPlayer(player_index=0, difficulty=1)
        planner = AttackPlanner(ai)
        searched = []
        real_search = planner.find_reachable_enemies

        def search(game_state, territory, *args, **kwargs):
            searched.append(territory)
            return real_search(game_state, territory, *args, **kwargs)

        monkeypatch.setattr(planner, 'find_reachable_enemies', search)
        try:
            planner.select_attack_targets(gs)
        finally:
            ai.shutdown()
        garrisoned = [t for t, g in gs.territory_garrisons.items()
                      if 0 in g and g[0].get('unmoved', 0) + g[0].get('moved', 0) > 0]
        assert set(home) <= set(garrisoned)
        assert sorted(searched) == sorted(garrisoned)


class TestAICodeQuality:
    def test_ai_hero_has_ability_scorers_dict(self):
        from ai_hero import AbilityExecutor
        executor = AbilityExecutor()
        assert hasattr(executor, '_ability_scorers')
        assert isinstance(executor._ability_scorers, dict)
        assert 'Aggressive Diplomacy' in executor._ability_scorers
        assert 'Levy' in executor._ability_scorers

    def test_ai_economy_has_generic_score_building(self):
        from ai_economy import BuildingPlanner
        planner = BuildingPlanner()
        assert hasattr(planner, '_score_building')
        assert callable(planner._score_building)

    def test_ai_economy_score_building_is_used_by_public_api(self, monkeypatch):
        from ai_economy import BuildingPlanner
        planner = BuildingPlanner()
        calls = []
        monkeypatch.setattr(planner, '_score_building',
                            lambda *args, **kwargs: calls.append((args, kwargs)) or 42.0)
        game_state = object()
        assert planner.score_building_placement('Conda', 'Farm', game_state, 0) == 42.0
        assert calls == [(('Conda', 'Farm', game_state, 0), {'cache': None})]


# ============================================================================
# 4. Game Logic Tests
# ============================================================================

class TestGameStateRefactor:
    """The order pipeline split out of execute_all_orders (Phase 7: game_state/military.py)."""

    def test_an_order_into_an_enemy_territory_opens_a_battle_there(self):
        import map_data
        gs = _game_state()
        source = sorted(map_data.get_all_territories())[0]
        target = map_data.get_neighbors(source)[0]
        _garrison(gs, source, 0, 5)
        _garrison(gs, target, 1, 3)
        unit_ids = [u['id'] for u in gs.territory_garrisons[source][0]['units']]
        gs.current_player = 0
        assert gs.add_movement_order_for_units(source, target, unit_ids, player=0)
        gs.execute_all_orders()
        # The march (an animation in the game) arrives; _process_arrivals finds the fight
        while gs.active_animations:
            march = gs.active_animations.pop()
            march.completed, march.progress = True, 1.0
            gs.pending_arrivals.append(march)
        gs._process_arrivals()
        assert [battle.territory for battle in gs.pending_battles] == [target]

    def test_unit_composition_reads_as_sorted_counts(self):
        gs = _game_state()
        assert gs._format_unit_composition({'Swordsman': 3, 'Archer': 2}) == '2 Archer, 3 Swordsman'
        assert gs._format_unit_composition({}) == 'none'


class TestSimultaneousMode:
    def test_an_overflow_territory_is_disbanded_when_it_expires(self, monkeypatch):
        import map_data
        from simultaneous import SimultaneousGameState
        sim = SimultaneousGameState(_game_state())
        disbanded = []
        monkeypatch.setattr(sim, '_disband_excess_armies', disbanded.append)
        territory = sorted(map_data.get_all_territories())[0]
        sim.mark_overflow_territory(territory)
        assert sim.is_overflow_territory(territory)
        expiry = sim.overflow_territories[territory]
        assert expiry > sim.round_number
        sim.round_number = expiry - 1
        sim._process_overflow_territories()
        assert disbanded == [] and sim.is_overflow_territory(territory)
        sim.round_number = expiry
        sim._process_overflow_territories()
        assert disbanded == [territory] and not sim.is_overflow_territory(territory)

    def test_a_repeated_movement_order_runs_once(self):
        """Only an exact repeat is dropped: the rest of a split army on the same route and
        another player's order on that route both stay."""
        from simultaneous import SimPhaseManager, SimultaneousGameState
        manager = SimPhaseManager(SimultaneousGameState(_game_state()))
        order = {'type': 'movement', 'from_territory': 'A', 'to_territory': 'B',
                 'unit_ids': [0, 1], 'army_count': 2}
        rest = dict(order, unit_ids=[2], army_count=1)
        merged = manager._merge_orders({0: [order, dict(order), rest], 1: [dict(order)]})
        assert [(o['player_id'], o['unit_ids']) for o in merged] == [(0, [0, 1]), (0, [2]), (1, [0, 1])]

    def test_no_commented_debug_prints_in_simultaneous(self):
        sim_dir = os.path.join(PROJECT_ROOT, 'simultaneous')
        commented_print_re = re.compile(r'#\s*print\(')
        violations = []
        for filename in os.listdir(sim_dir):
            if not filename.endswith('.py'):
                continue
            filepath = os.path.join(sim_dir, filename)
            content = read_file_contents(filepath)
            for i, line in enumerate(content.splitlines(), 1):
                if commented_print_re.search(line):
                    violations.append(f'{filename}:{i}: {line.strip()}')
        assert len(violations) == 0, (
            f'Found {len(violations)} commented-out print() in simultaneous/'
        )


# ============================================================================
# 5. Settings Tests
# ============================================================================

class TestSettingsValidation:
    def test_setting_types_dict_exists(self):
        from settings_manager import SETTING_TYPES
        assert isinstance(SETTING_TYPES, dict)
        assert len(SETTING_TYPES) > 0

    def test_setting_types_covers_all_defaults(self):
        from settings_manager import SETTING_TYPES, SettingsManager
        SettingsManager._instance = None
        sm = SettingsManager()
        for key in sm.defaults:
            assert key in SETTING_TYPES, f"Setting '{key}' has no entry in SETTING_TYPES"

    def test_type_validation_rejects_wrong_types(self):
        from settings_manager import SettingsManager
        SettingsManager._instance = None
        sm = SettingsManager()
        original = sm.get('fullscreen')
        sm.set('fullscreen', 'not_a_bool')
        assert sm.get('fullscreen') == original
        original_fps = sm.get('show_fps')
        sm.set('show_fps', 42)
        assert sm.get('show_fps') == original_fps

    def test_type_validation_accepts_correct_types(self):
        from settings_manager import SettingsManager
        SettingsManager._instance = None
        sm = SettingsManager()
        sm.set('fullscreen', True)
        assert sm.get('fullscreen') is True
        sm.set('fullscreen', False)
        assert sm.get('fullscreen') is False
        sm.set('camera_pan_speed', 15.0)
        assert sm.get('camera_pan_speed') == 15.0
        sm.set('player_name', 'TestPlayer')
        assert sm.get('player_name') == 'TestPlayer'

    def test_resolution_accepts_list_and_tuple(self):
        from settings_manager import SettingsManager
        SettingsManager._instance = None
        sm = SettingsManager()
        sm.set('resolution', [1920, 1080])
        assert sm.get('resolution') == [1920, 1080]
        sm.set('resolution', (1600, 900))
        assert sm.get('resolution') == (1600, 900)


# ============================================================================
# 6. Camera/Input Tests
# ============================================================================

class TestCameraHandler:
    def test_zoom_bounds_assertion_exists(self):
        import pygame
        pygame.init()
        from input.camera_handler import CameraHandler
        cam = CameraHandler(1000, 800, 1600, 900, 700,
                            initial_zoom=2.0, min_zoom=1.5, max_zoom=4.0)
        assert cam.min_zoom == 1.5
        assert cam.max_zoom == 4.0
        with pytest.raises(AssertionError):
            CameraHandler(1000, 800, 1600, 900, 700,
                          initial_zoom=2.0, min_zoom=5.0, max_zoom=3.0)

    def test_initial_zoom_bounds_assertion(self):
        import pygame
        pygame.init()
        from input.camera_handler import CameraHandler
        with pytest.raises(AssertionError):
            CameraHandler(1000, 800, 1600, 900, 700,
                          initial_zoom=1.0, min_zoom=1.5, max_zoom=4.0)
        with pytest.raises(AssertionError):
            CameraHandler(1000, 800, 1600, 900, 700,
                          initial_zoom=5.0, min_zoom=1.5, max_zoom=4.0)

    def test_a_smaller_map_pulls_the_camera_back_inside(self):
        """update_map_dimensions() clamps the offset (M1): after a resolution change the view
        never shows the black area past the map's edge."""
        import pygame
        pygame.init()
        from input.camera_handler import CameraHandler
        cam = CameraHandler(1000, 800, 1600, 900, 700,
                            initial_zoom=2.0, min_zoom=1.5, max_zoom=4.0)
        cam.offset = [200.0, 450.0]   # the far corner of the 1000x800 map at zoom 2
        cam.update_map_dimensions(600, 500, 1600, 900, 700)
        assert cam.offset == [0, 150.0]   # 600x500: no room across, 150 down

    def test_clamp_to_bounds_functionality(self):
        import pygame
        pygame.init()
        from input.camera_handler import CameraHandler
        cam = CameraHandler(1000, 800, 1600, 900, 700,
                            initial_zoom=2.0, min_zoom=1.5, max_zoom=4.0)
        cam.offset = [-500.0, -500.0]
        cam.clamp_to_bounds()
        assert cam.offset[0] >= 0
        assert cam.offset[1] >= 0


class TestKeyboardHandler:
    def test_cheat_guard_returns_false_for_multiplayer(self):
        # Game keeps its connection in network_connection / multiplayer_mode. (The guard
        # once read `network_client` / `network_server` - attributes Game never has - so it
        # never fired and cheats worked online.)
        from types import SimpleNamespace
        from input.keyboard_handler import KeyboardHandler
        handler = KeyboardHandler()
        game_state = SimpleNamespace(territory_owners={}, network_mode=False)
        game_instance = SimpleNamespace(multiplayer_mode=True, network_connection=object())
        ui_state = {'game_instance': game_instance}
        result = handler._handle_cheat_code('youhavemysword1', game_state, ui_state)
        assert result is False

    def test_cheat_guard_also_reads_the_game_state(self):
        """No game instance in ui_state: the GameState's own network flag still blocks."""
        from types import SimpleNamespace
        from input.keyboard_handler import KeyboardHandler
        handler = KeyboardHandler()
        game_state = SimpleNamespace(territory_owners={}, network_mode=True)
        assert handler._handle_cheat_code('youhavemysword1', game_state, {}) is False


# ============================================================================
# 7. Meta Quality Tests
# ============================================================================

class TestCodeQualityMeta:
    def test_print_statement_count_reasonable(self):
        print_pattern = re.compile(r'(?<!\w)print\s*\(')
        total_prints = 0
        file_counts = {}
        for filepath in get_game_py_files():
            content = read_file_contents(filepath)
            code_lines = [
                line for line in content.splitlines()
                if not line.strip().startswith('#')
            ]
            code_content = chr(10).join(code_lines)
            matches = print_pattern.findall(code_content)
            if matches:
                rel = os.path.relpath(filepath, PROJECT_ROOT)
                file_counts[rel] = len(matches)
                total_prints += len(matches)
        # Threshold accounts for tool files (Adjacency_Tool, Plot_Tool, etc.),
        # campaign missions, and sound_manager which legitimately use print()
        assert total_prints < 300, (
            f'Found {total_prints} print() statements across game files (threshold: 300). '
            f'Breakdown: {json.dumps(file_counts, indent=2)}'
        )

    def test_key_modules_import_logger(self):
        modules_needing_logger = [
            os.path.join('game_state', '__init__.py'),
            'ai_player.py',
            'ai_strategy.py',
            'ai_economy.py',
            os.path.join('network', 'server.py'),
            os.path.join('network', 'client.py'),
            os.path.join('network', 'message_queue.py'),
            os.path.join('input', 'keyboard_handler.py'),
            os.path.join('simultaneous', 'sim_phase_manager.py'),
        ]
        missing_logger = []
        for module_rel in modules_needing_logger:
            filepath = os.path.join(PROJECT_ROOT, module_rel)
            if not os.path.exists(filepath):
                continue
            content = read_file_contents(filepath)
            if 'from utils.logger import' not in content and 'import logging' not in content:
                missing_logger.append(module_rel)
        assert len(missing_logger) == 0, (
            f'These modules should import logger but do not: {missing_logger}'
        )

    def test_network_files_use_monotonic_time(self):
        network_files = [
            os.path.join(PROJECT_ROOT, 'network', 'server.py'),
            os.path.join(PROJECT_ROOT, 'network', 'client.py'),
        ]
        for filepath in network_files:
            if not os.path.exists(filepath):
                continue
            content = read_file_contents(filepath)
            rel = os.path.relpath(filepath, PROJECT_ROOT)
            problem_lines = []
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if 'time.time()' in stripped:
                    problem_lines.append(f'  {rel}:{i}: {stripped}')
            assert len(problem_lines) == 0, (
                f'{rel} uses time.time() instead of time.monotonic()'
            )

    def test_heartbeat_timeout_relationship(self):
        from network_config import (
            HEARTBEAT_INTERVAL,
            HEARTBEAT_TIMEOUT,
            CONNECTION_TIMEOUT,
        )
        assert HEARTBEAT_INTERVAL < HEARTBEAT_TIMEOUT
        assert HEARTBEAT_TIMEOUT <= CONNECTION_TIMEOUT
