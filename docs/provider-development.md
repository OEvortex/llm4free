# Provider Development Guide

> **Last updated:** 2026-01-24  
> **Type:** Developer Guide  
> **Audience:** Contributors, advanced users

## Overview

This guide teaches you how to create custom providers for LLM4Free, enabling integration with new AI services or local models.

### Two Provider Types

**Type 1: Native Providers** — Direct implementation from scratch (`llm4free.AIbase.Provider`), used for services with unique APIs. These are only usable via direct import; the unified `Client` and HTTP server do not discover them.

**Type 2: OpenAI-Compatible Providers** — Subclasses of `llm4free.llm.base.OpenAICompatibleProvider`. These are what `Client` and the server discover automatically.

This guide covers both. Provider implementations live in `llm4free/llm/` (authenticated ones in `llm4free/llm/Auth/`); the legacy `llm4free/Provider/` directory no longer exists.

---

## Architecture Overview

### Provider Hierarchy

```
llm4free.AIbase.Provider (ABC, native ask/chat/get_message interface)
└── Native Implementation (direct-import only)

llm4free.llm.base.OpenAICompatibleProvider (ABC, chat.completions.create)
└── Your Provider Implementation (discovered by Client and the server)
```

### Key Concepts

- **Provider** — A class that translates user prompts into API calls
- **Model** — The actual AI model (e.g., "gpt-4", "llama-3.1-70b")
- **Session** — HTTP client for API communication (uses `curl_cffi` for reliability)
- **Conversation** — Optional context preservation across turns

---

## Native Provider Implementation

### Step 1: Create the Provider File

Create `llm4free/llm/your_provider.py`:

```python
from typing import Any, Dict, Generator, Optional, Union

from curl_cffi.requests import Session
from llm4free.AIbase import Provider, Response
from llm4free import exceptions


class YourProvider(Provider):
    """
    A provider for Your AI Service.
    
    This provider integrates with the YourService API.
    """
    
    required_auth = True  # Set False if no API key needed
    
    def __init__(
        self,
        api_key: str,
        model: str = "default-model",
        is_conversation: bool = False,
        timeout: int = 30,
    ):
        """
        Initialize the provider.
        
        Args:
            api_key (str): Your API key
            model (str): Model to use. Default: default-model
            is_conversation (bool): Track conversation history
            timeout (int): Request timeout in seconds. Default: 30
        """
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.session = Session()
        
        # Conversation tracking
        self.conversation_id = None if is_conversation else None
        self.messages = []
```

### Step 2: Implement Required Methods

```python
    def ask(
        self,
        prompt: str,
        stream: bool = False,
        raw: bool = False,
        **kwargs: Any,
    ) -> Response:
        """
        Send a prompt and get raw response.
        """
        self.last_response = {}
        
        # Build API request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }
        
        try:
            # Make API request
            response = self.session.post(
                "https://api.yourservice.com/v1/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            
            if response.status_code != 200:
                raise exceptions.APIConnectionError(
                    f"API error: {response.status_code} - {response.text}"
                )
            
            data = response.json()
            self.last_response = data
            
            if stream:
                return self._stream_response(data)
            else:
                return data
                
        except Exception as e:
            raise exceptions.ProviderException(f"Failed to get response: {str(e)}")
    
    def _stream_response(self, response: Dict) -> Generator[str, None, None]:
        """Handle streaming responses."""
        if "choices" in response:
            for choice in response["choices"]:
                yield choice.get("text", "")
    
    def chat(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[str, Generator[str, None, None]]:
        """
        Send a prompt and get a clean message response.
        """
        response = self.ask(prompt, stream=stream, **kwargs)
        
        if stream:
            # For streaming, extract text from each chunk
            def extract_stream():
                for chunk in response:
                    yield self.get_message({"text": chunk})
            return extract_stream()
        else:
            return self.get_message(response)
    
    def get_message(self, response: Response) -> str:
        """
        Extract message text from response.
        """
        if isinstance(response, dict):
            # Adjust based on your API's response structure
            if "choices" in response:
                return response["choices"][0].get("text", "")
            elif "message" in response:
                return response["message"].get("content", "")
        
        return str(response)
```

> [!NOTE]
> `Provider.chat()` already implements a tool-calling loop, so a native provider
> gets tool support for free. `ask()` and `get_message()` are the only methods
> you must implement. Native providers are not discovered by `Client` or the
> server; use direct imports (or subclass `OpenAICompatibleProvider` instead).

### Step 3: Export Your Provider

Edit `llm4free/llm/__init__.py` and add:

```python
from llm4free.llm.your_provider import YourProvider

# At the end of the __all__ export list
__all__ = [
    # ... existing providers ...
    "YourProvider",
]
```

This makes `from llm4free.llm import YourProvider` work, but does **not** register
the provider with `Client` or the server (they only discover
`OpenAICompatibleProvider` subclasses).

### Step 4: Add Unit Tests

Create `tests/test_your_provider.py` (the repository keeps flat test modules, e.g.
`tests/test_tool_calling.py`):

```python
import unittest
from unittest.mock import MagicMock, patch

from llm4free.llm.your_provider import YourProvider


class TestYourProvider(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.api_key = "test-api-key"
        self.provider = YourProvider(api_key=self.api_key)
    
    @patch('llm4free.llm.your_provider.Session.post')
    def test_chat(self, mock_post):
        """Test basic chat functionality."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"text": "Hello, World!"}]
        }
        mock_post.return_value = mock_response
        
        # Test chat
        response = self.provider.chat("Hello")
        self.assertEqual(response, "Hello, World!")
    
    @patch('llm4free.llm.your_provider.Session.post')
    def test_streaming(self, mock_post):
        """Test streaming response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"text": "Chunk 1"}]
        }
        mock_post.return_value = mock_response
        
        # Collect streamed response
        response = self.provider.chat("Test", stream=True)
        chunks = list(response)
        self.assertTrue(len(chunks) > 0)


if __name__ == "__main__":
    unittest.main()
```

---

## OpenAI-Compatible Provider Implementation

For services that use OpenAI-like APIs:

`OpenAICompatibleProvider` requires two things:

1. A `models` property returning a `SimpleModelList` (or `ModelList`).
2. A `chat` attribute whose `.completions.create(...)` implements the OpenAI
   signature. The base class calls `super().__init__()` to create
   `self.session`, `self.proxies`, and `self.available_tools`.

`base_url`, `default_model`, and `default_timeout` are conventions used by many
providers, not abstract members. `AVAILABLE_MODELS` and `get_models()` are
optional, but they let the background model fetcher populate the registry and
let the server validate model names.

### Step 1: Define the Completions Class

```python
import time
import uuid
from typing import Any, Dict, List, Optional

from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
)
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionMessage,
    Choice,
    CompletionUsage,
)


class Completions(BaseCompletions):
    def __init__(self, client: "YourOpenAIProvider"):
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
        tools=None,
        tool_choice=None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        if stream:
            return self._stream(model, messages, timeout)

        data = self._request(model, messages, timeout)
        return ChatCompletion(
            id=f"chatcmpl-{uuid.uuid4().hex}",
            created=int(time.time()),
            model=model,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=data["choices"][0]["message"]["content"],
                    ),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=0, completion_tokens=0, total_tokens=0
            ),
        )

    def _request(self, model: str, messages: List[Dict[str, Any]], timeout):
        response = self._client.session.post(
            "https://api.yourservice.com/v1/chat/completions",
            json={"model": model, "messages": messages},
            headers={"Authorization": f"Bearer {self._client.api_key}"},
            timeout=timeout or self._client.timeout,
        )
        response.raise_for_status()
        return response.json()
```

> [!IMPORTANT]
> When `stream=True`, `create()` must return a generator of
> `ChatCompletionChunk` objects, not a `ChatCompletion`. Models are typed with
> pydantic: `ChatCompletion.choices` must contain `Choice` instances, and
> `usage` must be a `CompletionUsage` with all three token counts.

### Step 2: Define the Provider Class

```python
class Chat(BaseChat):
    def __init__(self, client: "YourOpenAIProvider"):
        self.completions = Completions(client)


class YourOpenAIProvider(OpenAICompatibleProvider):
    required_auth = True          # False makes it eligible for the HTTP server
    AVAILABLE_MODELS = ["model-1", "model-2"]
    default_model = "model-1"

    def __init__(self, api_key: str, timeout: int = 30, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self.api_key = api_key
        self.timeout = timeout
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        return cls.AVAILABLE_MODELS
```

Existing providers such as
[`llm4free/llm/akashgpt.py`](../llm4free/llm/akashgpt.py) are compact reference
implementations of this pattern.

### Step 3: Make It Discoverable

- **Python `Client`:** add the class to `llm4free/llm/__init__.py`; `Client`
  discovers every `OpenAICompatibleProvider` subclass exported there. Providers
  with `required_auth = True` are skipped unless you pass an `api_key` and
  `drop_auth_providers=False`.
- **HTTP server:** same export. The server registers only providers whose
  `required_auth` is `False`, and indexes their `AVAILABLE_MODELS` as
  `ProviderName/model`.

---

## Best Practices

### 1. Error Handling

```python
def ask(self, prompt: str, **kwargs) -> Response:
    """Handle errors gracefully."""
    try:
        # API call
        response = self.session.post(...)
    except TimeoutError:
        raise exceptions.APITimeoutError("Request timed out")
    except ConnectionError:
        raise exceptions.APIConnectionError("Connection failed")
    except Exception as e:
        raise exceptions.ProviderException(f"Unexpected error: {str(e)}")
```

### 2. Rate Limiting

```python
import time

def chat(self, prompt: str, **kwargs) -> str:
    """Add rate limiting support."""
    # Check if we need to wait
    if self.last_request_time:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
    
    self.last_request_time = time.time()
    # ... make request
```

### 3. Response Validation

```python
def get_message(self, response: Response) -> str:
    """Validate response format."""
    if not isinstance(response, dict):
        raise ValueError(f"Expected dict, got {type(response)}")
    
    if "choices" not in response:
        raise ValueError("No choices in response")
    
    if not response["choices"]:
        raise ValueError("Empty choices list")
    
    return response["choices"][0].get("message", {}).get("content", "")
```

### 4. Type Hints

```python
from typing import Any, Dict, Generator, Optional, Union

def chat(
    self,
    prompt: str,
    stream: bool = False,
    **kwargs: Any,
) -> Union[str, Generator[str, None, None]]:
    """Always use type hints."""
    pass
```

### 5. Documentation

Every provider should have docstrings:

```python
class MyProvider(Provider):
    """
    Brief description of provider.
    
    This provider uses [Service Name] API to generate responses.
    
    Required API Key:
        - Get from https://website.com/api-keys
        - Set via parameter or environment variable MY_SERVICE_API_KEY
    
    Attributes:
        api_key (str): Your API key
        model (str): Model to use
    
    Examples:
        >>> provider = MyProvider(api_key="sk-...")
        >>> response = provider.chat("Hello")
        >>> print(response)
    """
```

---

## Testing Checklist

- [ ] All methods raise appropriate exceptions
- [ ] Streaming works correctly
- [ ] Conversation history is maintained
- [ ] API key validation works
- [ ] Timeout handling is correct
- [ ] Error messages are clear
- [ ] Type hints are complete
- [ ] Tests pass: `pytest tests/`
- [ ] Linting passes: `ruff check .`
- [ ] Type checking passes: `ty check .`

---

## Deployment

### 1. Document Your Provider

Add an entry to [docs/api/providers.md](api/providers.md):

```markdown
### YourProvider

**Location:** `llm4free/llm/your_provider.py`

**Description:** Brief description of what it does

**Authentication:** API key required (`required_auth = True`)

**Models:** List available models

**Example:**
```python
from llm4free.llm import YourProvider
provider = YourProvider(api_key="your-key")
response = provider.chat.completions.create(
    model="model-1",
    messages=[{"role": "user", "content": "Hello"}],
)
```
```

### 2. Update Documentation

Add an example section to the getting-started guide if needed.

### 3. Create a PR

Follow the [Contributing Guidelines](contributing.md)

---

## Common Patterns

### Handling Different Response Formats

```python
def get_message(self, response: Response) -> str:
    """Handle multiple possible response formats."""
    if isinstance(response, str):
        return response
    
    if isinstance(response, dict):
        # Try multiple possible paths
        content = (
            response.get("message", {}).get("content")
            or response.get("choices", [{}])[0].get("message", {}).get("content")
            or response.get("text")
            or response.get("content")
        )
        
        if content:
            return str(content)
        
        raise ValueError(f"Could not extract message from: {response}")
    
    raise TypeError(f"Unexpected response type: {type(response)}")
```

### Implementing Conversation History

```python
def __init__(self, is_conversation: bool = True, **kwargs):
    super().__init__()
    self.is_conversation = is_conversation
    self.conversation_history = []

def chat(self, prompt: str, **kwargs) -> str:
    if self.is_conversation:
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": prompt
        })
    
    # Get response
    response = self.ask(prompt, **kwargs)
    message = self.get_message(response)
    
    if self.is_conversation:
        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": message
        })
    
    return message
```

---

## See Also

- [API Reference](api-reference.md) — Full API documentation
- [Contributing Guide](contributing.md) — How to contribute
- [Testing Guidelines](../AGENTS.md) — Testing standards
- [Provider List](api/providers.md) — All available providers
