# Tool Calling

> **Last updated:** 2026-10-24
> **Status:** Current & maintained
> **Target audience:** Developers building agentic AI applications

## Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Defining Tools](#defining-tools)
- [Passing Tools](#passing-tools)
- [How It Works](#how-it-works)
- [XML Format](#xml-format)
- [Reference](#reference)
- [Provider Examples](#provider-examples)
- [Troubleshooting](#troubleshooting)

---

## Overview

Every chat provider exposes OpenAI-style function calling. There are two layers,
plus a convenience loop for non-OpenAI providers.

| Layer | Entry point | Returns |
| --- | --- | --- |
| Unified client | `client.chat.completions.create(..., tools=[...])` | `ChatCompletion` with `message.tool_calls`; adds provider resolution and failover |
| OpenAI-compatible provider | `provider.chat.completions.create(..., tools=[...])` | `ChatCompletion` with `message.tool_calls` |
| `llm4free.AIbase.Provider` | `provider.chat(prompt, tools=[...])` | Final text after an automatic execute-and-continue loop |

Key points:

- **`Tool`** is a dataclass available from both `llm4free.AIbase` and
  `llm4free.llm.base`. Both variants are accepted by providers.
- **`tools`** accepts `Tool` objects, OpenAI-style dicts, or a mix. The list is
  typed loosely (`ToolList`) so `list[dict[str, Any]]`, `list[Tool]`, and mixed
  lists all type-check; entries are validated at runtime.
- **Native vs XML fallback** is automatic. Providers with
  `supports_tools = True` receive the OpenAI `tools` parameter directly. All
  others get an XML tool prompt injected into the system message, and their
  `<invoke>` output is converted back into native `tool_calls`.
- **You execute tools.** The standard OpenAI pattern applies: read
  `message.tool_calls`, run your functions, append `role: "tool"` messages, and
  call `create()` again.

---

## Quick Start

```python
import json

from llm4free import Client

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"],
            },
        },
    }
]

HANDLERS = {"get_weather": lambda city: {"city": city, "temp_c": 24}}

client = Client()
messages = [{"role": "user", "content": "What is the weather in Paris?"}]

for _ in range(5):
    response = client.chat.completions.create(
        model="auto",
        messages=messages,
        tools=TOOLS,
    )
    message = response.choices[0].message
    if message is None:
        raise RuntimeError("Provider returned no message")
    if not message.tool_calls:
        print(message.content)
        break

    messages.append(
        {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": call.type,
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in message.tool_calls
            ],
        }
    )

    for call in message.tool_calls:
        arguments = json.loads(call.function.arguments or "{}")
        result = HANDLERS[call.function.name](**arguments)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            }
        )
```

A minimal request that exposes the tool to the model is in
[`examples/tool_calling.py`](../examples/tool_calling.py). The loop below shows
how to execute the tool and send the result back.

---

## Defining Tools

### `Tool` objects

```python
from llm4free.AIbase import Tool

def get_weather(city: str, unit: str = "celsius") -> str:
    return f"Weather in {city}: 22 degrees {unit}, sunny"

weather_tool = Tool(
    name="get_weather",
    description="Get the current weather for a city.",
    parameters={
        "city": {"type": "string", "description": "City name."},
        "unit": {"type": "string", "description": "celsius or fahrenheit."},
    },
    required_params=["city"],
    implementation=get_weather,
)
```

`implementation` is optional. Without it, `tool.execute({...})` returns a
placeholder string. This is useful when another layer will execute the call.

More generally, `Tool.execute(arguments)` calls `implementation(**arguments)` and
returns the result.

### OpenAI-style dicts

```python
weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name."}
            },
            "required": ["city"],
        },
    },
}
```

Both forms can be mixed in the same `tools` list.

---

## Passing Tools

### Per request

```python
response = client.chat.completions.create(
    model="auto",
    messages=messages,
    tools=[weather_tool],
    tool_choice="auto",  # accepted for compatibility; ignored by the XML fallback
)
```

`tool_choice` is forwarded to native providers and dropped for the XML fallback,
where it has no meaning.

### Registered on a provider

```python
from llm4free.AIbase import Tool
from llm4free.llm.gemini import Gemini

weather_tool = Tool(
    name="get_weather",
    description="Get the current weather for a city.",
    parameters={"city": {"type": "string", "description": "City name."}},
    required_params=["city"],
)

ai = Gemini()
ai.register_tools([weather_tool])

response = ai.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Weather in Paris?"}],
)
```

When a request does not include `tools`, providers on the XML fallback use
`available_tools` automatically — the schemas are injected into the system
prompt, exactly as if they had been passed per request.

> [!NOTE]
> Some providers (for example `Miklium`) also accept `tools=[...]` in their
> constructor. Others override `__init__` without forwarding it, so call
> `register_tools()` there. Either way, each provider instance keeps its own
> `available_tools`; registered tools do not leak between instances.

> [!NOTE]
> Registering tools does not execute them. You still read `message.tool_calls`
> and run your handlers, just like the per-request flow.

---

## How It Works

### Native providers

Providers with `supports_tools = True` (currently `OpenRouter`) receive the
`tools` and `tool_choice` parameters directly. The provider parses its own
response into `message.tool_calls`.

### XML fallback

For every provider with `supports_tools = False`, `OpenAICompatibleProvider`
wraps `chat.completions.create` at instantiation. When tools are present:

1. **Normalize the conversation.** `_normalize_messages_for_prompt()` converts
   tool-aware messages into plain text:
   - `role: "tool"` → `role: "user"` with
     `Tool result (call_id=...):\n<content>`
   - assistant `tool_calls` → `<invoke>...</invoke>` XML inside the assistant
     content
2. **Inject the schemas.** `format_tools_for_prompt()` appends the tool
   instructions to the first system message, or prepends a system message when
   none exists.
3. **Strip incompatible fields.** `tools` and `tool_choice` are removed before
   calling the provider's real `create()`.
4. **Call the model once** with `stream=False`.
5. **Parse leniently.** `extract_tool_calls()` accepts:
   - the canonical `<invoke>` block
   - blocks wrapped in `<tool_call>` / `<function_calls>`
   - mismatched closing tags (for example `</tool_name>` closing `<parameters>`)
   - JSON-style `<tool_call>{"name": ..., "arguments": {...}}</tool_call>`
6. **Return native tool calls.** If calls were found, the response is rebuilt as
   a `ChatCompletion` with `content=None`, `finish_reason="tool_calls"`, and
   generated `ToolCall` ids. Otherwise the original response is returned
   unchanged.

Your follow-up call can use the standard OpenAI shape:

```python
messages += [
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "..."},
]
```

The fallback normalizes those `role: "tool"` messages on the next call, so models
that only understand plain chat still see the results.

### Streaming

Streaming is disabled when tools are present on the XML fallback: the wrapper
sets `stream=False` so it can inspect the full response before deciding whether a
tool was called. `create()` therefore returns a `ChatCompletion`, not a
generator. Providers with native tool support are unaffected.

### Client failover

`Client.chat.completions.create()` resolves a model to an available provider and
retries other providers when one fails. Tool-call responses with
`content=None` are treated as valid, so they are not mistaken for empty
responses. `client.chat.completions.last_provider` reports which provider
answered.

### `AIbase.Provider` loop

Non-OpenAI providers subclassing `llm4free.AIbase.Provider` expose a different
convenience API:

```python
answer = provider.chat("What is the weather in Paris?", tools=[weather_tool])
```

This runs the full loop internally: inject schemas, call the model, parse
`<invoke>` blocks, execute implementations, append `<tool_result>` blocks, and
repeat until the model returns plain text (up to `max_tool_rounds=5`). It returns
the final answer as text, not `tool_calls`.

---

## XML Format

**Tool invocation** (model output):

```xml
<invoke>
  <tool_name>get_weather</tool_name>
  <parameters>{"city": "Paris"}</parameters>
</invoke>
```

**Tool result** (fed back on the follow-up call for `AIbase.Provider`, or as a
`role: "tool"` message for the OpenAI-compatible path):

```xml
<tool_result>
  <tool_name>get_weather</tool_name>
  <result>Weather in Paris: 24C, sunny</result>
</tool_result>
```

The injected prompt asks the model to emit the block directly, with no
`<tool_call>` wrappers or markdown fences. The parser tolerates both anyway.

---

## Reference

### `Tool` dataclass

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `str` | Yes | Function name the model invokes. |
| `description` | `str` | Yes | What the tool does. |
| `parameters` | `Dict[str, Dict[str, Any]]` | Yes in `llm.base`; defaults to `{}` in `AIbase` | Parameter schema (name → info dict). |
| `required_params` | `Optional[List[str]]` | No | Required names. Defaults to all parameters. |
| `implementation` | `Optional[Callable[..., Any]]` | No | Callable executed by `execute()`. |

| Method | Signature | Returns |
| --- | --- | --- |
| `to_dict()` | `() -> Dict[str, Any]` | OpenAI-compatible tool definition |
| `execute()` | `(arguments: Dict[str, Any]) -> Any` | `implementation(**arguments)`, or an error/placeholder string |

### `create()` parameters relevant to tools

| Parameter | Type | Notes |
| --- | --- | --- |
| `tools` | `ToolList` (`list[Tool]`, `list[dict[str, Any]]`, or mixed) | Tool definitions available to the model. |
| `tool_choice` | `str \| dict \| None` | Forwarded to native providers; ignored by the XML fallback. |
| `stream` | `bool` | Ignored when tools are present on the XML fallback. |

### Response

```python
response.choices[0].message.tool_calls
# [ToolCall(id="call_...", type="function",
#           function=ToolFunction(name="get_weather",
#                                 arguments='{"city": "Paris"}'))]
```

`message.content` is `None` when the model only requests tools. `arguments` is a
JSON string; parse it with `json.loads`.

---

## Provider Examples

### Native tool support (OpenRouter)

```python
from llm4free.llm.Auth.openrouter import OpenRouter

ai = OpenRouter(api_key="sk-or-...")
response = ai.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "Weather in Paris?"}],
    tools=[weather_tool],
)
```

OpenRouter sets `supports_tools = True`, so no XML prompt is involved.

### XML fallback (Gemini)

```python
from llm4free.llm.gemini import Gemini

ai = Gemini()
response = ai.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Weather in Paris?"}],
    tools=[weather_tool],
)
```

### Mixed tool forms

```python
response = client.chat.completions.create(
    model="auto",
    messages=messages,
    tools=[weather_tool, {"type": "function", "function": {...}}],
)
```

### Full agent loop

The Quick Start above shows the full loop. For a minimal single-request example,
see [`examples/tool_calling.py`](../examples/tool_calling.py).

---

## Troubleshooting

**The model says it has no tools or ignores them.**
Some free providers do not follow the XML prompt. Pin a model that does:

```python
response = client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=messages,
    tools=TOOLS,
)
```

Native providers such as OpenRouter avoid the issue entirely.

**I get a `ChatCompletion` even though I passed `stream=True`.**
Expected on the XML fallback when tools are present. Streaming resumes on calls
without tools.

**The provider returns empty content and no tool calls.**
`Client` raises until another provider succeeds. If every provider fails, it
raises `RuntimeError: All chat providers failed`. Check provider availability or
pin one explicitly.

**The model passes the wrong argument names.**
Validate arguments in your handler and return an `{"error": "..."}` tool result.
The agent loop can then correct itself on the next turn; the example demonstrates
this.

**Type checking rejects `tools=[{"type": "function", ...}]`.**
Upgrade to the current signatures: `tools` accepts any list of `Tool`/dict
entries. If you see `no-matching-overload`, you are on an older version where the
parameter was `list[Tool | dict[str, Any]]` (which rejects `list[dict[str, Any]]`
because lists are invariant).
