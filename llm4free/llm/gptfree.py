import base64
from llm4free import LitAgent
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union, cast

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
)


def _to_data_uri(image: Any) -> str:
    """Convert an image to a base64 data URI."""
    if isinstance(image, str):
        if image.startswith("data:"):
            return image
        if image.startswith("http"):
            return image
        path = Path(image)
        if path.exists():
            data = base64.b64encode(path.read_bytes()).decode()
            mime = "image/png"
            ext = path.suffix.lower()
            if ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".webp":
                mime = "image/webp"
            elif ext == ".gif":
                mime = "image/gif"
            return f"data:{mime};base64,{data}"
        return image
    raise TypeError(f"Unsupported image type: {type(image)}")


def _encode_image(image: Any) -> str:
    """Convert various image formats to base64 data URI."""
    if isinstance(image, str):
        return _to_data_uri(image)
    if isinstance(image, tuple):
        return _to_data_uri(image[0])
    raise TypeError(f"Unsupported image type: {type(image)}")


class Completions(BaseCompletions):
    def __init__(self, client: "GptFree"):
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
        tools: Optional[List[Union[Any, Dict[str, Any]]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion with GptFree API."""
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(
                request_id,
                created_time,
                model,
                messages,
                max_tokens,
                temperature,
                top_p,
                timeout,
                proxies,
                kwargs,
            )
        return self._create_non_stream(
            request_id,
            created_time,
            model,
            messages,
            max_tokens,
            temperature,
            top_p,
            timeout,
            proxies,
            kwargs,
        )

    def _build_payload(self, messages: List[Dict[str, Any]], kwargs: Dict[str, Any]):
        """Build the message history and extract current message for the payload."""
        history: List[Dict[str, str]] = []
        current_message = ""
        images: List[str] = []

        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        img_url = part.get("image_url", {}).get("url")
                        if img_url:
                            images.append(img_url)
                content = "\n".join(text_parts)

            if msg["role"] == "system":
                history.append({"type": "user", "content": content})
            elif msg["role"] == "user":
                history.append({"type": "user", "content": content})
            elif msg["role"] == "assistant":
                history.append({"type": "agent", "content": content})

        if "image" in kwargs and kwargs["image"]:
            images.append(_encode_image(kwargs["image"]))
        if "images" in kwargs and kwargs["images"]:
            for img in kwargs["images"]:
                images.append(_encode_image(img))
        if "media" in kwargs and kwargs["media"]:
            for m in kwargs["media"]:
                images.append(_encode_image(m))

        if history and history[-1]["type"] == "user":
            current_message = history.pop()["content"]

        if not current_message.strip():
            if history and history[-1]["type"] == "user":
                current_message = history.pop()["content"]
            else:
                current_message = "Analyze this image" if images else "Hello"

        return {
            "message": current_message,
            "images": images,
            "history": history,
        }

    def _get_firebase_token(
        self, proxies: Optional[Dict[str, str]] = None, timeout: Optional[int] = None
    ) -> str:
        """Authenticate with Firebase and return an ID token."""
        firebase_api_key = "AIzaSyBdU-Np8RSh1tPSsPOWg3qIm6PnVK5PQb4"
        auth_url = (
            f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={firebase_api_key}"
        )
        response = self._client.session.post(
            auth_url,
            json={"returnSecureToken": True},
            proxies=cast(Any, proxies),
            timeout=timeout or self._client.timeout,
        )
        response.raise_for_status()
        return response.json()["idToken"]

    def _make_request(self, payload: Dict[str, Any], firebase_token: str, stream: bool = False):
        """Send the completion request and return the raw response."""
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://gptfree.com",
            "referer": "https://gptfree.com/",
            "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": LitAgent().random(),
            "Authorization": f"Bearer {firebase_token}",
        }
        response = self._client.session.post(
            self._client.api_endpoint,
            headers=headers,
            json=payload,
            proxies=cast(Any, self._client.proxies),
            timeout=self._client.timeout,
            stream=stream,
        )
        response.raise_for_status()
        return response

    def _parse_stream(
        self,
        response: Any,
        request_id: str,
        created_time: int,
        model: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Parse streaming SSE response into ChatCompletionChunk objects."""
        full_content = ""
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        for line in response.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                try:
                    line = line.decode("utf-8")
                except Exception:
                    continue
            line = line.strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if not data_str or data_str == "{}":
                continue
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if "response" in data:
                content_piece = data["response"]
                full_content += content_piece
                completion_tokens = count_tokens(full_content)
                total_tokens = prompt_tokens + completion_tokens

                delta = ChoiceDelta(content=content_piece, role="assistant")
                choice = Choice(index=0, delta=delta, finish_reason=None)
                chunk = ChatCompletionChunk(
                    id=request_id,
                    choices=[choice],
                    created=created_time,
                    model=model,
                )
                chunk.usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }
                yield chunk

        delta = ChoiceDelta(content=None)
        choice = Choice(index=0, delta=delta, finish_reason="stop")
        chunk = ChatCompletionChunk(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
        )
        chunk.usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        yield chunk

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
        kwargs: Dict[str, Any],
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Handle streaming response from GptFree API."""
        try:
            payload = self._build_payload(messages, kwargs)
            firebase_token = self._get_firebase_token(proxies, timeout)
            response = self._make_request(payload, firebase_token, stream=True)
            yield from self._parse_stream(response, request_id, created_time, model)
        except Exception as e:
            raise IOError(f"GptFree request failed: {e}") from e

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
        kwargs: Dict[str, Any],
    ) -> ChatCompletion:
        """Handle non-streaming response by aggregating the SSE stream."""
        try:
            payload = self._build_payload(messages, kwargs)
            firebase_token = self._get_firebase_token(proxies, timeout)
            response = self._make_request(payload, firebase_token, stream=True)

            full_content = ""
            for chunk in self._parse_stream(response, request_id, created_time, model):
                if chunk.choices[0].delta and chunk.choices[0].delta.content:
                    full_content += chunk.choices[0].delta.content
                if chunk.usage:
                    final_usage = chunk.usage

            prompt_tokens = final_usage.get("prompt_tokens", 0) if chunk.usage else 0
            completion_tokens = final_usage.get("completion_tokens", 0) if chunk.usage else 0
            total_tokens = final_usage.get("total_tokens", 0) if chunk.usage else 0

            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            message = ChatCompletionMessage(role="assistant", content=full_content)
            choice = Choice(index=0, message=message, finish_reason="stop")

            return ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )
        except Exception as e:
            raise IOError(f"GptFree request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "GptFree"):
        self.completions = Completions(client)


class GptFree(OpenAICompatibleProvider):
    """
    GptFree - A free OpenAI-compatible provider via gptfree.com

    Usage:
        from llm4free.llm import GptFree

        client = GptFree()

        # Streaming
        for chunk in client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
            stream=True,
        ):
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)

        # Non-streaming
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
            stream=False,
        )
        print(response.choices[0].message.content)
    """

    url = "https://gptfree.com"
    api_endpoint = "https://us-central1-gptfree-2.cloudfunctions.net/agent_stream"
    working = True
    supports_message_history = True
    supports_system_message = False
    timeout = 120

    AVAILABLE_MODELS = ["gpt-4o"]

    def __init__(
        self,
        proxies: Optional[Dict[str, str]] = None,
        timeout: int = 120,
    ):
        """
        Initialize the GptFree provider.

        Args:
            proxies: Optional proxy configuration dict, e.g. {"http": "http://proxy:8080", "https": "https://proxy:8080"}
            timeout: Request timeout in seconds
        """
        super().__init__(proxies=proxies)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.proxies.update(cast(Any, proxies or {}))
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(self.AVAILABLE_MODELS)


if __name__ == "__main__":
    client = GptFree()

    # Streaming example
    print("Streaming response:")
    for chunk in client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
        stream=True,
    ):
        if (
            isinstance(chunk, ChatCompletionChunk)
            and chunk.choices[0].delta
            and chunk.choices[0].delta.content
        ):
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n--- End of streaming ---\n")

    # Non-streaming example
    print("Non-streaming response:")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
        stream=False,
    )
    if (
        isinstance(response, ChatCompletion)
        and response.choices[0].message
        and response.choices[0].message.content
    ):
        print(response.choices[0].message.content)
