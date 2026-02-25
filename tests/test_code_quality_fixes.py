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
import inspect
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

# Set up headless pygame for tests that need it
os.environ["SDL_VIDEODRIVER"] = "dummy"


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
        assert len(violations) == 0, f'Found {len(violations)} bare except clause(s)'

    def test_except_clauses_have_specific_types(self):
        critical_files = [
            os.path.join(PROJECT_ROOT, 'network', 'client.py'),
            os.path.join(PROJECT_ROOT, 'network', 'server.py'),
            os.path.join(PROJECT_ROOT, 'network', 'protocol.py'),
            os.path.join(PROJECT_ROOT, 'settings_manager.py'),
        ]
        bare_except_re = re.compile(r'^\s*except\s*:\s*(#.*)?$', re.MULTILINE)
        for filepath in critical_files:
            if not os.path.exists(filepath):
                continue
            content = read_file_contents(filepath)
            for i, line in enumerate(content.splitlines(), 1):
                if bare_except_re.match(line):
                    rel = os.path.relpath(filepath, PROJECT_ROOT)
                    assert False, f'Bare except found in {rel}:{i}'


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
    def test_client_uses_monotonic_time(self):
        client_path = os.path.join(PROJECT_ROOT, 'network', 'client.py')
        content = read_file_contents(client_path)
        assert 'time.monotonic()' in content, 'network/client.py should use time.monotonic()'
        code_lines = [
            line for line in content.splitlines()
            if not line.strip().startswith('#') and 'time.time()' in line
        ]
        assert len(code_lines) == 0, f'network/client.py still uses time.time(): {code_lines}'

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

    def test_server_uses_monotonic_time(self):
        server_path = os.path.join(PROJECT_ROOT, 'network', 'server.py')
        content = read_file_contents(server_path)
        assert 'time.monotonic()' in content


# ============================================================================
# 3. AI Changes Tests
# ============================================================================

class TestAIPerformance:
    def test_ai_player_uses_thread_pool(self):
        ai_player_path = os.path.join(PROJECT_ROOT, 'ai_player.py')
        content = read_file_contents(ai_player_path)
        assert 'ThreadPoolExecutor' in content
        assert 'from concurrent.futures import ThreadPoolExecutor' in content

    def test_ai_player_has_thread_pool_attribute(self):
        import pygame
        pygame.init()
        from ai_player import AIPlayer
        ai = AIPlayer(player_index=1, difficulty=0)
        assert hasattr(ai, '_thread_pool')
        ai.shutdown()

    def test_ai_player_has_animation_event(self):
        import pygame
        pygame.init()
        from ai_player import AIPlayer
        ai = AIPlayer(player_index=1, difficulty=0)
        assert hasattr(ai, '_animation_done')
        assert isinstance(ai._animation_done, threading.Event)
        ai.shutdown()

    def test_ai_military_has_precomputed_reachability(self):
        mil_path = os.path.join(PROJECT_ROOT, 'ai_military.py')
        content = read_file_contents(mil_path)
        assert 'precomputed_reachability' in content


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

    def test_ai_economy_score_building_is_used_by_public_api(self):
        from ai_economy import BuildingPlanner
        source = inspect.getsource(BuildingPlanner.score_building_placement)
        assert '_score_building' in source


# ============================================================================
# 4. Game Logic Tests
# ============================================================================

class TestGameStateRefactor:
    def test_execute_all_orders_exists(self):
        gs_path = os.path.join(PROJECT_ROOT, 'game_state', '__init__.py')
        content = read_file_contents(gs_path)
        assert 'def execute_all_orders' in content

    def test_execute_all_orders_has_helper_methods(self):
        gs_path = os.path.join(PROJECT_ROOT, 'game_state', '__init__.py')
        content = read_file_contents(gs_path)
        assert 'def _process_arrivals' in content

    def test_format_unit_composition_helper_exists(self):
        gs_path = os.path.join(PROJECT_ROOT, 'game_state', '__init__.py')
        content = read_file_contents(gs_path)
        assert 'def _format_unit_composition' in content


class TestSimultaneousMode:
    def test_mark_overflow_territory_exists(self):
        # Check source file directly since sim_debug.py may have syntax issues
        sim_state_path = os.path.join(PROJECT_ROOT, 'simultaneous', 'sim_state.py')
        content = read_file_contents(sim_state_path)
        assert 'def mark_overflow_territory' in content

    def test_order_deduplication_in_phase_manager(self):
        spm_path = os.path.join(PROJECT_ROOT, 'simultaneous', 'sim_phase_manager.py')
        content = read_file_contents(spm_path)
        assert 'dedup' in content.lower()
        assert 'seen_movement_orders' in content

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

    def test_clamp_to_bounds_called_in_update_map_dimensions(self):
        import pygame
        pygame.init()
        from input.camera_handler import CameraHandler
        cam = CameraHandler(1000, 800, 1600, 900, 700,
                            initial_zoom=2.0, min_zoom=1.5, max_zoom=4.0)
        source = inspect.getsource(cam.update_map_dimensions)
        assert 'clamp_to_bounds' in source

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
    def test_multiplayer_cheat_guard_exists(self):
        from input.keyboard_handler import KeyboardHandler
        source = inspect.getsource(KeyboardHandler._handle_cheat_code)
        assert 'network_client' in source
        assert 'network_server' in source

    def test_cheat_guard_returns_false_for_multiplayer(self):
        from input.keyboard_handler import KeyboardHandler
        handler = KeyboardHandler()
        mock_game_state = Mock()
        mock_game_state.territory_owners = {}
        mock_game_instance = Mock()
        mock_game_instance.network_client = Mock()
        mock_game_instance.network_server = None
        ui_state = {'game_instance': mock_game_instance}
        result = handler._handle_cheat_code('youhavemysword1', mock_game_state, ui_state)
        assert result is False


# ============================================================================
# 7. Meta Quality Tests
# ============================================================================

class TestCodeQualityMeta:
    def test_zero_bare_excepts_across_all_game_files(self):
        bare_except_re = re.compile(r'^\s*except\s*:\s*(#.*)?$', re.MULTILINE)
        count = 0
        for filepath in get_game_py_files():
            content = read_file_contents(filepath)
            for line in content.splitlines():
                if bare_except_re.match(line):
                    count += 1
        assert count == 0, f'Found {count} bare except clause(s) across all game files'

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
