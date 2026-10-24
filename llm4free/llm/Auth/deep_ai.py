# Standard library imports
import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi.requests import RequestsError, Session

from llm4free.litagent import LitAgent

# Import base classes and utility structures
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

# --- DeepAI Client ---


class Completions(BaseCompletions):
    def __init__(self, client: "DeepAI"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 2049,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Union[Dict[str, Any], Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        payload: Dict[str, Any] = {
            "chat_style": self._client.chat_style,
            "chatHistory": json.dumps(messages),
            "model": model,
            "hacker_is_stinky": "very_stinky",
            "enabled_tools": json.dumps(self._client.enabled_tools),
        }

        # Add optional parameters if provided
        if max_tokens is not None and max_tokens > 0:
            payload["max_tokens"] = max_tokens

        if temperature is not None:
            payload["temperature"] = temperature

        if top_p is not None:
            payload["top_p"] = top_p

        # Add any additional parameters
        payload.update(kwargs)

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(
                request_id, created_time, model, payload, timeout=timeout, proxies=proxies
            )
        else:
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
        # DeepAI doesn't actually support streaming, but we'll implement it for compatibility
        # For now, just yield the non-stream response as a single chunk
        original_proxies = dict(cast(Any, self._client.session.proxies))
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))
        else:
            self._client.session.proxies.update(
                cast(Any, {})
            )  # Use update with empty dict instead of clear
        try:
            timeout_val = timeout if timeout is not None else self._client.timeout
            response = self._client.session.post(
                "https://api.deepai.org/hacking_is_a_serious_crime",
                data=payload,
                timeout=timeout_val,
            )

            if response.status_code != 200:
                raise IOError(
                    f"DeepAI request failed with status code {response.status_code}: {response.text}"
                )

            # Get response text
            content = response.text.strip()

            # Estimate token usage
            prompt_tokens = count_tokens(payload.get("chatHistory", ""))
            completion_tokens = count_tokens(content)
            total_tokens = prompt_tokens + completion_tokens

            # Create the delta object
            delta = ChoiceDelta(content=content, role="assistant", tool_calls=None)

            # Create the choice object
            choice = Choice(index=0, delta=delta, finish_reason="stop", logprobs=None)

            # Create the chunk object
            chunk = ChatCompletionChunk(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                system_fingerprint=None,
            )

            # Set usage directly on the chunk object
            chunk.usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": None,
            }

            yield chunk

        except RequestsError as e:
            print(f"Error during DeepAI stream request: {e}")
            raise IOError(f"DeepAI request failed: {e}") from e
        except Exception as e:
            print(f"Unexpected error during DeepAI stream request: {e}")
            raise IOError(f"DeepAI request failed: {e}") from e
        finally:
            self._client.session.proxies = cast(Any, original_proxies)

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        original_proxies = dict(cast(Any, self._client.session.proxies))
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))
        else:
            self._client.session.proxies.update(cast(Any, {}))
        try:
            timeout_val = timeout if timeout is not None else self._client.timeout
            response = self._client.session.post(
                "https://api.deepai.org/hacking_is_a_serious_crime",
                data=payload,
                timeout=timeout_val,
            )

            if response.status_code != 200:
                raise IOError(
                    f"DeepAI request failed with status code {response.status_code}: {response.text}"
                )

            # Get response text
            content = response.text.strip()

            # Estimate token usage
            prompt_tokens = count_tokens(payload.get("chatHistory", ""))
            completion_tokens = count_tokens(content)
            total_tokens = prompt_tokens + completion_tokens

            # Create the message object
            message = ChatCompletionMessage(role="assistant", content=content)

            # Create the choice object
            choice = Choice(index=0, message=message, finish_reason="stop")

            # Create the usage object
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            # Create the completion object
            completion = ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )
            return completion

        except RequestsError as e:
            print(f"Error during DeepAI non-stream request: {e}")
            raise IOError(f"DeepAI request failed: {e}") from e
        except Exception as e:
            print(f"Unexpected error during DeepAI non-stream request: {e}")
            raise IOError(f"DeepAI request failed: {e}") from e
        finally:
            self._client.session.proxies = cast(Any, original_proxies)


class Chat(BaseChat):
    def __init__(self, client: "DeepAI"):
        self.completions = Completions(client)


class DeepAI(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for DeepAI API.

    Usage:
        client = DeepAI()
        response = client.chat.completions.create(
            model="standard",
            messages=[{"role": "user", "content": "Hello!"}]
        )
    """

    required_auth = True
    AVAILABLE_MODELS = [
        # Standard Models
        "standard",
        "genius",
        "super-genius",
        # More Models - Free
        "deepseek-v3.2",
        "gemini-2.5-flash-lite",
        "gpt-4.1-nano",
        "gpt-oss-120b",
        "gemma-3-12b",
        "qwen3-30b",
        "gpt-5-nano",
        "llama-3.3-70b-instruct",
        "llama-3.1-8b-instant",
        "llama-4-scout",
        "gemma2-9b",
        # More Models - Pro
        "gpt-4o-mini",
        "gpt-4.1",
        "o4-mini",
        "o3",
        "gemini-3-pro",
        "claude-4.5-opus",
        "grok-4",
        "gpt-5-chat-latest",
        "gpt-5.2",
        "chatgpt-4o-latest",
    ]

    def __init__(
        self,
        api_key: str = "tryit-53926507126-2c8a2543c7b5638ca6b92b6e53ef2d2b",
        timeout: Optional[int] = 30,
        browser: str = "chrome",
        model: str = "standard",
        chat_style: str = "chat",
        enabled_tools: Optional[List[str]] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """
        Initialize the DeepAI client.

        Args:
            api_key: DeepAI API key
            timeout: Request timeout in seconds
            browser: Browser type for fingerprinting
            model: Default model to use
            chat_style: Chat style parameter
            enabled_tools: List of enabled tools
            proxies: Optional proxy configuration
        """
        super().__init__(proxies=proxies)

        # Defer model fetch to background to avoid blocking initialization
        self._start_background_model_fetch(api_key=api_key)

        # Initialize chat interface
        self.chat = Chat(self)

        self.timeout = timeout
        self.api_key = api_key
        self.model = model
        self.chat_style = chat_style
        self.enabled_tools = enabled_tools or ["image_generator"]

        # Use LitAgent for fingerprint if available, else fallback
        if LitAgent:
            agent = LitAgent()
            self.fingerprint = agent.generate_fingerprint(browser)
        else:
            self.fingerprint = {
                "accept": "*/*",
                "accept_language": "en-US,en;q=0.9",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "sec_ch_ua": "",
                "platform": "Windows",
            }

        # Use the fingerprint for headers
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "api-key": self.api_key,
            "Accept": self.fingerprint["accept"],
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": self.fingerprint["accept_language"],
            "User-Agent": self.fingerprint["user_agent"],
            "DNT": "1",
            "Sec-CH-UA": self.fingerprint["sec_ch_ua"]
            or '"Not/A)Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": f'"{self.fingerprint["platform"]}"',
        }

        # Create session cookies with unique identifiers
        self.cookies = {"__Host-session": uuid.uuid4().hex, "__cf_bm": uuid.uuid4().hex}

        # Set consistent headers for the scraper session
        self.session = Session()
        for header, value in self.headers.items():
            self.session.headers.update({header: value})

        # Set cookies
        self.session.cookies.update(self.cookies)

    def refresh_identity(self, browser: Optional[str] = None, impersonate: str = "chrome120"):
        """Refreshes the browser identity fingerprint and curl_cffi session."""
        browser = browser or self.fingerprint.get("browser_type", "chrome")
        if LitAgent:
            self.fingerprint = LitAgent().generate_fingerprint(browser)
        self.session = Session(impersonate=cast(Any, impersonate))
        # Update headers with new fingerprint
        self.headers.update(
            {
                "Accept": self.fingerprint["accept"],
                "Accept-Language": self.fingerprint["accept_language"],
                "Sec-CH-UA": self.fingerprint["sec_ch_ua"] or self.headers["Sec-CH-UA"],
                "Sec-CH-UA-Platform": f'"{self.fingerprint["platform"]}"',
                "User-Agent": self.fingerprint["user_agent"],
            }
        )

        # Update session headers
        for header, value in self.headers.items():
            self.session.headers.update({header: value})

        # Generate new cookies
        self.cookies = {"__Host-session": uuid.uuid4().hex, "__cf_bm": uuid.uuid4().hex}
        self.session.cookies.update(self.cookies)

        return self.fingerprint

    @classmethod
    def get_models(cls, api_key: Optional[str] = None):
        """Fetch available models from DeepAI API.

        Args:
            api_key (str, optional): DeepAI API key. If not provided, returns default models.

        Returns:
            list: List of available model IDs
        """
        if not api_key:
            return [
                "standard",
                "genius",
                "online",
                "supergenius",
                "onlinegenius",
                "deepseek-v3.2",
                "gemini-2.5-flash-lite",
                "qwen3-30b-a3b",
                "gpt-5-nano",
                "gpt-oss-120b",
                "gpt-5-chat-latest",
                "claude-opus-4-1",
                "llama-4-scout",
                "claude-4.5-sonnet",
                "deepseek-v3.1-terminus",
                "llama-3.3-70b-instruct",
                "grok-4",
                "claude-sonnet-4",
                "qwen3-coder",
                "gpt-5",
                "kimi-k2-0905",
                "claude-opus-4",
                "gpt-5-mini",
                "gemini-2.5-pro",
                "grok-code-fast-1",
                "gpt-4.1",
            ]

        try:
            # Use a temporary session for this class method
            from curl_cffi.requests import Session

            Session()

            # Note: DeepAI doesn't have a standard models endpoint, so we'll use a default list
            # If DeepAI has a models endpoint, you would call it here
            # For now, we'll return the default list as there's no known models endpoint
            return [
                "standard",
                "genius",
                "online",
                "supergenius",
                "onlinegenius",
                "deepseek-v3.2",
                "gemini-2.5-flash-lite",
                "qwen3-30b-a3b",
                "gpt-5-nano",
                "gpt-oss-120b",
                "gpt-5-chat-latest",
                "claude-opus-4-1",
                "llama-4-scout",
                "claude-4.5-sonnet",
                "deepseek-v3.1-terminus",
                "llama-3.3-70b-instruct",
                "grok-4",
                "claude-sonnet-4",
                "qwen3-coder",
                "gpt-5",
                "kimi-k2-0905",
                "claude-opus-4",
                "gpt-5-mini",
                "gemini-2.5-pro",
                "grok-code-fast-1",
                "gpt-4.1",
            ]

        except Exception:
            # Return default models list if fetching fails
            return [
                "standard",
                "genius",
                "online",
                "supergenius",
                "onlinegenius",
                "deepseek-v3.2",
                "gemini-2.5-flash-lite",
                "qwen3-30b-a3b",
                "gpt-5-nano",
                "gpt-oss-120b",
                "gpt-5-chat-latest",
                "claude-opus-4-1",
                "llama-4-scout",
                "claude-4.5-sonnet",
                "deepseek-v3.1-terminus",
                "llama-3.3-70b-instruct",
                "grok-4",
                "claude-sonnet-4",
                "qwen3-coder",
                "gpt-5",
                "kimi-k2-0905",
                "claude-opus-4",
                "gpt-5-mini",
                "gemini-2.5-pro",
                "grok-code-fast-1",
                "gpt-4.1",
            ]

    @classmethod
    def update_available_models(cls, api_key=None):
        """Update the available models list from DeepAI API"""
        try:
            models = cls.get_models(api_key)
            if models and len(models) > 0:
                cls.AVAILABLE_MODELS = models
        except Exception:
            # Fallback to default models list if fetching fails
            pass

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    client = DeepAI()
    response = client.chat.completions.create(
        model="standard", messages=[{"role": "user", "content": "Hello!"}], stream=True
    )
    if isinstance(response, ChatCompletion):
        if not isinstance(response, Generator):
            message = response.choices[0].message
            if message and message.content:
                print(message.content)
    else:
        for chunk in cast(Generator[ChatCompletionChunk, None, None], response):
            if chunk.choices[0].delta and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="")
