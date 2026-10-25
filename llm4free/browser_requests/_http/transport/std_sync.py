"""Blocking, zero-dependency HTTP/1.1 transport on raw sockets.

Handles direct connections, HTTP(S) proxies and SOCKS5 via :mod:`.proxy`, plus
chunked transfer and gzip/deflate content decoding. No HTTP/2 and no browser
TLS fingerprinting — those live behind the impersonation seam.

Kept-alive connections are pooled per ``(origin, proxy, tls-settings)`` and
reused across requests on the same transport instance; a pooled socket that the
peer has already closed is transparently re-established (only ever before the
request is handed to the wire, so it is safe for every method).
"""

from __future__ import annotations

import os
import socket
import ssl
import threading
import zlib
from typing import Any, Iterator

from ..exceptions import ConnectError, HTTPError, ReadError, TimeoutError as HTTPTimeout
from ..models import Cookies, Headers, Response
from .base import CertType, ProxyInfo, RequestSpec, Timeout, VerifyType, build_ssl_context
from . import proxy as proxy_mod

_DEFAULT_PORTS = {"http": 80, "https": 443}

# Bodies that are defined to be empty regardless of Content-Length.
_NO_BODY_STATUS = frozenset({204, 304})


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


def _proxy_key(proxy: ProxyInfo | None) -> tuple | None:
    if proxy is None:
        return None
    return (proxy.scheme, proxy.host, proxy.port, proxy.username)


def _tls_key(verify: VerifyType, cert: CertType) -> tuple:
    if isinstance(verify, ssl.SSLContext):
        v: object = ("ctx", id(verify))
    elif isinstance(verify, (str, os.PathLike)):
        v = ("path", os.fspath(verify))
    else:
        v = ("bool", bool(verify))
    if cert is None:
        c: object = None
    elif isinstance(cert, (str, os.PathLike)):
        c = os.fspath(cert)
    else:
        c = tuple(os.fspath(x) if isinstance(x, (str, os.PathLike)) else x for x in cert)
    return (v, c)


class SyncStdTransport:
    """A synchronous transport with an optional keep-alive connection pool."""

    def __init__(self, *, pool: bool = True, max_connections: int = 10) -> None:
        self._pool_enabled = pool
        self._max = max(1, max_connections)
        self._pool: dict[tuple, tuple[socket.socket, Any]] = {}
        self._lock = threading.Lock()

    # --- pool helpers ---
    def _take(self, key: tuple):
        if not self._pool_enabled:
            return None
        with self._lock:
            return self._pool.pop(key, None)

    def _give(self, key: tuple, sock: socket.socket, reader) -> None:  # type: ignore[no-untyped-def]
        if not self._pool_enabled:
            _safe_close(sock)
            return
        with self._lock:
            if len(self._pool) >= self._max:
                drop_key, drop = next(iter(self._pool.items()))
                del self._pool[drop_key]
                _safe_close(drop[0])
            self._pool[key] = (sock, reader)

    def _connect(self, request: RequestSpec, *, timeout: Timeout, verify: VerifyType,
                 cert: CertType, proxy: ProxyInfo | None) -> tuple[socket.socket, Any, bool]:
        """Return ``(sock, reader, absolute_form)`` for a brand-new connection."""
        raw_sock, absolute_form = proxy_mod.open_socket(
            request.host, request.port, request.is_https, proxy, timeout
        )
        sock: socket.socket = raw_sock
        if request.is_https:
            ctx = build_ssl_context(verify, cert)
            try:
                sock = ctx.wrap_socket(raw_sock, server_hostname=request.host)
            except Exception as ex:
                raw_sock.close()
                raise HTTPError(f"TLS handshake failed for {request.host}: {ex}") from ex
        if timeout.read is not None:
            sock.settimeout(timeout.read)
        return sock, sock.makefile("rb"), absolute_form

    def _write(self, request: RequestSpec, sock: socket.socket, absolute_form: bool) -> None:
        target = request.url if absolute_form else request.path
        req_headers = request.headers.merged({"Host": _host_header(request)})
        head = f"{request.method} {target} HTTP/1.1\r\n".encode("ascii")
        head += _encode_headers(req_headers) + b"\r\n\r\n"
        sock.sendall(head)
        body = request.body
        if body is not None:
            if isinstance(body, (bytes, bytearray)):
                sock.sendall(body)
            else:
                for chunk in body:  # type: ignore[union-attr]
                    sock.sendall(chunk)

    def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: VerifyType,
        cert: CertType = None,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Response:
        key = (
            request.scheme, request.host, request.port, request.is_https,
            _proxy_key(proxy), _tls_key(verify, cert),
        )

        # 1. Acquire a socket: reuse a pooled one, and on a dead-idle reuse
        #    (failed before the request hit the wire) fall back to a fresh one.
        pooled = self._take(key)
        absolute_form = proxy is not None and not request.is_https and proxy.scheme in ("http", "https")
        if pooled is not None:
            sock, reader = pooled
            try:
                if timeout.read is not None:
                    sock.settimeout(timeout.read)
                self._write(request, sock, absolute_form)
                reused = True
            except (BrokenPipeError, ConnectionResetError, OSError) as ex:
                # Socket was stale; the peer never received our request, so
                # reconnecting is safe for any method.
                _safe_close(sock)
                sock, reader, absolute_form = self._connect(
                    request, timeout=timeout, verify=verify, cert=cert, proxy=proxy
                )
                try:
                    self._write(request, sock, absolute_form)
                except (BrokenPipeError, ConnectionResetError, OSError) as ex2:
                    _safe_close(sock)
                    raise ConnectError(f"Failed sending request: {ex2}") from ex2
                reused = False
        else:
            sock, reader, absolute_form = self._connect(
                request, timeout=timeout, verify=verify, cert=cert, proxy=proxy
            )
            reused = False
            try:
                self._write(request, sock, absolute_form)
            except (BrokenPipeError, ConnectionResetError, OSError) as ex:
                _safe_close(sock)
                raise ConnectError(f"Failed sending request: {ex}") from ex

        # 2. Read the response head. A reused socket that yields nothing here
        #    means the server closed an idle connection mid-send; do not retry.
        try:
            status_line = reader.readline()
            if not status_line:
                raise ReadError("Server closed connection before sending a status line")
            code, reason, version = _parse_status(status_line)
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

        # 3. Body framing.
        encoding = (resp_headers.get("content-encoding") or "").lower()
        chunked = "chunked" in (resp_headers.get("transfer-encoding") or "").lower()
        cl = resp_headers.get("content-length")
        no_body = request.method == "HEAD" or code in _NO_BODY_STATUS
        if no_body:
            chunked, cl = False, None
        read_until_close = not chunked and cl is None and not no_body

        cookies = Cookies()
        for raw in resp_headers.get_all("set-cookie"):
            cookies.extract_set_cookie([raw])

        keep_alive = _is_keep_alive(resp_headers, code, version, read_until_close)

        if stream:
            # Streaming connections are handed back to the pool only once the
            # iterator is fully consumed; simpler and safer to close them.
            body_iter = _iter_stream(sock, reader, chunked, cl, encoding, close=True)
            content = None
        else:
            # Buffered read shares the framing/decompression path; read exactly
            # the body so the socket is positioned for a keep-alive reuse.
            content = b"".join(_iter_stream(sock, reader, chunked, cl, encoding, close=False))
            body_iter = None
            if keep_alive:
                self._give(key, sock, reader)
            else:
                _safe_close(sock)

        return Response(
            status_code=code,
            reason=reason,
            headers=resp_headers,
            url=request.url,
            cookies=cookies,
            content=content,
            stream=body_iter,
        )

    def close(self) -> None:
        with self._lock:
            for _key, (sock, _reader) in self._pool.items():
                _safe_close(sock)
            self._pool.clear()


def _is_keep_alive(headers: Headers, status: int, version: str, read_until_close: bool) -> bool:
    if read_until_close:
        return False
    conn = (headers.get("connection") or "").lower()
    if "close" in conn:
        return False
    if "1.1" in version:
        # HTTP/1.1 defaults to keep-alive unless the server says otherwise.
        pass
    elif "1.0" in version:
        # HTTP/1.0 only stays open when the server explicitly opts in.
        return "keep-alive" in conn
    if status in (408, 503):
        return False
    return True


def _parse_status(line: bytes) -> tuple[int, str, str]:
    text = line.decode("latin-1").strip()
    parts = text.split(" ", 2)
    if len(parts) < 2:
        raise ReadError(f"Malformed status line: {text!r}")
    version = parts[0]
    try:
        code = int(parts[1])
    except ValueError as ex:
        raise ReadError(f"Malformed status line: {text!r}") from ex
    reason = parts[2] if len(parts) > 2 else ""
    return code, reason, version


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


def _read_chunk(reader) -> bytes:  # type: ignore[no-untyped-def]
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


def _iter_stream(sock, reader, chunked: bool, cl, encoding: str, close: bool = True) -> Iterator[bytes]:  # type: ignore[no-untyped-def]
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
        if close:
            _safe_close(sock)


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
