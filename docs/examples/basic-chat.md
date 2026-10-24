# Basic Chat Examples

> **Last updated:** 2026-07-16
> **Audience:** Beginner · **Time to complete:** 5 minutes

This page shows the simplest ways to chat with an AI model using LLM4Free. Every provider implements the OpenAI-compatible `chat.completions.create(...)` interface, so the code shape is identical across vendors.

## Table of Contents

1. [Using the unified Client](#using-the-unified-client)
2. [Simplest example (no API key)](#simplest-example-no-api-key)
3. [Different providers](#different-providers)
4. [Customizing responses](#customizing-responses)
5. [Saving and reusing conversations](#saving-and-reusing-conversations)
6. [Using the unified Client (details)](#using-the-unified-client-details)

---

## Using the unified Client

Start here. The unified `Client` is the recommended way to chat — it mirrors the OpenAI SDK, picks a working provider for you, and auto-fails over when one is down. Use `model="auto"` to let it choose, or `model="Provider/Model"` to force a specific backend.

```python
from llm4free.client import Client

# Let the client pick any working provider/model
client = Client(print_provider_info=True)
print(client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Tell me a fun fact about space."}],
).choices[0].message.content)

# Force a specific provider/model
print(client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
print(client.chat.completions.last_provider)  # which provider was used
```

> [!TIP]
> `model="auto"` resolves a working provider/model for you; `model="Gemini/gemini-3.6-flash"` forces a specific backend. `print_provider_info=True` prints the chosen provider/model live. The raw-provider examples below are still valid, but the `Client` gives you auto-failover and model resolution for free.

---

## Simplest example (no API key)

`Gemini` is a free provider — no key required.

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "What is artificial intelligence?"}],
)
print(response.choices[0].message.content)
```

**Output:**

```
Artificial intelligence (AI) refers to computer systems designed to perform
tasks that typically require human intelligence — learning, reasoning,
problem-solving, language understanding, and visual perception...
```

---

## Different providers

### Gemini (free)

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
print(client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### Toolbaz (free)

```python
from llm4free.llm.toolbaz import Toolbaz

client = Toolbaz()
print(client.chat.completions.create(
    model="toolbaz-v5",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### ChatJimmy (free)

```python
from llm4free.llm.chatjimmy import ChatJimmy

client = ChatJimmy()
print(client.chat.completions.create(
    model="llama3.1-8B",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### Groq (API key)

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-groq-key")
print(client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Explain machine learning simply"}],
).choices[0].message.content)
```

### DeepInfra (API key)

```python
from llm4free.llm.Auth.deepinfra import DeepInfra

client = DeepInfra(api_key="your-deepinfra-key")
print(client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "What is Python?"}],
).choices[0].message.content)
```

> [!NOTE]
> The exact model strings accepted depend on the provider. Free providers expose their own model lists (for example Gemini's `"gemini-3.6-flash"`, Toolbaz's `"toolbaz-v5"`, or ChatJimmy's `"llama3.1-8B"`). Authenticated providers use the upstream model id (for example, Groq's `"llama-3.3-70b-versatile"` or DeepInfra's `"meta-llama/Meta-Llama-3.1-8B-Instruct"`).

---

## Customizing responses

Standard OpenAI parameters are supported: `temperature`, `max_tokens`, `top_p`, and `tools`.

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[
        {"role": "system", "content": "You are a concise tutor."},
        {"role": "user", "content": "Explain recursion in one sentence."},
    ],
    temperature=0.3,
    max_tokens=120,
)
print(response.choices[0].message.content)
```

---

## Saving and reusing conversations

Pass the full message list each call to keep context:

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
messages = [{"role": "user", "content": "My name is Ada."}]

r1 = client.chat.completions.create(model="gemini-3.6-flash", messages=messages)
print(r1.choices[0].message.content)

# Append the assistant reply, then ask a follow-up
messages.append({"role": "assistant", "content": r1.choices[0].message.content})
messages.append({"role": "user", "content": "What was my name?"})
r2 = client.chat.completions.create(model="gemini-3.6-flash", messages=messages)
print(r2.choices[0].message.content)
```

---

## Using the unified Client (details)

Forget provider names — let `Client` pick one and auto-fail over. Pass `model="auto"` for automatic selection, or `model="Provider/Model"` to force a specific backend.

```python
from llm4free.client import Client

client = Client(print_provider_info=True)
print(client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Tell me a fun fact about space."}],
).choices[0].message.content)

# Force a specific provider/model
print(client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

See [client.md](../client.md) for the full reference and [streaming-responses.md](streaming-responses.md) for streaming.
