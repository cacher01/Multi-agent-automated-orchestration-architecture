"""Main orchestration control flow."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.decision_engine import DecisionEngine, DecisionResult
from app.core.execution_engine import ExecutionResult
from app.core.execution_planner import ExecutionPlanner
from app.core.result_aggregator import AggregationResult, ResultAggregator
from app.tools.gateway import ToolGateway


@dataclass(slots=True)
class FailureResult:
    task_id: str
    reason: str
    error_message: str
    completed_parts: list[str] = field(default_factory=list)
    incomplete_parts: list[str] = field(default_factory=list)
    retry_count: int = 0
    last_status: str = "failed"


@dataclass(slots=True)
class CandidateMemory:
    source_task_id: str
    content: str
    reason: str
    status: str = "pending"


@dataclass(slots=True)
class OrchestratorOutcome:
    task_id: str
    status: str
    mode: str
    result: str | None = None
    decision: DecisionResult | None = None
    aggregation: AggregationResult | None = None
    failure: FailureResult | None = None
    tool_required: bool = False
    tool_message: str | None = None
    clarification_question: str | None = None
    candidate_memories: list[CandidateMemory] = field(default_factory=list)
    retry_count: int = 0


class OrchestratorAgent:
    def __init__(
        self,
        decision_engine: DecisionEngine | None = None,
        execution_planner: ExecutionPlanner | None = None,
        execution_engine: Any | None = None,
        result_aggregator: ResultAggregator | None = None,
        llm_provider: Any | None = None,
        tool_interface: Any | None = None,
        logger: Any | None = None,
        memory_extractor: Any | None = None,
        max_retries: int = 3,
    ) -> None:
        self.decision_engine = decision_engine or DecisionEngine(logger=logger)
        self.execution_planner = execution_planner or ExecutionPlanner(logger=logger)
        self.execution_engine = execution_engine
        self.result_aggregator = result_aggregator or ResultAggregator(logger=logger)
        self.llm_provider = llm_provider
        self.tool_interface = tool_interface or ToolGateway(logger=logger)
        self.logger = logger
        self.memory_extractor = memory_extractor
        self.max_retries = max_retries

    def handle(self, task_id: str, task_input: str, session_context: str | None = None) -> OrchestratorOutcome:
        decision = self.decision_engine.decide(task_input, task_id)
        self._log(task_id, "orchestrator_routed", asdict(decision))
        if decision.requires_clarification:
            question = decision.clarification_question or "Please provide more task details."
            self._log(task_id, "clarification_requested", {"question": question})
            return OrchestratorOutcome(
                task_id=task_id,
                status="waiting_for_clarification",
                mode="direct",
                decision=decision,
                clarification_question=question,
            )
        if decision.execution_mode == "direct" and decision.requires_tools:
            return self._handle_tool_intent(task_id, task_input, decision)
        if decision.execution_mode == "direct" and decision.complexity == "simple":
            return self._handle_direct(task_id, task_input, decision)
        return self._handle_complex(task_id, task_input, decision, session_context=session_context)

    def _handle_direct(self, task_id: str, task_input: str, decision: DecisionResult) -> OrchestratorOutcome:
        output = self._generate_direct(task_input)
        aggregation = self.result_aggregator.aggregate_direct(task_id, output)
        memories = self._extract_candidate_memories(task_id, output)
        self._log(task_id, "task_succeeded", {"mode": "direct"})
        return OrchestratorOutcome(
            task_id=task_id,
            status="succeeded",
            mode="direct",
            result=aggregation.final_output,
            decision=decision,
            aggregation=aggregation,
            candidate_memories=memories,
        )

    def _handle_tool_intent(self, task_id: str, task_input: str, decision: DecisionResult) -> OrchestratorOutcome:
        tool_name = decision.tool_name or "unknown"
        message = f"Tool request prepared for {tool_name}."
        tool_result: Any | None = None
        if self.tool_interface is not None:
            recorder = getattr(self.tool_interface, "record_intent", None) or getattr(self.tool_interface, "request_tool", None)
            if recorder is not None:
                try:
                    tool_result = recorder(
                        tool_name=tool_name,
                        requested_by="orchestrator",
                        input=self._tool_input_for(tool_name, task_input),
                        task_id=task_id,
                    )
                except TypeError:
                    recorder(tool_name, "orchestrator", {"task": task_input})
        if tool_result is not None:
            status = getattr(tool_result, "execution_status", "")
            output = getattr(tool_result, "output", None)
            error = getattr(tool_result, "error", None)
            result_message = getattr(tool_result, "message", message)
            if status == "succeeded" and output is not None:
                message = self._format_tool_output(tool_name, output)
            elif status:
                message = f"Tool {tool_name} {status}: {result_message}"
                if error:
                    code = error.get("code") if isinstance(error, dict) else None
                    if code:
                        message = f"{message} Error code: {code}."
        self._log(task_id, "tool_requested", {"tool_name": tool_name, "message": message})
        aggregation = self.result_aggregator.aggregate_direct(task_id, message)
        return OrchestratorOutcome(
            task_id=task_id,
            status="succeeded",
            mode="direct",
            result=message,
            decision=decision,
            aggregation=aggregation,
            tool_required=True,
            tool_message=message,
        )

    def _tool_input_for(self, tool_name: str, task_input: str) -> dict[str, Any]:
        if tool_name == "weather_query":
            location = task_input.strip()
            city = _detect_location(location)
            if city is not None:
                return {"location": city}
            for marker in (
                "weather",
                "forecast",
                "temperature",
                "in",
                "today",
                "please",
                "天气",
                "气温",
                "温度",
                "预报",
                "查询",
                "查一下",
                "今天",
                "现在",
                "?",
                "？",
            ):
                location = location.replace(marker, " ")
            location = " ".join(location.split()) or task_input
            return {"location": location}
        if tool_name == "calculator":
            expression = re.sub(r"(?i)\b(calculate|calculator|what is|compute)\b", " ", task_input)
            expression = re.sub(r"[^0-9+\-*/().% ]", " ", expression)
            return {"expression": " ".join(expression.split())}
        if tool_name == "time_lookup":
            return {"timezone": _detect_timezone(task_input) or "Asia/Shanghai", "operation": "now"}
        if tool_name == "web_fetch":
            return {"url": task_input.strip()}
        if tool_name == "web_search":
            return {"query": task_input}
        return {"task": task_input}

    def _format_tool_output(self, tool_name: str, output: Any) -> str:
        if not isinstance(output, dict):
            return f"Tool {tool_name} result: {output}"
        if tool_name == "weather_query":
            location = output.get("location") or "the requested location"
            summary = output.get("summary") or output
            source = output.get("source")
            suffix = f" Source: {source}." if source else ""
            return f"Weather for {location}: {summary}{suffix}"
        if tool_name == "time_lookup":
            timezone = output.get("timezone") or "the requested timezone"
            value = output.get("datetime") or output
            return f"Current time in {timezone}: {value}"
        if tool_name == "calculator":
            return f"Calculation result: {output.get('result')}"
        return f"Tool {tool_name} result: {output}"

    def _handle_complex(
        self,
        task_id: str,
        task_input: str,
        decision: DecisionResult,
        session_context: str | None = None,
    ) -> OrchestratorOutcome:
        last_execution: ExecutionResult | None = None
        last_aggregation: AggregationResult | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                self._log(task_id, "retry_started", {"attempt": attempt})
            plan = self.execution_planner.create_plan(task_id, task_input, decision)
            if self.execution_engine is None:
                raise RuntimeError("Execution engine is required for complex tasks.")
            try:
                last_execution = self.execution_engine.execute(plan, session_context=session_context)
            except TypeError:
                last_execution = self.execution_engine.execute(plan)
            last_aggregation = self.result_aggregator.aggregate(last_execution)
            accepted = self._review(task_id, task_input, last_aggregation)
            self._log(task_id, "review_completed", {"accepted": accepted, "attempt": attempt})
            if accepted:
                final_output = self._finalize_complex_output(task_id, task_input, decision.execution_mode, last_aggregation)
                memories = self._extract_candidate_memories(task_id, final_output)
                self._log(task_id, "task_succeeded", {"mode": decision.execution_mode, "retry_count": attempt})
                return OrchestratorOutcome(
                    task_id=task_id,
                    status="succeeded",
                    mode=decision.execution_mode,
                    result=final_output,
                    decision=decision,
                    aggregation=last_aggregation,
                    candidate_memories=memories,
                    retry_count=attempt,
                )
            if not self._should_retry(last_aggregation):
                break
        failure = FailureResult(
            task_id=task_id,
            reason="review_failed",
            error_message=(last_aggregation.error if last_aggregation else None)
            or "Complex task result did not pass orchestrator review after retries.",
            completed_parts=last_execution.completed_parts if last_execution else [],
            incomplete_parts=last_execution.incomplete_parts if last_execution else [],
            retry_count=self.max_retries,
            last_status=last_aggregation.status if last_aggregation else "failed",
        )
        self._log(task_id, "task_failed", asdict(failure))
        return OrchestratorOutcome(
            task_id=task_id,
            status="failed",
            mode=decision.execution_mode,
            decision=decision,
            aggregation=last_aggregation,
            failure=failure,
            retry_count=self.max_retries,
        )

    def _generate_direct(self, task_input: str) -> str:
        if self.llm_provider is None:
            return f"Direct response: {task_input}"
        try:
            response = self.llm_provider.generate(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the Orchestrator Agent in a multi-agent framework. "
                            "For simple direct tasks, answer as the main agent itself. "
                            "Do not mention that another model is answering for you."
                        ),
                    },
                    {"role": "user", "content": task_input},
                ],
                {"temperature": 0.2, "max_tokens": 1200},
            )
            return str(getattr(response, "content", response))
        except Exception as exc:
            return f"Direct response failed because the model backend was unavailable: {self._public_error(exc)}"

    def _review(self, task_id: str, task_input: str, aggregation: AggregationResult) -> bool:
        if aggregation.status != "succeeded":
            return False
        if aggregation.conflicts or aggregation.missing_outputs:
            return False
        if not aggregation.final_output.strip():
            return False
        if self._contains_tool_failure(aggregation):
            return False
        reviewer = getattr(self.llm_provider, "review", None) if self.llm_provider is not None else None
        if reviewer is None:
            return True
        review_result = reviewer(task_input, aggregation.final_output)
        return bool(getattr(review_result, "accepted", review_result))

    def _should_retry(self, aggregation: AggregationResult) -> bool:
        error_text = f"{aggregation.error or ''}\n{aggregation.final_output}".lower()
        non_retryable_markers = (
            "agent llm call exceeded",
            "tool execution is required but no tool gateway",
            "permission",
            "budget",
            "timeout",
            "provider_not_configured",
            "path_not_allowed",
            "command_denied",
        )
        return not any(marker in error_text for marker in non_retryable_markers)

    def _contains_tool_failure(self, aggregation: AggregationResult) -> bool:
        for source in aggregation.sources:
            output = source.get("output")
            if not isinstance(output, dict):
                continue
            for item in output.get("tool_results", []):
                if isinstance(item, dict) and item.get("execution_status") != "succeeded":
                    return True
        return False

    def _finalize_complex_output(
        self,
        task_id: str,
        task_input: str,
        execution_mode: str,
        aggregation: AggregationResult,
    ) -> str:
        self._log(task_id, "orchestrator_finalized", {"used_llm": False, "mode": "deterministic_aggregation"})
        return aggregation.final_output

    def _public_error(self, error: Any) -> str:
        text = str(error)
        text = re.sub(r"https?://\S+", "[url omitted]", text)
        text = re.sub(r"%[0-9A-Fa-f]{2}(?:%[0-9A-Fa-f]{2})+", "[encoded text omitted]", text)
        return text[:240]

    def _extract_candidate_memories(self, task_id: str, final_output: str) -> list[CandidateMemory]:
        if self.memory_extractor is None:
            return []
        extracted = self.memory_extractor.extract(task_id, final_output)
        memories: list[CandidateMemory] = []
        for item in extracted or []:
            if isinstance(item, CandidateMemory):
                memories.append(item)
            elif isinstance(item, dict):
                memories.append(
                    CandidateMemory(
                        source_task_id=task_id,
                        content=str(item.get("content", "")),
                        reason=str(item.get("reason", "Candidate memory extracted after task completion.")),
                        status="pending",
                    )
                )
        self._log(task_id, "candidate_memories_extracted", {"count": len(memories)})
        return memories

    def _log(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if self.logger is None:
            return
        if hasattr(self.logger, "log_event"):
            self.logger.log_event(task_id, event_type, payload)
        elif hasattr(self.logger, "log"):
            self.logger.log(task_id, event_type, payload)
        elif hasattr(self.logger, "record"):
            self.logger.record(task_id, event_type, payload)


_LOCATION_ALIASES = {
    "北京": "Beijing",
    "上海": "Shanghai",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "杭州": "Hangzhou",
    "南京": "Nanjing",
    "成都": "Chengdu",
    "重庆": "Chongqing",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "天津": "Tianjin",
    "东京": "Tokyo",
    "伦敦": "London",
    "纽约": "New York",
}

_TIMEZONE_ALIASES = {
    "北京": "Asia/Shanghai",
    "上海": "Asia/Shanghai",
    "中国": "Asia/Shanghai",
    "东京": "Asia/Tokyo",
    "日本": "Asia/Tokyo",
    "伦敦": "Europe/London",
    "英国": "Europe/London",
    "纽约": "America/New_York",
    "美国东部": "America/New_York",
    "洛杉矶": "America/Los_Angeles",
    "utc": "UTC",
    "gmt": "UTC",
}


def _detect_location(text: str) -> str | None:
    lowered = text.lower()
    for marker, location in _LOCATION_ALIASES.items():
        if marker in text:
            return location
    for english in ("beijing", "shanghai", "guangzhou", "shenzhen", "hangzhou", "tokyo", "london", "new york"):
        if english in lowered:
            return english.title()
    return None


def _detect_timezone(text: str) -> str | None:
    lowered = text.lower()
    for marker, timezone in _TIMEZONE_ALIASES.items():
        if marker in text or marker in lowered:
            return timezone
    if "utc" in lowered or "gmt" in lowered:
        return "UTC"
    return None
