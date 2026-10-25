"""Core data models: :class:`Headers`, :class:`Cookies`, :class:`Response`."""

from __future__ import annotations

import json as _json
from http.cookies import SimpleCookie
from typing import Any, Iterator, Mapping, Sequence


class Headers:
    """Immutable, case-insensitive, multi-value header container."""

    __slots__ = ("_items",)

    def __init__(self, data: Any = None) -> None:
        items: list[tuple[str, str]] = []
        if data is None:
            pass
        elif isinstance(data, Headers):
            items = list(data._items)
        elif isinstance(data, Mapping):
            items = [(str(k), str(v)) for k, v in data.items()]
        else:  # sequence of (k, v) pairs
            items = [(str(k), str(v)) for k, v in data]  # type: ignore[union-attr]
        self._items = items

    def _norm(self, key: str) -> str:
        return key.lower()

    def get(self, key: str, default: Any = None) -> Any:
        low = self._norm(key)
        for k, v in self._items:
            if k.lower() == low:
                return v
        return default

    def get_all(self, key: str) -> list[str]:
        low = self._norm(key)
        return [v for k, v in self._items if k.lower() == low]

    def __getitem__(self, key: str) -> str:
        low = self._norm(key)
        for k, v in self._items:
            if k.lower() == low:
                return v
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        low = self._norm(key)
        return any(k.lower() == low for k, _ in self._items)

    def __iter__(self) -> Iterator[str]:
        return (k for k, _ in self._items)

    def items(self) -> list[tuple[str, str]]:
        return list(self._items)

    def keys(self) -> list[str]:
        return [k for k, _ in self._items]

    def values(self) -> list[str]:
        return [v for _, v in self._items]

    def to_dict(self) -> dict[str, str]:
        return {k: v for k, v in self._items}

    def merged(self, other: Any) -> "Headers":
        """Return a new Headers with ``other`` overriding matching keys."""
        if not other:
            return self
        base = dict(self._items)
        for k, v in Headers(other).items():
            # drop existing case-insensitive match then re-add with new casing
            base = {bk: bv for bk, bv in base.items() if bk.lower() != k.lower()}
            base[k] = v
        return Headers(list(base.items()))

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Headers({self._items!r})"


class Cookies:
    """A minimal, request-scoped cookie jar.

    Stores name -> value. Real per-domain/path/expiry semantics are not needed
    by LLM4Free providers; they mostly ``update`` the jar manually and reuse it.
    """

    __slots__ = ("_jar",)

    def __init__(self, data: Mapping[str, str] | None = None) -> None:
        self._jar: dict[str, str] = dict(data) if data else {}

    def set(self, name: str, value: str) -> None:
        self._jar[name] = value

    def update(self, data: Mapping[str, str]) -> None:
        self._jar.update(data)

    def get(self, name: str, default: Any = None) -> Any:
        return self._jar.get(name, default)

    def __getitem__(self, name: str) -> str:
        return self._jar[name]

    def __setitem__(self, name: str, value: str) -> None:
        self._jar[name] = value

    def __contains__(self, name: str) -> bool:
        return name in self._jar

    def __iter__(self) -> Iterator[str]:
        return iter(self._jar)

    def items(self) -> list[tuple[str, str]]:
        return list(self._jar.items())

    def to_dict(self) -> dict[str, str]:
        return dict(self._jar)

    def get_dict(self) -> dict[str, str]:
        # requests-cookiejar compatibility.
        return dict(self._jar)

    def header_value(self) -> str | None:
        if not self._jar:
            return None
        return "; ".join(f"{k}={v}" for k, v in self._jar.items())

    def extract_set_cookie(self, header_values: Sequence[str]) -> None:
        """Absorb one or more raw ``Set-Cookie`` header strings."""
        for raw in header_values:
            sc = SimpleCookie()
            try:
                sc.load(raw)
            except Exception:
                continue
            for key, morsel in sc.items():
                self._jar[key] = morsel.value

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Cookies({self._jar!r})"


class Response:
    """HTTP response with an httpx-compatible surface.

    Constructed by a transport with either a fully-buffered body (``content``)
    or a stream iterator of *decoded* byte chunks (``stream``). Chunked transfer
    and content-encoding (gzip/deflate) are resolved by the transport before the
    chunks reach this object.
    """

    def __init__(
        self,
        *,
        status_code: int,
        reason: str = "",
        headers: Headers | None = None,
        url: str = "",
        cookies: Cookies | None = None,
        content: bytes | None = None,
        stream: Iterator[bytes] | None = None,
        request: Any = None,
    ) -> None:
        self.status_code = status_code
        self.reason = reason
        self.headers = headers or Headers()
        self.url = url
        self.cookies = cookies if cookies is not None else Cookies()
        self.request = request
        self._content: bytes | None = content
        self._stream: Iterator[bytes] | None = stream

    # --- status helpers ---
    @property
    def ok(self) -> bool:
        return self.status_code < 400

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308)

    def raise_for_status(self) -> "Response":
        if self.status_code >= 400:
            from .exceptions import HTTPStatusError

            raise HTTPStatusError(
                f"{self.status_code} {self.reason} for url: {self.url}",
                status_code=self.status_code,
                url=self.url,
            )
        return self

    # --- body access ---
    @property
    def content(self) -> bytes:
        if self._content is None:
            self._content = b"".join(self.iter_bytes())
            self._stream = None
        return self._content

    @property
    def text(self) -> str:
        return self.content.decode(self._encoding(), errors="replace")

    def _encoding(self) -> str:
        ctype = self.headers.get("content-type", "") or ""
        for part in ctype.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                return part.split("=", 1)[1].strip('"\' ') or "utf-8"
        return "utf-8"

    def json(self, **kwargs: Any) -> Any:
        return _json.loads(self.text, **kwargs)

    # --- streaming ---
    def iter_bytes(self, chunk_size: int = 8192) -> Iterator[bytes]:
        if self._content is not None:
            data = self._content
            for i in range(0, len(data), chunk_size):
                yield data[i : i + chunk_size]
            return
        assert self._stream is not None, "response has no body"
        yield from self._stream

    def _iter_split_lines(self, keep_blank: bool) -> Iterator[str]:
        buf = b""
        for raw in self.iter_bytes():
            buf += raw
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                text = line.decode("utf-8", errors="replace").rstrip("\r")
                if text or keep_blank:
                    yield text
        if buf:
            text = buf.decode("utf-8", errors="replace").rstrip("\r")
            if text or keep_blank:
                yield text

    def iter_lines(self) -> Iterator[str]:
        return self._iter_split_lines(keep_blank=False)

    def iter_content(self, chunk_size: int = 8192, decode_unicode: bool = False) -> Iterator[Any]:
        if decode_unicode:
            enc = self._encoding()
            for raw in self.iter_bytes(chunk_size):
                yield raw.decode(enc, errors="replace")
            return
        yield from self.iter_bytes(chunk_size)

    @property
    def raw(self) -> Any:
        # Compatibility shim: providers that fall back to a raw socket can read
        # from the buffered body instead.
        return self

    def iter_text(self) -> Iterator[str]:
        enc = self._encoding()
        for raw in self.iter_bytes():
            yield raw.decode(enc, errors="replace")

    def iter_sse(self) -> Iterator["ServerSentEvent"]:
        from .sse import iter_sse_events

        return iter_sse_events(self._iter_split_lines(keep_blank=True))

    def read(self) -> bytes:
        return self.content

    def close(self) -> None:
        stream = self._stream
        if stream is not None:
            closer = getattr(stream, "close", None)
            if callable(closer):
                closer()
            self._stream = None

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Response [{self.status_code}]>"


# Re-exported lazily for typing; defined in sse.py.
try:  # pragma: no cover - import ordering guard
    from .sse import ServerSentEvent  # noqa: F401
except Exception:  # circular-safe
    class ServerSentEvent:  # type: ignore[no-redef]
        pass


__all__ = ["Headers", "Cookies", "Response"]
