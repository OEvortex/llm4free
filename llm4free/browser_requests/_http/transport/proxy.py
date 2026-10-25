"""Pure-stdlib socket establishment for direct, HTTP(S)-proxy and SOCKS5 paths.

Every helper returns a *connected* socket plus a flag telling the caller whether
the HTTP request line should use the absolute-form URL (plain HTTP through an
HTTP proxy) or the origin-form path (everything else, including tunnels).
"""

from __future__ import annotations

import socket
import struct

from ..exceptions import ConnectError, ProxyError
from .base import ProxyInfo, Timeout

# --- SOCKS5 constants -------------------------------------------------------
_SOCKS5_VERSION = 0x05
_SOCKS5_AUTH_NONE = 0x00
_SOCKS5_AUTH_USERPASS = 0x02
_SOCKS5_CMD_CONNECT = 0x01
_SOCKS5_ATYP_DOMAIN = 0x03
_SOCKS5_ATYP_IPV4 = 0x01
_SOCKS5_ATYP_IPV6 = 0x04


def _new_socket(host: str, port: int, timeout: Timeout) -> socket.socket:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as ex:  # DNS failure
        raise ConnectError(f"DNS lookup failed for {host}: {ex}") from ex
    family, socktype, proto, _canon, addr = infos[0]
    sock = socket.socket(family, socktype, proto)
    if timeout.connect is not None:
        sock.settimeout(timeout.connect)
    try:
        sock.connect(addr)
    except (TimeoutError, OSError) as ex:
        sock.close()
        # socket.timeout is an alias of OSError in 3.10+; classify by message
        raise ConnectError(f"Connect to {host}:{port} failed: {ex}") from ex
    return sock


def _negotiate_socks5(sock: socket.socket, host: str, port: int, proxy: ProxyInfo) -> None:
    # greeting: version + one auth method (no-auth, or username/password)
    if proxy.username is not None:
        sock.sendall(struct.pack("BBB", _SOCKS5_VERSION, 2, _SOCKS5_AUTH_NONE) + bytes([_SOCKS5_AUTH_USERPASS]))
    else:
        sock.sendall(struct.pack("BBB", _SOCKS5_VERSION, 1, _SOCKS5_AUTH_NONE))

    hdr = _recv_exact(sock, 2)
    ver, method = hdr[0], hdr[1]
    if ver != _SOCKS5_VERSION:
        raise ProxyError(f"Unexpected SOCKS version from proxy: {ver}")

    if method == 0xFF:
        raise ProxyError("SOCKS5 proxy offered no acceptable auth method")

    if method == _SOCKS5_AUTH_USERPASS:
        if proxy.username is None:
            raise ProxyError("SOCKS5 proxy requires auth but no credentials were provided")
        user = proxy.username.encode("utf-8")
        pwd = (proxy.password or "").encode("utf-8")
        sock.sendall(b"\x01" + bytes([len(user)]) + user + bytes([len(pwd)]) + pwd)
        status = _recv_exact(sock, 2)
        if status[0] != 1 or status[1] != 0x00:
            raise ProxyError("SOCKS5 username/password authentication failed")

    # CONNECT request; prefer domain ATYP to also do remote DNS.
    host_bytes = host.encode("idna") if not _is_ip(host) else host.encode("ascii")
    if _is_ip(host):
        atyp = _SOCKS5_ATYP_IPV4
        addr_bytes = socket.inet_aton(host)
    else:
        atyp = _SOCKS5_ATYP_DOMAIN
        addr_bytes = bytes([len(host_bytes)]) + host_bytes
    sock.sendall(struct.pack("BBB", _SOCKS5_VERSION, _SOCKS5_CMD_CONNECT, 0x00) + bytes([atyp]) + addr_bytes + struct.pack(">H", port))

    rep = _recv_exact(sock, 4)
    if rep[0] != _SOCKS5_VERSION:
        raise ProxyError(f"Bad SOCKS5 CONNECT reply version: {rep[0]}")
    if rep[1] != 0x00:
        raise ProxyError(f"SOCKS5 CONNECT refused, reply code {rep[1]}")
    # skip bound address
    _skip_socks5_addr(sock, rep[3])


def _skip_socks5_addr(sock: socket.socket, atyp: int) -> None:
    if atyp == _SOCKS5_ATYP_IPV4:
        _recv_exact(sock, 4)
    elif atyp == _SOCKS5_ATYP_IPV6:
        _recv_exact(sock, 16)
    elif atyp == _SOCKS5_ATYP_DOMAIN:
        length = _recv_exact(sock, 1)[0]
        _recv_exact(sock, length)
    _recv_exact(sock, 2)  # port


def _is_ip(host: str) -> bool:
    try:
        socket.inet_aton(host)
        return True
    except OSError:
        return False


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ProxyError("Proxy connection closed during handshake")
        buf.extend(chunk)
    return bytes(buf)


def _connect_tunnel(sock: socket.socket, host: str, port: int, proxy: ProxyInfo, timeout: Timeout) -> None:
    connect_timeout = timeout.connect if timeout.connect is not None else 30.0
    sock.settimeout(connect_timeout)
    auth = ""
    if proxy.username is not None:
        import base64

        raw = f"{proxy.username}:{proxy.password or ''}".encode()
        auth = f"Proxy-Authorization: Basic {base64.b64encode(raw).decode()}\r\n"
    req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n{auth}\r\n".encode("ascii")
    sock.sendall(req)

    # Read the CONNECT response status line + headers until blank line.
    reader = sock.makefile("rb")
    status_line = reader.readline().decode("ascii", errors="replace")
    if not status_line:
        raise ProxyError("HTTP proxy returned an empty CONNECT response")
    pieces = status_line.split()
    if len(pieces) < 2 or not pieces[1].startswith("2"):
        raise ProxyError(f"HTTP proxy CONNECT failed: {status_line.strip()}")
    while True:
        line = reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break


def open_socket(
    host: str,
    port: int,
    is_https: bool,
    proxy: ProxyInfo | None,
    timeout: Timeout,
) -> tuple[socket.socket, bool]:
    """Return ``(connected_socket, absolute_form)`` reaching the origin host.

    ``absolute_form`` is True only for plain-HTTP-through-an-HTTP-proxy, where the
    request line uses the full URL instead of ``/path``.
    """
    if proxy is None:
        return _new_socket(host, port, timeout), False

    if proxy.scheme == "socks5":
        sock = _new_socket(proxy.host, proxy.port, timeout)
        try:
            _negotiate_socks5(sock, host, port, proxy)
        except Exception:
            sock.close()
            raise
        return sock, False

    # http / https forward proxy
    proxy_is_tls = proxy.scheme == "https"
    sock = _new_socket(proxy.host, proxy.port, timeout)
    if proxy_is_tls:
        import ssl as _ssl

        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        sock = ctx.wrap_socket(sock, server_hostname=proxy.host)

    if is_https:
        _connect_tunnel(sock, host, port, proxy, timeout)
        return sock, False  # tunnel established; caller TLS-wraps, origin-form
    return sock, True  # plain HTTP via proxy; absolute-form, no TLS


__all__ = ["open_socket"]
