"""Plan execution over fakeable agent, budget, permission, context, and logger dependencies."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.execution_planner import ExecutionPlan, PlanStep


@dataclass(slots=True)
class StepResult:
    step_id: str
    status: str
    output: Any = None
    error: str | None = None
    capability: str | None = None


@dataclass(slots=True)
class ExecutionResult:
    task_id: str
    status: str
    step_results: list[StepResult] = field(default_factory=list)
    error: str | None = None
    completed_parts: list[str] = field(default_factory=list)
    incomplete_parts: list[str] = field(default_factory=list)


class ExecutionEngine:
    def __init__(
        self,
        agent_runtime: Any | None = None,
        budget_manager: Any | None = None,
        permission_manager: Any | None = None,
        tool_gateway: Any | None = None,
        context_manager: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        self.agent_runtime = agent_runtime
        self.budget_manager = budget_manager
        self.permission_manager = permission_manager
        self.tool_gateway = tool_gateway
        self.context_manager = context_manager
        self.logger = logger

    def execute(self, plan: ExecutionPlan, session_context: str | None = None) -> ExecutionResult:
        if plan.requires_clarification:
            return ExecutionResult(plan.task_id, "waiting_for_clarification", error=plan.clarification_question)
        if plan.execution_mode == "direct":
            return self._execute_direct(plan)
        if plan.execution_mode == "dag":
            return self._execute_dag(plan, session_context=session_context)
        if plan.execution_mode == "discussion":
            return self._execute_linear(plan, discussion=True, session_context=session_context)
        if plan.execution_mode == "handoff":
            return self._execute_linear(plan, handoff=True, session_context=session_context)
        return self._execute_linear(plan, session_context=session_context)

    def _execute_direct(self, plan: ExecutionPlan) -> ExecutionResult:
        if not plan.steps:
            return ExecutionResult(plan.task_id, "succeeded")
        step = plan.steps[0]
        timeout = self._check_timeout(plan.task_id)
        if timeout is not True:
            return ExecutionResult(plan.task_id, "timeout", error=str(timeout), incomplete_parts=[step.step_id])
        budget = self._check_budget(plan.task_id, step)
        if budget is not True:
            return ExecutionResult(plan.task_id, "budget_exceeded", error=str(budget), incomplete_parts=[step.step_id])
        if step.kind == "tool":
            tool_result = self._run_step_tools(plan.task_id, step, {})
            if isinstance(tool_result, StepResult):
                self._record_step(plan.task_id, step, tool_result)
                return ExecutionResult(
                    plan.task_id,
                    tool_result.status,
                    [tool_result],
                    error=tool_result.error,
                    incomplete_parts=[step.step_id],
                )
            result = StepResult(
                step.step_id,
                "succeeded",
                output=tool_result.get("tool_results", []) if isinstance(tool_result, dict) else step.description,
                capability=step.capability,
            )
            self._record_step(plan.task_id, step, result)
            return ExecutionResult(plan.task_id, "succeeded", [result], completed_parts=[step.step_id])
        return ExecutionResult(plan.task_id, "succeeded", [StepResult(step.step_id, "succeeded", step.description, capability=step.capability)], completed_parts=[step.step_id])

    def _execute_linear(
        self,
        plan: ExecutionPlan,
        discussion: bool = False,
        handoff: bool = False,
        session_context: str | None = None,
    ) -> ExecutionResult:
        results: list[StepResult] = []
        shared_context: dict[str, Any] = {}
        if session_context:
            shared_context["session_context"] = session_context
        for step in plan.steps:
            timeout = self._check_timeout(plan.task_id)
            if timeout is not True:
                return self._failed(plan, results, "timeout", str(timeout), step.step_id)
            budget = self._check_budget(plan.task_id, step)
            if budget is not True:
                return self._failed(plan, results, "budget_exceeded", str(budget), step.step_id)
            if discussion:
                shared_context["discussion_outputs"] = [result.output for result in results]
            if handoff and results:
                shared_context["handoff_context"] = results[-1].output
            tool_context = self._run_step_tools(plan.task_id, step, shared_context)
            if isinstance(tool_context, StepResult):
                results.append(tool_context)
                self._record_step(plan.task_id, step, tool_context)
                return self._failed(plan, results, tool_context.status, tool_context.error or "Tool step failed.", step.step_id)
            result = self._invoke_step(plan.task_id, step, shared_context)
            results.append(result)
            self._record_step(plan.task_id, step, result)
            if result.status != "succeeded":
                return self._failed(plan, results, "failed", result.error or "Agent step failed.", step.step_id)
        return ExecutionResult(plan.task_id, "succeeded", results, completed_parts=[item.step_id for item in results])

    def _execute_dag(self, plan: ExecutionPlan, session_context: str | None = None) -> ExecutionResult:
        remaining = {step.step_id: step for step in plan.steps}
        results: dict[str, StepResult] = {}
        ordered_results: list[StepResult] = []
        while remaining:
            ready = [
                step
                for step in remaining.values()
                if all(dep in results and results[dep].status == "succeeded" for dep in step.dependencies)
            ]
            if not ready:
                incomplete = list(remaining)
                return ExecutionResult(plan.task_id, "failed", ordered_results, "Unresolved step dependencies.", list(results), incomplete)
            for step in ready:
                timeout = self._check_timeout(plan.task_id)
                if timeout is not True:
                    return self._failed(plan, ordered_results, "timeout", str(timeout), step.step_id)
                budget = self._check_budget(plan.task_id, step)
                if budget is not True:
                    return self._failed(plan, ordered_results, "budget_exceeded", str(budget), step.step_id)
                shared_context = {dep: results[dep].output for dep in step.dependencies}
                if session_context:
                    shared_context["session_context"] = session_context
                tool_context = self._run_step_tools(plan.task_id, step, shared_context)
                if isinstance(tool_context, StepResult):
                    results[step.step_id] = tool_context
                    ordered_results.append(tool_context)
                    self._record_step(plan.task_id, step, tool_context)
                    return self._failed(plan, ordered_results, tool_context.status, tool_context.error or "Tool step failed.", step.step_id)
                result = self._invoke_step(plan.task_id, step, shared_context)
                results[step.step_id] = result
                ordered_results.append(result)
                self._record_step(plan.task_id, step, result)
                del remaining[step.step_id]
                if result.status != "succeeded":
                    return self._failed(plan, ordered_results, "failed", result.error or "Agent step failed.", step.step_id)
        return ExecutionResult(plan.task_id, "succeeded", ordered_results, completed_parts=[item.step_id for item in ordered_results])

    def _invoke_step(self, task_id: str, step: PlanStep, shared_context: dict[str, Any]) -> StepResult:
        self._log(task_id, "step_started", {"step_id": step.step_id, "capability": step.capability})
        if self.agent_runtime is None:
            return StepResult(step.step_id, "succeeded", f"{step.capability}: {step.description}", capability=step.capability)
        try:
            try:
                output = self.agent_runtime.invoke(step.capability, step.description, shared_context)
            except TypeError:
                output = self.agent_runtime.invoke(self._build_agent_request(task_id, step, shared_context))
            status = getattr(output, "status", None) or (output.get("status") if isinstance(output, dict) else None) or "succeeded"
            value = getattr(output, "output", None) if not isinstance(output, dict) else output.get("output", output)
            error = getattr(output, "error", None) if not isinstance(output, dict) else output.get("error")
            return StepResult(step.step_id, status, value, error, step.capability)
        except Exception as exc:
            return StepResult(step.step_id, "failed", error=str(exc), capability=step.capability)

    def _run_step_tools(self, task_id: str, step: PlanStep, shared_context: dict[str, Any]) -> dict[str, Any] | StepResult:
        if not step.allowed_tools:
            return {}
        permission = self._check_permissions(task_id, step)
        if permission is not True:
            return StepResult(step.step_id, "permission_denied", error=str(permission), capability=step.capability)
        if self.tool_gateway is None:
            return StepResult(
                step.step_id,
                "failed",
                output={"tool_results": []},
                error="Tool execution is required but no tool gateway is configured.",
                capability=step.capability,
            )

        tool_results: list[dict[str, Any]] = []
        for tool_name in step.allowed_tools:
            try:
                result = self.tool_gateway.request_tool(
                    tool_name=tool_name,
                    requested_by=step.capability,
                    input=self._tool_input_for(tool_name, step.description, shared_context),
                    task_id=task_id,
                )
            except Exception as exc:
                return StepResult(step.step_id, "failed", {"tool_results": tool_results}, str(exc), step.capability)

            record = result.to_record() if hasattr(result, "to_record") else self._tool_result_record(result)
            visible_record = self._agent_visible_tool_result(record)
            tool_results.append(visible_record)
            status = str(getattr(result, "execution_status", record.get("execution_status", "")))
            if status != "succeeded":
                message = str(getattr(result, "message", record.get("message", "Tool execution failed.")))
                error = getattr(result, "error", None) or record.get("error")
                if error:
                    code = error.get("code") if isinstance(error, dict) else None
                    message = f"{message} Error code: {code or 'tool_error'}."
                if self._can_continue_after_tool_failure(step, tool_name):
                    shared_context.setdefault("tool_results", []).extend(tool_results)
                    shared_context.setdefault("tool_failures", []).append(
                        {"tool_name": tool_name, "message": message}
                    )
                    return {"tool_results": tool_results}
                return StepResult(step.step_id, "failed", {"tool_results": tool_results}, message, step.capability)

        shared_context.setdefault("tool_results", []).extend(tool_results)
        return {"tool_results": tool_results}

    def _tool_result_record(self, result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return dict(result)
        return {
            "tool_name": getattr(result, "tool_name", "unknown"),
            "execution_status": getattr(result, "execution_status", "unknown"),
            "message": getattr(result, "message", ""),
            "output": getattr(result, "output", None),
            "error": getattr(result, "error", None),
        }

    def _agent_visible_tool_result(self, record: dict[str, Any]) -> dict[str, Any]:
        visible: dict[str, Any] = {
            "tool_name": record.get("tool_name", "unknown"),
            "execution_status": record.get("execution_status", "unknown"),
            "message": record.get("message", ""),
        }
        output = record.get("output")
        if output is not None:
            visible["output"] = self._compact_tool_output(output)
        error = record.get("error")
        if error:
            visible["error"] = error
        return visible

    def _compact_tool_output(self, output: Any) -> Any:
        if not isinstance(output, dict):
            return output
        compact = dict(output)
        results = compact.get("results")
        if isinstance(results, list):
            compact["results"] = [self._compact_search_item(item) for item in results[:5]]
        return compact

    def _compact_search_item(self, item: Any) -> Any:
        if not isinstance(item, dict):
            return item
        allowed_keys = ("title", "url", "snippet", "source", "published_at")
        return {key: item[key] for key in allowed_keys if key in item and item[key] not in (None, "")}

    def _can_continue_after_tool_failure(self, step: PlanStep, tool_name: str) -> bool:
        return (
            step.capability == "researcher"
            and tool_name in {"web_search", "web_fetch"}
            and "original task:" in step.description.lower()
            and step.description.lower().lstrip().startswith("research")
        )

    def _tool_input_for(self, tool_name: str, description: str, shared_context: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "calculator":
            expression = re.sub(r"[^0-9+\-*/().% ]", " ", description)
            return {"expression": " ".join(expression.split())}
        if tool_name == "time_lookup":
            return {"timezone": "Asia/Shanghai", "operation": "now"}
        if tool_name == "weather_query":
            return {"location": self._extract_location(description)}
        if tool_name == "web_fetch":
            match = re.search(r"https?://\S+", description)
            return {"url": match.group(0) if match else description.strip(), "max_chars": 12000}
        if tool_name == "web_search":
            return {"query": self._search_query_for(description), "max_results": 8}
        if tool_name == "file_reader":
            return {"path": self._extract_path(description), "max_chars": 20000}
        if tool_name == "database_query":
            return {"query_type": "task", "filters": {"text": description}}
        if tool_name == "api_caller":
            return {"method": "GET", "url": description.strip()}
        return {"task": description, "context": shared_context}

    def _extract_location(self, description: str) -> str:
        cleaned = re.sub(
            r"(?i)\b(weather|forecast|temperature|query|search|today|current|please|for|in)\b",
            " ",
            description,
        )
        cleaned = re.sub(r"(天气|气温|温度|预报|查询|查一下|今天|现在|请|的)", " ", cleaned)
        return " ".join(cleaned.split()) or description.strip()

    def _extract_path(self, description: str) -> str:
        match = re.search(r"([A-Za-z]:\\[^\s]+|[./\\\w.-]+\.[A-Za-z0-9]{1,12})", description)
        return match.group(1) if match else description.strip()

    def _search_query_for(self, description: str) -> str:
        task = self._extract_original_task(description)
        focus = description.split("\n", 1)[0]
        query = f"{task} {focus}" if task and task not in focus else task or focus
        query = " ".join(query.split())
        financial_markers = ("market cap", "market capitalization", "stock price", "investment", "valuation", "earnings")
        chinese_financial_markers = ("\u5e02\u503c", "\u80a1\u4ef7", "\u6295\u8d44", "\u4f30\u503c", "\u8d22\u62a5")
        if any(marker in query.lower() for marker in financial_markers) or any(
            marker in query for marker in chinese_financial_markers
        ):
            return (
                f"{query} market capitalization stock price Tesla Nvidia Apple official financial data "
                "companiesmarketcap macrotrends ycharts"
            )[:260]
        return query[:220]

    def _extract_original_task(self, description: str) -> str:
        match = re.search(r"Original task:\s*(.+)", description, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return " ".join(match.group(1).split())
        return ""

    def _build_agent_request(self, task_id: str, step: PlanStep, shared_context: dict[str, Any]) -> Any:
        from app.agents.schemas import AgentInvocationRequest
        from app.memory.context import SharedContext

        context = SharedContext(
            task_summary=step.description,
            upstream_artifacts=dict(shared_context),
            allowed_information={"step_id": step.step_id},
        )
        return AgentInvocationRequest(
            task_id=task_id,
            capability=step.capability,
            subtask=step.description,
            shared_context=context,
        )

    def _check_budget(self, task_id: str, step: PlanStep) -> bool | str:
        if self.budget_manager is None:
            return True
        checker = (
            getattr(self.budget_manager, "check_step", None)
            or getattr(self.budget_manager, "check_agent_call", None)
            or getattr(self.budget_manager, "check_child_agent", None)
        )
        if checker is None:
            return True
        try:
            try:
                result = checker(task_id, step)
            except TypeError:
                result = checker(task_id)
        except Exception as exc:
            return getattr(exc, "message", str(exc))
        return True if result is None or result is True or getattr(result, "allowed", False) else getattr(result, "reason", result)

    def _check_timeout(self, task_id: str) -> bool | str:
        if self.budget_manager is None:
            return True
        checker = getattr(self.budget_manager, "check_timeout", None) or getattr(self.budget_manager, "is_timed_out", None)
        if checker is None:
            return True
        try:
            result = checker(task_id)
        except Exception as exc:
            return getattr(exc, "message", str(exc))
        if result is None:
            return True
        if isinstance(result, bool):
            return True if result is False else "task timeout"
        return True if getattr(result, "allowed", False) else getattr(result, "reason", result)

    def _check_permissions(self, task_id: str, step: PlanStep) -> bool | str:
        if self.permission_manager is None:
            return True
        checker = getattr(self.permission_manager, "check", None) or getattr(self.permission_manager, "can_use_tools", None)
        if checker is None:
            return True
        for tool_name in step.allowed_tools:
            try:
                try:
                    result = checker(step.capability, tool_name, task_id)
                except TypeError:
                    result = checker(step.capability, tool_name)
            except Exception as exc:
                return getattr(exc, "message", str(exc))
            if result is not True and not getattr(result, "allowed", False):
                return getattr(result, "reason", result)
        return True

    def _record_step(self, task_id: str, step: PlanStep, result: StepResult) -> None:
        if self.context_manager is not None:
            writer = getattr(self.context_manager, "add_intermediate_result", None) or getattr(self.context_manager, "save_intermediate_result", None)
            if writer is not None:
                writer(task_id, step.step_id, result.output)
        self._log(task_id, "step_completed", {"step": asdict(step), "result": asdict(result)})

    def _failed(self, plan: ExecutionPlan, results: list[StepResult], status: str, error: str, failed_step_id: str) -> ExecutionResult:
        completed = [result.step_id for result in results if result.status == "succeeded"]
        incomplete = [step.step_id for step in plan.steps if step.step_id not in completed]
        self._log(plan.task_id, "execution_failed", {"status": status, "error": error, "failed_step_id": failed_step_id})
        return ExecutionResult(plan.task_id, status, results, error, completed, incomplete)

    def _log(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if self.logger is None:
            return
        if hasattr(self.logger, "log_event"):
            self.logger.log_event(task_id, event_type, payload)
        elif hasattr(self.logger, "log"):
            self.logger.log(task_id, event_type, payload)
        elif hasattr(self.logger, "record"):
            self.logger.record(task_id, event_type, payload)
