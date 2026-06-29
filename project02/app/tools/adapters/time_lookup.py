from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.tools.adapters.base import AdapterResult, ToolAdapterError


class TimeLookupAdapter:
    name = "time_lookup"

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        timezone = str(tool_input.get("timezone") or "UTC")
        operation = str(tool_input.get("operation") or "now")
        if operation not in {"now", "convert"}:
            raise ToolAdapterError("invalid_input", f"Unsupported time operation: {operation}")
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ToolAdapterError("invalid_timezone", f"Unknown timezone: {timezone}") from exc
        current = datetime.now(zone)
        return AdapterResult(
            output={"timezone": timezone, "datetime": current.isoformat()},
            message="Time lookup completed.",
        )

