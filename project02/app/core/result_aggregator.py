"""Aggregation of direct and multi-agent execution outputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.execution_engine import ExecutionResult


@dataclass(slots=True)
class AggregationResult:
    task_id: str
    status: str
    final_output: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    missing_outputs: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class ResultAggregator:
    def __init__(self, logger: Any | None = None) -> None:
        self.logger = logger

    def aggregate_direct(self, task_id: str, output: Any) -> AggregationResult:
        result = AggregationResult(task_id=task_id, status="succeeded", final_output=self._stringify(output), sources=[])
        self._log(task_id, result)
        return result

    def aggregate(self, execution_result: ExecutionResult) -> AggregationResult:
        missing: list[str] = []
        sources: list[dict[str, Any]] = []
        successful_outputs: list[tuple[str, str | None, Any]] = []
        for step in execution_result.step_results:
            source = {"step_id": step.step_id, "status": step.status, "capability": step.capability, "output": step.output}
            sources.append(source)
            if step.status != "succeeded" or step.output in (None, ""):
                missing.append(step.step_id)
            else:
                successful_outputs.append((step.step_id, step.capability, step.output))
        conflicts = self._detect_conflicts(successful_outputs)
        status = "failed" if execution_result.status not in {"succeeded", "success"} or missing else "succeeded"
        if conflicts:
            status = "needs_review"
        final_output = self._compose_output(successful_outputs, execution_result.error)
        result = AggregationResult(
            task_id=execution_result.task_id,
            status=status,
            final_output=final_output,
            sources=sources,
            missing_outputs=missing,
            conflicts=conflicts,
            error=execution_result.error,
        )
        self._log(execution_result.task_id, result)
        return result

    def _detect_conflicts(self, outputs: list[tuple[str, str | None, Any]]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        dict_values: dict[str, tuple[str, Any]] = {}
        for step_id, _capability, output in outputs:
            if isinstance(output, str) and "conflict:" in output.lower():
                conflicts.append({"step_id": step_id, "reason": output})
            if isinstance(output, dict):
                for key, value in output.items():
                    if key in dict_values and dict_values[key][1] != value:
                        conflicts.append(
                            {
                                "field": key,
                                "first_step_id": dict_values[key][0],
                                "second_step_id": step_id,
                                "values": [dict_values[key][1], value],
                            }
                        )
                    else:
                        dict_values[key] = (step_id, value)
        return conflicts

    def _compose_output(self, outputs: list[tuple[str, str | None, Any]], error: str | None) -> str:
        if not outputs:
            return error or ""
        final_output = self._select_final_facing_output(outputs)
        if final_output is not None:
            return self._stringify(final_output)
        if len(outputs) == 1:
            return self._stringify(outputs[0][2])
        return "\n\n".join(f"{step_id}: {self._stringify(output)}" for step_id, _capability, output in outputs)

    def _select_final_facing_output(self, outputs: list[tuple[str, str | None, Any]]) -> Any | None:
        for preferred in ("writer", "reviewer"):
            for _step_id, capability, output in reversed(outputs):
                if capability == preferred and output not in (None, ""):
                    return output
        return None

    def _stringify(self, output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, Mapping):
            return self._stringify_mapping(output)
        if isinstance(output, list):
            return "\n".join(self._stringify(item) for item in output if item not in (None, ""))
        return str(output)

    def _stringify_mapping(self, output: Mapping[str, Any]) -> str:
        if "tool_results" in output and isinstance(output["tool_results"], list):
            return self._stringify_tool_results(output["tool_results"])
        if "results" in output and isinstance(output["results"], list):
            return self._stringify_search_results(output["results"])
        safe_items = {
            key: value
            for key, value in output.items()
            if key
            not in {
                "invocation_id",
                "task_id",
                "input",
                "permission_status",
                "created_at",
                "finished_at",
                "requested_by",
            }
        }
        return "\n".join(f"{key}: {self._stringify(value)}" for key, value in safe_items.items() if value not in (None, ""))

    def _stringify_tool_results(self, results: list[Any]) -> str:
        rendered: list[str] = []
        for result in results:
            if isinstance(result, Mapping):
                tool_name = result.get("tool_name", "tool")
                status = result.get("execution_status") or result.get("status")
                output = result.get("output")
                body = self._stringify(output) if output is not None else str(result.get("message", ""))
                rendered.append(f"{tool_name} ({status}):\n{body}".strip())
            elif result not in (None, ""):
                rendered.append(str(result))
        return "\n\n".join(rendered)

    def _stringify_search_results(self, results: list[Any]) -> str:
        rendered: list[str] = []
        for item in results[:8]:
            if not isinstance(item, Mapping):
                if item not in (None, ""):
                    rendered.append(str(item))
                continue
            title = item.get("title") or item.get("source") or "Result"
            snippet = item.get("snippet") or item.get("summary") or ""
            url = item.get("url")
            line = f"- {title}"
            if snippet:
                line += f": {snippet}"
            if url:
                line += f" ({url})"
            rendered.append(line)
        return "\n".join(rendered)

    def _log(self, task_id: str, result: AggregationResult) -> None:
        if self.logger is None:
            return
        payload = asdict(result)
        if hasattr(self.logger, "log_event"):
            self.logger.log_event(task_id, "result_aggregated", payload)
        elif hasattr(self.logger, "log"):
            self.logger.log(task_id, "result_aggregated", payload)
        elif hasattr(self.logger, "record"):
            self.logger.record(task_id, "result_aggregated", payload)
