"""Browser process discovery, launching and a refcounted process pool.

Owns one shared browser engine per port so that dozens of provider sessions
across the codebase reuse a single browser process — that is the "low RAM"
half of this package's design (a shared, refcounted browser pool):

* :func:`acquire` returns a running CDP endpoint, launching ``lightpanda``
  or stealth Chrome only when nothing is listening yet;
* :func:`release` drops a refcount; the engine shuts down once the last
  session closes (or via :func:`shutdown_all` from ``atexit``).

Note on UA policy: lightpanda deliberately forbids impersonating other
browsers (its ``--user-agent`` flag rejects any value containing
``"Mozilla"``); the CDP ``Network/Emulation.setUserAgentOverride`` commands
are accepted but ignored by current builds. Stealth-critical flows should
use the ``chrome`` engine (our launcher already sets a clean, non-
HeadlessChrome UA plus ``--disable-blink-features=AutomationControlled``).
"""

from __future__ import annotations
from litprinter import ic

import asyncio
import atexit
import dataclasses
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import weakref
from typing import Dict, Optional, Tuple

from .proxy_auth import parse_proxy, resolve_proxy_str



# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def find_lightpanda_path() -> Optional[str]:
    """Locate a lightpanda executable (env override, PATH, or config dir)."""
    override = os.environ.get("LLM4FREE_LIGHTPANDA")
    if override and os.path.exists(override):
        return override
    found = shutil.which("lightpanda")
    if found:
        return found
    config_cache = os.path.join(os.path.expanduser("~"), ".local", "bin", "lightpanda")
    if os.path.exists(config_cache):
        return config_cache
    return None


def find_chrome_binary() -> str:
    """Locate a real Chrome/Chromium binary for stealth mode.

    Search order: ``$LLM4FREE_CHROME_PATH``, common binaries on PATH, then
    the browser agent-browser installs under its own home.

    Raises:
        RuntimeError: If no Chrome/Chromium binary can be found.
    """
    env_path = os.environ.get("LLM4FREE_CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        found = shutil.which(name)
        if found:
            return found
    # agent-browser install fallback (chrome-<ver>/chrome).
    home = os.path.expanduser("~/.agent-browser")
    if os.path.isdir(home):
        browsers = os.path.join(home, "browsers")
        for entry in sorted(os.listdir(browsers), reverse=True):
            candidate = os.path.join(browsers, entry, "chrome")
            if os.path.exists(candidate):
                return candidate
    # Playwright cache fallback (chromium-<rev>/chrome-linux*/chrome).
    cache_dir = os.path.expanduser("~/.cache/ms-playwright")
    if os.path.isdir(cache_dir):
        for entry in sorted(
            (e for e in os.listdir(cache_dir) if e.startswith("chromium-")),
            reverse=True,
        ):
            for sub in ("chrome-linux64", "chrome-linux", "chrome"):
                candidate = os.path.join(cache_dir, entry, sub, "chrome")
                if os.path.exists(candidate):
                    return candidate
    raise RuntimeError(
        "Chrome/Chromium not found for stealth mode. "
        "Install Chrome or set LLM4FREE_CHROME_PATH."
    )


def cdp_alive(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check whether a CDP endpoint already answers on ``host:port``."""
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/json/version", timeout=timeout
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def free_port() -> int:
    """Reserve a free TCP loopback port (best effort, single-shot)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _chrome_user_agent(binary: str) -> str:
    """Realistic (HeadlessChrome-free) user agent string for the launch flag."""
    from .stealth import masked_chrome_user_agent

    return masked_chrome_user_agent(binary=binary)


# --------------------------------------------------------------------------- #
# Stealth Chrome launch
# --------------------------------------------------------------------------- #
def launch_stealth_chrome(
    port: int = 9222,
    host: str = "127.0.0.1",
    user_data_dir: Optional[str] = None,
    headless: bool = True,
    proxy: Optional[str] = None,
) -> Tuple[Optional[subprocess.Popen], Optional[str]]:
    """Launch a real Chrome optimized to pass Cloudflare Turnstile headless.

    ``--disable-blink-features=AutomationControlled`` keeps
    ``navigator.webdriver`` ``false``, the user agent is masked to a genuine
    ``Chrome`` release, and ``--headless=new`` semantics are used.

    Args:
        proxy: Optional HTTP(S)/SOCKS proxy URL (credentials are stripped;
            the native backend answers the ``407`` challenge over CDP). When
            set, Chrome is launched with ``--proxy-server`` so *all* its
            network — including in-page ``fetch`` — egresses through it.

    Returns:
        ``(process, profile_dir_or_None)``; ``(None, None)`` when an existing
        CDP endpoint was already listening on the port (reuse instead of a
        second launch).
    """
    if cdp_alive(host, port):
        return None, None

    binary = find_chrome_binary()
    flags = [
        binary,
        f"--remote-debugging-port={port}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1366,768",
        f"--user-agent={_chrome_user_agent(binary)}",
    ]
    if proxy:
        spec = parse_proxy(proxy)
        if spec is not None:
            flags.append(f"--proxy-server={spec.server}")
    if headless:
        flags.append("--headless=new")

    profile_dir: Optional[str] = None
    if user_data_dir:
        profile_dir = user_data_dir
        flags.append(f"--user-data-dir={profile_dir}")
    elif headless:
        profile_dir = tempfile.mkdtemp(prefix="llm4free-chrome-")
        flags.append(f"--user-data-dir={profile_dir}")

    flags.append("about:blank")

    for attempt in range(5):
        proc = subprocess.Popen(
            flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                break  # crashed (e.g. port taken) — retry with a new profile
            if cdp_alive(host, port):
                return proc, profile_dir
            time.sleep(0.2)
        if proc.poll() is None:
            proc.terminate()
        time.sleep(1.0)
    raise RuntimeError(f"Failed to launch stealth Chrome on port {port}")


# --------------------------------------------------------------------------- #
# Lightpanda launch
# --------------------------------------------------------------------------- #
def launch_lightpanda(
    port: int,
    host: str = "127.0.0.1",
) -> Optional[subprocess.Popen]:
    """Start a lightpanda CDP server (returns ``None`` when unavailable).

    Note: lightpanda has no ``--user-agent`` serve flag; UA masking is done
    per-session over CDP (``Network.setUserAgentOverride``) by the native
    backend when ``mask_user_agent`` is requested.
    """
    exe = find_lightpanda_path()
    if not exe:
        return None
    cmdline = [
        exe, "serve", "--host", host, "--port", str(port), "--log-level", "error",
        # SSRF guard (matches lightpanda's own recommended practice);
        # disable with LLM4FREE_ALLOW_LOCAL_NETS=1 for scraping localhost.
        "--block-private-networks",
        # Pull sub-resources for richer JS-driven pages (iframes needed by
        # Turnstile-style widgets); enable images too unless told otherwise.
        "--load-resources", "iframe",
    ]
    if os.environ.get("LLM4FREE_ALLOW_LOCAL_NETS"):
        cmdline.remove("--block-private-networks")
    if os.environ.get("LLM4FREE_LIGHTPANDA_IMAGES"):
        cmdline += ["--load-resources", "image"]
    if os.environ.get("LLM4FREE_LIGHTPANDA_OBEY_ROBOTS"):
        cmdline.append("--obey-robots")
    try:
        proc = subprocess.Popen(
            cmdline,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    deadline = time.time() + 10
    while time.time() < deadline:
        if proc.poll() is not None:
            return None
        if cdp_alive(host, port):
            return proc
        time.sleep(0.1)
    proc.terminate()
    return None


# --------------------------------------------------------------------------- #
# Refcounted shared-browser registry
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class _Lease:
    proc: Optional[subprocess.Popen]
    profile: Optional[str]
    refs: int = 0
    engine: str = "unknown"
    user_data_dir: Optional[str] = None
    proxy: Optional[str] = None


_POOL: Dict[Tuple[str, int], _Lease] = {}
# The pool is mutated from many event loops (each provider call runs its own
# ``asyncio.run`` in a worker thread). A single module-level ``asyncio.Lock``
# binds to whichever loop first awaits it and then raises "bound to a different
# event loop" on every subsequent loop, so the lock is held per-loop instead.
# ``WeakKeyDictionary`` drops the entry once a loop is garbage-collected.
_POOL_LOCKS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _get_pool_lock() -> asyncio.Lock:
    """Return the pool lock owned by the *current* running event loop."""
    loop = asyncio.get_running_loop()
    lock = _POOL_LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _POOL_LOCKS[loop] = lock
    return lock


async def _compatible_running_lease(
    engine: str, host: str, user_data_dir: Optional[str], proxy: Optional[str] = None
) -> Optional[Tuple[str, int]]:
    """Find a live engine lease we can share (same engine + profile + proxy).

    Chrome leases are only shared when the profile *and* proxy match, since a
    proxy is baked into the launch flags; lightpanda is always shareable.
    """
    want_proxy = resolve_proxy_str(proxy)
    for key, lease in _POOL.items():
        if key[0] != host or lease.engine != engine or lease.refs == 0:
            continue
        if engine == "chrome" and (lease.user_data_dir or None) != (user_data_dir or None):
            continue
        if engine == "chrome" and (lease.proxy or None) != want_proxy:
            continue
        if await asyncio.to_thread(cdp_alive, host, key[1]):
            return key
    return None


async def acquire(
    engine: str,
    host: str,
    port: Optional[int],
    headless: bool = True,
    user_data_dir: Optional[str] = None,
    mask_user_agent: bool = True,
    proxy: Optional[str] = None,
) -> Tuple[str, int, bool]:
    """Get (or start) a CDP endpoint for ``engine`` and hold a refcount slot.

    Sessions with matching engine/profile/proxy reuse ONE launched browser
    process; Chrome-style engines additionally require an equal
    ``user_data_dir`` *and* ``proxy`` for sharing (both are baked into the
    launch flags).

    Args:
        engine: ``"lightpanda"`` or ``"chrome"``. ``"chrome"`` reuses any
            listening CDP endpoint first (Chrome, Chromium, ...).
        host: Bind host.
        port: Requested port; ``None`` picks a free port (and prefers
            sharing an already-running engine of the same kind).
        headless: Passed to the Chrome launcher.
        user_data_dir: Chrome profile dir (persistent profile).
        mask_user_agent: For lightpanda: try to override its own UA at the
            CDP level (kept for API parity; current builds ignore it).
        proxy: Chrome ``--proxy-server`` proxy for the launched browser.
            lightpanda ignores it (its own SSRF guard governs networking).

    Returns:
        ``(host, port, ours)`` — ``ours`` is True when the caller is now a
        refcount owner of a browser registered in our pool and must call
        :func:`release`.
    """
    proxy = resolve_proxy_str(proxy)
    async with _get_pool_lock():
        # Explicit port: adopt whatever listens there (no pool bookkeeping).
        if port is not None:
            if not await asyncio.to_thread(cdp_alive, host, port):
                if engine == "lightpanda":
                    if find_lightpanda_path() is None:
                        raise RuntimeError(
                            "engine 'lightpanda' requested but no lightpanda "
                            "binary found (env LLM4FREE_LIGHTPANDA or PATH)"
                        )
                    proc = await asyncio.to_thread(launch_lightpanda, port, host)
                    if proc is None:
                        raise RuntimeError(
                            f"lightpanda failed to start on {host}:{port}"
                        )
                    _POOL[(host, port)] = _Lease(
                        proc=proc, profile=None, engine="lightpanda"
                    )
                elif engine == "chrome":
                    proc, profile_dir = await asyncio.to_thread(
                        launch_stealth_chrome, port, host, user_data_dir, headless, proxy
                    )
                    if proc is not None:
                        _POOL[(host, port)] = _Lease(
                            proc=proc, profile=profile_dir, engine="chrome",
                            user_data_dir=user_data_dir, proxy=proxy,
                        )
                else:
                    raise ValueError(f"unknown engine: {engine}")
                key = (host, port)
            else:
                key = None  # adopted external endpoint — nothing to release
        else:
            key = await _compatible_running_lease(engine, host, user_data_dir, proxy)
            if key is None:
                port = free_port()
                if engine == "lightpanda":
                    if find_lightpanda_path() is None:
                        raise RuntimeError(
                            "engine 'lightpanda' requested but no lightpanda "
                            "binary found (env LLM4FREE_LIGHTPANDA or PATH)"
                        )
                    proc = await asyncio.to_thread(launch_lightpanda, port, host)
                    if proc is None:
                        raise RuntimeError(
                            f"lightpanda failed to start on {host}:{port}"
                        )
                    key = (host, port)
                    _POOL[key] = _Lease(proc=proc, profile=None, engine="lightpanda")
                elif engine == "chrome":
                    proc, profile_dir = await asyncio.to_thread(
                        launch_stealth_chrome, port, host, user_data_dir, headless, proxy
                    )
                    if proc is not None:
                        key = (host, port)
                        _POOL[key] = _Lease(
                            proc=proc, profile=profile_dir, engine="chrome",
                            user_data_dir=user_data_dir, proxy=proxy,
                        )
                    else:
                        key = None  # external already running on that port
                else:
                    raise ValueError(f"unknown engine: {engine}")

        if key is None:
            if port is None:  # pragma: no cover — explicit path always has a port
                raise RuntimeError("internal: no port resolved")
            return host, port, False
        lease = _POOL.setdefault(key, _Lease(proc=None, profile=None, engine=engine))
        lease.refs += 1
        return key[0], key[1], True


async def release(host: str, port: int, engine: str = "chrome") -> None:
    """Drop one refcount slot; stop the browser at zero (if we launched it)."""
    async with _get_pool_lock():
        key = (host, port)
        lease = _POOL.get(key)
        if lease is None:
            return  # adopted external endpoint — nothing to release
        lease.refs = max(0, lease.refs - 1)
        if lease.refs == 0:
            _stop_lease(lease)
            _POOL.pop(key, None)


def _stop_lease(lease: _Lease) -> None:
    proc = lease.proc
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
    except Exception as e:
        ic("browser shutdown failed: %s", e)
    if lease.profile:
        shutil.rmtree(lease.profile, ignore_errors=True)


def shutdown_all() -> None:
    """Stop every browser we launched (registered on ``atexit``).

    Runs unconditionally — when this process dies nobody is left to hold
    the refcount, so a stranded lease must not outlive it.
    """
    for key, lease in list(_POOL.items()):
        _stop_lease(lease)
        _POOL.pop(key, None)


atexit.register(shutdown_all)


async def ensure_running(engine: str, host: Optional[str] = None,
                         port: Optional[int] = None, headless: bool = True,
                         user_data_dir: Optional[str] = None,
                         proxy: Optional[str] = None) -> Tuple[str, int]:
    """Simpler acquire that ignores the refcount bookkeeping bool."""
    h, p, _ = await acquire(
        engine, host or "127.0.0.1", port, headless, user_data_dir, proxy=proxy
    )
    return h, p
