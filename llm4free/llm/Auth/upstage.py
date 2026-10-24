"""Upstage Solar API Provider - OpenAI Compatible.

This module provides an OpenAI-compatible interface for Upstage's Solar models.
"""

import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

from curl_cffi import CurlError
from curl_cffi.requests import Session

from llm4free.litagent import LitAgent

from ..base import BaseChat, BaseCompletions, OpenAICompatibleProvider, SimpleModelList
from ..utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
)


class Completions(BaseCompletions):
    """Completions handler for Upstage API."""

    def __init__(self, client: "Upstage"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 4096,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p

        # Add any additional parameters
        payload.update(kwargs)

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(request_id, created_time, model, payload)
        else:
            return self._create_non_stream(request_id, created_time, model, payload)

    def _create_stream(
        self, request_id: str, created_time: int, model: str, payload: Dict[str, Any]
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Handle streaming response from Upstage API."""
        try:
            response = self._client.session.post(
                self._client.base_url,
                json=payload,
                stream=True,
                timeout=self._client.timeout,
                impersonate="chrome110",
            )

            if response.status_code != 200:
                raise IOError(
                    f"Upstage request failed with status code {response.status_code}: {response.text}"
                )

            # Track token usage across chunks
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

            for line in response.iter_lines(decode_unicode=True):
                if line:
                    if line.startswith("data: "):
                        json_str = line[6:]
                        if json_str == "[DONE]":
                            break

                        try:
                            data = json.loads(json_str)
                            choices = data.get("choices")
                            if not choices and choices is not None:
                                continue
                            choice_data = choices[0] if choices else {}
                            delta_data = choice_data.get("delta", {})
                            finish_reason = choice_data.get("finish_reason")

                            # Update token counts if available
                            usage_data = data.get("usage", {})
                            if usage_data:
                                prompt_tokens = usage_data.get("prompt_tokens", prompt_tokens)
                                completion_tokens = usage_data.get(
                                    "completion_tokens", completion_tokens
                                )
                                total_tokens = usage_data.get("total_tokens", total_tokens)

                            # Create the delta object
                            delta = ChoiceDelta(
                                content=delta_data.get("content"),
                                role=delta_data.get("role"),
                                tool_calls=delta_data.get("tool_calls"),
                            )

                            # Create the choice object
                            choice = Choice(
                                index=choice_data.get("index", 0),
                                delta=delta,
                                finish_reason=finish_reason,
                                logprobs=choice_data.get("logprobs"),
                            )

                            # Create the chunk object
                            chunk = ChatCompletionChunk(
                                id=request_id,
                                choices=[choice],
                                created=created_time,
                                model=model,
                                system_fingerprint=data.get("system_fingerprint"),
                            )

                            # Convert chunk to dict using Pydantic's API
                            if hasattr(chunk, "model_dump"):
                                chunk_dict = chunk.model_dump(exclude_none=True)
                            else:
                                chunk_dict = chunk.dict(exclude_none=True)

                            # Add usage information to match OpenAI format
                            usage_dict = {
                                "prompt_tokens": prompt_tokens or 10,
                                "completion_tokens": completion_tokens
                                or (
                                    len(delta_data.get("content", ""))
                                    if delta_data.get("content")
                                    else 0
                                ),
                                "total_tokens": total_tokens
                                or (
                                    10
                                    + (
                                        len(delta_data.get("content", ""))
                                        if delta_data.get("content")
                                        else 0
                                    )
                                ),
                                "estimated_cost": None,
                            }

                            # Update completion_tokens and total_tokens as we receive more content
                            if delta_data.get("content"):
                                completion_tokens += 1
                                total_tokens = prompt_tokens + completion_tokens
                                usage_dict["completion_tokens"] = completion_tokens
                                usage_dict["total_tokens"] = total_tokens

                            chunk_dict["usage"] = usage_dict

                            yield chunk
                        except json.JSONDecodeError:
                            print(f"Warning: Could not decode JSON line: {json_str}")
                            continue
        except CurlError as e:
            print(f"Error during Upstage stream request: {e}")
            raise IOError(f"Upstage request failed: {e}") from e
        except Exception as e:
            print(f"Error processing Upstage stream: {e}")
            raise

    def _create_non_stream(
        self, request_id: str, created_time: int, model: str, payload: Dict[str, Any]
    ) -> ChatCompletion:
        """Handle non-streaming response from Upstage API."""
        try:
            response = self._client.session.post(
                self._client.base_url,
                json=payload,
                timeout=self._client.timeout,
                impersonate="chrome110",
            )

            if response.status_code != 200:
                raise IOError(
                    f"Upstage request failed with status code {response.status_code}: {response.text}"
                )

            data = response.json()

            choices_data = data.get("choices", [])
            usage_data = data.get("usage", {})

            choices = []
            for choice_d in choices_data:
                message_d = choice_d.get("message", {})

                # Handle tool calls if present
                tool_calls = message_d.get("tool_calls")

                message = ChatCompletionMessage(
                    role=message_d.get("role", "assistant"),
                    content=message_d.get("content", ""),
                    tool_calls=tool_calls,
                )
                choice = Choice(
                    index=choice_d.get("index", 0),
                    message=message,
                    finish_reason=choice_d.get("finish_reason", "stop"),
                )
                choices.append(choice)

            usage = CompletionUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

            completion = ChatCompletion(
                id=request_id,
                choices=choices,
                created=created_time,
                model=data.get("model", model),
                usage=usage,
            )
            return completion

        except CurlError as e:
            print(f"Error during Upstage non-stream request: {e}")
            raise IOError(f"Upstage request failed: {e}") from e
        except Exception as e:
            print(f"Error processing Upstage response: {e}")
            raise


class Chat(BaseChat):
    """Chat interface for Upstage API."""

    def __init__(self, client: "Upstage"):
        self.completions = Completions(client)


class Upstage(OpenAICompatibleProvider):
    """Upstage Solar API Provider - OpenAI Compatible.

    A provider for interacting with Upstage Solar models using an OpenAI-compatible
    interface. Supports Solar 1 Pro, Solar Pro 2, and Solar Pro 3 models.

    Required API Key:
        - Get from https://console.upstage.ai/api-keys
        - Set via api_key parameter or UPSTAGE_API_KEY environment variable

    Attributes:
        api_key (str): Your Upstage API key
        timeout (int): Request timeout in seconds (default: 30)
        base_url (str): API endpoint URL

    Available Models:
        - solar-1-pro: Upstage Solar 1 Pro
        - solar-pro-2: Upstage Solar Pro 2
        - solar-pro-3: Upstage Solar Pro 3 (default)

    Examples:
        >>> from llm4free.llm import Upstage
        >>> client = Upstage(api_key="YOUR_API_KEY")
        >>> response = client.chat.completions.create(
        ...     model="solar-pro-3",
        ...     messages=[{"role": "user", "content": "Hello!"}]
        ... )
        >>> print(response.choices[0].message.content)

        >>> # Streaming
        >>> for chunk in client.chat.completions.create(
        ...     model="solar-pro-3",
        ...     messages=[{"role": "user", "content": "Tell me a joke"}],
        ...     stream=True
        ... ):
        ...     print(chunk.choices[0].delta.content, end="", flush=True)
    """

    required_auth = True
    AVAILABLE_MODELS = [
        "solar-1-pro",
        "solar-pro-2",
        "solar-pro-3",
    ]

    def __init__(
        self, api_key: Optional[str] = None, timeout: Optional[int] = 30, browser: str = "chrome"
    ):
        """
        Initialize the Upstage API client.

        Args:
            api_key: Upstage API key. If None, uses UPSTAGE_API_KEY env var.
            timeout: Request timeout in seconds (default: 30).
            browser: Browser type for fingerprinting (default: "chrome").

        Raises:
            ValueError: If API key is not provided and not found in environment.
        """
        self.timeout = timeout
        self.base_url = "https://api.upstage.ai/v1/chat/completions"

        # Get API key from parameter or environment
        if not api_key:
            import os

            api_key = os.getenv("UPSTAGE_API_KEY")

        if not api_key:
            raise ValueError(
                "Upstage API key is required. Set via api_key parameter or UPSTAGE_API_KEY env var."
            )

        self.api_key = api_key

        # Defer model fetch to background to avoid blocking initialization
        self._start_background_model_fetch(api_key=api_key)

        # Initialize curl_cffi Session
        self.session = Session()

        # Set up headers with API key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Try to use LitAgent for browser fingerprinting
        try:
            agent = LitAgent()
            fingerprint = agent.generate_fingerprint(browser)

            self.headers.update(
                {
                    "Accept": fingerprint["accept"],
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": fingerprint["accept_language"],
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Origin": "https://console.upstage.ai",
                    "Pragma": "no-cache",
                    "Referer": "https://console.upstage.ai/",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "Sec-CH-UA": fingerprint["sec_ch_ua"]
                    or '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
                    "Sec-CH-UA-Mobile": "?0",
                    "Sec-CH-UA-Platform": f'"{fingerprint["platform"]}"',
                    "User-Agent": fingerprint["user_agent"],
                }
            )
        except (NameError, Exception):
            # Fallback to basic headers if LitAgent is not available
            self.headers.update(
                {
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                }
            )

        # Update session headers
        self.session.headers.update(self.headers)

        # Initialize chat interface
        self.chat = Chat(self)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """Fetch available models from Upstage API.

        Args:
            api_key (str, optional): Upstage API key. If not provided, returns default models.

        Returns:
            list: List of available model IDs
        """
        if not api_key:
            return cls.AVAILABLE_MODELS

        try:
            # Use a temporary curl_cffi session for this class method
            temp_session = Session()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            response = temp_session.get(
                "https://api.upstage.ai/v1/models", headers=headers, impersonate="chrome110"
            )

            if response.status_code != 200:
                return cls.AVAILABLE_MODELS

            data = response.json()
            if "data" in data and isinstance(data["data"], list):
                return [model["id"] for model in data["data"]]
            return cls.AVAILABLE_MODELS

        except (CurlError, Exception):
            # Fallback to default models list if fetching fails
            return cls.AVAILABLE_MODELS

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None) -> None:
        """Update the available models list from Upstage API."""
        try:
            models = cls.get_models(api_key)
            if models and len(models) > 0:
                cls.AVAILABLE_MODELS = models
        except Exception:
            # Fallback to default models list if fetching fails
            pass

    @property
    def models(self) -> SimpleModelList:
        """Return the list of available models."""
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    # Example usage
    try:
        client = Upstage(api_key="YOUR_API_KEY_HERE")

        # Non-streaming example
        print("[cyan]Non-Streaming Response:[/cyan]")
        response = client.chat.completions.create(
            model="solar-pro-3",
            messages=[
                {"role": "user", "content": "What are the limitations of current AI models?"}
            ],
            stream=False,
        )
        print(response.choices[0].message.content)  # type: ignore

        print("\n[cyan]Streaming Response:[/cyan]")
        # Streaming example
        for chunk in client.chat.completions.create(
            model="solar-pro-3",
            messages=[{"role": "user", "content": "Write a short poem about machine learning"}],
            stream=True,
        ):
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()

    except ValueError as e:
        print(f"[red]Error: {e}[/red]")
    except IOError as e:
        print(f"[red]Request Error: {e}[/red]")
