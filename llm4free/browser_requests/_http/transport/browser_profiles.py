"""Browser impersonation catalog and ordered-header profiles.

The target names, aliases and defaults mirror ``curl_cffi.requests.impersonate``
so ``impersonate=`` accepts the exact same strings either way.

What this module powers depends on which transport is in play:

* With the optional ``primp`` backend installed, the *real* fingerprint
  (TLS ClientHello/JA3, HTTP/2 SETTINGS, and the browser's own header order) is
  produced inside the native ``primp`` library — nothing here is used for it;
  only the target name is forwarded (mapped to a supported primp target).
* Without ``primp`` (the pure-stdlib path), the :class:`StdImpersonationTransport`
  uses :func:`profile_headers` to send a realistic, **correctly ordered** set of
  browser request headers. That defeats header-order / header-set based bot
  checks; it cannot fake the TLS fingerprint, which is why ``primp`` stays
  recommended for fingerprint walls such as Cloudflare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Headers

# --- target catalog (copied from curl_cffi.requests.impersonate) -----------

BrowserTypeLiteral = (
    # Edge
    "edge99", "edge101",
    # Chrome
    "chrome99", "chrome100", "chrome101", "chrome104", "chrome107", "chrome110",
    "chrome116", "chrome119", "chrome120", "chrome123", "chrome124", "chrome131",
    "chrome133a", "chrome136", "chrome142", "chrome99_android", "chrome131_android",
    # Safari
    "safari153", "safari155", "safari170", "safari172_ios", "safari180",
    "safari180_ios", "safari184", "safari184_ios", "safari260", "safari2601",
    "safari260_ios",
    # Firefox
    "firefox133", "firefox135", "firefox144", "tor145",
)

DEFAULT_CHROME = "chrome142"
DEFAULT_EDGE = "edge101"
DEFAULT_SAFARI = "safari2601"
DEFAULT_SAFARI_IOS = "safari260_ios"
DEFAULT_CHROME_ANDROID = "chrome131_android"
DEFAULT_FIREFOX = "firefox144"
DEFAULT_TOR = "tor145"

# Aliases (plain family names and older spellings) -> concrete target name.
REAL_TARGET_MAP: dict[str, str] = {
    "chrome": DEFAULT_CHROME,
    "edge": DEFAULT_EDGE,
    "safari": DEFAULT_SAFARI,
    "safari_ios": DEFAULT_SAFARI_IOS,
    "safari_beta": DEFAULT_SAFARI,
    "safari_ios_beta": DEFAULT_SAFARI_IOS,
    "chrome_android": DEFAULT_CHROME_ANDROID,
    "firefox": DEFAULT_FIREFOX,
    "tor": DEFAULT_TOR,
}

# Legacy underscore spellings curl_cffi still accepts.
_DEPRECATED_ALIASES: dict[str, str] = {
    "safari15_3": "safari153",
    "safari15_5": "safari155",
    "safari17_0": "safari170",
    "safari17_2_ios": "safari172_ios",
    "safari18_0": "safari180",
    "safari18_0_ios": "safari180_ios",
    "safari18_4": "safari184",
    "safari18_4_ios": "safari184_ios",
}

KNOWN_TARGETS: tuple[str, ...] = tuple(
    sorted({*BrowserTypeLiteral, *REAL_TARGET_MAP, *_DEPRECATED_ALIASES})
)


def normalize_browser_type(item: str | None) -> str | None:
    """Resolve an alias to a concrete target name (curl_cffi compatible)."""
    if item is None:
        return None
    if item in _DEPRECATED_ALIASES:
        return _DEPRECATED_ALIASES[item]
    if item in REAL_TARGET_MAP:
        return REAL_TARGET_MAP[item]
    return item


# --- ordered header profiles ----------------------------------------------

# The synthetic values our plain (non-impersonated) client puts on every request.
# When impersonating we drop them so the browser-realistic values win.
_LIB_DEFAULT_UA = "llm4free-http/1.0 (+stdlib)"

_FAMILY_RE = re.compile(r"^(chrome|edge|safari|firefox|tor|deku|okhttp)(\d*)")


@dataclass(frozen=True)
class _Profile:
    family: str
    major: int
    platform: str  # "windows" | "macos" | "ios" | "android"
    brand: str  # sec-ch-ua brand, e.g. "Google Chrome" / "Microsoft Edge"


def _family_of(target: str) -> _Profile:
    m = _FAMILY_RE.match(target)
    family = m.group(1) if m else "chrome"
    digits = m.group(2) if m else ""
    major = int(digits) if digits else 0
    if family == "edge":
        brand, plat, maj = "Microsoft Edge", "windows", major or 101
    elif family == "safari":
        brand, plat, maj = "Safari", "macos", major or 17
    elif family == "firefox":
        brand, plat, maj = "Firefox", "windows", major or 133
    elif family == "tor":
        brand, plat, maj = "Tor Browser", "windows", major or 13
    elif family.endswith("_android") or "android" in target:
        brand, plat, maj = "Google Chrome", "android", major or 131
    elif "ios" in target:
        brand, plat, maj = "Safari", "ios", major or 17
    else:
        brand, plat, maj = "Google Chrome", "windows", major or 142
    return _Profile(family=family, major=maj, platform=plat, brand=brand)


def _user_agent(p: _Profile) -> str:
    if p.family in ("chrome", "edge"):
        base = {
            "windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
            "macos": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
            "android": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/{v}.0.0.0 Mobile Safari/537.36",
        }[p.platform].format(v=p.major)
        if p.family == "edge":
            base += f" Edg/{p.major}.0.0.0"
        return base
    if p.family == "safari":
        if p.platform == "ios":
            return (
                f"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{p.major}.0 Mobile/"
                f"15E148 Safari/604.1"
            )
        return (
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            f"(KHTML, like Gecko) Version/{p.major}.0 Safari/605.1.15"
        )
    if p.family in ("firefox", "tor"):
        plat = {
            "windows": "Windows NT 10.0; Win64; x64",
            "macos": "Macintosh; Intel Mac OS X 10.15",
            "android": "Android 100; Mobile",
            "ios": "iPhone; CPU iPhone OS 16.0 like Mac OS X",
        }[p.platform]
        return (
            f"Mozilla/5.0 ({plat}; rv:{p.major}.0) Gecko/20100101 "
            f"{p.brand.title()}/{p.major}.0"
        )
    return _LIB_DEFAULT_UA


def _sec_ch_ua(p: _Profile) -> str:
    return (
        f'"Not/A)Brand";v="8", "Chromium";v="{p.major}", "{p.brand}";v="{p.major}"'
    )


def _platform_header(p: _Profile) -> str:
    return {
        "windows": '"Windows"',
        "macos": '"macOS"',
        "android": '"Android"',
        "ios": '"iOS"',
    }[p.platform]


def _is_chromium(p: _Profile) -> bool:
    return p.family in ("chrome", "edge")


def default_headers(target: str) -> Headers:
    """Ordered, browser-realistic *default* headers for ``target`` (no Host/Cookie)."""
    p = _family_of(target)
    vals: dict[str, str] = {}
    order: list[str] = []

    def add(name: str, value: str) -> None:
        if name not in vals:
            order.append(name)
        vals[name] = value

    if _is_chromium(p):
        add("sec-ch-ua", _sec_ch_ua(p))
        add("sec-ch-ua-mobile", "?1" if p.platform in ("android", "ios") else "?0")
        add("sec-ch-ua-platform", _platform_header(p))
        add("Upgrade-Insecure-Requests", "1")
    if p.family in ("firefox", "tor"):
        add("Upgrade-Insecure-Requests", "1")
    add("User-Agent", _user_agent(p))
    add(
        "Accept",
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8",
    )
    if p.family == "safari":
        add(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        )
    if _is_chromium(p):
        add("Sec-Fetch-Site", "none")
        add("Sec-Fetch-Mode", "navigate")
        add("Sec-Fetch-Dest", "document")
        add("Connection", "keep-alive")
    elif p.family == "safari":
        add("Sec-Fetch-Dest", "document")
        add("Sec-Fetch-Mode", "navigate")
        add("Sec-Fetch-Site", "none")
        add("Connection", "keep-alive")
        add("Sec-GPC", "1")
    else:  # firefox
        add("Connection", "keep-alive")
        add("Sec-Fetch-Dest", "document")
        add("Sec-Fetch-Mode", "navigate")
        add("Sec-Fetch-Site", "none")
        add("Sec-Fetch-User", "?1")
        add("DNT", "1")
        add("Sec-GPC", "1")
    # stdlib only decodes gzip/deflate, so never advertise br/zstd we can't read.
    add("Accept-Encoding", "gzip, deflate")
    add("Accept-Language", "en-US,en;q=0.9")

    ordered = Headers([(name, vals[name]) for name in order])
    return ordered


def apply_profile(existing: Headers | None, target: str) -> Headers:
    """Return browser-ordered headers seeded by ``target`` with ``existing`` winning.

    User-supplied headers override the profile value for the same name (keeping
    the browser position), unknown headers are appended. Synthetic defaults the
    plain client injects (our library UA / ``Connection: close``) are dropped so
    the browser values are used.
    """
    prof = default_headers(target)
    overrides: dict[str, tuple[str, str]] = {}
    extras: list[tuple[str, str]] = []
    if existing:
        for name, value in existing.items():
            low = name.lower()
            if low == "user-agent" and value == _LIB_DEFAULT_UA:
                continue
            if low == "connection" and value.lower() == "close":
                continue
            if low in {n.lower() for n in prof.keys()}:
                overrides[low] = (name, value)
            else:
                extras.append((name, value))

    items: list[tuple[str, str]] = []
    for name, value in prof.items():
        rep = overrides.pop(name.lower(), None)
        if rep is not None:
            items.append(rep)
        else:
            items.append((name, value))
    items.extend(overrides.values())  # overridden names not in profile order (rare)
    items.extend(extras)
    return Headers(items)


__all__ = [
    "BrowserTypeLiteral",
    "KNOWN_TARGETS",
    "REAL_TARGET_MAP",
    "normalize_browser_type",
    "default_headers",
    "apply_profile",
]
