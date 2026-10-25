"""
TextPollinations OpenAI-compatible provider.
https://gen.pollinations.ai/v1
Requires an API key from https://pollinations.ai
"""

import json
import os
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from llm4free.browser_requests._http import compat as requests

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
    ToolCall,
    ToolFunction,
    count_tokens,
)

BOLD = "\033[1m"
RED = "\033[91m"
RESET = "\033[0m"


class Completions(BaseCompletions):
    """
    Handles chat completion requests for TextPollinations.
    """

    def __init__(self, client: "TextPollinations"):
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
        tools: Optional[List[Union[Any, Dict[str, Any]]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create.
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        payload.update(kwargs)

        request_id = str(uuid.uuid4())
        created_time = int(time.time())

        if stream:
            return self._create_streaming(
                request_id, created_time, model, payload, timeout, proxies
            )
        else:
            return self._create_non_streaming(
                request_id, created_time, model, payload, timeout, proxies
            )

    def _create_streaming(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """
        Implementation for streaming chat completions using SSE.
        """
        try:
            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
                proxies=proxies or getattr(self._client, "proxies", None),  # ty: ignore
            )

            if not response.ok:
                raise IOError(
                    f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                )

            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8").strip()
                    if line == "data: [DONE]":
                        break
                    if line.startswith("data: "):
                        try:
                            json_data = json.loads(line[6:])
                            if "choices" in json_data and len(json_data["choices"]) > 0:
                                choice = json_data["choices"][0]
                                if "delta" in choice:
                                    delta_obj = ChoiceDelta()

                                    if "content" in choice["delta"]:
                                        content = choice["delta"]["content"]
                                        delta_obj.content = content

                                    if "tool_calls" in choice["delta"]:
                                        tool_calls = []
                                        for tool_call_data in choice["delta"]["tool_calls"]:
                                            if "function" in tool_call_data:
                                                function = ToolFunction(
                                                    name=tool_call_data["function"].get("name", ""),
                                                    arguments=tool_call_data["function"].get(
                                                        "arguments", ""
                                                    ),
                                                )
                                                tool_call = ToolCall(
                                                    id=tool_call_data.get("id", str(uuid.uuid4())),
                                                    type=tool_call_data.get("type", "function"),
                                                    function=function,
                                                )
                                                tool_calls.append(tool_call)

                                        if tool_calls:
                                            delta_obj.tool_calls = tool_calls

                                    choice_obj = Choice(
                                        index=0, delta=delta_obj, finish_reason=None
                                    )
                                    chunk = ChatCompletionChunk(
                                        id=request_id,
                                        choices=[choice_obj],
                                        created=created_time,
                                        model=model,
                                    )

                                    yield chunk
                        except json.JSONDecodeError:
                            continue

            delta = ChoiceDelta(content=None)
            choice = Choice(index=0, delta=delta, finish_reason="stop")
            chunk = ChatCompletionChunk(
                id=request_id, choices=[choice], created=created_time, model=model
            )

            yield chunk

        except Exception as e:
            print(f"{RED}Error during TextPollinations streaming request: {e}{RESET}")
            raise IOError(f"TextPollinations streaming request failed: {e}") from e

    def _create_non_streaming(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        """
        Implementation for non-streaming chat completions.
        """
        try:
            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                timeout=timeout or self._client.timeout,
                proxies=proxies or getattr(self._client, "proxies", None),  # ty: ignore
            )

            if not response.ok:
                raise IOError(
                    f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                )

            response_json = response.json()

            full_content = ""
            message = ChatCompletionMessage(role="assistant", content="")

            if "choices" in response_json and len(response_json["choices"]) > 0:
                choice_data = response_json["choices"][0]
                if "message" in choice_data:
                    message_data = choice_data["message"]
                    full_content = message_data.get("content", "")
                    message = ChatCompletionMessage(role="assistant", content=full_content)

                    if "tool_calls" in message_data:
                        tool_calls = []
                        for tool_call_data in message_data["tool_calls"]:
                            if "function" in tool_call_data:
                                function = ToolFunction(
                                    name=tool_call_data["function"].get("name", ""),
                                    arguments=tool_call_data["function"].get("arguments", ""),
                                )
                                tool_call = ToolCall(
                                    id=tool_call_data.get("id", str(uuid.uuid4())),
                                    type=tool_call_data.get("type", "function"),
                                    function=function,
                                )
                                tool_calls.append(tool_call)

                        if tool_calls:
                            message.tool_calls = tool_calls

            choice = Choice(index=0, message=message, finish_reason="stop")

            prompt_tokens = count_tokens(
                [msg.get("content", "") for msg in payload.get("messages", [])]
            )
            completion_tokens = count_tokens(full_content)
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
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
            print(f"{RED}Error during TextPollinations non-stream request: {e}{RESET}")
            raise IOError(f"TextPollinations request failed: {e}") from e


class Chat(BaseChat):
    """
    Standard chat interface for the provider.
    """

    def __init__(self, client: "TextPollinations"):
        self.completions = Completions(client)


class TextPollinations(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for TextPollinations API.
    Requires an API key from https://pollinations.ai
    New API endpoint: https://gen.pollinations.ai/v1
    """

    required_auth = True

    AVAILABLE_MODELS = ["openai", "openai-large", "openai-fast", "gemini", "deepseek", "mistral"]

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """
        Fetch available models from TextPollinations API.
        """
        try:
            headers = {"Accept": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            response = requests.get(
                "https://gen.pollinations.ai/v1/models",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    # Standard list format (e.g., [{"name": "..."}])
                    return [
                        model.get("name")
                        for model in data
                        if isinstance(model, dict) and "name" in model
                    ]
                elif isinstance(data, dict) and "data" in data:
                    # OpenAI-compatible format (e.g., {"data": [{"id": "..."}]})
                    return [
                        model.get("id")
                        for model in data["data"]
                        if isinstance(model, dict) and "id" in model
                    ]

            return cls.AVAILABLE_MODELS

        except Exception:
            return cls.AVAILABLE_MODELS

    def __init__(self, api_key: str, timeout: int = 30, proxies: dict = {}):
        """
        Initialize the TextPollinations client.

        Args:
            api_key (str): Pollinations API key (required).
            timeout (int): Request timeout in seconds. Defaults to 30.
            proxies (dict): Proxy configuration. Defaults to {}.
        """
        # Start background model fetch (non-blocking)
        self._start_background_model_fetch()

        self.timeout = timeout
        self.api_endpoint = "https://gen.pollinations.ai/v1/chat/completions"
        self.proxies = proxies
        self.api_key = api_key

        self.session = requests.Session()
        if proxies:
            self.session.proxies.update(cast(Any, proxies))

        agent = LitAgent()
        self.user_agent = agent.random()

        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        self.session.headers.update(self.headers)
        self.chat = Chat(self)

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None):
        """
        Update the available models list from the API.
        """
        models = cls.get_models(api_key)
        if models:
            cls.AVAILABLE_MODELS = models

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")
    if not API_KEY:
        print("Set POLLINATIONS_API_KEY environment variable to test.")
        exit(1)

    client = TextPollinations(api_key=API_KEY)
    if client.models.list():
        print(f"Available models: {client.models.list()}")
        model_to_use = client.models.list()[0]
        print(f"Testing model: {model_to_use}")
        try:
            response = client.chat.completions.create(
                model=model_to_use, messages=[{"role": "user", "content": "Hello!"}]
            )
            if isinstance(response, ChatCompletion):
                if response.choices[0].message and response.choices[0].message.content:
                    print(response.choices[0].message.content)
        except Exception as e:
            print(f"Error testing model: {e}")
    else:
        print("No models available.")
