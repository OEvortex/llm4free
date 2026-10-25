"""llm4free.browser_requests._http — a lightweight, zero-dependency, httpx-style HTTP client.

Public API::

    from llm4free.browser_requests._http import Client, AsyncClient, get, post
    from llm4free.browser_requests._http import Response, Headers, Cookies

Plain traffic runs on the Python stdlib only. Browser TLS impersonation is
available *behind a seam*: pass ``impersonate="chrome124"`` and the client routes
through an optional ``primp`` backend (install ``llm4free[impersonate]``),
never for ordinary API calls.
"""

from __future__ import annotations

from .async_client import AsyncClient, AsyncResponse
from . import compat
from .auth import AuthBase, BasicAuth, BearerAuth, DigestAuth, resolve_auth
from .client import (
    Client,
    delete,
    get,
    head,
    patch,
    post,
    put,
    request,
)
from .exceptions import (
    ConnectError,
    ConnectionError,
    CurlError,
    HTTPError,
    HTTPLLError,
    HTTPStatusError,
    ProxyError,
    ReadError,
    ReadTimeout,
    RequestException,
    RequestsError,
    SSLError,
    Timeout,
    TimeoutError,
    TooManyRedirects,
)
from .models import Cookies, Headers, Response
from .sse import ServerSentEvent
from .transport import get_async_transport, get_sync_transport

__all__ = [
    # clients
    "Client",
    "AsyncClient",
    "AsyncResponse",
    # model
    "Response",
    "Headers",
    "Cookies",
    "ServerSentEvent",
    # auth
    "AuthBase",
    "BasicAuth",
    "BearerAuth",
    "DigestAuth",
    "resolve_auth",
    # helpers
    "request",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    # transport seam
    "get_sync_transport",
    "get_async_transport",
    # compat facade
    "compat",
    # exceptions
    "HTTPLLError",
    "HTTPError",
    "HTTPStatusError",
    "ConnectError",
    "ReadError",
    "ProxyError",
    "SSLError",
    "TimeoutError",
    "TooManyRedirects",
    # curl/requests compatibility aliases
    "CurlError",
    "RequestsError",
    "RequestException",
    "ConnectionError",
    "Timeout",
    "ReadTimeout",
]
