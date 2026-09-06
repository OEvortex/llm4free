import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi.requests import Session

from llm4free.litagent import LitAgent as agent
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

# Surfsense constants
AVAILABLE_MODELS = [
    "gpt-o4-mini-no-login",
    "gpt-5.4-mini-no-login",
]


class Completions(BaseCompletions):
    """Chat completions implementation for the Surfsense provider."""

    def __init__(self, client: "Surfsense"):
        """Initialize completions with a reference to the parent client.

        Args:
            client: The owning :class:`Surfsense` provider instance.
        """
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """Create a chat completion with the Surfsense API.

        Mimics ``openai.chat.completions.create``. Supports both streaming
        and non-streaming responses.

        Args:
            model: The model identifier to use for generation.
            messages: List of conversation message dictionaries.
            max_tokens: Maximum number of tokens to generate.
            stream: Whether to stream the response as chunks.
            temperature: Sampling temperature.
            top_p: Nucleus sampling parameter.
            timeout: Optional request timeout in seconds.
            proxies: Optional proxy configuration dict.
            **kwargs: Additional provider-specific parameters.

        Returns:
            A :class:`ChatCompletion` when streaming is disabled, or a
            generator of :class:`ChatCompletionChunk` objects when streaming.
        """
        # Resolve model aliases defensively.
        model = type(self._client).model_aliases.get(model, model)

        # Use format_prompt utility to format the conversation.
        conversation_prompt = format_prompt(
            messages, add_special_tokens=True, include_system=True
        )
        # Generate request ID and timestamp.
        request_id = str(uuid.uuid4())
        created_time = int(time.time())

        if stream:
            return self._create_streaming(
                request_id,
                created_time,
                model,
                conversation_prompt,
                messages,
                max_tokens,
                timeout,
                proxies,
            )
        else:
            return self._create_non_streaming(
                request_id,
                created_time,
                model,
                conversation_prompt,
                messages,
                max_tokens,
                timeout,
                proxies,
            )

    def _create_streaming(
        self,
        request_id: str,
        created_time: int,
        model: str,
        conversation_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int],
        timeout: Optional[int],
        proxies: Optional[dict],
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Implementation for streaming chat completions.

        Yields :class:`ChatCompletionChunk` objects for each text delta and a
        final usage chunk once the stream terminates.

        Args:
            request_id: Unique identifier for the completion.
            created_time: Unix timestamp of the request.
            model: Resolved model identifier.
            conversation_prompt: Formatted prompt string for token counting.
            messages: Conversation message dictionaries.
            max_tokens: Optional maximum tokens (unused by Surfsense).
            timeout: Optional request timeout.
            proxies: Optional proxy configuration dict.

        Yields:
            :class:`ChatCompletionChunk` objects.
        """
        try:
            prompt_tokens = count_tokens(conversation_prompt)
            completion_tokens = 0
            total_tokens = 0
            full_content = ""

            payload = {
                "model_slug": model,
                "messages": messages,
            }

            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                impersonate="safari15_3",
                timeout=timeout or 30,
                proxies=proxies,  # ty:ignore[invalid-argument-type]
                stream=True,
            )

            if not response.ok:
                raise Exception(
                    f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                )

            for line in response.iter_lines(decode_unicode=False):
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                line = line.strip()

                if not line.startswith("data:"):
                    continue

                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "text-delta":
                    delta_text = event.get("delta", "")
                    if delta_text:
                        full_content += delta_text
                        completion_tokens = count_tokens(full_content)
                        total_tokens = prompt_tokens + completion_tokens

                        delta = ChoiceDelta(content=delta_text, role="assistant")
                        choice = Choice(index=0, delta=delta, finish_reason=None)
                        chunk_response = ChatCompletionChunk(
                            id=request_id,
                            choices=[choice],
                            created=created_time,
                            model=model,
                        )
                        chunk_response.usage = {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                        }
                        yield chunk_response

            # Final chunk with finish_reason.
            total_tokens = prompt_tokens + completion_tokens
            delta = ChoiceDelta(content=None)
            choice = Choice(index=0, delta=delta, finish_reason="stop")
            final_chunk = ChatCompletionChunk(
                id=request_id, choices=[choice], created=created_time, model=model
            )
            final_chunk.usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
            yield final_chunk

        except Exception as e:
            raise IOError(f"Surfsense streaming request failed: {e}") from e

    def _create_non_streaming(
        self,
        request_id: str,
        created_time: int,
        model: str,
        conversation_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int],
        timeout: Optional[int],
        proxies: Optional[dict],
    ) -> ChatCompletion:
        """Implementation for non-streaming chat completions.

        Collects the full response from the SSE stream and returns a single
        :class:`ChatCompletion` with usage information.

        Args:
            request_id: Unique identifier for the completion.
            created_time: Unix timestamp of the request.
            model: Resolved model identifier.
            conversation_prompt: Formatted prompt string for token counting.
            messages: Conversation message dictionaries.
            max_tokens: Optional maximum tokens (unused by Surfsense).
            timeout: Optional request timeout.
            proxies: Optional proxy configuration dict.

        Returns:
            A populated :class:`ChatCompletion` object.
        """
        try:
            prompt_tokens = count_tokens(conversation_prompt)
            full_content = ""

            payload = {
                "model_slug": model,
                "messages": messages,
            }

            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                impersonate="safari15_3",
                timeout=timeout or 30,
                proxies=proxies,  # ty:ignore[invalid-argument-type]
                stream=True,
            )

            if not response.ok:
                raise Exception(
                    f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                )

            for line in response.iter_lines(decode_unicode=False):
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                line = line.strip()

                if not line.startswith("data:"):
                    continue

                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "text-delta":
                    delta_text = event.get("delta", "")
                    if delta_text:
                        full_content += delta_text

            completion_tokens = count_tokens(full_content)
            total_tokens = prompt_tokens + completion_tokens

            message = ChatCompletionMessage(role="assistant", content=full_content)

            choice = Choice(index=0, message=message, finish_reason="stop")

            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            completion = ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )

            return completion

        except Exception as e:
            raise IOError(f"Surfsense request failed: {e}") from e


class Chat(BaseChat):
    """Chat interface exposing completions for the Surfsense provider."""

    def __init__(self, client: "Surfsense"):
        """Initialize the chat interface.

        Args:
            client: The owning :class:`Surfsense` provider instance.
        """
        self.completions = Completions(client)
        self.client = client


class Surfsense(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for the Surfsense anonymous chat API.

    Usage:
        client = Surfsense()
        response = client.chat.completions.create(
            model="gpt-o4-mini-no-login",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)
    """

    required_auth = False

    url = "https://www.surfsense.com"
    api_endpoint = "https://api.surfsense.com/api/v1/public/anon-chat/stream"
    default_model = "gpt-o4-mini-no-login"

    AVAILABLE_MODELS = AVAILABLE_MODELS
    model_aliases = {
        "o4-mini": "gpt-o4-mini-no-login",
        "gpt-4o-mini": "gpt-o4-mini-no-login",
        "gpt-4.5-mini": "gpt-o4-mini-no-login",
    }

    def __init__(self, tools: Optional[List] = None, proxies: Optional[Dict[str, str]] = None):
        """Initialize the Surfsense-compatible client.

        Args:
            tools: Optional list of tools to register with the provider.
            proxies: Optional proxy configuration dict.
        """
        self.timeout = 30
        self.user_agent = agent().random()
        self.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://www.surfsense.com",
            "referer": "https://www.surfsense.com/",
            "user-agent": self.user_agent,
        }

        self.session = Session()
        if proxies:
            self.session.proxies.update(cast(Any, proxies))
        self.session.headers.update(self.headers)

        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        """Return the list of available models for this provider."""
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = Surfsense()
    print("NON-STREAMING RESPONSE:")
    response = client.chat.completions.create(
        model="gpt-o4-mini-no-login",
        messages=[
            {"role": "user", "content": "Hello, how are you?"},
        ],
    )
    print(response)
    print("\nSTREAMING RESPONSE:")
    stream_response = client.chat.completions.create(
        model="gpt-o4-mini-no-login",
        messages=[
            {"role": "user", "content": "Hello, how are you?"},
        ],
        stream=True,
    )
    for chunk in stream_response:
        print(chunk)
