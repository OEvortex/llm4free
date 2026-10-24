# Streaming Responses

> **Last updated:** 2026-07-16
> **Audience:** Beginner · **Time to complete:** 5 minutes

Handle long responses efficiently with streaming. Streaming returns response tokens as they are generated instead of waiting for the full response to finish.

---

## What is streaming?

Streaming lets you receive a response chunk-by-chunk instead of all at once:

```
Non-streaming: WAIT... WAIT... [Complete response all at once]
Streaming:     token → token → token → as → it → arrives
```

**Benefits:**

- Better user experience (shows progress immediately)
- Lower perceived latency (start reading faster)
- Works well for long responses

---

## Table of Contents

1. [Basic streaming](#basic-streaming)
2. [Streaming with different providers](#streaming-with-different-providers)
3. [Processing streamed data](#processing-streamed-data)
4. [Saving streamed responses](#saving-streamed-responses)
5. [Error handling](#error-handling)
6. [Troubleshooting](#troubleshooting)

---

## Basic streaming

### Stream with the unified Client (recommended)

The unified `Client` is the easiest way to stream: pass `stream=True` with `model="auto"` and the client picks a working provider and automatically fails over if it is unavailable. No need to import a specific provider class.

```python
from llm4free.client import Client

client = Client(print_provider_info=True)

print("AI Response:")
print("-" * 40)

# stream=True returns a generator of ChatCompletionChunk objects
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a short poem about Python"}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)

print()
print("-" * 40)
```

> [!TIP]
> `chunk.choices[0].delta.content` may be `None` for chunks that only carry metadata (for example, the finish reason). Always guard with `if delta:` before printing.

### Simple raw-provider streaming example

Every LLM provider also exposes the same OpenAI-compatible `chat.completions.create(..., stream=True)` method directly. With `stream=True` the call returns a generator of `ChatCompletionChunk` objects.

```python
from llm4free.llm.gemini import Gemini

client = Gemini()

print("AI Response:")
print("-" * 40)

stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Write a short poem about Python"}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)

print()
print("-" * 40)
```

**Output (real-time):**

```
AI Response:
----------------------------------------
Python is a language so fine,
With syntax that's easy, by design.
From scripts to data, it can do,
Libraries aplenty to choose from too.
----------------------------------------
```

### Streaming vs non-streaming

```python
from llm4free.llm.gemini import Gemini
import time

client = Gemini()

print("1. WITHOUT STREAMING (waits for complete response)")
print("-" * 50)
start = time.time()
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Write a 100-word essay on AI"}],
)
elapsed = time.time() - start
print(response.choices[0].message.content[:100] + "...")
print(f"Time: {elapsed:.1f}s\n")

print("2. WITH STREAMING (starts immediately)")
print("-" * 50)
start = time.time()
stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Write a 100-word essay on AI"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
elapsed = time.time() - start
print(f"\nTime: {elapsed:.1f}s")
```

---

## Streaming with different providers

### Gemini (free)

```python
from llm4free.llm.gemini import Gemini

client = Gemini()

stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello, write something nice"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

### Groq (API key)

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-groq-api-key")

stream = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Write a short story"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

### The unified Client (auto provider selection)

```python
from llm4free.client import Client

client = Client(print_provider_info=True)

stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Tell me a fun fact"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

---

## Processing streamed data

### Collect into a string

```python
from llm4free.llm.gemini import Gemini

client = Gemini()

stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Write a poem"}],
    stream=True,
)

full_response = ""
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        full_response += delta

print(f"Full response ({len(full_response)} chars):")
print(full_response)
```

### Count words in real time

```python
from llm4free.llm.gemini import Gemini

client = Gemini()

stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Write an essay on machine learning"}],
    stream=True,
)

word_count = 0
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        word_count += len(delta.split())
        print(delta, end="", flush=True)

print(f"\n\nTotal words: {word_count}")
```

### Filter chunks

```python
from llm4free.llm.gemini import Gemini

client = Gemini()

stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Discuss artificial intelligence"}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if not delta:
        continue
    if "AI" in delta or "intelligence" in delta:
        print(f"[{delta}]", end="", flush=True)
    else:
        print(delta, end="", flush=True)

print("\n")
```

---

## Saving streamed responses

### Save to file while streaming

```python
from llm4free.llm.gemini import Gemini
from datetime import datetime

client = Gemini()

filename = f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
print(f"Streaming to {filename}...\n")

stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Write about the future of technology"}],
    stream=True,
)

with open(filename, "w", encoding="utf-8") as f:
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            f.write(delta)
            print(delta, end="", flush=True)

print(f"\n\nSaved to {filename}")

with open(filename, "r", encoding="utf-8") as f:
    content = f.read()
    print(f"File size: {len(content)} bytes")
```

### Save multiple streams

```python
import json

from llm4free.llm.gemini import Gemini

client = Gemini()

prompts = [
    "What is AI?",
    "Explain machine learning",
    "Define deep learning",
]

responses = {}
for prompt in prompts:
    print(f"\nProcessing: {prompt}")
    stream = client.chat.completions.create(
        model="gemini-3.6-flash",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    full_response = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_response += delta
            print(delta, end="", flush=True)
    responses[prompt] = full_response

with open("responses.json", "w", encoding="utf-8") as f:
    json.dump(responses, f, indent=2, ensure_ascii=False)

print("\n\nAll responses saved to responses.json")
```

---

## Error handling

### Handle interrupted streams

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-groq-api-key", timeout=60)

full_response = ""
try:
    print("Streaming response...")
    stream = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Write a long story"}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_response += delta
            print(delta, end="", flush=True)
    print("\nStream completed successfully")
except Exception as e:
    print(f"\nStream interrupted: {e}")
    print(f"Partial response ({len(full_response)} chars received):")
    print(full_response)
```

> [!WARNING]
> Free providers change frequently and may intermittently return errors or empty streams. Wrap streaming calls in `try/except` and keep the partial response so a failure mid-stream does not lose all progress.

---

## Troubleshooting

### "No streaming data received"

**Problem:** The generator yields no usable content chunks.

**Solution:** Iterate the stream and confirm `delta.content` is non-empty:

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "test"}],
    stream=True,
)

chunks = [c.choices[0].delta.content for c in stream if c.choices[0].delta.content]
if not chunks:
    print("No content chunks received")
else:
    print(f"Received {len(chunks)} chunks")
    print("".join(chunks))
```

### "Incomplete response while streaming"

**Problem:** Connection interrupted.

**Solution:** Increase the timeout and capture the partial response:

```python
from llm4free.llm.gemini import Gemini

client = Gemini()

stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Long prompt"}],
    stream=True,
)

full_response = ""
try:
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_response += delta
except Exception as e:
    print(f"Stream interrupted: {e}")
    print(f"Partial response: {full_response}")
```

---

## See also

- [Basic Chat Examples](basic-chat.md)
- [API Reference](../api-reference.md)
- [Troubleshooting](../troubleshooting.md)

Next: learn about [Search](../search.md)
