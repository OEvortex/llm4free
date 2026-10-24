import json
from llm4free import LitAgent
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

# Import base classes and utilities from llm provider stack
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
)


class Completions(BaseCompletions):
    """TwoAI chat completions compatible with OpenAI format."""

    def __init__(self, client: "TwoAI"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = 2049,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        online_search: Optional[bool] = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion using TwoAI."""
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
        if online_search is not None:
            payload["extra_body"] = {"online_search": online_search}

        payload.update(kwargs)

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(
                request_id, created_time, model, payload, timeout=timeout, proxies=proxies
            )
        return self._create_non_stream(
            request_id, created_time, model, payload, timeout=timeout, proxies=proxies
        )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        original_proxies = dict(self._client.session.proxies)
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))
        else:
            cast(Dict, self._client.session.proxies).clear()
        try:
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=timeout if timeout is not None else self._client.timeout,
                proxies=proxies or getattr(self._client, "proxies", None),  # ty:ignore[invalid-argument-type]
            )
            response.raise_for_status()

            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8").strip()
                if not decoded.startswith("data: "):
                    continue
                json_str = decoded[6:]
                if json_str == "[DONE]":
                    break
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                choice_data = data.get("choices", [{}])[0]
                delta_data = choice_data.get("delta", {})
                finish_reason = choice_data.get("finish_reason")

                usage_data = data.get("usage", {})
                if usage_data:
                    prompt_tokens = usage_data.get("prompt_tokens", prompt_tokens)
                    completion_tokens = usage_data.get("completion_tokens", completion_tokens)
                    total_tokens = usage_data.get("total_tokens", total_tokens)

                delta = ChoiceDelta(
                    content=delta_data.get("content"),
                    role=delta_data.get("role"),
                    tool_calls=delta_data.get("tool_calls"),
                )

                choice = Choice(
                    index=choice_data.get("index", 0),
                    delta=delta,
                    finish_reason=finish_reason,
                    logprobs=choice_data.get("logprobs"),
                )

                chunk = ChatCompletionChunk(
                    id=request_id,
                    choices=[choice],
                    created=created_time,
                    model=model,
                    system_fingerprint=data.get("system_fingerprint"),
                )

                yield chunk
        except Exception as e:
            raise IOError(f"TwoAI request failed: {e}") from e
        finally:
            cast(Dict, self._client.session.proxies).clear()
            self._client.session.proxies.update(cast(Any, original_proxies))

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        original_proxies = dict(self._client.session.proxies)
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))
        else:
            cast(Dict, self._client.session.proxies).clear()
        try:
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                timeout=timeout if timeout is not None else self._client.timeout,
                proxies=proxies or getattr(self._client, "proxies", None),  # ty:ignore[invalid-argument-type]
            )
            response.raise_for_status()
            data = response.json()

            choices_data = data.get("choices", [])
            usage_data = data.get("usage", {})

            choices = []
            for choice_d in choices_data:
                message_d = choice_d.get("message", {})
                message = ChatCompletionMessage(
                    role=message_d.get("role", "assistant"),
                    content=message_d.get("content", ""),
                    tool_calls=message_d.get("tool_calls"),
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
        except Exception as e:
            raise IOError(f"TwoAI request failed: {e}") from e
        finally:
            self._client.session.proxies.clear()  # ty:ignore[unresolved-attribute]
            self._client.session.proxies.update(cast(Any, original_proxies))


class Chat(BaseChat):
    def __init__(self, client: "TwoAI"):
        self.completions = Completions(client)


class TwoAI(OpenAICompatibleProvider):
    """OpenAI-compatible client for the TwoAI API."""

    required_auth = True
    AVAILABLE_MODELS = ["sutra-v2", "sutra-r0"]

    def __init__(
        self, api_key: str, browser: str = "chrome", proxies: Optional[Dict[str, str]] = None
    ):
        super().__init__(proxies=proxies)
        self.timeout = 30
        self.base_url = "https://chatsutra-server.account-2b0.workers.dev/v2/chat/completions"
        self.api_key = api_key

        headers: Dict[str, str] = {
            "User-Agent": LitAgent().random(),
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,en-IN;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://chat.two.ai",
            "Referer": "https://chatsutra-server.account-2b0.workers.dev/",
            "Sec-Ch-Ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Gpc": "1",
            "Dnt": "1",
            "X-Session-Token": api_key,
        }

        self.headers = headers
        self.session.headers.update(headers)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    two_ai = TwoAI(api_key="api_key")
    resp = two_ai.chat.completions.create(
        model="sutra-v2", messages=[{"role": "user", "content": "Hello, how are you?"}], stream=True
    )
    for chunk in resp:
        print(chunk, end="")
