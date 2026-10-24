"""Tests for the Serply search engine provider."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from llm4free.search import SEARCH_AUTH_REQUIRED, SEARCH_PROVIDERS, Serply, TextResult


class TestSerply:
    """Tests for Serply metadata, request shape, and parsing."""

    def test_provider_metadata(self):
        """Serply metadata should match expectations."""
        engine = Serply()
        assert engine.name == "serply"
        assert engine.category == "text"
        assert engine.provider == "google"
        assert Serply.required_auth is True

    def test_search_without_api_key_raises(self, monkeypatch):
        """Without SERPLY_API_KEY, search should raise RuntimeError."""
        monkeypatch.delenv("SERPLY_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="SERPLY_API_KEY"):
            Serply().search("python")

    def test_build_payload_clamps_num(self):
        """Payload should carry the query and clamp num to one results page."""
        engine = Serply()
        assert engine.build_payload("openai", "us-en", "moderate", None) == {
            "q": "openai",
            "num": 10,
        }
        assert engine.build_payload("q", "us-en", "moderate", None, max_results=3)["num"] == 3
        assert engine.build_payload("q", "us-en", "moderate", None, num=50)["num"] == 10

    def test_search_sends_key_in_header_and_parses(self, monkeypatch):
        """The key goes in X-Api-Key, never the query string; results map to TextResult."""
        monkeypatch.setenv("SERPLY_API_KEY", "test-key")
        engine = Serply()
        resp = MagicMock()
        resp.json.return_value = {
            "results": [
                {"title": "A", "link": "https://a.example", "description": "first"},
                {"title": "B", "link": "not-a-url", "description": "dropped"},
                {"title": "C", "link": "https://c.example", "description": "third"},
            ]
        }
        engine.http_client = MagicMock()
        engine.http_client.client.get.return_value = resp

        results = engine.search("python", max_results=2)

        assert results == [
            TextResult(title="A", href="https://a.example", body="first"),
            TextResult(title="C", href="https://c.example", body="third"),
        ]
        _, kwargs = engine.http_client.client.get.call_args
        assert kwargs["params"] == {"q": "python", "num": 2}
        assert kwargs["headers"] == {"X-Api-Key": "test-key", "User-Agent": "llm4free"}

    def test_search_returns_empty_on_api_error(self, monkeypatch):
        """HTTP errors are logged and return an empty list."""
        monkeypatch.setenv("SERPLY_API_KEY", "test-key")
        engine = Serply()
        engine.http_client = MagicMock()
        engine.http_client.client.get.return_value.raise_for_status.side_effect = RuntimeError(
            "401"
        )
        assert engine.search("python") == []

    def test_registered(self):
        """Serply should be registered and marked as requiring auth."""
        assert SEARCH_PROVIDERS["Serply"] is Serply
        assert "Serply" in SEARCH_AUTH_REQUIRED


class TestSerplyLive:
    """Live tests for Serply (require SERPLY_API_KEY)."""

    @pytest.mark.live
    def test_text_search_with_api_key(self):
        """With a valid API key, text search should return non-empty results."""
        if not os.environ.get("SERPLY_API_KEY"):
            pytest.skip("SERPLY_API_KEY not set")

        results = Serply().search("lightweight python web framework")
        assert len(results) >= 1
        for item in results:
            assert isinstance(item, TextResult)
            assert item.title
            assert item.href
