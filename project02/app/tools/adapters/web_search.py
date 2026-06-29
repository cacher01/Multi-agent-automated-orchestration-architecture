from __future__ import annotations

import os
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.tools.adapters.base import AdapterResult, ToolAdapterError
from app.tools.policy import WebSearchPolicy


class WebSearchAdapter:
    name = "web_search"

    def __init__(self, policy: WebSearchPolicy, timeout_seconds: float = 10.0) -> None:
        self.policy = policy
        self.timeout_seconds = timeout_seconds

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        provider = self.policy.provider.lower()
        if provider == "tavily":
            return self._execute_tavily(tool_input)
        if provider in {"", "auto", "duckduckgo"}:
            if os.getenv("TAVILY_API_KEY") and provider == "auto":
                return self._execute_tavily(tool_input)
            return self._execute_duckduckgo(tool_input)
        raise ToolAdapterError(
            "provider_not_implemented",
            f"Web search provider is configured but not implemented: {provider}",
        )

    def _execute_tavily(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ToolAdapterError(
                "provider_not_configured",
                "Web search requires TAVILY_API_KEY or another configured provider.",
            )
        query = str(tool_input.get("query") or "").strip()
        if not query:
            raise ToolAdapterError("invalid_input", "Search query is required.")
        if len(query) > 300:
            raise ToolAdapterError("search_query_too_long", "Search query is too long after task normalization.")
        max_results = int(tool_input.get("max_results") or 5)
        try:
            response = httpx.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": max_results},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ToolAdapterError("external_request_failed", self._http_error_message(exc)) from exc
        except httpx.HTTPError as exc:
            raise ToolAdapterError("external_request_failed", "Web search request failed.") from exc
        payload = response.json()
        results = [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("content"),
                "published_at": item.get("published_date"),
                "source": "tavily",
            }
            for item in payload.get("results", [])
            if isinstance(item, Mapping)
        ]
        return AdapterResult(output={"results": results}, message="Web search completed.")

    def _execute_duckduckgo(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        query = str(tool_input.get("query") or "").strip()
        if not query:
            raise ToolAdapterError("invalid_input", "Search query is required.")
        if len(query) > 300:
            raise ToolAdapterError("search_query_too_long", "Search query is too long after task normalization.")
        max_results = int(tool_input.get("max_results") or 5)
        try:
            response = httpx.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ToolAdapterError("external_request_failed", self._http_error_message(exc)) from exc
        except httpx.HTTPError as exc:
            raise ToolAdapterError("external_request_failed", "Web search request failed.") from exc
        parser = _DuckDuckGoParser(max_results=max_results)
        parser.feed(response.text)
        return AdapterResult(output={"results": parser.results}, message="Web search completed.")

    def _http_error_message(self, exc: httpx.HTTPStatusError) -> str:
        status_code = exc.response.status_code
        if status_code == 414:
            return "Web search query was too long for the provider."
        return f"Web search provider returned HTTP {status_code}."


class _DuckDuckGoParser(HTMLParser):
    def __init__(self, max_results: int) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[dict[str, str | None]] = []
        self._in_title = False
        self._in_snippet = False
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._current_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class") or ""
        if tag == "a" and "result__a" in class_name and len(self.results) < self.max_results:
            self._in_title = True
            self._current_title = []
            self._current_snippet = []
            self._current_url = _clean_duckduckgo_url(attrs_dict.get("href") or "")
        elif tag in {"a", "div"} and "result__snippet" in class_name:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
            title = " ".join("".join(self._current_title).split())
            if title:
                self.results.append(
                    {
                        "title": title,
                        "url": self._current_url,
                        "snippet": None,
                        "published_at": None,
                        "source": "duckduckgo",
                    }
                )
        elif tag in {"a", "div"} and self._in_snippet:
            self._in_snippet = False
            snippet = " ".join("".join(self._current_snippet).split())
            if snippet and self.results:
                self.results[-1]["snippet"] = snippet

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)


def _clean_duckduckgo_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.query:
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return unquote(uddg[0])
    return raw_url
