import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi import CurlError

# Import curl_cffi for improved request handling
from curl_cffi.requests import Session

# Attempt to import LitAgent, fallback if not available
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
    format_prompt,
)


class Completions(BaseCompletions):
    def __init__(self, client: "IBM"):
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
        tools: Optional[List[Union[Any, Dict[str, Any]]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        formatted_prompt = format_prompt(
            messages, add_special_tokens=False, do_continue=True, include_system=True
        )

        if not formatted_prompt:
            raise ValueError("No valid prompt could be generated from messages")

        # Use count_tokens to estimate prompt tokens
        try:
            prompt_tokens = count_tokens(formatted_prompt)
        except Exception:
            # Fallback to simple estimation if tiktoken not available
            prompt_tokens = int(len(formatted_prompt.split()) * 1.3)

        now = datetime.now().isoformat()
        payload = {
            "agent_name": model,
            "input": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "content_type": "text/plain",
                            "content": formatted_prompt,
                            "content_encoding": "plain",
                            "role": "user",
                        }
                    ],
                    "created_at": now,
                    "completed_at": now,
                }
            ],
            "mode": "stream",
            "session_id": str(uuid.uuid4()),
        }

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(request_id, created_time, model, payload, prompt_tokens)
        else:
            return self._create_non_stream(request_id, created_time, model, payload, prompt_tokens)

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        prompt_tokens: int,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Stream chat completions using manual SSE parsing (no sanitize_stream)"""
        try:
            response = self._client.session.post(
                self._client.base_url,
                data=json.dumps(payload),
                stream=True,
                timeout=self._client.timeout,
                impersonate="chrome110",
            )

            if response.status_code in [401, 403]:
                # Token expired, refresh and retry once
                self._client.get_token()
                response = self._client.session.post(
                    self._client.base_url,
                    data=json.dumps(payload),
                    stream=True,
                    timeout=self._client.timeout,
                    impersonate="chrome110",
                )

            if response.status_code != 200:
                raise IOError(
                    f"IBM request failed with status code {response.status_code}: {response.text}"
                )

            # Track completion tokens
            completion_tokens = 0

            buffer = ""
            for chunk in response.iter_content(chunk_size=None):
                if not chunk:
                    continue

                # Decode bytes to string
                try:
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
                except UnicodeDecodeError:
                    continue

                buffer += chunk_str

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    # Parse SSE format: "data: {...}"
                    if line.startswith("data:"):
                        json_str = line[5:].strip()  # Remove "data:" prefix

                        # Skip [DONE] marker
                        if json_str == "[DONE]":
                            break

                        try:
                            # Parse JSON
                            data = json.loads(json_str)

                            # Extract content from IBM format
                            if data.get("type") == "message.part":
                                part = data.get("part", {})
                                content = part.get("content")

                                if content:
                                    completion_tokens += 1

                                    # Create the delta object
                                    delta = ChoiceDelta(content=content, role="assistant")

                                    # Create the choice object
                                    choice = Choice(index=0, delta=delta, finish_reason=None)

                                    # Create the chunk object
                                    chunk = ChatCompletionChunk(
                                        id=request_id,
                                        choices=[choice],
                                        created=created_time,
                                        model=model,
                                        system_fingerprint=None,
                                    )

                                    yield chunk

                        except json.JSONDecodeError:
                            # Skip malformed JSON lines
                            continue

            # Send final chunk with finish_reason
            final_delta = ChoiceDelta(content=None, role=None)
            final_choice = Choice(index=0, delta=final_delta, finish_reason="stop")
            final_chunk = ChatCompletionChunk(
                id=request_id,
                choices=[final_choice],
                created=created_time,
                model=model,
                system_fingerprint=None,
            )
            yield final_chunk

        except CurlError as e:
            print(f"Error during IBM stream request: {e}")
            raise IOError(f"IBM request failed: {e}") from e
        except Exception as e:
            print(f"Error processing IBM stream: {e}")
            raise

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        prompt_tokens: int,
    ) -> ChatCompletion:
        """Create non-streaming chat completion"""
        try:
            # Collect all content from stream
            accumulated_content = ""
            completion_tokens = 0

            for chunk in self._create_stream(
                request_id, created_time, model, payload, prompt_tokens
            ):
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    accumulated_content += chunk.choices[0].delta.content
                    completion_tokens += 1

            # Use count_tokens for more accurate completion token count
            try:
                completion_tokens = count_tokens(accumulated_content)
            except Exception:
                # Fallback if tiktoken not available
                pass

            # Create the message object
            message = ChatCompletionMessage(
                role="assistant", content=accumulated_content, tool_calls=None
            )

            # Create the choice object
            choice = Choice(index=0, message=message, finish_reason="stop")

            # Create usage object with proper token counts
            usage = CompletionUsage(
                prompt_tokens=int(prompt_tokens),
                completion_tokens=completion_tokens,
                total_tokens=int(prompt_tokens) + completion_tokens,
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

        except CurlError as e:
            print(f"Error during IBM non-stream request: {e}")
            raise IOError(f"IBM request failed: {e}") from e
        except Exception as e:
            print(f"Error processing IBM response: {e}")
            raise


class Chat(BaseChat):
    def __init__(self, client: "IBM"):
        self.completions = Completions(client)


class IBM(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for IBM Granite Playground API.
    Provides a familiar interface for interacting with IBM's Granite models.
    """

    required_auth = False  # No API key required for IBM Granite Playground
    AVAILABLE_MODELS = [
        "granite-reasoning-deep",
        "granite-reasoning-nothink",
        "granite-reasoning-light",
    ]

    def get_token(self) -> str:
        """Fetches a fresh dynamic Bearer token from the IBM UI auth endpoint."""
        auth_url = "https://www.ibm.com/granite/playground/api/v1/ui/auth"
        try:
            # Use the existing session to benefit from cookies/headers
            response = self.session.get(auth_url, timeout=self.timeout, impersonate="chrome110")
            if response.ok:
                data = response.json()
                token = data.get("token")
                if token:
                    self.headers["Authorization"] = f"Bearer {token}"
                    self.session.headers.update(self.headers)
                    return token
            raise IOError(f"Failed to fetch auth token: {response.status_code}")
        except Exception as e:
            raise IOError(f"Error fetching auth token: {str(e)}")

    def __init__(
        self, api_key: Optional[str] = None, timeout: Optional[int] = 30, browser: str = "chrome"
    ):
        """
        Initialize IBM client.

        Args:
            api_key: Not required for IBM Granite Playground (uses dynamic bearer token)
            timeout: Request timeout in seconds
            browser: Browser type for fingerprinting
        """
        self.timeout = timeout
        self.base_url = "https://d1eh1ubv87xmm5.cloudfront.net/granite/playground/api/v1/acp/runs"

        # Initialize curl_cffi Session
        self.session = Session()

        # Initialize LitAgent for browser fingerprinting
        try:
            agent = LitAgent()
            fingerprint = agent.generate_fingerprint(browser)

            self.headers = {
                "Accept": "text/event-stream",
                "Accept-Language": fingerprint.get("accept_language", "en-US,en;q=0.9"),
                "Authorization": "",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "Origin": "https://www.ibm.com",
                "Pragma": "no-cache",
                "Referer": "https://www.ibm.com/granite/playground",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "User-Agent": fingerprint.get("user_agent", ""),
                "Sec-CH-UA": fingerprint.get("sec_ch_ua", ""),
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": f'"{fingerprint.get("platform", "")}"',
            }
        except (NameError, Exception):
            # Fallback to basic headers if LitAgent is not available
            self.headers = {
                "Accept": "text/event-stream",
                "Accept-Language": "en-US,en;q=0.9",
                "Authorization": "",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "Origin": "https://www.ibm.com",
                "Pragma": "no-cache",
                "Referer": "https://www.ibm.com/granite/playground",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "User-Agent": LitAgent().random(),
                "Sec-CH-UA": '"Not)A;Brand";v="99", "Google Chrome";v="120", "Chromium";v="120"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
            }

        # Update session headers
        self.session.headers.update(self.headers)

        # Fetch initial token
        self.get_token()

        # Initialize chat interface
        self.chat = Chat(self)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None):
        """Get available models.

        Args:
            api_key: Not used for IBM (kept for compatibility)

        Returns:
            list: List of available model IDs
        """
        return cls.AVAILABLE_MODELS

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


# Example usage
if __name__ == "__main__":
    # Test the IBM client
    client = IBM()

    # Test streaming
    print("Testing streaming:")
    response = client.chat.completions.create(
        model="granite-reasoning-nothink",
        messages=[{"role": "user", "content": "Say 'Hello World' in one sentence"}],
        stream=True,
    )

    for chunk in response:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")

    # Test non-streaming
    print("Testing non-streaming:")
    response = client.chat.completions.create(
        model="granite-reasoning-nothink",
        messages=[{"role": "user", "content": "Say 'Hello' in one word"}],
        stream=False,
    )

    if isinstance(response, ChatCompletion):
        if response.choices[0].message and response.choices[0].message.content:
            print(response.choices[0].message.content)
