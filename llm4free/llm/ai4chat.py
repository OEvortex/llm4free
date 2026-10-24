import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

from curl_cffi.requests import RequestsError

from llm4free.litagent import agent

# Import base classes and utility structures
from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
)
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
    count_tokens,
)

# Available models for AI4Chat (text models only, synced from https://www.ai4chat.co/models)
MODELS = {
    # Popular Models
    "gpt-5.2": "GPT 5.2",
    "claude-haiku-4.5": "Claude Haiku 4.5",
    "gemini-3-flash": "Gemini 3 Flash",
    "grok-4.1-fast": "Grok 4.1 Fast",
    "kimi-k2.5": "Kimi K2.5",
    # OpenAI Models
    "gpt-3.5": "ChatGPT (GPT 3.5)",
    "gpt-4o": "GPT 4o",
    "gpt-4.5": "GPT-4.5",
    "gpt-4o-mini": "GPT 4o Mini",
    "gpt-4o-search-preview": "GPT-4o Search Preview",
    "gpt-4o-mini-search-preview": "GPT-4o mini Search Preview",
    "gpt-4.1": "GPT 4.1",
    "gpt-4.1-mini": "GPT 4.1 Mini",
    "gpt-4.1-nano": "GPT 4.1 Nano",
    "codex-mini": "Codex Mini",
    "o1": "o1",
    "o1-pro": "o1-pro",
    "o3-mini": "o3-mini",
    "o3-mini-high": "o3-mini-high",
    "o4-mini": "o4 Mini",
    "o4-mini-high": "o4 Mini High",
    "gpt-oss-20b": "GPT OSS 20B",
    "gpt-oss-120b": "GPT OSS 120B",
    "gpt-5-mini": "GPT-5 Mini",
    "gpt-5-nano": "GPT-5 Nano",
    "gpt-5": "GPT-5",
    "gpt-5.1": "GPT 5.1",
    "gpt-5.1-codex": "GPT 5.1 Codex",
    "gpt-5.1-codex-mini": "GPT 5.1 Codex-Mini",
    "gpt-5.2-codex": "GPT 5.2 Codex",
    "gpt-5.3-codex": "GPT 5.3 Codex",
    "gpt-5.3": "GPT 5.3",
    "gpt-5.4": "GPT 5.4",
    "gpt-5.4-pro": "GPT 5.4 Pro",
    "gpt-5.5": "GPT 5.5",
    # Anthropic Models
    "claude-3-haiku": "Claude 3 Haiku",
    "claude-3.5-haiku": "Claude 3.5 Haiku",
    "claude-3.7-sonnet": "Claude 3.7 Sonnet",
    "claude-sonnet-4": "Claude Sonnet 4",
    "claude-opus-4": "Claude Opus 4",
    "claude-opus-4.1": "Claude Opus 4.1",
    "claude-sonnet-4.5": "Claude Sonnet 4.5",
    "claude-opus-4.6": "Claude Opus 4.6",
    "claude-sonnet-4.6": "Claude Sonnet 4.6",
    "claude-opus-4.7": "Claude Opus 4.7",
    "claude-v2.0": "Claude v2.0",
    "claude-v2.1": "Claude v2.1",
    "claude-instant-v1": "Claude Instant v1",
    "claude-3-opus": "Claude 3 Opus",
    "claude-3-sonnet": "Claude 3 Sonnet",
    "claude-3.5-sonnet": "Claude 3.5 Sonnet",
    # DeepSeek Models
    "deepseek-v3": "DeepSeek V3",
    "deepseek-v3.1": "DeepSeek v3.1",
    "deepseek-v3.2": "DeepSeek v3.2",
    "deepseek-v3-0324": "DeepSeek V3 0324",
    "deepseek-v4-flash": "DeepSeek v4 Flash",
    "deepseek-v4-pro": "DeepSeek v4 Pro",
    "deepseek-v2-chat": "DeepSeek-V2 Chat",
    "deepseek-coder": "Deepseek Coder",
    "r1-distill-qwen-1.5b": "R1 Distill Qwen 1.5B",
    "r1-distill-qwen-14b": "R1 Distill Qwen 14B",
    "r1-distill-qwen-32b": "R1 Distill Qwen 32B",
    "r1-distill-llama-70b": "R1 Distill Llama 70B",
    "r1": "R1",
    # Google Models
    "gemini-flash-2.0": "Gemini Flash 2.0",
    "gemini-flash-lite-2.0": "Gemini Flash Lite 2.0",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    "gemini-2.5-flash-preview": "Gemini 2.5 Flash Preview",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemma-2-9b": "Gemma 2 9B",
    "gemma-2-27b": "Gemma 2 27B",
    "gemma-3-27b": "Gemma 3 27B",
    "gemma-4-31b": "Gemma 4 31B",
    "gemma-7b": "Gemma 7B",
    "gemini-3-pro": "Gemini 3 Pro",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "gemini-3.1-pro": "Gemini 3.1 Pro",
    "gemini-1.0-pro": "Gemini 1.0 Pro",
    "gemini-1.5-flash": "Gemini 1.5 Flash",
    "gemini-1.5-flash-8b": "Gemini 1.5 Flash 8B",
    "gemini-1.5-pro": "Gemini 1.5 Pro",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-2.0-flash-thinking-experimental": "Gemini 2.0 Flash Thinking Experimental",
    "gemini-pro-2.0-experimental": "Gemini Pro 2.0 Experimental",
    # Meta Models
    "llama-v3-8b": "Llama v3 8B",
    "llama-v3-70b": "Llama v3 70B",
    "llama-v3.1-8b": "Llama v3.1 8B",
    "llama-v3.1-70b": "Llama v3.1 70B",
    "llama-v3.1-405b": "Llama v3.1 405B",
    "llama-v3.2-1b": "Llama v3.2 1B",
    "llama-v3.2-3b": "Llama v3.2 3B",
    "llama-v3.2-11b": "Llama v3.2 11B",
    "llama-v3.2-90b": "Llama v3.2 90B",
    "llama-v3.3-70b": "Llama v3.3 70B",
    "llama-4-scout": "Llama 4 Scout",
    "llama-4-maverick": "Llama 4 Maverick",
    "llama-v2-13b": "Llama v2 13B",
    "llama-v2-70b": "Llama v2 70B",
    # Mistral Models
    "mistral-7b-instruct": "Mistral 7B Instruct",
    "mistral-7b-instruct-v0.1": "Mistral 7B Instruct v0.1",
    "mistral-7b-instruct-v0.2": "Mistral 7B Instruct v0.2",
    "mistral-7b-instruct-v0.3": "Mistral 7B Instruct v0.3",
    "mixtral-8x7b-instruct": "Mixtral 8x7B Instruct",
    "mixtral-8x22b-instruct": "Mixtral 8x22B Instruct",
    "mistral-nemo": "Mistral Nemo",
    "mistral-large-2": "Mistral Large 2",
    "mistral-large-3": "Mistral Large 3",
    "mistral-medium-3": "Mistral Medium 3",
    "mistral-small-3": "Mistral Small 3",
    "mistral-small-3.1-24b": "Mistral Small 3.1 24B",
    "mistral-small-3.2-24b": "Mistral Small 3.2 24B",
    "mistral-small-4": "Mistral Small 4",
    "ministral-3b": "Ministral 3B",
    "ministral-8b": "Ministral 8B",
    "ministral-3-3b": "Ministral 3 3B",
    "ministral-3-8b": "Ministral 3 8B",
    "ministral-3-14b": "Ministral 3 14B",
    "pixtral-12b": "Pixtral 12B",
    "codestral": "Codestral",
    "codestral-mamba": "Codestral Mamba",
    "saba": "Saba",
    "devstral-small-1.1": "Devstral Small 1.1",
    "devstral-medium": "Devstral Medium",
    "devstral-small": "Devstral Small",
    "devstral-2": "Devstral 2",
    # xAI Models
    "grok-2": "Grok 2",
    "grok-3-mini-beta": "Grok 3 Mini Beta",
    "grok-3-beta": "Grok 3 Beta",
    "grok-4": "Grok 4",
    "grok-4-fast": "Grok 4 Fast",
    "grok-4.2": "Grok 4.2",
    "grok-4.2-multi-agent": "Grok 4.2 Multi Agent",
    "grok-beta": "Grok Beta",
    "grok-code-fast-1": "Grok Code Fast 1",
    # Z.ai Models
    "glm-4-32b": "GLM 4 32B",
    "glm-4.5-air": "GLM 4.5 Air",
    "glm-4.5": "GLM 4.5",
    "glm-4.6": "GLM 4.6",
    "glm-4.7-flash": "GLM 4.7 Flash",
    "glm-5": "GLM 5",
    "glm-5-turbo": "GLM 5 Turbo",
    "glm-5.1": "GLM 5.1",
    # AI21 Models
    "jamba-mini-1.7": "Jamba Mini 1.7",
    "jamba-large-1.7": "Jamba Large 1.7",
    "jamba-1.5-large": "Jamba 1.5 Large",
    "jamba-1.5-mini": "Jamba 1.5 Mini",
    "jamba-instruct": "Jamba Instruct",
    "jamba-large-1.6": "Jamba Large 1.6",
    "jamba-mini-1.6": "Jamba Mini 1.6",
    # Amazon Models
    "nova-lite-1.0": "Nova Lite 1.0",
    "nova-micro-1.0": "Nova Micro 1.0",
    "nova-pro-1.0": "Nova Pro 1.0",
    "nova-premier-1.0": "Nova Premier 1.0",
    "nova-2-lite": "Nova 2 Lite",
    # Alibaba Cloud Models
    "qwen-2.5-7b": "Qwen 2.5 7B",
    "qwen-2.5-32b": "Qwen 2.5 32B",
    "qwen-2.5-72b": "Qwen 2.5 72B",
    "qwen-2.5-coder-32b": "Qwen 2.5 Coder 32B",
    "qwen-2-72b": "Qwen 2 72B",
    "qwen-2-7b": "Qwen 2 7B",
    "qwen-1.5-110b-chat": "Qwen 1.5 110B Chat",
    "qwen-1.5-4b-chat": "Qwen 1.5 4B Chat",
    "qwen-1.5-72b": "Qwen 1.5 72B",
    "qwen-1.5-7b-chat": "Qwen 1.5 7B Chat",
    "qwen-3-14b": "Qwen 3 14B",
    "qwen-3-32b": "Qwen 3 32B",
    "qwen-3-30b-a3b": "Qwen 3 30B A3B",
    "qwen-3-235b-a22b": "Qwen 3 235B A22B",
    "qwen-3-coder": "Qwen 3 Coder",
    "qwen3-coder-plus": "Qwen3 Coder Plus",
    "qwen3-max": "Qwen3 Max",
    "qwen-plus": "Qwen Plus",
    "qwen-max": "Qwen Max",
    "qwen-turbo": "Qwen Turbo",
    "qwq-32b": "QwQ 32B",
    "qwq-32b-preview": "QwQ 32B Preview",
    "qwen-3-max-thinking": "Qwen 3 Max Thinking",
    "qwen-3-coder-next": "Qwen 3 Coder Next",
    "qwen-3.5-397b-a17b": "Qwen 3.5 397B A17B",
    "qwen-3.5-plus": "Qwen 3.5 Plus",
    "qwen3.5-9b": "Qwen3.5-9B",
    # Cohere Models
    "command": "Command",
    "command-a": "Command A",
    "command-r": "Command R",
    "command-r7b": "Command R7B",
    "command-r-plus": "Command R+",
    # Dolphin Models
    "dolphin-2.9.2-mixtral-8x22b": "Dolphin 2.9.2 Mixtral 8x22B",
    "dolphin-2.6-mixtral-8x7b": "Dolphin 2.6 Mixtral 8x7B",
    "dolphin-llama-3-70b": "Dolphin Llama 3 70B",
    # Inception Models
    "inception-mercury": "Inception Mercury",
    "mercury-2": "Mercury 2",
    # Inflection AI Models
    "inflection-3-pi": "Inflection 3 Pi",
    "inflection-3-productivity": "Inflection 3 Productivity",
    # Liquid Models
    "lfm-3b": "LFM 3B",
    "lfm-7b": "LFM 7B",
    "lfm2-2.6b": "LFM2 2.6B",
    "lfm2-8b": "LFM2 8B",
    # Magnum Models
    "magnum-v4-72b": "Magnum v4 72B",
    "magnum-72b": "Magnum 72B",
    "magnum-v2-72b": "Magnum v2 72B",
    # Microsoft Models
    "phi-3-mini-instruct": "Phi-3 Mini Instruct",
    "phi-3.5-mini-128k-instruct": "Phi-3.5 Mini 128K Instruct",
    "phi-3-medium-instruct": "Phi-3 Medium Instruct",
    "phi-4": "Phi 4",
    "phi-4-reasoning-plus": "Phi 4 Reasoning Plus",
    "wizardlm-2-8x22b": "WizardLM-2 8x22B",
    "wizardlm-2-7b": "WizardLM-2 7B",
    # Midnight Rose Models
    "midnight-rose-70b": "Midnight Rose 70B",
    # MiniMax Models
    "minimax-01": "MiniMax-01",
    "minimax-m1": "MiniMax M1",
    "minimax-m2": "MiniMax M2",
    "minimax-m2.1": "MiniMax M2.1",
    "minimax-m2.5": "MiniMax M2.5",
    "minimax-m2.7": "MiniMax M2.7",
    "minimax-v01": "Minimax v01",
    # MoonshotAI Models
    "kimi-k2": "Kimi K2",
    "kimi-k2-thinking": "Kimi K2 Thinking",
    "kimi-k2.6": "Kimi K2.6",
    # MythoMax Models
    "mythomax-13b": "MythoMax 13B",
    "mythomist-7b": "MythoMist 7B",
    # Noromaid Models
    "noromaid-20b": "Noromaid 20B",
    "noromaid-mixtral-8x7b-instruct": "Noromaid Mixtral 8x7B Instruct",
    # NousResearch Models
    "hermes-2-pro-llama-3-8b": "Hermes 2 Pro - Llama-3 8B",
    "hermes-2-mixtral-8x7b-dpo": "Hermes 2 Mixtral 8x7B DPO",
    "hermes-2-mixtral-8x7b-sft": "Hermes 2 Mixtral 8x7B SFT",
    "hermes-2-theta-8b": "Hermes 2 Theta 8B",
    "hermes-13b": "Hermes 13B",
    "hermes-2-mistral-7b-dpo": "Hermes 2 - Mistral 7B DPO",
    "hermes-3-70b-instruct": "Hermes 3 70B Instruct",
    "hermes-3-405b-instruct": "Hermes 3 405B Instruct",
    "hermes-4-70b": "Hermes 4 70B",
    # NVIDIA Models
    "nvidia-llama-3.1-nemotron-70b": "NVIDIA Llama 3.1 Nemotron 70B",
    "nvidia-nemotron-4-340b-instruct": "NVIDIA Nemotron-4 340B Instruct",
    # Perplexity Models
    "sonar": "Sonar",
    "sonar-reasoning": "Sonar Reasoning",
    "sonar-pro": "Sonar Pro",
    "sonar-reasoning-pro": "Sonar Reasoning Pro",
    "sonar-deep-research": "Sonar Deep Research",
    # Rocinante Models
    "rocinante-12b": "Rocinante 12B",
    "unslopnemo-v4.1": "UnslopNemo v4.1",
    # Website new models
    "capybara-34b": "Capybara 34B",
    "capybara-7b": "Capybara 7B",
    "chronos-hermes-13b-v2": "Chronos Hermes 13B v2",
    "codellama-34b": "CodeLlama 34B",
    "codellama-70b-instruct": "CodeLlama 70B Instruct",
    "dbrx-132b-instruct": "DBRX 132B Instruct",
    "firellava-13b": "FireLLaVA 13B",
    "gpt-5.4-mini": "GPT 5.4 Mini",
    "gpt-5.4-nano": "GPT 5.4 Nano",
    "inferor-12b": "Inferor 12B",
    "llava-v1.6-34b": "LLaVA v1.6 34B",
    "llama-3-lumimaid-70b": "Llama 3 Lumimaid 70B",
    "llama-3-lumimaid-8b": "Llama 3 Lumimaid 8B",
    "llama-3-soliloquy-8b-v2": "Llama 3 Soliloquy 8B v2",
    "llama-3.1-sonar-405b-online": "Llama 3.1 Sonar 405B Online",
    "llama-3.1-sonar-70b-online": "Llama 3.1 Sonar 70B Online",
    "llama-3.1-sonar-8b-online": "Llama 3.1 Sonar 8B Online",
    "llama3-sonar-70b-online": "Llama3 Sonar 70B Online",
    "llama3-sonar-8b-online": "Llama3 Sonar 8B Online",
    "lumimaid-v0.2-70b": "Lumimaid v0.2 70B",
    "lzlv-70b": "Lzlv 70B",
    "mimo-v2-pro": "MiMo-V2-Pro",
    "nemotron-3-super": "Nemotron 3 Super",
    "olmo-7b-instruct": "OLMo 7B Instruct",
    "olmo-2-32b-instruct": "Olmo 2 32B Instruct",
    "openchat-3.5-8b": "OpenChat 3.5 8B",
    "openchat-3.6-8b": "OpenChat 3.6 8B",
    "openhermes-2.5-mistral-7b": "OpenHermes 2.5 Mistral 7B",
    "phind-codellama-34b-v2": "Phind CodeLlama 34B v2",
    "stripedhyena-nous-7b": "StripedHyena Nous 7B",
    "yi-1.5-34b": "Yi 1.5 34B",
    "yi-34b": "Yi 34B",
    "yi-6b": "Yi 6B",
    "yi-large": "Yi Large",
    "yi-large-turbo": "Yi Large Turbo",
    "o1-mini": "o1-mini",
    "o1-preview": "o1-preview",
}


# --- AI4Chat Client ---


# Bodies the legacy gateway returns with HTTP 200 when it rejects a request. These are
# error markers, never assistant content, so they must be raised rather than returned.
LEGACY_ERROR_BODIES = frozenset(
    {
        "invalid request",
        "invalid request.",
        "bad request",
        "unauthorized",
        "forbidden",
        "missing authentication token",
        "access denied",
        "not found",
        "internal server error",
    }
)


class Completions(BaseCompletions):
    def __init__(self, client: "AI4Chat"):
        self._client = client

    # ------------------------------------------------------------------ public

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create

        Requests go to AI4Chat's official OpenAI-compatible endpoint, which needs an
        API key (``AI4Chat(api_key=...)``). When no key is configured the legacy
        unauthenticated gateway is attempted instead and raises if it is unavailable.
        """
        model_name = self._client.resolve_model_name(model)
        payload_messages = self._client.prepare_messages(messages)

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(
                request_id,
                created_time,
                model,
                model_name,
                payload_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                timeout=timeout,
                proxies=proxies,
                **kwargs,
            )
        return self._create_non_stream(
            request_id,
            created_time,
            model,
            model_name,
            payload_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            timeout=timeout,
            proxies=proxies,
            **kwargs,
        )

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _build_payload(
        model_name: str,
        messages: List[Dict[str, Any]],
        stream: bool,
        max_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the JSON body for AI4Chat's OpenAI-compatible endpoint."""
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p

        # AI4Chat-specific optional parameters documented on their /api pages.
        for key in ("language", "tone", "wordcount", "googleSearchStatus", "top_k"):
            if kwargs.get(key) is not None:
                payload[key] = kwargs[key]
        return payload

    def _post_api(
        self,
        payload: Dict[str, Any],
        stream: bool,
        timeout: Optional[int],
        proxies: Optional[dict],
    ) -> Any:
        """POST to the official endpoint, mapping transport/API errors to IOError."""
        if not self._client.api_key:
            raise IOError(
                "AI4Chat requires an API key. Create a free key at "
                "https://www.ai4chat.co/api and pass it as AI4Chat(api_key='...')."
            )

        original_proxies = dict(self._client.session.proxies)
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))

        try:
            response = self._client.session.post(
                self._client.api_endpoint,
                data=json.dumps(payload),
                headers=self._client.headers,
                stream=stream,
                timeout=timeout if timeout is not None else self._client.timeout,
                impersonate="chrome",
            )
        except RequestsError as e:
            raise IOError(f"AI4Chat request failed: {e}") from e
        finally:
            if proxies is not None:
                cast(Dict, self._client.session.proxies).clear()
                self._client.session.proxies.update(cast(Any, original_proxies))

        self._raise_for_api_error(response)
        return response

    @staticmethod
    def _raise_for_api_error(response: Any) -> None:
        """Turn a non-2xx AI4Chat response into an actionable exception."""
        status = getattr(response, "status_code", 200)
        if status is None or status < 400:
            return

        detail = ""
        body_text = (getattr(response, "text", "") or "").strip()

        # A streamed response body has not been consumed yet, and curl_cffi's streaming
        # Response exposes neither read() nor a populated .text, so drain the iterator.
        if not body_text:
            iterator = getattr(response, "iter_content", None)
            if callable(iterator):
                parts = []
                try:
                    for part in iterator(chunk_size=None):
                        if not part:
                            continue
                        parts.append(
                            part.decode("utf-8", "replace")
                            if isinstance(part, bytes)
                            else str(part)
                        )
                except Exception:
                    pass
                body_text = "".join(parts).strip()

        try:
            body = json.loads(body_text) if body_text else None
            if isinstance(body, dict):
                raw = body.get("error") or body.get("message") or body.get("detail")
                detail = str(raw) if raw else json.dumps(body)
            elif body is not None:
                detail = str(body)
            else:
                detail = body_text
        except (json.JSONDecodeError, TypeError):
            detail = body_text

        if status in (401, 403):
            hint = (
                "AI4Chat rejected the API key. Create a free key at "
                "https://www.ai4chat.co/api and pass it as AI4Chat(api_key='...')."
            )
        elif status == 404:
            hint = f"Unknown AI4Chat endpoint: {getattr(response, 'url', '')}"
        elif status == 429:
            hint = "AI4Chat rate limit or exhausted free credits. Retry later."
        elif status >= 500:
            hint = "AI4Chat upstream error. Retry later."
        else:
            hint = "Check the request parameters."

        raise IOError(f"AI4Chat request failed (HTTP {status}): {detail or 'no detail'}. {hint}")

    # ------------------------------------------------------------ non-streaming

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        model_name: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        """Get a complete, non-streamed response from AI4Chat."""
        if not self._client.api_key:
            return self._create_legacy_non_stream(
                request_id,
                created_time,
                model,
                model_name,
                messages,
                timeout=timeout,
                proxies=proxies,
                **kwargs,
            )

        try:
            payload = self._build_payload(
                model_name, messages, False, max_tokens, temperature, top_p, kwargs
            )
            response = self._post_api(payload, stream=False, timeout=timeout, proxies=proxies)

            try:
                data = response.json()
            except Exception as e:
                raise IOError(
                    "AI4Chat returned a non-JSON response: "
                    f"{(getattr(response, 'text', '') or '')[:200]}"
                ) from e

            if not isinstance(data, dict):
                raise IOError(f"AI4Chat returned an unexpected payload: {str(data)[:200]}")

            # Some deployments still answer 200 with an error envelope.
            if data.get("error") and not data.get("choices"):
                raise IOError(f"AI4Chat request failed: {data['error']}")

            choices = data.get("choices") or []
            raw_choice = choices[0] if choices else {}
            message = raw_choice.get("message") or {}

            content = message.get("content")
            if content is None:
                content = message.get("reasoning_content") or ""
            elif not isinstance(content, str):
                content = str(content)

            finish_reason = raw_choice.get("finish_reason") or "stop"

            usage = data.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            if not isinstance(prompt_tokens, int):
                prompt_tokens = count_tokens(" ".join(str(m.get("content", "")) for m in messages))
            if not isinstance(completion_tokens, int):
                completion_tokens = count_tokens(content)

            return ChatCompletion(
                id=data.get("id") or request_id,
                choices=[
                    Choice(
                        index=raw_choice.get("index", 0),
                        message=ChatCompletionMessage(role="assistant", content=content),
                        finish_reason=finish_reason,
                    )
                ],
                created=data.get("created") or created_time,
                model=model,
                usage=CompletionUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
            )
        except RequestsError as e:
            print(f"Error during AI4Chat non-stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e
        except IOError:
            raise
        except Exception as e:
            print(f"Unexpected error during AI4Chat non-stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e

    # --------------------------------------------------------------- streaming

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        model_name: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Stream a response from AI4Chat as OpenAI-compatible chunks."""
        if not self._client.api_key:
            return self._create_legacy_stream(
                request_id,
                created_time,
                model,
                model_name,
                messages,
                timeout=timeout,
                proxies=proxies,
                **kwargs,
            )

        payload = self._build_payload(
            model_name, messages, True, max_tokens, temperature, top_p, kwargs
        )
        response = self._post_api(payload, stream=True, timeout=timeout, proxies=proxies)
        return self._iter_sse(response, request_id, created_time, model)

    def _iter_sse(
        self,
        response: Any,
        request_id: str,
        created_time: int,
        model: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Parse AI4Chat's SSE stream into ChatCompletionChunk objects."""
        buffer = ""
        done = False
        try:
            for raw in response.iter_content(chunk_size=None):
                if not raw:
                    continue
                try:
                    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                except UnicodeDecodeError:
                    continue

                buffer += text

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        done = True
                        break

                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(event, dict):
                        continue
                    if event.get("error"):
                        raise IOError(f"AI4Chat stream error: {event['error']}")

                    for choice in event.get("choices") or []:
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if content is None:
                            content = delta.get("reasoning_content")
                        if not content:
                            continue

                        yield ChatCompletionChunk(
                            id=event.get("id") or request_id,
                            choices=[
                                Choice(
                                    index=choice.get("index", 0),
                                    delta=ChoiceDelta(
                                        content=str(content), role=delta.get("role") or "assistant"
                                    ),
                                    finish_reason=choice.get("finish_reason"),
                                )
                            ],
                            created=event.get("created") or created_time,
                            model=model,
                        )

                if done:
                    break

            yield ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=None, role=None),
                        finish_reason="stop",
                    )
                ],
                created=created_time,
                model=model,
            )
        except RequestsError as e:
            print(f"Error during AI4Chat stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e
        except IOError:
            raise
        except Exception as e:
            print(f"Unexpected error during AI4Chat stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e

    # ----------------------------------------------------- legacy free gateway

    def _create_legacy_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        model_name: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        """Best-effort path via the legacy unauthenticated gateway (no API key)."""
        try:
            full_response = self._get_legacy_response(
                messages,
                country=str(kwargs.get("country", self._client.country)),
                user_id=str(kwargs.get("user_id", self._client.user_id)),
                model=model_name,
                timeout=timeout,
                proxies=proxies,
            )

            prompt_text = " ".join(str(m.get("content", "")) for m in messages)
            prompt_tokens = count_tokens(prompt_text)
            completion_tokens = count_tokens(full_response)

            return ChatCompletion(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        message=ChatCompletionMessage(role="assistant", content=full_response),
                        finish_reason="stop",
                    )
                ],
                created=created_time,
                model=model,
                usage=CompletionUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
            )
        except RequestsError as e:
            print(f"Error during AI4Chat non-stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e
        except IOError:
            raise
        except Exception as e:
            print(f"Unexpected error during AI4Chat non-stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e

    def _create_legacy_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        model_name: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Simulate streaming by slicing the legacy gateway's single-shot reply."""
        try:
            full_response = self._get_legacy_response(
                messages,
                country=str(kwargs.get("country", self._client.country)),
                user_id=str(kwargs.get("user_id", self._client.user_id)),
                model=model_name,
                timeout=timeout,
                proxies=proxies,
            )

            buffer = full_response
            chunk_size = 48
            while buffer:
                chunk_text = buffer[:chunk_size]
                buffer = buffer[chunk_size:]
                if not chunk_text.strip():
                    continue

                yield ChatCompletionChunk(
                    id=request_id,
                    choices=[
                        Choice(
                            index=0,
                            delta=ChoiceDelta(content=chunk_text, role="assistant"),
                            finish_reason=None,
                        )
                    ],
                    created=created_time,
                    model=model,
                )

            yield ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=None, role=None),
                        finish_reason="stop",
                    )
                ],
                created=created_time,
                model=model,
            )
        except RequestsError as e:
            print(f"Error during AI4Chat stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e
        except IOError:
            raise
        except Exception as e:
            print(f"Unexpected error during AI4Chat stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e

    def _get_legacy_response(
        self,
        messages: List[Dict[str, Any]],
        country: str,
        user_id: str,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
    ) -> str:
        """
        Call the legacy unauthenticated AI4Chat gateway.

        The gateway answers rejected requests with HTTP 200 and an error string in the
        body, so ``raise_for_status()`` is not enough - the body is validated here and
        such replies are raised instead of being returned as assistant content.
        """
        from llm4free.llm.utils import format_prompt

        conversation_prompt = format_prompt(messages, add_special_tokens=True, include_system=True)

        original_proxies = dict(self._client.session.proxies)
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))

        try:
            params: Dict[str, str] = {
                "text": conversation_prompt,
                "country": country,
                "user_id": user_id,
            }
            if model:
                params["model"] = model

            response = self._client.session.get(
                self._client.legacy_endpoint,
                params=params,
                headers=self._client.headers,
                timeout=timeout if timeout is not None else self._client.timeout,
                impersonate="chrome",
            )
            response.raise_for_status()
        except RequestsError as e:
            raise IOError(f"AI4Chat request failed: {e}") from e
        finally:
            if proxies is not None:
                cast(Dict, self._client.session.proxies).clear()
                self._client.session.proxies.update(cast(Any, original_proxies))

        response_text = (getattr(response, "text", "") or "").strip()

        # The gateway returns a JSON string (quoted) for successful replies.
        if response_text.startswith('"') and response_text.endswith('"') and len(response_text) > 1:
            try:
                decoded = json.loads(response_text)
                if isinstance(decoded, str):
                    response_text = decoded
            except json.JSONDecodeError:
                response_text = response_text[1:-1]

        normalized = response_text.strip().lower()
        if normalized in LEGACY_ERROR_BODIES:
            raise IOError(
                f"AI4Chat's free gateway is unavailable (returned {normalized!r}). "
                "Create a free API key at https://www.ai4chat.co/api and pass it as "
                "AI4Chat(api_key='...')."
            )

        if not response_text.strip():
            raise IOError("AI4Chat returned an empty response.")

        return response_text.replace("\\n", "\n")


class Chat(BaseChat):
    def __init__(self, client: "AI4Chat"):
        self.completions = Completions(client)


class AI4Chat(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for AI4Chat's API with support for 270+ AI models.

    Requests are sent to AI4Chat's official OpenAI-compatible endpoint, which requires
    a free API key from https://www.ai4chat.co/api

    Usage:
        client = AI4Chat(api_key="your-key")
        response = client.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)

        # List available models
        print(client.models.list())
    """

    required_auth = True
    AVAILABLE_MODELS = list(MODELS.keys())
    default_model = "gpt-5.2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None,
        country: str = "Asia",
        user_id: Optional[str] = None,
        proxies: Optional[Dict[str, str]] = None,
        model: str = default_model,
        timeout: int = 60,
    ):
        """
        Initialize the AI4Chat client.

        Args:
            api_key: AI4Chat API key from https://www.ai4chat.co/api. Optional, but
                required for the official endpoint. Without it the legacy
                unauthenticated gateway is attempted and raises if it is unavailable.
            system_prompt: Prepended to the conversation when the caller sends no
                system message. Left unset by default so messages are forwarded as-is.
            country: Country parameter for the legacy gateway only
            user_id: User ID for the legacy gateway only (random per instance by default)
            proxies: Proxy configuration
            model: Default model to use (default: "gpt-5.2")
            timeout: Request timeout in seconds
        """
        super().__init__(proxies=proxies)
        self.timeout = timeout
        self.system_prompt = system_prompt
        self.api_key = api_key
        self.country = country
        # The legacy gateway tracked anonymous users by id; a stale hard-coded id was
        # one reason it started rejecting requests, so default to a fresh one.
        self.user_id = user_id or f"user{uuid.uuid4().hex[:10]}"

        # Validate and set default model
        if model not in MODELS:
            raise ValueError(
                f"Invalid model '{model}'. Available models: {list(MODELS.keys())[:10]}... (and {len(MODELS) - 10} more)"
            )
        self.model = model
        self.model_name = MODELS[model]

        # Official OpenAI-compatible endpoint (POST, Bearer auth)
        self.api_endpoint = "https://www.ai4chat.co/api/v1/chat/completions"
        # Legacy unauthenticated gateway, kept as a no-API-key fallback
        self.legacy_endpoint = (
            "https://yw85opafq6.execute-api.us-east-1.amazonaws.com/default/boss_mode_15aug"
        )

        # Set headers
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://www.ai4chat.co",
            "Referer": "https://www.ai4chat.co/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": agent.random(),
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

        # Update session headers
        self.session.headers.update(self.headers)

        # Initialize chat interface
        self.chat = Chat(self)

    def resolve_model_name(self, model: Optional[str] = None) -> str:
        """Map an llm4free model key to the display name AI4Chat's API expects."""
        model_key = model or self.model
        if model_key not in MODELS:
            raise ValueError(
                f"Invalid model '{model_key}'. Available models: {list(MODELS.keys())[:10]}... (and {len(MODELS) - 10} more)"
            )
        return MODELS[model_key]

    def prepare_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize messages for the OpenAI-compatible endpoint.

        Only role/content pairs are forwarded. A configured ``system_prompt`` is
        prepended when the caller sent no system message; by default messages are
        passed through unchanged.
        """
        normalized: List[Dict[str, Any]] = []
        has_system = False

        for message in messages or []:
            role = str(message.get("role") or "user").strip().lower() or "user"
            content = message.get("content")
            if content is None:
                content = ""
            elif not isinstance(content, str):
                content = str(content)
            if not content.strip():
                continue
            if role == "system":
                has_system = True
            normalized.append({"role": role, "content": content})

        if not normalized:
            raise ValueError("No valid prompt could be generated from messages")

        if not has_system and self.system_prompt:
            normalized.insert(0, {"role": "system", "content": self.system_prompt})

        return normalized

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """Get available model ids (AI4Chat exposes no public model listing endpoint)."""
        return cls.AVAILABLE_MODELS

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    import os

    from rich import print

    # List available models
    print("[bold cyan]Available Models:[/bold cyan]")
    for model_key, model_name in list(MODELS.items())[:10]:
        print(f"  - {model_key}: {model_name}")
    print(f"  ... and {len(MODELS) - 10} more models\n")

    # Free API key from https://www.ai4chat.co/api
    client = AI4Chat(api_key=os.environ.get("AI4CHAT_API_KEY"), model="gpt-5.2")

    if not client.api_key:
        print(
            "[bold yellow]Set AI4CHAT_API_KEY (free key from "
            "https://www.ai4chat.co/api) to run this demo.[/bold yellow]\n"
        )

    print("[bold green]NON-STREAMING RESPONSE (GPT 5.2):[/bold green]")
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "user", "content": "how many r in strawberryr?"},
        ],
    )
    print(response)

    print("\n[bold green]STREAMING RESPONSE (Claude Haiku 4.5):[/bold green]")
    stream_response = client.chat.completions.create(
        model="claude-haiku-4.5",
        messages=[
            {"role": "user", "content": "Tell me a short joke."},
        ],
        stream=True,
    )
    for chunk in stream_response:
        if isinstance(chunk, ChatCompletionChunk):
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta is not None and delta.content is not None:
                    print(delta.content, end="", flush=True)
    print("\n")
