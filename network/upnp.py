"""
UPnP port forwarding and public IP detection for internet multiplayer.

Automates port mapping via UPnP IGD protocol so the host doesn't need
to manually configure their router. Falls back gracefully to LAN-only
if UPnP is unavailable.

Dependencies: miniupnpc (pip install miniupnpc) — optional, game works without it.
"""

import threading
import atexit
import urllib.request
import json
from typing import Optional

from utils.logger import get_logger
from network_config import DEFAULT_PORT, UPNP_DISCOVERY_TIMEOUT, UPNP_DESCRIPTION

logger = get_logger(__name__)

# UPnP status constants — polled by UI each frame
UPNP_STATUS_IDLE = "idle"
UPNP_STATUS_DISCOVERING = "discovering"
UPNP_STATUS_MAPPING = "mapping"
UPNP_STATUS_SUCCESS = "success"
UPNP_STATUS_FAILED = "failed"

# Public IP detection endpoints (tried in order, first success wins)
PUBLIC_IP_APIS = [
    ("https://api.ipify.org?format=json", "ip"),
    ("https://api.my-ip.io/v2/ip.json", "ip"),
]

class UPnPManager:
    """
    Manages UPnP port mapping lifecycle and public IP detection.

    Thread-safe. Discovery and mapping run in a background thread
    so the UI never freezes. Status can be polled from the main thread.

    Lifecycle:
        1. setup_async(port, local_ip) — starts background thread
        2. Poll status / public_ip from main thread
        3. cleanup() — removes port mapping (also registered with atexit)
    """

    def __init__(self):
        self.status: str = UPNP_STATUS_IDLE
        self.public_ip: Optional[str] = None
        self.error_message: str = ""
        self.port_mapped: bool = False

        self._port: int = DEFAULT_PORT
        self._local_ip: str = ""
        self._upnp = None  # miniupnpc.UPnP instance
        self._thread: Optional[threading.Thread] = None
        self._cleaned_up: bool = False
        self._lock = threading.Lock()

    def setup_async(self, port: int, local_ip: str) -> None:
        """
        Start UPnP discovery and port mapping in a background thread.
        Also detects public IP. Non-blocking.
        """
        self._port = port
        self._local_ip = local_ip
        self.status = UPNP_STATUS_DISCOVERING

        self._thread = threading.Thread(target=self._setup_worker, daemon=True)
        self._thread.start()

        # Register atexit handler for crash-safe cleanup
        atexit.register(self.cleanup)

    def _setup_worker(self) -> None:
        """Background worker: discover IGD, create mapping, detect public IP."""
        try:
            import miniupnpc
        except ImportError:
            # Auto-install miniupnpc if missing
            logger.info("miniupnpc not found — attempting auto-install...")
            try:
                import subprocess
                import sys
                subprocess.check_call(
                    [sys.executable, '-m', 'pip', 'install', 'miniupnpc'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                import miniupnpc
                logger.info("miniupnpc auto-installed successfully")
            except Exception as install_err:
                logger.warning(f"Could not auto-install miniupnpc: {install_err}")
                self.status = UPNP_STATUS_FAILED
                self.error_message = "UPnP library not available"
                self._detect_public_ip()
                return

        try:
            # Phase 1: Discover UPnP IGD device
            self.status = UPNP_STATUS_DISCOVERING
            logger.info("UPnP: Discovering IGD device...")

            upnp = miniupnpc.UPnP()
            upnp.discoverdelay = UPNP_DISCOVERY_TIMEOUT
            devices_found = upnp.discover()

            if devices_found == 0:
                logger.warning("UPnP: No IGD devices found")
                self.status = UPNP_STATUS_FAILED
                self.error_message = "No UPnP router found"
                self._detect_public_ip()
                return

            upnp.selectigd()
            logger.info(f"UPnP: Found IGD — external IP: {upnp.externalipaddress()}")

            # Phase 2: Create port mapping
            self.status = UPNP_STATUS_MAPPING
            logger.info(f"UPnP: Mapping port {self._port} -> {self._local_ip}:{self._port}")

            result = upnp.addportmapping(
                self._port,        # External port
                'TCP',             # Protocol
                self._local_ip,    # Internal IP
                self._port,        # Internal port
                UPNP_DESCRIPTION,  # Description shown in router admin
                ''                 # Remote host (empty = any)
            )

            if result:
                self._upnp = upnp
                self.port_mapped = True
                self.status = UPNP_STATUS_SUCCESS
                # Get public IP directly from IGD — most reliable
                self.public_ip = upnp.externalipaddress()
                logger.info(f"UPnP: Port {self._port} mapped successfully, public IP: {self.public_ip}")
            else:
                logger.warning("UPnP: addportmapping returned False")
                self.status = UPNP_STATUS_FAILED
                self.error_message = "Router rejected port mapping"
                self._detect_public_ip()

        except Exception as e:
            logger.warning(f"UPnP setup failed: {e}")
            self.status = UPNP_STATUS_FAILED
            self.error_message = str(e)
            self._detect_public_ip()

    def _detect_public_ip(self) -> None:
        """Detect public IP via HTTP API (fallback when UPnP unavailable)."""
        for api_url, key in PUBLIC_IP_APIS:
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "AvareonWar/1.0"})
                with urllib.request.urlopen(req, timeout=3) as response:
                    data = json.loads(response.read().decode())
                    ip = data.get(key, "").strip()
                    if ip:
                        self.public_ip = ip
                        logger.info(f"Public IP detected: {ip} (via {api_url})")
                        return
            except Exception as e:
                logger.debug(f"Public IP API {api_url} failed: {e}")
                continue

        logger.warning("Could not detect public IP from any API")

    def cleanup(self) -> None:
        """
        Remove UPnP port mapping. Safe to call multiple times.
        Called automatically via atexit, and explicitly on server stop.
        """
        with self._lock:
            if self._cleaned_up:
                return
            self._cleaned_up = True

        if self.port_mapped and self._upnp is not None:
            try:
                self._upnp.deleteportmapping(self._port, 'TCP')
                self.port_mapped = False
                logger.info(f"UPnP: Port {self._port} mapping removed")
            except Exception as e:
                logger.warning(f"UPnP cleanup failed: {e}")

        try:
            atexit.unregister(self.cleanup)
        except Exception:
            pass

    def get_display_ip(self, local_ip: str) -> str:
        """Return public IP if UPnP succeeded, otherwise local IP."""
        if self.status == UPNP_STATUS_SUCCESS and self.public_ip:
            return self.public_ip
        return local_ip

    def get_status_text(self) -> str:
        """Get a human-readable status string for UI display."""
        if self.status == UPNP_STATUS_DISCOVERING:
            return "Setting up internet access..."
        elif self.status == UPNP_STATUS_MAPPING:
            return "Configuring router..."
        elif self.status == UPNP_STATUS_SUCCESS:
            return "Internet play ready!"
        elif self.status == UPNP_STATUS_FAILED:
            return "LAN only (forward port 7777 for internet)"
        return ""

    def is_complete(self) -> bool:
        """Check if setup has finished (success or failure)."""
        return self.status in (UPNP_STATUS_SUCCESS, UPNP_STATUS_FAILED)
