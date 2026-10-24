"""Tests for the AI4Chat provider.

Regression coverage for the "Invalid Request" issue: AI4Chat's legacy public gateway
rejected every request with HTTP 200 and a literal ``"Invalid Request"`` body, which the
provider used to return to callers as if it were assistant content. The provider now
talks to AI4Chat's official OpenAI-compatible endpoint and raises on gateway error
bodies instead of surfacing them as completions.
"""

import json
from typing import Any, cast

import pytest

from llm4free.llm.ai4chat import LEGACY_ERROR_BODIES, AI4Chat
from llm4free.llm.utils import ChatCompletion, ChatCompletionChunk


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", chunks=None):
        self.status_code = status_code
        self._json_data = json_data
        self._text = text
        self._chunks = chunks or []

    @property
    def text(self):
        if self._text:
            return self._text
        if self._json_data is not None:
            return json.dumps(self._json_data)
        return ""

    def json(self):
        if self._json_data is not None:
            return self._json_data
        return json.loads(self._text)

    def iter_content(self, chunk_size=None):
        return iter(self._chunks)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP Error: {self.status_code}")


class FakeSession:
    """Records the outgoing request and replays a canned response."""

    def __init__(self, response):
        self.proxies = {}
        self.headers = {}
        self.calls = []
        self._response = response

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._response

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._response

    @property
    def last_body(self):
        return json.loads(self.calls[-1]["data"])


def make_client(response, **kwargs):
    client = AI4Chat(**kwargs)
    # Swap in the fake transport; the real session is a curl_cffi Session.
    cast(Any, client).session = FakeSession(response)
    return client


def completion_response(content="There are 3 r's."):
    return FakeResponse(
        json_data={
            "id": "cmpl-1",
            "created": 1700000000,
            "model": "GPT 5.2",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }
    )


# --- official endpoint -------------------------------------------------------


def test_uses_official_openai_compatible_endpoint():
    client = make_client(completion_response(), api_key="k")
    assert client.api_endpoint == "https://www.ai4chat.co/api/v1/chat/completions"
    assert client.headers["Authorization"] == "Bearer k"
    assert client.headers["Content-Type"] == "application/json"


def test_non_stream_maps_model_key_to_display_name_and_parses_usage():
    client = make_client(completion_response(), api_key="k")
    result = client.chat.completions.create(
        model="gpt-5.2", messages=[{"role": "user", "content": "how many r?"}]
    )

    body = client.session.last_body
    assert body["model"] == "GPT 5.2"
    assert body["stream"] is False

    assert isinstance(result, ChatCompletion)
    assert result.choices[0].message.content == "There are 3 r's."
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 7
    assert result.usage.total_tokens == 18


def test_optional_params_are_forwarded():
    client = make_client(completion_response(), api_key="k")
    client.chat.completions.create(
        model="gpt-5.2",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.4,
        top_p=0.9,
        max_tokens=64,
        language="English",
    )
    body = client.session.last_body
    assert body["temperature"] == 0.4
    assert body["top_p"] == 0.9
    assert body["max_tokens"] == 64
    assert body["language"] == "English"


def test_messages_pass_through_without_a_system_prompt_by_default():
    client = make_client(completion_response(), api_key="k")
    client.chat.completions.create(model="gpt-5.2", messages=[{"role": "user", "content": "hi"}])
    assert client.session.last_body["messages"] == [{"role": "user", "content": "hi"}]


def test_configured_system_prompt_is_used_only_when_caller_sends_none():
    client = make_client(completion_response(), api_key="k", system_prompt="Be terse.")
    client.chat.completions.create(model="gpt-5.2", messages=[{"role": "user", "content": "hi"}])
    assert client.session.last_body["messages"][0] == {"role": "system", "content": "Be terse."}

    client.chat.completions.create(
        model="gpt-5.2",
        messages=[{"role": "system", "content": "Mine."}, {"role": "user", "content": "hi"}],
    )
    assert client.session.last_body["messages"][0] == {"role": "system", "content": "Mine."}


def test_stream_parses_sse_into_chunks():
    events = [
        b'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"role":"assistant","content":"Hel"}}]}\n\n',
        b'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"content":"lo!"}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    client = make_client(FakeResponse(chunks=events), api_key="k")
    stream = client.chat.completions.create(
        model="claude-haiku-4.5", messages=[{"role": "user", "content": "hi"}], stream=True
    )

    assert client.session.last_body["stream"] is True

    text, finish = "", None
    for chunk in stream:
        assert isinstance(chunk, ChatCompletionChunk)
        if chunk.choices[0].delta and chunk.choices[0].delta.content:
            text += chunk.choices[0].delta.content
        if chunk.choices[0].finish_reason:
            finish = chunk.choices[0].finish_reason

    assert text == "Hello!"
    assert finish == "stop"


# --- error handling ----------------------------------------------------------


def test_invalid_api_key_raises_with_actionable_hint():
    client = make_client(
        FakeResponse(status_code=403, json_data={"error": "Forbidden - Invalid API Key"}),
        api_key="bad",
    )
    with pytest.raises(IOError) as exc:
        client.chat.completions.create(
            model="gpt-5.2", messages=[{"role": "user", "content": "hi"}]
        )
    assert "403" in str(exc.value)
    assert "ai4chat.co/api" in str(exc.value)


def test_missing_api_key_falls_back_to_the_legacy_gateway():
    client = make_client(FakeResponse(status_code=200, text='"From the legacy gateway."'))
    assert client.api_key is None

    result = client.chat.completions.create(
        model="gpt-5.2", messages=[{"role": "user", "content": "how many r?"}]
    )

    call = client.session.calls[-1]
    assert call["url"] == client.legacy_endpoint
    assert call["params"]["text"]
    assert "country" in call["params"] and "user_id" in call["params"]
    assert result.choices[0].message.content == "From the legacy gateway."


def test_legacy_invalid_request_body_is_never_returned_as_content():
    """Regression: the gateway answered HTTP 200 with a literal "Invalid Request"."""
    client = make_client(FakeResponse(status_code=200, text='"Invalid Request"'))
    with pytest.raises(IOError) as exc:
        client.chat.completions.create(
            model="gpt-5.2", messages=[{"role": "user", "content": "hi"}]
        )
    assert "free gateway is unavailable" in str(exc.value)


def test_legacy_stream_also_raises_on_error_body():
    client = make_client(FakeResponse(status_code=200, text='"Invalid Request"'))
    stream = client.chat.completions.create(
        model="gpt-5.2", messages=[{"role": "user", "content": "hi"}], stream=True
    )
    with pytest.raises(IOError):
        list(stream)


def test_legacy_successful_reply_is_still_parsed():
    client = make_client(FakeResponse(status_code=200, text='"The answer is 3."'))
    result = client.chat.completions.create(
        model="gpt-5.2", messages=[{"role": "user", "content": "how many r?"}]
    )
    assert result.choices[0].message.content == "The answer is 3."


def test_known_error_markers_are_enumerated():
    assert "invalid request" in LEGACY_ERROR_BODIES


# --- validation --------------------------------------------------------------


def test_invalid_model_raises_value_error():
    client = make_client(completion_response(), api_key="k")
    with pytest.raises(ValueError):
        client.chat.completions.create(
            model="does-not-exist", messages=[{"role": "user", "content": "hi"}]
        )


def test_blank_messages_raise_value_error():
    client = make_client(completion_response(), api_key="k")
    with pytest.raises(ValueError):
        client.chat.completions.create(
            model="gpt-5.2", messages=[{"role": "user", "content": "  "}]
        )


def test_provider_is_marked_as_requiring_auth():
    assert AI4Chat.required_auth is True


def test_legacy_user_id_is_not_a_hardcoded_constant():
    assert AI4Chat().user_id != AI4Chat().user_id
