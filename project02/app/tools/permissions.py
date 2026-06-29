from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.base import SUPPORTED_TOOL_NAMES

DEFAULT_TOOL_PERMISSIONS: dict[str, set[str]] = {
    "planner": set(),
    "researcher": {"web_search", "web_fetch", "api_caller"},
    "tool_user": set(SUPPORTED_TOOL_NAMES),
    "writer": set(),
    "reviewer": set(),
    "analyst": {"calculator", "database_query"},
    "explorer": {"web_search", "web_fetch", "api_caller"},
    "orchestrator": {"weather_query", "time_lookup", "calculator", "web_search", "api_caller"},
}


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    agent_capability: str
    tool_name: str
    reason: str


@dataclass
class PermissionManager:
    permission_map: dict[str, set[str]] = field(
        default_factory=lambda: {key: set(value) for key, value in DEFAULT_TOOL_PERMISSIONS.items()}
    )

    def allowed_tools_for(self, agent_capability: str) -> set[str]:
        return set(self.permission_map.get(agent_capability, set()))

    def check(self, agent_capability: str, tool_name: str) -> PermissionDecision:
        if tool_name not in SUPPORTED_TOOL_NAMES:
            return PermissionDecision(
                allowed=False,
                agent_capability=agent_capability,
                tool_name=tool_name,
                reason=f"Unsupported tool: {tool_name}",
            )

        allowed_tools = self.permission_map.get(agent_capability, set())
        if tool_name not in allowed_tools:
            return PermissionDecision(
                allowed=False,
                agent_capability=agent_capability,
                tool_name=tool_name,
                reason=f"{agent_capability} is not allowed to use {tool_name}",
            )

        return PermissionDecision(
            allowed=True,
            agent_capability=agent_capability,
            tool_name=tool_name,
            reason="Tool intent is permitted for recording",
        )
