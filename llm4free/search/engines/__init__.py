"""Static imports for all search engine modules."""

from __future__ import annotations

from ..base import BaseSearchEngine
from .bing import BingBase, BingImagesSearch, BingNewsSearch, BingSuggestionsSearch, BingTextSearch
from .brave import (
    BraveBase,
    BraveImages,
    BraveNews,
    BraveSuggestions,
    BraveTextSearch,
    BraveVideos,
)
from .duckduckgo import (
    DuckDuckGoAnswers,
    DuckDuckGoBase,
    DuckDuckGoImages,
    DuckDuckGoMaps,
    DuckDuckGoNews,
    DuckDuckGoSuggestions,
    DuckDuckGoTextSearch,
    DuckDuckGoTranslate,
    DuckDuckGoVideos,
    DuckDuckGoWeather,
)
from .mojeek import Mojeek
from .parallel import Parallel
from .serpbase import SerpBase
from .wikipedia import Wikipedia
from .yahoo import (
    YahooImages,
    YahooNews,
    YahooSearchEngine,
    YahooSuggestions,
    YahooText,
    YahooVideos,
)

# Engine categories mapping
ENGINES = {
    "text": {
        "brave": BraveTextSearch,
        "mojeek": Mojeek,
        "parallel": Parallel,
        "serpbase": SerpBase,
        "bing": BingTextSearch,
        "duckduckgo": DuckDuckGoTextSearch,
        "yahoo": YahooText,
    },
    "images": {
        "bing": BingImagesSearch,
        "brave": BraveImages,
        "duckduckgo": DuckDuckGoImages,
        "yahoo": YahooImages,
    },
    "videos": {
        "brave": BraveVideos,
        "duckduckgo": DuckDuckGoVideos,
        "yahoo": YahooVideos,
    },
    "news": {
        "brave": BraveNews,
        "bing": BingNewsSearch,
        "duckduckgo": DuckDuckGoNews,
        "yahoo": YahooNews,
    },
    "suggestions": {
        "brave": BraveSuggestions,
        "bing": BingSuggestionsSearch,
        "duckduckgo": DuckDuckGoSuggestions,
        "yahoo": YahooSuggestions,
    },
    "answers": {
        "duckduckgo": DuckDuckGoAnswers,
    },
    "maps": {
        "duckduckgo": DuckDuckGoMaps,
    },
    "translate": {
        "duckduckgo": DuckDuckGoTranslate,
    },
    "weather": {
        "duckduckgo": DuckDuckGoWeather,
    },
}

__all__ = [
    "BraveBase",
    "BraveTextSearch",
    "BraveImages",
    "BraveVideos",
    "BraveNews",
    "BraveSuggestions",
    "Mojeek",
    "Parallel",
    "SerpBase",
    "Wikipedia",
    "BingBase",
    "BingTextSearch",
    "BingImagesSearch",
    "BingNewsSearch",
    "BingSuggestionsSearch",
    "DuckDuckGoBase",
    "DuckDuckGoTextSearch",
    "DuckDuckGoImages",
    "DuckDuckGoVideos",
    "DuckDuckGoNews",
    "DuckDuckGoAnswers",
    "DuckDuckGoSuggestions",
    "DuckDuckGoMaps",
    "DuckDuckGoTranslate",
    "DuckDuckGoWeather",
    "YahooSearchEngine",
    "YahooText",
    "YahooImages",
    "YahooVideos",
    "YahooNews",
    "YahooSuggestions",
    "BaseSearchEngine",
    "ENGINES",
]
