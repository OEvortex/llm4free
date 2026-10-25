"""Blocking, zero-dependency HTTP/1.1 transport on raw sockets.

Handles direct connections, HTTP(S) proxies and SOCKS5 via :mod:`.proxy`, plus
chunked transfer and gzip/deflate content decoding. No HTTP/2 and no browser
TLS fingerprinting — those live behind the impersonation seam.
"""

from __future__ import annotations

import socket
import ssl
import zlib
from typing import Iterator

from ..exceptions import ConnectError, HTTPError, ReadError, TimeoutError as HTTPTimeout
from ..models import Cookies, Headers, Response
from .base import ProxyInfo, RequestSpec, Timeout, build_ssl_context
from . import proxy as proxy_mod

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _host_header(spec: RequestSpec) -> str:
    if spec.port == _DEFAULT_PORTS.get(spec.scheme):
        return spec.host
    return f"{spec.host}:{spec.port}"


def _encode_headers(headers: Headers) -> bytes:
    lines = []
    for name, value in headers.items():
        lines.append(f"{name}: {value}".encode("latin-1", "replace"))
    return b"\r\n".join(lines)


def _decompress_factory(encoding: str):
    if encoding == "gzip":
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif encoding == "deflate":
        # Try raw-zlib auto-detect; many servers send gzip-wrapped deflate.
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        except zlib.error:  # pragma: no cover
            d = zlib.decompressobj()
    else:
        return None
    return d


class SyncStdTransport:
    """A stateless synchronous transport."""

    def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: bool | ssl.SSLContext,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Response:
        raw_sock, absolute_form = proxy_mod.open_socket(
            request.host, request.port, request.is_https, proxy, timeout
        )

        sock: socket.socket = raw_sock
        if request.is_https:
            ctx = build_ssl_context(verify)
            try:
                sock = ctx.wrap_socket(raw_sock, server_hostname=request.host)
            except Exception as ex:
                raw_sock.close()
                raise HTTPError(f"TLS handshake failed for {request.host}: {ex}") from ex

        if timeout.read is not None:
            sock.settimeout(timeout.read)

        # --- serialize request ---
        target = request.url if absolute_form else request.path
        req_headers = request.headers.merged({"Host": _host_header(request)})
        head = f"{request.method} {target} HTTP/1.1\r\n".encode("ascii")
        head += _encode_headers(req_headers) + b"\r\n\r\n"

        try:
            sock.sendall(head)
            body = request.body
            if body is not None:
                if isinstance(body, (bytes, bytearray)):
                    sock.sendall(body)
                else:
                    for chunk in body:  # type: ignore[union-attr]
                        sock.sendall(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError) as ex:
            sock.close()
            raise ConnectError(f"Failed sending request: {ex}") from ex

        reader = sock.makefile("rb")
        try:
            status_line = reader.readline()
            if not status_line:
                raise ReadError("Server closed connection before sending a status line")
            code, reason = _parse_status(status_line)
            resp_headers = _parse_headers(reader)
        except HTTPTimeout:
            _safe_close(sock)
            raise
        except TimeoutError as ex:
            _safe_close(sock)
            raise HTTPTimeout(f"Timed out reading response headers: {ex}") from ex
        except ReadError:
            _safe_close(sock)
            raise
        except OSError as ex:
            _safe_close(sock)
            raise ReadError(f"Failed reading response headers: {ex}") from ex

        # --- body framing ---
        encoding = (resp_headers.get("content-encoding") or "").lower()
        chunked = (resp_headers.get("transfer-encoding") or "").lower().find("chunked") != -1
        cl = resp_headers.get("content-length")

        cookies = Cookies()
        for raw in resp_headers.get_all("set-cookie"):
            cookies.extract_set_cookie([raw])

        if stream:
            body_iter = _iter_stream(sock, reader, chunked, cl, encoding)
        else:
            try:
                data = _read_all(sock, reader, chunked, cl, encoding)
            finally:
                _safe_close(sock)
            body_iter = None
            content = data

        resp = Response(
            status_code=code,
            reason=reason,
            headers=resp_headers,
            url=request.url,
            cookies=cookies,
            content=None if stream else content,
            stream=body_iter,
        )
        return resp

    def close(self) -> None:
        return None


def _parse_status(line: bytes) -> tuple[int, str]:
    text = line.decode("latin-1").strip()
    parts = text.split(" ", 2)
    if len(parts) < 2:
        raise ReadError(f"Malformed status line: {text!r}")
    try:
        return int(parts[1]), parts[2] if len(parts) > 2 else ""
    except ValueError as ex:
        raise ReadError(f"Malformed status line: {text!r}") from ex


def _parse_headers(reader) -> Headers:  # type: ignore[no-untyped-def]
    items: list[tuple[str, str]] = []
    while True:
        line = reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break
        decoded = line.decode("latin-1").rstrip("\r\n")
        name, _, value = decoded.partition(":")
        items.append((name.strip(), value.strip()))
    return Headers(items)


def _read_chunk(reader) -> bytes:
    size_line = reader.readline()
    if not size_line:
        raise ReadError("Connection closed mid-chunked-body")
    try:
        size = int(size_line.split(b";")[0].strip(), 16)
    except ValueError as ex:
        raise ReadError(f"Bad chunk size line: {size_line!r}") from ex
    if size == 0:
        # consume trailers until blank line
        while True:
            t = reader.readline()
            if t in (b"\r\n", b"\n", b""):
                break
        return b""
    data = _read_exactly(reader, size)
    reader.readline()  # trailing CRLF
    return data


def _read_exactly(reader, n: int) -> bytes:  # type: ignore[no-untyped-def]
    buf = bytearray()
    while len(buf) < n:
        chunk = reader.read(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _iter_stream(sock, reader, chunked: bool, cl, encoding: str) -> Iterator[bytes]:  # type: ignore[no-untyped-def]
    dec = _decompress_factory(encoding)
    try:
        if chunked:
            while True:
                raw = _read_chunk(reader)
                if not raw:
                    break
                yield _feed(dec, raw)
            if dec:
                tail = dec.flush()
                if tail:
                    yield tail
        elif cl is not None:
            remaining = int(cl)
            while remaining > 0:
                raw = reader.read(min(remaining, 65536))
                if not raw:
                    break
                remaining -= len(raw)
                yield _feed(dec, raw)
            if dec:
                tail = dec.flush()
                if tail:
                    yield tail
        else:  # read-until-close
            while True:
                raw = reader.read(65536)
                if not raw:
                    break
                yield _feed(dec, raw)
            if dec:
                tail = dec.flush()
                if tail:
                    yield tail
    except (TimeoutError, OSError) as ex:
        raise HTTPTimeout(f"Read timed out during stream: {ex}") from ex
    finally:
        _safe_close(sock)


def _read_all(sock, reader, chunked: bool, cl, encoding: str) -> bytes:  # type: ignore[no-untyped-def]
    chunks = list(_iter_stream(sock, reader, chunked, cl, encoding))
    return b"".join(chunks)


def _feed(dec, raw: bytes) -> bytes:  # type: ignore[no-untyped-def]
    if dec is None:
        return raw
    return dec.decompress(raw)


def _safe_close(sock) -> None:  # type: ignore[no-untyped-def]
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


__all__ = ["SyncStdTransport"]
