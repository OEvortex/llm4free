import re
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

from llm4free.browser_requests._http.compat import Session

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
)

# --- WiseCat Client ---


class Completions(BaseCompletions):
    def __init__(self, client: "WiseCat"):
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
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        # Prepare the payload for WiseCat API
        payload = {
            "id": "ephemeral",
            "messages": messages,
            "selectedChatModel": self._client.convert_model_name(model),
        }

        # # Add optional parameters if provided
        # if max_tokens is not None and max_tokens > 0:
        #     payload["max_tokens"] = max_tokens

        # if temperature is not None:
        #     payload["temperature"] = temperature

        # if top_p is not None:
        #     payload["top_p"] = top_p

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
        try:
            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=self._client.timeout,
                impersonate="chrome120",
            )

            # Handle non-200 responses
            if response.status_code != 200:
                raise IOError(
                    f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                )

            # Track token usage across chunks
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

            # Estimate prompt tokens based on message length
            for msg in payload.get("messages", []):
                prompt_tokens += count_tokens(msg.get("content", ""))

            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode("utf-8").strip()

                    # Parse content lines (format: 0:"content")
                    content_match = re.match(r'^0:"(.*)"$', decoded_line)
                    if content_match:
                        content = content_match.group(1)
                        content = self._client.format_text(content)

                        # Update token counts
                        completion_tokens += 1
                        total_tokens = prompt_tokens + completion_tokens

                        # Create the delta object
                        delta = ChoiceDelta(content=content, role="assistant", tool_calls=None)

                        # Create the choice object
                        choice = Choice(index=0, delta=delta, finish_reason=None, logprobs=None)

                        # Create the chunk object
                        chunk = ChatCompletionChunk(
                            id=request_id,
                            choices=[choice],
                            created=created_time,
                            model=model,
                            system_fingerprint=None,
                        )

                        yield chunk
                        continue

                    # Parse usage lines (format: e:{...} or d:{...})
                    usage_match = re.match(r"^[ed]:(\{.*\})$", decoded_line)
                    if usage_match:
                        try:
                            import json

                            usage_data = json.loads(usage_match.group(1))
                            if "usage" in usage_data:
                                prompt_tokens = usage_data["usage"].get(
                                    "promptTokens", prompt_tokens
                                )
                                completion_tokens = usage_data["usage"].get(
                                    "completionTokens", completion_tokens
                                )
                                total_tokens = prompt_tokens + completion_tokens
                        except Exception:
                            pass

            # Final chunk with finish_reason="stop"
            delta = ChoiceDelta(content=None, role=None, tool_calls=None)
            choice = Choice(index=0, delta=delta, finish_reason="stop", logprobs=None)
            chunk = ChatCompletionChunk(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                system_fingerprint=None,
            )

            if hasattr(chunk, "model_dump"):
                chunk_dict = chunk.model_dump(exclude_none=True)
            else:
                chunk_dict = chunk.dict(exclude_none=True)
            chunk_dict["usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }

            yield chunk

        except Exception as e:
            raise IOError(f"WiseCat stream request failed: {e}") from e

    def _create_non_stream(
        self, request_id: str, created_time: int, model: str, payload: Dict[str, Any]
    ) -> ChatCompletion:
        try:
            # For non-streaming, we still use streaming internally to collect the full response
            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=self._client.timeout,
                impersonate="chrome120",
            )

            # Handle non-200 responses
            if response.status_code != 200:
                raise IOError(
                    f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                )

            # Collect the full response and usage info
            full_text = ""
            prompt_tokens = 0
            completion_tokens = 0

            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode("utf-8").strip()

                    # Parse content lines
                    content_match = re.match(r'^0:"(.*)"$', decoded_line)
                    if content_match:
                        full_text += content_match.group(1)
                        continue

                    # Parse usage lines
                    usage_match = re.match(r"^[ed]:(\{.*\})$", decoded_line)
                    if usage_match:
                        try:
                            import json

                            usage_data = json.loads(usage_match.group(1))
                            if "usage" in usage_data:
                                prompt_tokens = usage_data["usage"].get(
                                    "promptTokens", prompt_tokens
                                )
                                completion_tokens = usage_data["usage"].get(
                                    "completionTokens", completion_tokens
                                )
                        except Exception:
                            pass

            # Format the text
            full_text = self._client.format_text(full_text)

            # Calculate total tokens
            total_tokens = prompt_tokens + completion_tokens

            # Create the message object
            message = ChatCompletionMessage(role="assistant", content=full_text)

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

        except Exception as e:
            raise IOError(f"WiseCat request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "WiseCat"):
        self.completions = Completions(client)


class WiseCat(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for WiseCat API.

    Usage:
        client = WiseCat()
        response = client.chat.completions.create(
            model="chat-model-large",
            messages=[{"role": "user", "content": "Hello!"}]
        )
    """

    required_auth = False
    _base_models = ["chat-model-small"]
    # Create AVAILABLE_MODELS as a list with the format "WiseCat/model"
    AVAILABLE_MODELS = [f"WiseCat/{model}" for model in _base_models]
    # Create a mapping dictionary for internal use
    _model_mapping = {model: f"WiseCat/{model}" for model in _base_models}

    def __init__(self, timeout: Optional[int] = None, browser: str = "chrome"):
        """
        Initialize the WiseCat client.

        Args:
            timeout: Request timeout in seconds (None for no timeout)
            browser: Browser to emulate in user agent
        """
        self.timeout = timeout
        self.api_endpoint = "https://wise-cat-groq.vercel.app/api/chat"
        self.session = Session()

        # Initialize LitAgent for user agent generation
        agent = LitAgent()
        self.fingerprint = agent.generate_fingerprint(browser)

        # Use the fingerprint for headers
        self.headers = self.fingerprint

        self.session.headers.update(self.headers)

        # Initialize the chat interface
        self.chat = Chat(self)

    def format_text(self, text: str) -> str:
        """
        Format text by replacing escaped newlines with actual newlines.

        Args:
            text: Text to format

        Returns:
            Formatted text
        """
        try:
            # Handle common escape sequences
            text = text.replace("\\n", "\n")
            text = text.replace("\\t", "\t")
            text = text.replace('\\"', '"')
            text = text.replace("\\\\", "\\")

            # Remove timing information like (0.3s) or (125ms)
            text = re.sub(r"\(\d+\.?\d*s\)", "", text)
            text = re.sub(r"\(\d+\.?\d*ms\)", "", text)

            return text.strip()
        except Exception:
            return text

    def convert_model_name(self, model: str) -> str:
        """
        Convert model names to ones supported by WiseCat. Accepts both 'WiseCat/model' and raw model names.
        """
        if model.startswith("WiseCat/"):
            model_raw = model.replace("WiseCat/", "", 1)
        else:
            model_raw = model
        if f"WiseCat/{model_raw}" in self.AVAILABLE_MODELS:
            return model_raw
        print(f"Warning: Unknown model '{model}'. Using 'chat-model-small' instead.")
        return self._base_models[0]  # Default to the first model in _base_models

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    # Test the provider
    client = WiseCat()
    response = client.chat.completions.create(
        model="chat-model-small",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! How are you today?"},
        ],
    )
    if isinstance(response, ChatCompletion):
        if response.choices[0].message and response.choices[0].message.content:
            print(response.choices[0].message.content)
