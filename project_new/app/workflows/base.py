from dataclasses import dataclass, field

from app.core.enums import WorkflowType


@dataclass
class WorkflowResult:
    workflow: WorkflowType
    web_used: bool = False
    sub_agent_summaries: list[str] = field(default_factory=list)

