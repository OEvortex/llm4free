import base64
import json
import random
import re
import string
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, cast

from curl_cffi.requests import Session

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

# ANSI escape codes for formatting
BOLD = "\033[1m"
RED = "\033[91m"
RESET = "\033[0m"


class Completions(BaseCompletions):
    def __init__(self, client: "Toolbaz"):
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
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        # Format the messages using the format_prompt utility
        formatted_prompt = format_prompt(messages, add_special_tokens=True, do_continue=True)

        # The API only accepts its own lowercase model slugs
        resolved_model = self._client.resolve_model(model)

        # Get authentication token
        auth = self._client.get_auth()
        if not auth:
            raise IOError("Failed to authenticate with Toolbaz API")

        # Prepare the request data
        data = {
            "text": formatted_prompt,
            "capcha": auth["token"],
            "model": resolved_model,
            "session_id": auth["session_id"],
        }

        # Generate a unique request ID
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        # Handle streaming response
        if stream:
            return self._handle_streaming_response(
                request_id, created_time, resolved_model, data, timeout, proxies
            )
        else:
            return self._handle_non_streaming_response(
                request_id, created_time, resolved_model, data, timeout, proxies
            )

    def _handle_streaming_response(
        self,
        request_id: str,
        created_time: int,
        model: str,
        data: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Handle streaming response from Toolbaz API"""
        try:
            resp = self._client.session.post(
                "https://data.toolbaz.com/writing.php",
                data=data,
                stream=True,
                timeout=timeout or self._client.timeout,
                impersonate="chrome110",
            )
            self._client.raise_on_error(resp)

            buffer = ""
            tag_start = "[model:"
            streaming_text = ""

            for chunk in resp.iter_content(chunk_size=1):
                if chunk:
                    text = chunk.decode(errors="ignore")
                    buffer += text

                    # Remove all complete [model: ...] tags in buffer
                    while True:
                        match = re.search(r"\[model:.*?\]", buffer)
                        if not match:
                            break
                        buffer = buffer[: match.start()] + buffer[match.end() :]

                    # Only yield up to the last possible start of a tag
                    last_tag = buffer.rfind(tag_start)
                    if last_tag == -1 or last_tag + len(tag_start) > len(buffer):
                        if buffer:
                            streaming_text += buffer

                            # Create the delta object
                            delta = ChoiceDelta(content=buffer, role="assistant")

                            # Create the choice object
                            choice = Choice(index=0, delta=delta, finish_reason=None)

                            # Create the chunk object
                            chunk = ChatCompletionChunk(
                                id=request_id, choices=[choice], created=created_time, model=model
                            )

                            yield chunk
                            buffer = ""
                    else:
                        if buffer[:last_tag]:
                            streaming_text += buffer[:last_tag]

                            # Create the delta object
                            delta = ChoiceDelta(content=buffer[:last_tag], role="assistant")

                            # Create the choice object
                            choice = Choice(index=0, delta=delta, finish_reason=None)

                            # Create the chunk object
                            chunk = ChatCompletionChunk(
                                id=request_id, choices=[choice], created=created_time, model=model
                            )

                            yield chunk
                        buffer = buffer[last_tag:]

            # Remove any remaining [model: ...] tag in the buffer
            buffer = re.sub(r"\[model:.*?\]", "", buffer)
            if buffer:
                # Create the delta object
                delta = ChoiceDelta(content=buffer, role="assistant")

                # Create the choice object
                choice = Choice(index=0, delta=delta, finish_reason="stop")

                # Create the chunk object
                chunk = ChatCompletionChunk(
                    id=request_id, choices=[choice], created=created_time, model=model
                )

                yield chunk

            # Final chunk with finish_reason
            delta = ChoiceDelta(content=None, role=None)

            choice = Choice(index=0, delta=delta, finish_reason="stop")

            chunk = ChatCompletionChunk(
                id=request_id, choices=[choice], created=created_time, model=model
            )

            yield chunk

        except Exception as e:
            print(f"{RED}Error during Toolbaz streaming request: {e}{RESET}")
            raise IOError(f"Toolbaz streaming request failed: {e}") from e

    def _handle_non_streaming_response(
        self,
        request_id: str,
        created_time: int,
        model: str,
        data: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        """Handle non-streaming response from Toolbaz API"""
        try:
            resp = self._client.session.post(
                "https://data.toolbaz.com/writing.php",
                data=data,
                timeout=timeout or self._client.timeout,
                impersonate="chrome110",
            )
            self._client.raise_on_error(resp)

            text = resp.text
            # Remove [model: ...] tags
            text = re.sub(r"\[model:.*?\]", "", text)

            # Create the message object
            message = ChatCompletionMessage(role="assistant", content=text)

            # Create the choice object
            choice = Choice(index=0, message=message, finish_reason="stop")

            # Usage data is not provided by this API in a standard way, set to 0
            usage = CompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)

            # Create the completion object
            completion = ChatCompletion(
                id=request_id, choices=[choice], created=created_time, model=model, usage=usage
            )

            return completion

        except Exception as e:
            print(f"{RED}Error during Toolbaz non-stream request: {e}{RESET}")
            raise IOError(f"Toolbaz request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "Toolbaz"):
        self.completions = Completions(client)


class Toolbaz(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for Toolbaz API.

    Usage:
        client = Toolbaz()
        response = client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)
    """

    required_auth = False
    default_model = "gemini-2.5-flash"

    # These are the exact slugs accepted by writing.php. Display names such as
    # "Gemini-3.6-Flash" are normalized by resolve_model().
    AVAILABLE_MODELS = [
        # ToolBaz
        "toolbaz-v5",
        # Google
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3-flash",
        "gemini-3.6-flash",
        # DeepSeek
        "deepseek-v3",
        "deepseek-v3.1",
        "deepseek-r1",
        # OpenAI
        "gpt-5",
        "gpt-5.2",
        "gpt-4o",
        "gpt-oss-120b",
        "o3-mini",
        # Anthropic
        "claude-sonnet-4",
        # xAI
        "grok-4-fast",
        # Others (unfiltered)
        "midnight-rose",
    ]

    MODEL_ALIASES = {
        "gpt-4o (latest)": "gpt-4o",
        "toolbaz-v4.5-fast": "toolbaz-v5",
        "toolbaz-v4": "toolbaz-v5",
    }

    def __init__(self, timeout: int = 30, proxies: dict = {}, browser: str = "chrome"):
        """
        Initialize the Toolbaz client.

        Args:
            timeout: Request timeout in seconds
            proxies: Proxy configuration for requests
            browser: Browser name for LitAgent to generate User-Agent
        """
        self.timeout = timeout
        self.proxies = proxies

        # Initialize session with curl_cffi
        self.session = Session()

        # Set up headers
        self.session.headers.update(
            {
                **LitAgent().generate_fingerprint(browser=browser),
                "pragma": "no-cache",
                "referer": "https://toolbaz.com/",
            }
        )

        # Set proxies if provided
        if proxies:
            self.session.proxies.update(cast(Any, proxies))

        # Initialize chat property
        self.chat = Chat(self)

    def random_string(self, length):
        """Generate a random string of specified length"""
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))

    def resolve_model(self, model: Optional[str]) -> str:
        """Map a display name or alias to a slug accepted by the API."""
        if not model or not model.strip():
            return self.default_model

        key = model.strip().lower()
        if key in ("auto", "default"):
            return self.default_model

        alias = self.MODEL_ALIASES.get(key)
        if alias:
            return alias

        slug = re.sub(r"[^a-z0-9.]+", "-", key).strip("-")
        return slug or self.default_model

    @staticmethod
    def raise_on_error(resp: Any) -> None:
        """Raise with the response body, which carries the real error code."""
        if resp.status_code < 400:
            return
        detail = (resp.text or "").strip()[:500]
        message = f"HTTP {resp.status_code}"
        raise ValueError(f"{message}: {detail}" if detail else message)

    def generate_token(self):
        """Generate authentication token for Toolbaz API"""
        payload = {
            "bR6wF": {
                "nV5kP": self.session.headers.get("user-agent"),
                "lQ9jX": "en-US",
                "sD2zR": "431x958",
                "tY4hL": time.tzname[0] if time.tzname else "UTC",
                "pL8mC": "Linux armv81",
                "cQ3vD": datetime.now().year,
                "hK7jN": datetime.now().hour,
            },
            "uT4bX": {"mM9wZ": [], "kP8jY": []},
            "tuTcS": int(time.time()),
            "tDfxy": None,
            "RtyJt": str(uuid.uuid4()),
        }
        return "d8TW0v" + base64.b64encode(json.dumps(payload).encode()).decode()

    def get_auth(self):
        """Get authentication credentials for Toolbaz API"""
        try:
            session_id = self.random_string(36)
            token = self.generate_token()
            data = {"session_id": session_id, "token": token}
            resp = self.session.post(
                "https://data.toolbaz.com/token.php",
                data=data,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("success"):
                return {"token": result["token"], "session_id": session_id}
            return None
        except Exception as e:
            print(f"{RED}Error getting Toolbaz authentication: {e}{RESET}")
            return None

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


# Example usage
if __name__ == "__main__":
    # Test the provider
    client = Toolbaz()
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! How are you today?"},
        ],
        stream=True,
    )
    for chunk in response:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)