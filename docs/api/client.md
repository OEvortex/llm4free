# Client API Reference

## Unified Client

The `Client` class provides a unified interface for accessing multiple AI providers with automatic failover.

### Quick Start

```python
from llm4free import Client

client = Client()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

### Client Initialization

```python
from llm4free import Client

# Auto-detect available providers
client = Client()

# With specific API key
client = Client(api_key="your-key")

# With multiple provider keys
client = Client(api_keys_file="keys.json")
```

### Chat Completions

```python
# Basic completion
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"}
    ]
)

# With streaming
for chunk in client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write a poem"}],
    stream=True
):
    print(chunk.choices[0].delta.content or "", end="")

# With tool calling
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Weather in Paris?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    }]
)
```

### Available Methods

| Method | Description |
|--------|-------------|
| `client.chat.completions.create()` | Create chat completion |
| `client.models.list()` | List available models |
| `client.list_providers()` | List all providers |

## Provider Classes

### Direct Provider Usage

```python
from llm4free import ChatGPT, AI4Chat, HeckAI

# ChatGPT (requires API key)
ai = ChatGPT(api_key="sk-...")
response = ai.chat("Hello!")

# AI4Chat (free API key from https://www.ai4chat.co/api)
ai = AI4Chat(api_key="...")
response = ai.chat("Hello!")

# Free providers (no API key needed)
ai = HeckAI()
response = ai.chat("Hello!")
```

### Provider Methods

```python
# Basic chat
response = ai.chat("Hello!")

# Chat with history
response = ai.chat([
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello!"},
    {"role": "user", "content": "How are you?"}
])

# Streaming
for chunk in ai.chat("Write a story", stream=True):
    print(chunk, end="")
```

## Error Handling

```python
from llm4free import Client

client = Client()

try:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}]
    )
except Exception as e:
    print(f"Error: {e}")
    # Try fallback provider
    response = client.chat.completions.create(
        model="ai4chat/gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}]
    )
```
