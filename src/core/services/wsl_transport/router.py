"""Adaptive transport router for WSL2↔Windows communication.

Discovers the runtime environment, probes available channels,
ranks them by speed, and provides the fastest path to any
host:port on the Windows side.

Does NOT know about CDP, Chrome, or any specific protocol.
It just provides connectivity.

Channels (in typical speed order):
    native   — direct localhost (non-WSL2 or mirrored networking)
    tunnel   — TCP proxy via WslTunnel / socat / netsh / ssh
    direct   — hostname.local (netsh portproxy on Windows side)
    curl     — curl.exe subprocess (HTTP only, no WS)
    bridge   — PowerShell warm bridge (WS only, managed by ps_bridge)
"""

from __future__ import annotations

import json
import logging
import time
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .environment import get_environment, WslEnvironment
from .network import resolve_host_ip, is_mirrored
from .curl_bridge import curl_get, curl_put
from .websocket import PyWebSocket

logger = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────


@dataclass
class ChannelHealth:
    """Health status for a single transport channel."""

    ok: bool = True
    last_success: float | None = None
    last_failure: float | None = None
    latency_ms: float | None = None
    consecutive_failures: int = 0

    def record_success(self, latency_ms: float) -> None:
        self.ok = True
        self.last_success = time.monotonic()
        self.latency_ms = latency_ms
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.last_failure = time.monotonic()
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.ok = False


# Channel names — order matters for tie-breaking
CHANNEL_NAMES = ("native", "tunnel", "direct", "curl")
# Channels that can do raw WebSocket (not just HTTP)
WS_CAPABLE = ("native", "tunnel", "direct")


# ── TransportRouter ───────────────────────────────────────────


class TransportRouter:
    """Adaptive transport layer for WSL2↔Windows communication.

    Discovers the runtime environment, probes available channels,
    ranks them by speed, and provides the fastest path to any
    host:port on the Windows side.
    """

    def __init__(self) -> None:
        self._env: WslEnvironment = get_environment()
        self._host_ip: str | None = resolve_host_ip()
        self._mirrored: bool = is_mirrored()
        self._lock = threading.Lock()

        # Per-port state
        self._rankings: dict[int, list[tuple[str, float]]] = {}
        self._health: dict[str, ChannelHealth] = {
            name: ChannelHealth() for name in CHANNEL_NAMES
        }
        self._probed_ports: set[int] = set()

    # ── Public API ────────────────────────────────────────────

    @property
    def environment(self) -> WslEnvironment:
        """Read-only access to detected environment."""
        return self._env

    def probe(self, port: int) -> dict[str, float | None]:
        """Probe all channels for a port. Return {channel: latency_ms}.

        Latency is None if the channel failed.
        """
        results: dict[str, float | None] = {}

        # 1. Native (localhost direct — works on non-WSL2 or mirrored)
        if not self._env.wsl2 or self._mirrored:
            lat = self._probe_http("native", f"http://localhost:{port}/json/version")
            results["native"] = lat
        else:
            results["native"] = None

        # 2. Tunnel (if active)
        tunnel = self._get_active_tunnel()
        if tunnel and tunnel.is_running and tunnel.local_port == port:
            lat = self._probe_http("tunnel", f"http://localhost:{port}/json/version")
            results["tunnel"] = lat
        else:
            results["tunnel"] = None

        # 3. Direct hostname.local (netsh portproxy)
        if self._host_ip:
            lat = self._probe_http("direct", f"http://{self._host_ip}:{port}/json/version")
            results["direct"] = lat
        else:
            results["direct"] = None

        # 4. curl.exe (HTTP only)
        if self._env.curl_exe:
            t0 = time.monotonic()
            raw = curl_get(f"http://localhost:{port}/json/version", timeout=1.0)
            if raw:
                lat = (time.monotonic() - t0) * 1000
                self._health["curl"].record_success(lat)
                results["curl"] = round(lat, 1)
            else:
                self._health["curl"].record_failure()
                results["curl"] = None
        else:
            results["curl"] = None

        # Build rankings for this port
        ranked = [
            (ch, lat) for ch, lat in results.items()
            if lat is not None
        ]
        ranked.sort(key=lambda x: x[1])

        with self._lock:
            self._rankings[port] = ranked
            # Only cache as "probed" if we found at least one channel.
            # If zero channels, re-probe next time (Chrome may not be
            # ready yet on a freshly launched port).
            if ranked:
                self._probed_ports.add(port)

        logger.info(
            "Transport probe port %d: %s",
            port,
            ", ".join(f"{ch}={lat:.0f}ms" for ch, lat in ranked) or "no channels",
        )

        return results

    def _ensure_probed(self, port: int) -> None:
        """Lazy probe on first use per port.

        If another port has already been probed, borrow its rankings
        instead of running a full probe.  All CDP ports share the same
        channel infrastructure (same portproxy rules, same host IP),
        so channel knowledge transfers across ports.
        """
        if port in self._probed_ports:
            return
        # Borrow from any already-probed port
        with self._lock:
            for _other, rankings in self._rankings.items():
                if rankings:
                    self._rankings[port] = list(rankings)
                    self._probed_ports.add(port)
                    return
        # First port ever — full probe
        self.probe(port)

    def _ranked_channels(self, port: int) -> list[str]:
        """Channels sorted by latency for this port."""
        self._ensure_probed(port)
        with self._lock:
            rankings = self._rankings.get(port, [])
        return [ch for ch, _lat in rankings]

    def is_reachable(self, port: int) -> bool:
        """Can we reach anything on this port via any channel?"""
        self._ensure_probed(port)
        with self._lock:
            return len(self._rankings.get(port, [])) > 0

    def has_fast_channel(self, port: int) -> bool:
        """True if native, direct, or tunnel is working for this port."""
        channels = self._ranked_channels(port)
        return any(ch in ("native", "tunnel", "direct") for ch in channels)

    def needs_tunnel(self, port: int = 9222) -> bool:
        """Whether a tunnel should be started for this port.

        Returns True when:
        - Running on WSL2
        - Not mirrored networking
        - No fast channel (native/direct/tunnel) found in probe results

        This checks ACTUAL PROBE RESULTS, not just DNS resolution.
        DNS can resolve (mDNS works) but the direct channel can still
        be dead (no portproxy rules).
        """
        if not self._env.wsl2:
            return False
        if self._mirrored:
            return False
        return not self.has_fast_channel(port)

    # ── Adaptive timeouts ──────────────────────────────────────

    # Timeout profiles: ~3-5x expected latency per channel
    _TIMEOUT_PROFILES: dict[str, dict[str, float | None]] = {
        "native":  {"port_check": 0.010, "http_get": 0.050, "ws_connect": 0.100},
        "tunnel":  {"port_check": 0.050, "http_get": 0.100, "ws_connect": 0.200},
        "direct":  {"port_check": 0.050, "http_get": 0.100, "ws_connect": 0.200},
        "curl":    {"port_check": 0.500, "http_get": 1.000, "ws_connect": None},
    }
    _FALLBACK_PROFILE: dict[str, float] = {
        "port_check": 0.500, "http_get": 1.000, "ws_connect": 1.000,
    }

    def get_timeout(self, operation: str, port: int = 9222) -> float:
        """Get the appropriate timeout for an operation.

        Uses the fastest known channel for this port to size the
        timeout.  Falls back to conservative values if nothing
        has been probed yet.

        Args:
            operation: ``"port_check"``, ``"http_get"``, or ``"ws_connect"``.
            port: CDP port (default 9222).

        Returns:
            Timeout in seconds.
        """
        with self._lock:
            rankings = self._rankings.get(port)
        if rankings:
            fastest_channel = rankings[0][0]  # (channel_name, latency)
            profile = self._TIMEOUT_PROFILES.get(
                fastest_channel, self._FALLBACK_PROFILE,
            )
        else:
            profile = self._FALLBACK_PROFILE

        timeout = profile.get(operation)
        if timeout is None:
            # Operation not supported on this channel
            return self._FALLBACK_PROFILE.get(operation, 1.0)
        return timeout

    # ── Tunnel selection ──────────────────────────────────────

    def select_tunnel_backend(self) -> str:
        """Pick best available tunnel backend from TUNNEL_METHODS."""
        from .tunnel_backends import TUNNEL_METHODS

        # Prefer python_proxy (always available, zero deps)
        for method_key in ["python_proxy", "socat", "ssh", "netsh"]:
            if method_key in TUNNEL_METHODS:
                cls = TUNNEL_METHODS[method_key]["class"]
                if cls.is_available():
                    return method_key
        return "python_proxy"  # fallback

    # ── Quick single-channel check ─────────────────────────────

    def quick_check(
        self, port: int, path: str = "/json/version",
    ) -> str | None:
        """HTTP GET via the single best channel only.

        For port scanning and existence checks where speed matters.
        Uses only the fastest known channel with ``port_check`` timeout
        (50ms for direct — matches the old launcher urllib behavior).

        Unlike ``http_get()`` which iterates all ranked channels,
        this makes ONE call and returns. Zero regression on the fast
        path: when direct works at 6ms, this behaves identically to
        the old ``urllib.urlopen(host_ip:port, timeout=0.05)``.

        Returns:
            Response body as string, or None on failure.
        """
        self._ensure_probed(port)
        channels = self._ranked_channels(port)
        if not channels:
            return None
        timeout = self.get_timeout("port_check", port)
        return self._http_get_via(channels[0], port, path, timeout)

    # ── HTTP routing ──────────────────────────────────────────

    def http_get(
        self, port: int, path: str, timeout: float = 2.0,
    ) -> str | None:
        """HTTP GET to Windows host:port/path via fastest channel.

        Returns raw response body as string, or None on failure.
        """
        self._ensure_probed(port)
        channels = self._ranked_channels(port)

        for ch in channels:
            result = self._http_get_via(ch, port, path, timeout)
            if result is not None:
                return result

        # All ranked channels failed — try curl as last resort
        if "curl" not in channels and self._env.curl_exe:
            result = self._http_get_via("curl", port, path, timeout)
            if result is not None:
                return result

        return None

    def http_put(
        self, port: int, path: str, timeout: float = 2.0,
    ) -> str | None:
        """HTTP PUT to Windows host:port/path via fastest channel.

        Returns raw response body as string, or None on failure.
        """
        self._ensure_probed(port)
        channels = self._ranked_channels(port)

        for ch in channels:
            result = self._http_put_via(ch, port, path, timeout)
            if result is not None:
                return result

        # Last resort: curl
        if "curl" not in channels and self._env.curl_exe:
            result = self._http_put_via("curl", port, path, timeout)
            if result is not None:
                return result

        return None

    # ── WebSocket routing ─────────────────────────────────────

    def connect_ws(
        self, ws_url: str, timeout: float = 5.0,
    ) -> PyWebSocket | None:
        """Open a WebSocket via fastest WS-capable channel.

        Rewrites the URL hostname based on preferred channel:
          native → ws://localhost:port/path
          tunnel → ws://localhost:port/path
          direct → ws://hostname.local:port/path

        Returns a connected PyWebSocket or None.
        """
        parsed = urlparse(ws_url)
        port = parsed.port
        if not port:
            raise ValueError(f"ws_url has no port: {ws_url}")
        path = parsed.path or "/"

        self._ensure_probed(port)
        channels = self._ranked_channels(port)

        for ch in channels:
            if ch not in WS_CAPABLE:
                continue
            rewritten = self._rewrite_ws_url(ws_url, ch)
            host_override = self._ws_host_override(ch, port)
            try:
                ws = PyWebSocket(
                    rewritten,
                    timeout=timeout,
                    host_override=host_override,
                )
                if ws.connected:
                    t_ms = timeout * 1000  # approximate
                    self._health[ch].record_success(t_ms)
                    logger.debug(
                        "WS connected via %s: %s", ch, rewritten,
                    )
                    return ws
            except (ConnectionError, OSError, TimeoutError) as exc:
                self._health[ch].record_failure()
                logger.debug(
                    "WS connect via %s failed: %s", ch, exc,
                )

        return None

    def rewrite_url(self, url: str, port: int) -> str:
        """Rewrite a URL to use the preferred channel for this port."""
        channels = self._ranked_channels(port)
        for ch in channels:
            if ch in WS_CAPABLE:
                return self._rewrite_ws_url(url, ch)
        return url  # no rewrite possible

    # ── Health tracking ───────────────────────────────────────

    def evict(self, port: int) -> None:
        """Forget rankings for a port (e.g., after killing Chrome)."""
        with self._lock:
            self._rankings.pop(port, None)
            self._probed_ports.discard(port)

    def status(self) -> dict:
        """Full router status for observability."""
        with self._lock:
            rankings_copy = {
                port: [(ch, lat) for ch, lat in ranked]
                for port, ranked in self._rankings.items()
            }
        return {
            "environment": {
                "wsl2": self._env.wsl2,
                "curl_exe": self._env.curl_exe,
                "powershell_exe": self._env.powershell_exe,
                "win_temp_dir": self._env.win_temp_dir,
            },
            "network": {
                "host_ip": self._host_ip,
                "mirrored": self._mirrored,
            },
            "rankings": {
                str(port): {ch: lat for ch, lat in ranked}
                for port, ranked in rankings_copy.items()
            },
            "health": {
                name: {
                    "ok": h.ok,
                    "latency_ms": h.latency_ms,
                    "consecutive_failures": h.consecutive_failures,
                }
                for name, h in self._health.items()
            },
        }

    # ── Internal helpers ──────────────────────────────────────

    def _probe_http(self, channel: str, url: str) -> float | None:
        """Probe a single HTTP endpoint. Returns latency_ms or None."""
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=0.15) as resp:
                resp.read()
            lat = (time.monotonic() - t0) * 1000
            self._health[channel].record_success(lat)
            return round(lat, 1)
        except (urllib.error.URLError, OSError, ValueError):
            self._health[channel].record_failure()
            return None

    def _get_active_tunnel(self):
        """Get the active tunnel instance, if any."""
        from .tunnel_backends import get_active_tunnel
        return get_active_tunnel()

    def _url_for_channel(self, channel: str, port: int, path: str) -> str:
        """Build the HTTP URL for a channel."""
        if channel == "native":
            return f"http://localhost:{port}{path}"
        if channel == "tunnel":
            return f"http://localhost:{port}{path}"
        if channel == "direct":
            return f"http://{self._host_ip}:{port}{path}"
        if channel == "curl":
            return f"http://localhost:{port}{path}"
        return f"http://localhost:{port}{path}"

    def _http_get_via(
        self, channel: str, port: int, path: str, timeout: float,
    ) -> str | None:
        """HTTP GET via a specific channel."""
        url = self._url_for_channel(channel, port, path)
        t0 = time.monotonic()

        if channel == "curl":
            raw = curl_get(url, timeout=timeout)
            if raw:
                lat = (time.monotonic() - t0) * 1000
                self._health["curl"].record_success(lat)
                return raw
            self._health["curl"].record_failure()
            return None

        # Native, tunnel, direct — use urllib
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            lat = (time.monotonic() - t0) * 1000
            self._health[channel].record_success(lat)
            logger.debug(
                "HTTP GET via %s: %s (%.0fms)", channel, path, lat,
            )
            return body
        except (urllib.error.URLError, OSError):
            self._health[channel].record_failure()
            return None

    def _http_put_via(
        self, channel: str, port: int, path: str, timeout: float,
    ) -> str | None:
        """HTTP PUT via a specific channel."""
        url = self._url_for_channel(channel, port, path)
        t0 = time.monotonic()

        if channel == "curl":
            raw = curl_put(url, timeout=timeout)
            if raw:
                lat = (time.monotonic() - t0) * 1000
                self._health["curl"].record_success(lat)
                return raw
            self._health["curl"].record_failure()
            return None

        # Native, tunnel, direct — use urllib
        try:
            req = urllib.request.Request(url, method="PUT")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            lat = (time.monotonic() - t0) * 1000
            self._health[channel].record_success(lat)
            return body
        except (urllib.error.URLError, OSError):
            self._health[channel].record_failure()
            return None

    def _rewrite_ws_url(self, ws_url: str, channel: str) -> str:
        """Rewrite a WS URL for the given channel."""
        parsed = urlparse(ws_url)
        port = parsed.port or 9222
        path = parsed.path or "/"

        if channel in ("native", "tunnel"):
            return f"ws://localhost:{port}{path}"
        if channel == "direct" and self._host_ip:
            return f"ws://{self._host_ip}:{port}{path}"
        return ws_url

    def _ws_host_override(self, channel: str, port: int) -> str | None:
        """Host header override for WS connections.

        Chrome rejects WS connections where the Host header doesn't
        match localhost. When connecting via direct (hostname.local),
        we override the Host header to localhost:port.
        """
        if channel == "direct":
            return f"localhost:{port}"
        return None


# ── Singleton accessor ────────────────────────────────────────

_router: TransportRouter | None = None
_router_lock = threading.Lock()


def get_router() -> TransportRouter:
    """Return the singleton TransportRouter instance.

    Thread-safe. The router is created on first call.
    """
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = TransportRouter()
    return _router
