"""AskMe AI provider (https://www.ask-me-ai.app).

Wraps the site's public chat front-end behind the OpenAI-compatible interface.

Request flow:
1. Every request carries an ``X-App-Token`` signed from the device id, the
   current 5-minute time bucket and the server clock.
2. ``POST /api/chat/stream`` answers with an SSE stream of JSON events
   (``response_created``, ``text``, ``done``, ``error``, ...).
3. The ``responseId`` from ``response_created``/``done`` is chained into the
   next request via ``previousResponseId`` so the backend keeps the context.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple

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
)

BASE_URL = "https://www.ask-me-ai.app"
APP_VERSION = "4.0.6+"
AVAILABLE_MODELS = ["askme"]

_BUCKET_MS = 300_000
_SIGN_MASK = 0xFFFFFFFF

# Constants baked into the web client's token signer.
_KEY_SHIFT = [1, 2, 2, 4, 8, 32, 5, 160]
_KEY_MIX = [123, 47, 145, 68, 232, 60, 165, 105]
_KEY_XOR = [210, 23, 142, 243, 86, 186, 13, 193]
_KEY_SUFFIXES = ["Zy3", "A7x", "Lp2", "Hj4", "K9m", "Qw8", "Xs1", "Nv7"]

_ROLE_LABELS = {"system": "System", "assistant": "Assistant", "user": "User", "tool": "Tool"}


def _content_to_text(content: Any) -> str:
    """Normalize OpenAI message content (str or list of parts) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return "" if content is None else str(content)


def _signing_key(bucket: int) -> bytes:
    seed = bytearray()
    for slot, suffix in enumerate(_KEY_SUFFIXES):
        factor = ((bucket >> (slot * 4)) & 15) + 1
        for char in suffix:
            seed.append(((ord(char) ^ 90) * factor) & 0xFF)
    digest = hashlib.sha256(bytes(seed) + bucket.to_bytes(8, "big")).digest()

    key = bytearray()
    for index, byte in enumerate(digest):
        lane = index % 8
        base, other = _KEY_SHIFT[lane], _KEY_MIX[lane]
        key.append(((((byte ^ base) + (base & other) - (byte | other)) & 0xFF) ^ _KEY_XOR[lane]) & 0xFF)
    return bytes(key)


def _checksum(data: bytes, bucket: int) -> int:
    acc = (1095977805 ^ (bucket & 0xFFFF)) & _SIGN_MASK
    for index, byte in enumerate(data):
        factor = ((bucket >> ((index * 3) % 32)) & 7) + 1
        acc = (((acc << 5) & _SIGN_MASK) + acc * factor + byte) & _SIGN_MASK
    return (acc ^ 1161906481 ^ ((bucket >> 16) & 0xFFFF)) & _SIGN_MASK


def _scramble(data: bytes, seed: int) -> bytes:
    out = bytearray()
    state = seed
    for index, byte in enumerate(data):
        lane = index % 4
        if lane == 0:
            value = byte ^ ((index * 7 + 13) & 0xFF) ^ (state & 0xFF)
        elif lane == 1:
            value = byte + ((index * 11 + 17) & 0xFF) - (state & 63)
        elif lane == 2:
            value = byte ^ ((index * 13 + 23) & 0xFF) ^ ((state >> 2) & 15)
        else:
            value = byte - ((index * 17 + 31) & 127) + ((state >> 4) & 31)
        out.append(value & 0xFF)
        state = ((state * 1103515245 + 12345) & _SIGN_MASK) >> 16 & 32767
    return bytes(out)


def _noise(now_ms: int) -> bytes:
    minute_of_day = (now_ms // 3_600_000 % 24) * 60 + (now_ms // 60_000 % 60)
    mask = (minute_of_day ^ 43981) & 0xFF
    out = bytearray(secrets.token_bytes(16))
    for index in range(0, 16, 4):
        out[index] ^= mask
    return bytes(out)


def sign_token(device_id: str, now_ms: Optional[int] = None) -> str:
    """Build the ``X-App-Token`` value for a device id."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    bucket = now_ms // _BUCKET_MS
    noise = _noise(now_ms)

    encoded = device_id.encode("utf-8")
    body = bytearray(bucket.to_bytes(8, "big"))
    body.append(len(encoded) & 0xFF)
    body.extend(encoded)
    body.extend(noise)
    body.extend(_checksum(bytes(body), bucket).to_bytes(4, "big"))

    key = _signing_key(bucket)
    mac = hmac.new(key + b"\x00" * (64 - len(key)), bytes(body), hashlib.sha256).digest()

    high = (bucket & 0xFFFF) ^ noise[0]
    low = ((bucket >> 16) & 0xFFFF) ^ (noise[0] >> 8)
    tail = hashlib.sha256(mac + high.to_bytes(2, "big") + low.to_bytes(2, "big")).digest()

    signature = bytes(mac[i] if i % 2 == 0 else tail[i] for i in range(32))
    return base64.urlsafe_b64encode(_scramble(bytes(body) + signature, (bucket * 31337) & 0x7FFFFFFF)).decode()


def _iter_events(response: Any) -> Generator[Dict[str, Any], None, None]:
    """Yield JSON payloads from an SSE response."""
    buffer = ""
    for raw in response.iter_lines():
        if raw is None:
            continue
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        line = line.lstrip("\ufeff")
        if not line.strip():
            if buffer:
                try:
                    yield json.loads(buffer)
                except json.JSONDecodeError:
                    pass
                buffer = ""
            continue
        if line.startswith("data:"):
            data = line[5:]
            if data.startswith(" "):
                data = data[1:]
            buffer = f"{buffer}\n{data}" if buffer else data
    if buffer:
        try:
            yield json.loads(buffer)
        except json.JSONDecodeError:
            pass


def _utc_offset_minutes() -> int:
    offset = datetime.now().astimezone().utcoffset()
    return int(offset.total_seconds() // 60) if offset else 0


def _error_for(event: Dict[str, Any]) -> IOError:
    message = event.get("message") or event.get("code") or "unknown error"
    return IOError(f"AskMe AI error: {message}")


class Completions(BaseCompletions):
    def __init__(self, client: "AskMeAI"):
        self._client = client

    def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        timeout: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        model = model or self._client.default_model
        timeout = timeout or self._client.timeout
        normalized = self._client._normalize(messages or [])
        message, previous = self._client._prepare(normalized)

        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        if stream:
            return self._stream(request_id, created_time, model, normalized, message, previous, timeout)

        content = ""
        response_id: Optional[str] = None
        response = self._client._open_stream(message, previous, timeout)
        try:
            for event in _iter_events(response):
                kind = event.get("type")
                if kind == "text":
                    content += str(event.get("content") or "")
                elif kind == "text_reset":
                    content = ""
                elif kind == "error":
                    raise _error_for(event)
                elif kind in ("response_created", "done") and event.get("responseId"):
                    response_id = str(event["responseId"])
        finally:
            response.close()

        self._client._remember(normalized, content, response_id)

        prompt_tokens = count_tokens(format_prompt(messages or []))
        completion_tokens = count_tokens(content)
        return ChatCompletion(
            id=request_id,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(role="assistant", content=content),
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

    def _stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        normalized: List[Dict[str, str]],
        message: str,
        previous: Optional[str],
        timeout: int,
    ) -> Generator[ChatCompletionChunk, None, None]:
        response = self._client._open_stream(message, previous, timeout)
        parts: List[str] = []
        response_id: Optional[str] = None
        try:
            for event in _iter_events(response):
                kind = event.get("type")
                if kind == "text":
                    text = event.get("content")
                    if text:
                        parts.append(str(text))
                        yield ChatCompletionChunk(
                            id=request_id,
                            choices=[
                                Choice(
                                    index=0,
                                    delta=ChoiceDelta(content=str(text), role="assistant"),
                                    finish_reason=None,
                                )
                            ],
                            created=created_time,
                            model=model,
                        )
                elif kind == "error":
                    raise _error_for(event)
                elif kind in ("response_created", "done") and event.get("responseId"):
                    response_id = str(event["responseId"])
        finally:
            response.close()

        self._client._remember(normalized, "".join(parts), response_id)

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


class Chat(BaseChat):
    def __init__(self, client: "AskMeAI"):
        self.completions = Completions(client)


class AskMeAI(OpenAICompatibleProvider):
    required_auth = False
    AVAILABLE_MODELS = AVAILABLE_MODELS
    default_model = "askme"

    def __init__(
        self,
        timeout: int = 300,
        device_id: Optional[str] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ):
        super().__init__(proxies=proxies, **kwargs)
        self.timeout = timeout
        self.device_id = device_id or str(uuid.uuid4())
        self.user_agent = LitAgent().random()
        self.last_response_id: Optional[str] = None
        self._time_offset_ms = 0
        self._last_messages: List[Dict[str, str]] = []
        self.chat = Chat(self)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        return cls.AVAILABLE_MODELS

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-App-Token": sign_token(self.device_id, int(time.time() * 1000) + self._time_offset_ms),
            "X-App-Version": APP_VERSION,
            "X-AskMe-Visualization-Protocol": "1",
            "X-AskMe-Streaming-Protocol": "1",
            "X-AskMe-Music-Protocol": "1",
            "X-AskMe-YouTube-Protocol": "1",
            "X-AskMe-Jobs-Protocol": "1",
            "X-AskMe-Video-Protocol": "1",
            "User-Agent": self.user_agent,
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/",
        }

    def _open_stream(self, message: str, previous: Optional[str], timeout: int) -> Any:
        payload: Dict[str, Any] = {
            "message": message,
            "deviceId": self.device_id,
            "utcOffsetMinutes": _utc_offset_minutes(),
        }
        if previous:
            payload["previousResponseId"] = previous

        body = json.dumps(payload)

        for attempt in range(2):
            response = self.session.post(
                f"{BASE_URL}/api/chat/stream",
                data=body,
                headers=self._headers(),
                stream=True,
                timeout=(30, timeout),
                impersonate="chrome110",
            )
            if response.status_code == 401 and attempt == 0:
                self._sync_clock(response)
                response.close()
                continue
            if response.status_code == 429:
                response.close()
                raise IOError("AskMe AI rate limit reached; try again later")
            if response.status_code >= 400:
                detail = response.text[:300]
                response.close()
                raise IOError(f"AskMe AI request failed ({response.status_code}): {detail}")
            return response

        raise IOError("AskMe AI rejected the request token")

    def _sync_clock(self, response: Any) -> None:
        raw = response.headers.get("X-Server-Time")
        try:
            server_ms = int(raw) if raw is not None else int(response.json()["serverTime"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return
        self._time_offset_ms = server_ms - int(time.time() * 1000)

    @staticmethod
    def _normalize(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        for message in messages:
            text = _content_to_text(message.get("content"))
            if not text:
                continue
            role = message.get("role", "user")
            normalized.append({"role": role, "content": text})
        return normalized

    def _prepare(self, normalized: List[Dict[str, str]]) -> Tuple[str, Optional[str]]:
        previous = self._last_messages
        if (
            previous
            and self.last_response_id
            and len(normalized) > len(previous)
            and normalized[: len(previous)] == previous
        ):
            return self._flatten(normalized[len(previous):]), self.last_response_id
        return self._flatten(normalized), None

    @staticmethod
    def _flatten(messages: List[Dict[str, str]]) -> str:
        if not messages:
            return ""
        if len(messages) == 1 and messages[0]["role"] == "user":
            return messages[0]["content"]
        return "\n\n".join(
            f"{_ROLE_LABELS.get(message['role'], message['role'].title())}: {message['content']}"
            for message in messages
        )

    def _remember(
        self,
        normalized: List[Dict[str, str]],
        reply: str,
        response_id: Optional[str],
    ) -> None:
        self._last_messages = normalized + [{"role": "assistant", "content": reply}]
        self.last_response_id = response_id

if __name__ == "__main__":
    import sys

    provider = AskMeAI()
    messages = [{"role": "user", "content": "Hello, how are you?"}]
    try:
        completion = provider.chat.completions.create(model=provider.default_model, messages=messages)
        message = completion.choices[0].message
        print(message.content if message else "")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)