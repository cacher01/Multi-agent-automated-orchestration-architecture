from __future__ import annotations

from fastapi import APIRouter

from app.agents.schemas import BUILT_IN_CAPABILITIES
from app.tools.registry import ToolRegistry

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities")
def get_capabilities() -> dict:
    registry = ToolRegistry()
    return {
        "agents": list(BUILT_IN_CAPABILITIES),
        "tools": registry.list_tools(),
        "tool_definitions": registry.describe_tools(),
        "tool_execution_enabled": True,
    }
