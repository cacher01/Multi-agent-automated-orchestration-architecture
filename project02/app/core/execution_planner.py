"""Execution plan generation from structured decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from app.core.decision_engine import DecisionResult


@dataclass(slots=True)
class PlanStep:
    step_id: str
    description: str
    capability: str
    kind: str = "agent"
    dependencies: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionPlan:
    plan_id: str
    task_id: str
    execution_mode: str
    steps: list[PlanStep] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    budget: dict[str, int] = field(default_factory=dict)
    timeout: int = 300
    requires_clarification: bool = False
    clarification_question: str | None = None


class ExecutionPlanner:
    def __init__(
        self,
        storage: Any | None = None,
        logger: Any | None = None,
        default_budget: dict[str, int] | None = None,
        default_timeout: int = 300,
    ) -> None:
        self.storage = storage
        self.logger = logger
        self.default_budget = default_budget or {
            "task_token_budget": 12000,
            "agent_token_budget": 3000,
            "max_llm_calls_per_task": 20,
            "max_child_agents_per_task": 6,
        }
        self.default_timeout = default_timeout

    def create_plan(self, task_id: str, task_input: str, decision: DecisionResult) -> ExecutionPlan:
        if decision.requires_clarification:
            plan = ExecutionPlan(
                plan_id=self._new_id(),
                task_id=task_id,
                execution_mode="direct",
                budget=dict(self.default_budget),
                timeout=self.default_timeout,
                requires_clarification=True,
                clarification_question=decision.clarification_question
                or "Please provide the missing task details before execution.",
            )
            return self._persist_and_log(plan)

        allowed_tools = [decision.tool_name] if decision.tool_name else []
        mode = decision.execution_mode
        capabilities = decision.required_capabilities or self._default_capabilities(mode)
        steps = self._build_steps(task_input, mode, capabilities, allowed_tools, decision.requires_tools)
        dependencies = {step.step_id: list(step.dependencies) for step in steps if step.dependencies}
        plan = ExecutionPlan(
            plan_id=self._new_id(),
            task_id=task_id,
            execution_mode=mode,
            steps=steps,
            dependencies=dependencies,
            required_capabilities=capabilities,
            allowed_tools=allowed_tools,
            budget=dict(self.default_budget),
            timeout=self.default_timeout,
        )
        return self._persist_and_log(plan)

    def _build_steps(
        self,
        task_input: str,
        mode: str,
        capabilities: list[str],
        allowed_tools: list[str],
        requires_tools: bool,
    ) -> list[PlanStep]:
        if mode == "direct":
            return [
                PlanStep(
                    step_id="direct-1",
                    description=task_input,
                    capability=capabilities[0] if capabilities else "orchestrator",
                    kind="tool" if requires_tools else "direct",
                    allowed_tools=allowed_tools,
                )
            ]
        if mode == "dag":
            if requires_tools and allowed_tools:
                research = PlanStep(
                    "step-1",
                    f"Collect the required tool-backed information for the original task. Use tool results as evidence and clearly mark unavailable data.\nOriginal task: {task_input}",
                    "researcher" if "web_search" in allowed_tools or "web_fetch" in allowed_tools else "tool_user",
                    allowed_tools=allowed_tools,
                )
                planning = PlanStep(
                    "step-2",
                    f"Decompose the original task into concrete subtasks, deliverables, constraints, and dependencies using the research output.\nOriginal task: {task_input}",
                    "planner",
                    dependencies=["step-1"],
                )
                analysis = PlanStep(
                    "step-3",
                    f"Analyze the task using the research and planner outputs. Identify key decisions, risks, and information gaps.\nOriginal task: {task_input}",
                    "analyst",
                    dependencies=["step-1", "step-2"],
                )
                draft = PlanStep(
                    "step-4",
                    f"Produce the requested user-facing artifact using the research, planner, and analysis outputs.\nOriginal task: {task_input}",
                    "writer",
                    dependencies=["step-1", "step-2", "step-3"],
                )
                review = PlanStep(
                    "step-5",
                    f"Review the artifact against the original task. List gaps and concrete corrections if any.\nOriginal task: {task_input}",
                    "reviewer",
                    dependencies=["step-4"],
                )
                return [research, planning, analysis, draft, review]
            planning = PlanStep(
                "step-1",
                f"Decompose the original task into concrete subtasks, deliverables, constraints, and dependencies.\nOriginal task: {task_input}",
                "planner",
            )
            analysis_dependencies = ["step-1"]
            steps = [planning]
            if requires_tools and allowed_tools:
                research = PlanStep(
                    "step-2",
                    f"Collect the required tool-backed information for the original task. Use tool results as evidence and clearly mark unavailable data.\nOriginal task: {task_input}",
                    "researcher" if "web_search" in allowed_tools or "web_fetch" in allowed_tools else "tool_user",
                    dependencies=["step-1"],
                    allowed_tools=allowed_tools,
                )
                steps.append(research)
                analysis_dependencies.append("step-2")
            analysis = PlanStep(
                f"step-{len(steps) + 1}",
                f"Analyze the task using the planner output. Identify key decisions, risks, and information needed.\nOriginal task: {task_input}",
                "analyst",
                dependencies=analysis_dependencies,
            )
            draft = PlanStep(
                f"step-{len(steps) + 2}",
                f"Produce the requested user-facing artifact using the planner and analysis outputs.\nOriginal task: {task_input}",
                "writer",
                dependencies=["step-1", analysis.step_id],
            )
            review = PlanStep(
                f"step-{len(steps) + 3}",
                f"Review the artifact against the original task. List gaps and concrete corrections if any.\nOriginal task: {task_input}",
                "reviewer",
                dependencies=[draft.step_id],
            )
            return [*steps, analysis, draft, review]
        if mode == "discussion":
            first_capability = "researcher" if requires_tools and allowed_tools else "analyst"
            return [
                PlanStep(
                    "step-1",
                    f"Produce a structured first perspective for: {task_input}",
                    first_capability,
                    allowed_tools=allowed_tools if requires_tools else [],
                ),
                PlanStep(
                    "step-2",
                    f"Produce an alternate perspective and challenge assumptions for: {task_input}",
                    "explorer",
                    dependencies=["step-1"],
                ),
                PlanStep("step-3", f"Synthesize the perspectives into a balanced answer for: {task_input}", "writer", dependencies=["step-1", "step-2"]),
                PlanStep("step-4", f"Review the synthesized answer against the original task: {task_input}", "reviewer", dependencies=["step-3"]),
            ]
        if mode == "handoff":
            first_capability = "researcher" if requires_tools and allowed_tools else capabilities[0] if capabilities else "analyst"
            return [
                PlanStep(
                    "step-1",
                    f"Prepare handoff context, assumptions, and next actions for: {task_input}",
                    first_capability,
                    allowed_tools=allowed_tools if requires_tools else [],
                ),
                PlanStep("step-2", f"Continue from handoff context and finish the original task: {task_input}", capabilities[-1] if capabilities else "writer", dependencies=["step-1"]),
            ]
        if mode == "supervisor" and requires_tools and allowed_tools:
            research_steps = self._research_profile_steps(task_input, allowed_tools)
            analysis = PlanStep(
                f"step-{len(research_steps) + 1}",
                f"Analyze and compare the research outputs. Identify conclusions, uncertainty, and gaps.\nOriginal task: {task_input}",
                "analyst",
                dependencies=[step.step_id for step in research_steps],
            )
            draft = PlanStep(
                f"step-{len(research_steps) + 2}",
                f"Produce the requested user-facing answer or report from the research and analysis outputs.\nOriginal task: {task_input}",
                "writer",
                dependencies=[analysis.step_id],
            )
            review = PlanStep(
                f"step-{len(research_steps) + 3}",
                f"Review the final answer against the original task and list any material gaps or corrections.\nOriginal task: {task_input}",
                "reviewer",
                dependencies=[draft.step_id],
            )
            return [*research_steps, analysis, draft, review]
        return [
            PlanStep(
                step_id=f"step-{index + 1}",
                description=f"{capability} contribution for: {task_input}",
                capability=capability,
                allowed_tools=allowed_tools if capability in {"researcher", "tool_user"} else [],
            )
            for index, capability in enumerate(capabilities)
        ]

    def _research_profile_steps(self, task_input: str, allowed_tools: list[str]) -> list[PlanStep]:
        angles = [
            (
                "development history",
                "Research the company's development history, founding background, major milestones, leadership changes, and strategic turning points.",
            ),
            (
                "business model",
                "Research the company's business model, revenue structure, operating segments, market position, and recent business updates.",
            ),
            (
                "products and technology",
                "Research the company's main products, core technologies, product roadmap, production capability, and technical differentiation.",
            ),
        ]
        return [
            PlanStep(
                f"step-{index}",
                f"{instruction} Use tools and cite available evidence. Mark unavailable data clearly.\nResearch angle: {angle}.\nOriginal task: {task_input}",
                "researcher",
                allowed_tools=allowed_tools,
            )
            for index, (angle, instruction) in enumerate(angles, start=1)
        ]

    def _default_capabilities(self, mode: str) -> list[str]:
        if mode == "discussion":
            return ["analyst", "explorer", "writer"]
        if mode == "handoff":
            return ["analyst", "writer"]
        return ["analyst", "writer"]

    def _persist_and_log(self, plan: ExecutionPlan) -> ExecutionPlan:
        payload = asdict(plan)
        if self.storage is not None:
            if hasattr(self.storage, "save_execution_plan"):
                self.storage.save_execution_plan(plan)
            elif hasattr(self.storage, "save_plan"):
                try:
                    self.storage.save_plan(self._to_shared_plan(plan))
                except Exception:
                    self.storage.save_plan(plan)
        if self.logger is not None:
            if hasattr(self.logger, "log_event"):
                self.logger.log_event(plan.task_id, "plan_created", payload)
            elif hasattr(self.logger, "log"):
                self.logger.log(plan.task_id, "plan_created", payload)
            elif hasattr(self.logger, "record"):
                self.logger.record(plan.task_id, "plan_created", payload)
        return plan

    def _new_id(self) -> str:
        return f"plan-{uuid4().hex}"

    def _to_shared_plan(self, plan: ExecutionPlan) -> Any:
        from app.models.plan import ExecutionMode as SharedExecutionMode
        from app.models.plan import ExecutionPlan as SharedExecutionPlan
        from app.models.plan import ExecutionStep

        return SharedExecutionPlan(
            plan_id=plan.plan_id,
            task_id=plan.task_id,
            execution_mode=SharedExecutionMode(plan.execution_mode),
            steps=[
                ExecutionStep(
                    step_id=step.step_id,
                    description=step.description,
                    capability=step.capability,
                    dependencies=step.dependencies,
                    allowed_tools=step.allowed_tools,
                    metadata={"kind": step.kind},
                )
                for step in plan.steps
            ],
            dependencies=plan.dependencies,
            required_capabilities=plan.required_capabilities,
            allowed_tools=plan.allowed_tools,
            budget=plan.budget,
            timeout=plan.timeout,
        )
