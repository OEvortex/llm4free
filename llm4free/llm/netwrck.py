"""Netwrck provider (guest endpoint only)."""
from aiohttp.log import client_logger

import json
import re
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi import CurlError, requests

from llm4free.litagent import LitAgent
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
    format_prompt,
    get_system_prompt,
)

BASE_URL = "https://netwrck.com"
GUEST_CHAT_ENDPOINT = f"{BASE_URL}/api/chatpred_or"
GUEST_FALLBACK_ENDPOINT = f"{BASE_URL}/api/chatpred"

FREE_MODELS = [
    "inclusionai/ling-3.0-flash",
    "thedrummer/skyfall-36b-v2",
    "gryphe/mythomax-l2-13b",
]

AVAILABLE_MODELS = list(FREE_MODELS)

DEFAULT_MODEL = "thedrummer/skyfall-36b-v2"


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for entry in value:
            text = _extract_text(entry)
            if text:
                return text
        return ""
    if isinstance(value, dict):
        for key in ("generated_text", "text", "content", "message", "response", "data"):
            if key in value:
                text = _extract_text(value[key])
                if text:
                    return text
        return ""
    return str(value)


def _error_from_response(response: Any) -> str:
    raw = response.text or ""
    try:
        data = response.json()
    except Exception:
        return raw.strip() or f"HTTP {response.status_code}"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
        code = data.get("code")
        message = data.get("message") or data.get("detail")
        if code or message:
            return f"{code}: {message}" if code and message else str(code or message)
    return str(data)


def _chunk_text(text: str, size: int = 24) -> Generator[str, None, None]:
    if not text:
        return
    for match in re.finditer(r"\S+\s*", text):
        piece = match.group(0)
        for i in range(0, len(piece), size):
            yield piece[i : i + size]


class Completions(BaseCompletions):
    def __init__(self, client: "Netwrck"):
        self._client = client

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
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())
        resolved_model = self._client.convert_model_name(model)

        if resolved_model not in FREE_MODELS:
            raise ValueError(
                f"Netwrck model '{resolved_model}' is not available on guest endpoint. "
                f"Free models: {', '.join(FREE_MODELS)}"
            )

        guest_payload = self._build_guest_payload(
            resolved_model, messages, max_tokens, temperature, top_p
        )
        if stream:
            return self._create_guest_stream(
                request_id, created_time, resolved_model, guest_payload, timeout, proxies
            )
        return self._create_guest_non_stream(
            request_id, created_time, resolved_model, guest_payload, timeout, proxies
        )

    def _request_kwargs(
        self,
        payload: Dict[str, Any],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
        *,
        stream: bool,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "json": payload,
            "timeout": timeout or self._client.timeout,
            "headers": {
                "Accept": "text/event-stream" if stream else "application/json",
            },
        }
        if stream:
            kwargs["stream"] = True
        if proxies:
            kwargs["proxies"] = proxies
        return kwargs

    def _build_guest_payload(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "query": format_prompt(messages, add_special_tokens=True, do_continue=True),
            "context": get_system_prompt(messages) or self._client.system_prompt,
            "examples": [],
            "greeting": self._client.greeting,
            "model_name": model,
            "username": "User",
            "character": "",
            "web_tools": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        return payload

    def _post_guest(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
    ) -> Any:
        response = self._client.session.post(
            endpoint,
            **self._request_kwargs(payload, timeout, proxies, stream=False),
        )

        if response.status_code in (401, 402, 429):
            message = _error_from_response(response)
            if endpoint == GUEST_CHAT_ENDPOINT and response.status_code in (402, 429):
                fallback_payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"max_tokens", "temperature", "top_p"}
                }
                return self._post_guest(GUEST_FALLBACK_ENDPOINT, fallback_payload, timeout, proxies)
            raise IOError(f"Netwrck guest chat failed ({response.status_code}): {message}")

        response.raise_for_status()
        raw = response.text.strip()
        if not raw:
            raise IOError("Netwrck returned an empty response")
        if _looks_like_html(raw):
            raise IOError("Netwrck returned an HTML page instead of a chat response")

        try:
            return response.json()
        except Exception:
            return self._client.format_text(raw)

    def _create_guest_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
    ) -> ChatCompletion:
        try:
            data = self._post_guest(GUEST_CHAT_ENDPOINT, payload, timeout, proxies)
            text = _extract_text(data)
            if not text:
                raise IOError("Netwrck returned an empty chat response")
            text = self._client.format_text(text)

            prompt_tokens = count_tokens(payload.get("query", ""))
            completion_tokens = count_tokens(text)
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            message = ChatCompletionMessage(role="assistant", content=text)
            choice = Choice(index=0, message=message, finish_reason="stop")
            return ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )
        except Exception as e:
            raise IOError(f"Netwrck request failed: {e}") from e

    def _create_guest_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
    ) -> Generator[ChatCompletionChunk, None, None]:
        try:
            data = self._post_guest(GUEST_CHAT_ENDPOINT, payload, timeout, proxies)
            text = self._client.format_text(_extract_text(data))
            if not text:
                raise IOError("Netwrck returned an empty chat response")

            role_sent = False
            for piece in _chunk_text(text):
                delta = ChoiceDelta(content=piece, role=None if role_sent else "assistant")
                role_sent = True
                yield ChatCompletionChunk(
                    id=request_id,
                    choices=[Choice(index=0, delta=delta, finish_reason=None)],
                    created=created_time,
                    model=model,
                )

            yield ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=None),
                        finish_reason="stop",
                    )
                ],
                created=created_time,
                model=model,
            )
        except Exception as e:
            raise IOError(f"Netwrck streaming request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "Netwrck"):
        self.completions = Completions(client)


class Netwrck(OpenAICompatibleProvider):
    required_auth = False

    AVAILABLE_MODELS = AVAILABLE_MODELS
    FREE_MODELS = FREE_MODELS

    greeting = "Hello! I'm a helpful assistant. How can I help you today?"

    def __init__(
        self,
        timeout: int = 30,
        temperature: float = 0.7,
        top_p: float = 0.8,
        system_prompt: str = "You are a helpful assistant.",
        proxies: Optional[Dict[str, str]] = None,
        browser: str = "chrome",
    ):
        super().__init__(api_key=None, proxies=proxies)
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p
        self.system_prompt = system_prompt
        self.proxies = proxies or {}

        agent = LitAgent()
        self.headers = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": BASE_URL,
            "referer": f"{BASE_URL}/",
            "user-agent": agent.random(),
        }

        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update(self.headers)
        if self.proxies:
            self.session.proxies.update(cast(Any, self.proxies))

        self.chat = Chat(self)

    def format_text(self, text: str) -> str:
        if not text:
            return ""
        try:
            text = text.replace("\\\\", "\\")
            text = text.replace("\\n", "\n")
            text = text.replace("\\r", "\r")
            text = text.replace("\\t", "\t")
            text = text.replace('\\"', '"')
            text = text.replace("\\'", "'")
            try:
                return cast(str, json.loads(f'"{text}"'))
            except json.JSONDecodeError:
                return text
        except Exception:
            return text

    def convert_model_name(self, model: str) -> str:
        if not model or model.lower() in {"default", "netwrck"}:
            return DEFAULT_MODEL

        if model in self.AVAILABLE_MODELS:
            return model

        lowered = model.lower()
        for available_model in self.AVAILABLE_MODELS:
            if lowered == available_model.lower():
                return available_model

        for available_model in self.AVAILABLE_MODELS:
            short_name = available_model.split("/", 1)[-1].lower()
            if lowered in short_name or short_name in lowered:
                return available_model

        return DEFAULT_MODEL

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    client = Netwrck()
    response = client.chat.completions.create(
        model="thedrummer/skyfall-36b-v2",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        stream=False,
    )
    msg = response.choices[0].message
    print(msg.content if msg is not None else None)
