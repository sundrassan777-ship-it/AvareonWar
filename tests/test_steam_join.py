# -*- coding: utf-8 -*-
"""
Joining a friend's game from Steam (SDR Phase 3):

- the "+connect" target of a launch: Steam's own launch command line first (no
  "launching with arguments" warning), then the OS command line (both argument forms)
- join requests (Steam callback 337) while the game runs: the main menu takes them; in a
  game they wait, with a toast once; the invite this game was launched with is not
  joined a second time; stale ones are dropped
- the "Connecting..." screen: the window keeps responding, Cancel / Esc / Alt+F4 work
  at once, a connect that gets through just as the player cancels is closed again
- the Join Game screen: Alt+F4 closes the game (it used to be tried as an address)
- NetworkClient.cancel_connect()
"""

import os
import socket
import sys
import threading
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

from network.client import NetworkClient, SteamTarget  # noqa: E402
from steam_integration import (  # noqa: E402
    JOIN_REQUEST_LAUNCH_DEDUPE_SECONDS, JOIN_REQUEST_MAX_AGE_SECONDS, SteamManager,
    connect_target_from_args, connect_target_from_command_line, same_join_host)
from steam_networking import JoinRequest, steam_net  # noqa: E402

HOST_ID = 76561198886995069
FRIEND_ID = 76561198740785701
OTHER_ID = 76561198000000042
NAMES = {HOST_ID: 'Weel', FRIEND_ID: 'Rebeka'}


def wait_until(condition, timeout=5.0, what='condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(f"{what} not met within {timeout}s")


@pytest.fixture(scope='module')
def display():
    pygame.init()
    screen = pygame.display.set_mode((1600, 900))
    yield screen
    pygame.quit()


@pytest.fixture
def pending():
    """put(connect, friend, age) - a join request in steam_net, as Steam's callback 337
    leaves it; cleared afterwards."""
    def put(connect, friend=FRIEND_ID, age=0.0):
        join = JoinRequest(connect, friend, time.monotonic() - age)
        with steam_net._join_lock:
            steam_net._join_pending = join
        return join
    yield put
    with steam_net._join_lock:
        steam_net._join_pending = None


@pytest.fixture
def names(monkeypatch):
    """Steam names as steam_net would answer them ("[unknown]" for strangers)."""
    monkeypatch.setattr(steam_net, 'friend_name', lambda steam_id: NAMES.get(steam_id, '[unknown]'))


@pytest.fixture
def launched(monkeypatch):
    """launched(argv, steam_command_line='') -> a SteamManager that started with them."""
    def make(argv, steam_command_line=''):
        monkeypatch.setattr(steam_net, 'launch_command_line', lambda: steam_command_line)
        manager = SteamManager()
        manager.launch_connect_target(argv=argv)
        return manager
    return make


# ---------------------------------------------------------------------------
# The launch "+connect"
# ---------------------------------------------------------------------------

class TestLaunchTarget:

    @pytest.mark.parametrize('args, expected', [
        (['game.exe', '+connect', f'steam-{HOST_ID},1.2.3.4:7777'], f'steam-{HOST_ID},1.2.3.4:7777'),
        (['game.exe', '+connect 192.168.18.5:7777'], '192.168.18.5:7777'),   # one argument
        (['game.exe', '--sdr-test', '+connect', '"steam-5"'], 'steam-5'),
        (['game.exe'], ''),
        (['game.exe', '+connect'], ''),                                       # no value
        ([], ''),
    ])
    def test_both_argument_forms(self, args, expected):
        assert connect_target_from_args(args) == expected

    @pytest.mark.parametrize('text, expected', [
        (f'+connect steam-{HOST_ID},1.2.3.4:7777', f'steam-{HOST_ID},1.2.3.4:7777'),
        ('-windowed +connect "steam-5"', 'steam-5'),
        ('', ''),
        (None, ''),
    ])
    def test_steams_command_line_string(self, text, expected):
        assert connect_target_from_command_line(text) == expected

    def test_steams_launch_command_line_comes_first(self, launched):
        manager = launched(['game.exe', '+connect', '1.2.3.4:7777'],
                           steam_command_line=f'+connect steam-{HOST_ID}')
        assert manager._launch_connect_target == f'steam-{HOST_ID}'

    def test_the_os_command_line_is_the_fallback(self, launched):
        manager = launched(['game.exe', '+connect', '1.2.3.4:7777'])
        assert manager._launch_connect_target == '1.2.3.4:7777'

    def test_no_invite(self, launched):
        assert launched(['game.exe'])._launch_connect_target == ''

    def test_same_host(self):
        assert same_join_host(f'steam-{HOST_ID},1.2.3.4:7777', f'steam-{HOST_ID}')
        assert not same_join_host(f'steam-{HOST_ID}', f'steam-{OTHER_ID}')
        assert same_join_host('1.2.3.4:7777', '1.2.3.4')
        assert not same_join_host('1.2.3.4:7777', '1.2.3.5:7777')
        assert not same_join_host('', '')


# ---------------------------------------------------------------------------
# Join requests (callback 337)
# ---------------------------------------------------------------------------

class TestJoinRequests:

    def test_taken_once(self, pending):
        manager = SteamManager()
        pending(f'steam-{HOST_ID},1.2.3.4:7777')
        join = manager.take_join_request()
        assert join.connect == f'steam-{HOST_ID},1.2.3.4:7777'
        assert manager.take_join_request() is None

    def test_peek_leaves_it_for_the_main_menu(self, pending):
        manager = SteamManager()
        join = pending(f'steam-{HOST_ID}')
        assert manager.peek_join_request() is join
        assert manager.peek_join_request() is join
        assert manager.take_join_request() is join

    def test_the_launch_invite_again_is_not_joined_twice(self, launched, pending):
        # Steam might announce one invite both ways: on the command line and as 337
        manager = launched(['game.exe', '+connect', f'steam-{HOST_ID},192.168.18.5:7777'])
        pending(f'steam-{HOST_ID},212.20.115.148:7777')       # same host, newer addresses
        assert manager.peek_join_request() is None             # no toast for it
        assert manager.take_join_request() is None             # and no second join

    def test_the_same_host_later_is_a_new_join(self, launched, pending):
        manager = launched(['game.exe', '+connect', f'steam-{HOST_ID}'])
        manager._launch_time -= JOIN_REQUEST_LAUNCH_DEDUPE_SECONDS + 5
        pending(f'steam-{HOST_ID}')
        assert manager.take_join_request() is not None

    def test_another_host_right_after_launch_is_joined(self, launched, pending):
        manager = launched(['game.exe', '+connect', f'steam-{HOST_ID}'])
        pending(f'steam-{OTHER_ID}')
        assert manager.take_join_request().connect == f'steam-{OTHER_ID}'

    def test_stale_requests_are_dropped(self, pending):
        manager = SteamManager()
        pending(f'steam-{HOST_ID}', age=JOIN_REQUEST_MAX_AGE_SECONDS + 1)
        assert manager.peek_join_request() is None
        assert manager.take_join_request() is None

    def test_a_request_without_a_game_is_dropped(self, pending):
        manager = SteamManager()
        pending('')
        assert manager.take_join_request() is None

    def test_host_name_for_the_toast(self, names):
        manager = SteamManager()
        assert manager.join_request_host_name(JoinRequest(f'steam-{HOST_ID}', FRIEND_ID, 0)) == 'Weel'
        # No Steam target: the friend it came through
        assert manager.join_request_host_name(JoinRequest('1.2.3.4:7777', FRIEND_ID, 0)) == 'Rebeka'
        assert manager.join_request_host_name(JoinRequest(f'steam-{OTHER_ID}', 0, 0)) == ''


class TestMainMenu:

    def test_the_menu_starts_the_join(self, display, pending, monkeypatch):
        import main_menu
        from steam_integration import steam_manager
        monkeypatch.setattr(steam_manager, '_launch_connect_target', '')
        pending(f'steam-{HOST_ID},192.168.18.5:7777')
        menu = main_menu.MainMenu(display)
        assert menu.run() == 'steam_invite_join'
        assert menu.steam_join_target == f'steam-{HOST_ID},192.168.18.5:7777'
        assert steam_net.peek_join_request() is None            # taken


class _Toasts:
    def __init__(self):
        self.shown = []

    def add_system_notification(self, text, color=None):
        self.shown.append((text, color))


class TestInGameToast:

    @pytest.fixture
    def game(self, monkeypatch):
        from steam_integration import steam_manager
        monkeypatch.setattr(steam_manager, '_launch_connect_target', '')
        return types.SimpleNamespace(chat_notification_effect=_Toasts(), _steam_join_toast_for=None)

    @staticmethod
    def notify(game):
        from main import Game
        Game._notify_steam_join_request(game)

    def test_shown_once_per_request(self, game, pending, names):
        from ui.effects.chat_notification_effect import NEWS_MSG_COLOR
        pending(f'steam-{HOST_ID}')
        self.notify(game)
        self.notify(game)                                       # every frame: still once
        assert game.chat_notification_effect.shown == [
            ("Weel's game opens when you return to the main menu.", NEWS_MSG_COLOR)]
        assert steam_net.peek_join_request() is not None        # left for the main menu
        pending(f'steam-{HOST_ID}')                             # accepted again
        self.notify(game)
        assert len(game.chat_notification_effect.shown) == 2

    def test_unknown_host(self, game, pending, names):
        pending(f'steam-{OTHER_ID}', friend=0)
        self.notify(game)
        assert game.chat_notification_effect.shown[0][0] == \
            "A friend's game opens when you return to the main menu."

    def test_nothing_without_a_request(self, game, pending):
        self.notify(game)
        assert game.chat_notification_effect.shown == []


# ---------------------------------------------------------------------------
# The "Connecting..." screen
# ---------------------------------------------------------------------------

class FakeClient:
    """NetworkClient stand-in: connect_any() blocks until released, then answers."""

    def __init__(self, outcome=True, block=False, reason='Lobby is full'):
        self.outcome = outcome
        self.reason = reason
        self.release = threading.Event()
        if not block:
            self.release.set()
        self.current_target = None
        self.disconnect_reason = ''
        self.cancelled = threading.Event()
        self.disconnects = 0
        self.done = threading.Event()

    def connect_any(self, targets, player_name='Player'):
        try:
            self.current_target = targets[0] if targets else None
            self.release.wait(10)
            if not self.outcome:
                self.disconnect_reason = self.reason
            return self.outcome
        finally:
            self.done.set()

    def cancel_connect(self):
        self.cancelled.set()

    @property
    def connect_cancelled(self):
        return self.cancelled.is_set()

    def disconnect(self):
        self.disconnects += 1


class _RecordingFont:
    """A font that remembers what it rendered (the screen's text)."""

    def __init__(self, font, rendered):
        self._font, self._rendered = font, rendered

    def render(self, text, antialias, color):
        self._rendered.append(text)
        return self._font.render(text, antialias, color)

    def __getattr__(self, name):
        return getattr(self._font, name)


@pytest.fixture
def setup(display):
    from network.multiplayer_setup import MultiplayerSetup
    pygame.event.clear()
    return MultiplayerSetup(display)


def _cancel_button_center(setup):
    # connect_with_progress: Cancel 400x70 at (center_x - 200, center_y + 80)
    return setup.width // 2, setup.height // 2 + 80 + 35


class TestConnectingScreen:

    def test_connected(self, setup):
        assert setup.connect_with_progress(FakeClient(True), [('1.2.3.4', 7777)], 'Me') is True

    def test_failed_keeps_the_reason(self, setup):
        client = FakeClient(False)
        assert setup.connect_with_progress(client, [('1.2.3.4', 7777)], 'Me') is False
        assert client.disconnect_reason == 'Lobby is full'

    def test_cancel_returns_at_once_and_a_late_success_is_closed(self, setup):
        client = FakeClient(True, block=True)
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                             pos=_cancel_button_center(setup)))
        started = time.monotonic()
        assert setup.connect_with_progress(client, [SteamTarget(HOST_ID)], 'Me') == 'cancelled'
        assert time.monotonic() - started < 2.0
        assert client.cancelled.is_set()
        client.release.set()                    # the connect gets through after all...
        wait_until(lambda: client.disconnects == 1, what='late connection closed again')

    def test_escape_cancels(self, setup):
        client = FakeClient(True, block=True)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=''))
        assert setup.connect_with_progress(client, [('1.2.3.4', 7777)], 'Me') == 'cancelled'
        client.release.set()

    def test_alt_f4_quits(self, setup):
        client = FakeClient(True, block=True)
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        assert setup.connect_with_progress(client, [('1.2.3.4', 7777)], 'Me') == 'quit'
        assert client.cancelled.is_set()
        client.release.set()

    def test_the_window_keeps_responding(self, setup, monkeypatch):
        from steam_integration import steam_manager
        frames, pumps = [], []
        real_flip = pygame.display.flip
        monkeypatch.setattr(pygame.display, 'flip', lambda: frames.append(1) or real_flip())
        monkeypatch.setattr(steam_manager, 'run_callbacks', lambda: pumps.append(1))
        client = FakeClient(True, block=True)
        threading.Timer(0.5, client.release.set).start()
        assert setup.connect_with_progress(client, [('1.2.3.4', 7777)], 'Me') is True
        assert len(frames) >= 5 and len(pumps) >= 5     # drawn and pumped while waiting

    def test_says_who_it_joins_through_steam(self, setup, names):
        rendered = []
        setup.text_font = _RecordingFont(setup.text_font, rendered)
        setup.small_font = _RecordingFont(setup.small_font, rendered)
        client = FakeClient(True, block=True)
        threading.Timer(0.3, client.release.set).start()
        assert setup.connect_with_progress(client, [SteamTarget(HOST_ID)], 'Me') is True
        assert "Connecting to Weel through Steam..." in rendered
        assert "Steam can take up to 15 seconds to find the host" in rendered
        assert "0 s" in rendered

    def test_a_long_steam_name_stays_inside_the_frame(self, setup, monkeypatch):
        monkeypatch.setattr(steam_net, 'friend_name', lambda steam_id: 'Lord ' + 'W' * 60)
        rendered = []
        setup.small_font = _RecordingFont(setup.small_font, rendered)
        client = FakeClient(True, block=True)
        threading.Timer(0.3, client.release.set).start()
        setup.connect_with_progress(client, [SteamTarget(HOST_ID)], 'Me')
        status = [label for label in rendered if label.startswith("Connecting to Lord")]
        assert status and all(label.endswith('...') for label in status)
        max_width = min(820, setup.width - 80) - 2 * 90
        assert all(setup.small_font.size(label)[0] <= max_width for label in status)

    def test_says_which_address_it_tries(self, setup):
        rendered = []
        setup.text_font = _RecordingFont(setup.text_font, rendered)
        client = FakeClient(True, block=True)
        threading.Timer(0.3, client.release.set).start()
        setup.connect_with_progress(client, [('192.168.18.5', 7777)], 'Me')
        assert "Connecting to 192.168.18.5..." in rendered

    def test_long_errors_stay_up_longer(self, setup):
        assert setup._error_display_ms("Lobby is full") == 3000
        assert setup._error_display_ms("x" * 100) == 6000
        assert setup._error_display_ms("x" * 1000) == 12000


class TestJoinScreen:

    def test_alt_f4_on_the_address_screen_closes_the_game(self, setup, monkeypatch):
        tried = []
        monkeypatch.setattr(setup, '_get_host_ip', lambda: 'quit')
        monkeypatch.setattr(setup, 'connect_with_progress', lambda *a: tried.append(a) or False)
        assert setup._run_join_setup() == 'quit'
        assert tried == []                                    # "quit" is not an address

    def test_direct_ip_goes_through_the_connecting_screen(self, setup, monkeypatch):
        calls, errors = [], []
        monkeypatch.setattr(setup, '_get_host_ip', lambda: '192.168.18.5')

        def fail(client, targets, player_name):
            calls.append(targets)
            client.disconnect_reason = 'No game is being hosted at that address'
            return False
        monkeypatch.setattr(setup, 'connect_with_progress', fail)
        monkeypatch.setattr(setup, '_show_error', errors.append)
        assert setup._run_join_setup() is None
        assert calls == [[('192.168.18.5', 7777)]]
        assert errors == ["Could not join 192.168.18.5: No game is being hosted at that address"]

    def test_cancel_goes_back_quietly(self, setup, monkeypatch):
        errors = []
        monkeypatch.setattr(setup, '_get_host_ip', lambda: '192.168.18.5')
        monkeypatch.setattr(setup, 'connect_with_progress', lambda *a: 'cancelled')
        monkeypatch.setattr(setup, '_show_error', errors.append)
        assert setup._run_join_setup() is None
        assert errors == []


# ---------------------------------------------------------------------------
# NetworkClient.cancel_connect()
# ---------------------------------------------------------------------------

class TestClientCancel:

    def test_cancel_while_waiting_for_the_hosts_answer(self):
        silent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # takes us, never answers
        silent.bind(('127.0.0.1', 0))
        silent.listen(1)
        client = NetworkClient()
        outcome = {}
        worker = threading.Thread(target=lambda: outcome.update(
            ok=client.connect('127.0.0.1', silent.getsockname()[1], player_name='Me')))
        try:
            worker.start()
            time.sleep(0.3)
            started = time.monotonic()
            client.cancel_connect()
            worker.join(5)
            assert time.monotonic() - started < 1.0           # not the 5 s answer timeout
            assert outcome['ok'] is False
            assert client.disconnect_reason == "Cancelled"
        finally:
            silent.close()

    def test_a_cancelled_client_tries_nothing_more(self):
        client = NetworkClient()
        client.cancel_connect()
        assert client.connect_any([('127.0.0.1', 1), SteamTarget(HOST_ID)]) is False
        assert client.disconnect_reason == "Cancelled"
        assert client.current_target is None
        assert client.connect_cancelled
