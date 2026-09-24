"""Tests for the Parallel MCP search provider."""

from __future__ import annotations

import json
from typing import Any

import pytest

from llm4free.search import SEARCH_AUTH_REQUIRED, SEARCH_PROVIDERS, Parallel, TextResult


class TestParallelMetadata:
    """Tests for Parallel provider metadata and registration."""

    def test_provider_metadata(self) -> None:
        """Parallel should expose the expected text-search metadata."""
        engine = Parallel()

        assert engine.name == "parallel"
        assert engine.category == "text"
        assert engine.provider == "parallel"
        assert engine.required_auth is False

    def test_registered_in_search_providers(self) -> None:
        """Parallel should be exported through the search provider registry."""
        assert SEARCH_PROVIDERS["Parallel"] is Parallel
        assert "Parallel" not in SEARCH_AUTH_REQUIRED

    def test_registered_in_engines(self) -> None:
        """Parallel should be available as a low-level text engine."""
        from llm4free.search.engines import ENGINES

        assert ENGINES["text"]["parallel"] is Parallel

    def test_registered_in_cli(self) -> None:
        """Parallel should be available through the CLI engine map."""
        from llm4free.cli import ENGINES

        assert ENGINES["parallel"] is Parallel


class TestParallelPayload:
    """Tests for Parallel MCP payload construction."""

    def test_build_payload(self) -> None:
        """The default payload should search for the supplied query."""
        engine = Parallel()

        payload = engine.build_payload("python 3.15", "us-en", "moderate", None, 1)

        assert payload["name"] == "web_search"
        assert payload["arguments"]["objective"] == "python 3.15"
        assert payload["arguments"]["search_queries"] == ["python 3.15"]
        assert len(payload["arguments"]["session_id"]) >= 32

    def test_build_payload_accepts_multiple_queries(self) -> None:
        """Optional objective and related query variants should be forwarded."""
        engine = Parallel()

        payload = engine.build_payload(
            "python release",
            "us-en",
            "moderate",
            None,
            1,
            objective="Find the latest Python release",
            search_queries=["latest Python release", "Python release schedule"],
            model_name="test-model",
        )

        assert payload["arguments"]["objective"] == "Find the latest Python release"
        assert payload["arguments"]["search_queries"] == [
            "latest Python release",
            "Python release schedule",
        ]
        assert payload["arguments"]["model_name"] == "test-model"

    def test_empty_query_list_is_rejected(self) -> None:
        """At least one search query is required."""
        engine = Parallel()

        with pytest.raises(ValueError, match="at least one"):
            engine.build_payload(
                "python", "us-en", "moderate", None, 1, search_queries=[]
            )


class TestParallelSearch:
    """Tests for decoding Parallel search responses."""

    def test_search_converts_structured_results(self) -> None:
        """MCP structured content should become typed text results."""
        engine = Parallel()
        result = {
            "isError": False,
            "structuredContent": {
                "results": [
                    {
                        "url": "https://www.python.org/downloads/",
                        "title": "Python downloads",
                        "excerpts": ["Download Python", "Python 3.15 beta"],
                    }
                ]
            },
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(engine, "_call_web_search", lambda *args, **kwargs: result)
            results = engine.search("python 3.15", max_results=1)

        assert results == [
            TextResult(
                title="Python downloads",
                href="https://www.python.org/downloads/",
                body="Download Python\n\nPython 3.15 beta",
            )
        ]

    def test_search_decodes_json_text_fallback(self) -> None:
        """Older MCP responses without structured content should still work."""
        engine = Parallel()
        payload = {
            "results": [
                {
                    "url": "https://docs.python.org/3.15/",
                    "title": "Python 3.15 documentation",
                    "excerpts": ["Python 3.15 reference"],
                }
            ]
        }
        result = {"content": [{"type": "text", "text": json.dumps(payload)}]}

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(engine, "_call_web_search", lambda *args, **kwargs: result)
            results = engine.search("python 3.15")

        assert len(results) == 1
        assert results[0].href == "https://docs.python.org/3.15/"

    def test_search_text_returns_raw_content(self) -> None:
        """search_text should retain the endpoint's text-content behavior."""
        engine = Parallel()
        result = {
            "content": [
                {"type": "text", "text": "first result"},
                {"type": "image", "data": "ignored"},
                {"type": "text", "text": "second result"},
            ]
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(engine, "_call_web_search", lambda *args, **kwargs: result)
            text = engine.search_text("python")

        assert text == "first result\nsecond result"

    def test_max_results_is_applied_locally(self) -> None:
        """max_results should limit the fixed-size Parallel response."""
        engine = Parallel()
        result = {
            "structuredContent": {
                "results": [
                    {"url": f"https://example.com/{index}", "title": str(index)}
                    for index in range(3)
                ]
            }
        }

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(engine, "_call_web_search", lambda *args, **kwargs: result)
            results = engine.search("python", max_results=2)

        assert [result.title for result in results] == ["0", "1"]

    def test_tool_error_is_raised(self) -> None:
        """An MCP tool-level error should not be returned as empty results."""
        engine = Parallel()
        result = {"isError": True, "content": [{"type": "text", "text": "rate limited"}]}

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(engine, "_ensure_mcp_session", lambda *args, **kwargs: None)
            monkeypatch.setattr(engine, "_post", lambda *args, **kwargs: result)
            with pytest.raises(RuntimeError, match="rate limited"):
                engine.search("python")


class TestParallelMCPTransport:
    """Tests for JSON-RPC and SSE transport handling."""

    def test_plain_json_response_and_session_header(self, monkeypatch) -> None:
        """RPC IDs and the MCP session header should be tracked per instance."""
        engine = Parallel(timeout=20)
        captured: dict[str, Any] = {}

        class FakeResponse:
            status_code = 200
            headers = {"Mcp-Session-Id": "session-123"}
            text = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

        def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(engine.http_client.client, "post", fake_post)
        result = engine._post("ping", {"value": 1})

        assert result == {"ok": True}
        assert engine._mcp_session_id == "session-123"
        assert captured["url"] == engine.search_url
        assert captured["json"]["id"] == 1
        assert "Mcp-Session-Id" not in captured["headers"]
        assert captured["timeout"] == 20

        engine._post("ping")
        assert captured["headers"]["Mcp-Session-Id"] == "session-123"

    def test_sse_response_decoding(self) -> None:
        """CRLF SSE framing should be normalized before JSON decoding."""
        engine = Parallel()
        payload = 'event: message\r\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\r\n\r\n'

        assert engine._decode_rpc_response(payload) == {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"ok": True},
        }

    def test_rpc_error_is_raised(self, monkeypatch) -> None:
        """JSON-RPC errors should include their server-provided code and message."""
        engine = Parallel()

        class FakeResponse:
            status_code = 200
            headers: dict[str, str] = {}
            text = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            )

        monkeypatch.setattr(engine.http_client.client, "post", lambda *args, **kwargs: FakeResponse())

        with pytest.raises(RuntimeError, match=r"-32601.*Method not found"):
            engine._post("missing")


@pytest.mark.live
class TestParallelLive:
    """Live tests for Parallel's public MCP endpoint."""

    def test_text_search(self) -> None:
        """A public MCP search should return typed results."""
        engine = Parallel(timeout=60)

        results = engine.search("python 3.15", max_results=2)

        assert isinstance(results, list)
        assert results
        assert all(isinstance(item, TextResult) for item in results)
        assert all(item.href for item in results)
        assert all(item.body for item in results)
