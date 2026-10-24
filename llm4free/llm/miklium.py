import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

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
    CompletionUsage,
    count_tokens,
    format_prompt,
)

# Miklium constants
AVAILABLE_MODELS = ["miklium", "personalityless", "male", "female", "all"]


class Completions(BaseCompletions):
    """Chat completions interface for the Miklium provider."""

    def __init__(self, client: "Miklium"):
        """
        Initialize the completions handler.

        Args:
            client: The parent Miklium provider instance.
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
    ) -> Any:
        """
        Create a chat completion with the Miklium API.

        Mimics ``openai.chat.completions.create``. Miklium only supports
        non-streaming responses (a single plain JSON object), so passing
        ``stream=True`` raises a ``NotImplementedError``.

        Args:
            model: The Miklium personality/model to use.
            messages: List of message dictionaries.
            max_tokens: Maximum number of tokens to generate (unused by Miklium).
            stream: Must be ``False``; streaming is not supported.
            temperature: Sampling temperature (unused by Miklium).
            top_p: Nucleus sampling parameter (unused by Miklium).
            timeout: Optional request timeout in seconds.
            proxies: Optional proxy configuration dict.
            **kwargs: Extra arguments; ``response_stacking`` can be supplied here.

        Returns:
            A single ``ChatCompletion`` object.

        Raises:
            NotImplementedError: If ``stream=True`` is requested.
        """
        if stream:
            raise NotImplementedError(
                "Miklium does not support streaming; use stream=False."
            )

        # Use format_prompt utility to format the conversation into a single string
        conversation_prompt = format_prompt(messages, add_special_tokens=True, include_system=True)
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        return self._create_non_stream(
            request_id,
            created_time,
            model,
            conversation_prompt,
            timeout,
            proxies,
            kwargs,
        )

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        conversation_prompt: str,
        timeout: Optional[int],
        proxies: Optional[dict],
        kwargs: Dict[str, Any],
    ) -> ChatCompletion:
        """Implementation for non-streaming chat completions."""
        try:
            response_stacking = kwargs.get("response_stacking", 4)

            payload = {
                "message": conversation_prompt,
                "response_stacking": response_stacking,
                "personality": model,
            }

            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                timeout=timeout or 30,
                proxies=proxies,  # ty:ignore[invalid-argument-type]
                impersonate="chrome",
            )

            response.raise_for_status()
            data = response.json()

            if data.get("success") in (True, "true"):
                content = data.get("response") or data.get("message") or ""
            else:
                raise RuntimeError(
                    f"Miklium request failed: success={data.get('success')!r} "
                    f"message={data.get('message')!r}"
                )

            prompt_tokens = count_tokens(conversation_prompt)
            completion_tokens = count_tokens(content)
            total_tokens = prompt_tokens + completion_tokens

            message = ChatCompletionMessage(role="assistant", content=content)
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
            raise IOError(f"Miklium request failed: {e}") from e


class Chat(BaseChat):
    """Chat interface for the Miklium provider."""

    def __init__(self, client: "Miklium"):
        """
        Initialize the chat handler.

        Args:
            client: The parent Miklium provider instance.
        """
        self.completions = Completions(client)


class Miklium(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for the Miklium chatbot API.

    Usage:
        client = Miklium()
        response = client.chat.completions.create(
            model="miklium",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)
    """

    required_auth = False

    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(self, tools: Optional[List] = None, proxies: Optional[Dict[str, str]] = None):
        """
        Initialize the Miklium-compatible client.

        Args:
            tools: Optional list of tools to register with the provider.
            proxies: Optional proxy configuration dict.
        """
        super().__init__(api_key=None, tools=tools, proxies=proxies)

        self.session = Session()
        if self.proxies:
            self.session.proxies.update(self.proxies)  # ty:ignore[invalid-argument-type]

        self.timeout = 30
        self.api_endpoint = "https://miklium.vercel.app/api/chatbot"
        self.user_agent = agent().random()
        self.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://miklium.vercel.app",
            "referer": "https://miklium.vercel.app/",
            "user-agent": self.user_agent,
        }

        self.session.headers.update(self.headers)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = Miklium()
    print("NON-STREAMING RESPONSE:")
    response = client.chat.completions.create(
        model="miklium",
        messages=[
            {"role": "user", "content": "Hello, how are you?"},
        ],
    )
    print(response)
