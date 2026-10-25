import importlib.metadata
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from llm4free.browser_requests._http.compat import Session
from packaging import version

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    HAS_RICH = True
except ImportError:

    class _Dummy:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def print(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        @staticmethod
        def assemble(*_args: Any, **_kwargs: Any) -> str:
            return ""

    Console = _Dummy  # ty:ignore[invalid-assignment]
    Panel = _Dummy  # ty:ignore[invalid-assignment]
    Text = _Dummy  # ty:ignore[invalid-assignment]
    HAS_RICH = False

PYPI_URL = "https://pypi.org/pypi/llm4free/json"
YOUTUBE_URL = "https://youtube.com/@OEvortex"
GITHUB_URL = "https://github.com/OEvortex/LLM4Free"
CACHE_FILE = Path(tempfile.gettempdir()) / "llm4free_update_check.cache"

session = Session()


def get_installed_version() -> str:
    """Get the currently installed version of llm4free."""
    try:
        from .version import __version__

        return __version__
    except (ImportError, ValueError):
        pass

    try:
        import llm4free.version

        return llm4free.version.__version__
    except (ImportError, AttributeError):
        pass

    try:
        return importlib.metadata.version("llm4free")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def get_pypi_versions() -> Dict[str, Optional[str]]:
    """Get stable and latest versions from PyPI."""
    try:
        response = session.get(PYPI_URL, timeout=3)
        response.raise_for_status()
        data = response.json()

        stable = data.get("info", {}).get("version")

        releases = data.get("releases", {}).keys()
        parsed_versions = []
        for v in releases:
            try:
                parsed_versions.append(version.parse(v))
            except Exception:
                continue

        all_versions = sorted(parsed_versions)
        latest = str(all_versions[-1]) if all_versions else stable

        return {"stable": stable, "latest": latest}
    except Exception:
        return {"stable": None, "latest": None}


def should_check(force: bool = False) -> bool:
    """Check if we should perform an update check based on cache."""
    if os.environ.get("LLM4FREE_NO_UPDATE"):
        return False

    if force:
        return True

    try:
        if not CACHE_FILE.exists():
            return True

        last_check = float(CACHE_FILE.read_text().strip())
        if time.time() - last_check > 43200:
            return True
    except Exception:
        return True
    return False


def mark_checked() -> Any:
    """Mark the current time as the last update check."""
    try:
        CACHE_FILE.write_text(str(time.time()))
    except Exception:
        pass


def is_venv() -> bool:
    """Check if we are running inside a virtual environment."""
    return hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )


def get_env_name() -> str:
    """Get the name of the current environment."""
    if is_venv():
        return os.path.basename(sys.prefix)
    return "Global"


def format_update_message(current: str, new: str, utype: str) -> str:
    """Format the update message with colors and style."""
    cmd = "pip install -U llm4free"
    if utype == "Pre-release" or version.parse(new).is_prerelease:
        cmd = "pip install -U --pre llm4free"

    if HAS_RICH:
        from io import StringIO

        capture = StringIO()
        console = Console(file=capture, force_terminal=True, width=80)

        content = Text.assemble(
            ("A new ", "white"),
            (f"{utype} ", "bold yellow" if utype == "Pre-release" else "bold green"),
            ("version of LLM4Free is available!\n\n", "white"),
            ("Current:     ", "white"),
            (f"{current}", "bold red"),
            ("\n", ""),
            ("Latest:      ", "white"),
            (f"{new}", "bold green"),
            ("\n\n", ""),
            ("To update, run: ", "white"),
            (f"{cmd}", "bold cyan"),
            ("\n\n", ""),
            ("Subscribe to my YouTube: ", "dim"),
            (f"{YOUTUBE_URL}", "dim cyan"),
            ("\n", ""),
            ("Star on GitHub: ", "dim"),
            (f"{GITHUB_URL}", "dim cyan"),
        )

        panel = Panel(
            content,
            title="[bold magenta]Update Available[/bold magenta]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 2),
        )
        console.print(panel)
        return capture.getvalue()
    else:
        return (
            f"\n\033[1;36m[ LLM4Free Update ]\033[0m\n"
            f"New {utype} version available: \033[1;32m{new}\033[0m (Current: \033[1;31m{current}\033[0m)\n"
            f"Run: \033[1;33m{cmd}\033[0m to update.\n"
            f"\033[1;32mYouTube: {YOUTUBE_URL}\033[0m\n"
        )


def format_dev_message(current: str, latest: str) -> str:
    """Format the message for development versions."""
    if HAS_RICH:
        from io import StringIO

        capture = StringIO()
        console = Console(file=capture, force_terminal=True, width=80)

        content = Text.assemble(
            ("You are running a ", "white"),
            ("Development Version", "bold yellow"),
            ("\n\nLocal Version: ", "white"),
            (f"{current}", "bold cyan"),
            ("\n", ""),
            ("Latest PyPI:   ", "white"),
            (f"{latest}", "bold green"),
            ("\n\n", ""),
            ("YouTube: ", "dim"),
            (f"{YOUTUBE_URL}", "dim cyan"),
        )

        panel = Panel(
            content,
            title="[bold blue]LLM4Free Dev Mode[/bold blue]",
            border_style="yellow",
            expand=False,
            padding=(1, 2),
        )
        console.print(panel)
        return capture.getvalue()
    else:
        return (
            f"\n\033[1;33m[ LLM4Free Info ]\033[0m\n"
            f"You're running a development version (\033[1;36m{current}\033[0m)\n"
            f"Latest stable release: \033[1;32m{latest}\033[0m\n"
            f"\033[1;32mYouTube: {YOUTUBE_URL}\033[0m\n"
        )


def check_for_updates(force: bool = False) -> Optional[str]:
    """
    Check if a newer version of LLM4Free is available.

    Args:
        force (bool): If True, ignore cache and force check.

    Returns:
        Optional[str]: Formatted update message or None.
    """
    if not sys.stdout.isatty() and not force:
        return None

    if not should_check(force):
        return None

    try:
        installed_str = get_installed_version()
        installed_v = version.parse(installed_str)

        pypi = get_pypi_versions()
        mark_checked()

        stable_ver = pypi.get("stable")
        latest_ver = pypi.get("latest")

        if not stable_ver or not latest_ver:
            return None

        latest_stable_str = stable_ver
        latest_stable_v = version.parse(latest_stable_str)

        latest_any_str = latest_ver
        latest_any_v = version.parse(latest_any_str)

        is_prerelease = installed_v.is_prerelease

        if is_prerelease:
            if installed_v < latest_any_v:
                utype = "Pre-release" if latest_any_v.is_prerelease else "Stable"
                return format_update_message(installed_str, latest_any_str, utype)
            elif installed_v > latest_any_v:
                return format_dev_message(installed_str, latest_any_str)
        else:
            if installed_v < latest_stable_v:
                return format_update_message(installed_str, latest_stable_str, "Stable")
            elif installed_v > latest_stable_v:
                return format_dev_message(installed_str, latest_stable_str)

    except Exception:
        pass

    return None


if __name__ == "__main__":
    from litprinter import ic
    msg = check_for_updates(force=True)
    if msg:
        print(msg)
