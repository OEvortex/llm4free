from litprinter import ic
"""
LLM4Free Unified Client Interface

A unified client for llm4free that provides a simple interface
to interact with multiple AI providers for chat completions, image generation,
and TTS-based audio generation.
"""

import difflib
import functools
import importlib
import inspect
import pkgutil
import random
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    Type,
    TypeGuard,
    TypeVar,
    Union,
    cast,
    overload,
)

from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    Tool,
    ToolList,
)
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
)
from llm4free.search.client import Search
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.utils import ImageResponse
from llm4free.TTS.base import BaseTTSProvider



def load_openai_providers() -> Tuple[Dict[str, Type[OpenAICompatibleProvider]], Set[str]]:
    """
    Dynamically loads all OpenAI-compatible provider classes from the llm module.

    Scans the llm4free.llm package and imports all subclasses of
    OpenAICompatibleProvider. Excludes base classes, utility modules, and private classes.

    Returns:
        A tuple containing:
        - A dictionary mapping provider class names to their class objects.
        - A set of provider names that require API authentication.

    Raises:
        No exceptions are raised; failures are silently handled to ensure robust loading.

    Examples:
        >>> providers, auth_required = load_openai_providers()
        >>> print(list(providers.keys())[:3])
        ['Claude', 'GPT4Free', 'OpenRouter']
        >>> print('Claude' in auth_required)
        True
    """
    return _load_providers_cached(
        "llm4free.llm",
        OpenAICompatibleProvider,
        ("base", "utils", "pydantic", "__"),
    )


def load_tti_providers() -> Tuple[Dict[str, Type[TTICompatibleProvider]], Set[str]]:
    """
    Dynamically loads all TTI (Text-to-Image) provider classes from the TTI module.

    Scans the llm4free.TTI package and imports all subclasses of
    TTICompatibleProvider. Excludes base classes, utility modules, and private classes.

    Returns:
        A tuple containing:
        - A dictionary mapping TTI provider class names to their class objects.
        - A set of TTI provider names that require API authentication.

    Raises:
        No exceptions are raised; failures are silently handled to ensure robust loading.

    Examples:
        >>> providers, auth_required = load_tti_providers()
        >>> print('DALL-E' in providers)
        True
        >>> print('Stable Diffusion' in auth_required)
        False
    """
    return _load_providers_cached("llm4free.TTI", TTICompatibleProvider, ("base", "utils", "__"))


def load_tts_providers() -> Tuple[Dict[str, Type[BaseTTSProvider]], Set[str]]:
    """
    Dynamically loads all TTS provider classes from the TTS module.

    Scans the llm4free.TTS package and imports all subclasses of
    BaseTTSProvider. Excludes base classes, utility modules, and private classes.

    Returns:
        A tuple containing:
        - A dictionary mapping TTS provider class names to their class objects.
        - A set of TTS provider names that require API authentication.
    """
    return _load_providers_cached("llm4free.TTS", BaseTTSProvider, ("base", "utils", "__"))


def _get_models_safely(provider_cls: type, client: Optional["Client"] = None) -> List[str]:
    """
    Safely retrieves the list of available models from a provider.

    Attempts to instantiate the provider class and call its models.list() method.
    If a Client instance is provided, uses the client's provider cache to avoid
    redundant instantiations. Handles all exceptions gracefully and returns an
    empty list if model retrieval fails.

    Args:
        provider_cls: The provider class to retrieve models from.
        client: Optional Client instance to use for caching and configuration.
                If provided, uses client's proxies and api_key for initialization.

    Returns:
        A list of available model identifiers (strings). Returns an empty list
        if the provider has no models or if instantiation fails.

    Note:
        This function silently handles all exceptions and will not raise errors.
        Model names are extracted from both string lists and dicts with 'id' keys.

    Examples:
        >>> from llm4free.client import _get_models_safely, Client
        >>> client = Client()
        >>> from llm4free.llm.some_provider import SomeProvider
        >>> models = _get_models_safely(SomeProvider, client)
        >>> print(models)
        ['gpt-4', 'gpt-3.5-turbo']
    """
    models = []

    try:
        instance = None
        if client:
            p_name = provider_cls.__name__
            if p_name in client._provider_cache:
                instance = client._provider_cache[p_name]
            else:
                try:
                    init_kwargs = {}
                    if client.proxies:
                        init_kwargs["proxies"] = client.proxies
                    if client.api_key:
                        init_kwargs["api_key"] = client.api_key
                    instance = provider_cls(**init_kwargs)
                except (TypeError, RuntimeError):
                    try:
                        instance = provider_cls()
                    except (TypeError, RuntimeError):
                        pass

                if instance:
                    client._provider_cache[p_name] = instance
        else:
            try:
                instance = provider_cls()
            except (TypeError, RuntimeError):
                pass

        if instance and hasattr(instance, "models") and hasattr(instance.models, "list"):
            res = instance.models.list()
            if isinstance(res, list):
                for m in res:
                    if isinstance(m, str):
                        models.append(m)
                    elif isinstance(m, dict) and "id" in m:
                        models.append(m["id"])
    except (AttributeError, TypeError):
        pass

    return models


def _get_tts_models_safely(provider_cls: type) -> List[str]:
    """
    Returns the TTS models exposed by a provider class.

    TTS providers advertise models through class attributes rather than a
    nested models.list() interface, so we inspect the class directly.
    """
    models = getattr(provider_cls, "SUPPORTED_MODELS", None)
    if isinstance(models, list):
        return [model for model in models if isinstance(model, str)]

    models = getattr(provider_cls, "AVAILABLE_MODELS", None)
    if isinstance(models, list):
        return [model for model in models if isinstance(model, str)]

    return ["gpt-4o-mini-tts"]


def _normalized_name_set(values: Optional[List[str]]) -> Set[str]:
    return {value.casefold() for value in (values or []) if value}


ProviderT = TypeVar("ProviderT")


@functools.lru_cache(maxsize=None)
def _load_providers_cached(
    module_path: str,
    base_class: type,
    exclude_prefixes: Tuple[str, ...],
) -> Tuple[Dict[str, Any], Set[str]]:
    """Cached wrapper around _load_providers to avoid redundant scans."""
    return _load_providers(module_path, base_class, exclude_prefixes)


def _load_providers(
    module_path: str,
    base_class: Type[ProviderT],
    exclude_prefixes: Tuple[str, ...],
) -> Tuple[Dict[str, Type[ProviderT]], Set[str]]:
    provider_map: Dict[str, Type[ProviderT]] = {}
    auth_required_providers: Set[str] = set()

    try:
        provider_package = importlib.import_module(module_path)
        for _, module_name, _ in pkgutil.iter_modules(provider_package.__path__):
            if module_name.startswith(exclude_prefixes):
                continue
            try:
                module = importlib.import_module(f"{module_path}.{module_name}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, base_class)
                        and attr != base_class
                        and not attr_name.startswith(("Base", "_"))
                    ):
                        provider_map[attr_name] = attr
                        if getattr(attr, "required_auth", False):
                            auth_required_providers.add(attr_name)
            except (ImportError, AttributeError):
                pass
    except (ImportError, ValueError):
        pass

    return provider_map, auth_required_providers


def _print_provider_selection(
    provider_name: str, model_name: str, *, fallback: bool = False
) -> None:
    suffix = " (Fallback)" if fallback else ""
    print(f"\033[1;34m{provider_name}:{model_name}{suffix}\033[0m\n")


def _print_model_match(match_type: str, model: str, matched_model: str) -> None:
    print(f"\033[1;33m{match_type}: '{model}' -> '{matched_model}'\033[0m")


def _get_available_provider_items(
    provider_registry: Dict[str, Type[ProviderT]],
    auth_required_providers: Set[str],
    excluded: Optional[List[str]],
    api_key: Optional[str],
    *,
    drop_auth: bool = True,
) -> List[Tuple[str, Type[ProviderT]]]:
    exclude = _normalized_name_set(excluded)
    if api_key and not drop_auth:
        return [
            (name, cls) for name, cls in provider_registry.items() if name.casefold() not in exclude
        ]
    return [
        (name, cls)
        for name, cls in provider_registry.items()
        if name not in auth_required_providers and name.casefold() not in exclude
    ]


def _get_provider_instance_cached(
    cache: Dict[str, Any],
    provider_class: Type[ProviderT],
    init_kwargs_candidates: List[Dict[str, Any]],
    *,
    provider_kind: Optional[str] = None,
) -> ProviderT:
    provider_name = provider_class.__name__
    if provider_name in cache:
        return cache[provider_name]

    for init_kwargs in init_kwargs_candidates:
        try:
            instance = provider_class(**init_kwargs)
            cache[provider_name] = instance
            return instance
        except (TypeError, RuntimeError):
            continue

    try:
        instance = provider_class()
        cache[provider_name] = instance
        return instance
    except (TypeError, RuntimeError) as exc:
        label = f"{provider_kind} " if provider_kind else ""
        raise RuntimeError(f"Failed to initialize {label}provider {provider_class.__name__}: {exc}")


def _build_search_models(model: str, resolved_model: Optional[str]) -> Tuple[str, Set[str]]:
    base_model = model.split("/")[-1] if "/" in model else model
    search_models = {base_model, resolved_model} if resolved_model else {base_model}
    return base_model, search_models


def _fuzzy_resolve_provider_and_model(
    model: str,
    available: List[Tuple[str, Type[ProviderT]]],
    get_models_fn: Callable[[Type[ProviderT]], List[str]],
    *,
    print_provider_info: bool = False,
    match_suffix: str = "",
) -> Optional[Tuple[Type[ProviderT], str]]:
    model_to_provider: Dict[str, Type[ProviderT]] = {}

    for _, provider_class in available:
        for provider_model in get_models_fn(provider_class):
            if provider_model not in model_to_provider:
                model_to_provider[provider_model] = provider_class

    if not model_to_provider:
        return None

    model_lower = model.lower()

    for model_name in model_to_provider:
        if model_name.lower() == model_lower:
            return model_to_provider[model_name], model_name

    for model_name in model_to_provider:
        candidate = model_name.lower()
        if model_lower in candidate or candidate in model_lower:
            if print_provider_info:
                _print_model_match(f"Substring match{match_suffix}", model, model_name)
            return model_to_provider[model_name], model_name

    matches = difflib.get_close_matches(model, model_to_provider.keys(), n=1, cutoff=0.5)
    if matches:
        matched_model = matches[0]
        if print_provider_info:
            _print_model_match(f"Fuzzy match{match_suffix}", model, matched_model)
        return model_to_provider[matched_model], matched_model

    return None


def _resolve_provider_and_model(
    model: str,
    provider: Optional[Type[ProviderT]],
    provider_registry: Dict[str, Type[ProviderT]],
    available_provider_fn: Callable[[], List[Tuple[str, Type[ProviderT]]]],
    get_models_fn: Callable[[Type[ProviderT]], List[str]],
    *,
    print_provider_info: bool = False,
    no_available_message: str,
    no_available_with_models_message: str,
    provider_no_models_message: str,
    no_providers_for_model_message: str,
    provider_empty_model_fallback: Optional[str] = None,
    match_suffix: str = "",
) -> Tuple[Type[ProviderT], str]:
    if "/" in model:
        provider_name, model_name = model.split("/", 1)
        found_provider = next(
            (
                cls
                for name, cls in provider_registry.items()
                if name.lower() == provider_name.lower()
            ),
            None,
        )
        if found_provider:
            return found_provider, model_name

    if provider:
        resolved_model = model
        if model == "auto":
            provider_models = get_models_fn(provider)
            if provider_models:
                resolved_model = random.choice(provider_models)
            elif provider_empty_model_fallback is not None:
                resolved_model = provider_empty_model_fallback
            else:
                raise RuntimeError(provider_no_models_message.format(provider=provider.__name__))
        return provider, resolved_model

    if model == "auto":
        available = available_provider_fn()
        if not available:
            raise RuntimeError(no_available_message)

        providers_with_models = []
        for _, provider_class in available:
            provider_models = get_models_fn(provider_class)
            if provider_models:
                providers_with_models.append((provider_class, provider_models))

        if providers_with_models:
            provider_class, provider_models = random.choice(providers_with_models)
            return provider_class, random.choice(provider_models)

        raise RuntimeError(no_available_with_models_message)

    available = available_provider_fn()
    for _, provider_class in available:
        provider_models = get_models_fn(provider_class)
        if provider_models and model in provider_models:
            return provider_class, model

    fuzzy_result = _fuzzy_resolve_provider_and_model(
        model,
        available,
        get_models_fn,
        print_provider_info=print_provider_info,
        match_suffix=match_suffix,
    )
    if fuzzy_result:
        return fuzzy_result

    if available:
        random.shuffle(available)
        return available[0][1], model

    raise RuntimeError(no_providers_for_model_message.format(model=model))


def _build_fallback_queue(
    available: List[Tuple[str, Type[ProviderT]]],
    resolved_provider: Optional[Type[ProviderT]],
    model: str,
    resolved_model: Optional[str],
    get_models_fn: Callable[[Type[ProviderT]], List[str]],
    *,
    empty_model_fallback: str,
) -> List[Tuple[str, Type[ProviderT], str]]:
    tier1: List[Tuple[str, Type[ProviderT], str]] = []
    tier2: List[Tuple[str, Type[ProviderT], str]] = []
    tier3: List[Tuple[str, Type[ProviderT], str]] = []
    base_model, search_models = _build_search_models(model, resolved_model)

    for provider_name, provider_class in available:
        if provider_class == resolved_provider:
            continue

        provider_models = get_models_fn(provider_class)
        if not provider_models:
            fallback_model = base_model if base_model != "auto" else empty_model_fallback
            tier3.append((provider_name, provider_class, fallback_model))
            continue

        found_exact = False
        for search_model in search_models:
            if search_model != "auto" and search_model in provider_models:
                tier1.append((provider_name, provider_class, search_model))
                found_exact = True
                break
        if found_exact:
            continue

        if base_model != "auto":
            matches = difflib.get_close_matches(base_model, provider_models, n=1, cutoff=0.5)
            if matches:
                tier2.append((provider_name, provider_class, matches[0]))
                continue

        tier3.append((provider_name, provider_class, random.choice(provider_models)))

    random.shuffle(tier1)
    random.shuffle(tier2)
    random.shuffle(tier3)
    return tier1 + tier2 + tier3


def _is_valid_chat_completion(response: Any) -> TypeGuard[ChatCompletion]:
    """Type guard that validates a ChatCompletion has usable output.

    A response is valid when it contains either non-empty text content or
    at least one tool call. Tool-call responses legitimately have
    ``content=None``, so they must not be treated as empty completions.
    """
    if not (response and hasattr(response, "choices") and response.choices):
        return False

    message = response.choices[0].message
    if message is None:
        return False

    if message.tool_calls:
        return True

    return bool(message.content and message.content.strip())


def _chain_stream_response(
    first_chunk: ChatCompletionChunk,
    response: Generator[ChatCompletionChunk, None, None],
    *,
    provider_name: str,
    model_name: str,
    print_provider_info: bool,
    fallback: bool = False,
) -> Generator[ChatCompletionChunk, None, None]:
    if print_provider_info:
        _print_provider_selection(provider_name, model_name, fallback=fallback)

    yield first_chunk
    yield from response


OPENAI_PROVIDERS, OPENAI_AUTH_REQUIRED = load_openai_providers()
TTI_PROVIDERS, TTI_AUTH_REQUIRED = load_tti_providers()
TTS_PROVIDERS, TTS_AUTH_REQUIRED = load_tts_providers()


class ClientCompletions(BaseCompletions):
    """
    Unified completions interface with intelligent provider and model resolution.

    This class manages chat completions by automatically selecting appropriate
    providers and models based on user input. It supports:
    - Automatic model discovery and fuzzy matching
    - Provider failover for reliability
    - Provider and model caching for performance
    - Streaming and non-streaming responses
    - Tools and function calling support

    Attributes:
        _client: Reference to the parent Client instance.
        _last_provider: Name of the last successfully used provider.

    Examples:
        >>> from llm4free.client import Client
        >>> client = Client(print_provider_info=True)
        >>> response = client.chat.completions.create(
        ...     model="auto",
        ...     messages=[{"role": "user", "content": "Hello!"}]
        ... )
    """

    def __init__(self, client: "Client"):
        self._client = client
        self._last_provider: Optional[str] = None

    @property
    def last_provider(self) -> Optional[str]:
        """
        Returns the name of the last successfully used provider.

        This property tracks which provider was most recently used to generate
        a completion. Useful for debugging and understanding which fallback
        providers are being utilized.

        Returns:
            The name of the last provider as a string, or None if no provider
            has been successfully used yet.

        Examples:
            >>> completions = client.chat.completions
            >>> response = completions.create(model="auto", messages=[...])
            >>> print(completions.last_provider)
            'GPT4Free'
        """
        return self._last_provider

    def _get_provider_instance(
        self, provider_class: Type[OpenAICompatibleProvider], **kwargs
    ) -> OpenAICompatibleProvider:
        init_kwargs = {}
        if self._client.proxies:
            init_kwargs["proxies"] = self._client.proxies
        if self._client.api_key:
            init_kwargs["api_key"] = self._client.api_key
        init_kwargs.update(kwargs)

        return _get_provider_instance_cached(
            self._client._provider_cache,
            provider_class,
            [init_kwargs],
        )

    def _fuzzy_resolve_provider_and_model(
        self, model: str
    ) -> Optional[Tuple[Type[OpenAICompatibleProvider], str]]:
        return _fuzzy_resolve_provider_and_model(
            model,
            self._get_available_providers(),
            lambda provider_cls: _get_models_safely(provider_cls, self._client),
            print_provider_info=self._client.print_provider_info,
        )

    def _resolve_provider_and_model(
        self, model: str, provider: Optional[Type[OpenAICompatibleProvider]]
    ) -> Tuple[Type[OpenAICompatibleProvider], str]:
        return _resolve_provider_and_model(
            model,
            provider,
            OPENAI_PROVIDERS,
            self._get_available_providers,
            lambda provider_cls: _get_models_safely(provider_cls, self._client),
            print_provider_info=self._client.print_provider_info,
            no_available_message="No available chat providers found.",
            no_available_with_models_message="No available chat providers with models found.",
            provider_no_models_message="Provider {provider} has no available models.",
            no_providers_for_model_message="No providers found for model '{model}'",
        )

    def _get_available_providers(self) -> List[Tuple[str, Type[OpenAICompatibleProvider]]]:
        return _get_available_provider_items(
            OPENAI_PROVIDERS,
            OPENAI_AUTH_REQUIRED,
            self._client.exclude,
            self._client.api_key,
            drop_auth=self._client.drop_auth_providers,
        )

    @overload
    def create(
        self,
        *,
        model: str = "auto",
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: Literal[True],
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: ToolList = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        provider: Optional[Type[OpenAICompatibleProvider]] = None,
        **kwargs: Any,
    ) -> Generator[ChatCompletionChunk, None, None]: ...

    @overload
    def create(
        self,
        *,
        model: str = "auto",
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: Literal[False] = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: ToolList = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        provider: Optional[Type[OpenAICompatibleProvider]] = None,
        **kwargs: Any,
    ) -> ChatCompletion: ...

    @overload
    def create(
        self,
        *,
        model: str = "auto",
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: ToolList = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        provider: Optional[Type[OpenAICompatibleProvider]] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]: ...

    def create(
        self,
        *,
        model: str = "auto",
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: ToolList = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        provider: Optional[Type[OpenAICompatibleProvider]] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """
        Creates a chat completion with automatic provider selection and failover.

        Attempts to resolve the specified model to a provider and model name,
        then creates a completion. If the initial attempt fails, automatically
        falls back to other available providers, prioritizing:
        1. Providers with exact model matches
        2. Providers with fuzzy model matches
        3. Providers with any available model

        Args:
            model: Model identifier. Default "auto" randomly selects available models.
                   Can be "provider/model" format or model name. Required.
            messages: List of message dicts with 'role' and 'content' keys. Required.
            max_tokens: Maximum tokens in the response. Optional.
            stream: Whether to stream the response. Default is False.
            temperature: Sampling temperature (0-2). Controls response randomness. Optional.
            top_p: Nucleus sampling parameter (0-1). Optional.
            tools: List of tools or tool definitions for function calling. Optional.
            tool_choice: Which tool to use or how to select tools. Optional.
            timeout: Request timeout in seconds. Optional.
            proxies: HTTP proxy configuration dict. Optional.
            provider: Specific provider class to use. Optional.
            **kwargs: Additional arguments passed to the provider.

        Returns:
            ChatCompletion object for non-streaming requests.
            Generator[ChatCompletionChunk, None, None] for streaming requests.

        Raises:
            RuntimeError: If all chat providers fail or no providers are available.

        Note:
            If print_provider_info is True, provider name and model are printed
            to stdout in color-formatted text. Streaming responses print on first chunk.

        Examples:
            >>> client = Client(print_provider_info=True)
            >>> response = client.chat.completions.create(
            ...     model="gpt-4",
            ...     messages=[{"role": "user", "content": "Hello!"}]
            ... )
            >>> print(response.choices[0].message.content)

            >>> # Streaming example
            >>> for chunk in client.chat.completions.create(
            ...     model="auto",
            ...     messages=[{"role": "user", "content": "Hello!"}],
            ...     stream=True
            ... ):
            ...     print(chunk.choices[0].delta.content, end="")
        """
        try:
            resolved_provider, resolved_model = self._resolve_provider_and_model(model, provider)
        except (RuntimeError, ValueError):
            resolved_provider, resolved_model = None, model

        call_kwargs: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": stream,
        }
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if top_p is not None:
            call_kwargs["top_p"] = top_p
        if tools is not None:
            call_kwargs["tools"] = tools
        if tool_choice is not None:
            call_kwargs["tool_choice"] = tool_choice
        if timeout is not None:
            call_kwargs["timeout"] = timeout
        if proxies is not None:
            call_kwargs["proxies"] = proxies
        call_kwargs.update(kwargs)

        if resolved_provider:
            try:
                provider_instance = self._get_provider_instance(resolved_provider)
                response = provider_instance.chat.completions.create(**call_kwargs)

                if stream and inspect.isgenerator(response):
                    try:
                        first_chunk = cast(ChatCompletionChunk, next(response))
                        self._last_provider = resolved_provider.__name__
                        return _chain_stream_response(
                            first_chunk,
                            response,
                            provider_name=resolved_provider.__name__,
                            model_name=resolved_model,
                            print_provider_info=self._client.print_provider_info,
                        )
                    except StopIteration:
                        pass
                    except Exception as exc:
                        ic("Stream error from %s: %s", resolved_provider.__name__, exc)
                else:
                    if not inspect.isgenerator(response):
                        completion_response = cast(ChatCompletion, response)
                        if _is_valid_chat_completion(completion_response):
                            self._last_provider = resolved_provider.__name__
                            if self._client.print_provider_info:
                                _print_provider_selection(
                                    resolved_provider.__name__, resolved_model
                                )
                            return completion_response
                        raise ValueError(
                            f"Provider {resolved_provider.__name__} returned empty "
                            "content and no tool calls"
                        )
            except Exception as exc:
                ic("Provider %s failed: %s", resolved_provider.__name__, exc)

        all_available = self._get_available_providers()
        fallback_queue = _build_fallback_queue(
            all_available,
            resolved_provider,
            model,
            resolved_model,
            lambda provider_cls: _get_models_safely(provider_cls, self._client),
            empty_model_fallback="auto",
        )

        errors = []
        for p_name, p_cls, p_model in fallback_queue:
            try:
                provider_instance = self._get_provider_instance(p_cls)
                fallback_kwargs: Dict[str, Any] = dict(call_kwargs)
                fallback_kwargs["model"] = p_model
                response = provider_instance.chat.completions.create(**fallback_kwargs)

                if stream and inspect.isgenerator(response):
                    try:
                        first_chunk = cast(ChatCompletionChunk, next(response))
                        self._last_provider = p_name
                        return _chain_stream_response(
                            first_chunk,
                            response,
                            provider_name=p_name,
                            model_name=p_model,
                            print_provider_info=self._client.print_provider_info,
                            fallback=True,
                        )
                    except (StopIteration, RuntimeError, ValueError):
                        continue

                if not inspect.isgenerator(response):
                    completion_response = cast(ChatCompletion, response)
                    if _is_valid_chat_completion(completion_response):
                        self._last_provider = p_name
                        if self._client.print_provider_info:
                            _print_provider_selection(p_name, p_model, fallback=True)
                        return completion_response
                    errors.append(f"{p_name}: Returned empty response with no tool calls.")
                    continue
            except Exception as e:
                errors.append(f"{p_name}: {str(e)}")
                continue

        raise RuntimeError(f"All chat providers failed. Errors: {'; '.join(errors[:3])}")


class ClientChat(BaseChat):
    """
    Standard chat interface wrapper for the Client.

    Provides access to chat completions through a completions property that
    implements the BaseChat interface. Acts as an adapter between the Client
    and the underlying OpenAI-compatible completion system.

    Attributes:
        completions: ClientCompletions instance for creating chat completions.

    Examples:
        >>> chat = client.chat
        >>> response = chat.completions.create(
        ...     model="auto",
        ...     messages=[{"role": "user", "content": "Hi"}]
        ... )
    """

    def __init__(self, client: "Client"):
        self.completions = ClientCompletions(client)


class ClientImages(BaseImages):
    """
    Unified image generation interface with automatic provider selection and failover.

    Manages text-to-image (TTI) generation by automatically selecting appropriate
    providers and models based on user input. Implements similar resolution and
    failover logic as ClientCompletions but for image generation.

    Features:
    - Automatic model discovery and fuzzy matching
    - Provider failover for reliability
    - Provider and model caching for performance
    - Structured parameter validation
    - Support for multiple image output formats

    Attributes:
        _client: Reference to the parent Client instance.
        _last_provider: Name of the last successfully used image provider.

    Examples:
        >>> client = Client(print_provider_info=True)
        >>> response = client.images.generate(
        ...     prompt="A beautiful sunset",
        ...     model="auto",
        ...     n=1,
        ...     size="1024x1024"
        ... )
        >>> print(response.data[0].url)
    """

    def __init__(self, client: "Client"):
        self._client = client
        self._last_provider: Optional[str] = None

    @property
    def last_provider(self) -> Optional[str]:
        """
        Returns the name of the last successfully used image provider.

        Tracks which TTI provider was most recently used to generate images.
        Useful for debugging and understanding which fallback providers are
        being utilized.

        Returns:
            The name of the last provider as a string, or None if no provider
            has been successfully used yet.

        Examples:
            >>> images = client.images
            >>> response = images.generate(prompt="...", model="auto")
            >>> print(images.last_provider)
            'StableDiffusion'
        """
        return self._last_provider

    def _get_provider_instance(
        self, provider_class: Type[TTICompatibleProvider], **kwargs
    ) -> TTICompatibleProvider:
        init_kwargs = {}
        if self._client.proxies:
            init_kwargs["proxies"] = self._client.proxies
        init_kwargs.update(kwargs)

        return _get_provider_instance_cached(
            self._client._provider_cache,
            provider_class,
            [init_kwargs],
            provider_kind="TTI",
        )

    def _fuzzy_resolve_provider_and_model(
        self, model: str
    ) -> Optional[Tuple[Type[TTICompatibleProvider], str]]:
        return _fuzzy_resolve_provider_and_model(
            model,
            self._get_available_providers(),
            lambda provider_cls: _get_models_safely(provider_cls, self._client),
            print_provider_info=self._client.print_provider_info,
            match_suffix=" (TTI)",
        )

    def _resolve_provider_and_model(
        self, model: str, provider: Optional[Type[TTICompatibleProvider]]
    ) -> Tuple[Type[TTICompatibleProvider], str]:
        return _resolve_provider_and_model(
            model,
            provider,
            TTI_PROVIDERS,
            self._get_available_providers,
            lambda provider_cls: _get_models_safely(provider_cls, self._client),
            print_provider_info=self._client.print_provider_info,
            no_available_message="No available image providers found.",
            no_available_with_models_message="No available image providers with models found.",
            provider_no_models_message="TTI Provider {provider} has no available models.",
            no_providers_for_model_message="No image providers found for model '{model}'",
        )

    def _get_available_providers(self) -> List[Tuple[str, Type[TTICompatibleProvider]]]:
        return _get_available_provider_items(
            TTI_PROVIDERS,
            TTI_AUTH_REQUIRED,
            self._client.exclude_images,
            self._client.api_key,
            drop_auth=self._client.drop_auth_providers,
        )

    def generate(
        self,
        *,
        prompt: str,
        model: str = "auto",
        n: int = 1,
        size: str = "1024x1024",
        response_format: str = "url",
        provider: Optional[Type[TTICompatibleProvider]] = None,
        **kwargs: Any,
    ) -> ImageResponse:
        """
        Generates images with automatic provider selection and failover.

        Attempts to resolve the specified model to a provider and model name,
        then creates images. If the initial attempt fails, automatically falls
        back to other available providers, prioritizing:
        1. Providers with exact model matches
        2. Providers with fuzzy model matches
        3. Providers with any available model

        Args:
            prompt: Text description of the image(s) to generate. Required.
            model: Model identifier. Default "auto" randomly selects available models.
                   Can be "provider/model" format or model name.
            n: Number of images to generate. Default is 1.
            size: Image size specification (e.g., "1024x1024", "512x512"). Default is "1024x1024".
            response_format: Format for image response ("url" or "b64_json"). Default is "url".
            provider: Specific TTI provider class to use. Optional.
            **kwargs: Additional arguments passed to the provider.

        Returns:
            ImageResponse object containing generated images with URLs or base64 data.

        Raises:
            RuntimeError: If all image providers fail or no providers are available.

        Note:
            If print_provider_info is True, provider name and model are printed
            to stdout in color-formatted text.

        Examples:
            >>> client = Client(print_provider_info=True)
            >>> response = client.images.generate(
            ...     prompt="A beautiful sunset over mountains",
            ...     model="auto",
            ...     n=1,
            ...     size="1024x1024"
            ... )
            >>> print(response.data[0].url)

            >>> # Using specific provider
            >>> from llm4free.TTI.stable import StableDiffusion
            >>> response = client.images.generate(
            ...     prompt="A cat wearing sunglasses",
            ...     provider=StableDiffusion
            ... )
        """
        try:
            resolved_provider, resolved_model = self._resolve_provider_and_model(model, provider)
        except (RuntimeError, ValueError):
            resolved_provider, resolved_model = None, model

        call_kwargs: Dict[str, Any] = {
            "prompt": prompt,
            "model": resolved_model,
            "n": n,
            "size": size,
            "response_format": response_format,
        }
        call_kwargs.update(kwargs)

        errors: List[str] = []
        if resolved_provider:
            try:
                provider_instance = self._get_provider_instance(resolved_provider)
                response = provider_instance.images.create(**call_kwargs)
                self._last_provider = resolved_provider.__name__
                if self._client.print_provider_info:
                    _print_provider_selection(resolved_provider.__name__, resolved_model)
                return response
            except (RuntimeError, ValueError, TypeError) as exc:
                ic("TTI provider %s failed: %s", resolved_provider.__name__, exc)
                errors.append(f"{resolved_provider.__name__}: {exc}")

        all_available = self._get_available_providers()
        fallback_queue = _build_fallback_queue(
            all_available,
            resolved_provider,
            model,
            resolved_model,
            lambda provider_cls: _get_models_safely(provider_cls, self._client),
            empty_model_fallback="auto",
        )

        for p_name, p_cls, p_model in fallback_queue:
            try:
                provider_instance = self._get_provider_instance(p_cls)
                fallback_kwargs: Dict[str, Any] = dict(call_kwargs)
                fallback_kwargs["model"] = p_model
                response = provider_instance.images.create(**fallback_kwargs)
                self._last_provider = p_name
                if self._client.print_provider_info:
                    _print_provider_selection(p_name, p_model, fallback=True)
                return response
            except (RuntimeError, ValueError, TypeError) as e:
                errors.append(f"{p_name}: {e}")
                continue
        raise RuntimeError(
            f"All image providers failed. Errors: {'; '.join(errors[:5])}"
            if errors
            else "No image providers available."
        )

    def create(self, **kwargs) -> ImageResponse:
        """
        Alias for generate() method.

        Provides compatibility with OpenAI-style image API where create() is
        the standard method name for image generation.

        Args:
            **kwargs: All arguments accepted by generate().

        Returns:
            ImageResponse object containing generated images.

        Examples:
            >>> response = client.images.create(
            ...     prompt="A robot painting a picture",
            ...     model="auto"
            ... )
        """
        return self.generate(**kwargs)


class ClientAudioSpeech:
    """
    Unified audio/speech interface with automatic provider selection and failover.

    Mirrors the nested OpenAI client shape:

        client.audio.speech.create(...)
    """

    def __init__(self, client: "Client"):
        self._client = client
        self._last_provider: Optional[str] = None

    @property
    def last_provider(self) -> Optional[str]:
        return self._last_provider

    def _get_provider_instance(
        self, provider_class: Type[BaseTTSProvider], **kwargs: Any
    ) -> BaseTTSProvider:
        init_kwargs: Dict[str, Any] = dict(kwargs)
        if self._client.api_key:
            init_kwargs["api_key"] = self._client.api_key

        proxy_candidates: List[Dict[str, Any]] = [init_kwargs]
        if self._client.proxies:
            proxy_kwargs = {**init_kwargs, "proxies": self._client.proxies}
            proxy_candidates.insert(0, proxy_kwargs)

            proxy_value = (
                self._client.proxies.get("https")
                or self._client.proxies.get("http")
                or next(iter(self._client.proxies.values()), None)
            )
            if proxy_value:
                proxy_candidates.insert(1, {**init_kwargs, "proxy": proxy_value})

        return _get_provider_instance_cached(
            self._client._provider_cache,
            provider_class,
            proxy_candidates,
            provider_kind="TTS",
        )

    def _fuzzy_resolve_provider_and_model(
        self, model: str
    ) -> Optional[Tuple[Type[BaseTTSProvider], str]]:
        return _fuzzy_resolve_provider_and_model(
            model,
            self._get_available_providers(),
            _get_tts_models_safely,
            print_provider_info=self._client.print_provider_info,
            match_suffix=" (TTS)",
        )

    def _resolve_provider_and_model(
        self, model: str, provider: Optional[Type[BaseTTSProvider]]
    ) -> Tuple[Type[BaseTTSProvider], str]:
        return _resolve_provider_and_model(
            model,
            provider,
            TTS_PROVIDERS,
            self._get_available_providers,
            _get_tts_models_safely,
            print_provider_info=self._client.print_provider_info,
            no_available_message="No available audio providers found.",
            no_available_with_models_message="No available audio providers with models found.",
            provider_no_models_message="TTI Provider {provider} has no available models.",
            no_providers_for_model_message="No audio providers found for model '{model}'",
            provider_empty_model_fallback="gpt-4o-mini-tts",
            match_suffix=" (TTS)",
        )

    def _get_available_providers(self) -> List[Tuple[str, Type[BaseTTSProvider]]]:
        return _get_available_provider_items(
            TTS_PROVIDERS,
            TTS_AUTH_REQUIRED,
            self._client.exclude_tts,
            self._client.api_key,
            drop_auth=self._client.drop_auth_providers,
        )

    @staticmethod
    def _stream_audio_file(audio_file: str, chunk_size: int) -> Generator[bytes, None, None]:
        with open(audio_file, "rb") as file_handle:
            while chunk := file_handle.read(chunk_size):
                yield chunk

    def create(
        self,
        *,
        input_text: Optional[str] = None,
        model: str = "auto",
        voice: Optional[str] = None,
        response_format: str = "mp3",
        instructions: Optional[str] = None,
        stream: bool = False,
        chunk_size: int = 1024,
        provider: Optional[Type[BaseTTSProvider]] = None,
        verbose: bool = False,
        **kwargs: Any,
    ) -> Union[str, Generator[bytes, None, None]]:
        if input_text is None:
            input_text = kwargs.pop("input", None)

        if not input_text or not isinstance(input_text, str):
            raise ValueError("Input text must be a non-empty string")

        try:
            resolved_provider, resolved_model = self._resolve_provider_and_model(model, provider)
        except (RuntimeError, ValueError):
            resolved_provider, resolved_model = None, model

        call_kwargs: Dict[str, Any] = {
            "model": resolved_model,
            "voice": voice,
            "response_format": response_format,
            "instructions": instructions,
            "verbose": verbose,
        }
        call_kwargs.update(kwargs)

        if resolved_provider:
            try:
                provider_instance = self._get_provider_instance(resolved_provider)
                audio_file = provider_instance.tts(input_text, **call_kwargs)
                if audio_file and Path(audio_file).exists():
                    self._last_provider = resolved_provider.__name__
                    if self._client.print_provider_info:
                        _print_provider_selection(resolved_provider.__name__, resolved_model)
                    if stream:
                        return self._stream_audio_file(audio_file, chunk_size)
                    return audio_file
                raise FileNotFoundError(f"Audio file not generated by {resolved_provider.__name__}")
            except Exception as exc:
                ic("TTS provider %s failed: %s", resolved_provider.__name__, exc)

        all_available = self._get_available_providers()
        fallback_queue = _build_fallback_queue(
            all_available,
            resolved_provider,
            model,
            resolved_model,
            _get_tts_models_safely,
            empty_model_fallback="gpt-4o-mini-tts",
        )

        errors: List[str] = []
        for provider_name, provider_class, provider_model in fallback_queue:
            try:
                provider_instance = self._get_provider_instance(provider_class)
                fallback_kwargs: Dict[str, Any] = dict(call_kwargs)
                fallback_kwargs["model"] = provider_model
                audio_file = provider_instance.tts(input_text, **fallback_kwargs)
                if audio_file and Path(audio_file).exists():
                    self._last_provider = provider_name
                    if self._client.print_provider_info:
                        _print_provider_selection(provider_name, provider_model, fallback=True)
                    if stream:
                        return self._stream_audio_file(audio_file, chunk_size)
                    return audio_file
                errors.append(f"{provider_name}: Audio file not generated.")
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")

        raise RuntimeError(f"All audio providers failed. Errors: {'; '.join(errors[:3])}")


class ClientAudio:
    """
    Audio namespace that mirrors the OpenAI client structure.
    """

    def __init__(self, client: "Client"):
        self.speech = ClientAudioSpeech(client)


class Client:
    """
    Unified LLM4Free Client for AI chat, image generation, and audio synthesis.

    A high-level client that provides a single interface for interacting with
    multiple AI providers (chat completions and image generation). Automatically
    selects, caches, and fails over between providers based on availability
    and model support.

    This client aims to provide a seamless, provider-agnostic experience by:
    - Supporting automatic provider selection and fallback
    - Caching provider instances for performance
    - Offering intelligent model resolution (auto, provider/model, or model name)
    - Handling authentication across multiple providers
    - Providing detailed provider information when enabled

    Attributes:
        provider: Optional default provider for chat completions.
        image_provider: Optional default provider for image generation.
        api_key: Optional API key for providers that support authentication.
        proxies: HTTP proxy configuration dictionary.
        exclude: List of provider names to exclude from chat completions.
        exclude_images: List of provider names to exclude from image generation.
        exclude_tts: List of provider names to exclude from audio generation.
        drop_auth_providers: When True (default), exclude providers requiring auth.
        print_provider_info: Whether to print selected provider and model info.
        chat: ClientChat instance for chat completions.
        images: ClientImages instance for image generation.
        audio: ClientAudio instance for speech generation.
        search: Search instance for web/image/news/etc. search.

    Examples:
        >>> # Basic usage with automatic provider selection
        >>> client = Client()
        >>> response = client.chat.completions.create(
        ...     model="auto",
        ...     messages=[{"role": "user", "content": "Hello!"}]
        ... )
        >>> print(response.choices[0].message.content)

        >>> # With provider information and image generation
        >>> client = Client(print_provider_info=True)
        >>> chat_response = client.chat.completions.create(
        ...     model="gpt-4",
        ...     messages=[{"role": "user", "content": "Describe an image"}]
        ... )
        >>> image_response = client.images.generate(
        ...     prompt="A sunset over mountains",
        ...     model="auto"
        ... )

        >>> # Excluding certain providers and using API key
        >>> client = Client(
        ...     api_key="your-api-key-here",
        ...     exclude=["BadProvider"],
        ...     exclude_images=["SlowProvider"]
        ... )

        >>> # Multi-engine search (OpenAI-style)
        >>> search = client.search.create(
        ...     query="python web scraping",
        ...     engine="auto",
        ...     max_results=5,
        ... )
        >>> print(search.engine, len(search.data))
    """

    def __init__(
        self,
        provider: Optional[Type[OpenAICompatibleProvider]] = None,
        image_provider: Optional[Type[TTICompatibleProvider]] = None,
        api_key: Optional[str] = None,
        proxies: Optional[dict] = None,
        exclude: Optional[List[str]] = None,
        exclude_images: Optional[List[str]] = None,
        exclude_tts: Optional[List[str]] = None,
        exclude_search: Optional[List[str]] = None,
        print_provider_info: bool = False,
        drop_auth_providers: bool = True,
        **kwargs: Any,
    ):
        """
        Initialize the LLM4Free Client with optional configuration.

        Args:
            provider: Default provider class for chat completions. If specified,
                     this provider is prioritized in provider resolution. Optional.
            image_provider: Default provider class for image generation. If specified,
                           this provider is prioritized in image resolution. Optional.
            api_key: API key for authenticated providers. Optional. Note: auth-required
                    providers are excluded by default unless ``drop_auth_providers=False``.
            proxies: Dictionary of proxy settings (e.g., {"http": "http://proxy:8080"}).
                    Applied to all provider requests. Optional.
            exclude: List of provider names to exclude from chat completion selection.
                    Names are case-insensitive. Optional.
            exclude_images: List of provider names to exclude from image generation selection.
                           Names are case-insensitive. Optional.
            exclude_tts: List of provider names to exclude from audio generation selection.
                         Names are case-insensitive. Optional.
            exclude_search: List of search engine ids to skip during auto selection.
                            Names are case-insensitive. Optional.
            print_provider_info: If True, prints selected provider name and model to stdout
                                before each request. Useful for debugging. Default is False.
            drop_auth_providers: When True (default), providers that require authentication
                                 are excluded from resolution entirely — even if ``api_key``
                                 is set. Set to False to allow auth-required providers when an
                                 ``api_key`` is supplied. Optional.
            **kwargs: Additional keyword arguments stored for future use.

        Examples:
            >>> # Minimal setup - use default providers
            >>> client = Client()

            >>> # With authentication and custom settings
            >>> client = Client(
            ...     api_key="sk-1234567890abcdef",
            ...     proxies={"http": "http://proxy.example.com:8080"},
            ...     exclude=["UnreliableProvider"],
            ...     print_provider_info=True
            ... )

            >>> # With specific default providers
            >>> from llm4free.llm.groq import Groq
            >>> from llm4free.TTI.stable import StableDiffusion
            >>> client = Client(
            ...     provider=Groq,
            ...     image_provider=StableDiffusion
            ... )
        """
        self.provider = provider
        self.image_provider = image_provider
        self.api_key = api_key
        self.proxies = proxies or {}
        self.exclude = exclude or []
        self.exclude_images = exclude_images or []
        self.exclude_tts = exclude_tts or []
        self.exclude_search = exclude_search or []
        self.print_provider_info = print_provider_info
        self.drop_auth_providers = drop_auth_providers
        self.kwargs = kwargs

        self._provider_cache = {}
        self.chat = ClientChat(self)
        self.images = ClientImages(self)
        self.audio = ClientAudio(self)
        search_proxy = None
        if self.proxies:
            search_proxy = self.proxies.get("https") or self.proxies.get("http")
        self.search = Search(
            proxy=search_proxy,
            exclude=self.exclude_search,
            print_provider_info=print_provider_info,
        )

    @staticmethod
    def get_chat_providers() -> List[str]:
        """
        Returns a list of all available chat provider names.

        Queries the global OPENAI_PROVIDERS registry that is populated
        at module load time. Names are not normalized and appear as
        defined in their respective classes.

        Returns:
            List of provider class names available for chat completions.

        Examples:
            >>> providers = Client.get_chat_providers()
            >>> print("GPT4Free" in providers)
            True
            >>> print(len(providers))
            42
        """
        return list(OPENAI_PROVIDERS.keys())

    @staticmethod
    def get_image_providers() -> List[str]:
        """
        Returns a list of all available image provider names.

        Queries the global TTI_PROVIDERS registry that is populated
        at module load time. Names are not normalized and appear as
        defined in their respective classes.

        Returns:
            List of provider class names available for image generation.

        Examples:
            >>> providers = Client.get_image_providers()
            >>> print("StableDiffusion" in providers)
            True
            >>> print(len(providers))
            8
        """
        return list(TTI_PROVIDERS.keys())

    @staticmethod
    def get_search_providers() -> List[str]:
        """
        Returns every registered search engine id.

        Returns:
            List of engine ids accepted by ``client.search.create(engine=...)``.

        Examples:
            >>> Client.get_search_providers()
            ['duckduckgo', 'bing', 'brave', 'yahoo', 'mojeek', 'wikipedia', 'parallel', 'serpbase']
        """
        return Search().list_engines()

    @staticmethod
    def get_free_chat_providers() -> List[str]:
        """
        Returns a list of chat providers that don't require authentication.

        Filters the global OPENAI_PROVIDERS registry to include only providers
        where required_auth is False. These providers can be used without
        an API key.

        Returns:
            List of free chat provider class names.

        Examples:
            >>> free_providers = Client.get_free_chat_providers()
            >>> print("GPT4Free" in free_providers)
            True
            >>> print(len(free_providers))
            35
        """
        return [name for name in OPENAI_PROVIDERS.keys() if name not in OPENAI_AUTH_REQUIRED]

    @staticmethod
    def get_free_image_providers() -> List[str]:
        """
        Returns a list of image providers that don't require authentication.

        Filters the global TTI_PROVIDERS registry to include only providers
        where required_auth is False. These providers can be used without
        an API key.

        Returns:
            List of free image provider class names.

        Examples:
            >>> free_providers = Client.get_free_image_providers()
            >>> print("StableDiffusion" in free_providers)
            True
            >>> print(len(free_providers))
            6
        """
        return [name for name in TTI_PROVIDERS.keys() if name not in TTI_AUTH_REQUIRED]

    @staticmethod
    def get_tts_providers() -> List[str]:
        """
        Returns a list of all available TTS provider names.
        """
        return list(TTS_PROVIDERS.keys())

    @staticmethod
    def get_free_tts_providers() -> List[str]:
        """
        Returns a list of TTS providers that don't require authentication.
        """
        return [name for name in TTS_PROVIDERS.keys() if name not in TTS_AUTH_REQUIRED]

    @staticmethod
    def get_audio_providers() -> List[str]:
        """
        Alias for get_tts_providers().
        """
        return Client.get_tts_providers()

    @staticmethod
    def get_free_audio_providers() -> List[str]:
        """
        Alias for get_free_tts_providers().
        """
        return Client.get_free_tts_providers()


try:
    from llm4free.server.server import run_api as _run_api_impl
    from llm4free.server.server import run_api as _start_server_impl

    def run_api(*args: Any, **kwargs: Any) -> Any:
        """
        Runs the FastAPI OpenAI-compatible API server.

        Delegates to llm4free.server.server.run_api to start an OpenAI-compatible
        HTTP API server that provides chat and image endpoints. Requires the
        'api' optional dependencies to be installed.

        Args:
            *args: Positional arguments passed to the underlying run_api implementation.
            **kwargs: Keyword arguments passed to the underlying run_api implementation.
                     Common options include host, port, debug, and reload.

        Returns:
            The return value from the underlying FastAPI run function.

        Raises:
            ImportError: If llm4free.server.server is not available.

        Examples:
            >>> from llm4free.client import run_api
            >>> run_api(host="0.0.0.0", port=8000)
        """
        return _run_api_impl(*args, **kwargs)

    def start_server(*args: Any, **kwargs: Any) -> Any:
        """
        Starts the FastAPI OpenAI-compatible API server.

        Delegates to llm4free.server.server.start_server to initialize and run
        an OpenAI-compatible HTTP API server. This is typically the main entry
        point for starting the llm4free server in production or development.

        Args:
            *args: Positional arguments passed to the underlying start_server implementation.
            **kwargs: Keyword arguments passed to the underlying start_server implementation.
                     Common options include host, port, workers, and config paths.

        Returns:
            The return value from the underlying server implementation.

        Raises:
            ImportError: If llm4free.server.server is not available.

        Examples:
            >>> from llm4free.client import start_server
            >>> start_server()
        """
        return _start_server_impl(*args, **kwargs)

except ImportError:

    def run_api(*args: Any, **kwargs: Any) -> Any:
        """
        Runs the FastAPI OpenAI-compatible API server.

        Raises ImportError if the server module is not available.
        Install with: pip install llm4free[api]

        Raises:
            ImportError: Always raised; server not available in current environment.
        """
        raise ImportError("llm4free.server.server.run_api is not available.")

    def start_server(*args: Any, **kwargs: Any) -> Any:
        """
        Starts the FastAPI OpenAI-compatible API server.

        Raises ImportError if the server module is not available.
        Install with: pip install llm4free[api]

        Raises:
            ImportError: Always raised; server not available in current environment.
        """
        raise ImportError("llm4free.server.server.start_server is not available.")


if __name__ == "__main__":
    client = Client(print_provider_info=True)
    print("Testing auto resolution...")
    try:
        response = client.chat.completions.create(
            model="auto", messages=[{"role": "user", "content": "Hi"}]
        )
        if not inspect.isgenerator(response):
            completion = response
            if (
                completion.choices
                and completion.choices[0].message is not None
                and completion.choices[0].message.content is not None
            ):
                print(f"Auto Result: {completion.choices[0].message.content[:50]}...")
            else:
                print("Auto Result: Empty response")
        else:
            print("Streaming response received")
    except Exception as e:
        print(f"Error: {e}")
