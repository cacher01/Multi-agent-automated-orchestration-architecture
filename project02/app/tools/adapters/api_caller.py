from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

from app.tools.adapters.base import AdapterResult, ToolAdapterError
from app.tools.policy import ApiCallerPolicy


class ApiCallerAdapter:
    name = "api_caller"

    def __init__(self, policy: ApiCallerPolicy, timeout_seconds: float = 10.0) -> None:
        self.policy = policy
        self.timeout_seconds = timeout_seconds

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        method = str(tool_input.get("method") or "GET").upper()
        url = str(tool_input.get("url") or "").strip()
        if method not in {"GET", "POST"}:
            raise ToolAdapterError("invalid_method", "Only GET and POST API calls are supported.")
        host = urlparse(url).netloc.lower()
        if not host:
            raise ToolAdapterError("invalid_url", "API URL must be absolute.")
        if host not in {domain.lower() for domain in self.policy.allowed_domains}:
            raise ToolAdapterError("domain_not_allowed", f"API domain is not allowed: {host}")
        response = httpx.request(
            method,
            url,
            headers=_mapping(tool_input.get("headers")),
            params=_mapping(tool_input.get("params")),
            json=_mapping(tool_input.get("json")) if method == "POST" else None,
            timeout=self.timeout_seconds,
        )
        body: Any
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return AdapterResult(
            output={"status_code": response.status_code, "headers": dict(response.headers), "body": body},
            message="API call completed.",
        )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}

