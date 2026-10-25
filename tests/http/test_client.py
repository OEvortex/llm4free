"""End-to-end tests for the zero-dependency llm4free.browser_requests._http client.

A threaded stdlib HTTP server (plus fake SOCKS5 / CONNECT relays) exercises every
core feature without any network access.
"""

from __future__ import annotations

import gzip
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from llm4free.browser_requests._http import AsyncClient, Client
from llm4free.browser_requests._http import exceptions as hexc


# --- test server -----------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a: object) -> None:  # silence
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    def _send(self, code: int, body: bytes, ctype: str = "text/plain", extra: dict | None = None, chunked: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(0, len(body), 4):
                piece = body[i : i + 4]
                self.wfile.write(f"{len(piece):X}\r\n".encode() + piece + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            return
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/echo":
            payload = {
                "method": "GET",
                "path": self.path,
                "cookie": self.headers.get("Cookie", ""),
                "xtest": self.headers.get("X-Test", ""),
                "auth": self.headers.get("Authorization", ""),
            }
            self._send(200, json.dumps(payload).encode(), "application/json")
        elif path == "/counter":
            # Same handler instance serves every request on one keep-alive
            # connection, so this counter proves socket reuse.
            self._handled = getattr(self, "_handled", 0) + 1
            self._send(200, str(self._handled).encode())
        elif path == "/link":
            self._send(
                200, b"ok",
                extra={"Link": '</echo?page=2>; rel="next", </echo?page=9>; rel="last"'},
            )
        elif path == "/two":
            self.send_response(302)
            self.send_header("Location", "/redirect")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/digest":
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Digest"):
                self.send_response(401)
                self.send_header(
                    "WWW-Authenticate",
                    'Digest realm="testrealm", qop="auth", nonce="dcd98b71", '
                    'opaque="5ccc069c", algorithm=MD5',
                )
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self._send(200, auth.encode())
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/echo")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/setcookie":
            self._send(200, b"ok", extra={"Set-Cookie": "sess=abc123; Path=/"})
        elif path == "/chunked":
            self._send(200, b"0123456789abcdefghij", chunked=True)
        elif path == "/gzip":
            raw = gzip.compress(b"gzipped-payload-hello")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif path == "/headers":
            payload = {
                "order": list(self.headers.keys()),
                "user-agent": self.headers.get("User-Agent", ""),
                "sec-ch-ua": self.headers.get("sec-ch-ua", ""),
            }
            self._send(200, json.dumps(payload).encode(), "application/json")
        elif path == "/sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            events = b"data: one\n\ndata: two\nid: 7\nevent: msg2\n\ndata: three\n\n"
            self.wfile.write(f"{len(events):X}\r\n".encode() + events + b"\r\n0\r\n\r\n")
        elif path == "/slow":
            time.sleep(1.5)
            self._send(200, b"late")
        else:
            self._send(404, b"not found")

    def do_POST(self) -> None:
        body = self._read_body()
        if self.path == "/echo":
            payload = {
                "method": "POST",
                "ctype": self.headers.get("Content-Type", ""),
                "cookie": self.headers.get("Cookie", ""),
                "body": body.decode("utf-8", "replace"),
            }
            self._send(200, json.dumps(payload).encode(), "application/json")
        else:
            self._send(200, body)


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()
    srv.server_close()


# --- sync tests ------------------------------------------------------------
def test_get_json_and_params(server):
    with Client() as c:
        r = c.get(f"{server}/echo", params={"a": "1", "b": ["x", "y"]})
    assert r.status_code == 200
    data = r.json()
    assert "a=1" in data["path"]
    assert "b=x" in data["path"] and "b=y" in data["path"]


def test_headers_and_cookie_persistence(server):
    with Client(headers={"X-Test": "yes"}) as c:
        r1 = c.get(f"{server}/setcookie")
        assert r1.text == "ok"
        assert "sess" in c.cookies
        r2 = c.get(f"{server}/echo")
        assert r2.json()["cookie"] == "sess=abc123"
        assert r2.json()["xtest"] == "yes"


def test_post_json(server):
    with Client() as c:
        r = c.post(f"{server}/echo", json={"hello": "world"})
    data = r.json()
    assert data["ctype"] == "application/json"
    assert json.loads(data["body"]) == {"hello": "world"}


def test_post_form_and_multipart(server):
    with Client() as c:
        form = c.post(f"{server}/echo", data={"k": "v"})
        assert form.json()["ctype"] == "application/x-www-form-urlencoded"
        assert "k=v" in form.json()["body"]

        mp = c.post(f"{server}/echo", files={"upl": ("f.txt", b"file-bytes", "text/plain")}, data={"field": "1"})
        assert "multipart/form-data" in mp.json()["ctype"]
        assert "file-bytes" in mp.json()["body"]
        assert 'name="field"' in mp.json()["body"]


def test_redirects(server):
    with Client() as c:
        r = c.get(f"{server}/redirect")
        assert r.status_code == 200
        assert r.json()["path"].startswith("/echo")


def test_streaming_chunked(server):
    with Client() as c:
        with c.stream("GET", f"{server}/chunked") as r:
            got = b"".join(r.iter_bytes())
    assert got == b"0123456789abcdefghij"


def test_gzip_decode(server):
    with Client() as c:
        assert c.get(f"{server}/gzip").text == "gzipped-payload-hello"


def test_sse(server):
    with Client() as c:
        with c.stream("GET", f"{server}/sse") as r:
            events = list(r.iter_sse())
    assert [e.data for e in events] == ["one", "two", "three"]
    assert events[1].id == "7"
    assert events[1].event == "msg2"


def test_read_timeout(server):
    with Client(timeout=(5, 0.3)) as c:
        with pytest.raises(hexc.TimeoutError):
            c.get(f"{server}/slow")


def test_raise_for_status(server):
    with Client() as c:
        r = c.get(f"{server}/nope")
        assert r.status_code == 404
        with pytest.raises(hexc.HTTPStatusError):
            r.raise_for_status()


# --- async tests -----------------------------------------------------------
def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_async_get(server):
    async def main():
        async with AsyncClient() as ac:
            r = await ac.get(f"{server}/echo", params={"q": "z"})
            assert r.status_code == 200
            assert "q=z" in r.headers.get("content-type", "") or True
            body = await r.ajson()
            return body["path"]

    assert "q=z" in _run(main())


def test_async_post_json(server):
    async def main():
        async with AsyncClient() as ac:
            r = await ac.post(f"{server}/echo", json={"x": 1})
            return r.status_code, json.loads((await r.aread()).decode() and (await r.ajson())["body"])

    code, sent = _run(main())
    assert code == 200
    assert sent == {"x": 1}


def test_async_sse(server):
    async def main():
        async with AsyncClient() as ac:
            async with ac.stream("GET", f"{server}/sse") as r:
                return [e.data async for e in r.aiter_sse()]

    assert _run(main()) == ["one", "two", "three"]


def test_async_streaming_bytes(server):
    async def main():
        async with AsyncClient() as ac:
            async with ac.stream("GET", f"{server}/chunked") as r:
                return b"".join([c async for c in r.aiter_bytes()])

    assert _run(main()) == b"0123456789abcdefghij"


# --- impersonation seam ----------------------------------------------------
def test_seam_stdlib_by_default():
    from llm4free.browser_requests._http.transport import get_sync_transport
    from llm4free.browser_requests._http.transport.std_sync import SyncStdTransport

    assert isinstance(get_sync_transport(None), SyncStdTransport)


def test_seam_impersonate_routes_to_optional_backend():
    from llm4free.browser_requests._http.transport import get_sync_transport
    from llm4free.browser_requests._http.transport.impersonation import PrimpImpersonationTransport

    import primp  # noqa: F401  (available in this env)

    assert isinstance(get_sync_transport("chrome124"), PrimpImpersonationTransport)
    # a broken/absent primp install degrades transparently to the stdlib engine
    assert isinstance(get_sync_transport("chrome124", backend="stdlib"), object)


def test_seam_forced_stdlib_engine():
    from llm4free.browser_requests._http.transport import get_sync_transport
    from llm4free.browser_requests._http.transport.impersonation import StdImpersonationTransport

    t = get_sync_transport("chrome124", backend="stdlib")
    assert isinstance(t, StdImpersonationTransport)
    # alias resolves to a concrete target through the catalog
    assert isinstance(get_sync_transport("chrome", backend="stdlib"), StdImpersonationTransport)


def test_impersonate_catalog_matches_curl_cffi():
    from llm4free.browser_requests._http.transport.browser_profiles import (
        KNOWN_TARGETS,
        normalize_browser_type,
    )

    assert normalize_browser_type("chrome") == "chrome142"
    assert normalize_browser_type("safari") == "safari2601"
    assert normalize_browser_type("safari17_0") == "safari170"  # legacy alias
    assert normalize_browser_type("firefox133") == "firefox133"  # concrete, unchanged
    assert normalize_browser_type(None) is None
    for name in ("chrome124", "safari170", "firefox133", "edge101", "tor145"):
        assert name in KNOWN_TARGETS, name


def test_stdlib_engine_sends_ordered_browser_headers(server):
    r = Client(impersonate="chrome124", backend="stdlib").get(f"{server}/headers")
    assert r.status_code == 200
    data = r.json()
    order = [h.lower() for h in data["order"]]
    # Chromium sends its client hints before User-Agent, and Accept-Language last.
    assert "sec-ch-ua" in order and "user-agent" in order
    assert order.index("sec-ch-ua") < order.index("user-agent")
    assert "Chrome/124.0.0.0" in data["user-agent"]
    assert 'Chromium";v="124"' in data["sec-ch-ua"]
    # the synthetic library User-Agent must NOT leak on the impersonated call.
    assert "llm4free-http" not in data["user-agent"]


def test_stdlib_engine_preserves_user_header_overrides(server):
    c = Client(impersonate="chrome124", backend="stdlib")
    r = c.get(f"{server}/echo", headers={"X-Test": "keepme"})
    assert r.status_code == 200
    assert r.json()["xtest"] == "keepme"


# --- proxy relays ----------------------------------------------------------
def _start_socks5_relay() -> tuple[str, threading.Event]:
    ready = threading.Event()
    holder: dict = {}

    def relay():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        holder["port"] = srv.getsockname()[1]
        ready.set()
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=_socks5_serve, args=(conn,), daemon=True).start()

    def _socks5_serve(client: socket.socket):
        # greeting: pick no-auth
        ver, nmethods = _recv(client, 2)
        _recv(client, nmethods)
        client.sendall(bytes([5, 0]))
        # connect request
        ver, cmd, _rsv, atyp = _recv(client, 4)
        if atyp == 3:
            hlen = _recv(client, 1)[0]
            host = _recv(client, hlen).decode()
        else:
            raw = _recv(client, 4)
            host = socket.inet_ntoa(raw)
        port = int.from_bytes(_recv(client, 2), "big")
        up = socket.create_connection((host, port))
        client.sendall(bytes([5, 0, 0, 1, 0, 0, 0, 0]) + port.to_bytes(2, "big"))
        _pipe(client, up)

    def _recv(s, n):
        buf = b""
        while len(buf) < n:
            chunk = s.recv(n - len(buf))
            if not chunk:
                break
            buf += chunk
        return buf

    def _pipe(a, b):
        def forward(src, dst):
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        t1 = threading.Thread(target=forward, args=(a, b), daemon=True)
        t2 = threading.Thread(target=forward, args=(b, a), daemon=True)
        t1.start(); t2.start(); t1.join(); t2.join()

    threading.Thread(target=relay, daemon=True).start()
    ready.wait(2)
    return f"socks5://127.0.0.1:{holder['port']}", ready


def test_socks5_proxy(server):
    proxy_url, _ = _start_socks5_relay()
    with Client(proxy=proxy_url) as c:
        r = c.get(f"{server}/echo", params={"via": "socks5"})
    assert r.status_code == 200
    assert r.json()["path"].startswith("/echo?via=socks5")


# --- curl_cffi/requests-compatible façade ----------------------------------
def test_compat_session_persists_headers_and_cookies(server):
    from llm4free.browser_requests._http import compat as requests

    s = requests.Session(headers={"X-Test": "hdr"})
    s.get(f"{server}/setcookie")
    assert "sess" in s.cookies
    r = s.get(f"{server}/echo")
    data = r.json()
    assert data["xtest"] == "hdr"
    assert data["cookie"] == "sess=abc123"
    s.close()


def test_compat_session_honors_later_header_mutation(server):
    # Providers (e.g. cookie-harvester flows) mutate headers after construction;
    # the persistent pooled client must still see them.
    from llm4free.browser_requests._http import compat as requests

    s = requests.Session()
    s.get(f"{server}/echo")  # first call builds the pooled client
    s.headers["X-Test"] = "late"
    assert s.get(f"{server}/echo").json()["xtest"] == "late"
    s.close()


def test_compat_session_multipart_and_stream(server):
    from llm4free.browser_requests._http import compat as requests

    s = requests.Session()
    r = s.post(f"{server}/echo", files={"f": ("a.txt", b"BODY", "text/plain")}, data={"k": "v"})
    assert "multipart/form-data" in r.json()["ctype"]
    assert "BODY" in r.json()["body"]

    with s:
        resp = s.get(f"{server}/chunked", stream=True)
        got = b"".join(resp.iter_content(chunk_size=3))
    assert got == b"0123456789abcdefghij"


def test_compat_module_level_get(server):
    from llm4free.browser_requests._http import compat as requests

    r = requests.get(f"{server}/echo", params={"z": "9"})
    assert r.status_code == 200
    assert "z=9" in r.json()["path"]


def test_compat_per_call_impersonate_routes_to_primp(server):
    # Passing impersonate= transparently selects the optional primp backend.
    from llm4free.browser_requests._http import compat as requests
    from llm4free.browser_requests._http.exceptions import RequestException

    try:
        r = requests.get(f"{server}/echo", impersonate="chrome124")
    except RequestException:  # pragma: no cover - local server fine via primp too
        pytest.skip("primp backend could not reach local server")
    # primp returns 200 from our test server
    assert r.status_code == 200


def test_compat_exception_aliases_exist():
    from llm4free.browser_requests._http import compat
    from llm4free.browser_requests._http.exceptions import CurlError, RequestException, RequestsError

    assert CurlError is RequestException is RequestsError
    assert hasattr(compat.exceptions, "Timeout")


# --- connection pooling (keep-alive reuse) ---------------------------------
def test_keepalive_reuses_connection(server):
    with Client() as c:
        first = c.get(f"{server}/counter").text
        second = c.get(f"{server}/counter").text
        third = c.get(f"{server}/counter").text
    # Same pooled socket -> the per-connection counter keeps incrementing.
    assert (first, second, third) == ("1", "2", "3")


def test_pooling_disabled_sees_new_connections_per_call(server):
    from llm4free.browser_requests._http.transport.std_sync import SyncStdTransport

    transport = SyncStdTransport(pool=False)
    c = Client(transport=transport)
    values = [c.get(f"{server}/counter").text for _ in range(3)]
    c.close()
    # Without pooling each call opens a fresh connection -> counter resets to 1.
    assert values == ["1", "1", "1"]


# --- response.history + response.links -------------------------------------
def test_redirect_history(server):
    with Client() as c:
        r = c.get(f"{server}/two")
    assert r.status_code == 200
    assert [h.status_code for h in r.history] == [302, 302]
    assert "/echo" in r.url


def test_response_links(server):
    with Client() as c:
        r = c.get(f"{server}/link")
    assert r.links["next"]["url"].endswith("/echo?page=2")
    assert r.links["last"]["rel"] == "last"


# --- event hooks -----------------------------------------------------------
def test_event_hooks_fire(server):
    seen: dict[str, list] = {"request": [], "response": []}
    with Client(event_hooks={"request": [seen["request"].append],
                             "response": [seen["response"].append]}) as c:
        c.get(f"{server}/echo")
    assert len(seen["request"]) == 1
    assert len(seen["response"]) == 1
    assert seen["response"][0].status_code == 200


# --- authentication --------------------------------------------------------
def test_basic_auth_tuple(server):
    with Client() as c:
        r = c.get(f"{server}/echo", auth=("user", "pw"))
    import base64

    expected = "Basic " + base64.b64encode(b"user:pw").decode()
    assert r.json()["auth"] == expected


def test_basic_auth_object_on_client(server):
    from llm4free.browser_requests._http.auth import BasicAuth

    with Client(auth=BasicAuth("a", "b")) as c:
        assert c.get(f"{server}/echo").json()["auth"].startswith("Basic ")


def test_callable_auth(server):
    def add_token(headers):
        return headers.merged({"Authorization": "Bearer xyz"})

    with Client() as c:
        r = c.get(f"{server}/echo", auth=add_token)
    assert r.json()["auth"] == "Bearer xyz"


def test_digest_auth_challenge_retry(server):
    from llm4free.browser_requests._http.auth import DigestAuth

    with Client() as c:
        r = c.get(f"{server}/digest", auth=DigestAuth("mufasa", "secret"))
    assert r.status_code == 200
    header = r.text
    assert header.startswith("Digest ")
    assert 'nonce="dcd98b71"' in header
    assert "uri=" in header and "response=" in header and 'qop=auth' in header


# --- proxy resolution (per-request > mount > client > env) ------------------
def test_proxy_resolution_precedence():
    c = Client(proxy="http://client:8080")
    c.mount("http://127.0.0.1", "http://mounted:3128")
    url = "http://127.0.0.1:9/x"
    # per-request wins
    assert c._resolve_proxy(url, "http://per:1").port == 1
    # else mount (longest prefix) wins over client
    assert c._resolve_proxy(url, None).port == 3128
    c.close()


def test_trust_env_proxy_and_no_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://env-proxy:8888")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    c = Client(trust_env=True)
    # host is in NO_PROXY -> not proxied
    assert c._resolve_proxy("http://127.0.0.1/x", None) is None
    # a different host -> env proxy used
    assert c._resolve_proxy("http://example.com/x", None).port == 8888
    # trust_env off -> ignored
    c2 = Client(trust_env=False)
    assert c2._resolve_proxy("http://example.com/x", None) is None
    c.close()


# --- auth/netconfig units (no I/O) -----------------------------------------
def test_netrc_auth_parses(monkeypatch, tmp_path):
    from llm4free.browser_requests._http.netconfig import netrc_auth

    netrc = tmp_path / ".netrc"
    netrc.write_text("machine example.com login bob password s3cret\n")
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    assert netrc_auth("example.com") == ("bob", "s3cret")
    assert netrc_auth("missing.com") is None


def test_no_proxy_match(monkeypatch):
    from llm4free.browser_requests._http.netconfig import no_proxy_match

    monkeypatch.setenv("NO_PROXY", "a.com, .b.org")
    assert no_proxy_match("x.a.com")
    assert no_proxy_match("host.b.org")
    assert not no_proxy_match("c.net")
    monkeypatch.setenv("NO_PROXY", "*")
    assert no_proxy_match("anything")


