"""Zero-dependency RFC 6455 WebSocket client for the native CDP backend.

Implemented directly over :mod:`asyncio` streams — no ``websockets`` /
``aiohttp`` / ``sockjs`` dependency — which keeps the resident memory of a
single connection in the low hundreds of kilobytes and avoids an extra event
loop integration layer.

Only the subset needed for the Chrome DevTools Protocol is implemented:
* client handshake (``Upgrade: websocket``),
* masked text frames with fragmentation support (large CDP replies),
* server ping/pong handling and clean close handling.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import struct
import time
from typing import Optional

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# Op codes
_OP_TEXT = 0x1
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA


class WebSocketError(Exception):
    """Raised on protocol violations or an unexpectedly closed socket."""


class WsConnection:
    """A minimal client-side text WebSocket (RFC 6455) over asyncio streams."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._closed = False

    # ------------------------------------------------------------------ #
    # Handshake
    # ------------------------------------------------------------------ #
    async def connect(self, timeout: float = 10.0, path: str = "/") -> None:
        """Perform the HTTP Upgrade handshake with the peer."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout
        )
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._writer.write(request.encode("ascii"))
        await self._writer.drain()

        # Read response headers until the blank line.
        try:
            headers = await asyncio.wait_for(self._read_headers(), timeout)
        except asyncio.TimeoutError as e:
            raise WebSocketError("websocket handshake timed out") from e
        status_line = next(iter(headers), "")
        if " 101" not in status_line:
            raise WebSocketError(f"websocket upgrade refused: {status_line!r}")
        accept = ""
        for line in headers:
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
                break
        expected = base64.b64encode(
            hashlib.sha1((key + _GUID).encode("ascii")).digest()
        ).decode("ascii")
        if accept != expected:
            raise WebSocketError("websocket handshake: bad Sec-WebSocket-Accept")

    async def _read_headers(self) -> list:
        headers: list = []
        reader = self._reader
        while reader is not None:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            headers.append(line.decode("latin-1").rstrip("\r\n"))
        return headers

    # ------------------------------------------------------------------ #
    # Framing
    # ------------------------------------------------------------------ #
    async def send_text(self, text: str) -> None:
        """Send one unfragmented masked text frame."""
        if self._writer is None or self._closed:
            raise WebSocketError("websocket is closed")
        payload = text.encode("utf-8")
        header = bytearray()
        header.append(0x80 | _OP_TEXT)  # FIN + text
        length = len(payload)
        mask = os.urandom(4)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        header += mask
        self._writer.write(bytes(header))
        if payload:
            # XOR in 4-byte-sized chunks pipelined with the mask (fast path
            # when the payload length is a multiple of 4 is negligible here;
            # CDP commands are small).
            masked = bytearray(payload)
            for i in range(len(masked)):
                masked[i] ^= mask[i & 3]
            self._writer.write(bytes(masked))
        else:
            # zero-length payloads gain nothing from the mask copy
            self._writer.write(b"")
        await self._writer.drain()

    async def _read_exact(self, n: int, deadline: float) -> bytes:
        reader = self._reader
        if reader is None:
            raise WebSocketError("websocket is closed")
        data = await reader.read(n)
        while len(data) < n:
            if not data:
                raise WebSocketError("connection closed by peer")
            chunk = await reader.read(n - len(data))
            data += chunk
        return data

    async def _read_frame(self, deadline: float) -> tuple:
        """Read one frame. Returns ``(fin, opcode, payload_bytes)``."""
        head = await self._read_exact(2, deadline)
        fin = bool(head[0] & 0x80)
        opcode = head[0] & 0x0F
        masked = bool(head[1] & 0x80)
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", await self._read_exact(2, deadline))[0]
        elif length == 127:
            length = struct.unpack(">Q", await self._read_exact(8, deadline))[0]
        mask = await self._read_exact(4, deadline) if masked else b""
        payload = await self._read_exact(length, deadline) if length else b""
        if mask:
            payload = bytearray(payload)
            for i in range(len(payload)):
                payload[i] ^= mask[i & 3]
            payload = bytes(payload)
        return fin, opcode, payload

    async def recv_text(self, timeout: float = 30.0) -> str:
        """Receive the next complete text message, handling control frames.

        Returns:
            The decoded UTF-8 message.

        Raises:
            WebSocketError: On close frame or socket failure.
            asyncio.TimeoutError: When ``timeout`` elapses.
        """
        deadline = time.monotonic() + timeout
        fragments: list = []
        while True:
            remaining = max(0.001, deadline - time.monotonic())
            fin, opcode, payload = await self._read_frame(deadline)
            if opcode == _OP_TEXT:
                fragments.append(payload)
                if fin:
                    return b"".join(fragments).decode("utf-8", "replace")
            elif opcode == 0x0:  # continuation
                fragments.append(payload)
                if fin:
                    if not fragments:
                        raise WebSocketError("unexpected continuation frame")
                    data = b"".join(fragments)
                    fragments = []
                    return data.decode("utf-8", "replace")
            elif opcode == _OP_PING:
                await self._send_control(_OP_PONG, payload)
            elif opcode == _OP_PONG:
                continue
            elif opcode == _OP_CLOSE:
                try:
                    await self._send_control(_OP_CLOSE, payload[:2])
                except Exception:
                    pass
                raise WebSocketError("received close frame")
            else:
                raise WebSocketError(f"unsupported frame opcode {opcode}")

    async def _send_control(self, opcode: int, payload: bytes = b"") -> None:
        if self._writer is None or self._closed:
            return
        frame = bytearray()
        frame.append(0x80 | opcode)
        frame.append(0x80 | len(payload))
        frame += os.urandom(4)
        masked = bytearray(payload)
        mask = frame[2:6]
        for i in range(len(masked)):
            masked[i] ^= mask[i & 3]
        frame += masked
        try:
            self._writer.write(bytes(frame))
            await self._writer.drain()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Teardown
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        """Send a close frame (best effort) and drop the TCP connection."""
        self._closed = True
        try:
            if self._writer is not None:
                await self._send_control(_OP_CLOSE, b"\x03\xe8")
                try:
                    await asyncio.wait_for(self._writer.drain(), 1.0)
                except Exception:
                    pass
        finally:
            if self._writer is not None:
                try:
                    self._writer.close()
                except Exception:
                    pass
                self._writer = None
            self._reader = None
