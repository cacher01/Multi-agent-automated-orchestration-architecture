from app.core.execution_engine import ExecutionResult, StepResult
from app.core.result_aggregator import ResultAggregator


def test_aggregate_normal_merge_preserves_sources():
    execution = ExecutionResult(
        task_id="task-1",
        status="succeeded",
        step_results=[StepResult("s1", "succeeded", "alpha"), StepResult("s2", "succeeded", "beta")],
    )

    result = ResultAggregator().aggregate(execution)

    assert result.status == "succeeded"
    assert "s1: alpha" in result.final_output
    assert result.sources[0]["step_id"] == "s1"


def test_conflict_detection_for_dict_fields():
    execution = ExecutionResult(
        task_id="task-1",
        status="succeeded",
        step_results=[StepResult("s1", "succeeded", {"answer": "A"}), StepResult("s2", "succeeded", {"answer": "B"})],
    )

    result = ResultAggregator().aggregate(execution)

    assert result.status == "needs_review"
    assert result.conflicts[0]["field"] == "answer"


def test_missing_output_detection():
    execution = ExecutionResult(
        task_id="task-1",
        status="succeeded",
        step_results=[StepResult("s1", "succeeded", ""), StepResult("s2", "failed", error="boom")],
    )

    result = ResultAggregator().aggregate(execution)

    assert result.status == "failed"
    assert result.missing_outputs == ["s1", "s2"]


def test_aggregate_sanitizes_internal_tool_records_from_final_output():
    execution = ExecutionResult(
        task_id="task-1",
        status="succeeded",
        step_results=[
            StepResult(
                "s1",
                "succeeded",
                {
                    "tool_results": [
                        {
                            "invocation_id": "tool-1",
                            "task_id": "task-1",
                            "tool_name": "web_search",
                            "permission_status": "allowed",
                            "input": {"query": "internal"},
                            "output": {"results": [{"title": "AAPL market cap", "url": "https://example.com", "snippet": "Apple data"}]},
                        }
                    ]
                },
                capability="researcher",
            )
        ],
    )

    result = ResultAggregator().aggregate(execution)

    assert "AAPL market cap" in result.final_output
    assert "Apple data" in result.final_output
    assert "invocation_id" not in result.final_output
    assert "permission_status" not in result.final_output
    assert "input" not in result.final_output


def test_aggregate_prefers_writer_output_for_final_answer():
    execution = ExecutionResult(
        task_id="task-1",
        status="succeeded",
        step_results=[
            StepResult("s1", "succeeded", "planner checklist", capability="planner"),
            StepResult("s2", "succeeded", "research notes", capability="researcher"),
            StepResult("s3", "succeeded", "final report", capability="writer"),
        ],
    )

    result = ResultAggregator().aggregate(execution)

    assert result.status == "succeeded"
    assert result.final_output == "final report"
