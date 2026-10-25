"""Authentication primitives for :mod:`llm4free.browser_requests._http`.

Mirrors the ``requests`` auth-object model so a credential bundle can be handed
to ``auth=`` and applied transparently. ``BasicAuth`` and ``BearerAuth`` stamp a
static ``Authorization`` header; ``DigestAuth`` implements RFC 7616 (MD5 and
SHA-256, with the ``-sess`` variants) as a challenge/response that the client
retries once after a ``401``.

Any plain callable ``(Headers) -> Headers`` is also accepted by the client as an
auth hook, matching ``requests``' duck-typed callables.
"""

from __future__ import annotations

import hashlib
import os
from typing import Callable, Optional, cast

from .models import Headers

AuthLike = "AuthBase | tuple[str, str] | Callable[[Headers], Headers]"


class AuthBase:
    """Base class for auth applied before the request is sent."""

    #: Whether applying this auth requires a server challenge (Digest).
    requires_challenge: bool = False

    def auth_header(self, method: str, url: str) -> Optional[str]:  # pragma: no cover
        raise NotImplementedError

    def set_challenge(self, www_authenticate: str) -> None:
        """Absorb a server ``WWW-Authenticate`` challenge (no-op for static auth)."""
        return None

    def apply(self, headers: Headers, method: str, url: str) -> Headers:
        value = self.auth_header(method, url)
        if value is not None:
            return headers.merged({"Authorization": value})
        return headers


class BasicAuth(AuthBase):
    def __init__(self, username: str, password: str = "") -> None:
        import base64

        raw = f"{username}:{password}".encode("utf-8")
        self._value = "Basic " + base64.b64encode(raw).decode("ascii")

    def auth_header(self, method: str, url: str) -> str:
        return self._value


class BearerAuth(AuthBase):
    def __init__(self, token: str) -> None:
        self._value = f"Bearer {token}"

    def auth_header(self, method: str, url: str) -> str:
        return self._value


def _parse_digest_challenge(header: str) -> dict[str, str]:
    """Parse a ``Digest k=v, k="v with, comma"`` challenge into a dict."""
    params: dict[str, str] = {}
    # split on commas that are outside quotes
    buf = ""
    in_str = False
    parts: list[str] = []
    for ch in header:
        if ch == '"':
            in_str = not in_str
            buf += ch
        elif ch == "," and not in_str:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    for part in parts:
        name, sep, value = part.strip().partition("=")
        if not sep:
            continue
        params[name.strip().lower()] = value.strip().strip('"')
    return params


class DigestAuth(AuthBase):
    requires_challenge = True

    _ALGOS = {
        "MD5": hashlib.md5,
        "SHA-256": hashlib.sha256,
        "SHA-512-256": hashlib.sha512,  # truncated below
    }

    def __init__(self, username: str, password: str = "") -> None:
        self.username = username
        self.password = password
        self._nc = 0
        self._challenge: dict[str, str] = {}

    def auth_header(self, method: str, url: str) -> Optional[str]:
        if not self._challenge:
            return None
        return self._build(method, url)

    @property
    def has_challenge(self) -> bool:
        return bool(self._challenge)

    def set_challenge(self, www_authenticate: str) -> None:
        lowered = www_authenticate.lower()
        if not lowered.startswith("digest"):
            return
        self._challenge = _parse_digest_challenge(www_authenticate[6:])

    def _hash(self, algo: str, data: str) -> str:
        name = algo.upper()
        if name in self._ALGOS:
            h = self._ALGOS[name](data.encode("utf-8"))
            if name == "SHA-512-256":
                return h.hexdigest()[:64]
            return h.hexdigest()
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    def _build(self, method: str, uri: str) -> str:
        ch = self._challenge
        realm = ch.get("realm", "")
        nonce = ch.get("nonce", "")
        opaque = ch.get("opaque")
        qop = ch.get("qop", "").split(",")[0].strip()
        algo = ch.get("algorithm", "MD5")

        self._nc += 1
        nc = f"{self._nc:08x}"
        cnonce = hashlib.sha256(os.urandom(16)).hexdigest()[:16]

        ha1 = self._hash(algo, f"{self.username}:{realm}:{self.password}")
        if algo.upper().endswith("-SESS"):
            base = algo.upper()[: -len("-SESS")]
            ha1 = self._hash(base, f"{ha1}:{nonce}:{cnonce}")
        ha2 = self._hash(algo, f"{method}:{uri}")

        if qop:
            response = self._hash(
                algo, f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}"
            )
        else:
            response = self._hash(algo, f"{ha1}:{nonce}:{ha2}")

        fields = [
            f'username="{self.username}"',
            f'realm="{realm}"',
            f'nonce="{nonce}"',
            f'uri="{uri}"',
            f'response="{response}"',
        ]
        if qop:
            fields.append(f"qop={qop}")
            fields.append(f'nc="{nc}"')
            fields.append(f'cnonce="{cnonce}"')
        if opaque is not None:
            fields.append(f'opaque="{opaque}"')
        fields.append(f'algorithm={algo}')
        return "Digest " + ", ".join(fields)


def resolve_auth(auth: object) -> AuthBase | Callable[[Headers], Headers] | None:
    """Normalize the many accepted ``auth=`` forms into something usable."""
    if auth is None:
        return None
    if isinstance(auth, AuthBase):
        return auth
    if isinstance(auth, (tuple, list)):
        if not (1 <= len(auth) <= 2):
            raise ValueError("basic auth tuple must be (username,) or (username, password)")
        return BasicAuth(str(auth[0]), str(auth[1]) if len(auth) > 1 else "")
    if callable(auth):
        return cast("Callable[[Headers], Headers]", auth)
    raise TypeError(f"Unsupported auth object: {type(auth)!r}")


__all__ = [
    "AuthBase",
    "BasicAuth",
    "BearerAuth",
    "DigestAuth",
    "resolve_auth",
    "_parse_digest_challenge",
]
