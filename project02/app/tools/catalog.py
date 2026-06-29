from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.tools.base import ToolName


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    category: str
    description: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)


DEFAULT_TOOLS: dict[str, ToolDefinition] = {
    ToolName.WEB_SEARCH.value: ToolDefinition(
        name=ToolName.WEB_SEARCH.value,
        category="information",
        description="Plan a current-information web search through a configured provider.",
        input_schema={"query": "string", "recency_days": "integer|null", "domains": "list[string]", "max_results": "integer"},
        output_schema={"results": "list[search_result]"},
    ),
    ToolName.WEB_FETCH.value: ToolDefinition(
        name=ToolName.WEB_FETCH.value,
        category="information",
        description="Plan fetching and extracting content from a specific URL.",
        input_schema={"url": "string", "max_chars": "integer", "extract_mode": "text|metadata|links"},
        output_schema={"url": "string", "title": "string|null", "content": "string", "links": "list[string]"},
    ),
    ToolName.WEATHER_QUERY.value: ToolDefinition(
        name=ToolName.WEATHER_QUERY.value,
        category="information",
        description="Plan a simple weather lookup.",
        input_schema={"location": "string", "date": "string|null", "units": "metric|imperial"},
        output_schema={"location": "string", "date": "string", "summary": "string", "source": "string"},
    ),
    ToolName.TIME_LOOKUP.value: ToolDefinition(
        name=ToolName.TIME_LOOKUP.value,
        category="information",
        description="Plan current-time lookup or timezone conversion.",
        input_schema={"timezone": "string", "operation": "now|convert"},
        output_schema={"timezone": "string", "datetime": "string"},
    ),
    ToolName.FILE_READER.value: ToolDefinition(
        name=ToolName.FILE_READER.value,
        category="workspace",
        description="Plan reading a file from an authorized workspace path.",
        input_schema={"path": "string", "max_chars": "integer"},
        output_schema={"path": "string", "content": "string", "truncated": "boolean"},
    ),
    ToolName.FILE_WRITER.value: ToolDefinition(
        name=ToolName.FILE_WRITER.value,
        category="workspace",
        description="Plan creating or updating a file in an authorized workspace path.",
        input_schema={"path": "string", "operation": "create|update|append", "content": "string", "expected_hash": "string|null"},
        output_schema={"path": "string", "operation": "string", "bytes_written": "integer"},
    ),
    ToolName.CODE_EXECUTOR.value: ToolDefinition(
        name=ToolName.CODE_EXECUTOR.value,
        category="workspace",
        description="Plan running a permission-checked project command.",
        input_schema={"command": "list[string]", "cwd": "string", "timeout_seconds": "integer"},
        output_schema={"exit_code": "integer", "stdout": "string", "stderr": "string", "duration_seconds": "number"},
    ),
    ToolName.DATABASE_QUERY.value: ToolDefinition(
        name=ToolName.DATABASE_QUERY.value,
        category="data",
        description="Plan a structured query against application-owned task data.",
        input_schema={"query_type": "task|logs|memory|plan|tool_invocations", "filters": "object"},
        output_schema={"rows": "list[object]", "row_count": "integer"},
    ),
    ToolName.CALCULATOR.value: ToolDefinition(
        name=ToolName.CALCULATOR.value,
        category="data",
        description="Plan deterministic arithmetic, conversion, or simple formula evaluation.",
        input_schema={"expression": "string", "mode": "arithmetic|unit_conversion"},
        output_schema={"result": "string", "steps": "list[string]"},
    ),
    ToolName.API_CALLER.value: ToolDefinition(
        name=ToolName.API_CALLER.value,
        category="integration",
        description="Plan a call to an approved external API domain or service.",
        input_schema={"method": "GET|POST", "url": "string", "headers": "object", "params": "object", "json": "object"},
        output_schema={"status_code": "integer", "headers": "object", "body": "object"},
    ),
}

