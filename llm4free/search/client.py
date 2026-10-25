"""OpenAI-style unified search client.

Every registered search engine is exposed through a single resource:
``client.search.create(...)``. The shape mirrors the OpenAI SDK — one
``create`` entry point, a typed response object, ``.data`` iteration and
``to_dict()`` serialization — while ``engine="auto"`` fails over across
engines until one succeeds.

Examples:
    >>> from llm4free import Client
    >>> client = Client()
    >>> response = client.search.create(query="python web scraping")
    >>> response.engine
    'duckduckgo'
    >>> for result in response.data[:3]:
    ...     print(result.title, result.href)

    Pin a backend explicitly:

    >>> response = client.search.create(
    ...     query="python web scraping",
    ...     engine="bing",
    ...     max_results=5,
    ... )
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Type,
    Union,
    cast,
)

from .base import BaseSearchEngine

# Categories exposed by one or more engines.
_CATEGORIES: tuple[str, ...] = (
    "text",
    "images",
    "videos",
    "news",
    "suggestions",
    "answers",
    "maps",
    "weather",
    "translate",
    "books",
)

# Registry class name -> public engine id.
_ENGINE_IDS: Dict[str, str] = {
    "DuckDuckGoSearch": "duckduckgo",
    "BingSearch": "bing",
    "BraveSearch": "brave",
    "YahooSearch": "yahoo",
    "Mojeek": "mojeek",
    "Wikipedia": "wikipedia",
    "SerpBase": "serpbase",
    "Parallel": "parallel",
}

# Auto mode tries engines in this order.
_PREFERRED_ORDER: tuple[str, ...] = (
    "duckduckgo",
    "bing",
    "brave",
    "yahoo",
    "mojeek",
    "wikipedia",
    "parallel",
    "serpbase",
)

# Convenience aliases accepted by ``engine=``.
_ALIASES: Dict[str, str] = {
    "ddg": "duckduckgo",
    "duckduckgo": "duckduckgo",
    "duckduckgosearch": "duckduckgo",
    "bing": "bing",
    "bingsearch": "bing",
    "brave": "brave",
    "bravesearch": "brave",
    "yahoo": "yahoo",
    "yahoosearch": "yahoo",
    "mojeek": "mojeek",
    "wikipedia": "wikipedia",
    "wiki": "wikipedia",
    "serpbase": "serpbase",
    "serp": "serpbase",
    "parallel": "parallel",
}

# Legacy facade capabilities (the low-level engines are text-only).
_LEGACY_CAPABILITIES: Dict[str, frozenset[str]] = {
    "DuckDuckGoSearch": frozenset(
        {
            "text",
            "images",
            "videos",
            "news",
            "suggestions",
            "answers",
            "maps",
            "weather",
            "translate",
        }
    ),
    "BingSearch": frozenset({"text", "images", "news", "suggestions"}),
    "BraveSearch": frozenset({"text", "images", "videos", "news", "suggestions"}),
    "YahooSearch": frozenset(
        {
            "text",
            "images",
            "videos",
            "news",
            "suggestions",
            "answers",
            "maps",
            "weather",
            "translate",
        }
    ),
}

# Engines whose auth key is read from the environment.
_AUTH_ENV_VARS: Dict[str, str] = {"SerpBase": "SERPBASE_API_KEY"}

_REGISTRY: Optional[Dict[str, Type[Any]]] = None


def _registry() -> Dict[str, Type[Any]]:
    """Return the search-engine registry (imported lazily to avoid a cycle)."""
    global _REGISTRY
    if _REGISTRY is None:
        from . import SEARCH_PROVIDERS

        _REGISTRY = cast(Dict[str, Type[Any]], SEARCH_PROVIDERS)
    return _REGISTRY


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _supports(engine_class: Type[Any], category: str) -> bool:
    legacy = _LEGACY_CAPABILITIES.get(engine_class.__name__)
    if legacy is not None:
        return category in legacy
    return str(getattr(engine_class, "category", "text")) == category


def _serialize(item: Any) -> Any:
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if isinstance(item, dict):
        return item
    if hasattr(item, "__dict__"):
        return dict(vars(item))
    return item


@dataclass
class SearchResponse:
    """OpenAI-style search response.

    Attributes:
        query: The query that was sent.
        category: Result category (``text``, ``images``, ...).
        engine: Public engine id that served the request.
        engine_class: Registered class name (e.g. ``DuckDuckGoSearch``).
        provider: Upstream source reported by the engine.
        results: Typed result objects (or dicts for non-text categories).
        page: Page that was requested.
    """

    query: str
    category: str
    engine: str
    engine_class: str
    provider: str
    results: List[Any] = field(default_factory=list)
    page: int = 1

    @property
    def data(self) -> List[Any]:
        """Alias for :attr:`results` (OpenAI responses use ``.data``)."""
        return self.results

    def __len__(self) -> int:
        return len(self.results)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.results)

    def __getitem__(self, index: Union[int, slice]) -> Any:
        return self.results[index]

    def __repr__(self) -> str:
        return (
            f"SearchResponse(query={self.query!r}, engine={self.engine!r}, "
            f"category={self.category!r}, results={len(self.results)})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the response to a JSON-friendly dictionary."""
        return {
            "query": self.query,
            "category": self.category,
            "engine": self.engine,
            "engine_class": self.engine_class,
            "provider": self.provider,
            "page": self.page,
            "results": [_serialize(item) for item in self.results],
        }


class Search:
    """Unified search resource attached to :class:`llm4free.client.Client`."""

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: Optional[int] = None,
        verify: bool = True,
        exclude: Optional[Sequence[str]] = None,
        print_provider_info: bool = False,
    ) -> None:
        """
        Args:
            proxy: Proxy URL applied to low-level engines.
            timeout: Request timeout in seconds for low-level engines.
            verify: Whether low-level engines verify SSL certificates.
            exclude: Engine ids to skip during auto selection.
            print_provider_info: Print the selected engine before each request.
        """
        self.proxy = proxy
        self.timeout = timeout
        self.verify = verify
        self.exclude = list(exclude or [])
        self.print_provider_info = print_provider_info

    # -- discovery ---------------------------------------------------- #
    def _by_id(self) -> Dict[str, Type[Any]]:
        return {
            _ENGINE_IDS.get(name, _normalize(name)): cls
            for name, cls in _registry().items()
        }

    @staticmethod
    def _ordered_ids(by_id: Dict[str, Type[Any]]) -> List[str]:
        ordered = [engine_id for engine_id in _PREFERRED_ORDER if engine_id in by_id]
        ordered.extend(engine_id for engine_id in by_id if engine_id not in ordered)
        return ordered

    def list_engines(self, category: Optional[str] = None) -> List[str]:
        """List registered engine ids, optionally filtered by category.

        Examples:
            >>> client.search.list_engines()
            ['duckduckgo', 'bing', 'brave', 'yahoo', 'mojeek', 'wikipedia', 'parallel', 'serpbase']
            >>> client.search.list_engines(category="images")
            ['duckduckgo', 'bing', 'brave', 'yahoo']
        """
        by_id = self._by_id()
        ordered = self._ordered_ids(by_id)
        if category is None:
            return ordered
        normalized = category.lower()
        return [engine_id for engine_id in ordered if _supports(by_id[engine_id], normalized)]

    def capabilities(self) -> Dict[str, List[str]]:
        """Return a ``category -> engine ids`` matrix."""
        by_id = self._by_id()
        matrix: Dict[str, List[str]] = {}
        for category in _CATEGORIES:
            engines = [
                engine_id
                for engine_id in self._ordered_ids(by_id)
                if _supports(by_id[engine_id], category)
            ]
            if engines:
                matrix[category] = engines
        return matrix

    # -- resolution --------------------------------------------------- #
    def _canonical_id(self, name: str) -> str:
        key = _normalize(name)
        return _ALIASES.get(key, key)

    def _resolve_engine(self, engine: str) -> tuple[str, Type[Any]]:
        by_id = self._by_id()
        engine_id = _ALIASES.get(_normalize(engine))
        if engine_id is None:
            for name, cls in _registry().items():
                if _normalize(engine) in (_normalize(name), _normalize(str(cls.provider))):
                    engine_id = _ENGINE_IDS.get(name, _normalize(name))
                    break
        if engine_id is None or engine_id not in by_id:
            available = ", ".join(self._ordered_ids(by_id))
            raise ValueError(f"Unknown search engine {engine!r}. Available: {available}")
        return engine_id, by_id[engine_id]

    def _available(self, engine_class: Type[Any]) -> bool:
        if not getattr(engine_class, "required_auth", False):
            return True
        env_var = _AUTH_ENV_VARS.get(engine_class.__name__)
        return bool(env_var and os.environ.get(env_var))

    def _auto_candidates(self, category: str, exclude: Optional[Sequence[str]]) -> List[Any]:
        by_id = self._by_id()
        excluded = {self._canonical_id(name) for name in (list(self.exclude) + list(exclude or []))}
        candidates = []
        for engine_id in self._ordered_ids(by_id):
            engine_class = by_id[engine_id]
            if engine_id in excluded:
                continue
            if not _supports(engine_class, category):
                continue
            if not self._available(engine_class):
                continue
            candidates.append((engine_id, engine_class))
        return candidates

    # -- execution ---------------------------------------------------- #
    @staticmethod
    def _call_legacy(
        engine_class: Type[Any],
        method_name: str,
        query: str,
        region: Optional[str],
        safesearch: Optional[str],
        timelimit: Optional[str],
        max_results: Optional[int],
        extra: Dict[str, Any],
    ) -> Any:
        instance = engine_class()
        method = getattr(instance, method_name, None)
        if method is None:
            raise NotImplementedError(f"{engine_class.__name__} has no {method_name}()")

        accepted = set(inspect.signature(method).parameters)
        values: Dict[str, Any] = {
            "keywords": query,
            "query": query,
            "region": region,
            "safesearch": safesearch,
            "timelimit": timelimit,
            "max_results": max_results,
            **extra,
        }
        payload = {key: value for key, value in values.items() if key in accepted and value is not None}
        if "keywords" in payload and "query" in payload:
            payload.pop("query")
        return method(**payload)

    def _dispatch(
        self,
        engine_class: Type[Any],
        query: str,
        category: str,
        region: Optional[str],
        safesearch: Optional[str],
        timelimit: Optional[str],
        page: int,
        max_results: Optional[int],
        extra: Dict[str, Any],
    ) -> Any:
        if issubclass(engine_class, BaseSearchEngine):
            instance = engine_class(
                proxy=self.proxy,
                timeout=self.timeout,
                verify=self.verify,
            )
            params: Dict[str, Any] = {
                "region": region or "us-en",
                "safesearch": safesearch or "moderate",
                "timelimit": timelimit,
                "page": page,
                **extra,
            }
            if max_results is not None:
                params["max_results"] = max_results
            return instance.search(query, **params)

        return self._call_legacy(
            engine_class,
            category,
            query,
            region,
            safesearch,
            timelimit,
            max_results,
            extra,
        )

    # -- public API --------------------------------------------------- #
    def create(
        self,
        query: str,
        *,
        engine: Optional[str] = "auto",
        category: str = "text",
        max_results: Optional[int] = 10,
        region: Optional[str] = None,
        safesearch: Optional[str] = None,
        timelimit: Optional[str] = None,
        page: int = 1,
        exclude: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ) -> SearchResponse:
        """Run a search and return an OpenAI-style :class:`SearchResponse`.

        Args:
            query: Search query.
            engine: Engine id or alias, or ``"auto"`` to fail over. ``model``
                is accepted as an alias for OpenAI-style calls.
            category: ``text``, ``images``, ``videos``, ``news``, ``suggestions``,
                ``answers``, ``maps``, ``weather``, ``translate`` or ``books``.
            max_results: Maximum number of results (default 10). ``None`` keeps
                the engine default.
            region: Engine region code, e.g. ``"us-en"``.
            safesearch: ``"on"``, ``"moderate"`` or ``"off"``.
            timelimit: Recency filter understood by the engine (``"d"``, ``"w"``, ...).
            page: Page number for engines that paginate.
            exclude: Engine ids to skip during auto selection.
            **kwargs: Engine-specific options (``objective`` for Parallel,
                ``size``/``color`` for DuckDuckGo images, ...).

        Raises:
            ValueError: Unknown engine, unsupported category, or no candidate.
            RuntimeError: Auto mode exhausted every engine without success.
        """
        model = kwargs.pop("model", None)
        if model is not None:
            if engine not in (None, "", "auto"):
                raise TypeError("Pass either `engine=` or `model=`, not both")
            engine = str(model)

        if not query or not query.strip():
            raise ValueError("`query` must be a non-empty string")

        normalized_category = category.lower()
        if normalized_category not in _CATEGORIES:
            raise ValueError(
                f"Unknown search category {category!r}. "
                f"Choose from: {', '.join(_CATEGORIES)}"
            )

        explicit = engine is not None and _normalize(str(engine)) not in ("", "auto")
        if explicit:
            engine_id, engine_class = self._resolve_engine(str(engine))
            if not _supports(engine_class, normalized_category):
                raise ValueError(
                    f"Search engine {engine_id!r} does not support {normalized_category!r}. "
                    f"Available: {', '.join(self.list_engines(normalized_category))}"
                )
            candidates = [(engine_id, engine_class)]
        else:
            candidates = self._auto_candidates(normalized_category, exclude)
            if not candidates:
                raise ValueError(
                    f"No search engine supports {normalized_category!r}. "
                    f"Available: {', '.join(self.list_engines())}"
                )

        errors: List[str] = []
        for engine_id, engine_class in candidates:
            try:
                raw = self._dispatch(
                    engine_class,
                    query,
                    normalized_category,
                    region,
                    safesearch,
                    timelimit,
                    page,
                    max_results,
                    dict(kwargs),
                )
            except NotImplementedError as exc:
                if explicit:
                    raise ValueError(f"{engine_id} does not implement {normalized_category}") from exc
                errors.append(f"{engine_id}: unsupported")
                continue
            except Exception as exc:
                if explicit:
                    raise
                errors.append(f"{engine_id}: {type(exc).__name__}: {exc}")
                continue

            if raw is None:
                results: List[Any] = []
            elif isinstance(raw, list):
                results = raw
            else:
                results = [raw]
            if max_results is not None:
                results = results[:max_results]

            if self.print_provider_info:
                print(f"Search engine: {engine_id} ({engine_class.__name__})")

            return SearchResponse(
                query=query,
                category=normalized_category,
                engine=engine_id,
                engine_class=engine_class.__name__,
                provider=str(getattr(engine_class, "provider", engine_id)),
                results=results,
                page=page,
            )

        raise RuntimeError("All search engines failed: " + " | ".join(errors))

    # -- category helpers --------------------------------------------- #
    def text(self, query: str, **kwargs: Any) -> SearchResponse:
        """Text/web search. Shortcut for ``create(query, category="text")``."""
        return self.create(query, category="text", **kwargs)

    def images(self, query: str, **kwargs: Any) -> SearchResponse:
        """Image search. Shortcut for ``create(query, category="images")``."""
        return self.create(query, category="images", **kwargs)

    def videos(self, query: str, **kwargs: Any) -> SearchResponse:
        """Video search. Shortcut for ``create(query, category="videos")``."""
        return self.create(query, category="videos", **kwargs)

    def news(self, query: str, **kwargs: Any) -> SearchResponse:
        """News search. Shortcut for ``create(query, category="news")``."""
        return self.create(query, category="news", **kwargs)

    def suggestions(self, query: str, **kwargs: Any) -> SearchResponse:
        """Autocomplete search. Shortcut for ``create(query, category="suggestions")``."""
        return self.create(query, category="suggestions", **kwargs)

    def answers(self, query: str, **kwargs: Any) -> SearchResponse:
        """Instant answers. Shortcut for ``create(query, category="answers")``."""
        return self.create(query, category="answers", **kwargs)

    def maps(self, query: str, **kwargs: Any) -> SearchResponse:
        """Map search. Shortcut for ``create(query, category="maps")``."""
        return self.create(query, category="maps", **kwargs)

    def weather(self, query: str, **kwargs: Any) -> SearchResponse:
        """Weather lookup. Shortcut for ``create(query, category="weather")``."""
        return self.create(query, category="weather", **kwargs)

    def translate(self, query: str, **kwargs: Any) -> SearchResponse:
        """Translate text. Shortcut for ``create(query, category="translate")``."""
        return self.create(query, category="translate", **kwargs)

    def books(self, query: str, **kwargs: Any) -> SearchResponse:
        """Book search. Shortcut for ``create(query, category="books")``."""
        return self.create(query, category="books", **kwargs)
