from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.task_service import TaskNotFoundError, TaskRequest, TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


class SubmitTaskRequest(BaseModel):
    input: str = Field(min_length=1)
    session_id: str | None = None
    persist_logs: bool = False
    persist_intermediate_results: bool = False


def get_task_service(request: Request) -> TaskService:
    return request.app.state.task_service


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


@router.post("")
def submit_task(
    payload: SubmitTaskRequest,
    background_tasks: BackgroundTasks,
    task_service: TaskServiceDep,
) -> dict:
    try:
        return task_service.submit_task(
            TaskRequest(
                input=payload.input,
                session_id=payload.session_id,
                persist_logs=payload.persist_logs,
                persist_intermediate_results=payload.persist_intermediate_results,
            ),
            background_tasks.add_task,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "invalid_request", "message": str(exc), "details": {}},
        ) from exc


@router.get("/{task_id}")
def get_task(task_id: str, task_service: TaskServiceDep) -> dict:
    try:
        return task_service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise _not_found(task_id) from exc


@router.get("/{task_id}/result")
def get_task_result(task_id: str, task_service: TaskServiceDep) -> dict:
    try:
        return task_service.get_result(task_id)
    except TaskNotFoundError as exc:
        raise _not_found(task_id) from exc


@router.get("/{task_id}/logs")
def get_task_logs(task_id: str, task_service: TaskServiceDep) -> dict:
    try:
        return task_service.get_logs(task_id)
    except TaskNotFoundError as exc:
        raise _not_found(task_id) from exc


def _not_found(task_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "task_not_found",
            "message": f"Task not found: {task_id}",
            "details": {"task_id": task_id},
        },
    )
