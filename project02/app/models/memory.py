from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.task import utc_now


class MemoryStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELETED = "deleted"


class CandidateMemory(BaseModel):
    memory_id: str
    source_task_id: str | None = None
    content: str
    reason: str | None = None
    status: MemoryStatus = MemoryStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    confirmed_at: datetime | None = None
    deleted_at: datetime | None = None

