"""Regression tests for tool calling through the client and providers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import llm4free.client as client_module
from llm4free.client import _is_valid_chat_completion
from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
    Tool,
)
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionMessage,
    Choice,
    ToolCall,
    ToolFunction,
)

TOOLS: list[dict[str, Any]] = [
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

TOOL_XML = (
    "<invoke><tool_name>get_weather</tool_name>"
    '<parameters>{"city":"Paris"}</parameters></invoke>'
)


class FakeCompletions(BaseCompletions):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        self.calls.append({"stream": stream, "messages": messages, **kwargs})
        has_tool_result = any(
            message.get("role") == "tool"
            or "Tool result" in str(message.get("content") or "")
            for message in messages
        )
        content = "It is sunny in Paris." if has_tool_result else TOOL_XML
        return ChatCompletion(
            model=model,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(role="assistant", content=content),
                )
            ],
        )


class FakeChat(BaseChat):
    def __init__(self, client: "FakeProvider") -> None:
        self.completions = FakeCompletions()


class FakeProvider(OpenAICompatibleProvider):
    required_auth = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.chat = FakeChat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(["fake-model"])


def test_extracts_lenient_tool_call_formats() -> None:
    wrapped = (
        "<tool_call><function_calls>\n"
        "<invoke>\n"
        "  <tool_name>get_weather</tool_name>\n"
        "  <parameters>\n"
        '  {"city": "Paris"}\n'
        "  </tool_name>\n"
        "</invoke>\n"
        "</invoke>\n"
        "</function_calls></tool_call>"
    )
    calls = BaseCompletions.extract_tool_calls(wrapped)
    assert calls == [{"name": "get_weather", "arguments": {"city": "Paris"}}]


def test_extracts_json_style_tool_call() -> None:
    text = (
        '<tool_call>{"name": "get_weather", '
        '"arguments": {"city": "Paris"}}</tool_call>'
    )
    calls = BaseCompletions.extract_tool_calls(text)
    assert calls == [{"name": "get_weather", "arguments": {"city": "Paris"}}]


def test_validator_accepts_tool_call_without_content() -> None:
    completion = ChatCompletion(
        model="fake-model",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            type="function",
                            function=ToolFunction(
                                name="get_weather", arguments='{"city":"Paris"}'
                            ),
                        )
                    ],
                ),
            )
        ],
    )
    assert _is_valid_chat_completion(completion)

    empty = ChatCompletion(
        model="fake-model",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content="  "),
            )
        ],
    )
    assert not _is_valid_chat_completion(empty)


def test_non_native_provider_emits_tool_calls() -> None:
    provider = FakeProvider()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Weather in Paris?"}
    ]
    response = provider.chat.completions.create(
        model="fake-model",
        messages=messages,
        tools=TOOLS,
    )
    message = response.choices[0].message
    assert message is not None
    assert message.tool_calls is not None
    assert message.tool_calls[0].function.name == "get_weather"

    completions = provider.chat.completions
    assert isinstance(completions, FakeCompletions)
    assert "tools" not in completions.calls[0]
    assert "tool_choice" not in completions.calls[0]

    history: list[dict[str, Any]] = [
        {"role": "user", "content": "Weather in Paris?"},
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
        },
        {
            "role": "tool",
            "tool_call_id": message.tool_calls[0].id,
            "content": json.dumps({"city": "Paris", "temperature_c": 22}),
        },
    ]
    final = provider.chat.completions.create(
        model="fake-model", messages=history, tools=TOOLS
    )
    assert final.choices[0].message is not None
    assert final.choices[0].message.content == "It is sunny in Paris."

    follow_up_messages = completions.calls[1]["messages"]
    assert all(message.get("role") != "tool" for message in follow_up_messages)
    assert not any(message.get("tool_calls") for message in follow_up_messages)
    tool_result_text = "\n".join(
        str(message.get("content") or "") for message in follow_up_messages
    )
    assert "Tool result" in tool_result_text
    assert "temperature_c" in tool_result_text


def _load_tool_calling_example() -> Any:
    example_path = Path(__file__).resolve().parents[1] / "examples" / "tool_calling.py"
    spec = importlib.util.spec_from_file_location("example_tool_calling", example_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_agent_runs_tool_loop() -> None:
    example = _load_tool_calling_example()

    calls: list[dict[str, Any]] = []

    class StubCompletions:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            if len(calls) == 1:
                return ChatCompletion(
                    model="stub",
                    choices=[
                        Choice(
                            index=0,
                            message=ChatCompletionMessage(
                                role="assistant",
                                content=None,
                                tool_calls=[
                                    ToolCall(
                                        id="call_1",
                                        type="function",
                                        function=ToolFunction(
                                            name="get_weather",
                                            arguments='{"city": "Paris"}',
                                        ),
                                    )
                                ],
                            ),
                        )
                    ],
                )
            return ChatCompletion(
                model="stub",
                choices=[
                    Choice(
                        index=0,
                        message=ChatCompletionMessage(
                            role="assistant",
                            content="It is 24C and sunny in Paris.",
                        ),
                    )
                ],
            )

    class StubChat:
        def __init__(self) -> None:
            self.completions = StubCompletions()

    class StubClient:
        def __init__(self) -> None:
            self.chat = StubChat()

    answer = example.run_agent(
        cast(Any, StubClient()), "What is the weather in Paris?"
    )
    assert answer == "It is 24C and sunny in Paris."
    assert len(calls) == 2

    tool_messages = [m for m in calls[1]["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert '"condition": "sunny"' in tool_messages[0]["content"]


def test_registered_tools_are_injected_into_prompt() -> None:
    provider = FakeProvider(
        tools=[
            Tool(
                name="get_weather",
                description="Get the current weather for a city.",
                parameters={"city": {"type": "string"}},
                required_params=["city"],
            )
        ]
    )
    response = provider.chat.completions.create(
        model="fake-model",
        messages=[{"role": "user", "content": "Weather in Paris?"}],
    )
    message = response.choices[0].message
    assert message is not None
    assert message.tool_calls is not None

    completions = provider.chat.completions
    assert isinstance(completions, FakeCompletions)
    prompt_text = "\n".join(
        str(m.get("content") or "") for m in completions.calls[0]["messages"]
    )
    assert "# Tools" in prompt_text
    assert "get_weather" in prompt_text


def test_example_agent_recovers_from_bad_tool_arguments() -> None:
    example = _load_tool_calling_example()
    calls: list[dict[str, Any]] = []

    class StubCompletions:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            if len(calls) == 1:
                return ChatCompletion(
                    model="stub",
                    choices=[
                        Choice(
                            index=0,
                            message=ChatCompletionMessage(
                                role="assistant",
                                content=None,
                                tool_calls=[
                                    ToolCall(
                                        id="call_bad",
                                        type="function",
                                        function=ToolFunction(
                                            name="get_weather",
                                            arguments='{"town": "Paris"}',
                                        ),
                                    )
                                ],
                            ),
                        )
                    ],
                )
            return ChatCompletion(
                model="stub",
                choices=[
                    Choice(
                        index=0,
                        message=ChatCompletionMessage(
                            role="assistant",
                            content="It is 24C and sunny in Paris.",
                        ),
                    )
                ],
            )

    class StubChat:
        def __init__(self) -> None:
            self.completions = StubCompletions()

    class StubClient:
        def __init__(self) -> None:
            self.chat = StubChat()

    answer = example.run_agent(
        cast(Any, StubClient()), "What is the weather in Paris?"
    )
    assert answer == "It is 24C and sunny in Paris."

    tool_messages = [m for m in calls[1]["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "unexpected keyword argument" in tool_messages[0]["content"]


def test_accepts_aibase_tool_objects() -> None:
    from llm4free.AIbase import Tool as AIbaseTool

    ai_tool = AIbaseTool(
        name="get_weather",
        description="Get the current weather for a city.",
        parameters={"city": {"type": "string"}},
        required_params=["city"],
    )
    provider = FakeProvider()
    response = provider.chat.completions.create(
        model="fake-model",
        messages=[{"role": "user", "content": "Weather in Paris?"}],
        tools=[ai_tool],
    )
    message = response.choices[0].message
    assert message is not None
    assert message.tool_calls is not None

    completions = provider.chat.completions
    assert isinstance(completions, FakeCompletions)
    prompt_text = "\n".join(
        str(m.get("content") or "") for m in completions.calls[0]["messages"]
    )
    assert "get_weather" in prompt_text


def test_client_returns_tool_calls(monkeypatch) -> None:
    monkeypatch.setitem(client_module.OPENAI_PROVIDERS, "FakeProvider", FakeProvider)
    client = client_module.Client()
    monkeypatch.setattr(
        client.chat.completions,
        "_get_available_providers",
        lambda: [("FakeProvider", FakeProvider)],
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Weather in Paris?"}
    ]
    response = client.chat.completions.create(
        model="FakeProvider/fake-model",
        messages=messages,
        tools=TOOLS,
    )
    message = response.choices[0].message
    assert message is not None
    assert message.tool_calls is not None
    assert message.tool_calls[0].function.name == "get_weather"

    completions = client.chat.completions
    assert isinstance(completions, client_module.ClientCompletions)
    assert completions.last_provider == "FakeProvider"

    history: list[dict[str, Any]] = [
        *messages,
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": message.tool_calls[0].id,
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city":"Paris"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": message.tool_calls[0].id,
            "content": json.dumps({"temperature_c": 22}),
        },
    ]
    final = client.chat.completions.create(
        model="FakeProvider/fake-model",
        messages=history,
        tools=TOOLS,
    )
    final_message = final.choices[0].message
    assert final_message is not None
    assert final_message.content == "It is sunny in Paris."


def test_openrouter_parses_tool_calls(monkeypatch) -> None:
    from llm4free.llm.Auth.openrouter import OpenRouter

    monkeypatch.setattr(
        OpenRouter, "_start_background_model_fetch", lambda self, api_key=None: None
    )
    provider = OpenRouter(api_key="test-key")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "id": "chatcmpl-test",
                "model": "openai/gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"city":"Paris"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            }

    class FakeSession:
        def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    provider.session = FakeSession()  # ty: ignore[invalid-assignment]

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Weather in Paris?"}
    ]
    response = provider.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=messages,
        tools=TOOLS,
    )
    message = response.choices[0].message
    assert message is not None
    assert message.tool_calls is not None
    assert message.tool_calls[0].function.name == "get_weather"
