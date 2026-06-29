from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from app.tools.adapters.base import AdapterResult, ToolAdapterError


class DatabaseQueryAdapter:
    name = "database_query"

    def __init__(self, storage: Any | None = None) -> None:
        self.storage = storage

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        if self.storage is None:
            raise ToolAdapterError("storage_unavailable", "Database query tool requires a storage dependency.")
        query_type = str(tool_input.get("query_type") or "")
        filters_value = tool_input.get("filters")
        filters: Mapping[str, Any] = filters_value if isinstance(filters_value, Mapping) else {}
        rows: list[dict[str, Any]]
        if query_type == "task":
            task_id = str(filters.get("task_id") or "")
            task = self.storage.get_task(task_id)
            rows = [_to_dict(task)] if task is not None else []
        elif query_type == "logs":
            task_id = str(filters.get("task_id") or "")
            rows = [_to_dict(item) for item in self.storage.get_events(task_id)]
        elif query_type == "memory":
            rows = [_to_dict(item) for item in self.storage.get_memories()]
        else:
            raise ToolAdapterError("invalid_query_type", f"Unsupported database query_type: {query_type}")
        return AdapterResult(output={"rows": rows, "row_count": len(rows)}, message="Database query completed.")


def _to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": str(value)}
