# Troubleshooting Guide

> Last updated: 2026-07-16
> Type: Support & FAQ
> Audience: All users

## Table of Contents

- [Installation Issues](#installation-issues)
- [Authentication Errors](#authentication-errors)
- [Runtime Errors](#runtime-errors)
- [Streaming Problems](#streaming-problems)
- [Performance Issues](#performance-issues)
- [FAQ](#faq)

---

## Installation Issues

### "ModuleNotFoundError: No module named 'llm4free'"

**Diagnosis:** LLM4Free is not installed or not in your Python path.

**Solutions:**

```bash
# 1. Install via pip
pip install -U llm4free

# 2. Or use uv (recommended)
uv add llm4free

# 3. If developing locally, install in editable mode
cd /path/to/LLM4Free
pip install -e .

# 4. Verify installation worked
python -c "import llm4free; print(llm4free.__version__)"
```

### "pip: command not found"

**Diagnosis:** Python or pip is not installed, or not in PATH.

**Solutions:**

```bash
# 1. Check if Python is installed
python --version
python3 --version

# 2. Install pip if missing
python -m ensurepip --upgrade

# 3. Use uv instead (easier)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv add llm4free

# 4. Use python -m pip instead
python -m pip install llm4free
```

### "Permission denied" during installation

**Windows:**

```bash
# Run Command Prompt as Administrator
# Then run
pip install -U llm4free
```

**Linux/macOS:**

```bash
# Use --user flag to install for current user only
pip install --user llm4free

# Or use a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install llm4free
```

### "Could not find a version that satisfies the requirement"

**Diagnosis:** Package version doesn't exist or your Python version is incompatible.

**Solutions:**

```bash
# 1. Check your Python version
python --version

# 2. Install latest version
pip install --upgrade llm4free

# 3. Install specific version
pip install llm4free==2024.12.01

# 4. Clear pip cache and retry
pip cache purge
pip install llm4free
```

---

## Authentication Errors

### "401 Unauthorized" or "Invalid API Key"

**Diagnosis:** API key is invalid, expired, or has wrong permissions. This applies to auth-required providers such as `Groq`, `DeepInfra`, `OpenRouter`, and others in `llm4free.llm.Auth`.

**Solutions:**

```python
# 1. Check for typos and whitespace
api_key = "gsk-your-key"  # Good
api_key = "gsk-your-key " # Bad - trailing space!
api_key = " gsk-your-key" # Bad - leading space!

# 2. Verify the key format for the provider
# Groq keys start with "gsk_"
# DeepInfra keys are issued from deepinfra.com

from llm4free.llm.Auth.groq import Groq
client = Groq(api_key=api_key.strip())  # Remove whitespace
```

> [!NOTE]
> Free providers such as `ChatGPT`, `Gemini`, `Toolbaz`, `GptFree`, and `IBM` require no API key. If you only need basic chat, prefer them to avoid auth issues entirely.

### "API key not provided"

**Diagnosis:** A required API key is missing for an auth-gated provider.

**Solutions:**

```python
# 1. Pass key directly (for testing only)
from llm4free.llm.Auth.groq import Groq
client = Groq(api_key="your-actual-key-here")

# 2. Use environment variable (more secure)
import os
os.environ["GROQ_API_KEY"] = "your-key-here"
client = Groq(api_key=os.environ["GROQ_API_KEY"])

# 3. Shell environment variables are only a source for os.environ;
#    LLM4Free does not read provider keys from the environment itself.
#    Linux/macOS: export GROQ_API_KEY=your-key-here
#    Windows PowerShell: $env:GROQ_API_KEY="your-key-here"

# 4. For providers that don't require auth
from llm4free.llm.chatgpt import ChatGPT
ai = ChatGPT()  # No key needed
response = ai.chat.completions.create(
    model="GPT-6-free",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

### "Invalid authentication credentials"

**Diagnosis:** API key exists but is not properly formatted or has been revoked.

**Solutions:**

```python
# 1. Generate a new API key from the service's dashboard
# 2. Make sure you're using the latest key
# 3. Check if the key has the required permissions

# 4. Test connectivity with curl (example for a keyed provider)
import subprocess

api_key = "your-key"
result = subprocess.run(
    ["curl", "-H", f"Authorization: Bearer {api_key}",
     "https://api.groq.com/openai/v1/models"],
    capture_output=True, text=True,
)
print(result.stdout)  # Should show available models
```

---

## Runtime Errors

### "ConnectionError" or "Failed to establish connection"

**Diagnosis:** Network issue or server is unreachable.

**Solutions:**

```python
# 1. Check your internet connection
import socket
try:
    socket.create_connection(("8.8.8.8", 53))
    print("Internet connection: OK")
except OSError:
    print("No internet connection")

# 2. Increase timeout
from llm4free.llm.Auth.groq import Groq
client = Groq(api_key="key", timeout=60)  # 60 seconds instead of default

# 3. Use a retry mechanism
from llm4free.AIutel import retry

@retry(retries=3, delay=2)
def safe_chat(prompt):
    client = Groq(api_key="key")
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )

response = safe_chat("Hello")
```

### "TimeoutError: request timed out"

**Diagnosis:** Request took too long to complete.

**Solutions:**

```python
# 1. Increase timeout value
from llm4free.llm.Auth.groq import Groq

client = Groq(
    api_key="key",
    timeout=120,  # 2 minutes
)

# 2. Try with a simpler prompt
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello"}],
)

# 3. Use a proxy/VPN if certain services are blocked.
#    Groq's constructor does not take a proxies argument; the unified
#    Client applies proxies to every provider it initializes.
from llm4free import Client
client = Client(
    api_key="key",
    drop_auth_providers=False,
    proxies={
        "http": "http://proxy.example.com:8080",
        "https": "http://proxy.example.com:8080",
    },
)
```

### "RateLimitError" or "Too many requests"

**Diagnosis:** You're making requests too frequently.

**Solutions:**

```python
# 1. Add delays between requests
import time
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="key")

for i in range(10):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Question {i}"}],
    )
    print(response.choices[0].message.content)
    time.sleep(5)  # Wait 5 seconds between requests

# 2. Check rate limits in the provider's documentation
print("Check service documentation for rate limits:")
print("- Groq: https://console.groq.com/docs/rate-limits")
```

### "AttributeError" or "TypeError"

**Diagnosis:** Using wrong method names, attributes, or import paths.

**Solutions:**

```python
# 1. Check method names (Python is case-sensitive)
from llm4free.llm.chatgpt import ChatGPT

client = ChatGPT()

# Good - correct OpenAI-compatible interface
response = client.chat.completions.create(
    model="GPT-6-free",
    messages=[{"role": "user", "content": "Hello"}],
)

# Bad - wrong interface (AttributeError!)
# response = client.Chat("Hello")

# 2. Check method signatures
from inspect import signature
sig = signature(client.chat.completions.create)
print(sig)  # Shows what parameters are expected

# 3. Use dir() to list available methods
print(dir(client))

# 4. Check docstrings
help(client.chat.completions.create)
```

### "ImportError" or "ModuleNotFoundError" for specific modules

**Diagnosis:** Wrong import path, or optional dependencies not installed.

**Solutions:**

> [!WARNING]
> The legacy import paths `llm4free.Provider.Openai_comp.*` and top-level names like `Meta`, `GROQ`, `OpenAI` do **not** exist in this version. Use the verified paths below:
>
> - `from llm4free.llm.chatgpt import ChatGPT`
> - `from llm4free.llm.Auth.groq import Groq`
> - `from llm4free.client import Client`
> - `from llm4free import DuckDuckGoSearch`

> [!TIP]
> When using the unified `Client`, two options make debugging provider failures much easier:
> - **Exclude flaky providers** so the auto-failover logic skips them entirely:
>   ```python
>   from llm4free.client import Client
>   client = Client(exclude=["SomeFlakyProvider"])
>   ```
> - **Trace which provider actually answered** a request. Pass `print_provider_info=True` to the constructor for a one-time banner, or inspect `client.chat.completions.last_provider` after a call:
>   ```python
>   from llm4free.client import Client
>   client = Client(print_provider_info=True)
>   resp = client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Hi"}])
>   print("Served by:", client.chat.completions.last_provider)
>   ```
> The same exclusion helpers exist for the image and audio namespaces: `exclude_images=[...]` and `exclude_tts=[...]`.

```bash
# 1. Install with extras for API server
pip install "llm4free[api]"

# 2. Install with dev dependencies
pip install "llm4free[dev]"

# 3. Install specific missing packages
pip install beautifulsoup4
pip install requests
pip install curl-cffi

# 4. Check what's installed
pip list | grep llm4free
```

---

## Streaming Problems

### "No streaming data received" or "Generator is empty"

**Diagnosis:** Streaming isn't enabled or response format is wrong.

**Solutions:**

```python
import types
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="key")

# 1. Make sure stream=True
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Write a story"}],
    stream=True,
)

# 2. Check if it's actually a generator
if isinstance(response, types.GeneratorType):
    print("Streaming enabled")
    for chunk in response:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
else:
    print("Not streaming - got direct response")
    print(response)
```

### "Incomplete response while streaming"

**Diagnosis:** Connection interrupted during streaming.

**Solutions:**

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="key", timeout=120)

full_response = ""
try:
    stream = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Your prompt"}],
        stream=True,
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            full_response += chunk.choices[0].delta.content
            print(chunk.choices[0].delta.content, end="", flush=True)
except Exception as e:
    print(f"\n\nStream interrupted: {e}")
    print(f"Partial response received:\n{full_response}")
```

---

## Performance Issues

### "Response is very slow"

**Diagnosis:** Network latency, server load, or model complexity.

**Solutions:**

```python
# 1. Check network speed
import time

from llm4free.llm.gemini import Gemini
client = Gemini()

start = time.time()
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "What is AI?"}],
)
duration = time.time() - start

if duration > 10:
    print(f"Slow response: {duration:.1f}s")
else:
    print(f"Normal response time: {duration:.1f}s")

# 2. Use faster models (Groq is known for low latency)
from llm4free.llm.Auth.groq import Groq
client = Groq(api_key="key")
response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[{"role": "user", "content": "Prompt"}],
)

# 3. Reduce response length
response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[{"role": "user", "content": "What is AI?"}],
    max_tokens=100,  # Shorter response = faster
)
```

### "High memory usage" or "Out of memory"

**Diagnosis:** Large response, long conversation history, or memory leak.

**Solutions:**

```python
# 1. Process streaming chunks and discard (don't accumulate)
from llm4free.llm.chatgpt import ChatGPT
client = ChatGPT()

for chunk in client.chat.completions.create(
    model="GPT-6-free",
    messages=[{"role": "user", "content": "Long prompt"}],
    stream=True,
):
    if chunk.choices[0].delta.content:
        # Process each chunk and discard
        process_chunk(chunk.choices[0].delta.content)

# 2. Process large lists in batches
prompts = ["Q1", "Q2"]  # Potentially huge list

batch_size = 10
for i in range(0, len(prompts), batch_size):
    batch = prompts[i:i + batch_size]
    for prompt in batch:
        response = client.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": prompt}],
        )
    del batch
    import gc
    gc.collect()  # Force garbage collection
```

---

## FAQ

### Q: Which provider should I use?

**A:** Depends on your needs:

- **Free, no API key:** `ChatGPT`, `Gemini`, `Toolbaz`, `GptFree`, `IBM` (in `llm4free.llm`)
- **Fast and affordable:** `Groq` (free tier available, in `llm4free.llm.Auth`)
- **Open models:** `DeepInfra`, `TogetherAI` (auth required)
- **Multi-model router:** `OpenRouter` (auth required)

### Q: How do I use multiple providers as fallback?

**A:** Use the `Client` with automatic failover:

```python
from llm4free.client import Client

client = Client()

# Automatically tries providers in order
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

Or implement manual fallback:

```python
def chat_with_fallback(prompt):
    providers = [
        ("Groq", lambda: __import__("llm4free.llm.Auth.groq", fromlist=["Groq"]).Groq(api_key="key"), "llama-3.3-70b-versatile"),
        ("ChatGPT", lambda: __import__("llm4free.llm.chatgpt", fromlist=["ChatGPT"]).ChatGPT(), "GPT-6-free"),
    ]
    for name, factory, model in providers:
        try:
            client = factory()
            return client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            ).choices[0].message.content
        except Exception as e:
            print(f"{name} failed, trying next...")
    raise RuntimeError("All providers failed")
```

### Q: How do I save API keys securely?

**A:** Never hardcode API keys:

```python
# Bad - hardcoded keys
# client = Groq(api_key="gsk-1234567890")

# Good - environment variables
import os
api_key = os.getenv("GROQ_API_KEY")
from llm4free.llm.Auth.groq import Groq
client = Groq(api_key=api_key)

# Good - .env file
from dotenv import load_dotenv
load_dotenv()  # Load from .env file
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key)
```

### Q: How do I use LLM4Free with asyncio?

**A:** LLM4Free is synchronous, but you can use `asyncio` with `run_in_executor`:

```python
import asyncio
from llm4free.llm.Auth.groq import Groq

async def async_chat(prompt):
    loop = asyncio.get_event_loop()
    client = Groq(api_key="key")
    return await loop.run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
        ),
    )

response = await async_chat("Hello")
print(response.choices[0].message.content)
```

### Q: How do I handle special characters in prompts?

**A:** They're handled automatically, but you can check encoding:

```python
prompt = "你好 مرحبا שלום"  # Multiple languages

from llm4free.llm.chatgpt import ChatGPT
client = ChatGPT()
response = client.chat.completions.create(
    model="GPT-6-free",
    messages=[{"role": "user", "content": prompt}],
)
print(response.choices[0].message.content)
```

### Q: How do I report a bug?

**A:**

1. Check the [GitHub Issues](https://github.com/OEvortex/LLM4Free/issues)
2. Create a minimal reproducible example:

```python
from llm4free.llm.chatgpt import ChatGPT

client = ChatGPT()
response = client.chat.completions.create(
    model="GPT-6-free",
    messages=[{"role": "user", "content": "Simple test"}],
)
print(response.choices[0].message.content)
```

3. Include:
   - Python version: `python --version`
   - LLM4Free version: `pip show llm4free`
   - Full error traceback
   - Steps to reproduce

---

## Still Having Issues?

- **Documentation:** [docs/README.md](README.md)
- **API Reference:** [docs/api-reference.md](api-reference.md)
- **Examples:** [docs/examples/](examples/README.md)
- **GitHub Issues:** https://github.com/OEvortex/LLM4Free/issues
- **Telegram Group:** https://t.me/OEvortexAI
