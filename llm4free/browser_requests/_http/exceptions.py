"""HTTP exception types for the stdlib client.

These are thin wrappers that map onto the project's existing exception
hierarchy (``LLM4FreeE`` / ``TimeoutE`` / ``RatelimitE``) so that provider
``except`` clauses keep working after migration.
"""

from __future__ import annotations

from ...exceptions import (
    APIConnectionError,
    LLM4FreeE,
    RatelimitE,
    TimeoutE,
)


class HTTPLLError(LLM4FreeE):
    """Base class for all errors raised by :mod:`llm4free.browser_requests._http`."""


class HTTPError(HTTPLLError, APIConnectionError):
    """A transport-level HTTP failure (connection, protocol, proxy, ...)."""


class ConnectError(HTTPError):
    """Failed to establish the underlying connection."""


class ReadError(HTTPError):
    """Connection established but reading the response failed."""


class ProxyError(HTTPError):
    """Proxy (HTTP CONNECT / SOCKS5) handshake failed."""


class SSLError(HTTPError):
    """TLS handshake / certificate verification failed."""


class TimeoutError(HTTPLLError, TimeoutE):  # noqa: A001 - intentional shadow
    """A request exceeded its connect or read timeout."""


class TooManyRedirects(HTTPError):
    """The request exceeded the configured redirect limit."""


class HTTPStatusError(HTTPLLError):
    """The server returned an unsuccessful status and ``raise_for_status`` fired."""

    def __init__(self, message: str, *, status_code: int, url: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


# Rate-limit status codes mirrored from search/http_client.py:129
_RATELIMIT_STATUS = {202, 301, 403, 400, 429, 418}


def status_to_exception(status_code: int, url: str) -> LLM4FreeE:
    """Map an HTTP status code onto the project's exception vocabulary.

    Reuses the exact rules from :class:`llm4free.search.http_client.HttpClient`.
    """
    if status_code in _RATELIMIT_STATUS:
        return RatelimitE(f"{url} {status_code} Rate limit")
    return LLM4FreeE(f"{url} returned {status_code}")


# --- curl_cffi / requests compatibility aliases ----------------------------
# Provider bodies do ``except CurlError``, ``except RequestException``,
# ``from curl_cffi.requests import RequestsError`` and ``Timeout``. Mapping those
# names onto this module's hierarchy lets a provider migrate by swapping only its
# import line.
RequestException = HTTPError
RequestsError = HTTPError
CurlError = HTTPError
ConnectionError = ConnectError
Timeout = TimeoutError
ReadTimeout = TimeoutError
ConnectTimeout = TimeoutError


__all__ = [
    "HTTPLLError",
    "HTTPError",
    "ConnectError",
    "ReadError",
    "ProxyError",
    "SSLError",
    "TimeoutError",
    "TooManyRedirects",
    "HTTPStatusError",
    "status_to_exception",
    # compatibility aliases
    "RequestException",
    "RequestsError",
    "CurlError",
    "ConnectionError",
    "Timeout",
    "ReadTimeout",
    "ConnectTimeout",
]
