"""Raw WebSocket client — protocol-agnostic, zero dependencies.

Implements RFC 6455 just enough for text-only WebSocket communication:
client masking, multi-frame receive, close/ping handling.

This is a transport primitive. It does NOT know about CDP, Chrome,
or any higher-level protocol. ``CdpSession`` wraps it for CDP framing.

Uses only Python's ``socket`` module — no external dependencies.
"""

from __future__ import annotations


class PyWebSocket:
    """Minimal Python-native WebSocket client (text-only, for CDP).

    Implements RFC 6455 just enough for CDP: text frames,
    client masking, multi-frame receive, close/ping handling.
    No external dependencies — uses only Python's ``socket`` module.
    """

    __slots__ = ("_sock", "_connected")

    def __init__(self, ws_url: str, timeout: float = 5.0, host_override: str | None = None):
        import socket
        import base64
        import os
        from urllib.parse import urlparse

        parsed = urlparse(ws_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80
        path = parsed.path or "/"

        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._connected = False  # set True after successful handshake

        # WebSocket upgrade handshake
        # host_override lets us spoof Host: localhost when connecting
        # through netsh portproxy (Chrome rejects non-localhost WS)
        header_host = host_override or f"{host}:{port}"
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {header_host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        self._sock.sendall(handshake.encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("WS handshake: connection closed")
            resp += chunk

        status_line = resp.split(b"\r\n")[0]
        if b"101" not in status_line:
            raise ConnectionError(
                f"WS upgrade failed: {status_line.decode(errors='replace')}"
            )

        self._connected = True

    def send(self, text: str) -> None:
        """Send a text frame (client-masked per RFC 6455)."""
        import os

        data = text.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray()
        header.append(0x81)  # FIN + TEXT opcode

        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))

        header.extend(mask)
        masked = bytearray(length)
        for i in range(length):
            masked[i] = data[i] ^ mask[i % 4]
        self._sock.sendall(bytes(header) + bytes(masked))

    @property
    def connected(self) -> bool:
        """True if the WebSocket is alive and handshake completed."""
        if not self._connected:
            return False
        # Check if socket is still open (non-blocking peek)
        import select
        try:
            # select with 0 timeout = poll: ready-to-read means either
            # data waiting or socket closed. We can't distinguish without
            # recv, so we just check fileno() is valid.
            self._sock.fileno()
            return True
        except Exception:
            self._connected = False
            return False

    def recv(self, timeout: float | None = None) -> str:
        """Receive a complete text message (handles continuation frames).

        If *timeout* is given, temporarily sets the socket timeout for
        this receive operation, then restores the original timeout.
        If *timeout* is None, uses the socket's existing timeout.
        """
        old_timeout = self._sock.gettimeout()
        if timeout is not None:
            self._sock.settimeout(timeout)
        fragments = []
        while True:
            hdr = self._recv_exact(2)
            fin = hdr[0] & 0x80
            opcode = hdr[0] & 0x0F
            has_mask = hdr[1] & 0x80
            length = hdr[1] & 0x7F

            if length == 126:
                length = int.from_bytes(self._recv_exact(2), "big")
            elif length == 127:
                length = int.from_bytes(self._recv_exact(8), "big")

            mask_key = self._recv_exact(4) if has_mask else None
            payload = self._recv_exact(length)

            if mask_key:
                payload = bytearray(payload)
                for i in range(len(payload)):
                    payload[i] ^= mask_key[i % 4]
                payload = bytes(payload)

            if opcode == 0x08:
                self._connected = False
                raise ConnectionError("WS peer sent close frame")
            if opcode == 0x09:
                self._send_pong(payload)
                continue
            if opcode == 0x0A:
                continue

            fragments.append(payload)
            if fin:
                break

        if timeout is not None:
            self._sock.settimeout(old_timeout)
        return b"".join(fragments).decode("utf-8")

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("WS connection lost")
            buf.extend(chunk)
        return bytes(buf)

    def _send_pong(self, payload: bytes) -> None:
        import os
        mask = os.urandom(4)
        header = bytearray([0x8A])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        else:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        header.extend(mask)
        masked = bytearray(length)
        for i in range(length):
            masked[i] = payload[i] ^ mask[i % 4]
        self._sock.sendall(bytes(header) + bytes(masked))

    def close(self) -> None:
        self._connected = False
        try:
            self._sock.sendall(b"\x88\x80" + b"\x00\x00\x00\x00")
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass
