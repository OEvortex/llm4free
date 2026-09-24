"""LLM4Free search module - unified search interfaces."""

from __future__ import annotations

from typing import Dict, Set, Tuple, Type, cast

from .base import BaseSearch, BaseSearchEngine
from .bing_main import BingSearch
from .brave_main import BraveSearch
from .duckduckgo_main import DuckDuckGoSearch

# Import new search engines
from .engines.mojeek import Mojeek
from .engines.parallel import Parallel
from .engines.serpbase import SerpBase
from .engines.wikipedia import Wikipedia

# Import result models
from .results import (
    BooksResult,
    ImagesResult,
    NewsResult,
    TextResult,
    VideosResult,
)
from .yahoo_main import YahooSearch

# Search engine registry: class name -> class object
SEARCH_PROVIDERS: Dict[str, Type[BaseSearchEngine]] = cast(
    Dict[str, Type[BaseSearchEngine]],
    {
        "BingSearch": BingSearch,
        "BraveSearch": BraveSearch,
        "DuckDuckGoSearch": DuckDuckGoSearch,
        "Mojeek": Mojeek,
        "Parallel": Parallel,
        "SerpBase": SerpBase,
        "Wikipedia": Wikipedia,
        "YahooSearch": YahooSearch,
    },
)

# Search providers that require API authentication
SEARCH_AUTH_REQUIRED: Set[str] = {
    name for name, cls in SEARCH_PROVIDERS.items() if getattr(cls, "required_auth", False)
}


def _get_available_search_engines(api_key: str | None = None) -> Dict[str, Type[BaseSearchEngine]]:
    """Return search providers available without authentication, or all if `api_key` is provided."""
    if api_key:
        return dict(SEARCH_PROVIDERS)
    return {name: cls for name, cls in SEARCH_PROVIDERS.items() if name not in SEARCH_AUTH_REQUIRED}


__all__ = [
    # Base classes
    "BaseSearch",
    "BaseSearchEngine",
    # Main search interfaces
    "BraveSearch",
    "DuckDuckGoSearch",
    "BingSearch",
    "YahooSearch",
    # Individual engines
    "Mojeek",
    "Parallel",
    "SerpBase",
    "Wikipedia",
    # Registry
    "SEARCH_PROVIDERS",
    "SEARCH_AUTH_REQUIRED",
    "_get_available_search_engines",
    # Result models
    "TextResult",
    "ImagesResult",
    "VideosResult",
    "NewsResult",
    "BooksResult",
]
