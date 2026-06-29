from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4


class MemoryStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELETED = "deleted"


@dataclass
class CandidateMemory:
    content: str
    reason: str
    source_task_id: str | None = None
    status: str = MemoryStatus.PENDING.value
    memory_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: datetime | None = None
    deleted_at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "source_task_id": self.source_task_id,
            "content": self.content,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


class MemoryStore(Protocol):
    def save_memory(self, memory: CandidateMemory) -> None:
        ...

    def update_memory(self, memory: CandidateMemory) -> None:
        ...


class UserPreferenceStore:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store
        self._memories: dict[str, CandidateMemory] = {}

    def create_candidate(self, *, content: str, reason: str, source_task_id: str | None = None) -> CandidateMemory:
        memory = CandidateMemory(content=content, reason=reason, source_task_id=source_task_id)
        self._memories[memory.memory_id] = memory
        if self._store is not None:
            self._store.save_memory(memory)
        return memory

    def list_memories(self, *, include_deleted: bool = False) -> list[CandidateMemory]:
        memories = list(self._memories.values())
        if not include_deleted:
            memories = [memory for memory in memories if memory.status != MemoryStatus.DELETED.value]
        return sorted(memories, key=lambda memory: memory.created_at)

    def get_memory(self, memory_id: str) -> CandidateMemory:
        return self._memories[memory_id]

    def approve(self, memory_id: str) -> CandidateMemory:
        memory = self.get_memory(memory_id)
        memory.status = MemoryStatus.APPROVED.value
        memory.confirmed_at = datetime.now(timezone.utc)
        self._update(memory)
        return memory

    def reject(self, memory_id: str) -> CandidateMemory:
        memory = self.get_memory(memory_id)
        memory.status = MemoryStatus.REJECTED.value
        memory.confirmed_at = datetime.now(timezone.utc)
        self._update(memory)
        return memory

    def delete(self, memory_id: str) -> CandidateMemory:
        memory = self.get_memory(memory_id)
        memory.status = MemoryStatus.DELETED.value
        memory.deleted_at = datetime.now(timezone.utc)
        self._update(memory)
        return memory

    def _update(self, memory: CandidateMemory) -> None:
        if self._store is not None:
            self._store.update_memory(memory)
