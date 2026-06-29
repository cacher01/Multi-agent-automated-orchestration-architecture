from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.models.event import TaskEvent
from app.storage.base import Storage

SENSITIVE_MARKERS = ("api_key", "apikey", "authorization", "bearer", "secret", "token")


class TaskLogger:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def log_event(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        safe_payload = self._redact(payload or {})
        json.dumps(safe_payload)
        self.storage.append_event(
            TaskEvent(
                event_id=str(uuid4()),
                task_id=task_id,
                event_type=event_type,
                payload=safe_payload,
            )
        )

    def get_logs(self, task_id: str) -> list[TaskEvent]:
        return self.storage.get_events(task_id)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if any(marker in key_text for marker in SENSITIVE_MARKERS):
                    redacted[key] = "***"
                else:
                    redacted[key] = self._redact(item)
            return redacted
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value

