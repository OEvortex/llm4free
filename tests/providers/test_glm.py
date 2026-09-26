"""Mocked tests for the OpenAI-compatible GLM provider."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from llm4free.llm.glm import GLM, CaptchaRequiredError
from llm4free.llm.utils import ChatCompletion, ChatCompletionChunk
from tests.providers.utils import FakeResp


class StreamResponse(FakeResp):
    def __init__(self, events: list[dict[str, Any]], status_code: int = 200) -> None:
        lines = [f"data: {json.dumps(event)}" for event in events]
        super().__init__(status_code=status_code, text="\n".join(lines))
        self.status_code = status_code
        self._lines = [line.encode() for line in lines]

    def iter_lines(self, *args: Any, **kwargs: Any):
        yield from self._lines


def completion_event(phase: str, delta: str = "") -> dict[str, Any]:
    return {"type": "chat:completion", "data": {"phase": phase, "delta_content": delta}}


def test_model_resolution_and_signature() -> None:
    provider = GLM()
    provider._token = "token"
    provider._user_id = "user-id"
    provider._model_map = {"GLM-5.3-Flash": "x-preview-l", "GLM-5.2": "glm-5.2"}
    assert provider.resolve_model("GLM-5.2") == "glm-5.2"
    assert provider.resolve_model("x-preview-l") == "x-preview-l"
    assert provider.resolve_model("missing") == "x-preview-l"
    signature = GLM._compute_signature("request", "123", "user-id")
    source = "requestId=request,timestamp=123,user_id=user-id"
    assert signature == hmac.new(b"", source.encode(), hashlib.sha256).hexdigest()


def test_non_stream_request_and_sse_parse() -> None:
    provider = GLM()
    provider._token = "token"
    provider._user_id = "user-id"
    provider._model_map = {"GLM-5.3-Flash": "x-preview-l"}
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> StreamResponse:
        if url.endswith("/api/v1/chats/new"):
            return FakeResp(json_data={"id": "chat-1"})
        captured["url"] = url
        captured.update(kwargs)
        return StreamResponse(
            [
                completion_event("thinking", "reason"),
                completion_event("answer", "Hello"),
                completion_event("answer", " world"),
                {
                    "type": "chat:completion",
                    "data": {
                        "phase": "other",
                        "usage": {
                            "prompt_tokens": 3,
                            "completion_tokens": 2,
                            "total_tokens": 5,
                        },
                    },
                },
                completion_event("done"),
            ]
        )

    with patch.object(provider.session, "post", side_effect=fake_post):
        response = provider.chat.completions.create(
            model="GLM-5.3-Flash",
            messages=[{"role": "user", "content": "Hi"}],
            web_search=True,
        )

    assert isinstance(response, ChatCompletion)
    assert response.choices[0].message.content == "Hello world"
    assert response.choices[0].message.reasoning_content == "reason"
    assert response.usage.total_tokens == 5
    assert json.loads(captured["data"])["messages"] == [{"role": "user", "content": "Hi"}]
    assert json.loads(captured["data"])["features"]["web_search"] is True
    params = parse_qs(urlparse(captured["url"]).query)
    assert params["token"] == ["token"]
    assert params["user_id"] == ["user-id"]
    assert captured["headers"]["x-signature"] == GLM._compute_signature(
        params["requestId"][0], params["timestamp"][0], "user-id"
    )


def test_streaming_chunks_include_content_reasoning_and_finish() -> None:
    provider = GLM()
    provider._token = "token"
    provider._user_id = "user-id"
    provider._model_map = {"GLM-5.3-Flash": "x-preview-l"}

    def fake_post(url: str, **kwargs: Any) -> StreamResponse:
        if url.endswith("/api/v1/chats/new"):
            return FakeResp(json_data={"id": "chat-1"})
        return StreamResponse(
            [
                completion_event("thinking", "think"),
                completion_event("answer", "Hi"),
                completion_event("done"),
            ]
        )

    with patch.object(provider.session, "post", side_effect=fake_post):
        chunks = list(
            provider.chat.completions.create(
                model="GLM-5.3-Flash",
                messages=[{"role": "user", "content": "Hi"}],
                stream=True,
            )
        )

    assert all(isinstance(chunk, ChatCompletionChunk) for chunk in chunks)
    assert chunks[0].choices[0].delta.reasoning_content == "think"
    assert chunks[1].choices[0].delta.content == "Hi"
    assert chunks[-1].choices[0].finish_reason == "stop"


def test_stream_captcha_error_is_detected() -> None:
    response = StreamResponse(
        [
            {
                "type": "chat:completion",
                "data": {"error": {"code": "FRONTEND_CAPTCHA_REQUIRED", "detail": "captcha"}},
            }
        ]
    )
    try:
        list(GLM._parse_stream(response))
    except CaptchaRequiredError as error:
        assert "captcha" in str(error)
    else:
        raise AssertionError("captcha error was not raised")


def test_captcha_retry_submits_solved_token() -> None:
    provider = GLM()
    provider._token = "token"
    provider._user_id = "user-id"
    provider._model_map = {"GLM-5.3-Flash": "x-preview-l"}
    completions: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> Any:
        if url.endswith("/api/v1/chats/new"):
            return FakeResp(json_data={"id": "chat-1"})
        completions.append(json.loads(kwargs["data"]))
        if len(completions) == 1:
            return FakeResp(status_code=403, text="FRONTEND_CAPTCHA")
        return StreamResponse(
            [
                completion_event("answer", "ok"),
                completion_event("done"),
            ]
        )

    with (
        patch.object(provider.session, "post", side_effect=fake_post),
        patch("llm4free.llm.glm.get_captcha_verify_param", return_value="captcha-token"),
        patch("llm4free.llm.glm.invalidate_captcha_token"),
    ):
        response = provider.chat.completions.create(
            model="GLM-5.3-Flash",
            messages=[{"role": "user", "content": "Hi"}],
        )

    assert isinstance(response, ChatCompletion)
    assert response.choices[0].message.content == "ok"
    assert completions[0]["captcha_verify_param"] == ""
    assert completions[1]["captcha_verify_param"] == "captcha-token"
