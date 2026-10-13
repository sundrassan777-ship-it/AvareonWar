"""
Steam networking binding (steam_networking.py) without Steam: struct layouts against the
SDK 1.63 headers, the init order and kill switches, copy-then-release of received
messages, the status callback, and the emulated CCallbackBase for join requests (337).

A FakeSteamApi stands in for steam_api64.dll. It has the same function names and plays
the side effects the SDK documents (e.g. SteamAPI_RegisterCallback sets the "registered"
flag). Real-Steam behaviour is checked by the --sdr-test tool (steam_sdr_test.py).
"""

import ctypes
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import steam_networking as sn  # noqa: E402
from steam_networking import (  # noqa: E402
    SteamNetworking, SteamNetConnectionInfo_t, SteamNetConnectionStatusChangedCallback_t,
    SteamNetworkingMessage_t, GameRichPresenceJoinRequested_t, SteamNetworkingIdentity,
    SteamNetworkingIPAddr, CCallbackBase, parse_join_connect_string)

HOST_ID = 76561198740785701
FRIEND_ID = 76561198012345678


class FakeSteamApi:
    """steam_api64.dll stand-in: records calls in order, plays documented side effects."""

    def __init__(self, register_sets_flag=True):
        self.calls = []
        self.register_sets_flag = register_sets_flag
        self.config = {}
        self.sent = []
        self.released = []
        self.inbox = {}           # conn -> [bytes, ...] waiting to be received
        self.send_result = sn.RESULT_OK
        self._keep_alive = []     # fake messages + buffers until the test ends

    # Interface accessors
    def SteamAPI_SteamNetworkingSockets_SteamAPI_v012(self):
        return 0x1000

    def SteamAPI_SteamNetworkingUtils_SteamAPI_v004(self):
        return 0x2000

    def SteamAPI_SteamFriends_v018(self):
        return 0x3000

    def SteamAPI_SteamUser_v023(self):
        return 0x4000

    def SteamAPI_SteamUtils_v010(self):
        return 0x5000

    def SteamAPI_SteamApps_v008(self):
        return 0x6000

    # ISteamApps: the launch command line (a string buffer filled like Steam does)
    launch_command_line = ''

    def SteamAPI_ISteamApps_GetLaunchCommandLine(self, _apps, buffer, size):
        data = self.launch_command_line.encode('utf-8')[:size - 1]
        buffer.value = data
        return len(data)

    # Relay setup
    def SteamAPI_ISteamNetworkingUtils_SetGlobalCallback_SteamNetConnectionStatusChanged(self, _utils, fn):
        self.calls.append(('global_callback', None if fn is None else fn.value))
        return True

    def SteamAPI_ISteamNetworkingUtils_SetConfigValue(self, _utils, value_id, scope, _obj, data_type, arg):
        self.calls.append(('config', value_id))
        self.config[value_id] = (arg._obj.value, scope, data_type)
        return True

    def SteamAPI_ISteamNetworkingUtils_InitRelayNetworkAccess(self, _utils):
        self.calls.append('init_relay')

    def SteamAPI_ISteamNetworkingSockets_InitAuthentication(self, _sockets):
        self.calls.append('init_auth')
        return 3

    # Classic callbacks (steam_api_internal.h: register sets the flag, unregister clears it)
    def SteamAPI_RegisterCallback(self, obj_ref, callback_id):
        self.calls.append(('register', callback_id))
        self.registered = obj_ref._obj
        if self.register_sets_flag:
            obj_ref._obj.m_nCallbackFlags |= 0x01
            obj_ref._obj.m_iCallback = callback_id

    def SteamAPI_UnregisterCallback(self, obj_ref):
        self.calls.append('unregister')
        obj_ref._obj.m_nCallbackFlags &= ~0x01

    # Sockets
    def SteamAPI_ISteamNetworkingSockets_RunCallbacks(self, _sockets):
        self.calls.append('run_callbacks')

    def SteamAPI_ISteamNetworkingSockets_CreateListenSocketP2P(self, _sockets, port, _n, _opts):
        self.calls.append(('listen', port))
        return 11

    def SteamAPI_ISteamNetworkingSockets_ConnectP2P(self, _sockets, identity_ref, port, _n, _opts):
        identity = identity_ref._obj.value
        self.calls.append(('connect', identity.m_eType, identity.m_steamID64, port))
        return 77

    def SteamAPI_SteamNetworkingIdentity_SetSteamID64(self, identity_ref, steam_id):
        identity = identity_ref._obj.value
        identity.m_eType, identity.m_cbSize, identity.m_steamID64 = 16, 8, steam_id

    def SteamAPI_SteamNetworkingIdentity_GetSteamID64(self, identity_ref):
        identity = identity_ref._obj.value
        return identity.m_steamID64 if identity.m_eType == 16 else 0

    def SteamAPI_ISteamNetworkingSockets_SendMessageToConnection(self, _sockets, conn, data, size, flags, _out):
        self.sent.append((conn, bytes(data), size, flags))
        return self.send_result

    def SteamAPI_ISteamNetworkingSockets_ReceiveMessagesOnConnection(self, _sockets, conn, pointers, max_messages):
        queue = self.inbox.get(conn)
        if queue is None:
            return -1
        count = 0
        while queue and count < max_messages:
            data = queue.pop(0)
            buffer = ctypes.create_string_buffer(data, len(data))
            message = SteamNetworkingMessage_t()
            message.m_pData = ctypes.cast(buffer, ctypes.c_void_p)
            message.m_cbSize = len(data)
            message.m_conn = conn
            self._keep_alive.append((buffer, message))
            pointers[count] = ctypes.addressof(message)
            count += 1
        return count

    def SteamAPI_SteamNetworkingMessage_t_Release(self, pointer):
        self.released.append(pointer)

    def SteamAPI_ISteamNetworkingSockets_GetConnectionInfo(self, _sockets, conn, out_ref):
        if conn != 77:
            return False
        info = out_ref._obj.value
        info.m_eState = sn.STATE_CONNECTED
        info.m_nFlags = sn.CONNECTION_FLAG_RELAYED
        info.m_identityRemote.m_eType = 16
        info.m_identityRemote.m_steamID64 = HOST_ID
        info.m_szConnectionDescription = b'conn #77 P2P steamid:' + str(HOST_ID).encode()
        return True

    def SteamAPI_ISteamNetworkingSockets_CloseConnection(self, _sockets, conn, reason, debug, linger):
        self.calls.append(('close', conn, reason, debug, linger))
        return True

    def SteamAPI_ISteamUser_GetSteamID(self, _user):
        return HOST_ID


@pytest.fixture
def fake_api():
    return FakeSteamApi()


@pytest.fixture
def net(fake_api):
    """A SteamNetworking bound to the fake DLL with both features on."""
    networking = SteamNetworking()
    assert networking.init(join_hook=True, relay=True, api=fake_api)
    yield networking
    networking.shutdown()


# ---------------------------------------------------------------------------
# Struct layouts (SDK 1.63, Win64)
# ---------------------------------------------------------------------------

class TestLayouts:

    def test_struct_sizes_match_the_sdk(self):
        expected = {SteamNetworkingIPAddr: 18, SteamNetworkingIdentity: 136,
                    SteamNetConnectionInfo_t: 696, SteamNetConnectionStatusChangedCallback_t: 712,
                    SteamNetworkingMessage_t: 216, GameRichPresenceJoinRequested_t: 264}
        for struct, size in expected.items():
            assert ctypes.sizeof(struct) == size, struct.__name__

    def test_field_offsets_match_the_sdk(self):
        assert SteamNetworkingIdentity.m_steamID64.offset == 8
        assert SteamNetConnectionInfo_t.m_nUserData.offset == 136
        assert SteamNetConnectionInfo_t.m_addrRemote.offset == 148
        assert SteamNetConnectionInfo_t.m_eState.offset == 176
        assert SteamNetConnectionInfo_t.m_szEndDebug.offset == 184
        assert SteamNetConnectionInfo_t.m_nFlags.offset == 440
        assert SteamNetConnectionStatusChangedCallback_t.m_info.offset == 8
        assert SteamNetConnectionStatusChangedCallback_t.m_eOldState.offset == 704
        assert SteamNetworkingMessage_t.m_identityPeer.offset == 16
        assert SteamNetworkingMessage_t.m_pfnRelease.offset == 184
        assert GameRichPresenceJoinRequested_t.m_rgchConnect.offset == 8

    def test_callback_object_matches_ccallbackbase(self):
        # vtable pointer, uint8 flags at 8, int id at 12 (the first 16 bytes Steam uses)
        assert CCallbackBase.vtable.offset == 0
        assert CCallbackBase.m_nCallbackFlags.offset == 8
        assert CCallbackBase.m_iCallback.offset == 12
        assert ctypes.sizeof(CCallbackBase) >= 16


# ---------------------------------------------------------------------------
# Without Steam: every call is a harmless no-op
# ---------------------------------------------------------------------------

class TestWithoutSteam:

    def test_unbound_module_does_nothing(self):
        networking = SteamNetworking()
        assert not networking.available and not networking.relay_enabled
        assert networking.listen() == sn.INVALID_HANDLE
        assert networking.connect(HOST_ID) == sn.INVALID_HANDLE
        assert networking.send(5, b'x') == sn.RESULT_NO_CONNECTION
        assert networking.receive(5) is None
        assert networking.connection_info(5) is None
        assert networking.create_socket_pair() is None
        assert networking.poll_status_events() == []
        assert networking.take_join_request() is None
        assert networking.get_friend_rich_presence(HOST_ID, 'connect') == ''
        assert not networking.set_rich_presence('connect', 'x')
        assert networking.own_steam_id() == 0
        networking.run_callbacks()
        networking.shutdown()

    def test_no_interface_from_steam_means_unavailable(self, fake_api):
        fake_api.SteamAPI_SteamNetworkingSockets_SteamAPI_v012 = lambda: None
        networking = SteamNetworking()
        assert not networking.init(api=fake_api)
        assert not networking.available


# ---------------------------------------------------------------------------
# Init order, kill switches, shutdown
# ---------------------------------------------------------------------------

class TestLifecycle:

    def test_status_callback_is_installed_before_anything_else(self, net, fake_api):
        relay_calls = [c for c in fake_api.calls if c in ('init_relay', 'init_auth')
                       or (isinstance(c, tuple) and c[0] in ('global_callback', 'config'))]
        assert relay_calls[0][0] == 'global_callback' and relay_calls[0][1]
        assert relay_calls[-2:] == ['init_relay', 'init_auth']
        assert net.relay_enabled and net.join_hook_enabled

    def test_connection_defaults_are_set_globally(self, net, fake_api):
        # 4 MB send buffer (frames reach 1 MB; the 512 KB default makes sends fail) and a
        # 15 s connect timeout, both at global scope as int32
        assert fake_api.config[9] == (sn.SEND_BUFFER_BYTES, 1, 1)
        assert fake_api.config[24] == (sn.CONNECT_TIMEOUT_MS, 1, 1)

    def test_relay_switch_off_skips_all_networking(self, fake_api):
        networking = SteamNetworking()
        assert networking.init(join_hook=True, relay=False, api=fake_api)
        assert not networking.relay_enabled
        assert not any(isinstance(c, tuple) and c[0] in ('global_callback', 'config')
                       for c in fake_api.calls)
        assert networking.listen() == sn.INVALID_HANDLE       # bridge cannot start
        assert networking.join_hook_enabled                    # the other feature still runs

    def test_join_hook_switch_off_never_registers(self, fake_api):
        networking = SteamNetworking()
        assert networking.init(join_hook=False, relay=True, api=fake_api)
        assert not networking.join_hook_enabled
        assert not any(isinstance(c, tuple) and c[0] == 'register' for c in fake_api.calls)

    def test_shutdown_unregisters_and_clears_the_callback(self, fake_api):
        networking = SteamNetworking()
        networking.init(api=fake_api)
        networking.shutdown()
        assert 'unregister' in fake_api.calls
        assert fake_api.calls[-1] == ('global_callback', None)
        assert not networking.available


# ---------------------------------------------------------------------------
# Kill switches (launch options + config.json keys)
# ---------------------------------------------------------------------------

class _Settings:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class TestKillSwitches:

    def test_both_features_on_by_default(self):
        from steam_integration import steam_feature_switches
        assert steam_feature_switches(['game.exe'], _Settings()) == (True, True)

    def test_launch_options_switch_features_off(self):
        from steam_integration import steam_feature_switches
        assert steam_feature_switches(['game.exe', '--no-steam-join-hook'], _Settings()) == (False, True)
        assert steam_feature_switches(['game.exe', '--no-steam-relay'], _Settings()) == (True, False)

    def test_config_keys_switch_features_off(self):
        from steam_integration import steam_feature_switches
        assert steam_feature_switches(['game.exe'], _Settings(steam_join_hook=False)) == (False, True)
        assert steam_feature_switches(['game.exe'], _Settings(steam_relay=False)) == (True, False)

    @pytest.mark.parametrize('argv', [
        ['game.exe'],                   # regular play (joining through Steam needs it)
        ['game.exe', '--sdr-test'],     # the diagnostics tool
    ])
    def test_binding_happens_in_regular_play_too(self, monkeypatch, argv):
        # The Phase 1 gate (only --sdr-test bound it) is gone since the two-PC test
        import settings_manager
        import steam_integration
        from steam_networking import steam_net
        calls = []
        monkeypatch.setattr(settings_manager, 'settings', _Settings())  # not this PC's config.json
        monkeypatch.setattr(sys, 'argv', argv)
        monkeypatch.setattr(steam_net, 'init', lambda **kw: calls.append(kw) or True)
        steam_integration.SteamManager()._init_networking()
        assert calls == [{'join_hook': True, 'relay': True}]

    def test_kill_switch_reaches_the_binding(self, monkeypatch):
        import settings_manager
        import steam_integration
        from steam_networking import steam_net
        calls = []
        monkeypatch.setattr(settings_manager, 'settings', _Settings())
        monkeypatch.setattr(sys, 'argv', ['game.exe', '--no-steam-relay'])
        monkeypatch.setattr(steam_net, 'init', lambda **kw: calls.append(kw) or True)
        steam_integration.SteamManager()._init_networking()
        assert calls == [{'join_hook': True, 'relay': False}]

    def test_settings_know_the_keys(self):
        # Unknown keys are deleted on load (settings_manager validation) - they must be known
        from settings_manager import SETTING_TYPES, settings
        for key in ('steam_join_hook', 'steam_relay'):
            assert SETTING_TYPES[key] == (bool,)
            assert settings.defaults[key] is True


# ---------------------------------------------------------------------------
# Sockets: send, receive (copy + release), identities, connection info
# ---------------------------------------------------------------------------

class TestSockets:

    def test_connect_builds_a_steamid_identity(self, net, fake_api):
        assert net.connect(HOST_ID) == 77
        assert ('connect', 16, HOST_ID, 0) in fake_api.calls

    def test_send_is_reliable_and_passes_the_whole_message(self, net, fake_api):
        payload = os.urandom(300 * 1024)
        assert net.send(77, payload) == sn.RESULT_OK
        conn, data, size, flags = fake_api.sent[-1]
        assert (conn, data, size, flags) == (77, payload, len(payload), sn.SEND_RELIABLE)

    def test_send_reports_a_full_buffer(self, net, fake_api):
        fake_api.send_result = sn.RESULT_LIMIT_EXCEEDED
        assert net.send(77, b'x') == sn.RESULT_LIMIT_EXCEEDED

    def test_received_messages_are_copied_then_released(self, net, fake_api):
        fake_api.inbox[77] = [b'first', b'', os.urandom(70000)]
        expected = list(fake_api.inbox[77])
        messages = net.receive_messages(77, 32)
        assert [m.data for m in messages] == expected
        assert all(m.conn == 77 and m.size == len(m.data) for m in messages)
        # Every message released exactly once - Steam leaks it otherwise
        assert len(fake_api.released) == 3 and len(set(fake_api.released)) == 3

    def test_receive_reports_a_bad_handle(self, net):
        assert net.receive(999) is None

    def test_connection_info_reads_route_and_peer(self, net):
        info = net.connection_info(77)
        assert info.state == sn.STATE_CONNECTED
        assert info.flags & sn.CONNECTION_FLAG_RELAYED
        assert info.remote_steam_id == HOST_ID
        assert info.description.startswith('conn #77')
        assert net.connection_info(5) is None

    def test_close_passes_reason_debug_and_linger(self, net, fake_api):
        net.close(77, sn.END_APP_GENERIC, 'lobby full', linger=True)
        assert ('close', 77, sn.END_APP_GENERIC, b'lobby full', True) in fake_api.calls

    def test_identity_round_trip(self, net):
        assert net.identity_round_trip(HOST_ID) == HOST_ID

    def test_run_callbacks_uses_the_networking_dispatch(self, net, fake_api):
        net.run_callbacks()
        assert fake_api.calls[-1] == 'run_callbacks'


# ---------------------------------------------------------------------------
# Status callback (global function pointer)
# ---------------------------------------------------------------------------

class TestStatusCallback:

    def test_status_change_is_copied_into_an_event(self, net):
        data = SteamNetConnectionStatusChangedCallback_t()
        data.m_hConn = 42
        data.m_eOldState = sn.STATE_CONNECTING
        data.m_info.m_eState = sn.STATE_CLOSED_BY_PEER
        data.m_info.m_hListenSocket = 11
        data.m_info.m_eEndReason = 5003
        data.m_info.m_szEndDebug = b'timed out'
        data.m_info.m_nFlags = sn.CONNECTION_FLAG_RELAYED
        data.m_info.m_identityRemote.m_eType = 16
        data.m_info.m_identityRemote.m_steamID64 = FRIEND_ID
        # Call the exact C function pointer Steam would call
        net._status_callback(ctypes.addressof(data))
        events = net.poll_status_events()
        assert len(events) == 1
        event = events[0]
        assert (event.conn, event.state, event.old_state, event.listen_socket) == (
            42, sn.STATE_CLOSED_BY_PEER, sn.STATE_CONNECTING, 11)
        assert (event.end_reason, event.end_debug, event.remote_steam_id) == (5003, 'timed out', FRIEND_ID)
        assert event.thread  # the dispatching thread is recorded (diagnostics)
        assert net.poll_status_events() == []

    def test_a_bad_pointer_never_raises_into_steam(self, net):
        net._status_callback(None)          # handler must swallow it
        assert net.poll_status_events() == []


# ---------------------------------------------------------------------------
# Join requests (callback 337, emulated CCallbackBase)
# ---------------------------------------------------------------------------

def _call_slot(net, slot, param):
    """Call one vtable slot of our callback object the way Steam's C++ code would."""
    address = net._join_vtable[slot]
    run = sn._CALLBACK_RUN_TYPE(address)
    run(ctypes.addressof(net._join_object), param, False, 0)


class TestJoinHook:

    def test_vtable_points_both_run_overloads_at_one_handler(self, net):
        slots = list(net._join_vtable)
        assert slots[0] == slots[1] != slots[2]
        size = sn._CALLBACK_SIZE_TYPE(slots[2])(ctypes.addressof(net._join_object))
        assert size == 264
        assert net._join_object.vtable == ctypes.addressof(net._join_vtable)

    @pytest.mark.parametrize('slot', [0, 1])
    def test_join_request_is_recorded_from_either_slot(self, net, slot):
        request = GameRichPresenceJoinRequested_t()
        request.m_steamIDFriend = HOST_ID
        request.m_rgchConnect = f'+connect steam-{HOST_ID},192.168.18.5:7777'.encode()
        _call_slot(net, slot, ctypes.addressof(request))
        join = net.take_join_request()
        assert join.connect == f'steam-{HOST_ID},192.168.18.5:7777'
        assert join.friend_steam_id == HOST_ID
        assert net.take_join_request() is None            # handled once
        assert net.join_history()[-1].connect == join.connect

    def test_newest_request_wins(self, net):
        for target in ('1.2.3.4:7777', '5.6.7.8:7777'):
            request = GameRichPresenceJoinRequested_t()
            request.m_rgchConnect = f'+connect {target}'.encode()
            _call_slot(net, 0, ctypes.addressof(request))
        assert net.take_join_request().connect == '5.6.7.8:7777'

    def test_peek_leaves_the_request_for_the_main_menu(self, net):
        # The in-game toast peeks; the main menu takes it later
        request = GameRichPresenceJoinRequested_t()
        request.m_rgchConnect = f'+connect steam-{HOST_ID}'.encode()
        _call_slot(net, 0, ctypes.addressof(request))
        first = net.peek_join_request()
        assert first is net.peek_join_request() is not None
        assert net.take_join_request() is first
        assert net.peek_join_request() is None


class TestLaunchCommandLine:
    """ISteamApps::GetLaunchCommandLine: an invite's "+connect" without the OS command
    line (no "launching with arguments" warning from Steam)."""

    def test_read_from_steam(self, net, fake_api):
        fake_api.launch_command_line = f'+connect steam-{HOST_ID},192.168.18.5:7777'
        assert net.launch_command_line() == f'+connect steam-{HOST_ID},192.168.18.5:7777'

    def test_empty_when_steam_has_none(self, net):
        assert net.launch_command_line() == ''

    def test_without_the_apps_interface_networking_still_works(self):
        class NoApps(FakeSteamApi):
            SteamAPI_SteamApps_v008 = None      # not found in this DLL
        networking = SteamNetworking()
        assert networking.init(api=NoApps())
        assert networking.relay_enabled
        assert networking.launch_command_line() == ''
        networking.shutdown()

    def test_functions_are_typed_for_the_real_dll(self):
        assert sn._FUNCTIONS['SteamAPI_SteamApps_v008'] == (ctypes.c_void_p, [])
        restype, argtypes = sn._FUNCTIONS['SteamAPI_ISteamApps_GetLaunchCommandLine']
        assert restype is ctypes.c_int
        assert argtypes == [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]

    def test_unbound_module_reads_nothing(self):
        assert SteamNetworking().launch_command_line() == ''

    def test_layout_mismatch_turns_the_hook_off(self):
        # Steam did not set the registered flag where we expect it -> unregister, stay off
        api = FakeSteamApi(register_sets_flag=False)
        networking = SteamNetworking()
        networking.init(api=api)
        assert not networking.join_hook_enabled
        assert 'unregister' in api.calls

    @pytest.mark.parametrize('raw, expected', [
        (b'+connect steam-76561198740785701', 'steam-76561198740785701'),
        (b'+connect  1.2.3.4:7777,5.6.7.8:7777 ', '1.2.3.4:7777,5.6.7.8:7777'),
        (b'1.2.3.4:7777', '1.2.3.4:7777'),
        (b'', ''),
        (b'+connect \xff\xfe', '��'),
        ('+connect steam-1', 'steam-1'),
    ])
    def test_connect_string_parsing(self, raw, expected):
        assert parse_join_connect_string(raw) == expected


# ---------------------------------------------------------------------------
# The --sdr-test window
# ---------------------------------------------------------------------------

class TestSdrTestWindow:

    def test_steam_target_from_a_connect_string(self):
        from steam_sdr_test import _steam_target
        assert _steam_target(f'steam-{HOST_ID},1.2.3.4:7777') == HOST_ID
        assert _steam_target('1.2.3.4:7777') is None
        assert _steam_target('steam-abc') is None

    def test_hosting_friends_listed_first_and_selection_kept(self, monkeypatch):
        import pygame
        import steam_sdr_test
        from steam_sdr_test import SdrTest
        friends = [{'steam_id': 1, 'name': 'Anna'}, {'steam_id': 2, 'name': 'Bob'},
                   {'steam_id': 3, 'name': 'Cid'}]
        presence = {3: f'+connect steam-{HOST_ID}'}
        monkeypatch.setattr(steam_sdr_test.steam_manager, 'get_online_friends', lambda: list(friends))
        monkeypatch.setattr(steam_sdr_test.steam_net, 'get_friend_rich_presence',
                            lambda steam_id, key: presence.get(steam_id, ''))
        monkeypatch.setattr(steam_sdr_test.steam_net, 'relay_status', lambda: (0, ''))
        monkeypatch.setattr(steam_sdr_test.steam_net, 'auth_status', lambda: (0, ''))
        pygame.init()
        try:
            tool = SdrTest(pygame.display.set_mode((1100, 700)))
            tool._refresh(100.0, force=True)
            assert [f['name'] for f in tool.friends] == ['Cid', 'Anna', 'Bob']   # hosting first
            tool.selected = 2                                                   # Bob
            presence = {2: f'+connect steam-{HOST_ID}'}                         # now Bob hosts
            monkeypatch.setattr(steam_sdr_test.steam_net, 'get_friend_rich_presence',
                                lambda steam_id, key: presence.get(steam_id, ''))
            tool._refresh(200.0)
            assert tool.friends[0]['name'] == 'Bob'
            assert tool._selected_friend()['name'] == 'Bob'                     # still selected
        finally:
            pygame.quit()

    def test_window_opens_and_quits_without_steam(self):
        import pygame
        from steam_sdr_test import SdrTest
        pygame.init()
        try:
            screen = pygame.display.set_mode((1100, 700))
            tool = SdrTest(screen, connect_target='steam-1')
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            tool.run()                      # returns once Esc is processed
            assert not tool.running
            assert any('not available' in text for text, _ in tool.lines)
        finally:
            pygame.quit()
