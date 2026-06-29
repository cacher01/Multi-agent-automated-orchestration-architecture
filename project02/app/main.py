from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import capabilities, memories, tasks
from app.services.task_service import TaskService

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_DIR = WEB_DIR / "templates"


def create_app(task_service: TaskService | None = None) -> FastAPI:
    app = FastAPI(title="Multi-Agent Orchestration Framework MVP")
    app.state.task_service = task_service or TaskService.with_default_storage()

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(tasks.router)
    app.include_router(capabilities.router)
    app.include_router(memories.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(TEMPLATE_DIR / "index.html")

    return app


app = create_app()
