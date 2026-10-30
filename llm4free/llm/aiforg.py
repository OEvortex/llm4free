"""HTTP-backed AIForg Playground provider (https://ai-forg.com/playground).

Posts to the Supabase Edge Function and streams SSE responses.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

from llm4free.browser_requests._http import compat as requests

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

PLAYGROUND_URL = "https://ai-forg.com/playground"
API_ENDPOINT = "https://pykusrxcysyararvmwdr.supabase.co/functions/v1/ai-playground"

DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_TIMEOUT = 180

MODELS = {
    "gemini-3-flash-preview": "gemini-3-flash-preview",

}
AVAILABLE_MODELS = list(MODELS.keys())

PROMPTIONAL_KEYWORDS = ["AIFORGE offers full courses"]


class _SSEParser:
    @staticmethod
    def extract(data: Dict[str, Any]) -> str:
        if "choices" in data:
            choices = data["choices"]
            if choices and isinstance(choices, list):
                c = choices[0]
                if isinstance(c, dict):
                    delta = c.get("delta")
                    if isinstance(delta, dict):
                        return delta.get("content") or ""
                    msg = c.get("message")
                    if isinstance(msg, dict):
                        return msg.get("content") or ""
                    return c.get("text") or ""
        if "response" in data and isinstance(data["response"], str):
            return data["response"]
        if "text" in data and isinstance(data["text"], str):
            return data["text"]
        return data.get("content") or ""


class Completions(BaseCompletions):
    def __init__(self, client: "AIForg"):
        self._client = client
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "*/*",
                "Accept-Language": "en-GB,en;q=0.9",
                "Content-Type": "application/json",
                "Origin": "https://ai-forg.com",
                "Referer": "https://ai-forg.com/playground",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            }
        )

    def create(
        self,
        *,
        model: str = DEFAULT_MODEL,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        proxy: Any = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        if not messages:
            raise ValueError("AIForg requires at least one message")

        model = model or DEFAULT_MODEL
        prompt = format_prompt(messages, add_special_tokens=True)
        effective_timeout = timeout or self._client.timeout

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        request_kwargs: Dict[str, Any] = {
            "json": {"prompt": prompt},
            "timeout": effective_timeout,
            "stream": stream,
        }
        if proxy or proxies:
            request_kwargs["proxies"] = proxy or proxies

        try:
            resp = self.session.post(API_ENDPOINT, **request_kwargs)
        except Exception as e:
            raise IOError(f"AIForg request failed: {e}") from e

        if resp.status_code != 200:
            try:
                text = resp.text[:400]
            except Exception:
                text = ""
            raise IOError(f"AIForg request failed: http {resp.status_code} {text}")

        if stream:
            return self._create_stream(resp, request_id, created_time, model)
        return self._create_non_stream(resp, request_id, created_time, model, messages)

    def _create_stream(
        self,
        resp,
        request_id: str,
        created_time: int,
        model: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        full_content = []
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    content = _SSEParser.extract(data)
                    if content:
                        full_content.append(content)
                else:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = _SSEParser.extract(data)
                    if content:
                        full_content.append(content)
        except Exception as e:
            raise IOError(f"AIForg stream failed: {e}") from e

        full_text = "".join(full_content)
        full_text = full_text.replace("\n\n***\n\n", "\n\n").replace("\n***\n", "\n\n").rstrip()
        # Remove promotional block if present (second mention of AIFORGE with course offer)
        if PROMPTIONAL_KEYWORDS[0] in full_text:
            # Check if it's not just "AIFORGE Playground" mention
            idx = full_text.find(PROMPTIONAL_KEYWORDS[0])
            # Make sure it's after first occurrence
            first_aiforge = full_text.find("AIFORGE")
            if first_aiforge >= 0 and idx > first_aiforge + 20:
                cut_start = full_text.rfind('\n\n', 0, idx)
                if cut_start == -1:
                    cut_start = full_text.rfind('\n', 0, idx)
                if cut_start == -1:
                    cut_start = full_text.rfind('*', 0, idx)
                if cut_start >= 0:
                    full_text = full_text[:cut_start].rstrip()
                else:
                    full_text = full_text[:idx].rstrip()

        if full_text:
            yield ChatCompletionChunk(
                id=request_id,
                choices=[Choice(index=0, delta=ChoiceDelta(content=full_text, role="assistant"), finish_reason=None)],
                created=created_time,
                model=model,
            )

        final_choice = Choice(index=0, delta=ChoiceDelta(content=None, role=None), finish_reason="stop")
        yield ChatCompletionChunk(
            id=request_id,
            choices=[final_choice],
            created=created_time,
            model=model,
        )

    def _create_non_stream(
        self,
        resp,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
    ) -> ChatCompletion:
        full_content = []
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    content = _SSEParser.extract(data)
                    if content:
                        full_content.append(content)
                else:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = _SSEParser.extract(data)
                    if content:
                        full_content.append(content)
        except Exception as e:
            raise IOError(f"AIForg request failed: {e}") from e

        full_text = "".join(full_content)
        full_text = full_text.replace("\n\n***\n\n", "\n\n").replace("\n***\n", "\n\n").rstrip()
        count = full_text.count("AIFORGE")
        if count > 1:
            first = full_text.find("AIFORGE")
            second = full_text.find("AIFORGE", first + 1)
            if second >= 0:
                cut_start = full_text.rfind('\n\n', 0, second)
                if cut_start == -1:
                    cut_start = full_text.rfind('\n', 0, second)
                if cut_start == -1:
                    cut_start = full_text.rfind('*', 0, second)
                if cut_start >= 0:
                    full_text = full_text[:cut_start].rstrip()
                else:
                    full_text = full_text[:second].rstrip()

        message = ChatCompletionMessage(role="assistant", content=full_text)
        choice = Choice(index=0, message=message, finish_reason="stop")
        prompt_tokens = count_tokens(format_prompt(messages))
        completion_tokens = count_tokens(full_text)
        usage = CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return ChatCompletion(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "AIForg"):
        self.completions = Completions(client)


class AIForg(OpenAICompatibleProvider):
    """HTTP-backed AIForg Playground provider (no API key)."""

    required_auth = False
    supports_stream = True
    supports_system_message = True
    default_model = DEFAULT_MODEL
    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        proxies: Optional[Dict[str, str]] = None,
        proxy: Any = None,
    ):
        super().__init__(proxies=proxies)
        self.timeout = timeout
        self._proxy = proxy if proxy is not None else proxies
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        return AVAILABLE_MODELS


if __name__ == "__main__":
    from rich import print

    client = AIForg()
    print(f"Available models: {client.models.list()}")
    response = client.chat.completions.create(
        model="gemini-3-flash-preview",
        messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
        stream=False,
    )
    if isinstance(response, ChatCompletion):
        msg = response.choices[0].message
        if msg and msg.content:
            print(msg.content)
