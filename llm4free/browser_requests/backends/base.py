"""Backend contract shared by every browser engine driver.

A backend owns the engine-specific details (CLI bridge vs native CDP socket)
behind one async interface used by :class:`...browser_requests.cdp.CDPSession`
— the compatible facade. Swapping backends never changes provider code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseBackend(ABC):
    """Abstract async browser backend."""

    engine: str = "abstract"

    # Network instrumentation (populated by native backends; CLI keeps empty).
    network_requests: List[dict]
    network_responses: List[dict]
    # Console ring shared by poll_console / install_console_capture.
    console_buffer: List[str]

    @abstractmethod
    async def start(self) -> None:
        """Make the engine ready (launch/connect; open a working tab)."""

    @abstractmethod
    async def navigate(self, url: str, force: bool = False) -> None:
        """Navigate the tab to ``url`` and wait for it to settle."""

    @abstractmethod
    async def evaluate_js(self, expression: str) -> Any:
        """Execute JavaScript and return the plain value."""

    @abstractmethod
    async def evaluate_js_stdin(self, expression: str) -> Any:
        """Execute large JavaScript (streamed on stdin for CLI engines)."""

    @abstractmethod
    async def get_user_agent(self) -> str:
        """Current browser user agent."""

    @abstractmethod
    async def get_cookies_list(self, urls: Optional[List[str]] = None) -> List[dict]:
        """Full cookie objects (name, value, domain, path, ...)."""

    @abstractmethod
    async def set_cookies(self, cookies: List[dict]) -> None:
        """Install cookies into the browser session."""

    @abstractmethod
    async def get_title(self) -> str:
        """Page title as plain text."""

    @abstractmethod
    async def click(self, x: int = 200, y: int = 400) -> None:
        """Human-ish focus click to feed bot checks."""

    @abstractmethod
    async def click_selector(self, selector: str) -> None:
        """Click an element by CSS selector (comma fallbacks allowed)."""

    @abstractmethod
    async def mouse_move(self, x: int, y: int) -> None:
        """Pointer gesture."""

    @abstractmethod
    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        """Scroll the active page."""

    @abstractmethod
    async def install_console_capture(self) -> None:
        """Set up console streaming for :meth:`poll_console`."""

    @abstractmethod
    async def poll_console(self, marker: str, timeout: float = 30.0,
                           interval: float = 0.5) -> Optional[str]:
        """First buffered console line containing ``marker`` (or None)."""

    @abstractmethod
    async def wait_for_event(self, method: str, timeout: float = 30.0) -> dict:
        """Await one CDP event (native) or approximate it (CLI)."""

    def add_event_handler(self, method: str, destination: Any) -> None:
        """Register a queue/list/callback for CDP events (optional)."""

    def remove_event_handler(self, method: str, destination: Any) -> None:
        """Unregister a destination (optional)."""

    @abstractmethod
    async def close(self) -> None:
        """Release engine resources (tab close, process stop, disconnect)."""


__all__ = ["BaseBackend"]
