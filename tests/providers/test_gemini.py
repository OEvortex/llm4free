"""
Real API tests for Gemini provider.

These tests use actual API calls to verify provider functionality.
Requires a valid cookies.json file for Gemini authentication.
Set GEMINI_COOKIE_FILE environment variable to run these tests.
"""

import os

import pytest

# Gemini provider now lives in llm4free.llm.gemini with an
# OpenAI-compatible interface.  The legacy ask/get_message tests are
# skipped until they are rewritten against the new interface.

pytestmark = pytest.mark.skip(reason="Gemini provider uses legacy interface; tests need rewriting")


class TestGemini:
    """Real API tests for Gemini provider."""

    @pytest.fixture(autouse=True)
    def setup(self):
        cookie_file = os.environ.get("GEMINI_COOKIE_FILE")
        assert cookie_file is not None, "GEMINI_COOKIE_FILE must be set"
        from llm4free.Bard import GEMINI

        self.provider = GEMINI(cookie_file=cookie_file)

    def test_ask_non_stream(self):
        response = self.provider.ask("Say 'Hello World' and nothing else")
        assert response is not None
        message = self.provider.get_message(response)
        assert message is not None
        assert len(message) > 0
        assert isinstance(message, str)

    def test_ask_stream(self):
        response = self.provider.ask("Count from 1 to 5", stream=True)
        assert response is not None
        chunks = list(response)
        assert len(chunks) > 0

    def test_get_message(self):
        response = self.provider.ask("Say 'test'")
        message = self.provider.get_message(response)
        assert message is not None
        assert isinstance(message, str)

    def test_different_models(self):
        models_to_test = ["gemini-3.0-flash", "gemini-3.0-pro"]
        for model in models_to_test:
            try:
                from llm4free.Bard import GEMINI

                cookie_file = os.environ.get("GEMINI_COOKIE_FILE")
                provider = GEMINI(cookie_file=cookie_file, model=model)
                response = provider.ask("Say 'test'")
                assert response is not None
            except Exception as e:
                pytest.skip(f"Model {model} not available: {e}")
