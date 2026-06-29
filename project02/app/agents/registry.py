from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.schemas import BUILT_IN_CAPABILITIES, AgentDefinition

DEFAULT_AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "planner": AgentDefinition(
        "planner",
        "You are a planning agent. Decompose the assigned task into concrete, ordered work items, dependencies, assumptions, and deliverables. Return concise structured text.",
    ),
    "researcher": AgentDefinition(
        "researcher",
        "You are a research agent. Collect and organize only the information available in the prompt and permitted shared context. Clearly mark unknowns and needed tools.",
    ),
    "tool_user": AgentDefinition(
        "tool_user",
        "You are a tool-using agent. Interpret tool results from shared context and explain their relevance. Do not invent unavailable tool outputs.",
    ),
    "writer": AgentDefinition(
        "writer",
        "You are a writing agent. Produce the requested artifact from upstream context, preserving user intent, constraints, and useful details.",
    ),
    "reviewer": AgentDefinition(
        "reviewer",
        "You are a review agent. Check whether the upstream result satisfies the original task, identify gaps, conflicts, and concrete fixes.",
    ),
    "analyst": AgentDefinition(
        "analyst",
        "You are an analysis agent. Compare options, reason through tradeoffs, and produce structured conclusions grounded in the shared context.",
    ),
    "explorer": AgentDefinition(
        "explorer",
        "You are an exploration agent. Explore alternative approaches or perspectives and surface non-obvious risks and opportunities.",
    ),
}


@dataclass
class AgentRegistry:
    definitions: dict[str, AgentDefinition] = field(default_factory=lambda: dict(DEFAULT_AGENT_DEFINITIONS))

    def list_capabilities(self) -> list[str]:
        return sorted(self.definitions)

    def get(self, capability: str) -> AgentDefinition:
        if capability not in self.definitions:
            raise KeyError(f"Unknown agent capability: {capability}")
        return self.definitions[capability]

    def validate_builtin_coverage(self) -> bool:
        return set(self.definitions) == set(BUILT_IN_CAPABILITIES)
