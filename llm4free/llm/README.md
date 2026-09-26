<div align="center">
  <a href="https://github.com/OEvortex/llm4free">
    <img src="https://img.shields.io/badge/LLM4Free-OpenAI%20Compatible%20Providers-4285F4?style=for-the-badge&logo=openai&logoColor=white" alt="LLM4Free OpenAI Compatible Providers">
  </a>
  <br/>
  <h1>LLM4Free OpenAI-Compatible Providers</h1>
  <p><strong>Seamlessly integrate with various AI providers using OpenAI-compatible interfaces</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.7+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.7+">
    <img src="https://img.shields.io/badge/License-Apache--2.0-blue?style=flat-square" alt="License: Apache-2.0">
    <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome">
  </p>

  <p>
    Access multiple AI providers through a standardized OpenAI-compatible interface, making it easy to switch between providers without changing your code.
  </p>
</div>

## 🚀 Overview

The LLM4Free OpenAI-Compatible Providers module offers a standardized way to interact with various AI providers using the familiar OpenAI API structure. This makes it easy to:

- Use the same code structure across different AI providers
- Switch between providers without major code changes
- Leverage the OpenAI ecosystem of tools and libraries with alternative AI providers

## ⚙️ Available Providers

Currently, the following providers are implemented with OpenAI-compatible interfaces:

- GLM (z.ai) — anonymous GLM models with streaming and reasoning
- DeepInfra
- WiseCat
- ExaAI
- TypeGPT
- YEPCHAT
- HeckAI
- IBM
- SonusAI
- Ayle
- Netwrck
- StandardInput
- Writecream
- toolbaz
- UncovrAI
- OPKFC
- TextPollinations
- E2B
- MultiChatAI
- AI4Chat
- MCPCore
- TypefullyAI
- Flowith
- ChatSandbox
- Cloudflare
- NEMOTRON
- BLACKBOXAI
- Copilot
- TwoAI
- oivscode
- Qwen3
- TogetherAI
- PiAI
- FalconH1
- XenAI
- MonoChat
- Friendli
- MiniMax
- QodoAI
- Kimi
- GptOss

## GLM (z.ai)

GLM provides anonymous access to the live z.ai model catalog through the standard OpenAI-compatible interface. No API key is required.

```python
from llm4free.llm import GLM

client = GLM(timeout=60)
response = client.chat.completions.create(
    model="GLM-5.3-Flash",
    messages=[{"role": "user", "content": "Explain Python generators"}],
    reasoning_effort="none",
)
print(response.choices[0].message.content)
```

Streaming, reasoning output, and web search are supported:

```python
for chunk in client.chat.completions.create(
    model="GLM-5.3",
    messages=[{"role": "user", "content": "What changed in Python 3.13?"}],
    stream=True,
    reasoning_effort="high",
    web_search=True,
):
    delta = chunk.choices[0].delta
    if delta.reasoning_content:
        print(delta.reasoning_content, end="", flush=True)
    if delta.content:
        print(delta.content, end="", flush=True)
```

The provider first requests normally. If z.ai returns `FRONTEND_CAPTCHA_REQUIRED`, captcha recovery launches the existing `agent-browser` backend automatically. Install it if it is not already available:

```bash
npm i -g agent-browser
agent-browser install
```

> [!WARNING]
> Anonymous GLM completion currently depends on z.ai's Aliyun captcha challenge. The protocol and retry flow are implemented, but the live challenge may reject automated/headless browser fingerprints with `verifyCode: F001`. In that case the provider raises a clear captcha error instead of returning an empty completion. The upstream gpt4free GLM snapshot currently has a separate CDP serialization failure before it can complete the same challenge.

## 💻 Usage Examples

Here are examples of how to use the OpenAI-compatible providers in your code.

### Basic Usage with DeepInfra

```python
from llm4free.client import DeepInfra

# Initialize the client
client = DeepInfra()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ],
    temperature=0.7,
    max_tokens=500
)

# Print the response
print(response.choices[0].message.content)
```

### Basic Usage with Glider

```python
from llm4free.client import Glider

# Initialize the client
client = Glider()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="chat-llama-3-1-70b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ],
    max_tokens=500
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming Responses (Example with DeepInfra)

```python
from llm4free.client import DeepInfra

# Initialize the client
client = DeepInfra()

# Create a streaming completion
stream = client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True,
    temperature=0.7
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Streaming with Glider

```python
from llm4free.client import Glider

# Initialize the client
client = Glider()

# Create a streaming completion
stream = client.chat.completions.create(
    model="chat-llama-3-1-70b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```


### Basic Usage with WiseCat

```python
from llm4free.client import WiseCat

# Initialize the client
client = WiseCat()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="chat-model-small",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming with WiseCat

```python
from llm4free.client import WiseCat

# Initialize the client
client = WiseCat()

# Create a streaming completion
stream = client.chat.completions.create(
    model="chat-model-small",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Basic Usage with ExaAI

```python
from llm4free.client import ExaAI

# Initialize the client
client = ExaAI()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="O3-Mini",
    messages=[
        # Note: ExaAI does not support system messages (they will be removed)
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you today?"},
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Basic Usage with HeckAI

```python
from llm4free.client import HeckAI

# Initialize the client
client = HeckAI(language="English")

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="google/gemini-2.0-flash-001",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming with HeckAI

```python
from llm4free.client import HeckAI

# Initialize the client
client = HeckAI()

# Create a streaming completion
stream = client.chat.completions.create(
    model="google/gemini-2.0-flash-001",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Basic Usage with IBM

```python
from llm4free.llm.ibm import IBM

# Initialize the client
client = IBM(timeout=30)

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="granite-chat",
    messages=[
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming with IBM

```python
from llm4free.llm.ibm import IBM

# Initialize the client
client = IBM()

# Create a streaming completion
stream = client.chat.completions.create(
    model="granite-chat",
    messages=[
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Using Different IBM Granite Models

```python
from llm4free.llm.ibm import IBM

# Initialize the client
client = IBM()

# Get available models
print("Available models:", client.models.list())

# Use granite-chat model
response = client.chat.completions.create(
    model="granite-chat",
    messages=[
        {"role": "user", "content": "Explain quantum computing in simple terms."}
    ]
)
print("Granite Chat:", response.choices[0].message.content)

# Use granite-search model (optimized for search tasks)
search_response = client.chat.completions.create(
    model="granite-search",
    messages=[
        {"role": "user", "content": "What are the best practices for Python development?"}
    ]
)
print("Granite Search:", search_response.choices[0].message.content)
```

### Streaming with ExaAI

```python
from llm4free.client import ExaAI

# Initialize the client
client = ExaAI()

# Create a streaming completion
stream = client.chat.completions.create(
    model="O3-Mini",
    messages=[
        # Note: ExaAI does not support system messages (they will be removed)
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you today?"},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Basic Usage with TypeGPT

```python
from llm4free.client import TypeGPT

# Initialize the client
client = TypeGPT()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="chatgpt-4o-latest",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming with TypeGPT

```python
from llm4free.client import TypeGPT

# Initialize the client
client = TypeGPT()

# Create a streaming completion
stream = client.chat.completions.create(
    model="chatgpt-4o-latest",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Basic Usage with FreeAIChat

```python
from llm4free.client import FreeAIChat

# Initialize the client
client = FreeAIChat()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="GPT 4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming with FreeAIChat

```python
from llm4free.client import FreeAIChat

# Initialize the client
client = FreeAIChat()

# Create a streaming completion
stream = client.chat.completions.create(
    model="GPT 4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Basic Usage with YEPCHAT

```python
from llm4free.client import YEPCHAT

# Initialize the client
client = YEPCHAT()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="DeepSeek-R1-Distill-Qwen-32B",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ],
    temperature=0.7
)

# Print the response
print(response.choices[0].message.content)
```

### Basic Usage with SonusAI

```python
from llm4free.client import SonusAI

# Initialize the client
client = SonusAI()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="pro",  # Choose from 'pro', 'air', or 'mini'
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ],
    reasoning=True  # Optional: Enable reasoning mode
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming with YEPCHAT

```python
from llm4free.client import YEPCHAT

# Initialize the client
client = YEPCHAT()

# Create a streaming completion
stream = client.chat.completions.create(
    model="Mixtral-8x7B-Instruct-v0.1",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Streaming with SonusAI

```python
from llm4free.client import SonusAI

# Initialize the client
client = SonusAI(timeout=60)

# Create a streaming completion
stream = client.chat.completions.create(
    model="air",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Basic Usage with Ayle

```python
from llm4free.client import Ayle

# Initialize the client
client = Ayle()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="gemini-2.5-flash",  # Choose from many available models
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Using Different Ayle Models

```python
from llm4free.client import Ayle

# Initialize the client
client = Ayle(timeout=60)

# Use a Gemini model
gemini_response = client.chat.completions.create(
    model="gemini-2.0-flash",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in simple terms."}
    ]
)

# Use a Groq model
groq_response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(gemini_response.choices[0].message.content)
```

### Streaming with Netwrck

```python
from llm4free.client import Netwrck

# Initialize the client
client = Netwrck(timeout=60)

# Create a streaming completion
stream = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short poem about programming."}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

### Basic Usage with StandardInput

```python
from llm4free.client import StandardInput

# Initialize the client
client = StandardInput()

# Create a completion (non-streaming)
response = client.chat.completions.create(
    model="standard-quick",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."}
    ]
)

# Print the response
print(response.choices[0].message.content)
```

### Streaming with StandardInput

```python
from llm4free.client import StandardInput

# Initialize the client
client = StandardInput()

# Create a streaming completion
stream = client.chat.completions.create(
    model="standard-reasoning",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Count from 1 to 5."}
    ],
    stream=True,
    enable_reasoning=True  # Enable reasoning capabilities
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()  # Add a newline at the end
```

## 🔄 Response Format

All providers return responses that mimic the OpenAI API structure, ensuring compatibility with tools built for OpenAI.

### 📝 Non-streaming Response

```json
{
  "id": "chatcmpl-123abc",
  "object": "chat.completion",
  "created": 1677858242,
  "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
  "usage": {
    "prompt_tokens": 13,
    "completion_tokens": 7,
    "total_tokens": 20
  },
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "This is a response from the model."
      },
      "finish_reason": "stop",
      "index": 0
    }
  ]
}
```

### 📱 Streaming Response Chunks

```json
{
  "id": "chatcmpl-123abc",
  "object": "chat.completion.chunk",
  "created": 1677858242,
  "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
  "choices": [
    {
      "delta": {
        "content": "This "
      },
      "finish_reason": null,
      "index": 0
    }
  ]
}
```

## 🧩 Architecture

The OpenAI-compatible providers are built on a modular architecture:

- `base.py`: Contains abstract base classes that define the OpenAI-compatible interface
- `utils.py`: Provides data structures that mimic OpenAI's response format
- Provider-specific implementations (e.g., `deepinfra.py`): Implement the abstract interfaces for specific providers

This architecture makes it easy to add new providers while maintaining a consistent interface.

## 📝 Notes

- Some providers may require API keys for full functionality
- Not all OpenAI features are supported by all providers
- Response formats are standardized to match OpenAI's format, but the underlying content depends on the specific provider and model

## 🤝 Contributing

Want to add a new OpenAI-compatible provider? Follow these steps:

1.  Create a new file in the `llm4free/llm/` directory
2.  Implement the `OpenAICompatibleProvider` interface
3.  Add appropriate tests
4.  Update this README with information about the new provider

## 📚 Related Documentation

- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [DeepInfra Documentation](https://deepinfra.com/docs)
- [WiseCat Website](https://wise-cat-groq.vercel.app/)
- [ExaAI Website](https://o3minichat.exa.ai/)
- [Sambanova Website](https://sambanova.ai/)
- [DeepInfra Website](https://deepinfra.com/)
- [Yep.com Website](https://yep.com/)
- [HeckAI Website](https://heck.ai/)
- [SonusAI Website](https://chat.sonus.ai/)
- [Ayle Website](https://ayle.chat/)
- [Netwrck Website](https://netwrck.com/)
- [StandardInput Website](https://chat.standard-input.com/)

<div align="center">
  <a href="https://t.me/OEvortexAI"><img alt="Telegram Group" src="https://img.shields.io/badge/Telegram%20Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"></a>
  <a href="https://buymeacoffee.com/oevortex"><img alt="Buy Me A Coffee" src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black"></a>
</div>
