"""Tests for the SerpBase search engine provider."""

from __future__ import annotations

import os

import pytest

from llm4free.search import SEARCH_AUTH_REQUIRED, SEARCH_PROVIDERS, SerpBase, TextResult


class TestSerpBase:
    """Tests for SerpBase metadata and required-auth behavior."""

    def test_imports(self):
        """SerpBase should be importable from llm4free.search."""
        assert SerpBase is not None

    def test_provider_metadata(self):
        """SerpBase metadata should match expectations."""
        engine = SerpBase()
        assert engine.name == "serpbase"
        assert engine.category == "text"
        assert engine.provider == "google"

    def test_required_auth_flag(self):
        """SerpBase should declare that it requires authentication."""
        assert getattr(SerpBase, "required_auth", False) is True

    def test_search_without_api_key_raises(self):
        """Without SERPBASE_API_KEY, search should raise RuntimeError."""
        engine = SerpBase()
        with pytest.raises(RuntimeError, match="SERPBASE_API_KEY"):
            engine.search("python")

    def test_build_payload_shapes_request(self):
        """Payload should include query, num, and api_key."""
        engine = SerpBase()
        payload = engine.build_payload("openai", "us-en", "moderate", None)
        assert payload["q"] == "openai"
        assert payload["num"] == 10
        assert "api_key" in payload

    def test_api_key_caching(self):
        """_api_key should be cached after first access."""
        engine = SerpBase()
        key1 = engine._api_key
        key2 = engine._api_key
        assert key1 == key2
        assert key1 == ""


class TestSerpBaseRegistry:
    """Tests for SerpBase in the search provider registry."""

    def test_registered_in_search_providers(self):
        """SerpBase should be registered in SEARCH_PROVIDERS."""
        assert "SerpBase" in SEARCH_PROVIDERS
        assert SEARCH_PROVIDERS["SerpBase"] is SerpBase

    def test_registered_in_search_auth_required(self):
        """SerpBase should be in SEARCH_AUTH_REQUIRED."""
        assert "SerpBase" in SEARCH_AUTH_REQUIRED


class TestSerpBaseLive:
    """Live tests for SerpBase (require SERPBASE_API_KEY)."""

    @pytest.mark.live
    def test_text_search_with_api_key(self):
        """With a valid API key, text search should return non-empty results."""
        if not os.environ.get("SERPBASE_API_KEY"):
            pytest.skip("SERPBASE_API_KEY not set")

        engine = SerpBase()
        results = engine.search("lightweight python web framework")
        assert isinstance(results, list)
        assert len(results) >= 1
        for item in results:
            assert isinstance(item, TextResult)
            assert item.title
            assert item.href
            assert item.body


class TestGetAvailableSearchEngines:
    """Tests for the search provider availability helper."""

    def test_serpbase_excluded_when_no_key(self):
        """When api_key is None, SerpBase should be excluded."""
        from llm4free.search import _get_available_search_engines

        available = _get_available_search_engines(None)
        assert "SerpBase" not in available

    def test_serpbase_included_when_key_provided(self):
        """When api_key is provided, SerpBase should be included."""
        from llm4free.search import _get_available_search_engines

        available = _get_available_search_engines("fake-key")
        assert "SerpBase" in available
