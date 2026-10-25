"""Network-environment helpers: proxy resolution, ``NO_PROXY`` and netrc.

These mirror the behaviour users expect from ``requests``/``httpx``:

* an explicit per-request or client proxy always wins;
* ``mount``-registered prefixes match by longest path;
* when ``trust_env`` is set, ``HTTP_PROXY`` / ``HTTPS_PROXY`` (and their lowercase
  forms) are consulted, honouring ``NO_PROXY`` host matching.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

_ENV_PROXIES = {
    "http": ("HTTP_PROXY", "http_proxy"),
    "https": ("HTTPS_PROXY", "https_proxy"),
    "all": ("ALL_PROXY", "all_proxy"),
}


def _get_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value or None


def no_proxy_match(host: str, no_proxy: str | None = None) -> bool:
    """Return True when ``host`` is excluded from proxying by ``NO_PROXY``."""
    entries = no_proxy if no_proxy is not None else (
        _get_env("NO_PROXY") or _get_env("no_proxy") or ""
    )
    host = (host or "").lower().rstrip(".")
    for raw in entries.split(","):
        token = raw.strip().lower().lstrip(".")
        if not token or token == "*":
            if token == "*":
                return True
            continue
        if host == token or host.endswith("." + token):
            return True
    return False


def env_proxy_for(scheme: str, host: str) -> str | None:
    """Proxy URL from the environment for ``scheme``/``host``, or ``None``."""
    if no_proxy_match(host):
        return None
    keys = (*_ENV_PROXIES.get(scheme, ()), *_ENV_PROXIES["all"])
    for key in keys:
        value = _get_env(key)
        if value:
            return value
    return None


def match_mount(prefix: str, url: str) -> bool:
    """requests-style prefix match used by :meth:`Client.mount`."""
    if not prefix:
        return False
    return url.startswith(prefix)


def best_mount(matches: dict[str, str], url: str) -> str | None:
    """Longest matching mount prefix's value (proxy URL or adapter marker)."""
    best_len = -1
    best_val: str | None = None
    for prefix, value in matches.items():
        if match_mount(prefix, url) and len(prefix) > best_len:
            best_len = len(prefix)
            best_val = value
    return best_val


def netrc_auth(host: str) -> tuple[str, str] | None:
    """Credentials for ``host`` from the user's netrc file, or ``None``.

    Never raises: a missing/invalid netrc simply yields no auth.
    """
    try:
        import netrc

        path = os.environ.get("NETRC") or os.path.expanduser("~/.netrc")
        machine = netrc.netrc(path).authenticators(host)
    except (OSError, netrc.NetrcParseError):
        return None
    if not machine:
        return None
    login, _, password = machine
    if login is None:
        return None
    return login, password or ""


__all__ = [
    "no_proxy_match",
    "env_proxy_for",
    "match_mount",
    "best_mount",
    "netrc_auth",
    "urlsplit",
]
