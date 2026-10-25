# The `AwesomePrompts` class is a prompts manager in Python that fetches, caches, updates, and
# provides prompts with optimization features like LRU caching and concurrency.
# -*- coding: utf-8 -*-


import json
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Union

from llm4free.browser_requests._http.compat import Session
from rich.console import Console
from rich.table import Table

console = Console()


class AwesomePrompts:
    """Prompts manager with caching and optimization."""

    def __init__(
        self,
        repo_url: str = "https://raw.githubusercontent.com/OEvortex/prompts/main/prompt.json",
        local_path: Optional[str] = None,
        auto_update: bool = True,
        timeout: int = 10,
        impersonate: Optional[str] = "chrome110",
        cache_size: int = 128,
        max_workers: int = 4,
    ):
        """Initialize optimized Awesome Prompts.

        Args:
            repo_url: URL to fetch prompts from
            local_path: Where to save prompts locally
            auto_update: Auto update prompts on init
            timeout: Timeout for HTTP requests
            impersonate: Browser profile for the impersonation backend (primp)
            cache_size: LRU cache size for get operations
            max_workers: Max threads for concurrent operations
        """
        self.repo_url = repo_url
        self.local_path = (
            Path(local_path) if local_path else Path.home() / ".llm4free" / "awesome-prompts.json"
        )
        self.timeout = timeout
        self._last_update: Optional[datetime] = None
        self._cache_lock = threading.RLock()
        self._file_lock = threading.Lock()
        self._max_workers = max_workers

        self._max_workers = max_workers
        self.timeout = timeout
        try:
            self.session = Session(timeout=timeout, impersonate=impersonate)
        except Exception:
            self.session = Session(timeout=timeout)
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[Union[str, int], str] = {}
        self._load_cache()
        self._get_cached = lru_cache(maxsize=cache_size)(self._get_uncached)
        if auto_update:
            self.update_prompts_from_online()

    def _load_cache(self) -> None:
        """Initialize cache from local file."""
        try:
            if self.local_path.exists():
                with self._file_lock:
                    with open(self.local_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        with self._cache_lock:
                            self._cache = data
                        self._rebuild_numeric_indices()
        except (json.JSONDecodeError, IOError) as e:
            console.print(f"[red]Warning: Failed to load cache: {e}[/red]")
            self._cache = {}

    def _save_cache(self) -> None:
        """Save cache to local file with atomic write."""
        try:
            temp_path = self.local_path.with_suffix(".tmp")
            with self._file_lock:
                with open(temp_path, "w", encoding="utf-8") as f:
                    cache_to_save = {k: v for k, v in self._cache.items() if isinstance(k, str)}
                    json.dump(cache_to_save, f, indent=2, ensure_ascii=False, sort_keys=True)
                temp_path.replace(self.local_path)
        except IOError as e:
            console.print(f"[red]Error saving cache: {e}[/red]")

    def _load_prompts(self) -> Dict[Union[str, int], str]:
        """Load prompts from cache or file."""
        with self._cache_lock:
            if self._cache:
                return self._cache.copy()

        self._load_cache()
        self._rebuild_numeric_indices()
        with self._cache_lock:
            return self._cache.copy()

    def _rebuild_numeric_indices(self) -> None:
        """Rebuild numeric indices from string keys."""
        with self._cache_lock:
            numeric_keys = [k for k in self._cache.keys() if isinstance(k, int)]
            for key in numeric_keys:
                del self._cache[key]

            string_keys = [k for k in self._cache.keys() if isinstance(k, str)]
            for i, key in enumerate(string_keys):
                self._cache[i] = self._cache[key]

    def _save_prompts(self, prompts: Dict[Union[str, int], str]) -> None:
        """Save prompts and update cache."""
        with self._cache_lock:
            self._cache = prompts.copy()
        self._save_cache()

    def update_prompts_from_online(self, force: bool = False) -> bool:
        """Update prompts from repository with optimized merging."""
        try:
            if (
                not force
                and self._last_update
                and (datetime.now() - self._last_update) < timedelta(hours=1)
            ):
                console.print("[yellow]Prompts are already up to date![/yellow]")
                return True

            console.print("[cyan]Updating prompts...[/cyan]")

            response = self.session.get(self.repo_url)
            response.raise_for_status()

            new_prompts = response.json()
            if not isinstance(new_prompts, dict):
                raise ValueError("Invalid response format")

            existing_prompts = self._load_prompts()

            merged_prompts = {}
            string_keys = []

            for key, value in existing_prompts.items():
                if isinstance(key, str):
                    merged_prompts[key] = value
                    string_keys.append(key)

            for key, value in new_prompts.items():
                if isinstance(key, str):
                    merged_prompts[key] = value
                    if key not in string_keys:
                        string_keys.append(key)

            for i, key in enumerate(string_keys):
                merged_prompts[i] = merged_prompts[key]

            self._save_prompts(merged_prompts)
            self._last_update = datetime.now()

            console.print(
                f"[green]Updated {len([k for k in merged_prompts if isinstance(k, str)])} prompts successfully![/green]"
            )
            return True

        except Exception as e:
            error_msg = str(e)
            if hasattr(e, "response") and e.response is not None:
                status_code = getattr(e.response, "status_code", None)
                if status_code:
                    error_msg = f"HTTP {status_code}: {error_msg}"
            console.print(f"[red]Update failed: {error_msg}[/red]")
            return False

    def get_act(
        self,
        key: Union[str, int],
        default: Optional[str] = None,
        case_insensitive: bool = True,
        use_cache: bool = True,
    ) -> Optional[str]:
        """Get prompt with LRU caching for performance.

        Args:
            key: Prompt name or index
            default: Default value if not found
            case_insensitive: Enable case-insensitive matching
            use_cache: Use LRU cache for better performance
        """
        if use_cache:
            return self._get_cached(key, default, case_insensitive)
        return self._get_uncached(key, default, case_insensitive)

    def _get_uncached(
        self, key: Union[str, int], default: Optional[str] = None, case_insensitive: bool = True
    ) -> Optional[str]:
        """Core get logic without caching."""
        with self._cache_lock:
            prompts = self._cache if self._cache else self._load_prompts()

            if key in prompts:
                return prompts[key]

            if isinstance(key, str) and case_insensitive:
                key_lower = key.lower()
                for k, v in prompts.items():
                    if isinstance(k, str) and k.lower() == key_lower:
                        return v

        return default

    def add_prompt(self, name: str, prompt: str, validate: bool = True) -> bool:
        """Add a new prompt with validation and deduplication.

        Args:
            name: Name of the prompt
            prompt: The prompt text
            validate: Validate input and check for duplicates
        """
        if validate:
            if not name or not prompt:
                console.print("[red]Name and prompt cannot be empty![/red]")
                return False

            if len(name) > 100 or len(prompt) > 10000:
                console.print("[red]Name too long (max 100) or prompt too long (max 10000)[/red]")
                return False

        with self._cache_lock:
            prompts = self._load_prompts()

            if validate:
                for existing_name, existing_prompt in prompts.items():
                    if isinstance(existing_name, str) and existing_prompt == prompt:
                        console.print(
                            f"[yellow]Prompt with same content exists: '{existing_name}'[/yellow]"
                        )
                        return False

            prompts[name] = prompt

            string_keys = [k for k in prompts.keys() if isinstance(k, str)]
            for i, key in enumerate(string_keys):
                prompts[i] = prompts[key]

            self._save_prompts(prompts)

        console.print(f"[green]Added prompt: '{name}'[/green]")
        return True

    def delete_prompt(
        self, name: Union[str, int], case_insensitive: bool = True, raise_not_found: bool = False
    ) -> bool:
        """Delete a prompt with proper cleanup.

        Args:
            name: Name or index of prompt to delete
            case_insensitive: Enable case-insensitive matching
            raise_not_found: Raise error if prompt not found?
        """
        with self._cache_lock:
            prompts = self._load_prompts()

            if name in prompts:
                del prompts[name]

                string_keys = [k for k in prompts.keys() if isinstance(k, str)]
                numeric_keys = [k for k in prompts.keys() if isinstance(k, int)]
                for key in numeric_keys:
                    del prompts[key]

                for i, key in enumerate(string_keys):
                    prompts[i] = prompts[key]

                self._save_prompts(prompts)
                console.print(f"[green]Deleted prompt: '{name}'[/green]")
                return True

            if isinstance(name, str) and case_insensitive:
                name_lower = name.lower()
                for k in list(prompts.keys()):
                    if isinstance(k, str) and k.lower() == name_lower:
                        return self.delete_prompt(
                            k, case_insensitive=False, raise_not_found=raise_not_found
                        )

            if raise_not_found:
                raise KeyError(f"Prompt '{name}' not found!")
            console.print(f"[yellow]Prompt '{name}' not found![/yellow]")
            return False

    @property
    def all_acts(self) -> Dict[Union[str, int], str]:
        """Get all prompts with optimized indexing."""
        with self._cache_lock:
            if self._cache:
                return self._cache.copy()

        prompts = self._load_prompts()
        if not prompts:
            self.update_prompts_from_online()
            prompts = self._load_prompts()

        return prompts.copy()

    def show_acts(self, search: Optional[str] = None, limit: int = 100) -> None:
        """Display prompts with optimized filtering and pagination.

        Args:
            search: Filter by search term
            limit: Maximum number of prompts to display
        """
        prompts = self.all_acts

        filtered_items = []
        search_lower = search.lower() if search else None

        for key, value in prompts.items():
            if isinstance(key, int):
                continue

            if search_lower:
                if search_lower not in key.lower() and search_lower not in value.lower():
                    continue

            preview = value[:80] + "..." if len(value) > 80 else value
            filtered_items.append((str(key), preview))

            if len(filtered_items) >= limit:
                break

        if not filtered_items:
            console.print("[yellow]No prompts found[/yellow]")
            return

        table = Table(
            title=f"Awesome Prompts ({len(filtered_items)} shown)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Name", style="green", max_width=30)
        table.add_column("Preview", style="yellow", max_width=50)

        for name, preview in filtered_items:
            table.add_row(name, preview)

        console.print(table)

    def get_random_act(self) -> Optional[str]:
        """Get a random prompt."""
        prompts = self.all_acts
        string_keys = [k for k in prompts.keys() if isinstance(k, str)]
        if not string_keys:
            return None
        import random

        return prompts[random.choice(string_keys)]


if __name__ == "__main__":
    prompt_manager = AwesomePrompts()
    print(prompt_manager.get_random_act())
