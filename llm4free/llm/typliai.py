"""
TypliAI OpenAI-compatible provider.
"""

import json
import random
import string
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast
from urllib.parse import unquote

from llm4free.browser_requests._http.compat import Session

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
    format_prompt,
)


def generate_random_id(length=16):
    """Generates a random alphanumeric string."""
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for i in range(length))


class Completions(BaseCompletions):
    def __init__(self, client: "TypliAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "openai/gpt-4o-mini",
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        """
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(request_id, created_time, model, messages, timeout, proxies)
        else:
            return self._create_non_stream(
                request_id, created_time, model, messages, timeout, proxies
            )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Implementation for streaming chat completions."""
        try:
            # Initialize session to get CSRF token
            self._client._init_session(proxies=proxies)

            chat_messages = []
            for m in messages:
                role = m.get("role", "user")
                content = str(m.get("content", ""))
                chat_messages.append(
                    {
                        "id": generate_random_id(),
                        "role": role,
                        "parts": [{"type": "text", "text": content}],
                    }
                )

            payload = {
                "modelId": model,
                "id": generate_random_id(),
                "messages": chat_messages,
                "trigger": "submit-message",
            }

            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
                impersonate="chrome120",
                proxies=proxies or self._client.proxies,
            )

            if not response.ok:
                raise IOError(f"TypliAI request failed: {response.status_code} - {response.text}")

            full_content = ""
            full_reasoning = ""
            completion_tokens = 0

            # Parse SSE stream manually
            for chunk in response.iter_content(chunk_size=None):
                if not chunk:
                    continue

                # Decode bytes to string if needed
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")

                # Parse SSE data lines
                for line in chunk.split("\n"):
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    # Parse JSON
                    try:
                        item = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    if not item or not isinstance(item, dict):
                        continue

                    item_type = item.get("type")

                    # Handle reasoning-delta (reasoning/thinking content)
                    if item_type == "reasoning-delta":
                        reasoning_delta = item.get("delta", "")
                        if reasoning_delta:
                            full_reasoning += reasoning_delta
                            delta = ChoiceDelta(
                                reasoning_content=reasoning_delta,
                                reasoning=full_reasoning,
                                role="assistant" if completion_tokens == 0 else None,
                            )
                            choice = Choice(index=0, delta=delta, finish_reason=None)
                            chunk = ChatCompletionChunk(
                                id=request_id, choices=[choice], created=created_time, model=model
                            )
                            yield chunk

                    # Handle text-delta (actual response content)
                    elif item_type == "text-delta":
                        text_delta = item.get("delta", "")
                        if text_delta:
                            full_content += text_delta
                            completion_tokens += 1
                            delta = ChoiceDelta(
                                content=text_delta,
                                reasoning_content=None,
                                reasoning=None,
                                role="assistant" if completion_tokens == 1 else None,
                            )
                            choice = Choice(index=0, delta=delta, finish_reason=None)
                            chunk = ChatCompletionChunk(
                                id=request_id, choices=[choice], created=created_time, model=model
                            )
                            yield chunk

            # Final chunk
            choice = Choice(
                index=0,
                delta=ChoiceDelta(
                    content=None,
                    reasoning_content=None,
                    reasoning=None,
                ),
                finish_reason="stop",
            )
            yield ChatCompletionChunk(
                id=request_id, choices=[choice], created=created_time, model=model
            )

        except Exception as e:
            raise IOError(f"TypliAI stream request failed: {e}") from e

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        """Implementation for non-streaming chat completions."""
        full_content = ""
        full_reasoning = ""

        for chunk in self._create_stream(request_id, created_time, model, messages, timeout, proxies):
            delta = chunk.choices[0].delta

            # Accumulate reasoning content
            if delta and delta.reasoning_content:
                full_reasoning += delta.reasoning_content

            # Accumulate text content
            if delta and delta.content:
                full_content += delta.content

        message = ChatCompletionMessage(
            role="assistant",
            content=full_content,
            reasoning_content=full_reasoning if full_reasoning else None,
            reasoning=full_reasoning if full_reasoning else None,
        )
        choice = Choice(index=0, message=message, finish_reason="stop")
        prompt_words = sum(len(str(m.get("content", "")).split()) for m in messages)
        completion_words = len(full_content.split())
        usage = CompletionUsage(
            prompt_tokens=prompt_words,
            completion_tokens=completion_words,
            total_tokens=prompt_words + completion_words,
        )

        return ChatCompletion(
            id=request_id, choices=[choice], created=created_time, model=model, usage=usage
        )


class Chat(BaseChat):
    def __init__(self, client: "TypliAI"):
        self.completions = Completions(client)


class TypliAI(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for TypliAI.
    """

    required_auth = False

    AVAILABLE_MODELS = [
        "openai/gpt-4o-mini",
        "openai/gpt-5.4-pro",
        "openai/gpt-5.6-terra-pro",
        "openai/gpt-5.5-pro",
        "openai/gpt-6-astra-pro",
        "openai/gpt-5.6-sol-pro",
        "openai/gpt-5.6-luna-pro",
        "google/gemini-3.1-flash-lite",
        "google/gemini-3.8-flash-pro",
        "google/gemini-3.1-pro",
        "anthropic/claude-fable-5-1-pro",
        "anthropic/claude-opus-5-5-pro",
        "anthropic/claude-opus-5-pro",
        "anthropic/claude-sonnet-5-5-pro",
        "anthropic/claude-sonnet-5-pro",
        "anthropic/claude-opus-4-8-pro",
        "anthropic/claude-sonnet-4-6-pro",
        "xai/grok-4.6-pro",
        "xai/grok-4.5-pro",
        "deepseek/deepseek-v4-1-flash-pro",
        "moonshotai/kimi-k3-pro",
        "alibaba/qwen-3.8-max-pro",
    ]

    def __init__(self, timeout: int = 60, proxies: Optional[dict] = None, browser: str = "chrome"):
        self.timeout = timeout
        self.proxies = proxies or {}
        # Use the new chat2 API endpoint
        self.api_endpoint = "https://typli.ai/api/chat2"

        self.session = Session()
        self.agent = LitAgent() if LitAgent else None
        user_agent = (
            self.agent.random()
            if self.agent
            else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
        )

        self.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9,en-IN;q=0.8",
            "content-type": "application/json",
            "dnt": "1",
            "origin": "https://typli.ai",
            "priority": "u=1, i",
            "referer": "https://typli.ai/ai-chat",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "user-agent": user_agent,
        }

        try:
            h = getattr(self.session, 'headers', None)
            if h is None:
                self.session.headers = dict(self.headers)
            else:
                try:
                    h.update(self.headers)
                    self.session.headers = h
                except Exception:
                    self.session.headers = dict(h)
                    self.session.headers.update(self.headers)
        except Exception:
            self.session.headers = dict(self.headers)
        if proxies:
            try:
                p = getattr(self.session, 'proxies', None)
                pd = dict(proxies)
                if p is None:
                    self.session.proxies = pd
                else:
                    try:
                        p.update(pd)
                        self.session.proxies = p
                    except Exception:
                        self.session.proxies = {**dict(p), **pd}
            except Exception:
                self.session.proxies = dict(proxies) if proxies else getattr(self.session, 'proxies', {})

        self.chat = Chat(self)

    def _init_session(self, proxies: Optional[Dict[str, str]] = None) -> None:
        """Initialize session by visiting the page to get CSRF token and cookies."""
        try:
            # Visit the page first to get CSRF token cookie
            self.session.get(
                "https://typli.ai/ai-chat",
                headers=self.headers,
                timeout=self.timeout,
                impersonate="chrome120",
                proxies=proxies or self.proxies,
            )
            # Extract CSRF token from cookies and decode it
            csrf_token = self.session.cookies.get("csrf-token")
            if csrf_token:
                # URL decode the CSRF token
                csrf_decoded = unquote(csrf_token)
                # Add x-csrf-token header with the decoded value
                self.headers["x-csrf-token"] = csrf_decoded
                # Update session headers
                self.session.headers.update(self.headers)
        except Exception:
            # Continue even if init fails - cookies might still work
            pass

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    client = TypliAI()
    print(f"Available models: {client.models.list()}")

    test_model = "deepseek/deepseek-v4-1-flash-pro"

    # Test non-streaming with reasoning model
    print("\n=== Testing Non-Streaming with Reasoning Model ===")
    response = client.chat.completions.create(
        model=test_model,
        messages=[{"role": "user", "content": "Hello! How are you?"}],
        stream=False,
    )
    if isinstance(response, ChatCompletion):
        msg = response.choices[0].message
        if msg and msg.content:
            print(f"Response: {msg.content}")
        if msg and msg.reasoning_content:
            print(f"Reasoning: {msg.reasoning_content[:100]}...")
    else:
        print(f"Response: {response}")

    # Test streaming with reasoning model
    print("\n=== Testing Streaming with Reasoning Model ===")
    stream_resp = client.chat.completions.create(
        model=test_model,
        messages=[{"role": "user", "content": "Hello!"}],
        stream=True,
    )
    if hasattr(stream_resp, "__iter__") and not isinstance(
        stream_resp, (str, bytes, ChatCompletion)
    ):
        for chunk in cast(Generator[ChatCompletionChunk, None, None], stream_resp):
            delta = chunk.choices[0].delta
            if delta:
                if delta.reasoning_content:
                    print(delta.reasoning_content, end="", flush=True)
                if delta.content:
                    print(delta.content, end="", flush=True)
    else:
        print(stream_resp)
    print()
