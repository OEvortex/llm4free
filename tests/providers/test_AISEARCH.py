import asyncio
import json
import unittest
from collections.abc import Generator as GeneratorType
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from llm4free.AIbase import SearchResponse
from llm4free.AISEARCH import (
    BraveSearch,
    IAsk,
    Monica,
    Perplexity,
    webpilotai,
)
from tests.providers.utils import FakeResp


class FakeStreamResp(FakeResp):
    """A mock response that supports the `with` protocol and streaming."""

    def __init__(
        self,
        status_code: int = 200,
        text: str = "",
        json_data: dict | None = None,
        headers: dict | None = None,
        content: bytes | None = None,
        iter_bytes: list[bytes] | None = None,
        reason: str = "OK",
    ):
        super().__init__(status_code=status_code, text=text, json_data=json_data, headers=headers)
        self.content = content if content is not None else self.text.encode("utf-8")
        self._iter_bytes = iter_bytes or [self.content]
        self.reason = reason

    @property
    def ok(self):
        return self.status_code < 400

    def iter_content(self, chunk_size=1024):
        for chunk in self._iter_bytes:
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestAISEARCHProviders(unittest.TestCase):
    def test_iask_create_url(self):
        ai = IAsk()
        url = ai.create_url("Climate change", mode="academic", detail_level="detailed")
        self.assertIn("mode=academic", url)
        self.assertIn("q=Climate+change", url)
        self.assertIn("options%5Bdetail_level%5D=detailed", url)

    def test_iask_format_html(self):
        ai = IAsk()
        html = "<h1>Title</h1><p>Paragraph</p><div class='footnotes'><li><a href='https://example.com'>Link</a></li></div>"
        out = ai.format_html(html)
        self.assertIn("**Title**", out)
        self.assertIn("Paragraph", out)
        self.assertIn("https://example.com", out)

    @patch("llm4free.AISEARCH.iask_search.AsyncSession")
    def test_iask_search_non_stream(self, mock_async_session):
        response = MagicMock()
        response.status_code = 200
        response.reason = "OK"
        response.text = '<div id="text"><p>Answer</p></div>'

        async def fake_get(*args, **kwargs):
            return response

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.get.side_effect = fake_get
        mock_async_session.return_value = mock_session

        ai = IAsk()
        result = ai.search("Hi")
        self.assertIsInstance(result, SearchResponse)
        self.assertIn("Answer", str(result))

    @patch("llm4free.AISEARCH.iask_search.AsyncSession")
    def test_iask_search_stream(self, mock_async_session):
        response = MagicMock()
        response.status_code = 200
        response.reason = "OK"
        response.text = '<div id="text"><p>Answer</p></div>'

        async def fake_get(*args, **kwargs):
            return response

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.get.side_effect = fake_get
        mock_async_session.return_value = mock_session

        ai = IAsk()
        gen = ai.search("Hi", stream=True)
        self.assertTrue(hasattr(gen, "__iter__"))
        result = "".join(str(x) for x in cast(GeneratorType[Any, Any, Any], gen))
        self.assertIn("Answer", result)

    @patch("llm4free.AISEARCH.monica_search.requests.Session.post")
    def test_monica_search_non_stream(self, mock_post):
        payload = b'{"text":"Hello"}'
        mock_post.return_value = FakeStreamResp(content=payload)

        ai = Monica()
        result = ai.search("Hi")
        self.assertIsInstance(result, SearchResponse)
        self.assertIn("Hello", str(result))

    @patch("llm4free.AISEARCH.monica_search.requests.Session.post")
    def test_monica_search_stream(self, mock_post):
        payload_chunks = [b'{"text":"He"}', b'{"text":"llo"}']
        mock_post.return_value = FakeStreamResp(iter_bytes=payload_chunks)

        ai = Monica()
        gen = ai.search("Hi", stream=True)
        self.assertTrue(hasattr(gen, "__iter__"))
        result = "".join(str(x) for x in cast(GeneratorType[Any, Any, Any], gen))
        self.assertIn("Hello", result)

    @patch("llm4free.AISEARCH.webpilotai_search.requests.Session.post")
    def test_webpilotai_search_non_stream(self, mock_post):
        payload = b'{"data":{"content":"Hi"}}'
        mock_post.return_value = FakeStreamResp(content=payload)

        ai = webpilotai()
        result = ai.search("Hi")
        self.assertIsInstance(result, SearchResponse)
        self.assertIn("Hi", str(result))

    @patch("llm4free.AISEARCH.webpilotai_search.requests.Session.post")
    def test_webpilotai_search_stream(self, mock_post):
        payload_chunks = [b'{"data":{"content":"He"}}', b'{"data":{"content":"llo"}}']
        mock_post.return_value = FakeStreamResp(iter_bytes=payload_chunks)

        ai = webpilotai()
        gen = ai.search("Hi", stream=True)
        result = "".join(str(x) for x in cast(GeneratorType[Any, Any, Any], gen))
        self.assertIn("Hello", result)

    @patch("llm4free.AISEARCH.Perplexity.requests.Session.post")
    def test_perplexity_search_non_stream(self, mock_post):
        payload = b'data: {"step_type": "FINAL", "content": {"answer": "Hello"}}\r\n\r\n'
        mock_post.return_value = FakeStreamResp(content=payload)

        ai = Perplexity()
        result = ai.search("Hi")
        self.assertIsInstance(result, SearchResponse)
        self.assertIn("Hello", str(result))

    @patch("llm4free.AISEARCH.Perplexity.requests.Session.post")
    def test_perplexity_search_stream(self, mock_post):
        payload_chunks = [
            b'data: {"step_type": "FINAL", "content": {"answer": "He"}}\r\n\r\n',
            b'data: {"step_type": "FINAL", "content": {"answer": "Hello"}}\r\n\r\n',
        ]
        mock_post.return_value = FakeStreamResp(iter_bytes=payload_chunks)

        ai = Perplexity()
        gen = ai.search("Hi", stream=True)
        result = "".join(str(x) for x in cast(GeneratorType[Any, Any, Any], gen))
        self.assertIn("Hello", result)

    def test_brave_search_stream_formats_token_deltas(self):
        ai = BraveSearch()
        ai._iter_stream = MagicMock(
            return_value=iter(
                [
                    '{"type":"text_delta","delta":"Read"}',
                    '{"type":"text_delta","delta":"able "}',
                    '{"type":"text_delta","delta":"result"}',
                ]
            )
        )

        chunks = list(ai.search("Hi", stream=True))

        self.assertEqual(len(chunks), 1)
        result = "".join(str(chunk) for chunk in chunks)
        self.assertEqual(result, "Readable result")
        self.assertEqual(str(ai.last_response), result)

    def test_brave_search_raw_stream_preserves_deltas(self):
        ai = BraveSearch()
        raw_lines = [
            '{"type":"text_delta","delta":"Read"}',
            '{"type":"text_delta","delta":"able"}',
        ]
        ai._iter_stream = MagicMock(return_value=iter(raw_lines))

        result = list(ai.search("Hi", stream=True, raw=True))

        self.assertEqual(result, raw_lines)

    def test_brave_search_stream_chunks_long_text_without_splitting_words(self):
        ai = BraveSearch()
        chunks, remainder = ai._drain_readable_chunks("word " * 200 + "remainder", final=True)

        self.assertEqual("".join(chunks), "word " * 200 + "remainder")
        self.assertEqual(remainder, "")
        self.assertTrue(all(len(chunk) <= 800 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
