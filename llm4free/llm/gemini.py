import json
import random
import re
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi import requests

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

BOLD = "\033[1m"
RED = "\033[91m"
RESET = "\033[0m"

GEMINI_API = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
DEFAULT_BL = "boq_assistant-bard-web-server_20240625.13_p0"

# Reverse-engineered mode mapping for anonymous Gemini requests.
MODEL_MODE = {
    "gemini-3.6-flash": 1,
    "gemini-3.5-flash": 1,
    "gemini-2.5-flash": 1,
    "gemini-2.0-flash": 1,
    "gemini-1.5-flash": 1,
    "gemini-3.1-pro": 3,
    "gemini-2.5-pro": 3,
    "gemini-2.0-pro": 3,
    "gemini-1.5-pro": 3,
    "gemini-3.5-flash-lite": 6,
}

MODEL_ALIASES = {
    "gemini-2.0": "gemini-3.6-flash",
    "gemini-2.0-flash": "gemini-3.6-flash",
    "gemini-2.0-flash-thinking": "gemini-3.6-flash",
    "gemini-2.0-flash-thinking-with-apps": "gemini-3.6-flash",
    "gemini-2.5-flash": "gemini-3.6-flash",
    "gemini-2.5-pro": "gemini-3.1-pro",
    "gemini-3.1-flash-lite": "gemini-3.5-flash-lite",
    "gemini-3.5-flash": "gemini-3.6-flash",
    "gemini-3.5-flash-thinking": "gemini-3.6-flash",
    "gemini-3.6-flash-thinking": "gemini-3.6-flash",
    "gemini-auto": "gemini-3.6-flash",
    "gemini-3.5-flash-thinking-lite": "gemini-3.5-flash-lite",
    "gemini-3.5-flash-lite-thinking": "gemini-3.5-flash-lite",
    "gemini-flash-lite": "gemini-3.5-flash-lite",
}


def _resolve_model(name: str) -> str:
    resolved = MODEL_ALIASES.get(name, name)
    if resolved not in MODEL_MODE:
        raise ValueError(
            f"Unknown Gemini model: {name!r}. Available models: {', '.join(MODEL_MODE)}"
        )
    return resolved


def _convert_messages(messages: List[Dict[str, str]]) -> str:
    parts: List[str] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if not content:
            continue
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
        else:
            parts.append(f"User: {content}")
    return "\n".join(parts)


def _iter_wrb_payloads(value: Any) -> Generator[str, None, None]:
    if not isinstance(value, list):
        return
    for item in value:
        if not isinstance(item, list) or not item:
            continue
        first = item[0]
        if isinstance(first, str) and first.startswith("wrb.fr"):
            payload = first[len("wrb.fr"):]
            if payload.startswith(","):
                payload = payload[1:]
            if payload:
                yield payload
                return
            if len(item) > 2 and isinstance(item[2], str):
                yield item[2]
                return
        yield from _iter_wrb_payloads(item)


def _extract_response_content(response_part: list) -> Optional[str]:
    try:
        parts = response_part[4]
    except (IndexError, TypeError):
        return None
    if not isinstance(parts, list):
        return None
    snapshots: List[str] = []
    for part in parts:
        if not isinstance(part, list) or len(part) <= 1:
            continue
        values = part[1]
        if isinstance(values, str):
            snapshots.append(values)
        elif isinstance(values, list):
            snapshots.extend(value for value in values if isinstance(value, str))
    return snapshots[-1] if snapshots else None


def _extract_response_part(value: Any) -> Optional[list]:
    response_parts: List[list] = []
    for payload in _iter_wrb_payloads(value):
        try:
            response_part = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if isinstance(response_part, list):
            response_parts.append(response_part)
    for response_part in reversed(response_parts):
        if _extract_response_content(response_part) is not None:
            return response_part
    return None


class Completions(BaseCompletions):
    def __init__(self, client: "Gemini"):
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
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        resolved = _resolve_model(model)
        prompt = _convert_messages(messages)

        request_uuid = str(uuid.uuid4()).upper()
        request = [None] * 97
        request[0] = [prompt, 0, None, [], None, None, 0]
        request[1] = ["en"]
        request[2] = ["", "", "", None, None, None, None, None, None, ""]
        request[6] = [1]
        request[7] = 1
        request[10] = 1
        request[11] = 0
        request[17] = [[0]]
        request[18] = 0
        request[27] = 1
        request[30] = [4]
        request[41] = [1]
        request[53] = 0
        request[59] = request_uuid
        request[61] = []
        request[68] = 2
        request[79] = MODEL_MODE[resolved]
        request[80] = 1
        request[91] = 0
        request[96] = 1

        payload = {
            "f.req": json.dumps(
                [None, json.dumps(request, ensure_ascii=False)], ensure_ascii=False
            ),
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Referer": "https://gemini.google.com/",
            "X-Same-Domain": "1",
        }

        session = self._client.session
        actual_timeout = timeout or self._client.timeout
        actual_proxies = cast(Any, proxies or getattr(self._client, "proxies", None))

        response = session.post(
            GEMINI_API,
            params={"bl": DEFAULT_BL, "_reqid": str(self._client._reqid), "rt": "c"},
            data=payload,
            headers=headers,
            timeout=actual_timeout,
            proxies=actual_proxies,
        )
        response.raise_for_status()

        if stream:
            return self._stream_response(response.text, resolved, model)
        return self._parse_response(response.text, resolved, model)

    def _stream_response(
        self,
        text: str,
        resolved_model: str,
        requested_model: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        full_text = ""
        finish_reason = "stop"

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(")]}'"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            response_part = _extract_response_part(payload)
            if response_part is None:
                continue
            content = _extract_response_content(response_part) or ""
            if not content:
                continue
            delta_text = content[len(full_text):]
            if delta_text:
                full_text = content
                delta = ChoiceDelta(content=delta_text)
                choice = Choice(index=0, delta=delta, finish_reason=None)
                yield ChatCompletionChunk(
                    id=request_id,
                    choices=[choice],
                    created=created_time,
                    model=requested_model,
                )

        delta = ChoiceDelta(content=None)
        choice = Choice(index=0, delta=delta, finish_reason=finish_reason)
        yield ChatCompletionChunk(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=requested_model,
        )

    def _parse_response(
        self,
        text: str,
        resolved_model: str,
        requested_model: str,
    ) -> ChatCompletion:
        response_part = None
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(")]}'"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            candidate = _extract_response_part(payload)
            if candidate is None:
                continue
            if _extract_response_content(candidate):
                response_part = candidate

        if response_part is None:
            raise IOError("Gemini returned no parseable response")

        content = _extract_response_content(response_part) or ""
        prompt_tokens = count_tokens(str(getattr(self._client, "_last_messages", "")))
        completion_tokens = count_tokens(content)
        usage = CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        message = ChatCompletionMessage(role="assistant", content=content)
        choice = Choice(index=0, message=message, finish_reason="stop")
        return ChatCompletion(
            id=f"chatcmpl-{uuid.uuid4()}",
            choices=[choice],
            created=int(time.time()),
            model=requested_model,
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "Gemini"):
        self.completions = Completions(client)


class Gemini(OpenAICompatibleProvider):
    required_auth = False
    AVAILABLE_MODELS = list(MODEL_MODE.keys())

    def __init__(self, timeout: int = 60, proxies: Optional[dict] = None):
        self.timeout = timeout
        self.proxies = proxies or {}
        self._reqid = int("".join([str(random.randint(0, 9)) for _ in range(7)]))
        self.session = requests.Session()
        self.session.timeout = (timeout, timeout * 3)
        if self.proxies:
            self.session.proxies.update(cast(Any, self.proxies))
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    def convert_model_name(self, model: str) -> str:
        try:
            return _resolve_model(model)
        except ValueError:
            print(f"{BOLD}Warning: Model '{model}' not found, using default 'gemini-3.6-flash'{RESET}")
            return "gemini-3.6-flash"

    def _build_request(self, prompt: str, resolved_model: str) -> dict:
        request_uuid = str(uuid.uuid4()).upper()
        request = [None] * 97
        request[0] = [prompt, 0, None, [], None, None, 0]
        request[1] = ["en"]
        request[2] = ["", "", "", None, None, None, None, None, None, ""]
        request[6] = [1]
        request[7] = 1
        request[10] = 1
        request[11] = 0
        request[17] = [[0]]
        request[18] = 0
        request[27] = 1
        request[30] = [4]
        request[41] = [1]
        request[53] = 0
        request[59] = request_uuid
        request[61] = []
        request[68] = 2
        request[79] = MODEL_MODE[resolved_model]
        request[80] = 1
        request[91] = 0
        request[96] = 1
        return {
            "f.req": json.dumps(
                [None, json.dumps(request, ensure_ascii=False)], ensure_ascii=False
            ),
        }


if __name__ == "__main__":
    print("-" * 80)
    print(f"{'Model':<50} {'Status':<10} {'Response'}")
    print("-" * 80)

    for model in Gemini.AVAILABLE_MODELS:
        try:
            client = Gemini(timeout=300)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say 'Hello' in one word"}],
                stream=False,
            )
            content = response.choices[0].message.content or ""
            print(f"{model:<50} {'OK':<10} {content[:30]}")
        except Exception as e:
            print(f"{model:<50} {'FAIL':<10} {type(e).__name__}: {e}")
