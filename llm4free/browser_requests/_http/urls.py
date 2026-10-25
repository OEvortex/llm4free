"""URL parsing and query-parameter encoding (stdlib only)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


def encode_params(
    params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
) -> str:
    """Encode a params mapping/sequence into a query string.

    Behaviour matches the common HTTP-client contract:
    * ``None`` values are skipped entirely.
    * list/tuple values repeat the key once per element (``a=1&a=2``).
    * bool values are lower-cased (``True`` -> ``true``) like httpx.
    * everything else is ``str()``-ed and percent-encoded.
    """
    if not params:
        return ""

    if isinstance(params, Mapping):
        items: list[tuple[str, Any]] = list(params.items())
    else:
        items = list(params)

    pairs: list[tuple[str, str]] = []
    for key, value in items:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            for v in value:
                if v is None:
                    continue
                pairs.append((key, _scalar(v)))
        else:
            pairs.append((key, _scalar(value)))
    return urlencode(pairs, quote_via=quote)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_url(base_url: str | None, url: str, params: Any = None) -> str:
    """Join an optional base URL with ``url`` and append encoded ``params``.

    ``url`` may already be absolute (scheme present) or a path relative to
    ``base_url``. Existing query strings on ``url`` are merged with ``params``.
    """
    target = url
    if base_url and not urlsplit(target).scheme:
        target = _join(base_url.rstrip("/"), target if target.startswith("/") else "/" + target)

    parts = urlsplit(target)
    qs = parts.query
    extra = encode_params(params)
    if extra:
        qs = f"{qs}&{extra}" if qs else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", qs, parts.fragment))


def _join(base: str, path: str) -> str:
    scheme, netloc, *_ = urlsplit(base)
    prefix = base if not netloc else urlsplit(base)._replace(query="", fragment="").geturl()
    return prefix.rstrip("/") + "/" + path.lstrip("/")


class SplitURL:
    """Parsed pieces of an absolute URL needed by the transport layer."""

    __slots__ = ("scheme", "host", "port", "path", "query", "is_https", "url")

    def __init__(self, url: str) -> None:
        parts = urlsplit(url)
        if not parts.scheme:
            raise ValueError(f"URL must be absolute (got {url!r})")
        self.scheme = parts.scheme
        self.is_https = parts.scheme == "https"
        self.host = parts.hostname or ""
        default_port = 443 if self.is_https else 80
        self.port = parts.port or default_port
        self.query = parts.query
        path = parts.path or "/"
        self.path = path if not parts.query else f"{path}?{parts.query}"
        self.url = url

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"SplitURL({self.url!r})"


__all__ = ["encode_params", "build_url", "SplitURL"]
