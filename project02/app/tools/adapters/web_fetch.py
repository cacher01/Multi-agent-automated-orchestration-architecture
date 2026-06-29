from __future__ import annotations

import re
from collections.abc import Mapping
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from app.tools.adapters.base import AdapterResult, ToolAdapterError


class WebFetchAdapter:
    name = "web_fetch"

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        url = str(tool_input.get("url") or "").strip()
        if not url:
            raise ToolAdapterError("invalid_input", "URL is required.")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ToolAdapterError("invalid_url", "Only absolute HTTP(S) URLs are supported.")
        max_chars = int(tool_input.get("max_chars") or 12000)
        response = httpx.get(url, timeout=self.timeout_seconds, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        text = response.text
        title = None
        if "html" in content_type.lower() or "<html" in text.lower():
            title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
            if title_match:
                title = _clean_text(title_match.group(1))
            text = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
        content = _clean_text(text)
        truncated = len(content) > max_chars
        return AdapterResult(
            output={
                "url": str(response.url),
                "title": title,
                "content": content[:max_chars],
                "links": [],
                "truncated": truncated,
            },
            message="URL fetched successfully.",
        )


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()

