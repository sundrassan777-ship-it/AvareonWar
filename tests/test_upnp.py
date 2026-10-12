# -*- coding: utf-8 -*-
"""
UPnP setup (network/upnp.py) without a network: miniupnpc is replaced by a stand-in.

miniupnpc 2.3 raises an exception whose text is "Success" from discover() when no
router answers, instead of returning 0 devices. The setup reported that as
"UPnP setup failed: Success"; it is the ordinary "no UPnP router" case.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import network.upnp as upnp  # noqa: E402


def manager_with(monkeypatch, discover):
    """A UPnPManager whose miniupnpc.UPnP().discover() is `discover` (no public-IP lookup)."""
    class FakeUPnP:
        discoverdelay = 0

        def discover(self):
            return discover()
    monkeypatch.setattr(upnp, 'UPNP_AVAILABLE', True)
    monkeypatch.setattr(upnp, 'miniupnpc', SimpleNamespace(UPnP=FakeUPnP), raising=False)
    manager = upnp.UPnPManager()
    monkeypatch.setattr(manager, '_detect_public_ip', lambda: None)
    return manager


def test_no_router_answering_is_reported_as_no_router(monkeypatch):
    def discover():
        raise Exception("Success")
    manager = manager_with(monkeypatch, discover)
    manager._setup_worker()
    assert manager.status == upnp.UPNP_STATUS_FAILED
    assert manager.error_message == "No UPnP router found"
    assert manager.get_status_text() == "LAN only (forward port 7777 for internet)"


def test_zero_devices_is_still_no_router(monkeypatch):
    manager = manager_with(monkeypatch, lambda: 0)
    manager._setup_worker()
    assert manager.status == upnp.UPNP_STATUS_FAILED
    assert manager.error_message == "No UPnP router found"


def test_discovery_is_retried(monkeypatch):
    """Some routers miss the first search request - a second one is sent."""
    calls = []

    def discover():
        calls.append(1)
        if len(calls) == 1:
            raise Exception("Success")                 # no answer the first time
        return 1
    manager = manager_with(monkeypatch, discover)
    monkeypatch.setattr(upnp, 'UPNP_DISCOVERY_ATTEMPTS', 2)
    found = manager._discover(upnp.miniupnpc.UPnP())
    assert found == 1 and len(calls) == 2


def test_discovery_gives_up_after_the_last_attempt(monkeypatch):
    calls = []

    def discover():
        calls.append(1)
        return 0
    manager = manager_with(monkeypatch, discover)
    monkeypatch.setattr(upnp, 'UPNP_DISCOVERY_ATTEMPTS', 2)
    manager._setup_worker()
    assert len(calls) == 2
    assert manager.status == upnp.UPNP_STATUS_FAILED


def test_not_complete_until_the_public_ip_lookup_is_done(monkeypatch):
    """status turns FAILED before the public-IP lookup; a Steam invite sent in between
    carried only the LAN address. is_complete() waits for the lookup."""
    seen_during_lookup = []
    manager = manager_with(monkeypatch, lambda: 0)

    def lookup():
        seen_during_lookup.append((manager.status, manager.is_complete()))
        manager.public_ip = '212.20.115.148'
    monkeypatch.setattr(manager, '_detect_public_ip', lookup)
    assert not manager.is_complete()
    manager._setup_worker()
    assert seen_during_lookup == [(upnp.UPNP_STATUS_FAILED, False)]
    assert manager.is_complete()


def test_complete_even_when_setup_crashes(monkeypatch):
    manager = manager_with(monkeypatch, lambda: 0)

    def boom():
        raise RuntimeError("lookup broke")
    monkeypatch.setattr(manager, '_detect_public_ip', boom)
    try:
        manager._setup_worker()
    except RuntimeError:
        pass
    assert manager.is_complete()


def test_join_addresses_order():
    manager = upnp.UPnPManager()
    # Nothing known yet: only the LAN address
    assert manager.get_join_addresses('192.168.18.5') == ['192.168.18.5']
    # No UPnP, public IP looked up: LAN first (it is the one known to work)
    manager.status = upnp.UPNP_STATUS_FAILED
    manager.public_ip = '212.20.115.148'
    assert manager.get_join_addresses('192.168.18.5') == ['192.168.18.5', '212.20.115.148']
    # Port mapped: the public address works from anywhere, so it goes first
    manager.status = upnp.UPNP_STATUS_SUCCESS
    assert manager.get_join_addresses('192.168.18.5') == ['212.20.115.148', '192.168.18.5']
