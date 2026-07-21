import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.config import Settings
from app.db.database import init_database
from app.db.repositories import Repository
from app.llm.client import LLMResponse, MockLLMClient, OpenAICompatibleClient
from app.orchestration.orchestrator import Orchestrator
from app.services.event_service import EventService
from app.services.artifact_service import ArtifactService
from app.services.quota_service import QuotaService
from app.services.result_service import ResultService
from app.services.task_service import TaskService
from app.tools.builtin.tavily_search import TavilySearchTool
from app.tools.builtin.web_fetch import WebFetchTool
from app.tools.builtin.calculator import CalculatorTool
from app.tools.builtin.current_time import CurrentTimeTool
from app.tools.builtin.date_calculator import DateCalculatorTool
from app.tools.builtin.research_tools import (
    CitationCheckerTool,
    QueryPlannerTool,
    ResultCriticTool,
)
from app.tools.builtin.unit_converter import UnitConverterTool
from app.tools.builtin.weather import WeatherTool
from app.tools.builtin.artifacts import ArtifactArchiverTool, ArtifactWriterTool
from app.tools.executor import ToolExecutor
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry


class TaskCreateRequest(BaseModel):
    input: str
    session_id: str | None = None


class SessionCreateRequest(BaseModel):
    title: str = "New session"


def create_app(testing: bool = False) -> FastAPI:
    settings = Settings(database_url="sqlite:///:memory:") if testing else Settings.from_env_file()
    db_path = ":memory:" if testing else _sqlite_path(settings.database_url)
    connection = init_database(db_path)
    repository = Repository(connection)
    event_service = EventService(repository)
    result_service = ResultService(repository)
    artifact_service = ArtifactService(settings, repository)
    quota_service = QuotaService(repository, model=settings.llm_model)
    registry = ToolRegistry()
    registry.register(CurrentTimeTool())
    registry.register(CalculatorTool())
    registry.register(DateCalculatorTool())
    registry.register(UnitConverterTool())
    registry.register(QueryPlannerTool())
    registry.register(CitationCheckerTool(evidence_loader=repository.list_evidence))
    registry.register(ResultCriticTool())
    registry.register(ArtifactWriterTool(artifact_service))
    registry.register(ArtifactArchiverTool(artifact_service))
    if settings.weather_api_key:
        registry.register(WeatherTool(settings))
    if settings.tavily_api_key:
        registry.register(TavilySearchTool(settings))
        registry.register(WebFetchTool(settings))
    tool_executor = ToolExecutor(
        registry=registry,
        policy=ToolPolicy(max_tool_calls=settings.max_tool_calls),
        repository=repository,
        event_service=event_service,
    )
    llm = _testing_llm() if testing else OpenAICompatibleClient(settings)
    orchestrator = Orchestrator(
        settings=settings,
        repository=repository,
        event_service=event_service,
        result_service=result_service,
        llm=llm,
        tool_executor=tool_executor,
    )
    task_service = TaskService(
        repository=repository,
        event_service=event_service,
        orchestrator=orchestrator,
        run_inline=testing,
    )

    app = FastAPI(title="Multi-Agent Orchestration")
    app.state.repository = repository
    app.state.event_service = event_service
    app.state.result_service = result_service
    app.state.task_service = task_service
    app.state.artifact_service = artifact_service
    app.state.orchestrator = orchestrator
    app.state.quota_service = quota_service

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.post("/tasks")
    async def create_task(request: TaskCreateRequest):
        task = await task_service.create_task(request.input, request.session_id)
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "workflow": task.get("workflow"),
            "session_id": task.get("session_id"),
        }

    @app.post("/sessions")
    async def create_session(request: SessionCreateRequest):
        return repository.create_session(request.title)

    @app.get("/sessions")
    async def list_sessions(limit: int = 50):
        return repository.list_sessions(limit)

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: str):
        session = repository.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session": session,
            "tasks": repository.list_session_tasks(session_id),
        }

    @app.post("/sessions/{session_id}/tasks")
    async def create_session_task(session_id: str, request: TaskCreateRequest):
        if repository.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        task = await task_service.create_task(request.input, session_id)
        return {
            "task_id": task["task_id"],
            "session_id": session_id,
            "status": task["status"],
            "workflow": task.get("workflow"),
        }

    @app.get("/tasks")
    async def list_tasks(limit: int = 50):
        return repository.list_tasks(limit)

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str):
        task = repository.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @app.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str):
        try:
            return task_service.cancel_task(task_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Task not found")

    @app.get("/tasks/{task_id}/events")
    async def get_events(task_id: str):
        if repository.get_task(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return event_service.list_events(task_id)

    @app.get("/tasks/{task_id}/result")
    async def get_result(task_id: str):
        result = result_service.get(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Result not found")
        return result

    @app.get("/tasks/{task_id}/replay")
    async def replay_task(task_id: str):
        task = repository.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task": task,
            "events": event_service.list_events(task_id),
            "agents": repository.list_agents(task_id),
            "tool_calls": repository.list_tool_calls(task_id),
            "evidence": repository.list_evidence(task_id),
            "result": result_service.get(task_id),
            "artifacts": repository.list_artifacts(task_id),
        }

    @app.get("/tasks/{task_id}/artifacts")
    async def list_artifacts(task_id: str):
        if repository.get_task(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return repository.list_artifacts(task_id)

    @app.get("/tasks/{task_id}/artifacts/{artifact_id}")
    async def download_artifact(task_id: str, artifact_id: str):
        artifact = repository.get_artifact(task_id, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        try:
            path = artifact_service.resolve_artifact_path(artifact)
        except ValueError:
            raise HTTPException(status_code=404, detail="Artifact not found")
        if not path.is_file() or path.is_symlink():
            raise HTTPException(status_code=404, detail="Artifact file not found")
        return FileResponse(
            path,
            media_type=artifact["media_type"],
            filename=artifact["filename"],
        )

    # ── Quota endpoints (embedded dashboard) ─────────────────────
    @app.get("/quota/summary")
    async def quota_summary(scope: str = "today"):
        return quota_service.summary(scope)

    @app.get("/quota/breakdown")
    async def quota_breakdown(by: str = "workflow", scope: str = "today"):
        return {"items": quota_service.breakdown(by, scope)}

    @app.get("/quota/timeline")
    async def quota_timeline(days: int = 7):
        return {"items": quota_service.timeline(max(1, min(days, 90)))}

    @app.get("/quota/limits")
    async def quota_limits():
        return quota_service.limits()

    @app.get("/quota/recent")
    async def quota_recent(limit: int = 12):
        return {"items": quota_service.recent_tasks(max(1, min(limit, 50)))}

    @app.get("/quota/sessions")
    async def quota_sessions(limit: int = 8):
        return {"items": quota_service.session_consumption(max(1, min(limit, 50)))}

    @app.get("/quota/pricing")
    async def quota_pricing():
        return {"model": settings.llm_model, "table": {k: v for k, v in __import__("app.services.quota_service", fromlist=["MODEL_PRICING"]).MODEL_PRICING.items() if k != "default"}}

    @app.get("/tasks/{task_id}/stream")
    async def stream_events(task_id: str):
        if repository.get_task(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        queue = event_service.subscribe(task_id)

        async def generator():
            try:
                for event in event_service.list_events(task_id):
                    yield _sse(event)
                while True:
                    event = await queue.get()
                    yield _sse(event)
                    if event["type"] in {"task_completed", "task_degraded", "task_failed", "task_cancelled"}:
                        break
            finally:
                event_service.unsubscribe(task_id, queue)

        return StreamingResponse(generator(), media_type="text/event-stream")

    @app.get("/", response_class=HTMLResponse)
    @app.get("/ui", response_class=HTMLResponse)
    async def ui():
        index = static_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="UI not found")
        return index.read_text(encoding="utf-8")

    return app


def _sse(event: dict) -> str:
    data = dict(event)
    status = None
    if event["type"] == "task_completed":
        status = "completed"
    elif event["type"] == "task_degraded":
        status = "degraded"
    elif event["type"] == "task_failed":
        status = "failed"
    elif event["type"] == "task_cancelled":
        status = "cancelled"
    if status:
        data["status"] = status
    return f"event: event\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sqlite_path(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "", 1)
    return "orchestration.db"


def _testing_llm() -> MockLLMClient:
    responses = []
    for _ in range(10):
        responses.extend(
            [
            LLMResponse(
                content=json.dumps(
                    {
                        "workflow": "direct",
                        "complexity": "simple",
                        "reason": "test",
                        "requires_web": False,
                        "expected_sub_agents": 0,
                        "estimated_steps": 1,
                        "risk_flags": [],
                        "constraints": {
                            "max_agents": 4,
                            "max_swarm_rounds": 2,
                            "max_concurrent_agents": 2,
                        },
                    }
                )
            ),
            LLMResponse(
                content=json.dumps(
                    {
                        "answer": "A multi-agent orchestration framework coordinates task execution across agents.",
                        "citations": [],
                        "limitations": [],
                        "confidence": 0.8,
                        "used_workflow": "direct",
                        "web_used": False,
                    }
                )
            ),
            ]
        )
    return MockLLMClient(responses)


app = create_app()
