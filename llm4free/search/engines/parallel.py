"""Parallel web search engine using the public MCP server."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from ..base import BaseSearchEngine
from ..results import TextResult

MCP_URL = "https://search.parallel.ai/mcp"
MCP_PROTOCOL_VERSION = "2025-06-18"


class Parallel(BaseSearchEngine[TextResult]):
    """LLM-friendly web search through Parallel's public MCP endpoint.

    The endpoint does not require an API key. Public access is subject to
    Parallel's free-tier rate limits and customer terms.
    """

    name = "parallel"
    category = "text"
    provider = "parallel"

    search_url = MCP_URL
    search_method = "POST"

    def __init__(self, proxy: str | None = None, timeout: int | None = None, verify: bool = True):
        """Initialize the Parallel MCP search provider."""
        super().__init__(proxy=proxy, timeout=timeout, verify=verify)
        self._mcp_session_id: str | None = None
        self._mcp_initialized = False
        self._request_id = 0
        self._search_session_id = uuid4().hex

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build a ``web_search`` MCP tool payload.

        ``region``, ``safesearch``, ``timelimit``, and ``page`` are accepted for
        compatibility with :class:`BaseSearchEngine`, but Parallel determines
        relevance independently of those values.
        """
        del region, safesearch, timelimit, page

        objective = str(kwargs.get("objective") or query).strip()
        if not objective:
            raise ValueError("Parallel search requires a non-empty query or objective")

        raw_queries = kwargs.get("search_queries")
        if raw_queries is None:
            raw_queries = [query]
        if isinstance(raw_queries, (str, bytes)) or not isinstance(raw_queries, Sequence):
            raise TypeError("search_queries must be a sequence of strings")

        search_queries = [str(item).strip() for item in raw_queries]
        if not search_queries or any(not item for item in search_queries):
            raise ValueError("search_queries must contain at least one non-empty query")

        arguments: dict[str, Any] = {
            "objective": objective,
            "search_queries": search_queries,
            "session_id": str(kwargs.get("session_id") or self._search_session_id),
        }
        model_name = kwargs.get("model_name")
        if model_name:
            arguments["model_name"] = str(model_name)

        return {"name": "web_search", "arguments": arguments}

    def _decode_rpc_response(self, payload: str) -> dict[str, Any]:
        """Decode a plain JSON or Server-Sent Events JSON-RPC response."""
        text = payload.strip()
        if not text:
            raise RuntimeError("Parallel MCP returned an empty response")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        if text.startswith("{"):
            decoded = json.loads(text)
            if not isinstance(decoded, dict):
                raise RuntimeError("Parallel MCP returned an invalid JSON-RPC response")
            return decoded

        response: dict[str, Any] | None = None
        for event in text.split("\n\n"):
            data_lines = [
                line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
            ]
            if not data_lines:
                continue
            decoded = json.loads("\n".join(data_lines))
            if isinstance(decoded, dict) and "id" in decoded:
                response = decoded

        if response is None:
            raise RuntimeError("Parallel MCP SSE response did not contain a JSON-RPC result")
        return response

    def _post(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        notify: bool = False,
        timeout: int | None = None,
    ) -> dict[str, Any] | None:
        """Send one JSON-RPC request to the Parallel MCP server."""
        data: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notify:
            self._request_id += 1
            data["id"] = self._request_id
        if params is not None:
            data["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "python-mcp/1",
        }
        if self._mcp_session_id:
            headers["Mcp-Session-Id"] = self._mcp_session_id

        response = self.http_client.client.post(
            self.search_url,
            json=data,
            headers=headers,
            timeout=timeout if timeout is not None else self.http_client.timeout,
        )
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._mcp_session_id = session_id

        if response.status_code < 200 or response.status_code >= 300:
            detail = getattr(response, "text", "").strip()
            suffix = f": {detail[:500]}" if detail else ""
            raise RuntimeError(
                f"Parallel MCP request failed with HTTP {response.status_code}{suffix}"
            )
        if notify:
            return None

        rpc_response = self._decode_rpc_response(response.text)
        error = rpc_response.get("error")
        if error:
            if isinstance(error, Mapping):
                code = error.get("code", "unknown")
                message = error.get("message", "unknown error")
                raise RuntimeError(f"Parallel MCP error ({code}): {message}")
            raise RuntimeError(f"Parallel MCP error: {error}")

        result = rpc_response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Parallel MCP response did not include a result object")
        return result

    def _ensure_mcp_session(self, timeout: int | None = None) -> None:
        """Initialize the MCP transport once per provider instance."""
        if self._mcp_initialized:
            return

        self._post(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "llm4free", "version": "1"},
            },
            timeout=timeout,
        )
        self._post("notifications/initialized", notify=True, timeout=timeout)
        self._mcp_initialized = True

    @staticmethod
    def _content_text(result: Mapping[str, Any]) -> str:
        """Return the server's concatenated text content."""
        content = result.get("content", [])
        if not isinstance(content, list):
            return ""
        return "\n".join(
            str(item["text"])
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "text" and item.get("text")
        ).strip()

    def _call_web_search(
        self,
        query: str,
        *,
        objective: str | None = None,
        search_queries: Sequence[str] | None = None,
        session_id: str | None = None,
        model_name: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Initialize MCP if needed and call its ``web_search`` tool."""
        self._ensure_mcp_session(timeout=timeout)
        payload = self.build_payload(
            query=query,
            region="us-en",
            safesearch="moderate",
            timelimit=None,
            page=1,
            objective=objective,
            search_queries=search_queries,
            session_id=session_id,
            model_name=model_name,
        )
        result = self._post("tools/call", payload, timeout=timeout)
        assert result is not None
        if result.get("isError"):
            raise RuntimeError(f"Parallel web search failed: {self._content_text(result)}")
        return result

    def search_text(
        self,
        query: str,
        *,
        objective: str | None = None,
        search_queries: Sequence[str] | None = None,
        session_id: str | None = None,
        model_name: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """Search the web and return Parallel's raw MCP text content."""
        result = self._call_web_search(
            query,
            objective=objective,
            search_queries=search_queries,
            session_id=session_id,
            model_name=model_name,
            timeout=timeout,
        )
        return self._content_text(result)

    def search(
        self,
        query: str,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        page: int = 1,
        **kwargs: Any,
    ) -> list[TextResult]:
        """Run a text search and convert Parallel's results to ``TextResult`` objects."""
        del region, safesearch, timelimit, page

        result = self._call_web_search(
            query,
            objective=kwargs.pop("objective", None),
            search_queries=kwargs.pop("search_queries", None),
            session_id=kwargs.pop("session_id", None),
            model_name=kwargs.pop("model_name", None),
            timeout=kwargs.pop("timeout", None),
        )
        max_results = kwargs.pop("max_results", None)
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(f"Unexpected Parallel search arguments: {unexpected}")

        raw_results: list[object] = []
        text = self._content_text(result)
        structured_content = result.get("structuredContent")
        if isinstance(structured_content, Mapping):
            structured_results = structured_content.get("results")
            if isinstance(structured_results, list):
                raw_results = structured_results

        if not raw_results and text:
            try:
                decoded = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                decoded = None
            if isinstance(decoded, Mapping) and isinstance(decoded.get("results"), list):
                raw_results = decoded["results"]

        def to_text_result(item: Mapping[str, Any]) -> TextResult:
            excerpts = item.get("excerpts", [])
            if isinstance(excerpts, (list, tuple)):
                body = "\n\n".join(str(excerpt) for excerpt in excerpts)
            else:
                body = str(excerpts or "")
            return TextResult(
                title=str(item.get("title") or ""),
                href=str(item.get("url") or ""),
                body=body,
            )

        results = [to_text_result(item) for item in raw_results if isinstance(item, Mapping)]  # ty:ignore[invalid-argument-type]
        if not results and text:
            results = [TextResult(body=text)]

        if max_results is None:
            return results
        try:
            limit = int(max_results)
        except (TypeError, ValueError) as exc:
            raise TypeError("max_results must be an integer") from exc
        if limit < 0:
            raise ValueError("max_results must be non-negative")
        return results[:limit]

    def run(self, *args: Any, **kwargs: Any) -> list[TextResult]:
        """Run a text search using the CLI-compatible positional interface."""
        query = args[0] if args else kwargs.pop("keywords", None)
        if query is None:
            query = kwargs.pop("query", None)
        if query is None:
            raise ValueError("Parallel search requires a query")
        if len(args) > 1:
            kwargs.setdefault("region", args[1])
        if len(args) > 2:
            kwargs.setdefault("safesearch", args[2])
        if len(args) > 3:
            kwargs.setdefault("max_results", args[3])
        return self.search(query, **kwargs)
