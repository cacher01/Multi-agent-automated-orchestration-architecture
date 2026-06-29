from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.services.task_service import MemoryNotFoundError, TaskService

router = APIRouter(prefix="/memories", tags=["memories"])


def get_task_service(request: Request) -> TaskService:
    return request.app.state.task_service


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


@router.get("")
def list_memories(task_service: TaskServiceDep) -> dict:
    return task_service.list_memories()


@router.post("/{memory_id}/approve")
def approve_memory(memory_id: str, task_service: TaskServiceDep) -> dict:
    try:
        return task_service.approve_memory(memory_id)
    except MemoryNotFoundError as exc:
        raise _not_found(memory_id) from exc


@router.post("/{memory_id}/reject")
def reject_memory(memory_id: str, task_service: TaskServiceDep) -> dict:
    try:
        return task_service.reject_memory(memory_id)
    except MemoryNotFoundError as exc:
        raise _not_found(memory_id) from exc


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, task_service: TaskServiceDep) -> dict:
    try:
        return task_service.delete_memory(memory_id)
    except MemoryNotFoundError as exc:
        raise _not_found(memory_id) from exc


def _not_found(memory_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "memory_not_found",
            "message": f"Memory not found: {memory_id}",
            "details": {"memory_id": memory_id},
        },
    )
