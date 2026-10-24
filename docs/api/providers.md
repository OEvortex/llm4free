# Providers API Reference

## Base Class

All providers inherit from `OpenAICompatibleProvider` which provides a standard interface.

### Interface

```python
class OpenAICompatibleProvider:
    AVAILABLE_MODELS = []  # List of available models
    
    def chat(self, messages, stream=False):
        """Send chat messages and get response."""
        pass
```

## Provider Management

### Initialize Providers

```python
from llm4free.server.providers import initialize_provider_map

# Discover and register all available providers
initialize_provider_map()
```

### Resolve Provider

```python
from llm4free.server.providers import resolve_provider_and_model

# Resolve provider class and model name from identifier
provider_class, model_name = resolve_provider_and_model("AI4Chat/gpt-4o")
```

### Get Provider Instance

```python
from llm4free.server.providers import get_provider_instance

# Get cached provider instance
provider = get_provider_instance(provider_class)
```

## Available Providers

### Free Providers (No API Key Required)

| Provider | Models | Features |
|----------|--------|----------|
| ChatGPT | 15+ | GPT models |
| HeckAI | 9+ | DeepSeek, Gemini |
| LLMChat | 40+ | Cloudflare models |
| Toolbaz | 20+ | Various models |
| FreeAI | 30+ | Anthropic, OpenAI |

### Paid Providers (API Key Required)

| Provider | Models | Features |
|----------|--------|----------|
| OpenAI | GPT-4o, o1, etc. | Official OpenAI |
| Anthropic | Claude 3.5, etc. | Official Anthropic |
| Google | Gemini 2.0, etc. | Official Google |

## Creating Custom Providers

### Step 1: Create Provider Class

```python
from llm4free.llm.base import OpenAICompatibleProvider

class MyProvider(OpenAICompatibleProvider):
    AVAILABLE_MODELS = ["model-1", "model-2"]
    required_auth = True  # or False for free providers
    
    def __init__(self, api_key=None):
        self.api_key = api_key
    
    def chat(self, messages, stream=False, **kwargs):
        # Implement chat logic
        response = self._call_api(messages, **kwargs)
        return response
```

### Step 2: Register Provider

```python
# In your provider's __init__.py
from llm4free.server.providers import AppConfig

AppConfig.provider_map["MyProvider"] = MyProvider

# Register models
for model in MyProvider.AVAILABLE_MODELS:
    AppConfig.provider_map[f"MyProvider/{model}"] = MyProvider
```

## Provider Selection

### Automatic Selection

```python
from llm4free import Client

client = Client()
# Client automatically selects best available provider
response = client.chat.completions.create(
    model="gpt-4o",  # Mapped to available provider
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### Manual Selection

```python
from llm4free import AI4Chat

# Use specific provider (free API key from https://www.ai4chat.co/api)
ai = AI4Chat(api_key="...")
response = ai.chat("Hello!")
```

## Provider Configuration

### API Keys

```python
# Via JSON file
client = Client(api_keys_file="keys.json")

# Via environment
import os
os.environ["OPENAI_API_KEY"] = "sk-..."

# Via constructor
client = Client(api_key="sk-...")
```

### keys.json Format

```json
{
    "OpenAI": "sk-...",
    "Anthropic": "sk-ant-...",
    "Google": "AIza..."
}
```
