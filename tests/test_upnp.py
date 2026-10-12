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
