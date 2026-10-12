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
from network_config import (DEFAULT_PORT, UPNP_DISCOVERY_TIMEOUT, UPNP_DESCRIPTION,
                            UPNP_DISCOVERY_ATTEMPTS)

logger = get_logger(__name__)

# Check for miniupnpc at import time. Auto-installing packages at runtime was
# removed because it runs pip inside the game process without user consent,
# performs no integrity verification, and is unexpected behaviour for a game.
# Install miniupnpc manually if internet play is desired: pip install miniupnpc
try:
    import miniupnpc
    UPNP_AVAILABLE = True
except ImportError:
    UPNP_AVAILABLE = False
    logger.warning(
        "miniupnpc is not installed — UPnP port forwarding won't be available. "
        "Install it manually with: pip install miniupnpc"
    )

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
        # True once the background setup is completely done, public-IP lookup included.
        # status turns FAILED before that lookup runs, so is_complete() reads this flag:
        # a Steam invite sent in between carried only the LAN address.
        self._finished: bool = False

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
            self._run_setup()
        finally:
            # Done for good (success or failure, public IP looked up) - see is_complete()
            self._finished = True

    def _discover(self, upnp):
        """
        Search for the router, up to UPNP_DISCOVERY_ATTEMPTS times.

        Returns:
            The number of devices found, 0 / None when no router answered.
        """
        devices_found = None
        for attempt in range(1, UPNP_DISCOVERY_ATTEMPTS + 1):
            try:
                devices_found = upnp.discover()
            except Exception as e:
                # miniupnpc 2.3 raises instead of returning 0 when no router answers -
                # with its text for "no error", so the log read "UPnP setup failed: Success"
                logger.warning(f"UPnP: no router answered the discovery, attempt {attempt}/"
                               f"{UPNP_DISCOVERY_ATTEMPTS} (miniupnpc: {e})")
                devices_found = None
            else:
                if devices_found == 0:
                    logger.warning(f"UPnP: No IGD devices found, attempt {attempt}/"
                                   f"{UPNP_DISCOVERY_ATTEMPTS}")
            if devices_found:
                break
        return devices_found

    def _run_setup(self) -> None:
        """Discovery, port mapping and public-IP detection (body of _setup_worker)."""
        # Guard against miniupnpc being absent — UPNP_AVAILABLE is set at module
        # load time. We do not attempt to install packages at runtime (security).
        if not UPNP_AVAILABLE:
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
            devices_found = self._discover(upnp)

            if not devices_found:
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

    def get_join_addresses(self, local_ip: str) -> list:
        """
        Every address a player might reach this host at, best first (Steam invites
        carry them all; the joining PC tries each in turn).

        With a mapped port the public IP works from anywhere, so it goes first. Without
        one the LAN address is the one known to work (same network); the public IP is
        still listed in case the host forwarded port 7777 by hand.
        """
        if self.status == UPNP_STATUS_SUCCESS and self.public_ip:
            addresses = [self.public_ip, local_ip]
        else:
            addresses = [local_ip, self.public_ip]
        # Drop unknown / duplicate entries, keep the order
        result = []
        for address in addresses:
            if address and address not in result:
                result.append(address)
        return result

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
        """Check if setup has finished (success or failure), public-IP lookup included."""
        return self._finished
