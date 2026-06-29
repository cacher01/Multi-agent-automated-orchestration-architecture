from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterResult:
    output: Mapping[str, Any] = field(default_factory=dict)
    message: str = "Tool executed successfully."


class ToolAdapter(Protocol):
    name: str

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        ...


class ToolAdapterError(Exception):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_error(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}

